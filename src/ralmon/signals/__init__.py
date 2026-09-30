"""ralmon.signals: public API (see 02-interfaces.md#package-public-api)."""

from __future__ import annotations

from ralmon.signals._stubs import (
    DerivedSignal,
    ObservedTrace,
    SignalId,
    default_derived_signals,
    event_to_sample,
    hold_last,
    hours,
    impulses_on_grid,
    minutes,
)
from ralmon.signals.trace_types import Event, EventKind, Sample
from ralmon.signals.units import (
    MS_PER_HOUR,
    MS_PER_MINUTE,
    MS_PER_SECOND,
    DurationMs,
    TimeMs,
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
