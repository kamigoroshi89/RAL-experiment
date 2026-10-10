"""Raw robustness of a template instance on the monitor grid, for the baselines B3 and B5 (WS06-T06; WS06-T04).

Entry point of the spec package that this module wraps: ``ralmon.monitor.make_point_evaluator`` (WS05-T04,
ADR-053 (c); the spike of WS05-T02 found that RTAMT cannot host the templates, ADR-013 outcome C). The wrapper builds
nothing of the STL semantics: it passes the instance, the registry and the values of a step to the point evaluator
and returns its answer, a raw robustness in ``Template.unit`` (never scaled, never clipped, possibly minus or plus
infinity for a failed Boolean guard) or ``None`` while the instance is open or an atom is undefined.

Public names (the contract that WS06-T04 describes, extended where the point evaluator needs more):

* ``RawRobustnessEvaluator``: ``unit``, ``reset(instance)`` (a fresh online evaluation of one instance) and
  ``step(t_ms, values) -> float | None``. The steps are consecutive from step 0 of the axis of the instance
  (``PointEvaluator`` rule), so a caller that works on a continuing axis shifts the anchor of the instance and the
  times of the steps by a multiple of the day: the baselines run one day at a time with empty carry-over state
  (ADR-061, proposed), and this is what ``SignalGrid(origin_ms=...)`` does for the values.
* ``TemplateRawEvaluator`` and ``make_evaluator(template, registry, step_ms, anchor_kind=None)``: the real adapter.
  ``step_ms`` and ``anchor_kind`` are needed by the point evaluator and are not in the two-argument text of the
  WS06-T04 task; the later task reconciles. Parameters that an instance omits come from the registry, as in the
  monitor (ADR-047 (g)); a name that is not a parameter of the template is an error of the point evaluator.
* ``LoggingRegistry``: ``AuditedRegistry`` that also forwards ``overrides()`` and ``step_ms``, which the point
  evaluator reads, so that the audit log and the approved-range rule of ADR-047 (g) work together.
* ``SignalGrid`` and ``GridStep``: the ``values`` of each step, built incrementally from the harness batches with the
  signal construction of ``ralmon.signals`` (held signals, one-step impulse counts, the derived signals fed in
  device-time order with a clock sample at every step; the construction of the monitor tests, ``step_values``).
  Inputs that arrive older than the state they would overwrite are not applied to that state. The level of
  ``presence`` is the held level of the last sample: the construction of ADR-054 (a level per co-location episode,
  an unavailable channel) is not done, so an INT result on a generated day is not evidence until ADR-054 is decided.
"""

from __future__ import annotations

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
from ralmon.spec import RobustnessUnit, Template, TemplateInstance

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
    SignalId.PRESENCE.value,
)
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

    @property
    def unit(self) -> RobustnessUnit:
        return self._template.unit

    def reset(self, instance: TemplateInstance) -> None:
        self._inner = make_point_evaluator(
            self._template,
            instance,
            self._registry,
            self._step_ms,
            anchor_kind=self._anchor_kind,
        )

    def step(self, t_ms: TimeMs, values: Mapping[str, float | None]) -> float | None:
        if self._inner is None:
            raise RuntimeError("reset(instance) must be called before step")
        return self._inner.step(t_ms, values)


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
    """The values of one step on the axis of the day and the anchors that its events open.

    ``k`` is the step index on the axis of the day (0 at the origin); ``values`` is the argument of
    ``RawRobustnessEvaluator.step``; ``measurements`` and ``dispenses`` are the device times, on the axis of the
    day, of the MEASUREMENT and DISPENSE events delivered at this step (they anchor RANGE and SYS, and HOLD, COUNT,
    RESP and INT).
    """

    k: int
    values: dict[str, float | None]
    measurements: tuple[int, ...]
    dispenses: tuple[int, ...]


class SignalGrid:
    """Builds the ``values`` of each step from the harness batches (see the module docstring).

    ``origin_ms`` is the time of step 0 on the continuing axis (the start of the day); every device time is shifted
    by it. ``delay_ms`` is the reorder delay of the harness: the clock of the derived signals at a step is
    ``t - delay_ms``, the device time up to which the step has delivered inputs.
    """

    def __init__(self, step_ms: int, *, delay_ms: int = 0, origin_ms: int = 0) -> None:
        if step_ms <= 0:
            raise ValueError(f"step_ms must be positive, got {step_ms}")
        self._step = step_ms
        self._delay = delay_ms
        self._origin = origin_ms
        self._held: dict[str, float] = {}
        self._held_time: dict[str, int] = {}
        self._derived: list[DerivedSignal] = list(default_derived_signals())
        self._derived_last: dict[str, float] = {}

    def _feed(self, sample: Sample) -> None:
        for derived in self._derived:
            try:
                out = derived.update(sample)
            except ValueError:
                continue  # older than the clock of this derived signal: it is not part of its state
            if out is not None:
                self._derived_last[out.signal] = out.value

    def apply(self, batch: StepBatch) -> GridStep:
        origin = self._origin
        t_local = batch.t_ms - origin
        counts = dict.fromkeys(_IMPULSES, 0)
        measurements: list[int] = []
        dispenses: list[int] = []
        for item in batch.inputs():
            device = item.t_device_ms - origin
            if isinstance(item, Sample):
                if item.signal in _HELD:
                    if device >= self._held_time.get(item.signal, device):
                        self._held[item.signal] = item.value
                        self._held_time[item.signal] = device
                elif item.signal == SignalId.AUTH.value:
                    counts[SignalId.AUTH.value] += 1
                if item.signal != SignalId.AUTH.value:
                    self._feed(
                        replace(item, t_device_ms=device, t_rx_ms=item.t_rx_ms - origin)
                    )
            else:
                self._event(item, device, counts, measurements, dispenses)
        clock = t_local - self._delay
        self._feed(Sample(_CLOCK_SIGNAL, clock, clock, 0.0, None, None))
        values: dict[str, float | None] = dict(self._held)
        for name in _IMPULSES:
            values[name] = float(counts[name])
        values.update(self._derived_last)
        return GridStep(
            t_local // self._step, values, tuple(measurements), tuple(dispenses)
        )

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
