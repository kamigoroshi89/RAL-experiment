"""Placeholders for public names whose owner task is not done (decision D1 of WS05).

Each placeholder imports, carries ``__ralmon_stub_owner__`` and fails loudly when used.
The owner task moves its names to a real module and deletes them from this file.
"""

from __future__ import annotations

from typing import NoReturn

from ralmon._stub import stub_class, stub_function


@stub_class("WS05-T02")
class SignalId: ...


@stub_class("WS05-T02")
class Sample: ...


@stub_class("WS05-T02")
class Event: ...


@stub_class("WS05-T02")
class EventKind: ...


@stub_class("WS05-T02")
class DerivedSignal: ...


@stub_class("WS05-T02")
class ObservedTrace: ...


@stub_function("WS05-T02")
def hold_last(*args: object, **kwargs: object) -> NoReturn: ...


@stub_function("WS05-T02")
def minutes(*args: object, **kwargs: object) -> NoReturn: ...


@stub_function("WS05-T02")
def hours(*args: object, **kwargs: object) -> NoReturn: ...


@stub_function("WS05-T02")
def default_derived_signals(*args: object, **kwargs: object) -> NoReturn: ...


@stub_function("WS05-T02")
def event_to_sample(*args: object, **kwargs: object) -> NoReturn: ...


@stub_function("WS05-T02")
def impulses_on_grid(*args: object, **kwargs: object) -> NoReturn: ...
