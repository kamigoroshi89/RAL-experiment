"""The toolchain of ADR-016 is configured in pyproject.toml (WS05-T01)."""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
from hypothesis import settings

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 has no tomllib (ADR-042)
    import tomli as tomllib

ROOT = Path(__file__).resolve().parent.parent


def _pyproject() -> dict[str, object]:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)


def _names(specs: list[str]) -> set[str]:
    return {re.match(r"[A-Za-z0-9_.\-]+", s).group(0).lower() for s in specs}  # type: ignore[union-attr]


def test_pyproject_declares_toolchain() -> None:
    data = _pyproject()
    project = data["project"]
    tool = data["tool"]
    assert project["requires-python"].startswith(">=3.10")
    assert tool["mypy"]["strict"] is True
    assert "src/ralmon" in tool["mypy"]["files"]
    assert {"I", "B"} <= set(tool["ruff"]["lint"]["extend-select"])
    assert tool["pytest"]["ini_options"]["testpaths"] == ["tests"]
    assert {"numpy", "pyyaml"} <= _names(project["dependencies"])
    assert {"pytest", "hypothesis", "ruff", "mypy"} <= _names(
        project["optional-dependencies"]["dev"]
    )
    every = list(project["dependencies"])
    for extra in project["optional-dependencies"].values():
        every.extend(extra)
    for spec in every:
        assert re.fullmatch(r"[A-Za-z0-9_.\-]+", spec), f"version specifier in {spec!r}"


def test_hypothesis_profile_is_deterministic() -> None:
    assert settings.default.derandomize is True
    assert settings.default.database is None


def test_rng_fixture_is_seeded_with_zero(rng: np.random.Generator) -> None:
    assert isinstance(rng, np.random.Generator)
    assert rng.random() == np.random.default_rng(0).random()
