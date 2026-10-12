"""WS08-T08: metrics per template, the equal-weight aggregate without RESP, the excess over the background.

ILLUSTRATIVE, UNVERIFIED, FIXTURE-ONLY. Counts, windows and tails are arithmetic test values; the expected numbers are
computed by hand in the comments (T = 86_400_000 ms, H = one hour, D = one day). Nothing here is a clinical value.
"""

from __future__ import annotations

import json
import math
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from ralmon.benchmark import GroundTruthEvent, InjectedClass
from ralmon.eval.background import DAY_MS, Footprint, PatientBackground
from ralmon.eval.metrics import (
    AGGREGATE_TEMPLATES,
    EXCESS_COLUMNS,
    TEMPLATE_COLUMNS,
    TEMPLATES,
    MatchConfig,
    bootstrap_statistic,
    excess_table,
    match_events,
    table_aggregate_metric,
    table_excess_detected,
    table_excess_events,
    table_excess_recall,
    table_template_metric,
    template_of_event,
)
from tests.eval.helpers import MINI, ms
from tests.eval.test_background_false_alarms import background_document, entry
from tests.eval.test_runner import (
    SCRIPT,
    factory_for,
    hand_document,
    read_metrics,
    run_doc,
)

H = 3_600_000
D = DAY_MS
CFG = MatchConfig(60_000, "onset")
SCALAR = {"value", "ci_lo", "ci_hi", "ci_cluster_lo", "ci_cluster_hi"}


def row(**counts: float) -> np.ndarray:
    """A summed row of the template table with the given counts (e.g. ``RANGE_gt=4``), all other columns 0."""
    out = np.zeros(len(TEMPLATE_COLUMNS))
    for name, value in counts.items():
        out[TEMPLATE_COLUMNS.index(name)] = value
    return out


def event(
    cls: str, template: str | None, onset: int, end: int | None = None, injected: bool | None = None
) -> GroundTruthEvent:
    c = InjectedClass(cls)
    return GroundTruthEvent(c, "fx", onset, end, c is not InjectedClass.C1 if injected is None else injected, template, None)


# ---- the vocabulary ----------------------------------------------------------------------------------------------------


def test_the_templates_and_the_aggregate_set_are_declared() -> None:
    assert TEMPLATES == ("RANGE", "SCHED", "HOLD", "COUNT", "RESP", "SYS", "INT")
    assert AGGREGATE_TEMPLATES == ("RANGE", "SCHED", "HOLD", "COUNT", "SYS", "INT")  # RESP is apart (ADR-072 (b))


def test_template_of_an_event_is_its_template_for_c1_and_sys_int_for_c2_c3() -> None:
    """C2 and C3 events carry no template (``template_id`` None); a C2 fault violates the system specification SYS and
    a C3 attack the integrity specification INT."""
    assert template_of_event(event("C1", "range", 0)) == "RANGE"
    assert template_of_event(event("C1", "resp", 0, 5)) == "RESP"
    assert template_of_event(event("C2", None, 0)) == "SYS"
    assert template_of_event(event("C3", None, 0)) == "INT"
    with pytest.raises(ValueError, match="template"):
        template_of_event(event("C1", "nonsense", 0))
    with pytest.raises(ValueError, match="template"):
        template_of_event(event("C1", None, 0))


# 1
def test_metrics_are_available_per_template(tmp_path: Path) -> None:
    """The hand case of test_runner (SCRIPT on the mini benchmark, six test patients, 12 patient-days, tolerance 60 s,
    three scored false alarms: p05 03:00, p06 12:00, p06 T+12:00). Truth by template (a C2 event is SYS, a C3 event INT):
    RANGE 2 (p01, p05), SCHED 1 (p03), COUNT 1 (p03 day end), RESP 1 (p01 closing step), SYS 2 (ble_dropout, stuck_at),
    INT 2 (replay, injection_naive), HOLD 0. True positives: RANGE 2, SCHED 1, COUNT 1, RESP 1, SYS 2, INT 0.
    Precision is TP / (TP + 3) because the false alarms are pooled (E3): RANGE 2/5, SCHED 1/4, COUNT 1/4, RESP 1/4,
    SYS 2/5, INT 0/3. F1 = 2 p r / (p + r): RANGE 0.571428..., SCHED 0.4, COUNT 0.4, SYS 0.571428..., INT 0.
    Delays: RANGE (30 000 + 0) / 2 = 15 000 ms, SCHED 0, COUNT -30 000, RESP 0, SYS 0, INT none."""
    m = read_metrics(run_doc(tmp_path, hand_document(), factory_for(SCRIPT))[0])
    block = m["per_template"]["ours-s1"]
    t = block["templates"]
    assert list(t) == ["RANGE", "SCHED", "HOLD", "COUNT", "SYS", "INT"]
    expected = {
        "RANGE": (2, 2, 2 / 5, 1.0, 4 / 7, 15_000.0),
        "SCHED": (1, 1, 1 / 4, 1.0, 0.4, 0.0),
        "COUNT": (1, 1, 1 / 4, 1.0, 0.4, -30_000.0),
        "SYS": (2, 2, 2 / 5, 1.0, 4 / 7, 0.0),
        "INT": (2, 0, 0.0, 0.0, 0.0, None),
    }
    for name, (n_gt, n_tp, precision, recall, f1, delay) in expected.items():
        e = t[name]
        assert (e["n_events"], e["n_matched"]) == (n_gt, n_tp), name
        assert e["precision"]["value"] == pytest.approx(precision), name
        assert e["recall"]["value"] == pytest.approx(recall), name
        assert e["f1"]["value"] == pytest.approx(f1), name
        assert set(e["recall"]) == SCALAR
        if delay is None:
            assert e["delay_ms"]["mean"]["value"] is None  # nothing matched: no delay, not zero
        else:
            assert e["delay_ms"]["mean"]["value"] == pytest.approx(delay), name
        assert e["delay_ms"]["n_matched"] == n_tp
    # HOLD has no truth event: null leaves (and an event count of zero), not zero and not NaN
    hold = t["HOLD"]
    assert hold["n_events"] == 0 and hold["n_matched"] == 0
    assert hold["precision"] is None and hold["recall"] is None and hold["f1"] is None
    assert hold["delay_ms"] is None
    # RESP is reported apart, with the same fields
    resp = block["resp"]
    assert (resp["n_events"], resp["n_matched"]) == (1, 1)
    assert resp["precision"]["value"] == pytest.approx(1 / 4)
    assert resp["recall"]["value"] == 1.0
    assert resp["delay_ms"]["mean"]["value"] == 0.0
    assert "NaN" not in json.dumps(m)


def test_a_template_with_no_truth_event_is_null_not_zero() -> None:
    total = row(RANGE_gt=3, RANGE_tp=1, fa_background=2, exposure_days=4)
    assert table_template_metric(total, "RANGE", "recall") == pytest.approx(1 / 3)
    for key in ("precision", "recall", "f1", "delay_mean", "fraction_early"):
        assert math.isnan(table_template_metric(total, "HOLD", key)), key  # nan here, null in the file
    # a template that has events but no match: recall 0, precision 0, delay undefined
    missed = row(SCHED_gt=2, fa_background=1)
    assert table_template_metric(missed, "SCHED", "recall") == 0.0
    assert table_template_metric(missed, "SCHED", "precision") == 0.0
    assert math.isnan(table_template_metric(missed, "SCHED", "delay_mean"))


def test_per_template_counts_of_a_matching_by_hand() -> None:
    """One patient, one day: a RANGE event at 10:00 matched 20 s late, a RANGE event at 12:00 missed, a C2 event at 15:00
    matched 40 s early, a C3 event at 18:00 missed; one false alarm at 03:00 (no injection anywhere)."""
    gt = [
        event("C1", "range", 10 * H, injected=False),
        event("C1", "range", 12 * H, injected=False),
        event("C2", None, 15 * H),
        event("C3", None, 18 * H),
    ]
    from tests.eval.helpers import det
    from ralmon.eval.metrics import template_table

    dets = [det(10 * H + 20_000), det(15 * H - 40_000), det(3 * H)]
    matching = match_events(gt, dets, CFG, n_days=1)
    table = template_table(matching, [0, 0, 0, 0], [0, 0, 0], 1, PatientBackground((), 1, margin_ms=0))
    total = table.sum(axis=0)
    assert total[TEMPLATE_COLUMNS.index("RANGE_gt")] == 2 and total[TEMPLATE_COLUMNS.index("RANGE_tp")] == 1
    assert total[TEMPLATE_COLUMNS.index("SYS_tp")] == 1 and total[TEMPLATE_COLUMNS.index("INT_tp")] == 0
    assert table_template_metric(total, "RANGE", "delay_mean") == 20_000.0
    assert table_template_metric(total, "SYS", "delay_mean") == -40_000.0
    assert table_template_metric(total, "SYS", "fraction_early") == 1.0
    assert table_template_metric(total, "RANGE", "fraction_early") == 0.0
    assert table_template_metric(total, "RANGE", "precision") == 0.5  # 1 / (1 + 1)


# 2
def test_aggregate_is_the_equal_weight_mean_of_the_templates_without_resp() -> None:
    """Hand counts (events, matched): RANGE 4/2 = 0.5, SCHED 2/2 = 1, HOLD 1/0 = 0, COUNT 3/1 = 1/3, SYS 5/5 = 1, INT 0
    events (absent), RESP 4/0 = 0.  Aggregate recall = mean of the templates PRESENT without RESP =
    (0.5 + 1 + 0 + 1/3 + 1) / 5 = 17/30 = 0.56666...; the pooled recall would be 10/15 = 0.6666... (not the aggregate).
    With RESP the mean would be (17/6) / 6 = 17/36 = 0.47222...; its removal moves the aggregate by 17/30 - 17/36 =
    17/180 = 0.094444..."""
    total = row(
        RANGE_gt=4, RANGE_tp=2, SCHED_gt=2, SCHED_tp=2, HOLD_gt=1, HOLD_tp=0, COUNT_gt=3, COUNT_tp=1,
        SYS_gt=5, SYS_tp=5, RESP_gt=4, RESP_tp=0, fa_background=3, exposure_days=7,
    )  # fmt: skip
    without = table_aggregate_metric(total, "recall")
    assert without == pytest.approx(17 / 30)
    with_resp = table_aggregate_metric(total, "recall", templates=(*AGGREGATE_TEMPLATES, "RESP"))
    assert with_resp == pytest.approx(17 / 36)
    assert without - with_resp == pytest.approx(17 / 180)
    pooled = (2 + 2 + 0 + 1 + 5) / (4 + 2 + 1 + 3 + 5)
    assert pooled == pytest.approx(2 / 3) and without != pytest.approx(pooled)
    # precision of a template is TP / (TP + 3): RANGE 2/5, SCHED 2/5, HOLD 0, COUNT 1/4, SYS 5/8 -> mean over five
    precisions = [2 / 5, 2 / 5, 0.0, 1 / 4, 5 / 8]
    assert table_aggregate_metric(total, "precision") == pytest.approx(sum(precisions) / 5)


def test_aggregate_f1_is_the_mean_of_the_template_f1_and_delay_the_mean_of_the_template_delays() -> None:
    # RANGE: gt 2, tp 1, FA 1 -> p = 1/2, r = 1/2, f1 = 1/2.  SYS: gt 1, tp 1 -> p = 1/2, r = 1, f1 = 2/3.
    total = row(
        RANGE_gt=2, RANGE_tp=1, RANGE_delay_n=1, RANGE_delay_sum_ms=1000,
        SYS_gt=1, SYS_tp=1, SYS_delay_n=1, SYS_delay_sum_ms=-3000, fa_background=1, exposure_days=1,
    )  # fmt: skip
    assert table_aggregate_metric(total, "f1") == pytest.approx((1 / 2 + 2 / 3) / 2)
    assert table_aggregate_metric(total, "delay_mean") == pytest.approx((1000 - 3000) / 2)  # equal weights, not pooled


def test_aggregate_is_undefined_when_no_template_has_an_event_and_resp_alone_does_not_make_one() -> None:
    assert math.isnan(table_aggregate_metric(row(), "recall"))
    only_resp = row(RESP_gt=3, RESP_tp=3, fa_background=1, exposure_days=1)
    assert math.isnan(table_aggregate_metric(only_resp, "recall"))  # RESP is not in the aggregate
    assert table_template_metric(only_resp, "RESP", "recall") == 1.0


def test_aggregate_leaves_of_the_runner_agree_with_the_template_leaves(tmp_path: Path) -> None:
    """From the hand case of test 1: present templates RANGE, SCHED, COUNT, SYS, INT (HOLD absent, RESP apart).
    Recall (1 + 1 + 1 + 1 + 0) / 5 = 0.8; precision (2/5 + 1/4 + 1/4 + 2/5 + 0) / 5 = 0.26; F1 (4/7 + 2/5 + 2/5 + 4/7 + 0) / 5;
    delay (15 000 + 0 - 30 000 + 0) / 4 over the four templates with a delay = -3750."""
    m = read_metrics(run_doc(tmp_path, hand_document(), factory_for(SCRIPT))[0])
    agg = m["per_template"]["ours-s1"]["aggregate"]
    assert agg["templates"] == ["RANGE", "SCHED", "HOLD", "COUNT", "SYS", "INT"]
    assert agg["templates_with_events"] == ["RANGE", "SCHED", "COUNT", "SYS", "INT"]
    assert agg["weights"] == "equal"
    assert agg["recall"]["value"] == pytest.approx(0.8)
    assert agg["precision"]["value"] == pytest.approx(0.26)
    assert agg["f1"]["value"] == pytest.approx((4 / 7 + 0.4 + 0.4 + 4 / 7) / 5)
    assert agg["delay_ms_mean"]["value"] == pytest.approx(-3750.0)
    assert set(agg["recall"]) == SCALAR


# 6
def test_resp_reported_apart_flag(tmp_path: Path) -> None:
    m = read_metrics(run_doc(tmp_path, hand_document(), factory_for(SCRIPT))[0])
    meta = m["meta"]["aggregate"]
    assert meta["weights"] == "equal"
    assert meta["templates"] == ["RANGE", "SCHED", "HOLD", "COUNT", "SYS", "INT"]
    assert meta["excluded"] == ["RESP"]
    why = meta["excluded_reason"]
    assert why.startswith("RESP excluded from the aggregate")
    assert "ADR-072" in why and "chance" in why
    assert "RESP" not in m["per_template"]["ours-s1"]["templates"]
    assert "resp" in m["per_template"]["ours-s1"]


def test_every_detector_gets_a_per_template_entry_even_a_scripted_one_with_no_detection(tmp_path: Path) -> None:
    m = read_metrics(run_doc(tmp_path, hand_document(), factory_for({}))[0])
    t = m["per_template"]["ours-s1"]["templates"]
    assert t["RANGE"]["recall"]["value"] == 0.0 and t["RANGE"]["precision"]["value"] is None  # 0 / (0 + 0) is undefined
    assert t["RANGE"]["delay_ms"]["mean"]["value"] is None
    assert "NaN" not in json.dumps(m)


# ---- the excess over the background -------------------------------------------------------------------------------------


def eventful_background(window: tuple[int, int]) -> PatientBackground:
    return PatientBackground((Footprint("hypertensive_spike", "C1", *window),), 2, margin_ms=0)


def test_excess_table_by_hand() -> None:
    """One patient, two days. A spike record covers 13:00-15:00 of day 0 (2 H) and 13:00-15:00 of day 1 (2 H). RANGE
    events: day 0 at 14:00 (in the window, detected), day 1 at 14:00 (in the window, missed), day 0 at 20:00 (outside,
    detected), day 1 at 08:00 (outside, missed), day 1 at 21:00 (outside, missed); one COUNT event at 14:00 of day 0 (another
    template: ignored).  In the windows: 2 events, 1 detected, 4 H = 1/6 day.  Outside every footprint: 3 events, 1 detected,
    48 H - 4 H = 44 H = 11/6 day."""
    bg = PatientBackground(
        (Footprint("hypertensive_spike", "C1", 13 * H, 15 * H), Footprint("hypertensive_spike", "C1", D + 13 * H, D + 15 * H)),
        2,
        margin_ms=0,
    )
    gt = [
        event("C1", "range", 14 * H, injected=False),
        event("C1", "range", D + 14 * H, injected=False),
        event("C1", "range", 20 * H, injected=False),
        event("C1", "range", D + 8 * H, injected=False),
        event("C1", "range", D + 21 * H, injected=False),
        event("C1", "count", 14 * H, injected=False),
    ]
    from tests.eval.helpers import det

    matching = match_events(gt, [det(14 * H), det(20 * H)], CFG, n_days=2)
    days = [0, 1, 0, 1, 1, 0]
    table = excess_table(matching, days, 2, bg, "C1/hypertensive_spike", "RANGE")
    total = table.sum(axis=0)
    col = {name: float(total[i]) for i, name in enumerate(EXCESS_COLUMNS)}
    assert col == pytest.approx(
        {"events_in": 2, "detected_in": 1, "exposure_in_days": 1 / 6, "events_bg": 3, "detected_bg": 1, "exposure_bg_days": 11 / 6}
    )
    # rate of events: 2 / (1/6) = 12 per day inside, 3 / (11/6) = 18/11 outside
    assert table_excess_events(total) == pytest.approx(12 - 18 / 11)
    assert table_excess_detected(total) == pytest.approx(6 - 6 / 11)  # 1 / (1/6) - 1 / (11/6)
    assert table_excess_recall(total) == pytest.approx(1 / 2 - 1 / 3)


# 5
def test_excess_over_background() -> None:
    """Eight patients of one day each; every patient has 0.1 day of window and 0.9 day outside (test values).
    Injected subtype: each patient has 1 event in the window and 0 or 1 event outside (4 of 8): rate in the windows
    8 / 0.8 = 10 per day, background 4 / 7.2 = 0.5555... per day, excess 9.4444...; the cluster interval over patients does
    not contain 0.  No-excess subtype: the window holds 4 or 5 events in turn per 0.1 day... scaled so that both rates are
    equal: 4 events in the windows over 0.8 day = 5 per day; the background has 36 events over 7.2 days = 5 per day;
    excess exactly 0 with patient-to-patient variation, so the interval contains 0."""
    n = 8
    patients = [f"p{i}" for i in range(n)]

    def table(events_in: list[float], events_bg: list[float]) -> np.ndarray:
        out = np.zeros((n, len(EXCESS_COLUMNS)))
        out[:, EXCESS_COLUMNS.index("events_in")] = events_in
        out[:, EXCESS_COLUMNS.index("exposure_in_days")] = 0.1
        out[:, EXCESS_COLUMNS.index("events_bg")] = events_bg
        out[:, EXCESS_COLUMNS.index("exposure_bg_days")] = 0.9
        return out

    injected = table([1] * 8, [0, 1] * 4)
    total = injected.sum(axis=0)
    assert table_excess_events(total) == pytest.approx(10 - 4 / 7.2)
    lo, hi = bootstrap_statistic(injected, table_excess_events, n_resamples=200, level=0.95, seed=3, clusters=patients)
    assert 0 < lo <= 10 - 4 / 7.2 <= hi

    none = table([0, 1, 0, 1, 0, 1, 0, 1], [4, 5, 4, 5, 4, 5, 4, 5])  # 4 in 0.8 day = 5; 36 in 7.2 days = 5
    assert table_excess_events(none.sum(axis=0)) == pytest.approx(0.0)
    lo, hi = bootstrap_statistic(none, table_excess_events, n_resamples=200, level=0.95, seed=3, clusters=patients)
    assert lo < 0 < hi


def test_excess_is_undefined_without_exposure_or_without_events() -> None:
    total = np.zeros(len(EXCESS_COLUMNS))
    assert math.isnan(table_excess_events(total)) and math.isnan(table_excess_detected(total))
    assert math.isnan(table_excess_recall(total))
    no_window = np.zeros(len(EXCESS_COLUMNS))
    no_window[EXCESS_COLUMNS.index("events_bg")] = 2
    no_window[EXCESS_COLUMNS.index("exposure_bg_days")] = 1
    assert math.isnan(table_excess_events(no_window))


def test_the_runner_reports_the_excess_of_an_injected_c1_subtype(tmp_path: Path) -> None:
    """The mini benchmark with a spike record covering 13:00-15:00 of p05 day 0 (the RANGE event at 14:00 of that patient
    is in the window; the RANGE event of p01 at 14:00 is outside every footprint). Both are detected by SCRIPT.
    Windows: 1 event, 1 detected, 2 H = 1/12 day; outside: 1 event, 1 detected, 12 - 1/12 = 143/12 days.
    Excess of the event rate 12 - 12/143; of the detected rate the same; of the recall 1 - 1 = 0."""
    bench = tmp_path / "bench"
    shutil.copytree(MINI, bench)
    path = bench / "truth" / "p05" / "0.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["injection_log"] = [entry("C1", "hypertensive_spike", ms(13), ms(15), truth_indices=(0,))]
    path.write_text(json.dumps(doc), encoding="utf-8")
    m = read_metrics(run_doc(tmp_path, background_document(bench), factory_for(SCRIPT))[0])
    block = m["background"]["excess_over_background"]["ours-s1"]["hypertensive_spike"]
    assert block["template"] == "RANGE"
    assert block["events"]["value"] == pytest.approx(12 - 12 / 143)
    assert block["detected"]["value"] == pytest.approx(12 - 12 / 143)
    assert block["recall"]["value"] == pytest.approx(0.0)
    assert set(block["events"]) >= SCALAR
    counts = block["counts"]
    assert counts["events_in_windows"] == 1 and counts["events_background"] == 1
    assert counts["exposure_in_windows_days"] == pytest.approx(1 / 12)
    assert counts["exposure_background_days"] == pytest.approx(143 / 12)
    assert "NaN" not in json.dumps(m)


def test_a_benchmark_without_injected_c1_records_has_an_empty_excess_block(tmp_path: Path) -> None:
    m = read_metrics(run_doc(tmp_path, background_document(None), factory_for(SCRIPT))[0])
    assert m["background"]["excess_over_background"]["ours-s1"] == {}
