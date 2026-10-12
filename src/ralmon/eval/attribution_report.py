"""The blocks of ``metrics.json`` for the probabilistic attribution (WS08-T09, ADR-074), built from the pure functions.

``ralmon.eval.runner`` calls these functions with the records of the test patients (and of the calibration patients when the sets
are calibrated); nothing here runs a detector. Every block is JSON-ready: no ``nan``, no ``inf`` (a threshold that is the full-set
fallback, or a log score that is infinite, is ``null`` with a reason), no ``Fraction`` (a level is a string key).

Layout (metric first, then the detector; ``null`` for a method the metric does not apply to, a ``status`` block for a metric that
applies and cannot be computed yet, and ``primary_labelling`` / ``labellings`` with BOTH labellings in every table, ADR-074 amendment 2):

* ``attribution_log_score.<det>`` and ``attribution_brier.<det>``: per template (RESP apart), the equal-weight ``aggregate`` and the
  counts; every mean is a scalar leaf with the day and the cluster bootstrap interval.
* ``attribution_calibration_curve.<det>``: per template, the pooled one-vs-rest reliability bins (counts; an empty bin has ``n`` 0 and
  ``null`` mean and frequency), the curve per class and the top-label curve with its ECE.
* ``attribution_sets.<det>``: coverage and size of ``Alert.cause_set`` (or of the kappa as a set for the hierarchical rule) per
  template, true class and true subtype, coverage per patient and its cluster bootstrap.
* ``attribution_equal_coverage.<det>``: the comparison at equal coverage and, under ``pairs``, the separate calibration of the pairs
  with the transfer from the main population.
* ``pair_llr.<det>`` and ``pair_direction_mcnemar.<det>``: see ``ralmon.eval.pairs``.
"""

from __future__ import annotations

import dataclasses
import math
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, NamedTuple, Protocol

import numpy as np

from ralmon.attribution import Alert, Detection
from ralmon.benchmark import GroundTruthEvent, InjectedClass
from ralmon.conformal import SubtypeCalibrationAlert
from ralmon.eval import attribution_sets as S
from ralmon.eval import metrics as M
from ralmon.eval import pairs as P
from ralmon.eval.attribution_truth import (
    EFFECT_POLICIES,
    LABELLING_STATEMENT,
    LABELLINGS,
    AlertInputs,
    AmbiguousAlert,
    EventContext,
    LabelledAlert,
    LabelResult,
    ambiguous_summary,
    label_alerts,
    subtype_alert_table,
)
from ralmon.eval.background import DAY_MS

__all__ = [
    "AWAITING",
    "AttributionConfigError",
    "AttributionOptions",
    "InputHook",
    "PairOutcome",
    "PairPatient",
    "PatientRecord",
    "calibrate_detector_sets",
    "dump_options",
    "instance_blocks",
    "mcnemar_blocks",
    "meta_block",
    "pair_outcome",
    "parse_options",
    "set_calibration_skip_reason",
]

AWAITING: Final = "awaiting_human_value"
InputHook = Callable[[str, Alert], "AlertInputs | None"]
_LEAF_KEYS: Final[tuple[str, ...]] = (
    "value",
    "ci_lo",
    "ci_hi",
    "ci_cluster_lo",
    "ci_cluster_hi",
)
_BLOCKS: Final[tuple[str, ...]] = (
    "attribution_log_score",
    "attribution_brier",
    "attribution_calibration_curve",
    "attribution_sets",
    "attribution_equal_coverage",
    "attribution_labelling",
)


class AttributionConfigError(ValueError):
    """``run_options.attribution`` is invalid."""


@dataclass(frozen=True, slots=True)
class AttributionOptions:
    """``run_options.attribution`` (WS08-T09). No number has a default.

    * ``loose_after_ms``: how long after the end of the window of an event an alert can still be caused by it (the loose
      labelling, and the C1 and C3 events in the tight one). ``awaiting_human_value`` (None) until a human states it; the research
      prototype used 24 h, which is not a value of the project.
    * ``set_alphas``: the targets of the equal-coverage comparison (None: not run, ``awaiting_human_value``).
    * ``effects``: ``fold`` (a cascade effect carries the ROOT's posterior and set and is left out, counted) or ``include``.
    * ``pair_primary_templates``: group to the template at which the members of the pairs of that group are compared first.
    """

    loose_after_ms: int | None = None
    set_alphas: tuple[float, ...] | None = None
    effects: str = "fold"
    pair_primary_templates: Mapping[str, str] = field(default_factory=dict)


def _is_int(x: object) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def parse_options(doc: Any) -> AttributionOptions:
    if not isinstance(doc, Mapping):
        raise AttributionConfigError("run_options.attribution must be a mapping")
    unknown = sorted(
        set(doc) - {"loose_after_ms", "set_alphas", "effects", "pair_primary_templates"}
    )
    if unknown:
        raise AttributionConfigError(f"run_options.attribution: unknown keys {unknown}")
    raw = doc.get("loose_after_ms", AWAITING)
    after: int | None
    if raw == AWAITING:
        after = None
    elif _is_int(raw) and raw >= 0:
        after = int(raw)
    else:
        raise AttributionConfigError(
            f"run_options.attribution.loose_after_ms must be a non-negative integer (ms) or {AWAITING!r}"
        )
    alphas_raw = doc.get("set_alphas")
    alphas: tuple[float, ...] | None = None
    if alphas_raw is not None:
        ok = (
            isinstance(alphas_raw, list)
            and len(alphas_raw) > 0
            and all(isinstance(a, float) and 0.0 < a < 1.0 for a in alphas_raw)
        )
        if not ok:
            raise AttributionConfigError(
                "run_options.attribution.set_alphas must be a non-empty list of numbers in (0, 1) written as decimals"
            )
        if len(set(alphas_raw)) != len(alphas_raw):
            raise AttributionConfigError(
                "run_options.attribution.set_alphas must not repeat"
            )
        alphas = tuple(float(a) for a in alphas_raw)
    effects = doc.get("effects", "fold")
    if effects not in EFFECT_POLICIES:
        raise AttributionConfigError(
            f"run_options.attribution.effects must be one of {list(EFFECT_POLICIES)}, got {effects!r}"
        )
    primary = doc.get("pair_primary_templates", {})
    valid = {t.lower() for t in M.TEMPLATES}
    if not (
        isinstance(primary, Mapping)
        and all(isinstance(k, str) and isinstance(v, str) for k, v in primary.items())
    ):
        raise AttributionConfigError(
            "run_options.attribution.pair_primary_templates must map a group to a template"
        )
    for group, template in primary.items():
        if template not in valid:
            raise AttributionConfigError(
                f"run_options.attribution.pair_primary_templates[{group!r}]: {template!r} is not a template ({sorted(valid)})"
            )
    return AttributionOptions(after, alphas, str(effects), dict(primary))


def dump_options(options: AttributionOptions) -> dict[str, Any]:
    out: dict[str, Any] = {
        "loose_after_ms": AWAITING
        if options.loose_after_ms is None
        else options.loose_after_ms,
        "effects": options.effects,
        "pair_primary_templates": dict(options.pair_primary_templates),
    }
    if options.set_alphas is not None:
        out["set_alphas"] = list(options.set_alphas)
    return out


@dataclass(frozen=True, slots=True)
class PatientRecord:
    """The scoring-side record of one patient: ground truth, the detections of the detector and the event contexts."""

    patient_id: str
    gt: tuple[GroundTruthEvent, ...]
    det: tuple[Detection, ...]
    contexts: tuple[EventContext, ...]
    n_days: int


@dataclass(frozen=True, slots=True)
class PairPatient:
    """One member of a confounder pair as the pairs module needs it."""

    patient_id: str
    pair_id: str
    member: str
    group: str
    variant_id: str | None
    indistinguishable: bool | None
    record: PatientRecord


# ---- helpers ------------------------------------------------------------------------------------------------------------------


def _num(x: float | None) -> float | None:
    return None if x is None or not math.isfinite(x) else float(x)


def _null_leaf() -> dict[str, None]:
    return dict.fromkeys(_LEAF_KEYS)


def _bins_json(bins: Sequence[M.ReliabilityBin]) -> list[dict[str, Any]]:
    return [
        {
            "lo": b.lo,
            "hi": b.hi,
            "n": b.n,
            "mean_p": _num(b.mean_rho),
            "observed_rate": _num(b.observed_rate),
        }
        for b in bins
    ]


class _Weights(Protocol):
    def scalar(
        self,
        table: np.ndarray,
        stat: Callable[[np.ndarray], float],
        label: str = "",
    ) -> dict[str, Any]: ...


def _has_p_kappa(records: Sequence[PatientRecord]) -> bool:
    return any(
        isinstance(d, Alert) and d.p_kappa is not None for r in records for d in r.det
    )


def _has_alert(records: Sequence[PatientRecord]) -> bool:
    return any(isinstance(d, Alert) for r in records for d in r.det)


def _has_cause_set(records: Sequence[PatientRecord]) -> bool:
    return any(
        isinstance(d, Alert) and d.cause_set is not None for r in records for d in r.det
    )


def _status(needs: Sequence[str], message: str) -> dict[str, Any]:
    return {"status": AWAITING, "needs": list(needs), "message": message}


# ---- labelling of a part of the split ---------------------------------------------------------------------------------------------


class _Labelled(NamedTuple):
    """The labelled alerts of a part of the split, the counts of those left out and the AMBIGUOUS alerts (tight labelling)."""

    labelled: list[LabelledAlert]
    excluded: dict[str, int]
    ambiguous: list[AmbiguousAlert]


def label_records(
    records: Sequence[PatientRecord],
    labelling: str,
    options: AttributionOptions,
    inputs: Callable[[str, Alert], AlertInputs | None] | None,
) -> _Labelled:
    """The labelled alerts of the records under one labelling, with the counts of those left out; an alert decided after the
    scored axis (in the unscored tail day) is left out as in the other metrics. ``inputs`` is the detector's hook (or None)."""
    assert options.loose_after_ms is not None
    out: list[LabelledAlert] = []
    ambiguous: list[AmbiguousAlert] = []
    excluded: Counter[str] = Counter()
    for rec in records:
        result = label_alerts(
            rec.gt,
            rec.det,
            rec.contexts,
            labelling=labelling,
            loose_after_ms=options.loose_after_ms,
            patient_id=rec.patient_id,
            effects=options.effects,
        )
        excluded.update(result.excluded)
        for amb in result.ambiguous:
            if amb.alert.t_ms > rec.n_days * DAY_MS:
                excluded["unscored_tail"] += 1
                excluded["ambiguous"] -= 1
                continue
            ambiguous.append(amb)
        for item in result.labelled:
            if item.alert.t_ms > rec.n_days * DAY_MS:
                excluded["unscored_tail"] += 1
                continue
            if inputs is not None:
                item = dataclasses.replace(
                    item, inputs=inputs(rec.patient_id, item.alert)
                )
            out.append(item)
    return _Labelled(out, dict(sorted(excluded.items())), ambiguous)


# ---- scores ---------------------------------------------------------------------------------------------------------------------


def _score_leaf(
    labelled: Sequence[LabelledAlert],
    summary: M.AttributionScoreSummary | None,
    template: str,
    key: str,
    table: np.ndarray,
    weights: _Weights,
    label: str,
) -> dict[str, Any]:
    n = summary.n[template] if summary is not None else 0
    if n == 0 or summary is None:
        return {"n_alerts": 0, "n_zero_probability": 0, "mean": None}
    zero = summary.n_zero_probability[template]
    leaf: dict[str, Any] = {"n_alerts": n, "n_zero_probability": zero}
    if key == "log_score" and zero:
        leaf["mean"] = _null_leaf()
        leaf["reason"] = (
            f"zero probability of the true class for {zero} alert(s): -ln 0 is infinite, so the mean is not finite "
            "(null, not a number); mean_finite is the mean over the other alerts"
        )
        leaf["mean_finite"] = weights.scalar(
            table,
            lambda row: M.table_score_metric(row, template, key),
            f"{label}.finite",
        )
        return leaf

    def stat(row: np.ndarray) -> float:
        return M.table_score_metric(row, template, key)

    leaf["mean"] = weights.scalar(table, stat, label)
    return leaf


def _score_block(
    labelled: Sequence[LabelledAlert],
    key: str,
    unit_of: Callable[[LabelledAlert], int],
    n_units: int,
    weights: _Weights,
    label: str,
    excluded: Mapping[str, int],
) -> dict[str, Any]:
    summary = M.attribution_score_summary(labelled)
    table = M.score_table(labelled, unit_of, n_units)
    leaves = {
        t: _score_leaf(labelled, summary, t, key, table, weights, f"{label}.{t}")
        for t in M.TEMPLATES
    }
    averaged = list(summary.templates_averaged) if summary is not None else []
    aggregate: dict[str, Any] = {
        "weights": "equal",
        "templates_averaged": averaged,
        "excluded": ["RESP"],
        "excluded_reason": "ADR-072 (b): RESP is reported apart and does not enter the aggregate",
        "mean": None,
    }
    if averaged:
        zero_templates = [
            t
            for t in averaged
            if key == "log_score" and leaves[t]["n_zero_probability"]
        ]
        if zero_templates:
            aggregate["mean"] = _null_leaf()
            aggregate["reason"] = (
                f"zero probability of the true class in {zero_templates}: the log score is infinite there"
            )
        else:
            aggregate["mean"] = weights.scalar(
                table,
                lambda row: M.table_score_aggregate(row, key),
                f"{label}.aggregate",
            )
    return {
        "templates": {t: leaves[t] for t in M.AGGREGATE_TEMPLATES},
        "resp": leaves["RESP"],
        "aggregate": aggregate,
        "n_scored": sum(summary.n.values()) if summary is not None else 0,
        "n_without_p_kappa": summary.n_without_p_kappa if summary is not None else 0,
        "excluded": dict(excluded),
    }


def _curve_block(
    labelled: Sequence[LabelledAlert], bins: int, excluded: Mapping[str, int]
) -> dict[str, Any]:
    detail = M.attribution_calibration_detail(labelled, bins) or {}

    def one(t: str) -> dict[str, Any] | None:
        got = detail.get(t)
        if got is None:
            return None
        return {
            "n_alerts": got["n_alerts"],
            "bins": bins,
            "pooled": _bins_json(got["pooled"]),
            "per_class": {c: _bins_json(b) for c, b in got["per_class"].items()},
            "top_label": _bins_json(got["top_label"]),
            "ece_top_label": _num(got["ece_top_label"]),
        }

    return {
        "definition": (
            "pooled: the pairs (p_c, y_c) of the three classes of every alert in equal-width bins of [0, 1], mean stated p against the "
            "observed frequency; an empty bin has n 0 and null mean and frequency; top_label: the largest p_kappa (a tie goes to the first "
            "of C1, C2, C3) against whether that class was the cause"
        ),
        "templates": {t: one(t) for t in M.AGGREGATE_TEMPLATES},
        "resp": one("RESP"),
        "excluded": dict(excluded),
    }


# ---- the sets of the detector (WS08-T10) ---------------------------------------------------------------------------------------


def wants_set_calibration(detector: Any, options: AttributionOptions) -> bool:
    """A detector with a likelihood rule and a configured ``set_alpha`` gets its alert sets calibrated before the test run, when the
    labelling can be applied (``loose_after_ms``)."""
    return (
        getattr(detector, "alert_inputs", None) is not None
        and getattr(detector, "set_alpha", None) is not None
        and hasattr(detector, "fit_set_calibrator")
        and options.loose_after_ms is not None
    )


def set_calibration_skip_reason(detector: Any, options: AttributionOptions) -> str:
    """Why a detector with a ``set_alpha`` has no set calibration (the inverse of ``wants_set_calibration``)."""
    reasons = []
    if options.loose_after_ms is None:
        reasons.append(
            "run_options.attribution.loose_after_ms is an awaiting_human_value: no alert can be assigned a cause to calibrate on"
        )
    if getattr(detector, "alert_inputs", None) is None:
        reasons.append("the detector has no alert_inputs hook")
    if not hasattr(detector, "fit_set_calibrator"):
        reasons.append("the detector has no fit_set_calibrator")
    return "; ".join(reasons) + ": the sets stay the cumulative-level set"


def set_calibration_alerts(
    detector: Any, records: Sequence[PatientRecord], options: AttributionOptions
) -> list[SubtypeCalibrationAlert]:
    """The calibration alerts of the sets: the VIOLATED alerts of the calibration patients under the TIGHT labelling (the primary one),
    each with the likelihood posterior (``lik``) and the true subtype. The truth is read here, on the scoring side; the detector only
    receives the finished ``SubtypeCalibrationAlert`` list."""
    labelled = label_records(records, "tight", options, detector.alert_inputs).labelled
    return [
        SubtypeCalibrationAlert(
            item.patient_id,
            item.template,
            dict(item.inputs.posteriors[S.METHOD_LIKELIHOOD]),
            item.true_subtype,
        )
        for item in labelled
        if item.inputs is not None and S.METHOD_LIKELIHOOD in item.inputs.posteriors
    ]


def calibrate_detector_sets(
    detector: Any,
    records: Sequence[PatientRecord],
    options: AttributionOptions,
    *,
    test_patient_ids: Sequence[str],
) -> dict[str, Any]:
    """Fit and install the main-population set calibrator of ``detector`` on the calibration part; returns what was done (for ``meta``).

    Without a calibration alert nothing is fitted and the detector keeps issuing the cumulative-level set (the status says so). The
    pairs get their OWN calibrator elsewhere, from the calibration part of the pair population: never this one."""
    alerts = set_calibration_alerts(detector, records, options)
    status: dict[str, Any] = {
        "labelling": "tight",
        "population": "main",
        "n_calibration_alerts": len(alerts),
        "n_calibration_patients": len({a.patient_id for a in alerts}),
        "fitted": False,
    }
    if not alerts:
        status["reason"] = (
            "no labelled alert in the calibration part: the sets stay the cumulative-level set"
        )
        return status
    detector.fit_set_calibrator(alerts, test_patient_ids=list(test_patient_ids))
    detector.reset_set_counts()
    status["fitted"] = True
    return status


# ---- sets and equal coverage -----------------------------------------------------------------------------------------------------


def _model_version(detector: Any) -> str:
    rule = getattr(detector, "likelihood_rule", None)
    version = getattr(rule, "model_version", None) or getattr(
        detector, "model_version", None
    )
    return str(version) if version else "unversioned"


def instance_blocks(
    *,
    name: str,
    detector: Any,
    test: Sequence[PatientRecord],
    calibration: Sequence[PatientRecord],
    options: AttributionOptions,
    applicable: Mapping[str, Mapping[str, Sequence[str]]] | None,
    units: Sequence[tuple[str, int]],
    weights: _Weights,
    bins: int,
    n_resamples: int,
    level: float,
    seed: int,
) -> dict[str, Any]:
    """The five per-detector blocks (``_BLOCKS``) of one main detector, keyed by metric name.

    ``units`` are the patient-days of the bootstrap in the order of ``weights``; ``calibration`` are the records of the calibration
    part (only used by the equal-coverage comparison); ``applicable`` is the table of the subtypes applicable per template and class
    (for the kappa of the hierarchical rule as a set)."""
    out: dict[str, Any] = dict.fromkeys(_BLOCKS)
    scoring = _has_p_kappa(test)
    set_source = _has_cause_set(test) or (_has_alert(test) and applicable is not None)
    hook = getattr(detector, "alert_inputs", None)
    if not (scoring or set_source or hook is not None):
        return out
    if options.loose_after_ms is None:
        message = "loose_after_ms is an awaiting_human_value: without it no alert can be assigned a cause"
        needs = ["run_options.attribution.loose_after_ms"]
        if scoring:
            for key in _BLOCKS[:3]:
                out[key] = _status(needs, message)
        if set_source:
            out["attribution_sets"] = _status(needs, message)
        if hook is not None:
            out["attribution_equal_coverage"] = _status(needs, message)
        out["attribution_labelling"] = _status(needs, message)
        return out
    index = {unit: i for i, unit in enumerate(units)}
    n_days = {r.patient_id: r.n_days for r in test}

    def unit_of(item: LabelledAlert) -> int:
        days = n_days[item.patient_id]
        day = min(max(item.alert.t_ms, 0) // DAY_MS, days - 1)
        return index[(item.patient_id, day)]

    cache: dict[tuple[str, int], AlertInputs | None] = {}

    def inputs(patient: str, alert: Alert) -> AlertInputs | None:
        if hook is None:
            return None
        key = (patient, id(alert))
        if key not in cache:
            cache[key] = hook(patient, alert)
        return cache[key]

    parts: dict[str, _Labelled] = {
        lab: label_records(test, lab, options, inputs if hook else None)
        for lab in LABELLINGS
    }
    n_units = len(units)
    if scoring:
        for key, short in (
            ("attribution_log_score", "log_score"),
            ("attribution_brier", "brier"),
        ):
            out[key] = {
                "primary_labelling": "tight",
                "labellings": {
                    lab: _score_block(
                        parts[lab][0],
                        short,
                        unit_of,
                        n_units,
                        weights,
                        f"{key}.{name}.{lab}",
                        parts[lab][1],
                    )
                    for lab in LABELLINGS
                },
            }
        out["attribution_calibration_curve"] = {
            "primary_labelling": "tight",
            "labellings": {
                lab: _curve_block(parts[lab][0], bins, parts[lab][1])
                for lab in LABELLINGS
            },
        }
    if set_source:
        sets: dict[str, Any] = {}
        for lab in LABELLINGS:
            got = S.set_metrics(
                parts[lab][0],
                applicable=applicable,
                n_resamples=n_resamples,
                level=level,
                seed=seed,
            )
            if got is not None:
                got["excluded"] = parts[lab][1]
            sets[lab] = got
        out["attribution_sets"] = {"primary_labelling": "tight", "labellings": sets}
    if hook is not None:
        out["attribution_equal_coverage"] = _equal_block(
            detector, parts, calibration, options, inputs, (n_resamples, level, seed)
        )
    out["attribution_labelling"] = _labelling_block(test, parts)
    return out


def _labelling_block(
    test: Sequence[PatientRecord], parts: Mapping[str, _Labelled]
) -> dict[str, Any]:
    """How the two labellings divide the injected subtypes (B1): the table injected subtype x alert count under the tight label, the
    AMBIGUOUS bucket of the tight labelling and the loose label, ZEROS SHOWN, the ambiguous alerts per injected subtype with their loose
    labels, and the point subtypes (injected C2 events with no window), whose headline figure is the LOOSE one."""
    injected = sorted({e.subtype for rec in test for e in rec.gt if e.injected})
    point = sorted(
        {
            e.subtype
            for rec in test
            for e in rec.gt
            if e.injected and e.cls is InjectedClass.C2 and e.end_ms is None
        }
    )
    results = {
        lab: LabelResult(
            tuple(parts[lab].labelled), parts[lab].excluded, tuple(parts[lab].ambiguous)
        )
        for lab in LABELLINGS
    }
    return {
        "primary_labelling": "tight",
        "injected_subtype_table": subtype_alert_table(results, injected),
        "ambiguous": ambiguous_summary(parts["tight"].ambiguous),
        "n_ambiguous": len(parts["tight"].ambiguous),
        "point_subtypes": point,
        "headline_for_point_subtypes": "loose",
        "note": (
            "ambiguous: the loose rule accepts an injected C2 event that the tight rule rejects only by time (a point or per-tick fault is "
            "active only at its instant); the alert is excluded from the tight tables and shown with its loose label; for the point "
            "subtypes the headline figure is the loose one"
        ),
    }


def _equal_block(
    detector: Any,
    parts: Mapping[str, _Labelled],
    calibration: Sequence[PatientRecord],
    options: AttributionOptions,
    inputs: Callable[[str, Alert], AlertInputs | None],
    bootstrap: tuple[int, float, int],
) -> dict[str, Any] | None:
    if options.set_alphas is None:
        return _status(
            ["run_options.attribution.set_alphas"],
            "the targets of the equal-coverage comparison are run parameters with no default",
        )
    if not calibration:
        return {
            "status": "no calibration patients",
            "message": "the split has no calibration part: the sets cannot be calibrated",
        }
    version = _model_version(detector)
    labellings: dict[str, Any] = {}
    for lab in LABELLINGS:
        cal, cal_excluded, _ = label_records(calibration, lab, options, inputs)
        test = parts[lab][0]
        methods = _methods_in(cal, test)
        if not methods:
            labellings[lab] = None
            continue
        labellings[lab] = S.equal_coverage(
            cal,
            test,
            methods=methods,
            alphas=options.set_alphas,
            model_version=version,
            population="main",
            bootstrap=bootstrap,
        )
        labellings[lab]["calibration_excluded"] = cal_excluded
        labellings[lab]["role_swap"] = S.role_swap_check(
            cal,
            test,
            methods=methods,
            alphas=options.set_alphas,
            model_version=version,
            population="main",
            bootstrap=bootstrap,
        )
    return {
        "primary_labelling": "tight",
        "labellings": labellings,
        "pairs": None,
    }


def _methods_in(*parts: Sequence[LabelledAlert]) -> list[str]:
    """The posterior methods present in the inputs of the labelled alerts, in order of first appearance."""
    seen: dict[str, None] = {}
    for part in parts:
        for item in part:
            if item.inputs is not None:
                for method in item.inputs.posteriors:
                    seen.setdefault(method, None)
    return list(seen)


# ---- pairs -----------------------------------------------------------------------------------------------------------------------------


def _pair_labelled(
    member: PairPatient, match: P.MemberMatch, alert: Alert, inputs: AlertInputs | None
) -> LabelledAlert:
    event = match.event
    return LabelledAlert(
        member.pair_id,
        alert,
        str(getattr(alert.tau, "value", alert.tau)).lower(),
        event.cls.value,
        event.subtype,
        match.event_index,
        event.injected,
        1,
        inputs,
    )


@dataclass(frozen=True, slots=True)
class PairOutcome:
    """What one detector gives on the confounder pairs: the ``pair_llr`` block, the results (test pairs) for McNemar and the
    pair-calibration block (or None)."""

    llr: dict[str, Any] | None
    results: tuple[P.PairResult, ...]
    sets: dict[str, Any] | None


def pair_outcome(
    *,
    detector: Any,
    twins: Sequence[PairPatient],
    test_pairs: Sequence[str],
    calibration_pairs: Sequence[str],
    calibration_records: Sequence[PatientRecord],
    options: AttributionOptions,
    level: float,
    bootstrap: tuple[int, float, int],
) -> PairOutcome:
    """The pair quantities of one detector (``pair_llr`` block, results of the test pairs, the separate calibration of the pairs).

    The detector needs ``likelihood_rule`` (a ``LikelihoodRule``: the cells) and ``alert_inputs`` (the evidence of an alert);
    without them the metric does not apply (``llr`` None). ``twins`` carry the detections of THIS detector."""
    rule = getattr(detector, "likelihood_rule", None)
    hook = getattr(detector, "alert_inputs", None)
    if rule is None or hook is None:
        return PairOutcome(None, (), None)
    by_pair: dict[str, dict[str, PairPatient]] = {}
    for twin in twins:
        by_pair.setdefault(twin.pair_id, {})[twin.member] = twin
    unmatched: Counter[str] = Counter()
    results: list[P.PairResult] = []
    rows: list[dict[str, Any]] = []
    labelled: dict[str, list[LabelledAlert]] = {"calibration": [], "test": []}
    for pair_id in sorted(by_pair):
        members = by_pair[pair_id]
        part = (
            "test"
            if pair_id in test_pairs
            else "calibration"
            if pair_id in calibration_pairs
            else None
        )
        if part is None or set(members) != {"A", "B"}:
            continue
        a, b = members["A"], members["B"]
        ma = P.match_member(a.record.gt, a.record.contexts, a.record.det, group=a.group)
        mb = P.match_member(b.record.gt, b.record.contexts, b.record.det, group=b.group)
        if ma is None or mb is None:
            unmatched[f"{part}: a member has no relevant injected event"] += 1
            continue
        common = P.common_match(
            ma, mb, primary=options.pair_primary_templates.get(a.group)
        )
        if common is None:
            unmatched[f"{part}: no common template with an alert in both members"] += 1
            continue
        template, alert_a, alert_b = common
        inputs_a, inputs_b = hook(a.patient_id, alert_a), hook(b.patient_id, alert_b)
        labelled[part].extend(
            [
                _pair_labelled(a, ma, alert_a, inputs_a),
                _pair_labelled(b, mb, alert_b, inputs_b),
            ]
        )
        if part != "test":
            continue
        if (
            inputs_a is None
            or inputs_b is None
            or inputs_a.evidence is None
            or inputs_b.evidence is None
        ):
            unmatched["test: no evidence vector for an alert"] += 1
            continue
        member_a = P.PairMember(
            pair_id, "A", a.group, a.variant_id, a.indistinguishable,
            ma.event.subtype, mb.event.subtype, template, inputs_a.evidence, alert_a,
        )  # fmt: skip
        member_b = P.PairMember(
            pair_id, "B", b.group, b.variant_id, b.indistinguishable,
            ma.event.subtype, mb.event.subtype, template, inputs_b.evidence, alert_b,
        )  # fmt: skip
        result = P.pair_result(member_a, member_b, rule)
        results.append(result)
        rows.append(
            {
                "pair_id": pair_id,
                "group": a.group,
                "variant_id": a.variant_id,
                "indistinguishable": a.indistinguishable,
                "template": template,
                "subtype_a": ma.event.subtype,
                "subtype_b": mb.event.subtype,
                "lambda_a": _num(result.lambda_a),
                "lambda_b": _num(result.lambda_b),
                "d": _num(result.d),
                "a_right": result.a_right,
                "b_right": result.b_right,
                "both_right": result.both_right,
                "d_positive": result.d_positive,
                "d_zero": result.d_zero,
            }
        )
    llr = {
        "quantity": (
            "Lambda_M = log P(e_M | s_A) - log P(e_M | s_B) between the two specific subtypes of the pair, prior-free; "
            "D = Lambda_A - Lambda_B"
        ),
        "matching": (
            "the relevant event of a member is its injected event of the confounder group; its alert is the earliest violated alert of "
            "a template the event can violate decided at or after the onset; the pair is compared at a common template (the primary "
            "template of the group if given, then the order of TEMPLATES); provisional rule of pairs-allocation.md section 5"
        ),
        "primary_templates": dict(options.pair_primary_templates),
        "n_pairs_test": len(test_pairs),
        "n_pairs_calibration": len(calibration_pairs),
        "unmatched": dict(sorted(unmatched.items())),
        "strata": P.summarize_strata(results, level=level),
        "pairs": rows,
    }
    return PairOutcome(
        llr,
        tuple(results),
        _pair_sets(detector, labelled, calibration_records, options, hook, bootstrap),
    )


def _pair_sets(
    detector: Any,
    labelled: Mapping[str, Sequence[LabelledAlert]],
    calibration_records: Sequence[PatientRecord],
    options: AttributionOptions,
    hook: Callable[[str, Alert], AlertInputs | None],
    bootstrap: tuple[int, float, int],
) -> dict[str, Any] | None:
    if options.set_alphas is None or options.loose_after_ms is None:
        return None
    pair_cal, pair_test = labelled["calibration"], labelled["test"]
    if not pair_cal or not pair_test:
        return {
            "status": "no calibration or no test pair with a matched alert",
            "n_calibration_alerts": len(pair_cal),
            "n_test_alerts": len(pair_test),
        }
    main_cal = label_records(calibration_records, "tight", options, hook).labelled
    methods = _methods_in(pair_cal, pair_test)
    if not methods or not main_cal:
        return {
            "status": "no posterior for the pair alerts or no calibration alert of the main population",
            "n_main_calibration_alerts": len(main_cal),
        }
    got = S.pair_set_calibration(
        main_cal,
        pair_cal,
        pair_test,
        methods=methods,
        alphas=options.set_alphas,
        model_version=_model_version(detector),
        bootstrap=bootstrap,
    )
    got["main_labelling"] = "tight"
    return got


def mcnemar_blocks(
    outcomes: Mapping[str, PairOutcome],
) -> dict[str, dict[str, Any] | None]:
    """``pair_direction_mcnemar.<det>``: for each detector with pair results, the McNemar table against every other one on the
    pairs they share (``b``: this detector right and the other not; ``c``: the reverse)."""
    out: dict[str, dict[str, Any] | None] = {}
    for name, outcome in outcomes.items():
        if outcome.llr is None:
            out[name] = None
            continue
        versus: dict[str, Any] = {}
        for other, theirs in outcomes.items():
            if other == name or theirs.llr is None:
                continue
            x, y, ids = P.align_directions(outcome.results, theirs.results)
            only_this, only_other = P.unshared_pairs(outcome.results, theirs.results)
            table = P.pair_direction_mcnemar(x, y)
            versus[other] = {
                "only_this": only_this,
                "only_other": only_other,
                **table,
                "n_pairs": len(ids),
                "indicator": "both members point to their own cause",
            }
        out[name] = {"vs": versus}
    return out


def meta_block(
    options: AttributionOptions | None,
    *,
    calibration_patients: Sequence[str],
    test_patients: Sequence[str],
    ece_bins: int,
    applicable_source: str | None,
) -> dict[str, Any]:
    """``meta.attribution``: the definitions, the labelling choice, the set statements, what is not implemented."""
    base: dict[str, Any] = {
        "score_definitions": {
            "log_score": "mean of -ln p_kappa(true class) over the scored alerts, in nats; infinite (null) if a true class has probability 0",
            "brier": "sum over C1, C2, C3 of (p_c - y_c)^2, averaged over the scored alerts (range 0 to 2)",
            "aggregate": "plain mean over the templates RANGE, SCHED, HOLD, COUNT, SYS, INT that have a scored alert; RESP apart (ADR-072 (b))",
            "per_template": "the template of the alert (Alert.tau)",
            "calibration_bins": ece_bins,
        },
        "cell_scope": S.sets_metadata()["cell_scope"],
        "family": S.sets_metadata()["family"],
        "pairs": {
            "precision": "not computed on pairs",
            "unit": "the pair; McNemar between methods on the indicator that both members point to their own cause",
        },
    }
    if options is None:
        return {"status": "not configured", **base}
    if options.loose_after_ms is None:
        status = AWAITING
    else:
        status = "configured"
    meta = S.sets_metadata()
    return {
        "status": status,
        **base,
        "labelling": {
            "primary": "tight",
            "reported_next_to_it": "loose",
            "choice": LABELLING_STATEMENT,
            "ambiguous": meta["labelling"]["ambiguous"],
            "point_c2_headline": meta["labelling"]["point_c2_headline"],
            "loose_after_ms_scope": meta["labelling"]["loose_after_ms_scope"],
            "loose_after_ms": options.loose_after_ms,
            "loose_after_ms_status": AWAITING
            if options.loose_after_ms is None
            else "set",
        },
        "effects": options.effects,
        "effects_note": (
            "a cascade effect carries the ROOT's p_kappa and cause_set; under 'fold' it is left out of the scores (counted in "
            "'excluded'), under 'include' it is scored against its own compatible events"
        ),
        "sets": {
            "guarantee_marginal": meta["guarantee_marginal"],
            "guarantee_mondrian": meta["guarantee_mondrian"],
            "assumptions": meta["assumptions"],
            "exchangeability": meta["exchangeability"],
            "cluster_bootstrap": meta["cluster_bootstrap"],
            "top1_fill": meta["top1_fill"],
            "full_set_fallback": meta["full_set_fallback"],
            "fixed_methods": meta["fixed_methods"],
            "alphas": None if options.set_alphas is None else list(options.set_alphas),
            "calibration_patients": sorted(calibration_patients),
            "test_patients": sorted(test_patients),
            "applicable_table": applicable_source,
        },
    }
