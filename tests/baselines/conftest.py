"""Hand-written fixtures of the baseline harness tests (WS06-T01).

FIXTURE-ONLY. Every number is arithmetic chosen so that results can be computed by hand: band 110 to 140
mmHg, hold threshold 100 mmHg and dose limit 2 are the illustrative numbers of analisi section 4.1
("illustrative, unverified"), and the 30 min window is chosen for these tests only. None of it is a clinical
value. Signal names in the harness tests are opaque strings: the harness never looks at what a signal means.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import pytest

from ralmon.attribution import Detection, EvidenceVector
from ralmon.baselines.base import BaselineBase, TimingConfig
from ralmon.benchmark import (
    BenchmarkDay,
    GroundTruthEvent,
    InjectedClass,
    LatentDay,
    ObservedDay,
)
from ralmon.signals import Event, EventKind, Sample
from ralmon.spec import CarePlan, PhysioBounds, RegistryEntry, TemplateInstance
from ralmon.spec.templates import TemplateId

STEP_MS = 60_000


def make_sample(
    signal: str = "s",
    t_device_ms: int = 0,
    t_rx_ms: int | None = None,
    value: float = 1.0,
    seq: int | None = None,
    quality: float | None = None,
) -> Sample:
    rx = t_device_ms if t_rx_ms is None else t_rx_ms
    return Sample(signal, t_device_ms, rx, value, seq, quality)


def make_event(
    kind: EventKind = EventKind.MEASUREMENT,
    t_device_ms: int = 0,
    t_rx_ms: int | None = None,
    source: str = "dev",
    payload: Mapping[str, float | int | str | bool] | None = None,
    seq: int | None = None,
) -> Event:
    rx = t_device_ms if t_rx_ms is None else t_rx_ms
    return Event(kind, t_device_ms, rx, source, dict(payload or {}), seq)


def make_observed_day(
    samples: Sequence[Sample] = (),
    events: Sequence[Event] = (),
    *,
    patient_id: str = "p1",
    day_index: int = 0,
    seed: int = 0,
    care_plan_id: str = "plan-1",
) -> ObservedDay:
    return ObservedDay(
        patient_id, day_index, seed, tuple(samples), tuple(events), care_plan_id
    )


def make_ground_truth() -> tuple[GroundTruthEvent, ...]:
    return (
        GroundTruthEvent(
            InjectedClass.C1, "fixture_event", 1_000, None, True, "range", None
        ),
    )


def make_benchmark_day(
    samples: Sequence[Sample] = (),
    events: Sequence[Event] = (),
    *,
    patient_id: str = "p1",
    day_index: int = 0,
    ground_truth: Sequence[GroundTruthEvent] | None = None,
) -> BenchmarkDay:
    observed = make_observed_day(
        samples, events, patient_id=patient_id, day_index=day_index
    )
    latent = LatentDay(
        patient_id, day_index, 0, (make_sample("latent_s", 0, 0, 9.0),), ()
    )
    truth = make_ground_truth() if ground_truth is None else tuple(ground_truth)
    return BenchmarkDay(observed, latent, truth)


def make_care_plan(
    instances: Sequence[TemplateInstance] = (),
    schedule: Sequence[int] = (),
    *,
    patient_id: str = "p1",
) -> CarePlan:
    return CarePlan(
        "plan-1",
        "pathway-1",
        patient_id,
        "0.0.0",
        tuple(instances),
        tuple(schedule),
        1,
        None,
    )


def make_instance(
    template: TemplateId,
    instance_key: str,
    params: Mapping[str, float],
    anchor_ms: int | None = None,
) -> TemplateInstance:
    return TemplateInstance(template, instance_key, dict(params), anchor_ms)


class StubRegistry:
    """A test-local ``ParameterRegistry``; names are entry names of the registry files (test 21)."""

    ENTRIES: Mapping[str, float] = {
        "bp_band_low": 110.0,  # illustrative, unverified (analisi 4.1)
        "bp_band_high": 140.0,  # illustrative, unverified (analisi 4.1)
        "bp_hold_threshold": 100.0,  # illustrative, unverified (analisi 4.1)
        "dose_max_24h": 2.0,  # illustrative, unverified (analisi 4.1)
        "delta2": 30 * 60_000.0,  # window chosen for these tests only
    }
    BOUNDS: Mapping[str, tuple[str, str]] = {"bp": ("bound_bp_lower", "bound_bp_upper")}
    BOUND_VALUES: Mapping[str, float] = {
        "bound_bp_lower": 50.0,
        "bound_bp_upper": 250.0,
    }

    def get(self, name: str) -> RegistryEntry:
        if name not in self.ENTRIES:
            raise KeyError(name)
        return RegistryEntry(
            name,
            self.ENTRIES[name],
            "1",
            "illustrative, unverified",
            "FIXTURE-ONLY: tests/baselines/conftest.py",
            None,
        )

    def bounds(self, signal: str) -> PhysioBounds:
        low, high = self.BOUNDS[signal]
        return PhysioBounds(signal, self.BOUND_VALUES[low], self.BOUND_VALUES[high])

    def version(self) -> str:
        return "0.0.0"

    def names(self) -> frozenset[str]:
        """Every registry name this stub can answer (entries and the two bound entries)."""
        names = set(self.ENTRIES)
        for low, high in self.BOUNDS.values():
            names.update((low, high))
        return frozenset(names)


@pytest.fixture
def stub_registry() -> StubRegistry:
    return StubRegistry()


class RecordingBaseline(BaselineBase):
    """A minimal subclass: records its `_fit` calls and emits what the test tells it to."""

    name = "STUB"

    def __init__(
        self,
        timing: TimingConfig | None = None,
        *,
        output: Sequence[Detection] = (),
        **kwargs: Any,
    ) -> None:
        super().__init__(timing or TimingConfig(STEP_MS, 0, 0), **kwargs)
        self.output = tuple(output)
        self.fit_calls: list[tuple[tuple[Any, ...], tuple[Any, ...]]] = []
        self.state: Any = None

    def _fit(self, train: Any, calib: Any) -> None:
        self.fit_calls.append((tuple(train), tuple(calib)))
        self.state = (len(train), len(calib))

    def _run(self, day: ObservedDay, plan: CarePlan) -> Sequence[Detection]:
        return self.output


def evidence_mapping() -> Mapping[str, EvidenceVector]:
    """A non-empty mapping standing for evidence; the harness must drop it unread."""
    return {"k": object()}  # type: ignore[dict-item]


# ---- fixtures of the fairness audit (WS06-T07) -----------------------------------------------------------------------
#
# FIXTURE-ONLY. The parameter values of the audit plans are the rows of the fixture registry F0 (illustrative,
# unverified, ADR-027), the operating parameters below are test values and none is a clinical or tuned value. The
# builders are plain functions so that the audit note can be regenerated outside pytest (see ``render_audit_note``
# in ``test_fairness_audit.py``); the pytest fixtures wrap them.

AUDIT_STEP_MS = STEP_MS
AUDIT_DELAY_MS = (
    2 * STEP_MS
)  # a multiple of the step (open decision: D not a multiple of the step)
AUDIT_TAIL_MS = 25 * 60 * STEP_MS  # covers the longest window and the day-end COUNT
AUDIT_TIMING = TimingConfig(AUDIT_STEP_MS, AUDIT_DELAY_MS, AUDIT_TAIL_MS)
T_DAY_MS = 86_400_000
AUDIT_ALPHA = 0.2  # test value
AUDIT_Z_THRESHOLD = 3.0  # test value
AUDIT_SCORE_QUANTILE = 0.9  # test value
AUDIT_FEATURE_STEP_MS = 3_600_000  # one forest row an hour: 24 rows a day (test value)
ACT_STEP = 10  # step of the dose of the calibration days
TICK_STEP = 75  # a measurement tick inside the response window of that dose
# drops of the calibration days (R = drop for the response template); n = 19, so that alpha = 0.05 and 0.2 both give
# a finite constant (k = 19 and k = 16): 10 and 7 (hand computation in test_conformal_baselines_monotone_in_alpha)
CALIB_DROPS = (0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 10)
PRE_DOSE_BP = 150.0

# parameter names of the six templates that the plan carries as parameter records (anchor None)
_RECORD_PARAMS: Mapping[str, tuple[str, ...]] = {
    "range": ("bp_band_low", "bp_band_high"),
    "hold": ("bp_hold_threshold", "hold_lookback"),
    "count": ("dose_max_24h", "dose_min_day_end"),
    "resp": ("delta1", "delta2", "delta_resp"),
    "sys": ("cuff_inflation_min",),
    "int": ("int_window",),
}


def audit_registry() -> Any:
    """The fixture registry F0 (FIXTURE-ONLY, ADR-027) loaded on the audit step."""
    from tests.monitor.helpers import load_f0

    return load_f0(AUDIT_STEP_MS)


def audit_templates(registry: Any) -> tuple[Any, ...]:
    from ralmon.spec import load_templates

    return tuple(load_templates(registry=registry))


def make_full_plan(
    registry: Any,
    *,
    sched_steps: Sequence[int] = (480, 840),
    day_end: bool = True,
    ticks: Sequence[int] = (485, 555, 605),  # the dose ticks of the test day
    patient_id: str = "p1",
) -> CarePlan:
    """A plan with the seven templates: a parameter record (anchor None) for RANGE, HOLD, COUNT, RESP, SYS and INT, one
    anchored SCHED instance per ``sched_steps`` entry with its own window, and the day-end COUNT at 24 h."""
    instances: list[TemplateInstance] = []
    for name, params in _RECORD_PARAMS.items():
        instances.append(
            make_instance(
                TemplateId(name),
                f"record-{name}",
                {p: float(registry.get(p).value) for p in params},
            )
        )
    window = float(registry.get("sched_window").value)
    for step in sched_steps:
        instances.append(
            make_instance(
                TemplateId.SCHED,
                f"sched@{step}",
                {"sched_window": window},
                step * STEP_MS,
            )
        )
    if day_end:
        instances.append(
            make_instance(
                TemplateId.COUNT,
                "count-day-end",
                {p: float(registry.get(p).value) for p in _RECORD_PARAMS["count"]},
                T_DAY_MS,
            )
        )
    return CarePlan(
        "plan-1",
        "pathway-1",
        patient_id,
        registry.version(),
        tuple(instances),
        tuple(step * STEP_MS for step in sorted(set(sched_steps) | set(ticks))),
        1,
        None,
    )


def _audit_sample(signal: str, step: int, value: float) -> Sample:
    return Sample(signal, step * STEP_MS, step * STEP_MS, float(value), None, None)


def _audit_event(kind: EventKind, step: int) -> Event:
    return Event(kind, step * STEP_MS, step * STEP_MS, "dev", {}, None)


def audit_test_day(patient_id: str = "p1") -> ObservedDay:
    """The day every detector runs on: a day with a violation of each of the seven templates in the monitor's sense
    (the hand-built day of the B3 tests), plus a heart rate and a saturation every 30 minutes (the signals that B2 and
    B4 monitor besides blood pressure)."""

    def m(h: int, mm: int = 0) -> int:
        return 60 * h + mm

    samples = [
        _audit_sample("bp", m(8), 150.0),
        _audit_sample("cuff_health", m(8), 0.0),
        _audit_sample("inflation_ms", m(8), 40000.0),
        _audit_sample("bp", m(9, 10), 95.0),
        _audit_sample("cuff_health", m(9, 10), 1.0),
        _audit_sample("bp", m(10), 130.0),
        _audit_sample("bp", m(11, 30), 118.0),
        _audit_sample("presence", m(8, 3), 1.0),
        _audit_sample("bp", m(14, 40), 125.0),
        _audit_sample("cuff_health", m(14, 40), 1.0),
        _audit_sample("inflation_ms", m(14, 40), 40000.0),
    ]
    for k in range(48):
        samples.append(_audit_sample("hr_ecg", 30 * k, 70.0 + (k % 5)))
        samples.append(_audit_sample("spo2", 30 * k, 96.0 + (k % 3)))
    events = [
        _audit_event(EventKind.MEASUREMENT, m(8)),
        _audit_event(EventKind.DISPENSE, m(8, 5)),
        _audit_event(EventKind.INTAKE, m(8, 6)),
        _audit_event(EventKind.MEASUREMENT, m(9, 10)),
        _audit_event(EventKind.DISPENSE, m(9, 15)),
        _audit_event(EventKind.DISPENSE, m(10, 5)),
        _audit_event(EventKind.MEASUREMENT, m(10)),
        _audit_event(EventKind.MEASUREMENT, m(11, 30)),
        _audit_event(EventKind.MEASUREMENT, m(14, 40)),
    ]
    samples.sort(key=lambda s: s.t_rx_ms)
    events.sort(key=lambda e: e.t_rx_ms)
    return make_observed_day(samples, events, patient_id=patient_id)


def response_day(drop: float, patient_id: str, *, extra: float = 0.0) -> ObservedDay:
    """A day with one dose at ``ACT_STEP``, the pre-dose pressure 150 and, at the tick, 150 - drop - extra."""
    return make_observed_day(
        [
            _audit_sample("bp", 0, PRE_DOSE_BP),
            _audit_sample("bp", TICK_STEP, PRE_DOSE_BP - drop - extra),
        ],
        [
            _audit_event(EventKind.DISPENSE, ACT_STEP),
            _audit_event(EventKind.MEASUREMENT, TICK_STEP),
        ],
        patient_id=patient_id,
    )


class PoisonedBenchmarkDay(BenchmarkDay):
    """A benchmark day whose latent trace and ground truth raise on any access (fixture ``poisoned_benchmark_days``)."""

    def __init__(self, observed_day: ObservedDay) -> None:
        object.__setattr__(self, "observed", observed_day)

    @property  # type: ignore[override]
    def latent(self) -> Any:
        raise AssertionError("the latent trace was read")

    @property  # type: ignore[override]
    def ground_truth(self) -> Any:
        raise AssertionError("the ground truth was read")


def poisoned_days() -> tuple[list[BenchmarkDay], list[BenchmarkDay]]:
    """Two training days and one calibration day per entry of ``CALIB_DROPS``; latent and truth raise on access."""
    train = [PoisonedBenchmarkDay(response_day(3.0, f"train{i}")) for i in range(2)]
    calib = [
        PoisonedBenchmarkDay(response_day(float(d), f"calib{i}"))
        for i, d in enumerate(CALIB_DROPS)
    ]
    return train, calib


def audit_plan_for_day(registry: Any) -> Callable[[ObservedDay], CarePlan]:
    """The function that gives B2 and B5 (and the proposed method) the care plan of a training or calibration day."""

    def plan_for_day(day: ObservedDay) -> CarePlan:
        return make_full_plan(
            registry,
            sched_steps=(TICK_STEP,),
            day_end=False,
            ticks=(ACT_STEP,),
            patient_id=day.patient_id,
        )

    return plan_for_day


@dataclass
class AuditSetup:
    """The five baselines of one audit, built from one timing configuration, and the probes of their forecasters."""

    detectors: dict[str, BaselineBase]
    probes: dict[str, Any]
    registry: Any
    templates: tuple[Any, ...]
    plan_for_day: Callable[[ObservedDay], CarePlan]


def build_audit_setup(*, alpha: float = AUDIT_ALPHA) -> AuditSetup:
    """B1 to B5 as the experiment configures them: one timing, one persistence forecaster class per baseline that has
    one (wrapped in a probe), the calibrator of the proposed method, the operating parameters of the fixture."""
    from ralmon.baselines.audit import ForecasterProbe

    from ralmon.baselines import (
        B1StaticThresholds,
        B2AnomalyDetection,
        B3PlainSTL,
        B4ConformalOnly,
        B5ConformalSTL,
    )
    from ralmon.conformal import SplitConformal
    from ralmon.monitor import PersistenceForecaster

    registry = audit_registry()
    templates = audit_templates(registry)
    plan_for_day = audit_plan_for_day(registry)
    probes = {
        name: ForecasterProbe(PersistenceForecaster(AUDIT_STEP_MS))
        for name in ("B2", "B4", "B5")
    }
    detectors: dict[str, BaselineBase] = {
        "B1": B1StaticThresholds(timing=AUDIT_TIMING, registry=registry),
        "B2": B2AnomalyDetection(
            probes["B2"],
            mode="both",
            z_threshold=AUDIT_Z_THRESHOLD,
            score_quantile=AUDIT_SCORE_QUANTILE,
            seed=0,
            feature_step_ms=AUDIT_FEATURE_STEP_MS,
            timing=AUDIT_TIMING,
            plan_for_day=plan_for_day,
        ),
        "B3": B3PlainSTL(templates, registry, timing=AUDIT_TIMING),
        "B4": B4ConformalOnly(
            probes["B4"], SplitConformal, alpha=alpha, timing=AUDIT_TIMING
        ),
        "B5": B5ConformalSTL(
            templates,
            registry,
            probes["B5"],
            SplitConformal,
            alpha=alpha,
            timing=AUDIT_TIMING,
            plan_for_day=plan_for_day,
        ),
    }
    return AuditSetup(detectors, probes, registry, templates, plan_for_day)


@pytest.fixture
def audit_setup() -> AuditSetup:
    return build_audit_setup()


@pytest.fixture
def all_baselines(audit_setup: AuditSetup) -> dict[str, BaselineBase]:
    """B1 to B5, unfitted, keyed by name."""
    return audit_setup.detectors


@pytest.fixture
def full_plan(audit_setup: AuditSetup) -> CarePlan:
    return make_full_plan(audit_setup.registry)


@pytest.fixture
def poisoned_benchmark_days() -> tuple[list[BenchmarkDay], list[BenchmarkDay]]:
    """(training days, calibration days) whose latent trace and ground truth raise on any access."""
    return poisoned_days()


# ---- the audit run and the probes (WS06-T07) -------------------------------------------------------------------------


def _event(
    kind: EventKind, step: int, *, seq: int | None = None, rx_step: int | None = None
) -> Event:
    rx = step if rx_step is None else rx_step
    return Event(kind, step * STEP_MS, rx * STEP_MS, "dev", {}, seq)


def _sample(
    signal: str, step: int, value: float, *, rx_step: int | None = None
) -> Sample:
    rx = step if rx_step is None else rx_step
    return Sample(signal, step * STEP_MS, rx * STEP_MS, float(value), None, None)


def _day(
    samples: Sequence[Sample],
    events: Sequence[Event],
    *,
    day_index: int = 0,
) -> ObservedDay:
    return make_observed_day(
        sorted(samples, key=lambda s: s.t_rx_ms),
        sorted(events, key=lambda e: e.t_rx_ms),
        day_index=day_index,
    )


def audit_probes(registry: Any) -> list[Any]:
    """The perturbation probes: each is a control day and a perturbed day that differ in one thing only, so that the
    detections added by the perturbation are the size of an asymmetry between the baselines and the monitor."""
    from ralmon.baselines.audit import Probe

    plan = make_full_plan(registry, sched_steps=(), day_end=False, ticks=())
    in_band = [_sample("bp", 0, 125.0)]

    # 1. duplicate deliveries: two doses (the limit is 2), each delivered twice with the same sequence number
    once = [
        _event(EventKind.DISPENSE, 10, seq=1),
        _event(EventKind.DISPENSE, 20, seq=2),
    ]
    twice = [
        *once,
        _event(EventKind.DISPENSE, 10, seq=1),
        _event(EventKind.DISPENSE, 20, seq=2),
    ]
    # 2. a pressure of 160 mmHg received 10 steps after its time (late for the monitor at a delay of 2 steps)
    late_bp = [
        _sample("bp", 100, 160.0, rx_step=110),
    ]
    late_meas = [_event(EventKind.MEASUREMENT, 100, rx_step=110)]
    # 3. a pressure of 160 mmHg stamped 200 steps in the future (the monitor rejects a future stamp)
    future_bp = [_sample("bp", 300, 160.0, rx_step=100)]
    future_meas = [_event(EventKind.MEASUREMENT, 300, rx_step=100)]
    # 4. a dose at 23:00 with no response measurement: the window closes after midnight
    evening = [_event(EventKind.DISPENSE, 1380), _event(EventKind.MEASUREMENT, 1370)]
    evening_bp = [_sample("bp", 1370, 125.0)]
    # 5. the INT blind spot (ADR-063): the robot is co-located from step 470, sees nobody (presence 0) or the patient
    colocated = Event(
        EventKind.NODE_STATE,
        470 * STEP_MS,
        470 * STEP_MS,
        "robot",
        {"state": "active", "colocated": True},
        None,
    )
    int_events = [colocated, _event(EventKind.DISPENSE, 480)]
    seen = [_sample("presence", m, 1.0) for m in range(470, 480)]
    unseen = [_sample("presence", m, 0.0) for m in range(470, 480)]
    # 6. cross-midnight state: two doses at 23:00 and 23:30 of the day before and one at 00:30
    previous = _day(
        [], [_event(EventKind.DISPENSE, 1380), _event(EventKind.DISPENSE, 1410)]
    )
    next_day = _day([], [_event(EventKind.DISPENSE, 1470)], day_index=1)
    return [
        Probe(
            "duplicate deliveries",
            _day(in_band, once),
            _day(in_band, twice),
            plan,
            "asymmetry (b): the monitor deduplicates by (source, name, seq), the harness does not",
        ),
        Probe(
            "late input",
            _day(
                [*in_band, _sample("bp", 100, 125.0)],
                [_event(EventKind.MEASUREMENT, 100)],
            ),
            _day([*in_band, *late_bp], late_meas),
            plan,
            "asymmetry (a): the monitor excludes a late input; the baselines drop it by the rule of the grid",
        ),
        Probe(
            "future-stamped input",
            _day(in_band, []),
            _day([*in_band, *future_bp], future_meas),
            plan,
            "asymmetry (c): the monitor rejects an input stamped in the future; the harness delivers it at its time",
        ),
        Probe(
            "deadline after midnight",
            _day([*in_band, *evening_bp], [_event(EventKind.MEASUREMENT, 1370)]),
            _day([*in_band, *evening_bp], evening),
            plan,
            "the window of a late dose closes after the day: the per-day monitor ends PENDING",
        ),
        Probe(
            "integrity violation without a point value",
            _day(seen, int_events),
            _day(unseen, int_events),
            plan,
            "ADR-063: the point evaluator has no value for an interval whose upper bound is negative",
        ),
        Probe(
            "state across midnight",
            next_day,
            next_day,
            plan,
            "ADR-061: the trailing 24 h counter needs the day before; Detector.run has no history input",
            history=(previous,),
        ),
    ]


@dataclass
class Audit:
    """Everything one audit run produces, shared by the tests of the module and by the note generator."""

    setup: AuditSetup
    days: Any
    plan: CarePlan
    proposed: Any
    report: Any
    probes: list[Any]
    probe_results: list[Any]


def build_audit() -> Audit:
    from ralmon.baselines.audit import (
        AuditDays,
        ForecasterProbe,
        ProposedMethod,
        run_audit,
        run_probe,
    )

    from ralmon.conformal import SplitConformal
    from ralmon.monitor import MonitorConfig, PersistenceForecaster

    setup = build_audit_setup()
    train, calib = poisoned_days()
    plan = make_full_plan(setup.registry)
    days = AuditDays(train, calib, audit_test_day())
    config = MonitorConfig(
        AUDIT_STEP_MS,
        AUDIT_DELAY_MS,
        True,
        AUDIT_ALPHA,
        "likely",
        setup.registry.version(),
    )
    forecaster = ForecasterProbe(PersistenceForecaster(AUDIT_STEP_MS))
    proposed = ProposedMethod(
        config, setup.templates, forecaster, setup.plan_for_day, SplitConformal
    )
    report = run_audit(
        list(setup.detectors.values()),
        days,
        plan,
        setup.registry,
        templates=setup.templates,
        proposed=proposed,
        probes=setup.probes,
    )
    probes = audit_probes(setup.registry)
    results = [
        run_probe(list(setup.detectors.values()), probe, setup.registry, proposed)
        for probe in probes
    ]
    return Audit(setup, days, plan, proposed, report, probes, results)


def render_audit_blocks() -> tuple[str, str]:
    """The two generated blocks of the audit note: the knowledge matrix and the probe table."""
    from ralmon.baselines.audit import render_markdown, render_probe_table

    audit = build_audit()
    return render_markdown(audit.report), render_probe_table(audit.probe_results)
