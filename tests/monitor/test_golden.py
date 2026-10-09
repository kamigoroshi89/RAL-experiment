"""Golden replays (WS05-T04 tests 1 and 2 and the worked day of WS01-T08).

``templates.yaml``: 26 cases through ``make_point_evaluator``. ``verdicts.yaml``: 24 cases through
``StreamingMonitor`` with no forecaster (V-PRED-1 is checked for its measured part only; the
predicted state is WS05-T08). ``patient-day.yaml``: 32 records of one day. The golden copies under
``tests/fixtures/monitor`` must equal their sources.
"""

from __future__ import annotations

from typing import Any

import pytest

import ralmon.monitor as m
from ralmon.spec import CarePlan, TemplateId, TemplateInstance

from .helpers import (
    FIXTURES,
    GOLDEN_SOURCES,
    STEP,
    T_DAY,
    Inputs,
    at_step,
    close,
    drive,
    expect_record,
    golden_patient_day,
    golden_templates,
    golden_verdicts,
    inputs_of,
    load_f0,
    load_lib,
    make_config,
    make_plan,
    step_values,
)

REGISTRY = load_f0()
LIB = load_lib(REGISTRY)
BY_ID = {t.id: t for t in LIB}


# ---------------------------------------------------------------------------------------------
# the copies equal the golden sources
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("copy", "source"),
    [
        ("golden_templates.yaml", "templates.yaml"),
        ("golden_verdicts.yaml", "verdicts.yaml"),
        ("golden_patient_day.yaml", "patient-day.yaml"),
    ],
)
def test_fixture_copies_equal_the_golden_sources(copy: str, source: str) -> None:
    src = GOLDEN_SOURCES / source
    if not src.exists():  # the golden files are read-only inputs of the plan
        pytest.skip(f"{src} not present")
    assert (FIXTURES / copy).read_bytes() == src.read_bytes()


# ---------------------------------------------------------------------------------------------
# test 1: templates.yaml through make_point_evaluator
# ---------------------------------------------------------------------------------------------

TEMPLATE_CASES = golden_templates()


@pytest.mark.parametrize("case", TEMPLATE_CASES, ids=[c["id"] for c in TEMPLATE_CASES])
def test_point_robustness_matches_golden_templates(case: dict[str, Any]) -> None:
    c_in = case["inputs"]
    template = BY_ID[TemplateId(c_in["template"])]
    anchor_kind = c_in.get("anchor_kind")
    instance = TemplateInstance(
        template.id, f"{template.id.value}@{c_in['anchor_ms']}", {}, c_in["anchor_ms"]
    )
    evaluator = m.make_point_evaluator(
        template,
        instance,
        REGISTRY,
        STEP,
        anchor_kind=anchor_kind if anchor_kind in ("day_end",) else None,
    )
    k_eval = case["eval_at_ms"] // STEP
    values = step_values(inputs_of(c_in), k_eval)
    result: float | None = None
    for k in range(k_eval + 1):
        result = evaluator.step(k * STEP, values[k])
    want = case["expected"]["sigma_raw"]
    assert result is not None, case["id"]
    assert close(result, want), (case["id"], result, want)
    assert evaluator.guard_failed == case["expected"].get("guard_failed"), case["id"]
    assert evaluator.unit == template.unit


def test_template_golden_has_26_cases() -> None:
    assert len(TEMPLATE_CASES) == 26


# ---------------------------------------------------------------------------------------------
# test 2: verdicts.yaml through StreamingMonitor
# ---------------------------------------------------------------------------------------------

VERDICT_CASES = golden_verdicts()
STATIC = {"sched": TemplateId.SCHED, "count_end": TemplateId.COUNT}
KEY_OF = {
    "sched": "sched@{a}",
    "resp": "resp@{a}",
    "count_limit": "count@{a}",
    "count_end": "count@{a}",
    "int": "int@{a}",
}


def run_case(
    case: dict[str, Any], extra_steps: int = 0
) -> tuple[Any, list[Any], str, int]:
    d = case["fixture"]["reorder_delay_ms"]
    name = case["inputs"]["instance"]["template"]
    anchor = case["inputs"]["instance"]["anchor_ms"]
    plan = make_plan(
        REGISTRY,
        sched=[anchor] if name == "sched" else [],
        day_end=[anchor] if name == "count_end" else [],
    )
    mon = m.StreamingMonitor(make_config(REGISTRY, d_ms=d), REGISTRY, LIB)
    mon.load(plan)
    k_eval = (case["eval_at_ms"] - d) // STEP
    records = drive(mon, inputs_of(case["inputs"]), k_eval + extra_steps, d_ms=d)
    return mon, records, KEY_OF[name].format(a=anchor), k_eval


@pytest.mark.parametrize("case", VERDICT_CASES, ids=[c["id"] for c in VERDICT_CASES])
def test_monitor_records_match_golden_verdicts(case: dict[str, Any]) -> None:
    mon, records, key, k_eval = run_case(case)
    rec = at_step(records, key, k_eval * STEP)
    exp = case["expected"]
    if exp["state"] == "predicted_violation":
        # V-PRED-1: the predicted state needs a forecaster (WS05-T08); the measured prefix is PENDING
        # with the interval, the deadline and no decision of the record (05 section 5.2, P3)
        assert rec.state.value == "pending"
        assert rec.sigma_interval.lo == exp["sigma_interval"][0]
        assert close(rec.sigma_interval.hi, exp["sigma_interval"][1])
        assert close(rec.sigma_norm_interval[1], exp["sigma_norm_interval"][1])
        assert rec.pending_until_ms == exp["pending_until_ms"]
        assert rec.decided_at_ms is None and rec.rho is None
        return
    expect_record(rec, exp, case["id"])
    # the monitor time of emission is decided_at + D (the record of step k is returned by advance(t_k + D))
    if "emitted_at_monitor_ms" in exp:
        assert (
            exp["emitted_at_monitor_ms"]
            == k_eval * STEP + case["fixture"]["reorder_delay_ms"]
        )
    if "late_inputs" in exp:
        assert len(mon.late_inputs()) == exp["late_inputs"], case["id"]


def test_verdict_golden_has_24_cases() -> None:
    assert len(VERDICT_CASES) == 24


def test_v_late_1_the_late_sample_is_ignored_one_step_later() -> None:
    """05 section 9.4 item 6: push the late sample after the evaluation time, compare one step later."""
    case = next(c for c in VERDICT_CASES if c["id"] == "V-LATE-1")
    mon, records, key, k_eval = run_case(case, extra_steps=1)
    first = at_step(records, key, k_eval * STEP)
    later = at_step(records, key, (k_eval + 1) * STEP)
    assert first.state == later.state and first.decided_at_ms == later.decided_at_ms
    assert first.rho == later.rho and first.guard_failed == later.guard_failed
    # graded interval of a SCHED instance with no accepted measurement (05 section 9.4 item 6)
    assert later.sigma_interval.lo == float("-inf")
    assert later.sigma_interval.hi == -120_000.0
    assert len(mon.late_inputs()) == 1
    assert mon.late_inputs()[0].t_rx_ms == 34_240_000


def test_v_late_2_the_on_time_sample_is_accepted() -> None:
    case = next(c for c in VERDICT_CASES if c["id"] == "V-LATE-2")
    mon, _records, _key, _k = run_case(case, extra_steps=1)
    assert mon.late_inputs() == ()


# ---------------------------------------------------------------------------------------------
# the worked day: 32 records
# ---------------------------------------------------------------------------------------------

DAY = golden_patient_day()


def day_plan() -> CarePlan:
    static = [
        TemplateInstance(
            TemplateId(i["template"]), i["instance_key"], {}, i["anchor_ms"]
        )
        for i in DAY["plan"]["static_instances"]
    ]
    return CarePlan(
        care_plan_id=DAY["plan"]["care_plan_id"],
        pathway_template_id=DAY["plan"]["pathway_template_id"],
        patient_id=DAY["plan"]["patient_id"],
        registry_version=REGISTRY.version(),  # the golden pins "F0 (fixture, ADR-027)": a label
        instances=tuple(static),
        schedule=tuple(x["t_ms"] for x in DAY["plan"]["schedule"]),
        plan_version=DAY["plan"]["plan_version"],
        signature=None,
    )


@pytest.fixture(scope="module")
def day_records() -> list[Any]:
    mon = m.StreamingMonitor(make_config(REGISTRY), REGISTRY, LIB)
    mon.load(day_plan())
    inputs = inputs_of(DAY["observed_day"])
    return drive(mon, inputs, T_DAY // STEP)


@pytest.mark.parametrize(
    "golden", DAY["records"], ids=[r["id"] for r in DAY["records"]]
)
def test_monitor_reproduces_worked_day_record(
    golden: dict[str, Any], day_records: list[Any]
) -> None:
    rec = at_step(day_records, golden["instance_key"], golden["eval_at_ms"])
    exp = golden["expected"]
    assert rec.template.value == exp["template"]
    if exp["state"] == "predicted_violation":
        # PD-REC-11: the forecast is WS05-T08; the measured record is PENDING with the same interval
        assert rec.state.value == "pending"
        assert close(rec.sigma_interval.hi, exp["sigma_interval"][1])
        assert rec.sigma_interval.lo == exp["sigma_interval"][0]
        assert rec.pending_until_ms == exp["pending_until_ms"]
        return
    expect_record(rec, exp, golden["id"])


def test_worked_day_has_32_records_and_the_monitor_decides_exactly_the_golden_instances(
    day_records: list[Any],
) -> None:
    assert len(DAY["records"]) == 32
    want: dict[str, tuple[str, int]] = {}
    for g in DAY["records"]:
        e = g["expected"]
        if e["state"] in ("violated", "satisfied"):
            want[g["instance_key"]] = (e["state"], e["decided_at_ms"])
    got: dict[str, tuple[str, int]] = {}
    for r in day_records:
        if r.state.value in ("violated", "satisfied") and r.instance_key not in got:
            assert r.decided_at_ms is not None
            got[r.instance_key] = (r.state.value, r.decided_at_ms)
    assert got == want
    # every instance of the monitor is an instance of the golden (nothing is created that the day lacks)
    assert {r.instance_key for r in day_records} == {
        g["instance_key"] for g in DAY["records"]
    }


def test_worked_day_definitive_records_never_change_state(
    day_records: list[Any],
) -> None:
    final_state: dict[str, tuple[str, int | None, Any]] = {}
    for r in day_records:
        triple = (r.state.value, r.decided_at_ms, r.rho)
        if r.instance_key in final_state and final_state[r.instance_key][0] in (
            "violated",
            "satisfied",
        ):
            assert final_state[r.instance_key] == triple, r.instance_key
        final_state[r.instance_key] = triple


def test_golden_inputs_hold_no_ground_truth() -> None:
    """The replay feeds only ``samples``, ``events`` and the availability marks (ground-truth discipline)."""
    assert Inputs is not None
    assert set(DAY["observed_day"]) == {
        "patient_id",
        "day_index",
        "seed",
        "care_plan_id",
        "samples",
        "events",
        "channels_unavailable",
    }
