"""Coverage of the split calibrator: exact rank bound and seeded Monte Carlo (WS05-T06).

Tests 12 to 14. The tolerance rule of the Monte Carlo tests (four standard errors of the
per-set rates) is fixed before the run and is never widened to pass.
"""

from __future__ import annotations

import math
from fractions import Fraction

import numpy as np
import pytest

import ralmon.conformal as c

from .helpers import episode, episodes_from_scores

N_SETS = 500
N_CAL = 99
N_NEW = 500
LEVELS = (0.05, 0.1, 0.2)


def test_exhaustive_rank_coverage_bound() -> None:
    """Exact, in rationals: P(new score exceeds q) = (n + 1 - k) / (n + 1) <= alpha."""
    for n in range(1, 31):
        cal = c.SplitConformal()
        cal.fit(episodes_from_scores([float(i) for i in range(1, n + 1)]), 0.5)
        for j in range(1, 20):
            alpha = Fraction(j, 20)
            k = math.ceil((n + 1) * (1 - alpha))
            q = cal.quantile(j / 20)
            if k > n:
                assert q == math.inf
                exceed = Fraction(0)
            else:
                assert q == float(k)  # the k-th smallest of 1..n
                exceed = Fraction(n + 1 - k, n + 1)
            assert exceed <= alpha, (n, j)


def _calibration_sets(rng: np.random.Generator) -> np.ndarray:
    return rng.standard_normal((N_SETS, N_CAL))


def _fit_quantiles(scores: np.ndarray) -> dict[float, np.ndarray]:
    out: dict[float, list[float]] = {a: [] for a in LEVELS}
    for row in scores:
        cal = c.SplitConformal()
        cal.fit([episode(i, 0.0, float(r)) for i, r in enumerate(row)], 0.1)
        for a in LEVELS:
            out[a].append(cal.quantile(a))
    return {a: np.asarray(v) for a, v in out.items()}


def _rank_bound(alpha: float) -> float:
    k = math.ceil((N_CAL + 1) * (1 - Fraction(str(alpha))))
    return (N_CAL + 1 - k) / (N_CAL + 1)


def test_monte_carlo_upper_bound_miscoverage_matches_nominal() -> None:
    rng = np.random.default_rng(0)
    cal_scores = _calibration_sets(rng)
    new = rng.standard_normal((N_SETS, N_NEW))
    quantiles = _fit_quantiles(cal_scores)
    for a in LEVELS:
        rates = (new > quantiles[a][:, None]).mean(axis=1)
        se = rates.std(ddof=1) / math.sqrt(N_SETS)
        assert abs(rates.mean() - _rank_bound(a)) <= 4 * se, (a, rates.mean(), se)


def test_monte_carlo_alert_and_nonviolation_rate_at_most_alpha() -> None:
    rng = np.random.default_rng(0)
    cal_scores = _calibration_sets(rng)
    new_r = rng.standard_normal((N_SETS, N_NEW))
    sigma_hat = rng.uniform(-2.0, 0.0, size=(N_SETS, N_NEW))
    quantiles = _fit_quantiles(cal_scores)
    for a in LEVELS:
        emitted = sigma_hat + quantiles[a][:, None] < 0
        false_alarm = emitted & (sigma_hat + new_r >= 0)
        rates = false_alarm.mean(axis=1)
        se = rates.std(ddof=1) / math.sqrt(N_SETS)
        assert rates.mean() <= a + 4 * se, (a, rates.mean(), se)


def test_vectorised_emission_agrees_with_predict() -> None:
    """The Monte Carlo above uses ``quantile``; ``predict`` must give the same emissions."""
    rng = np.random.default_rng(1)
    row = rng.standard_normal(N_CAL)
    cal = c.SplitConformal()
    cal.fit([episode(i, 0.0, float(r)) for i, r in enumerate(row)], 0.1)
    for a in LEVELS:
        q = cal.quantile(a)
        for s_hat in rng.uniform(-2.0, 0.0, size=200):
            assert cal.predict(float(s_hat), a).emitted == bool(s_hat + q < 0)
