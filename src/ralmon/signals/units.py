"""Time and units (02-interfaces.md#time-and-units): aliases and constants, no behaviour."""

from __future__ import annotations

TimeMs = int  # milliseconds since the start of the patient-day trace (ADR-017)
DurationMs = int

MS_PER_SECOND: int = 1_000
MS_PER_MINUTE: int = 60_000
MS_PER_HOUR: int = 3_600_000
