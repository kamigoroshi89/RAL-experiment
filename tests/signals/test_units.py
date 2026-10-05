"""Time and units contract: constants (WS05-T01) and the conversion helpers (WS05-T02)."""

from __future__ import annotations

import pytest

from ralmon.signals import hours, minutes, units


def test_time_constants_are_exact() -> None:
    assert units.MS_PER_SECOND == 1_000
    assert units.MS_PER_MINUTE == 60_000
    assert units.MS_PER_HOUR == 3_600_000
    assert units.TimeMs is int
    assert units.DurationMs is int


def test_minutes_hours_helpers() -> None:
    assert minutes(5) == 300_000
    assert minutes(0.5) == 30_000
    assert hours(1.5) == 5_400_000
    assert hours(9) + minutes(5) == 32_700_000  # 09:05, WS01-T01 W1 (32,700,000)
    for value in (minutes(5), minutes(0.5), hours(1.5), hours(9) + minutes(5)):
        assert type(value) is int


def test_minutes_hours_round_to_integer_milliseconds() -> None:
    # 0.29 * 3_600_000 is 1043999.9999999999 in floating point: truncation would give
    # 1_043_999, the helper rounds to the nearest integer millisecond (ADR-017).
    assert hours(0.29) == 1_044_000
    assert minutes(0.1) == 6_000
    assert minutes(1 / 3) == 20_000
    assert type(minutes(1 / 3)) is int
    # Zero and negative durations are plain arithmetic: the contract does not forbid them.
    assert minutes(0) == 0
    assert hours(-1) == -3_600_000


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_minutes_hours_reject_non_finite_input(bad: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        minutes(bad)
    with pytest.raises(ValueError, match="finite"):
        hours(bad)


def test_w7_alignment_arithmetic_of_the_fixture_windows() -> None:
    # WS01-T01 section 7, W7 (F0, T_s = 60,000): 1,800,000 is a multiple of T_s and
    # 90,500 is not. Only the arithmetic is tested here; the rejection at plan load is
    # Monitor.load (WS05-T04, CG-12), not a signals function.
    step = minutes(1)
    assert step == 60_000
    assert minutes(30) == 1_800_000 and minutes(30) % step == 0
    assert 90_500 % step == 30_500
    for window in (hours(1), minutes(5), hours(3), hours(3) - hours(1)):
        assert window % step == 0  # hold_lookback, int_window, delta2, delta2 - delta1
