"""Hostile objects at the public entry points of ``ralmon.spec``: only the module's named error.

A hostile object raises ``RuntimeError`` from ``__repr__``, ``__str__``, ``__getattr__``,
``__getattribute__``, ``__class__``, ``__iter__``, ``__bool__``, ``__len__``, ``__eq__``, ``__hash__``,
``__float__``, ``__int__``, ``__index__``, ``__lt__``, ``__getitem__``, ``__contains__`` or
``__fspath__``. Each is passed in every argument position of every public function, loader and
constructor; the call may succeed or raise the named error of its module, and nothing else may
escape (docs/plan/01-conventions.md section 2: specific exceptions per package).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterator, Mapping
from types import SimpleNamespace
from typing import Any

import pytest

from ralmon.spec import (
    CarePlan,
    HmacSha256PlanVerifier,
    PlanIntegrityError,
    RegistryEntry,
    TemplateId,
    TemplateInstance,
    load_registry,
    load_templates,
    normalise,
    rank_alerts,
    verify_plan,
)
from ralmon.spec.integrity import canonical_plan_bytes
from ralmon.spec.registry import RegistryError, as_duration_ms, as_priority
from ralmon.spec.templates import TemplateLibraryError

from .helpers import F0_PATH, STEP_MS, TEMPLATES_PATH


def _boom(*args: object, **kwargs: object) -> Any:
    raise RuntimeError("hostile object")


_METHODS = (
    "__repr__",
    "__str__",
    "__getattr__",
    "__getattribute__",
    "__iter__",
    "__bool__",
    "__len__",
    "__eq__",
    "__hash__",
    "__float__",
    "__int__",
    "__index__",
    "__lt__",
    "__getitem__",
    "__contains__",
    "__fspath__",
)


class HostileStr(str):
    __hash__ = _boom  # type: ignore[assignment]
    __eq__ = _boom  # type: ignore[assignment]
    __lt__ = _boom
    __getitem__ = _boom
    __len__ = _boom


class HostileInt(int):
    __hash__ = _boom  # type: ignore[assignment]
    __eq__ = _boom  # type: ignore[assignment]
    __lt__ = _boom
    __gt__ = _boom
    __float__ = _boom
    __index__ = _boom
    __int__ = _boom
    __bool__ = _boom


class HostileFloat(float):
    __hash__ = _boom  # type: ignore[assignment]
    __eq__ = _boom  # type: ignore[assignment]
    __lt__ = _boom
    __gt__ = _boom
    __float__ = _boom
    __bool__ = _boom


class HostileList(list[Any]):
    __iter__ = _boom
    __len__ = _boom
    __getitem__ = _boom


class HostileTuple(tuple[Any, ...]):
    __iter__ = _boom
    __len__ = _boom
    __getitem__ = _boom


class HostileDict(dict[Any, Any]):
    __iter__ = _boom
    __getitem__ = _boom
    __len__ = _boom

    def items(self) -> Any:
        raise RuntimeError("hostile object")


def hostile_objects() -> list[tuple[str, Any]]:
    objects: list[tuple[str, Any]] = [
        (m.strip("_"), type(f"Hostile{m.strip('_')}", (), {m: _boom})())
        for m in _METHODS
    ]
    objects.append(
        ("class", type("HostileClass", (), {"__class__": property(_boom)})())
    )
    objects.extend(
        [
            ("str", HostileStr("name")),
            ("int", HostileInt(5)),
            ("float", HostileFloat(1.5)),
            ("list", HostileList([1, 2])),
            ("tuple", HostileTuple((1, 2))),
            ("dict", HostileDict({"a": 1})),
        ]
    )
    return objects


HOSTILE = hostile_objects()
IDS = [name for name, _ in HOSTILE]

_REGISTRY = load_registry(F0_PATH, step_ms=STEP_MS, allow_fixture_only=True)
_GOOD_PLAN = CarePlan(
    "cp",
    "pt",
    "p",
    "0.0.0",
    (TemplateInstance(TemplateId.RANGE, "k", {"a": 1.0}, 1),),
    (1, 2),
    1,
    None,
)
_VERIFIER = HmacSha256PlanVerifier(b"key")
_SIGNED = dataclasses.replace(_GOOD_PLAN, signature=_VERIFIER.sign(_GOOD_PLAN))
_ALERT = {"priority": 1, "sigma_norm": -0.5, "t_ms": 1, "instance_key": "k"}


class _Registry:
    """A bare ParameterRegistry whose answer for every name is the hostile object."""

    def __init__(self, answer: Any) -> None:
        self._answer = answer

    def get(self, name: str) -> Any:
        return self._answer

    def bounds(self, signal: str) -> Any:
        return self._answer

    def version(self) -> str:
        return "0"


def _with(**changes: Any) -> Callable[[Any], Any]:
    """A call that puts the hostile object in the named field of a valid alert."""

    def call(h: Any) -> Any:
        fields = {**_ALERT, **{k: h if v == "H" else v for k, v in changes.items()}}
        return rank_alerts([SimpleNamespace(**fields)])

    return call


NORMALISE_CALLS: list[Callable[[Any], Any]] = [
    lambda h: normalise(h, 1.0),
    lambda h: normalise(1.0, h),
    lambda h: normalise(h, h),
    lambda h: normalise(float("inf"), h),
]
RANK_CALLS: list[Callable[[Any], Any]] = [
    lambda h: rank_alerts(h),
    lambda h: rank_alerts([h]),
    lambda h: rank_alerts([SimpleNamespace(**_ALERT), h]),
    _with(priority="H"),
    _with(sigma_norm="H"),
    _with(t_ms="H"),
    _with(instance_key="H"),
    _with(xi="H"),
    lambda h: rank_alerts(
        [SimpleNamespace(**{**_ALERT, "xi": SimpleNamespace(instance_key=h)})]
    ),
    lambda h: rank_alerts(HostileList([SimpleNamespace(**_ALERT)])),
]
REGISTRY_CALLS: list[Callable[[Any], Any]] = [
    lambda h: load_registry(h),
    lambda h: load_registry(F0_PATH, step_ms=h, allow_fixture_only=True),
    lambda h: load_registry(F0_PATH, allow_fixture_only=h),
    lambda h: _REGISTRY.get(h),
    lambda h: _REGISTRY.bounds(h),
    lambda h: _REGISTRY.is_declared(h),
    lambda h: _REGISTRY.is_set(h),
    lambda h: as_duration_ms(h),
    lambda h: as_priority(h),
    lambda h: as_duration_ms(RegistryEntry(h, h, h, h, h, h)),
    lambda h: as_duration_ms(RegistryEntry("n", h, "ms", "r", "s", None)),
    lambda h: as_duration_ms(RegistryEntry("n", 1.5, "ms", "r", "s", h)),
    lambda h: as_priority(RegistryEntry(h, 0.0, "1", "r", "s", None)),
    lambda h: as_priority(RegistryEntry("n", h, "1", "r", "s", None)),
    lambda h: as_priority(RegistryEntry("n", 1.0, h, "r", "s", None)),
]
TEMPLATE_CALLS: list[Callable[[Any], Any]] = [
    lambda h: load_templates(h, _REGISTRY),
    lambda h: load_templates(TEMPLATES_PATH, h),
    lambda h: load_templates(TEMPLATES_PATH, _Registry(h)),
]


class _OneKey(Mapping[Any, float]):
    """A mapping with one key that is never hashed (a dict literal would hash a hostile key itself)."""

    def __init__(self, key: Any) -> None:
        self._key = key

    def __getitem__(self, key: Any) -> float:
        return 1.0

    def __iter__(self) -> Iterator[Any]:
        yield self._key

    def __len__(self) -> int:
        return 1


def _plan_with(**changes: Any) -> CarePlan:
    return dataclasses.replace(_GOOD_PLAN, **changes)


def _instance_with(**changes: Any) -> CarePlan:
    return _plan_with(
        instances=(dataclasses.replace(_GOOD_PLAN.instances[0], **changes),)
    )


PLAN_CALLS: list[Callable[[Any], Any]] = [
    lambda h: canonical_plan_bytes(h),
    lambda h: canonical_plan_bytes(_plan_with(care_plan_id=h)),
    lambda h: canonical_plan_bytes(_plan_with(pathway_template_id=h)),
    lambda h: canonical_plan_bytes(_plan_with(patient_id=h)),
    lambda h: canonical_plan_bytes(_plan_with(registry_version=h)),
    lambda h: canonical_plan_bytes(_plan_with(instances=h)),
    lambda h: canonical_plan_bytes(_plan_with(instances=(h,))),
    lambda h: canonical_plan_bytes(_plan_with(schedule=h)),
    lambda h: canonical_plan_bytes(_plan_with(schedule=(h,))),
    lambda h: canonical_plan_bytes(_plan_with(plan_version=h)),
    lambda h: canonical_plan_bytes(_instance_with(template=h)),
    lambda h: canonical_plan_bytes(_instance_with(instance_key=h)),
    lambda h: canonical_plan_bytes(_instance_with(param_values=h)),
    lambda h: canonical_plan_bytes(_instance_with(param_values={"a": h})),
    lambda h: canonical_plan_bytes(_instance_with(param_values=_OneKey(h))),
    lambda h: canonical_plan_bytes(_instance_with(anchor_ms=h)),
    lambda h: HmacSha256PlanVerifier(h),
    lambda h: _VERIFIER.sign(h),
    lambda h: _VERIFIER.verify(h, "0" * 64),
    lambda h: _VERIFIER.verify(b"payload", h),
    lambda h: verify_plan(h, _VERIFIER),
    lambda h: verify_plan(_SIGNED, h),
    lambda h: verify_plan(_SIGNED, _VERIFIER, registry_version=h),
    lambda h: verify_plan(_SIGNED, _VERIFIER, require_signature=h),
    lambda h: verify_plan(_plan_with(signature=h), _VERIFIER),
    lambda h: verify_plan(
        _plan_with(registry_version=h), None, registry_version="0.0.0"
    ),
]

ALL_CALLS: list[tuple[str, type[Exception], list[Callable[[Any], Any]]]] = [
    ("normalise", ValueError, NORMALISE_CALLS),
    ("rank_alerts", ValueError, RANK_CALLS),
    ("registry", RegistryError, REGISTRY_CALLS),
    ("templates", TemplateLibraryError, TEMPLATE_CALLS),
    ("plan", PlanIntegrityError, PLAN_CALLS),
]


HOSTILE_BY_ID = dict(HOSTILE)


@pytest.mark.parametrize(
    "hostile_id", IDS
)  # ids, not the objects: pytest must not touch them
@pytest.mark.parametrize(
    ("group", "error", "calls"), ALL_CALLS, ids=[g for g, _, _ in ALL_CALLS]
)
def test_a_hostile_object_never_leaks_a_raw_exception(
    group: str,
    error: type[Exception],
    calls: list[Callable[[Any], Any]],
    hostile_id: str,
) -> None:
    hostile = HOSTILE_BY_ID[hostile_id]
    for index, call in enumerate(calls):
        try:
            call(hostile)
        except error:
            continue
        except Exception as exc:  # noqa: BLE001 - report which call leaked what
            pytest.fail(
                f"{group} call #{index} leaked {type(exc).__name__}: {exc!s}"[:300]
            )


def test_the_original_exception_type_is_kept_in_the_message_and_chained() -> None:
    hostile = type("HostileGetattr", (), {"__getattribute__": _boom})()
    with pytest.raises(RegistryError) as info:
        _REGISTRY.get(hostile)  # the isinstance check itself raises
    assert "RuntimeError" in str(info.value)
    assert isinstance(info.value.__cause__, RuntimeError)
    with pytest.raises(PlanIntegrityError) as plan_info:
        canonical_plan_bytes(hostile)  # type: ignore[arg-type]
    assert "RuntimeError" in str(plan_info.value)
    assert isinstance(plan_info.value.__cause__, RuntimeError)


def test_the_named_error_passes_through_unchanged() -> None:
    """The boundary converts foreign exceptions only: a RegistryError keeps its own message."""
    with pytest.raises(RegistryError, match="unknown parameter") as info:
        _REGISTRY.get("no_such_name")
    assert info.value.__cause__ is None


def test_a_verifier_that_raises_a_foreign_error_is_reported_with_its_type() -> None:
    class Exploding:
        def verify(self, payload: bytes, signature: str) -> bool:
            raise RuntimeError("boom")

    with pytest.raises(PlanIntegrityError, match="RuntimeError.*boom"):
        verify_plan(_SIGNED, Exploding())
