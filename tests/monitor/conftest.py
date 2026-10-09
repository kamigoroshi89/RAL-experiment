"""Fixtures of the tests of ``ralmon.monitor`` (WS05-T04): F0 registry and the template library."""

from __future__ import annotations

from typing import Any

import pytest

from .helpers import load_f0, load_lib


@pytest.fixture(scope="session")
def f0() -> Any:
    """The F0 fixture registry with the F0 monitor step (FIXTURE-ONLY, ADR-027)."""
    return load_f0()


@pytest.fixture(scope="session")
def lib(f0: Any) -> Any:
    return load_lib(f0)
