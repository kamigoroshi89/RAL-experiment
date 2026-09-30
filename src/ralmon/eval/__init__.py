"""ralmon.eval: public API (see 02-interfaces.md#package-public-api)."""

from __future__ import annotations

from ralmon.eval._stubs import (
    ExperimentConfig,
    MatchConfig,
    Matching,
    OursDetector,
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
    run_experiment,
    severity_rank_agreement,
)

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
