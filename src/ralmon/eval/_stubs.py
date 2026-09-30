"""Placeholders for public names whose owner task is not done (decision D1 of WS05).

Each placeholder imports, carries ``__ralmon_stub_owner__`` and fails loudly when used.
The owner task moves its names to a real module and deletes them from this file.
"""

from __future__ import annotations

from typing import NoReturn

from ralmon._stub import stub_class, stub_function


@stub_class("WS08-T01")
class MatchConfig: ...


@stub_class("WS08-T01")
class Matching: ...


@stub_class("WS08-T01")
class OursDetector: ...


@stub_class("WS08-T01")
class ExperimentConfig: ...


@stub_function("WS08-T01")
def match_events(*args: object, **kwargs: object) -> NoReturn: ...


@stub_function("WS08-T01")
def per_class_prf(*args: object, **kwargs: object) -> NoReturn: ...


@stub_function("WS08-T01")
def detection_delay_ms(*args: object, **kwargs: object) -> NoReturn: ...


@stub_function("WS08-T01")
def false_alarms_per_patient_day(*args: object, **kwargs: object) -> NoReturn: ...


@stub_function("WS08-T01")
def empirical_coverage(*args: object, **kwargs: object) -> NoReturn: ...


@stub_function("WS08-T01")
def expected_calibration_error(*args: object, **kwargs: object) -> NoReturn: ...


@stub_function("WS08-T01")
def attribution_confusion(*args: object, **kwargs: object) -> NoReturn: ...


@stub_function("WS08-T01")
def latency_percentiles(*args: object, **kwargs: object) -> NoReturn: ...


@stub_function("WS08-T01")
def mean_interval_width(*args: object, **kwargs: object) -> NoReturn: ...


@stub_function("WS08-T01")
def recall_vs_false_alarm_curve(*args: object, **kwargs: object) -> NoReturn: ...


@stub_function("WS08-T01")
def accuracy_vs_coverage(*args: object, **kwargs: object) -> NoReturn: ...


@stub_function("WS08-T01")
def severity_rank_agreement(*args: object, **kwargs: object) -> NoReturn: ...


@stub_function("WS08-T01")
def run_experiment(*args: object, **kwargs: object) -> NoReturn: ...
