"""ralmon.signals: public API (see 02-interfaces.md#package-public-api)."""

from __future__ import annotations

from ralmon.signals.derived import DerivedSignal, default_derived_signals, hold_last
from ralmon.signals.ids import SignalId
from ralmon.signals.samples import ObservedTrace, event_to_sample, impulses_on_grid
from ralmon.signals.trace_types import Event, EventKind, Sample
from ralmon.signals.units import (
    MS_PER_HOUR,
    MS_PER_MINUTE,
    MS_PER_SECOND,
    DurationMs,
    TimeMs,
    hours,
    minutes,
)

__all__ = [
    "MS_PER_HOUR",
    "MS_PER_MINUTE",
    "MS_PER_SECOND",
    "DerivedSignal",
    "DurationMs",
    "Event",
    "EventKind",
    "ObservedTrace",
    "Sample",
    "SignalId",
    "TimeMs",
    "default_derived_signals",
    "event_to_sample",
    "hold_last",
    "hours",
    "impulses_on_grid",
    "minutes",
]
