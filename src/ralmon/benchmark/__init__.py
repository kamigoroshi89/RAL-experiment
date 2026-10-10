"""ralmon.benchmark: public API (see 02-interfaces.md#package-public-api)."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

from ralmon.benchmark.trace import (
    BenchmarkDay,
    GroundTruthEvent,
    InjectedClass,
    LatentDay,
    ObservedDay,
)

if TYPE_CHECKING:
    from ralmon.benchmark.builder import (
        BenchmarkReader as BenchmarkReader,
    )
    from ralmon.benchmark.builder import (
        generate_benchmark,
        load_benchmark,
    )
    from ralmon.benchmark.builder import (
        open_benchmark as open_benchmark,
    )
    from ralmon.benchmark.builder import (
        split_patients as split_patients,
    )
    from ralmon.benchmark.priors import (
        AdherenceParams,
        DeviceErrorModel,
        LiteraturePriorSource,
        ParamProvenance,
        PatientParams,
        PriorSource,
    )

# The names of ralmon.benchmark.priors and ralmon.benchmark.builder load on first use, so that running
# ``python -m ralmon.benchmark.priors`` does not import that module twice (runpy warns) and importing the package
# stays light (the builder imports the registry and the monitor).
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


# ``generate_benchmark`` and ``load_benchmark`` are in the contract table; ``open_benchmark``, ``BenchmarkReader``
# and ``split_patients`` are importable from the package root and stay outside ``__all__`` until the contract
# table lists them (the table of ``#package-public-api`` is frozen; issue I9 of the WS04 README).
_BUILDER_NAMES = frozenset(
    {
        "BenchmarkReader",
        "generate_benchmark",
        "load_benchmark",
        "open_benchmark",
        "split_patients",
    }
)


def __getattr__(name: str) -> Any:
    if name in _PRIORS_NAMES:
        value = getattr(importlib.import_module("ralmon.benchmark.priors"), name)
        globals()[name] = value
        return value
    if name in _BUILDER_NAMES:
        value = getattr(importlib.import_module("ralmon.benchmark.builder"), name)
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
