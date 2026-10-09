"""Gaps closed in fix round 1 (WS05-T04): counters, mutation gaps and pinned behaviours.

M5 anchors without a plan and the error hierarchy of ``load``; M6 four mutation gaps (a pressure below
the lower bound in a response window, the order of the floating-point operations of docs/formal/05
section 2.6 (b), the divisibility of the day by the step, the keys of a replaced plan); M9 two SCHED
instances with one anchor; M10 the eviction of dedup keys.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import ralmon.monitor as m
from ralmon.spec import PlanIntegrityError, TemplateId, TemplateInstance

from .helpers import (
    BP_LOWER,
    K_DAY,
    STEP,
    T_DAY,
    Inputs,
    by_key,
    drive,
    evt,
    final,
    hhmm,
    load_f0,
    load_lib,
    make_config,
    make_monitor,
    make_plan,
    registry_variant,
    smp,
)
from .scenarios import Meas, Scenario
from .test_boundaries import against_oracle

REG = load_f0()
LIB = load_lib(REG)

# ---------------------------------------------------------------------------------------------
# M5: anchors that arrive before any plan, and the hierarchy of the errors of load
# ---------------------------------------------------------------------------------------------


def test_dynamic_anchors_before_the_first_plan_are_counted_not_lost_silently() -> None:
    mon = m.StreamingMonitor(make_config(REG), REG, LIB)
    mon.push_event(evt("measurement", STEP))
    mon.push_event(evt("dispense", 2 * STEP))
    mon.push_event(evt("intake", 2 * STEP))  # not an anchor
    assert mon.advance(3 * STEP) == ()
    assert mon.stats().anchors_without_plan == 2
    mon.load(make_plan(REG))
    mon.push_event(evt("measurement", 5 * STEP))
    assert mon.advance(5 * STEP)
    assert mon.stats().anchors_without_plan == 2  # unchanged: the plan is loaded now


def test_a_plan_the_monitor_cannot_run_is_not_a_plan_integrity_or_version_error() -> (
    None
):
    """The node of WS05-T09 must catch PlanFeasibilityError (a MonitorConfigError) as well."""
    assert issubclass(m.PlanFeasibilityError, m.MonitorConfigError)
    assert not issubclass(
        m.PlanFeasibilityError, (PlanIntegrityError, m.PlanVersionError)
    )
    mon = make_monitor()
    mon.advance(5 * STEP)
    with pytest.raises(m.PlanFeasibilityError):
        mon.load(make_plan(REG, sched=[5 * STEP]))
    with pytest.raises(PlanIntegrityError):
        mon.load(make_plan(REG, signature="00" * 32))  # signed, no verifier configured
    with pytest.raises(m.PlanVersionError):
        mon.load(make_plan(REG, plan_version=0))


# ---------------------------------------------------------------------------------------------
# M6 (a): a pressure below the lower bound of the registry in the window of a response
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("bp", [40.0, 30.5, 260.0])
def test_a_response_measured_outside_the_registry_bounds_widens_the_upper_end(
    bp: float,
) -> None:
    """Docs/formal/05 section 2.5: outside (H-dom) the measured margin can exceed the bound term."""
    delta1 = int(REG.get("delta1").value)
    t_dose = hhmm(0, 10)
    scn = Scenario(
        standalone_bp=((hhmm(0, 5), 70.0),),
        dispenses=(t_dose,),
        meas=(Meas(t_dose + delta1, bp),),
    )
    records = against_oracle(scn, 200)
    rec = next(
        r for r in by_key(records)[f"resp@{t_dose}"] if r.t_eval_ms == t_dose + delta1
    )
    margin = (70.0 - bp) - 10.0
    assert rec.sigma_interval.lo == margin
    assert rec.sigma_interval.hi == max(margin, (70.0 - BP_LOWER) - 10.0)


# ---------------------------------------------------------------------------------------------
# M6 (b): the order of the floating-point operations (docs/formal/05 section 2.6 (b))
# ---------------------------------------------------------------------------------------------


def test_the_response_margin_is_computed_in_the_order_of_the_template(
    tmp_path: Path,
) -> None:
    pre, bound, threshold = 68.82600838793651, 47.5, 5.56
    assert (pre - bound) - threshold != pre - (
        bound + threshold
    )  # the order matters here
    reg = registry_variant(
        tmp_path, values={"bound_bp_lower": bound, "delta_resp": threshold}
    )
    delta1 = int(reg.get("delta1").value)
    t_dose = hhmm(0, 10)
    inputs = Inputs()
    inputs.samples.append(smp("bp", hhmm(0, 5), pre))
    inputs.events.append(evt("dispense", t_dose, source="dispenser"))
    inputs.events.append(evt("measurement", t_dose + delta1, source="cuff"))
    inputs.samples.append(smp("bp", t_dose + delta1, bound))
    mon = make_monitor(reg)
    records = drive(mon, inputs, 200)
    resp = by_key(records)[f"resp@{t_dose}"]
    expected = (pre - bound) - threshold
    assert resp[0].sigma_interval.hi == expected  # the bound term at the anchor step
    at_measurement = next(r for r in resp if r.t_eval_ms == t_dose + delta1)
    assert (
        at_measurement.sigma_interval.lo == at_measurement.sigma_interval.hi == expected
    )


# ---------------------------------------------------------------------------------------------
# M6 (c): the day is a whole number of steps (CG-12)
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("step", [7, 70_000, 86_399_999, 100_000_000])
def test_a_step_that_does_not_divide_the_day_is_refused_everywhere(step: int) -> None:
    from dataclasses import replace

    from ralmon.monitor.config import check_config

    with pytest.raises(m.MonitorConfigError, match="divide|step_ms"):
        check_config(replace(make_config(REG), step_ms=step))
    if step >= 86_400_000:
        return  # above the day: the range check answers first
    instance = TemplateInstance(TemplateId.RANGE, "range@0", {}, 0)
    template = next(t for t in LIB if t.id is TemplateId.RANGE)
    with pytest.raises(m.MonitorConfigError, match="must divide the day"):
        m.make_point_evaluator(template, instance, _NoStepRegistry(REG), step)


class _NoStepRegistry:
    """The F0 registry without a ``step_ms`` attribute, so that only the evaluator checks the step."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def get(self, name: str) -> Any:
        return self._inner.get(name)

    def bounds(self, signal: str) -> Any:
        return self._inner.bounds(signal)

    def version(self) -> str:
        return self._inner.version()

    def overrides(self) -> Any:
        return self._inner.overrides()


@pytest.mark.parametrize("step", [1_000, 60_000, 1_200_000, T_DAY])
def test_a_step_that_divides_the_day_is_accepted_by_the_config_check(step: int) -> None:
    from dataclasses import replace

    from ralmon.monitor.config import check_config

    assert check_config(replace(make_config(REG), step_ms=step)).step_ms == step


# ---------------------------------------------------------------------------------------------
# M6 (d): what a replaced plan keeps and drops
# ---------------------------------------------------------------------------------------------


def sched(key: str, anchor: int) -> TemplateInstance:
    return TemplateInstance(TemplateId.SCHED, key, {}, anchor)


def test_a_started_key_is_not_restarted_by_a_new_version_of_the_same_plan() -> None:
    mon = make_monitor(plan=make_plan(REG, records=[sched("shared", hhmm(9, 0))]))
    drive(mon, Inputs(), 9 * 60 + 10)  # the instance runs
    mon.load(
        make_plan(
            REG,
            records=[sched("shared", hhmm(12, 0)), sched("new", hhmm(13, 0))],
            plan_version=2,
        )
    )
    records = drive(mon, Inputs(), 14 * 60, first_step=9 * 60 + 11)
    keys = by_key(records)
    # the first "shared" is still being refined; the new anchor (12:00, deadline 12:30) did not start
    assert {r.pending_until_ms for r in keys["shared"]} == {hhmm(9, 30)}
    assert keys["new"][0].t_eval_ms == hhmm(13, 0)


def test_another_plan_may_reuse_a_key_that_the_first_plan_started() -> None:
    mon = make_monitor(plan=make_plan(REG, records=[sched("shared", hhmm(9, 0))]))
    drive(mon, Inputs(), 9 * 60 + 10)
    mon.load(
        make_plan(REG, records=[sched("shared", hhmm(12, 0))], care_plan_id="plan-2")
    )
    records = drive(mon, Inputs(), 13 * 60, first_step=9 * 60 + 11)
    restarted = [
        r for r in by_key(records)["shared"] if r.pending_until_ms == hhmm(12, 30)
    ]
    assert restarted and restarted[0].t_eval_ms == hhmm(12, 0)


def test_the_static_keys_of_a_replaced_plan_do_not_rename_a_dynamic_instance() -> None:
    mon = m.StreamingMonitor(make_config(REG), REG, LIB)
    mon.load(
        make_plan(REG, day_end=[T_DAY])
    )  # static key count@86400000, never activated
    mon.load(make_plan(REG, care_plan_id="plan-2"))  # another plan, without it
    mon.push_event(evt("dispense", T_DAY))
    keys = {r.instance_key for r in mon.advance(T_DAY) if r.template.value == "count"}
    assert keys == {f"count@{T_DAY}"}  # not count@86400000#2


# ---------------------------------------------------------------------------------------------
# M9: two SCHED instances with one anchor
# ---------------------------------------------------------------------------------------------


def test_two_sched_instances_with_one_anchor_take_each_other_as_the_next_tick() -> None:
    """Documented, not wanted: the earlier of two equal anchors gets no refinement after its window."""
    first, second = sched("first", hhmm(9, 0)), sched("second", hhmm(9, 0))
    mon = make_monitor(plan=make_plan(REG, records=[first, second]))
    keys = by_key(drive(mon, Inputs(), K_DAY))
    window = int(REG.get("sched_window").value) // STEP
    k_a = hhmm(9, 0) // STEP
    assert len(keys["first"]) == window + 1  # stops at its decision step
    assert (
        len(keys["second"]) == K_DAY - k_a + 1
    )  # refined to the closing step of the day
    assert final(keys["first"], "first").state == final(keys["second"], "second").state


# ---------------------------------------------------------------------------------------------
# M10: dedup keys evicted at capacity
# ---------------------------------------------------------------------------------------------


def test_the_eviction_of_dedup_keys_is_counted(monkeypatch: pytest.MonkeyPatch) -> None:
    from ralmon.monitor import core

    monkeypatch.setattr(core, "DEDUP_CAPACITY", 3)
    mon = make_monitor()
    for i in range(5):
        mon.push_sample(smp("bp", i * STEP, 120.0, seq=i))
    stats = mon.stats()
    assert stats.retained_dedup_keys == 3
    assert stats.dedup_evicted_count == 2
    # an evicted key can no longer be recognised: the replay of sequence 0 is accepted again
    mon.push_sample(smp("bp", 0, 120.0, seq=0))
    assert mon.stats().duplicate_count == 0 and mon.stats().accepted_count == 6


# ---------------------------------------------------------------------------------------------
# found while reproducing B1 with the benchmark generator: it writes a `day_end` Sample per day
# ---------------------------------------------------------------------------------------------


def test_a_day_end_sample_of_the_generator_is_ignored_and_counted() -> None:
    """`day_end` is the monitor's own calendar impulse (docs/formal/01 section 2.2); WS04-T06 test 8
    puts one in every generated day, and a refusal would abort `run_offline` on that day."""
    mon = make_monitor()
    mon.push_sample(smp("day_end", T_DAY, 1.0))
    mon.advance(0)
    assert mon.stats().ignored_samples == 1 and mon.stats().accepted_count == 0


def test_a_malformed_day_end_sample_is_still_a_named_error() -> None:
    mon = make_monitor()
    with pytest.raises(m.MonitorInputError):
        mon.push_sample(smp("day_end", -1, 1.0))
    with pytest.raises(m.MonitorInputError):
        mon.push_sample(smp("day_end", 5, float("nan")))


def test_a_day_with_the_generators_day_end_sample_runs_offline() -> None:
    from .helpers import LocalDay

    day = LocalDay(
        [smp("bp", STEP, 120.0), smp("day_end", T_DAY, 1.0)],
        [evt("measurement", STEP, source="cuff")],
    )
    result = m.run_offline_detailed(
        day, make_plan(REG), make_config(REG), None, None, registry=REG, templates=LIB
    )
    assert result.stats.ignored_samples == 1
    assert any(r.instance_key == f"range@{STEP}" for r in result.records)


# ---------------------------------------------------------------------------------------------
# the diagnostic of a stale presence level follows the int_window of the loaded plan
# ---------------------------------------------------------------------------------------------


def test_the_stale_level_counter_uses_the_int_window_of_the_plan(
    tmp_path: Path,
) -> None:
    from .helpers import override_row

    reg = registry_variant(
        tmp_path, overrides=[override_row("int_window", 0.0, 3_600_000.0)]
    )
    record = TemplateInstance(
        TemplateId.INT, "int-params", {"int_window": 900_000.0}, None
    )
    counts = {}
    for label, plan in (
        ("default", make_plan(reg)),
        ("longer window", make_plan(reg, records=[record])),
    ):
        mon = make_monitor(reg, plan=plan)
        mon.push_sample(smp("presence", hhmm(7, 0), 1.0))
        mon.advance(hhmm(8, 0))
        counts[label] = mon.stats().presence_level_older_than_window_steps
    # steps 07:00 .. 08:00: the level is older than 5 steps from step 6, than 15 steps from step 16
    assert counts == {"default": 61 - 6, "longer window": 61 - 16}


# ---------------------------------------------------------------------------------------------
# what a replaced plan keeps: the started keys of another plan do not leak into a later version
# ---------------------------------------------------------------------------------------------


def test_the_started_keys_of_an_earlier_plan_do_not_block_a_later_one() -> None:
    mon = make_monitor(plan=make_plan(REG, records=[sched("shared", hhmm(9, 0))]))
    drive(mon, Inputs(), 9 * 60 + 10)  # plan-1 starts "shared"
    mon.load(
        make_plan(REG, care_plan_id="plan-2")
    )  # another plan: the started set restarts empty
    mon.load(
        make_plan(
            REG,
            care_plan_id="plan-2",
            plan_version=2,
            records=[sched("shared", hhmm(12, 0))],
        )
    )
    records = drive(mon, Inputs(), 13 * 60, first_step=9 * 60 + 11)
    restarted = [
        r for r in by_key(records)["shared"] if r.pending_until_ms == hhmm(12, 30)
    ]
    assert restarted and restarted[0].t_eval_ms == hhmm(12, 0)
