"""WS08-T08: metrics per template, the equal-weight aggregate without RESP, the excess over the background.

ILLUSTRATIVE, UNVERIFIED, FIXTURE-ONLY. Counts, windows and tails are arithmetic test values; the expected numbers are
computed by hand in the comments (T = 86_400_000 ms, H = one hour, D = one day). Nothing here is a clinical value.

Fix round (review of WS08-T08): per-template PRECISION and F1 exist only for detectors whose detections carry a template
(``Alert.tau``); a plain ``Detection`` gets ``precision_pooled_fa`` only. A template WITH events whose true positives are 0 has
precision, recall and F1 equal to 0 (never NaN, never dropped), so the leaves of one aggregate average the same templates
(``templates_averaged``). The excess is a count per injection record.
"""

from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

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
    aggregate_templates,
    bootstrap_statistic,
    excess_counts,
    excess_table,
    match_events,
    table_aggregate_metric,
    table_excess_detected,
    table_excess_detected_per_record,
    table_excess_events,
    table_excess_events_per_record,
    table_excess_recall,
    table_template_metric,
    template_of_event,
    template_table,
)
from ralmon.spec import TemplateId
from tests.eval.helpers import C1, MINI, UND, alert, det, ms
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
    cls: str,
    template: str | None,
    onset: int,
    end: int | None = None,
    injected: bool | None = None,
) -> GroundTruthEvent:
    c = InjectedClass(cls)
    return GroundTruthEvent(
        c,
        "fx",
        onset,
        end,
        c is not InjectedClass.C1 if injected is None else injected,
        template,
        None,
    )


# the hand case with detections that carry a template (Alert.tau); same truth as SCRIPT (see test_runner)
ALERTS = {
    ("p01", 0): [alert(ms(14) + 30_000, C1, key="a", tau=TemplateId.RANGE)],
    ("p03", 0): [alert(ms(8, 30), C1, key="e", tau=TemplateId.SCHED)],
    ("p05", 0): [
        alert(ms(14), UND, key="b", tau=TemplateId.RANGE),
        alert(ms(3), C1, key="c", tau=TemplateId.SCHED),
    ],
    ("p06", 0): [alert(ms(12), C1, key="d", tau=TemplateId.RANGE)],
}


# ---- the vocabulary ----------------------------------------------------------------------------------------------------


def test_the_templates_and_the_aggregate_set_are_declared() -> None:
    assert TEMPLATES == ("RANGE", "SCHED", "HOLD", "COUNT", "RESP", "SYS", "INT")
    assert AGGREGATE_TEMPLATES == (
        "RANGE",
        "SCHED",
        "HOLD",
        "COUNT",
        "SYS",
        "INT",
    )  # RESP is apart (ADR-072 (b))


def test_template_of_an_event_is_its_template_for_c1_and_sys_int_for_c2_c3() -> None:
    """C2 and C3 events carry no template (``template_id`` None); SYS and INT are CLASS PROXIES: a C2 event is counted under
    SYS and a C3 event under INT (not the violations of the SYS and INT templates)."""
    assert template_of_event(event("C1", "range", 0)) == "RANGE"
    assert template_of_event(event("C1", "resp", 0, 5)) == "RESP"
    assert template_of_event(event("C2", None, 0)) == "SYS"
    assert template_of_event(event("C3", None, 0)) == "INT"
    with pytest.raises(ValueError, match="template"):
        template_of_event(event("C1", "nonsense", 0))
    with pytest.raises(ValueError, match="template"):
        template_of_event(event("C1", None, 0))


# 1, I2: a plain detector
def test_metrics_are_available_per_template(tmp_path: Path) -> None:
    """The hand case of test_runner (SCRIPT: PLAIN detections on the mini benchmark, six test patients, 12 patient-days,
    tolerance 60 s, three scored false alarms: p05 03:00, p06 12:00, p06 T+12:00). Truth by template (a C2 event is counted
    as SYS, a C3 event as INT): RANGE 2 (p01, p05), SCHED 1 (p03), COUNT 1 (p03 day end), RESP 1 (p01 closing step), SYS 2
    (ble_dropout, stuck_at), INT 2 (replay, injection_naive), HOLD 0. True positives: RANGE 2, SCHED 1, COUNT 1, RESP 1,
    SYS 2, INT 0. A plain detection carries no template, so PRECISION and F1 per template are null; the figure
    ``precision_pooled_fa`` is TP / (TP + 3) with the three false alarms pooled over all templates: RANGE 2/5, SCHED 1/4,
    COUNT 1/4, RESP 1/4, SYS 2/5, INT 0 (no true positive). Delays: RANGE (30 000 + 0) / 2 = 15 000 ms, SCHED 0, COUNT
    -30 000, RESP 0, SYS 0, INT none."""
    m = read_metrics(run_doc(tmp_path, hand_document(), factory_for(SCRIPT))[0])
    block = m["per_template"]["ours-s1"]
    t = block["templates"]
    assert set(t) == {"RANGE", "SCHED", "HOLD", "COUNT", "SYS", "INT"}  # sorted keys
    assert block["templated"] is False
    expected = {
        "RANGE": (2, 2, 2 / 5, 1.0, 15_000.0),
        "SCHED": (1, 1, 1 / 4, 1.0, 0.0),
        "COUNT": (1, 1, 1 / 4, 1.0, -30_000.0),
        "SYS": (2, 2, 2 / 5, 1.0, 0.0),
        "INT": (2, 0, 0.0, 0.0, None),
    }
    for name, (n_gt, n_tp, pooled, recall, delay) in expected.items():
        e = t[name]
        assert (e["n_events"], e["n_matched"]) == (n_gt, n_tp), name
        assert e["precision"] is None and e["f1"] is None, name
        assert e["precision_pooled_fa"]["value"] == pytest.approx(pooled), name
        assert e["recall"]["value"] == pytest.approx(recall), name
        assert set(e["recall"]) == SCALAR
        if delay is None:
            assert (
                e["delay_ms"]["mean"]["value"] is None
            )  # nothing matched: no delay, not zero
        else:
            assert e["delay_ms"]["mean"]["value"] == pytest.approx(delay), name
        assert e["delay_ms"]["n_matched"] == n_tp
    # SYS and INT count the C2 and C3 events: class proxies, flagged; the other templates carry no flag
    assert t["SYS"]["class_proxy"] is True and t["INT"]["class_proxy"] is True
    assert "class_proxy" not in t["RANGE"] and "class_proxy" not in block["resp"]
    # HOLD has no truth event: null leaves (and an event count of zero), not zero and not NaN
    hold = t["HOLD"]
    assert hold == {
        "n_events": 0,
        "n_matched": 0,
        "precision": None,
        "precision_pooled_fa": None,
        "recall": None,
        "f1": None,
        "delay_ms": None,
    }
    resp = block["resp"]  # reported apart, with the same fields
    assert (resp["n_events"], resp["n_matched"]) == (1, 1)
    assert resp["precision_pooled_fa"]["value"] == pytest.approx(1 / 4)
    assert resp["recall"]["value"] == 1.0
    assert resp["delay_ms"]["mean"]["value"] == 0.0
    assert "NaN" not in json.dumps(m)


# I2: a detector whose detections carry a template
def test_templated_detector_gets_precision_and_f1_per_template(tmp_path: Path) -> None:
    """Alerts (``Alert.tau``) on the same truth. Alerts: p01 14:00:30 RANGE (true positive), p05 14:00 RANGE (true
    positive) and 03:00 SCHED (false alarm), p03 08:30 SCHED (true positive), p06 12:00 RANGE (false alarm). Background false
    alarms by template: RANGE 1, SCHED 1. Truth: RANGE 2, SCHED 1, COUNT 1, RESP 1, SYS 2, INT 2.
    Precision TP / (TP + FA_t): RANGE 2/3, SCHED 1/2, COUNT 0, RESP 0, SYS 0, INT 0 (a template with events and no true
    positive has precision 0, not a missing value). Recall: 1, 1, 0, 0, 0, 0. F1: RANGE 2 (2/3) / (5/3) = 4/5, SCHED
    2 (1/2) / (3/2) = 2/3, the others 0. Pooled-FA precision: RANGE 2/4, SCHED 1/3.
    Aggregate over the five templates WITH events (RANGE, SCHED, COUNT, SYS, INT; HOLD has none, RESP is apart):
    precision (2/3 + 1/2) / 5 = 7/30, recall 2/5, F1 (4/5 + 2/3) / 5 = 22/75; delay over the two templates with a match
    (15 000 + 0) / 2 = 7500."""
    m = read_metrics(run_doc(tmp_path, hand_document(), factory_for(ALERTS))[0])
    block = m["per_template"]["ours-s1"]
    assert block["templated"] is True
    t = block["templates"]
    for name, precision, recall, f1, pooled in (
        ("RANGE", 2 / 3, 1.0, 4 / 5, 1 / 2),
        ("SCHED", 1 / 2, 1.0, 2 / 3, 1 / 3),
        ("COUNT", 0.0, 0.0, 0.0, 0.0),
        ("SYS", 0.0, 0.0, 0.0, 0.0),
        ("INT", 0.0, 0.0, 0.0, 0.0),
    ):
        e = t[name]
        assert e["precision"]["value"] == pytest.approx(precision), name
        assert e["recall"]["value"] == pytest.approx(recall), name
        assert e["f1"]["value"] == pytest.approx(f1), name
        assert e["precision_pooled_fa"]["value"] == pytest.approx(pooled), name
        assert set(e["precision"]) >= SCALAR
    assert (
        block["resp"]["precision"]["value"] == 0.0
        and block["resp"]["f1"]["value"] == 0.0
    )
    assert t["HOLD"]["precision"] is None  # no truth event
    agg = block["aggregate"]
    assert agg["precision"]["value"] == pytest.approx(7 / 30)
    assert agg["recall"]["value"] == pytest.approx(2 / 5)
    assert agg["f1"]["value"] == pytest.approx(22 / 75)
    assert agg["delay_ms_mean"]["value"] == pytest.approx(7500.0)
    every = ["RANGE", "SCHED", "COUNT", "SYS", "INT"]
    for key in ("precision", "recall", "f1"):
        assert agg[key]["templates_averaged"] == every, key
    assert agg["delay_ms_mean"]["templates_averaged"] == ["RANGE", "SCHED"]
    assert "pooled" not in json.dumps(
        agg
    )  # the pooled-FA precision does not enter the aggregate


def test_a_plain_detector_has_no_aggregate_precision_or_f1_but_has_recall_and_delay(
    tmp_path: Path,
) -> None:
    """From the plain hand case: present templates RANGE, SCHED, COUNT, SYS, INT (HOLD absent, RESP apart). Recall
    (1 + 1 + 1 + 1 + 0) / 5 = 0.8; delay (15 000 + 0 - 30 000 + 0) / 4 over the four templates with a match = -3750."""
    m = read_metrics(run_doc(tmp_path, hand_document(), factory_for(SCRIPT))[0])
    agg = m["per_template"]["ours-s1"]["aggregate"]
    assert agg["templates"] == ["RANGE", "SCHED", "HOLD", "COUNT", "SYS", "INT"]
    assert agg["templates_with_events"] == ["RANGE", "SCHED", "COUNT", "SYS", "INT"]
    assert agg["weights"] == "equal"
    assert agg["precision"] is None and agg["f1"] is None
    assert agg["recall"]["value"] == pytest.approx(0.8)
    assert agg["recall"]["templates_averaged"] == [
        "RANGE",
        "SCHED",
        "COUNT",
        "SYS",
        "INT",
    ]
    assert agg["delay_ms_mean"]["value"] == pytest.approx(-3750.0)
    assert agg["delay_ms_mean"]["templates_averaged"] == [
        "RANGE",
        "SCHED",
        "COUNT",
        "SYS",
    ]
    assert set(agg["recall"]) >= SCALAR


def test_a_template_with_no_truth_event_is_null_not_zero() -> None:
    total = row(RANGE_gt=3, RANGE_tp=1, RANGE_fa=2, fa_background=2, exposure_days=4)
    assert table_template_metric(total, "RANGE", "recall") == pytest.approx(1 / 3)
    assert table_template_metric(
        total, "RANGE", "precision", templated=True
    ) == pytest.approx(1 / 3)
    for key in (
        "precision",
        "recall",
        "f1",
        "precision_pooled_fa",
        "delay_mean",
        "fraction_early",
    ):
        assert math.isnan(table_template_metric(total, "HOLD", key, templated=True)), (
            key
        )
    # a template that has events but no match: recall, precision and F1 are 0, the delay is undefined
    missed = row(SCHED_gt=2, SCHED_fa=1, fa_background=1)
    for key in ("recall", "precision", "f1", "precision_pooled_fa"):
        assert table_template_metric(missed, "SCHED", key, templated=True) == 0.0, key
    assert math.isnan(table_template_metric(missed, "SCHED", "delay_mean"))
    # and with no detection at all: still 0 (the rule of the aggregate), not a missing value
    silent = row(SCHED_gt=2)
    assert table_template_metric(silent, "SCHED", "precision", templated=True) == 0.0
    assert table_template_metric(silent, "SCHED", "f1", templated=True) == 0.0


def test_precision_and_f1_do_not_exist_for_a_plain_detector() -> None:
    total = row(RANGE_gt=2, RANGE_tp=1, fa_background=1, exposure_days=1)
    assert math.isnan(table_template_metric(total, "RANGE", "precision"))
    assert math.isnan(table_template_metric(total, "RANGE", "f1"))
    assert table_template_metric(total, "RANGE", "precision_pooled_fa") == 0.5
    assert math.isnan(table_aggregate_metric(total, "precision"))
    assert math.isnan(table_aggregate_metric(total, "f1"))
    assert table_aggregate_metric(total, "recall") == 0.5
    assert aggregate_templates(total, "precision") == ()
    assert aggregate_templates(total, "recall") == ("RANGE",)


def test_alert_false_alarms_are_attributed_to_the_template_of_the_alert() -> None:
    """A false alarm of an alert with ``tau`` SCHED is a SCHED false alarm; a plain detection has no template and only
    counts in the pooled total. Both are background false alarms (no footprint)."""
    dets = [
        alert(9 * H, C1, key="x", tau=TemplateId.SCHED),
        alert(12 * H, C1, key="y", tau=TemplateId.SYS),
        det(15 * H),
    ]
    matching = match_events([], dets, CFG, n_days=1)
    table = template_table(
        matching, [], [0, 0, 0], 1, PatientBackground((), 1, margin_ms=0)
    )
    cols = {
        name: float(table[:, TEMPLATE_COLUMNS.index(name)].sum())
        for name in TEMPLATE_COLUMNS
    }
    assert cols["SCHED_fa"] == 1 and cols["SYS_fa"] == 1 and cols["RANGE_fa"] == 0
    assert cols["fa_background"] == 3


def test_per_template_counts_of_a_matching_by_hand() -> None:
    """One patient, one day: a RANGE event at 10:00 matched 20 s late, a RANGE event at 12:00 missed, a C2 event at 15:00
    matched 40 s early, a C3 event at 18:00 missed; one false alarm at 03:00 (no injection anywhere)."""
    gt = [
        event("C1", "range", 10 * H, injected=False),
        event("C1", "range", 12 * H, injected=False),
        event("C2", None, 15 * H),
        event("C3", None, 18 * H),
    ]
    dets = [det(10 * H + 20_000), det(15 * H - 40_000), det(3 * H)]
    matching = match_events(gt, dets, CFG, n_days=1)
    table = template_table(
        matching, [0, 0, 0, 0], [0, 0, 0], 1, PatientBackground((), 1, margin_ms=0)
    )
    total = table.sum(axis=0)
    assert total[TEMPLATE_COLUMNS.index("RANGE_gt")] == 2
    assert total[TEMPLATE_COLUMNS.index("RANGE_tp")] == 1
    assert total[TEMPLATE_COLUMNS.index("SYS_tp")] == 1
    assert total[TEMPLATE_COLUMNS.index("INT_tp")] == 0
    assert table_template_metric(total, "RANGE", "delay_mean") == 20_000.0
    assert table_template_metric(total, "SYS", "delay_mean") == -40_000.0
    assert table_template_metric(total, "SYS", "fraction_early") == 1.0
    assert table_template_metric(total, "RANGE", "fraction_early") == 0.0
    assert (
        table_template_metric(total, "RANGE", "precision_pooled_fa") == 0.5
    )  # 1 / (1 + 1)


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
    with_resp = table_aggregate_metric(
        total, "recall", templates=(*AGGREGATE_TEMPLATES, "RESP")
    )
    assert with_resp == pytest.approx(17 / 36)
    assert without - with_resp == pytest.approx(17 / 180)
    pooled = (2 + 2 + 0 + 1 + 5) / (4 + 2 + 1 + 3 + 5)
    assert pooled == pytest.approx(2 / 3) and without != pytest.approx(pooled)
    assert aggregate_templates(total, "recall") == (
        "RANGE",
        "SCHED",
        "HOLD",
        "COUNT",
        "SYS",
    )


def test_aggregate_f1_is_the_mean_of_the_template_f1_and_delay_the_mean_of_the_template_delays() -> (
    None
):
    # RANGE: gt 2, tp 1, FA 1 -> p = 1/2, r = 1/2, f1 = 1/2.  SYS: gt 1, tp 1, FA 1 -> p = 1/2, r = 1, f1 = 2/3.
    total = row(
        RANGE_gt=2, RANGE_tp=1, RANGE_fa=1, RANGE_delay_n=1, RANGE_delay_sum_ms=1000,
        SYS_gt=1, SYS_tp=1, SYS_fa=1, SYS_delay_n=1, SYS_delay_sum_ms=-3000, fa_background=2, exposure_days=1,
    )  # fmt: skip
    assert table_aggregate_metric(total, "f1", templated=True) == pytest.approx(
        (1 / 2 + 2 / 3) / 2
    )
    assert table_aggregate_metric(total, "delay_mean") == pytest.approx(
        (1000 - 3000) / 2
    )  # equal weights, not pooled


# I1: the reviewer's scenario
def test_aggregate_f1_averages_every_template_with_events_and_one_false_alarm_does_not_swing_it() -> (
    None
):
    """RANGE 5 of 10 matched, SCHED, HOLD, COUNT, SYS and INT have 2 events each and none matched, no false alarm. RANGE:
    precision 1, recall 1/2, F1 2/3; the five others F1 0 (events but no true positive). The aggregate F1 is
    (2/3) / 6 = 1/9, NOT the 2/3 of RANGE alone. One background false alarm of RANGE: precision 5/6, F1 = 2 (5/6)(1/2) /
    (5/6 + 1/2) = 5/8, aggregate 5/48 = 0.1041...: the aggregate moves by a factor 0.9375, not sixfold. A false alarm of
    SCHED leaves the aggregate F1 unchanged (SCHED has no true positive: F1 0 with or without it)."""
    base = {
        "RANGE_gt": 10,
        "RANGE_tp": 5,
        "SCHED_gt": 2,
        "HOLD_gt": 2,
        "COUNT_gt": 2,
        "SYS_gt": 2,
        "INT_gt": 2,
    }
    every = ("RANGE", "SCHED", "HOLD", "COUNT", "SYS", "INT")
    clean = row(**base, exposure_days=5)
    f1 = table_aggregate_metric(clean, "f1", templated=True)
    assert f1 == pytest.approx(1 / 9) and f1 != pytest.approx(2 / 3)
    assert aggregate_templates(clean, "f1", templated=True) == every
    assert aggregate_templates(clean, "precision", templated=True) == every
    assert aggregate_templates(clean, "recall") == every
    one_fa = row(**base, RANGE_fa=1, fa_background=1, exposure_days=5)
    moved = table_aggregate_metric(one_fa, "f1", templated=True)
    assert moved == pytest.approx(5 / 48)
    assert 0.9 < moved / f1 < 1.0
    other = row(**base, SCHED_fa=1, fa_background=1, exposure_days=5)
    assert table_aggregate_metric(other, "f1", templated=True) == pytest.approx(1 / 9)
    # the precision average also keeps all six templates: (1 + 0 * 5) / 6, and with the false alarm (5/6) / 6
    assert table_aggregate_metric(clean, "precision", templated=True) == pytest.approx(
        1 / 6
    )
    assert table_aggregate_metric(one_fa, "precision", templated=True) == pytest.approx(
        5 / 36
    )


def test_aggregate_is_undefined_when_no_template_has_an_event_and_resp_alone_does_not_make_one() -> (
    None
):
    assert math.isnan(table_aggregate_metric(row(), "recall"))
    only_resp = row(RESP_gt=3, RESP_tp=3, fa_background=1, exposure_days=1)
    assert math.isnan(
        table_aggregate_metric(only_resp, "recall")
    )  # RESP is not in the aggregate
    assert table_template_metric(only_resp, "RESP", "recall") == 1.0


# 6, I4
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
    # the class proxies and the single rule of the aggregate are stated
    assert meta["class_proxies"] == {"SYS": "C2 events", "INT": "C3 events"}
    assert "not the violations of the SYS and INT templates" in meta["class_proxy_note"]
    assert "templates_averaged" in meta["average_rule"]
    assert "0" in meta["precision_rule"] and "Alert.tau" in meta["precision_rule"]
    assert "precision_pooled_fa" in meta["precision_pooled_fa"]


def test_every_detector_gets_a_per_template_entry_even_a_scripted_one_with_no_detection(
    tmp_path: Path,
) -> None:
    m = read_metrics(run_doc(tmp_path, hand_document(), factory_for({}))[0])
    t = m["per_template"]["ours-s1"]["templates"]
    assert t["RANGE"]["recall"]["value"] == 0.0
    assert (
        t["RANGE"]["precision_pooled_fa"]["value"] == 0.0
    )  # events but no true positive: 0
    assert t["RANGE"]["precision"] is None  # no detection carries a template
    assert t["RANGE"]["delay_ms"]["mean"]["value"] is None
    assert "NaN" not in json.dumps(m)


# ---- the excess over the background -------------------------------------------------------------------------------------


def test_excess_table_by_hand() -> None:
    """One patient, two days. A spike record covers 13:00-15:00 of day 0 (2 H) and 13:00-15:00 of day 1 (2 H): two records.
    RANGE events: day 0 at 14:00 (in the window, detected), day 1 at 14:00 (in the window, missed), day 0 at 20:00 (outside,
    detected), day 1 at 08:00 (outside, missed), day 1 at 21:00 (outside, missed); one COUNT event at 14:00 of day 0 (another
    template: ignored).  In the windows: 2 events, 1 detected, 4 H = 1/6 day.  Outside every footprint: 3 events, 1 detected,
    48 H - 4 H = 44 H = 11/6 day."""
    bg = PatientBackground(
        (
            Footprint("hypertensive_spike", "C1", 13 * H, 15 * H),
            Footprint("hypertensive_spike", "C1", D + 13 * H, D + 15 * H),
        ),
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
    matching = match_events(gt, [det(14 * H), det(20 * H)], CFG, n_days=2)
    days = [0, 1, 0, 1, 1, 0]
    table = excess_table(matching, days, 2, bg, "C1/hypertensive_spike", "RANGE")
    total = table.sum(axis=0)
    assert excess_counts(total) == pytest.approx(
        {
            "records": 2,
            "events_in": 2,
            "detected_in": 1,
            "exposure_in_days": 1 / 6,
            "events_bg": 3,
            "detected_bg": 1,
            "exposure_bg_days": 11 / 6,
        }
    )
    # COUNT PER RECORD: the background rate is 3 / (11/6) = 18/11 per day, so 18/11 * 1/6 = 3/11 events are expected in
    # the footprints; the excess is (2 - 3/11) / 2 = 19/22 events per record.  Detected: rate 6/11, expected 1/11,
    # (1 - 1/11) / 2 = 5/11 per record.
    assert table_excess_events_per_record(total) == pytest.approx(19 / 22)
    assert table_excess_detected_per_record(total) == pytest.approx(5 / 11)
    assert table_excess_recall(total) == pytest.approx(1 / 2 - 1 / 3)
    # the secondary figures per patient-day: 2 / (1/6) - 18/11 = 12 - 18/11 and 6 - 6/11
    assert table_excess_events(total) == pytest.approx(12 - 18 / 11)
    assert table_excess_detected(total) == pytest.approx(6 - 6 / 11)


def test_the_excess_per_record_hardly_moves_with_the_footprint_length_the_rate_per_day_does() -> (
    None
):
    """Four records, 8 events in the footprints, background 9 events in 9 days (1 per day). With 0.4 day of footprint the
    excess per record is (8 - 1 * 0.4) / 4 = 1.9 and per patient-day 8 / 0.4 - 1 = 19; with the footprint twice as long
    (a longer tail, the same events) 1.8 and 8 / 0.8 - 1 = 9: the rate per day halves, the count per record moves by 5%."""

    def total(exposure_in: float) -> np.ndarray:
        out = np.zeros(len(EXCESS_COLUMNS))
        for name, value in {
            "records": 4,
            "events_in": 8,
            "exposure_in_days": exposure_in,
            "events_bg": 9,
            "exposure_bg_days": 9,
        }.items():
            out[EXCESS_COLUMNS.index(name)] = value
        return out

    assert table_excess_events_per_record(total(0.4)) == pytest.approx(1.9)
    assert table_excess_events_per_record(total(0.8)) == pytest.approx(1.8)
    assert table_excess_events(total(0.4)) == pytest.approx(19.0)
    assert table_excess_events(total(0.8)) == pytest.approx(9.0)


# M1
def test_an_event_at_the_end_of_the_scored_axis_is_in_no_excess_count() -> None:
    """The exposure covers [0, n_days * D); an event whose onset is exactly n_days * D (the day-end COUNT of the last day, a
    closing-step event) is outside the axis and is counted neither inside the footprints nor in the background."""
    bg = PatientBackground(
        (Footprint("double_take", "C1", 20 * H, 2 * D),), 2, margin_ms=0
    )
    gt = [
        event(
            "C1", "count", 2 * D, 2 * D, injected=True
        ),  # onset on the axis end; the footprint reaches it
        event("C1", "count", 10 * H, injected=False),  # a real background event
    ]
    matching = match_events(gt, [], CFG, n_days=2)
    total = excess_table(matching, [1, 0], 2, bg, "C1/double_take", "COUNT").sum(axis=0)
    counts = excess_counts(total)
    assert counts["events_in"] == 0 and counts["events_bg"] == 1
    outside = PatientBackground((), 2, margin_ms=0)
    total = excess_table(matching, [1, 0], 2, outside, "C1/double_take", "COUNT").sum(
        axis=0
    )
    assert excess_counts(total)["events_bg"] == 1  # not 2


# 5
def test_excess_over_background() -> None:
    """Eight patients of one day each; every patient has 0.1 day of footprint (one record) and 0.9 day outside (test values).
    Injected subtype: each patient has 1 event in the footprint and 0 or 1 outside (4 of 8): background rate 4 / 7.2,
    expected events in the footprints 4 / 7.2 * 0.8 = 4/9, excess per record (8 - 4/9) / 8 = 17/18; the cluster interval over
    patients does not contain 0.  No-excess subtype: 4 events in the footprints (expected 36 / 7.2 * 0.8 = 4) and 36 outside:
    excess exactly 0 with patient-to-patient variation, so the interval contains 0."""
    n = 8
    patients = [f"p{i}" for i in range(n)]

    def table(events_in: list[float], events_bg: list[float]) -> np.ndarray:
        out = np.zeros((n, len(EXCESS_COLUMNS)))
        out[:, EXCESS_COLUMNS.index("records")] = 1
        out[:, EXCESS_COLUMNS.index("events_in")] = events_in
        out[:, EXCESS_COLUMNS.index("exposure_in_days")] = 0.1
        out[:, EXCESS_COLUMNS.index("events_bg")] = events_bg
        out[:, EXCESS_COLUMNS.index("exposure_bg_days")] = 0.9
        return out

    injected = table([1] * 8, [0, 1] * 4)
    total = injected.sum(axis=0)
    assert table_excess_events_per_record(total) == pytest.approx(17 / 18)
    lo, hi = bootstrap_statistic(
        injected,
        table_excess_events_per_record,
        n_resamples=200,
        level=0.95,
        seed=3,
        clusters=patients,
    )
    assert 0 < lo <= 17 / 18 <= hi

    none = table([0, 1, 0, 1, 0, 1, 0, 1], [4, 5, 4, 5, 4, 5, 4, 5])
    assert table_excess_events_per_record(none.sum(axis=0)) == pytest.approx(
        0.0, abs=1e-12
    )
    lo, hi = bootstrap_statistic(
        none,
        table_excess_events_per_record,
        n_resamples=200,
        level=0.95,
        seed=3,
        clusters=patients,
    )
    assert lo < 0 < hi


def test_excess_is_undefined_without_exposure_or_without_events_or_without_records() -> (
    None
):
    total = np.zeros(len(EXCESS_COLUMNS))
    for stat in (
        table_excess_events,
        table_excess_detected,
        table_excess_recall,
        table_excess_events_per_record,
        table_excess_detected_per_record,
    ):
        assert math.isnan(stat(total)), stat.__name__
    no_window = np.zeros(len(EXCESS_COLUMNS))
    no_window[EXCESS_COLUMNS.index("events_bg")] = 2
    no_window[EXCESS_COLUMNS.index("exposure_bg_days")] = 1
    assert math.isnan(table_excess_events(no_window))
    assert math.isnan(table_excess_events_per_record(no_window))  # no record


def spike_bench(tmp_path: Path, record: dict[str, object]) -> Path:
    bench = tmp_path / "bench"
    shutil.copytree(MINI, bench)
    path = bench / "truth" / "p05" / "0.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["injection_log"] = [record]
    path.write_text(json.dumps(doc), encoding="utf-8")
    return bench


def test_the_runner_reports_the_excess_of_an_injected_c1_subtype(
    tmp_path: Path,
) -> None:
    """The mini benchmark with a spike record covering 13:00-15:00 of p05 day 0 (the RANGE event at 14:00 of that patient
    is in the footprint; the RANGE event of p01 at 14:00 is outside every footprint). Both are detected by SCRIPT.
    Footprint: 1 record, 1 event, 1 detected, 2 H = 1/12 day; outside: 1 event, 1 detected, 12 - 1/12 = 143/12 days.
    Background rate 12/143 per day, expected in the footprint 1/143: the excess per record is 1 - 1/143 = 142/143 for the
    events and for the detected events; per patient-day 12 - 12/143 (secondary); recall 1 - 1 = 0."""
    bench = spike_bench(
        tmp_path, entry("C1", "hypertensive_spike", ms(13), ms(15), truth_indices=(0,))
    )
    m = read_metrics(
        run_doc(tmp_path, background_document(bench), factory_for(SCRIPT))[0]
    )
    block = m["background"]["excess_over_background"]["ours-s1"]["hypertensive_spike"]
    assert block["template"] == "RANGE"
    assert block["events_per_record"]["value"] == pytest.approx(142 / 143)
    assert block["detected_per_record"]["value"] == pytest.approx(142 / 143)
    assert block["recall"]["value"] == pytest.approx(0.0)
    assert block["events_per_patient_day"]["value"] == pytest.approx(12 - 12 / 143)
    assert block["detected_per_patient_day"]["value"] == pytest.approx(12 - 12 / 143)
    assert set(block["events_per_record"]) >= SCALAR
    counts = block["counts"]
    assert counts["n_injection_records"] == 1
    assert counts["events_in_windows"] == 1 and counts["events_background"] == 1
    assert counts["exposure_in_windows_days"] == pytest.approx(1 / 12)
    assert counts["exposure_background_days"] == pytest.approx(143 / 12)
    assert "secondary" in block["note"] and "footprint" in block["note"]
    meta = m["meta"]["background"]
    assert "ci_cluster" in meta["excess_interval_note"]
    assert "time-of-day" in meta["excess_counterfactual_note"]
    assert "NaN" not in json.dumps(m)


# M2
def test_the_template_of_an_excess_subtype_comes_from_the_builder_vocabulary_not_from_the_truth_present(
    tmp_path: Path,
) -> None:
    """The mini truth has no ``drug_nonresponse`` event among the test patients, yet the record of that subtype gets the
    template RESP from the link table of the labeller; a subtype that the vocabulary does not know gets ``null``."""
    bench = spike_bench(
        tmp_path, entry("C1", "drug_nonresponse", ms(13), ms(15), truth_indices=())
    )
    m = read_metrics(
        run_doc(tmp_path, background_document(bench), factory_for(SCRIPT))[0]
    )
    block = m["background"]["excess_over_background"]["ours-s1"]["drug_nonresponse"]
    assert block["template"] == "RESP"
    assert block["counts"]["n_injection_records"] == 1
    other = tmp_path / "other"
    other.mkdir()
    bench = spike_bench(other, entry("C1", "mystery_subtype", ms(13), ms(15)))
    m = read_metrics(run_doc(other, background_document(bench), factory_for(SCRIPT))[0])
    block = m["background"]["excess_over_background"]["ours-s1"]["mystery_subtype"]
    assert block["template"] is None and block["events_per_record"] is None


def test_a_benchmark_without_injected_c1_records_has_an_empty_excess_block(
    tmp_path: Path,
) -> None:
    m = read_metrics(
        run_doc(tmp_path, background_document(None), factory_for(SCRIPT))[0]
    )
    assert m["background"]["excess_over_background"]["ours-s1"] == {}
