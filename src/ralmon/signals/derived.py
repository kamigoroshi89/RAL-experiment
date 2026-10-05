"""hold_last and the streaming derived signals (docs/formal/01-signals-sampling.md 3.2, 5).

Every derived signal is causal and streaming: ``update`` is called with samples in device
time order (the reorder buffer of the monitor releases them in that order) and returns the
output sample, if any, that the input produced. Rules shared by the four implementations:

* The clock advances on every sample given, whatever its signal, so that a window can
  expire on a sample that is not one of ``inputs``. A sample whose device time is lower
  than the previous one raises ``ValueError`` and leaves the state unchanged; equal device
  times are allowed.
* Output samples carry the device time and receive time of the sample that caused them,
  ``seq`` None and ``quality`` None.
* A counter has the value 0.0 until its first output: no output sample means "unchanged",
  and before the first one the grid view built by ``hold_last`` is ``nan``, so the monitor
  must read an absent counter as 0 (it is a count, not an unknown).
* ``bp_pre`` and ``bp_drop`` are unavailable before the first dispense: ``update`` returns
  None, never 0.0 (section 3.5).
* A sample does not carry a source: de-duplication by ``(source, seq)`` (section 3.4) is
  the job of the accepting layer of the monitor, upstream of these classes.

Day-boundary rule of ``meas_count`` (modelling choice M7 of WS05-T02; section 5.2 says
"the current day" and leaves the exact edge open for a continuing time axis). Day ``d``
covers device times ``(d * T_day, (d + 1) * T_day]``, and day 0 also contains the instant 0.
The closing step ``K`` of a day (device time ``(d + 1) * T_day``) and the generated
``day_end`` marker belong to the day they close, so a day-end obligation reads the whole
day. An event is therefore counted in the day of the first grid step that shows it under
the ceiling rule. Section 3.1 assigns an event at exactly 24:00 to the next day; for a day
trace that instant does not occur, and on a continuing axis M7 keeps the closing step
consistent. Negative device times (warm-up prefix, CG-11) fall in the days before day 0.
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Sequence
from itertools import pairwise
from typing import Protocol, runtime_checkable

from ralmon.signals.ids import SignalId
from ralmon.signals.samples import check_strictly_increasing
from ralmon.signals.trace_types import Sample
from ralmon.signals.units import MS_PER_HOUR, TimeMs

# T_day of section 1.4: the 24 h trailing window of dose_count (a definition, not a
# clinical parameter) and the length of the day of meas_count.
_T_DAY_MS: int = 24 * MS_PER_HOUR


@runtime_checkable
class DerivedSignal(Protocol):
    output: SignalId
    inputs: Sequence[SignalId]

    def update(self, sample: Sample) -> Sample | None:
        """Streaming, causal; returns the output sample this input produced, if any."""
        ...


def hold_last(
    samples: Sequence[Sample], t_grid_ms: Sequence[TimeMs]
) -> Sequence[float]:
    """Piecewise-constant interpolation on the monitor grid (section 3.2).

    The value at grid point ``t`` is the value of the sample with the largest device time
    ``<= t`` (right-continuous: a sample exactly on a grid point is visible there), and
    ``nan`` if no sample has ``t_device_ms <= t``. ``nan`` means "undefined before the first
    sample" and is never 0.0; the contract return type ``Sequence[float]`` cannot carry the
    "channel unavailable" state of ``presence`` and ``intake``, which an availability mask
    next to the array must express (CG-6, not part of this contract). Only ``t_device_ms``
    is read: the reorder delay is applied by the monitor, not here, and ``quality`` does
    not change the value.

    ``samples`` must be sorted by ``t_device_ms`` (non-decreasing) and ``t_grid_ms`` must be
    strictly increasing, else ``ValueError``. Samples with equal device time are ordered by
    ``seq`` when all of them carry one, else by ``t_rx_ms`` (ties keep the listed order),
    and the last of them is the one that is held. Samples before the first grid point are
    held from it; samples after the last grid point are not used. Negative times are not
    rejected (CG-11). Cost: O(len(samples) + len(t_grid_ms)).
    """
    check_strictly_increasing(t_grid_ms)
    for before, after in pairwise(samples):
        if after.t_device_ms < before.t_device_ms:
            raise ValueError(
                "samples must be sorted by t_device_ms, got "
                f"{before.t_device_ms} then {after.t_device_ms}"
            )

    # One effective (device time, value) pair per distinct device time.
    effective: list[tuple[TimeMs, float]] = []
    start = 0
    while start < len(samples):
        t = samples[start].t_device_ms
        stop = start + 1
        while stop < len(samples) and samples[stop].t_device_ms == t:
            stop += 1
        group = list(samples[start:stop])
        if len(group) > 1:
            if all(s.seq is not None for s in group):
                group.sort(key=lambda s: s.seq if s.seq is not None else 0)
            else:
                group.sort(key=lambda s: s.t_rx_ms)
        effective.append((t, group[-1].value))
        start = stop

    held: list[float] = []
    current = math.nan
    j = 0
    for t_grid in t_grid_ms:
        while j < len(effective) and effective[j][0] <= t_grid:
            current = effective[j][1]
            j += 1
        held.append(current)
    return held


class _Clocked:
    """Device-time order check shared by the derived signals."""

    def __init__(self) -> None:
        self._clock: TimeMs | None = None

    def _tick(self, sample: Sample) -> TimeMs:
        t = sample.t_device_ms
        if self._clock is not None and t < self._clock:
            raise ValueError(
                "samples must be given in non-decreasing device time, got "
                f"{t} after {self._clock}"
            )
        self._clock = t
        return t


def _out(signal: SignalId, source: Sample, value: float) -> Sample:
    return Sample(signal.value, source.t_device_ms, source.t_rx_ms, value, None, None)


class DoseCount(_Clocked):
    """``dose_count``: dispenses with device time in ``(t - T_day, t]`` (section 5.1).

    The window is half-open: a dispense exactly 24 h old has left it. It is a trailing
    window and is not reset at midnight. A queue holds the device times of the dispenses in
    the window; each is pushed once and popped once, so the cost is amortised O(1) per
    sample (one ``update`` may pop several entries, and none is popped twice); memory is
    the number of dispenses in 24 h. Two dispenses in one grid step are two entries
    (multiplicity, section 3.4), because the count is taken from the stream and not from
    the binned impulse.

    A ``dispense`` sample always produces an output (the count after the push and the
    eviction); any other sample produces one only if it expired entries.
    """

    output = SignalId.DOSE_COUNT
    inputs: Sequence[SignalId] = (SignalId.DISPENSE,)

    def __init__(self) -> None:
        super().__init__()
        self._times: deque[TimeMs] = deque()

    def update(self, sample: Sample) -> Sample | None:
        t = self._tick(sample)
        expired = False
        while self._times and self._times[0] <= t - _T_DAY_MS:
            self._times.popleft()
            expired = True
        if sample.signal == SignalId.DISPENSE:
            self._times.append(t)
            return _out(self.output, sample, float(len(self._times)))
        if expired:
            return _out(self.output, sample, float(len(self._times)))
        return None


def _day_of(t: TimeMs) -> int:
    """Day index of device time ``t`` under M7: ``(d * T_day, (d + 1) * T_day]``, 0 in day 0."""
    return 0 if t == 0 else (t - 1) // _T_DAY_MS


class MeasCount(_Clocked):
    """``meas_count``: completed measurements in the current day (section 5.2, rule M7).

    O(1) per sample. A ``meas`` sample always produces an output; any other sample
    produces one only when it opens a new day and the previous count was not zero (the
    reset to 0.0). A ``MEASUREMENT_MISSED`` event never reaches this class: it is not a
    signal (``event_to_sample`` maps it to None).
    """

    output = SignalId.MEAS_COUNT
    inputs: Sequence[SignalId] = (SignalId.MEAS,)

    def __init__(self) -> None:
        super().__init__()
        self._day: int | None = None
        self._count: int = 0

    def update(self, sample: Sample) -> Sample | None:
        t = self._tick(sample)
        day = _day_of(t)
        reset = False
        if self._day is not None and day != self._day:
            reset = self._count != 0
            self._count = 0
        self._day = day
        if sample.signal == SignalId.MEAS:
            self._count += 1
            return _out(self.output, sample, float(self._count))
        if reset:
            return _out(self.output, sample, 0.0)
        return None


class _PreDose(_Clocked):
    """Shared state of ``bp_pre`` and ``bp_drop``: the held ``bp`` and the latched pre-dose value.

    At each ``dispense`` the pre-dose value is set to the held ``bp`` (``nan`` if none) and
    kept until the next dispense (the global stream of section 5.3). A ``bp`` sample with
    the same device time as the latest dispense counts as before the dose (M5), whichever of
    the two was delivered first, so it re-latches the value. The per-instance capture for
    overlapping doses belongs to the monitor (WS05-T04).
    """

    def __init__(self) -> None:
        super().__init__()
        self._bp: float = math.nan
        self._pre: float | None = None
        self._dispense_t: TimeMs | None = None

    def _observe(self, sample: Sample) -> tuple[bool, bool]:
        """Advance the state; return (is_bp_or_dispense, pre_was_latched)."""
        t = self._tick(sample)
        if sample.signal == SignalId.DISPENSE:
            self._pre = self._bp
            self._dispense_t = t
            return True, True
        if sample.signal == SignalId.BP:
            self._bp = sample.value
            if self._pre is not None and self._dispense_t == t:
                self._pre = sample.value
                return True, True
            return True, False
        return False, False


class BpPre(_PreDose):
    """``bp_pre``: the pressure of the last measurement at or before the latest dose.

    Unavailable (``update`` returns None) before the first dispense. O(1) per sample.
    """

    output = SignalId.BP_PRE
    inputs: Sequence[SignalId] = (SignalId.BP, SignalId.DISPENSE)

    def update(self, sample: Sample) -> Sample | None:
        _, latched = self._observe(sample)
        if latched and self._pre is not None:
            return _out(self.output, sample, self._pre)
        return None


class BpDrop(_PreDose):
    """``bp_drop = bp_pre - bp`` (section 5.4): positive for a fall in pressure.

    Unavailable before the first dispense. ``nan`` if either operand is ``nan``. An output
    is produced for every ``bp`` and ``dispense`` sample once a dose exists. O(1) per sample.
    """

    output = SignalId.BP_DROP
    inputs: Sequence[SignalId] = (SignalId.BP, SignalId.DISPENSE)

    def update(self, sample: Sample) -> Sample | None:
        relevant, _ = self._observe(sample)
        if relevant and self._pre is not None:
            return _out(self.output, sample, self._pre - self._bp)
        return None


def default_derived_signals() -> Sequence[DerivedSignal]:
    """Fresh instances of the four derived signals, in the order of the contract."""
    return [DoseCount(), MeasCount(), BpPre(), BpDrop()]
