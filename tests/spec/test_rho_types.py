"""``Rho`` and ``RhoKind``: one definition in ``ralmon.spec``, re-exported by ``ralmon.monitor``
(02-interfaces.md#verdict, ADR-024). Test 29 of WS05-T03."""

from __future__ import annotations

import ast
import dataclasses

import pytest

import ralmon.monitor
import ralmon.spec
from ralmon.spec import Rho, RhoKind

from .helpers import SRC_RALMON


def test_rho_and_rhokind_are_single_definition() -> None:
    assert [f.name for f in dataclasses.fields(Rho)] == [
        "value",
        "kind",
        "guarantee",
        "alpha",
        "assumptions",
    ]
    assert Rho.__dataclass_params__.frozen is True  # type: ignore[attr-defined]
    assert "__slots__" in vars(Rho)
    assert {m.name: m.value for m in RhoKind} == {
        "MEASURED": "measured",
        "PREDICTED": "predicted",
        "DETERMINISTIC": "deterministic",
    }
    assert [m.value for m in RhoKind] == ["measured", "predicted", "deterministic"]
    assert issubclass(RhoKind, str)
    assert ralmon.monitor.Rho is ralmon.spec.Rho
    assert ralmon.monitor.RhoKind is ralmon.spec.RhoKind


def test_rho_is_frozen_slotted_and_hashable_by_value() -> None:
    rho = Rho(0.9, RhoKind.MEASURED, "P(sigma_true < 0 | measurement)", None, ("a",))
    with pytest.raises(dataclasses.FrozenInstanceError):
        rho.value = 0.1  # type: ignore[misc]
    with pytest.raises((AttributeError, TypeError)):
        rho.extra = 1  # type: ignore[attr-defined]
    assert not hasattr(rho, "__dict__")
    assert rho == Rho(
        0.9, RhoKind.MEASURED, "P(sigma_true < 0 | measurement)", None, ("a",)
    )
    assert hash(rho) == hash(
        Rho(0.9, RhoKind.MEASURED, "P(sigma_true < 0 | measurement)", None, ("a",))
    )
    assert rho != Rho(0.9, RhoKind.PREDICTED, "g", 0.1, ("a",))


def test_rho_takes_the_five_fields_positionally_and_by_name() -> None:
    by_position = Rho(1.0, RhoKind.DETERMINISTIC, "event-log predicate", None, ())
    by_name = Rho(
        value=1.0,
        kind=RhoKind.DETERMINISTIC,
        guarantee="event-log predicate",
        alpha=None,
        assumptions=(),
    )
    assert by_position == by_name


def test_rhokind_members_are_strings() -> None:
    assert RhoKind("measured") is RhoKind.MEASURED
    assert RhoKind.PREDICTED == "predicted"
    with pytest.raises(ValueError):
        RhoKind("Measured")


def test_there_is_one_definition_of_rho_in_the_sources() -> None:
    definitions: dict[str, list[str]] = {"Rho": [], "RhoKind": []}
    for path in sorted(SRC_RALMON.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name in definitions:
                definitions[node.name].append(str(path.relative_to(SRC_RALMON)))
    assert definitions == {
        "Rho": ["spec/rho.py"],
        "RhoKind": ["spec/rho.py"],
    }


def test_the_monitor_reexport_is_a_reexport_not_a_stub() -> None:
    assert not hasattr(ralmon.monitor.Rho, "__ralmon_stub_owner__")
    assert not hasattr(ralmon.monitor.RhoKind, "__ralmon_stub_owner__")
    assert ralmon.monitor.Rho.__module__ == "ralmon.spec.rho"
