"""Time, reorder buffer and lateness (WS05-T04 tests 16 to 22).

Lateness is decided from the two clocks of an input alone, ``t_rx > t_{k_up(t_dev)} + D``; an arrival
exactly at the watermark is on time (05 section 6.1, R-late; 01 section 4.2). The task text of step 4
("an input at or below the last released watermark is late") is equivalent only when ``advance`` is
called at every ``t_k + D``; the tests below hold for any call pattern.
"""

from __future__ import annotations

import dataclasses
import random
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

import ralmon.monitor as m
from ralmon.signals import Event, EventKind, Sample
from ralmon.spec import TemplateId

from .helpers import (
    STEP,
    T_DAY,
    Inputs,
    at_step,
    by_key,
    drive,
    entry_row,
    evt,
    first_definitive,
    hhmm,
    load_f0,
    load_lib,
    make_monitor,
    registry_variant,
    smp,
)
from .scenarios import Scenario, futures, scenarios

REG = load_f0()
LIB = load_lib(REG)
D = 30_000
TICK = hhmm(9, 0)
SETTINGS = settings(
    max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow]
)


def sched_monitor(d_ms: int = D, **kwargs: Any) -> Any:
    return make_monitor(REG, d_ms=d_ms, sched=(TICK,), **kwargs)


# ---------------------------------------------------------------------------------------------
# the clock functions
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("t", "step"),
    [
        (0, 0),
        (1, 1),
        (59_999, 1),
        (60_000, 1),
        (60_001, 2),
        (24_740_000, 413),
        (24_720_000, 412),
    ],
)
def test_ceiling_rule_of_the_step(t: int, step: int) -> None:
    from ralmon.monitor.reorder import step_of

    assert step_of(t, STEP) == step


@pytest.mark.parametrize(
    ("t_dev", "t_rx", "late"),
    [
        (
            34_190_000,
            34_230_000,
            False,
        ),  # exactly at the watermark t_570 + D: on time (01 section 4.2)
        (34_190_000, 34_230_001, True),  # one millisecond later
        (34_190_000, 34_210_000, False),  # V-LATE-2
        (34_190_000, 34_240_000, True),  # V-LATE-1
        (34_200_000, 34_230_000, False),  # on the grid, step 570
        (34_200_000, 34_230_001, True),
        (34_200_001, 34_290_000, False),  # step 571: the watermark is t_571 + D
        (34_200_001, 34_290_001, True),
    ],
)
def test_lateness_is_decided_from_the_two_clocks(
    t_dev: int, t_rx: int, late: bool
) -> None:
    from ralmon.monitor.reorder import is_late

    assert is_late(t_dev, t_rx, STEP, D) is late


# ---------------------------------------------------------------------------------------------
# test 16: advance releases only inputs up to t - D
# ---------------------------------------------------------------------------------------------


def test_advance_releases_only_inputs_up_to_t_minus_delay() -> None:
    mon = sched_monitor()
    mon.push_event(evt("schedule_tick", TICK, source="care_plan"))
    for k in range(540, 570):
        mon.advance(k * STEP + D)
    # device time 09:29:50 is visible at step 570 and its watermark is 34_230_000 (09:30:30)
    mon.push_event(evt("measurement", 34_190_000, rx=34_210_000, source="cuff"))
    assert mon.advance(34_229_999) == ()  # step 570 is not finalised before t_570 + D
    records = mon.advance(34_230_000)
    sched = [r for r in records if r.instance_key == f"sched@{TICK}"]
    assert [r.t_eval_ms for r in sched] == [34_200_000]
    assert (
        sched[0].state is m.VerdictState.SATISFIED
    )  # the sample was used for step 570
    assert mon.late_inputs() == ()


def test_an_input_after_the_watermark_step_is_not_used_by_that_step() -> None:
    """Causality: device time 09:30:01 is visible at step 571, not at step 570."""
    mon = sched_monitor(d_ms=0)
    mon.push_event(evt("schedule_tick", TICK, source="care_plan"))
    mon.push_event(evt("measurement", 34_200_001, source="cuff"))
    records = []
    for k in range(540, 572):
        records += list(mon.advance(k * STEP))
    at_deadline = at_step(records, f"sched@{TICK}", 34_200_000)
    assert (
        at_deadline.state is m.VerdictState.VIOLATED
    )  # the measurement lies after the deadline
    late_one = at_step(records, f"sched@{TICK}", 34_260_000)
    assert late_one.sigma_interval.lo == late_one.sigma_interval.hi == -60_000.0


# ---------------------------------------------------------------------------------------------
# test 17: a late input is excluded, reported with its receive time, and never retracts
# ---------------------------------------------------------------------------------------------


def test_late_input_is_excluded_reported_and_never_retracts() -> None:
    sample = evt("measurement", 34_190_000, rx=34_240_000, source="cuff")
    with_late = sched_monitor()
    with_late.push_event(evt("schedule_tick", TICK, source="care_plan"))
    out_a: list[Any] = []
    for k in range(540, 571):
        out_a += list(with_late.advance(k * STEP + D))
    assert at_step(out_a, f"sched@{TICK}", 34_200_000).state is m.VerdictState.VIOLATED
    with_late.push_event(sample)  # received 09:30:40, after the watermark 09:30:30
    out_a += list(with_late.advance(34_260_000 + D))
    late = with_late.late_inputs()
    assert len(late) == 1
    assert (
        late[0].item == sample
        and late[0].t_rx_ms == 34_240_000
        and late[0].reason == "late"
    )
    assert with_late.stats().late_count == 1
    # no record changes: the run without the sample is the same
    without = sched_monitor()
    without.push_event(evt("schedule_tick", TICK, source="care_plan"))
    out_b: list[Any] = []
    for k in range(540, 572):
        out_b += list(without.advance(k * STEP + D))
    assert out_a == out_b
    verdict = at_step(out_a, f"sched@{TICK}", 34_260_000)
    assert (
        verdict.state is m.VerdictState.VIOLATED and verdict.decided_at_ms == 34_200_000
    )


def test_the_late_decision_does_not_depend_on_when_advance_is_called() -> None:
    """R-late: the same arrival is late whether or not an advance call lies between."""
    for extra_call in (False, True):
        mon = sched_monitor()
        mon.push_event(evt("schedule_tick", TICK, source="care_plan"))
        for k in range(540, 570):
            mon.advance(k * STEP + D)
        if extra_call:
            mon.advance(34_229_999)
        mon.push_event(
            evt("measurement", 34_190_000, rx=34_230_001, source="cuff")
        )  # 1 ms after the watermark
        assert len(mon.late_inputs()) == 1, extra_call
        assert mon.stats().late_count == 1


def test_an_arrival_exactly_at_the_watermark_is_on_time_even_when_advance_follows_at_that_time() -> (
    None
):
    mon = sched_monitor()
    mon.push_event(evt("schedule_tick", TICK, source="care_plan"))
    for k in range(540, 570):
        mon.advance(k * STEP + D)
    mon.push_event(evt("measurement", 34_190_000, rx=34_230_000, source="cuff"))
    out = mon.advance(34_230_000)
    assert mon.late_inputs() == ()
    assert (
        at_step(list(out), f"sched@{TICK}", 34_200_000).state
        is m.VerdictState.SATISFIED
    )


def test_an_input_pushed_after_its_step_was_finalised_is_reported_not_applied() -> None:
    """A push with t_rx not after the last advance time breaks the call order; reported, never silent."""
    mon = sched_monitor(d_ms=0)
    mon.advance(2 * STEP)
    mon.push_sample(smp("bp", STEP, 130.0, rx=STEP))
    assert mon.stats().accepted_count == 0
    (rejected,) = mon.rejected_inputs()
    assert rejected.reason == "finalised" and rejected.t_rx_ms == STEP
    assert mon.late_inputs() == ()


# ---------------------------------------------------------------------------------------------
# test 18: arrival order does not matter inside the delay
# ---------------------------------------------------------------------------------------------


def delayed(inputs: Inputs, rng: random.Random, d_ms: int) -> Inputs:
    """The same inputs with receive times t_dev + delay, delay in [0, D] (all on time)."""
    out = Inputs()
    for s in inputs.samples:
        out.samples.append(
            dataclasses.replace(s, t_rx_ms=s.t_device_ms + rng.randint(0, d_ms))
        )
    for e in inputs.events:
        out.events.append(
            dataclasses.replace(e, t_rx_ms=e.t_device_ms + rng.randint(0, d_ms))
        )
    out.avail = [(a[0], a[1], a[2], a[2]) for a in inputs.avail]
    return out


def drive_shuffled(
    mon: Any, inputs: Inputs, last: int, d_ms: int, rng: random.Random
) -> list[Any]:
    items = [it for it in inputs.merged() if it[3] != "avail"]
    avail = [it for it in inputs.merged() if it[3] == "avail"]
    pointer = 0
    out: list[Any] = []
    pending_avail = list(avail)
    for k in range(last + 1):
        t = k * STEP + d_ms
        batch = []
        while pointer < len(items) and items[pointer][0] <= t:
            batch.append(items[pointer])
            pointer += 1
        batch += [a for a in pending_avail if a[0] <= t]
        pending_avail = [a for a in pending_avail if a[0] > t]
        rng.shuffle(batch)  # arrival order inside one advance interval is arbitrary
        for _rx, _rank, _i, kind, obj in batch:
            if kind == "sample":
                mon.push_sample(obj)
            elif kind == "event":
                mon.push_event(obj)
            else:
                from ralmon.signals import SignalId

                mon.push_availability(SignalId(obj[0]), obj[1], obj[2], obj[3])
        out += list(mon.advance(t))
    return out


@SETTINGS
@given(scenarios(), st.integers(5, 330), st.integers(0, 2**32 - 1))
def test_reorder_buffer_orders_by_device_time(
    scn: Scenario, last: int, seed: int
) -> None:
    rng = random.Random(seed)
    sorted_inputs = scn.to_inputs()
    reference = drive(
        make_monitor(REG, d_ms=D, sched=scn.ticks, day_end=scn.day_end_anchors()),
        sorted_inputs,
        last,
        d_ms=D,
    )
    shuffled_inputs = delayed(sorted_inputs, rng, D)
    shuffled = drive_shuffled(
        make_monitor(REG, d_ms=D, sched=scn.ticks, day_end=scn.day_end_anchors()),
        shuffled_inputs,
        last,
        D,
        rng,
    )
    assert shuffled == reference


# ---------------------------------------------------------------------------------------------
# test 19: step alignment of impulses
# ---------------------------------------------------------------------------------------------


def test_step_alignment_of_impulses() -> None:
    """W2: an event at 06:52:20 counts at step 06:53; one at exactly 06:52:00 at step 06:52."""
    tick = hhmm(6, 50)
    for t, step in ((hhmm(6, 52, 20), 413), (hhmm(6, 52), 412)):
        mon = make_monitor(REG, sched=(tick,))
        inputs = Inputs()
        inputs.events.append(evt("measurement", t, source="cuff"))
        records = drive(mon, inputs, 414)
        before = at_step(records, f"sched@{tick}", (step - 1) * STEP)
        assert before.state is m.VerdictState.PENDING
        assert (
            before.sigma_interval.hi == (440 - step) * STEP
        )  # the earliest measurement still possible
        here = at_step(records, f"sched@{tick}", step * STEP)
        assert (
            here.state is m.VerdictState.SATISFIED and here.decided_at_ms == step * STEP
        )
        assert (here.sigma_interval.lo, here.sigma_interval.hi) == (
            (440 - step) * STEP,
        ) * 2


def test_w4_b_a_sole_measurement_at_the_anchor_step_satisfies_at_once() -> None:
    """The per-instance reading: no shadow-window violation at 09:31 (01 section 3.7 effect 1)."""
    mon = sched_monitor(d_ms=0)
    inputs = Inputs()
    inputs.events.append(evt("measurement", TICK, source="cuff"))
    records = drive(mon, inputs, 572)
    rec = at_step(records, f"sched@{TICK}", 34_260_000)
    assert rec.state is m.VerdictState.SATISFIED and rec.decided_at_ms == TICK
    assert (rec.sigma_interval.lo, rec.sigma_interval.hi) == (1_800_000.0, 1_800_000.0)


def test_w4_c_a_measurement_after_the_deadline_does_not_help() -> None:
    mon = sched_monitor(d_ms=0)
    inputs = Inputs()
    inputs.events.append(evt("measurement", hhmm(9, 31), source="cuff"))
    records = drive(mon, inputs, 572)
    rec = first_definitive(records, f"sched@{TICK}")
    assert (
        rec is not None
        and rec.state is m.VerdictState.VIOLATED
        and rec.decided_at_ms == 34_200_000
    )


def test_w4_d_an_anchor_between_two_grid_times_is_decided_one_window_after_its_step() -> (
    None
):
    anchor = hhmm(9, 0, 20)
    mon = make_monitor(REG, sched=(anchor,))
    records = drive(mon, Inputs(), 575)
    mine = by_key(records)[f"sched@{anchor}"]
    assert mine[0].t_eval_ms == 541 * STEP and mine[0].pending_until_ms == 34_260_000
    deciding = first_definitive(records, f"sched@{anchor}")
    assert deciding is not None and deciding.decided_at_ms == 34_260_000
    # the event-time latency from the anchor is below W + T_s (W4 d)
    assert 1_800_000 <= deciding.decided_at_ms - anchor < 1_800_000 + STEP


# ---------------------------------------------------------------------------------------------
# test 20: latency bounds per template
# ---------------------------------------------------------------------------------------------


def test_verdict_latency_bound_reported_per_template() -> None:
    mon = make_monitor(REG, d_ms=D)
    assert mon.verdict_latency_bound_ms(TemplateId.RESP) == 10_890_000
    assert mon.verdict_latency_bound_ms(TemplateId.SCHED) == 1_890_000
    for tid in (
        TemplateId.RANGE,
        TemplateId.HOLD,
        TemplateId.COUNT,
        TemplateId.SYS,
        TemplateId.INT,
    ):
        assert mon.verdict_latency_bound_ms(tid) == STEP + D, tid
    plain = make_monitor(REG, d_ms=0)
    assert plain.verdict_latency_bound_ms(TemplateId.RESP) == 10_860_000
    assert plain.verdict_latency_bound_ms(TemplateId.SCHED) == 1_860_000
    assert isinstance(plain.verdict_latency_bound_ms(TemplateId.RANGE), int)


# ---------------------------------------------------------------------------------------------
# test 21: definitive records are emitted within the bound
# ---------------------------------------------------------------------------------------------


def anchor_of(key: str) -> int:
    return int(key.split("@")[1].split("#")[0])


@SETTINGS
@given(scenarios(), st.integers(10, 330), st.sampled_from([0, D]))
def test_definitive_records_are_emitted_within_the_bound(
    scn: Scenario, last: int, d_ms: int
) -> None:
    mon = make_monitor(REG, d_ms=d_ms, sched=scn.ticks, day_end=scn.day_end_anchors())
    records = drive(mon, scn.to_inputs(), last, d_ms=d_ms)
    for key, recs in by_key(records).items():
        first = first_definitive(recs, key)
        if first is None:
            continue
        bound = mon.verdict_latency_bound_ms(first.template)
        emitted = (
            first.t_eval_ms + d_ms
        )  # the argument of the advance that returns the record
        assert emitted - anchor_of(key) <= bound, (key, emitted, bound)
        assert first.decided_at_ms is not None and first.decided_at_ms >= 0
        if first.template is not TemplateId.COUNT or not key.endswith(f"@{T_DAY}"):
            assert first.decided_at_ms >= anchor_of(key), (
                key
            )  # decided at a step at or after the anchor


def test_the_latency_bound_is_attained_to_within_a_millisecond() -> None:
    """Lemma 13: an anchor 1 ms after a grid time with no measurement decides B + T_s - 1 ms later."""
    anchor = hhmm(9, 0, 0, 1)
    mon = make_monitor(REG, sched=(anchor,))
    records = drive(mon, Inputs(), 575)
    deciding = first_definitive(records, f"sched@{anchor}")
    assert deciding is not None
    assert deciding.decided_at_ms - anchor == 1_800_000 + STEP - 1


# ---------------------------------------------------------------------------------------------
# test 22: advance is causal
# ---------------------------------------------------------------------------------------------


@SETTINGS
@given(scenarios(), st.integers(5, 330), st.sampled_from([0, D]), st.data())
def test_advance_is_causal(
    scn: Scenario, cut: int, d_ms: int, data: st.DataObject
) -> None:
    base = scn.truncated(cut)
    future = data.draw(futures(cut))
    other = Scenario(
        meas=base.meas + future.meas,
        dispenses=base.dispenses + future.dispenses,
        presence=base.presence + future.presence,
        intakes=base.intakes,
        auths=base.auths,
        standalone_bp=base.standalone_bp,
        ticks=base.ticks,
        day_end=base.day_end,
        unavailable_presence=base.unavailable_presence,
        unavailable_intake=base.unavailable_intake,
    )
    inputs_a, inputs_b = base.to_inputs(), other.to_inputs()
    # the device clock of the extra inputs runs ahead: they are received at once (t_rx = the cut)
    inputs_b.samples = [
        dataclasses.replace(s, t_rx_ms=min(s.t_rx_ms, cut * STEP))
        if s.t_device_ms > cut * STEP
        else s
        for s in inputs_b.samples
    ]
    inputs_b.events = [
        dataclasses.replace(e, t_rx_ms=min(e.t_rx_ms, cut * STEP))
        if e.t_device_ms > cut * STEP
        else e
        for e in inputs_b.events
    ]
    run_a = drive(
        make_monitor(REG, d_ms=d_ms, sched=base.ticks, day_end=base.day_end_anchors()),
        inputs_a,
        cut,
        d_ms=d_ms,
    )
    run_b = drive(
        make_monitor(REG, d_ms=d_ms, sched=base.ticks, day_end=base.day_end_anchors()),
        inputs_b,
        cut,
        d_ms=d_ms,
    )
    assert [r for r in run_a if r.t_eval_ms <= cut * STEP] == [
        r for r in run_b if r.t_eval_ms <= cut * STEP
    ]


# ---------------------------------------------------------------------------------------------
# the lateness rule does not depend on the advance pattern (R-late)
# ---------------------------------------------------------------------------------------------


@SETTINGS
@given(scenarios(), st.integers(0, 2**32 - 1), st.integers(0, 4))
def test_acceptance_depends_on_the_two_clocks_not_on_the_advance_pattern(
    scn: Scenario, seed: int, extra: int
) -> None:
    rng = random.Random(seed)
    inputs = scn.to_inputs()
    arrivals = Inputs()
    for s in inputs.samples:
        arrivals.samples.append(
            dataclasses.replace(s, t_rx_ms=s.t_device_ms + rng.randint(0, 2 * D))
        )
    for e in inputs.events:
        arrivals.events.append(
            dataclasses.replace(e, t_rx_ms=e.t_device_ms + rng.randint(0, 2 * D))
        )
    last = 120
    aligned = make_monitor(REG, d_ms=D, sched=scn.ticks)
    rec_a = drive(aligned, arrivals, last, d_ms=D)
    # a different pattern: extra calls at random times between the steps, same pushes
    random_pattern = make_monitor(REG, d_ms=D, sched=scn.ticks)
    items = arrivals.merged()
    times = sorted(
        {k * STEP + D for k in range(last + 1)}
        | {rng.randint(0, last * STEP + D) for _ in range(extra * 5)}
    )
    pointer, rec_b = 0, []
    for t in times:
        while pointer < len(items) and items[pointer][0] <= t:
            obj = items[pointer][4]
            (
                random_pattern.push_sample
                if isinstance(obj, Sample)
                else random_pattern.push_event
            )(obj)
            pointer += 1
        rec_b += list(random_pattern.advance(t))
    assert rec_a == rec_b
    expected_late = {
        id(x)
        for x in (*arrivals.samples, *arrivals.events)
        if x.t_rx_ms > ((x.t_device_ms + STEP - 1) // STEP) * STEP + D
        and x.t_rx_ms <= last * STEP + D
    }
    for mon in (aligned, random_pattern):
        got = {id(r.item) for r in mon.late_inputs()}
        assert got == expected_late


# ---------------------------------------------------------------------------------------------
# the reorder buffer, bounded, and the other rejections (all reported, none silent)
# ---------------------------------------------------------------------------------------------


def test_buffer_orders_by_device_time_with_pressure_before_dispense_on_ties() -> None:
    from ralmon.monitor.reorder import BufferedInput, ReorderBuffer

    buf = ReorderBuffer(10)
    items = [
        BufferedInput(30, 30, "event", "dispense-30", None),
        BufferedInput(10, 99, "sample", "bp-10", None),
        BufferedInput(30, 31, "sample", "bp-30", None),
        BufferedInput(20, 20, "event", "meas-20", None),
    ]
    for it in items:
        assert buf.push(it)
    assert len(buf) == 4
    assert [x.item for x in buf.release(20)] == ["bp-10", "meas-20"]
    assert len(buf) == 2
    assert [x.item for x in buf.release(30)] == [
        "bp-30",
        "dispense-30",
    ]  # M5: the sample first
    assert buf.release(10**9) == []


def test_buffer_ties_follow_seq_then_receive_time() -> None:
    from ralmon.monitor.reorder import BufferedInput, ReorderBuffer

    buf = ReorderBuffer(10)
    buf.push(BufferedInput(10, 5, "sample", "seq-2", 2))
    buf.push(BufferedInput(10, 9, "sample", "seq-1", 1))
    buf.push(BufferedInput(20, 9, "sample", "rx-9", None))
    buf.push(BufferedInput(20, 5, "sample", "rx-5", None))
    assert [x.item for x in buf.release(20)] == ["seq-1", "seq-2", "rx-5", "rx-9"]


def test_buffer_is_bounded_and_reports_the_overflow() -> None:
    from ralmon.monitor.reorder import BufferedInput, ReorderBuffer

    buf = ReorderBuffer(2)
    assert buf.push(BufferedInput(1, 1, "sample", "a", None))
    assert buf.push(BufferedInput(2, 2, "sample", "b", None))
    assert not buf.push(
        BufferedInput(3, 3, "sample", "c", None)
    )  # full: refused, the caller reports it
    assert len(buf) == 2
    assert buf.release(1)  # room again
    assert buf.push(BufferedInput(3, 3, "sample", "c", None))


def test_monitor_reports_over_capacity_inputs() -> None:
    mon = make_monitor(REG, buffer_capacity=3)
    for i in range(5):
        mon.push_sample(smp("bp", i * 1000, 120.0 + i))
    stats = mon.stats()
    assert stats.buffered_inputs == 3 and stats.overflow_count == 2
    rejected = mon.rejected_inputs()
    assert [r.reason for r in rejected] == ["capacity", "capacity"]
    assert [r.item.value for r in rejected] == [123.0, 124.0]
    assert mon.late_inputs() == ()
    mon.advance(STEP)  # releases the three buffered samples: room again
    mon.push_sample(smp("bp", 2 * STEP, 140.0))
    assert mon.stats().buffered_inputs == 1 and mon.stats().overflow_count == 2


def test_capacity_must_be_a_positive_integer() -> None:
    for bad in (0, -1, True, 1.5, None, "3"):
        with pytest.raises(m.MonitorConfigError):
            make_monitor(REG, buffer_capacity=bad)


def test_the_default_capacity_is_a_named_constant() -> None:
    from ralmon.monitor import core

    assert (
        isinstance(core.DEFAULT_BUFFER_CAPACITY, int)
        and core.DEFAULT_BUFFER_CAPACITY > 0
    )


def test_a_repeated_seq_is_a_duplicate_not_counted_and_not_an_anchor() -> None:
    """Rule R8 (08 section 5.3): a repeated accepted (source, name, seq) is flagged and not counted."""
    mon = make_monitor(REG)
    mon.push_event(evt("dispense", hhmm(7, 0), source="dispenser", seq=7))
    mon.push_event(
        evt("dispense", hhmm(7, 0, 30), source="dispenser", seq=7)
    )  # replay with a fresh stamp
    mon.push_event(evt("dispense", hhmm(7, 1), source="dispenser", seq=8))
    records = []
    for k in range(425):
        records += list(mon.advance(k * STEP))
    keys = {r.instance_key for r in records}
    assert f"count@{hhmm(7, 0)}" in keys and f"count@{hhmm(7, 1)}" in keys
    assert f"count@{hhmm(7, 0, 30)}" not in keys
    assert mon.stats().duplicate_count == 1
    (dup,) = mon.rejected_inputs()
    assert dup.reason == "duplicate"
    count_rec = at_step(records, f"count@{hhmm(7, 1)}", hhmm(7, 1))
    assert (count_rec.sigma_interval.lo, count_rec.sigma_interval.hi) == (
        0.0,
        0.0,
    )  # 2 - 2, the replay not counted


def test_equal_seq_of_different_names_is_not_a_duplicate() -> None:
    mon = make_monitor(REG)
    mon.push_event(evt("measurement", hhmm(9, 0), source="cuff", seq=101))
    mon.push_sample(smp("bp", hhmm(9, 0), 125.0, seq=101))
    mon.push_sample(smp("cuff_health", hhmm(9, 0), 1.0, seq=101))
    assert mon.stats().duplicate_count == 0 and mon.rejected_inputs() == ()


def test_a_future_stamp_beyond_the_skew_bound_is_excluded_and_counted(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """M4 (01 section 4.4): ``t_device > t_rx + skew_max`` is not used; the bound is a registry name."""
    registry = registry_variant(
        tmp_path_factory.mktemp("skew"),
        add_entries=[entry_row("clock_skew_max_ms", 1000.0)],
    )
    mon = make_monitor(registry)
    mon.push_sample(
        smp("bp", 5_000 + 1000, 150.0, rx=5_000)
    )  # exactly at the bound: used
    mon.push_sample(
        smp("bp", 8_000 + 1001, 151.0, rx=8_000)
    )  # one millisecond beyond: excluded
    stats = mon.stats()
    assert stats.future_stamped_count == 1 and stats.accepted_count == 1
    (rej,) = mon.rejected_inputs()
    assert rej.reason == "future_stamp" and rej.item.value == 151.0
    assert mon.stats().future_stamp_check is True


def test_without_a_skew_entry_the_future_stamp_check_is_off_and_says_so() -> None:
    mon = make_monitor(REG)
    mon.push_sample(smp("bp", 9_000_000, 150.0, rx=1_000))
    assert (
        mon.stats().future_stamp_check is False
        and mon.stats().future_stamped_count == 0
    )


def test_evidence_only_events_are_counted_and_not_buffered() -> None:
    mon = make_monitor(REG)
    for kind in ("measurement_missed", "node_state", "robot_task", "device_error"):
        mon.push_event(Event(EventKind(kind), 0, 0, "x", {}, None))
    stats = mon.stats()
    assert (
        stats.ignored_events == 4
        and stats.buffered_inputs == 0
        and stats.accepted_count == 0
    )


def test_advance_with_a_smaller_time_is_refused_and_an_equal_time_is_a_noop() -> None:
    mon = make_monitor(REG)
    mon.advance(10 * STEP)
    assert mon.advance(10 * STEP) == ()
    with pytest.raises(m.MonitorInputError):
        mon.advance(10 * STEP - 1)


def test_advance_before_the_first_step_finalises_nothing() -> None:
    mon = sched_monitor()
    assert mon.advance(0) == ()  # t - D < 0: no step yet
    assert mon.advance(D - 1) == ()
    assert mon.stats().steps_finalised == 0
    mon.advance(D)  # step 0 is finalised at t_0 + D
    assert mon.stats().steps_finalised == 1


def test_a_huge_jump_is_refused_before_any_state_changes() -> None:
    from ralmon.monitor import core

    mon = sched_monitor(d_ms=0)
    limit = core.MAX_STEPS_PER_ADVANCE
    with pytest.raises(m.MonitorInputError):
        mon.advance((limit + 1) * STEP)
    assert mon.stats().steps_finalised == 0
    mon.advance(2 * STEP)  # the monitor is intact and can still advance
    assert mon.stats().steps_finalised == 3
