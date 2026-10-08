"""No illustrative clinical constant in the core sources (test 19 of WS05-T03; WS05 acceptance 9).

``pytest tests/spec -q -k clinical_constants`` runs this file. The registry rule of
02-interfaces.md#parameter-registry: no numeric clinical constant in ``src/ralmon`` outside the loader.
The list of values is a constant of the test: the illustrative numbers of analisi §4.1 and §4.7.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from .helpers import SRC_RALMON

# analisi §4.1 (band 110 to 140, hold 100) and §4.7 (physiological bounds 50 and 250): illustrative, unverified
ILLUSTRATIVE_VALUES = (50, 100, 110, 140, 250)
SCANNED_PACKAGES = ("signals", "spec", "monitor", "conformal", "attribution")


def numeric_literals(source: str) -> list[tuple[int, int | float]]:
    """Every int or float literal of the AST (docstrings and comments are not literals of this kind)."""
    found: list[tuple[int, int | float]] = []
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, (int, float))
            and not isinstance(node.value, bool)
        ):
            found.append((node.lineno, node.value))
    return found


def offending_literals(source: str) -> list[tuple[int, int | float]]:
    return [
        (line, v) for line, v in numeric_literals(source) if v in ILLUSTRATIVE_VALUES
    ]


def scanned_files() -> list[Path]:
    files: list[Path] = []
    for package in SCANNED_PACKAGES:
        files.extend(sorted((SRC_RALMON / package).rglob("*.py")))
    return files


def test_no_illustrative_clinical_constants_in_core_sources() -> None:
    hits = []
    for path in scanned_files():
        for line, value in offending_literals(path.read_text(encoding="utf-8")):
            hits.append(
                f"{path.relative_to(SRC_RALMON.parent.parent)}:{line}: {value!r}"
            )
    assert hits == []


def test_the_scan_covers_the_registry_loader_and_every_core_package() -> None:
    files = {p.relative_to(SRC_RALMON).as_posix() for p in scanned_files()}
    for package in SCANNED_PACKAGES:
        assert any(f.startswith(f"{package}/") for f in files), package
    for module in ("registry", "templates", "plan", "normalise", "rho", "integrity"):
        assert f"spec/{module}.py" in files


@pytest.mark.parametrize("value", ILLUSTRATIVE_VALUES)
def test_the_scanner_flags_each_illustrative_value_in_every_numeric_form(
    value: int,
) -> None:
    for text in (
        f"x = {value}",
        f"x = {value}.0",
        f"x = -{value}",
        f"f({value})",
        f"x = [{value}]",
    ):
        assert offending_literals(text) != [], text


def test_the_scanner_ignores_docstrings_comments_strings_and_other_numbers() -> None:
    source = '''"""Band 110 to 140, hold 100."""
# 250 mmHg, 50 mmHg
x = "110"
y = 51 + 99 + 109 + 141 + 249 + 1_000
z = True
'''
    assert offending_literals(source) == []
    assert offending_literals("x = 1\n\ny = 110\n") == [(3, 110)]


def test_the_scanner_names_file_and_line() -> None:
    hits = offending_literals("a = 1\nb = 2\nc = 140  # a hit\n")
    assert hits == [(3, 140)]
