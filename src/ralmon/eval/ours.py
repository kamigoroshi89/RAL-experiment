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

Diagnostics. After each ``run`` the detector exposes ``last_run`` (``OursRunDetails``): the verdict records, the alerts,
the counters of the monitor (``n_tests``, ``per_test_alpha``, the INT gate of ADR-054, the rejected inputs), the
logical verdict latencies and the outcome of every predicted instance. The runner reads it for the metrics that need more
than ``Detection``s (coverage, calibration of rho, latency).
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from ralmon.attribution import (
    Alert,
    EvidenceVector,
    RuleAttributor,
    extract_evidence,
)
from ralmon.benchmark import BenchmarkDay, ObservedDay
from ralmon.conformal import CalibrationEpisode, ConformalCalibrator, SplitConformal
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
    presence_samples_without_availability_marks: int
    prediction_skips: tuple[tuple[str, int], ...]
    rejected_inputs: tuple[RejectedInput, ...]
    latencies_ms: tuple[float, ...]
    predictions: tuple[PredictionOutcome, ...]
    episodes: tuple[CalibrationEpisode, ...]
    n_censored: int
    stats: MonitorStats | None


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

    def at_alpha(self, alpha: float) -> OursDetector:
        """A sibling at another total level that shares the fitted forecaster and calibrator (the calibrator is
        level-agnostic: only the level given to ``predict`` changes). Adaptive per-patient forks are not shared."""
        if not self._fitted:
            raise RuntimeError("at_alpha needs a fitted detector")
        other = copy.copy(self)
        other._config = (
            replace(self._config, alpha=alpha) if self._predictive else self._config
        )
        other._forks = {}
        other.last_run = None
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
            )
        )
        used = components.evidence_transform(extracted, self._seed)
        attributor = RuleAttributor(
            self._registry, self._templates, plan=the_plan, variant=cfg.variant
        )
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
            RuleAttributor(
                self._registry, self._templates, plan=the_plan, variant=cfg.variant
            ).attribute_all(list(first_predicted.values()), used)
        )
        alerts = [*violated, *predicted]
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
            0 if stats is None else stats.presence_samples_without_availability_marks,
            () if stats is None else stats.prediction_skips,
            rejected,
            self._latencies(records, cfg.reorder_delay_ms),
            self._outcomes(records, first_predicted),
            episodes,
            n_censored,
            stats,
        )
        return ranked

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
