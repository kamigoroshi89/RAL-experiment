"""``EvidenceVector`` and its six parts (02-interfaces.md#evidencevector, version 0.1.0), verbatim.

``None`` in a field always means "channel unavailable or not applicable", never "negative" (the rule of the
contract and of docs/models/evidence-channels.md, section Reading states). A field is addressed by its canonical
path ``group.field`` (evidence-channels.md, section Conventions); ``EVIDENCE_PATHS`` lists the twenty paths in
contract order, and ``get_evidence`` reads one.

Helpers outside the contract: ``empty_evidence`` (the vector of an absent evidence key: provenance from the
record, every other field ``None``, decision D-1), ``template_kind_of`` and ``instance_anchor_ms``.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from ralmon.signals import TimeMs
from ralmon.spec import TemplateId, TemplateKind

__all__ = [
    "EVIDENCE_PATHS",
    "NON_PROVENANCE_PATHS",
    "CrossDeviceEvidence",
    "CryptoTemporalEvidence",
    "EmbodiedWitnessEvidence",
    "EvidenceVector",
    "ProvenanceEvidence",
    "SignalQualityEvidence",
    "SystemHealthEvidence",
    "empty_evidence",
    "get_evidence",
    "instance_anchor_ms",
    "template_kind_of",
]


@dataclass(frozen=True, slots=True)
class ProvenanceEvidence:
    violated_template: TemplateId
    template_kind: TemplateKind  # which of phi_cp, phi_sys, phi_int is violated


@dataclass(frozen=True, slots=True)
class SystemHealthEvidence:
    node_lifecycle: Mapping[str, str] | None  # ROS 2 lifecycle state per node
    diagnostics_ok: bool | None
    liveliness_ok: bool | None
    qos_deadline_missed: bool | None
    ble_link_quality: float | None
    battery_low: bool | None
    nav_task_failed: bool | None
    manip_task_failed: bool | None


@dataclass(frozen=True, slots=True)
class SignalQualityEvidence:
    ecg_sqi: float | None
    ppg_sqi: float | None
    cuff_error_code: str | None


@dataclass(frozen=True, slots=True)
class CrossDeviceEvidence:
    pulse_vs_ecg_hr_diff: (
        float | None
    )  # cuff pulse rate versus ECG heart rate at the same instant


@dataclass(frozen=True, slots=True)
class EmbodiedWitnessEvidence:
    robot_present: bool | None  # None if the robot was not co-located
    identity_confirmed: bool | None
    intake_observed: bool | None


@dataclass(frozen=True, slots=True)
class CryptoTemporalEvidence:
    authenticated: bool | None
    seq_gap_or_replay: bool | None
    timestamp_implausible: bool | None


@dataclass(frozen=True, slots=True)
class EvidenceVector:
    provenance: ProvenanceEvidence
    system: SystemHealthEvidence
    signal_quality: SignalQualityEvidence
    cross_device: CrossDeviceEvidence
    witness: EmbodiedWitnessEvidence
    crypto_temporal: CryptoTemporalEvidence


def _paths() -> tuple[str, ...]:
    out: list[str] = []
    for group in dataclasses.fields(EvidenceVector):
        part = {
            "provenance": ProvenanceEvidence,
            "system": SystemHealthEvidence,
            "signal_quality": SignalQualityEvidence,
            "cross_device": CrossDeviceEvidence,
            "witness": EmbodiedWitnessEvidence,
            "crypto_temporal": CryptoTemporalEvidence,
        }[group.name]
        out.extend(f"{group.name}.{leaf.name}" for leaf in dataclasses.fields(part))
    return tuple(out)


#: The twenty canonical paths ``group.field`` in contract order (evidence-channels.md, section Conventions).
EVIDENCE_PATHS: Final[tuple[str, ...]] = _paths()
#: The eighteen fields other than the two ``provenance`` fields.
NON_PROVENANCE_PATHS: Final[tuple[str, ...]] = tuple(
    p for p in EVIDENCE_PATHS if not p.startswith("provenance.")
)


def get_evidence(evidence: EvidenceVector, path: str) -> object:
    """The value of the field ``path`` (``group.field``) of a vector; ``KeyError`` for an unknown path."""
    if path not in EVIDENCE_PATHS:
        raise KeyError(path)
    group, leaf = path.split(".", 1)
    return getattr(getattr(evidence, group), leaf)


_KIND: Final[Mapping[TemplateId, TemplateKind]] = {
    TemplateId.RANGE: TemplateKind.CARE_PLAN,
    TemplateId.SCHED: TemplateKind.CARE_PLAN,
    TemplateId.HOLD: TemplateKind.CARE_PLAN,
    TemplateId.COUNT: TemplateKind.CARE_PLAN,
    TemplateId.RESP: TemplateKind.CARE_PLAN,
    TemplateId.SYS: TemplateKind.SYSTEM,
    TemplateId.INT: TemplateKind.INTEGRITY,
}


def template_kind_of(template: TemplateId) -> TemplateKind:
    """The conjunct of a template (docs/formal/02-templates.md section 3.1): SYSTEM for ``sys``, INTEGRITY for ``int``."""
    return _KIND[template]


def empty_evidence(template: TemplateId) -> EvidenceVector:
    """The vector of an absent evidence key: provenance from the record, every other field ``None`` (D-1)."""
    return EvidenceVector(
        provenance=ProvenanceEvidence(template, template_kind_of(template)),
        system=SystemHealthEvidence(None, None, None, None, None, None, None, None),
        signal_quality=SignalQualityEvidence(None, None, None),
        cross_device=CrossDeviceEvidence(None),
        witness=EmbodiedWitnessEvidence(None, None, None),
        crypto_temporal=CryptoTemporalEvidence(None, None, None),
    )


def instance_anchor_ms(
    instance_key: str,
    template: TemplateId,
    *,
    decided_at_ms: TimeMs | None,
    t_eval_ms: TimeMs,
    pending_until_ms: TimeMs | None,
    window_ms: int | None,
    plan_anchor_ms: TimeMs | None = None,
) -> TimeMs:
    """The anchor of an instance: the schedule tick or the event that created it.

    In order: the anchor of the plan instance (``plan_anchor_ms``); the number after ``@`` in a dynamic key
    ``<template id>@<t_device_ms of the anchoring event>`` (an optional ``#n`` suffix is ignored); the
    decision deadline minus the window for ``sched`` (``sched_window``) and ``resp`` (``delta2``); the decision
    time of an instance decided at its anchor step (``range``, ``sys``, ``hold``, ``int``, the limit of
    ``count``), else the evaluation time. A plan key is free text, so this chain is a convention of the
    attribution layer (docs/models/evidence-channels.md, D-1).
    """
    if plan_anchor_ms is not None:
        return plan_anchor_ms
    _, sep, tail = instance_key.partition("@")
    if sep:
        digits = tail.split("#", 1)[0]
        if digits.isdigit():
            return int(digits)
    if (
        template in (TemplateId.SCHED, TemplateId.RESP)
        and pending_until_ms is not None
        and window_ms is not None
    ):
        return pending_until_ms - window_ms
    if decided_at_ms is not None:
        return decided_at_ms
    return t_eval_ms
