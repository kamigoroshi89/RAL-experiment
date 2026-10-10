"""Metrics of WS08-T01 (tests 1 to 26 of the task list, plus the table and bootstrap checks of the runner).

ILLUSTRATIVE, UNVERIFIED, FIXTURE-ONLY. Every expected value is computed by hand in the comment next to it, never by
the function under test.

Fixture M1 (one patient-day, tolerance 1_000 ms, reference "onset"): ground truth g1 = C1 at 10_000, g2 = C2 at
50_000, g3 = C3 at 90_000; detections d1 t=10_400 C1, d3 t=10_700 C1, d2 t=50_900 C3, d4 t=200_000 C1. By hand:
g1 matches d1 (the earliest in its window), d3 is a duplicate (in the window of a matched event), g2 matches d2
(900 <= 1_000), g3 is missed, d4 is the one false alarm.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from ralmon.conformal import PredictedViolation
from ralmon.eval import (
    MatchConfig,
    Matching,
    accuracy_vs_coverage,
    attribution_confusion,
    detection_delay_ms,
    empirical_coverage,
    expected_calibration_error,
    false_alarms_per_patient_day,
    latency_percentiles,
    match_events,
    mean_interval_width,
    per_class_prf,
    recall_vs_false_alarm_curve,
    severity_rank_agreement,
)
from ralmon.eval.metrics import (
    abstention_rate,
    attribution_macro_f1,
    bootstrap_ci,
    bootstrap_statistic,
    first_decidable_ms,
    paired_bootstrap_ci,
    reliability_bins,
    residual_coverage,
)
from ralmon.monitor import VerdictState
from ralmon.spec import Rho, RhoKind
from tests.eval.helpers import C1, C2, C3, UND, alert, benchmark_day, det, gt

CFG = MatchConfig(tolerance_ms=1_000, time_reference="onset")
CFG_FD = MatchConfig(tolerance_ms=1_000, time_reference="first_decidable")


def m1() -> Matching:
    events = [gt("C1", 10_000), gt("C2", 50_000), gt("C3", 90_000)]
    dets = [
        det(10_400, C1),
        det(10_700, C1),
        det(50_900, C3),
        det(200_000, C1),
    ]
    return match_events(events, dets, CFG)


def predicted(emitted: bool, alpha: float = 0.2) -> PredictedViolation:
    rho = (
        Rho(
            0.8,
            RhoKind.PREDICTED,
            "marginal over patient episodes under exchangeability",
            alpha,
            (),
        )
        if emitted
        else None
    )
    return PredictedViolation(emitted, rho, "likely")


# 1
def test_match_events_fixture_m1() -> None:
    m = m1()
    assert len(m.pairs) == 2
    assert [(p.gt.cls.value, p.det.t_ms) for p in m.pairs] == [
        ("C1", 10_400),
        ("C2", 50_900),
    ]
    assert [e.cls.value for e in m.missed] == ["C3"]
    assert [d.t_ms for d in m.duplicates] == [10_700]
    assert [d.t_ms for d in m.false_alarms] == [200_000]
    assert m.n_days == 1


# 2
def test_per_class_prf_fixture_m1() -> None:
    prf = per_class_prf(m1())
    # precision_c = TP_c / (TP_c + FA), FA = 1 (label-agnostic); recall_c = TP_c / GT_c
    assert prf["C1"]["precision"] == pytest.approx(0.5)
    assert prf["C1"]["recall"] == pytest.approx(1.0)
    assert prf["C1"]["f1"] == pytest.approx(2 / 3)
    assert prf["C2"]["precision"] == pytest.approx(0.5)
    assert prf["C2"]["recall"] == pytest.approx(1.0)
    assert prf["C2"]["f1"] == pytest.approx(2 / 3)
    assert prf["C3"] == {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    # any: TP = 2, FA = 1, GT = 3
    assert prf["any"]["precision"] == pytest.approx(2 / 3)
    assert prf["any"]["recall"] == pytest.approx(2 / 3)
    assert prf["any"]["f1"] == pytest.approx(2 / 3)


# 3
def test_per_class_prf_undefined_is_nan_not_zero() -> None:
    m = match_events([gt("C1", 10_000)], [det(10_000, C1)], CFG)
    prf = per_class_prf(m)
    assert math.isnan(prf["C2"]["recall"])  # no C2 event: GT_c = 0
    assert math.isnan(prf["C2"]["precision"])  # TP_c + FA = 0 + 0
    assert math.isnan(prf["C2"]["f1"])
    assert prf["C1"] == {"precision": 1.0, "recall": 1.0, "f1": 1.0}


def test_per_class_prf_precision_nan_when_nothing_was_detected() -> None:
    m = match_events([gt("C1", 10_000)], [], CFG)
    prf = per_class_prf(m)
    assert math.isnan(prf["C1"]["precision"])  # TP_c + FA = 0
    assert prf["C1"]["recall"] == 0.0  # GT_c = 1, TP_c = 0
    assert math.isnan(prf["C1"]["f1"])  # undefined precision: undefined F1
    assert math.isnan(prf["C2"]["recall"])


# 4
def test_false_alarms_per_patient_day() -> None:
    two_days = Matching.concat([m1(), match_events([], [], CFG)])
    assert two_days.n_days == 2
    assert false_alarms_per_patient_day(two_days, 2) == pytest.approx(0.5)  # 1 / 2
    with pytest.raises(ValueError):
        false_alarms_per_patient_day(two_days, 3)


# 5
def test_detection_delay_onset_reference() -> None:
    days = [benchmark_day([gt("C1", 10_000), gt("C2", 50_000), gt("C3", 90_000)])]
    assert detection_delay_ms(m1(), days) == [400.0, 900.0]
    early = match_events([gt("C1", 10_000)], [det(9_800, C1)], CFG)
    assert detection_delay_ms(early, [benchmark_day([gt("C1", 10_000)])]) == [-200.0]


# 6
def test_first_decidable_ms_rules() -> None:
    assert first_decidable_ms(gt("C1", 100_000, 400_000, template="resp")) == 400_000
    assert first_decidable_ms(gt("C1", 100_000, None, template="range")) == 100_000
    assert first_decidable_ms(gt("C2", 100_000, 200_000)) == 100_000
    assert first_decidable_ms(gt("C3", 100_000)) == 100_000


# 7
def test_match_first_decidable_reference_and_window() -> None:
    event = gt("C1", 100_000, 400_000, template="resp")
    hit = match_events([event], [det(399_000, C1)], CFG_FD)
    assert [p.delay_ms for p in hit.pairs] == [-1_000.0]
    miss = match_events(
        [event], [det(402_000, C1)], CFG_FD
    )  # |402_000 - 400_000| = 2_000 > 1_000
    assert miss.pairs == ()
    assert len(miss.missed) == 1 and len(miss.false_alarms) == 1


# 8
def test_detection_delay_rejects_misaligned_days() -> None:
    other = [benchmark_day([gt("C1", 10_000)])]
    with pytest.raises(ValueError):
        detection_delay_ms(m1(), other)


# 9
def test_recall_vs_false_alarm_curve_hand_computed() -> None:
    cfg = CFG
    events = [gt("C1", 10_000), gt("C1", 30_000), gt("C2", 50_000), gt("C3", 70_000)]
    # alpha 0.05: two events matched, one false alarm; 10 patient-days
    a = match_events(
        events, [det(10_000, C1), det(30_000, C1), det(500_000, C1)], cfg, n_days=10
    )
    # alpha 0.2: three matched, three false alarms
    b = match_events(
        events,
        [
            det(10_000, C1),
            det(30_000, C1),
            det(50_000, C2),
            det(500_000, C1),
            det(600_000, C1),
            det(700_000, C1),
        ],
        cfg,
        n_days=10,
    )
    curve = recall_vs_false_alarm_curve([a, b], [0.05, 0.2])
    # (false alarms per patient-day, recall) = (1 / 10, 2 / 4) and (3 / 10, 3 / 4)
    assert curve == [
        (pytest.approx(0.1), pytest.approx(0.5)),
        (pytest.approx(0.3), pytest.approx(0.75)),
    ]
    with pytest.raises(ValueError):
        recall_vs_false_alarm_curve([a], [0.05, 0.2])


# 10
def test_empirical_coverage_alert_level() -> None:
    preds = [predicted(True), predicted(True), predicted(False), predicted(False)]
    truth = [-0.2, 0.1, -0.5, 0.3]
    # emitted with sigma >= 0: only the second one, so 1 - 1/4
    assert empirical_coverage(preds, truth, 0.2) == pytest.approx(0.75)
    with pytest.raises(ValueError):
        empirical_coverage(
            [predicted(True, alpha=0.1)], [0.1], 0.2
        )  # rho.alpha differs from alpha
    with pytest.raises(ValueError):
        empirical_coverage(preds, truth[:3], 0.2)


# 11
def test_residual_coverage_band_level() -> None:
    # sigma_true <= sigma_hat + q = 0.35 for -0.1, 0.05, 0.3 (not 0.6): 3 / 4
    assert residual_coverage([0.0] * 4, [-0.1, 0.05, 0.3, 0.6], 0.35) == pytest.approx(
        0.75
    )
    assert (
        residual_coverage([0.0], [5.0], math.inf) == 1.0
    )  # an infinite quantile covers everything


# 12
def test_mean_interval_width() -> None:
    assert mean_interval_width([(-0.2, 0.2), (0.0, 0.5)]) == pytest.approx(
        0.45
    )  # (0.4 + 0.5) / 2
    with pytest.raises(ValueError):
        mean_interval_width([])


# 13
def test_expected_calibration_error_hand_computed() -> None:
    rho = [0.95, 0.85, 0.7, 0.65]
    outcome = [True, True, False, False]
    # 5 bins: [0.8, 1.0] holds 0.95 and 0.85 (mean 0.9, observed 1.0): |0.9 - 1.0| * 0.5 = 0.05;
    # [0.6, 0.8) holds 0.7 and 0.65 (mean 0.675, observed 0.0): 0.675 * 0.5 = 0.3375; total 0.3875
    assert expected_calibration_error(rho, outcome, 5) == pytest.approx(0.3875)
    bins = reliability_bins(rho, outcome, 5)
    assert len(bins) == 5
    top = bins[-1]
    assert (top.n, top.observed_rate) == (2, 1.0)
    assert top.mean_rho == pytest.approx(0.9)
    assert (top.lo, top.hi) == (pytest.approx(0.8), pytest.approx(1.0))
    assert bins[0].n == 0 and math.isnan(bins[0].mean_rho)


# 14
def test_expected_calibration_error_rho_one_in_last_bin() -> None:
    assert expected_calibration_error([1.0], [True], 5) == 0.0
    assert reliability_bins([1.0], [True], 5)[-1].n == 1


# 15
def test_attribution_confusion_fixture_m1() -> None:
    cells = attribution_confusion(m1())
    assert cells is not None
    assert cells[("C1", "C1")] == 1 and cells[("C2", "C3")] == 1
    assert len(cells) == 12  # 3 true classes x (C1, C2, C3, UNDETERMINED)
    assert sum(cells.values()) == 2
    assert all(
        v == 0 for k, v in cells.items() if k not in {("C1", "C1"), ("C2", "C3")}
    )
    assert {k[1] for k in cells} == {"C1", "C2", "C3", "UNDETERMINED"}


def attribution_matching():  # type: ignore[no-untyped-def]
    events = [gt("C1", 10_000), gt("C2", 30_000), gt("C3", 50_000), gt("C1", 70_000)]
    dets = [det(10_000, C1), det(30_000, UND), det(50_000, C3), det(70_000, C2)]
    return match_events(events, dets, CFG)


# 16
def test_attribution_metrics_with_abstention() -> None:
    m = attribution_matching()
    assert abstention_rate(m) == pytest.approx(0.25)  # 1 of 4 matched pairs
    # answered 3 of 4 (coverage 0.75), correct 2 of 3
    assert accuracy_vs_coverage(m) == [(pytest.approx(0.75), pytest.approx(2 / 3))]
    # C1: TP 1, FP 0, FN 1 -> P 1, R 0.5, F1 2/3; C2: TP 0, FP 1, FN 1 -> F1 0; C3: TP 1 -> F1 1
    assert attribution_macro_f1(m) == pytest.approx((2 / 3 + 0.0 + 1.0) / 3)  # 5 / 9


# 17
def test_attribution_none_for_unlabelled_detector() -> None:
    m = match_events([gt("C1", 10_000)], [det(10_000, None)], CFG)
    assert attribution_confusion(m) is None
    assert accuracy_vs_coverage(m) is None
    assert attribution_macro_f1(m) is None
    assert abstention_rate(m) is None


def test_attribution_of_a_pair_matched_by_a_predicted_alert_reads_the_superseding_alert() -> (
    None
):
    """OP-T07-10 / ADR-041 (6): the label of a pair matched by a predicted alert comes from the VIOLATED alert of the
    same instance key; a predicted alert that is never superseded has no attribution to score."""
    events = [gt("C1", 10_000), gt("C2", 50_000)]
    dets = [
        alert(10_000, UND, key="a", verdict=VerdictState.PREDICTED_VIOLATION),
        alert(
            10_300, C1, key="a"
        ),  # supersedes it: a duplicate in the window, the source of the label
        alert(
            50_000, UND, key="b", verdict=VerdictState.PREDICTED_VIOLATION
        ),  # never superseded
    ]
    m = match_events(events, dets, CFG)
    assert len(m.pairs) == 2 and len(m.duplicates) == 1
    cells = attribution_confusion(m)
    assert cells is not None
    assert cells[("C1", "C1")] == 1
    assert (
        sum(cells.values()) == 1
    )  # the second pair is out of the numerator and the denominator
    assert m.unresolved_attribution == 1
    assert abstention_rate(m) == 0.0  # 0 of 1 scored pair


# 18
def test_latency_percentiles_hand_computed() -> None:
    p = latency_percentiles([float(i) for i in range(1, 11)])
    # linear interpolation at (n - 1) q: 1 + 9 * 0.5 = 5.5; 1 + 9 * 0.95 = 9.55; 1 + 9 * 0.99 = 9.91
    assert p["p50"] == pytest.approx(5.5)
    assert p["p95"] == pytest.approx(9.55)
    assert p["p99"] == pytest.approx(9.91)
    with pytest.raises(ValueError):
        latency_percentiles([])


# 19
def test_severity_rank_agreement_kendall() -> None:
    # six pairs, five concordant and one discordant: (5 - 1) / 6
    assert severity_rank_agreement([1, 2, 3, 4], [1, 3, 2, 4]) == pytest.approx(2 / 3)
    # tau-b: C = 2, D = 0, n0 = 3, ties in the first list 1, none in the second: 2 / sqrt((3 - 1)(3 - 0))
    assert severity_rank_agreement([1, 1, 2], [1, 2, 3]) == pytest.approx(
        2 / math.sqrt(6)
    )
    assert math.isnan(severity_rank_agreement([1, 1, 1], [1, 2, 3]))
    with pytest.raises(ValueError):
        severity_rank_agreement([1, 2], [1])


# 20
def test_bootstrap_ci_two_days_hand_computed() -> None:
    # the mean of a resample of two values {0, 1} is 0, 0.5 or 1 with probability 1/4, 1/2, 1/4: the 2.5th and
    # 97.5th percentiles of 2_000 resamples are the extremes
    assert bootstrap_ci([0.0, 1.0], n_resamples=2_000, level=0.95, seed=0) == (0.0, 1.0)


# 21
def test_bootstrap_ci_constant_values_degenerate() -> None:
    lo, hi = bootstrap_ci([0.25] * 7, n_resamples=500, level=0.95, seed=3)
    assert lo == hi == 0.25


# 22
def test_bootstrap_ci_reproducible_and_stream_independent() -> None:
    values = [0.0, 0.2, 0.4, 0.4, 1.0, 0.7, 0.1]
    first = bootstrap_ci(values, n_resamples=300, level=0.9, seed=5)
    np.random.default_rng([5, 1]).random(
        100
    )  # the split stream of the same seed is consumed first
    again = bootstrap_ci(values, n_resamples=300, level=0.9, seed=5)
    assert first == again
    assert bootstrap_ci(values, n_resamples=300, level=0.9, seed=6) != first


# 23
def test_paired_bootstrap_constant_positive_difference() -> None:
    a = [1.5, 2.0, 0.5, 3.0]
    b = [0.5, 1.0, -0.5, 2.0]  # a - b = +1 everywhere
    assert paired_bootstrap_ci(a, b, n_resamples=400, level=0.95, seed=0) == (1.0, 1.0)
    with pytest.raises(ValueError):
        paired_bootstrap_ci(a, b[:3], n_resamples=10, level=0.95, seed=0)


def test_cluster_bootstrap_resamples_clusters_not_units() -> None:
    # two clusters of two units with values (0, 0) and (1, 1): a cluster resample has mean 0, 0.5 or 1; a unit
    # resample could give any of 0, .25, .5, .75, 1. The percentile interval is the same here, the check is the
    # weights: constant within a cluster, so every resampled mean is a multiple of 0.5
    values = [0.0, 0.0, 1.0, 1.0]
    lo, hi = bootstrap_ci(
        values, n_resamples=500, level=0.95, seed=1, clusters=[0, 0, 1, 1]
    )
    assert (lo, hi) == (0.0, 1.0)
    lo2, hi2 = bootstrap_ci(
        values, n_resamples=500, level=0.5, seed=1, clusters=[0, 0, 1, 1]
    )
    assert lo2 in (0.0, 0.5) and hi2 in (0.5, 1.0)


def test_bootstrap_statistic_ratio_of_sums() -> None:
    # a ratio statistic (hits over trials) recomputed on the resampled sums, one row per unit: (hits, trials)
    table = np.array([[1.0, 2.0], [0.0, 2.0], [2.0, 2.0]])

    def ratio(row: np.ndarray) -> float:
        return float(row[0] / row[1]) if row[1] else math.nan

    lo, hi = bootstrap_statistic(table, ratio, n_resamples=1_000, level=0.95, seed=2)
    # every unit ratio is 0.5, 0.0, 1.0: any resample of three units has a ratio in [0, 1]
    assert 0.0 <= lo <= hi <= 1.0
    assert bootstrap_statistic(table, ratio, n_resamples=1_000, level=0.95, seed=2) == (
        lo,
        hi,
    )


def test_matching_table_sum_equals_concatenation() -> None:
    a, b = m1(), attribution_matching()
    both = Matching.concat([a, b])
    assert both.n_days == 2
    assert len(both.gt) == len(a.gt) + len(b.gt)
    assert len(both.pairs) == len(a.pairs) + len(b.pairs)
    ta = a.table().sum(axis=0)
    tb = b.table().sum(axis=0)
    assert np.array_equal(both.table().sum(axis=0), ta + tb)


def test_restrict_subtypes_keeps_false_alarms() -> None:
    events = [gt("C2", 10_000, subtype="stuck_at"), gt("C2", 50_000, subtype="drift")]
    m = match_events(events, [det(10_000, C2), det(900_000, C2)], CFG)
    only = m.restrict_subtypes({"stuck_at"})
    assert len(only.gt) == 1 and len(only.pairs) == 1
    assert len(only.false_alarms) == 1  # a false alarm stays a false alarm
    assert per_class_prf(only)["C2"]["recall"] == 1.0


# 24
@given(
    gt_times=st.lists(st.integers(0, 10**6), max_size=12),
    det_times=st.lists(st.integers(0, 10**6), max_size=12),
    tol=st.integers(1, 5_000),
)
def test_prop_matching_is_one_to_one(
    gt_times: list[int], det_times: list[int], tol: int
) -> None:
    events = [gt("C1", t) for t in gt_times]
    dets = [det(t, C1) for t in det_times]
    m = match_events(events, dets, MatchConfig(tol, "onset"))
    assert len(m.pairs) + len(m.missed) == len(events)
    assert len(m.pairs) + len(m.duplicates) + len(m.false_alarms) == len(dets)
    used = [p.det_index for p in m.pairs]
    assert len(used) == len(set(used))  # no detection matches twice
    assert all(abs(p.det.t_ms - p.t_ref_ms) <= tol for p in m.pairs)


# 25
@given(
    gt_times=st.lists(st.integers(0, 10**5), max_size=10),
    det_times=st.lists(st.integers(0, 10**5), max_size=10),
    seed=st.integers(0, 10),
)
def test_prop_matching_invariant_to_input_order(
    gt_times: list[int], det_times: list[int], seed: int
) -> None:
    events = [gt("C1", t) for t in gt_times]
    dets = [det(t, C1) for t in det_times]
    shuffled = list(dets)
    np.random.default_rng(seed).shuffle(shuffled)
    a = match_events(events, dets, CFG)
    b = match_events(events, shuffled, CFG)
    key = lambda m: (  # noqa: E731
        sorted((p.gt.onset_ms, p.det.t_ms) for p in m.pairs),
        sorted(e.onset_ms for e in m.missed),
        sorted(d.t_ms for d in m.duplicates),
        sorted(d.t_ms for d in m.false_alarms),
    )
    assert key(a) == key(b)


# 26
@given(
    gt_times=st.lists(st.integers(0, 10**5), max_size=10),
    det_times=st.lists(st.integers(0, 10**5), max_size=10),
    rho=st.lists(st.floats(0.0, 1.0), min_size=1, max_size=20),
    bins=st.integers(1, 12),
)
def test_prop_prf_and_ece_in_unit_interval(
    gt_times: list[int], det_times: list[int], rho: list[float], bins: int
) -> None:
    events = [gt("C1", t) for t in gt_times]
    dets = [det(t, C1) for t in det_times]
    prf = per_class_prf(match_events(events, dets, CFG))
    for group in prf.values():
        for value in group.values():
            assert math.isnan(value) or 0.0 <= value <= 1.0
    outcome = [r > 0.5 for r in rho]
    ece = expected_calibration_error(rho, outcome, bins)
    assert math.isnan(ece) or 0.0 <= ece <= 1.0
