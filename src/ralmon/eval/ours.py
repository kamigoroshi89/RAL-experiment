"""The proposed method as a ``Detector``: ``OursDetector`` and its seam for the ablation variants (WS08-T01).

The pipeline is built from public pieces only: ``build_calibration_episodes`` and a conformal calibrator on the calibration
days, ``run_offline`` (or its detailed form) on the day, ``extract_evidence``, ``RuleAttributor`` and ``rank_alerts``.
``PipelineComponents`` is the frozen seam through which the ablations of WS08-T03 to T05 replace one stage; the default
is the full method with the split conformal calibrator.

What the detector reads. ``fit`` takes benchmark days (the ``Detector`` contract) and reads the observed trace of each
and nothing else: it never touches the latent trace or the ground truth of a training or a calibration day, and the
runner hands it days whose other members raise on access. ``run`` takes an observed day (a benchmark day is refused).
The forecaster is fitted on the training days only; the calibrator is fitted on the calibration days with
``model_version=forecaster.model_version`` (else the monitor refuses it, ``StaleCalibratorError``).

Output. ``run`` returns the alerts the way a nurse receives them: one VIOLATED alert per violated instance (``t_ms`` is
the instant at which the violation became decidable, ADR-041) and one PREDICTED_VIOLATION alert per predicted instance
at its first predicted record, also when the instance ends violated (the early warning of E3: it is the matched
detection when it is the earliest in the window, and the VIOLATED alert is then a duplicate) or satisfied (a false
predictive alarm). The label of a predicted alert is UNDETERMINED by definition; the attribution metrics read the label
of the superseding VIOLATED alert (``ralmon.eval.metrics``). The list is in the order of ``components.rank``.

Statefulness. ``run(..., history=days)`` forwards the earlier days of the patient to the monitor (ADR-046). The
calibration episodes are built with an empty history (``build_calibration_episodes`` has no history input), so a run with
history uses a calibrator fitted on per-day episodes; the runner reports it. An adaptive calibrator is forked per patient
(no leakage between patients) and updated once per completed episode, after the day that holds the episode has been run
(a prediction of the day is made with the state at the start of the day: the simplification of an offline run).

The attribution rule (WS08-T10, ADR-074). Without ``likelihood`` the detector is ``ours-hier``: the hierarchical rule, ``Alert.p_kappa``
and ``Alert.cause_set`` None, no ``alert_inputs``. With a ``LikelihoodSpec`` it builds the ``LikelihoodRule`` of WS05-T12 from
``configs/attribution_likelihood.yaml`` and the labelled ``sensitivity_values`` of the run (an awaiting row without a supplied value
fails at construction, ``AwaitingValueError``; the values are sensitivity values, never proposals). The rule is built with
``needs_cumulative_level=False`` and the set of every alert comes from this detector's selector: the conformal set of a fitted
``SubtypeSetCalibrator`` when one is installed for the population in use (``main``; ``pairs`` inside ``using_population("pairs")``,
a SEPARATE instance, never borrowed from ``main``), else ``cumulative_level_set`` with the declared ``cumulative_level``. The set
calibrator needs the true subtype of the calibration alerts, which a detector never sees: the scoring side (the runner) labels the
alerts of the calibration patients and hands the calibration alerts to ``fit_set_calibrator`` (``test_patient_ids`` refuses a patient
that is in both parts), and the calibrator is fitted with the model-version token of the rule (``StaleSetCalibratorError`` on a
mismatch). ``alert_inputs(patient_id, alert)`` gives the scoring side the subtype posterior, the prior-only baseline, the
hierarchical rule's kappa as a fixed set and the evidence vector of an alert (``alert_inputs_from_rule``); the evidence vectors and
records are kept per run for it and are released by ``fit``. ``a4=True`` is the variant ``ours-A4``: the extractor leaves the robot out
(witness and robot system fields None, the four aggregates recomputed over the devices) and the rule drops the cells of those fields.

Diagnostics. After each ``run`` the detector exposes ``last_run`` (``OursRunDetails``): the verdict records, the alerts,
the counters of the monitor (``n_tests``, ``per_test_alpha``, the INT gate of ADR-054, the rejected inputs), the
logical verdict latencies and the outcome of every predicted instance. The runner reads it for the metrics that need more
than ``Detection``s (coverage, calibration of rho, latency).
"""

from __future__ import annotations

import copy
from collections import Counter
from collections.abc import Callable, Collection, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from fractions import Fraction
from pathlib import Path
from typing import Any, Final

from ralmon.attribution import (
    Alert,
    AwaitingValueError,
    EvidenceVector,
    LikelihoodRule,
    RuleAttributor,
    empty_evidence,
    extract_evidence,
    load_likelihood_table,
)
from ralmon.benchmark import BenchmarkDay, ObservedDay
from ralmon.conformal import (
    ASSUMPTIONS_SETS,
    GUARANTEE_SETS,
    GUARANTEE_SETS_MONDRIAN,
    CalibrationEpisode,
    ConformalCalibrator,
    SplitConformal,
    SubtypeCalibrationAlert,
    SubtypeSetCalibrator,
    cumulative_level_set,
)
from ralmon.eval.attribution_sets import (
    alert_inputs_from_rule,
    alpha_key,
    threshold_json,
)
from ralmon.eval.attribution_truth import AlertInputs
from ralmon.monitor import (
    Forecast,
    Forecaster,
    MonitorConfig,
    MonitorStats,
    RejectedInput,
    UnsupportedSignalError,
    VerdictRecord,
    VerdictState,
    build_calibration_episodes,
    run_offline,
    run_offline_detailed,
)
from ralmon.signals import DurationMs, Sample, TimeMs
from ralmon.spec import CarePlan, ParameterRegistry, Template, rank_alerts

__all__ = [
    "CompositeForecaster",
    "LikelihoodSpec",
    "OursDetector",
    "OursRunDetails",
    "PipelineComponents",
    "PredictionOutcome",
]

EvidenceMap = Mapping[str, EvidenceVector]


def _identity_plan(plan: CarePlan) -> CarePlan:
    return plan


def _identity_evidence(evidence: EvidenceMap, seed: int) -> EvidenceMap:
    return evidence


def _default_rank(
    alerts: Sequence[Alert], records_by_instance_key: Mapping[str, VerdictRecord]
) -> Sequence[Alert]:
    """``rank_alerts`` (priority, then the normalised robustness, ADR-028); the records are for variants that need them."""
    return rank_alerts(alerts)


@dataclass(frozen=True, slots=True)
class PipelineComponents:
    """The stages of the proposed method that an ablation can replace (frozen: a variant is a new object).

    * ``calibrator_factory``: a fresh conformal calibrator (the split calibrator; A6 gives the adaptive one).
    * ``use_forecaster``: False runs the measured-only monitor (A2: no forecaster, no calibrator, no early warning).
    * ``plan_transform``: applied to the care plan before the monitor sees it (A5 removes the RESP and HOLD instances).
    * ``evidence_transform(evidence, seed)``: applied to the extracted evidence (A4 hides the embodied channel); ``seed``
      is the seed of the detector, for a transform that is random.
    * ``verdict_runner``: ``run_offline`` or a function with its signature (A7: the delayed future-time formulation). When
      it is ``run_offline`` the detector calls ``run_offline_detailed`` instead, which gives the same records and the
      counters of the run.
    * ``rank(alerts, records_by_instance_key)``: the order of the alerts (A3 ranks without the normalisation).
    """

    calibrator_factory: Callable[[], ConformalCalibrator] = SplitConformal
    use_forecaster: bool = True
    plan_transform: Callable[[CarePlan], CarePlan] = _identity_plan
    evidence_transform: Callable[[EvidenceMap, int], EvidenceMap] = _identity_evidence
    verdict_runner: Callable[..., Sequence[VerdictRecord]] = run_offline
    rank: Callable[[Sequence[Alert], Mapping[str, VerdictRecord]], Sequence[Alert]] = (
        _default_rank
    )


class CompositeForecaster:
    """One forecaster made of several that support disjoint signals (for example a deadline forecaster for ``meas`` and a
    persistence forecaster for the continuous signals), so that the monitor predicts every instance that has a path.

    ``model_version`` is the concatenation of the parts' versions and changes whenever one of them does; ``fit`` fits every
    part; ``predict`` routes by ``signal``.
    """

    name = "composite"

    def __init__(self, parts: Sequence[Forecaster]) -> None:
        if not parts:
            raise ValueError("a composite forecaster needs at least one part")
        seen: set[str] = set()
        for part in parts:
            overlap = seen & set(part.supported_signals)
            if overlap:
                raise ValueError(
                    f"two parts support the same signal: {sorted(overlap)}"
                )
            seen |= set(part.supported_signals)
        self._parts = tuple(parts)
        self.supported_signals: frozenset[str] = frozenset(seen)

    @property
    def model_version(self) -> str:
        return "+".join(p.model_version for p in self._parts)

    def fit(self, train_days: Sequence[Any]) -> None:
        for part in self._parts:
            part.fit(train_days)

    def predict(
        self,
        history: Sequence[Sample],
        t_ms: TimeMs,
        horizon_ms: DurationMs,
        *,
        signal: str | None = None,
    ) -> Forecast:
        if signal is not None:
            for part in self._parts:
                if signal in part.supported_signals:
                    return part.predict(history, t_ms, horizon_ms, signal=signal)  # type: ignore[call-arg]
            raise UnsupportedSignalError(f"no part supports {signal!r}")
        for part in self._parts:
            try:
                return part.predict(history, t_ms, horizon_ms)
            except UnsupportedSignalError:
                continue
        raise UnsupportedSignalError(
            "no part can forecast the signals present in history"
        )


@dataclass(frozen=True, slots=True)
class PredictionOutcome:
    """A predicted instance: its confidence and what the measured trace decided (E7).

    ``outcome`` is True when the instance ended VIOLATED, False when it ended SATISFIED and None when it was still
    undecided at the end of the run (it is left out of the calibration statistics and counted).
    """

    instance_key: str
    rho: float | None
    alpha: float | None
    outcome: bool | None


@dataclass(frozen=True, slots=True)
class OursRunDetails:
    """What the last ``OursDetector.run`` produced besides the alerts (module docstring)."""

    patient_id: str
    day_index: int
    records: tuple[VerdictRecord, ...]
    alerts: tuple[Alert, ...]
    alpha_total: float | None
    n_tests: int
    per_test_alpha: float | None
    presence_samples_without_availability_marks: int | None
    prediction_skips: tuple[tuple[str, int], ...]
    rejected_inputs: tuple[RejectedInput, ...]
    latencies_ms: tuple[float, ...]
    predictions: tuple[PredictionOutcome, ...]
    episodes: tuple[CalibrationEpisode, ...]
    n_censored: int
    stats: MonitorStats | None
    #: the evidence vector of each violation-claiming instance, as the attribution rule read it (after ``evidence_transform``)
    evidence: Mapping[str, EvidenceVector] = field(default_factory=dict)


SENSITIVITY_LABEL: Final = "sensitivity, not a proposal"
POPULATIONS: Final[tuple[str, ...]] = ("main", "pairs")


@dataclass(frozen=True, slots=True)
class LikelihoodSpec:
    """The wiring of the likelihood attributor of ADR-074 into ``OursDetector`` (WS08-T10). No number has a default.

    * ``table_path``: ``configs/attribution_likelihood.yaml``.
    * ``sensitivity_values``: a labelled sensitivity value for each awaiting row the run reads (``LikelihoodRule``), plus the
      ``cumulative_level`` of the set that is used until a set calibrator is installed. They are sensitivity values, not proposals.
    * ``diagnostics_profile``: ``without_diagnostics`` or ``driver_with_diagnostics`` (the profile of the benchmark; no default).
    * ``grouped_variant``: None for the reference declared in the file.
    * ``set_alpha``: the miscoverage target of the calibrated set (None: the set is always the cumulative-level set).
    * ``set_mode`` / ``min_cell_size``: ``marginal`` or ``mondrian`` and the optional minimum size of a Mondrian cell.
    """

    table_path: str | Path
    sensitivity_values: Mapping[str, object]
    diagnostics_profile: str
    grouped_variant: str | None = None
    set_alpha: float | Fraction | None = None
    set_mode: str = "marginal"
    min_cell_size: int | None = None

    def __post_init__(self) -> None:
        if self.set_mode not in ("marginal", "mondrian"):
            raise ValueError(
                f"set_mode must be 'marginal' or 'mondrian', got {self.set_mode!r}"
            )
        alpha = self.set_alpha
        if alpha is not None and (
            isinstance(alpha, bool)
            or not isinstance(alpha, (int, float, Fraction))
            or not 0 < alpha < 1
        ):
            raise ValueError(f"set_alpha must be None or in (0, 1), got {alpha!r}")


class _SetState:
    """The set calibrators and the counters of the sets issued, shared by a detector and its ``at_alpha`` siblings (the posterior
    does not depend on the monitor level, so one calibration serves the whole alpha grid)."""

    def __init__(self) -> None:
        self.calibrators: dict[str, SubtypeSetCalibrator] = {}
        self.population = "main"
        self.patient = ""
        self.issued: dict[tuple[str, str], Counter[str]] = {}

    def count(self, population: str, template: str, *flags: str) -> None:
        tally = self.issued.setdefault((population, template), Counter())
        tally["n"] += 1
        for flag in flags:
            tally[flag] += 1


class OursDetector:
    """The proposed method (the Runtime Safety Monitor with its forecaster, conformal calibrator and attribution layer)."""

    def __init__(
        self,
        config: MonitorConfig,
        registry: ParameterRegistry,
        templates: Sequence[Template],
        *,
        name: str = "ours",
        components: PipelineComponents | None = None,
        forecaster_factory: Callable[[], Forecaster] | None = None,
        plan_for_day: Callable[[ObservedDay], CarePlan] | None = None,
        profile: object | None = None,
        seed: int = 0,
        collect_episodes: bool = False,
        likelihood: LikelihoodSpec | None = None,
        a4: bool = False,
    ) -> None:
        self.name = name
        self._components = (
            components if components is not None else PipelineComponents()
        )
        self._config = config
        self._registry = registry
        self._templates = tuple(templates)
        self._forecaster_factory = forecaster_factory
        self._plan_for_day = plan_for_day
        self._profile = profile
        self._seed = seed
        self._collect = collect_episodes
        self._forecaster: Forecaster | None = None
        self._calibrator: ConformalCalibrator | None = None
        self._forks: dict[str, ConformalCalibrator] = {}
        self._episodes: tuple[CalibrationEpisode, ...] = ()
        self._n_censored = 0
        self._fitted = False
        self.last_run: OursRunDetails | None = None
        self._likelihood = likelihood
        self._a4 = bool(a4)
        self._set_state = _SetState()
        self._store: dict[tuple[str, str, int], tuple[Any, EvidenceVector, str]] = {}
        self._fallback_level: object = None
        self._rule: LikelihoodRule | None = (
            None if likelihood is None else self._build_rule(likelihood)
        )
        if self._predictive:
            if forecaster_factory is None or plan_for_day is None:
                raise ValueError(
                    "a predictive OursDetector needs a forecaster_factory and a plan_for_day "
                    "(the care plans of the calibration days, ADR-062)"
                )
            if config.alpha is None:
                raise ValueError("a predictive OursDetector needs config.alpha")

    # -- read-only views ----------------------------------------------------------------------------------------

    @property
    def _predictive(self) -> bool:
        return self._components.use_forecaster and self._config.predictive

    @property
    def components(self) -> PipelineComponents:
        return self._components

    @property
    def config(self) -> MonitorConfig:
        return self._config

    @property
    def registry(self) -> ParameterRegistry:
        return self._registry

    @property
    def templates(self) -> tuple[Template, ...]:
        return self._templates

    @property
    def forecaster(self) -> Forecaster | None:
        return self._forecaster

    @property
    def calibrator(self) -> ConformalCalibrator | None:
        return self._calibrator

    @property
    def seed(self) -> int:
        return self._seed

    @property
    def n_calibration_episodes(self) -> int:
        return len(self._episodes)

    @property
    def n_censored_calibration(self) -> int:
        return self._n_censored

    @property
    def calibration_episodes(self) -> tuple[CalibrationEpisode, ...]:
        return self._episodes

    @property
    def is_predictive(self) -> bool:
        return self._predictive

    # -- the attribution rule (WS08-T10) --------------------------------------------------------------------------

    @property
    def likelihood_rule(self) -> LikelihoodRule | None:
        """The ``LikelihoodRule`` of the run, None for ``ours-hier`` (the pair quantities of the runner need it)."""
        return self._rule

    @property
    def alert_inputs(self) -> Callable[[str, Alert], AlertInputs | None] | None:
        """The hook of the scoring side, ``(patient_id, alert) -> AlertInputs | None``; None without a likelihood rule."""
        return None if self._rule is None else self._alert_inputs

    @property
    def is_a4(self) -> bool:
        return self._a4

    @property
    def set_alpha(self) -> float | Fraction | None:
        return None if self._likelihood is None else self._likelihood.set_alpha

    def _build_rule(self, spec: LikelihoodSpec) -> LikelihoodRule:
        values = dict(spec.sensitivity_values)
        level = values.get("cumulative_level")
        if level is None:
            raise AwaitingValueError(
                ["cumulative_level"],
                "cumulative_level is an awaiting_human_value: the set of an alert before a set calibrator is fitted is the "
                "cumulative-level set, and the level must be supplied as a labelled sensitivity value (run option "
                "sensitivity_values)",
            )
        table = load_likelihood_table(Path(spec.table_path))
        rule = LikelihoodRule(
            self._registry,
            table,
            sensitivity_values=values,
            diagnostics_profile=spec.diagnostics_profile,
            grouped_variant=spec.grouped_variant,
            a4=self._a4,
            needs_cumulative_level=False,
        )
        self._fallback_level = level
        return rule

    def _select(
        self, posteriors: Mapping[str, float], template: Any, instance_key: str
    ) -> Sequence[str]:
        """The injected ``set_selector``: the conformal set of the calibrator of the population in use, else the cumulative-level set."""
        assert self._rule is not None and self._likelihood is not None
        state = self._set_state
        population, name = state.population, str(template.value).lower()
        calibrator = state.calibrators.get(population)
        alpha = self._likelihood.set_alpha
        if calibrator is None or alpha is None:
            state.count(population, name, "cumulative_fallback")
            return cumulative_level_set(posteriors, self._fallback_level)  # type: ignore[arg-type]
        got = calibrator.predict_set(
            posteriors,
            name,
            alpha,
            patient_id=state.patient,
            model_version=self._rule.model_version,
        )
        state.count(
            population,
            name,
            *(["full_set_fallback"] if got.full_set_fallback else []),
            *(["top1_fill"] if got.top1_fill else []),
        )
        return got.subtypes

    @staticmethod
    def _check_population(population: str) -> None:
        if population not in POPULATIONS:
            raise ValueError(
                f"population must be one of {list(POPULATIONS)}, got {population!r}"
            )

    def set_calibrator(self, population: str = "main") -> SubtypeSetCalibrator | None:
        self._check_population(population)
        return self._set_state.calibrators.get(population)

    def fit_set_calibrator(
        self,
        alerts: Sequence[SubtypeCalibrationAlert],
        *,
        test_patient_ids: Collection[str],
        population: str = "main",
    ) -> SubtypeSetCalibrator:
        """Fit and install the set calibrator of ``population`` on calibration alerts that the SCORING side labelled.

        The detector never sees the true subtype: ``alerts`` are built by the caller from the posteriors of the calibration part
        (``alert_inputs``) and the labelled truth. ``test_patient_ids`` are the patients the sets will be issued for; a patient in
        both parts raises ``PatientLeakError``. The calibrator carries the model-version token of the rule. The ``pairs`` population is a
        separate instance, fitted on the calibration part of the pair population.
        """
        if self._rule is None or self._likelihood is None:
            raise RuntimeError(
                "fit_set_calibrator needs a likelihood rule (ours-hier has no sets)"
            )
        if self._likelihood.set_alpha is None:
            raise ValueError(
                "no set_alpha is configured: a calibrated set needs the miscoverage target of the run"
            )
        self._check_population(population)
        calibrator = SubtypeSetCalibrator(
            self._likelihood.set_mode,  # type: ignore[arg-type]
            population=population,
            min_cell_size=self._likelihood.min_cell_size,
        )
        calibrator.fit(
            alerts,
            model_version=self._rule.model_version,
            test_patient_ids=test_patient_ids,
        )
        self._set_state.calibrators[population] = calibrator
        return calibrator

    def install_set_calibrator(
        self, calibrator: SubtypeSetCalibrator, *, population: str = "main"
    ) -> None:
        """Install a fitted calibrator; ``StaleSetCalibratorError`` if it was not fitted for this rule's model version."""
        if self._rule is None:
            raise RuntimeError("install_set_calibrator needs a likelihood rule")
        self._check_population(population)
        if calibrator.population != population:
            raise ValueError(
                f"the calibrator is for the population {calibrator.population!r}, not {population!r}"
            )
        calibrator.check_fresh(self._rule.model_version)
        self._set_state.calibrators[population] = calibrator

    @contextmanager
    def using_population(self, population: str) -> Iterator[None]:
        """Issue the sets of the runs inside the block with the calibrator of ``population`` (``pairs``: the separate instance)."""
        self._check_population(population)
        state = self._set_state
        before = state.population
        state.population = population
        try:
            yield
        finally:
            state.population = before

    def reset_set_counts(self) -> None:
        self._set_state.issued.clear()

    def set_selector_metadata(self) -> dict[str, Any]:
        """JSON-ready account of the sets: the mode and target, the declared fallback level, per population the calibration and its
        thresholds (``inf`` written as null with the ``fallback`` flag), the sets issued with their fallback and fill counts per
        template, and the guarantee strings as the set builder states them."""
        if self._rule is None or self._likelihood is None:
            raise RuntimeError("an ours-hier detector has no set selector")
        spec, state = self._likelihood, self._set_state
        alpha = spec.set_alpha
        populations: dict[str, Any] = {}
        for name, calibrator in sorted(state.calibrators.items()):
            thresholds: dict[str, Any] = {}
            if alpha is not None:
                cells = (
                    sorted(calibrator.cell_sizes())
                    if calibrator.mode == "mondrian"
                    else ["all"]
                )
                for cell in cells:
                    thresholds[cell] = threshold_json(
                        calibrator.threshold("range" if cell == "all" else cell, alpha)
                    )
            populations[name] = {
                "mode": calibrator.mode,
                "n_calibration": calibrator.n_calibration,
                "n_patients": len(calibrator.calibration_patients),
                "model_version": calibrator.calibrated_for,
                "cell_sizes": dict(sorted(calibrator.cell_sizes().items())),
                "thresholds": thresholds,
                "guarantee": GUARANTEE_SETS
                if calibrator.mode == "marginal"
                else GUARANTEE_SETS_MONDRIAN,
                "assumptions": list(ASSUMPTIONS_SETS),
            }
        issued: dict[str, dict[str, Any]] = {}
        for (population, template), tally in sorted(state.issued.items()):
            issued.setdefault(population, {})[template] = {
                "n": tally["n"],
                "full_set_fallback": tally["full_set_fallback"],
                "top1_fill": tally["top1_fill"],
                "cumulative_fallback": tally["cumulative_fallback"],
            }
        return {
            "mode": spec.set_mode,
            "set_alpha": None if alpha is None else alpha_key(alpha),
            "min_cell_size": spec.min_cell_size,
            "fallback_level": {
                "value": self._fallback_level,
                "label": SENSITIVITY_LABEL,
            },
            "model_version": self._rule.model_version,
            "populations": populations,
            "sets_issued": issued,
            "note": (
                "a population without a calibrator issues the cumulative-level set (cumulative_fallback); the pairs never borrow the "
                "main calibrator. sets_issued aggregates over every run of this detector and of its at_alpha siblings (they share the "
                "calibrators and the counters), the calibration-patient runs excluded: a patient-day run for each alpha of the grid "
                "counts, so read the shares, not the totals"
            ),
        }

    def _alert_inputs(self, patient_id: str, alert: Alert) -> AlertInputs | None:
        assert self._rule is not None
        entry = self._store.get((patient_id, alert.xi.instance_key, alert.t_ms))
        if entry is None or alert.verdict is not VerdictState.VIOLATED:
            return None
        record, evidence, kappa = entry
        return alert_inputs_from_rule(
            self._rule, record, evidence, hierarchical_kappa=kappa
        )

    def at_alpha(self, alpha: float) -> OursDetector:
        """A sibling at another total level that shares the fitted forecaster and the calibration episodes.

        The split calibrator is level-agnostic (only the level given to ``predict`` changes), so it is shared. An adaptive
        calibrator takes its target level from ``fit``, so the sibling gets a new one fitted on the same episodes at the
        new level. Adaptive per-patient forks are never shared.
        """
        if not self._fitted:
            raise RuntimeError("at_alpha needs a fitted detector")
        other = copy.copy(self)
        other._config = (
            replace(self._config, alpha=alpha) if self._predictive else self._config
        )
        other._forks = {}
        other.last_run = None
        calibrator = self._calibrator
        if (
            calibrator is not None
            and calibrator.mode == "adaptive"
            and self._forecaster is not None
        ):
            fresh = self._components.calibrator_factory()
            fresh.fit(
                self._episodes, alpha, model_version=self._forecaster.model_version
            )
            other._calibrator = fresh
        return other

    # -- fit ----------------------------------------------------------------------------------------------------

    def fit(
        self, train_days: Sequence[BenchmarkDay], calib_days: Sequence[BenchmarkDay]
    ) -> None:
        train = [
            self._observed(d, f"train_days[{i}]") for i, d in enumerate(train_days)
        ]
        calib = [
            self._observed(d, f"calib_days[{i}]") for i, d in enumerate(calib_days)
        ]
        self._fitted = False
        self._forks = {}
        self._episodes = ()
        self._n_censored = 0
        self._forecaster = None
        self._calibrator = None
        self._store.clear()
        self._set_state.calibrators.clear()
        self._set_state.issued.clear()
        if self._predictive:
            assert (
                self._forecaster_factory is not None and self._plan_for_day is not None
            )
            assert self._config.alpha is not None
            forecaster = self._forecaster_factory()
            forecaster.fit(train)
            plans = [
                self._components.plan_transform(self._plan_for_day(d)) for d in calib
            ]
            episodes, censored = build_calibration_episodes(
                calib,
                plans,
                self._config,
                forecaster,
                registry=self._registry,
                templates=self._templates,
            )
            if not episodes:
                raise ValueError(
                    "the calibration days give no calibration episode: the conformal calibrator cannot be fitted"
                )
            calibrator = self._components.calibrator_factory()
            calibrator.fit(
                episodes, self._config.alpha, model_version=forecaster.model_version
            )
            self._forecaster, self._calibrator = forecaster, calibrator
            self._episodes, self._n_censored = tuple(episodes), censored
        self._fitted = True

    @staticmethod
    def _observed(day: object, what: str) -> ObservedDay:
        if not isinstance(day, BenchmarkDay):
            raise TypeError(f"{what} must be a BenchmarkDay, got {type(day).__name__}")
        return day.observed  # the only member read: the other two are never touched

    # -- run ----------------------------------------------------------------------------------------------------

    def _calibrator_for(self, patient_id: str) -> ConformalCalibrator | None:
        calibrator = self._calibrator
        if calibrator is None or calibrator.mode != "adaptive":
            return calibrator
        fork = getattr(calibrator, "fork", None)
        if not callable(fork):
            return calibrator
        if patient_id not in self._forks:
            self._forks[patient_id] = fork()
        return self._forks[patient_id]

    def run(
        self,
        day: ObservedDay,
        plan: CarePlan,
        evidence: Mapping[str, EvidenceVector] | None = None,
        *,
        history: Sequence[ObservedDay] = (),
    ) -> Sequence[Alert]:
        if not isinstance(day, ObservedDay):
            raise TypeError(
                f"run takes an ObservedDay, got {type(day).__name__}: a detector sees the observed trace only"
            )
        if not self._fitted:
            raise RuntimeError("OursDetector.run was called before fit")
        components = self._components
        the_plan = components.plan_transform(plan)
        cfg = (
            self._config
            if self._predictive
            else replace(self._config, predictive=False, alpha=None)
        )
        calibrator = self._calibrator_for(day.patient_id) if self._predictive else None
        forecaster = self._forecaster if self._predictive else None
        runner = components.verdict_runner
        stats: MonitorStats | None = None
        rejected: tuple[RejectedInput, ...] = ()
        kwargs: dict[str, Any] = {
            "registry": self._registry,
            "templates": self._templates,
        }
        if history:
            kwargs["history"] = tuple(history)
        if runner is run_offline:
            result = run_offline_detailed(
                day, the_plan, cfg, calibrator, forecaster, **kwargs
            )
            records = tuple(result.records)
            stats, rejected = result.stats, tuple(result.rejected_inputs)
        else:
            records = tuple(
                runner(day, the_plan, cfg, calibrator, forecaster, **kwargs)
            )
        extracted = (
            evidence
            if evidence is not None
            else extract_evidence(
                day,
                records,
                self._registry,
                step_ms=cfg.step_ms,
                reorder_delay_ms=cfg.reorder_delay_ms,
                profile=self._profile,  # type: ignore[arg-type]
                plan=the_plan,
                exclude_robot=self._a4,
            )
        )
        used = components.evidence_transform(extracted, self._seed)
        self._set_state.patient = day.patient_id
        attributor = self._attributor(the_plan, cfg.variant)
        violated = [
            a
            for a in attributor.attribute_all(records, used)
            if a.verdict is VerdictState.VIOLATED
        ]
        first_predicted: dict[str, VerdictRecord] = {}
        for record in records:
            if record.state is VerdictState.PREDICTED_VIOLATION:
                first_predicted.setdefault(record.instance_key, record)
        predicted = list(
            self._attributor(the_plan, cfg.variant).attribute_all(
                list(first_predicted.values()), used
            )
        )
        alerts = [*violated, *predicted]
        if self._rule is not None:
            self._remember(
                day.patient_id, records, used, violated, the_plan, cfg.variant
            )
        by_key: dict[str, VerdictRecord] = {}
        for record in records:
            held = by_key.get(record.instance_key)
            if held is None or (
                held.state is not VerdictState.VIOLATED
                and record.state is VerdictState.VIOLATED
            ):
                by_key[record.instance_key] = record
        ranked = tuple(components.rank(alerts, by_key))
        episodes: tuple[CalibrationEpisode, ...] = ()
        n_censored = 0
        adaptive = calibrator is not None and calibrator.mode == "adaptive"
        if self._predictive and forecaster is not None and (self._collect or adaptive):
            plan_list = [the_plan]
            built, n_censored = build_calibration_episodes(
                [day],
                plan_list,
                cfg,
                forecaster,
                registry=self._registry,
                templates=self._templates,
            )
            episodes = tuple(built)
            if adaptive:
                assert calibrator is not None
                for episode in episodes:  # after the day is complete: no episode is updated before its deadline
                    calibrator.update(episode.sigma_hat, episode.sigma_true)
        self.last_run = OursRunDetails(
            day.patient_id,
            day.day_index,
            records,
            ranked,
            cfg.alpha if self._predictive else None,
            0 if stats is None else stats.n_tests,
            None if stats is None else stats.per_test_alpha,
            None
            if stats is None
            else stats.presence_samples_without_availability_marks,
            () if stats is None else stats.prediction_skips,
            rejected,
            self._latencies(records, cfg.reorder_delay_ms),
            self._outcomes(records, first_predicted),
            episodes,
            n_censored,
            stats,
            used,
        )
        return ranked

    def _attributor(self, plan: CarePlan, variant: str | None) -> RuleAttributor:
        """The attributor of a run: the likelihood rule with this detector's set selector, or the hierarchical rule."""
        if self._rule is None:
            return RuleAttributor(
                self._registry, self._templates, plan=plan, variant=variant
            )
        return RuleAttributor(
            self._registry,
            self._templates,
            self._rule,
            plan=plan,
            variant=variant,
            set_selector=self._select,
        )

    def _remember(
        self,
        patient_id: str,
        records: Sequence[VerdictRecord],
        used: Mapping[str, EvidenceVector],
        violated: Sequence[Alert],
        plan: CarePlan,
        variant: str | None,
    ) -> None:
        """Keep, per VIOLATED alert, the record and the evidence vector the rule read and the hierarchical rule's kappa, for
        ``alert_inputs``. A cascade effect carries the posterior of its root, so it points to the root's entry."""
        first: dict[str, VerdictRecord] = {}
        for record in records:
            if record.state is VerdictState.VIOLATED:
                held = first.get(record.instance_key)
                if held is None or record.t_eval_ms < held.t_eval_ms:
                    first[record.instance_key] = record
        hier = {
            a.xi.instance_key: str(getattr(a.kappa, "value", a.kappa))
            for a in RuleAttributor(
                self._registry, self._templates, plan=plan, variant=variant
            ).attribute_all(records, used)
            if a.verdict is VerdictState.VIOLATED
        }
        for alert in violated:
            key = alert.xi.instance_key
            root = alert.caused_by if alert.caused_by in first else key
            source = first.get(root)
            if source is None:
                continue
            vector = used.get(root)
            evidence = vector if vector is not None else empty_evidence(source.template)
            self._store[(patient_id, key, alert.t_ms)] = (
                source,
                evidence,
                hier.get(root, "UNDETERMINED"),
            )

    @staticmethod
    def _latencies(
        records: Sequence[VerdictRecord], reorder_delay_ms: DurationMs
    ) -> tuple[float, ...]:
        """Logical verdict latency in trace time: the instant at which the monitor emits the first VIOLATED record of an
        instance (``t_eval_ms + reorder_delay_ms``) minus the instant at which it became decidable."""
        seen: set[str] = set()
        out: list[float] = []
        for record in records:
            if (
                record.state is VerdictState.VIOLATED
                and record.instance_key not in seen
            ):
                seen.add(record.instance_key)
                decided = (
                    record.decided_at_ms
                    if record.decided_at_ms is not None
                    else record.t_eval_ms
                )
                out.append(float(record.t_eval_ms + reorder_delay_ms - decided))
        return tuple(out)

    @staticmethod
    def _outcomes(
        records: Sequence[VerdictRecord], first_predicted: Mapping[str, VerdictRecord]
    ) -> tuple[PredictionOutcome, ...]:
        final: dict[str, bool | None] = {}
        for record in records:
            if record.instance_key not in first_predicted:
                continue
            if record.state is VerdictState.VIOLATED:
                final[record.instance_key] = True
            elif (
                record.state is VerdictState.SATISFIED
                and final.get(record.instance_key) is not True
            ):
                final[record.instance_key] = False
        out: list[PredictionOutcome] = []
        for key, record in first_predicted.items():
            rho = record.rho
            out.append(
                PredictionOutcome(
                    key,
                    None if rho is None else rho.value,
                    None if rho is None else rho.alpha,
                    final.get(key),
                )
            )
        return tuple(out)
