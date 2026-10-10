"""Fidelity of ``ralmon.monitor`` to the contracts #verdict and #monitor (WS05-T04, step 3 and step 8).

``02-interfaces.md`` is not edited by this task: the optional fields of ``VerdictRecord`` and the
keyword-only arguments of ``run_offline`` are ahead of the contract until ADR-048 and ADR-047 are
accepted. The prefix of the record must equal the contract text field by field; the extras are
trailing and defaulted so that code that builds a record with the contract fields keeps working.
"""

from __future__ import annotations

import dataclasses
import inspect
import re
from typing import Any

import pytest

import ralmon.monitor as m
import ralmon.spec as s

from .helpers import INTERFACES, SRC_MONITOR

CONTRACT = INTERFACES.read_text(encoding="utf-8")
EXTRA_FIELDS = (
    "undecidable",
    "guard_failed",
    "subformula_path",
    "predicted_sigma_norm",
)


def class_block(header: str) -> list[str]:
    """The indented lines of the contract block that starts with ``header``."""
    lines = CONTRACT.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(header))
    block: list[str] = []
    for line in lines[start + 1 :]:
        if line.strip() and not line.startswith(" "):
            break
        block.append(line)
    return block


def fields_of(header: str) -> list[tuple[str, str]]:
    out = []
    for line in class_block(header):
        match = re.match(r"^    (\w+): ([^#]+?)\s*(?:#.*)?$", line)
        if match and "def " not in line:
            out.append((match.group(1), match.group(2).strip()))
    return out


def norm_type(text: str) -> str:
    """The type text with one space between tokens and double quotes (Python 3.14 unparses with single)."""
    return re.sub(r"\s+", " ", text.strip()).replace("'", '"')


def test_verdict_record_prefix_equals_the_contract_text_field_by_field() -> None:
    contract = fields_of("class VerdictRecord")
    assert [n for n, _ in contract] == [
        "instance_key",
        "template",
        "t_eval_ms",
        "state",
        "sigma_interval",
        "sigma_norm_interval",
        "rho",
        "decided_at_ms",
        "pending_until_ms",
    ]
    fields = dataclasses.fields(m.VerdictRecord)
    for (name, type_text), field in zip(contract, fields, strict=False):
        assert field.name == name
        assert norm_type(str(field.type)) == norm_type(type_text), name
        assert (
            field.default is dataclasses.MISSING
            and field.default_factory is dataclasses.MISSING
        ), name


def test_the_extra_fields_are_trailing_and_defaulted_to_none() -> None:
    fields = dataclasses.fields(m.VerdictRecord)
    assert len(fields) == 9 + len(EXTRA_FIELDS)
    extras = fields[9:]
    assert tuple(f.name for f in extras) == EXTRA_FIELDS
    assert all(f.default is None for f in extras)
    types = {f.name: norm_type(str(f.type)) for f in extras}
    assert types == {
        "undecidable": "str | None",
        "guard_failed": "str | None",
        "subformula_path": "str | None",
        "predicted_sigma_norm": "float | None",
    }


def test_a_record_built_with_the_contract_fields_keeps_working() -> None:
    rec = m.VerdictRecord(
        "range@0",
        s.TemplateId.RANGE,
        0,
        m.VerdictState.PENDING,
        m.RobustnessInterval(-1.0, 1.0),
        (-0.05, 0.05),
        None,
        None,
        0,
    )
    assert (
        rec.undecidable,
        rec.guard_failed,
        rec.subformula_path,
        rec.predicted_sigma_norm,
    ) == (None,) * 4
    with pytest.raises(dataclasses.FrozenInstanceError):
        rec.state = m.VerdictState.VIOLATED  # type: ignore[misc]
    assert hasattr(m.VerdictRecord, "__slots__")
    assert rec == dataclasses.replace(rec)
    assert hash(rec) == hash(dataclasses.replace(rec))


def test_robustness_interval_and_state_follow_the_contract_text() -> None:
    assert [n for n, _ in fields_of("class RobustnessInterval")] == ["lo", "hi"]
    assert [f.name for f in dataclasses.fields(m.RobustnessInterval)] == ["lo", "hi"]
    members = re.findall(
        r"^    (\w+) = \"(\w+)\"",
        "\n".join(class_block("class VerdictState")),
        re.MULTILINE,
    )
    assert members == [(x.name, x.value) for x in m.VerdictState]
    assert [x.name for x in m.VerdictState] == [
        "PENDING",
        "PREDICTED_VIOLATION",
        "VIOLATED",
        "SATISFIED",
    ]
    assert issubclass(m.VerdictState, str)


def test_monitor_config_has_the_contract_fields() -> None:
    contract = fields_of("class MonitorConfig")
    assert [n for n, _ in contract] == [
        f.name for f in dataclasses.fields(m.MonitorConfig)
    ]
    for (name, type_text), field in zip(
        contract, dataclasses.fields(m.MonitorConfig), strict=True
    ):
        assert norm_type(str(field.type)) == norm_type(type_text), name


def test_monitor_protocol_and_streaming_monitor_signatures() -> None:
    for cls in (m.Monitor, m.StreamingMonitor):
        for name, params in (
            ("load", ["plan"]),
            ("push_sample", ["sample"]),
            ("push_event", ["event"]),
            ("advance", ["t_ms"]),
            ("verdict_latency_bound_ms", ["template"]),
        ):
            sig = inspect.signature(getattr(cls, name))
            assert list(sig.parameters)[1:] == params, (cls.__name__, name)
    init = inspect.signature(m.StreamingMonitor.__init__)
    names = list(init.parameters)
    assert names[1:4] == ["config", "registry", "templates"]
    kwonly = [
        p.name
        for p in init.parameters.values()
        if p.kind is inspect.Parameter.KEYWORD_ONLY
    ]
    assert kwonly[:4] == ["calibrator", "forecaster", "verifier", "template_ids"]


def test_forecast_and_forecaster_follow_the_contract() -> None:
    contract = fields_of("class Forecast")
    assert [n for n, _ in contract] == [f.name for f in dataclasses.fields(m.Forecast)]
    fc = m.Forecast("hr_ecg", 0, 60_000, (1.0, 2.0))
    assert fc.signal == "hr_ecg" and fc.horizon_ms == 60_000
    for method in ("fit", "predict"):
        assert callable(getattr(m.Forecaster, method))
    assert list(inspect.signature(m.Forecaster.predict).parameters)[1:] == [
        "history",
        "t_ms",
        "horizon_ms",
    ]
    assert list(inspect.signature(m.Forecaster.fit).parameters)[1:] == ["train_days"]


def test_done_when_names_and_stub_owners() -> None:
    names = [
        "Monitor",
        "MonitorConfig",
        "VerdictRecord",
        "VerdictState",
        "RobustnessInterval",
        "Rho",
        "RhoKind",
        "run_offline",
        "StreamingMonitor",
        "Forecast",
        "Forecaster",
        "PointEvaluator",
        "make_point_evaluator",
        "MonitorConfigError",
        "PlanVersionError",
    ]
    for name in names:
        assert not hasattr(getattr(m, name), "__ralmon_stub_owner__"), name
    # WS05-T08 moved the last two placeholders: no name of ralmon.monitor is a placeholder any more
    stubs = sorted(
        n for n in m.__all__ if hasattr(getattr(m, n), "__ralmon_stub_owner__")
    )
    assert stubs == []


def test_rho_is_the_single_definition_of_spec() -> None:
    assert m.Rho is s.Rho and m.RhoKind is s.RhoKind


def test_public_all_is_the_contract_row_and_nothing_more() -> None:
    row = next(
        line for line in CONTRACT.splitlines() if line.startswith("| `ralmon.monitor`")
    )
    assert set(re.findall(r"`(\w+)`", row.split("|")[2])) == set(m.__all__)


def test_the_names_of_adr_053_are_in_the_package_root_and_in_all() -> None:
    # ADR-053 (d), accepted 2026-10-09: the named errors and the report types joined the contract table
    for name in (
        "MonitorInputError",
        "PlanFeasibilityError",
        "MonitorInvariantError",
        "MonitorStats",
    ):
        assert hasattr(m, name), name
        assert name in m.__all__, name


def test_error_classes_are_distinct_named_exceptions() -> None:
    assert issubclass(m.MonitorConfigError, Exception) and issubclass(
        m.PlanVersionError, Exception
    )
    assert issubclass(m.PlanFeasibilityError, m.MonitorConfigError)
    for cls in (m.MonitorInputError, m.MonitorInvariantError):
        assert issubclass(cls, Exception)
        assert not issubclass(cls, m.MonitorConfigError)
    assert not issubclass(m.PlanVersionError, m.MonitorConfigError)


def test_no_module_of_the_monitor_raises_the_unfinished_work_error() -> None:
    # the placeholder helper of ralmon is the only place allowed to name it (tests/test_public_api.py)
    for path in SRC_MONITOR.rglob("*.py"):
        assert "NotImplementedError" not in path.read_text(encoding="utf-8"), path.name


def test_python_floor_3_10_no_newer_syntax_or_modules() -> None:
    """ADR-042: no tomllib, typing.Self, datetime.UTC, StrEnum, PEP 695 or ExceptionGroup in the monitor."""
    import ast

    banned_names = {
        "StrEnum",
        "ExceptionGroup",
        "BaseExceptionGroup",
        "tomllib",
        "Self",
    }
    for path in SRC_MONITOR.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in banned_names:
                pytest.fail(f"{path.name}: {node.id}")
            if isinstance(node, ast.ImportFrom) and node.module in {"tomllib", "enum"}:
                assert all(a.name != "StrEnum" for a in node.names), path.name
            if isinstance(node, ast.ImportFrom) and node.module == "typing":
                assert all(a.name != "Self" for a in node.names), path.name
            if isinstance(node, ast.Attribute) and node.attr == "UTC":
                pytest.fail(f"{path.name}: datetime.UTC")
            # PEP 695: `type X = ...` and `def f[T](...)`
            assert not isinstance(node, getattr(ast, "TypeAlias", ())), (
                f"{path.name}: type statement"
            )
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                assert not getattr(node, "type_params", None), (
                    f"{path.name}: PEP 695 type parameters"
                )


def test_docstrings_name_the_ahead_of_contract_additions() -> None:
    doc: Any = m.VerdictRecord.__doc__ or ""
    assert "ADR-048" in doc  # the extras are ahead of the contract until it is accepted
    # the keyword-only arguments are in the contract since ADR-053 and ADR-046 (WS05-T10)
    assert "ADR-053" in (m.run_offline.__doc__ or "")
    assert "ADR-046" in (m.run_offline.__doc__ or "")
