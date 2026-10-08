"""Assembly of the complete latent day, with the C1 injections (WS04-T09).

``assemble_latent_days`` builds, for each day of a call, the **latent day** of one patient: the
noise-free, fault-free trace that carries the ground truth (``02-interfaces.md#trace-schema``).
The pipeline of the README, in this order, one day at a time:

1. the latent baseline pressure (``latent.simulate_baseline_sbp``: baseline, circadian component,
   autoregressive noise);
2. the adherence chain (``adherence.AdherenceModel``) with the forced slots (see below): the true
   DISPENSE and INTAKE events;
3. the per-intake Emax scales of the ``drug_nonresponse`` specs (``inject_c1``);
4. the drug response (a ``pkpd.ResponseModel``): the pressure is ``baseline - effect``;
5. the spike and hypotension pulses, added to the pressure (``inject_c1``);
6. the latent heart rate and SpO2 from the clean segments (``measurement.draw_clean_vitals`` with
   the key that the observed base uses, so the latent and the observed vitals agree);
7. the latent events: ``SCHEDULE_TICK`` at every tick, an ideal ``MEASUREMENT`` at every
   measurement tick except the refused ones, and the true ``DISPENSE`` and ``INTAKE``.

The latent day holds samples ``bp`` (the latent grid), ``hr_ecg`` and ``spo2`` (the vitals grid)
and events of kinds ``SCHEDULE_TICK``, ``MEASUREMENT``, ``DISPENSE`` and ``INTAKE`` only: no
``cuff_health``, ``inflation_ms``, ``presence``, no quality, no sequence number, no transport
delay. It carries nothing that belongs to the observation. The latent value of the pressure
never reaches an observed day through this module (it returns latent days and records).

Continuity across midnight. The autoregressive noise, the adherence chain and the drug
accumulation are continuous: a call over ``n`` days equals ``n`` calls of one day, each given the
``AssemblyState`` that the previous one returned (``LatentResult.end_state``) and the same spec
list; nothing resets at midnight. To make that exact the draws are keyed per day: the noise is the
stream ``(seed, patient, day, LATENT_AR)`` and the chain the stream ``(seed, patient, day,
ADHERENCE)``, the carried state being the last noise value and the last chain state. (The
patient-level stream of ``adherence.adherence_stream`` would restart at the first draw in a
call that starts at day ``d``; WS04-T05 left the choice open.) The drug of an intake acts on every
later day: the state carries all the true intake times of the earlier days (the model of
WS04-T04 has no memory across calls) and the scale of an intake is a function of its time and the
``drug_nonresponse`` specs, which are the same in every call. An INTAKE that falls after the end
of its day (a delayed dose, the second release of a double take at the end of a day) belongs to the
events of the day of its slot, as in WS04-T05, and acts on the pressure from its own time on.

Forced slots. The adherence model of WS04-T05 draws the state of every slot from its chain and
has no hook to force one (its ``state`` argument carries the chain, it does not force a slot).
This module forces a slot without touching ``adherence.py``: the chain is run as usual (so every
draw is consumed and the other slots are bit-identical with or without the forcing), then the
behaviour log entry of the forced slot is replaced by the entry that the model gives for the
point-mass chain in the forced state on a schedule of that dose alone, and the events of the day
are rebuilt from the log (``_events_from_log``, tested against the model). A forced slot is
``ForcedSlot`` (``ON_TIME`` or ``OMITTED``: scenario controls that need no record) or the C1 spec
``double_take`` (a forced double take is an injection: it has a record). The chain itself is not
changed by the forcing: the natural state sequence continues (with the default memoryless matrix
nothing differs). ``DELAYED`` cannot be forced (a delay needs a draw).

Ground truth. This module does not construct a ground-truth event and does not read one; the C1
records it returns say what was injected, and the labeller (WS04-T10) decides what is true.

Resource bounds (named constants, checked before any array is allocated): at most ``MAX_DAYS``
days, ``MAX_TOTAL_POINTS`` samples and events over the call, ``MAX_TOTAL_EVALUATIONS``
intake-by-grid-point evaluations of the response model over the call, ``MAX_FORCED_SLOTS`` forced
slots. Every public function raises ``LatentAssemblyError`` or the errors of ``inject_c1`` (both
subclasses of ``InjectionError``) and nothing else: an error of the response model or of another
benchmark module is converted.
"""

from __future__ import annotations

import math
import numbers
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from operator import itemgetter
from typing import Any, Final, TypeGuard

import numpy as np

from ralmon.benchmark import vocab
from ralmon.benchmark.adherence import (
    AdherenceConfigError,
    AdherenceModel,
    AdherenceState,
    BehaviourEntry,
)
from ralmon.benchmark.inject_c1 import (
    C1_SUBTYPES,
    DOUBLE_TAKE,
    HYPOTENSION,
    NONRESPONSE,
    REFUSAL,
    SPIKE,
    LatentWork,
    check_c1_specs,
    double_take,
    drug_nonresponse,
    hypertensive_spike,
    hypotension_below_hold,
    measurement_refusal,
)
from ralmon.benchmark.injection import InjectionError, InjectionRecord, InjectionSpec
from ralmon.benchmark.latent import (
    MAX_GRID_POINTS,
    T_DAY_MS,
    LatentModelError,
    simulate_baseline_sbp,
)
from ralmon.benchmark.measurement import (
    MAX_VISITS_PER_DAY,
    MeasurementConfigError,
    MeasurementDesign,
    draw_clean_vitals,
)
from ralmon.benchmark.pkpd import (
    PkpdModelError,
    ResponseModel,
    compose_latent_sbp,
    intake_times_from_events,
)
from ralmon.benchmark.priors import AdherenceParams, PatientParams
from ralmon.benchmark.rng import StreamKeyError, StreamPurpose, stream
from ralmon.benchmark.schedule import Schedule, ScheduleError
from ralmon.benchmark.segments import SegmentError, SegmentLibrary
from ralmon.benchmark.trace import LatentDay, TraceError, validate_day
from ralmon.signals import DurationMs, Event, EventKind, Sample, SignalId

__all__ = [
    "MAX_DAYS",
    "MAX_FORCED_SLOTS",
    "MAX_TOTAL_EVALUATIONS",
    "MAX_TOTAL_POINTS",
    "SOURCE_PATIENT",
    "AssemblyConfig",
    "AssemblyState",
    "ForcedSlot",
    "LatentAssemblyError",
    "LatentResult",
    "assemble_latent_days",
]

MAX_DAYS: Final[int] = 366  # algorithmic: days of one call
MAX_FORCED_SLOTS: Final[int] = 10_000  # algorithmic: forced slots of one call
MAX_TOTAL_POINTS: Final[int] = 200_000  # algorithmic: samples and events over one call
MAX_TOTAL_EVALUATIONS: Final[int] = (
    20_000_000  # algorithmic: intake-by-point evaluations of a call
)
_MAX_START_DAY: Final = 1_000_000  # algorithmic: latest day index of a call
_SEED_LIMIT: Final = 1 << 64  # algorithmic: the root seed of rng.stream is below 2**64
_WORD_LIMIT: Final = 1 << 32  # algorithmic: a stream key entry is below 2**32
_EVENTS_PER_SLOT: Final = 5  # algorithmic: a tick, two dispenses, two intakes at most
_HEADROOM: Final = 4  # algorithmic: a time is at most a quarter of the int64 range
_MAX_TIME: Final = int(np.iinfo(np.int64).max) // _HEADROOM
SOURCE_PATIENT: Final = (
    "patient"  # Event.source of a true INTAKE (as WS04-T05 writes it)
)

_BP: Final = SignalId.BP.value
_HR_ECG: Final = SignalId.HR_ECG.value
_SPO2: Final = SignalId.SPO2.value
_FORCEABLE: Final = (AdherenceState.ON_TIME, AdherenceState.OMITTED)
# Errors of the other benchmark modules, converted into LatentAssemblyError with their message
# (any other error of a collaborator is converted by ``assemble_latent_days`` without it).
_FOREIGN: Final = (
    ArithmeticError,  # OverflowError: a float field of the patient beyond the float range
    AdherenceConfigError,
    LatentModelError,
    MeasurementConfigError,
    PkpdModelError,
    ScheduleError,
    SegmentError,
    StreamKeyError,
    TraceError,
)


class LatentAssemblyError(InjectionError):
    """An argument, the state or the horizon of the latent assembly is invalid."""


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _is_integer(x: object) -> TypeGuard[numbers.Integral]:
    return not isinstance(x, (bool, np.bool_)) and isinstance(x, numbers.Integral)


def _int(name: str, x: object, lo: int, hi: int) -> int:
    if not _is_integer(x):
        raise LatentAssemblyError(f"{name} must be an integer")
    try:
        value = int(x)
    except Exception as exc:  # a number type whose conversion misbehaves
        raise LatentAssemblyError(f"{name} is not an integer") from exc
    if not lo <= value <= hi:
        raise LatentAssemblyError(f"{name} must lie in [{lo}, {hi}]")
    return value


def _real(name: str, x: object) -> float:
    if isinstance(x, (bool, np.bool_)) or not isinstance(x, numbers.Real):
        raise LatentAssemblyError(f"{name} must be a finite number")
    try:
        value = float(x)
    except Exception as exc:  # too large, or a number type whose conversion misbehaves
        raise LatentAssemblyError(f"{name} is not a finite number") from exc
    if not math.isfinite(value):
        raise LatentAssemblyError(f"{name} must be a finite number")
    return value


def _sequence(name: str, items: object, limit: int) -> tuple[Any, ...]:
    if isinstance(items, (str, bytes)) or not isinstance(items, (list, tuple)):
        raise LatentAssemblyError(f"{name} must be a list or a tuple")
    try:
        if len(items) > limit:
            raise LatentAssemblyError(f"{name} has more than {limit} entries")
        return tuple(items)
    except LatentAssemblyError:
        raise
    except Exception as exc:  # a list or tuple subclass whose methods misbehave
        raise LatentAssemblyError(
            f"{name} cannot be read: {type(exc).__name__}"
        ) from exc


# ---------------------------------------------------------------------------
# Configuration, forced slots, state, result
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AssemblyConfig:
    """The generator settings of the latent day (none is a clinical value).

    ``latent_step_ms`` is the grid of the latent pressure (it must divide the day and give at most
    ``MAX_GRID_POINTS`` points a day), ``circadian_peak_clock_ms`` the clock time of the circadian
    maximum and ``ar_reference_step_ms`` the step at which ``ar_noise_phi`` was estimated (both read
    by the caller from the design file and the prior source), ``adherence`` the adherence model,
    ``vitals`` the measurement design (its ``vitals_period_ms`` is the grid of the latent heart rate
    and SpO2), ``allow_no_segments`` lets a library without a heart-rate or SpO2 kind produce a day
    without that signal (no value is invented).
    """

    latent_step_ms: DurationMs
    circadian_peak_clock_ms: DurationMs
    ar_reference_step_ms: DurationMs
    adherence: AdherenceModel
    vitals: MeasurementDesign
    allow_no_segments: bool = False

    def __post_init__(self) -> None:
        step = _int("latent_step_ms", self.latent_step_ms, 1, T_DAY_MS)
        if T_DAY_MS % step != 0 or T_DAY_MS // step > MAX_GRID_POINTS:
            raise LatentAssemblyError(
                "latent_step_ms must divide the day and give at most "
                f"{MAX_GRID_POINTS} points a day"
            )
        object.__setattr__(self, "latent_step_ms", step)
        object.__setattr__(
            self,
            "circadian_peak_clock_ms",
            _int(
                "circadian_peak_clock_ms", self.circadian_peak_clock_ms, 0, T_DAY_MS - 1
            ),
        )
        object.__setattr__(
            self,
            "ar_reference_step_ms",
            _int("ar_reference_step_ms", self.ar_reference_step_ms, 1, T_DAY_MS),
        )
        if not isinstance(self.adherence, AdherenceModel):
            raise LatentAssemblyError("adherence must be an AdherenceModel")
        if not isinstance(self.vitals, MeasurementDesign):
            raise LatentAssemblyError("vitals must be a MeasurementDesign")
        if not isinstance(self.allow_no_segments, bool):
            raise LatentAssemblyError("allow_no_segments must be a bool")


@dataclass(frozen=True, slots=True)
class ForcedSlot:
    """Force the adherence outcome of one dose: ``dose_index`` is its position among the day's doses.

    ``ON_TIME`` (one dispense at the tick) and ``OMITTED`` (none) are the scenario controls of the
    confounder pairs; they carry no record. A double take is forced by the C1 spec ``double_take``
    (it is an injection with a record), and ``DELAYED`` needs a draw: both are refused here.
    """

    day_index: int
    dose_index: int
    state: AdherenceState

    def __post_init__(self) -> None:
        _int("day_index", self.day_index, 0, _MAX_START_DAY + MAX_DAYS)
        _int("dose_index", self.dose_index, 0, MAX_VISITS_PER_DAY)
        if not isinstance(self.state, AdherenceState) or self.state not in _FORCEABLE:
            raise LatentAssemblyError(
                "a forced slot is ON_TIME or OMITTED (a double take is the C1 spec double_take; "
                "a delay needs a draw)"
            )


@dataclass(frozen=True, slots=True)
class AssemblyState:
    """What a call hands to the next one (nothing resets at midnight).

    ``next_day`` is the day the next call starts at, ``ar_state_mmhg`` the last autoregressive
    value, ``chain_state`` the last adherence state (None before the first slot) and
    ``intake_times_ms`` every true intake time of the earlier days (their drug still acts).
    """

    next_day: int
    ar_state_mmhg: float
    chain_state: AdherenceState | None
    intake_times_ms: tuple[int, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "next_day",
            _int("next_day", self.next_day, 0, _MAX_START_DAY + MAX_DAYS),
        )
        object.__setattr__(
            self, "ar_state_mmhg", _real("ar_state_mmhg", self.ar_state_mmhg)
        )
        if self.chain_state is not None and not isinstance(
            self.chain_state, AdherenceState
        ):
            raise LatentAssemblyError("chain_state must be an AdherenceState or None")
        times = _sequence("intake_times_ms", self.intake_times_ms, MAX_TOTAL_POINTS)
        object.__setattr__(
            self,
            "intake_times_ms",
            tuple(_int("an intake time", t, 0, _MAX_TIME) for t in times),
        )


@dataclass(frozen=True, slots=True)
class LatentResult:
    """One assembled day.

    ``latent`` is the latent day (the only thing a ground-truth labeller reads), ``behaviour_log``
    the adherence outcome of each dose (a sidecar of the truth file), ``c1_records`` the records of
    the C1 injections whose onset lies in this day, in canonical order (never ground truth).
    ``refused_ticks_ms`` are the refused measurement ticks as clock times (the skip list of
    ``measurement.build_observed_base``), ``baseline_sbp_mmhg`` the latent pressure before the drug
    and the pulses (a generator-side sidecar for the paired design) and ``end_state`` the state to
    continue from.
    """

    latent: LatentDay
    behaviour_log: tuple[BehaviourEntry, ...]
    c1_records: tuple[InjectionRecord, ...]
    refused_ticks_ms: tuple[int, ...]
    baseline_sbp_mmhg: tuple[float, ...]
    end_state: AssemblyState


# ---------------------------------------------------------------------------
# Adherence with forced slots
# ---------------------------------------------------------------------------


def _forced_model(model: AdherenceModel, state: AdherenceState) -> AdherenceModel:
    """The point-mass chain in ``state``, with the timing of ``model``."""
    omitted = state is AdherenceState.OMITTED
    double = state is AdherenceState.DOUBLE_TAKE
    return AdherenceModel(
        AdherenceParams(0.0, 1.0 if omitted else 0.0, 1.0 if double else 0.0, 0),
        model.config,
    )


def _events_from_log(log: Sequence[BehaviourEntry], lag_ms: int) -> tuple[Event, ...]:
    """The true events of the slots of a log: a DISPENSE and, ``lag_ms`` later, an INTAKE each.

    Sorted by ``(time, kind, slot)`` with DISPENSE before INTAKE at one instant: the order of
    ``adherence.AdherenceModel.simulate`` (a test compares the two).
    """
    stamped: list[tuple[int, int, int, Event]] = []
    for slot, entry in enumerate(log):
        for t in entry.dispense_times_ms:
            stamped.append(
                (
                    t,
                    0,
                    slot,
                    Event(EventKind.DISPENSE, t, t, vocab.SOURCE_DISPENSER, {}, None),
                )
            )
            stamped.append(
                (
                    t + lag_ms,
                    1,
                    slot,
                    Event(
                        EventKind.INTAKE,
                        t + lag_ms,
                        t + lag_ms,
                        SOURCE_PATIENT,
                        {},
                        None,
                    ),
                )
            )
    stamped.sort(key=itemgetter(0, 1, 2))
    return tuple(item[-1] for item in stamped)


def _adherence_day(
    model: AdherenceModel,
    schedule: Schedule,
    day: int,
    chain: AdherenceState | None,
    seed: int,
    patient_index: int,
    forced: Mapping[int, AdherenceState],
) -> tuple[tuple[Event, ...], tuple[BehaviourEntry, ...], AdherenceState | None]:
    rng = stream(seed, patient_index, day, StreamPurpose.ADHERENCE)
    result = model.simulate(schedule, 1, rng, start_day=day, state=chain)
    if not forced:
        return result.events, result.behaviour_log, result.final_state
    log = list(result.behaviour_log)
    for dose_index, state in sorted(forced.items()):
        tick = schedule.dose_ticks_ms[dose_index]
        sub = _forced_model(model, state).simulate(
            Schedule((tick,), ()),
            1,
            stream(seed, patient_index, day, StreamPurpose.CONFOUNDER, dose_index),
            start_day=day,
        )
        log[dose_index] = sub.behaviour_log[0]
    return (
        _events_from_log(log, model.config.intake_lag_ms),
        tuple(log),
        result.final_state,  # the natural chain continues: the forcing is an intervention
    )


# ---------------------------------------------------------------------------
# Events and samples
# ---------------------------------------------------------------------------

# Order of the kinds at one instant: the ticks, the dispense, the intake, the measurement.
_RANK_DOSE_TICK: Final = 0
_RANK_MEASUREMENT_TICK: Final = 1
_RANK_DISPENSE: Final = 2
_RANK_INTAKE: Final = 3  # algorithmic: rank of the intake at one instant
_RANK_MEASUREMENT: Final = 4  # algorithmic: rank of the measurement at one instant


def _latent_events(
    work: LatentWork, adherence_events: Sequence[Event]
) -> tuple[Event, ...]:
    """SCHEDULE_TICK, ideal MEASUREMENT (not the refused ones), DISPENSE and INTAKE, in time order."""
    stamped: list[tuple[int, int, int, Event]] = []
    for k, t in enumerate(work.dose_ticks_ms):
        stamped.append(
            (t, _RANK_DOSE_TICK, k, Event(
                EventKind.SCHEDULE_TICK, t, t, vocab.SOURCE_WARD, {vocab.KEY_KIND: vocab.KIND_DOSE}, None,
            ))
        )  # fmt: skip
    for k, t in enumerate(work.measurement_ticks_ms):
        stamped.append(
            (t, _RANK_MEASUREMENT_TICK, k, Event(
                EventKind.SCHEDULE_TICK, t, t, vocab.SOURCE_WARD, {vocab.KEY_KIND: vocab.KIND_MEASUREMENT}, None,
            ))
        )  # fmt: skip
        if t not in work.refused_ticks_ms:
            stamped.append(
                (t, _RANK_MEASUREMENT, k, Event(EventKind.MEASUREMENT, t, t, vocab.SOURCE_CUFF, {}, None))
            )  # fmt: skip
    for k, e in enumerate(adherence_events):
        rank = _RANK_DISPENSE if e.kind is EventKind.DISPENSE else _RANK_INTAKE
        stamped.append((e.t_device_ms, rank, k, e))
    stamped.sort(key=itemgetter(0, 1, 2))
    return tuple(item[-1] for item in stamped)


def _sample(signal: str, t: int, value: float) -> Sample:
    return Sample(signal, t, t, float(value), None, None)


# ---------------------------------------------------------------------------
# The assembly
# ---------------------------------------------------------------------------


def _day_of(onset_ms: int) -> int:
    return onset_ms // T_DAY_MS


def assemble_latent_days(
    patient: PatientParams,
    schedule: Schedule,
    n_days: int,
    c1_specs: Sequence[InjectionSpec],
    response_model: ResponseModel,
    library: SegmentLibrary,
    seed: int,
    patient_index: int,
    *,
    config: AssemblyConfig,
    start_day: int = 0,
    state: AssemblyState | None = None,
    forced_slots: Sequence[ForcedSlot] = (),
) -> tuple[LatentResult, ...]:
    """The latent days ``start_day .. start_day + n_days - 1`` of one patient (module docstring).

    ``c1_specs`` is the list of C1 specs of the whole patient timeline: every spec is validated,
    the records of those whose onset lies in an assembled day are returned with that day, a
    ``drug_nonresponse`` spec acts on every intake whose time lies in its window, whichever day's
    call it is made in, and the other specs of a day outside the call are ignored. Pass the same
    list to every call of a chain. ``state`` (None at day 0) is ``end_state`` of the previous call.
    ``response_model`` is any ``pkpd.ResponseModel``. Raises ``LatentAssemblyError`` (and the
    errors of ``inject_c1`` for a spec); an error of the response model is converted.
    """
    try:
        return _assemble(
            patient, schedule, n_days, c1_specs, response_model, library, seed,
            patient_index, config, start_day, state, forced_slots,
        )  # fmt: skip
    except InjectionError:
        raise
    except _FOREIGN as exc:
        raise LatentAssemblyError(f"{type(exc).__name__}: {exc}") from exc
    except MemoryError:
        raise
    except Exception as exc:
        # An argument of another module that misbehaves when it is read: a patient with a field
        # beyond the float range (``OverflowError``), a float or a string subclass that raises
        # from its methods, a model or a library that breaks (review F5).
        raise LatentAssemblyError(f"the assembly failed: {type(exc).__name__}") from exc


def _check_forced(
    forced_slots: object, first: int, days: int, n_doses: int
) -> dict[tuple[int, int], AdherenceState]:
    forced: dict[tuple[int, int], AdherenceState] = {}
    for item in _sequence("forced_slots", forced_slots, MAX_FORCED_SLOTS):
        if not isinstance(item, ForcedSlot):
            raise LatentAssemblyError("every forced slot must be a ForcedSlot")
        if not first <= item.day_index < first + days:
            raise LatentAssemblyError(
                f"a forced slot of day {item.day_index} is outside the call"
            )
        if item.dose_index >= n_doses:
            raise LatentAssemblyError(f"the schedule has no dose {item.dose_index}")
        key = (item.day_index, item.dose_index)
        if key in forced:
            raise LatentAssemblyError(f"slot {key} is forced twice")
        forced[key] = item.state
    return forced


def _assemble(
    patient: PatientParams,
    schedule: Schedule,
    n_days: int,
    c1_specs: Sequence[InjectionSpec],
    response_model: ResponseModel,
    library: SegmentLibrary,
    seed: int,
    patient_index: int,
    config: AssemblyConfig,
    start_day: int,
    state: AssemblyState | None,
    forced_slots: Sequence[ForcedSlot],
) -> tuple[LatentResult, ...]:
    if not isinstance(patient, PatientParams):
        raise LatentAssemblyError("patient must be a PatientParams")
    if not isinstance(schedule, Schedule):
        raise LatentAssemblyError("schedule must be a Schedule")
    days = _int("n_days", n_days, 1, MAX_DAYS)
    first = _int("start_day", start_day, 0, _MAX_START_DAY)
    if not callable(getattr(response_model, "effect_mmhg", None)):
        raise LatentAssemblyError("response_model must have an effect_mmhg method")
    if not isinstance(library, SegmentLibrary):
        raise LatentAssemblyError("library must be a SegmentLibrary")
    root = _int("seed", seed, 0, _SEED_LIMIT - 1)
    index = _int("patient_index", patient_index, 0, _WORD_LIMIT - 1)
    if not isinstance(config, AssemblyConfig):
        raise LatentAssemblyError("config must be an AssemblyConfig")
    if first == 0:
        if state is not None:
            raise LatentAssemblyError(
                "a call that starts at day 0 has no state to carry"
            )
    elif not isinstance(state, AssemblyState) or state.next_day != first:
        raise LatentAssemblyError(
            f"start_day {first} needs the AssemblyState of day {first - 1}"
        )
    specs = check_c1_specs(c1_specs)
    doses, ticks = schedule.dose_ticks_ms, schedule.measurement_ticks_ms
    if len(doses) + len(ticks) > MAX_VISITS_PER_DAY:
        raise LatentAssemblyError(f"a day has at most {MAX_VISITS_PER_DAY} ticks")
    forced = _check_forced(forced_slots, first, days, len(doses))

    step = config.latent_step_ms
    points = T_DAY_MS // step
    per_day = (
        points
        + 2 * config.vitals.vitals_points
        + _EVENTS_PER_SLOT * (len(doses) + len(ticks))
    )
    if days * per_day > MAX_TOTAL_POINTS:
        raise LatentAssemblyError(
            f"{days} day(s) of {per_day} samples and events exceed MAX_TOTAL_POINTS = {MAX_TOTAL_POINTS}"
        )
    by_type = {t: tuple(s for s in specs if s.subtype == t) for t in C1_SUBTYPES}
    rank = {id(spec): k for k, spec in enumerate(specs)}

    ar_state = None if state is None else state.ar_state_mmhg
    chain = None if state is None else state.chain_state
    history: tuple[int, ...] = () if state is None else state.intake_times_ms
    evaluations = 0
    results: list[LatentResult] = []
    for day in range(first, first + days):
        day_start = day * T_DAY_MS
        pressure = simulate_baseline_sbp(
            patient,
            step,
            1,
            config.circadian_peak_clock_ms,
            config.ar_reference_step_ms,
            stream(root, index, day, StreamPurpose.LATENT_AR),
            start_day=day,
            ar_state_mmhg=ar_state,
        )
        work = LatentWork(
            day,
            pressure.t_ms,
            dose_ticks_ms=doses,
            measurement_ticks_ms=ticks,
            double_take_gap_ms=config.adherence.config.double_take_gap_ms,
        )
        today = {
            t: tuple(s for s in by_type[t] if _day_of(s.onset_ms) == day)
            for t in C1_SUBTYPES
        }
        records: list[InjectionRecord] = list(double_take(work, today[DOUBLE_TAKE]))

        forced_today = {d: s for (dd, d), s in forced.items() if dd == day}
        for tick in work.double_take_ticks_ms:
            dose_index = doses.index(tick - day_start)
            if dose_index in forced_today:
                raise LatentAssemblyError(
                    f"dose {dose_index} of day {day} is forced twice (a double_take spec and a forced slot)"
                )
            forced_today[dose_index] = AdherenceState.DOUBLE_TAKE
        events, log, chain = _adherence_day(
            config.adherence, schedule, day, chain, root, index, forced_today
        )
        intakes = history + intake_times_from_events(events)
        evaluations += len(intakes) * points
        if evaluations > MAX_TOTAL_EVALUATIONS:
            raise LatentAssemblyError(
                f"the response model would need more than {MAX_TOTAL_EVALUATIONS} evaluations"
            )
        work.set_intakes(intakes)
        records.extend(
            r
            for r in drug_nonresponse(work, by_type[NONRESPONSE])
            if _day_of(r.spec.onset_ms) == day
        )

        scales = (
            work.intake_scales if any(s != 1.0 for s in work.intake_scales) else None
        )
        try:
            effect = response_model.effect_mmhg(
                patient, intakes, pressure.t_ms.tolist(), intake_scales=scales
            )
        except InjectionError:
            raise
        except Exception as exc:  # a response model that misbehaves
            raise LatentAssemblyError(
                f"the response model failed: {type(exc).__name__}"
            ) from exc
        sbp = compose_latent_sbp(pressure.sbp_mmhg, effect)
        records.extend(hypertensive_spike(work, today[SPIKE]))
        records.extend(hypotension_below_hold(work, today[HYPOTENSION]))
        if work.has_pulses:
            sbp = (
                sbp + work.pulse_mmhg
            )  # validate_day below refuses a value that is not finite
        records.extend(measurement_refusal(work, today[REFUSAL]))

        vitals = draw_clean_vitals(
            library,
            config.vitals,
            root,
            index,
            day,
            allow_missing=config.allow_no_segments,
        )
        samples: list[Sample] = [
            _sample(_BP, int(t), float(v))
            for t, v in zip(pressure.t_ms.tolist(), sbp.tolist(), strict=True)
        ]
        period = config.vitals.vitals_period_ms
        for name, grid in ((_HR_ECG, vitals.hr_bpm), (_SPO2, vitals.spo2_pct)):
            if grid is not None:
                samples.extend(
                    _sample(name, day_start + j * period, v) for j, v in enumerate(grid)
                )
        samples.sort(
            key=lambda s: s.t_device_ms
        )  # stable: bp before the vitals at one instant
        latent = LatentDay(
            patient.patient_id,
            day,
            root,
            tuple(samples),
            _latent_events(work, events),
        )
        validate_day(latent)
        ar_state = pressure.ar_state_mmhg
        history = intakes
        results.append(
            LatentResult(
                latent,
                log,
                tuple(sorted(records, key=lambda r: rank[id(r.spec)])),
                work.refused_clock_ticks_ms(),
                tuple(pressure.sbp_mmhg.tolist()),
                AssemblyState(day + 1, ar_state, chain, history),
            )
        )
    return tuple(results)
