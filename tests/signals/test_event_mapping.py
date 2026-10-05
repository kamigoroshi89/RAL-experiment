"""event_to_sample and impulses_on_grid: the ceiling rule and multiplicity (WS01-T01 3.3, 3.4).

Time labels convert as t_ms = (60*hh + mm) * 60000. Fixture values are FIXTURE-ONLY.
"""

from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ralmon.signals import (
    Event,
    EventKind,
    Sample,
    SignalId,
    default_derived_signals,
    event_to_sample,
    hold_last,
    impulses_on_grid,
)

STEP = 60_000  # F0 step_ms
K = 1_440


def hhmm(hh: int, mm: int, ss: int = 0, ms: int = 0) -> int:
    return ((60 * hh + mm) * 60 + ss) * 1000 + ms


def event(
    kind: EventKind, t_ms: int, *, rx: int | None = None, seq: int | None = None
) -> Event:
    return Event(kind, t_ms, t_ms if rx is None else rx, "fixture", {}, seq)


def impulse(signal: str, t_ms: int) -> Sample:
    return Sample(signal, t_ms, t_ms, 1.0, None, None)


GRID = [k * STEP for k in range(K + 1)]


def steps_with_impulse(values: list[float] | tuple[float, ...]) -> list[int]:
    return [k for k, v in enumerate(values) if v != 0.0]


# -- event_to_sample --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "signal"),
    [
        (EventKind.MEASUREMENT, "meas"),
        (EventKind.DISPENSE, "dispense"),
        (EventKind.INTAKE, "intake"),
        (EventKind.SCHEDULE_TICK, "sched_tick"),
    ],
)
@pytest.mark.parametrize("seq", [None, 7])
def test_event_to_sample_mapping_table(
    kind: EventKind, signal: str, seq: int | None
) -> None:
    ev = Event(kind, 1_000, 1_250, "cuff", {"note": "x"}, seq)
    got = event_to_sample(ev)
    assert got == Sample(signal, 1_000, 1_250, 1.0, seq, None)
    assert got is not None and got.quality is None and got.value == 1.0


@pytest.mark.parametrize(
    "kind",
    [
        EventKind.MEASUREMENT_MISSED,
        EventKind.NODE_STATE,
        EventKind.ROBOT_TASK,
        EventKind.DEVICE_ERROR,
    ],
)
def test_event_to_sample_evidence_only_events_are_not_signals(kind: EventKind) -> None:
    assert event_to_sample(event(kind, 1_000)) is None


def test_event_to_sample_covers_every_event_kind_exactly_once() -> None:
    mapped = {k for k in EventKind if event_to_sample(event(k, 0)) is not None}
    assert mapped == {
        EventKind.MEASUREMENT,
        EventKind.DISPENSE,
        EventKind.INTAKE,
        EventKind.SCHEDULE_TICK,
    }
    signals = [event_to_sample(event(k, 0)).signal for k in mapped]  # type: ignore[union-attr]
    assert len(set(signals)) == 4


def test_dispense_event_never_becomes_an_intake_sample() -> None:
    # DISPENSE is not INTAKE (ADR-004; WS01-T01 section 2.3).
    got = event_to_sample(event(EventKind.DISPENSE, 0))
    assert got is not None and got.signal == "dispense" and got.signal != "intake"


# -- impulses_on_grid: ceiling rule ---------------------------------------------------


def test_impulses_on_grid_w2_ceiling_rule() -> None:
    # WS01-T01 W2: a meas event at 06:52:20 (24,740,000) is visible only at step 06:53
    # (413, 24,780,000); an event at exactly 06:52:00 (24,720,000) only at step 06:52 (412).
    late = impulses_on_grid([impulse("meas", 24_740_000)], GRID)
    assert steps_with_impulse(late) == [413]
    assert GRID[413] == 24_780_000
    exact = impulses_on_grid([impulse("meas", 24_720_000)], GRID)
    assert steps_with_impulse(exact) == [412]
    assert (24_740_000 + STEP - 1) // STEP == 413  # the integer form of W2


def test_impulses_on_grid_values_are_zero_or_one_floats() -> None:
    values = impulses_on_grid([impulse("meas", 24_740_000)], GRID)
    assert len(values) == K + 1
    assert set(values) == {0.0, 1.0}
    assert all(type(v) is float for v in values)


def test_impulses_on_grid_w3_multiplicity() -> None:
    # WS01-T01 W3: dispense events at 20:59:59.500 (75,599,500) and 21:00:00.000
    # (75,600,000) fall in the same bin (75,540,000, 75,600,000]: one impulse at step 1260,
    # multiplicity n_1260 = 2, and the dose counter increases by 2 (0 -> 2).
    events = [
        event(EventKind.DISPENSE, 75_599_500),
        event(EventKind.DISPENSE, 75_600_000),
    ]
    samples = [s for e in events if (s := event_to_sample(e)) is not None]
    assert len(samples) == 2
    grid_values = impulses_on_grid(samples, GRID)
    assert steps_with_impulse(grid_values) == [1260]
    assert grid_values[1260] == 1.0  # one impulse, not two
    counts = impulses_on_grid(samples, GRID, count=True)
    assert counts[1260] == 2.0 and sum(counts) == 2.0
    # The counter reads the event stream, not the binned impulse.
    dose = next(d for d in default_derived_signals() if d.output is SignalId.DOSE_COUNT)
    outputs = [o for s in samples if (o := dose.update(s)) is not None]
    assert [o.value for o in outputs] == [1.0, 2.0]
    held = hold_last(outputs, GRID)
    assert math.isnan(
        held[1259]
    )  # no output yet: the counter starts at 0 by definition
    assert held[1260] == 2.0  # the increment seen on the grid is 2, not 1


def test_impulses_on_grid_w3_note_pair_in_two_bins() -> None:
    # W3 note: 21:00:00.000 and 21:00:00.500 do not coalesce: steps 1260 and 1261.
    samples = [impulse("dispense", 75_600_000), impulse("dispense", 75_600_500)]
    assert steps_with_impulse(impulses_on_grid(samples, GRID)) == [1260, 1261]


def test_impulses_on_grid_w4_anchor_and_window_steps() -> None:
    # WS01-T01 W4: tick at 09:00 (32,400,000) is visible at step 540; a tick at 09:00:20
    # (32,420,000) at 541 (ceil(540.33)); meas at 09:20 -> 560; meas at 09:31 -> 571.
    assert steps_with_impulse(
        impulses_on_grid([impulse("sched_tick", 32_400_000)], GRID)
    ) == [540]
    assert steps_with_impulse(
        impulses_on_grid([impulse("sched_tick", 32_420_000)], GRID)
    ) == [541]
    assert steps_with_impulse(
        impulses_on_grid([impulse("meas", hhmm(9, 20))], GRID)
    ) == [560]
    assert steps_with_impulse(
        impulses_on_grid([impulse("meas", hhmm(9, 31))], GRID)
    ) == [571]


def test_impulses_on_grid_empty_inputs() -> None:
    assert list(impulses_on_grid([], GRID)) == [0.0] * (K + 1)
    assert list(impulses_on_grid([impulse("meas", 0)], [])) == []
    assert list(impulses_on_grid([], [], count=True)) == []


def test_impulses_on_grid_event_at_time_zero_is_visible_at_step_zero() -> None:
    assert steps_with_impulse(impulses_on_grid([impulse("meas", 0)], GRID)) == [0]


def test_impulses_on_grid_last_bin_and_beyond() -> None:
    # An event in the last bin (t_{K-1}, t_K] is visible at the closing step K; an event
    # after t_K is not on the grid.
    last = impulses_on_grid([impulse("meas", K * STEP - 1)], GRID)
    assert steps_with_impulse(last) == [K]
    beyond = impulses_on_grid([impulse("meas", K * STEP + 1)], GRID)
    assert steps_with_impulse(beyond) == []


def test_impulses_before_the_grid_start_are_not_visible() -> None:
    # Bin of step k is (t_{k-1}, t_k]; the first step has no earlier bin, so only an
    # event exactly at grid[0] is visible there. This keeps warm-up events at negative
    # times (CG-11) off the grid of the current day.
    grid = [0, STEP, 2 * STEP]
    assert steps_with_impulse(impulses_on_grid([impulse("meas", -1)], grid)) == []
    assert steps_with_impulse(impulses_on_grid([impulse("meas", -STEP)], grid)) == []
    assert steps_with_impulse(impulses_on_grid([impulse("meas", 0)], grid)) == [0]
    shifted = [5 * STEP, 6 * STEP]
    assert (
        steps_with_impulse(impulses_on_grid([impulse("meas", 4 * STEP + 1)], shifted))
        == []
    )
    assert steps_with_impulse(
        impulses_on_grid([impulse("meas", 5 * STEP)], shifted)
    ) == [0]
    assert steps_with_impulse(
        impulses_on_grid([impulse("meas", 5 * STEP + 1)], shifted)
    ) == [1]


def test_impulses_on_grid_does_not_depend_on_sample_order() -> None:
    a = [impulse("meas", 100_000), impulse("meas", 30_000), impulse("meas", 100_000)]
    assert impulses_on_grid(a, GRID, count=True) == impulses_on_grid(
        list(reversed(a)), GRID, count=True
    )


def test_impulses_on_grid_rejects_non_increasing_grid() -> None:
    with pytest.raises(ValueError, match="strictly increasing"):
        impulses_on_grid([impulse("meas", 0)], [0, 0])
    with pytest.raises(ValueError, match="strictly increasing"):
        impulses_on_grid([], [STEP, 0])


# -- property tests (deterministic Hypothesis profile of tests/conftest.py) ------------

_event_times = st.lists(st.integers(min_value=0, max_value=K * STEP), max_size=40)


@given(_event_times)
def test_ceiling_rule_identity_property(times: list[int]) -> None:
    """The impulse of an event is at step (t + T_s - 1) // T_s, for every event."""
    samples = [impulse("meas", t) for t in times]
    counts = impulses_on_grid(samples, GRID, count=True)
    expected = [0.0] * (K + 1)
    for t in times:
        expected[(t + STEP - 1) // STEP] += 1.0
    assert list(counts) == expected
    # and the 0/1 impulse is the indicator of a non-zero count
    assert list(impulses_on_grid(samples, GRID)) == [
        1.0 if c else 0.0 for c in expected
    ]


@given(
    st.sampled_from([1, 7, 1_000, STEP, 4 * STEP]),
    st.lists(st.integers(min_value=0, max_value=100), max_size=40),
    st.lists(st.integers(min_value=0, max_value=6), max_size=40),
)
def test_ceiling_rule_identity_for_other_step_sizes_property(
    step: int, whole_steps: list[int], offsets: list[int]
) -> None:
    # A short grid of 101 points (0 .. 100 * step) keeps the memory use small; events sit
    # on grid points (offset 0) or just after them, so that bin edges are exercised.
    grid = [k * step for k in range(101)]
    times = [
        min(k * step + (0 if i >= len(offsets) else offsets[i] % step), 100 * step)
        for i, k in enumerate(whole_steps)
    ]
    samples = [impulse("meas", t) for t in times]
    counts = impulses_on_grid(samples, grid, count=True)
    expected = [0.0] * len(grid)
    for t in times:
        expected[(t + step - 1) // step] += 1.0
    assert list(counts) == expected


@given(_event_times)
def test_coalescing_preserves_multiplicity_property(times: list[int]) -> None:
    samples = [impulse("dispense", t) for t in times]
    counts = impulses_on_grid(samples, GRID, count=True)
    impulses = impulses_on_grid(samples, GRID)
    # every event on the grid is counted once, however many share a bin
    assert sum(counts) == float(len(times))
    # coalescing: one impulse per occupied bin, never more impulses than events
    assert sum(impulses) == float(len({(t + STEP - 1) // STEP for t in times}))
    assert sum(impulses) <= sum(counts)
    # the streaming dose counter (which reads the event stream) ends at the number of events
    # inside its 24 h window, even when events share a bin
    dose = next(d for d in default_derived_signals() if d.output is SignalId.DOSE_COUNT)
    last = None
    for s in sorted(samples, key=lambda s: s.t_device_ms):
        out = dose.update(s)
        if out is not None:
            last = out
    if times:
        end = max(times)
        assert last is not None
        assert last.value == float(sum(1 for t in times if end - 86_400_000 < t <= end))
