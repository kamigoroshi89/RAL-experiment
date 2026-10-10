"""Raw robustness of a template instance on the monitor grid, for the baselines B3 and B5 (WS06-T06; WS06-T04).

Entry point of the spec package that this module wraps: ``ralmon.monitor.make_point_evaluator`` (WS05-T04,
ADR-053 (c); the spike of WS05-T02 found that RTAMT cannot host the templates, ADR-013 outcome C). The wrapper builds
nothing of the STL semantics: it passes the instance, the registry and the values of a step to the point evaluator
and returns its answer, a raw robustness in ``Template.unit`` (never scaled, never clipped, possibly minus or plus
infinity for a failed Boolean guard) or ``None`` while the instance is open or an atom is undefined. The answer is a value only when the interval of the
instance is a point: an instance that the monitor decides VIOLATED from the sign of the upper bound of a wider interval
(INT with an undefined or unavailable step in its history and no witness since) stays ``None``, so the baselines built
on this module do not detect it (Notes of WS06-T04).

Public names (the contract that WS06-T04 describes, extended where the point evaluator needs more):

* ``RawRobustnessEvaluator``: ``unit``, ``reset(instance)`` (a fresh online evaluation of one instance) and
  ``step(t_ms, values) -> float | None``. The steps are consecutive from step 0 of the axis of the instance
  (``PointEvaluator`` rule), so a caller that works on a continuing axis shifts the anchor of the instance and the
  times of the steps by a multiple of the day: the baselines run one day at a time with empty carry-over state
  (ADR-061, proposed), and this is what ``SignalGrid(origin_ms=...)`` does for the values.
* ``TemplateRawEvaluator`` and ``make_evaluator(template, registry, step_ms, anchor_kind=None)``: the real adapter.
  ``step_ms`` and ``anchor_kind`` are needed by the point evaluator and are not in the two-argument text of the
  WS06-T04 task (reconciled there: B3 passes them as B5 does). Parameters that an instance omits come from the
  registry, as in the monitor (ADR-047 (g)); a name that is not a parameter of the template, and a value that
  differs from the registry outside an approved range, are errors of the point evaluator (``PlanFeasibilityError``),
  never ignored. The adapter has the optional member ``done``: true once the value of an instance other than SCHED is
  final, so that a baseline need not step it again.
* ``LoggingRegistry``: ``AuditedRegistry`` that also forwards ``overrides()`` and ``step_ms``, which the point
  evaluator reads, so that the audit log and the approved-range rule of ADR-047 (g) work together.
* ``SignalGrid`` and ``GridStep``: the ``values`` of each step of the device-time grid, built incrementally from the
  harness batches with the signal construction of ``ralmon.signals`` (held signals, one-step impulse counts, the
  derived signals fed in device-time order with a clock sample at every step; the construction of the monitor
  tests, ``step_values``). The step ``j`` is final at ``j * step_ms + delay_ms`` as in ``run_offline``, and an input
  that arrives after its step is final is late and dropped, as in the monitor.

  The robot channels follow ADR-054 (b), accepted 2026-10-09, as ``StreamingMonitor.push_event`` applies it: a
  ``NODE_STATE`` event of source ``robot`` with a boolean ``payload.colocated`` is an availability mark of both
  ``presence`` and ``intake``, ordered before the samples of its device time. The level of ``presence`` belongs to
  one co-location episode: ``None`` while the channel is down (as ``intake``, never a zero), absent (undefined)
  from the step at which it returns until the first sample of the new episode, and cleared by the first mark of
  the run if that mark is a report. A trace with no report is read as before (the channels are available until
  marked, the level is held for the rest of the day, the documented hazard), and
  ``presence_samples_without_availability_marks`` is the gate of that hazard with the definition of
  ``MonitorStats``: the presence samples applied before the first mark. A result that rests on the INT template is
  evidence only if the gate is 0; the grid has no ``push_availability`` (an ``ObservedDay`` carries no
  availability stream).
"""

from __future__ import annotations

import heapq
import math
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any, Final, Protocol, runtime_checkable

from ralmon.baselines.access import AuditedRegistry
from ralmon.baselines.base import StepBatch
from ralmon.monitor import PointEvaluator, make_point_evaluator
from ralmon.signals import (
    DerivedSignal,
    Event,
    EventKind,
    Sample,
    SignalId,
    TimeMs,
    default_derived_signals,
    event_to_sample,
)
from ralmon.spec import RobustnessUnit, Template, TemplateId, TemplateInstance

__all__ = [
    "GridStep",
    "LoggingRegistry",
    "RawRobustnessEvaluator",
    "SignalGrid",
    "TemplateRawEvaluator",
    "make_evaluator",
]

_HELD: Final = (
    SignalId.BP.value,
    SignalId.CUFF_HEALTH.value,
    SignalId.INFLATION_MS.value,
)
_ROBOT_SOURCE: Final = "robot"  # the source of the NODE_STATE reports of the robot node
_KEY_COLOCATED: Final = "colocated"
_IMPULSES: Final = (
    SignalId.MEAS.value,
    SignalId.DISPENSE.value,
    SignalId.INTAKE.value,
    SignalId.SCHED_TICK.value,
    SignalId.AUTH.value,
)
# no derived signal reads this signal: a sample of it only advances the clock of the derived signals
_CLOCK_SIGNAL: Final = SignalId.SPO2.value


@runtime_checkable
class RawRobustnessEvaluator(Protocol):
    """One template instance stepped on the grid; the answer is the raw robustness or ``None``."""

    @property
    def unit(self) -> RobustnessUnit: ...

    def reset(self, instance: TemplateInstance) -> None: ...

    def step(
        self, t_ms: TimeMs, values: Mapping[str, float | None]
    ) -> float | None: ...


class TemplateRawEvaluator:
    """The point evaluator of ``ralmon.monitor`` behind the ``RawRobustnessEvaluator`` protocol."""

    def __init__(
        self,
        template: Template,
        registry: Any,
        step_ms: int,
        *,
        anchor_kind: str | None = None,
    ) -> None:
        self._template = template
        self._registry = registry
        self._step_ms = step_ms
        self._anchor_kind = anchor_kind
        self._inner: PointEvaluator | None = None
        self._value: float | None = None

    @property
    def unit(self) -> RobustnessUnit:
        return self._template.unit

    @property
    def done(self) -> bool:
        """Whether the value is final and the evaluator need not be stepped again.

        True once an instance of a template other than SCHED has a value: the point evaluator freezes such an
        instance when it decides (SCHED keeps grading the lateness of the first measurement after its deadline).
        This is an optional member of the protocol, a caller that does not know it steps the evaluator to the end.
        """
        return self._value is not None and self._template.id is not TemplateId.SCHED

    def reset(self, instance: TemplateInstance) -> None:
        self._inner = make_point_evaluator(
            self._template,
            instance,
            self._registry,
            self._step_ms,
            anchor_kind=self._anchor_kind,
        )
        self._value = None

    def step(self, t_ms: TimeMs, values: Mapping[str, float | None]) -> float | None:
        if self._inner is None:
            raise RuntimeError("reset(instance) must be called before step")
        self._value = self._inner.step(t_ms, values)
        return self._value


def make_evaluator(
    template: Template,
    registry: Any,
    step_ms: int,
    anchor_kind: str | None = None,
) -> RawRobustnessEvaluator:
    """The default ``evaluator_factory`` of the baselines: a ``TemplateRawEvaluator``."""
    return TemplateRawEvaluator(template, registry, step_ms, anchor_kind=anchor_kind)


class LoggingRegistry(AuditedRegistry):
    """An ``AuditedRegistry`` that forwards what the point evaluator reads besides ``get``, ``bounds``, ``version``."""

    def overrides(self) -> Any:
        getter = getattr(self._inner, "overrides", None)
        return getter() if callable(getter) else []

    @property
    def step_ms(self) -> int | None:
        value = getattr(self._inner, "step_ms", None)
        return value if isinstance(value, int) else None


@dataclass(frozen=True, slots=True)
class GridStep:
    """The values of one step of the device-time grid and the anchors that its events open.

    ``k`` is the step index on the axis of the day (0 at the origin); ``values`` is the argument of
    ``RawRobustnessEvaluator.step``; ``measurements`` and ``dispenses`` are the device times, on the axis of the
    day, of the MEASUREMENT and DISPENSE events applied at this step (they anchor RANGE and SYS, and HOLD, COUNT,
    RESP and INT); ``samples`` are the samples applied at this step, as they were received.
    """

    k: int
    values: dict[str, float | None]
    measurements: tuple[int, ...]
    dispenses: tuple[int, ...]
    samples: tuple[Sample, ...] = ()


# Same order as the reorder buffer of the monitor: events of one device time by kind (a measurement, a dispense, an
# intake, a schedule tick); a sample comes before an event of the same device time.
_EVENT_RANK: Final = {
    EventKind.MEASUREMENT: 0,
    EventKind.DISPENSE: 1,
    EventKind.INTAKE: 2,
    EventKind.SCHEDULE_TICK: 3,
}


def _report_of(item: Sample | Event) -> bool | None:
    """The ``colocated`` flag of a report of the robot that marks its channels, else ``None`` (ADR-054 (b))."""
    if (
        isinstance(item, Event)
        and item.kind is EventKind.NODE_STATE
        and item.source == _ROBOT_SOURCE
    ):
        flag = item.payload.get(_KEY_COLOCATED)
        if isinstance(flag, bool):
            return flag
    return None


class SignalGrid:
    """Builds the ``values`` of each step of the device-time grid from the harness batches.

    The step ``j`` of the grid shows the inputs with device time up to ``j * step_ms`` (the ceiling rule of
    docs/formal/01 section 3.3) and is final at the monitor time ``j * step_ms + delay_ms``, the cadence of
    ``run_offline``. ``apply(batch)`` buffers the inputs of a harness batch and returns the steps that the batch
    makes final: none while the reorder delay has not elapsed, one per batch when ``delay_ms`` is 0 (several if a
    batch jumps). An input that arrives after its step is final is late, as in the monitor, and is counted in
    ``late`` and not applied. ``origin_ms`` is the time of step 0 on the continuing axis (the start of the day);
    every device time is shifted by it.
    """

    def __init__(self, step_ms: int, *, delay_ms: int = 0, origin_ms: int = 0) -> None:
        if step_ms <= 0:
            raise ValueError(f"step_ms must be positive, got {step_ms}")
        if delay_ms < 0:
            raise ValueError(f"delay_ms must not be negative, got {delay_ms}")
        self._step = step_ms
        self._delay = delay_ms
        self._origin = origin_ms
        self._held: dict[str, float] = {}
        self._presence = (
            math.nan
        )  # the level of the current co-location episode (NaN: undefined)
        self._presence_off = False
        self._intake_off = False
        self._marks = 0
        self.availability_reports = 0
        self.presence_samples_without_availability_marks = 0
        self._derived: list[DerivedSignal] = list(default_derived_signals())
        self._derived_last: dict[str, float] = {}
        self._pending: list[tuple[tuple[int, ...], int, Sample | Event]] = []
        self._arrivals = 0
        self._next = 0
        self.late = 0

    @staticmethod
    def _key(item: Sample | Event, device: int) -> tuple[int, ...]:
        has_seq = item.seq is not None
        secondary = item.seq if item.seq is not None else item.t_rx_ms
        if isinstance(item, Sample):
            return (device, 1, 0, 0 if has_seq else 1, secondary)
        if (
            _report_of(item) is not None
        ):  # an availability mark goes before a sample (reorder buffer)
            return (device, 0, 0, 0 if has_seq else 1, secondary)
        return (
            device,
            2,
            _EVENT_RANK.get(item.kind, 0),
            0 if has_seq else 1,
            secondary,
        )

    def _feed(self, sample: Sample) -> None:
        for derived in self._derived:
            try:
                out = derived.update(sample)
            except ValueError:
                continue  # older than the clock of this derived signal: it is not part of its state
            if out is not None:
                self._derived_last[out.signal] = out.value

    def apply(self, batch: StepBatch) -> tuple[GridStep, ...]:
        origin, step = self._origin, self._step
        for item in batch.inputs():
            device = item.t_device_ms - origin
            if max(0, -(-device // step)) < self._next:
                self.late += 1  # its step is final already
                continue
            heapq.heappush(
                self._pending, (self._key(item, device), self._arrivals, item)
            )
            self._arrivals += 1
        last = (batch.t_ms - origin - self._delay) // step
        steps: list[GridStep] = []
        while self._next <= last:
            steps.append(self._finalise(self._next))
            self._next += 1
        return tuple(steps)

    def _finalise(self, j: int) -> GridStep:
        origin = self._origin
        limit = j * self._step
        counts = dict.fromkeys(_IMPULSES, 0)
        measurements: list[int] = []
        dispenses: list[int] = []
        applied: list[Sample] = []
        while self._pending and self._pending[0][0][0] <= limit:
            item = heapq.heappop(self._pending)[2]
            device = item.t_device_ms - origin
            if isinstance(item, Sample):
                applied.append(item)
                if item.signal in _HELD:
                    self._held[item.signal] = item.value
                elif item.signal == SignalId.PRESENCE.value:
                    self._presence = item.value
                    if self._marks == 0:
                        self.presence_samples_without_availability_marks += 1
                elif item.signal == SignalId.AUTH.value:
                    counts[SignalId.AUTH.value] += 1
                if item.signal != SignalId.AUTH.value:
                    self._feed(
                        replace(item, t_device_ms=device, t_rx_ms=item.t_rx_ms - origin)
                    )
            elif (colocated := _report_of(item)) is not None:
                self._mark(colocated)
            else:
                self._event(item, device, counts, measurements, dispenses)
        self._feed(Sample(_CLOCK_SIGNAL, limit, limit, 0.0, None, None))
        values: dict[str, float | None] = dict(self._held)
        for name in _IMPULSES:
            values[name] = float(counts[name])
        # the robot channels: None while the channel is down, never a zero; the level of presence is absent while
        # it is undefined (ADR-054)
        if self._intake_off:
            values[SignalId.INTAKE.value] = None
        if self._presence_off:
            values[SignalId.PRESENCE.value] = None
            self._presence = (
                math.nan
            )  # the level belongs to one episode: a step that is down clears it
        elif not math.isnan(self._presence):
            values[SignalId.PRESENCE.value] = self._presence
        values.update(self._derived_last)
        return GridStep(
            j, values, tuple(measurements), tuple(dispenses), tuple(applied)
        )

    def _mark(self, available: bool) -> None:
        """A ``colocated`` report: the mark of both robot channels (``StreamingMonitor._apply``)."""
        if self._marks == 0:
            self._presence = (
                math.nan
            )  # the first mark is a report: a level held from before it is no episode
        self._presence_off = not available
        self._intake_off = not available
        self._marks += 1
        self.availability_reports += 1

    def _event(
        self,
        event: Event,
        device: int,
        counts: dict[str, int],
        measurements: list[int],
        dispenses: list[int],
    ) -> None:
        mapped = event_to_sample(event)
        if mapped is None:
            return  # evidence, not a signal
        counts[mapped.signal] += 1
        self._feed(
            replace(
                mapped,
                t_device_ms=device,
                t_rx_ms=event.t_rx_ms - self._origin,
            )
        )
        if event.kind is EventKind.MEASUREMENT:
            measurements.append(device)
        elif event.kind is EventKind.DISPENSE:
            dispenses.append(device)
