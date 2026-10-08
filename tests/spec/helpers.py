"""Shared helpers of the tests of ``ralmon.spec`` (WS05-T03).

Nothing here reads the code under test; the F0 registry used by the hand-computed tests is the
test-owned copy ``tests/fixtures/spec/registry_f0.yaml`` and never the real registry file.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "spec"
F0_PATH = FIXTURES / "registry_f0.yaml"
TEMPLATE_TABLE_PATH = FIXTURES / "template_table.yaml"
GOLDEN_RANKING_COPY = FIXTURES / "golden_ranking.yaml"
GOLDEN_TEMPLATES_COPY = FIXTURES / "golden_templates.yaml"
GOLDEN_DIR = ROOT / "docs" / "formal" / "golden"
REAL_REGISTRY_PATH = ROOT / "configs" / "registry" / "hypertension.yaml"
FIXTURE_REGISTRY_PATH = ROOT / "configs" / "registry" / "fixture.yaml"
TEMPLATES_PATH = ROOT / "configs" / "templates" / "hypertension.yaml"
INTERFACES = ROOT / "docs" / "plan" / "02-interfaces.md"
TEMPLATES_DOC = ROOT / "docs" / "formal" / "02-templates.md"
SRC_RALMON = ROOT / "src" / "ralmon"

STEP_MS = 60_000  # step of the F0 fixture (fixture arithmetic)

TEMPLATE_IDS = ("range", "sched", "hold", "count", "resp", "sys", "int")


class _NoAliasDumper(yaml.SafeDumper):
    """Safe dumper that never writes anchors, so a modified document stays alias-free."""

    def ignore_aliases(self, data: object) -> bool:
        return True


def read_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def dump_yaml(doc: Any) -> str:
    return yaml.dump(doc, Dumper=_NoAliasDumper, sort_keys=False, allow_unicode=True)


def write_yaml(tmp_path: Path, doc: Any, name: str = "registry.yaml") -> Path:
    path = tmp_path / name
    path.write_text(dump_yaml(doc), encoding="utf-8")
    return path


def f0_doc() -> dict[str, Any]:
    """A fresh, mutable copy of the F0 registry document."""
    doc = read_yaml(F0_PATH)
    assert isinstance(doc, dict)
    return copy.deepcopy(doc)


def entry_of(doc: dict[str, Any], name: str) -> dict[str, Any]:
    for item in doc["entries"]:
        if item["name"] == name:
            assert isinstance(item, dict)
            return item
    raise KeyError(name)


def drop_entry(doc: dict[str, Any], name: str) -> dict[str, Any]:
    entry = entry_of(doc, name)
    doc["entries"].remove(entry)
    return entry


def make_unset(
    doc: dict[str, Any], name: str, required_by: tuple[str, ...] = ()
) -> None:
    """Move an entry of the document into its ``unset`` list (the way a name is declared unset)."""
    entry = drop_entry(doc, name)
    doc["unset"].append(
        {
            "parameter": name,
            "unit": entry["unit"],
            "required_by": list(required_by),
            "note": "value to be set and reviewed by WS00-T07",
        }
    )


def unfixture(doc: dict[str, Any]) -> dict[str, Any]:
    """Remove the FIXTURE-ONLY marker from every rationale (a registry with no fixture rows)."""
    for item in doc["entries"]:
        item["rationale"] = item["rationale"].replace(
            "FIXTURE-ONLY (fixture registry F0, ADR-027); ", "not a fixture row; "
        )
    return doc
