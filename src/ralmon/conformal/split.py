"""Split conformal calibrator, ``PredictedViolation`` and the calibrator protocol (WS05-T06).

Contract: 02-interfaces.md#conformal-calibrator. The confidence ``rho`` of an emitted alert is
``1 - alpha_star``, a conformal p-value (docs/formal/06-rho-proposition1.md sections 4.5 and 4.6).
"""

from __future__ import annotations

import math
from bisect import bisect_left
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from ralmon.conformal.scores import (
    CalibrationEpisode,
    Level,
    exact_level,
    lower_quantile,
    scores_of,
    upper_quantile,
)
from ralmon.spec import Rho, RhoKind

__all__ = [
    "GUARANTEE_SPLIT",
    "ConformalCalibrator",
    "PredictedViolation",
    "SplitConformal",
]

Variant = Literal["likely", "possible"]

# The exact strings of docs/formal/06-rho-proposition1.md section 2.2 (golden case C-2).
GUARANTEE_SPLIT = "marginal over patient episodes under exchangeability"
ASSUMPTIONS_SPLIT: tuple[str, ...] = (
    "calibration unit is the patient episode; calibration and test episodes are exchangeable",
    (
        "forecaster and normalisation are fixed before calibration and independent of the "
        "calibration and test episodes"
    ),
    (
        "one designated prediction instant per episode, with the same rule for calibration and "
        "test episodes"
    ),
    "calibrator fitted on the current model version",
)


@dataclass(frozen=True, slots=True)
class PredictedViolation:
    emitted: bool
    rho: (
        Rho | None
    )  # RhoKind.PREDICTED with alpha_star = inf{alpha : sigma_hat + q_{1-alpha} < 0}
    variant: Literal["likely", "possible"]


class ConformalCalibrator(Protocol):
    @property
    def mode(self) -> Literal["split", "adaptive"]: ...

    calibrated_for: (
        str | None
    )  # model version of the last ``fit``; None: no particular model

    def fit(
        self,
        episodes: Sequence[CalibrationEpisode],
        alpha: Level,
        *,
        model_version: str | None = None,
    ) -> None: ...

    def quantile(self, alpha: Level) -> float: ...  # one-sided q_{1-alpha} of R

    def quantile_lower(
        self, alpha: Level
    ) -> float: ...  # q^lo_alpha, variant "possible"

    def predict(
        self, sigma_hat: float, alpha: Level, *, variant: Variant = "likely"
    ) -> PredictedViolation: ...

    def update(self, sigma_hat: float, sigma_true: float) -> None: ...  # adaptive only


def check_variant(variant: str) -> None:
    if variant not in ("likely", "possible"):
        raise ValueError(f"variant must be 'likely' or 'possible', got {variant!r}")


def decide(
    sorted_scores: Sequence[float],
    sigma_hat: float,
    quantile: float,
    alpha: Level,
    variant: Variant,
    *,
    guarantee: str,
    assumptions: tuple[str, ...],
) -> PredictedViolation:
    """Emission test and ``rho`` for one prediction, shared by the split and adaptive modes.

    ``quantile`` is the ``q`` of the variant that decides: the upper quantile for "likely", the
    lower quantile for "possible". ``rho = m / (n + 1)`` with ``m`` the number of scores with
    ``sigma_hat + R_i < 0``; this equals ``1 - alpha_star`` with
    ``alpha_star = (m' + 1) / (n + 1)`` and ``m' = n - m`` the number of scores with
    ``sigma_hat + R_i >= 0`` (docs/formal/06 section 4.6). ``rho`` is ``None`` when nothing is
    emitted: there is no alert whose confidence could be stated.
    """
    if not math.isfinite(sigma_hat):
        raise ValueError(f"sigma_hat must be finite, got {sigma_hat!r}")
    if not sigma_hat + quantile < 0:
        return PredictedViolation(emitted=False, rho=None, variant=variant)
    n = len(sorted_scores)
    below = bisect_left(sorted_scores, -sigma_hat)  # scores R_i < -sigma_hat
    rho = Rho(
        value=below / (n + 1),
        kind=RhoKind.PREDICTED,
        guarantee=guarantee,
        alpha=float(alpha),
        assumptions=assumptions,
    )
    return PredictedViolation(emitted=True, rho=rho, variant=variant)


class SplitConformal:
    """Split conformal calibrator with a one-sided score ``R = sigma_true - sigma_hat``.

    Reporting rules: calibration unit: patient episode. One ``CalibrationEpisode`` is one decision point of one
    template instance of one patient-day at its designated prediction instant; it is never a time
    step, and the calibration and test episodes come from different patients (split by patient).

    Coverage is marginal over the population under exchangeability across episodes, not
    conditional on the patient: Proposition 1 bounds ``P(alert emitted and sigma >= 0)`` by
    ``(n + 1 - k) / (n + 1) <= alpha`` over the joint draw of the calibration set and the test
    episode, given a fixed forecaster and normalisation. This calibrator pools all episodes it is
    given, so the coverage is marginal over the population and over the template mix; one
    calibrator per template and prediction-instant class gives a statement per template. With many
    tests per patient-day an alpha allocation is required (``BonferroniAllocation``): a level
    below ``1 / (n + 1)`` never emits, which is reported by ``quantile`` returning ``+inf``.

    The quantile of level ``alpha`` is the ``k``-th smallest score, ``k = ceil((n + 1)(1 - alpha))``,
    and ``+inf`` if ``k > n``. The rank is computed from the decimal literal of ``alpha`` (a float
    is read through its ``repr``; pass a ``Fraction`` for an allocated level such as
    ``alpha_total / n_tests``). The calibrator is level-agnostic: the ``alpha`` of ``fit`` is only
    validated, the level is given to ``quantile`` and ``predict``. ``fit`` stores no randomness, no
    clock and no reference to latent data; it reads only ``CalibrationEpisode`` values. A
    calibrator is tied to the model version given to ``fit`` (``calibrated_for``): every model
    update triggers a refit on held-out episodes (contract rule 4).
    """

    mode: Literal["split"] = "split"

    def __init__(self) -> None:
        self.calibrated_for: str | None = None
        self._sorted: list[float] = []

    @property
    def n_scores(self) -> int:
        """Number of calibration episodes, ``n`` of the finite-sample rank."""
        return len(self._sorted)

    def fit(
        self,
        episodes: Sequence[CalibrationEpisode],
        alpha: Level,
        *,
        model_version: str | None = None,
    ) -> None:
        exact_level(alpha)  # validated only: the split calibrator is level-agnostic
        self._sorted = sorted(scores_of(episodes))
        self.calibrated_for = model_version

    def _require_fitted(self) -> list[float]:
        if not self._sorted:
            raise RuntimeError("SplitConformal.fit has not been called")
        return self._sorted

    def quantile(self, alpha: Level) -> float:
        return upper_quantile(self._require_fitted(), exact_level(alpha))

    def quantile_lower(self, alpha: Level) -> float:
        return lower_quantile(self._require_fitted(), exact_level(alpha))

    def predict(
        self, sigma_hat: float, alpha: Level, *, variant: Variant = "likely"
    ) -> PredictedViolation:
        check_variant(variant)
        scores = self._require_fitted()
        level = exact_level(alpha)
        q = (
            upper_quantile(scores, level)
            if variant == "likely"
            else lower_quantile(scores, level)
        )
        return decide(
            scores,
            sigma_hat,
            q,
            alpha,
            variant,
            guarantee=GUARANTEE_SPLIT,
            assumptions=ASSUMPTIONS_SPLIT,
        )

    def update(self, sigma_hat: float, sigma_true: float) -> None:
        """No-op: the split calibrator does not adapt (adaptive mode only)."""
