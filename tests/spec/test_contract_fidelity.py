"""The dataclasses, enums and protocols of ``ralmon.spec`` are the contract, field for field.

Test 23 of WS05-T03 (hand-copied values) and a script that compares every contract class with the code
blocks of ``docs/plan/02-interfaces.md`` (#parameter-registry, #template, #verdict): names, order,
annotation text, ``frozen`` and ``slots``, enum members and values, protocol methods.
"""

from __future__ import annotations

import ast
import dataclasses
import enum
import inspect
import re
import typing
from typing import Any

import pytest

from ralmon.spec import (
    CarePlan,
    ParameterRegistry,
    PhysioBounds,
    RegistryEntry,
    Rho,
    RhoKind,
    RobustnessUnit,
    Template,
    TemplateId,
    TemplateInstance,
    TemplateKind,
    normalise,
    rank_alerts,
)

from .helpers import INTERFACES

# --- test 23: hand-copied from the contract ---------------------------------------------


def test_enums_match_contract() -> None:
    assert {m.name: m.value for m in TemplateKind} == {
        "CARE_PLAN": "phi_cp",
        "SYSTEM": "phi_sys",
        "INTEGRITY": "phi_int",
    }
    assert {m.name: m.value for m in TemplateId} == {
        "RANGE": "range",
        "SCHED": "sched",
        "HOLD": "hold",
        "COUNT": "count",
        "RESP": "resp",
        "SYS": "sys",
        "INT": "int",
    }
    assert {m.name: m.value for m in RobustnessUnit} == {
        "MMHG": "mmHg",
        "MS": "ms",
        "DOSE": "dose",
        "DIMENSIONLESS": "1",
    }
    assert {m.name: m.value for m in RhoKind} == {
        "MEASURED": "measured",
        "PREDICTED": "predicted",
        "DETERMINISTIC": "deterministic",
    }
    for enum_class in (TemplateKind, TemplateId, RobustnessUnit, RhoKind):
        assert issubclass(enum_class, str) and issubclass(enum_class, enum.Enum)
    assert [m.name for m in TemplateId] == [
        "RANGE",
        "SCHED",
        "HOLD",
        "COUNT",
        "RESP",
        "SYS",
        "INT",
    ]


def field_names(cls: type) -> list[str]:
    return [f.name for f in dataclasses.fields(cls)]


def test_dataclass_fields_and_order_match_contract() -> None:
    assert field_names(Template) == [
        "id",
        "kind",
        "formula_past_time",
        "signals",
        "params",
        "unit",
        "scale_param",
        "priority_param",
        "max_verdict_latency_param",
        "creates_robot_obligation",
    ]
    assert field_names(TemplateInstance) == [
        "template",
        "instance_key",
        "param_values",
        "anchor_ms",
    ]
    assert field_names(CarePlan) == [
        "care_plan_id",
        "pathway_template_id",
        "patient_id",
        "registry_version",
        "instances",
        "schedule",
        "plan_version",
        "signature",
    ]
    assert field_names(RegistryEntry) == [
        "name",
        "value",
        "unit",
        "rationale",
        "source_ref",
        "reviewed_by",
    ]
    assert field_names(PhysioBounds) == ["signal", "lower", "upper"]
    assert field_names(Rho) == ["value", "kind", "guarantee", "alpha", "assumptions"]


@pytest.mark.parametrize(
    "cls",
    [Template, TemplateInstance, CarePlan, RegistryEntry, PhysioBounds, Rho],
    ids=lambda c: c.__name__,
)
def test_contract_dataclasses_are_frozen_and_slotted(cls: type) -> None:
    assert cls.__dataclass_params__.frozen is True  # type: ignore[attr-defined]
    assert tuple(vars(cls)["__slots__"]) == tuple(field_names(cls))
    assert not any(
        f.default is not dataclasses.MISSING for f in dataclasses.fields(cls)
    )


def test_parameter_registry_is_a_protocol_with_the_three_methods() -> None:
    assert getattr(ParameterRegistry, "_is_protocol", False) is True
    methods = {
        n
        for n, v in vars(ParameterRegistry).items()
        if inspect.isfunction(v) and not n.startswith("_")
    }
    assert methods == {"get", "bounds", "version"}
    assert list(inspect.signature(ParameterRegistry.get).parameters) == ["self", "name"]
    assert list(inspect.signature(ParameterRegistry.bounds).parameters) == [
        "self",
        "signal",
    ]
    assert list(inspect.signature(ParameterRegistry.version).parameters) == ["self"]


def test_normalise_and_rank_alerts_signatures() -> None:
    assert list(inspect.signature(normalise).parameters) == ["sigma_raw", "scale"]
    assert list(inspect.signature(rank_alerts).parameters) == ["alerts"]
    assert normalise.__doc__ and "clip" in normalise.__doc__
    assert rank_alerts.__doc__ and "priority" in rank_alerts.__doc__


# --- the script: compare with the code blocks of the contract ---------------------------

SECTIONS = ("Parameter registry", "Template", "Verdict")
CONTRACT_NAMES = {
    "RegistryEntry": RegistryEntry,
    "PhysioBounds": PhysioBounds,
    "ParameterRegistry": ParameterRegistry,
    "TemplateKind": TemplateKind,
    "TemplateId": TemplateId,
    "RobustnessUnit": RobustnessUnit,
    "Template": Template,
    "TemplateInstance": TemplateInstance,
    "CarePlan": CarePlan,
    "RhoKind": RhoKind,
    "Rho": Rho,
}


def contract_classes() -> dict[str, ast.ClassDef]:
    text = INTERFACES.read_text(encoding="utf-8")
    found: dict[str, ast.ClassDef] = {}
    for section in SECTIONS:
        body = text.split(f"\n## {section}\n", 1)[1].split("\n## ", 1)[0]
        for block in re.findall(r"```python\n(.*?)```", body, flags=re.DOTALL):
            for node in ast.parse(block).body:
                if isinstance(node, ast.ClassDef) and node.name in CONTRACT_NAMES:
                    found[node.name] = node
    return found


def normal(annotation: str) -> str:
    return ast.unparse(ast.parse(annotation, mode="eval").body)


CONTRACT = contract_classes()


def test_every_contract_class_was_found_in_the_contract_text() -> None:
    assert set(CONTRACT) == set(CONTRACT_NAMES)


@pytest.mark.parametrize("name", sorted(CONTRACT), ids=str)
def test_class_matches_the_code_block_of_the_contract(name: str) -> None:
    node, cls = CONTRACT[name], CONTRACT_NAMES[name]
    decorators = [ast.unparse(d) for d in node.decorator_list]
    bases = [ast.unparse(b) for b in node.bases]
    if decorators:  # a dataclass
        assert decorators == ["dataclass(frozen=True, slots=True)"]
        assert dataclasses.is_dataclass(cls)
        params: Any = cls.__dataclass_params__  # type: ignore[attr-defined]
        assert params.frozen is True
        assert "__slots__" in vars(cls)
        contract_fields = [
            (stmt.target.id, normal(ast.unparse(stmt.annotation)))
            for stmt in node.body
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
        ]
        code_fields = [
            (f.name, normal(f.type if isinstance(f.type, str) else str(f.type)))
            for f in dataclasses.fields(cls)
        ]
        assert code_fields == contract_fields
    elif bases == ["str", "Enum"]:
        assert issubclass(cls, str) and issubclass(cls, enum.Enum)
        contract_members = [
            (stmt.targets[0].id, ast.literal_eval(stmt.value))  # type: ignore[attr-defined]
            for stmt in node.body
            if isinstance(stmt, ast.Assign)
        ]
        assert [(m.name, m.value) for m in cls] == contract_members  # type: ignore[attr-defined]
    elif bases == ["Protocol"]:
        assert getattr(cls, "_is_protocol", False)
        for stmt in node.body:
            if isinstance(stmt, ast.FunctionDef):
                method = getattr(cls, stmt.name)
                signature = inspect.signature(method)
                assert list(signature.parameters) == [a.arg for a in stmt.args.args]
                assert normal(str(signature.return_annotation)) == normal(
                    ast.unparse(stmt.returns)
                )
                for arg in stmt.args.args[1:]:
                    assert normal(
                        str(signature.parameters[arg.arg].annotation)
                    ) == normal(ast.unparse(arg.annotation))
    else:  # pragma: no cover - a new kind of block in the contract must get its own check
        pytest.fail(f"unhandled contract class {name}")


def test_normalise_and_rank_alerts_match_the_contract_function_text() -> None:
    text = INTERFACES.read_text(encoding="utf-8")
    block = text.split("\n## Template\n", 1)[1].split("\n## ", 1)[0]
    functions = {
        node.name: node
        for code in re.findall(r"```python\n(.*?)```", block, flags=re.DOTALL)
        for node in ast.parse(code).body
        if isinstance(node, ast.FunctionDef)
    }
    assert set(functions) == {"normalise", "rank_alerts"}
    norm = inspect.signature(normalise)
    assert [(p.name, normal(str(p.annotation))) for p in norm.parameters.values()] == [
        ("sigma_raw", "float"),
        ("scale", "float"),
    ]
    assert normal(str(norm.return_annotation)) == "float"
    # rank_alerts: the contract types the argument with Alert; ADR-024 types it structurally, so the
    # annotation differs by design (TypeVar bound to a Protocol), the name and the arity do not.
    contract_args = [a.arg for a in functions["rank_alerts"].args.args]
    assert (
        list(inspect.signature(rank_alerts).parameters) == contract_args == ["alerts"]
    )


def test_typing_hints_of_the_dataclasses_resolve() -> None:
    """Each annotation string names things that exist in the module that defines the class."""
    for cls in (Template, TemplateInstance, CarePlan, RegistryEntry, PhysioBounds, Rho):
        hints = typing.get_type_hints(cls)
        assert set(hints) == set(field_names(cls))
