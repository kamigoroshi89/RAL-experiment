"""ralmon.eval: public API (see 02-interfaces.md#package-public-api).

The metrics of analisi section 5.5 (``metrics``), the seeded experiment runner (``runner``) and the adapter of the
proposed method to the ``Detector`` contract (``ours``). Names outside the table of the contract
(``Matching`` helpers, ``RunOptions``, ``load_experiment``, ``build_detector``, ``split_patients``) are listed in
``__all__`` for the experiment tasks of WS08 and for WS09.
"""

from __future__ import annotations

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

__all__ = [
    "MatchConfig",
    "Matching",
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
    "severity_rank_agreement",
]
