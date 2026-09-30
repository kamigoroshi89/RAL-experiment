"""Placeholders for public names whose owner task is not done (decision D1 of WS05).

Each placeholder imports, carries ``__ralmon_stub_owner__`` and fails loudly when used.
The owner task moves its names to a real module and deletes them from this file.
"""

from __future__ import annotations

from typing import NoReturn

from ralmon._stub import stub_class, stub_function


@stub_class("WS04-T01")
class BenchmarkDay: ...


@stub_class("WS04-T01")
class ObservedDay: ...


@stub_class("WS04-T01")
class LatentDay: ...


@stub_class("WS04-T01")
class GroundTruthEvent: ...


@stub_class("WS04-T01")
class InjectedClass: ...


@stub_class("WS04-T02")
class PriorSource: ...


@stub_class("WS04-T02")
class LiteraturePriorSource: ...


@stub_class("WS04-T02")
class PatientParams: ...


@stub_class("WS04-T02")
class AdherenceParams: ...


@stub_class("WS04-T02")
class DeviceErrorModel: ...


@stub_class("WS04-T02")
class ParamProvenance: ...


@stub_function("WS04-T11")
def generate_benchmark(*args: object, **kwargs: object) -> NoReturn: ...


@stub_function("WS04-T11")
def load_benchmark(*args: object, **kwargs: object) -> NoReturn: ...
