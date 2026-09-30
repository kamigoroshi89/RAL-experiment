"""Placeholders for public names whose owner task is not done (decision D1 of WS05).

Each placeholder imports, carries ``__ralmon_stub_owner__`` and fails loudly when used.
The owner task moves its names to a real module and deletes them from this file.
"""

from __future__ import annotations

from typing import NoReturn

from ralmon._stub import stub_class, stub_function


@stub_class("WS05-T03")
class Template: ...


@stub_class("WS05-T03")
class TemplateId: ...


@stub_class("WS05-T03")
class TemplateKind: ...


@stub_class("WS05-T03")
class TemplateInstance: ...


@stub_class("WS05-T03")
class CarePlan: ...


@stub_class("WS05-T03")
class RobustnessUnit: ...


@stub_class("WS05-T03")
class ParameterRegistry: ...


@stub_class("WS05-T03")
class RegistryEntry: ...


@stub_class("WS05-T03")
class PhysioBounds: ...


@stub_class("WS05-T03")
class Rho: ...


@stub_class("WS05-T03")
class RhoKind: ...


@stub_class("WS05-T03")
class PlanVerifier: ...


@stub_class("WS05-T03")
class HmacSha256PlanVerifier: ...


@stub_class("WS05-T03")
class PlanIntegrityError: ...


@stub_function("WS05-T03")
def normalise(*args: object, **kwargs: object) -> NoReturn: ...


@stub_function("WS05-T03")
def rank_alerts(*args: object, **kwargs: object) -> NoReturn: ...


@stub_function("WS05-T03")
def load_registry(*args: object, **kwargs: object) -> NoReturn: ...


@stub_function("WS05-T03")
def load_templates(*args: object, **kwargs: object) -> NoReturn: ...


@stub_function("WS05-T03")
def verify_plan(*args: object, **kwargs: object) -> NoReturn: ...
