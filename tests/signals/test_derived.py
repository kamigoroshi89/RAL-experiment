"""Streaming derived signals: dose_count, meas_count, bp_pre, bp_drop (WS01-T01 section 5).

Time labels convert as t_ms = (60*hh + mm) * 60000. Fixture values are FIXTURE-ONLY.
Day-boundary rules named here:
  * dose_count: trailing half-open window (t - T_day, t], not reset at midnight (5.1);
  * meas_count: current day, where day d covers (d * T_day, (d + 1) * T_day] and day 0 also
    contains the instant 0 (modelling choice M7 of WS05-T02: the closing step K and the
    generated day_end marker belong to the day they close, see the module docstring of
    ralmon.signals.derived).
"""

from __future__ import annotations

import math
from collections.abc import Iterable

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ralmon.signals import (
    DerivedSignal,
    Sample,
    SignalId,
    default_derived_signals,
    hold_last,
)

T_DAY = 86_400_000


def hhmm(hh: int, mm: int, ss: int = 0, ms: int = 0) -> int:
    return ((60 * hh + mm) * 60 + ss) * 1000 + ms


def s(
    signal: SignalId, t_ms: int, value: float = 1.0, *, rx: int | None = None
) -> Sample:
    return Sample(signal.value, t_ms, t_ms if rx is None else rx, value, None, None)


def derived(output: SignalId) -> DerivedSignal:
    (found,) = [d for d in default_derived_signals() if d.output is output]
    return found


def run(sig: DerivedSignal, samples: Iterable[Sample]) -> list[Sample | None]:
    return [sig.update(x) for x in samples]


def values(outputs: Iterable[Sample | None]) -> list[float]:
    return [o.value for o in outputs if o is not None]


# -- default_derived_signals ------------------------------------------------------------


def test_default_derived_signals_outputs_and_inputs() -> None:
    four = list(default_derived_signals())
    assert [d.output for d in four] == [
        SignalId.DOSE_COUNT,
        SignalId.MEAS_COUNT,
        SignalId.BP_PRE,
        SignalId.BP_DROP,
    ]
    for d in four:
        assert len(d.inputs) >= 1
        assert all(isinstance(i, SignalId) for i in d.inputs)
        assert d.output not in d.inputs
        assert isinstance(d, DerivedSignal)  # structural Protocol (runtime checkable)
    stream = [
        s(SignalId.BP, hhmm(6, 45), 150.0),
        s(SignalId.MEAS, hhmm(6, 45)),
        s(SignalId.DISPENSE, hhmm(7, 0)),
        s(SignalId.BP, hhmm(8, 30), 132.0),
        s(SignalId.MEAS, hhmm(8, 30)),
        s(SignalId.DISPENSE, hhmm(21, 0)),
        s(SignalId.DAY_END, T_DAY),
    ]
    first = [[d.update(x) for x in stream] for d in default_derived_signals()]
    second = [[d.update(x) for x in stream] for d in default_derived_signals()]
    assert first == second  # no hidden state shared between fresh instances
    assert any(o is not None for outs in first for o in outs)


def test_default_derived_signals_returns_fresh_instances_each_call() -> None:
    a = list(default_derived_signals())
    b = list(default_derived_signals())
    assert all(x is not y for x, y in zip(a, b, strict=True))
    a[0].update(s(SignalId.DISPENSE, 1_000))
    assert values([b[0].update(s(SignalId.DISPENSE, 1_000))]) == [1.0]


def test_derived_output_sample_fields() -> None:
    out = derived(SignalId.DOSE_COUNT).update(s(SignalId.DISPENSE, 5_000, rx=5_300))
    assert out == Sample("dose_count", 5_000, 5_300, 1.0, None, None)


# -- dose_count ---------------------------------------------------------------------------


def test_dose_count_w6_trailing_24h_half_open() -> None:
    # WS01-T01 W6: dispenses day 1 07:00 (25,200,000), 21:00 (75,600,000), 21:02
    # (75,720,000); day 2 07:00 = 86,400,000 + 25,200,000 = 111,600,000 on the continuing
    # axis. Window (t - 24 h, t]; at day-2 07:00 it is (25,200,000, 111,600,000] and the
    # day-1 07:00 dose (exactly 24 h old) is excluded: 3. A closed window would give 4.
    dose = derived(SignalId.DOSE_COUNT)
    times = [25_200_000, 75_600_000, 75_720_000, 111_600_000]
    assert values(run(dose, [s(SignalId.DISPENSE, t) for t in times])) == [
        1.0,
        2.0,
        3.0,
        3.0,
    ]
    assert 111_600_000 - T_DAY == 25_200_000


def test_dose_count_w6_truncation_fallback_counts_only_the_new_day() -> None:
    # W6: a run of day 2 that starts with empty state sees only its own dispense: 1.
    dose = derived(SignalId.DOSE_COUNT)
    assert values(run(dose, [s(SignalId.DISPENSE, 111_600_000)])) == [1.0]


def test_dose_count_event_at_the_exact_window_edge_is_excluded() -> None:
    # (t - T_day, t]: an event exactly T_day old has left the window; one ms younger stays.
    edge = derived(SignalId.DOSE_COUNT)
    assert values(
        run(edge, [s(SignalId.DISPENSE, 0), s(SignalId.DISPENSE, T_DAY)])
    ) == [1.0, 1.0]
    inside = derived(SignalId.DOSE_COUNT)
    assert values(
        run(inside, [s(SignalId.DISPENSE, 1), s(SignalId.DISPENSE, T_DAY)])
    ) == [1.0, 2.0]


def test_dose_count_expires_on_any_forwarded_sample() -> None:
    dose = derived(SignalId.DOSE_COUNT)
    run(
        dose,
        [
            s(SignalId.DISPENSE, t)
            for t in (25_200_000, 75_600_000, 75_720_000, 111_600_000)
        ],
    )
    # No change yet at 111,600,001: the window still holds 75.6M, 75.72M and 111.6M.
    assert dose.update(s(SignalId.DAY_END, 111_600_001)) is None
    # 75,600,000 + T_day = 162,000,000: the 21:00 dose leaves the window.
    out = dose.update(s(SignalId.DAY_END, 162_000_000))
    assert out == Sample("dose_count", 162_000_000, 162_000_000, 2.0, None, None)
    # 198,000,000 = 111,600,000 + T_day: the last dose leaves; the count is 0.0, not None.
    out = dose.update(s(SignalId.DAY_END, 198_000_000))
    assert out == Sample("dose_count", 198_000_000, 198_000_000, 0.0, None, None)
    # An unchanged value gives no sample.
    assert dose.update(s(SignalId.DAY_END, 199_000_000)) is None


def test_dose_count_counts_two_dispenses_with_the_same_device_time() -> None:
    # Multiplicity (WS01-T01 3.4): without seq a repeated dispense cannot be told from a
    # genuine one, both are counted (the replay exposure is stated in section 4.5).
    dose = derived(SignalId.DOSE_COUNT)
    assert values(
        run(dose, [s(SignalId.DISPENSE, 500), s(SignalId.DISPENSE, 500)])
    ) == [1.0, 2.0]


def test_dose_count_ignores_other_signals_as_events() -> None:
    dose = derived(SignalId.DOSE_COUNT)
    assert run(
        dose, [s(SignalId.MEAS, 10), s(SignalId.INTAKE, 20), s(SignalId.BP, 30, 120.0)]
    ) == [
        None,
        None,
        None,
    ]
    assert values(run(dose, [s(SignalId.DISPENSE, 40)])) == [1.0]


def test_dose_count_state_is_bounded_by_the_window() -> None:
    # Each dispense is appended once and removed once: the queue never holds more than the
    # dispenses of one window (amortised O(1) per sample).
    dose = derived(SignalId.DOSE_COUNT)
    hour = 3_600_000
    for i in range(1_000):
        dose.update(s(SignalId.DISPENSE, i * hour))
    assert len(dose._times) <= 24  # type: ignore[attr-defined]


@pytest.mark.parametrize("signal", ["bp", "dispense", "meas", "day_end", "presence"])
def test_derived_signals_reject_samples_out_of_device_time_order(signal: str) -> None:
    for d in default_derived_signals():
        d.update(s(SignalId(signal), 1_000))
        with pytest.raises(ValueError, match="non-decreasing"):
            d.update(s(SignalId(signal), 999))
        d.update(s(SignalId(signal), 1_000))  # equal device time is allowed


def _naive_dose_count(times: list[int], t: int) -> int:
    return sum(1 for d in times if t - T_DAY < d <= t)


@given(
    st.lists(st.integers(min_value=0, max_value=5 * T_DAY), max_size=30),
    st.lists(st.integers(min_value=0, max_value=5 * T_DAY), max_size=10),
)
def test_dose_count_matches_naive_recount_property(
    dispense_times: list[int], clock_times: list[int]
) -> None:
    # Streaming value after each sample equals the batch definition, with other signals
    # interleaved as pure clock ticks.
    stream = sorted(
        [(t, SignalId.DISPENSE) for t in dispense_times]
        + [(t, SignalId.DAY_END) for t in clock_times],
        key=lambda x: x[0],
    )
    dose = derived(SignalId.DOSE_COUNT)
    seen: list[int] = []
    current = 0.0
    for t, sig in stream:
        if sig is SignalId.DISPENSE:
            seen.append(t)
        out = dose.update(s(sig, t))
        if out is not None:
            current = out.value
        assert current == float(_naive_dose_count(seen, t))
        if sig is SignalId.DISPENSE:
            assert out is not None and out.value == float(_naive_dose_count(seen, t))


# -- meas_count -----------------------------------------------------------------------


def test_meas_count_counts_measurements_in_the_day() -> None:
    # Rule: measurements in the current day, day 0 = [0, T_day] (WS01-T01 5.2, M7).
    meas = derived(SignalId.MEAS_COUNT)
    times = [hhmm(6, 45), hhmm(8, 30), hhmm(12, 0), hhmm(15, 0), hhmm(21, 0)]
    assert values(run(meas, [s(SignalId.MEAS, t) for t in times])) == [
        1.0,
        2.0,
        3.0,
        4.0,
        5.0,
    ]


def test_meas_count_day_boundary_closing_step_belongs_to_the_day_it_closes() -> None:
    meas = derived(SignalId.MEAS_COUNT)
    run(meas, [s(SignalId.MEAS, t) for t in (hhmm(6, 45), hhmm(8, 30), hhmm(21, 0))])
    # The generated day_end marker at exactly 24:00 is in day 0: no reset, no change.
    assert meas.update(s(SignalId.DAY_END, T_DAY)) is None
    # A measurement at exactly 24:00 is visible at the closing step K, so it counts in day 0.
    assert values([meas.update(s(SignalId.MEAS, T_DAY))]) == [4.0]
    # The first instant after 24:00 is day 1: the count restarts, even on a clock sample.
    out = meas.update(s(SignalId.DAY_END, T_DAY + 1))
    assert out == Sample("meas_count", T_DAY + 1, T_DAY + 1, 0.0, None, None)
    assert values([meas.update(s(SignalId.MEAS, T_DAY + 60_000))]) == [1.0]


def test_meas_count_first_measurement_of_a_new_day_gives_one() -> None:
    meas = derived(SignalId.MEAS_COUNT)
    run(meas, [s(SignalId.MEAS, t) for t in (hhmm(6, 45), hhmm(8, 30))])
    assert values([meas.update(s(SignalId.MEAS, T_DAY + hhmm(6, 50)))]) == [1.0]
    assert values([meas.update(s(SignalId.MEAS, T_DAY + hhmm(8, 0)))]) == [2.0]


def test_meas_count_samples_at_negative_times_are_not_in_day_zero() -> None:
    # A warm-up prefix at negative times (CG-11) belongs to the previous day: it never
    # raises the count of day 0.
    meas = derived(SignalId.MEAS_COUNT)
    assert values(
        run(meas, [s(SignalId.MEAS, -60_000), s(SignalId.MEAS, -30_000)])
    ) == [1.0, 2.0]
    assert values([meas.update(s(SignalId.MEAS, 0))]) == [1.0]  # day 0 restarts at 1
    fresh = derived(SignalId.MEAS_COUNT)
    assert values(run(fresh, [s(SignalId.MEAS, 0), s(SignalId.MEAS, 60_000)])) == [
        1.0,
        2.0,
    ]


def test_meas_count_ignores_other_signals_and_starts_at_zero() -> None:
    meas = derived(SignalId.MEAS_COUNT)
    assert run(meas, [s(SignalId.DISPENSE, 10), s(SignalId.BP, 20, 130.0)]) == [
        None,
        None,
    ]
    assert values(run(meas, [s(SignalId.MEAS, 30)])) == [1.0]


def test_meas_count_first_sample_in_a_later_day_starts_that_day_at_zero() -> None:
    meas = derived(SignalId.MEAS_COUNT)
    assert meas.update(s(SignalId.DAY_END, 3 * T_DAY + 5)) is None  # 0.0 -> 0.0
    assert values([meas.update(s(SignalId.MEAS, 3 * T_DAY + 10))]) == [1.0]


def _naive_day(t: int) -> int:
    return 0 if t == 0 else -((-t) // T_DAY) - 1  # ceil(t / T_day) - 1 for t != 0


@given(st.lists(st.integers(min_value=-2 * T_DAY, max_value=4 * T_DAY), max_size=30))
def test_meas_count_matches_naive_recount_property(times: list[int]) -> None:
    times = sorted(times)
    meas = derived(SignalId.MEAS_COUNT)
    seen: list[int] = []
    current = 0.0
    for t in times:
        seen.append(t)
        out = meas.update(s(SignalId.MEAS, t))
        if out is not None:
            current = out.value
        assert current == float(sum(1 for u in seen if _naive_day(u) == _naive_day(t)))


# -- bp_pre and bp_drop ---------------------------------------------------------------


def test_bp_pre_latches_last_measurement_before_dose_and_bp_drop() -> None:
    # G-RESP-1: bp 150 at 06:45, dispense at 07:00 -> bp_pre 150; bp 132 at 08:30 ->
    # bp_drop = 150 - 132 = 18.
    pre = derived(SignalId.BP_PRE)
    drop = derived(SignalId.BP_DROP)
    stream = [
        s(SignalId.BP, hhmm(6, 45), 150.0),
        s(SignalId.DISPENSE, hhmm(7, 0)),
        s(SignalId.BP, hhmm(8, 30), 132.0),
    ]
    pre_out = run(pre, stream)
    drop_out = run(drop, stream)
    assert pre_out[:2] == [
        None,
        Sample("bp_pre", hhmm(7, 0), hhmm(7, 0), 150.0, None, None),
    ]
    assert pre_out[2] is None  # bp_pre is held until the next dispense
    assert drop_out[0] is None  # before the first dispense
    assert drop_out[1] == Sample("bp_drop", hhmm(7, 0), hhmm(7, 0), 0.0, None, None)
    assert drop_out[2] == Sample("bp_drop", hhmm(8, 30), hhmm(8, 30), 18.0, None, None)


def test_bp_pre_unavailable_before_first_dispense() -> None:
    pre = derived(SignalId.BP_PRE)
    drop = derived(SignalId.BP_DROP)
    stream = [
        s(SignalId.BP, 1_000, 150.0),
        s(SignalId.MEAS, 1_000),
        s(SignalId.BP, 2_000, 140.0),
    ]
    assert run(pre, stream) == [None, None, None]
    assert run(drop, stream) == [None, None, None]


def test_bp_pre_takes_the_value_of_the_latest_bp_not_a_later_one() -> None:
    pre = derived(SignalId.BP_PRE)
    out = run(
        pre,
        [
            s(SignalId.BP, 100, 150.0),
            s(SignalId.BP, 200, 148.0),
            s(SignalId.DISPENSE, 300),
            s(SignalId.BP, 400, 120.0),
        ],
    )
    assert values(out) == [148.0]


def test_bp_pre_overwrites_at_each_dispense_global_stream() -> None:
    # The signal form is a global stream: the second dispense overwrites the first (the
    # per-instance capture for overlapping doses belongs to the monitor, WS05-T04).
    pre = derived(SignalId.BP_PRE)
    out = run(
        pre,
        [
            s(SignalId.BP, 100, 150.0),
            s(SignalId.DISPENSE, 200),
            s(SignalId.BP, 300, 135.0),
            s(SignalId.DISPENSE, 400),
        ],
    )
    assert values(out) == [150.0, 135.0]


def test_bp_pre_is_nan_when_no_measurement_precedes_the_dispense() -> None:
    pre = derived(SignalId.BP_PRE)
    drop = derived(SignalId.BP_DROP)
    out = pre.update(s(SignalId.DISPENSE, 100))
    assert out is not None and math.isnan(out.value)
    out = drop.update(s(SignalId.DISPENSE, 100))
    assert out is not None and math.isnan(out.value)
    # a later measurement gives a NaN drop (pre-dose value unknown), never 0.0
    out = drop.update(s(SignalId.BP, 200, 120.0))
    assert out is not None and math.isnan(out.value)


def test_bp_pre_measurement_with_the_dispense_device_time_counts_as_pre_dose() -> None:
    # M5: a bp sample whose device time equals the dispense time is before the dose,
    # whichever of the two is delivered first.
    bp_first = derived(SignalId.BP_PRE)
    assert values(
        run(bp_first, [s(SignalId.BP, 100, 150.0), s(SignalId.DISPENSE, 100)])
    ) == [150.0]
    dispense_first = derived(SignalId.BP_PRE)
    out = run(dispense_first, [s(SignalId.DISPENSE, 100), s(SignalId.BP, 100, 150.0)])
    # the NaN latched at first is corrected by a second sample with the same device time
    assert math.isnan(out[0].value) and out[1] == Sample(
        "bp_pre", 100, 100, 150.0, None, None
    )  # type: ignore[union-attr]
    # a measurement one ms later is after the dose and does not change bp_pre
    later = derived(SignalId.BP_PRE)
    first, second = run(later, [s(SignalId.DISPENSE, 100), s(SignalId.BP, 101, 150.0)])
    assert first is not None and math.isnan(
        first.value
    )  # no measurement before the dose
    assert second is None  # the later measurement does not alter the latched value


def test_bp_drop_follows_every_measurement_after_a_dose() -> None:
    drop = derived(SignalId.BP_DROP)
    out = run(
        drop,
        [
            s(SignalId.BP, 100, 150.0),
            s(SignalId.DISPENSE, 200),
            s(SignalId.BP, 300, 145.0),
            s(SignalId.BP, 400, 138.0),
        ],
    )
    assert values(out) == [0.0, 5.0, 12.0]  # G-RESP-3 drops 5 and 12


def test_bp_drop_with_the_dispense_device_time_uses_the_equal_time_measurement() -> (
    None
):
    drop = derived(SignalId.BP_DROP)
    out = run(drop, [s(SignalId.DISPENSE, 100), s(SignalId.BP, 100, 150.0)])
    assert values(out)[-1] == 0.0  # pre 150 (M5) minus held bp 150


@given(
    st.lists(
        st.tuples(
            st.sampled_from(["bp", "dispense"]),
            st.integers(min_value=0, max_value=1_000),
            st.floats(min_value=50, max_value=250, allow_nan=False),
        ),
        max_size=25,
    )
)
def test_bp_pre_and_drop_match_batch_definition_property(
    raw: list[tuple[str, int, float]],
) -> None:
    # distinct device times (so the batch definition has no tie to break)
    seen_t: set[int] = set()
    stream: list[Sample] = []
    for kind, t, v in sorted(raw, key=lambda x: x[1]):
        if t in seen_t:
            continue
        seen_t.add(t)
        stream.append(s(SignalId(kind), t, v))
    pre = derived(SignalId.BP_PRE)
    drop = derived(SignalId.BP_DROP)
    bp_so_far: list[Sample] = []
    pre_now: float | None = None
    for x in stream:
        if x.signal == "bp":
            bp_so_far.append(x)
        o_pre = pre.update(x)
        o_drop = drop.update(x)
        if x.signal == "dispense":
            # batch: latest bp with device time <= dispense time, NaN if none
            want = bp_so_far[-1].value if bp_so_far else math.nan
            pre_now = want
            assert o_pre is not None
            assert (math.isnan(o_pre.value) and math.isnan(want)) or o_pre.value == want
        else:
            assert o_pre is None
        if pre_now is None:
            assert o_drop is None
        else:
            assert o_drop is not None
            held = bp_so_far[-1].value if bp_so_far else math.nan
            want_drop = pre_now - held
            assert (
                math.isnan(o_drop.value) and math.isnan(want_drop)
            ) or o_drop.value == pytest.approx(want_drop)


def test_hold_last_over_derived_output_gives_nan_before_the_first_output() -> None:
    # The grid view of a derived stream is NaN until its first sample (CG-6/CP12 reading):
    # bp_pre does not exist before the first dispense.
    pre = derived(SignalId.BP_PRE)
    outs = [
        o
        for x in (s(SignalId.BP, 100, 150.0), s(SignalId.DISPENSE, 200))
        if (o := pre.update(x)) is not None
    ]
    held = hold_last(outs, [0, 100, 200, 300])
    assert [math.isnan(v) for v in held] == [True, True, False, False]
    assert held[2] == held[3] == 150.0
