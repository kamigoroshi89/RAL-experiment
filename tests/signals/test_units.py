"""Time and units contract: aliases and constants are real definitions (WS05-T01)."""

from __future__ import annotations

from ralmon.signals import units


def test_time_constants_are_exact() -> None:
    assert units.MS_PER_SECOND == 1_000
    assert units.MS_PER_MINUTE == 60_000
    assert units.MS_PER_HOUR == 3_600_000
    assert units.TimeMs is int
    assert units.DurationMs is int
