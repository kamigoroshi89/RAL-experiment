"""``rho`` of a VIOLATED record (docs/formal/06-rho-proposition1.md sections 2.2, 2.3 and 3.2).

A violation decided by a margin on a measured pressure is MEASURED: ``rho = P(sigma_true < 0 |
measurement)`` under the declared device error model (Gaussian error of standard deviation
``cuff_error_sd`` read from the registry, errors of distinct measurements independent, flat prior on
the true value). A violation decided by a predicate over the event log or the timestamps is
DETERMINISTIC (``rho = 1``). The strings are the literal contents of section 2.2. The PREDICTED kind is
WS05-T08. Nothing here is a clinical statement: the value is conditional on the adequacy of the model.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Final

from ralmon.monitor._text import converting
from ralmon.monitor.config import MonitorInputError
from ralmon.spec import Rho, RhoKind

__all__ = [
    "bounds_rho",
    "deterministic_rho",
    "difference_rho",
    "lower_limit_rho",
    "range_band_rho",
]

MEASURED_GUARANTEE: Final = (
    "conditional on the adequacy of the declared device error model"
)
MEASURED_ASSUMPTIONS: Final[tuple[str, ...]] = (
    "measured value equals the true value plus an independent Gaussian error with standard deviation cuff_error_sd",
    "zero bias after correction (a silent bias is not seen by rho)",
    "flat prior on the true value",
    "errors of distinct measurements are independent",
)
DETERMINISTIC_GUARANTEE: Final = "conditional on the integrity of the event log"
DETERMINISTIC_ASSUMPTIONS: Final[tuple[str, ...]] = (
    "the predicate is evaluated on the accepted event log or timestamps without error",
    "authenticity of the events is attributed by kappa and is not covered by rho",
)

# algorithmic: intervals of the Simpson rule for the several-measurement integral of section 3.2 item 4
# (even), and the half-width of the interval of integration in standard deviations of the pre-dose error
_QUADRATURE_INTERVALS: Final = 4096
_QUADRATURE_HALF_WIDTH: Final = 9.0


def _phi(x: float) -> float:
    """The standard normal cdf, by ``erfc`` so that the lower tail keeps its relative precision."""
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def _measured(value: float) -> Rho:
    return Rho(
        value=min(max(value, 0.0), 1.0),
        kind=RhoKind.MEASURED,
        guarantee=MEASURED_GUARANTEE,
        alpha=None,
        assumptions=MEASURED_ASSUMPTIONS,
    )


def deterministic_rho() -> Rho:
    """``rho = 1`` for a predicate over the event log or the timestamps."""
    return Rho(
        value=1.0,
        kind=RhoKind.DETERMINISTIC,
        guarantee=DETERMINISTIC_GUARANTEE,
        alpha=None,
        assumptions=DETERMINISTIC_ASSUMPTIONS,
    )


@converting(MonitorInputError)
def range_band_rho(x: float, low: float, high: float, sd: float) -> Rho:
    """Band ``[low, high]`` violated by the measured value ``x``: the two disjoint regions add (item 2)."""
    return _measured(_phi((low - x) / sd) + _phi((x - high) / sd))


@converting(MonitorInputError)
def lower_limit_rho(x: float, limit: float, sd: float) -> Rho:
    """A lower limit (the hold threshold) violated by the measured value ``x`` (item 1)."""
    return _measured(_phi((limit - x) / sd))


@converting(MonitorInputError)
def bounds_rho(pre: float, bound_lower: float, delta: float, sd: float) -> Rho:
    """RESP decided at its anchor step because ``pre < bound_lower + delta`` (item 5)."""
    return _measured(_phi((bound_lower + delta - pre) / sd))


@converting(MonitorInputError)
def difference_rho(
    pre: float, responses: Sequence[float], delta: float, sd: float
) -> Rho:
    """RESP violated on a closed window: every measured drop is below ``delta`` (items 3 and 4).

    One response: ``Phi((delta - (pre - x)) / (sd * sqrt 2))``. Several share the pre-dose error, so
    the drops are positively correlated and the value is the integral over the pre-dose error ``z`` of
    ``phi(z) * prod_j Phi((x_j + delta - pre) / sd - z)``, computed by Simpson's rule.
    """
    if len(responses) == 1:
        return _measured(_phi((delta - (pre - responses[0])) / (sd * math.sqrt(2.0))))
    n = _QUADRATURE_INTERVALS
    half = _QUADRATURE_HALF_WIDTH
    h = 2.0 * half / n
    offsets = [(x + delta - pre) / sd for x in responses]
    total = 0.0
    for i in range(n + 1):
        z = -half + i * h
        term = math.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi)
        for c in offsets:
            term *= _phi(c - z)
        weight = 1.0 if i in (0, n) else (4.0 if i % 2 == 1 else 2.0)
        total += weight * term
    return _measured(total * h / 3.0)
