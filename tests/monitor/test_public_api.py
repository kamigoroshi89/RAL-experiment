"""The boundary of ``ralmon.monitor``: named errors only, the formula helpers, the detailed offline run
(WS05-T04, review round 1, B2, M7 and M8).

ADR-053 (d): every public entry point raises only ``MonitorConfigError`` (and its subclass
``PlanFeasibilityError``), ``MonitorInputError``, ``MonitorInvariantError``, ``PlanVersionError`` and
``PlanIntegrityError``, whatever the arguments are, hostile objects included. The entry points are the
names the package root exports and the boundary functions of ``formula``, ``parameters``, ``config``,
``evaluator`` and ``offline``. The numeric kernels of ``reorder``, ``measured_rho``, ``instances`` and
``_text`` are not entry points: the monitor calls them with values it has already validated.
"""

from __future__ import annotations

import importlib
import inspect
import math
import pkgutil
import random
from typing import Any

import pytest

import ralmon.monitor as m
from ralmon.spec import PlanIntegrityError, TemplateId, TemplateInstance

from .helpers import (
    STEP,
    Inputs,
    LocalDay,
    evt,
    hhmm,
    load_f0,
    load_lib,
    make_config,
    make_monitor,
    make_plan,
    smp,
)
from .test_inputs import Hostile, HostileStr

REG = load_f0()
LIB = load_lib(REG)
BY_ID = {t.id: t for t in LIB}

NAMED = (
    m.MonitorConfigError,
    m.MonitorInputError,
    m.MonitorInvariantError,
    m.PlanVersionError,
    PlanIntegrityError,
)

BOUNDARY_MODULES = {
    "ralmon.monitor.config",
    "ralmon.monitor.evaluator",
    "ralmon.monitor.formula",
    "ralmon.monitor.offline",
    "ralmon.monitor.parameters",
}
INTERNAL_MODULES = {  # numeric kernels and plumbing, called with validated values
    "ralmon.monitor._stubs",
    "ralmon.monitor._text",
    "ralmon.monitor.core",  # StreamingMonitor: fuzzed by test_inputs.py
    "ralmon.monitor.forecast",
    "ralmon.monitor.forecasters",  # WS05-T05: its classes are exercised by test_forecasters.py
    "ralmon.monitor.instances",
    "ralmon.monitor.measured_rho",
    "ralmon.monitor.reorder",
    "ralmon.monitor.verdict",
}


def test_every_module_is_classified_as_boundary_or_internal() -> None:
    names = {f"ralmon.monitor.{info.name}" for info in pkgutil.iter_modules(m.__path__)}
    assert names == BOUNDARY_MODULES | INTERNAL_MODULES


def pool() -> list[Any]:
    instance = TemplateInstance(TemplateId.SCHED, "sched@0", {}, 0)
    return [
        None,
        0,
        5,
        -1,
        True,
        1.5,
        math.nan,
        math.inf,
        10**30,
        "",
        "sched",
        "x" * 20_000,
        "int/0/1",
        "int/0;int/1",
        b"bytes",
        [],
        [1, 2],
        {},
        {"a": 1},
        (),
        (1,),
        object(),
        Hostile(),
        HostileStr("h"),
        REG,
        LIB,
        LIB[0],
        list(LIB),
        instance,
        make_config(REG),
        make_plan(REG),
        TemplateId.INT,
        STEP,
    ]


def swept_functions() -> list[tuple[str, Any]]:
    """Every function in an ``__all__``, every public function defined in a module of the package, and
    every function reachable from the package root (the stubs of WS05-T08 excepted: they raise
    ``NotImplementedError`` by design)."""
    found: dict[int, tuple[str, Any]] = {}
    for name in sorted(BOUNDARY_MODULES | INTERNAL_MODULES):
        if name.rsplit(".", 1)[1].startswith("_"):
            continue  # private modules: helpers that take the error class to raise as an argument
        mod = importlib.import_module(name)
        for fname, obj in inspect.getmembers(mod, inspect.isfunction):
            public = fname in getattr(mod, "__all__", ()) or not fname.startswith("_")
            if public and obj.__module__ == name:
                found[id(obj)] = (f"{name}.{fname}", obj)
    for fname, obj in inspect.getmembers(m, inspect.isfunction):
        if not hasattr(obj, "__ralmon_stub_owner__"):
            found.setdefault(id(obj), (f"ralmon.monitor.{fname}", obj))
    return sorted(found.values(), key=lambda item: item[0])


def fuzz_calls(fn: Any) -> list[tuple[Any, ...]]:
    values = pool()
    rng = random.Random(20261010)
    arity = len(
        [
            p
            for p in inspect.signature(fn).parameters.values()
            if p.default is p.empty
            and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
        ]
    )
    calls: list[tuple[Any, ...]] = []
    for position in range(arity):  # one hostile argument, the others from the pool
        for value in values:
            args = [rng.choice(values) for _ in range(arity)]
            args[position] = value
            calls.append(tuple(args))
    calls += [tuple(rng.choice(values) for _ in range(arity)) for _ in range(1500)]
    return calls


def assert_only_named_errors(name: str, fn: Any, calls: list[tuple[Any, ...]]) -> None:
    for args in calls:
        try:
            fn(*args)
        except NAMED:
            pass
        except BaseException as exc:  # noqa: BLE001 - this is the point of the test
            pytest.fail(
                f"{name}{tuple(type(a).__name__ for a in args)}: {type(exc).__name__}: {exc}"
            )


def test_the_sweep_finds_the_known_boundary_functions() -> None:
    names = {name for name, _ in swept_functions()}
    for expected in (
        "ralmon.monitor.config.check_config",
        "ralmon.monitor.formula.render",
        "ralmon.monitor.formula.resolve_subformula_paths",
        "ralmon.monitor.parameters.read_value",
        "ralmon.monitor.reorder.step_of",
        "ralmon.monitor.measured_rho.range_band_rho",
        "ralmon.monitor.instances.format_marker",
        "ralmon.monitor.offline.run_offline_detailed",
        "ralmon.monitor.evaluator.make_point_evaluator",
    ):
        assert expected in names, expected


@pytest.mark.parametrize(
    ("name", "fn"), swept_functions(), ids=[n for n, _ in swept_functions()]
)
def test_a_function_raises_only_named_errors(name: str, fn: Any) -> None:
    assert_only_named_errors(name, fn, fuzz_calls(fn))


def test_the_methods_of_the_classes_raise_only_named_errors() -> None:
    from ralmon.monitor.reorder import BufferedInput, ReorderBuffer

    buffer = ReorderBuffer(100)
    for label, method in (
        ("ReorderBuffer.push", buffer.push),
        ("ReorderBuffer.release", buffer.release),
    ):
        assert_only_named_errors(label, method, fuzz_calls(method))
    assert_only_named_errors("BufferedInput", BufferedInput, fuzz_calls(BufferedInput))


INTERNAL_CLASSES = {  # built by the monitor from validated values; their methods are the per-step path
    "ralmon.monitor.instances.CountEndInstance",
    "ralmon.monitor.instances.CountLimitInstance",
    "ralmon.monitor.instances.EngineContext",
    "ralmon.monitor.instances.HoldInstance",
    "ralmon.monitor.instances.Instance",
    "ralmon.monitor.instances.IntInstance",
    "ralmon.monitor.instances.RangeInstance",
    "ralmon.monitor.instances.RespInstance",
    "ralmon.monitor.instances.SchedInstance",
    "ralmon.monitor.instances.StepView",
    "ralmon.monitor.instances.SysInstance",
    "ralmon.monitor.instances.WitnessTracker",
}
FUZZED_CLASSES = {  # fuzzed here, in test_inputs.py or in test_field_fuzz.py
    "ralmon.monitor.core.StreamingMonitor",
    "ralmon.monitor.core.ChannelAvailability",
    "ralmon.monitor.core.MonitorStats",
    "ralmon.monitor.core.RejectedInput",
    "ralmon.monitor.core.Monitor",
    "ralmon.monitor.evaluator.PointEvaluator",
    "ralmon.monitor.formula.Formula",
    "ralmon.monitor.formula.Node",
    "ralmon.monitor.formula.PathTable",
    "ralmon.monitor.offline.OfflineResult",
    "ralmon.monitor.reorder.BufferedInput",
    "ralmon.monitor.reorder.ReorderBuffer",
    "ralmon.monitor.config.MonitorConfig",
    "ralmon.monitor.forecast.Forecast",
    "ralmon.monitor.forecast.Forecaster",
    "ralmon.monitor.forecasters.AutoRegressiveForecaster",
    "ralmon.monitor.forecasters.DeadlineForecaster",
    "ralmon.monitor.forecasters.PersistenceForecaster",
    "ralmon.monitor.verdict.RobustnessInterval",
    "ralmon.monitor.verdict.VerdictRecord",
    "ralmon.monitor.verdict.VerdictState",
    "ralmon.monitor.verdict.Rho",
    "ralmon.monitor.verdict.RhoKind",
}


def test_every_class_of_an_all_is_classified() -> None:
    classes = set()
    for name in sorted(BOUNDARY_MODULES | INTERNAL_MODULES):
        if name.rsplit(".", 1)[1].startswith("_"):
            continue
        mod = importlib.import_module(name)
        for cname in getattr(mod, "__all__", ()):
            obj = getattr(mod, cname)
            if inspect.isclass(obj) and not issubclass(obj, BaseException):
                classes.add(f"{obj.__module__}.{obj.__name__}")
    # Rho and RhoKind are defined in ralmon.spec and re-exported
    classes -= {"ralmon.spec.verdict.Rho", "ralmon.spec.verdict.RhoKind"}
    unclassified = {c for c in classes if c not in INTERNAL_CLASSES | FUZZED_CLASSES}
    unclassified = {c for c in unclassified if not c.startswith("ralmon.spec.")}
    assert not unclassified, sorted(unclassified)


def test_the_methods_of_the_parsed_formula_raise_only_named_errors() -> None:
    from ralmon.monitor.formula import build_path_table, parse_formula

    formula = parse_formula(BY_ID[TemplateId.INT].formula_past_time)
    table = build_path_table(TemplateId.COUNT)
    for value in pool():
        for call in (
            lambda v=value: formula.node_at(v),
            lambda v=value: formula.find(v),
            lambda v=value: table.path(v),
            lambda v=value: table.path("limit", v),
            lambda v=value: table.path(v, v),
        ):
            try:
                call()
            except NAMED:
                pass
            except BaseException as exc:  # noqa: BLE001
                pytest.fail(f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------------------------
# paths of a violation, as the monitor emits them
# ---------------------------------------------------------------------------------------------


def composite_record() -> Any:
    mon = make_monitor()
    t = 10 * STEP
    mon.push_event(evt("measurement", t))
    mon.push_sample(smp("bp", t, 120.0))
    mon.push_sample(smp("cuff_health", t, 0.0))  # the guard fails
    mon.push_sample(smp("inflation_ms", t, 1_000.0))  # and so does the margin
    return next(r for r in mon.advance(t) if r.instance_key == f"sys@{t}")


def test_the_root_exports_what_the_attribution_layer_needs() -> None:
    # ADR-053 (d), accepted 2026-10-09: these names are in the contract table, so in ``__all__``
    for name in (
        "resolve_subformula_path",
        "resolve_subformula_paths",
        "run_offline_detailed",
        "OfflineResult",
    ):
        assert hasattr(m, name), name
        assert name in m.__all__, name


def test_a_composite_path_is_split_at_the_semicolons_and_resolves_part_by_part() -> (
    None
):
    rec = composite_record()
    assert rec.state.value == "violated"
    assert rec.subformula_path is not None and ";" in rec.subformula_path
    template = BY_ID[TemplateId.SYS]
    texts = m.resolve_subformula_paths(template, rec.subformula_path)
    assert len(texts) == 2 and texts[0] != texts[1]
    parts = rec.subformula_path.split(";")
    assert texts == tuple(m.resolve_subformula_path(template, p) for p in parts)
    # the decisive part comes first, and the single form answers with it
    assert m.resolve_subformula_path(template, rec.subformula_path) == texts[0]


@pytest.mark.parametrize(
    ("path", "fragment"),
    [
        ("sys/0;", "empty part"),
        (";sys/0", "empty part"),
        ("sys/0;;sys/1", "empty part"),
        (";", "empty part"),
        ("sys/0;int/0", "does not start with the template id"),
    ],
)
def test_a_composite_path_with_an_empty_or_foreign_part_is_a_named_error(
    path: str, fragment: str
) -> None:
    with pytest.raises(m.MonitorInputError, match=fragment):
        m.resolve_subformula_paths(BY_ID[TemplateId.SYS], path)


def test_a_template_whose_attributes_raise_is_a_named_error() -> None:
    import dataclasses

    hostile = dataclasses.replace(BY_ID[TemplateId.SYS], id=Hostile())  # type: ignore[arg-type]
    for fn in (m.resolve_subformula_path, m.resolve_subformula_paths):
        with pytest.raises(m.MonitorInputError, match="unusable argument"):
            fn(hostile, "sys/0")


class _DayWhoseSamplesRaise:
    """Satisfies the ObservedTrace protocol by name, and raises when its data is read."""

    patient_id = "p-1"
    day_index = 0
    seed = 0
    care_plan_id = "plan-1"

    @property
    def samples(self) -> Any:
        raise RuntimeError("hostile samples")

    @property
    def events(self) -> Any:
        raise RuntimeError("hostile events")


@pytest.mark.parametrize("entry", [m.run_offline, m.run_offline_detailed])
@pytest.mark.parametrize(
    "day", [Hostile(), _DayWhoseSamplesRaise()], ids=["hostile", "raising"]
)
def test_a_day_whose_attributes_raise_is_a_named_error(entry: Any, day: Any) -> None:
    with pytest.raises(m.MonitorInputError):
        entry(
            day,
            make_plan(REG),
            make_config(REG),
            None,
            None,
            registry=REG,
            templates=LIB,
        )


@pytest.mark.parametrize(
    "template",
    [None, 5, "sys", object(), Hostile(), TemplateId.SYS],
    ids=["none", "int", "str", "object", "hostile", "template-id"],
)
def test_a_path_resolved_against_something_that_is_not_a_template_is_a_named_error(
    template: Any,
) -> None:
    with pytest.raises(m.MonitorInputError, match="template"):
        m.resolve_subformula_path(template, "sys/0")
    with pytest.raises(m.MonitorInputError, match="template"):
        m.resolve_subformula_paths(template, "sys/0")


# ---------------------------------------------------------------------------------------------
# the detailed offline run: records and the diagnostics that run_offline cannot return
# ---------------------------------------------------------------------------------------------


def day_with_a_late_sample() -> LocalDay:
    inputs = Inputs()
    inputs.events.append(evt("measurement", hhmm(6, 0), source="cuff"))
    inputs.samples.append(smp("bp", hhmm(6, 0), 150.0, seq=7))
    inputs.samples.append(smp("bp", hhmm(6, 0), 150.0, seq=7))  # the same input twice
    inputs.samples.append(smp("bp", hhmm(6, 10), 130.0, rx=hhmm(6, 10) + 5 * STEP))
    return LocalDay(inputs.samples, inputs.events)


def run_kwargs() -> dict[str, Any]:
    return {"registry": REG, "templates": LIB}


def test_run_offline_detailed_returns_the_records_of_run_offline_and_the_diagnostics() -> (
    None
):
    cfg = make_config(REG, d_ms=STEP)
    day = day_with_a_late_sample()
    plan = make_plan(REG)
    plain = m.run_offline(day, plan, cfg, None, None, **run_kwargs())
    detailed = m.run_offline_detailed(day, plan, cfg, None, None, **run_kwargs())
    assert detailed.records == tuple(plain)
    assert [r.reason for r in detailed.late_inputs] == ["late"]
    assert sorted(r.reason for r in detailed.rejected_inputs) == ["duplicate", "late"]
    assert detailed.stats.late_count == 1 and detailed.stats.duplicate_count == 1
    assert detailed.stats.steps_finalised == 1441
    assert detailed.stats.records_emitted == len(detailed.records)


def test_run_offline_detailed_raises_the_named_errors_of_run_offline() -> None:
    cfg = make_config(REG)
    with pytest.raises(m.MonitorInputError, match="observed day"):
        m.run_offline_detailed(
            object(), make_plan(REG), cfg, None, None, **run_kwargs()
        )  # type: ignore[arg-type]


# ---------------------------------------------------------------------------------------------
# what run_offline types, and what the monitor does with a calibrator and a forecaster
# ---------------------------------------------------------------------------------------------


def test_the_annotations_of_the_offline_run_follow_the_contract() -> None:
    hints = {
        name: str(p.annotation).replace("'", "")
        for name, p in inspect.signature(m.run_offline).parameters.items()
    }
    # the layering rule (signals and spec only) keeps ConformalCalibrator out of this package: disclosed
    assert hints["calibrator"] == "object | None"
    assert "Forecaster" in hints["forecaster"]
    assert "ObservedTrace" in hints["day"]


def test_a_calibrator_and_a_forecaster_are_accepted_and_never_called() -> None:
    """WS05-T08 gives them a role; until then the measured half ignores whatever is passed."""

    class Spy:
        calls = 0

        def __getattr__(self, name: str) -> Any:
            Spy.calls += 1
            raise AssertionError(name)

    spy = Spy()
    mon = m.StreamingMonitor(make_config(REG), REG, LIB, calibrator=spy, forecaster=spy)  # type: ignore[arg-type]
    mon.load(make_plan(REG))
    mon.push_event(evt("measurement", STEP))
    mon.advance(STEP)
    assert Spy.calls == 0
