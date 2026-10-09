"""Robustness intervals of ``StreamingMonitor`` against the independent oracle (WS05-T04 tests 13 to 15).

The oracle (``tests/fixtures/monitor/oracle.py``) evaluates the template strings by the structural
recursion of docs/formal/05 section 2.2 on dense arrays. The monitor uses the closed forms of
section 2.3 (Lemma 10). Both are fixture arithmetic with half-unit pressures, so the comparison is
exact. Hypothesis is derandomised (``tests/conftest.py``) with small example counts.
"""

from __future__ import annotations

import math
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tests.fixtures.monitor import oracle

from .helpers import (
    STEP,
    T_DAY,
    by_key,
    drive,
    hhmm,
    load_f0,
    load_lib,
    make_monitor,
    registry_variant,
)
from .scenarios import (
    Meas,
    Scenario,
    futures,
    oracle_formulas,
    oracle_params,
    scenarios,
)

REG = load_f0()
LIB = load_lib(REG)
PARAMS = oracle_params()
FORMULAS = oracle_formulas(LIB)
SETTINGS = settings(
    max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow]
)


def engine(scn: Scenario, last: int, registry: Any = REG) -> list[Any]:
    mon = make_monitor(registry, sched=scn.ticks, day_end=scn.day_end_anchors())
    return drive(mon, scn.to_inputs(), last)


def oracle_instances(scn: Scenario) -> dict[str, oracle.Inst]:
    return {
        i.key: i
        for i in oracle.make_instances(
            scn.to_trace(),
            PARAMS,
            sched_anchors=scn.ticks,
            day_end_anchors=scn.day_end_anchors(),
        )
    }


# ---------------------------------------------------------------------------------------------
# the closed forms equal the structural recursion
# ---------------------------------------------------------------------------------------------


@SETTINGS
@given(scenarios(), st.integers(0, 330), st.data())
def test_closed_forms_equal_the_structural_recursion(
    scn: Scenario, cut: int, data: st.DataObject
) -> None:
    records = engine(scn, cut)
    insts = oracle_instances(scn)
    trace = scn.to_trace()
    steps = sorted({cut, data.draw(st.integers(0, cut))})
    grids = {k: oracle.grid_for(trace, PARAMS, k, list(insts.values())) for k in steps}
    assert {r.instance_key for r in records} <= set(insts)
    for r in records:
        k = r.t_eval_ms // STEP
        if k not in grids:
            continue
        lo, hi = oracle.interval(
            trace, PARAMS, FORMULAS, insts[r.instance_key], k, grids[k]
        )
        assert (r.sigma_interval.lo, r.sigma_interval.hi) == (lo, hi), (
            r.instance_key,
            k,
        )


@SETTINGS
@given(scenarios(), st.integers(0, 330))
def test_the_state_machine_is_the_rule_applied_to_the_intervals(
    scn: Scenario, last: int
) -> None:
    """Rule 1 and the tie rule on the intervals the monitor itself emitted; absorbing; first step wins."""
    records = engine(scn, last)
    insts = oracle_instances(scn)
    for key, recs in by_key(records).items():
        k_d = insts[key].k_d
        state, decided = "pending", None
        for r in recs:
            k = r.t_eval_ms // STEP
            if state == "pending":
                now = oracle.classify(r.sigma_interval.lo, r.sigma_interval.hi, k, k_d)
                if now != "pending":
                    state, decided = now, k * STEP
            assert r.state.value == state, (key, k)
            assert r.decided_at_ms == decided, (key, k)
        # an instance still active at the end is listed up to the last step it was active
        assert [r.t_eval_ms for r in recs] == sorted(r.t_eval_ms for r in recs)


@SETTINGS
@given(scenarios(), st.integers(0, 330))
def test_instances_exist_exactly_when_the_oracle_says(scn: Scenario, last: int) -> None:
    """Every instance of the trace with act <= last has a first record at ``act``."""
    records = engine(scn, last)
    got = by_key(records)
    for key, inst in oracle_instances(scn).items():
        if inst.act <= last:
            assert key in got, key
            assert got[key][0].t_eval_ms == inst.act * STEP, key
        else:
            assert key not in got, key


# ---------------------------------------------------------------------------------------------
# test 13: soundness for every completion
# ---------------------------------------------------------------------------------------------


@SETTINGS
@given(scenarios(), st.integers(0, 330), st.data())
def test_interval_contains_true_robustness_for_every_completion(
    scn: Scenario, cut: int, data: st.DataObject
) -> None:
    prefix = scn.truncated(cut)
    full = prefix.with_future(data.draw(futures(cut)))
    records = engine(prefix, cut)
    insts_full = oracle_instances(full)
    horizon = max(i.horizon for i in insts_full.values()) if insts_full else 0
    cut_full = max(cut, full.last_step(), horizon) + 1
    trace = full.to_trace()
    grid = oracle.grid_for(trace, PARAMS, cut_full, list(insts_full.values()))
    last_record: dict[str, Any] = {}
    for r in records:
        last_record[r.instance_key] = (
            r  # the latest interval of each instance, at its retirement or at the cut
        )
    for key, rec in last_record.items():
        lo_f, hi_f = oracle.interval(
            trace, PARAMS, FORMULAS, insts_full[key], cut_full, grid
        )
        assert rec.sigma_interval.lo <= lo_f <= hi_f <= rec.sigma_interval.hi, (
            key,
            rec.sigma_interval,
            lo_f,
            hi_f,
        )


def test_soundness_example_sched_any_arrival_time_is_inside_the_interval() -> None:
    """V-SCHED-1 by hand: [-inf, 19 min]; a measurement at any later step gives a value inside."""
    tick = hhmm(9, 0)
    records = engine(Scenario(ticks=(tick,)), 550)
    rec = by_key(records)[f"sched@{tick}"][-1]
    assert (rec.sigma_interval.lo, rec.sigma_interval.hi) == (-math.inf, 1_140_000.0)
    for arrival in (551, 560, 570, 571, 600):
        full = Scenario(meas=(Meas(arrival * STEP, 130.0),), ticks=(tick,))
        inst = oracle_instances(full)[f"sched@{tick}"]
        trace = full.to_trace()
        lo, hi = oracle.interval(
            trace,
            PARAMS,
            FORMULAS,
            inst,
            700,
            oracle.grid_for(trace, PARAMS, 700, [inst]),
        )
        assert lo == hi
        assert rec.sigma_interval.lo <= lo <= rec.sigma_interval.hi, arrival


# ---------------------------------------------------------------------------------------------
# test 14: widening the physiological bounds widens the interval
# ---------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def wide_registry(tmp_path_factory: pytest.TempPathFactory) -> Any:
    return registry_variant(
        tmp_path_factory.mktemp("wide"),
        values={"bound_bp_lower": 40, "bound_bp_upper": 260},
    )


@SETTINGS
@given(scenarios(), st.integers(0, 330))
def test_interval_inclusion_is_monotone_in_bounds(
    wide_registry: Any, scn: Scenario, last: int
) -> None:
    narrow = {(r.instance_key, r.t_eval_ms): r for r in engine(scn, last)}
    wide = {(r.instance_key, r.t_eval_ms): r for r in engine(scn, last, wide_registry)}
    for key, n in narrow.items():
        if (
            key in wide
        ):  # an early decision at a narrow bound may retire an instance earlier
            w = wide[key]
            assert w.sigma_interval.lo <= n.sigma_interval.lo, key
            assert n.sigma_interval.hi <= w.sigma_interval.hi, key


def test_the_bounds_come_from_the_registry(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """RESP with pre 150: hi is (150 - bound_lower) - delta_resp, so the registry decides it."""
    inputs_scn = Scenario(
        meas=(Meas(hhmm(6, 55), 150.0),),
        dispenses=(hhmm(7, 0),),
    )
    for lower, want in ((50, 90.0), (100, 40.0)):
        registry = registry_variant(
            tmp_path_factory.mktemp("lower"), values={"bound_bp_lower": lower}
        )
        rec = by_key(engine(inputs_scn, 430, registry))[f"resp@{hhmm(7, 0)}"][-1]
        assert rec.sigma_interval.hi == want, lower


# ---------------------------------------------------------------------------------------------
# test 15: endpoints are ordered and may be infinite
# ---------------------------------------------------------------------------------------------


@SETTINGS
@given(scenarios(in_domain=False), st.integers(0, 330))
def test_interval_endpoints_are_ordered_and_may_be_infinite(
    scn: Scenario, last: int
) -> None:
    saw_infinite = False
    for r in engine(scn, last):
        lo, hi = r.sigma_interval.lo, r.sigma_interval.hi
        assert not math.isnan(lo) and not math.isnan(hi)
        assert lo <= hi, r
        n_lo, n_hi = r.sigma_norm_interval
        assert -1.0 <= n_lo <= n_hi <= 1.0, r
        if lo == -math.inf:
            assert n_lo == -1.0
            saw_infinite = True
        if hi == math.inf:
            assert n_hi == 1.0
            saw_infinite = True
    assert saw_infinite in (True, False)


def test_infinite_endpoints_normalise_to_the_unit_interval() -> None:
    """CP12: V-COUNT-3 is [-1, +inf] dose and V-SCHED-1 is [-inf, 1140000] ms."""
    scn = Scenario(dispenses=(7 * 3_600_000,), day_end=True)
    rec = by_key(engine(scn, 1290))[f"count@{T_DAY}"][-1]
    assert (rec.sigma_interval.lo, rec.sigma_interval.hi) == (-1.0, math.inf)
    assert rec.sigma_norm_interval == (-1.0, 1.0)
    scn2 = Scenario(ticks=(9 * 3_600_000,))
    rec2 = by_key(engine(scn2, 550))[f"sched@{9 * 3_600_000}"][-1]
    assert rec2.sigma_norm_interval[0] == -1.0
    assert rec2.sigma_norm_interval[1] == pytest.approx(0.6333333333333333)
