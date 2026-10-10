"""ralmon.conformal: public API (see 02-interfaces.md#package-public-api).

Calibration unit: patient episode. Coverage is marginal over the population under exchangeability
across episodes, not conditional on the patient; with many tests per patient-day an alpha
allocation is required (analisi §4.4, three caveats).

``conformal`` imports only ``signals`` and ``spec``.
"""

from __future__ import annotations

from ralmon.conformal.adaptive import AdaptiveConformal
from ralmon.conformal.allocation import AlphaAllocation, BonferroniAllocation
from ralmon.conformal.scores import CalibrationEpisode
from ralmon.conformal.split import (
    ConformalCalibrator,
    PredictedViolation,
    SplitConformal,
)

__all__ = [
    "AdaptiveConformal",
    "AlphaAllocation",
    "BonferroniAllocation",
    "CalibrationEpisode",
    "ConformalCalibrator",
    "PredictedViolation",
    "SplitConformal",
]
