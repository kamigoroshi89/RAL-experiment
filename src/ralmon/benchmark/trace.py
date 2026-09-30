"""Trace schema, canonical JSON files and manifest (02-interfaces.md#trace-schema).

Layout of a benchmark directory (ADR-025)::

    manifest.json
    days/<patient_id>/<day_index>.json     ObservedDay only
    truth/<patient_id>/<day_index>.json    LatentDay, ground truth, sidecars

Files are canonical JSON: sorted keys, two-space indent, final newline, floats written
with ``repr``, no timestamp and no host field, so equal objects give equal bytes. A
detector run reads only ``days/``; nothing under ``truth/`` is needed to read a day.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TypeAlias

from ralmon.signals import Event, EventKind, Sample, TimeMs

__all__ = [
    "BenchmarkDay",
    "Event",
    "EventKind",
    "GroundTruthEvent",
    "InjectedClass",
    "JsonValue",
    "LatentDay",
    "Manifest",
    "ManifestError",
    "ObservedDay",
    "Sample",
    "SplitLeakError",
    "TraceError",
    "TraceOrderError",
    "TraceTypeError",
    "TruthRecord",
    "file_sha256",
    "observed_relpath",
    "read_benchmark_day",
    "read_manifest",
    "read_observed_day",
    "read_truth",
    "truth_relpath",
    "validate_day",
    "verify_manifest",
    "write_manifest",
    "write_observed_day",
    "write_truth",
]

JsonValue: TypeAlias = (
    "None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]"
)

MANIFEST_NAME = "manifest.json"
DAYS_DIR = "days"
TRUTH_DIR = "truth"
SPLITS = ("train", "calibration", "test")
FORBIDDEN_OBSERVED_KEY_PARTS = ("latent", "ground_truth")

OBSERVED_KEYS = frozenset(
    {"patient_id", "day_index", "seed", "samples", "events", "care_plan_id"}
)
LATENT_KEYS = frozenset({"patient_id", "day_index", "seed", "samples", "events"})
TRUTH_REQUIRED_KEYS = frozenset({"latent", "ground_truth"})
TRUTH_OPTIONAL_KEYS = frozenset({"injection_log", "behaviour_log"})
SAMPLE_KEYS = frozenset({"signal", "t_device_ms", "t_rx_ms", "value", "seq", "quality"})
EVENT_KEYS = frozenset({"kind", "t_device_ms", "t_rx_ms", "source", "payload", "seq"})
GROUND_TRUTH_KEYS = frozenset(
    {
        "cls",
        "subtype",
        "onset_ms",
        "end_ms",
        "injected",
        "template_id",
        "confounder_group",
    }
)
PROVENANCE_KEYS = frozenset({"name", "source_ref", "verified_by"})


class TraceError(ValueError):
    """Base class of the errors raised by this module."""


class TraceOrderError(TraceError):
    """Samples or events are not non-decreasing in ``t_rx_ms``."""


class TraceTypeError(TraceError):
    """A value has the wrong type, is out of range, or a file is malformed."""


class ManifestError(TraceError):
    """The manifest is incomplete, malformed, or does not match the files on disk."""


class SplitLeakError(ManifestError):
    """A patient is listed in more than one split (contract rule 2)."""


class InjectedClass(str, Enum):
    C1 = "C1"  # physiological / adherence deviation
    C2 = "C2"  # system or embodiment failure
    C3 = "C3"  # integrity violation


@dataclass(frozen=True, slots=True)
class GroundTruthEvent:
    cls: InjectedClass
    subtype: str  # e.g. "hypertensive_spike", "silent_bias", "replay" (open vocabulary, listed in WS04 README)
    onset_ms: TimeMs
    end_ms: TimeMs | None  # None for point events
    injected: bool  # False for C1 events that arise from the latent trace itself
    template_id: str | None  # violated template for C1; None otherwise
    confounder_group: (
        str | None
    )  # e.g. "double_take_vs_bounce"; used to score abstention


@dataclass(frozen=True, slots=True)
class ObservedDay:
    patient_id: str
    day_index: int
    seed: int
    samples: Sequence[Sample]  # sorted by t_rx_ms
    events: Sequence[Event]  # sorted by t_rx_ms
    care_plan_id: str


@dataclass(frozen=True, slots=True)
class LatentDay:
    patient_id: str
    day_index: int
    seed: int
    samples: Sequence[Sample]  # latent physiology and true intake, no corruption
    events: Sequence[Event]


@dataclass(frozen=True, slots=True)
class BenchmarkDay:
    observed: ObservedDay
    latent: LatentDay
    ground_truth: Sequence[GroundTruthEvent]


@dataclass(frozen=True, slots=True)
class TruthRecord:
    """Content of one truth file: the latent day, ground truth and the JSON sidecars."""

    latent: LatentDay
    ground_truth: Sequence[GroundTruthEvent]
    injection_log: JsonValue
    behaviour_log: JsonValue


@dataclass(frozen=True, slots=True)
class Manifest:
    """Benchmark-level record: provenance, seeds, splits and sha256 of every file.

    ``patients`` maps a patient id to ``split`` and ``cohort`` plus optional JSON-native
    keys (for example ``role``, ``pair``). ``files`` maps a path relative to the
    benchmark directory to its sha256. There is no wall-clock field.
    """

    benchmark_version: str
    generator_git_rev: str
    generation_seed: int
    prior_source_name: str
    prior_provenance: Sequence[
        Mapping[str, str | None]
    ]  # name, source_ref, verified_by
    fixture_only: bool
    n_unfilled: int
    n_unverified: int
    patients: Mapping[str, Mapping[str, JsonValue]]
    files: Mapping[str, str]
    event_counts: Mapping[
        str, int
    ]  # key "<class>/<subtype>", e.g. "C1/hypertensive_spike"
    settings: Mapping[str, JsonValue]


# ---------------------------------------------------------------------------
# Type checks
# ---------------------------------------------------------------------------


def _is_int(x: object) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _is_number(x: object) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _check_int(x: object, what: str) -> None:
    if not _is_int(x):
        raise TraceTypeError(f"{what} must be an int, got {x!r}")


def _check_time(x: object, what: str, *, allow_negative: bool = True) -> None:
    if not _is_int(x):
        raise TraceTypeError(f"{what} must be integer milliseconds, got {x!r}")
    assert isinstance(x, int)
    if not allow_negative and x < 0:
        raise TraceTypeError(f"{what} must be >= 0, got {x}")


def _check_finite(x: object, what: str) -> None:
    if not _is_number(x):
        raise TraceTypeError(f"{what} must be a number, got {x!r}")
    assert isinstance(x, (int, float))
    if isinstance(x, float) and not math.isfinite(x):
        raise TraceTypeError(f"{what} must be finite, got {x!r}")


def _check_str(x: object, what: str) -> None:
    if not isinstance(x, str):
        raise TraceTypeError(f"{what} must be a str, got {x!r}")


def _check_json(value: object, what: str, error: type[TraceError]) -> None:
    """Accept only JSON-native values: None, bool, int, finite float, str, list, dict."""
    if value is None or isinstance(value, (bool, int, str)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise error(f"{what}: non-finite float {value!r}")
        return
    if isinstance(value, list):
        for i, item in enumerate(value):
            _check_json(item, f"{what}[{i}]", error)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise error(f"{what}: key {key!r} is not a str")
            _check_json(item, f"{what}.{key}", error)
        return
    raise error(f"{what}: {type(value).__name__} is not JSON-native")


def _check_path_component(x: object, what: str) -> str:
    if not isinstance(x, str) or x in ("", ".", "..") or any(c in x for c in "/\\\0"):
        raise TraceTypeError(f"{what} is not usable as a directory name: {x!r}")
    return x


def _check_sample(s: Sample, what: str) -> None:
    _check_str(s.signal, f"{what}.signal")
    _check_time(s.t_device_ms, f"{what}.t_device_ms")
    _check_time(s.t_rx_ms, f"{what}.t_rx_ms", allow_negative=False)
    _check_finite(s.value, f"{what}.value")
    if s.seq is not None:
        _check_int(s.seq, f"{what}.seq")
    if s.quality is not None:
        _check_finite(s.quality, f"{what}.quality")


def _check_event(e: Event, what: str) -> None:
    if not isinstance(e.kind, EventKind):
        raise TraceTypeError(f"{what}.kind must be an EventKind, got {e.kind!r}")
    _check_time(e.t_device_ms, f"{what}.t_device_ms")
    _check_time(e.t_rx_ms, f"{what}.t_rx_ms", allow_negative=False)
    _check_str(e.source, f"{what}.source")
    if e.seq is not None:
        _check_int(e.seq, f"{what}.seq")
    if not isinstance(e.payload, Mapping):
        raise TraceTypeError(f"{what}.payload must be a mapping")
    for key, value in e.payload.items():
        _check_str(key, f"{what}.payload key")
        if isinstance(value, (bool, str)):
            continue
        _check_finite(value, f"{what}.payload[{key!r}]")


def _check_sorted(items: Sequence[Sample] | Sequence[Event], what: str) -> None:
    for i in range(1, len(items)):
        if items[i].t_rx_ms < items[i - 1].t_rx_ms:
            raise TraceOrderError(
                f"{what} not sorted by t_rx_ms at index {i}: "
                f"{items[i].t_rx_ms} < {items[i - 1].t_rx_ms}"
            )


def validate_day(day: ObservedDay | LatentDay) -> None:
    """Check integer times, finite values and non-decreasing ``t_rx_ms``.

    A negative ``t_device_ms`` is allowed (a stale replayed sample); a negative
    ``t_rx_ms`` is not. Equal ``t_rx_ms`` values are allowed.
    """
    _check_str(day.patient_id, "patient_id")
    _check_int(day.day_index, "day_index")
    _check_int(day.seed, "seed")
    if isinstance(day, ObservedDay):
        _check_str(day.care_plan_id, "care_plan_id")
    for i, sample in enumerate(day.samples):
        _check_sample(sample, f"samples[{i}]")
    for i, event in enumerate(day.events):
        _check_event(event, f"events[{i}]")
    _check_sorted(day.samples, "samples")
    _check_sorted(day.events, "events")


def _check_ground_truth(events: Sequence[GroundTruthEvent]) -> None:
    for i, g in enumerate(events):
        what = f"ground_truth[{i}]"
        if not isinstance(g.cls, InjectedClass):
            raise TraceTypeError(f"{what}.cls must be an InjectedClass, got {g.cls!r}")
        _check_str(g.subtype, f"{what}.subtype")
        _check_time(g.onset_ms, f"{what}.onset_ms")
        if g.end_ms is not None:
            _check_time(g.end_ms, f"{what}.end_ms")
        if not isinstance(g.injected, bool):
            raise TraceTypeError(f"{what}.injected must be a bool, got {g.injected!r}")
        for name in ("template_id", "confounder_group"):
            value = getattr(g, name)
            if value is not None:
                _check_str(value, f"{what}.{name}")


def _check_observed_payload_keys(day: ObservedDay) -> None:
    """Observed files must never carry a key that names latent or truth data."""
    for i, event in enumerate(day.events):
        for key in event.payload:
            if any(part in key for part in FORBIDDEN_OBSERVED_KEY_PARTS):
                raise TraceTypeError(
                    f"events[{i}].payload key {key!r} names latent or truth data"
                )


# ---------------------------------------------------------------------------
# Conversion to and from JSON-native objects (shared by observed and truth files)
# ---------------------------------------------------------------------------


def _sample_to_json(s: Sample) -> dict[str, JsonValue]:
    return {
        "signal": s.signal,
        "t_device_ms": s.t_device_ms,
        "t_rx_ms": s.t_rx_ms,
        "value": float(s.value),
        "seq": s.seq,
        "quality": None if s.quality is None else float(s.quality),
    }


def _event_to_json(e: Event) -> dict[str, JsonValue]:
    return {
        "kind": e.kind.value,
        "t_device_ms": e.t_device_ms,
        "t_rx_ms": e.t_rx_ms,
        "source": e.source,
        "payload": dict(e.payload),
        "seq": e.seq,
    }


def _ground_truth_to_json(g: GroundTruthEvent) -> dict[str, JsonValue]:
    return {
        "cls": g.cls.value,
        "subtype": g.subtype,
        "onset_ms": g.onset_ms,
        "end_ms": g.end_ms,
        "injected": g.injected,
        "template_id": g.template_id,
        "confounder_group": g.confounder_group,
    }


def _day_to_json(day: ObservedDay | LatentDay) -> dict[str, JsonValue]:
    obj: dict[str, JsonValue] = {
        "patient_id": day.patient_id,
        "day_index": day.day_index,
        "seed": day.seed,
        "samples": [_sample_to_json(s) for s in day.samples],
        "events": [_event_to_json(e) for e in day.events],
    }
    if isinstance(day, ObservedDay):
        obj["care_plan_id"] = day.care_plan_id
    return obj


def _expect_dict(obj: object, keys: frozenset[str], what: str) -> dict[str, JsonValue]:
    if not isinstance(obj, dict):
        raise TraceTypeError(f"{what} must be an object")
    if set(obj) != keys:
        missing = sorted(keys - set(obj))
        extra = sorted(set(obj) - keys)
        raise TraceTypeError(f"{what}: missing keys {missing}, unexpected keys {extra}")
    return obj


def _expect_list(obj: object, what: str) -> list[JsonValue]:
    if not isinstance(obj, list):
        raise TraceTypeError(f"{what} must be an array")
    return obj


def _float_of(x: object, what: str) -> float:
    _check_finite(x, what)
    assert isinstance(x, (int, float))
    return float(x)


def _opt_int(x: object, what: str) -> int | None:
    if x is None:
        return None
    _check_int(x, what)
    assert isinstance(x, int)
    return x


def _sample_from_json(obj: object, what: str) -> Sample:
    d = _expect_dict(obj, SAMPLE_KEYS, what)
    quality = d["quality"]
    signal = d["signal"]
    t_device, t_rx = d["t_device_ms"], d["t_rx_ms"]
    _check_str(signal, f"{what}.signal")
    _check_time(t_device, f"{what}.t_device_ms")
    _check_time(t_rx, f"{what}.t_rx_ms")
    assert (
        isinstance(signal, str) and isinstance(t_device, int) and isinstance(t_rx, int)
    )
    return Sample(
        signal,
        t_device,
        t_rx,
        _float_of(d["value"], f"{what}.value"),
        _opt_int(d["seq"], f"{what}.seq"),
        None if quality is None else _float_of(quality, f"{what}.quality"),
    )


def _event_from_json(obj: object, what: str) -> Event:
    d = _expect_dict(obj, EVENT_KEYS, what)
    kind, source, payload = d["kind"], d["source"], d["payload"]
    t_device, t_rx = d["t_device_ms"], d["t_rx_ms"]
    try:
        event_kind = EventKind(kind)
    except ValueError:
        raise TraceTypeError(f"{what}.kind: unknown event kind {kind!r}") from None
    _check_str(source, f"{what}.source")
    _check_time(t_device, f"{what}.t_device_ms")
    _check_time(t_rx, f"{what}.t_rx_ms")
    if not isinstance(payload, dict):
        raise TraceTypeError(f"{what}.payload must be an object")
    clean: dict[str, float | int | str | bool] = {}
    for key, value in payload.items():
        if not isinstance(value, (bool, int, float, str)):
            raise TraceTypeError(
                f"{what}.payload[{key!r}] must be bool, int, float or str"
            )
        clean[key] = value
    assert (
        isinstance(source, str) and isinstance(t_device, int) and isinstance(t_rx, int)
    )
    return Event(
        event_kind, t_device, t_rx, source, clean, _opt_int(d["seq"], f"{what}.seq")
    )


def _series_from_json(
    d: dict[str, JsonValue], what: str
) -> tuple[tuple[Sample, ...], tuple[Event, ...]]:
    samples = tuple(
        _sample_from_json(s, f"{what}.samples[{i}]")
        for i, s in enumerate(_expect_list(d["samples"], f"{what}.samples"))
    )
    events = tuple(
        _event_from_json(e, f"{what}.events[{i}]")
        for i, e in enumerate(_expect_list(d["events"], f"{what}.events"))
    )
    return samples, events


def _header_from_json(d: dict[str, JsonValue], what: str) -> tuple[str, int, int]:
    patient_id, day_index, seed = d["patient_id"], d["day_index"], d["seed"]
    _check_str(patient_id, f"{what}.patient_id")
    _check_int(day_index, f"{what}.day_index")
    _check_int(seed, f"{what}.seed")
    assert isinstance(patient_id, str)
    assert isinstance(day_index, int) and isinstance(seed, int)
    return patient_id, day_index, seed


def _observed_from_json(obj: object) -> ObservedDay:
    d = _expect_dict(obj, OBSERVED_KEYS, "observed day")
    patient_id, day_index, seed = _header_from_json(d, "observed day")
    samples, events = _series_from_json(d, "observed day")
    care_plan_id = d["care_plan_id"]
    _check_str(care_plan_id, "care_plan_id")
    assert isinstance(care_plan_id, str)
    return ObservedDay(patient_id, day_index, seed, samples, events, care_plan_id)


def _latent_from_json(obj: object) -> LatentDay:
    d = _expect_dict(obj, LATENT_KEYS, "latent day")
    patient_id, day_index, seed = _header_from_json(d, "latent day")
    samples, events = _series_from_json(d, "latent day")
    return LatentDay(patient_id, day_index, seed, samples, events)


def _ground_truth_from_json(obj: object, what: str) -> GroundTruthEvent:
    d = _expect_dict(obj, GROUND_TRUTH_KEYS, what)
    try:
        cls = InjectedClass(d["cls"])
    except ValueError:
        raise TraceTypeError(f"{what}.cls: unknown class {d['cls']!r}") from None
    subtype, onset = d["subtype"], d["onset_ms"]
    injected = d["injected"]
    _check_str(subtype, f"{what}.subtype")
    _check_time(onset, f"{what}.onset_ms")
    if not isinstance(injected, bool):
        raise TraceTypeError(f"{what}.injected must be a bool")
    end_ms = d["end_ms"]
    if end_ms is not None:
        _check_time(end_ms, f"{what}.end_ms")
    strings: list[str | None] = []
    for name in ("template_id", "confounder_group"):
        value = d[name]
        if value is not None:
            _check_str(value, f"{what}.{name}")
        assert value is None or isinstance(value, str)
        strings.append(value)
    assert isinstance(subtype, str) and isinstance(onset, int)
    assert end_ms is None or isinstance(end_ms, int)
    return GroundTruthEvent(
        cls, subtype, onset, end_ms, injected, strings[0], strings[1]
    )


# ---------------------------------------------------------------------------
# Canonical JSON files
# ---------------------------------------------------------------------------


def _dump(obj: object) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=2, allow_nan=False) + "\n").encode(
        "utf-8"
    )


def _write(path: Path, obj: object) -> Path:
    data = _dump(obj)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _reject_constant(name: str) -> object:
    raise TraceTypeError(f"non-finite constant {name} in JSON")


def _load(path: Path) -> tuple[object, list[tuple[str, object, object]]]:
    """Parse a file; also return the duplicate keys, which plain ``json`` drops silently."""
    duplicates: list[tuple[str, object, object]] = []

    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        out: dict[str, object] = {}
        for key, value in items:
            if key in out:
                duplicates.append((key, out[key], value))
            out[key] = value
        return out

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise TraceTypeError(f"cannot read {path}: {exc}") from exc
    try:
        obj = json.loads(text, object_pairs_hook=pairs, parse_constant=_reject_constant)
    except json.JSONDecodeError as exc:
        raise TraceTypeError(f"{path} is not valid JSON: {exc}") from exc
    return obj, duplicates


def _load_strict(path: Path) -> object:
    obj, duplicates = _load(path)
    if duplicates:
        raise TraceTypeError(f"{path}: duplicate key {duplicates[0][0]!r}")
    return obj


def observed_relpath(patient_id: str, day_index: int) -> str:
    """Path of an observed day relative to the benchmark directory (posix form)."""
    return (
        f"{DAYS_DIR}/{_check_path_component(patient_id, 'patient_id')}/{day_index}.json"
    )


def truth_relpath(patient_id: str, day_index: int) -> str:
    """Path of a truth file relative to the benchmark directory (posix form)."""
    return f"{TRUTH_DIR}/{_check_path_component(patient_id, 'patient_id')}/{day_index}.json"


def write_observed_day(root: Path, day: ObservedDay) -> Path:
    """Validate and write ``days/<patient_id>/<day_index>.json``; return the path."""
    validate_day(day)
    _check_observed_payload_keys(day)
    return _write(
        root / observed_relpath(day.patient_id, day.day_index), _day_to_json(day)
    )


def read_observed_day(root: Path, patient_id: str, day_index: int) -> ObservedDay:
    """Read one observed day; never touches ``truth/``."""
    day = _observed_from_json(
        _load_strict(root / observed_relpath(patient_id, day_index))
    )
    if (day.patient_id, day.day_index) != (patient_id, day_index):
        raise TraceTypeError(
            f"file for {patient_id}/{day_index} holds {day.patient_id}/{day.day_index}"
        )
    validate_day(day)
    return day


def write_truth(
    root: Path,
    latent: LatentDay,
    ground_truth: Sequence[GroundTruthEvent],
    injection_log: JsonValue = None,
    behaviour_log: JsonValue = None,
) -> Path:
    """Validate and write ``truth/<patient_id>/<day_index>.json``.

    The sidecars ``injection_log`` and ``behaviour_log`` are stored as given after a
    JSON-native check; ``None`` omits the key.
    """
    validate_day(latent)
    _check_ground_truth(ground_truth)
    obj: dict[str, JsonValue] = {
        "latent": _day_to_json(latent),
        "ground_truth": [_ground_truth_to_json(g) for g in ground_truth],
    }
    for name, sidecar in (
        ("injection_log", injection_log),
        ("behaviour_log", behaviour_log),
    ):
        if sidecar is not None:
            _check_json(sidecar, name, TraceTypeError)
            obj[name] = sidecar
    return _write(root / truth_relpath(latent.patient_id, latent.day_index), obj)


def read_truth(root: Path, patient_id: str, day_index: int) -> TruthRecord:
    """Read one truth file. Only evaluation code may call this, never a detector."""
    obj = _load_strict(root / truth_relpath(patient_id, day_index))
    if not isinstance(obj, dict):
        raise TraceTypeError("truth file must be an object")
    keys = set(obj)
    if (
        not TRUTH_REQUIRED_KEYS <= keys
        or not keys <= TRUTH_REQUIRED_KEYS | TRUTH_OPTIONAL_KEYS
    ):
        raise TraceTypeError(f"truth file has unexpected keys {sorted(keys)}")
    latent = _latent_from_json(obj["latent"])
    if (latent.patient_id, latent.day_index) != (patient_id, day_index):
        raise TraceTypeError(
            f"file for {patient_id}/{day_index} holds {latent.patient_id}/{latent.day_index}"
        )
    validate_day(latent)
    ground_truth = tuple(
        _ground_truth_from_json(g, f"ground_truth[{i}]")
        for i, g in enumerate(_expect_list(obj["ground_truth"], "ground_truth"))
    )
    _check_ground_truth(ground_truth)
    return TruthRecord(
        latent, ground_truth, obj.get("injection_log"), obj.get("behaviour_log")
    )


def read_benchmark_day(root: Path, patient_id: str, day_index: int) -> BenchmarkDay:
    """Recombine the observed file and the truth file into a ``BenchmarkDay``."""
    observed = read_observed_day(root, patient_id, day_index)
    truth = read_truth(root, patient_id, day_index)
    return BenchmarkDay(observed, truth.latent, truth.ground_truth)


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

MANIFEST_KEYS = (
    "benchmark_version",
    "generator_git_rev",
    "generation_seed",
    "prior_source_name",
    "prior_provenance",
    "fixture_only",
    "n_unfilled",
    "n_unverified",
    "patients",
    "files",
    "event_counts",
    "settings",
)


def file_sha256(path: Path) -> str:
    """Hex sha256 of a file's bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest_check(ok: bool, message: str) -> None:
    if not ok:
        raise ManifestError(message)


def _validate_patient(patient_id: object, entry: object) -> None:
    _manifest_check(isinstance(patient_id, str) and patient_id != "", "patient id")
    _manifest_check(
        isinstance(entry, Mapping), f"patients[{patient_id!r}] not a mapping"
    )
    assert isinstance(entry, Mapping)
    split = entry.get("split")
    if isinstance(split, (list, tuple, set, frozenset)):
        raise SplitLeakError(f"patient {patient_id!r} listed in splits {sorted(split)}")
    _manifest_check(
        split in SPLITS, f"patients[{patient_id!r}].split must be one of {SPLITS}"
    )
    _manifest_check(
        isinstance(entry.get("cohort"), str), f"patients[{patient_id!r}].cohort missing"
    )
    _check_json(dict(entry), f"patients[{patient_id!r}]", ManifestError)


def validate_manifest(m: Manifest) -> None:
    """Check types, JSON-nativeness and the split rule; raise ``ManifestError``."""
    for name in ("benchmark_version", "generator_git_rev", "prior_source_name"):
        _manifest_check(isinstance(getattr(m, name), str), f"{name} must be a str")
    _manifest_check(_is_int(m.generation_seed), "generation_seed must be an int")
    _manifest_check(isinstance(m.fixture_only, bool), "fixture_only must be a bool")
    for name in ("n_unfilled", "n_unverified"):
        value = getattr(m, name)
        _manifest_check(_is_int(value) and value >= 0, f"{name} must be an int >= 0")
    for i, record in enumerate(m.prior_provenance):
        _manifest_check(
            isinstance(record, Mapping) and set(record) == PROVENANCE_KEYS,
            f"prior_provenance[{i}] must have exactly {sorted(PROVENANCE_KEYS)}",
        )
        _manifest_check(
            isinstance(record["name"], str) and isinstance(record["source_ref"], str),
            f"prior_provenance[{i}]: name and source_ref must be str",
        )
        _manifest_check(
            record["verified_by"] is None or isinstance(record["verified_by"], str),
            f"prior_provenance[{i}].verified_by must be str or None",
        )
    for patient_id, entry in m.patients.items():
        _validate_patient(patient_id, entry)
    for path, digest in m.files.items():
        parts = path.split("/") if isinstance(path, str) else []
        _manifest_check(
            bool(parts) and all(p not in ("", ".", "..") for p in parts),
            f"files: unusable relative path {path!r}",
        )
        _manifest_check(
            isinstance(digest, str)
            and len(digest) == 64
            and all(c in "0123456789abcdef" for c in digest),
            f"files[{path!r}] is not a lower-case sha256 hex digest",
        )
    for key, count in m.event_counts.items():
        _manifest_check(
            isinstance(key, str) and _is_int(count) and count >= 0,
            f"event_counts[{key!r}] must map to an int >= 0",
        )
    _check_json(dict(m.settings), "settings", ManifestError)


def _manifest_to_json(m: Manifest) -> dict[str, JsonValue]:
    return {
        "benchmark_version": m.benchmark_version,
        "generator_git_rev": m.generator_git_rev,
        "generation_seed": m.generation_seed,
        "prior_source_name": m.prior_source_name,
        "prior_provenance": [dict(r) for r in m.prior_provenance],
        "fixture_only": m.fixture_only,
        "n_unfilled": m.n_unfilled,
        "n_unverified": m.n_unverified,
        "patients": {p: dict(e) for p, e in m.patients.items()},
        "files": dict(m.files),
        "event_counts": dict(m.event_counts),
        "settings": dict(m.settings),
    }


def write_manifest(root: Path, manifest: Manifest) -> Path:
    """Validate and write ``manifest.json``; return the path."""
    validate_manifest(manifest)
    return _write(root / MANIFEST_NAME, _manifest_to_json(manifest))


def _check_duplicate_patients(
    duplicates: list[tuple[str, object, object]], obj: dict[str, object]
) -> None:
    patients = obj.get("patients")
    for key, first, second in duplicates:
        if isinstance(patients, dict) and key in patients:
            if first != second:
                raise SplitLeakError(
                    f"patient {key!r} listed twice with different entries"
                )
            raise ManifestError(f"patient {key!r} listed twice")
        raise ManifestError(f"duplicate key {key!r}")


def read_manifest(root: Path) -> Manifest:
    """Read and validate ``manifest.json``."""
    try:
        obj, duplicates = _load(root / MANIFEST_NAME)
    except TraceTypeError as exc:
        raise ManifestError(str(exc)) from exc
    _manifest_check(isinstance(obj, dict), "manifest must be an object")
    assert isinstance(obj, dict)
    _check_duplicate_patients(duplicates, obj)
    missing = [k for k in MANIFEST_KEYS if k not in obj]
    _manifest_check(not missing, f"manifest is missing keys {missing}")
    extra = sorted(set(obj) - set(MANIFEST_KEYS))
    _manifest_check(not extra, f"manifest has unexpected keys {extra}")
    manifest = Manifest(
        benchmark_version=obj["benchmark_version"],
        generator_git_rev=obj["generator_git_rev"],
        generation_seed=obj["generation_seed"],
        prior_source_name=obj["prior_source_name"],
        prior_provenance=tuple(obj["prior_provenance"]),
        fixture_only=obj["fixture_only"],
        n_unfilled=obj["n_unfilled"],
        n_unverified=obj["n_unverified"],
        patients=obj["patients"],
        files=obj["files"],
        event_counts=obj["event_counts"],
        settings=obj["settings"],
    )
    _validate_container_types(manifest)
    validate_manifest(manifest)
    return manifest


def _validate_container_types(m: Manifest) -> None:
    """Guard the containers before ``validate_manifest`` iterates over them."""
    for name in ("patients", "files", "event_counts", "settings"):
        _manifest_check(isinstance(getattr(m, name), dict), f"{name} must be an object")
    _manifest_check(
        isinstance(m.prior_provenance, Sequence), "prior_provenance must be an array"
    )


def verify_manifest(root: Path) -> None:
    """Check that every file listed in the manifest exists and has the recorded sha256."""
    manifest = read_manifest(root)
    for rel in sorted(manifest.files):
        path = root / rel
        if not path.is_file():
            raise ManifestError(f"missing file: {rel}")
        if file_sha256(path) != manifest.files[rel]:
            raise ManifestError(f"sha256 mismatch: {rel}")
