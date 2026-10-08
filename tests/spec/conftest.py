"""Fixtures of the tests of ``ralmon.spec`` (WS05-T03).

The imports of the code under test are made inside the fixtures, so that the tests that only check the
fixture files against the formal documents do not depend on the implementation.
"""

from __future__ import annotations

from typing import Any

import pytest

from .helpers import F0_PATH, REAL_REGISTRY_PATH, STEP_MS


@pytest.fixture
def f0_registry() -> Any:
    """The F0 fixture registry with the F0 monitor step (fixture arithmetic, FIXTURE-ONLY)."""
    from ralmon.spec import load_registry

    return load_registry(F0_PATH, step_ms=STEP_MS, allow_fixture_only=True)


@pytest.fixture
def real_registry() -> Any:
    from ralmon.spec import load_registry

    return load_registry(REAL_REGISTRY_PATH)


@pytest.fixture
def f0_templates(f0_registry: Any) -> Any:
    from ralmon.spec import load_templates

    return load_templates(registry=f0_registry)
