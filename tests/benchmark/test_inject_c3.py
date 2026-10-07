"""C3 integrity attacks at two attacker levels (WS04-T08).

Every number below is arithmetic and FIXTURE-ONLY (cuff readings of the previous day 128, 135, 120
and of today 131, 127, 133 at 08:00, 12:00 and 16:00 plus 30 s of inflation, heart rate 70 on the
cuff and 70 + hour on the ECG, dispenses at 08:10 and 20:00, robot dwell 10 min, physiological
bounds 50 to 250 mmHg and 40 to 180 bpm labelled illustrative): none is a clinical value, none is
a device specification and none enters a prior file used by the builder. State independence: no
test reads a committed configuration in a way that depends on whether a human has filled it; the
injection rows are exercised on copies under ``tmp_path`` in both states.

Rules under test (``ralmon.benchmark.inject_c3`` and the machinery of ``ralmon.benchmark.injection``):

* the attack stage runs after the sequence numbering and the link stage: attacker traffic is never
  renumbered by the pipeline and a dropout of the genuine device cannot remove it;
* a window is half open, ``[onset, onset + duration)`` on ``t_rx_ms``; a point attack has
  ``end_ms`` None; a replay copies the previous day's cuff messages one day after their arrival;
* the informed level keeps the delivered sequence contiguous (``fresh_metadata``), the naive level
  does not; whether a device authenticates is a deployment property (``authenticating_devices``);
* a draw is keyed by ``(seed, patient, day, INJECTION_C3, digest of the injection)``.
"""

from __future__ import annotations

import ast
import copy
import dataclasses
import hashlib
import itertools
import json
import math
import os
import re
import subprocess
import sys
import textwrap
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

import ralmon.benchmark as benchmark_pkg
import ralmon.benchmark.inject_c2 as c2_mod
import ralmon.benchmark.inject_c3 as c3_mod
import ralmon.benchmark.injection as injection_mod
from ralmon.benchmark import vocab
from ralmon.benchmark.inject_c3 import (
    C3_SUBTYPES,
    CAPABILITY_SETS,
    EXPECTED_UNDETECTABLE,
    INFORMED,
    NAIVE,
    NOT_INJECTED_IN_V1,
    AttackerCapabilities,
    attack_signature,
    capabilities_of,
    load_capability_sets,
)
from ralmon.benchmark.injection import (
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
)
from ralmon.benchmark.latent import T_DAY_MS
from ralmon.benchmark.measurement import (
    MeasurementRecord,
    ObservedStream,
    RobotVisit,
)
from ralmon.benchmark.priors import SOURCE_TYPES, load_design_file
from ralmon.benchmark.rng import StreamPurpose
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
THREAT_MODEL = ROOT / "docs" / "models" / "threat-model.md"
EVIDENCE_DOC = ROOT / "docs" / "models" / "evidence-channels.md"
INTERFACES = ROOT / "docs" / "plan" / "02-interfaces.md"
REGISTRY_FILE = ROOT / "configs" / "registry" / "hypertension.yaml"

SEC = 1_000
MIN = 60_000
HOUR = 3_600_000
DAY = T_DAY_MS
C3 = InjectedClass.C3

INFLATION = 30 * SEC  # FIXTURE-ONLY
DWELL = 10 * MIN  # FIXTURE-ONLY
PULSE = 70.0  # FIXTURE-ONLY cuff pulse rate (the ECG reads 70 + hour)
PATIENT = "p0000"
BOUNDS_BP = (50.0, 250.0)  # FIXTURE-ONLY, labelled illustrative (analisi 4.7)
BOUNDS_HR = (40.0, 180.0)  # FIXTURE-ONLY, labelled illustrative

TICKS = (8 * HOUR, 12 * HOUR, 16 * HOUR)
PREV_BPS = (128.0, 135.0, 120.0)
TODAY_BPS = (131.0, 127.0, 133.0)
DOSE_TICKS = (8 * HOUR + 10 * MIN, 20 * HOUR)
INTAKE_AFTER = MIN

X_DIFF = "cross_device.pulse_vs_ecg_hr_diff"
W_ROBOT = "witness.robot_present"
W_IDENT = "witness.identity_confirmed"
W_INTAKE = "witness.intake_observed"
C_AUTH = "crypto_temporal.authenticated"
C_SEQ = "crypto_temporal.seq_gap_or_replay"
C_TS = "crypto_temporal.timestamp_implausible"

CUFF_SIGNALS = ("bp", "inflation_ms", "cuff_health", "hr_pulse")
FLAGS = ("fresh_metadata", "coherent_pulse", "plausible_values", "spoofs_witness")


# ---------------------------------------------------------------------------
# The hand-written fixture streams
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
    day_index: int = 1,
    ticks: Sequence[int] = TICKS,
    bps: Sequence[float] | None = None,
    *,
    dose_ticks: Sequence[int] = DOSE_TICKS,
    doses_taken: Sequence[int] | None = None,
    jitter_ms: int = 0,
    seed: int = 0,
) -> ObservedStream:
    """A fault-free, unnumbered observed stream with its generator-side records.

    ``doses_taken`` lists the dose ticks at which the patient really takes the dose (a dispense
    and a witnessed intake); the others only have the robot visit. ``jitter_ms`` delays the
    arrival of every measurement visit (and its reading) after its tick.
    """
    base = day_index * DAY
    if bps is None:
        if tuple(ticks) == TICKS:
            bps = PREV_BPS if day_index == 0 else TODAY_BPS
        else:
            bps = [128.0 + k for k in range(len(ticks))]
    taken = tuple(dose_ticks) if doses_taken is None else tuple(doses_taken)
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
        arrival = tick + (jitter_ms if rank == 1 else 0)
        visits.append(
            RobotVisit(index, kind, tick, arrival, arrival + DWELL, arrival - tick)
        )
        events.append(E(EventKind.SCHEDULE_TICK, tick, "ward", {"kind": kind}))
        samples.append(S("presence", arrival, 1.0))
        events.append(
            E(
                EventKind.ROBOT_TASK,
                arrival,
                "robot",
                {"task": "navigate", "outcome": "success", "patient_id": PATIENT},
            )
        )
    for k, t in enumerate(ticks):
        tick = base + t
        arrival = tick + jitter_ms
        t_meas = arrival + INFLATION
        samples += [
            S("bp", t_meas, bps[k]),
            S("inflation_ms", t_meas, float(INFLATION)),
            S("cuff_health", t_meas, 1.0),
            S("hr_pulse", t_meas, PULSE),
        ]
        events.append(E(EventKind.MEASUREMENT, t_meas, "cuff"))
        records.append(
            MeasurementRecord(
                k, tick, arrival, t_meas, 131.4375, bps[k] - 131.4375,
                bps[k], INFLATION, False, PULSE,
            )
        )  # fmt: skip
    for t in taken:
        events.append(E(EventKind.DISPENSE, base + t, "dispenser"))
        events.append(E(EventKind.INTAKE, base + t + INTAKE_AFTER, "robot"))
    for h in range(24):
        samples.append(S("hr_ecg", base + h * HOUR, 70.0 + h))
        samples.append(S("spo2", base + h * HOUR, 95.0))
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


def numbered(stream_: ObservedStream, **kwargs: Any) -> ObservedStream:
    """The stream with the sequence numbers of the pipeline (no injection)."""
    return apply_observation_injections(
        stream_, [], InjectionContext(0, **kwargs)
    ).stream


PREV = numbered(fixture_stream(0))  # cuff messages 1 to 3, dispenses 1 and 2
TODAY = fixture_stream(1)  # numbered by the pipeline from cuff 4 and dispense 3
HOURLY_TICKS = tuple(h * HOUR for h in range(6, 18))  # 06:00 to 17:00
PREV_HOURLY = numbered(
    fixture_stream(0, HOURLY_TICKS, [120.0 + (5 * k) % 16 for k in range(12)])
)  # readings from 120 to 135 inclusive
TODAY_HOURLY = fixture_stream(
    1, HOURLY_TICKS, [128.0] + [160.0 + k for k in range(11)]
)  # 06:00 reads 128, every reading in the window is far above the previous day's


def ctx(**kwargs: Any) -> InjectionContext:
    kwargs.setdefault("patient_index", 0)
    kwargs.setdefault("previous_day", PREV)
    kwargs.setdefault("bp_bounds_mmhg", BOUNDS_BP)
    kwargs.setdefault("hr_bounds_bpm", BOUNDS_HR)
    kwargs.setdefault("cuff_start", 4)
    kwargs.setdefault("dispenser_start", 3)
    return InjectionContext(**kwargs)


def spec3(
    subtype: str,
    onset: int,
    duration: int | None = None,
    level: str | None = None,
    **params: Any,
) -> InjectionSpec:
    return InjectionSpec(C3, subtype, onset, duration, None, None, params, level)


def replay(onset: int, duration: int, level: str = "naive", **p: Any) -> InjectionSpec:
    return spec3("replay", onset, duration, level, **p)


def inj_naive(onset: int, duration: int) -> InjectionSpec:
    return spec3("injection_naive", onset, duration)


def inj_informed(onset: int, duration: int) -> InjectionSpec:
    return spec3("injection_informed", onset, duration)


def forge(onset: int, level: str = "naive", **p: Any) -> InjectionSpec:
    return spec3("dispense_forgery", onset, None, level, **p)


def spoof(
    onset: int, level: str = "naive", intake: bool | None = None
) -> InjectionSpec:
    extra = {} if intake is None else {"spoof_intake": intake}
    return spec3("presence_spoof", onset, None, level, **extra)


WINDOW = (DAY + 7 * HOUR, 10 * HOUR)  # 07:00 to 17:00 of day 1
AT = tuple(DAY + t + INFLATION for t in TICKS)  # the three message instants of day 1
CUFF_AUTH = ("cuff",)


def run(
    specs: Sequence[InjectionSpec],
    *,
    stream_: ObservedStream = TODAY,
    **kwargs: Any,
) -> InjectionResult:
    return apply_observation_injections(stream_, specs, ctx(**kwargs))


def items_at(out: InjectionResult | ObservedStream, t_rx: int) -> list[Any]:
    """The keys of the cuff items (samples and events) that arrived at ``t_rx``, in order."""
    s = out_stream(out)
    cuff = [x for x in s.samples if x.signal in CUFF_SIGNALS]
    cuff += [
        e for e in s.events if e.source == "cuff" and e.kind is not EventKind.NODE_STATE
    ]
    return [item_key(x) for x in cuff if x.t_rx_ms == t_rx]


def in_window(item: Sample | Event, window: tuple[int, int] = WINDOW) -> bool:
    """Whether an item arrived in the half-open window ``(onset, duration)``."""
    return window[0] <= item.t_rx_ms < window[0] + window[1]


def day0(**kwargs: Any) -> dict[str, Any]:
    """Keyword arguments for a run on a stream of day 0 (no previous day)."""
    return {"previous_day": None, "cuff_start": 1, "dispenser_start": 1, **kwargs}


def out_stream(out: InjectionResult | ObservedStream) -> ObservedStream:
    return out.stream if isinstance(out, InjectionResult) else out


def samples_of(out: InjectionResult | ObservedStream, signal: str) -> list[Sample]:
    return [x for x in out_stream(out).samples if x.signal == signal]


def events_of(out: InjectionResult | ObservedStream, kind: EventKind) -> list[Event]:
    return [x for x in out_stream(out).events if x.kind == kind]


def values_of(out: InjectionResult | ObservedStream, signal: str) -> list[float]:
    return [x.value for x in samples_of(out, signal)]


def gateway_events(out: InjectionResult | ObservedStream) -> list[Event]:
    return [e for e in events_of(out, EventKind.DEVICE_ERROR) if e.source == "gateway"]


def cuff_seqs(out: InjectionResult | ObservedStream) -> list[tuple[int, int | None]]:
    """``(t_rx_ms, seq)`` of every MEASUREMENT message of the cuff, in arrival order."""
    return [
        (e.t_rx_ms, e.seq)
        for e in events_of(out, EventKind.MEASUREMENT)
        if e.source == "cuff"
    ]


def item_key(item: Sample | Event, *, with_seq: bool = True) -> Any:
    seq = item.seq if with_seq else None
    if isinstance(item, Sample):
        return (
            "S",
            item.signal,
            item.t_device_ms,
            item.t_rx_ms,
            item.value,
            seq,
            item.quality,
        )
    return (
        "E", item.kind.value, item.t_device_ms, item.t_rx_ms, item.source,
        tuple(sorted(item.payload.items())), seq,
    )  # fmt: skip


def item_multiset(s: ObservedStream, *, with_seq: bool = True) -> dict[Any, int]:
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


def same(a: InjectionResult, b: InjectionResult) -> bool:
    x, y = a.stream, b.stream
    return (x.samples, x.events, x.visits, x.measurements) == (
        y.samples,
        y.events,
        y.visits,
        y.measurements,
    )


def deep_state(latent: LatentDay) -> Any:
    return (
        latent.patient_id,
        latent.day_index,
        latent.seed,
        [
            (s.signal, s.t_device_ms, s.t_rx_ms, s.value, s.seq, s.quality)
            for s in latent.samples
        ],
        [
            (
                e.kind, e.t_device_ms, e.t_rx_ms, e.source,
                copy.deepcopy(dict(e.payload)), e.seq,
            )
            for e in latent.events
        ],
    )  # fmt: skip


def latent_day(day_index: int = 1) -> LatentDay:
    """A latent day with a pressure series, one dispense at 08:10 and one intake (FIXTURE-ONLY)."""
    base = day_index * DAY
    return LatentDay(
        PATIENT,
        day_index,
        0,
        tuple(S("bp", base + t, 130.0 + t // HOUR) for t in range(0, DAY, 10 * MIN)),
        (
            E(EventKind.DISPENSE, base + DOSE_TICKS[0], "dispenser"),
            E(EventKind.INTAKE, base + DOSE_TICKS[0] + INTAKE_AFTER, "patient"),
        ),
    )


# ---------------------------------------------------------------------------
# 1. Capability sets against the threat model
# ---------------------------------------------------------------------------

# Hand-copied from the table of flags under "## Knowledge levels" of docs/models/threat-model.md
# (flag: naive, informed). A change of the document must be reflected here by a person.
HAND_COPIED_FLAGS: dict[str, tuple[bool, bool]] = {
    "fresh_metadata": (False, True),
    "coherent_pulse": (False, True),
    "plausible_values": (False, True),
    "spoofs_witness": (False, True),
}


def knowledge_flag_rows() -> dict[str, tuple[bool, bool, int, str]]:
    """The flag rows of the document: flag -> (naive, informed, line number, line)."""
    lines = THREAT_MODEL.read_text(encoding="utf-8").splitlines()
    start = next(i for i, x in enumerate(lines) if x == "## Knowledge levels")
    end = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("## "))
    rows: dict[str, tuple[bool, bool, int, str]] = {}
    for i in range(start, end):
        cells = [c.strip().strip("`") for c in lines[i].strip().strip("|").split("|")]
        if (
            lines[i].startswith("| `")
            and len(cells) >= 3
            and cells[0] in FLAGS
            and cells[1] in ("true", "false")
        ):
            rows[cells[0]] = (cells[1] == "true", cells[2] == "true", i + 1, lines[i])
    return rows


def check_flags_against_document(
    document: Mapping[str, tuple[bool, bool, int, str]],
    hand: Mapping[str, tuple[bool, bool]],
) -> None:
    for flag, (naive, informed) in hand.items():
        d_naive, d_informed, number, line = document[flag]
        assert (d_naive, d_informed) == (naive, informed), (
            f"docs/models/threat-model.md line {number} differs from the hand-copied "
            f"table for {flag}: {line}"
        )


def test_capability_sets_match_threat_model_levels() -> None:
    document = knowledge_flag_rows()
    assert set(document) == set(FLAGS) == set(HAND_COPIED_FLAGS)
    check_flags_against_document(document, HAND_COPIED_FLAGS)
    # the module constants equal the hand-copied table
    for flag, (naive, informed) in HAND_COPIED_FLAGS.items():
        assert getattr(NAIVE, flag) is naive and getattr(INFORMED, flag) is informed
    assert [f.name for f in dataclasses.fields(AttackerCapabilities)] == list(FLAGS)
    assert dict(CAPABILITY_SETS) == {"naive": NAIVE, "informed": INFORMED}
    assert capabilities_of("naive") is NAIVE and capabilities_of("informed") is INFORMED
    # the committed design file carries the same two sets, with the flags as booleans
    loaded = load_capability_sets(INJECTIONS_FILE)
    assert dict(loaded) == {"naive": NAIVE, "informed": INFORMED}
    # a difference fails with the document line: the check itself is exercised on a mutation
    mutated = dict(document)
    flag = "coherent_pulse"
    n_, i_, number, line = mutated[flag]
    mutated[flag] = (not n_, i_, number, line)
    with pytest.raises(AssertionError) as caught:
        check_flags_against_document(mutated, HAND_COPIED_FLAGS)
    assert f"line {number}" in str(caught.value) and line in str(caught.value)


def test_capability_flags_are_booleans_and_the_set_is_frozen() -> None:
    caps = AttackerCapabilities(True, False, True, False)
    assert (caps.fresh_metadata, caps.coherent_pulse) == (True, False)
    assert hash(caps) == hash(AttackerCapabilities(True, False, True, False))
    with pytest.raises(dataclasses.FrozenInstanceError):
        caps.fresh_metadata = False  # type: ignore[misc]
    for junk in (None, 0, 1, "true", 1.0, np.bool_(True), [True], math.nan, 10**400):
        for position in range(4):
            args: list[Any] = [True, True, True, True]
            args[position] = junk
            with pytest.raises(InjectionSpecError):
                AttackerCapabilities(*args)
    for bad in (None, "", "other", "Naive", 5, b"naive", ["naive"], object()):
        with pytest.raises(InjectionSpecError):
            capabilities_of(bad)  # type: ignore[arg-type]
    with pytest.raises(TypeError):  # the mapping of the levels is read-only
        CAPABILITY_SETS["naive"] = INFORMED  # type: ignore[index]


# ---------------------------------------------------------------------------
# 2 and 3. Replay of the previous day
# ---------------------------------------------------------------------------


def test_replay_copies_previous_day_values_in_window() -> None:
    for level in ("naive", "informed"):
        out = run([replay(*WINDOW, level)])
        (record,) = out.records
        assert record.realised and record.n_changed > 0  # the positive case first
        got = [(s.t_rx_ms, s.value) for s in samples_of(out, "bp")]
        assert got == [(AT[0], 128.0), (AT[1], 135.0), (AT[2], 120.0)]
        # the genuine readings of the window are suppressed, not merely hidden
        assert not {131.0, 127.0, 133.0} & set(values_of(out, "bp"))
        # the whole group of the cuff is replayed, as the previous day sent it
        assert values_of(out, "inflation_ms") == [float(INFLATION)] * 3
        assert values_of(out, "cuff_health") == [1.0] * 3
        assert len(events_of(out, EventKind.MEASUREMENT)) == 3
        # everything that is not a cuff message of the window is untouched
        assert samples_of(out, "hr_ecg") == samples_of(TODAY, "hr_ecg")
        assert events_of(out, EventKind.DISPENSE)[0].t_device_ms == DAY + DOSE_TICKS[0]


def test_replay_window_is_half_open_and_only_the_window_is_replaced() -> None:
    inside = replay(AT[1], AT[2] - AT[1], "informed")  # [12:00:30, 16:00:30)
    out = run([inside])
    assert values_of(out, "bp") == [131.0, 135.0, 133.0]  # 16:00:30 is outside
    before = replay(AT[0], AT[1] - AT[0], "informed")  # [08:00:30, 12:00:30)
    out2 = run([before])
    assert values_of(out2, "bp") == [128.0, 127.0, 133.0]  # 12:00:30 is outside
    assert out.records[0].realised and out2.records[0].realised
    # the message that arrives exactly at the end of the window is the genuine one, whole: its
    # four samples and its event, with the number the device gave it
    genuine = run([])
    for result, boundary in ((out, AT[2]), (out2, AT[1])):
        assert items_at(result, boundary) == items_at(genuine, boundary)
        assert len([k for k in items_at(result, boundary) if k[0] == "S"]) >= 4
    # and one that arrives exactly at the start belongs to the window
    assert items_at(out, AT[1]) != items_at(genuine, AT[1])


def test_replay_needs_previous_day() -> None:
    with pytest.raises(InjectionSpecError):
        run([replay(7 * HOUR, 10 * HOUR)], stream_=fixture_stream(0), **day0())
    # a day after the first needs the previous day in the context
    with pytest.raises(InjectionContextError):
        run([replay(*WINDOW)], previous_day=None)
    # and the right one: same patient, same seed, the day before
    with pytest.raises(InjectionContextError):
        run([replay(*WINDOW)], previous_day=fixture_stream(2))
    with pytest.raises(InjectionContextError):
        run([replay(*WINDOW)], previous_day=dataclasses.replace(PREV, patient_id="p1"))
    with pytest.raises(InjectionContextError):
        run([replay(*WINDOW)], previous_day=dataclasses.replace(PREV, seed=7))
    # a context that is not used is checked as well
    with pytest.raises(InjectionContextError):
        run([], previous_day=fixture_stream(2))
    # called directly, the injector refuses day 0 with the same error
    work = injection_mod.InjectionWork(fixture_stream(0), ctx(**day0()))
    with pytest.raises(InjectionSpecError):
        c3_mod.replay(work, [replay(7 * HOUR, 10 * HOUR)], ctx(**day0()))


def test_naive_replay_keeps_stale_metadata() -> None:
    out = run([replay(*WINDOW, "naive")])
    copies = [s for s in samples_of(out, "bp")]
    assert len(copies) == 3
    for copy_, prev in zip(copies, samples_of(PREV, "bp"), strict=True):
        assert copy_.t_rx_ms == prev.t_rx_ms + DAY  # delivered at the current time
        assert copy_.t_device_ms == prev.t_device_ms  # the stamp is 24 h older
        assert copy_.t_rx_ms - copy_.t_device_ms == DAY
        assert copy_.seq == prev.seq  # the previous day's number again
    assert [s.seq for s in copies] == [1, 2, 3]
    assert [e.seq for e in events_of(out, EventKind.MEASUREMENT)] == [1, 2, 3]
    for signal in CUFF_SIGNALS:
        assert [s.seq for s in samples_of(out, signal)] == [1, 2, 3]
    # a verbatim copy: the pulse is the one the cuff sent (70), not the ECG rate (78, 82, 86)
    assert values_of(out, "hr_pulse") == [PULSE] * 3
    assert [
        s.value
        for s in samples_of(out, "hr_ecg")
        if s.t_device_ms % DAY in (8 * HOUR, 12 * HOUR, 16 * HOUR)
    ] == [78.0, 82.0, 86.0]
    (record,) = out.records
    assert C_SEQ in record.evidence_paths and C_TS in record.evidence_paths
    assert record.level == "naive" and record.details["capabilities"] == {
        f: False for f in FLAGS
    }
    # a verbatim copy has a valid tag: no failed verification, authenticated or not
    assert gateway_events(out) == []
    authenticated = run([replay(*WINDOW, "naive")], authenticating_devices=CUFF_AUTH)
    assert gateway_events(authenticated) == []
    assert C_AUTH not in authenticated.records[0].evidence_paths
    assert same(out, authenticated)
    # the genuine day's own sequence is not touched outside the window
    assert samples_of(out, "hr_ecg") == samples_of(TODAY, "hr_ecg")


def test_informed_replay_rewrites_metadata() -> None:
    today = fixture_stream(1, (6 * HOUR, *TICKS), [126.0, *TODAY_BPS])
    out = run([replay(*WINDOW, "informed")], stream_=today, cuff_start=4)
    copies = samples_of(out, "bp")
    assert [s.value for s in copies] == [126.0, 128.0, 135.0, 120.0]
    inside = copies[1:]
    assert all(s.t_device_ms == s.t_rx_ms for s in inside)
    # the sequence continues from the last genuine number (04 at 06:00): 05, 06, 07
    assert [s.seq for s in copies] == [4, 5, 6, 7]
    assert [e.seq for e in events_of(out, EventKind.MEASUREMENT)] == [4, 5, 6, 7]
    (record,) = out.records
    assert record.realised and record.level == "informed"
    assert C_SEQ not in record.evidence_paths and C_TS not in record.evidence_paths
    assert record.evidence_paths == ()  # pulse patched, no authentication: no evidence
    # the pulse is the current ECG rate, exactly, at each instant (coherent_pulse)
    ecg = {s.t_device_ms: s.value for s in samples_of(out, "hr_ecg")}
    pulses = samples_of(out, "hr_pulse")
    assert [s.value for s in pulses[1:]] == [ecg[DAY + h * HOUR] for h in (8, 12, 16)]
    assert [s.value for s in pulses[1:]] == [78.0, 82.0, 86.0]
    assert pulses[0].value == PULSE  # the 06:00 genuine message is untouched
    # the metadata of every replayed item is fresh
    for e in events_of(out, EventKind.MEASUREMENT)[1:]:
        assert e.t_device_ms == e.t_rx_ms


def test_informed_replay_with_authentication_leaves_failed_verifications() -> None:
    out = run([replay(*WINDOW, "informed")], authenticating_devices=CUFF_AUTH)
    (record,) = out.records
    assert record.evidence_paths == (C_AUTH,)
    events = gateway_events(out)
    assert [e.t_rx_ms for e in events] == list(AT)
    for e in events:
        assert e.t_device_ms == e.t_rx_ms and e.seq is None
        assert e.payload == {
            vocab.KEY_VERIFICATION: vocab.VERIFICATION_FAILED,
            vocab.KEY_SUBJECT: "cuff",
        }
    assert record.details["auth_deployed"] is True
    # without authentication on the cuff there is no outcome at all
    plain = run([replay(*WINDOW, "informed")])
    assert gateway_events(plain) == []
    assert C_AUTH not in plain.records[0].evidence_paths
    # another device that authenticates does not make the cuff authenticated
    other = run([replay(*WINDOW, "informed")], authenticating_devices=("dispenser",))
    assert gateway_events(other) == [] and same(other, plain)


def test_replay_is_delivered_one_day_after_the_capture_whatever_today_does() -> None:
    jittered = numbered(
        fixture_stream(0, jitter_ms=15 * SEC)
    )  # the capture: readings at 08:00:45 and so on
    today = fixture_stream(1, jitter_ms=0)
    out = run([replay(*WINDOW, "informed")], stream_=today, previous_day=jittered)
    instants = [s.t_rx_ms for s in samples_of(out, "bp")]
    assert instants == [DAY + t + INFLATION + 15 * SEC for t in TICKS]
    # today's genuine readings of the window are gone although they sit at other instants
    assert not {131.0, 127.0, 133.0} & set(values_of(out, "bp"))
    # a patient who refused today (no genuine message in the window) is replayed all the same
    refused = fixture_stream(1, (), ())
    quiet = run([replay(*WINDOW, "naive")], stream_=refused)
    assert quiet.records[0].realised and values_of(quiet, "bp") == [128.0, 135.0, 120.0]
    assert quiet.records[0].details["n_suppressed"] == 0


def test_replay_copies_only_measurement_messages_of_the_previous_day() -> None:
    odd = dataclasses.replace(
        PREV,
        events=tuple(
            by_rx(
                [
                    *PREV.events,
                    E(
                        EventKind.DEVICE_ERROR,
                        9 * HOUR,
                        "cuff",
                        {"error_code": "X1"},
                        9,
                    ),
                    E(EventKind.MEASUREMENT_MISSED, 9 * HOUR, "cuff", {}, 9),
                    E(EventKind.NODE_STATE, 9 * HOUR, "cuff", {"state": "inactive"}),
                ]
            )
        ),
    )
    out = run([replay(*WINDOW, "naive")], previous_day=odd)
    assert [e.kind for e in out.stream.events if e.t_rx_ms == DAY + 9 * HOUR] == []
    assert len(events_of(out, EventKind.MEASUREMENT)) == 3
    assert events_of(out, EventKind.DEVICE_ERROR) == []
    assert events_of(out, EventKind.MEASUREMENT_MISSED) == []
    # a previous day with no measurement in the window leaves the replay without effect
    far = run([replay(DAY + 18 * HOUR, HOUR, "informed")])
    assert far.records[0].realised is False and far.records[0].n_changed == 0
    assert same(far, run([]))


def test_informed_replay_keeps_the_delivered_sequence_contiguous() -> None:
    # more copies than genuine messages: today's patient refused at 12:00
    short = fixture_stream(1, (8 * HOUR, 16 * HOUR, 18 * HOUR), [131.0, 133.0, 140.0])
    out = run([replay(*WINDOW, "informed")], stream_=short)
    assert [s for _, s in cuff_seqs(out)] == [
        4,
        5,
        6,
        7,
    ]  # the 18:00 message moved 6 -> 7
    assert values_of(out, "bp") == [128.0, 135.0, 120.0, 140.0]
    assert out.records[0].details["n_renumbered"] > 0
    assert out.stream.settings["next_cuff_seq"] == 8  # the counter follows the relay
    # fewer copies than genuine messages: five genuine messages, three replayed
    long = fixture_stream(
        1,
        (8 * HOUR, 10 * HOUR, 12 * HOUR, 16 * HOUR, 18 * HOUR),
        [1.0, 2.0, 3.0, 4.0, 5.0],
    )
    out2 = run([replay(*WINDOW, "informed")], stream_=long)
    assert [s for _, s in cuff_seqs(out2)] == [4, 5, 6, 7]
    assert values_of(out2, "bp") == [128.0, 135.0, 120.0, 5.0]
    assert out2.stream.settings["next_cuff_seq"] == 8  # 9 - 1
    # every sample of one message carries the number of its event
    for signal in CUFF_SIGNALS:
        assert [s.seq for s in samples_of(out2, signal)] == [4, 5, 6, 7]
    # the equal case moves nothing
    out3 = run([replay(*WINDOW, "informed")])
    assert out3.records[0].details["n_renumbered"] == 0
    assert out3.stream.settings["next_cuff_seq"] == TODAY_NEXT_CUFF


TODAY_NEXT_CUFF = run([]).stream.settings["next_cuff_seq"]


def test_informed_replay_numbers_start_after_the_last_earlier_message_or_the_day_counter() -> (
    None
):
    # no genuine message in the window, one before it: the copies follow it
    early = fixture_stream(1, (6 * HOUR,), [126.0])
    out = run([replay(*WINDOW, "informed")], stream_=early)
    assert [s for _, s in cuff_seqs(out)] == [4, 5, 6, 7]
    assert out.records[0].details["n_suppressed"] == 0
    assert out.stream.settings["next_cuff_seq"] == 8  # 5 + 3
    # no genuine message at all: the first number of the day
    none = fixture_stream(1, (), ())
    out2 = run([replay(*WINDOW, "informed")], stream_=none, cuff_start=9)
    assert [s for _, s in cuff_seqs(out2)] == [9, 10, 11]
    assert out2.stream.settings["next_cuff_seq"] == 12
    # a genuine message exactly at the end of the window belongs to the sequence that follows
    end = DAY + 18 * HOUR + INFLATION
    late = fixture_stream(1, (8 * HOUR, 12 * HOUR, 18 * HOUR), [131.0, 127.0, 140.0])
    out3 = run([replay(WINDOW[0], end - WINDOW[0], "informed")], stream_=late)
    assert [(t, s) for t, s in cuff_seqs(out3)][-1] == (
        end,
        7,
    )  # it was 6: three copies, two genuine
    assert [s for _, s in cuff_seqs(out3)] == [4, 5, 6, 7]
    assert values_of(out3, "bp") == [128.0, 135.0, 120.0, 140.0]
    for signal in (
        CUFF_SIGNALS
    ):  # the samples of the message at the boundary moved with its event
        assert [s.seq for s in samples_of(out3, signal)] == [4, 5, 6, 7], signal


def test_a_replay_that_equals_the_genuine_messages_is_not_realised() -> None:
    # today the cuff sent what the previous day sent, with the pulse of the ECG: nothing changes
    same_bps = fixture_stream(1, bps=PREV_BPS)
    ecg = {s.t_device_ms: s.value for s in samples_of(same_bps, "hr_ecg")}
    patched = tuple(
        dataclasses.replace(s, value=ecg[(s.t_rx_ms // HOUR) * HOUR])
        if s.signal == "hr_pulse"
        else s
        for s in same_bps.samples
    )
    today = dataclasses.replace(same_bps, samples=patched)
    out = run([replay(*WINDOW, "informed")], stream_=today)
    (record,) = out.records
    assert (
        record.n_changed == 0
        and record.realised is False
        and "reason" in record.details
    )
    assert same(out, run([], stream_=today))
    assert ground_truth_events(out.records) == []
    assert out.stream.settings["next_cuff_seq"] == TODAY_NEXT_CUFF
    # with the authentication of the cuff the rewritten messages still fail verification
    secured = run(
        [replay(*WINDOW, "informed")], stream_=today, authenticating_devices=CUFF_AUTH
    )
    assert secured.records[0].realised and len(gateway_events(secured)) == 3


def test_no_attack_writes_an_auth_sample() -> None:
    # a keyless injector cannot write the authentication of a dispense (EC-GAP-9, ADR-035 (3)):
    # the genuine one of the 08:10 dispense stays, nothing is added, in either deployment
    genuine = S("auth", DAY + DOSE_TICKS[0], 1.0)
    today = dataclasses.replace(
        NO_EVENING_DOSE, samples=tuple(by_rx([*NO_EVENING_DOSE.samples, genuine]))
    )
    for auth in ((), ("cuff", "dispenser")):
        out = run(ALL_C3, stream_=today, authenticating_devices=auth)
        assert all(r.realised for r in out.records)
        assert samples_of(out, "auth") == [genuine]
        for one in ALL_C3:
            single = run([one], stream_=today, authenticating_devices=auth)
            assert samples_of(single, "auth") == [genuine], one.subtype
    assert "auth" not in {s.signal for s in NO_EVENING_DOSE.samples}


def test_the_pulse_follows_the_last_ecg_sample_at_or_before_the_instant() -> None:
    extra = S(
        "hr_ecg", AT[0], 99.0
    )  # an ECG sample exactly at the instant of the message
    later = S("hr_ecg", AT[0] + 1, 55.0)  # and one just after it
    today = dataclasses.replace(
        TODAY, samples=tuple(by_rx([*TODAY.samples, extra, later]))
    )
    out = run([replay(*WINDOW, "informed")], stream_=today)
    assert [s.value for s in samples_of(out, "hr_pulse")] == [99.0, 82.0, 86.0]
    # an ECG that only starts after the message leaves the pulse of the replay as it was
    start = dataclasses.replace(
        TODAY,
        samples=tuple(
            s for s in TODAY.samples if s.signal != "hr_ecg" or s.t_rx_ms > AT[2]
        ),
    )
    out2 = run([replay(*WINDOW, "informed")], stream_=start)
    assert [s.value for s in samples_of(out2, "hr_pulse")] == [PULSE] * 3
    out3 = run([inj_informed(*WINDOW)], stream_=start)
    assert [s.value for s in samples_of(out3, "hr_pulse")] == [PULSE] * 3


def test_a_replay_cannot_leave_the_range_of_time() -> None:
    last = injection_mod._MAX_DAY_INDEX  # the last day the pipeline accepts
    top = last * DAY
    limit = injection_mod.MAX_TIME_MS
    assert (
        top + DAY > limit > top + HOUR
    )  # the premise: the end of the day is past the limit

    def previous(t: int) -> ObservedStream:
        return ObservedStream(
            PATIENT,
            last - 1,
            0,
            "plan-1",
            (S("bp", t, 131.0, 1),),
            (E(EventKind.MEASUREMENT, t, "cuff", None, 1),),
        )

    today = ObservedStream(PATIENT, last, 0, "plan-1", (), ())
    window = (top, DAY)  # the whole day, which ends past the limit
    bad = ctx(
        previous_day=previous(top - 10 * SEC)
    )  # lands one day later: past the limit
    work = injection_mod.InjectionWork(today, bad)
    with pytest.raises(InjectionContextError):  # refused before anything is written
        c3_mod.replay(work, [replay(*window, "naive")], bad)
    assert not work.samples and not work.events
    # a window that ends at the limit and a message that lands inside it: replayed as usual
    inside = (top, limit - top)
    good = ctx(previous_day=previous(top - DAY + HOUR))
    out = apply_observation_injections(today, [replay(*inside, "naive")], good)
    assert out.records[0].realised
    assert [s.t_rx_ms for s in samples_of(out, "bp")] == [top + HOUR]
    finalize_observed(out.stream)


def test_a_stream_without_numbers_gets_replayed_messages_without_numbers() -> None:
    raw_prev = fixture_stream(0)
    raw_today = fixture_stream(1)
    work = injection_mod.InjectionWork(raw_today, ctx(previous_day=raw_prev))
    (record,) = c3_mod.replay(
        work, [replay(*WINDOW, "informed")], ctx(previous_day=raw_prev)
    )
    assert record.realised
    assert {s.seq for s in work.samples if s.signal in CUFF_SIGNALS} == {None}
    assert {e.seq for e in work.events if e.kind is EventKind.MEASUREMENT} == {None}
    assert (
        "next_cuff_seq" not in work.settings
    )  # nothing numbered it, nothing invented it


def test_a_replay_with_nothing_to_replay_leaves_the_genuine_messages_alone() -> None:
    # the previous day sent nothing between 16:30 and 18:30, today's patient did (17:00)
    out = run(
        [replay(DAY + 16 * HOUR + 30 * MIN, 2 * HOUR, "informed")],
        stream_=TODAY_HOURLY,
        previous_day=PREV,
    )
    (record,) = out.records
    assert (
        record.realised is False
        and record.n_changed == 0
        and record.details["n_copies"] == 0
    )
    assert same(out, run([], stream_=TODAY_HOURLY, previous_day=PREV))
    assert 17 * HOUR + INFLATION in {s.t_rx_ms % DAY for s in samples_of(out, "bp")}


def test_the_previous_day_must_be_exactly_the_day_before() -> None:
    three = numbered(fixture_stream(0))
    today = fixture_stream(2)
    with pytest.raises(InjectionContextError):
        run([replay(2 * DAY + 7 * HOUR, 10 * HOUR)], stream_=today, previous_day=three)
    with pytest.raises(InjectionContextError):
        run([], stream_=today, previous_day=three)
    ok = run(
        [replay(2 * DAY + 7 * HOUR, 10 * HOUR)],
        stream_=today,
        previous_day=numbered(fixture_stream(1)),
    )
    assert ok.records[0].realised


def test_a_replayed_duplicate_sequence_number_is_not_renumbered_by_finalisation() -> (
    None
):
    out = run([replay(*WINDOW, "naive")])
    day = finalize_observed(out.stream)
    assert [e.seq for e in day.events if e.kind is EventKind.MEASUREMENT] == [1, 2, 3]
    assert [s.seq for s in day.samples if s.signal == "bp"] == [1, 2, 3]
    assert out.stream.settings["next_cuff_seq"] == TODAY_NEXT_CUFF == 7


# ---------------------------------------------------------------------------
# 6 and 7. Injection of values at two levels
# ---------------------------------------------------------------------------


def test_injection_naive_values_and_incoherent_pulse() -> None:
    out = run([inj_naive(*WINDOW)], stream_=TODAY_HOURLY, previous_day=PREV_HOURLY)
    (record,) = out.records
    assert record.realised and record.level == "naive"
    forged = [s for s in samples_of(out, "bp") if in_window(s)]
    # one forged message for each genuine message of the window (07:00 to 16:00)
    assert len(forged) == 10
    lo, hi = BOUNDS_BP
    assert all(lo <= s.value <= hi for s in forged)
    genuine = {160.0 + k for k in range(10)}
    assert not genuine & {s.value for s in forged}  # the genuine ones are gone
    # the messages outside the window are the genuine ones
    outside = [s.value for s in samples_of(out, "bp") if not in_window(s)]
    assert outside == [128.0, 170.0]
    # the values ignore the patient's history: some lie outside the range of the readings
    assert any(not 120.0 <= s.value <= 135.0 for s in forged)
    # the pulse rate is independent of the ECG at the same instant
    ecg = {s.t_device_ms: s.value for s in samples_of(out, "hr_ecg")}
    pulses = [s for s in samples_of(out, "hr_pulse") if in_window(s)]
    assert len(pulses) == 10
    for p in pulses:
        held = ecg[(p.t_rx_ms // HOUR) * HOUR]
        assert p.value != held and BOUNDS_HR[0] <= p.value <= BOUNDS_HR[1]
    assert X_DIFF in record.evidence_paths and C_SEQ in record.evidence_paths
    # the stamp is the receive time, inside the bounds: nothing is late
    assert C_TS not in record.evidence_paths
    # the forged messages carry no group: the system template reads the held earlier values
    assert not [s for s in samples_of(out, "cuff_health") if in_window(s)]
    assert not [s for s in samples_of(out, "inflation_ms") if in_window(s)]
    messages = [e for e in events_of(out, EventKind.MEASUREMENT) if in_window(e)]
    assert len(messages) == 10 and all(e.t_device_ms == e.t_rx_ms for e in messages)
    # a keyless forger that does not know the counter numbers its own messages from one
    assert [e.seq for e in messages] == list(range(1, 11))
    assert [s.seq for s in forged] == list(range(1, 11))
    assert [s.seq for s in pulses] == list(range(1, 11))
    # the genuine messages around the window keep the device's numbers
    assert [
        e.seq for e in events_of(out, EventKind.MEASUREMENT) if not in_window(e)
    ] == [4, 15]
    assert record.details["n_forged"] == 10 and record.details["n_suppressed"] == 50


def test_injection_naive_ignores_the_history_of_the_patient() -> None:
    a = run([inj_naive(*WINDOW)], stream_=TODAY_HOURLY, previous_day=PREV_HOURLY)
    shifted = numbered(fixture_stream(0, HOURLY_TICKS, [200.0 + k for k in range(12)]))
    b = run([inj_naive(*WINDOW)], stream_=TODAY_HOURLY, previous_day=shifted)
    assert samples_of(a, "bp") == samples_of(b, "bp")
    assert samples_of(a, "hr_pulse") == samples_of(b, "hr_pulse")
    no_prev = run([inj_naive(*WINDOW)], stream_=TODAY_HOURLY, previous_day=None)
    assert samples_of(a, "bp") == samples_of(no_prev, "bp")
    # nor does it read what today's genuine readings were (the forged ones are the same)
    other_today = fixture_stream(1, HOURLY_TICKS, [90.0 + k for k in range(12)])
    c = run([inj_naive(*WINDOW)], stream_=other_today, previous_day=PREV_HOURLY)
    forged = [s for s in samples_of(a, "bp") if in_window(s)]
    assert forged and forged == [s for s in samples_of(c, "bp") if in_window(s)]
    assert [s for s in samples_of(a, "hr_pulse") if in_window(s)] == [
        s for s in samples_of(c, "hr_pulse") if in_window(s)
    ]


def test_injection_naive_needs_the_population_bounds() -> None:
    with pytest.raises(InjectionContextError):
        run([inj_naive(*WINDOW)], bp_bounds_mmhg=None)
    with pytest.raises(InjectionContextError):
        run([inj_naive(*WINDOW)], hr_bounds_bpm=None)
    # no attack that needs no bounds asks for them
    run([replay(*WINDOW)], bp_bounds_mmhg=None, hr_bounds_bpm=None)
    run([inj_informed(*WINDOW)], bp_bounds_mmhg=None, hr_bounds_bpm=None)


def test_injection_informed_values_and_coherent_pulse() -> None:
    out = run([inj_informed(*WINDOW)], stream_=TODAY_HOURLY, previous_day=PREV_HOURLY)
    (record,) = out.records
    assert record.realised and record.level == "informed"
    forged = [s for s in samples_of(out, "bp") if in_window(s)]
    assert len(forged) == 10
    # inside the minimum and the maximum of the patient's own genuine readings: the previous day
    # (120 to 135) and the reading of 06:00 (128); the genuine readings of the window, which
    # lie far above, are not part of what the attacker has captured before the attack
    assert all(120.0 <= s.value <= 135.0 for s in forged)
    assert len({s.value for s in forged}) > 1  # drawn, not copied
    # the pulse rate equals the ECG rate exactly at each injected instant
    ecg = {s.t_device_ms: s.value for s in samples_of(out, "hr_ecg")}
    pulses = [s for s in samples_of(out, "hr_pulse") if in_window(s)]
    assert len(pulses) == 10
    assert all(p.value == ecg[(p.t_rx_ms // HOUR) * HOUR] for p in pulses)
    assert all(p.value != PULSE for p in pulses)  # the genuine pulse (70) was replaced
    # fresh metadata: the stamp is the receive time and the numbers are the genuine ones
    messages = [e for e in events_of(out, EventKind.MEASUREMENT) if in_window(e)]
    assert all(e.t_device_ms == e.t_rx_ms for e in messages)
    assert [e.seq for e in messages] == list(range(5, 15))
    assert [s.seq for s in forged] == list(range(5, 15))
    assert [s.seq for s in pulses] == list(range(5, 15))
    assert [e.seq for e in events_of(out, EventKind.MEASUREMENT)] == list(range(4, 16))
    # the group is written as the device does: the genuine health and inflation stay
    assert values_of(out, "cuff_health") == [1.0] * 12
    assert values_of(out, "inflation_ms") == [float(INFLATION)] * 12
    assert record.evidence_paths == ()  # no authentication: nothing at all
    assert record.details["n_renumbered"] == 0
    assert out.stream.settings["next_cuff_seq"] == 16


def test_injection_informed_range_is_the_range_of_what_was_captured_before() -> None:
    # the previous day alone: 120 to 135; today's reading at 06:00 (140) widens it
    wide = fixture_stream(1, HOURLY_TICKS, [140.0] + [160.0 + k for k in range(11)])
    reached = set()
    for seed in range(20):
        out = run(
            [inj_informed(*WINDOW)],
            stream_=dataclasses.replace(wide, seed=seed),
            previous_day=dataclasses.replace(PREV_HOURLY, seed=seed),
        )
        forged = [s.value for s in samples_of(out, "bp") if in_window(s)]
        assert len(forged) == 10 and all(120.0 <= v <= 140.0 for v in forged)
        reached.add(max(forged) > 135.0)
    # the reading of today before the window is in the history: values above 135 are drawn
    assert True in reached
    # a single captured value is the only value that can be forged
    one = numbered(fixture_stream(0, (8 * HOUR,), [127.0]))
    out2 = run([inj_informed(*WINDOW)], previous_day=one)
    assert set(values_of(out2, "bp")) == {127.0}


def test_a_reading_that_arrives_at_the_onset_is_not_part_of_what_was_captured_before() -> (
    None
):
    onset = DAY + 7 * HOUR + INFLATION  # the 07:00 reading (160) arrives exactly then
    window = (onset, 9 * HOUR)
    for seed in range(8):
        out = run(
            [inj_informed(*window)],
            stream_=dataclasses.replace(TODAY_HOURLY, seed=seed),
            previous_day=dataclasses.replace(PREV_HOURLY, seed=seed),
        )
        forged = [s.value for s in samples_of(out, "bp") if in_window(s, window)]
        assert len(forged) == 9 and all(120.0 <= v <= 135.0 for v in forged), seed


def test_a_naive_pulse_is_not_the_pressure_draw() -> None:
    out = run([inj_naive(*WINDOW)], stream_=TODAY_HOURLY)
    (bp_lo, bp_hi), (hr_lo, hr_hi) = BOUNDS_BP, BOUNDS_HR
    bp = [
        (s.value - bp_lo) / (bp_hi - bp_lo)
        for s in samples_of(out, "bp")
        if in_window(s)
    ]
    hr = [
        (s.value - hr_lo) / (hr_hi - hr_lo)
        for s in samples_of(out, "hr_pulse")
        if in_window(s)
    ]
    assert len(bp) == len(hr) == 10 and len({round(x, 12) for x in bp + hr}) == 20


def test_forged_values_stay_in_the_bounds_whatever_the_rounding() -> None:
    # degenerate and huge bounds: the value is exactly the bound, and always finite
    for bounds in ((50.1, 50.1), (-1e308, 1e308), (0.1, 0.1), (1e308, 1e308)):
        out = run(
            [inj_naive(*WINDOW)],
            stream_=TODAY_HOURLY,
            bp_bounds_mmhg=bounds,
            hr_bounds_bpm=bounds,
        )
        values = [
            s.value
            for s in samples_of(out, "bp") + samples_of(out, "hr_pulse")
            if in_window(s)
        ]
        assert len(values) == 20 and all(math.isfinite(v) for v in values)
        assert all(bounds[0] <= v <= bounds[1] for v in values)
        if bounds[0] == bounds[1]:
            assert set(values) == {bounds[0]}
        finalize_observed(out.stream)
    rng = np.random.default_rng(7)  # FIXTURE-ONLY seed of the test
    for _ in range(2_000):
        low = float(rng.uniform(-300, 300))
        high = low + float(rng.choice([0.0, 1e-9, 1.0, 400.0]))
        for u in (0.0, float(rng.random()), float(np.nextafter(1.0, 0.0))):
            assert low <= c3_mod._draw(low, high, u) <= high


def test_injection_informed_without_a_capture_is_not_realised() -> None:
    # day 0, the window opens before the first reading, no previous day: nothing was captured
    out = run([inj_informed(7 * HOUR, 10 * HOUR)], stream_=fixture_stream(0), **day0())
    (record,) = out.records
    assert record.realised is False and record.n_changed == 0
    assert "reason" in record.details
    assert same(out, run([], stream_=fixture_stream(0), **day0()))
    assert ground_truth_events(out.records) == []


def test_injection_windows_without_a_genuine_message_are_not_realised() -> None:
    for s in (inj_naive(DAY + 9 * HOUR, HOUR), inj_informed(DAY + 9 * HOUR, HOUR)):
        out = run([s])
        assert out.records[0].realised is False
        assert same(out, run([]))


def test_a_window_that_holds_only_a_failed_attempt_has_no_reading_to_forge() -> None:
    failed = InjectionSpec(InjectedClass.C2, "cuff_detached", DAY + 11 * HOUR, 2 * HOUR)
    around = (
        DAY + 11 * HOUR + 30 * MIN,
        2 * HOUR,
    )  # holds the failed 12:00:30 attempt only
    base = run([failed])
    assert events_of(base, EventKind.MEASUREMENT_MISSED) and events_of(
        base, EventKind.DEVICE_ERROR
    )
    for attack in (inj_naive(*around), inj_informed(*around)):
        out = run([failed, attack])
        assert out.records[-1].realised is False and out.records[-1].n_changed == 0
        assert same(
            out, base
        )  # the failure report is the device's: nobody forges over it


def test_injection_with_authentication_logs_a_failed_verification_for_every_message() -> (
    None
):
    for s in (inj_naive(*WINDOW), inj_informed(*WINDOW)):
        out = run([s], authenticating_devices=CUFF_AUTH)
        assert [e.t_rx_ms for e in gateway_events(out)] == list(AT)
        assert C_AUTH in out.records[0].evidence_paths
    assert run([inj_informed(*WINDOW)], authenticating_devices=CUFF_AUTH).records[
        0
    ].evidence_paths == (C_AUTH,)


def test_informed_injection_keeps_the_sequence_contiguous_over_a_failed_attempt() -> (
    None
):
    from ralmon.benchmark.inject_c2 import C2_SUBTYPES  # noqa: F401  (registers C2)

    failed = InjectionSpec(InjectedClass.C2, "cuff_detached", DAY + 11 * HOUR, 2 * HOUR)
    out = run([failed, inj_informed(*WINDOW)])
    # 08:00 and 16:00 are forged; the failed attempt of 12:00 was a message of the window
    assert [s for _, s in cuff_seqs(out)] == [4, 5]
    assert events_of(out, EventKind.MEASUREMENT_MISSED) == []
    assert out.stream.settings["next_cuff_seq"] == 6
    day = finalize_observed(out.stream)
    assert [s.seq for s in day.samples if s.signal == "bp"] == [4, 5]


def test_an_informed_attack_does_not_renumber_attacker_traffic_that_ignores_the_counter() -> (
    None
):
    detached = InjectionSpec(InjectedClass.C2, "cuff_detached", DAY + 8 * HOUR, HOUR)
    informed = inj_informed(
        DAY + 7 * HOUR, 3 * HOUR
    )  # 07:00 to 10:00, with a failed attempt
    # 14:00:30 and 15:00:30 are forged; the genuine message of 16:00:30 arrives at the very end
    naive = inj_naive(DAY + 14 * HOUR, 2 * HOUR + INFLATION)
    kwargs = {"stream_": TODAY_HOURLY, "previous_day": PREV_HOURLY}
    base = run([detached, naive], **kwargs)
    both = run([detached, naive, informed], **kwargs)
    # the informed window held three messages (07:00, the failed 08:00, 09:00) and two forged
    # readings: the relay closes the gap, so every genuine message after the window moves by one
    assert (
        both.records[-1].spec == informed
        and both.records[-1].details["n_renumbered"] > 0
    )
    forged_at = [DAY + 14 * HOUR + INFLATION, DAY + 15 * HOUR + INFLATION]
    for signal in ("bp", "hr_pulse"):  # the samples as well as the events
        moved = {s.t_rx_ms: s.seq for s in samples_of(both, signal)}
        original = {s.t_rx_ms: s.seq for s in samples_of(base, signal)}
        for t in forged_at:  # the numbers of the naive forger are its own: untouched
            assert moved[t] == original[t] and original[t] in (1, 2)
        for t, seq in moved.items():
            if t > DAY + 10 * HOUR and t not in forged_at:
                assert seq == original[t] - 1, (
                    signal,
                    t,
                )  # the genuine ones moved by one
    events_moved = {t: seq for t, seq in cuff_seqs(both)}
    events_original = {t: seq for t, seq in cuff_seqs(base)}
    assert [events_moved[t] for t in forged_at] == [
        events_original[t] for t in forged_at
    ]
    boundary = (
        DAY + 16 * HOUR + INFLATION
    )  # arrives exactly when the naive window closes
    assert events_moved[boundary] == events_original[boundary] - 1
    assert (
        both.stream.settings["next_cuff_seq"]
        == base.stream.settings["next_cuff_seq"] - 1
    )
    assert duplicates_at_one_instant(both) == []


def test_a_stale_replay_keeps_its_numbers_whatever_an_informed_attack_does() -> None:
    detached = InjectionSpec(InjectedClass.C2, "cuff_detached", DAY + 8 * HOUR, HOUR)
    informed = inj_informed(DAY + 7 * HOUR, 3 * HOUR)
    stale = replay(
        DAY + 15 * HOUR, 2 * HOUR, "naive"
    )  # copies of the previous day, 15:00 and 16:00
    kwargs = {"stream_": TODAY_HOURLY, "previous_day": PREV_HOURLY}
    out = run([detached, informed, stale], **kwargs)
    copies = [
        e
        for e in events_of(out, EventKind.MEASUREMENT)
        if DAY + 15 * HOUR <= e.t_rx_ms < DAY + 17 * HOUR
    ]
    previous = [
        e
        for e in events_of(PREV_HOURLY, EventKind.MEASUREMENT)
        if 15 * HOUR <= e.t_rx_ms < 17 * HOUR
    ]
    assert len(copies) == len(previous) == 2
    assert [e.seq for e in copies] == [
        e.seq for e in previous
    ]  # the previous day's numbers
    assert all(e.t_device_ms == e.t_rx_ms - DAY for e in copies)


# ---------------------------------------------------------------------------
# 8. Dispense forgery
# ---------------------------------------------------------------------------

FORGED_AT = DAY + 14 * HOUR


def test_dispense_forgery_adds_dispense_without_latent_event() -> None:
    latent = latent_day()
    before, snapshot = deep_state(latent), copy.deepcopy(latent)
    base = run([], latent=latent)
    out = run([forge(FORGED_AT, "naive")], latent=latent)
    assert deep_state(latent) == before and latent == snapshot
    dispenses = events_of(out, EventKind.DISPENSE)
    assert len(dispenses) == len(events_of(base, EventKind.DISPENSE)) + 1
    extra = [e for e in dispenses if e.t_device_ms == FORGED_AT]
    assert len(extra) == 1
    assert extra[0].source == "dispenser" and extra[0].t_rx_ms == FORGED_AT
    assert dict(extra[0].payload) == {} and extra[0].seq is not None
    # no authentication sample, no intake: the forger cannot write either
    assert samples_of(out, "auth") == []
    assert events_of(out, EventKind.INTAKE) == events_of(base, EventKind.INTAKE)
    assert [s for s in out.stream.samples if s.signal == "presence"] == [
        s for s in base.stream.samples if s.signal == "presence"
    ]
    # exactly one C3 truth event, a point
    (record,) = out.records
    truth = record_to_ground_truth(record)
    assert truth == GroundTruthEvent(
        C3, "dispense_forgery", FORGED_AT, None, True, None, None
    )
    assert truth is not None and truth.end_ms is None
    assert ground_truth_events(out.records) == [truth]
    assert latent.events == snapshot.events  # latent unchanged: no dose was released


def test_dispense_forgery_numbers_follow_the_fresh_metadata_flag() -> None:
    # genuine dispenses of day 1 are numbered 3 (08:10) and 4 (20:00)
    informed = run([forge(FORGED_AT, "informed")])
    numbers = [
        (e.t_device_ms - DAY, e.seq) for e in events_of(informed, EventKind.DISPENSE)
    ]
    assert numbers == [(DOSE_TICKS[0], 3), (14 * HOUR, 4), (DOSE_TICKS[1], 5)]
    # the relay renumbered the later genuine dispense: no gap, no duplicate
    assert informed.stream.settings["next_dispenser_seq"] == 6
    assert informed.records[0].details["n_renumbered"] == 1
    assert informed.records[0].evidence_paths == ()
    # the naive forger numbers its own message from one: the device's counter is untouched
    naive = run([forge(FORGED_AT, "naive")])
    numbers = [
        (e.t_device_ms - DAY, e.seq) for e in events_of(naive, EventKind.DISPENSE)
    ]
    assert numbers == [(DOSE_TICKS[0], 3), (14 * HOUR, 1), (DOSE_TICKS[1], 4)]
    assert naive.stream.settings["next_dispenser_seq"] == 5
    # 14:00 is between visits: the robot is away, so no witness field reads False
    assert {C_SEQ} == set(naive.records[0].evidence_paths)
    # a forgery before every genuine dispense takes the first number of the day
    first = run([forge(DAY + HOUR, "informed")])
    assert [e.seq for e in events_of(first, EventKind.DISPENSE)] == [3, 4, 5]
    # after the last one it takes the next number and renumbers nothing
    last = run([forge(DAY + 22 * HOUR, "informed")])
    assert [e.seq for e in events_of(last, EventKind.DISPENSE)] == [3, 4, 5]
    assert last.records[0].details["n_renumbered"] == 0
    # two forgeries on one day keep the sequence contiguous whatever the order of the specs
    two = [forge(DAY + 9 * HOUR, "informed"), forge(DAY + 21 * HOUR, "informed")]
    a, b = run(two), run(list(reversed(two)))
    assert same(a, b)
    assert [e.seq for e in events_of(a, EventKind.DISPENSE)] == [3, 4, 5, 6]
    assert a.stream.settings["next_dispenser_seq"] == 7


def test_a_forgery_on_a_day_without_a_dispense_takes_the_counter_of_the_day() -> None:
    quiet = fixture_stream(
        1, doses_taken=()
    )  # the robot visits, the dispenser never opens
    assert not events_of(quiet, EventKind.DISPENSE)
    informed = run([forge(FORGED_AT, "informed")], stream_=quiet, dispenser_start=7)
    assert [e.seq for e in events_of(informed, EventKind.DISPENSE)] == [7]
    assert informed.stream.settings["next_dispenser_seq"] == 8
    naive = run([forge(FORGED_AT, "naive")], stream_=quiet, dispenser_start=7)
    assert [e.seq for e in events_of(naive, EventKind.DISPENSE)] == [1]
    assert naive.stream.settings["next_dispenser_seq"] == 7


def test_a_naive_forgery_never_shares_the_number_of_a_genuine_dispense_at_its_instant() -> (
    None
):
    out = run([forge(DAY + DOSE_TICKS[0], "naive")], dispenser_start=1)
    at = [
        e
        for e in events_of(out, EventKind.DISPENSE)
        if e.t_device_ms == DAY + DOSE_TICKS[0]
    ]
    assert len(at) == 2
    assert len({(e.kind, e.source, e.seq) for e in at}) == 2  # distinct numbers
    assert sorted(e.seq for e in at) == [1, 2]  # type: ignore[type-var]


def test_dispense_forgery_with_authentication_is_a_failed_verification() -> None:
    out = run([forge(FORGED_AT, "informed")], authenticating_devices=("dispenser",))
    assert out.records[0].evidence_paths == (C_AUTH,)
    (event,) = gateway_events(out)
    assert event.t_rx_ms == FORGED_AT and event.payload == {
        vocab.KEY_VERIFICATION: vocab.VERIFICATION_FAILED,
        vocab.KEY_SUBJECT: "dispenser",
    }
    # the cuff authenticating says nothing about the dispenser
    plain = run([forge(FORGED_AT, "informed")], authenticating_devices=CUFF_AUTH)
    assert gateway_events(plain) == [] and plain.records[0].evidence_paths == ()
    assert (
        C_AUTH
        in run([forge(FORGED_AT, "naive")], authenticating_devices=("dispenser",))
        .records[0]
        .evidence_paths
    )


# ---------------------------------------------------------------------------
# 9. Presence spoof
# ---------------------------------------------------------------------------

SPOOF_AT = DAY + DOSE_TICKS[1] + MIN  # 20:01, inside the 20:00 visit [20:00, 20:10]
NO_EVENING_DOSE = fixture_stream(
    1, doses_taken=(DOSE_TICKS[0],)
)  # the robot visits, no intake


def test_presence_spoof_emits_presence_and_optional_intake() -> None:
    latent = latent_day()
    before = deep_state(latent)
    base = run([], stream_=NO_EVENING_DOSE, latent=latent)
    naive = run([spoof(SPOOF_AT, "naive")], stream_=NO_EVENING_DOSE, latent=latent)
    (record,) = naive.records
    assert record.realised and record.n_changed == 1  # the positive case
    added = [s for s in naive.stream.samples if s not in base.stream.samples]
    assert added == [Sample("presence", SPOOF_AT, SPOOF_AT, 1.0, None, None)]
    assert events_of(naive, EventKind.INTAKE) == events_of(base, EventKind.INTAKE)
    assert record.evidence_paths == (W_IDENT,)
    # informed, with a forged dispense before it, and with the intake spoofed
    forged = forge(DAY + DOSE_TICKS[1], "informed")
    full = run(
        [forged, spoof(SPOOF_AT, "informed", intake=True)],
        stream_=NO_EVENING_DOSE,
        latent=latent,
    )
    intakes = [
        e for e in events_of(full, EventKind.INTAKE) if e.t_device_ms > DAY + 9 * HOUR
    ]
    assert len(intakes) == 1
    (intake,) = intakes
    assert intake.source == "robot" and intake.t_device_ms == intake.t_rx_ms == SPOOF_AT
    assert dict(intake.payload) == {} and intake.seq is None
    dispense = [
        e for e in events_of(full, EventKind.DISPENSE) if e.t_device_ms > DAY + 9 * HOUR
    ]
    assert [e.t_device_ms for e in dispense] == [DAY + DOSE_TICKS[1]]
    assert (
        dispense[0].t_device_ms <= intake.t_device_ms
    )  # coherent with the forged dispense
    visit = next(v for v in NO_EVENING_DOSE.visits if v.tick_ms == DAY + DOSE_TICKS[1])
    assert (
        visit.arrival_ms <= intake.t_device_ms <= visit.departure_ms
    )  # inside the dwell
    assert record_of(full, "presence_spoof").details["spoof_intake"] is True
    assert full.records[1].evidence_paths == () and full.records[0].evidence_paths == ()
    # without the option the informed level reports the presence only
    only = run([spoof(SPOOF_AT, "informed")], stream_=NO_EVENING_DOSE)
    assert events_of(only, EventKind.INTAKE) == events_of(base, EventKind.INTAKE)
    assert only.records[0].details["spoof_intake"] is False
    # no latent intake exists in any of the cases, and the latent day never changed
    assert [e.t_device_ms for e in latent.events if e.kind is EventKind.INTAKE] == [
        DAY + DOSE_TICKS[0] + INTAKE_AFTER
    ]
    assert deep_state(latent) == before


def test_presence_spoof_needs_a_robot_in_the_room() -> None:
    # 12:30 is between visits: the robot is not co-located and the channel stays None
    out = run([spoof(DAY + 12 * HOUR + 30 * MIN, "informed", intake=True)])
    (record,) = out.records
    assert record.realised is False and "reason" in record.details
    assert same(out, run([]))
    assert ground_truth_events(out.records) == []
    # the dwell is a closed interval on both ends
    visit = next(v for v in TODAY.visits if v.tick_ms == DAY + DOSE_TICKS[1])
    for t, expect in (
        (visit.arrival_ms, True), (visit.departure_ms, True),
        (visit.arrival_ms - 1, False), (visit.departure_ms + 1, False),
    ):  # fmt: skip
        # the informed spoof with an intake: at the arrival the presence sample already exists,
        # the intake is new, so the dwell alone decides whether it is realised
        out = run([spoof(t, "informed", intake=True)], stream_=NO_EVENING_DOSE)
        assert out.records[0].realised is expect


def test_presence_spoof_option_needs_the_informed_level() -> None:
    with pytest.raises(InjectionSpecError):
        run([spoof(SPOOF_AT, "naive", intake=True)])
    run([spoof(SPOOF_AT, "naive", intake=False)])  # the explicit default is allowed
    for bad in (1, 0, "true", "yes", None, 1.0):
        with pytest.raises(InjectionSpecError):
            run([spec3("presence_spoof", SPOOF_AT, None, "informed", spoof_intake=bad)])


# ---------------------------------------------------------------------------
# 10. The informed attacker coherent on every channel is undetectable by construction
# ---------------------------------------------------------------------------


def test_informed_coherent_attack_is_undetectable_by_construction() -> None:
    latent = latent_day()
    out = run([inj_informed(*WINDOW)], latent=latent)
    (record,) = out.records
    assert record.realised  # the attack happened
    assert (
        record.evidence_paths == ()
        and attack_signature("injection_informed", INFORMED, False) == ()
    )
    assert record.details[EXPECTED_UNDETECTABLE] is True
    assert EXPECTED_UNDETECTABLE == "expected_undetectable"
    # and it still has a ground-truth event: the limit is a result, not a margin note
    truth = ground_truth_events(out.records)
    assert truth == [
        GroundTruthEvent(
            C3, "injection_informed", WINDOW[0], sum(WINDOW), True, None, None
        )
    ]
    (entry,) = injection_log(out.records)
    assert entry["details"]["expected_undetectable"] is True
    assert entry["evidence_paths"] == [] and entry["cls"] == "C3"
    # nothing of the trace tells it from a genuine day: no gateway event, no stale stamp,
    # a continuing sequence, the pulse equal to the ECG rate
    assert gateway_events(out) == []
    # with authentication deployed the signature is exactly the failed verification
    secured = run(
        [inj_informed(*WINDOW)], authenticating_devices=CUFF_AUTH, latent=latent
    )
    (srecord,) = secured.records
    assert srecord.evidence_paths == (C_AUTH,)
    assert srecord.details[EXPECTED_UNDETECTABLE] is False
    assert attack_signature("injection_informed", INFORMED, True) == (C_AUTH,)
    assert len(ground_truth_events(secured.records)) == 1
    # the tag is not on the other cases
    assert run([inj_naive(*WINDOW)]).records[0].details[EXPECTED_UNDETECTABLE] is False
    assert (
        run([replay(*WINDOW, "naive")]).records[0].details[EXPECTED_UNDETECTABLE]
        is False
    )


def test_the_tag_follows_the_signature_for_every_subtype_level_and_deployment() -> None:
    cases = [
        (replay(*WINDOW, "naive"), False), (replay(*WINDOW, "informed"), True),
        (inj_naive(*WINDOW), False), (inj_informed(*WINDOW), True),
        (forge(FORGED_AT, "naive"), False), (forge(FORGED_AT, "informed"), True),
        (spoof(SPOOF_AT, "naive"), False), (spoof(SPOOF_AT, "informed"), True),
    ]  # fmt: skip
    for s, undetectable_in_u in cases:
        stream_ = NO_EVENING_DOSE if s.subtype == "presence_spoof" else TODAY
        for auth in ((), ("cuff", "dispenser")):
            out = run([s], stream_=stream_, authenticating_devices=auth)
            (r,) = out.records
            assert r.realised, s
            tagged = r.details[EXPECTED_UNDETECTABLE]
            assert tagged is (len(r.evidence_paths) == 0), (s, auth)
            if not auth:
                assert tagged is undetectable_in_u, s
            if s.subtype == "presence_spoof":
                assert tagged is (s.level == "informed")  # the robot link has no tag
            if s.level == "informed" and s.subtype != "presence_spoof":
                assert tagged is (not auth)


# ---------------------------------------------------------------------------
# attack_signature
# ---------------------------------------------------------------------------

SIGNATURES: dict[tuple[str, str, bool], set[str]] = {
    ("replay", "naive", False): {C_SEQ, C_TS},
    ("replay", "naive", True): {C_SEQ, C_TS},  # a verbatim copy has a valid tag
    ("replay", "informed", False): set(),
    ("replay", "informed", True): {C_AUTH},
    ("injection_naive", "naive", False): {X_DIFF, C_SEQ},
    ("injection_naive", "naive", True): {X_DIFF, C_SEQ, C_AUTH},
    ("injection_informed", "informed", False): set(),
    ("injection_informed", "informed", True): {C_AUTH},
    ("dispense_forgery", "naive", False): {C_SEQ, W_ROBOT, W_INTAKE},
    ("dispense_forgery", "naive", True): {C_SEQ, W_ROBOT, W_INTAKE, C_AUTH},
    ("dispense_forgery", "informed", False): set(),
    ("dispense_forgery", "informed", True): {C_AUTH},
    ("presence_spoof", "naive", False): {W_IDENT},
    ("presence_spoof", "naive", True): {W_IDENT},
    ("presence_spoof", "informed", False): set(),
    ("presence_spoof", "informed", True): set(),
}  # transcribed from the table of TX-9 and the attack-to-evidence table of the threat model


def test_attack_signature_follows_the_attack_to_evidence_table() -> None:
    for (subtype, level, auth), expected in SIGNATURES.items():
        got = attack_signature(subtype, capabilities_of(level), auth)
        assert isinstance(got, tuple) and len(set(got)) == len(got)
        assert set(got) == expected, (subtype, level, auth)
    # the flags act one at a time
    flags = AttackerCapabilities
    assert set(attack_signature("replay", flags(True, False, False, False), False)) == {
        X_DIFF
    }
    assert set(attack_signature("replay", flags(True, False, False, False), True)) == {
        X_DIFF,
        C_AUTH,
    }
    assert set(attack_signature("replay", flags(False, True, False, False), False)) == {
        C_SEQ,
        C_TS,
    }
    assert set(attack_signature("replay", flags(False, True, False, False), True)) == {
        C_SEQ,
        C_TS,
        C_AUTH,
    }
    assert set(
        attack_signature("dispense_forgery", flags(True, False, False, False), False)
    ) == {W_ROBOT, W_INTAKE}
    assert set(
        attack_signature("dispense_forgery", flags(False, False, False, True), False)
    ) == {C_SEQ}
    assert set(
        attack_signature("presence_spoof", flags(True, True, True, False), False)
    ) == {W_IDENT}
    # plausible_values changes no evidence path: it only picks the range of the values
    for a, b in itertools.product((False, True), repeat=2):
        for subtype in ("replay", "dispense_forgery", "presence_spoof"):
            assert attack_signature(
                subtype, flags(a, b, False, a), b
            ) == attack_signature(subtype, flags(a, b, True, a), b)
    # the two injection subtypes are the two levels, nothing in between
    with pytest.raises(InjectionSpecError):
        attack_signature("injection_naive", INFORMED, False)
    with pytest.raises(InjectionSpecError):
        attack_signature("injection_informed", NAIVE, False)


def test_attack_signature_checks_its_arguments() -> None:
    for subtype in (
        "dispenser_physical_tamper",
        "timestamp_manipulation",
        "x",
        "",
        None,
        5,
    ):
        with pytest.raises(InjectionSpecError):
            attack_signature(subtype, NAIVE, False)  # type: ignore[arg-type]
    for bad in (None, 5, "naive", {"fresh_metadata": True}, object()):
        with pytest.raises(InjectionSpecError):
            attack_signature("replay", bad, False)  # type: ignore[arg-type]
    for bad in (None, 0, 1, "yes", np.bool_(True), 1.0):
        with pytest.raises(InjectionSpecError):
            attack_signature("replay", NAIVE, bad)  # type: ignore[arg-type]


def evidence_fields() -> set[str]:
    """The 20 dotted paths of EvidenceVector, read from the contract document."""
    text = INTERFACES.read_text(encoding="utf-8")
    block = text.split("## EvidenceVector", 1)[1].split("## Attribution", 1)[0]
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
                paths.add(f"{current}.{f.group(1)}")
    mapping = {v: k for k, v in top.items()}
    return {
        f"{mapping[p.split('.')[0]]}.{p.split('.')[1]}"
        for p in paths
        if p.split(".")[0] in mapping
    }


def test_signature_paths_are_contract_fields() -> None:
    fields = evidence_fields()
    assert len(fields) == 20  # the contract has twenty fields
    seen: set[str] = set()
    for subtype in C3_SUBTYPES:
        for combo in itertools.product((False, True), repeat=4):
            for auth in (False, True):
                caps = AttackerCapabilities(*combo)
                if subtype == "injection_naive" and caps != NAIVE:
                    continue
                if subtype == "injection_informed" and caps != INFORMED:
                    continue
                paths = attack_signature(subtype, caps, auth)
                assert set(paths) <= fields, (subtype, combo, set(paths) - fields)
                seen |= set(paths)
    assert seen == {X_DIFF, W_ROBOT, W_IDENT, W_INTAKE, C_AUTH, C_SEQ, C_TS}
    # the records carry exactly the paths of the function
    for s, caps in (
        (replay(*WINDOW, "informed"), INFORMED),
        (replay(*WINDOW, "naive"), NAIVE),
    ):
        assert run([s]).records[0].evidence_paths == attack_signature(
            "replay", caps, False
        )
    # the order of the paths is the order of the contract (group, then field)
    order = [
        X_DIFF, W_ROBOT, W_IDENT, W_INTAKE, C_AUTH, C_SEQ, C_TS,
    ]  # fmt: skip
    for subtype, level, auth in SIGNATURES:
        got = attack_signature(subtype, capabilities_of(level), auth)
        assert list(got) == sorted(got, key=order.index)


# ---------------------------------------------------------------------------
# 11. The latent day and the ground truth
# ---------------------------------------------------------------------------

ALL_C3 = [
    replay(DAY + 7 * HOUR, 2 * HOUR, "naive"),
    inj_naive(DAY + 11 * HOUR, 2 * HOUR),
    inj_informed(DAY + 15 * HOUR, 2 * HOUR),
    forge(DAY + 14 * HOUR, "informed"),
    spoof(SPOOF_AT, "informed", intake=True),
]


def test_c3_never_mutates_latent_day() -> None:
    payload: dict[str, Any] = {"note": "latent"}
    latent = LatentDay(
        PATIENT,
        1,
        0,
        tuple(S("bp", DAY + t, 130.0 + t // HOUR) for t in range(0, DAY, 10 * MIN)),
        (
            Event(
                EventKind.DISPENSE,
                DAY + DOSE_TICKS[0],
                DAY + DOSE_TICKS[0],
                "dispenser",
                payload,
                None,
            ),
        ),
    )
    before, snapshot = deep_state(latent), copy.deepcopy(latent)
    for specs in ([s] for s in ALL_C3):
        out = run(
            specs,
            stream_=NO_EVENING_DOSE,
            latent=latent,
            authenticating_devices=("cuff", "dispenser"),
        )
        assert deep_state(latent) == before and latent == snapshot
        finalize_observed(out.stream)
    out = run(ALL_C3, stream_=NO_EVENING_DOSE, latent=latent)
    assert all(r.realised for r in out.records)
    assert (
        deep_state(latent) == before
        and latent == snapshot
        and payload == {"note": "latent"}
    )
    # the attacks do not read it either: the result is the same without a latent day
    assert same(out, run(ALL_C3, stream_=NO_EVENING_DOSE))
    # a latent day of another patient, day or seed is refused: the pairing is checked
    for other in (
        dataclasses.replace(latent, patient_id="p0001"),
        dataclasses.replace(latent, day_index=2),
        dataclasses.replace(latent, seed=9),
    ):
        with pytest.raises(InjectionContextError):
            run([forge(FORGED_AT)], latent=other)


def test_the_c3_module_does_not_name_the_latent_day_or_the_truth_containers() -> None:
    tree = ast.parse((SRC / "inject_c3.py").read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.alias):
            names.add(node.name.split(".")[-1])
    assert (
        not {"LatentDay", "GroundTruthEvent", "BenchmarkDay", "TruthRecord", "latent"}
        & names
    )
    assert "latent_hold" not in names and "latent_sbp_mmhg" not in names
    text = (SRC / "inject_c3.py").read_text(encoding="utf-8")
    assert "np.random.seed" not in text and "random.random" not in text
    assert "np.random.default_rng" not in text  # every generator comes from rng.stream


def test_c3_subtypes_are_in_threat_model_vocabulary() -> None:
    text = THREAT_MODEL.read_text(encoding="utf-8")
    block = text.split("## Subtype vocabulary", 1)[1].split("\n## ", 1)[0]
    vocabulary = re.findall(r"^- ([a-z_]+)$", block, flags=re.MULTILINE)
    assert len(vocabulary) == len(set(vocabulary)) == 7
    assert set(C3_SUBTYPES) <= set(vocabulary)
    assert set(registered_subtypes(C3)) == set(C3_SUBTYPES)
    assert set(NOT_INJECTED_IN_V1) == set(vocabulary) - set(C3_SUBTYPES)
    assert set(NOT_INJECTED_IN_V1) == {
        "dispenser_physical_tamper",
        "timestamp_manipulation",
    }
    # the ground-truth subtype of every record is in the vocabulary
    for record in run(ALL_C3, stream_=NO_EVENING_DOSE).records:
        assert record.spec.subtype in vocabulary
    # the two subtypes that v1 does not inject are listed as such and never produced
    document = yaml.safe_load(INJECTIONS_FILE.read_text(encoding="utf-8"))
    listed = document["attacker"]["not_injected_in_v1"]
    assert set(listed) == set(NOT_INJECTED_IN_V1)
    for name, reason in listed.items():
        assert "not injected in v1" in reason and name in vocabulary
        with pytest.raises(InjectionSpecError):
            run([spec3(name, DAY + 9 * HOUR, HOUR, "naive")])
        with pytest.raises(InjectionSpecError):
            run([spec3(name, DAY + 9 * HOUR)])
    # the README of the workstream lists the same five
    readme = (
        ROOT / "docs" / "plan" / "workstreams" / "WS04-benchmark" / "README.md"
    ).read_text("utf-8")
    line = next(x for x in readme.splitlines() if x.startswith("- C3 (injected)"))
    assert set(re.findall(r"`([a-z_]+)`", line.split(":", 1)[1])) >= set(C3_SUBTYPES)
    # a C2 subtype is not a C3 subtype
    with pytest.raises(InjectionSpecError):
        run([spec3("stuck_at", DAY + 9 * HOUR, HOUR)])


def test_realised_flag_and_ground_truth_mapping() -> None:
    nothing = [
        replay(DAY + 18 * HOUR, HOUR, "informed"),  # the previous day sent nothing then
        inj_naive(DAY + 9 * HOUR, HOUR),  # no genuine message to replace
        spoof(DAY + 12 * HOUR + 30 * MIN),  # the robot is away
    ]
    out = run(nothing)
    assert [r.realised for r in out.records] == [False] * 3
    assert all(r.n_changed == 0 for r in out.records)
    assert same(out, run([]))
    assert ground_truth_events(out.records) == []
    assert [record_to_ground_truth(r) for r in out.records] == [None] * 3
    entries = injection_log(out.records)
    assert [e["realised"] for e in entries] == [False] * 3
    json.dumps(entries, allow_nan=False)  # JSON-native sidecar
    # the realised ones map to a C3 truth event
    realised = run(ALL_C3, stream_=NO_EVENING_DOSE)
    assert all(r.realised for r in realised.records)
    truths = ground_truth_events(realised.records)
    assert len(truths) == len(ALL_C3)
    for t in truths:
        assert t.cls is C3 and t.injected is True
        assert t.template_id is None and t.confounder_group is None
    ends = {t.subtype: t.end_ms for t in truths}
    assert ends["dispense_forgery"] is None and ends["presence_spoof"] is None
    assert (
        ends["replay"] == DAY + 9 * HOUR and ends["injection_naive"] == DAY + 13 * HOUR
    )
    assert [(t.onset_ms, t.subtype) for t in truths] == sorted(
        (t.onset_ms, t.subtype) for t in truths
    )
    # the confounder group of the spec travels to the truth event
    grouped = dataclasses.replace(
        forge(FORGED_AT, "informed"),
        confounder_group="nonresponse_vs_falsified_dispense",
    )
    (g,) = run([grouped]).records
    truth = record_to_ground_truth(g)
    assert (
        truth is not None
        and truth.confounder_group == "nonresponse_vs_falsified_dispense"
    )
    # one realised injection beside an unrealised one yields exactly one event
    mixed = run([spoof(DAY + 12 * HOUR + 30 * MIN), forge(FORGED_AT)])
    # the presence spoof ranks first: a forgery reads the witness the spoof wrote
    assert [r.spec.subtype for r in mixed.records] == [
        "presence_spoof",
        "dispense_forgery",
    ]
    assert [r.realised for r in mixed.records] == [False, True]
    assert len(ground_truth_events(mixed.records)) == 1


def test_records_are_json_native_and_describe_the_attack() -> None:
    out = run(ALL_C3, stream_=NO_EVENING_DOSE, authenticating_devices=("cuff",))
    for record in out.records:
        json.dumps(dict(record.details), allow_nan=False)
        d = record.details
        assert d["capabilities"] == dataclasses.asdict(
            capabilities_of(record.level or "")
        )
        assert set(d["capabilities"]) == set(FLAGS)
        assert d["gateway_policy"] == "flag"
        unit = {"dispense_forgery": "dispenser", "presence_spoof": "robot"}
        assert d["target"] == unit.get(record.spec.subtype, "cuff")
        assert isinstance(d["auth_deployed"], bool) and isinstance(
            d[EXPECTED_UNDETECTABLE], bool
        )
        assert record.level in ("naive", "informed")
        assert record.evidence_paths == attack_signature(
            record.spec.subtype, capabilities_of(record.level or ""), d["auth_deployed"]
        )
    levels = {r.spec.subtype: r.level for r in out.records}
    assert (
        levels["injection_naive"] == "naive"
        and levels["injection_informed"] == "informed"
    )
    assert levels["replay"] == "naive" and levels["presence_spoof"] == "informed"
    log = injection_log(out.records)
    assert {e["cls"] for e in log} == {"C3"}
    assert [e["level"] for e in log] == [r.level for r in out.records]


# ---------------------------------------------------------------------------
# 15. The stage of the attack: after the numbering and the link stage
# ---------------------------------------------------------------------------


def test_c3_step_runs_after_sequence_numbering_and_link_step() -> None:
    from ralmon.benchmark.inject_c2 import C2_SUBTYPES  # noqa: F401

    def dropout(onset: int, duration: int, target: str) -> InjectionSpec:
        return InjectionSpec(
            InjectedClass.C2,
            "ble_dropout",
            onset,
            duration,
            None,
            None,
            {"target": target},
        )

    # a dropout of the genuine cuff over the whole window and of the dispenser for the evening
    drops = [dropout(DAY, DAY, "cuff"), dropout(DAY + 19 * HOUR, 3 * HOUR, "dispenser")]
    out = run(
        [*drops, replay(*WINDOW, "naive"), forge(DAY + DOSE_TICKS[1] + 7, "naive")]
    )
    kinds = [r.spec.subtype for r in out.records]
    assert kinds[:2] == ["ble_dropout", "ble_dropout"]
    assert set(kinds[2:]) == {"replay", "dispense_forgery"}  # the attacks are last
    assert (
        injection_mod.STAGE_ATTACK == "attack"
        and injection_mod.PIPELINE_STAGES[-1] == "attack"
    )
    # the copies survive the dropout of the genuine device: the link stage ran before them
    assert values_of(out, "bp") == [128.0, 135.0, 120.0]
    assert [e.seq for e in events_of(out, EventKind.MEASUREMENT)] == [1, 2, 3]
    # a replayed duplicate number is not renumbered (the numbering ran before and not again)
    assert [s.seq for s in samples_of(out, "bp")] == [1, 2, 3]
    # the forged dispense inside the dropout of the dispenser is delivered, and numbered by the
    # attacker (one), not by the pipeline: the genuine 20:00 dispense of the window was lost
    forged = [
        e
        for e in events_of(out, EventKind.DISPENSE)
        if e.t_device_ms == DAY + DOSE_TICKS[1] + 7
    ]
    assert len(forged) == 1 and forged[0].seq == 1
    assert [
        r.realised
        for r in out.records
        if r.spec.subtype in ("replay", "dispense_forgery")
    ] == [True, True]
    # an informed forgery renumbers only the genuine events that remain
    informed = run(
        [
            dropout(DAY + 19 * HOUR, 3 * HOUR, "dispenser"),
            forge(DAY + DOSE_TICKS[1] + 7, "informed"),
        ]
    )
    assert [e.seq for e in events_of(informed, EventKind.DISPENSE)] == [3, 4]


def test_the_attack_stage_sees_the_genuine_stream_as_it_was_before_the_attacks() -> (
    None
):
    # an earlier naive window does not change what an informed attacker has captured
    early_naive = inj_naive(DAY + 6 * HOUR + 30 * MIN, HOUR)  # [06:30, 07:30)
    informed = inj_informed(DAY + 11 * HOUR, 6 * HOUR)
    alone = run([informed], stream_=TODAY_HOURLY, previous_day=PREV_HOURLY)
    both = run([early_naive, informed], stream_=TODAY_HOURLY, previous_day=PREV_HOURLY)
    assert early_naive.onset_ms < informed.onset_ms
    assert both.records[0].realised and both.records[1].realised
    window = lambda out: [
        s for s in samples_of(out, "bp") if s.t_rx_ms >= informed.onset_ms
    ]
    assert window(alone) == window(both)
    # the genuine view of the work is what the devices delivered before the attack stage
    work = injection_mod.InjectionWork(TODAY, ctx())
    before = work.genuine_view()
    assert before == (tuple(work.samples), tuple(work.events))
    work.freeze_genuine()
    work.samples.append(S("bp", DAY + 3, 1.0))
    assert work.genuine_view()[0] == before[0] and work.genuine_view()[0] != tuple(
        work.samples
    )


def test_overlapping_cuff_attacks_are_refused_and_touching_ones_are_not() -> None:
    a = replay(DAY + 7 * HOUR, 4 * HOUR, "informed")
    for other in (
        inj_naive(DAY + 10 * HOUR, 2 * HOUR),
        inj_informed(DAY + 10 * HOUR, 2 * HOUR),
        replay(DAY + 10 * HOUR, 2 * HOUR, "naive"),
    ):
        with pytest.raises(InjectionSpecError):
            run([a, other])
    out = run([a, inj_informed(DAY + 11 * HOUR, 2 * HOUR)])  # touching: allowed
    assert [r.spec.subtype for r in out.records] == ["replay", "injection_informed"]
    # the dispenser and the robot are other units: no overlap with the cuff
    run([a, forge(DAY + 9 * HOUR), spoof(DAY + DOSE_TICKS[1] + MIN)])
    with pytest.raises(InjectionSpecError):
        run(
            [forge(FORGED_AT), forge(FORGED_AT, "informed")]
        )  # two forgeries at one instant
    with pytest.raises(InjectionSpecError):
        run([spoof(SPOOF_AT), spoof(SPOOF_AT, "informed")])


# ---------------------------------------------------------------------------
# 16. Independent streams, determinism and the paired design
# ---------------------------------------------------------------------------

PAIRED: dict[str, InjectionSpec] = {
    "replay": replay(DAY + 7 * HOUR, 2 * HOUR, "naive"),
    "injection_naive": inj_naive(DAY + 9 * HOUR, 2 * HOUR),
    "injection_informed": inj_informed(DAY + 11 * HOUR, 2 * HOUR),
    "dispense_forgery": forge(DAY + 14 * HOUR, "naive"),
    "presence_spoof": spoof(DAY + 8 * HOUR + 5 * MIN, "naive"),
}
PAIRED_STREAM = fixture_stream(1, HOURLY_TICKS, [126.0 + k for k in range(12)])
PAIRED_PREV = PREV_HOURLY


def touched(subtype: str, key: Any) -> bool:
    """Whether an item key lies in the footprint of the PAIRED injection of ``subtype``."""
    kind, name, t = key[0], key[1], key[2]
    t_rx = key[3]
    cuff = name in CUFF_SIGNALS or name == "measurement"
    if subtype == "replay":
        return cuff and DAY + 7 * HOUR <= t_rx < DAY + 9 * HOUR
    if subtype == "injection_naive":
        return cuff and DAY + 9 * HOUR <= t_rx < DAY + 11 * HOUR
    if subtype == "injection_informed":
        return cuff and DAY + 11 * HOUR <= t_rx < DAY + 13 * HOUR
    if subtype == "dispense_forgery":
        return kind == "E" and name == "dispense"
    if subtype == "presence_spoof":
        return kind == "S" and name == "presence" and t == DAY + 8 * HOUR + 5 * MIN
    raise AssertionError(subtype)


@pytest.mark.parametrize("subtype", sorted(PAIRED))
def test_samples_outside_effect_are_bit_identical(subtype: str) -> None:
    others = [s for k, s in PAIRED.items() if k != subtype]
    kwargs = {"stream_": PAIRED_STREAM, "previous_day": PAIRED_PREV}
    without = run(others, **kwargs)
    with_one = run([*others, PAIRED[subtype]], **kwargs)
    # the dispenser's later genuine numbers move with an informed forgery only
    changed = diff_items(without.stream, with_one.stream)
    assert changed, subtype  # the injection did something
    assert all(touched(subtype, k) for k in changed), [
        k for k in changed if not touched(subtype, k)
    ]
    # every record of the others is identical, in value and in its draws
    mine = [r for r in with_one.records if r.spec != PAIRED[subtype]]
    assert mine == list(without.records)
    assert (
        with_one.stream.settings["next_cuff_seq"]
        == without.stream.settings["next_cuff_seq"]
    )
    # removing the injection again restores the stream exactly
    assert same(run(others, **kwargs), without)


NOTHING: dict[str, InjectionSpec] = {
    "replay": replay(DAY + 20 * HOUR, HOUR, "naive"),
    "injection_naive": inj_naive(DAY + 20 * HOUR, HOUR),
    "injection_informed": inj_informed(DAY + 20 * HOUR + 1, HOUR),
    "presence_spoof": spoof(DAY + 12 * HOUR + 30 * MIN),
}  # a forgery is always realised: there is none here


@pytest.mark.parametrize("subtype", sorted(NOTHING))
def test_an_unrealised_injection_shifts_no_draw_of_another(subtype: str) -> None:
    others = [s for k, s in PAIRED.items() if k != subtype]
    nothing = NOTHING[subtype]
    kwargs = {"stream_": PAIRED_STREAM, "previous_day": PAIRED_PREV}
    base = run(others, **kwargs)
    extra = run([*others, nothing], **kwargs)
    assert same(extra, base)
    assert [r for r in extra.records if r.spec != nothing] == list(base.records)
    assert not next(r for r in extra.records if r.spec == nothing).realised


def test_attack_streams_independent_and_deterministic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    s1, s2 = inj_naive(*WINDOW), inj_informed(DAY + 18 * HOUR, 2 * HOUR)
    calls: list[tuple[Any, ...]] = []
    real = injection_mod.stream

    def spy(*args: Any, **kwargs: Any) -> Any:
        calls.append(args)
        return real(*args, **kwargs)

    monkeypatch.setattr(injection_mod, "stream", spy)
    out = run([s1, s2], stream_=TODAY_HOURLY, previous_day=PREV_HOURLY, patient_index=3)
    assert calls and {c[3] for c in calls} == {StreamPurpose.INJECTION_C3}
    assert (0, 3, 1, StreamPurpose.INJECTION_C3, injection_sub_index(s1)) in calls
    monkeypatch.undo()
    # a replay, a forgery and a spoof draw nothing
    calls.clear()
    monkeypatch.setattr(injection_mod, "stream", spy)
    run([PAIRED["replay"], PAIRED["dispense_forgery"], PAIRED["presence_spoof"]])
    assert calls == []
    monkeypatch.undo()
    # the same seed repeats exactly; another patient or seed can differ
    again = run(
        [s1, s2], stream_=TODAY_HOURLY, previous_day=PREV_HOURLY, patient_index=3
    )
    assert again.stream == out.stream and again.records == out.records
    outs = {
        tuple(
            s.value
            for s in samples_of(
                run(
                    [s1],
                    stream_=TODAY_HOURLY,
                    previous_day=PREV_HOURLY,
                    patient_index=p,
                ),
                "bp",
            )
        )
        for p in range(6)
    }
    assert len(outs) > 1
    seeded = dataclasses.replace(TODAY_HOURLY, seed=5)
    assert samples_of(
        run(
            [s1], stream_=seeded, previous_day=dataclasses.replace(PREV_HOURLY, seed=5)
        ),
        "bp",
    ) != samples_of(run([s1], stream_=TODAY_HOURLY, previous_day=PREV_HOURLY), "bp")
    # the draw of one injection does not depend on the other one or on the order of the specs
    solo = run([s1], stream_=TODAY_HOURLY, previous_day=PREV_HOURLY, patient_index=3)
    assert [s for s in samples_of(solo, "bp") if s.t_rx_ms < DAY + 17 * HOUR] == [
        s for s in samples_of(out, "bp") if s.t_rx_ms < DAY + 17 * HOUR
    ]
    flipped = run(
        [s2, s1], stream_=TODAY_HOURLY, previous_day=PREV_HOURLY, patient_index=3
    )
    assert same(flipped, out)


def test_default_target_and_explicit_target_give_the_same_stream() -> None:
    bare = inj_naive(*WINDOW)
    explicit = spec3("injection_naive", WINDOW[0], WINDOW[1], target="cuff")
    assert injection_sub_index(bare) == injection_sub_index(explicit)
    a = run([bare], stream_=TODAY_HOURLY, previous_day=PREV_HOURLY)
    b = run([explicit], stream_=TODAY_HOURLY, previous_day=PREV_HOURLY)
    assert samples_of(a, "bp") == samples_of(b, "bp")
    assert injection_sub_index(forge(FORGED_AT)) == injection_sub_index(
        spec3("dispense_forgery", FORGED_AT, None, "naive", target="dispenser")
    )
    # the digest is the one of the documented recipe, in any process
    payload = json.dumps(
        ["injection", "C3", "injection_naive", "cuff", WINDOW[0], WINDOW[1]],
        separators=(",", ":"),
    )
    expected = int.from_bytes(hashlib.sha256(payload.encode()).digest()[:4], "big")
    assert injection_sub_index(bare) == expected
    # a replay naive and informed at one place are one injection for the draws
    assert injection_sub_index(replay(*WINDOW, "naive")) == injection_sub_index(
        replay(*WINDOW, "informed")
    )
    assert injection_sub_index(inj_naive(*WINDOW)) != injection_sub_index(
        inj_informed(*WINDOW)
    )


def test_output_does_not_depend_on_the_order_of_the_specs_or_on_hash_seeds() -> None:
    specs = ALL_C3
    base = run(specs, stream_=NO_EVENING_DOSE)
    for perm in itertools.islice(itertools.permutations(specs), 12):
        assert same(run(list(perm), stream_=NO_EVENING_DOSE), base)
        assert [r.spec for r in run(list(perm), stream_=NO_EVENING_DOSE).records] == [
            r.spec for r in base.records
        ]
    assert [s.subtype for s in canonical_order(specs)] == [
        r.spec.subtype for r in base.records
    ]
    # the canonical order puts every C3 attack after every C2 fault
    c2 = InjectionSpec(
        InjectedClass.C2, "cuff_silent_bias", DAY + 9 * HOUR, HOUR, 5.0, "mmHg", {}
    )
    assert next(s.cls for s in canonical_order([*specs, c2])) is InjectedClass.C2
    # one digest of the result in processes with other hash seeds
    script = textwrap.dedent(
        """
        import hashlib, json, sys
        sys.path.insert(0, %r)
        from tests.benchmark.test_inject_c3 import ALL_C3, NO_EVENING_DOSE, run
        out = run(ALL_C3, stream_=NO_EVENING_DOSE)
        text = repr((out.stream.samples, out.stream.events, out.records))
        print(hashlib.sha256(text.encode()).hexdigest())
        """
    ) % str(ROOT)
    digests = set()
    for hash_seed in ("0", "1", "12345"):
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, text=True, check=True, cwd=ROOT,
            env={**os.environ, "PYTHONHASHSEED": hash_seed},
        )  # fmt: skip
        digests.add(result.stdout.strip())
    assert len(digests) == 1 and len(next(iter(digests))) == 64
    assert (
        hashlib.sha256(
            repr((base.stream.samples, base.stream.events, base.records)).encode()
        ).hexdigest()
        in digests
    )


# ---------------------------------------------------------------------------
# Hand-over rules: duplicates, whole milliseconds, payload strings, the stream stays valid
# ---------------------------------------------------------------------------


def duplicates_at_one_instant(out: InjectionResult | ObservedStream) -> list[Any]:
    """Items that share (kind or signal, source, instant, seq): a monitor would read a replay."""
    s = out_stream(out)
    seen: dict[Any, int] = {}
    for e in s.events:
        if e.seq is not None:
            key = ("E", e.kind.value, e.source, e.t_rx_ms, e.seq)
            seen[key] = seen.get(key, 0) + 1
    for x in s.samples:
        if x.seq is not None:
            key = ("S", x.signal, x.t_rx_ms, x.seq)
            seen[key] = seen.get(key, 0) + 1
    return [k for k, n in seen.items() if n > 1]


def test_no_two_items_of_one_kind_share_a_number_at_one_instant() -> None:
    scenarios: list[tuple[list[InjectionSpec], dict[str, Any]]] = [
        ([replay(*WINDOW, "naive")], {}),
        ([replay(*WINDOW, "informed")], {}),
        ([inj_naive(*WINDOW)], {}),
        ([inj_informed(*WINDOW)], {}),
        ([forge(DAY + DOSE_TICKS[0], "naive")], {"dispenser_start": 1}),
        ([forge(DAY + DOSE_TICKS[0], "informed")], {}),
        (
            [
                forge(DAY + DOSE_TICKS[0], "naive"),
                forge(DAY + DOSE_TICKS[0] + 1, "naive"),
            ],
            {"dispenser_start": 1},
        ),
        (ALL_C3, {"authenticating_devices": ("cuff", "dispenser")}),
    ]
    for specs, kwargs in scenarios:
        out = run(specs, stream_=NO_EVENING_DOSE, **kwargs)
        assert all(r.realised for r in out.records), specs
        assert duplicates_at_one_instant(out) == [], specs
    # two cuff attempts at one instant (a delayed visit landing on another) stay distinct
    twin = fixture_stream(1, (8 * HOUR, 8 * HOUR), [131.0, 127.0])
    out = run([inj_naive(*WINDOW)], stream_=twin)
    assert len(events_of(out, EventKind.MEASUREMENT)) == 2
    assert duplicates_at_one_instant(out) == []
    out = run([inj_informed(*WINDOW)], stream_=twin)
    assert duplicates_at_one_instant(out) == []


def test_every_time_and_number_is_an_integer_and_the_stream_stays_valid() -> None:
    out = run(
        ALL_C3, stream_=NO_EVENING_DOSE, authenticating_devices=("cuff", "dispenser")
    )
    for item in (*out.stream.samples, *out.stream.events):
        assert type(item.t_device_ms) is int and type(item.t_rx_ms) is int
        assert item.seq is None or type(item.seq) is int
    day = finalize_observed(out.stream)
    validate_day(day)
    assert isinstance(day, ObservedDay)
    assert [s.t_rx_ms for s in day.samples] == sorted(s.t_rx_ms for s in day.samples)
    assert [e.t_rx_ms for e in day.events] == sorted(e.t_rx_ms for e in day.events)
    # the stale stamp of a naive replay is earlier than the day itself and is accepted
    stale = run([replay(*WINDOW, "naive")])
    assert min(s.t_device_ms for s in stale.stream.samples if s.signal == "bp") < DAY
    validate_day(finalize_observed(stale.stream))


def test_observed_payload_strings_never_name_the_ground_truth() -> None:
    forbidden = set(C3_SUBTYPES) | set(NOT_INJECTED_IN_V1) | set(CAPABILITY_SETS)
    forbidden |= set(c2_mod.C2_SUBTYPES) | {EXPECTED_UNDETECTABLE}
    out = run(
        ALL_C3, stream_=NO_EVENING_DOSE, authenticating_devices=("cuff", "dispenser")
    )
    strings: set[str] = set()
    for e in out.stream.events:
        strings |= {str(k) for k in e.payload} | {
            v for v in e.payload.values() if isinstance(v, str)
        }
        strings |= {e.source, e.kind.value}
    strings |= {s.signal for s in out.stream.samples}
    assert strings
    for text in strings:
        assert text not in forbidden, text
        assert not re.search(
            r"latent|ground_truth|injected|attack|forg|spoof|replay", text
        ), text
    assert {"gateway", "failed", "cuff", "dispenser"} <= strings
    day = finalize_observed(out.stream)
    text = repr(day)
    for needle in (
        "latent",
        "ground_truth",
        "injected",
        "expected_undetectable",
        "n_visits",
    ):
        assert needle not in text, needle


def test_finalize_observed_drops_every_generator_side_field_after_an_attack() -> None:
    out = run(ALL_C3, stream_=NO_EVENING_DOSE)
    day = finalize_observed(out.stream)
    assert {f.name for f in dataclasses.fields(day)} == {
        "patient_id", "day_index", "seed", "samples", "events", "care_plan_id",
    }  # fmt: skip
    latent_values = {m.latent_sbp_mmhg for m in out.stream.measurements}
    assert latent_values == {131.4375} and not latent_values & {
        s.value for s in day.samples
    }
    assert (
        out.stream.visits == NO_EVENING_DOSE.visits
    )  # the generator side is untouched


def test_written_observed_day_reads_back(tmp_path: Path) -> None:
    from ralmon.benchmark.trace import read_observed_day

    out = run(
        ALL_C3, stream_=NO_EVENING_DOSE, authenticating_devices=("cuff", "dispenser")
    )
    day = finalize_observed(out.stream)
    write_observed_day(tmp_path, day)
    assert read_observed_day(tmp_path, day.patient_id, day.day_index) == day


def test_the_attacks_compose_with_built_base_streams_of_two_days(
    tmp_path: Path,
) -> None:
    from ralmon.benchmark.measurement import (
        MeasurementDesign,
        NoJitter,
        build_observed_base,
    )
    from ralmon.benchmark.priors import DeviceErrorModel
    from ralmon.benchmark.schedule import Schedule
    from ralmon.benchmark.segments import InlineSegment, SegmentLibrary

    lib = SegmentLibrary.from_memory(
        [
            InlineSegment(
                "hr-1",
                "hr_clean",
                [70.0 + i % 30 for i in range(DAY // MIN)],
                MIN,
                "bpm",
            ),
            InlineSegment("sp-1", "spo2_clean", [95.0] * (DAY // MIN), MIN, "%"),
        ]
    )
    design = MeasurementDesign(INFLATION, 0, 0.0, DWELL, MIN, INFLATION)
    schedule = Schedule(
        dose_ticks_ms=(8 * HOUR, 20 * HOUR),
        measurement_ticks_ms=(9 * HOUR, 13 * HOUR, 21 * HOUR),
    )

    def build(day: int) -> tuple[ObservedStream, LatentDay]:
        samples = tuple(
            S("bp", day * DAY + t, 128.0 + day + t // (6 * HOUR))
            for t in range(0, DAY, MIN)
        )
        events = (
            E(EventKind.DISPENSE, day * DAY + 8 * HOUR, "dispenser"),
            E(EventKind.INTAKE, day * DAY + 8 * HOUR + SEC, "patient"),
            E(EventKind.DISPENSE, day * DAY + 20 * HOUR, "dispenser"),
        )
        latent = LatentDay(PATIENT, day, 0, samples, events)
        errors = DeviceErrorModel(0.0, 0.0, 0.0, 0.0)
        base = build_observed_base(
            latent, schedule, "plan-1", errors, design, NoJitter(), lib, 0, 0
        )
        return base, latent

    base0, _ = build(0)
    day0_out = apply_observation_injections(base0, [], InjectionContext(0, library=lib))
    base1, latent1 = build(1)
    settings = day0_out.stream.settings
    context = InjectionContext(
        0,
        library=lib,
        latent=latent1,
        previous_day=day0_out.stream,
        bp_bounds_mmhg=BOUNDS_BP,
        hr_bounds_bpm=BOUNDS_HR,
        cuff_start=settings["next_cuff_seq"],
        dispenser_start=settings["next_dispenser_seq"],
        authenticating_devices=("cuff", "dispenser"),
    )
    specs = [
        replay(DAY + 8 * HOUR + 30 * MIN, 2 * HOUR, "informed"),  # the 09:00 reading
        inj_naive(DAY + 12 * HOUR, 2 * HOUR),  # the 13:00 reading
        forge(DAY + 15 * HOUR, "informed"),
        spoof(DAY + 20 * HOUR + MIN, "informed", intake=True),
    ]
    before = copy.deepcopy(latent1)
    out = apply_observation_injections(base1, specs, context)
    assert latent1 == before
    assert [r.spec.subtype for r in out.records] == [
        "replay", "injection_naive", "presence_spoof", "dispense_forgery",
    ]  # fmt: skip
    assert all(r.realised for r in out.records)
    day = finalize_observed(out.stream)
    validate_day(day)
    # the replayed 09:00 reading is the one of the previous day, delivered one day later
    t = 9 * HOUR + INFLATION
    old = [
        s.value for s in day0_out.stream.samples if s.signal == "bp" and s.t_rx_ms == t
    ]
    new = [s.value for s in day.samples if s.signal == "bp" and s.t_rx_ms == DAY + t]
    assert (
        new == old
        and len(new) == 1
        and new != [s.value for s in base1.samples if s.signal == "bp"][:1]
    )
    # the informed replay continues the device's numbers (4 after the 3 of the previous day), the
    # naive forger counts from one, and the genuine 21:00 message keeps its own number
    cuff = [e.seq for e in day.events if e.kind is EventKind.MEASUREMENT]
    assert cuff == [settings["next_cuff_seq"], 1, settings["next_cuff_seq"] + 2]
    # the informed forgery took the number after the 08:00 dispense and moved the 20:00 one
    dispenses = [e.seq for e in day.events if e.kind is EventKind.DISPENSE]
    start = settings["next_dispenser_seq"]
    assert dispenses == [start, start + 1, start + 2]
    assert out.stream.settings["next_dispenser_seq"] == start + 3
    # the replay, the naive message and the forged dispense of authenticating devices failed
    assert len(gateway_events(out)) == 3
    # the spoofed intake is the only intake of the evening, inside the visit of the 20:00 dose
    evening = [
        e.t_device_ms
        for e in day.events
        if e.kind is EventKind.INTAKE and e.t_device_ms > DAY + 12 * HOUR
    ]
    assert evening == [DAY + 20 * HOUR + MIN]
    # the day is written and read back unchanged
    from ralmon.benchmark.trace import read_observed_day

    write_observed_day(tmp_path, day)
    assert read_observed_day(tmp_path, day.patient_id, day.day_index) == day


def test_the_input_streams_are_never_modified() -> None:
    before = copy.deepcopy((TODAY, PREV))
    run(ALL_C3, stream_=TODAY)
    run([replay(*WINDOW, "informed"), forge(FORGED_AT, "informed")])
    assert (TODAY, PREV) == before
    work = injection_mod.InjectionWork(TODAY, ctx())
    c3_mod.replay(work, [replay(*WINDOW, "naive")], ctx())
    assert TODAY == before[0] and work.samples != list(TODAY.samples)


# ---------------------------------------------------------------------------
# Gateway verification outcome (WS02-T03 gap G-4, provisional until ADR-035 is confirmed)
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


def test_gateway_verification_key_declared_in_vocab() -> None:
    assert vocab.KEY_VERIFICATION == "verification" and vocab.KEY_SUBJECT == "subject"
    assert vocab.VERIFICATION_FAILED == "failed" and vocab.SOURCE_GATEWAY == "gateway"
    assert vocab.VERIFICATIONS == ("failed",)
    # the names are those of the conventions table of evidence-channels.md
    rows = conventions_rows()
    assert {vocab.KEY_VERIFICATION, vocab.KEY_SUBJECT, vocab.KEY_ERROR_CODE} <= rows[
        "DEVICE_ERROR"
    ]
    text = EVIDENCE_DOC.read_text(encoding="utf-8")
    assert f"`{vocab.VERIFICATION_FAILED}`" in text
    assert vocab.KEY_VERIFICATION in vocab.PAYLOAD_KEYS[EventKind.DEVICE_ERROR]
    assert vocab.KEY_SUBJECT in vocab.PAYLOAD_KEYS[EventKind.DEVICE_ERROR]
    assert (
        vocab.KEY_VERIFICATION in vocab.ALL_PAYLOAD_KEYS
        and vocab.KEY_SUBJECT in vocab.ALL_PAYLOAD_KEYS
    )
    # every key constant is declared once (the T06 and T07 conformity rule)
    declared = {
        getattr(vocab, n)
        for n in dir(vocab)
        if n.startswith("KEY_") and isinstance(getattr(vocab, n), str)
    }
    assert declared == set(vocab.ALL_PAYLOAD_KEYS)
    # the outcome used by the replay, injection and forgery tests is exactly these constants
    out = run(
        [replay(*WINDOW, "informed"), forge(FORGED_AT, "naive")],
        authenticating_devices=("cuff", "dispenser"),
    )
    events = gateway_events(out)
    assert len(events) == 4
    for e in events:
        assert e.source == vocab.SOURCE_GATEWAY and e.seq is None
        assert dict(e.payload) == {
            vocab.KEY_VERIFICATION: vocab.VERIFICATION_FAILED,
            vocab.KEY_SUBJECT: e.payload[vocab.KEY_SUBJECT],
        }
        vocab.check_payload(e.kind, e.payload)
    assert {e.payload[vocab.KEY_SUBJECT] for e in events} == {"cuff", "dispenser"}


GATEWAY_BAD: list[Any] = [
    {"verification": "failed"},  # a failure needs its subject
    {"subject": "cuff"},
    {"verification": "passed", "subject": "cuff"},
    {"verification": 1, "subject": "cuff"},
    {"verification": "failed", "subject": ""},
    {"verification": "failed", "subject": " "},
    {"verification": "failed", "subject": 5},
    {"verification": "failed", "subject": "x" * 10_000},
    {
        "verification": "failed",
        "subject": "cuff",
        "error_code": "E1",
    },  # not both kinds of report
    {"verification": "failed", "subject": "cuff", "extra": 1},
]


@pytest.mark.parametrize("payload", GATEWAY_BAD)
def test_vocab_refuses_bad_verification_payloads(payload: Any) -> None:
    with pytest.raises(vocab.VocabularyError):
        vocab.check_payload(EventKind.DEVICE_ERROR, payload)


def test_vocab_still_accepts_the_device_error_of_a_device() -> None:
    vocab.check_payload(EventKind.DEVICE_ERROR, {"error_code": "CUFF_E01"})
    vocab.check_payload(
        EventKind.DEVICE_ERROR, {"verification": "failed", "subject": "cuff"}
    )
    assert vocab.REQUIRED_ALTERNATIVES[EventKind.DEVICE_ERROR] == (
        frozenset({vocab.KEY_ERROR_CODE}),
        frozenset({vocab.KEY_VERIFICATION, vocab.KEY_SUBJECT}),
    )
    assert vocab.SOURCE_GATEWAY not in {
        vocab.SOURCE_CUFF,
        vocab.SOURCE_DISPENSER,
        vocab.SOURCE_ECG,
    }
    assert vocab.BLE_DEVICES == (
        vocab.SOURCE_CUFF,
        vocab.SOURCE_DISPENSER,
        vocab.SOURCE_ECG,
        vocab.SOURCE_OXIMETER,
    )


# ---------------------------------------------------------------------------
# Machinery added for the attack stage (injection.py)
# ---------------------------------------------------------------------------


def good_apply(work: Any, specs: Any, context: Any) -> Any:
    return ()


def injector_kwargs(**overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "cls": C3, "subtype": "x_attack", "stage": "attack", "rank": 0, "shape": "point",
        "magnitude": "none", "magnitude_unit": None, "targets": ("cuff",),
        "target_required": False, "choices": {}, "signature": (), "apply": good_apply,
    }  # fmt: skip
    kwargs.update(overrides)
    return kwargs


def test_injector_levels_choices_and_overlap_group() -> None:
    plain = injection_mod.Injector(**injector_kwargs())
    assert (
        plain.levels == ()
        and plain.level_required is False
        and plain.overlap_group is None
    )
    full = injection_mod.Injector(
        **injector_kwargs(
            levels=("naive", "informed"),
            level_required=True,
            overlap_group="g",
            choices={"flag": (False, True)},
        )
    )
    assert full.levels == ("naive", "informed") and full.overlap_group == "g"
    for bad in (
        {"levels": ["naive"]}, {"levels": ("",)}, {"levels": (1,)}, {"levels": ("a", "a")},
        {"level_required": True}, {"level_required": 1}, {"levels": ("a",), "level_required": "yes"},
        {"overlap_group": ""}, {"overlap_group": 5}, {"choices": {"k": (1,)}},
        {"choices": {"k": (True, "x")}}, {"choices": {"k": (False, False)}},
    ):  # fmt: skip
        with pytest.raises(InjectionError):
            injection_mod.Injector(**injector_kwargs(**bad))


def test_level_and_boolean_choices_are_checked_strictly() -> None:
    # replay: the level is required and one of the two; the others are refused
    for bad in (None, "", "other", "Naive", " naive"):
        with pytest.raises(InjectionSpecError):
            run([spec3("replay", *WINDOW, bad)])
    with pytest.raises(InjectionSpecError):
        run([spec3("injection_naive", *WINDOW, "informed")])
    with pytest.raises(InjectionSpecError):
        run([spec3("injection_informed", *WINDOW, "naive")])
    run([spec3("injection_naive", *WINDOW, "naive")])
    run([spec3("injection_informed", *WINDOW, "informed")])
    # a boolean choice is a bool: an integer, a float or a string with the same meaning is not
    assert injection_mod.registered_subtypes(C3)[-1] == "dispense_forgery"  # runs last
    for ok in (True, False):
        run(
            [spec3("presence_spoof", SPOOF_AT, None, "informed", spoof_intake=ok)],
            stream_=NO_EVENING_DOSE,
        )
    # the target is one of the unit of the attack
    with pytest.raises(InjectionSpecError):
        run([spec3("replay", *WINDOW, "naive", target="dispenser")])
    with pytest.raises(InjectionSpecError):
        run([spec3("dispense_forgery", FORGED_AT, None, "naive", target="cuff")])
    with pytest.raises(InjectionSpecError):
        run([spec3("replay", *WINDOW, "naive", kind="dose")])  # no such param
    # a magnitude is not an attack parameter
    with pytest.raises(InjectionSpecError):
        run([InjectionSpec(C3, "replay", WINDOW[0], WINDOW[1], 5.0, "ms", {}, "naive")])
    # shapes: a window attack needs a duration, a point attack has none
    with pytest.raises(InjectionSpecError):
        run([spec3("replay", WINDOW[0], None, "naive")])
    with pytest.raises(InjectionSpecError):
        run([spec3("dispense_forgery", FORGED_AT, HOUR, "naive")])
    with pytest.raises(InjectionSpecError):
        run([replay(DAY + 20 * HOUR, 10 * HOUR)])  # beyond the end of the day


def test_context_fields_of_the_attack_stage_are_validated_and_normalised() -> None:
    c = ctx(
        bp_bounds_mmhg=[60, 200],
        hr_bounds_bpm=(50, 50.0),
        authenticating_devices=["dispenser", "cuff", "cuff"],
    )
    assert c.bp_bounds_mmhg == (60.0, 200.0) and c.hr_bounds_bpm == (50.0, 50.0)
    assert c.authenticating_devices == ("cuff", "dispenser")
    assert all(isinstance(x, float) for x in c.bp_bounds_mmhg or ())
    empty = InjectionContext(0)
    assert (empty.previous_day, empty.bp_bounds_mmhg, empty.hr_bounds_bpm) == (
        None,
        None,
        None,
    )
    assert empty.authenticating_devices == ()
    junk_bounds = [
        (1.0,), (1.0, 2.0, 3.0), (2.0, 1.0), (math.nan, 1.0), (1.0, math.inf), (-math.inf, 1.0), (True, 2.0),
        ("1", 2.0), (None, 2.0), 5, "ab", object(), iter([1.0, 2.0]), {1.0, 2.0}, (10**400, 10**401), np.array([1.0, 2.0, 3.0]),
    ]  # fmt: skip
    for bad in junk_bounds:
        for name in ("bp_bounds_mmhg", "hr_bounds_bpm"):
            with pytest.raises(InjectionContextError):
                InjectionContext(0, **{name: bad})
    for bad in (
        "cuff",
        b"cuff",
        5,
        [5],
        ["robot"],
        [""],
        [None],
        ["cuff", 1],
        object(),
        iter(["cuff"]),
        {"cuff": 1},
    ):
        with pytest.raises(InjectionContextError):
            InjectionContext(0, authenticating_devices=bad)
    for bad in (5, "x", object(), PREV.samples, True):
        with pytest.raises(InjectionContextError):
            InjectionContext(0, previous_day=bad)
    # boundaries of the keyword-only fields
    with pytest.raises(TypeError):
        InjectionContext(0, PREV)  # type: ignore[misc]


def test_the_context_fields_are_copied_not_shared() -> None:
    devices = ["cuff"]
    c = InjectionContext(0, authenticating_devices=devices)
    devices.append("dispenser")
    assert c.authenticating_devices == ("cuff",)
    bounds = [60.0, 200.0]
    c2 = InjectionContext(0, bp_bounds_mmhg=bounds)
    bounds[0] = -5.0
    assert c2.bp_bounds_mmhg == (60.0, 200.0)


def test_the_c2_injectors_are_unaffected_by_the_c3_machinery() -> None:
    assert set(registered_subtypes(InjectedClass.C2)) == set(c2_mod.C2_SUBTYPES)
    for subtype in c2_mod.C2_SUBTYPES:
        injector = injection_mod._REGISTRY[(InjectedClass.C2, subtype)]
        assert injector.levels == () and injector.overlap_group is None


# ---------------------------------------------------------------------------
# 17. The design file: parameters, levels, capability sets (state independent)
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


WINDOW_ATTACKS = ("replay", "injection_naive", "injection_informed")
POINT_ATTACKS = ("dispense_forgery", "presence_spoof")
HR_BOUND_ROWS = ("injection_naive_pulse_lower_bpm", "injection_naive_pulse_upper_bpm")


def check_c3_rows(path: Path) -> None:
    """Structure that holds whether the rows are awaiting a value or filled."""
    document = injection_document(path)
    section = document["injections"]["c3"]
    assert set(section) == set(C3_SUBTYPES)
    rows = {r.parameter: r for r in load_design_file(path).rows}
    referenced: set[str] = set()
    for subtype, entry in section.items():
        assert set(entry) >= {"family", "target", "onset", "duration", "magnitude"}, (
            subtype
        )
        assert entry["family"] in {"ble_attack", "perception_attack"}
        assert entry["target"] and all(isinstance(t, str) for t in entry["target"])
        assert isinstance(entry["onset"], str) and entry["onset"].strip()
        assert entry["magnitude"] is None, (
            subtype
        )  # no magnitude: values come from bounds or history
        if subtype in POINT_ATTACKS:
            assert entry["duration"] is None, subtype
            continue
        block = entry["duration"]
        assert block["key"] == "duration_ms" and block["unit"] == "ms", subtype
        levels = block["levels"]
        assert set(levels) == {"short", "medium", "long"}, subtype
        for name in levels.values():
            row = rows[name]
            referenced.add(name)
            assert (
                row.source_type in SOURCE_TYPES and row.source_type != "fixture_only"
            ), name
            assert row.source_ref and row.source_ref.strip(), name
            assert row.unit == "ms", name
            assert row.consumer_task == "WS04-T08", name
            if row.filled:
                assert (
                    row.value is not None and row.rationale and row.rationale.strip()
                ), name
            else:
                assert row.value is None, name
    assert numeric_leaves(section) == []  # the numbers are the rows of `parameters:`
    attacker = document["attacker"]
    assert numeric_leaves(attacker) == []  # booleans and names only
    for level, flags in attacker["capability_sets"].items():
        assert level in ("naive", "informed")
        assert set(flags) == {*FLAGS, "source_type", "source_ref"}
        assert all(isinstance(flags[f], bool) for f in FLAGS)
        assert flags["source_type"] in SOURCE_TYPES
        assert "docs/models/threat-model.md" in flags["source_ref"]
        assert "Knowledge levels" in flags["source_ref"]
    assert set(attacker["capability_sets"]) == {"naive", "informed"}
    for name in HR_BOUND_ROWS:  # the population heart-rate bounds wait for a human
        row = rows[name]
        assert row.consumer_task == "WS04-T08" and row.unit == "bpm"
        assert (
            row.source_type in SOURCE_TYPES
            and row.source_ref
            and row.source_ref.strip()
        )
        assert (row.value is None) is (not row.filled)
    bounds = attacker["bounds"]
    assert set(bounds) == {"bp", "hr"}
    registry = {
        e["name"] for e in yaml.safe_load(REGISTRY_FILE.read_text("utf-8"))["entries"]
    }
    assert (
        {bounds["bp"]["lower"], bounds["bp"]["upper"]}
        == {"bound_bp_lower", "bound_bp_upper"}
        <= registry
    )
    assert {bounds["hr"]["lower"], bounds["hr"]["upper"]} == set(HR_BOUND_ROWS)
    assert referenced


def test_c3_rows_have_provenance_and_levels() -> None:
    check_c3_rows(INJECTIONS_FILE)
    document = injection_document()
    assert document["injections"]["c2"]  # the C2 section is still there
    for level in ("naive", "informed"):
        assert (
            document["attacker"]["capability_sets"][level]["source_ref"].count(
                "threat-model.md"
            )
            == 1
        )
    # every C3 row of the file is a design choice with a rationale in its note
    rows = [
        r
        for r in load_design_file(INJECTIONS_FILE).rows
        if r.consumer_task == "WS04-T08"
    ]
    assert len(rows) == 3 * 3 + 2
    for row in rows:
        assert row.source_type == "design_choice" and row.note.strip(), row.parameter
        assert "No value has been chosen by an agent" in row.note, row.parameter
        assert row.status == "awaiting_human_value" or row.filled


def edited_injections(
    tmp_path: Path, fill: bool, mutate: Callable[[dict[str, Any]], None] | None = None
) -> Path:
    document = injection_document()
    for row in document["parameters"]:
        if row["consumer_task"] != "WS04-T08":
            continue
        if fill:
            row.update(
                value=60_000 if row["unit"] == "ms" else 60.0, status="filled",
                source_ref="FIXTURE-ONLY: exercises the filled state of the row",
                rationale="FIXTURE-ONLY: arithmetic", verified_by=None,
            )  # fmt: skip
        else:
            row.update(
                value=None,
                dist=None,
                status="awaiting_human_value",
                rationale=None,
                verified_by=None,
            )
    if mutate is not None:
        mutate(document)
    path = tmp_path / "injections.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def test_c3_rows_structure_holds_unfilled_and_filled(tmp_path: Path) -> None:
    check_c3_rows(edited_injections(tmp_path, fill=False))
    # a filled copy exercises the state of the rows once a human has supplied the values
    filled = edited_injections(tmp_path, fill=True)
    document = injection_document(filled)
    rows = {r.parameter: r for r in load_design_file(filled).rows}
    assert all(rows[n].filled for n in HR_BOUND_ROWS)
    assert document["attacker"]["bounds"]["hr"]["lower"] == HR_BOUND_ROWS[0]


def test_design_loader_reads_the_c3_section_in_both_states(tmp_path: Path) -> None:
    empty = load_injection_design(edited_injections(tmp_path, fill=False), section="c3")
    full = load_injection_design(edited_injections(tmp_path, fill=True), section="c3")
    assert set(empty) == set(full) == set(C3_SUBTYPES)
    for subtype in C3_SUBTYPES:
        a, b = empty[subtype], full[subtype]
        assert (a.family, a.targets, a.onset) == (b.family, b.targets, b.onset)
        assert a.magnitude is None and b.magnitude is None
        assert (a.duration is None) == (subtype in POINT_ATTACKS)
        if a.duration is not None and b.duration is not None:
            assert [lv.level for lv in a.duration.levels] == ["short", "medium", "long"]
            assert all(lv.value is None and not lv.filled for lv in a.duration.levels)
            assert all(lv.value == 60_000.0 and lv.filled for lv in b.duration.levels)
    assert empty["replay"].targets == ("cuff",) and empty[
        "dispense_forgery"
    ].targets == ("dispenser",)
    assert empty["presence_spoof"].targets == ("robot",)
    assert empty["presence_spoof"].family == "perception_attack"


def test_design_loader_rejects_a_broken_c3_structure(tmp_path: Path) -> None:
    def drop(name: str) -> Callable[[dict[str, Any]], None]:
        return lambda d: d["injections"]["c3"].pop(name)

    def add(d: dict[str, Any]) -> None:
        d["injections"]["c3"]["timestamp_manipulation"] = dict(
            d["injections"]["c3"]["replay"]
        )

    def number(d: dict[str, Any]) -> None:
        d["injections"]["c3"]["replay"]["duration"]["levels"]["short"] = 5

    def family(d: dict[str, Any]) -> None:
        d["injections"]["c3"]["replay"]["family"] = "device"

    def magnitude(d: dict[str, Any]) -> None:
        d["injections"]["c3"]["replay"]["magnitude"] = d["injections"]["c2"][
            "nav_delay"
        ]["magnitude"]

    def point_with_duration(d: dict[str, Any]) -> None:
        d["injections"]["c3"]["presence_spoof"]["duration"] = d["injections"]["c3"][
            "replay"
        ]["duration"]

    def wrong_target(d: dict[str, Any]) -> None:
        d["injections"]["c3"]["replay"]["target"] = ["dispenser"]

    def missing_row(d: dict[str, Any]) -> None:
        d["injections"]["c3"]["replay"]["duration"]["levels"]["short"] = "no_such_row"

    for _name, mutate in (
        ("drop", drop("replay")), ("add", add), ("number", number), ("family", family),
        ("magnitude", magnitude), ("point", point_with_duration), ("target", wrong_target),
        ("row", missing_row),
    ):  # fmt: skip
        path = edited_injections(tmp_path, fill=False, mutate=mutate)
        with pytest.raises(InjectionDesignError):
            load_injection_design(path, section="c3")
        load_injection_design(
            path, section="c2"
        )  # the C2 section is independent of the C3 one


def test_capability_loader_rejects_a_broken_attacker_section(tmp_path: Path) -> None:
    def flip(d: dict[str, Any]) -> None:
        d["attacker"]["capability_sets"]["naive"]["coherent_pulse"] = True

    def drop(d: dict[str, Any]) -> None:
        d["attacker"]["capability_sets"].pop("informed")

    def nonbool(d: dict[str, Any]) -> None:
        d["attacker"]["capability_sets"]["informed"]["fresh_metadata"] = 1

    def extra(d: dict[str, Any]) -> None:
        d["attacker"]["capability_sets"]["informed"]["secret_key"] = False

    def noattacker(d: dict[str, Any]) -> None:
        d.pop("attacker")

    path = edited_injections(tmp_path, fill=False, mutate=flip)
    assert (
        dict(load_capability_sets(path))["naive"] != NAIVE
    )  # a changed flag is read as written
    for mutate in (drop, nonbool, extra, noattacker):
        with pytest.raises(InjectionDesignError):
            load_capability_sets(edited_injections(tmp_path, fill=False, mutate=mutate))
    for bad in (None, 5, "", "/no/such/file.yaml", b"x", object(), tmp_path):
        with pytest.raises(InjectionDesignError):
            load_capability_sets(bad)  # type: ignore[arg-type]


def test_design_rows_are_in_the_provenance_table() -> None:
    table = (ROOT / "docs" / "benchmark" / "parameter-provenance.md").read_text("utf-8")
    rows = [r.parameter for r in load_design_file(INJECTIONS_FILE).rows]
    assert [
        r
        for r in rows
        if "replay" in r or "injection_naive" in r or "injection_informed" in r
    ]
    for name in rows:
        assert f"| {name} |" in table, name


def test_a_yaml_alias_bomb_in_the_attacker_section_is_refused_quickly(
    tmp_path: Path,
) -> None:
    lines = [
        "schema_version: '0.1.0'",
        "attacker:",
        "  capability_sets: &a0 {naive: [1]}",
    ]
    for i in range(1, 30):
        lines.append(f"  x{i}: &a{i} [*a{i - 1}, *a{i - 1}]")
    path = tmp_path / "bomb.yaml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(InjectionDesignError):
        load_capability_sets(path)


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


FORBIDDEN_PACKAGES = (
    "ralmon.spec", "ralmon.conformal", "ralmon.monitor", "ralmon.attribution",
    "ralmon.baselines", "ralmon.eval",
)  # fmt: skip
ALLOWED_C3_IMPORTS = (
    "ralmon.signals",
    "ralmon.benchmark.injection",
    "ralmon.benchmark.latent",
    "ralmon.benchmark.measurement",
    "ralmon.benchmark.trace",
    "ralmon.benchmark.vocab",
)
ALLOWED_THIRD_PARTY = {
    "__future__", "bisect", "collections", "dataclasses", "itertools", "math", "numbers", "os",
    "pathlib", "types", "typing", "numpy", "ralmon", "yaml",
}  # fmt: skip


def test_c3_module_layering_is_one_way_and_below_the_monitor() -> None:
    mods = imported_modules(SRC / "inject_c3.py")
    for forbidden in FORBIDDEN_PACKAGES:
        assert not any(m == forbidden or m.startswith(forbidden + ".") for m in mods)
    for m in mods:
        if m.startswith("ralmon") and m not in ("ralmon", "ralmon.benchmark"):
            assert any(m == a or m.startswith(a + ".") for a in ALLOWED_C3_IMPORTS), m
    top = {m.split(".")[0] for m in mods if not m.startswith(".")}
    assert top <= ALLOWED_THIRD_PARTY, top - ALLOWED_THIRD_PARTY
    assert not any(m.startswith(".") for m in mods)  # no relative import
    assert not {"time", "datetime", "random"} & top  # no wall clock, no global random
    # the lower modules do not know the injectors
    for name in ("measurement.py", "segments.py", "vocab.py", "rng.py", "trace.py"):
        assert not any("inject" in m for m in imported_modules(SRC / name)), name
    assert "ralmon.benchmark.inject_c3" in injection_mod._INJECTOR_MODULES


def test_new_names_are_not_exported_from_the_package_root() -> None:
    exported = set(benchmark_pkg.__all__)
    new = {
        "AttackerCapabilities",
        "attack_signature",
        "C3_SUBTYPES",
        "NAIVE",
        "INFORMED",
        "load_capability_sets",
    }
    assert not exported & new
    for name in new:
        assert not hasattr(benchmark_pkg, name), name


def test_the_module_lists_what_it_exports() -> None:
    declared = set(c3_mod.__all__)
    for name in declared:
        assert hasattr(c3_mod, name), name
    assert {
        "replay",
        "injection_naive",
        "injection_informed",
        "dispense_forgery",
        "presence_spoof",
    } <= declared
    assert {
        "attack_signature",
        "AttackerCapabilities",
        "EXPECTED_UNDETECTABLE",
        "NOT_INJECTED_IN_V1",
    } <= declared
    text = (SRC / "inject_c3.py").read_text(encoding="utf-8")
    assert text.count("expected_undetectable") >= 1  # the Done-when grep


# ---------------------------------------------------------------------------
# Extreme inputs: every public function and constructor raises the named error
# ---------------------------------------------------------------------------


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


def _junk() -> list[Any]:
    class Boom:
        def __getattr__(self, name: str) -> Any:
            raise RuntimeError("boom")

    return [
        None, True, False, 0, -1, 5, 2**70, 10**400, -(10**400), 1.5, math.nan,
        math.inf, -math.inf, "", " ", "x", "x" * 5000, b"x", [], [1], (1,), {},
        {"a": 1}, {1, 2}, object(), (lambda: 0), np.int64(3), np.float32(2.5),
        np.array([1, 2]), np.array(5), iter([1]), MappingProxy({"target": "cuff"}),
        Hostile(), Boom(), TODAY, PREV, ctx(), replay(*WINDOW), EventKind.DISPENSE,
        InjectedClass.C3, float("1e308"), -0.0, NAIVE, INFORMED,
    ]  # fmt: skip


def fuzz(
    fn: Callable[..., Any], args: Sequence[Any], kwargs: Mapping[str, Any] | None = None
) -> int:
    """Call ``fn`` with each argument replaced by each junk value; only the named error may escape."""
    kwargs = dict(kwargs or {})
    calls = 0
    for position in range(len(args)):
        for junk in _junk():
            trial = list(args)
            trial[position] = junk
            calls += 1
            try:
                fn(*trial, **kwargs)
            except InjectionError:
                pass
    for key in kwargs:
        for junk in _junk():
            trial_kwargs = dict(kwargs)
            trial_kwargs[key] = junk
            calls += 1
            try:
                fn(*args, **trial_kwargs)
            except InjectionError:
                pass
    return calls


def fresh_work(stream_: ObservedStream = TODAY) -> injection_mod.InjectionWork:
    return injection_mod.InjectionWork(stream_, ctx())


def test_every_public_function_raises_only_the_named_error_for_junk() -> None:
    total = 0
    total += fuzz(AttackerCapabilities, [True, False, True, False])
    total += fuzz(capabilities_of, ["naive"])
    total += fuzz(attack_signature, ["replay", NAIVE, False])
    total += fuzz(load_capability_sets, [INJECTIONS_FILE])
    total += fuzz(
        InjectionContext,
        [0],
        {
            "previous_day": PREV, "bp_bounds_mmhg": BOUNDS_BP, "hr_bounds_bpm": BOUNDS_HR,
            "authenticating_devices": ("cuff",), "cuff_start": 4, "dispenser_start": 3,
        },
    )  # fmt: skip
    total += fuzz(apply_observation_injections, [TODAY, [replay(*WINDOW)], ctx()])
    total += fuzz(injection_mod.Injector, list(injector_kwargs().values()))
    for name in C3_SUBTYPES:
        fn = getattr(c3_mod, name)
        s = {
            "replay": replay(*WINDOW, "informed"),
            "injection_naive": inj_naive(*WINDOW),
            "injection_informed": inj_informed(*WINDOW),
            "dispense_forgery": forge(FORGED_AT, "informed"),
            "presence_spoof": spoof(SPOOF_AT, "informed", intake=True),
        }[name]
        total += fuzz(fn, [fresh_work(), [s], ctx()])
    assert total > 2_000


class BadList(list):  # type: ignore[type-arg]
    """A list whose methods misbehave."""

    def __len__(self) -> int:
        raise RuntimeError("boom")

    def __iter__(self) -> Any:
        raise RuntimeError("boom")


class BadTuple(tuple):  # type: ignore[type-arg]
    def __len__(self) -> int:
        raise RuntimeError("boom")

    def __iter__(self) -> Any:
        raise RuntimeError("boom")

    def __getitem__(self, key: Any) -> Any:
        raise RuntimeError("boom")


class BadSet(set):  # type: ignore[type-arg]
    def __iter__(self) -> Any:
        raise RuntimeError("boom")


class BadFloat(float):
    def __float__(self) -> float:
        raise RuntimeError("boom")


class BadInt(int):
    def __int__(self) -> int:
        raise RuntimeError("boom")


def test_collections_that_misbehave_raise_the_named_error() -> None:
    for bad in (
        BadList([1.0, 2.0]),
        BadTuple((1.0, 2.0)),
        (BadFloat(1.0), 2.0),
        [1.0, BadFloat(2.0)],
    ):
        for name in ("bp_bounds_mmhg", "hr_bounds_bpm"):
            with pytest.raises(InjectionContextError):
                InjectionContext(0, **{name: bad})
    for bad in (BadList(["cuff"]), BadTuple(("cuff",)), BadSet({"cuff"})):
        with pytest.raises(InjectionContextError):
            InjectionContext(0, authenticating_devices=bad)
    for field in ("cuff_start", "dispenser_start", "patient_index"):
        with pytest.raises(InjectionContextError):
            InjectionContext(**{"patient_index": 0, field: BadInt(3)})
    assert InjectionContext(
        0, authenticating_devices={"cuff", "ecg"}
    ).authenticating_devices == ("cuff", "ecg")
    assert InjectionContext(
        0, authenticating_devices=frozenset({"dispenser"})
    ).authenticating_devices == ("dispenser",)


def test_new_public_functions_raise_only_the_named_error_for_junk() -> None:
    total = 0
    total += fuzz(injection_mod.check_previous_day, [fresh_work(), ctx()])
    total += fuzz(injection_mod.load_design_mapping, [INJECTIONS_FILE, "attacker"])
    total += fuzz(
        injection_mod.Injector,
        list(injector_kwargs().values()),
        {
            "levels": ("naive",),
            "level_required": False,
            "overlap_group": "g",
            "magnitude_optional": False,
        },
    )
    assert total > 500
    # the vocabulary raises its own error, never another one
    for junk in _junk():
        for payload in (
            {"verification": junk, "subject": "cuff"},
            {"verification": "failed", "subject": junk},
            {"verification": junk},
            {"subject": junk},
            {"error_code": "x", "verification": junk},
            junk,
        ):
            try:
                vocab.check_payload(EventKind.DEVICE_ERROR, payload)
            except vocab.VocabularyError:
                pass


def test_junk_in_the_attack_fields_of_the_context_raises_only_the_named_error() -> None:
    specs = list(ALL_C3)
    calls = 0
    for name in (
        "previous_day",
        "bp_bounds_mmhg",
        "hr_bounds_bpm",
        "authenticating_devices",
    ):
        for junk in _junk():
            calls += 1
            try:
                apply_observation_injections(
                    NO_EVENING_DOSE, specs, InjectionContext(0, **{name: junk})
                )
            except InjectionError:
                pass
    # a previous day with junk in every field of the stream and its items
    for field_ in dataclasses.fields(ObservedStream):
        for junk in _junk():
            calls += 1
            try:
                run(
                    [replay(*WINDOW, "informed")],
                    previous_day=dataclasses.replace(PREV, **{field_.name: junk}),
                )
            except InjectionError:
                pass
    for item, index, name in (
        (PREV.samples[3], 3, "samples"), (PREV.events[3], 3, "events"),
    ):  # fmt: skip
        for field_ in dataclasses.fields(item):
            for junk in _junk():
                calls += 1
                bad = dataclasses.replace(item, **{field_.name: junk})
                items = list(getattr(PREV, name))
                items[index] = bad
                try:
                    run(
                        [replay(*WINDOW, "informed")],
                        previous_day=dataclasses.replace(PREV, **{name: tuple(items)}),
                    )
                except InjectionError:
                    pass
    assert calls > 1_000


def test_junk_in_the_genuine_stream_raises_only_the_named_error() -> None:
    calls = 0
    for field_ in dataclasses.fields(ObservedStream):
        for junk in _junk():
            calls += 1
            try:
                run(
                    ALL_C3,
                    stream_=dataclasses.replace(NO_EVENING_DOSE, **{field_.name: junk}),
                )
            except InjectionError:
                pass
    sample, event = TODAY.samples[5], TODAY.events[5]
    for item, index, name in ((sample, 5, "samples"), (event, 5, "events")):
        for field_ in dataclasses.fields(item):
            for junk in _junk():
                calls += 1
                bad = dataclasses.replace(item, **{field_.name: junk})
                items = list(getattr(NO_EVENING_DOSE, name))
                items[index] = bad
                try:
                    run(
                        ALL_C3,
                        stream_=dataclasses.replace(
                            NO_EVENING_DOSE, **{name: tuple(items)}
                        ),
                    )
                except InjectionError:
                    pass
    assert calls > 900


def test_hostile_numbers_in_the_stream_cannot_break_an_attack() -> None:
    # values at the limits: a counter that cannot grow any more is refused, never wrapped
    for bad in (10**400, 2**63, -1, 0, True, 1.5, math.nan):
        with pytest.raises(InjectionContextError):
            ctx(cuff_start=bad)
    limit = injection_mod._INT64_MAX
    odd = dataclasses.replace(
        TODAY,
        events=tuple(
            by_rx(
                [
                    *TODAY.events,
                    E(EventKind.DISPENSE, DAY + 21 * HOUR, "dispenser", {}, limit),
                ]
            )
        ),
    )  # called directly: the pipeline would number the dispenses again
    with pytest.raises(InjectionContextError):  # the renumbering would pass the limit
        c3_mod.dispense_forgery(
            injection_mod.InjectionWork(odd, ctx()),
            [forge(FORGED_AT, "informed")],
            ctx(),
        )
    work = injection_mod.InjectionWork(odd, ctx())
    (record,) = c3_mod.dispense_forgery(work, [forge(FORGED_AT, "naive")], ctx())
    assert record.realised  # the naive forger does not renumber
    assert [e.seq for e in work.events if e.kind is EventKind.DISPENSE][-1] == 1
    negative = dataclasses.replace(
        TODAY,
        events=tuple(
            by_rx(
                [
                    *TODAY.events,
                    E(EventKind.DISPENSE, DAY + 21 * HOUR, "dispenser", {}, -5),
                ]
            )
        ),
    )
    out = run([forge(FORGED_AT, "informed")], stream_=negative)
    assert len(events_of(out, EventKind.DISPENSE)) == 4
    # mixed-type params of presence spoofs sort without a TypeError
    mixed = [
        spec3("presence_spoof", SPOOF_AT, None, "informed", spoof_intake=True),
        spec3("presence_spoof", SPOOF_AT + 1, None, "informed", spoof_intake=False),
        spec3("presence_spoof", SPOOF_AT + 2, None, "naive"),
    ]
    assert len(canonical_order(mixed)) == 3
    twin_a = spec3("presence_spoof", SPOOF_AT, None, "informed", spoof_intake=True)
    twin_b = dataclasses.replace(twin_a, params={"spoof_intake": 1})
    assert (
        len(canonical_order([twin_b, twin_a])) == 2
    )  # compared by text, never by value
    with pytest.raises(InjectionSpecError):
        run([twin_b])


def test_a_stream_without_a_sequence_scheme_gets_forged_messages_without_one() -> None:
    plain = dataclasses.replace(
        TODAY,
        samples=tuple(dataclasses.replace(s, seq=None) for s in TODAY.samples),
        events=tuple(dataclasses.replace(e, seq=None) for e in TODAY.events),
    )
    work = injection_mod.InjectionWork(plain, ctx())
    (record,) = c3_mod.injection_informed(work, [inj_informed(*WINDOW)], ctx())
    assert record.realised
    assert {s.seq for s in work.samples if s.signal == "bp"} == {None}
    assert {e.seq for e in work.events if e.kind is EventKind.MEASUREMENT} == {None}
    work2 = injection_mod.InjectionWork(plain, ctx())
    c3_mod.dispense_forgery(work2, [forge(FORGED_AT, "informed")], ctx())
    assert {e.seq for e in work2.events if e.kind is EventKind.DISPENSE} == {None}
    work3 = injection_mod.InjectionWork(plain, ctx())
    c3_mod.injection_naive(work3, [inj_naive(*WINDOW)], ctx())
    assert {e.seq for e in work3.events if e.kind is EventKind.MEASUREMENT} == {None}


def test_injector_functions_work_directly_and_check_their_arguments() -> None:
    work = fresh_work()
    (record,) = c3_mod.replay(work, [replay(*WINDOW, "informed")], ctx())
    assert record.realised and [s.value for s in work.samples if s.signal == "bp"] != []
    for bad_specs in (
        [inj_naive(*WINDOW)],  # another subtype
        [spec3("replay", WINDOW[0], None, "naive")],
        [replay(*WINDOW), replay(WINDOW[0] + HOUR, HOUR)],  # overlapping windows
        [replay(DAY + 20 * HOUR, 10 * HOUR)],
    ):
        with pytest.raises(InjectionSpecError):
            c3_mod.replay(fresh_work(), bad_specs, ctx())
    with pytest.raises(InjectionContextError):
        c3_mod.replay(object(), [replay(*WINDOW)], ctx())  # type: ignore[arg-type]
    with pytest.raises(InjectionContextError):
        c3_mod.dispense_forgery(fresh_work(), [forge(FORGED_AT)], object())  # type: ignore[arg-type]
    with pytest.raises(InjectionSpecError):
        c3_mod.dispense_forgery(fresh_work(), [spoof(SPOOF_AT)], ctx())


# ---------------------------------------------------------------------------
# Review round 1 (independent review of 2026-10-07): each test failed before its fix
# ---------------------------------------------------------------------------

DOSE_WINDOW_AT = (
    DAY + DOSE_TICKS[1] + 2 * MIN
)  # 20:02, inside the 20:00 visit [20:00, 20:10]


def record_of(out: InjectionResult, subtype: str) -> InjectionRecord:
    (record,) = [r for r in out.records if r.spec.subtype == subtype]
    return record


def test_the_forgery_tag_follows_what_the_stream_shows_not_the_capability_alone() -> (
    None
):
    # a robot is in the room at the dose tick and nobody takes the dose
    alone = record_of(
        run([forge(DOSE_WINDOW_AT, "informed")], stream_=NO_EVENING_DOSE),
        "dispense_forgery",
    )
    assert alone.realised
    assert set(alone.evidence_paths) == {W_ROBOT, W_INTAKE}
    assert alone.details[EXPECTED_UNDETECTABLE] is False
    naive = record_of(
        run([forge(DOSE_WINDOW_AT, "naive")], stream_=NO_EVENING_DOSE),
        "dispense_forgery",
    )
    assert set(naive.evidence_paths) == {W_ROBOT, W_INTAKE, C_SEQ}
    # the companion presence spoof with an intake hides it, whatever the order of the specs
    for order in (0, 1):
        pair = [
            forge(DOSE_WINDOW_AT, "informed"),
            spoof(SPOOF_AT, "informed", intake=True),
        ]
        out = run(pair[::-1] if order else pair, stream_=NO_EVENING_DOSE)
        hidden = record_of(out, "dispense_forgery")
        assert hidden.realised
        assert hidden.evidence_paths == ()
        assert hidden.details[EXPECTED_UNDETECTABLE] is True
    # a presence without an intake still leaves the intake unobserved
    out = run(
        [forge(DOSE_WINDOW_AT, "informed"), spoof(SPOOF_AT, "informed", intake=False)],
        stream_=NO_EVENING_DOSE,
    )
    only = record_of(out, "dispense_forgery")
    assert set(only.evidence_paths) == {W_ROBOT, W_INTAKE}
    assert only.details[EXPECTED_UNDETECTABLE] is False
    # a genuine intake in the dwell already makes the witness read True
    with_intake = record_of(
        run([forge(DOSE_WINDOW_AT, "informed")]), "dispense_forgery"
    )
    assert with_intake.realised and with_intake.evidence_paths == ()
    assert with_intake.details[EXPECTED_UNDETECTABLE] is True
    # the robot away: no witness reading to contradict, even for the naive forger
    away_naive = record_of(run([forge(FORGED_AT, "naive")]), "dispense_forgery")
    assert away_naive.evidence_paths == (C_SEQ,)
    away_informed = record_of(run([forge(FORGED_AT, "informed")]), "dispense_forgery")
    assert away_informed.evidence_paths == ()
    assert away_informed.details[EXPECTED_UNDETECTABLE] is True


def test_the_two_levels_of_a_standalone_forgery_do_not_differ_in_witness_evidence() -> (
    None
):
    # same stream, same instant: the witness evidence is what the stream holds, for both levels
    paths = {
        level: set(
            record_of(
                run([forge(DOSE_WINDOW_AT, level)], stream_=NO_EVENING_DOSE),
                "dispense_forgery",
            ).evidence_paths
        )
        & {W_ROBOT, W_INTAKE}
        for level in ("naive", "informed")
    }
    assert paths["naive"] == paths["informed"] == {W_ROBOT, W_INTAKE}


def test_forged_samples_keep_the_order_of_a_genuine_message() -> None:
    genuine = tuple(
        s.signal
        for s in run([]).stream.samples
        if s.signal in CUFF_SIGNALS and s.t_rx_ms == AT[0]
    )
    assert genuine == CUFF_SIGNALS
    for s in (inj_informed(*WINDOW), inj_naive(*WINDOW)):
        out = run([s])
        assert out.records[0].realised
        for t in AT:
            order = tuple(
                x.signal
                for x in out.stream.samples
                if x.signal in CUFF_SIGNALS and x.t_rx_ms == t
            )
            assert order == tuple(sorted(order, key=CUFF_SIGNALS.index)), (
                s.subtype,
                order,
            )
            if s.subtype == "injection_informed":
                assert order == CUFF_SIGNALS


def test_a_presence_spoof_where_the_robot_is_genuinely_present_changes_nothing() -> (
    None
):
    # the 08:00 visit arrives at 08:00 and already writes a presence sample of 1.0 there
    arrival = DAY + TICKS[0]
    base = run([])
    out = run([spoof(arrival, "naive")])
    (record,) = out.records
    assert not record.realised and record.n_changed == 0
    assert ground_truth_events(out.records) == []
    assert (
        out.stream.samples == base.stream.samples
        and out.stream.events == base.stream.events
    )
    # inside the dwell but away from the arrival the spoof is a new sample
    later = run([spoof(arrival + MIN, "naive")])
    assert later.records[0].realised and later.records[0].n_changed == 1


def test_a_str_subclass_is_a_valid_param_value_and_a_bool_still_is_not_an_int() -> None:
    # master accepted any str subclass; the strict check only needs to keep bool apart from int
    ok = run([forge(FORGED_AT, "naive", target=np.str_("dispenser"))])
    assert ok.records[0].realised
    assert run(
        [spoof(SPOOF_AT, "informed", intake=True)], stream_=NO_EVENING_DOSE
    ).records
    with pytest.raises(InjectionSpecError):
        run([spoof(SPOOF_AT, "informed", intake=1)], stream_=NO_EVENING_DOSE)  # type: ignore[arg-type]
    # an np.bool_ is already normalised to a bool by the spec: accepted before and after
    run([spoof(SPOOF_AT, "informed", intake=np.True_)], stream_=NO_EVENING_DOSE)  # type: ignore[arg-type]


def test_naive_attacks_of_one_day_keep_one_counter_of_their_own() -> None:
    start = c3_mod.FORGED_SEQ_START
    out = run([forge(DAY + h * HOUR, "naive") for h in (9, 10, 11)])
    forged = [
        e.seq
        for e in events_of(out, EventKind.DISPENSE)
        if e.t_device_ms in {DAY + h * HOUR for h in (9, 10, 11)}
    ]
    assert forged == [start, start + 1, start + 2]
    two = run(
        [inj_naive(DAY + 6 * HOUR, 3 * HOUR), inj_naive(DAY + 12 * HOUR, 3 * HOUR)],
        stream_=TODAY_HOURLY,
    )
    assert all(r.realised for r in two.records)
    numbers = [
        x.seq
        for x in samples_of(two, "bp")
        if DAY + 6 * HOUR <= x.t_rx_ms < DAY + 9 * HOUR
        or DAY + 12 * HOUR <= x.t_rx_ms < DAY + 15 * HOUR
    ]
    assert len(numbers) == 6 and len(set(numbers)) == 6


def test_the_draw_layout_of_an_injection_is_pinned() -> None:
    # column 0 is the pressure, column 1 the pulse of the naive forger: a change of the layout
    # would silently change every benchmark
    naive = run([inj_naive(*WINDOW)])
    assert [round(v, 6) for v in values_of(naive, "bp")] == [
        55.660779,
        145.927536,
        69.591823,
    ]
    assert [round(v, 6) for v in values_of(naive, "hr_pulse")] == [
        100.76902,
        146.923186,
        54.820218,
    ]
    informed = run([inj_informed(*WINDOW)])
    assert [round(v, 6) for v in values_of(informed, "bp")] == [
        121.908715,
        123.379501,
        121.253681,
    ]
