"""``VerdictState``, ``RobustnessInterval`` and ``VerdictRecord`` (02-interfaces.md#verdict).

The first nine fields of ``VerdictRecord`` are the contract (version 0.1.0), verbatim and in the same
order. The four optional fields after them are AHEAD OF THE CONTRACT until ADR-048 is accepted (that
ADR moves the edit of ``02-interfaces.md#verdict`` to its acceptance; ADR-029 adopted the semantics
they carry): code that builds a record with the nine contract fields keeps working because the extras
are trailing and default to ``None``.

* ``undecidable``: the marker ``undecidable: <reason>:<signal>`` of an instance that stays PENDING after
  its decision step because a position is stale-open (docs/formal/05 section 3.5, CP6); several entries
  are joined by commas.
* ``guard_failed``: the guard of the margin and guard rule that made the decision-step value minus
  infinity (docs/formal/02 section 2.1): ``no_measurement_after_tick``, ``no_recent_measurement``,
  ``obligation_unmet``, ``cuff_unhealthy`` or ``no_witness``; set on a VIOLATED record and kept by its
  refinements.
* ``subformula_path``: the path of the sub-formula that attained the deciding bound, as child indices
  from the root of ``Template.formula_past_time`` preceded by the template id (``sched/0/1/0/0``), with
  the labels ``limit`` and ``day_end`` for the two conjuncts of COUNT and the guard marker as the last
  element of a path that ends in a failed guard; other violated sub-formulas follow, separated by ``;``
  (ADR-048 (a)). ``ralmon.monitor.evaluator.resolve_subformula_path`` resolves a path.
* ``predicted_sigma_norm``: the bound of a PREDICTED_VIOLATION record; ``None`` in every record of this
  monitor (filled by WS05-T08).

A definitive record's ``state``, ``rho``, ``decided_at_ms``, ``guard_failed`` and ``subformula_path``
never change; its interval fields may refine (the graded lateness of SCHED, ADR-048 (b)).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ralmon.signals import TimeMs
from ralmon.spec import Rho, RhoKind, TemplateId

__all__ = [
    "Rho",
    "RhoKind",
    "RobustnessInterval",
    "VerdictRecord",
    "VerdictState",
]


class VerdictState(str, Enum):
    PENDING = "pending"
    PREDICTED_VIOLATION = "predicted_violation"  # early warning, never definitive
    VIOLATED = "violated"  # definitive, from measured prefix only
    SATISFIED = "satisfied"  # definitive, from measured prefix only


@dataclass(frozen=True, slots=True)
class RobustnessInterval:
    lo: float  # raw robustness lower bound (native unit)
    hi: float  # raw robustness upper bound; unknown future values replaced by physiological bounds


@dataclass(frozen=True, slots=True)
class VerdictRecord:
    """One record ``rec(i, k)`` of an instance at a finalised step (docs/formal/05 section 3.1).

    The first nine fields are the contract of ``#verdict``; the four trailing fields are ahead of the
    contract until ADR-048 is accepted (see the module docstring).
    """

    instance_key: str
    template: TemplateId
    t_eval_ms: TimeMs
    state: VerdictState
    sigma_interval: RobustnessInterval  # raw, native unit
    sigma_norm_interval: tuple[float, float]  # clipped normalised interval
    rho: Rho | None
    decided_at_ms: (
        TimeMs | None
    )  # when the definitive verdict became decidable; None while PENDING
    pending_until_ms: (
        TimeMs | None
    )  # deadline after which the verdict is definitive (anchor + Delta2 or W)
    # --- ahead of the contract until ADR-048 is accepted (trailing, defaulted) ---
    undecidable: str | None = None
    guard_failed: str | None = None
    subformula_path: str | None = None
    predicted_sigma_norm: float | None = None
