"""Test 30 of WS05-T04: the RTAMT oracle, conditional on the outcome of the spike of ADR-013.

ADR-013 records outcome C (WS05-T02, ``docs/plan/workstreams/WS05-monitor/rtamt-spike.md``): RTAMT
cannot host the templates (the term ``age``, the equality atom, the unavailable channel), the
evaluator is custom and RTAMT is neither an engine nor an oracle. The test therefore runs only if a
later decision of ADR-013 says outcome A or B *and* RTAMT is installed.
"""

from __future__ import annotations

import importlib.util
import re
from typing import Any

import pytest

from .helpers import ROOT, golden_templates

ADR = (ROOT / "docs" / "plan" / "03-decisions.md").read_text(encoding="utf-8")
SPIKE = ROOT / "tools" / "rtamt_spike.py"


def adr013_outcome() -> str:
    line = next(line for line in ADR.splitlines() if line.startswith("Spike result"))
    match = re.search(r"outcome ([ABC])\b", line)
    assert match is not None, line
    return match.group(1)


def test_adr013_records_an_outcome_for_the_spike() -> None:
    assert adr013_outcome() in {"A", "B", "C"}


def test_rtamt_oracle_agrees_on_completed_traces() -> None:
    outcome = adr013_outcome()
    if outcome == "C":
        pytest.skip(
            "ADR-013 records outcome C (RTAMT cannot host the templates: the term age, the equality atom, "
            "the unavailable channel); the point evaluator is custom and RTAMT is not an oracle. "
            "Test 30 of WS05-T04 is conditional on outcome A or B."
        )
    rtamt = pytest.importorskip("rtamt")
    spec = importlib.util.spec_from_file_location("rtamt_spike", SPIKE)
    assert spec is not None and spec.loader is not None
    module: Any = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows = module.evaluate_cases(rtamt)
    assert rows
    from ralmon.monitor import make_point_evaluator
    from ralmon.spec import TemplateId, TemplateInstance

    from .helpers import STEP, inputs_of, load_f0, load_lib, step_values

    registry = load_f0()
    templates = {t.id: t for t in load_lib(registry)}
    cases = {c["id"]: c for c in golden_templates()}
    compared = 0
    for row in rows:
        if row.kind != "literal" or row.got is None or not row.equal:
            continue
        case = cases[row.case_id]
        tid = TemplateId(case["inputs"]["template"])
        kind = "day_end" if case["inputs"].get("anchor_kind") == "day_end" else None
        instance = TemplateInstance(tid, row.case_id, {}, case["inputs"]["anchor_ms"])
        evaluator = make_point_evaluator(
            templates[tid], instance, registry, STEP, anchor_kind=kind
        )
        k = case["eval_at_ms"] // STEP
        values = step_values(inputs_of(case["inputs"]), k)
        got = None
        for step in range(k + 1):
            got = evaluator.step(step * STEP, values[step])
        assert got == pytest.approx(row.got), row.case_id
        compared += 1
    assert compared > 0
