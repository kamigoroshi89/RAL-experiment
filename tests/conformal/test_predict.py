"""``predict``: emission, alpha star as a conformal p-value, rho fields, variants, golden cases.

Tests 3 to 9 and 24 of the task. Fixture-only values; the golden cases are copies of
``docs/formal/golden/conformal.yaml`` in ``tests/fixtures/conformal``.
"""

from __future__ import annotations

import math
from fractions import Fraction
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import ralmon.conformal as c
from ralmon.spec import RhoKind

from .helpers import FIXTURE_SCORES, episodes_from_scores, load_golden, split_on

GOLDEN = load_golden()


def test_infinite_quantile_never_emits() -> None:
    cal = split_on(FIXTURE_SCORES)
    pred = cal.predict(
        -10.0, 0.05
    )  # too few episodes for that level; reported, not hidden
    assert pred.emitted is False
    assert pred.rho is None
    assert pred.variant == "likely"


def test_predict_emits_when_sigma_hat_plus_q_is_negative() -> None:
    cal = split_on(FIXTURE_SCORES)  # q_{0.8} = 0.4
    assert cal.predict(-0.5, 0.2).emitted is True  # -0.5 + 0.4 < 0
    assert (
        cal.predict(-0.4, 0.2).emitted is False
    )  # -0.4 + 0.4 = 0.0, strict inequality


def test_alpha_star_is_the_conformal_p_value() -> None:
    cal = split_on(FIXTURE_SCORES)
    # one score (0.6) is at least 0.5: alpha_star = (1 + 1) / 10
    pred = cal.predict(-0.5, 0.2)
    assert pred.rho is not None and pred.rho.value == pytest.approx(0.8)
    # four scores (0.2, 0.3, 0.4, 0.6) at least 0.2: (4 + 1) / 10
    pred = cal.predict(-0.2, 0.5)
    assert pred.rho is not None and pred.rho.value == pytest.approx(0.5)
    # two scores (0.4, 0.6) at least 0.4: (2 + 1) / 10
    pred = cal.predict(-0.4, 0.3)
    assert pred.rho is not None and pred.rho.value == pytest.approx(0.7)


@given(
    scores=st.lists(st.integers(-10, 10), min_size=1, max_size=25),
    sigma_hat=st.integers(-12, 12),
    twentieths=st.integers(1, 19),
)
@settings(max_examples=300, deadline=None)
def test_emission_iff_alpha_at_least_alpha_star(
    scores: list[int], sigma_hat: int, twentieths: int
) -> None:
    r = [x / 10 for x in scores]
    s_hat = sigma_hat / 10
    cal = c.SplitConformal()
    cal.fit(episodes_from_scores(r), 0.5)
    alpha = twentieths / 20
    n = len(r)
    m = sum(1 for x in r if s_hat + x >= 0)
    alpha_star = Fraction(m + 1, n + 1)
    pred = cal.predict(s_hat, alpha)
    assert pred.emitted == (Fraction(str(alpha)) >= alpha_star)
    if pred.emitted:
        assert pred.rho is not None
        assert pred.rho.value == pytest.approx(float(1 - alpha_star))
    else:
        assert pred.rho is None


def test_rho_declares_kind_guarantee_and_assumptions() -> None:
    cal = split_on(FIXTURE_SCORES)
    pred = cal.predict(-0.5, 0.2)
    rho = pred.rho
    assert rho is not None
    assert rho.kind == RhoKind.PREDICTED
    assert rho.alpha == 0.2
    assert "marginal" in rho.guarantee and "exchangeab" in rho.guarantee
    assumptions = " | ".join(rho.assumptions)
    assert "patient episode" in assumptions and "calibration unit" in assumptions
    assert "exchangeable" in assumptions
    doc = c.SplitConformal.__doc__ or ""
    assert "calibration unit: patient episode" in doc
    assert "marginal over the population" in doc and "exchangeab" in doc
    assert "not conditional on the patient" in doc
    assert "pools all episodes" in doc and "template mix" in doc
    assert "alpha allocation is required" in doc


def test_rho_alpha_is_the_level_used_not_alpha_star() -> None:
    cal = split_on(FIXTURE_SCORES)
    pred = cal.predict(-0.5, Fraction(3, 10))
    assert pred.rho is not None
    assert pred.rho.alpha == 0.3
    assert pred.rho.value == pytest.approx(
        0.8
    )  # alpha_star 0.2 is 1 - value, not stored


def test_variant_possible_follows_ws01_t06() -> None:
    """Lower-quantile form of Proposition 1b (golden C-3), not the symmetric form."""
    case = GOLDEN["C-3"]
    cal = split_on(case["inputs"]["scores_sorted"])
    alpha = case["inputs"]["alpha"]
    assert cal.quantile_lower(alpha) == case["inputs"]["q_lower"]
    for row in case["expected"]["predictions"]:
        pred = cal.predict(row["sigma_hat"], alpha, variant="possible")
        assert pred.variant == "possible"
        assert pred.emitted == row["emitted_lower_quantile_form"]
        # the symmetric form of the contract text disagrees on the first row
        symmetric = row["sigma_hat"] - cal.quantile(alpha) < 0
        assert symmetric == row["emitted_symmetric_form"]
        if pred.emitted:
            assert pred.rho is not None
            assert pred.rho.value == pytest.approx(row["one_minus_alpha_star"])
            assert pred.rho.alpha == alpha
        else:
            assert pred.rho is None
    first = cal.predict(0.15, alpha, variant="possible")
    assert first.emitted is True
    assert (
        cal.predict(0.15, alpha).emitted is False
    )  # variant "likely": 0.15 + 0.09 >= 0


def test_variant_possible_on_the_task_fixture() -> None:
    """On R = [-0.2 .. 0.6] the lower quantile at 0.2 is -0.1: sigma_hat = 0.3 is not emitted."""
    cal = split_on(FIXTURE_SCORES)
    assert cal.quantile_lower(0.2) == -0.1
    assert cal.predict(0.3, 0.2, variant="possible").emitted is False  # 0.3 - 0.1 >= 0
    assert cal.predict(0.3, 0.2, variant="likely").emitted is False
    assert cal.predict(0.05, 0.2, variant="possible").emitted is True  # 0.05 - 0.1 < 0


def test_variant_possible_with_infinite_lower_quantile_flags_everything() -> None:
    cal = split_on(FIXTURE_SCORES)
    pred = cal.predict(0.3, 0.05, variant="possible")  # j = 0: q_lower = -inf
    assert pred.emitted is True
    assert pred.rho is not None and pred.rho.value == pytest.approx(0.0)


def test_unknown_variant_is_refused() -> None:
    cal = split_on(FIXTURE_SCORES)
    with pytest.raises(ValueError):
        cal.predict(0.0, 0.2, variant="symmetric")  # type: ignore[arg-type]


def _inf(x: Any) -> float:
    return float(x)


@pytest.mark.parametrize("case_id", ["C-1", "C-2", "C-4", "C-5"])
def test_golden_conformal_cases(case_id: str) -> None:
    case = GOLDEN[case_id]
    inputs, expected = case["inputs"], case["expected"]
    if case_id == "C-1":
        cal = split_on(inputs["scores_sorted"])
        for row in expected["upper_quantile"]:
            assert cal.quantile(row["alpha"]) == _inf(row["value"])
        for row in expected["lower_quantile"]:
            assert cal.quantile_lower(row["alpha"]) == _inf(row["value"])
        ident = expected["exact_coverage_identity"]
        n = inputs["n"]
        assert Fraction(ident["k"], n + 1) == Fraction(ident["p_new_score_at_most_q"])
    elif case_id == "C-2":
        cal = split_on(inputs["scores_sorted"])
        alpha = inputs["alpha"]
        for row in expected["predictions"]:
            pred = cal.predict(row["sigma_hat"], alpha, variant=inputs["variant"])
            assert pred.emitted == row["emitted"]
            if row["rho"] is None:
                assert pred.rho is None
            else:
                rho = pred.rho
                assert rho is not None
                want = row["rho"]
                assert rho.kind == RhoKind(want["kind"])
                assert rho.value == pytest.approx(want["value"])
                assert rho.alpha == want["alpha"]
                assert rho.guarantee == want["guarantee"]
                assert list(rho.assumptions) == want["assumptions"]
    elif case_id == "C-4":
        cal = split_on(inputs["scores_sorted"])
        up, lo = expected["upper"], expected["lower"]
        assert cal.quantile(up["alpha"]) == up["exact_value"]  # not the float-rank 0.60
        assert (
            cal.quantile_lower(lo["alpha"]) == lo["exact_value"]
        )  # not the float-rank 0.28
    else:
        for row in expected["minimum_n"]:
            alpha = row["alpha"]
            below = split_on([float(i) for i in range(row["n_min"] - 1)])
            at = split_on([float(i) for i in range(row["n_min"])])
            assert below.quantile(alpha) == math.inf
            assert math.isfinite(at.quantile(alpha))
        small = expected["small_n"]
        cal = split_on(GOLDEN["C-1"]["inputs"]["scores_sorted"])
        assert cal.quantile(small["alpha"]) == math.inf
        assert cal.quantile_lower(small["alpha"]) == -math.inf
        assert small["alert_possible"] is False
        assert cal.predict(-100.0, small["alpha"]).emitted is False
        alloc = expected["allocation"]
        bonferroni = c.BonferroniAllocation()
        assert (
            bonferroni.per_test(inputs["alpha_total"], inputs["n_tests"])
            == (alloc["alpha_per_test"])
        )
        assert bonferroni.per_test_exact(
            inputs["alpha_total"], inputs["n_tests"]
        ) == Fraction(alloc["alpha_per_test_exact"])


def test_ablation_a1_point_forecast_is_a_zero_score_calibrator() -> None:
    """A1 (analisi 5.6): all scores 0.0 gives the overconfident rho of a point forecast."""
    cal = c.SplitConformal()
    cal.fit(
        episodes_from_scores([0.0] * 9, sigma_hat=0.0),
        0.2,
    )
    assert cal.quantile(0.2) == 0.0
    assert cal.predict(-0.1, 0.2).emitted is True
    assert cal.predict(0.0, 0.2).emitted is False  # emits exactly when sigma_hat < 0
    assert cal.predict(0.1, 0.2).emitted is False
    pred = cal.predict(-0.1, 0.2)
    assert pred.rho is not None
    assert pred.rho.value == pytest.approx(0.9)  # alpha_star = (0 + 1) / 10
