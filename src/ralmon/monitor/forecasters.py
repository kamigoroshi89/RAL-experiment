"""The three forecasters of ``Forecaster`` (02-interfaces.md#forecaster), WS05-T05 and ADR-057.

* ``PersistenceForecaster``: the reference, the last observation repeated.
* ``AutoRegressiveForecaster``: least squares on the hold-last grid series, one model per signal, for
  the continuous signals ``hr_ecg``, ``hr_pulse``, ``spo2`` and for sparse ``bp``.
* ``DeadlineForecaster``: an additive model of the arrival of the robot for a care-delivery
  deadline, which forecasts the impulse signal ``meas``.

A forecaster emits a point path and nothing else: it never scores an anomaly (residual-based
detection is baseline B2, review item R2-W8). A forecaster reads only the ``ObservedTrace`` days it is
fitted on and the ``history`` it is given, never the noise-free latent trace or the ground-truth labels of the benchmark. The index
convention of the path is documented on ``Forecast``. No class here holds a random generator: a fit is
a deterministic function of the training days.

Errors (named, never a silent default): ``ForecasterNotFittedError`` (predict before fit, or no model
for the signal), ``InsufficientHistoryError`` (the history cannot define the inputs) and
``UnsupportedSignalError`` (the requested or only available signal is outside ``supported_signals``).
A malformed argument is a ``ValueError`` (non-positive step, negative horizon, non-finite or
negative value) or a ``TypeError`` (a time that is not an integer).
"""

from __future__ import annotations

import hashlib
import math
from bisect import bisect_left
from collections.abc import Iterable, Sequence
from typing import Final

import numpy as np
from numpy.typing import NDArray

from ralmon.monitor.forecast import Forecast
from ralmon.signals import (
    DurationMs,
    ObservedTrace,
    Sample,
    SignalId,
    TimeMs,
    event_to_sample,
    hold_last,
)

__all__ = [
    "AutoRegressiveForecaster",
    "DeadlineForecaster",
    "ForecasterNotFittedError",
    "InsufficientHistoryError",
    "PersistenceForecaster",
    "UnsupportedSignalError",
]

_CONTINUOUS: Final = frozenset(
    {
        SignalId.BP.value,
        SignalId.HR_ECG.value,
        SignalId.HR_PULSE.value,
        SignalId.SPO2.value,
    }
)
_MEAS: Final = SignalId.MEAS.value
_TICK: Final = SignalId.SCHED_TICK.value
_NAV: Final = SignalId.NAV_ETA.value
_QUEUE: Final = SignalId.TASK_QUEUE.value


class ForecasterNotFittedError(Exception):
    """``predict`` was called before ``fit``, or the fit holds no model for the signal."""


class InsufficientHistoryError(Exception):
    """The history does not define the inputs of the model at ``t_ms`` (unavailable, not zero)."""


class UnsupportedSignalError(Exception):
    """The requested signal, or the only signal present in the history, is not supported."""


# -- shared helpers (module-private) --------------------------------------------------------------


def _check_step(step_ms: int) -> int:
    if isinstance(step_ms, bool) or not isinstance(step_ms, int) or step_ms <= 0:
        raise ValueError(f"step_ms must be a positive integer, got {step_ms!r}")
    return step_ms


def _check_call(t_ms: TimeMs, horizon_ms: DurationMs) -> None:
    for label, value in (("t_ms", t_ms), ("horizon_ms", horizon_ms)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{label} must be an integer, got {value!r}")
    if horizon_ms < 0:
        raise ValueError(f"horizon_ms must not be negative, got {horizon_ms}")


def _upto(history: Sequence[Sample], t_ms: TimeMs) -> list[Sample]:
    """The samples with ``t_device_ms <= t_ms``: nothing later is ever read."""
    return [s for s in history if s.t_device_ms <= t_ms]


def _of_signal(samples: Iterable[Sample], signal: str) -> list[Sample]:
    """Samples of one signal sorted by device time (stable: ties keep the given order)."""
    chosen = [s for s in samples if s.signal == signal]
    chosen.sort(key=lambda s: s.t_device_ms)
    for s in chosen:
        if not math.isfinite(s.value):
            raise ValueError(
                f"{signal} sample at {s.t_device_ms} has a non-finite value {s.value!r}"
            )
    return chosen


def _resolve_signal(
    available: Sequence[Sample], supported: frozenset[str], signal: str | None
) -> str:
    """The target signal: the requested one, else the single supported signal in the history."""
    if signal is not None:
        if signal not in supported:
            raise UnsupportedSignalError(
                f"signal {signal!r} is not supported (supported: {sorted(supported)})"
            )
        return signal
    present = {s.signal for s in available}
    candidates = present & supported
    if len(candidates) == 1:
        return next(iter(candidates))
    if len(candidates) > 1:
        raise ValueError(
            f"the history carries several supported signals {sorted(candidates)}; pass signal="
        )
    if present:
        raise UnsupportedSignalError(
            f"no supported signal in the history (found {sorted(present)}, "
            f"supported {sorted(supported)})"
        )
    raise InsufficientHistoryError("the history has no sample up to t_ms")


def _latest(samples: Sequence[Sample], t_ms: TimeMs) -> float | None:
    """Value held at ``t_ms`` by ``hold_last`` (samples sorted), or ``None`` if there is none."""
    if not samples:
        return None
    held = hold_last(samples, [t_ms])[0]
    return None if math.isnan(held) else held


def _digest(parts: Iterable[str]) -> str:
    """Hex SHA-256 of the lines; floats are written with ``repr`` by the callers."""
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _ceil_div(numerator: int, denominator: int) -> int:
    return -(-numerator // denominator)


def _training_series(
    day: ObservedTrace,
    signal: str,
    step_ms: int,
    t_end_ms: TimeMs | None = None,
) -> list[float]:
    """The hold-last grid series of ``signal`` on one day (module-private).

    The grid is ``k * step_ms`` as in the monitor. It starts at the first grid point at or after the
    first sample of the signal and ends at ``t_end_ms`` if given, else at the grid point at which the
    last sample becomes visible (ceiling rule). Each value is the last sample at or before the grid
    point (``hold_last``), so a sparse signal such as ``bp`` becomes a piecewise-constant series; the
    forecaster is not fitted on the raw irregular samples. The result is empty if the day has no
    sample of the signal.
    """
    samples = _of_signal(day.samples, signal)
    if not samples:
        return []
    start = _ceil_div(samples[0].t_device_ms, step_ms) * step_ms
    end = (
        _ceil_div(samples[-1].t_device_ms, step_ms) * step_ms
        if t_end_ms is None
        else t_end_ms
    )
    if end < start:
        return []
    grid = list(range(start, end + 1, step_ms))
    return [float(v) for v in hold_last(samples, grid)]


def _path(
    signal: str, t_ms: TimeMs, horizon_ms: DurationMs, mean: Sequence[float]
) -> Forecast:
    return Forecast(signal, t_ms, horizon_ms, tuple(mean))


# -- persistence ------------------------------------------------------------------------------------


class PersistenceForecaster:
    """The reference forecaster: the last observation at or before ``t_ms``, repeated.

    It needs no fit (``fit`` does nothing) and has a constant ``model_version``. It supports
    ``bp``, ``hr_ecg``, ``hr_pulse`` and ``spo2``. Every forecast of the autoregressive forecaster is
    to be reported next to this one.
    """

    name: str = "persistence"
    supported_signals: frozenset[str] = _CONTINUOUS

    def __init__(self, step_ms: int) -> None:
        self._step_ms = _check_step(step_ms)

    @property
    def model_version(self) -> str:
        return "persistence-1"

    def fit(self, train_days: Sequence[ObservedTrace]) -> None:
        """No parameters: nothing is learned."""

    def predict(
        self,
        history: Sequence[Sample],
        t_ms: TimeMs,
        horizon_ms: DurationMs,
        *,
        signal: str | None = None,
    ) -> Forecast:
        _check_call(t_ms, horizon_ms)
        available = _upto(history, t_ms)
        target = _resolve_signal(available, self.supported_signals, signal)
        last = _latest(_of_signal(available, target), t_ms)
        if last is None:
            raise InsufficientHistoryError(f"no {target} sample at or before t_ms")
        return _path(target, t_ms, horizon_ms, [last] * (horizon_ms // self._step_ms))


# -- autoregressive ---------------------------------------------------------------------------------


class AutoRegressiveForecaster:
    """Autoregression of explicit order ``p`` by least squares, one model per signal.

    Model: ``x[k+1] = c + a_1 x[k] + ... + a_p x[k-p+1]`` on the monitor grid. The training series of
    a signal on a day is its hold-last grid series (so ``bp``, sparse, becomes piecewise constant);
    the regression rows never cross a day boundary; the fit is ``numpy.linalg.lstsq`` on all rows of
    the training days (deterministic, no random generator). A multi-step forecast iterates the
    one-step model, feeding its own output back. The order is a required argument: no default is
    invented, WS08 chooses it on validation days.

    The target signals are ``hr_ecg``, ``hr_pulse``, ``spo2`` (continuous) and ``bp``. Blood pressure
    with about five measurements a day is expected to be uninformative as a forecasting target
    (analisi §4.3, R2-W5): the same code path produces its path so that WS08 can report the width of
    the intervals as a finding, and no accuracy claim is made here for any signal. The class emits
    paths only; it has no anomaly scoring (baseline B2 owns that, R2-W8).

    ``predict`` needs at least ``order`` samples of the signal at or before ``t_ms`` and a value of
    the held series at each of the ``order`` lag grid points ``t_ms - j * step_ms``; otherwise
    ``InsufficientHistoryError``. A signal with fewer training rows than parameters has no model
    (``ForecasterNotFittedError`` at predict).
    """

    name: str = "autoregressive"
    supported_signals: frozenset[str] = _CONTINUOUS

    def __init__(self, step_ms: int, order: int) -> None:
        self._step_ms = _check_step(step_ms)
        if isinstance(order, bool) or not isinstance(order, int) or order < 1:
            raise ValueError(f"order must be an integer >= 1, got {order!r}")
        self._order = order
        self._models: dict[str, tuple[float, tuple[float, ...]]] = {}
        self._rows: dict[str, int] = {}

    @property
    def order(self) -> int:
        return self._order

    @property
    def model_version(self) -> str:
        parts = [
            type(self).__name__,
            f"step_ms={self._step_ms}",
            f"order={self._order}",
        ]
        for signal in sorted(self._models):
            intercept, coefficients = self._models[signal]
            parts.append(f"{signal}:intercept={intercept!r}")
            parts.extend(f"{signal}:a{i + 1}={c!r}" for i, c in enumerate(coefficients))
        return _digest(parts)

    def intercept(self, signal: str) -> float:
        """The fitted ``c`` of ``signal``."""
        return self._model(signal)[0]

    def coefficients(self, signal: str) -> tuple[float, ...]:
        """The fitted ``(a_1, ..., a_p)`` of ``signal``; ``a_1`` multiplies the latest value."""
        return self._model(signal)[1]

    def n_training_rows(self, signal: str) -> int:
        """Number of regression rows of the last fit (0 if the signal has no model)."""
        return self._rows.get(signal, 0)

    def _model(self, signal: str) -> tuple[float, tuple[float, ...]]:
        if not self._models:
            raise ForecasterNotFittedError("fit has not been called")
        if signal not in self._models:
            raise ForecasterNotFittedError(f"the fit holds no model for {signal!r}")
        return self._models[signal]

    def fit(self, train_days: Sequence[ObservedTrace]) -> None:
        p = self._order
        models: dict[str, tuple[float, tuple[float, ...]]] = {}
        rows: dict[str, int] = {}
        for signal in sorted(self.supported_signals):
            blocks_x: list[NDArray[np.float64]] = []
            blocks_y: list[NDArray[np.float64]] = []
            for day in train_days:
                series = np.asarray(
                    _training_series(day, signal, self._step_ms), dtype=np.float64
                )
                n = len(series)
                if n <= p:
                    continue
                lags = [series[p - i : n - i] for i in range(1, p + 1)]
                blocks_x.append(np.column_stack([np.ones(n - p), *lags]))
                blocks_y.append(series[p:])
            if not blocks_x:
                continue
            design = np.vstack(blocks_x)
            target = np.concatenate(blocks_y)
            if design.shape[0] < p + 1:  # fewer rows than parameters: no model
                continue
            solution, _, _, _ = np.linalg.lstsq(design, target, rcond=None)
            models[signal] = (float(solution[0]), tuple(float(v) for v in solution[1:]))
            rows[signal] = int(design.shape[0])
        if not models:
            raise ValueError(
                "no signal has enough training rows for an autoregression of this order"
            )
        self._models, self._rows = models, rows

    def predict(
        self,
        history: Sequence[Sample],
        t_ms: TimeMs,
        horizon_ms: DurationMs,
        *,
        signal: str | None = None,
    ) -> Forecast:
        _check_call(t_ms, horizon_ms)
        if not self._models:
            raise ForecasterNotFittedError("fit has not been called")
        available = _upto(history, t_ms)
        target = _resolve_signal(available, self.supported_signals, signal)
        intercept, coefficients = self._model(target)
        samples = _of_signal(available, target)
        p = self._order
        if len(samples) < p:
            raise InsufficientHistoryError(
                f"order {p} needs {p} {target} samples, the history has {len(samples)}"
            )
        lag_grid = [
            t_ms - (p - 1 - j) * self._step_ms for j in range(p)
        ]  # oldest first
        window = [float(v) for v in hold_last(samples, lag_grid)]
        if any(math.isnan(v) for v in window):
            raise InsufficientHistoryError(
                f"{target} has no value at the {p} lag grid points ending at t_ms"
            )
        mean: list[float] = []
        for _ in range(horizon_ms // self._step_ms):
            nxt = intercept + sum(
                a * window[-1 - i] for i, a in enumerate(coefficients)
            )
            if not math.isfinite(nxt):
                raise ValueError(
                    f"the iterated {target} path is not finite after {len(mean)} steps "
                    "(overflow of the fitted model); no path is returned"
                )
            window.append(nxt)
            mean.append(nxt)
        return _path(target, t_ms, horizon_ms, mean)


# -- robot deadline ---------------------------------------------------------------------------------


class DeadlineForecaster:
    """Additive forecaster of the robot's arrival for a care-delivery deadline (signal ``meas``).

    Model: predicted arrival = ``t_ms`` + latest ``nav_eta_ms`` + latest ``task_queue_ms`` + ``bias``,
    where ``bias`` is the mean signed error of the same sum on the training episodes. The forecast
    path of ``meas`` is an impulse: 1.0 at the first grid step at or after the predicted arrival
    (ceiling rule; an arrival at or before ``t_ms`` is placed on the first step), 0.0 elsewhere,
    and all zero if the arrival is beyond the horizon.

    Both robot-state signals are assumed to be refreshed by the robot task layer at least once per
    step; the age of the latest sample is not compensated. If either is absent at or before ``t_ms``
    ``predict`` raises ``InsufficientHistoryError`` (the channel is unavailable, not zero).

    ``fit`` builds one episode per ``sched_tick`` of each training day: the robot state is the latest
    ``nav_eta_ms`` and ``task_queue_ms`` at or before the tick, the outcome is the first ``meas`` at
    or after the tick on the same day, and the residual of the episode is that time minus the tick,
    ETA and queue sum. A tick with no later ``meas`` that day is censored (counted, not trained on); a
    tick with no robot state is counted in ``n_no_robot_state``. Ticks and measurements are read from
    the events (``event_to_sample``) and from samples of the same name, de-duplicated by time. The bias
    is the mean of the residuals; with no episode the fit is refused.
    """

    name: str = "deadline"
    supported_signals: frozenset[str] = frozenset({_MEAS})

    def __init__(self, step_ms: int) -> None:
        self._step_ms = _check_step(step_ms)
        self._bias_ms: float | None = None
        self.n_train_episodes: int = 0
        self.n_censored: int = 0
        self.n_no_robot_state: int = 0

    @property
    def bias_ms(self) -> float:
        """Mean signed error of the fitted episodes, in ms (positive: the robot is later)."""
        if self._bias_ms is None:
            raise ForecasterNotFittedError("fit has not been called")
        return self._bias_ms

    @property
    def model_version(self) -> str:
        parts = [type(self).__name__, f"step_ms={self._step_ms}"]
        if self._bias_ms is not None:
            parts.append(f"bias_ms={self._bias_ms!r}")
        return _digest(parts)

    @staticmethod
    def _times(day: ObservedTrace, signal: str) -> list[TimeMs]:
        times = {s.t_device_ms for s in day.samples if s.signal == signal}
        for event in day.events:
            sample = event_to_sample(event)
            if sample is not None and sample.signal == signal:
                times.add(sample.t_device_ms)
        return sorted(times)

    @staticmethod
    def _state(samples: Sequence[Sample], t_ms: TimeMs) -> tuple[float, float] | None:
        """Latest ``(nav_eta_ms, task_queue_ms)`` at or before ``t_ms``, or ``None`` if either is absent."""
        upto = _upto(samples, t_ms)
        eta = _latest(_of_signal(upto, _NAV), t_ms)
        queue = _latest(_of_signal(upto, _QUEUE), t_ms)
        if eta is None or queue is None:
            return None
        for label, value in (("nav_eta_ms", eta), ("task_queue_ms", queue)):
            if value < 0:
                raise ValueError(f"{label} must not be negative, got {value!r}")
        return eta, queue

    def fit(self, train_days: Sequence[ObservedTrace]) -> None:
        residuals: list[float] = []
        censored = 0
        no_state = 0
        for day in train_days:
            measurements = self._times(day, _MEAS)
            for tick in self._times(day, _TICK):
                j = bisect_left(measurements, tick)
                if j == len(measurements):
                    censored += 1
                    continue
                state = self._state(day.samples, tick)
                if state is None:
                    no_state += 1
                    continue
                residuals.append(measurements[j] - (tick + state[0] + state[1]))
        if not residuals:
            raise ValueError("no usable training episode: the bias would be undefined")
        self._bias_ms = math.fsum(residuals) / len(residuals)
        self.n_train_episodes = len(residuals)
        self.n_censored = censored
        self.n_no_robot_state = no_state

    def predict(
        self,
        history: Sequence[Sample],
        t_ms: TimeMs,
        horizon_ms: DurationMs,
        *,
        signal: str | None = None,
    ) -> Forecast:
        _check_call(t_ms, horizon_ms)
        bias = self.bias_ms
        if signal is not None and signal not in self.supported_signals:
            raise UnsupportedSignalError(
                f"signal {signal!r} is not supported (supported: ['meas'])"
            )
        state = self._state(history, t_ms)
        if state is None:
            raise InsufficientHistoryError(
                "no nav_eta_ms or task_queue_ms sample at or before t_ms"
            )
        delay_ms = state[0] + state[1] + bias
        if not math.isfinite(
            delay_ms
        ):  # two finite states can still sum past the float range
            raise ValueError(
                "the predicted delay is not finite (nav_eta_ms + task_queue_ms + bias overflows)"
            )
        steps = max(1, math.ceil(delay_ms / self._step_ms))
        n = horizon_ms // self._step_ms
        mean = [0.0] * n
        if steps <= n:
            mean[steps - 1] = 1.0
        return _path(_MEAS, t_ms, horizon_ms, mean)
