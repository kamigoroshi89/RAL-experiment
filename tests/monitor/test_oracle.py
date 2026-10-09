"""The independent oracle of ``tests/fixtures/monitor/oracle.py`` against the golden files (WS05-T04).

The oracle shares no code with ``ralmon.monitor``. Before it is trusted for the soundness tests it must
reproduce the golden files by itself: 26 template cases, 24 verdict cases (the three predictive ones
only for the measured interval), 32 records of the worked day. Counts are asserted so that a silently
skipped case cannot pass.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from tests.fixtures.monitor import oracle

from .helpers import (
    STEP,
    T_DAY,
    close,
    golden_patient_day,
    golden_templates,
    golden_verdicts,
    load_f0,
    load_lib,
)
from .scenarios import oracle_formulas, oracle_params

PARAMS = oracle_params()
FORMULAS = oracle_formulas(load_lib(load_f0()))


def trace_of(
    inputs: dict[str, Any], *, accept_until_rx: dict[str, int] | None = None
) -> oracle.Trace:
    """The accepted trace of a golden case; ``accept_until_rx`` maps (device time) to a lateness cut."""
    trace = oracle.Trace(STEP)
    d = (accept_until_rx or {}).get("D", 0)
    for s in inputs.get("samples", []):
        if s["t_rx_ms"] <= ((s["t_device_ms"] + STEP - 1) // STEP) * STEP + d:
            trace.samples.append((s["signal"], s["t_device_ms"], float(s["value"])))
    for e in inputs.get("events", []):
        if e["t_rx_ms"] <= ((e["t_device_ms"] + STEP - 1) // STEP) * STEP + d:
            trace.events.append((e["kind"], e["t_device_ms"]))
    for c in inputs.get("channels_unavailable") or []:
        if isinstance(
            c, str
        ):  # templates.yaml: the channel is unavailable for the whole day
            trace.unavailable.setdefault(c, []).append((0, T_DAY // STEP))
        else:
            trace.unavailable.setdefault(c["signal"], []).append(
                (c["from_ms"] // STEP, c["to_ms"] // STEP)
            )
    return trace


def pick(
    trace: oracle.Trace,
    template: str,
    anchor: int,
    *,
    sched: list[int],
    day_end: list[int],
) -> oracle.Inst:
    insts = oracle.make_instances(
        trace, PARAMS, sched_anchors=sched, day_end_anchors=day_end
    )
    found = [
        i
        for i in insts
        if i.template == template
        and i.anchor_ms == anchor
        and (i.conjunct == 1) == bool(day_end)
    ]
    assert len(found) == 1, (template, anchor, [(i.key) for i in insts])
    return found[0]


def check_lateness_free(case: dict[str, Any]) -> bool:
    return True


# ---------------------------------------------------------------------------------------------
# templates.yaml: 26 cases, point robustness at eval_at_ms
# ---------------------------------------------------------------------------------------------

TEMPLATE_CASES = golden_templates()


@pytest.mark.parametrize("case", TEMPLATE_CASES, ids=[c["id"] for c in TEMPLATE_CASES])
def test_oracle_reproduces_golden_template_case(case: dict[str, Any]) -> None:
    inputs = case["inputs"]
    trace = trace_of(inputs)
    template = inputs["template"]
    anchor = inputs["anchor_ms"]
    k = case["eval_at_ms"] // STEP
    day_end = [anchor] if inputs.get("anchor_kind") == "day_end" else []
    sched = [anchor] if template == "sched" else []
    inst = pick(trace, template, anchor, sched=sched, day_end=day_end)
    grid = oracle.grid_for(trace, PARAMS, k, [inst])
    lo, hi = oracle.interval(trace, PARAMS, FORMULAS, inst, k, grid)
    want = case["expected"]["sigma_raw"]
    # the instance value is the lower end once the decision window is closed (05 section 2.3)
    assert close(lo, want), (case["id"], lo, hi, want)


def test_template_case_count() -> None:
    assert len(TEMPLATE_CASES) == 26


# ---------------------------------------------------------------------------------------------
# verdicts.yaml: 24 cases, interval and state at eval_at_ms
# ---------------------------------------------------------------------------------------------

VERDICT_CASES = golden_verdicts()
KINDS = {
    "sched": "sched",
    "resp": "resp",
    "count_limit": "count",
    "count_end": "count",
    "int": "int",
}


def verdict_instance(
    case: dict[str, Any],
) -> tuple[oracle.Trace, oracle.Inst, int, int]:
    inputs = case["inputs"]
    d = case["fixture"]["reorder_delay_ms"]
    trace = trace_of(inputs, accept_until_rx={"D": d})
    name = inputs["instance"]["template"]
    anchor = inputs["instance"]["anchor_ms"]
    inst = pick(
        trace,
        KINDS[name],
        anchor,
        sched=[anchor] if name == "sched" else [],
        day_end=[anchor] if name == "count_end" else [],
    )
    k = (case["eval_at_ms"] - d) // STEP
    return trace, inst, k, d


@pytest.mark.parametrize("case", VERDICT_CASES, ids=[c["id"] for c in VERDICT_CASES])
def test_oracle_reproduces_golden_verdict_case(case: dict[str, Any]) -> None:
    trace, inst, k, _d = verdict_instance(case)
    exp = case["expected"]
    lo, hi = oracle.interval(
        trace, PARAMS, FORMULAS, inst, k, oracle.grid_for(trace, PARAMS, k, [inst])
    )
    assert close(lo, exp["sigma_interval"][0]), (case["id"], lo, hi)
    assert close(hi, exp["sigma_interval"][1]), (case["id"], lo, hi)
    state = oracle.classify(lo, hi, k, inst.k_d)
    if exp["state"] == "predicted_violation":
        assert (
            state == "pending"
        )  # the measured prefix of a predicted record is PENDING (P3)
        return
    assert state == exp["state"], (case["id"], state)
    if state == "pending":
        assert exp["decided_at_ms"] is None
        return
    # the first deciding step is the one the golden gives: not decided one step before
    decided = exp["decided_at_ms"] // STEP
    if decided > inst.act:
        lo2, hi2 = oracle.interval(
            trace,
            PARAMS,
            FORMULAS,
            inst,
            decided - 1,
            oracle.grid_for(trace, PARAMS, decided - 1, [inst]),
        )
        assert oracle.classify(lo2, hi2, decided - 1, inst.k_d) == "pending", (
            case["id"],
            lo2,
            hi2,
        )
    lo3, hi3 = oracle.interval(
        trace,
        PARAMS,
        FORMULAS,
        inst,
        decided,
        oracle.grid_for(trace, PARAMS, decided, [inst]),
    )
    assert oracle.classify(lo3, hi3, decided, inst.k_d) == exp["state"]


def test_verdict_case_count() -> None:
    assert len(VERDICT_CASES) == 24


# ---------------------------------------------------------------------------------------------
# patient-day.yaml: 32 records
# ---------------------------------------------------------------------------------------------

DAY = golden_patient_day()
DAY_TRACE = trace_of(DAY["observed_day"])
SCHED_ANCHORS = [
    int(i["anchor_ms"])
    for i in DAY["plan"]["static_instances"]
    if i["template"] == "sched"
]
DAY_INSTANCES = {
    i.key: i
    for i in oracle.make_instances(
        DAY_TRACE, PARAMS, sched_anchors=SCHED_ANCHORS, day_end_anchors=[T_DAY]
    )
}


@pytest.mark.parametrize("rec", DAY["records"], ids=[r["id"] for r in DAY["records"]])
def test_oracle_reproduces_patient_day_record(rec: dict[str, Any]) -> None:
    inst = DAY_INSTANCES[rec["instance_key"]]
    k = rec["eval_at_ms"] // STEP
    exp = rec["expected"]
    lo, hi = oracle.interval(
        DAY_TRACE,
        PARAMS,
        FORMULAS,
        inst,
        k,
        oracle.grid_for(DAY_TRACE, PARAMS, k, [inst]),
    )
    assert close(lo, exp["sigma_interval"][0]), (rec["id"], lo, hi)
    assert close(hi, exp["sigma_interval"][1]), (rec["id"], lo, hi)
    state = oracle.classify(lo, hi, k, inst.k_d)
    if exp["state"] == "predicted_violation":
        assert state == "pending"
    else:
        assert state == exp["state"], (rec["id"], state)


def test_patient_day_record_count() -> None:
    assert len(DAY["records"]) == 32
    assert set(DAY_INSTANCES) >= {r["instance_key"] for r in DAY["records"]}


# ---------------------------------------------------------------------------------------------
# properties of the oracle itself
# ---------------------------------------------------------------------------------------------


def test_oracle_intervals_are_ordered_and_never_nan_on_the_worked_day() -> None:
    for key, inst in DAY_INSTANCES.items():
        for k in {inst.act, inst.k_a, inst.k_d, min(inst.horizon, 700)}:
            lo, hi = oracle.interval(
                DAY_TRACE,
                PARAMS,
                FORMULAS,
                inst,
                k,
                oracle.grid_for(DAY_TRACE, PARAMS, k, [inst]),
            )
            assert not math.isnan(lo) and not math.isnan(hi), key
            assert lo <= hi, (key, k, lo, hi)


def test_oracle_parser_reads_every_library_formula() -> None:
    for name, text in FORMULAS.items():
        root = oracle.parse(text)
        assert root.op in ("hist", "and"), name
        assert oracle.body_of(text).op in ("and", "cmp", "once", "ind"), name
    assert oracle.body_of(FORMULAS["count"], 1).op == "cmp"


def test_oracle_rejects_an_unaligned_window() -> None:
    bad = oracle.Params({**PARAMS.values, "hold_lookback": 90_500.0}, 50.0, 250.0, STEP)
    trace = oracle.Trace(STEP, events=[("dispense", 0)])
    inst = oracle.Inst("hold", "hold@0", 0, 0, 0, 0, act=0)
    with pytest.raises(AssertionError):
        oracle.interval(trace, bad, FORMULAS, inst, 0)
