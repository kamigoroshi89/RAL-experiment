"""Measurement process: the fault-free observed base stream of one day (WS04-T06).

``build_observed_base`` turns a complete latent day into what the devices and the robot would
report when nothing is wrong: care-plan ``SCHEDULE_TICK`` events, robot visits with arrival
jitter, cuff measurements with the device error model, nominal cuff inflation and health,
the cuff pulse rate, dispenser events as the device reports them, robot presence and
witnessed ``INTAKE``, and heart rate and SpO2 from clean public segments. The injectors of
WS04-T07 to T09 corrupt this stream; nothing here injects a fault.

Latent input. The pressure is read from the ``LatentDay.samples`` whose ``signal`` is ``bp``
(strictly increasing ``t_device_ms``; the latent grid, not the cuff). Of ``LatentDay.events``
only ``DISPENSE`` and ``INTAKE`` are read (their times); latent ``SCHEDULE_TICK`` and
``MEASUREMENT`` events and every latent source or payload are ignored, so the observed ticks
come from the schedule and the observed readings from the device model. Heart rate and SpO2
are not read from the latent day: ``draw_clean_vitals`` draws them from the segment library
with a named stream, and the latent assembly of WS04-T09 must call the same function so that
the latent and the observed heart rate agree. The ``seed`` argument must equal ``latent.seed``
(one root seed per benchmark: a mismatch would draw the observed noise from another seed than the
latent day was generated with, so it is refused). The latent day is never modified.

Hold. The latent pressure at an instant is the value of the last grid point at or before it
(piecewise constant, right-continuous, as ``ralmon.signals.hold_last``). An instant before
the first grid point has no value (``hold_last`` gives ``nan``): ``LatentSbpHold.at`` raises
``MeasurementConfigError``, never a reading. An instant after the last grid point holds the
last value (the latent day has no closing step: its last value holds to the day end and
beyond); the readings stamped after the closing instant of their day, which no latent
point of that day covers, are counted in ``settings["n_measurements_after_day_end"]``.

Time. Integer milliseconds on the continuing axis ``day_index * T_day + clock time``
(ADR-017). The schedule ticks are clock times in ``[0, T_day)``. Every item generated from
the ticks of day ``d`` belongs to the stream of day ``d`` whatever its time: a visit pushed by
jitter after midnight, a reading that crosses midnight and an intake after midnight stay in
the day of their tick (as the adherence model keeps a slot in the day of its dose), so a
stream may hold items later than ``(d + 1) * T_day``. The end-of-day impulse ``day_end`` is
the sample at exactly ``(d + 1) * T_day``: ``docs/formal/01-signals-sampling.md`` section 5.5
item 2 ("true at the closing step K of a day") with the day-boundary choice M7 of
``ralmon.signals`` (day ``d`` covers ``(d * T_day, (d + 1) * T_day]``, the closing step belongs
to the day it closes). ``t_rx_ms == t_device_ms`` (no transport delay in the fault-free base).

Schedule and visits. A robot visit is made for every dose tick and every measurement tick. The
arrival is ``tick + delay``, the delay from the jitter model (nonnegative, at most one day),
drawn from the named stream ``(seed, patient, day, JITTER, 2 * index + kind)`` where ``kind``
is 0 for a measurement visit and 1 for a dose visit and ``index`` the position among ticks of
that kind: a visit's delay depends on no other visit. The robot stays ``robot_dwell_ms`` (closed
interval ``[arrival, arrival + dwell]``). One presence sample of value 1.0 is emitted at each
arrival (never a zero: the absence of the robot is not a value, ``#signals`` rule) and one
``ROBOT_TASK`` event (task ``navigate``, outcome ``success``) from source ``robot``. A visit
for a measurement tick makes the reading ``inflation`` later; a keyword argument can mark
measurement ticks the patient refuses (no reading, the robot still comes).

Cuff. For measurement ``k`` (position of its tick in ``schedule.measurement_ticks_ms``, whether
or not it is realised) the generator ``(seed, patient, day, MEASUREMENT, k)`` gives three
standard normals in this fixed order: the cuff error, the inflation duration and the pulse
error; all three are always drawn, so no branch shifts a later measurement and a delayed
measurement keeps its draws. Reading ``= latent(t) + bias + sd * z0`` (Gaussian, family
declared in ``CuffModel.family``; ISO 81060-2 acceptance limits are not a device model, see
the provenance rows). Inflation ``= round(nominal + sd * z1)`` raised to the registry minimum
``cuff_inflation_min`` (an argument of the design): the raised draws are counted in
``settings["n_inflation_raised"]``, so a fault-free day cannot violate the system template by
construction. The reading is stamped ``arrival + inflation``. Pulse ``= heart rate level at that
instant + pulse_sd * z2``; without a heart-rate segment no pulse sample is emitted (no level is
invented).

Streams emitted. Samples: ``bp``, ``inflation_ms``, ``cuff_health`` (1.0), ``hr_pulse`` (all four
of one measurement share its instant), ``presence``, ``hr_ecg`` and ``spo2`` (every
``vitals_period_ms``), ``day_end``. Events: ``SCHEDULE_TICK``, ``ROBOT_TASK``, ``MEASUREMENT``,
``DISPENSE``, ``INTAKE``. The impulses ``meas``, ``dispense``, ``intake`` and ``sched_tick`` are
events only: the monitor derives them with ``event_to_sample``, a duplicate sample would be
counted twice (WS04 README issue I10). The witnessed ``INTAKE`` carries no payload (the event is
the reading, ``evidence-channels.md``); a latent INTAKE becomes an observed one only if a visit
covers it, so a true intake is never copied verbatim and a dose delayed beyond the dwell has
a DISPENSE and no INTAKE. The observed ``DISPENSE`` repeats the latent time with source
``dispenser`` and an empty payload (with ``dispenser_content_sensing`` it carries ``content_change``
``CONTENT_PER_RELEASE``: WS04-T09, the capability that separates a double take from a bounce).
Not emitted here: ``NODE_STATE`` events for the robot
co-location status (needed by the availability mask H-MASK of the evidence conventions),
which WS04-T07 declares in ``vocab.py``; the visits are in ``ObservedStream.visits`` for it.
Fault-free ECG heart rate and SpO2 equal the clean segments: noise enters only through the
C2 fault ``ecg_noise`` (declared simplification), and heart rate is not coupled to pressure.

Order. Samples and events are each sorted by ``t_rx_ms`` with a stable sort, so ties keep the
generation order. Samples: presence (in visit order), cuff messages (in measurement-index
order; within a message ``bp``, ``inflation_ms``, ``cuff_health``, ``hr_pulse``), ``hr_ecg``,
``spo2``, ``day_end``. Events: ``SCHEDULE_TICK`` (in tick order, a dose before a measurement at
the same tick), ``ROBOT_TASK`` (visit order), ``MEASUREMENT`` (index order), ``DISPENSE`` and
``INTAKE`` (latent order).

Sequence numbers. ``assign_device_seq`` gives each cuff message and each dispenser event a
counter that starts at 1 and follows the order of the stream (arrival order, not measurement
index): all four cuff samples of a message and its ``MEASUREMENT`` event share one number,
as in ``docs/models/threat-model.md`` ("(source, name, seq)"), a ``DISPENSE`` has its own
counter; robot, ward, ECG and SpO2 items keep ``seq`` None. A message starts when a cuff
signal repeats within the current one or when the instant changes (WS04-T07: a failed attempt
of the cuff has no ``bp``, so the signal alone would merge its samples with the next
message); a ``MEASUREMENT_MISSED`` event takes the number of the attempt like a
``MEASUREMENT`` event, and a ``DEVICE_ERROR`` of the cuff reported at the instant of that
attempt shares it. The counters can start at another number and the next
ones are recorded in the settings (``next_cuff_seq``, ``next_dispenser_seq``), so that days
chain without a restart that a replay check would flag.

Dispense interval (WS04-T18). ``assign_dispense_intervals`` adds to the payload of each ``DISPENSE`` of the dispenser
``interval_since_previous_ms``, the interval since its previous opening in the stream as the DISPENSER reports it
(an integer of ms, never negative): it is computed on the openings the device made (before the link stage, so a
lost opening still counts for the next one, and a forged opening never does), it is absent on the first opening of
the stream, so also across midnight (a stream is one day), and the ``content_change`` of the payload is untouched.
The injection pipeline calls it after the numbering when the device profile says that the dispenser reports it.

Resource bounds: at most ``MAX_VISITS_PER_DAY`` ticks, ``MAX_VITALS_SAMPLES`` vitals samples per
signal, ``MAX_LATENT_SAMPLES`` latent samples and ``MAX_LATENT_EVENTS`` latent events, all
checked from the lengths before any work; a jitter file has at most ``MAX_JITTER_FILE_BYTES``
bytes and ``MAX_JITTER_DELAYS`` delays. Every public function raises ``MeasurementConfigError``
(or the segment errors of ``ralmon.benchmark.segments``) for an invalid argument and nothing else.
No number here is a clinical parameter: the design values come from
``configs/benchmark/generator_design.yaml`` (rows ``inflation_ms_nominal``, ``inflation_ms_sd``,
``pulse_error_sd_bpm``, ``robot_dwell_ms``, ``vitals_period_ms``) through
``load_measurement_design``.
"""

from __future__ import annotations

import hashlib
import json
import math
import numbers
import os
from bisect import bisect_right
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from itertools import islice
from pathlib import Path
from typing import Any, ClassVar, Final, Protocol, TypeGuard, runtime_checkable

import numpy as np

from ralmon.benchmark.latent import MAX_GRID_POINTS, T_DAY_MS
from ralmon.benchmark.priors import DeviceErrorModel
from ralmon.benchmark.rng import StreamKeyError, StreamPurpose, stream
from ralmon.benchmark.schedule import Schedule, load_filled_rows
from ralmon.benchmark.segments import (
    KIND_HR_CLEAN,
    KIND_SPO2_CLEAN,
    SegmentLibrary,
    SegmentUnavailableError,
)
from ralmon.benchmark.trace import JsonValue, LatentDay
from ralmon.benchmark.vocab import (
    KEY_CONTENT_CHANGE,
    KEY_INTERVAL,
    KEY_KIND,
    KEY_OUTCOME,
    KEY_PATIENT_ID,
    KEY_TASK,
    KIND_DOSE,
    KIND_MEASUREMENT,
    OUTCOME_SUCCESS,
    SOURCE_CUFF,
    SOURCE_DISPENSER,
    SOURCE_ROBOT,
    SOURCE_WARD,
    TASK_NAVIGATE,
)
from ralmon.signals import DurationMs, Event, EventKind, Sample, SignalId, TimeMs

__all__ = [
    "CONTENT_PER_RELEASE",
    "DESIGN_ROWS",
    "MAX_JITTER_DELAYS",
    "MAX_JITTER_FILE_BYTES",
    "MAX_LATENT_EVENTS",
    "MAX_LATENT_SAMPLES",
    "MAX_VISITS_PER_DAY",
    "MAX_VITALS_SAMPLES",
    "ArrivalJitterModel",
    "CleanVitals",
    "CuffModel",
    "EmpiricalJitter",
    "LatentSbpHold",
    "MeasurementConfigError",
    "MeasurementDesign",
    "MeasurementRecord",
    "NoJitter",
    "ObservedStream",
    "RobotVisit",
    "assign_device_seq",
    "assign_dispense_intervals",
    "build_observed_base",
    "draw_clean_vitals",
    "jitter_descriptor",
    "load_measurement_design",
]

# Resource guards of the generator.
MAX_VISITS_PER_DAY: Final[int] = (
    10_000  # algorithmic: ticks (doses plus measurements) of a day
)
MAX_VITALS_SAMPLES: Final[int] = 100_000  # algorithmic: heart-rate samples of a day
MAX_LATENT_SAMPLES: Final[int] = MAX_GRID_POINTS
MAX_LATENT_EVENTS: Final[int] = (
    400_000  # algorithmic: latent events of a day (four per slot)
)
_MIB: Final = 1024 * 1024  # algorithmic: one mebibyte
MAX_JITTER_FILE_BYTES: Final[int] = 4 * _MIB  # algorithmic: jitter file size
MAX_JITTER_DELAYS: Final[int] = 100_000  # algorithmic: delays in a jitter file
_N_NORMALS: Final = 3  # algorithmic: cuff error, inflation, pulse error per measurement
# ``content_change`` of a real release of a dispenser that senses its content: one unit leaves it (the
# unit the dispenser declares is a released-pill counter, so a release is +1 and a bounce is 0).
CONTENT_PER_RELEASE: Final[float] = 1.0
_MAX_TEXT: Final = 256  # algorithmic: longest identifier
_INT64_MAX: Final = int(np.iinfo(np.int64).max)
_INT64_MIN: Final = int(np.iinfo(np.int64).min)

DESIGN_ROWS: Final = (
    "inflation_ms_nominal",
    "inflation_ms_sd",
    "pulse_error_sd_bpm",
    "robot_dwell_ms",
    "vitals_period_ms",
)

_BP: Final = SignalId.BP.value
_INFLATION: Final = SignalId.INFLATION_MS.value
_HEALTH: Final = SignalId.CUFF_HEALTH.value
_PULSE: Final = SignalId.HR_PULSE.value
_HR_ECG: Final = SignalId.HR_ECG.value
_SPO2: Final = SignalId.SPO2.value
_PRESENCE: Final = SignalId.PRESENCE.value
_DAY_END: Final = SignalId.DAY_END.value
_CUFF_SIGNALS: Final = frozenset({_BP, _INFLATION, _HEALTH, _PULSE})
_CUFF_ATTEMPT_EVENTS: Final = frozenset(
    {EventKind.MEASUREMENT, EventKind.MEASUREMENT_MISSED}
)
_VITALS_SUB: Final = {KIND_HR_CLEAN: 0, KIND_SPO2_CLEAN: 1}
_NO_SEGMENTS: Final = "none"
_MAX_SEQ: Final = _INT64_MAX // 2  # algorithmic: room for a counter that keeps growing


class MeasurementConfigError(ValueError):
    """An argument, a design value, a latent day or a jitter file of the measurement process is invalid."""


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _is_integer(x: object) -> TypeGuard[numbers.Integral]:
    return not isinstance(x, (bool, np.bool_)) and isinstance(x, numbers.Integral)


def _int(name: str, x: object, lo: int, hi: int) -> int:
    if not _is_integer(x):
        raise MeasurementConfigError(f"{name} must be an integer")
    value = int(x)
    if not lo <= value <= hi:
        raise MeasurementConfigError(f"{name} must lie in [{lo}, {hi}]")
    return value


def _real(name: str, x: object) -> float:
    if isinstance(x, (bool, np.bool_)) or not isinstance(x, numbers.Real):
        raise MeasurementConfigError(f"{name} must be a finite number")
    try:
        value = float(x)
    except OverflowError as exc:
        raise MeasurementConfigError(f"{name} is too large for a float") from exc
    if not math.isfinite(value):
        raise MeasurementConfigError(f"{name} must be a finite number")
    return value


def _nonneg_real(name: str, x: object, hi: float | None = None) -> float:
    value = _real(name, x)
    if value < 0.0 or (hi is not None and value > hi):
        raise MeasurementConfigError(
            f"{name} must be >= 0" + ("" if hi is None else f" and <= {hi:g}")
        )
    return value


def _text(name: str, x: object) -> str:
    if not isinstance(x, str) or not x.strip() or len(x) > _MAX_TEXT:
        raise MeasurementConfigError(
            f"{name} must be a non-empty string of at most {_MAX_TEXT} characters"
        )
    return x


def _path(name: str, value: object) -> Path:
    if not isinstance(value, (str, os.PathLike)) or isinstance(value, bytes):
        raise MeasurementConfigError(
            f"{name} must be a path, got {type(value).__name__}"
        )
    try:
        text = os.fspath(value)
    except (TypeError, ValueError, OSError) as exc:  # a misbehaving __fspath__
        raise MeasurementConfigError(f"{name} is not a valid path") from exc
    if not isinstance(text, str) or not text or "\0" in text:
        raise MeasurementConfigError(f"{name} is not a valid path")
    return Path(text)


def _key(
    seed: object, patient_index: object, day_index: object
) -> tuple[int, int, int]:
    """Validate the stream key by building one stream; the key as three ints.

    ``rng.stream`` accepts ``None`` as a day (a patient-level stream); the three members must be
    integers here, so each is checked before the stream is built.
    """
    for name, value in (
        ("seed", seed),
        ("patient_index", patient_index),
        ("day_index", day_index),
    ):
        if not _is_integer(value):
            raise MeasurementConfigError(f"{name} must be an integer")
    try:
        stream(seed, patient_index, day_index, StreamPurpose.MEASUREMENT, 0)  # type: ignore[arg-type]
    except StreamKeyError as exc:
        raise MeasurementConfigError(str(exc)) from exc
    return int(seed), int(patient_index), int(day_index)  # type: ignore[call-overload]


def _stream(
    key: tuple[int, int, int], purpose: StreamPurpose, sub_index: int
) -> np.random.Generator:
    try:
        return stream(key[0], key[1], key[2], purpose, sub_index)
    except (
        StreamKeyError
    ) as exc:  # a sub_index beyond 2**32: a schedule can never reach it
        raise MeasurementConfigError(str(exc)) from exc


# ---------------------------------------------------------------------------
# Design
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MeasurementDesign:
    """The design values of the measurement process (none is chosen here).

    ``inflation_ms_nominal`` and ``inflation_ms_sd``: nominal cuff inflation duration and its
    SD, ms; ``pulse_error_sd_bpm``: SD of the cuff pulse-rate error; ``robot_dwell_ms``: how
    long the robot stays after it arrives; ``vitals_period_ms``: period of the ``hr_ecg`` and
    ``spo2`` samples, which must divide the day and give at most ``MAX_VITALS_SAMPLES``
    samples; ``inflation_min_ms``: the registry minimum ``cuff_inflation_min`` that a
    fault-free inflation is raised to (the caller reads it from the registry).
    """

    inflation_ms_nominal: DurationMs
    inflation_ms_sd: float
    pulse_error_sd_bpm: float
    robot_dwell_ms: DurationMs
    vitals_period_ms: DurationMs
    inflation_min_ms: DurationMs

    def __post_init__(self) -> None:
        nominal = _int("inflation_ms_nominal", self.inflation_ms_nominal, 0, T_DAY_MS)
        sd = _nonneg_real("inflation_ms_sd", self.inflation_ms_sd, float(T_DAY_MS))
        pulse = _nonneg_real("pulse_error_sd_bpm", self.pulse_error_sd_bpm)
        dwell = _int("robot_dwell_ms", self.robot_dwell_ms, 0, T_DAY_MS)
        period = _int("vitals_period_ms", self.vitals_period_ms, 1, T_DAY_MS)
        minimum = _int("inflation_min_ms", self.inflation_min_ms, 0, T_DAY_MS)
        if T_DAY_MS % period != 0:
            raise MeasurementConfigError(
                f"vitals_period_ms {period} does not divide the day"
            )
        if T_DAY_MS // period > MAX_VITALS_SAMPLES:
            raise MeasurementConfigError(
                f"vitals_period_ms {period} gives more than {MAX_VITALS_SAMPLES} samples a day"
            )
        for name, value in (
            ("inflation_ms_nominal", nominal),
            ("inflation_ms_sd", sd),
            ("pulse_error_sd_bpm", pulse),
            ("robot_dwell_ms", dwell),
            ("vitals_period_ms", period),
            ("inflation_min_ms", minimum),
        ):
            object.__setattr__(self, name, value)

    @property
    def vitals_points(self) -> int:
        """Number of ``hr_ecg`` (and ``spo2``) samples of a day."""
        return T_DAY_MS // self.vitals_period_ms


def load_measurement_design(
    path: str | os.PathLike[str], *, inflation_min_ms: DurationMs
) -> MeasurementDesign:
    """Read the five design rows of ``generator_design.yaml`` (each must be filled).

    Raises ``UnfilledParameterError`` (naming the rows) while a human has not supplied a
    value, ``PriorConfigError`` for a missing row or file or a malformed row, and
    ``MeasurementConfigError`` for a value that is not valid. ``inflation_min_ms`` is the
    registry entry ``cuff_inflation_min`` read by the caller.
    """
    target = _path("path", path)
    minimum = _int("inflation_min_ms", inflation_min_ms, 0, T_DAY_MS)
    values = load_filled_rows(target, DESIGN_ROWS)
    return MeasurementDesign(
        inflation_ms_nominal=values["inflation_ms_nominal"],
        inflation_ms_sd=values["inflation_ms_sd"],
        pulse_error_sd_bpm=values["pulse_error_sd_bpm"],
        robot_dwell_ms=values["robot_dwell_ms"],
        vitals_period_ms=values["vitals_period_ms"],
        inflation_min_ms=minimum,
    )


# ---------------------------------------------------------------------------
# Arrival jitter
# ---------------------------------------------------------------------------


@runtime_checkable
class ArrivalJitterModel(Protocol):
    """Delay of a robot arrival after its tick.

    ``descriptor`` names the source for the manifest (``none`` or ``file:<sha256>``);
    ``delay_ms`` returns a nonnegative integer number of ms (at most one day) and may use
    only the generator it is given (one named stream per visit); ``kind`` is
    ``vocab.KIND_MEASUREMENT`` or ``vocab.KIND_DOSE`` and ``index`` the position among the
    ticks of that kind.
    """

    descriptor: str

    def delay_ms(
        self, rng: np.random.Generator, *, kind: str, index: int
    ) -> DurationMs: ...


class NoJitter:
    """No arrival delay (the default): the robot arrives at the tick; no random number is drawn."""

    descriptor: str = "none"
    run_source: str | None = None

    def delay_ms(
        self, rng: np.random.Generator, *, kind: str, index: int
    ) -> DurationMs:
        return 0


def _reject_constant(token: str) -> Any:
    raise MeasurementConfigError(f"JSON constant {token} is not allowed")


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    keys = [key for key, _ in pairs]
    if len(set(keys)) != len(keys):
        raise MeasurementConfigError("a JSON object has a duplicate key")
    return dict(pairs)


class EmpiricalJitter:
    """Arrival delays resampled from a file exported by the WS07 simulation.

    The JSON file has ``delays_ms`` (a nonempty list of at most ``MAX_JITTER_DELAYS``
    integers in ``[0, T_day]``) and ``source`` (a non-empty string naming the simulation
    run); further keys are ignored. A delay is drawn uniformly from the list. The file is
    bounded in size and its sha256 is the descriptor ``file:<sha256>``.
    """

    def __init__(self, path: str | os.PathLike[str]) -> None:
        target = _path("jitter path", path)
        try:
            if not target.is_file():
                raise MeasurementConfigError("the jitter file is not a regular file")
            if target.stat().st_size > MAX_JITTER_FILE_BYTES:
                raise MeasurementConfigError(
                    f"the jitter file is larger than {MAX_JITTER_FILE_BYTES} bytes"
                )
            with target.open("rb") as handle:
                data = handle.read(MAX_JITTER_FILE_BYTES + 1)
        except MeasurementConfigError:
            raise
        except (OSError, ValueError) as exc:
            raise MeasurementConfigError(
                f"the jitter file cannot be read: {type(exc).__name__}"
            ) from exc
        if len(data) > MAX_JITTER_FILE_BYTES:
            raise MeasurementConfigError(
                f"the jitter file is larger than {MAX_JITTER_FILE_BYTES} bytes"
            )
        try:
            document = json.loads(
                data.decode("utf-8"),
                parse_constant=_reject_constant,
                object_pairs_hook=_reject_duplicates,
            )
        except MeasurementConfigError:
            raise
        except (
            ValueError,
            RecursionError,
        ) as exc:  # JSONDecodeError, UnicodeDecodeError
            raise MeasurementConfigError(
                f"the jitter file is not valid JSON: {type(exc).__name__}"
            ) from exc
        if (
            not isinstance(document, dict)
            or "delays_ms" not in document
            or "source" not in document
        ):
            raise MeasurementConfigError(
                "the jitter file needs the keys delays_ms and source"
            )
        raw = document["delays_ms"]
        if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_JITTER_DELAYS:
            raise MeasurementConfigError(
                f"delays_ms must be a list of 1 to {MAX_JITTER_DELAYS} integers"
            )
        self.delays_ms: tuple[int, ...] = tuple(
            _int(f"delays_ms[{i}]", d, 0, T_DAY_MS) for i, d in enumerate(raw)
        )
        self.run_source: str = _text("source", document["source"])
        self.file_sha256: str = hashlib.sha256(data).hexdigest()
        self.descriptor: str = "file:" + self.file_sha256

    def delay_ms(
        self, rng: np.random.Generator, *, kind: str, index: int
    ) -> DurationMs:
        return self.delays_ms[int(rng.integers(0, len(self.delays_ms)))]


def jitter_descriptor(model: ArrivalJitterModel) -> str:
    """The source descriptor of a jitter model for the manifest (``none`` or ``file:<sha256>``)."""
    descriptor = getattr(model, "descriptor", None)
    return _text("jitter descriptor", descriptor)


def _check_jitter(model: object) -> str:
    if not callable(getattr(model, "delay_ms", None)):
        raise MeasurementConfigError("jitter must have a delay_ms method")
    return _text("jitter descriptor", getattr(model, "descriptor", None))


def _jitter_delay(
    model: ArrivalJitterModel, key: tuple[int, int, int], kind: str, index: int
) -> int:
    if type(model) is NoJitter:
        return 0
    rng = _stream(
        key, StreamPurpose.JITTER, 2 * index + (0 if kind == KIND_MEASUREMENT else 1)
    )
    return _int(
        "the delay of the jitter model",
        model.delay_ms(rng, kind=kind, index=index),
        0,
        T_DAY_MS,
    )


# ---------------------------------------------------------------------------
# Cuff model
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CuffModel:
    """Gaussian cuff error: ``reading = latent + bias + sd * z`` with ``z`` standard normal.

    The family is declared (``family``); the bias and the SD are the ``DeviceErrorModel``
    fields (WS04-T02 priors, unverified until a human fills them).
    """

    bias_mmhg: float
    sd_mmhg: float
    family: ClassVar[str] = "gaussian"

    def __post_init__(self) -> None:
        object.__setattr__(self, "bias_mmhg", _real("bias_mmhg", self.bias_mmhg))
        object.__setattr__(self, "sd_mmhg", _nonneg_real("sd_mmhg", self.sd_mmhg))

    @classmethod
    def from_device_errors(cls, errors: object) -> CuffModel:
        if not isinstance(errors, DeviceErrorModel):
            raise MeasurementConfigError("device_errors must be a DeviceErrorModel")
        return cls(errors.cuff_bias_mmhg, errors.cuff_error_sd_mmhg)

    def error(self, z: float) -> float:
        """``bias + sd * z`` for a standard normal draw ``z``."""
        value = self.bias_mmhg + self.sd_mmhg * _real("z", z)
        if not math.isfinite(value):
            raise MeasurementConfigError("the cuff error is not finite")
        return value

    def reading(self, latent_mmhg: float, z: float) -> float:
        """The reported pressure for a latent pressure and a draw ``z``."""
        value = _real("latent_mmhg", latent_mmhg) + self.error(z)
        if not math.isfinite(value):
            raise MeasurementConfigError("the cuff reading is not finite")
        return value


# ---------------------------------------------------------------------------
# Latent pressure hold
# ---------------------------------------------------------------------------


class LatentSbpHold:
    """Piecewise-constant hold of the latent ``bp`` samples of a latent day (module docstring)."""

    def __init__(self, samples: object) -> None:
        if isinstance(samples, (str, bytes)) or not isinstance(samples, Sequence):
            raise MeasurementConfigError(
                "the latent samples must be a sequence of Sample"
            )
        if len(samples) > MAX_LATENT_SAMPLES:
            raise MeasurementConfigError(
                f"a latent day holds at most {MAX_LATENT_SAMPLES} samples"
            )
        times: list[int] = []
        values: list[float] = []
        for sample in samples:
            if not isinstance(sample, Sample):
                raise MeasurementConfigError("every latent sample must be a Sample")
            if sample.signal != _BP:
                continue
            t = _int(
                "latent bp t_device_ms", sample.t_device_ms, _INT64_MIN, _INT64_MAX
            )
            if times and t <= times[-1]:
                raise MeasurementConfigError(
                    "latent bp samples must have strictly increasing times"
                )
            times.append(t)
            values.append(_real("latent bp value", sample.value))
        if not times:
            raise MeasurementConfigError("the latent day has no bp sample")
        self._times = times
        self._values = values

    @property
    def first_t_ms(self) -> TimeMs:
        return self._times[0]

    @property
    def last_t_ms(self) -> TimeMs:
        return self._times[-1]

    def at(self, t_ms: TimeMs) -> float:
        """The value of the last grid point at or before ``t_ms``.

        Raises ``MeasurementConfigError`` before the first grid point (undefined) and for a
        time that is not an int64 integer; after the last point the last value is held.
        """
        t = _int("t_ms", t_ms, _INT64_MIN, _INT64_MAX)
        position = bisect_right(self._times, t) - 1
        if position < 0:
            raise MeasurementConfigError(
                f"instant {t} is before the first latent grid point {self._times[0]}"
            )
        return self._values[position]


# ---------------------------------------------------------------------------
# Clean vitals from segments
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CleanVitals:
    """Clean heart rate and SpO2 of one day on the vitals grid, with their provenance.

    ``hr_bpm`` and ``spo2_pct`` are ``None`` when the library has no segment of that kind and
    the caller allowed it. ``segment_ids`` and ``join_count`` are keyed by segment kind.
    """

    hr_bpm: tuple[float, ...] | None
    spo2_pct: tuple[float, ...] | None
    segment_ids: Mapping[str, tuple[str, ...]]
    join_count: Mapping[str, int]


def draw_clean_vitals(
    library: SegmentLibrary,
    design: MeasurementDesign,
    seed: int,
    patient_index: int,
    day_index: int,
    *,
    allow_missing: bool = False,
) -> CleanVitals:
    """The clean heart rate and SpO2 of one patient-day: a pure function of the stream key.

    Draws from ``(seed, patient, day, SEGMENTS, k)`` with ``k`` 0 for heart rate and 1 for
    SpO2, so the latent assembly (WS04-T09) and the observed base see the same values. The
    segment of period ``P`` is held to the vitals grid: grid point ``j`` takes segment sample
    ``(j * vitals_period) // P``. Raises ``SegmentUnavailableError`` for a missing kind unless
    ``allow_missing``.
    """
    if not isinstance(library, SegmentLibrary):
        raise MeasurementConfigError("library must be a SegmentLibrary")
    if not isinstance(design, MeasurementDesign):
        raise MeasurementConfigError("design must be a MeasurementDesign")
    if not isinstance(allow_missing, bool):
        raise MeasurementConfigError("allow_missing must be a bool")
    key = _key(seed, patient_index, day_index)
    grids: dict[str, tuple[float, ...] | None] = {}
    ids: dict[str, tuple[str, ...]] = {}
    joins: dict[str, int] = {}
    points, step = design.vitals_points, design.vitals_period_ms
    for kind, sub in _VITALS_SUB.items():
        if not library.has_kind(kind):
            if not allow_missing:
                raise SegmentUnavailableError(
                    f"the library has no segment of kind {kind!r}"
                )
            grids[kind], ids[kind], joins[kind] = None, (), 0
            continue
        period = library.sample_period_ms(kind)
        need = ((points - 1) * step) // period + 1
        drawn = library.draw(kind, need, _stream(key, StreamPurpose.SEGMENTS, sub))
        grids[kind] = tuple(drawn.values[(j * step) // period] for j in range(points))
        ids[kind], joins[kind] = drawn.segment_ids, drawn.join_count
    return CleanVitals(grids[KIND_HR_CLEAN], grids[KIND_SPO2_CLEAN], ids, joins)


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RobotVisit:
    """One robot visit: ``kind`` is ``vocab.KIND_MEASUREMENT`` or ``vocab.KIND_DOSE``.

    ``index`` is the position among the ticks of that kind; times are on the continuing axis.
    """

    index: int
    kind: str
    tick_ms: TimeMs
    arrival_ms: TimeMs
    departure_ms: TimeMs
    delay_ms: DurationMs


@dataclass(frozen=True, slots=True)
class MeasurementRecord:
    """Generator-side record of one realised reading (not part of the observed trace).

    ``latent_sbp_mmhg`` is latent information kept for the injectors and the labeller; it is
    never written into an observed file.
    """

    index: int
    tick_ms: TimeMs
    arrival_ms: TimeMs
    t_ms: TimeMs
    latent_sbp_mmhg: float
    error_mmhg: float
    value_mmhg: float
    inflation_ms: DurationMs
    inflation_raised: bool
    pulse_bpm: float | None


@dataclass(frozen=True, slots=True)
class ObservedStream:
    """The fault-free observed base of one patient-day, before injection.

    ``samples`` and ``events`` are sorted by ``t_rx_ms``; ``visits`` (in tick order) and
    ``measurements`` (in index order) are generator-side records for the injectors;
    ``settings`` is a JSON-native mapping for the manifest. The last three fields default to
    empty so that a hand-written stream (an injector test) need not give them.
    """

    patient_id: str
    day_index: int
    seed: int
    care_plan_id: str
    samples: tuple[Sample, ...]
    events: tuple[Event, ...]
    visits: tuple[RobotVisit, ...] = ()
    measurements: tuple[MeasurementRecord, ...] = ()
    settings: Mapping[str, JsonValue] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Building the base stream
# ---------------------------------------------------------------------------


def _latent_identity(latent: object) -> tuple[str, int]:
    if not isinstance(latent, LatentDay):
        raise MeasurementConfigError("latent must be a LatentDay")
    patient_id = _text("latent patient_id", latent.patient_id)
    day_index = _int(
        "latent day_index", latent.day_index, 0, _INT64_MAX // T_DAY_MS - 1
    )
    return patient_id, day_index


def _latent_times(latent: LatentDay) -> tuple[list[int], list[int]]:
    """Times of the latent ``DISPENSE`` and ``INTAKE`` events (nothing else is read)."""
    events = latent.events
    if isinstance(events, (str, bytes)) or not isinstance(events, Sequence):
        raise MeasurementConfigError("the latent events must be a sequence of Event")
    if len(events) > MAX_LATENT_EVENTS:
        raise MeasurementConfigError(
            f"a latent day holds at most {MAX_LATENT_EVENTS} events"
        )
    dispenses: list[int] = []
    intakes: list[int] = []
    for event in events:
        if not isinstance(event, Event) or not isinstance(event.kind, EventKind):
            raise MeasurementConfigError(
                "every latent event must be an Event with an EventKind"
            )
        if event.kind is EventKind.DISPENSE:
            dispenses.append(
                _int("latent DISPENSE time", event.t_device_ms, _INT64_MIN, _INT64_MAX)
            )
        elif event.kind is EventKind.INTAKE:
            intakes.append(
                _int("latent INTAKE time", event.t_device_ms, _INT64_MIN, _INT64_MAX)
            )
    return dispenses, intakes


def _skip_indices(skip: object, schedule: Schedule) -> frozenset[int]:
    if isinstance(skip, (str, bytes)) or not isinstance(skip, Iterable):
        raise MeasurementConfigError(
            "skip_measurement_ticks_ms must be a collection of ticks"
        )
    position = {t: k for k, t in enumerate(schedule.measurement_ticks_ms)}
    chosen: set[int] = set()
    try:
        values = list(islice(skip, MAX_VISITS_PER_DAY + 1))
    except TypeError as exc:  # e.g. a zero-dimensional array is Iterable by type only
        raise MeasurementConfigError(
            "skip_measurement_ticks_ms must be a collection of ticks"
        ) from exc
    if len(values) > MAX_VISITS_PER_DAY:
        raise MeasurementConfigError(
            f"skip_measurement_ticks_ms has more than {MAX_VISITS_PER_DAY} entries"
        )
    for value in values:
        tick = _int("a skipped tick", value, _INT64_MIN, _INT64_MAX)
        if tick not in position:
            raise MeasurementConfigError(
                f"tick {tick} is not a measurement tick of the schedule"
            )
        chosen.add(position[tick])
    return frozenset(chosen)


def _sample(signal: str, t: int, value: float) -> Sample:
    return Sample(signal, t, t, value, None, None)


def _event(
    kind: EventKind, t: int, source: str, payload: dict[str, float | int | str | bool]
) -> Event:
    return Event(kind, t, t, source, payload, None)


def build_observed_base(
    latent: LatentDay,
    schedule: Schedule,
    care_plan_id: str,
    device_errors: DeviceErrorModel,
    design: MeasurementDesign,
    jitter: ArrivalJitterModel,
    library: SegmentLibrary,
    seed: int,
    patient_index: int,
    *,
    allow_no_segments: bool = False,
    skip_measurement_ticks_ms: Iterable[int] = (),
    dispenser_content_sensing: bool = False,
) -> ObservedStream:
    """The fault-free observed stream of one latent day (module docstring).

    ``dispenser_content_sensing`` (WS04-T09, default False: the stream is then exactly as before)
    says that the dispenser senses its content: every observed ``DISPENSE`` then carries
    ``content_change`` ``CONTENT_PER_RELEASE`` (a real release; the extra dispense of a bounce reports
    0.0, see ``inject_c2``). It is the capability that separates a double take from a bounce.

    ``skip_measurement_ticks_ms`` lists measurement ticks (clock time in the schedule) that
    the patient refuses: the robot visits, no reading is made, and no draw of any other
    measurement changes. ``allow_no_segments`` lets a library without a heart-rate or SpO2
    segment produce a stream without that signal (and without ``hr_pulse`` when heart rate
    is missing); otherwise a missing kind raises ``SegmentUnavailableError``.
    """
    patient_id, day_index = _latent_identity(latent)
    if not isinstance(schedule, Schedule):
        raise MeasurementConfigError("schedule must be a Schedule")
    plan_id = _text("care_plan_id", care_plan_id)
    cuff = CuffModel.from_device_errors(device_errors)
    if not isinstance(design, MeasurementDesign):
        raise MeasurementConfigError("design must be a MeasurementDesign")
    jitter_source = _check_jitter(jitter)
    if not isinstance(library, SegmentLibrary):
        raise MeasurementConfigError("library must be a SegmentLibrary")
    if not isinstance(allow_no_segments, bool):
        raise MeasurementConfigError("allow_no_segments must be a bool")
    if not isinstance(dispenser_content_sensing, bool):
        raise MeasurementConfigError("dispenser_content_sensing must be a bool")
    key = _key(seed, patient_index, day_index)
    if not _is_integer(latent.seed) or int(latent.seed) != key[0]:
        raise MeasurementConfigError(
            "seed must equal the seed of the latent day (one seed per benchmark)"
        )
    doses, ticks = schedule.dose_ticks_ms, schedule.measurement_ticks_ms
    if len(doses) + len(ticks) > MAX_VISITS_PER_DAY:
        raise MeasurementConfigError(f"a day has at most {MAX_VISITS_PER_DAY} ticks")
    skipped = _skip_indices(skip_measurement_ticks_ms, schedule)
    hold = LatentSbpHold(latent.samples)
    latent_dispenses, latent_intakes = _latent_times(latent)
    vitals = draw_clean_vitals(
        library, design, key[0], key[1], key[2], allow_missing=allow_no_segments
    )

    start = day_index * T_DAY_MS
    # visits: dose before measurement at the same tick
    order = sorted(
        [(t, 0, j) for j, t in enumerate(doses)]
        + [(t, 1, k) for k, t in enumerate(ticks)]
    )
    visits: list[RobotVisit] = []
    measurement_visit: dict[int, RobotVisit] = {}
    for tick, rank, index in order:
        kind = KIND_DOSE if rank == 0 else KIND_MEASUREMENT
        delay = _jitter_delay(jitter, key, kind, index)
        arrival = start + tick + delay
        visit = RobotVisit(
            index, kind, start + tick, arrival, arrival + design.robot_dwell_ms, delay
        )
        visits.append(visit)
        if rank == 1:
            measurement_visit[index] = visit

    records: list[MeasurementRecord] = []
    samples: list[Sample] = [_sample(_PRESENCE, v.arrival_ms, 1.0) for v in visits]
    n_past_end = 0
    for k in range(len(ticks)):
        if k in skipped:
            continue
        visit = measurement_visit[k]
        z = _stream(key, StreamPurpose.MEASUREMENT, k).standard_normal(_N_NORMALS)
        raw = round(design.inflation_ms_nominal + design.inflation_ms_sd * float(z[1]))
        inflation = max(raw, design.inflation_min_ms)
        t_meas = visit.arrival_ms + inflation
        latent_value = hold.at(t_meas)
        n_past_end += t_meas > (day_index + 1) * T_DAY_MS
        error = cuff.error(float(z[0]))
        value = cuff.reading(latent_value, float(z[0]))
        pulse: float | None = None
        if vitals.hr_bpm is not None:
            j = min(
                max((t_meas - start) // design.vitals_period_ms, 0),
                design.vitals_points - 1,
            )
            pulse = _real(
                "the pulse reading",
                vitals.hr_bpm[j] + design.pulse_error_sd_bpm * float(z[2]),
            )
        records.append(
            MeasurementRecord(
                k, visit.tick_ms, visit.arrival_ms, t_meas, latent_value, error, value,
                inflation, raw < design.inflation_min_ms, pulse,
            )
        )  # fmt: skip
        samples.append(_sample(_BP, t_meas, value))
        samples.append(_sample(_INFLATION, t_meas, float(inflation)))
        samples.append(_sample(_HEALTH, t_meas, 1.0))
        if pulse is not None:
            samples.append(_sample(_PULSE, t_meas, pulse))
    for name, grid in ((_HR_ECG, vitals.hr_bpm), (_SPO2, vitals.spo2_pct)):
        if grid is not None:
            samples.extend(
                _sample(name, start + j * design.vitals_period_ms, v)
                for j, v in enumerate(grid)
            )
    samples.append(_sample(_DAY_END, (day_index + 1) * T_DAY_MS, 1.0))

    events: list[Event] = []
    for visit in visits:
        kind = visit.kind
        events.append(
            _event(
                EventKind.SCHEDULE_TICK, visit.tick_ms, SOURCE_WARD, {KEY_KIND: kind}
            )
        )
    for visit in visits:
        events.append(
            _event(
                EventKind.ROBOT_TASK, visit.arrival_ms, SOURCE_ROBOT,
                {KEY_TASK: TASK_NAVIGATE, KEY_OUTCOME: OUTCOME_SUCCESS, KEY_PATIENT_ID: patient_id},
            )
        )  # fmt: skip
    events.extend(
        _event(EventKind.MEASUREMENT, r.t_ms, SOURCE_CUFF, {}) for r in records
    )
    events.extend(
        _event(
            EventKind.DISPENSE,
            t,
            SOURCE_DISPENSER,
            {KEY_CONTENT_CHANGE: CONTENT_PER_RELEASE}
            if dispenser_content_sensing
            else {},
        )
        for t in latent_dispenses
    )
    arrivals = sorted(v.arrival_ms for v in visits)
    for t in latent_intakes:
        position = bisect_right(arrivals, t)
        if position > 0 and arrivals[position - 1] >= t - design.robot_dwell_ms:
            events.append(_event(EventKind.INTAKE, t, SOURCE_ROBOT, {}))

    used = [k for k, g in (
        (KIND_HR_CLEAN, vitals.hr_bpm), (KIND_SPO2_CLEAN, vitals.spo2_pct)
    ) if g is not None]  # fmt: skip
    run_source = getattr(jitter, "run_source", None)
    settings: dict[str, Any] = {
        "jitter_source": jitter_source,
        "jitter_run_source": run_source if isinstance(run_source, str) else None,
        "segment_source": library.descriptor if used else _NO_SEGMENTS,
        "segment_ids": {k: list(v) for k, v in vitals.segment_ids.items()},
        "join_count": dict(vitals.join_count),
        "cuff_error_family": CuffModel.family,
        "n_inflation_raised": sum(r.inflation_raised for r in records),
        "n_measurements": len(records),
        "n_visits": len(visits),
        "skipped_measurement_indices": sorted(skipped),
        "n_measurements_after_day_end": n_past_end,
        "dispenser_content_sensing": dispenser_content_sensing,
    }
    return ObservedStream(
        patient_id=patient_id,
        day_index=day_index,
        seed=key[0],
        care_plan_id=plan_id,
        samples=tuple(sorted(samples, key=_by_rx)),
        events=tuple(sorted(events, key=_by_rx)),
        visits=tuple(visits),
        measurements=tuple(records),
        settings=settings,
    )


def _by_rx(item: Sample | Event) -> int:
    return item.t_rx_ms


# ---------------------------------------------------------------------------
# Device sequence numbers
# ---------------------------------------------------------------------------


def assign_device_seq(
    stream_: ObservedStream, *, cuff_start: int = 1, dispenser_start: int = 1
) -> ObservedStream:
    """A copy of ``stream_`` whose cuff messages and dispenser events carry their own counter.

    Counters follow the order of the stream (module docstring): the four cuff samples of one
    message and its ``MEASUREMENT`` event share a number, each ``DISPENSE`` has the next number
    of the dispenser; every other item keeps its ``seq``. The cuff counter starts at
    ``cuff_start`` and the dispenser counter at ``dispenser_start`` (both 1 by default); to
    chain days pass the ``next_cuff_seq`` and ``next_dispenser_seq`` of the settings of the
    previous day's result, which this function records: a counter that restarts at 1 every
    day would look like a replay to a monitor that keeps the accepted ``(source, name, seq)``
    of the previous day. Applying it twice gives the same stream.
    """
    if not isinstance(stream_, ObservedStream):
        raise MeasurementConfigError("stream_ must be an ObservedStream")
    first_cuff = _int("cuff_start", cuff_start, 1, _MAX_SEQ)
    first_dispense = _int("dispenser_start", dispenser_start, 1, _MAX_SEQ)
    for what, members in (("samples", stream_.samples), ("events", stream_.events)):
        if isinstance(members, (str, bytes)) or not isinstance(members, Sequence):
            raise MeasurementConfigError(f"the {what} of the stream must be a sequence")
    old_settings = stream_.settings
    if not isinstance(old_settings, Mapping) or not all(
        isinstance(key, str) for key in old_settings
    ):
        raise MeasurementConfigError(
            "the settings of the stream must be a mapping with string keys"
        )
    samples: list[Sample] = []
    message = first_cuff - 1
    started = False
    message_t: object = None
    present: set[str] = set()
    for sample in stream_.samples:
        if not isinstance(sample, Sample):
            raise MeasurementConfigError("every sample must be a Sample")
        if not isinstance(sample.signal, str):
            raise MeasurementConfigError("every sample needs a signal name")
        if sample.signal in _CUFF_SIGNALS:
            if (
                not started
                or sample.signal in present
                or sample.t_device_ms != message_t
            ):
                message += 1
                started = True
                present = set()
                message_t = sample.t_device_ms
            present.add(sample.signal)
            sample = replace(sample, seq=message)
        samples.append(sample)
    events: list[Event] = []
    attempts = first_cuff - 1  # one counter for MEASUREMENT and MEASUREMENT_MISSED
    last_attempt: tuple[object, int] | None = None
    unmatched: list[
        int
    ] = []  # missed attempts of one instant still waiting for their error
    unmatched_t: object = None
    dispenses = first_dispense - 1
    for event in stream_.events:
        if not isinstance(event, Event):
            raise MeasurementConfigError("every event must be an Event")
        if not isinstance(event.kind, EventKind):
            raise MeasurementConfigError("every event needs an EventKind")
        if event.kind in _CUFF_ATTEMPT_EVENTS:
            attempts += 1
            last_attempt = (event.t_device_ms, attempts)
            if event.kind is EventKind.MEASUREMENT_MISSED:
                if event.t_device_ms != unmatched_t:
                    unmatched, unmatched_t = [], event.t_device_ms
                unmatched.append(attempts)
            event = replace(event, seq=attempts)
        elif event.kind is EventKind.DISPENSE:
            dispenses += 1
            event = replace(event, seq=dispenses)
        elif (
            event.kind is EventKind.DEVICE_ERROR
            and event.source == SOURCE_CUFF
            and last_attempt is not None
            and event.t_device_ms == last_attempt[0]
        ):
            # the n-th error of an instant belongs to the n-th missed attempt of that instant: two
            # attempts at one instant (a delayed visit landing on another) keep distinct numbers
            if unmatched and event.t_device_ms == unmatched_t:
                event = replace(event, seq=unmatched.pop(0))
            else:
                event = replace(event, seq=last_attempt[1])
        events.append(event)
    settings = dict(old_settings)
    settings["next_cuff_seq"] = max(message, attempts) + 1
    settings["next_dispenser_seq"] = dispenses + 1
    return replace(
        stream_,
        samples=tuple(samples),
        events=tuple(events),
        settings=settings,
    )


def assign_dispense_intervals(stream_: ObservedStream) -> ObservedStream:
    """A copy of ``stream_`` whose ``DISPENSE`` events of the dispenser carry ``interval_since_previous_ms``.

    The openings are taken in order of ``t_device_ms`` (a tie keeps the order of the stream); each one but the first
    gets the integer interval since the previous one, and the first has none (the first opening of a stream, so
    also across midnight). Other payload keys (``content_change``) are kept. Applying it twice gives the same stream.
    """
    if not isinstance(stream_, ObservedStream):
        raise MeasurementConfigError("stream_ must be an ObservedStream")
    events = list(stream_.events)
    openings = sorted(
        (
            i
            for i, e in enumerate(events)
            if isinstance(e, Event)
            and e.kind is EventKind.DISPENSE
            and e.source == SOURCE_DISPENSER
        ),
        key=lambda i: (events[i].t_device_ms, i),
    )
    previous: int | None = None
    for i in openings:
        event = events[i]
        payload: dict[str, Any] = {
            k: v for k, v in event.payload.items() if k != KEY_INTERVAL
        }
        if previous is not None:
            payload[KEY_INTERVAL] = int(event.t_device_ms) - previous
        events[i] = replace(event, payload=payload)
        previous = int(event.t_device_ms)
    return replace(stream_, events=tuple(events))
