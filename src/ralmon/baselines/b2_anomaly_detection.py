"""B2: anomaly detection without a specification (WS06-T03; analisi section 5.4, row B2; review item R2-W8).

What B2 is. The approach the paper says it moves away from, built as a fair competitor: purely data-driven, unsupervised
and blind to the STL templates and to the clinical bands. Two detectors, which can be run alone or together:

* ``mode="residual"``. The forecast-residual z-score. A forecaster predicts the next reading of a continuous signal from
  the previous one, the residual of a delivered sample is ``value - forecast``, and a detection is raised when
  ``|z| > z_threshold`` with ``z = (residual - mean) / std``, where ``mean`` and ``std`` (population standard deviation)
  are those of the residuals of the observed calibration days, per signal. The test is strict and two-sided.
* ``mode="iforest"``. An Isolation Forest on features (``b2_features.py``: last value and age of each monitored signal,
  24 h dispense count, time since the last dispense, time to the next and since the last scheduled tick, time of day),
  fitted on the rows of the observed training days. A row is scored every ``feature_step_ms`` over the 24 h of the day; the
  threshold is the ``score_quantile`` quantile (``numpy.quantile``, linear interpolation) of the scores of the rows of the
  observed calibration days; a detection is raised at each rising edge of ``score > threshold``.
* ``mode="both"`` (name ``B2``): the union of the two lists, sorted by time.

Residual. The residual of a delivered sample of signal ``s`` at device time ``t`` is ``value - forecast`` where the forecast
is issued at the device time ``t_prev`` of the previous delivered sample of ``s`` (``Forecaster.predict`` with the history of
``s`` delivered so far, the keyword ``signal=`` when the forecaster accepts it, and horizon ``t - t_prev``) and read from the
path at index ``(t - t_prev) // step_ms - 1`` (the convention of ``Forecast``: entry ``k`` predicts
``t_prev + (k + 1) * step_ms``). This is the rule of B4 and the two series are equal (a test pins it, WS06-T07 checks it);
the index differs from the ``floor((t - t_from_ms) / step_ms)`` written in the task text, which would read past the path
(hand-over of WS05-T05). The first sample of a signal has no residual; a gap of less than one step has an empty path and
no residual (counted in ``run_stats.no_forecast``, as is an ``InsufficientHistoryError`` of the forecaster); a sample whose
device time is not later than the previous one (a duplicate, or an older reading delivered late) has no residual
(``not_newer``) and does not replace the previous sample; a value that is not a finite number is not a reading
(``non_finite_samples``). The same code computes the residuals of the calibration days and of the run.

Scale. ``mean`` and ``std`` come from at least two calibration residuals of the signal (fewer: the signal is uncalibrated,
B2 is silent on it and ``run_stats.uncalibrated_signals`` names it). A scale of 0 (all calibration residuals equal) makes a
residual equal to the mean a ``z`` of 0 and any other residual an infinite ``z``, whose score is the largest finite float
(the harness refuses an infinite score). The scale is tied to the forecaster that produced the residuals: ``run`` refuses a
forecaster whose ``model_version`` changed since ``fit`` (``StaleCalibratorError``).

Score. The score of a detection is the statistic divided by its threshold (``|z| / z_threshold``; the isolation score of the
row divided by the isolation threshold), so above 1 is an alarm. Scores of the two detectors are in units of their own
threshold and are comparable only as multiples of it. ``B2.residuals`` and ``B2.iforest_rows`` expose the continuous
statistics of the last run for rank metrics (WS08); they take no part in any decision. Unlike B1 and B4 the statistic exists
for every sample or row, so B2 can be ranked, but only within one detector.

Fitting. ``fit`` fits the forecaster on the observed training days (residual modes), estimates the residual scale on the
observed calibration days, estimates the feature means used to impute an undefined feature on the training rows, fits the
Isolation Forest on the training rows (unlabelled) and sets its threshold from the calibration rows. The ground truth is
not read although a training day may show it, and nothing of a calibration day other than the observed trace is read (the
access log shows ``observed`` reads only). The schedule features need the plan of each training and calibration day, which
the ``Detector`` contract does not pass to ``fit``: the constructor takes ``plan_for_day`` for the isolation-forest modes, as
B5 does (ADR-062, proposed); only ``plan.schedule`` of the plan it returns is read. An undefined feature is replaced by the
mean of its defined values over the training rows (0.0 if there is none: a column with no defined value is constant and carries
no information).

What B2 knows. A forecaster, the residual scale, the samples of the monitored signals, the dispense events and the schedule of
the plan. Nothing else: no band, no hold threshold, no window, no template, no plan parameter (``read_log`` stays empty), no
registry, no evidence and no attribution (every ``Detection.label`` is ``None``). The residual mode does not read the plan at
all. Fair competitor, different question: B2 is given the forecaster and the training and calibration days of the proposed
method; it is not given the clinical knowledge, and that is the point of the baseline, not a handicap that hides a weaker
implementation.

What B2 cannot see, by construction. The residual detector sees a CHANGE between two consecutive readings of one signal, in
either direction and in the unit of that signal. It does not see a level (a value held outside the prescribed range has
residual 0, and a drift in steps smaller than the scale reaches any level without a detection), an absence (a missed
measurement, a silent sensor, a day without readings) or an event (dispenses, counts, schedules, robot tasks); it cannot tell
a wanted change (the drop after a dose) from a harmful one. The Isolation Forest sees what is unusual in the training
population and not what is unsafe: a value that is frequent in the training days is ordinary however far outside the band it
is, and a value inside the band that is rare scores as an anomaly (pinned by a test); it has no direction, no clinical meaning
and no cause. It can react to an absence or a count only if that feature is unusual among the training rows. Neither makes an
attribution or has a notion of severity. By template of the proposed method: RANGE is seen only as an unusual value or a large
change, never as a level relative to the band; HOLD, COUNT, SCHED, RESP, SYS and INT only as unusual feature values, if at all
(the forest has the dispense count, the time since the last dispense and the age of the last reading, but no window, no
deadline and no pre- or post-dose comparison). By class of the benchmark, as expectations derived from the design and not as
measurements (WS08 reports the measured values): C1, an abrupt spike can be seen by the residual detector when it is larger than
the usual change; C2, noise on a continuous channel can be seen, a stuck value cannot (residual 0); C3, injected or replayed
values are seen only if they differ from the previous reading by more than the scale. Blood pressure is a poor forecasting
target (about five readings a day, ``#forecaster``): the residual of a persistence forecast over an hours-long gap is as large
as the usual variation, so the scale is wide.

Time. Delivery is the shared causal step iterator; the detection time of a residual is the grid time at which the sample is
delivered (``t_eval + D``), not clipped at midnight (a sample delivered after the closing step of its day is detected there, as
for B1, B3 and B4); the detection time of a forest row is its grid time. B2 applies the lateness rule of the monitor and of B1,
B3, B4 and B5 to the samples and dispense events it uses: an input received after its step is final is dropped and counted
(``late_inputs``, ``late_events``). It does not deduplicate (asymmetry (b) of ``base.py``): a duplicate sample has no
residual, whereas a dispense delivered twice counts twice in the feature. B2 runs one day at a time with empty carry-over
state (ADR-061): the first reading of every day has no residual and the 24 h counter can only under-count. The residual run
ends at the last step that delivers a monitored sample and the forest rows cover ``[t0, t0 + 24 h)``, so the output does not
depend on ``tail_ms``.

Hyperparameter selection. ``z_threshold`` and ``score_quantile`` are operating parameters with no default, swept by WS08 over
the grids of the experiment config; no value is tuned on test days. Each is required by the modes that use it and refused for
the modes that do not. ``feature_step_ms`` (default: the step of ``timing``), ``signals`` and the forecaster are fixed by the
experiment config, not tuned. The Isolation Forest keeps the library defaults of ``IsolationForest`` (number of trees,
subsample size, contamination ``"auto"``) with the integer ``seed`` as ``random_state``; none is changed here. Everything that
is estimated (residual scale, feature means, forest, threshold) comes from training and calibration days only.

Numbers. No clinical constant appears here. The numbers are the operating parameters given by the caller, the 24 h of the day
and the minimum of two residuals needed for a spread (algorithmic: one value has no standard deviation).
"""

from __future__ import annotations

import inspect
import math
import sys
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, replace
from typing import Any, Final, Literal, Protocol

import numpy as np
import numpy.typing as npt

from ralmon.attribution import Detection
from ralmon.baselines.access import (
    AccessLog,
    AccessPolicy,
    GuardedDay,
    ReadLog,
    logged_plan,
)
from ralmon.baselines.b2_features import (
    DEFAULT_SIGNALS,
    FeatureExtractor,
)
from ralmon.baselines.base import (
    BaselineBase,
    StepBatch,
    TimingConfig,
    iter_steps,
    rising_edges,
)
from ralmon.benchmark import ObservedDay
from ralmon.monitor import Forecaster, InsufficientHistoryError, StaleCalibratorError
from ralmon.signals import MS_PER_HOUR, EventKind, Sample
from ralmon.spec import CarePlan

__all__ = [
    "DEFAULT_SIGNALS",
    "MODES",
    "AnomalyScorer",
    "B2AnomalyDetection",
    "B2IForestRow",
    "B2Residual",
    "B2ResidualScale",
    "B2RunStats",
    "IsolationForestScorer",
]

MODES: Final = ("residual", "iforest", "both")
Mode = Literal["residual", "iforest", "both"]
Matrix = npt.NDArray[np.float64]

_T_DAY_MS: Final = 24 * MS_PER_HOUR
# the score of a detection whose threshold is 0 or whose statistic overflows: the largest finite number (the harness
# refuses an infinite score)
_LARGEST_SCORE: Final = sys.float_info.max
# algorithmic: a standard deviation needs two values
_MIN_RESIDUALS_FOR_SCALE: Final = 2


class AnomalyScorer(Protocol):
    """An unsupervised scorer: ``fit`` on rows, ``score`` rows (higher is more anomalous, never negative)."""

    def fit(self, rows: Matrix) -> None: ...

    def score(self, rows: Matrix) -> Matrix: ...


class IsolationForestScorer:
    """``sklearn.ensemble.IsolationForest`` with its library defaults and ``random_state=seed``.

    The score is ``-score_samples``: in (0, 1], higher for rows that are isolated by fewer random splits.
    """

    def __init__(self, seed: int) -> None:
        from sklearn.ensemble import IsolationForest

        if isinstance(seed, bool) or not isinstance(seed, int):
            raise TypeError(f"seed must be an integer, got {seed!r}")
        self.seed = seed
        self.estimator = IsolationForest(random_state=seed)

    def fit(self, rows: Matrix) -> None:
        self.estimator.fit(rows)

    def score(self, rows: Matrix) -> Matrix:
        return np.asarray(-self.estimator.score_samples(rows), dtype=np.float64)


@dataclass(frozen=True, slots=True)
class B2Residual:
    """One residual of a run: the delivered sample, the forecast it was compared with and the outcome.

    ``t_ms`` is the grid time of delivery, ``t_device_ms`` the device time of the sample. ``z`` is ``None`` when the signal
    has no scale (and infinite for a residual that differs from the mean of a scale of 0); ``alarm`` is ``|z| > z_threshold``.
    """

    signal: str
    t_ms: int
    t_device_ms: int
    value: float
    forecast: float
    residual: float
    z: float | None = None
    alarm: bool = False


@dataclass(frozen=True, slots=True)
class B2ResidualScale:
    """Mean and population standard deviation of the calibration residuals of one signal, and their number."""

    mean: float
    std: float
    n: int


@dataclass(frozen=True, slots=True)
class B2IForestRow:
    """One scored row of a run: grid time, raw score, score divided by the threshold (``None`` without a threshold) and alarm."""

    t_ms: int
    score: float
    ratio: float | None
    alarm: bool


@dataclass(frozen=True, slots=True)
class B2RunStats:
    """What the last ``run`` counted (no wall clock).

    ``residuals`` the residuals computed in the day; ``late_inputs`` the monitored samples dropped because they arrived
    after their step was final and ``late_events`` the same for dispense events; ``non_finite_samples`` the samples that were
    not numbers; ``not_newer`` the duplicates; ``no_forecast`` the pairs of samples with no forecast;
    ``uncalibrated_signals`` the monitored signals with no scale, on which the residual detector is silent;
    ``feature_rows`` the rows scored; ``iforest_calibrated`` whether the forest has a threshold (``None`` when the mode has
    no forest).
    """

    residuals: int
    late_inputs: int
    late_events: int
    non_finite_samples: int
    not_newer: int
    no_forecast: int
    uncalibrated_signals: tuple[str, ...]
    feature_rows: int
    iforest_calibrated: bool | None


@dataclass(slots=True)
class _Counts:
    late: int = 0
    late_events: int = 0
    non_finite: int = 0
    not_newer: int = 0
    no_forecast: int = 0


def _accepts_signal(predict: Callable[..., Any]) -> bool:
    try:
        parameters = inspect.signature(predict).parameters
    except (TypeError, ValueError):
        return False
    return "signal" in parameters or any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters.values()
    )


def _ratio(value: float, threshold: float) -> float:
    """``value / threshold``, finite: 0 for a value of 0, the largest float for a threshold of 0 or an overflow."""
    if value == 0.0:
        return 0.0
    if threshold == 0.0:
        return _LARGEST_SCORE
    return min(value / threshold, _LARGEST_SCORE)


def _number(value: object, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{what} must be a number, got {value!r}")  # noqa: TRY004
    return float(value)


class B2AnomalyDetection(BaselineBase):
    """Baseline B2; see the module docstring for the method, what it sees and what it cannot see.

    Parameters: ``forecaster`` (fitted by ``fit`` on the observed training days; required for ``"residual"`` and
    ``"both"``, ignored by ``"iforest"``), ``mode`` (``"residual"``, ``"iforest"`` or ``"both"``), ``signals`` (default:
    ``bp``, ``hr_ecg``, ``hr_pulse`` and ``spo2``; for the residual modes the ones the forecaster supports),
    ``z_threshold`` (residual modes), ``score_quantile`` (forest modes), ``seed`` (integer, required: the forest is random),
    ``feature_step_ms`` (default: the step of ``timing``; a positive multiple of it), ``timing``, ``plan_for_day`` (forest
    modes: the function from an observed training or calibration day to its care plan, of which only ``schedule`` is read;
    ADR-062) and ``scorer_factory`` (default ``IsolationForestScorer``; called with the seed at each ``fit``). B2 makes no
    attribution (every ``label`` is ``None``) and ignores the evidence.

    Hyperparameter selection. ``z_threshold`` and ``score_quantile`` are operating parameters with no default; WS08 sweeps
    them over the grids of the experiment config. No value is tuned on test days; the residual scale, the feature means, the
    forest and its threshold are estimated on training and calibration days only. The forest keeps the library defaults.
    """

    name = "B2"

    def __init__(
        self,
        forecaster: Forecaster | None,
        *,
        mode: Mode,
        signals: Sequence[str] | None = None,
        z_threshold: float | None = None,
        score_quantile: float | None = None,
        seed: int,
        feature_step_ms: int | None = None,
        timing: TimingConfig,
        plan_for_day: Callable[[ObservedDay], CarePlan] | None = None,
        scorer_factory: Callable[[int], AnomalyScorer] | None = None,
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
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
        self._mode: Mode = mode
        self._residual = mode in ("residual", "both")
        self._forest = mode in ("iforest", "both")
        self.name = {"residual": "B2-residual", "iforest": "B2-iforest", "both": "B2"}[
            mode
        ]
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError(f"seed must be an integer, got {seed!r}")  # noqa: TRY004
        self._seed = seed
        self._z_threshold = self._check_z(z_threshold)
        self._score_quantile = self._check_quantile(score_quantile)
        if self._residual and forecaster is None:
            raise ValueError(f"mode {mode!r} needs a forecaster")
        if self._forest and plan_for_day is None:
            raise ValueError(
                f"mode {mode!r} needs plan_for_day: the schedule features of the training and calibration days "
                "need their care plans, which fit() does not receive (ADR-062)"
            )
        self._forecaster = forecaster
        self._predict: Callable[..., Any] | None = (
            None if forecaster is None else forecaster.predict
        )
        self._with_signal = self._predict is not None and _accepts_signal(self._predict)
        self._signals = self._resolve_signals(signals, forecaster)
        self._feature_step = self._check_feature_step(feature_step_ms)
        self._plan_for_day = plan_for_day
        self._scorer_factory: Callable[[int], AnomalyScorer] = (
            IsolationForestScorer if scorer_factory is None else scorer_factory
        )
        self._reset_state()

    # -- construction helpers ----------------------------------------------------------------------------------

    def _check_z(self, value: object) -> float | None:
        if not self._residual:
            if value is not None:
                raise ValueError(
                    f"z_threshold is not used by mode {self._mode!r}; leave it None"
                )
            return None
        if value is None:
            raise ValueError(f"mode {self._mode!r} needs z_threshold (no default)")
        z = _number(value, "z_threshold")
        if not (math.isfinite(z) and z > 0.0):
            raise ValueError(f"z_threshold must be a positive finite number, got {z!r}")
        return z

    def _check_quantile(self, value: object) -> float | None:
        if not self._forest:
            if value is not None:
                raise ValueError(
                    f"score_quantile is not used by mode {self._mode!r}; leave it None"
                )
            return None
        if value is None:
            raise ValueError(f"mode {self._mode!r} needs score_quantile (no default)")
        q = _number(value, "score_quantile")
        if not 0.0 <= q <= 1.0:
            raise ValueError(f"score_quantile must lie in [0, 1], got {q!r}")
        return q

    def _check_feature_step(self, value: object) -> int:
        step = self._timing.step_ms
        if value is None:
            return step
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"feature_step_ms must be an integer, got {value!r}")  # noqa: TRY004
        if value <= 0 or value % step != 0:
            raise ValueError(
                f"feature_step_ms must be a positive multiple of step_ms ({step}), got {value}"
            )
        return value

    def _resolve_signals(
        self, signals: Sequence[str] | None, forecaster: Forecaster | None
    ) -> tuple[str, ...]:
        supported: frozenset[str] | None = (
            frozenset(forecaster.supported_signals)
            if forecaster is not None and self._residual
            else None
        )
        if signals is None:
            chosen = tuple(
                s for s in DEFAULT_SIGNALS if supported is None or s in supported
            )
            if not chosen:
                raise ValueError(
                    f"the forecaster supports none of the default signals {DEFAULT_SIGNALS}; name the signals"
                )
            return chosen
        names = tuple(str(getattr(s, "value", s)) for s in signals)
        if not names:
            raise ValueError("signals must name at least one signal")
        for index, name in enumerate(names):
            if name in names[:index]:
                raise ValueError(f"signal {name!r} is given twice")
            if supported is not None and name not in supported:
                raise ValueError(
                    f"signal {name!r} is not supported by the forecaster (supported: {sorted(supported)})"
                )
        return names

    def _reset_state(self) -> None:
        self._scales: dict[str, B2ResidualScale] = {}
        self._calibrated_for: str | None = None
        self._means: Matrix = np.zeros(0, dtype=np.float64)
        self._scorer: AnomalyScorer | None = None
        self._threshold: float | None = None
        self._residuals: tuple[B2Residual, ...] = ()
        self._iforest_rows: tuple[B2IForestRow, ...] = ()
        self._run_stats: B2RunStats | None = None

    # -- what the last fit and run produced --------------------------------------------------------------------

    @property
    def mode(self) -> Mode:
        return self._mode

    @property
    def signals(self) -> tuple[str, ...]:
        """The monitored signals."""
        return self._signals

    @property
    def z_threshold(self) -> float | None:
        return self._z_threshold

    @property
    def score_quantile(self) -> float | None:
        return self._score_quantile

    @property
    def seed(self) -> int:
        return self._seed

    @property
    def feature_step_ms(self) -> int:
        return self._feature_step

    @property
    def residual_scales(self) -> dict[str, B2ResidualScale]:
        """Mean and standard deviation of the calibration residuals, for each signal that has a scale."""
        return dict(self._scales)

    @property
    def iforest_threshold(self) -> float | None:
        """The ``score_quantile`` quantile of the calibration scores; ``None`` before ``fit`` or without calibration rows."""
        return self._threshold

    @property
    def residuals(self) -> tuple[B2Residual, ...]:
        """The residuals of the last ``run``, with ``z`` and the outcome."""
        return self._residuals

    @property
    def iforest_rows(self) -> tuple[B2IForestRow, ...]:
        """The rows of the last ``run`` with their scores, in time order."""
        return self._iforest_rows

    @property
    def run_stats(self) -> B2RunStats | None:
        """The counters of the last ``run``; ``None`` before the first one and after a ``fit``."""
        return self._run_stats

    # -- causal delivery, with the lateness rule of the grid ---------------------------------------------------

    def _delivered(
        self, day: ObservedDay, end: int, counts: _Counts, *, events: bool
    ) -> Iterator[StepBatch]:
        """The batches of ``day`` up to ``end`` with the inputs B2 uses (late ones dropped and counted)."""
        timing = self._timing
        step, delay = timing.step_ms, timing.reorder_delay_ms
        t0 = day.day_index * _T_DAY_MS
        monitored = frozenset(self._signals)
        previous: int | None = None
        for batch in iter_steps(day, timing, end):
            # the steps of the device-time grid that were final at the previous batch (the lateness rule of the monitor
            # and of B1, B3, B4 and B5)
            final = -1 if previous is None else (previous - t0 - delay) // step
            samples: list[Sample] = []
            for sample in batch.samples:
                if sample.signal not in monitored:
                    continue
                if max(0, -(-(sample.t_device_ms - t0) // step)) <= final:
                    counts.late += 1
                    continue
                samples.append(sample)
            kept = []
            if events:
                for event in batch.events:
                    if event.kind is not EventKind.DISPENSE:
                        continue
                    if max(0, -(-(event.t_device_ms - t0) // step)) <= final:
                        counts.late_events += 1
                        continue
                    kept.append(event)
            previous = batch.t_ms
            yield StepBatch(batch.t_ms, tuple(samples), tuple(kept))

    # -- residuals of one day, shared by fit and run -----------------------------------------------------------

    def _forecast(
        self, history: Sequence[Sample], t_prev: int, gap: int, signal: str
    ) -> float:
        """The forecast issued at ``t_prev`` for ``gap`` ms later, checked to be the path that was asked for."""
        assert self._predict is not None
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

    def _residual_rows(self, day: ObservedDay) -> tuple[list[B2Residual], _Counts]:
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
        rows: list[B2Residual] = []
        history: dict[str, list[Sample]] = {name: [] for name in self._signals}
        newest: dict[str, Sample] = {}
        for batch in self._delivered(day, end, counts, events=False):
            for sample in batch.samples:
                name = sample.signal
                device = sample.t_device_ms
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
                                    B2Residual(
                                        name,
                                        batch.t_ms,
                                        device,
                                        sample.value,
                                        forecast,
                                        sample.value - forecast,
                                    )
                                )
                history[name].append(sample)
        return rows, counts

    @staticmethod
    def _scale_of(values: Sequence[float]) -> B2ResidualScale:
        n = len(values)
        mean = math.fsum(values) / n
        variance = math.fsum((v - mean) ** 2 for v in values) / n
        return B2ResidualScale(mean, math.sqrt(variance), n)

    # -- feature rows of one day, shared by fit and run --------------------------------------------------------

    def _feature_rows(
        self, day: ObservedDay, schedule: Sequence[int]
    ) -> tuple[list[int], Matrix, _Counts]:
        """The grid times of the rows of the day, the rows (``nan`` for an undefined feature) and the counters."""
        t0 = day.day_index * _T_DAY_MS
        counts = _Counts()
        extractor = FeatureExtractor(self._signals, schedule)
        names = extractor.names
        grid: list[int] = []
        rows: list[list[float]] = []
        for batch in self._delivered(day, t0 + _T_DAY_MS, counts, events=True):
            row = extractor.push(batch)
            offset = batch.t_ms - t0
            if offset < _T_DAY_MS and offset % self._feature_step == 0:
                grid.append(batch.t_ms)
                values = [row[n] for n in names]
                rows.append([math.nan if v is None else v for v in values])
        matrix = np.array(rows, dtype=np.float64).reshape(len(rows), len(names))
        return grid, matrix, counts

    def _imputed(self, matrix: Matrix) -> Matrix:
        return np.where(np.isnan(matrix), self._means, matrix)

    def _scores(self, matrix: Matrix) -> Matrix:
        assert self._scorer is not None
        if len(matrix) == 0:
            return np.zeros(0, dtype=np.float64)
        scores = np.asarray(self._scorer.score(self._imputed(matrix)), dtype=np.float64)
        if scores.shape != (len(matrix),):
            raise ValueError(
                f"the scorer returned {scores.shape} scores for {len(matrix)} rows"
            )
        if not np.all(np.isfinite(scores)) or np.any(scores < 0.0):
            raise ValueError(
                "the scorer returned a score that is not a finite number of at least 0"
            )
        return scores

    def _plan(self, day: ObservedDay) -> CarePlan:
        assert self._plan_for_day is not None
        return logged_plan(self._plan_for_day(day), self.read_log)

    # -- fit ---------------------------------------------------------------------------------------------------

    def _fit(self, train: Sequence[GuardedDay], calib: Sequence[GuardedDay]) -> None:
        self._reset_state()
        train_days = [g.observed for g in train]
        calib_days = [g.observed for g in calib]
        if self._residual:
            assert self._forecaster is not None
            self._forecaster.fit(train_days)
            self._calibrated_for = self._forecaster.model_version
            by_signal: dict[str, list[float]] = {n: [] for n in self._signals}
            for day in calib_days:
                rows, _ = self._residual_rows(day)
                for row in rows:
                    by_signal[row.signal].append(row.residual)
            self._scales = {
                name: self._scale_of(values)
                for name, values in by_signal.items()
                if len(values) >= _MIN_RESIDUALS_FOR_SCALE
            }
        if self._forest:
            self._fit_forest(train_days, calib_days)

    def _fit_forest(
        self, train_days: Sequence[ObservedDay], calib_days: Sequence[ObservedDay]
    ) -> None:
        if not train_days:
            raise ValueError(
                "the isolation forest needs at least one training day to fit on"
            )
        assert self._score_quantile is not None
        blocks = [
            self._feature_rows(day, self._plan(day).schedule)[1] for day in train_days
        ]
        train_matrix = np.concatenate(blocks, axis=0)
        means = np.zeros(train_matrix.shape[1], dtype=np.float64)
        for j in range(train_matrix.shape[1]):
            column = train_matrix[:, j]
            defined = column[~np.isnan(column)]
            # algorithmic: a column with no defined value is constant, so its fill value carries no information
            means[j] = float(defined.mean()) if defined.size else 0.0
        scorer = self._scorer_factory(self._seed)
        self._means = means
        scorer.fit(self._imputed(train_matrix))
        self._scorer = scorer
        calibration: list[float] = []
        for day in calib_days:
            matrix = self._feature_rows(day, self._plan(day).schedule)[1]
            calibration.extend(float(s) for s in self._scores(matrix))
        self._threshold = (
            float(np.quantile(np.asarray(calibration), self._score_quantile))
            if calibration
            else None
        )

    # -- run ---------------------------------------------------------------------------------------------------

    def _check_fresh(self) -> None:
        assert self._forecaster is not None
        model = self._forecaster.model_version
        if self._calibrated_for is None or self._calibrated_for != model:
            raise StaleCalibratorError(
                f"the residual scale was estimated for {self._calibrated_for!r}, the forecaster is {model!r}: "
                "fit B2 again"
            )

    def _z(self, row: B2Residual) -> float | None:
        scale = self._scales.get(row.signal)
        if scale is None:
            return None
        if scale.std > 0.0:
            return (row.residual - scale.mean) / scale.std
        return (
            0.0
            if row.residual == scale.mean
            else math.copysign(math.inf, row.residual - scale.mean)
        )

    def _run(self, day: ObservedDay, plan: CarePlan) -> Sequence[Detection]:
        detections: list[Detection] = []
        counts = _Counts()
        feature_counts = _Counts()
        results: list[B2Residual] = []
        if self._residual:
            assert self._z_threshold is not None
            self._check_fresh()
            rows, counts = self._residual_rows(day)
            for row in rows:
                z = self._z(row)
                alarm = z is not None and abs(z) > self._z_threshold
                if alarm:
                    assert z is not None
                    detections.append(
                        Detection(row.t_ms, None, _ratio(abs(z), self._z_threshold))
                    )
                results.append(replace(row, z=z, alarm=alarm))
        forest_rows: list[B2IForestRow] = []
        if self._forest:
            grid, matrix, feature_counts = self._feature_rows(day, plan.schedule)
            scores = self._scores(matrix)
            threshold = self._threshold
            flags = [threshold is not None and float(s) > threshold for s in scores]
            for t, s, flag in zip(grid, scores, flags, strict=True):
                ratio = None if threshold is None else _ratio(float(s), threshold)
                forest_rows.append(B2IForestRow(t, float(s), ratio, flag))
            for index in rising_edges(flags):
                ratio = forest_rows[index].ratio
                assert ratio is not None
                detections.append(Detection(grid[index], None, ratio))
        self._residuals = tuple(results)
        self._iforest_rows = tuple(forest_rows)
        self._run_stats = B2RunStats(
            len(results),
            counts.late if self._residual else feature_counts.late,
            feature_counts.late_events,
            counts.non_finite,
            counts.not_newer,
            counts.no_forecast,
            tuple(n for n in self._signals if n not in self._scales)
            if self._residual
            else (),
            len(forest_rows),
            (self._threshold is not None) if self._forest else None,
        )
        return detections
