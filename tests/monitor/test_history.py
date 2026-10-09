"""The ``history`` input of ``run_offline`` (WS05-T10, ADR-046, ADR-053 (h)).

The earlier days of a patient are replayed first on the continuing axis (``day_index * T_day + clock
time``), the records of the steps before the first step of the day are not returned, and the state that
crosses midnight (the trailing 24 h counter, the held pressure and the measurement look-back, the
instances whose window ends after the closing step) carries into the day. The two-day cases are hand
computed in ``tests/fixtures/monitor/golden_history.yaml`` (registry F0, FIXTURE-ONLY, ``step_ms = 60000``).
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import re
from typing import Any

import pytest
from hypothesis import given

import ralmon.monitor as m
from ralmon.monitor import offline
from ralmon.signals import Event, Sample

from .helpers import (
    FIXTURES,
    INTERFACES,
    K_DAY,
    STEP,
    T_DAY,
    LocalDay,
    close,
    events_of,
    evt,
    golden_patient_day,
    golden_verdicts,
    hhmm,
    load_f0,
    load_lib,
    make_config,
    make_plan,
    read_yaml,
    samples_of,
    smp,
)
from .scenarios import SETTINGS, Scenario, scenarios
from .test_field_fuzz import Leaks, pool, tampered

REG = load_f0()
LIB = load_lib(REG)
CFG = make_config(REG)
CASES = read_yaml(FIXTURES / "golden_history.yaml")["cases"]
BY_ID = {c["id"]: c for c in CASES}


def run(
    day: Any,
    plan: Any,
    history: Any = None,
    config: Any = CFG,
    *,
    detailed: bool = False,
) -> Any:
    fn = m.run_offline_detailed if detailed else m.run_offline
    kwargs: dict[str, Any] = {"registry": REG, "templates": LIB}
    if history is not None:
        kwargs["history"] = history
    return fn(day, plan, config, None, None, **kwargs)


def days_of(case: dict[str, Any]) -> list[LocalDay]:
    return [
        LocalDay(samples_of(d), events_of(d), day_index=d["day_index"])
        for d in case["days"]
    ]


def plan_of(case: dict[str, Any]) -> Any:
    return make_plan(REG, sched=case["plan"]["sched"], day_end=case["plan"]["day_end"])


def run_case(case: dict[str, Any], *, with_history: bool) -> Any:
    days = days_of(case)
    day = days[case["run_day"]]
    history = days[: case["run_day"]] if with_history else ()
    return run(day, plan_of(case), history)


def records_of(records: Any, key: str, t_eval_ms: int | None = None) -> list[Any]:
    return [
        r
        for r in records
        if r.instance_key == key and (t_eval_ms is None or r.t_eval_ms == t_eval_ms)
    ]


def check_record(rec: Any, want: dict[str, Any], label: str) -> None:
    assert rec.state.value == want["state"], (label, rec.state)
    lo, hi = want["sigma_interval"]
    assert close(rec.sigma_interval.lo, float(lo)), (label, rec.sigma_interval)
    assert close(rec.sigma_interval.hi, float(hi)), (label, rec.sigma_interval)
    assert rec.decided_at_ms == want["decided_at_ms"], (label, rec.decided_at_ms)
    assert rec.pending_until_ms == want["pending_until_ms"], (
        label,
        rec.pending_until_ms,
    )
    assert rec.guard_failed == want["guard_failed"], (label, rec.guard_failed)


def check_expected(case: dict[str, Any], *, with_history: bool) -> None:
    records = run_case(case, with_history=with_history)
    mode = "with_history" if with_history else "without_history"
    for exp in case["expected"]:
        if mode not in exp:
            continue
        label = f"{case['id']} {exp['key']} {mode}"
        want = exp[mode]
        if want is None:
            assert records_of(records, exp["key"]) == [], label
            continue
        found = records_of(records, exp["key"], exp["t_eval_ms"])
        assert len(found) == 1, (label, len(found))
        check_record(found[0], want, label)


# ---------------------------------------------------------------------------------------------
# test 1
# ---------------------------------------------------------------------------------------------


def test_no_history_is_the_present_behaviour() -> None:
    golden = golden_patient_day()
    day = LocalDay(
        samples_of(golden["observed_day"]), events_of(golden["observed_day"])
    )
    static = [
        (i["template"], i["instance_key"], i["anchor_ms"])
        for i in golden["plan"]["static_instances"]
    ]
    from ralmon.spec import CarePlan, TemplateId, TemplateInstance

    plan = CarePlan(
        "PD-1-plan",
        "hypertension-fixture",
        "PD-1-patient",
        REG.version(),
        tuple(TemplateInstance(TemplateId(t), k, {}, a) for t, k, a in static),
        (),
        1,
        None,
    )
    for d_ms in (0, 30_000):
        config = make_config(REG, d_ms=d_ms)
        without = run(day, plan, None, config)
        assert len(without) > 1000
        for empty in ((), []):
            assert run(day, plan, empty, config) == without
        detailed = run(day, plan, (), config, detailed=True)
        assert detailed.records == without
        assert detailed == run(day, plan, None, config, detailed=True)


def test_no_history_is_the_present_behaviour_on_the_golden_verdict_inputs() -> None:
    for case in golden_verdicts():
        inputs = case["inputs"]
        if inputs.get("channels_unavailable") or inputs.get("forecast"):
            continue
        day = LocalDay(samples_of(inputs), events_of(inputs))
        plan = make_plan(REG)
        assert run(day, plan, ()) == run(day, plan)


@SETTINGS
@given(scenarios())
def test_no_history_is_the_present_behaviour_on_random_days(scn: Scenario) -> None:
    inputs = scn.to_inputs()
    day = LocalDay(tuple(inputs.samples), tuple(inputs.events))
    plan = make_plan(REG, sched=scn.ticks, day_end=scn.day_end_anchors())
    assert run(day, plan, ()) == run(day, plan)


# ---------------------------------------------------------------------------------------------
# tests 2, 4, 5, 6: the hand-computed two-day cases
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("case_id", ["H-W6", "H-W6-MORNING"])
def test_w6_counter_across_midnight(case_id: str) -> None:
    case = BY_ID[case_id]
    check_expected(case, with_history=True)
    check_expected(case, with_history=False)
    key = "count@111600000"
    with_h = records_of(run_case(case, with_history=True), key)
    without = records_of(run_case(case, with_history=False), key)
    assert [r.state for r in with_h] == [m.VerdictState.VIOLATED]
    assert [r.state for r in without] == [m.VerdictState.SATISFIED]


def test_no_record_before_the_day_is_returned() -> None:
    plan = make_plan(
        REG,
        sched=[hhmm(9, 0), T_DAY + hhmm(9, 0), 2 * T_DAY + hhmm(9, 0)],
        day_end=[T_DAY, 2 * T_DAY, 3 * T_DAY],
    )
    history = [
        LocalDay(
            [smp("bp", hhmm(8, 0), 130.0), smp("bp", hhmm(20, 0), 135.0)],
            [
                evt("measurement", hhmm(8, 0)),
                evt("dispense", hhmm(20, 0), source="dispenser"),
            ],
            day_index=0,
        ),
        LocalDay(
            [smp("bp", T_DAY + hhmm(8, 0), 128.0)],
            [
                evt("measurement", T_DAY + hhmm(8, 0)),
                evt("dispense", T_DAY + hhmm(23, 0), source="dispenser"),
            ],
            day_index=1,
        ),
    ]
    day = LocalDay(
        [smp("bp", 2 * T_DAY + hhmm(7, 0), 140.0)],
        [
            evt("measurement", 2 * T_DAY + hhmm(7, 0)),
            evt("dispense", 2 * T_DAY + hhmm(7, 1), source="dispenser"),
        ],
        day_index=2,
    )
    result = run(day, plan, history, detailed=True)
    first = 2 * K_DAY * STEP
    assert result.records
    assert min(r.t_eval_ms for r in result.records) >= first
    assert max(r.t_eval_ms for r in result.records) <= 3 * T_DAY
    # the run itself starts at the first history step and finalises the whole axis
    assert result.stats.steps_finalised == 3 * K_DAY + 1
    assert result.stats.plan_instances_before_start == 0
    assert result.rejected_inputs == ()
    assert result.stats.accepted_count == 10  # 4 + 3 + 3 samples and events
    # a record of the dispense of the evening of day 1 (decided in day 2) is there, with its anchor in day 1
    assert records_of(result.records, f"resp@{T_DAY + hhmm(23, 0)}")


def test_instances_anchored_in_history_days_are_part_of_the_run() -> None:
    plan = make_plan(
        REG, sched=[hhmm(9, 0), T_DAY + hhmm(9, 0), 2 * T_DAY + hhmm(9, 0)]
    )
    hist = [LocalDay([], [], day_index=0), LocalDay([], [], day_index=1)]
    day = LocalDay([], [], day_index=2)
    full = run(day, plan, hist, detailed=True)
    assert full.stats.plan_instances_before_start == 0
    only_last = run(day, plan, hist[1:], detailed=True)
    assert only_last.stats.plan_instances_before_start == 1  # the tick of day 0
    none = run(day, plan, (), detailed=True)
    assert none.stats.plan_instances_before_start == 2
    # whatever the length of the history, the instance of the day itself gives the same records
    key = f"sched@{2 * T_DAY + hhmm(9, 0)}"
    assert records_of(full.records, key) == records_of(none.records, key)
    assert records_of(only_last.records, key) == records_of(none.records, key)
    assert records_of(full.records, key)
    assert records_of(
        full.records, f"sched@{T_DAY + hhmm(9, 0)}"
    )  # the tick of day 1 is part of the run
    assert records_of(none.records, f"sched@{T_DAY + hhmm(9, 0)}") == []


def test_resp_window_across_midnight_is_decided_in_the_next_day() -> None:
    case = BY_ID["H-RESP-MIDNIGHT"]
    check_expected(case, with_history=True)
    check_expected(case, with_history=False)
    days = days_of(case)
    plan = plan_of(case)
    key = "resp@79200000"
    # day 0 alone: the window ends at 01:00 of day 1, the instance stays PENDING (never a violation)
    alone = run(days[0], plan)
    states = {r.state for r in records_of(alone, key)}
    assert states == {m.VerdictState.PENDING}
    assert records_of(alone, key)[-1].t_eval_ms == T_DAY
    # day 1 with history: the VIOLATED record is at 01:00 of day 1, the anchor is in day 0
    with_h = records_of(run(days[1], plan, days[:1]), key)
    violated = [r for r in with_h if r.state is m.VerdictState.VIOLATED]
    assert [r.t_eval_ms for r in violated] == [T_DAY + hhmm(1, 0)]
    assert violated[0].decided_at_ms == T_DAY + hhmm(1, 0)
    assert 79_200_000 < T_DAY  # the anchor lies before the first step of the day


def test_held_pressure_and_lookback_cross_midnight() -> None:
    case = BY_ID["H-HOLD-LOOKBACK"]
    check_expected(case, with_history=True)
    check_expected(case, with_history=False)
    days = days_of(case)
    without = records_of(run(days[1], plan_of(case)), "hold@88200000")
    assert [r.guard_failed for r in without] == ["no_recent_measurement"]
    with_h = records_of(run(days[1], plan_of(case), days[:1]), "hold@88200000")
    assert [r.guard_failed for r in with_h] == [None]
    # the 23:50 reading is the pre-dose value of the response instance
    resp = records_of(
        run(days[1], plan_of(case), days[:1]), "resp@88200000", 88_200_000
    )
    assert resp[0].sigma_interval.hi == pytest.approx(120.0 - 50.0 - 10.0)


def test_the_day_end_count_of_the_previous_day_is_decided_once() -> None:
    case = BY_ID["H-DAYEND-ONCE"]
    check_expected(case, with_history=True)
    days = days_of(case)
    plan = plan_of(case)
    key = "count@86400000"
    own = records_of(run(days[0], plan), key)  # the run of its own day
    definitive = [r for r in own if r.state is not m.VerdictState.PENDING]
    assert [(r.t_eval_ms, r.state) for r in definitive] == [
        (T_DAY, m.VerdictState.VIOLATED)
    ]
    assert definitive[0].sigma_interval.lo == -2.0
    nxt = run(days[1], plan, days[:1])
    assert records_of(nxt, key) == []
    # the obligation of the day that is run is still there
    assert records_of(nxt, "count@172800000", 2 * T_DAY)


# ---------------------------------------------------------------------------------------------
# test 7: validation
# ---------------------------------------------------------------------------------------------


def good_day(index: int, **kwargs: Any) -> LocalDay:
    return LocalDay([], [], day_index=index, **kwargs)


def raises_input_error(history: Any, day: Any = None) -> None:
    day = good_day(3) if day is None else day
    for detailed in (False, True):
        with pytest.raises(m.MonitorInputError, match="history") as info:
            run(day, make_plan(REG), history, detailed=detailed)
        assert type(info.value) is m.MonitorInputError


def test_history_is_validated() -> None:
    raises_input_error([good_day(0, patient_id="another-patient")])  # another patient
    raises_input_error([good_day(0), good_day(1, patient_id="another-patient")])
    raises_input_error([good_day(3)])  # not smaller than day.day_index
    raises_input_error([good_day(4)])
    raises_input_error([good_day(1), good_day(0)])  # not increasing
    raises_input_error([good_day(1), good_day(1)])
    raises_input_error([good_day(0), good_day(2), good_day(2)])
    raises_input_error([good_day(0), good_day(5)])  # the last one is after the day
    too_long = offline.MAX_HISTORY_DAYS + 1
    raises_input_error(
        [good_day(i) for i in range(too_long)], good_day(too_long)
    )  # longer than the named bound
    raises_input_error([good_day(0)], good_day(too_long + 7))  # the span, not the count
    for item in (object(), None, 5, "day", {"day_index": 0}, 1.5, [], (good_day(0),)):
        raises_input_error([item])
        raises_input_error([good_day(0), item])
    for history in (5, None.__class__, object(), 1.5):
        raises_input_error(history)
    with pytest.raises(m.MonitorInputError, match="history"):
        m.run_offline(
            good_day(3),
            make_plan(REG),
            CFG,
            None,
            None,
            registry=REG,
            templates=LIB,
            history=None,
        )  # type: ignore[arg-type]
    # a bad day index of an item
    for bad in (-1, True, 1.5, None, "1", 2**70):
        item = good_day(0)
        object.__setattr__(item, "day_index", bad)
        raises_input_error([item])


def test_history_at_the_named_bound_is_accepted() -> None:
    n = offline.MAX_HISTORY_DAYS
    history = [good_day(i) for i in range(n)]
    result = run(good_day(n), make_plan(REG), history, detailed=True)
    assert result.stats.steps_finalised == (n + 1) * K_DAY + 1


def test_history_is_validated_before_the_run_starts() -> None:
    """A bad history is refused whole: nothing of it is replayed (the error is raised at once)."""
    big = [good_day(0), object()]
    with pytest.raises(m.MonitorInputError, match="history"):
        run(good_day(3), make_plan(REG), big)


def test_history_is_read_through_a_bounded_iterator() -> None:
    class Endless:
        def __iter__(self) -> Any:
            while True:
                yield good_day(0)

    with pytest.raises(m.MonitorInputError, match="history"):
        run(good_day(3), make_plan(REG), Endless())


# ---------------------------------------------------------------------------------------------
# test 8: the continuing axis
# ---------------------------------------------------------------------------------------------


def test_history_days_are_on_the_continuing_axis() -> None:
    """A history day written on the per-day axis is reported as rejected inputs, as a day is today."""
    per_day = LocalDay(
        [smp("bp", hhmm(7, 0), 150.0)],
        [evt("measurement", hhmm(7, 0), source="cuff")],
        day_index=1,  # the times are those of day 0
    )
    day = LocalDay([], [], day_index=2)
    result = run(day, make_plan(REG), [per_day], detailed=True)
    assert result.stats.accepted_count == 0
    assert result.stats.after_finalisation_count == 2
    assert [r.reason for r in result.rejected_inputs] == ["finalised", "finalised"]
    # the same day, written on the continuing axis, is used
    right = LocalDay(
        [smp("bp", T_DAY + hhmm(7, 0), 150.0)],
        [evt("measurement", T_DAY + hhmm(7, 0), source="cuff")],
        day_index=1,
    )
    used = run(day, make_plan(REG), [right], detailed=True)
    assert used.stats.accepted_count == 2 and used.rejected_inputs == ()


def test_the_day_itself_on_the_per_day_axis_is_still_reported_with_a_history() -> None:
    per_day = LocalDay(
        [smp("bp", hhmm(7, 0), 150.0)],
        [evt("measurement", hhmm(7, 0), source="cuff")],
        day_index=2,
    )
    result = run(per_day, make_plan(REG), [good_day(1)], detailed=True)
    assert result.stats.accepted_count == 0
    assert [r.reason for r in result.rejected_inputs] == ["finalised", "finalised"]


# ---------------------------------------------------------------------------------------------
# test 9
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("case_id", [c["id"] for c in CASES])
def test_detailed_run_agrees(case_id: str) -> None:
    case = BY_ID[case_id]
    days = days_of(case)
    day = days[case["run_day"]]
    history = days[: case["run_day"]]
    plan = plan_of(case)
    plain = run(day, plan, history)
    detailed = run(day, plan, history, detailed=True)
    assert detailed.records == plain
    assert len(plain) > 0
    assert run(day, plan, history) == plain  # deterministic


# ---------------------------------------------------------------------------------------------
# test 10
# ---------------------------------------------------------------------------------------------


def contract_signature() -> list[tuple[str, str, str | None]]:
    text = INTERFACES.read_text(encoding="utf-8")
    block = re.search(r"def run_offline\(.*?\) -> [^\n]*: \.\.\.", text, re.DOTALL)
    assert block is not None
    func = ast.parse(block.group(0)).body[0]
    assert isinstance(func, ast.FunctionDef)
    a = func.args
    out: list[tuple[str, str, str | None]] = []
    n_plain = len(a.args) - len(a.defaults)
    for i, arg in enumerate(a.args):
        default = None if i < n_plain else ast.unparse(a.defaults[i - n_plain])
        out.append((arg.arg, "POSITIONAL_OR_KEYWORD", default))
    for arg, default_node in zip(a.kwonlyargs, a.kw_defaults, strict=True):
        default = None if default_node is None else ast.unparse(default_node)
        out.append((arg.arg, "KEYWORD_ONLY", default))
    return out


def test_contract_signature() -> None:
    want = contract_signature()
    assert [n for n, _k, _d in want][-1] == "history"
    for fn in (m.run_offline, m.run_offline_detailed):
        got = [
            (
                p.name,
                p.kind.name,
                None if p.default is inspect.Parameter.empty else repr(p.default),
            )
            for p in inspect.signature(fn).parameters.values()
        ]
        assert got == want, fn.__name__


# ---------------------------------------------------------------------------------------------
# test 11: hostile history
# ---------------------------------------------------------------------------------------------


def hostile_days() -> tuple[LocalDay, list[LocalDay], Any]:
    """The day 2 and a two-day history of a patient, with a few inputs in each, and the plan."""
    history = [
        LocalDay(
            [smp("bp", hhmm(8, 0), 130.0)],
            [evt("measurement", hhmm(8, 0), source="cuff")],
            day_index=0,
        ),
        LocalDay(
            [smp("bp", T_DAY + hhmm(8, 0), 128.0)],
            [evt("dispense", T_DAY + hhmm(8, 5), source="dispenser")],
            day_index=1,
        ),
    ]
    day = LocalDay(
        [smp("bp", 2 * T_DAY + 60_000, 120.0)],
        [evt("measurement", 2 * T_DAY + 60_000)],
        day_index=2,
    )
    return day, history, make_plan(REG, sched=[2 * T_DAY + hhmm(9, 0)])


def test_hostile_history_raises_only_named_errors() -> None:
    day, history, plan = hostile_days()
    assert run(day, plan, history)  # the well-formed history is accepted and replayed
    leaks = Leaks()

    def go(label: str, hist: Any, both: bool = False) -> None:
        # both entry points share one implementation: the field loops use the detailed one only
        entries = (
            (m.run_offline, m.run_offline_detailed)
            if both
            else (m.run_offline_detailed,)
        )
        for fn in entries:
            leaks.run(
                f"{fn.__name__}[{label}]",
                fn,
                day,
                plan,
                CFG,
                None,
                None,
                registry=REG,
                templates=LIB,
                history=hist,
            )

    for value in pool():
        go("history=v", value, both=True)
        go("history=[v]", [value], both=True)
        go("history=[good, v]", [history[0], value], both=True)
        go("history=[v, good]", [value, history[1]], both=True)
        go("history=[good, good, v]", [*history, value], both=True)
    for position in range(2):
        for f in dataclasses.fields(LocalDay):
            for value in pool():
                bad = list(history)
                bad[position] = tampered(history[position], f.name, value)
                go(f"history[{position}].{f.name}", bad)
        for f in dataclasses.fields(Sample):
            for value in pool():
                bad_sample = tampered(
                    smp("bp", T_DAY * position + STEP, 120.0), f.name, value
                )
                bad = list(history)
                bad[position] = LocalDay([bad_sample], [], day_index=position)
                go(f"history[{position}].sample.{f.name}", bad)
        for f in dataclasses.fields(Event):
            for value in pool():
                bad_event = tampered(
                    evt("measurement", T_DAY * position + STEP), f.name, value
                )
                bad = list(history)
                bad[position] = LocalDay([], [bad_event], day_index=position)
                go(f"history[{position}].event.{f.name}", bad)
    for value in pool():
        bad = list(history)
        bad[0] = LocalDay([value], [], day_index=0)
        go("history[0].samples=[v]", bad)
        bad[0] = LocalDay([], [value], day_index=0)
        go("history[0].events=[v]", bad)
    # the day that is run, with a history
    for f in dataclasses.fields(LocalDay):
        for value in pool():
            for fn in (m.run_offline, m.run_offline_detailed):
                leaks.run(
                    f"{fn.__name__}[day.{f.name}] with history",
                    fn,
                    tampered(day, f.name, value),
                    plan,
                    CFG,
                    None,
                    None,
                    registry=REG,
                    templates=LIB,
                    history=history,
                )
    leaks.check()
