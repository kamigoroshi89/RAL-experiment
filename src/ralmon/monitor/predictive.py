"""The predictive step of the monitor (WS05-T08, ADR-060): early warning in the PENDING state, nothing else.

What it does. When an instance with a predictive path is created (a SCHED instance of the plan, a RESP instance
at a dispense) and its record at the activation step is PENDING, the step asks the forecaster for the future of
the signal that the instance still needs, completes the trace with that path, evaluates the body of the instance
with the point evaluator, normalises with the scale of the template and asks the conformal calibrator whether
``sigma_hat + q`` is negative. If it is, the instance goes PENDING to PREDICTED_VIOLATION with the confidence of
the calibrator and the bound ``clip(sigma_hat + q, -1, 1)``. That is the whole effect (docs/formal/05 section 5,
rules P1 to P6): the interval, ``decided_at_ms`` and the definitive verdict are those of the measured prefix, the
forecast never produces VIOLATED or SATISFIED (ADR-008, Lemma 9), and a removed forecaster changes no definitive
record (ablation A2).

One prediction per instance, at its activation step (WS05 decision D6, ADR-060). Every episode is then predicted
at the same lead, so the calibration episodes are exchangeable, and the number of tests of a patient-day is known
when the plan is loaded, so the level is allocated over them by the union bound: ``MonitorConfig.alpha`` is the
total level of a patient-day, the per-test level is ``alpha / n_tests`` (``BonferroniAllocation``, passed to the
calibrator as an exact fraction). Re-predicting as the robot estimate improves would be a different test at each
lead time and needs a calibration per lead time; it is not done.

Predictive path. SCHED needs a forecast of ``meas`` (the arrival of the measurement), RESP a forecast of ``bp``
(the measurements themselves come from the schedule of the plan: the measurement ticks are the anchors of the
SCHED instances, and the other ticks of ``CarePlan.schedule`` are dispense ticks). An instance whose signal is not
in ``Forecaster.supported_signals`` has no predictive path: it is not counted in ``n_tests`` and the step records
the reason. The same holds for a forecaster with no basis (``InsufficientHistoryError``) or a path that cannot be
used; none of this changes a verdict.

Horizon. The time to the deadline of the instance; for a template whose unit is milliseconds the scale of the
template is added, so that an overrun up to the clipping point of the normalisation is representable.

Calibration and deployment share the code path: ``build_calibration_episodes`` runs the same monitor with a
recording hook in place of the calibrator, so the ``sigma_hat`` of an episode is the value the monitor would use.
This module reads only the observed samples and events that the monitor accepted; it knows nothing of the
benchmark generator, its latent trace or its ground truth.
"""

from __future__ import annotations

import inspect
import math
from collections import Counter, deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from fractions import Fraction
from typing import Any, Final

from ralmon.conformal import BonferroniAllocation
from ralmon.monitor.config import (
    T_DAY_MS,
    MonitorConfig,
    MonitorConfigError,
)
from ralmon.monitor.evaluator import _evaluator_from
from ralmon.monitor.forecast import Forecast
from ralmon.monitor.forecasters import InsufficientHistoryError
from ralmon.monitor.instances import EngineContext, Instance
from ralmon.monitor.reorder import is_late, step_of
from ralmon.monitor.verdict import VerdictRecord, VerdictState
from ralmon.signals import Event, EventKind, Sample, SignalId
from ralmon.spec import RobustnessUnit, Template, TemplateId, normalise

__all__ = ["PredictionPoint", "Predictor", "StaleCalibratorError"]


class StaleCalibratorError(Exception):
    """The conformal calibrator was calibrated for another model than the forecaster in use (analisi section 2, R2
    weakness 6), or for no particular model: ``calibrator.calibrated_for != forecaster.model_version``."""


# the reasons of a skipped prediction, as recorded in ``MonitorStats.prediction_skips``
NO_COVERAGE: Final = "no_forecast_coverage"
DECIDED: Final = "decided_at_activation"
BEYOND_PLAN: Final = "resp_beyond_plan"
INSUFFICIENT: Final = "insufficient_history"
INVALID: Final = "invalid_forecast"
UNDEFINED: Final = "undefined_completion"
NO_ALLOCATION: Final = "no_test_allocated"

# the signal that an instance of a template still needs from the forecaster, and the anchor kind of its
# point evaluator (docs/formal/02 section 3.2)
_TARGET: Final[dict[TemplateId, tuple[str, str]]] = {
    TemplateId.SCHED: (SignalId.MEAS.value, "sched_tick"),
    TemplateId.RESP: (SignalId.BP.value, "dispense"),
}
# the signals that a forecaster of ADR-057 reads besides its target: the robot state of the deadline model
_ROBOT_STATE: Final = (SignalId.NAV_ETA.value, SignalId.TASK_QUEUE.value)
_SAMPLE_SIGNALS: Final = frozenset(
    {
        SignalId.BP.value,
        SignalId.HR_ECG.value,
        SignalId.HR_PULSE.value,
        SignalId.SPO2.value,
    }
)
# an impulse of a forecast path is a value of at least this much (the contract writes 1.0 and 0.0)
_IMPULSE: Final = 0.5
_NAN: Final = math.nan


@dataclass(frozen=True, slots=True)
class PredictionPoint:
    """What the recording hook receives at an activation step: the instance and its ``sigma_hat``."""

    template: Template
    key: str
    anchor_ms: int
    k_a: int
    kind: str
    params: Mapping[str, float]
    pre: float
    scale: float
    sigma_hat: float
    ctx: EngineContext


def _accepts_signal(forecaster: Any) -> bool:
    """Whether ``forecaster.predict`` takes the keyword ``signal`` (the concrete classes of ADR-057 do)."""
    try:
        parameters = inspect.signature(forecaster.predict).parameters
    except (TypeError, ValueError):
        return False
    return "signal" in parameters or any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters.values()
    )


class Predictor:
    """The predictive step of one ``StreamingMonitor`` (see the module docstring)."""

    def __init__(
        self,
        *,
        config: MonitorConfig,
        ctx: EngineContext,
        templates: Mapping[TemplateId, Template],
        forecaster: Any,
        calibrator: Any | None,
        recorder: Callable[[PredictionPoint], None] | None = None,
    ) -> None:
        if forecaster is None:
            raise MonitorConfigError("predictive monitoring needs a forecaster")
        for name in ("model_version", "supported_signals", "predict"):
            if not hasattr(forecaster, name):
                raise MonitorConfigError(f"the forecaster has no {name!r}")
        if recorder is None:
            if calibrator is None:
                raise MonitorConfigError("predictive monitoring needs a calibrator")
            for name in ("predict", "quantile", "quantile_lower", "calibrated_for"):
                if not hasattr(calibrator, name):
                    raise MonitorConfigError(f"the calibrator has no {name!r}")
            if config.alpha is None:
                raise MonitorConfigError("predictive monitoring needs alpha")
        self._step = ctx.step_ms
        self._k_day = T_DAY_MS // ctx.step_ms
        self._ctx = ctx
        self._templates = templates
        self._forecaster = forecaster
        self._calibrator = calibrator if recorder is None else None
        self._recorder = recorder
        self._variant = config.variant
        self._alpha = None if config.alpha is None else float(config.alpha)
        self._with_signal = _accepts_signal(forecaster)
        supported = frozenset(forecaster.supported_signals)
        self._supported = supported
        self._keep = (supported & _SAMPLE_SIGNALS) | frozenset(_ROBOT_STATE)
        self._history: deque[Sample] = deque()
        self._measure_steps: frozenset[int] = frozenset()
        self._slots: Counter[int] = Counter()
        self._resp_used: Counter[int] = Counter()
        self._n_tests = 0
        self._level: Fraction | None = None
        self._made = 0
        self._emitted = 0
        self._uninformative = 0
        self._skips: Counter[str] = Counter()
        self.check_fresh()

    # -- the model token --------------------------------------------------------------------------------

    def check_fresh(self) -> None:
        """Refuse a calibrator older than the model (analisi section 2, R2 weakness 6; WS05 decision D10)."""
        if self._calibrator is None:
            return
        calibrated = self._calibrator.calibrated_for
        model = self._forecaster.model_version
        if calibrated is None or calibrated != model:
            raise StaleCalibratorError(
                f"the calibrator was calibrated for {calibrated!r}, the forecaster is {model!r}: "
                "fit the calibrator again on held-out episodes of the current model "
                "(fit(..., model_version=forecaster.model_version))"
            )

    # -- the plan: how many tests, at which level --------------------------------------------------------

    def covers(self, template: TemplateId) -> bool:
        target = _TARGET.get(template)
        return target is not None and target[0] in self._supported

    def on_plan(
        self,
        *,
        schedule: Sequence[int],
        sched_anchors: Sequence[int],
        sched_counted: Sequence[int],
    ) -> None:
        """Fix ``n_tests`` and the per-test level from the plan (WS01-T06 section 6.2).

        ``sched_anchors`` are all the measurement ticks of the plan (the anchors of its SCHED instances),
        ``sched_counted`` the SCHED instances that this run activates. The other ticks of ``schedule`` are
        dispense ticks; each is one RESP test (the instance created at the dispense). ``n_tests`` is the largest
        number of tests of one calendar day: the union bound is per patient-day, so each day is bounded by
        ``alpha`` when ``n_tests`` is that maximum. A tick of a day that the run does not reach is counted as well
        (it can only lower the level).
        """
        per_day: Counter[int] = Counter()
        if self.covers(TemplateId.SCHED):
            for anchor in sched_counted:
                per_day[anchor // T_DAY_MS] += 1
        slots: Counter[int] = Counter()
        if self.covers(TemplateId.RESP):
            remaining = Counter(schedule)
            remaining.subtract(Counter(sched_anchors))
            for tick, count in remaining.items():
                if count > 0:
                    slots[tick // T_DAY_MS] += count
        for day, count in slots.items():
            per_day[day] += count
        self._slots = slots  # the slots used so far are kept: a new version of the plan restarts nothing
        self._measure_steps = frozenset(step_of(a, self._step) for a in sched_anchors)
        self._n_tests = max(per_day.values(), default=0)
        if self._alpha is not None and self._n_tests >= 1:
            self._level = BonferroniAllocation().per_test_exact(
                self._alpha, self._n_tests
            )
        else:
            self._level = None

    # -- the released history -----------------------------------------------------------------------------

    def observe(self, sample: Sample) -> None:
        """Keep a released sample of a signal that a forecaster reads (device-time order, one day back)."""
        if sample.signal in self._keep:
            self._history.append(sample)

    def trim(self, t_ms: int) -> None:
        horizon = t_ms - T_DAY_MS
        history = self._history
        while history and history[0].t_device_ms < horizon:
            history.popleft()

    # -- one prediction ------------------------------------------------------------------------------------

    def counters(self) -> dict[str, Any]:
        return {
            "n_tests": self._n_tests,
            "per_test_alpha": None if self._level is None else float(self._level),
            "predictions_made": self._made,
            "predictions_emitted": self._emitted,
            "predictions_uninformative": self._uninformative,
            "prediction_skips": tuple(sorted(self._skips.items())),
        }

    def _skip(self, reason: str) -> None:
        self._skips[reason] += 1

    def _forecast(self, signal: str, t_ms: int, horizon_ms: int) -> Forecast | None:
        history: list[Sample] = list(self._history)
        try:
            if self._with_signal:
                return self._forecaster.predict(  # type: ignore[no-any-return]
                    history, t_ms, horizon_ms, signal=signal
                )
            # without the keyword the target is the single supported signal present: drop the others
            clean = [
                s
                for s in history
                if s.signal == signal or s.signal not in self._supported
            ]
            return self._forecaster.predict(clean, t_ms, horizon_ms)  # type: ignore[no-any-return]
        except InsufficientHistoryError:
            self._skip(INSUFFICIENT)
            return None

    def _path(
        self, forecast: Any, signal: str, t_ms: int, horizon_ms: int
    ) -> list[float] | None:
        """The path of a forecast if it is the one that was asked for, else ``None`` (counted)."""
        n = horizon_ms // self._step
        try:
            ok = (
                forecast.signal == signal
                and forecast.t_from_ms == t_ms
                and len(forecast.mean) == n
            )
            values = [float(v) for v in forecast.mean] if ok else []
        except (AttributeError, TypeError, ValueError, OverflowError):
            ok = False
            values = []
        if not ok or not all(math.isfinite(v) for v in values):
            self._skip(INVALID)
            return None
        return values

    def test(
        self, instance: Instance, record: VerdictRecord, k: int, bp_now: float
    ) -> VerdictRecord | None:
        """The one prediction of an instance at its activation step ``k``; the PREDICTED record or ``None``.

        ``record`` is the PENDING-or-definitive record that the instance has just emitted at ``k`` and
        ``bp_now`` the held pressure at ``k`` (NaN if undefined).
        """
        template = instance.template
        tid = template.id
        signal, kind = _TARGET[tid]
        if signal not in self._supported:
            self._skip(NO_COVERAGE)
            return None
        if tid is TemplateId.RESP:
            day = k // self._k_day
            if self._resp_used[day] >= self._slots[day]:
                self._skip(BEYOND_PLAN)
                return None
            self._resp_used[day] += 1
        if record.state is not VerdictState.PENDING:
            self._skip(DECIDED)
            return None
        if self._recorder is None and self._level is None:
            self._skip(NO_ALLOCATION)
            return None
        t_ms = k * self._step
        horizon_ms = (instance.k_d - k) * self._step
        if template.unit is RobustnessUnit.MS:
            horizon_ms += int(instance.scale)
        forecast = self._forecast(signal, t_ms, horizon_ms)
        if forecast is None:
            return None
        path = self._path(forecast, signal, t_ms, horizon_ms)
        if path is None:
            return None
        pre = getattr(instance, "pre", _NAN)
        raw = self._complete(
            instance, kind, k, bp_now, pre, path, horizon_ms // self._step
        )
        if raw is None:
            self._skip(UNDEFINED)
            return None
        low, high = record.sigma_norm_interval
        sigma_hat = min(
            max(normalise(raw, instance.scale), low), high
        )  # P4: inside the record
        if self._recorder is not None:
            self._recorder(
                PredictionPoint(
                    template,
                    instance.key,
                    instance.anchor_ms,
                    instance.k_a,
                    kind,
                    instance.params,
                    pre,
                    instance.scale,
                    sigma_hat,
                    self._ctx,
                )
            )
            self._made += 1
            return None
        assert self._calibrator is not None and self._level is not None
        verdict = self._calibrator.predict(
            sigma_hat, self._level, variant=self._variant
        )
        self._made += 1
        if not verdict.emitted or verdict.rho is None:
            return None
        quantile = (
            self._calibrator.quantile(self._level)
            if self._variant == "likely"
            else self._calibrator.quantile_lower(self._level)
        )
        bound = normalise(sigma_hat + quantile, 1.0)
        instance.mark_predicted(verdict.rho, bound)
        self._emitted += 1
        if verdict.rho.value == 0.0:
            self._uninformative += (
                1  # a level below 1 / (n + 1) in the variant "possible": no information
            )
        return replace(
            record,
            state=VerdictState.PREDICTED_VIOLATION,
            rho=verdict.rho,
            predicted_sigma_norm=bound,
        )

    def _complete(
        self,
        instance: Instance,
        kind: str,
        k: int,
        bp_now: float,
        pre: float,
        path: list[float],
        n_steps: int,
    ) -> float | None:
        """The raw robustness of the instance on the completed trace, ``None`` if it is undefined.

        The measured prefix is the state of the instance at its activation step; the unknown future is the
        forecast for the signal of the instance and the schedule of the plan for the measurements (SCHED: the
        forecast arrival is the measurement; RESP: a measurement at each measurement tick of the plan, with the
        forecast pressure at that tick). The physiological bounds are not used here.
        """
        evaluator = _evaluator_from(
            instance.template,
            instance.anchor_ms,
            kind,
            instance.params,
            self._ctx,
            k,
        )
        step = self._step
        value: float | None = None
        if instance.template.id is TemplateId.SCHED:
            arrival = next((i for i, v in enumerate(path) if v >= _IMPULSE), None)
            arrival_step = None if arrival is None else k + 1 + arrival
            for kk in range(k, k + n_steps + 1):
                row: dict[str, float | None] = {}
                if kk == arrival_step:
                    row["meas"] = 1.0
                value = evaluator.step(kk * step, row)
            return value
        for kk in range(k, k + n_steps + 1):
            row = {}
            if kk == k:
                if not math.isnan(bp_now):
                    row["bp"] = bp_now
                row["bp_pre"] = pre
            else:
                row["bp"] = path[kk - k - 1]
                if kk in self._measure_steps:
                    row["meas"] = 1.0
            value = evaluator.step(kk * step, row)
        return value


def _observed_sigma_true(
    point: PredictionPoint,
    samples: Sequence[Sample],
    events: Sequence[Event],
    *,
    reorder_delay_ms: int,
    last_step: int,
) -> float | None:
    """``sigma_true`` of a predicted instance on the complete observed day, or ``None`` if it is not decided.

    The completed trace is the accepted observed inputs of the day from the activation step to ``last_step``
    (an input that the monitor would have excluded as late is excluded here too, so the completed trace is the
    one the measured verdict will rest on): the measurement events and the held pressure. The value is the
    normalised robustness of the instance by the point evaluator, so a late measurement counts as in G-SCHED-3.
    ``None`` when the decision step of the instance lies after ``last_step`` (the window closes after the end of
    the day) or an open position keeps the value undefined (a pre-dose pressure that was never measured).
    """
    ctx = point.ctx
    step = ctx.step_ms
    meas: Counter[int] = Counter()
    for event in events:
        if event.kind is EventKind.MEASUREMENT and not is_late(
            event.t_device_ms, event.t_rx_ms, step, reorder_delay_ms
        ):
            meas[step_of(event.t_device_ms, step)] += 1
    pressures = sorted(
        (
            (s.t_device_ms, s.value)
            for s in samples
            if s.signal == SignalId.BP.value
            and not is_late(s.t_device_ms, s.t_rx_ms, step, reorder_delay_ms)
        ),
        key=lambda item: item[0],
    )
    evaluator = _evaluator_from(
        point.template, point.anchor_ms, point.kind, point.params, ctx, point.k_a
    )
    held = _NAN
    pointer = 0
    value: float | None = None
    for kk in range(point.k_a, last_step + 1):
        while pointer < len(pressures) and step_of(pressures[pointer][0], step) <= kk:
            held = pressures[pointer][1]
            pointer += 1
        row: dict[str, float | None] = {}
        if not math.isnan(held):
            row["bp"] = held
        if kk == point.k_a:
            row["bp_pre"] = point.pre
        if meas[kk]:
            row["meas"] = float(meas[kk])
        value = evaluator.step(kk * step, row)
    if value is None:
        return None
    return normalise(value, point.scale)
