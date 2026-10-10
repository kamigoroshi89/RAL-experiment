"""ralmon.eval: public API (see 02-interfaces.md#package-public-api).

The metrics of analisi section 5.5 (``metrics``), the seeded experiment runner (``runner``) and the adapter of the
proposed method to the ``Detector`` contract (``ours``). ``__all__`` is the ``ralmon.eval`` row of the contract table.
Names that the experiment tasks of WS08 and WS09 need and that the table does not list (``RunOptions``,
``load_experiment``, ``build_detector``, ``split_patients``, ``PipelineComponents``, ``HookResult``, ``RunContext``,
``ConfigError``, ``GuardError`` and the metric helpers) are importable from this package and stay outside ``__all__``
until the table is amended (the same arrangement as ``open_benchmark`` in ``ralmon.benchmark``).

The runner and the detector load on first use, so that ``python -m ralmon.eval.runner`` does not import the module twice.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

from ralmon.eval.metrics import (
    MatchConfig,
    Matching,
    accuracy_vs_coverage,
    attribution_confusion,
    detection_delay_ms,
    empirical_coverage,
    expected_calibration_error,
    false_alarms_per_patient_day,
    latency_percentiles,
    match_events,
    mean_interval_width,
    per_class_prf,
    recall_vs_false_alarm_curve,
    severity_rank_agreement,
)

if TYPE_CHECKING:
    from ralmon.eval.ours import OursDetector as OursDetector
    from ralmon.eval.ours import PipelineComponents as PipelineComponents
    from ralmon.eval.runner import (
        ConfigError as ConfigError,
    )
    from ralmon.eval.runner import (
        ExperimentConfig as ExperimentConfig,
    )
    from ralmon.eval.runner import (
        GuardError as GuardError,
    )
    from ralmon.eval.runner import (
        HookResult as HookResult,
    )
    from ralmon.eval.runner import (
        RunContext as RunContext,
    )
    from ralmon.eval.runner import (
        RunOptions as RunOptions,
    )
    from ralmon.eval.runner import (
        build_detector as build_detector,
    )
    from ralmon.eval.runner import (
        load_experiment as load_experiment,
    )
    from ralmon.eval.runner import (
        run_experiment as run_experiment,
    )
    from ralmon.eval.runner import (
        split_patients as split_patients,
    )

_OURS_NAMES = frozenset({"OursDetector", "PipelineComponents"})
_RUNNER_NAMES = frozenset(
    {
        "ConfigError",
        "ExperimentConfig",
        "GuardError",
        "HookResult",
        "RunContext",
        "RunOptions",
        "build_detector",
        "load_experiment",
        "run_experiment",
        "split_patients",
    }
)


def __getattr__(name: str) -> Any:
    if name in _OURS_NAMES:
        value = getattr(importlib.import_module("ralmon.eval.ours"), name)
    elif name in _RUNNER_NAMES:
        value = getattr(importlib.import_module("ralmon.eval.runner"), name)
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted({*globals(), *__all__})


__all__ = [
    "ExperimentConfig",
    "MatchConfig",
    "Matching",
    "OursDetector",
    "accuracy_vs_coverage",
    "attribution_confusion",
    "detection_delay_ms",
    "empirical_coverage",
    "expected_calibration_error",
    "false_alarms_per_patient_day",
    "latency_percentiles",
    "match_events",
    "mean_interval_width",
    "per_class_prf",
    "recall_vs_false_alarm_curve",
    "run_experiment",
    "severity_rank_agreement",
]
