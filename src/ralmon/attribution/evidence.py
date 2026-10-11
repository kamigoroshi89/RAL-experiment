"""``EvidenceVector`` and its seven parts (02-interfaces.md#evidencevector, version 0.2.0), verbatim.

``None`` in a field always means "channel unavailable or not applicable", never "negative" (the rule of the
contract and of docs/models/evidence-channels.md, section Reading states). A field is addressed by its canonical
path ``group.field`` (evidence-channels.md, section Conventions); ``EVIDENCE_PATHS`` lists the twenty-four paths in
contract order, and ``get_evidence`` reads one.

Helpers outside the contract: ``empty_evidence`` (the vector of an absent evidence key: provenance from the
record, every other field ``None``, decision D-1), ``template_kind_of`` and ``instance_anchor_ms``.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from ralmon.signals import TimeMs
from ralmon.spec import ParameterRegistry, RegistryError, TemplateId, TemplateKind

__all__ = [
    "EVIDENCE_PATHS",
    "NON_PROVENANCE_PATHS",
    "CrossDeviceEvidence",
    "CryptoTemporalEvidence",
    "DispenserEvidence",
    "EmbodiedWitnessEvidence",
    "EvidenceVector",
    "ProvenanceEvidence",
    "SignalQualityEvidence",
    "SystemHealthEvidence",
    "empty_evidence",
    "get_evidence",
    "instance_anchor_ms",
    "known_anchor_ms",
    "parse_anchor_from_key",
    "require_registry_names",
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
    seq_gap: (
        bool | None
    )  # a sequence value is missing at the cut-off (BLE sources only; system evidence)


@dataclass(frozen=True, slots=True)
class SignalQualityEvidence:
    ecg_sqi: float | None
    ppg_sqi: float | None
    cuff_error_code: str | None
    cuff_value_repeated: (
        bool | None
    )  # the reading equals the previous reading of the same cuff stream


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
    seq_repeat: (
        bool | None
    )  # a received (name, seq) repeats an accepted one (integrity evidence)
    timestamp_implausible: bool | None


@dataclass(frozen=True, slots=True)
class DispenserEvidence:
    interval_since_previous_ms: int | None = None  # never negative
    content_change: float | None = (
        None  # before minus after: a release is positive, a bounce is zero (ADR-040 (2))
    )


@dataclass(frozen=True, slots=True)
class EvidenceVector:
    provenance: ProvenanceEvidence
    system: SystemHealthEvidence
    signal_quality: SignalQualityEvidence
    cross_device: CrossDeviceEvidence
    witness: EmbodiedWitnessEvidence
    crypto_temporal: CryptoTemporalEvidence
    dispenser: DispenserEvidence = DispenserEvidence()


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
            "dispenser": DispenserEvidence,
        }[group.name]
        out.extend(f"{group.name}.{leaf.name}" for leaf in dataclasses.fields(part))
    return tuple(out)


#: The twenty-four canonical paths ``group.field`` in contract order (evidence-channels.md, section Conventions).
EVIDENCE_PATHS: Final[tuple[str, ...]] = _paths()
#: The twenty-two fields other than the two ``provenance`` fields.
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
        system=SystemHealthEvidence(
            None, None, None, None, None, None, None, None, None
        ),
        signal_quality=SignalQualityEvidence(None, None, None, None),
        cross_device=CrossDeviceEvidence(None),
        witness=EmbodiedWitnessEvidence(None, None, None),
        crypto_temporal=CryptoTemporalEvidence(None, None, None),
        dispenser=DispenserEvidence(None, None),
    )


def require_registry_names(
    registry: ParameterRegistry, names: Sequence[str], who: str
) -> None:
    """Raise one ``RegistryError`` that lists every name of ``names`` without a value in the registry.

    These parameters are requested by docs/models/evidence-channels.md and docs/models/attribution-rule.md and have no
    registry row (open point OPF-6 of docs/formal/08-consistency-review.md); no default is invented.
    """
    missing: list[str] = []
    for name in names:
        try:
            registry.get(name)
        except RegistryError:
            missing.append(name)
    if missing:
        where = getattr(registry, "path", None)
        file = (
            f" (registry file {where}, version {registry.version()})" if where else ""
        )
        raise RegistryError(
            f"{who}: the registry{file} has no value for {', '.join(missing)}; these names are requested "
            "by docs/models/evidence-channels.md and docs/models/attribution-rule.md and have no registry row "
            "(open point OPF-6 of docs/formal/08-consistency-review.md); add them to the registry file "
            "(configs/registry/hypertension.yaml) or use a registry that carries them, no default is assumed"
        )


def parse_anchor_from_key(key: str, template: TemplateId) -> TimeMs | None:
    """The anchor in a dynamic instance key ``<template id>@<t_device_ms>`` (``#n`` suffix ignored), else ``None``.

    The convention is the monitor's for the instances created by an anchoring event (a measurement, a dispense).
    A ``sched`` instance is anchored by a schedule tick of the plan and its key is free text, and a key whose prefix
    is not the template id is not of the convention: neither names an anchor.
    """
    if template is TemplateId.SCHED:
        return None
    prefix, sep, tail = key.partition("@")
    digits = tail.split("#", 1)[0]
    if sep and prefix == template.value and digits.isdigit():
        return int(digits)
    return None


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
    """The anchor of an instance, always a number (the evidence window needs one).

    In order: the anchor of the plan instance (``plan_anchor_ms``); the anchor of a dynamic key
    (``parse_anchor_from_key``); for ``sched`` and ``resp`` the decision deadline (``pending_until_ms``, else the
    decision time) minus the window (``sched_window``, ``delta2``); else the decision time of an instance decided at
    its anchor step, else the evaluation time. Where the anchor is only an estimate the text does not print it
    (``known_anchor_ms``).
    """
    known = known_anchor_ms(
        instance_key,
        template,
        pending_until_ms=pending_until_ms,
        window_ms=window_ms,
        plan_anchor_ms=plan_anchor_ms,
    )
    if known is not None:
        return known
    if template in (TemplateId.SCHED, TemplateId.RESP) and window_ms is not None:
        deadline = decided_at_ms if decided_at_ms is not None else t_eval_ms
        return deadline - window_ms
    if decided_at_ms is not None:
        return decided_at_ms
    return t_eval_ms


def known_anchor_ms(
    instance_key: str,
    template: TemplateId,
    *,
    pending_until_ms: TimeMs | None,
    window_ms: int | None,
    plan_anchor_ms: TimeMs | None = None,
) -> TimeMs | None:
    """The anchor when a source states it (plan, dynamic key, deadline minus window), else ``None``."""
    if plan_anchor_ms is not None:
        return plan_anchor_ms
    parsed = parse_anchor_from_key(instance_key, template)
    if parsed is not None:
        return parsed
    if (
        template in (TemplateId.SCHED, TemplateId.RESP)
        and pending_until_ms is not None
        and window_ms is not None
    ):
        return pending_until_ms - window_ms
    return None
