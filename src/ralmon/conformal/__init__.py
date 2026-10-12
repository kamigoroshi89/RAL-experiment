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
from ralmon.conformal.scores import Level as Level

# The conformal sets of the attribution (WS05-T14, ADR-074) are importable from the package root and stay outside ``__all__`` (the
# table of ``#package-public-api`` is frozen); ``ralmon.eval`` reads them and ``tests/test_layering.py`` requires the root (WS08-T09).
from ralmon.conformal.sets import (
    ASSUMPTIONS_SETS as ASSUMPTIONS_SETS,
)
from ralmon.conformal.sets import (
    GUARANTEE_SETS as GUARANTEE_SETS,
)
from ralmon.conformal.sets import (
    GUARANTEE_SETS_MONDRIAN as GUARANTEE_SETS_MONDRIAN,
)
from ralmon.conformal.sets import (
    AttributionSet as AttributionSet,
)
from ralmon.conformal.sets import (
    PatientLeakError as PatientLeakError,
)
from ralmon.conformal.sets import (
    SetThreshold as SetThreshold,
)
from ralmon.conformal.sets import (
    StaleSetCalibratorError as StaleSetCalibratorError,
)
from ralmon.conformal.sets import (
    SubtypeCalibrationAlert as SubtypeCalibrationAlert,
)
from ralmon.conformal.sets import (
    SubtypeSetCalibrator as SubtypeSetCalibrator,
)
from ralmon.conformal.sets import (
    cumulative_level_set as cumulative_level_set,
)
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
