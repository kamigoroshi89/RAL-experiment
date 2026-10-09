"""Event to sample mapping, impulses on the monitor grid, the ObservedTrace Protocol.

``Sample``, ``Event`` and ``EventKind`` are defined once in ``ralmon.signals.trace_types``
(WS04-T01) and are imported here, never redefined. Semantics: docs/formal/01-signals-sampling.md
sections 2.2 (transport form), 3.3 (ceiling rule) and 3.4 (multiplicity).
"""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Mapping, Sequence
from itertools import pairwise
from types import MappingProxyType
from typing import Final, Protocol, runtime_checkable

from ralmon.signals.ids import SignalId
from ralmon.signals.trace_types import Event, EventKind, Sample
from ralmon.signals.units import TimeMs

# Events that are signals: the four impulses of section 2.1. MEASUREMENT_MISSED,
# NODE_STATE, ROBOT_TASK, DEVICE_ERROR and VERIFICATION are evidence for the attribution layer, not
# signals (section 2.1, `meas` row; 02-interfaces.md#evidencevector).
_EVENT_SIGNAL: Final[Mapping[EventKind, SignalId]] = MappingProxyType(
    {
        EventKind.MEASUREMENT: SignalId.MEAS,
        EventKind.DISPENSE: SignalId.DISPENSE,
        EventKind.INTAKE: SignalId.INTAKE,
        EventKind.SCHEDULE_TICK: SignalId.SCHED_TICK,
    }
)


@runtime_checkable
class ObservedTrace(Protocol):
    """Structural view of an observed patient-day (``ObservedDay`` satisfies it).

    Read-only properties, so that a frozen dataclass with these fields conforms. Monitor
    inputs are annotated with this Protocol so that ``monitor`` never imports
    ``benchmark`` (decision D2 of WS05). It deliberately has no latent or ground-truth
    member: the monitor sees only the observed trace.
    """

    @property
    def patient_id(self) -> str: ...

    @property
    def day_index(self) -> int: ...

    @property
    def seed(self) -> int: ...

    @property
    def samples(self) -> Sequence[Sample]: ...

    @property
    def events(self) -> Sequence[Event]: ...

    @property
    def care_plan_id(self) -> str: ...


def event_to_sample(event: Event) -> Sample | None:
    """Map an event to the impulse sample of its signal, or ``None`` for evidence-only kinds.

    ``MEASUREMENT`` gives ``meas``, ``DISPENSE`` gives ``dispense``, ``INTAKE`` gives
    ``intake`` and ``SCHEDULE_TICK`` gives ``sched_tick``, with value 1.0, ``quality`` None
    and both clocks and ``seq`` copied. A DISPENSE never becomes an ``intake`` sample
    (docs/formal/01-signals-sampling.md section 2.3).
    """
    signal = _EVENT_SIGNAL.get(event.kind)
    if signal is None:
        return None
    return Sample(
        signal=signal.value,
        t_device_ms=event.t_device_ms,
        t_rx_ms=event.t_rx_ms,
        value=1.0,
        seq=event.seq,
        quality=None,
    )


def check_strictly_increasing(grid: Sequence[TimeMs]) -> None:
    """Raise ``ValueError`` unless ``grid`` is strictly increasing (module-internal helper)."""
    for earlier, later in pairwise(grid):
        if later <= earlier:
            raise ValueError(
                f"the grid must be strictly increasing, got {earlier} then {later}"
            )


def impulses_on_grid(
    samples: Sequence[Sample],
    t_grid_ms: Sequence[TimeMs],
    *,
    count: bool = False,
) -> Sequence[float]:
    """Place impulse samples on the monitor grid with the ceiling rule.

    A sample with device time ``t`` is visible at the first grid point ``>= t``, that is in
    the half-open bin ``(t_{k-1}, t_k]`` (section 3.3). On the grid ``t_k = k * T_s`` this is
    step ``(t + T_s - 1) // T_s``. A sample after the last grid point is not on the grid. A
    sample before the first grid point is not on the grid either (the first step has no
    earlier bin; only ``t == t_grid_ms[0]`` is visible there); negative device times are
    not defined by the contract (CG-11) and are never shown at step 0 of the current day.

    Several samples in one bin give one impulse of value 1.0, or, with ``count=True``, the
    multiplicity ``n_k`` (section 3.4), so that coalescing does not lose events. Counters
    must still be computed from the event stream, not from either array. All samples are
    taken as impulses of one signal: the ``signal`` field is not inspected. The result does
    not depend on the order of ``samples``. Cost: O((m + n) log n) for ``m`` samples and a
    grid of ``n`` points.
    """
    check_strictly_increasing(t_grid_ms)
    counts = [0] * len(t_grid_ms)
    for sample in samples:
        t = sample.t_device_ms
        k = bisect_left(t_grid_ms, t)
        if k == len(t_grid_ms) or (k == 0 and t != t_grid_ms[0]):
            continue
        counts[k] += 1
    if count:
        return [float(c) for c in counts]
    return [1.0 if c else 0.0 for c in counts]
