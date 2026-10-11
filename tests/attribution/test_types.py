"""Types and alert fields (WS05-T07 tests 1 to 3).

The expected field lists are read from the contract text of ``docs/plan/02-interfaces.md`` and not retyped.
"""

from __future__ import annotations

import ast
import dataclasses
import re
from pathlib import Path

import pytest

from ralmon.monitor import VerdictState
from ralmon.spec import TemplateId, load_templates
from tests.fixtures.attribution import (
    CONTRACT_PATHS,
    hms,
    load_fixture_registry,
    make_record,
    predicted_rho,
)

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = (ROOT / "docs" / "plan" / "02-interfaces.md").read_text(encoding="utf-8")

PARTS = (
    "ProvenanceEvidence",
    "SystemHealthEvidence",
    "SignalQualityEvidence",
    "CrossDeviceEvidence",
    "EmbodiedWitnessEvidence",
    "CryptoTemporalEvidence",
    "DispenserEvidence",
)


GROUP_CLASS = {
    "provenance": "ProvenanceEvidence",
    "system": "SystemHealthEvidence",
    "signal_quality": "SignalQualityEvidence",
    "cross_device": "CrossDeviceEvidence",
    "witness": "EmbodiedWitnessEvidence",
    "crypto_temporal": "CryptoTemporalEvidence",
    "dispenser": "DispenserEvidence",
}


def contract_classes(heading: str) -> dict[str, list[str]]:
    """Class name to field names in order, from the first python block under ``## heading``."""
    section = CONTRACT.split(f"## {heading}\n", 1)[1]
    block = re.search(r"```python\n(.*?)```", section, flags=re.DOTALL)
    assert block is not None
    tree = ast.parse(block.group(1))
    out: dict[str, list[str]] = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            out[node.name] = [
                stmt.target.id
                for stmt in node.body
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
            ]
    return out


def test_evidence_dataclasses_match_contract() -> None:
    from ralmon import attribution

    expected = contract_classes("EvidenceVector")
    assert set(expected) == {*PARTS, "EvidenceVector"}
    total = 0
    for name, names in expected.items():
        cls = getattr(attribution, name)
        assert dataclasses.is_dataclass(cls), name
        assert [f.name for f in dataclasses.fields(cls)] == names, name
        assert cls.__dataclass_params__.frozen, f"{name} is not frozen"
        assert hasattr(cls, "__slots__"), f"{name} is not slotted"
        if name != "EvidenceVector":
            total += len(names)
    assert total == 24 == len(CONTRACT_PATHS)
    paths = [
        f"{group.name}.{leaf.name}"
        for group in dataclasses.fields(attribution.EvidenceVector)
        for leaf in dataclasses.fields(getattr(attribution, GROUP_CLASS[group.name]))
    ]
    assert tuple(paths) == CONTRACT_PATHS
    from ralmon.attribution.evidence import EVIDENCE_PATHS

    assert EVIDENCE_PATHS == CONTRACT_PATHS


def test_alert_extends_detection_and_matches_contract() -> None:
    from ralmon import attribution

    expected = contract_classes("Alert")
    assert issubclass(attribution.Alert, attribution.Detection)
    for name in ("Explanation", "Detection", "Alert"):
        cls = getattr(attribution, name)
        assert cls.__dataclass_params__.frozen, name
        assert hasattr(cls, "__slots__"), name
    assert [f.name for f in dataclasses.fields(attribution.Detection)] == expected[
        "Detection"
    ]
    assert [f.name for f in dataclasses.fields(attribution.Explanation)] == expected[
        "Explanation"
    ]
    assert [f.name for f in dataclasses.fields(attribution.Alert)] == [
        "t_ms",
        "label",
        "score",
        "tau",
        "kappa",
        "sigma_norm",
        "rho",
        "xi",
        "verdict",
        "priority",
        "root_cause_of",
        "caused_by",
        "p_kappa",
    ]
    assert expected["Alert"] == [
        "tau",
        "kappa",
        "sigma_norm",
        "rho",
        "xi",
        "verdict",
        "priority",
        "root_cause_of",
        "caused_by",
        "p_kappa",
    ]
    assert [c.value for c in attribution.AttributedCause] == [
        "C1",
        "C2",
        "C3",
        "UNDETERMINED",
    ]


@pytest.fixture(scope="module")
def registry_and_templates():  # type: ignore[no-untyped-def]
    registry = load_fixture_registry()
    return registry, {t.id: t for t in load_templates(registry=registry)}


def _alert(record, registry, templates, kappa="C2"):  # type: ignore[no-untyped-def]
    from ralmon.attribution import AttributedCause
    from ralmon.attribution.alert import alert_from_record
    from ralmon.attribution.rule import Decision

    decision = Decision(
        kappa=AttributedCause(kappa),
        row=4,
        reason=None,
        evidence_used=("system.liveliness_ok",),
        missing=(),
    )
    return alert_from_record(record, decision, templates[record.template], registry)


def test_alert_fields_derive_from_the_record(registry_and_templates) -> None:  # type: ignore[no-untyped-def]
    registry, templates = registry_and_templates
    record = make_record(
        "range",
        decided_at_ms=32_700_000,
        hi=-12.0,
        sigma_norm=(-0.6, -0.6),
    )
    alert = _alert(record, registry, templates)
    assert alert.t_ms == 32_700_000 == hms(9, 5)
    assert alert.label == alert.kappa
    assert alert.score == pytest.approx(0.6)
    assert alert.sigma_norm == pytest.approx(-0.6)
    assert alert.verdict is VerdictState.VIOLATED
    assert alert.tau is TemplateId.RANGE
    assert alert.priority == int(registry.get("priority_range").value)
    assert alert.xi.template is TemplateId.RANGE
    assert alert.xi.instance_key == record.instance_key
    assert alert.root_cause_of == () or list(alert.root_cause_of) == []
    assert alert.caused_by is None

    # an interval keeps the upper end: the smallest violation that is certain
    interval = make_record(
        "range", decided_at_ms=32_700_000, hi=-4.0, lo=-18.0, sigma_norm=(-0.9, -0.2)
    )
    assert _alert(interval, registry, templates).sigma_norm == pytest.approx(-0.2)
    assert _alert(interval, registry, templates).score == pytest.approx(0.2)

    # a predicted record: t_eval_ms and its predicted bound
    predicted = make_record(
        "sched",
        key="sched@32400000",
        state=VerdictState.PREDICTED_VIOLATION,
        t_eval_ms=33_000_000,
        decided_at_ms=33_000_000,
        hi=0.0,
        sigma_norm=(-1.0, 0.2),
        rho=predicted_rho(),
        predicted_sigma_norm=-0.2433,
    )
    alert = _alert(predicted, registry, templates, kappa="UNDETERMINED")
    assert alert.t_ms == 33_000_000
    assert alert.sigma_norm == pytest.approx(-0.2433)
    assert alert.score == pytest.approx(0.2433)
    assert alert.verdict is VerdictState.PREDICTED_VIOLATION
    assert alert.priority == int(registry.get("priority_sched").value)


def test_score_of_a_zero_bound_is_positive_zero(registry_and_templates) -> None:  # type: ignore[no-untyped-def]
    registry, templates = registry_and_templates
    record = make_record("range", hi=-0.0, lo=-0.0, sigma_norm=(-0.0, -0.0))
    alert = _alert(record, registry, templates)
    assert str(alert.score) == "0.0"


def test_alert_rho_may_be_none_by_contract_and_adr_059() -> None:
    """The widening of ``Alert.rho`` is in the contract and in a proposed ADR, not only in the code."""
    import typing

    from ralmon.attribution import Alert

    assert (
        "rho: Rho | None"
        in CONTRACT.split("## Alert\n", 1)[1].split("## EvidenceVector", 1)[0]
    )
    decisions = (ROOT / "docs" / "plan" / "03-decisions.md").read_text(encoding="utf-8")
    adr = decisions.split("## ADR-059", 1)[1]
    assert "[DA-CONFERMARE]" in adr.splitlines()[0]
    hints = typing.get_type_hints(Alert, include_extras=True)
    assert type(None) in typing.get_args(hints["rho"])
