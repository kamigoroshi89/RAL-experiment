"""Latent ground-truth labeller and the non-circularity tests (WS04-T10).

FIXTURE-ONLY. Every number below is arithmetic against the fixture registry F0
(``tests/fixtures/spec/registry_f0.yaml``, ADR-027: band 110 to 140, hold threshold 100 with a 60 min
look-back, dose limit 2 and day-end minimum 2, delta1 60 min, delta2 180 min, delta_resp 10, sched_window
30 min, lower pressure bound 50, ``step_ms = 60000``), chosen so that expected results can be computed by
hand. None of it is a clinical value, a device specification or a statement about any patient.
State independence: no test reads a committed design or prior file in a way that depends on whether a human
has filled it, and the real registry is read only by tests that must hold for any of its states.

What is under test (``ralmon.benchmark.labelling``)
---------------------------------------------------
* ``ideal_observation``: an ``ObservedDay``-shaped view of a latent day built only from latent values at
  measurement times (``scheduled``) or at every latent grid step (``dense``), exact values, ``t_rx == t_device``,
  no quality, no noise, only the phi_CP template signals;
* ``label_latent_day``: the C1 truth is the set of violated phi_CP instances on the LATENT day (the WS05
  monitor run on the ideal observation), one ``GroundTruthEvent`` per violated instance, with the
  ``onset_ms`` and ``end_ms`` conventions of the module, explained by an injection record only by the link table
  and the latency bound, with natural subtypes from the behaviour log; C2 and C3 truth is one event per
  REALISED injection record; ``label_latent_day`` has no observed-day parameter;
* the non-circularity tests 13 to 18 (analisi section 10 objection 1), 21 and 22: perfect observation
  reproduces the truth, noisy observation diverges in the expected direction, the truth follows the latent
  trace and not the injection intent, the truth is the same whatever corrupts the observation, an undetectable
  injection is still in the truth, and an independent reference evaluator (``reference_phi_cp``, no import of
  ``ralmon``) agrees with the labeller.
"""

from __future__ import annotations

import ast
import copy
import dataclasses
import inspect
import itertools
import json
import math
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from ralmon.benchmark import labelling
from ralmon.benchmark.adherence import (
    AdherenceConfig,
    AdherenceModel,
    AdherenceState,
    BehaviourEntry,
)
from ralmon.benchmark.inject_c1 import C1_SUBTYPES, c1_spec
from ralmon.benchmark.injection import (
    InjectionContext,
    InjectionRecord,
    InjectionSpec,
    apply_observation_injections,
    finalize_observed,
    injection_log,
    record_to_ground_truth,
)
from ralmon.benchmark.labelling import (
    LINK_TABLE,
    MODE_DENSE,
    MODE_SCHEDULED,
    AssembledDay,
    IdealObservationError,
    LabelledDay,
    LabellingError,
    RegistryMismatchError,
    RunnerError,
    assemble_benchmark_day,
    ideal_observation,
    label_latent_day,
    label_latent_day_detailed,
)
from ralmon.benchmark.latent import T_DAY_MS
from ralmon.benchmark.latent_day import (
    AssemblyConfig,
    ForcedSlot,
    LatentResult,
    assemble_latent_days,
)
from ralmon.benchmark.measurement import (
    MeasurementDesign,
    NoJitter,
    build_observed_base,
)
from ralmon.benchmark.pkpd import OneCompartmentEmax
from ralmon.benchmark.priors import (
    AdherenceParams,
    DeviceErrorModel,
    LiteraturePriorSource,
    PatientParams,
)
from ralmon.benchmark.schedule import Schedule, derive_schedule
from ralmon.benchmark.segments import InlineSegment, SegmentLibrary
from ralmon.benchmark.trace import (
    BenchmarkDay,
    GroundTruthEvent,
    InjectedClass,
    LatentDay,
    ObservedDay,
    TruthRecord,
)
from ralmon.monitor import (
    MonitorConfig,
    RobustnessInterval,
    VerdictRecord,
    VerdictState,
    run_offline,
    run_offline_detailed,
)
from ralmon.signals import Event, EventKind, Sample
from ralmon.spec import (
    CarePlan,
    TemplateId,
    TemplateInstance,
    TemplateKind,
    load_registry,
    load_templates,
)

from .conftest import make_fixture_prior
from .reference_phi_cp import Params as RefParams
from .reference_phi_cp import Violation as RefViolation
from .reference_phi_cp import evaluate as reference_evaluate

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "ralmon" / "benchmark"
F0_PATH = ROOT / "tests" / "fixtures" / "spec" / "registry_f0.yaml"
CASES_PATH = ROOT / "tests" / "fixtures" / "benchmark" / "latent_days_phi_cp.yaml"
GOLDEN = ROOT / "docs" / "formal" / "golden"
README = ROOT / "docs" / "plan" / "workstreams" / "WS04-benchmark" / "README.md"
GROUND_TRUTH_DOC = ROOT / "docs" / "benchmark" / "ground-truth.md"
THIS_FILE = Path(__file__)

SEC = 1_000
MIN = 60_000
HOUR = 3_600_000
DAY = T_DAY_MS
C1, C2, C3 = InjectedClass.C1, InjectedClass.C2, InjectedClass.C3
INF = math.inf
PATIENT = "p-1"
PLAN_ID = "plan-1"
LAG = 5 * SEC  # FIXTURE-ONLY intake lag


def T(h: int, m: int = 0, s: int = 0, day: int = 0) -> int:
    """Clock time on the continuing axis, in ms."""
    return day * DAY + ((h * 60 + m) * 60 + s) * SEC


def clock(text: str, day: int = 0) -> int:
    """``"HH:MM"`` (or ``"24:00"``) on the continuing axis."""
    hours, minutes = text.split(":")
    return day * DAY + (int(hours) * 60 + int(minutes)) * MIN


# ---------------------------------------------------------------------------------------------------
# Registry, templates, configuration (F0, state independent)
# ---------------------------------------------------------------------------------------------------

F0 = load_registry(F0_PATH, step_ms=MIN, allow_fixture_only=True)
LIBRARY = load_templates(registry=F0)
CP_TEMPLATES = tuple(t for t in LIBRARY if t.kind is TemplateKind.CARE_PLAN)
CFG = MonitorConfig(MIN, 0, False, None, "likely", F0.version())
REF_PARAMS = RefParams.from_registry_file(F0_PATH)
DELTA2 = 3 * HOUR  # delta2 of F0, read below from the registry as a check
assert int(F0.get("delta2").value) == DELTA2
assert int(F0.get("sched_window").value) == 30 * MIN


def make_config(**changes: Any) -> MonitorConfig:
    return dataclasses.replace(CFG, **changes)


# ---------------------------------------------------------------------------------------------------
# Hand-built latent days, plans and verdict records
# ---------------------------------------------------------------------------------------------------


def make_latent(
    day: int = 0,
    *,
    bp: float | Callable[[int], float] = 130.0,
    measurements: Sequence[int] = (),
    dispenses: Sequence[int] = (),
    ticks: Sequence[int] = (),
    intakes: bool = True,
    grid_ms: int = MIN,
    vitals: bool = False,
    patient: str = PATIENT,
    seed: int = 0,
) -> LatentDay:
    """A latent day: ``bp`` on the grid (a number or a function of the clock time), ideal MEASUREMENT events
    at ``measurements``, true DISPENSE (and INTAKE ``LAG`` later) events, SCHEDULE_TICK events.

    Times of the arguments are clock times of the day (ms); the result is on the continuing axis.
    """
    base = day * DAY
    value = bp if callable(bp) else (lambda _t, _v=bp: _v)
    samples = [
        Sample("bp", base + t, base + t, float(value(t)), None, None)
        for t in range(0, DAY, grid_ms)
    ]
    if vitals:
        for t in range(0, DAY, HOUR):
            samples.append(Sample("hr_ecg", base + t, base + t, 70.0, None, None))
            samples.append(Sample("spo2", base + t, base + t, 96.0, None, None))
    events = [
        Event(
            EventKind.SCHEDULE_TICK,
            base + t,
            base + t,
            "ward",
            {"kind": "measurement"},
            None,
        )
        for t in ticks
    ]
    events += [
        Event(EventKind.MEASUREMENT, base + t, base + t, "cuff", {}, None)
        for t in measurements
    ]
    for t in dispenses:
        events.append(
            Event(EventKind.DISPENSE, base + t, base + t, "dispenser", {}, None)
        )
        if intakes:
            events.append(
                Event(
                    EventKind.INTAKE,
                    base + t + LAG,
                    base + t + LAG,
                    "patient",
                    {},
                    None,
                )
            )
    samples.sort(key=lambda s: s.t_rx_ms)
    events.sort(key=lambda e: e.t_rx_ms)
    return LatentDay(patient, day, seed, tuple(samples), tuple(events))


def make_plan(
    day: int = 0,
    *,
    sched: Sequence[int] = (),
    count_end: bool = True,
    parameter_records: Sequence[TemplateInstance] = (),
    patient: str = PATIENT,
    care_plan_id: str = PLAN_ID,
    registry_version: str | None = None,
) -> CarePlan:
    """A plan with static SCHED instances at ``sched`` (clock times) and the day-end COUNT of ``day``."""
    base = day * DAY
    instances = [
        TemplateInstance(TemplateId.SCHED, f"sched@{base + t}", {}, base + t)
        for t in sched
    ]
    if count_end:
        instances.append(
            TemplateInstance(TemplateId.COUNT, f"count@{base + DAY}", {}, base + DAY)
        )
    instances += list(parameter_records)
    return CarePlan(
        care_plan_id,
        "hypertension-fixture",
        patient,
        F0.version() if registry_version is None else registry_version,
        tuple(instances),
        (),
        1,
        None,
    )


def vr(
    template: TemplateId | str,
    key: str,
    state: VerdictState,
    t_eval: int,
    *,
    decided: int | None | str = "auto",
    pending: int | None = None,
) -> VerdictRecord:
    """A hand-written verdict record. ``decided="auto"`` is ``t_eval`` for a definitive state."""
    tid = TemplateId(template)
    if decided == "auto":
        decided = (
            t_eval if state in (VerdictState.VIOLATED, VerdictState.SATISFIED) else None
        )
    assert decided is None or isinstance(decided, int)
    if state is VerdictState.VIOLATED:
        interval = RobustnessInterval(-INF, -1.0)
    elif state is VerdictState.SATISFIED:
        interval = RobustnessInterval(1.0, INF)
    else:
        interval = RobustnessInterval(-INF, INF)
    return VerdictRecord(
        key,
        tid,
        t_eval,
        state,
        interval,
        (-1.0, 1.0),
        None,
        decided,
        pending,
    )


def violated(
    template: TemplateId | str,
    key: str,
    decided: int,
    pending: int | None,
    *,
    t_eval: int | None = None,
) -> VerdictRecord:
    return vr(
        template,
        key,
        VerdictState.VIOLATED,
        decided if t_eval is None else t_eval,
        decided=decided,
        pending=pending,
    )


class Stub:
    """A runner that returns hand-written verdict records and remembers how it was called."""

    def __init__(self, records: Sequence[Any] = ()) -> None:
        self.records = list(records)
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self,
        day: Any,
        plan: Any,
        config: Any,
        calibrator: Any,
        forecaster: Any,
        **kw: Any,
    ) -> Any:
        self.calls.append(
            {
                "day": day,
                "plan": plan,
                "config": config,
                "calibrator": calibrator,
                "forecaster": forecaster,
                **kw,
            }
        )
        return list(self.records)


def label(
    records: Sequence[Any] = (),
    *,
    latent: LatentDay | None = None,
    plan: CarePlan | None = None,
    injections: Sequence[Any] = (),
    behaviour: Sequence[Any] = (),
    run_fn: Callable[..., Any] | None = None,
    config: MonitorConfig | None = None,
    bound: Callable[[TemplateId], int] | None = None,
    mode: str = MODE_SCHEDULED,
    **kw: Any,
) -> tuple[GroundTruthEvent, ...]:
    """``label_latent_day`` with a stub runner that returns ``records`` (F0 registry and library)."""
    kw.setdefault("registry", F0)
    kw.setdefault("templates", LIBRARY)
    return label_latent_day(
        make_latent(measurements=(T(6), T(12))) if latent is None else latent,
        make_plan() if plan is None else plan,
        list(injections),
        list(behaviour),
        Stub(records) if run_fn is None else run_fn,
        CFG if config is None else config,
        bound,
        mode,
        **kw,
    )


def tup(e: GroundTruthEvent) -> tuple[Any, ...]:
    return (
        e.cls.value,
        e.subtype,
        e.onset_ms,
        e.end_ms,
        e.injected,
        e.template_id,
        e.confounder_group,
    )


def c1_event(
    subtype: str,
    template: str,
    onset: int,
    end: int | None = None,
    *,
    injected: bool,
    group: str | None = None,
) -> tuple[Any, ...]:
    return ("C1", subtype, onset, end, injected, template, group)


# Injection records ---------------------------------------------------------------------------------


def c1_record(
    subtype: str,
    onset: int,
    end: int | None = None,
    *,
    realised: bool = True,
    group: str | None = None,
    details: Mapping[str, Any] | None = None,
    level: str | None = None,
) -> InjectionRecord:
    """A hand-written C1 injection record (the window ``[onset, end)`` or the instant ``onset``)."""
    duration = None if end is None else end - onset
    magnitude = (
        1.0
        if subtype
        in ("hypertensive_spike", "hypotension_below_hold", "drug_nonresponse")
        else None
    )
    unit = (
        "mmHg" if subtype in ("hypertensive_spike", "hypotension_below_hold") else None
    )
    spec = InjectionSpec(
        C1, subtype, onset, duration, magnitude, unit, {}, level, group
    )
    return InjectionRecord(
        spec,
        onset,
        end,
        realised,
        1 if realised else 0,
        (),
        level,
        group,
        dict(details or {}),
    )


def other_record(
    cls: InjectedClass,
    subtype: str,
    onset: int,
    end: int | None = None,
    *,
    realised: bool = True,
    group: str | None = None,
    evidence: tuple[str, ...] = (),
) -> InjectionRecord:
    duration = None if end is None else end - onset
    spec = InjectionSpec(cls, subtype, onset, duration, None, None, {}, None, group)
    return InjectionRecord(
        spec, onset, end, realised, 1 if realised else 0, evidence, None, group, {}
    )


def named(exc: BaseException) -> bool:
    """The exception is one of the module's named errors, not a raw built-in one."""
    return (
        isinstance(exc, LabellingError)
        and type(exc).__module__ == "ralmon.benchmark.labelling"
    )


# ---------------------------------------------------------------------------------------------------
# Tests 1 to 3: the ideal observation
# ---------------------------------------------------------------------------------------------------


def stepped(t: int) -> float:
    """Latent pressure that changes every hour (so that a hold between grid points is visible)."""
    return 120.0 + t // HOUR


def bp_pairs(day: Any) -> list[tuple[int, float]]:
    return [(s.t_device_ms, s.value) for s in day.samples if s.signal == "bp"]


def times_of(day: Any, kind: EventKind) -> list[int]:
    return [e.t_device_ms for e in day.events if e.kind is kind]


def test_ideal_observation_scheduled_mode() -> None:
    measurements = (T(6, 50), T(9, 0, 30), T(12), T(20, 15))
    latent = make_latent(
        bp=stepped,
        measurements=measurements,
        dispenses=(T(7), T(21)),
        ticks=(T(6, 50), T(12)),
        vitals=True,
        seed=7,
    )
    day = ideal_observation(latent, PLAN_ID)  # the default mode is `scheduled`
    assert isinstance(day, ObservedDay)
    assert (day.patient_id, day.day_index, day.seed, day.care_plan_id) == (
        PATIENT,
        0,
        7,
        PLAN_ID,
    )
    sources = {e.kind: e.source for e in day.events}
    assert sources == {
        EventKind.MEASUREMENT: "cuff",
        EventKind.DISPENSE: "dispenser",
        EventKind.SCHEDULE_TICK: "ward",
    }
    # bp exists only at the latent MEASUREMENT times, with the exact held latent value
    # (the value of the last grid point at or before the instant: 09:00:30 holds the 09:00 value)
    assert bp_pairs(day) == [
        (T(6, 50), 126.0),
        (T(9, 0, 30), 129.0),
        (T(12), 132.0),
        (T(20, 15), 140.0),
    ]
    # one MEASUREMENT event each; impulses are events only, never a `meas` sample
    assert times_of(day, EventKind.MEASUREMENT) == list(measurements)
    assert not [s for s in day.samples if s.signal == "meas"]
    # no transport, no quality, no sequence, no noise
    for item in itertools.chain(day.samples, day.events):
        assert item.t_rx_ms == item.t_device_ms
    assert all(s.quality is None and s.seq is None for s in day.samples)
    assert all(e.seq is None for e in day.events)
    # only the phi_CP template signals: bp and the end-of-day impulse; no latent vitals, no intake
    assert {s.signal for s in day.samples} == {"bp", "day_end"}
    assert {e.kind for e in day.events} == {
        EventKind.MEASUREMENT,
        EventKind.DISPENSE,
        EventKind.SCHEDULE_TICK,
    }
    assert times_of(day, EventKind.DISPENSE) == [T(7), T(21)]
    assert times_of(day, EventKind.SCHEDULE_TICK) == [T(6, 50), T(12)]
    # the contract order: sorted by receive time
    assert [s.t_rx_ms for s in day.samples] == sorted(s.t_rx_ms for s in day.samples)
    assert [e.t_rx_ms for e in day.events] == sorted(e.t_rx_ms for e in day.events)


def test_ideal_observation_is_built_from_latent_values_only() -> None:
    # a refused measurement (no latent MEASUREMENT) gives no reading: the observation never invents one
    latent = make_latent(bp=stepped, measurements=(T(12),), ticks=(T(9), T(12)))
    day = ideal_observation(latent, PLAN_ID)
    assert times_of(day, EventKind.MEASUREMENT) == [T(12)]
    assert bp_pairs(day) == [(T(12), 132.0)]
    # the closing step is held: the last grid point holds to the end of the day
    late = make_latent(bp=stepped, measurements=(DAY - 1,))
    assert bp_pairs(ideal_observation(late, PLAN_ID)) == [(DAY - 1, 143.0)]
    # the input is never modified
    again = make_latent(bp=stepped, measurements=(T(12),), ticks=(T(9), T(12)))
    assert again == latent


def test_ideal_observation_dense_mode() -> None:
    latent = make_latent(
        bp=stepped, measurements=(T(9, 0, 30),), dispenses=(T(7),), ticks=(T(9),)
    )
    day = ideal_observation(latent, PLAN_ID, MODE_DENSE)
    grid = [(s.t_device_ms, s.value) for s in latent.samples if s.signal == "bp"]
    assert len(grid) == DAY // MIN
    assert bp_pairs(day) == grid  # bp at every latent grid step, exact values
    # each with a MEASUREMENT event; the latent MEASUREMENT at 09:00:30 is not copied
    assert times_of(day, EventKind.MEASUREMENT) == [t for t, _ in grid]
    assert not [s for s in day.samples if s.signal == "meas"]
    for item in itertools.chain(day.samples, day.events):
        assert item.t_rx_ms == item.t_device_ms
    assert times_of(day, EventKind.DISPENSE) == [T(7)]


def test_modes_are_named_and_unknown_ones_refused() -> None:
    assert labelling.MODES == (MODE_SCHEDULED, MODE_DENSE) == ("scheduled", "dense")
    latent = make_latent(measurements=(T(12),))
    for bad in ("Scheduled", "", "sparse", None, 0, True, b"dense", ["dense"]):
        with pytest.raises(IdealObservationError):
            ideal_observation(latent, PLAN_ID, bad)  # type: ignore[arg-type]


def test_ideal_observation_continuing_axis_and_day_end_impulse() -> None:
    for day_index in (0, 1, 5):
        latent = make_latent(day_index, measurements=(T(12),), dispenses=(T(7),))
        obs = ideal_observation(latent, PLAN_ID)
        assert obs.day_index == day_index
        assert bp_pairs(obs) == [(T(12, day=day_index), 130.0)]
        [end] = [s for s in obs.samples if s.signal == "day_end"]
        assert (end.t_device_ms, end.t_rx_ms, end.value) == (
            (day_index + 1) * DAY,
        ) * 2 + (1.0,)
        assert end.seq is None and end.quality is None


def test_ideal_observation_rejects_missing_template_signal() -> None:
    # the latent day cannot supply a pressure: no bp sample at all
    no_bp = LatentDay(
        PATIENT,
        0,
        0,
        (),
        (Event(EventKind.MEASUREMENT, T(12), T(12), "cuff", {}, None),),
    )
    with pytest.raises(IdealObservationError, match="no bp sample"):
        ideal_observation(no_bp, PLAN_ID)
    with pytest.raises(IdealObservationError, match="no bp sample"):
        ideal_observation(no_bp, PLAN_ID, MODE_DENSE)
    # a measurement before the first pressure: there is no value to hold, nothing is guessed
    late_start = LatentDay(
        PATIENT,
        0,
        0,
        (Sample("bp", T(8), T(8), 130.0, None, None),),
        (Event(EventKind.MEASUREMENT, T(7), T(7), "cuff", {}, None),),
    )
    with pytest.raises(IdealObservationError, match="before"):
        ideal_observation(late_start, PLAN_ID)
    # a template signal the latent day never carries: the request is refused, not answered with a guess
    latent = make_latent(measurements=(T(12),))
    for name in (
        "presence",
        "intake",
        "cuff_health",
        "inflation_ms",
        "auth",
        "hr_ecg",
        "spo2",
        "hr_pulse",
    ):
        with pytest.raises(IdealObservationError, match=name):
            ideal_observation(latent, PLAN_ID, signals=("bp", "meas", name))
    with pytest.raises(IdealObservationError, match="not a signal"):
        ideal_observation(latent, PLAN_ID, signals=("not_a_signal",))
    # the same through the labeller: a phi_CP template that needs the `presence` signal
    needy = dataclasses.replace(CP_TEMPLATES[0], signals=("meas", "presence"))
    with pytest.raises(IdealObservationError, match="phi_CP templates need.*presence"):
        label(templates=(needy, *CP_TEMPLATES[1:]))


def test_day_end_impulse_is_added_exactly_when_a_template_needs_it() -> None:
    latent = make_latent(measurements=(T(12),), dispenses=(T(7),))
    with_end = ideal_observation(
        latent, PLAN_ID, signals=("bp", "meas", "dispense", "day_end")
    )
    assert [s.t_device_ms for s in with_end.samples if s.signal == "day_end"] == [DAY]
    without = ideal_observation(latent, PLAN_ID, signals=("bp", "meas", "dispense"))
    assert not [s for s in without.samples if s.signal == "day_end"]
    # derived signals are computed by the monitor, never supplied
    derived = ideal_observation(
        latent, PLAN_ID, signals=("bp", "meas", "dose_count", "bp_drop", "bp_pre")
    )
    assert {s.signal for s in derived.samples} == {"bp"}
    assert {e.kind for e in derived.events} == {EventKind.MEASUREMENT}
    # each requested signal gives exactly its items
    only_dispense = ideal_observation(latent, PLAN_ID, signals=("dispense",))
    assert not only_dispense.samples
    assert [e.kind for e in only_dispense.events] == [EventKind.DISPENSE]
    only_ticks = ideal_observation(
        make_latent(ticks=(T(9),)), PLAN_ID, signals=("sched_tick",)
    )
    assert [e.kind for e in only_ticks.events] == [EventKind.SCHEDULE_TICK]
    assert only_ticks.events[0].payload == {"kind": "measurement"}


def test_ideal_observation_keeps_each_tick_with_its_own_kind() -> None:
    # a dose tick and a measurement tick at one instant are two events, each with its own payload
    base = make_latent(measurements=(T(8),))
    ticks = (
        Event(EventKind.SCHEDULE_TICK, T(8), T(8), "ward", {"kind": "dose"}, None),
        Event(
            EventKind.SCHEDULE_TICK, T(8), T(8), "ward", {"kind": "measurement"}, None
        ),
    )
    latent = dataclasses.replace(base, events=(*ticks, *base.events))
    day = ideal_observation(latent, PLAN_ID)
    got = [dict(e.payload) for e in day.events if e.kind is EventKind.SCHEDULE_TICK]
    assert got == [{"kind": "dose"}, {"kind": "measurement"}]
    # a payload that is not a mapping is refused
    broken = clone_with(ticks[0], payload=[1])
    with pytest.raises(IdealObservationError):
        ideal_observation(
            dataclasses.replace(base, events=(broken, *base.events)), PLAN_ID
        )


def test_ideal_observation_refuses_what_the_semantics_cannot_hold() -> None:
    step = MIN
    # (A0) of docs/formal/05 section 2.1: at most one pressure per grid bin
    close = make_latent(
        measurements=(T(12, 0, 10), T(12, 0, 40))
    )  # one bin (12:00, 12:01]
    with pytest.raises(IdealObservationError, match="bin"):
        ideal_observation(close, PLAN_ID, step_ms=step)
    ideal_observation(close, PLAN_ID)  # without a step the check cannot be made
    ideal_observation(
        make_latent(measurements=(T(12), T(12, 1))), PLAN_ID, step_ms=step
    )
    # a dense grid finer than the monitor step would put several readings in one bin
    fine = make_latent(grid_ms=20 * SEC, measurements=())
    with pytest.raises(IdealObservationError, match="bin"):
        ideal_observation(fine, PLAN_ID, MODE_DENSE, step_ms=step)
    # items outside the day are refused (the monitor would report them as finalised and drop them)
    for day_index, t in ((0, -1), (0, DAY + 1), (1, DAY - 1), (1, 2 * DAY + 1)):
        base = make_latent(day_index, measurements=())
        outside = dataclasses.replace(
            base, events=(Event(EventKind.DISPENSE, t, t, "dispenser", {}, None),)
        )
        with pytest.raises(IdealObservationError, match="day"):
            ideal_observation(outside, PLAN_ID)
    # the closing instant itself belongs to the day (it covers (d T, (d + 1) T])
    edge = dataclasses.replace(
        make_latent(measurements=()),
        events=(Event(EventKind.DISPENSE, DAY, DAY, "dispenser", {}, None),),
    )
    assert times_of(ideal_observation(edge, PLAN_ID), EventKind.DISPENSE) == [DAY]
    # a pressure that is not a finite number is not a reading
    for bad in (math.nan, math.inf, -math.inf):
        base = make_latent(measurements=(T(12),))
        samples = tuple(
            dataclasses.replace(s, value=bad) if s.t_device_ms == T(12) else s
            for s in base.samples
        )
        with pytest.raises(IdealObservationError):
            ideal_observation(dataclasses.replace(base, samples=samples), PLAN_ID)
    # duplicate or unsorted grid times
    base = make_latent(measurements=(T(12),))
    twice = dataclasses.replace(base, samples=(base.samples[0], *base.samples))
    with pytest.raises(IdealObservationError):
        ideal_observation(twice, PLAN_ID)


# ---------------------------------------------------------------------------------------------------
# Tests 4, 5, 6 and 23: from violated records to events (stub runner, hand-written records)
# ---------------------------------------------------------------------------------------------------


def ordered(records: Sequence[VerdictRecord]) -> list[VerdictRecord]:
    """The records in the order of the monitor: by evaluation step (stable)."""
    return sorted(records, key=lambda r: r.t_eval_ms)


def convention_records(
    day: int = 0,
) -> tuple[list[VerdictRecord], CarePlan, set[tuple[Any, ...]]]:
    """One VIOLATED record per kind of phi_CP instance, in the shape of the real monitor, with the plan and
    the events the conventions give."""
    b = day * DAY
    records = [
        violated("range", f"range@{b + T(12)}", b + T(12), b + T(12)),
        violated("hold", f"hold@{b + T(7)}", b + T(7), b + T(7)),
        violated(
            "count", f"count@{b + T(21, 2)}", b + T(21, 2), b + T(21, 2)
        ),  # the limit
        violated("sched", f"sched@{b + T(9)}", b + T(9, 30), b + T(9, 30)),
        violated(
            "resp", f"resp@{b + T(7)}", b + T(10), b + T(10)
        ),  # created at a DISPENSE
        violated(
            "count", f"count@{b + DAY}", b + DAY, b + DAY
        ),  # the day-end obligation
        # these give nothing: a pending, a satisfied and a predicted record
        vr(
            "resp",
            f"resp@{b + T(15)}",
            VerdictState.PENDING,
            b + T(16),
            pending=b + T(18),
        ),
        vr(
            "sched",
            f"sched@{b + T(14)}",
            VerdictState.SATISFIED,
            b + T(14, 5),
            pending=b + T(14, 30),
        ),
        vr(
            "sched",
            f"sched@{b + T(17)}",
            VerdictState.PREDICTED_VIOLATION,
            b + T(17, 20),
            decided=None,
            pending=b + T(17, 30),
        ),
    ]
    plan = make_plan(day, sched=(T(9), T(14), T(17)))
    expected = {
        c1_event("spontaneous_range", "range", b + T(12), None, injected=False),
        c1_event("spontaneous_hold", "hold", b + T(7), None, injected=False),
        c1_event("spontaneous_count", "count", b + T(21, 2), None, injected=False),
        c1_event("spontaneous_sched", "sched", b + T(9), b + T(9, 30), injected=False),
        c1_event("spontaneous_resp", "resp", b + T(7), b + T(10), injected=False),
        c1_event("spontaneous_count", "count", b + DAY, b + DAY, injected=False),
    }
    return ordered(records), plan, expected


def test_violated_records_become_events_with_end_ms_convention() -> None:
    for day in (0, 1, 4):
        records, plan, expected = convention_records(day)
        latent = make_latent(day, measurements=(T(12),))
        out = label(records, latent=latent, plan=plan)
        assert {tup(e) for e in out} == expected
        assert len(out) == len(expected)  # one event per violated instance
        by_template = {(e.template_id, e.end_ms is None) for e in out}
        # RANGE, HOLD and COUNT-limit violations: onset = decided_at_ms, end_ms None
        assert ("range", True) in by_template and ("hold", True) in by_template
        # RESP, SCHED and day-end COUNT: onset = the anchor, end_ms = the deadline pending_until_ms
        assert {("resp", False), ("sched", False)} <= by_template
        for e in out:
            assert e.cls is C1 and e.template_id in {
                "range",
                "hold",
                "count",
                "sched",
                "resp",
            }
            assert e.injected is False and e.confounder_group is None


@pytest.mark.parametrize("template", ["range", "hold", "count"])
@pytest.mark.parametrize("shape", ["none", "same", "later"])
def test_point_templates_have_no_end_whatever_pending_until_says(
    template: str, shape: str
) -> None:
    # the rule is by TEMPLATE KIND: the real monitor sets pending_until_ms on every record (OP-T05-17), a
    # hand-written one may leave it out, and a record whose deadline differs must not become a window
    decided = T(12)
    pending = {"none": None, "same": decided, "later": decided + HOUR}[shape]
    out = label([violated(template, f"{template}@{decided}", decided, pending)])
    [event] = out
    assert (event.onset_ms, event.end_ms) == (decided, None)
    assert event.template_id == template


def test_windowed_templates_need_their_deadline() -> None:
    plan = make_plan(sched=(T(9),))
    for record in (
        violated("sched", f"sched@{T(9)}", T(9, 30), None),
        violated("resp", f"resp@{T(7)}", T(10), None),
        violated("count", f"count@{DAY}", DAY, None),
    ):
        with pytest.raises(RunnerError, match="pending_until_ms"):
            label([record], plan=plan)


def test_sched_onset_is_the_plan_anchor_not_the_decision() -> None:
    plan = make_plan(sched=(T(9, 0, 20),))  # a tick that is not on the monitor grid
    [event] = label(
        [violated("sched", f"sched@{T(9, 0, 20)}", T(9, 31), T(9, 31))], plan=plan
    )
    assert (event.onset_ms, event.end_ms) == (T(9, 0, 20), T(9, 31))


def test_duplicate_records_of_one_instance_give_one_event() -> None:
    plan = make_plan(sched=(T(9),))
    key = f"sched@{T(9)}"
    records = ordered(
        [
            vr("sched", key, VerdictState.PENDING, T(9, 10), pending=T(9, 30)),
            violated("sched", key, T(9, 30), T(9, 30)),
            # the monitor keeps emitting the refinement of a SCHED violation until its horizon
            violated("sched", key, T(9, 30), T(9, 30), t_eval=T(9, 31)),
            violated("sched", key, T(9, 30), T(9, 30), t_eval=T(9, 45)),
            violated("sched", key, T(9, 30), T(9, 30), t_eval=T(10)),
        ]
    )
    out = label(records, plan=plan)
    assert [tup(e) for e in out] == [
        c1_event("spontaneous_sched", "sched", T(9), T(9, 30), injected=False)
    ]
    # two instances (two keys) of one template and one anchor are two events
    twin = ordered(
        [
            violated("resp", f"resp@{T(7)}", T(10), T(10)),
            violated("resp", f"resp@{T(7)}#2", T(10), T(10)),
        ]
    )
    assert len(label(twin)) == 2


def test_the_first_violated_record_defines_the_event_and_the_others_must_agree() -> (
    None
):
    plan = make_plan(sched=(T(9),))
    key = f"sched@{T(9)}"
    first = violated("sched", key, T(9, 30), T(9, 30))
    for bad in (
        violated(
            "sched", key, T(9, 31), T(9, 30), t_eval=T(9, 40)
        ),  # another decision instant
        violated("sched", key, T(9, 30), T(9, 40), t_eval=T(9, 40)),  # another deadline
        vr(
            "sched",
            key,
            VerdictState.SATISFIED,
            T(9, 40),
            decided=T(9, 40),
            pending=T(9, 30),
        ),
        vr("sched", key, VerdictState.PENDING, T(9, 40), pending=T(9, 30)),
        violated(
            "range", key, T(9, 30), T(9, 30), t_eval=T(9, 40)
        ),  # the key of another template
    ):
        with pytest.raises(RunnerError):
            label(ordered([first, bad]), plan=plan)
    # a satisfied instance that later reads violated is incoherent as well
    sat = vr("sched", key, VerdictState.SATISFIED, T(9, 10), pending=T(9, 30))
    with pytest.raises(RunnerError):
        label(ordered([sat, violated("sched", key, T(9, 30), T(9, 30))]), plan=plan)
    # a violated record must say when it was decided, and not after it was evaluated
    for bad in (
        vr(
            "sched",
            key,
            VerdictState.VIOLATED,
            T(9, 30),
            decided=None,
            pending=T(9, 30),
        ),
        violated("sched", key, T(9, 31), T(9, 31), t_eval=T(9, 30)),
    ):
        with pytest.raises(RunnerError):
            label([bad], plan=plan)


def test_only_care_plan_templates_become_c1() -> None:
    records = ordered(
        [
            violated("sys", f"sys@{T(12)}", T(12), T(12)),
            violated("int", f"int@{T(7)}", T(7), T(7)),
            violated("range", f"range@{T(13)}", T(13), T(13)),
        ]
    )
    out = label(records)
    assert [e.template_id for e in out] == ["range"]
    assert label(records[:2]) == ()
    # the labeller does not even run SYS and INT: the library handed to the runner is phi_CP only
    stub = Stub(records)
    label(run_fn=stub)
    [call] = stub.calls
    assert {t.kind for t in call["templates"]} == {TemplateKind.CARE_PLAN}
    assert {t.id for t in call["templates"]} == {
        TemplateId.RANGE,
        TemplateId.SCHED,
        TemplateId.HOLD,
        TemplateId.COUNT,
        TemplateId.RESP,
    }


def test_dynamic_instance_anchor_recovered_from_deadline() -> None:
    # a RESP instance created at a DISPENSE is not in the plan: its deadline pending_until_ms (10:00) minus
    # the window length delta2 of the registry (3 h in F0) is the anchor (07:00)
    assert DELTA2 == 3 * HOUR
    [event] = label([violated("resp", f"resp@{T(7)}", T(10), T(10))])
    assert (event.onset_ms, event.end_ms) == (T(7), T(10))
    # a dispense inside a grid step: the anchor is the grid step, the deadline minus delta2
    [event] = label([violated("resp", f"resp@{T(7, 0, 20)}", T(10, 1), T(10, 1))])
    assert (event.onset_ms, event.end_ms) == (T(7, 1), T(10, 1))
    # decided at the anchor by the registry bounds: decided_at_ms is the anchor, the deadline is later
    [event] = label([violated("resp", f"resp@{T(21)}", T(21), T(24))])
    assert (event.onset_ms, event.end_ms) == (T(21), T(24))
    # the suffix of a second instance changes nothing
    [event] = label([violated("resp", f"resp@{T(7)}#3", T(10), T(10))])
    assert event.onset_ms == T(7)
    # an instance that IS in the plan keeps the plan anchor
    anchored = TemplateInstance(TemplateId.RESP, f"resp@{T(6, 30)}", {}, T(6, 30))
    plan = make_plan(parameter_records=(anchored,))
    [event] = label([violated("resp", f"resp@{T(6, 30)}", T(10), T(10))], plan=plan)
    assert (event.onset_ms, event.end_ms) == (T(6, 30), T(10))
    # the window length is the registry delta2 overlaid by the plan's own parameter record
    record = TemplateInstance(
        TemplateId.RESP, "resp-params", {"delta2": 2 * HOUR}, None
    )
    plan = make_plan(parameter_records=(record,))
    [event] = label([violated("resp", f"resp@{T(8)}", T(10), T(10))], plan=plan)
    assert (event.onset_ms, event.end_ms) == (T(8), T(10))
    # day 1 on the continuing axis
    [event] = label(
        [violated("resp", f"resp@{DAY + T(7)}", DAY + T(10), DAY + T(10))],
        latent=make_latent(1, measurements=(T(12),)),
        plan=make_plan(1),
    )
    assert (event.onset_ms, event.end_ms) == (DAY + T(7), DAY + T(10))


def test_a_window_length_that_the_registry_does_not_have_is_an_error_not_a_number(
    tmp_path: Path,
) -> None:
    # delta2 declared unset (as the real registry declares priority_sys): no number is substituted
    document = yaml.safe_load(F0_PATH.read_text(encoding="utf-8"))
    document["entries"] = [e for e in document["entries"] if e["name"] != "delta2"]
    document["unset"] = [
        {
            "parameter": "delta2",
            "unit": "ms",
            "required_by": ["resp"],
            "note": "fixture: unset",
        }
    ]
    path = tmp_path / "unset_delta2.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    registry = load_registry(path, step_ms=MIN, allow_fixture_only=True)
    config = make_config(registry_version=registry.version())
    # nothing needs delta2 when no windowed RESP instance is violated
    assert label(
        [violated("range", f"range@{T(12)}", T(12), T(12))],
        registry=registry,
        templates=None,
        config=config,
    )
    with pytest.raises(LabellingError, match="delta2"):
        label(
            [violated("resp", f"resp@{T(7)}", T(10), T(10))],
            registry=registry,
            templates=None,
            config=config,
        )


# ---------------------------------------------------------------------------------------------------
# Tests 7, 8, 9: subtype, injected flag, behaviour log and group
# ---------------------------------------------------------------------------------------------------

NOON = T(12)


def spike_record(onset: int = T(11), end: int = T(13), **kw: Any) -> InjectionRecord:
    return c1_record("hypertensive_spike", onset, end, **kw)


def hypo_record(onset: int = T(11), end: int = T(13), **kw: Any) -> InjectionRecord:
    return c1_record("hypotension_below_hold", onset, end, **kw)


def refusal_record(tick: int = NOON, **kw: Any) -> InjectionRecord:
    return c1_record("measurement_refusal", tick, None, **kw)


def double_take_record(second: int = NOON, **kw: Any) -> InjectionRecord:
    return c1_record("double_take", second, None, **kw)


def nonresponse_record(
    intakes: Sequence[int] = (NOON + LAG,),
    onset: int = T(11),
    end: int = T(13),
    **kw: Any,
) -> InjectionRecord:
    details = dict(kw.pop("details", {}))
    details.setdefault("intake_times_ms", list(intakes))
    return c1_record("drug_nonresponse", onset, end, details=details, **kw)


# one event of each template around noon, and the latent day / plan it needs
EVENT_RECORDS: dict[str, VerdictRecord] = {
    "range": violated("range", f"range@{NOON}", NOON, NOON),
    "hold": violated("hold", f"hold@{NOON}", NOON, NOON),
    "count": violated("count", f"count@{NOON}", NOON, NOON),
    "sched": violated("sched", f"sched@{NOON}", T(12, 30), T(12, 30)),
    "resp": violated("resp", f"resp@{NOON}", T(15), T(15)),
}
NOON_LATENT = make_latent(
    measurements=(T(11, 30), NOON), dispenses=(NOON,), ticks=(NOON,)
)
NOON_PLAN = make_plan(sched=(NOON,))
EXPLAINERS: dict[str, Callable[[], InjectionRecord]] = {
    "hypertensive_spike": spike_record,
    "hypotension_below_hold": hypo_record,
    "measurement_refusal": refusal_record,
    "double_take": double_take_record,
    "drug_nonresponse": nonresponse_record,
}


def label_noon(
    template: str,
    injections: Sequence[InjectionRecord],
    behaviour: Sequence[Any] = (),
    **kw: Any,
) -> tuple[GroundTruthEvent, ...]:
    return label(
        [EVENT_RECORDS[template]],
        latent=NOON_LATENT,
        plan=NOON_PLAN,
        injections=injections,
        behaviour=behaviour,
        **kw,
    )


def test_link_table_is_the_task_table() -> None:
    assert dict(LINK_TABLE) == {
        "hypertensive_spike": "range",
        "drug_nonresponse": "resp",
        "hypotension_below_hold": "hold",
        "measurement_refusal": "sched",
        "double_take": "count",
    }
    assert set(LINK_TABLE) == set(
        C1_SUBTYPES
    )  # every C1 subtype that T09 injects has a template
    assert set(LINK_TABLE.values()) <= {t.value for t in TemplateId}


def test_c1_subtype_and_injected_flag_from_explaining_record() -> None:
    for subtype, make in EXPLAINERS.items():
        template = LINK_TABLE[subtype]
        [event] = label_noon(template, [make()])
        assert event.cls is C1 and event.subtype == subtype, subtype
        assert event.injected is True and event.template_id == template
    # no record: the natural subtype `spontaneous_<template id>`, not injected
    for template in EVENT_RECORDS:
        [event] = label_noon(template, [])
        assert (event.subtype, event.injected) == (f"spontaneous_{template}", False)
        assert event.template_id == template


@pytest.mark.parametrize("subtype", sorted(EXPLAINERS))
@pytest.mark.parametrize("template", sorted(EVENT_RECORDS))
def test_a_record_of_another_template_does_not_explain_the_event(
    subtype: str, template: str
) -> None:
    [event] = label_noon(template, [EXPLAINERS[subtype]()])
    if LINK_TABLE[subtype] == template:
        assert (event.subtype, event.injected) == (subtype, True)
    else:  # a spike against COUNT, a refusal against RANGE, ...
        assert (event.subtype, event.injected) == (f"spontaneous_{template}", False)


def test_all_five_records_at_once_pick_the_one_of_the_template() -> None:
    everything = [make() for make in EXPLAINERS.values()]
    for template in EVENT_RECORDS:
        [event] = label_noon(template, everything)
        assert event.subtype == next(s for s, t in LINK_TABLE.items() if t == template)
        assert event.injected is True


def test_window_edges_and_the_latency_bound_of_the_monitor() -> None:
    # the window [11:00, 13:00) is extended by the template latency bound of the monitor
    # (verdict_latency_bound_ms = max_latency + reorder delay: one step, 60000 ms, for RANGE with D = 0)
    def explained(decided: int, **kw: Any) -> bool:
        records = [violated("range", f"range@{decided}", decided, decided)]
        [event] = label(records, injections=[spike_record()], **kw)
        return event.injected

    assert explained(T(11)) is True  # the onset is inside
    assert explained(T(10, 59)) is False  # one step before it is not
    assert explained(T(12, 59)) is True
    assert explained(T(13)) is True  # past the end, inside the extension by one step
    assert explained(T(13, 1)) is False  # the end plus the bound is excluded
    # a larger reorder delay D enlarges the bound the monitor reports (60000 + 30000)
    delayed = make_config(reorder_delay_ms=30 * SEC)
    assert explained(T(13, 1), config=delayed) is True
    assert explained(T(13, 1, 30), config=delayed) is False
    # the bound is the one handed in: a function of the template
    seen: list[TemplateId] = []

    def bound(template: TemplateId) -> int:
        seen.append(template)
        return 10 * MIN

    assert explained(T(13, 9), bound=bound) is True
    assert explained(T(13, 10), bound=bound) is False
    assert set(seen) == {TemplateId.RANGE}
    # the bound of SCHED is the window plus a step: the refusal at the tick explains the violation that
    # is decided one window later, and not the one of the next tick
    plan = make_plan(sched=(NOON, T(12, 30)))
    for tick, flag in ((NOON, True), (T(12, 30), False)):
        record = violated("sched", f"sched@{tick}", tick + 30 * MIN, tick + 30 * MIN)
        [event] = label(
            [record], plan=plan, latent=NOON_LATENT, injections=[refusal_record(NOON)]
        )
        assert event.injected is flag


def test_unrealised_and_foreign_class_records_explain_nothing() -> None:
    [event] = label_noon("range", [spike_record(realised=False)])
    assert (event.subtype, event.injected) == ("spontaneous_range", False)
    for cls in (C2, C3):
        record = other_record(
            cls, "cuff_silent_bias" if cls is C2 else "replay", T(11), T(13)
        )
        out = label_noon("range", [record])
        assert {tup(e)[:2] for e in out} == {
            ("C1", "spontaneous_range"),
            (cls.value, record.spec.subtype),
        }
        [c1] = [e for e in out if e.cls is C1]
        assert c1.injected is False  # a C2 or C3 record never explains a C1 event


def test_a_c1_record_of_an_unknown_subtype_is_refused() -> None:
    with pytest.raises(LabellingError, match="subtype"):
        label_noon("range", [c1_record("surprise_spike", T(11), T(13))])


def test_overlapping_candidates_pick_the_strict_window_then_the_first_onset() -> None:
    # two touching windows: [11:00, 12:00) and [12:00, 13:00); an event decided at 12:00 is inside the
    # second and inside the extension of the first: the strict window wins
    first = spike_record(T(11), T(12), group="g1")
    second = spike_record(T(12), T(13), group="g2")
    [event] = label_noon("range", [first, second])
    assert event.confounder_group == "g2"
    [event] = label_noon("range", [second, first])
    assert event.confounder_group == "g2"  # the order of the records is irrelevant
    # an event only in the extension of the first
    only_ext = violated("range", f"range@{T(12, 0)}", T(12), T(12))
    [event] = label(
        [only_ext], injections=[first, spike_record(T(13), T(14), group="g3")]
    )
    assert event.confounder_group == "g1"
    # two candidates that both contain it strictly: the earlier onset, whatever the order
    wide = spike_record(T(10), T(14), group="wide")
    narrow = spike_record(T(11, 30), T(12, 30), group="narrow")
    for order in ((wide, narrow), (narrow, wide)):
        [event] = label_noon("range", list(order))
        assert event.confounder_group == "wide"


def test_drug_nonresponse_is_linked_through_the_intake_times_not_the_window() -> None:
    # the window [12:00:03, 12:30) starts after the dispense (the resp anchor, 12:00) and before the
    # intake 5 s later: a link of the form "the window contains the anchor" would miss it
    record = nonresponse_record([NOON + LAG], onset=NOON + 3 * SEC, end=T(12, 30))
    assert record.realised_onset_ms > NOON
    [event] = label_noon("resp", [record])
    assert (event.subtype, event.injected) == ("drug_nonresponse", True)
    # the intake of ANOTHER dose in the list: the window contains the anchor, the link does not hold
    elsewhere = nonresponse_record([T(7) + LAG], onset=T(11), end=T(13))
    [event] = label_noon("resp", [elsewhere])
    assert (event.subtype, event.injected) == ("spontaneous_resp", False)
    # a record that lists no intake times cannot be linked: an error, not a guess
    bare = c1_record("drug_nonresponse", T(11), T(13), details={})
    with pytest.raises(LabellingError, match="has no details"):
        label_noon("resp", [bare])
    for bad in ("x", [True], [1.5], [None], 5, {"a": 1}, [-1]):
        broken = c1_record(
            "drug_nonresponse", T(11), T(13), details={"intake_times_ms": bad}
        )
        with pytest.raises(LabellingError, match="intake_times_ms"):
            label_noon("resp", [broken])


def test_double_take_pairs_each_dispense_with_its_own_intake() -> None:
    latent = make_latent(measurements=(T(6), T(12)), dispenses=(T(7), T(7, 2)))
    second = violated("resp", f"resp@{T(7, 2)}", T(10, 2), T(10, 2))
    only_first = nonresponse_record([T(7) + LAG], onset=T(6, 30), end=T(7, 1))
    out = label(
        ordered([violated("resp", f"resp@{T(7)}", T(10), T(10)), second]),
        latent=latent,
        injections=[only_first],
    )
    assert [(e.onset_ms, e.subtype) for e in out] == [
        (T(7), "drug_nonresponse"),
        (T(7, 2), "spontaneous_resp"),
    ]
    # without INTAKE events in the latent day the dispense instant stands in for the intake instant
    bare = make_latent(measurements=(T(6),), dispenses=(NOON,), intakes=False)
    record = nonresponse_record([NOON], onset=T(11), end=T(13))
    [event] = label([EVENT_RECORDS["resp"]], latent=bare, injections=[record])
    assert event.subtype == "drug_nonresponse"


def test_hold_is_explained_by_the_record_that_covers_its_deciding_measurement() -> None:
    # the HOLD violation is decided at the dispense (07:00) but caused by the latest reading (06:50): a
    # hypotension window that covers the reading and ends before the dispense still explains it
    latent = make_latent(measurements=(T(6, 50),), dispenses=(T(7),))
    event_record = violated("hold", f"hold@{T(7)}", T(7), T(7))
    covering = hypo_record(T(6, 40), T(6, 55))
    [event] = label([event_record], latent=latent, injections=[covering])
    assert (event.subtype, event.injected) == ("hypotension_below_hold", True)
    # a later reading outside the window is the deciding one: the record does not explain it
    later = make_latent(measurements=(T(6, 50), T(6, 58)), dispenses=(T(7),))
    [event] = label([event_record], latent=later, injections=[covering])
    assert (event.subtype, event.injected) == ("spontaneous_hold", False)
    # a window that covers neither the reading nor the dispense
    far = hypo_record(T(3), T(4))
    [event] = label([event_record], latent=latent, injections=[far])
    assert event.injected is False


def test_count_limit_is_explained_through_the_24_hour_window_of_the_counter() -> None:
    # a double take at 07:00 (surplus dispense 07:02) violates the limit at the NEXT dispense, 21:00,
    # because the trailing 24 h count is then 3: the surplus lies in the window of the counter
    event_record = violated("count", f"count@{T(21)}", T(21), T(21))
    [event] = label([event_record], injections=[double_take_record(T(7, 2))])
    assert (event.subtype, event.injected) == ("double_take", True)
    # the window is (decision - 24 h, decision]: the surplus exactly 24 h before is out, 1 ms later is in
    at_end = violated(
        "count", f"count@{DAY}#2", DAY, DAY
    )  # the limit instance, not the day-end obligation
    [event] = label([at_end], injections=[double_take_record(0)])
    assert event.injected is False
    [event] = label([at_end], injections=[double_take_record(1)])
    assert event.injected is True
    # a surplus after the decision does not explain it
    [event] = label([event_record], injections=[double_take_record(T(21, 1))])
    assert event.injected is False


def test_adherence_deviations_labelled_from_behaviour_log() -> None:
    omitted = BehaviourEntry(T(7), 0, AdherenceState.OMITTED, ())
    on_time = BehaviourEntry(T(21), 0, AdherenceState.ON_TIME, (T(21),))
    delayed = BehaviourEntry(T(21), 0, AdherenceState.DELAYED, (T(21, 20),))
    double = BehaviourEntry(T(21), 0, AdherenceState.DOUBLE_TAKE, (T(21), T(21, 2)))
    day_end = violated("count", f"count@{DAY}", DAY, DAY)
    limit = violated("count", f"count@{T(21, 2)}", T(21, 2), T(21, 2))
    # an omitted slot gives a day-end COUNT event `dose_omission`, not injected, no group
    [event] = label([day_end], behaviour=[omitted, on_time])
    assert tup(event) == c1_event("dose_omission", "count", DAY, DAY, injected=False)
    # a Markov double take gives `double_take`, not injected
    [event] = label([limit], behaviour=[on_time, double])
    assert tup(event) == c1_event(
        "double_take", "count", T(21, 2), None, injected=False
    )
    # the double take of an earlier slot is inside the 24 h window of a later violation
    early = BehaviourEntry(T(7), 0, AdherenceState.DOUBLE_TAKE, (T(7), T(7, 2)))
    [event] = label(
        [violated("count", f"count@{T(21)}", T(21), T(21))], behaviour=[early]
    )
    assert event.subtype == "double_take" and event.injected is False
    # nothing in the log explains it: the natural subtype
    for entries in ([], [on_time], [delayed], [on_time, delayed]):
        [event] = label([day_end], behaviour=entries)
        assert event.subtype == "spontaneous_count" and event.injected is False
        [event] = label([limit], behaviour=entries)
        assert event.subtype == "spontaneous_count" and event.injected is False
    # an omission does not explain a limit violation and a double take does not explain the day end
    [event] = label([limit], behaviour=[omitted])
    assert event.subtype == "spontaneous_count"
    [event] = label([day_end], behaviour=[double])
    assert event.subtype == "spontaneous_count"
    # entries of another day are not this day's
    other_day = BehaviourEntry(T(7) + DAY, 1, AdherenceState.OMITTED, ())
    [event] = label([day_end], behaviour=[other_day])
    assert event.subtype == "spontaneous_count"
    [event] = label(
        [violated("count", f"count@{2 * DAY}", 2 * DAY, 2 * DAY)],
        latent=make_latent(1, measurements=(T(12),)),
        plan=make_plan(1),
        behaviour=[other_day],
    )
    assert event.subtype == "dose_omission"
    # a forced double take (a confounder record) is an injection: injected True; the log agrees with it
    [event] = label(
        [limit], injections=[double_take_record(T(21, 2))], behaviour=[on_time, double]
    )
    assert tup(event) == c1_event("double_take", "count", T(21, 2), None, injected=True)
    # a forced omission has no record: the log makes it `dose_omission`, still not injected
    [event] = label([day_end], behaviour=[omitted])
    assert (event.subtype, event.injected) == ("dose_omission", False)


def test_behaviour_log_entries_are_validated() -> None:
    day_end = violated("count", f"count@{DAY}", DAY, DAY)
    for bad in (
        ["x"],
        [None],
        [
            BehaviourEntry(T(21), 0, AdherenceState.DOUBLE_TAKE, (T(21),))
        ],  # a double take with one dispense
        [
            BehaviourEntry(T(21), 0, AdherenceState.OMITTED, (T(21),))
        ],  # an omission with a dispense
    ):
        with pytest.raises(LabellingError):
            label([day_end], behaviour=bad)
    with pytest.raises(LabellingError):
        label_latent_day(  # type: ignore[arg-type]
            make_latent(),
            make_plan(),
            [],
            "log",
            Stub(),
            CFG,
            None,
            MODE_SCHEDULED,
            registry=F0,
            templates=LIBRARY,
        )


def test_confounder_group_propagates_from_record() -> None:
    for subtype, make in EXPLAINERS.items():
        template = LINK_TABLE[subtype]
        [with_group] = label_noon(template, [make(group="double_take_vs_bounce")])
        assert with_group.confounder_group == "double_take_vs_bounce", subtype
        [without] = label_noon(template, [make()])
        assert without.confounder_group is None
        [unexplained] = label_noon(template, [])
        assert unexplained.confounder_group is None
    # the group of an unrelated record does not leak onto an unexplained event
    [event] = label_noon("range", [refusal_record(group="refusal_vs_robot_missed")])
    assert event.confounder_group is None
    # a natural double take from the behaviour log has no group
    double = BehaviourEntry(T(21), 0, AdherenceState.DOUBLE_TAKE, (T(21), T(21, 2)))
    [event] = label(
        [violated("count", f"count@{T(21, 2)}", T(21, 2), T(21, 2))], behaviour=[double]
    )
    assert (event.subtype, event.confounder_group) == ("double_take", None)


# ---------------------------------------------------------------------------------------------------
# Tests 10, 11, 12
# ---------------------------------------------------------------------------------------------------


def test_c2_c3_events_are_realised_records_only() -> None:
    realised = [
        other_record(C2, "cuff_silent_bias", T(8), T(10)),
        other_record(
            C2, "dispenser_bounce", T(21, 2), None, group="double_take_vs_bounce"
        ),
        other_record(
            C3, "replay", T(14), T(15), evidence=("crypto_temporal.seq_gap_or_replay",)
        ),
        other_record(
            C3,
            "dispense_forgery",
            T(7),
            None,
            group="nonresponse_vs_falsified_dispense",
        ),
    ]
    unrealised = [
        other_record(C2, "stuck_at", T(11), T(12), realised=False),
        other_record(C3, "injection_naive", T(16), T(17), realised=False),
    ]
    c1_only = [
        spike_record(),
        refusal_record(),
    ]  # realised C1 records that explain nothing here
    out = label([], injections=[*unrealised, *realised, *c1_only])
    expected = [record_to_ground_truth(r) for r in realised]
    assert sorted(map(tup, out)) == sorted(map(tup, expected))  # one to one
    assert all(e.injected is True and e.template_id is None for e in out)
    assert {e.cls for e in out} == {C2, C3}
    # no event for the unrealised records, none for the C1 records (the C1 truth is the latent trace's)
    assert not [e for e in out if e.subtype in ("stuck_at", "injection_naive")]
    assert not [e for e in out if e.cls is C1]
    # the group travels with the event
    assert {(e.subtype, e.confounder_group) for e in out if e.confounder_group} == {
        ("dispenser_bounce", "double_take_vs_bounce"),
        ("dispense_forgery", "nonresponse_vs_falsified_dispense"),
    }
    # a window fault keeps its end, a point fault has none
    by_subtype = {e.subtype: e for e in out}
    assert (
        by_subtype["cuff_silent_bias"].onset_ms,
        by_subtype["cuff_silent_bias"].end_ms,
    ) == (T(8), T(10))
    assert by_subtype["dispenser_bounce"].end_ms is None


def test_a_c1_record_is_never_turned_into_an_injected_event_without_a_template() -> (
    None
):
    # record_to_ground_truth on a C1 record would give injected=True and template_id None: wrong truth
    wrong = record_to_ground_truth(spike_record())
    assert wrong is not None and wrong.template_id is None and wrong.injected is True
    assert (
        label(
            [],
            injections=[
                spike_record(),
                hypo_record(),
                refusal_record(),
                double_take_record(),
            ],
        )
        == ()
    )


def test_ground_truth_sorted_and_deterministic() -> None:
    records = ordered(
        [
            violated("range", f"range@{T(12)}", T(12), T(12)),
            violated("range", f"range@{T(9)}", T(9), T(9)),
            violated("sched", f"sched@{T(9)}", T(9, 30), T(9, 30)),
            violated("hold", f"hold@{T(9)}", T(9), T(9)),
            violated("resp", f"resp@{T(9)}", T(12), T(12)),
        ]
    )
    plan = make_plan(sched=(T(9),))
    injections = [
        other_record(C3, "replay", T(9), T(10)),
        other_record(C2, "cuff_silent_bias", T(9), None),
        other_record(C2, "ble_dropout", T(9), T(9, 30)),
        other_record(C2, "ble_dropout", T(9), T(10)),
        other_record(C2, "stuck_at", T(3), None),
    ]

    def run(
        recs: Sequence[VerdictRecord], inj: Sequence[InjectionRecord]
    ) -> tuple[GroundTruthEvent, ...]:
        return label(recs, plan=plan, injections=inj)

    out = run(records, injections)

    def key(e: GroundTruthEvent) -> tuple[Any, ...]:
        return (
            e.onset_ms,
            e.cls.value,
            e.subtype,
            -1 if e.end_ms is None else e.end_ms,
        )

    assert list(out) == sorted(out, key=key)  # (onset_ms, cls, subtype, end_ms)
    assert len(out) == len(records) + len(injections)
    assert out[0].subtype == "stuck_at" and out[0].onset_ms == T(3)
    # at one onset: C1 before C2 before C3, then the subtype, then the end (None first)
    at_nine = [(e.cls.value, e.subtype, e.end_ms) for e in out if e.onset_ms == T(9)]
    assert at_nine == [
        ("C1", "spontaneous_hold", None),
        ("C1", "spontaneous_range", None),
        ("C1", "spontaneous_resp", T(12)),
        ("C1", "spontaneous_sched", T(9, 30)),
        ("C2", "ble_dropout", T(9, 30)),
        ("C2", "ble_dropout", T(10)),
        ("C2", "cuff_silent_bias", None),
        ("C3", "replay", T(10)),
    ]
    # two runs, and any order of the injection records, give equal tuples
    assert run(records, injections) == out
    assert run(records, list(reversed(injections))) == out
    rotated = injections[2:] + injections[:2]
    assert run(records, rotated) == out
    assert isinstance(out, tuple)
    # events with equal onsets keep a total order: None sorts before an integer end
    same = label(
        [],
        injections=[
            other_record(C2, "ble_dropout", T(9), T(10)),
            other_record(C2, "ble_dropout", T(9), None),
        ],
    )
    assert [e.end_ms for e in same] == [None, T(10)]


def test_registry_version_mismatch_raises() -> None:
    stub = Stub()
    plan = make_plan(registry_version="9.9.9")
    with pytest.raises(RegistryMismatchError, match="9.9.9") as info:
        label(run_fn=stub, plan=plan)
    assert F0.version() in str(info.value)
    assert stub.calls == []  # nothing ran on a plan of another registry
    # the configuration against the loaded registry
    with pytest.raises(RegistryMismatchError):
        label(
            run_fn=stub,
            config=make_config(registry_version="1.2.3"),
            plan=make_plan(registry_version="1.2.3"),
        )
    # a patch bump is a mismatch too: no compatible range is defined (ADR-047 (h))
    with pytest.raises(RegistryMismatchError):
        label(run_fn=stub, plan=make_plan(registry_version="0.0.1"))
    assert stub.calls == []
    # the matching version runs
    label(run_fn=stub)
    assert len(stub.calls) == 1
    # the step of the configuration is the step of the registry
    with pytest.raises(LabellingError, match="step"):
        label(run_fn=stub, config=make_config(step_ms=30 * SEC))
    # RegistryMismatchError is a LabellingError
    assert issubclass(RegistryMismatchError, LabellingError)
    assert issubclass(IdealObservationError, LabellingError)
    assert issubclass(RunnerError, LabellingError)


# ---------------------------------------------------------------------------------------------------
# The runner is an argument: what it may and may not return
# ---------------------------------------------------------------------------------------------------


def test_the_default_runner_is_run_offline_without_calibrator_and_forecaster() -> None:
    sig = inspect.signature(label_latent_day)
    assert sig.parameters["run_fn"].default is None
    # a runner is called as run_offline is: (day, plan, config, calibrator, forecaster) plus the registry
    # and the phi_CP library by keyword
    stub = Stub()
    label(run_fn=stub)
    [call] = stub.calls
    assert call["calibrator"] is None and call["forecaster"] is None
    assert call["config"] == CFG
    assert call["registry"] is F0
    assert isinstance(call["day"], ObservedDay) and call["plan"].care_plan_id == PLAN_ID
    # `run_offline_detailed` is a runner too: its records are read
    out = label_latent_day(
        make_latent(measurements=(T(12),), dispenses=(T(7),)),
        make_plan(),
        [],
        [],
        run_offline_detailed,
        CFG,
        None,
        MODE_SCHEDULED,
        registry=F0,
        templates=LIBRARY,
    )
    assert {e.template_id for e in out} >= {
        "hold"
    }  # no reading before the dose: HOLD fails its guard


@pytest.mark.parametrize(
    "garbage",
    [
        None,
        5,
        "records",
        b"x",
        {"a": 1},
        object(),
        iter(()),
        (x for x in ()),
        1.5,
        True,
    ],
)
def test_a_runner_that_returns_garbage_is_a_named_error(garbage: Any) -> None:
    with pytest.raises(RunnerError):
        label(run_fn=lambda *a, **k: garbage)


def test_a_runner_that_returns_bad_records_is_a_named_error() -> None:
    good = violated("range", f"range@{T(12)}", T(12), T(12))
    plan = make_plan(sched=(T(9),))
    bad_lists: list[list[Any]] = [
        [good, "not a record"],
        [good, None],
        [good, good.instance_key],
        [violated("range", f"range@{T(13)}", T(13), T(13)), good],  # not in step order
        [
            violated("range", f"range@{DAY + T(12)}", DAY + T(12), DAY + T(12))
        ],  # a record of day 1
        [
            vr("resp", f"resp@{T(3)}", VerdictState.PENDING, -MIN, pending=T(6))
        ],  # before the day
        [
            violated("sched", f"sched@{T(15)}", T(15, 30), T(15, 30))
        ],  # an instance the plan does not have
        [
            vr(
                "sched",
                f"sched@{T(15)}",
                VerdictState.PENDING,
                T(15, 10),
                pending=T(15, 30),
            )
        ],
    ]
    for records in bad_lists:
        with pytest.raises(RunnerError):
            label(records, plan=plan)
    # fields of the wrong type (a record built around the validation of the dataclass)
    for field_name, junk in (
        ("template", "range"),
        ("template", None),
        ("state", "violated"),
        ("state", None),
        ("t_eval_ms", True),
        ("t_eval_ms", 1.5),
        ("t_eval_ms", None),
        ("t_eval_ms", 10**400),
        ("instance_key", ""),
        ("instance_key", None),
        ("instance_key", 5),
        ("decided_at_ms", True),
        ("decided_at_ms", 1.5),
        ("decided_at_ms", 10**30),
        ("pending_until_ms", True),
        ("pending_until_ms", "x"),
        ("pending_until_ms", -1),
    ):
        broken = clone_with(good, **{field_name: junk})
        with pytest.raises(RunnerError):
            label([broken], plan=plan)
    # a record of day 0 handed for day 1 and the reverse
    with pytest.raises(RunnerError):
        label([good], latent=make_latent(1, measurements=(T(12),)), plan=make_plan(1))


def test_a_runner_that_raises_is_wrapped_with_its_cause() -> None:
    for exc in (
        ValueError("boom"),
        KeyError("k"),
        RuntimeError("r"),
        ZeroDivisionError(),
        OverflowError(),
        TypeError("t"),
    ):

        def run_fn(*a: Any, _exc: Exception = exc, **k: Any) -> Any:
            raise _exc

        with pytest.raises(RunnerError) as info:
            label(run_fn=run_fn)
        assert info.value.__cause__ is exc
        assert named(info.value)
    # the monitor's own named errors are wrapped as well, not re-raised as they are
    from ralmon.monitor import MonitorConfigError, MonitorInputError

    for monitor_error in (MonitorConfigError("c"), MonitorInputError("i")):

        def failing(*a: Any, _e: Exception = monitor_error, **k: Any) -> Any:
            raise _e

        with pytest.raises(RunnerError) as info:
            label(run_fn=failing)
        assert info.value.__cause__ is monitor_error
    # a non-callable runner
    for bad in (5, "run", object(), [Stub()]):
        with pytest.raises(LabellingError, match="callable"):
            label(run_fn=bad)  # type: ignore[arg-type]


def test_a_runner_that_never_stops_is_not_waited_for_beyond_its_own_return(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # bounded sizes: the labeller refuses more records than its named bound
    monkeypatch.setattr(labelling, "MAX_VERDICT_RECORDS", 3)
    many = ordered(
        [
            violated(
                "range", f"range@{T(12) + i * MIN}", T(12) + i * MIN, T(12) + i * MIN
            )
            for i in range(4)
        ]
    )
    with pytest.raises(RunnerError, match="records"):
        label(many)
    assert len(label(many[:3])) == 3


def test_sys_and_int_records_are_not_validated_beyond_their_shape() -> None:
    # SYS and INT are not phi_CP: their keys need not be in the plan and their records do not matter
    records = ordered(
        [
            vr("sys", f"sys@{T(12)}", VerdictState.PENDING, T(12), pending=T(12)),
            violated("int", f"int@{T(7)}", T(7), T(7)),
        ]
    )
    assert label(records) == ()


# --- the constants are named and documented ----------------------------------------------------------


def test_bounds_are_named_constants_with_a_reason() -> None:
    source = (SRC / "labelling.py").read_text(encoding="utf-8")
    names = [
        n
        for n in dir(labelling)
        if n.startswith("MAX_")
        and isinstance(getattr(labelling, n), int)
        and not isinstance(getattr(labelling, n), bool)
    ]
    assert {
        "MAX_VERDICT_RECORDS",
        "MAX_INJECTION_RECORDS",
        "MAX_BEHAVIOUR_ENTRIES",
    } <= set(names)
    lines = source.splitlines()
    for name in names:
        defining = [i for i, line in enumerate(lines) if re.match(rf"^{name}\b", line)]
        assert defining, name
        # the definition (up to the wrapped value) says "# algorithmic: <reason>"
        window = " ".join(
            lines[defining[0] : defining[0] + 4]
        )  # the value may be wrapped by the formatter
        assert re.search(r"#\s*algorithmic:\s*\S", window), name


def test_too_many_items_are_refused_before_any_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(labelling, "MAX_INJECTION_RECORDS", 2)
    monkeypatch.setattr(labelling, "MAX_BEHAVIOUR_ENTRIES", 2)
    records = [other_record(C2, "ble_dropout", T(h), T(h, 30)) for h in (1, 2, 3)]
    with pytest.raises(LabellingError, match="injection"):
        label([], injections=records)
    entries = [
        BehaviourEntry(T(h), 0, AdherenceState.ON_TIME, (T(h),)) for h in (1, 2, 3)
    ]
    with pytest.raises(LabellingError, match="behaviour"):
        label([], behaviour=entries)
    assert len(label([], injections=records[:2])) == 2


# ---------------------------------------------------------------------------------------------------
# Robustness: only the module's named errors, whatever the argument
# ---------------------------------------------------------------------------------------------------


class Boom:
    """An object that raises from every hook a careless implementation might touch."""

    def _boom(self, *a: Any, **k: Any) -> Any:
        raise RuntimeError("hostile object touched")

    __repr__ = __str__ = __eq__ = __ne__ = __hash__ = __iter__ = __len__ = _boom  # type: ignore[assignment]
    __bool__ = __int__ = __float__ = __index__ = __lt__ = __gt__ = __contains__ = _boom  # type: ignore[assignment]
    __getitem__ = __call__ = __getattr__ = _boom  # type: ignore[assignment]


class BoomList(list):  # type: ignore[type-arg]
    def _boom(self, *a: Any, **k: Any) -> Any:
        raise RuntimeError("hostile list touched")

    __iter__ = __len__ = __getitem__ = __eq__ = __hash__ = __repr__ = _boom  # type: ignore[assignment]


class BoomStr(str):
    def _boom(self, *a: Any, **k: Any) -> Any:
        raise RuntimeError("hostile str touched")

    __eq__ = __hash__ = __repr__ = __len__ = __iter__ = __getitem__ = _boom  # type: ignore[assignment]


class BoomInt(int):
    def _boom(self, *a: Any, **k: Any) -> Any:
        raise RuntimeError("hostile int touched")

    __eq__ = __hash__ = __lt__ = __gt__ = __le__ = __ge__ = __index__ = __repr__ = (
        __add__
    ) = __sub__ = _boom  # type: ignore[assignment]


class BoomFloat(float):
    def _boom(self, *a: Any, **k: Any) -> Any:
        raise RuntimeError("hostile float touched")

    __eq__ = __hash__ = __lt__ = __gt__ = __le__ = __ge__ = __repr__ = __add__ = (
        __sub__
    ) = __float__ = _boom  # type: ignore[assignment]


class GrowingList(list):  # type: ignore[type-arg]
    """A list that claims to be enormous (the bound must be checked from its length, before iterating)."""

    def __len__(self) -> int:
        return 10**12


JUNK: tuple[Any, ...] = (
    None,
    True,
    False,
    0,
    -1,
    1,
    2**63,
    10**400,
    -(10**400),
    1.5,
    math.nan,
    math.inf,
    -math.inf,
    "",
    "x",
    "scheduled",
    b"x",
    [],
    (),
    {},
    set(),
    [None],
    [[]],
    {"a": 1},
    object(),
    np.float64(1.0),
    np.int64(3),
    np.array([1.0]),
    Boom(),
    BoomList([1]),
    BoomStr("x"),
    BoomInt(3),
    BoomFloat(1.5),
    GrowingList(),
    lambda: 1,
    float,
)


def clone_with(obj: Any, **changes: Any) -> Any:
    """A copy of a (frozen, slotted) dataclass with fields replaced, bypassing ``__post_init__``."""
    new = object.__new__(type(obj))
    for f in dataclasses.fields(obj):
        object.__setattr__(
            new, f.name, changes[f.name] if f.name in changes else getattr(obj, f.name)
        )
    return new


SMALL_LATENT = make_latent(
    measurements=(T(6), T(12)), dispenses=(T(7),), ticks=(T(6), T(12)), grid_ms=HOUR
)
SMALL_PLAN = make_plan(sched=(T(6), T(12)))
SMALL_RECORDS = ordered(
    [
        violated("range", f"range@{T(12)}", T(12), T(12)),
        violated("sched", f"sched@{T(6)}", T(6, 30), T(6, 30)),
        violated("resp", f"resp@{T(7)}", T(10), T(10)),
        violated("count", f"count@{DAY}", DAY, DAY),
    ]
)
SMALL_INJECTIONS = [
    spike_record(),
    nonresponse_record([T(7) + LAG], T(6), T(8)),
    other_record(C2, "ble_dropout", T(1), T(2)),
]
SMALL_BEHAVIOUR = [BehaviourEntry(T(7), 0, AdherenceState.OMITTED, ())]


def allowed(call: Callable[[], Any]) -> None:
    """The call returns, or raises a named error of the module: nothing else."""
    try:
        call()
    except LabellingError as exc:
        assert named(exc), type(exc)
    except MemoryError:
        raise
    except Exception as exc:  # noqa: BLE001 - a raw TypeError, KeyError, AttributeError, OverflowError, ValueError ...
        pytest.fail(f"raw {type(exc).__name__} escaped: {str(exc)[:80]!r}")


def entry_calls() -> list[tuple[str, Callable[..., Any], list[Any], dict[str, Any]]]:
    """(name, function, positional arguments, keyword arguments) of every public entry point."""
    observed = ideal_observation(SMALL_LATENT, PLAN_ID)
    stub = Stub(SMALL_RECORDS)
    label_args = [
        SMALL_LATENT,
        SMALL_PLAN,
        SMALL_INJECTIONS,
        SMALL_BEHAVIOUR,
        stub,
        CFG,
        None,
        MODE_SCHEDULED,
    ]
    label_kw = {"registry": F0, "templates": LIBRARY}
    return [
        (
            "ideal_observation",
            ideal_observation,
            [SMALL_LATENT, PLAN_ID, MODE_SCHEDULED],
            {"step_ms": MIN, "signals": ("bp", "meas", "dispense", "day_end")},
        ),
        ("label_latent_day", label_latent_day, list(label_args), dict(label_kw)),
        (
            "label_latent_day_detailed",
            label_latent_day_detailed,
            list(label_args),
            dict(label_kw),
        ),
        (
            "assemble_benchmark_day",
            assemble_benchmark_day,
            [
                observed,
                SMALL_LATENT,
                SMALL_PLAN,
                SMALL_INJECTIONS,
                SMALL_BEHAVIOUR,
                stub,
                CFG,
                None,
                MODE_SCHEDULED,
            ],
            dict(label_kw),
        ),
    ]


def test_the_baseline_calls_of_the_fuzz_succeed() -> None:
    for _name, function, args, kw in entry_calls():
        function(*args, **kw)  # a baseline that fails would make the fuzz vacuous


def test_every_public_entry_raises_only_named_errors_for_junk_arguments() -> None:
    for _name, function, args, kw in entry_calls():
        for position in range(len(args)):
            for junk in JUNK:
                changed = list(args)
                changed[position] = junk
                allowed(lambda f=function, c=changed, k=kw: f(*c, **k))
        for keyword in kw:
            for junk in JUNK:
                changed_kw = dict(kw)
                changed_kw[keyword] = junk
                allowed(lambda f=function, a=args, k=changed_kw: f(*a, **k))
        # an unknown keyword or a missing argument is a TypeError of the language, not of the module
        with pytest.raises(TypeError):
            function(*args[:0])


def _field_junk() -> tuple[Any, ...]:
    return (
        None,
        True,
        "x",
        1.5,
        math.nan,
        10**400,
        -1,
        [],
        Boom(),
        BoomInt(3),
        BoomStr("x"),
        BoomFloat(2.0),
    )


def test_every_field_of_every_input_object_raises_only_named_errors() -> None:
    latent = SMALL_LATENT
    sample0, event0 = latent.samples[0], latent.events[0]
    plan = SMALL_PLAN
    instance0 = plan.instances[0]
    injection0 = SMALL_INJECTIONS[1]
    behaviour0 = SMALL_BEHAVIOUR[0]
    record0 = SMALL_RECORDS[0]

    def run(position: int, replacement: Any) -> None:
        args: list[Any] = [
            latent,
            plan,
            list(SMALL_INJECTIONS),
            list(SMALL_BEHAVIOUR),
            Stub(SMALL_RECORDS),
            CFG,
            None,
            MODE_SCHEDULED,
        ]
        args[position] = replacement
        allowed(lambda: label_latent_day(*args, registry=F0, templates=LIBRARY))
        observed = ideal_observation(latent, PLAN_ID)
        allowed(
            lambda: assemble_benchmark_day(
                observed if position != 0 else args[0],
                args[0],
                args[1],
                args[2],
                args[3],
                args[4],
                args[5],
                args[6],
                args[7],
                registry=F0,
                templates=LIBRARY,
            )
        )

    for junk in _field_junk():
        for f in dataclasses.fields(latent):
            run(0, clone_with(latent, **{f.name: junk}))
        for f in dataclasses.fields(sample0):
            run(
                0,
                clone_with(
                    latent,
                    samples=(
                        clone_with(sample0, **{f.name: junk}),
                        *latent.samples[1:],
                    ),
                ),
            )
        for f in dataclasses.fields(event0):
            run(
                0,
                clone_with(
                    latent,
                    events=(clone_with(event0, **{f.name: junk}), *latent.events[1:]),
                ),
            )
        for f in dataclasses.fields(plan):
            run(1, clone_with(plan, **{f.name: junk}))
        for f in dataclasses.fields(instance0):
            run(
                1,
                clone_with(
                    plan,
                    instances=(
                        clone_with(instance0, **{f.name: junk}),
                        *plan.instances[1:],
                    ),
                ),
            )
        for f in dataclasses.fields(injection0):
            run(2, [clone_with(injection0, **{f.name: junk})])
        for f in dataclasses.fields(injection0.spec):
            run(
                2,
                [
                    clone_with(
                        injection0, spec=clone_with(injection0.spec, **{f.name: junk})
                    )
                ],
            )
        for f in dataclasses.fields(behaviour0):
            run(3, [clone_with(behaviour0, **{f.name: junk})])
        for f in dataclasses.fields(CFG):
            run(5, clone_with(CFG, **{f.name: junk}))
        for f in dataclasses.fields(record0):
            run(4, Stub([clone_with(record0, **{f.name: junk}), *SMALL_RECORDS[1:]]))


# ---------------------------------------------------------------------------------------------------
# The real monitor on hand-written cases: hand calculation, reference evaluator and labeller agree
# ---------------------------------------------------------------------------------------------------


def load_cases() -> list[dict[str, Any]]:
    document = yaml.safe_load(CASES_PATH.read_text(encoding="utf-8"))
    return list(document["cases"])


CASES = load_cases()
CASE_IDS = [c["id"] for c in CASES]
DAYS = (0, 1)


def case_bp(case: Mapping[str, Any]) -> Callable[[int], float]:
    segments = [(clock(a), clock(b), float(v)) for a, b, v in case["bp_segments"]]
    default = float(case["bp_default"])

    def bp(t: int) -> float:
        for lo, hi, value in segments:
            if lo <= t < hi:
                return value
        return default

    return bp


def case_latent(case: Mapping[str, Any], day: int) -> LatentDay:
    return make_latent(
        day,
        bp=case_bp(case),
        measurements=[clock(x) for x in case["measurements"]],
        dispenses=[clock(x) for x in case["dispenses"]],
        ticks=[clock(x) for x in case["sched_ticks"]],
    )


def case_plan(case: Mapping[str, Any], day: int) -> CarePlan:
    return make_plan(
        day,
        sched=[clock(x) for x in case["sched_ticks"]],
        count_end=bool(case["count_end"]),
    )


def case_expected(
    case: Mapping[str, Any], day: int
) -> list[tuple[str, int, int | None]]:
    return sorted(
        (
            e["template"],
            clock(e["onset"], day),
            None if e["end"] is None else clock(e["end"], day),
        )
        for e in case["expected"]
    )


def truth_of(
    latent: LatentDay,
    plan: CarePlan,
    injections: Sequence[Any] = (),
    behaviour: Sequence[Any] = (),
    mode: str = MODE_SCHEDULED,
    **kw: Any,
) -> tuple[GroundTruthEvent, ...]:
    """The labeller with the real monitor (the default runner) on the F0 registry."""
    kw.setdefault("registry", F0)
    kw.setdefault("templates", LIBRARY)
    return label_latent_day(
        latent, plan, list(injections), list(behaviour), None, CFG, None, mode, **kw
    )


def c1_set(events: Sequence[GroundTruthEvent]) -> list[tuple[str | None, int]]:
    """The C1 truth as a set of (template, anchor) pairs (sorted list: multiplicity is kept)."""
    return sorted((e.template_id, e.onset_ms) for e in events if e.cls is C1)  # type: ignore[type-var]


def monitor_violation_set(
    records: Sequence[VerdictRecord], plan: CarePlan
) -> list[tuple[str, int]]:
    """The (template, anchor) pairs of the VIOLATED phi_CP verdicts of a monitor run, deduplicated by
    instance key at the first VIOLATED record: written here, from the record fields only, with the
    anchor conventions of the specification (not the labeller's code)."""
    cp = {"range", "sched", "hold", "count", "resp"}
    first: dict[str, VerdictRecord] = {}
    for r in records:
        if r.state is VerdictState.VIOLATED and r.template.value in cp:
            first.setdefault(r.instance_key, r)
    sched_anchor = {
        i.instance_key: i.anchor_ms
        for i in plan.instances
        if i.template is TemplateId.SCHED
    }
    day_end = {
        i.instance_key
        for i in plan.instances
        if i.template is TemplateId.COUNT and i.anchor_ms is not None
    }
    found: list[tuple[str, int]] = []
    for key, r in first.items():
        name = r.template.value
        assert r.decided_at_ms is not None and r.pending_until_ms is not None
        if name == "sched":
            anchor = sched_anchor[key]
            assert anchor is not None
        elif name == "resp":
            anchor = (
                r.pending_until_ms - DELTA2
            )  # the dispense step: deadline minus the window
        elif key in day_end:
            anchor = r.pending_until_ms
        else:
            anchor = r.decided_at_ms
        found.append((name, anchor))
    return sorted(found)


def perfect_observation(
    case: Mapping[str, Any], day: int, *, bias: float = 0.0
) -> ObservedDay:
    """The perfect observation of a hand case, built here from the case data and not from the latent day:
    exact pressure at the measurement instants (plus ``bias``), the dispenses, the ticks, no noise."""
    f = case_bp(case)
    b = day * DAY
    samples = [
        Sample("bp", b + clock(x), b + clock(x), f(clock(x)) + bias, None, None)
        for x in case["measurements"]
    ]
    samples.append(Sample("day_end", b + DAY, b + DAY, 1.0, None, None))
    events = [
        Event(EventKind.MEASUREMENT, b + clock(x), b + clock(x), "cuff", {}, None)
        for x in case["measurements"]
    ]
    events += [
        Event(EventKind.DISPENSE, b + clock(x), b + clock(x), "dispenser", {}, None)
        for x in case["dispenses"]
    ]
    events += [
        Event(
            EventKind.SCHEDULE_TICK,
            b + clock(x),
            b + clock(x),
            "ward",
            {"kind": "measurement"},
            None,
        )
        for x in case["sched_ticks"]
    ]
    samples.sort(key=lambda s: s.t_rx_ms)
    events.sort(key=lambda e: e.t_rx_ms)
    return ObservedDay(PATIENT, day, 0, tuple(samples), tuple(events), PLAN_ID)


def run_monitor(observed: ObservedDay, plan: CarePlan) -> tuple[VerdictRecord, ...]:
    """The whole seven-template library on an observed day (SYS and INT included)."""
    return tuple(
        run_offline(observed, plan, CFG, None, None, registry=F0, templates=LIBRARY)
    )


def reference_set(case: Mapping[str, Any], day: int) -> list[RefViolation]:
    b = day * DAY
    f = case_bp(case)
    return reference_evaluate(
        REF_PARAMS,
        step_ms=MIN,
        origin_ms=b,
        measurements=[b + clock(x) for x in case["measurements"]],
        bp_samples=[(b + clock(x), f(clock(x))) for x in case["measurements"]],
        dispenses=[b + clock(x) for x in case["dispenses"]],
        sched_ticks=[b + clock(x) for x in case["sched_ticks"]],
        count_end=bool(case["count_end"]),
    )


@pytest.mark.parametrize("day", DAYS)
@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_hand_computed_cases_label_as_computed_by_hand(
    case: Mapping[str, Any], day: int
) -> None:
    latent, plan = case_latent(case, day), case_plan(case, day)
    truth = truth_of(latent, plan)
    got = sorted((e.template_id, e.onset_ms, e.end_ms) for e in truth)  # type: ignore[type-var]
    assert got == case_expected(case, day), case["why"]
    assert all(
        e.cls is C1 and e.injected is False and e.confounder_group is None
        for e in truth
    )
    assert all(e.subtype == f"spontaneous_{e.template_id}" for e in truth)
    # the independent reference evaluator gives the same instances, anchors and deadlines
    reference = sorted(
        (v.template, v.anchor_ms, v.end_ms) for v in reference_set(case, day)
    )
    assert reference == got


# ---------------------------------------------------------------------------------------------------
# Tests 13 to 20: the non-circularity tests
# ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("day", DAYS)
@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_perfect_observation_equals_ground_truth_on_c1(
    case: Mapping[str, Any], day: int
) -> None:
    latent, plan = case_latent(case, day), case_plan(case, day)
    truth = truth_of(latent, plan)
    # the monitor on an observed day with zero cuff error, no fault, no attack, measurements at the
    # ticks: the observation is built from the case data, independently of the labeller
    observed = perfect_observation(case, day)
    records = run_monitor(observed, plan)
    monitored = monitor_violation_set(records, plan)
    assert monitored == c1_set(
        truth
    )  # as sets of (template, anchor), multiplicity included
    assert monitored == sorted(
        (t, clock(e["onset"], day)) for e in case["expected"] for t in [e["template"]]
    )
    # and the ideal observation of the labeller is that same perfect observation
    ideal = ideal_observation(latent, PLAN_ID)
    assert [(s.signal, s.t_device_ms, s.value) for s in ideal.samples] == [
        (s.signal, s.t_device_ms, s.value) for s in observed.samples
    ]
    assert sorted((e.kind.value, e.t_device_ms) for e in ideal.events) == sorted(
        (e.kind.value, e.t_device_ms) for e in observed.events
    )


# --- the measurement process of the benchmark (WS04-T06) and the C1 assembly (WS04-T09) --------------

HR_VALUES = [70.0 + i % 30 for i in range(DAY // MIN)]  # FIXTURE-ONLY
SPO2_VALUES = [95.0 + i % 4 for i in range(DAY // MIN)]  # FIXTURE-ONLY
SEGMENTS = SegmentLibrary.from_memory(
    [
        InlineSegment("hr-1", "hr_clean", HR_VALUES, MIN, "bpm"),
        InlineSegment("sp-1", "spo2_clean", SPO2_VALUES, MIN, "%"),
    ]
)
DESIGN = MeasurementDesign(
    inflation_ms_nominal=30 * SEC,
    inflation_ms_sd=0,
    pulse_error_sd_bpm=0.0,
    robot_dwell_ms=10 * MIN,
    vitals_period_ms=MIN,
    inflation_min_ms=30 * SEC,
)
PERFECT_ADHERENCE = AdherenceModel(
    AdherenceParams(0.0, 0.0, 0.0, 10 * MIN),
    AdherenceConfig(intake_lag_ms=LAG, double_take_gap_ms=2 * MIN),
)
SEED = 7
PATIENT_INDEX = 3
ZERO_ERRORS = DeviceErrorModel(0.0, 0.0, 0.0, 0.0)
NOISY_ERRORS = DeviceErrorModel(
    4.0, 1.0, 0.0, 0.0
)  # FIXTURE-ONLY cuff error SD 4, bias 1


def make_patient(
    *,
    baseline: float = 130.0,
    amplitude: float = 0.0,
    sd: float = 0.0,
    phi: float = 0.0,
    emax: float = 20.0,
    ec50: float = 0.25,
    ka: float = 2.0,
    ke: float = 1.0,
) -> PatientParams:
    return PatientParams(
        PATIENT, baseline, amplitude, sd, phi, emax, ec50, ka, ke, (HOUR, 2 * HOUR)
    )


def assembly_config(adherence: AdherenceModel = PERFECT_ADHERENCE) -> AssemblyConfig:
    return AssemblyConfig(
        latent_step_ms=MIN,
        circadian_peak_clock_ms=14 * HOUR,
        ar_reference_step_ms=MIN,
        adherence=adherence,
        vitals=DESIGN,
    )


def assemble(
    patient: PatientParams,
    schedule: Schedule,
    specs: Sequence[InjectionSpec] = (),
    *,
    adherence: AdherenceModel = PERFECT_ADHERENCE,
    forced: Sequence[ForcedSlot] = (),
    seed: int = SEED,
    index: int = PATIENT_INDEX,
) -> LatentResult:
    return assemble_latent_days(
        patient,
        schedule,
        1,
        list(specs),
        OneCompartmentEmax(),
        SEGMENTS,
        seed,
        index,
        config=assembly_config(adherence),
        forced_slots=forced,
    )[0]


def observed_stream(
    result: LatentResult,
    schedule: Schedule,
    errors: DeviceErrorModel,
    *,
    seed: int = SEED,
) -> Any:
    return build_observed_base(
        result.latent,
        schedule,
        PLAN_ID,
        errors,
        DESIGN,
        NoJitter(),
        SEGMENTS,
        seed,
        PATIENT_INDEX,
        skip_measurement_ticks_ms=result.refused_ticks_ms,
    )


def plan_for(schedule: Schedule, *, count_end: bool = False, day: int = 0) -> CarePlan:
    return make_plan(day, sched=schedule.measurement_ticks_ms, count_end=count_end)


NOON_ONLY = Schedule(dose_ticks_ms=(), measurement_ticks_ms=(NOON,))


def test_noisy_observation_diverges_from_ground_truth() -> None:
    plan = plan_for(NOON_ONLY)

    def rows(
        baseline: float, bias: float
    ) -> tuple[list[tuple[str | None, int]], list[tuple[str, int]]]:
        result = assemble(make_patient(baseline=baseline), NOON_ONLY)
        truth = c1_set(
            truth_of(result.latent, plan, result.c1_records, result.behaviour_log)
        )
        stream = observed_stream(
            result, NOON_ONLY, DeviceErrorModel(0.0, bias, 0.0, 0.0)
        )
        monitored = monitor_violation_set(
            run_monitor(finalize_observed(stream), plan), plan
        )
        return truth, monitored

    # false positive: latent 139 (inside the band, sigma = 140 - 139 = +1) with a cuff bias of +3 reads 142
    # (sigma = 140 - 142 = -2): the monitor flags a range violation that the truth lacks
    truth, monitored = rows(139.0, 3.0)
    assert truth == []
    assert [name for name, _ in monitored] == ["range"]
    # false negative: latent 141 (sigma = 140 - 141 = -1, a true violation) with a bias of -3 reads 138
    # (sigma = 138 - 110 = 28 and 140 - 138 = 2, so +2): the truth has the event, the monitor misses it
    truth, monitored = rows(141.0, -3.0)
    assert [name for name, _ in truth] == ["range"]
    assert monitored == []
    # the same latent days with a perfect cuff agree (the divergence is the observation's)
    for baseline, expect in ((139.0, []), (141.0, ["range"])):
        truth, monitored = rows(baseline, 0.0)
        assert [name for name, _ in truth] == expect and [
            name for name, _ in monitored
        ] == expect
    # the limits of the band: 140 is a tie (satisfied) and 141 is not
    assert rows(140.0, 0.0)[0] == []


def test_c1_truth_follows_latent_not_injection_intent() -> None:
    schedule = Schedule(dose_ticks_ms=(), measurement_ticks_ms=(NOON,))
    plan = plan_for(schedule)
    patient = make_patient(baseline=130.0)
    # a spike of 5 mmHg around the 12:00 measurement keeps it inside the band (135 <= 140)
    mild = assemble(
        patient,
        schedule,
        [c1_spec("hypertensive_spike", T(11), duration_ms=2 * HOUR, magnitude=5.0)],
    )
    [record] = mild.c1_records
    assert (
        record.realised and record.n_changed == 120
    )  # the injection happened and is in the log
    assert [
        v
        for t, v in (
            (s.t_device_ms, s.value) for s in mild.latent.samples if s.signal == "bp"
        )
        if t == NOON
    ] == [135.0]
    assert truth_of(mild.latent, plan, mild.c1_records, mild.behaviour_log) == ()
    # a spike of 20 mmHg crosses the band edge (150): one hypertensive_spike event, injected
    big = assemble(
        patient,
        schedule,
        [c1_spec("hypertensive_spike", T(11), duration_ms=2 * HOUR, magnitude=20.0)],
    )
    [event] = truth_of(big.latent, plan, big.c1_records, big.behaviour_log)
    assert tup(event) == c1_event(
        "hypertensive_spike", "range", NOON, None, injected=True
    )
    # the record is the same kind of record in both: the truth did not read the injection log's intent
    assert big.c1_records[0].spec.subtype == mild.c1_records[0].spec.subtype
    # a record placed away from every measurement yields no event, and an event no record explains stays natural
    away = assemble(
        patient,
        schedule,
        [c1_spec("hypertensive_spike", T(1), duration_ms=HOUR, magnitude=60.0)],
    )
    assert away.c1_records[0].realised
    assert truth_of(away.latent, plan, away.c1_records, away.behaviour_log) == ()
    [natural] = truth_of(big.latent, plan, [], big.behaviour_log)
    assert (natural.subtype, natural.injected) == ("spontaneous_range", False)


# --- test 16: three corruptions of one latent day, one set of C1 events ------------------------------

SCHED_16 = Schedule(
    dose_ticks_ms=(8 * HOUR,), measurement_ticks_ms=(T(7, 15), T(9, 45))
)


def test_ground_truth_unchanged_by_observation_corruption() -> None:
    plan = plan_for(SCHED_16)
    patient = make_patient(baseline=130.0)
    spike = c1_spec("hypertensive_spike", T(7), duration_ms=HOUR, magnitude=20.0)
    result = assemble(patient, SCHED_16, [spike])
    latent_truth = [
        tup(e)
        for e in truth_of(result.latent, plan, result.c1_records, result.behaviour_log)
    ]
    assert [t[:5] for t in latent_truth] == [
        ("C1", "hypertensive_spike", T(7, 15), None, True)
    ]

    base = observed_stream(result, SCHED_16, ZERO_ERRORS)
    c2 = InjectionSpec(C2, "cuff_silent_bias", T(9), 3 * HOUR, -30.0, "mmHg", {})
    c3 = InjectionSpec(C3, "injection_naive", T(9), 3 * HOUR, None, None, {}, None)
    context = InjectionContext(
        PATIENT_INDEX, bp_bounds_mmhg=(50.0, 250.0), hr_bounds_bpm=(40.0, 180.0)
    )

    def inject(spec: InjectionSpec) -> tuple[ObservedDay, list[InjectionRecord]]:
        out = apply_observation_injections(base, [spec], context)
        return finalize_observed(out.stream), list(out.records)

    variants: dict[str, tuple[ObservedDay, list[InjectionRecord]]] = {
        "cuff noise": (
            finalize_observed(observed_stream(result, SCHED_16, NOISY_ERRORS)),
            [],
        ),
        "C2 fault": inject(c2),
        "C3 attack": inject(c3),
    }
    seen_by_monitor: dict[str, list[tuple[str, int]]] = {}
    for name, (observed, extra) in variants.items():
        assembled = assemble_benchmark_day(
            observed,
            result.latent,
            plan,
            [*result.c1_records, *extra],
            result.behaviour_log,
            None,
            CFG,
            None,
            MODE_SCHEDULED,
            registry=F0,
            templates=LIBRARY,
        )
        truth = assembled.day.ground_truth
        # the identical set of C1 events (as full events), whatever corrupts the observation
        assert [tup(e) for e in truth if e.cls is C1] == latent_truth, name
        assert (
            assembled.day.observed is observed and assembled.day.latent is result.latent
        )
        seen_by_monitor[name] = monitor_violation_set(run_monitor(observed, plan), plan)
    # the observation did change what the monitor sees: its violated sets differ from the truth and each other
    assert any(
        seen != [("range", t[2]) for t in latent_truth]
        for seen in seen_by_monitor.values()
    )
    assert len({tuple(v) for v in seen_by_monitor.values()}) >= 2
    # C2 and C3 truth follows the records (one event per realised injection), not the monitor
    truth_c2 = assemble_benchmark_day(
        variants["C2 fault"][0],
        result.latent,
        plan,
        [*result.c1_records, *variants["C2 fault"][1]],
        result.behaviour_log,
        None,
        CFG,
        None,
        MODE_SCHEDULED,
        registry=F0,
        templates=LIBRARY,
    )
    assert [e.subtype for e in truth_c2.day.ground_truth if e.cls is C2] == [
        "cuff_silent_bias"
    ]


def test_the_labeller_hands_the_monitor_only_the_ideal_observation() -> None:
    result = assemble(make_patient(), SCHED_16)
    plan = plan_for(SCHED_16)
    stub = Stub()
    label_latent_day(
        result.latent,
        plan,
        result.c1_records,
        result.behaviour_log,
        stub,
        CFG,
        None,
        MODE_SCHEDULED,
        registry=F0,
        templates=LIBRARY,
    )
    [call] = stub.calls
    day = call["day"]
    # exactly what ideal_observation builds, and built only from latent values at measurement instants
    assert day == ideal_observation(
        result.latent,
        PLAN_ID,
        MODE_SCHEDULED,
        step_ms=MIN,
        signals=("bp", "meas", "dispense", "sched_tick", "day_end"),
    )
    assert (
        type(day) is ObservedDay
        and not hasattr(day, "ground_truth")
        and not hasattr(day, "latent")
    )
    latent_bp = {
        s.t_device_ms: s.value for s in result.latent.samples if s.signal == "bp"
    }
    # every observed bp is the held latent value at a MEASUREMENT instant; the other latent signals are absent
    for s in day.samples:
        assert s.signal in ("bp", "day_end")
        if s.signal == "bp":
            held = latent_bp[max(t for t in latent_bp if t <= s.t_device_ms)]
            assert s.value == held
    assert {e.kind for e in day.events} <= {
        EventKind.MEASUREMENT,
        EventKind.DISPENSE,
        EventKind.SCHEDULE_TICK,
    }


# --- test 17: an undetectable injection is still in the ground truth -----------------------------------


def test_undetectable_injection_still_in_ground_truth() -> None:
    schedule = Schedule(dose_ticks_ms=(), measurement_ticks_ms=(T(9), T(15)))
    plan = plan_for(schedule)
    result = assemble(make_patient(baseline=130.0), schedule)
    base = observed_stream(result, schedule, ZERO_ERRORS)
    silent = InjectionSpec(C2, "cuff_silent_bias", T(8), 8 * HOUR, 20.0, "mmHg", {})
    injected = apply_observation_injections(
        base, [silent], InjectionContext(PATIENT_INDEX)
    )
    [record] = injected.records
    assert record.realised and record.spec.subtype == "cuff_silent_bias"
    assert (
        record.evidence_paths == ()
    )  # the evidence signature is empty: a declared diagnosability limit
    observed = finalize_observed(injected.stream)
    verdicts = run_monitor(observed, plan)
    # the monitor emits no phi_SYS or phi_INT violation: cuff health and inflation are nominal
    assert not [
        r
        for r in verdicts
        if r.template in (TemplateId.SYS, TemplateId.INT)
        and r.state is VerdictState.VIOLATED
    ]
    assert [
        r
        for r in verdicts
        if r.template is TemplateId.SYS and r.state is VerdictState.SATISFIED
    ]
    # it does see the shifted readings as a care-plan violation (150 > 140) that the latent trace lacks
    assert monitor_violation_set(verdicts, plan) and all(
        n == "range" for n, _ in monitor_violation_set(verdicts, plan)
    )
    # the truth: no C1 event (the latent pressure is 130), and the C2 event is there, injected, no template
    assembled = assemble_benchmark_day(
        observed,
        result.latent,
        plan,
        [*result.c1_records, record],
        result.behaviour_log,
        None,
        CFG,
        None,
        MODE_SCHEDULED,
        registry=F0,
        templates=LIBRARY,
    )
    truth = assembled.day.ground_truth
    assert [e for e in truth if e.cls is C1] == []
    [c2] = [e for e in truth if e.cls is C2]
    assert tup(c2) == ("C2", "cuff_silent_bias", T(8), T(16), True, None, None)
    # and the same through the labeller alone
    [only] = truth_of(result.latent, plan, [record], result.behaviour_log)
    assert only == c2


# --- test 18: the independent reference evaluator agrees ----------------------------------------------

SEEDS = tuple(range(20))
SHIFTS = (
    0.0,
    30.0,
)  # the fixture prior as it is, and a shift that puts the pressure across the band


def hold_value(grid: Sequence[Sample], t: int) -> float:
    """The latent pressure at ``t``: the last grid sample at or before it (plain bisect, own code)."""
    import bisect

    times = [s.t_device_ms for s in grid]
    return grid[bisect.bisect_right(times, t) - 1].value


@pytest.fixture(scope="module")
def natural_days(
    tmp_path_factory: pytest.TempPathFactory,
) -> dict[tuple[int, float], dict[str, Any]]:
    path = make_fixture_prior(tmp_path_factory.mktemp("fixture_prior"))
    prior = LiteraturePriorSource(path, allow_fixture_only=True)
    windows = (
        REF_PARAMS.hold_lookback_ms,
        REF_PARAMS.delta1_ms,
        REF_PARAMS.delta2_ms,
        REF_PARAMS.sched_window_ms,
    )
    schedule = derive_schedule((8 * HOUR, 20 * HOUR), 6, *windows)
    adherence_params = prior.adherence()
    out: dict[tuple[int, float], dict[str, Any]] = {}
    for seed in SEEDS:
        for shift in SHIFTS:
            patient = prior.sample_patient(np.random.default_rng(seed), seed)
            patient = dataclasses.replace(
                patient, baseline_sbp_mmhg=patient.baseline_sbp_mmhg + shift
            )
            adherence = AdherenceModel(
                adherence_params,
                AdherenceConfig(intake_lag_ms=LAG, double_take_gap_ms=2 * MIN),
            )
            result = assemble(
                patient, schedule, adherence=adherence, seed=seed, index=seed
            )
            ticks = (
                *schedule.measurement_ticks_ms,
                T(3),
            )  # 03:00 has no reading: a SCHED violation
            plan = make_plan(sched=ticks, patient=patient.patient_id)
            truth = truth_of(
                result.latent, plan, result.c1_records, result.behaviour_log
            )
            grid = [s for s in result.latent.samples if s.signal == "bp"]
            meas = [
                e.t_device_ms
                for e in result.latent.events
                if e.kind is EventKind.MEASUREMENT
            ]
            reference = reference_evaluate(
                REF_PARAMS,
                step_ms=MIN,
                origin_ms=0,
                measurements=meas,
                bp_samples=[(t, hold_value(grid, t)) for t in meas],
                dispenses=[
                    e.t_device_ms
                    for e in result.latent.events
                    if e.kind is EventKind.DISPENSE
                ],
                sched_ticks=list(ticks),
                count_end=True,
            )
            out[(seed, shift)] = {
                "truth": truth,
                "reference": reference,
                "result": result,
            }
    return out


@pytest.mark.parametrize("shift", SHIFTS)
@pytest.mark.parametrize("seed", SEEDS)
def test_independent_reference_evaluator_agrees(
    natural_days: dict[tuple[int, float], dict[str, Any]], seed: int, shift: float
) -> None:
    run = natural_days[(seed, shift)]
    labelled = sorted(
        (e.template_id, e.onset_ms, e.end_ms) for e in run["truth"] if e.cls is C1
    )
    reference = sorted((v.template, v.anchor_ms, v.end_ms) for v in run["reference"])
    assert labelled == reference
    # (template, anchor_ms) as sets, the form of the task
    assert {(t, a) for t, a, _ in labelled} == {
        (v.template, v.anchor_ms) for v in run["reference"]
    }
    # natural adherence, no injection: every event is natural
    assert all(not e.injected for e in run["truth"])


def test_the_reference_comparison_is_not_vacuous(
    natural_days: dict[tuple[int, float], dict[str, Any]],
) -> None:
    templates = {v.template for run in natural_days.values() for v in run["reference"]}
    assert templates == {"range", "hold", "resp", "sched", "count"}
    assert sum(len(run["reference"]) for run in natural_days.values()) >= 60
    subtypes = {e.subtype for run in natural_days.values() for e in run["truth"]}
    assert (
        "dose_omission" in subtypes
    )  # the natural adherence model produced an omitted slot
    assert subtypes <= {
        f"spontaneous_{t}" for t in ("range", "hold", "resp", "sched", "count")
    } | {
        "dose_omission",
        "double_take",
    }
    days_with_events = sum(1 for run in natural_days.values() if run["truth"])
    assert days_with_events >= 10


# --- the reference evaluator against the golden files, and its independence ----------------------------


def test_reference_reproduces_the_golden_patient_day() -> None:
    golden = yaml.safe_load((GOLDEN / "patient-day.yaml").read_text(encoding="utf-8"))
    observed = golden["observed_day"]
    ticks = [
        i["anchor_ms"]
        for i in golden["plan"]["static_instances"]
        if i["template"] == "sched"
    ]
    reference = reference_evaluate(
        RefParams.from_registry_file(F0_PATH),
        step_ms=MIN,
        origin_ms=0,
        measurements=[
            e["t_device_ms"] for e in observed["events"] if e["kind"] == "measurement"
        ],
        bp_samples=[
            (s["t_device_ms"], s["value"])
            for s in observed["samples"]
            if s["signal"] == "bp"
        ],
        dispenses=[
            e["t_device_ms"] for e in observed["events"] if e["kind"] == "dispense"
        ],
        sched_ticks=ticks,
        count_end=any(
            i["template"] == "count" for i in golden["plan"]["static_instances"]
        ),
    )
    cp = {"range", "sched", "hold", "count", "resp"}
    first: dict[str, Any] = {}
    for record in golden["records"]:
        key = record["instance_key"]
        if (
            record["expected"]["state"] == "violated"
            and record["expected"]["template"] in cp
        ):
            first.setdefault(key, record)
    expected = sorted(
        (r["expected"]["template"], int(k.split("@")[1])) for k, r in first.items()
    )
    assert expected == [
        ("count", T(21, 2)),
        ("range", T(12, 24)),
        ("range", T(20, 32)),
        ("resp", T(7)),
        ("sched", T(9)),
    ]
    assert sorted((v.template, v.anchor_ms) for v in reference) == expected


def test_reference_reproduces_the_golden_verdict_cases() -> None:
    cases = yaml.safe_load((GOLDEN / "verdicts.yaml").read_text(encoding="utf-8"))
    checked = 0
    for case in cases:
        e, instance, inputs = (
            case["expected"],
            case["inputs"]["instance"],
            case["inputs"],
        )
        if (
            e["state"] not in ("violated", "satisfied")
            or "late_inputs" in e
            or case["fixture"]["reorder_delay_ms"] != 0
        ):
            continue
        template = instance["template"]
        if template not in ("sched", "resp", "count_limit", "count_end"):
            continue
        anchor = instance["anchor_ms"]
        found = reference_evaluate(
            REF_PARAMS,
            step_ms=MIN,
            origin_ms=0,
            measurements=[
                x["t_device_ms"] for x in inputs["events"] if x["kind"] == "measurement"
            ],
            bp_samples=[
                (x["t_device_ms"], x["value"])
                for x in inputs["samples"]
                if x["signal"] == "bp"
            ],
            dispenses=[
                x["t_device_ms"] for x in inputs["events"] if x["kind"] == "dispense"
            ],
            sched_ticks=[anchor] if template == "sched" else [],
            count_end=template == "count_end",
        )
        name = {
            "sched": "sched",
            "resp": "resp",
            "count_limit": "count",
            "count_end": "count",
        }[template]
        was_violated = any(v.template == name and v.anchor_ms == anchor for v in found)
        assert was_violated == (e["state"] == "violated"), case["id"]
        checked += 1
    assert checked == 14  # SCHED 2 to 5b, PRED-2 and 3, RESP-3 to 6, COUNT-1, 2 and 4


def test_the_reference_evaluator_shares_no_code_with_the_monitor_or_the_labeller() -> (
    None
):
    path = THIS_FILE.with_name("reference_phi_cp.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "no relative import"
            imported.add((node.module or "").split(".")[0])
    assert imported <= {
        "__future__",
        "math",
        "collections",
        "dataclasses",
        "pathlib",
        "typing",
        "yaml",
    }
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
        n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
    }
    for forbidden in (
        "ralmon",
        "labelling",
        "monitor",
        "StreamingMonitor",
        "run_offline",
        "VerdictRecord",
    ):
        assert forbidden not in names, forbidden


# --- test 19: the scheduled and the dense modes ------------------------------------------------------


def test_scheduled_and_dense_modes_differ_only_where_expected() -> None:
    def pressure(t: int) -> float:
        return (
            160.0 if T(10) <= t < T(10, 30) else 130.0
        )  # a spike between two scheduled readings

    latent = make_latent(bp=pressure, measurements=(T(9), T(11)), ticks=(T(9), T(11)))
    plan = make_plan(sched=(T(9), T(11)), count_end=False)
    spike = spike_record(T(10), T(10, 30))
    scheduled = truth_of(latent, plan, [spike], mode=MODE_SCHEDULED)
    dense = truth_of(latent, plan, [spike], mode=MODE_DENSE)
    # between two scheduled measurements the spike is no C1 event; in dense mode every grid step is a reading
    assert scheduled == ()
    assert len(dense) == 30
    assert [e.onset_ms for e in dense] == [T(10) + i * MIN for i in range(30)]
    for e in dense:
        assert tup(e) == c1_event(
            "hypertensive_spike", "range", e.onset_ms, None, injected=True
        )
    # the modes differ only there: the scheduled events are all dense events
    assert set(scheduled) <= set(dense)
    # without the record the dense events are natural
    assert {e.subtype for e in truth_of(latent, plan, [], mode=MODE_DENSE)} == {
        "spontaneous_range"
    }
    # a tick without a reading violates SCHED in scheduled mode and not in dense mode (a reading every step)
    lonely = make_plan(sched=(T(15),), count_end=False)
    base = make_latent(measurements=())
    assert [e.template_id for e in truth_of(base, lonely, mode=MODE_SCHEDULED)] == [
        "sched"
    ]
    assert truth_of(base, lonely, mode=MODE_DENSE) == ()
    # the mode is a parameter of the labeller only: the default is `scheduled`
    assert (
        inspect.signature(label_latent_day).parameters["mode"].default == MODE_SCHEDULED
    )
    assert truth_of(latent, plan, [spike]) == scheduled


def test_dense_mode_pre_dose_reference_is_the_latent_pressure_at_the_dose() -> None:
    # dense mode reads the latent pressure at every grid step, so the pre-dose value of RESP is the latent
    # value at the dispense step: 150 here, and a response of 20 at 09:00 satisfies delta_resp = 10
    def pressure(t: int) -> float:
        return 150.0 if t < T(8) else 130.0

    latent = make_latent(bp=pressure, measurements=(), dispenses=(T(7),))
    out = truth_of(latent, make_plan(), mode=MODE_DENSE)
    assert "resp" not in {e.template_id for e in out}
    # the same dose in scheduled mode has no reading at all in its window: the obligation is unmet
    scheduled = truth_of(latent, make_plan(), mode=MODE_SCHEDULED)
    assert "resp" in {e.template_id for e in scheduled}


# --- test 20: the null latent day ---------------------------------------------------------------------

NULL_SCHEDULE = derive_schedule(
    (8 * HOUR, 20 * HOUR),
    6,
    REF_PARAMS.hold_lookback_ms,
    REF_PARAMS.delta1_ms,
    REF_PARAMS.delta2_ms,
    REF_PARAMS.sched_window_ms,
)
# FIXTURE-ONLY patient for the null day: constant 135 in the band, a drug that lowers the pressure by more
# than delta_resp = 10 at the post-dose reading (13.4 at 1 h 45 min after the dose) and by 20 at most (115)
NULL_PATIENT = make_patient(baseline=135.0, emax=60.0, ec50=1.0, ka=2.0, ke=1.0)


def registry_with(tmp_path: Path, **changes: float) -> Any:
    document = yaml.safe_load(F0_PATH.read_text(encoding="utf-8"))
    for entry in document["entries"]:
        if entry["name"] in changes:
            entry["value"] = float(changes[entry["name"]])
    path = tmp_path / "changed_registry.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return load_registry(path, step_ms=MIN, allow_fixture_only=True)


def test_null_latent_day_has_no_care_plan_violation(tmp_path: Path) -> None:
    result = assemble(NULL_PATIENT, NULL_SCHEDULE)
    assert not result.c1_records and all(
        e.state is AdherenceState.ON_TIME for e in result.behaviour_log
    )
    plan = plan_for(NULL_SCHEDULE, count_end=True)
    assert truth_of(result.latent, plan, result.c1_records, result.behaviour_log) == ()
    assert (
        truth_of(
            result.latent,
            plan,
            result.c1_records,
            result.behaviour_log,
            mode=MODE_DENSE,
        )
        == ()
    )
    # not vacuous: the instances exist and are all satisfied
    ideal = ideal_observation(result.latent, PLAN_ID, step_ms=MIN)
    verdicts = run_offline(
        ideal, plan, CFG, None, None, registry=F0, templates=CP_TEMPLATES
    )
    final: dict[str, VerdictState] = {}
    for r in verdicts:
        if r.state in (VerdictState.VIOLATED, VerdictState.SATISFIED):
            final.setdefault(r.instance_key, r.state)
    names = [k.split("@")[0] for k in final]
    assert {n: names.count(n) for n in set(names)} == {
        "sched": 6,
        "range": 6,
        "hold": 2,
        "resp": 2,
        "count": 3,
    }
    assert set(final.values()) == {VerdictState.SATISFIED}
    # the null day is sensitive to a schedule or registry mismatch of the generator (what it is there to catch)
    shifted = make_plan(
        sched=[t + 45 * MIN for t in NULL_SCHEDULE.measurement_ticks_ms]
    )
    assert {e.template_id for e in truth_of(result.latent, shifted)} == {"sched"}
    stricter = registry_with(
        tmp_path, delta_resp=20.0
    )  # the drop of 13.4 no longer answers the dose
    out = truth_of(result.latent, plan, registry=stricter, templates=None)
    assert {e.template_id for e in out} == {"resp"} and len(out) == 2
    narrower = registry_with(
        tmp_path, bp_band_high=134.0
    )  # the baseline 135 leaves the band
    assert "range" in {
        e.template_id
        for e in truth_of(result.latent, plan, registry=narrower, templates=None)
    }


# --- CP7: instances open at the end of the day are not violations --------------------------------------


@pytest.mark.parametrize("day", [0, 1, 6])
def test_instances_open_at_the_end_of_the_day_are_not_violations(day: int) -> None:
    # a dose at 22:00: the response window ends at 25:00, after the closing step; the reading at 23:00 shows no
    # response at all (130 against 130), and the tick at 23:45 has its deadline at 24:15
    latent = make_latent(
        day,
        bp=130.0,
        measurements=(T(21, 30), T(23)),
        dispenses=(T(22),),
        ticks=(T(23, 45),),
    )
    plan = make_plan(day, sched=(T(23, 45),))
    out = truth_of(latent, plan)
    assert [(e.template_id, e.onset_ms, e.end_ms) for e in out] == [
        ("count", day * DAY + DAY, day * DAY + DAY)
    ]
    # a response that the bounds already rule out is decided at the anchor (Lemma 12), not left open
    low = make_latent(
        day,
        bp=lambda t: 55.0 if t >= T(21, 30) else 130.0,
        measurements=(T(21, 30),),
        dispenses=(T(22),),
    )
    resp = [
        e
        for e in truth_of(low, make_plan(day, count_end=False))
        if e.template_id == "resp"
    ]
    assert [(e.onset_ms, e.end_ms) for e in resp] == [
        (day * DAY + T(22), day * DAY + T(25))
    ]


# --- tests 21 and 22 -----------------------------------------------------------------------------------


def test_labeller_takes_no_observed_day() -> None:
    for function in (label_latent_day, label_latent_day_detailed):
        sig = inspect.signature(function)
        assert list(sig.parameters)[:4] == [
            "latent",
            "plan",
            "records",
            "behaviour_log",
        ]
        assert list(sig.parameters)[4:8] == [
            "run_fn",
            "config",
            "latency_bound_fn",
            "mode",
        ]
        for name, parameter in sig.parameters.items():
            text = f"{name} {parameter.annotation}".lower()
            assert "observed" not in text, (function.__name__, name)
            assert "benchmarkday" not in text and "groundtruth" not in text
        assert "LatentDay" in str(sig.parameters["latent"].annotation)
        tree = ast.parse(inspect.getsource(function).lstrip())
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
            a.arg for a in ast.walk(tree) if isinstance(a, ast.arg)
        }
        assert not {n for n in names if "observed" in n.lower()}
    # assemble_benchmark_day is the one place that takes the observed day, and it only stores it
    assert "observed" in inspect.signature(assemble_benchmark_day).parameters


def imports_of(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    package = ["ralmon", "benchmark"]
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                base = (node.module or "").split(".")
            else:
                base = package[: len(package) - (node.level - 1)] + (
                    (node.module or "").split(".") if node.module else []
                )
            found.add(".".join(base))
    return found


def test_import_boundaries() -> None:
    composition = {"labelling.py", "builder.py", "validation.py"}
    stdlib = set(sys.stdlib_module_names)
    modules = sorted(SRC.glob("*.py"))
    assert {m.name for m in modules} >= {
        "labelling.py",
        "trace.py",
        "injection.py",
        "latent_day.py",
        "measurement.py",
    }
    offenders: list[str] = []
    for path in modules:
        for name in imports_of(path):
            top, _, rest = name.partition(".")
            second = rest.split(".")[0] if rest else ""
            if top == "ralmon":
                if second in ("monitor", "spec"):
                    if path.name not in composition:
                        offenders.append(f"{path.name}: {name}")
                elif second not in ("signals", "benchmark", "_stub"):
                    offenders.append(f"{path.name}: {name}")
            elif top not in stdlib and top not in ("numpy", "yaml"):
                offenders.append(f"{path.name}: {name}")
    assert offenders == []
    # the rule is not vacuous: the composition module does import both, at the package root
    names = imports_of(SRC / "labelling.py")
    assert {"ralmon.monitor", "ralmon.spec"} <= names
    # and no module outside the three names reaches into monitor or spec through a deeper path either
    for path in modules:
        if path.name in composition:
            continue
        assert not [
            n
            for n in imports_of(path)
            if n.startswith(("ralmon.monitor", "ralmon.spec"))
        ], path.name


def test_labelling_is_deterministic_by_construction() -> None:
    tree = ast.parse((SRC / "labelling.py").read_text(encoding="utf-8"))
    banned_modules = {
        "time",
        "datetime",
        "random",
        "secrets",
        "uuid",
        "os",
        "subprocess",
        "socket",
        "threading",
        "tempfile",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not {a.name.split(".")[0] for a in node.names} & banned_modules
        elif isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] not in banned_modules
            assert node.module != "numpy.random"
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
        n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
    }
    assert not names & {
        "random",
        "default_rng",
        "Generator",
        "time",
        "monotonic",
        "perf_counter",
        "now",
        "environ",
        "getenv",
    }


# ---------------------------------------------------------------------------------------------------
# assemble_benchmark_day: the day, the truth and the sidecars
# ---------------------------------------------------------------------------------------------------


def assembled_fixture() -> tuple[
    AssembledDay, Any, LatentResult, CarePlan, list[InjectionRecord]
]:
    plan = plan_for(SCHED_16)
    result = assemble(
        make_patient(baseline=130.0),
        SCHED_16,
        [c1_spec("hypertensive_spike", T(7), duration_ms=HOUR, magnitude=20.0)],
    )
    base = observed_stream(result, SCHED_16, ZERO_ERRORS)
    silent = InjectionSpec(C2, "cuff_silent_bias", T(9), 3 * HOUR, -30.0, "mmHg", {})
    injected = apply_observation_injections(
        base, [silent], InjectionContext(PATIENT_INDEX)
    )
    observed = finalize_observed(injected.stream)
    unrealised = other_record(C3, "replay", T(14), T(15), realised=False)
    records = [unrealised, *result.c1_records, *injected.records]
    out = assemble_benchmark_day(
        observed,
        result.latent,
        plan,
        records,
        result.behaviour_log,
        None,
        CFG,
        None,
        MODE_SCHEDULED,
        registry=F0,
        templates=LIBRARY,
    )
    return out, observed, result, plan, records


def test_assemble_benchmark_day_returns_the_day_the_truth_and_the_sidecars(
    tmp_path: Path,
) -> None:
    out, observed, result, plan, records = assembled_fixture()
    assert isinstance(out, AssembledDay)
    assert isinstance(out.day, BenchmarkDay) and isinstance(out.truth, TruthRecord)
    assert out.day.observed is observed and out.day.latent is result.latent
    expected = label_latent_day(
        result.latent,
        plan,
        records,
        result.behaviour_log,
        None,
        CFG,
        None,
        MODE_SCHEDULED,
        registry=F0,
        templates=LIBRARY,
    )
    assert tuple(out.day.ground_truth) == expected == tuple(out.truth.ground_truth)
    assert out.truth.latent is result.latent
    assert [e.subtype for e in expected] == ["hypertensive_spike", "cuff_silent_bias"]
    # the injection log: one entry per record, in the order given, with the keys of the sidecar
    log = out.truth.injection_log
    assert isinstance(log, list) and len(log) == len(records)
    assert [entry["record_index"] for entry in log] == list(range(len(records)))
    for entry in log:
        assert (
            tuple(entry)
            == labelling.INJECTION_LOG_BASE_KEYS + labelling.INJECTION_LOG_LINK_KEYS
        )
    base_keys = set(injection_log(records)[0])
    assert (
        set(labelling.INJECTION_LOG_BASE_KEYS) == base_keys
    )  # the keys of injection.injection_log
    by_subtype = {entry["subtype"]: entry for entry in log}
    assert (
        by_subtype["replay"]["realised"] is False
        and by_subtype["replay"]["truth_indices"] == []
    )
    assert by_subtype["hypertensive_spike"]["truth_indices"] == [
        0
    ]  # the index into ground_truth it explains
    assert by_subtype["cuff_silent_bias"]["truth_indices"] == [1]
    assert by_subtype["cuff_silent_bias"]["evidence_paths"] == []
    assert (
        by_subtype["hypertensive_spike"]["magnitude"] == 20.0
        and by_subtype["hypertensive_spike"]["magnitude_unit"] == "mmHg"
    )
    # the behaviour log is the list of the entries as JSON
    assert out.truth.behaviour_log == [e.to_json() for e in result.behaviour_log]
    # the sidecars are JSON-native and the truth file round-trips (WS04-T01 writer and reader)
    json.dumps(out.truth.injection_log, allow_nan=False)
    from ralmon.benchmark.trace import read_truth, write_truth

    write_truth(
        tmp_path,
        result.latent,
        list(out.truth.ground_truth),
        out.truth.injection_log,
        out.truth.behaviour_log,
    )
    back = read_truth(tmp_path, PATIENT, 0)
    assert (
        tuple(back.ground_truth) == expected
        and back.injection_log == out.truth.injection_log
    )
    assert back.behaviour_log == out.truth.behaviour_log


def test_detailed_labelling_links_events_to_records_by_index() -> None:
    result = assemble(
        make_patient(),
        SCHED_16,
        [c1_spec("hypertensive_spike", T(7), duration_ms=HOUR, magnitude=20.0)],
    )
    plan = plan_for(SCHED_16)
    extra = other_record(C2, "ble_dropout", T(1), T(2))
    records = [extra, *result.c1_records]
    detailed = label_latent_day_detailed(
        result.latent,
        plan,
        records,
        result.behaviour_log,
        None,
        CFG,
        None,
        MODE_SCHEDULED,
        registry=F0,
        templates=LIBRARY,
    )
    assert isinstance(detailed, LabelledDay)
    assert len(detailed.record_index) == len(detailed.events)
    assert [e.subtype for e in detailed.events] == ["ble_dropout", "hypertensive_spike"]
    assert detailed.record_index == (
        0,
        1,
    )  # the C2 event comes from record 0, the C1 event is explained by record 1
    assert detailed.n_verdict_records > 0
    # an event explained by no record has no index
    plain = label_latent_day_detailed(
        result.latent,
        plan,
        [extra],
        result.behaviour_log,
        None,
        CFG,
        None,
        MODE_SCHEDULED,
        registry=F0,
        templates=LIBRARY,
    )
    assert [
        (e.subtype, i) for e, i in zip(plain.events, plain.record_index, strict=True)
    ] == [("ble_dropout", 0), ("spontaneous_range", None)]


def test_assemble_refuses_an_observed_day_that_is_not_of_this_latent_day() -> None:
    _out, observed, result, plan, records = assembled_fixture()

    def call(obs: Any, latent: Any = None, pl: Any = None) -> Any:
        return assemble_benchmark_day(
            obs,
            result.latent if latent is None else latent,
            plan if pl is None else pl,
            records,
            result.behaviour_log,
            None,
            CFG,
            None,
            MODE_SCHEDULED,
            registry=F0,
            templates=LIBRARY,
        )

    for change in (
        {"patient_id": "other"},
        {"day_index": 1},
        {"seed": 99},
        {"care_plan_id": "other-plan"},
    ):
        with pytest.raises(LabellingError):
            call(dataclasses.replace(observed, **change))
    # an ObservedStream carries the latent pressure of every reading: it is never accepted
    stream = observed_stream(result, SCHED_16, ZERO_ERRORS)
    assert stream.measurements and hasattr(stream.measurements[0], "latent_sbp_mmhg")
    with pytest.raises(LabellingError):
        call(stream)
    with pytest.raises(LabellingError):
        call(result.latent)  # the latent day is not an observed day
    with pytest.raises(LabellingError):
        call(
            observed,
            pl=make_plan(
                care_plan_id="other-plan", sched=SCHED_16.measurement_ticks_ms
            ),
        )
    with pytest.raises(LabellingError):
        call(
            observed,
            pl=make_plan(patient="someone-else", sched=SCHED_16.measurement_ticks_ms),
        )


def test_the_observed_day_contains_nothing_derived_from_the_latent_day() -> None:
    plan = plan_for(SCHED_16)
    result = assemble(
        make_patient(baseline=131.4375), SCHED_16
    )  # a sentinel pressure, exact in binary
    stream = observed_stream(result, SCHED_16, DeviceErrorModel(0.0, 2.5, 0.0, 0.0))
    observed = finalize_observed(stream)
    before = copy.deepcopy(observed)
    out = assemble_benchmark_day(
        observed,
        result.latent,
        plan,
        [],
        result.behaviour_log,
        None,
        CFG,
        None,
        MODE_SCHEDULED,
        registry=F0,
        templates=LIBRARY,
    )
    assert out.day.observed == before  # not modified
    latent_only = {m.latent_sbp_mmhg for m in stream.measurements} | {
        s.value for s in result.latent.samples if s.signal == "bp"
    }
    assert 131.4375 in latent_only
    observed_values = {s.value for s in out.day.observed.samples}
    assert (
        not observed_values & latent_only
    )  # the readings are latent + bias: no latent value is written
    text = json.dumps(
        {
            "samples": [dataclasses.astuple(s) for s in out.day.observed.samples],
            "events": [
                (e.kind.value, e.t_device_ms, e.source, sorted(e.payload))
                for e in out.day.observed.events
            ],
        }
    )
    assert "latent" not in text and "ground_truth" not in text
    # the ideal observation, by contrast, is made of latent values and is never an ObservedDay of a benchmark day
    ideal = ideal_observation(result.latent, PLAN_ID)
    assert {s.value for s in ideal.samples if s.signal == "bp"} <= latent_only


# ---------------------------------------------------------------------------------------------------
# Vocabulary and documents
# ---------------------------------------------------------------------------------------------------


def vocabulary_of(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    section = text.split("## Subtype vocabulary", 1)[1].split("\n## ", 1)[0]
    return re.findall(r"^- ([a-z_]+)\s*$", section, re.MULTILINE)


def test_c1_vocabulary_is_the_one_of_the_workstream_readme() -> None:
    line = next(
        x
        for x in README.read_text(encoding="utf-8").splitlines()
        if x.startswith("- C1 (truth from")
    )
    pairs = dict(re.findall(r"`([a-z_]+)` \((?:template )?`([a-z]+)`", line))
    assert pairs == {**LINK_TABLE, "dose_omission": "count"}
    assert "`spontaneous_<template id>`" in line
    assert labelling.SPONTANEOUS_PREFIX == "spontaneous_"
    assert (labelling.SUBTYPE_DOUBLE_TAKE, labelling.SUBTYPE_DOSE_OMISSION) == (
        "double_take",
        "dose_omission",
    )
    assert (
        labelling.SUBTYPE_DOUBLE_TAKE in pairs
        and labelling.SUBTYPE_DOSE_OMISSION in pairs
    )
    # every subtype the labeller can put on a C1 event is in that vocabulary
    produced = {
        e.subtype for template in EVENT_RECORDS for e in label_noon(template, [])
    }
    produced |= {
        e.subtype
        for s, make in EXPLAINERS.items()
        for e in label_noon(LINK_TABLE[s], [make()])
    }
    allowed_names = set(pairs) | {
        f"spontaneous_{t}" for t in ("range", "sched", "hold", "count", "resp")
    }
    assert produced <= allowed_names


def test_c2_and_c3_subtypes_pass_through_from_the_fault_and_threat_models() -> None:
    fault = vocabulary_of(ROOT / "docs" / "models" / "fault-model.md")
    threat = vocabulary_of(ROOT / "docs" / "models" / "threat-model.md")
    assert len(fault) == len(set(fault)) >= 17 and len(threat) == len(set(threat)) == 7
    for cls, names in ((C2, fault), (C3, threat)):
        for name in names:
            [event] = label([], injections=[other_record(cls, name, T(8), T(9))])
            assert (event.cls, event.subtype, event.template_id, event.injected) == (
                cls,
                name,
                None,
                True,
            )


def test_the_module_surface_is_not_exported_from_the_package_root() -> None:
    import ralmon.benchmark as pkg

    assert not {
        "ideal_observation",
        "label_latent_day",
        "assemble_benchmark_day",
    } & set(pkg.__all__)
    assert set(labelling.__all__) >= {
        "ideal_observation",
        "label_latent_day",
        "label_latent_day_detailed",
        "assemble_benchmark_day",
        "LabellingError",
        "IdealObservationError",
        "RegistryMismatchError",
        "RunnerError",
    }
    for name in labelling.__all__:
        assert hasattr(labelling, name)


def defined_test_names() -> set[str]:
    tree = ast.parse(THIS_FILE.read_text(encoding="utf-8"))
    return {
        n.name
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
    }


def test_the_23_tests_of_the_task_are_defined() -> None:
    task = (
        ROOT
        / "docs"
        / "plan"
        / "workstreams"
        / "WS04-benchmark"
        / "tasks"
        / "T10-latent-ground-truth.md"
    ).read_text(encoding="utf-8")
    listed = []
    for line in task.splitlines():
        match = re.match(r"^(\d+)\. `(test_[a-z0-9_]+)`", line)
        if match:
            listed.append((int(match.group(1)), match.group(2)))
    assert [n for n, _ in listed] == list(range(1, 24))
    defined = defined_test_names()
    assert [name for _, name in listed if name not in defined] == []
    assert len(defined) >= 23


NON_CIRCULARITY_TESTS = (
    "test_perfect_observation_equals_ground_truth_on_c1",
    "test_noisy_observation_diverges_from_ground_truth",
    "test_c1_truth_follows_latent_not_injection_intent",
    "test_ground_truth_unchanged_by_observation_corruption",
    "test_undetectable_injection_still_in_ground_truth",
    "test_independent_reference_evaluator_agrees",
    "test_labeller_takes_no_observed_day",
    "test_import_boundaries",
)
SECTIONS = (
    "Definition",
    "Onset and end conventions",
    "Injection records versus truth",
    "Modes",
    "Non-circularity tests",
    "Residual circularity",
)


def doc_sections() -> dict[str, str]:
    text = GROUND_TRUTH_DOC.read_text(encoding="utf-8")
    parts = re.split(r"^## (.+)$", text, flags=re.MULTILINE)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}


def test_ground_truth_document_has_its_sections_and_names_the_tests() -> None:
    sections = doc_sections()
    assert list(sections) == list(SECTIONS)
    defined = defined_test_names()
    body = sections["Non-circularity tests"]
    for name in NON_CIRCULARITY_TESTS:
        assert name in defined, name
        assert name in body, name  # the section names each test ...
    assert "tests/benchmark/test_ground_truth.py" in body  # ... with its path
    assert "tests/benchmark/reference_phi_cp.py" in body
    residual = sections["Residual circularity"]
    for needle in ("WS00-T07", "reference evaluator", "same specification"):
        assert needle in residual, needle
    conventions = sections["Onset and end conventions"]
    for needle in (
        "pending_until_ms",
        "decided_at_ms",
        "instance_key",
        "first",
        "delta2",
        "end_ms",
        "None",
    ):
        assert needle in conventions, needle
    for mode in ("scheduled", "dense"):
        assert mode in sections["Modes"]
    link = sections["Injection records versus truth"]
    for needle in (
        "intake_times_ms",
        "record_index",
        "truth_indices",
        "verdict_latency_bound_ms",
        *LINK_TABLE,
    ):
        assert needle in link, needle
    definition = sections["Definition"]
    for needle in ("latent", "analisi", "label_latent_day", "ideal observation"):
        assert needle in definition, needle


def test_default_registry_path_is_the_real_registry_and_is_never_substituted() -> None:
    # config.registry_version and the plan are those of the committed registry file, read here as plain YAML
    # so that the test holds in any state of that file; the labeller loads it (never a fixture registry) and
    # either runs or reports a named error, and never reads a number that the registry does not hold
    document = yaml.safe_load(
        (ROOT / "configs" / "registry" / "hypertension.yaml").read_text(
            encoding="utf-8"
        )
    )
    version = str(document["registry_version"])
    stub = Stub()
    try:
        out = label_latent_day(
            make_latent(measurements=(T(12),)),
            make_plan(registry_version=version),
            [],
            [],
            stub,
            MonitorConfig(MIN, 0, False, None, "likely", version),
            None,
            MODE_SCHEDULED,
        )
    except (
        LabellingError
    ) as exc:  # the registry cannot be loaded at this step: a named error
        assert named(exc)
    else:
        assert out == () and len(stub.calls) == 1
        loaded = stub.calls[0]["registry"]
        assert loaded.version() == version and not loaded.fixture_only
    # a fixture registry is refused unless the caller loaded it with the explicit flag (ADR-027)
    with pytest.raises(LabellingError):
        label_latent_day(
            make_latent(measurements=(T(12),)),
            make_plan(registry_version=F0.version()),
            [],
            [],
            Stub(),
            CFG,
            None,
            MODE_SCHEDULED,
            registry=str(F0_PATH),  # type: ignore[arg-type]
        )


def test_natural_double_take_and_omission_are_labelled_from_the_generator_log() -> None:
    # the adherence model of WS04-T05 as a point mass: every slot a double take, then every slot omitted
    schedule = Schedule(
        dose_ticks_ms=(8 * HOUR, 20 * HOUR),
        measurement_ticks_ms=(T(7, 30), T(12), T(19, 30), T(22, 30)),
    )
    plan = make_plan(sched=schedule.measurement_ticks_ms)
    config = AdherenceConfig(intake_lag_ms=LAG, double_take_gap_ms=2 * MIN)
    doubles = AdherenceModel(AdherenceParams(0.0, 0.0, 1.0, 10 * MIN), config)
    result = assemble(make_patient(baseline=130.0), schedule, adherence=doubles)
    assert [e.state for e in result.behaviour_log] == [AdherenceState.DOUBLE_TAKE] * 2
    out = truth_of(result.latent, plan, result.c1_records, result.behaviour_log)
    limits = [e for e in out if e.template_id == "count"]
    # 08:00, 08:02, 20:00, 20:02: the trailing count is 3 at 20:00 and 4 at 20:02 (the limit is 2)
    assert [(e.onset_ms, e.subtype, e.injected) for e in limits] == [
        (20 * HOUR, "double_take", False),
        (20 * HOUR + 2 * MIN, "double_take", False),
    ]
    assert all(e.confounder_group is None and e.end_ms is None for e in limits)
    omitted = AdherenceModel(AdherenceParams(0.0, 1.0, 0.0, 10 * MIN), config)
    result = assemble(make_patient(baseline=130.0), schedule, adherence=omitted)
    assert [e.state for e in result.behaviour_log] == [AdherenceState.OMITTED] * 2
    out = truth_of(result.latent, plan, result.c1_records, result.behaviour_log)
    [end] = [e for e in out if e.template_id == "count"]
    assert tup(end) == c1_event("dose_omission", "count", DAY, DAY, injected=False)
    # a forced omission is a scenario control without a record: the log still labels it, not injected
    result = assemble(
        make_patient(baseline=130.0),
        schedule,
        forced=[ForcedSlot(0, 1, AdherenceState.OMITTED)],
    )
    [end] = [
        e
        for e in truth_of(result.latent, plan, result.c1_records, result.behaviour_log)
        if e.template_id == "count"
    ]
    assert (end.subtype, end.injected, end.confounder_group) == (
        "dose_omission",
        False,
        None,
    )
    # a forced double take is an injection with a record: the same limit events, now injected
    spec = c1_spec("double_take", 20 * HOUR)
    result = assemble(make_patient(baseline=130.0), schedule, [spec])
    limits = [
        e
        for e in truth_of(result.latent, plan, result.c1_records, result.behaviour_log)
        if e.template_id == "count"
    ]
    assert [(e.subtype, e.injected) for e in limits] == [("double_take", True)]


# ---------------------------------------------------------------------------------------------------
# Tests added after the mutation self-check (each kills at least one mutant of labelling.py)
# ---------------------------------------------------------------------------------------------------


def test_dense_mode_with_only_the_measurement_signal() -> None:
    day = ideal_observation(
        make_latent(measurements=(T(9),)), PLAN_ID, MODE_DENSE, signals=("meas",)
    )
    assert not day.samples
    assert times_of(day, EventKind.MEASUREMENT) == list(range(0, DAY, MIN))


def test_the_ceiling_rule_decides_which_readings_share_a_bin() -> None:
    # 12:00:00 is the step 720 and 12:00:30 the step 721 (an item is visible at ceil(t / T_s)): two bins
    ideal_observation(
        make_latent(measurements=(T(12), T(12, 0, 30))), PLAN_ID, step_ms=MIN
    )
    # 12:00:10 and 12:00:40 are both in (12:00, 12:01]
    with pytest.raises(IdealObservationError, match="bin"):
        ideal_observation(
            make_latent(measurements=(T(12, 0, 10), T(12, 0, 40))), PLAN_ID, step_ms=MIN
        )
    with pytest.raises(IdealObservationError, match="bin"):
        ideal_observation(
            make_latent(measurements=(T(12, 0, 1), T(12, 1))), PLAN_ID, step_ms=MIN
        )


def test_two_measurements_at_one_instant_are_refused() -> None:
    with pytest.raises(IdealObservationError, match="share one instant"):
        ideal_observation(make_latent(measurements=(T(12), T(12))), PLAN_ID)


def test_a_step_that_does_not_divide_the_day_is_refused() -> None:
    latent = make_latent(measurements=(T(12),))
    for bad in (7_000, 0, -MIN, 10**400, True, 1.5, "60000", DAY + 1):
        with pytest.raises(IdealObservationError):
            ideal_observation(latent, PLAN_ID, step_ms=bad)  # type: ignore[arg-type]
    with pytest.raises(IdealObservationError, match="divide"):
        ideal_observation(latent, PLAN_ID, step_ms=7_000)
    ideal_observation(latent, PLAN_ID, step_ms=DAY)  # one step a day divides it


def test_a_tick_outside_the_day_is_refused() -> None:
    base = make_latent(measurements=())
    for t in (-1, DAY + 1):
        tick = Event(EventKind.SCHEDULE_TICK, t, t, "ward", {"kind": "dose"}, None)
        with pytest.raises(IdealObservationError, match="day"):
            ideal_observation(dataclasses.replace(base, events=(tick,)), PLAN_ID)


def test_a_boolean_is_not_a_pressure() -> None:
    base = make_latent(measurements=(T(12),))
    samples = tuple(
        dataclasses.replace(s, value=True) if s.t_device_ms == T(12) else s
        for s in base.samples
    )
    with pytest.raises(IdealObservationError):
        ideal_observation(dataclasses.replace(base, samples=samples), PLAN_ID)


# --- configuration, registry and templates ------------------------------------------------------------


def test_the_configuration_is_checked() -> None:
    with pytest.raises(LabellingError, match="predictive"):
        label(config=make_config(predictive=True))
    with pytest.raises(LabellingError, match="predictive"):
        label(config=clone_with(CFG, predictive="no"))
    with pytest.raises(LabellingError, match="divide the day"):
        label(config=make_config(step_ms=7_000))
    for delay in (-1, DAY + 1, True, 1.5, None):
        with pytest.raises(LabellingError, match="reorder_delay_ms"):
            label(config=clone_with(CFG, reorder_delay_ms=delay))
    label(config=make_config(reorder_delay_ms=DAY))  # the largest delay
    with pytest.raises(LabellingError, match="config"):
        label(config="not a configuration")  # type: ignore[arg-type]


def test_a_missing_configuration_is_derived_from_the_registry() -> None:
    stub = Stub()
    label_latent_day(
        make_latent(measurements=(T(12),)), make_plan(), [], [], stub, None, None,
        MODE_SCHEDULED, registry=F0, templates=LIBRARY,
    )  # fmt: skip
    assert stub.calls[0]["config"] == CFG  # step 60000, no reorder delay, measured only
    # a registry that was not loaded with a step gives nothing to derive one from
    no_step = load_registry(F0_PATH, allow_fixture_only=True)
    with pytest.raises(LabellingError, match="step_ms"):
        label_latent_day(
            make_latent(measurements=(T(12),)), make_plan(), [], [], stub, None, None,
            MODE_SCHEDULED, registry=no_step, templates=LIBRARY,
        )  # fmt: skip
    with pytest.raises(LabellingError, match="step_ms"):
        label_latent_day(
            make_latent(), make_plan(), [], [], stub, None, None, MODE_SCHEDULED
        )


def test_a_library_without_a_care_plan_template_is_refused() -> None:
    others = [t for t in LIBRARY if t.kind is not TemplateKind.CARE_PLAN]
    assert others
    for library in (others, ()):
        with pytest.raises(LabellingError, match="phi_CP"):
            label(templates=library)
    with pytest.raises(LabellingError, match="Template"):
        label(templates=[object()])
    with pytest.raises(LabellingError, match="templates"):
        label(templates="templates")  # type: ignore[arg-type]


def test_only_the_signals_the_templates_use_are_supplied() -> None:
    range_only = [t for t in LIBRARY if t.id is TemplateId.RANGE]
    stub = Stub()
    label(
        run_fn=stub,
        templates=range_only,
        latent=make_latent(measurements=(T(12),), dispenses=(T(7),), ticks=(T(9),)),
    )
    day = stub.calls[0]["day"]
    assert {e.kind for e in day.events} == {EventKind.MEASUREMENT}
    assert {s.signal for s in day.samples} == {"bp"}  # no day_end, no dispense, no tick
    assert [t.id for t in stub.calls[0]["templates"]] == [TemplateId.RANGE]


def test_a_registry_that_cannot_be_loaded_is_a_named_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ralmon.spec import RegistryError, TemplateLibraryError

    def no_registry(*a: Any, **k: Any) -> Any:
        raise RegistryError("no such file")

    monkeypatch.setattr(labelling, "load_registry", no_registry)
    with pytest.raises(LabellingError, match="default registry cannot be loaded"):
        label(registry=None)

    def no_library(*a: Any, **k: Any) -> Any:
        raise TemplateLibraryError("broken library")

    monkeypatch.setattr(labelling, "load_templates", no_library)
    with pytest.raises(
        LabellingError, match="default template library cannot be loaded"
    ):
        label(templates=None)


def test_a_registry_object_must_have_get_and_version() -> None:
    class OnlyVersion:
        def version(self) -> str:
            return F0.version()

    class OnlyGet:
        def get(self, name: str) -> Any:
            return F0.get(name)

    class BadVersion(OnlyGet):
        def __init__(self, version: Any) -> None:
            self._version = version

        def version(self) -> Any:
            if isinstance(self._version, Exception):
                raise self._version
            return self._version

    with pytest.raises(LabellingError, match="get method"):
        label(registry=OnlyVersion())
    with pytest.raises(LabellingError, match="version method"):
        label(registry=OnlyGet())
    for version in (RuntimeError("x"), 5, None, ""):
        with pytest.raises(LabellingError):
            label(registry=BadVersion(version))


def test_the_window_length_must_be_a_positive_whole_number_of_milliseconds() -> None:
    def with_delta2(value: float) -> CarePlan:
        record = TemplateInstance(
            TemplateId.RESP, "resp-params", {"delta2": value}, None
        )
        return make_plan(parameter_records=(record,))

    resp = [violated("resp", f"resp@{T(7)}", T(10), T(10))]
    for bad in (0, -HOUR, 2 * HOUR + 0.5):
        with pytest.raises(LabellingError, match="delta2"):
            label(resp, plan=with_delta2(bad))
    [event] = label(
        resp, plan=with_delta2(2.0 * HOUR)
    )  # a whole number as a float is fine
    assert event.onset_ms == T(8)


# --- the verdict records -------------------------------------------------------------------------------


def test_more_incoherent_records_are_refused() -> None:
    plan = make_plan(sched=(T(9),))
    key = f"sched@{T(9)}"
    # decided before the day started (a SCHED anchor comes from the plan, so only this check sees it)
    before = vr(
        "sched", key, VerdictState.VIOLATED, T(9, 30), decided=-MIN, pending=T(9, 30)
    )
    with pytest.raises(RunnerError, match="outside this day"):
        label([before], plan=plan)
    # a deadline before the anchor
    early = violated("sched", key, T(9, 30), T(8))
    with pytest.raises(RunnerError, match="before its anchor"):
        label([early], plan=plan)
    # a negative deadline on a record that is not even violated
    negative = vr("resp", f"resp@{T(3)}", VerdictState.PENDING, T(3), pending=-1)
    with pytest.raises(RunnerError):
        label([negative])
    # a key longer than the bound, and one of exactly the bound
    with pytest.raises(RunnerError):
        label([violated("range", "k" * (labelling.MAX_TEXT + 1), T(12), T(12))])
    assert len(label([violated("range", "k" * labelling.MAX_TEXT, T(12), T(12))])) == 1
    # an empty key
    with pytest.raises(RunnerError):
        label([violated("range", "", T(12), T(12))])


def test_the_day_end_obligation_starts_at_its_plan_anchor() -> None:
    # decided a minute before the closing step (a hand-written record), anchored at the closing step
    [event] = label([violated("count", f"count@{DAY}", T(23, 59), DAY)])
    assert (event.onset_ms, event.end_ms, event.template_id) == (DAY, DAY, "count")


# --- injection records, behaviour log, bounds ---------------------------------------------------------


def test_an_unrealised_nonresponse_needs_no_intake_list() -> None:
    bare = c1_record("drug_nonresponse", T(11), T(13), realised=False, details={})
    [event] = label_noon("resp", [bare])
    assert (event.subtype, event.injected) == ("spontaneous_resp", False)


def test_the_latency_bound_function_is_checked() -> None:
    with pytest.raises(LabellingError, match="callable"):
        label(bound=5)  # type: ignore[arg-type]  # even when no record needs it
    with pytest.raises(LabellingError, match="latency bound"):
        label(
            [violated("range", f"range@{T(12)}", T(12), T(12))],
            injections=[spike_record()],
            bound=lambda t: -1,
        )
    for bad in (None, True, 1.5, "60000"):
        with pytest.raises(LabellingError, match="latency bound"):
            label(
                [violated("range", f"range@{T(12)}", T(12), T(12))],
                injections=[spike_record()],
                bound=lambda t, _b=bad: _b,  # type: ignore[arg-type,misc]
            )

    def failing(template: TemplateId) -> int:
        raise ValueError("no bound")

    with pytest.raises(LabellingError, match="latency_bound_fn failed"):
        label(
            [violated("range", f"range@{T(12)}", T(12), T(12))],
            injections=[spike_record()],
            bound=failing,
        )
    assert (
        label(
            [violated("range", f"range@{T(12)}", T(12), T(12))],
            injections=[spike_record()],
            bound=lambda t: 0,
        )[0].injected
        is True
    )


def test_records_and_behaviour_log_must_be_a_list_or_a_tuple() -> None:
    latent, plan = make_latent(measurements=(T(12),)), make_plan()

    def call(records: Any, behaviour: Any) -> Any:
        return label_latent_day(
            latent, plan, records, behaviour, Stub(), CFG, None, MODE_SCHEDULED,
            registry=F0, templates=LIBRARY,
        )  # fmt: skip

    for bad in (set(), frozenset(), iter(()), {}, "x", 5):
        with pytest.raises(LabellingError):
            call(bad, [])
        with pytest.raises(LabellingError):
            call([], bad)
    assert call((), ()) == () and call([], []) == ()


def test_intake_pairing_when_the_counts_differ() -> None:
    # more INTAKE events than DISPENSE events (a hand-written latent day): the dispense instant stands in
    extra = Event(EventKind.INTAKE, NOON + HOUR, NOON + HOUR, "patient", {}, None)
    latent = dataclasses.replace(NOON_LATENT, events=(*NOON_LATENT.events, extra))
    record = nonresponse_record([NOON], T(11), T(13))
    [event] = label([EVENT_RECORDS["resp"]], latent=latent, injections=[record])
    assert event.subtype == "drug_nonresponse"
    # fewer INTAKE events than DISPENSE events
    fewer = make_latent(
        measurements=(T(6),), dispenses=(NOON, NOON + 3 * HOUR), intakes=False
    )
    [event] = label([EVENT_RECORDS["resp"]], latent=fewer, injections=[record])
    assert event.subtype == "drug_nonresponse"


def test_the_resp_anchor_is_the_grid_step_of_the_dispense() -> None:
    # a dispense at 07:00:20 is visible at the step 07:01 (the ceiling rule): the instance is anchored there,
    # and the intake 5 s after the dispense belongs to it
    latent = make_latent(measurements=(T(6),), dispenses=(T(7, 0, 20),))
    resp = violated("resp", f"resp@{T(7, 0, 20)}", T(10, 1), T(10, 1))
    record = nonresponse_record([T(7, 0, 20) + LAG], T(7), T(8))
    [event] = label([resp], latent=latent, injections=[record])
    assert (event.onset_ms, event.subtype, event.injected) == (
        T(7, 1),
        "drug_nonresponse",
        True,
    )


def test_natural_double_take_needs_a_surplus_dispense_inside_the_counter_window() -> (
    None
):
    limit = violated("count", f"count@{T(20)}", T(20), T(20))
    # the surplus of the slot (20:02) comes after the decision at 20:00 and its first dispense is not a surplus
    entry = BehaviourEntry(T(20), 0, AdherenceState.DOUBLE_TAKE, (T(20), T(20, 2)))
    [event] = label([limit], behaviour=[entry])
    assert event.subtype == "spontaneous_count"
    # a surplus more than 24 h before the decision (here exactly 24 h) is out of the window
    old = BehaviourEntry(-2 * MIN, 0, AdherenceState.DOUBLE_TAKE, (-2 * MIN, 0))
    at_end = violated("count", f"count@{DAY}#2", DAY, DAY)
    [event] = label([at_end], behaviour=[old])
    assert event.subtype == "spontaneous_count"
    # an entry that is not a double take is not one, whatever its dispenses
    other = BehaviourEntry(T(20), 0, AdherenceState.ON_TIME, (T(20), T(20, 2)))
    [event] = label(
        [violated("count", f"count@{T(20, 2)}", T(20, 2), T(20, 2))], behaviour=[other]
    )
    assert event.subtype == "spontaneous_count"


def test_the_labeller_refuses_two_readings_in_one_bin() -> None:
    close = make_latent(measurements=(T(12, 0, 10), T(12, 0, 40)))
    with pytest.raises(IdealObservationError, match="bin"):
        label(latent=close)


def test_the_default_mode_of_every_entry_point_is_scheduled() -> None:
    for function in (
        label_latent_day,
        label_latent_day_detailed,
        assemble_benchmark_day,
    ):
        assert inspect.signature(function).parameters["mode"].default == MODE_SCHEDULED
    assert (
        inspect.signature(ideal_observation).parameters["mode"].default
        == MODE_SCHEDULED
    )


def test_assemble_refuses_an_observed_day_that_is_not_valid() -> None:
    _out, observed, result, plan, records = assembled_fixture()
    unsorted = dataclasses.replace(observed, samples=tuple(reversed(observed.samples)))
    assert [s.t_rx_ms for s in unsorted.samples] != sorted(
        s.t_rx_ms for s in unsorted.samples
    )
    with pytest.raises(LabellingError, match="invalid"):
        assemble_benchmark_day(
            unsorted, result.latent, plan, records, result.behaviour_log, None, CFG, None,
            MODE_SCHEDULED, registry=F0, templates=LIBRARY,
        )  # fmt: skip


def test_the_latent_day_index_and_the_plan_are_checked() -> None:
    base = make_latent(measurements=(T(12),))
    for day_index in (True, 1.5, None):
        with pytest.raises(IdealObservationError):
            ideal_observation(clone_with(base, day_index=day_index), PLAN_ID)
    # a day before the first, and one after the last, whose items lie on their own axis
    for day_index in (-1, labelling.MAX_DAY_INDEX + 1):
        with pytest.raises(IdealObservationError, match="day_index"):
            ideal_observation(make_latent(day_index, measurements=(T(12),)), PLAN_ID)
    # the earliest and the latest day are fine (nothing in the day is outside its own axis)
    ideal_observation(
        make_latent(labelling.MAX_DAY_INDEX, measurements=(T(12),)), PLAN_ID
    )
    # a plan with a repeated key, two parameter records of one template, or an instance of no template
    twice = make_plan(sched=(T(9),))
    instance = twice.instances[0]
    for bad in (
        clone_with(twice, instances=(*twice.instances, instance)),
        clone_with(
            twice,
            instances=(
                *twice.instances,
                TemplateInstance(TemplateId.RESP, "a", {}, None),
                TemplateInstance(TemplateId.RESP, "b", {}, None),
            ),
        ),
        clone_with(twice, instances=(clone_with(instance, template="sched"),)),
        clone_with(
            twice,
            instances=(clone_with(instance, anchor_ms=None, param_values=[1]),),
        ),
        clone_with(
            twice,
            instances=(clone_with(instance, anchor_ms=None, param_values={1: 2.0}),),
        ),
        clone_with(
            twice,
            instances=(clone_with(instance, anchor_ms=None, param_values={"a": True}),),
        ),
    ):
        with pytest.raises(LabellingError):
            label(plan=bad)
    with pytest.raises(LabellingError, match="CarePlan"):
        label(plan="plan")  # type: ignore[arg-type]


def test_a_signal_selection_must_be_a_collection() -> None:
    latent = make_latent(measurements=(T(12),))
    for bad in (iter(("bp",)), (s for s in ("bp",)), "bp", 5, {"bp": 1}):
        with pytest.raises(IdealObservationError, match="collection"):
            ideal_observation(latent, PLAN_ID, signals=bad)  # type: ignore[arg-type]
    for good in (("bp",), ["bp"], {"bp"}, frozenset({"bp"})):
        assert bp_pairs(ideal_observation(latent, PLAN_ID, signals=good)) == [
            (T(12), 130.0)
        ]


def test_a_behaviour_entry_must_have_a_state() -> None:
    entry = BehaviourEntry(T(7), 0, AdherenceState.ON_TIME, (T(7),))
    for bad in (
        clone_with(entry, state="OMITTED"),
        clone_with(entry, state=None),
        clone_with(entry, day_index=True),
        clone_with(entry, slot_tick_ms=1.5),
        clone_with(entry, dispense_times_ms=5),
        clone_with(entry, dispense_times_ms=(True,)),
    ):
        with pytest.raises(LabellingError):
            label([], behaviour=[bad])


def test_the_order_of_the_latent_events_does_not_matter() -> None:
    forward = NOON_LATENT
    backward = dataclasses.replace(forward, events=tuple(reversed(forward.events)))
    record = nonresponse_record([NOON + LAG], T(11), T(13))
    expected = label([EVENT_RECORDS["resp"]], latent=forward, injections=[record])
    assert expected[0].subtype == "drug_nonresponse"
    assert (
        label([EVENT_RECORDS["resp"]], latent=backward, injections=[record]) == expected
    )
    assert ideal_observation(backward, PLAN_ID) == ideal_observation(forward, PLAN_ID)


def test_a_collection_that_claims_a_huge_length_is_refused_before_it_is_read() -> None:
    latent = make_latent(measurements=(T(12),))
    with pytest.raises(IdealObservationError, match="more than"):
        ideal_observation(latent, PLAN_ID, signals=GrowingList())  # type: ignore[arg-type]
    for bad in (GrowingList(), GrowingList([1])):
        with pytest.raises(LabellingError, match="more than"):
            label_latent_day(
                latent, make_plan(), bad, [], Stub(), CFG, None, MODE_SCHEDULED,
                registry=F0, templates=LIBRARY,
            )  # fmt: skip
        with pytest.raises(LabellingError, match="more than"):
            label_latent_day(
                latent, make_plan(), [], bad, Stub(), CFG, None, MODE_SCHEDULED,
                registry=F0, templates=LIBRARY,
            )  # fmt: skip
        with pytest.raises(LabellingError, match="more than"):
            label_latent_day(
                latent, make_plan(), [], [], Stub(), CFG, None, MODE_SCHEDULED,
                registry=F0, templates=bad,
            )  # fmt: skip
        with pytest.raises(RunnerError, match="more than"):
            label(run_fn=lambda *a, _b=bad, **k: _b)
        with pytest.raises(LabellingError, match="more than"):
            label(latent=clone_with(latent, samples=bad))
        with pytest.raises(LabellingError, match="more than"):
            label(latent=clone_with(latent, events=bad))
        with pytest.raises(LabellingError, match="more than"):
            label(plan=clone_with(make_plan(), instances=bad))


def test_real_monitor_refinement_records_give_one_event() -> None:
    # the monitor keeps emitting records of a SCHED instance after its decision (the graded lateness): the
    # first VIOLATED record defines the event and the later ones add nothing
    case = next(c for c in CASES if c["id"] == "GT-05-sched-deadline")
    latent, plan = case_latent(case, 0), case_plan(case, 0)
    ideal = ideal_observation(latent, PLAN_ID, step_ms=MIN)
    records = run_offline(
        ideal, plan, CFG, None, None, registry=F0, templates=CP_TEMPLATES
    )
    key = f"sched@{clock('12:00')}"
    violated_records = [
        r for r in records if r.instance_key == key and r.state is VerdictState.VIOLATED
    ]
    assert len(violated_records) > 1  # the refinement records
    first = violated_records[0]
    assert first.t_eval_ms == first.decided_at_ms == clock("12:30")
    assert all(
        r.decided_at_ms == first.decided_at_ms
        and r.pending_until_ms == first.pending_until_ms
        for r in violated_records
    )
    assert (
        len({r.sigma_interval for r in violated_records}) > 1
    )  # the interval refines, the decision does not
    events = [e for e in truth_of(latent, plan) if e.onset_ms == clock("12:00")]
    assert [(e.template_id, e.end_ms) for e in events] == [("sched", clock("12:30"))]
    # every record of the real run carries pending_until_ms (OP-T05-17), RANGE and HOLD included
    assert all(r.pending_until_ms is not None for r in records)
