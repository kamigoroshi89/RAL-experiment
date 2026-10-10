"""Calibration episodes, the one-sided score and the exact quantile ranks (WS05-T06).

The calibration unit is the patient episode (02-interfaces.md#conformal-calibrator, rule 1), never
the time step. The score is one-sided, ``R = sigma_true - sigma_hat``: only the direction
``sigma_true < sigma_hat`` matters for a warning. Ranks are computed in integer arithmetic from the
decimal literal of the level (docs/formal/06-rho-proposition1.md section 4.4, ADR-030): a floating
point product moves the rank for levels such as 0.7 or 0.41, and so does exact arithmetic on the
binary value of the float.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from ralmon.spec import TemplateId

__all__ = [
    "CalibrationEpisode",
    "Level",
    "exact_level",
    "lower_quantile",
    "residual",
    "score",
    "scores_of",
    "upper_quantile",
]

Level = float | Fraction  # a level is a decimal literal (float) or an exact fraction


@dataclass(frozen=True, slots=True)
class CalibrationEpisode:
    patient_id: str
    day_index: int
    template: TemplateId
    sigma_hat: float  # predicted normalised robustness
    sigma_true: (
        float  # normalised robustness of the completed trace (latent or measured)
    )


def residual(sigma_hat: float, sigma_true: float) -> float:
    """``R = sigma_true - sigma_hat`` of one episode, both values finite."""
    if not (math.isfinite(sigma_hat) and math.isfinite(sigma_true)):
        raise ValueError("sigma_hat and sigma_true must be finite")
    return sigma_true - sigma_hat


def score(episode: CalibrationEpisode) -> float:
    """The one-sided nonconformity score ``R = sigma_true - sigma_hat`` (not an absolute value)."""
    try:
        return residual(episode.sigma_hat, episode.sigma_true)
    except ValueError:
        raise ValueError(
            f"calibration episode of patient {episode.patient_id!r} day {episode.day_index} "
            "has a non-finite sigma"
        ) from None


def scores_of(episodes: Sequence[CalibrationEpisode]) -> list[float]:
    """Scores of ``episodes`` in the given order; an empty calibration set is refused."""
    if len(episodes) == 0:
        raise ValueError(
            "a conformal calibrator needs at least one calibration episode"
        )
    return [score(e) for e in episodes]


def exact_level(alpha: Level) -> Fraction:
    """The level as an exact fraction, validated to lie in the open interval (0, 1).

    A float (not a bool, a string or an int) is read as the shortest decimal that round-trips (``Fraction(repr(alpha))``): the level
    is the literal that the user wrote. A ``Fraction`` is used as it is.
    """
    if isinstance(alpha, Fraction):
        level = alpha
    else:
        if isinstance(alpha, bool) or not isinstance(alpha, float):
            raise ValueError(  # noqa: TRY004 - one named error for every bad level
                f"alpha must be a float or a Fraction in (0, 1), got {type(alpha).__name__}"
            )
        value = float(alpha)
        if not math.isfinite(value):
            raise ValueError(f"alpha must be finite, got {alpha!r}")
        level = Fraction(repr(value))
    if not 0 < level < 1:
        raise ValueError(f"alpha must lie in (0, 1), got {alpha!r}")
    return level


def _lower_rank(n: int, level: Fraction) -> int:
    """``j = floor((n + 1) * level)`` in integer arithmetic."""
    return ((n + 1) * level.numerator) // level.denominator


def upper_quantile(sorted_scores: Sequence[float], level: Fraction) -> float:
    """``q_{1-alpha}``: the ``k``-th smallest, ``k = ceil((n + 1)(1 - alpha))``; ``+inf`` if ``k > n``."""
    n = len(sorted_scores)
    k = n + 1 - _lower_rank(n, level)
    if k > n:
        return math.inf
    return sorted_scores[k - 1]


def lower_quantile(sorted_scores: Sequence[float], level: Fraction) -> float:
    """``q^lo_alpha``: the ``j``-th smallest, ``j = floor((n + 1) alpha)``; ``-inf`` if ``j < 1``."""
    j = _lower_rank(len(sorted_scores), level)
    if j < 1:
        return -math.inf
    return sorted_scores[j - 1]
