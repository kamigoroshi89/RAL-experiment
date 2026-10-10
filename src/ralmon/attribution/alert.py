"""The alert tuple (02-interfaces.md#alert, version 0.1.0): ``AttributedCause``, ``Explanation``, ``Detection``, ``Alert``.

The dataclasses are the contract, verbatim, with one widening that is ahead of the contract (see below). The
derivation of the fields from a ``VerdictRecord`` is in ``alert_from_record`` and follows
docs/formal/07-alert-tuple-mapping.md section 1 (ADR-041, proposed) and decision D7 of the WS05 README:

* ``t_ms`` is ``decided_at_ms`` of the first VIOLATED record, ``t_eval_ms`` for a PREDICTED_VIOLATION record;
* ``label`` equals ``kappa``; ``score`` is minus ``sigma_norm`` (higher is more severe);
* ``sigma_norm`` is the upper end of ``sigma_norm_interval`` for a definitive record (the smallest violation that is
  certain) and ``predicted_sigma_norm`` for a predicted one;
* ``priority`` is the registry entry named by ``Template.priority_param`` (1 is the highest);
* ``xi`` carries the instance, the sub-formula path, the parameter values the instance used, the decisive
  evidence fields and the text of ``render.render_text``.

AHEAD OF THE CONTRACT: ``Alert.rho`` is annotated ``Rho | None``. A VIOLATED record has ``rho`` ``None`` when the
monitor has no error model for a MEASURED confidence ("no probability available", ``stats().rho_unavailable``,
handover (3) of WS05-T04) and a violated verdict is always reported, so the alert is built and carries ``None``
instead of an invented number. The contract text says ``Rho``; the widening is recorded in the Notes of WS05-T07.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from enum import Enum
from types import MappingProxyType
from typing import TYPE_CHECKING

from ralmon.monitor import VerdictRecord, VerdictState
from ralmon.signals import TimeMs
from ralmon.spec import (
    ParameterRegistry,
    Rho,
    Template,
    TemplateId,
    as_priority,
)

if TYPE_CHECKING:
    from ralmon.attribution.rule import Decision

__all__ = [
    "Alert",
    "AttributedCause",
    "Detection",
    "Explanation",
    "alert_from_record",
]


class AttributedCause(str, Enum):
    C1_CLINICAL = "C1"  # clinical or adherence deviation
    C2_SYSTEM = "C2"  # system or embodiment failure
    C3_INTEGRITY = "C3"  # integrity or plausibility violation
    UNDETERMINED = "UNDETERMINED"


@dataclass(frozen=True, slots=True)
class Explanation:
    """xi: specification-level traceability (not 'intrinsic explainability')."""

    template: TemplateId
    instance_key: str
    subformula_path: str  # path to the violated sub-formula
    param_values: Mapping[str, float]  # clinical parameters used
    evidence_used: Sequence[str]  # EvidenceVector fields that decided kappa
    text: str  # natural-language rendering for nursing staff


@dataclass(frozen=True, slots=True)
class Detection:
    """Minimal output shared by every detector, including baselines B1-B4."""

    t_ms: TimeMs
    label: AttributedCause | None  # None for detectors that do not attribute
    score: (
        float  # detector-specific; higher = more anomalous, only for ROC-style curves
    )


@dataclass(frozen=True, slots=True)
class Alert(Detection):
    tau: TemplateId  # violated template (constraint)
    kappa: AttributedCause  # attributed cause; UNDETERMINED is a valid output
    sigma_norm: float  # normalised robustness in [-1, 0) for a violation
    rho: (
        Rho | None
    )  # confidence with declared kind and guarantee (None: no probability available)
    xi: Explanation
    verdict: VerdictState  # VIOLATED or PREDICTED_VIOLATION
    priority: int  # clinician-assigned template priority
    root_cause_of: Sequence[
        str
    ]  # instance keys of downstream violations explained by this alert (cascades)
    caused_by: (
        str | None
    )  # instance key of the upstream alert when this one is a cascade effect


def alert_time_and_severity(record: VerdictRecord) -> tuple[TimeMs, float]:
    """``(t_ms, sigma_norm)`` of the alert that a violation-claiming record produces.

    Raises ``ValueError`` for a record that claims no violation, and for a PREDICTED_VIOLATION record
    that carries no ``predicted_sigma_norm`` (the carrier of ADR-048 (a); the predictive layer fills it).
    """
    if record.state is VerdictState.VIOLATED:
        decided = (
            record.decided_at_ms
            if record.decided_at_ms is not None
            else record.t_eval_ms
        )
        return decided, float(record.sigma_norm_interval[1])
    if record.state is VerdictState.PREDICTED_VIOLATION:
        bound = getattr(record, "predicted_sigma_norm", None)
        if bound is None:
            raise ValueError(
                f"{record.instance_key}: a PREDICTED_VIOLATION record needs predicted_sigma_norm"
            )
        return record.t_eval_ms, float(bound)
    raise ValueError(
        f"{record.instance_key}: a {record.state.value} record makes no alert"
    )


def instance_param_values(
    template: Template,
    registry: ParameterRegistry,
    overrides: Mapping[str, float] | None = None,
) -> Mapping[str, float]:
    """The values of ``Template.params`` that an instance used: the plan value, else the registry value."""
    values: dict[str, float] = {}
    for name in template.params:
        if overrides is not None and name in overrides:
            values[name] = float(overrides[name])
        else:
            values[name] = float(registry.get(name).value)
    return MappingProxyType(values)


def alert_from_record(
    record: VerdictRecord,
    decision: Decision,
    template: Template,
    registry: ParameterRegistry,
    *,
    param_values: Mapping[str, float] | None = None,
    anchor_ms: TimeMs | None = None,
    variant: str | None = None,
    caused_by: str | None = None,
    root_cause_of: Sequence[str] = (),
) -> Alert:
    """The one function that derives the fields of an ``Alert`` from the record, the decision and the template.

    ``decision`` carries the attributed cause and the decisive fields (those of the rule, or those of the root
    for a cascade effect, or the undetermined decision of a predicted record). ``anchor_ms`` and ``variant``
    (``"likely"`` or ``"possible"`` for a predicted alert) only enter the text.
    """
    from ralmon.attribution.render import render_text

    t_ms, sigma_norm = alert_time_and_severity(record)
    kappa = decision.kappa
    xi = Explanation(
        template=record.template,
        instance_key=record.instance_key,
        subformula_path=record.subformula_path or "",
        param_values=instance_param_values(template, registry, param_values),
        evidence_used=tuple(decision.evidence_used),
        text="",
    )
    alert = Alert(
        t_ms=t_ms,
        label=kappa,
        score=0.0 - sigma_norm,  # minus zero becomes plus zero
        tau=record.template,
        kappa=kappa,
        sigma_norm=sigma_norm,
        rho=record.rho,
        xi=xi,
        verdict=record.state,
        priority=as_priority(registry.get(template.priority_param)),
        root_cause_of=tuple(root_cause_of),
        caused_by=caused_by,
    )
    text = render_text(
        alert,
        record,
        decision,
        template,
        registry,
        anchor_ms=anchor_ms,
        variant=variant,
    )
    return replace(alert, xi=replace(xi, text=text))
