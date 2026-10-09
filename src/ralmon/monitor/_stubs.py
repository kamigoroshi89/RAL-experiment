"""Placeholders for public names whose owner task is not done (decision D1 of WS05).

Each placeholder imports, carries ``__ralmon_stub_owner__`` and fails loudly when used.
The owner task moves its names to a real module and deletes them from this file. WS05-T04 has moved
its names (``Monitor``, ``MonitorConfig``, ``VerdictRecord``, ``VerdictState``, ``RobustnessInterval``,
``StreamingMonitor``, ``Forecast``, ``Forecaster``, ``PointEvaluator``, ``MonitorConfigError``,
``PlanVersionError``, ``run_offline`` and ``make_point_evaluator``) to real modules; the two names
below remain placeholders owned by WS05-T08.
"""

from __future__ import annotations

from typing import NoReturn

from ralmon._stub import stub_class, stub_function


@stub_class("WS05-T08")
class StaleCalibratorError: ...


@stub_function("WS05-T08")
def build_calibration_episodes(*args: object, **kwargs: object) -> NoReturn: ...
