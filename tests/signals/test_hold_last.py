"""hold_last: piecewise-constant hold on the monitor grid (WS01-T01 sections 3.1, 3.2, 3.5).

Time labels convert as t_ms = (60*hh + mm) * 60000. Fixture values are FIXTURE-ONLY.
"""

from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ralmon.signals import Sample, hold_last

STEP = 60_000  # F0 step_ms
K = 1_440  # steps per day, closing step included: 0..K


def hhmm(hh: int, mm: int, ss: int = 0, ms: int = 0) -> int:
    return ((60 * hh + mm) * 60 + ss) * 1000 + ms


def bp(
    t_ms: int, value: float, *, rx: int | None = None, seq: int | None = None
) -> Sample:
    return Sample("bp", t_ms, t_ms if rx is None else rx, value, seq, None)


def is_nan(x: float) -> bool:
    return math.isnan(x)


def test_hold_last_w1() -> None:
    # WS01-T01 section 7, W1: bp 138 at 06:52 (24,720,000) and 152 at 09:05 (32,700,000).
    samples = [bp(24_720_000, 138.0), bp(32_700_000, 152.0)]
    grid = [hhmm(6, 51), hhmm(6, 52), hhmm(9, 4), hhmm(9, 5)]
    held = hold_last(samples, grid)
    assert is_nan(held[0])
    assert list(held[1:]) == [138.0, 138.0, 152.0]


def test_hold_last_w1_full_day_counts() -> None:
    # W1 hand calculation: 412 NaN steps (0..411), 133 steps of 138 (412..544),
    # 896 steps of 152 (545..1440); 412 + 133 + 896 = 1441 = K + 1.
    samples = [bp(24_720_000, 138.0), bp(32_700_000, 152.0)]
    grid = [k * STEP for k in range(K + 1)]
    held = hold_last(samples, grid)
    assert len(held) == 1441
    assert sum(1 for v in held if is_nan(v)) == 412
    assert all(is_nan(v) for v in held[:412])
    assert sum(1 for v in held if v == 138.0) == 133
    assert all(v == 138.0 for v in held[412:545])
    assert sum(1 for v in held if v == 152.0) == 896
    assert all(v == 152.0 for v in held[545:])
    assert 412 + 133 + 896 == K + 1


def test_hold_last_w2_sample_inside_a_step_is_held_from_the_next_step() -> None:
    # W2 closing remark: a bp sample at 06:52:20 (24,740,000) starts to be held at 06:53.
    samples = [bp(24_740_000, 138.0)]
    grid = [24_720_000, 24_780_000]  # 06:52 and 06:53
    held = hold_last(samples, grid)
    assert is_nan(held[0])
    assert held[1] == 138.0


def test_hold_last_w5_case_i_accepted_sample_is_held_from_step_0930() -> None:
    # W5 case (i): bp 152 at device time 09:29:50 (34,190,000) is held from step 09:30
    # (570), not from 09:29 (569); before it the held value is 138 (W1).
    samples = [bp(24_720_000, 138.0), bp(34_190_000, 152.0)]
    held = hold_last(samples, [569 * STEP, 570 * STEP])
    assert list(held) == [138.0, 152.0]


def test_hold_last_no_samples_gives_nan_not_zero() -> None:
    held = hold_last([], [0, STEP, 2 * STEP])
    assert len(held) == 3
    assert all(is_nan(v) for v in held)
    assert not any(v == 0.0 for v in held)


def test_hold_last_empty_grid_gives_empty_result() -> None:
    assert list(hold_last([bp(0, 1.0)], [])) == []
    assert list(hold_last([], [])) == []


def test_hold_last_uses_device_time() -> None:
    # The reorder delay is applied by the monitor, not here: the receive time is ignored.
    samples = [bp(100, 7.0, rx=500)]
    held = hold_last(samples, [50, 200])
    assert is_nan(held[0])
    assert held[1] == 7.0


def test_hold_last_sample_exactly_on_a_grid_point_is_visible_there() -> None:
    held = hold_last([bp(STEP, 5.0)], [0, STEP, 2 * STEP])
    assert is_nan(held[0])
    assert list(held[1:]) == [5.0, 5.0]


def test_hold_last_sample_after_the_last_grid_point_is_not_used() -> None:
    held = hold_last([bp(3 * STEP, 5.0)], [0, STEP, 2 * STEP])
    assert all(is_nan(v) for v in held)


def test_hold_last_several_samples_inside_one_step_keep_the_latest() -> None:
    samples = [bp(10, 1.0), bp(20, 2.0), bp(59_999, 3.0)]
    held = hold_last(samples, [0, STEP])
    assert is_nan(held[0])
    assert held[1] == 3.0


def test_hold_last_sample_before_the_grid_start_is_held() -> None:
    # A sample before the first grid point is visible at it. Negative TimeMs is not
    # forbidden by the contract (CG-11); hold_last does not reject it.
    held = hold_last([bp(-5_000, 9.0)], [0, STEP])
    assert list(held) == [9.0, 9.0]


def test_hold_last_nan_value_is_held_as_nan() -> None:
    held = hold_last([bp(0, 1.0), bp(STEP, float("nan"))], [0, STEP, 2 * STEP])
    assert held[0] == 1.0
    assert is_nan(held[1]) and is_nan(held[2])


def test_hold_last_duplicate_device_time_is_ordered_by_seq() -> None:
    # T01 section 3.2: equal device times are ordered by seq when present.
    samples = [bp(100, 2.0, seq=2), bp(100, 1.0, seq=1)]
    assert hold_last(samples, [100])[0] == 2.0
    assert hold_last(list(reversed(samples)), [100])[0] == 2.0


def test_hold_last_duplicate_device_time_without_seq_is_ordered_by_receive_time() -> (
    None
):
    samples = [bp(100, 2.0, rx=300), bp(100, 1.0, rx=200)]
    assert hold_last(samples, [100])[0] == 2.0
    assert hold_last(list(reversed(samples)), [100])[0] == 2.0


def test_hold_last_duplicate_device_time_with_equal_keys_keeps_the_later_listed() -> (
    None
):
    samples = [bp(100, 1.0), bp(100, 2.0)]
    assert hold_last(samples, [100])[0] == 2.0


def test_hold_last_rejects_unsorted_samples_or_non_increasing_grid() -> None:
    with pytest.raises(ValueError, match="sorted"):
        hold_last([bp(200, 1.0), bp(100, 2.0)], [0, 300])
    with pytest.raises(ValueError, match="strictly increasing"):
        hold_last([bp(100, 1.0)], [0, 300, 300])
    with pytest.raises(ValueError, match="strictly increasing"):
        hold_last([bp(100, 1.0)], [300, 0])


def test_hold_last_validates_even_when_the_other_input_is_empty() -> None:
    with pytest.raises(ValueError, match="strictly increasing"):
        hold_last([], [5, 5])
    with pytest.raises(ValueError, match="sorted"):
        hold_last([bp(2, 1.0), bp(1, 1.0)], [])


# -- property tests (deterministic Hypothesis profile of tests/conftest.py) ------------

_times = st.integers(min_value=-1_000, max_value=10_000)
_values = st.floats(
    min_value=-1e3, max_value=1e3, allow_nan=False, allow_infinity=False
)


@st.composite
def _samples_and_grid(
    draw: st.DrawFn,
) -> tuple[list[Sample], list[int]]:
    """Samples with distinct device times, sorted, plus a strictly increasing grid."""
    times = sorted(draw(st.sets(_times, max_size=12)))
    samples = [bp(t, draw(_values)) for t in times]
    grid = sorted(draw(st.sets(_times, max_size=15)))
    return samples, grid


def _brute_force(samples: list[Sample], grid: list[int]) -> list[float]:
    out = []
    for g in grid:
        visible = [s for s in samples if s.t_device_ms <= g]
        out.append(
            max(visible, key=lambda s: s.t_device_ms).value if visible else math.nan
        )
    return out


@given(_samples_and_grid())
def test_hold_last_equals_brute_force_definition_property(
    case: tuple[list[Sample], list[int]],
) -> None:
    samples, grid = case
    got = list(hold_last(samples, grid))
    want = _brute_force(samples, grid)
    assert len(got) == len(want) == len(grid)
    for g, w in zip(got, want, strict=True):
        assert (is_nan(g) and is_nan(w)) or g == w


@given(_samples_and_grid(), st.lists(_values, max_size=6), st.integers(0, 5_000))
def test_hold_last_is_causal_property(
    case: tuple[list[Sample], list[int]], extra: list[float], shift: int
) -> None:
    samples, grid = case
    if not grid:
        return
    cut = grid[len(grid) // 2]
    past = [s for s in samples if s.t_device_ms <= cut]
    # Append, alter and remove samples that lie strictly after `cut`.
    last = samples[-1].t_device_ms if samples else cut
    appended = [bp(max(cut, last) + 1 + i, v) for i, v in enumerate(extra)]
    altered = past + [
        bp(s.t_device_ms, s.value + 1.0 + shift) for s in samples if s.t_device_ms > cut
    ]
    variants = [past, past + appended, altered + appended, samples]
    upto = [i for i, g in enumerate(grid) if g <= cut]
    base = list(hold_last(variants[0], grid))
    for variant in variants[1:]:
        other = list(hold_last(variant, grid))
        for i in upto:
            assert (is_nan(base[i]) and is_nan(other[i])) or base[i] == other[i]
