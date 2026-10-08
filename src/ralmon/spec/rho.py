"""``Rho`` and ``RhoKind`` of 02-interfaces.md#verdict: the single definition.

They live in ``ralmon.spec`` so that ``ralmon.conformal`` (which builds a ``Rho``) and
``ralmon.monitor`` (which uses ``conformal``) do not import each other; ``ralmon.monitor``
re-exports them (ADR-024).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

__all__ = ["Rho", "RhoKind"]


class RhoKind(str, Enum):
    MEASURED = "measured"  # P(sigma_true < 0 | measurement) under a device error model
    PREDICTED = "predicted"  # conformal, 1 - alpha_star
    DETERMINISTIC = "deterministic"  # event-log predicate, rho = 1


@dataclass(frozen=True, slots=True)
class Rho:
    value: float  # in [0, 1]
    kind: RhoKind
    guarantee: str  # exact statement, e.g. "marginal over patient episodes under exchangeability"
    alpha: float | None  # nominal level for PREDICTED
    assumptions: Sequence[str]
