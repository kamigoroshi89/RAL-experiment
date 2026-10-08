"""ralmon.spec: public API (see 02-interfaces.md#package-public-api).

``__all__`` is the ``ralmon.spec`` row of the contract table (ADR-024). The error types and helpers
below it (``RegistryError``, ``UnsetParameterError``, ``TemplateLibraryError``, ``LoadedRegistry``,
``as_duration_ms``, ``as_priority``) are importable from this package root, so that other packages
respect the rule of importing package roots only, but they are outside ``__all__`` until the proposed
ADR-047 puts them in the contract table.
"""

from __future__ import annotations

from ralmon.spec.integrity import (
    HmacSha256PlanVerifier,
    PlanIntegrityError,
    PlanVerifier,
    verify_plan,
)
from ralmon.spec.normalise import normalise, rank_alerts
from ralmon.spec.plan import CarePlan, TemplateInstance
from ralmon.spec.registry import (
    LoadedRegistry as LoadedRegistry,
)
from ralmon.spec.registry import (
    ParameterRegistry,
    PhysioBounds,
    RegistryEntry,
    load_registry,
)
from ralmon.spec.registry import (
    RegistryError as RegistryError,
)
from ralmon.spec.registry import (
    UnsetParameterError as UnsetParameterError,
)
from ralmon.spec.registry import (
    as_duration_ms as as_duration_ms,
)
from ralmon.spec.registry import (
    as_priority as as_priority,
)
from ralmon.spec.rho import Rho, RhoKind
from ralmon.spec.templates import (
    RobustnessUnit,
    Template,
    TemplateId,
    TemplateKind,
    load_templates,
)
from ralmon.spec.templates import (
    TemplateLibraryError as TemplateLibraryError,
)

__all__ = [
    "CarePlan",
    "HmacSha256PlanVerifier",
    "ParameterRegistry",
    "PhysioBounds",
    "PlanIntegrityError",
    "PlanVerifier",
    "RegistryEntry",
    "Rho",
    "RhoKind",
    "RobustnessUnit",
    "Template",
    "TemplateId",
    "TemplateInstance",
    "TemplateKind",
    "load_registry",
    "load_templates",
    "normalise",
    "rank_alerts",
    "verify_plan",
]
