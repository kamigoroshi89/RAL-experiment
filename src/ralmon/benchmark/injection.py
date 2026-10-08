"""Shared injection machinery of the benchmark generator (WS04-T07).

The injectors of the benchmark corrupt the **observed base stream** of T06 (``ObservedStream``)
and never the latent day. This module holds what every injector shares: the specification of an
injection (``InjectionSpec``), the record of a realised or unrealised one (``InjectionRecord``),
the canonical pipeline (``apply_observation_injections``), the conversion to an ``ObservedDay``
(``finalize_observed``), the mapping to the ground truth (``record_to_ground_truth``), the log
sidecar (``injection_log``) and the design loader of ``configs/benchmark/injections.yaml``.
The C2 injectors are in ``ralmon.benchmark.inject_c2`` and the C3 attacks of WS04-T08 in
``ralmon.benchmark.inject_c3`` (they register themselves here).

Pipeline (fixed order, ``docs/models/fault-model.md`` hypothesis 3)
  1. robot faults (``robot`` stage), 2. device faults (``device``), 3. sequence numbering of
  the cuff messages and the dispenser events (``assign_device_seq``, once, with the chaining
  counters of the context), 4. link faults (``link``, removal last: a lost message keeps the
  sequence number it was sent with, so the delivered numbers show the gap), 5. an ``attack``
  stage after all of that, empty for C2 and used by the C3 attacks of WS04-T08 (they register
  with ``register_injector`` and ``_INJECTOR_MODULES``; their traffic is never renumbered by the
  pipeline and a dropout of the genuine device cannot remove it; an attack reads the genuine
  stream through ``InjectionWork.genuine_view``, the snapshot taken when the stage starts, so
  one attack never sees the traffic of another). Within a stage
  the order is the rank of the injector, then ``canonical_order``: the result does not depend
  on the order of the specs. Specs that overlap on one subtype (or one ``overlap_group``) and one target are refused
  (windows are half open, ``[onset, onset + duration)``; two windows that touch are allowed).

Ground truth and the latent day. Injection is part of the generator. It may read the latent
day through the optional ``InjectionContext.latent`` (a delayed measurement re-reads the latent
pressure at its new instant with the same cuff error: the paired design) but never changes it,
and it never writes generator-side data into an observed file: ``ObservedStream.visits`` and
``measurements`` carry latent values, and ``finalize_observed`` builds the ``ObservedDay`` from
the samples and events only. A C2 truth event is the injected event itself, whether or not a
channel can detect it; only a **realised** injection (one that changed at least one item of the
stream, ``n_changed > 0``) becomes a ``GroundTruthEvent``; the others stay in the injection
log with ``realised`` false (WS04-T12 reports the realisation rate).

Determinism. Randomness comes only from the named stream ``(seed, patient, day,
INJECTION_C2, sub_index)`` where ``sub_index`` is a digest of the identity of the injection
(subtype, target, onset, duration; ``injection_sub_index``): it does not depend on the
position in the spec list, on the other injections, on the magnitude or on whether the
injection is realised, so adding or removing one injection changes none of the draws of the
others (and none of the items it does not touch). An item added by an injection follows the
existing items with the same ``t_rx_ms`` (stable sort).

Resource bounds: at most ``MAX_INJECTIONS_PER_DAY`` specs, ``MAX_PARAMS`` params per spec,
``MAX_STREAM_SAMPLES`` samples and ``MAX_STREAM_EVENTS`` events (also after injection),
checked before any work. Every public function raises ``InjectionError`` (``InjectionSpecError``
for a spec, ``InjectionContextError`` for the context, the stream or a library,
``InjectionDesignError`` for the design file) and nothing else.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import math
import numbers
import os
from collections.abc import Callable, Hashable, Iterable, Mapping, Sequence
from dataclasses import KW_ONLY, dataclass, field
from itertools import pairwise
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final, TypeGuard

import numpy as np
import yaml

from ralmon.benchmark import vocab
from ralmon.benchmark.latent import T_DAY_MS
from ralmon.benchmark.measurement import (
    LatentSbpHold,
    MeasurementConfigError,
    MeasurementRecord,
    ObservedStream,
    RobotVisit,
    assign_device_seq,
)
from ralmon.benchmark.priors import PriorError, load_design_file
from ralmon.benchmark.rng import StreamKeyError, StreamPurpose, stream
from ralmon.benchmark.segments import SegmentLibrary
from ralmon.benchmark.trace import (
    GroundTruthEvent,
    InjectedClass,
    LatentDay,
    ObservedDay,
    TraceError,
    validate_day,
)
from ralmon.signals import DurationMs, Event, EventKind, Sample, TimeMs

__all__ = [
    "MAGNITUDE_MS",
    "MAGNITUDE_NONE",
    "MAGNITUDE_POSITIVE",
    "MAGNITUDE_REAL",
    "MAX_ABS_MAGNITUDE",
    "MAX_INJECTIONS_PER_DAY",
    "MAX_PARAMS",
    "MAX_STREAM_EVENTS",
    "MAX_STREAM_SAMPLES",
    "MAX_TIME_MS",
    "MIN_MAGNITUDE_LEVELS",
    "PIPELINE_STAGES",
    "SHAPE_POINT",
    "SHAPE_TICK",
    "SHAPE_WINDOW",
    "STAGE_ATTACK",
    "STAGE_DEVICE",
    "STAGE_LINK",
    "STAGE_ROBOT",
    "STAGE_SEQUENCE",
    "InjectionContext",
    "InjectionContextError",
    "InjectionDesignError",
    "InjectionError",
    "InjectionRecord",
    "InjectionResult",
    "InjectionSpec",
    "InjectionSpecError",
    "InjectionWork",
    "Injector",
    "LevelRow",
    "QuantityDesign",
    "SubtypeDesign",
    "apply_observation_injections",
    "canonical_order",
    "check_call",
    "check_previous_day",
    "finalize_observed",
    "ground_truth_events",
    "injection_log",
    "injection_rng",
    "injection_sub_index",
    "load_design_mapping",
    "load_injection_design",
    "record_to_ground_truth",
    "register_injector",
    "registered_subtypes",
    "resolve_magnitude",
    "stable_index",
]

STAGE_ROBOT: Final = "robot"
STAGE_DEVICE: Final = "device"
STAGE_SEQUENCE: Final = "sequence"
STAGE_LINK: Final = "link"
STAGE_ATTACK: Final = (
    "attack"  # after the link stage: attacker traffic is never numbered or dropped
)
PIPELINE_STAGES: Final = (
    STAGE_ROBOT,
    STAGE_DEVICE,
    STAGE_SEQUENCE,
    STAGE_LINK,
    STAGE_ATTACK,
)
_INJECTION_STAGES: Final = (STAGE_ROBOT, STAGE_DEVICE, STAGE_LINK, STAGE_ATTACK)
# Modules that register injectors on first use.
_INJECTOR_MODULES: Final = ("ralmon.benchmark.inject_c2", "ralmon.benchmark.inject_c3")

SHAPE_WINDOW: Final = "window"  # [onset, onset + duration) inside the day
SHAPE_TICK: Final = "tick"  # one per-tick fault: onset is the tick, end None
SHAPE_POINT: Final = "point"  # one point fault: onset is the event it follows, end None
_SHAPES: Final = (SHAPE_WINDOW, SHAPE_TICK, SHAPE_POINT)
MAGNITUDE_NONE: Final = "none"
MAGNITUDE_REAL: Final = "real"  # any finite signed number
MAGNITUDE_POSITIVE: Final = "positive"  # a finite number above zero
MAGNITUDE_MS: Final = "ms"  # a positive integral number of ms, at most one day
_MAGNITUDES: Final = (MAGNITUDE_NONE, MAGNITUDE_REAL, MAGNITUDE_POSITIVE, MAGNITUDE_MS)

# Resource guards of the generator.
MAX_INJECTIONS_PER_DAY: Final[int] = 1_000  # algorithmic: specs applied to one day
MAX_PARAMS: Final[int] = 16  # algorithmic: params of one spec
MAX_STREAM_SAMPLES: Final[int] = 500_000  # algorithmic: samples of one day
MAX_STREAM_EVENTS: Final[int] = 500_000  # algorithmic: events of one day
MAX_ABS_MAGNITUDE: Final[float] = 1e12  # algorithmic: bound of any magnitude
MIN_MAGNITUDE_LEVELS: Final[int] = 3  # algorithmic: levels of a magnitude in the design
MAX_DESIGN_BYTES: Final[int] = 1 << 22  # algorithmic: size of injections.yaml
_MAX_TEXT: Final = 256  # algorithmic: longest identifier or label
_INT64_MAX: Final = int(np.iinfo(np.int64).max)
_TIME_LIMIT: Final = _INT64_MAX // 4  # algorithmic: room for onset + duration
MAX_TIME_MS: Final[int] = _TIME_LIMIT  # largest onset or duration of a spec
_DAY_HEADROOM: Final = 4  # algorithmic: days of room above the last day index
_MAX_DAY_INDEX: Final = _INT64_MAX // T_DAY_MS // _DAY_HEADROOM
_SEED_BITS: Final = 64  # algorithmic: width of the root seed (rng.stream)
_DIGEST_BYTES: Final = 4  # algorithmic: bytes of a digest used as a stream sub_index
_MAX_SEQ: Final = _INT64_MAX // 2  # algorithmic: room for a counter that keeps growing
_WORD: Final = 1 << 32  # algorithmic: width of a stream key entry
# The family of a subtype in the design file: the unit class of a fault (C2, fault-model.md), the
# capability of an attack (C3, threat-model.md: BLE injection and replay, perception spoofing) or, for
# a C1 subtype (WS04-T09), what the patient does: a physiological change of the latent day
# (``physiology``) or a behaviour (``behaviour``: a refusal, a double take).
_FAMILIES_BY_CLASS: Final = {
    InjectedClass.C1: ("physiology", "behaviour"),
    InjectedClass.C2: ("device", "link", "robot"),
    InjectedClass.C3: ("ble_attack", "perception_attack"),
}
_FAMILIES: Final = tuple(sorted({f for fs in _FAMILIES_BY_CLASS.values() for f in fs}))
_PURPOSES: Final = {
    InjectedClass.C1: StreamPurpose.INJECTION_C1,
    InjectedClass.C2: StreamPurpose.INJECTION_C2,
    InjectedClass.C3: StreamPurpose.INJECTION_C3,
}

ParamValue = str | int | float | bool
JsonValue = Any


class InjectionError(ValueError):
    """Base of the errors of the injection modules."""


class InjectionSpecError(InjectionError):
    """An injection specification (or a list of them) is invalid."""


class InjectionContextError(InjectionError):
    """The context, the observed stream or a library given to the pipeline is invalid."""


class InjectionDesignError(InjectionError):
    """``injections.yaml`` or a level of it is invalid."""


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _is_integer(x: object) -> TypeGuard[numbers.Integral]:
    return not isinstance(x, (bool, np.bool_)) and isinstance(x, numbers.Integral)


def _int(
    name: str,
    x: object,
    lo: int,
    hi: int,
    error: type[InjectionError] = InjectionSpecError,
) -> int:
    if not _is_integer(x):
        raise error(f"{name} must be an integer")
    try:
        value = int(x)
    except Exception as exc:  # a number type whose conversion misbehaves
        raise error(f"{name} is not an integer") from exc
    if not lo <= value <= hi:
        raise error(f"{name} must lie in [{lo}, {hi}]")
    return value


def _real(
    name: str, x: object, error: type[InjectionError] = InjectionSpecError
) -> float:
    if isinstance(x, (bool, np.bool_)) or not isinstance(x, numbers.Real):
        raise error(f"{name} must be a finite number")
    try:
        value = float(x)
    except Exception as exc:  # too large, or a number type whose conversion misbehaves
        raise error(f"{name} is not a finite number") from exc
    if not math.isfinite(value):
        raise error(f"{name} must be a finite number")
    return value


def _text(
    name: str, x: object, error: type[InjectionError] = InjectionSpecError
) -> str:
    if not isinstance(x, str) or not x.strip() or len(x) > _MAX_TEXT:
        raise error(
            f"{name} must be a non-empty string of at most {_MAX_TEXT} characters"
        )
    return x


def _enum(
    name: str,
    x: object,
    allowed: tuple[str, ...],
    error: type[InjectionError] = InjectionSpecError,
) -> str:
    if not isinstance(x, str) or x not in allowed:
        raise error(f"{name} must be one of {allowed}")
    return x


def _optional_text(name: str, x: object) -> str | None:
    return None if x is None else _text(name, x)


def _param_value(key: str, value: object) -> ParamValue:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, str):
        if len(value) > _MAX_TEXT:
            raise InjectionSpecError(f"param {key!r} is longer than {_MAX_TEXT}")
        return value
    if _is_integer(value):
        return _int(f"param {key!r}", value, -_INT64_MAX, _INT64_MAX)
    if isinstance(value, numbers.Real):
        return _real(f"param {key!r}", value)
    raise InjectionSpecError(
        f"param {key!r} must be a string, a number or a bool, got {type(value).__name__}"
    )


def _params(raw: object) -> Mapping[str, ParamValue]:
    if raw is None:
        return MappingProxyType({})
    if not isinstance(raw, Mapping):
        raise InjectionSpecError("params must be a mapping")
    try:
        if len(raw) > MAX_PARAMS:
            raise InjectionSpecError(f"params has more than {MAX_PARAMS} entries")
        items = list(raw.items())
    except InjectionSpecError:
        raise
    except Exception as exc:  # a mapping whose methods misbehave
        raise InjectionSpecError(
            f"params cannot be read: {type(exc).__name__}"
        ) from exc
    if len(items) > MAX_PARAMS:
        raise InjectionSpecError(f"params has more than {MAX_PARAMS} entries")
    clean: dict[str, ParamValue] = {}
    for key, value in items:
        name = _text("a param key", key)
        clean[name] = _param_value(name, value)
    return MappingProxyType(dict(sorted(clean.items())))


# ---------------------------------------------------------------------------
# Specification and record
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class InjectionSpec:
    """What to inject: a subtype with an onset, a duration, a magnitude and parameters.

    ``onset_ms`` and ``duration_ms`` are integer ms on the continuing axis of the day
    (ADR-017). A window fault has a duration and acts on ``[onset, onset + duration)``; a
    per-tick fault (``nav_delay``, ``manipulation_failure``) has the tick time as onset and no
    duration; a point fault (``dispenser_bounce``) has the time of the real dispense it
    follows as onset and no duration. ``magnitude`` is one number in ``magnitude_unit``
    (mmHg for the bias, ms for a delay or a gap, 1 for the ECG noise factor).

    ``params`` carries the rest, and is the bridge to the schedule of WS07-T05, whose
    ``magnitude.<key>`` mapping has one key per injection: ``magnitude`` is the value of that
    single key (``bias_mmhg``, ``noise_level``, ``gap_ms``, ``delay_ms``) and ``params`` holds
    ``target`` (the unit of failure: ``cuff``, ``dispenser``, ``ecg``, ``oximeter``) and the
    subtype-specific choices (``kind`` of the visit); ``seed`` is not a field here: the stream
    is keyed by the identity of the injection. ``level`` names the design level the magnitude
    was taken from and ``confounder_group`` the pair it belongs to (both only recorded).
    """

    cls: InjectedClass
    subtype: str
    onset_ms: TimeMs
    duration_ms: DurationMs | None = None
    magnitude: float | None = None
    magnitude_unit: str | None = None
    params: Mapping[str, ParamValue] = field(default_factory=dict)
    level: str | None = None
    confounder_group: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.cls, InjectedClass):
            raise InjectionSpecError("cls must be an InjectedClass")
        _text("subtype", self.subtype)
        object.__setattr__(
            self, "onset_ms", _int("onset_ms", self.onset_ms, 0, _TIME_LIMIT)
        )
        if self.duration_ms is not None:
            object.__setattr__(
                self,
                "duration_ms",
                _int("duration_ms", self.duration_ms, 1, _TIME_LIMIT),
            )
        if self.magnitude is not None:
            value = _real("magnitude", self.magnitude)
            if abs(value) > MAX_ABS_MAGNITUDE:
                raise InjectionSpecError(
                    f"magnitude must be at most {MAX_ABS_MAGNITUDE:g}"
                )
            object.__setattr__(self, "magnitude", value)
        object.__setattr__(
            self,
            "magnitude_unit",
            _optional_text("magnitude_unit", self.magnitude_unit),
        )
        object.__setattr__(self, "params", _params(self.params))
        object.__setattr__(self, "level", _optional_text("level", self.level))
        object.__setattr__(
            self,
            "confounder_group",
            _optional_text("confounder_group", self.confounder_group),
        )

    def _key(self) -> tuple[Hashable, ...]:
        return (
            self.cls.value,
            self.subtype,
            self.onset_ms,
            self.duration_ms,
            self.magnitude,
            self.magnitude_unit,
            tuple(self.params.items()),
            self.level,
            self.confounder_group,
        )

    def __hash__(self) -> int:
        return hash(self._key())


@dataclass(frozen=True, slots=True)
class InjectionRecord:
    """The outcome of one injection: the spec, the instants of the truth event and what changed.

    ``realised_onset_ms`` and ``realised_end_ms`` are the instants of the ground-truth event
    (the spec's own window, the tick or the real dispense; windows are never clipped because a
    window outside the day is refused); ``realised_end_ms`` is None for a point or per-tick
    fault. ``n_changed`` counts the items (samples and events) removed, changed, moved or added,
    and ``realised`` is ``n_changed > 0``. ``evidence_paths`` is the evidence signature of the
    subtype (dotted ``EvidenceVector`` paths; empty for a declared diagnosability limit).
    ``details`` is a JSON-native mapping for the log (what was removed, a segment id, an error
    code); it is not part of the observed trace.
    """

    spec: InjectionSpec
    realised_onset_ms: TimeMs
    realised_end_ms: TimeMs | None
    realised: bool
    n_changed: int
    evidence_paths: tuple[str, ...]
    level: str | None = None
    confounder_group: str | None = None
    details: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.spec, InjectionSpec):
            raise InjectionSpecError("spec must be an InjectionSpec")
        _int("realised_onset_ms", self.realised_onset_ms, 0, _TIME_LIMIT)
        if self.realised_end_ms is not None:
            _int("realised_end_ms", self.realised_end_ms, 0, _TIME_LIMIT)
        n = _int("n_changed", self.n_changed, 0, _INT64_MAX)
        if not isinstance(self.realised, bool) or self.realised != (n > 0):
            raise InjectionSpecError("realised must be True exactly when n_changed > 0")
        if not isinstance(self.evidence_paths, tuple) or not all(
            isinstance(p, str) and p for p in self.evidence_paths
        ):
            raise InjectionSpecError("evidence_paths must be a tuple of paths")
        _optional_text("level", self.level)
        _optional_text("confounder_group", self.confounder_group)
        if not isinstance(self.details, Mapping):
            raise InjectionSpecError("details must be a mapping")
        try:
            copied = dict(self.details)
            json.dumps(copied, allow_nan=False)
        except (
            Exception
        ) as exc:  # a mapping that misbehaves, or a value that is not JSON
            raise InjectionSpecError(
                f"details must be JSON-native: {type(exc).__name__}"
            ) from exc
        object.__setattr__(self, "details", copied)


def _bounds(name: str, value: object) -> tuple[float, float] | None:
    """A pair ``(lower, upper)`` of finite numbers with ``lower <= upper``, or None."""
    if value is None:
        return None
    error = InjectionContextError
    if not isinstance(value, (tuple, list)):
        raise error(f"{name} must be a pair (lower, upper) or None")
    try:
        items = list(value)
    except Exception as exc:  # a tuple or list subclass that misbehaves
        raise error(f"{name} cannot be read: {type(exc).__name__}") from exc
    if len(items) != 2:
        raise error(f"{name} must be a pair (lower, upper) or None")
    lower = _real(f"{name} lower", items[0], error)
    upper = _real(f"{name} upper", items[1], error)
    if lower > upper:
        raise error(f"{name} needs lower <= upper")
    return (lower, upper)


def _devices(name: str, value: object) -> tuple[str, ...]:
    """The BLE devices of a collection, once each, sorted by name."""
    error = InjectionContextError
    if not isinstance(value, (tuple, list, set, frozenset)):
        raise error(f"{name} must be a tuple, a list or a set of device names")
    try:
        items = list(value)
    except Exception as exc:  # a collection that misbehaves
        raise error(f"{name} cannot be read: {type(exc).__name__}") from exc
    for item in items:
        if not isinstance(item, str) or item not in vocab.BLE_DEVICES:
            raise error(f"{name} must name devices among {vocab.BLE_DEVICES}")
    return tuple(sorted(set(items)))


@dataclass(frozen=True, slots=True)
class InjectionContext:
    """What the pipeline needs besides the stream and the specs.

    ``patient_index`` keys the named streams. ``library`` is the segment library (the noise
    segments of ``ecg_noise``; absent or without that kind, the subtype is disabled and
    recorded). ``latent`` is the latent day of the same patient, day and seed, read (never
    changed) so that a delayed measurement re-reads the latent pressure at its new instant.
    ``task_deadline_offset_ms`` is the interval from a tick to the deadline of its robot task
    (the registry ``sched_window``, passed by the caller as ``inflation_min_ms`` is in T06):
    ``nav_delay`` needs it. ``dispenser_content_sensing`` says whether the dispenser reports
    a content change (the extra dispense of a bounce then reports 0.0). ``cuff_start`` and
    ``dispenser_start`` are the first sequence numbers of the day (the ``next_*`` of the
    previous day's settings), see ``assign_device_seq``.

    The attack stage (WS04-T08) needs four more. ``previous_day`` is the observed stream of the
    day before (what a passive observer captured: the source of a replay); it must be the same
    patient and seed and ``day_index - 1`` (checked by ``check_previous_day``). ``bp_bounds_mmhg``
    and ``hr_bounds_bpm`` are the population bounds of a naive forger, a pair ``(lower, upper)``
    that the caller reads from the registry (``bound_bp_lower``, ``bound_bp_upper``) and from the
    design rows of ``injections.yaml``; the naive injection refuses to run without them.
    ``authenticating_devices`` lists the BLE devices that authenticate their messages (a
    deployment property, per device: hypothesis H-DEP of the threat model); a forged or rewritten
    message of such a device leaves a failed verification in the trace, the message of a device
    that does not authenticate leaves none (the field is ``None``, never a negative).
    """

    patient_index: int
    _: KW_ONLY
    library: SegmentLibrary | None = None
    latent: LatentDay | None = None
    task_deadline_offset_ms: DurationMs | None = None
    dispenser_content_sensing: bool = False
    cuff_start: int = 1
    dispenser_start: int = 1
    previous_day: ObservedStream | None = None
    bp_bounds_mmhg: tuple[float, float] | None = None
    hr_bounds_bpm: tuple[float, float] | None = None
    authenticating_devices: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        error = InjectionContextError
        _int("patient_index", self.patient_index, 0, _WORD - 1, error)
        if self.library is not None and not isinstance(self.library, SegmentLibrary):
            raise error("library must be a SegmentLibrary or None")
        if self.latent is not None and not isinstance(self.latent, LatentDay):
            raise error("latent must be a LatentDay or None")
        if self.task_deadline_offset_ms is not None:
            _int(
                "task_deadline_offset_ms",
                self.task_deadline_offset_ms,
                1,
                T_DAY_MS,
                error,
            )
        if not isinstance(self.dispenser_content_sensing, bool):
            raise error("dispenser_content_sensing must be a bool")
        _int("cuff_start", self.cuff_start, 1, _MAX_SEQ, error)
        _int("dispenser_start", self.dispenser_start, 1, _MAX_SEQ, error)
        if self.previous_day is not None and not isinstance(
            self.previous_day, ObservedStream
        ):
            raise error("previous_day must be an ObservedStream or None")
        for name in ("bp_bounds_mmhg", "hr_bounds_bpm"):
            object.__setattr__(self, name, _bounds(name, getattr(self, name)))
        object.__setattr__(
            self,
            "authenticating_devices",
            _devices("authenticating_devices", self.authenticating_devices),
        )


@dataclass(frozen=True, slots=True)
class InjectionResult:
    """The injected stream, one record per spec (in execution order) and the disabled subtypes."""

    stream: ObservedStream
    records: tuple[InjectionRecord, ...]
    disabled_subtypes: tuple[str, ...]


class InjectionWork:
    """The mutable working copy of a stream that the injectors edit, stage by stage.

    ``samples`` and ``events`` are lists of immutable items; an injector replaces, removes or
    appends items and the pipeline restores the order after each stage (stable sort by
    ``t_rx_ms``). ``failed_visits`` holds the ``(kind, index)`` of visits whose manipulation
    failed; ``disabled`` the subtypes an injector could not run (a missing library);
    ``unsequenced`` the half-open windows ``(lo, hi)`` of attacker traffic that does not follow
    the sequence of the device (a stale replay, a forger with a counter of its own): an attack
    that renumbers the sequence of the device leaves the items inside them alone.
    ``attacker_next`` is the next number of the counter of its own that a forger keeps per device
    for the whole day (a naive attacker has one counter, not one per attack).
    """

    __slots__ = (
        "attacker_next",
        "care_plan_id",
        "context",
        "day_index",
        "disabled",
        "events",
        "failed_visits",
        "genuine",
        "latent_hold",
        "measurements",
        "patient_id",
        "samples",
        "seed",
        "settings",
        "unsequenced",
        "visits",
    )

    def __init__(self, stream_: ObservedStream, context: InjectionContext) -> None:
        context = _check_context(context)
        stream_ = _check_stream(stream_)
        self.patient_id: str = stream_.patient_id
        self.day_index: int = stream_.day_index
        self.seed: int = stream_.seed
        self.care_plan_id: str = stream_.care_plan_id
        self.samples: list[Sample] = list(stream_.samples)
        self.events: list[Event] = list(stream_.events)
        self.visits: list[RobotVisit] = list(stream_.visits)
        self.measurements: list[MeasurementRecord] = list(stream_.measurements)
        self.settings: dict[str, Any] = dict(stream_.settings)
        self.failed_visits: set[tuple[str, int]] = set()
        self.disabled: set[str] = set()
        self.context: InjectionContext = context
        self.latent_hold: LatentSbpHold | None = None
        self.genuine: tuple[tuple[Sample, ...], tuple[Event, ...]] | None = None
        self.unsequenced: list[tuple[int, int]] = []
        self.attacker_next: dict[str, int] = {}

    @property
    def day_start_ms(self) -> TimeMs:
        return self.day_index * T_DAY_MS

    @property
    def day_end_ms(self) -> TimeMs:
        return (self.day_index + 1) * T_DAY_MS

    def sort(self) -> None:
        """Stable sort by ``t_rx_ms``: an added item follows the existing ones at its instant."""
        self.samples.sort(key=_by_rx)
        self.events.sort(key=_by_rx)

    def freeze_genuine(self) -> None:
        """Take the snapshot of what the devices delivered (the pipeline does it before the attacks)."""
        self.genuine = (tuple(self.samples), tuple(self.events))

    def genuine_view(self) -> tuple[tuple[Sample, ...], tuple[Event, ...]]:
        """The ``(samples, events)`` that the genuine devices and the link delivered.

        After ``freeze_genuine`` it is the snapshot, so that an attack never reads the traffic
        that another attack wrote; before it (an injector called directly) it is the current
        content. The tuples are immutable: an attack that edits ``samples`` and ``events`` leaves
        the view as it was.
        """
        if self.genuine is not None:
            return self.genuine
        return (tuple(self.samples), tuple(self.events))

    def as_stream(self) -> ObservedStream:
        return ObservedStream(
            self.patient_id,
            self.day_index,
            self.seed,
            self.care_plan_id,
            tuple(self.samples),
            tuple(self.events),
            tuple(self.visits),
            tuple(self.measurements),
            dict(self.settings),
        )

    def check_bounds(self) -> None:
        if (
            len(self.samples) > MAX_STREAM_SAMPLES
            or len(self.events) > MAX_STREAM_EVENTS
        ):
            raise InjectionContextError(
                "the injected stream would exceed "
                f"{MAX_STREAM_SAMPLES} samples or {MAX_STREAM_EVENTS} events"
            )


def _by_rx(item: Sample | Event) -> int:
    return item.t_rx_ms


# ---------------------------------------------------------------------------
# Injector registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Injector:
    """How one subtype is specified and applied (registered by the module that implements it).

    ``apply(work, specs, context)`` receives the specs of the subtype in canonical order and
    returns one ``InjectionRecord`` per spec, in the same order. ``targets`` are the allowed
    values of the ``target`` param (the first is the default; ``target_required`` makes it
    mandatory). ``choices`` maps another param to its allowed values (the first is the
    default). ``magnitude`` is one of ``none``, ``real``, ``positive`` and ``ms`` and
    ``magnitude_unit`` the unit that a spec must give; with ``magnitude_optional`` a spec may
    give neither (the injector then uses its documented default). A choice is a set of strings
    or a set of booleans (never a mix; a boolean choice only accepts a bool).

    ``levels`` (empty: the level of a spec is a free label that is only recorded, as for C2) are
    the attacker levels of a C3 subtype: the ``level`` of a spec must be one of them, and
    ``level_required`` makes it mandatory (otherwise the first is the default).
    ``overlap_group`` names a group of subtypes whose windows on one target must not overlap
    each other (the three attacks on the cuff stream), instead of only windows of the same subtype.
    """

    cls: InjectedClass
    subtype: str
    stage: str
    rank: int
    shape: str
    magnitude: str
    magnitude_unit: str | None
    targets: tuple[str, ...]
    target_required: bool
    choices: Mapping[str, tuple[str | bool, ...]]
    signature: tuple[str, ...]
    apply: Callable[
        [InjectionWork, Sequence[InjectionSpec], InjectionContext],
        Sequence[InjectionRecord],
    ]
    magnitude_optional: bool = False
    levels: tuple[str, ...] = ()
    level_required: bool = False
    overlap_group: str | None = None

    def __post_init__(self) -> None:
        error = InjectionError
        if not isinstance(self.cls, InjectedClass):
            raise error("an injector needs an InjectedClass")
        _text("subtype", self.subtype, error)
        _enum("stage", self.stage, _INJECTION_STAGES, error)
        _int("rank", self.rank, 0, _INT64_MAX, error)
        _enum("shape", self.shape, _SHAPES, error)
        _enum("magnitude", self.magnitude, _MAGNITUDES, error)
        if self.magnitude_unit is not None:
            _text("magnitude_unit", self.magnitude_unit, error)
        if (self.magnitude == MAGNITUDE_NONE) != (self.magnitude_unit is None):
            raise error("a magnitude needs a unit and no magnitude none")
        if not isinstance(self.targets, tuple):
            raise error("targets must be a tuple")
        for target in self.targets:
            _text("a target", target, error)
        if not isinstance(self.target_required, bool) or not isinstance(
            self.magnitude_optional, bool
        ):
            raise error("target_required and magnitude_optional must be bool")
        if not isinstance(self.choices, Mapping):
            raise error("choices must be a mapping")
        try:
            choices = list(self.choices.items())
        except Exception as exc:  # a mapping that misbehaves
            raise error(f"choices cannot be read: {type(exc).__name__}") from exc
        for key, values in choices:
            _text("a choice key", key, error)
            if not isinstance(values, tuple) or not values:
                raise error("the values of a choice must be a non-empty tuple")
            if all(isinstance(value, bool) for value in values):
                pass
            elif all(isinstance(value, str) for value in values):
                for value in values:
                    _text("a choice value", value, error)
            else:
                raise error("a choice holds strings or booleans, not a mix")
            if len(set(values)) != len(values):
                raise error("a choice lists a value twice")
        if not isinstance(self.levels, tuple):
            raise error("levels must be a tuple")
        for level in self.levels:
            _text("a level", level, error)
        if len(set(self.levels)) != len(self.levels):
            raise error("levels lists a level twice")
        if not isinstance(self.level_required, bool):
            raise error("level_required must be a bool")
        if self.level_required and not self.levels:
            raise error("level_required needs levels")
        if self.overlap_group is not None:
            _text("overlap_group", self.overlap_group, error)
        if not isinstance(self.signature, tuple) or not all(
            isinstance(path, str) and path for path in self.signature
        ):
            raise error("signature must be a tuple of dotted paths")
        if not callable(self.apply):
            raise error("apply must be callable")


_REGISTRY: dict[tuple[InjectedClass, str], Injector] = {}


def register_injector(injector: Injector) -> None:
    """Register the injector of a subtype (once; a second registration is an error)."""
    if not isinstance(injector, Injector):
        raise InjectionError("injector must be an Injector")
    key = (injector.cls, injector.subtype)
    if key in _REGISTRY and _REGISTRY[key] is not injector:
        raise InjectionError(f"subtype {injector.subtype!r} is already registered")
    _REGISTRY[key] = injector


def _ensure_registered() -> None:
    for name in _INJECTOR_MODULES:
        importlib.import_module(name)


def registered_subtypes(cls: InjectedClass) -> tuple[str, ...]:
    """The subtypes of a class that have an injector, in canonical order (stage, rank, name)."""
    _ensure_registered()
    if not isinstance(cls, InjectedClass):
        raise InjectionSpecError("cls must be an InjectedClass")
    found = [i for (c, _), i in _REGISTRY.items() if c is cls]
    found.sort(key=_injector_rank)
    return tuple(i.subtype for i in found)


def _injector_rank(injector: Injector) -> tuple[int, int, str]:
    return (_INJECTION_STAGES.index(injector.stage), injector.rank, injector.subtype)


def _injector_of(spec: InjectionSpec) -> Injector:
    injector = _REGISTRY.get((spec.cls, spec.subtype))
    if injector is None:
        raise InjectionSpecError(
            f"no injector is registered for {spec.cls.value} subtype {spec.subtype!r}"
        )
    return injector


# ---------------------------------------------------------------------------
# Canonical order and spec validation
# ---------------------------------------------------------------------------


def stable_index(domain: str, *parts: str | int | None) -> int:
    """A 32-bit integer from a digest of ``domain`` and ``parts`` (a stream ``sub_index``).

    The digest uses only strings and integers (no ``hash()``), so the index is the same in any
    process and on any platform.
    """
    _text("domain", domain)
    clean: list[str | int | None] = []
    for part in parts:
        if part is None:
            clean.append(None)
        elif isinstance(part, str):
            if len(part) > _MAX_TEXT:
                raise InjectionSpecError(f"a part is longer than {_MAX_TEXT}")
            clean.append(part)
        else:
            clean.append(_int("a part", part, -_INT64_MAX, _INT64_MAX))
    payload = json.dumps([domain, *clean], separators=(",", ":"), allow_nan=False)
    return int.from_bytes(
        hashlib.sha256(payload.encode("utf-8")).digest()[:_DIGEST_BYTES], "big"
    )


def _target_of(spec: InjectionSpec, injector: Injector) -> str | None:
    target = spec.params.get("target")
    if target is None:
        return (
            injector.targets[0]
            if injector.targets and not injector.target_required
            else None
        )
    return target if isinstance(target, str) else None


def injection_sub_index(spec: InjectionSpec) -> int:
    """The ``sub_index`` of the named stream of an injection (module docstring)."""
    if not isinstance(spec, InjectionSpec):
        raise InjectionSpecError("spec must be an InjectionSpec")
    _ensure_registered()
    injector = _REGISTRY.get((spec.cls, spec.subtype))
    if injector is not None:
        target = _target_of(spec, injector)  # an omitted default target is the target
    else:
        raw = spec.params.get("target")
        target = raw if isinstance(raw, str) else None
    return stable_index(
        "injection",
        spec.cls.value,
        spec.subtype,
        target,
        spec.onset_ms,
        spec.duration_ms,
    )


def injection_rng(
    work: InjectionWork, context: InjectionContext, spec: InjectionSpec
) -> np.random.Generator:
    """The named stream of an injection: ``(seed, patient, day, INJECTION_<class>, sub_index)``."""
    if not isinstance(work, InjectionWork):
        raise InjectionContextError("work must be an InjectionWork")
    if not isinstance(context, InjectionContext):
        raise InjectionContextError("context must be an InjectionContext")
    if not isinstance(spec, InjectionSpec):
        raise InjectionSpecError("spec must be an InjectionSpec")
    purpose = _PURPOSES.get(spec.cls)
    if purpose is None:
        raise InjectionSpecError(f"no stream purpose for class {spec.cls.value}")
    try:
        return stream(
            work.seed,
            context.patient_index,
            work.day_index,
            purpose,
            injection_sub_index(spec),
        )
    except StreamKeyError as exc:
        raise InjectionContextError(str(exc)) from exc


def _checked_specs(specs: object) -> tuple[InjectionSpec, ...]:
    if isinstance(specs, (str, bytes)) or not isinstance(specs, (list, tuple)):
        raise InjectionSpecError("specs must be a list or a tuple of InjectionSpec")
    if len(specs) > MAX_INJECTIONS_PER_DAY:
        raise InjectionSpecError(
            f"at most {MAX_INJECTIONS_PER_DAY} injections can be applied to one day"
        )
    for item in specs:
        if not isinstance(item, InjectionSpec):
            raise InjectionSpecError("every spec must be an InjectionSpec")
    return tuple(specs)


def _params_key(params: Mapping[str, Any]) -> tuple[tuple[str, str, str], ...]:
    """Params as a sortable key: values of different types are never compared with each other."""
    return tuple(
        sorted((repr(k), type(v).__name__, repr(v)) for k, v in params.items())
    )


def _sort_key(spec: InjectionSpec) -> tuple[Any, ...]:
    injector = _injector_of(spec)
    target = _target_of(spec, injector)
    magnitude = (0, 0.0) if spec.magnitude is None else (1, spec.magnitude)
    return (
        _INJECTION_STAGES.index(injector.stage),
        injector.rank,
        spec.subtype,
        spec.cls.value,
        spec.onset_ms,
        target or "",
        -1 if spec.duration_ms is None else spec.duration_ms,
        magnitude,
        spec.magnitude_unit or "",
        _params_key(spec.params),
        spec.level or "",
        spec.confounder_group or "",
    )


def canonical_order(specs: Sequence[InjectionSpec]) -> tuple[InjectionSpec, ...]:
    """The specs in execution order: robot, device, link stage; within a stage by rank.

    The order is a total function of the content of the specs, so the result of a pipeline run
    does not depend on how the caller ordered them.
    """
    _ensure_registered()
    return tuple(sorted(_checked_specs(specs), key=_sort_key))


def _check_spec_shape(
    spec: InjectionSpec, injector: Injector, day_start: int, day_end: int
) -> None:
    name = spec.subtype
    if injector.shape == SHAPE_WINDOW:
        if spec.duration_ms is None:
            raise InjectionSpecError(
                f"{name} is a window fault and needs a duration_ms"
            )
        if spec.onset_ms < day_start or spec.onset_ms + spec.duration_ms > day_end:
            raise InjectionSpecError(
                f"{name} window [{spec.onset_ms}, {spec.onset_ms + spec.duration_ms}) "
                f"is not inside the day [{day_start}, {day_end}]"
            )
    else:
        if spec.duration_ms is not None:
            raise InjectionSpecError(f"{name} has no duration")
        if not day_start <= spec.onset_ms < day_end + T_DAY_MS:
            raise InjectionSpecError(
                f"{name} onset {spec.onset_ms} is outside the day [{day_start}, {day_end}) "
                "and the following day"
            )
    _check_magnitude(spec, injector)
    if injector.levels:
        if spec.level is None:
            if injector.level_required:
                raise InjectionSpecError(
                    f"{name} needs a level, one of {injector.levels}"
                )
        elif spec.level not in injector.levels:
            raise InjectionSpecError(
                f"{name} level must be one of {injector.levels}, got {spec.level!r}"
            )
    allowed: dict[str, tuple[str | bool, ...]] = dict(injector.choices)
    if injector.targets:
        allowed["target"] = injector.targets
    for key, value in spec.params.items():
        if key not in allowed:
            raise InjectionSpecError(f"{name} has no param {key!r}")
        # a bool is not an int (1 == True), but any other equal value is the same choice
        if not any(
            isinstance(value, bool) == isinstance(a, bool) and value == a
            for a in allowed[key]
        ):
            raise InjectionSpecError(
                f"{name} param {key!r} must be one of {allowed[key]}, got {value!r}"
            )
    if injector.target_required and "target" not in spec.params:
        raise InjectionSpecError(f"{name} needs the param target")


def _check_magnitude(spec: InjectionSpec, injector: Injector) -> None:
    name = spec.subtype
    if injector.magnitude == MAGNITUDE_NONE:
        if spec.magnitude is not None or spec.magnitude_unit is not None:
            raise InjectionSpecError(f"{name} has no magnitude")
        return
    if spec.magnitude is None:
        if injector.magnitude_optional and spec.magnitude_unit is None:
            return
        raise InjectionSpecError(
            f"{name} needs a magnitude in {injector.magnitude_unit}"
        )
    if spec.magnitude_unit != injector.magnitude_unit:
        raise InjectionSpecError(
            f"{name} magnitude must be given in {injector.magnitude_unit!r}"
        )
    if injector.magnitude == MAGNITUDE_POSITIVE and not spec.magnitude > 0.0:
        raise InjectionSpecError(f"{name} magnitude must be above zero")
    if injector.magnitude == MAGNITUDE_MS and not (
        spec.magnitude.is_integer() and 1 <= spec.magnitude <= T_DAY_MS
    ):
        raise InjectionSpecError(
            f"{name} magnitude must be a whole number of ms in [1, {T_DAY_MS}]"
        )


def check_call(
    work: object, specs: object, context: object, subtype: str
) -> tuple[InjectionSpec, ...]:
    """Validate the arguments of an injector function called directly (not through the pipeline).

    ``work`` and ``context`` must be an ``InjectionWork`` and an ``InjectionContext``; ``specs``
    a list or tuple of specs of ``subtype`` that satisfy the shape rules of the injector for the
    day of ``work`` and do not overlap. Returns the specs; raises ``InjectionSpecError`` or
    ``InjectionContextError``.
    """
    if not isinstance(work, InjectionWork):
        raise InjectionContextError("work must be an InjectionWork")
    if not isinstance(context, InjectionContext):
        raise InjectionContextError("context must be an InjectionContext")
    _text("subtype", subtype)
    checked = _checked_specs(specs)
    for spec in checked:
        injector = _injector_of(spec)
        if spec.subtype != subtype:
            raise InjectionSpecError(
                f"{spec.subtype} given to the injector of {subtype}"
            )
        _check_spec_shape(spec, injector, work.day_start_ms, work.day_end_ms)
    _check_overlaps(checked)
    return checked


def _check_overlaps(ordered: Sequence[InjectionSpec]) -> None:
    windows: dict[tuple[str, str | None], list[tuple[int, int]]] = {}
    points: set[tuple[str, str | None, int, ParamValue | None]] = set()
    for spec in ordered:
        injector = _injector_of(spec)
        target = _target_of(spec, injector)
        if injector.shape == SHAPE_WINDOW:
            assert spec.duration_ms is not None
            group = injector.overlap_group or spec.subtype
            windows.setdefault((group, target), []).append(
                (spec.onset_ms, spec.onset_ms + spec.duration_ms)
            )
        else:
            key = (spec.subtype, target, spec.onset_ms, spec.params.get("kind"))
            if key in points:
                raise InjectionSpecError(
                    f"two {spec.subtype} injections at {spec.onset_ms} on the same unit"
                )
            points.add(key)
    for (group, target), spans in windows.items():
        spans.sort()
        for (_, end), (start, _) in pairwise(spans):
            if start < end:
                raise InjectionSpecError(
                    f"two {group} windows overlap on {target!r} at {start}"
                )


# ---------------------------------------------------------------------------
# Stream and context checks
# ---------------------------------------------------------------------------


def _members(name: str, items: object, kind: type, limit: int) -> list[Any]:
    if isinstance(items, (str, bytes)) or not isinstance(items, Sequence):
        raise InjectionContextError(f"the {name} of the stream must be a sequence")
    try:
        if len(items) > limit:
            raise InjectionContextError(f"the stream holds more than {limit} {name}")
        listed = list(items)
    except InjectionContextError:
        raise
    except Exception as exc:  # a sequence whose methods misbehave
        raise InjectionContextError(
            f"the {name} of the stream cannot be read: {type(exc).__name__}"
        ) from exc
    for item in listed:
        if not isinstance(item, kind):
            raise InjectionContextError(
                f"every item of {name} must be a {kind.__name__}"
            )
    return listed


def _check_time(name: str, value: object, *, allow_negative: bool) -> None:
    lo = -_TIME_LIMIT if allow_negative else 0
    _int(name, value, lo, _TIME_LIMIT, InjectionContextError)


def _check_visit(visit: RobotVisit) -> None:
    for name in ("index", "tick_ms", "arrival_ms", "departure_ms", "delay_ms"):
        _int(
            f"visit {name}", getattr(visit, name), 0, _TIME_LIMIT, InjectionContextError
        )
    _enum("visit kind", visit.kind, vocab.KINDS, InjectionContextError)


def _check_measurement(record: MeasurementRecord) -> None:
    for name in ("index", "tick_ms", "arrival_ms", "t_ms", "inflation_ms"):
        _int(
            f"measurement {name}",
            getattr(record, name),
            0,
            _TIME_LIMIT,
            InjectionContextError,
        )
    for name in ("latent_sbp_mmhg", "error_mmhg", "value_mmhg"):
        _real(f"measurement {name}", getattr(record, name), InjectionContextError)
    if record.pulse_bpm is not None:
        _real("measurement pulse_bpm", record.pulse_bpm, InjectionContextError)
    if not isinstance(record.inflation_raised, bool):
        raise InjectionContextError("measurement inflation_raised must be a bool")


def _check_sample(sample: Sample) -> None:
    if not isinstance(sample.signal, str) or not sample.signal:
        raise InjectionContextError("every sample needs a signal name")
    _check_time("t_device_ms", sample.t_device_ms, allow_negative=True)
    _check_time("t_rx_ms", sample.t_rx_ms, allow_negative=False)
    _real("a sample value", sample.value, InjectionContextError)
    if sample.seq is not None:
        _int("seq", sample.seq, -_INT64_MAX, _INT64_MAX, InjectionContextError)
    if sample.quality is not None:
        _real("a sample quality", sample.quality, InjectionContextError)


def _check_event(event: Event) -> None:
    if not isinstance(event.kind, EventKind):
        raise InjectionContextError("every event needs an EventKind")
    _check_time("t_device_ms", event.t_device_ms, allow_negative=True)
    _check_time("t_rx_ms", event.t_rx_ms, allow_negative=False)
    if not isinstance(event.source, str) or not event.source:
        raise InjectionContextError("every event needs a source")
    if not isinstance(event.payload, Mapping):
        raise InjectionContextError("an event payload must be a mapping")
    try:
        items = list(event.payload.items())
    except Exception as exc:  # a mapping that misbehaves
        raise InjectionContextError(
            f"an event payload cannot be read: {type(exc).__name__}"
        ) from exc
    for key, value in items:
        if not isinstance(key, str) or not isinstance(value, (str, int, float, bool)):
            raise InjectionContextError(
                "a payload maps strings to strings, numbers or bools"
            )
    if event.seq is not None:
        _int("seq", event.seq, -_INT64_MAX, _INT64_MAX, InjectionContextError)


def _check_sorted(items: Sequence[Sample | Event], name: str) -> None:
    for previous, current in pairwise(items):
        if current.t_rx_ms < previous.t_rx_ms:
            raise InjectionContextError(f"the {name} are not sorted by t_rx_ms")


def _check_stream(stream_: object) -> ObservedStream:
    if not isinstance(stream_, ObservedStream):
        raise InjectionContextError("stream must be an ObservedStream")
    _text("patient_id", stream_.patient_id, InjectionContextError)
    _text("care_plan_id", stream_.care_plan_id, InjectionContextError)
    _int("day_index", stream_.day_index, 0, _MAX_DAY_INDEX, InjectionContextError)
    _int("seed", stream_.seed, 0, (1 << _SEED_BITS) - 1, InjectionContextError)
    samples = _members("samples", stream_.samples, Sample, MAX_STREAM_SAMPLES)
    events = _members("events", stream_.events, Event, MAX_STREAM_EVENTS)
    for sample in samples:
        _check_sample(sample)
    for event in events:
        _check_event(event)
    _check_sorted(samples, "samples")
    _check_sorted(events, "events")
    for visit in _members("visits", stream_.visits, RobotVisit, MAX_STREAM_EVENTS):
        _check_visit(visit)
    for record in _members(
        "measurements", stream_.measurements, MeasurementRecord, MAX_STREAM_EVENTS
    ):
        _check_measurement(record)
    settings = stream_.settings
    try:
        valid = isinstance(settings, Mapping) and all(
            isinstance(k, str) for k in settings
        )
    except Exception as exc:  # a mapping that misbehaves
        raise InjectionContextError(
            f"settings cannot be read: {type(exc).__name__}"
        ) from exc
    if not valid:
        raise InjectionContextError("settings must be a mapping with string keys")
    return stream_


def _check_context(context: object) -> InjectionContext:
    if not isinstance(context, InjectionContext):
        raise InjectionContextError("context must be an InjectionContext")
    return context


def check_previous_day(work: object, context: object) -> ObservedStream | None:
    """The previous day of the context, validated against the day of ``work`` (None if absent).

    It must be a well-formed observed stream of the same patient and seed whose ``day_index`` is
    one less than the day of ``work``; anything else is an ``InjectionContextError``. The stream
    is only read: a replay copies from it, nothing writes into it.
    """
    if not isinstance(work, InjectionWork):
        raise InjectionContextError("work must be an InjectionWork")
    previous = _check_context(context).previous_day
    if previous is None:
        return None
    previous = _check_stream(previous)
    if not (
        previous.patient_id == work.patient_id
        and previous.seed == work.seed
        and previous.day_index == work.day_index - 1
    ):
        raise InjectionContextError(
            "the previous day must be the day before the stream (same patient and seed)"
        )
    return previous


# ---------------------------------------------------------------------------
# The pipeline
# ---------------------------------------------------------------------------


def _run_stage(
    stage: str,
    ordered: Sequence[InjectionSpec],
    work: InjectionWork,
    context: InjectionContext,
) -> list[InjectionRecord]:
    records: list[InjectionRecord] = []
    here = [s for s in ordered if _injector_of(s).stage == stage]
    for subtype in dict.fromkeys(s.subtype for s in here):
        group = [s for s in here if s.subtype == subtype]
        made = list(_injector_of(group[0]).apply(work, group, context))
        if len(made) != len(group) or any(
            not isinstance(r, InjectionRecord) or r.spec != s
            for r, s in zip(made, group, strict=True)
        ):
            raise InjectionError(f"injector of {subtype} returned inconsistent records")
        records.extend(made)
        work.sort()
        work.check_bounds()
    return records


def _number(work: InjectionWork, context: InjectionContext) -> None:
    try:
        numbered = assign_device_seq(
            work.as_stream(),
            cuff_start=context.cuff_start,
            dispenser_start=context.dispenser_start,
        )
    except MeasurementConfigError as exc:
        raise InjectionContextError(str(exc)) from exc
    work.samples = list(numbered.samples)
    work.events = list(numbered.events)
    work.settings = dict(numbered.settings)


def apply_observation_injections(
    stream_: ObservedStream, specs: Sequence[InjectionSpec], context: InjectionContext
) -> InjectionResult:
    """Apply the injections to an observed base stream in the canonical order.

    Returns the injected stream (a new ``ObservedStream``: the input is never modified) and
    one record per spec in execution order. Raises ``InjectionSpecError`` for an invalid spec
    list (shape, range, overlap, unknown subtype) and ``InjectionContextError`` for an invalid
    stream or context; an injection that finds nothing to change is not an error but a record
    with ``realised`` false.
    """
    _ensure_registered()
    work = InjectionWork(stream_, context)  # checks the context and the stream
    ctx = work.context
    ordered = canonical_order(specs)
    for spec in ordered:
        _check_spec_shape(spec, _injector_of(spec), work.day_start_ms, work.day_end_ms)
    _check_overlaps(ordered)
    latent = ctx.latent
    if latent is not None and not (
        isinstance(latent.patient_id, str)
        and latent.patient_id == work.patient_id
        and _is_integer(latent.day_index)
        and latent.day_index == work.day_index
        and _is_integer(latent.seed)
        and latent.seed == work.seed
    ):
        raise InjectionContextError(
            "the latent day is not the day of the stream (patient, day and seed)"
        )
    check_previous_day(work, ctx)
    work.check_bounds()
    records: list[InjectionRecord] = []
    records.extend(_run_stage(STAGE_ROBOT, ordered, work, ctx))
    records.extend(_run_stage(STAGE_DEVICE, ordered, work, ctx))
    _number(work, ctx)
    records.extend(_run_stage(STAGE_LINK, ordered, work, ctx))
    work.freeze_genuine()  # what the devices delivered: the view of every attack
    records.extend(_run_stage(STAGE_ATTACK, ordered, work, ctx))
    work.settings["injection_n_records"] = len(records)
    work.settings["injection_n_realised"] = sum(r.realised for r in records)
    disabled = tuple(sorted(work.disabled))
    work.settings["injection_disabled_subtypes"] = list(disabled)
    return InjectionResult(work.as_stream(), tuple(records), disabled)


# ---------------------------------------------------------------------------
# Observed day, ground truth and log
# ---------------------------------------------------------------------------


def finalize_observed(stream_: ObservedStream) -> ObservedDay:
    """The ``ObservedDay`` of a stream: samples and events only.

    ``visits``, ``measurements`` and ``settings`` of the stream carry generator-side and
    latent values (``MeasurementRecord.latent_sbp_mmhg``) and are never written. Every event
    payload is checked against ``vocab`` and the day against ``trace.validate_day``.
    """
    checked = _check_stream(stream_)
    for event in checked.events:
        try:
            vocab.check_payload(event.kind, event.payload)
        except vocab.VocabularyError as exc:
            raise InjectionContextError(str(exc)) from exc
    day = ObservedDay(
        patient_id=checked.patient_id,
        day_index=checked.day_index,
        seed=checked.seed,
        samples=tuple(checked.samples),
        events=tuple(checked.events),
        care_plan_id=checked.care_plan_id,
    )
    try:
        validate_day(day)
    except TraceError as exc:
        raise InjectionContextError(str(exc)) from exc
    return day


def _check_record(record: object) -> InjectionRecord:
    if not isinstance(record, InjectionRecord):
        raise InjectionSpecError("record must be an InjectionRecord")
    return record


def record_to_ground_truth(record: InjectionRecord) -> GroundTruthEvent | None:
    """The ground-truth event of a realised injection; None for an unrealised one.

    A C2 or C3 truth is the injected event itself: ``cls`` and ``subtype`` of the spec, the
    window of a window fault (``end_ms`` its end) or the instant of a point or per-tick fault
    (``end_ms`` None), ``injected`` True, no template, and the confounder group of the spec.
    """
    checked = _check_record(record)
    if not checked.realised:
        return None
    return GroundTruthEvent(
        cls=checked.spec.cls,
        subtype=checked.spec.subtype,
        onset_ms=checked.realised_onset_ms,
        end_ms=checked.realised_end_ms,
        injected=True,
        template_id=None,
        confounder_group=checked.confounder_group,
    )


def ground_truth_events(records: Iterable[InjectionRecord]) -> list[GroundTruthEvent]:
    """The ground-truth events of the realised records, sorted by onset then subtype."""
    if isinstance(records, (str, bytes)) or not isinstance(records, (list, tuple)):
        raise InjectionSpecError("records must be a list or a tuple of InjectionRecord")
    events = [
        e for e in (record_to_ground_truth(_check_record(r)) for r in records) if e
    ]
    return sorted(events, key=lambda e: (e.onset_ms, e.subtype))


def injection_log(records: Iterable[InjectionRecord]) -> list[dict[str, JsonValue]]:
    """JSON-native log entries (the ``injection_log`` sidecar of the truth file), one per record."""
    if isinstance(records, (str, bytes)) or not isinstance(records, (list, tuple)):
        raise InjectionSpecError("records must be a list or a tuple of InjectionRecord")
    log: list[dict[str, JsonValue]] = []
    for item in records:
        r = _check_record(item)
        log.append(
            {
                "cls": r.spec.cls.value,
                "subtype": r.spec.subtype,
                "onset_ms": r.realised_onset_ms,
                "duration_ms": r.spec.duration_ms,
                "end_ms": r.realised_end_ms,
                "magnitude": r.spec.magnitude,
                "magnitude_unit": r.spec.magnitude_unit,
                "params": dict(r.spec.params),
                "level": r.level,
                "confounder_group": r.confounder_group,
                "realised": r.realised,
                "n_changed": r.n_changed,
                "evidence_paths": list(r.evidence_paths),
                "details": dict(r.details),
            }
        )
    return log


# ---------------------------------------------------------------------------
# Design file
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LevelRow:
    """One level of a duration or a magnitude: a row of ``parameters:`` of the design file.

    ``value`` is None while the row is ``awaiting_human_value``. For a relative quantity
    (``QuantityDesign.reference`` names a reference quantity) the value is a multiple of it.
    """

    name: str
    level: str
    unit: str
    value: float | None
    filled: bool
    source_type: str
    source_ref: str
    quantity_unit: str = ""

    @property
    def reference(self) -> str | None:
        """The quantity this value is a multiple of (``unit`` is ``"x <name>"``), else None."""
        return self.unit[2:] if self.unit.startswith("x ") else None


@dataclass(frozen=True, slots=True)
class QuantityDesign:
    """A duration or a magnitude with its key, unit, optional reference and levels."""

    key: str
    unit: str
    reference: str | None
    levels: tuple[LevelRow, ...]


@dataclass(frozen=True, slots=True)
class SubtypeDesign:
    """The design of one subtype: family, targets, onset placement, duration, magnitude, rate."""

    subtype: str
    family: str
    targets: tuple[str, ...]
    onset: str
    duration: QuantityDesign | None
    magnitude: QuantityDesign | None
    rate_source: str | None


class _UniqueKeyLoader(yaml.SafeLoader):
    """Safe loader that refuses a repeated key instead of keeping the last one."""

    def construct_mapping(
        self, node: yaml.MappingNode, deep: bool = False
    ) -> dict[Hashable, Any]:
        seen: set[Hashable] = set()
        for key_node, _value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if isinstance(key, Hashable):
                if key in seen:
                    raise InjectionDesignError(f"duplicate key {key!r} in the YAML")
                seen.add(key)
        return super().construct_mapping(node, deep=deep)


def _design_path(path: object) -> Path:
    if not isinstance(path, (str, os.PathLike)) or isinstance(path, bytes):
        raise InjectionDesignError(f"path must be a path, got {type(path).__name__}")
    try:
        text = os.fspath(path)
    except (TypeError, ValueError, OSError) as exc:
        raise InjectionDesignError("path is not a valid path") from exc
    if not isinstance(text, str) or not text or "\0" in text:
        raise InjectionDesignError("path is not a valid path")
    return Path(text)


def _read_design(path: Path) -> Mapping[str, Any]:
    try:
        with path.open("rb") as handle:
            data = handle.read(MAX_DESIGN_BYTES + 1)
    except (OSError, ValueError) as exc:
        raise InjectionDesignError(
            f"{path} cannot be read: {type(exc).__name__}"
        ) from exc
    if len(data) > MAX_DESIGN_BYTES:
        raise InjectionDesignError(f"{path} is larger than {MAX_DESIGN_BYTES} bytes")
    try:
        document = yaml.load(data.decode("utf-8"), Loader=_UniqueKeyLoader)
    except InjectionDesignError:
        raise
    except (yaml.YAMLError, UnicodeDecodeError, RecursionError, ValueError) as exc:
        raise InjectionDesignError(
            f"{path} is not valid YAML: {type(exc).__name__}"
        ) from exc
    if not isinstance(document, Mapping):
        raise InjectionDesignError(f"{path} must hold a mapping at top level")
    return document


def _has_number(node: object, seen: set[int] | None = None) -> bool:
    if isinstance(node, bool):
        return False
    if isinstance(node, (int, float)):
        return True
    if not isinstance(node, (Mapping, list, tuple)):
        return False
    # YAML aliases share nodes: a node already walked held no number (else the walk would have
    # stopped), so walking it again only costs time (exponential in the depth of the aliases)
    seen = set() if seen is None else seen
    if id(node) in seen:
        return False
    seen.add(id(node))
    if isinstance(node, Mapping):
        return any(
            _has_number(k, seen) or _has_number(v, seen) for k, v in node.items()
        )
    return any(_has_number(v, seen) for v in node)


def _design_text(where: str, value: object) -> str:
    return _text(where, value, InjectionDesignError)


def _quantity(
    where: str,
    block: object,
    rows: Mapping[str, Any],
    *,
    minimum: int,
) -> QuantityDesign:
    if not isinstance(block, Mapping) or set(block) - {
        "key",
        "unit",
        "reference",
        "levels",
    }:
        raise InjectionDesignError(f"{where}: expected key, unit, reference and levels")
    key = _design_text(f"{where}.key", block.get("key"))
    unit = _design_text(f"{where}.unit", block.get("unit"))
    reference = block.get("reference")
    if reference is not None:
        reference = _design_text(f"{where}.reference", reference)
    levels = block.get("levels")
    if not isinstance(levels, Mapping) or len(levels) < minimum:
        raise InjectionDesignError(f"{where}: needs at least {minimum} levels")
    made: list[LevelRow] = []
    for level, name in levels.items():
        _design_text(f"{where} level", level)
        row_name = _design_text(f"{where} level {level!r}", name)
        row = rows.get(row_name)
        if row is None:
            raise InjectionDesignError(
                f"{where}: level {level!r} names no row {row_name!r}"
            )
        if not row.source_type or not (row.source_ref and row.source_ref.strip()):
            raise InjectionDesignError(
                f"row {row_name!r} needs source_type and source_ref"
            )
        value: float | None = None
        if row.filled:
            value = _real(f"row {row_name!r} value", row.value, InjectionDesignError)
        made.append(
            LevelRow(
                row_name,
                str(level),
                row.unit,
                value,
                row.filled,
                row.source_type,
                row.source_ref,
                unit,
            )
        )
    return QuantityDesign(key, unit, reference, tuple(made))


def load_injection_design(
    path: str | os.PathLike[str], *, section: str = "c2"
) -> Mapping[str, SubtypeDesign]:
    """Read the structured section of ``injections.yaml`` with the rows its levels name.

    The file has a top-level ``injections:`` mapping with one section per class (``c2``): per
    subtype the ``family``, the allowed ``target`` units, the ``onset`` placement rule, the
    ``duration`` and ``magnitude`` blocks (``key``, ``unit``, optional ``reference``, and
    ``levels``: a mapping from a level label to the name of a row of ``parameters:``) or null,
    and an optional ``rate`` block. The structured section holds no number: every number is a
    row of ``parameters:`` (same schema as the other design files, rendered into
    ``docs/benchmark/parameter-provenance.md``), and a row that is still
    ``awaiting_human_value`` gives a level with ``value`` None. The loader checks that the
    subtypes are exactly those with an injector, that the units agree with the injector, that a
    magnitude has at least ``MIN_MAGNITUDE_LEVELS`` levels and that every named row has a
    ``source_type`` and a ``source_ref``.
    """
    target = _design_path(path)
    if not isinstance(section, str) or not section:
        raise InjectionDesignError("section must be a non-empty string")
    document = _read_design(target)
    try:
        rows = {r.parameter: r for r in load_design_file(target).rows}
    except PriorError as exc:
        raise InjectionDesignError(f"{target}: {exc}") from exc
    injections = document.get("injections")
    if not isinstance(injections, Mapping) or not isinstance(
        injections.get(section), Mapping
    ):
        raise InjectionDesignError(f"{target}: no injections.{section} mapping")
    block = injections[section]
    if _has_number(block):
        raise InjectionDesignError(
            f"injections.{section} holds a number: numbers are rows of parameters:"
        )
    _ensure_registered()
    cls = next((c for c in InjectedClass if c.value.lower() == section.lower()), None)
    expected = registered_subtypes(cls) if cls is not None else ()
    if expected and set(block) != set(expected):
        raise InjectionDesignError(
            f"injections.{section} must list exactly {sorted(expected)}, got {sorted(map(str, block))}"
        )
    design: dict[str, SubtypeDesign] = {}
    for subtype, entry in block.items():
        where = f"injections.{section}.{subtype}"
        _design_text(where, subtype)
        if not isinstance(entry, Mapping):
            raise InjectionDesignError(f"{where} must be a mapping")
        family = entry.get("family")
        families = (
            _FAMILIES_BY_CLASS.get(cls, _FAMILIES) if cls is not None else _FAMILIES
        )
        if family not in families:
            raise InjectionDesignError(f"{where}.family must be one of {families}")
        targets = entry.get("target")
        if not isinstance(targets, list) or not targets:
            raise InjectionDesignError(f"{where}.target must be a non-empty list")
        onset = _design_text(f"{where}.onset", entry.get("onset"))
        duration = (
            None
            if entry.get("duration") is None
            else _quantity(f"{where}.duration", entry["duration"], rows, minimum=1)
        )
        magnitude = (
            None
            if entry.get("magnitude") is None
            else _quantity(
                f"{where}.magnitude",
                entry["magnitude"],
                rows,
                minimum=MIN_MAGNITUDE_LEVELS,
            )
        )
        rate = entry.get("rate")
        rate_source = None
        if rate is not None:
            if not isinstance(rate, Mapping) or set(rate) != {"source"}:
                raise InjectionDesignError(f"{where}.rate must have exactly a source")
            rate_source = _design_text(f"{where}.rate.source", rate["source"])
        injector = _REGISTRY.get((cls, subtype)) if cls is not None else None
        if injector is not None:
            if (duration is not None) != (injector.shape == SHAPE_WINDOW):
                raise InjectionDesignError(
                    f"{where}: duration disagrees with the injector"
                )
            if (magnitude is not None) != (injector.magnitude != MAGNITUDE_NONE):
                raise InjectionDesignError(
                    f"{where}: magnitude disagrees with the injector"
                )
            if magnitude is not None and magnitude.unit != injector.magnitude_unit:
                raise InjectionDesignError(
                    f"{where}: magnitude unit disagrees with the injector"
                )
            if duration is not None and duration.unit != "ms":
                raise InjectionDesignError(f"{where}: a duration is in ms")
            if tuple(targets) != injector.targets and injector.targets:
                raise InjectionDesignError(
                    f"{where}: targets disagree with the injector"
                )
        design[str(subtype)] = SubtypeDesign(
            str(subtype),
            str(family),
            tuple(_design_text(f"{where}.target", t) for t in targets),
            onset,
            duration,
            magnitude,
            rate_source,
        )
    return MappingProxyType(design)


def load_design_mapping(path: str | os.PathLike[str], key: str) -> Mapping[str, Any]:
    """The mapping under the top-level ``key`` of a design file (``InjectionDesignError`` otherwise).

    For the sections that hold no parameter rows and no recursion to walk (the attacker section
    of ``injections.yaml``): the file is read with the same safe loader that refuses a repeated
    key, and only the mapping under ``key`` is returned.
    """
    target = _design_path(path)
    if not isinstance(key, str) or not key:
        raise InjectionDesignError("key must be a non-empty string")
    section = _read_design(target).get(key)
    if not isinstance(section, Mapping):
        raise InjectionDesignError(f"{target}: no {key} mapping")
    return section


def resolve_magnitude(level: LevelRow, reference_value: float, reference: str) -> float:
    """The absolute magnitude of a relative level: ``level.value * reference_value``.

    ``reference`` names the quantity whose value ``reference_value`` is (the prior or registry
    name, for the bias ``cuff_error_sd_mmhg``) and must be the one the level itself names in its
    unit: a block can mix references (the level ``device_bias`` is a multiple of
    ``cuff_bias_mmhg`` inside a block whose other levels are multiples of the SD), and an
    absolute row has no reference to resolve. A quantity in milliseconds is rounded to whole
    milliseconds (ADR-017: a product such as ``1.1 * 900000`` is not an integer in binary
    floating point). A level that is still awaiting a value is an error, never a default.
    """
    if not isinstance(level, LevelRow):
        raise InjectionDesignError("level must be a LevelRow")
    if not isinstance(reference, str) or not reference:
        raise InjectionDesignError(
            "reference must be the name of the reference quantity"
        )
    if level.reference is None:
        raise InjectionDesignError(
            f"row {level.name!r} is absolute ({level.unit}): its value is the magnitude"
        )
    if reference != level.reference:
        raise InjectionDesignError(
            f"row {level.name!r} is a multiple of {level.reference!r}, not of {reference!r}"
        )
    if level.value is None:
        raise InjectionDesignError(f"row {level.name!r} is awaiting_human_value")
    value = level.value * _real(
        "reference_value", reference_value, InjectionDesignError
    )
    if not math.isfinite(value):
        raise InjectionDesignError("the resolved magnitude is not finite")
    if level.quantity_unit == "ms":
        value = float(round(value))
    return value
