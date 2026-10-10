"""Alpha allocation over the tests of a patient-day (WS05-T06).

Caveat 3 of analisi §4.4: with many tests per patient-day an alpha allocation is required,
otherwise the probability of at least one false predictive alert grows with the number of tests.
"""

from __future__ import annotations

import math
from fractions import Fraction
from typing import Protocol

__all__ = ["AlphaAllocation", "BonferroniAllocation"]


class AlphaAllocation(Protocol):
    def per_test(
        self, alpha_total: float, n_tests: int
    ) -> float: ...  # alarms per patient-day


class BonferroniAllocation:
    """Uniform split ``alpha_per_test = alpha_total / n_tests`` (the union bound).

    With many tests per patient-day an alpha allocation is required. ``n_tests`` is an upper bound
    on the number of tests of the day, fixed before the day from the care plan (it must not depend
    on outcomes or on other patients); each test needs its own calibration set of at least
    ``ceil(1 / alpha_per_test) - 1`` episodes of distinct patients to emit anything. The union
    bound (Boole's inequality) needs no independence among the tests, the instances or the
    calibration sets: the expected number of false predictive alerts of a patient-day is at most
    ``alpha_total``. It bounds neither the alerts of several days (``D`` days give ``D`` times
    ``alpha_total``), nor the missed violations, and the guarantee of each term is marginal over
    the population under exchangeability across episodes, not conditional on the patient.

    ``per_test`` returns a float. A float such as ``0.05 / 3`` has a 16 or 17 digit ``repr`` and can
    move a quantile rank by one; pass the exact level ``per_test_exact`` (a ``Fraction``) to
    ``quantile`` and ``predict`` (ADR-030).
    """

    def per_test_exact(self, alpha_total: float, n_tests: int) -> Fraction:
        """``alpha_total / n_tests`` in exact arithmetic on the decimal literal of ``alpha_total``."""
        if isinstance(n_tests, bool) or not isinstance(n_tests, int) or n_tests < 1:
            raise ValueError(
                f"n_tests must be an integer of at least 1, got {n_tests!r}"
            )
        if not math.isfinite(alpha_total):
            raise ValueError(f"alpha_total must be finite, got {alpha_total!r}")
        total = Fraction(repr(float(alpha_total)))
        if not 0 < total < 1:
            raise ValueError(f"alpha_total must lie in (0, 1), got {alpha_total!r}")
        return total / n_tests

    def per_test(self, alpha_total: float, n_tests: int) -> float:
        return float(self.per_test_exact(alpha_total, n_tests))
