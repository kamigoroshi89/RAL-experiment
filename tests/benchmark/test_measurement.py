"""Measurement process, segment library and payload vocabulary (WS04-T06).

Every number below is arithmetic and FIXTURE-ONLY (constant pressure 130 on a 60 s grid, ticks
at 08:00 and 20:00, nominal inflation 30 s, dwell 10 min, cuff bias 3 and SD 5, heart-rate
and SpO2 segments 70, 71, 72, ...): none is a clinical value, none is a device specification
and none enters a prior file used by the builder. State independence: no test reads a
committed configuration in a way that depends on whether a human has filled it; the design
rows are exercised on copies under ``tmp_path`` in their filled and unfilled forms.

Statistical tolerances are derived from standard errors (test 4: mean within ``4 * sd /
sqrt(n)``, sample SD within ``4 * sd / sqrt(2 n)``), seeds are fixed, no test builds a
per-millisecond array, and the longest test builds 20 000 measurements.

Tie rule under test (stated in ``ralmon.benchmark.measurement``): samples and events are
sorted by ``t_rx_ms``; ties keep the generation order (samples: presence, cuff messages in
measurement order, ``hr_ecg``, ``spo2``, ``day_end``; events: schedule ticks, robot tasks,
measurements, dispenses, intakes).
"""

from __future__ import annotations

import ast
import copy
import dataclasses
import hashlib
import json
import math
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

import ralmon.benchmark as benchmark_pkg
import ralmon.benchmark.measurement as measurement_mod
import ralmon.benchmark.segments as segments_mod
from ralmon.benchmark import vocab
from ralmon.benchmark.latent import MAX_GRID_POINTS, T_DAY_MS
from ralmon.benchmark.measurement import (
    MAX_JITTER_DELAYS,
    MAX_JITTER_FILE_BYTES,
    MAX_LATENT_EVENTS,
    MAX_VISITS_PER_DAY,
    MAX_VITALS_SAMPLES,
    CuffModel,
    EmpiricalJitter,
    LatentSbpHold,
    MeasurementConfigError,
    MeasurementDesign,
    NoJitter,
    ObservedStream,
    assign_device_seq,
    build_observed_base,
    draw_clean_vitals,
    jitter_descriptor,
    load_measurement_design,
)
from ralmon.benchmark.priors import (
    SOURCE_TYPES,
    DeviceErrorModel,
    PriorConfigError,
    UnfilledParameterError,
    load_design_file,
)
from ralmon.benchmark.rng import StreamPurpose, stream
from ralmon.benchmark.schedule import Schedule
from ralmon.benchmark.segments import (
    MAX_DRAW_SAMPLES,
    MAX_INDEX_BYTES,
    MAX_SEGMENT_FILE_BYTES,
    MAX_SEGMENT_SAMPLES,
    MAX_SEGMENTS,
    MAX_TOTAL_SAMPLES,
    SEGMENT_KINDS,
    InlineSegment,
    SegmentEntry,
    SegmentError,
    SegmentIndex,
    SegmentIndexError,
    SegmentLibrary,
    SegmentUnavailableError,
)
from ralmon.benchmark.trace import LatentDay, ObservedDay
from ralmon.signals import Event, EventKind, Sample

ROOT = Path(__file__).resolve().parents[2]
DESIGN_FILE = ROOT / "configs" / "benchmark" / "generator_design.yaml"
SRC = ROOT / "src" / "ralmon" / "benchmark"

SEC = 1_000
MIN = 60_000
HOUR = 3_600_000
DAY = T_DAY_MS

DESIGN_ROWS = (
    "inflation_ms_nominal",
    "inflation_ms_sd",
    "pulse_error_sd_bpm",
    "robot_dwell_ms",
    "vitals_period_ms",
)
FIXTURE_NOTE = "FIXTURE-ONLY arithmetic of the test, not a source"

CUFF_SIGNALS = ("bp", "inflation_ms", "cuff_health", "hr_pulse")
IMPULSE_SIGNALS = ("meas", "dispense", "intake", "sched_tick")
SAMPLE_SIGNALS = {
    "bp",
    "inflation_ms",
    "cuff_health",
    "hr_pulse",
    "hr_ecg",
    "spo2",
    "presence",
    "day_end",
}

DESIGN = MeasurementDesign(
    inflation_ms_nominal=30 * SEC,
    inflation_ms_sd=0,
    pulse_error_sd_bpm=0.0,
    robot_dwell_ms=10 * MIN,
    vitals_period_ms=MIN,
    inflation_min_ms=30 * SEC,
)
ZERO_ERRORS = DeviceErrorModel(0.0, 0.0, 0.0, 0.0)
SCHED = Schedule(dose_ticks_ms=(), measurement_ticks_ms=(8 * HOUR, 20 * HOUR))
SCHED_BOTH = Schedule(
    dose_ticks_ms=(8 * HOUR, 20 * HOUR), measurement_ticks_ms=(9 * HOUR, 21 * HOUR)
)


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


def hr_values(n: int = DAY // MIN) -> list[float]:
    return [70.0 + i % 30 for i in range(n)]  # FIXTURE-ONLY: 70, 71, ..., 99, 70, ...


def spo2_values(n: int = DAY // MIN) -> list[float]:
    return [95.0 + i % 4 for i in range(n)]  # FIXTURE-ONLY


def inline_library(
    *, hr: Sequence[float] | None = None, spo2: Sequence[float] | None = None
) -> SegmentLibrary:
    return SegmentLibrary.from_memory(
        [
            InlineSegment("hr-1", "hr_clean", hr or hr_values(), MIN, "bpm"),
            InlineSegment("sp-1", "spo2_clean", spo2 or spo2_values(), MIN, "%"),
        ]
    )


LIB = inline_library()


def latent_day(
    sbp: float | None = 130.0,
    *,
    day_index: int = 0,
    step: int = MIN,
    ramp: float = 0.0,
    dispenses: Sequence[int] = (),
    intakes: Sequence[int] = (),
    extra_events: Sequence[Event] = (),
    patient_id: str = "p0000",
    seed: int = 0,
) -> LatentDay:
    start = day_index * DAY
    samples = tuple(
        Sample(
            "bp",
            start + k * step,
            start + k * step,
            (sbp or 0.0) + ramp * k,
            None,
            None,
        )
        for k in range(DAY // step)
    )
    events = [
        Event(EventKind.DISPENSE, t, t, "dispenser", {}, None) for t in dispenses
    ] + [Event(EventKind.INTAKE, t, t, "patient", {}, None) for t in intakes]
    events.extend(extra_events)
    events.sort(key=lambda e: e.t_device_ms)
    return LatentDay(patient_id, day_index, seed, samples, tuple(events))


_UNSET: Any = object()


def build(
    latent: Any = _UNSET,
    schedule: Schedule = SCHED,
    *,
    errors: DeviceErrorModel = ZERO_ERRORS,
    design: MeasurementDesign = DESIGN,
    jitter: Any = _UNSET,
    library: Any = _UNSET,
    seed: int = 0,
    patient_index: int = 0,
    care_plan_id: str = "plan-1",
    keep_latent_seed: bool = False,
    **kwargs: Any,
) -> ObservedStream:
    # the latent day of a test carries the seed of the build, as the builder's would
    # (a mismatch is refused: see test_build_refuses_a_seed_that_differs_from_the_latent_day)
    latent = latent_day(seed=seed) if latent is _UNSET else latent
    if isinstance(latent, LatentDay) and not keep_latent_seed:
        latent = dataclasses.replace(latent, seed=seed)
    return build_observed_base(
        latent,
        schedule,
        care_plan_id,
        errors,
        design,
        NoJitter() if jitter is _UNSET else jitter,
        LIB if library is _UNSET else library,
        seed,
        patient_index,
        **kwargs,
    )


def samples_of(stream_: ObservedStream, signal: str) -> list[Sample]:
    return [s for s in stream_.samples if s.signal == signal]


def events_of(stream_: ObservedStream, kind: EventKind) -> list[Event]:
    return [e for e in stream_.events if e.kind == kind]


def sha_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_jitter(tmp_path: Path, delays: Any, source: Any = "fixture run") -> Path:
    path = tmp_path / "jitter.json"
    path.write_text(json.dumps({"delays_ms": delays, "source": source}), "utf-8")
    return path


class DelayOne:
    """A jitter double that delays one measurement visit (what ``nav_delay`` will do)."""

    descriptor = "test-double"

    def __init__(self, index: int, delay: int) -> None:
        self.index, self.delay = index, delay

    def delay_ms(self, rng: np.random.Generator, *, kind: str, index: int) -> int:
        if kind == vocab.KIND_MEASUREMENT and index == self.index:
            return self.delay
        return 0


# ---------------------------------------------------------------------------
# Segment helpers
# ---------------------------------------------------------------------------


def write_segment(
    root: Path,
    relpath: str,
    values: Sequence[Any],
    quality: Sequence[Any] | None = None,
) -> str:
    """Write a segment file under ``root`` and return its sha256."""
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    body: dict[str, Any] = {"values": list(values)}
    if quality is not None:
        body["quality"] = list(quality)
    path.write_text(json.dumps(body), "utf-8")
    return sha_of(path)


def entry(sha: str, **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "segment_id": "s1",
        "dataset": "fixture-dataset",
        "record_id": "rec-1",
        "kind": "hr_clean",
        "sample_period_ms": MIN,
        "n_samples": 3,
        "unit": "bpm",
        "path": "hr/s1.json",
        "sha256": sha,
        "licence": "fixture-only",
    }
    base.update(over)
    return base


def write_index(root: Path, entries: Sequence[Any], **top: Any) -> Path:
    document: dict[str, Any] = {"schema_version": "0.1.0", "segments": list(entries)}
    document.update(top)
    path = root / "index.json"
    path.write_text(json.dumps(document), "utf-8")
    return path


def one_segment_library(tmp_path: Path, values: Sequence[float] = (70.0, 71.0, 72.0)):
    sha = write_segment(tmp_path, "hr/s1.json", values)
    index = write_index(tmp_path, [entry(sha, n_samples=len(values))])
    return SegmentLibrary(tmp_path, SegmentIndex.from_file(index))


def rng(seed: int = 0) -> np.random.Generator:
    return stream(seed, 0, 0, StreamPurpose.SEGMENTS, 0)


# ---------------------------------------------------------------------------
# 1. to 3. Schedule, arrival, cuff identity and bias
# ---------------------------------------------------------------------------


def test_measurement_times_follow_schedule_without_jitter() -> None:
    out = build()
    arrivals = [e.t_device_ms for e in events_of(out, EventKind.ROBOT_TASK)]
    assert arrivals == [8 * HOUR, 20 * HOUR]
    assert [v.arrival_ms for v in out.visits] == [8 * HOUR, 20 * HOUR]
    meas = events_of(out, EventKind.MEASUREMENT)
    assert [e.t_device_ms for e in meas] == [8 * HOUR + 30 * SEC, 20 * HOUR + 30 * SEC]
    bp = samples_of(out, "bp")
    assert [s.t_device_ms for s in bp] == [8 * HOUR + 30 * SEC, 20 * HOUR + 30 * SEC]
    assert [m.index for m in out.measurements] == [0, 1]
    ticks = events_of(out, EventKind.SCHEDULE_TICK)
    assert [e.t_device_ms for e in ticks] == [8 * HOUR, 20 * HOUR]
    assert all(e.payload == {vocab.KEY_KIND: vocab.KIND_MEASUREMENT} for e in ticks)


def test_zero_error_cuff_is_identity() -> None:
    out = build()
    assert [s.value for s in samples_of(out, "bp")] == [130.0, 130.0]
    assert all(m.value_mmhg == 130.0 and m.error_mmhg == 0.0 for m in out.measurements)


def test_cuff_bias_shifts_value() -> None:
    out = build(errors=DeviceErrorModel(0.0, 3.0, 0.0, 0.0))
    assert [s.value for s in samples_of(out, "bp")] == [133.0, 133.0]
    assert [m.latent_sbp_mmhg for m in out.measurements] == [130.0, 130.0]


def test_cuff_error_statistics() -> None:
    sd, bias, days, per_day = 5.0, 3.0, 20, 1_000  # FIXTURE-ONLY
    ticks = tuple(k * 86_000 for k in range(per_day))
    schedule = Schedule(dose_ticks_ms=(), measurement_ticks_ms=ticks)
    errors = []
    for day in range(days):
        out = build(
            latent_day(day_index=day, step=HOUR),
            schedule,
            errors=DeviceErrorModel(sd, bias, 0.0, 0.0),
            seed=0,
            library=SegmentLibrary.from_memory([]),
            allow_no_segments=True,
        )
        errors.extend(s.value - 130.0 for s in samples_of(out, "bp"))
    n = len(errors)
    assert n == 20_000
    mean = sum(errors) / n
    sample_sd = math.sqrt(sum((e - mean) ** 2 for e in errors) / (n - 1))
    assert abs(mean - bias) <= 4 * sd / math.sqrt(n)
    assert abs(sample_sd - sd) <= 4 * sd / math.sqrt(2 * n)


def test_cuff_model_is_gaussian_with_declared_family() -> None:
    model = CuffModel.from_device_errors(DeviceErrorModel(5.0, 3.0, 0.0, 0.0))
    assert model.family == "gaussian"
    assert model.reading(130.0, 0.0) == 133.0
    assert model.reading(130.0, 2.0) == 143.0
    assert CuffModel(0.0, 0.0).reading(130.0, 8.0) == 130.0


def test_cuff_noise_indexed_by_measurement_not_by_time() -> None:
    schedule = Schedule(
        dose_ticks_ms=(), measurement_ticks_ms=tuple(h * HOUR for h in range(6, 22, 3))
    )
    errors = DeviceErrorModel(5.0, 3.0, 0.0, 0.0)
    base = build(latent_day(ramp=0.01), schedule, errors=errors, seed=4)
    moved = build(
        latent_day(ramp=0.01), schedule, errors=errors, seed=4, jitter=DelayOne(2, HOUR)
    )
    assert (
        len(base.measurements)
        == len(moved.measurements)
        == len(schedule.measurement_ticks_ms)
    )
    for a, b in zip(base.measurements, moved.measurements, strict=True):
        assert a.error_mmhg == b.error_mmhg  # the draw follows the index, not the time
        assert a.inflation_ms == b.inflation_ms and a.pulse_bpm == b.pulse_bpm
    assert base.measurements[2].t_ms != moved.measurements[2].t_ms
    assert base.measurements[2].value_mmhg != moved.measurements[2].value_mmhg
    # the draw layout is the documented one: normals (cuff, inflation, pulse) of stream k
    z = stream(4, 0, 0, StreamPurpose.MEASUREMENT, 3).standard_normal(3)
    assert base.measurements[3].error_mmhg == pytest.approx(3.0 + 5.0 * z[0], rel=1e-12)


# ---------------------------------------------------------------------------
# 6. and 7. Arrival jitter
# ---------------------------------------------------------------------------


def test_empirical_jitter_uses_file_and_records_hash(tmp_path: Path) -> None:
    delays = [0, 60_000, 120_000]
    path = write_jitter(tmp_path, delays, "sim run 7")
    jitter = EmpiricalJitter(path)
    assert jitter_descriptor(jitter) == "file:" + sha_of(path)
    assert jitter.run_source == "sim run 7"
    ticks = tuple(range(0, 60 * 600_000, 600_000))
    schedule = Schedule(dose_ticks_ms=(), measurement_ticks_ms=ticks)
    out = build(
        schedule=schedule,
        jitter=jitter,
        library=SegmentLibrary.from_memory([]),
        allow_no_segments=True,
    )
    used = {v.delay_ms for v in out.visits}
    assert used == set(delays)
    assert all(v.arrival_ms == v.tick_ms + v.delay_ms for v in out.visits)
    assert out.settings["jitter_source"] == "file:" + sha_of(path)
    assert out.settings["jitter_run_source"] == "sim run 7"


def test_no_jitter_records_none_source(tmp_path: Path) -> None:
    assert jitter_descriptor(NoJitter()) == "none"
    out = build()
    assert out.settings["jitter_source"] == "none"
    assert all(v.delay_ms == 0 for v in out.visits)
    for bad in ([-1], [0, -60_000]):
        with pytest.raises(MeasurementConfigError):
            EmpiricalJitter(write_jitter(tmp_path, bad))


JITTER_BAD_DELAYS: list[Any] = [
    [],
    "0",
    {"a": 1},
    None,
    [True],
    [1.5],
    ["1"],
    [None],
    [[1]],
    [10**400],
    [T_DAY_MS + 1],
    [-(10**400)],
]


@pytest.mark.parametrize("delays", JITTER_BAD_DELAYS)
def test_jitter_file_rejects_bad_delays(tmp_path: Path, delays: Any) -> None:
    with pytest.raises(MeasurementConfigError):
        EmpiricalJitter(write_jitter(tmp_path, delays))


@pytest.mark.parametrize("source", [None, "", 5, ["a"], " "])
def test_jitter_file_rejects_bad_source(tmp_path: Path, source: Any) -> None:
    with pytest.raises(MeasurementConfigError):
        EmpiricalJitter(write_jitter(tmp_path, [0], source))


def test_jitter_file_malformed_missing_and_oversized(tmp_path: Path) -> None:
    def raw(name: str, data: bytes) -> Path:
        path = tmp_path / name
        path.write_bytes(data)
        return path

    bad_files = [
        raw("empty.json", b""),
        raw("notjson.json", b"{not json"),
        raw("list.json", b"[1, 2]"),
        raw("nan.json", b'{"delays_ms": [NaN], "source": "x"}'),
        raw("inf.json", b'{"delays_ms": [Infinity], "source": "x"}'),
        raw("big.json", b'{"delays_ms": [1e999], "source": "x"}'),
        raw("badutf.json", b"\xff\xfe\x00"),
        raw("deep.json", b"[" * 100_000),
        raw("nokey.json", b'{"source": "x"}'),
        raw("nosource.json", b'{"delays_ms": [0]}'),
        tmp_path,  # a directory
        tmp_path / "missing.json",
    ]
    for path in bad_files:
        with pytest.raises(MeasurementConfigError):
            EmpiricalJitter(path)
    oversized = tmp_path / "oversized.json"
    with oversized.open("wb") as handle:
        handle.truncate(MAX_JITTER_FILE_BYTES + 1)
    with pytest.raises(MeasurementConfigError):
        EmpiricalJitter(oversized)
    too_many = write_jitter(tmp_path, [0] * (MAX_JITTER_DELAYS + 1))
    assert too_many.stat().st_size < MAX_JITTER_FILE_BYTES
    with pytest.raises(MeasurementConfigError):
        EmpiricalJitter(too_many)
    at_limit = write_jitter(tmp_path, [0] * MAX_JITTER_DELAYS)
    assert len(EmpiricalJitter(at_limit).delays_ms) == MAX_JITTER_DELAYS


@pytest.mark.parametrize("path", [None, 5, b"x", 1.5, ["a"], "a\0b", object()])
def test_jitter_path_types(path: Any) -> None:
    with pytest.raises(MeasurementConfigError):
        EmpiricalJitter(path)


def test_jitter_symlink_to_file_is_followed_and_hashed(tmp_path: Path) -> None:
    target = write_jitter(tmp_path, [0, 1])
    link = tmp_path / "link.json"
    link.symlink_to(target)
    assert EmpiricalJitter(link).file_sha256 == sha_of(target)


def test_jitter_model_double_is_validated(tmp_path: Path) -> None:
    class Negative:
        descriptor = "neg"

        def delay_ms(self, rng: np.random.Generator, *, kind: str, index: int) -> Any:
            return -1

    class Weird:
        descriptor = "weird"

        def __init__(self, value: Any) -> None:
            self.value = value

        def delay_ms(self, rng: np.random.Generator, *, kind: str, index: int) -> Any:
            return self.value

    class NoDescriptor:
        def delay_ms(self, rng: np.random.Generator, *, kind: str, index: int) -> int:
            return 0

    for bad in (
        Negative(),
        Weird(True),
        Weird(1.5),
        Weird(None),
        Weird(10**400),
        Weird(T_DAY_MS + 1),
        Weird("1"),
        NoDescriptor(),
        object(),
        "none",
    ):
        with pytest.raises(MeasurementConfigError):
            build(jitter=bad)
    with pytest.raises(MeasurementConfigError):
        jitter_descriptor(NoDescriptor())  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 8. Observed base signals and order
# ---------------------------------------------------------------------------


def test_observed_base_signals_and_order() -> None:
    out = build(latent_day(), SCHED_BOTH, errors=DeviceErrorModel(0.0, 3.0, 0.0, 0.0))
    signals = {s.signal for s in out.samples}
    assert signals <= SAMPLE_SIGNALS
    assert not signals & set(IMPULSE_SIGNALS)
    assert signals == SAMPLE_SIGNALS  # a library is given, so every signal occurs
    n_meas = len(SCHED_BOTH.measurement_ticks_ms)
    for name in CUFF_SIGNALS:
        assert len(samples_of(out, name)) == n_meas
    assert len(events_of(out, EventKind.MEASUREMENT)) == n_meas
    assert all(s.value == 1.0 for s in samples_of(out, "cuff_health"))
    assert all(s.quality is None for s in out.samples)
    assert samples_of(out, "hr_pulse")[0].value == hr_values()[9 * 60]
    ends = samples_of(out, "day_end")
    assert [(s.t_device_ms, s.value) for s in ends] == [
        (DAY, 1.0)
    ]  # WS01-T01 section 5.5
    for items in (out.samples, out.events):
        assert all(a.t_rx_ms <= b.t_rx_ms for a, b in pairwise(items))
        assert all(i.t_rx_ms == i.t_device_ms for i in items)
    assert all(s.seq is None for s in out.samples) and all(
        e.seq is None for e in out.events
    )
    assert (
        out.patient_id == "p0000"
        and out.day_index == 0
        and out.care_plan_id == "plan-1"
    )
    kinds = {e.kind for e in out.events}
    assert kinds <= {
        EventKind.SCHEDULE_TICK,
        EventKind.ROBOT_TASK,
        EventKind.MEASUREMENT,
        EventKind.DISPENSE,
        EventKind.INTAKE,
    }
    # every measurement group shares one instant: samples and the event
    for m in out.measurements:
        group = [
            s
            for s in out.samples
            if s.signal in CUFF_SIGNALS and s.t_device_ms == m.t_ms
        ]
        assert len(group) == len(CUFF_SIGNALS)


def test_no_sample_stream_carries_an_impulse_signal_for_events() -> None:
    out = build(
        latent_day(dispenses=[8 * HOUR], intakes=[8 * HOUR + 5 * SEC]), SCHED_BOTH
    )
    assert not {s.signal for s in out.samples} & set(IMPULSE_SIGNALS)


# ---------------------------------------------------------------------------
# 9. to 12. Dispense, witnessed intake, presence
# ---------------------------------------------------------------------------

DOSE_SCHED = Schedule(dose_ticks_ms=(8 * HOUR, 20 * HOUR), measurement_ticks_ms=())


def test_dispense_events_pass_through_from_latent() -> None:
    times = [8 * HOUR + 7 * SEC, 20 * HOUR + 11 * MIN]
    latent = latent_day(dispenses=times)
    out = build(latent, DOSE_SCHED)
    disp = events_of(out, EventKind.DISPENSE)
    assert [e.t_device_ms for e in disp] == times
    assert all(e.t_rx_ms == e.t_device_ms for e in disp)
    assert all(e.source == vocab.SOURCE_DISPENSER for e in disp)
    for e in disp:
        assert set(e.payload) <= vocab.PAYLOAD_KEYS[EventKind.DISPENSE]
        vocab.check_payload(e.kind, e.payload)


def test_dispense_source_is_not_copied_from_latent() -> None:
    odd = Event(EventKind.DISPENSE, 8 * HOUR, 8 * HOUR, "latent-secret", {"k": 1}, 7)
    out = build(latent_day(extra_events=[odd]), DOSE_SCHED)
    (e,) = events_of(out, EventKind.DISPENSE)
    assert (
        e.source == vocab.SOURCE_DISPENSER and dict(e.payload) == {} and e.seq is None
    )


def test_intake_witnessed_only_during_robot_visit() -> None:
    inside = 8 * HOUR + 65 * SEC
    outside = 20 * HOUR + 10 * MIN + 1  # one ms after the dwell of the 20:00 visit
    latent = latent_day(
        dispenses=[8 * HOUR + 60 * SEC, 20 * HOUR + 10 * MIN - SEC],
        intakes=[inside, outside],
    )
    out = build(latent, DOSE_SCHED)
    intakes = events_of(out, EventKind.INTAKE)
    assert [e.t_device_ms for e in intakes] == [inside]
    assert intakes[0].source == vocab.SOURCE_ROBOT and dict(intakes[0].payload) == {}
    # without any visit that covers it, nothing is witnessed
    empty = build(latent, Schedule(dose_ticks_ms=(), measurement_ticks_ms=()))
    assert events_of(empty, EventKind.INTAKE) == []


@pytest.mark.parametrize(
    ("offset", "witnessed"),
    [
        (-1, False),  # one ms before the arrival
        (0, True),  # the arrival instant: closed at the lower end
        (10 * MIN - 1, True),
        (10 * MIN, True),  # the departure instant: closed at the upper end
        (10 * MIN + 1, False),
    ],
)
def test_witness_window_is_closed_at_both_ends(offset: int, witnessed: bool) -> None:
    t = 8 * HOUR + offset
    out = build(
        latent_day(intakes=[t]),
        Schedule(dose_ticks_ms=(8 * HOUR,), measurement_ticks_ms=()),
    )
    assert (len(events_of(out, EventKind.INTAKE)) == 1) is witnessed


def test_witness_window_follows_the_jittered_arrival() -> None:
    class Late:
        descriptor = "late"

        def delay_ms(self, rng: np.random.Generator, *, kind: str, index: int) -> int:
            return 5 * MIN

    t = 8 * HOUR + 12 * MIN  # outside [08:00, 08:10], inside [08:05, 08:15]
    sched = Schedule(dose_ticks_ms=(8 * HOUR,), measurement_ticks_ms=())
    assert (
        len(
            events_of(
                build(latent_day(intakes=[t]), sched, jitter=Late()), EventKind.INTAKE
            )
        )
        == 1
    )
    assert events_of(build(latent_day(intakes=[t]), sched), EventKind.INTAKE) == []


def test_presence_sample_only_during_visit_no_zeros() -> None:
    out = build(latent_day(), SCHED_BOTH)
    presence = samples_of(out, "presence")
    assert [s.t_device_ms for s in presence] == sorted(v.arrival_ms for v in out.visits)
    assert len(presence) == len(out.visits) == 4
    assert all(s.value == 1.0 for s in presence)
    assert not [s for s in out.samples if s.signal == "presence" and s.value == 0.0]
    # a schedule with no tick has no visit and no presence sample at all
    nothing = build(latent_day(), Schedule(dose_ticks_ms=(), measurement_ticks_ms=()))
    assert samples_of(nothing, "presence") == [] and nothing.visits == ()


def test_delayed_dose_outside_visit_is_not_witnessed() -> None:
    late = 8 * HOUR + 15 * MIN  # beyond the dwell of the 08:00 visit
    latent = latent_day(dispenses=[late], intakes=[late + 5 * SEC])
    out = build(latent, Schedule(dose_ticks_ms=(8 * HOUR,), measurement_ticks_ms=()))
    assert [e.t_device_ms for e in events_of(out, EventKind.DISPENSE)] == [late]
    assert events_of(out, EventKind.INTAKE) == []
    assert [s.t_device_ms for s in samples_of(out, "presence")] == [8 * HOUR]


def test_every_visit_emits_one_navigate_success_task() -> None:
    out = build(latent_day(), SCHED_BOTH)
    tasks = events_of(out, EventKind.ROBOT_TASK)
    assert len(tasks) == len(out.visits)
    for event, visit in zip(
        tasks, sorted(out.visits, key=lambda v: v.arrival_ms), strict=True
    ):
        assert (
            event.source == vocab.SOURCE_ROBOT and event.t_device_ms == visit.arrival_ms
        )
        assert dict(event.payload) == {
            vocab.KEY_TASK: vocab.TASK_NAVIGATE,
            vocab.KEY_OUTCOME: vocab.OUTCOME_SUCCESS,
            vocab.KEY_PATIENT_ID: "p0000",
        }
    kinds = [v.kind for v in out.visits]
    assert kinds == [vocab.KIND_DOSE, vocab.KIND_MEASUREMENT] * 2


# ---------------------------------------------------------------------------
# 13. and 14. Heart rate and SpO2 from segments
# ---------------------------------------------------------------------------


def test_hr_spo2_from_segments_with_ids_recorded() -> None:
    out = build(latent_day(day_index=3), SCHED)
    start = 3 * DAY
    hr = samples_of(out, "hr_ecg")
    sp = samples_of(out, "spo2")
    assert [s.t_device_ms for s in hr] == [start + j * MIN for j in range(DAY // MIN)]
    assert [s.value for s in hr] == hr_values()
    assert [s.value for s in sp] == spo2_values()
    assert out.settings["segment_ids"] == {"hr_clean": ["hr-1"], "spo2_clean": ["sp-1"]}
    assert out.settings["join_count"] == {"hr_clean": 0, "spo2_clean": 0}
    assert out.settings["segment_source"] == LIB.descriptor != "none"
    # the cuff pulse follows the same clean heart rate (no error: SD 0) at the reading instant
    for m in out.measurements:
        j = (m.t_ms - start) // MIN
        assert m.pulse_bpm == hr_values()[j]
    assert [s.value for s in samples_of(out, "hr_pulse")] == [
        m.pulse_bpm for m in out.measurements
    ]


def test_vitals_period_other_than_segment_period_uses_hold() -> None:
    hr = [70.0, 71.0, 72.0, 73.0] * (DAY // (4 * 15 * MIN))
    library = SegmentLibrary.from_memory(
        [
            InlineSegment("hr-q", "hr_clean", hr, 15 * MIN, "bpm"),
            InlineSegment("sp-q", "spo2_clean", [96.0], DAY, "%"),
        ]
    )
    design = dataclasses.replace(DESIGN, vitals_period_ms=5 * MIN)
    out = build(design=design, library=library)
    vals = [s.value for s in samples_of(out, "hr_ecg")]
    assert len(vals) == DAY // (5 * MIN)
    assert vals[:7] == [70.0, 70.0, 70.0, 71.0, 71.0, 71.0, 72.0]
    assert {s.value for s in samples_of(out, "spo2")} == {96.0}


def test_missing_segments_error_unless_allowed(tmp_path: Path) -> None:
    empty = SegmentLibrary(tmp_path, SegmentIndex(()))
    with pytest.raises(SegmentUnavailableError):
        build(library=empty)
    out = build(library=empty, allow_no_segments=True)
    assert out.settings["segment_source"] == "none"
    assert not {s.signal for s in out.samples} & {"hr_ecg", "spo2", "hr_pulse"}
    assert out.settings["segment_ids"] == {"hr_clean": [], "spo2_clean": []}
    assert len(samples_of(out, "bp")) == 2  # the pressure path does not need segments
    # a library that lacks one kind: error, or that kind alone is omitted
    only_hr = SegmentLibrary.from_memory(
        [InlineSegment("h", "hr_clean", hr_values(), MIN, "bpm")]
    )
    with pytest.raises(SegmentUnavailableError):
        build(library=only_hr)
    partial = build(library=only_hr, allow_no_segments=True)
    assert (
        samples_of(partial, "spo2") == []
        and len(samples_of(partial, "hr_ecg")) == DAY // MIN
    )
    assert partial.settings["segment_source"] == only_hr.descriptor != "none"
    assert partial.settings["segment_ids"] == {"hr_clean": ["h"], "spo2_clean": []}


def test_segments_too_short_are_joined_and_counted() -> None:
    library = SegmentLibrary.from_memory(
        [
            InlineSegment("a", "hr_clean", [70.0] * 600, MIN, "bpm"),
            InlineSegment("b", "hr_clean", [80.0] * 600, MIN, "bpm"),
            InlineSegment("sp", "spo2_clean", spo2_values(), MIN, "%"),
        ]
    )
    out = build(library=library)
    ids = out.settings["segment_ids"]["hr_clean"]  # type: ignore[index]
    joins = out.settings["join_count"]["hr_clean"]  # type: ignore[index]
    assert len(ids) == joins + 1 and joins >= 2
    assert len(samples_of(out, "hr_ecg")) == DAY // MIN


def test_draw_clean_vitals_is_a_pure_function_of_the_key() -> None:
    a = draw_clean_vitals(LIB, DESIGN, 5, 2, 3)
    b = draw_clean_vitals(LIB, DESIGN, 5, 2, 3)
    assert a == b and a.hr_bpm is not None and len(a.hr_bpm) == DAY // MIN
    assert (
        draw_clean_vitals(LIB, DESIGN, 5, 2, 4).segment_ids == a.segment_ids
    )  # one segment
    two = SegmentLibrary.from_memory(
        [InlineSegment(f"h{k}", "hr_clean", hr_values(), MIN, "bpm") for k in range(8)]
        + [InlineSegment("sp", "spo2_clean", spo2_values(), MIN, "%")]
    )
    picks = {
        draw_clean_vitals(two, DESIGN, 5, 2, d).segment_ids["hr_clean"]
        for d in range(30)
    }
    assert len(picks) > 1  # the segment varies with the day


# ---------------------------------------------------------------------------
# 15. and 16. Segment index, hashes, path confinement
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = (
    "segment_id",
    "dataset",
    "record_id",
    "kind",
    "sample_period_ms",
    "n_samples",
    "unit",
    "path",
    "sha256",
    "licence",
)


@pytest.mark.parametrize("field", REQUIRED_FIELDS)
def test_segment_index_requires_provenance_fields(tmp_path: Path, field: str) -> None:
    sha = write_segment(tmp_path, "hr/s1.json", [70.0, 71.0, 72.0])
    broken = entry(sha)
    del broken[field]
    with pytest.raises(SegmentIndexError):
        SegmentIndex.from_file(write_index(tmp_path, [broken]))
    with pytest.raises(SegmentIndexError):
        SegmentIndex.from_mapping({"schema_version": "0.1.0", "segments": [broken]})
    assert (
        SegmentIndex.from_file(write_index(tmp_path, [entry(sha)])).entries[0].licence
    )


@pytest.mark.parametrize(
    "field", ("dataset", "record_id", "licence", "unit", "segment_id", "sha256", "path")
)
@pytest.mark.parametrize("value", [None, "", " ", 5, True, ["a"]])
def test_segment_entry_text_fields_are_validated(
    tmp_path: Path, field: str, value: Any
) -> None:
    sha = write_segment(tmp_path, "hr/s1.json", [70.0, 71.0, 72.0])
    with pytest.raises(SegmentIndexError):
        SegmentIndex.from_mapping(
            {"schema_version": "0.1.0", "segments": [entry(sha, **{field: value})]}
        )


@pytest.mark.parametrize("field", ("sample_period_ms", "n_samples"))
@pytest.mark.parametrize(
    "value",
    [None, 0, -1, True, 1.5, "3", 10**400, float("nan"), MAX_SEGMENT_SAMPLES + 1],
)
def test_segment_entry_integers_are_validated(
    tmp_path: Path, field: str, value: Any
) -> None:
    sha = write_segment(tmp_path, "hr/s1.json", [70.0, 71.0, 72.0])
    if field == "sample_period_ms" and value == MAX_SEGMENT_SAMPLES + 1:
        return  # a long period is valid
    with pytest.raises(SegmentIndexError):
        SegmentIndex.from_mapping(
            {"schema_version": "0.1.0", "segments": [entry(sha, **{field: value})]}
        )


@pytest.mark.parametrize("kind", [None, "", "hr", "HR_CLEAN", 3, "hr_clean "])
def test_segment_entry_kind_must_be_known(tmp_path: Path, kind: Any) -> None:
    sha = write_segment(tmp_path, "hr/s1.json", [70.0, 71.0, 72.0])
    with pytest.raises(SegmentIndexError):
        SegmentIndex.from_mapping(
            {"schema_version": "0.1.0", "segments": [entry(sha, kind=kind)]}
        )
    assert set(SEGMENT_KINDS) == {"hr_clean", "spo2_clean", "hr_error_ecg_noise"}


@pytest.mark.parametrize("sha", ["abc", "G" * 64, "A" * 64, "0" * 63, "0" * 65, 5])
def test_segment_entry_sha256_format(sha: Any) -> None:
    with pytest.raises(SegmentIndexError):
        SegmentIndex.from_mapping({"schema_version": "0.1.0", "segments": [entry(sha)]})


def test_segment_index_top_level_and_duplicates(tmp_path: Path) -> None:
    sha = write_segment(tmp_path, "hr/s1.json", [70.0, 71.0, 72.0])
    good = entry(sha)
    for document in (
        [],
        None,
        "x",
        {"segments": [good]},
        {"schema_version": "9", "segments": [good]},
        {"schema_version": "0.1.0"},
        {"schema_version": "0.1.0", "segments": "x"},
        {"schema_version": "0.1.0", "segments": [good], "extra": 1},
        {"schema_version": "0.1.0", "segments": [good, good]},  # duplicate id
        {"schema_version": "0.1.0", "segments": [None]},
        {"schema_version": "0.1.0", "segments": [dict(good, extra=1)]},
        {"schema_version": "0.1.0", "segments": [good] * (MAX_SEGMENTS + 1)},
        {
            "schema_version": "0.1.0",
            "segments": [dict(good, segment_id="s2", sample_period_ms=2 * MIN)]
            + [good],
        },  # mixed periods in a kind
    ):
        with pytest.raises(SegmentIndexError):
            SegmentIndex.from_mapping(document)  # type: ignore[arg-type]
    assert (
        len(
            SegmentIndex.from_mapping(
                {"schema_version": "0.1.0", "segments": []}
            ).entries
        )
        == 0
    )


def test_segment_index_file_problems(tmp_path: Path) -> None:
    def raw(name: str, data: bytes) -> Path:
        path = tmp_path / name
        path.write_bytes(data)
        return path

    for path in (
        raw("bad.json", b"{oops"),
        raw("nan.json", b'{"schema_version": "0.1.0", "segments": [NaN]}'),
        raw("utf.json", b"\xff\xfe"),
        raw("deep.json", b"[" * 100_000),
        tmp_path,
        tmp_path / "missing.json",
    ):
        with pytest.raises(SegmentIndexError):
            SegmentIndex.from_file(path)
    huge = tmp_path / "huge.json"
    with huge.open("wb") as handle:
        handle.truncate(MAX_INDEX_BYTES + 1)
    with pytest.raises(SegmentIndexError):
        SegmentIndex.from_file(huge)
    for bad in (None, 5, b"x", ["a"], "a\0b", object()):
        with pytest.raises(SegmentIndexError):
            SegmentIndex.from_file(bad)  # type: ignore[arg-type]


def test_segment_hash_mismatch_is_refused(tmp_path: Path) -> None:
    sha = write_segment(tmp_path, "hr/s1.json", [70.0, 71.0, 72.0])
    index = SegmentIndex.from_file(write_index(tmp_path, [entry(sha)]))
    assert SegmentLibrary(tmp_path, index).draw("hr_clean", 3, rng()).values == (
        70.0,
        71.0,
        72.0,
    )
    (tmp_path / "hr" / "s1.json").write_text(
        json.dumps({"values": [70.0, 71.0, 73.0]}), "utf-8"
    )
    with pytest.raises(SegmentIndexError):
        SegmentLibrary(tmp_path, index)
    # changed after the library was built: the draw verifies again
    sha2 = write_segment(tmp_path, "hr/s1.json", [70.0, 71.0, 72.0])
    library = SegmentLibrary(
        tmp_path, SegmentIndex.from_file(write_index(tmp_path, [entry(sha2)]))
    )
    (tmp_path / "hr" / "s1.json").write_text(
        json.dumps({"values": [1.0, 1.0, 1.0]}), "utf-8"
    )
    with pytest.raises(SegmentIndexError):
        library.draw("hr_clean", 3, rng())


@pytest.mark.parametrize(
    "path",
    [
        "../x.json",
        "hr/../../x.json",
        "..",
        "hr/..",
        "/etc/passwd",
        "/abs/s1.json",
        "C:/x.json",
        "C:\\x.json",
        "\\\\host\\share\\x.json",
        "hr\\s1.json",
        "",
        ".",
        "hr/",
        "a\0b",
    ],
)
def test_segment_paths_confined_to_root(tmp_path: Path, path: str) -> None:
    sha = write_segment(tmp_path, "hr/s1.json", [70.0, 71.0, 72.0])
    with pytest.raises(SegmentIndexError):
        SegmentIndex.from_mapping(
            {"schema_version": "0.1.0", "segments": [entry(sha, path=path)]}
        )


def test_segment_symlink_escaping_root_and_missing_or_directory(tmp_path: Path) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps({"values": [70.0, 71.0, 72.0]}), "utf-8")
    (root / "hr").mkdir(parents=True)
    (root / "hr" / "link.json").symlink_to(outside)
    (root / "dir.json").mkdir()
    index = SegmentIndex.from_mapping(
        {
            "schema_version": "0.1.0",
            "segments": [entry(sha_of(outside), path="hr/link.json")],
        }
    )
    with pytest.raises(SegmentIndexError):
        SegmentLibrary(root, index)
    as_dir = SegmentIndex.from_mapping(
        {
            "schema_version": "0.1.0",
            "segments": [entry(sha_of(outside), path="dir.json")],
        }
    )
    with pytest.raises(SegmentIndexError):
        SegmentLibrary(root, as_dir)
    missing = SegmentIndex.from_mapping(
        {
            "schema_version": "0.1.0",
            "segments": [entry(sha_of(outside), path="nope.json")],
        }
    )
    with pytest.raises(SegmentIndexError):
        SegmentLibrary(root, missing)
    # a symlink that stays inside the root is accepted
    sha = write_segment(root, "hr/real.json", [70.0, 71.0, 72.0])
    (root / "hr" / "alias.json").symlink_to(root / "hr" / "real.json")
    ok = SegmentIndex.from_mapping(
        {"schema_version": "0.1.0", "segments": [entry(sha, path="hr/alias.json")]}
    )
    assert SegmentLibrary(root, ok).draw("hr_clean", 3, rng()).values == (
        70.0,
        71.0,
        72.0,
    )


@pytest.mark.parametrize(
    "root", [None, 5, b"x", ["a"], "a\0b", object(), "missing-dir"]
)
def test_library_root_is_validated(tmp_path: Path, root: Any) -> None:
    if root == "missing-dir":
        root = tmp_path / "missing-dir"
    with pytest.raises(SegmentIndexError):
        SegmentLibrary(root, SegmentIndex(()))
    file_root = tmp_path / "f"
    file_root.write_text("x", "utf-8")
    with pytest.raises(SegmentIndexError):
        SegmentLibrary(file_root, SegmentIndex(()))
    with pytest.raises(SegmentIndexError):
        SegmentLibrary(tmp_path, "index")  # type: ignore[arg-type]


SEGMENT_FILE_BODIES: list[Any] = [
    b"",
    b"{oops",
    b"[1, 2, 3]",
    b'{"values": "abc"}',
    b'{"values": [1, 2]}',  # n_samples is 3
    b'{"values": [1, 2, 3, 4]}',
    b'{"values": [1, 2, true]}',
    b'{"values": [1, 2, null]}',
    b'{"values": [1, 2, "3"]}',
    b'{"values": [1, 2, NaN]}',
    b'{"values": [1, 2, Infinity]}',
    b'{"values": [1, 2, 1e999]}',
    b'{"values": [1, 2, 1' + b"0" * 400 + b"]}",
    b'{"values": [1, 2, 3], "extra": 1}',
    b'{"values": [1, 2, 3], "quality": [0.5, 0.5]}',
    b'{"values": [1, 2, 3], "quality": [0.5, 0.5, 1.5]}',
    b'{"values": [1, 2, 3], "quality": [0.5, 0.5, true]}',
    b'{"values": [1, 2, 3], "quality": "x"}',
    b"\xff\xfe",
]


@pytest.mark.parametrize("body", SEGMENT_FILE_BODIES)
def test_segment_file_contents_are_validated(tmp_path: Path, body: bytes) -> None:
    path = tmp_path / "hr" / "s1.json"
    path.parent.mkdir()
    path.write_bytes(body)
    index = SegmentIndex.from_mapping(
        {"schema_version": "0.1.0", "segments": [entry(sha_of(path))]}
    )
    with pytest.raises(SegmentIndexError):
        library = SegmentLibrary(tmp_path, index)
        library.draw("hr_clean", 1, rng())


def test_segment_file_size_bound(tmp_path: Path) -> None:
    path = tmp_path / "hr" / "s1.json"
    path.parent.mkdir()
    with path.open("wb") as handle:
        handle.truncate(MAX_SEGMENT_FILE_BYTES + 1)
    index = SegmentIndex.from_mapping(
        {"schema_version": "0.1.0", "segments": [entry(sha_of(path))]}
    )
    with pytest.raises(SegmentIndexError):
        SegmentLibrary(tmp_path, index)


def test_segment_quality_is_carried(tmp_path: Path) -> None:
    sha = write_segment(
        tmp_path, "hr/s1.json", [5.0, -3.0, 8.0], quality=[0.5, 0.25, 1.0]
    )
    index = write_index(tmp_path, [entry(sha, kind="hr_error_ecg_noise")])
    draw = SegmentLibrary(tmp_path, SegmentIndex.from_file(index)).draw(
        "hr_error_ecg_noise", 3, rng()
    )
    assert draw.values == (5.0, -3.0, 8.0) and draw.quality == (0.5, 0.25, 1.0)
    other = tmp_path / "other"
    other.mkdir()
    assert one_segment_library(other).draw("hr_clean", 2, rng()).quality is None


# ---------------------------------------------------------------------------
# Segment draws
# ---------------------------------------------------------------------------


def test_draw_prefers_long_enough_segments_and_counts_joins() -> None:
    library = SegmentLibrary.from_memory(
        [
            InlineSegment("short1", "hr_clean", [1.0, 2.0], MIN, "bpm"),
            InlineSegment("short2", "hr_clean", [3.0, 4.0], MIN, "bpm"),
            InlineSegment(
                "long", "hr_clean", [10.0, 11.0, 12.0, 13.0, 14.0], MIN, "bpm"
            ),
        ]
    )
    starts = set()
    for seed in range(20):
        draw = library.draw("hr_clean", 4, rng(seed))
        assert draw.segment_ids == ("long",) and draw.join_count == 0
        assert draw.values in ((10.0, 11.0, 12.0, 13.0), (11.0, 12.0, 13.0, 14.0))
        starts.add(draw.values[0])
    assert starts == {10.0, 11.0}  # the offset is drawn
    # the segment choice and the offset come from independent draws
    pair = SegmentLibrary.from_memory(
        [
            InlineSegment("a", "hr_clean", [1.0, 2.0, 3.0, 4.0, 5.0], MIN, "bpm"),
            InlineSegment("b", "hr_clean", [6.0, 7.0, 8.0, 9.0, 10.0], MIN, "bpm"),
        ]
    )
    combos = {
        (d.segment_ids, d.values[0])
        for d in (pair.draw("hr_clean", 4, rng(seed)) for seed in range(60))
    }
    assert len(combos) == 4
    for seed in range(20):
        joined = library.draw("hr_clean", 8, rng(seed))
        assert (
            len(joined.values) == 8 and joined.join_count == len(joined.segment_ids) - 1
        )
        assert joined.join_count >= 1
    exact = library.draw("hr_clean", 5, rng(0))
    assert exact.segment_ids == ("long",) and exact.join_count == 0
    one = library.draw("hr_clean", 1, rng(0))
    assert len(one.values) == 1 and one.join_count == 0
    assert library.draw("hr_clean", 4, rng(3)) == library.draw("hr_clean", 4, rng(3))
    assert library.sample_period_ms("hr_clean") == MIN and library.has_kind("hr_clean")
    assert not library.has_kind("spo2_clean")


@pytest.mark.parametrize(
    "n", [0, -1, True, 1.5, "3", None, 10**400, MAX_DRAW_SAMPLES + 1]
)
def test_draw_rejects_bad_sample_counts(n: Any) -> None:
    with pytest.raises(SegmentUnavailableError):
        LIB.draw("hr_clean", n, rng())


@pytest.mark.parametrize("kind", [None, "", "nope", 3, "spo2_clean_"])
def test_draw_rejects_unknown_or_absent_kinds(kind: Any) -> None:
    with pytest.raises(SegmentUnavailableError):
        LIB.draw(kind, 1, rng())
    with pytest.raises(SegmentUnavailableError):
        LIB.draw("hr_error_ecg_noise", 1, rng())  # a known kind with no segment
    with pytest.raises(SegmentUnavailableError):
        LIB.sample_period_ms("hr_error_ecg_noise")


@pytest.mark.parametrize("bad", [None, 0, "rng", np.random.RandomState(0), object()])
def test_draw_requires_a_generator(bad: Any) -> None:
    with pytest.raises(SegmentUnavailableError):
        LIB.draw("hr_clean", 1, bad)


def test_segment_errors_share_a_base() -> None:
    assert issubclass(SegmentIndexError, SegmentError)
    assert issubclass(SegmentUnavailableError, SegmentError)
    assert issubclass(SegmentError, ValueError)
    assert issubclass(MeasurementConfigError, ValueError)


def test_inline_library_validation() -> None:
    for bad in (
        [InlineSegment("a", "hr_clean", [], MIN, "bpm")],
        [InlineSegment("a", "hr_clean", [float("nan")], MIN, "bpm")],
        [InlineSegment("a", "nope", [1.0], MIN, "bpm")],
        [InlineSegment("a", "hr_clean", [1.0], 0, "bpm")],
        [
            InlineSegment("a", "hr_clean", [1.0], MIN, "bpm"),
            InlineSegment("a", "hr_clean", [1.0], MIN, "bpm"),
        ],
        [InlineSegment("a", "hr_clean", [1.0], MIN, "bpm", quality=[0.5, 0.5])],
        [InlineSegment("a", "hr_clean", [1.0], MIN, "bpm", quality=[2.0])],
        ["x"],
        None,
    ):
        with pytest.raises(SegmentIndexError):
            SegmentLibrary.from_memory(bad)  # type: ignore[arg-type]


def test_library_descriptor_depends_on_the_index_only(tmp_path: Path) -> None:
    sha = write_segment(tmp_path, "hr/s1.json", [70.0, 71.0, 72.0])
    a = SegmentLibrary(
        tmp_path, SegmentIndex.from_file(write_index(tmp_path, [entry(sha)]))
    )
    b = SegmentLibrary(
        tmp_path, SegmentIndex.from_file(write_index(tmp_path, [entry(sha)]))
    )
    c = SegmentLibrary(
        tmp_path,
        SegmentIndex.from_file(write_index(tmp_path, [entry(sha, licence="other")])),
    )
    assert a.descriptor == b.descriptor != c.descriptor
    assert SegmentLibrary(tmp_path, SegmentIndex(())).descriptor == "none"


# ---------------------------------------------------------------------------
# 17. The latent day is read, never changed
# ---------------------------------------------------------------------------


def test_latent_day_not_mutated() -> None:
    event = Event(
        EventKind.INTAKE, 8 * HOUR + SEC, 8 * HOUR + SEC, "patient", {"a": 1}, None
    )
    latent = latent_day(dispenses=[8 * HOUR], extra_events=[event])
    snapshot = copy.deepcopy(latent)
    payloads = [id(e.payload) for e in latent.events]
    out = build(latent, DOSE_SCHED)
    assert latent == snapshot
    assert repr(latent) == repr(snapshot)
    assert [id(e.payload) for e in latent.events] == payloads
    # the observed payloads are fresh objects: editing them cannot reach the latent day
    for observed in out.events:
        assert all(observed.payload is not e.payload for e in latent.events)
    # list-backed members are not reordered or edited either
    listed = LatentDay("p0000", 0, 0, list(latent.samples), list(latent.events))  # type: ignore[arg-type]
    before = copy.deepcopy(listed)
    build(listed, DOSE_SCHED)
    assert listed == before and isinstance(listed.samples, list)
    # a read-only array behind the library stays read-only and unchanged
    values = np.array(hr_values())
    values.setflags(write=False)
    library = SegmentLibrary.from_memory(
        [
            InlineSegment("h", "hr_clean", values, MIN, "bpm"),
            InlineSegment("s", "spo2_clean", spo2_values(), MIN, "%"),
        ]
    )
    build(library=library)
    assert not values.flags.writeable and values.tolist() == hr_values()


def test_observed_stream_has_no_latent_only_information() -> None:
    ideal = [
        Event(EventKind.MEASUREMENT, 3 * HOUR, 3 * HOUR, "ideal", {"x": 1}, None),
        Event(EventKind.SCHEDULE_TICK, 4 * HOUR, 4 * HOUR, "latent", {}, None),
        Event(EventKind.INTAKE, 5 * HOUR, 5 * HOUR, "patient", {}, None),
    ]
    latent = latent_day(dispenses=[5 * HOUR - SEC], extra_events=ideal)
    out = build(latent, DOSE_SCHED)
    # latent MEASUREMENT / SCHEDULE_TICK events are ignored: the schedule is the source
    assert events_of(out, EventKind.MEASUREMENT) == []
    assert [e.t_device_ms for e in events_of(out, EventKind.SCHEDULE_TICK)] == [
        8 * HOUR,
        20 * HOUR,
    ]
    assert (
        events_of(out, EventKind.INTAKE) == []
    )  # not witnessed: no visit covers 05:00
    assert {e.source for e in out.events} <= {
        vocab.SOURCE_WARD,
        vocab.SOURCE_ROBOT,
        vocab.SOURCE_CUFF,
        vocab.SOURCE_DISPENSER,
    }
    assert "patient" not in {e.source for e in out.events}
    text = repr(out.samples) + repr(out.events)
    assert "latent" not in text and "ideal" not in text and "ground_truth" not in text


# ---------------------------------------------------------------------------
# 18. Device sequence numbers
# ---------------------------------------------------------------------------


def test_assign_device_seq_per_device() -> None:
    latent = latent_day(
        dispenses=[8 * HOUR, 20 * HOUR + SEC, 20 * HOUR + 2 * SEC],
        intakes=[8 * HOUR + 5 * SEC],
    )
    schedule = Schedule(
        dose_ticks_ms=(8 * HOUR, 20 * HOUR),
        measurement_ticks_ms=(9 * HOUR, 12 * HOUR, 21 * HOUR),
    )
    raw = build(latent, schedule)
    assert all(s.seq is None for s in raw.samples) and all(
        e.seq is None for e in raw.events
    )
    out = assign_device_seq(raw)
    for name in CUFF_SIGNALS:
        assert [s.seq for s in samples_of(out, name)] == [1, 2, 3]
    assert [e.seq for e in events_of(out, EventKind.MEASUREMENT)] == [1, 2, 3]
    assert [e.seq for e in events_of(out, EventKind.DISPENSE)] == [1, 2, 3]
    for kind in (EventKind.INTAKE, EventKind.ROBOT_TASK, EventKind.SCHEDULE_TICK):
        assert events_of(out, kind) and all(e.seq is None for e in events_of(out, kind))
    for name in ("presence", "day_end", "hr_ecg", "spo2"):
        assert all(s.seq is None for s in samples_of(out, name))
    # only the sequence number changes; the input stream is untouched; the call is idempotent
    assert [dataclasses.replace(s, seq=None) for s in out.samples] == list(raw.samples)
    assert all(s.seq is None for s in raw.samples)
    assert assign_device_seq(out) == out
    assert out.visits == raw.visits and out.measurements == raw.measurements


def test_assign_device_seq_follows_arrival_order_not_index() -> None:
    schedule = Schedule(dose_ticks_ms=(), measurement_ticks_ms=(8 * HOUR, 9 * HOUR))
    out = assign_device_seq(build(schedule=schedule, jitter=DelayOne(0, 3 * HOUR)))
    by_time = sorted(samples_of(out, "bp"), key=lambda s: s.t_device_ms)
    assert [s.seq for s in by_time] == [
        1,
        2,
    ]  # the later reading takes the larger number
    assert [m.index for m in out.measurements] == [0, 1]


def test_assign_device_seq_coincident_measurements_keep_generation_order() -> None:
    class SameInstant:
        descriptor = "same"

        def delay_ms(self, rng: np.random.Generator, *, kind: str, index: int) -> int:
            return HOUR if index == 0 else 0  # visit 0 arrives when visit 1 does

    schedule = Schedule(dose_ticks_ms=(), measurement_ticks_ms=(8 * HOUR, 9 * HOUR))
    out = assign_device_seq(build(schedule=schedule, jitter=SameInstant()))
    bps = samples_of(out, "bp")
    assert [s.t_device_ms for s in bps] == [9 * HOUR + 30 * SEC] * 2
    assert [s.seq for s in bps] == [1, 2]
    for name in ("inflation_ms", "cuff_health", "hr_pulse"):
        assert [s.seq for s in samples_of(out, name)] == [1, 2]
    assert [e.seq for e in events_of(out, EventKind.MEASUREMENT)] == [1, 2]


@pytest.mark.parametrize("bad", [None, 5, "x", [], object()])
def test_assign_device_seq_rejects_non_streams(bad: Any) -> None:
    with pytest.raises(MeasurementConfigError):
        assign_device_seq(bad)


# ---------------------------------------------------------------------------
# 19. Payload vocabulary
# ---------------------------------------------------------------------------


def test_payload_keys_declared_in_vocab(tmp_path: Path) -> None:
    jitter = EmpiricalJitter(write_jitter(tmp_path, [0, MIN]))
    latent = latent_day(dispenses=[8 * HOUR, 20 * HOUR], intakes=[8 * HOUR + SEC])
    runs = [
        build(),
        build(latent, SCHED_BOTH),
        build(latent, DOSE_SCHED, jitter=jitter),
        assign_device_seq(build(latent, SCHED_BOTH)),
    ]
    declared = {
        getattr(vocab, name)
        for name in dir(vocab)
        if name.startswith("KEY_") and isinstance(getattr(vocab, name), str)
    }
    assert declared == set(vocab.ALL_PAYLOAD_KEYS)
    seen = set()
    for out in runs:
        for event in out.events:
            seen |= set(event.payload)
            vocab.check_payload(event.kind, event.payload)
            assert all(
                isinstance(v, (str, int, float, bool)) for v in event.payload.values()
            )
    assert seen and seen <= set(vocab.ALL_PAYLOAD_KEYS)
    assert seen == {
        vocab.KEY_KIND,
        vocab.KEY_TASK,
        vocab.KEY_OUTCOME,
        vocab.KEY_PATIENT_ID,
    }


def test_vocab_matches_the_evidence_conventions_table() -> None:
    """Keys and values that the conventions table of evidence-channels.md fixes (WS02-T03)."""
    text = (ROOT / "docs" / "models" / "evidence-channels.md").read_text(
        encoding="utf-8"
    )
    start = text.index("### Trace evidence conventions")
    table = text[start : text.index("###", start + 10)]
    rows = {}
    for line in table.splitlines():
        cells = [c.strip().strip("`") for c in line.strip("|").split("|")]
        if len(cells) >= 2 and cells[0] in {"ROBOT_TASK", "DISPENSE", "INTAKE"}:
            rows.setdefault(cells[0], []).append(cells[1])
    assert set(rows["ROBOT_TASK"]) >= {
        vocab.KEY_TASK,
        vocab.KEY_OUTCOME,
        vocab.KEY_PATIENT_ID,
    }
    assert vocab.KEY_CONTENT_CHANGE in rows["DISPENSE"]
    assert rows["INTAKE"] == ["none"]  # the INTAKE event carries no payload key
    assert vocab.PAYLOAD_KEYS[EventKind.INTAKE] == frozenset()
    assert {vocab.TASK_NAVIGATE, vocab.TASK_MANIPULATE, vocab.TASK_WITNESS} == set(
        vocab.TASKS
    )
    assert {
        vocab.OUTCOME_SUCCESS,
        vocab.OUTCOME_LATE,
        vocab.OUTCOME_FAILED,
        vocab.OUTCOME_TIMEOUT,
    } == set(vocab.OUTCOMES)
    for word in vocab.TASKS + vocab.OUTCOMES:
        assert f"`{word}`" in table


VOCAB_BAD: list[tuple[EventKind, Any]] = [
    (EventKind.INTAKE, {"witness": True}),
    (EventKind.MEASUREMENT, {"x": 1}),
    (EventKind.SCHEDULE_TICK, {"kind": "other"}),
    (EventKind.SCHEDULE_TICK, {"kind": 5}),
    (EventKind.SCHEDULE_TICK, {"latent": 1}),
    (EventKind.ROBOT_TASK, {"task": "fly", "outcome": "success"}),
    (EventKind.ROBOT_TASK, {"task": "navigate", "outcome": "maybe"}),
    (EventKind.ROBOT_TASK, {"patient_id": 5}),
    (EventKind.ROBOT_TASK, {"patient_id": ""}),
    (EventKind.DISPENSE, {"content_change": float("nan")}),
    (EventKind.DISPENSE, {"content_change": True}),
    (EventKind.DISPENSE, {"content_change": "x"}),
    (EventKind.DISPENSE, {"content_change": 10**400}),
    (EventKind.DISPENSE, None),
    (EventKind.DISPENSE, [("content_change", 1.0)]),
    (EventKind.DISPENSE, {1: 1.0}),
    ("dispense", {}),
    (None, {}),
    (EventKind.NODE_STATE, {}),  # not emitted by this task: no declared payload
]


@pytest.mark.parametrize(("kind", "payload"), VOCAB_BAD)
def test_check_payload_refuses_undeclared_content(kind: Any, payload: Any) -> None:
    with pytest.raises(vocab.VocabularyError):
        vocab.check_payload(kind, payload)


def test_check_payload_accepts_declared_content() -> None:
    vocab.check_payload(EventKind.SCHEDULE_TICK, {"kind": "dose"})
    vocab.check_payload(EventKind.DISPENSE, {})
    vocab.check_payload(EventKind.DISPENSE, {"content_change": -1.0})
    vocab.check_payload(EventKind.INTAKE, {})
    vocab.check_payload(
        EventKind.ROBOT_TASK, {"task": "witness", "outcome": "late", "patient_id": "p1"}
    )
    assert issubclass(vocab.VocabularyError, ValueError)


# ---------------------------------------------------------------------------
# 20. Design rows (committed file invariants that hold filled or not; copies for the rest)
# ---------------------------------------------------------------------------


def design_rows(path: Path) -> dict[str, Any]:
    return {r.parameter: r for r in load_design_file(path).rows}


def edited_copy(tmp_path: Path, updates: Mapping[str, Mapping[str, Any]]) -> Path:
    document = yaml.safe_load(DESIGN_FILE.read_text(encoding="utf-8"))
    for row in document["parameters"]:
        row.update(updates.get(row["parameter"], {}))
    path = tmp_path / "generator_design.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), "utf-8")
    return path


def filled(value: Any) -> dict[str, Any]:
    return {
        "value": value,
        "status": "filled",
        "source_ref": FIXTURE_NOTE,
        "rationale": "FIXTURE-ONLY: exercises the filled state of the row",
        "verified_by": None,
    }


def unfilled() -> dict[str, Any]:
    return {
        "value": None,
        "dist": None,
        "status": "awaiting_human_value",
        "rationale": None,
        "verified_by": None,
    }


FILLED_ROWS = {
    "inflation_ms_nominal": 30 * SEC,
    "inflation_ms_sd": 5 * SEC,
    "pulse_error_sd_bpm": 2.0,
    "robot_dwell_ms": 10 * MIN,
    "vitals_period_ms": MIN,
}


def test_design_rows_have_provenance() -> None:
    """Invariants that hold whether or not a human has filled the rows."""
    rows = design_rows(DESIGN_FILE)
    for name in DESIGN_ROWS:
        row = rows[name]
        assert row.consumer_task == "WS04-T06", name
        assert row.source_type in SOURCE_TYPES and row.source_type != "fixture_only", (
            name
        )
        assert row.source_type in {"design_choice", "published_literature"}, name
        assert row.source_ref and row.source_ref.strip(), name
        if row.filled:
            assert row.rationale and row.rationale.strip(), name
        else:
            assert row.value is None
    assert rows["inflation_ms_nominal"].unit == "ms"
    assert rows["inflation_ms_sd"].unit == "ms"
    assert rows["pulse_error_sd_bpm"].unit == "bpm"
    assert rows["robot_dwell_ms"].unit == "ms"
    assert rows["vitals_period_ms"].unit == "ms"
    table = (ROOT / "docs" / "benchmark" / "parameter-provenance.md").read_text("utf-8")
    for name in DESIGN_ROWS:
        assert f"| {name} |" in table


def test_cuff_rows_state_the_monitor_keeps_its_own_copy() -> None:
    """Passo 5: the provenance rows say who reads which copy of the device error."""
    path = ROOT / "configs" / "priors" / "literature_hypertension.yaml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    rows = {r["parameter"]: r for r in document["parameters"]}
    for name in ("cuff_error_sd_mmhg", "cuff_bias_mmhg"):
        note = " ".join(rows[name]["note"].split()).lower()
        assert "cuff_error_sd" in note and "own copy" in note, name
        assert "same source value" in note and "mismatch" in note, name


def test_measurement_design_unfilled_state_on_a_copy(tmp_path: Path) -> None:
    path = edited_copy(tmp_path, {name: unfilled() for name in DESIGN_ROWS})
    with pytest.raises(UnfilledParameterError) as info:
        load_measurement_design(path, inflation_min_ms=30 * SEC)
    for name in DESIGN_ROWS:
        assert name in str(info.value)
    one = dict(FILLED_ROWS)
    partly = edited_copy(
        tmp_path,
        {n: filled(v) if n != "robot_dwell_ms" else unfilled() for n, v in one.items()},
    )
    with pytest.raises(UnfilledParameterError, match="robot_dwell_ms"):
        load_measurement_design(partly, inflation_min_ms=30 * SEC)


def test_measurement_design_filled_state_on_a_copy(tmp_path: Path) -> None:
    path = edited_copy(tmp_path, {n: filled(v) for n, v in FILLED_ROWS.items()})
    design = load_measurement_design(path, inflation_min_ms=25 * SEC)
    assert design == MeasurementDesign(
        inflation_ms_nominal=30 * SEC,
        inflation_ms_sd=5 * SEC,
        pulse_error_sd_bpm=2.0,
        robot_dwell_ms=10 * MIN,
        vitals_period_ms=MIN,
        inflation_min_ms=25 * SEC,
    )
    # the filled design builds a day
    out = build(design=design)
    assert len(out.measurements) == 2


BAD_ROW_VALUES: list[tuple[str, Any]] = [
    ("inflation_ms_nominal", -1),
    ("inflation_ms_nominal", 1.5),
    ("inflation_ms_nominal", "30"),
    ("inflation_ms_nominal", True),
    ("inflation_ms_nominal", DAY + 1),
    ("inflation_ms_sd", -1.0),
    ("inflation_ms_sd", "x"),
    ("inflation_ms_sd", [1]),
    ("pulse_error_sd_bpm", -0.5),
    ("pulse_error_sd_bpm", {"a": 1}),
    ("robot_dwell_ms", -1),
    ("robot_dwell_ms", 0.5),
    ("vitals_period_ms", 0),
    ("vitals_period_ms", 7),  # does not divide the day
    ("vitals_period_ms", 7 * MIN),  # few samples, does not divide the day
    ("vitals_period_ms", 1),  # more samples than MAX_VITALS_SAMPLES
    ("vitals_period_ms", True),
]


@pytest.mark.parametrize(("name", "value"), BAD_ROW_VALUES)
def test_measurement_design_refuses_bad_filled_values(
    tmp_path: Path, name: str, value: Any
) -> None:
    updates = {n: filled(v) for n, v in FILLED_ROWS.items()}
    updates[name] = filled(value)
    path = edited_copy(tmp_path, updates)
    # a value the row parser refuses (a bool, a string) is a PriorConfigError of the loader
    with pytest.raises((MeasurementConfigError, PriorConfigError)):
        load_measurement_design(path, inflation_min_ms=30 * SEC)


def test_measurement_design_loader_inputs(tmp_path: Path) -> None:
    path = edited_copy(tmp_path, {n: filled(v) for n, v in FILLED_ROWS.items()})
    for bad_min in (None, -1, 1.5, True, "1", DAY + 1, 10**400):
        with pytest.raises(MeasurementConfigError):
            load_measurement_design(path, inflation_min_ms=bad_min)  # type: ignore[arg-type]
    for bad_path in (None, 5, b"x", ["a"], "a\0b", object()):
        with pytest.raises(MeasurementConfigError):
            load_measurement_design(bad_path, inflation_min_ms=0)  # type: ignore[arg-type]
    for missing in (tmp_path / "missing.yaml", tmp_path):
        with pytest.raises(PriorConfigError):
            load_measurement_design(missing, inflation_min_ms=0)
    document = yaml.safe_load(path.read_text("utf-8"))
    document["parameters"] = [
        r for r in document["parameters"] if r["parameter"] != "robot_dwell_ms"
    ]
    path.write_text(yaml.safe_dump(document, sort_keys=False), "utf-8")
    with pytest.raises(PriorConfigError, match="robot_dwell_ms"):
        load_measurement_design(path, inflation_min_ms=0)


# ---------------------------------------------------------------------------
# 21. Fault-free inflation is never below the registry minimum
# ---------------------------------------------------------------------------


def test_fault_free_inflation_not_below_registry_minimum() -> None:
    design = MeasurementDesign(
        inflation_ms_nominal=30 * SEC,
        inflation_ms_sd=10 * SEC,
        pulse_error_sd_bpm=0.0,
        robot_dwell_ms=10 * MIN,
        vitals_period_ms=MIN,
        inflation_min_ms=30 * SEC,
    )
    ticks = tuple(range(0, 200 * 400_000, 400_000))
    schedule = Schedule(dose_ticks_ms=(), measurement_ticks_ms=ticks)
    out = build(schedule=schedule, design=design, seed=9)
    values = [m.inflation_ms for m in out.measurements]
    assert min(values) >= 30 * SEC and len(values) == len(ticks)
    expected_raised = 0
    for k in range(len(ticks)):
        z = stream(9, 0, 0, StreamPurpose.MEASUREMENT, k).standard_normal(3)
        raw = round(30 * SEC + 10 * SEC * z[1])
        expected_raised += raw < 30 * SEC
        assert values[k] == max(raw, 30 * SEC)
    assert 0 < expected_raised < len(ticks)  # about half: the guard is exercised
    assert out.settings["n_inflation_raised"] == expected_raised
    assert [m.inflation_raised for m in out.measurements].count(True) == expected_raised
    assert [s.value for s in samples_of(out, "inflation_ms")] == [
        float(v) for v in values
    ]
    # the measurement instant uses the raised duration
    assert all(m.t_ms == m.arrival_ms + m.inflation_ms for m in out.measurements)
    # a zero SD at the minimum raises nothing
    assert build().settings["n_inflation_raised"] == 0


# ---------------------------------------------------------------------------
# Latent hold semantics, time edges, day boundary
# ---------------------------------------------------------------------------


def hold(values: Sequence[tuple[int, float]]) -> LatentSbpHold:
    return LatentSbpHold([Sample("bp", t, t, v, None, None) for t, v in values])


def test_latent_hold_is_last_value_at_or_before() -> None:
    h = hold([(0, 100.0), (60_000, 110.0), (120_000, 120.0)])
    assert h.at(0) == 100.0
    assert h.at(59_999) == 100.0
    assert h.at(60_000) == 110.0  # exactly on a grid point: that point's value
    assert h.at(60_001) == 110.0
    assert h.at(120_000) == 120.0
    assert h.at(10**12) == 120.0  # after the last point: held
    assert h.last_t_ms == 120_000 and h.first_t_ms == 0
    with pytest.raises(MeasurementConfigError):
        h.at(
            -1
        )  # before the first point: undefined (hold_last gives nan, never a reading)
    shifted = hold([(DAY, 1.0), (DAY + 60_000, 2.0)])
    with pytest.raises(MeasurementConfigError):
        shifted.at(DAY - 1)
    assert shifted.at(DAY) == 1.0


@pytest.mark.parametrize(
    "t", [None, True, 1.5, "1", 10**400, -(10**400), 2**63, float("nan")]
)
def test_latent_hold_rejects_bad_instants(t: Any) -> None:
    with pytest.raises(MeasurementConfigError):
        hold([(0, 1.0)]).at(t)


LATENT_HOLD_BAD: list[Any] = [
    [],
    [
        Sample("bp", 5, 5, 1.0, None, None),
        Sample("bp", 5, 5, 2.0, None, None),
    ],  # duplicate
    [
        Sample("bp", 5, 5, 1.0, None, None),
        Sample("bp", 3, 3, 2.0, None, None),
    ],  # unsorted
    [Sample("bp", 5, 5, float("nan"), None, None)],
    [Sample("bp", 5, 5, float("inf"), None, None)],
    [Sample("bp", True, 5, 1.0, None, None)],
    [Sample("bp", 1.5, 5, 1.0, None, None)],
    [Sample("bp", 5, 5, True, None, None)],
    [Sample("bp", 5, 5, "1", None, None)],
    [Sample("hr_ecg", 5, 5, 1.0, None, None)],  # no bp sample at all
    ["x"],
    None,
    5,
    "abc",
]


@pytest.mark.parametrize("samples", LATENT_HOLD_BAD)
def test_latent_hold_rejects_bad_latent_pressure(samples: Any) -> None:
    with pytest.raises(MeasurementConfigError):
        LatentSbpHold(samples)


def test_latent_hold_ignores_other_signals() -> None:
    mixed = [
        Sample("hr_ecg", 0, 0, 50.0, None, None),
        Sample("bp", 0, 0, 100.0, None, None),
        Sample("bp", 10, 10, 101.0, None, None),
    ]
    assert LatentSbpHold(mixed).at(5) == 100.0


def test_latent_pressure_instant_before_first_grid_point_is_refused_in_a_build() -> (
    None
):
    late_grid = tuple(
        Sample("bp", 9 * HOUR + k * MIN, 9 * HOUR + k * MIN, 130.0, None, None)
        for k in range(60)
    )
    latent = LatentDay("p0000", 0, 0, late_grid, ())
    with pytest.raises(MeasurementConfigError):
        build(latent)  # the 08:00 reading precedes the first latent point
    ok = build(latent, Schedule(dose_ticks_ms=(), measurement_ticks_ms=(9 * HOUR,)))
    assert ok.measurements[0].latent_sbp_mmhg == 130.0


def test_reading_after_the_last_grid_point_holds_the_last_value() -> None:
    latent = latent_day(step=HOUR, ramp=1.0)  # 23 is the last grid hour
    out = build(
        latent, Schedule(dose_ticks_ms=(), measurement_ticks_ms=(23 * HOUR + 30 * MIN,))
    )
    assert out.measurements[0].latent_sbp_mmhg == 130.0 + 23
    assert out.settings["n_measurements_after_day_end"] == 0
    past = build(
        latent, Schedule(dose_ticks_ms=(), measurement_ticks_ms=(DAY - 10 * SEC,))
    )
    assert past.measurements[0].t_ms == DAY + 20 * SEC
    assert past.measurements[0].latent_sbp_mmhg == 130.0 + 23
    assert past.settings["n_measurements_after_day_end"] == 1


def test_measurement_crossing_midnight_stays_with_its_day() -> None:
    latent = latent_day(day_index=1)
    sched = Schedule(dose_ticks_ms=(), measurement_ticks_ms=(DAY - 10 * SEC,))
    out = build(latent, sched)
    (m,) = out.measurements
    assert m.tick_ms == DAY + DAY - 10 * SEC and m.t_ms == 2 * DAY + 20 * SEC
    (meas,) = events_of(out, EventKind.MEASUREMENT)
    assert meas.t_device_ms == 2 * DAY + 20 * SEC
    # the day_end of day 1 lies at the closing instant, before the reading, and the order holds
    ends = samples_of(out, "day_end")
    assert [s.t_device_ms for s in ends] == [2 * DAY]
    assert all(a.t_rx_ms <= b.t_rx_ms for a, b in pairwise(out.samples))
    assert out.samples[-1].signal == "bp" or out.samples[-1].t_rx_ms >= 2 * DAY


def test_arrival_jitter_can_push_a_visit_into_the_next_day() -> None:
    class Late:
        descriptor = "late"

        def delay_ms(self, rng: np.random.Generator, *, kind: str, index: int) -> int:
            return 2 * HOUR

    sched = Schedule(
        dose_ticks_ms=(23 * HOUR,), measurement_ticks_ms=(23 * HOUR + 30 * MIN,)
    )
    latent = latent_day(intakes=[DAY + HOUR + 5 * MIN])  # after midnight, in the visit
    out = build(latent, sched, jitter=Late())
    assert all(v.arrival_ms >= DAY for v in out.visits)
    assert [e.t_device_ms for e in events_of(out, EventKind.INTAKE)] == [
        DAY + HOUR + 5 * MIN
    ]
    assert samples_of(out, "day_end")[0].t_device_ms == DAY
    assert out.day_index == 0 and all(v.tick_ms < DAY for v in out.visits)
    assert all(a.t_rx_ms <= b.t_rx_ms for a, b in pairwise(out.samples))
    assert all(a.t_rx_ms <= b.t_rx_ms for a, b in pairwise(out.events))


@pytest.mark.parametrize("day", [0, 1, 6, 400])
def test_day_end_at_the_closing_instant_of_each_day(day: int) -> None:
    out = build(latent_day(day_index=day))
    (end,) = samples_of(out, "day_end")
    assert end.t_device_ms == end.t_rx_ms == (day + 1) * DAY and end.value == 1.0
    start = day * DAY
    assert samples_of(out, "hr_ecg")[0].t_device_ms == start
    assert [e.t_device_ms for e in events_of(out, EventKind.SCHEDULE_TICK)] == [
        start + 8 * HOUR,
        start + 20 * HOUR,
    ]


def test_tie_rule_keeps_generation_order() -> None:
    sched = Schedule(dose_ticks_ms=(8 * HOUR,), measurement_ticks_ms=(8 * HOUR,))
    design = dataclasses.replace(DESIGN, inflation_ms_nominal=0, inflation_min_ms=0)
    out = build(
        latent_day(dispenses=[8 * HOUR], intakes=[8 * HOUR]), sched, design=design
    )
    at = [e for e in out.events if e.t_device_ms == 8 * HOUR]
    assert [e.kind for e in at] == [
        EventKind.SCHEDULE_TICK,
        EventKind.SCHEDULE_TICK,
        EventKind.ROBOT_TASK,
        EventKind.ROBOT_TASK,
        EventKind.MEASUREMENT,
        EventKind.DISPENSE,
        EventKind.INTAKE,
    ]
    assert [v.kind for v in out.visits] == [vocab.KIND_DOSE, vocab.KIND_MEASUREMENT]
    sig = [s.signal for s in out.samples if s.t_device_ms == 8 * HOUR]
    assert sig[:2] == ["presence", "presence"] and sig[2:6] == list(CUFF_SIGNALS)
    # the hr_ecg grid point at 08:00 follows the cuff message at the same instant
    assert sig[6:] == ["hr_ecg", "spo2"]


def test_skipped_measurements_keep_later_noise_aligned() -> None:
    schedule = Schedule(
        dose_ticks_ms=(), measurement_ticks_ms=tuple(h * HOUR for h in range(6, 22, 3))
    )
    errors = DeviceErrorModel(5.0, 3.0, 0.0, 0.0)
    design = dataclasses.replace(
        DESIGN, inflation_ms_sd=10 * SEC, pulse_error_sd_bpm=2.0
    )
    full = build(schedule=schedule, errors=errors, design=design, seed=11)
    skipped = build(
        schedule=schedule,
        errors=errors,
        design=design,
        seed=11,
        skip_measurement_ticks_ms=[schedule.measurement_ticks_ms[1]],
    )
    by_index_full = {m.index: m for m in full.measurements}
    by_index_skip = {m.index: m for m in skipped.measurements}
    assert 1 not in by_index_skip and len(by_index_skip) == len(by_index_full) - 1
    for k, m in by_index_skip.items():
        assert m == by_index_full[k]  # every other measurement is bit-identical
    assert skipped.settings["skipped_measurement_indices"] == [1]
    # the robot still visits, so presence and arrivals are unchanged
    assert [v.arrival_ms for v in skipped.visits] == [v.arrival_ms for v in full.visits]
    assert len(samples_of(skipped, "bp")) == len(samples_of(full, "bp")) - 1


@pytest.mark.parametrize(
    "skip",
    [
        [1],
        [8 * HOUR + 1],
        "abc",
        5,
        [True],
        [1.5],
        [None],
        [10**400],
        np.array(8 * HOUR),  # an array that is "iterable" by type but has no length
        {8 * HOUR + 1: 1},
    ],
)
def test_skip_measurement_ticks_are_validated(skip: Any) -> None:
    with pytest.raises(MeasurementConfigError):
        build(skip_measurement_ticks_ms=skip)


# ---------------------------------------------------------------------------
# Determinism and independence
# ---------------------------------------------------------------------------


def test_same_seed_and_patient_give_identical_output(tmp_path: Path) -> None:
    jitter = EmpiricalJitter(write_jitter(tmp_path, [0, MIN, 2 * MIN]))
    errors = DeviceErrorModel(5.0, 3.0, 0.0, 0.0)
    design = dataclasses.replace(
        DESIGN, inflation_ms_sd=10 * SEC, pulse_error_sd_bpm=2.0
    )
    a = build(
        latent_day(),
        SCHED_BOTH,
        errors=errors,
        design=design,
        jitter=jitter,
        seed=3,
        patient_index=2,
    )
    b = build(
        latent_day(),
        SCHED_BOTH,
        errors=errors,
        design=design,
        jitter=jitter,
        seed=3,
        patient_index=2,
    )
    assert a == b and repr(a) == repr(b)
    other_seed = build(
        latent_day(),
        SCHED_BOTH,
        errors=errors,
        design=design,
        jitter=jitter,
        seed=4,
        patient_index=2,
    )
    other_patient = build(
        latent_day(),
        SCHED_BOTH,
        errors=errors,
        design=design,
        jitter=jitter,
        seed=3,
        patient_index=3,
    )
    assert other_seed.measurements != a.measurements
    assert other_patient.measurements != a.measurements


def test_other_patients_and_days_do_not_change_a_stream(tmp_path: Path) -> None:
    jitter = EmpiricalJitter(write_jitter(tmp_path, [0, MIN, 2 * MIN]))
    errors = DeviceErrorModel(5.0, 3.0, 0.0, 0.0)
    design = dataclasses.replace(DESIGN, inflation_ms_sd=10 * SEC)

    def day(patient: int, d: int) -> ObservedStream:
        return build(
            latent_day(day_index=d),
            SCHED_BOTH,
            errors=errors,
            design=design,
            jitter=jitter,
            seed=1,
            patient_index=patient,
        )

    alone = day(1, 2)
    for patients in ((0, 1), (1, 0, 5), tuple(range(8))):
        for p in patients:
            for d in (3, 2, 0):  # other days, in another order
                built = day(p, d)
                if (p, d) == (1, 2):
                    assert built == alone
    assert day(1, 2) == alone
    assert day(1, 3) != alone


def test_streams_are_independent_across_purposes(tmp_path: Path) -> None:
    errors = DeviceErrorModel(5.0, 3.0, 0.0, 0.0)
    design = dataclasses.replace(
        DESIGN, inflation_ms_sd=10 * SEC, pulse_error_sd_bpm=2.0
    )
    jitter = EmpiricalJitter(write_jitter(tmp_path, [0, MIN, 2 * MIN]))
    plain = build(
        latent_day(ramp=0.0), SCHED_BOTH, errors=errors, design=design, seed=6
    )
    jittered = build(
        latent_day(ramp=0.0),
        SCHED_BOTH,
        errors=errors,
        design=design,
        jitter=jitter,
        seed=6,
    )
    assert [m.error_mmhg for m in plain.measurements] == [
        m.error_mmhg for m in jittered.measurements
    ]
    assert [m.inflation_ms for m in plain.measurements] == [
        m.inflation_ms for m in jittered.measurements
    ]
    assert plain.settings["segment_ids"] == jittered.settings["segment_ids"]
    assert [s.value for s in samples_of(plain, "hr_ecg")] == [
        s.value for s in samples_of(jittered, "hr_ecg")
    ]


# ---------------------------------------------------------------------------
# Extreme inputs of build_observed_base and the design
# ---------------------------------------------------------------------------

BAD_BUILD_ARGS: list[tuple[str, Any]] = [
    ("latent", None),
    ("latent", "x"),
    ("latent", {}),
    ("latent", LatentDay("p", 0, 0, (), ())),  # no pressure
    ("latent", LatentDay("", 0, 0, latent_day().samples, ())),
    ("latent", LatentDay(5, 0, 0, latent_day().samples, ())),  # type: ignore[arg-type]
    ("latent", LatentDay("p", -1, 0, latent_day().samples, ())),
    ("latent", LatentDay("p", True, 0, latent_day().samples, ())),
    ("latent", LatentDay("p", 10**400, 0, latent_day().samples, ())),
    ("latent", LatentDay("p", 2**32, 0, latent_day().samples, ())),
    ("latent", LatentDay("p", 0, 0, latent_day().samples, "x")),  # type: ignore[arg-type]
    ("latent", LatentDay("p", 0, 0, latent_day().samples, (5,))),  # type: ignore[arg-type]
    (
        "latent",
        LatentDay(
            "p", 0, 0, latent_day().samples, (Event("intake", 1, 1, "s", {}, None),)
        ),
    ),  # type: ignore[arg-type]
    (
        "latent",
        LatentDay(
            "p",
            0,
            0,
            latent_day().samples,
            (Event(EventKind.INTAKE, 1.5, 1, "s", {}, None),),
        ),
    ),  # type: ignore[arg-type]
    (
        "latent",
        LatentDay(
            "p",
            0,
            0,
            latent_day().samples,
            (Event(EventKind.INTAKE, True, 1, "s", {}, None),),
        ),
    ),  # type: ignore[arg-type]
    (
        "latent",
        LatentDay(
            "p",
            0,
            0,
            latent_day().samples,
            (Event(EventKind.INTAKE, 10**400, 1, "s", {}, None),),
        ),
    ),
    ("schedule", None),
    ("schedule", "x"),
    ("schedule", [8 * HOUR]),
    ("care_plan_id", None),
    ("care_plan_id", ""),
    ("care_plan_id", " "),
    ("care_plan_id", 5),
    ("errors", None),
    ("errors", (0.0, 0.0)),
    ("errors", DeviceErrorModel(float("nan"), 0.0, 0.0, 0.0)),
    ("errors", DeviceErrorModel(float("inf"), 0.0, 0.0, 0.0)),
    ("errors", DeviceErrorModel(-1.0, 0.0, 0.0, 0.0)),
    ("errors", DeviceErrorModel(0.0, float("nan"), 0.0, 0.0)),
    ("errors", DeviceErrorModel(0.0, float("-inf"), 0.0, 0.0)),
    ("errors", DeviceErrorModel(True, 0.0, 0.0, 0.0)),  # type: ignore[arg-type]
    ("errors", DeviceErrorModel("1", 0.0, 0.0, 0.0)),  # type: ignore[arg-type]
    ("errors", DeviceErrorModel(None, 0.0, 0.0, 0.0)),  # type: ignore[arg-type]
    ("errors", DeviceErrorModel(10**400, 0.0, 0.0, 0.0)),
    ("design", None),
    ("design", {"inflation_ms_nominal": 1}),
    ("library", None),
    ("library", "x"),
    ("seed", -1),
    ("seed", 2**64),
    ("seed", True),
    ("seed", 1.5),
    ("seed", None),
    ("seed", "0"),
    ("seed", 10**400),
    ("patient_index", -1),
    ("patient_index", 2**32),
    ("patient_index", True),
    ("patient_index", None),
    ("patient_index", 1.5),
    ("patient_index", 10**400),
    ("allow_no_segments", 1),
    ("allow_no_segments", None),
    ("allow_no_segments", "yes"),
]


@pytest.mark.parametrize(("name", "value"), BAD_BUILD_ARGS)
def test_build_refuses_extreme_or_malformed_inputs(name: str, value: Any) -> None:
    with pytest.raises(MeasurementConfigError):
        build(**{name: value})


def test_build_refuses_a_huge_latent_day_and_a_huge_schedule() -> None:
    class Huge(Sequence[Sample]):
        def __len__(self) -> int:
            return MAX_GRID_POINTS + 1

        def __getitem__(self, index: Any) -> Sample:
            raise AssertionError("must not be read")

    with pytest.raises(MeasurementConfigError):
        build(LatentDay("p0000", 0, 0, Huge(), ()))

    class HugeEvents(Sequence[Event]):
        def __len__(self) -> int:
            return MAX_LATENT_EVENTS + 1

        def __getitem__(self, index: Any) -> Event:
            raise AssertionError("must not be read")

    with pytest.raises(MeasurementConfigError):
        build(LatentDay("p0000", 0, 0, latent_day().samples, HugeEvents()))
    many = Schedule(
        dose_ticks_ms=(),
        measurement_ticks_ms=tuple(range(0, (MAX_VISITS_PER_DAY + 1) * 1000, 1000)),
    )
    with pytest.raises(MeasurementConfigError):
        build(schedule=many)
    split = Schedule(
        dose_ticks_ms=tuple(range(0, (MAX_VISITS_PER_DAY // 2 + 1) * 1000, 1000)),
        measurement_ticks_ms=tuple(
            range(1, (MAX_VISITS_PER_DAY // 2 + 1) * 1000, 1000)
        ),
    )
    with pytest.raises(MeasurementConfigError):
        build(schedule=split)  # the limit counts doses and measurements together


def test_build_refuses_a_reading_that_overflows() -> None:
    with pytest.raises(MeasurementConfigError):
        build(latent_day(sbp=1.7e308), errors=DeviceErrorModel(0.0, 1.7e308, 0.0, 0.0))


def test_build_with_many_events_is_bounded_not_hanging() -> None:
    big_events = [
        Event(EventKind.DISPENSE, 8 * HOUR + k, 8 * HOUR + k, "d", {}, None)
        for k in range(20_000)
    ]
    out = build(latent_day(extra_events=big_events), DOSE_SCHED)
    assert len(events_of(out, EventKind.DISPENSE)) == 20_000


DESIGN_BAD: list[dict[str, Any]] = [
    {"inflation_ms_nominal": -1},
    {"inflation_ms_nominal": 1.5},
    {"inflation_ms_nominal": True},
    {"inflation_ms_nominal": None},
    {"inflation_ms_nominal": "30"},
    {"inflation_ms_nominal": 10**400},
    {"inflation_ms_nominal": DAY + 1},
    {"inflation_ms_sd": -1},
    {"inflation_ms_sd": float("nan")},
    {"inflation_ms_sd": float("inf")},
    {"inflation_ms_sd": True},
    {"inflation_ms_sd": "x"},
    {"inflation_ms_sd": 10**400},
    {"pulse_error_sd_bpm": -1.0},
    {"pulse_error_sd_bpm": float("nan")},
    {"pulse_error_sd_bpm": None},
    {"pulse_error_sd_bpm": 10**400},
    {"robot_dwell_ms": -1},
    {"robot_dwell_ms": 1.5},
    {"robot_dwell_ms": True},
    {"robot_dwell_ms": DAY + 1},
    {"vitals_period_ms": 0},
    {"vitals_period_ms": -60_000},
    {"vitals_period_ms": 7},
    {"vitals_period_ms": 7 * MIN},  # few samples but it does not divide the day
    {"vitals_period_ms": DAY * 2},
    {"vitals_period_ms": 432},  # divides the day but gives 200 000 samples
    {"vitals_period_ms": True},
    {"vitals_period_ms": 1.5},
    {"inflation_min_ms": -1},
    {"inflation_min_ms": 1.5},
    {"inflation_min_ms": None},
    {"inflation_min_ms": DAY + 1},
]


@pytest.mark.parametrize("change", DESIGN_BAD)
def test_measurement_design_refuses_bad_values(change: dict[str, Any]) -> None:
    fields = dataclasses.asdict(DESIGN)
    fields.update(change)
    with pytest.raises(MeasurementConfigError):
        MeasurementDesign(**fields)


def test_measurement_design_accepts_the_limits() -> None:
    edge = MeasurementDesign(
        0,
        0,
        0.0,
        0,
        DAY // MAX_VITALS_SAMPLES if DAY % MAX_VITALS_SAMPLES == 0 else DAY,
        0,
    )
    assert edge.inflation_ms_nominal == 0
    longest = MeasurementDesign(DAY, DAY, 1.0, DAY, DAY, DAY)
    assert longest.vitals_period_ms == DAY
    assert isinstance(
        MeasurementDesign(30 * SEC, 5, 2, MIN, MIN, 0).pulse_error_sd_bpm, float
    )


@pytest.mark.parametrize(
    ("bias", "sd"),
    [
        (float("nan"), 0.0),
        (0.0, float("nan")),
        (float("inf"), 0.0),
        (0.0, float("inf")),
        (0.0, -1.0),
        (True, 0.0),
        (0.0, True),
        ("1", 0.0),
        (None, 0.0),
        (10**400, 0.0),
        (0.0, 10**400),
    ],
)
def test_cuff_model_refuses_bad_parameters(bias: Any, sd: Any) -> None:
    with pytest.raises(MeasurementConfigError):
        CuffModel(bias, sd)


@pytest.mark.parametrize("z", [float("nan"), float("inf"), None, "0", True])
def test_cuff_model_refuses_bad_draws(z: Any) -> None:
    with pytest.raises(MeasurementConfigError):
        CuffModel(0.0, 1.0).reading(130.0, z)
    with pytest.raises(MeasurementConfigError):
        CuffModel(0.0, 1.0).reading(float("nan"), 0.0)
    with pytest.raises(MeasurementConfigError):
        CuffModel(1e308, 1e308).reading(1e308, 1e308)  # overflow to inf


@pytest.mark.parametrize(
    ("args", "kwargs"),
    [
        ((None, DESIGN, 0, 0, 0), {}),
        ((LIB, None, 0, 0, 0), {}),
        ((LIB, DESIGN, -1, 0, 0), {}),
        ((LIB, DESIGN, 0, -1, 0), {}),
        ((LIB, DESIGN, 0, 0, -1), {}),
        ((LIB, DESIGN, 0, 0, 2**32), {}),
        ((LIB, DESIGN, True, 0, 0), {}),
        ((LIB, DESIGN, 0, 1.5, 0), {}),
        ((LIB, DESIGN, 0, 0, 0), {"allow_missing": 1}),
    ],
)
def test_draw_clean_vitals_refuses_bad_arguments(args: Any, kwargs: Any) -> None:
    with pytest.raises(MeasurementConfigError):
        draw_clean_vitals(*args, **kwargs)


def test_draw_clean_vitals_missing_kinds(tmp_path: Path) -> None:
    empty = SegmentLibrary(tmp_path, SegmentIndex(()))
    with pytest.raises(SegmentUnavailableError):
        draw_clean_vitals(empty, DESIGN, 0, 0, 0)
    allowed = draw_clean_vitals(empty, DESIGN, 0, 0, 0, allow_missing=True)
    assert allowed.hr_bpm is None and allowed.spo2_pct is None
    assert allowed.segment_ids == {"hr_clean": (), "spo2_clean": ()}
    assert allowed.join_count == {"hr_clean": 0, "spo2_clean": 0}


# ---------------------------------------------------------------------------
# Resource bounds, public API and layering
# ---------------------------------------------------------------------------


def test_output_size_is_bounded_by_the_schedule_and_the_vitals_grid() -> None:
    out = build(latent_day(), SCHED_BOTH)
    n_meas = len(SCHED_BOTH.measurement_ticks_ms)
    n_visits = n_meas + len(SCHED_BOTH.dose_ticks_ms)
    expected_samples = n_visits + 4 * n_meas + 2 * (DAY // MIN) + 1
    assert len(out.samples) == expected_samples
    assert MAX_VITALS_SAMPLES * 2 + MAX_VISITS_PER_DAY * 5 + 1 < 1_000_000
    assert MAX_DRAW_SAMPLES <= MAX_SEGMENT_SAMPLES


def test_new_modules_export_nothing_from_the_package_root() -> None:
    exported = set(benchmark_pkg.__all__)
    new = {
        "MeasurementDesign",
        "EmpiricalJitter",
        "NoJitter",
        "SegmentLibrary",
        "SegmentIndex",
        "build_observed_base",
        "assign_device_seq",
        "ObservedStream",
        "vocab",
    }
    assert not exported & new
    for name in new:
        assert not hasattr(benchmark_pkg, name) or name == "vocab"


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = "." * node.level + (node.module or "")
            found.add(base)
            found.update(f"{base}.{a.name}" for a in node.names)
    return found


# Packages and benchmark modules that each new module may import (ADR layering of
# ``tests/test_layering.py`` allows more to ``benchmark`` as a whole; these three modules
# are narrower on purpose: they sit below the injectors and the labeller and never touch
# the monitor, the calibrator, the attribution layer, the baselines or the evaluation).
FORBIDDEN_PACKAGES = (
    "ralmon.spec",
    "ralmon.conformal",
    "ralmon.monitor",
    "ralmon.attribution",
    "ralmon.baselines",
    "ralmon.eval",
)
ALLOWED_RALMON_IMPORTS = {
    "segments.py": (),
    "vocab.py": ("ralmon.signals",),
    "measurement.py": (
        "ralmon.signals",
        "ralmon.benchmark.latent",
        "ralmon.benchmark.priors",
        "ralmon.benchmark.rng",
        "ralmon.benchmark.schedule",
        "ralmon.benchmark.segments",
        "ralmon.benchmark.trace",
        "ralmon.benchmark.vocab",
    ),
}


def test_module_layering_is_one_way() -> None:
    segments = imported_modules(SRC / "segments.py")
    assert not any("measurement" in m or "vocab" in m for m in segments)
    vocab_imports = imported_modules(SRC / "vocab.py")
    assert not any("measurement" in m or "segments" in m for m in vocab_imports)
    for path in (SRC / "segments.py", SRC / "vocab.py", SRC / "measurement.py"):
        mods = imported_modules(path)
        for forbidden in FORBIDDEN_PACKAGES:
            assert not any(
                m == forbidden or m.startswith(forbidden + ".") for m in mods
            ), (path.name, forbidden)
        allowed = ALLOWED_RALMON_IMPORTS[path.name]
        for m in mods:
            if m.startswith("ralmon") and m not in ("ralmon", "ralmon.benchmark"):
                assert any(m == a or m.startswith(a + ".") for a in allowed), (
                    path.name,
                    m,
                )
        top = {m.split(".")[0] for m in mods if not m.startswith(".")}
        assert top <= {
            "__future__",
            "collections",
            "dataclasses",
            "enum",
            "hashlib",
            "json",
            "math",
            "numbers",
            "operator",
            "os",
            "pathlib",
            "re",
            "types",
            "typing",
            "bisect",
            "itertools",
            "stat",
            "numpy",
            "ralmon",
            "yaml",
        }, (path.name, top)
        assert not any(m.startswith(".") for m in mods), path.name  # no relative import


def referenced_names(path: Path) -> set[str]:
    """Every identifier, attribute and imported name that the source of a module mentions."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.alias):
            names.add(node.name.split(".")[-1])
    return names


def test_no_ground_truth_or_latent_day_import_in_the_new_modules() -> None:
    for name in ("segments.py", "vocab.py", "measurement.py"):
        mods = imported_modules(SRC / name)
        assert not any(m.endswith("GroundTruthEvent") for m in mods), name
        assert not {"time", "datetime", "random"} & {m.split(".")[0] for m in mods}, (
            name
        )
        # no mention at all of the ground-truth containers, not only no import of them
        assert not {"GroundTruthEvent", "BenchmarkDay", "TruthRecord"} & (
            referenced_names(SRC / name)
        ), name
    for name in ("segments.py", "vocab.py"):
        assert not any(m.endswith("LatentDay") for m in imported_modules(SRC / name))
        assert "LatentDay" not in referenced_names(SRC / name), name
    # (a previous assertion that no import starts with ``ralmon.benchmark.latent_day`` was
    # vacuous: no such module exists. ``LatentDay`` lives in ``ralmon.benchmark.trace``, and
    # the import allowlist of ``test_module_layering_is_one_way`` already confines the three
    # modules to the modules above, so the assertion is dropped, not replaced.)


def test_json_stability_of_settings() -> None:
    out = build(latent_day(), SCHED_BOTH)
    encoded = json.dumps(out.settings, sort_keys=True)
    assert json.loads(encoded) == json.loads(json.dumps(json.loads(encoded)))
    assert out.settings["cuff_error_family"] == "gaussian"
    assert out.settings["n_measurements"] == 2 and out.settings["n_visits"] == 4


# ---------------------------------------------------------------------------
# Pins of formulas and stream layout (what the documentation promises)
# ---------------------------------------------------------------------------


def test_pulse_reading_is_the_clean_rate_plus_the_third_normal() -> None:
    design = dataclasses.replace(DESIGN, pulse_error_sd_bpm=2.0)
    schedule = Schedule(
        dose_ticks_ms=(), measurement_ticks_ms=(8 * HOUR, 9 * HOUR + 7 * MIN)
    )
    out = build(schedule=schedule, design=design, seed=12, patient_index=3)
    for m in out.measurements:
        z = stream(12, 3, 0, StreamPurpose.MEASUREMENT, m.index).standard_normal(3)
        level = hr_values()[(m.t_ms - 0) // MIN]
        assert m.pulse_bpm == pytest.approx(level + 2.0 * z[2], rel=1e-12)
    assert [s.value for s in samples_of(out, "hr_pulse")] == [
        m.pulse_bpm for m in out.measurements
    ]


def test_reading_uses_the_latent_pressure_at_the_reading_instant() -> None:
    design = dataclasses.replace(
        DESIGN, inflation_ms_nominal=90 * SEC, inflation_min_ms=0
    )
    latent = latent_day(ramp=0.5)  # 130 + 0.5 k at minute k
    jitter = DelayOne(0, 3 * MIN + 20 * SEC)  # arrival 08:03:20, reading 08:04:50
    out = build(latent, SCHED, design=design, jitter=jitter)
    first = out.measurements[0]
    assert first.arrival_ms == 8 * HOUR + 3 * MIN + 20 * SEC
    assert first.t_ms == 8 * HOUR + 4 * MIN + 50 * SEC
    assert first.latent_sbp_mmhg == 130.0 + 0.5 * (8 * 60 + 4)
    assert first.value_mmhg == first.latent_sbp_mmhg  # zero error
    second = out.measurements[1]
    assert second.latent_sbp_mmhg == 130.0 + 0.5 * (20 * 60 + 1)  # 20:01:30


def test_event_and_sample_times_follow_tick_arrival_and_reading() -> None:
    out = build(
        latent_day(), SCHED_BOTH, jitter=DelayOne(0, 2 * MIN)
    )  # first measurement visit (09:00) arrives at 09:02
    ticks = {e.t_device_ms for e in events_of(out, EventKind.SCHEDULE_TICK)}
    assert ticks == {8 * HOUR, 9 * HOUR, 20 * HOUR, 21 * HOUR}
    tasks = {e.t_device_ms for e in events_of(out, EventKind.ROBOT_TASK)}
    assert tasks == {8 * HOUR, 9 * HOUR + 2 * MIN, 20 * HOUR, 21 * HOUR}
    presence = {s.t_device_ms for s in samples_of(out, "presence")}
    assert presence == tasks
    meas = [e.t_device_ms for e in events_of(out, EventKind.MEASUREMENT)]
    assert meas == [9 * HOUR + 2 * MIN + 30 * SEC, 21 * HOUR + 30 * SEC]
    assert [s.t_device_ms for s in samples_of(out, "bp")] == meas
    visit = next(v for v in out.visits if v.kind == vocab.KIND_MEASUREMENT)
    assert (visit.tick_ms, visit.arrival_ms, visit.delay_ms) == (
        9 * HOUR,
        9 * HOUR + 2 * MIN,
        2 * MIN,
    )
    assert visit.departure_ms == visit.arrival_ms + 10 * MIN


def test_jitter_delay_is_pinned_to_its_named_stream(tmp_path: Path) -> None:
    delays = [0, 1_000, 2_000, 3_000, 4_000, 5_000, 6_000, 7_000]
    jitter = EmpiricalJitter(write_jitter(tmp_path, delays))
    schedule = Schedule(
        dose_ticks_ms=(7 * HOUR, 12 * HOUR),
        measurement_ticks_ms=(8 * HOUR, 9 * HOUR, 10 * HOUR),
    )
    out = build(schedule=schedule, jitter=jitter, seed=21, patient_index=4)
    for visit in out.visits:
        sub = 2 * visit.index + (0 if visit.kind == vocab.KIND_MEASUREMENT else 1)
        expected = delays[
            int(stream(21, 4, 0, StreamPurpose.JITTER, sub).integers(0, 8))
        ]
        assert visit.delay_ms == expected, (visit.kind, visit.index)
    # a dose visit and a measurement visit of the same position draw independently
    sub_keys = {(v.kind, v.index) for v in out.visits}
    assert (vocab.KIND_DOSE, 0) in sub_keys and (vocab.KIND_MEASUREMENT, 0) in sub_keys


def test_segment_draw_is_pinned_to_its_named_stream() -> None:
    many = SegmentLibrary.from_memory(
        [
            InlineSegment(f"{k}{i}", k, list(range(1_500 + i)), MIN, "u")
            for k in ("hr_clean", "spo2_clean")
            for i in range(6)
        ]
    )
    vitals = draw_clean_vitals(many, DESIGN, 8, 5, 2)
    for kind, sub in (("hr_clean", 0), ("spo2_clean", 1)):
        direct = many.draw(
            kind, DAY // MIN, stream(8, 5, 2, StreamPurpose.SEGMENTS, sub)
        )
        assert vitals.segment_ids[kind] == direct.segment_ids
        grid = vitals.hr_bpm if kind == "hr_clean" else vitals.spo2_pct
        assert grid == direct.values
    out = build(
        library=many,
        seed=8,
        patient_index=5,
        latent=latent_day(day_index=2),
    )
    assert out.settings["segment_ids"] == {
        k: list(v) for k, v in vitals.segment_ids.items()
    }


SOURCES_DOC = ROOT / "docs" / "benchmark" / "public-sources.md"
SOURCE_ROWS = (
    "VitalDB",
    "BIDMC PPG and Respiration",
    "MIT-BIH Arrhythmia Database",
    "MIT-BIH Noise Stress Test Database",
    "PhysioNet/CinC Challenge 2015",
)
DOC_HEADINGS = [
    "## Purpose",
    "## Sources",
    "## Extraction procedure",
    "## Segment file format",
    "## Verification status",
]
SOURCES_COLUMNS = [
    "source",
    "role in the benchmark (from the README table)",
    "segment kinds intended",
    "licence and redistribution",
    "signal names",
    "sampling rates",
    "units",
    "record layout or labels",
]
STATUS_COLUMNS = ["item", "status", "verified_by", "verified_on"]


def doc_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def doc_section(text: str, heading: str) -> str:
    start = text.index(heading)
    following = [
        text.index(h, start + 1) for h in DOC_HEADINGS if h in text[start + 1 :]
    ]
    return text[start : min(following) if following else len(text)]


def check_public_sources(text: str) -> None:
    """Structure of the document, whatever a human has verified so far.

    Facts may be ``unverified`` or carry the ``verified_by:`` marker defined in the section
    Verification status; a status row may be ``unverified`` or ``verified`` (then it names
    who and when). No count of ``unverified`` is asserted: the document is edited by a human.
    """
    assert [x for x in text.splitlines() if x.startswith("## ")] == DOC_HEADINGS
    status = doc_section(text, "## Verification status")
    assert "verified_by:" in status  # the marker convention is defined here
    sources = doc_section(text, "## Sources")
    assert "WS00-T04" in sources
    table = [x for x in sources.splitlines() if x.startswith("|")]
    assert doc_cells(table[0]) == SOURCES_COLUMNS
    for name in SOURCE_ROWS:
        (row,) = [x for x in table if x.startswith(f"| {name} ")]
        cells = doc_cells(row)
        assert len(cells) == len(SOURCES_COLUMNS), name
        for column, cell in zip(SOURCES_COLUMNS[3:], cells[3:], strict=True):
            # a filled fact is either unverified or marked as verified by someone
            assert cell.startswith("unverified") or "verified_by:" in cell, (
                name,
                column,
                cell,
            )
    rows = [x for x in status.splitlines() if x.startswith("|")]
    assert doc_cells(rows[0]) == STATUS_COLUMNS
    assert len(rows) > 2
    for row in rows[2:]:
        item, state, who, when = doc_cells(row)
        assert item and state in ("unverified", "verified"), row
        if state == "verified":
            assert who and when, row  # a verification names who and when


def test_public_sources_document_structure_whatever_a_human_has_verified() -> None:
    text = SOURCES_DOC.read_text("utf-8")
    check_public_sources(text)  # the committed document, in any verification state

    def edit_row(document: str, name: str, column: int, value: str) -> str:
        lines = document.splitlines()
        at = next(i for i, x in enumerate(lines) if x.startswith(f"| {name} "))
        cells = doc_cells(lines[at])
        cells[column] = value
        lines[at] = "| " + " | ".join(cells) + " |"
        return "\n".join(lines) + "\n"

    # a human confirms one fact: marker in the Sources row, row filled in the status table
    confirmed = edit_row(text, "VitalDB", 4, "NAME (verified_by: tester)")
    confirmed = confirmed.replace(
        "| unverified | | |", "| verified | tester | 2026-01-01 |", 1
    )
    check_public_sources(confirmed)
    # a fact with neither the word unverified nor the marker is refused
    with pytest.raises(AssertionError):
        check_public_sources(edit_row(text, "VitalDB", 5, "500 Hz"))
    # a verification that names nobody is refused
    with pytest.raises(AssertionError):
        check_public_sources(text.replace("| unverified | | |", "| verified | | |", 1))
    # a missing section or row is refused
    with pytest.raises(AssertionError):
        check_public_sources(text.replace("## Purpose", "## Aim", 1))
    with pytest.raises((AssertionError, ValueError)):
        check_public_sources(text.replace("| VitalDB ", "| VitalDb ", 1))


# ---------------------------------------------------------------------------
# Counters that continue across days, defaults of the stream record
# ---------------------------------------------------------------------------


def test_device_counters_chain_across_days() -> None:
    schedule = Schedule(
        dose_ticks_ms=(8 * HOUR,), measurement_ticks_ms=(9 * HOUR, 12 * HOUR)
    )
    day0 = assign_device_seq(
        build(latent_day(day_index=0, dispenses=[8 * HOUR]), schedule)
    )
    assert day0.settings["next_cuff_seq"] == 3
    assert day0.settings["next_dispenser_seq"] == 2
    day1 = assign_device_seq(
        build(latent_day(day_index=1, dispenses=[DAY + 8 * HOUR]), schedule),
        cuff_start=int(day0.settings["next_cuff_seq"]),  # type: ignore[call-overload]
        dispenser_start=int(day0.settings["next_dispenser_seq"]),  # type: ignore[call-overload]
    )
    assert [s.seq for s in samples_of(day1, "bp")] == [3, 4]
    assert [e.seq for e in events_of(day1, EventKind.MEASUREMENT)] == [3, 4]
    assert [e.seq for e in events_of(day1, EventKind.DISPENSE)] == [2]
    assert day1.settings["next_cuff_seq"] == 5
    assert day1.settings["next_dispenser_seq"] == 3
    assert assign_device_seq(day1, cuff_start=3, dispenser_start=2) == day1
    # a day with nothing from a device leaves the next numbers where they were
    empty = assign_device_seq(
        build(schedule=Schedule(dose_ticks_ms=(), measurement_ticks_ms=())),
        cuff_start=7,
        dispenser_start=9,
    )
    assert empty.settings["next_cuff_seq"] == 7
    assert empty.settings["next_dispenser_seq"] == 9


@pytest.mark.parametrize(
    "value", [0, -1, True, 1.5, "1", None, 10**400, 2**63, float("nan")]
)
def test_assign_device_seq_validates_the_start_numbers(value: Any) -> None:
    out = build()
    with pytest.raises(MeasurementConfigError):
        assign_device_seq(out, cuff_start=value)
    with pytest.raises(MeasurementConfigError):
        assign_device_seq(out, dispenser_start=value)


def test_observed_stream_defaults_allow_a_hand_written_fixture() -> None:
    bare = ObservedStream("p0000", 0, 0, "plan-1", (), ())
    assert bare.visits == () and bare.measurements == () and dict(bare.settings) == {}
    assert assign_device_seq(bare).settings == {
        "next_cuff_seq": 1,
        "next_dispenser_seq": 1,
    }
    other = ObservedStream("p0000", 0, 0, "plan-1", (), ())
    assert other.settings is not bare.settings  # no shared mutable default


# ---------------------------------------------------------------------------
# Review round 1: unvalidated arguments never reach a raw TypeError
# ---------------------------------------------------------------------------


class PathLikeReturning:
    """A path-like whose ``__fspath__`` misbehaves (a path object is an argument too)."""

    def __init__(self, value: Any) -> None:
        self.value = value

    def __fspath__(self) -> Any:
        if isinstance(self.value, Exception):
            raise self.value
        return self.value


BAD_PATH_LIKES = [
    PathLikeReturning(5),
    PathLikeReturning(None),
    PathLikeReturning(ValueError("embedded")),
    PathLikeReturning(TypeError("not a path")),
]


@pytest.mark.parametrize("path", BAD_PATH_LIKES)
def test_path_like_objects_that_misbehave_are_refused_by_name(path: Any) -> None:
    with pytest.raises(MeasurementConfigError):
        EmpiricalJitter(path)
    with pytest.raises(MeasurementConfigError):
        load_measurement_design(path, inflation_min_ms=0)
    with pytest.raises(SegmentIndexError):
        SegmentIndex.from_file(path)
    with pytest.raises(SegmentIndexError):
        SegmentLibrary(path, SegmentIndex(()))


INLINE_BAD_NUMBERS = [
    5,
    1.5,
    True,
    object(),
    {0.5: 1},  # a mapping is not a sequence of numbers (iterating it gives its keys)
    iter([0.5]),  # nor is an iterator (it would be consumed)
    np.array(0.5),  # a zero-dimensional array has no length
    np.zeros((1, 1)),
    "0.5",
    b"\x01",
]


@pytest.mark.parametrize("bad", INLINE_BAD_NUMBERS)
def test_inline_segment_numbers_must_be_a_sequence_of_numbers(bad: Any) -> None:
    with pytest.raises(SegmentIndexError):
        SegmentLibrary.from_memory(
            [InlineSegment("a", "hr_clean", [1.0], MIN, "bpm", quality=bad)]
        )
    with pytest.raises(SegmentIndexError):
        SegmentLibrary.from_memory([InlineSegment("a", "hr_clean", bad, MIN, "bpm")])


def test_inline_segment_accepts_sequences_and_one_dimensional_arrays() -> None:
    library = SegmentLibrary.from_memory(
        [
            InlineSegment(
                "a",
                "hr_clean",
                np.array([1.0, 2.0]),
                MIN,
                "bpm",
                quality=np.array([0.5, 1.0]),
            ),
            InlineSegment("b", "spo2_clean", (1.0, 2.0), MIN, "%", quality=[0.5, 1.0]),
        ]
    )
    assert library.draw("hr_clean", 2, rng()).quality == (0.5, 1.0)
    assert library.draw("spo2_clean", 2, rng()).values == (1.0, 2.0)


@pytest.mark.parametrize(
    "args",
    [
        (LIB, DESIGN, 0, 0, None),
        (LIB, DESIGN, 0, 0, 1.5),
        (LIB, DESIGN, 0, 0, "1"),
        (LIB, DESIGN, 0, 0, True),
        (LIB, DESIGN, 0, None, 0),
        (LIB, DESIGN, None, 0, 0),
        (LIB, DESIGN, "0", 0, 0),
        (LIB, DESIGN, 0, 0, 10**400),
    ],
)
def test_draw_clean_vitals_day_index_is_an_integer(args: Any) -> None:
    with pytest.raises(MeasurementConfigError):
        draw_clean_vitals(*args)


def stream_with(**changes: Any) -> ObservedStream:
    return dataclasses.replace(build(), **changes)


BAD_STREAMS = [
    stream_with(settings=5),
    stream_with(settings=None),
    stream_with(settings="x"),
    stream_with(settings=[("a", 1)]),  # pairs are not a mapping
    stream_with(settings={1: "x"}),  # the settings are JSON-native: keys are strings
    stream_with(samples=5),
    stream_with(samples=None),
    stream_with(samples=iter(())),
    stream_with(samples="abc"),
    stream_with(events=5),
    stream_with(events=None),
    stream_with(events=iter(())),
    stream_with(samples=(Sample([], 0, 0, 0.0, None, None),)),  # unhashable signal
    stream_with(samples=(Sample(5, 0, 0, 0.0, None, None),)),
    stream_with(events=(Event([], 0, 0, "s", {}, None),)),  # unhashable kind
    stream_with(
        events=(Event("measurement", 0, 0, "s", {}, None),)
    ),  # not an EventKind
]


@pytest.mark.parametrize("bad", BAD_STREAMS)
def test_assign_device_seq_refuses_malformed_stream_members(bad: Any) -> None:
    with pytest.raises(MeasurementConfigError):
        assign_device_seq(bad)


# ---------------------------------------------------------------------------
# Review round 1: duplicate JSON keys are refused, not resolved to the last value
# ---------------------------------------------------------------------------


def test_index_with_a_duplicate_key_is_refused(tmp_path: Path) -> None:
    sha = write_segment(tmp_path, "hr/s1.json", [70.0, 71.0, 72.0])
    plain = json.dumps({"schema_version": "0.1.0", "segments": [entry(sha)]})
    path = tmp_path / "index.json"
    path.write_text(plain, "utf-8")
    assert len(SegmentIndex.from_file(path).entries) == 1  # the control parses
    top = plain[:-1] + ', "segments": []}'
    inner = json.dumps(entry(sha))[:-1] + ', "licence": "other"}'
    nested = '{"schema_version": "0.1.0", "segments": [' + inner + "]}"
    for text in (top, nested):
        path.write_text(text, "utf-8")
        with pytest.raises(SegmentIndexError, match="duplicate"):
            SegmentIndex.from_file(path)


def test_segment_file_with_a_duplicate_key_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "hr" / "s1.json"
    path.parent.mkdir()
    path.write_text('{"values": [70.0, 71.0, 72.0]}', "utf-8")
    index = SegmentIndex.from_mapping(
        {"schema_version": "0.1.0", "segments": [entry(sha_of(path))]}
    )
    assert SegmentLibrary(tmp_path, index).draw("hr_clean", 3, rng()).values == (
        70.0,
        71.0,
        72.0,
    )  # the control parses
    path.write_text(
        '{"values": [1.0, 2.0, 3.0], "values": [70.0, 71.0, 72.0]}', "utf-8"
    )
    index = SegmentIndex.from_mapping(
        {"schema_version": "0.1.0", "segments": [entry(sha_of(path))]}
    )
    with pytest.raises(SegmentIndexError, match="duplicate"):
        SegmentLibrary(tmp_path, index).draw("hr_clean", 3, rng())


def test_jitter_file_with_a_duplicate_key_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "jitter.json"
    path.write_text('{"delays_ms": [5], "source": "x"}', "utf-8")
    assert EmpiricalJitter(path).delays_ms == (5,)  # the control parses
    for text in (
        '{"delays_ms": [0], "delays_ms": [5], "source": "x"}',
        '{"delays_ms": [5], "source": "x", "source": "y"}',
    ):
        path.write_text(text, "utf-8")
        with pytest.raises(MeasurementConfigError, match="duplicate"):
            EmpiricalJitter(path)


# ---------------------------------------------------------------------------
# Review round 1: the seed of the build is the seed of the latent day
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("latent_seed", [1, 2**40, "0", None, 0.0, True])
def test_build_refuses_a_seed_that_differs_from_the_latent_day(
    latent_seed: Any,
) -> None:
    latent = latent_day(seed=latent_seed)
    with pytest.raises(MeasurementConfigError, match="seed"):
        build(latent, keep_latent_seed=True, seed=0)
    ok = build(latent_day(seed=7), seed=7)
    assert ok.seed == 7
    with pytest.raises(MeasurementConfigError, match="seed"):
        build(latent_day(seed=7), keep_latent_seed=True, seed=8)


# ---------------------------------------------------------------------------
# Review round 1: resource bounds, exactly at the limit and one beyond
# ---------------------------------------------------------------------------

MIB = 1024 * 1024


def test_resource_bounds_have_their_documented_values() -> None:
    # a change of one of these is a decision, not a refactoring: the monkeypatched tests
    # below pin how a bound is applied, this one pins what it is
    assert (
        MAX_VISITS_PER_DAY,
        MAX_VITALS_SAMPLES,
        MAX_LATENT_EVENTS,
        MAX_JITTER_FILE_BYTES,
        MAX_JITTER_DELAYS,
    ) == (10_000, 100_000, 400_000, 4 * MIB, 100_000)
    assert (
        MAX_INDEX_BYTES,
        MAX_SEGMENT_FILE_BYTES,
        MAX_SEGMENTS,
        MAX_SEGMENT_SAMPLES,
        MAX_TOTAL_SAMPLES,
        MAX_DRAW_SAMPLES,
        segments_mod.MAX_SAMPLE_PERIOD_MS,
    ) == (4 * MIB, 8 * MIB, 10_000, 500_000, 10_000_000, 500_000, DAY)
    assert measurement_mod.MAX_LATENT_SAMPLES == MAX_GRID_POINTS


def intake_events(n: int) -> tuple[Event, ...]:
    return tuple(
        Event(EventKind.INTAKE, 1_000 + k, 1_000 + k, "patient", {}, None)
        for k in range(n)
    )


def test_latent_event_bound_is_exact(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(measurement_mod, "MAX_LATENT_EVENTS", 5)
    samples = latent_day().samples
    assert build(LatentDay("p0000", 0, 0, samples, intake_events(5)), DOSE_SCHED)
    with pytest.raises(MeasurementConfigError):
        build(LatentDay("p0000", 0, 0, samples, intake_events(6)), DOSE_SCHED)


def test_latent_event_bound_at_its_real_value_is_exact() -> None:
    class Lazy(Sequence[Event]):
        """``n`` copies of one latent INTAKE, built on demand (no 400 000 objects)."""

        def __init__(self, n: int) -> None:
            self.n, self.one = n, intake_events(1)[0]

        def __len__(self) -> int:
            return self.n

        def __getitem__(self, index: Any) -> Event:
            if not 0 <= index < self.n:
                raise IndexError(index)  # ends the iteration of the Sequence mixin
            return self.one

    samples = latent_day().samples
    out = build(LatentDay("p0000", 0, 0, samples, Lazy(MAX_LATENT_EVENTS)))
    assert (
        events_of(out, EventKind.INTAKE) == []
    )  # none is witnessed: no visit near 00:01
    with pytest.raises(MeasurementConfigError):
        build(LatentDay("p0000", 0, 0, samples, Lazy(MAX_LATENT_EVENTS + 1)))


def test_latent_sample_bound_is_exact(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(measurement_mod, "MAX_LATENT_SAMPLES", 3)
    points = [Sample("bp", k, k, 130.0, None, None) for k in range(4)]
    assert LatentSbpHold(points[:3]).last_t_ms == 2
    with pytest.raises(MeasurementConfigError):
        LatentSbpHold(points)


def test_tick_bound_is_exact(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(measurement_mod, "MAX_VISITS_PER_DAY", 3)
    three = Schedule(dose_ticks_ms=(HOUR,), measurement_ticks_ms=(2 * HOUR, 3 * HOUR))
    four = Schedule(
        dose_ticks_ms=(HOUR, 4 * HOUR), measurement_ticks_ms=(2 * HOUR, 3 * HOUR)
    )
    assert len(build(schedule=three).visits) == 3
    with pytest.raises(MeasurementConfigError):
        build(schedule=four)
    # the skipped-tick list is read with the same bound: one more than the ticks is refused
    ticks = (2 * HOUR, 3 * HOUR, 4 * HOUR)
    full = Schedule(dose_ticks_ms=(), measurement_ticks_ms=ticks)
    assert len(build(schedule=full, skip_measurement_ticks_ms=ticks).measurements) == 0
    assert (
        len(build(schedule=full, skip_measurement_ticks_ms=[ticks[0]] * 3).measurements)
        == 2
    )
    with pytest.raises(MeasurementConfigError, match="entries"):
        build(
            schedule=full, skip_measurement_ticks_ms=[ticks[0]] * 4
        )  # valid but too many


def test_vitals_sample_bound_is_exact(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(measurement_mod, "MAX_VITALS_SAMPLES", DAY // MIN)
    assert dataclasses.replace(DESIGN, vitals_period_ms=MIN).vitals_points == DAY // MIN
    monkeypatch.setattr(measurement_mod, "MAX_VITALS_SAMPLES", DAY // MIN - 1)
    with pytest.raises(MeasurementConfigError):
        dataclasses.replace(DESIGN, vitals_period_ms=MIN)


def test_jitter_delay_count_bound_is_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(measurement_mod, "MAX_JITTER_DELAYS", 3)
    assert len(EmpiricalJitter(write_jitter(tmp_path, [0, 1, 2])).delays_ms) == 3
    with pytest.raises(MeasurementConfigError):
        EmpiricalJitter(write_jitter(tmp_path, [0, 1, 2, 3]))


def test_jitter_file_size_bound_is_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = b'{"delays_ms": [1], "source": "x"}'
    path = tmp_path / "jitter.json"
    path.write_bytes(body)
    monkeypatch.setattr(measurement_mod, "MAX_JITTER_FILE_BYTES", len(body))
    assert EmpiricalJitter(path).delays_ms == (1,)  # exactly at the limit
    path.write_bytes(body + b" ")
    with pytest.raises(MeasurementConfigError):
        EmpiricalJitter(path)  # one byte beyond


def seg_entry(i: int, n: int = 3, kind: str = "hr_clean") -> SegmentEntry:
    return SegmentEntry(
        f"s{i}", "d", "r", kind, MIN, n, "bpm", f"p/s{i}.json", "0" * 64, "l"
    )


def test_index_size_bound_is_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sha = write_segment(tmp_path, "hr/s1.json", [70.0, 71.0, 72.0])
    path = write_index(tmp_path, [entry(sha)])
    size = path.stat().st_size
    monkeypatch.setattr(segments_mod, "MAX_INDEX_BYTES", size)
    assert len(SegmentIndex.from_file(path).entries) == 1
    monkeypatch.setattr(segments_mod, "MAX_INDEX_BYTES", size - 1)
    with pytest.raises(SegmentIndexError):
        SegmentIndex.from_file(path)


def test_segment_file_size_bound_is_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sha = write_segment(tmp_path, "hr/s1.json", [70.0, 71.0, 72.0])
    index = SegmentIndex.from_mapping(
        {"schema_version": "0.1.0", "segments": [entry(sha)]}
    )
    size = (tmp_path / "hr" / "s1.json").stat().st_size
    monkeypatch.setattr(segments_mod, "MAX_SEGMENT_FILE_BYTES", size)
    assert SegmentLibrary(tmp_path, index).draw("hr_clean", 3, rng()).values[0] == 70.0
    monkeypatch.setattr(segments_mod, "MAX_SEGMENT_FILE_BYTES", size - 1)
    with pytest.raises(SegmentIndexError):
        SegmentLibrary(tmp_path, index)


def test_segment_count_bound_is_exact(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(segments_mod, "MAX_SEGMENTS", 2)
    assert len(SegmentIndex(tuple(seg_entry(i) for i in range(2))).entries) == 2
    with pytest.raises(SegmentIndexError):
        SegmentIndex(tuple(seg_entry(i) for i in range(3)))
    raw = [entry("0" * 64, segment_id=f"s{i}", path=f"hr/s{i}.json") for i in range(3)]
    ok = {"schema_version": "0.1.0", "segments": raw[:2]}
    assert len(SegmentIndex.from_mapping(ok).entries) == 2
    with pytest.raises(SegmentIndexError):
        SegmentIndex.from_mapping({"schema_version": "0.1.0", "segments": raw})


def test_total_sample_bound_is_exact(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(segments_mod, "MAX_TOTAL_SAMPLES", 6)
    assert SegmentIndex((seg_entry(0, 3), seg_entry(1, 3)))
    with pytest.raises(SegmentIndexError):
        SegmentIndex((seg_entry(0, 3), seg_entry(1, 4)))


def test_samples_per_segment_bound_is_exact(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(segments_mod, "MAX_SEGMENT_SAMPLES", 3)
    assert seg_entry(0, 3).n_samples == 3
    with pytest.raises(SegmentIndexError):
        seg_entry(0, 4)
    assert (
        SegmentLibrary.from_memory(
            [InlineSegment("a", "hr_clean", [1.0, 2.0, 3.0], MIN, "bpm")]
        )
        .index.entries[0]
        .n_samples
        == 3
    )
    with pytest.raises(SegmentIndexError):
        SegmentLibrary.from_memory(
            [InlineSegment("a", "hr_clean", [1.0, 2.0, 3.0, 4.0], MIN, "bpm")]
        )


def test_draw_size_and_period_bounds_are_exact(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(segments_mod, "MAX_DRAW_SAMPLES", 3)
    library = SegmentLibrary.from_memory(
        [InlineSegment("a", "hr_clean", [1.0, 2.0, 3.0, 4.0], MIN, "bpm")]
    )
    assert len(library.draw("hr_clean", 3, rng()).values) == 3
    with pytest.raises(SegmentUnavailableError):
        library.draw("hr_clean", 4, rng())
    monkeypatch.setattr(segments_mod, "MAX_SAMPLE_PERIOD_MS", MIN)
    assert seg_entry(0).sample_period_ms == MIN
    with pytest.raises(SegmentIndexError):
        SegmentEntry(
            "s", "d", "r", "hr_clean", MIN + 1, 3, "bpm", "p/s.json", "0" * 64, "l"
        )


# ---------------------------------------------------------------------------
# Review round 1: boundaries, ties and the kind of file that is read
# ---------------------------------------------------------------------------


def test_reading_at_the_closing_instant_is_not_past_the_day_end() -> None:
    sched = Schedule(dose_ticks_ms=(), measurement_ticks_ms=(DAY - 30 * SEC,))
    exact = build(
        schedule=sched
    )  # inflation 30 s: the reading is stamped at DAY exactly
    assert exact.measurements[0].t_ms == DAY
    assert exact.settings["n_measurements_after_day_end"] == 0
    late = build(
        schedule=sched,
        design=dataclasses.replace(DESIGN, inflation_ms_nominal=30 * SEC + 1),
    )
    assert late.measurements[0].t_ms == DAY + 1
    assert late.settings["n_measurements_after_day_end"] == 1


def test_segment_source_is_none_when_no_vitals_segment_is_used() -> None:
    noise_only = SegmentLibrary.from_memory(
        [InlineSegment("n", "hr_error_ecg_noise", [0.0, 1.0], MIN, "bpm")]
    )
    assert noise_only.descriptor != "none"  # the library is not empty
    out = build(library=noise_only, allow_no_segments=True)
    assert out.settings["segment_source"] == "none"
    assert samples_of(out, "hr_ecg") == [] and samples_of(out, "hr_pulse") == []
    assert build().settings["segment_source"] == LIB.descriptor


def test_a_segment_exactly_as_long_as_the_request_is_long_enough() -> None:
    library = SegmentLibrary.from_memory(
        [
            InlineSegment("short1", "hr_clean", [1.0, 2.0], MIN, "bpm"),
            InlineSegment("short2", "hr_clean", [3.0, 4.0], MIN, "bpm"),
            InlineSegment("exact", "hr_clean", [5.0, 6.0, 7.0], MIN, "bpm"),
        ]
    )
    for seed in range(40):
        draw = library.draw("hr_clean", 3, rng(seed))
        assert draw.segment_ids == ("exact",), seed
        assert draw.join_count == 0 and draw.values == (5.0, 6.0, 7.0)
    assert library.draw("hr_clean", 4, rng(0)).join_count >= 1  # one more is a join


class DoseAfterMeasurement:
    """Dose visit arrives at the end of the day, measurement visit 30 s before it."""

    descriptor = "tie"

    def delay_ms(self, rng: np.random.Generator, *, kind: str, index: int) -> int:
        return HOUR if kind == vocab.KIND_DOSE else 0


def test_items_at_the_closing_instant_come_before_day_end() -> None:
    schedule = Schedule(
        dose_ticks_ms=(23 * HOUR,), measurement_ticks_ms=(DAY - 30 * SEC,)
    )
    out = build(
        latent_day(dispenses=[DAY], intakes=[DAY]),
        schedule,
        jitter=DoseAfterMeasurement(),
    )
    # presence (dose visit arrives at DAY), the cuff message (reading at DAY), then day_end
    assert [s.signal for s in out.samples if s.t_device_ms == DAY] == [
        "presence",
        "bp",
        "inflation_ms",
        "cuff_health",
        "hr_pulse",
        "day_end",
    ]
    assert [e.kind for e in out.events if e.t_device_ms == DAY] == [
        EventKind.ROBOT_TASK,
        EventKind.MEASUREMENT,
        EventKind.DISPENSE,
        EventKind.INTAKE,
    ]
    assert out.samples[-1].signal == "day_end"


def test_schedule_ticks_at_one_instant_put_the_dose_first() -> None:
    sched = Schedule(
        dose_ticks_ms=(8 * HOUR, 12 * HOUR), measurement_ticks_ms=(8 * HOUR, 12 * HOUR)
    )
    out = build(latent_day(), sched)
    ticks = events_of(out, EventKind.SCHEDULE_TICK)
    assert [(e.t_device_ms, e.payload["kind"]) for e in ticks] == [
        (8 * HOUR, vocab.KIND_DOSE),
        (8 * HOUR, vocab.KIND_MEASUREMENT),
        (12 * HOUR, vocab.KIND_DOSE),
        (12 * HOUR, vocab.KIND_MEASUREMENT),
    ]
    assert [(v.kind, v.index) for v in out.visits] == [
        (vocab.KIND_DOSE, 0),
        (vocab.KIND_MEASUREMENT, 0),
        (vocab.KIND_DOSE, 1),
        (vocab.KIND_MEASUREMENT, 1),
    ]


def test_special_files_are_refused_without_being_opened(tmp_path: Path) -> None:
    """A FIFO has size 0 and blocks a reader that opens it: the kind of file is checked first.

    The check runs in a child process with a timeout, so a regression that opens the FIFO
    fails this test instead of blocking the suite.
    """
    if not hasattr(os, "mkfifo"):
        pytest.skip("no named pipes on this platform")
    fifo_index = tmp_path / "index.json"
    fifo_segment = tmp_path / "hr" / "s1.json"
    fifo_jitter = tmp_path / "jitter.json"
    fifo_segment.parent.mkdir()
    for fifo in (fifo_index, fifo_segment, fifo_jitter):
        os.mkfifo(fifo)
    code = (
        "import sys\n"
        "from ralmon.benchmark.measurement import EmpiricalJitter, MeasurementConfigError\n"
        "from ralmon.benchmark.segments import SegmentIndex, SegmentIndexError, SegmentLibrary\n"
        "root, = sys.argv[1:]\n"
        "def attempt(name, call, error):\n"
        "    try:\n"
        "        call()\n"
        "    except error:\n"
        "        print(name, 'refused')\n"
        "attempt('index', lambda: SegmentIndex.from_file(root + '/index.json'), SegmentIndexError)\n"
        "attempt('jitter', lambda: EmpiricalJitter(root + '/jitter.json'), MeasurementConfigError)\n"
        "index = SegmentIndex.from_mapping({'schema_version': '0.1.0', 'segments': [{\n"
        "    'segment_id': 's1', 'dataset': 'd', 'record_id': 'r', 'kind': 'hr_clean',\n"
        "    'sample_period_ms': 60000, 'n_samples': 3, 'unit': 'bpm', 'path': 'hr/s1.json',\n"
        "    'sha256': '0' * 64, 'licence': 'l'}]})\n"
        "attempt('segment', lambda: SegmentLibrary(root, index), SegmentIndexError)\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 0, done.stderr[-500:]
    assert done.stdout.split("\n")[:-1] == [
        "index refused",
        "jitter refused",
        "segment refused",
    ]


def test_observed_stream_carries_latent_values_only_in_generator_side_records() -> None:
    stream_fields = {f.name for f in dataclasses.fields(ObservedStream)}
    assert stream_fields == {
        "patient_id",
        "day_index",
        "seed",
        "care_plan_id",
        "samples",
        "events",
        "visits",
        "measurements",
        "settings",
    }
    latent_named = {
        (cls.__name__, f.name)
        for cls in (
            ObservedStream,
            measurement_mod.RobotVisit,
            measurement_mod.MeasurementRecord,
            measurement_mod.CleanVitals,
        )
        for f in dataclasses.fields(cls)
        if "latent" in f.name
    }
    assert latent_named == {("MeasurementRecord", "latent_sbp_mmhg")}
    # the monitor-facing record has no place for it, nor for the generator-side members
    day_fields = {f.name for f in dataclasses.fields(ObservedDay)}
    assert day_fields == {
        "patient_id",
        "day_index",
        "seed",
        "samples",
        "events",
        "care_plan_id",
    }
    assert not any("latent" in name for name in day_fields)
    assert not day_fields & {"measurements", "visits", "settings"}
    # nothing observed (samples, events, settings) mentions the latent pressure
    out = build(
        latent_day(sbp=131.25), SCHED_BOTH, errors=DeviceErrorModel(0.0, 3.0, 0.0, 0.0)
    )
    assert out.measurements and all(
        m.latent_sbp_mmhg != m.value_mmhg for m in out.measurements
    )
    assert "latent" not in repr(out.samples) + repr(out.events) + repr(out.settings)
    # (there is no ObservedStream -> ObservedDay conversion yet: WS04-T11 builds the monitor-
    # facing day from ``samples`` and ``events`` only; this test then extends to that call)
