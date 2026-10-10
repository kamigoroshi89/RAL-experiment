"""Placeholders for public names whose owner task is not done (decision D1 of WS05).

Each placeholder imports, carries ``__ralmon_stub_owner__`` and fails loudly when used.
The owner task moves its names to a real module and deletes them from this file.
"""

from __future__ import annotations

from ralmon._stub import stub_class


@stub_class("WS06-T02")
class B1StaticThresholds: ...


@stub_class("WS06-T03")
class B2AnomalyDetection: ...


@stub_class("WS06-T04")
class B3PlainSTL: ...


@stub_class("WS06-T05")
class B4ConformalOnly: ...
