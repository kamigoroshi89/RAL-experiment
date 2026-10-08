"""The test fixtures of WS05-T03 agree with the formal documents they were copied from.

These tests read files only; they do not import the code under test.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from .helpers import (
    F0_PATH,
    FIXTURE_REGISTRY_PATH,
    FIXTURES,
    GOLDEN_DIR,
    GOLDEN_RANKING_COPY,
    GOLDEN_TEMPLATES_COPY,
    TEMPLATE_IDS,
    TEMPLATE_TABLE_PATH,
    TEMPLATES_DOC,
    TEMPLATES_PATH,
    f0_doc,
    read_yaml,
)

# F0 rows that are not registry names (docs/formal/03-parameter-registry.md section 3.3).
NOT_REGISTRY_NAMES = {"meas_min_day", "step_ms", "reorder_delay_ms"}
UNIT_OF_F0_CELL = {
    "mmHg": "mmHg",
    "ms": "ms",
    "dose": "dose",
    "rank, 1 = highest": "1",
    "rank": "1",
}
F0_FIXTURE_ONLY_NAMES = {
    "sched_window",
    "delta_resp",
    "cuff_inflation_min",
    "scale_hold",
    "scale_resp",
    "scale_sys",
    "scale_int",
    "priority_count",
    "priority_resp",
    "priority_sys",
    "priority_int",
    "cuff_error_sd",
}


def test_f0_copy_equals_the_fixture_registry_of_the_golden_file() -> None:
    """Every name and value of the F0 section of templates.yaml is in the F0 copy, and nothing else."""
    golden = read_yaml(GOLDEN_DIR / "templates.yaml")["fixture_registry"]
    expected: dict[str, tuple[float, str]] = {}
    for row in golden:
        for name, value in zip(row["names"], row["values"], strict=True):
            if name not in NOT_REGISTRY_NAMES:
                expected[name] = (float(value), UNIT_OF_F0_CELL[row["unit"]])
    copy_entries = {e["name"]: (e["value"], e["unit"]) for e in f0_doc()["entries"]}
    assert copy_entries == expected
    assert (
        len(expected) == 29
    )  # 32 F0 names minus the three that are not registry names


def test_f0_golden_section_has_the_rows_of_the_workshop_f0_table() -> None:
    """The F0 table of the WS01 README and the golden section agree name by name (26 rows)."""
    readme = (
        F0_PATH.parents[3]
        / "docs"
        / "plan"
        / "workstreams"
        / "WS01-formalization"
        / "README.md"
    ).read_text(encoding="utf-8")
    table = readme.split("### Fixture registry F0", 1)[1].split(
        "FIXTURE-ONLY means", 1
    )[0]
    readme_rows = [
        line for line in table.splitlines() if line.startswith("| `")
    ]  # the header and separator start with "| Working" and "|---"
    golden = read_yaml(GOLDEN_DIR / "templates.yaml")["fixture_registry"]
    assert len(readme_rows) == len(golden) == 26
    for line, row in zip(readme_rows, golden, strict=True):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        assert cells[0] == row["row_name_cell"]
        assert cells[1] == row["value_cell"]


def test_every_f0_entry_is_marked_fixture_only() -> None:
    for entry in f0_doc()["entries"]:
        assert entry["rationale"].startswith("FIXTURE-ONLY"), entry["name"]
        assert entry["rationale"].endswith("illustrative, unverified")
        assert entry["reviewed_by"] is None
    names = {e["name"] for e in f0_doc()["entries"]}
    assert F0_FIXTURE_ONLY_NAMES <= names


def test_the_registry_fixture_in_configs_equals_the_test_copy() -> None:
    """ADR-027: configs/registry/fixture.yaml holds the F0 rows; the test copy must not drift from it."""
    assert FIXTURE_REGISTRY_PATH.is_file()
    assert read_yaml(FIXTURE_REGISTRY_PATH) == read_yaml(F0_PATH)


def test_golden_copies_equal_the_golden_files() -> None:
    assert read_yaml(GOLDEN_RANKING_COPY) == read_yaml(GOLDEN_DIR / "ranking.yaml")
    assert read_yaml(GOLDEN_TEMPLATES_COPY) == read_yaml(GOLDEN_DIR / "templates.yaml")


def test_golden_case_counts_are_those_of_the_freeze() -> None:
    ranking = read_yaml(GOLDEN_RANKING_COPY)
    templates = read_yaml(GOLDEN_TEMPLATES_COPY)
    assert [c["id"] for c in ranking if c["id"].startswith("N-")] == [
        f"N-{i}" for i in range(1, 11)
    ]
    assert [c["id"] for c in ranking if c["id"].startswith("RK-")] == [
        f"RK-{i}" for i in range(1, 7)
    ]
    assert len(templates["cases"]) == 26


def _markdown_template_rows() -> list[dict[str, Any]]:
    text = TEMPLATES_DOC.read_text(encoding="utf-8")
    section = text.split("### 3.1 The seven templates", 1)[1].split(
        "Notes on the table.", 1
    )[0]
    rows = []
    for line in section.splitlines():
        match = re.match(r"^\| (RANGE|SCHED|HOLD|COUNT|RESP|SYS|INT) \|", line)
        if match is None:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split(" | ")]
        assert len(cells) == 10, line
        formula = cells[2]
        assert formula.startswith("`") and formula.endswith("`")
        rows.append(
            {
                "id": cells[0],
                "kind": cells[1],
                "formula_past_time": formula.strip("`"),
                "signals": [s.strip() for s in cells[3].split(",")],
                "params": [s.strip() for s in cells[4].split(",")],
                "unit": cells[5],
                "scale_param": cells[6],
                "priority_param": cells[7],
                "max_verdict_latency_param": cells[8],
                "creates_robot_obligation": {"True": True, "False": False}[cells[9]],
            }
        )
    return rows


def test_template_table_fixture_is_a_faithful_transcription_of_the_document() -> None:
    document_rows = _markdown_template_rows()
    assert [r["id"] for r in document_rows] == [i.upper() for i in TEMPLATE_IDS]
    fixture_rows = read_yaml(TEMPLATE_TABLE_PATH)["rows"]
    stripped = [
        {k: v for k, v in row.items() if k != "locator"} for row in fixture_rows
    ]
    assert stripped == document_rows
    for row in fixture_rows:
        assert row["locator"].startswith("docs/formal/02-templates.md section 3.1")


def test_template_library_file_matches_the_document_table() -> None:
    """configs/templates/hypertension.yaml is the machine-readable form of the section-3 table."""
    assert TEMPLATES_PATH.is_file()
    library = read_yaml(TEMPLATES_PATH)
    kind_of = {
        "CARE_PLAN": "phi_cp",
        "SYSTEM": "phi_sys",
        "INTEGRITY": "phi_int",
    }
    unit_of = {"MMHG": "mmHg", "MS": "ms", "DOSE": "dose", "DIMENSIONLESS": "1"}
    expected = []
    for row in _markdown_template_rows():
        expected.append(
            {
                "id": row["id"].lower(),
                "kind": kind_of[row["kind"]],
                "formula_past_time": row["formula_past_time"],
                "signals": row["signals"],
                "params": row["params"],
                "unit": unit_of[row["unit"]],
                "scale_param": row["scale_param"],
                "priority_param": row["priority_param"],
                "max_verdict_latency_param": row["max_verdict_latency_param"],
                "creates_robot_obligation": row["creates_robot_obligation"],
            }
        )
    actual = [
        {k: v for k, v in row.items() if k != "source"} for row in library["templates"]
    ]
    assert actual == expected
    for row in library[
        "templates"
    ]:  # the locator names the row it was transcribed from
        assert row["source"] == (
            f"docs/formal/02-templates.md section 3.1, row {row['id'].upper()}"
        )


GOLDEN_PLAN_FILES = (
    "plan_golden.key",
    "plan_a.canonical.json",
    "plan_a.hmac_sha256",
    "plan_b.canonical.json",
    "plan_b.hmac_sha256",
    "plan_c.canonical.json",
    "plan_c.hmac_sha256",
)


@pytest.mark.parametrize("name", GOLDEN_PLAN_FILES)
def test_plan_golden_files_are_committed(name: str) -> None:
    assert (FIXTURES / name).is_file()


@pytest.mark.parametrize("plan", ["plan_a", "plan_b", "plan_c"])
def test_plan_golden_digest_is_a_lowercase_sha256_hex(plan: str) -> None:
    digest = (FIXTURES / f"{plan}.hmac_sha256").read_text(encoding="ascii").strip()
    assert re.fullmatch(r"[0-9a-f]{64}", digest) is not None


def test_make_plan_golden_script_uses_openssl_and_no_python() -> None:
    script = Path(FIXTURES / "make_plan_golden.sh").read_text(encoding="utf-8")
    assert "openssl dgst -sha256 -hmac" in script
    assert "python" not in script
