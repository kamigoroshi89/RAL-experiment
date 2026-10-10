"""The rows of ``configs/diagnosability.yaml`` reproduced by the rule (WS05-T07 test 12).

A row carries evidence paths and expected causes, not the readings of a vector (docs/models/diagnosability-hazards.md,
section Using the file). The vectors are built from the worked cases that the row ``note`` names (W-01 to W-15 of
``attribution-rule.md``, read from ``tests/fixtures/attribution/worked_cases.json``) and, for the templates of
``violated_templates`` that no named case covers, from a vector with every channel clean. Each outcome is read through
its ``when`` set: the empty set is the unauthenticated default deployment, ``CH-CRYPTO: available`` the authenticated
one, the pair ``CH-WIT``/``CH-SYS-ROBOT`` unavailable is ablation A4 (the variant ``<case>-A4`` when the document has
one, else the path mask of evidence-channels.md), and the other channels are set to ``None``.

The check is that every expected cause of an outcome that the rule can produce is produced by at least one of those
vectors (several expected causes are a union over templates and cases, not alternatives for one vector). An outcome
whose ``when`` names the proposed channel ``CH-DISP`` (the analisi verdict of DX-06 and DX-07, not reproducible by the
rule until ADR-032) and an expected cause ``NO_ALERT`` (a statement about detection) are skipped, with a recorded reason
(``test_skipped_outcomes_have_a_recorded_reason``). The rows are read through the file; none is retyped.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.fixtures.attribution import (
    CONTRACT_PATHS,
    build_vector,
    case_ids,
    load_fixture_registry,
    make_record,
    vector,
    worked_case,
)

ROOT = Path(__file__).resolve().parents[2]
MATRIX = yaml.safe_load(
    (ROOT / "configs" / "diagnosability.yaml").read_text(encoding="utf-8")
)
ROWS = MATRIX["rows"]
KNOWN = set(case_ids())

A4_PATHS = (
    "witness.robot_present",
    "witness.identity_confirmed",
    "witness.intake_observed",
    "system.nav_task_failed",
    "system.manip_task_failed",
    "system.battery_low",
)
CHANNEL_FIELDS = {
    "CH-SYS-WARD": (
        "system.node_lifecycle",
        "system.diagnostics_ok",
        "system.liveliness_ok",
        "system.qos_deadline_missed",
        "system.ble_link_quality",
    ),
    "CH-SQI": (
        "signal_quality.ecg_sqi",
        "signal_quality.ppg_sqi",
        "signal_quality.cuff_error_code",
    ),
    "CH-XDEV": ("cross_device.pulse_vs_ecg_hr_diff",),
}
THREE = {"cuff": "active", "dispenser": "active", "robot": "active"}
CLEAN = {
    "system.node_lifecycle": THREE,
    "system.diagnostics_ok": True,
    "system.liveliness_ok": True,
    "system.qos_deadline_missed": False,
    "system.ble_link_quality": 1.0,
    "system.nav_task_failed": False,
    "system.manip_task_failed": False,
    "signal_quality.ecg_sqi": 0.75,
    "signal_quality.ppg_sqi": 0.75,
    "signal_quality.cuff_error_code": "",
    "cross_device.pulse_vs_ecg_hr_diff": 2.0,
    "witness.identity_confirmed": True,
    "witness.intake_observed": True,
    "crypto_temporal.seq_gap_or_replay": False,
    "crypto_temporal.timestamp_implausible": False,
}


def named_cases(row: dict[str, Any]) -> list[str]:
    names = re.findall(r"\bW-\d\d(?:-[A-Za-z0-9]+)*", row["note"])
    return sorted(set(names))


def skip_reason(outcome: dict[str, Any]) -> str | None:
    if "CH-DISP" in outcome["when"]:
        return "proposed channel CH-DISP (ADR-032): the analisi verdict, not reproducible by the rule"
    if not set(outcome["expected_kappa"]) - {"NO_ALERT"}:
        return "NO_ALERT is a statement about detection: the rule runs on violated records only"
    return None


def is_a4(when: dict[str, str]) -> bool:
    return (
        when.get("CH-WIT") == "unavailable"
        and when.get("CH-SYS-ROBOT") == "unavailable"
    )


def transform(
    case_id: str, fields: dict[str, Any], when: dict[str, str]
) -> dict[str, Any]:
    """The fields of a worked case under the channel assumptions of an outcome."""
    out = dict(fields)
    if is_a4(when):
        a4_variant = f"{case_id}-A4"
        if a4_variant in KNOWN:
            out = dict(worked_case(a4_variant)["fields"])
        elif not case_id.endswith("A4"):
            out = {k: v for k, v in out.items() if k not in A4_PATHS}
    elif when.get("CH-WIT") == "unavailable":
        out = {k: v for k, v in out.items() if not k.startswith("witness.")}
    if (
        when.get("CH-CRYPTO") == "available"
        and "crypto_temporal.authenticated" not in out
    ):
        out["crypto_temporal.authenticated"] = True
    for channel, paths in CHANNEL_FIELDS.items():
        if when.get(channel) == "unavailable":
            out = {k: v for k, v in out.items() if k not in paths}
    return out


def candidates(row: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    """(case id, template, fields) of the named cases, then a clean vector per template of the row."""
    out: list[tuple[str, str, dict[str, Any]]] = []
    for cid in named_cases(row):
        assert cid in KNOWN, (
            f"{row['id']}: the note names {cid}, which is not a worked case"
        )
        case = worked_case(cid)
        out.append((cid, case["template"], dict(case["fields"])))
    for template in row["violated_templates"]:
        out.append((f"clean-{template}", template, dict(CLEAN)))
    return out


def computed_causes(
    row: dict[str, Any], outcome: dict[str, Any], rule: Any, registry: Any
) -> set[str]:
    causes: set[str] = set()
    for cid, template, fields in candidates(row):
        fields = transform(cid, fields, outcome["when"])
        decision = rule.decide(
            make_record(template), vector(template, fields, registry)
        )
        causes.add(decision.kappa.value)
    return causes


def row_verdict(row: dict[str, Any]) -> str:
    """The one rule of ``vocabulary.row_verdict``: judged on the outcomes that keep the embodied pair."""
    results = [o["result"] for o in row["outcomes"] if not is_a4(o["when"])]
    if "not_distinguishable" in results:
        return "not_distinguishable"
    if "distinguishable" in results and "partial" in results:
        return "conditional"
    if all(r == "distinguishable" for r in results):
        return "distinguishable"
    return "partial"


@pytest.fixture(scope="module")
def registry():  # type: ignore[no-untyped-def]
    return load_fixture_registry()


@pytest.fixture(scope="module")
def rule(registry):  # type: ignore[no-untyped-def]
    from ralmon.attribution import HierarchicalRule

    return HierarchicalRule(registry)


@pytest.mark.parametrize("row", ROWS, ids=[r["id"] for r in ROWS])
def test_diagnosability_rows_reproduced(row: dict[str, Any], registry, rule) -> None:  # type: ignore[no-untyped-def]
    # the file schema: evidence paths are fields of the contract or proposed fields in slash notation
    for path in row["discriminating_evidence"]:
        assert path in CONTRACT_PATHS, path
    for path in row["proposed_evidence"]:
        assert "/" in path, path
    # the row verdict and the declared limit follow the one rule of the file, and keep their flag
    assert row["distinguishable"] == row_verdict(row), row["id"]
    assert row["declared_limit"] is (row["distinguishable"] == "not_distinguishable")
    if row["id"] in {"DX-04", "DX-10"}:
        assert row["distinguishable"] == "not_distinguishable"
        assert row["declared_limit"] is True
        default = next(o for o in row["outcomes"] if not o["when"])
        assert default["masquerades_as"] == "C1"
        assert row["true_class"] != "C1"
    true_class = row["true_class"]
    for outcome in row["outcomes"]:
        expected = set(outcome["expected_kappa"])
        result = outcome["result"]
        # the outcome is consistent with the row (the stated cause of a distinguishable outcome is the true class)
        if result == "distinguishable":
            assert true_class in expected, (row["id"], outcome)
        elif result == "not_distinguishable":
            assert outcome["masquerades_as"] in expected and true_class not in expected
        else:
            assert true_class in outcome["candidates"], (row["id"], outcome)
        if skip_reason(outcome) is not None:
            continue
        causes = computed_causes(row, outcome, rule, registry)
        assert expected - {"NO_ALERT"} <= causes, (row["id"], outcome["when"], causes)


def test_skipped_outcomes_have_a_recorded_reason() -> None:
    skipped = [
        (row["id"], skip_reason(o), o["when"])
        for row in ROWS
        for o in row["outcomes"]
        if skip_reason(o)
    ]
    assert skipped
    assert all(reason for _, reason, _ in skipped)
    ids = {rid for rid, _, _ in skipped}
    assert {"DX-06", "DX-07"} <= ids  # the CH-DISP outcomes
    assert all(
        "CH-DISP" in when
        for rid, _, when in skipped
        if rid in {"DX-06", "DX-07"} and when
    )


def test_named_cases_exist_for_every_row() -> None:
    for row in ROWS:
        for cid in named_cases(row):
            assert cid in KNOWN, (row["id"], cid)
    assert build_vector  # the builder is part of the fixture API
