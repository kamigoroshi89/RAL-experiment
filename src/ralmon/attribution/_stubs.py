"""Placeholders for public names whose owner task is not done (decision D1 of WS05).

Each placeholder imports, carries ``__ralmon_stub_owner__`` and fails loudly when used.
The owner task moves its names to a real module and deletes them from this file.
"""

from __future__ import annotations

from typing import NoReturn

from ralmon._stub import stub_class, stub_function


@stub_class("WS05-T07")
class EvidenceVector: ...


@stub_class("WS05-T07")
class ProvenanceEvidence: ...


@stub_class("WS05-T07")
class SystemHealthEvidence: ...


@stub_class("WS05-T07")
class SignalQualityEvidence: ...


@stub_class("WS05-T07")
class CrossDeviceEvidence: ...


@stub_class("WS05-T07")
class EmbodiedWitnessEvidence: ...


@stub_class("WS05-T07")
class CryptoTemporalEvidence: ...


@stub_class("WS05-T07")
class AttributionRule: ...


@stub_class("WS05-T07")
class Attributor: ...


@stub_class("WS05-T07")
class AttributedCause: ...


@stub_class("WS05-T07")
class Alert: ...


@stub_class("WS05-T07")
class Explanation: ...


@stub_class("WS05-T07")
class Detection: ...


@stub_class("WS05-T07")
class HierarchicalRule: ...


@stub_class("WS05-T07")
class RuleAttributor: ...


@stub_class("WS05-T07")
class EvidenceExtractor: ...


@stub_function("WS05-T07")
def extract_evidence(*args: object, **kwargs: object) -> NoReturn: ...
