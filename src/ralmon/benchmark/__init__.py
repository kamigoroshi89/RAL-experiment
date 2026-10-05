"""ralmon.benchmark: public API (see 02-interfaces.md#package-public-api)."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

from ralmon.benchmark._stubs import generate_benchmark, load_benchmark
from ralmon.benchmark.trace import (
    BenchmarkDay,
    GroundTruthEvent,
    InjectedClass,
    LatentDay,
    ObservedDay,
)

if TYPE_CHECKING:
    from ralmon.benchmark.priors import (
        AdherenceParams,
        DeviceErrorModel,
        LiteraturePriorSource,
        ParamProvenance,
        PatientParams,
        PriorSource,
    )

# The names of ralmon.benchmark.priors load on first use, so that running
# ``python -m ralmon.benchmark.priors`` does not import that module twice (runpy warns).
_PRIORS_NAMES = frozenset(
    {
        "AdherenceParams",
        "DeviceErrorModel",
        "LiteraturePriorSource",
        "ParamProvenance",
        "PatientParams",
        "PriorSource",
    }
)


def __getattr__(name: str) -> Any:
    if name in _PRIORS_NAMES:
        value = getattr(importlib.import_module("ralmon.benchmark.priors"), name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted({*globals(), *__all__})


__all__ = [
    "AdherenceParams",
    "BenchmarkDay",
    "DeviceErrorModel",
    "GroundTruthEvent",
    "InjectedClass",
    "LatentDay",
    "LiteraturePriorSource",
    "ObservedDay",
    "ParamProvenance",
    "PatientParams",
    "PriorSource",
    "generate_benchmark",
    "load_benchmark",
]
