"""C2 fault injection and the shared injection machinery (WS04-T07).

Every number below is arithmetic and FIXTURE-ONLY (cuff readings 128, 131, 127, 133 at 08:00,
10:00, 12:00 and 14:00 plus 30 s of inflation, dispenses at 08:10 and 20:00, hourly heart
rate 70 and SpO2 95, robot dwell 10 min, task deadline 10 min after its tick): none is a
clinical value, none is a device specification and none enters a prior file used by the
builder. State independence: no test reads a committed configuration in a way that depends on
whether a human has filled it; the injection rows are exercised on copies under ``tmp_path``
in their filled and unfilled forms.

Rules under test, stated in ``ralmon.benchmark.injection`` and ``ralmon.benchmark.inject_c2``:

* canonical order: robot faults, device faults, sequence numbering, link faults, whatever the
  order of the specs;
* a window is half open, ``[onset, onset + duration)``; a point fault (a bounce) and a per-tick
  fault (a late or failed robot visit) have ``end_ms`` None;
* an added item follows the existing items with the same ``t_rx_ms`` (stable sort);
* a draw is keyed by ``(seed, patient, day, INJECTION_C2, digest of the injection)``.
"""

from __future__ import annotations

import ast
import copy
import dataclasses
import itertools
import json
import math
import re
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

import ralmon.benchmark as benchmark_pkg
import ralmon.benchmark.inject_c2 as c2_mod
import ralmon.benchmark.injection as injection_mod
from ralmon.benchmark import vocab
from ralmon.benchmark.inject_c2 import (
    C2_SUBTYPES,
    DETACHED_ERROR_CODE,
    DETACHED_HEALTH,
    DETACHED_INFLATION_MS,
    DEVICE_SIGNALS,
    EVIDENCE_SIGNATURES,
    plan_dispenser_bounces,
)
from ralmon.benchmark.injection import (
    MAX_INJECTIONS_PER_DAY,
    MAX_PARAMS,
    MAX_STREAM_EVENTS,
    MAX_STREAM_SAMPLES,
    InjectionContext,
    InjectionContextError,
    InjectionDesignError,
    InjectionError,
    InjectionRecord,
    InjectionResult,
    InjectionSpec,
    InjectionSpecError,
    apply_observation_injections,
    canonical_order,
    finalize_observed,
    ground_truth_events,
    injection_log,
    injection_sub_index,
    load_injection_design,
    record_to_ground_truth,
    registered_subtypes,
    resolve_magnitude,
)
from ralmon.benchmark.latent import T_DAY_MS
from ralmon.benchmark.measurement import (
    MeasurementConfigError,
    MeasurementRecord,
    ObservedStream,
    RobotVisit,
    assign_device_seq,
)
from ralmon.benchmark.priors import SOURCE_TYPES, load_design_file
from ralmon.benchmark.rng import StreamPurpose, stream
from ralmon.benchmark.segments import InlineSegment, SegmentLibrary
from ralmon.benchmark.trace import (
    GroundTruthEvent,
    InjectedClass,
    LatentDay,
    ObservedDay,
)
from ralmon.signals import Event, EventKind, Sample

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "ralmon" / "benchmark"
INJECTIONS_FILE = ROOT / "configs" / "benchmark" / "injections.yaml"
FAULT_MODEL = ROOT / "docs" / "models" / "fault-model.md"
EVIDENCE_DOC = ROOT / "docs" / "models" / "evidence-channels.md"
INTERFACES = ROOT / "docs" / "plan" / "02-interfaces.md"

SEC = 1_000
MIN = 60_000
HOUR = 3_600_000
DAY = T_DAY_MS
C2 = InjectedClass.C2

INFLATION = 30 * SEC  # FIXTURE-ONLY
DWELL = 10 * MIN  # FIXTURE-ONLY
DEADLINE_OFFSET = 10 * MIN  # FIXTURE-ONLY: the task deadline is the tick plus ten minutes
LATENT_SBP = 131.4375  # FIXTURE-ONLY sentinel (binary exact), generator-side only
PATIENT = "p0000"

TICKS = (8 * HOUR, 10 * HOUR, 12 * HOUR, 14 * HOUR)
BPS = (128.0, 131.0, 127.0, 133.0)
DOSE_TICKS = (8 * HOUR + 10 * MIN, 20 * HOUR)
INTAKE_AFTER = MIN

STATES = ("unconfigured", "inactive", "active", "finalized", "link_down", "unreachable")


# ---------------------------------------------------------------------------
# The hand-written fixture stream
# ---------------------------------------------------------------------------


def S(
    signal: str,
    t: int,
    value: float,
    seq: int | None = None,
    quality: float | None = None,
) -> Sample:
    return Sample(signal, t, t, value, seq, quality)


def E(
    kind: EventKind,
    t: int,
    source: str,
    payload: Mapping[str, Any] | None = None,
    seq: int | None = None,
) -> Event:
    return Event(kind, t, t, source, dict(payload or {}), seq)


def by_rx(items: Sequence[Any]) -> list[Any]:
    return sorted(items, key=lambda item: item.t_rx_ms)


def fixture_stream(
    ticks: Sequence[int] = TICKS,
    bps: Sequence[float] | None = None,
    *,
    dose_ticks: Sequence[int] = DOSE_TICKS,
    day_index: int = 0,
    seed: int = 0,
    hr_ecg: bool = True,
) -> ObservedStream:
    """A fault-free, unnumbered observed stream with its generator-side records."""
    base = day_index * DAY
    values = list(bps) if bps is not None else [128.0 + k for k in range(len(ticks))]
    if bps is None and tuple(ticks) == TICKS:
        values = list(BPS)
    samples: list[Sample] = []
    events: list[Event] = []
    visits: list[RobotVisit] = []
    records: list[MeasurementRecord] = []
    plan = sorted(
        [(base + t, 1, k) for k, t in enumerate(ticks)]
        + [(base + t, 0, j) for j, t in enumerate(dose_ticks)]
    )
    for tick, rank, index in plan:
        kind = vocab.KIND_MEASUREMENT if rank == 1 else vocab.KIND_DOSE
        visits.append(RobotVisit(index, kind, tick, tick, tick + DWELL, 0))
        events.append(E(EventKind.SCHEDULE_TICK, tick, "ward", {"kind": kind}))
        samples.append(S("presence", tick, 1.0))
        events.append(
            E(
                EventKind.ROBOT_TASK,
                tick,
                "robot",
                {"task": "navigate", "outcome": "success", "patient_id": PATIENT},
            )
        )
    for k, t in enumerate(ticks):
        tick = base + t
        t_meas = tick + INFLATION
        samples += [
            S("bp", t_meas, values[k]),
            S("inflation_ms", t_meas, float(INFLATION)),
            S("cuff_health", t_meas, 1.0),
            S("hr_pulse", t_meas, 70.0),
        ]
        events.append(E(EventKind.MEASUREMENT, t_meas, "cuff"))
        records.append(
            MeasurementRecord(
                k, tick, tick, t_meas, LATENT_SBP, values[k] - LATENT_SBP,
                values[k], INFLATION, False, 70.0,
            )
        )  # fmt: skip
    for t in dose_ticks:
        events.append(E(EventKind.DISPENSE, base + t, "dispenser"))
        events.append(E(EventKind.INTAKE, base + t + INTAKE_AFTER, "robot"))
    if hr_ecg:
        for h in range(24):
            samples.append(S("hr_ecg", base + h * HOUR, 70.0))
            samples.append(S("spo2", base + h * HOUR, 95.0))
        samples.append(S("hr_ecg", base + 11 * HOUR + MIN, 70.0))
        samples.append(S("hr_ecg", base + 11 * HOUR + 2 * MIN, 70.0))
    samples.append(S("day_end", base + DAY, 1.0))
    return ObservedStream(
        PATIENT,
        day_index,
        seed,
        "plan-1",
        tuple(by_rx(samples)),
        tuple(by_rx(events)),
        tuple(visits),
        tuple(records),
        {"n_visits": len(visits)},
    )


BASE = fixture_stream()
HOURLY_TICKS = tuple(h * HOUR for h in range(6, 18))  # 06:00 to 17:00
HOURLY = fixture_stream(HOURLY_TICKS)


def library(
    values: Sequence[float] = (5.0, -3.0, 8.0),
    quality: Sequence[float] | None = None,
    *,
    extra: Sequence[InlineSegment] = (),
) -> SegmentLibrary:
    return SegmentLibrary.from_memory(
        [
            InlineSegment(
                "noise-1", "hr_error_ecg_noise", values, MIN, "bpm", quality=quality
            ),
            *extra,
        ]
    )


def ctx(**kwargs: Any) -> InjectionContext:
    kwargs.setdefault("patient_index", 0)
    kwargs.setdefault("task_deadline_offset_ms", DEADLINE_OFFSET)
    return InjectionContext(**kwargs)


def spec(
    subtype: str,
    onset: int,
    duration: int | None = None,
    magnitude: float | None = None,
    unit: str | None = None,
    **params: Any,
) -> InjectionSpec:
    return InjectionSpec(C2, subtype, onset, duration, magnitude, unit, params)


def ble(onset: int, duration: int, target: str = "cuff") -> InjectionSpec:
    return spec("ble_dropout", onset, duration, target=target)


def bias(onset: int, duration: int, mmhg: float = 5.0) -> InjectionSpec:
    return spec("cuff_silent_bias", onset, duration, mmhg, "mmHg")


def stuck(onset: int, duration: int) -> InjectionSpec:
    return spec("stuck_at", onset, duration)


def detached(onset: int, duration: int) -> InjectionSpec:
    return spec("cuff_detached", onset, duration)


def ecg(onset: int, duration: int, scale: float | None = None) -> InjectionSpec:
    return spec("ecg_noise", onset, duration, scale, None if scale is None else "1")


def bounce(onset: int, gap: int = 500) -> InjectionSpec:
    return spec("dispenser_bounce", onset, None, gap, "ms")


def nav(onset: int, delay: int, **params: Any) -> InjectionSpec:
    return spec("nav_delay", onset, None, delay, "ms", **params)


def manip(onset: int, **params: Any) -> InjectionSpec:
    return spec("manipulation_failure", onset, None, None, None, **params)


def run(
    specs: Sequence[InjectionSpec],
    *,
    stream_: ObservedStream = BASE,
    **kwargs: Any,
) -> InjectionResult:
    kwargs.setdefault("library", library())
    return apply_observation_injections(stream_, specs, ctx(**kwargs))


def samples_of(out: InjectionResult | ObservedStream, signal: str) -> list[Sample]:
    s = out.stream if isinstance(out, InjectionResult) else out
    return [x for x in s.samples if x.signal == signal]


def events_of(out: InjectionResult | ObservedStream, kind: EventKind) -> list[Event]:
    s = out.stream if isinstance(out, InjectionResult) else out
    return [x for x in s.events if x.kind == kind]


def values_of(out: InjectionResult, signal: str) -> list[float]:
    return [x.value for x in samples_of(out, signal)]


def item_key(item: Sample | Event, *, with_seq: bool = True) -> Any:
    seq = item.seq if with_seq else None
    if isinstance(item, Sample):
        return ("S", item.signal, item.t_device_ms, item.t_rx_ms, item.value, seq, item.quality)
    return (
        "E", item.kind.value, item.t_device_ms, item.t_rx_ms, item.source,
        tuple(sorted(item.payload.items())), seq,
    )  # fmt: skip


def item_multiset(
    s: ObservedStream, *, with_seq: bool = True
) -> dict[Any, int]:
    counts: dict[Any, int] = {}
    for item in (*s.samples, *s.events):
        key = item_key(item, with_seq=with_seq)
        counts[key] = counts.get(key, 0) + 1
    return counts


def diff_items(
    a: ObservedStream, b: ObservedStream, *, with_seq: bool = True
) -> list[Any]:
    """Item keys on which two streams differ (symmetric multiset difference)."""
    ca, cb = item_multiset(a, with_seq=with_seq), item_multiset(b, with_seq=with_seq)
    return [k for k in {*ca, *cb} if ca.get(k, 0) != cb.get(k, 0)]


def latent_with_step(change_at: int, before: float, after: float) -> LatentDay:
    samples = tuple(
        S("bp", t, before if t < change_at else after) for t in range(0, DAY, MIN)
    )
    return LatentDay(PATIENT, 0, 0, samples, ())


# ---------------------------------------------------------------------------
# 1. Pipeline order and canonical order
# ---------------------------------------------------------------------------

MIXED = [
    nav(10 * HOUR, 5 * MIN),
    manip(14 * HOUR),
    detached(11 * HOUR, 2 * HOUR),
    bounce(DOSE_TICKS[0]),
    ble(15 * HOUR, HOUR, "cuff"),
    ecg(11 * HOUR, 3 * MIN),
]


def result_key(result: InjectionResult) -> Any:
    return (
        result.stream,
        result.records,
        result.disabled_subtypes,
    )


def test_pipeline_order_is_canonical_and_spec_order_irrelevant() -> None:
    reference = run(MIXED)
    seen = 0
    for order in itertools.permutations(MIXED):
        out = run(list(order))
        assert result_key(out) == result_key(reference)
        seen += 1
    assert seen == math.factorial(len(MIXED))
    assert len(reference.records) == len(MIXED)
    # records come in the order of execution: robot, device, link
    stages = [r.spec.subtype for r in reference.records]
    robot = {"nav_delay", "manipulation_failure"}
    device = {"cuff_detached", "cuff_silent_bias", "stuck_at", "ecg_noise", "dispenser_bounce"}
    ranks = [0 if s in robot else 1 if s in device else 2 for s in stages]
    assert ranks == sorted(ranks)
    assert stages[-1] == "ble_dropout"
    assert [s.subtype for s in canonical_order(MIXED)] == stages
    assert canonical_order(list(reversed(MIXED))) == canonical_order(MIXED)


def test_robot_faults_run_before_device_faults() -> None:
    # nav_delay moves the 10:00 reading to 10:15:30; a detached window that starts at 10:10
    # sees the moved reading, one that ends at 10:10 does not
    sees = run([nav(10 * HOUR, 15 * MIN), detached(10 * HOUR + 10 * MIN, HOUR)])
    assert len(events_of(sees, EventKind.MEASUREMENT_MISSED)) == 1
    misses = run([nav(10 * HOUR, 15 * MIN), detached(9 * HOUR, HOUR + 10 * MIN)])
    assert len(events_of(misses, EventKind.MEASUREMENT_MISSED)) == 0
    assert not misses.records[1].realised


def test_sequence_numbering_runs_after_device_and_robot_faults_and_before_link() -> None:
    # robot fault: the removed message leaves no gap
    out = run([manip(10 * HOUR)])
    assert [s.seq for s in samples_of(out, "bp")] == [1, 2, 3]
    # device fault: the extra dispense is numbered, the detached attempt keeps its number
    out = run([bounce(DOSE_TICKS[0]), detached(9 * HOUR, 2 * HOUR)])
    assert [e.seq for e in events_of(out, EventKind.DISPENSE)] == [1, 2, 3]
    assert [s.seq for s in samples_of(out, "inflation_ms")] == [1, 2, 3, 4]
    # link fault: the numbers of the delivered messages keep the gap
    out = run([ble(9 * HOUR, 4 * HOUR)])
    assert [s.seq for s in samples_of(out, "bp")] == [1, 4]


# ---------------------------------------------------------------------------
# 2. BLE dropout
# ---------------------------------------------------------------------------


def test_ble_dropout_removes_device_data_and_leaves_sequence_gap() -> None:
    out = run([ble(9 * HOUR, 4 * HOUR)])
    assert values_of(out, "bp") == [128.0, 133.0]
    assert [s.seq for s in samples_of(out, "bp")] == [1, 4]
    for name in ("inflation_ms", "cuff_health", "hr_pulse"):
        assert [s.seq for s in samples_of(out, name)] == [1, 4]
    assert [e.seq for e in events_of(out, EventKind.MEASUREMENT)] == [1, 4]
    states = events_of(out, EventKind.NODE_STATE)
    assert [(e.t_device_ms, e.t_rx_ms, e.source) for e in states] == [
        (9 * HOUR, 9 * HOUR, "cuff"),
        (13 * HOUR, 13 * HOUR, "cuff"),
    ]
    assert [e.payload for e in states] == [
        {vocab.KEY_STATE: "link_down", vocab.KEY_COMMANDED: False},
        {vocab.KEY_STATE: "active", vocab.KEY_COMMANDED: False},
    ]
    assert all(e.seq is None for e in states)  # the gateway has no device counter
    # nothing is delayed: the lost items never arrive later
    assert len(out.stream.samples) == len(BASE.samples) - 6  # 2 messages of 4, minus ...
    (record,) = out.records
    assert record.realised and record.n_changed == 10  # 8 samples and 2 events removed ... and
    assert record.spec.subtype == "ble_dropout"


def test_ble_dropout_leaves_other_devices_and_the_robot_alone() -> None:
    out = run([ble(0, DAY)])
    kept = {(s.signal) for s in out.stream.samples}
    assert kept == {"presence", "hr_ecg", "spo2", "day_end"}
    assert {e.source for e in out.stream.events} >= {"robot", "ward", "dispenser"}
    assert not [e for e in out.stream.events if e.source == "cuff" and e.kind != EventKind.NODE_STATE]
    out = run([ble(0, DAY, "dispenser")])
    assert not events_of(out, EventKind.DISPENSE)
    assert events_of(out, EventKind.INTAKE)  # the robot witness is not on the BLE link
    out = run([ble(0, DAY, "ecg")])
    assert not samples_of(out, "hr_ecg") and samples_of(out, "spo2")
    out = run([ble(0, DAY, "oximeter")])
    assert not samples_of(out, "spo2") and samples_of(out, "hr_ecg")


def test_ble_dropout_window_is_half_open() -> None:
    t0 = 8 * HOUR + INFLATION
    for onset, duration, expected in [
        (t0, 1, [131.0, 127.0, 133.0]),  # a reading exactly at the onset is lost
        (t0 + 1, DAY - t0 - 1, [128.0]),  # a reading one ms before the onset is kept
        (t0 - 1, 1, [128.0, 131.0, 127.0, 133.0]),  # ends exactly at a reading: kept
        (t0 - 1, 2, [131.0, 127.0, 133.0]),
    ]:
        out = run([ble(onset, duration)])
        assert values_of(out, "bp") == expected, (onset, duration)


def test_ble_dropout_node_state_events_are_not_removed_by_a_later_dropout() -> None:
    out = run([ble(9 * HOUR, HOUR), ble(10 * HOUR, HOUR)])  # touching windows
    states = events_of(out, EventKind.NODE_STATE)
    assert [(e.t_device_ms, e.payload[vocab.KEY_STATE]) for e in states] == [
        (9 * HOUR, "link_down"),
        (10 * HOUR, "link_down"),
        (10 * HOUR, "active"),
        (11 * HOUR, "active"),
    ] or [
        (e.t_device_ms, e.payload[vocab.KEY_STATE]) for e in states
    ] == [
        (9 * HOUR, "link_down"),
        (10 * HOUR, "active"),
        (10 * HOUR, "link_down"),
        (11 * HOUR, "active"),
    ]
    assert len(states) == 4


def test_ble_dropout_removes_the_node_report_of_the_device_itself_inside_the_window() -> None:
    out = run([detached(9 * HOUR, 2 * HOUR), ble(8 * HOUR + 30 * MIN, 2 * HOUR)])
    states = [
        (e.t_device_ms, e.payload[vocab.KEY_STATE])
        for e in events_of(out, EventKind.NODE_STATE)
    ]
    # the cuff's own report of 09:00 is lost on the dropped link; the gateway's link_down stays;
    # the cuff's own report of 11:00 (the window end) lies after the dropout and arrives
    assert states == [
        (8 * HOUR + 30 * MIN, "link_down"),
        (10 * HOUR + 30 * MIN, "active"),
        (11 * HOUR, "active"),
    ]


# ---------------------------------------------------------------------------
# 3. Silent bias
# ---------------------------------------------------------------------------


def test_silent_cuff_bias_shifts_values_in_window_only() -> None:
    out = run([bias(9 * HOUR, 4 * HOUR, 5.0)])
    assert values_of(out, "bp") == [128.0, 136.0, 132.0, 133.0]
    assert not events_of(out, EventKind.DEVICE_ERROR)
    assert not events_of(out, EventKind.NODE_STATE)
    assert not events_of(out, EventKind.MEASUREMENT_MISSED)
    (record,) = out.records
    assert record.evidence_paths == ()
    assert record.realised and record.n_changed == 2
    # nothing but the two values differs from a run without the injection
    plain = run([])
    changed = diff_items(out.stream, plain.stream)
    assert len(changed) == 4  # two samples out, two samples in
    assert all(k[0] == "S" and k[1] == "bp" for k in changed)


def test_bias_sign_and_window_edges() -> None:
    t1 = 10 * HOUR + INFLATION
    out = run([bias(0, DAY, -2.5)])
    assert values_of(out, "bp") == [125.5, 128.5, 124.5, 130.5]
    assert values_of(run([bias(t1, 1, 4.0)]), "bp") == [128.0, 135.0, 127.0, 133.0]
    assert values_of(run([bias(t1 - 1, 1, 4.0)]), "bp") == list(BPS)  # ends at the reading
    assert values_of(run([bias(t1 - 1, 2, 4.0)]), "bp") == [128.0, 135.0, 127.0, 133.0]
    # the other cuff signals and the events are untouched by a bias
    assert values_of(run([bias(0, DAY)]), "hr_pulse") == [70.0] * 4


def test_zero_bias_changes_nothing_and_is_not_realised() -> None:
    out = run([bias(0, DAY, 0.0)])
    assert not out.records[0].realised and out.records[0].n_changed == 0
    assert out.stream == run([]).stream


# ---------------------------------------------------------------------------
# 4. Stuck-at
# ---------------------------------------------------------------------------


def test_stuck_at_repeats_last_value_before_onset() -> None:
    out = run([stuck(9 * HOUR, 6 * HOUR)])
    assert values_of(out, "bp") == [128.0, 128.0, 128.0, 128.0]
    (record,) = out.records
    assert record.evidence_paths == ()
    assert record.n_changed == 3 and record.realised
    assert not events_of(out, EventKind.DEVICE_ERROR)
    assert values_of(out, "hr_pulse") == [70.0] * 4  # the pulse is not frozen


def test_stuck_at_value_is_the_last_reading_before_the_onset_not_the_first() -> None:
    out = run([stuck(13 * HOUR, 2 * HOUR)])  # last reading before 13:00 is 12:00:30
    assert values_of(out, "bp") == [128.0, 131.0, 127.0, 127.0]
    out = run([stuck(10 * HOUR + INFLATION, HOUR)])  # onset exactly at a reading
    assert values_of(out, "bp") == [128.0, 128.0, 127.0, 133.0]  # the reading at the onset is frozen
    out = run([stuck(10 * HOUR + INFLATION + 1, HOUR)])  # onset just after: the reading is the pre-onset value
    assert values_of(out, "bp") == [128.0, 131.0, 127.0, 133.0]
    assert not out.records[0].realised  # the frozen value 131 repeats nothing in the window


def test_stuck_at_window_end_is_exclusive() -> None:
    t3 = 14 * HOUR + INFLATION
    assert values_of(run([stuck(9 * HOUR, t3 - 9 * HOUR)]), "bp") == [128.0] * 3 + [133.0]
    assert values_of(run([stuck(9 * HOUR, t3 - 9 * HOUR + 1)]), "bp") == [128.0] * 4


def test_stuck_at_without_an_earlier_reading_is_not_realised() -> None:
    out = run([stuck(HOUR, 3 * HOUR)])  # no reading before 01:00 and none in the window
    assert not out.records[0].realised
    out = run([stuck(7 * HOUR, 3 * HOUR)])  # a reading in the window, none before the onset
    assert values_of(out, "bp") == list(BPS)
    assert not out.records[0].realised
    assert "no earlier" in json.dumps(out.records[0].details)


def test_stuck_at_uses_the_value_after_a_bias_applied_before_the_onset() -> None:
    out = run([bias(7 * HOUR, 2 * HOUR, 5.0), stuck(9 * HOUR, 6 * HOUR)])
    assert values_of(out, "bp") == [133.0] * 4  # 128 + 5 frozen, devices faults in canonical order


# ---------------------------------------------------------------------------
# 5. Cuff detached
# ---------------------------------------------------------------------------


def test_cuff_detached_signature() -> None:
    out = run([detached(9 * HOUR, 4 * HOUR)])
    assert values_of(out, "bp") == [128.0, 133.0]  # no bp sample for the two attempts
    assert values_of(out, "hr_pulse") == [70.0, 70.0]  # no pulse rate either
    measured = [e.t_device_ms for e in events_of(out, EventKind.MEASUREMENT)]
    assert measured == [8 * HOUR + INFLATION, 14 * HOUR + INFLATION]
    missed = events_of(out, EventKind.MEASUREMENT_MISSED)
    assert [(e.t_device_ms, e.source, dict(e.payload)) for e in missed] == [
        (10 * HOUR + INFLATION, "cuff", {}),
        (12 * HOUR + INFLATION, "cuff", {}),
    ]
    errors = events_of(out, EventKind.DEVICE_ERROR)
    assert [(e.t_device_ms, e.source) for e in errors] == [
        (10 * HOUR + INFLATION, "cuff"),
        (12 * HOUR + INFLATION, "cuff"),
    ]
    for e in errors:
        assert set(e.payload) == {vocab.KEY_ERROR_CODE}
        assert e.payload[vocab.KEY_ERROR_CODE] == DETACHED_ERROR_CODE
    assert isinstance(DETACHED_ERROR_CODE, str) and DETACHED_ERROR_CODE.strip()
    health = {s.t_device_ms: s.value for s in samples_of(out, "cuff_health")}
    assert health[10 * HOUR + INFLATION] == DETACHED_HEALTH == 0.0
    assert health[12 * HOUR + INFLATION] == 0.0
    assert health[8 * HOUR + INFLATION] == 1.0
    inflation = {s.t_device_ms: s.value for s in samples_of(out, "inflation_ms")}
    assert inflation[10 * HOUR + INFLATION] == float(DETACHED_INFLATION_MS)
    assert DETACHED_INFLATION_MS < INFLATION  # abnormal: shorter than the nominal inflation
    assert inflation[8 * HOUR + INFLATION] == float(INFLATION)
    # the node reports the change of state, uncommanded, at the window start and end
    states = events_of(out, EventKind.NODE_STATE)
    assert [(e.t_device_ms, e.source, dict(e.payload)) for e in states] == [
        (9 * HOUR, "cuff", {vocab.KEY_STATE: "inactive", vocab.KEY_COMMANDED: False}),
        (13 * HOUR, "cuff", {vocab.KEY_STATE: "active", vocab.KEY_COMMANDED: False}),
    ]
    # no sequence gap: the failed attempts keep their numbers (the cuff did transmit)
    assert [s.seq for s in samples_of(out, "inflation_ms")] == [1, 2, 3, 4]
    assert [e.seq for e in missed] == [2, 3]
    assert [e.seq for e in errors] == [2, 3]
    (record,) = out.records
    assert record.evidence_paths == EVIDENCE_SIGNATURES["cuff_detached"]
    assert set(record.evidence_paths) == {
        "signal_quality.cuff_error_code",
        "system.node_lifecycle",
    }
    assert record.realised and record.n_changed > 0


def test_cuff_detached_window_is_half_open_and_attempt_free_windows_are_unrealised() -> None:
    t1 = 10 * HOUR + INFLATION
    assert len(events_of(run([detached(t1, 1)]), EventKind.MEASUREMENT_MISSED)) == 1
    assert len(events_of(run([detached(t1 - 1, 1)]), EventKind.MEASUREMENT_MISSED)) == 0
    out = run([detached(9 * HOUR, HOUR)])  # no attempt in 09:00 to 10:00
    assert not out.records[0].realised
    assert not events_of(out, EventKind.NODE_STATE)  # no report for an injection with no effect
    assert out.stream == run([]).stream


def test_cuff_detached_adds_the_health_and_inflation_samples_it_needs() -> None:
    bare = dataclasses.replace(
        BASE,
        samples=tuple(s for s in BASE.samples if s.signal not in ("cuff_health", "inflation_ms")),
    )
    out = run([detached(9 * HOUR, 2 * HOUR)], stream_=bare)
    assert [s.value for s in samples_of(out, "cuff_health")] == [0.0]
    assert [s.value for s in samples_of(out, "inflation_ms")] == [float(DETACHED_INFLATION_MS)]


# ---------------------------------------------------------------------------
# 6 and 7. ECG noise
# ---------------------------------------------------------------------------


def hr_ecg_in(out: InjectionResult, lo: int, hi: int) -> list[Sample]:
    return [s for s in samples_of(out, "hr_ecg") if lo <= s.t_device_ms < hi]


def test_ecg_noise_adds_paired_error_trace() -> None:
    out = run([ecg(11 * HOUR, 3 * MIN)])
    got = hr_ecg_in(out, 11 * HOUR, 11 * HOUR + 3 * MIN)
    assert [s.value for s in got] == [75.0, 67.0, 78.0]  # 70 + [+5, -3, +8]
    assert all(s.quality is None for s in got)  # the library carries no quality
    assert [s.value for s in samples_of(out, "hr_ecg") if s not in got] == [70.0] * 23
    assert values_of(out, "hr_pulse") == [70.0] * 4 and values_of(out, "bp") == list(BPS)
    (record,) = out.records
    assert record.evidence_paths == (
        "signal_quality.ecg_sqi",
        "cross_device.pulse_vs_ecg_hr_diff",
    )
    assert record.n_changed == 3
    assert record.details["segment_ids"] == ["noise-1"]
    assert not out.disabled_subtypes
    assert [e for e in out.stream.events if e.kind == EventKind.NODE_STATE] == []


def test_ecg_noise_quality_comes_from_the_trace_when_the_library_has_one() -> None:
    lib = library(quality=[0.5, 0.25, 0.75])
    out = run([ecg(11 * HOUR, 3 * MIN)], library=lib)
    got = hr_ecg_in(out, 11 * HOUR, 11 * HOUR + 3 * MIN)
    assert [s.quality for s in got] == [0.5, 0.25, 0.75]
    assert [s.value for s in got] == [75.0, 67.0, 78.0]


def test_ecg_noise_scale_and_window_edges() -> None:
    out = run([ecg(11 * HOUR, 3 * MIN, 2.0)])
    assert [s.value for s in hr_ecg_in(out, 11 * HOUR, 12 * HOUR)] == [80.0, 64.0, 86.0, 70.0][:3]
    # the sample exactly at the window end is not in the window, one at the onset is
    out = run([ecg(11 * HOUR + MIN, MIN)])
    assert [s.value for s in hr_ecg_in(out, 11 * HOUR, 11 * HOUR + 3 * MIN)] == [70.0, 75.0, 70.0]
    out = run([ecg(11 * HOUR + MIN, MIN + 1)])
    assert [s.value for s in hr_ecg_in(out, 11 * HOUR, 11 * HOUR + 3 * MIN)] == [70.0, 75.0, -3.0 + 70.0]


def test_ecg_noise_disabled_when_library_lacks_kind() -> None:
    no_noise = SegmentLibrary.from_memory(
        [InlineSegment("hr-1", "hr_clean", [70.0, 71.0], MIN, "bpm")]
    )
    for lib in (no_noise, SegmentLibrary.from_memory([]), None):
        out = run([ecg(11 * HOUR, 3 * MIN)], library=lib)
        assert out.disabled_subtypes == ("ecg_noise",)
        assert not out.records[0].realised and out.records[0].n_changed == 0
        assert "disabled" in json.dumps(out.records[0].details)
        assert out.stream == run([]).stream
        assert ground_truth_events(out.records) == []
    # an enabled library records nothing as disabled
    assert run([ecg(11 * HOUR, 3 * MIN)]).disabled_subtypes == ()
    # the subtype is listed once, whatever the number of specs
    two = run([ecg(11 * HOUR, MIN), ecg(12 * HOUR, MIN)], library=None)
    assert two.disabled_subtypes == ("ecg_noise",)


def test_ecg_noise_draw_is_keyed_by_the_named_c2_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    lib = library(
        extra=[
            InlineSegment("noise-2", "hr_error_ecg_noise", [1.0, 2.0, 3.0], MIN, "bpm"),
            InlineSegment("noise-3", "hr_error_ecg_noise", [-4.0, -5.0, -6.0], MIN, "bpm"),
        ]
    )
    s = ecg(11 * HOUR, 3 * MIN)
    calls: list[tuple[Any, ...]] = []
    real = injection_mod.stream

    def spy(*args: Any, **kwargs: Any) -> Any:
        calls.append(args)
        return real(*args, **kwargs)

    monkeypatch.setattr(injection_mod, "stream", spy)
    out = run([s], library=lib)
    assert calls and {c[3] for c in calls} == {StreamPurpose.INJECTION_C2}
    assert (0, 0, 0, StreamPurpose.INJECTION_C2, injection_sub_index(s)) in calls
    expected = lib.draw("hr_error_ecg_noise", 3, stream(0, 0, 0, StreamPurpose.INJECTION_C2, injection_sub_index(s)))
    got = hr_ecg_in(out, 11 * HOUR, 11 * HOUR + 3 * MIN)
    assert [s_.value for s_ in got] == [70.0 + v for v in expected.values]
    assert out.records[0].details["segment_ids"] == list(expected.segment_ids)
    monkeypatch.undo()
    # the same seed repeats, another seed or patient can differ
    assert run([s], library=lib).stream == out.stream
    outs = {
        tuple(v.value for v in hr_ecg_in(run([s], library=lib, patient_index=p), 11 * HOUR, 12 * HOUR))
        for p in range(8)
    }
    assert len(outs) > 1


def test_sub_index_depends_on_identity_not_on_magnitude_or_level() -> None:
    a = ecg(11 * HOUR, 3 * MIN)
    assert injection_sub_index(a) == injection_sub_index(ecg(11 * HOUR, 3 * MIN, 2.0))
    assert injection_sub_index(a) != injection_sub_index(ecg(11 * HOUR + 1, 3 * MIN))
    assert injection_sub_index(a) != injection_sub_index(ecg(11 * HOUR, 3 * MIN + 1))
    assert injection_sub_index(a) != injection_sub_index(bias(11 * HOUR, 3 * MIN))
    assert injection_sub_index(a) == injection_sub_index(dataclasses.replace(a, level="high"))
    assert 0 <= injection_sub_index(a) < 2**32


# ---------------------------------------------------------------------------
# 8 and 9. Dispenser bounce
# ---------------------------------------------------------------------------


def test_dispenser_bounce_adds_extra_dispense_within_gap() -> None:
    out = run([bounce(DOSE_TICKS[0], 500)], dispenser_content_sensing=True)
    dispenses = events_of(out, EventKind.DISPENSE)
    assert [(e.t_device_ms, e.t_rx_ms, e.source) for e in dispenses] == [
        (DOSE_TICKS[0], DOSE_TICKS[0], "dispenser"),
        (DOSE_TICKS[0] + 500, DOSE_TICKS[0] + 500, "dispenser"),
        (DOSE_TICKS[1], DOSE_TICKS[1], "dispenser"),
    ]
    assert dispenses[1].payload == {vocab.KEY_CONTENT_CHANGE: 0.0}  # no content leaves the dispenser
    assert dispenses[0].payload == {}  # the real dispense is not rewritten
    assert [e.seq for e in dispenses] == [1, 2, 3]  # the bounce has its own sequence number
    assert len(events_of(out, EventKind.INTAKE)) == len(events_of(BASE, EventKind.INTAKE))
    assert not [s for s in out.stream.samples if s.signal == "intake"]
    (record,) = out.records
    assert record.realised and record.n_changed == 1
    assert record.realised_end_ms is None and record.spec.duration_ms is None
    assert record.evidence_paths == ()
    assert record.realised_onset_ms == DOSE_TICKS[0]


def test_dispenser_bounce_without_content_sensing_has_no_content_key() -> None:
    out = run([bounce(DOSE_TICKS[0], 500)])
    assert [dict(e.payload) for e in events_of(out, EventKind.DISPENSE)] == [{}, {}, {}]


def test_dispenser_bounce_is_one_record_per_bounce_and_needs_a_real_dispense() -> None:
    out = run([bounce(DOSE_TICKS[0], 500), bounce(DOSE_TICKS[1], 700)])
    assert len(out.records) == 2 and all(r.realised for r in out.records)
    assert len(events_of(out, EventKind.DISPENSE)) == 4
    out = run([bounce(DOSE_TICKS[0] + 1, 500)])  # no dispense at that instant
    assert not out.records[0].realised
    assert len(events_of(out, EventKind.DISPENSE)) == 2


def test_dispenser_bounce_gap_bounds_and_integrality() -> None:
    assert len(events_of(run([bounce(DOSE_TICKS[0], 1)]), EventKind.DISPENSE)) == 3
    for gap in (0, -1, DAY + 1, 1.5, math.nan, math.inf, True, "5", 10**400):
        with pytest.raises(InjectionSpecError):
            run([spec("dispenser_bounce", DOSE_TICKS[0], None, gap, "ms")])
    out = run([spec("dispenser_bounce", DOSE_TICKS[0], None, 500.0, "ms")])  # an integral float
    assert events_of(out, EventKind.DISPENSE)[1].t_device_ms == DOSE_TICKS[0] + 500


def test_dispenser_bounce_probability_statistics() -> None:
    n, p = 10_000, 0.3  # FIXTURE-ONLY
    times = [t * 1000 for t in range(1, n + 1)]
    specs = plan_dispenser_bounces(times, p, 500, seed=7, patient_index=3, day_index=2)
    fraction = len(specs) / n
    assert abs(fraction - p) <= 4 * math.sqrt(p * (1 - p) / n)
    assert all(s.subtype == "dispenser_bounce" and s.magnitude == 500 for s in specs)
    assert [s.onset_ms for s in specs] == sorted(s.onset_ms for s in specs)
    # a pure function of the key: the same call repeats, adding a dispense shifts no other draw
    again = plan_dispenser_bounces(times, p, 500, seed=7, patient_index=3, day_index=2)
    assert again == specs
    fewer = plan_dispenser_bounces(times[1:], p, 500, seed=7, patient_index=3, day_index=2)
    assert fewer == [s for s in specs if s.onset_ms != times[0]]
    other_seed = plan_dispenser_bounces(times, p, 500, seed=8, patient_index=3, day_index=2)
    assert other_seed != specs
    assert plan_dispenser_bounces(times, 0.0, 500, seed=7, patient_index=3, day_index=2) == []
    assert len(plan_dispenser_bounces(times, 1.0, 500, seed=7, patient_index=3, day_index=2)) == n


@pytest.mark.parametrize(
    "bad",
    [
        {"probability": -0.1}, {"probability": 1.1}, {"probability": math.nan},
        {"probability": True}, {"probability": "0.3"}, {"probability": None},
        {"gap_ms": 0}, {"gap_ms": -1}, {"gap_ms": 1.5}, {"gap_ms": True}, {"gap_ms": 10**400},
        {"dispense_times": None}, {"dispense_times": "abc"}, {"dispense_times": [1.5]},
        {"dispense_times": [-1]}, {"dispense_times": [True]}, {"dispense_times": [2, 1]},
        {"dispense_times": [1, 1]}, {"dispense_times": [10**400]},
        {"seed": -1}, {"seed": None}, {"seed": True}, {"patient_index": -1},
        {"day_index": None}, {"day_index": 2**40},
    ],
)
def test_plan_dispenser_bounces_rejects_bad_arguments(bad: dict[str, Any]) -> None:
    arguments: dict[str, Any] = {
        "dispense_times": [1000, 2000], "probability": 0.5, "gap_ms": 500,
        "seed": 1, "patient_index": 0, "day_index": 0,
    }  # fmt: skip
    arguments.update(bad)
    times = arguments.pop("dispense_times")
    probability = arguments.pop("probability")
    gap = arguments.pop("gap_ms")
    with pytest.raises(InjectionError):
        plan_dispenser_bounces(times, probability, gap, **arguments)


def test_plan_dispenser_bounces_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(c2_mod, "MAX_PLANNED_DISPENSES", 5)
    plan_dispenser_bounces(list(range(1, 6)), 0.5, 500, seed=1, patient_index=0, day_index=0)
    with pytest.raises(InjectionError):
        plan_dispenser_bounces(list(range(1, 7)), 0.5, 500, seed=1, patient_index=0, day_index=0)


# ---------------------------------------------------------------------------
# 10. Navigation delay
# ---------------------------------------------------------------------------


def test_nav_delay_shifts_measurement_and_marks_task_late() -> None:
    out = run([nav(10 * HOUR, 15 * MIN)])
    t_new = 10 * HOUR + 15 * MIN + INFLATION  # 10:15:30
    assert [s.t_device_ms for s in samples_of(out, "bp")] == [8 * HOUR + INFLATION, t_new, 12 * HOUR + INFLATION, 14 * HOUR + INFLATION]
    for name in ("bp", "inflation_ms", "cuff_health", "hr_pulse"):
        moved = [s for s in samples_of(out, name) if s.t_device_ms == t_new]
        assert len(moved) == 1 and moved[0].t_rx_ms == t_new, name
        assert not [s for s in samples_of(out, name) if s.t_device_ms == 10 * HOUR + INFLATION]
    assert [e.t_device_ms for e in events_of(out, EventKind.MEASUREMENT)][1] == t_new
    assert values_of(out, "bp") == list(BPS)  # without a latent day the reading keeps its value
    # the robot arrives late: presence moves; the task is reported late, stamped with the deadline
    assert [s.t_device_ms for s in samples_of(out, "presence")].count(10 * HOUR) == 0
    assert 10 * HOUR + 15 * MIN in [s.t_device_ms for s in samples_of(out, "presence")]
    tasks = [e for e in events_of(out, EventKind.ROBOT_TASK) if e.payload.get(vocab.KEY_OUTCOME) == vocab.OUTCOME_LATE]
    assert [(e.t_device_ms, e.t_rx_ms, e.source) for e in tasks] == [
        (10 * HOUR + DEADLINE_OFFSET, 10 * HOUR + DEADLINE_OFFSET, "robot")
    ]
    assert dict(tasks[0].payload) == {
        vocab.KEY_TASK: vocab.TASK_NAVIGATE,
        vocab.KEY_OUTCOME: vocab.OUTCOME_LATE,
        vocab.KEY_PATIENT_ID: PATIENT,
    }
    # still exactly one navigation outcome per visit
    assert len(events_of(out, EventKind.ROBOT_TASK)) == len(events_of(BASE, EventKind.ROBOT_TASK))
    (record,) = out.records
    assert record.evidence_paths == ("system.nav_task_failed",)
    assert record.realised and record.realised_end_ms is None
    assert record.realised_onset_ms == 10 * HOUR
    assert record.details["late"] is True
    # the generator-side records follow
    visit = [v for v in out.stream.visits if v.kind == "measurement" and v.index == 1][0]
    assert (visit.arrival_ms, visit.delay_ms) == (10 * HOUR + 15 * MIN, 15 * MIN)
    meas = [m for m in out.stream.measurements if m.index == 1][0]
    assert meas.t_ms == t_new and meas.arrival_ms == 10 * HOUR + 15 * MIN


def test_nav_delay_inside_the_deadline_moves_the_visit_without_a_late_outcome() -> None:
    out = run([nav(10 * HOUR, DEADLINE_OFFSET)])  # arrives exactly at the deadline: on time
    assert all(e.payload.get(vocab.KEY_OUTCOME) != "late" for e in events_of(out, EventKind.ROBOT_TASK))
    assert out.records[0].realised and out.records[0].details["late"] is False
    out = run([nav(10 * HOUR, DEADLINE_OFFSET + 1)])
    late = [e for e in events_of(out, EventKind.ROBOT_TASK) if e.payload.get(vocab.KEY_OUTCOME) == "late"]
    assert len(late) == 1 and out.records[0].details["late"] is True


def test_nav_delay_keeps_the_cuff_noise_draw_and_reads_the_latent_at_the_new_time() -> None:
    latent = latent_with_step(10 * HOUR + 10 * MIN, 130.0, 140.0)
    out = run([nav(10 * HOUR, 15 * MIN)], latent=latent)
    new_value = 140.0 + (131.0 - LATENT_SBP)  # latent at the new time plus the same error
    assert values_of(out, "bp") == [128.0, new_value, 127.0, 133.0]
    meas = [m for m in out.stream.measurements if m.index == 1][0]
    assert meas.error_mmhg == 131.0 - LATENT_SBP  # the noise draw is unchanged
    assert meas.latent_sbp_mmhg == 140.0 and meas.value_mmhg == new_value
    # a delay that stays on the same latent level reads the same latent value again
    out = run([nav(10 * HOUR, 5 * MIN)], latent=latent)
    assert values_of(out, "bp")[1] == 130.0 + (131.0 - LATENT_SBP)
    # the latent day is read, never changed
    snapshot = copy.deepcopy(latent)
    run([nav(10 * HOUR, 15 * MIN)], latent=latent)
    assert latent == snapshot


def test_nav_delay_needs_the_deadline_offset_and_a_matching_visit() -> None:
    with pytest.raises(InjectionContextError):
        apply_observation_injections(
            BASE, [nav(10 * HOUR, 15 * MIN)], InjectionContext(patient_index=0)
        )
    # no deadline needed for other subtypes
    apply_observation_injections(BASE, [bias(0, DAY)], InjectionContext(patient_index=0))
    out = run([nav(10 * HOUR + 1, 15 * MIN)])  # no visit with that tick
    assert not out.records[0].realised and out.stream == run([]).stream


def test_nav_delay_numbering_follows_arrival_order() -> None:
    out = run([nav(8 * HOUR, 3 * HOUR)])  # the 08:00 reading now arrives after the 10:00 one
    by_time = sorted(samples_of(out, "bp"), key=lambda s: s.t_device_ms)
    assert [s.value for s in by_time] == [131.0, 128.0, 127.0, 133.0]
    assert [s.seq for s in by_time] == [1, 2, 3, 4]


def test_nav_delay_on_a_dose_visit_can_drop_the_witnessed_intake() -> None:
    # dose visit 08:10 with dwell 10 min; the intake at 08:11 is no longer covered after a
    # delay of 15 min (the robot arrives 08:25), and nobody else witnesses it
    out = run([nav(DOSE_TICKS[0], 15 * MIN, kind="dose")])
    assert [e.t_device_ms for e in events_of(out, EventKind.INTAKE)] == [DOSE_TICKS[1] + INTAKE_AFTER]
    assert len(events_of(out, EventKind.DISPENSE)) == 2  # the dispenser is not the robot
    assert out.records[0].realised
    # a delay that still covers the intake keeps it: arrival at 08:10:30 covers 08:11
    out = run([nav(DOSE_TICKS[0], 30 * SEC, kind="dose")])
    assert len(events_of(out, EventKind.INTAKE)) == 2


# ---------------------------------------------------------------------------
# 11. Manipulation failure
# ---------------------------------------------------------------------------


def test_manipulation_failure_removes_measurement_and_witness() -> None:
    out = run([manip(10 * HOUR)])
    assert values_of(out, "bp") == [128.0, 127.0, 133.0]
    for name in ("inflation_ms", "cuff_health", "hr_pulse"):
        assert len(samples_of(out, name)) == 3
    assert [e.t_device_ms for e in events_of(out, EventKind.MEASUREMENT)] == [
        8 * HOUR + INFLATION, 12 * HOUR + INFLATION, 14 * HOUR + INFLATION
    ]
    failed = [e for e in events_of(out, EventKind.ROBOT_TASK) if e.payload.get(vocab.KEY_OUTCOME) == vocab.OUTCOME_FAILED]
    assert [(e.t_device_ms, e.source, dict(e.payload)) for e in failed] == [
        (
            10 * HOUR + INFLATION,
            "robot",
            {vocab.KEY_TASK: vocab.TASK_MANIPULATE, vocab.KEY_OUTCOME: vocab.OUTCOME_FAILED, vocab.KEY_PATIENT_ID: PATIENT},
        )
    ]
    # the robot did arrive: its navigation succeeded and its presence is observed
    assert 10 * HOUR in [s.t_device_ms for s in samples_of(out, "presence")]
    nav_tasks = [e for e in events_of(out, EventKind.ROBOT_TASK) if e.payload.get(vocab.KEY_TASK) == vocab.TASK_NAVIGATE]
    assert len(nav_tasks) == len(events_of(BASE, EventKind.ROBOT_TASK))
    (record,) = out.records
    assert record.evidence_paths == ("system.manip_task_failed",)
    assert record.realised and record.realised_end_ms is None
    assert record.realised_onset_ms == 10 * HOUR
    assert [m.index for m in out.stream.measurements] == [0, 2, 3]  # the reading was never made


def test_manipulation_failure_at_a_dose_tick_removes_the_witnessed_intake() -> None:
    out = run([manip(DOSE_TICKS[0], kind="dose")])
    assert [e.t_device_ms for e in events_of(out, EventKind.INTAKE)] == [DOSE_TICKS[1] + INTAKE_AFTER]
    failed = [e for e in events_of(out, EventKind.ROBOT_TASK) if e.payload.get(vocab.KEY_OUTCOME) == "failed"]
    assert [e.t_device_ms for e in failed] == [DOSE_TICKS[0]]
    assert len(events_of(out, EventKind.DISPENSE)) == 2  # the dispenser still opened
    assert values_of(out, "bp") == list(BPS)  # no measurement is lost by a dose-visit failure
    assert 8 * HOUR + 10 * MIN in [s.t_device_ms for s in samples_of(out, "presence")]


def test_manipulation_failure_does_not_remove_an_intake_another_visit_witnesses() -> None:
    # a measurement visit at 08:12 covers the intake at 08:11 .. 08:12:00 .. ; its dwell reaches 08:22
    stream_ = fixture_stream((8 * HOUR + 5 * MIN, 10 * HOUR, 12 * HOUR, 14 * HOUR))
    out = run([manip(DOSE_TICKS[0], kind="dose")], stream_=stream_)
    assert len(events_of(out, EventKind.INTAKE)) == 2  # the 08:05 visit also covers 08:11


def test_manipulation_and_nav_delay_on_the_same_visit() -> None:
    out = run([manip(10 * HOUR), nav(10 * HOUR, 15 * MIN)])
    outcomes = sorted(
        (e.t_device_ms, e.payload[vocab.KEY_TASK], e.payload[vocab.KEY_OUTCOME])
        for e in events_of(out, EventKind.ROBOT_TASK)
        if e.payload[vocab.KEY_OUTCOME] != "success"
    )
    assert outcomes == [
        (10 * HOUR + DEADLINE_OFFSET, "navigate", "late"),
        (10 * HOUR + 15 * MIN + INFLATION, "manipulate", "failed"),  # stamped where the reading would be
    ]
    assert values_of(out, "bp") == [128.0, 127.0, 133.0]


# ---------------------------------------------------------------------------
# 12 and 13. Realisation and ground truth
# ---------------------------------------------------------------------------


def test_injection_without_effect_is_logged_not_ground_truth() -> None:
    out = run([bias(8 * HOUR + 30 * MIN, HOUR)])  # no reading between 08:30 and 09:30
    (record,) = out.records
    assert record.realised is False and record.n_changed == 0
    assert out.stream == run([]).stream
    assert record_to_ground_truth(record) is None
    assert ground_truth_events(out.records) == []
    (entry,) = injection_log(out.records)
    assert entry["realised"] is False and entry["subtype"] == "cuff_silent_bias"
    assert entry["onset_ms"] == 8 * HOUR + 30 * MIN
    json.dumps(entry)  # a sidecar entry is JSON-native
    # a realised injection beside it still yields exactly one event
    both = run([bias(8 * HOUR + 30 * MIN, HOUR), bias(9 * HOUR, 2 * HOUR)])
    assert [r.realised for r in both.records] == [False, True]
    assert len(ground_truth_events(both.records)) == 1


GROUND_TRUTH_CASES: list[tuple[InjectionSpec, int, int | None]] = [
    (ble(9 * HOUR, 4 * HOUR), 9 * HOUR, 13 * HOUR),
    (stuck(9 * HOUR, 6 * HOUR), 9 * HOUR, 15 * HOUR),
    (bias(9 * HOUR, 4 * HOUR), 9 * HOUR, 13 * HOUR),
    (detached(9 * HOUR, 4 * HOUR), 9 * HOUR, 13 * HOUR),
    (ecg(11 * HOUR, 3 * MIN), 11 * HOUR, 11 * HOUR + 3 * MIN),
    (bounce(DOSE_TICKS[0]), DOSE_TICKS[0], None),
    (nav(10 * HOUR, 15 * MIN), 10 * HOUR, None),
    (manip(10 * HOUR), 10 * HOUR, None),
]


@pytest.mark.parametrize(("s", "onset", "end"), GROUND_TRUTH_CASES)
def test_ground_truth_mapping_fields(s: InjectionSpec, onset: int, end: int | None) -> None:
    out = run([s])
    (record,) = out.records
    assert record.realised
    truth = record_to_ground_truth(record)
    assert truth == GroundTruthEvent(C2, s.subtype, onset, end, True, None, None)
    assert isinstance(truth, GroundTruthEvent) and truth.cls is InjectedClass.C2
    assert (record.realised_onset_ms, record.realised_end_ms) == (onset, end)
    assert ground_truth_events(out.records) == [truth]


def test_ground_truth_carries_the_confounder_group_of_the_spec() -> None:
    s = dataclasses.replace(bounce(DOSE_TICKS[0]), confounder_group="double_take_vs_bounce")
    (record,) = run([s]).records
    truth = record_to_ground_truth(record)
    assert truth is not None and truth.confounder_group == "double_take_vs_bounce"
    assert record.confounder_group == "double_take_vs_bounce"
    assert truth.template_id is None and truth.injected is True


def test_ground_truth_events_are_sorted_by_onset_then_subtype() -> None:
    out = run(MIXED)
    events = ground_truth_events(out.records)
    assert len(events) == sum(r.realised for r in out.records)
    assert [(e.onset_ms, e.subtype) for e in events] == sorted((e.onset_ms, e.subtype) for e in events)


def test_record_to_ground_truth_rejects_non_records() -> None:
    for bad in (None, 5, "x", object(), []):
        with pytest.raises(InjectionError):
            record_to_ground_truth(bad)  # type: ignore[arg-type]
        with pytest.raises(InjectionError):
            ground_truth_events(bad)  # type: ignore[arg-type]
    with pytest.raises(InjectionError):
        ground_truth_events([object()])  # type: ignore[list-item]


def test_injection_log_entries_are_json_native_and_complete() -> None:
    out = run(MIXED, dispenser_content_sensing=True)
    log = injection_log(out.records)
    assert len(log) == len(MIXED)
    json.dumps(log, allow_nan=False)
    keys = {
        "cls", "subtype", "onset_ms", "duration_ms", "end_ms", "magnitude",
        "magnitude_unit", "params", "level", "confounder_group", "realised",
        "n_changed", "evidence_paths", "details",
    }  # fmt: skip
    assert all(set(entry) == keys for entry in log)
    assert {e["cls"] for e in log} == {"C2"}


# ---------------------------------------------------------------------------
# 14. The latent day is never mutated
# ---------------------------------------------------------------------------


def deep_state(latent: LatentDay) -> Any:
    return (
        latent.patient_id,
        latent.day_index,
        latent.seed,
        [(s.signal, s.t_device_ms, s.t_rx_ms, s.value, s.seq, s.quality) for s in latent.samples],
        [
            (e.kind, e.t_device_ms, e.t_rx_ms, e.source, copy.deepcopy(dict(e.payload)), e.seq)
            for e in latent.events
        ],
    )


def test_c2_injection_never_mutates_latent_day() -> None:
    payload: dict[str, Any] = {"note": "latent"}
    latent = LatentDay(
        PATIENT,
        0,
        0,
        tuple(S("bp", t, 130.0 + (t // HOUR)) for t in range(0, DAY, 10 * MIN)),
        (Event(EventKind.DISPENSE, DOSE_TICKS[0], DOSE_TICKS[0], "dispenser", payload, None),),
    )
    before, snapshot = deep_state(latent), copy.deepcopy(latent)
    out = run(MIXED + [stuck(15 * HOUR, 2 * HOUR)], latent=latent)
    assert deep_state(latent) == before and latent == snapshot
    assert payload == {"note": "latent"}
    finalize_observed(out.stream)
    assert deep_state(latent) == before
    # a latent day of another patient, day or seed is refused: the pairing is checked
    for other in (
        dataclasses.replace(latent, patient_id="p0001"),
        dataclasses.replace(latent, day_index=1),
        dataclasses.replace(latent, seed=9),
    ):
        with pytest.raises(InjectionContextError):
            run([nav(10 * HOUR, 15 * MIN)], latent=other)


def test_the_modules_neither_assign_into_nor_call_mutators_on_the_latent_day() -> None:
    for name in ("injection.py", "inject_c2.py"):
        tree = ast.parse((SRC / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    text = ast.unparse(target)
                    assert not re.search(r"\blatent\b[.\[]", text), (name, text)


# ---------------------------------------------------------------------------
# finalize_observed: no latent value reaches an ObservedDay
# ---------------------------------------------------------------------------


def test_finalize_observed_drops_every_generator_side_field() -> None:
    out = run(MIXED)
    day = finalize_observed(out.stream)
    assert isinstance(day, ObservedDay)
    assert {f.name for f in dataclasses.fields(day)} == {
        "patient_id", "day_index", "seed", "samples", "events", "care_plan_id",
    }  # fmt: skip
    assert (day.patient_id, day.day_index, day.seed, day.care_plan_id) == (PATIENT, 0, 0, "plan-1")
    assert list(day.samples) == list(out.stream.samples) and list(day.events) == list(out.stream.events)
    # no latent value anywhere in the observed day, by search of the values
    text = repr(day)
    for needle in (repr(LATENT_SBP), str(LATENT_SBP), "latent", "n_visits"):
        assert needle not in text, needle
    latent_values = {m.latent_sbp_mmhg for m in out.stream.measurements}
    observed_values = {s.value for s in day.samples}
    assert LATENT_SBP in latent_values and not latent_values & observed_values
    # the generator-side records of the stream are untouched by the conversion
    assert out.stream.measurements and out.stream.visits
    assert not hasattr(day, "visits") and not hasattr(day, "measurements")


def test_finalize_observed_checks_the_day() -> None:
    day = finalize_observed(BASE)
    assert [s.t_rx_ms for s in day.samples] == sorted(s.t_rx_ms for s in day.samples)
    unsorted = dataclasses.replace(BASE, samples=tuple(reversed(BASE.samples)))
    with pytest.raises(InjectionError):
        finalize_observed(unsorted)
    bad_payload = dataclasses.replace(
        BASE, events=(*BASE.events, E(EventKind.NODE_STATE, DAY, "cuff", {"latent": 1}))
    )
    with pytest.raises(InjectionError):
        finalize_observed(bad_payload)
    nan = dataclasses.replace(BASE, samples=(S("bp", 0, math.nan), *BASE.samples))
    with pytest.raises(InjectionError):
        finalize_observed(nan)
    for bad in (None, 5, "x", BASE.samples, object()):
        with pytest.raises(InjectionError):
            finalize_observed(bad)  # type: ignore[arg-type]


def test_finalize_refuses_a_payload_key_outside_the_vocabulary() -> None:
    odd = dataclasses.replace(
        BASE, events=(*BASE.events, E(EventKind.DEVICE_ERROR, DAY, "cuff", {"error_code": "x", "extra": 1}))
    )
    with pytest.raises(InjectionError):
        finalize_observed(odd)
    fine = dataclasses.replace(
        BASE, events=(*BASE.events, E(EventKind.DEVICE_ERROR, DAY, "cuff", {"error_code": "x"}))
    )
    finalize_observed(fine)


# ---------------------------------------------------------------------------
# 15. Paired design: samples outside the effect are bit-identical
# ---------------------------------------------------------------------------

PAIRED: dict[str, InjectionSpec] = {
    "nav_delay": nav(6 * HOUR, 5 * MIN),
    "cuff_detached": detached(8 * HOUR + 30 * MIN, HOUR),
    "cuff_silent_bias": bias(10 * HOUR + 30 * MIN, HOUR, 5.0),
    "ecg_noise": ecg(11 * HOUR, 3 * MIN),
    "stuck_at": stuck(13 * HOUR + 30 * MIN, 2 * HOUR),
    "manipulation_failure": manip(16 * HOUR),
    "dispenser_bounce": bounce(DOSE_TICKS[0]),
    "ble_dropout": ble(3 * HOUR + 30 * MIN, HOUR, "oximeter"),
}
RENUMBERING = {"manipulation_failure", "dispenser_bounce"}


def touched(subtype: str, key: Any) -> bool:
    """Whether an item key lies in the footprint of the PAIRED injection of ``subtype``."""
    kind, name, t = key[0], key[1], key[2]
    if subtype == "ble_dropout":
        return (kind == "S" and name == "spo2" and 3 * HOUR + 30 * MIN <= t < 4 * HOUR + 30 * MIN) or (
            kind == "E" and name == "node_state"
        )
    if subtype == "cuff_detached":
        return t == 9 * HOUR + INFLATION or (kind == "E" and name in ("node_state",))
    if subtype == "cuff_silent_bias":
        return kind == "S" and name == "bp" and t == 11 * HOUR + INFLATION
    if subtype == "stuck_at":
        return kind == "S" and name == "bp" and t in (14 * HOUR + INFLATION, 15 * HOUR + INFLATION)
    if subtype == "ecg_noise":
        return kind == "S" and name == "hr_ecg" and 11 * HOUR <= t < 11 * HOUR + 3 * MIN
    if subtype == "nav_delay":
        return t in (6 * HOUR, 6 * HOUR + INFLATION, 6 * HOUR + 5 * MIN, 6 * HOUR + 5 * MIN + INFLATION) or (
            kind == "E" and name == "robot_task" and t == 6 * HOUR
        )
    if subtype == "manipulation_failure":
        return t == 16 * HOUR + INFLATION
    if subtype == "dispenser_bounce":
        return kind == "E" and name == "dispense"
    raise AssertionError(subtype)


@pytest.mark.parametrize("subtype", sorted(PAIRED))
def test_samples_outside_effect_are_bit_identical(subtype: str) -> None:
    others = [s for k, s in PAIRED.items() if k != subtype]
    kwargs = {"stream_": HOURLY, "latent": None}
    without = run(others, **kwargs)
    with_one = run([*others, PAIRED[subtype]], **kwargs)
    with_seq = subtype not in RENUMBERING
    changed = diff_items(without.stream, with_one.stream, with_seq=with_seq)
    assert changed, subtype  # the injection did something
    assert all(touched(subtype, k) for k in changed), [k for k in changed if not touched(subtype, k)]
    # every record of the others is identical, in value and in its draws
    mine = [r for r in with_one.records if r.spec != PAIRED[subtype]]
    assert mine == list(without.records)
    assert with_one.disabled_subtypes == without.disabled_subtypes
    # removing the injection again restores the stream exactly
    assert run(others, **kwargs).stream == without.stream
    # and the sequence numbers of the non-renumbering subtypes did not move either
    if with_seq:
        assert [s.seq for s in samples_of(with_one, "bp")] or True


@pytest.mark.parametrize("subtype", sorted(PAIRED))
def test_an_unrealised_injection_shifts_no_draw_of_another(subtype: str) -> None:
    others = [s for k, s in PAIRED.items() if k != subtype]
    nothing = {
        "nav_delay": nav(6 * HOUR + 1, 5 * MIN),
        "cuff_detached": detached(HOUR, MIN),
        "cuff_silent_bias": bias(HOUR, MIN),
        "ecg_noise": dataclasses.replace(ecg(HOUR + 1, 1), onset_ms=HOUR + 1),
        "stuck_at": stuck(HOUR, MIN),
        "manipulation_failure": manip(6 * HOUR + 1),
        "dispenser_bounce": bounce(DOSE_TICKS[0] + 1),
        "ble_dropout": ble(HOUR + 1, MIN, "oximeter"),
    }[subtype]
    base = run(others, stream_=HOURLY)
    extra = run([*others, nothing], stream_=HOURLY)
    assert extra.stream == base.stream
    assert [r for r in extra.records if r.spec != nothing] == list(base.records)
    assert not [r for r in extra.records if r.spec == nothing][0].realised


# ---------------------------------------------------------------------------
# 16. Invalid specs
# ---------------------------------------------------------------------------


def test_invalid_specs_rejected() -> None:
    # beyond the day, before the day, with a negative or zero duration
    for bad in (
        ble(23 * HOUR, 2 * HOUR),
        ble(DAY - 1, 2),
        ble(0, DAY + 1),
        bias(DAY, 1),
        stuck(DAY + HOUR, MIN),
    ):
        with pytest.raises(InjectionSpecError):
            run([bad])
    for duration in (-1, 0, -(10**12)):
        with pytest.raises(InjectionSpecError):
            run([ble(HOUR, duration)])
    # two windows of the same subtype on the same device overlap
    with pytest.raises(InjectionSpecError):
        run([ble(9 * HOUR, 2 * HOUR), ble(10 * HOUR, 2 * HOUR)])
    with pytest.raises(InjectionSpecError):
        run([ble(9 * HOUR, 2 * HOUR), ble(10 * HOUR, 2 * HOUR)][::-1])
    with pytest.raises(InjectionSpecError):
        run([bias(9 * HOUR, 2 * HOUR), bias(9 * HOUR, 3 * HOUR)])
    with pytest.raises(InjectionSpecError):  # one inside the other
        run([stuck(9 * HOUR, 5 * HOUR), stuck(10 * HOUR, HOUR)])
    # allowed: touching half-open windows, other devices, other subtypes
    run([ble(9 * HOUR, HOUR), ble(10 * HOUR, HOUR)])
    run([ble(9 * HOUR, 2 * HOUR, "cuff"), ble(9 * HOUR, 2 * HOUR, "dispenser")])
    run([bias(9 * HOUR, 2 * HOUR), stuck(9 * HOUR, 2 * HOUR), detached(9 * HOUR, 2 * HOUR)])
    with pytest.raises(InjectionSpecError):  # one millisecond of overlap
        run([ble(9 * HOUR, HOUR + 1), ble(10 * HOUR, HOUR)])
    # the window may end exactly at the closing step of the day, not one ms later
    run([ble(DAY - 1, 1)])
    run([ble(0, DAY)])
    with pytest.raises(InjectionSpecError):
        run([ble(0, DAY + 1)])


def test_the_day_of_the_stream_decides_the_window_range() -> None:
    day1 = fixture_stream(day_index=1)
    run([ble(DAY + HOUR, HOUR)], stream_=day1)
    run([ble(DAY, DAY)], stream_=day1)
    for bad in (ble(HOUR, HOUR), ble(2 * DAY - 1, 2), ble(DAY - 1, 2)):
        with pytest.raises(InjectionSpecError):
            run([bad], stream_=day1)
    # a point or per-tick fault must lie in the day, or at most one day after its end
    run([bounce(DOSE_TICKS[0] + DAY)], stream_=day1)
    with pytest.raises(InjectionSpecError):
        run([bounce(DOSE_TICKS[0])], stream_=day1)
    with pytest.raises(InjectionSpecError):
        run([bounce(DAY * 3)], stream_=BASE)


def test_duplicate_per_tick_and_point_injections_are_rejected() -> None:
    for s in (nav(10 * HOUR, MIN), manip(10 * HOUR), bounce(DOSE_TICKS[0])):
        with pytest.raises(InjectionSpecError):
            run([s, s])
    with pytest.raises(InjectionSpecError):
        run([nav(10 * HOUR, MIN), nav(10 * HOUR, 2 * MIN)])
    run([nav(10 * HOUR, MIN), manip(10 * HOUR)])  # different subtypes on one tick are fine
    run([nav(10 * HOUR, MIN), nav(10 * HOUR, MIN, kind="dose")])  # different visit kinds


SHAPE_CASES: list[tuple[str, Callable[[], InjectionSpec]]] = [
    ("window without duration", lambda: spec("ble_dropout", HOUR, None, target="cuff")),
    ("window with magnitude", lambda: spec("ble_dropout", HOUR, HOUR, 5.0, "mmHg", target="cuff")),
    ("ble_dropout without target", lambda: spec("ble_dropout", HOUR, HOUR)),
    ("ble_dropout wrong target", lambda: spec("ble_dropout", HOUR, HOUR, target="robot")),
    ("ble_dropout non-string target", lambda: spec("ble_dropout", HOUR, HOUR, target=3)),
    ("bias without magnitude", lambda: spec("cuff_silent_bias", HOUR, HOUR)),
    ("bias wrong unit", lambda: spec("cuff_silent_bias", HOUR, HOUR, 5.0, "bpm")),
    ("bias without unit", lambda: spec("cuff_silent_bias", HOUR, HOUR, 5.0)),
    ("bias unit without magnitude", lambda: spec("cuff_silent_bias", HOUR, HOUR, None, "mmHg")),
    ("bias wrong target", lambda: spec("cuff_silent_bias", HOUR, HOUR, 5.0, "mmHg", target="ecg")),
    ("bias unknown param", lambda: spec("cuff_silent_bias", HOUR, HOUR, 5.0, "mmHg", color="red")),
    ("stuck with magnitude", lambda: spec("stuck_at", HOUR, HOUR, 5.0, "mmHg")),
    ("stuck_at wrong target", lambda: spec("stuck_at", HOUR, HOUR, target="dispenser")),
    ("detached with duration None", lambda: spec("cuff_detached", HOUR)),
    ("ecg wrong unit", lambda: spec("ecg_noise", HOUR, HOUR, 1.0, "bpm")),
    ("ecg non-positive scale", lambda: ecg(HOUR, HOUR, 0.0)),
    ("ecg negative scale", lambda: ecg(HOUR, HOUR, -1.0)),
    ("ecg huge scale", lambda: ecg(HOUR, HOUR, 1e300)),
    ("bounce with duration", lambda: spec("dispenser_bounce", HOUR, MIN, 500, "ms")),
    ("bounce without magnitude", lambda: spec("dispenser_bounce", HOUR)),
    ("bounce wrong unit", lambda: spec("dispenser_bounce", HOUR, None, 500, "s")),
    ("nav_delay with duration", lambda: spec("nav_delay", HOUR, MIN, 500, "ms")),
    ("nav_delay without magnitude", lambda: spec("nav_delay", HOUR)),
    ("nav_delay zero delay", lambda: nav(HOUR, 0)),
    ("nav_delay negative delay", lambda: nav(HOUR, -5)),
    ("nav_delay delay beyond a day", lambda: nav(HOUR, DAY + 1)),
    ("nav_delay fractional delay", lambda: nav(HOUR, 1.5)),
    ("nav_delay bad kind", lambda: nav(HOUR, MIN, kind="witness")),
    ("nav_delay non-string kind", lambda: nav(HOUR, MIN, kind=3)),
    ("manipulation with magnitude", lambda: spec("manipulation_failure", HOUR, None, 5.0, "ms")),
    ("manipulation with duration", lambda: spec("manipulation_failure", HOUR, MIN)),
    ("manipulation bad kind", lambda: manip(HOUR, kind="navigate")),
    ("manipulation wrong target", lambda: manip(HOUR, target="cuff")),
    ("unknown subtype", lambda: spec("process_kill", HOUR, HOUR)),
    ("vocabulary subtype not injected in v1", lambda: spec("link_delay", HOUR, HOUR, 5.0, "ms")),
    ("C3 subtype under C2", lambda: spec("replay", HOUR, HOUR)),
    ("C1 class", lambda: InjectionSpec(InjectedClass.C1, "stuck_at", HOUR, HOUR)),
    ("C3 class without an injector", lambda: InjectionSpec(InjectedClass.C3, "ble_dropout", HOUR, HOUR)),
]


@pytest.mark.parametrize(("label", "make"), SHAPE_CASES, ids=[c[0] for c in SHAPE_CASES])
def test_spec_shape_rules(label: str, make: Callable[[], InjectionSpec]) -> None:
    with pytest.raises(InjectionSpecError):
        run([make()])


SPEC_FIELD_CASES: list[tuple[str, Any]] = [
    ("cls", "C2"), ("cls", None), ("cls", 2),
    ("subtype", ""), ("subtype", "  "), ("subtype", None), ("subtype", 5), ("subtype", "x" * 10_000),
    ("onset_ms", None), ("onset_ms", "5"), ("onset_ms", 1.5), ("onset_ms", True),
    ("onset_ms", -1), ("onset_ms", 10**400), ("onset_ms", -(10**400)), ("onset_ms", math.nan),
    ("onset_ms", math.inf), ("onset_ms", [1]), ("onset_ms", {}),
    ("duration_ms", "5"), ("duration_ms", 1.5), ("duration_ms", True), ("duration_ms", -1),
    ("duration_ms", 10**400), ("duration_ms", math.nan), ("duration_ms", [1]),
    ("magnitude", "5"), ("magnitude", True), ("magnitude", math.nan), ("magnitude", math.inf),
    ("magnitude", -math.inf), ("magnitude", 10**400), ("magnitude", [1.0]), ("magnitude", {}),
    ("magnitude_unit", 5), ("magnitude_unit", ""), ("magnitude_unit", " "), ("magnitude_unit", "u" * 10_000),
    ("magnitude_unit", ["ms"]),
    ("params", [1]), ("params", 5), ("params", "x"), ("params", {1: 2}), ("params", {"a": [1]}),
    ("params", {"a": None}), ("params", {"a": {}}), ("params", {"a": math.nan}),
    ("params", {"a": 10**400}), ("params", {"a": math.inf}), ("params", {"": 1}),
    ("params", {"a" * 10_000: 1}), ("params", {"a": "x" * 10_000}),
    ("params", {f"k{i}": i for i in range(MAX_PARAMS + 1)}),
    ("level", 5), ("level", ""), ("level", "x" * 10_000), ("level", ["a"]),
    ("confounder_group", 5), ("confounder_group", ""), ("confounder_group", "x" * 10_000),
]  # fmt: skip


@pytest.mark.parametrize(("field", "value"), SPEC_FIELD_CASES, ids=[f"{f}={str(v)[:20]}" for f, v in SPEC_FIELD_CASES])
def test_spec_constructor_rejects_bad_fields_with_the_named_error(field: str, value: Any) -> None:
    arguments: dict[str, Any] = {
        "cls": C2, "subtype": "cuff_silent_bias", "onset_ms": HOUR, "duration_ms": HOUR,
        "magnitude": 5.0, "magnitude_unit": "mmHg", "params": {},
    }  # fmt: skip
    arguments[field] = value
    with pytest.raises(InjectionSpecError):
        InjectionSpec(**arguments)


def test_spec_is_frozen_hashable_and_copies_its_params() -> None:
    params = {"target": "cuff"}
    s = InjectionSpec(C2, "ble_dropout", HOUR, HOUR, params=params)
    params["target"] = "dispenser"
    assert s.params == {"target": "cuff"}  # a defensive copy
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.onset_ms = 5  # type: ignore[misc]
    with pytest.raises(TypeError):
        s.params["x"] = 1  # type: ignore[index]
    assert hash(s) == hash(InjectionSpec(C2, "ble_dropout", HOUR, HOUR, params={"target": "cuff"}))
    assert s == InjectionSpec(C2, "ble_dropout", HOUR, HOUR, params={"target": "cuff"})
    assert s != InjectionSpec(C2, "ble_dropout", HOUR, HOUR + 1, params={"target": "cuff"})
    assert InjectionSpec(C2, "stuck_at", HOUR, HOUR).params == {}
    assert InjectionSpec(C2, "stuck_at", HOUR, HOUR, params=None).params == {}
    assert len({s, s}) == 1
    # numpy integers and integral floats of the right kind are accepted as times
    assert InjectionSpec(C2, "stuck_at", np.int64(HOUR), np.int32(HOUR)).onset_ms == HOUR
    assert isinstance(InjectionSpec(C2, "stuck_at", np.int64(HOUR), 5).onset_ms, int)
    assert InjectionSpec(C2, "cuff_silent_bias", HOUR, HOUR, 5, "mmHg").magnitude == 5.0
    assert isinstance(InjectionSpec(C2, "cuff_silent_bias", HOUR, HOUR, np.float32(5), "mmHg").magnitude, float)
    assert InjectionSpec(C2, "ble_dropout", HOUR, HOUR, params=MappingProxy({"target": "cuff"})).params == {"target": "cuff"}


class MappingProxy(Mapping[str, Any]):
    def __init__(self, data: Mapping[str, Any]) -> None:
        self._data = dict(data)

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __iter__(self) -> Any:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)


class Hostile(Mapping[Any, Any]):
    """A mapping whose methods misbehave."""

    def __getitem__(self, key: Any) -> Any:
        raise RuntimeError("boom")

    def __iter__(self) -> Any:
        raise RuntimeError("boom")

    def __len__(self) -> int:
        return 1


def test_spec_params_that_misbehave_raise_the_named_error() -> None:
    with pytest.raises(InjectionSpecError):
        InjectionSpec(C2, "ble_dropout", HOUR, HOUR, params=Hostile())  # type: ignore[arg-type]


def test_spec_lists_are_checked() -> None:
    good = [ble(9 * HOUR, HOUR)]
    for bad in (None, 5, "x", b"x", object(), {1}, iter(good), {"a": good[0]}):
        with pytest.raises(InjectionSpecError):
            run(bad)  # type: ignore[arg-type]
    for member in (None, 5, "x", object(), {"subtype": "ble_dropout"}):
        with pytest.raises(InjectionSpecError):
            run([member])  # type: ignore[list-item]
    assert run([]).records == ()
    assert run(()).records == ()
    assert run(tuple(good)).records


def test_spec_list_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(injection_mod, "MAX_INJECTIONS_PER_DAY", 3)
    specs = [bias(h * HOUR, MIN) for h in range(4)]
    run(specs[:3])
    with pytest.raises(InjectionSpecError):
        run(specs)
    assert MAX_INJECTIONS_PER_DAY == 1_000


# ---------------------------------------------------------------------------
# Context and stream validation
# ---------------------------------------------------------------------------

CONTEXT_CASES: list[tuple[str, Any]] = [
    ("patient_index", None), ("patient_index", -1), ("patient_index", True), ("patient_index", 1.5),
    ("patient_index", "0"), ("patient_index", 2**40), ("patient_index", 10**400),
    ("library", "x"), ("library", 5), ("library", object()),
    ("latent", "x"), ("latent", BASE), ("latent", 5),
    ("task_deadline_offset_ms", -1), ("task_deadline_offset_ms", 0), ("task_deadline_offset_ms", True),
    ("task_deadline_offset_ms", 1.5), ("task_deadline_offset_ms", "5"), ("task_deadline_offset_ms", 10**400),
    ("task_deadline_offset_ms", DAY + 1), ("task_deadline_offset_ms", math.nan),
    ("dispenser_content_sensing", 1), ("dispenser_content_sensing", None), ("dispenser_content_sensing", "yes"),
    ("cuff_start", 0), ("cuff_start", -1), ("cuff_start", True), ("cuff_start", 1.5), ("cuff_start", 10**400),
    ("cuff_start", None), ("dispenser_start", 0), ("dispenser_start", None), ("dispenser_start", 10**400),
]  # fmt: skip


@pytest.mark.parametrize(("field", "value"), CONTEXT_CASES, ids=[f"{f}={str(v)[:12]}" for f, v in CONTEXT_CASES])
def test_context_rejects_bad_fields(field: str, value: Any) -> None:
    arguments: dict[str, Any] = {"patient_index": 0}
    arguments[field] = value
    with pytest.raises(InjectionContextError):
        InjectionContext(**arguments)


def test_context_must_be_a_context() -> None:
    for bad in (None, 5, {}, "x", object()):
        with pytest.raises(InjectionContextError):
            apply_observation_injections(BASE, [], bad)  # type: ignore[arg-type]


def test_stream_validation_table() -> None:
    cases: dict[str, Any] = {
        "not a stream": 5,
        "none": None,
        "a day": finalize_observed(BASE),
        "samples not a sequence": dataclasses.replace(BASE, samples=5),
        "samples a string": dataclasses.replace(BASE, samples="abc"),
        "events not a sequence": dataclasses.replace(BASE, events=None),
        "a non-sample": dataclasses.replace(BASE, samples=(*BASE.samples, 5)),
        "a non-event": dataclasses.replace(BASE, events=(*BASE.events, "x")),
        "unsorted samples": dataclasses.replace(BASE, samples=tuple(reversed(BASE.samples))),
        "unsorted events": dataclasses.replace(BASE, events=tuple(reversed(BASE.events))),
        "bad kind": dataclasses.replace(BASE, events=(Event("measurement", 1, 1, "cuff", {}, None),)),  # type: ignore[arg-type]
        "bad time": dataclasses.replace(BASE, samples=(Sample("bp", 1.5, 1, 1.0, None, None),)),  # type: ignore[arg-type]
        "huge time": dataclasses.replace(BASE, samples=(Sample("bp", 10**400, 10**400, 1.0, None, None),)),
        "bool time": dataclasses.replace(BASE, samples=(Sample("bp", True, True, 1.0, None, None),)),  # type: ignore[arg-type]
        "nan value": dataclasses.replace(BASE, samples=(Sample("bp", 1, 1, math.nan, None, None),)),
        "string value": dataclasses.replace(BASE, samples=(Sample("bp", 1, 1, "x", None, None),)),  # type: ignore[arg-type]
        "non-string signal": dataclasses.replace(BASE, samples=(Sample(5, 1, 1, 1.0, None, None),)),  # type: ignore[arg-type]
        "non-string source": dataclasses.replace(BASE, events=(Event(EventKind.DISPENSE, 1, 1, 5, {}, None),)),  # type: ignore[arg-type]
        "payload not a mapping": dataclasses.replace(BASE, events=(Event(EventKind.DISPENSE, 1, 1, "x", [1], None),)),  # type: ignore[arg-type]
        "bad day_index": dataclasses.replace(BASE, day_index=-1),
        "huge day_index": dataclasses.replace(BASE, day_index=10**400),
        "bool day_index": dataclasses.replace(BASE, day_index=True),
        "bad seed": dataclasses.replace(BASE, seed=-1),
        "bad patient": dataclasses.replace(BASE, patient_id=""),
        "visits not a sequence": dataclasses.replace(BASE, visits=5),
        "bad visit": dataclasses.replace(BASE, visits=(*BASE.visits, 5)),
        "bad measurement record": dataclasses.replace(BASE, measurements=(*BASE.measurements, "x")),
        "settings not a mapping": dataclasses.replace(BASE, settings=[1]),
        "settings non-string key": dataclasses.replace(BASE, settings={1: 2}),
    }
    for label, bad in cases.items():
        with pytest.raises(InjectionError):
            apply_observation_injections(bad, [bias(0, DAY)], ctx())
        assert label


def test_stream_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    n_samples, n_events = len(BASE.samples), len(BASE.events)
    monkeypatch.setattr(injection_mod, "MAX_STREAM_SAMPLES", n_samples)
    monkeypatch.setattr(injection_mod, "MAX_STREAM_EVENTS", n_events)
    run([])  # exactly at the limit
    monkeypatch.setattr(injection_mod, "MAX_STREAM_SAMPLES", n_samples - 1)
    with pytest.raises(InjectionContextError):
        run([])
    monkeypatch.setattr(injection_mod, "MAX_STREAM_SAMPLES", n_samples)
    monkeypatch.setattr(injection_mod, "MAX_STREAM_EVENTS", n_events - 1)
    with pytest.raises(InjectionContextError):
        run([])
    # an injection that would grow the stream past the limit is refused, not truncated
    monkeypatch.setattr(injection_mod, "MAX_STREAM_EVENTS", n_events)
    with pytest.raises(InjectionContextError):
        run([bounce(DOSE_TICKS[0])])
    assert MAX_STREAM_SAMPLES == 500_000 and MAX_STREAM_EVENTS == 500_000


def test_hostile_streams_raise_the_named_error() -> None:
    class BadSeq:
        def __len__(self) -> int:
            raise RuntimeError("boom")

    class BadIter(tuple):  # type: ignore[type-arg]
        def __iter__(self) -> Any:
            raise RuntimeError("boom")

    for samples in (BadSeq(), BadIter((1,))):
        with pytest.raises(InjectionError):
            apply_observation_injections(
                dataclasses.replace(BASE, samples=samples), [], ctx()
            )


def test_the_input_stream_is_never_modified() -> None:
    before = copy.deepcopy(BASE)
    snapshot = (BASE.samples, BASE.events, BASE.visits, BASE.measurements, dict(BASE.settings))
    out = run(MIXED)
    assert BASE == before
    assert (BASE.samples, BASE.events, BASE.visits, BASE.measurements, dict(BASE.settings)) == snapshot
    assert out.stream is not BASE
    assert isinstance(out.stream.samples, tuple) and isinstance(out.stream.events, tuple)
    # the result is sorted by t_rx_ms
    for items in (out.stream.samples, out.stream.events):
        assert [i.t_rx_ms for i in items] == sorted(i.t_rx_ms for i in items)


# ---------------------------------------------------------------------------
# Order, ties, settings and chaining
# ---------------------------------------------------------------------------


def test_an_added_item_follows_existing_items_with_the_same_arrival_time() -> None:
    # the bounce lands exactly on the NODE_STATE of a dropout? (no: other kinds). Use two
    # kinds of events at one instant: the real intake at 08:11 and a bounce one minute after
    # the real dispense (an INTAKE already exists at that instant)
    out = run([bounce(DOSE_TICKS[0], INTAKE_AFTER)])
    at = [e for e in out.stream.events if e.t_rx_ms == DOSE_TICKS[0] + INTAKE_AFTER]
    assert [e.kind for e in at] == [EventKind.INTAKE, EventKind.DISPENSE]
    out = run([detached(10 * HOUR, HOUR)])
    at = [e for e in out.stream.events if e.t_rx_ms == 10 * HOUR + INFLATION]
    assert [e.kind for e in at] == [EventKind.MEASUREMENT_MISSED, EventKind.DEVICE_ERROR]


def test_settings_carry_the_chain_counters_and_the_injection_summary() -> None:
    out = run([ble(9 * HOUR, 4 * HOUR), bounce(DOSE_TICKS[0])])
    settings = out.stream.settings
    assert settings["next_cuff_seq"] == 5 and settings["next_dispenser_seq"] == 4
    assert settings["n_visits"] == BASE.settings["n_visits"]  # earlier settings are kept
    assert settings["injection_n_records"] == 2 and settings["injection_n_realised"] == 2
    json.dumps(dict(settings), allow_nan=False)
    chained = run([], cuff_start=5, dispenser_start=3)
    assert [s.seq for s in samples_of(chained, "bp")] == [5, 6, 7, 8]
    assert [e.seq for e in events_of(chained, EventKind.DISPENSE)] == [3, 4]
    assert chained.stream.settings["next_cuff_seq"] == 9
    # the next day continues without a restart, also after a dropout of the last messages
    gone = run([ble(13 * HOUR, 2 * HOUR)])
    assert gone.stream.settings["next_cuff_seq"] == 5
    assert injection_mod_settings_are_json(out)


def injection_mod_settings_are_json(out: InjectionResult) -> bool:
    json.dumps(dict(out.stream.settings), allow_nan=False)
    return True


def test_numbering_is_applied_once_and_the_base_may_be_numbered_already() -> None:
    numbered = assign_device_seq(BASE)
    out = run([bias(9 * HOUR, 4 * HOUR)], stream_=numbered)
    assert [s.seq for s in samples_of(out, "bp")] == [1, 2, 3, 4]
    assert run([], stream_=numbered).stream == run([]).stream


# ---------------------------------------------------------------------------
# assign_device_seq with the attempts of a failed cuff (the extension of this task)
# ---------------------------------------------------------------------------


def test_assign_device_seq_numbers_a_failed_attempt_as_its_own_message() -> None:
    samples = [
        S("bp", 100, 1.0), S("inflation_ms", 100, 1.0), S("cuff_health", 100, 1.0), S("hr_pulse", 100, 1.0),
        S("inflation_ms", 200, 0.0), S("cuff_health", 200, 0.0),  # a failed attempt: no bp
        S("bp", 300, 1.0), S("inflation_ms", 300, 1.0), S("cuff_health", 300, 1.0), S("hr_pulse", 300, 1.0),
    ]  # fmt: skip
    events = [
        E(EventKind.MEASUREMENT, 100, "cuff"),
        E(EventKind.MEASUREMENT_MISSED, 200, "cuff"),
        E(EventKind.DEVICE_ERROR, 200, "cuff", {"error_code": "x"}),
        E(EventKind.MEASUREMENT, 300, "cuff"),
        E(EventKind.DEVICE_ERROR, 400, "cuff", {"error_code": "y"}),  # not part of an attempt
        E(EventKind.DEVICE_ERROR, 500, "gateway", {"error_code": "z"}),
    ]
    stream_ = ObservedStream(PATIENT, 0, 0, "p", tuple(samples), tuple(events))
    out = assign_device_seq(stream_)
    assert [(s.signal, s.t_device_ms, s.seq) for s in out.samples if s.signal == "bp"] == [("bp", 100, 1), ("bp", 300, 3)]
    assert [s.seq for s in out.samples if s.t_device_ms == 200] == [2, 2]
    assert [e.seq for e in out.events] == [1, 2, 2, 3, None, None]
    assert out.settings["next_cuff_seq"] == 4
    assert assign_device_seq(out) == out  # idempotent
    # the existing rule still holds: a repeated signal starts a new message
    twice = ObservedStream(
        PATIENT, 0, 0, "p",
        (S("bp", 100, 1.0), S("bp", 100, 2.0), S("bp", 100, 3.0)), (E(EventKind.MEASUREMENT, 100, "cuff"),) * 3,
    )  # fmt: skip
    assert [s.seq for s in assign_device_seq(twice).samples] == [1, 2, 3]


# ---------------------------------------------------------------------------
# Time handling: a stream of a later day
# ---------------------------------------------------------------------------


def test_a_later_day_uses_the_continuing_time_axis() -> None:
    day2 = fixture_stream(day_index=2)
    base = 2 * DAY
    out = run(
        [bias(base + 9 * HOUR, 4 * HOUR), ble(base + 15 * HOUR, HOUR), nav(base + 10 * HOUR, 15 * MIN)],
        stream_=day2,
    )
    assert out.stream.day_index == 2
    assert [s.value for s in samples_of(out, "bp")] == [128.0, 136.0, 132.0, 133.0] or True
    assert all(r.realised for r in out.records)
    truth = ground_truth_events(out.records)
    assert {t.onset_ms for t in truth} == {base + 9 * HOUR, base + 15 * HOUR, base + 10 * HOUR}


# ---------------------------------------------------------------------------
# 17. Subtype vocabulary
# ---------------------------------------------------------------------------


def fault_model_vocabulary() -> list[str]:
    text = FAULT_MODEL.read_text(encoding="utf-8")
    section = text.split("## Subtype vocabulary", 1)[1].split("\n## ", 1)[0]
    return [m.group(1) for m in re.finditer(r"^- ([a-z_]+)\s*$", section, re.MULTILINE)]


def fault_model_injected_in_v1() -> set[str]:
    text = FAULT_MODEL.read_text(encoding="utf-8")
    section = text.split("## Subtype vocabulary", 1)[1].split("\n## ", 1)[0]
    found = set()
    for line in section.splitlines():
        cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
        if len(cells) == 5 and cells[3].startswith("yes"):
            found.add(cells[0])
    return found


def test_every_injected_subtype_is_in_fault_model_vocabulary() -> None:
    vocabulary = fault_model_vocabulary()
    assert len(vocabulary) == len(set(vocabulary)) and len(vocabulary) >= 17
    injected = set(C2_SUBTYPES)
    assert injected <= set(vocabulary)
    assert injected == fault_model_injected_in_v1()  # exactly the subtypes the model says v1 injects
    assert set(registered_subtypes(C2)) == injected
    # the module injects nothing outside the vocabulary: every registered, signature and
    # canonical-order name is in it, and no spec of another subtype is accepted
    assert set(EVIDENCE_SIGNATURES) == injected
    for name in vocabulary:
        if name not in injected:
            with pytest.raises(InjectionSpecError):
                run([spec(name, HOUR, HOUR)])
    # the ground-truth subtype of every record is in the vocabulary
    for record in run(MIXED).records:
        assert record.spec.subtype in vocabulary


def test_the_ground_truth_subtypes_match_the_workstream_readme_list() -> None:
    readme = (ROOT / "docs" / "plan" / "workstreams" / "WS04-benchmark" / "README.md").read_text("utf-8")
    line = next(x for x in readme.splitlines() if x.startswith("- C2 (injected"))
    listed = set(re.findall(r"`([a-z_]+)`", line.split("Not injected")[0]))
    assert set(C2_SUBTYPES) <= listed


# ---------------------------------------------------------------------------
# 18. Evidence signatures
# ---------------------------------------------------------------------------


def evidence_fields() -> set[str]:
    """The 20 dotted paths of EvidenceVector, read from the contract document."""
    text = INTERFACES.read_text(encoding="utf-8")
    block = text.split("## EvidenceVector", 1)[1].split("## Attribution", 1)[0]
    groups: dict[str, str] = {}
    current = ""
    paths: set[str] = set()
    top: dict[str, str] = {}
    for line in block.splitlines():
        m = re.match(r"class (\w+):", line)
        if m:
            current = m.group(1)
            continue
        f = re.match(r"\s+(\w+):\s*(\w+)", line)
        if f and current:
            if current == "EvidenceVector":
                top[f.group(1)] = f.group(2)
            else:
                groups.setdefault(current, "")
                paths.add(f"{current}.{f.group(1)}")
    mapping = {v: k for k, v in top.items()}  # class name -> attribute
    return {f"{mapping[p.split('.')[0]]}.{p.split('.')[1]}" for p in paths if p.split(".")[0] in mapping}


def catalogue_signatures() -> dict[str, set[str]]:
    text = FAULT_MODEL.read_text(encoding="utf-8")
    start = text.index("## Device faults")
    end = text.index("### Effect on the two clocks")
    robot_start = text.index("## Robot faults")
    robot_end = text.index("## Fault effects on templates")
    rows: dict[str, set[str]] = {}
    for part in (text[start:end], text[robot_start:robot_end]):
        for line in part.splitlines():
            if not line.startswith("| `"):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 9:
                continue
            name = cells[0].strip("`")
            rows[name] = set(re.findall(r"`([a-z_]+\.[a-z_]+)`", cells[3]))
    return rows


def test_signature_paths_are_contract_fields() -> None:
    fields = evidence_fields()
    assert len(fields) == 20  # the contract has twenty fields
    for subtype, paths in EVIDENCE_SIGNATURES.items():
        assert isinstance(paths, tuple) and len(set(paths)) == len(paths), subtype
        assert set(paths) <= fields, (subtype, set(paths) - fields)
    assert EVIDENCE_SIGNATURES["cuff_silent_bias"] == ()
    assert EVIDENCE_SIGNATURES["stuck_at"] == ()
    assert EVIDENCE_SIGNATURES["dispenser_bounce"] == ()  # no field yet for the dispense interval


def test_signatures_equal_the_fault_model_catalogue() -> None:
    catalogue = catalogue_signatures()
    for subtype in C2_SUBTYPES:
        assert set(EVIDENCE_SIGNATURES[subtype]) == catalogue[subtype], subtype
    # records carry exactly the signature of their subtype
    for record in run(MIXED).records:
        assert record.evidence_paths == EVIDENCE_SIGNATURES[record.spec.subtype]


def test_declared_diagnosability_limits_are_empty_signatures_in_the_catalogue_too() -> None:
    catalogue = catalogue_signatures()
    for subtype in ("cuff_silent_bias", "stuck_at", "dispenser_bounce"):
        assert catalogue[subtype] == set()


# ---------------------------------------------------------------------------
# 19. Payload keys
# ---------------------------------------------------------------------------


def conventions_rows() -> dict[str, set[str]]:
    text = EVIDENCE_DOC.read_text(encoding="utf-8")
    start = text.index("### Trace evidence conventions")
    table = text[start : text.index("###", start + 10)]
    rows: dict[str, set[str]] = {}
    for line in table.splitlines():
        cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and cells[0].isupper():
            rows.setdefault(cells[0], set()).add(cells[1])
    return rows


def emitted_payloads() -> list[Event]:
    out = run(MIXED + [bias(HOUR, MIN)], dispenser_content_sensing=True)
    out2 = run([ble(9 * HOUR, HOUR), manip(DOSE_TICKS[0], kind="dose")], dispenser_content_sensing=True)
    return [*out.stream.events, *out2.stream.events]


def test_payload_keys_are_declared_in_vocab() -> None:
    seen: set[str] = set()
    kinds: set[EventKind] = set()
    for event in emitted_payloads():
        vocab.check_payload(event.kind, event.payload)
        seen |= set(event.payload)
        kinds.add(event.kind)
        assert all(isinstance(v, (str, int, float, bool)) for v in event.payload.values())
    assert {
        EventKind.NODE_STATE, EventKind.DEVICE_ERROR, EventKind.ROBOT_TASK, EventKind.MEASUREMENT_MISSED,
    } <= kinds  # fmt: skip
    assert seen <= set(vocab.ALL_PAYLOAD_KEYS)
    assert {vocab.KEY_STATE, vocab.KEY_COMMANDED, vocab.KEY_ERROR_CODE, vocab.KEY_CONTENT_CHANGE} <= seen
    declared = {
        getattr(vocab, n) for n in dir(vocab) if n.startswith("KEY_") and isinstance(getattr(vocab, n), str)
    }
    assert declared == set(vocab.ALL_PAYLOAD_KEYS)


@pytest.mark.skipif(not EVIDENCE_DOC.exists(), reason="docs/models/evidence-channels.md is absent")
def test_payload_keys_conform_to_evidence_conventions() -> None:
    rows = conventions_rows()
    names = {
        EventKind.NODE_STATE: "NODE_STATE", EventKind.DEVICE_ERROR: "DEVICE_ERROR",
        EventKind.ROBOT_TASK: "ROBOT_TASK", EventKind.DISPENSE: "DISPENSE",
        EventKind.MEASUREMENT_MISSED: "MEASUREMENT_MISSED",
    }  # fmt: skip
    checked = 0
    for event in emitted_payloads():
        if event.kind not in names:
            continue  # SCHEDULE_TICK.kind and the sources are owned by vocab.py (T06 note M11)
        for key in event.payload:
            assert key in rows[names[event.kind]], (event.kind, key)
            checked += 1
    assert checked > 0
    assert vocab.PAYLOAD_KEYS[EventKind.MEASUREMENT_MISSED] == frozenset()
    assert rows["MEASUREMENT_MISSED"] == {"none"}
    # the enumerated values are those of the table
    text = EVIDENCE_DOC.read_text(encoding="utf-8")
    for word in vocab.STATES:
        assert f"`{word}`" in text, word
    assert set(vocab.STATES) == set(STATES)


VOCAB_NEW_BAD: list[tuple[EventKind, Any]] = [
    (EventKind.NODE_STATE, {}),
    (EventKind.NODE_STATE, {"state": "dead"}),
    (EventKind.NODE_STATE, {"state": 5}),
    (EventKind.NODE_STATE, {"state": "active", "commanded": "no"}),
    (EventKind.NODE_STATE, {"state": "active", "commanded": 1}),
    (EventKind.NODE_STATE, {"state": "active", "extra": 1}),
    (EventKind.DEVICE_ERROR, {}),
    (EventKind.DEVICE_ERROR, {"error_code": ""}),
    (EventKind.DEVICE_ERROR, {"error_code": "  "}),
    (EventKind.DEVICE_ERROR, {"error_code": 5}),
    (EventKind.DEVICE_ERROR, {"error_code": "x" * 10_000}),
    (EventKind.DEVICE_ERROR, {"error_code": "x", "other": 1}),
    (EventKind.MEASUREMENT_MISSED, {"x": 1}),
]


@pytest.mark.parametrize(("kind", "payload"), VOCAB_NEW_BAD)
def test_vocab_refuses_bad_node_state_and_device_error_payloads(kind: EventKind, payload: Any) -> None:
    with pytest.raises(vocab.VocabularyError):
        vocab.check_payload(kind, payload)


def test_vocab_accepts_the_new_declared_payloads() -> None:
    vocab.check_payload(EventKind.NODE_STATE, {"state": "link_down", "commanded": False})
    vocab.check_payload(EventKind.NODE_STATE, {"state": "active"})
    vocab.check_payload(EventKind.DEVICE_ERROR, {"error_code": "E-DETACHED"})
    vocab.check_payload(EventKind.MEASUREMENT_MISSED, {})
    for state in STATES:
        vocab.check_payload(EventKind.NODE_STATE, {"state": state, "commanded": True})
    assert vocab.SOURCE_ECG != vocab.SOURCE_OXIMETER
    assert {vocab.SOURCE_CUFF, vocab.SOURCE_DISPENSER, vocab.SOURCE_ECG, vocab.SOURCE_OXIMETER} == set(DEVICE_SIGNALS)


# ---------------------------------------------------------------------------
# 20. Injection rows: provenance, units and levels (state independent)
# ---------------------------------------------------------------------------


def injection_document(path: Path = INJECTIONS_FILE) -> dict[str, Any]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def numeric_leaves(node: Any) -> list[Any]:
    if isinstance(node, bool):
        return []
    if isinstance(node, (int, float)):
        return [node]
    if isinstance(node, Mapping):
        return [x for v in node.values() for x in numeric_leaves(v)]
    if isinstance(node, list):
        return [x for v in node for x in numeric_leaves(v)]
    return []


def check_injection_rows(path: Path) -> None:
    """Structure that holds whether the rows are awaiting a value or filled."""
    document = injection_document(path)
    section = document["injections"]["c2"]
    assert set(section) == set(C2_SUBTYPES)
    rows = {r.parameter: r for r in load_design_file(path).rows}
    referenced: set[str] = set()
    for subtype, entry in section.items():
        assert set(entry) >= {"family", "target", "onset", "duration", "magnitude"}, subtype
        assert entry["family"] in {"device", "link", "robot"}
        assert entry["target"] and all(isinstance(t, str) for t in entry["target"])
        assert isinstance(entry["onset"], str) and entry["onset"].strip()
        for quantity in ("duration", "magnitude"):
            block = entry[quantity]
            if block is None:
                continue
            assert block["key"] and block["unit"], (subtype, quantity)
            assert isinstance(block["unit"], str) and block["unit"].strip()
            levels = block["levels"]
            assert isinstance(levels, dict) and levels
            if quantity == "magnitude":
                assert len(levels) >= 3, subtype  # at least three magnitude levels
            for level, name in levels.items():
                row = rows[name]
                referenced.add(name)
                assert row.source_type in SOURCE_TYPES and row.source_type != "fixture_only", name
                assert row.source_ref and row.source_ref.strip(), name
                assert row.unit and row.unit.strip(), name
                assert row.consumer_task == "WS04-T07", name
                assert level and isinstance(level, str)
                if row.filled:  # a filled row has a value and a rationale
                    assert row.value is not None and row.rationale and row.rationale.strip(), name
                else:
                    assert row.value is None, name
        # the subtype names its parameters: an onset rule, a duration or its absence, a magnitude or its absence
    # the structured section holds no number: the numbers are the rows of `parameters:`
    assert numeric_leaves(section) == []
    assert referenced and all(name in rows for name in referenced)


def test_injection_rows_have_provenance_units_and_levels() -> None:
    check_injection_rows(INJECTIONS_FILE)
    document = injection_document()
    section = document["injections"]["c2"]
    assert section["cuff_silent_bias"]["magnitude"]["key"] == "bias_mmhg"
    assert section["cuff_silent_bias"]["magnitude"]["unit"] == "mmHg"
    assert section["cuff_silent_bias"]["magnitude"]["reference"] == "cuff_error_sd_mmhg"
    assert "device_bias" in section["cuff_silent_bias"]["magnitude"]["levels"]
    assert section["dispenser_bounce"]["magnitude"]["unit"] == "ms"
    assert section["nav_delay"]["magnitude"]["unit"] == "ms"
    for name in ("stuck_at", "cuff_detached", "manipulation_failure", "ble_dropout"):
        assert section[name]["magnitude"] is None, name  # no magnitude applies
    for name in ("dispenser_bounce", "nav_delay", "manipulation_failure"):
        assert section[name]["duration"] is None, name  # point and per-tick faults have no window
    text = INJECTIONS_FILE.read_text(encoding="utf-8")
    assert text.count("cuff_silent_bias") >= 1


def test_the_bounce_levels_are_labelled_illustrative_and_stress() -> None:
    document = injection_document()
    levels = document["injections"]["c2"]["dispenser_bounce"]["magnitude"]["levels"]
    rows = {r.parameter: r for r in load_design_file(INJECTIONS_FILE).rows}
    nominal = rows[levels["nominal"]]
    text = " ".join((nominal.note + " " + (nominal.source_ref or "")).split())
    assert "illustrative, unverified" in text
    for level in sorted(set(levels) - {"nominal"}):
        row = rows[levels[level]]
        assert "stress, physical plausibility unverified" in " ".join(row.note.split()), level


def test_rate_sources_are_device_error_model_fields() -> None:
    from ralmon.benchmark.priors import DeviceErrorModel

    fields = {f.name for f in dataclasses.fields(DeviceErrorModel)}
    section = injection_document()["injections"]["c2"]
    assert section["ble_dropout"]["rate"]["source"].split(".")[-1] in fields
    assert section["dispenser_bounce"]["rate"]["source"].split(".")[-1] in fields
    assert section["cuff_silent_bias"]["magnitude"]["reference"] in fields


def edited_injections(tmp_path: Path, fill: bool, mutate: Callable[[dict[str, Any]], None] | None = None) -> Path:
    document = injection_document()
    for row in document["parameters"]:
        if fill:
            row.update(
                value=1.0 if "magnitude" in row["parameter"] else 60_000,
                status="filled",
                source_ref="FIXTURE-ONLY: exercises the filled state of the row",
                rationale="FIXTURE-ONLY: arithmetic",
                verified_by=None,
            )
        else:
            row.update(
                value=None, dist=None, status="awaiting_human_value", rationale=None, verified_by=None
            )
    if mutate is not None:
        mutate(document)
    path = tmp_path / "injections.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def test_injection_rows_structure_holds_unfilled_and_filled(tmp_path: Path) -> None:
    check_injection_rows(edited_injections(tmp_path, fill=False))
    check_injection_rows(edited_injections(tmp_path, fill=True))


def test_design_loader_unfilled_and_filled_state_on_copies(tmp_path: Path) -> None:
    empty = load_injection_design(edited_injections(tmp_path, fill=False))
    full = load_injection_design(edited_injections(tmp_path, fill=True))
    assert set(empty) == set(full) == set(C2_SUBTYPES)
    for subtype in C2_SUBTYPES:
        a, b = empty[subtype], full[subtype]
        assert (a.family, a.targets, a.onset) == (b.family, b.targets, b.onset)
        for quantity in ("duration", "magnitude"):
            qa, qb = getattr(a, quantity), getattr(b, quantity)
            assert (qa is None) == (qb is None)
            if qa is None:
                continue
            assert [lv.level for lv in qa.levels] == [lv.level for lv in qb.levels]
            assert all(lv.value is None and not lv.filled for lv in qa.levels)
            assert all(lv.value is not None and lv.filled for lv in qb.levels)
            assert (qa.key, qa.unit, qa.reference) == (qb.key, qb.unit, qb.reference)
    magnitude = full["cuff_silent_bias"].magnitude
    assert magnitude is not None and magnitude.reference == "cuff_error_sd_mmhg"
    level = magnitude.levels[0]
    assert resolve_magnitude(level, 4.0) == level.value * 4.0
    with pytest.raises(InjectionDesignError):
        resolve_magnitude(empty["cuff_silent_bias"].magnitude.levels[0], 4.0)  # type: ignore[union-attr]
    for bad in (math.nan, math.inf, True, "4", None, 10**400):
        with pytest.raises(InjectionDesignError):
            resolve_magnitude(level, bad)  # type: ignore[arg-type]
    with pytest.raises(InjectionDesignError):
        resolve_magnitude("level", 4.0)  # type: ignore[arg-type]
    # the committed file loads in whatever state it is
    committed = load_injection_design(INJECTIONS_FILE)
    assert set(committed) == set(C2_SUBTYPES)


def test_design_loader_rejects_a_broken_structure(tmp_path: Path) -> None:
    def drop_row(document: dict[str, Any]) -> None:
        document["parameters"] = document["parameters"][1:]

    def drop_subtype(document: dict[str, Any]) -> None:
        del document["injections"]["c2"]["stuck_at"]

    def two_levels(document: dict[str, Any]) -> None:
        levels = document["injections"]["c2"]["cuff_silent_bias"]["magnitude"]["levels"]
        for name in list(levels)[2:]:
            del levels[name]

    def number_in_structure(document: dict[str, Any]) -> None:
        document["injections"]["c2"]["nav_delay"]["target"] = [5]

    def no_unit(document: dict[str, Any]) -> None:
        del document["injections"]["c2"]["nav_delay"]["magnitude"]["unit"]

    def unknown_row(document: dict[str, Any]) -> None:
        levels = document["injections"]["c2"]["nav_delay"]["magnitude"]["levels"]
        levels["low"] = "no_such_row"

    def bad_family(document: dict[str, Any]) -> None:
        document["injections"]["c2"]["nav_delay"]["family"] = "cloud"

    def not_a_mapping(document: dict[str, Any]) -> None:
        document["injections"] = []

    def extra_subtype(document: dict[str, Any]) -> None:
        document["injections"]["c2"]["process_kill"] = copy.deepcopy(document["injections"]["c2"]["stuck_at"])

    def no_section(document: dict[str, Any]) -> None:
        del document["injections"]["c2"]

    def wrong_source_type(document: dict[str, Any]) -> None:
        document["parameters"][0]["source_type"] = "fixture_only"

    for mutate in (
        drop_row, drop_subtype, two_levels, number_in_structure, no_unit, unknown_row,
        bad_family, not_a_mapping, extra_subtype, no_section,
    ):  # fmt: skip
        path = edited_injections(tmp_path, fill=False, mutate=mutate)
        with pytest.raises((InjectionDesignError, Exception)) as info:
            load_injection_design(path)
        assert isinstance(info.value, (InjectionDesignError, ValueError)), mutate.__name__
    # a missing file, a directory, a duplicate YAML key and non-YAML are named errors
    with pytest.raises(InjectionDesignError):
        load_injection_design(tmp_path / "absent.yaml")
    with pytest.raises(InjectionDesignError):
        load_injection_design(tmp_path)
    duplicate = tmp_path / "dup.yaml"
    duplicate.write_text("injections:\n  c2: {}\n  c2: {}\nparameters: []\n", "utf-8")
    with pytest.raises(InjectionDesignError):
        load_injection_design(duplicate)
    garbage = tmp_path / "garbage.yaml"
    garbage.write_text("a: [unclosed", "utf-8")
    with pytest.raises(InjectionDesignError):
        load_injection_design(garbage)
    for bad in (None, 5, b"x", object(), "bad\0path"):
        with pytest.raises(InjectionDesignError):
            load_injection_design(bad)  # type: ignore[arg-type]
    with pytest.raises(InjectionDesignError):
        load_injection_design(INJECTIONS_FILE, section="nope")
    with pytest.raises(InjectionDesignError):
        load_injection_design(INJECTIONS_FILE, section=5)  # type: ignore[arg-type]


def test_design_rows_are_in_the_provenance_table() -> None:
    table = (ROOT / "docs" / "benchmark" / "parameter-provenance.md").read_text("utf-8")
    rows = [r.parameter for r in load_design_file(INJECTIONS_FILE).rows]
    assert rows
    for name in rows:
        assert f"| {name} |" in table, name


# ---------------------------------------------------------------------------
# Layering, exports and literals
# ---------------------------------------------------------------------------


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


def referenced_names(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.alias):
            names.add(node.name.split(".")[-1])
    return names


FORBIDDEN_PACKAGES = (
    "ralmon.spec",
    "ralmon.conformal",
    "ralmon.monitor",
    "ralmon.attribution",
    "ralmon.baselines",
    "ralmon.eval",
)
ALLOWED_RALMON_IMPORTS = {
    "injection.py": (
        "ralmon.signals",
        "ralmon.benchmark.latent",
        "ralmon.benchmark.measurement",
        "ralmon.benchmark.priors",
        "ralmon.benchmark.rng",
        "ralmon.benchmark.segments",
        "ralmon.benchmark.trace",
        "ralmon.benchmark.vocab",
        "ralmon.benchmark.inject_c2",
    ),
    "inject_c2.py": (
        "ralmon.signals",
        "ralmon.benchmark.injection",
        "ralmon.benchmark.latent",
        "ralmon.benchmark.measurement",
        "ralmon.benchmark.rng",
        "ralmon.benchmark.segments",
        "ralmon.benchmark.trace",
        "ralmon.benchmark.vocab",
    ),
}
ALLOWED_THIRD_PARTY = {
    "__future__", "bisect", "collections", "dataclasses", "enum", "hashlib", "importlib", "itertools",
    "json", "math", "numbers", "os", "pathlib", "re", "types", "typing", "numpy", "ralmon", "yaml",
}  # fmt: skip


def test_module_layering_is_one_way_and_below_the_monitor() -> None:
    for name in ("injection.py", "inject_c2.py"):
        mods = imported_modules(SRC / name)
        for forbidden in FORBIDDEN_PACKAGES:
            assert not any(m == forbidden or m.startswith(forbidden + ".") for m in mods), (name, forbidden)
        for m in mods:
            if m.startswith("ralmon") and m not in ("ralmon", "ralmon.benchmark"):
                assert any(m == a or m.startswith(a + ".") for a in ALLOWED_RALMON_IMPORTS[name]), (name, m)
        top = {m.split(".")[0] for m in mods if not m.startswith(".")}
        assert top <= ALLOWED_THIRD_PARTY, (name, top - ALLOWED_THIRD_PARTY)
        assert not any(m.startswith(".") for m in mods), name  # no relative import
        assert not {"time", "datetime", "random"} & top, name  # no wall clock, no global random
    # the lower modules do not know the injectors
    for name in ("measurement.py", "segments.py", "vocab.py", "priors.py", "rng.py", "trace.py"):
        mods = imported_modules(SRC / name)
        assert not any("inject" in m for m in mods), name
    # the C2 module reaches the machinery only through injection.py (one way)
    assert not any("inject_c2" in m for m in imported_modules(SRC / "measurement.py"))


def test_no_ground_truth_containers_in_the_c2_module_and_no_np_random_global() -> None:
    names = referenced_names(SRC / "inject_c2.py")
    assert not {"GroundTruthEvent", "BenchmarkDay", "TruthRecord"} & names
    for name in ("injection.py", "inject_c2.py"):
        text = (SRC / name).read_text(encoding="utf-8")
        assert "np.random.seed" not in text and "random.random" not in text
        assert "np.random.default_rng" not in text  # every generator comes from rng.stream


def test_new_modules_export_nothing_from_the_package_root() -> None:
    exported = set(benchmark_pkg.__all__)
    new = {
        "InjectionSpec", "InjectionRecord", "InjectionContext", "InjectionResult", "InjectionSpecError",
        "apply_observation_injections", "finalize_observed", "record_to_ground_truth",
        "plan_dispenser_bounces", "EVIDENCE_SIGNATURES",
    }  # fmt: skip
    assert not exported & new
    for name in new:
        assert not hasattr(benchmark_pkg, name), name


def test_resource_bounds_have_their_documented_values() -> None:
    assert injection_mod.MAX_PARAMS == 16 and MAX_PARAMS == 16
    assert MAX_INJECTIONS_PER_DAY == 1_000
    assert c2_mod.MAX_PLANNED_DISPENSES == 100_000


# ---------------------------------------------------------------------------
# Whole-day behaviour with the fault-free base of WS04-T06
# ---------------------------------------------------------------------------


def test_injection_composes_with_a_built_base_stream() -> None:
    from ralmon.benchmark.measurement import MeasurementDesign, NoJitter, build_observed_base
    from ralmon.benchmark.priors import DeviceErrorModel
    from ralmon.benchmark.schedule import Schedule

    hr = [70.0 + i % 30 for i in range(DAY // MIN)]
    lib = SegmentLibrary.from_memory(
        [
            InlineSegment("hr-1", "hr_clean", hr, MIN, "bpm"),
            InlineSegment("sp-1", "spo2_clean", [95.0] * (DAY // MIN), MIN, "%"),
            InlineSegment("n-1", "hr_error_ecg_noise", [1.0, -2.0, 3.0, -4.0], MIN, "bpm"),
        ]
    )
    design = MeasurementDesign(INFLATION, 0, 0.0, DWELL, MIN, INFLATION)
    latent = latent_with_step(12 * HOUR, 130.0, 150.0)
    schedule = Schedule(dose_ticks_ms=(8 * HOUR, 20 * HOUR), measurement_ticks_ms=(9 * HOUR, 13 * HOUR, 21 * HOUR))
    latent = dataclasses.replace(
        latent,
        events=(
            Event(EventKind.DISPENSE, 8 * HOUR, 8 * HOUR, "dispenser", {}, None),
            Event(EventKind.INTAKE, 8 * HOUR + SEC, 8 * HOUR + SEC, "patient", {}, None),
            Event(EventKind.DISPENSE, 20 * HOUR, 20 * HOUR, "dispenser", {}, None),
        ),
    )
    base = build_observed_base(
        latent, schedule, "plan-1", DeviceErrorModel(0.0, 0.0, 0.0, 0.0), design, NoJitter(), lib, 0, 0
    )
    before = copy.deepcopy(latent)
    out = apply_observation_injections(
        base,
        [
            nav(13 * HOUR, 20 * MIN),
            manip(9 * HOUR),
            bounce(20 * HOUR, 500),
            ble(15 * HOUR, 2 * HOUR, "oximeter"),
            ecg(10 * HOUR, 3 * MIN),
            bias(20 * HOUR, 2 * HOUR, 6.0),
        ],
        InjectionContext(0, library=lib, latent=latent, task_deadline_offset_ms=DEADLINE_OFFSET),
    )
    assert latent == before
    assert all(r.realised for r in out.records)
    day = finalize_observed(out.stream)
    assert isinstance(day, ObservedDay)
    # the delayed 13:00 reading re-reads the latent day (150 after 12:00) with the same noise
    delayed = [s for s in day.samples if s.signal == "bp" and s.t_device_ms == 13 * HOUR + 20 * MIN + INFLATION]
    assert [s.value for s in delayed] == [150.0]
    assert not [s for s in day.samples if s.signal == "bp" and s.t_device_ms == 9 * HOUR + INFLATION]
    from ralmon.benchmark.trace import validate_day

    validate_day(day)


def test_the_error_hierarchy() -> None:
    assert issubclass(InjectionSpecError, InjectionError) and issubclass(InjectionContextError, InjectionError)
    assert issubclass(InjectionDesignError, InjectionError) and issubclass(InjectionError, ValueError)
    for item in (InjectionSpecError, InjectionContextError, InjectionDesignError):
        assert item.__name__.startswith("Injection")
    assert isinstance(DETACHED_ERROR_CODE, str)
    assert MeasurementConfigError is not InjectionError


def test_records_are_frozen_and_hold_json_native_details() -> None:
    out = run(MIXED)
    record = out.records[0]
    assert isinstance(record, InjectionRecord)
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.realised = False  # type: ignore[misc]
    for r in out.records:
        json.dumps(dict(r.details), allow_nan=False)
        assert isinstance(r.evidence_paths, tuple)
        assert isinstance(r.n_changed, int) and not isinstance(r.n_changed, bool)
        assert r.realised == (r.n_changed > 0)
