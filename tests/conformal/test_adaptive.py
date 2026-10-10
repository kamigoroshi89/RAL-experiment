"""Adaptive conformal calibrator (ablation A6) and its per-patient forks (WS05-T06).

Tests 15 to 20 of the task. The recursion is that of the cited work on adaptive conformal
inference, unverified until the human check of WS03-T06. Values are fixture-only.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

import ralmon.conformal as c

from .helpers import FIXTURE_SCORES, episode, episodes_from_scores


def fitted(gamma: float = 0.1, alpha: float = 0.2, **kw: object) -> c.AdaptiveConformal:
    cal = c.AdaptiveConformal(gamma=gamma, **kw)  # type: ignore[arg-type]
    cal.fit(episodes_from_scores(FIXTURE_SCORES), alpha)
    return cal


def test_adaptive_alpha_recursion_hand_values() -> None:
    cal = fitted()
    assert cal.mode == "adaptive"
    assert cal.alpha_t == 0.2
    assert cal.quantile(0.2) == 0.4
    miss = fitted()
    miss.update(0.0, 0.9)  # R = 0.9 above the quantile 0.4
    assert miss.alpha_t == pytest.approx(0.12)  # 0.2 + 0.1 * (0.2 - 1)
    covered = fitted()
    covered.update(0.0, 0.0)
    assert covered.alpha_t == pytest.approx(0.22)  # 0.2 + 0.1 * 0.2


def test_adaptive_gamma_is_explicit() -> None:
    with pytest.raises(TypeError):
        c.AdaptiveConformal()  # type: ignore[call-arg]
    for bad in (0.0, -0.1, math.nan, math.inf):
        with pytest.raises(ValueError):
            c.AdaptiveConformal(gamma=bad)
    for bad_window in (0, -3):
        with pytest.raises(ValueError):
            c.AdaptiveConformal(gamma=0.1, window=bad_window)


def test_adaptive_update_extends_the_score_set() -> None:
    cal = fitted()
    assert cal.n_scores == 9
    q_before = cal.quantile(0.2)
    cal.update(0.0, 0.9)
    assert cal.n_scores == 10
    assert cal.quantile(0.2) != q_before or cal.alpha_t != 0.2
    # alpha_t = 0.12 on ten scores: k = ceil(11 * 0.88) = 10, the largest score 0.9
    assert cal.quantile(0.2) == 0.9


def test_adaptive_window_limits_the_retained_scores() -> None:
    cal = fitted(window=9)
    cal.update(0.0, 5.0)
    assert cal.n_scores == 9
    # alpha_t = 0.12: the largest of nine retained scores is the new 5.0, and the lower rank
    # j = floor(10 * 0.12) = 1 is the smallest retained score; the oldest score (-0.2) left
    assert cal.quantile(0.2) == 5.0
    assert cal.quantile_lower(0.2) == -0.1
    unbounded = fitted()
    for _ in range(5):
        unbounded.update(0.0, 0.0)
    assert unbounded.n_scores == 14


def test_adaptive_infinite_conventions() -> None:
    low = fitted(gamma=0.5)
    low.update(0.0, 0.9)  # miss: 0.2 + 0.5 * (0.2 - 1) = -0.2
    assert low.alpha_t == pytest.approx(-0.2)  # stored unclipped
    assert low.quantile(0.2) == math.inf  # no alert
    assert low.predict(-10.0, 0.2).emitted is False
    high = fitted(gamma=5.0)
    high.update(0.0, 0.0)  # covered: 0.2 + 5 * 0.2 = 1.2
    assert high.alpha_t == pytest.approx(1.2)
    assert high.quantile(0.2) == -math.inf
    assert high.predict(10.0, 0.2).emitted is True  # 10 + (-inf) < 0


def test_adaptive_quantile_is_tied_to_the_fitted_level() -> None:
    cal = fitted()
    with pytest.raises(ValueError):
        cal.quantile(0.1)
    with pytest.raises(ValueError):
        cal.predict(0.0, 0.3)


def test_adaptive_guarantee_string_is_empirical() -> None:
    pred = fitted().predict(-0.5, 0.2)
    assert pred.emitted is True and pred.rho is not None
    g = pred.rho.guarantee
    assert "empirical" in g and "no finite-sample" in g
    assert "distribution-free" not in g
    assert pred.rho.alpha == 0.2
    assert "patient episode" in " ".join(pred.rho.assumptions)


def test_adaptive_docstring_states_the_reporting_rules() -> None:
    doc = c.AdaptiveConformal.__doc__ or ""
    doc = " ".join(doc.split())  # docstring line breaks do not matter
    assert "calibration unit: patient episode" in doc
    assert "ref-needed: WS03" in doc
    assert "alpha allocation is required" in doc


def test_adaptive_recovers_coverage_under_shift() -> None:
    rng = np.random.default_rng(0)
    r = np.concatenate([rng.standard_normal(1000), rng.normal(1.0, 1.0, 1000)])
    alpha, gamma = 0.1, 0.05  # test-only values
    split = c.SplitConformal()
    split.fit([episode(i, 0.0, float(x)) for i, x in enumerate(r[:500])], alpha)
    adaptive = c.AdaptiveConformal(gamma=gamma)
    adaptive.fit([episode(i, 0.0, float(x)) for i, x in enumerate(r[:500])], alpha)
    q_split = split.quantile(alpha)
    miss_split = miss_adaptive = 0
    for i in range(500, 2000):
        x = float(r[i])
        if i >= 1500:
            miss_split += x > q_split
            miss_adaptive += x > adaptive.quantile(alpha)
        adaptive.update(0.0, x)
    split_rate, adaptive_rate = miss_split / 500, miss_adaptive / 500
    assert abs(adaptive_rate - alpha) < abs(split_rate - alpha), (
        adaptive_rate,
        split_rate,
    )


def test_fork_states_are_independent() -> None:
    parent = fitted()
    parent.update(0.0, 0.9)  # the parent has adapted; forks start from the population
    first, second = parent.fork(), parent.fork()
    assert first.alpha_t == 0.2 and first.n_scores == 9
    assert first is not second and first.mode == "adaptive"
    first.update(0.0, 0.9)
    assert first.alpha_t == pytest.approx(0.12) and first.n_scores == 10
    assert second.alpha_t == 0.2 and second.n_scores == 9
    assert parent.alpha_t == pytest.approx(0.12) and parent.n_scores == 10
    assert second.quantile(0.2) == 0.4


def test_adaptive_fit_resets_and_records_model_version() -> None:
    cal = fitted()
    cal.update(0.0, 0.9)
    cal.fit(episodes_from_scores(FIXTURE_SCORES), 0.2, model_version="v7")
    assert cal.alpha_t == 0.2 and cal.n_scores == 9
    assert cal.calibrated_for == "v7"
    assert cal.fork().calibrated_for == "v7"


def test_adaptive_unfitted_refuses() -> None:
    cal = c.AdaptiveConformal(gamma=0.1)
    with pytest.raises(RuntimeError):
        cal.quantile(0.2)
    with pytest.raises(RuntimeError):
        cal.update(0.0, 0.0)
