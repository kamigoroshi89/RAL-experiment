"""The presence witness of INT across outages of the robot channel (WS05-T04, review round 1, B1).

Reference semantics adopted here (proposed in ADR-054, ``[DA-CONFERMARE]``): ``presence`` exists only
while the robot is co-located (``02-interfaces.md#signals``, rule; ``01-signals-sampling.md`` section
2.2), so its held level belongs to one co-location episode. A step at which the channel is marked
unavailable clears the level: after the channel returns, the level is undefined until a new sample
arrives (``value_undefined:presence``), never the level of an earlier visit.

What this does NOT cover by itself: a trace that carries no availability mark and no zero-valued presence
sample (the output of the benchmark generator before the reports of ADR-054 (b), WS04-T06 test 11) keeps the
level of the last robot visit for the rest of the day, so every later dispense with an old enough sample is
witnessed; WS05-T11 makes the ``NODE_STATE colocated`` reports the mask (tests/monitor/test_availability_
reports.py) and keeps this behaviour, reported by the gate, for a trace that carries none. ``docs/formal/02-
templates.md`` section 4.7 and TG-9 state that a witness that has left needs an explicit ``0`` sample
or an availability mask. ``MonitorStats.presence_samples_without_availability_marks`` is the gate (non-zero
exactly when presence samples were used and no mark for ``presence`` ever arrived);
``presence_level_older_than_window_steps`` is information only.
"""

from __future__ import annotations

from typing import Any

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from ralmon.monitor import make_point_evaluator
from ralmon.signals import SignalId

from .helpers import (
    STEP,
    Inputs,
    drive,
    evt,
    final,
    hhmm,
    make_monitor,
    smp,
)
from .scenarios import Scenario
from .test_boundaries import against_oracle

INT_WINDOW = 300_000  # int_window of F0 (fixture arithmetic)


def int_record(records: Any, t_dispense: int) -> Any:
    return final(records, f"int@{t_dispense}")


# ---------------------------------------------------------------------------------------------
# reproducer 1: a level does not survive an outage of the channel
# ---------------------------------------------------------------------------------------------


def test_a_presence_level_does_not_survive_an_outage_of_the_channel() -> None:
    mon = make_monitor()
    mon.push_sample(smp("presence", hhmm(7, 0), 1.0))
    mon.push_availability(SignalId.PRESENCE, False, hhmm(7, 10), hhmm(7, 10))
    mon.push_availability(SignalId.PRESENCE, True, hhmm(20, 55), hhmm(20, 55))
    mon.push_event(evt("dispense", hhmm(21, 0)))
    rec = int_record(mon.advance(hhmm(21, 0)), hhmm(21, 0))
    assert rec.state.value == "pending"
    # lo: the last determined witness is the sample of 07:00, held until the channel went down at 07:10
    assert rec.sigma_interval.lo == INT_WINDOW - (21 * 60 - (7 * 60 + 9)) * STEP
    assert (
        rec.sigma_interval.hi == INT_WINDOW
    )  # an undefined level at the dispense step may be 1
    assert rec.undecidable == "undecidable: value_undefined:presence"


def test_the_oracle_agrees_that_the_level_is_gone() -> None:
    scn = Scenario(
        presence=((hhmm(7, 0), 1.0),),
        unavailable_presence=((7 * 60 + 10, 20 * 60 + 54),),
        dispenses=(hhmm(21, 0),),
    )
    rec = int_record(against_oracle(scn, 21 * 60), hhmm(21, 0))
    assert rec.state.value == "pending"


def test_a_new_sample_after_the_return_is_a_witness_of_the_new_episode() -> None:
    mon = make_monitor()
    mon.push_sample(smp("presence", hhmm(7, 0), 1.0))
    mon.push_availability(SignalId.PRESENCE, False, hhmm(7, 10), hhmm(7, 10))
    mon.push_availability(SignalId.PRESENCE, True, hhmm(20, 55), hhmm(20, 55))
    mon.push_sample(smp("presence", hhmm(20, 58), 1.0))
    mon.push_event(evt("dispense", hhmm(21, 0)))
    rec = int_record(mon.advance(hhmm(21, 0)), hhmm(21, 0))
    assert rec.state.value == "satisfied"
    assert rec.sigma_interval.lo == INT_WINDOW


def test_a_zero_after_the_return_ends_the_uncertainty_as_an_absent_witness() -> None:
    mon = make_monitor()
    mon.push_sample(smp("presence", hhmm(7, 0), 1.0))
    mon.push_availability(SignalId.PRESENCE, False, hhmm(7, 10), hhmm(7, 10))
    mon.push_availability(SignalId.PRESENCE, True, hhmm(20, 40), hhmm(20, 40))
    mon.push_sample(smp("presence", hhmm(20, 41), 0.0))
    mon.push_event(evt("dispense", hhmm(21, 0)))
    rec = int_record(mon.advance(hhmm(21, 0)), hhmm(21, 0))
    # the last possible witness is the undefined step 20:40 (the level was cleared, then 0 at 20:41): 20
    # minutes old, graded by age and not a missing witness (the window is 5 minutes)
    assert rec.state.value == "violated" and rec.guard_failed is None
    assert rec.sigma_interval.hi == INT_WINDOW - 20 * STEP
    assert rec.undecidable is None


def test_a_sample_taken_during_an_outage_is_not_held_after_the_return() -> None:
    mon = make_monitor()
    mon.push_availability(SignalId.PRESENCE, False, hhmm(7, 10), hhmm(7, 10))
    mon.push_sample(
        smp("presence", hhmm(8, 0), 1.0)
    )  # the channel is down: not an observation
    mon.push_availability(SignalId.PRESENCE, True, hhmm(20, 55), hhmm(20, 55))
    mon.push_event(evt("dispense", hhmm(21, 0)))
    rec = int_record(mon.advance(hhmm(21, 0)), hhmm(21, 0))
    assert rec.state.value == "pending"
    assert rec.undecidable == "undecidable: value_undefined:presence"


def test_a_level_sampled_after_an_earlier_outage_counts() -> None:
    """The outage ended before the sample: the level belongs to the current episode and is held."""
    mon = make_monitor()
    mon.push_availability(SignalId.PRESENCE, False, hhmm(7, 10), hhmm(7, 10))
    mon.push_availability(SignalId.PRESENCE, True, hhmm(7, 20), hhmm(7, 20))
    mon.push_sample(smp("presence", hhmm(20, 58), 1.0))
    mon.push_event(evt("dispense", hhmm(21, 0)))
    rec = int_record(mon.advance(hhmm(21, 0)), hhmm(21, 0))
    assert rec.state.value == "satisfied"


def test_an_outage_of_the_intake_channel_does_not_touch_the_presence_level() -> None:
    mon = make_monitor()
    mon.push_sample(smp("presence", hhmm(20, 58), 1.0))
    mon.push_availability(SignalId.INTAKE, False, hhmm(7, 10), hhmm(7, 10))
    mon.push_event(evt("dispense", hhmm(21, 0)))
    rec = int_record(mon.advance(hhmm(21, 0)), hhmm(21, 0))
    assert rec.state.value == "satisfied"


# ---------------------------------------------------------------------------------------------
# reproducer 2: no marks and no zeros (the trace of the benchmark generator). The pinned hazard test of
# this place was replaced by WS05-T11 (ADR-054 (b)): see tests/monitor/test_availability_reports.py,
# ``test_departure_report_ends_the_witness`` (the same dispense with the reports is not witnessed) and
# ``test_gate_stays_positive_on_a_day_without_reports`` (a trace without reports keeps the hazard and the gate
# reports it).
# ---------------------------------------------------------------------------------------------


def test_the_stale_level_counter_is_zero_when_the_robot_keeps_sampling() -> None:
    inputs = Inputs()
    for minute in range(0, 4 * 60, 3):
        inputs.samples.append(smp("presence", hhmm(7, 0) + minute * 60_000, 1.0))
    mon = make_monitor()
    drive(mon, inputs, 7 * 60 + 4 * 60)
    assert mon.stats().presence_level_older_than_window_steps == 0


def test_the_stale_level_counter_ignores_a_zero_level_and_an_unavailable_channel() -> (
    None
):
    mon = make_monitor()
    mon.push_sample(smp("presence", hhmm(7, 0), 0.0))
    mon.advance(hhmm(12, 0))
    assert mon.stats().presence_level_older_than_window_steps == 0
    mon2 = make_monitor()
    mon2.push_sample(smp("presence", hhmm(7, 0), 1.0))
    mon2.push_availability(SignalId.PRESENCE, False, hhmm(7, 30), hhmm(7, 30))
    mon2.advance(hhmm(12, 0))
    # steps 07:06 to 07:29 hold an old level (counted), from 07:30 the channel is down and the level gone
    assert mon2.stats().presence_level_older_than_window_steps == 24


# ---------------------------------------------------------------------------------------------
# the monitor against the oracle on traces built around outages of the presence channel
# ---------------------------------------------------------------------------------------------


@settings(
    max_examples=60,
    deadline=None,
    derandomize=True,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    st.lists(
        st.tuples(st.integers(0, 45), st.sampled_from([0.0, 1.0, 0.5])),
        max_size=5,
        unique_by=lambda x: x[0],
    ),
    st.lists(
        st.tuples(st.integers(0, 45), st.integers(0, 12)),
        max_size=3,
    ),
    st.lists(st.integers(0, 55), min_size=1, max_size=3, unique=True),
    st.lists(st.integers(0, 55), max_size=2, unique=True),
)
def test_the_monitor_agrees_with_the_oracle_around_presence_outages(
    samples: list[tuple[int, float]],
    outages: list[tuple[int, int]],
    dispenses: list[int],
    intakes: list[int],
) -> None:
    ranges: list[tuple[int, int]] = []
    for a, length in sorted(outages):
        if not ranges or a > ranges[-1][1] + 1:
            ranges.append((a, a + length))
    scn = Scenario(
        presence=tuple((minute * 60_000, v) for minute, v in sorted(samples)),
        unavailable_presence=tuple(ranges),
        dispenses=tuple(sorted(d * 60_000 for d in dispenses)),
        intakes=tuple(sorted(i * 60_000 for i in intakes)),
    )
    against_oracle(scn, 65)


# ---------------------------------------------------------------------------------------------
# the point evaluator takes presence as the caller builds it (baselines B3 and B5)
# ---------------------------------------------------------------------------------------------


def point_value(inputs: Inputs, t_dispense: int) -> Any:
    from ralmon.spec import TemplateId, TemplateInstance

    from .helpers import load_f0, load_lib, step_values

    reg = load_f0()
    template = next(t for t in load_lib(reg) if t.id is TemplateId.INT)
    instance = TemplateInstance(TemplateId.INT, f"int@{t_dispense}", {}, t_dispense)
    ev = make_point_evaluator(template, instance, reg, STEP)
    value = None
    for k, row in enumerate(step_values(inputs, t_dispense // STEP)):
        value = ev.step(k * STEP, row)
    return value


def test_the_point_evaluator_agrees_with_the_monitor_when_the_level_is_built_per_episode() -> (
    None
):
    inputs = Inputs()
    inputs.samples.append(smp("presence", hhmm(7, 0), 1.0))
    inputs.events.append(evt("dispense", hhmm(21, 0)))
    inputs.avail.append(("presence", False, hhmm(7, 10), hhmm(7, 10)))
    inputs.avail.append(("presence", True, hhmm(20, 55), hhmm(20, 55)))
    assert (
        point_value(inputs, hhmm(21, 0)) is None
    )  # undecided, like the PENDING record
    inputs.samples.append(smp("presence", hhmm(20, 58), 1.0))
    assert point_value(inputs, hhmm(21, 0)) == INT_WINDOW


def test_the_point_evaluator_shares_the_documented_hazard_of_a_trace_without_marks() -> (
    None
):
    inputs = Inputs()
    inputs.samples.append(smp("presence", hhmm(7, 0), 1.0))
    inputs.events.append(evt("dispense", hhmm(21, 0)))
    assert point_value(inputs, hhmm(21, 0)) == INT_WINDOW


# ---------------------------------------------------------------------------------------------
# the gate: presence samples were accepted and no availability mark for presence ever arrived
# ---------------------------------------------------------------------------------------------


def test_presence_samples_without_any_availability_mark_are_counted() -> None:
    mon = make_monitor()
    for minute in (0, 10, 20):
        mon.push_sample(smp("presence", hhmm(7, minute), 1.0))
    mon.advance(hhmm(8, 0))
    assert mon.stats().presence_samples_without_availability_marks == 3


def test_a_presence_mark_clears_the_gate_whenever_it_arrives() -> None:
    mon = make_monitor()
    mon.push_sample(smp("presence", hhmm(7, 0), 1.0))
    mon.push_sample(smp("presence", hhmm(7, 10), 1.0))
    mon.advance(hhmm(7, 30))
    assert mon.stats().presence_samples_without_availability_marks == 2
    mon.push_availability(
        SignalId.PRESENCE, True, hhmm(7, 40), hhmm(7, 40)
    )  # a mark, of any value
    mon.advance(hhmm(8, 0))
    assert mon.stats().presence_samples_without_availability_marks == 0
    mon.push_sample(smp("presence", hhmm(8, 10), 1.0))
    mon.advance(hhmm(9, 0))
    assert mon.stats().presence_samples_without_availability_marks == 0


def test_an_intake_mark_does_not_clear_the_presence_gate() -> None:
    mon = make_monitor()
    mon.push_sample(smp("presence", hhmm(7, 0), 1.0))
    mon.push_availability(SignalId.INTAKE, False, hhmm(7, 5), hhmm(7, 5))
    mon.advance(hhmm(8, 0))
    assert mon.stats().presence_samples_without_availability_marks == 1


def test_a_run_without_presence_samples_passes_the_gate() -> None:
    mon = make_monitor()
    mon.push_event(evt("dispense", hhmm(7, 0)))
    mon.advance(hhmm(8, 0))
    assert mon.stats().presence_samples_without_availability_marks == 0


def test_the_gate_counts_samples_that_were_used_not_the_ones_refused_as_late() -> None:
    mon = make_monitor(d_ms=STEP)
    mon.push_sample(smp("presence", hhmm(7, 0), 1.0, rx=hhmm(7, 0) + 5 * STEP))  # late
    mon.advance(hhmm(8, 0))
    assert mon.stats().late_count == 1
    assert mon.stats().presence_samples_without_availability_marks == 0


def test_the_older_counter_is_information_a_long_visit_alone_makes_it_positive() -> (
    None
):
    """With marks present and a visit longer than int_window the level is older than the window while the
    robot is co-located (the generator's dwell is 10 minutes, int_window 5): not a stale witness."""
    mon = make_monitor()
    mon.push_availability(SignalId.PRESENCE, True, hhmm(7, 0), hhmm(7, 0))
    mon.push_sample(smp("presence", hhmm(7, 0), 1.0))
    mon.push_availability(SignalId.PRESENCE, False, hhmm(7, 10), hhmm(7, 10))
    mon.advance(hhmm(8, 0))
    stats = mon.stats()
    assert stats.presence_samples_without_availability_marks == 0
    assert stats.presence_level_older_than_window_steps == 4  # steps 07:06 to 07:09


def test_known_divergence_with_the_extractor_of_evidence_channels() -> None:
    """ADR-054, consequences: the extractor holds the level across the outage and reads
    `witness.robot_present` False here (so EX-9 invariant I2 expects VIOLATED); the monitor, which clears
    the level of an earlier episode, says PENDING with `value_undefined:presence` (invariant I4 then fails
    for the pair). Pinned so that closing the divergence is a visible decision."""
    mon = make_monitor()
    mon.push_sample(smp("presence", hhmm(6, 0), 0.0))
    mon.push_availability(SignalId.PRESENCE, False, hhmm(6, 10), hhmm(6, 10))
    mon.push_availability(SignalId.PRESENCE, True, hhmm(20, 50), hhmm(20, 50))
    mon.push_event(evt("dispense", hhmm(21, 0)))
    rec = int_record(mon.advance(hhmm(21, 0)), hhmm(21, 0))
    assert rec.state.value == "pending"
    assert rec.undecidable == "undecidable: value_undefined:presence"
