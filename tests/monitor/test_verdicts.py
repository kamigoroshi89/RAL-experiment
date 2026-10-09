"""Three-valued verdicts of ``StreamingMonitor`` (WS05-T04 tests 3 to 12 and the rules around them).

Fixture registry F0, ``step_ms = 60000``. Times convert as ``t_ms = (60 * hh + mm) * 60000``. Where the
task text and docs/formal/05 differ, the document governs: states repeat at every step (emission rule,
section 6.5), a definitive record never changes state, rho or ``decided_at_ms`` but its interval may
refine (ADR-048 (b)), a closed point-zero instance is SATISFIED (tie rule), a residual ``lo = 0 < hi``
stays PENDING, and early decisions are made as soon as the interval resolves (section 3.3).
"""

from __future__ import annotations

import math
from itertools import pairwise
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

import ralmon.monitor as m
from ralmon.spec import TemplateId

from .helpers import (
    STEP,
    T_DAY,
    Inputs,
    at_step,
    by_key,
    drive,
    evt,
    first_definitive,
    hhmm,
    load_f0,
    load_lib,
    make_monitor,
    mark_unavailable,
    smp,
)
from .scenarios import Scenario, scenarios

INF = math.inf
REG = load_f0()
LIB = load_lib(REG)


def run(
    inputs: Inputs,
    until_ms: int,
    *,
    sched: tuple[int, ...] = (),
    day_end: tuple[int, ...] = (),
    d_ms: int = 0,
    **kwargs: Any,
) -> list[Any]:
    mon = make_monitor(REG, d_ms=d_ms, sched=sched, day_end=day_end, **kwargs)
    return drive(mon, inputs, (until_ms - d_ms) // STEP, d_ms=d_ms)


def measure(
    inputs: Inputs,
    t: int,
    bp: float,
    *,
    health: float = 1.0,
    inflation: float = 45_000.0,
) -> None:
    inputs.events.append(evt("measurement", t, source="cuff"))
    inputs.samples.append(smp("bp", t, bp))
    inputs.samples.append(smp("cuff_health", t, health))
    inputs.samples.append(smp("inflation_ms", t, inflation))


def dose(inputs: Inputs, t: int) -> None:
    inputs.events.append(evt("dispense", t, source="dispenser"))


def pre_dose(inputs: Inputs, bp: float = 150.0, t: int = hhmm(6, 55)) -> None:
    """A pre-dose pressure sample with its measurement event (the pre_i of a RESP instance)."""
    measure(inputs, t, bp)


# ---------------------------------------------------------------------------------------------
# tests 3 and 4: the arithmetic of the worked examples
# ---------------------------------------------------------------------------------------------


def test_range_violation_g_range_2() -> None:
    inputs = Inputs()
    measure(inputs, hhmm(9, 5), 152.0)
    records = run(inputs, hhmm(9, 5))
    rec = at_step(records, f"range@{hhmm(9, 5)}", hhmm(9, 5))
    assert rec.state is m.VerdictState.VIOLATED
    assert (rec.sigma_interval.lo, rec.sigma_interval.hi) == (-12.0, -12.0)
    assert rec.sigma_norm_interval == (-0.6, -0.6)


def test_count_violation_g_count_1() -> None:
    inputs = Inputs()
    for t in (hhmm(7, 0), hhmm(21, 0), hhmm(21, 2)):
        dose(inputs, t)
    records = run(inputs, hhmm(21, 2))
    rec = at_step(records, f"count@{hhmm(21, 2)}", hhmm(21, 2))
    assert rec.state is m.VerdictState.VIOLATED
    assert (rec.sigma_interval.lo, rec.sigma_interval.hi) == (
        -1.0,
        -1.0,
    )  # 2 - 3, not -8
    assert rec.sigma_norm_interval == (-1.0, -1.0)


# ---------------------------------------------------------------------------------------------
# test 5: SCHED pending, then satisfied or violated (decision rules of 05 section 3.3)
# ---------------------------------------------------------------------------------------------

TICK = hhmm(9, 0)
SCHED_KEY = f"sched@{TICK}"


def test_sched_pending_then_satisfied_when_a_measurement_resolves_it() -> None:
    inputs = Inputs()
    inputs.events.append(evt("schedule_tick", TICK, source="care_plan"))
    measure(inputs, hhmm(9, 5), 130.0)
    records = run(inputs, hhmm(9, 31), sched=(TICK,))
    first = at_step(records, SCHED_KEY, TICK)
    assert first.state is m.VerdictState.PENDING
    assert first.pending_until_ms == 34_200_000  # 09:30
    at_five = at_step(records, SCHED_KEY, 32_700_000)
    assert at_five.state is m.VerdictState.SATISFIED
    assert at_five.decided_at_ms == 32_700_000  # early decision of the golden V-SCHED-2
    assert at_five.pending_until_ms == 34_200_000
    # the decided record keeps its state and its decision step
    for r in by_key(records)[SCHED_KEY]:
        if r.t_eval_ms >= 32_700_000:
            assert r.state is m.VerdictState.SATISFIED and r.decided_at_ms == 32_700_000


def test_sched_without_measurement_is_violated_at_the_decision_step() -> None:
    inputs = Inputs()
    inputs.events.append(evt("schedule_tick", TICK, source="care_plan"))
    records = run(inputs, hhmm(9, 31), sched=(TICK,))
    before = at_step(records, SCHED_KEY, 34_140_000)
    assert before.state is m.VerdictState.PENDING
    rec = at_step(records, SCHED_KEY, 34_200_000)
    assert rec.state is m.VerdictState.VIOLATED
    assert rec.decided_at_ms == 34_200_000 and rec.decided_at_ms <= 34_260_000
    assert rec.guard_failed == "no_measurement_after_tick"


# ---------------------------------------------------------------------------------------------
# test 6: RESP pending until the deadline, then violated
# ---------------------------------------------------------------------------------------------


def test_resp_pending_until_deadline_then_violated() -> None:
    inputs = Inputs()
    pre_dose(inputs, 150.0)
    dose(inputs, hhmm(7, 0))
    records = run(inputs, hhmm(10, 1))
    key = f"resp@{hhmm(7, 0)}"
    mine = by_key(records)[key]
    states = [(r.t_eval_ms, r.state) for r in mine]
    assert [t for t, _ in states] == list(range(hhmm(7, 0), hhmm(10, 0) + 1, STEP))
    for t, state in states[:-1]:  # every step from 07:00 to 09:59
        assert state is m.VerdictState.PENDING, t
    assert all(r.pending_until_ms == 36_000_000 for r in mine)
    last = mine[-1]
    assert last.state is m.VerdictState.VIOLATED
    assert last.decided_at_ms == 36_000_000 and last.decided_at_ms <= 36_060_000
    assert last.guard_failed == "obligation_unmet"
    assert last.sigma_interval.lo == -INF and last.sigma_interval.hi == -INF


# ---------------------------------------------------------------------------------------------
# tests 7 and 8: early decisions licensed by the interval (05 section 3.3, Lemma 12)
# ---------------------------------------------------------------------------------------------


def test_resp_satisfied_early_with_physiological_completion() -> None:
    inputs = Inputs()
    pre_dose(inputs, 150.0)
    dose(inputs, hhmm(7, 0))
    measure(inputs, hhmm(8, 30), 132.0)
    records = run(inputs, hhmm(8, 30))
    rec = at_step(records, f"resp@{hhmm(7, 0)}", hhmm(8, 30))
    assert rec.state is m.VerdictState.SATISFIED
    assert rec.decided_at_ms == 30_600_000 and rec.pending_until_ms == 36_000_000
    assert (rec.sigma_interval.lo, rec.sigma_interval.hi) == (8.0, 90.0)
    assert rec.sigma_norm_interval == (0.4, 1.0)  # 90 / 20 clipped


def test_resp_violated_early_when_bounds_cannot_satisfy() -> None:
    inputs = Inputs()
    pre_dose(inputs, 55.0, t=hhmm(6, 45))
    dose(inputs, hhmm(7, 0))
    records = run(inputs, hhmm(7, 5))
    mine = by_key(records)[f"resp@{hhmm(7, 0)}"]
    assert (
        len(mine) == 1
    )  # retired at the deciding step: a definitive instance is not re-evaluated
    rec = mine[0]
    assert rec.t_eval_ms == hhmm(
        7, 0
    )  # the first step that sees the dispense, before the window opens
    assert rec.state is m.VerdictState.VIOLATED and rec.decided_at_ms == hhmm(7, 0)
    assert (rec.sigma_interval.lo, rec.sigma_interval.hi) == (
        -INF,
        -5.0,
    )  # (55 - 50) - 10
    assert rec.sigma_norm_interval == (-1.0, -0.25)
    assert rec.guard_failed is None  # a finite hi from the bounds, not a failed guard
    assert rec.rho is not None and rec.rho.kind is m.RhoKind.MEASURED


def test_resp_margin_exactly_zero_waits_for_the_closed_window() -> None:
    """Section 3.3: a margin of 0 waits for the decision step (tie rule), it is not an early SATISFIED."""
    inputs = Inputs()
    pre_dose(inputs, 150.0)
    dose(inputs, hhmm(7, 0))
    measure(inputs, hhmm(8, 30), 140.0)  # drop 10 = delta_resp
    records = run(inputs, hhmm(10, 0))
    key = f"resp@{hhmm(7, 0)}"
    at_measure = at_step(records, key, hhmm(8, 30))
    assert at_measure.state is m.VerdictState.PENDING
    assert (at_measure.sigma_interval.lo, at_measure.sigma_interval.hi) == (0.0, 90.0)
    closed = at_step(records, key, hhmm(10, 0))
    assert closed.state is m.VerdictState.SATISFIED and closed.decided_at_ms == hhmm(
        10, 0
    )


# ---------------------------------------------------------------------------------------------
# test 9: ties (CP3)
# ---------------------------------------------------------------------------------------------


def test_zero_margin_with_nothing_unknown_is_decided() -> None:
    inputs = Inputs()
    measure(inputs, hhmm(9, 0), 140.0)  # G-RANGE-4, on the upper limit
    dose(inputs, hhmm(7, 0))
    dose(inputs, hhmm(21, 0))  # G-COUNT-2: c_d = 2 = dose_max_24h
    records = run(inputs, hhmm(21, 0))
    rng = at_step(records, f"range@{hhmm(9, 0)}", hhmm(9, 0))
    assert rng.state is m.VerdictState.SATISFIED
    assert (rng.sigma_interval.lo, rng.sigma_interval.hi) == (0.0, 0.0)
    cnt = at_step(records, f"count@{hhmm(21, 0)}", hhmm(21, 0))
    assert cnt.state is m.VerdictState.SATISFIED
    assert (cnt.sigma_interval.lo, cnt.sigma_interval.hi) == (0.0, 0.0)


def test_lo_zero_below_a_positive_hi_stays_pending_even_after_the_deadline() -> None:
    """CP3-b: every completion satisfies but rule 1 does not fire; the residual case is PENDING."""
    inputs = Inputs()
    inputs.samples.append(
        smp("presence", hhmm(20, 55), 1.0)
    )  # exactly int_window before the dose
    dose(inputs, hhmm(21, 0))
    mark_unavailable(inputs, "presence", hhmm(20, 56), hhmm(21, 0))
    records = run(inputs, hhmm(21, 0))
    rec = at_step(records, f"int@{hhmm(21, 0)}", hhmm(21, 0))
    assert (rec.sigma_interval.lo, rec.sigma_interval.hi) == (0.0, 300_000.0)
    assert rec.state is m.VerdictState.PENDING
    assert rec.undecidable == "undecidable: channel_unavailable:presence"


def test_day_end_count_equal_to_the_minimum_waits_for_the_closing_step() -> None:
    inputs = Inputs()
    dose(inputs, hhmm(7, 0))
    dose(inputs, hhmm(21, 0))
    records = run(inputs, T_DAY, day_end=(T_DAY,))
    key = f"count@{T_DAY}"
    at_evening = at_step(records, key, hhmm(21, 0))
    assert at_evening.state is m.VerdictState.PENDING
    assert (at_evening.sigma_interval.lo, at_evening.sigma_interval.hi) == (0.0, INF)
    closing = at_step(records, key, T_DAY)
    assert closing.state is m.VerdictState.SATISFIED and closing.decided_at_ms == T_DAY
    assert (closing.sigma_interval.lo, closing.sigma_interval.hi) == (0.0, 0.0)


# ---------------------------------------------------------------------------------------------
# tests 10 and 11: the emitted states (restated per 05 section 6.5 and ADR-048 (b))
# ---------------------------------------------------------------------------------------------


def is_path_of_allowed_graph(states: list[Any]) -> bool:
    """PENDING* then (at most) one definitive state repeated; PREDICTED_VIOLATION does not occur here."""
    seen_definitive: Any = None
    for s in states:
        if s.value not in ("pending", "violated", "satisfied"):
            return False
        if seen_definitive is not None and s is not seen_definitive:
            return False
        if s.value != "pending" and seen_definitive is None:
            seen_definitive = s
    return True


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(scenarios(), st.integers(10, 330))
def test_verdict_states_follow_allowed_transitions(scn: Scenario, last: int) -> None:
    mon = make_monitor(REG, sched=scn.ticks, day_end=scn.day_end_anchors())
    records = drive(mon, scn.to_inputs(), last)
    for key, recs in by_key(records).items():
        steps = [r.t_eval_ms for r in recs]
        assert steps == sorted(set(steps)), (
            key
        )  # one record per active instance per step
        assert is_path_of_allowed_graph([r.state for r in recs]), key


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(scenarios(), st.integers(10, 330))
def test_definitive_records_are_never_revised(scn: Scenario, last: int) -> None:
    """ADR-048 (b): state, rho, decided_at_ms and the markers never change; the interval may refine."""
    mon = make_monitor(REG, sched=scn.ticks, day_end=scn.day_end_anchors())
    records = drive(mon, scn.to_inputs(), last)
    for key, recs in by_key(records).items():
        first = first_definitive(recs, key)
        if first is None:
            continue
        later = [r for r in recs if r.t_eval_ms > first.t_eval_ms]
        if first.template is not TemplateId.SCHED:
            assert later == [], (
                key
            )  # a definitive instance is retired: no later record exists
        for r in later:
            assert (r.state, r.rho, r.decided_at_ms) == (
                first.state,
                first.rho,
                first.decided_at_ms,
            )
            assert (r.guard_failed, r.subformula_path, r.pending_until_ms) == (
                first.guard_failed,
                first.subformula_path,
                first.pending_until_ms,
            )
        # in the bounded domain the refinement is a nesting (Lemma 4 (a)): lo only up, hi only down
        for a, b in pairwise(recs):
            assert b.sigma_interval.lo >= a.sigma_interval.lo, key
            assert b.sigma_interval.hi <= a.sigma_interval.hi, key


def test_sched_refinement_records_change_the_upper_end_every_step_without_changing_the_state() -> (
    None
):
    inputs = Inputs()
    records = run(inputs, hhmm(9, 40), sched=(TICK,))
    mine = by_key(records)[SCHED_KEY]
    at_deadline = at_step(records, SCHED_KEY, 34_200_000)
    at_ten_later = at_step(records, SCHED_KEY, 34_800_000)
    assert (
        at_deadline.sigma_interval.hi == -60_000.0
        and at_ten_later.sigma_interval.hi == -660_000.0
    )
    assert at_deadline.sigma_norm_interval[1] == pytest.approx(-0.03333333333333333)
    assert at_ten_later.state is m.VerdictState.VIOLATED
    assert at_ten_later.decided_at_ms == 34_200_000
    assert [r.t_eval_ms for r in mine] == list(range(TICK, hhmm(9, 40) + 1, STEP))


def test_sched_graded_by_a_late_measurement_then_the_instance_retires_at_the_horizon() -> (
    None
):
    """V-SCHED-5b, and the horizon H = max(k_d, min(k_next, K)) of 05 section 2.3."""
    inputs = Inputs()
    measure(inputs, hhmm(9, 51), 130.0)
    next_tick = hhmm(10, 0)
    records = run(inputs, hhmm(10, 5), sched=(TICK, next_tick))
    rec = at_step(records, SCHED_KEY, hhmm(9, 51))
    assert (rec.sigma_interval.lo, rec.sigma_interval.hi) == (
        -1_260_000.0,
        -1_260_000.0,
    )
    assert rec.sigma_norm_interval == (-0.7, -0.7)
    mine = by_key(records)[SCHED_KEY]
    assert (
        mine[-1].t_eval_ms == next_tick
    )  # H = k_next: the instance is retired at the next tick
    second = by_key(records)[f"sched@{next_tick}"]
    assert second[0].t_eval_ms == next_tick


def test_sched_with_a_close_next_tick_has_no_refinement_and_hi_minus_infinity() -> None:
    inputs = Inputs()
    records = run(inputs, hhmm(9, 40), sched=(TICK, hhmm(9, 10)))
    mine = by_key(records)[SCHED_KEY]
    assert (
        mine[-1].t_eval_ms == 34_200_000
    )  # H = k_d because the next tick is visible before the deadline
    assert mine[-1].state is m.VerdictState.VIOLATED
    assert (mine[-1].sigma_interval.lo, mine[-1].sigma_interval.hi) == (-INF, -INF)
    assert mine[-1].sigma_norm_interval == (-1.0, -1.0)


# ---------------------------------------------------------------------------------------------
# test 12: the measured verdicts ignore the forecaster
# ---------------------------------------------------------------------------------------------


class ExplodingForecaster:
    name = "exploding"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def fit(self, train_days: Any) -> None:
        self.calls.append("fit")
        raise AssertionError("fit must not be called")

    def predict(self, history: Any, t_ms: int, horizon_ms: int) -> Any:
        self.calls.append("predict")
        raise AssertionError("predict must not be called")


def test_measured_verdicts_ignore_forecaster() -> None:
    forecaster = ExplodingForecaster()
    inputs = Inputs()
    inputs.events.append(evt("schedule_tick", TICK, source="care_plan"))
    records = run(inputs, hhmm(9, 31), sched=(TICK,), forecaster=forecaster)
    assert forecaster.calls == []
    with_none = run(inputs, hhmm(9, 31), sched=(TICK,))
    assert records == with_none  # the forecaster changes nothing (Lemma 9)


# ---------------------------------------------------------------------------------------------
# stale-open positions: markers of 05 section 3.5, never VIOLATED and never SATISFIED
# ---------------------------------------------------------------------------------------------


def only_record(records: list[Any], key: str) -> Any:
    found = by_key(records)[key]
    return found[-1]


def test_marker_range_without_a_pressure_sample_is_the_hull() -> None:
    inputs = Inputs()
    inputs.events.append(evt("measurement", hhmm(9, 0), source="cuff"))
    rec = only_record(run(inputs, hhmm(9, 0)), f"range@{hhmm(9, 0)}")
    assert (rec.sigma_interval.lo, rec.sigma_interval.hi) == (
        -110.0,
        90.0,
    )  # not the exact range
    assert rec.state is m.VerdictState.PENDING and rec.decided_at_ms is None
    assert rec.undecidable == "undecidable: value_undefined:bp"


def test_marker_range_uses_an_older_sample_when_the_new_one_is_lost() -> None:
    inputs = Inputs()
    measure(inputs, hhmm(8, 0), 125.0)
    inputs.events.append(
        evt("measurement", hhmm(9, 0), source="cuff")
    )  # its own sample is lost
    rec = only_record(run(inputs, hhmm(9, 0)), f"range@{hhmm(9, 0)}")
    assert rec.state is m.VerdictState.SATISFIED
    assert (rec.sigma_interval.lo, rec.sigma_interval.hi) == (15.0, 15.0)
    assert rec.undecidable is None


def test_marker_hold_open_pressure() -> None:
    inputs = Inputs()
    inputs.events.append(
        evt("measurement", hhmm(6, 50), source="cuff")
    )  # no bp sample at all
    dose(inputs, hhmm(7, 0))
    rec = only_record(run(inputs, hhmm(7, 0)), f"hold@{hhmm(7, 0)}")
    assert (rec.sigma_interval.lo, rec.sigma_interval.hi) == (-50.0, 150.0)
    assert rec.state is m.VerdictState.PENDING
    assert rec.undecidable == "undecidable: value_undefined:bp"


def test_hold_guard_failed_without_a_recent_measurement() -> None:
    inputs = Inputs()
    measure(inputs, hhmm(5, 30), 120.0)  # G-HOLD-4: 90 minutes before the dose
    dose(inputs, hhmm(7, 0))
    rec = only_record(run(inputs, hhmm(7, 0)), f"hold@{hhmm(7, 0)}")
    assert rec.state is m.VerdictState.VIOLATED
    assert (rec.sigma_interval.lo, rec.sigma_interval.hi) == (-INF, -INF)
    assert rec.sigma_norm_interval == (-1.0, -1.0)
    assert rec.guard_failed == "no_recent_measurement"
    assert (
        rec.rho is not None
        and rec.rho.kind is m.RhoKind.DETERMINISTIC
        and rec.rho.value == 1.0
    )


def test_hold_refined_form_uses_the_latest_pressure() -> None:
    """G-HOLD-3: an old high reading does not mask a recent low one."""
    inputs = Inputs()
    measure(inputs, hhmm(6, 15), 120.0)
    measure(inputs, hhmm(6, 55), 90.0)
    dose(inputs, hhmm(7, 0))
    rec = only_record(run(inputs, hhmm(7, 0)), f"hold@{hhmm(7, 0)}")
    assert rec.state is m.VerdictState.VIOLATED
    assert (rec.sigma_interval.lo, rec.sigma_interval.hi) == (-10.0, -10.0)


def test_marker_sys_open_cuff_health() -> None:
    inputs = Inputs()
    inputs.events.append(evt("measurement", hhmm(9, 0), source="cuff"))
    inputs.samples.append(
        smp("inflation_ms", hhmm(9, 0), 45_000.0)
    )  # the health sample is lost
    rec = only_record(run(inputs, hhmm(9, 0)), f"sys@{hhmm(9, 0)}")
    assert (rec.sigma_interval.lo, rec.sigma_interval.hi) == (-INF, 15_000.0)
    assert rec.state is m.VerdictState.PENDING
    assert rec.undecidable == "undecidable: value_undefined:cuff_health"


def test_marker_sys_open_inflation_and_unhealthy_guard() -> None:
    inputs = Inputs()
    inputs.events.append(evt("measurement", hhmm(9, 0), source="cuff"))
    inputs.samples.append(smp("cuff_health", hhmm(9, 0), 1.0))
    records = run(inputs, hhmm(9, 0))
    rec = only_record(records, f"sys@{hhmm(9, 0)}")
    assert (rec.sigma_interval.lo, rec.sigma_interval.hi) == (-30_000.0, INF)
    assert rec.undecidable == "undecidable: value_undefined:inflation_ms"
    bad = Inputs()
    measure(bad, hhmm(9, 0), 130.0, health=0.0)  # G-SYS-3
    rec2 = only_record(run(bad, hhmm(9, 0)), f"sys@{hhmm(9, 0)}")
    assert (
        rec2.state is m.VerdictState.VIOLATED and rec2.guard_failed == "cuff_unhealthy"
    )
    assert (rec2.sigma_interval.lo, rec2.sigma_interval.hi) == (-INF, -INF)


def test_sys_low_inflation_is_a_margin_not_a_guard() -> None:
    inputs = Inputs()
    measure(inputs, hhmm(9, 0), 130.0, inflation=9_000.0)  # G-SYS-2
    rec = only_record(run(inputs, hhmm(9, 0)), f"sys@{hhmm(9, 0)}")
    assert rec.state is m.VerdictState.VIOLATED and rec.guard_failed is None
    assert (rec.sigma_interval.lo, rec.sigma_interval.hi) == (-21_000.0, -21_000.0)
    assert rec.sigma_norm_interval == (-0.7, -0.7)
    assert rec.rho is not None and rec.rho.kind is m.RhoKind.DETERMINISTIC


def test_marker_resp_without_a_pre_dose_pressure_stays_pending_after_the_deadline() -> (
    None
):
    inputs = Inputs()
    dose(inputs, hhmm(7, 0))  # no pressure sample before the dose
    measure(inputs, hhmm(8, 30), 130.0)
    records = run(inputs, hhmm(10, 0))
    mine = by_key(records)[f"resp@{hhmm(7, 0)}"]
    last = mine[-1]
    assert last.t_eval_ms == hhmm(10, 0) and last.state is m.VerdictState.PENDING
    assert last.undecidable == "undecidable: value_undefined:bp_pre"
    assert (last.sigma_interval.lo, last.sigma_interval.hi) == (-90.0, 110.0)
    assert all(
        r.undecidable is None for r in mine[:-1]
    )  # no marker before the decision step


def test_resp_without_a_pre_dose_pressure_and_without_measurement_is_violated() -> None:
    """Whatever the missing pre-dose pressure is, no measurement in the window violates (05 section 7.3)."""
    inputs = Inputs()
    dose(inputs, hhmm(7, 0))
    rec = only_record(run(inputs, hhmm(10, 0)), f"resp@{hhmm(7, 0)}")
    assert (
        rec.state is m.VerdictState.VIOLATED and rec.guard_failed == "obligation_unmet"
    )
    assert rec.undecidable is None


def test_marker_resp_measurement_without_any_pressure() -> None:
    inputs = Inputs()
    dose(inputs, hhmm(7, 0))
    inputs.events.append(
        evt("measurement", hhmm(8, 30), source="cuff")
    )  # no sample, no earlier sample
    rec = only_record(run(inputs, hhmm(10, 0)), f"resp@{hhmm(7, 0)}")
    assert rec.state is m.VerdictState.PENDING
    assert rec.undecidable == "undecidable: value_undefined:bp_pre,value_undefined:bp"
    assert (rec.sigma_interval.lo, rec.sigma_interval.hi) == (-210.0, 190.0)


def test_marker_int_value_undefined_presence() -> None:
    """The channel is available but never sampled: not an absent witness (V-INT-3 differs by a 0 sample)."""
    inputs = Inputs()
    dose(inputs, hhmm(21, 0))
    rec = only_record(run(inputs, hhmm(21, 0)), f"int@{hhmm(21, 0)}")
    assert rec.state is m.VerdictState.PENDING
    assert (rec.sigma_interval.lo, rec.sigma_interval.hi) == (-INF, 300_000.0)
    assert rec.undecidable == "undecidable: value_undefined:presence"


def test_marker_int_both_robot_channels_unavailable_and_undefined_before() -> None:
    inputs = Inputs()
    dose(inputs, hhmm(21, 0))
    mark_unavailable(inputs, "presence", hhmm(20, 57), hhmm(21, 0))
    mark_unavailable(inputs, "intake", hhmm(20, 59), hhmm(21, 0))
    rec = only_record(run(inputs, hhmm(21, 0)), f"int@{hhmm(21, 0)}")
    assert rec.state is m.VerdictState.PENDING
    assert rec.undecidable == (
        "undecidable: channel_unavailable:presence,channel_unavailable:intake,value_undefined:presence"
    )


def test_int_witness_older_than_the_window_is_graded_negative() -> None:
    """G-INT-2: presence 8 minutes before the dose (age 8 min against int_window 5 min)."""
    inputs = Inputs()
    inputs.samples.append(smp("presence", hhmm(6, 52), 1.0))
    inputs.samples.append(smp("presence", hhmm(6, 53), 0.0))
    dose(inputs, hhmm(7, 0))
    rec = only_record(run(inputs, hhmm(7, 0)), f"int@{hhmm(7, 0)}")
    assert rec.state is m.VerdictState.VIOLATED
    assert (rec.sigma_interval.lo, rec.sigma_interval.hi) == (-180_000.0, -180_000.0)
    assert (
        rec.guard_failed is None
    )  # a witness exists: the margin is negative, the guard did not fail
    assert rec.sigma_norm_interval == (-0.6, -0.6)


def test_int_intake_after_the_dispense_does_not_count() -> None:
    inputs = Inputs()
    inputs.samples.append(smp("presence", 0, 0.0))
    dose(inputs, hhmm(7, 0))
    inputs.events.append(evt("intake", hhmm(7, 1), source="robot"))
    rec = only_record(run(inputs, hhmm(7, 1)), f"int@{hhmm(7, 0)}")
    assert rec.state is m.VerdictState.VIOLATED and rec.guard_failed == "no_witness"


# ---------------------------------------------------------------------------------------------
# counters, multiplicity and the clock of the derived signals (WS05-T02 hand-over)
# ---------------------------------------------------------------------------------------------


def test_two_dispenses_in_one_step_both_count_for_both_instances() -> None:
    """W3: multiplicity is kept; each instance of the step sees c_d = 2 + earlier."""
    inputs = Inputs()
    dose(inputs, hhmm(7, 0))
    dose(inputs, hhmm(20, 59, 59, 500))
    dose(inputs, hhmm(21, 0))
    records = run(inputs, hhmm(21, 0))
    a = only_record(records, f"count@{hhmm(20, 59, 59, 500)}")
    b = only_record(records, f"count@{hhmm(21, 0)}")
    assert (
        a.sigma_interval == b.sigma_interval
    )  # both read the counter of the grid step
    assert (a.sigma_interval.lo, a.sigma_interval.hi) == (-1.0, -1.0)  # 2 - 3


def test_dose_count_window_is_read_at_the_grid_time_not_at_the_dispense_time() -> None:
    """The per-step clock sample ages the window to t_k (01 section 5.1): c_d is the count at the grid step."""
    first = hhmm(7, 0, 30)  # 07:00:30 on day 0
    second = T_DAY + hhmm(7, 0, 10)  # 07:00:10 on day 1, visible at 07:01
    inputs = Inputs()
    dose(inputs, first)
    dose(inputs, second)
    records = run(inputs, T_DAY + hhmm(7, 1))
    rec = only_record(records, f"count@{second}")
    # at t_k = 07:01 on day 1 the window is (07:01 on day 0, 07:01 on day 1]: the first dose left it
    assert (rec.sigma_interval.lo, rec.sigma_interval.hi) == (1.0, 1.0)  # 2 - 1
    assert rec.state is m.VerdictState.SATISFIED


def test_dose_count_window_is_half_open_a_dispense_exactly_24h_old_has_left_it() -> (
    None
):
    """W6: the day-1 07:00 event is excluded at day-2 07:00."""
    inputs = Inputs()
    for t in (hhmm(7, 0), hhmm(21, 0), hhmm(21, 2), T_DAY + hhmm(7, 0)):
        dose(inputs, t)
    records = run(inputs, T_DAY + hhmm(7, 0))
    rec = only_record(records, f"count@{T_DAY + hhmm(7, 0)}")
    assert (rec.sigma_interval.lo, rec.sigma_interval.hi) == (-1.0, -1.0)  # c_d = 3
    assert rec.state is m.VerdictState.VIOLATED


def test_derived_signals_receive_every_released_sample() -> None:
    """An absent counter is 0: a first dispense with no earlier input has c_d = 1."""
    inputs = Inputs()
    dose(inputs, hhmm(7, 0))
    rec = only_record(run(inputs, hhmm(7, 0)), f"count@{hhmm(7, 0)}")
    assert (rec.sigma_interval.lo, rec.sigma_interval.hi) == (1.0, 1.0)


def test_overlapping_doses_each_hold_their_own_pre_dose_value() -> None:
    """A3 of 02-templates 1.5: the per-instance capture, not a global stream."""
    inputs = Inputs()
    measure(inputs, hhmm(6, 55), 150.0)
    dose(inputs, hhmm(7, 0))
    measure(inputs, hhmm(7, 30), 120.0)
    dose(inputs, hhmm(7, 40))
    measure(inputs, hhmm(8, 50), 128.0)
    records = run(inputs, hhmm(8, 50))
    first = at_step(records, f"resp@{hhmm(7, 0)}", hhmm(8, 50))
    second = at_step(records, f"resp@{hhmm(7, 40)}", hhmm(8, 50))
    assert (first.sigma_interval.lo, first.sigma_interval.hi) == (
        12.0,
        90.0,
    )  # 150 - 128 - 10
    assert (second.sigma_interval.lo, second.sigma_interval.hi) == (
        -18.0,
        60.0,
    )  # 120 - 128 - 10, 120 - 50 - 10


def test_a_pressure_with_the_device_time_of_the_dispense_counts_as_pre_dose() -> None:
    """M5: a sample with the same device time as the dispense is the pre-dose value; a later one is not."""
    t_dose = hhmm(7, 0, 10)
    inputs = Inputs()
    dose(inputs, t_dose)
    inputs.samples.append(smp("bp", t_dose, 150.0))
    inputs.samples.append(
        smp("bp", hhmm(7, 0, 40), 99.0)
    )  # after the dose, in the same step
    inputs.events.append(evt("measurement", hhmm(8, 30), source="cuff"))
    inputs.samples.append(smp("bp", hhmm(8, 30), 132.0))
    rec = at_step(run(inputs, hhmm(8, 30)), f"resp@{t_dose}", hhmm(8, 30))
    assert (rec.sigma_interval.lo, rec.sigma_interval.hi) == (
        8.0,
        90.0,
    )  # pre_i = 150, not 99


def test_out_of_domain_pressure_is_used_as_measured_and_counted() -> None:
    inputs = Inputs()
    pre_dose(inputs, 55.0, t=hhmm(6, 45))
    dose(inputs, hhmm(7, 0))
    measure(
        inputs, hhmm(8, 30), 40.0
    )  # outside the bounds: the example of 05 section 2.5
    mon = make_monitor(REG)
    records = drive(mon, inputs, hhmm(8, 30) // STEP)
    mine = by_key(records)[f"resp@{hhmm(7, 0)}"]
    assert (
        len(mine) == 1 and mine[0].state is m.VerdictState.VIOLATED
    )  # not retracted, not re-evaluated
    assert mon.stats().out_of_domain_samples == 1


# ---------------------------------------------------------------------------------------------
# record fields
# ---------------------------------------------------------------------------------------------


def test_pending_until_is_the_grid_decision_time_on_every_record() -> None:
    """CG-3: ``t_{k_up(a)} + B``, also for an anchor between two grid times."""
    anchor = hhmm(9, 0, 20)  # 09:00:20 -> step 541
    inputs = Inputs()
    records = run(inputs, hhmm(9, 5), sched=(anchor,))
    mine = by_key(records)[f"sched@{anchor}"]
    assert mine[0].t_eval_ms == 541 * STEP
    assert all(r.pending_until_ms == 571 * STEP for r in mine)


def test_records_are_returned_in_step_order_then_creation_order() -> None:
    inputs = Inputs()
    measure(inputs, hhmm(9, 0), 125.0)
    records = run(inputs, hhmm(9, 2), sched=(hhmm(9, 0),))
    steps = [r.t_eval_ms for r in records]
    assert steps == sorted(steps)
    at_nine = [r.instance_key for r in records if r.t_eval_ms == hhmm(9, 0)]
    assert at_nine == [
        f"sched@{hhmm(9, 0)}",
        f"range@{hhmm(9, 0)}",
        f"sys@{hhmm(9, 0)}",
    ]


def test_t_eval_is_the_grid_time_of_the_finalised_step_with_a_reorder_delay() -> None:
    inputs = Inputs()
    inputs.events.append(evt("schedule_tick", TICK, source="care_plan"))
    records = run(inputs, 34_230_000, sched=(TICK,), d_ms=30_000)
    assert records[-1].t_eval_ms == 34_200_000  # advance(t_k + D) finalises step k
    assert records[-1].state is m.VerdictState.VIOLATED


def test_normalised_interval_clips_and_maps_infinities() -> None:
    inputs = Inputs()
    measure(inputs, hhmm(9, 0), 200.0)  # G-RANGE-5: -60 mmHg, clipped
    rec = only_record(run(inputs, hhmm(9, 0)), f"range@{hhmm(9, 0)}")
    assert (rec.sigma_interval.lo, rec.sigma_interval.hi) == (-60.0, -60.0)
    assert rec.sigma_norm_interval == (-1.0, -1.0)
