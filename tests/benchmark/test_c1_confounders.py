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
import re
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

import ralmon.benchmark as benchmark_pkg
import ralmon.benchmark.confounders as confounders_mod
import ralmon.benchmark.inject_c1 as c1_mod
import ralmon.benchmark.injection as injection_mod
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
    load_design_file,
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
FINE = 10 * SEC  # FIXTURE-ONLY: a grid fine enough to sit on the pressure peak
LAG = 5 * SEC  # FIXTURE-ONLY intake lag
GAP = 2 * MIN  # FIXTURE-ONLY double-take gap
BOUNCE = 500  # FIXTURE-ONLY nominal (sub-second) bounce gap, ms
DWELL = 10 * MIN  # FIXTURE-ONLY robot dwell
PEAK_CLOCK = 14 * HOUR  # FIXTURE-ONLY circadian peak clock time
SEED = 7
PATIENT_INDEX = 3

DOSE = 8 * HOUR
SCHED_ONE = Schedule(
    dose_ticks_ms=(DOSE,), measurement_ticks_ms=(7 * HOUR + 15 * MIN, 9 * HOUR + 45 * MIN)
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
NOISY_ERRORS = DeviceErrorModel(4.0, 1.0, 0.0, 0.0)  # FIXTURE-ONLY cuff error SD 4, bias 1
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
) -> AdherenceModel:
    return AdherenceModel(
        AdherenceParams(p_delay, p_omission, p_double_take, mean_delay),
        AdherenceConfig(intake_lag_ms=lag, double_take_gap_ms=gap),
        transition_matrix=matrix,
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
        (intake - 10 * MIN, 10 * MIN, False),  # [intake - 10 min, intake): the end is excluded
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
    assert times_of(out, EventKind.SCHEDULE_TICK).count(second) == 1  # the tick still happens
    [record] = out.c1_records
    assert record.spec.subtype == "measurement_refusal" and record.realised
    assert record.realised_onset_ms == second and record.realised_end_ms is None

    stream_ = observe_refusals(observed_of(out), out.c1_records)
    day = finalize_observed(stream_)
    visit = next(v for v in stream_.visits if v.kind == "measurement" and v.tick_ms == second)
    presences = [s.t_device_ms for s in day.samples if s.signal == "presence"]
    assert visit.arrival_ms in presences  # the robot visit is there
    tasks = [e for e in day.events if e.kind is EventKind.ROBOT_TASK]
    assert any(
        e.payload["task"] == "navigate" and e.payload["outcome"] == "success"
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
    out = assemble([spike(HOUR, HOUR, 10.0), refusal(SCHED_ONE.measurement_ticks_ms[0])])[0]
    for item in dataclasses.astuple(out.latent) + tuple(out.c1_records) + (out.end_state,):
        assert not isinstance(item, GroundTruthEvent)
    assert all(r.spec.cls is C1 for r in out.c1_records)
    # the module has no constructor of a truth event in its namespace
    assert not hasattr(c1_mod, "GroundTruthEvent") and not hasattr(latent_day_mod, "GroundTruthEvent")


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
    assert not signals & {"cuff_health", "inflation_ms", "presence", "hr_pulse", "day_end"}
    assert all(s.quality is None and s.seq is None for s in day.samples)
    assert all(s.t_rx_ms == s.t_device_ms for s in day.samples)
    kinds = {e.kind for e in day.events}
    assert kinds <= {
        EventKind.DISPENSE, EventKind.INTAKE, EventKind.MEASUREMENT, EventKind.SCHEDULE_TICK,
    }  # fmt: skip
    assert {EventKind.MEASUREMENT, EventKind.SCHEDULE_TICK} <= kinds
    assert all(e.seq is None and e.t_rx_ms == e.t_device_ms for e in day.events)
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
    assert all(type(s.t_device_ms) is int and type(s.value) is float for s in day.samples)
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
    for t in ticks:
        held = bp[max(g for g in grid if g <= t)]
        from ralmon.benchmark.measurement import LatentSbpHold

        assert LatentSbpHold(out.latent.samples).at(t) == held
    # an off-grid tick and a day with no measurement tick
    off = Schedule(dose_ticks_ms=(), measurement_ticks_ms=(8 * HOUR + 17 * SEC,))
    odd = assemble(schedule=off, patient=NOISY_PATIENT)[0]
    assert times_of(odd, EventKind.MEASUREMENT) == [8 * HOUR + 17 * SEC]
    none = assemble(schedule=Schedule((), ()))[0]
    assert times_of(none, EventKind.MEASUREMENT) == [] and none.refused_ticks_ms == ()


def test_assembly_without_injections_equals_baseline_minus_effect() -> None:
    config = make_config(step=STEP, adherence=NATURAL)
    for patient in (FIX_PATIENT, NOISY_PATIENT):
        out = assemble(patient=patient, schedule=SCHED_TWO, config=config)[0]
        # the same pipeline written out by hand with the same named streams
        rng = stream(SEED, PATIENT_INDEX, 0, StreamPurpose.LATENT_AR)
        base = simulate_baseline_sbp(
            patient, STEP, 1, PEAK_CLOCK, STEP, rng, start_day=0
        )
        adh_rng = stream(SEED, PATIENT_INDEX, 0, StreamPurpose.ADHERENCE)
        events = NATURAL.simulate(SCHED_TWO, 1, adh_rng, start_day=0).events
        intakes = intake_times_from_events(events)
        effect = OneCompartmentEmax().effect_mmhg(patient, intakes, base.t_ms.tolist())
        expected = compose_latent_sbp(base.sbp_mmhg, effect)
        assert [s.value for s in out.latent.samples if s.signal == "bp"] == expected.tolist()
        assert list(out.baseline_sbp_mmhg) == base.sbp_mmhg.tolist()
        assert dispense_intake(out) == [
            (e.kind.value, e.t_device_ms, e.source) for e in events
        ]
        assert out.c1_records == ()


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
    chain = make_adherence(p_double_take=1.0)  # every slot is a double take, same gap and lag
    chain_events = chain.simulate(
        SCHED_TWO, 1, stream(SEED, PATIENT_INDEX, 0, StreamPurpose.ADHERENCE), start_day=0
    )
    first_slot, second_slot = chain_events.behaviour_log
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
    assert [row[1] for row in got if row[0] == "intake"] == [DOSE + LAG, DOSE + GAP + LAG]
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
        [double_take_spec(DOSE)], schedule=SCHED_TWO, config=make_config(adherence=chain)
    )[0]
    assert again.c1_records[0].realised
    assert [r for r in dispense_intake(again) if r[1] < 20 * HOUR] == expected


@pytest.mark.parametrize(
    "state", [AdherenceState.ON_TIME, AdherenceState.OMITTED, AdherenceState.DOUBLE_TAKE]
)
def test_forced_slot_equals_the_chain_in_that_state(state: AdherenceState) -> None:
    probabilities = {
        AdherenceState.ON_TIME: {},
        AdherenceState.OMITTED: {"p_omission": 1.0},
        AdherenceState.DOUBLE_TAKE: {"p_double_take": 1.0},
    }[state]
    chain = make_adherence(**probabilities)
    reference = chain.simulate(
        SCHED_TWO, 1, stream(SEED, PATIENT_INDEX, 0, StreamPurpose.ADHERENCE), start_day=0
    )
    # natural chain: the delayed / omitted / double mix; force slot 0 into `state`
    out = assemble(
        schedule=SCHED_TWO,
        config=make_config(adherence=NATURAL),
        forced_slots=[ForcedSlot(0, 0, state)] if state is not AdherenceState.DOUBLE_TAKE else (),
        specs=[double_take_spec(DOSE)] if state is AdherenceState.DOUBLE_TAKE else (),
    )[0]
    assert out.behaviour_log[0].state is state
    assert out.behaviour_log[0].dispense_times_ms == reference.behaviour_log[0].dispense_times_ms
    natural = assemble(schedule=SCHED_TWO, config=make_config(adherence=NATURAL))[0]
    assert out.behaviour_log[1] == natural.behaviour_log[1]  # the other slot is bit-identical
    assert [r for r in dispense_intake(out) if r[1] >= 20 * HOUR] == [
        r for r in dispense_intake(natural) if r[1] >= 20 * HOUR
    ] or natural.behaviour_log[0].dispense_times_ms[:1] == ()  # a delayed first slot may cross


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
            specs=[double_take_spec(DOSE)] if slot is AdherenceState.DOUBLE_TAKE else (),
        )[0]
        assert dispense_intake(forced) == dispense_intake(natural), seed
        assert forced.behaviour_log == natural.behaviour_log, seed


def test_forcing_a_delayed_dose_is_refused() -> None:
    with pytest.raises(LatentAssemblyError):
        ForcedSlot(0, 0, AdherenceState.DELAYED)
    with pytest.raises(LatentAssemblyError):
        assemble(forced_slots=[ForcedSlot(0, 5, AdherenceState.OMITTED)])  # no such dose
    with pytest.raises(LatentAssemblyError):
        assemble(forced_slots=[ForcedSlot(3, 0, AdherenceState.OMITTED)])  # day outside the call
    with pytest.raises(LatentAssemblyError):  # the same slot forced twice
        assemble(
            forced_slots=[
                ForcedSlot(0, 0, AdherenceState.OMITTED),
                ForcedSlot(0, 0, AdherenceState.ON_TIME),
            ]
        )
    with pytest.raises(LatentAssemblyError):  # a double-take spec and a forced slot on one slot
        assemble(
            [double_take_spec(DOSE)], forced_slots=[ForcedSlot(0, 0, AdherenceState.OMITTED)]
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
        "row", "above", unit, value, value is not None, "design_choice", "fixture", quantity_unit
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
    assert assemble([spec])[0].c1_records[0].spec.magnitude == 40.0
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
    nonresp = c1_spec_from_level("drug_nonresponse", DOSE, scale, None, duration_ms=HOUR)
    assert nonresp.magnitude == 0.5 and nonresp.magnitude_unit == UNIT_SCALE
    assert "reference" not in nonresp.params


def design_rows(path: Path, task: str = "WS04-T09") -> list[dict[str, Any]]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
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
                    assert entry.magnitude.unit == UNIT_SCALE and level.unit == UNIT_SCALE
        if entry.duration is not None:
            assert entry.duration.unit == "ms" and len(entry.duration.levels) >= 1
    # no row of the task is an absolute pressure
    for row in design_rows(path):
        assert row["unit"] != "mmHg", row["parameter"]
        assert row["source_type"] in SOURCE_TYPES
        assert isinstance(row["source_ref"], str) and row["source_ref"].strip()


def rewrite_rows(
    tmp_path: Path, *, filled: bool, name: str, drop_status_lines: bool = False
) -> Path:
    """A copy of injections.yaml with every row of the task awaiting a value, or filled."""
    document = yaml.safe_load(INJECTIONS_FILE.read_text(encoding="utf-8"))
    for row in document["parameters"]:
        unit = row["unit"]
        if filled:
            if row["status"] == "awaiting_human_value":
                row["value"] = (
                    60_000 if unit == "ms" else 2.0 if unit.startswith("x ") else 0.5
                )
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


def test_c1_rows_are_structured_relative_and_valid_in_every_state(tmp_path: Path) -> None:
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
        if row["consumer_task"] == "WS04-T09" and row["unit"].startswith("x scale_range"):
            row["unit"] = "mmHg"
    bad = tmp_path / "absolute.yaml"
    bad.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    with pytest.raises((AssertionError, InjectionError)):
        check_c1_design_structure(bad)


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
        GROUP_DOUBLE_TAKE_VS_BOUNCE, vid, withheld=withheld, bounce_gap=gap, expected=expected
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

G1_GRID = [g1(gap, c, r) for gap in ("nominal", "double_take_gap") for c in (True, False) for r in (True, False)]
G2_GRID = [g2(a, r, u) for a in ("naive", "informed") for r in (True, False) for u in (False, True)]
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
    assert len(set(ra.latent.baseline_sbp_mmhg)) > 100  # a real, noisy, circadian baseline
    # the same cuff noise draws: the stream (seed, patient, day, MEASUREMENT, k) feeds both
    for k, (ma, mb) in enumerate(zip(ra.stream.measurements, rb.stream.measurements, strict=True)):
        z0 = float(stream(SEED, PATIENT_INDEX, 0, StreamPurpose.MEASUREMENT, ma.index).standard_normal(3)[0])
        expected_error = NOISY_ERRORS.cuff_bias_mmhg + NOISY_ERRORS.cuff_error_sd_mmhg * z0
        assert ma.error_mmhg == mb.error_mmhg == expected_error, k
        assert ma.inflation_ms == mb.inflation_ms and ma.index == mb.index
    assert len(ra.stream.measurements) == len(SCHED_TWO.measurement_ticks_ms)
    # the same schedule, patient, seed and care plan
    assert ra.observed.patient_id == rb.observed.patient_id == "p0003"
    assert ra.observed.seed == rb.observed.seed == SEED
    assert ra.observed.care_plan_id == rb.observed.care_plan_id
    assert [e.t_device_ms for e in ra.latent.latent.events if e.kind is EventKind.SCHEDULE_TICK] == [
        e.t_device_ms for e in rb.latent.latent.events if e.kind is EventKind.SCHEDULE_TICK
    ]
    assert [e.t_device_ms for e in ra.latent.latent.events if e.kind is EventKind.MEASUREMENT] == list(
        SCHED_TWO.measurement_ticks_ms
    )
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
    assert not [e for e in da.events if e.kind is EventKind.INTAKE]  # the robot is absent
    assert not [s for s in da.samples if s.signal == "presence"]
    assert not [e for e in da.events if e.kind is EventKind.ROBOT_TASK]
    # the latent days differ: two intakes against one
    assert len(times_of(ev.a.latent, EventKind.INTAKE)) == len(times_of(ev.b.latent, EventKind.INTAKE)) + 1
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
    assert [e.t_device_ms for e in dispenses(nominal.b.observed)][:2] == [DOSE, DOSE + BOUNCE]
    assert [e.t_device_ms for e in dispenses(nominal.a.observed)][:2] == [DOSE, DOSE + GAP]
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
            assert all(vocab.KEY_CONTENT_CHANGE not in e.payload for e in dispenses(day))
        if "witness" in v.withheld:
            assert not [e for e in day.events if e.kind is EventKind.INTAKE]
            assert not [s for s in day.samples if s.signal == "presence"]


def only(day: ObservedDay, kind: EventKind, source: str | None = None) -> list[Event]:
    return [e for e in day.events if e.kind is kind and (source is None or e.source == source)]


def test_nonresponse_vs_forgery_identical_without_witness() -> None:
    # robot co-located and spoofed (informed attacker, spoof_intake, no authentication)
    spoofed = evaluated(g2("informed", True, False))
    real, forged = spoofed.a, spoofed.b
    assert {r.spec.subtype for r in real.records} == {"drug_nonresponse"}
    assert {r.spec.subtype for r in forged.records} == {"dispense_forgery", "presence_spoof"}
    assert real.records[0].spec.cls is C1 and real.records[0].spec.magnitude == 0.0
    assert {r.spec.cls for r in forged.records} == {C3}
    assert dispenses(real.observed) == dispenses(forged.observed)
    assert only(real.observed, EventKind.INTAKE) == only(forged.observed, EventKind.INTAKE)
    assert len(only(real.observed, EventKind.INTAKE, "robot")) >= 1
    assert spoofed.separated_by == () and spoofed.indistinguishable_by_construction is True
    # the whole observed days agree outside the presence samples (an extra 1.0 inside a visit
    # changes no held level): the pressure response is equal because scale 0 removes the effect
    assert [s for s in real.observed.samples if s.signal == "bp"] == [
        s for s in forged.observed.samples if s.signal == "bp"
    ]
    # the robot absent: equal streams without any witness
    absent = evaluated(g2("informed", False, False))
    assert dispenses(absent.a.observed) == dispenses(absent.b.observed)
    assert not only(absent.a.observed, EventKind.INTAKE) and not only(absent.b.observed, EventKind.INTAKE)
    assert absent.separated_by == () and absent.indistinguishable_by_construction is True
    # the latent days differ: a dose against none
    assert len(times_of(real.latent, EventKind.DISPENSE)) == len(times_of(forged.latent, EventKind.DISPENSE)) + 1
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
    assert "witness" in ev.separated_by and ev.indistinguishable_by_construction is False
    assert {r.spec.subtype for r in ev.b.records} == {"dispense_forgery"}  # a naive spoof is not made
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


def test_refusal_vs_robot_missed_pair() -> None:
    ev = evaluated(G3_REPORTED)
    tick = SCHED_TWO.measurement_ticks_ms[BASE.measurement_index]
    a, b = ev.a, ev.b
    assert {r.spec.subtype for r in a.records} == {"measurement_refusal"}
    assert {r.spec.subtype for r in b.records} == {"manipulation_failure"}
    assert (a.records[0].spec.cls, b.records[0].spec.cls) == (C1, C2)
    assert a.records[0].spec.onset_ms == b.records[0].spec.onset_ms == tick
    assert {r.confounder_group for r in a.records + b.records} == {GROUP_REFUSAL_VS_ROBOT_MISSED}
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
    outcomes = lambda day: [  # noqa: E731
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
    result = apply_observation_injections(stream_, [bias], InjectionContext(PATIENT_INDEX))
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
    assert "variant_id" not in plain[0] and "indistinguishable_by_construction" not in plain[0]


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
            assert v.source_type in SOURCE_TYPES and v.source_ref.strip() and v.rationale.strip()
            assert set(v.withheld) <= {"content_change", "witness", "robot_task_outcome", "verification"}


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
    short = copy.deepcopy(yaml.safe_load((tmp_path / "f.yaml").read_text(encoding="utf-8")))
    levels = short["injections"]["c1"]["hypertensive_spike"]["magnitude"]["levels"]
    levels.pop(next(iter(levels)))
    bad = tmp_path / "two_levels.yaml"
    bad.write_text(yaml.safe_dump(short, sort_keys=False), encoding="utf-8")
    with pytest.raises(InjectionError):
        load_c1_design(bad)
    # a variant without provenance is refused
    broken = copy.deepcopy(yaml.safe_load((tmp_path / "f.yaml").read_text(encoding="utf-8")))
    group = next(iter(broken["confounders"]["groups"].values()))
    next(iter(group["variants"].values())).pop("source_ref")
    bad2 = tmp_path / "no_ref.yaml"
    bad2.write_text(yaml.safe_dump(broken, sort_keys=False), encoding="utf-8")
    with pytest.raises(InjectionError):
        load_confounder_design(bad2)


def test_committed_grid_matches_the_computed_separation() -> None:
    """The ``expected_indistinguishable`` of every committed variant is what the code computes."""
    design = load_confounder_design(INJECTIONS_FILE)
    for group, variants in design.items():
        for v in variants:
            ev = evaluated(v)
            assert ev.indistinguishable_by_construction is v.expected_indistinguishable, v.variant_id
    # the grid has separable and indistinguishable variants for every group (abstention can be scored)
    for group, variants in design.items():
        flags = {v.expected_indistinguishable for v in variants}
        assert flags == {True, False}, group


# ---------------------------------------------------------------------------
# compare_observed: each discriminator on its own, hand-written days
# ---------------------------------------------------------------------------


def S(signal: str, t: int, value: float = 1.0, seq: int | None = None) -> Sample:
    return Sample(signal, t, t, value, seq, None)


def E(kind: EventKind, t: int, source: str, payload: Mapping[str, Any] | None = None, seq: int | None = None) -> Event:
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
            day_of(events=[E(EventKind.DISPENSE, DOSE, "dispenser", {"content_change": 1.0}, 1)]),
            day_of(events=[E(EventKind.DISPENSE, DOSE, "dispenser", {"content_change": 0.0}, 1)]),
        ),
        "witness": (
            day_of(events=[E(EventKind.INTAKE, DOSE + LAG, "robot")]),
            day_of(),
        ),
        "robot_task_outcome": (
            day_of(events=[E(EventKind.ROBOT_TASK, DOSE, "robot", {"task": "manipulate", "outcome": "failed", "patient_id": "p0"})]),
            day_of(events=[E(EventKind.ROBOT_TASK, DOSE, "robot", {"task": "manipulate", "outcome": "declined", "patient_id": "p0"})]),
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
            day_of(events=[E(EventKind.DEVICE_ERROR, DOSE, "gateway", {"verification": "failed", "subject": "dispenser"})]),
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
        day_of([S("hr_ecg", 1, 70.0)]), day_of([S("hr_ecg", 1, 71.0)]), VISITS, (), ignore_pressure=True
    ) == ("other",)


def test_compare_observed_presence_is_a_level_over_the_visit() -> None:
    one = day_of([S("presence", DOSE)])
    extra_in_visit = day_of([S("presence", DOSE), S("presence", DOSE + LAG)])
    assert compare_observed(one, extra_in_visit, VISITS, ()) == ()  # a held level: no new information
    outside = day_of([S("presence", DOSE), S("presence", DOSE + 2 * DWELL)])
    assert compare_observed(one, outside, VISITS, ()) == ("witness",)  # a sample off every visit
    no_visit = day_of()
    assert compare_observed(one, no_visit, VISITS, ()) == ("witness",)
    assert compare_observed(one, no_visit, VISITS, ("witness",)) == ()
    # the order of items at one instant is not a difference
    x = E(EventKind.SCHEDULE_TICK, 5, "ward", {"kind": "dose"})
    y = E(EventKind.NODE_STATE, 5, "cuff", {"state": "active"})
    assert compare_observed(day_of(events=[x, y]), day_of(events=[y, x]), VISITS, ()) == ()


def test_compare_observed_reads_observed_days_only() -> None:
    sig = inspect.signature(compare_observed)
    for name in ("a", "b"):
        assert sig.parameters[name].annotation in (ObservedDay, "ObservedDay")
    code_names = set(compare_observed.__code__.co_names)
    assert not code_names & {"LatentDay", "latent", "LatentResult", "baseline_sbp_mmhg"}
    src = inspect.getsource(confounders_mod)
    comparison = src[src.index("def compare_observed"):]
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
    one = assemble(specs, patient=NOISY_PATIENT, schedule=SCHED_TWO, n_days=2, config=cfg)
    two = assemble(specs, patient=NOISY_PATIENT, schedule=SCHED_TWO, n_days=2, config=cfg)
    assert [snapshot(r) for r in one] == [snapshot(r) for r in two]
    other = assemble(specs, patient=NOISY_PATIENT, schedule=SCHED_TWO, n_days=2, config=cfg, seed=SEED + 1)
    assert bp_series(other[0]) != bp_series(one[0])
    other_patient = assemble(specs, patient=NOISY_PATIENT, schedule=SCHED_TWO, n_days=2, config=cfg, patient_index=PATIENT_INDEX + 1)
    assert bp_series(other_patient[0]) != bp_series(one[0])
    # the order of the specs is irrelevant
    swapped = assemble(specs[::-1], patient=NOISY_PATIENT, schedule=SCHED_TWO, n_days=2, config=cfg)
    assert [snapshot(r) for r in swapped] == [snapshot(r) for r in one]
    assert [r.c1_records for r in swapped] == [r.c1_records for r in one]


def test_adding_one_c1_injection_leaves_everything_it_does_not_touch_identical() -> None:
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
        out = assemble([spec], patient=NOISY_PATIENT, schedule=SCHED_TWO, n_days=2, config=cfg)
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
    again = spike(HOUR, HOUR, 99.0)  # a different magnitude: the same injection identity
    one = c1_stream(SEED, PATIENT_INDEX, 0, spec).standard_normal(4).tolist()
    assert one == c1_stream(SEED, PATIENT_INDEX, 0, again).standard_normal(4).tolist()
    expected = stream(
        SEED, PATIENT_INDEX, 0, StreamPurpose.INJECTION_C1, injection_sub_index(spec)
    ).standard_normal(4)
    assert one == expected.tolist()
    assert one != c1_stream(SEED, PATIENT_INDEX, 0, spike(2 * HOUR, HOUR, 10.0)).standard_normal(4).tolist()
    assert one != c1_stream(SEED, PATIENT_INDEX, 1, spec).standard_normal(4).tolist()
    # the injectors themselves are deterministic functions of the spec: no draw is consumed
    source = (SRC / "inject_c1.py").read_text(encoding="utf-8")
    assert "default_rng" not in source and "np.random." not in source.replace("np.random.Generator", "")
    assert "import random" not in source and "time." not in source.replace("datetime", "")


def test_pair_members_do_not_shift_each_others_draws() -> None:
    v = g1("double_take_gap", True, True)
    ev = evaluated(v)
    # the draws of the cuff and of the vitals are the same whatever the mechanism
    assert [m.error_mmhg for m in ev.a.stream.measurements] == [m.error_mmhg for m in ev.b.stream.measurements]
    hr = lambda r: [s.value for s in r.latent.latent.samples if s.signal == "hr_ecg"]  # noqa: E731
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


def chained(
    n_days: int, **kwargs: Any
) -> list[LatentResult]:
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
    # the end state of the whole call is the state to continue from
    [day3] = assemble(start_day=3, state=whole[-1].end_state, **{k: v for k, v in kwargs.items() if k != "specs"}, specs=[])
    [day3_whole] = assemble(n_days=4, **{k: v for k, v in kwargs.items() if k != "specs"}, specs=[])[3:]
    assert bp_series(day3)  # continues
    assert day3.latent.day_index == 3


def test_midnight_carries_the_drug_the_noise_and_the_chain() -> None:
    cfg = make_config(adherence=NATURAL)
    kwargs: dict[str, Any] = {"patient": NOISY_PATIENT, "schedule": SCHED_LATE, "config": cfg}
    whole = assemble(n_days=2, **kwargs)
    # (1) drug accumulation: the dose of day 0 at 23:50 acts on day 1 (intake 23:50:05, effect at 00:30)
    perfect = make_config(adherence=PERFECT)
    both = assemble(n_days=2, patient=FIX_PATIENT, schedule=SCHED_LATE, config=perfect)
    carried = bp_series(both[1])
    t = DAY + 30 * MIN  # 40 minutes after the intake, near the effect peak
    assert 130.0 - carried[t] > 5.0  # a large drop on day 1 caused by the dose of day 0
    # without the history of day 0 the effect is gone: a day 1 assembled alone has none of it
    [alone] = assemble(start_day=1, state=AssemblyState(1, 0.0, None, ()), patient=FIX_PATIENT, schedule=SCHED_LATE, config=perfect)
    assert 130.0 - bp_series(alone)[t] < 130.0 - carried[t] - 5.0
    # (2) autoregressive noise continues: day 1 starts from the last value of day 0
    first_noise_day1 = whole[1].baseline_sbp_mmhg[0]
    last_noise_day0 = whole[0].end_state.ar_state_mmhg
    assert whole[0].end_state.next_day == 1 and whole[1].end_state.next_day == 2
    reset = chained(2, **kwargs)[1].baseline_sbp_mmhg[0]
    assert first_noise_day1 == reset
    assert last_noise_day0 == whole[0].end_state.ar_state_mmhg
    # a state that is not carried (a fresh AR state) gives another day 1
    [fresh] = assemble(start_day=1, state=AssemblyState(1, 0.0, whole[0].end_state.chain_state, whole[0].end_state.intake_times_ms), **kwargs)
    assert fresh.baseline_sbp_mmhg != whole[1].baseline_sbp_mmhg
    # (3) the adherence chain continues: the carried state is the last outcome of day 0
    assert whole[0].end_state.chain_state is whole[0].behaviour_log[-1].state


def test_assembly_state_must_match_the_start_day() -> None:
    [first] = assemble()
    for state in (None, first.end_state):
        with pytest.raises(LatentAssemblyError):
            assemble(start_day=2, state=state)  # the state is of day 1, or absent
    with pytest.raises(LatentAssemblyError):
        assemble(start_day=0, state=first.end_state)  # a start from day 0 has no state to carry
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
        InjectionSpec(C1, "hypertensive_spike", HOUR, None, 5.0, "mmHg"),  # a window needs a duration
        InjectionSpec(C1, "hypertensive_spike", HOUR, HOUR, None, None),  # needs a magnitude
        InjectionSpec(C1, "hypertensive_spike", HOUR, HOUR, 5.0, "ms"),  # wrong unit
        InjectionSpec(C1, "hypertensive_spike", HOUR, HOUR, 0.0, "mmHg"),  # must be above zero
        InjectionSpec(C1, "hypertensive_spike", HOUR, HOUR, -5.0, "mmHg"),  # the sign is the subtype's
        InjectionSpec(C1, "hypotension_below_hold", HOUR, HOUR, -5.0, "mmHg"),
        InjectionSpec(C1, "drug_nonresponse", HOUR, HOUR, 1.5, "1"),  # a scale above 1 is no non-response
        InjectionSpec(C1, "drug_nonresponse", HOUR, HOUR, -0.5, "1"),
        InjectionSpec(C1, "drug_nonresponse", HOUR, HOUR, 0.5, "mmHg"),
        InjectionSpec(C1, "measurement_refusal", HOUR, HOUR),  # a refusal is per tick
        InjectionSpec(C1, "measurement_refusal", HOUR, None, 1.0, "1"),  # and has no magnitude
        InjectionSpec(C1, "double_take", HOUR, None, 1.0, "1"),
        InjectionSpec(C1, "hypertensive_spike", HOUR, HOUR, 5.0, "mmHg", {"foo": 1}),  # unknown param
        InjectionSpec(C1, "hypertensive_spike", HOUR, HOUR, 5.0, "mmHg", {"multiple": 2.0, "reference_value": 20.0, "reference": "scale_range"}),  # 5 != 2 * 20
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
    check_c1_specs([spike(HOUR, HOUR, 5.0), spike(2 * HOUR, HOUR, 5.0)])  # touching windows
    check_c1_specs([spike(HOUR, HOUR, 5.0), hypo(HOUR, HOUR, 5.0)])  # different subtypes overlap
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
    assert ok.c1_records[0].realised and bp_series(ok)[DAY - STEP] == bp_series(assemble()[0])[DAY - STEP] + 5.0


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
    assert [s.subtype for s in first][:2] == ["hypertensive_spike", "hypertensive_spike"]
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
        assemble(schedule=many, config=make_config(step=SEC, adherence=make_adherence(gap=1000 - 1, lag=1)), n_days=1)


# ---------------------------------------------------------------------------
# Extremes: every public function raises its named error, nothing else
# ---------------------------------------------------------------------------

JUNK: list[Any] = [
    None, True, False, "x", "", b"1", 1.5, float("nan"), float("inf"), -float("inf"), -1, 0,
    10**400, -(10**400), np.int64(3), np.float64(1.5), np.array([1]), np.array(1), [], {}, (),
    object(), [1, 2], {"a": 1}, {1, 2},
]  # fmt: skip


def fuzz(fn: Callable[..., Any], good: Mapping[str, Any], *, skip: Iterable[str] = ()) -> int:
    """Call ``fn`` with each argument replaced by each junk value; only named errors may escape."""
    skipped = set(skip)
    calls = 0
    for name in good:
        if name in skipped:
            continue
        for junk in JUNK:
            args = dict(good)
            args[name] = junk
            calls += 1
            try:
                fn(**args)
            except Exception as exc:  # noqa: BLE001
                assert named_error(exc), (fn.__name__, name, repr(junk), type(exc), exc)
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
    fuzz(c1_spec, {"subtype": "hypertensive_spike", "onset_ms": HOUR, "duration_ms": HOUR, "magnitude": 5.0})
    fuzz(c1_spec, {"subtype": "measurement_refusal", "onset_ms": HOUR}, skip=("onset_ms",))
    fuzz(hold_distance_mmhg, {"baseline_sbp_mmhg": 130.0, "bp_hold_threshold_mmhg": 100.0})
    fuzz(
        resolve_c1_magnitude,
        {"level": level_row(2.0), "reference_value": 20.0, "reference": REFERENCE_SCALE_RANGE},
    )
    fuzz(
        c1_spec_from_level,
        {"subtype": "hypertensive_spike", "onset_ms": HOUR, "level": level_row(2.0), "reference_value": 20.0, "duration_ms": HOUR},
    )
    fuzz(check_c1_specs, {"specs": [spike(HOUR, HOUR, 5.0)]})
    fuzz(canonical_c1_order, {"specs": [spike(HOUR, HOUR, 5.0)]})
    fuzz(c1_stream, {"seed": SEED, "patient_index": 0, "day_index": 0, "spec": spike(HOUR, HOUR, 5.0)})
    # the wrong type of a spec inside a list, and a list that is not a list
    for bad in (["x"], [None], "ab", b"ab", 5, {1: 2}, iter([1]), [spike(HOUR, HOUR, 5.0)] * 3):
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
        other = spike(HOUR, HOUR, 5.0) if fn is not hypertensive_spike else hypo(HOUR, HOUR, 5.0)
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
    with pytest.raises(C1InjectionError):  # a refusal whose tick has no visit in the stream
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
    fuzz(assemble_latent_days, {**good, "start_day": 0, "state": None, "forced_slots": ()}, skip=tuple(good))
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
    fuzz(AssemblyState, {"next_day": 1, "ar_state_mmhg": 0.0, "chain_state": None, "intake_times_ms": ()})
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
                FIX_PATIENT, SCHED_ONE, 1, [], model, LIB, SEED, 0, config=make_config(step=HOUR)  # type: ignore[arg-type]
            )
    with pytest.raises(LatentAssemblyError):  # a library without heart-rate segments
        assemble(library=SegmentLibrary.from_memory([]))
    ok = assemble(library=SegmentLibrary.from_memory([]), config=make_config(allow_no_segments=True))[0]
    assert {s.signal for s in ok.latent.samples} == {"bp"}  # no vitals are invented


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
    readme = (ROOT / "docs/plan/workstreams/WS04-benchmark/README.md").read_text(encoding="utf-8")
    for group in GROUPS:
        assert group in readme
    assert DISCRIMINATORS == (
        "content_change", "witness", "robot_task_outcome", "dispense_interval",
        "dispense_seq", "verification",
    )  # fmt: skip


def test_build_confounder_pair_scenarios() -> None:
    v = g1("double_take_gap", False, True)
    a, b = build_confounder_pair(v.group, v, BASE)
    assert a.group == b.group == v.group and a.variant_id == b.variant_id == v.variant_id
    assert [s.subtype for s in a.c1_specs] == ["double_take"] and not a.c2_specs and not a.c3_specs
    assert [s.subtype for s in b.c2_specs] == ["dispenser_bounce"] and not b.c1_specs
    assert b.c2_specs[0].magnitude == GAP  # the stress level: the double-take gap itself
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
    assert a2.c1_specs[0].magnitude == 0.0 and a2.c1_specs[0].magnitude_unit == UNIT_SCALE
    assert a2.forced_slots == (ForcedSlot(0, 0, AdherenceState.ON_TIME),)
    assert b2.forced_slots == (ForcedSlot(0, 0, AdherenceState.OMITTED),)
    assert [s.subtype for s in b2.c3_specs] == ["presence_spoof", "dispense_forgery"] or sorted(
        s.subtype for s in b2.c3_specs
    ) == ["dispense_forgery", "presence_spoof"]
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
    assert a3.c1_specs[0].subtype == "measurement_refusal" and a3.c1_specs[0].onset_ms == tick
    assert b3.c2_specs[0].subtype == "manipulation_failure" and b3.c2_specs[0].onset_ms == tick
    assert not a3.forced_slots and not b3.forced_slots


def test_pair_builder_refuses_inconsistent_requests() -> None:
    v = g1("double_take_gap", True, True)
    with pytest.raises(ConfounderError):
        build_confounder_pair(GROUP_REFUSAL_VS_ROBOT_MISSED, v, BASE)  # the variant is of another group
    with pytest.raises(ConfounderError):
        build_confounder_pair("no_such_group", v, BASE)
    with pytest.raises(ConfounderError):
        build_confounder_pair(v.group, g1("nominal", True, True), pair_base(nominal_bounce_gap_ms=None))
    with pytest.raises(ConfounderError):
        build_confounder_pair(v.group, v, pair_base(dose_index=2))
    with pytest.raises(ConfounderError):
        build_confounder_pair(G3_REPORTED.group, G3_REPORTED, pair_base(measurement_index=9))
    with pytest.raises(ConfounderError):  # a nominal gap that is not shorter than the double-take gap
        build_confounder_pair(v.group, g1("nominal", True, True), pair_base(nominal_bounce_gap_ms=GAP))
    # the variant itself is validated
    for kwargs in (
        {"withheld": ("nothing",)},
        {"withheld": ("witness",)},  # the robot channel is withheld as a pair: witness and task outcome
        {"withheld": ("witness", "witness", "robot_task_outcome")},
        {"bounce_gap": "huge"},
        {"attacker": "informed"},  # an attacker has no place in group 1
    ):
        with pytest.raises(ConfounderError):
            variant(GROUP_DOUBLE_TAKE_VS_BOUNCE, "v", **{"bounce_gap": "nominal", **kwargs})
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
        latent_values = {s.value for s in member.latent.latent.samples if s.signal == "bp"}
        observed_bp = [s.value for s in day.samples if s.signal == "bp"]
        assert not latent_values & set(observed_bp)  # the cuff error is not zero in this fixture
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
            InjectionContext(BASE.patient_index, library=BASE.library, latent=res.latent),
        ).stream
    )
    assert realised.observed == expected


def test_pair_works_for_a_late_day_and_a_jittered_robot() -> None:
    class Late:
        descriptor = "test-double"
        run_source = None

        def delay_ms(self, rng: np.random.Generator, *, kind: str, index: int) -> int:
            return 2 * MIN if kind == vocab.KIND_DOSE else 0

    base = pair_base(jitter=Late(), schedule=SCHED_ONE)
    v = g1("double_take_gap", True, True)
    ev = evaluate_pair(v.group, v, base)
    assert ev.separated_by == ("content_change", "witness")
    # the robot arrives two minutes late: the first intake is before the arrival, only the second
    # (DOSE + GAP + LAG) is covered, for the double take; the bounce has none after the arrival
    intakes = lambda r: [e.t_device_ms for e in only(r.observed, EventKind.INTAKE)]  # noqa: E731
    assert intakes(ev.a) != intakes(ev.b)


# ---------------------------------------------------------------------------
# The change to the measurement base (content sensing) and to the shared machinery
# ---------------------------------------------------------------------------


def test_measurement_base_emits_content_change_only_when_the_dispenser_senses_it() -> None:
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


def test_the_loader_rejects_aliases_duplicates_and_numbers_in_the_new_sections(tmp_path: Path) -> None:
    text = INJECTIONS_FILE.read_text(encoding="utf-8")
    # a duplicate key
    dup = tmp_path / "dup.yaml"
    dup.write_text(text.replace("  c1:\n", "  c1:\n    double_take: {}\n    double_take: {}\n", 1), encoding="utf-8")
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
    next(iter(next(iter(document["confounders"]["groups"].values()))["variants"].values()))["margin"] = 5
    num2 = tmp_path / "num2.yaml"
    num2.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    with pytest.raises(InjectionError):
        load_confounder_design(num2)
    # a YAML alias bomb is read in bounded time and refused or accepted, never a hang or a raw error
    bomb = "a: &a [x]\n" + "".join(
        f"{chr(98 + k)}: &{chr(98 + k)} [*{chr(97 + k)}, *{chr(97 + k)}]\n" for k in range(9)
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
    a, b = build_confounder_pair(v.group, v, BASE)
    fuzz(realise_scenario, {"scenario": a, "base_context": BASE})
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


# ---------------------------------------------------------------------------
# Layering, exports and the literal guard
# ---------------------------------------------------------------------------

NEW_MODULES = ("inject_c1", "latent_day", "confounders")
ALLOWED_IMPORTS: dict[str, set[str]] = {
    "inject_c1": {
        "ralmon.benchmark.injection", "ralmon.benchmark.latent", "ralmon.benchmark.measurement",
        "ralmon.benchmark.rng", "ralmon.benchmark.trace", "ralmon.benchmark.vocab",
        "ralmon.signals",
    },
    "latent_day": {
        "ralmon.benchmark.adherence", "ralmon.benchmark.inject_c1", "ralmon.benchmark.injection",
        "ralmon.benchmark.latent", "ralmon.benchmark.measurement", "ralmon.benchmark.pkpd",
        "ralmon.benchmark.priors", "ralmon.benchmark.rng", "ralmon.benchmark.schedule",
        "ralmon.benchmark.segments", "ralmon.benchmark.trace", "ralmon.benchmark.vocab",
        "ralmon.signals",
    },
    "confounders": {
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
    for forbidden in ("spec", "monitor", "conformal", "attribution", "baselines", "eval"):
        assert not [i for i in imports if i.split(".")[1:2] == [forbidden]], (name, forbidden)
    assert not imports - ALLOWED_IMPORTS[name] - {f"ralmon.benchmark.{name}"}, imports - ALLOWED_IMPORTS[name]
    # no wall clock, no global random state, no network, no subprocess
    source = (SRC / f"{name}.py").read_text(encoding="utf-8")
    for token in ("import time", "datetime", "import random", "np.random.seed", "np.random.normal", "socket", "subprocess", "urllib"):
        assert token not in source, (name, token)
    assert not re.search(r"default_rng\(\s*\)", source)


def test_no_new_name_is_exported_from_the_package_root() -> None:
    exported = set(benchmark_pkg.__all__)
    for module in (c1_mod, latent_day_mod, confounders_mod):
        for public in getattr(module, "__all__"):
            assert public not in exported, public
    table = (ROOT / "docs/plan/02-interfaces.md").read_text(encoding="utf-8")
    row = next(line for line in table.splitlines() if line.startswith("| `ralmon.benchmark`"))
    listed = set(re.findall(r"`([A-Za-z_]+)`", row))
    assert exported <= listed | {"ralmon.benchmark"}


def test_new_modules_have_all_and_no_unannotated_numeric_parameters() -> None:
    sys.path.insert(0, str(ROOT / "tests" / "benchmark"))
    from test_priorsource import parameter_literals

    for name in NEW_MODULES:
        path = SRC / f"{name}.py"
        assert parameter_literals(path.read_text(encoding="utf-8")) == [], name
        module = {"inject_c1": c1_mod, "latent_day": latent_day_mod, "confounders": confounders_mod}[name]
        assert sorted(module.__all__) == list(module.__all__), name  # ruff RUF022 style: sorted
        for public in module.__all__:
            assert hasattr(module, public), (name, public)
    # no clinical value of the registry appears in the new modules
    registry = yaml.safe_load(REGISTRY_FILE.read_text(encoding="utf-8"))
    clinical = {float(e["value"]) for e in registry["entries"] if abs(float(e["value"])) > 3.0}
    for name in NEW_MODULES:
        tree = ast.parse((SRC / f"{name}.py").read_text(encoding="utf-8"))
        values = {
            float(n.value)
            for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool)
        }
        assert not values & clinical, (name, values & clinical)


def test_bound_constants_are_documented_values() -> None:
    assert c1_mod.MAX_C1_SPECS == 10_000
    assert MAX_DAYS == 366
    assert latent_day_mod.MAX_TOTAL_EVALUATIONS == 20_000_000
    assert latent_day_mod.MAX_FORCED_SLOTS == 10_000
    assert confounders_mod.MAX_VARIANTS == 1_000


def test_module_help_text_names_the_conventions() -> None:
    doc = (c1_mod.__doc__ or "") + (latent_day_mod.__doc__ or "") + (confounders_mod.__doc__ or "")
    for needle in ("[onset, onset + duration)", "ground", "paired", "midnight", "R3-W4"):
        assert needle in doc, needle
    fault_model = FAULT_MODEL.read_text(encoding="utf-8")
    assert "half" in fault_model.lower()  # the window convention the docstring cites


def test_c1_subtypes_are_the_workstream_vocabulary() -> None:
    readme = (ROOT / "docs/plan/workstreams/WS04-benchmark/README.md").read_text(encoding="utf-8")
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
