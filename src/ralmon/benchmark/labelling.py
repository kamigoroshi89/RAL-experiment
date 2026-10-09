"""Latent ground-truth labeller (WS04-T10): the C1 truth is phi_CP evaluated on the LATENT day.

Definition (analisi section 5.1; ``02-interfaces.md#trace-schema`` rule 1). A true C1 event is a violation
of the care-plan specification phi_CP (the templates RANGE, SCHED, HOLD, COUNT and RESP) evaluated on the
latent trace, that is, on the day without cuff error, faults or attacks. True C2 and C3 events are the
injected events. The monitor and every baseline see only the corrupted observation; this module is the one
place that turns the latent day into truth, so it is the composition module that may import ``ralmon.monitor``
and ``ralmon.spec`` (together with the builder and the validation report, README issue I1).

How the C1 truth is computed. ``ideal_observation`` builds an ``ObservedDay``-shaped view of the latent day
from latent values only: the exact latent pressure at the latent MEASUREMENT instants (mode ``scheduled``, the
default) or at every latent grid step (mode ``dense``), the true DISPENSE events, the SCHEDULE_TICK events and
the end-of-day impulse, with ``t_rx_ms == t_device_ms``, no quality, no sequence number and no noise. Only the
signals that the phi_CP templates use are supplied; SYS and INT are not run, so the presence/INT hazard of
ADR-054 cannot reach a C1 label. The labeller hands the WS05 monitor that view and nothing else
(``label_latent_day`` has no observed-day parameter), keeps the first VIOLATED record of each phi_CP instance
and turns it into one ``GroundTruthEvent``.

Conventions (``docs/benchmark/ground-truth.md`` section "Onset and end conventions"; WS08 reads them).

* One event per violated instance, identified by ``instance_key``: the FIRST VIOLATED record of the key
  defines it. The monitor keeps emitting records of an instance after its decision (the graded refinement of
  SCHED, docs/formal/05 section 6.5), and every record carries ``pending_until_ms`` (OP-T05-17); later VIOLATED
  records must agree with the first on ``decided_at_ms`` and ``pending_until_ms``, else the runner is refused.
* By TEMPLATE KIND, not by the presence of ``pending_until_ms``: RANGE, HOLD and the COUNT limit give
  ``onset_ms = decided_at_ms`` and ``end_ms = None``. The windowed obligations RESP, SCHED and the day-end
  COUNT give ``onset_ms`` = the anchor of the violated instance and ``end_ms = pending_until_ms`` (the
  deadline). The anchor is ``TemplateInstance.anchor_ms`` when the instance is in the plan (SCHED, the day-end
  COUNT); for a RESP instance created at a DISPENSE it is ``pending_until_ms - delta2`` (the window length from
  the registry, overlaid by the plan's own parameter record). For the day-end COUNT the anchor is the closing
  step, so ``onset_ms == end_ms``.
* Instances still open at the end of the day (``k_d > K``: a RESP window or a SCHED deadline after the closing
  step) are decided early where the monitor's early-decision rule applies (RESP with a pre-dose value that no
  pressure of the physiological domain can answer) and are otherwise PENDING at trace end: they are not
  violations (docs/formal/05 section 7.5 item 2; ADR-046 proposed). A day is labelled with empty history, as the
  monitor runs it: nothing is carried over from the day before.
* Time is the continuing axis ``day_index * T_day + clock time`` (ADR-053 (h)); ``run_offline`` starts the
  monitor at the step ``day_index * K``.

Injection records versus truth. A C1 injection record explains a C1 event (``injected = True``, its subtype,
its confounder group) iff its template matches by ``LINK_TABLE`` and the instant of the event lies in its
window extended by the template latency bound of the monitor (``verdict_latency_bound_ms``); ``drug_nonresponse``
is linked through ``details["intake_times_ms"]`` (its window selects intakes, the RESP anchor is the dispense),
the COUNT limit through the 24 h window of the counter, and HOLD also through the reading that decided it
(ADR-055, proposed, records these readings of the rule).
An event no record explains gets its natural subtype: ``double_take`` or ``dose_omission`` from the behaviour
log (never injected), else ``spontaneous_<template id>``. C2 and C3 events are one per REALISED record through
``record_to_ground_truth``; no C1 record is ever passed to it (it would answer ``injected = True`` and no
template).

Determinism. No clock, no random number, no environment: the result is a function of the arguments. Every
public function raises only the named errors of this module (``LabellingError`` and its subclasses), also for
hostile arguments; sizes are bounded by named constants.
"""

from __future__ import annotations

import bisect
import itertools
import math
import numbers
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final, TypeGuard

from ralmon.benchmark import vocab
from ralmon.benchmark.adherence import AdherenceState, BehaviourEntry
from ralmon.benchmark.injection import (
    InjectionRecord,
    injection_log,
    record_to_ground_truth,
)
from ralmon.benchmark.latent import T_DAY_MS
from ralmon.benchmark.trace import (
    BenchmarkDay,
    GroundTruthEvent,
    InjectedClass,
    JsonValue,
    LatentDay,
    ObservedDay,
    TraceError,
    TruthRecord,
    validate_day,
)
from ralmon.monitor import (
    MonitorConfig,
    OfflineResult,
    StreamingMonitor,
    VerdictRecord,
    VerdictState,
    run_offline,
)
from ralmon.signals import Event, EventKind, Sample, SignalId, default_derived_signals
from ralmon.spec import (
    CarePlan,
    RegistryError,
    Template,
    TemplateId,
    TemplateKind,
    TemplateLibraryError,
    load_registry,
    load_templates,
)

__all__ = [
    "INJECTION_LOG_BASE_KEYS",
    "INJECTION_LOG_LINK_KEYS",
    "LINK_TABLE",
    "MODES",
    "MODE_DENSE",
    "MODE_SCHEDULED",
    "SPONTANEOUS_PREFIX",
    "SUBTYPE_DOSE_OMISSION",
    "SUBTYPE_DOUBLE_TAKE",
    "AssembledDay",
    "IdealObservationError",
    "LabelledDay",
    "LabellingError",
    "RegistryMismatchError",
    "RunnerError",
    "assemble_benchmark_day",
    "ideal_observation",
    "label_latent_day",
    "label_latent_day_detailed",
]

# ---------------------------------------------------------------------------------------------------
# Named constants
# ---------------------------------------------------------------------------------------------------

MODE_SCHEDULED: Final = "scheduled"
MODE_DENSE: Final = "dense"
MODES: Final = (MODE_SCHEDULED, MODE_DENSE)

SPONTANEOUS_PREFIX: Final = "spontaneous_"
SUBTYPE_DOUBLE_TAKE: Final = "double_take"
SUBTYPE_DOSE_OMISSION: Final = "dose_omission"

# The injection-to-template link (WS04 README, vocabulary of GroundTruthEvent.subtype).
LINK_TABLE: Final[Mapping[str, str]] = MappingProxyType(
    {
        "hypertensive_spike": TemplateId.RANGE.value,
        "drug_nonresponse": TemplateId.RESP.value,
        "hypotension_below_hold": TemplateId.HOLD.value,
        "measurement_refusal": TemplateId.SCHED.value,
        SUBTYPE_DOUBLE_TAKE: TemplateId.COUNT.value,
    }
)

# Keys of one entry of the ``injection_log`` sidecar: the fourteen of ``injection.injection_log`` and the two
# links to the truth that this module adds (the position of the record, and the positions in the ground truth
# of the events it explains or produced).
INJECTION_LOG_BASE_KEYS: Final = (
    "cls",
    "subtype",
    "onset_ms",
    "duration_ms",
    "end_ms",
    "magnitude",
    "magnitude_unit",
    "params",
    "level",
    "confounder_group",
    "realised",
    "n_changed",
    "evidence_paths",
    "details",
)
INJECTION_LOG_LINK_KEYS: Final = ("record_index", "truth_indices")

MAX_VERDICT_RECORDS: Final[int] = (
    5_000_000  # algorithmic: most verdict records a runner may hand back for one day
)
MAX_INJECTION_RECORDS: Final[int] = (
    100_000  # algorithmic: most injection records of one day
)
MAX_BEHAVIOUR_ENTRIES: Final[int] = (
    100_000  # algorithmic: most behaviour-log entries of one call
)
MAX_LATENT_ITEMS: Final[int] = (
    1_000_000  # algorithmic: most samples or events of one latent day
)
MAX_PLAN_INSTANCES: Final[int] = (
    1_000_000  # algorithmic: most instances of one care plan
)
MAX_INTAKES_PER_RECORD: Final[int] = (
    100_000  # algorithmic: most intake times of one drug_nonresponse record
)
MAX_DAY_INDEX: Final[int] = (
    36_500  # algorithmic: latest day index, about a century of days
)
MAX_TEXT: Final[int] = (
    4_096  # algorithmic: longest identifier or label read from a record
)
MAX_TEMPLATES: Final[int] = (
    64  # algorithmic: most templates or template signals in a library
)
MAX_DISPENSES_PER_SLOT: Final[int] = (
    16  # algorithmic: most dispenses of one behaviour-log slot
)
_SHOWN: Final = 32  # algorithmic: characters of a value shown in an error message

_BP: Final = SignalId.BP.value
_MEAS: Final = SignalId.MEAS.value
_DISPENSE: Final = SignalId.DISPENSE.value
_SCHED_TICK: Final = SignalId.SCHED_TICK.value
_DAY_END: Final = SignalId.DAY_END.value
_SUPPLIED: Final = frozenset({_BP, _MEAS, _DISPENSE, _SCHED_TICK})
_GENERATED: Final = frozenset({_DAY_END})
_CP_SIGNALS: Final = (_BP, _MEAS, _DISPENSE, _SCHED_TICK, _DAY_END)

# the kinds of violated instance, which are finer than the template for COUNT
_K_RANGE: Final = "range"
_K_HOLD: Final = "hold"
_K_SCHED: Final = "sched"
_K_RESP: Final = "resp"
_K_LIMIT: Final = "count_limit"
_K_END: Final = "count_end"
_LINK_KIND: Final = {
    "range": _K_RANGE,
    "resp": _K_RESP,
    "hold": _K_HOLD,
    "sched": _K_SCHED,
    "count": _K_LIMIT,
}


# ---------------------------------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------------------------------


class LabellingError(ValueError):
    """An argument, a record or a registry that the labeller cannot use."""


class IdealObservationError(LabellingError):
    """A phi_CP template signal that the latent day cannot supply (nothing is guessed)."""


class RegistryMismatchError(LabellingError):
    """The plan, the monitor configuration and the registry do not name one registry version."""


class RunnerError(LabellingError):
    """The runner failed or returned something that is not a coherent list of verdict records."""


# ---------------------------------------------------------------------------------------------------
# Small checks (no hostile object is ever formatted or compared before it is reduced to a plain value)
# ---------------------------------------------------------------------------------------------------


def _show(value: object) -> str:
    """The type of a value and, for plain str, int, float and bool, a bounded form of it; never raises."""
    kind = type(value).__name__
    if type(value) in (int, float, bool, str):
        try:
            text = repr(value)
        except Exception:  # noqa: BLE001 - an int beyond the conversion limit of the interpreter
            return kind
        return f"{kind} {text[:_SHOWN]}" + ("..." if len(text) > _SHOWN else "")
    return kind


def _is_int(value: object) -> TypeGuard[numbers.Integral]:
    return isinstance(value, numbers.Integral) and not isinstance(value, bool)


def _int(
    value: object,
    what: str,
    error: type[LabellingError],
    low: int | None = None,
    high: int | None = None,
) -> int:
    if not _is_int(value):
        raise error(f"{what} must be an integer, got {_show(value)}")
    try:
        number = int(value)
    except Exception as exc:
        raise error(f"{what} is not an integer") from exc
    if (low is not None and number < low) or (high is not None and number > high):
        raise error(f"{what} is out of range, got {_show(number)}")
    return number


def _optional_int(
    value: object, what: str, error: type[LabellingError], low: int | None = None
) -> int | None:
    return None if value is None else _int(value, what, error, low)


def _finite(value: object, what: str, error: type[LabellingError]) -> float:
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise error(f"{what} must be a finite number, got {_show(value)}")
    try:
        number = float(value)
    except Exception as exc:
        raise error(f"{what} is not a finite number") from exc
    if not math.isfinite(number):
        raise error(f"{what} must be finite, got {_show(number)}")
    return number


def _text(value: object, what: str, error: type[LabellingError]) -> str:
    if not isinstance(value, str):
        raise error(f"{what} must be a str, got {_show(value)}")
    plain = str.__str__(value)  # an exact str: the hooks of a subclass are not called
    if not plain or len(plain) > MAX_TEXT:
        raise error(f"{what} must be a non-empty str of at most {MAX_TEXT} characters")
    return plain


def _items(
    value: object, what: str, limit: int, error: type[LabellingError]
) -> tuple[Any, ...]:
    """The items of a list or tuple: the length is checked before the read, and the read stops past the limit
    (a subclass can report a short length and yield without end)."""
    if not isinstance(value, (list, tuple)):
        raise error(f"{what} must be a list or a tuple, got {_show(value)}")
    if len(value) > limit:
        raise error(f"{what} has more than {limit} items")
    items = tuple(itertools.islice(iter(value), limit + 1))
    if len(items) > limit:
        raise error(f"{what} has more than {limit} items")
    return items


# ---------------------------------------------------------------------------------------------------
# Validation of the latent day and the plan
# ---------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Latent:
    patient_id: str
    day_index: int
    seed: int
    samples: tuple[Sample, ...]
    events: tuple[Event, ...]

    @property
    def day_start(self) -> int:
        return self.day_index * T_DAY_MS

    @property
    def day_end(self) -> int:
        return self.day_start + T_DAY_MS


def _read_latent(latent: object, error: type[LabellingError]) -> _Latent:
    if not isinstance(latent, LatentDay):
        raise error(f"latent must be a LatentDay, got {_show(latent)}")
    return _Latent(
        _text(latent.patient_id, "latent.patient_id", error),
        _int(latent.day_index, "latent.day_index", error, 0, MAX_DAY_INDEX),
        _int(latent.seed, "latent.seed", error),
        _items(latent.samples, "latent.samples", MAX_LATENT_ITEMS, error),
        _items(latent.events, "latent.events", MAX_LATENT_ITEMS, error),
    )


@dataclass(frozen=True, slots=True)
class _Plan:
    care_plan_id: str
    patient_id: str
    registry_version: str
    sched_anchor: Mapping[str, int]
    day_end_anchor: Mapping[str, int]
    resp_anchor: Mapping[str, int]
    parameters: Mapping[TemplateId, Mapping[str, float]]


def _read_plan(plan: object) -> _Plan:
    if not isinstance(plan, CarePlan):
        raise LabellingError(f"plan must be a CarePlan, got {_show(plan)}")
    sched: dict[str, int] = {}
    day_end: dict[str, int] = {}
    resp: dict[str, int] = {}
    records: dict[TemplateId, dict[str, float]] = {}
    seen: set[str] = set()
    for item in _items(
        plan.instances, "plan.instances", MAX_PLAN_INSTANCES, LabellingError
    ):
        template = item.template
        if not isinstance(template, TemplateId):
            raise LabellingError(
                f"a plan instance has a template that is {_show(template)}"
            )
        key = _text(item.instance_key, "a plan instance_key", LabellingError)
        if key in seen:
            raise LabellingError("an instance_key appears twice in the plan")
        seen.add(key)
        anchor = _optional_int(item.anchor_ms, "a plan anchor_ms", LabellingError)
        if anchor is None:
            if template in records:
                raise LabellingError("a template has two parameter records in the plan")
            values = item.param_values
            if not isinstance(values, Mapping):
                raise LabellingError("a plan param_values must be a mapping")
            records[template] = {
                _text(name, "a parameter name", LabellingError): _finite(
                    value, "a plan parameter value", LabellingError
                )
                for name, value in values.items()
            }
        elif template is TemplateId.SCHED:
            sched[key] = anchor
        elif template is TemplateId.COUNT:
            day_end[key] = anchor
        elif template is TemplateId.RESP:
            resp[key] = anchor
    return _Plan(
        _text(plan.care_plan_id, "plan.care_plan_id", LabellingError),
        _text(plan.patient_id, "plan.patient_id", LabellingError),
        _text(plan.registry_version, "plan.registry_version", LabellingError),
        sched,
        day_end,
        resp,
        records,
    )


# ---------------------------------------------------------------------------------------------------
# The ideal observation
# ---------------------------------------------------------------------------------------------------


def _wanted_signals(signals: object) -> frozenset[str]:
    """The template signals to supply: derived ones are dropped, the unsupplyable ones are refused."""
    if signals is None:
        return frozenset(_CP_SIGNALS)
    if not isinstance(signals, (list, tuple, set, frozenset)):
        raise IdealObservationError(
            f"signals must be a collection, got {_show(signals)}"
        )
    known = {s.value for s in SignalId}
    derived = {d.output.value for d in default_derived_signals()}
    wanted: set[str] = set()
    if (
        len(signals) > MAX_TEMPLATES
    ):  # the length is read before the collection is iterated
        raise IdealObservationError(f"signals has more than {MAX_TEMPLATES} items")
    listed = tuple(itertools.islice(iter(signals), MAX_TEMPLATES + 1))
    if (
        len(listed) > MAX_TEMPLATES
    ):  # a collection can report a short length and yield without end
        raise IdealObservationError(f"signals has more than {MAX_TEMPLATES} items")
    for name in listed:
        plain = _text(name, "a template signal", IdealObservationError)
        if plain not in known:
            raise IdealObservationError(f"{plain!r} is not a signal")
        if plain in derived:
            continue  # the monitor derives it from the supplied signals
        if plain not in _SUPPLIED and plain not in _GENERATED:
            raise IdealObservationError(
                f"the latent day cannot supply the signal {plain!r}: it has no robot, cuff-health, "
                "inflation, authentication or vital-sign channel"
            )
        wanted.add(plain)
    return frozenset(wanted)


def _bin_of(t: int, origin: int, step: int) -> int:
    return -((origin - t) // step)  # ceil((t - origin) / step)


def ideal_observation(
    latent: LatentDay,
    care_plan_id: str,
    mode: str = MODE_SCHEDULED,
    *,
    step_ms: int | None = None,
    signals: Sequence[str] | None = None,
) -> ObservedDay:
    """An ``ObservedDay``-shaped view of a latent day made of latent values only (module docstring).

    ``mode`` is ``scheduled`` (``bp`` only at the latent MEASUREMENT instants, the exact held latent value,
    one MEASUREMENT event each) or ``dense`` (``bp`` and a MEASUREMENT event at every latent grid step).
    ``signals`` are the template signals to supply (default: those of the five phi_CP templates); a signal
    that the latent day cannot supply raises ``IdealObservationError``, nothing is guessed. ``step_ms`` is
    the monitor step: with it, two readings in one grid bin are refused (hypothesis (A0) of
    docs/formal/05 section 2.1). Raises only ``IdealObservationError``.
    """
    try:
        return _ideal_observation(latent, care_plan_id, mode, step_ms, signals)
    except LabellingError as exc:
        if isinstance(exc, IdealObservationError):
            raise
        raise IdealObservationError(str(exc)) from exc
    except MemoryError:
        raise
    except Exception as exc:
        raise IdealObservationError(
            f"the ideal observation failed: {type(exc).__name__}"
        ) from exc


def _ideal_observation(
    latent: object,
    care_plan_id: object,
    mode: object,
    step_ms: object,
    signals: object,
) -> ObservedDay:
    error = IdealObservationError
    day = _read_latent(latent, error)
    plan_id = _text(care_plan_id, "care_plan_id", error)
    if not isinstance(mode, str) or str.__str__(mode) not in MODES:
        raise error(f"mode must be one of {MODES}, got {_show(mode)}")
    dense = str.__str__(mode) == MODE_DENSE
    step = None if step_ms is None else _int(step_ms, "step_ms", error, 1, T_DAY_MS)
    if step is not None and T_DAY_MS % step != 0:
        raise error("step_ms must divide the day")
    want = _wanted_signals(signals)
    lo, hi = day.day_start, day.day_end

    # the latent pressure: strictly increasing times, finite values
    times: list[int] = []
    values: list[float] = []
    for sample in day.samples:
        if not isinstance(sample, Sample):
            raise error(f"a latent sample must be a Sample, got {_show(sample)}")
        if sample.signal != _BP:
            continue
        t = _int(sample.t_device_ms, "a latent bp time", error)
        if times and t <= times[-1]:
            raise error("latent bp samples must have strictly increasing times")
        times.append(t)
        values.append(_finite(sample.value, "a latent bp value", error))

    def inside(t: int, what: str) -> int:
        if not lo <= t <= hi:
            raise error(f"{what} at {t} lies outside the day [{lo}, {hi}]")
        return t

    event_times: dict[EventKind, list[int]] = {
        EventKind.MEASUREMENT: [],
        EventKind.DISPENSE: [],
        EventKind.SCHEDULE_TICK: [],
    }
    ticks: list[tuple[int, dict[str, float | int | str | bool]]] = []
    for event in day.events:
        if not isinstance(event, Event):
            raise error(f"a latent event must be an Event, got {_show(event)}")
        if not isinstance(event.kind, EventKind):
            raise error("a latent event has a kind that is not an EventKind")
        if event.kind not in event_times:
            continue
        t = _int(event.t_device_ms, "a latent event time", error)
        event_times[event.kind].append(t)
        if event.kind is EventKind.SCHEDULE_TICK:
            if not isinstance(event.payload, Mapping):
                raise error("a latent event payload must be a mapping")
            ticks.append((t, dict(event.payload)))
    measurement_times = sorted(event_times[EventKind.MEASUREMENT])

    need_grid = (_BP in want or _MEAS in want) and (dense or _BP in want)
    if dense:
        if (_BP in want or _MEAS in want) and not times:
            raise error(
                "dense mode needs the latent bp grid: the latent day has no bp sample"
            )
        reading_times = (
            [inside(t, "a latent grid step") for t in times] if need_grid else []
        )
        reading_values = list(values) if need_grid else []
    else:
        for earlier, later in itertools.pairwise(measurement_times):
            if earlier == later:
                raise error("two latent MEASUREMENT events share one instant")
        reading_times = [inside(t, "a latent MEASUREMENT") for t in measurement_times]
        reading_values = []
        if _BP in want and reading_times:
            if not times:
                raise error(
                    "the latent day has no bp sample: no pressure to hold at a measurement"
                )
            for t in reading_times:
                position = bisect.bisect_right(times, t) - 1
                if position < 0:
                    raise error(
                        f"the latent bp starts after the measurement at {t}: "
                        "there is no pressure before it to hold"
                    )
                reading_values.append(values[position])
    if step is not None and (_BP in want or _MEAS in want):
        bins = [_bin_of(t, lo, step) for t in reading_times]
        if len(set(bins)) != len(bins):
            raise error(
                "two readings share one grid bin of the monitor step: hypothesis (A0) of the "
                "semantics (at most one pressure per bin) would not hold"
            )

    samples: list[Sample] = []
    if _BP in want:
        samples.extend(
            Sample(_BP, t, t, v, None, None)
            for t, v in zip(reading_times, reading_values, strict=True)
        )
    if _DAY_END in want:
        samples.append(Sample(_DAY_END, hi, hi, 1.0, None, None))
    events: list[Event] = []
    if _MEAS in want:
        events.extend(
            Event(EventKind.MEASUREMENT, t, t, vocab.SOURCE_CUFF, {}, None)
            for t in reading_times
        )
    if _DISPENSE in want:
        events.extend(
            Event(EventKind.DISPENSE, t, t, vocab.SOURCE_DISPENSER, {}, None)
            for t in (
                inside(t, "a latent DISPENSE") for t in event_times[EventKind.DISPENSE]
            )
        )
    if _SCHED_TICK in want:
        events.extend(
            Event(
                EventKind.SCHEDULE_TICK,
                inside(t, "a latent SCHEDULE_TICK"),
                t,
                vocab.SOURCE_WARD,
                payload,
                None,
            )
            for t, payload in ticks
        )
    samples.sort(key=_by_rx)
    events.sort(key=_by_rx)
    return ObservedDay(
        day.patient_id, day.day_index, day.seed, tuple(samples), tuple(events), plan_id
    )


def _by_rx(item: Sample | Event) -> int:
    return item.t_rx_ms


# ---------------------------------------------------------------------------------------------------
# Configuration, registry, templates
# ---------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Setup:
    config: MonitorConfig
    registry: Any
    templates: tuple[Template, ...]  # the phi_CP templates only
    needed: frozenset[str]


def _read_config(config: object) -> MonitorConfig:
    if not isinstance(config, MonitorConfig):
        raise LabellingError(f"config must be a MonitorConfig, got {_show(config)}")
    step = _int(config.step_ms, "config.step_ms", LabellingError, 1, T_DAY_MS)
    if T_DAY_MS % step != 0:
        raise LabellingError("config.step_ms must divide the day")
    _int(
        config.reorder_delay_ms, "config.reorder_delay_ms", LabellingError, 0, T_DAY_MS
    )
    if not isinstance(config.predictive, bool) or config.predictive:
        raise LabellingError(
            "the labeller uses the measured channel only: predictive must be False"
        )
    _text(config.registry_version, "config.registry_version", LabellingError)
    return config


def _setup(
    plan: _Plan,
    config: Any,
    registry: Any,
    templates: Any,
) -> _Setup:
    if config is None:
        step = getattr(registry, "step_ms", None) if registry is not None else None
        if step is None:
            raise LabellingError(
                "config is missing and the registry gives no step_ms to derive one from"
            )
        cfg = _read_config(
            MonitorConfig(step, 0, False, None, "likely", _version_of(registry))
        )
    else:
        cfg = _read_config(config)
    if registry is None:
        try:
            registry = load_registry(
                step_ms=cfg.step_ms
            )  # the real registry, never a fixture
        except RegistryError as exc:
            raise LabellingError(
                f"the default registry cannot be loaded: {exc}"
            ) from exc
    for method in ("get", "version"):
        if not callable(getattr(registry, method, None)):
            raise LabellingError(
                f"registry must have a {method} method, got {_show(registry)}"
            )
    loaded = _version_of(registry)
    if plan.registry_version != cfg.registry_version or loaded != cfg.registry_version:
        raise RegistryMismatchError(
            f"the plan names registry version {plan.registry_version!r}, the monitor configuration "
            f"{cfg.registry_version!r} and the loaded registry {loaded!r}: they must be one version"
        )
    registry_step = getattr(registry, "step_ms", None)
    if registry_step is not None and registry_step != cfg.step_ms:
        raise LabellingError(
            f"config.step_ms {cfg.step_ms} differs from the step_ms of the registry "
            f"{_show(registry_step)}: load the registry with the step of the monitor"
        )
    if templates is None:
        try:
            library = tuple(load_templates(registry=registry))
        except (RegistryError, TemplateLibraryError) as exc:
            raise LabellingError(
                f"the default template library cannot be loaded: {exc}"
            ) from exc
    else:
        library = _items(templates, "templates", MAX_TEMPLATES, LabellingError)
    for template in library:
        if not isinstance(template, Template):
            raise LabellingError(
                f"templates must be Template objects, got {_show(template)}"
            )
    chosen = tuple(t for t in library if t.kind is TemplateKind.CARE_PLAN)
    if not chosen:
        raise LabellingError("the template library holds no phi_CP template")
    needed: set[str] = set()
    for template in chosen:
        signals = _items(
            template.signals, "a template's signals", MAX_TEMPLATES, LabellingError
        )
        needed.update(_text(s, "a template signal", LabellingError) for s in signals)
    return _Setup(cfg, registry, chosen, frozenset(needed))


def _version_of(registry: object) -> str:
    try:
        version = registry.version()  # type: ignore[attr-defined]
    except Exception as exc:
        raise LabellingError("the registry has no readable version") from exc
    return _text(version, "the registry version", LabellingError)


def _check_supply(setup: _Setup) -> frozenset[str]:
    """The template signals to hand ``ideal_observation``; a signal no latent day carries is refused."""
    derived = {d.output.value for d in default_derived_signals()}
    unknown = sorted(setup.needed - derived - _SUPPLIED - _GENERATED)
    if unknown:
        raise IdealObservationError(
            f"the phi_CP templates need the signal(s) {unknown}, which a latent day cannot supply"
        )
    return (
        setup.needed
    )  # the derived ones are dropped by ideal_observation: the monitor computes them


# ---------------------------------------------------------------------------------------------------
# The runner and its records
# ---------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Violation:
    """One violated phi_CP instance: the first VIOLATED record of its key, with the conventions applied."""

    kind: str
    template: TemplateId
    key: str
    onset: int
    end: int | None
    decided: int


def _run(
    run_fn: object,
    day: ObservedDay,
    plan: CarePlan,
    setup: _Setup,
) -> tuple[Any, ...]:
    runner = run_offline if run_fn is None else run_fn
    if not callable(runner):
        raise LabellingError(f"run_fn must be callable, got {_show(run_fn)}")
    try:
        result = runner(
            day,
            plan,
            setup.config,
            None,
            None,
            registry=setup.registry,
            templates=list(setup.templates),
        )
    except MemoryError:
        raise
    except Exception as exc:
        raise RunnerError(f"run_fn failed: {type(exc).__name__}") from exc
    if isinstance(result, OfflineResult):
        result = result.records
    return _items(result, "the runner's records", MAX_VERDICT_RECORDS, RunnerError)


def _window_ms(
    setup: _Setup, plan: _Plan, template: TemplateId, name: str, meaning: str
) -> int:
    """A window length: the plan's own parameter record of the template, else the registry."""
    override = plan.parameters.get(template, {}).get(name)
    if override is not None:
        value = override
    else:
        try:
            value = setup.registry.get(name).value
        except Exception as exc:
            raise LabellingError(
                f"the registry has no value for {name!r}, {meaning}: {exc}"
            ) from exc
    if _is_int(value):
        length = int(value)
    else:
        number = _finite(value, name, LabellingError)
        if number != math.floor(number):
            raise LabellingError(f"{name} must be a whole number of milliseconds")
        length = int(number)
    if length <= 0:
        raise LabellingError(f"{name} must be positive")
    return length


def _delta2(setup: _Setup, plan: _Plan) -> int:
    return _window_ms(
        setup, plan, TemplateId.RESP, "delta2", "the window length of RESP"
    )


def _hold_lookback(setup: _Setup, plan: _Plan) -> int:
    return _window_ms(
        setup, plan, TemplateId.HOLD, "hold_lookback", "the look-back of HOLD"
    )


def _violations(
    records: tuple[Any, ...], latent: _Latent, plan: _Plan, setup: _Setup
) -> list[_Violation]:
    lo, hi = latent.day_start, latent.day_end
    cp = {t.id for t in setup.templates}
    first: dict[str, VerdictRecord] = {}
    template_of: dict[str, TemplateId] = {}
    final: dict[str, VerdictState] = {}
    previous: int | None = None
    for record in records:
        if not isinstance(record, VerdictRecord):
            raise RunnerError(
                f"the runner returned {_show(record)} where a VerdictRecord belongs"
            )
        template = record.template
        state = record.state
        if not isinstance(template, TemplateId):
            raise RunnerError("a record has a template that is not a TemplateId")
        if not isinstance(state, VerdictState):
            raise RunnerError("a record has a state that is not a VerdictState")
        key = _text(record.instance_key, "a record's instance_key", RunnerError)
        t_eval = _int(record.t_eval_ms, "a record's t_eval_ms", RunnerError)
        decided = _optional_int(
            record.decided_at_ms, "a record's decided_at_ms", RunnerError
        )
        pending = _optional_int(
            record.pending_until_ms, "a record's pending_until_ms", RunnerError, 0
        )
        if previous is not None and t_eval < previous:
            raise RunnerError("the records are not in step order (t_eval_ms decreases)")
        previous = t_eval
        if template not in cp:
            continue  # SYS and INT are not phi_CP: their records never become C1
        if template is TemplateId.COUNT and plan.day_end_anchor.get(key, hi) != hi:
            # the day-end count of another day: its closing step is not this day's, and the run starts
            # with an empty history at this day's first step (a patient-level plan lists such instances)
            continue
        if not lo <= t_eval <= hi:
            raise RunnerError(
                f"a record of {key!r} is evaluated at {t_eval}, outside this day [{lo}, {hi}]"
            )
        if template_of.setdefault(key, template) is not template:
            raise RunnerError(f"the instance {key!r} appears under two templates")
        if template is TemplateId.SCHED and key not in plan.sched_anchor:
            raise RunnerError(
                f"{key!r} is a SCHED instance that the plan does not have"
            )
        definitive = state in (VerdictState.VIOLATED, VerdictState.SATISFIED)
        if definitive:
            if decided is None:
                raise RunnerError(
                    f"a definitive record of {key!r} has no decided_at_ms"
                )
            if decided > t_eval or not lo <= decided <= hi:
                raise RunnerError(
                    f"{key!r} is decided at {decided}, outside this day or after its evaluation"
                )
        known = final.get(key)
        if known is not None:
            if state is not known:  # a definitive state is absorbing
                raise RunnerError(
                    f"{key!r} changed from {known.value} to {state.value}"
                )
        elif definitive:
            final[key] = state
            if state is VerdictState.VIOLATED:
                first[key] = record
        if known is VerdictState.VIOLATED:
            earlier = first[key]
            if decided != earlier.decided_at_ms or pending != earlier.pending_until_ms:
                raise RunnerError(
                    f"{key!r} changed its decision or its deadline after it was decided"
                )
    found: list[_Violation] = []
    for key, record in first.items():
        found.append(_violation_of(record, key, plan, setup, latent))
    return found


def _violation_of(
    record: VerdictRecord, key: str, plan: _Plan, setup: _Setup, latent: _Latent
) -> _Violation:
    template = record.template
    decided = _int(record.decided_at_ms, "decided_at_ms", RunnerError)
    pending = _optional_int(record.pending_until_ms, "pending_until_ms", RunnerError, 0)
    onset: int
    end: int | None
    if template is TemplateId.RANGE:
        kind, onset, end = _K_RANGE, decided, None
    elif template is TemplateId.HOLD:
        kind, onset, end = _K_HOLD, decided, None
    elif template is TemplateId.COUNT and key not in plan.day_end_anchor:
        kind, onset, end = _K_LIMIT, decided, None
    else:
        if pending is None:
            raise RunnerError(
                f"{key!r} is a windowed obligation whose record has no pending_until_ms (its deadline)"
            )
        end = pending
        if template is TemplateId.SCHED:
            kind, onset = _K_SCHED, plan.sched_anchor[key]
        elif template is TemplateId.COUNT:
            kind, onset = _K_END, plan.day_end_anchor[key]
        else:
            kind = _K_RESP
            anchored = plan.resp_anchor.get(key)
            onset = anchored if anchored is not None else pending - _delta2(setup, plan)
        if end < onset:
            raise RunnerError(
                f"{key!r} has its deadline {end} before its anchor {onset}"
            )
    if not latent.day_start <= onset <= latent.day_end:
        raise RunnerError(f"{key!r} is anchored at {onset}, outside this day")
    return _Violation(kind, template, key, onset, end, decided)


# ---------------------------------------------------------------------------------------------------
# Injection records, behaviour log, link and natural subtypes
# ---------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _C1Record:
    index: int
    subtype: str
    kind: str
    onset: int
    end: int | None
    group: str | None
    intakes: frozenset[int] | None


def _read_injections(
    records: object,
) -> tuple[tuple[InjectionRecord, ...], list[_C1Record]]:
    items = _items(records, "injection records", MAX_INJECTION_RECORDS, LabellingError)
    c1: list[_C1Record] = []
    for index, record in enumerate(items):
        if not isinstance(record, InjectionRecord):
            raise LabellingError(
                f"records[{index}] must be an InjectionRecord, got {_show(record)}"
            )
        spec = record.spec
        if not isinstance(spec.cls, InjectedClass):
            raise LabellingError(
                f"records[{index}] has a class that is not an InjectedClass"
            )
        subtype = _text(spec.subtype, "a record subtype", LabellingError)
        realised = record.realised
        if not isinstance(realised, bool):
            raise LabellingError(f"records[{index}].realised must be a bool")
        onset = _int(
            record.realised_onset_ms, "a record's realised_onset_ms", LabellingError
        )
        end = _optional_int(
            record.realised_end_ms, "a record's realised_end_ms", LabellingError
        )
        group = record.confounder_group
        if group is not None:
            group = _text(group, "a record's confounder_group", LabellingError)
        if spec.cls is not InjectedClass.C1:
            continue
        if subtype not in LINK_TABLE:
            raise LabellingError(
                f"records[{index}] has the C1 subtype {subtype!r}, which is not one of {sorted(LINK_TABLE)}"
            )
        intakes = (
            _intake_times(record)
            if subtype == "drug_nonresponse" and realised
            else None
        )
        if realised:
            c1.append(
                _C1Record(
                    index,
                    subtype,
                    _LINK_KIND[LINK_TABLE[subtype]],
                    onset,
                    end,
                    group,
                    intakes,
                )
            )
    return items, c1


def _intake_times(record: InjectionRecord) -> frozenset[int]:
    details = record.details
    listed = details.get("intake_times_ms") if isinstance(details, Mapping) else None
    if listed is None:
        raise LabellingError(
            "a realised drug_nonresponse record has no details['intake_times_ms']: it cannot be linked"
        )
    times = _items(
        listed, "details['intake_times_ms']", MAX_INTAKES_PER_RECORD, LabellingError
    )
    return frozenset(
        _int(t, "details['intake_times_ms'] item", LabellingError, 0) for t in times
    )


def _read_behaviour(behaviour_log: object, latent: _Latent) -> list[BehaviourEntry]:
    """The entries of this day (entries of another day are not this day's slots)."""
    items = _items(
        behaviour_log, "behaviour_log", MAX_BEHAVIOUR_ENTRIES, LabellingError
    )
    today: list[BehaviourEntry] = []
    for entry in items:
        if not isinstance(entry, BehaviourEntry):
            raise LabellingError(
                f"behaviour_log items must be BehaviourEntry, got {_show(entry)}"
            )
        if not isinstance(entry.state, AdherenceState):
            raise LabellingError(
                "a behaviour entry has a state that is not an AdherenceState"
            )
        day = _int(entry.day_index, "a behaviour entry day_index", LabellingError)
        _int(entry.slot_tick_ms, "a behaviour entry slot_tick_ms", LabellingError)
        dispenses = tuple(
            _int(t, "a behaviour entry dispense time", LabellingError)
            for t in _items(
                entry.dispense_times_ms,
                "dispense_times_ms",
                MAX_DISPENSES_PER_SLOT,
                LabellingError,
            )
        )
        if entry.state is AdherenceState.OMITTED and dispenses:
            raise LabellingError("an omitted slot cannot have a dispense")
        if entry.state is AdherenceState.DOUBLE_TAKE and len(dispenses) < 2:
            raise LabellingError("a double-take slot needs at least two dispenses")
        if day == latent.day_index:
            today.append(entry)
    return today


class _Bound:
    """The template latency bound: the caller's function, else the monitor's ``verdict_latency_bound_ms``."""

    def __init__(self, fn: object, setup: _Setup) -> None:
        if fn is not None and not callable(fn):
            raise LabellingError(f"latency_bound_fn must be callable, got {_show(fn)}")
        self._fn: Any = fn
        self._setup = setup

    def __call__(self, template: TemplateId) -> int:
        if self._fn is None:
            try:
                monitor = StreamingMonitor(
                    self._setup.config,
                    self._setup.registry,
                    list(self._setup.templates),
                )
            except Exception as exc:
                raise LabellingError(
                    f"the latency bound of the monitor is not available: {type(exc).__name__}"
                ) from exc
            self._fn = monitor.verdict_latency_bound_ms
        try:
            bound = self._fn(template)
        except Exception as exc:
            raise LabellingError(
                f"latency_bound_fn failed: {type(exc).__name__}"
            ) from exc
        return _int(bound, "a latency bound", LabellingError, 0)


@dataclass(slots=True)
class _Context:
    latent: _Latent
    day: ObservedDay
    step: int
    bound: _Bound
    records: list[_C1Record]
    behaviour: list[BehaviourEntry]
    measurement_times: list[int]
    dispense_times: list[int]
    intake_of: dict[int, int]
    hold_lookback: Callable[[], int]  # read when a HOLD violation needs it


def _context(
    latent: _Latent,
    raw_latent: LatentDay,
    day: ObservedDay,
    setup: _Setup,
    bound: _Bound,
    records: list[_C1Record],
    behaviour: list[BehaviourEntry],
    plan: _Plan,
) -> _Context:
    measurement_times = sorted(
        e.t_device_ms for e in day.events if e.kind is EventKind.MEASUREMENT
    )
    dispense_times = sorted(
        e.t_device_ms for e in day.events if e.kind is EventKind.DISPENSE
    )
    intake_times = sorted(
        _int(e.t_device_ms, "a latent INTAKE time", LabellingError)
        for e in raw_latent.events
        if e.kind is EventKind.INTAKE
    )
    # the k-th DISPENSE of a day is followed by its k-th INTAKE (a constant lag keeps the order); when the
    # counts differ the pairing is unknown and the dispense instant stands in for the intake instant
    if len(intake_times) == len(dispense_times):
        intake_of = dict(zip(dispense_times, intake_times, strict=True))
    else:
        intake_of = {t: t for t in dispense_times}
    return _Context(
        latent,
        day,
        setup.config.step_ms,
        bound,
        records,
        behaviour,
        measurement_times,
        dispense_times,
        intake_of,
        lambda: _hold_lookback(setup, plan),
    )


def _anchor_of(t: int, ctx: _Context) -> int:
    origin = ctx.latent.day_start
    return origin + _bin_of(t, origin, ctx.step) * ctx.step


def _explaining(violation: _Violation, ctx: _Context) -> _C1Record | None:
    """The record that explains a violation: template by the link table, then the instant rule."""
    candidates: list[tuple[tuple[int, int], _C1Record]] = []
    template = violation.template
    for record in ctx.records:
        if record.kind != violation.kind:
            continue
        strict = False
        if violation.kind == _K_RESP:
            assert record.intakes is not None
            wanted = [
                ctx.intake_of[t]
                for t in ctx.dispense_times
                if _anchor_of(t, ctx) == violation.onset
            ]
            if not any(i in record.intakes for i in wanted):
                continue
        elif violation.kind == _K_LIMIT:
            # the counter looks back one day: the surplus dispense of the record lies in (decision - 24 h, decision]
            if not violation.decided - T_DAY_MS < record.onset <= violation.decided:
                continue
        else:
            bound = ctx.bound(template)
            reach = (record.end if record.end is not None else record.onset) + bound
            instants = [violation.decided]
            if violation.kind == _K_HOLD:
                # the violation is decided at the dispense but caused by the latest reading before it
                at = bisect.bisect_right(ctx.measurement_times, violation.decided) - 1
                # only a reading in the look-back window can have decided it (the refined form needs one)
                if (
                    at >= 0
                    and violation.decided - ctx.measurement_times[at]
                    <= ctx.hold_lookback()
                ):
                    instants.append(ctx.measurement_times[at])
            if not any(record.onset <= t < reach for t in instants):
                continue
            # a window record is strict when the instant lies in its own window, without the extension;
            # a point record has no window of its own
            strict = record.end is not None and any(
                record.onset <= t < record.end for t in instants
            )
        candidates.append(((0 if strict else 1, record.onset), record))
    # the records are visited in the order of the argument, and min keeps the first of equal keys
    return min(candidates, key=lambda c: c[0])[1] if candidates else None


def _natural_subtype(violation: _Violation, ctx: _Context) -> str:
    if violation.kind == _K_LIMIT:
        for entry in ctx.behaviour:
            if entry.state is AdherenceState.DOUBLE_TAKE and any(
                violation.decided - T_DAY_MS < t <= violation.decided
                for t in entry.dispense_times_ms[1:]
            ):
                return SUBTYPE_DOUBLE_TAKE
    elif violation.kind == _K_END and any(
        entry.state is AdherenceState.OMITTED for entry in ctx.behaviour
    ):
        return SUBTYPE_DOSE_OMISSION
    return SPONTANEOUS_PREFIX + violation.template.value


# ---------------------------------------------------------------------------------------------------
# The labeller
# ---------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LabelledDay:
    """The ground truth of one day and where each event comes from.

    ``events`` are sorted by ``(onset_ms, cls, subtype, end_ms)``; ``record_index[i]`` is the position in
    ``records`` of the injection record that explains the C1 event ``i`` or produced the C2 or C3 event ``i``
    (``None`` for a C1 event that no record explains); ``n_verdict_records`` is the number of records the
    runner returned.
    """

    events: tuple[GroundTruthEvent, ...]
    record_index: tuple[int | None, ...]
    n_verdict_records: int


def label_latent_day_detailed(
    latent: LatentDay,
    plan: CarePlan,
    records: Sequence[InjectionRecord],
    behaviour_log: Sequence[BehaviourEntry],
    run_fn: Callable[..., Any] | None = None,
    config: MonitorConfig | None = None,
    latency_bound_fn: Callable[[TemplateId], int] | None = None,
    mode: str = MODE_SCHEDULED,
    *,
    registry: Any | None = None,
    templates: Sequence[Template] | None = None,
) -> LabelledDay:
    """``label_latent_day`` with the provenance of each event (see ``LabelledDay``)."""
    try:
        return _label(
            latent,
            plan,
            records,
            behaviour_log,
            run_fn,
            config,
            latency_bound_fn,
            mode,
            registry,
            templates,
        )
    except LabellingError:
        raise
    except MemoryError:
        raise
    except Exception as exc:
        raise LabellingError(f"labelling failed: {type(exc).__name__}") from exc


def label_latent_day(
    latent: LatentDay,
    plan: CarePlan,
    records: Sequence[InjectionRecord],
    behaviour_log: Sequence[BehaviourEntry],
    run_fn: Callable[..., Any] | None = None,
    config: MonitorConfig | None = None,
    latency_bound_fn: Callable[[TemplateId], int] | None = None,
    mode: str = MODE_SCHEDULED,
    *,
    registry: Any | None = None,
    templates: Sequence[Template] | None = None,
) -> tuple[GroundTruthEvent, ...]:
    """The ground truth of a latent day: C1 from phi_CP on the latent trace, C2 and C3 from the records.

    ``records`` are all the injection records of the day (C1 records only explain C1 events, C2 and C3
    records give one event each when realised). ``behaviour_log`` is the adherence log of the day.
    ``run_fn`` runs the monitor on the ideal observation as ``run_offline`` does (``None``: ``run_offline``
    without calibrator and forecaster; a stub is accepted). ``config`` is the monitor configuration,
    ``latency_bound_fn`` the template latency bound (``None``: the one of the monitor), ``mode`` is
    ``scheduled`` or ``dense``. ``registry`` and ``templates`` default to the real registry and its template
    library. There is no observed-day parameter. Raises only ``LabellingError`` and its subclasses.
    """
    return label_latent_day_detailed(
        latent,
        plan,
        records,
        behaviour_log,
        run_fn,
        config,
        latency_bound_fn,
        mode,
        registry=registry,
        templates=templates,
    ).events


def _label(
    latent: object,
    plan: object,
    records: object,
    behaviour_log: object,
    run_fn: Any,
    config: Any,
    latency_bound_fn: Any,
    mode: Any,
    registry: Any,
    templates: Any,
) -> LabelledDay:
    day_latent = _read_latent(latent, LabellingError)
    read_plan = _read_plan(plan)
    if read_plan.patient_id != day_latent.patient_id:
        raise LabellingError("the plan is for another patient than the latent day")
    injections, c1_records = _read_injections(records)
    behaviour = _read_behaviour(behaviour_log, day_latent)
    setup = _setup(read_plan, config, registry, templates)
    signals = _check_supply(setup)
    assert isinstance(latent, LatentDay) and isinstance(plan, CarePlan)
    day = ideal_observation(
        latent,
        read_plan.care_plan_id,
        mode,
        step_ms=setup.config.step_ms,
        signals=sorted(signals),
    )
    verdicts = _run(run_fn, day, plan, setup)
    violations = _violations(verdicts, day_latent, read_plan, setup)
    bound = _Bound(latency_bound_fn, setup)
    ctx = _context(
        day_latent, latent, day, setup, bound, c1_records, behaviour, read_plan
    )

    entries: list[tuple[GroundTruthEvent, int | None]] = []
    for violation in violations:
        record = _explaining(violation, ctx)
        subtype = (
            record.subtype if record is not None else _natural_subtype(violation, ctx)
        )
        entries.append(
            (
                GroundTruthEvent(
                    InjectedClass.C1,
                    subtype,
                    violation.onset,
                    violation.end,
                    record is not None,
                    violation.template.value,
                    record.group if record is not None else None,
                ),
                record.index if record is not None else None,
            )
        )
    for index, injected in enumerate(injections):
        if injected.spec.cls is InjectedClass.C1:
            continue  # the C1 truth is the latent trace's: record_to_ground_truth would say injected, no template
        truth = record_to_ground_truth(injected)
        if truth is not None:
            entries.append((truth, index))
    entries.sort(key=_order)
    return LabelledDay(
        tuple(e for e, _ in entries), tuple(i for _, i in entries), len(verdicts)
    )


def _order(entry: tuple[GroundTruthEvent, int | None]) -> tuple[Any, ...]:
    event, index = entry
    return (
        event.onset_ms,
        event.cls.value,
        event.subtype,
        event.end_ms is not None,
        event.end_ms if event.end_ms is not None else 0,
        event.template_id or "",
        event.injected,
        event.confounder_group or "",
        -1 if index is None else index,
    )


# ---------------------------------------------------------------------------------------------------
# The benchmark day
# ---------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AssembledDay:
    """A ``BenchmarkDay`` and the truth file content (``TruthRecord``: latent, ground truth and the sidecars).

    ``BenchmarkDay`` has no room for the sidecars, so they travel in ``truth`` (what ``write_truth`` takes).
    """

    day: BenchmarkDay
    truth: TruthRecord


def assemble_benchmark_day(
    observed: ObservedDay,
    latent: LatentDay,
    plan: CarePlan,
    records: Sequence[InjectionRecord],
    behaviour_log: Sequence[BehaviourEntry],
    run_fn: Callable[..., Any] | None = None,
    config: MonitorConfig | None = None,
    latency_bound_fn: Callable[[TemplateId], int] | None = None,
    mode: str = MODE_SCHEDULED,
    *,
    registry: Any | None = None,
    templates: Sequence[Template] | None = None,
) -> AssembledDay:
    """The ``BenchmarkDay`` of an observed day and its latent day, with the truth and the sidecars.

    The observed day is stored as it is (never changed, never given a latent-derived field); it must be an
    ``ObservedDay`` of the same patient, day, seed and care plan (an ``ObservedStream`` carries the latent
    pressure of every reading and is refused). ``truth.injection_log`` has one entry per record, in the order
    of ``records``, with the keys ``INJECTION_LOG_BASE_KEYS`` and ``INJECTION_LOG_LINK_KEYS``;
    ``truth.behaviour_log`` is the list of the entries as JSON.
    """
    try:
        return _assemble(
            observed,
            latent,
            plan,
            records,
            behaviour_log,
            run_fn,
            config,
            latency_bound_fn,
            mode,
            registry,
            templates,
        )
    except LabellingError:
        raise
    except MemoryError:
        raise
    except Exception as exc:
        raise LabellingError(
            f"assembling the benchmark day failed: {type(exc).__name__}"
        ) from exc


def _assemble(
    observed: object,
    latent: object,
    plan: Any,
    records: Any,
    behaviour_log: Any,
    run_fn: Any,
    config: Any,
    latency_bound_fn: Any,
    mode: Any,
    registry: Any,
    templates: Any,
) -> AssembledDay:
    if not isinstance(observed, ObservedDay):
        raise LabellingError(
            f"observed must be an ObservedDay, got {_show(observed)} (an ObservedStream or a latent day carries latent values)"
        )
    read = _read_latent(latent, LabellingError)
    read_plan = _read_plan(plan)
    if (
        _text(observed.patient_id, "observed.patient_id", LabellingError)
        != read.patient_id
        or _int(observed.day_index, "observed.day_index", LabellingError)
        != read.day_index
        or _int(observed.seed, "observed.seed", LabellingError) != read.seed
        or _text(observed.care_plan_id, "observed.care_plan_id", LabellingError)
        != read_plan.care_plan_id
    ):
        raise LabellingError(
            "the observed day is not the day of this latent day and care plan"
        )
    try:
        validate_day(observed)
    except TraceError as exc:
        raise LabellingError(f"the observed day is invalid: {exc}") from exc
    assert isinstance(latent, LatentDay)
    labelled = label_latent_day_detailed(
        latent,
        plan,
        records,
        behaviour_log,
        run_fn,
        config,
        latency_bound_fn,
        mode,
        registry=registry,
        templates=templates,
    )
    items, _ = _read_injections(records)
    log = injection_log(list(items))
    links: dict[int, list[int]] = {}
    for position, index in enumerate(labelled.record_index):
        if index is not None:
            links.setdefault(index, []).append(position)
    sidecar: list[JsonValue] = []
    for index, entry in enumerate(log):
        full: dict[str, JsonValue] = dict(entry)
        full["record_index"] = index
        full["truth_indices"] = list(links.get(index, []))
        sidecar.append(full)
    behaviour = _items(
        behaviour_log, "behaviour_log", MAX_BEHAVIOUR_ENTRIES, LabellingError
    )
    behaviour_json: list[JsonValue] = [dict(b.to_json()) for b in behaviour]
    return AssembledDay(
        BenchmarkDay(observed, latent, labelled.events),
        TruthRecord(latent, labelled.events, sidecar, behaviour_json),
    )
