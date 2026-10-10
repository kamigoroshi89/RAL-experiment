"""The hierarchical rule against the worked cases and the rows of the analisi (WS05-T07 tests 4, 11, 13)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ralmon.monitor import VerdictState
from ralmon.spec import RegistryError, TemplateId
from tests.fixtures.attribution import (
    NON_PROVENANCE_PATHS,
    build_vector,
    case_ids,
    load_fixture_registry,
    make_record,
    registry_variant,
    vector,
    worked_case,
)

THRESHOLDS = (
    "hr_coherence_tolerance",
    "ecg_sqi_floor",
    "ppg_sqi_floor",
    "ble_link_quality_floor",
)


@pytest.fixture(scope="module")
def registry():  # type: ignore[no-untyped-def]
    return load_fixture_registry()


@pytest.fixture(scope="module")
def rule(registry):  # type: ignore[no-untyped-def]
    from ralmon.attribution import HierarchicalRule

    return HierarchicalRule(registry)


@pytest.mark.parametrize("case_id", case_ids())
def test_rule_matches_worked_cases(case_id: str, registry, rule) -> None:  # type: ignore[no-untyped-def]
    case = worked_case(case_id)
    evidence = build_vector(case, registry)
    record = make_record(case["template"])
    decision = rule.decide(record, evidence)
    assert decision.kappa.value == case["kappa"], case_id
    assert list(decision.evidence_used) == case["decisive"], case_id
    assert decision.row == case["row"], case_id
    if case["kappa"] == "UNDETERMINED":
        assert decision.reason is not None
        assert decision.reason.value == case["reason"], case_id
    else:
        assert decision.reason is None
    assert rule.attribute(record, evidence) is decision.kappa


def test_worked_case_ids_cover_w01_to_w15() -> None:
    ids = case_ids()
    for n in range(1, 16):
        assert any(i == f"W-{n:02d}" or i.startswith(f"W-{n:02d}-") for i in ids), n


@pytest.mark.parametrize("name", THRESHOLDS)
def test_rule_requires_registry_thresholds(name: str, tmp_path: Path) -> None:
    from ralmon.attribution import HierarchicalRule

    with pytest.raises(RegistryError):
        HierarchicalRule(registry_variant(tmp_path, drop=(name,)))
    with pytest.raises(RegistryError):
        # the real registry and the F0 registry carry none of the thresholds
        from ralmon.spec import load_registry

        HierarchicalRule(load_registry(step_ms=60_000))


def test_rule_checks_that_the_link_floor_is_at_most_one(tmp_path: Path) -> None:
    from ralmon.attribution import HierarchicalRule

    with pytest.raises(RegistryError):
        HierarchicalRule(
            registry_variant(tmp_path, override={"ble_link_quality_floor": 1.5})
        )


# ---- test 11: the rows of analisi 4.5, reproduced by hand --------------------------------------

CLEAN_RANGE = {
    "system.node_lifecycle": {"cuff": "active"},
    "system.diagnostics_ok": True,
    "system.liveliness_ok": True,
    "system.qos_deadline_missed": False,
    "system.ble_link_quality": 1.0,
    "signal_quality.ecg_sqi": 0.9,
    "signal_quality.ppg_sqi": 0.9,
    "signal_quality.cuff_error_code": "",
    "cross_device.pulse_vs_ecg_hr_diff": 2.0,
    "crypto_temporal.seq_gap_or_replay": False,
    "crypto_temporal.timestamp_implausible": False,
}


def test_analisi_matrix_rows_by_hand(registry, rule) -> None:  # type: ignore[no-untyped-def]
    import yaml

    record = make_record("range")

    # row 8 (replay): a repeated sequence value with a complete delivery ratio and no link fault -> C3
    ev = vector(
        "range", {**CLEAN_RANGE, "crypto_temporal.seq_gap_or_replay": True}, registry
    )
    assert rule.decide(record, ev).kappa.value == "C3"

    # row 3 (cuff detached, evident failure): a device error code -> C2
    ev = vector(
        "range", {**CLEAN_RANGE, "signal_quality.cuff_error_code": "E1"}, registry
    )
    assert rule.decide(record, ev).kappa.value == "C2"

    # row 5 (robot late): nav_task_failed asserted with a violated sched -> C2
    sched = {
        "system.node_lifecycle": {"cuff": "active", "robot": "active"},
        "system.liveliness_ok": True,
        "system.ble_link_quality": 1.0,
        "system.nav_task_failed": True,
        "system.manip_task_failed": False,
        "signal_quality.cuff_error_code": "",
        "crypto_temporal.seq_gap_or_replay": False,
    }
    decision = rule.decide(make_record("sched"), vector("sched", sched, registry))
    assert decision.kappa.value == "C2"
    assert list(decision.evidence_used) == ["system.nav_task_failed"]

    # row 1 (real hypertension): every relevant channel available and coherent -> C1
    ev = vector("range", CLEAN_RANGE, registry)
    assert rule.decide(record, ev).kappa.value == "C1"

    # row 4 (silent cuff bias): all channels coherent -> C1, and the matrix declares it not distinguishable
    assert rule.decide(record, ev).kappa.value == "C1"
    matrix = yaml.safe_load(
        (
            Path(__file__).resolve().parents[2] / "configs" / "diagnosability.yaml"
        ).read_text(encoding="utf-8")
    )
    row = next(r for r in matrix["rows"] if r["id"] == "DX-04")
    assert row["distinguishable"] == "not_distinguishable"
    assert row["declared_limit"] is True


# ---- test 13: a missing evidence entry is all unavailable ------------------------------------


@pytest.mark.parametrize("template", [t.value for t in TemplateId])
def test_missing_evidence_entry_is_all_unavailable(template: str, registry) -> None:  # type: ignore[no-untyped-def]
    from ralmon.attribution import AttributedCause, RuleAttributor
    from ralmon.spec import load_templates

    attributor = RuleAttributor(registry, load_templates(registry=registry))
    record = make_record(template, key=f"{template}@1000", decided_at_ms=1000)
    alerts = attributor.attribute_all(
        [record], {}
    )  # no entry for the key: no exception
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.kappa is AttributedCause.UNDETERMINED
    assert alert.label is AttributedCause.UNDETERMINED
    assert list(alert.xi.evidence_used) == []
    assert alert.verdict is VerdictState.VIOLATED


def test_empty_evidence_vector_has_provenance_only(registry) -> None:  # type: ignore[no-untyped-def]
    from ralmon.attribution.evidence import EVIDENCE_PATHS, empty_evidence, get_evidence

    from ralmon.spec import TemplateKind

    for template in TemplateId:
        ev = empty_evidence(template)
        assert get_evidence(ev, "provenance.violated_template") is template
        for path in NON_PROVENANCE_PATHS:
            assert get_evidence(ev, path) is None
    assert (
        get_evidence(empty_evidence(TemplateId.SYS), "provenance.template_kind")
        is TemplateKind.SYSTEM
    )
    assert (
        get_evidence(empty_evidence(TemplateId.INT), "provenance.template_kind")
        is TemplateKind.INTEGRITY
    )
    assert len(EVIDENCE_PATHS) == 20


def test_mismatched_template_kind_abstains_without_exception(
    registry, rule, caplog
) -> None:  # type: ignore[no-untyped-def]
    """AD-18: a template_kind that does not match the template makes row 8 apply, and the defect is logged."""
    import dataclasses

    from ralmon.spec import TemplateKind

    case = worked_case("W-01")
    evidence = build_vector(case, registry)
    bad = dataclasses.replace(
        evidence,
        provenance=dataclasses.replace(
            evidence.provenance, template_kind=TemplateKind.SYSTEM
        ),
    )
    with caplog.at_level("WARNING", logger="ralmon.attribution"):
        decision = rule.decide(make_record("range"), bad)
    assert decision.kappa.value == "UNDETERMINED"
    assert decision.row == 8
    assert list(decision.evidence_used) == []
    assert any("template_kind" in r.getMessage() for r in caplog.records)


def test_out_of_domain_readings_are_unavailable(registry, rule) -> None:  # type: ignore[no-untyped-def]
    """AD-18: a delivery ratio above one, a NaN and a negative difference are read as unavailable."""
    base = dict(CLEAN_RANGE)
    for path, bad in (
        ("system.ble_link_quality", 1.5),
        ("system.ble_link_quality", float("nan")),
        ("cross_device.pulse_vs_ecg_hr_diff", -1.0),
    ):
        fields = {**base, path: bad}
        decision = rule.decide(make_record("range"), vector("range", fields, registry))
        assert decision.kappa.value == "UNDETERMINED", path
        assert (
            decision.reason is not None and decision.reason.value == "insufficient"
        ), path
