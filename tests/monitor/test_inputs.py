"""Every public entry point of ``ralmon.monitor`` raises a named error and nothing else (WS05-T04).

Table driven: non-finite and out-of-range times, ``bool``, ``None``, ``str``, ``NaN``, ``10**400``
and hostile objects whose ``__repr__``, ``__eq__``, ``__hash__``, ``__bool__``, ``__len__``,
``__iter__`` or attributes raise. The named errors are ``MonitorInputError`` (inputs and calls),
``MonitorConfigError`` (configuration, registry, library, evaluator arguments), ``PlanIntegrityError``
of ``ralmon.spec`` (a plan that cannot be trusted or parsed), ``PlanFeasibilityError`` and
``PlanVersionError``. A failed call changes no state.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Any

import pytest

import ralmon.monitor as m
from ralmon.signals import Event, EventKind, Sample, SignalId
from ralmon.spec import (
    CarePlan,
    PlanIntegrityError,
    Template,
    TemplateId,
    TemplateInstance,
)

from .helpers import (
    STEP,
    Inputs,
    drive,
    evt,
    hhmm,
    load_f0,
    load_lib,
    make_config,
    make_monitor,
    make_plan,
    smp,
)

REG = load_f0()
LIB = load_lib(REG)


class Hostile:
    """An object that raises from every protocol the monitor could touch."""

    def _boom(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("hostile")

    __repr__ = __str__ = __eq__ = __ne__ = __hash__ = __bool__ = __len__ = _boom  # type: ignore[assignment]
    __iter__ = __getitem__ = __contains__ = __index__ = __int__ = __float__ = _boom  # type: ignore[assignment]
    __lt__ = __gt__ = __le__ = __ge__ = __add__ = __sub__ = __getattr__ = _boom  # type: ignore[assignment]


class HostileStr(str):
    def _boom(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("hostile str")

    __repr__ = __eq__ = __hash__ = __ne__ = _boom  # type: ignore[assignment]


class HostileKey(str):
    """A dict key that hashes but raises when compared."""

    def _boom(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("hostile key")

    __eq__ = __ne__ = _boom  # type: ignore[assignment]
    __hash__ = str.__hash__


class HostileInt(int):
    def _boom(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("hostile int")

    __repr__ = __eq__ = __hash__ = __ne__ = __lt__ = __le__ = __gt__ = __ge__ = _boom  # type: ignore[assignment]


class HostileFloat(float):
    def _boom(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("hostile float")

    __repr__ = __eq__ = __hash__ = __ne__ = __lt__ = __le__ = __gt__ = __ge__ = _boom  # type: ignore[assignment]


BAD_TIMES: list[Any] = [
    None,
    True,
    False,
    1.5,
    float("nan"),
    float("inf"),
    -float("inf"),
    "1000",
    b"1",
    -1,
    2**53 + 1,
    10**400,
    -(10**400),
    1j,
    [1],
    Hostile(),
    HostileFloat(2.0),
]
BAD_VALUES: list[Any] = [
    None,
    True,
    "120",
    float("nan"),
    float("inf"),
    -float("inf"),
    1e300,
    10**400,
    1j,
    [1.0],
    Hostile(),
]
BAD_SEQ: list[Any] = [True, 1.5, "1", 10**400, [1], Hostile()]
BAD_TEXT: list[Any] = [None, 5, b"x", Hostile(), HostileStr("x"), ["x"]]


def fresh() -> Any:
    return make_monitor(REG)


def unchanged(mon: Any) -> bool:
    stats = mon.stats()
    return (
        stats.accepted_count == 0
        and stats.buffered_inputs == 0
        and mon.rejected_inputs() == ()
    )


def sample_cases() -> list[tuple[str, Any]]:
    base = smp("bp", 1000, 120.0)
    cases: list[tuple[str, Any]] = [
        ("not a sample", x) for x in (None, 5, "bp", {"signal": "bp"}, Hostile())
    ]
    cases.append(("an event", evt("dispense", 0)))
    for signal in (
        None,
        1,
        b"bp",
        "",
        "BP",
        "unknown",
        "dose_count",
        "bp_pre",
        "bp_drop",
        "meas_count",
        "meas",
        "dispense",
        "intake",
        "sched_tick",
        "day_end",
        HostileStr("bp"),
        Hostile(),
    ):
        cases.append(("signal", dataclasses.replace(base, signal=signal)))
    cases += [
        ("t_device_ms", dataclasses.replace(base, t_device_ms=t)) for t in BAD_TIMES
    ]
    cases += [("t_rx_ms", dataclasses.replace(base, t_rx_ms=t)) for t in BAD_TIMES]
    cases += [("value", dataclasses.replace(base, value=v)) for v in BAD_VALUES]
    cases += [("seq", dataclasses.replace(base, seq=q)) for q in BAD_SEQ]
    cases += [
        ("quality", dataclasses.replace(base, quality=q))
        for q in (True, "x", float("nan"), Hostile())
    ]
    return cases


SAMPLE_CASES = sample_cases()


@pytest.mark.parametrize(
    ("what", "bad"),
    SAMPLE_CASES,
    ids=[f"{w}-{i}" for i, (w, _) in enumerate(SAMPLE_CASES)],
)
def test_push_sample_refuses_invalid_samples(what: str, bad: Any) -> None:
    mon = fresh()
    with pytest.raises(m.MonitorInputError):
        mon.push_sample(bad)
    assert unchanged(mon)


def event_cases() -> list[tuple[str, Any]]:
    base = evt("dispense", 1000, source="dispenser")
    cases: list[tuple[str, Any]] = [
        ("not an event", x) for x in (None, 5, "dispense", Hostile())
    ]
    cases.append(("a sample", smp("bp", 0)))
    for kind in (None, "dispense", 5, Hostile(), HostileStr("dispense")):
        cases.append(("kind", dataclasses.replace(base, kind=kind)))
    cases += [
        ("t_device_ms", dataclasses.replace(base, t_device_ms=t)) for t in BAD_TIMES
    ]
    cases += [("t_rx_ms", dataclasses.replace(base, t_rx_ms=t)) for t in BAD_TIMES]
    cases += [("source", dataclasses.replace(base, source=t)) for t in BAD_TEXT]
    cases += [
        ("payload", dataclasses.replace(base, payload=p))
        for p in (None, [], 5, "x", Hostile())
    ]
    cases += [("seq", dataclasses.replace(base, seq=q)) for q in BAD_SEQ]
    return cases


EVENT_CASES = event_cases()


@pytest.mark.parametrize(
    ("what", "bad"),
    EVENT_CASES,
    ids=[f"{w}-{i}" for i, (w, _) in enumerate(EVENT_CASES)],
)
def test_push_event_refuses_invalid_events(what: str, bad: Any) -> None:
    mon = fresh()
    with pytest.raises(m.MonitorInputError):
        mon.push_event(bad)
    assert unchanged(mon)


@pytest.mark.parametrize(
    "args",
    [
        (SignalId.BP, True, 0, 0),
        (SignalId.AUTH, True, 0, 0),
        ("bp", True, 0, 0),
        (None, True, 0, 0),
        (Hostile(), True, 0, 0),
        (SignalId.PRESENCE, 1, 0, 0),
        (SignalId.PRESENCE, None, 0, 0),
        (SignalId.PRESENCE, "yes", 0, 0),
        (SignalId.PRESENCE, Hostile(), 0, 0),
        *[(SignalId.PRESENCE, True, t, 0) for t in BAD_TIMES],
        *[(SignalId.INTAKE, False, 0, t) for t in BAD_TIMES],
    ],
)
def test_push_availability_refuses_invalid_arguments(args: tuple[Any, ...]) -> None:
    mon = fresh()
    with pytest.raises(m.MonitorInputError):
        mon.push_availability(*args)
    assert mon.stats().accepted_count == 0


def test_push_availability_accepts_the_two_robot_channels_only_as_signal_or_value() -> (
    None
):
    mon = fresh()
    mon.push_availability(SignalId.PRESENCE, False, 0, 0)
    mon.push_availability("intake", False, 0, 0)  # the value of the SignalId
    assert mon.stats().accepted_count == 2


@pytest.mark.parametrize(
    "bad", BAD_TIMES, ids=[f"time-{i}" for i in range(len(BAD_TIMES))]
)
def test_advance_refuses_invalid_times(bad: Any) -> None:
    mon = fresh()
    with pytest.raises(m.MonitorInputError):
        mon.advance(bad)
    assert mon.stats().steps_finalised == 0
    mon.advance(STEP)  # the monitor is intact
    assert mon.stats().steps_finalised == 2


def test_advance_refuses_time_going_backwards_and_keeps_its_state() -> None:
    mon = fresh()
    mon.advance(5 * STEP)
    for t in (5 * STEP - 1, 0, 4 * STEP):
        with pytest.raises(m.MonitorInputError):
            mon.advance(t)
    assert mon.stats().steps_finalised == 6
    assert mon.advance(5 * STEP) == ()  # the same time again is a no-op


BAD_TEMPLATES: list[Any] = [
    None,
    "resp",
    5,
    Hostile(),
    HostileStr("resp"),
    TemplateId,
    "RESP",
    ("resp",),
]


@pytest.mark.parametrize("index", range(len(BAD_TEMPLATES)))
def test_verdict_latency_bound_refuses_a_non_template(index: int) -> None:
    with pytest.raises(m.MonitorInputError):
        fresh().verdict_latency_bound_ms(BAD_TEMPLATES[index])


def broken_plans() -> list[tuple[str, Any]]:
    good = make_plan(REG, sched=(hhmm(9, 0),))
    cases: list[tuple[str, Any]] = [
        ("not a plan", x) for x in (None, 5, "plan", {"care_plan_id": "x"}, Hostile())
    ]
    fields: dict[str, list[Any]] = {
        "care_plan_id": [None, 5, b"x", Hostile(), HostileStr("x"), ""],
        "pathway_template_id": [None, 5, Hostile()],
        "patient_id": [None, 5, Hostile()],
        "registry_version": [None, 5, Hostile()],
        "instances": [
            None,
            5,
            "abc",
            [None],
            [Hostile()],
            [("x",)],
            Hostile(),
            [object()],
        ],
        "schedule": [
            None,
            5,
            "abc",
            [None],
            ["x"],
            [1.5],
            [True],
            [-1],
            [10**400],
            Hostile(),
        ],
        "plan_version": [None, True, 1.5, "1", -1, 10**400, Hostile(), HostileInt(1)],
        "signature": [5, b"x", Hostile(), HostileStr("x")],
    }
    for name, values in fields.items():
        for v in values:
            cases.append((name, dataclasses.replace(good, **{name: v})))
    for bad_instance in (
        TemplateInstance(None, "k", {}, None),  # type: ignore[arg-type]
        TemplateInstance("sched", "k", {}, None),  # type: ignore[arg-type]
        TemplateInstance(TemplateId.SCHED, None, {}, None),  # type: ignore[arg-type]
        TemplateInstance(TemplateId.SCHED, 5, {}, None),  # type: ignore[arg-type]
        TemplateInstance(TemplateId.SCHED, "k", None, None),  # type: ignore[arg-type]
        TemplateInstance(TemplateId.SCHED, "k", [("a", 1.0)], None),  # type: ignore[arg-type]
        TemplateInstance(TemplateId.SCHED, "k", {1: 1.0}, None),  # type: ignore[arg-type]
        TemplateInstance(TemplateId.SCHED, "k", {"sched_window": None}, None),  # type: ignore[dict-item]
        TemplateInstance(TemplateId.SCHED, "k", {"sched_window": True}, None),  # type: ignore[dict-item]
        TemplateInstance(TemplateId.SCHED, "k", {"sched_window": "1"}, None),  # type: ignore[dict-item]
        TemplateInstance(TemplateId.SCHED, "k", {"sched_window": Hostile()}, None),  # type: ignore[dict-item]
        TemplateInstance(
            TemplateId.SCHED, "k", {HostileKey("sched_window"): 1.0}, None
        ),  # type: ignore[dict-item]
        TemplateInstance(TemplateId.SCHED, "k", {"sched_window": 10**400}, None),
    ):
        cases.append(("instance", dataclasses.replace(good, instances=(bad_instance,))))
    return cases


PLAN_CASES = broken_plans()


@pytest.mark.parametrize(
    ("what", "bad"), PLAN_CASES, ids=[f"{w}-{i}" for i, (w, _) in enumerate(PLAN_CASES)]
)
def test_load_refuses_a_plan_that_cannot_be_read(what: str, bad: Any) -> None:
    mon = fresh()
    with pytest.raises(
        (PlanIntegrityError, m.PlanFeasibilityError, m.MonitorInputError)
    ):
        mon.load(bad)
    # nothing was loaded: a valid plan of version 1 is still accepted afterwards, and no instance exists
    mon.load(make_plan(REG, sched=(hhmm(10, 0),)))
    records = drive(mon, Inputs(), 605)
    assert {r.instance_key for r in records} == {f"sched@{hhmm(10, 0)}"}


def test_load_errors_are_the_named_ones() -> None:
    """The plan errors are PlanIntegrityError for a plan that cannot be read, never TypeError and the like."""
    for _what, bad in PLAN_CASES:
        try:
            fresh().load(bad)
        except (PlanIntegrityError, m.PlanFeasibilityError, m.MonitorInputError):
            continue
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"{type(exc).__name__} escaped for {_what}")
        pytest.fail(f"no error for {_what}")


def constructor_cases() -> list[tuple[str, Any]]:
    cases: list[tuple[str, Any]] = []
    for name, values in {
        "config": [None, 5, {"step_ms": 60_000}, Hostile()],
        "registry": [None, 5, "r", Hostile(), object()],
        "templates": [None, 5, "t", Hostile(), [object()], [None], [Hostile()]],
    }.items():
        cases += [(name, v) for v in values]
    return cases


CONSTRUCTOR_CASES = constructor_cases()


@pytest.mark.parametrize(
    ("what", "bad"),
    CONSTRUCTOR_CASES,
    ids=[f"{w}-{i}" for i, (w, _) in enumerate(CONSTRUCTOR_CASES)],
)
def test_constructor_refuses_bad_arguments(what: str, bad: Any) -> None:
    kwargs = {"config": make_config(REG), "registry": REG, "templates": LIB, what: bad}
    with pytest.raises(m.MonitorConfigError):
        m.StreamingMonitor(**kwargs)


@pytest.mark.parametrize(
    "option",
    [
        {"verifier": 5},
        {"verifier": Hostile()},
        {"require_signature": 1},
        {"require_signature": None},
        {"require_signature": Hostile()},
        {"template_ids": Hostile()},
        {"template_ids": 5},
        {"buffer_capacity": Hostile()},
        {"buffer_capacity": 10**400},
        {"buffer_capacity": 10**9},
    ],
)
def test_constructor_refuses_bad_options(option: dict[str, Any]) -> None:
    with pytest.raises(m.MonitorConfigError):
        m.StreamingMonitor(make_config(REG), REG, LIB, **option)


def test_hostile_calibrator_and_forecaster_are_accepted_and_never_touched() -> None:
    mon = m.StreamingMonitor(
        make_config(REG), REG, LIB, calibrator=Hostile(), forecaster=Hostile()
    )
    mon.load(make_plan(REG, sched=(hhmm(9, 0),)))
    assert len(drive(mon, Inputs(), 545)) == 6


def test_a_verifier_that_raises_is_a_plan_integrity_error() -> None:
    class Raising:
        def verify(self, payload: bytes, signature: str) -> bool:
            raise RuntimeError("boom")

    mon = m.StreamingMonitor(make_config(REG), REG, LIB, verifier=Raising())  # type: ignore[arg-type]
    plan = dataclasses.replace(make_plan(REG), signature="0" * 64)
    with pytest.raises(PlanIntegrityError):
        mon.load(plan)


def test_a_closed_monitor_refuses_every_call_but_stats() -> None:
    mon = fresh()
    mon.advance(STEP)
    mon.close()
    mon.close()  # idempotent
    with pytest.raises(m.MonitorInputError):
        mon.push_sample(smp("bp", 2 * STEP, 120.0))
    with pytest.raises(m.MonitorInputError):
        mon.push_event(evt("dispense", 2 * STEP))
    with pytest.raises(m.MonitorInputError):
        mon.push_availability(SignalId.PRESENCE, True, 2 * STEP, 2 * STEP)
    with pytest.raises(m.MonitorInputError):
        mon.advance(3 * STEP)
    with pytest.raises(m.MonitorInputError):
        mon.load(make_plan(REG))
    assert mon.stats().steps_finalised == 2
    assert mon.late_inputs() == ()


def test_values_inside_the_float_range_are_accepted() -> None:
    mon = fresh()
    for value in (0.0, -0.0, 1e-300, 119.999, 1e12, -1e12, 7):
        mon.push_sample(smp("bp", 1000, value))
    assert mon.stats().accepted_count == 7


def test_an_integer_value_is_accepted_as_a_number() -> None:
    mon = fresh()
    mon.push_sample(Sample("bp", 0, 0, 120, None, None))  # type: ignore[arg-type]
    mon.push_event(Event(EventKind.MEASUREMENT, 0, 0, "cuff", {"k": 1}, 3))
    assert mon.stats().accepted_count == 2


def test_hostile_numeric_subclasses_are_accepted_or_refused_by_name_never_escape() -> (
    None
):
    mon = fresh()
    attempts: list[Any] = [
        lambda: mon.push_sample(
            dataclasses.replace(
                smp("bp", 0, 1.0), t_device_ms=HostileInt(5), t_rx_ms=HostileInt(5)
            )
        ),
        lambda: mon.push_sample(
            dataclasses.replace(smp("bp", 0, 1.0), value=HostileFloat(1.0))
        ),
        lambda: mon.push_sample(
            dataclasses.replace(smp("bp", 0, 1.0), seq=HostileInt(3))
        ),
        lambda: mon.push_event(
            dataclasses.replace(evt("dispense", 0), seq=HostileInt(3))
        ),
        lambda: mon.advance(HostileInt(5)),
        lambda: m.StreamingMonitor(
            make_config(REG), REG, LIB, buffer_capacity=HostileInt(3)
        ),
    ]
    for attempt in attempts:
        try:
            attempt()
        except (m.MonitorInputError, m.MonitorConfigError):
            pass


def test_error_messages_are_bounded_and_never_call_a_hostile_repr() -> None:
    mon = fresh()
    huge = "x" * 1_000_000
    with pytest.raises(m.MonitorInputError) as info:
        mon.push_sample(dataclasses.replace(smp("bp", 0, 1.0), signal=huge))
    assert len(str(info.value)) < 2_000
    with pytest.raises(m.MonitorInputError) as info2:
        mon.push_sample(dataclasses.replace(smp("bp", 0, 1.0), value=Hostile()))
    assert len(str(info2.value)) < 2_000


def test_nan_never_enters_an_interval() -> None:
    """Section 2.6 (d): no NaN in an interval, whatever finite pressures arrive."""
    mon = make_monitor(REG, sched=(hhmm(9, 0),))
    inputs = Inputs()
    for k, v in enumerate((120.0, 1e12, -1e12, 0.0, 150.0)):
        inputs.events.append(evt("measurement", hhmm(9, 0) + k * STEP, source="cuff"))
        inputs.samples.append(smp("bp", hhmm(9, 0) + k * STEP, v))
        inputs.events.append(
            evt("dispense", hhmm(9, 0) + k * STEP + 1000, source="dispenser")
        )
    for r in drive(mon, inputs, 560):
        assert not math.isnan(r.sigma_interval.lo) and not math.isnan(
            r.sigma_interval.hi
        )
        assert r.sigma_interval.lo <= r.sigma_interval.hi


def test_pointevaluator_argument_errors_are_named() -> None:
    template = next(t for t in LIB if t.id is TemplateId.RANGE)
    instance = TemplateInstance(TemplateId.RANGE, "range@0", {}, 0)
    good = (template, instance, REG, STEP)
    m.make_point_evaluator(*good)
    bad_calls: list[tuple[Any, ...]] = [
        (None, instance, REG, STEP),
        (5, instance, REG, STEP),
        (Hostile(), instance, REG, STEP),
        (template, None, REG, STEP),
        (template, Hostile(), REG, STEP),
        (template, instance, None, STEP),
        (template, instance, Hostile(), STEP),
        *[
            (template, instance, REG, t)
            for t in (None, True, 0, -1, 1.5, "60000", 70_000, 10**400, Hostile())
        ],
        (
            template,
            TemplateInstance(TemplateId.SCHED, "x", {}, 0),
            REG,
            STEP,
        ),  # another template
        (
            template,
            TemplateInstance(TemplateId.RANGE, "x", {}, None),
            REG,
            STEP,
        ),  # no anchor
        (template, TemplateInstance(TemplateId.RANGE, "x", {}, -1), REG, STEP),
        (
            template,
            TemplateInstance(TemplateId.RANGE, "x", {"nope": 1.0}, 0),
            REG,
            STEP,
        ),
    ]
    for args in bad_calls:
        with pytest.raises(m.MonitorConfigError):
            m.make_point_evaluator(*args)
    for kind in (
        "nope",
        5,
        Hostile(),
        "day_end",
        "dispense",
    ):  # a day-end is a COUNT anchor only
        with pytest.raises(m.MonitorConfigError):
            m.make_point_evaluator(*good, anchor_kind=kind)


def test_pointevaluator_step_errors_are_named() -> None:
    template = next(t for t in LIB if t.id is TemplateId.RANGE)
    evaluator = m.make_point_evaluator(
        template, TemplateInstance(TemplateId.RANGE, "r", {}, 0), REG, STEP
    )
    for t in (
        None,
        True,
        1.5,
        STEP,
        -STEP,
        10**400,
        Hostile(),
        "0",
    ):  # the first step is step 0
        with pytest.raises(m.MonitorInputError):
            evaluator.step(t, {})
    evaluator.step(0, {"meas": 1.0, "bp": 125.0})
    for values in (
        None,
        5,
        "x",
        [("bp", 1.0)],
        Hostile(),
        {"bp": "x"},
        {"bp": True},
        {1: 2.0},
        {"bp": Hostile()},
    ):
        with pytest.raises(m.MonitorInputError):
            evaluator.step(STEP, values)  # type: ignore[arg-type]
    with pytest.raises(m.MonitorInputError):
        evaluator.step(0, {})  # a step cannot be repeated
    assert (
        evaluator.step(STEP, {"bp": 125.0}) is not None
    )  # the evaluator survived the refused calls


def test_run_offline_argument_errors_are_named() -> None:
    config, plan = make_config(REG), make_plan(REG)

    class Day:
        samples = ()
        events = ()
        patient_id = "p"
        day_index = 0
        seed = 0
        care_plan_id = "c"

    for day in (None, 5, "day", Hostile(), object()):
        with pytest.raises(m.MonitorInputError):
            m.run_offline(day, plan, config, None, None, registry=REG, templates=LIB)  # type: ignore[arg-type]
    for bad_plan in (None, 5, Hostile()):
        with pytest.raises(PlanIntegrityError):
            m.run_offline(
                Day(), bad_plan, config, None, None, registry=REG, templates=LIB
            )  # type: ignore[arg-type]
    for bad_config in (None, 5, Hostile()):
        with pytest.raises(m.MonitorConfigError):
            m.run_offline(
                Day(), plan, bad_config, None, None, registry=REG, templates=LIB
            )  # type: ignore[arg-type]
    for bad in (5, "x", Hostile()):
        with pytest.raises(m.MonitorConfigError):
            m.run_offline(Day(), plan, config, None, None, registry=bad, templates=LIB)
        with pytest.raises(m.MonitorConfigError):
            m.run_offline(Day(), plan, config, None, None, registry=REG, templates=bad)

    class BadSamples(Day):
        samples = (5,)

    with pytest.raises(m.MonitorInputError):
        m.run_offline(
            BadSamples(), plan, config, None, None, registry=REG, templates=LIB
        )

    class NotIterable(Day):
        events = 5

    with pytest.raises(m.MonitorInputError):
        m.run_offline(
            NotIterable(), plan, config, None, None, registry=REG, templates=LIB
        )


def test_template_dataclass_is_not_modified_by_the_monitor() -> None:
    before = [dataclasses.astuple(t) for t in LIB]
    fresh()
    assert [dataclasses.astuple(t) for t in LIB] == before
    assert all(isinstance(t, Template) for t in LIB)
    assert isinstance(make_plan(REG), CarePlan)
