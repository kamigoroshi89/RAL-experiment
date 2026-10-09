"""C1 injection, latent day assembly and the deliberate confounder pairs (WS04-T09).

Every number below is arithmetic and FIXTURE-ONLY (constant baseline 130 with zero autoregressive
noise for the exact-value tests, a baseline with a circadian component and noise for the paired-design
tests, the PK/PD fixture ``ka = 2 per h, ke = 1 per h, Emax = 20, EC50 = 0.25``, an intake lag of 5 s,
a double-take gap of 2 min, a sub-second bounce gap of 500 ms, a robot dwell of 10 min): none is a
clinical value, none is a device specification and none enters a prior file used by the builder.
State independence: no test reads a committed configuration in a way that depends on whether a human
has filled it; the design rows are exercised on copies under ``tmp_path`` in both states.

Rules under test (``ralmon.benchmark.inject_c1``, ``latent_day`` and ``confounders``):

* C1 changes the LATENT day and returns ``InjectionRecord`` values; C1 truth is computed by the
  labeller (WS04-T10) on the latent trace, so nothing here constructs a ``GroundTruthEvent``;
* windows are half open, ``[onset, onset + duration)`` (``docs/models/fault-model.md``, boundary
  convention), on the integer-ms grid of the latent day;
* a call over ``n`` days equals consecutive calls that carry the state (autoregressive noise, adherence
  chain, drug accumulation); there is no reset at midnight;
* a member of a confounder pair differs from the other only in the labelled mechanism: same patient,
  baseline, cuff noise draws and schedule.
"""

from __future__ import annotations

import ast
import copy
import dataclasses
import functools
import inspect
import itertools
import json
import math
import os
import re
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

import ralmon.benchmark as benchmark_pkg
import ralmon.benchmark.confounders as confounders_mod
import ralmon.benchmark.inject_c1 as c1_mod
import ralmon.benchmark.latent_day as latent_day_mod
from ralmon.benchmark import vocab
from ralmon.benchmark.adherence import (
    AdherenceConfig,
    AdherenceModel,
    AdherenceState,
)
from ralmon.benchmark.confounders import (
    DISCRIMINATORS,
    GROUP_DOUBLE_TAKE_VS_BOUNCE,
    GROUP_NONRESPONSE_VS_FORGERY,
    GROUP_REFUSAL_VS_ROBOT_MISSED,
    GROUPS,
    WITHHOLDABLE,
    ConfounderError,
    PairBase,
    PairEvaluation,
    RealisedScenario,
    Scenario,
    Variant,
    build_confounder_pair,
    compare_observed,
    confounder_log,
    evaluate_pair,
    load_confounder_design,
    realise_scenario,
)
from ralmon.benchmark.inject_c1 import (
    C1_SUBTYPES,
    REFERENCE_HOLD_DISTANCE,
    REFERENCE_SCALE_RANGE,
    UNIT_MMHG,
    UNIT_SCALE,
    C1InjectionError,
    LatentWork,
    c1_spec,
    c1_spec_from_level,
    c1_stream,
    canonical_c1_order,
    check_c1_specs,
    double_take,
    drug_nonresponse,
    hold_distance_mmhg,
    hypertensive_spike,
    hypotension_below_hold,
    load_c1_design,
    measurement_refusal,
    observe_refusals,
    resolve_c1_magnitude,
)
from ralmon.benchmark.injection import (
    InjectionContext,
    InjectionError,
    InjectionRecord,
    InjectionSpec,
    LevelRow,
    apply_observation_injections,
    finalize_observed,
    ground_truth_events,
    injection_log,
    injection_sub_index,
    load_injection_design,
)
from ralmon.benchmark.latent import T_DAY_MS, simulate_baseline_sbp
from ralmon.benchmark.latent_day import (
    MAX_DAYS,
    AssemblyConfig,
    AssemblyState,
    ForcedSlot,
    LatentAssemblyError,
    LatentResult,
    assemble_latent_days,
)
from ralmon.benchmark.measurement import (
    LatentSbpHold,
    MeasurementConfigError,
    MeasurementDesign,
    NoJitter,
    ObservedStream,
    RobotVisit,
    build_observed_base,
)
from ralmon.benchmark.pkpd import (
    OneCompartmentEmax,
    compose_latent_sbp,
    intake_times_from_events,
)
from ralmon.benchmark.priors import (
    SOURCE_TYPES,
    AdherenceParams,
    DeviceErrorModel,
    PatientParams,
)
from ralmon.benchmark.rng import StreamPurpose, stream
from ralmon.benchmark.schedule import Schedule
from ralmon.benchmark.segments import InlineSegment, SegmentLibrary
from ralmon.benchmark.trace import (
    GroundTruthEvent,
    InjectedClass,
    LatentDay,
    ObservedDay,
    validate_day,
    write_observed_day,
)
from ralmon.signals import Event, EventKind, Sample

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "ralmon" / "benchmark"
INJECTIONS_FILE = ROOT / "configs" / "benchmark" / "injections.yaml"
FAULT_MODEL = ROOT / "docs" / "models" / "fault-model.md"
REGISTRY_FILE = ROOT / "configs" / "registry" / "hypertension.yaml"

SEC = 1_000
MIN = 60_000
HOUR = 3_600_000
DAY = T_DAY_MS
C1, C2, C3 = InjectedClass.C1, InjectedClass.C2, InjectedClass.C3

STEP = MIN  # FIXTURE-ONLY latent grid: 1440 points a day
FINE = (
    20 * SEC
)  # FIXTURE-ONLY: a grid fine enough to sit near the pressure peak (error < 4e-5 mmHg)
LAG = 5 * SEC  # FIXTURE-ONLY intake lag
GAP = 2 * MIN  # FIXTURE-ONLY double-take gap
BOUNCE = 500  # FIXTURE-ONLY nominal (sub-second) bounce gap, ms
DWELL = 10 * MIN  # FIXTURE-ONLY robot dwell
PEAK_CLOCK = 14 * HOUR  # FIXTURE-ONLY circadian peak clock time
SEED = 7
PATIENT_INDEX = 3

DOSE = 8 * HOUR
SCHED_ONE = Schedule(
    dose_ticks_ms=(DOSE,),
    measurement_ticks_ms=(7 * HOUR + 15 * MIN, 9 * HOUR + 45 * MIN),
)
SCHED_TWO = Schedule(
    dose_ticks_ms=(DOSE, 20 * HOUR),
    measurement_ticks_ms=(
        7 * HOUR + 15 * MIN,
        9 * HOUR + 45 * MIN,
        14 * HOUR + 30 * MIN,
        19 * HOUR + 15 * MIN,
        21 * HOUR + 45 * MIN,
    ),
)
SCHED_LATE = Schedule(
    dose_ticks_ms=(DAY - 10 * MIN,), measurement_ticks_ms=(12 * HOUR,)
)  # a dose ten minutes before midnight: its drug effect spills into the next day

ZERO_ERRORS = DeviceErrorModel(0.0, 0.0, 0.0, 0.0)
NOISY_ERRORS = DeviceErrorModel(
    4.0, 1.0, 0.0, 0.0
)  # FIXTURE-ONLY cuff error SD 4, bias 1
DESIGN = MeasurementDesign(
    inflation_ms_nominal=30 * SEC,
    inflation_ms_sd=0,
    pulse_error_sd_bpm=0.0,
    robot_dwell_ms=DWELL,
    vitals_period_ms=MIN,
    inflation_min_ms=30 * SEC,
)


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
    patient_id: str = "p0003",
) -> PatientParams:
    return PatientParams(
        patient_id=patient_id,
        baseline_sbp_mmhg=baseline,
        circadian_amplitude_mmhg=amplitude,
        ar_noise_sd_mmhg=sd,
        ar_noise_phi=phi,
        emax_mmhg=emax,
        ec50=ec50,
        absorption_rate_per_h=ka,
        elimination_rate_per_h=ke,
        onset_delay_range_ms=(HOUR, 2 * HOUR),
    )


FIX_PATIENT = make_patient()  # constant 130, no noise: the exact-value fixture
NOISY_PATIENT = make_patient(amplitude=10.0, sd=8.0, phi=0.6)  # FIXTURE-ONLY


def make_adherence(
    *,
    p_delay: float = 0.0,
    p_omission: float = 0.0,
    p_double_take: float = 0.0,
    mean_delay: int = 10 * MIN,
    lag: int = LAG,
    gap: int = GAP,
    matrix: Sequence[Sequence[float]] | None = None,
    initial: Sequence[float] | None = None,
) -> AdherenceModel:
    return AdherenceModel(
        AdherenceParams(p_delay, p_omission, p_double_take, mean_delay),
        AdherenceConfig(intake_lag_ms=lag, double_take_gap_ms=gap),
        transition_matrix=matrix,
        initial_distribution=initial,
    )


PERFECT = make_adherence()
NATURAL = make_adherence(p_delay=0.25, p_omission=0.125, p_double_take=0.0625)


def hr_values(n: int = DAY // MIN) -> list[float]:
    return [70.0 + i % 30 for i in range(n)]  # FIXTURE-ONLY


def spo2_values(n: int = DAY // MIN) -> list[float]:
    return [95.0 + i % 4 for i in range(n)]  # FIXTURE-ONLY


LIB = SegmentLibrary.from_memory(
    [
        InlineSegment("hr-1", "hr_clean", hr_values(), MIN, "bpm"),
        InlineSegment("sp-1", "spo2_clean", spo2_values(), MIN, "%"),
    ]
)
NOISE_LIB = SegmentLibrary.from_memory(
    [
        InlineSegment("hr-1", "hr_clean", hr_values(), MIN, "bpm"),
        InlineSegment("sp-1", "spo2_clean", spo2_values(), MIN, "%"),
        InlineSegment("ecg-1", "hr_error_ecg_noise", [5.0, -3.0, 8.0], MIN, "bpm"),
    ]
)


def make_config(
    *,
    step: int = STEP,
    adherence: AdherenceModel | None = None,
    allow_no_segments: bool = False,
) -> AssemblyConfig:
    return AssemblyConfig(
        latent_step_ms=step,
        circadian_peak_clock_ms=PEAK_CLOCK,
        ar_reference_step_ms=step,
        adherence=PERFECT if adherence is None else adherence,
        vitals=DESIGN,
        allow_no_segments=allow_no_segments,
    )


def assemble(
    specs: Sequence[InjectionSpec] = (),
    *,
    patient: PatientParams = FIX_PATIENT,
    schedule: Schedule = SCHED_ONE,
    n_days: int = 1,
    config: AssemblyConfig | None = None,
    seed: int = SEED,
    patient_index: int = PATIENT_INDEX,
    library: SegmentLibrary = LIB,
    **kwargs: Any,
) -> tuple[LatentResult, ...]:
    return assemble_latent_days(
        patient,
        schedule,
        n_days,
        list(specs),
        OneCompartmentEmax(),
        library,
        seed,
        patient_index,
        config=make_config() if config is None else config,
        **kwargs,
    )


def spike(onset: int, duration: int, magnitude: float, **kw: Any) -> InjectionSpec:
    return c1_spec(
        "hypertensive_spike", onset, duration_ms=duration, magnitude=magnitude, **kw
    )


def hypo(onset: int, duration: int, magnitude: float, **kw: Any) -> InjectionSpec:
    return c1_spec(
        "hypotension_below_hold", onset, duration_ms=duration, magnitude=magnitude, **kw
    )


def nonresponse(onset: int, duration: int, scale: float, **kw: Any) -> InjectionSpec:
    return c1_spec(
        "drug_nonresponse", onset, duration_ms=duration, magnitude=scale, **kw
    )


def refusal(onset: int, **kw: Any) -> InjectionSpec:
    return c1_spec("measurement_refusal", onset, **kw)


def double_take_spec(onset: int, **kw: Any) -> InjectionSpec:
    return c1_spec("double_take", onset, **kw)


def bp_series(result: LatentResult) -> dict[int, float]:
    return {s.t_device_ms: s.value for s in result.latent.samples if s.signal == "bp"}


def events_of(result: LatentResult, kind: EventKind) -> list[Event]:
    return [e for e in result.latent.events if e.kind is kind]


def times_of(result: LatentResult, kind: EventKind) -> list[int]:
    return [e.t_device_ms for e in events_of(result, kind)]


def dispense_intake(result: LatentResult) -> list[tuple[str, int, str]]:
    return [
        (e.kind.value, e.t_device_ms, e.source)
        for e in result.latent.events
        if e.kind in (EventKind.DISPENSE, EventKind.INTAKE)
    ]


def named_error(exc: BaseException) -> bool:
    """The error is one of the project's named errors, not a raw built-in one."""
    return isinstance(exc, InjectionError) and type(exc).__module__.startswith(
        "ralmon."
    )


# ---------------------------------------------------------------------------
# Test 1 and 2: pulses on the latent grid, exactly
# ---------------------------------------------------------------------------


def test_hypertensive_spike_adds_magnitude_inside_window_only() -> None:
    t1, t2 = 2 * HOUR, 3 * HOUR
    plain = assemble()[0]
    out = assemble([spike(t1, t2 - t1, 40.0)])[0]
    bp, base = bp_series(out), bp_series(plain)
    assert len(bp) == DAY // STEP
    for t, value in bp.items():
        if t1 <= t < t2:
            assert value == 170.0, t  # exactly 130 + 40
        elif t < DOSE:
            assert value == 130.0, t  # exactly the baseline: no drug yet
        else:
            assert value == base[t], t  # after the dose: untouched by the spike
    # the exact edge instants of [t1, t2)
    assert bp[t1 - STEP] == 130.0 and bp[t1] == 170.0
    assert bp[t2 - STEP] == 170.0 and bp[t2] == 130.0
    [record] = out.c1_records
    assert record.spec.cls is C1 and record.spec.subtype == "hypertensive_spike"
    assert record.realised and record.n_changed == (t2 - t1) // STEP
    assert record.realised_onset_ms == t1 and record.realised_end_ms == t2


def test_hypotension_pulse_subtracts_magnitude() -> None:
    t1, t2 = 2 * HOUR, 3 * HOUR
    plain = assemble()[0]
    out = assemble([hypo(t1, t2 - t1, 40.0)])[0]
    bp, base = bp_series(out), bp_series(plain)
    for t, value in bp.items():
        if t1 <= t < t2:
            assert value == 90.0, t  # exactly 130 - 40
        elif t < DOSE:
            assert value == 130.0, t
        else:
            assert value == base[t], t
    assert bp[t1 - STEP] == 130.0 and bp[t1] == 90.0
    assert bp[t2 - STEP] == 90.0 and bp[t2] == 130.0
    [record] = out.c1_records
    assert record.spec.subtype == "hypotension_below_hold" and record.realised


def test_overlapping_spike_and_hypotension_add_up_in_canonical_order() -> None:
    a, b = spike(2 * HOUR, 2 * HOUR, 40.0), hypo(3 * HOUR, 2 * HOUR, 25.0)
    out = assemble([b, a])[0]
    swapped = assemble([a, b])[0]
    assert bp_series(out) == bp_series(swapped)  # the order of the specs is irrelevant
    bp = bp_series(out)
    assert bp[2 * HOUR] == 170.0 and bp[3 * HOUR] == 145.0 and bp[4 * HOUR] == 105.0
    assert bp[5 * HOUR] == 130.0


def test_spike_window_without_a_grid_point_is_logged_not_realised() -> None:
    # [t1, t2) between two grid points of a coarse grid contains none: nothing changes
    config = make_config(step=HOUR)
    out = assemble([spike(2 * HOUR + 1, 10 * MIN, 40.0)], config=config)[0]
    assert out.c1_records[0].realised is False and out.c1_records[0].n_changed == 0
    assert bp_series(out) == bp_series(assemble(config=config)[0])


# ---------------------------------------------------------------------------
# Test 3: non-response scales the Emax of the intakes inside the window
# ---------------------------------------------------------------------------


def peak_effect(result: LatentResult, around_ms: int, baseline: float = 130.0) -> float:
    """Largest drop below the baseline within 30 min of ``around_ms`` (the grid is ``FINE``)."""
    bp = bp_series(result)
    return max(baseline - v for t, v in bp.items() if abs(t - around_ms) <= 30 * MIN)


def test_drug_nonresponse_scales_emax_for_intakes_in_window() -> None:
    config = make_config(step=FINE)
    t_max = 0.6931471805599453 * HOUR  # ln(ka / ke) / (ka - ke), in ms: 2 495 329.4
    peak = DOSE + LAG + t_max
    window = (DOSE, 20 * HOUR - DOSE)  # the slot of the first dose only
    unscaled = assemble(schedule=SCHED_TWO, config=config)[0]
    assert peak_effect(unscaled, peak) == pytest.approx(13.3333333, abs=1e-4)
    half = assemble([nonresponse(*window, 0.5)], schedule=SCHED_TWO, config=config)[0]
    zero = assemble([nonresponse(*window, 0.0)], schedule=SCHED_TWO, config=config)[0]
    assert peak_effect(half, peak) == pytest.approx(6.6666667, abs=1e-4)
    assert peak_effect(zero, peak) == pytest.approx(0.0, abs=1e-9)
    # the intake at 20:00 is outside the window and keeps its full effect
    peak2 = 20 * HOUR + LAG + t_max
    for scaled in (half, zero):
        assert peak_effect(scaled, peak2) == pytest.approx(13.3333333, abs=1e-3)
    # hand-checked against the model on the same grid, bit for bit
    intakes = times_of(half, EventKind.INTAKE)
    grid = sorted(bp_series(half))
    effect = OneCompartmentEmax().effect_mmhg(
        FIX_PATIENT, intakes, grid, intake_scales=[0.5, 1.0]
    )
    expected = compose_latent_sbp([130.0] * len(grid), effect)
    assert [bp_series(half)[t] for t in grid] == expected.tolist()
    assert half.c1_records[0].n_changed == 1 and half.c1_records[0].realised


def test_nonresponse_window_edges_apply_to_intakes_in_the_half_open_window() -> None:
    config = make_config(step=MIN)
    intake = DOSE + LAG
    plain = assemble(config=config)[0]
    for onset, duration, scaled in (
        (intake, 1, True),  # the intake instant is the first instant of the window
        (intake - 1, 2, True),
        (
            intake - 10 * MIN,
            10 * MIN,
            False,
        ),  # [intake - 10 min, intake): the end is excluded
        (intake + 1, 10 * MIN, False),  # starts one ms after the intake
        (intake - 10 * MIN, 10 * MIN + 1, True),  # one ms longer reaches the intake
    ):
        out = assemble([nonresponse(onset, duration, 0.0)], config=config)[0]
        record = out.c1_records[0]
        assert record.realised is scaled, (onset, duration)
        assert (bp_series(out) != bp_series(plain)) is scaled, (onset, duration)
    # a scale of 1 changes nothing: logged, not realised
    same = assemble([nonresponse(DOSE, HOUR, 1.0)], config=config)[0]
    assert same.c1_records[0].realised is False
    assert bp_series(same) == bp_series(plain)


# ---------------------------------------------------------------------------
# Test 4: a measurement refusal removes the latent AND the observed measurement
# ---------------------------------------------------------------------------


def observed_of(
    result: LatentResult,
    schedule: Schedule = SCHED_ONE,
    *,
    errors: DeviceErrorModel = ZERO_ERRORS,
    seed: int = SEED,
    **kwargs: Any,
) -> ObservedStream:
    return build_observed_base(
        result.latent,
        schedule,
        "plan-1",
        errors,
        DESIGN,
        NoJitter(),
        LIB,
        seed,
        PATIENT_INDEX,
        skip_measurement_ticks_ms=result.refused_ticks_ms,
        **kwargs,
    )


def test_measurement_refusal_removes_latent_and_observed_measurement() -> None:
    first, second = SCHED_ONE.measurement_ticks_ms
    out = assemble([refusal(second)])[0]
    ticks = times_of(out, EventKind.MEASUREMENT)
    assert ticks == [first]  # the latent MEASUREMENT at the refused tick is absent
    assert out.refused_ticks_ms == (second,)
    assert (
        times_of(out, EventKind.SCHEDULE_TICK).count(second) == 1
    )  # the tick still happens
    [record] = out.c1_records
    assert record.spec.subtype == "measurement_refusal" and record.realised
    assert record.realised_onset_ms == second and record.realised_end_ms is None

    stream_ = observe_refusals(observed_of(out), out.c1_records)
    day = finalize_observed(stream_)
    visit = next(
        v for v in stream_.visits if v.kind == "measurement" and v.tick_ms == second
    )
    presences = [s.t_device_ms for s in day.samples if s.signal == "presence"]
    assert visit.arrival_ms in presences  # the robot visit is there
    tasks = [e for e in day.events if e.kind is EventKind.ROBOT_TASK]
    assert any(
        e.payload["task"] == "navigate"
        and e.payload["outcome"] == "success"
        and e.t_device_ms == second
        for e in tasks
    )
    declined = [e for e in tasks if e.payload["outcome"] == vocab.OUTCOME_DECLINED]
    assert len(declined) == 1 and declined[0].payload["task"] == vocab.TASK_MANIPULATE
    assert declined[0].t_device_ms == visit.arrival_ms and declined[0].source == "robot"
    bps = [s.t_device_ms for s in day.samples if s.signal == "bp"]
    assert len(bps) == 1 and bps[0] < second  # no bp sample at the refused tick
    assert [e.t_device_ms for e in day.events if e.kind is EventKind.MEASUREMENT] == bps
    # the other measurement keeps its draw (indexed by the measurement, not by its position)
    plain = observed_of(assemble()[0], errors=NOISY_ERRORS)
    refused = observed_of(out, errors=NOISY_ERRORS)
    assert refused.measurements[0] == plain.measurements[0]


def test_declined_outcome_is_a_vocabulary_member() -> None:
    assert vocab.OUTCOME_DECLINED == "declined"
    assert vocab.OUTCOME_DECLINED in vocab.OUTCOMES
    vocab.check_payload(
        EventKind.ROBOT_TASK,
        {"task": "manipulate", "outcome": "declined", "patient_id": "p0"},
    )
    with pytest.raises(vocab.VocabularyError):
        vocab.check_payload(
            EventKind.ROBOT_TASK,
            {"task": "manipulate", "outcome": "refused", "patient_id": "p0"},
        )


# ---------------------------------------------------------------------------
# Test 5: C1 returns records, never ground truth
# ---------------------------------------------------------------------------

FORBIDDEN_NAMES = {"GroundTruthEvent", "record_to_ground_truth", "ground_truth_events"}


def _names_in(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, ast.alias):
            found.add(node.name.split(".")[-1])
            if node.asname:
                found.add(node.asname)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.update(re.findall(r"[A-Za-z_]+", node.value))
    return found


def test_c1_injectors_return_records_not_ground_truth() -> None:
    # no GroundTruthEvent anywhere in inject_c1.py and latent_day.py (AST scan, strings included)
    for name in ("inject_c1.py", "latent_day.py"):
        assert not FORBIDDEN_NAMES & _names_in(SRC / name), name
    work = LatentWork(
        0,
        np.arange(0, DAY, STEP, dtype=np.int64),
        dose_ticks_ms=SCHED_ONE.dose_ticks_ms,
        measurement_ticks_ms=SCHED_ONE.measurement_ticks_ms,
        double_take_gap_ms=GAP,
    )
    work.set_intakes((DOSE + LAG,))
    calls: list[tuple[Callable[..., Any], InjectionSpec]] = [
        (hypertensive_spike, spike(HOUR, HOUR, 10.0)),
        (hypotension_below_hold, hypo(HOUR, HOUR, 10.0)),
        (drug_nonresponse, nonresponse(DOSE, HOUR, 0.5)),
        (measurement_refusal, refusal(SCHED_ONE.measurement_ticks_ms[0])),
        (double_take, double_take_spec(DOSE)),
    ]
    for fn, spec in calls:
        records = fn(work, [spec])
        assert isinstance(records, tuple) and len(records) == 1
        assert isinstance(records[0], InjectionRecord)
        assert records[0].spec.cls is C1 and records[0].spec is spec
        assert not isinstance(records[0], GroundTruthEvent)
        assert records[0].evidence_paths == ()  # a C1 has no evidence signature
    # the whole assembly: nothing in a result is a ground-truth event
    out = assemble(
        [spike(HOUR, HOUR, 10.0), refusal(SCHED_ONE.measurement_ticks_ms[0])]
    )[0]
    for item in (
        *out.latent.samples,
        *out.latent.events,
        *out.c1_records,
        out.end_state,
    ):
        assert not isinstance(item, GroundTruthEvent)
    assert all(r.spec.cls is C1 for r in out.c1_records)
    # the module has no constructor of a truth event in its namespace
    assert not hasattr(c1_mod, "GroundTruthEvent") and not hasattr(
        latent_day_mod, "GroundTruthEvent"
    )


# ---------------------------------------------------------------------------
# Test 6 and 7: the latent day
# ---------------------------------------------------------------------------


def test_latent_day_has_no_observation_only_fields() -> None:
    out = assemble(schedule=SCHED_TWO, config=make_config(adherence=NATURAL))[0]
    day = out.latent
    assert isinstance(day, LatentDay)
    assert {f.name for f in dataclasses.fields(LatentDay)} == {
        "patient_id", "day_index", "seed", "samples", "events",
    }  # fmt: skip
    signals = {s.signal for s in day.samples}
    assert signals == {"bp", "hr_ecg", "spo2"}
    assert not signals & {
        "cuff_health",
        "inflation_ms",
        "presence",
        "hr_pulse",
        "day_end",
    }
    assert all(s.quality is None and s.seq is None for s in day.samples)
    assert all(s.t_rx_ms == s.t_device_ms for s in day.samples)
    kinds = {e.kind for e in day.events}
    assert kinds <= {
        EventKind.DISPENSE, EventKind.INTAKE, EventKind.MEASUREMENT, EventKind.SCHEDULE_TICK,
    }  # fmt: skip
    assert {EventKind.MEASUREMENT, EventKind.SCHEDULE_TICK} <= kinds
    assert all(e.seq is None and e.t_rx_ms == e.t_device_ms for e in day.events)
    sources = {
        EventKind.SCHEDULE_TICK: "ward",
        EventKind.MEASUREMENT: "cuff",
        EventKind.DISPENSE: "dispenser",
        EventKind.INTAKE: "patient",
    }
    assert all(e.source == sources[e.kind] for e in day.events)
    for e in day.events:
        vocab.check_payload(e.kind, e.payload)
        if e.kind is EventKind.SCHEDULE_TICK:
            assert set(e.payload) == {"kind"} and e.payload["kind"] in vocab.KINDS
        else:
            assert dict(e.payload) == {}
    validate_day(day)  # sorted, finite, integer times
    assert (day.patient_id, day.day_index, day.seed) == ("p0003", 0, SEED)
    # vitals come from the clean segments, on the vitals grid
    assert [s.value for s in day.samples if s.signal == "hr_ecg"] == hr_values()
    assert [s.value for s in day.samples if s.signal == "spo2"] == spo2_values()
    # types: plain python ints and floats (the trace schema rejects numpy scalars)
    assert all(
        type(s.t_device_ms) is int and type(s.value) is float for s in day.samples
    )
    assert all(type(e.t_device_ms) is int for e in day.events)


def test_latent_measurements_at_scheduled_ticks_with_exact_values() -> None:
    schedule = SCHED_TWO
    out = assemble(schedule=schedule, patient=NOISY_PATIENT)[0]
    ticks = list(schedule.measurement_ticks_ms)
    assert times_of(out, EventKind.MEASUREMENT) == ticks
    assert times_of(out, EventKind.SCHEDULE_TICK) == sorted(
        list(schedule.dose_ticks_ms) + ticks
    )
    kinds = {
        (e.t_device_ms, e.payload["kind"])
        for e in out.latent.events
        if e.kind is EventKind.SCHEDULE_TICK
    }
    assert {(t, "measurement") for t in ticks} <= kinds
    assert {(t, "dose") for t in schedule.dose_ticks_ms} <= kinds
    # the latent bp at a tick is the held value of the latent trace: the last grid point at or before
    bp = bp_series(out)
    grid = sorted(bp)
    hold = LatentSbpHold(out.latent.samples)
    for t in ticks:
        held = bp[max(g for g in grid if g <= t)]
        assert hold.at(t) == held
    # an off-grid tick and a day with no measurement tick
    off = Schedule(dose_ticks_ms=(), measurement_ticks_ms=(8 * HOUR + 17 * SEC,))
    odd = assemble(schedule=off, patient=NOISY_PATIENT)[0]
    assert times_of(odd, EventKind.MEASUREMENT) == [8 * HOUR + 17 * SEC]
    none = assemble(schedule=Schedule((), ()))[0]
    assert times_of(none, EventKind.MEASUREMENT) == [] and none.refused_ticks_ms == ()


def test_assembly_without_injections_equals_baseline_minus_effect() -> None:
    config = make_config(step=STEP, adherence=NATURAL)
    for patient in (FIX_PATIENT, NOISY_PATIENT):
        out = assemble(patient=patient, schedule=SCHED_TWO, n_days=3, config=config)
        # the same pipeline written out by hand with the same named streams, day by day
        state_ar: float | None = None
        chain: AdherenceState | None = None
        history: list[int] = []
        for day, result in enumerate(out):
            rng = stream(SEED, PATIENT_INDEX, day, StreamPurpose.LATENT_AR)
            base = simulate_baseline_sbp(
                patient,
                STEP,
                1,
                PEAK_CLOCK,
                STEP,
                rng,
                start_day=day,
                ar_state_mmhg=state_ar,
            )
            adh_rng = stream(SEED, PATIENT_INDEX, day, StreamPurpose.ADHERENCE)
            adh = NATURAL.simulate(SCHED_TWO, 1, adh_rng, start_day=day, state=chain)
            history += list(intake_times_from_events(adh.events))
            effect = OneCompartmentEmax().effect_mmhg(
                patient, history, base.t_ms.tolist()
            )
            expected = compose_latent_sbp(base.sbp_mmhg, effect)
            got = [s.value for s in result.latent.samples if s.signal == "bp"]
            assert got == expected.tolist(), (day, patient)
            assert list(result.baseline_sbp_mmhg) == base.sbp_mmhg.tolist()
            assert dispense_intake(result) == [
                (e.kind.value, e.t_device_ms, e.source) for e in adh.events
            ]
            assert result.behaviour_log == adh.behaviour_log
            assert result.c1_records == ()
            state_ar, chain = base.ar_state_mmhg, adh.final_state


def test_no_intake_means_the_baseline_is_returned_bit_for_bit() -> None:
    omit = make_adherence(p_omission=1.0)
    out = assemble(patient=NOISY_PATIENT, config=make_config(adherence=omit))[0]
    assert dispense_intake(out) == []
    assert [s.value for s in out.latent.samples if s.signal == "bp"] == list(
        out.baseline_sbp_mmhg
    )


# ---------------------------------------------------------------------------
# Test 9: forcing a slot state equals the chain in that state
# ---------------------------------------------------------------------------


def test_forced_double_take_matches_markov_double_take() -> None:
    chain = make_adherence(
        p_double_take=1.0
    )  # every slot is a double take, same gap and lag
    chain_events = chain.simulate(
        SCHED_TWO,
        1,
        stream(SEED, PATIENT_INDEX, 0, StreamPurpose.ADHERENCE),
        start_day=0,
    )
    first_slot = chain_events.behaviour_log[0]
    assert first_slot.state is AdherenceState.DOUBLE_TAKE
    forced = assemble([double_take_spec(DOSE)], schedule=SCHED_TWO)[0]
    expected = [
        (e.kind.value, e.t_device_ms, e.source)
        for e in chain_events.events
        if e.t_device_ms < 20 * HOUR  # the events of the first slot
    ]
    got = [row for row in dispense_intake(forced) if row[1] < 20 * HOUR]
    assert got == expected
    assert [row[1] for row in got if row[0] == "dispense"] == [DOSE, DOSE + GAP]
    assert [row[1] for row in got if row[0] == "intake"] == [
        DOSE + LAG,
        DOSE + GAP + LAG,
    ]
    # the other slot follows the natural chain (here: perfect adherence), untouched
    assert [r for r in dispense_intake(forced) if r[1] >= 20 * HOUR] == [
        r for r in dispense_intake(assemble(schedule=SCHED_TWO)[0]) if r[1] >= 20 * HOUR
    ]
    assert forced.behaviour_log[0].state is AdherenceState.DOUBLE_TAKE
    assert forced.behaviour_log[0].dispense_times_ms == (DOSE, DOSE + GAP)
    # the record of a forced double take: realised, the surplus release is its instant
    [record] = forced.c1_records
    assert record.spec.subtype == "double_take" and record.realised
    assert record.realised_onset_ms == DOSE + GAP and record.realised_end_ms is None
    assert record.details["second_dispense_ms"] == DOSE + GAP
    # forcing a state that the chain draws anyway still records the injection (and changes nothing)
    again = assemble(
        [double_take_spec(DOSE)],
        schedule=SCHED_TWO,
        config=make_config(adherence=chain),
    )[0]
    assert again.c1_records[0].realised
    assert [r for r in dispense_intake(again) if r[1] < 20 * HOUR] == expected


@pytest.mark.parametrize(
    "state",
    [AdherenceState.ON_TIME, AdherenceState.OMITTED, AdherenceState.DOUBLE_TAKE],
)
def test_forced_slot_equals_the_chain_in_that_state(state: AdherenceState) -> None:
    probabilities = {
        AdherenceState.ON_TIME: {},
        AdherenceState.OMITTED: {"p_omission": 1.0},
        AdherenceState.DOUBLE_TAKE: {"p_double_take": 1.0},
    }[state]
    chain = make_adherence(**probabilities)
    reference = chain.simulate(
        SCHED_TWO,
        1,
        stream(SEED, PATIENT_INDEX, 0, StreamPurpose.ADHERENCE),
        start_day=0,
    )
    # natural chain: the delayed / omitted / double mix; force slot 0 into `state`
    natural = assemble(schedule=SCHED_TWO, config=make_config(adherence=NATURAL))[0]
    forced = (
        {"specs": [double_take_spec(DOSE)]}
        if state is AdherenceState.DOUBLE_TAKE
        else {"forced_slots": [ForcedSlot(0, 0, state)]}
    )
    out = assemble(schedule=SCHED_TWO, config=make_config(adherence=NATURAL), **forced)[
        0
    ]
    assert out.behaviour_log[0].state is state
    assert (
        out.behaviour_log[0].dispense_times_ms
        == reference.behaviour_log[0].dispense_times_ms
    )
    assert (
        out.behaviour_log[1] == natural.behaviour_log[1]
    )  # the other slot is bit-identical

    def of_slot(result: LatentResult, slot: int) -> list[tuple[str, int, str]]:
        times = set(result.behaviour_log[slot].dispense_times_ms)
        return [
            row
            for row in dispense_intake(result)
            if (row[0] == "dispense" and row[1] in times)
            or (row[0] == "intake" and row[1] - LAG in times)
        ]

    assert of_slot(out, 1) == of_slot(
        natural, 1
    )  # the events of the other slot are identical
    assert of_slot(out, 0) == [
        (e.kind.value, e.t_device_ms, e.source)
        for e in reference.events
        if e.t_device_ms < 20 * HOUR
    ]


def test_forced_slots_do_not_shift_the_other_draws() -> None:
    config = make_config(adherence=NATURAL)
    natural = assemble(schedule=SCHED_TWO, n_days=3, config=config)
    forced = assemble(
        schedule=SCHED_TWO,
        n_days=3,
        config=config,
        forced_slots=[ForcedSlot(1, 0, AdherenceState.OMITTED)],
    )
    for day in (0, 2):
        assert natural[day].behaviour_log == forced[day].behaviour_log
        assert natural[day].latent.events == forced[day].latent.events
    assert forced[1].behaviour_log[0].state is AdherenceState.OMITTED
    assert forced[1].behaviour_log[1] == natural[1].behaviour_log[1]
    # the autoregressive noise of every day is the same: forcing touches the adherence only
    for day in range(3):
        assert natural[day].baseline_sbp_mmhg == forced[day].baseline_sbp_mmhg


def test_rebuilding_events_from_the_log_matches_the_adherence_model() -> None:
    # latent_day rebuilds the events of a day that has a forced slot from the behaviour log; the
    # rebuild must give exactly what the adherence model gives for the same states
    for seed in range(12):
        natural = assemble(
            schedule=SCHED_TWO, config=make_config(adherence=NATURAL), seed=seed
        )[0]
        slot = natural.behaviour_log[0].state
        # force the slot into the state it already has: same events, rebuilt from the log
        if slot is AdherenceState.DELAYED:
            continue  # a delay needs a draw; forcing it is refused (tested below)
        forced = assemble(
            schedule=SCHED_TWO,
            config=make_config(adherence=NATURAL),
            seed=seed,
            forced_slots=[ForcedSlot(0, 0, slot)]
            if slot is not AdherenceState.DOUBLE_TAKE
            else (),
            specs=[double_take_spec(DOSE)]
            if slot is AdherenceState.DOUBLE_TAKE
            else (),
        )[0]
        assert dispense_intake(forced) == dispense_intake(natural), seed
        assert forced.behaviour_log == natural.behaviour_log, seed


@pytest.mark.parametrize(
    "state",
    [AdherenceState.ON_TIME, AdherenceState.OMITTED, AdherenceState.DOUBLE_TAKE],
)
def test_rebuilt_events_of_a_forced_day_equal_the_models_events_field_by_field(
    state: AdherenceState,
) -> None:
    """Review F6 (M60): the events rebuilt from the log are compared as whole ``Event`` values
    (kind, both times, source, payload, sequence number), not as (kind, time, source)."""
    probabilities = {
        AdherenceState.ON_TIME: {},
        AdherenceState.OMITTED: {"p_omission": 1.0},
        AdherenceState.DOUBLE_TAKE: {"p_double_take": 1.0},
    }[state]
    reference = make_adherence(**probabilities).simulate(
        SCHED_TWO,
        1,
        stream(SEED, PATIENT_INDEX, 0, StreamPurpose.ADHERENCE),
        start_day=0,
    )
    forced = (
        {"specs": [double_take_spec(DOSE)]}
        if state is AdherenceState.DOUBLE_TAKE
        else {"forced_slots": [ForcedSlot(0, 0, state)]}
    )
    out = assemble(schedule=SCHED_TWO, config=make_config(adherence=NATURAL), **forced)[
        0
    ]
    kinds = (EventKind.DISPENSE, EventKind.INTAKE)
    rebuilt = [
        e for e in out.latent.events if e.kind in kinds and e.t_device_ms < 20 * HOUR
    ]
    expected = [e for e in reference.events if e.t_device_ms < 20 * HOUR]
    assert rebuilt == expected  # whole Event values
    for event in rebuilt:
        assert (
            event.payload == {}
            and event.seq is None
            and event.t_rx_ms == event.t_device_ms
        )
        assert event.source == (
            "dispenser" if event.kind is EventKind.DISPENSE else "patient"
        )
    assert bool(rebuilt) is (state is not AdherenceState.OMITTED)


def test_rebuilt_events_of_every_forced_day_equal_the_natural_events_whole() -> None:
    forced_states: set[AdherenceState] = set()
    for seed in range(12):
        natural = assemble(
            schedule=SCHED_TWO,
            n_days=2,
            config=make_config(adherence=NATURAL),
            seed=seed,
        )
        states = [r.behaviour_log[0].state for r in natural]
        if AdherenceState.DELAYED in states:
            continue  # a delay needs a draw
        slots = [
            ForcedSlot(d, 0, s)
            for d, s in enumerate(states)
            if s is not AdherenceState.DOUBLE_TAKE
        ]
        specs = [
            double_take_spec(d * DAY + DOSE)
            for d, s in enumerate(states)
            if s is AdherenceState.DOUBLE_TAKE
        ]
        forced = assemble(
            specs, schedule=SCHED_TWO, n_days=2, config=make_config(adherence=NATURAL), seed=seed,
            forced_slots=slots,
        )  # fmt: skip
        kinds = (EventKind.DISPENSE, EventKind.INTAKE)
        for day in range(2):
            assert [e for e in forced[day].latent.events if e.kind in kinds] == [
                e for e in natural[day].latent.events if e.kind in kinds
            ], (seed, day)
        forced_states.update(states)
    assert len(forced_states) >= 2  # the rebuild was exercised with more than one state


def test_forcing_a_delayed_dose_is_refused() -> None:
    with pytest.raises(LatentAssemblyError):
        ForcedSlot(0, 0, AdherenceState.DELAYED)
    with pytest.raises(LatentAssemblyError):
        assemble(
            forced_slots=[ForcedSlot(0, 5, AdherenceState.OMITTED)]
        )  # no such dose
    with pytest.raises(LatentAssemblyError):
        assemble(
            forced_slots=[ForcedSlot(3, 0, AdherenceState.OMITTED)]
        )  # day outside the call
    with pytest.raises(LatentAssemblyError):  # the same slot forced twice
        assemble(
            forced_slots=[
                ForcedSlot(0, 0, AdherenceState.OMITTED),
                ForcedSlot(0, 0, AdherenceState.ON_TIME),
            ]
        )
    with pytest.raises(
        LatentAssemblyError
    ):  # a double-take spec and a forced slot on one slot
        assemble(
            [double_take_spec(DOSE)],
            forced_slots=[ForcedSlot(0, 0, AdherenceState.OMITTED)],
        )


# ---------------------------------------------------------------------------
# Test 10: magnitudes are a level times a named reference quantity
# ---------------------------------------------------------------------------


def level_row(
    value: float | None,
    unit: str = f"x {REFERENCE_SCALE_RANGE}",
    *,
    quantity_unit: str = UNIT_MMHG,
) -> LevelRow:
    return LevelRow(
        "row",
        "above",
        unit,
        value,
        value is not None,
        "design_choice",
        "fixture",
        quantity_unit,
    )


def test_magnitude_levels_are_relative_to_named_reference() -> None:
    level = level_row(2.0)
    assert resolve_c1_magnitude(level, 20.0, REFERENCE_SCALE_RANGE) == 40.0
    spec = c1_spec_from_level(
        "hypertensive_spike", 2 * HOUR, level, 20.0, duration_ms=HOUR
    )
    assert spec.magnitude == 40.0 and spec.magnitude_unit == UNIT_MMHG
    assert spec.level == "above"
    assert spec.params["reference"] == REFERENCE_SCALE_RANGE
    assert spec.params["multiple"] == 2.0 and spec.params["reference_value"] == 20.0
    record = assemble([spec])[0].c1_records[0]
    assert record.spec.magnitude == 40.0 and record.level == "above"
    assert record.details["reference"] == REFERENCE_SCALE_RANGE
    assert (
        record.details["multiple"] == 2.0 and record.details["reference_value"] == 20.0
    )
    # the other named reference: the distance from the baseline to the hold threshold
    assert hold_distance_mmhg(130.0, 100.0) == 30.0
    hold_level = level_row(1.5, f"x {REFERENCE_HOLD_DISTANCE}")
    assert resolve_c1_magnitude(hold_level, 30.0, REFERENCE_HOLD_DISTANCE) == 45.0
    # a wrong reference, an absolute row and an unfilled row are refused, never defaulted
    with pytest.raises(InjectionError):
        resolve_c1_magnitude(level, 20.0, REFERENCE_HOLD_DISTANCE)
    with pytest.raises(InjectionError):
        resolve_c1_magnitude(level_row(40.0, "mmHg"), 20.0, REFERENCE_SCALE_RANGE)
    with pytest.raises(InjectionError):
        resolve_c1_magnitude(level_row(None), 20.0, REFERENCE_SCALE_RANGE)
    # the dimensionless Emax scale is an absolute level: it is its own magnitude
    scale = level_row(0.5, UNIT_SCALE, quantity_unit=UNIT_SCALE)
    nonresp = c1_spec_from_level(
        "drug_nonresponse", DOSE, scale, None, duration_ms=HOUR
    )
    assert nonresp.magnitude == 0.5 and nonresp.magnitude_unit == UNIT_SCALE
    assert "reference" not in nonresp.params


def design_rows(path: Path, task: str = "WS04-T09") -> list[dict[str, Any]]:
    document = (
        _committed_document()
        if path == INJECTIONS_FILE
        else yaml.safe_load(path.read_text(encoding="utf-8"))
    )
    return [r for r in document["parameters"] if r["consumer_task"] == task]


def check_c1_design_structure(path: Path) -> None:
    """The structural facts of the C1 section, true whatever the state of the rows."""
    design = load_c1_design(path)
    assert set(design) == set(C1_SUBTYPES)
    for subtype, entry in design.items():
        assert entry.family in ("physiology", "behaviour"), subtype
        assert entry.targets, subtype
        if entry.magnitude is not None:
            assert len(entry.magnitude.levels) >= 3, subtype  # below, near and above
            for level in entry.magnitude.levels:
                assert level.source_type in SOURCE_TYPES and level.source_ref.strip()
                if entry.magnitude.unit == UNIT_MMHG:
                    # a pressure magnitude is relative to a named reference, never absolute mmHg
                    assert entry.magnitude.reference in (
                        REFERENCE_SCALE_RANGE,
                        REFERENCE_HOLD_DISTANCE,
                    )
                    assert level.unit == f"x {entry.magnitude.reference}", level
                else:
                    assert (
                        entry.magnitude.unit == UNIT_SCALE and level.unit == UNIT_SCALE
                    )
        if entry.duration is not None:
            assert entry.duration.unit == "ms" and len(entry.duration.levels) >= 1
    # no row of the task is an absolute pressure
    for row in design_rows(path):
        assert row["unit"] != "mmHg", row["parameter"]
        assert row["source_type"] in SOURCE_TYPES
        assert isinstance(row["source_ref"], str) and row["source_ref"].strip()


@functools.cache
def _committed_document() -> dict[str, Any]:
    return yaml.safe_load(INJECTIONS_FILE.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def committed_document() -> dict[str, Any]:
    """A private deep copy of the committed design file (parsed once per test run)."""
    return copy.deepcopy(_committed_document())


FIXTURE_MULTIPLE = {
    "below": 0.5,
    "near": 1.0,
    "above": 2.0,
}  # FIXTURE-ONLY levels of a pressure magnitude


def fixture_value(row: Mapping[str, Any]) -> float:
    """A FIXTURE-ONLY value for a row: a duration, a multiple spanning the reference, or a scale."""
    unit = row["unit"]
    if unit == "ms":
        return 60_000
    if unit.startswith("x "):  # below, near and above the reference (review F9)
        return FIXTURE_MULTIPLE.get(row["parameter"].rsplit("_", 1)[-1], 2.0)
    return 0.5


def rewrite_rows(tmp_path: Path, *, filled: bool, name: str) -> Path:
    """A copy of injections.yaml with every row of the task awaiting a value, or filled."""
    document = committed_document()
    for row in document["parameters"]:
        if filled:
            if row["status"] == "awaiting_human_value":
                row["value"] = fixture_value(row)
                row["status"] = "filled"
                row["rationale"] = "FIXTURE-ONLY value for a test"
        else:
            row["value"] = None
            row["status"] = "awaiting_human_value"
            row["rationale"] = None
            row["verified_by"] = None
    path = tmp_path / name
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def test_c1_rows_are_structured_relative_and_valid_in_every_state(
    tmp_path: Path,
) -> None:
    for path in (
        INJECTIONS_FILE,  # whatever its state
        rewrite_rows(tmp_path, filled=False, name="unfilled.yaml"),
        rewrite_rows(tmp_path, filled=True, name="filled.yaml"),
    ):
        check_c1_design_structure(path)
    # the filled copy resolves: every level has a number; the unfilled one has none
    filled = load_c1_design(tmp_path / "filled.yaml")
    unfilled = load_c1_design(tmp_path / "unfilled.yaml")
    for subtype, entry in filled.items():
        if entry.magnitude is not None:
            assert all(level.value is not None for level in entry.magnitude.levels)
            assert all(
                level.value is None
                for level in unfilled[subtype].magnitude.levels  # type: ignore[union-attr]
            )
    # the checker catches an absolute pressure row (a mutated copy)
    document = yaml.safe_load((tmp_path / "filled.yaml").read_text(encoding="utf-8"))
    for row in document["parameters"]:
        if row["consumer_task"] == "WS04-T09" and row["unit"].startswith(
            "x scale_range"
        ):
            row["unit"] = "mmHg"
    bad = tmp_path / "absolute.yaml"
    bad.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    with pytest.raises((AssertionError, InjectionError)):
        check_c1_design_structure(bad)


def test_filled_pressure_levels_must_span_the_reference(tmp_path: Path) -> None:
    """Review F9: once every level of a pressure magnitude has a value, the multiples span the
    reference (one below 1, one above 1); a block that still awaits a value is not judged."""
    filled = rewrite_rows(tmp_path, filled=True, name="span_ok.yaml")
    load_c1_design(filled)  # below, near and above: 0.5, 1.0, 2.0
    load_c1_design(rewrite_rows(tmp_path, filled=False, name="span_unfilled.yaml"))
    for subtype in ("hypertensive_spike", "hypotension_below_hold"):
        bad_sets = {
            "all_above": (1.5, 2.0, 3.0),
            "all_below": (0.2, 0.5, 0.9),
            "smallest_is_one": (1.0, 1.5, 2.0),
            "largest_is_one": (0.5, 0.8, 1.0),
            "all_one": (1.0, 1.0, 1.0),
        }
        for label, values in bad_sets.items():
            document = yaml.safe_load(filled.read_text(encoding="utf-8"))
            rows = [
                r
                for r in document["parameters"]
                if r["parameter"].startswith(f"{subtype}_magnitude_")
            ]
            assert [r["parameter"].rsplit("_", 1)[-1] for r in rows] == [
                "below",
                "near",
                "above",
            ]
            for row, value in zip(rows, values, strict=True):
                row["value"] = value
            path = tmp_path / f"{subtype}_{label}.yaml"
            path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
            with pytest.raises(InjectionError) as caught:
                load_c1_design(path)
            assert named_error(caught.value) and "span" in str(caught.value), (
                subtype,
                label,
            )
        # spanning values in another order and a partly filled block are accepted
        document = yaml.safe_load(filled.read_text(encoding="utf-8"))
        rows = [
            r
            for r in document["parameters"]
            if r["parameter"].startswith(f"{subtype}_magnitude_")
        ]
        for row, value in zip(rows, (3.0, 0.1, 1.0), strict=True):
            row["value"] = value
        path = tmp_path / f"{subtype}_shuffled.yaml"
        path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
        load_c1_design(path)
        document = yaml.safe_load(filled.read_text(encoding="utf-8"))
        rows = [
            r
            for r in document["parameters"]
            if r["parameter"].startswith(f"{subtype}_magnitude_")
        ]
        for row, value in zip(
            rows, (1.5, 2.0, None), strict=True
        ):  # all above, but one row awaits
            row.update(
                {
                    "value": value,
                    "status": "filled" if value is not None else "awaiting_human_value",
                }
            )
            if value is None:
                row.update({"rationale": None, "verified_by": None})
        path = tmp_path / f"{subtype}_partial.yaml"
        path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
        load_c1_design(path)
    # the Emax scale is an absolute level in [0, 1]: it has no span rule
    document = yaml.safe_load(filled.read_text(encoding="utf-8"))
    for row in document["parameters"]:
        if row["parameter"].startswith("drug_nonresponse_magnitude_"):
            row["value"] = 0.25
    path = tmp_path / "scale_flat.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    load_c1_design(path)


# ---------------------------------------------------------------------------
# Tests 11 to 18: the confounder pairs
# ---------------------------------------------------------------------------


def pair_base(**overrides: Any) -> PairBase:
    values: dict[str, Any] = {
        "patient": NOISY_PATIENT,
        "schedule": SCHED_TWO,
        "config": make_config(adherence=NATURAL),
        "response_model": OneCompartmentEmax(),
        "device_errors": NOISY_ERRORS,
        "design": DESIGN,
        "jitter": NoJitter(),
        "library": LIB,
        "care_plan_id": "plan-1",
        "seed": SEED,
        "patient_index": PATIENT_INDEX,
        "nominal_bounce_gap_ms": BOUNCE,
        "task_deadline_offset_ms": 30 * MIN,
    }
    values.update(overrides)
    return PairBase(**values)


BASE = pair_base()


def variant(
    group: str,
    variant_id: str,
    *,
    withheld: Sequence[str] = (),
    bounce_gap: str | None = None,
    attacker: str | None = None,
    expected: bool = False,
) -> Variant:
    return Variant(
        group=group,
        variant_id=variant_id,
        withheld=tuple(withheld),
        bounce_gap=bounce_gap,
        attacker=attacker,
        expected_indistinguishable=expected,
        source_type="design_choice",
        source_ref="FIXTURE-ONLY variant of a test",
        rationale="FIXTURE-ONLY",
    )


def g1(gap: str, content: bool, robot: bool) -> Variant:
    withheld = []
    if not content:
        withheld.append("content_change")
    if not robot:
        withheld += ["witness", "robot_task_outcome"]
    vid = f"{'nominal' if gap == 'nominal' else 'stress'}_{'content' if content else 'nocontent'}_{'robot' if robot else 'norobot'}"
    expected = gap == "double_take_gap" and not content and not robot
    return variant(
        GROUP_DOUBLE_TAKE_VS_BOUNCE,
        vid,
        withheld=withheld,
        bounce_gap=gap,
        expected=expected,
    )


def g2(attacker: str, robot: bool, auth: bool) -> Variant:
    withheld = []
    if not robot:
        withheld += ["witness", "robot_task_outcome"]
    if not auth:
        withheld.append("verification")
    vid = f"{attacker}_{'robot' if robot else 'norobot'}_{'auth' if auth else 'noauth'}"
    return variant(
        GROUP_NONRESPONSE_VS_FORGERY,
        vid,
        withheld=withheld,
        attacker=attacker,
        expected=attacker == "informed" and not auth,
    )


G3_REPORTED = variant(GROUP_REFUSAL_VS_ROBOT_MISSED, "outcome_reported")
G3_WITHHELD = variant(
    GROUP_REFUSAL_VS_ROBOT_MISSED, "outcome_withheld",
    withheld=["robot_task_outcome"], expected=True,
)  # fmt: skip
G3_ABSENT = variant(
    GROUP_REFUSAL_VS_ROBOT_MISSED, "robot_absent",
    withheld=["witness", "robot_task_outcome"], expected=True,
)  # fmt: skip

G1_GRID = [
    g1(gap, c, r)
    for gap in ("nominal", "double_take_gap")
    for c in (True, False)
    for r in (True, False)
]
G2_GRID = [
    g2(a, r, u)
    for a in ("naive", "informed")
    for r in (True, False)
    for u in (False, True)
]
G3_GRID = [G3_REPORTED, G3_WITHHELD, G3_ABSENT]


@functools.cache
def evaluated(variant_: Variant, base: PairBase = BASE) -> PairEvaluation:
    return evaluate_pair(variant_.group, variant_, base)


def first_plain_slot() -> int:
    return 0


def test_double_take_vs_bounce_pair_shares_base_and_seed() -> None:
    v = g1("double_take_gap", True, True)
    a, b = build_confounder_pair(v.group, v, BASE)
    assert isinstance(a, Scenario) and isinstance(b, Scenario)
    assert (a.member, b.member) == ("A", "B")
    ev = evaluated(v)
    ra, rb = ev.a, ev.b
    # the same baseline: the latent pressure before any drug, drawn from the same stream
    assert ra.latent.baseline_sbp_mmhg == rb.latent.baseline_sbp_mmhg
    assert (
        len(set(ra.latent.baseline_sbp_mmhg)) > 100
    )  # a real, noisy, circadian baseline
    # the same cuff noise draws: the stream (seed, patient, day, MEASUREMENT, k) feeds both
    for k, (ma, mb) in enumerate(
        zip(ra.stream.measurements, rb.stream.measurements, strict=True)
    ):
        z0 = float(
            stream(
                SEED, PATIENT_INDEX, 0, StreamPurpose.MEASUREMENT, ma.index
            ).standard_normal(3)[0]
        )
        expected_error = (
            NOISY_ERRORS.cuff_bias_mmhg + NOISY_ERRORS.cuff_error_sd_mmhg * z0
        )
        assert ma.error_mmhg == mb.error_mmhg == expected_error, k
        assert ma.inflation_ms == mb.inflation_ms and ma.index == mb.index
    assert len(ra.stream.measurements) == len(SCHED_TWO.measurement_ticks_ms)
    # the same schedule, patient, seed and care plan
    assert ra.observed.patient_id == rb.observed.patient_id == "p0003"
    assert ra.observed.seed == rb.observed.seed == SEED
    assert ra.observed.care_plan_id == rb.observed.care_plan_id
    assert [
        e.t_device_ms
        for e in ra.latent.latent.events
        if e.kind is EventKind.SCHEDULE_TICK
    ] == [
        e.t_device_ms
        for e in rb.latent.latent.events
        if e.kind is EventKind.SCHEDULE_TICK
    ]
    assert [
        e.t_device_ms
        for e in ra.latent.latent.events
        if e.kind is EventKind.MEASUREMENT
    ] == list(SCHED_TWO.measurement_ticks_ms)
    # only the mechanism differs
    assert a.mechanism == "double_take" and b.mechanism == "dispenser_bounce"
    assert (a.mechanism_class, b.mechanism_class) == (C1, C2)
    assert {r.spec.subtype for r in ra.records} == {"double_take"}
    assert {r.spec.subtype for r in rb.records} == {"dispenser_bounce"}
    assert dispense_intake(ra.latent) != dispense_intake(rb.latent)


def dispenses(day: ObservedDay) -> list[Event]:
    return [e for e in day.events if e.kind is EventKind.DISPENSE]


def test_double_take_vs_bounce_identical_when_discriminators_withheld() -> None:
    # content sensing off, the robot absent, the bounce gap set to the double-take gap (stress level)
    v = g1("double_take_gap", False, False)
    ev = evaluated(v)
    da, db = ev.a.observed, ev.b.observed
    assert dispenses(da) == dispenses(db)  # the observed dispense streams are equal
    assert len(dispenses(da)) >= 2
    assert [e.t_device_ms for e in dispenses(da)][:2] == [DOSE, DOSE + GAP]
    assert [e.seq for e in dispenses(da)] == list(range(1, len(dispenses(da)) + 1))
    assert all(dict(e.payload) == {} for e in dispenses(da))  # no content_change key
    assert not [
        e for e in da.events if e.kind is EventKind.INTAKE
    ]  # the robot is absent
    assert not [s for s in da.samples if s.signal == "presence"]
    assert not [e for e in da.events if e.kind is EventKind.ROBOT_TASK]
    # the latent days differ: two intakes against one
    assert (
        len(times_of(ev.a.latent, EventKind.INTAKE))
        == len(times_of(ev.b.latent, EventKind.INTAKE)) + 1
    )
    assert ev.a.latent.latent.events != ev.b.latent.latent.events
    # the records: C1 double_take against C2 dispenser_bounce, both with the group
    [ra] = [r for r in ev.a.records if r.spec.subtype == "double_take"]
    [rb] = [r for r in ev.b.records if r.spec.subtype == "dispenser_bounce"]
    assert ra.spec.cls is C1 and rb.spec.cls is C2
    assert ra.confounder_group == rb.confounder_group == GROUP_DOUBLE_TAKE_VS_BOUNCE
    assert ev.separated_by == () and ev.indistinguishable_by_construction is True
    # the pressure response differs by construction (two doses against one): reported, not hidden
    assert ev.pressure_response_differs is True


def test_double_take_vs_bounce_separable_with_sensing_or_interval() -> None:
    # content sensing on: the second DISPENSE carries content_change 1 in the double take, 0 in the bounce
    v = g1("double_take_gap", True, False)
    ev = evaluated(v)
    second_a, second_b = dispenses(ev.a.observed)[1], dispenses(ev.b.observed)[1]
    assert second_a.t_device_ms == second_b.t_device_ms == DOSE + GAP
    assert second_a.payload[vocab.KEY_CONTENT_CHANGE] == 1.0
    assert second_b.payload[vocab.KEY_CONTENT_CHANGE] == 0.0
    assert dispenses(ev.a.observed)[0].payload[vocab.KEY_CONTENT_CHANGE] == 1.0
    assert ev.separated_by == ("content_change",)
    assert ev.indistinguishable_by_construction is False
    # at the sub-second nominal gap the interval alone separates them
    nominal = evaluated(g1("nominal", False, False))
    assert [e.t_device_ms for e in dispenses(nominal.b.observed)][:2] == [
        DOSE,
        DOSE + BOUNCE,
    ]
    assert [e.t_device_ms for e in dispenses(nominal.a.observed)][:2] == [
        DOSE,
        DOSE + GAP,
    ]
    assert nominal.separated_by == ("dispense_interval",)
    assert nominal.indistinguishable_by_construction is False


@pytest.mark.parametrize("v", G1_GRID, ids=lambda v: v.variant_id)
def test_double_take_vs_bounce_grid_separated_by(v: Variant) -> None:
    ev = evaluated(v)
    expected = []
    if "content_change" not in v.withheld:
        expected.append("content_change")
    if "witness" not in v.withheld:
        expected.append("witness")
    if v.bounce_gap == "nominal":
        expected.append("dispense_interval")
    expected_sorted = tuple(f for f in DISCRIMINATORS if f in expected)
    assert ev.separated_by == expected_sorted
    assert ev.indistinguishable_by_construction is v.expected_indistinguishable
    # a withheld channel is really absent from the released day
    for day in (ev.a.observed, ev.b.observed):
        if "content_change" in v.withheld:
            assert all(
                vocab.KEY_CONTENT_CHANGE not in e.payload for e in dispenses(day)
            )
        if "witness" in v.withheld:
            assert not [e for e in day.events if e.kind is EventKind.INTAKE]
            assert not [s for s in day.samples if s.signal == "presence"]


def only(day: ObservedDay, kind: EventKind, source: str | None = None) -> list[Event]:
    return [
        e
        for e in day.events
        if e.kind is kind and (source is None or e.source == source)
    ]


def test_nonresponse_vs_forgery_identical_without_witness() -> None:
    # robot co-located and spoofed (informed attacker, spoof_intake, no authentication)
    spoofed = evaluated(g2("informed", True, False))
    real, forged = spoofed.a, spoofed.b
    assert {r.spec.subtype for r in real.records} == {"drug_nonresponse"}
    assert {r.spec.subtype for r in forged.records} == {
        "dispense_forgery",
        "presence_spoof",
    }
    assert real.records[0].spec.cls is C1 and real.records[0].spec.magnitude == 0.0
    assert real.records[0].level == "complete"
    assert {r.level for r in forged.records} == {"informed"}
    assert {r.spec.cls for r in forged.records} == {C3}
    assert dispenses(real.observed) == dispenses(forged.observed)
    assert only(real.observed, EventKind.INTAKE) == only(
        forged.observed, EventKind.INTAKE
    )
    assert len(only(real.observed, EventKind.INTAKE, "robot")) >= 1
    assert (
        spoofed.separated_by == () and spoofed.indistinguishable_by_construction is True
    )
    # the pressure response is equal because scale 0 removes the effect of the dose (an extra
    # presence 1.0 inside a visit changes no held level); on a day with a later dose the drug of the
    # real intake still occupies the saturation term, so the later pressure differs by a residual
    # that the comparison ignores and the evaluation reports
    early = lambda day: [
        s for s in day.samples if s.signal == "bp" and s.t_device_ms < 20 * HOUR
    ]
    assert early(real.observed) == early(forged.observed) and early(real.observed)
    assert spoofed.pressure_response_differs is True
    one_dose = evaluated(g2("informed", True, False), pair_base(schedule=SCHED_ONE))
    assert one_dose.pressure_response_differs is False  # no later dose: exactly equal
    assert [s for s in one_dose.a.observed.samples if s.signal == "bp"] == [
        s for s in one_dose.b.observed.samples if s.signal == "bp"
    ]
    assert one_dose.separated_by == () and one_dose.indistinguishable_by_construction
    # the robot absent: equal streams without any witness
    absent = evaluated(g2("informed", False, False))
    assert dispenses(absent.a.observed) == dispenses(absent.b.observed)
    assert not only(absent.a.observed, EventKind.INTAKE) and not only(
        absent.b.observed, EventKind.INTAKE
    )
    assert (
        absent.separated_by == () and absent.indistinguishable_by_construction is True
    )
    # the latent days differ: a dose against none
    assert (
        len(times_of(real.latent, EventKind.DISPENSE))
        == len(times_of(forged.latent, EventKind.DISPENSE)) + 1
    )
    assert DOSE in times_of(real.latent, EventKind.DISPENSE)
    assert DOSE not in times_of(forged.latent, EventKind.DISPENSE)
    assert forged.latent.behaviour_log[0].state is AdherenceState.OMITTED
    assert real.latent.behaviour_log[0].state is AdherenceState.ON_TIME


def test_nonresponse_vs_forgery_separable_by_witness() -> None:
    # robot present, naive attacker: the forged variant lacks the INTAKE of the real variant
    ev = evaluated(g2("naive", True, False))
    real_intakes = only(ev.a.observed, EventKind.INTAKE, "robot")
    forged_intakes = only(ev.b.observed, EventKind.INTAKE, "robot")
    assert DOSE + LAG in [e.t_device_ms for e in real_intakes]
    assert DOSE + LAG not in [e.t_device_ms for e in forged_intakes]
    assert (
        "witness" in ev.separated_by and ev.indistinguishable_by_construction is False
    )
    assert {r.spec.subtype for r in ev.b.records} == {
        "dispense_forgery"
    }  # a naive spoof is not made
    # the forged dispense is the same event for the dispenser; the robot is what differs
    assert ev.b.records[0].spec.level == "naive"


@pytest.mark.parametrize("v", G2_GRID, ids=lambda v: v.variant_id)
def test_nonresponse_vs_forgery_grid_separated_by(v: Variant) -> None:
    ev = evaluated(v)
    expected = []
    if v.attacker == "naive":
        if "witness" not in v.withheld:
            expected.append("witness")
        expected.append("dispense_seq")
    if "verification" not in v.withheld:
        expected.append("verification")
    assert ev.separated_by == tuple(f for f in DISCRIMINATORS if f in expected)
    assert ev.indistinguishable_by_construction is v.expected_indistinguishable
    if "verification" not in v.withheld:
        failed = [e for e in ev.b.observed.events if e.source == "gateway"]
        assert failed and not [e for e in ev.a.observed.events if e.source == "gateway"]


NOROBOT_GRID = [v for v in G1_GRID + G2_GRID + G3_GRID if not v.robot_present]


@pytest.mark.parametrize("v", NOROBOT_GRID, ids=lambda v: v.variant_id)
def test_a_withheld_robot_leaves_no_witness_path_in_the_records(v: Variant) -> None:
    """Review F2: the injectors of a variant without a robot see no visit, so no record names it.

    A forged dispense with the robot away reads the witness as None (never a negative): its
    evidence signature has no ``witness.*`` path, and the ``expected_undetectable`` tag agrees with
    the signature and, for the forgery, with the flag computed on the released streams.
    """
    ev = evaluated(v)
    for member in (ev.a, ev.b):
        for record in member.records:
            where = (v.variant_id, record.spec.subtype)
            assert not [p for p in record.evidence_paths if p.startswith("witness.")], (
                where
            )
            tag = record.details.get("expected_undetectable")
            if tag is not None:
                assert tag is (not record.evidence_paths), where
    if v.group == GROUP_NONRESPONSE_VS_FORGERY:
        [forgery] = [r for r in ev.b.records if r.spec.subtype == "dispense_forgery"]
        assert (
            forgery.details["expected_undetectable"]
            is ev.indistinguishable_by_construction
        )
        assert {r.spec.subtype for r in ev.b.records} == {
            "dispense_forgery"
        }  # no spoof is made
    # the hidden visits are an injector view only: the stream still holds the base visits
    robot = {
        GROUP_DOUBLE_TAKE_VS_BOUNCE: g1("double_take_gap", True, True),
        GROUP_NONRESPONSE_VS_FORGERY: g2("naive", True, False),
        GROUP_REFUSAL_VS_ROBOT_MISSED: G3_REPORTED,
    }[v.group]
    assert ev.a.stream.visits == ev.b.stream.visits == evaluated(robot).a.stream.visits
    assert ev.a.stream.visits


@pytest.mark.parametrize("v", G2_GRID, ids=lambda v: v.variant_id)
def test_the_forgery_tag_agrees_with_the_computed_flag_on_the_whole_grid(
    v: Variant,
) -> None:
    ev = evaluated(v)
    [forgery] = [r for r in ev.b.records if r.spec.subtype == "dispense_forgery"]
    assert (
        forgery.details["expected_undetectable"] is ev.indistinguishable_by_construction
    )
    assert (
        forgery.details["indistinguishable_by_construction"]
        is ev.indistinguishable_by_construction
    )
    assert (forgery.details["expected_undetectable"]) is (not forgery.evidence_paths)


def test_refusal_vs_robot_missed_pair() -> None:
    ev = evaluated(G3_REPORTED)
    tick = SCHED_TWO.measurement_ticks_ms[BASE.measurement_index]
    a, b = ev.a, ev.b
    assert {r.spec.subtype for r in a.records} == {"measurement_refusal"}
    assert {r.spec.subtype for r in b.records} == {"manipulation_failure"}
    assert (a.records[0].spec.cls, b.records[0].spec.cls) == (C1, C2)
    assert a.records[0].spec.onset_ms == b.records[0].spec.onset_ms == tick
    assert {r.confounder_group for r in a.records + b.records} == {
        GROUP_REFUSAL_VS_ROBOT_MISSED
    }
    # both lack the measurement at the tick
    for day in (a.observed, b.observed):
        meas = [e.t_device_ms for e in day.events if e.kind is EventKind.MEASUREMENT]
        assert len(meas) == len(SCHED_TWO.measurement_ticks_ms) - 1
        assert not [t for t in meas if tick <= t < tick + 10 * MIN]
        bps = [s.t_device_ms for s in day.samples if s.signal == "bp"]
        assert not [t for t in bps if tick <= t < tick + 10 * MIN]
    # the latent days differ: the refused measurement is absent from the latent day only
    assert tick not in times_of(a.latent, EventKind.MEASUREMENT)
    assert tick in times_of(b.latent, EventKind.MEASUREMENT)
    # the robot task outcome differs: declined against failed
    outcomes = lambda day: [
        (e.payload["task"], e.payload["outcome"])
        for e in day.events
        if e.kind is EventKind.ROBOT_TASK and e.payload["task"] == "manipulate"
    ]
    assert outcomes(a.observed) == [("manipulate", "declined")]
    assert outcomes(b.observed) == [("manipulate", "failed")]
    assert ev.separated_by == ("robot_task_outcome",)
    # without the outcome (or without the robot) the two are the same stream
    for withheld in (G3_WITHHELD, G3_ABSENT):
        w = evaluated(withheld)
        assert w.separated_by == () and w.indistinguishable_by_construction is True
        assert [s for s in w.a.observed.samples if s.signal == "bp"] == [
            s for s in w.b.observed.samples if s.signal == "bp"
        ]
        assert not [e for e in w.a.observed.events if e.kind is EventKind.ROBOT_TASK]


def test_confounder_group_carried_by_records_of_both_members() -> None:
    for grid, group in (
        (G1_GRID, GROUP_DOUBLE_TAKE_VS_BOUNCE),
        (G2_GRID, GROUP_NONRESPONSE_VS_FORGERY),
        (G3_GRID, GROUP_REFUSAL_VS_ROBOT_MISSED),
    ):
        for v in grid[:3]:
            ev = evaluated(v)
            for member in (ev.a, ev.b):
                assert member.records, v.variant_id
                assert all(r.confounder_group == group for r in member.records)
                assert all(r.spec.confounder_group == group for r in member.records)
                # the truth of a C2 or C3 record carries the group; C1 truth is the labeller's
                assert all(g.confounder_group == group for g in member.ground_truth)
                assert all(g.cls is not C1 for g in member.ground_truth)
                assert all(g.injected for g in member.ground_truth)
    # ordinary injections carry None, whatever their class
    assert refusal(SCHED_ONE.measurement_ticks_ms[0]).confounder_group is None
    out = assemble([spike(HOUR, HOUR, 10.0)])[0]
    assert out.c1_records[0].confounder_group is None
    stream_ = observed_of(assemble()[0])
    bias = InjectionSpec(
        C2, "cuff_silent_bias", 6 * HOUR, 6 * HOUR, 5.0, "mmHg", {"target": "cuff"}
    )
    result = apply_observation_injections(
        stream_, [bias], InjectionContext(PATIENT_INDEX)
    )
    assert all(r.confounder_group is None for r in result.records)
    assert all(g.confounder_group is None for g in ground_truth_events(result.records))


def test_pair_records_flag_indistinguishable_by_construction() -> None:
    for v, flag in (
        (g1("double_take_gap", False, False), True),
        (g1("nominal", True, True), False),
        (g2("informed", True, False), True),
        (g2("informed", True, True), False),
        (G3_WITHHELD, True),
        (G3_REPORTED, False),
    ):
        ev = evaluated(v)
        assert ev.indistinguishable_by_construction is flag, v.variant_id
        for member in (ev.a, ev.b):
            log = member.log
            assert len(log) == len(member.records) and log
            for entry in log:
                assert entry["variant_id"] == v.variant_id
                assert entry["indistinguishable_by_construction"] is flag
                assert entry["confounder_group"] == v.group
                assert entry["details"]["variant_id"] == v.variant_id
            assert log == confounder_log(member.records)
            json.dumps(log, allow_nan=False)  # a JSON-native sidecar
    # an ordinary record has neither key
    plain = injection_log(assemble([spike(HOUR, HOUR, 10.0)])[0].c1_records)
    assert (
        "variant_id" not in plain[0]
        and "indistinguishable_by_construction" not in plain[0]
    )


# ---------------------------------------------------------------------------
# Test 19: provenance of the rows and the grid
# ---------------------------------------------------------------------------


def check_variant_grid_structure(path: Path) -> None:
    design = load_confounder_design(path)
    assert set(design) == set(GROUPS)
    for group, variants in design.items():
        assert variants, group
        ids = [v.variant_id for v in variants]
        assert len(ids) == len(set(ids))
        for v in variants:
            assert v.group == group
            assert (
                v.source_type in SOURCE_TYPES
                and v.source_ref.strip()
                and v.rationale.strip()
            )
            assert set(v.withheld) <= {
                "content_change",
                "witness",
                "robot_task_outcome",
                "verification",
            }


def test_c1_and_confounder_rows_have_provenance(tmp_path: Path) -> None:
    for path in (
        INJECTIONS_FILE,
        rewrite_rows(tmp_path, filled=False, name="u.yaml"),
        rewrite_rows(tmp_path, filled=True, name="f.yaml"),
    ):
        check_c1_design_structure(path)
        check_variant_grid_structure(path)
        rows = design_rows(path)
        assert rows, "the task adds rows to injections.yaml"
        for row in rows:
            assert row["source_type"] in SOURCE_TYPES, row["parameter"]
            assert row["source_ref"] and row["source_ref"].strip()
            assert row["source_type"] == "design_choice"  # agent-proposed grid points
        design = load_c1_design(path)
        for subtype, entry in design.items():
            if entry.magnitude is not None:
                assert len(entry.magnitude.levels) >= 3, subtype
    # every row of the task is read by the loader (none is orphaned in `parameters:`)
    document = yaml.safe_load(INJECTIONS_FILE.read_text(encoding="utf-8"))
    named = {
        level.name
        for entry in load_c1_design(INJECTIONS_FILE).values()
        for block in (entry.duration, entry.magnitude)
        if block is not None
        for level in block.levels
    }
    assert {r["parameter"] for r in design_rows(INJECTIONS_FILE)} == named
    assert document["injections"]["c1"]  # the structured section exists
    # at least three magnitude levels per C1 magnitude is enforced by the loader
    short = copy.deepcopy(
        yaml.safe_load((tmp_path / "f.yaml").read_text(encoding="utf-8"))
    )
    levels = short["injections"]["c1"]["hypertensive_spike"]["magnitude"]["levels"]
    levels.pop(next(iter(levels)))
    bad = tmp_path / "two_levels.yaml"
    bad.write_text(yaml.safe_dump(short, sort_keys=False), encoding="utf-8")
    with pytest.raises(InjectionError):
        load_c1_design(bad)
    # a variant without provenance is refused
    broken = copy.deepcopy(
        yaml.safe_load((tmp_path / "f.yaml").read_text(encoding="utf-8"))
    )
    group = next(iter(broken["confounders"]["groups"].values()))
    next(iter(group["variants"].values())).pop("source_ref")
    bad2 = tmp_path / "no_ref.yaml"
    bad2.write_text(yaml.safe_dump(broken, sort_keys=False), encoding="utf-8")
    with pytest.raises(InjectionError):
        load_confounder_design(bad2)


def test_committed_grid_matches_the_computed_separation() -> None:
    """The ``expected_indistinguishable`` of every committed variant is what the code computes."""
    design = load_confounder_design(INJECTIONS_FILE)
    for variants in design.values():
        for v in variants:
            ev = evaluated(v)
            assert (
                ev.indistinguishable_by_construction is v.expected_indistinguishable
            ), v.variant_id
    # the grid has separable and indistinguishable variants for every group (abstention can be scored)
    for group, variants in design.items():
        flags = {v.expected_indistinguishable for v in variants}
        assert flags == {True, False}, group


# ---------------------------------------------------------------------------
# compare_observed: each discriminator on its own, hand-written days
# ---------------------------------------------------------------------------


def S(signal: str, t: int, value: float = 1.0, seq: int | None = None) -> Sample:
    return Sample(signal, t, t, value, seq, None)


def E(
    kind: EventKind,
    t: int,
    source: str,
    payload: Mapping[str, Any] | None = None,
    seq: int | None = None,
) -> Event:
    return Event(kind, t, t, source, dict(payload or {}), seq)


def day_of(samples: Iterable[Sample] = (), events: Iterable[Event] = ()) -> ObservedDay:
    return ObservedDay(
        "p0", 0, 0,
        tuple(sorted(samples, key=lambda s: s.t_rx_ms)),
        tuple(sorted(events, key=lambda e: e.t_rx_ms)),
        "plan-1",
    )  # fmt: skip


VISITS = (RobotVisit(0, "dose", DOSE, DOSE, DOSE + DWELL, 0),)
D0 = E(EventKind.DISPENSE, DOSE, "dispenser", {}, 1)


def test_compare_observed_names_each_discriminating_field() -> None:
    base = day_of([S("bp", DOSE, 120.0)], [D0])
    assert compare_observed(base, base, VISITS, ()) == ()
    cases: dict[str, tuple[ObservedDay, ObservedDay]] = {
        "content_change": (
            day_of(
                events=[
                    E(EventKind.DISPENSE, DOSE, "dispenser", {"content_change": 1.0}, 1)
                ]
            ),
            day_of(
                events=[
                    E(EventKind.DISPENSE, DOSE, "dispenser", {"content_change": 0.0}, 1)
                ]
            ),
        ),
        "witness": (
            day_of(events=[E(EventKind.INTAKE, DOSE + LAG, "robot")]),
            day_of(),
        ),
        "robot_task_outcome": (
            day_of(
                events=[
                    E(
                        EventKind.ROBOT_TASK,
                        DOSE,
                        "robot",
                        {"task": "manipulate", "outcome": "failed", "patient_id": "p0"},
                    )
                ]
            ),
            day_of(
                events=[
                    E(
                        EventKind.ROBOT_TASK,
                        DOSE,
                        "robot",
                        {
                            "task": "manipulate",
                            "outcome": "declined",
                            "patient_id": "p0",
                        },
                    )
                ]
            ),
        ),
        "dispense_interval": (
            day_of(events=[D0, E(EventKind.DISPENSE, DOSE + 500, "dispenser", {}, 2)]),
            day_of(events=[D0, E(EventKind.DISPENSE, DOSE + GAP, "dispenser", {}, 2)]),
        ),
        "dispense_seq": (
            day_of(events=[E(EventKind.DISPENSE, DOSE, "dispenser", {}, 1)]),
            day_of(events=[E(EventKind.DISPENSE, DOSE, "dispenser", {}, 5)]),
        ),
        "verification": (
            day_of(
                events=[
                    E(
                        EventKind.VERIFICATION,
                        DOSE,
                        "gateway",
                        {"verification": "failed", "subject": "dispenser"},
                    )
                ]
            ),
            day_of(),
        ),
        "other": (day_of([S("bp", 1, 120.0)]), day_of([S("bp", 1, 121.0)])),
    }
    for field, (a, b) in cases.items():
        assert compare_observed(a, b, VISITS, ()) == (field,), field
        assert compare_observed(b, a, VISITS, ()) == (field,), field  # symmetric
        if field != "other":
            assert compare_observed(a, b, VISITS, (field,)) == (), field  # masked
    # the pressure channel is ignored on request, only there
    a, b = cases["other"]
    assert compare_observed(a, b, VISITS, (), ignore_pressure=True) == ()
    assert compare_observed(
        day_of([S("hr_ecg", 1, 70.0)]),
        day_of([S("hr_ecg", 1, 71.0)]),
        VISITS,
        (),
        ignore_pressure=True,
    ) == ("other",)


def test_compare_observed_presence_is_a_level_over_the_visit() -> None:
    one = day_of([S("presence", DOSE)])
    extra_in_visit = day_of([S("presence", DOSE), S("presence", DOSE + LAG)])
    assert (
        compare_observed(one, extra_in_visit, VISITS, ()) == ()
    )  # a held level: no new information
    outside = day_of([S("presence", DOSE), S("presence", DOSE + 2 * DWELL)])
    assert compare_observed(one, outside, VISITS, ()) == (
        "witness",
    )  # a sample off every visit
    no_visit = day_of()
    assert compare_observed(one, no_visit, VISITS, ()) == ("witness",)
    assert compare_observed(one, no_visit, VISITS, ("witness",)) == ()
    # the order of items at one instant is not a difference
    x = E(EventKind.SCHEDULE_TICK, 5, "ward", {"kind": "dose"})
    y = E(EventKind.NODE_STATE, 5, "cuff", {"state": "active"})
    assert (
        compare_observed(day_of(events=[x, y]), day_of(events=[y, x]), VISITS, ()) == ()
    )


def test_compare_observed_reads_observed_days_only() -> None:
    sig = inspect.signature(compare_observed)
    for name in ("a", "b"):
        assert sig.parameters[name].annotation in (ObservedDay, "ObservedDay")
    code_names = set(compare_observed.__code__.co_names)
    assert not code_names & {"LatentDay", "latent", "LatentResult", "baseline_sbp_mmhg"}
    src = inspect.getsource(confounders_mod)
    comparison = src[src.index("def compare_observed") :]
    comparison = comparison[: comparison.index("\ndef ", 10)]
    assert "latent" not in comparison.lower()


# ---------------------------------------------------------------------------
# Paired design, determinism and independence
# ---------------------------------------------------------------------------


def snapshot(result: LatentResult) -> Any:
    return (
        result.latent,
        result.behaviour_log,
        result.refused_ticks_ms,
        result.baseline_sbp_mmhg,
        result.end_state,
    )


def test_assembly_is_deterministic_and_seeded() -> None:
    specs = [spike(HOUR, HOUR, 10.0), nonresponse(DOSE, HOUR, 0.5)]
    cfg = make_config(adherence=NATURAL)
    one = assemble(
        specs, patient=NOISY_PATIENT, schedule=SCHED_TWO, n_days=2, config=cfg
    )
    two = assemble(
        specs, patient=NOISY_PATIENT, schedule=SCHED_TWO, n_days=2, config=cfg
    )
    assert [snapshot(r) for r in one] == [snapshot(r) for r in two]
    other = assemble(
        specs,
        patient=NOISY_PATIENT,
        schedule=SCHED_TWO,
        n_days=2,
        config=cfg,
        seed=SEED + 1,
    )
    assert bp_series(other[0]) != bp_series(one[0])
    other_patient = assemble(
        specs,
        patient=NOISY_PATIENT,
        schedule=SCHED_TWO,
        n_days=2,
        config=cfg,
        patient_index=PATIENT_INDEX + 1,
    )
    assert bp_series(other_patient[0]) != bp_series(one[0])
    # the order of the specs is irrelevant
    swapped = assemble(
        specs[::-1], patient=NOISY_PATIENT, schedule=SCHED_TWO, n_days=2, config=cfg
    )
    assert [snapshot(r) for r in swapped] == [snapshot(r) for r in one]
    assert [r.c1_records for r in swapped] == [r.c1_records for r in one]


def test_adding_one_c1_injection_leaves_everything_it_does_not_touch_identical() -> (
    None
):
    cfg = make_config(adherence=NATURAL)
    base = assemble(patient=NOISY_PATIENT, schedule=SCHED_TWO, n_days=2, config=cfg)
    far = 10 * HOUR + 3 * MIN
    cases: list[tuple[InjectionSpec, Callable[[int], bool]]] = [
        (spike(far, HOUR, 10.0), lambda t: far <= t < far + HOUR),
        (hypo(far, HOUR, 10.0), lambda t: far <= t < far + HOUR),
        (nonresponse(DOSE, HOUR, 0.5), lambda t: t >= DOSE),  # an intake's drug lasts
        (refusal(SCHED_TWO.measurement_ticks_ms[1]), lambda t: False),
    ]
    for spec, touches in cases:
        out = assemble(
            [spec], patient=NOISY_PATIENT, schedule=SCHED_TWO, n_days=2, config=cfg
        )
        for plain, injected in zip(base, out, strict=True):
            # the draws (adherence, noise, vitals) and the latent baseline are untouched
            assert plain.behaviour_log == injected.behaviour_log
            assert plain.baseline_sbp_mmhg == injected.baseline_sbp_mmhg
            assert dispense_intake(plain) == dispense_intake(injected)
            assert [s for s in plain.latent.samples if s.signal != "bp"] == [
                s for s in injected.latent.samples if s.signal != "bp"
            ]
        a, b = bp_series(base[0]), bp_series(out[0])
        if spec.subtype == "measurement_refusal":
            assert a == b  # the pressure is untouched; only a measurement is gone
        else:
            assert all(a[t] == b[t] for t in a if not touches(t)), spec.subtype
            assert any(a[t] != b[t] for t in a if touches(t)), spec.subtype


def test_c1_stream_is_the_named_injection_stream() -> None:
    spec = spike(HOUR, HOUR, 10.0)
    again = spike(
        HOUR, HOUR, 99.0
    )  # a different magnitude: the same injection identity
    one = c1_stream(SEED, PATIENT_INDEX, 0, spec).standard_normal(4).tolist()
    assert one == c1_stream(SEED, PATIENT_INDEX, 0, again).standard_normal(4).tolist()
    expected = stream(
        SEED, PATIENT_INDEX, 0, StreamPurpose.INJECTION_C1, injection_sub_index(spec)
    ).standard_normal(4)
    assert one == expected.tolist()
    assert (
        one
        != c1_stream(SEED, PATIENT_INDEX, 0, spike(2 * HOUR, HOUR, 10.0))
        .standard_normal(4)
        .tolist()
    )
    assert one != c1_stream(SEED, PATIENT_INDEX, 1, spec).standard_normal(4).tolist()
    # the injectors themselves are deterministic functions of the spec: no draw is consumed
    source = (SRC / "inject_c1.py").read_text(encoding="utf-8")
    assert "default_rng" not in source and "np.random." not in source.replace(
        "np.random.Generator", ""
    )
    assert "import random" not in source and "time." not in source.replace(
        "datetime", ""
    )


def test_pair_members_do_not_shift_each_others_draws() -> None:
    v = g1("double_take_gap", True, True)
    ev = evaluated(v)
    # the draws of the cuff and of the vitals are the same whatever the mechanism
    assert [m.error_mmhg for m in ev.a.stream.measurements] == [
        m.error_mmhg for m in ev.b.stream.measurements
    ]
    hr = lambda r: [s.value for s in r.latent.latent.samples if s.signal == "hr_ecg"]
    assert hr(ev.a) == hr(ev.b)
    # the second dose is natural in both members and bit-identical
    assert [r for r in dispense_intake(ev.a.latent) if r[1] >= 20 * HOUR] == [
        r for r in dispense_intake(ev.b.latent) if r[1] >= 20 * HOUR
    ]
    # the same pair evaluated twice is identical
    again = evaluate_pair(v.group, v, BASE)
    assert again.a.observed == ev.a.observed and again.b.observed == ev.b.observed
    assert again.a.log == ev.a.log and again.separated_by == ev.separated_by


# ---------------------------------------------------------------------------
# Continuity across midnight
# ---------------------------------------------------------------------------


def chained(n_days: int, **kwargs: Any) -> list[LatentResult]:
    """``n_days`` one-day assemblies, each carrying the state of the previous one."""
    out: list[LatentResult] = []
    state: AssemblyState | None = None
    for day in range(n_days):
        [result] = assemble(start_day=day, state=state, **kwargs)
        out.append(result)
        state = result.end_state
    return out


def test_three_day_assembly_equals_three_one_day_assemblies_that_carry_state() -> None:
    cfg = make_config(adherence=NATURAL)
    specs = [
        spike(HOUR, HOUR, 10.0),
        nonresponse(DAY + 8 * HOUR, 12 * HOUR, 0.5),  # day 1
        refusal(2 * DAY + SCHED_LATE.measurement_ticks_ms[0]),
    ]
    kwargs: dict[str, Any] = {
        "patient": NOISY_PATIENT, "schedule": SCHED_LATE, "config": cfg, "specs": specs,
    }  # fmt: skip
    whole = assemble(n_days=3, **kwargs)
    parts = chained(3, **kwargs)
    assert len(whole) == 3
    for w, p in zip(whole, parts, strict=True):
        assert snapshot(w) == snapshot(p)
        assert w.c1_records == p.c1_records
    # each record is returned once, with the day of its onset
    for day, result in enumerate(whole):
        assert [r.spec.onset_ms // DAY for r in result.c1_records] == [day]
        times = {s.signal: [] for s in result.latent.samples}
        for sample in result.latent.samples:
            times[sample.signal].append(sample.t_device_ms)
        for signal, values in times.items():  # every sample of a day lies in that day
            assert day * DAY <= min(values) and max(values) < (day + 1) * DAY, (
                day,
                signal,
            )
            assert min(values) == day * DAY, (day, signal)
    # the end state of a call is the state to continue from: a 4-day call equals the 3-day call
    # followed by the call that starts at day 3 with its end state
    four = assemble(n_days=4, **kwargs)
    [day3] = assemble(start_day=3, state=whole[-1].end_state, **kwargs)
    assert snapshot(day3) == snapshot(four[3]) and day3.latent.day_index == 3
    assert [snapshot(r) for r in four[:3]] == [snapshot(r) for r in whole]


def test_midnight_carries_the_drug_the_noise_and_the_chain() -> None:
    cfg = make_config(adherence=NATURAL)
    kwargs: dict[str, Any] = {
        "patient": NOISY_PATIENT,
        "schedule": SCHED_LATE,
        "config": cfg,
    }
    whole = assemble(n_days=2, **kwargs)
    # (1) drug accumulation: the dose of day 0 at 23:50 acts on day 1 (intake 23:50:05, effect at 00:30)
    perfect = make_config(adherence=PERFECT)
    both = assemble(n_days=2, patient=FIX_PATIENT, schedule=SCHED_LATE, config=perfect)
    carried = bp_series(both[1])
    t = DAY + 30 * MIN  # 40 minutes after the intake, near the effect peak
    assert 130.0 - carried[t] > 5.0  # a large drop on day 1 caused by the dose of day 0
    # without the history of day 0 the effect is gone: a day 1 assembled alone has none of it
    [alone] = assemble(
        start_day=1,
        state=AssemblyState(1, 0.0, None, ()),
        patient=FIX_PATIENT,
        schedule=SCHED_LATE,
        config=perfect,
    )
    assert 130.0 - bp_series(alone)[t] < 130.0 - carried[t] - 5.0
    # (2) autoregressive noise continues: day 1 starts from the last value of day 0
    first_noise_day1 = whole[1].baseline_sbp_mmhg[0]
    last_noise_day0 = whole[0].end_state.ar_state_mmhg
    assert whole[0].end_state.next_day == 1 and whole[1].end_state.next_day == 2
    reset = chained(2, **kwargs)[1].baseline_sbp_mmhg[0]
    assert first_noise_day1 == reset
    assert last_noise_day0 == whole[0].end_state.ar_state_mmhg
    # a state that is not carried (a fresh AR state) gives another day 1
    [fresh] = assemble(
        start_day=1,
        state=AssemblyState(
            1, 0.0, whole[0].end_state.chain_state, whole[0].end_state.intake_times_ms
        ),
        **kwargs,
    )
    assert fresh.baseline_sbp_mmhg != whole[1].baseline_sbp_mmhg
    # (3) the adherence chain continues: the carried state is the last outcome of day 0
    assert whole[0].end_state.chain_state is whole[0].behaviour_log[-1].state


def test_assembly_state_must_match_the_start_day() -> None:
    [first] = assemble()
    for state in (None, first.end_state):
        with pytest.raises(LatentAssemblyError):
            assemble(start_day=2, state=state)  # the state is of day 1, or absent
    with pytest.raises(LatentAssemblyError):
        assemble(
            start_day=0, state=first.end_state
        )  # a start from day 0 has no state to carry
    with pytest.raises(LatentAssemblyError):
        assemble(state="state")  # type: ignore[arg-type]
    assert first.end_state.next_day == 1
    assert first.end_state.intake_times_ms == tuple(times_of(first, EventKind.INTAKE))


# ---------------------------------------------------------------------------
# Spec validation, windows and bounds
# ---------------------------------------------------------------------------


def test_c1_specs_validation_table() -> None:
    ok = [spike(HOUR, HOUR, 5.0)]
    assert check_c1_specs(ok) == tuple(ok)
    bad_specs: list[Any] = [
        InjectionSpec(C2, "hypertensive_spike", HOUR, HOUR, 5.0, "mmHg"),  # not a C1
        InjectionSpec(C1, "no_such_subtype", HOUR, HOUR, 5.0, "mmHg"),
        InjectionSpec(
            C1, "hypertensive_spike", HOUR, None, 5.0, "mmHg"
        ),  # a window needs a duration
        InjectionSpec(
            C1, "hypertensive_spike", HOUR, HOUR, None, None
        ),  # needs a magnitude
        InjectionSpec(C1, "hypertensive_spike", HOUR, HOUR, 5.0, "ms"),  # wrong unit
        InjectionSpec(
            C1, "hypertensive_spike", HOUR, HOUR, 0.0, "mmHg"
        ),  # must be above zero
        InjectionSpec(
            C1, "hypertensive_spike", HOUR, HOUR, -5.0, "mmHg"
        ),  # the sign is the subtype's
        InjectionSpec(C1, "hypotension_below_hold", HOUR, HOUR, -5.0, "mmHg"),
        InjectionSpec(
            C1, "drug_nonresponse", HOUR, HOUR, 1.5, "1"
        ),  # a scale above 1 is no non-response
        InjectionSpec(C1, "drug_nonresponse", HOUR, HOUR, -0.5, "1"),
        InjectionSpec(C1, "drug_nonresponse", HOUR, HOUR, 0.5, "mmHg"),
        InjectionSpec(C1, "measurement_refusal", HOUR, HOUR),  # a refusal is per tick
        InjectionSpec(
            C1, "measurement_refusal", HOUR, None, 1.0, "1"
        ),  # and has no magnitude
        InjectionSpec(C1, "double_take", HOUR, None, 1.0, "1"),
        InjectionSpec(
            C1, "hypertensive_spike", HOUR, HOUR, 5.0, "mmHg", {"foo": 1}
        ),  # unknown param
        InjectionSpec(
            C1,
            "hypertensive_spike",
            HOUR,
            HOUR,
            5.0,
            "mmHg",
            {"multiple": 2.0, "reference_value": 20.0, "reference": "scale_range"},
        ),  # 5 != 2 * 20
        # windows beyond the day, and a window that crosses midnight
        InjectionSpec(C1, "hypertensive_spike", DAY - HOUR, 2 * HOUR, 5.0, "mmHg"),
        InjectionSpec(C1, "hypotension_below_hold", 5 * DAY - 1, 2, 5.0, "mmHg"),
        # two windows of one subtype that overlap (a touching pair is fine, see below)
    ]
    for spec in bad_specs:
        with pytest.raises(C1InjectionError):
            check_c1_specs([spec])
    with pytest.raises(C1InjectionError):
        check_c1_specs([spike(HOUR, 2 * HOUR, 5.0), spike(2 * HOUR, HOUR, 5.0)])
    with pytest.raises(C1InjectionError):  # an identical pair is an overlap
        check_c1_specs([spike(HOUR, HOUR, 5.0), spike(HOUR, HOUR, 5.0)])
    with pytest.raises(C1InjectionError):  # two refusals of one tick
        check_c1_specs([refusal(HOUR), refusal(HOUR)])
    with pytest.raises(C1InjectionError):
        check_c1_specs([double_take_spec(HOUR), double_take_spec(HOUR)])
    check_c1_specs(
        [spike(HOUR, HOUR, 5.0), spike(2 * HOUR, HOUR, 5.0)]
    )  # touching windows
    check_c1_specs(
        [spike(HOUR, HOUR, 5.0), hypo(HOUR, HOUR, 5.0)]
    )  # different subtypes overlap
    check_c1_specs([nonresponse(HOUR, HOUR, 0.0), nonresponse(2 * HOUR, HOUR, 1.0)])
    # negative durations and onsets never reach a spec (the generic spec refuses them)
    for onset, duration in ((-1, HOUR), (HOUR, -1), (HOUR, 0)):
        with pytest.raises(InjectionError):
            c1_spec("hypertensive_spike", onset, duration_ms=duration, magnitude=5.0)


def test_windows_beyond_the_day_or_the_horizon_raise_the_named_error() -> None:
    with pytest.raises(C1InjectionError):
        assemble([spike(DAY - HOUR, 2 * HOUR, 5.0)])
    # a window of a later day than the call is allowed (a chained call passes the whole list)
    out = assemble([spike(DAY + HOUR, HOUR, 5.0)])[0]
    assert out.c1_records == () and bp_series(out) == bp_series(assemble()[0])
    # the window must end by the day end exactly: [DAY - 1 hour, DAY) is the last admissible one
    ok = assemble([spike(DAY - HOUR, HOUR, 5.0)])[0]
    assert (
        ok.c1_records[0].realised
        and bp_series(ok)[DAY - STEP] == bp_series(assemble()[0])[DAY - STEP] + 5.0
    )


def test_canonical_order_is_independent_of_the_input_order() -> None:
    specs = [
        spike(3 * HOUR, HOUR, 5.0),
        refusal(HOUR),
        nonresponse(DOSE, HOUR, 0.5),
        spike(HOUR, HOUR, 5.0),
        hypo(2 * HOUR, HOUR, 5.0),
        double_take_spec(DOSE),
    ]
    first = canonical_c1_order(specs)
    for shuffled in itertools.islice(itertools.permutations(specs), 40):
        assert canonical_c1_order(list(shuffled)) == first
    assert [s.subtype for s in first][:2] == [
        "hypertensive_spike",
        "hypertensive_spike",
    ]
    assert tuple(s.subtype for s in first) == tuple(
        sorted((s.subtype for s in specs), key=C1_SUBTYPES.index)
    )


def test_spec_list_and_horizon_are_bounded() -> None:
    too_many = [spike(k * 2, 1, 1.0) for k in range(c1_mod.MAX_C1_SPECS + 1)]
    with pytest.raises(C1InjectionError):
        check_c1_specs(too_many)
    with pytest.raises(LatentAssemblyError):
        assemble(n_days=MAX_DAYS + 1)
    with pytest.raises(LatentAssemblyError):
        assemble(n_days=10**400)
    with pytest.raises(LatentAssemblyError):
        assemble(start_day=10**18)
    cfg = make_config(step=DAY // 2)  # the coarsest grid: two points a day
    assert len(assemble(n_days=3, config=cfg)) == 3
    # the work of one call is bounded: intakes times grid points
    with pytest.raises(LatentAssemblyError):
        many = Schedule(
            dose_ticks_ms=tuple(range(0, 30_000 * 1000, 1000)),
            measurement_ticks_ms=(),
        )
        assemble(
            schedule=many,
            config=make_config(step=SEC, adherence=make_adherence(gap=1000 - 1, lag=1)),
            n_days=1,
        )


# ---------------------------------------------------------------------------
# Extremes: every public function raises its named error, nothing else
# ---------------------------------------------------------------------------


class HashBomb(str):
    """A ``str`` whose hash raises (review F5): a dict lookup or a set membership blows up."""

    def __hash__(self) -> int:
        raise RuntimeError("hash")


class EqBomb(str):
    def __eq__(self, other: object) -> bool:
        raise RuntimeError("eq")

    def __ne__(self, other: object) -> bool:
        raise RuntimeError("ne")

    __hash__ = str.__hash__


class BoolBomb(str):
    def __bool__(self) -> bool:
        raise RuntimeError("bool")


class LenBomb(str):
    def __len__(self) -> int:
        raise RuntimeError("len")


class ReprBomb(str):
    def __str__(self) -> str:
        raise RuntimeError("str")

    def __repr__(self) -> str:
        raise RuntimeError("repr")


class IndexBomb(int):
    def __index__(self) -> int:
        raise RuntimeError("index")

    def __int__(self) -> int:
        raise RuntimeError("int")


class FloatBomb(float):
    def __float__(self) -> float:
        raise RuntimeError("float")

    def __repr__(self) -> str:
        raise RuntimeError("repr")


class CmpBomb(float):
    """A number that cannot be compared (an ordering or an equality test raises)."""

    def __le__(self, other: object) -> bool:
        raise RuntimeError("le")

    __lt__ = __ge__ = __gt__ = __le__

    def __eq__(self, other: object) -> bool:
        raise RuntimeError("eq")

    __hash__ = float.__hash__


class IterBomb(tuple):  # type: ignore[type-arg]
    def __iter__(self) -> Any:
        raise RuntimeError("iter")

    def __len__(self) -> int:
        raise RuntimeError("len")


class ItemBomb(list):  # type: ignore[type-arg]
    def __iter__(self) -> Any:
        raise RuntimeError("iter")

    def __getitem__(self, key: Any) -> Any:
        raise RuntimeError("getitem")


class MapBomb(dict):  # type: ignore[type-arg]
    def __iter__(self) -> Any:
        raise RuntimeError("iter")

    def __len__(self) -> int:
        raise RuntimeError("len")


class TruthBomb:
    def __bool__(self) -> bool:
        raise RuntimeError("bool")


STR_BOMBS = (HashBomb, EqBomb, BoolBomb, LenBomb, ReprBomb)
JUNK: list[Any] = [
    None, True, False, "x", "", b"1", 1.5, float("nan"), float("inf"), -float("inf"), -1, 0, 1,
    10**400, -(10**400), 1e308, np.int64(3), np.float64(1.5), np.bool_(True), np.str_("x"),
    np.array([1]), np.array(1), np.array([1, 2]), np.array([], dtype=float), [], {}, (),
    object(), [1, 2], {"a": 1}, {1, 2}, (None,), "a" * 300, complex(1, 1), range(3),
    HashBomb("witness"), EqBomb("witness"), BoolBomb("witness"), LenBomb("witness"),
    ReprBomb("witness"), IndexBomb(3), FloatBomb(1.5), CmpBomb(1.5), IterBomb((1,)), ItemBomb([1]),
    MapBomb({"a": 1}), TruthBomb(),
]  # fmt: skip


def show(junk: object) -> str:
    try:
        return repr(junk)[:60]
    except Exception:  # noqa: BLE001
        return f"<{type(junk).__name__}, repr raises>"


def fuzz(
    fn: Callable[..., Any], good: Mapping[str, Any], *, skip: Iterable[str] = ()
) -> int:
    """Call ``fn`` with each argument replaced by each junk value (and by a one-item list or tuple
    of it where the argument is one); only named errors may escape."""
    skipped = set(skip)
    calls = 0
    for name, value in good.items():
        if name in skipped:
            continue
        candidates = list(JUNK)
        if isinstance(value, (list, tuple)):
            candidates += [[junk] for junk in JUNK] + [(junk,) for junk in JUNK]
        for junk in candidates:
            args = dict(good)
            args[name] = junk
            calls += 1
            try:
                fn(**args)
            except Exception as exc:  # noqa: BLE001
                assert named_error(exc), (fn.__name__, name, show(junk), type(exc), exc)
    return calls


def fresh_work() -> LatentWork:
    work = LatentWork(
        0,
        np.arange(0, DAY, HOUR, dtype=np.int64),
        dose_ticks_ms=SCHED_ONE.dose_ticks_ms,
        measurement_ticks_ms=SCHED_ONE.measurement_ticks_ms,
        double_take_gap_ms=GAP,
    )
    work.set_intakes((DOSE + LAG,))
    return work


def test_extreme_inputs_c1_helpers() -> None:
    fuzz(
        c1_spec,
        {
            "subtype": "hypertensive_spike",
            "onset_ms": HOUR,
            "duration_ms": HOUR,
            "magnitude": 5.0,
        },
    )
    fuzz(
        c1_spec,
        {"subtype": "measurement_refusal", "onset_ms": HOUR},
        skip=("onset_ms",),
    )
    fuzz(
        hold_distance_mmhg,
        {"baseline_sbp_mmhg": 130.0, "bp_hold_threshold_mmhg": 100.0},
    )
    fuzz(
        resolve_c1_magnitude,
        {
            "level": level_row(2.0),
            "reference_value": 20.0,
            "reference": REFERENCE_SCALE_RANGE,
        },
    )
    fuzz(
        c1_spec_from_level,
        {
            "subtype": "hypertensive_spike",
            "onset_ms": HOUR,
            "level": level_row(2.0),
            "reference_value": 20.0,
            "duration_ms": HOUR,
        },
    )
    fuzz(check_c1_specs, {"specs": [spike(HOUR, HOUR, 5.0)]})
    fuzz(canonical_c1_order, {"specs": [spike(HOUR, HOUR, 5.0)]})
    fuzz(
        c1_stream,
        {
            "seed": SEED,
            "patient_index": 0,
            "day_index": 0,
            "spec": spike(HOUR, HOUR, 5.0),
        },
    )
    # the wrong type of a spec inside a list, and a list that is not a list
    for bad in (
        ["x"],
        [None],
        "ab",
        b"ab",
        5,
        {1: 2},
        iter([1]),
        [spike(HOUR, HOUR, 5.0)] * 3,
    ):
        try:
            check_c1_specs(bad)  # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001
            assert named_error(exc), (bad, exc)
    # arithmetic edges of the pressure references
    for baseline, threshold in ((100.0, 100.0), (90.0, 100.0), (1e308, -1e308)):
        with pytest.raises(C1InjectionError):
            hold_distance_mmhg(baseline, threshold)


def test_extreme_inputs_c1_injectors_and_work() -> None:
    for fn, spec in (
        (hypertensive_spike, spike(HOUR, HOUR, 5.0)),
        (hypotension_below_hold, hypo(HOUR, HOUR, 5.0)),
        (drug_nonresponse, nonresponse(DOSE, HOUR, 0.5)),
        (measurement_refusal, refusal(SCHED_ONE.measurement_ticks_ms[0])),
        (double_take, double_take_spec(DOSE)),
    ):
        fuzz(fn, {"work": fresh_work(), "specs": [spec]})
        # a spec of another subtype is refused, never mis-applied
        other = (
            spike(HOUR, HOUR, 5.0)
            if fn is not hypertensive_spike
            else hypo(HOUR, HOUR, 5.0)
        )
        with pytest.raises(C1InjectionError):
            fn(fresh_work(), [other])
    fuzz(
        LatentWork,
        {
            "day_index": 0,
            "t_ms": np.arange(0, DAY, HOUR, dtype=np.int64),
            "dose_ticks_ms": (DOSE,),
            "measurement_ticks_ms": (HOUR,),
            "double_take_gap_ms": GAP,
        },
    )
    work = fresh_work()
    fuzz(work.set_intakes.__func__, {"self": work, "times_ms": (1, 2)}, skip=("self",))  # type: ignore[attr-defined]
    stream_ = observed_of(assemble([refusal(SCHED_ONE.measurement_ticks_ms[0])])[0])
    records = assemble([refusal(SCHED_ONE.measurement_ticks_ms[0])])[0].c1_records
    fuzz(observe_refusals, {"stream_": stream_, "records": records})
    with pytest.raises(
        C1InjectionError
    ):  # a refusal whose tick has no visit in the stream
        observe_refusals(dataclasses.replace(stream_, visits=()), records)
    with pytest.raises(C1InjectionError):
        observe_refusals(stream_, [spike(HOUR, HOUR, 5.0)])  # a spec is not a record
    assert observe_refusals(stream_, ()) == stream_  # nothing to observe


def test_extreme_inputs_latent_assembly() -> None:
    good: dict[str, Any] = {
        "patient": FIX_PATIENT,
        "schedule": SCHED_ONE,
        "n_days": 1,
        "c1_specs": [],
        "response_model": OneCompartmentEmax(),
        "library": LIB,
        "seed": SEED,
        "patient_index": 0,
        "config": make_config(step=HOUR),
    }
    calls = fuzz(assemble_latent_days, good)
    assert calls > 150
    fuzz(
        assemble_latent_days,
        {**good, "start_day": 0, "state": None, "forced_slots": ()},
        skip=tuple(good),
    )
    fuzz(
        AssemblyConfig,
        {
            "latent_step_ms": HOUR,
            "circadian_peak_clock_ms": PEAK_CLOCK,
            "ar_reference_step_ms": HOUR,
            "adherence": PERFECT,
            "vitals": DESIGN,
            "allow_no_segments": False,
        },
    )
    fuzz(ForcedSlot, {"day_index": 0, "dose_index": 0, "state": AdherenceState.OMITTED})
    fuzz(
        AssemblyState,
        {
            "next_day": 1,
            "ar_state_mmhg": 0.0,
            "chain_state": None,
            "intake_times_ms": (),
        },
    )

    # a response model that misbehaves is a named error as well
    class Broken:
        def effect_mmhg(self, *args: Any, **kwargs: Any) -> Any:
            raise ZeroDivisionError("broken model")

    class Wrong:
        def effect_mmhg(self, *args: Any, **kwargs: Any) -> Any:
            return [1.0]

    for model in (Broken(), Wrong(), object(), None):
        with pytest.raises(LatentAssemblyError):
            assemble_latent_days(
                FIX_PATIENT,
                SCHED_ONE,
                1,
                [],
                model,
                LIB,
                SEED,
                0,
                config=make_config(step=HOUR),  # type: ignore[arg-type]
            )
    with pytest.raises(LatentAssemblyError):  # a library without heart-rate segments
        assemble(library=SegmentLibrary.from_memory([]))
    ok = assemble(
        library=SegmentLibrary.from_memory([]),
        config=make_config(allow_no_segments=True),
    )[0]
    assert {s.signal for s in ok.latent.samples} == {"bp"}  # no vitals are invented


def test_the_number_of_days_is_bounded_exactly() -> None:
    # one vitals point a day and two pressure points a day keep the work small enough to hit the
    # bound on the number of days itself rather than the bound on the work
    coarse = dataclasses.replace(
        make_config(step=DAY // 2),
        vitals=dataclasses.replace(DESIGN, vitals_period_ms=DAY),
    )
    with pytest.raises(LatentAssemblyError):
        assemble(n_days=0, config=coarse)
    with pytest.raises(LatentAssemblyError):
        assemble(n_days=MAX_DAYS + 1, config=coarse)
    week = assemble(n_days=MAX_DAYS, config=coarse)
    assert len(week) == MAX_DAYS and week[-1].latent.day_index == MAX_DAYS - 1


def test_extreme_inputs_schedules_and_spec_lists() -> None:
    cfg = make_config(step=HOUR)
    # an unsorted, duplicate or huge schedule never reaches the assembly: Schedule refuses it
    for ticks in ((2 * HOUR, HOUR), (HOUR, HOUR), (DAY,), (-1,), (10**400,)):
        with pytest.raises(ValueError):
            Schedule(dose_ticks_ms=ticks, measurement_ticks_ms=())
    # a spec list given twice, or a spec of another day than the schedule has, is handled
    spec = spike(HOUR, HOUR, 5.0)
    with pytest.raises(C1InjectionError):
        assemble([spec, spec], config=cfg)
    assert len(assemble([spike(5 * DAY + HOUR, HOUR, 5.0)], config=cfg)) == 1


# ---------------------------------------------------------------------------
# The pair builder, the variants and the YAML grid
# ---------------------------------------------------------------------------


def test_group_names_are_the_workstream_vocabulary() -> None:
    assert GROUPS == (
        "double_take_vs_bounce",
        "nonresponse_vs_falsified_dispense",
        "refusal_vs_robot_missed",
    )
    readme = (ROOT / "docs/plan/workstreams/WS04-benchmark/README.md").read_text(
        encoding="utf-8"
    )
    for group in GROUPS:
        assert group in readme
    assert DISCRIMINATORS == (
        "content_change", "witness", "robot_task_outcome", "dispense_interval",
        "dispense_seq", "verification",
    )  # fmt: skip


def test_build_confounder_pair_scenarios() -> None:
    v = g1("double_take_gap", False, True)
    a, b = build_confounder_pair(v.group, v, BASE)
    assert (
        a.group == b.group == v.group and a.variant_id == b.variant_id == v.variant_id
    )
    assert (
        [s.subtype for s in a.c1_specs] == ["double_take"]
        and not a.c2_specs
        and not a.c3_specs
    )
    assert [s.subtype for s in b.c2_specs] == ["dispenser_bounce"] and not b.c1_specs
    assert (
        b.c2_specs[0].magnitude == GAP
    )  # the stress level: the double-take gap itself
    assert b.c2_specs[0].onset_ms == DOSE and a.c1_specs[0].onset_ms == DOSE
    assert b.forced_slots == (ForcedSlot(0, 0, AdherenceState.ON_TIME),)
    nominal = build_confounder_pair(v.group, g1("nominal", False, True), BASE)[1]
    assert nominal.c2_specs[0].magnitude == BOUNCE
    # content sensing and the robot follow the declared withheld set
    assert a.content_sensing is False and a.robot_present is True
    sensing = build_confounder_pair(v.group, g1("nominal", True, False), BASE)[0]
    assert sensing.content_sensing is True and sensing.robot_present is False
    # group 2
    v2 = g2("informed", True, False)
    a2, b2 = build_confounder_pair(v2.group, v2, BASE)
    assert [s.subtype for s in a2.c1_specs] == ["drug_nonresponse"]
    assert (
        a2.c1_specs[0].magnitude == 0.0 and a2.c1_specs[0].magnitude_unit == UNIT_SCALE
    )
    assert a2.forced_slots == (ForcedSlot(0, 0, AdherenceState.ON_TIME),)
    assert b2.forced_slots == (ForcedSlot(0, 0, AdherenceState.OMITTED),)
    assert [s.subtype for s in b2.c3_specs] == [
        "presence_spoof",
        "dispense_forgery",
    ] or sorted(s.subtype for s in b2.c3_specs) == [
        "dispense_forgery",
        "presence_spoof",
    ]
    spoof = next(s for s in b2.c3_specs if s.subtype == "presence_spoof")
    assert spoof.onset_ms == DOSE + LAG and spoof.params["spoof_intake"] is True
    assert {s.level for s in b2.c3_specs} == {"informed"}
    naive_b = build_confounder_pair(v2.group, g2("naive", True, True), BASE)[1]
    assert [s.subtype for s in naive_b.c3_specs] == ["dispense_forgery"]
    assert naive_b.authenticating_devices == ("dispenser",)
    assert b2.authenticating_devices == ()
    # group 3
    a3, b3 = build_confounder_pair(G3_REPORTED.group, G3_REPORTED, BASE)
    tick = SCHED_TWO.measurement_ticks_ms[0]
    assert (
        a3.c1_specs[0].subtype == "measurement_refusal"
        and a3.c1_specs[0].onset_ms == tick
    )
    assert (
        b3.c2_specs[0].subtype == "manipulation_failure"
        and b3.c2_specs[0].onset_ms == tick
    )
    assert not a3.forced_slots and not b3.forced_slots


def test_pair_builder_refuses_inconsistent_requests() -> None:
    v = g1("double_take_gap", True, True)
    with pytest.raises(ConfounderError):
        build_confounder_pair(
            GROUP_REFUSAL_VS_ROBOT_MISSED, v, BASE
        )  # the variant is of another group
    with pytest.raises(ConfounderError):
        build_confounder_pair("no_such_group", v, BASE)
    with pytest.raises(ConfounderError):
        build_confounder_pair(
            v.group, g1("nominal", True, True), pair_base(nominal_bounce_gap_ms=None)
        )
    with pytest.raises(ConfounderError):
        build_confounder_pair(v.group, v, pair_base(dose_index=2))
    with pytest.raises(ConfounderError):
        build_confounder_pair(
            G3_REPORTED.group, G3_REPORTED, pair_base(measurement_index=9)
        )
    with pytest.raises(
        ConfounderError
    ):  # a nominal gap that is not shorter than the double-take gap
        build_confounder_pair(
            v.group, g1("nominal", True, True), pair_base(nominal_bounce_gap_ms=GAP)
        )
    # the variant itself is validated
    for kwargs in (
        {"withheld": ("nothing",)},
        {
            "withheld": ("witness",)
        },  # the robot channel is withheld as a pair: witness and task outcome
        {"withheld": ("witness", "witness", "robot_task_outcome")},
        {"bounce_gap": "huge"},
        {"attacker": "informed"},  # an attacker has no place in group 1
    ):
        with pytest.raises(ConfounderError):
            variant(
                GROUP_DOUBLE_TAKE_VS_BOUNCE, "v", **{"bounce_gap": "nominal", **kwargs}
            )
    with pytest.raises(ConfounderError):
        variant(GROUP_NONRESPONSE_VS_FORGERY, "v", attacker=None)
    with pytest.raises(ConfounderError):
        variant(GROUP_NONRESPONSE_VS_FORGERY, "v", attacker="expert")
    with pytest.raises(ConfounderError):
        variant(GROUP_REFUSAL_VS_ROBOT_MISSED, "v", bounce_gap="nominal")
    with pytest.raises(ConfounderError):
        dataclasses.replace(v, source_type="invented")
    with pytest.raises(ConfounderError):
        dataclasses.replace(v, source_ref="   ")
    with pytest.raises(ConfounderError):
        dataclasses.replace(v, variant_id="")


def test_realised_scenario_never_leaks_latent_values_into_the_observed_day() -> None:
    ev = evaluated(g1("nominal", True, True))
    for member in (ev.a, ev.b):
        day = member.observed
        assert isinstance(day, ObservedDay)
        assert {f.name for f in dataclasses.fields(ObservedDay)} == {
            "patient_id", "day_index", "seed", "samples", "events", "care_plan_id",
        }  # fmt: skip
        validate_day(day)
        text = repr(day.samples) + repr(day.events)
        assert "latent" not in text and "baseline" not in text
        # the latent baseline never equals an observed value except by coincidence of 0 error
        latent_values = {
            s.value for s in member.latent.latent.samples if s.signal == "bp"
        }
        observed_bp = [s.value for s in day.samples if s.signal == "bp"]
        assert not latent_values & set(
            observed_bp
        )  # the cuff error is not zero in this fixture
        # a day written to disk contains no latent key
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = write_observed_day(Path(tmp), day)
            assert "latent" not in Path(path).read_text(encoding="utf-8").lower()
    assert isinstance(ev, PairEvaluation) and isinstance(ev.a, RealisedScenario)


def test_realise_scenario_matches_the_pipeline_written_by_hand() -> None:
    v = G3_REPORTED
    a, _ = build_confounder_pair(v.group, v, BASE)
    realised = realise_scenario(a, BASE)
    [res] = assemble_latent_days(
        BASE.patient, BASE.schedule, 1, list(a.c1_specs), BASE.response_model, BASE.library,
        BASE.seed, BASE.patient_index, config=BASE.config, forced_slots=a.forced_slots,
    )  # fmt: skip
    assert realised.latent == res
    base_stream = build_observed_base(
        res.latent, BASE.schedule, BASE.care_plan_id, BASE.device_errors, BASE.design,
        BASE.jitter, BASE.library, BASE.seed, BASE.patient_index,
        skip_measurement_ticks_ms=res.refused_ticks_ms,
    )  # fmt: skip
    expected = finalize_observed(
        apply_observation_injections(
            observe_refusals(base_stream, res.c1_records),
            [],
            InjectionContext(
                BASE.patient_index, library=BASE.library, latent=res.latent
            ),
        ).stream
    )
    assert realised.observed == expected


def test_pair_works_for_a_late_day_and_a_jittered_robot() -> None:
    class Late:
        descriptor = "test-double"
        run_source = None

        def delay_ms(self, rng: np.random.Generator, *, kind: str, index: int) -> int:
            return 2 * MIN if kind == vocab.KIND_DOSE else 0

    # the robot arrives two minutes late at the dose: the first intake (5 s after the dispense) is
    # before the arrival and not witnessed; the second release of a double take (2 min 5 s) is
    # covered, so only the double take has a witnessed INTAKE there
    base = pair_base(
        jitter=Late(), schedule=SCHED_ONE, config=make_config(adherence=PERFECT)
    )
    v = g1("double_take_gap", True, True)
    ev = evaluate_pair(v.group, v, base)
    intakes = lambda r: [e.t_device_ms for e in only(r.observed, EventKind.INTAKE)]
    assert intakes(ev.a) == [DOSE + GAP + LAG]
    assert intakes(ev.b) == []
    assert ev.separated_by == ("content_change", "witness")
    assert not ev.indistinguishable_by_construction


# ---------------------------------------------------------------------------
# The change to the measurement base (content sensing) and to the shared machinery
# ---------------------------------------------------------------------------


def test_measurement_base_emits_content_change_only_when_the_dispenser_senses_it() -> (
    None
):
    result = assemble(schedule=SCHED_TWO)[0]
    plain = observed_of(result, SCHED_TWO)
    sensing = observed_of(result, SCHED_TWO, dispenser_content_sensing=True)
    assert all(dict(e.payload) == {} for e in dispenses(finalize_observed(plain)))
    for e in dispenses(finalize_observed(sensing)):
        assert dict(e.payload) == {vocab.KEY_CONTENT_CHANGE: 1.0}
    assert sensing.settings["dispenser_content_sensing"] is True
    assert plain.settings["dispenser_content_sensing"] is False
    # nothing else changes
    assert [e for e in sensing.events if e.kind is not EventKind.DISPENSE] == [
        e for e in plain.events if e.kind is not EventKind.DISPENSE
    ]
    assert sensing.samples == plain.samples
    for bad in (None, 1, "yes", np.bool_(True), [True]):
        with pytest.raises(MeasurementConfigError):
            observed_of(result, SCHED_TWO, dispenser_content_sensing=bad)


def test_c1_design_loader_accepts_the_c1_families_and_the_other_sections_still_refuse_them(
    tmp_path: Path,
) -> None:
    filled = rewrite_rows(tmp_path, filled=True, name="f.yaml")
    assert set(load_injection_design(filled, section="c1")) == set(C1_SUBTYPES)
    document = yaml.safe_load(filled.read_text(encoding="utf-8"))
    # the families of C1 are not families of a C2 or C3 subtype, and the reverse
    document["injections"]["c2"]["stuck_at"]["family"] = "physiology"
    document["injections"]["c3"]["replay"]["family"] = "behaviour"
    document["injections"]["c1"]["double_take"]["family"] = "robot"
    for section in ("c2", "c3", "c1"):
        mutated = tmp_path / f"{section}.yaml"
        only_one = copy.deepcopy(document)
        # restore the other sections so that exactly one is wrong
        original = yaml.safe_load(filled.read_text(encoding="utf-8"))
        for other in ("c1", "c2", "c3"):
            if other != section:
                only_one["injections"][other] = original["injections"][other]
        mutated.write_text(yaml.safe_dump(only_one, sort_keys=False), encoding="utf-8")
        with pytest.raises(InjectionError):
            load_injection_design(mutated, section=section)


def test_the_loader_rejects_aliases_duplicates_and_numbers_in_the_new_sections(
    tmp_path: Path,
) -> None:
    text = INJECTIONS_FILE.read_text(encoding="utf-8")
    # a duplicate key
    dup = tmp_path / "dup.yaml"
    dup.write_text(
        text.replace("  c1:\n", "  c1:\n    double_take: {}\n    double_take: {}\n", 1),
        encoding="utf-8",
    )
    for loader in (load_c1_design, load_confounder_design):
        with pytest.raises(InjectionError):
            loader(dup)
    # a number inside the structured sections (numbers are rows of `parameters:`)
    document = yaml.safe_load(text)
    document["injections"]["c1"]["hypertensive_spike"]["onset"] = 5
    num = tmp_path / "num.yaml"
    num.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    with pytest.raises(InjectionError):
        load_c1_design(num)
    document = yaml.safe_load(text)
    next(
        iter(
            next(iter(document["confounders"]["groups"].values()))["variants"].values()
        )
    )["margin"] = 5
    num2 = tmp_path / "num2.yaml"
    num2.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    with pytest.raises(InjectionError):
        load_confounder_design(num2)
    # a YAML alias bomb is read in bounded time and refused or accepted, never a hang or a raw error
    bomb = "a: &a [x]\n" + "".join(
        f"{chr(98 + k)}: &{chr(98 + k)} [*{chr(97 + k)}, *{chr(97 + k)}]\n"
        for k in range(9)
    )
    path = tmp_path / "bomb.yaml"
    path.write_text(bomb, encoding="utf-8")
    for loader in (load_c1_design, load_confounder_design):
        with pytest.raises(InjectionError):
            loader(path)
    # not a path, a missing file, a directory, an oversized one
    for junk in (None, 5, b"x", "", str(tmp_path / "missing.yaml"), tmp_path):
        for loader in (load_c1_design, load_confounder_design):
            with pytest.raises(InjectionError):
                loader(junk)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Extremes of the pair builder
# ---------------------------------------------------------------------------


def test_extreme_inputs_pair_builder() -> None:
    v = g1("double_take_gap", True, True)
    fuzz(build_confounder_pair, {"group": v.group, "variant": v, "base_context": BASE})
    fuzz(
        PairBase,
        {f.name: getattr(BASE, f.name) for f in dataclasses.fields(PairBase)},
    )
    fuzz(
        Variant,
        {
            "group": v.group, "variant_id": "x", "withheld": (), "bounce_gap": "nominal",
            "attacker": None, "expected_indistinguishable": False, "source_type": "design_choice",
            "source_ref": "r", "rationale": "r",
        },
    )  # fmt: skip
    scenario_a, _ = build_confounder_pair(v.group, v, BASE)
    fuzz(realise_scenario, {"scenario": scenario_a, "base_context": BASE})
    fuzz(evaluate_pair, {"group": v.group, "variant": v, "base_context": BASE})
    ev = evaluated(v)
    day = ev.a.observed
    fuzz(
        compare_observed,
        {"a": day, "b": ev.b.observed, "visits": ev.a.stream.visits, "masked": ()},
    )
    fuzz(confounder_log, {"records": ev.a.records})
    with pytest.raises(ConfounderError):
        compare_observed(day, ev.b.observed, ev.a.stream.visits, ("nothing",))  # type: ignore[arg-type]
    with pytest.raises(ConfounderError):
        compare_observed(day, ev.b.observed, ev.a.stream.visits, (), ignore_pressure=1)  # type: ignore[arg-type]
    # the scenario itself is validated (review F5: it had no validation)
    good_fields = {
        f.name: getattr(scenario_a, f.name) for f in dataclasses.fields(Scenario)
    }
    fuzz(Scenario, good_fields)


def scenario_fields(scenario: Scenario) -> dict[str, Any]:
    return {f.name: getattr(scenario, f.name) for f in dataclasses.fields(Scenario)}


def test_scenario_is_validated_by_the_named_error() -> None:
    """Review F5: ``c1_specs=None`` raised a TypeError and an array flag a ValueError."""
    a, b = build_confounder_pair(G3_REPORTED.group, G3_REPORTED, BASE)
    fields = scenario_fields(a)
    assert Scenario(**fields) == a  # a valid scenario passes untouched
    cases: list[tuple[str, Any]] = []
    for name in ("content_sensing", "robot_present", "task_outcomes"):
        cases += [
            (name, bad)
            for bad in (
                None,
                1,
                "yes",
                np.bool_(True),
                np.array([1, 2]),
                np.array([]),
                TruthBomb(),
            )
        ]
    for name in (
        "c1_specs",
        "c2_specs",
        "c3_specs",
        "forced_slots",
        "authenticating_devices",
        "withheld",
    ):
        cases += [
            (name, bad)
            for bad in (
                None,
                5,
                "abc",
                b"ab",
                {1: 2},
                iter([1]),
                object(),
                np.array(1),
                IterBomb((1,)),
                ItemBomb([1]),
                [None],
                [5],
                (TruthBomb(),),
            )
        ]
    cases += [
        ("group", "no_such_group"),
        ("group", HashBomb("no_such_group")),
        ("group", EqBomb("no_such_group")),
        ("group", None),
        ("variant_id", ""),
        ("variant_id", None),
        ("variant_id", LenBomb(" ")),
        ("variant_id", 5),
        ("member", "C"),
        ("member", None),
        ("member", EqBomb("C")),
        ("member", "a"),
        ("mechanism", "bounce"),
        ("mechanism", None),
        ("mechanism", HashBomb("x")),
        ("mechanism_class", "C1"),
        ("mechanism_class", None),
        ("mechanism_class", InjectedClass.C3),
        (
            "c1_specs",
            (spike(HOUR, HOUR, 5.0),) + a.c1_specs,
        ),  # a spec of another group or class
        ("c2_specs", a.c1_specs),  # a C1 spec in the C2 slot
        ("c3_specs", a.c1_specs),
        ("c1_specs", b.c2_specs),
        ("forced_slots", ("slot",)),
        ("withheld", ("nothing",)),
        ("withheld", ("witness",) * 2),
        ("authenticating_devices", ("",)),
        ("authenticating_devices", (5,)),
    ]
    for name, bad in cases:
        with pytest.raises(ConfounderError):
            Scenario(**{**fields, name: bad})
        with pytest.raises(ConfounderError):
            dataclasses.replace(a, **{name: bad})
    # lists are accepted and stored as tuples
    listed = Scenario(
        **{**fields, "c1_specs": list(a.c1_specs), "withheld": list(a.withheld)}
    )
    assert isinstance(listed.c1_specs, tuple) and isinstance(listed.withheld, tuple)
    assert listed == a
    # the builder's scenarios of every variant of every grid pass their own validation
    for grid in (G1_GRID, G2_GRID, G3_GRID):
        for v in grid:
            for member in build_confounder_pair(v.group, v, BASE):
                assert Scenario(**scenario_fields(member)) == member


@pytest.mark.parametrize(
    "name", ["baseline", "amplitude", "sd", "phi", "emax", "ec50", "ka", "ke"]
)
@pytest.mark.parametrize("huge", [10**400, -(10**400)], ids=["positive", "negative"])
def test_a_patient_parameter_beyond_the_float_range_is_a_named_error(
    name: str, huge: int
) -> None:
    """Review F5: ``10**400`` in a float field raised a raw OverflowError from the assembly."""
    patient = make_patient(**{name: huge})
    # the foreign error is converted with its message (a field of the baseline and noise model), or
    # reported as the failure of the response model (a field of the drug response)
    message = (
        "the response model failed"
        if name in ("emax", "ec50", "ka", "ke")
        else "OverflowError: int too large to convert to float"
    )
    with pytest.raises(LatentAssemblyError, match=message):
        assemble(patient=patient)
    v = g1("double_take_gap", False, False)
    with pytest.raises(InjectionError) as caught:
        evaluate_pair(v.group, v, pair_base(patient=patient))
    assert named_error(caught.value)
    sa, _ = build_confounder_pair(v.group, v, pair_base(patient=patient))
    with pytest.raises(LatentAssemblyError):
        realise_scenario(sa, pair_base(patient=patient))


@pytest.mark.parametrize(
    "name, value",
    [("baseline", 130.0), ("amplitude", 0.0), ("sd", 0.0), ("phi", 0.0)],
)
def test_a_patient_float_that_misbehaves_is_a_named_error(
    name: str, value: float
) -> None:
    """A float subclass that raises from ``__float__`` is read inside the baseline model, which is not
    this module's code: the assembly reports it as its own failure (review F5)."""
    patient = make_patient(**{name: FloatBomb(value)})
    with pytest.raises(LatentAssemblyError, match="the assembly failed: RuntimeError"):
        assemble(patient=patient)


def test_pathological_strings_are_read_as_plain_strings_or_refused() -> None:
    """A ``str`` subclass whose hash, equality, truth value, length or repr raises is copied to a plain
    ``str`` before it is used (review F5): valid content gives the plain result, invalid content the
    named error, and the stored value is an exact ``str``."""
    for bomb in STR_BOMBS:
        spec = c1_spec(
            bomb("hypertensive_spike"),
            HOUR,
            duration_ms=HOUR,
            magnitude=5.0,
            level=bomb("high"),
            confounder_group=bomb("g"),
        )
        plain = c1_spec(
            "hypertensive_spike",
            HOUR,
            duration_ms=HOUR,
            magnitude=5.0,
            level="high",
            confounder_group="g",
        )
        assert spec == plain
        assert (
            type(spec.subtype) is str
            and type(spec.level) is str
            and type(spec.confounder_group) is str
        )
        with pytest.raises(C1InjectionError):
            c1_spec(bomb("no_such_subtype"), HOUR)
        with pytest.raises(C1InjectionError):
            c1_spec(
                bomb("hypertensive_spike"),
                HOUR,
                duration_ms=HOUR,
                magnitude=5.0,
                reference=bomb("no_such_reference"),
                multiple=1.0,
                reference_value=5.0,
            )
        with pytest.raises(C1InjectionError):
            resolve_c1_magnitude(level_row(2.0), 20.0, bomb("no_such_reference"))
        assert (
            resolve_c1_magnitude(level_row(2.0), 20.0, bomb(REFERENCE_SCALE_RANGE))
            == 40.0
        )
        with pytest.raises(ConfounderError):
            build_confounder_pair(
                bomb("no_such_group"), g1("nominal", True, True), BASE
            )
        v = g1("double_take_gap", False, True)
        built = Variant(
            group=bomb(v.group), variant_id=bomb(v.variant_id), withheld=(bomb("content_change"),),
            bounce_gap=bomb("double_take_gap"), attacker=None, expected_indistinguishable=False,
            source_type=bomb("design_choice"), source_ref=bomb("r"), rationale=bomb("r"),
        )  # fmt: skip
        assert (
            built.withheld == ("content_change",)
            and built.bounce_gap == "double_take_gap"
        )
        assert all(
            type(x) is str
            for x in (
                built.group,
                built.variant_id,
                built.withheld[0],
                built.bounce_gap,
                built.source_type,
                built.source_ref,
                built.rationale,
            )
        )
        for kwargs in (
            {"group": bomb("no_such_group")}, {"withheld": (bomb("nothing"),)}, {"bounce_gap": bomb("huge")},
            {"source_type": bomb("invented")}, {"variant_id": bomb("")},
        ):  # fmt: skip
            fields = {
                f.name: getattr(built, f.name) for f in dataclasses.fields(Variant)
            }
            with pytest.raises(ConfounderError):
                Variant(**{**fields, **kwargs})
        with pytest.raises(ConfounderError):
            Variant(
                **{
                    **{
                        f.name: getattr(built, f.name)
                        for f in dataclasses.fields(Variant)
                    },
                    "group": GROUP_NONRESPONSE_VS_FORGERY,
                    "bounce_gap": None,
                    "attacker": bomb("expert"),
                }
            )
        ev = evaluated(g1("double_take_gap", False, False))
        assert compare_observed(
            ev.a.observed, ev.b.observed, ev.a.stream.visits, [bomb("content_change")]
        ) == compare_observed(
            ev.a.observed, ev.b.observed, ev.a.stream.visits, ["content_change"]
        )
        with pytest.raises(ConfounderError):
            compare_observed(
                ev.a.observed, ev.b.observed, ev.a.stream.visits, [bomb("nothing")]
            )
        assert pair_base(care_plan_id=bomb("plan-1")).care_plan_id == "plan-1"
        assert type(pair_base(care_plan_id=bomb("plan-1")).care_plan_id) is str


def test_containers_that_misbehave_are_named_errors() -> None:
    ev = evaluated(g1("double_take_gap", False, False))
    day = ev.a.observed
    for bad in (IterBomb((1,)), ItemBomb([1]), MapBomb({"a": 1})):
        with pytest.raises(ConfounderError):
            compare_observed(day, ev.b.observed, bad, ())  # type: ignore[arg-type]
        with pytest.raises(ConfounderError):
            compare_observed(day, ev.b.observed, (), bad)  # type: ignore[arg-type]
        with pytest.raises(ConfounderError):
            confounder_log(bad)  # type: ignore[arg-type]
        with pytest.raises(ConfounderError):
            Variant(
                GROUP_DOUBLE_TAKE_VS_BOUNCE,
                "v",
                bad,
                "nominal",
                None,
                False,
                "design_choice",
                "r",
                "r",
            )  # type: ignore[arg-type]


def test_foreign_objects_with_unreadable_fields_are_named_errors() -> None:
    """The observed days, visits, streams and records come from other modules and are not validated
    there: a field that cannot be read is the named error of the module that reads it (review F5)."""
    ev = evaluated(g1("double_take_gap", False, False))
    day, other, visits = ev.a.observed, ev.b.observed, ev.a.stream.visits
    for name in ("samples", "events"):
        for junk in (
            None,
            5,
            [None],
            [5],
            TruthBomb(),
            IterBomb((1,)),
            ItemBomb([1]),
            np.array(1),
        ):
            broken = dataclasses.replace(day, **{name: junk})
            with pytest.raises(ConfounderError):
                compare_observed(broken, other, visits, ())
            with pytest.raises(ConfounderError):
                compare_observed(other, broken, visits, ())
    robot = evaluated(
        g2("naive", True, False)
    )  # a day with presence samples: the visits are read
    assert [s for s in robot.a.observed.samples if s.signal == "presence"]
    visit = robot.a.stream.visits[0]
    for name in ("arrival_ms", "departure_ms"):
        for junk in (
            None,
            "x",
            [1],
            np.array([1, 2]),
            TruthBomb(),
            CmpBomb(1.0),
            object(),
        ):
            broken_visit = dataclasses.replace(visit, **{name: junk})
            with pytest.raises(ConfounderError):
                compare_observed(robot.a.observed, robot.b.observed, [broken_visit], ())
    scenario, _ = build_confounder_pair(G3_REPORTED.group, G3_REPORTED, BASE)
    realised = realise_scenario(scenario, BASE)
    for name in ("events", "visits"):
        for junk in (
            None,
            5,
            [None],
            [5],
            TruthBomb(),
            IterBomb((1,)),
            ItemBomb([1]),
            np.array(1),
        ):
            broken_stream = dataclasses.replace(realised.stream, **{name: junk})
            with pytest.raises(C1InjectionError):
                observe_refusals(broken_stream, realised.records)
    # a level, a spec, a device error model and a patient whose fields cannot be read
    row = level_row(2.0)
    for name, junk in (
        ("unit", None), ("unit", CmpBomb(1.0)), ("value", [1]), ("value", 10**400), ("value", 1j),
        ("quantity_unit", np.array([1, 2])), ("quantity_unit", EqBomb(UNIT_MMHG)),
    ):  # fmt: skip
        broken_row = dataclasses.replace(row, **{name: junk})
        with pytest.raises(C1InjectionError):
            c1_spec_from_level(
                "hypertensive_spike", HOUR, broken_row, 20.0, duration_ms=HOUR
            )
        with pytest.raises(C1InjectionError):
            resolve_c1_magnitude(broken_row, 20.0, REFERENCE_SCALE_RANGE)
    plain_spec = spike(HOUR, HOUR, 5.0)
    for name, junk in (
        ("level", BoolBomb("high")), ("confounder_group", BoolBomb("g")),
        ("subtype", HashBomb("hypertensive_spike")), ("subtype", EqBomb("hypertensive_spike")),
    ):  # fmt: skip
        broken_spec = dataclasses.replace(plain_spec, **{name: junk})
        with pytest.raises(C1InjectionError):
            check_c1_specs([broken_spec])
        with pytest.raises(C1InjectionError):
            c1_stream(SEED, 0, 0, broken_spec)
    quiet = g1("double_take_gap", False, False)
    for name in ("cuff_bias_mmhg", "cuff_error_sd_mmhg"):
        errors = dataclasses.replace(NOISY_ERRORS, **{name: FloatBomb(1.0)})
        with pytest.raises(ConfounderError):
            evaluate_pair(quiet.group, quiet, pair_base(device_errors=errors))
    for bomb in (LenBomb, EqBomb):
        with pytest.raises(ConfounderError):
            evaluate_pair(
                quiet.group,
                quiet,
                pair_base(patient=make_patient(patient_id=bomb("p0003"))),
            )
    # a design file given as a path that misbehaves
    for bomb in (*STR_BOMBS, TruthBomb, IterBomb):
        path = bomb("no/such/file.yaml") if bomb in STR_BOMBS else bomb()
        for loader in (load_confounder_design, load_c1_design):
            with pytest.raises(InjectionError) as caught:
                loader(path)  # type: ignore[arg-type]
            assert named_error(caught.value)

    class PathBomb(os.PathLike):  # type: ignore[type-arg]
        def __fspath__(self) -> str:
            raise RuntimeError("fspath")

    for loader in (load_confounder_design, load_c1_design):
        with pytest.raises(InjectionError) as caught:
            loader(PathBomb())  # type: ignore[arg-type]
        assert named_error(caught.value)
    # a path that is a misbehaving str with a valid content is read as the plain path
    for bomb in STR_BOMBS:
        assert load_confounder_design(
            bomb(str(INJECTIONS_FILE))
        ) == load_confounder_design(INJECTIONS_FILE)
        assert load_c1_design(bomb(str(INJECTIONS_FILE))) == load_c1_design(
            INJECTIONS_FILE
        )

    # a record that was valid when it was built and cannot be read any more
    class Unreadable(Mapping):  # type: ignore[type-arg]
        def __getitem__(self, key: Any) -> Any:
            raise RuntimeError("getitem")

        def __iter__(self) -> Any:
            return iter(("a",))

        def __len__(self) -> int:
            return 1

    broken_record = dataclasses.replace(ev.a.records[0])
    object.__setattr__(broken_record, "details", Unreadable())
    with pytest.raises(ConfounderError):
        confounder_log([broken_record])


# ---------------------------------------------------------------------------
# Layering, exports and the literal guard
# ---------------------------------------------------------------------------

NEW_MODULES = ("inject_c1", "latent_day", "confounders")
ALLOWED_IMPORTS: dict[str, set[str]] = {
    "inject_c1": {
        "ralmon.benchmark",
        "ralmon.benchmark.injection", "ralmon.benchmark.latent", "ralmon.benchmark.measurement",
        "ralmon.benchmark.rng", "ralmon.benchmark.trace", "ralmon.benchmark.vocab",
        "ralmon.signals",
    },
    "latent_day": {
        "ralmon.benchmark",
        "ralmon.benchmark.adherence", "ralmon.benchmark.inject_c1", "ralmon.benchmark.injection",
        "ralmon.benchmark.latent", "ralmon.benchmark.measurement", "ralmon.benchmark.pkpd",
        "ralmon.benchmark.priors", "ralmon.benchmark.rng", "ralmon.benchmark.schedule",
        "ralmon.benchmark.segments", "ralmon.benchmark.trace", "ralmon.benchmark.vocab",
        "ralmon.signals",
    },
    "confounders": {
        "ralmon.benchmark",
        "ralmon.benchmark.adherence", "ralmon.benchmark.inject_c1", "ralmon.benchmark.inject_c2",
        "ralmon.benchmark.inject_c3", "ralmon.benchmark.injection", "ralmon.benchmark.latent",
        "ralmon.benchmark.latent_day", "ralmon.benchmark.measurement", "ralmon.benchmark.pkpd",
        "ralmon.benchmark.priors", "ralmon.benchmark.rng", "ralmon.benchmark.schedule",
        "ralmon.benchmark.segments", "ralmon.benchmark.trace", "ralmon.benchmark.vocab",
        "ralmon.signals",
    },
}  # fmt: skip


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


@pytest.mark.parametrize("name", NEW_MODULES)
def test_new_modules_stay_below_monitor_and_spec(name: str) -> None:
    imports = {i for i in _imports(SRC / f"{name}.py") if i.startswith("ralmon")}
    for forbidden in (
        "spec",
        "monitor",
        "conformal",
        "attribution",
        "baselines",
        "eval",
    ):
        assert not [i for i in imports if i.split(".")[1:2] == [forbidden]], (
            name,
            forbidden,
        )
    assert not imports - ALLOWED_IMPORTS[name] - {f"ralmon.benchmark.{name}"}, (
        imports - ALLOWED_IMPORTS[name]
    )
    # no wall clock, no global random state, no network, no subprocess
    source = (SRC / f"{name}.py").read_text(encoding="utf-8")
    for token in (
        "import time",
        "datetime",
        "import random",
        "np.random.seed",
        "np.random.normal",
        "socket",
        "subprocess",
        "urllib",
    ):
        assert token not in source, (name, token)
    assert not re.search(r"default_rng\(\s*\)", source)


def test_no_new_name_is_exported_from_the_package_root() -> None:
    exported = set(benchmark_pkg.__all__)
    for module in (c1_mod, latent_day_mod, confounders_mod):
        for public in module.__all__:
            assert public not in exported, public
    table = (ROOT / "docs/plan/02-interfaces.md").read_text(encoding="utf-8")
    row = next(
        line for line in table.splitlines() if line.startswith("| `ralmon.benchmark`")
    )
    listed = set(re.findall(r"`([A-Za-z_]+)`", row))
    assert exported <= listed | {"ralmon.benchmark"}


def test_new_modules_have_all_and_no_unannotated_numeric_parameters() -> None:
    from .test_priorsource import parameter_literals

    for name in NEW_MODULES:
        path = SRC / f"{name}.py"
        assert parameter_literals(path.read_text(encoding="utf-8")) == [], name
        module = {
            "inject_c1": c1_mod,
            "latent_day": latent_day_mod,
            "confounders": confounders_mod,
        }[name]
        # constants, then classes, then functions, each group sorted (the style of the other modules)
        order = lambda n: (0 if n.isupper() else 1 if n[0].isupper() else 2, n)
        assert sorted(module.__all__, key=order) == list(module.__all__), name
        for public in module.__all__:
            assert hasattr(module, public), (name, public)
    # no clinical value of the registry appears in the new modules
    registry = yaml.safe_load(REGISTRY_FILE.read_text(encoding="utf-8"))
    clinical = {
        float(e["value"])
        for e in registry["entries"]
        if abs(float(e["value"])) > 3.0
        # monitor configuration, not a clinical parameter (registry note)
        and e["name"] != "clock_skew_max_ms"
    }
    for name in NEW_MODULES:
        tree = ast.parse((SRC / f"{name}.py").read_text(encoding="utf-8"))
        values = {
            float(n.value)
            for n in ast.walk(tree)
            if isinstance(n, ast.Constant)
            and isinstance(n.value, (int, float))
            and not isinstance(n.value, bool)
        }
        assert not values & clinical, (name, values & clinical)


def test_bound_constants_are_documented_values() -> None:
    assert c1_mod.MAX_C1_SPECS == 10_000
    assert MAX_DAYS == 366
    assert latent_day_mod.MAX_TOTAL_EVALUATIONS == 20_000_000
    assert latent_day_mod.MAX_FORCED_SLOTS == 10_000
    assert confounders_mod.MAX_VARIANTS == 1_000


def test_module_help_text_names_the_conventions() -> None:
    doc = (
        (c1_mod.__doc__ or "")
        + (latent_day_mod.__doc__ or "")
        + (confounders_mod.__doc__ or "")
    )
    for needle in (
        "[onset, onset + duration)",
        "ground",
        "paired",
        "midnight",
        "R3-W4",
    ):
        assert needle in doc, needle
    fault_model = FAULT_MODEL.read_text(encoding="utf-8")
    assert "half" in fault_model.lower()  # the window convention the docstring cites


def test_c1_subtypes_are_the_workstream_vocabulary() -> None:
    readme = (ROOT / "docs/plan/workstreams/WS04-benchmark/README.md").read_text(
        encoding="utf-8"
    )
    for subtype in C1_SUBTYPES:
        assert subtype in readme, subtype
    assert C1_SUBTYPES[:4] == (
        "hypertensive_spike", "drug_nonresponse", "hypotension_below_hold", "measurement_refusal",
    )  # fmt: skip


def test_command_line_checks_still_pass() -> None:
    done = subprocess.run(
        [sys.executable, "-m", "ralmon.benchmark.priors", "--check-table"],
        cwd=ROOT, capture_output=True, text=True, timeout=120, check=False,
    )  # fmt: skip
    assert done.returncode == 0, done.stderr
    names = (SRC / "confounders.py").read_text(encoding="utf-8")
    assert sum(names.count(g) for g in GROUPS) >= 3
    assert math.isfinite(1.0)


# ---------------------------------------------------------------------------
# More behaviour of the injectors, the working copy and the records
# ---------------------------------------------------------------------------


def work_for(day: int = 0, *, step: int = HOUR) -> LatentWork:
    work = LatentWork(
        day,
        np.arange(0, DAY, step, dtype=np.int64) + day * DAY,
        dose_ticks_ms=SCHED_TWO.dose_ticks_ms,
        measurement_ticks_ms=SCHED_TWO.measurement_ticks_ms,
        double_take_gap_ms=GAP,
    )
    return work


def test_latent_work_validates_its_grid_and_ticks() -> None:
    grid = np.arange(0, DAY, HOUR, dtype=np.int64)
    good: dict[str, Any] = {
        "dose_ticks_ms": (DOSE,),
        "measurement_ticks_ms": (HOUR,),
        "double_take_gap_ms": GAP,
    }
    bad_grids: list[Any] = [
        np.array([], dtype=np.int64),
        np.array([1.0, 2.0]),  # floats
        np.array([5, 3], dtype=np.int64),  # not increasing
        np.array([3, 3], dtype=np.int64),
        np.array([DAY], dtype=np.int64),  # a point after the day
        np.array([-1, 0], dtype=np.int64),
        np.arange(10**6 + 5, dtype=np.int64),  # more points than a call may build
        np.zeros((2, 2), dtype=np.int64),
        np.array([1, 2], dtype=np.uint64),
        [0, 1, 2],
    ]
    for bad in bad_grids:
        with pytest.raises(C1InjectionError):
            LatentWork(0, bad, **good)
    for bad_ticks in ((HOUR, HOUR), (2 * HOUR, HOUR), (DAY,), (-1,), ("x",)):
        with pytest.raises(C1InjectionError):
            LatentWork(0, grid, **{**good, "measurement_ticks_ms": bad_ticks})
        with pytest.raises(C1InjectionError):
            LatentWork(0, grid, **{**good, "dose_ticks_ms": bad_ticks})
    with pytest.raises(C1InjectionError):
        LatentWork(1, grid, **good)  # day 1 needs a grid inside day 1
    for bad_gap in (
        0,
        -1,
        DAY + 1,
        10**400,
        1.5,
        True,
        None,
        "2",
    ):  # review F6 (E24): both bounds
        with pytest.raises(C1InjectionError):
            LatentWork(0, grid, **{**good, "double_take_gap_ms": bad_gap})
    for edge_gap in (1, DAY):
        assert (
            LatentWork(
                0, grid, **{**good, "double_take_gap_ms": edge_gap}
            ).double_take_gap_ms
            == edge_gap
        )
    work = LatentWork(0, grid, **good)
    assert work.has_pulses is False and not work.pulse_mmhg.any()
    assert work.dose_ticks_ms == (DOSE,) and work.day_end_ms == DAY
    work.set_intakes([DOSE + LAG, 10])
    assert work.intake_scales == [1.0, 1.0]
    assert LatentWork(2, grid + 2 * DAY, **good).measurement_ticks_ms == (
        2 * DAY + HOUR,
    )
    with pytest.raises(C1InjectionError):
        work.set_intakes([-1])
    with pytest.raises(C1InjectionError):
        work.set_intakes([0] * (c1_mod.MAX_WORK_INTAKES + 1))


def test_injector_records_state_what_changed_for_every_subtype() -> None:
    work = work_for()
    work.set_intakes((DOSE + LAG, 20 * HOUR + LAG))
    [spike_rec] = hypertensive_spike(work, [spike(2 * HOUR, 3 * HOUR, 7.5)])
    assert (spike_rec.n_changed, spike_rec.realised) == (3, True)
    assert (spike_rec.realised_onset_ms, spike_rec.realised_end_ms) == (
        2 * HOUR,
        5 * HOUR,
    )
    assert (
        spike_rec.details["n_grid_points"] == 3
        and spike_rec.details["magnitude"] == 7.5
    )
    assert work.has_pulses and work.pulse_mmhg[2:5].tolist() == [7.5, 7.5, 7.5]
    assert work.pulse_mmhg[:2].tolist() == [0.0, 0.0] and work.pulse_mmhg[5] == 0.0
    [hypo_rec] = hypotension_below_hold(work, [hypo(4 * HOUR, 2 * HOUR, 2.5)])
    assert hypo_rec.n_changed == 2 and work.pulse_mmhg[4:6].tolist() == [5.0, -2.5]
    # a window with no grid point: unrealised, nothing changes
    off = work_for()
    [none_rec] = hypertensive_spike(off, [spike(HOUR + 1, HOUR - 2, 7.5)])
    assert (none_rec.n_changed, none_rec.realised) == (0, False) and not off.has_pulses
    # the non-response; the intakes may be given in any order (the history is not sorted by time)
    unsorted = work_for()
    unsorted.set_intakes((20 * HOUR + LAG, DOSE + LAG, 12 * HOUR))
    [other] = drug_nonresponse(unsorted, [nonresponse(DOSE, HOUR, 0.5)])
    assert other.n_changed == 1 and unsorted.intake_scales == [1.0, 0.5, 1.0]
    assert other.details["intake_times_ms"] == [DOSE + LAG]
    [nr] = drug_nonresponse(work, [nonresponse(DOSE, HOUR, 0.25)])
    assert nr.n_changed == 1 and nr.details["n_intakes_in_window"] == 1
    assert nr.details["intake_times_ms"] == [DOSE + LAG] and nr.details["scale"] == 0.25
    assert work.intake_scales == [0.25, 1.0]
    [again] = drug_nonresponse(work, [nonresponse(DOSE, HOUR, 0.25)])
    assert again.n_changed == 0 and again.realised is False  # the scale is already that
    assert work.intake_scales == [0.25, 1.0]
    # a refusal of a tick and of an instant that is no tick
    tick = SCHED_TWO.measurement_ticks_ms[1]
    [ref_ok, ref_bad] = measurement_refusal(work, [refusal(tick), refusal(tick + 1)])
    assert (ref_ok.n_changed, ref_ok.realised_onset_ms, ref_ok.realised_end_ms) == (
        1,
        tick,
        None,
    )
    assert ref_bad.n_changed == 0 and "reason" in ref_bad.details
    assert work.refused_ticks_ms == {tick} and work.refused_clock_ticks_ms() == (tick,)
    # a double take on a dose tick and on an instant that is no dose tick
    [dt_ok, dt_bad] = double_take(
        work, [double_take_spec(DOSE), double_take_spec(DOSE + 1)]
    )
    assert (dt_ok.n_changed, dt_ok.realised_onset_ms) == (4, DOSE + GAP)
    assert dt_ok.details["gap_ms"] == GAP and dt_ok.details["forced"] is True
    assert dt_bad.n_changed == 0 and "reason" in dt_bad.details
    assert work.double_take_ticks_ms == {DOSE}
    for record in (spike_rec, hypo_rec, nr, ref_ok, dt_ok):
        json.dumps(injection_log([record]), allow_nan=False)  # a JSON-native sidecar


def test_work_on_a_later_day_uses_the_continuing_axis() -> None:
    work = work_for(day=3)
    tick = 3 * DAY + SCHED_TWO.measurement_ticks_ms[0]
    [rec] = measurement_refusal(work, [refusal(tick)])
    assert rec.realised and work.refused_clock_ticks_ms() == (
        SCHED_TWO.measurement_ticks_ms[0],
    )
    [rec2] = hypertensive_spike(work, [spike(3 * DAY + 2 * HOUR, HOUR, 4.0)])
    assert rec2.n_changed == 1 and work.pulse_mmhg[2] == 4.0
    [rec3] = hypertensive_spike(
        work, [spike(2 * DAY + 2 * HOUR, HOUR, 4.0)]
    )  # another day
    assert rec3.n_changed == 0


def test_c1_spec_bookkeeping_of_the_reference() -> None:
    ok = c1_spec(
        "hypertensive_spike", HOUR, duration_ms=HOUR, magnitude=40.0,
        reference=REFERENCE_SCALE_RANGE, multiple=2.0, reference_value=20.0,
    )  # fmt: skip
    assert dict(ok.params) == {
        "multiple": 2.0,
        "reference": "scale_range",
        "reference_value": 20.0,
    }
    bad = [
        {"reference": REFERENCE_SCALE_RANGE},  # all three or none
        {"multiple": 2.0, "reference_value": 20.0},
        {
            "reference": REFERENCE_SCALE_RANGE,
            "multiple": 2.0,
            "reference_value": 21.0,
        },  # 40 != 2 * 21
        {
            "reference": REFERENCE_HOLD_DISTANCE,
            "multiple": 2.0,
            "reference_value": 20.0,
        },  # wrong name
        {"reference": REFERENCE_SCALE_RANGE, "multiple": 0.0, "reference_value": 20.0},
        {"reference": REFERENCE_SCALE_RANGE, "multiple": 2.0, "reference_value": -20.0},
        {"reference": 5, "multiple": 2.0, "reference_value": 20.0},
    ]
    for extra in bad:
        with pytest.raises(C1InjectionError):
            c1_spec(
                "hypertensive_spike", HOUR, duration_ms=HOUR, magnitude=40.0, **extra
            )
    with pytest.raises(C1InjectionError):  # a non-response takes no reference params
        c1_spec(
            "drug_nonresponse", HOUR, duration_ms=HOUR, magnitude=0.5,
            reference=REFERENCE_SCALE_RANGE, multiple=2.0, reference_value=0.25,
        )  # fmt: skip
    with pytest.raises(C1InjectionError):
        c1_spec("nothing", HOUR)
    with pytest.raises(C1InjectionError):
        c1_spec_from_level(
            "measurement_refusal", HOUR, level_row(1.0), 20.0
        )  # no magnitude
    with pytest.raises(
        C1InjectionError
    ):  # a pressure level for the Emax scale: wrong quantity
        c1_spec_from_level(
            "drug_nonresponse", HOUR, level_row(1.0), 20.0, duration_ms=HOUR
        )
    with pytest.raises(C1InjectionError):  # a dimensionless scale is no pressure
        c1_spec_from_level(
            "hypertensive_spike", HOUR,
            level_row(0.5, UNIT_SCALE, quantity_unit=UNIT_SCALE), None, duration_ms=HOUR,
        )  # fmt: skip
    with pytest.raises(C1InjectionError):  # an unfilled level
        c1_spec_from_level(
            "hypertensive_spike", HOUR, level_row(None), 20.0, duration_ms=HOUR
        )
    with pytest.raises(C1InjectionError):  # a relative level needs its reference value
        c1_spec_from_level(
            "hypertensive_spike", HOUR, level_row(2.0), None, duration_ms=HOUR
        )
    with pytest.raises(C1InjectionError):
        c1_spec_from_level(
            "hypertensive_spike", HOUR, level_row(2.0), -5.0, duration_ms=HOUR
        )


def test_observe_refusals_adds_only_declined_events_in_stable_order() -> None:
    first, second = SCHED_TWO.measurement_ticks_ms[:2]
    out = assemble([refusal(first), refusal(second)], schedule=SCHED_TWO)[0]
    base = observed_of(out, SCHED_TWO)
    observed = observe_refusals(base, out.c1_records)
    added = [e for e in observed.events if e not in base.events]
    assert [(e.t_device_ms, e.payload["outcome"]) for e in added] == [
        (first, "declined"), (second, "declined"),
    ]  # fmt: skip
    assert observed.samples == base.samples and observed.visits == base.visits
    assert observed.measurements == base.measurements  # nothing generator-side changes
    # sorted by arrival, and each declined event follows the navigation event of its instant
    assert [e.t_rx_ms for e in observed.events] == sorted(
        e.t_rx_ms for e in observed.events
    )
    at = [
        e
        for e in observed.events
        if e.kind is EventKind.ROBOT_TASK and e.t_device_ms == first
    ]
    assert [e.payload["task"] for e in at] == ["navigate", "manipulate"]
    # an unrealised refusal and a record of another subtype add nothing
    unrealised = measurement_refusal(work_for(), [refusal(first + 1)])
    assert observe_refusals(base, unrealised + out.c1_records[:0]) == base
    sp = assemble([spike(HOUR, HOUR, 1.0)], schedule=SCHED_TWO)[0].c1_records
    assert observe_refusals(base, sp) == base
    # the input stream is never changed
    assert base == observed_of(out, SCHED_TWO)


def test_truth_file_round_trip_of_the_sidecars(tmp_path: Path) -> None:
    from ralmon.benchmark.trace import read_truth, write_truth

    out = assemble(
        [
            spike(HOUR, HOUR, 5.0),
            refusal(SCHED_TWO.measurement_ticks_ms[0]),
            double_take_spec(DOSE),
        ],
        schedule=SCHED_TWO,
        config=make_config(adherence=NATURAL),
    )[0]
    log = injection_log(out.c1_records)
    behaviour = [e.to_json() for e in out.behaviour_log]
    write_truth(tmp_path, out.latent, [], log, behaviour)
    back = read_truth(tmp_path, out.latent.patient_id, out.latent.day_index)
    assert [(e.kind, e.t_device_ms, e.source) for e in back.latent.events] == [
        (e.kind, e.t_device_ms, e.source) for e in out.latent.events
    ]
    assert [s.value for s in back.latent.samples] == [
        s.value for s in out.latent.samples
    ]
    assert back.injection_log == log and back.behaviour_log == behaviour
    assert list(back.ground_truth) == []  # a C1 record is not ground truth


def test_a_week_is_assembled_with_bounded_memory() -> None:
    import tracemalloc

    config = make_config(adherence=NATURAL)
    specs = [spike(k * DAY + 2 * HOUR, HOUR, 5.0) for k in range(7)]
    tracemalloc.start()
    try:
        week = assemble(
            specs, patient=NOISY_PATIENT, schedule=SCHED_TWO, n_days=7, config=config
        )
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert [r.latent.day_index for r in week] == list(range(7))
    assert all(len(r.c1_records) == 1 and r.c1_records[0].realised for r in week)
    assert peak < 120 * 1024 * 1024
    assert len(week[-1].end_state.intake_times_ms) == len(
        [t for r in week for t in times_of(r, EventKind.INTAKE)]
    )


def test_config_and_slot_validation_details() -> None:
    cfg = make_config()
    for step in (0, -1, 7 * SEC + 1, DAY + 1, 10**400, 1.5, True, None):
        with pytest.raises(LatentAssemblyError):
            AssemblyConfig(step, PEAK_CLOCK, STEP, PERFECT, DESIGN)  # type: ignore[arg-type]
    with pytest.raises(LatentAssemblyError):  # more points a day than a call may build
        AssemblyConfig(1, PEAK_CLOCK, 1, PERFECT, DESIGN)
    for peak in (-1, DAY, 10**400):
        with pytest.raises(LatentAssemblyError):
            dataclasses.replace(cfg, circadian_peak_clock_ms=peak)
    with pytest.raises(LatentAssemblyError):
        dataclasses.replace(cfg, adherence="model")  # type: ignore[arg-type]
    with pytest.raises(LatentAssemblyError):
        dataclasses.replace(cfg, vitals=None)  # type: ignore[arg-type]
    with pytest.raises(LatentAssemblyError):
        dataclasses.replace(cfg, allow_no_segments=1)  # type: ignore[arg-type]
    for state in (AdherenceState.DELAYED, AdherenceState.DOUBLE_TAKE, 0, None):
        with pytest.raises(LatentAssemblyError):
            ForcedSlot(0, 0, state)  # type: ignore[arg-type]
    for bad in (-1, 10**400, 1.0, True):
        with pytest.raises(LatentAssemblyError):
            ForcedSlot(bad, 0, AdherenceState.OMITTED)  # type: ignore[arg-type]
        with pytest.raises(LatentAssemblyError):
            ForcedSlot(0, bad, AdherenceState.OMITTED)  # type: ignore[arg-type]
    for args in (
        (-1, 0.0, None, ()), (1, float("nan"), None, ()), (1, 0.0, 3, ()),
        (1, 0.0, None, (-1,)), (1, 0.0, None, "abc"), (1, 0.0, None, (1.5,)),
    ):  # fmt: skip
        with pytest.raises(LatentAssemblyError):
            AssemblyState(*args)  # type: ignore[arg-type]
    # the day grid: a step that divides the day with the fewest points
    assert AssemblyConfig(DAY, PEAK_CLOCK, DAY, PERFECT, DESIGN).latent_step_ms == DAY


def test_a_misbehaving_library_or_model_is_a_named_error() -> None:
    class NaNModel:
        def effect_mmhg(
            self, params: Any, intakes: Any, grid: Any, intake_scales: Any = None
        ) -> Any:
            return [float("nan")] * len(grid)

    class Negative:
        def effect_mmhg(
            self, params: Any, intakes: Any, grid: Any, intake_scales: Any = None
        ) -> Any:
            return [-1.0] * len(grid)

    for model in (NaNModel(), Negative()):
        with pytest.raises(LatentAssemblyError):
            assemble_latent_days(
                FIX_PATIENT,
                SCHED_ONE,
                1,
                [],
                model,
                LIB,
                SEED,
                0,
                config=make_config(step=HOUR),  # type: ignore[arg-type]
            )
    # a patient with an impossible parameter: the named error, not a raw one
    for patient in (
        make_patient(baseline=-1.0), make_patient(baseline=float("nan")),
        make_patient(emax=-1.0), make_patient(ka=0.0), make_patient(sd=-1.0),
        make_patient(phi=1.0), make_patient(ec50=0.0),
    ):  # fmt: skip
        with pytest.raises(LatentAssemblyError):
            assemble(patient=patient)
    # a double-take gap that does not fit the shortest slot
    tight = Schedule(dose_ticks_ms=(8 * HOUR, 8 * HOUR + MIN), measurement_ticks_ms=())
    with pytest.raises(LatentAssemblyError):
        assemble(schedule=tight)
    # the largest representable baseline stays finite with the largest admissible pulse
    huge = assemble([spike(HOUR, HOUR, 1e12)], patient=make_patient(baseline=1.7e308))[
        0
    ]
    assert all(math.isfinite(v) for v in bp_series(huge).values())


def test_evaluate_pair_refuses_members_with_different_bases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    v = g1("double_take_gap", False, False)
    real = confounders_mod.realise_scenario
    calls: list[RealisedScenario] = []

    def other_visits(scenario: Scenario, base: PairBase) -> RealisedScenario:
        out = real(scenario, base)
        if calls:
            out = dataclasses.replace(
                out, stream=dataclasses.replace(out.stream, visits=())
            )
        calls.append(out)
        return out

    monkeypatch.setattr(confounders_mod, "realise_scenario", other_visits)
    with pytest.raises(ConfounderError):
        evaluate_pair(v.group, v, BASE)


def test_pair_base_validation() -> None:
    bad: dict[str, Any] = {
        "patient": "p", "schedule": None, "config": None, "response_model": object(),
        "device_errors": None, "design": None, "jitter": object(), "library": None,
        "care_plan_id": "", "seed": -1, "patient_index": 2**32, "dose_index": -1,
        "measurement_index": 1.5, "nominal_bounce_gap_ms": 0, "task_deadline_offset_ms": -5,
    }  # fmt: skip
    for key, value in bad.items():
        with pytest.raises(ConfounderError):
            pair_base(**{key: value})

    class NoDescriptor:
        def delay_ms(self, rng: Any, *, kind: str, index: int) -> int:
            return 0

    with pytest.raises(ConfounderError):
        pair_base(jitter=NoDescriptor())
    assert pair_base(nominal_bounce_gap_ms=None).nominal_bounce_gap_ms is None


def test_scenarios_never_carry_the_other_members_specs() -> None:
    for grid in (G1_GRID, G2_GRID, G3_GRID):
        for v in grid:
            a, b = build_confounder_pair(v.group, v, BASE)
            assert {s.cls for s in a.c1_specs} == {C1} and not (
                a.c2_specs or a.c3_specs
            )
            assert not b.c1_specs
            assert {s.cls for s in b.c2_specs + b.c3_specs} <= {C2, C3} and (
                b.c2_specs or b.c3_specs
            )
            specs = a.c1_specs + a.c2_specs + a.c3_specs + b.c2_specs + b.c3_specs
            assert all(s.confounder_group == v.group for s in specs)
            assert a.withheld == b.withheld == v.withheld
            assert a.content_sensing == b.content_sensing == v.content_sensing
            assert a.robot_present == b.robot_present == v.robot_present
            assert a.task_outcomes == b.task_outcomes == v.task_outcomes


def test_content_sensing_is_a_knob_of_the_double_take_pair_only() -> None:
    for v in G2_GRID + G3_GRID:
        assert variant_content(v) is False
    assert g1("nominal", True, True).content_sensing is True
    assert g1("nominal", False, True).content_sensing is False
    assert g2("naive", True, True).authenticating is True
    assert g2("naive", True, False).authenticating is False
    assert g1("nominal", True, True).authenticating is False


def variant_content(v: Variant) -> bool:
    return v.content_sensing


# ---------------------------------------------------------------------------
# Mutated design files: every structural rule of the loaders is a named error
# ---------------------------------------------------------------------------


def mutated(
    tmp_path: Path, name: str, mutate: Callable[[dict[str, Any]], None]
) -> Path:
    """A slim copy of the design file (only the sections and rows of this task) with a mutation."""
    document = committed_document()
    document["injections"] = {"c1": document["injections"]["c1"]}
    document.pop("attacker", None)
    document["parameters"] = [
        r for r in document["parameters"] if r["consumer_task"] == "WS04-T09"
    ]
    mutate(document)
    path = tmp_path / name
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def first_variant(
    document: dict[str, Any], group: str = GROUP_DOUBLE_TAKE_VS_BOUNCE
) -> dict[str, Any]:
    variants = document["confounders"]["groups"][group]["variants"]
    return variants[next(iter(variants))]


def test_c1_design_rules_are_named_errors(tmp_path: Path) -> None:
    c1 = lambda d: d["injections"]["c1"]
    cases: dict[str, Callable[[dict[str, Any]], None]] = {
        "missing_subtype": lambda d: c1(d).pop("double_take"),
        "extra_subtype": lambda d: c1(d).update({"invented": c1(d)["double_take"]}),
        "bad_family": lambda d: c1(d)["double_take"].update({"family": "device"}),
        "no_target": lambda d: c1(d)["double_take"].update({"target": []}),
        "refusal_with_duration": lambda d: c1(d)["measurement_refusal"].update(
            {"duration": c1(d)["hypertensive_spike"]["duration"]}
        ),
        "spike_without_duration": lambda d: c1(d)["hypertensive_spike"].update(
            {"duration": None}
        ),
        "spike_without_magnitude": lambda d: c1(d)["hypertensive_spike"].update(
            {"magnitude": None}
        ),
        "wrong_unit": lambda d: c1(d)["hypertensive_spike"]["magnitude"].update(
            {"unit": "1"}
        ),
        "wrong_reference": lambda d: c1(d)["hypertensive_spike"]["magnitude"].update(
            {"reference": "baseline_to_hold_distance"}
        ),
        "hypotension_wrong_reference": lambda d: c1(d)["hypotension_below_hold"][
            "magnitude"
        ].update({"reference": "scale_range"}),
        "scale_with_reference": lambda d: c1(d)["drug_nonresponse"]["magnitude"].update(
            {"reference": "scale_range"}
        ),
        "duration_not_ms": lambda d: c1(d)["hypertensive_spike"]["duration"].update(
            {"unit": "mmHg"}
        ),
        "unknown_row": lambda d: c1(d)["hypertensive_spike"]["magnitude"][
            "levels"
        ].update({"below": "no_such_row"}),
        "two_levels": lambda d: c1(d)["drug_nonresponse"]["magnitude"].update(
            {
                "levels": dict(
                    list(c1(d)["drug_nonresponse"]["magnitude"]["levels"].items())[:2]
                )
            }
        ),
        "row_without_provenance": lambda d: [
            r.update({"source_ref": None})
            for r in d["parameters"]
            if r["parameter"] == "hypertensive_spike_magnitude_below"
        ],
        "duration_row_in_wrong_unit": lambda d: [
            r.update({"unit": "mmHg"})
            for r in d["parameters"]
            if r["parameter"] == "hypertensive_spike_duration_short"
        ],
        "scale_row_in_wrong_unit": lambda d: [
            r.update({"unit": "x scale_range"})
            for r in d["parameters"]
            if r["parameter"] == "drug_nonresponse_magnitude_mild"
        ],
        "number_in_structure": lambda d: c1(d)["double_take"].update({"onset": 3}),
        "absolute_pressure_row": lambda d: [
            r.update({"unit": "mmHg"})
            for r in d["parameters"]
            if r["parameter"] == "hypertensive_spike_magnitude_below"
        ],
        "hold_row_in_scale_units": lambda d: [
            r.update({"unit": "x scale_range"})
            for r in d["parameters"]
            if r["parameter"] == "hypotension_below_hold_magnitude_near"
        ],
    }
    for name, mutate in cases.items():
        with pytest.raises(InjectionError):
            load_c1_design(mutated(tmp_path, f"{name}.yaml", mutate))
    load_c1_design(INJECTIONS_FILE)  # the committed file still loads


def test_confounder_design_rules_are_named_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    groups = lambda d: d["confounders"]["groups"]
    g1_name, g2_name, g3_name = GROUPS
    cases: dict[str, Callable[[dict[str, Any]], None]] = {
        "no_section": lambda d: d.pop("confounders"),
        "section_not_a_mapping": lambda d: d.update({"confounders": [1]}),
        "no_groups": lambda d: d["confounders"].pop("groups"),
        "missing_group": lambda d: groups(d).pop(g3_name),
        "extra_group": lambda d: groups(d).update({"other": groups(d)[g1_name]}),
        "group_missing_key": lambda d: groups(d)[g1_name].pop("added_by"),
        "group_extra_key": lambda d: groups(d)[g1_name].update({"extra": "x"}),
        "members_wrong_class": lambda d: groups(d)[g1_name]["members"]["A"].update(
            {"class": "C2"}
        ),
        "members_wrong_subtype": lambda d: groups(d)[g2_name]["members"]["B"].update(
            {"subtype": "replay"}
        ),
        "members_missing": lambda d: groups(d)[g3_name]["members"].pop("B"),
        "matrix_rows_not_list": lambda d: groups(d)[g1_name].update(
            {"matrix_rows": "6"}
        ),
        "matrix_rows_empty_text": lambda d: groups(d)[g1_name].update(
            {"matrix_rows": [" "]}
        ),
        "no_variants": lambda d: groups(d)[g1_name].update({"variants": {}}),
        "variants_not_a_mapping": lambda d: groups(d)[g1_name].update(
            {"variants": ["a"]}
        ),
        "unknown_field": lambda d: first_variant(d).update({"colour": "red"}),
        "bad_gap": lambda d: first_variant(d).update({"bounce_gap": "huge"}),
        "bad_withheld": lambda d: first_variant(d).update({"withheld": ["nothing"]}),
        "withheld_not_list": lambda d: first_variant(d).update({"withheld": "witness"}),
        "witness_alone": lambda d: first_variant(d).update({"withheld": ["witness"]}),
        "expected_not_bool": lambda d: first_variant(d).update(
            {"expected_indistinguishable": "yes"}
        ),
        "no_source_type": lambda d: first_variant(d).pop("source_type"),
        "bad_source_type": lambda d: first_variant(d).update(
            {"source_type": "invented"}
        ),
        "empty_source_ref": lambda d: first_variant(d).update({"source_ref": " "}),
        "no_rationale": lambda d: first_variant(d).pop("rationale"),
        "attacker_in_group_one": lambda d: first_variant(d).update(
            {"attacker": "naive"}
        ),
        "gap_in_group_two": lambda d: first_variant(d, g2_name).update(
            {"bounce_gap": "nominal"}
        ),
        "no_attacker": lambda d: first_variant(d, g2_name).pop("attacker"),
        "number": lambda d: first_variant(d).update({"withheld": [1]}),
    }
    for name, mutate in cases.items():
        with pytest.raises(InjectionError):
            load_confounder_design(mutated(tmp_path, f"{name}.yaml", mutate))
    # too many variants (the bound is lowered to keep the file small)
    monkeypatch.setattr(confounders_mod, "MAX_VARIANTS", 25)
    big = mutated(
        tmp_path,
        "big.yaml",
        lambda d: groups(d)[g1_name]["variants"].update(
            {f"v{k}": dict(first_variant(d)) for k in range(26)}
        ),
    )
    with pytest.raises(InjectionError):
        load_confounder_design(big)
    monkeypatch.undo()
    assert set(load_confounder_design(INJECTIONS_FILE)) == set(GROUPS)


def test_the_committed_grid_lists_every_discriminator_it_withholds_consistently() -> (
    None
):
    for variants in load_confounder_design(INJECTIONS_FILE).values():
        for v in variants:
            if not v.robot_present:
                assert not v.task_outcomes, v.variant_id  # no robot, no task outcome
            assert set(v.withheld) <= set(WITHHOLDABLE)
    assert confounders_mod.WITHHOLDABLE == (
        "content_change",
        "witness",
        "robot_task_outcome",
        "verification",
    )


def check_variant_names_match_withheld(path: Path) -> None:
    """Review F6 (Y03): the flags in a variant id and the channels it withholds say the same."""
    design = load_confounder_design(path)
    first, second, third = GROUPS
    robot_pair = {"witness", "robot_task_outcome"}
    expected_ids = {
        first: {
            f"{g}_{c}_{r}"
            for g in ("nominal", "stress")
            for c in ("content", "nocontent")
            for r in ("robot", "norobot")
        },
        second: {
            f"{a}_{r}_{u}"
            for a in ("naive", "informed")
            for r in ("robot", "norobot")
            for u in ("noauth", "auth")
        },
        third: {"outcome_reported", "outcome_withheld", "robot_absent"},
    }
    for group, variants in design.items():
        assert {v.variant_id for v in variants} == expected_ids[group], (
            group
        )  # the whole grid, once
    for v in design[first]:
        gap, content, robot = v.variant_id.split("_")
        assert (
            v.bounce_gap == {"nominal": "nominal", "stress": "double_take_gap"}[gap]
        ), v.variant_id
        expected = ({"content_change"} if content == "nocontent" else set()) | (
            robot_pair if robot == "norobot" else set()
        )
        assert set(v.withheld) == expected and len(v.withheld) == len(expected), (
            v.variant_id
        )
    for v in design[second]:
        attacker, robot, auth = v.variant_id.split("_")
        assert v.attacker == attacker, v.variant_id
        expected = (robot_pair if robot == "norobot" else set()) | (
            {"verification"} if auth == "noauth" else set()
        )
        assert set(v.withheld) == expected and len(v.withheld) == len(expected), (
            v.variant_id
        )
    named = {
        "outcome_reported": set(), "outcome_withheld": {"robot_task_outcome"}, "robot_absent": robot_pair,
    }  # fmt: skip
    for v in design[third]:
        assert set(v.withheld) == named[v.variant_id] and len(v.withheld) == len(
            named[v.variant_id]
        ), v.variant_id


def test_variant_ids_match_the_channels_they_withhold_in_every_state_of_the_file(
    tmp_path: Path,
) -> None:
    for path in (
        INJECTIONS_FILE,  # whatever its state
        rewrite_rows(tmp_path, filled=False, name="ids_unfilled.yaml"),
        rewrite_rows(tmp_path, filled=True, name="ids_filled.yaml"),
    ):
        check_variant_names_match_withheld(path)
    # the check catches a variant whose id and withheld channels disagree (a mutated filled copy)
    mutations: dict[str, Callable[[dict[str, Any]], None]] = {
        "content_flag": lambda groups: groups[GROUPS[0]]["variants"][
            "nominal_content_robot"
        ].update({"withheld": ["content_change"]}),
        "robot_flag": lambda groups: groups[GROUPS[0]]["variants"][
            "stress_nocontent_robot"
        ].update({"withheld": ["content_change", "witness", "robot_task_outcome"]}),
        "gap": lambda groups: groups[GROUPS[0]]["variants"][
            "stress_content_robot"
        ].update({"bounce_gap": "nominal"}),
        "auth_flag": lambda groups: groups[GROUPS[1]]["variants"][
            "naive_robot_auth"
        ].update({"withheld": ["verification"]}),
        "attacker": lambda groups: groups[GROUPS[1]]["variants"][
            "informed_robot_auth"
        ].update({"attacker": "naive"}),
        "outcome": lambda groups: groups[GROUPS[2]]["variants"][
            "outcome_withheld"
        ].update({"withheld": []}),
        "absent": lambda groups: groups[GROUPS[2]]["variants"]["robot_absent"].update(
            {"withheld": ["witness", "robot_task_outcome", "verification"]}
        ),
    }
    for name, mutate in mutations.items():
        document = yaml.safe_load(
            (tmp_path / "ids_filled.yaml").read_text(encoding="utf-8")
        )
        mutate(document["confounders"]["groups"])
        path = tmp_path / f"ids_{name}.yaml"
        path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
        with pytest.raises(AssertionError):
            check_variant_names_match_withheld(path)


def test_measurement_refusal_design_has_no_numbers_and_double_take_names_the_gap_row() -> (
    None
):
    design = load_c1_design(INJECTIONS_FILE)
    assert (
        design["measurement_refusal"].duration is None
        and design["measurement_refusal"].magnitude is None
    )
    assert (
        design["double_take"].duration is None
        and design["double_take"].magnitude is None
    )
    assert "double_take_gap_ms" in design["double_take"].onset


def test_provenance_table_lists_the_new_rows() -> None:
    table = (ROOT / "docs" / "benchmark" / "parameter-provenance.md").read_text(
        encoding="utf-8"
    )
    for row in design_rows(INJECTIONS_FILE):
        assert f"`{row['parameter']}`" in table or row["parameter"] in table, row[
            "parameter"
        ]
    rows = {r["parameter"] for r in design_rows(INJECTIONS_FILE)}
    assert (
        len(rows) >= 3 * 3 * 2 - 3 + 1
    )  # three durations and three levels for three window subtypes
    # every row of the task names its consumer and is a design choice
    assert all(r["consumer_task"] == "WS04-T09" for r in design_rows(INJECTIONS_FILE))


def test_latent_vitals_equal_the_observed_vitals_of_the_same_key() -> None:
    out = assemble(schedule=SCHED_TWO)[0]
    observed = observed_of(out, SCHED_TWO)
    for signal in ("hr_ecg", "spo2"):
        latent_values = [
            (s.t_device_ms, s.value) for s in out.latent.samples if s.signal == signal
        ]
        observed_values = [
            (s.t_device_ms, s.value) for s in observed.samples if s.signal == signal
        ]
        assert latent_values == observed_values and len(latent_values) == DAY // MIN
    # another day, another seed: the same key on both sides
    [day0, day1] = assemble(schedule=SCHED_TWO, n_days=2, seed=SEED + 3)
    for result, day in ((day0, 0), (day1, 1)):
        stream_ = build_observed_base(
            result.latent, SCHED_TWO, "plan-1", ZERO_ERRORS, DESIGN, NoJitter(), LIB,
            SEED + 3, PATIENT_INDEX,
        )  # fmt: skip
        assert [s.value for s in stream_.samples if s.signal == "hr_ecg"] == [
            s.value for s in result.latent.samples if s.signal == "hr_ecg"
        ], day


def test_latent_vitals_use_the_key_of_their_own_day_with_several_segments() -> None:
    """Review F6 (M46): with one segment per kind every day draws the same values, so a latent
    vitals key that used day 0 went unseen. Here eight segments with distinct levels make the days
    differ, and each day is compared with a draw computed from its own stream key."""
    n = DAY // MIN
    library = SegmentLibrary.from_memory(
        [
            InlineSegment(f"hr-{i}", "hr_clean", [60.0 + i] * n, MIN, "bpm")
            for i in range(8)
        ]
        + [
            InlineSegment(f"sp-{i}", "spo2_clean", [90.0 + i] * n, MIN, "%")
            for i in range(8)
        ]
    )
    seed = SEED + 5
    days = assemble(schedule=SCHED_TWO, n_days=4, library=library, seed=seed)
    levels: dict[str, list[float]] = {"hr_ecg": [], "spo2": []}
    for day, result in enumerate(days):
        for signal, kind, sub in (("hr_ecg", "hr_clean", 0), ("spo2", "spo2_clean", 1)):
            drawn = library.draw(
                kind, n, stream(seed, PATIENT_INDEX, day, StreamPurpose.SEGMENTS, sub)
            )
            got = [s.value for s in result.latent.samples if s.signal == signal]
            assert got == [drawn.values[j] for j in range(n)], (day, signal)
            levels[signal].append(got[0])
        stream_ = build_observed_base(
            result.latent, SCHED_TWO, "plan-1", ZERO_ERRORS, DESIGN, NoJitter(), library, seed, PATIENT_INDEX,
        )  # fmt: skip
        for signal in ("hr_ecg", "spo2"):
            assert [s.value for s in stream_.samples if s.signal == signal] == [
                s.value for s in result.latent.samples if s.signal == signal
            ], (day, signal)
    # the days really do draw different segments: a key of the wrong day would be seen
    assert len(set(levels["hr_ecg"])) >= 3 and len(set(levels["spo2"])) >= 3
    assert (
        levels["hr_ecg"][1] != levels["hr_ecg"][0]
        and levels["spo2"][1] != levels["spo2"][0]
    )


def test_an_intake_after_midnight_belongs_to_the_day_of_its_slot_and_acts_on_the_next_day() -> (
    None
):
    # a double take at 23:50 whose second release is at 23:59:58 and whose second intake (5 s
    # later) falls at 00:00:03 of the next day
    gap = 9 * MIN + 58 * SEC
    cfg = make_config(adherence=make_adherence(p_double_take=1.0, gap=gap))
    whole = assemble(n_days=2, schedule=SCHED_LATE, config=cfg, patient=FIX_PATIENT)
    day0_intakes = times_of(whole[0], EventKind.INTAKE)
    late_intake = DAY + 3 * SEC
    assert late_intake in day0_intakes  # in the events of day 0, after its end
    assert late_intake not in times_of(whole[1], EventKind.INTAKE)  # never twice
    assert whole[0].behaviour_log[0].dispense_times_ms == (
        DAY - 10 * MIN,
        DAY - 2 * SEC,
    )
    assert whole[0].end_state.intake_times_ms == tuple(day0_intakes)
    # its drug acts on day 1 from 00:00:03: compare with the model on the whole history
    intakes = [
        e.t_device_ms
        for r in whole
        for e in r.latent.events
        if e.kind is EventKind.INTAKE
    ]
    grid = sorted(bp_series(whole[1]))
    effect = OneCompartmentEmax().effect_mmhg(FIX_PATIENT, intakes, grid)
    expected = compose_latent_sbp([130.0] * len(grid), effect)
    assert [bp_series(whole[1])[t] for t in grid] == expected.tolist()
    # chained one-day calls agree
    parts = chained(2, schedule=SCHED_LATE, config=cfg, patient=FIX_PATIENT)
    assert [snapshot(r) for r in parts] == [snapshot(r) for r in whole]
    validate_day(
        whole[0].latent
    )  # events sorted although the last lies after the day end


def test_the_kinds_at_one_instant_are_ordered_tick_dispense_intake_measurement() -> (
    None
):
    # a dose tick, a measurement tick and a zero-lag intake at one instant
    schedule = Schedule(dose_ticks_ms=(DOSE,), measurement_ticks_ms=(DOSE,))
    cfg = make_config(adherence=make_adherence(lag=0, gap=GAP))
    out = assemble(schedule=schedule, config=cfg)[0]
    at = [e for e in out.latent.events if e.t_device_ms == DOSE]
    assert [(e.kind.value, e.payload.get("kind")) for e in at] == [
        ("schedule_tick", "dose"), ("schedule_tick", "measurement"),
        ("dispense", None), ("intake", None), ("measurement", None),
    ]  # fmt: skip


def test_the_chain_state_is_carried_across_midnight_for_a_chain_with_memory() -> None:
    # an absorbing OMITTED row: once a dose is omitted every later one is, so a chain that is not
    # carried across midnight would start again from the initial law
    absorbing = [
        [1.0, 0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [1.0, 0.0, 0.0, 0.0],
    ]
    model = make_adherence(matrix=absorbing, initial=[0.5, 0.0, 0.5, 0.0])
    cfg = make_config(adherence=model)
    carried_omission = 0
    for seed in range(8):
        whole = assemble(n_days=4, schedule=SCHED_TWO, config=cfg, seed=seed)
        parts = chained(4, schedule=SCHED_TWO, config=cfg, seed=seed)
        assert [snapshot(r) for r in whole] == [snapshot(r) for r in parts], seed
        states = [e.state for r in whole for e in r.behaviour_log]
        if AdherenceState.OMITTED in states:
            first = states.index(AdherenceState.OMITTED)
            assert set(states[first:]) == {AdherenceState.OMITTED}  # absorbing
            carried_omission += first < len(states) - len(SCHED_TWO.dose_ticks_ms)
    assert carried_omission >= 1  # the property was exercised across a day boundary
    # a forced slot is an intervention: the natural chain continues underneath it
    for seed in range(8):
        natural = assemble(n_days=2, schedule=SCHED_TWO, config=cfg, seed=seed)
        forced = assemble(
            n_days=2, schedule=SCHED_TWO, config=cfg, seed=seed,
            forced_slots=[ForcedSlot(0, 0, AdherenceState.ON_TIME)],
        )  # fmt: skip
        assert forced[0].behaviour_log[0].state is AdherenceState.ON_TIME
        assert forced[0].end_state.chain_state is natural[0].end_state.chain_state
        assert forced[1].behaviour_log == natural[1].behaviour_log


def test_the_work_bounds_are_exact(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = make_config(step=6 * HOUR)  # four grid points a day
    per_day = (
        4 + 2 * DESIGN.vitals_points + 5 * (1 + len(SCHED_ONE.measurement_ticks_ms))
    )
    monkeypatch.setattr(latent_day_mod, "MAX_TOTAL_POINTS", 2 * per_day)
    assert len(assemble(n_days=2, config=cfg)) == 2  # exactly at the bound
    with pytest.raises(LatentAssemblyError):
        assemble(n_days=3, config=cfg)
    monkeypatch.setattr(latent_day_mod, "MAX_TOTAL_POINTS", 2 * per_day - 1)
    with pytest.raises(LatentAssemblyError):
        assemble(n_days=2, config=cfg)
    monkeypatch.undo()
    # intake-by-point evaluations: two days, one intake each, four points a day
    # day 0: 1 intake * 4 points; day 1: 2 intakes * 4 points; total 12
    monkeypatch.setattr(latent_day_mod, "MAX_TOTAL_EVALUATIONS", 12)
    assert len(assemble(n_days=2, config=cfg)) == 2
    monkeypatch.setattr(latent_day_mod, "MAX_TOTAL_EVALUATIONS", 11)
    with pytest.raises(LatentAssemblyError):
        assemble(n_days=2, config=cfg)
    monkeypatch.undo()
    monkeypatch.setattr(c1_mod, "MAX_C1_SPECS", 2)
    check_c1_specs([spike(HOUR, HOUR, 1.0), spike(3 * HOUR, HOUR, 1.0)])
    with pytest.raises(C1InjectionError):
        check_c1_specs(
            [
                spike(HOUR, HOUR, 1.0),
                spike(3 * HOUR, HOUR, 1.0),
                spike(5 * HOUR, HOUR, 1.0),
            ]
        )
    monkeypatch.undo()
    monkeypatch.setattr(latent_day_mod, "MAX_FORCED_SLOTS", 1)
    assemble(forced_slots=[ForcedSlot(0, 0, AdherenceState.OMITTED)])
    with pytest.raises(LatentAssemblyError):
        assemble(forced_slots=[ForcedSlot(0, 0, AdherenceState.OMITTED)] * 2)


def test_group_pressure_scope_is_a_declared_decision() -> None:
    info = confounders_mod._GROUP_INFO
    # the pressure of the double-take pair differs by construction (two doses against one) and that of
    # the non-response pair by the drug that still occupies the saturation term; the refusal pair
    # shares the latent pressure exactly, so its comparison keeps the pressure samples
    assert {g: info[g].pressure_differs for g in GROUPS} == {
        GROUP_DOUBLE_TAKE_VS_BOUNCE: True,
        GROUP_NONRESPONSE_VS_FORGERY: True,
        GROUP_REFUSAL_VS_ROBOT_MISSED: False,
    }
    # and a difference in the pressure of the refusal pair would be seen
    ev = evaluated(G3_REPORTED)
    shifted = dataclasses.replace(
        ev.b.observed,
        samples=tuple(
            dataclasses.replace(s, value=s.value + 1.0) if s.signal == "bp" else s
            for s in ev.b.observed.samples
        ),
    )
    assert compare_observed(
        ev.a.observed, shifted, ev.a.stream.visits, ("robot_task_outcome",)
    ) == ("other",)


def test_pair_scenarios_for_the_other_knobs() -> None:
    # an informed attacker with no robot makes no spoof; with the robot, a spoof of the intake
    no_robot = build_confounder_pair(
        GROUP_NONRESPONSE_VS_FORGERY, g2("informed", False, False), BASE
    )[1]
    assert [s.subtype for s in no_robot.c3_specs] == ["dispense_forgery"]
    assert no_robot.robot_present is False and no_robot.task_outcomes is False
    robot = build_confounder_pair(
        GROUP_NONRESPONSE_VS_FORGERY, g2("informed", True, False), BASE
    )[1]
    assert sorted(s.subtype for s in robot.c3_specs) == [
        "dispense_forgery",
        "presence_spoof",
    ]
    # the other dose and the other measurement tick
    for index, tick in enumerate(SCHED_TWO.measurement_ticks_ms):
        a, b = build_confounder_pair(
            G3_REPORTED.group, G3_REPORTED, pair_base(measurement_index=index)
        )
        assert a.c1_specs[0].onset_ms == b.c2_specs[0].onset_ms == tick
    second = pair_base(dose_index=1)
    a1, b1 = build_confounder_pair(
        GROUP_DOUBLE_TAKE_VS_BOUNCE, g1("double_take_gap", True, True), second
    )
    assert a1.c1_specs[0].onset_ms == b1.c2_specs[0].onset_ms == 20 * HOUR
    assert b1.forced_slots == (ForcedSlot(0, 1, AdherenceState.ON_TIME),)
    a2, b2 = build_confounder_pair(
        GROUP_NONRESPONSE_VS_FORGERY, g2("informed", True, False), second
    )
    length = SCHED_TWO.slot_lengths_ms()[1]
    assert (a2.c1_specs[0].onset_ms, a2.c1_specs[0].duration_ms) == (20 * HOUR, length)
    assert a2.forced_slots == (ForcedSlot(0, 1, AdherenceState.ON_TIME),)
    assert b2.forced_slots == (ForcedSlot(0, 1, AdherenceState.OMITTED),)
    # the pair of the second dose realises: the 20:00 dose is the mechanism
    ev = evaluate_pair(
        GROUP_NONRESPONSE_VS_FORGERY, g2("informed", True, False), second
    )
    assert ev.indistinguishable_by_construction and ev.separated_by == ()
    assert 20 * HOUR in [e.t_device_ms for e in dispenses(ev.b.observed)]


def test_a_zero_reference_value_is_refused() -> None:
    for reference_value in (0.0, -1.0):
        with pytest.raises(C1InjectionError):
            resolve_c1_magnitude(level_row(2.0), reference_value, REFERENCE_SCALE_RANGE)


def test_records_come_back_in_canonical_order_whatever_the_order_of_the_specs() -> None:
    specs = [
        refusal(SCHED_ONE.measurement_ticks_ms[1]),
        double_take_spec(DOSE),
        hypo(3 * HOUR, HOUR, 2.0),
        nonresponse(DOSE, HOUR, 0.5),
        spike(HOUR, HOUR, 2.0),
    ]
    out = assemble(specs)[0]
    assert [r.spec for r in out.c1_records] == list(canonical_c1_order(specs))
    assert [r.spec.subtype for r in out.c1_records] == [
        "hypertensive_spike", "drug_nonresponse", "hypotension_below_hold",
        "measurement_refusal", "double_take",
    ]  # fmt: skip
    assert [r.spec for r in assemble(specs[::-1])[0].c1_records] == [
        r.spec for r in out.c1_records
    ]


def test_a_forced_slot_must_name_a_dose_of_the_schedule() -> None:
    assemble(forced_slots=[ForcedSlot(0, 0, AdherenceState.OMITTED)])  # the only dose
    with pytest.raises(LatentAssemblyError):
        assemble(
            forced_slots=[ForcedSlot(0, 1, AdherenceState.OMITTED)]
        )  # one past the last
    assemble(
        schedule=SCHED_TWO, forced_slots=[ForcedSlot(0, 1, AdherenceState.OMITTED)]
    )
    with pytest.raises(LatentAssemblyError):
        assemble(
            schedule=SCHED_TWO, forced_slots=[ForcedSlot(0, 2, AdherenceState.OMITTED)]
        )
    with pytest.raises(LatentAssemblyError):
        assemble(
            schedule=Schedule((), ()),
            forced_slots=[ForcedSlot(0, 0, AdherenceState.OMITTED)],
        )


def test_a_forced_slot_must_lie_inside_the_days_of_the_call() -> None:
    assemble(
        n_days=2, forced_slots=[ForcedSlot(1, 0, AdherenceState.OMITTED)]
    )  # the last day
    for day in (2, 3):
        with pytest.raises(LatentAssemblyError):
            assemble(
                n_days=2, forced_slots=[ForcedSlot(day, 0, AdherenceState.OMITTED)]
            )
    [first] = assemble()
    with pytest.raises(
        LatentAssemblyError
    ):  # a slot of an earlier day than the call starts at
        assemble(
            start_day=1,
            state=first.end_state,
            forced_slots=[ForcedSlot(0, 0, AdherenceState.OMITTED)],
        )
    assemble(
        start_day=1,
        state=first.end_state,
        forced_slots=[ForcedSlot(1, 0, AdherenceState.OMITTED)],
    )


def test_compare_observed_reads_times_orders_and_edges_exactly() -> None:
    # presence at the departure instant is inside the visit (closed interval, as in the base)
    one = day_of([S("presence", DOSE)])
    assert (
        compare_observed(
            one, day_of([S("presence", DOSE), S("presence", DOSE + DWELL)]), VISITS, ()
        )
        == ()
    )
    assert compare_observed(
        one, day_of([S("presence", DOSE), S("presence", DOSE + DWELL + 1)]), VISITS, ()
    ) == ("witness",)
    assert compare_observed(
        one, day_of([S("presence", DOSE), S("presence", DOSE - 1)]), VISITS, ()
    ) == ("witness",)
    # a presence only at the departure instant is still inside the visit; one ms later is not
    assert (
        compare_observed(one, day_of([S("presence", DOSE + DWELL)]), VISITS, ()) == ()
    )
    assert compare_observed(
        one, day_of([S("presence", DOSE + DWELL + 1)]), VISITS, ()
    ) == ("witness",)
    # the same sequence numbers in another order over the times are a difference
    a = day_of(
        events=[
            E(EventKind.DISPENSE, 10, "dispenser", {}, 5),
            E(EventKind.DISPENSE, 20, "dispenser", {}, 1),
        ]
    )
    b = day_of(
        events=[
            E(EventKind.DISPENSE, 10, "dispenser", {}, 1),
            E(EventKind.DISPENSE, 20, "dispenser", {}, 5),
        ]
    )
    assert compare_observed(a, b, VISITS, ()) == ("dispense_seq",)
    # an INTAKE at another time (the same count) is a difference; so is another source
    early = day_of(events=[E(EventKind.INTAKE, 10, "robot")])
    late = day_of(events=[E(EventKind.INTAKE, 11, "robot")])
    other = day_of(events=[E(EventKind.INTAKE, 10, "patient")])
    assert compare_observed(early, late, VISITS, ()) == ("witness",)
    assert compare_observed(early, other, VISITS, ()) == ("witness",)
    # a dispense at another time with the same count and sequence numbers is the interval
    d1 = day_of(events=[E(EventKind.DISPENSE, 10, "dispenser", {}, 1)])
    d2 = day_of(events=[E(EventKind.DISPENSE, 11, "dispenser", {}, 1)])
    assert compare_observed(d1, d2, VISITS, ()) == ("dispense_interval",)
    # a robot task at another time or with another payload key is a difference of the outcome field
    t1 = day_of(
        events=[
            E(
                EventKind.ROBOT_TASK,
                10,
                "robot",
                {"task": "navigate", "outcome": "late", "patient_id": "p"},
            )
        ]
    )
    t2 = day_of(
        events=[
            E(
                EventKind.ROBOT_TASK,
                11,
                "robot",
                {"task": "navigate", "outcome": "late", "patient_id": "p"},
            )
        ]
    )
    assert compare_observed(t1, t2, VISITS, ()) == ("robot_task_outcome",)


@st.composite
def pulse_plans(
    draw: Any,
) -> tuple[list[tuple[int, int, float]], list[tuple[int, int, float]]]:
    """Non-overlapping spike windows and non-overlapping hypotension windows on the hour grid."""

    def windows(count: int) -> list[tuple[int, int, float]]:
        cuts = sorted(
            draw(
                st.lists(
                    st.integers(0, 24),
                    min_size=2 * count,
                    max_size=2 * count,
                    unique=True,
                )
            )
        )
        magnitudes = draw(st.lists(st.integers(1, 80), min_size=count, max_size=count))
        return [
            (
                cuts[2 * k] * HOUR,
                (cuts[2 * k + 1] - cuts[2 * k]) * HOUR,
                magnitudes[k] / 4.0,
            )
            for k in range(count)
        ]

    return windows(draw(st.integers(0, 3))), windows(draw(st.integers(0, 3)))


@settings(max_examples=60, deadline=None, derandomize=True)
@given(plan=pulse_plans(), data=st.data())
def test_pulses_on_random_windows_are_exact_and_independent_of_the_order(
    plan: tuple[list[tuple[int, int, float]], list[tuple[int, int, float]]],
    data: st.DataObject,
) -> None:
    spikes, hypos = plan
    specs = [spike(o, d, m) for o, d, m in spikes] + [
        hypo(o, d, m) for o, d, m in hypos
    ]
    order = data.draw(st.permutations(specs)) if specs else []
    cfg = make_config(step=HOUR)
    plain = bp_series(assemble(config=cfg)[0])
    out = assemble(order, config=cfg)[0]
    got = bp_series(out)
    for t, base in plain.items():
        pulse = 0.0
        for o, d, m in sorted(spikes):
            if o <= t < o + d:
                pulse += m
        for o, d, m in sorted(hypos):
            if o <= t < o + d:
                pulse += -m
        assert got[t] == (base + pulse if pulse != 0.0 else base), (
            t
        )  # exact: multiples of 0.25
    assert {r.n_changed for r in out.c1_records} <= set(range(25))
    assert sum(r.n_changed for r in out.c1_records) == sum(
        d // HOUR for _, d, _ in spikes + hypos
    )
    assert (
        out.c1_records == assemble(specs, config=cfg)[0].c1_records
    )  # the input order is irrelevant
