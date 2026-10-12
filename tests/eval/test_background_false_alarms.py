"""WS08-T08: footprints of the injections and the false alarms of the windows WITHOUT injections (ADR-071 (b)).

ILLUSTRATIVE, UNVERIFIED, FIXTURE-ONLY. Every instant, window, tail and margin below is an arithmetic TEST VALUE chosen so
that the expected numbers can be computed by hand; none is a clinical value and none is a proposal for the experiment
configuration (the footprint tail of the C1 injections is an ``awaiting_human_value`` of the real configuration).

Units used in the comments: H = one hour in ms, D = one day = 24 H.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from ralmon.benchmark import GroundTruthEvent, InjectedClass
from ralmon.eval.background import (
    DAY_MS,
    Footprint,
    PatientBackground,
    patient_footprints,
    record_footprint,
    subtype_key,
)
from ralmon.eval.metrics import (
    TEMPLATE_COLUMNS,
    MatchConfig,
    match_events,
    table_background_fa_per_day,
    template_table,
)
from ralmon.eval.runner import (
    ConfigError,
    GuardError,
    RunFacts,
    RunOptions,
    dump_experiment,
    evaluate_guards,
    load_experiment,
)
from tests.eval.helpers import MINI, det, ms, smoke_document, write_config
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


def entry(
    cls: str,
    subtype: str,
    onset: int,
    end: int | None,
    *,
    realised: bool = True,
    truth_indices: tuple[int, ...] = (),
    explains: tuple[tuple[int, int], ...] = (),
) -> dict[str, Any]:
    """A log entry with the keys of ``injection_log`` plus the ones the builder adds (builder.md, truth sidecars)."""
    return {
        "cls": cls,
        "subtype": subtype,
        "onset_ms": onset,
        "duration_ms": None if end is None else end - onset,
        "end_ms": end,
        "magnitude": 1.0,
        "magnitude_unit": "x",
        "params": {},
        "level": None,
        "confounder_group": None,
        "realised": realised,
        "n_changed": 1 if realised else 0,
        "evidence_paths": [],
        "details": {},
        "record_index": 0,
        "truth_indices": list(truth_indices),
        "explains_in_later_days": [
            {"day_index": d, "truth_index": i} for d, i in explains
        ],
    }


def natural(
    template: str, onset: int, end: int | None = None, subtype: str = "spontaneous_x"
) -> GroundTruthEvent:
    return GroundTruthEvent(
        InjectedClass.C1, subtype, onset, end, False, template, None
    )


def col(table: np.ndarray, name: str) -> float:
    return float(table[:, TEMPLATE_COLUMNS.index(name)].sum())


# ---- footprints ------------------------------------------------------------------------------------------------------


def test_the_footprint_of_a_c2_or_c3_record_is_its_window_whatever_the_tail() -> None:
    fp = record_footprint(
        entry("C2", "cuff_detached", 8 * H, 10 * H),
        day_index=0,
        truth_by_day={0: []},
        c1_tail_ms=5 * H,
    )
    assert fp == (Footprint("cuff_detached", "C2", 8 * H, 10 * H),)
    point = record_footprint(
        entry("C3", "dispense_forgery", 9 * H, None),
        day_index=0,
        truth_by_day={0: []},
        c1_tail_ms=5 * H,
    )
    assert point == (Footprint("dispense_forgery", "C3", 9 * H, 9 * H),)


def test_the_footprint_of_a_c1_record_is_the_window_plus_the_stated_tail() -> None:
    # window [10 H, 12 H) with a test tail of 3 H: [10 H, 15 H]; a point record: [onset, onset + tail]
    window = record_footprint(
        entry("C1", "hypertensive_spike", 10 * H, 12 * H),
        day_index=0,
        truth_by_day={0: []},
        c1_tail_ms=3 * H,
    )
    assert window == (Footprint("hypertensive_spike", "C1", 10 * H, 15 * H),)
    point = record_footprint(
        entry("C1", "double_take", 20 * H, None),
        day_index=0,
        truth_by_day={0: []},
        c1_tail_ms=3 * H,
    )
    assert point == (Footprint("double_take", "C1", 20 * H, 23 * H),)


def test_a_record_that_changed_nothing_has_no_footprint() -> None:
    assert (
        record_footprint(
            entry("C2", "cuff_detached", 8 * H, 10 * H, realised=False),
            day_index=0,
            truth_by_day={0: []},
            c1_tail_ms=0,
        )
        == ()
    )


def test_events_that_a_record_explains_in_a_later_day_are_part_of_its_footprint() -> (
    None
):
    """A double take at 20:00 of day 0 produces the day-end COUNT event of day 1 (builder.md, explains_in_later_days)."""
    later = natural("count", 2 * D, 2 * D, subtype="dose_excess")  # day 1, index 0
    same_day = natural("count", 20 * H + 60_000, subtype="x")  # day 0, index 0
    fps = patient_footprints(
        {
            0: [
                entry(
                    "C1",
                    "double_take",
                    20 * H,
                    None,
                    truth_indices=(0,),
                    explains=((1, 0),),
                )
            ]
        },
        {0: [same_day], 1: [later]},
        c1_tail_ms=0,
    )
    spans = sorted((f.start_ms, f.end_ms) for f in fps)
    assert spans == [
        (20 * H, 20 * H),
        (20 * H + 60_000, 20 * H + 60_000),
        (2 * D, 2 * D),
    ]
    assert {f.subtype for f in fps} == {"double_take"}
    # one record, two linked spans: only the window counts as an injection record
    assert [f.linked for f in sorted(fps, key=lambda f: f.start_ms)] == [
        False,
        True,
        True,
    ]
    bg = PatientBackground(fps, 2, margin_ms=0)
    assert bg.records("C1/double_take") == (1, 0)
    assert bg.records("C1/unknown") == (0, 0)


# 7
def test_footprint_uses_t_rx_for_a_replay() -> None:
    """The window of a replay is on the ARRIVAL axis (builder: 'half open on the arrival time of the messages'): the
    replayed messages keep an old ``t_device`` (the previous day) but a detection is made on the receive axis. A replay
    window of day 1 at 15:00-16:00 holds the detection of 15:30 of day 1 and not the detection of 15:30 of day 0, which
    is where the ``t_device`` of the copied message lies."""
    fp = record_footprint(
        entry("C3", "replay", D + 15 * H, D + 16 * H),
        day_index=1,
        truth_by_day={},
        c1_tail_ms=0,
    )
    assert fp == (Footprint("replay", "C3", D + 15 * H, D + 16 * H, axis="t_rx"),)
    assert fp[0].axis == "t_rx"
    bg = PatientBackground(fp, 2, margin_ms=0)
    assert not bg.outside(D + 15 * H + 30 * 60_000)  # the arrival of the replayed copy
    assert bg.outside(15 * H + 30 * 60_000)  # the t_device of the copy, a day earlier


def test_footprints_of_two_subtypes_overlap_into_one_covered_time_per_day() -> None:
    fps = (
        Footprint("a", "C2", 8 * H, 10 * H),
        Footprint("b", "C3", 9 * H, 11 * H),
        Footprint(
            "c", "C2", 23 * H, 25 * H
        ),  # crosses midnight: 1 H on day 0, 1 H on day 1
    )
    bg = PatientBackground(fps, 2, margin_ms=0)
    # day 0: [8, 11) = 3 H and [23, 24) = 1 H; day 1: [24, 25) = 1 H
    assert bg.exposure_ms() == (24 * H - 4 * H, 24 * H - 1 * H)
    assert bg.window_ms(subtype_key(fps[0])) == (2 * H, 0)
    assert bg.window_ms(subtype_key(fps[2])) == (1 * H, 1 * H)


def test_the_margin_widens_every_footprint_and_is_clipped_to_the_scored_axis() -> None:
    bg = PatientBackground(
        (Footprint("a", "C2", 8 * H, 10 * H),), 1, margin_ms=10 * 60_000
    )
    assert not bg.outside(8 * H - 5 * 60_000) and not bg.outside(10 * H + 5 * 60_000)
    assert bg.outside(8 * H - 11 * 60_000)
    assert bg.exposure_ms() == (24 * H - 2 * H - 20 * 60_000,)
    edge = PatientBackground(
        (Footprint("a", "C2", 0, 1 * H),), 1, margin_ms=30 * 60_000
    )
    assert edge.exposure_ms() == (
        24 * H - 90 * 60_000,
    )  # [-30 min, 1.5 H] clipped to [0, 1.5 H]


# ---- the false alarms of the windows without injections ----------------------------------------------------------------


def background_of_two_windows() -> PatientBackground:
    """Day 0 has two windows of known length: a C2 fault 08:00-10:00 (2 H) and a C3 replay 14:00-15:00 (1 H); day 1 none."""
    return PatientBackground(
        (
            Footprint("cuff_detached", "C2", 8 * H, 10 * H),
            Footprint("replay", "C3", 14 * H, 15 * H),
        ),
        2,
        margin_ms=0,
    )


# 3
def test_false_alarms_are_counted_outside_injection_windows() -> None:
    """No event, four detections of day 0: 09:00 and 14:30 lie inside the windows, 12:00 and 20:00 outside. The exposure is
    the patient-time outside the windows: (24 - 3) H on day 0 and 24 H on day 1 = 45 H = 1.875 patient-days."""
    detections = [det(9 * H), det(12 * H), det(14 * H + 30 * 60_000), det(20 * H)]
    matching = match_events([], detections, CFG, n_days=2)
    assert len(matching.false_alarm_index) == 4  # all four are unmatched detections
    table = template_table(matching, [], [0, 0, 0, 0], 2, background_of_two_windows())
    assert col(table, "fa_background") == 2
    assert col(table, "fa_in_footprint") == 2
    assert col(table, "exposure_days") == pytest.approx(45 / 24)
    assert table_background_fa_per_day(table.sum(axis=0)) == pytest.approx(
        2 / (45 / 24)
    )


def test_the_same_detection_inside_and_outside_a_window_is_classified_differently() -> (
    None
):
    inside = match_events([], [det(9 * H)], CFG, n_days=2)
    outside = match_events([], [det(12 * H)], CFG, n_days=2)
    bg = background_of_two_windows()
    assert col(template_table(inside, [], [0], 2, bg), "fa_background") == 0
    assert col(template_table(outside, [], [0], 2, bg), "fa_background") == 1


def test_a_detection_in_the_unscored_tail_is_in_no_unit_and_not_counted() -> None:
    matching = match_events([], [det(2 * D + H)], CFG, n_days=2)
    table = template_table(matching, [], [-1], 2, background_of_two_windows())
    assert col(table, "fa_background") == 0 and col(table, "fa_in_footprint") == 0


def test_without_a_background_every_false_alarm_is_background_and_the_exposure_is_the_whole_time() -> (
    None
):
    matching = match_events([], [det(9 * H)], CFG, n_days=2)
    table = template_table(matching, [], [0], 2, None)
    assert col(table, "fa_background") == 1 and col(table, "exposure_days") == 2


# 4
def test_natural_events_are_truth_and_noise_alarms_are_false_alarms() -> None:
    """A natural RANGE event (the latent pressure is out of band) at 14:00 is truth: the detection at 14:00 is a true
    positive. A noise alarm (the observed reading is out of band while the latent value is in band) has no event: the
    detection at 03:00 is a false alarm, and it counts in the background because no injection is near."""
    events = [natural("range", 14 * H, subtype="spontaneous_range")]
    matching = match_events(events, [det(14 * H), det(3 * H)], CFG, n_days=1)
    table = template_table(
        matching, [0], [0, 0], 1, PatientBackground((), 1, margin_ms=0)
    )
    assert col(table, "RANGE_gt") == 1 and col(table, "RANGE_tp") == 1
    assert col(table, "fa_background") == 1
    total = table.sum(axis=0)
    from ralmon.eval.metrics import table_template_metric

    assert table_template_metric(total, "RANGE", "recall") == 1.0
    assert (
        table_template_metric(total, "RANGE", "precision_pooled_fa") == 0.5
    )  # 1 / (1 + 1)


def test_a_detection_matched_to_an_injected_event_inside_its_window_is_a_true_positive_not_a_false_alarm() -> (
    None
):
    injected = GroundTruthEvent(
        InjectedClass.C2, "cuff_detached", 8 * H, 10 * H, True, None, None
    )
    matching = match_events([injected], [det(8 * H)], CFG, n_days=1)
    table = template_table(
        matching,
        [0],
        [0],
        1,
        PatientBackground(
            (Footprint("cuff_detached", "C2", 8 * H, 10 * H),), 1, margin_ms=0
        ),
    )
    assert col(table, "SYS_tp") == 1 and col(table, "fa_background") == 0
    assert col(table, "fa_in_footprint") == 0


# ---- the runner ------------------------------------------------------------------------------------------------------


def benchmark_with_a_window(tmp_path: Path) -> Path:
    """A copy of the mini benchmark whose patient p06 has a C2 record 11:00-13:00 on day 0 (the mini truth lists none)."""
    bench = tmp_path / "bench"
    shutil.copytree(MINI, bench)
    path = bench / "truth" / "p06" / "0.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["injection_log"] = [entry("C2", "cuff_detached", ms(11), ms(13))]
    path.write_text(json.dumps(doc), encoding="utf-8")
    return bench


def background_document(bench: Path | None, **background: Any) -> dict[str, Any]:
    doc = hand_document()
    if bench is not None:
        doc["benchmark_manifest"] = str(bench)
    doc["run_options"]["background"] = {
        "c1_footprint_tail_ms": 0,  # test value
        "c1_footprint_tail_reason": "test value, not a clinical value",
        "footprint_margin_ms": 0,  # test value
        **background,
    }
    return doc


def test_the_runner_counts_background_false_alarms_outside_the_injection_windows(
    tmp_path: Path,
) -> None:
    """SCRIPT has three scored false alarms: p05 03:00, p06 12:00 and p06 T+12:00 (the one in the tail day is dropped).
    The p06 record covers 11:00-13:00 of day 0, which holds the 12:00 alarm. Background: 2 alarms; in the footprint: 1;
    the exposure is 12 patient-days minus 2 H = 12 - 1/12 days; the old figure keeps all three."""
    bench = benchmark_with_a_window(tmp_path)
    m = read_metrics(
        run_doc(tmp_path, background_document(bench), factory_for(SCRIPT))[0]
    )
    bg = m["background"]["false_alarms_per_patient_day"]["ours-s1"]
    assert bg["n_false_alarms_background"] == 2
    assert bg["n_false_alarms_in_footprint"] == 1
    assert bg["exposure_patient_days"] == pytest.approx(12 - 1 / 12)
    assert bg["value"] == pytest.approx(2 / (12 - 1 / 12))
    assert set(bg) >= {"value", "ci_lo", "ci_hi", "ci_cluster_lo", "ci_cluster_hi"}
    assert (
        m["false_alarms_per_patient_day"]["ours-s1"]["n_false_alarms"] == 3
    )  # unchanged
    facts = m["analysis"]["run"]["background"]
    assert facts["n_injection_records"] == 1 and facts["n_footprints"] == 1


def test_a_benchmark_without_injection_records_has_the_whole_time_as_exposure(
    tmp_path: Path,
) -> None:
    m = read_metrics(
        run_doc(tmp_path, background_document(None), factory_for(SCRIPT))[0]
    )
    bg = m["background"]["false_alarms_per_patient_day"]["ours-s1"]
    assert (
        bg["n_false_alarms_background"] == 3 and bg["n_false_alarms_in_footprint"] == 0
    )
    assert bg["exposure_patient_days"] == 12 and bg["value"] == pytest.approx(3 / 12)


def test_the_background_block_of_the_options_is_parsed_dumped_and_reloaded(
    tmp_path: Path,
) -> None:
    config, options = load_experiment(
        write_config(
            tmp_path / "a.yaml", background_document(None, c1_footprint_tail_ms=7 * H)
        )
    )
    assert options.c1_footprint_tail_ms == 7 * H
    assert options.c1_footprint_tail_reason == "test value, not a clinical value"
    assert options.footprint_margin_ms == 0
    again = load_experiment(
        write_config(
            tmp_path / "b.yaml", yaml.safe_load(dump_experiment(config, options))
        )
    )
    assert again[1] == options


def test_an_awaiting_tail_is_a_value_that_is_not_there_yet(tmp_path: Path) -> None:
    doc = background_document(None, c1_footprint_tail_ms="awaiting_human_value")
    config, options = load_experiment(write_config(tmp_path / "a.yaml", doc))
    assert options.c1_footprint_tail_ms is None
    assert "awaiting_human_value" in dump_experiment(config, options)
    # a run option file with no background block at all is the same: the number is not invented
    plain = smoke_document()
    del plain["run_options"]["background"]
    assert (
        load_experiment(write_config(tmp_path / "c.yaml", plain))[
            1
        ].c1_footprint_tail_ms
        is None
    )


@pytest.mark.parametrize(
    "bad",
    [
        {"c1_footprint_tail_ms": -1},
        {"c1_footprint_tail_ms": 1.5},
        {"c1_footprint_tail_ms": "later"},
        {"footprint_margin_ms": -5},
        {"unknown": 1},
    ],
)
def test_a_bad_background_block_is_refused(tmp_path: Path, bad: dict[str, Any]) -> None:
    with pytest.raises(ConfigError):
        load_experiment(
            write_config(tmp_path / "a.yaml", background_document(None, **bad))
        )


def test_the_margin_defaults_to_the_matching_tolerance(tmp_path: Path) -> None:
    """Without ``footprint_margin_ms`` a detection within the matching tolerance (60 000 ms in the hand case) of a
    window belongs to the window: the 12:00 alarm of p06 against a record 12:00:30-13:00 is inside by 30 s."""
    bench = tmp_path / "bench"
    shutil.copytree(MINI, bench)
    path = bench / "truth" / "p06" / "0.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["injection_log"] = [entry("C2", "cuff_detached", ms(12) + 30_000, ms(13))]
    path.write_text(json.dumps(doc), encoding="utf-8")
    config = background_document(bench)
    del config["run_options"]["background"]["footprint_margin_ms"]
    m = read_metrics(run_doc(tmp_path, config, factory_for(SCRIPT))[0])
    assert (
        m["background"]["false_alarms_per_patient_day"]["ours-s1"][
            "n_false_alarms_in_footprint"
        ]
        == 1
    )
    assert m["meta"]["background"]["footprint_margin_ms"] == 60_000


def test_a_missing_tail_is_a_flag_and_a_hard_failure_of_a_headline_run() -> None:
    base: dict[str, Any] = {
        "detectors": ("ours",),
        "benchmark_fixture_only": False,
        "registry_fixture_only": False,
        "step_ms": 60_000,
        "reorder_delay_ms": 0,
        "has_device_profile": True,
        "n_seeds": 5,
        "background_tail_awaiting": True,
    }
    cfg: dict[str, Any] = {
        "alpha_grid": (0.05,),
        "n_bootstrap": 10,
        "ci_level": 0.95,
        "ece_bins": 5,
    }
    soft = evaluate_guards(RunFacts(**base), RunOptions(**cfg, headline=False))
    assert "C1_FOOTPRINT_TAIL_AWAITING" in {g.id for g in soft.flags}
    hard = evaluate_guards(RunFacts(**base), RunOptions(**cfg, headline=True))
    assert "C1_FOOTPRINT_TAIL_AWAITING" in {g.id for g in hard.hard}
    with pytest.raises(GuardError, match="C1_FOOTPRINT_TAIL_AWAITING"):
        hard.raise_if_failed()
    fine = evaluate_guards(
        RunFacts(**{**base, "background_tail_awaiting": False}),
        RunOptions(**cfg, headline=True),
    )
    assert "C1_FOOTPRINT_TAIL_AWAITING" not in {g.id for g in fine.hard + fine.flags}


def test_the_runner_without_a_tail_flags_it_and_computes_with_the_window_only(
    tmp_path: Path,
) -> None:
    doc = background_document(None, c1_footprint_tail_ms="awaiting_human_value")
    m = read_metrics(run_doc(tmp_path, doc, factory_for(SCRIPT))[0])
    assert "C1_FOOTPRINT_TAIL_AWAITING" in {
        g["id"] for g in m["meta"]["guards"]["flags"]
    }
    meta = m["meta"]["background"]
    assert meta["c1_footprint_tail_ms"] is None
    assert meta["c1_footprint_tail_status"] == "awaiting_human_value"
    assert "window only" in meta["c1_footprint_tail_note"]
