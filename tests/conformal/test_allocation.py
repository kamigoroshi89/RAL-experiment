"""Bonferroni alpha allocation over the tests of a patient-day (WS05-T06, test 21)."""

from __future__ import annotations

import math
from fractions import Fraction

import pytest
from hypothesis import given
from hypothesis import strategies as st

import ralmon.conformal as c

from .helpers import episodes_from_scores


def test_bonferroni_allocation() -> None:
    alloc = c.BonferroniAllocation()
    assert alloc.per_test(0.1, 5) == pytest.approx(0.02)
    assert alloc.per_test(0.1, 1) == 0.1
    for bad_n in (0, -1):
        with pytest.raises(ValueError):
            alloc.per_test(0.1, bad_n)
    for bad_alpha in (0.0, 1.0, -0.1, 1.5, math.nan, math.inf):
        with pytest.raises(ValueError):
            alloc.per_test(bad_alpha, 3)


@given(
    alpha=st.integers(1, 99).map(lambda x: x / 100),
    n=st.integers(1, 200),
)
def test_n_times_per_test_is_alpha_total(alpha: float, n: int) -> None:
    assert n * c.BonferroniAllocation().per_test(alpha, n) == pytest.approx(alpha)


def test_exact_split_is_a_fraction_of_the_decimal_literal() -> None:
    alloc = c.BonferroniAllocation()
    assert alloc.per_test_exact(0.05, 10) == Fraction(1, 200)
    assert alloc.per_test_exact(0.1, 3) == Fraction(1, 30)
    assert isinstance(alloc.per_test_exact(0.1, 3), Fraction)


def test_allocated_levels_keep_the_exact_rank_as_fractions() -> None:
    """ADR-030: an allocated level is passed as a Fraction, so its rank is exact.

    For every scanned (alpha_total, n_tests) the rank of the calibrator at the exact allocated
    level equals ``ceil((n + 1) (1 - alpha_total / n_tests))`` computed in rationals.
    """
    alloc = c.BonferroniAllocation()
    for size in (9, 19, 59, 99, 199, 399):
        cal = c.SplitConformal()
        cal.fit(episodes_from_scores([float(i) for i in range(1, size + 1)]), 0.5)
        for hundredths in range(1, 51):
            for n_tests in range(1, 13):
                exact = Fraction(str(hundredths / 100)) / n_tests
                k = math.ceil((size + 1) * (1 - exact))
                expected = math.inf if k > size else float(k)
                level = alloc.per_test_exact(hundredths / 100, n_tests)
                assert cal.quantile(level) == expected, (size, hundredths, n_tests)
