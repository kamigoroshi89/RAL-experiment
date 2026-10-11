"""Conformal calibration of the subtype sets of the attribution (WS05-T14, ADR-074 amendments 1 to 3).

The likelihood attributor returns a posterior over the SUBTYPES applicable at the template of an alert
(``posterior_subtypes``, WS05-T12). The reported cause is a SET of subtypes. This module builds that set
in two ways:

* ``cumulative_level_set``: the most probable subtypes up to a declared cumulative probability. This is
  the non-conformal set of the specification (``cumulative_level`` of
  ``docs/models/attribution-likelihood.md``), a run parameter without a default; it carries no coverage
  statement.
* ``SubtypeSetCalibrator``: split conformal calibration of a threshold on the nonconformity score
  ``1 - p(true subtype | e, t)``. The set of an alert is every subtype whose score is at most the
  threshold. Variants: ``"marginal"`` (one threshold for all alerts) and ``"mondrian"`` (one threshold per
  template, the Mondrian variant). The confounder pairs are calibrated by a SEPARATE instance (their
  prevalence is 50% and their template mix differs from the main population).

What the guarantee is, and is not. The rank argument of split conformal prediction gives, for a fixed
posterior model, a coverage of the true subtype of at least ``1 - alpha`` for a new alert, marginally
over the draw of the calibration set and of the test alert, IF the calibration scores and the test score
are exchangeable. Exchangeability of PATIENTS is not enough for that when a patient contributes several
alerts: alerts of one patient are correlated, so the alerts are not exchangeable even if the patients
are. The finite-sample bound is therefore exact only for one designated alert per patient (one score per
patient in the calibration set and one test alert from a patient not in it); with several alerts per
patient the coverage is APPROXIMATE and is checked empirically: the role-swap check (calibrate on the
test patients, evaluate on the calibration patients), the cluster bootstrap over patients and the
coverage per patient are metrics of the evaluation (WS08-T09), not part of this statement. Calibration
and test patients must be disjoint (this class refuses the overlap) and drawn from the same population.
Ties between scores make the coverage conservative. The Mondrian variant is marginal within each
template cell, not conditional on the true cause. Nothing here applies to another population (the
transfer from the main population to the pairs is a measured failure of the research), and nothing says
that the posterior is correct: a poor model gives large sets, not a broken guarantee. The phrase
"distribution-free coverage" is never used here without the qualification above.

Ground-truth discipline. Only the calibration side takes a truth: ``SubtypeCalibrationAlert.true_subtype``
and ``nonconformity_score``. The builders of a set (``prediction_set``, ``cumulative_level_set`` and
``SubtypeSetCalibrator.predict_set``) take only posteriors, a template, a level and identifiers; nothing
in this module reads ``LatentDay`` or ``GroundTruthEvent``.

Exactness. The level is read as in the other calibrators: a float through its ``repr`` (a decimal
literal), or a ``Fraction``; the quantile rank is computed in integer arithmetic
(``ralmon.conformal.scores``, ADR-030). The cumulative probabilities of ``cumulative_level_set`` are sums
of the decimal literals of the posteriors, exact. Scores are doubles ``1.0 - p``; a subtype is inside
the set when its score is at most the threshold, a comparison between two doubles obtained by the same
expression, so a subtype with the posterior of the calibration alert that gave the threshold is inside.
"""

from __future__ import annotations

import math
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
from typing import Final, Literal

from ralmon.conformal.scores import Level, exact_level, upper_quantile

__all__ = [
    "ASSUMPTIONS_SETS",
    "GUARANTEE_SETS",
    "GUARANTEE_SETS_MONDRIAN",
    "POSTERIOR_SUM_TOLERANCE",
    "AttributionSet",
    "PatientLeakError",
    "PosteriorError",
    "SetCalibrationError",
    "SetThreshold",
    "StaleSetCalibratorError",
    "SubtypeCalibrationAlert",
    "SubtypeSetCalibrator",
    "cumulative_level_set",
    "nonconformity_score",
    "prediction_set",
]

SetMode = Literal["marginal", "mondrian"]

#: Numerical tolerance on the sum of a posterior (floating-point rounding of a softmax), not a modelling value.
POSTERIOR_SUM_TOLERANCE: Final = 1e-9

GUARANTEE_SETS: Final = (
    "marginal over alerts; a finite-sample bound only for one designated alert per patient with "
    "calibration and test patients disjoint and exchangeable, otherwise approximate and checked empirically"
)
GUARANTEE_SETS_MONDRIAN: Final = (
    "marginal within each template cell; a finite-sample bound only for one designated alert per patient "
    "with calibration and test patients disjoint and exchangeable, otherwise approximate and checked "
    "empirically"
)
ASSUMPTIONS_SETS: Final[tuple[str, ...]] = (
    (
        "calibration and test patients are disjoint and are exchangeable draws from the same population; "
        "nothing is claimed for another population"
    ),
    (
        "alerts of one patient are correlated: patient-level exchangeability alone does not make the alerts "
        "exchangeable, so the rank bound is exact only for one designated alert per patient; with several "
        "alerts per patient the coverage is approximate and is checked empirically (role-swap check, "
        "cluster bootstrap over patients, coverage per patient)"
    ),
    "ties between scores make the coverage conservative",
    "the posterior model is fixed before calibration; the calibrator is fitted on the current model version",
    (
        "a threshold needs enough calibration alerts for the level; otherwise the set is the full set of "
        "the applicable subtypes"
    ),
)


class SetCalibrationError(ValueError):
    """Base of the named errors of the set calibration."""


class PosteriorError(SetCalibrationError):
    """A posterior is not a probability distribution over the subtypes (empty, negative, not finite, sum not 1)."""


class PatientLeakError(SetCalibrationError):
    """A patient of the calibration set also appears in the test set (the split must be patient-wise)."""


class StaleSetCalibratorError(Exception):
    """The set calibrator was fitted for another model version than the one in use, or for no model."""


# --- posteriors and scores ---------------------------------------------------------------------------------


def _validate_posteriors(posteriors: Mapping[str, float], context: str = "") -> None:
    where = f" ({context})" if context else ""
    if not isinstance(posteriors, Mapping) or len(posteriors) == 0:
        raise PosteriorError(
            f"a posterior must be a non-empty mapping subtype -> probability{where}"
        )
    for name, p in posteriors.items():
        if not isinstance(name, str) or not name:
            raise PosteriorError(
                f"subtype names must be non-empty strings, got {name!r}{where}"
            )
        if (
            isinstance(p, bool)
            or not isinstance(p, (int, float))
            or not math.isfinite(p)
        ):
            raise PosteriorError(
                f"the probability of {name!r} must be a finite number, got {p!r}{where}"
            )
        if not 0.0 <= p <= 1.0:
            raise PosteriorError(
                f"the probability of {name!r} must lie in [0, 1], got {p!r}{where}"
            )
    total = math.fsum(posteriors.values())
    if abs(total - 1.0) > POSTERIOR_SUM_TOLERANCE:
        raise PosteriorError(
            f"the probabilities must sum to 1 within {POSTERIOR_SUM_TOLERANCE}, got {total!r}{where}"
        )


def _ranked(posteriors: Mapping[str, float]) -> list[tuple[str, float]]:
    """Subtypes by decreasing probability, ties by name (the order of ``Alert.cause_set``)."""
    return sorted(
        ((n, float(p)) for n, p in posteriors.items()),
        key=lambda item: (-item[1], item[0]),
    )


def nonconformity_score(posteriors: Mapping[str, float], true_subtype: str) -> float:
    """``1 - p(true subtype | e, t)`` of one CALIBRATION alert: the only function here that takes a truth.

    A true subtype that is not a key of the posterior (not applicable at the template of the alert) has
    ``p = 0`` and score 1.
    """
    _validate_posteriors(posteriors)
    if not isinstance(true_subtype, str) or not true_subtype:
        raise ValueError(
            f"true_subtype must be a non-empty string, got {true_subtype!r}"
        )
    return 1.0 - float(posteriors.get(true_subtype, 0.0))


def prediction_set(
    posteriors: Mapping[str, float], threshold: float
) -> tuple[str, ...]:
    """Every subtype whose score ``1 - p`` is at most ``threshold``, by decreasing probability, ties by name.

    The builder takes only the posterior and the threshold: no truth can reach it. ``threshold = +inf``
    gives the full set of the subtypes of the posterior (the keys are the subtypes applicable at the
    template, see ``posterior_subtypes``). The pure rule can give an empty set when no subtype is probable
    enough; the calibrator then adds the most probable subtype (``SubtypeSetCalibrator.predict_set``).
    """
    _validate_posteriors(posteriors)
    if (
        isinstance(threshold, bool)
        or not isinstance(threshold, (int, float))
        or math.isnan(threshold)
    ):
        raise ValueError(
            f"threshold must be a number (+inf allowed), got {threshold!r}"
        )
    return tuple(name for name, p in _ranked(posteriors) if 1.0 - p <= threshold)


def cumulative_level_set(
    posteriors: Mapping[str, float], level: Level
) -> tuple[str, ...]:
    """The most probable subtypes until their cumulative probability reaches ``level`` (no default).

    Non-conformal alternative of ADR-074 amendment 1 (``cumulative_level``, a sensitivity value, for
    example 0.8, 0.9 or 0.95): it states no coverage. Subtypes are taken by decreasing probability, ties
    broken by subtype name, so the result does not depend on the order of the mapping. Probabilities and
    level are read as decimal literals (a float through its ``repr``) and summed exactly. The set has at
    least one subtype; if the probabilities sum to slightly less than the level, all subtypes are returned.
    """
    _validate_posteriors(posteriors)
    try:
        target = exact_level(level)
    except ValueError:
        raise ValueError(
            f"level must be a float or a Fraction in (0, 1), got {level!r}"
        ) from None
    chosen: list[str] = []
    cumulative = Fraction(0)
    for name, p in _ranked(posteriors):
        chosen.append(name)
        cumulative += Fraction(repr(p))
        if cumulative >= target:
            break
    return tuple(chosen)


# --- the calibration side ----------------------------------------------------------------------------------


def _cell_name(template: object) -> str:
    name = template.value if isinstance(template, Enum) else template
    if not isinstance(name, str) or not name:
        raise ValueError(
            f"template must be a non-empty string or a TemplateId, got {template!r}"
        )
    return name


@dataclass(frozen=True, slots=True)
class SubtypeCalibrationAlert:
    """One CALIBRATION alert: its posterior, its template and the true subtype (calibration only).

    ``posteriors`` are those of ``posterior_subtypes`` at the alert (keys: the subtypes applicable at the
    template). ``true_subtype`` is the ground-truth subtype of the alert in the calibration part of the
    benchmark; it is never an input of a set builder. ``patient_id`` is the unit of the split.
    """

    patient_id: str
    template: str
    posteriors: Mapping[str, float]
    true_subtype: str

    def __post_init__(self) -> None:
        if not isinstance(self.patient_id, str) or not self.patient_id:
            raise ValueError(
                f"patient_id must be a non-empty string, got {self.patient_id!r}"
            )
        _cell_name(self.template)
        if not isinstance(self.true_subtype, str) or not self.true_subtype:
            raise ValueError(
                f"true_subtype must be a non-empty string, got {self.true_subtype!r}"
            )


@dataclass(frozen=True, slots=True)
class SetThreshold:
    """The threshold of one cell at one level, and whether it is the full-set fallback."""

    value: float  # +inf: the full set of the applicable subtypes
    n: int  # calibration alerts of the cell (all alerts for the marginal variant)
    fallback: bool
    reason: str | None  # why the cell falls back; None when the threshold is finite
    cell: str | None  # the template of a Mondrian cell; None for the marginal variant


@dataclass(frozen=True, slots=True)
class AttributionSet:
    """The set of subtypes of one alert (``Alert.cause_set``) with the provenance of its threshold."""

    subtypes: tuple[str, ...]  # by decreasing probability, ties by name; never empty
    threshold: float  # +inf when ``full_set_fallback``
    alpha: Fraction
    mode: SetMode
    population: str
    cell: str | None
    n_calibration: int
    full_set_fallback: bool
    fallback_reason: str | None
    top1_fill: (
        bool  # the pure rule gave an empty set and the most probable subtype was added
    )
    guarantee: str
    assumptions: tuple[str, ...]


class SubtypeSetCalibrator:
    """Split conformal calibrator of the subtype sets, marginal or Mondrian per template.

    Reporting rules: the calibration unit is the PATIENT. ``fit`` receives the calibration alerts (with
    the true subtype, calibration only) and may be given the test patients, whose overlap with the
    calibration patients it refuses (``PatientLeakError``); ``predict_set`` takes the ``patient_id`` of
    the alert and refuses a patient of the calibration set. The calibrator is level-agnostic like
    ``SplitConformal``: the level ``alpha`` (a run parameter, no default) is given to ``threshold`` and
    ``predict_set``. The threshold of level ``alpha`` is the ``k``-th smallest calibration score,
    ``k = ceil((n + 1)(1 - alpha))``, and ``+inf`` (the full set of the applicable subtypes) if ``k > n``.

    A Mondrian cell (a template) with fewer calibration alerts than the rank needs, or fewer than
    ``min_cell_size`` if given, falls back to the full set of the applicable subtypes (the keys of the
    posterior), and ``SetThreshold`` and ``AttributionSet`` say so (``fallback``, ``reason``). A template
    without any calibration alert falls back in the same way. ``min_cell_size`` has no default: without it
    the only condition is the rank of the finite-sample correction.

    The statement is marginal; the finite-sample bound is exact only for one designated alert per patient,
    and with several correlated alerts per patient the coverage is approximate and checked empirically
    (see the module docstring). Use a SEPARATE instance
    (``population="pairs"``) for the confounder pairs: their prevalence is 50% and their template mix
    differs, so the thresholds of the main population do not transfer. The calibrator is tied to the
    model version given to ``fit`` (``calibrated_for``): ``predict_set`` requires the version of the
    posterior model in use and raises ``StaleSetCalibratorError`` on a mismatch or when the calibrator
    was fitted for no model, as for the other calibrators (contract rule 4). ``fit`` reads no randomness,
    no clock and no latent data other than the truth given in the calibration alerts.
    """

    def __init__(
        self,
        mode: SetMode,
        *,
        population: str,
        min_cell_size: int | None = None,
    ) -> None:
        if mode not in ("marginal", "mondrian"):
            raise ValueError(f"mode must be 'marginal' or 'mondrian', got {mode!r}")
        if not isinstance(population, str) or not population:
            raise ValueError(
                f"population must be a non-empty label (for example 'main' or 'pairs'), got {population!r}"
            )
        if min_cell_size is not None and (
            isinstance(min_cell_size, bool)
            or not isinstance(min_cell_size, int)
            or min_cell_size < 1
        ):
            raise ValueError(
                f"min_cell_size must be None or an integer of at least 1, got {min_cell_size!r}"
            )
        self._mode: SetMode = mode
        self._population = population
        self._min_cell_size = min_cell_size
        self.calibrated_for: str | None = None
        self._all: list[float] = []
        self._by_cell: dict[str, list[float]] = {}
        self._patients: frozenset[str] = frozenset()

    # -- accessors ---------------------------------------------------------------------------------------

    @property
    def mode(self) -> SetMode:
        return self._mode

    @property
    def population(self) -> str:
        return self._population

    @property
    def n_calibration(self) -> int:
        """Number of calibration alerts (all templates)."""
        return len(self._all)

    @property
    def calibration_patients(self) -> frozenset[str]:
        return self._patients

    def cell_sizes(self) -> dict[str, int]:
        """Calibration alerts per template, whatever the mode (to report which cells are small)."""
        return {cell: len(scores) for cell, scores in sorted(self._by_cell.items())}

    # -- fitting -----------------------------------------------------------------------------------------

    def fit(
        self,
        examples: Iterable[SubtypeCalibrationAlert],
        *,
        model_version: str | None = None,
        test_patient_ids: Collection[str] | None = None,
    ) -> None:
        """Compute the scores of the calibration alerts; refuse a patient shared with ``test_patient_ids``."""
        items = list(examples)
        if len(items) == 0:
            raise ValueError("a set calibrator needs at least one calibration alert")
        all_scores: list[float] = []
        by_cell: dict[str, list[float]] = {}
        for item in items:
            try:
                score = nonconformity_score(item.posteriors, item.true_subtype)
            except PosteriorError as err:
                raise PosteriorError(
                    f"calibration alert of patient {item.patient_id!r}: {err}"
                ) from None
            all_scores.append(score)
            by_cell.setdefault(_cell_name(item.template), []).append(score)
        patients = frozenset(item.patient_id for item in items)
        if test_patient_ids is not None:
            self._check_disjoint(patients, test_patient_ids)
        self._all = sorted(all_scores)
        self._by_cell = {cell: sorted(scores) for cell, scores in by_cell.items()}
        self._patients = patients
        self.calibrated_for = model_version

    def _require_fitted(self) -> None:
        if not self._all:
            raise RuntimeError("SubtypeSetCalibrator.fit has not been called")

    @staticmethod
    def _check_disjoint(calibration: frozenset[str], test: Collection[str]) -> None:
        if isinstance(test, str):
            raise TypeError(
                "test patient ids must be a collection of ids, not a single str "
                f"(got {test!r}, which would be read as its characters)"
            )
        shared = sorted(calibration.intersection(test))
        if shared:
            shown = ", ".join(repr(p) for p in shared[:5])
            more = f" and {len(shared) - 5} more" if len(shared) > 5 else ""
            raise PatientLeakError(
                f"{len(shared)} patient(s) appear in the calibration set and in the test set: {shown}{more}; "
                "the split must be patient-wise"
            )

    def require_disjoint(self, test_patient_ids: Collection[str]) -> None:
        """Raise ``PatientLeakError`` if a test patient belongs to the calibration set."""
        self._require_fitted()
        self._check_disjoint(self._patients, test_patient_ids)

    def check_fresh(self, model_version: str) -> None:
        """Refuse a calibrator fitted for another model version, or for no model."""
        if self.calibrated_for is None or self.calibrated_for != model_version:
            raise StaleSetCalibratorError(
                f"the set calibrator was calibrated for {self.calibrated_for!r}, the posterior model is "
                f"{model_version!r}: fit it again on held-out calibration alerts of the current model "
                "(fit(..., model_version=...))"
            )

    # -- thresholds and sets -----------------------------------------------------------------------------

    def threshold(self, template: str, alpha: Level) -> SetThreshold:
        """The threshold of the cell of ``template`` at level ``alpha`` (the marginal variant pools all alerts)."""
        self._require_fitted()
        level = exact_level(alpha)
        if self._mode == "marginal":
            cell: str | None = None
            scores = self._all
            scope = "all templates"
        else:
            cell = _cell_name(template)
            scores = self._by_cell.get(cell, [])
            scope = f"template {cell!r}"
        n = len(scores)
        needed = (
            math.ceil(1 / level) - 1
        )  # fewest alerts with a finite rank at this level
        reason: str | None = None
        if n == 0:
            reason = f"{scope}: no calibration alert; the full set of the applicable subtypes"
        elif self._min_cell_size is not None and n < self._min_cell_size:
            reason = (
                f"{scope}: {n} calibration alerts, below min_cell_size={self._min_cell_size}; "
                "the full set of the applicable subtypes"
            )
        else:
            value = upper_quantile(scores, level)
            if math.isinf(value):
                reason = (
                    f"{scope}: {n} calibration alerts, but level {float(level)!r} needs at least {needed} "
                    "for a finite threshold; the full set of the applicable subtypes"
                )
            else:
                return SetThreshold(
                    value=value, n=n, fallback=False, reason=None, cell=cell
                )
        return SetThreshold(
            value=math.inf, n=n, fallback=True, reason=reason, cell=cell
        )

    def predict_set(
        self,
        posteriors: Mapping[str, float],
        template: str,
        alpha: Level,
        *,
        patient_id: str,
        model_version: str,
    ) -> AttributionSet:
        """The set of subtypes of one alert: no truth, only the posterior, the template and the level.

        ``patient_id`` is mandatory: a patient of the calibration set is refused (``PatientLeakError``).
        ``model_version`` is the version of the posterior model in use (``StaleSetCalibratorError`` on a
        mismatch). If the pure rule gives an empty set (no subtype has a score at most the threshold),
        the most probable subtype (ties by name) is returned alone and ``top1_fill`` is True: a set is
        never empty (``Alert.cause_set``), and the addition can only raise the coverage.
        """
        self._require_fitted()
        self.check_fresh(model_version)
        if not isinstance(patient_id, str) or not patient_id:
            raise ValueError(
                f"patient_id must be a non-empty string, got {patient_id!r}"
            )
        self._check_disjoint(self._patients, (patient_id,))
        _validate_posteriors(posteriors, f"patient {patient_id!r}")
        level = exact_level(alpha)
        limit = self.threshold(template, level)
        chosen = prediction_set(posteriors, limit.value)
        fill = len(chosen) == 0
        if fill:
            chosen = (_ranked(posteriors)[0][0],)
        return AttributionSet(
            subtypes=chosen,
            threshold=limit.value,
            alpha=level,
            mode=self._mode,
            population=self._population,
            cell=limit.cell,
            n_calibration=limit.n,
            full_set_fallback=limit.fallback,
            fallback_reason=limit.reason,
            top1_fill=fill,
            guarantee=GUARANTEE_SETS
            if self._mode == "marginal"
            else GUARANTEE_SETS_MONDRIAN,
            assumptions=ASSUMPTIONS_SETS,
        )
