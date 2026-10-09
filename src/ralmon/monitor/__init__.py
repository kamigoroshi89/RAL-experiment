"""ralmon.monitor: public API (see 02-interfaces.md#package-public-api).

``__all__`` is the ``ralmon.monitor`` row of the contract table. The names below it (the named errors
``MonitorInputError``, ``PlanFeasibilityError`` and ``MonitorInvariantError``, the report types
``MonitorStats``, ``RejectedInput`` and ``ChannelAvailability``) are importable from this package root so
that other packages respect the rule of importing package roots only; they are outside ``__all__`` until
the proposed ADR of WS05-T04 puts them in the contract table.

``build_calibration_episodes`` and ``StaleCalibratorError`` stay placeholders owned by WS05-T08.
"""

from __future__ import annotations

from ralmon.monitor._stubs import (
    StaleCalibratorError,
    build_calibration_episodes,
)
from ralmon.monitor.config import (
    MonitorConfig,
    MonitorConfigError,
    PlanVersionError,
)
from ralmon.monitor.config import (
    MonitorInputError as MonitorInputError,
)
from ralmon.monitor.config import (
    MonitorInvariantError as MonitorInvariantError,
)
from ralmon.monitor.config import (
    PlanFeasibilityError as PlanFeasibilityError,
)
from ralmon.monitor.core import (
    ChannelAvailability as ChannelAvailability,
)
from ralmon.monitor.core import (
    Monitor,
    StreamingMonitor,
)
from ralmon.monitor.core import (
    MonitorStats as MonitorStats,
)
from ralmon.monitor.core import (
    RejectedInput as RejectedInput,
)
from ralmon.monitor.evaluator import PointEvaluator, make_point_evaluator
from ralmon.monitor.forecast import Forecast, Forecaster
from ralmon.monitor.offline import run_offline
from ralmon.monitor.verdict import (
    Rho,
    RhoKind,
    RobustnessInterval,
    VerdictRecord,
    VerdictState,
)

__all__ = [
    "Forecast",
    "Forecaster",
    "Monitor",
    "MonitorConfig",
    "MonitorConfigError",
    "PlanVersionError",
    "PointEvaluator",
    "Rho",
    "RhoKind",
    "RobustnessInterval",
    "StaleCalibratorError",
    "StreamingMonitor",
    "VerdictRecord",
    "VerdictState",
    "build_calibration_episodes",
    "make_point_evaluator",
    "run_offline",
]
