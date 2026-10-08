"""Public surface, stub policy and layering of ``ralmon.spec`` (WS05-T03 Done when; ADR-024, ADR-025).

The existing suite (``tests/test_public_api.py``, ``tests/test_layering.py``) checks the whole package
tree; these tests pin the facts that belong to this task.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import re
import subprocess
import sys
from pathlib import Path

import pytest

import ralmon.spec
from ralmon import _stub

from .helpers import INTERFACES, ROOT, SRC_RALMON

SPEC_DIR = SRC_RALMON / "spec"
DONE_WHEN_NAMES = (
    "Template",
    "TemplateId",
    "TemplateKind",
    "TemplateInstance",
    "CarePlan",
    "RobustnessUnit",
    "ParameterRegistry",
    "RegistryEntry",
    "PhysioBounds",
    "normalise",
    "rank_alerts",
    "load_registry",
    "load_templates",
    "Rho",
    "RhoKind",
    "PlanVerifier",
    "HmacSha256PlanVerifier",
    "PlanIntegrityError",
    "verify_plan",
)
EXTRA_NAMES = (
    "RegistryError",
    "UnsetParameterError",
    "TemplateLibraryError",
    "LoadedRegistry",
    "as_duration_ms",
    "as_priority",
)


def contract_names() -> list[str]:
    text = INTERFACES.read_text(encoding="utf-8")
    row = next(
        line
        for line in text.split("## Package public API", 1)[1].splitlines()
        if line.startswith("| `ralmon.spec`")
    )
    return re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)`", row.split("|")[2])


def test_dunder_all_equals_the_contract_table() -> None:
    assert sorted(ralmon.spec.__all__) == sorted(contract_names())
    assert sorted(contract_names()) == sorted(DONE_WHEN_NAMES)
    assert len(set(ralmon.spec.__all__)) == len(ralmon.spec.__all__)


@pytest.mark.parametrize("name", DONE_WHEN_NAMES)
def test_no_done_when_name_is_a_placeholder(name: str) -> None:
    obj = getattr(ralmon.spec, name)
    assert not hasattr(obj, _stub.STUB_OWNER_ATTR)
    assert getattr(obj, "__ralmon_stub_owner__", None) is None


def test_the_stubs_module_has_no_spec_placeholder_left() -> None:
    stubs = importlib.import_module("ralmon.spec._stubs")
    leftovers = [
        n
        for n, v in vars(stubs).items()
        if getattr(v, _stub.STUB_OWNER_ATTR, None) is not None
    ]
    assert leftovers == []
    tree = ast.parse((SPEC_DIR / "_stubs.py").read_text(encoding="utf-8"))
    assert [
        n for n in tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef))
    ] == []


def test_no_not_implemented_error_outside_the_stub_helpers() -> None:
    for path in sorted(SPEC_DIR.glob("*.py")):
        if path.name.startswith("_stub"):
            continue
        assert "NotImplementedError" not in path.read_text(encoding="utf-8"), path.name


def test_every_public_name_is_defined_in_its_module() -> None:
    expected_home = {
        "Template": "templates",
        "TemplateId": "templates",
        "TemplateKind": "templates",
        "RobustnessUnit": "templates",
        "load_templates": "templates",
        "TemplateInstance": "plan",
        "CarePlan": "plan",
        "ParameterRegistry": "registry",
        "RegistryEntry": "registry",
        "PhysioBounds": "registry",
        "load_registry": "registry",
        "normalise": "normalise",
        "rank_alerts": "normalise",
        "Rho": "rho",
        "RhoKind": "rho",
        "PlanVerifier": "integrity",
        "HmacSha256PlanVerifier": "integrity",
        "PlanIntegrityError": "integrity",
        "verify_plan": "integrity",
    }
    assert set(expected_home) == set(DONE_WHEN_NAMES)
    for name, home in expected_home.items():
        assert getattr(ralmon.spec, name).__module__ == f"ralmon.spec.{home}", name


@pytest.mark.parametrize("name", EXTRA_NAMES)
def test_error_types_and_helpers_are_reachable_from_the_package_root(name: str) -> None:
    """Outside ``__all__`` (ADR-024 pins ``__all__`` to the contract table) but importable from the
    root, because the layering rule forbids other packages to import ``ralmon.spec.registry``."""
    assert hasattr(ralmon.spec, name)
    assert name not in ralmon.spec.__all__
    assert not hasattr(getattr(ralmon.spec, name), _stub.STUB_OWNER_ATTR)


def test_error_hierarchy() -> None:
    from ralmon.spec import (
        PlanIntegrityError,
        RegistryError,
        TemplateLibraryError,
        UnsetParameterError,
    )

    assert issubclass(UnsetParameterError, RegistryError)
    assert issubclass(RegistryError, Exception) and not issubclass(
        RegistryError, (ValueError, OSError)
    )
    assert issubclass(TemplateLibraryError, Exception)
    assert issubclass(PlanIntegrityError, Exception)
    assert len({RegistryError, TemplateLibraryError, PlanIntegrityError}) == 3


def imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.append(("." * node.level) + (node.module or ""))
    return found


def test_spec_imports_only_signals_stdlib_numpy_and_yaml() -> None:
    allowed_third_party = {"yaml", "numpy"}
    stdlib = (
        set(sys.stdlib_module_names) if hasattr(sys, "stdlib_module_names") else None
    )
    for path in sorted(SPEC_DIR.glob("*.py")):
        for module in imported_modules(path):
            top = module.split(".")[0]
            if module.startswith("."):
                assert module.startswith(".") and not module.startswith(".."), (
                    path.name,
                    module,
                )
                continue  # a sibling module of ralmon.spec
            if top == "ralmon":
                assert module in {"ralmon.signals", "ralmon.spec"} or module.startswith(
                    "ralmon.spec."
                ), (path.name, module)
                continue
            if stdlib is not None:
                assert top in stdlib | allowed_third_party | {"__future__"}, (
                    path.name,
                    module,
                )
            else:  # pragma: no cover - Python 3.10 has no sys.stdlib_module_names
                assert top not in {"scipy", "pandas", "rclpy", "requests"}, (
                    path.name,
                    module,
                )


def test_done_when_layering_grep_finds_nothing() -> None:
    pattern = r"^from ralmon\.\(attribution\|monitor\|conformal\)\|^import ralmon\.\(attribution\|monitor\|conformal\)"
    result = subprocess.run(
        ["grep", "-rn", pattern, str(SPEC_DIR)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1 and result.stdout == ""
    for path in SPEC_DIR.glob("*.py"):
        assert not any(
            m.split(".")[:2]
            in (
                ["ralmon", "attribution"],
                ["ralmon", "monitor"],
                ["ralmon", "conformal"],
            )
            for m in imported_modules(path)
        ), path.name


def test_spec_does_not_import_the_benchmark_ground_truth() -> None:
    """Ground-truth discipline: nothing in spec can read LatentDay or GroundTruthEvent."""
    for path in sorted(SPEC_DIR.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        assert "LatentDay" not in text and "GroundTruthEvent" not in text, path.name
        assert not any(m.startswith("ralmon.benchmark") for m in imported_modules(path))


def test_every_module_of_the_task_exists() -> None:
    for module in ("registry", "templates", "plan", "normalise", "rho", "integrity"):
        assert (SPEC_DIR / f"{module}.py").is_file()
        importlib.import_module(f"ralmon.spec.{module}")


def test_public_functions_have_docstrings_and_annotations() -> None:
    for name in (
        "normalise",
        "rank_alerts",
        "load_registry",
        "load_templates",
        "verify_plan",
    ):
        function = getattr(ralmon.spec, name)
        assert inspect.getdoc(function), name
        signature = inspect.signature(function)
        assert signature.return_annotation is not inspect.Signature.empty, name
        for parameter in signature.parameters.values():
            assert parameter.annotation is not inspect.Parameter.empty, (
                name,
                parameter.name,
            )


def test_the_load_registry_signature_is_the_planned_one() -> None:
    signature = inspect.signature(ralmon.spec.load_registry)
    assert list(signature.parameters) == ["path", "step_ms", "allow_fixture_only"]
    assert signature.parameters["path"].default is None
    assert signature.parameters["step_ms"].kind is inspect.Parameter.KEYWORD_ONLY
    assert signature.parameters["step_ms"].default is None
    assert (
        signature.parameters["allow_fixture_only"].kind
        is inspect.Parameter.KEYWORD_ONLY
    )
    assert signature.parameters["allow_fixture_only"].default is False
    loader = inspect.signature(ralmon.spec.load_templates)
    assert list(loader.parameters) == ["path", "registry"]
    assert all(p.default is None for p in loader.parameters.values())
    verify = inspect.signature(ralmon.spec.verify_plan)
    assert list(verify.parameters) == [
        "plan",
        "verifier",
        "registry_version",
        "require_signature",
    ]
    assert verify.parameters["registry_version"].kind is inspect.Parameter.KEYWORD_ONLY
    assert verify.parameters["require_signature"].default is False


def test_the_package_imports_without_reading_any_file() -> None:
    """Importing ``ralmon.spec`` does not load the registry or the templates (no hidden I/O at import)."""
    code = (
        "import sys\n"
        "opened = []\n"
        "def hook(event, args):\n"
        "    if event == 'open':\n"
        "        opened.append(str(args[0]))\n"
        "sys.addaudithook(hook)\n"
        "import ralmon.spec\n"
        "bad = [f for f in opened if f.endswith('.yaml') or f.endswith('.yml')]\n"
        "sys.exit(1 if bad else 0)\n"
    )
    env_path = str(ROOT / "src")
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
        env={"PYTHONPATH": env_path, "PATH": ""},
    )
    assert result.returncode == 0, result.stderr
