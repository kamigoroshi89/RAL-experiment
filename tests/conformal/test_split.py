"""Split conformal calibrator: score, finite-sample quantile, validation, versions (WS05-T06).

Tests 1, 2, 10, 11, 22 and 23 of the task. Fixture-only values; no clock, no network.
"""

from __future__ import annotations

import importlib
import math
from fractions import Fraction

import pytest

import ralmon.conformal as c

from .helpers import FIXTURE_SCORES, episode, episodes_from_scores, split_on


def test_score_is_one_sided_true_minus_hat() -> None:
    ep = episode(0, sigma_hat=0.5, sigma_true=0.3)
    score = importlib.import_module("ralmon.conformal.scores").score
    assert score(ep) == pytest.approx(-0.2)  # not the absolute value 0.2


def test_split_quantile_finite_sample_rank() -> None:
    cal = split_on(FIXTURE_SCORES)
    assert cal.quantile(0.5) == 0.1  # k = 5
    assert cal.quantile(0.3) == 0.3  # k = 7
    assert cal.quantile(0.2) == 0.4  # k = 8
    assert cal.quantile(0.1) == 0.6  # k = 9
    assert cal.quantile(0.05) == math.inf  # k = 10 > n


def test_split_quantile_float_boundary_level() -> None:
    """Flag of the WS01-T06 review: the boundary level of this fixture is 0.7.

    ``10 * (1 - 0.7)`` is 3.0000000000000004 in doubles (rank 4 instead of 3), so a float
    product returns 0.1; the exact rank 3 returns the third smallest score, 0.0.
    """
    cal = split_on(FIXTURE_SCORES)
    assert cal.quantile(0.7) == 0.0


def test_rank_is_exact_for_decimal_levels_on_a_grid() -> None:
    """The rank follows the decimal literal of the level (docs/formal/06 section 4.4)."""
    for n in range(1, 61):
        scores = [float(i) for i in range(1, n + 1)]
        cal = split_on(scores)
        for hundredths in range(1, 100):
            alpha = hundredths / 100
            exact = Fraction(str(alpha))
            k = math.ceil((n + 1) * (1 - exact))
            expected = math.inf if k > n else float(k)
            assert cal.quantile(alpha) == expected, (n, alpha)


def test_quantile_accepts_an_exact_fraction_level() -> None:
    cal = split_on(FIXTURE_SCORES)
    assert cal.quantile(Fraction(7, 10)) == 0.0
    assert cal.quantile(Fraction(1, 5)) == 0.4


def test_lower_quantile_follows_the_exact_rank() -> None:
    cal = split_on(FIXTURE_SCORES)
    assert cal.quantile_lower(0.2) == -0.1  # j = 2
    assert cal.quantile_lower(0.1) == -0.2  # j = 1
    assert cal.quantile_lower(0.05) == -math.inf  # j = 0


def test_lower_quantile_is_minus_the_upper_quantile_of_flipped_scores() -> None:
    """Duality of docs/formal/06 section 5.7, checked on the fixture."""
    cal = split_on(FIXTURE_SCORES)
    flipped = c.SplitConformal()
    flipped.fit(episodes_from_scores([-r for r in FIXTURE_SCORES]), 0.2)
    for alpha in (0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 0.9):
        assert cal.quantile_lower(alpha) == -flipped.quantile(alpha)


def test_alpha_and_episode_validation() -> None:
    cal = split_on(FIXTURE_SCORES)
    for bad in (0.0, 1.0, -0.1, 1.5, math.nan):
        with pytest.raises(ValueError):
            cal.quantile(bad)
        with pytest.raises(ValueError):
            cal.quantile_lower(bad)
        with pytest.raises(ValueError):
            cal.predict(0.0, bad)
    fresh = c.SplitConformal()
    with pytest.raises(ValueError):
        fresh.fit([], 0.2)
    for bad in (0.0, 1.0, -0.1):
        with pytest.raises(ValueError):
            fresh.fit(episodes_from_scores(FIXTURE_SCORES), bad)
    with pytest.raises(ValueError):
        fresh.fit([episode(0, 0.0, math.nan)], 0.2)
    with pytest.raises(ValueError):
        fresh.fit([episode(0, math.inf, 0.0)], 0.2)


def test_unfitted_calibrator_refuses_to_answer() -> None:
    fresh = c.SplitConformal()
    with pytest.raises(RuntimeError):
        fresh.quantile(0.2)
    with pytest.raises(RuntimeError):
        fresh.predict(0.0, 0.2)


def test_split_update_is_a_noop() -> None:
    cal = split_on(FIXTURE_SCORES)
    before_q = [cal.quantile(a) for a in (0.1, 0.2, 0.5)]
    before_p = cal.predict(-0.5, 0.2)
    cal.update(0.0, 5.0)
    assert [cal.quantile(a) for a in (0.1, 0.2, 0.5)] == before_q
    assert cal.predict(-0.5, 0.2) == before_p
    assert cal.n_scores == len(FIXTURE_SCORES)


def test_split_mode_and_input_order_independence() -> None:
    cal = split_on(FIXTURE_SCORES)
    assert cal.mode == "split"
    shuffled = c.SplitConformal()
    shuffled.fit(episodes_from_scores(list(reversed(FIXTURE_SCORES))), 0.2)
    assert shuffled.quantile(0.2) == cal.quantile(0.2)


def test_fit_records_model_version() -> None:
    cal = c.SplitConformal()
    eps = episodes_from_scores(FIXTURE_SCORES)
    assert cal.calibrated_for is None
    cal.fit(eps, 0.2, model_version="v1")
    assert cal.calibrated_for == "v1"
    cal.fit(eps, 0.2, model_version="v2")
    assert cal.calibrated_for == "v2"
    cal.fit(eps, 0.2)
    assert cal.calibrated_for is None  # calibrated for no particular model


def test_fit_without_model_version_leaves_none() -> None:
    cal = c.SplitConformal()
    cal.fit(episodes_from_scores(FIXTURE_SCORES), 0.2)
    assert cal.calibrated_for is None


def test_model_version_is_keyword_only() -> None:
    cal = c.SplitConformal()
    with pytest.raises(TypeError):
        cal.fit(episodes_from_scores(FIXTURE_SCORES), 0.2, "v1")


def test_no_hidden_randomness() -> None:
    eps = episodes_from_scores(FIXTURE_SCORES)
    a, b = c.SplitConformal(), c.SplitConformal()
    a.fit(eps, 0.2)
    b.fit(eps, 0.2)
    levels = (0.05, 0.1, 0.2, 0.3, 0.5, 0.7)
    assert [a.quantile(x) for x in levels] == [b.quantile(x) for x in levels]
    with pytest.raises(TypeError):
        c.SplitConformal(rng=object())  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        c.SplitConformal(seed=0)  # type: ignore[call-arg]


def test_levels_of_the_wrong_type_are_refused() -> None:
    cal = split_on(FIXTURE_SCORES)
    for bad in ("0.1", b"0.1", True, False, 1, None, [0.1]):
        with pytest.raises(ValueError):
            cal.quantile(bad)  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            cal.quantile_lower(bad)  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            cal.predict(0.0, bad)  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            c.SplitConformal().fit(episodes_from_scores(FIXTURE_SCORES), bad)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        c.BonferroniAllocation().per_test("0.1", 3)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        c.BonferroniAllocation().per_test(True, 3)  # type: ignore[arg-type]
