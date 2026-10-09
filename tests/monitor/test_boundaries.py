"""Boundaries and degenerate inputs that the random scenarios do not reach (WS05-T04).

Written after the mutation self-check of the monitor (a throwaway copy of the package with 297
single-line mutants, run against ``tests/monitor``): every test here kills at least one mutant that the
first version of the suite let through. The tests are directed: one boundary, one degenerate registry
or one order of inputs each, compared with the independent oracle (``tests/fixtures/monitor/oracle.py``)
where the oracle covers the quantity and asserted directly where it does not (markers, counters,
errors). Fixture arithmetic only (registry F0, ``step_ms = 60000``).
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

import ralmon.monitor as m
from ralmon.spec import TemplateId, TemplateInstance
from tests.fixtures.monitor import oracle

from .helpers import (
    BP_LOWER,
    BP_UPPER,
    K_DAY,
    STEP,
    T_DAY,
    Inputs,
    LocalDay,
    SpyRegistry,
    by_key,
    drive,
    entry_row,
    evt,
    final,
    hhmm,
    load_f0,
    load_lib,
    make_config,
    make_monitor,
    make_plan,
    override_row,
    registry_variant,
    smp,
)
from .scenarios import Meas, Scenario, oracle_formulas, oracle_params

REG = load_f0()
LIB = load_lib(REG)
BY_ID = {t.id: t for t in LIB}
PARAMS = oracle_params()
FORMULAS = oracle_formulas(LIB)
INF = math.inf


# ---------------------------------------------------------------------------------------------
# the monitor against the oracle, step by step, intervals and states
# ---------------------------------------------------------------------------------------------


def against_oracle(
    scn: Scenario,
    last: int,
    registry: Any = REG,
    params: Any = PARAMS,
) -> list[Any]:
    """Run ``scn`` through a monitor; every record equals the oracle's interval and the oracle's state."""
    mon = make_monitor(registry, sched=scn.ticks, day_end=scn.day_end_anchors())
    records = drive(mon, scn.to_inputs(), last)
    trace = scn.to_trace()
    insts = {
        i.key: i
        for i in oracle.make_instances(
            trace,
            params,
            sched_anchors=scn.ticks,
            day_end_anchors=scn.day_end_anchors(),
        )
    }
    grids: dict[int, Any] = {}
    for key, recs in by_key(records).items():
        state = "pending"
        for r in recs:
            k = r.t_eval_ms // STEP
            if k not in grids:
                grids[k] = oracle.grid_for(trace, params, k, list(insts.values()))
            lo, hi = oracle.interval(trace, params, FORMULAS, insts[key], k, grids[k])
            assert (r.sigma_interval.lo, r.sigma_interval.hi) == (lo, hi), (key, k)
            if state == "pending":
                state = oracle.classify(lo, hi, k, insts[key].k_d)
            assert r.state.value == state, (key, k, r.state)
    return records


def last_of(records: Sequence[Any], key: str) -> Any:
    return final(records, key)


# ---------------------------------------------------------------------------------------------
# INT: the three witnesses, the first step of the day, the window edge
# ---------------------------------------------------------------------------------------------


def test_an_intake_two_minutes_before_the_dispense_is_a_witness() -> None:
    scn = Scenario(dispenses=(hhmm(0, 30),), intakes=(hhmm(0, 28),))
    records = against_oracle(scn, 31)
    rec = last_of(records, f"int@{hhmm(0, 30)}")
    assert rec.state.value == "satisfied"
    assert rec.sigma_interval.lo == 300_000 - 120_000


def test_a_witness_at_the_first_step_of_the_day_counts() -> None:
    scn = Scenario(dispenses=(hhmm(0, 2),), auths=(0,))
    records = against_oracle(scn, 3)
    rec = last_of(records, f"int@{hhmm(0, 2)}")
    assert rec.state.value == "satisfied"
    assert rec.sigma_interval.lo == 300_000 - 120_000


@pytest.mark.parametrize("level", [0.5, 2.0, -1.0])
def test_a_presence_level_other_than_one_is_not_a_witness(level: float) -> None:
    scn = Scenario(dispenses=(hhmm(0, 30),), presence=((0, 0.0), (hhmm(0, 29), level)))
    records = against_oracle(scn, 31)
    rec = last_of(records, f"int@{hhmm(0, 30)}")
    assert rec.state.value == "violated"
    assert rec.guard_failed == "no_witness"


def test_an_open_position_at_the_first_step_of_the_window_is_named_in_the_marker() -> (
    None
):
    """Dispense at step 30, window 5 steps: the channel is down at step 25 only (the first step)."""
    scn = Scenario(
        dispenses=(hhmm(0, 30),),
        presence=((0, 0.0),),
        unavailable_presence=((25, 25),),
    )
    records = against_oracle(scn, 31)
    rec = last_of(records, f"int@{hhmm(0, 30)}")
    assert rec.state.value == "pending"
    assert rec.sigma_interval.hi == 0.0
    assert rec.undecidable == "undecidable: channel_unavailable:presence"
    # one step earlier the position is outside the window: the age is over the window, a violation
    scn_out = Scenario(
        dispenses=(hhmm(0, 30),),
        presence=((0, 0.0),),
        unavailable_presence=((24, 24),),
    )
    out = last_of(against_oracle(scn_out, 31), f"int@{hhmm(0, 30)}")
    assert out.state.value == "violated" and out.undecidable is None


def test_an_unavailable_intake_channel_alone_leaves_the_witness_open() -> None:
    scn = Scenario(
        dispenses=(hhmm(0, 30),),
        presence=((0, 0.0),),
        unavailable_intake=((29, 30),),
    )
    rec = last_of(against_oracle(scn, 31), f"int@{hhmm(0, 30)}")
    assert rec.state.value == "pending"
    assert rec.undecidable == "undecidable: channel_unavailable:intake"


# ---------------------------------------------------------------------------------------------
# HOLD and RESP windows, SYS guard, the paths of a violation with several failed parts
# ---------------------------------------------------------------------------------------------


def test_a_measurement_exactly_one_look_back_before_the_dispense_is_recent() -> None:
    look_back = int(REG.get("hold_lookback").value)
    t_meas = hhmm(0, 10)
    scn = Scenario(meas=(Meas(t_meas, 120.0),), dispenses=(t_meas + look_back,))
    rec = last_of(against_oracle(scn, 80), f"hold@{t_meas + look_back}")
    assert rec.guard_failed is None and rec.sigma_interval.lo == 120.0 - 100.0
    late = Scenario(meas=(Meas(t_meas, 120.0),), dispenses=(t_meas + look_back + 1000,))
    rec = last_of(against_oracle(late, 80), f"hold@{t_meas + look_back + 1000}")
    assert rec.state.value == "violated"
    assert rec.guard_failed == "no_recent_measurement"


def test_a_response_measured_at_the_first_step_of_its_window_counts() -> None:
    delta1 = int(REG.get("delta1").value)
    t_dose = hhmm(0, 10)
    scn = Scenario(
        standalone_bp=((hhmm(0, 5), 140.0),),
        dispenses=(t_dose,),
        meas=(Meas(t_dose + delta1, 120.0),),
    )
    records = against_oracle(scn, 200)
    rec = last_of(records, f"resp@{t_dose}")
    assert rec.state.value == "satisfied" and rec.sigma_interval.lo == 10.0


def test_a_tie_before_the_decision_step_is_not_a_satisfied_verdict() -> None:
    """pre = 60, the one response is the lower bound 50: [0, 0] at the measurement, 110 steps early."""
    delta1 = int(REG.get("delta1").value)
    t_dose = hhmm(0, 10)
    scn = Scenario(
        standalone_bp=((hhmm(0, 5), 60.0),),
        dispenses=(t_dose,),
        meas=(Meas(t_dose + delta1, BP_LOWER),),
    )
    records = against_oracle(scn, 200)
    recs = by_key(records)[f"resp@{t_dose}"]
    k_meas = (t_dose + delta1) // STEP
    at_meas = next(r for r in recs if r.t_eval_ms == (t_dose + delta1))
    assert at_meas.sigma_interval.lo == at_meas.sigma_interval.hi == 0.0
    assert at_meas.state.value == "pending" and k_meas < recs[-1].t_eval_ms // STEP
    assert recs[-1].state.value == "satisfied"
    assert recs[-1].decided_at_ms == recs[-1].t_eval_ms


@pytest.mark.parametrize("health", [0.0, 2.0, 0.5, -1.0])
def test_only_a_cuff_health_of_exactly_one_is_healthy(health: float) -> None:
    t = hhmm(0, 10)
    scn = Scenario(meas=(Meas(t, 120.0, health=health),))
    rec = last_of(against_oracle(scn, 12), f"sys@{t}")
    assert rec.state.value == "violated" and rec.guard_failed == "cuff_unhealthy"


def test_an_undefined_cuff_health_is_not_an_unhealthy_one() -> None:
    """The violation is the inflation margin; the cuff health is unknown, so no guard is named."""
    t = hhmm(0, 10)
    scn = Scenario(meas=(Meas(t, 120.0, inflation=1_000.0, drop_health=True),))
    rec = last_of(against_oracle(scn, 12), f"sys@{t}")
    assert rec.state.value == "violated"
    assert rec.guard_failed is None
    assert rec.subformula_path is not None and ";" not in rec.subformula_path


def test_a_part_at_zero_is_not_a_violated_part_in_the_path() -> None:
    """The guard fails; the margin is exactly 0 (bp = threshold, inflation = minimum): one path only."""
    threshold = REG.get("bp_hold_threshold").value
    hold = Scenario(standalone_bp=((hhmm(0, 20), threshold),), dispenses=(hhmm(0, 30),))
    rec = last_of(against_oracle(hold, 31), f"hold@{hhmm(0, 30)}")
    assert rec.state.value == "violated" and rec.guard_failed == "no_recent_measurement"
    assert rec.subformula_path is not None and ";" not in rec.subformula_path
    minimum = REG.get("cuff_inflation_min").value
    sys_ = Scenario(meas=(Meas(hhmm(0, 10), 120.0, health=0.0, inflation=minimum),))
    rec = last_of(against_oracle(sys_, 12), f"sys@{hhmm(0, 10)}")
    assert rec.state.value == "violated" and rec.guard_failed == "cuff_unhealthy"
    assert rec.subformula_path is not None and ";" not in rec.subformula_path


def test_a_closed_interval_ending_at_zero_is_pending_not_satisfied(
    tmp_path: Path,
) -> None:
    """The bounds end at the band edge: with no pressure the interval is [-60, 0], not a tie."""
    reg = registry_variant(tmp_path, values={"bound_bp_upper": 110.0})
    t = hhmm(0, 10)
    scn = Scenario(meas=(Meas(t, 120.0, drop_bp=True),))
    records = against_oracle(scn, 12, reg, oracle_params(tmp_path / "registry.yaml"))
    rec = last_of(records, f"range@{t}")
    assert (rec.sigma_interval.lo, rec.sigma_interval.hi) == (-60.0, 0.0)
    assert rec.state.value == "pending"
    assert rec.undecidable == "undecidable: value_undefined:bp"


# ---------------------------------------------------------------------------------------------
# the day: SCHED horizon at the closing step, the day-end COUNT
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tick_step", "last_record_step"),
    [
        (0, K_DAY),  # a tick at step 0 closes with the first day
        (K_DAY, K_DAY + 30),  # a tick on the closing step: only its own window
        (K_DAY - 1, K_DAY),  # one step before the close: the horizon is the close
    ],
)
def test_a_sched_instance_emits_until_its_horizon(
    tick_step: int, last_record_step: int
) -> None:
    window = int(REG.get("sched_window").value) // STEP
    mon = make_monitor(sched=[tick_step * STEP])
    records = drive(mon, Inputs(), K_DAY + window + 10)
    mine = [r for r in records if r.instance_key == f"sched@{tick_step * STEP}"]
    expected = max(tick_step + window, last_record_step)
    assert [r.t_eval_ms // STEP for r in mine] == list(range(tick_step, expected + 1))


def test_the_day_end_count_of_a_plan_loaded_mid_day_counts_the_dispenses_of_its_day() -> (
    None
):
    mon = make_monitor()
    mon.push_event(evt("dispense", 0))  # step 0 closes the previous day: not counted
    mon.push_event(evt("dispense", 3 * STEP))  # counted
    mon.advance(5 * STEP)
    mon.load(make_plan(REG, day_end=[T_DAY]))
    records = list(mon.advance(T_DAY))
    rec = final(records, f"count@{T_DAY}")
    minimum = REG.get("dose_min_day_end").value
    assert rec.sigma_interval.lo == rec.sigma_interval.hi == 1 - minimum
    assert rec.state.value == "violated"


def test_a_dispense_at_the_first_step_after_a_mid_day_load_is_counted() -> None:
    """The day-end count starts at the step after the load; the dispense of that very step is its first."""
    mon = make_monitor()
    mon.advance(5 * STEP)
    mon.load(make_plan(REG, day_end=[T_DAY]))
    mon.push_event(evt("dispense", 6 * STEP))  # the step after the last finalised one
    mon.push_event(evt("dispense", 9 * STEP))
    rec = final(list(mon.advance(T_DAY)), f"count@{T_DAY}")
    minimum = REG.get("dose_min_day_end").value
    assert rec.sigma_interval.lo == rec.sigma_interval.hi == 2 - minimum
    assert rec.state.value == "satisfied"  # 2 of 2: the tie rule at the closing step


def test_a_dispense_on_the_first_step_of_the_day_is_not_of_the_day() -> None:
    """A plan loaded before the day: the instance exists from its first step, which closes the day before."""
    mon = make_monitor(day_end=[2 * T_DAY])
    mon.advance(K_DAY * STEP - 1)  # the previous day
    mon.push_event(evt("dispense", T_DAY))  # step K_DAY: the last step of the first day
    mon.push_event(evt("dispense", T_DAY + 2 * STEP))
    mon.push_event(evt("dispense", T_DAY + 3 * STEP))
    rec = final(list(mon.advance(2 * T_DAY)), f"count@{2 * T_DAY}")
    minimum = REG.get("dose_min_day_end").value
    assert rec.sigma_interval.lo == rec.sigma_interval.hi == 2 - minimum


@pytest.mark.parametrize("anchor", [0, T_DAY - STEP, T_DAY + STEP, 2 * T_DAY - 1])
def test_a_day_end_anchor_must_close_a_day(anchor: int) -> None:
    with pytest.raises(m.PlanFeasibilityError, match="closing step of a day"):
        make_monitor(day_end=[anchor])


def test_a_plan_cannot_add_an_instance_at_the_last_finalised_step() -> None:
    mon = make_monitor()
    mon.advance(5 * STEP)
    with pytest.raises(m.PlanFeasibilityError, match="finalised"):
        mon.load(make_plan(REG, sched=[5 * STEP]))
    mon.load(make_plan(REG, sched=[6 * STEP]))
    assert any(r.instance_key == f"sched@{6 * STEP}" for r in mon.advance(6 * STEP))


def test_a_monitor_without_a_plan_is_idle() -> None:
    cfg = make_config(REG)
    mon = m.StreamingMonitor(cfg, REG, LIB)
    mon.push_event(evt("measurement", STEP))
    mon.push_sample(smp("bp", STEP, 120.0))
    mon.push_event(evt("dispense", 2 * STEP))
    assert mon.advance(3 * STEP) == ()
    assert mon.stats().active_instances == 0


def test_two_measurements_of_one_instant_make_two_instances_with_distinct_keys() -> (
    None
):
    mon = make_monitor()
    t = 10 * STEP
    mon.push_event(evt("measurement", t, source="cuff-a"))
    mon.push_event(evt("measurement", t, source="cuff-b"))
    mon.push_sample(smp("bp", t, 120.0))
    records = mon.advance(t)
    keys = sorted(r.instance_key for r in records if r.template is TemplateId.RANGE)
    assert keys == [f"range@{t}", f"range@{t}#2"]


# ---------------------------------------------------------------------------------------------
# the counters and what is kept
# ---------------------------------------------------------------------------------------------


def test_a_dispense_and_a_dedup_key_are_kept_for_exactly_a_day() -> None:
    mon = make_monitor()
    mon.push_event(evt("dispense", 0, seq=1))
    mon.push_sample(smp("bp", 0, 120.0, seq=1))
    mon.advance((K_DAY - 1) * STEP)
    stats = mon.stats()
    assert stats.retained_samples == 1 and stats.retained_dedup_keys == 2
    mon.advance(K_DAY * STEP)
    stats = mon.stats()
    assert stats.retained_samples == 0 and stats.retained_dedup_keys == 0


def test_an_input_without_a_sequence_number_leaves_no_dedup_key() -> None:
    mon = make_monitor()
    for i in range(3):
        mon.push_sample(smp("bp", i * STEP, 120.0))
        mon.push_event(evt("dispense", i * STEP))
    mon.advance(3 * STEP)
    assert mon.stats().retained_dedup_keys == 0


def test_the_buffered_inputs_are_retained_samples() -> None:
    mon = make_monitor(d_ms=2 * STEP)
    mon.push_sample(smp("bp", 0, 120.0))
    mon.push_sample(smp("bp", STEP, 121.0))
    assert mon.stats().retained_samples == 2 == mon.stats().buffered_inputs


@pytest.mark.parametrize(
    ("value", "out"),
    [(BP_LOWER, 0), (BP_UPPER, 0), (BP_LOWER - 0.5, 1), (BP_UPPER + 0.5, 1)],
)
def test_the_registry_bounds_belong_to_the_domain(value: float, out: int) -> None:
    mon = make_monitor()
    mon.push_sample(smp("bp", 0, value))
    mon.advance(0)
    assert mon.stats().out_of_domain_samples == out


def test_node_updates_count_summaries_released_inputs_and_evaluations() -> None:
    mon = make_monitor()
    mon.advance(2 * STEP)  # steps 0, 1, 2: three summaries
    assert mon.stats().node_updates == 3
    mon.push_sample(smp("bp", 3 * STEP, 120.0))
    mon.push_sample(smp("cuff_health", 3 * STEP, 1.0))
    mon.advance(3 * STEP)  # a summary and two released inputs
    assert mon.stats().node_updates == 3 + 1 + 2
    mon.push_event(evt("measurement", 4 * STEP))
    mon.advance(4 * STEP)  # a summary, a released input, the RANGE and the SYS instance
    assert mon.stats().node_updates == 6 + 1 + 1 + 2
    assert mon.stats().records_emitted == 2


def test_an_input_for_the_last_finalised_step_is_refused() -> None:
    mon = make_monitor()
    mon.advance(5 * STEP)
    mon.push_sample(
        smp("bp", 5 * STEP, 120.0)
    )  # on time by the watermark, step 5 is done
    mon.push_sample(smp("bp", 6 * STEP, 120.0))
    stats = mon.stats()
    assert stats.after_finalisation_count == 1 and stats.accepted_count == 1
    assert [r.reason for r in mon.rejected_inputs()] == ["finalised"]


def test_an_absent_dose_counter_is_read_as_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ralmon.monitor import core
    from ralmon.signals import default_derived_signals
    from ralmon.signals.derived import DoseCount

    monkeypatch.setattr(
        core,
        "default_derived_signals",
        lambda: [d for d in default_derived_signals() if not isinstance(d, DoseCount)],
    )
    mon = make_monitor()
    mon.push_event(evt("dispense", 2 * STEP))
    records = mon.advance(2 * STEP)
    rec = final(records, f"count@{2 * STEP}")
    assert (
        rec.sigma_interval.lo == rec.sigma_interval.hi == REG.get("dose_max_24h").value
    )
    assert rec.state.value == "satisfied"


# ---------------------------------------------------------------------------------------------
# the bounds of one advance call
# ---------------------------------------------------------------------------------------------


def test_advance_accepts_exactly_the_step_cap_and_refuses_one_more(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ralmon.monitor import core

    monkeypatch.setattr(core, "MAX_STEPS_PER_ADVANCE", 6)
    mon = make_monitor()
    assert mon.advance(5 * STEP) == ()  # steps 0..5
    with pytest.raises(m.MonitorInputError, match="steps"):
        mon.advance(12 * STEP)  # seven steps
    assert mon.stats().steps_finalised == 6  # nothing changed
    assert mon.advance(11 * STEP) == ()  # six steps


def test_advance_accepts_exactly_the_record_cap_and_does_not_count_old_instances(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ralmon.monitor import core

    monkeypatch.setattr(core, "MAX_RECORDS_PER_ADVANCE", 10)
    mon = make_monitor(sched=[0])
    assert len(mon.advance(9 * STEP)) == 10  # ten steps, one instance: exactly the cap
    with pytest.raises(m.MonitorInputError, match="records"):
        mon.advance(20 * STEP)  # eleven steps, one instance
    assert mon.stats().steps_finalised == 10
    # six steps, one active instance: 6 records; a started instance is not counted twice
    assert len(mon.advance(15 * STEP)) == 6


# ---------------------------------------------------------------------------------------------
# registry and configuration: the edges of what is accepted
# ---------------------------------------------------------------------------------------------


def config_of(**changes: Any) -> Any:
    return dataclasses.replace(make_config(REG), **changes)


def test_a_zero_step_is_a_named_error() -> None:
    from ralmon.monitor.config import check_config

    with pytest.raises(m.MonitorConfigError, match="step_ms"):
        check_config(config_of(step_ms=0))


def test_the_longest_reorder_delay_is_a_day() -> None:
    from ralmon.monitor.config import check_config

    assert check_config(config_of(reorder_delay_ms=T_DAY)).reorder_delay_ms == T_DAY
    with pytest.raises(m.MonitorConfigError, match="reorder_delay_ms"):
        check_config(config_of(reorder_delay_ms=T_DAY + 1))


class _EqualsEverything:
    def __eq__(self, other: object) -> bool:
        return True

    def __hash__(self) -> int:
        return 1


@pytest.mark.parametrize(
    "variant", ["certain", "", ["likely"], _EqualsEverything(), None, 1]
)
def test_the_variant_is_one_of_the_two_names(variant: Any) -> None:
    from ralmon.monitor.config import check_config

    with pytest.raises(m.MonitorConfigError, match="variant"):
        check_config(config_of(variant=variant))


def test_the_registry_version_of_the_config_is_a_text() -> None:
    from ralmon.monitor.config import check_config

    with pytest.raises(m.MonitorConfigError, match="registry_version must be a str"):
        check_config(config_of(registry_version=5))


class _Entry:
    def __init__(self, value: float) -> None:
        self.value = value


class _Registry:
    def __init__(self, **values: float) -> None:
        self.values = values

    def get(self, name: str) -> Any:
        from ralmon.spec import UnsetParameterError

        if name not in self.values:
            raise UnsetParameterError(
                f"parameter {name!r} is declared but has no value"
            )
        return _Entry(self.values[name])


def test_an_optional_value_may_equal_its_lower_limit() -> None:
    from ralmon.monitor.parameters import optional_value

    assert optional_value(_Registry(skew=0.0), "skew", low=0.0) == 0.0
    assert optional_value(_Registry(), "skew", low=0.0) is None
    with pytest.raises(m.MonitorConfigError, match="at least"):
        optional_value(_Registry(skew=-1.0), "skew", low=0.0)


def test_an_unset_name_is_a_config_error_that_names_it() -> None:
    from ralmon.monitor.parameters import read_value

    spy = SpyRegistry(REG, unset=("delta_resp",))
    with pytest.raises(m.MonitorConfigError, match="delta_resp.*cannot be read"):
        read_value(spy, "delta_resp")


@pytest.mark.parametrize(
    ("params", "ok"),
    [
        ({"sched_window": 0.0}, True),
        ({"sched_window": 120_000.0}, True),
        ({"sched_window": -60_000.0}, False),
        ({"sched_window": 60_000.5}, False),
        ({"sched_window": 90_000.0}, False),
        ({"hold_lookback": 90_000.0}, False),
        ({"int_window": 90_000.0}, False),
        ({"delta1": 90_000.0}, False),
        ({"delta2": 90_000.0}, False),
        ({"delta1": 120_000.0, "delta2": 120_000.0}, True),
        ({"delta1": 180_000.0, "delta2": 120_000.0}, False),
        ({"delta_resp": 7.5, "bp_band_low": 110.5}, True),  # not window parameters
    ],
)
def test_window_parameters_are_non_negative_whole_steps(
    params: dict[str, float], ok: bool
) -> None:
    from ralmon.monitor.parameters import check_alignment

    if ok:
        check_alignment(params, STEP, "test")
    else:
        with pytest.raises(m.PlanFeasibilityError):
            check_alignment(params, STEP, "test")


def test_a_zero_clock_skew_accepts_an_input_stamped_at_its_receive_time(
    tmp_path: Path,
) -> None:
    reg = registry_variant(tmp_path, add_entries=[entry_row("clock_skew_max_ms", 0.0)])
    mon = make_monitor(reg)
    mon.push_sample(smp("bp", 100, 120.0, rx=100))
    mon.push_sample(smp("bp", 200, 121.0, rx=199))
    assert mon.stats().accepted_count == 1 and mon.stats().future_stamped_count == 1


class _ValueRegistry(SpyRegistry):
    """The registry with some values replaced (a registry that the loader would not have produced)."""

    def __init__(self, inner: Any, **values: float) -> None:
        super().__init__(inner)
        self.values = values

    def get(self, name: str) -> Any:
        try:
            entry = super().get(name)
        except Exception:
            if name in self.values:  # a name the registry does not declare
                return _Entry(self.values[name])
            raise
        if name in self.values:
            return dataclasses.replace(entry, value=self.values[name])
        return entry


def test_a_negative_clock_skew_is_refused() -> None:
    reg = _ValueRegistry(REG, clock_skew_max_ms=-1.0)
    with pytest.raises(m.MonitorConfigError, match="clock_skew_max_ms"):
        m.StreamingMonitor(make_config(REG), reg, LIB)


@pytest.mark.parametrize("scale", [0.0, -20.0])
def test_a_scale_must_be_positive(scale: float) -> None:
    """The template loader refuses it too; the monitor does not rely on the loader having run."""
    reg = _ValueRegistry(REG, scale_range=scale)
    with pytest.raises(m.MonitorConfigError, match="scale_range.*positive"):
        m.StreamingMonitor(make_config(REG), reg, LIB)


@pytest.mark.parametrize("sd", [0.0, -3.0])
def test_a_device_error_that_is_not_positive_is_no_error_model(sd: float) -> None:
    reg = _ValueRegistry(REG, cuff_error_sd=sd)
    mon = make_monitor(reg)
    mon.push_event(evt("measurement", STEP))
    mon.push_sample(smp("bp", STEP, 200.0))
    records = mon.advance(STEP)
    rec = final(records, f"range@{STEP}")
    assert rec.state.value == "violated" and rec.rho is None
    assert mon.stats().rho_unavailable == 1


# ---------------------------------------------------------------------------------------------
# the reorder buffer key
# ---------------------------------------------------------------------------------------------


def test_an_input_with_a_sequence_number_precedes_one_without_at_the_same_key() -> None:
    from ralmon.monitor.reorder import BufferedInput, ReorderBuffer

    buf = ReorderBuffer(10)
    assert buf.push(BufferedInput(10, 1, "sample", "plain", None))
    assert buf.push(BufferedInput(10, 9, "sample", "numbered", 5))
    assert [x.item for x in buf.release(10)] == ["numbered", "plain"]


# ---------------------------------------------------------------------------------------------
# formulas and paths
# ---------------------------------------------------------------------------------------------


def test_a_formula_may_not_nest_without_limit() -> None:
    from ralmon.monitor.formula import parse_formula

    with pytest.raises(m.MonitorConfigError, match="deep|depth|nest"):
        parse_formula("(" * 200 + "meas" + ")" * 200)


def test_text_after_a_formula_is_refused() -> None:
    from ralmon.monitor.formula import parse_formula

    with pytest.raises(m.MonitorConfigError, match="after the formula"):
        parse_formula("meas meas")


def test_find_returns_the_first_node_in_preorder() -> None:
    from ralmon.monitor.formula import parse_formula

    formula = parse_formula("meas or meas")
    assert formula.find("meas") == (0,)
    assert formula.find("meas or meas") == ()


@pytest.mark.parametrize(
    "path",
    [
        "int/0/no_witness/1",  # the guard marker is only the last element
        "int/²",  # a digit that is not an ASCII digit
        "int/٣",  # an Arabic-Indic digit, which int() would accept
        "int/-1",
        "int/ 1",
        "int/0//0",
        "int/9",
    ],
)
def test_a_path_that_does_not_resolve_is_a_named_error(path: str) -> None:
    from ralmon.monitor.formula import resolve_subformula_path

    with pytest.raises(m.MonitorInputError):
        resolve_subformula_path(BY_ID[TemplateId.INT], path)


def test_the_marker_names_the_sorted_unique_entries() -> None:
    from ralmon.monitor.instances import format_marker

    assert format_marker([]) is None
    assert format_marker(
        ["value_undefined:bp", "channel_unavailable:presence", "value_undefined:bp"]
    ) == ("undecidable: channel_unavailable:presence,value_undefined:bp")


# ---------------------------------------------------------------------------------------------
# the point evaluator: what a missing value, an infinity or a different registry mean
# ---------------------------------------------------------------------------------------------


def evaluator(
    tid: TemplateId,
    anchor: int,
    *,
    kind: str | None = None,
    registry: Any = REG,
    step: int = STEP,
    template: Any = None,
    params: dict[str, float] | None = None,
) -> Any:
    instance = TemplateInstance(tid, f"{tid.value}@{anchor}", params or {}, anchor)
    return m.make_point_evaluator(
        template or BY_ID[tid], instance, registry, step, anchor_kind=kind
    )


def run(ev: Any, rows: Sequence[dict[str, float | None]]) -> list[float | None]:
    return [ev.step(k * STEP, row) for k, row in enumerate(rows)]


def test_a_missing_or_undefined_count_is_zero() -> None:
    for row in ({}, {"dose_count": math.nan}, {"dose_count": None}):
        ev = evaluator(TemplateId.COUNT, 2 * STEP, kind="dispense")
        out = run(ev, [row, row, row])
        assert out[-1] == REG.get("dose_max_24h").value


def test_a_missing_measurement_count_is_no_measurement() -> None:
    window = int(REG.get("sched_window").value) // STEP
    ev = evaluator(TemplateId.SCHED, STEP)
    out = run(ev, [{} for _ in range(window + 2)])
    assert out[-1] == -INF
    assert ev.guard_failed == "no_measurement_after_tick"


def test_an_unavailable_intake_channel_leaves_the_witness_open() -> None:
    ev = evaluator(TemplateId.INT, 5 * STEP)
    rows: list[dict[str, float | None]] = [
        {"presence": 0.0, "intake": None, "auth": 0.0, "dispense": 0.0}
        for _ in range(6)
    ]
    out = run(ev, rows)
    assert out[-1] is None and ev.guard_failed is None  # unknown, not minus infinity
    rows_known = [dict(r, intake=0.0) for r in rows]
    ev = evaluator(TemplateId.INT, 5 * STEP)
    assert run(ev, rows_known)[-1] == -INF


def test_a_day_end_dispense_on_the_first_step_belongs_to_the_previous_day() -> None:
    ev = evaluator(TemplateId.COUNT, T_DAY, kind="day_end")
    rows: list[dict[str, float | None]] = [{} for _ in range(K_DAY + 1)]
    rows[0] = {"dispense": 1.0}
    rows[5] = {"dispense": 1.0}
    out = run(ev, rows)
    assert out[-1] == 1 - REG.get("dose_min_day_end").value


@pytest.mark.parametrize("anchor", [0, T_DAY - STEP, T_DAY + STEP])
def test_a_day_end_evaluator_needs_a_closing_step(anchor: int) -> None:
    with pytest.raises(m.MonitorConfigError, match="closing step"):
        evaluator(TemplateId.COUNT, anchor, kind="day_end")


def test_a_template_with_another_formula_is_refused() -> None:
    other = dataclasses.replace(BY_ID[TemplateId.RANGE], formula_past_time="meas")
    with pytest.raises(m.MonitorConfigError, match="formula"):
        evaluator(TemplateId.RANGE, STEP, template=other)


def test_the_step_must_be_the_step_of_the_registry() -> None:
    other = load_f0(step_ms=STEP // 2)
    with pytest.raises(m.MonitorConfigError, match="step_ms"):
        evaluator(TemplateId.RANGE, STEP, registry=other)


def test_an_override_off_the_grid_is_refused(tmp_path: Path) -> None:
    reg = registry_variant(
        tmp_path, overrides=[override_row("sched_window", 0.0, 3_600_000.0)]
    )
    with pytest.raises(m.MonitorConfigError, match="multiple"):
        evaluator(
            TemplateId.SCHED, STEP, registry=reg, params={"sched_window": 90_000.0}
        )


def test_a_value_may_be_undefined_but_not_infinite() -> None:
    ev = evaluator(TemplateId.RANGE, STEP)
    ev.step(0, {"bp": math.nan})
    with pytest.raises(m.MonitorInputError, match="finite"):
        ev.step(STEP, {"bp": INF})


# ---------------------------------------------------------------------------------------------
# the rho helpers: the clamp, and the integral over no response
# ---------------------------------------------------------------------------------------------


def test_a_probability_is_clamped_to_the_unit_interval() -> None:
    from ralmon.monitor.measured_rho import _measured

    assert _measured(1.0 + 1e-9).value == 1.0
    assert _measured(-1e-9).value == 0.0
    assert _measured(0.25).value == 0.25


def test_no_response_gives_the_empty_product() -> None:
    from ralmon.monitor.measured_rho import difference_rho

    assert abs(difference_rho(120.0, [], 10.0, 6.0).value - 1.0) < 1e-9


# ---------------------------------------------------------------------------------------------
# helpers of the package: the edges of a time and a value
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "ok"),
    [(0, True), (2**53, True), (2**53 + 1, False), (-1, False), (True, False)],
)
def test_the_edges_of_a_time(value: Any, ok: bool) -> None:
    from ralmon.monitor._text import as_int

    if ok:
        assert as_int(value, "t", m.MonitorInputError) == value
    else:
        with pytest.raises(m.MonitorInputError):
            as_int(value, "t", m.MonitorInputError)


@pytest.mark.parametrize(
    ("value", "ok"),
    [(1e15, True), (-1e15, True), (1e15 * 1.000001, False), (math.nan, False)],
)
def test_the_edges_of_a_value(value: float, ok: bool) -> None:
    from ralmon.monitor._text import as_number

    if ok:
        assert as_number(value, "v", m.MonitorInputError) == value
    else:
        with pytest.raises(m.MonitorInputError):
            as_number(value, "v", m.MonitorInputError)


def test_a_day_that_is_not_a_trace_is_a_named_error() -> None:
    cfg = make_config(REG)
    with pytest.raises(m.MonitorInputError, match="observed day"):
        m.run_offline(object(), make_plan(REG), cfg, None, None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------------------------
# an invariant that fails is an invariant error, not a complaint about the argument
# ---------------------------------------------------------------------------------------------


BAD_INTERVALS = [(1.0, 0.0), (math.nan, 0.0), (0.0, math.nan)]


@pytest.mark.parametrize("bad", BAD_INTERVALS)
def test_an_invalid_interval_is_an_invariant_error_in_advance(
    monkeypatch: pytest.MonkeyPatch, bad: tuple[float, float]
) -> None:
    from ralmon.monitor.instances import RangeInstance

    monkeypatch.setattr(RangeInstance, "interval", lambda self, k, v: bad)
    mon = make_monitor()
    mon.push_event(evt("measurement", 0))
    with pytest.raises(m.MonitorInvariantError, match="invalid interval"):
        mon.advance(0)


@pytest.mark.parametrize("bad", BAD_INTERVALS)
def test_an_invalid_interval_is_an_invariant_error_in_run_offline(
    monkeypatch: pytest.MonkeyPatch, bad: tuple[float, float]
) -> None:
    from ralmon.monitor.instances import RangeInstance

    monkeypatch.setattr(RangeInstance, "interval", lambda self, k, v: bad)
    day = LocalDay(samples=(), events=(evt("measurement", 0),))
    with pytest.raises(m.MonitorInvariantError, match="invalid interval"):
        m.run_offline(
            day,
            make_plan(REG),
            make_config(REG),
            None,
            None,
            registry=REG,
            templates=LIB,
        )


def test_an_invalid_interval_is_an_invariant_error_in_the_point_evaluator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ralmon.monitor.instances import RangeInstance

    monkeypatch.setattr(RangeInstance, "interval", lambda self, k, v: (1.0, 0.0))
    ev = evaluator(TemplateId.RANGE, 0)
    with pytest.raises(m.MonitorInvariantError, match="invalid interval"):
        ev.step(0, {"bp": 120.0})
