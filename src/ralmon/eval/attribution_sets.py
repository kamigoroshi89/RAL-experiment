"""Set metrics of the probabilistic attribution: coverage and size, the equal-coverage comparison, the pair calibration (WS08-T09).

The output of the likelihood attributor is a SET of subtypes (ADR-074 amendment 1). This module scores it:

* ``set_metrics``: coverage of the true subtype (it is in the set) and the size of the set, overall, per template, per true cause
  class and per true subtype; coverage PER PATIENT with a CLUSTER bootstrap over patients (the alerts of one patient are
  correlated). The set of an alert is ``Alert.cause_set``; an alert of the hierarchical rule has none, and its kappa is scored
  as a set (``kappa_as_set``: kappa to every subtype of its class applicable at the template, UNDETERMINED to every applicable
  subtype), given the table of the applicable subtypes. Without either the metric is ``None``.
* ``equal_coverage``: each method's posterior is calibrated by ``SubtypeSetCalibrator`` (marginal and Mondrian per template) on
  the calibration part of the patient-level split to the same target ``alpha`` and compared on the test part by the mean set
  size. A method with a fixed set (the hierarchical rule's kappa) has no threshold to tune: it is compared at its own coverage
  (``alpha = 1 - its coverage on the calibration part``). The frequency of ``top1_fill`` (the pure rule gave an empty set and the
  most probable subtype was added: it raises coverage above the rule) and of the Mondrian fallbacks (the full set of the
  applicable subtypes: it inflates the size) is reported PER TEMPLATE, because a comparison at equal coverage is only fair when
  it says how much of the coverage comes from them. A true subtype that is not applicable at the template (not a key of the
  posterior) is never in a set; it is counted.
* ``pair_set_calibration``: the confounder pairs get a SEPARATE calibrator (population ``pairs``, fitted on the calibration part
  of the pair population) and the main-population calibrator evaluated on the same pair test alerts is reported next to it (the
  transfer): the pairs have 50% prevalence of each mechanism and another template mix, so thresholds do not transfer.

What the coverage statement is. It is marginal (or within a Mondrian cell). The rank argument of split conformal prediction needs
exchangeable ALERTS; patient-level exchangeability of calibration and test does not give that when a patient contributes several
correlated alerts, so the finite-sample bound is exact only for one designated alert per patient and otherwise coverage is
approximate and checked empirically here (the cluster bootstrap over patients, the coverage per patient, the role-swap check);
ties make it conservative; it says nothing about another population. ``sets_metadata`` copies the guarantee strings of the set
builder and states the choices of the run.

Scoring side: this module reads the truth (``LabelledAlert.true_subtype``). The set builder it calls takes posteriors only.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from statistics import NormalDist
from typing import Any, Final

import numpy as np

from ralmon.conformal.scores import Level
from ralmon.conformal.sets import (
    ASSUMPTIONS_SETS,
    GUARANTEE_SETS,
    GUARANTEE_SETS_MONDRIAN,
    AttributionSet,
    SetThreshold,
    SubtypeCalibrationAlert,
    SubtypeSetCalibrator,
)
from ralmon.eval.attribution_truth import (
    LABELLING_STATEMENT,
    AlertInputs,
    LabelledAlert,
)
from ralmon.eval.metrics import CLASSES, TEMPLATES, bootstrap_statistic

__all__ = [
    "EQUAL_COVERAGE_WHY_PAIRS",
    "MODES",
    "alert_inputs_from_rule",
    "alpha_key",
    "applicable_from_table",
    "equal_coverage",
    "kappa_as_set",
    "pair_set_calibration",
    "set_metrics",
    "sets_metadata",
    "threshold_json",
    "wilson_interval",
]

MODES: Final[tuple[str, ...]] = ("marginal", "mondrian")
EQUAL_COVERAGE_WHY_PAIRS: Final = (
    "The confounder pairs are calibrated SEPARATELY: their prevalence is 50% of each mechanism and their template mix differs from the "
    "main population, so the calibration and test parts of the two populations are not exchangeable and the thresholds of the main "
    "population do not transfer. The transfer is reported next to the separate calibration to show it."
)


# ---- small statistics -----------------------------------------------------------------------------------------------


def wilson_interval(k: int, n: int, level: float) -> tuple[float, float]:
    """The Wilson score interval of a proportion ``k / n`` at the confidence ``level`` (over alerts, anti-conservative when the
    alerts of a patient are correlated); ``(nan, nan)`` without an observation."""
    if n <= 0:
        return math.nan, math.nan
    z = NormalDist().inv_cdf((1.0 + level) / 2.0)
    p = k / n
    d = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, centre - half), min(1.0, centre + half)


def _num(x: float) -> float | None:
    return float(x) if math.isfinite(x) else None


def alpha_key(alpha: Level) -> str:
    """The key of a level in the outputs: the decimal literal of a float (``0.2``) or ``n/d`` of a Fraction."""
    if isinstance(alpha, Fraction):
        return str(alpha)
    return repr(float(alpha))


def threshold_json(limit: SetThreshold) -> dict[str, Any]:
    """A threshold as JSON: ``inf`` (the full-set fallback) is ``null`` with the ``fallback`` flag and the reason."""
    return {
        "value": _num(limit.value),
        "n": limit.n,
        "fallback": limit.fallback,
        "reason": limit.reason,
        "cell": limit.cell,
    }


# ---- the set of an alert ------------------------------------------------------------------------------------------------


def kappa_as_set(
    kappa: str, applicable_by_class: Mapping[str, Sequence[str]]
) -> tuple[str, ...]:
    """A class label as a set: ``C1``/``C2``/``C3`` to every subtype of that class applicable at the template, ``UNDETERMINED`` to
    every applicable subtype (the convention of the metrics; not a stored value). Order: classes C1, C2, C3, as given."""
    if kappa == "UNDETERMINED":
        seen: dict[str, None] = {}
        for c in CLASSES:
            for name in applicable_by_class.get(c, ()):
                seen.setdefault(name, None)
        return tuple(seen)
    if kappa not in CLASSES:
        raise ValueError(f"kappa must be C1, C2, C3 or UNDETERMINED, got {kappa!r}")
    return tuple(applicable_by_class.get(kappa, ()))


def _set_of(
    item: LabelledAlert,
    applicable: Mapping[str, Mapping[str, Sequence[str]]] | None,
) -> tuple[tuple[str, ...], str] | None:
    if item.alert.cause_set is not None:
        return tuple(item.alert.cause_set), "alert.cause_set"
    if applicable is None or item.template not in applicable:
        return None
    kappa = str(getattr(item.alert.kappa, "value", item.alert.kappa))
    return kappa_as_set(kappa, applicable[item.template]), "kappa_as_set"


def applicable_from_table(table: Any) -> dict[str, dict[str, tuple[str, ...]]]:
    """The subtypes applicable at each template, by class, from a ``LikelihoodTable`` (``components`` with ``subtype``, ``cls`` and
    ``templates``): ``{template: {class: sorted subtypes}}``. Structure only: no cell value is read, so no sensitivity value is
    needed to build it. It is the table by which the kappa of the hierarchical rule is scored as a set."""
    out: dict[str, dict[str, set[str]]] = {}
    for component in table.components:
        for template in component.templates:
            out.setdefault(template, {c: set() for c in CLASSES})[component.cls].add(
                component.subtype
            )
    return {t: {c: tuple(sorted(v)) for c, v in by.items()} for t, by in out.items()}


METHOD_LIKELIHOOD: Final = "lik"
METHOD_PRIOR: Final = "prior"
FIXED_HIERARCHICAL: Final = "hier"


def alert_inputs_from_rule(
    rule: Any,
    record: Any,
    evidence: Any,
    *,
    hierarchical_kappa: str | None = None,
) -> AlertInputs:
    """The ``AlertInputs`` of an alert for the scoring side, from a ``LikelihoodRule`` (the call for a detector that offers
    ``alert_inputs``): the likelihood posterior (``lik``), the PRIOR-ONLY baseline (``prior``: the same rule on an evidence vector
    with every field unavailable, which contributes the factor 1, so the posterior is ``prior_t(class) * pi``), the evidence
    vector (for the pair quantity) and, when the hierarchical rule's ``kappa`` is given, its kappa as a fixed set (``hier``: every
    subtype of that class applicable at the template; ``UNDETERMINED`` every applicable subtype). Reads no truth."""
    from ralmon.attribution.evidence import empty_evidence

    template = evidence.provenance.violated_template
    by_class = applicable_from_table(rule.table)[template.value]
    fixed: dict[str, tuple[str, ...]] = {}
    if hierarchical_kappa is not None:
        fixed[FIXED_HIERARCHICAL] = kappa_as_set(hierarchical_kappa, by_class)
    return AlertInputs(
        {
            METHOD_LIKELIHOOD: dict(rule.posterior_subtypes(record, evidence)),
            METHOD_PRIOR: dict(
                rule.posterior_subtypes(record, empty_evidence(template))
            ),
        },
        fixed,
        evidence,
    )


# ---- coverage and size ------------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Row:
    patient: str
    template: str
    true_class: str
    true_subtype: str
    covered: bool
    size: int


def _group(rows: Sequence[_Row], level: float | None) -> dict[str, Any] | None:
    """The statistics of a group of alerts; ``level`` is the confidence of the Wilson interval (None: not computed)."""
    if not rows:
        return None
    n = len(rows)
    covered = sum(1 for r in rows if r.covered)
    wilson: list[float | None] | None = None
    if level is not None:
        lo, hi = wilson_interval(covered, n, level)
        wilson = [_num(lo), _num(hi)]
    counts = Counter(r.size for r in rows)
    return {
        "n": n,
        "covered": covered,
        "coverage": covered / n,
        "wilson": wilson,
        "mean_size": sum(r.size for r in rows) / n,
        "size_counts": {str(k): counts[k] for k in sorted(counts)},
    }


def _patient_table(rows: Sequence[_Row]) -> tuple[list[str], np.ndarray]:
    patients = sorted({r.patient for r in rows})
    index = {p: i for i, p in enumerate(patients)}
    table = np.zeros((len(patients), 3), dtype=np.float64)
    for r in rows:
        i = index[r.patient]
        table[i, 0] += 1.0 if r.covered else 0.0
        table[i, 1] += 1.0
        table[i, 2] += r.size
    return patients, table


def _cov_stat(row: np.ndarray) -> float:
    return float(row[0] / row[1]) if row[1] > 0 else math.nan


def _size_stat(row: np.ndarray) -> float:
    return float(row[2] / row[1]) if row[1] > 0 else math.nan


def _per_patient(
    rows: Sequence[_Row], n_resamples: int, level: float, seed: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    patients, table = _patient_table(rows)
    per = {p: float(table[i, 0] / table[i, 1]) for i, p in enumerate(patients)}
    values = np.array(list(per.values()), dtype=np.float64)
    summary = {
        "n_patients": len(patients),
        "coverage_by_patient": per,
        "median_coverage": float(np.median(values)),
        "p10_coverage": float(np.percentile(values, 10)),
    }
    boot: dict[str, Any] = {
        "unit": "patient",
        "n_resamples": n_resamples,
        "level": level,
        "n_patients": len(patients),
    }
    if len(patients) < 2:
        boot["coverage"] = [None, None]
        boot["mean_size"] = [None, None]
    else:
        for name, stat in (("coverage", _cov_stat), ("mean_size", _size_stat)):
            lo, hi = bootstrap_statistic(
                table,
                stat,
                n_resamples=n_resamples,
                level=level,
                seed=seed,
                clusters=patients,
            )
            boot[name] = [_num(lo), _num(hi)]
    return summary, boot


def set_metrics(
    items: Sequence[LabelledAlert],
    *,
    applicable: Mapping[str, Mapping[str, Sequence[str]]] | None = None,
    n_resamples: int,
    level: float,
    seed: int,
) -> dict[str, Any] | None:
    """Coverage and size of the sets of labelled alerts (module docstring); ``None`` when no alert has a set.

    ``applicable`` maps a lower-case template to ``{class: subtypes}`` and is needed only to score the kappa of an alert without a
    ``cause_set``. ``n_resamples``, ``level`` and ``seed`` are the cluster bootstrap over patients (run options, no defaults)."""
    rows: list[_Row] = []
    sources: set[str] = set()
    n_without = 0
    for item in items:
        got = _set_of(item, applicable)
        if got is None:
            n_without += 1
            continue
        chosen, source = got
        sources.add(source)
        rows.append(
            _Row(
                item.patient_id,
                item.template.upper(),
                item.true_class,
                item.true_subtype,
                item.true_subtype in chosen,
                len(chosen),
            )
        )
    if not rows:
        return None
    per_patient, boot = _per_patient(rows, n_resamples, level, seed)
    return {
        "n_alerts": len(rows),
        "n_without_set": n_without,
        "set_source": next(iter(sources)) if len(sources) == 1 else "mixed",
        "overall": _group(rows, level),
        "per_template": {
            t: _group([r for r in rows if r.template == t], level) for t in TEMPLATES
        },
        "per_true_class": {
            c: _group([r for r in rows if r.true_class == c], level) for c in CLASSES
        },
        "per_true_subtype": {
            s: _group([r for r in rows if r.true_subtype == s], level)
            for s in sorted({r.true_subtype for r in rows})
        },
        "per_patient": per_patient,
        "cluster_bootstrap": {
            **boot,
            "pooled_coverage_note": "the interval resamples patients",
        },
    }


# ---- equal coverage -------------------------------------------------------------------------------------------------------


def _posterior(item: LabelledAlert, method: str) -> Mapping[str, float] | None:
    if item.inputs is None:
        return None
    return item.inputs.posteriors.get(method)


def _fixed_set(item: LabelledAlert, method: str) -> tuple[str, ...] | None:
    if item.inputs is None:
        return None
    return item.inputs.fixed_sets.get(method)


class _Fitted:
    """The calibrators of one population: one per (method, mode), fitted once (the calibrator is level-agnostic)."""

    def __init__(
        self,
        calibration: Sequence[LabelledAlert],
        test: Sequence[LabelledAlert],
        methods: Sequence[str],
        modes: Sequence[str],
        population: str,
        model_version: str,
        min_cell_size: int | None,
    ) -> None:
        self.population = population
        self.model_version = model_version
        self.calibrators: dict[tuple[str, str], SubtypeSetCalibrator | None] = {}
        self.n_calibration: dict[str, int] = {}
        test_ids = sorted({item.patient_id for item in test})
        for method in methods:
            examples = [
                SubtypeCalibrationAlert(
                    item.patient_id, item.template, post, item.true_subtype
                )
                for item in calibration
                if (post := _posterior(item, method)) is not None
            ]
            self.n_calibration[method] = len(examples)
            for mode in modes:
                if not examples:
                    self.calibrators[(method, mode)] = None
                    continue
                calibrator = SubtypeSetCalibrator(
                    mode,  # type: ignore[arg-type]
                    population=population,
                    min_cell_size=min_cell_size,
                )
                calibrator.fit(
                    examples, model_version=model_version, test_patient_ids=test_ids
                )
                self.calibrators[(method, mode)] = calibrator


def _cell(
    fitted: _Fitted,
    method: str,
    mode: str,
    alpha: Level,
    test: Sequence[LabelledAlert],
    bootstrap: tuple[int, float, int] | None,
) -> dict[str, Any] | None:
    calibrator = fitted.calibrators.get((method, mode))
    if calibrator is None:
        return None
    rows: list[_Row] = []
    sets: list[AttributionSet] = []
    n_without = 0
    for item in test:
        post = _posterior(item, method)
        if post is None:
            n_without += 1
            continue
        chosen = calibrator.predict_set(
            post,
            item.template,
            alpha,
            patient_id=item.patient_id,
            model_version=fitted.model_version,
        )
        sets.append(chosen)
        rows.append(
            _Row(
                item.patient_id,
                item.template.upper(),
                item.true_class,
                item.true_subtype,
                item.true_subtype in chosen.subtypes,
                len(chosen.subtypes),
            )
        )
    if not rows:
        return None
    level = bootstrap[1] if bootstrap is not None else None
    out = _group(rows, level)
    assert out is not None
    per_template: dict[str, Any] = {}
    for t in sorted({r.template for r in rows}):
        idx = [i for i, r in enumerate(rows) if r.template == t]
        sub = _group([rows[i] for i in idx], level)
        assert sub is not None
        fallback = sum(1 for i in idx if sets[i].full_set_fallback)
        fill = sum(1 for i in idx if sets[i].top1_fill)
        sub.update(
            {
                "n_full_set_fallback": fallback,
                "full_set_fallback_share": fallback / len(idx),
                "n_top1_fill": fill,
                "top1_fill_share": fill / len(idx),
            }
        )
        per_template[t] = sub
    out["per_template"] = per_template
    out["per_true_class"] = {
        c: _group([r for r in rows if r.true_class == c], level) for c in CLASSES
    }
    out["n_without_posterior"] = n_without
    out["n_full_set_fallback"] = sum(1 for s in sets if s.full_set_fallback)
    out["n_top1_fill"] = sum(1 for s in sets if s.top1_fill)
    out["full_set_fallback_share"] = out["n_full_set_fallback"] / len(rows)
    out["top1_fill_share"] = out["n_top1_fill"] / len(rows)
    out["guarantee"] = sets[0].guarantee
    if mode == "marginal":
        out["threshold"] = threshold_json(
            calibrator.threshold(rows[0].template.lower(), alpha)
        )
    else:
        out["thresholds"] = {
            t: threshold_json(calibrator.threshold(t.lower(), alpha))
            for t in sorted({r.template for r in rows})
        }
    if bootstrap is not None:
        n_resamples, ci_level, seed = bootstrap
        _, boot = _per_patient(rows, n_resamples, ci_level, seed)
        out["cluster_bootstrap"] = boot
    return out


def _fixed_group(
    items: Sequence[LabelledAlert], method: str, level: float | None
) -> tuple[dict[str, Any] | None, int, int]:
    rows = [
        _Row(
            i.patient_id,
            i.template.upper(),
            i.true_class,
            i.true_subtype,
            i.true_subtype in chosen,
            len(chosen),
        )
        for i in items
        if (chosen := _fixed_set(i, method)) is not None
    ]
    group = _group(rows, level)
    covered = sum(1 for r in rows if r.covered)
    return group, covered, len(rows)


def _not_applicable(items: Sequence[LabelledAlert], method: str) -> int:
    return sum(
        1
        for i in items
        if (post := _posterior(i, method)) is not None and i.true_subtype not in post
    )


def _all_methods(items: Sequence[LabelledAlert]) -> tuple[list[str], list[str]]:
    posterior: dict[str, None] = {}
    fixed: dict[str, None] = {}
    for item in items:
        if item.inputs is None:
            continue
        for name in item.inputs.posteriors:
            posterior.setdefault(name, None)
        for name in item.inputs.fixed_sets:
            fixed.setdefault(name, None)
    return list(posterior), list(fixed)


def equal_coverage(
    calibration: Sequence[LabelledAlert],
    test: Sequence[LabelledAlert],
    *,
    methods: Sequence[str],
    alphas: Sequence[Level],
    model_version: str,
    population: str,
    modes: Sequence[str] = MODES,
    fixed_methods: Sequence[str] | None = None,
    min_cell_size: int | None = None,
    bootstrap: tuple[int, float, int] | None = None,
) -> dict[str, Any]:
    """The comparison at equal coverage (module docstring).

    ``calibration`` and ``test`` are labelled alerts of the two parts of the patient-level split; their ``inputs`` carry the
    posterior of each method. ``alphas`` are the targets (run parameters: no default), ``modes`` ``marginal`` and/or ``mondrian``.
    ``fixed_methods`` None means every name of ``AlertInputs.fixed_sets``. ``bootstrap`` is ``(n_resamples, level, seed)`` of the
    cluster bootstrap over patients. ``PatientLeakError`` if a calibration patient is also a test patient. The first of
    ``methods`` is the primary one for the count of true subtypes that are not applicable."""
    if not methods:
        raise ValueError("methods must name at least one posterior")
    for mode in modes:
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
    keys = [alpha_key(a) for a in alphas]
    if len(set(keys)) != len(keys):
        raise ValueError("alphas must not repeat")
    fitted = _Fitted(
        calibration, test, methods, modes, population, model_version, min_cell_size
    )
    primary = methods[0]
    out: dict[str, Any] = {
        "population": population,
        "model_version": model_version,
        "modes": list(modes),
        "n_calibration": len(calibration),
        "n_test": len(test),
        "n_calibration_patients": len({i.patient_id for i in calibration}),
        "n_test_patients": len({i.patient_id for i in test}),
        "n_calibration_true_not_applicable": _not_applicable(calibration, primary),
        "n_test_true_not_applicable": _not_applicable(test, primary),
        "calibration_cell_sizes": dict(
            sorted(Counter(i.template.upper() for i in calibration).items())
        ),
        "methods": {},
        "fixed": {},
    }
    for method in methods:
        out["methods"][method] = {
            "n_calibration": fitted.n_calibration[method],
            "alphas": {
                key: {
                    mode: _cell(fitted, method, mode, alpha, test, bootstrap)
                    for mode in modes
                }
                for key, alpha in zip(keys, alphas, strict=True)
            },
        }
    level = bootstrap[1] if bootstrap is not None else None
    names = (
        list(fixed_methods)
        if fixed_methods is not None
        else _all_methods([*calibration, *test])[1]
    )
    for name in names:
        cal_group, covered, n = _fixed_group(calibration, name, level)
        test_group, _, _ = _fixed_group(test, name, level)
        entry: dict[str, Any] = {"calibration": cal_group, "test": test_group}
        if n == 0 or covered in (0, n):
            entry["alpha_at_calibration_coverage"] = None
            entry["methods_at_alpha"] = None
            entry["note"] = (
                "the fixed set covers none or all of the calibration part: alpha = 1 - coverage is 1 or 0, which has no "
                "finite calibration"
            )
        else:
            alpha = Fraction(n - covered, n)
            entry["alpha_at_calibration_coverage"] = alpha_key(alpha)
            entry["methods_at_alpha"] = {
                method: {
                    mode: _cell(fitted, method, mode, alpha, test, bootstrap)
                    for mode in modes
                }
                for method in methods
            }
        out["fixed"][name] = entry
    return out


def pair_set_calibration(
    main_calibration: Sequence[LabelledAlert],
    pair_calibration: Sequence[LabelledAlert],
    pair_test: Sequence[LabelledAlert],
    *,
    methods: Sequence[str],
    alphas: Sequence[Level],
    model_version: str,
    modes: Sequence[str] = MODES,
    min_cell_size: int | None = None,
    bootstrap: tuple[int, float, int] | None = None,
) -> dict[str, Any]:
    """The pair population has its own calibrator (population ``pairs``), fitted on ``pair_calibration``; the main-population
    calibrator, fitted on ``main_calibration``, evaluated on the same ``pair_test`` alerts is the transfer, reported next to it.
    The ``patient_id`` of a pair alert is the identifier of its PAIR (the unit of the split)."""
    separate = equal_coverage(
        pair_calibration,
        pair_test,
        methods=methods,
        alphas=alphas,
        model_version=model_version,
        population="pairs",
        modes=modes,
        min_cell_size=min_cell_size,
        bootstrap=bootstrap,
        fixed_methods=(),
    )
    transfer = equal_coverage(
        main_calibration,
        pair_test,
        methods=methods,
        alphas=alphas,
        model_version=model_version,
        population="main",
        modes=modes,
        min_cell_size=min_cell_size,
        bootstrap=bootstrap,
        fixed_methods=(),
    )
    return {
        "separate": separate,
        "transfer_from_main": transfer,
        "why": EQUAL_COVERAGE_WHY_PAIRS,
    }


# ---- the statements of the metadata ---------------------------------------------------------------------------------------


def sets_metadata() -> dict[str, Any]:
    """The statements that go with every set table: the guarantee (copied from the set builder), the exchangeability statement,
    the labelling choice, the reading of ``top1_fill`` and of the fallbacks, and the study dimensions that are not implemented."""
    return {
        "guarantee_marginal": GUARANTEE_SETS,
        "guarantee_mondrian": GUARANTEE_SETS_MONDRIAN,
        "assumptions": list(ASSUMPTIONS_SETS),
        "exchangeability": (
            "Coverage is marginal (or within a Mondrian cell). The finite-sample bound of split conformal prediction needs exchangeable "
            "ALERTS: patient-level exchangeability of the calibration and test parts is not enough when a patient contributes several "
            "correlated alerts, so the bound is exact only for one designated alert per patient and otherwise coverage is approximate and "
            "checked empirically (cluster bootstrap over patients, coverage per patient, role-swap check); ties make it conservative; "
            "nothing is claimed for another population (the transfer from the main population to the pairs is reported as a failure). "
            "Coverage claims are always qualified in this way."
        ),
        "top1_fill": (
            "top1_fill: the pure conformal rule gave an empty set and the most probable subtype was added; it can only raise coverage "
            "above the rule, and its frequency is reported per template"
        ),
        "full_set_fallback": (
            "full_set_fallback: a threshold needs enough calibration alerts for the level (a Mondrian cell can have too few); the set "
            "is then the full set of the applicable subtypes, which inflates the mean size; its frequency is reported per template"
        ),
        "fixed_methods": (
            "A method with a fixed set (the hierarchical rule's kappa as a set) has no threshold to tune: the calibrated methods are "
            "compared with it at alpha = 1 - its coverage on the calibration part"
        ),
        "cell_scope": {
            "status": "not implemented",
            "note": "the study dimension cell_scope (template or all) of the sensitivity design is not implemented in LikelihoodRule; every result is for the components that can violate the template",
        },
        "family": {
            "status": "not implemented",
            "note": "the study dimension family (catalogue or benchmark_v1) is not implemented; every result is for the whole catalogue",
        },
        "labelling": {
            "primary": "tight",
            "reported_next_to_it": "loose",
            "choice": LABELLING_STATEMENT,
        },
    }
