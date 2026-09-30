"""Placeholders for public names whose owner task is not done (decision D1 of WS05).

Each placeholder imports, carries ``__ralmon_stub_owner__`` and fails loudly when used.
The owner task moves its names to a real module and deletes them from this file.
"""

from __future__ import annotations

from ralmon._stub import stub_class


@stub_class("WS05-T06")
class ConformalCalibrator: ...


@stub_class("WS05-T06")
class CalibrationEpisode: ...


@stub_class("WS05-T06")
class PredictedViolation: ...


@stub_class("WS05-T06")
class AlphaAllocation: ...


@stub_class("WS05-T06")
class SplitConformal: ...


@stub_class("WS05-T06")
class AdaptiveConformal: ...


@stub_class("WS05-T06")
class BonferroniAllocation: ...
