"""B4: conformal anomaly detection without a specification (WS06-T05; analisi section 5.4, row B4).

What B4 is. A forecaster predicts the next reading of a continuous signal from the previous one; the residual of a
delivered sample is ``value - forecast``; a detection is raised when the magnitude of the residual leaves the conformal
prediction interval ``[forecast - q, forecast + q]``, where ``q`` is the one-sided conformal quantile (level ``alpha``)
of the residual magnitudes of the calibration days. The interval is closed: a residual of exactly ``q`` is inside. The
calibrator is the one of the proposed method (``ralmon.conformal``, public API only: ``fit`` and ``quantile``); the
forecaster is the same class and training days as the proposed method. B4 therefore isolates the contribution of the
specification: whatever B4 misses that the proposed method finds is due to the clinical specification, with the same
forecaster and the same conformal machinery (analisi section 5.4).

Residual. The residual of a delivered sample of signal ``s`` at device time ``t`` is ``value - forecast`` where the
forecast is issued at the device time ``t_prev`` of the previous delivered sample of ``s`` (``Forecaster.predict`` with
the history of ``s`` delivered so far, the keyword ``signal=`` when the forecaster accepts it, and horizon ``t -
t_prev``) and read from the path at index ``(t - t_prev) // step_ms - 1`` (the convention of ``Forecast``: entry ``k``
predicts ``t_prev + (k + 1) * step_ms``). The first sample of a signal has no residual; a gap of less than one step has
an empty path and no residual (counted in ``run_stats.no_forecast``, as is a ``InsufficientHistoryError`` of the
forecaster); a sample whose device time is not later than the previous one (a duplicate, or an older reading delivered
late) has no residual (``not_newer``) and does not replace the previous sample. A non-finite value is not a reading
(``non_finite_samples``). The same code computes the residuals of the calibration days and of the run.

Calibration. ``fit`` fits the forecaster on the observed training days, computes the residuals on the observed
calibration days (the latent trace is never read: the default ``AccessPolicy`` denies it, and the log shows
``observed`` reads only) and builds the calibration episodes. There is one calibrator per monitored signal (the
residual of a heart rate and that of a saturation are in different units and are never pooled), created by the factory
at each ``fit`` and fitted with ``model_version`` equal to that of the forecaster; ``run`` refuses a calibrator that is
older than the forecaster (``StaleCalibratorError``). The contract score is ``R = sigma_true - sigma_hat``
(``#conformal-calibrator``), one-sided; B4 sets ``sigma_hat = 0.0`` and ``sigma_true`` to a residual magnitude, so the
calibrator's one-sided quantile is the quantile of the magnitudes. Two calibration units:

* ``unit="day_max"`` (default): one episode per (patient, day, signal), ``sigma_true`` the largest residual magnitude of
  that day. This follows rule 1 of the contract (the unit is the patient episode, one designated statistic per
  episode) and the test statistic is the same: the daily maximum exceeds ``q`` iff some residual of the day does. A day
  with no residual of the signal gives no episode.
* ``unit="sample"``: one episode per residual. This is the classical time-step conformal anomaly detection. It does
  NOT follow rule 1 of the contract (the unit is a time step and consecutive residuals of one patient are dependent),
  so the statement below does not apply to it; it is offered because it is what a reader expects under the name
  conformal anomaly detection.

``CalibrationEpisode.template`` is required and is a ``TemplateId``; B4 has no template. ``PLACEHOLDER_TEMPLATE`` is
used for every episode and is ignored by the calibrator (``SplitConformal`` pools its episodes whatever their template,
pinned by ``test_b4_placeholder_template_does_not_change_quantile``): one calibrator per signal, no template meaning.

Coverage statement (qualified; no distribution-free claim is made without its assumptions). For ``unit="day_max"`` the
probability that the largest residual magnitude of a test day on a signal exceeds ``q`` is at most ``alpha``, marginal
over patient episodes under exchangeability of the calibration and test days, given a fixed forecaster, and only if the
number of readings of a day is exchangeable as well (the daily maximum grows with the number of readings). It is not
conditional on the patient. With an ``allocation`` the level of each signal is ``alpha_total / n`` with ``n`` the
number of monitored signals: a union bound over the signals of one patient-day, which is a bound on the daily
false-alarm probability only for ``day_max`` and says nothing about the number of detections of a day. The calibration
days are unlabelled: an anomaly injected in a calibration day inflates the quantile and B4 loses power, a limitation
shared with any conformal method that does not use labels. Days of one patient are not independent and the harness does
not check the split by patient beyond the labels it is given. The allocated level is taken from
``allocation.per_test_exact`` (a ``Fraction``, WS05-T06 hand-over) when the allocation has it, else from ``per_test``.
An allocation takes a float total, read as its decimal literal: a ``Fraction`` ``alpha`` is passed to it only when it is
exactly such a literal (``Fraction(1, 20)`` is ``0.05``); any other ``Fraction`` with an allocation is a ``ValueError``,
never a rounded float.

What B4 knows. A forecaster, the quantile of residual magnitudes, and the samples of the monitored signals. Nothing
else: no band, no hold threshold, no window, no schedule, no template, no plan parameter (the plan is not read, so
``read_log`` stays empty and the output does not depend on ``plan.schedule`` or on ``tail_ms``), no event, no evidence,
no attribution (every ``Detection.label`` is ``None``). Fair competitor, different question: B4 is given the same
forecaster, calibrator and calibration days as the proposed method; it is not given the clinical knowledge, and that is
the point of the baseline, not a handicap that hides a weaker implementation.

What B4 cannot see, by construction. B4 sees a CHANGE between two consecutive readings of one signal, in either
direction and in the unit of that signal. It does not see a level: a value held outside the prescribed range has
residual 0, and a drift in steps smaller than ``q`` reaches any level without a detection. It does not see an
absence: a missed measurement, a sensor that went silent, a whole day without readings (no residual is no detection).
It does not see events, so dispenses, counts, doses, schedules and the robot's tasks are invisible to it. It cannot
tell a clinically meaningful change from a harmless one (a drop that is wanted after a dose alarms like a rise).
It makes no attribution and has no notion of severity or priority. By template of the proposed method: RANGE is seen
only as a large change into or out of the band, never as a level; HOLD, COUNT, SCHED and INT (events, counters and
deadlines) not at all; RESP (the expected drop after a dose, an event-anchored window) not at all; SYS (cuff health
and inflation time) not at all. By class of the benchmark, as expectations derived from the design and not as
measurements (WS08 reports the measured values): C1, an abrupt spike can be seen when it is larger than the usual
change between readings, a missed or refused measurement, a missing response to a dose and a double dose cannot; C2,
noise on a continuous channel can be seen, a detached or silent device, a stuck value, a delayed or failed robot task
and a dispenser fault cannot (a stuck value has residual 0); C3, injected or replayed values are seen only if they
differ from the previous reading by more than ``q``, forged dispenses and spoofed presence not at all. Several of these
are pinned by tests (``test_b4_blind_spot_*``) so that the comparison per class is not read as a comparison of equals.
Blood pressure is a poor forecasting target (about five readings a day, ``#forecaster``): its gaps are hours long and
the residual of a persistence forecast over such a gap is as large as the usual variation, so the interval is wide.

Time. Delivery is the shared causal step iterator; the detection time is the grid time at which the sample is delivered
(``t_eval + D``), not clipped at midnight (a sample delivered after the closing step of its day is detected there, as
for B1 and B3). B4 applies the lateness rule of the monitor and of B1, B3 and B5 to the samples it uses: a sample
received after its step is final is dropped and counted (``late_inputs``). It does not deduplicate (asymmetry (b) of
``base.py``): a duplicate is delivered twice but has no residual, so it cannot raise a second alarm. A device time in
``(t0 - step, t0]`` is step 0 of the day; a sample stamped a whole step or more before the day is a delivered value
(it can be the previous sample of the next one) but yields neither a detection nor a calibration residual. B4 runs one
day at a time with empty carry-over state (ADR-061): the first reading of every day has no residual, whereas the
proposed method with a history would have one. The run ends at the last step that delivers a monitored sample, so the
output does not depend on ``tail_ms``.

Score. The score is the residual magnitude divided by the quantile of its signal (above 1 is an alarm); a quantile of
0 gives the largest finite float, because the harness refuses an infinite score. A quantile of ``+inf`` (a level below
``1 / (n + 1)``) never alarms. Scores of different signals are in units of their own quantile and are comparable only
as multiples of the interval half-width.

Hyperparameter selection. The only operating parameter is ``alpha`` (with the optional ``allocation``); it has no
default and is swept by WS08 over the grid of the experiment config. ``signals``, ``unit`` and the forecaster are fixed by
the experiment config, not tuned. The residual scale (the quantile) is estimated on calibration days only, the forecaster
on training days only, and nothing is tuned on test days.

Numbers. No clinical constant appears here; the only numbers are the operating parameter given by the caller.
"""

from __future__ import annotations

import inspect
import math
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from fractions import Fraction
from typing import Any, Final, Literal

from ralmon.attribution import Detection
from ralmon.baselines.access import AccessLog, AccessPolicy, GuardedDay, ReadLog
from ralmon.baselines.base import BaselineBase, TimingConfig, iter_steps
from ralmon.benchmark import ObservedDay
from ralmon.conformal import (
    AlphaAllocation,
    CalibrationEpisode,
    ConformalCalibrator,
    SplitConformal,
)
from ralmon.monitor import Forecaster, InsufficientHistoryError, StaleCalibratorError
from ralmon.signals import MS_PER_HOUR, Sample, SignalId
from ralmon.spec import CarePlan, TemplateId

__all__ = [
    "DEFAULT_SIGNALS",
    "PLACEHOLDER_TEMPLATE",
    "UNITS",
    "B4ConformalOnly",
    "B4Residual",
    "B4RunStats",
]

# the continuous signals of the in-scope forecasting targets (#forecaster); the same default as B2
DEFAULT_SIGNALS: Final[tuple[str, ...]] = (
    SignalId.BP.value,
    SignalId.HR_ECG.value,
    SignalId.HR_PULSE.value,
    SignalId.SPO2.value,
)
UNITS: Final = ("day_max", "sample")
Unit = Literal["day_max", "sample"]
Level = float | Fraction

# B4 has no template: every calibration episode carries this one, which the calibrator ignores (module docstring)
PLACEHOLDER_TEMPLATE: Final = TemplateId.RANGE

_T_DAY_MS: Final = 24 * MS_PER_HOUR
# the score of a detection whose quantile is 0: the largest finite number (the harness refuses an infinite score)
_LARGEST_SCORE: Final = sys.float_info.max


@dataclass(frozen=True, slots=True)
class B4Residual:
    """One residual of a run: the delivered sample, the forecast it was compared with and the outcome.

    ``t_ms`` is the grid time of delivery, ``t_device_ms`` the device time of the sample. ``quantile`` is ``None`` when
    the signal has no fitted calibrator (and ``math.inf`` when the level is below ``1 / (n + 1)``); ``alarm`` is
    ``|residual| > quantile``. It is what WS08 reads for the width and the empirical coverage of the interval (the
    interval is ``forecast -+ quantile``); it takes no part in any decision.
    """

    signal: str
    t_ms: int
    t_device_ms: int
    value: float
    forecast: float
    residual: float
    quantile: float | None = None
    alarm: bool = False


@dataclass(frozen=True, slots=True)
class B4RunStats:
    """What the last ``run`` counted (no wall clock).

    ``residuals`` the residuals computed in the day; ``late_inputs`` the monitored samples dropped because they arrived
    after their step was final; ``non_finite_samples`` the samples that were not numbers; ``not_newer`` the samples
    with a device time not later than the previous one of their signal (duplicates); ``no_forecast`` the pairs of
    samples with no forecast (a gap under one step, or a forecaster that could not define the forecast);
    ``uncalibrated_signals`` the monitored signals with no calibration episode, on which B4 is silent.
    """

    residuals: int
    late_inputs: int
    non_finite_samples: int
    not_newer: int
    no_forecast: int
    uncalibrated_signals: tuple[str, ...]


@dataclass(slots=True)
class _Counts:
    late: int = 0
    non_finite: int = 0
    not_newer: int = 0
    no_forecast: int = 0


def _check_level(level: object, what: str) -> Level:
    if isinstance(level, bool) or not isinstance(level, (float, Fraction)):
        raise ValueError(  # noqa: TRY004 - one named error for every bad level
            f"{what} must be a float or a Fraction in (0, 1), got {level!r}"
        )
    if not 0 < level < 1:
        raise ValueError(f"{what} must lie in (0, 1), got {level!r}")
    return level


def _accepts_signal(predict: Callable[..., Any]) -> bool:
    try:
        parameters = inspect.signature(predict).parameters
    except (TypeError, ValueError):
        return False
    return "signal" in parameters or any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters.values()
    )


def _score(magnitude: float, quantile: float) -> float:
    """The magnitude in units of the interval half-width, finite (``quantile`` is at least 0 and below ``magnitude``)."""
    if quantile == 0.0:
        return _LARGEST_SCORE
    return min(magnitude / quantile, _LARGEST_SCORE)


class B4ConformalOnly(BaselineBase):
    """Baseline B4; see the module docstring for the method, what it sees and what it cannot see.

    Parameters: ``forecaster`` (fitted by ``fit`` on the observed training days), ``calibrator_factory`` (default
    ``SplitConformal``; called once per monitored signal at each ``fit``, in the order of ``signals``), ``alpha`` (the
    operating parameter, no default), ``allocation`` (optional; the level of each signal is the allocation of ``alpha``
    over the number of monitored signals), ``signals`` (default: ``bp``, ``hr_ecg``, ``hr_pulse`` and ``spo2``, the
    ones the forecaster supports), ``unit`` (``"day_max"`` by default, or ``"sample"``, the classical time-step
    variant that does not follow rule 1 of the contract) and ``timing``. B4 makes no attribution (every ``label`` is
    ``None``) and ignores the evidence and the care plan.

    Hyperparameter selection. The only operating parameter is ``alpha`` (and the optional allocation); WS08 sweeps it
    over the grid of the experiment config. The residual scale is estimated on calibration days only; nothing is tuned
    on test days. Coverage statements read "marginal over patient episodes under exchangeability".
    """

    name = "B4"

    def __init__(
        self,
        forecaster: Forecaster,
        calibrator_factory: Callable[[], ConformalCalibrator] = SplitConformal,
        *,
        alpha: float | Fraction,
        allocation: AlphaAllocation | None = None,
        signals: Sequence[str | SignalId] | None = None,
        unit: Unit = "day_max",
        timing: TimingConfig,
        access_policy: AccessPolicy | None = None,
        access_log: AccessLog | None = None,
        read_log: ReadLog | None = None,
    ) -> None:
        super().__init__(
            timing,
            access_policy=access_policy,
            access_log=access_log,
            read_log=read_log,
        )
        if unit not in UNITS:
            raise ValueError(f"unit must be one of {UNITS}, got {unit!r}")
        self._unit: Unit = unit
        self._alpha = _check_level(alpha, "alpha")
        supported = frozenset(forecaster.supported_signals)
        self._signals = self._resolve_signals(signals, supported)
        if allocation is None:
            level: object = self._alpha
        else:
            total = self._float_total(self._alpha)
            exact = getattr(allocation, "per_test_exact", None)
            n_tests = len(self._signals)
            level = (
                exact(total, n_tests)
                if exact is not None
                else allocation.per_test(total, n_tests)
            )
        self._level: Level = _check_level(level, "the allocated level")
        self._forecaster = forecaster
        self._predict: Callable[..., Any] = forecaster.predict
        self._with_signal = _accepts_signal(self._predict)
        self._factory = calibrator_factory
        self._calibrators: dict[str, ConformalCalibrator] = {}
        self._fitted_signals: tuple[str, ...] = ()
        self._episodes: tuple[CalibrationEpisode, ...] = ()
        self._n_episodes: dict[str, int] = {}
        self._residuals: tuple[B4Residual, ...] = ()
        self._run_stats: B4RunStats | None = None

    @staticmethod
    def _float_total(alpha: Level) -> float:
        """``alpha`` as the float an allocation takes (``AlphaAllocation.per_test(alpha_total: float, ...)``).

        An allocation reads its float as the decimal literal. A ``Fraction`` is converted only if it IS that literal
        (``Fraction(1, 20)`` is ``0.05``); any other ``Fraction`` would be rounded silently, which moves a quantile rank
        (the WS05-T06 trap), so it is refused by name.
        """
        if isinstance(alpha, float):
            return alpha
        value = float(alpha)
        if Fraction(repr(value)) != alpha:
            raise ValueError(
                f"alpha = {alpha} is a Fraction that is not the decimal literal of a float, and an allocation takes "
                "a float: give a float alpha with the allocation, or a Fraction alpha without one"
            )
        return value

    @staticmethod
    def _resolve_signals(
        signals: Sequence[str | SignalId] | None, supported: frozenset[str]
    ) -> tuple[str, ...]:
        if signals is None:
            chosen = tuple(s for s in DEFAULT_SIGNALS if s in supported)
            if not chosen:
                raise ValueError(
                    f"the forecaster supports none of the default signals {DEFAULT_SIGNALS}; name the signals"
                )
            return chosen
        names = tuple(s.value if isinstance(s, SignalId) else s for s in signals)
        if not names:
            raise ValueError("signals must name at least one signal")
        for index, name in enumerate(names):
            if name in names[:index]:
                raise ValueError(f"signal {name!r} is given twice")
            if name not in supported:
                raise ValueError(
                    f"signal {name!r} is not supported by the forecaster (supported: {sorted(supported)})"
                )
        return names

    # -- what the last fit and run produced --------------------------------------------------------------------

    @property
    def signals(self) -> tuple[str, ...]:
        """The monitored signals, in the order in which the calibrator factory is called."""
        return self._signals

    @property
    def unit(self) -> Unit:
        return self._unit

    @property
    def alpha(self) -> Level:
        """The operating parameter as given."""
        return self._alpha

    @property
    def level(self) -> Level:
        """The level passed to the calibrators: ``alpha``, or its allocation over the monitored signals."""
        return self._level

    @property
    def calibration_episodes(self) -> tuple[CalibrationEpisode, ...]:
        """The episodes of the last ``fit``, in calibration-day order (all signals)."""
        return self._episodes

    @property
    def n_calibration_episodes(self) -> dict[str, int]:
        """The number of calibration episodes of each monitored signal at the last ``fit``."""
        return dict(self._n_episodes)

    @property
    def residuals(self) -> tuple[B4Residual, ...]:
        """The residuals of the last ``run`` (the ones of the day), with the quantile used and the outcome."""
        return self._residuals

    @property
    def run_stats(self) -> B4RunStats | None:
        """The counters of the last ``run``; ``None`` before the first one and after a ``fit``."""
        return self._run_stats

    # -- the residuals of one day, shared by fit and run -------------------------------------------------------

    def _forecast(
        self, history: Sequence[Sample], t_prev: int, gap: int, signal: str
    ) -> float:
        """The forecast issued at ``t_prev`` for ``gap`` ms later, checked to be the path that was asked for."""
        if self._with_signal:
            path = self._predict(history, t_prev, gap, signal=signal)
        else:
            path = self._predict(history, t_prev, gap)
        n = gap // self._timing.step_ms
        if path.signal != signal or path.t_from_ms != t_prev or len(path.mean) != n:
            raise ValueError(
                f"the forecaster returned a forecast that is not the one asked for ({signal!r} at {t_prev} for {n} "
                f"steps): got {path.signal!r} at {path.t_from_ms} for {len(path.mean)} steps"
            )
        value = float(path.mean[n - 1])
        if not math.isfinite(value):
            raise ValueError(f"the forecast of {signal!r} at {t_prev} is not finite")
        return value

    def _day_rows(self, day: ObservedDay) -> tuple[list[B4Residual], _Counts]:
        """The residuals of the samples of the monitored signals that fall in the day, and the counters."""
        timing = self._timing
        step, delay = timing.step_ms, timing.reorder_delay_ms
        t0 = day.day_index * _T_DAY_MS
        monitored = frozenset(self._signals)
        end = t0
        for sample in day.samples:
            if sample.signal in monitored:
                end = max(end, sample.t_rx_ms, sample.t_device_ms + delay)
        counts = _Counts()
        rows: list[B4Residual] = []
        history: dict[str, list[Sample]] = {name: [] for name in self._signals}
        newest: dict[str, Sample] = {}
        previous: int | None = None
        for batch in iter_steps(day, timing, end):
            # the steps of the device-time grid that were final at the previous batch (the lateness rule of the monitor
            # and of B1, B3 and B5)
            final = -1 if previous is None else (previous - t0 - delay) // step
            for sample in batch.samples:
                name = sample.signal
                if name not in monitored:
                    continue
                device = sample.t_device_ms
                if max(0, -(-(device - t0) // step)) <= final:
                    counts.late += 1
                    continue
                if not math.isfinite(sample.value):
                    counts.non_finite += 1
                    continue
                last = newest.get(name)
                if last is None:
                    newest[name] = sample
                elif device <= last.t_device_ms:
                    counts.not_newer += 1
                else:
                    gap = device - last.t_device_ms
                    newest[name] = sample
                    if gap < step:
                        counts.no_forecast += 1
                    else:
                        try:
                            forecast = self._forecast(
                                history[name], last.t_device_ms, gap, name
                            )
                        except InsufficientHistoryError:
                            counts.no_forecast += 1
                        else:
                            # a device time in (t0 - step, t0] is step 0 of the day; an earlier one is not part of it
                            if device - t0 > -step:
                                rows.append(
                                    B4Residual(
                                        name,
                                        batch.t_ms,
                                        device,
                                        sample.value,
                                        forecast,
                                        sample.value - forecast,
                                    )
                                )
                history[name].append(sample)
            previous = batch.t_ms
        return rows, counts

    # -- fit ---------------------------------------------------------------------------------------------------

    def _fit(self, train: Sequence[GuardedDay], calib: Sequence[GuardedDay]) -> None:
        self._forecaster.fit([g.observed for g in train])
        version = self._forecaster.model_version
        by_signal: dict[str, list[CalibrationEpisode]] = {n: [] for n in self._signals}
        episodes: list[CalibrationEpisode] = []
        for guarded in calib:
            day = guarded.observed
            rows, _ = self._day_rows(day)
            for name in self._signals:
                magnitudes = [abs(r.residual) for r in rows if r.signal == name]
                if self._unit == "day_max":
                    magnitudes = [max(magnitudes)] if magnitudes else []
                for magnitude in magnitudes:
                    episode = CalibrationEpisode(
                        day.patient_id,
                        day.day_index,
                        PLACEHOLDER_TEMPLATE,
                        0.0,
                        magnitude,
                    )
                    by_signal[name].append(episode)
                    episodes.append(episode)
        calibrators = {name: self._factory() for name in self._signals}
        fitted: list[str] = []
        for name, calibrator in calibrators.items():
            if by_signal[name]:
                calibrator.fit(by_signal[name], self._level, model_version=version)
                fitted.append(name)
        self._calibrators = calibrators
        self._fitted_signals = tuple(fitted)
        self._episodes = tuple(episodes)
        self._n_episodes = {n: len(by_signal[n]) for n in self._signals}
        self._residuals = ()
        self._run_stats = None

    # -- run ---------------------------------------------------------------------------------------------------

    def _check_fresh(self) -> None:
        model = self._forecaster.model_version
        for name in self._fitted_signals:
            calibrated = self._calibrators[name].calibrated_for
            if calibrated is None or calibrated != model:
                raise StaleCalibratorError(
                    f"the calibrator of {name!r} was calibrated for {calibrated!r}, the forecaster is {model!r}: "
                    "fit B4 again"
                )

    def _quantiles(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for name in self._fitted_signals:
            q = float(self._calibrators[name].quantile(self._level))
            if math.isnan(q) or q < 0.0:
                raise ValueError(
                    f"the quantile of {name!r} is {q!r}; a quantile of residual magnitudes is a number of at least 0 "
                    "or +inf"
                )
            out[name] = q
        return out

    def _run(self, day: ObservedDay, plan: CarePlan) -> Sequence[Detection]:
        _ = plan  # B4 has no clinical specification and no schedule: the plan is not read
        self._check_fresh()
        quantiles = self._quantiles()
        rows, counts = self._day_rows(day)
        detections: list[Detection] = []
        results: list[B4Residual] = []
        for row in rows:
            q = quantiles.get(row.signal)
            magnitude = abs(row.residual)
            alarm = q is not None and magnitude > q
            if alarm:
                assert q is not None
                detections.append(Detection(row.t_ms, None, _score(magnitude, q)))
            results.append(replace(row, quantile=q, alarm=alarm))
        self._residuals = tuple(results)
        self._run_stats = B4RunStats(
            len(results),
            counts.late,
            counts.non_finite,
            counts.not_newer,
            counts.no_forecast,
            tuple(n for n in self._signals if n not in self._fitted_signals),
        )
        return detections
