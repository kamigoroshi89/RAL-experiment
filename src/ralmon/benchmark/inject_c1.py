"""C1 injection: physiological and behavioural deviations of the LATENT day (WS04-T09).

A C1 event is a violation of the care-plan specification phi_CP by the patient's own trace
(analisi section 5.1 item 3: hypertensive spikes, drug non-response, hypotension below the hold
parameter, a refusal of the measurement). Unlike the C2 and C3 injectors of ``inject_c2`` and
``inject_c3``, which corrupt the observed stream, a C1 injection changes the **latent day**: the
latent pressure, the true intakes or the latent measurements. What the monitor sees follows from
the latent day through the measurement process (WS04-T06). Two consequences are the rules of this
module.

* **Records, never ground truth.** Every injector returns ``InjectionRecord`` values (class C1)
  that say what was done. Whether a C1 injection is a true C1 event is decided by the labeller
  (WS04-T10), which evaluates phi_CP on the latent trace: a spike that keeps every scheduled
  measurement inside the band is in the log and not in the ground truth (README, section "Ground
  truth definition"). Nothing in this module constructs a ground-truth event or reads one.
* **No clinical constant.** A magnitude is a **level times a named reference quantity** that the
  caller resolves: ``scale_range`` of the registry for the pressure pulses
  (``REFERENCE_SCALE_RANGE``), the distance between the patient's baseline and the registry entry
  ``bp_hold_threshold`` for the hypotension (``REFERENCE_HOLD_DISTANCE``, ``hold_distance_mmhg``),
  and the dimensionless Emax scale itself for the non-response (an absolute level, the reference
  being the unscaled effect, 1). The levels are rows of ``configs/benchmark/injections.yaml``
  (section ``injections.c1``), design proposals awaiting a human value; ``c1_spec_from_level``
  turns a level and a reference value into a spec.

Subtypes (``C1_SUBTYPES``; the first four are those of the task, the fifth is the forced double
take that the confounder pair of WS04-T09 needs):

``hypertensive_spike``     a window ``[onset, onset + duration)`` in which ``magnitude`` mmHg (> 0)
                           is added to the latent pressure at every grid point;
``hypotension_below_hold`` the same with the magnitude subtracted;
``drug_nonresponse``       a window in which the Emax of every true intake whose time lies in it is
                           scaled by ``magnitude`` in ``[0, 1]`` (0 is a complete non-response; the
                           drug of that intake still occupies the saturation term, ADR-039);
``measurement_refusal``    the patient refuses the measurement of the schedule tick ``onset``: the
                           latent MEASUREMENT event is absent, the robot still visits and the robot
                           task is ``declined`` (``observe_refusals``);
``double_take``            the dose whose tick is ``onset`` is a double take: the chain of the
                           adherence model is forced into that state for that slot (WS04-T05 gap:
                           it has no forcing hook, so ``latent_day`` composes the forced slot from
                           the public API).

Windows are half open, ``[onset, onset + duration)``, on the integer-ms grid of the latent day
(``docs/models/fault-model.md``, boundary convention): a grid point at the onset is inside, one at
the end is outside. A window must lie inside the day of its onset (a spec that crosses midnight, a
negative duration or onset is refused with ``C1InjectionError``). Two windows of one subtype must
not overlap (touching windows are allowed); windows of different subtypes may overlap and add up
(spikes first, then hypotensions, so the sum is a function of the specs and not of their order).

An injection that changes nothing (no grid point in the window, no intake in the window, a scale of
1, a tick that is not a measurement tick of the day) is logged with ``realised`` False and
``n_changed`` 0. A forced ``double_take`` is always realised: the record is what explains the
latent double take (the labeller reads it), even if the chain would have drawn the same state.

Determinism. The injectors are deterministic functions of the specs: they draw no random number.
``c1_stream`` is the named stream ``(seed, patient, day, INJECTION_C1, digest of the injection)``
for any future randomised C1 subtype (and for the plan of WS04-T11), keyed like the C2 streams, so
adding or removing an injection never shifts another draw. The latent day is only changed through
``LatentWork``, the working copy that ``latent_day`` hands to the injectors.

Resource bounds: at most ``MAX_C1_SPECS`` specs per call and ``MAX_WORK_INTAKES`` intakes per
work, checked before any loop. Every public function raises ``C1InjectionError`` (a subclass of
``InjectionError``) or the design errors of ``ralmon.benchmark.injection`` for an invalid argument
and nothing else.
"""

from __future__ import annotations

import dataclasses
import itertools
import math
import numbers
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, TypeGuard, TypeVar

import numpy as np
import numpy.typing as npt

from ralmon.benchmark import vocab
from ralmon.benchmark.injection import (
    InjectionDesignError,
    InjectionError,
    InjectionRecord,
    InjectionSpec,
    LevelRow,
    SubtypeDesign,
    injection_sub_index,
    load_injection_design,
    resolve_magnitude,
)
from ralmon.benchmark.latent import MAX_GRID_POINTS, T_DAY_MS
from ralmon.benchmark.measurement import ObservedStream
from ralmon.benchmark.rng import StreamKeyError, StreamPurpose, stream
from ralmon.benchmark.trace import InjectedClass
from ralmon.signals import Event, EventKind

__all__ = [
    "C1_SUBTYPES",
    "DOUBLE_TAKE",
    "HYPOTENSION",
    "MAX_C1_SPECS",
    "MAX_WORK_INTAKES",
    "NONRESPONSE",
    "REFERENCE_HOLD_DISTANCE",
    "REFERENCE_SCALE_RANGE",
    "REFUSAL",
    "SPIKE",
    "UNIT_MMHG",
    "UNIT_SCALE",
    "C1InjectionError",
    "LatentWork",
    "c1_spec",
    "c1_spec_from_level",
    "c1_stream",
    "canonical_c1_order",
    "check_c1_specs",
    "double_take",
    "drug_nonresponse",
    "hold_distance_mmhg",
    "hypertensive_spike",
    "hypotension_below_hold",
    "load_c1_design",
    "measurement_refusal",
    "observe_refusals",
    "resolve_c1_magnitude",
]

SPIKE: Final = "hypertensive_spike"
NONRESPONSE: Final = "drug_nonresponse"
HYPOTENSION: Final = "hypotension_below_hold"
REFUSAL: Final = "measurement_refusal"
DOUBLE_TAKE: Final = "double_take"
C1_SUBTYPES: Final = (SPIKE, NONRESPONSE, HYPOTENSION, REFUSAL, DOUBLE_TAKE)

UNIT_MMHG: Final = "mmHg"
UNIT_SCALE: Final = "1"  # the dimensionless Emax scale
REFERENCE_SCALE_RANGE: Final = "scale_range"  # registry entry, mmHg
REFERENCE_HOLD_DISTANCE: Final = (
    "baseline_to_hold_distance"  # baseline minus bp_hold_threshold
)

# Resource guards of the generator.
MAX_C1_SPECS: Final[int] = 10_000  # algorithmic: C1 specs of one call
MAX_WORK_INTAKES: Final[int] = 10_000  # algorithmic: intakes held by one working copy
_REL_TOL: Final = (
    1e-12  # algorithmic: consistency of magnitude = multiple * reference value
)
_MAX_TEXT: Final = 256  # algorithmic: longest identifier or label
_MIN_REFERENCE: Final = 0.0  # a reference quantity must lie strictly above this
_DOUBLE_TAKE_EVENTS: Final = (
    4  # algorithmic: two DISPENSE and two INTAKE events of the slot
)
_PARAM_KEYS: Final = ("reference", "multiple", "reference_value")
_HEADROOM: Final = 4  # algorithmic: a time is at most a quarter of the int64 range
_TIME_LIMIT: Final = int(np.iinfo(np.int64).max) // _HEADROOM
_SEED_LIMIT: Final = 1 << 64  # algorithmic: the root seed of rng.stream is below 2**64
_WORD_LIMIT: Final = 1 << 32  # algorithmic: a stream key entry is below 2**32

_T = TypeVar("_T")

_MMHG_REFERENCES: Final = {
    SPIKE: REFERENCE_SCALE_RANGE,
    HYPOTENSION: REFERENCE_HOLD_DISTANCE,
}


class C1InjectionError(InjectionError):
    """A C1 spec, level, working copy or design file is invalid."""


@dataclass(frozen=True, slots=True)
class _Shape:
    window: bool  # a window with a duration (else a per-tick or per-slot point)
    unit: str | None  # unit of the magnitude, None when there is none
    scale: bool  # the magnitude is a scale in [0, 1] (else a positive pressure)


_SHAPES: Final[Mapping[str, _Shape]] = {
    SPIKE: _Shape(True, UNIT_MMHG, False),
    NONRESPONSE: _Shape(True, UNIT_SCALE, True),
    HYPOTENSION: _Shape(True, UNIT_MMHG, False),
    REFUSAL: _Shape(False, None, False),
    DOUBLE_TAKE: _Shape(False, None, False),
}


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _is_integer(x: object) -> TypeGuard[numbers.Integral]:
    return not isinstance(x, (bool, np.bool_)) and isinstance(x, numbers.Integral)


def _int(name: str, x: object, lo: int, hi: int) -> int:
    if not _is_integer(x):
        raise C1InjectionError(f"{name} must be an integer")
    try:
        value = int(x)
    except Exception as exc:  # a number type whose conversion misbehaves
        raise C1InjectionError(f"{name} is not an integer") from exc
    if not lo <= value <= hi:
        raise C1InjectionError(f"{name} must lie in [{lo}, {hi}]")
    return value


def _real(name: str, x: object) -> float:
    if isinstance(x, (bool, np.bool_)) or not isinstance(x, numbers.Real):
        raise C1InjectionError(f"{name} must be a finite number")
    try:
        value = float(x)
    except Exception as exc:  # too large, or a number type whose conversion misbehaves
        raise C1InjectionError(f"{name} is not a finite number") from exc
    if not math.isfinite(value):
        raise C1InjectionError(f"{name} must be a finite number")
    return value


def _plain(x: _T) -> _T:
    """A ``str`` subclass copied to an exact ``str`` (anything else is returned as it is).

    A subclass may override its hash, equality, truth value, length or repr and raise from them
    (review F5); the copy is read by the validation and stored in its place, so none of those is
    ever called.
    """
    return str.__str__(x) if isinstance(x, str) else x  # type: ignore[return-value]


def _text(name: str, x: object) -> str:
    if not isinstance(x, str):
        raise C1InjectionError(
            f"{name} must be a non-empty string of at most {_MAX_TEXT} characters"
        )
    plain = str.__str__(x)
    if not plain.strip() or len(plain) > _MAX_TEXT:
        raise C1InjectionError(
            f"{name} must be a non-empty string of at most {_MAX_TEXT} characters"
        )
    return plain


def _unreadable(what: str, exc: Exception) -> C1InjectionError:
    """The named error for an argument or a foreign object that misbehaves when it is read."""
    return C1InjectionError(f"{what} cannot be read: {type(exc).__name__}")


def _wrap(exc: InjectionError) -> C1InjectionError:
    return exc if isinstance(exc, C1InjectionError) else C1InjectionError(str(exc))


def _sequence(name: str, items: object, limit: int) -> tuple[Any, ...]:
    """A list or tuple of at most ``limit`` items (never a string, a generator or a mapping)."""
    if isinstance(items, (str, bytes)) or not isinstance(items, (list, tuple)):
        raise C1InjectionError(f"{name} must be a list or a tuple")
    try:
        if len(items) > limit:
            raise C1InjectionError(f"{name} has more than {limit} entries")
        return tuple(items)
    except C1InjectionError:
        raise
    except Exception as exc:  # a list or tuple subclass whose methods misbehave
        raise C1InjectionError(f"{name} cannot be read: {type(exc).__name__}") from exc


# ---------------------------------------------------------------------------
# Magnitudes: a level times a named reference quantity
# ---------------------------------------------------------------------------


def hold_distance_mmhg(
    baseline_sbp_mmhg: float, bp_hold_threshold_mmhg: float
) -> float:
    """The reference quantity of the hypotension: ``baseline - bp_hold_threshold`` (mmHg).

    The caller reads the patient's baseline from the prior source and the threshold from the
    registry; a level of 1 then takes the pressure from the baseline exactly to the threshold, a
    level below 1 stays above it (the template is not violated), a level above 1 goes below. A
    patient whose baseline is not above the threshold has no margin: ``C1InjectionError``.
    """
    baseline = _real("baseline_sbp_mmhg", baseline_sbp_mmhg)
    threshold = _real("bp_hold_threshold_mmhg", bp_hold_threshold_mmhg)
    with np.errstate(all="ignore"):
        distance = baseline - threshold
    if not math.isfinite(distance) or distance <= _MIN_REFERENCE:
        raise C1InjectionError(
            "the baseline must lie above the hold threshold by a finite margin"
        )
    return float(distance)


def resolve_c1_magnitude(
    level: LevelRow, reference_value: float, reference: str
) -> float:
    """``level.value * reference_value`` for a relative level (``injection.resolve_magnitude``).

    ``reference`` names the quantity whose value ``reference_value`` is and must be the one the
    level names in its unit (``"x scale_range"``); an absolute level, an unfilled level and a
    non-positive reference are refused (never defaulted).
    """
    value = _real("reference_value", reference_value)
    if value <= _MIN_REFERENCE:
        raise C1InjectionError("reference_value must be above zero")
    try:
        return resolve_magnitude(level, value, _plain(reference))
    except InjectionError as exc:
        raise _wrap(exc) from exc
    except Exception as exc:
        # a level of another module whose fields misbehave when they are read
        raise _unreadable("the level", exc) from exc


def c1_spec(
    subtype: str,
    onset_ms: int,
    *,
    duration_ms: int | None = None,
    magnitude: float | None = None,
    level: str | None = None,
    confounder_group: str | None = None,
    reference: str | None = None,
    multiple: float | None = None,
    reference_value: float | None = None,
) -> InjectionSpec:
    """A validated C1 ``InjectionSpec`` (the unit of the magnitude is the subtype's).

    ``reference``, ``multiple`` and ``reference_value`` (all three or none) record how a pressure
    magnitude was obtained, ``magnitude = multiple * reference_value``; the check refuses a
    magnitude that disagrees. Raises ``C1InjectionError``.
    """
    name = _text("subtype", subtype)
    shape = _SHAPES.get(name)
    if shape is None:
        raise C1InjectionError(f"subtype must be one of {C1_SUBTYPES}")
    params: dict[str, str | float] = {}
    for key, value in (
        ("reference", reference),
        ("multiple", multiple),
        ("reference_value", reference_value),
    ):
        if value is not None:
            params[key] = (
                str.__str__(value) if isinstance(value, str) else _real(key, value)
            )
    try:
        spec = InjectionSpec(
            InjectedClass.C1,
            name,
            onset_ms,
            duration_ms,
            magnitude,
            None if magnitude is None else shape.unit,
            params,
            _plain(level),
            _plain(confounder_group),
        )
    except InjectionError as exc:
        raise _wrap(exc) from exc
    return _check_spec(spec)


def c1_spec_from_level(
    subtype: str,
    onset_ms: int,
    level: LevelRow,
    reference_value: float | None,
    *,
    duration_ms: int | None = None,
    confounder_group: str | None = None,
) -> InjectionSpec:
    """The spec of a design level: the magnitude is the level times its named reference.

    For a relative level (unit ``"x <reference>"``) ``reference_value`` is the value of that
    quantity (``scale_range`` of the registry, or ``hold_distance_mmhg`` of the patient) and the
    spec records ``reference``, ``multiple`` and ``reference_value``. For an absolute level (the
    dimensionless Emax scale) the level is the magnitude and ``reference_value`` is ignored.
    """
    if not isinstance(level, LevelRow):
        raise C1InjectionError("level must be a LevelRow")
    name = _text("subtype", subtype)
    confounder_group = _plain(confounder_group)
    shape = _SHAPES.get(name)
    if shape is None or shape.unit is None:
        raise C1InjectionError(f"{name} has no magnitude level")
    try:
        return _spec_from_level(
            name, shape, onset_ms, level, reference_value, duration_ms, confounder_group
        )
    except InjectionError:
        raise
    except MemoryError:
        raise
    except Exception as exc:
        # a level of another module whose fields misbehave when read
        raise _unreadable("the level", exc) from exc


def _spec_from_level(
    name: str,
    shape: _Shape,
    onset_ms: int,
    level: LevelRow,
    reference_value: float | None,
    duration_ms: int | None,
    confounder_group: str | None,
) -> InjectionSpec:
    if level.quantity_unit != shape.unit:
        raise C1InjectionError(
            f"{name} takes a magnitude in {shape.unit!r}, the level is in {level.quantity_unit!r}"
        )
    if level.reference is None:
        if level.value is None:
            raise C1InjectionError(f"row {level.name!r} is awaiting_human_value")
        return c1_spec(
            name,
            onset_ms,
            duration_ms=duration_ms,
            magnitude=_real("level value", level.value),
            level=level.level,
            confounder_group=confounder_group,
        )
    magnitude = resolve_c1_magnitude(
        level, _real("reference_value", reference_value), level.reference
    )
    assert level.value is not None  # resolve_c1_magnitude refused an unfilled level
    return c1_spec(
        name,
        onset_ms,
        duration_ms=duration_ms,
        magnitude=magnitude,
        level=level.level,
        confounder_group=confounder_group,
        reference=level.reference,
        multiple=level.value,
        reference_value=float(reference_value),  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# Spec rules
# ---------------------------------------------------------------------------


def _day_of(onset_ms: int) -> int:
    return onset_ms // T_DAY_MS


def _check_spec(spec: InjectionSpec) -> InjectionSpec:
    if not isinstance(spec, InjectionSpec):
        raise C1InjectionError("every spec must be an InjectionSpec")
    if spec.cls is not InjectedClass.C1:
        raise C1InjectionError("a C1 injector takes C1 specs")
    shape = _SHAPES.get(spec.subtype)
    if shape is None:
        raise C1InjectionError(f"subtype must be one of {C1_SUBTYPES}")
    name = spec.subtype
    if shape.window:
        if spec.duration_ms is None:
            raise C1InjectionError(f"{name} is a window and needs a duration_ms")
        end = spec.onset_ms + spec.duration_ms
        if end > (_day_of(spec.onset_ms) + 1) * T_DAY_MS:
            raise C1InjectionError(
                f"{name} window [{spec.onset_ms}, {end}) crosses the end of its day"
            )
    elif spec.duration_ms is not None:
        raise C1InjectionError(f"{name} has no duration")
    if shape.unit is None:
        if spec.magnitude is not None or spec.magnitude_unit is not None:
            raise C1InjectionError(f"{name} has no magnitude")
    else:
        if spec.magnitude is None:
            raise C1InjectionError(f"{name} needs a magnitude in {shape.unit}")
        if spec.magnitude_unit != shape.unit:
            raise C1InjectionError(f"{name} magnitude must be given in {shape.unit!r}")
        if shape.scale:
            if not 0.0 <= spec.magnitude <= 1.0:
                raise C1InjectionError(
                    f"{name} scale must lie in [0, 1]: a scale above 1 is no non-response"
                )
        elif not spec.magnitude > 0.0:
            raise C1InjectionError(
                f"{name} magnitude must be above zero (the sign is the subtype's)"
            )
    _check_params(spec)
    return spec


def _check_params(spec: InjectionSpec) -> None:
    keys = set(spec.params)
    if not keys:
        return
    if spec.subtype not in _MMHG_REFERENCES:
        raise C1InjectionError(f"{spec.subtype} takes no params")
    unknown = keys - set(_PARAM_KEYS)
    if unknown or keys != set(_PARAM_KEYS):
        raise C1InjectionError(
            f"params are {_PARAM_KEYS} together or none, got {sorted(keys)}"
        )
    reference, multiple, ref_value = (
        spec.params["reference"],
        spec.params["multiple"],
        spec.params["reference_value"],
    )
    if reference != _MMHG_REFERENCES[spec.subtype]:
        raise C1InjectionError(
            f"{spec.subtype} is a multiple of {_MMHG_REFERENCES[spec.subtype]!r}"
        )
    for label, number in (("multiple", multiple), ("reference_value", ref_value)):
        if isinstance(number, (bool, str)) or not float(number) > 0.0:
            raise C1InjectionError(f"param {label} must be a number above zero")
    assert spec.magnitude is not None
    expected = float(multiple) * float(ref_value)
    if not math.isclose(spec.magnitude, expected, rel_tol=_REL_TOL):
        raise C1InjectionError("the magnitude is not multiple times reference_value")


def _sort_key(spec: InjectionSpec) -> tuple[Any, ...]:
    return (
        C1_SUBTYPES.index(spec.subtype),
        spec.onset_ms,
        -1 if spec.duration_ms is None else spec.duration_ms,
        (0, 0.0) if spec.magnitude is None else (1, spec.magnitude),
        spec.level or "",
        spec.confounder_group or "",
        tuple(sorted((k, repr(v)) for k, v in spec.params.items())),
    )


def _check_overlaps(ordered: Sequence[InjectionSpec]) -> None:
    last_end: dict[str, int] = {}
    points: set[tuple[str, int]] = set()
    for spec in (
        ordered
    ):  # sorted by (subtype, onset): a window starts after the previous one ends
        if _SHAPES[spec.subtype].window:
            assert spec.duration_ms is not None
            end = last_end.get(spec.subtype)
            if end is not None and spec.onset_ms < end:
                raise C1InjectionError(
                    f"two {spec.subtype} windows overlap at {spec.onset_ms}"
                )
            last_end[spec.subtype] = spec.onset_ms + spec.duration_ms
        else:
            key = (spec.subtype, spec.onset_ms)
            if key in points:
                raise C1InjectionError(
                    f"two {spec.subtype} injections at {spec.onset_ms}"
                )
            points.add(key)


def check_c1_specs(specs: Sequence[InjectionSpec]) -> tuple[InjectionSpec, ...]:
    """Validate a list of C1 specs and return them in canonical order.

    Every spec must be a C1 spec of a known subtype with the shape, unit and sign of that subtype;
    windows lie inside their day and do not overlap within a subtype; a per-tick or per-slot spec
    is not repeated. At most ``MAX_C1_SPECS`` specs. Raises ``C1InjectionError``.
    """
    items = _sequence("specs", specs, MAX_C1_SPECS)
    try:
        checked = tuple(_check_spec(item) for item in items)
        ordered = tuple(sorted(checked, key=_sort_key))
        _check_overlaps(ordered)
    except InjectionError:
        raise
    except MemoryError:
        raise
    except Exception as exc:
        # a spec of another module whose fields misbehave when they are read
        raise _unreadable("a spec", exc) from exc
    return ordered


def canonical_c1_order(specs: Sequence[InjectionSpec]) -> tuple[InjectionSpec, ...]:
    """The specs in canonical order (subtype, onset, duration, magnitude): independent of the input order."""
    return check_c1_specs(specs)


def c1_stream(
    seed: int, patient_index: int, day_index: int, spec: InjectionSpec
) -> np.random.Generator:
    """The named stream of a C1 injection: ``(seed, patient, day, INJECTION_C1, digest)``.

    The digest is that of the identity of the injection (subtype, onset, duration; not the
    magnitude), as for the C2 streams, so it does not depend on the position in a list or on the
    other injections. The current injectors draw nothing; the stream is for the plan and for a
    randomised subtype added later.
    """
    check_c1_specs([spec])
    day = _int("day_index", day_index, 0, _TIME_LIMIT // T_DAY_MS)
    try:
        return stream(
            _int("seed", seed, 0, _SEED_LIMIT - 1),
            _int("patient_index", patient_index, 0, _WORD_LIMIT - 1),
            day,
            StreamPurpose.INJECTION_C1,
            injection_sub_index(spec),
        )
    except StreamKeyError as exc:
        raise C1InjectionError(str(exc)) from exc
    except InjectionError as exc:
        raise _wrap(exc) from exc


# ---------------------------------------------------------------------------
# The working copy of one latent day
# ---------------------------------------------------------------------------


class LatentWork:
    """The mutable working copy of one latent day that the C1 injectors edit.

    ``t_ms`` is the pressure grid of the day (strictly increasing integer ms on the continuing
    axis, inside ``[day * T_day, (day + 1) * T_day)``); ``dose_ticks_ms`` and
    ``measurement_ticks_ms`` are the schedule ticks as clock times of the day; the working copy
    keeps them on the continuing axis. ``double_take_gap_ms`` is the gap of the adherence
    configuration. The injectors fill ``pulse_mmhg`` (added to the pressure), ``intake_scales``
    (the per-intake scales of the Emax, aligned with ``intake_times_ms`` once ``set_intakes`` was
    called), ``refused_ticks_ms`` and ``double_take_ticks_ms``; ``latent_day`` reads them.
    """

    __slots__ = (
        "day_index",
        "day_start_ms",
        "dose_ticks_ms",
        "double_take_gap_ms",
        "double_take_ticks_ms",
        "has_pulses",
        "intake_scales",
        "intake_times_ms",
        "measurement_ticks_ms",
        "pulse_mmhg",
        "refused_ticks_ms",
        "t_ms",
    )

    def __init__(
        self,
        day_index: int,
        t_ms: npt.NDArray[np.int64],
        *,
        dose_ticks_ms: Sequence[int],
        measurement_ticks_ms: Sequence[int],
        double_take_gap_ms: int,
    ) -> None:
        day = _int("day_index", day_index, 0, _TIME_LIMIT // T_DAY_MS)
        if (
            not isinstance(t_ms, np.ndarray)
            or t_ms.ndim != 1
            or t_ms.dtype.kind not in "iu"
            or not np.can_cast(t_ms.dtype, np.int64, "safe")
        ):
            raise C1InjectionError(
                "t_ms must be a one-dimensional array of int64 times"
            )
        if not 0 < t_ms.size <= MAX_GRID_POINTS:
            raise C1InjectionError(f"t_ms needs 1 to {MAX_GRID_POINTS} points")
        grid = np.asarray(t_ms, dtype=np.int64)
        start = day * T_DAY_MS
        if int(grid[0]) < start or int(grid[-1]) >= start + T_DAY_MS:
            raise C1InjectionError("the grid must lie inside the day")
        if grid.size > 1 and not bool(np.all(np.diff(grid) > 0)):
            raise C1InjectionError("the grid must be strictly increasing")
        ticks = []
        for name, values in (
            ("dose_ticks_ms", dose_ticks_ms),
            ("measurement_ticks_ms", measurement_ticks_ms),
        ):
            items = _sequence(name, values, MAX_WORK_INTAKES)
            checked = tuple(
                start + _int(f"{name} entry", v, 0, T_DAY_MS - 1) for v in items
            )
            if any(b <= a for a, b in itertools.pairwise(checked)):
                raise C1InjectionError(f"{name} must be strictly increasing")
            ticks.append(checked)
        self.day_index: int = day
        self.day_start_ms: int = start
        self.t_ms: npt.NDArray[np.int64] = grid
        self.dose_ticks_ms: tuple[int, ...] = ticks[0]
        self.measurement_ticks_ms: tuple[int, ...] = ticks[1]
        self.double_take_gap_ms: int = _int(
            "double_take_gap_ms", double_take_gap_ms, 1, T_DAY_MS
        )
        self.pulse_mmhg: npt.NDArray[np.float64] = np.zeros(grid.size, dtype=np.float64)
        self.has_pulses: bool = False
        self.intake_times_ms: tuple[int, ...] = ()
        self.intake_scales: list[float] = []
        self.refused_ticks_ms: set[int] = set()
        self.double_take_ticks_ms: set[int] = set()

    @property
    def day_end_ms(self) -> int:
        return self.day_start_ms + T_DAY_MS

    def set_intakes(self, times_ms: Sequence[int]) -> None:
        """The true intake times of the history and of the day (every scale starts at 1)."""
        items = _sequence("times_ms", times_ms, MAX_WORK_INTAKES)
        self.intake_times_ms = tuple(
            _int("an intake time", t, 0, _TIME_LIMIT) for t in items
        )
        self.intake_scales = [1.0] * len(self.intake_times_ms)

    def refused_clock_ticks_ms(self) -> tuple[int, ...]:
        """The refused measurement ticks as clock times of the day (the skip list of WS04-T06)."""
        return tuple(sorted(t - self.day_start_ms for t in self.refused_ticks_ms))


# ---------------------------------------------------------------------------
# The injectors
# ---------------------------------------------------------------------------


def _prepare(
    work: object, specs: object, subtype: str
) -> tuple[LatentWork, tuple[InjectionSpec, ...]]:
    if not isinstance(work, LatentWork):
        raise C1InjectionError("work must be a LatentWork")
    ordered = check_c1_specs(specs)  # type: ignore[arg-type]
    for spec in ordered:
        if spec.subtype != subtype:
            raise C1InjectionError(f"{spec.subtype} given to the injector of {subtype}")
    return work, ordered


def _record(
    spec: InjectionSpec,
    n_changed: int,
    onset_ms: int,
    end_ms: int | None,
    details: Mapping[str, Any],
) -> InjectionRecord:
    return InjectionRecord(
        spec,
        onset_ms,
        end_ms,
        n_changed > 0,
        n_changed,
        (),  # a C1 has no evidence signature: it is what the channels agree on
        spec.level,
        spec.confounder_group,
        dict(details),
    )


def _window(spec: InjectionSpec) -> tuple[int, int]:
    assert spec.duration_ms is not None  # a window subtype: check_c1_specs required it
    return spec.onset_ms, spec.onset_ms + spec.duration_ms


def _pulse_details(spec: InjectionSpec, n: int) -> dict[str, Any]:
    details: dict[str, Any] = {"n_grid_points": n, "magnitude": spec.magnitude}
    if spec.params:
        details["reference"] = spec.params["reference"]
        details["multiple"] = spec.params["multiple"]
        details["reference_value"] = spec.params["reference_value"]
    return details


def _pulse(
    work: object, specs: object, subtype: str, sign: int
) -> tuple[InjectionRecord, ...]:
    work_, ordered = _prepare(work, specs, subtype)
    records: list[InjectionRecord] = []
    for spec in ordered:
        start, end = _window(spec)
        lo = int(
            np.searchsorted(work_.t_ms, start, side="left")
        )  # a point at start is inside
        hi = int(
            np.searchsorted(work_.t_ms, end, side="left")
        )  # a point at end is outside
        assert spec.magnitude is not None
        if hi > lo:
            work_.pulse_mmhg[lo:hi] += sign * spec.magnitude
            work_.has_pulses = True
        records.append(
            _record(spec, hi - lo, start, end, _pulse_details(spec, hi - lo))
        )
    return tuple(records)


def hypertensive_spike(
    work: LatentWork, specs: Sequence[InjectionSpec]
) -> tuple[InjectionRecord, ...]:
    """Add ``magnitude`` mmHg to the latent pressure at every grid point of ``[onset, onset + duration)``."""
    return _pulse(work, specs, SPIKE, 1)


def hypotension_below_hold(
    work: LatentWork, specs: Sequence[InjectionSpec]
) -> tuple[InjectionRecord, ...]:
    """Subtract ``magnitude`` mmHg from the latent pressure at every grid point of the window."""
    return _pulse(work, specs, HYPOTENSION, -1)


def drug_nonresponse(
    work: LatentWork, specs: Sequence[InjectionSpec]
) -> tuple[InjectionRecord, ...]:
    """Scale the Emax of every intake whose time lies in ``[onset, onset + duration)`` by ``magnitude``.

    The scale replaces the default 1 of the intake (windows of one subtype do not overlap, so an
    intake lies in at most one). The intakes are those given to ``LatentWork.set_intakes`` (the
    history of the earlier days and the day itself): the scale of an intake is a function of its
    time and the specs, whichever day's call it is made in. ``n_changed`` counts the intakes whose
    scale differs from what it was; a scale of 1 changes nothing.
    """
    work_, ordered = _prepare(work, specs, NONRESPONSE)
    times = np.asarray(work_.intake_times_ms, dtype=np.int64)
    order = np.argsort(times, kind="stable")
    sorted_times = times[order]
    records: list[InjectionRecord] = []
    for spec in ordered:
        start, end = _window(spec)
        lo = int(np.searchsorted(sorted_times, start, side="left"))
        hi = int(np.searchsorted(sorted_times, end, side="left"))
        assert spec.magnitude is not None
        inside = [int(i) for i in order[lo:hi]]
        changed = 0
        for i in inside:
            if work_.intake_scales[i] != spec.magnitude:
                changed += 1
                work_.intake_scales[i] = spec.magnitude
        details: dict[str, Any] = {
            "scale": spec.magnitude,
            "n_intakes_in_window": len(inside),
            "intake_times_ms": sorted(int(times[i]) for i in inside),
        }
        records.append(_record(spec, changed, start, end, details))
    return tuple(records)


def measurement_refusal(
    work: LatentWork, specs: Sequence[InjectionSpec]
) -> tuple[InjectionRecord, ...]:
    """The patient refuses the measurement of the schedule tick ``onset`` (no latent MEASUREMENT)."""
    work_, ordered = _prepare(work, specs, REFUSAL)
    ticks = set(work_.measurement_ticks_ms)
    records: list[InjectionRecord] = []
    for spec in ordered:
        tick = spec.onset_ms
        details: dict[str, Any] = {"tick_ms": tick}
        n = 0
        if tick in ticks:
            work_.refused_ticks_ms.add(tick)
            n = 1
        else:
            details["reason"] = "the instant is not a measurement tick of the day"
        records.append(_record(spec, n, tick, None, details))
    return tuple(records)


def double_take(
    work: LatentWork, specs: Sequence[InjectionSpec]
) -> tuple[InjectionRecord, ...]:
    """Force the dose whose tick is ``onset`` into the double-take state of the adherence chain.

    The surplus release is the instant of the record (``tick + double_take_gap_ms``): that is where
    the count of dispenses rises. The record is realised whenever the tick is a dose tick of the
    day, even if the chain would have drawn the same state (it explains the latent double take).
    """
    work_, ordered = _prepare(work, specs, DOUBLE_TAKE)
    doses = set(work_.dose_ticks_ms)
    records: list[InjectionRecord] = []
    for spec in ordered:
        tick = spec.onset_ms
        second = tick + work_.double_take_gap_ms
        details: dict[str, Any] = {
            "slot_tick_ms": tick,
            "gap_ms": work_.double_take_gap_ms,
            "second_dispense_ms": second,
            "forced": True,
        }
        n = 0
        if tick in doses:
            work_.double_take_ticks_ms.add(tick)
            n = _DOUBLE_TAKE_EVENTS
        else:
            details["reason"] = "the instant is not a dose tick of the day"
        records.append(_record(spec, n, second, None, details))
    return tuple(records)


# ---------------------------------------------------------------------------
# The observed side of a refusal
# ---------------------------------------------------------------------------


def observe_refusals(
    stream_: ObservedStream, records: Sequence[InjectionRecord]
) -> ObservedStream:
    """Add the declined-task event of every realised refusal to an observed base stream.

    The base stream was built with the refused ticks in its skip list (no reading, the robot still
    visits). The patient's refusal is what the robot reports: a ``ROBOT_TASK`` event of the task
    ``manipulate`` with the outcome ``declined`` (``vocab.OUTCOME_DECLINED``), stamped at the arrival
    of the visit, in contrast to a manipulation failure (outcome ``failed``). Nothing else changes;
    no latent value is written. A refusal whose tick has no visit in the stream is
    ``C1InjectionError``. Returns the same stream when there is nothing to add.
    """
    if not isinstance(stream_, ObservedStream):
        raise C1InjectionError("stream_ must be an ObservedStream")
    checked = _sequence("records", records, MAX_C1_SPECS)
    try:
        return _observe_refusals(stream_, checked)
    except InjectionError:
        raise
    except MemoryError:
        raise
    except Exception as exc:
        # a stream or record of another module whose fields misbehave
        raise _unreadable("the stream or a record", exc) from exc


def _observe_refusals(
    stream_: ObservedStream, records: Sequence[Any]
) -> ObservedStream:
    added: list[Event] = []
    for record in records:
        if not isinstance(record, InjectionRecord):
            raise C1InjectionError("every record must be an InjectionRecord")
        spec = record.spec
        if (
            spec.cls is not InjectedClass.C1
            or spec.subtype != REFUSAL
            or not record.realised
        ):
            continue
        visit = next(
            (
                v
                for v in stream_.visits
                if v.kind == vocab.KIND_MEASUREMENT and v.tick_ms == spec.onset_ms
            ),
            None,
        )
        if visit is None:
            raise C1InjectionError(
                f"no robot visit at the refused tick {spec.onset_ms}: the stream is not the base of that day"
            )
        payload: dict[str, float | int | str | bool] = {
            vocab.KEY_TASK: vocab.TASK_MANIPULATE,
            vocab.KEY_OUTCOME: vocab.OUTCOME_DECLINED,
            vocab.KEY_PATIENT_ID: stream_.patient_id,
        }
        try:
            vocab.check_payload(EventKind.ROBOT_TASK, payload)
        except vocab.VocabularyError as exc:
            raise C1InjectionError(str(exc)) from exc
        added.append(
            Event(
                EventKind.ROBOT_TASK,
                visit.arrival_ms,
                visit.arrival_ms,
                vocab.SOURCE_ROBOT,
                payload,
                None,
            )
        )
    if not added:
        return stream_
    events = sorted(
        (*stream_.events, *added), key=lambda e: e.t_rx_ms
    )  # stable: new ones last
    return dataclasses.replace(stream_, events=tuple(events))


# ---------------------------------------------------------------------------
# Design file
# ---------------------------------------------------------------------------


def _design_error(message: str) -> InjectionDesignError:
    return InjectionDesignError(f"injections.c1: {message}")


def load_c1_design(path: str | os.PathLike[str]) -> Mapping[str, SubtypeDesign]:
    """The C1 section of ``injections.yaml`` with the rows its levels name.

    The section ``injections.c1`` lists exactly ``C1_SUBTYPES`` with the families ``physiology``
    and ``behaviour`` and, per subtype, the duration and magnitude blocks of
    ``injection.load_injection_design``: a window subtype has a duration, a pressure magnitude is
    a multiple of its named reference (``scale_range`` for the spike, ``baseline_to_hold_distance``
    for the hypotension; the unit of a level row is ``"x <reference>"``, never an absolute mmHg), the
    Emax scale is an absolute dimensionless level, and every magnitude has at least three levels
    (below, near and above the reference). A row that is still ``awaiting_human_value`` gives a
    level with ``value`` None; once every level of a pressure magnitude has a value, the values
    must span the reference (the smallest multiple below 1, the largest above 1). Raises
    ``InjectionError`` for an invalid file.
    """
    try:
        design = load_injection_design(_plain(path), section="c1")
    except InjectionError:
        raise
    except MemoryError:
        raise
    except Exception as exc:  # a path object that misbehaves
        raise _design_error(
            f"the design file cannot be read: {type(exc).__name__}"
        ) from exc
    if set(design) != set(C1_SUBTYPES):
        raise _design_error(f"must list exactly {sorted(C1_SUBTYPES)}")
    for subtype, entry in design.items():
        shape = _SHAPES[subtype]
        where = f"{subtype}"
        if (entry.duration is not None) != shape.window:
            raise _design_error(f"{where}: duration disagrees with the subtype")
        if (entry.magnitude is not None) != (shape.unit is not None):
            raise _design_error(f"{where}: magnitude disagrees with the subtype")
        if entry.duration is not None:
            if entry.duration.unit != "ms":
                raise _design_error(f"{where}: a duration is in ms")
            for row in entry.duration.levels:
                if row.unit != "ms":
                    raise _design_error(f"{where}: duration row {row.name!r} is in ms")
        magnitude = entry.magnitude
        if magnitude is None:
            continue
        if magnitude.unit != shape.unit:
            raise _design_error(f"{where}: the magnitude is in {shape.unit}")
        if shape.unit == UNIT_MMHG:
            reference = _MMHG_REFERENCES[subtype]
            if magnitude.reference != reference:
                raise _design_error(
                    f"{where}: the magnitude is a multiple of {reference}"
                )
            for row in magnitude.levels:
                if row.unit != f"x {reference}":
                    raise _design_error(
                        f"{where}: row {row.name!r} must be in 'x {reference}', "
                        "never an absolute pressure"
                    )
            # Once every level has a value they must span the reference: a multiple below 1 and
            # one above it (review F9). A block that still awaits a value is not judged.
            multiples = [row.value for row in magnitude.levels]
            filled = [m for m in multiples if m is not None]
            if len(filled) == len(multiples) and not min(filled) < 1.0 < max(filled):
                raise _design_error(
                    f"{where}: the filled levels must span below and above the reference "
                    f"{reference} (a multiple under 1 and one over 1), got {sorted(filled)}"
                )
        else:
            if magnitude.reference is not None:
                raise _design_error(f"{where}: the Emax scale has no reference")
            for row in magnitude.levels:
                if row.unit != UNIT_SCALE:
                    raise _design_error(
                        f"{where}: row {row.name!r} is a dimensionless scale"
                    )
    return design
