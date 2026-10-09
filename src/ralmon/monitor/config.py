"""``MonitorConfig`` (02-interfaces.md#monitor) and the named errors of ``ralmon.monitor``.

``MonitorConfig`` is the contract dataclass, verbatim: it validates nothing. The checks of CG-12
(docs/formal/01-signals-sampling.md section 9: ``T_s > 0``, ``T_s`` divides ``T_day``, ``D >= 0``) and
the agreement with the registry are made by ``check_config`` when a ``StreamingMonitor`` is built.

Errors. ``MonitorConfigError`` is a configuration, registry, template library or evaluator argument
that cannot be used; ``PlanFeasibilityError`` (a ``MonitorConfigError``) is a well-formed care plan
that cannot be monitored (a window parameter off the grid, a value outside its approved range, an
anchor already finalised); ``PlanVersionError`` is a ``plan_version`` that would decrease;
``MonitorInputError`` is an invalid argument of a call (a sample, an event, a time); and
``MonitorInvariantError`` is an internal invariant that failed (it never occurs on valid input and
exists so that nothing else escapes). A plan that cannot be read or verified raises
``ralmon.spec.PlanIntegrityError``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final, Literal

from ralmon.monitor._text import as_int, converting, show
from ralmon.signals import MS_PER_HOUR, DurationMs

__all__ = [
    "MAX_REORDER_DELAY_MS",
    "T_DAY_MS",
    "MonitorConfig",
    "MonitorConfigError",
    "MonitorInputError",
    "MonitorInvariantError",
    "PlanFeasibilityError",
    "PlanVersionError",
    "check_config",
]

# T_day of docs/formal/01-signals-sampling.md section 1.4: a definition, not a registry parameter
T_DAY_MS: Final[int] = 24 * MS_PER_HOUR
# algorithmic: the largest reorder delay (one day); a longer delay is a configuration mistake
MAX_REORDER_DELAY_MS: Final[int] = T_DAY_MS


class MonitorConfigError(Exception):
    """The configuration, the registry, the template library or an evaluator argument cannot be used."""


class PlanFeasibilityError(MonitorConfigError):
    """A well-formed care plan that the monitor cannot run (window off the grid, value out of range)."""


class PlanVersionError(Exception):
    """A care plan whose ``plan_version`` is lower than the one already loaded for its ``care_plan_id``."""


class MonitorInputError(Exception):
    """An invalid argument of a call: a sample, an event, a time, a call after ``close``."""


class MonitorInvariantError(Exception):
    """An internal invariant failed (a NaN in an interval, an interval with ``lo > hi``)."""


# ---------------------------------------------------------------------------------------
# Contract (02-interfaces.md#monitor, version 0.1.0): copied verbatim
# ---------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MonitorConfig:
    step_ms: DurationMs  # T_s
    reorder_delay_ms: DurationMs  # maximum reorder buffer delay
    predictive: bool  # emit PREDICTED_VIOLATION
    alpha: float | None
    variant: Literal["likely", "possible"]
    registry_version: str


@converting(MonitorConfigError)
def check_config(config: object) -> MonitorConfig:
    """Validate a ``MonitorConfig`` (CG-12) and return it; raise ``MonitorConfigError`` otherwise.

    ``predictive`` is refused: the predictive mode is added by WS05-T08 and this monitor produces
    measured verdicts only (ADR-008).
    """
    if not isinstance(config, MonitorConfig):
        raise MonitorConfigError(f"config must be a MonitorConfig, got {show(config)}")
    step = as_int(config.step_ms, "step_ms", MonitorConfigError, low=1, high=T_DAY_MS)
    if T_DAY_MS % step != 0:
        raise MonitorConfigError(
            f"step_ms {step} must divide the day of {T_DAY_MS} ms (modelling choice M2)"
        )
    as_int(
        config.reorder_delay_ms,
        "reorder_delay_ms",
        MonitorConfigError,
        low=0,
        high=MAX_REORDER_DELAY_MS,
    )
    if not isinstance(config.predictive, bool):
        raise MonitorConfigError(
            f"predictive must be a bool, got {show(config.predictive)}"
        )
    if not isinstance(config.variant, str) or config.variant not in (
        "likely",
        "possible",
    ):
        raise MonitorConfigError(
            f"variant must be 'likely' or 'possible', got {show(config.variant)}"
        )
    alpha = config.alpha
    if alpha is not None:
        if isinstance(alpha, bool) or not isinstance(alpha, (int, float)):
            raise MonitorConfigError(
                f"alpha must be a number or None, got {show(alpha)}"
            )
        if not math.isfinite(alpha) or not 0.0 < alpha < 1.0:
            raise MonitorConfigError(f"alpha must lie in (0, 1), got {show(alpha)}")
    if not isinstance(config.registry_version, str):
        raise MonitorConfigError(
            f"registry_version must be a str, got {show(config.registry_version)}"
        )
    if config.predictive:
        raise MonitorConfigError(
            "predictive monitoring (PREDICTED_VIOLATION) is added by WS05-T08; this monitor "
            "emits measured verdicts only (ADR-008): pass predictive=False"
        )
    return config
