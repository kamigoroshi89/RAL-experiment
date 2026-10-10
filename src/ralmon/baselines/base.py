"""The ``Detector`` protocol, the ``BaselineBase`` template and the causal step iterator (WS06-T01).

Every baseline B1 to B5 is a subclass of ``BaselineBase`` and is driven by the same code, so none of them
can see more than the proposed method sees (analisi section 10 objection 1). The module fixes the
conventions that WS06-T02 to T07 and WS08-T01 rely on; each is stated here once.

Harness boundary (``BaselineBase``)
-----------------------------------
* ``fit(train_days, calib_days)`` is a template method. The ``BenchmarkDay`` objects are wrapped in
  ``GuardedDay`` views (``ralmon.baselines.access``) with the split label and the ``AccessPolicy``; ``_fit``
  gets only those. A second ``fit`` replaces the state of the first (recalibration semantics, #conformal-calibrator
  rule 4); a ``_fit`` that raises leaves the detector not fitted.
* ``run(day, plan, evidence)`` is a template method. It raises ``LeakageError`` unless ``day`` is an
  ``ObservedDay`` (a benchmark day or a latent day is refused before anything else), then ``NotFittedError``
  before ``fit``. It drops ``evidence`` (baselines do not attribute, analisi section 5.4: this asymmetry is
  documented, not hidden), passes the plan through ``logged_plan`` so that the parameters a baseline reads are
  logged, and validates the output of ``_run``: every item a ``Detection`` with ``label is None``, an integer
  non-negative ``t_ms``, a finite score. The result is a tuple sorted by ``t_ms`` (stable).
* ``Detector.run`` has no ``history`` input yet. ADR-046 accepts a ``history`` for ``run_offline`` and leaves
  the ``Detector`` contract to a separate proposal (ADR-061, proposed): until it is decided a baseline is run
  one day at a time with empty carry-over state, as the monitor is when it is given no history. A counter over
  24 h can then only under-count, for the baselines as for the proposed method run the same way.

Timing conventions (``iter_steps``, ``TimingConfig``)
-----------------------------------------------------
* The grid is ``t = start, start + step_ms, ...`` on the continuing axis of the patient
  (#time-and-units rule 5); ``start`` is ``day_index * 24 h`` unless given. The grid covers ``end_ms``: its
  last point is the first one at or after it.
* Causality is that of ``Monitor.advance``. At step ``t`` an input is delivered iff it has been received
  (``t_rx_ms <= t``) and ``t_device_ms <= t - reorder_delay_ms``. Each input is delivered exactly once, at
  the first step where both hold. A batch is ordered by device time; ties by the rules of the monitor's
  reorder buffer: events by kind (measurement, dispense, intake, schedule tick), then inputs that carry a
  sequence number before those that do not, then ``seq`` (or the receive time when there is none), then the
  order of arrival. ``StepBatch.inputs()`` merges samples and events, a sample first at an equal device time
  (a pressure with the device time of a dispense is the pre-dose value). An input stamped before the first
  step is delivered in the first batch, not dropped.
* The grid time ``t`` is a monitor time: the step ``t`` sees device times up to ``t - reorder_delay_ms``.
  ``run_offline`` calls ``advance(k * T_s + D)``, so its step ``k`` sees device times up to ``k * T_s``. The two
  agree when the grid is shifted by ``D``; the harness keeps the grid at multiples of ``step_ms`` (as the
  task's hand-computed cases require) and WS06-T07 compares detection times with that offset in mind.
* ``Detection.t_ms`` is the grid time at which the detector emits.
* A deadline rule decides at the first step with ``t - reorder_delay_ms >= deadline``, after the inputs of that
  step were delivered: inputs are delivered before deadlines are evaluated at a step.
* Intervals follow the STL formulas: closed windows.
* One ``Detection`` per rising edge for a state-like condition (``rising_edges``), one per input for a
  sample-like condition.
* ``evaluation_end_ms`` is the end of the run: the last receive time of the day or the last tick of the
  plan, whichever is later (never before the start of the day), plus ``tail_ms``, long enough for the
  deadlines opened by the last input to expire. It reads ``plan.schedule`` as a list of ticks of the day.

Numbers. No clinical constant appears here; ``TimingConfig`` carries values the experiment config supplies.
"""

from __future__ import annotations

import heapq
import math
from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Protocol, runtime_checkable

from ralmon.attribution import Detection, EvidenceVector
from ralmon.baselines.access import (
    AccessLog,
    AccessPolicy,
    GuardedDay,
    LeakageError,
    ReadLog,
    Split,
    logged_plan,
)
from ralmon.benchmark import BenchmarkDay, ObservedDay
from ralmon.signals import MS_PER_HOUR, DurationMs, Event, EventKind, Sample, TimeMs
from ralmon.spec import CarePlan

__all__ = [
    "BaselineBase",
    "Detector",
    "InvalidDetectionError",
    "InvalidTimingError",
    "LeakageError",
    "NotFittedError",
    "StepBatch",
    "TimingConfig",
    "evaluation_end_ms",
    "iter_steps",
    "rising_edges",
]

_T_DAY_MS: Final[int] = 24 * MS_PER_HOUR

# Same order as the monitor (``ralmon.monitor.core._EVENT_ORDER``): events of one device time are
# delivered measurement, dispense, intake, schedule tick; any other kind ranks with the measurement.
_EVENT_RANK: Final[dict[EventKind, int]] = {
    EventKind.MEASUREMENT: 0,
    EventKind.DISPENSE: 1,
    EventKind.INTAKE: 2,
    EventKind.SCHEDULE_TICK: 3,
}


class NotFittedError(RuntimeError):
    """``run`` was called before a successful ``fit``."""


class InvalidDetectionError(ValueError):
    """A baseline emitted something that is not a valid unattributed ``Detection``."""


class InvalidTimingError(ValueError):
    """A step, delay, tail or time value is not a valid integer duration or time."""


# Copied verbatim from 02-interfaces.md#detector (version 0.1.0); ``runtime_checkable`` is the only addition.
@runtime_checkable
class Detector(Protocol):
    name: str  # "B1".."B5", "ours", "ours-A1" ...

    def fit(
        self,
        train_days: Sequence[BenchmarkDay],
        calib_days: Sequence[BenchmarkDay],
    ) -> None: ...

    def run(
        self,
        day: ObservedDay,
        plan: CarePlan,
        evidence: Mapping[str, EvidenceVector] | None,
    ) -> Sequence[Detection]: ...


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _check_ms(value: object, what: str, *, positive: bool = False) -> int:
    if not _is_int(value):
        raise InvalidTimingError(
            f"{what} must be an integer number of ms, got {value!r}"
        )
    assert isinstance(value, int)
    if value < 0 or (positive and value == 0):
        raise InvalidTimingError(
            f"{what} must be {'positive' if positive else 'non-negative'}, got {value}"
        )
    return value


@dataclass(frozen=True, slots=True)
class TimingConfig:
    """The time base shared by every baseline and by the monitor of the same experiment.

    ``step_ms`` and ``reorder_delay_ms`` equal the ``MonitorConfig`` fields of the same names; ``tail_ms`` is
    the time after the last input and the last tick that a run continues for, so that open deadlines expire.
    """

    step_ms: DurationMs
    reorder_delay_ms: DurationMs
    tail_ms: DurationMs

    def __post_init__(self) -> None:
        _check_ms(self.step_ms, "step_ms", positive=True)
        _check_ms(self.reorder_delay_ms, "reorder_delay_ms")
        _check_ms(self.tail_ms, "tail_ms")


@dataclass(frozen=True, slots=True)
class StepBatch:
    """The inputs delivered at grid time ``t_ms``, each tuple in delivery order (module docstring)."""

    t_ms: TimeMs
    samples: tuple[Sample, ...]
    events: tuple[Event, ...]

    def inputs(self) -> tuple[Sample | Event, ...]:
        """Samples and events merged by device time, a sample first at an equal device time."""
        merged: list[Sample | Event] = []
        s, e = self.samples, self.events
        i = j = 0
        while i < len(s) or j < len(e):
            if j >= len(e) or (i < len(s) and s[i].t_device_ms <= e[j].t_device_ms):
                merged.append(s[i])
                i += 1
            else:
                merged.append(e[j])
                j += 1
        return tuple(merged)


# heap key: device time, kind rank, no-seq flag, seq or receive time, arrival index (unique, so the item
# itself is never compared)
_Key = tuple[int, int, int, int, int]


def _key(item: Sample | Event, rank: int, arrival: int) -> _Key:
    has_seq = item.seq is not None
    secondary = item.seq if item.seq is not None else item.t_rx_ms
    return (item.t_device_ms, rank, 0 if has_seq else 1, secondary, arrival)


def _arrivals(items: Iterable[Any], what: str) -> list[tuple[int, int, Any]]:
    """``(t_rx_ms, index, item)`` in order of arrival; checks the two clocks of every item."""
    out: list[tuple[int, int, Any]] = []
    for index, item in enumerate(items):
        _check_ms(item.t_device_ms, f"{what}[{index}].t_device_ms")
        _check_ms(item.t_rx_ms, f"{what}[{index}].t_rx_ms")
        if item.seq is not None and not _is_int(item.seq):
            raise InvalidTimingError(f"{what}[{index}].seq must be an integer or None")
        out.append((item.t_rx_ms, index, item))
    out.sort(key=lambda a: (a[0], a[1]))
    return out


def iter_steps(
    day: ObservedDay,
    timing: TimingConfig,
    end_ms: TimeMs,
    *,
    start_ms: TimeMs | None = None,
) -> Iterator[StepBatch]:
    """The batches of a day on the grid of ``timing``, delivered as ``Monitor.advance`` would see them.

    The grid starts at ``start_ms`` (default: ``day.day_index * 24 h``) and covers ``end_ms``. Arguments are
    validated when the function is called, not when the iterator is first advanced.
    """
    if not isinstance(timing, TimingConfig):
        raise InvalidTimingError(f"timing must be a TimingConfig, got {timing!r}")
    end = _check_ms(end_ms, "end_ms")
    day_index = _check_ms(day.day_index, "day_index")
    start = (
        day_index * _T_DAY_MS if start_ms is None else _check_ms(start_ms, "start_ms")
    )
    samples = _arrivals(day.samples, "samples")
    events = _arrivals(day.events, "events")
    return _steps(samples, events, timing, start, end)


def _steps(
    samples: list[tuple[int, int, Sample]],
    events: list[tuple[int, int, Event]],
    timing: TimingConfig,
    start: int,
    end: int,
) -> Iterator[StepBatch]:
    step, delay = timing.step_ms, timing.reorder_delay_ms
    n_steps = max(0, -(-(end - start) // step))
    sample_heap: list[tuple[_Key, Sample]] = []
    event_heap: list[tuple[_Key, Event]] = []
    next_sample = next_event = arrival = 0
    for k in range(n_steps + 1):
        t = start + k * step
        while next_sample < len(samples) and samples[next_sample][0] <= t:
            item = samples[next_sample][2]
            heapq.heappush(sample_heap, (_key(item, 0, arrival), item))
            next_sample += 1
            arrival += 1
        while next_event < len(events) and events[next_event][0] <= t:
            ev = events[next_event][2]
            heapq.heappush(
                event_heap, (_key(ev, _EVENT_RANK.get(ev.kind, 0), arrival), ev)
            )
            next_event += 1
            arrival += 1
        horizon = t - delay
        out_samples: list[Sample] = []
        out_events: list[Event] = []
        while sample_heap and sample_heap[0][0][0] <= horizon:
            out_samples.append(heapq.heappop(sample_heap)[1])
        while event_heap and event_heap[0][0][0] <= horizon:
            out_events.append(heapq.heappop(event_heap)[1])
        yield StepBatch(t, tuple(out_samples), tuple(out_events))


def evaluation_end_ms(day: ObservedDay, plan: CarePlan, tail_ms: DurationMs) -> TimeMs:
    """The end of a run: ``max(last receive time, last plan tick, day start) + tail_ms`` (module docstring)."""
    tail = _check_ms(tail_ms, "tail_ms")
    last = _check_ms(day.day_index, "day_index") * _T_DAY_MS
    for sample in day.samples:
        last = max(last, _check_ms(sample.t_rx_ms, "t_rx_ms"))
    for event in day.events:
        last = max(last, _check_ms(event.t_rx_ms, "t_rx_ms"))
    for tick in plan.schedule:
        last = max(last, _check_ms(tick, "schedule tick"))
    return last + tail


def rising_edges(flags: Iterable[bool]) -> list[int]:
    """The indices where a condition turns true (the first index counts if it starts true)."""
    edges: list[int] = []
    previous = False
    for index, flag in enumerate(flags):
        if flag and not previous:
            edges.append(index)
        previous = bool(flag)
    return edges


def _validate_detections(raw: object, who: str) -> tuple[Detection, ...]:
    if isinstance(raw, (str, bytes)):
        raise InvalidDetectionError(
            f"{who}: the output must be a sequence of Detection"
        )
    try:
        items = list(raw)  # type: ignore[call-overload]
    except TypeError as exc:
        raise InvalidDetectionError(
            f"{who}: the output must be a sequence of Detection, got {raw!r}"
        ) from exc
    for index, item in enumerate(items):
        if not isinstance(item, Detection):
            raise InvalidDetectionError(
                f"{who}: item {index} is not a Detection: {item!r}"
            )
        if item.label is not None:
            raise InvalidDetectionError(
                f"{who}: item {index} has label {item.label!r}; baselines do not attribute (label is None)"
            )
        if not _is_int(item.t_ms) or item.t_ms < 0:
            raise InvalidDetectionError(
                f"{who}: item {index} has t_ms {item.t_ms!r}, expected a non-negative integer"
            )
        score = item.score
        if (
            isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not math.isfinite(score)
        ):
            raise InvalidDetectionError(
                f"{who}: item {index} has score {score!r}, expected a finite number"
            )
    items.sort(key=lambda d: d.t_ms)  # stable
    return tuple(items)


class BaselineBase(ABC):
    """Template for B1 to B5: a ``Detector`` whose inputs and outputs are checked at one boundary.

    Subclasses set ``name`` (a class attribute), implement ``_fit`` and ``_run`` and read time only through
    ``iter_steps`` / ``_steps``. They may keep their own constructor arguments and call ``super().__init__``.
    ``access_log`` and ``read_log`` expose what ``fit`` and ``run`` read (WS06-T07); both can be injected to
    share a log across detectors, and ``clear()`` resets them between runs.
    """

    name: str

    def __init__(
        self,
        timing: TimingConfig,
        *,
        access_policy: AccessPolicy | None = None,
        access_log: AccessLog | None = None,
        read_log: ReadLog | None = None,
    ) -> None:
        if not isinstance(timing, TimingConfig):
            raise InvalidTimingError(f"timing must be a TimingConfig, got {timing!r}")
        self._timing = timing
        self._policy = AccessPolicy() if access_policy is None else access_policy
        self.access_log = AccessLog() if access_log is None else access_log
        self.read_log = ReadLog() if read_log is None else read_log
        self._fitted = False

    @property
    def timing(self) -> TimingConfig:
        return self._timing

    @property
    def access_policy(self) -> AccessPolicy:
        return self._policy

    @property
    def is_fitted(self) -> bool:
        return self._fitted

    def fit(
        self,
        train_days: Sequence[BenchmarkDay],
        calib_days: Sequence[BenchmarkDay],
    ) -> None:
        train = self._guard(train_days, Split.TRAIN, "train_days")
        calib = self._guard(calib_days, Split.CALIB, "calib_days")
        self._fitted = False
        self._fit(train, calib)
        self._fitted = True

    def run(
        self,
        day: ObservedDay,
        plan: CarePlan,
        evidence: Mapping[str, EvidenceVector] | None = None,
    ) -> Sequence[Detection]:
        if not isinstance(day, ObservedDay):
            raise LeakageError(
                f"{type(day).__name__} is not an ObservedDay; a detector runs on the observed trace only"
            )
        if not self._fitted:
            raise NotFittedError(f"{type(self).__name__}.run was called before fit")
        _ = evidence  # dropped at the harness boundary: baselines do not attribute
        return _validate_detections(
            self._run(day, logged_plan(plan, self.read_log)), type(self).__name__
        )

    @abstractmethod
    def _fit(self, train: Sequence[GuardedDay], calib: Sequence[GuardedDay]) -> None:
        """Fit on guarded days; replace any earlier state."""

    @abstractmethod
    def _run(self, day: ObservedDay, plan: CarePlan) -> Sequence[Detection]:
        """Detections for one observed day; the plan is the logged copy."""

    def _steps(self, day: ObservedDay, plan: CarePlan) -> Iterator[StepBatch]:
        """The batches of ``day`` up to ``evaluation_end_ms`` on this detector's timing."""
        return iter_steps(
            day, self._timing, evaluation_end_ms(day, plan, self._timing.tail_ms)
        )

    def _guard(
        self, days: Sequence[BenchmarkDay], split: Split, what: str
    ) -> list[GuardedDay]:
        guarded: list[GuardedDay] = []
        for index, item in enumerate(days):
            if not isinstance(item, BenchmarkDay):
                raise TypeError(
                    f"{what}[{index}] must be a BenchmarkDay, got {type(item).__name__}"
                )
            guarded.append(GuardedDay(item, split, self.access_log, self._policy))
        return guarded
