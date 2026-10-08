"""``normalise`` (02-interfaces.md#template, docs/formal/04-normalisation-ranking.md section 2).

Tests 1 to 5 of WS05-T03 plus the properties P-N1 to P-N9 of the formal document and the robust-input
table (a bad argument raises ``ValueError``, never a raw ``TypeError`` or ``OverflowError``).
"""

from __future__ import annotations

import math
import sys
from decimal import Decimal
from fractions import Fraction
from typing import Any

import numpy as np
import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from ralmon.spec import normalise

from .helpers import GOLDEN_RANKING_COPY, GOLDEN_TEMPLATES_COPY, read_yaml

RANKING = read_yaml(GOLDEN_RANKING_COPY)
N_CASES = [case for case in RANKING if case["id"].startswith("N-")]
TEMPLATE_CASES = read_yaml(GOLDEN_TEMPLATES_COPY)["cases"]

FLOAT_MIN_NORMAL = sys.float_info.min


# --- test 1: golden cases ---------------------------------------------------------------


@pytest.mark.parametrize("case", N_CASES, ids=[c["id"] for c in N_CASES])
def test_normalise_matches_ranking_golden(case: dict[str, Any]) -> None:
    """Handles the three shapes of docs/formal/04-normalisation-ranking.md section 2.2:
    a value (N-1 to N-6, N-10), a list over ``inputs.calls`` (N-7), ``expected.error`` (N-8, N-9)."""
    inputs, expected = case["inputs"], case["expected"]
    assert inputs["call"] == "normalise"
    if "error" in expected:
        assert expected["error"] == "ValueError"
        calls = [{"sigma_raw": inputs["sigma_raw"], "scale": inputs["scale"]}]
        calls += list(expected.get("also_raises", []))
        for call in calls:
            with pytest.raises(ValueError):
                normalise(call["sigma_raw"], call["scale"])
        return
    if "calls" in inputs:
        calls, values = list(inputs["calls"]), list(expected["sigma_norm"])
        assert len(calls) == len(values) == 2
    else:
        calls, values = [inputs], [expected["sigma_norm"]]
    for call, value in zip(calls, values, strict=True):
        result = normalise(call["sigma_raw"], call["scale"])
        assert type(result) is float
        assert result == value


def test_normalise_golden_n10_is_the_scale_equivariant_partner_of_n1() -> None:
    by_id = {c["id"]: c for c in N_CASES}
    n1, n10 = by_id["N-1"]["inputs"], by_id["N-10"]["inputs"]
    k = n10["k"]
    assert n10["equivariance_partner"] == "N-1"
    assert normalise(k * n1["sigma_raw"], k * n1["scale"]) == normalise(
        n1["sigma_raw"], n1["scale"]
    )


@pytest.mark.parametrize("case", TEMPLATE_CASES, ids=[c["id"] for c in TEMPLATE_CASES])
def test_normalise_matches_templates_golden(
    case: dict[str, Any], f0_registry: Any
) -> None:
    """Each of the 26 template cases: the F0 scale of the template turns ``sigma_raw`` into
    ``sigma_norm`` (a failed guard, ``-inf``, gives -1.0) and the sign agrees with the Boolean verdict."""
    template = case["inputs"]["template"]
    scale_entry = f0_registry.get(f"scale_{template}")
    expected = case["expected"]
    assert scale_entry.unit == expected["unit"]
    result = normalise(expected["sigma_raw"], scale_entry.value)
    assert result == pytest.approx(expected["sigma_norm"], rel=1e-15, abs=0.0)
    assert (result >= 0.0) == (expected["boolean"] == "satisfied")
    if "workshop_form" in expected:
        workshop = expected["workshop_form"]
        assert (
            normalise(workshop["sigma_raw"], scale_entry.value)
            == workshop["sigma_norm"]
        )


def test_every_golden_case_of_the_normalisation_tests_is_collected() -> None:
    """The ids of the parametrised golden tests are exactly the case ids of the two golden files."""
    assert [c["id"] for c in N_CASES] == [f"N-{i}" for i in range(1, 11)]
    assert len(TEMPLATE_CASES) == 26
    assert len({c["id"] for c in TEMPLATE_CASES}) == 26


# --- test 2 ------------------------------------------------------------------------------


def test_normalise_hand_values() -> None:
    assert normalise(-12.0, 20.0) == -0.6
    assert normalise(15.0, 20.0) == 0.75
    assert normalise(-60.0, 20.0) == -1.0  # clipped, G-RANGE-5
    assert normalise(1_500_000.0, 1_800_000.0) == pytest.approx(0.8333, abs=1e-4)
    assert normalise(-180_000.0, 300_000.0) == -0.6  # G-INT-2
    assert normalise(-1.0, 1.0) == -1.0  # G-COUNT-1
    assert normalise(60.0, 20.0) == 1.0  # clipped above
    assert normalise(0.0, 20.0) == 0.0  # tie, G-RANGE-4


def test_normalise_returns_a_python_float_for_every_real_argument() -> None:
    for value in (
        normalise(1, 2),
        normalise(0, 1),
        normalise(np.float64(-12.0), np.float64(20.0)),
        normalise(np.int64(15), np.int32(20)),
        normalise(np.float32(0.5), 1),
        normalise(Fraction(-12), Fraction(20)),
    ):
        assert type(value) is float
    assert normalise(np.int64(15), np.int32(20)) == 0.75
    assert normalise(Fraction(-12), Fraction(20)) == -0.6


# --- test 3 ------------------------------------------------------------------------------


def test_normalise_infinities_and_nan() -> None:
    assert normalise(-math.inf, 20.0) == -1.0
    assert normalise(math.inf, 20.0) == 1.0
    assert normalise(-math.inf, 1e-300) == -1.0
    assert normalise(math.inf, 10**400) == 1.0
    with pytest.raises(ValueError, match="sigma_raw"):
        normalise(math.nan, 20.0)
    with pytest.raises(ValueError, match="sigma_raw"):
        normalise(float("-nan"), 20.0)
    with pytest.raises(ValueError, match="sigma_raw"):
        normalise(np.float64("nan"), 20.0)


# --- test 4 ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "scale",
    [
        0.0,
        -0.0,
        -20.0,
        -1e-300,
        -math.inf,
        math.inf,
        math.nan,
        0,
        -1,
        -(10**400),
        np.float64(0.0),
        np.float64("nan"),
        Fraction(0),
    ],
)
def test_normalise_rejects_nonpositive_or_nonfinite_scale(scale: Any) -> None:
    with pytest.raises(ValueError, match="scale"):
        normalise(5.0, scale)
    with pytest.raises(ValueError, match="scale"):
        normalise(math.inf, scale)  # the scale is checked before the infinity shortcut


def test_normalise_accepts_the_smallest_positive_scale() -> None:
    assert normalise(5e-324, 5e-324) == 1.0
    assert normalise(-5e-324, 5e-324) == -1.0
    assert normalise(1e-300, 1e300) == 0.0  # underflow of the quotient, not an error


# --- bad types and huge integers ---------------------------------------------------------


BAD_NUMBERS: list[Any] = [
    None,
    True,
    False,
    np.True_,
    np.False_,
    "1.0",
    "nan",
    b"1",
    bytearray(b"1"),
    [1.0],
    (1.0,),
    {"a": 1},
    {1.0},
    1 + 2j,
    object(),
    Decimal(1),
    Decimal("NaN"),
    lambda: 1.0,
]


@pytest.mark.parametrize(
    "bad",
    BAD_NUMBERS,
    ids=[type(b).__name__ + str(i) for i, b in enumerate(BAD_NUMBERS)],
)
def test_normalise_rejects_non_numbers_with_value_error(bad: Any) -> None:
    """A bool is not a number here (a flag passed for a robustness is a caller bug); no raw TypeError."""
    with pytest.raises(ValueError, match="sigma_raw"):
        normalise(bad, 20.0)
    with pytest.raises(ValueError, match="scale"):
        normalise(1.0, bad)


def test_normalise_handles_integers_beyond_the_float_range_exactly() -> None:
    big = 10**400
    assert normalise(big, 20.0) == 1.0
    assert normalise(-big, 20.0) == -1.0
    assert normalise(big, big) == 1.0
    assert normalise(-big, big) == -1.0
    assert normalise(big // 10, big) == 0.1
    assert normalise(-(big // 4), big) == -0.25
    assert normalise(1.0, big) == 0.0
    assert normalise(-1.0, big) == 0.0
    assert normalise(1, big) == 0.0
    assert normalise(2 * 10**399, 10**400) == 0.2
    assert (
        normalise(10**399, 5.0) == 1.0
    )  # float scale, huge int sigma (OverflowError path)
    assert normalise(10**330, 10**330 + 1) == pytest.approx(1.0, abs=1e-12)


def test_normalise_never_raises_zero_division_or_overflow() -> None:
    for sigma in (1e308, -1e308, 5e-324, 10**400, -(10**400), 0):
        for scale in (5e-324, 1e-300, 1.0, 1e308, 10**400):
            result = normalise(sigma, scale)
            assert -1.0 <= result <= 1.0


# --- test 5 and the properties of the formal document ------------------------------------

POSITIVE = st.floats(
    min_value=0.0, exclude_min=True, allow_nan=False, allow_infinity=False
)
SIGMA = st.floats(allow_nan=False, allow_infinity=True)
SIGMA_FINITE = st.floats(allow_nan=False, allow_infinity=False)


@settings(max_examples=120)
@given(a=SIGMA, b=SIGMA, s=POSITIVE)
def test_normalise_is_monotone_bounded_and_sign_preserving(
    a: float, b: float, s: float
) -> None:
    lo, hi = min(a, b), max(a, b)
    assert normalise(lo, s) <= normalise(hi, s)  # P-N3
    for x in (a, b):
        value = normalise(x, s)
        assert -1.0 <= value <= 1.0  # P-N1
        if x == 0.0 or (abs(x) >= 1e-300 and s <= 1e12):  # P-N2: avoid underflow
            assert (value >= 0.0) == (x >= 0.0)
            assert (value < 0.0) == (x < 0.0)
            assert (value == 0.0) == (x == 0.0)


@settings(max_examples=120)
@given(sigma=SIGMA_FINITE, s=POSITIVE)
def test_normalise_identity_zone_and_saturation(sigma: float, s: float) -> None:
    value = normalise(sigma, s)
    if abs(sigma) <= s:  # P-N5
        assert value == sigma / s
    if sigma <= -s:  # P-N6
        assert value == -1.0
    if sigma >= s:
        assert value == 1.0


@settings(max_examples=120)
@given(s=POSITIVE)
def test_normalise_infinities_property(s: float) -> None:
    assert normalise(-math.inf, s) == -1.0  # P-N7
    assert normalise(math.inf, s) == 1.0


@settings(max_examples=120)
@given(
    sigma=st.integers(min_value=-(10**6), max_value=10**6),
    s=st.integers(min_value=1, max_value=10**6),
    k=st.integers(min_value=1, max_value=10**3),
)
def test_normalise_is_scale_equivariant_for_integer_valued_floats(
    sigma: int, s: int, k: int
) -> None:
    """P-N4 in the exact regime: integer-valued floats, every product below 2**53."""
    assert normalise(float(k * sigma), float(k * s)) == normalise(
        float(sigma), float(s)
    )


@settings(max_examples=120)
@given(sigma=SIGMA_FINITE, s=POSITIVE, k=POSITIVE)
def test_normalise_is_scale_equivariant_with_tolerance(
    sigma: float, s: float, k: float
) -> None:
    assume(math.isfinite(k * s) and k * s >= FLOAT_MIN_NORMAL)
    assume(math.isfinite(k * sigma))
    assert normalise(k * sigma, k * s) == pytest.approx(
        normalise(sigma, s), rel=1e-12, abs=1e-12
    )


@settings(max_examples=120)
@given(
    s=st.one_of(st.just(0.0), st.floats(max_value=0.0, allow_nan=False)), sigma=SIGMA
)
def test_normalise_nonpositive_scale_always_raises(s: float, sigma: float) -> None:
    with pytest.raises(ValueError):  # P-N8
        normalise(sigma, s)


@settings(max_examples=120)
@given(values=st.lists(SIGMA, min_size=3, max_size=3), s=POSITIVE)
def test_normalise_encloses_interval_values(values: list[float], s: float) -> None:
    """P-N9: the normalised ends of an interval enclose the normalised value of any point inside."""
    lo, x, hi = sorted(values)
    assert normalise(lo, s) <= normalise(x, s) <= normalise(hi, s)


# --- error messages name the argument ---------------------------------------------------


def test_error_messages_name_the_argument_and_the_rule() -> None:
    with pytest.raises(ValueError, match=r"scale.*positive"):
        normalise(1.0, 0.0)
    with pytest.raises(ValueError, match=r"sigma_raw.*NaN"):
        normalise(math.nan, 1.0)
    with pytest.raises(ValueError, match=r"sigma_raw.*number"):
        normalise("x", 1.0)


def test_the_exact_path_clips_quotients_of_integers_beyond_the_float_range() -> None:
    """The quotient of an integer above the largest float by a float scale is computed exactly."""
    above = 2**1024  # larger than the largest float
    assert normalise(above, 1.7e308) == 1.0  # the exact quotient is about 1.06: clipped
    assert normalise(-above, 1.7e308) == -1.0
    assert normalise(above, 1e300) == 1.0
    assert normalise(-above, 1e300) == -1.0
    assert (
        normalise(5.0, above) == 5 / above
    )  # the correctly rounded quotient of the exact values
    assert normalise(-5.0, above) == -5 / above
