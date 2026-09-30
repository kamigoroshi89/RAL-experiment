"""The Package public API contract is importable and stubs fail loudly (WS05-T01)."""

from __future__ import annotations

import importlib
import inspect
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
INTERFACES = ROOT / "docs" / "plan" / "02-interfaces.md"
SRC = ROOT / "src" / "ralmon"
PACKAGES = (
    "signals",
    "spec",
    "monitor",
    "conformal",
    "attribution",
    "benchmark",
    "baselines",
    "eval",
)
EVIDENCE_PARTS = (
    "ProvenanceEvidence",
    "SystemHealthEvidence",
    "SignalQualityEvidence",
    "CrossDeviceEvidence",
    "EmbodiedWitnessEvidence",
    "CryptoTemporalEvidence",
)
STUB_ATTR = "__ralmon_stub_owner__"


def parse_contract_table() -> dict[str, list[str]]:
    """Parse the table under '## Package public API' into {package: [names]}."""
    text = INTERFACES.read_text(encoding="utf-8")
    section = text.split("## Package public API", 1)[1]
    table: dict[str, list[str]] = {}
    for line in section.splitlines():
        match = re.match(r"^\|\s*`(ralmon\.[a-z_]+)`\s*\|(.*)\|\s*$", line)
        if match is None:
            continue
        cell = match.group(2)
        names = re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)`", cell)
        if "(and its parts)" in cell:
            names.extend(EVIDENCE_PARTS)
        table[match.group(1)] = names
    return table


def contract_pairs() -> list[tuple[str, str]]:
    return [
        (pkg, name) for pkg, names in parse_contract_table().items() for name in names
    ]


def exported_objects() -> list[tuple[str, str, object]]:
    found = []
    for pkg in parse_contract_table():
        module = importlib.import_module(pkg)
        for name in module.__all__:
            found.append((pkg, name, getattr(module, name)))
    return found


def test_contract_table_lists_exactly_eight_packages() -> None:
    assert set(parse_contract_table()) == {f"ralmon.{p}" for p in PACKAGES}


@pytest.mark.parametrize(
    ("package", "name"), contract_pairs(), ids=[f"{p}.{n}" for p, n in contract_pairs()]
)
def test_every_public_name_is_importable(package: str, name: str) -> None:
    module = importlib.import_module(package)
    assert hasattr(module, name)


@pytest.mark.parametrize("package", sorted(parse_contract_table()))
def test_dunder_all_equals_contract_names(package: str) -> None:
    module = importlib.import_module(package)
    assert set(module.__all__) == set(parse_contract_table()[package])


def test_only_eight_package_directories() -> None:
    found = {
        p.name for p in SRC.iterdir() if p.is_dir() and (p / "__init__.py").is_file()
    }
    assert found == set(PACKAGES)


def test_stub_functions_raise_not_implemented_naming_owner() -> None:
    for _pkg, _name, obj in exported_objects():
        owner = getattr(obj, STUB_ATTR, None)
        if owner is None or not inspect.isfunction(obj):
            continue
        with pytest.raises(NotImplementedError, match=re.escape(owner)):
            obj()


def test_stub_classes_cannot_be_instantiated_silently() -> None:
    for _pkg, _name, obj in exported_objects():
        owner = getattr(obj, STUB_ATTR, None)
        if owner is None or not inspect.isclass(obj):
            continue
        with pytest.raises(NotImplementedError, match=re.escape(owner)):
            obj()


def test_every_stub_owner_is_a_real_task() -> None:
    for pkg, name, obj in exported_objects():
        owner = getattr(obj, STUB_ATTR, None)
        if owner is None:
            continue
        match = re.fullmatch(r"WS(\d\d)-T(\d\d)", owner)
        assert match is not None, f"{pkg}.{name}: malformed owner {owner!r}"
        pattern = (
            f"docs/plan/workstreams/WS{match.group(1)}-*/tasks/T{match.group(2)}-*.md"
        )
        assert list(ROOT.glob(pattern)), f"{pkg}.{name}: no task file for {owner}"


def test_not_implemented_error_is_written_only_in_stub_helper() -> None:
    assert SRC.is_dir(), "src/ralmon does not exist"
    offenders = [
        str(path.relative_to(ROOT))
        for path in SRC.rglob("*.py")
        if path.name != "_stub.py" or path.parent != SRC
        if "NotImplementedError" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []
