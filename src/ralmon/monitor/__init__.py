"""ralmon.monitor: public API (see 02-interfaces.md#package-public-api).

``__all__`` is the ``ralmon.monitor`` row of the contract table. The names below it are importable from
this package root so that other packages respect the rule of importing package roots only, and they stay
outside ``__all__`` (as WS05-T03 did for the extras of ``ralmon.spec``) until ADR-053 puts them in the
contract table: the named errors ``MonitorInputError``, ``PlanFeasibilityError`` and
``MonitorInvariantError``; the report types ``MonitorStats``, ``RejectedInput`` and
``ChannelAvailability``; ``run_offline_detailed`` and its ``OfflineResult`` (the records of
``run_offline`` plus the late and rejected inputs and the counters of the run); and
``resolve_subformula_path`` and ``resolve_subformula_paths``, which the attribution layer uses to turn the
``subformula_path`` of a record (several parts joined by ``;``) into the text of the sub-formulas.

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
from ralmon.monitor.formula import (
    resolve_subformula_path as resolve_subformula_path,
)
from ralmon.monitor.formula import (
    resolve_subformula_paths as resolve_subformula_paths,
)
from ralmon.monitor.offline import (
    OfflineResult as OfflineResult,
)
from ralmon.monitor.offline import (
    run_offline,
)
from ralmon.monitor.offline import (
    run_offline_detailed as run_offline_detailed,
)
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
