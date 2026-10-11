"""C2 fault injection: device, link and robot failures on the observed stream (WS04-T07).

One function per subtype of the vocabulary of ``docs/models/fault-model.md`` (the section
"Subtype vocabulary"; ``C2_SUBTYPES`` are the eight that benchmark v1 injects). Each takes the
working copy of the stream, the specs of its subtype in canonical order and the context, and
returns one ``InjectionRecord`` per spec. The pipeline, the canonical order, the spec rules
and the ground-truth mapping are in ``ralmon.benchmark.injection``; this module registers its
injectors there. The latent day is never an argument of an injector (``context.latent`` is
read, never written, by ``nav_delay``).

Conventions used by every injector
  * A window is ``[onset, onset + duration)`` on ``t_device_ms``: an item exactly at the
    onset is inside, one exactly at the end is outside. Before the link stage
    ``t_rx_ms == t_device_ms``.
  * ``n_changed`` counts the items removed, changed, moved or added; the injection is
    realised when it is positive. An injection that finds nothing leaves the stream as it was
    and no event of the node is emitted for it.
  * Device faults run in the order ``cuff_detached``, ``cuff_silent_bias``, ``stuck_at``,
    ``ecg_noise``, ``dispenser_bounce``: a detached attempt has no pressure to shift, and a
    stuck cuff freezes the value that the (possibly biased) cuff last reported.

Subtypes
  ``ble_dropout`` (link, one device): every sample and event of the device with its
    ``t_device_ms`` in the window is removed, the node reports of the device included (loss, not
    delay: nothing arrives later). The gateway reports ``NODE_STATE`` ``link_down`` at the
    window start and ``active`` at its end (uncommanded; ward clock, H-WARDCLK; source the
    device). The sequence numbers are assigned before the link stage, so the delivered
    numbers keep the gap. No lease parameter exists in this generator (EC-OP-18), so the
    ``unreachable`` report of a window longer than the liveliness lease is **not** produced;
    ``system.liveliness_ok`` and ``system.qos_deadline_missed`` of the signature are the
    conditional paths of condition LC and are only listed.
  ``stuck_at`` (cuff): from the onset every ``bp`` sample of the window repeats the last value
    the cuff reported strictly before the onset. With no earlier reading in the stream there is
    nothing to freeze and the injection is not realised. The pulse and the events are not
    frozen; the signature is empty (a declared diagnosability limit).
  ``cuff_silent_bias`` (cuff): ``bp`` samples of the window plus ``magnitude`` mmHg (signed);
    nothing else changes; empty signature (declared limit, analisi section 4.8).
  ``cuff_detached`` (cuff): each ``MEASUREMENT`` event of the window becomes a failed attempt: no
    ``bp`` sample and no pulse sample, a ``MEASUREMENT_MISSED`` event, a ``DEVICE_ERROR`` event
    with the generator-defined label ``DETACHED_ERROR_CODE`` (not a vendor code), a
    ``cuff_health`` sample of ``DETACHED_HEALTH`` and an ``inflation_ms`` sample of
    ``DETACHED_INFLATION_MS`` (no inflation: below any positive registry minimum). The
    failed attempt keeps the sequence number of its message (no gap). The cuff node reports
    ``NODE_STATE`` ``inactive`` (uncommanded) at the window start and ``active`` at its end
    (OP-16: the benchmark adds the event, so ``system.node_lifecycle`` is in the signature).
  ``ecg_noise`` (ECG device): the ``hr_ecg`` samples of the window get the paired error trace
    of the library (kind ``hr_error_ecg_noise``) added, scaled by ``magnitude`` (the factor
    ``noise_level``; 1 when absent). Sample ``j`` of the window takes error ``(t - onset) //
    period``. ``Sample.quality`` becomes the quality of the trace when the library carries one,
    otherwise None. Without that kind the subtype is **disabled**: the record is unrealised,
    the subtype is listed in ``InjectionResult.disabled_subtypes`` and nothing is raised.
  ``dispenser_bounce`` (dispenser, point fault): a second ``DISPENSE`` event ``gap_ms`` (the
    magnitude) after the real dispense at the onset; no ``INTAKE``; ``content_change`` 0.0 when
    the dispenser senses its content, no key otherwise. It gets its own sequence number
    (a bounce that repeated the real one would be a duplicate and not counted, fault model
    section Device faults). It affects ``count``, ``hold``, ``resp`` and ``int`` (M-DUPWIN,
    FX-16) through the duplicate instance; the evidence signature is the dispenser group of
    ``#evidencevector`` 0.2.0 (the interval and the content change, conditional on the dispenser
    reporting them; the generator's emission of the interval key is WS04-T18). One record per bounce; ``plan_dispenser_bounces`` draws
    which dispenses bounce from ``DeviceErrorModel.dispenser_bounce_prob``.
  ``nav_delay`` (robot, per tick): the visit of the tick (``kind`` measurement by default, or
    dose) arrives ``magnitude`` ms later: its presence sample and navigation outcome move, the
    measurement it carries moves by the same delay and every item of the measurement keeps its
    value, except ``bp`` which, when the context has the latent day, is re-read from it at the
    new instant with the same cuff error (the noise draw of the measurement is unchanged: it
    is keyed by the measurement index, not by the time). The pulse keeps its value. An
    intake that no visit covers any more is no longer witnessed. **Stamp rule (H-OVERRUN,
    EC-OP-14):** the deadline of the task is the tick plus ``context.task_deadline_offset_ms``;
    if the delayed arrival is after it, the navigation outcome is ``late`` and the ``ROBOT_TASK``
    event is stamped with the deadline, not with the arrival or the delayed measurement, so
    that ``system.nav_task_failed`` can see it (an outcome stamped after the decision time of
    the violated instance is invisible to it); on time, the outcome stays ``success`` at the
    new arrival. One outcome per visit is kept (the late completion publishes nothing more).
  ``manipulation_failure`` (robot, per tick): the manipulation step of the visit fails. At a
    measurement visit the measurement is never made (no sample of it, no ``MEASUREMENT`` event;
    the generator-side record is dropped); at a dose visit the witnessed ``INTAKE`` events of
    that visit that no other visit covers are removed (the witness is ``None``, not a denial).
    A ``ROBOT_TASK`` event with task ``manipulate`` and outcome ``failed`` is added, stamped
    where the missing item would have been (the reading instant, or the arrival at a dose
    visit); the navigation of the visit stays ``success`` and its presence stays. A ``failed``
    outcome stamped after the decision time of an instance is invisible to it (EC-OP-14).

The ``NODE_STATE`` report of the robot with ``colocated`` (availability of the robot channels,
H-MASK) is **not** emitted here: the fault model and the evidence document do not assign it
to a C2 injection; its owner is still open (proposed WS04-T11).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any, Final

from ralmon.benchmark import vocab
from ralmon.benchmark.injection import (
    MAGNITUDE_MS,
    MAGNITUDE_NONE,
    MAGNITUDE_POSITIVE,
    MAGNITUDE_REAL,
    MAX_TIME_MS,
    SHAPE_POINT,
    SHAPE_TICK,
    SHAPE_WINDOW,
    STAGE_DEVICE,
    STAGE_LINK,
    STAGE_ROBOT,
    InjectionContext,
    InjectionContextError,
    InjectionError,
    InjectionRecord,
    InjectionSpec,
    InjectionSpecError,
    InjectionWork,
    Injector,
    check_call,
    injection_rng,
    register_injector,
    stable_index,
)
from ralmon.benchmark.latent import T_DAY_MS
from ralmon.benchmark.measurement import (
    LatentSbpHold,
    MeasurementConfigError,
    MeasurementRecord,
    RobotVisit,
)
from ralmon.benchmark.rng import StreamKeyError, StreamPurpose, stream
from ralmon.benchmark.segments import (
    KIND_HR_ERROR_ECG_NOISE,
    MAX_DRAW_SAMPLES,
    SegmentError,
)
from ralmon.benchmark.trace import InjectedClass
from ralmon.signals import Event, EventKind, Sample, SignalId

__all__ = [
    "C2_SUBTYPES",
    "DETACHED_ERROR_CODE",
    "DETACHED_HEALTH",
    "DETACHED_INFLATION_MS",
    "DEVICE_SIGNALS",
    "EVIDENCE_SIGNATURES",
    "MAX_PLANNED_DISPENSES",
    "TEMPLATES_AFFECTED",
    "ble_dropout",
    "cuff_detached",
    "cuff_silent_bias",
    "dispenser_bounce",
    "ecg_noise",
    "manipulation_failure",
    "nav_delay",
    "plan_dispenser_bounces",
    "stuck_at",
]

MAX_PLANNED_DISPENSES: Final[int] = (
    100_000  # algorithmic: dispenses given to the planner
)
DETACHED_ERROR_CODE: Final = "CUFF_E01"  # a generator-defined opaque code: not a vendor code, not a ground-truth label
DETACHED_HEALTH: Final = 0.0  # cuff_health of a failed attempt (1.0 is healthy)
DETACHED_INFLATION_MS: Final = 0  # no inflation: below any positive registry minimum

_BP: Final = SignalId.BP.value
_INFLATION: Final = SignalId.INFLATION_MS.value
_HEALTH: Final = SignalId.CUFF_HEALTH.value
_PULSE: Final = SignalId.HR_PULSE.value
_HR_ECG: Final = SignalId.HR_ECG.value
_SPO2: Final = SignalId.SPO2.value
_AUTH: Final = SignalId.AUTH.value
_PRESENCE: Final = SignalId.PRESENCE.value
_CUFF_SIGNALS: Final = (_BP, _INFLATION, _HEALTH, _PULSE)

# Which signals a BLE device produces (a Sample has no source field, TM-GAP-SEQKEY); the events
# of a device are the events whose ``source`` is its identifier.
DEVICE_SIGNALS: Final[dict[str, frozenset[str]]] = {
    vocab.SOURCE_CUFF: frozenset(_CUFF_SIGNALS),
    vocab.SOURCE_DISPENSER: frozenset({_AUTH}),
    vocab.SOURCE_ECG: frozenset({_HR_ECG}),
    vocab.SOURCE_OXIMETER: frozenset({_SPO2}),
}

# Transcribed by hand from the column "EvidenceVector paths raised" of the device, link and
# robot tables of docs/models/fault-model.md (a test compares the two). The set of paths of a
# fault is the union of its raised and conditional fields; a conditional path belongs to the
# evidence of a realised injection only when its condition holds there (LC, SEQ, D-5).
EVIDENCE_SIGNATURES: Final[dict[str, tuple[str, ...]]] = {
    "ble_dropout": (
        "system.node_lifecycle",
        "system.liveliness_ok",
        "system.qos_deadline_missed",
        "system.ble_link_quality",
        "system.seq_gap",
    ),
    "stuck_at": ("signal_quality.cuff_value_repeated",),
    "cuff_silent_bias": (),
    "ecg_noise": ("signal_quality.ecg_sqi", "cross_device.pulse_vs_ecg_hr_diff"),
    "nav_delay": ("system.nav_task_failed",),
    "manipulation_failure": ("system.manip_task_failed",),
    "dispenser_bounce": (
        "dispenser.interval_since_previous_ms",
        "dispenser.content_change",
    ),
    "cuff_detached": ("signal_quality.cuff_error_code", "system.node_lifecycle"),
}
C2_SUBTYPES: Final = tuple(EVIDENCE_SIGNATURES)

# The templates a realised injection may make violated, transcribed by hand from the column
# "templates that may become violated" of the same tables (a test compares the two). The record
# lists them in ``details["templates"]``: a ``dispenser_bounce`` reaches ``count``, ``hold``,
# ``resp`` and ``int`` through the duplicate instance of the extra dispense (M-DUPWIN, FX-16)
# although it raises no evidence field, and ``ecg_noise`` reaches none (no template reads
# ``hr_ecg``).
TEMPLATES_AFFECTED: Final[dict[str, tuple[str, ...]]] = {
    "ble_dropout": ("sched", "resp", "hold", "count"),
    "stuck_at": ("range", "hold", "resp"),
    "cuff_silent_bias": ("range", "hold", "resp"),
    "ecg_noise": (),
    "nav_delay": ("sched", "resp", "hold"),
    "manipulation_failure": ("sched", "resp", "hold"),
    "dispenser_bounce": ("count", "hold", "resp", "int"),
    "cuff_detached": ("sched", "resp", "hold"),
}

_KIND_DEFAULT: Final = vocab.KIND_MEASUREMENT


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _window(spec: InjectionSpec) -> tuple[int, int]:
    assert (
        spec.duration_ms is not None
    )  # a window fault: the pipeline checked the shape
    return spec.onset_ms, spec.onset_ms + spec.duration_ms


def _target(spec: InjectionSpec, default: str) -> str:
    target = spec.params.get("target", default)
    return target if isinstance(target, str) else default


def _record(
    spec: InjectionSpec, n_changed: int, details: dict[str, Any]
) -> InjectionRecord:
    end = None if spec.duration_ms is None else spec.onset_ms + spec.duration_ms
    return InjectionRecord(
        spec,
        spec.onset_ms,
        end,
        n_changed > 0,
        n_changed,
        EVIDENCE_SIGNATURES[spec.subtype],
        spec.level,
        spec.confounder_group,
        {**details, "templates": list(TEMPLATES_AFFECTED[spec.subtype])},
    )


def _node_state(source: str, t: int, state: str) -> Event:
    payload: dict[str, float | int | str | bool] = {
        vocab.KEY_STATE: state,
        vocab.KEY_COMMANDED: False,
    }
    return Event(EventKind.NODE_STATE, t, t, source, payload, None)


def _finite(value: float, what: str) -> float:
    if not math.isfinite(value):
        raise InjectionSpecError(f"{what} is not finite")
    return value


def _first(items: Sequence[Any], match: Any) -> int | None:
    for i, item in enumerate(items):
        if match(item):
            return i
    return None


# ---------------------------------------------------------------------------
# Link and device faults
# ---------------------------------------------------------------------------


def ble_dropout(
    work: InjectionWork, specs: Sequence[InjectionSpec], context: InjectionContext
) -> tuple[InjectionRecord, ...]:
    """Lose everything a device sent in the window; the gateway reports the link (module docstring)."""
    specs = check_call(work, specs, context, "ble_dropout")
    records: list[InjectionRecord] = []
    gateway: list[Event] = []
    for spec in specs:
        target = _target(spec, vocab.SOURCE_CUFF)
        signals = DEVICE_SIGNALS[target]
        onset, end = _window(spec)
        samples = [
            s
            for s in work.samples
            if not (s.signal in signals and onset <= s.t_device_ms < end)
        ]
        events = [
            e
            for e in work.events
            if not (e.source == target and onset <= e.t_device_ms < end)
        ]
        n_samples = len(work.samples) - len(samples)
        n_events = len(work.events) - len(events)
        work.samples, work.events = samples, events
        n = 0
        if n_samples + n_events > 0:
            gateway.append(_node_state(target, onset, vocab.STATE_LINK_DOWN))
            gateway.append(_node_state(target, end, vocab.STATE_ACTIVE))
            n = n_samples + n_events + 2  # the two reports of the gateway
        records.append(
            _record(
                spec,
                n,
                {
                    "target": target,
                    "n_samples_removed": n_samples,
                    "n_events_removed": n_events,
                },
            )
        )
    work.events.extend(gateway)  # after every removal: a later window cannot lose them
    return tuple(records)


def stuck_at(
    work: InjectionWork, specs: Sequence[InjectionSpec], context: InjectionContext
) -> tuple[InjectionRecord, ...]:
    """Freeze the cuff pressure at the last value reported strictly before the onset."""
    specs = check_call(work, specs, context, "stuck_at")
    records: list[InjectionRecord] = []
    for spec in specs:
        onset, end = _window(spec)
        frozen: float | None = None
        last_t: int | None = None
        for s in work.samples:
            if (
                s.signal == _BP
                and s.t_device_ms < onset
                and (last_t is None or s.t_device_ms >= last_t)
            ):
                frozen, last_t = s.value, s.t_device_ms
        n = 0
        details: dict[str, Any] = {"target": vocab.SOURCE_CUFF}
        if frozen is None:
            details["reason"] = "no earlier reading to freeze"
        else:
            details["frozen_value"] = frozen
            for i, s in enumerate(work.samples):
                if (
                    s.signal == _BP
                    and onset <= s.t_device_ms < end
                    and s.value != frozen
                ):
                    work.samples[i] = replace(s, value=frozen)
                    n += 1
        records.append(_record(spec, n, details))
    return tuple(records)


def cuff_silent_bias(
    work: InjectionWork, specs: Sequence[InjectionSpec], context: InjectionContext
) -> tuple[InjectionRecord, ...]:
    """Add the offset (mmHg, signed) to the pressure the cuff reports in the window."""
    specs = check_call(work, specs, context, "cuff_silent_bias")
    records: list[InjectionRecord] = []
    for spec in specs:
        onset, end = _window(spec)
        offset = spec.magnitude if spec.magnitude is not None else 0.0
        n = 0
        for i, s in enumerate(work.samples):
            if s.signal == _BP and onset <= s.t_device_ms < end:
                shifted = _finite(s.value + offset, "the biased reading")
                if shifted != s.value:
                    work.samples[i] = replace(s, value=shifted)
                    n += 1
        records.append(
            _record(spec, n, {"target": vocab.SOURCE_CUFF, "bias_mmhg": offset})
        )
    return tuple(records)


def cuff_detached(
    work: InjectionWork, specs: Sequence[InjectionSpec], context: InjectionContext
) -> tuple[InjectionRecord, ...]:
    """Turn every measurement of the window into a failed attempt (module docstring)."""
    specs = check_call(work, specs, context, "cuff_detached")
    records: list[InjectionRecord] = []
    source = vocab.SOURCE_CUFF
    for spec in specs:
        onset, end = _window(spec)
        slots: dict[int, dict[str, list[int]]] = {}
        for i, s in enumerate(work.samples):
            if s.signal in _CUFF_SIGNALS and onset <= s.t_device_ms < end:
                slots.setdefault(s.t_device_ms, {}).setdefault(s.signal, []).append(i)
        attempts = [
            i
            for i, e in enumerate(work.events)
            if e.kind is EventKind.MEASUREMENT
            and e.source == source
            and onset <= e.t_device_ms < end
        ]
        drop: set[int] = set()
        added_samples: list[Sample] = []
        added_events: list[Event] = []
        n = 0
        for i in attempts:
            event = work.events[i]
            t = event.t_device_ms
            slot = slots.get(t, {})
            for signal in (
                _BP,
                _PULSE,
            ):  # a failed attempt reports no pressure and no pulse
                found = slot.get(signal)
                if found:
                    drop.add(found.pop(0))
                    n += 1
            for signal, value in (
                (_HEALTH, DETACHED_HEALTH),
                (_INFLATION, float(DETACHED_INFLATION_MS)),
            ):
                found = slot.get(signal)
                if found:
                    j = found.pop(0)
                    old = work.samples[j]
                    if old.value != value or old.quality is not None:
                        work.samples[j] = replace(old, value=value, quality=None)
                        n += 1
                else:
                    added_samples.append(
                        Sample(signal, t, event.t_rx_ms, value, None, None)
                    )
                    n += 1
            work.events[i] = replace(
                event, kind=EventKind.MEASUREMENT_MISSED, payload={}
            )
            code: dict[str, float | int | str | bool] = {
                vocab.KEY_ERROR_CODE: DETACHED_ERROR_CODE
            }
            added_events.append(
                Event(EventKind.DEVICE_ERROR, t, event.t_rx_ms, source, code, None)
            )
            n += 2
        if attempts:
            added_events.append(_node_state(source, onset, vocab.STATE_INACTIVE))
            added_events.append(_node_state(source, end, vocab.STATE_ACTIVE))
            n += 2
        work.samples = [s for i, s in enumerate(work.samples) if i not in drop]
        work.samples.extend(added_samples)
        work.events.extend(added_events)
        records.append(
            _record(
                spec,
                n,
                {
                    "target": source,
                    "n_attempts": len(attempts),
                    "error_code": DETACHED_ERROR_CODE,
                },
            )
        )
    return tuple(records)


def ecg_noise(
    work: InjectionWork, specs: Sequence[InjectionSpec], context: InjectionContext
) -> tuple[InjectionRecord, ...]:
    """Add the paired real error trace to the ECG heart rate of the window (or disable)."""
    specs = check_call(work, specs, context, "ecg_noise")
    records: list[InjectionRecord] = []
    library = context.library
    for spec in specs:
        details: dict[str, Any] = {"target": vocab.SOURCE_ECG}
        if library is None or not library.has_kind(KIND_HR_ERROR_ECG_NOISE):
            work.disabled.add(spec.subtype)
            details["disabled"] = (
                f"no segment of kind {KIND_HR_ERROR_ECG_NOISE!r} in the library"
            )
            records.append(_record(spec, 0, details))
            continue
        onset, end = _window(spec)
        scale = 1.0 if spec.magnitude is None else spec.magnitude
        inside = [
            i
            for i, s in enumerate(work.samples)
            if s.signal == _HR_ECG and onset <= s.t_device_ms < end
        ]
        n = 0
        if inside:
            try:
                period = library.sample_period_ms(KIND_HR_ERROR_ECG_NOISE)
                last = max(work.samples[i].t_device_ms for i in inside)
                need = (last - onset) // period + 1
                if need > MAX_DRAW_SAMPLES:
                    raise InjectionSpecError(
                        f"the window needs {need} noise samples, more than {MAX_DRAW_SAMPLES}"
                    )
                draw = library.draw(
                    KIND_HR_ERROR_ECG_NOISE, need, injection_rng(work, context, spec)
                )
            except SegmentError as exc:
                raise InjectionContextError(
                    f"the noise segments cannot be drawn: {exc}"
                ) from exc
            for i in inside:
                s = work.samples[i]
                j = (s.t_device_ms - onset) // period
                value = _finite(
                    s.value + scale * draw.values[j], "the noisy heart rate"
                )
                quality = None if draw.quality is None else draw.quality[j]
                if value != s.value or quality != s.quality:
                    work.samples[i] = replace(s, value=value, quality=quality)
                    n += 1
            details["segment_ids"] = list(draw.segment_ids)
            details["join_count"] = draw.join_count
        details["scale"] = scale
        records.append(_record(spec, n, details))
    return tuple(records)


def dispenser_bounce(
    work: InjectionWork, specs: Sequence[InjectionSpec], context: InjectionContext
) -> tuple[InjectionRecord, ...]:
    """Add one extra DISPENSE ``gap`` ms after the real one at the onset (no INTAKE)."""
    specs = check_call(work, specs, context, "dispenser_bounce")
    records: list[InjectionRecord] = []
    source = vocab.SOURCE_DISPENSER
    real = {
        e.t_device_ms
        for e in work.events
        if e.kind is EventKind.DISPENSE and e.source == source
    }
    for spec in specs:
        assert spec.magnitude is not None  # a bounce has a gap: the pipeline checked it
        gap = int(spec.magnitude)
        n = 0
        details: dict[str, Any] = {"target": source, "gap_ms": gap}
        if spec.onset_ms in real:
            t = spec.onset_ms + gap
            payload: dict[str, float | int | str | bool] = {}
            if context.dispenser_content_sensing:
                payload[vocab.KEY_CONTENT_CHANGE] = (
                    0.0  # no content leaves the dispenser
                )
            work.events.append(Event(EventKind.DISPENSE, t, t, source, payload, None))
            n = 1
        else:
            details["reason"] = "no real dispense at the onset"
        records.append(_record(spec, n, details))
    return tuple(records)


# ---------------------------------------------------------------------------
# Robot faults
# ---------------------------------------------------------------------------


def _visit_of(work: InjectionWork, spec: InjectionSpec) -> int | None:
    kind = spec.params.get("kind", _KIND_DEFAULT)
    return _first(work.visits, lambda v: v.kind == kind and v.tick_ms == spec.onset_ms)


def _record_of(work: InjectionWork, visit: RobotVisit) -> MeasurementRecord | None:
    if visit.kind != vocab.KIND_MEASUREMENT:
        return None
    found = _first(work.measurements, lambda m: m.index == visit.index)
    return None if found is None else work.measurements[found]


def _covered(work: InjectionWork, t: int) -> bool:
    """Whether a visit that has not failed is in the room at ``t`` (closed dwell interval)."""
    return any(
        v.arrival_ms <= t <= v.departure_ms
        and (v.kind, v.index) not in work.failed_visits
        for v in work.visits
    )


def _drop_unwitnessed_intakes(work: InjectionWork, window: tuple[int, int]) -> int:
    """Remove the witnessed INTAKE events of ``window`` that no visit covers any more."""
    lo, hi = window
    keep: list[Event] = []
    for e in work.events:
        if (
            e.kind is EventKind.INTAKE
            and e.source == vocab.SOURCE_ROBOT
            and lo <= e.t_device_ms <= hi
            and not _covered(work, e.t_device_ms)
        ):
            continue
        keep.append(e)
    removed = len(work.events) - len(keep)
    work.events = keep
    return removed


def _take_sample(work: InjectionWork, signal: str, t: int) -> int | None:
    return _first(work.samples, lambda s: s.signal == signal and s.t_device_ms == t)


def _latent_hold(
    work: InjectionWork, context: InjectionContext
) -> LatentSbpHold | None:
    if context.latent is None:
        return None
    if work.latent_hold is None:
        try:
            work.latent_hold = LatentSbpHold(context.latent.samples)
        except MeasurementConfigError as exc:
            raise InjectionContextError(
                f"the latent day cannot be read: {exc}"
            ) from exc
    return work.latent_hold


def nav_delay(
    work: InjectionWork, specs: Sequence[InjectionSpec], context: InjectionContext
) -> tuple[InjectionRecord, ...]:
    """Delay one robot visit and the measurement it carries (module docstring, stamp rule)."""
    specs = check_call(work, specs, context, "nav_delay")
    records: list[InjectionRecord] = []
    offset = context.task_deadline_offset_ms
    if offset is None:
        raise InjectionContextError(
            "nav_delay needs context.task_deadline_offset_ms (the registry sched_window)"
        )
    for spec in specs:
        assert spec.magnitude is not None  # a delay: the pipeline checked it
        delay = int(spec.magnitude)
        kind = str(spec.params.get("kind", _KIND_DEFAULT))
        at = _visit_of(work, spec)
        details: dict[str, Any] = {"kind": kind, "delay_ms": delay}
        if at is None:
            details["reason"] = "no visit at that tick"
            records.append(_record(spec, 0, details))
            continue
        visit = work.visits[at]
        arrival = visit.arrival_ms + delay
        deadline = visit.tick_ms + offset
        late = arrival > deadline
        n = 0
        presence = _take_sample(work, _PRESENCE, visit.arrival_ms)
        if presence is not None:
            work.samples[presence] = replace(
                work.samples[presence], t_device_ms=arrival, t_rx_ms=arrival
            )
            n += 1
        task = _first(
            work.events,
            lambda e, t=visit.arrival_ms: (
                e.kind is EventKind.ROBOT_TASK
                and e.source == vocab.SOURCE_ROBOT
                and e.t_device_ms == t
                and e.payload.get(vocab.KEY_TASK) == vocab.TASK_NAVIGATE
                and e.payload.get(vocab.KEY_OUTCOME) == vocab.OUTCOME_SUCCESS
            ),
        )
        if task is not None:
            event = work.events[task]
            if late:
                payload = dict(event.payload)
                payload[vocab.KEY_OUTCOME] = vocab.OUTCOME_LATE
                work.events[task] = replace(
                    event, t_device_ms=deadline, t_rx_ms=deadline, payload=payload
                )
            else:
                work.events[task] = replace(event, t_device_ms=arrival, t_rx_ms=arrival)
            n += 1
        reread = False
        record = _record_of(work, visit)
        if record is not None:
            n_moved, reread = _move_measurement(work, context, record, delay)
            n += n_moved
        old_window = (visit.arrival_ms, visit.departure_ms)
        work.visits[at] = replace(
            visit,
            arrival_ms=arrival,
            departure_ms=visit.departure_ms + delay,
            delay_ms=visit.delay_ms + delay,
        )
        n += _drop_unwitnessed_intakes(work, old_window)
        details.update(
            {
                "late": late,
                "deadline_ms": deadline,
                "new_arrival_ms": arrival,
                "reread_latent": reread,
            }
        )
        records.append(_record(spec, n, details))
    return tuple(records)


def _move_measurement(
    work: InjectionWork,
    context: InjectionContext,
    record: MeasurementRecord,
    delay: int,
) -> tuple[int, bool]:
    """Move the items of a measurement by ``delay``; re-read ``bp`` from the latent day."""
    old, new = record.t_ms, record.t_ms + delay
    n = 0
    value = record.value_mmhg
    latent_value = record.latent_sbp_mmhg
    hold = _latent_hold(work, context)
    reread = hold is not None
    if hold is not None:
        try:
            latent_value = hold.at(new)
        except MeasurementConfigError as exc:
            raise InjectionContextError(
                f"the latent day cannot be read: {exc}"
            ) from exc
        value = _finite(latent_value + record.error_mmhg, "the re-read reading")
    for signal in _CUFF_SIGNALS:
        i = _take_sample(work, signal, old)
        if i is None:
            continue
        s = work.samples[i]
        moved = replace(
            s, t_device_ms=new, t_rx_ms=new, value=value if signal == _BP else s.value
        )
        work.samples[i] = moved
        n += 1
    j = _first(
        work.events,
        lambda e: (
            e.kind is EventKind.MEASUREMENT
            and e.source == vocab.SOURCE_CUFF
            and e.t_device_ms == old
        ),
    )
    if j is not None:
        work.events[j] = replace(work.events[j], t_device_ms=new, t_rx_ms=new)
        n += 1
    k = _first(work.measurements, lambda m: m.index == record.index)
    if k is not None:
        work.measurements[k] = replace(
            record,
            arrival_ms=record.arrival_ms + delay,
            t_ms=new,
            latent_sbp_mmhg=latent_value,
            value_mmhg=value,
        )
    return n, reread


def manipulation_failure(
    work: InjectionWork, specs: Sequence[InjectionSpec], context: InjectionContext
) -> tuple[InjectionRecord, ...]:
    """Fail the manipulation step of one visit (module docstring)."""
    specs = check_call(work, specs, context, "manipulation_failure")
    records: list[InjectionRecord] = []
    for spec in specs:
        kind = str(spec.params.get("kind", _KIND_DEFAULT))
        at = _visit_of(work, spec)
        details: dict[str, Any] = {"kind": kind}
        if at is None:
            details["reason"] = "no visit at that tick"
            records.append(_record(spec, 0, details))
            continue
        visit = work.visits[at]
        stamp = visit.arrival_ms
        n = 0
        record = _record_of(work, visit)
        if record is not None:
            stamp = record.t_ms
            for (
                signal
            ) in _CUFF_SIGNALS:  # the measurement was never made: no cuff sample of it
                i = _take_sample(work, signal, record.t_ms)
                if i is not None:
                    del work.samples[i]
                    n += 1
            j = _first(
                work.events,
                lambda e, t=record.t_ms: (
                    e.kind is EventKind.MEASUREMENT
                    and e.source == vocab.SOURCE_CUFF
                    and e.t_device_ms == t
                ),
            )
            if j is not None:
                del work.events[j]
                n += 1
            work.measurements = [m for m in work.measurements if m is not record]
        work.failed_visits.add((visit.kind, visit.index))
        if visit.kind == vocab.KIND_DOSE:
            n += _drop_unwitnessed_intakes(work, (visit.arrival_ms, visit.departure_ms))
        payload: dict[str, float | int | str | bool] = {
            vocab.KEY_TASK: vocab.TASK_MANIPULATE,
            vocab.KEY_OUTCOME: vocab.OUTCOME_FAILED,
            vocab.KEY_PATIENT_ID: work.patient_id,
        }
        work.events.append(
            Event(EventKind.ROBOT_TASK, stamp, stamp, vocab.SOURCE_ROBOT, payload, None)
        )
        n += 1
        details["stamp_ms"] = stamp
        records.append(_record(spec, n, details))
    return tuple(records)


# ---------------------------------------------------------------------------
# Planning the bounces
# ---------------------------------------------------------------------------


def plan_dispenser_bounces(
    dispense_times_ms: Sequence[int],
    probability: float,
    gap_ms: int,
    *,
    seed: int,
    patient_index: int,
    day_index: int,
) -> list[InjectionSpec]:
    """The bounce specs of the dispenses that bounce, each with probability ``probability``.

    ``probability`` is ``DeviceErrorModel.dispenser_bounce_prob`` (per dispense) and ``gap_ms``
    the gap of a design level. Dispense ``i`` bounces when the first uniform number of the
    stream ``(seed, patient, day, INJECTION_C2, stable_index("bounce_plan", time))`` is below
    the probability: the draw depends on the dispense time only, so adding or removing a
    dispense shifts no other draw. The times must be strictly increasing; the result is sorted
    by onset.
    """
    if (
        isinstance(dispense_times_ms, (str, bytes))
        or not isinstance(dispense_times_ms, (list, tuple))
        or len(dispense_times_ms) > MAX_PLANNED_DISPENSES
    ):
        raise InjectionSpecError(
            f"dispense_times_ms must be a list or tuple of at most {MAX_PLANNED_DISPENSES} times"
        )
    p = probability
    if isinstance(p, bool) or not isinstance(p, (int, float)) or not 0.0 <= p <= 1.0:
        raise InjectionSpecError("probability must be a number in [0, 1]")
    if (
        isinstance(gap_ms, bool)
        or not isinstance(gap_ms, int)
        or not 1 <= gap_ms <= T_DAY_MS
    ):
        raise InjectionSpecError(f"gap_ms must be an integer in [1, {T_DAY_MS}]")
    for name, value in (
        ("seed", seed),
        ("patient_index", patient_index),
        ("day_index", day_index),
    ):
        if isinstance(value, bool) or not isinstance(value, int):
            raise InjectionContextError(f"{name} must be an integer")
    previous = -1
    times: list[int] = []
    for t in dispense_times_ms:
        if (
            isinstance(t, bool)
            or not isinstance(t, int)
            or t <= previous
            or t > MAX_TIME_MS
        ):
            raise InjectionSpecError(
                f"dispense times must be strictly increasing integers in [0, {MAX_TIME_MS}]"
            )
        times.append(t)
        previous = t
    specs: list[InjectionSpec] = []
    for t in times:
        try:
            rng = stream(
                seed, patient_index, day_index, StreamPurpose.INJECTION_C2,
                stable_index("bounce_plan", t),
            )  # fmt: skip
        except StreamKeyError as exc:
            raise InjectionContextError(str(exc)) from exc
        if float(rng.random()) < p:
            specs.append(
                InjectionSpec(
                    InjectedClass.C2, "dispenser_bounce", t, None, float(gap_ms), "ms"
                )
            )
    return specs


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


# The order of the injectors inside a stage (and the order of this tuple is the rank).
_ORDER: Final = (
    "nav_delay",
    "manipulation_failure",
    "cuff_detached",
    "cuff_silent_bias",
    "stuck_at",
    "ecg_noise",
    "dispenser_bounce",
    "ble_dropout",
)


def _injector(
    subtype: str,
    stage: str,
    shape: str,
    apply: Any,
    *,
    targets: tuple[str, ...],
    magnitude: str = MAGNITUDE_NONE,
    unit: str | None = None,
    required: bool = False,
    choices: Mapping[str, tuple[str, ...]] | None = None,
    optional: bool = False,
) -> Injector:
    return Injector(
        cls=InjectedClass.C2,
        subtype=subtype,
        stage=stage,
        rank=_ORDER.index(subtype),
        shape=shape,
        magnitude=magnitude,
        magnitude_unit=unit,
        targets=targets,
        target_required=required,
        choices=choices or {},
        signature=EVIDENCE_SIGNATURES[subtype],
        apply=apply,
        magnitude_optional=optional,
    )


def _register() -> None:
    cuff = (vocab.SOURCE_CUFF,)
    robot = (vocab.SOURCE_ROBOT,)
    kinds = {"kind": (vocab.KIND_MEASUREMENT, vocab.KIND_DOSE)}
    table = [
        _injector(
            "nav_delay", STAGE_ROBOT, SHAPE_TICK, nav_delay,
            targets=robot, magnitude=MAGNITUDE_MS, unit="ms", choices=kinds,
        ),
        _injector(
            "manipulation_failure", STAGE_ROBOT, SHAPE_TICK, manipulation_failure,
            targets=robot, choices=kinds,
        ),
        _injector("cuff_detached", STAGE_DEVICE, SHAPE_WINDOW, cuff_detached, targets=cuff),
        _injector(
            "cuff_silent_bias", STAGE_DEVICE, SHAPE_WINDOW, cuff_silent_bias,
            targets=cuff, magnitude=MAGNITUDE_REAL, unit="mmHg",
        ),
        _injector("stuck_at", STAGE_DEVICE, SHAPE_WINDOW, stuck_at, targets=cuff),
        _injector(
            "ecg_noise", STAGE_DEVICE, SHAPE_WINDOW, ecg_noise,
            targets=(vocab.SOURCE_ECG,), magnitude=MAGNITUDE_POSITIVE, unit="1", optional=True,
        ),
        _injector(
            "dispenser_bounce", STAGE_DEVICE, SHAPE_POINT, dispenser_bounce,
            targets=(vocab.SOURCE_DISPENSER,), magnitude=MAGNITUDE_MS, unit="ms",
        ),
        _injector(
            "ble_dropout", STAGE_LINK, SHAPE_WINDOW, ble_dropout,
            targets=tuple(DEVICE_SIGNALS), required=True,
        ),
    ]  # fmt: skip
    for injector in table:
        register_injector(injector)
    if {i.subtype for i in table} != set(C2_SUBTYPES) or set(_ORDER) != set(
        C2_SUBTYPES
    ):
        raise InjectionError("the registered subtypes differ from C2_SUBTYPES")


_register()
