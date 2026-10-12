"""ralmon.attribution: public API (see 02-interfaces.md#package-public-api).

The package turns violated verdict records into alerts: ``EvidenceVector`` and its parts (``evidence``), the
alert tuple (``alert``), the hierarchical rule with abstention (``rule``), the attributor with cascade root-cause
propagation (``attributor``), the nursing-staff text (``render``) and the evidence extractor (``extract``).
The likelihood attributor of ADR-074 (``LikelihoodRule``, ``load_likelihood_table``, ``AwaitingValueError``) is in the
submodule ``ralmon.attribution.likelihood``; ``RuleAttributor`` takes it as its ``rule`` (the hierarchical rule stays the
default, ``ours-hier``). Helpers outside the contract table (``Decision``, ``AbstentionReason``, ``DeviceProfile`` and ``DeviceCapabilities``
(also importable from this package root, for ``ralmon.eval.device_capabilities``), ``alert_from_record``,
``render_text``, ``empty_evidence``) are importable from the submodules and are not in ``__all__``.
"""

from __future__ import annotations

from ralmon.attribution.alert import (
    Alert,
    AttributedCause,
    Detection,
    Explanation,
)
from ralmon.attribution.attributor import Attributor, RuleAttributor
from ralmon.attribution.evidence import (
    CrossDeviceEvidence,
    CryptoTemporalEvidence,
    DispenserEvidence,
    EmbodiedWitnessEvidence,
    EvidenceVector,
    ProvenanceEvidence,
    SignalQualityEvidence,
    SystemHealthEvidence,
)
from ralmon.attribution.extract import (
    DeviceCapabilities as DeviceCapabilities,
)
from ralmon.attribution.extract import (
    DeviceProfile as DeviceProfile,
)
from ralmon.attribution.extract import (
    EvidenceExtractor,
    extract_evidence,
)
from ralmon.attribution.rule import AttributionRule, HierarchicalRule

__all__ = [
    "Alert",
    "AttributedCause",
    "AttributionRule",
    "Attributor",
    "CrossDeviceEvidence",
    "CryptoTemporalEvidence",
    "Detection",
    "DispenserEvidence",
    "EmbodiedWitnessEvidence",
    "EvidenceExtractor",
    "EvidenceVector",
    "Explanation",
    "HierarchicalRule",
    "ProvenanceEvidence",
    "RuleAttributor",
    "SignalQualityEvidence",
    "SystemHealthEvidence",
    "extract_evidence",
]
