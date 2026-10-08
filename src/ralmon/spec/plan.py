"""``TemplateInstance`` and ``CarePlan`` of 02-interfaces.md#template: the patient care plan.

A pathway template (institutional) is instantiated into a patient care plan; the plan pins the
registry version and carries an integrity signature (analisi §4.9 item 7, ``ralmon.spec.integrity``).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ralmon.signals import TimeMs
from ralmon.spec.templates import TemplateId

__all__ = ["CarePlan", "TemplateInstance"]


@dataclass(frozen=True, slots=True)
class TemplateInstance:
    template: TemplateId
    instance_key: str  # unique within a care plan, e.g. "resp@2026-01-01T07:00"
    param_values: Mapping[str, float]
    anchor_ms: TimeMs | None  # schedule tick that anchors the instance, if any


@dataclass(frozen=True, slots=True)
class CarePlan:
    care_plan_id: str
    pathway_template_id: str  # institutional pathway template it instantiates
    patient_id: str
    registry_version: str
    instances: Sequence[TemplateInstance]
    schedule: Sequence[TimeMs]  # measurement and dispense ticks
    plan_version: int
    signature: (
        str | None
    )  # integrity signature of the distributed plan (analisi §2 R1 weakness 9, §4.9 item 7)
