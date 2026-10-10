"""Features of the B2 isolation forest (WS06-T03; analisi section 5.4, row B2).

A streaming extractor over the batches of the shared causal step iterator (``StepBatch``). It sees the delivered samples
of the monitored signals, the delivered dispense events and the care-plan schedule (a list of tick times), and nothing
else: no band, no hold threshold, no window, no template and no plan parameter. B2 is the baseline without the
specification, so the extractor is given none of it, and its signature accepts nothing from which a clinical constant
could be read.

``FEATURE_NAMES`` (the default signals ``bp``, ``hr_ecg``, ``hr_pulse`` and ``spo2``; the row of ``feature_names(signals)``
has the pair ``last_<signal>``, ``age_<signal>_ms`` per monitored signal, then the five schedule and counter features):

* ``last_bp``, ``age_bp_ms``, ``last_hr_ecg``, ``age_hr_ecg_ms``, ``last_hr_pulse``, ``age_hr_pulse_ms``, ``last_spo2``,
  ``age_spo2_ms``: the value of the newest delivered sample of the signal (newest by device time; a sample whose device
  time is not later than the newest one, and a value that is not a finite number, is not a reading) and the time from its
  device time to the grid time of the row, in ms. ``None`` until the first reading.
* ``dose_count_24h``: the number of delivered DISPENSE events with device time in ``(t - 24 h, t]``. A count is always
  defined (0 before the first dispense). It is a count of dispenses, not of intakes: DISPENSE is not INTAKE.
* ``since_last_dispense_ms``: ``t`` minus the device time of the newest delivered dispense at or before ``t``; ``None``
  before the first.
* ``to_next_tick_ms``: the time to the first scheduled tick strictly after ``t``; ``None`` after the last tick (or with
  an empty schedule).
* ``since_last_tick_ms``: ``t`` minus the last scheduled tick at or before ``t``; ``None`` before the first tick. A tick
  at ``t`` is the last one (distance 0) and not the next one.
* ``time_of_day_ms``: ``t`` modulo 24 h, on the continuing axis of the patient.

All values are floats or ``None``. The row at ``t`` is a function of the inputs delivered up to ``t`` and of the schedule,
which is known in advance: appending later inputs never changes it (a Hypothesis test pins this). The grid time ``t`` is a
monitor time (``base.py``): with a reorder delay ``D`` the newest reading has an age of at least ``D``.

Numbers. The only numbers here are the 24 h of the counter, named in the feature itself, and the unit conversions.
"""

from __future__ import annotations

import math
from bisect import bisect_right, insort
from collections.abc import Sequence
from typing import Final

from ralmon.baselines.base import StepBatch
from ralmon.signals import MS_PER_HOUR, EventKind, Sample, SignalId

__all__ = [
    "DEFAULT_SIGNALS",
    "FEATURE_NAMES",
    "FeatureExtractor",
    "FeatureRow",
    "feature_names",
]

# the continuous signals of the in-scope forecasting targets (#forecaster), the same default as B4
DEFAULT_SIGNALS: Final[tuple[str, ...]] = (
    SignalId.BP.value,
    SignalId.HR_ECG.value,
    SignalId.HR_PULSE.value,
    SignalId.SPO2.value,
)

FeatureRow = dict[str, float | None]

_T_DAY_MS: Final = 24 * MS_PER_HOUR
_TAIL_NAMES: Final[tuple[str, ...]] = (
    "dose_count_24h",
    "since_last_dispense_ms",
    "to_next_tick_ms",
    "since_last_tick_ms",
    "time_of_day_ms",
)


def feature_names(signals: Sequence[str]) -> tuple[str, ...]:
    """The column names of a row for ``signals``, in order."""
    head: list[str] = []
    for name in signals:
        head.append(f"last_{name}")
        head.append(f"age_{name}_ms")
    return (*head, *_TAIL_NAMES)


FEATURE_NAMES: Final[tuple[str, ...]] = feature_names(DEFAULT_SIGNALS)


def _check_signals(signals: Sequence[str]) -> tuple[str, ...]:
    names = tuple(signals)
    if not names:
        raise ValueError("signals must name at least one signal")
    for index, name in enumerate(names):
        if not isinstance(name, str):
            raise ValueError(  # noqa: TRY004 - one named error for every bad argument
                f"signal {name!r} is not a string"
            )
        if name in names[:index]:
            raise ValueError(f"signal {name!r} is given twice")
    return names


def _check_schedule(schedule: Sequence[int]) -> tuple[int, ...]:
    ticks: list[int] = []
    for tick in schedule:
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0:
            raise ValueError(
                f"a schedule tick must be a non-negative integer number of ms, got {tick!r}"
            )
        ticks.append(tick)
    return tuple(sorted(ticks))


class FeatureExtractor:
    """Turns the batches of one day into feature rows, one per batch (see the module docstring)."""

    def __init__(self, signals: Sequence[str], schedule: Sequence[int]) -> None:
        self._signals = _check_signals(signals)
        self._monitored = frozenset(self._signals)
        self._schedule = _check_schedule(schedule)
        self._newest: dict[str, Sample] = {}
        self._dispenses: list[int] = []
        self._last_t: int | None = None

    @property
    def names(self) -> tuple[str, ...]:
        return feature_names(self._signals)

    def push(self, batch: StepBatch) -> FeatureRow:
        """Take in the inputs delivered at ``batch.t_ms`` and return the row at that time."""
        t = batch.t_ms
        if self._last_t is not None and t < self._last_t:
            raise ValueError(
                f"batches must not go backwards in time: {t} after {self._last_t}"
            )
        self._last_t = t
        for sample in batch.samples:
            if sample.signal not in self._monitored:
                continue
            if not math.isfinite(sample.value):
                continue
            last = self._newest.get(sample.signal)
            if last is None or sample.t_device_ms > last.t_device_ms:
                self._newest[sample.signal] = sample
        for event in batch.events:
            if event.kind is EventKind.DISPENSE:
                insort(self._dispenses, event.t_device_ms)
        return self._row(t)

    def _row(self, t: int) -> FeatureRow:
        row: FeatureRow = {}
        for name in self._signals:
            sample = self._newest.get(name)
            row[f"last_{name}"] = None if sample is None else float(sample.value)
            row[f"age_{name}_ms"] = (
                None if sample is None else float(t - sample.t_device_ms)
            )
        upto = bisect_right(self._dispenses, t)
        before = bisect_right(self._dispenses, t - _T_DAY_MS)
        row["dose_count_24h"] = float(upto - before)
        row["since_last_dispense_ms"] = (
            float(t - self._dispenses[upto - 1]) if upto else None
        )
        ticks = bisect_right(self._schedule, t)
        row["to_next_tick_ms"] = (
            float(self._schedule[ticks] - t) if ticks < len(self._schedule) else None
        )
        row["since_last_tick_ms"] = (
            float(t - self._schedule[ticks - 1]) if ticks else None
        )
        row["time_of_day_ms"] = float(t % _T_DAY_MS)
        return row
