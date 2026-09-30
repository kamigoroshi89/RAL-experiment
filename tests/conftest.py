"""Shared test configuration: deterministic Hypothesis profile and seeded RNG."""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import settings

settings.register_profile("ralmon", derandomize=True, database=None)
settings.load_profile("ralmon")


@pytest.fixture
def rng() -> np.random.Generator:
    """Random generator with the default seed 0 (01-conventions.md sections 2 and 3)."""
    return np.random.default_rng(0)
