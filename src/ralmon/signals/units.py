"""Time and units (02-interfaces.md#time-and-units): aliases, constants, conversions.

All timestamps and durations are integer milliseconds (ADR-017). The helpers convert a
duration given in minutes or hours and round to the nearest integer millisecond, so that
no float time leaks into the monitor.
"""

from __future__ import annotations

import math

TimeMs = int  # milliseconds since the start of the patient-day trace (ADR-017)
DurationMs = int

MS_PER_SECOND: int = 1_000
MS_PER_MINUTE: int = 60_000
MS_PER_HOUR: int = 3_600_000


def _to_ms(x: float, unit_ms: int) -> DurationMs:
    if not math.isfinite(x):
        raise ValueError(f"a duration must be finite, got {x!r}")
    return round(x * unit_ms)


def minutes(x: float) -> DurationMs:
    """Return ``x`` minutes as integer milliseconds (``round(x * 60_000)``)."""
    return _to_ms(x, MS_PER_MINUTE)


def hours(x: float) -> DurationMs:
    """Return ``x`` hours as integer milliseconds (``round(x * 3_600_000)``)."""
    return _to_ms(x, MS_PER_HOUR)
