"""Adaptive conformal calibrator for distribution shift, ablation A6 (WS05-T06)."""

from __future__ import annotations

import math
from bisect import bisect_left, insort
from collections import deque
from collections.abc import Sequence
from fractions import Fraction
from typing import Literal

from ralmon.conformal.scores import (
    CalibrationEpisode,
    Level,
    exact_level,
    lower_quantile,
    residual,
    scores_of,
    upper_quantile,
)
from ralmon.conformal.split import PredictedViolation, Variant, check_variant, decide

__all__ = ["GUARANTEE_ADAPTIVE", "AdaptiveConformal"]

GUARANTEE_ADAPTIVE = (
    "empirical coverage under distribution shift (ablation A6); no finite-sample guarantee is "
    "claimed for the adaptive level update"
)
ASSUMPTIONS_ADAPTIVE: tuple[str, ...] = (
    "calibration unit is the patient episode; the population scores come from calibration episodes",
    (
        "forecaster and normalisation are fixed before calibration and independent of the "
        "calibration and test episodes"
    ),
    (
        "one designated prediction instant per episode, with the same rule for calibration and "
        "test episodes"
    ),
    "calibrator fitted on the current model version",
    "the level is updated online from the observed outcomes of earlier episodes",
)


class AdaptiveConformal:
    """Adaptive conformal calibrator: the level follows the observed miscoverage (ablation A6).

    Reporting rules: calibration unit: patient episode. The population scores come from the calibration episodes
    given to ``fit``; ``update`` is called once per completed episode, after its outcome is known
    (``sigma_true``), and extends the score set and moves the working level ``alpha_t``.

    The recursion is that of adaptive conformal inference, ``alpha_{t+1} = alpha_t + gamma
    (alpha - err_t)`` with ``err_t = 1`` when the new score exceeds the quantile at ``alpha_t``
    (a miss) and ``0`` otherwise, ``alpha`` the target level of ``fit`` [ref-needed: WS03]: the
    citation details and the statement proved in that work are unverified until the human check of
    WS03-T06 (ADR-018), and no guarantee of it is reproduced here. The claim of this project for
    the adaptive mode is the empirical one of ablation A6, and ``Rho.guarantee`` says so.

    Coverage is marginal over the population under exchangeability across episodes, not
    conditional on the patient, wherever it is stated for the population scores; under shift it
    is measured, not guaranteed. With many tests per patient-day an alpha allocation is required
    (``BonferroniAllocation``), and the target level of ``fit`` is the allocated level.

    ``alpha_t`` is stored unclipped. For the working level ``alpha_t <= 0`` the quantile is
    ``+inf`` (no alert); for ``alpha_t >= 1`` it is ``-inf`` (every prediction is emitted). The
    lower quantile of the variant "possible" is the mirror: ``-inf`` for ``alpha_t <= 0`` and
    ``+inf`` for ``alpha_t >= 1``; the recursion tracks the upper quantile only, so the variant
    "possible" is not analysed for this mode. The calibrator is tied to the target level of
    ``fit``: ``quantile``, ``quantile_lower`` and ``predict`` refuse another level (refit
    instead). ``window`` keeps only the newest scores (``None`` keeps all). ``fork`` gives a
    per-patient copy that starts from the population scores and the target level, so that
    adaptation to one patient does not leak to others. A calibrator is tied to the model version
    given to ``fit`` (``calibrated_for``).
    """

    mode: Literal["adaptive"] = "adaptive"

    def __init__(self, gamma: float, window: int | None = None) -> None:
        if not (math.isfinite(gamma) and gamma > 0):
            raise ValueError(
                f"gamma must be a positive finite step size, got {gamma!r}"
            )
        if window is not None and window < 1:
            raise ValueError(f"window must be at least 1 or None, got {window!r}")
        self.gamma = gamma
        self.window = window
        self.calibrated_for: str | None = None
        self._target: Fraction | None = None
        self._target_float = math.nan
        self._alpha_t = math.nan
        self._moved = (
            False  # True once an update has moved alpha_t away from the target
        )
        self._population: tuple[float, ...] = ()
        self._arrival: deque[float] = deque()
        self._sorted: list[float] = []

    @property
    def alpha_t(self) -> float:
        """Working level, unclipped (it can leave ``(0, 1)``)."""
        self._require_fitted()
        return self._alpha_t

    @property
    def n_scores(self) -> int:
        """Number of retained scores (population plus updates, limited by ``window``)."""
        return len(self._sorted)

    def _require_fitted(self) -> Fraction:
        if self._target is None:
            raise RuntimeError("AdaptiveConformal.fit has not been called")
        return self._target

    def _load(self, scores: Sequence[float]) -> None:
        kept = list(scores) if self.window is None else list(scores)[-self.window :]
        self._arrival = deque(kept)
        self._sorted = sorted(kept)

    def fit(
        self,
        episodes: Sequence[CalibrationEpisode],
        alpha: Level,
        *,
        model_version: str | None = None,
    ) -> None:
        target = exact_level(alpha)
        self._load(scores_of(episodes))
        self._target = target
        self._target_float = float(alpha)
        self._alpha_t = self._target_float
        self._moved = False
        self._population = tuple(self._arrival)
        self.calibrated_for = model_version

    def fork(self) -> AdaptiveConformal:
        """A copy at the state right after ``fit``: population scores and target level."""
        target = self._require_fitted()
        other = AdaptiveConformal(gamma=self.gamma, window=self.window)
        other._load(self._population)
        other._target = target
        other._target_float = self._target_float
        other._alpha_t = self._target_float
        other._moved = False
        other._population = self._population
        other.calibrated_for = self.calibrated_for
        return other

    def _check_level(self, alpha: Level) -> None:
        if exact_level(alpha) != self._require_fitted():
            raise ValueError(
                "AdaptiveConformal tracks the level given to fit "
                f"({self._target_float}); got {alpha!r}, refit for another level"
            )

    def _working_level(self) -> Fraction | None:
        """Exact working level, or None when ``alpha_t`` is outside ``(0, 1)``.

        Until an update moves it, the working level is the fitted target itself, so a ``Fraction``
        level keeps its exact rank; the moving level comes from the float recursion.
        """
        if not self._moved:
            return self._target
        if 0 < self._alpha_t < 1:
            return Fraction(repr(self._alpha_t))
        return None

    def _upper(self) -> float:
        level = self._working_level()
        if level is None:
            return math.inf if self._alpha_t <= 0 else -math.inf
        return upper_quantile(self._sorted, level)

    def _lower(self) -> float:
        level = self._working_level()
        if level is None:
            return -math.inf if self._alpha_t <= 0 else math.inf
        return lower_quantile(self._sorted, level)

    def quantile(self, alpha: Level) -> float:
        self._check_level(alpha)
        return self._upper()

    def quantile_lower(self, alpha: Level) -> float:
        self._check_level(alpha)
        return self._lower()

    def predict(
        self, sigma_hat: float, alpha: Level, *, variant: Variant = "likely"
    ) -> PredictedViolation:
        check_variant(variant)
        self._check_level(alpha)
        q = self._upper() if variant == "likely" else self._lower()
        return decide(
            self._sorted,
            sigma_hat,
            q,
            alpha,
            variant,
            guarantee=GUARANTEE_ADAPTIVE,
            assumptions=ASSUMPTIONS_ADAPTIVE,
        )

    def update(self, sigma_hat: float, sigma_true: float) -> None:
        """Observe one completed episode: move ``alpha_t``, then add its score."""
        self._require_fitted()
        r = residual(sigma_hat, sigma_true)
        err = 1.0 if r > self._upper() else 0.0
        self._alpha_t = self._alpha_t + self.gamma * (self._target_float - err)
        self._moved = True
        self._arrival.append(r)
        insort(self._sorted, r)
        if self.window is not None and len(self._arrival) > self.window:
            oldest = self._arrival.popleft()
            del self._sorted[bisect_left(self._sorted, oldest)]
