"""Placeholders for public names whose owner task is not done (decision D1 of WS05).

Each placeholder imports, carries ``__ralmon_stub_owner__`` and fails loudly when used.
The owner task moves its names to a real module and deletes them from this file.
"""

from __future__ import annotations

from typing import NoReturn

from ralmon._stub import stub_class, stub_function


@stub_class("WS05-T04")
class Monitor: ...


@stub_class("WS05-T04")
class MonitorConfig: ...


@stub_class("WS05-T04")
class VerdictRecord: ...


@stub_class("WS05-T04")
class VerdictState: ...


@stub_class("WS05-T04")
class RobustnessInterval: ...


@stub_class("WS05-T04")
class StreamingMonitor: ...


@stub_class("WS05-T04")
class Forecast: ...


@stub_class("WS05-T04")
class Forecaster: ...


@stub_class("WS05-T04")
class PointEvaluator: ...


@stub_class("WS05-T04")
class MonitorConfigError: ...


@stub_class("WS05-T04")
class PlanVersionError: ...


@stub_function("WS05-T04")
def run_offline(*args: object, **kwargs: object) -> NoReturn: ...


@stub_function("WS05-T04")
def make_point_evaluator(*args: object, **kwargs: object) -> NoReturn: ...


@stub_class("WS05-T08")
class StaleCalibratorError: ...


@stub_function("WS05-T08")
def build_calibration_episodes(*args: object, **kwargs: object) -> NoReturn: ...
