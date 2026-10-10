"""Availability of the robot channels from the ``NODE_STATE colocated`` reports (WS05-T11, ADR-054 (b)).

The translation lives in ``StreamingMonitor.push_event``: a ``NODE_STATE`` event of the robot with a
boolean ``payload.colocated`` is an availability mark of BOTH robot channels (``presence`` and
``intake``: one mask, H-MASK of ``docs/models/evidence-channels.md``), at the device time and receive
time of the event, ordered and late by the same rule as any input. ``run_offline`` and a hand-driven
``StreamingMonitor`` therefore share it, and no public name is added.

Reading chosen for H-INIT ("the robot channels are unavailable until a status report says that the robot
is co-located"). A streaming monitor cannot know at step 0 whether the trace will carry reports, and a
trace without reports (every golden case, every trace written before the reports existed) must give the
records it gave before. So the mask starts as the monitor always started it, "available until marked", and
the first report is the first mark; when that first mark is a report, the presence level held from before
it is cleared (a sample used before the first report belongs to no episode that a report opened) and the
gate counts the sample. What differs from strict H-INIT is then only the name of the marker before the
first arrival (``value_undefined:presence`` instead of ``channel_unavailable:presence``).
``test_before_the_first_report_the_channels_are_available`` and ``test_a_level_held_from_before_the_first_
arrival_report_does_not_witness`` state it; marks given by ``push_availability`` keep their reading.

Fixture-only: registry F0, ``step_ms = 60000`` (fixture arithmetic, ADR-027).
"""

from __future__ import annotations

from typing import Any

import ralmon.monitor as m
from ralmon.signals import Event, EventKind, SignalId

from .helpers import (
    STEP,
    LocalDay,
    evt,
    final,
    hhmm,
    load_f0,
    load_lib,
    make_config,
    make_monitor,
    make_plan,
    smp,
)
from .test_field_fuzz import Leaks, pool, tampered

REG = load_f0()
LIB = load_lib(REG)
T_DAY = 86_400_000


def report(
    t: int,
    colocated: Any,
    *,
    rx: int | None = None,
    source: str = "robot",
    seq: int | None = None,
    **extra: Any,
) -> Event:
    """A ``NODE_STATE`` report of ``source`` with ``payload.colocated`` (and ``state`` unless overridden)."""
    payload: dict[str, Any] = {"state": "active", "colocated": colocated}
    payload.update(extra)
    return Event(EventKind.NODE_STATE, t, t if rx is None else rx, source, payload, seq)


def int_record(records: Any, t_dispense: int) -> Any:
    return final(records, f"int@{t_dispense}")


def visit_day() -> tuple[list[Any], list[Any]]:
    """One visit 07:00 to 07:10 (arrival report, presence 1.0, departure report), a dispense at 21:00."""
    samples = [smp("presence", hhmm(7, 0), 1.0)]
    events = [
        report(hhmm(7, 0), True),
        report(hhmm(7, 10), False),
        evt("dispense", hhmm(21, 0)),
    ]
    return samples, events


def run_stream(
    samples: list[Any], events: list[Any], last_ms: int, **kwargs: Any
) -> Any:
    mon = make_monitor(**kwargs)
    for s in samples:
        mon.push_sample(s)
    for e in events:
        mon.push_event(e)
    return mon, mon.advance(last_ms)


# ---------------------------------------------------------------------------------------------
# 1 and 2: reproducer 2 of ADR-054, with the reports
# ---------------------------------------------------------------------------------------------


def test_departure_report_ends_the_witness() -> None:
    samples, events = visit_day()
    mon, records = run_stream(samples, events, hhmm(21, 0))
    rec = int_record(records, hhmm(21, 0))
    assert (
        rec.state.value == "pending"
    )  # before this task: SATISFIED on a 14-hour-old sample
    assert rec.undecidable is not None
    assert "channel_unavailable:presence" in rec.undecidable
    assert mon.stats().availability_reports == 2


def test_a_visit_at_the_dispense_witnesses_it() -> None:
    mon = make_monitor()
    mon.push_event(report(hhmm(20, 58), True))
    mon.push_sample(smp("presence", hhmm(21, 0), 1.0))
    mon.push_event(evt("dispense", hhmm(21, 0)))
    rec = int_record(mon.advance(hhmm(21, 0)), hhmm(21, 0))
    assert rec.state.value == "satisfied"
    assert rec.sigma_interval.lo == 300_000  # int_window of F0, age 0


def test_an_earlier_visit_does_not_witness_a_later_dispense_even_if_the_robot_returns_late() -> (
    None
):
    """The robot is back at 20:56 but has not yet seen the patient: the level of the 07:00 visit is gone."""
    samples, events = visit_day()
    events.append(report(hhmm(20, 56), True))
    _mon, records = run_stream(samples, events, hhmm(21, 0))
    rec = int_record(records, hhmm(21, 0))
    assert rec.state.value == "pending"
    assert rec.undecidable is not None
    assert "value_undefined:presence" in rec.undecidable


# ---------------------------------------------------------------------------------------------
# 3: one mask for both channels
# ---------------------------------------------------------------------------------------------


def test_reports_drive_both_channels() -> None:
    by_report = make_monitor()
    by_mark = make_monitor()
    for mon in (by_report, by_mark):
        mon.push_sample(smp("presence", hhmm(20, 0), 1.0))
        mon.push_event(evt("dispense", hhmm(21, 0)))
    by_report.push_event(report(hhmm(20, 0), True))
    by_report.push_event(report(hhmm(20, 50), False))
    by_mark.push_availability(SignalId.PRESENCE, True, hhmm(20, 0), hhmm(20, 0))
    by_mark.push_availability(SignalId.INTAKE, True, hhmm(20, 0), hhmm(20, 0))
    by_mark.push_availability(SignalId.PRESENCE, False, hhmm(20, 50), hhmm(20, 50))
    by_mark.push_availability(SignalId.INTAKE, False, hhmm(20, 50), hhmm(20, 50))
    got = by_report.advance(hhmm(21, 0))
    want = by_mark.advance(hhmm(21, 0))
    assert got == want
    rec = int_record(got, hhmm(21, 0))
    assert rec.undecidable is not None
    assert "channel_unavailable:presence" in rec.undecidable
    assert (
        "channel_unavailable:intake" in rec.undecidable
    )  # the same mask applies to intake


def test_an_arrival_report_makes_both_channels_available_again() -> None:
    mon = make_monitor()
    mon.push_event(report(hhmm(7, 0), False))
    mon.push_event(report(hhmm(20, 0), True))
    mon.push_sample(smp("presence", hhmm(20, 58), 1.0))
    mon.push_event(evt("dispense", hhmm(21, 0)))
    rec = int_record(mon.advance(hhmm(21, 0)), hhmm(21, 0))
    assert rec.state.value == "satisfied"


# ---------------------------------------------------------------------------------------------
# 4: the gate
# ---------------------------------------------------------------------------------------------


def test_gate_is_zero_with_reports() -> None:
    samples, events = visit_day()
    mon, _ = run_stream(samples, events, hhmm(21, 0))
    assert mon.stats().presence_samples_without_availability_marks == 0


def test_gate_stays_positive_on_a_day_without_reports() -> None:
    samples, events = visit_day()
    only_dispense = [e for e in events if e.kind is EventKind.DISPENSE]
    mon, records = run_stream(samples, only_dispense, hhmm(21, 0))
    assert mon.stats().presence_samples_without_availability_marks == 1
    # the hazard is still there and still reported, never hidden
    rec = int_record(records, hhmm(21, 0))
    assert rec.state.value == "satisfied"
    assert (rec.sigma_interval.lo, rec.sigma_interval.hi) == (300_000, 300_000)
    stale = mon.stats().presence_level_older_than_window_steps
    assert stale == hhmm(21, 0) // STEP - (hhmm(7, 0) // STEP + 300_000 // STEP)
    assert mon.stats().availability_reports == 0


# ---------------------------------------------------------------------------------------------
# 5: traces without reports are unchanged
# ---------------------------------------------------------------------------------------------


def test_traces_without_reports_are_unchanged() -> None:
    """NODE_STATE events without ``colocated`` (state reports of any node) are ignored as before."""
    samples = [smp("presence", hhmm(20, 58), 1.0)]
    base = [evt("dispense", hhmm(21, 0))]
    noise = [
        Event(
            EventKind.NODE_STATE,
            hhmm(7, 0),
            hhmm(7, 0),
            "robot",
            {"state": "inactive"},
            None,
        ),
        Event(
            EventKind.NODE_STATE,
            hhmm(8, 0),
            hhmm(8, 0),
            "gateway",
            {"state": "link_down"},
            None,
        ),
        Event(EventKind.NODE_STATE, hhmm(9, 0), hhmm(9, 0), "robot", {}, None),
    ]
    plain_mon, plain = run_stream(samples, base, hhmm(21, 5))
    noisy_mon, noisy = run_stream(samples, base + noise, hhmm(21, 5))
    assert noisy == plain
    stats = noisy_mon.stats()
    assert stats.ignored_events == plain_mon.stats().ignored_events + 3
    assert stats.availability_reports == 0
    assert stats.colocated_reports_ignored == 0
    assert stats.presence_samples_without_availability_marks == 1


def test_before_the_first_report_the_channels_are_available() -> None:
    """The reading of H-INIT chosen here (module docstring): the mask starts as before this task, so a run
    with reports equals a run without them up to the first report."""
    with_reports = make_monitor()
    without = make_monitor()
    for mon in (with_reports, without):
        mon.push_event(evt("dispense", hhmm(6, 0)))
    with_reports.push_event(report(hhmm(7, 0), True))
    got = with_reports.advance(hhmm(6, 59))
    want = without.advance(hhmm(6, 59))
    assert got == want
    rec = int_record(got, hhmm(6, 0))
    assert rec.undecidable is not None and "value_undefined:presence" in rec.undecidable


# ---------------------------------------------------------------------------------------------
# 6: a report is ordered and late like an input; foreign and malformed reports are ignored and counted
# ---------------------------------------------------------------------------------------------


def test_a_report_is_ordered_and_late_like_an_input() -> None:
    d_ms = 5 * STEP
    mon = make_monitor(d_ms=d_ms)
    mon.push_sample(smp("presence", hhmm(7, 0), 1.0))
    # arrives out of order but within the reorder delay: applied in device order
    mon.push_event(report(hhmm(7, 10), False, rx=hhmm(7, 10)))
    mon.push_event(report(hhmm(7, 5), True, rx=hhmm(7, 9)))
    late = report(hhmm(7, 20), True, rx=hhmm(7, 20) + 6 * STEP)
    mon.push_event(late)
    assert [r.item for r in mon.late_inputs()] == [late]
    mon.push_event(evt("dispense", hhmm(21, 0)))
    records = mon.advance(hhmm(21, 0) + d_ms)
    rec = int_record(records, hhmm(21, 0))
    # the late arrival report is refused: the departure of 07:10 stays the last mark
    assert rec.state.value == "pending"
    assert rec.undecidable is not None and "channel_unavailable" in rec.undecidable
    stats = mon.stats()
    assert stats.late_count == 1
    assert stats.availability_reports == 2  # the late one was not used


def test_a_report_of_another_node_or_without_a_boolean_is_ignored_and_counted() -> None:
    mon = make_monitor()
    mon.push_sample(smp("presence", hhmm(20, 58), 1.0))
    ignored = [
        report(hhmm(7, 0), False, source="gateway"),
        report(hhmm(7, 1), False, source="ward"),
        report(hhmm(7, 2), 0),
        report(hhmm(7, 3), 1),
        report(hhmm(7, 4), "false"),
        report(hhmm(7, 5), None),
        report(hhmm(7, 6), 0.0),
    ]
    for event in ignored:
        mon.push_event(event)
    mon.push_event(evt("dispense", hhmm(21, 0)))
    rec = int_record(mon.advance(hhmm(21, 0)), hhmm(21, 0))
    assert rec.state.value == "satisfied"  # none of them marked a channel
    stats = mon.stats()
    assert stats.colocated_reports_ignored == len(ignored)
    assert stats.ignored_events == len(ignored)
    assert stats.availability_reports == 0
    assert stats.presence_samples_without_availability_marks == 1


def test_a_duplicate_report_is_refused_like_a_duplicate_event() -> None:
    mon = make_monitor()
    mon.push_event(report(hhmm(7, 0), True, seq=5))
    mon.push_event(report(hhmm(7, 0), True, seq=5))
    mon.advance(hhmm(8, 0))
    assert mon.stats().duplicate_count == 1
    assert mon.stats().availability_reports == 1


def test_a_report_for_a_finalised_step_is_refused() -> None:
    mon = make_monitor()
    mon.advance(hhmm(8, 0))
    mon.push_event(report(hhmm(7, 0), False))
    assert mon.stats().after_finalisation_count == 1
    assert mon.stats().availability_reports == 0


# ---------------------------------------------------------------------------------------------
# 7: run_offline and a hand-driven monitor agree
# ---------------------------------------------------------------------------------------------


def test_offline_and_streaming_agree() -> None:
    samples = [
        smp("presence", hhmm(7, 0), 1.0),
        smp("presence", hhmm(20, 57), 1.0),
    ]
    events = [
        report(hhmm(7, 0), True),
        evt("dispense", hhmm(7, 2)),
        evt("intake", hhmm(7, 4), source="robot"),
        report(hhmm(7, 10), False),
        report(hhmm(20, 56), True),
        report(hhmm(21, 5), False),
        evt("dispense", hhmm(21, 0)),
        evt("intake", hhmm(21, 1), source="robot"),
    ]
    plan = make_plan(REG)
    for d_ms in (0, 30_000):
        config = make_config(REG, d_ms=d_ms)
        day = LocalDay(tuple(samples), tuple(events))
        got = m.run_offline(day, plan, config, None, None, registry=REG, templates=LIB)

        mon = m.StreamingMonitor(config, REG, LIB)
        mon.load(plan)
        items: list[tuple[int, int, Any]] = [(s.t_rx_ms, 0, s) for s in samples]
        items += [(e.t_rx_ms, 1, e) for e in events]
        items.sort(key=lambda it: (it[0], it[1]))
        pointer, want = 0, []
        for k in range(T_DAY // STEP + 1):
            t = k * STEP + d_ms
            while pointer < len(items) and items[pointer][0] <= t:
                obj = items[pointer][2]
                (mon.push_sample if items[pointer][1] == 0 else mon.push_event)(obj)
                pointer += 1
            want += list(mon.advance(t))
        assert tuple(got) == tuple(want)
        assert mon.stats().availability_reports == 4
        assert mon.stats().presence_samples_without_availability_marks == 0
        # the 21:00 dispense is witnessed by the visit of 20:56 to 21:05
        assert int_record(got, hhmm(21, 0)).state.value == "satisfied"
        # and the dispense of 07:02 by the first visit
        assert int_record(got, hhmm(7, 2)).state.value == "satisfied"


# ---------------------------------------------------------------------------------------------
# 8: hostile reports
# ---------------------------------------------------------------------------------------------


def test_hostile_reports_raise_only_named_errors() -> None:
    leaks = Leaks()
    good = report(hhmm(7, 0), True)
    for value in pool():
        mon = make_monitor()
        leaks.run("colocated", mon.push_event, report(hhmm(7, 0), value))
        mon = make_monitor()
        leaks.run("payload", mon.push_event, tampered(good, "payload", value))
        mon = make_monitor()
        leaks.run("source", mon.push_event, tampered(good, "source", value))
        mon = make_monitor()
        leaks.run("state", mon.push_event, report(hhmm(7, 0), True, state=value))
        mon = make_monitor()
        leaks.run("t_device", mon.push_event, tampered(good, "t_device_ms", value))
        mon = make_monitor()
        leaks.run("t_rx", mon.push_event, tampered(good, "t_rx_ms", value))
        mon = make_monitor()
        leaks.run("seq", mon.push_event, tampered(good, "seq", value))
        # whatever was pushed, the monitor still runs and answers
        leaks.run("advance", mon.advance, hhmm(8, 0))
        leaks.run("stats", mon.stats)
    leaks.check()


# ---------------------------------------------------------------------------------------------
# M1 of the review: a presence level held from before the FIRST report must not count (H-INIT)
# ---------------------------------------------------------------------------------------------


def test_a_level_held_from_before_the_first_arrival_report_does_not_witness() -> None:
    """Probe of the review: presence 1.0 at 07:00 with no arrival report, one arrival report later in the
    day, a dispense at 21:00. The level is 14 hours old and belongs to no episode that a report opened:
    INT must not be SATISFIED (strict H-INIT gives PENDING value_undefined:presence) and the gate must not
    say 0 for a presence sample that was used before the first mark of a run that has marks."""
    for arrival in (hhmm(20, 0), hhmm(20, 50)):
        mon = make_monitor()
        mon.push_sample(smp("presence", hhmm(7, 0), 1.0))
        mon.push_event(report(arrival, True))
        mon.push_event(evt("dispense", hhmm(21, 0)))
        rec = int_record(mon.advance(hhmm(21, 0)), hhmm(21, 0))
        assert rec.state.value == "pending", arrival
        assert rec.undecidable is not None
        assert "value_undefined:presence" in rec.undecidable
        assert mon.stats().presence_samples_without_availability_marks == 1


def test_a_sample_after_the_first_arrival_report_is_a_witness() -> None:
    mon = make_monitor()
    mon.push_sample(smp("presence", hhmm(7, 0), 1.0))
    mon.push_event(report(hhmm(20, 50), True))
    mon.push_sample(smp("presence", hhmm(20, 58), 1.0))
    mon.push_event(evt("dispense", hhmm(21, 0)))
    rec = int_record(mon.advance(hhmm(21, 0)), hhmm(21, 0))
    assert rec.state.value == "satisfied"
    assert (
        mon.stats().presence_samples_without_availability_marks == 1
    )  # the 07:00 sample


def test_a_first_report_that_is_a_departure_still_ends_the_witness_and_is_gated() -> (
    None
):
    mon = make_monitor()
    mon.push_sample(smp("presence", hhmm(7, 0), 1.0))
    mon.push_event(report(hhmm(7, 10), False))
    mon.push_event(evt("dispense", hhmm(21, 0)))
    rec = int_record(mon.advance(hhmm(21, 0)), hhmm(21, 0))
    assert rec.state.value == "pending"
    assert rec.undecidable is not None
    assert "channel_unavailable:presence" in rec.undecidable
    assert mon.stats().presence_samples_without_availability_marks == 1


def test_a_trace_without_reports_keeps_its_behaviour_and_its_gate() -> None:
    plain = make_monitor()
    plain.push_sample(smp("presence", hhmm(7, 0), 1.0))
    plain.push_event(evt("dispense", hhmm(21, 0)))
    rec = int_record(plain.advance(hhmm(21, 0)), hhmm(21, 0))
    assert rec.state.value == "satisfied"
    assert plain.stats().presence_samples_without_availability_marks == 1
    # marks given by push_availability (the harness form, CG-6) keep their reading: the first mark clears
    # the gate whenever it arrives and a True mark does not clear the held level
    marked = make_monitor()
    marked.push_sample(smp("presence", hhmm(7, 0), 1.0))
    marked.push_availability(SignalId.PRESENCE, True, hhmm(20, 0), hhmm(20, 0))
    marked.push_event(evt("dispense", hhmm(21, 0)))
    rec = int_record(marked.advance(hhmm(21, 0)), hhmm(21, 0))
    assert rec.state.value == "satisfied"
    assert marked.stats().presence_samples_without_availability_marks == 0


def test_the_sample_of_the_arrival_instant_is_not_gated() -> None:
    """A sample and the arrival report of one device time: the report is applied first."""
    mon = make_monitor()
    mon.push_sample(smp("presence", hhmm(7, 0), 1.0))
    mon.push_event(report(hhmm(7, 0), True))
    mon.push_event(evt("dispense", hhmm(7, 2)))
    rec = int_record(mon.advance(hhmm(7, 5)), hhmm(7, 2))
    assert rec.state.value == "satisfied"
    assert mon.stats().presence_samples_without_availability_marks == 0
