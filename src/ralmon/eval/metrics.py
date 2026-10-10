"""The metrics of analisi section 5.5 (``02-interfaces.md#metrics``), the matching of E3 and the bootstrap of E5.

Every function is a pure function of its arguments. Randomness enters only through ``bootstrap_weights``, which takes an
explicit integer seed and draws from ``numpy.random.default_rng([seed, STREAM_BOOTSTRAP])`` (E2: one named stream per
component, never a generator shared between components). Nothing here reads a clock, the environment or the network.

Matching (E3). ``match_events`` takes the ground-truth events and the detections of one unit (the runner passes the
whole record of one patient, see the runner docstring) and matches them one to one. The events are taken in onset order;
for each the earliest unmatched detection with ``|t_det - t_ref| <= tolerance_ms`` is its match, so an early warning is
the matched detection. A detection that is not matched but lies in the window of a matched event is a duplicate (neither a
true positive nor a false alarm); every other unmatched detection is a false alarm and counts in full. Detection is
label-agnostic: the class of a detection is never used to match. The detections are put in a total order (time, label,
score, input position) first, so the result does not depend on the order of the input.

Per-class scores. ``TP_c`` counts the matched events of class ``c``; ``precision_c = TP_c / (TP_c + FA)`` (``FA`` is the
number of false alarms of the detector, whatever its label), ``recall_c = TP_c / GT_c``, ``f1_c`` their harmonic mean
(0 when both are defined and ``TP_c = 0``). A ratio with a zero denominator is ``nan``, never 0. ``any`` pools the classes.

Attribution (E4). It is scored on matched pairs only. A pair matched by a predicted alert reads its label from the VIOLATED
alert of the same ``xi.instance_key`` in the same list of detections (ADR-041 (6), OP-T07-10); when there is none the pair
has no attribution to score, stays in the detection metrics, is left out of the numerator and the denominator of the
attribution metrics and is counted in ``Matching.unresolved_attribution``. A detector whose detections carry no label gets
``None`` from every attribution metric (they do not apply to it).

The sums of a matching are kept in a table (``Matching.table``, one row per unit of the bootstrap), and every scalar metric
of the runner is a function of the summed table, so that a bootstrap replicate is a matrix product and the interval of a
ratio is the interval of the ratio of the resampled sums.
"""

from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from collections.abc import Callable, Collection, Hashable, Sequence
from dataclasses import dataclass
from typing import Final, Literal

import numpy as np
from numpy.typing import NDArray

from ralmon.attribution import Alert, AttributedCause, Detection
from ralmon.benchmark import BenchmarkDay, GroundTruthEvent, InjectedClass
from ralmon.conformal import PredictedViolation
from ralmon.monitor import VerdictState
from ralmon.signals import DurationMs, TimeMs

__all__ = [
    "CLASSES",
    "COLUMNS",
    "LABEL_COLUMNS",
    "STREAM_AVAILABILITY",
    "STREAM_BOOTSTRAP",
    "STREAM_CALIBRATION",
    "STREAM_FORECASTER",
    "STREAM_SPLIT",
    "MatchConfig",
    "MatchedPair",
    "Matching",
    "ReliabilityBin",
    "abstention_rate",
    "accuracy_vs_coverage",
    "attribution_confusion",
    "attribution_macro_f1",
    "bootstrap_ci",
    "bootstrap_statistic",
    "bootstrap_weights",
    "ci_from_weights",
    "detection_delay_ms",
    "empirical_coverage",
    "expected_calibration_error",
    "false_alarms_per_patient_day",
    "first_decidable_ms",
    "latency_percentiles",
    "match_events",
    "mean_interval_width",
    "paired_bootstrap_ci",
    "paired_ci_from_weights",
    "per_class_prf",
    "recall_vs_false_alarm_curve",
    "reliability_bins",
    "residual_coverage",
    "severity_rank_agreement",
    "table_abstention_rate",
    "table_accuracy_answered",
    "table_coverage_answered",
    "table_delay_mean",
    "table_early_fraction",
    "table_fa_per_day",
    "table_macro_f1",
    "table_prf",
]

# algorithmic labels of the random streams of E2: one integer per component, fixed once, never reused
STREAM_SPLIT: Final[int] = 1
STREAM_FORECASTER: Final[int] = 2
STREAM_CALIBRATION: Final[int] = 3
STREAM_BOOTSTRAP: Final[int] = 4
STREAM_AVAILABILITY: Final[int] = 5

CLASSES: Final[tuple[str, ...]] = ("C1", "C2", "C3")
LABEL_COLUMNS: Final[tuple[str, ...]] = (*CLASSES, "UNDETERMINED")
TimeReference = Literal["onset", "first_decidable"]
_TIME_REFERENCES: Final[tuple[str, ...]] = ("onset", "first_decidable")
AttributionStatus = Literal["answered", "abstained", "unresolved", "unlabelled"]

# the columns of the sums table of a matching
COLUMNS: Final[tuple[str, ...]] = (
    "gt_C1",
    "gt_C2",
    "gt_C3",
    "tp_C1",
    "tp_C2",
    "tp_C3",
    "false_alarms",
    "duplicates",
    "days",
    "delay_n",
    "delay_sum_ms",
    "delay_early_n",
    "unresolved",
    *(f"conf_{t}_{p}" for t in CLASSES for p in LABEL_COLUMNS),
)
_COL: Final[dict[str, int]] = {name: i for i, name in enumerate(COLUMNS)}
Table = NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class MatchConfig:
    """Verbatim from ``02-interfaces.md#metrics`` (version 0.1.0), with a check of the values."""

    tolerance_ms: DurationMs  # matching window between detection and ground-truth event; declared in the paper
    time_reference: Literal["onset", "first_decidable"]

    def __post_init__(self) -> None:
        if (
            isinstance(self.tolerance_ms, bool)
            or not isinstance(self.tolerance_ms, int)
            or self.tolerance_ms < 0
        ):
            raise ValueError(
                f"tolerance_ms must be a non-negative integer, got {self.tolerance_ms!r}"
            )
        if self.time_reference not in _TIME_REFERENCES:
            raise ValueError(
                f"time_reference must be one of {_TIME_REFERENCES}, got {self.time_reference!r}"
            )


def first_decidable_ms(event: GroundTruthEvent) -> TimeMs:
    """The first instant at which the monitor can decide the event (README assumption 1 of WS08).

    A C1 event of a windowed obligation (RESP, SCHED, the day-end COUNT) stores the deadline in ``end_ms`` and is
    decidable from it; every other event is decidable from its onset.
    """
    if event.cls is InjectedClass.C1 and event.end_ms is not None:
        return event.end_ms
    return event.onset_ms


def _reference(event: GroundTruthEvent, cfg: MatchConfig) -> TimeMs:
    return (
        event.onset_ms if cfg.time_reference == "onset" else first_decidable_ms(event)
    )


@dataclass(frozen=True, slots=True)
class MatchedPair:
    """A ground-truth event and the detection matched to it.

    ``delay_ms`` is ``det.t_ms - t_ref_ms`` (negative: early warning). ``label`` is the label that the attribution metrics
    read (the detection's own, or the one of the superseding alert for a predicted alert) and ``attribution`` says
    whether that pair is scored: ``answered`` (C1, C2 or C3), ``abstained`` (UNDETERMINED), ``unresolved`` (a predicted
    alert that nothing supersedes) or ``unlabelled`` (a detector that does not attribute).
    """

    gt_index: int
    det_index: int
    gt: GroundTruthEvent
    det: Detection
    t_ref_ms: TimeMs
    delay_ms: float
    label: AttributedCause | None
    attribution: AttributionStatus


@dataclass(frozen=True, slots=True)
class Matching:
    """The outcome of ``match_events``: pairs, missed events, duplicates and false alarms, over ``n_days`` patient-days.

    ``gt`` and ``det`` keep the order of the input; the index tuples refer to them. ``attributes`` is True when some
    detection carries a label, False when detections exist and none does, None when there is no detection.
    """

    cfg: MatchConfig
    gt: tuple[GroundTruthEvent, ...]
    det: tuple[Detection, ...]
    pairs: tuple[MatchedPair, ...]
    missed_index: tuple[int, ...]
    duplicate_index: tuple[int, ...]
    false_alarm_index: tuple[int, ...]
    n_days: int
    attributes: bool | None

    @property
    def missed(self) -> tuple[GroundTruthEvent, ...]:
        return tuple(self.gt[i] for i in self.missed_index)

    @property
    def duplicates(self) -> tuple[Detection, ...]:
        return tuple(self.det[i] for i in self.duplicate_index)

    @property
    def false_alarms(self) -> tuple[Detection, ...]:
        return tuple(self.det[i] for i in self.false_alarm_index)

    @property
    def unresolved_attribution(self) -> int:
        """Matched pairs that stay out of the attribution metrics (a predicted alert that nothing supersedes)."""
        return sum(1 for p in self.pairs if p.attribution == "unresolved")

    @staticmethod
    def concat(matchings: Sequence[Matching]) -> Matching:
        """The matching of several units put together (days add up); all must share the same ``MatchConfig``."""
        if not matchings:
            raise ValueError("concat needs at least one matching")
        cfg = matchings[0].cfg
        gt: list[GroundTruthEvent] = []
        det: list[Detection] = []
        pairs: list[MatchedPair] = []
        missed: list[int] = []
        dups: list[int] = []
        fas: list[int] = []
        days = 0
        flags: list[bool | None] = []
        for m in matchings:
            if m.cfg != cfg:
                raise ValueError(
                    "cannot concatenate matchings with different MatchConfig"
                )
            g0, d0 = len(gt), len(det)
            gt.extend(m.gt)
            det.extend(m.det)
            pairs.extend(
                MatchedPair(
                    p.gt_index + g0,
                    p.det_index + d0,
                    p.gt,
                    p.det,
                    p.t_ref_ms,
                    p.delay_ms,
                    p.label,
                    p.attribution,
                )
                for p in m.pairs
            )
            missed.extend(i + g0 for i in m.missed_index)
            dups.extend(i + d0 for i in m.duplicate_index)
            fas.extend(i + d0 for i in m.false_alarm_index)
            days += m.n_days
            flags.append(m.attributes)
        attributes: bool | None
        if any(f is True for f in flags):
            attributes = True
        elif any(f is False for f in flags):
            attributes = False
        else:
            attributes = None
        return Matching(
            cfg,
            tuple(gt),
            tuple(det),
            tuple(pairs),
            tuple(missed),
            tuple(dups),
            tuple(fas),
            days,
            attributes,
        )

    def restrict_subtypes(self, subtypes: Collection[str]) -> Matching:
        """The matching seen through the events of the given subtypes (the subtype breakdown of recall).

        Events of other subtypes leave the matching, and so do the detections matched to them (they are neither true
        positives nor false alarms of this view); duplicates and false alarms stay, because the nurse still receives them.
        """
        keep_gt = [i for i, e in enumerate(self.gt) if e.subtype in subtypes]
        gt_map = {old: new for new, old in enumerate(keep_gt)}
        dropped_det = {p.det_index for p in self.pairs if p.gt_index not in gt_map}
        keep_det = [i for i in range(len(self.det)) if i not in dropped_det]
        det_map = {old: new for new, old in enumerate(keep_det)}
        pairs = tuple(
            MatchedPair(
                gt_map[p.gt_index],
                det_map[p.det_index],
                p.gt,
                p.det,
                p.t_ref_ms,
                p.delay_ms,
                p.label,
                p.attribution,
            )
            for p in self.pairs
            if p.gt_index in gt_map
        )
        return Matching(
            self.cfg,
            tuple(self.gt[i] for i in keep_gt),
            tuple(self.det[i] for i in keep_det),
            pairs,
            tuple(gt_map[i] for i in self.missed_index if i in gt_map),
            tuple(det_map[i] for i in self.duplicate_index),
            tuple(det_map[i] for i in self.false_alarm_index),
            self.n_days,
            self.attributes,
        )

    def table(
        self,
        event_days: Sequence[int] | None = None,
        det_days: Sequence[int] | None = None,
        n_units: int | None = None,
    ) -> Table:
        """The sums of this matching, one row per unit of the bootstrap.

        Without arguments the result has one row with the totals and ``days = n_days``. With ``event_days`` (the unit of
        each ground-truth event, in the order of ``gt``), ``det_days`` (the unit of each detection, in the order of
        ``det``) and ``n_units`` the result has ``n_units`` rows of one day each: a pair and a missed event belong to
        the unit of the event, a duplicate and a false alarm to the unit of the detection; a detection with the unit ``-1``
        is in no unit (the runner puts the unscored tail day there) and a duplicate or false alarm of it is not counted.
        """
        if event_days is None and det_days is None and n_units is None:
            rows = 1
            ev = [0] * len(self.gt)
            dt = [0] * len(self.det)
        else:
            if event_days is None or det_days is None or n_units is None:
                raise ValueError("event_days, det_days and n_units go together")
            if len(event_days) != len(self.gt) or len(det_days) != len(self.det):
                raise ValueError("event_days and det_days must align with gt and det")
            rows, ev, dt = n_units, list(event_days), list(det_days)
            for u in ev:
                if not 0 <= u < rows:
                    raise ValueError(f"unit {u} is outside 0..{rows - 1}")
            for u in dt:
                if not -1 <= u < rows:
                    raise ValueError(f"unit {u} is outside -1..{rows - 1}")
        table = np.zeros((rows, len(COLUMNS)), dtype=np.float64)
        table[:, _COL["days"]] = self.n_days if rows == 1 else 1.0
        for i, event in enumerate(self.gt):
            table[ev[i], _COL[f"gt_{event.cls.value}"]] += 1
        for p in self.pairs:
            u = ev[p.gt_index]
            cls = p.gt.cls.value
            table[u, _COL[f"tp_{cls}"]] += 1
            table[u, _COL["delay_n"]] += 1
            table[u, _COL["delay_sum_ms"]] += p.delay_ms
            if p.delay_ms < 0:
                table[u, _COL["delay_early_n"]] += 1
            if p.attribution == "unresolved":
                table[u, _COL["unresolved"]] += 1
            elif p.attribution in ("answered", "abstained") and p.label is not None:
                table[u, _COL[f"conf_{cls}_{p.label.value}"]] += 1
        for i in self.false_alarm_index:
            if dt[i] >= 0:
                table[dt[i], _COL["false_alarms"]] += 1
        for i in self.duplicate_index:
            if dt[i] >= 0:
                table[dt[i], _COL["duplicates"]] += 1
        return table


def _label_and_status(
    det: Detection, detections: Sequence[Detection]
) -> tuple[AttributedCause | None, AttributionStatus]:
    """The label that scores a matched detection (module docstring, "Attribution")."""
    source = det
    if isinstance(det, Alert) and det.verdict is VerdictState.PREDICTED_VIOLATION:
        found: Alert | None = None
        for other in detections:
            if (
                isinstance(other, Alert)
                and other.verdict is VerdictState.VIOLATED
                and other.xi.instance_key == det.xi.instance_key
            ):
                found = other
                break
        if found is None:
            return None, "unresolved"
        source = found
    if source.label is None:
        return None, "unlabelled"
    if source.label is AttributedCause.UNDETERMINED:
        return source.label, "abstained"
    return source.label, "answered"


def match_events(
    gt: Sequence[GroundTruthEvent],
    det: Sequence[Detection],
    cfg: MatchConfig,
    *,
    n_days: int = 1,
) -> Matching:
    """Match the detections of a unit to its ground-truth events (module docstring); the unit counts ``n_days`` days."""
    if isinstance(n_days, bool) or not isinstance(n_days, int) or n_days < 0:
        raise ValueError(f"n_days must be a non-negative integer, got {n_days!r}")
    gt_t = tuple(gt)
    det_t = tuple(det)
    order = sorted(
        range(len(det_t)),
        key=lambda i: (
            det_t[i].t_ms,
            "" if det_t[i].label is None else det_t[i].label.value,  # type: ignore[union-attr]
            det_t[i].score,
            i,
        ),
    )
    times = [det_t[i].t_ms for i in order]
    taken = [False] * len(order)
    pairs: list[MatchedPair] = []
    matched_windows: list[tuple[int, int]] = []
    matched_gt: set[int] = set()
    tol = cfg.tolerance_ms
    for g in sorted(range(len(gt_t)), key=lambda i: (gt_t[i].onset_ms, i)):
        ref = _reference(gt_t[g], cfg)
        lo = bisect_left(times, ref - tol)
        hi = bisect_right(times, ref + tol)
        chosen = next((p for p in range(lo, hi) if not taken[p]), None)
        if chosen is None:
            continue
        taken[chosen] = True
        matched_gt.add(g)
        matched_windows.append((lo, hi))
        d_index = order[chosen]
        label, status = _label_and_status(det_t[d_index], det_t)
        pairs.append(
            MatchedPair(
                g,
                d_index,
                gt_t[g],
                det_t[d_index],
                ref,
                float(det_t[d_index].t_ms - ref),
                label,
                status,
            )
        )
    in_window = [False] * len(order)
    for lo, hi in matched_windows:
        for p in range(lo, hi):
            in_window[p] = True
    duplicates = sorted(
        order[p] for p in range(len(order)) if not taken[p] and in_window[p]
    )
    false_alarms = sorted(
        order[p] for p in range(len(order)) if not taken[p] and not in_window[p]
    )
    missed = [i for i in range(len(gt_t)) if i not in matched_gt]
    attributes: bool | None
    if not det_t:
        attributes = None
    else:
        attributes = any(d.label is not None for d in det_t)
    return Matching(
        cfg,
        gt_t,
        det_t,
        tuple(pairs),
        tuple(missed),
        tuple(duplicates),
        tuple(false_alarms),
        n_days,
        attributes,
    )


# ---- scalar metrics of a summed table ---------------------------------------------------------------------------------


def _ratio(num: float, den: float) -> float:
    return num / den if den > 0 else math.nan


def _f1(precision: float, recall: float) -> float:
    if math.isnan(precision) or math.isnan(recall):
        return math.nan
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def table_prf(total: Table) -> dict[str, dict[str, float]]:
    """Precision, recall and F1 per class and pooled, from a summed table (module docstring)."""
    fa = float(total[_COL["false_alarms"]])
    out: dict[str, dict[str, float]] = {}
    gt_all = tp_all = 0.0
    for c in CLASSES:
        tp = float(total[_COL[f"tp_{c}"]])
        n_gt = float(total[_COL[f"gt_{c}"]])
        gt_all += n_gt
        tp_all += tp
        precision, recall = _ratio(tp, tp + fa), _ratio(tp, n_gt)
        out[c] = {
            "precision": precision,
            "recall": recall,
            "f1": _f1(precision, recall),
        }
    precision, recall = _ratio(tp_all, tp_all + fa), _ratio(tp_all, gt_all)
    out["any"] = {
        "precision": precision,
        "recall": recall,
        "f1": _f1(precision, recall),
    }
    return out


def table_fa_per_day(total: Table) -> float:
    return _ratio(float(total[_COL["false_alarms"]]), float(total[_COL["days"]]))


def table_delay_mean(total: Table) -> float:
    return _ratio(float(total[_COL["delay_sum_ms"]]), float(total[_COL["delay_n"]]))


def table_early_fraction(total: Table) -> float:
    return _ratio(float(total[_COL["delay_early_n"]]), float(total[_COL["delay_n"]]))


def _confusion(total: Table) -> dict[tuple[str, str], int]:
    return {
        (t, p): round(float(total[_COL[f"conf_{t}_{p}"]]))
        for t in CLASSES
        for p in LABEL_COLUMNS
    }


def table_macro_f1(total: Table) -> float:
    """Macro F1 over the classes that appear in a row or a column; UNDETERMINED is a false negative, never a false positive."""
    cells = _confusion(total)
    scores: list[float] = []
    for c in CLASSES:
        tp = cells[(c, c)]
        fn = sum(cells[(c, p)] for p in LABEL_COLUMNS) - tp
        fp = sum(cells[(t, c)] for t in CLASSES) - tp
        if tp + fn + fp == 0:
            continue  # the class appears nowhere
        scores.append(2 * tp / (2 * tp + fp + fn))
    return sum(scores) / len(scores) if scores else math.nan


def table_abstention_rate(total: Table) -> float:
    cells = _confusion(total)
    scored = sum(cells.values())
    return _ratio(sum(cells[(t, "UNDETERMINED")] for t in CLASSES), scored)


def table_coverage_answered(total: Table) -> float:
    cells = _confusion(total)
    scored = sum(cells.values())
    return _ratio(scored - sum(cells[(t, "UNDETERMINED")] for t in CLASSES), scored)


def table_accuracy_answered(total: Table) -> float:
    cells = _confusion(total)
    answered = sum(v for (_, p), v in cells.items() if p != "UNDETERMINED")
    return _ratio(sum(cells[(c, c)] for c in CLASSES), answered)


# ---- the metric functions of the contract -----------------------------------------------------------------------------


def per_class_prf(matching: Matching) -> dict[str, dict[str, float]]:
    """Precision, recall and F1 per class C1, C2, C3 and pooled (``any``); ``nan`` where the ratio is undefined."""
    return table_prf(matching.table().sum(axis=0))


def detection_delay_ms(matching: Matching, days: Sequence[BenchmarkDay]) -> list[float]:
    """``t_det - t_ref`` of every matched pair, in pair order (negative: early warning).

    ``days`` must be the days whose ground truth the matching was made from (their events, concatenated in order, are
    ``matching.gt``); anything else raises ``ValueError``.
    """
    truth = [e for day in days for e in day.ground_truth]
    if truth != list(matching.gt):
        raise ValueError(
            "the ground truth of days does not equal the ground truth of the matching"
        )
    return [p.delay_ms for p in matching.pairs]


def false_alarms_per_patient_day(matching: Matching, n_patient_days: int) -> float:
    if n_patient_days != matching.n_days:
        raise ValueError(
            f"n_patient_days is {n_patient_days} but the matching covers {matching.n_days} patient-days"
        )
    return _ratio(float(len(matching.false_alarm_index)), float(n_patient_days))


def recall_vs_false_alarm_curve(
    runs: Sequence[Matching], alphas: Sequence[float]
) -> list[tuple[float, float]]:
    """``(false alarms per patient-day, recall)`` of the run made at each alpha, in the order of ``alphas``."""
    if len(runs) != len(alphas):
        raise ValueError("runs and alphas must have the same length")
    curve: list[tuple[float, float]] = []
    for run in runs:
        total = run.table().sum(axis=0)
        gt_all = sum(float(total[_COL[f"gt_{c}"]]) for c in CLASSES)
        tp_all = sum(float(total[_COL[f"tp_{c}"]]) for c in CLASSES)
        curve.append((table_fa_per_day(total), _ratio(tp_all, gt_all)))
    return curve


def empirical_coverage(
    pred: Sequence[PredictedViolation], truth_sigma: Sequence[float], alpha: float
) -> float:
    """The alert level of Proposition 1: ``1 - P(alert emitted and sigma_true >= 0)`` over the predictions.

    ``alpha`` is the level of the prediction (the per-test level for the monitor, ADR-060): an emitted prediction whose
    ``rho.alpha`` differs raises ``ValueError``. The statement is marginal over patient episodes under exchangeability.
    """
    if len(pred) != len(truth_sigma):
        raise ValueError("pred and truth_sigma must have the same length")
    if not pred:
        raise ValueError("no predictions")
    bad = 0
    for p, sigma in zip(pred, truth_sigma, strict=True):
        if not p.emitted:
            continue
        if (
            p.rho is None
            or p.rho.alpha is None
            or not math.isclose(p.rho.alpha, alpha, rel_tol=1e-12, abs_tol=0.0)
        ):
            raise ValueError(
                f"an emitted prediction has level {None if p.rho is None else p.rho.alpha!r}, not alpha {alpha!r}"
            )
        if sigma >= 0:
            bad += 1
    return 1.0 - bad / len(pred)


def residual_coverage(
    sigma_hat: Sequence[float], sigma_true: Sequence[float], q: float
) -> float:
    """The band level: the share of episodes with ``sigma_true <= sigma_hat + q``."""
    if len(sigma_hat) != len(sigma_true):
        raise ValueError("sigma_hat and sigma_true must have the same length")
    if not sigma_hat:
        raise ValueError("no episodes")
    if math.isnan(q):
        raise ValueError("q is not a number")
    hits = sum(1 for h, t in zip(sigma_hat, sigma_true, strict=True) if t <= h + q)
    return hits / len(sigma_hat)


def mean_interval_width(intervals: Sequence[tuple[float, float]]) -> float:
    if not intervals:
        raise ValueError("no intervals")
    widths = []
    for lo, hi in intervals:
        if math.isnan(lo) or math.isnan(hi) or hi < lo:
            raise ValueError(f"invalid interval ({lo!r}, {hi!r})")
        widths.append(hi - lo)
    return sum(widths) / len(widths)


@dataclass(frozen=True, slots=True)
class ReliabilityBin:
    """One equal-width bin of the reliability diagram; ``nan`` means undefined (an empty bin)."""

    lo: float
    hi: float
    n: int
    mean_rho: float
    observed_rate: float


def reliability_bins(
    rho: Sequence[float], outcome: Sequence[bool], bins: int
) -> list[ReliabilityBin]:
    """Equal-width bins on [0, 1]; ``rho = 1`` falls in the last bin (E7)."""
    if len(rho) != len(outcome):
        raise ValueError("rho and outcome must have the same length")
    if isinstance(bins, bool) or not isinstance(bins, int) or bins < 1:
        raise ValueError(f"bins must be a positive integer, got {bins!r}")
    counts = [0] * bins
    rho_sum = [0.0] * bins
    hit_sum = [0] * bins
    for r, o in zip(rho, outcome, strict=True):
        if math.isnan(r) or not 0.0 <= r <= 1.0:
            raise ValueError(f"rho must lie in [0, 1], got {r!r}")
        b = min(int(r * bins), bins - 1)
        counts[b] += 1
        rho_sum[b] += r
        hit_sum[b] += 1 if o else 0
    return [
        ReliabilityBin(
            b / bins,
            (b + 1) / bins,
            counts[b],
            rho_sum[b] / counts[b] if counts[b] else math.nan,
            hit_sum[b] / counts[b] if counts[b] else math.nan,
        )
        for b in range(bins)
    ]


def expected_calibration_error(
    rho: Sequence[float], outcome: Sequence[bool], bins: int
) -> float:
    """``sum_b (n_b / N) |mean rho_b - observed rate_b|`` over equal-width bins; ``rho`` is never re-mapped (E7)."""
    if not rho:
        raise ValueError("no predictions")
    total = 0.0
    for b in reliability_bins(rho, outcome, bins):
        if b.n:
            total += b.n / len(rho) * abs(b.mean_rho - b.observed_rate)
    return total


def attribution_confusion(matching: Matching) -> dict[tuple[str, str], int] | None:
    """Counts of (true class, attributed cause) over the scored matched pairs; ``None`` for a detector that does not attribute."""
    if matching.attributes is not True:
        return None
    return _confusion(matching.table().sum(axis=0))


def accuracy_vs_coverage(matching: Matching) -> list[tuple[float, float]] | None:
    """The single operating point of a rule-based attributor: ``[(coverage, accuracy)]`` over the scored pairs (E4)."""
    if matching.attributes is not True:
        return None
    total = matching.table().sum(axis=0)
    return [(table_coverage_answered(total), table_accuracy_answered(total))]


def attribution_macro_f1(matching: Matching) -> float | None:
    if matching.attributes is not True:
        return None
    return table_macro_f1(matching.table().sum(axis=0))


def abstention_rate(matching: Matching) -> float | None:
    if matching.attributes is not True:
        return None
    return table_abstention_rate(matching.table().sum(axis=0))


def latency_percentiles(latencies_ms: Sequence[float]) -> dict[str, float]:
    """p50, p95 and p99 by linear interpolation between order statistics."""
    if not len(latencies_ms):
        raise ValueError("no latencies")
    values = np.asarray(latencies_ms, dtype=np.float64)
    if not np.all(np.isfinite(values)):
        raise ValueError("latencies must be finite")
    p50, p95, p99 = np.percentile(values, [50, 95, 99])
    return {"p50": float(p50), "p95": float(p95), "p99": float(p99)}


def severity_rank_agreement(auto: Sequence[float], clinician: Sequence[float]) -> float:
    """Kendall tau-b between two scorings of the same alerts (``nan`` when one of them is constant)."""
    if len(auto) != len(clinician):
        raise ValueError("auto and clinician must have the same length")
    n = len(auto)
    if n < 2:
        return math.nan
    if any(math.isnan(x) for x in (*auto, *clinician)):
        raise ValueError("scores must not be NaN")
    concordant = discordant = ties_a = ties_c = 0
    for i in range(n):
        for j in range(i + 1, n):
            da = auto[i] - auto[j]
            dc = clinician[i] - clinician[j]
            if da == 0:
                ties_a += 1
            if dc == 0:
                ties_c += 1
            if da == 0 or dc == 0:
                continue
            if (da > 0) == (dc > 0):
                concordant += 1
            else:
                discordant += 1
    n0 = n * (n - 1) // 2
    denominator = math.sqrt((n0 - ties_a) * (n0 - ties_c))
    return (concordant - discordant) / denominator if denominator else math.nan


# ---- bootstrap (E5) ---------------------------------------------------------------------------------------------------


def bootstrap_weights(
    n_units: int,
    n_resamples: int,
    seed: int,
    clusters: Sequence[Hashable] | None = None,
) -> NDArray[np.float64]:
    """The resampling weights, shape ``(n_resamples, n_units)``: how many times each unit enters a replicate.

    Without ``clusters`` the units (patient-days) are drawn with replacement. With ``clusters`` (one label per unit,
    typically the patient) the clusters are drawn with replacement and a unit enters as often as its cluster does, so the
    days of a patient stay together (the conservative interval). The generator is
    ``numpy.random.default_rng([seed, STREAM_BOOTSTRAP])``.
    """
    if n_units < 1:
        raise ValueError("no units to resample")
    if (
        isinstance(n_resamples, bool)
        or not isinstance(n_resamples, int)
        or n_resamples < 1
    ):
        raise ValueError(f"n_resamples must be a positive integer, got {n_resamples!r}")
    rng = np.random.default_rng([seed, STREAM_BOOTSTRAP])
    if clusters is None:
        return rng.multinomial(
            n_units, np.full(n_units, 1.0 / n_units), size=n_resamples
        ).astype(np.float64)
    if len(clusters) != n_units:
        raise ValueError("clusters must have one label per unit")
    labels = sorted(set(clusters), key=repr)
    index = {label: i for i, label in enumerate(labels)}
    k = len(labels)
    counts = rng.multinomial(k, np.full(k, 1.0 / k), size=n_resamples).astype(
        np.float64
    )
    unit_cluster = np.array([index[c] for c in clusters])
    return counts[:, unit_cluster]


def _percentiles(stats: NDArray[np.float64], level: float) -> tuple[float, float]:
    if not 0.0 < level < 1.0:
        raise ValueError(f"level must lie in (0, 1), got {level!r}")
    finite = stats[~np.isnan(stats)]
    if finite.size == 0:
        return math.nan, math.nan
    lo, hi = np.quantile(finite, [(1 - level) / 2, (1 + level) / 2])
    return float(lo), float(hi)


def ci_from_weights(
    table: NDArray[np.float64],
    stat: Callable[[NDArray[np.float64]], float],
    weights: NDArray[np.float64],
    level: float,
) -> tuple[float, float]:
    """Percentile interval of ``stat`` applied to the resampled sums ``weights @ table`` (one row per replicate)."""
    if table.shape[0] != weights.shape[1]:
        raise ValueError("weights and table disagree on the number of units")
    sums = weights @ table
    stats = np.array([stat(row) for row in sums], dtype=np.float64)
    return _percentiles(stats, level)


def paired_ci_from_weights(
    table_a: NDArray[np.float64],
    table_b: NDArray[np.float64],
    stat: Callable[[NDArray[np.float64]], float],
    weights: NDArray[np.float64],
    level: float,
) -> tuple[float, float]:
    """Percentile interval of ``stat(a) - stat(b)`` on the same resampled units (the paired bootstrap of ablations)."""
    if table_a.shape != table_b.shape:
        raise ValueError("the two tables must have the same shape")
    sums_a = weights @ table_a
    sums_b = weights @ table_b
    stats = np.array(
        [stat(a) - stat(b) for a, b in zip(sums_a, sums_b, strict=True)],
        dtype=np.float64,
    )
    return _percentiles(stats, level)


def bootstrap_statistic(
    table: NDArray[np.float64],
    stat: Callable[[NDArray[np.float64]], float],
    *,
    n_resamples: int,
    level: float,
    seed: int,
    clusters: Sequence[Hashable] | None = None,
) -> tuple[float, float]:
    """``ci_from_weights`` with the weights drawn from ``seed`` (one row of ``table`` per unit)."""
    weights = bootstrap_weights(table.shape[0], n_resamples, seed, clusters)
    return ci_from_weights(table, stat, weights, level)


def _mean_stat(row: NDArray[np.float64]) -> float:
    return float(row[0] / row[1]) if row[1] > 0 else math.nan


def _per_unit_table(values: Sequence[float]) -> NDArray[np.float64]:
    array = np.asarray(values, dtype=np.float64)
    if array.ndim != 1 or array.size == 0 or not np.all(np.isfinite(array)):
        raise ValueError("values must be a non-empty sequence of finite numbers")
    return np.column_stack([array, np.ones_like(array)])


def bootstrap_ci(
    values: Sequence[float],
    *,
    n_resamples: int,
    level: float,
    seed: int,
    clusters: Sequence[Hashable] | None = None,
) -> tuple[float, float]:
    """Percentile interval of the mean of per-unit ``values`` (patient-days) under resampling of the units."""
    return bootstrap_statistic(
        _per_unit_table(values),
        _mean_stat,
        n_resamples=n_resamples,
        level=level,
        seed=seed,
        clusters=clusters,
    )


def paired_bootstrap_ci(
    a: Sequence[float],
    b: Sequence[float],
    *,
    n_resamples: int,
    level: float,
    seed: int,
    clusters: Sequence[Hashable] | None = None,
) -> tuple[float, float]:
    """Percentile interval of the mean of ``a - b`` over the same resampled units."""
    if len(a) != len(b):
        raise ValueError("a and b must have the same length")
    ta, tb = _per_unit_table(a), _per_unit_table(b)
    weights = bootstrap_weights(ta.shape[0], n_resamples, seed, clusters)
    return paired_ci_from_weights(ta, tb, _mean_stat, weights, level)
