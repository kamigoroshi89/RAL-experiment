"""Field-level hostile values through every entry point of ``ralmon.monitor`` (WS05-T04, fix round 2).

The fuzz of ``test_public_api.py`` swaps whole arguments. This one keeps the argument well-formed and
replaces ONE field of it with a hostile value: of ``MonitorConfig`` (and of a subclass whose properties
raise), ``Sample``, ``Event``, ``CarePlan``, ``TemplateInstance``, ``Template``, an observed day and its
items, and of a registry object (what each of its methods returns, or raises). ADR-053 (d): the only
exceptions that may escape an entry point are ``MonitorConfigError`` (and ``PlanFeasibilityError``),
``MonitorInputError``, ``MonitorInvariantError``, ``PlanVersionError`` and ``PlanIntegrityError``.

A frozen dataclass is tampered with ``object.__setattr__`` so that no validation of the constructor
stands in the way; that is what a caller with a hand-made or deserialised object can do.
"""

from __future__ import annotations

import copy
import dataclasses
import math
from collections.abc import Callable, Mapping
from typing import Any

import ralmon.monitor as m
from ralmon.monitor.formula import (
    build_path_table,
    check_library_formulas,
    parse_formula,
    render,
    resolve_subformula_paths,
)
from ralmon.monitor.parameters import (
    check_registry,
    optional_value,
    read_bounds,
    read_latency,
    read_overrides,
    read_value,
)
from ralmon.signals import Event, EventKind, Sample
from ralmon.spec import (
    CarePlan,
    PlanIntegrityError,
    Template,
    TemplateId,
    TemplateInstance,
)

from .helpers import (
    STEP,
    LocalDay,
    evt,
    hhmm,
    load_f0,
    load_lib,
    make_config,
    make_plan,
    smp,
)
from .test_inputs import Hostile, HostileFloat, HostileInt, HostileKey, HostileStr

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


class CmpFloat(float):
    """A float whose ordering raises: ``alpha`` goes through ``0 < alpha < 1``."""

    def __lt__(self, other: object) -> bool:
        raise RuntimeError("hostile __lt__")

    __gt__ = __le__ = __ge__ = __lt__  # type: ignore[assignment]


class EqStr(str):
    """A str whose equality raises: ``variant`` is compared with 'likely' and 'possible'."""

    def __eq__(self, other: object) -> bool:
        raise RuntimeError("hostile __eq__")

    __hash__ = str.__hash__


class RaisingMapping(Mapping):  # type: ignore[type-arg]
    def __getitem__(self, key: Any) -> Any:
        raise RuntimeError("hostile __getitem__")

    def __iter__(self) -> Any:
        raise RuntimeError("hostile __iter__")

    def __len__(self) -> int:
        raise RuntimeError("hostile __len__")


class RaisingSequence:
    def __iter__(self) -> Any:
        raise RuntimeError("hostile __iter__")

    def __len__(self) -> int:
        raise RuntimeError("hostile __len__")

    def __getitem__(self, i: Any) -> Any:
        raise RuntimeError("hostile __getitem__")


def pool() -> list[Any]:
    return [
        None,
        True,
        False,
        0,
        -1,
        1,
        2**53 + 1,
        10**400,
        -(10**400),
        1.5,
        0.5,
        math.nan,
        math.inf,
        -math.inf,
        1e300,
        1j,
        "",
        "likely",
        "x" * 100_000,
        b"likely",
        [],
        [1],
        [Hostile()],
        {},
        {"a": Hostile()},
        {HostileKey("k"): 1.0},
        (),
        object(),
        Hostile(),
        HostileStr("s"),
        HostileInt(7),
        HostileFloat(0.5),
        CmpFloat(0.5),
        EqStr("likely"),
        RaisingMapping(),
        RaisingSequence(),
        EventKind.DISPENSE,
        TemplateId.RANGE,
        REG,
        LIB,
    ]


def tampered(obj: Any, name: str, value: Any) -> Any:
    clone = copy.copy(obj)
    object.__setattr__(clone, name, value)
    return clone


class Leaks:
    def __init__(self) -> None:
        self.found: list[str] = []
        self.calls = 0

    def run(
        self, label: str, fn: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> None:
        self.calls += 1
        try:
            fn(*args, **kwargs)
        except NAMED:
            pass
        except BaseException as exc:  # noqa: BLE001 - this is the point of the test
            self.found.append(f"{label}: {type(exc).__name__}: {str(exc)[:80]}")

    def check(self) -> None:
        assert not self.found, (
            f"{len(self.found)} of {self.calls} calls leaked:\n"
            + "\n".join(sorted(set(self.found))[:25])
        )


GOOD_DAY = LocalDay([smp("bp", STEP, 120.0)], [evt("measurement", STEP)])


def run_all_config_entry_points(leaks: Leaks, label: str, cfg: Any) -> None:
    from ralmon.monitor.config import check_config

    leaks.run(f"check_config[{label}]", check_config, cfg)
    leaks.run(f"StreamingMonitor[{label}]", m.StreamingMonitor, cfg, REG, LIB)
    leaks.run(
        f"run_offline[{label}]",
        m.run_offline,
        GOOD_DAY,
        make_plan(REG),
        cfg,
        None,
        None,
        registry=REG,
        templates=LIB,
    )


def test_a_hostile_field_of_the_config_raises_only_named_errors() -> None:
    leaks = Leaks()
    good = make_config(REG)
    for f in dataclasses.fields(m.MonitorConfig):
        for value in pool():
            run_all_config_entry_points(leaks, f.name, tampered(good, f.name, value))
    # the three values the review found
    run_all_config_entry_points(
        leaks, "alpha=10**400", tampered(good, "alpha", 10**400)
    )
    run_all_config_entry_points(
        leaks, "alpha=CmpFloat", tampered(good, "alpha", CmpFloat(0.5))
    )
    run_all_config_entry_points(
        leaks, "variant=EqStr", tampered(good, "variant", EqStr("likely"))
    )
    leaks.check()


def test_a_config_subclass_whose_properties_raise_or_are_missing_raises_only_named_errors() -> (
    None
):
    leaks = Leaks()
    names = [f.name for f in dataclasses.fields(m.MonitorConfig)]

    def boom(self: Any) -> Any:
        raise RuntimeError("hostile property")

    for name in names:
        evil = type("EvilConfig", (m.MonitorConfig,), {name: property(boom)})
        run_all_config_entry_points(leaks, f"property {name}", object.__new__(evil))
    # an instance whose slots were never set
    run_all_config_entry_points(leaks, "unset slots", object.__new__(m.MonitorConfig))
    leaks.check()


def test_a_hostile_field_of_a_sample_or_an_event_raises_only_named_errors() -> None:
    leaks = Leaks()
    mon = m.StreamingMonitor(make_config(REG), REG, LIB)
    mon.load(make_plan(REG))
    for f in dataclasses.fields(Sample):
        for value in pool():
            leaks.run(
                f"push_sample[{f.name}]",
                mon.push_sample,
                tampered(smp("bp", STEP, 120.0), f.name, value),
            )
    for f in dataclasses.fields(Event):
        for value in pool():
            leaks.run(
                f"push_event[{f.name}]",
                mon.push_event,
                tampered(evt("measurement", STEP), f.name, value),
            )
    for value in pool():
        leaks.run("push_availability[signal]", mon.push_availability, value, True, 0, 0)
        leaks.run(
            "push_availability[available]",
            mon.push_availability,
            "presence",
            value,
            0,
            0,
        )
        leaks.run(
            "push_availability[t_device_ms]",
            mon.push_availability,
            "presence",
            True,
            value,
            0,
        )
        leaks.run(
            "push_availability[t_rx_ms]",
            mon.push_availability,
            "presence",
            True,
            0,
            value,
        )
        leaks.run("advance", mon.advance, value)
        leaks.run("verdict_latency_bound_ms", mon.verdict_latency_bound_ms, value)
    leaks.check()


def a_plan() -> CarePlan:
    instance = TemplateInstance(
        TemplateId.SCHED, "sched@3600000", {"sched_window": 1_800_000.0}, hhmm(1, 0)
    )
    return make_plan(REG, records=[instance], sched=[hhmm(2, 0)])


def test_a_hostile_field_of_a_plan_or_an_instance_raises_only_named_errors() -> None:
    leaks = Leaks()
    mon = m.StreamingMonitor(make_config(REG), REG, LIB)
    plan = a_plan()
    for f in dataclasses.fields(CarePlan):
        for value in pool():
            leaks.run(f"load[{f.name}]", mon.load, tampered(plan, f.name, value))
    instance = plan.instances[0]
    for f in dataclasses.fields(TemplateInstance):
        for value in pool():
            bad = tampered(instance, f.name, value)
            leaks.run(
                f"load[instance.{f.name}]",
                mon.load,
                tampered(plan, "instances", (bad,)),
            )
            leaks.run(
                f"make_point_evaluator[instance.{f.name}]",
                m.make_point_evaluator,
                BY_ID[TemplateId.SCHED],
                bad,
                REG,
                STEP,
            )
    leaks.check()


def test_a_hostile_field_of_a_template_raises_only_named_errors() -> None:
    leaks = Leaks()
    instance = TemplateInstance(TemplateId.RANGE, "range@0", {}, 0)
    for f in dataclasses.fields(Template):
        for value in pool():
            bad = tampered(BY_ID[TemplateId.RANGE], f.name, value)
            library = [bad if t.id is TemplateId.RANGE else t for t in LIB]
            leaks.run(
                f"StreamingMonitor[template.{f.name}]",
                m.StreamingMonitor,
                make_config(REG),
                REG,
                library,
            )
            leaks.run(
                f"make_point_evaluator[template.{f.name}]",
                m.make_point_evaluator,
                bad,
                instance,
                REG,
                STEP,
            )
            leaks.run(
                f"resolve_subformula_paths[template.{f.name}]",
                resolve_subformula_paths,
                bad,
                "range/0;range/0",
            )
            leaks.run(
                f"check_library_formulas[template.{f.name}]",
                check_library_formulas,
                [bad],
            )
            leaks.run(f"read_latency[template.{f.name}]", read_latency, REG, bad)
    for value in pool():
        leaks.run("build_path_table", build_path_table, value)
        leaks.run("parse_formula", parse_formula, value)
        leaks.run("render", render, value)
    leaks.check()


def test_a_hostile_field_of_a_day_or_of_its_items_raises_only_named_errors() -> None:
    leaks = Leaks()
    plan = make_plan(REG)
    cfg = make_config(REG)

    def run_day(label: str, day: Any) -> None:
        for fn in (m.run_offline, m.run_offline_detailed):
            leaks.run(
                f"{fn.__name__}[{label}]",
                fn,
                day,
                plan,
                cfg,
                None,
                None,
                registry=REG,
                templates=LIB,
            )

    for f in dataclasses.fields(LocalDay):
        for value in pool():
            run_day(f"day.{f.name}", tampered(GOOD_DAY, f.name, value))
    for f in dataclasses.fields(Sample):
        for value in pool():
            bad = tampered(smp("bp", STEP, 120.0), f.name, value)
            run_day(f"day.sample.{f.name}", LocalDay([bad], []))
    for f in dataclasses.fields(Event):
        for value in pool():
            bad = tampered(evt("measurement", STEP), f.name, value)
            run_day(f"day.event.{f.name}", LocalDay([], [bad]))
    for value in pool():
        run_day("day.samples=[v]", LocalDay([value], []))
        run_day("day.events=[v]", LocalDay([], [value]))
        for fn in (m.run_offline, m.run_offline_detailed):
            leaks.run(
                f"{fn.__name__}[plan]",
                fn,
                GOOD_DAY,
                value,
                cfg,
                None,
                None,
                registry=REG,
                templates=LIB,
            )
            leaks.run(
                f"{fn.__name__}[registry]",
                fn,
                GOOD_DAY,
                plan,
                cfg,
                None,
                None,
                registry=value,
                templates=LIB,
            )
            leaks.run(
                f"{fn.__name__}[templates]",
                fn,
                GOOD_DAY,
                plan,
                cfg,
                None,
                None,
                registry=REG,
                templates=value,
            )
            leaks.run(
                f"{fn.__name__}[verifier]",
                fn,
                GOOD_DAY,
                plan,
                cfg,
                None,
                None,
                registry=REG,
                templates=LIB,
                verifier=value,
            )
    leaks.check()


class HostileRegistry:
    """The F0 registry with one method replaced: it raises, or it returns ``value``."""

    def __init__(self, replaced: str, value: Any, raises: bool) -> None:
        self._replaced = replaced
        self._value = value
        self._raises = raises
        self.step_ms = value if replaced == "step_ms" else REG.step_ms

    def _answer(self, name: str, real: Callable[[], Any]) -> Any:
        if name == self._replaced:
            if self._raises:
                raise RuntimeError(f"hostile {name}")
            return self._value
        return real()

    def get(self, name: str) -> Any:
        return self._answer("get", lambda: REG.get(name))

    def bounds(self, signal: str) -> Any:
        return self._answer("bounds", lambda: REG.bounds(signal))

    def version(self) -> str:
        return self._answer("version", REG.version)

    def overrides(self) -> Any:
        return self._answer("overrides", REG.overrides)


class HostileEntry:
    """What ``get`` returns: a registry entry whose ``value`` is hostile."""

    def __init__(self, value: Any) -> None:
        self.value = value


def test_a_hostile_registry_raises_only_named_errors() -> None:
    leaks = Leaks()
    cfg = make_config(REG)
    instance = TemplateInstance(TemplateId.RANGE, "range@0", {}, 0)
    registries: list[tuple[str, Any]] = []
    for replaced in ("get", "bounds", "version", "overrides", "step_ms"):
        registries.append((f"{replaced} raises", HostileRegistry(replaced, None, True)))
        for value in pool():
            registries.append(
                (f"{replaced} returns", HostileRegistry(replaced, value, False))
            )
    for value in pool():
        registries.append(
            ("get returns an entry", HostileRegistry("get", HostileEntry(value), False))
        )
    for label, reg in registries:
        leaks.run(f"StreamingMonitor[{label}]", m.StreamingMonitor, cfg, reg, LIB)
        leaks.run(
            f"make_point_evaluator[{label}]",
            m.make_point_evaluator,
            BY_ID[TemplateId.RANGE],
            instance,
            reg,
            STEP,
        )
        leaks.run(
            f"run_offline[{label}]",
            m.run_offline,
            GOOD_DAY,
            make_plan(REG),
            cfg,
            None,
            None,
            registry=reg,
            templates=LIB,
        )
        leaks.run(f"check_registry[{label}]", check_registry, reg)
        leaks.run(f"read_value[{label}]", read_value, reg, "bp_band_low")
        leaks.run(
            f"optional_value[{label}]",
            optional_value,
            reg,
            "clock_skew_max_ms",
            low=0.0,
        )
        leaks.run(f"read_bounds[{label}]", read_bounds, reg)
        leaks.run(f"read_overrides[{label}]", read_overrides, reg)
        leaks.run(f"read_latency[{label}]", read_latency, reg, BY_ID[TemplateId.RANGE])
    leaks.check()


def test_the_values_the_review_found_are_named_errors_when_called_directly() -> None:
    from ralmon.monitor.config import check_config

    base = make_config(REG)
    for name, value in (
        ("alpha", 10**400),
        ("alpha", CmpFloat(0.5)),
        ("variant", EqStr("likely")),
    ):
        try:
            check_config(tampered(base, name, value))
        except m.MonitorConfigError:
            continue
        raise AssertionError(f"{name}={type(value).__name__} was accepted")
