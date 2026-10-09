"""The grammar of the template strings, sub-formula paths and the point evaluator (WS05-T04, step 5).

The monitor implements the closed forms of docs/formal/05 section 2.3 (Lemma 10) for exactly the
strings of the library; the parser below is what binds the two (a library with another string is
refused) and what gives ``subformula_path`` its child-index syntax. ``make_point_evaluator`` is the
entry point of baselines B3 and B5 (ADR-013, outcome C: no RTAMT).
"""

from __future__ import annotations

import math
from typing import Any

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

import ralmon.monitor as m
from ralmon.spec import TemplateId, TemplateInstance
from tests.fixtures.monitor import oracle

from .helpers import (
    STEP,
    T_DAY,
    Inputs,
    at_step,
    by_key,
    drive,
    evt,
    hhmm,
    load_f0,
    load_lib,
    make_monitor,
    smp,
    step_values,
)
from .scenarios import SETTINGS, Scenario, oracle_formulas, oracle_params, scenarios

REG = load_f0()
LIB = load_lib(REG)
BY_ID = {t.id: t for t in LIB}
INF = math.inf


def parse_formula(text: Any) -> Any:
    from ralmon.monitor.evaluator import parse_formula as parse

    return parse(text)


def resolve_subformula_path(template: Any, path: Any) -> str:
    from ralmon.monitor.evaluator import resolve_subformula_path as resolve

    return resolve(template, path)


# ---------------------------------------------------------------------------------------------
# the grammar of 02-templates.md section 1.2
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("template", LIB, ids=[t.id.value for t in LIB])
def test_every_library_string_parses_and_reprints_stably(template: Any) -> None:
    formula = parse_formula(template.formula_past_time)
    assert parse_formula(formula.text).text == formula.text


def test_whitespace_is_not_structure() -> None:
    a = parse_formula(
        "historically(meas -> (bp >= bp_band_low and bp <= bp_band_high))"
    )
    b = parse_formula(
        "  historically ( meas->( bp>=bp_band_low   and   bp<=bp_band_high ) ) "
    )
    assert a == b and a.text == b.text


def test_precedence_and_associativity() -> None:
    assert (
        parse_formula("meas or dispense and intake").text
        == "meas or (dispense and intake)"
    )
    assert parse_formula("not meas and dispense").text == "(not meas) and dispense"
    assert (
        parse_formula("meas -> dispense -> intake").text
        == "meas -> (dispense -> intake)"
    )
    assert (
        parse_formula("meas and dispense and intake").text
        == "(meas and dispense) and intake"
    )
    assert (
        parse_formula("once[0, 60000] meas and dispense").text
        == "(once[0, 60000] meas) and dispense"
    )


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "   ",
        "historically(",
        "meas ->",
        "bp >=",
        "meas !",
        "once meas",  # once needs an interval
        "bp + 1",  # an atom without a comparison must be a signal
        "(meas",
        "meas)",
        "meas meas",
        "bp >= >= 1",
        "once[0, ] meas",
        "once[0 meas",
        "1 >= ",
        "BP >= 1",
        "x" * 20_000,
        "(" * 5_000 + "meas" + ")" * 5_000,
        "not " * 5_000 + "meas",
    ],
    ids=lambda s: (s[:12] + str(len(s))) if isinstance(s, str) else "x",
)
def test_a_string_outside_the_grammar_is_refused_by_name(bad: str) -> None:
    with pytest.raises(m.MonitorConfigError):
        parse_formula(bad)


@pytest.mark.parametrize("bad", [None, 5, b"meas", ["meas"]])
def test_parse_refuses_a_non_string(bad: Any) -> None:
    with pytest.raises(m.MonitorConfigError):
        parse_formula(bad)


def test_since_is_in_the_grammar_but_unused() -> None:
    assert parse_formula("meas since[0, 60000] dispense").text.startswith("meas since")


# ---------------------------------------------------------------------------------------------
# paths: child indices from the root, labels for the conjuncts of COUNT, the guard marker last
# ---------------------------------------------------------------------------------------------


def one(template_id: TemplateId, path: str) -> str:
    return resolve_subformula_path(BY_ID[template_id], path)


def test_path_syntax_resolves_to_the_sub_formula_text() -> None:
    assert one(TemplateId.RANGE, "range/0/1/0") == "bp >= bp_band_low"
    assert one(TemplateId.RANGE, "range/0/1/1") == "bp <= bp_band_high"
    assert one(TemplateId.SCHED, "sched/0/1/0/0") == "meas"
    assert one(TemplateId.SCHED, "sched/0/1/0/1") == "age >= 0"
    assert one(TemplateId.HOLD, "hold/0/1/0") == "once[0, hold_lookback] meas"
    assert one(TemplateId.HOLD, "hold/0/1/1") == "bp >= bp_hold_threshold"
    assert one(TemplateId.COUNT, "count/limit/0/1") == "dose_count <= dose_max_24h"
    assert (
        one(TemplateId.COUNT, "count/day_end/0/1") == "dose_count >= dose_min_day_end"
    )
    assert one(TemplateId.RESP, "resp/0/1/0/0") == "meas"
    assert one(TemplateId.RESP, "resp/0/1/0/1") == "bp_drop >= delta_resp"
    assert one(TemplateId.SYS, "sys/0/1/0") == "cuff_health == 1"
    assert one(TemplateId.SYS, "sys/0/1/1") == "inflation_ms >= cuff_inflation_min"
    assert one(TemplateId.INT, "int/0/1/0/0") == "(presence or intake) or auth"
    assert one(TemplateId.INT, "int/0/1/0/1") == "age <= int_window"
    # the guard marker is the last element and does not change what the path resolves to
    assert one(TemplateId.SCHED, "sched/0/1/0/0/no_measurement_after_tick") == "meas"


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "sched/9",
        "sched/0/0/0/0/0/0/0",
        "sched/x",
        "range/0/1/0",
        "sched/-1",
        "sched//",
        "sched/0/1/0/0/obligation_unmet",
        None,
        5,
    ],
)
def test_a_path_that_does_not_resolve_is_refused(bad: Any) -> None:
    with pytest.raises(m.MonitorInputError):
        resolve_subformula_path(BY_ID[TemplateId.SCHED], bad)


def path_of(records: list[Any], key: str) -> str | None:
    return by_key(records)[key][-1].subformula_path


def run(inputs: Inputs, until_ms: int, **kwargs: Any) -> list[Any]:
    mon = make_monitor(REG, **kwargs)
    return drive(mon, inputs, until_ms // STEP)


def measure(inputs: Inputs, t: int, bp: float, **kw: float) -> None:
    inputs.events.append(evt("measurement", t, source="cuff"))
    inputs.samples.append(smp("bp", t, bp))
    inputs.samples.append(smp("cuff_health", t, kw.get("health", 1.0)))
    inputs.samples.append(smp("inflation_ms", t, kw.get("inflation", 45_000.0)))


def test_range_path_names_the_limit_that_decided() -> None:
    for bp, want in (
        (104.0, "bp >= bp_band_low"),
        (152.0, "bp <= bp_band_high"),
        (125.0, "bp >= bp_band_low"),
    ):
        inputs = Inputs()
        measure(inputs, hhmm(9, 0), bp)
        path = path_of(run(inputs, hhmm(9, 0)), f"range@{hhmm(9, 0)}")
        assert path is not None and path.startswith("range/")
        assert resolve_subformula_path(BY_ID[TemplateId.RANGE], path) == want, bp


def test_pending_records_have_no_path_and_no_guard() -> None:
    inputs = Inputs()
    records = run(inputs, hhmm(9, 10), sched=(hhmm(9, 0),))
    rec = by_key(records)[f"sched@{hhmm(9, 0)}"][-1]
    assert rec.state is m.VerdictState.PENDING
    assert (
        rec.subformula_path is None
        and rec.guard_failed is None
        and rec.undecidable is None
    )


def test_guard_paths_end_with_the_marker() -> None:
    inputs = Inputs()
    records = run(inputs, hhmm(9, 31), sched=(hhmm(9, 0),))
    assert (
        path_of(records, f"sched@{hhmm(9, 0)}")
        == "sched/0/1/0/0/no_measurement_after_tick"
    )
    inputs2 = Inputs()
    measure(inputs2, hhmm(9, 5), 130.0)
    records2 = run(inputs2, hhmm(9, 5), sched=(hhmm(9, 0),))
    rec = at_step(records2, f"sched@{hhmm(9, 0)}", hhmm(9, 5))
    assert (
        rec.subformula_path == "sched/0/1/0/1" and rec.guard_failed is None
    )  # the deadline margin decided


def test_resp_paths() -> None:
    pre = Inputs()
    measure(pre, hhmm(6, 55), 150.0)
    pre.events.append(evt("dispense", hhmm(7, 0), source="dispenser"))
    guard = path_of(run(pre, hhmm(10, 0)), f"resp@{hhmm(7, 0)}")
    assert guard == "resp/0/1/0/0/obligation_unmet"
    margin = Inputs()
    measure(margin, hhmm(6, 55), 150.0)
    margin.events.append(evt("dispense", hhmm(7, 0), source="dispenser"))
    measure(margin, hhmm(8, 30), 145.0)
    assert path_of(run(margin, hhmm(10, 0)), f"resp@{hhmm(7, 0)}") == "resp/0/1/0/1"
    early = Inputs()
    measure(early, hhmm(6, 45), 55.0)
    early.events.append(evt("dispense", hhmm(7, 0), source="dispenser"))
    assert (
        path_of(run(early, hhmm(7, 0)), f"resp@{hhmm(7, 0)}") == "resp/0/1/0/1"
    )  # the bound, not a guard


def test_count_paths_carry_the_conjunct_label() -> None:
    inputs = Inputs()
    for t in (hhmm(7, 0), hhmm(21, 0), hhmm(21, 2)):
        inputs.events.append(evt("dispense", t, source="dispenser"))
    records = run(inputs, T_DAY, day_end=(T_DAY,))
    assert path_of(records, f"count@{hhmm(21, 2)}") == "count/limit/0/1"
    inputs2 = Inputs()
    inputs2.events.append(evt("dispense", hhmm(7, 0), source="dispenser"))
    assert (
        path_of(run(inputs2, T_DAY, day_end=(T_DAY,)), f"count@{T_DAY}")
        == "count/day_end/0/1"
    )


def test_sys_lists_the_decisive_path_first_then_the_other_violated_ones() -> None:
    inputs = Inputs()
    measure(
        inputs, hhmm(9, 0), 130.0, health=0.0, inflation=9_000.0
    )  # the guard fails and so does the margin
    rec = by_key(run(inputs, hhmm(9, 0)))[f"sys@{hhmm(9, 0)}"][-1]
    assert rec.guard_failed == "cuff_unhealthy"
    assert rec.subformula_path == "sys/0/1/0/cuff_unhealthy;sys/0/1/1"
    healthy = Inputs()
    measure(healthy, hhmm(9, 0), 130.0, inflation=9_000.0)
    rec2 = by_key(run(healthy, hhmm(9, 0)))[f"sys@{hhmm(9, 0)}"][-1]
    assert rec2.subformula_path == "sys/0/1/1"


def test_hold_and_int_paths() -> None:
    old = Inputs()
    measure(
        old, hhmm(5, 30), 120.0
    )  # 90 minutes before the dose: the guard fails, the margin is positive
    old.events.append(evt("dispense", hhmm(7, 0), source="dispenser"))
    rec = by_key(run(old, hhmm(7, 0)))[f"hold@{hhmm(7, 0)}"][-1]
    assert rec.subformula_path == "hold/0/1/0/no_recent_measurement"
    both = Inputs()
    measure(
        both, hhmm(5, 30), 90.0
    )  # the guard fails and the held pressure is below the threshold too
    both.events.append(evt("dispense", hhmm(7, 0), source="dispenser"))
    rec2 = by_key(run(both, hhmm(7, 0)))[f"hold@{hhmm(7, 0)}"][-1]
    assert rec2.subformula_path == "hold/0/1/0/no_recent_measurement;hold/0/1/1"
    recent = Inputs()
    measure(recent, hhmm(6, 50), 94.0)
    recent.events.append(evt("dispense", hhmm(7, 0), source="dispenser"))
    assert (
        by_key(run(recent, hhmm(7, 0)))[f"hold@{hhmm(7, 0)}"][-1].subformula_path
        == "hold/0/1/1"
    )
    witness = Inputs()
    witness.samples.append(smp("presence", 0, 0.0))
    witness.events.append(evt("dispense", hhmm(7, 0), source="dispenser"))
    assert (
        by_key(run(witness, hhmm(7, 0)))[f"int@{hhmm(7, 0)}"][-1].subformula_path
        == "int/0/1/0/0/no_witness"
    )
    old_witness = Inputs()
    old_witness.samples.append(smp("presence", hhmm(6, 52), 1.0))
    old_witness.samples.append(smp("presence", hhmm(6, 53), 0.0))
    old_witness.events.append(evt("dispense", hhmm(7, 0), source="dispenser"))
    assert (
        by_key(run(old_witness, hhmm(7, 0)))[f"int@{hhmm(7, 0)}"][-1].subformula_path
        == "int/0/1/0/1"
    )


# ---------------------------------------------------------------------------------------------
# make_point_evaluator
# ---------------------------------------------------------------------------------------------


def evaluator(
    template_id: TemplateId,
    anchor: int,
    *,
    kind: str | None = None,
    params: dict[str, float] | None = None,
) -> Any:
    instance = TemplateInstance(
        template_id, f"{template_id.value}@{anchor}", params or {}, anchor
    )
    return m.make_point_evaluator(
        BY_ID[template_id], instance, REG, STEP, anchor_kind=kind
    )


def feed(ev: Any, inputs: Inputs, last: int) -> list[float | None]:
    values = step_values(inputs, last)
    return [ev.step(k * STEP, values[k]) for k in range(last + 1)]


def test_the_value_is_none_until_the_decision_step_then_the_decision_value() -> None:
    inputs = Inputs()
    inputs.events.append(evt("measurement", hhmm(9, 5), source="cuff"))
    out = feed(evaluator(TemplateId.SCHED, hhmm(9, 0)), inputs, 575)
    assert all(v is None for v in out[:570])  # the value is defined at k_d = 570
    assert out[570] == 1_500_000.0
    assert out[575] == 1_500_000.0  # kept after the decision


def test_sched_value_is_graded_after_the_decision_step() -> None:
    """G-SCHED-3: the string gives -inf at the decision step; the instance value grades the lateness."""
    ev = evaluator(TemplateId.SCHED, hhmm(9, 0))
    inputs = Inputs()
    inputs.events.append(evt("measurement", hhmm(9, 51), source="cuff"))
    values = step_values(inputs, 592)
    out = []
    guards = []
    for k in range(593):
        out.append(ev.step(k * STEP, values[k]))
        guards.append(ev.guard_failed)
    assert out[570] == -INF and out[580] == -INF
    assert (
        guards[570] == guards[580] == "no_measurement_after_tick"
    )  # the value is -inf because of the guard
    assert out[591] == -1_260_000.0 and out[592] == -1_260_000.0
    assert guards[591] is None  # a finite graded value is not a failed guard


def test_a_b0_value_is_defined_at_the_anchor_and_kept() -> None:
    inputs = Inputs()
    measure(inputs, hhmm(9, 0), 125.0)
    out = feed(evaluator(TemplateId.RANGE, hhmm(9, 0)), inputs, 543)
    assert out[539] is None and out[540] == 15.0 and out[543] == 15.0


def test_the_value_stays_none_while_a_position_is_open() -> None:
    """An undefined pressure (no sample): the instance value is not a number (05 section 3.5)."""
    inputs = Inputs()
    inputs.events.append(evt("measurement", hhmm(9, 0), source="cuff"))
    ev = evaluator(TemplateId.RANGE, hhmm(9, 0))
    assert feed(ev, inputs, 541)[540] is None


def test_robot_channel_marks_are_none_values_and_make_the_witness_open() -> None:
    ev = evaluator(TemplateId.INT, hhmm(21, 0))
    values = [
        {"intake": None, "presence": None, "dispense": 0.0, "auth": 0.0}
        for _ in range(1261)
    ]
    values[1260]["dispense"] = 1.0
    out = [ev.step(k * STEP, values[k]) for k in range(1261)]
    assert out[1260] is None  # lo = -inf < hi: not a point; the instance is undecidable
    ev2 = evaluator(TemplateId.INT, hhmm(21, 0))
    values[1260]["auth"] = 1.0
    out2 = [ev2.step(k * STEP, values[k]) for k in range(1261)]
    assert out2[1260] == 300_000.0


def test_the_pre_dose_value_is_the_bp_pre_of_the_anchor_step() -> None:
    ev = evaluator(TemplateId.RESP, hhmm(7, 0))
    base = {"meas": 0.0, "dispense": 0.0}
    out: list[float | None] = []
    for k in range(601):
        values: dict[str, float | None] = dict(base)
        if k >= 417:
            values["bp"] = 150.0
        if k == 420:
            values["dispense"] = 1.0
            values["bp_pre"] = 150.0
        if k >= 420:
            values["bp_pre"] = 150.0
        if k == 510:
            values["meas"] = 1.0
            values["bp"] = 132.0
        elif k > 510:
            values["bp"] = 132.0
        out.append(ev.step(k * STEP, values))
    assert out[599] is None and out[600] == 8.0


def test_without_bp_pre_the_held_pressure_of_the_anchor_step_is_used() -> None:
    ev = evaluator(TemplateId.RESP, hhmm(7, 0))
    out = []
    for k in range(601):
        values: dict[str, float | None] = {
            "meas": 1.0 if k == 510 else 0.0,
            "dispense": 1.0 if k == 420 else 0.0,
        }
        values["bp"] = 150.0 if k < 510 else 132.0
        out.append(ev.step(k * STEP, values))
    assert out[600] == 8.0


def test_a_missing_pre_dose_pressure_gives_no_value_unless_the_guard_failed() -> None:
    ev = evaluator(TemplateId.RESP, hhmm(7, 0))
    out = [
        ev.step(k * STEP, {"meas": 0.0, "dispense": 1.0 if k == 420 else 0.0})
        for k in range(601)
    ]
    assert (
        out[600] == -INF
    )  # no measurement in the window: the guard fails whatever the pre-dose value is
    assert ev.guard_failed == "obligation_unmet"


def test_count_limit_and_day_end_anchor_kinds() -> None:
    limit = evaluator(TemplateId.COUNT, hhmm(21, 2))
    out = [
        limit.step(
            k * STEP,
            {
                "dispense": 1.0 if k in (420, 1260, 1262) else 0.0,
                "dose_count": float(sum(k >= x for x in (420, 1260, 1262))),
            },
        )
        for k in range(1263)
    ]
    assert out[1262] == -1.0
    day_end = evaluator(TemplateId.COUNT, T_DAY, kind="day_end")
    out2 = [
        day_end.step(
            k * STEP,
            {
                "dispense": 1.0 if k == 420 else 0.0,
                "dose_count": 1.0 if k >= 420 else 0.0,
            },
        )
        for k in range(1441)
    ]
    assert out2[1439] is None and out2[1440] == -1.0
    with pytest.raises(m.MonitorConfigError):
        evaluator(TemplateId.RANGE, 0, kind="day_end")


def test_instances_do_not_share_state() -> None:
    a, b = (
        evaluator(TemplateId.SCHED, hhmm(9, 0)),
        evaluator(TemplateId.SCHED, hhmm(9, 0)),
    )
    for k in range(571):
        a.step(k * STEP, {"meas": 1.0 if k == 545 else 0.0})
        b.step(k * STEP, {"meas": 0.0})
    assert a.step(571 * STEP, {"meas": 0.0}) == 1_500_000.0
    assert b.step(571 * STEP, {"meas": 0.0}) == -INF


def test_the_unit_and_the_params_of_the_instance() -> None:
    ev = evaluator(TemplateId.RANGE, 0)
    assert ev.unit == BY_ID[TemplateId.RANGE].unit
    with pytest.raises(
        m.MonitorConfigError
    ):  # F0 has no override: the value cannot differ from the registry
        evaluator(TemplateId.RANGE, 0, params={"bp_band_low": 100.0})
    same = evaluator(TemplateId.RANGE, 0, params={"bp_band_low": 110.0})
    assert same.step(0, {"meas": 1.0, "bp": 125.0}) == 15.0


def test_steps_are_consecutive_from_zero() -> None:
    ev = evaluator(TemplateId.RANGE, 0)
    with pytest.raises(m.MonitorInputError):
        ev.step(STEP, {})  # step 0 first
    ev.step(0, {"meas": 1.0, "bp": 125.0})
    with pytest.raises(m.MonitorInputError):
        ev.step(2 * STEP, {})  # no gap
    with pytest.raises(m.MonitorInputError):
        ev.step(0, {})  # no repeat


PARAMS = oracle_params()
FORMULAS = oracle_formulas(LIB)


@SETTINGS
@given(scenarios(with_drops=False), st.integers(0, 330))
def test_the_point_evaluator_agrees_with_the_oracle_on_random_traces(
    scn: Scenario, cut: int
) -> None:
    """A defined value is the lower end of the closed instance; None where a position is open."""
    # two dispenses in one step share the global bp_pre stream: the per-instance capture differs
    steps = [(t + STEP - 1) // STEP for t in scn.dispenses]
    assume(len(set(steps)) == len(steps))
    trace = scn.to_trace()
    insts = oracle.make_instances(
        trace, PARAMS, sched_anchors=scn.ticks, day_end_anchors=scn.day_end_anchors()
    )
    inputs = scn.to_inputs()
    last = min(cut, 330)
    values = step_values(inputs, last)
    kinds = {
        "range": "measurement",
        "sys": "measurement",
        "hold": "dispense",
        "resp": "dispense",
        "int": "dispense",
    }
    for inst in insts:
        if inst.k_d > last or inst.act > last:
            continue
        kind = "day_end" if inst.day_end else None
        ev = m.make_point_evaluator(
            BY_ID[TemplateId(inst.template)],
            TemplateInstance(TemplateId(inst.template), inst.key, {}, inst.anchor_ms),
            REG,
            STEP,
            anchor_kind=kind or kinds.get(inst.template),
        )
        got: float | None = None
        for k in range(inst.k_d + 1):
            got = ev.step(k * STEP, values[k])
        grid = oracle.grid_for(trace, PARAMS, inst.k_d, [inst])
        lo, hi = oracle.interval(trace, PARAMS, FORMULAS, inst, inst.k_d, grid)
        if inst.template == "sched" or lo == hi:
            assert got == lo, (inst.key, got, lo, hi)
        else:
            assert got is None, (inst.key, got, lo, hi)
