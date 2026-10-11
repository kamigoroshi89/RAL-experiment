"""C3 integrity attacks at two attacker-knowledge levels on the observed stream (WS04-T08).

The attack classes are those of ``docs/models/threat-model.md`` (section "Subtype vocabulary");
``C3_SUBTYPES`` are the five that benchmark v1 injects, ``NOT_INJECTED_IN_V1`` the two that it
models and does not produce. Each injector takes the working copy of the stream, the specs of its
subtype in canonical order and the context, and returns one ``InjectionRecord`` per spec. The
pipeline, the canonical order, the spec rules and the ground-truth mapping are in
``ralmon.benchmark.injection``; this module registers its injectors there in the ``attack`` stage,
which runs after the sequence numbering and the link stage: the pipeline never renumbers attacker
traffic and a dropout of the genuine device cannot remove it. The latent day is not an argument of
any function here and nothing reads ``context.latent``.

Levels and capabilities. The knowledge of the attacker is a set of four flags
(``AttackerCapabilities``), ``NAIVE`` and ``INFORMED`` as in the table of flags of the section
"Knowledge levels" of the threat model (a test compares the module, the document and
``injections.yaml``). The level of a spec is ``spec.level`` (``naive`` or ``informed``; implied by
the subtype for ``injection_naive`` and ``injection_informed``) and is recorded in the record.
What each flag does here:
  ``fresh_metadata``  the delivered sequence numbers and stamps follow the device (informed) or
                      they do not (naive: stale stamps and numbers of a replay, an own counter
                      from ``FORGED_SEQ_START`` for a forgery);
  ``coherent_pulse``  the cuff pulse rate of a message is the ECG rate held at its instant;
  ``plausible_values`` forged pressures lie in the range of the patient's own readings captured
                      before the attack (informed) or in the population bounds of the context
                      (naive), and the forged message carries the group as the device writes it;
  ``spoofs_witness``  the robot is made to report an intake (``presence_spoof`` with
                      ``spoof_intake``). It is a capability of the attacker, not a property of a
                      stream: a forged dispense hides from the witness only where the stream shows
                      it (no robot co-located, or an ``INTAKE`` of the robot in the visit; the
                      presence spoof ranks before the forgery so that its intake counts).

Evidence signature and the declared limit. ``attack_signature(subtype, capabilities,
auth_deployed)`` is the set of ``EvidenceVector`` paths that the attack can drive adverse, in the
order of the contract: the attack-to-evidence table and the table TX-9 of the threat model, each
path under its own condition (the union of raised and conditional paths, as for C2). Whether a
device authenticates is a deployment property per device (``InjectionContext.authenticating_devices``,
hypothesis H-DEP and TM-OP-8): a forged or rewritten message of such a device leaves one failed
verification, a ``VERIFICATION`` event of the source ``gateway`` (``verification`` ``failed``,
``subject`` the device: ADR-035 and the conventions of ``docs/models/evidence-channels.md``,
policy "flag"); a verbatim copy has a valid tag and leaves none; a device that does not
authenticate leaves none (the field is ``None``, never a negative). A record whose signature is
empty carries ``details["expected_undetectable"]`` True: the informed attacker that is coherent on
every available channel is in the ground truth (it is an injected event) and is reported as the
diagnosability limit of analisi section 4.5 (row 10), not as an error of the monitor. The tag is
computed on the stream the attack is written to: a forged dispense whose witness the stream
contradicts (a robot is in the room, no intake) is not tagged, whatever the capability, and one
with the robot away or an intake in the visit is.

Conventions of the attacks on the cuff stream (``replay``, ``injection_naive``,
``injection_informed``; ``[onset, onset + duration)`` on ``t_rx_ms``)
  * The attacker is in the relay position (hypothesis H-SUPP): every message the cuff delivers in
    the window (its four samples ``bp``, ``hr_pulse``, ``cuff_health``, ``inflation_ms`` and the
    events ``MEASUREMENT``, ``MEASUREMENT_MISSED``, ``DEVICE_ERROR`` of source ``cuff``) does not
    reach the gateway. Node reports, robot events and every other device are not touched
    (hypothesis H-EVID: the other evidence sources are as the devices set them).
  * The attack reads the genuine stream through ``InjectionWork.genuine_view`` (the snapshot
    taken when the attack stage starts), so that one attack never reads the traffic of another.
  * ``replay``: every ``MEASUREMENT`` message of the previous day whose arrival plus one day lies
    in the window is delivered again at that instant, one day after it arrived (a replay attacker
    re-sends its capture 24 h later, whatever today's cuff does: it also works where the genuine
    device dropped out). Naive: verbatim, with the stale stamp and the previous day's sequence
    number. Informed: stamps equal to the arrival time, numbers that continue the sequence.
    With no message to replay nothing is suppressed and the injection is not realised.
  * ``injection_naive`` and ``injection_informed``: one forged message in place of each genuine
    ``MEASUREMENT`` message of the window, at the instant of that message (stamp equal to the
    arrival time). Values: uniform draws from the named stream ``INJECTION_C3`` in the bounds of
    the context (naive) or between the minimum and the maximum of the genuine ``bp`` samples
    captured before the onset and of the previous day (informed). Naive pulse: independent
    draw in the heart-rate bounds; no group samples (the system template reads the held earlier
    values); numbers from ``FORGED_SEQ_START``. Informed pulse: the ECG rate held at the instant;
    health and inflation as the genuine message had them; the numbers continue the sequence.
  * Informed numbering (hypothesis H-FRESH): the forged messages take consecutive numbers from the
    first number of the suppressed messages (or, with none, the number after the last earlier
    message, or ``context.cuff_start``) and every later message of the cuff is shifted by the
    difference of the counts, so that the delivered sequence has no gap and no duplicate; the
    counter ``settings["next_cuff_seq"]`` follows (the relay renumbers for good). Inside the
    window the numbers are consecutive (a gap that a link dropout left there is closed, a gap
    outside stays); attacker traffic that ignores the counter (a stale replay, a naive forger) is
    not on the device's sequence and is never renumbered (``InjectionWork.unsequenced``). A
    sequence with no numbers (a device that provides none) gets forged messages with none.

``dispense_forgery`` (point): a synthesised ``DISPENSE`` event of the dispenser at the onset (no
payload, no ``auth`` sample, no ``INTAKE``, nothing in the latent day). Informed: the number after
the last earlier dispense and every later dispense of the dispenser shifted by one (TM-OP-7: the
informed forgery renumbers), ``settings["next_dispenser_seq"]`` follows. Naive: its own number
from ``FORGED_SEQ_START`` (the first one that no dispense at that instant uses); the device's
counter is untouched.

``presence_spoof`` (point): a ``presence`` sample of 1.0 at the onset, only if a robot visit
covers the instant (closed interval; the channel is ``None`` while the robot is away, so no value
can enter it); with ``spoof_intake`` (informed level only) also an ``INTAKE`` event of source
``robot`` at the same instant. The messages are robot outputs: no stamp, number or tag of a device.
It never writes an ``auth`` sample: a keyless injector cannot (WS02-T03 EC-GAP-9).

``n_changed`` counts the items changed, removed or added (a replaced reading is one changed item),
the sequence numbers shifted, and the failed verifications logged; the injection is realised when
it is positive, and an injection that changes nothing leaves the stream exactly as it was.
"""

from __future__ import annotations

import dataclasses
import os
from bisect import bisect_right
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final

import numpy as np

from ralmon.benchmark import vocab
from ralmon.benchmark.injection import (
    MAGNITUDE_NONE,
    MAX_TIME_MS,
    SHAPE_POINT,
    SHAPE_WINDOW,
    STAGE_ATTACK,
    InjectionContext,
    InjectionContextError,
    InjectionDesignError,
    InjectionError,
    InjectionRecord,
    InjectionSpec,
    InjectionSpecError,
    InjectionWork,
    Injector,
    check_call,
    check_previous_day,
    injection_rng,
    load_design_mapping,
    register_injector,
)
from ralmon.benchmark.latent import T_DAY_MS
from ralmon.benchmark.trace import InjectedClass
from ralmon.signals import Event, EventKind, Sample, SignalId

__all__ = [
    "C3_SUBTYPES",
    "CAPABILITY_SETS",
    "EXPECTED_UNDETECTABLE",
    "FORGED_SEQ_START",
    "GATEWAY_POLICY",
    "INFORMED",
    "NAIVE",
    "NOT_INJECTED_IN_V1",
    "AttackerCapabilities",
    "attack_signature",
    "capabilities_of",
    "dispense_forgery",
    "injection_informed",
    "injection_naive",
    "load_capability_sets",
    "presence_spoof",
    "replay",
]

C3_SUBTYPES: Final = (
    "replay",
    "injection_naive",
    "injection_informed",
    "dispense_forgery",
    "presence_spoof",
)
# Modelled in the threat model, not produced by benchmark v1 (they are listed as such in
# configs/benchmark/injections.yaml and have no injector).
NOT_INJECTED_IN_V1: Final = ("dispenser_physical_tamper", "timestamp_manipulation")
EXPECTED_UNDETECTABLE: Final = (
    "expected_undetectable"  # key of the tag in the injection log
)
GATEWAY_POLICY: Final = (
    "flag"  # H-GW: a message that fails verification stays in the trace
)
FORGED_SEQ_START: Final = (
    1  # algorithmic: the first number of a forger that ignores the counter
)
LEVELS: Final = ("naive", "informed")
_INT64_MAX: Final = int(
    np.iinfo(np.int64).max
)  # the largest number the trace schema accepts
_GROUP: Final = (
    "cuff_stream_attack"  # overlap group: the three attacks on the cuff stream
)

_BP: Final = SignalId.BP.value
_INFLATION: Final = SignalId.INFLATION_MS.value
_HEALTH: Final = SignalId.CUFF_HEALTH.value
_PULSE: Final = SignalId.HR_PULSE.value
_HR_ECG: Final = SignalId.HR_ECG.value
_PRESENCE: Final = SignalId.PRESENCE.value
_CUFF_SIGNALS: Final = (_BP, _INFLATION, _HEALTH, _PULSE)
_CUFF_ATTEMPTS: Final = (
    EventKind.MEASUREMENT,
    EventKind.MEASUREMENT_MISSED,
    EventKind.DEVICE_ERROR,
)

_X_DIFF: Final = "cross_device.pulse_vs_ecg_hr_diff"
_W_ROBOT: Final = "witness.robot_present"
_W_IDENT: Final = "witness.identity_confirmed"
_W_INTAKE: Final = "witness.intake_observed"
_C_AUTH: Final = "crypto_temporal.authenticated"
_C_SEQ: Final = "crypto_temporal.seq_repeat"
_C_TS: Final = "crypto_temporal.timestamp_implausible"
# The paths in the order of the EvidenceVector contract (group, then field).
_PATH_ORDER: Final = (_X_DIFF, _W_ROBOT, _W_IDENT, _W_INTAKE, _C_AUTH, _C_SEQ, _C_TS)


# ---------------------------------------------------------------------------
# Capabilities and the evidence signature
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AttackerCapabilities:
    """The four capability flags of an attacker level (threat model, "Knowledge levels")."""

    fresh_metadata: bool
    coherent_pulse: bool
    plausible_values: bool
    spoofs_witness: bool

    def __post_init__(self) -> None:
        for field in dataclasses.fields(self):
            if not isinstance(getattr(self, field.name), bool):
                raise InjectionSpecError(f"{field.name} must be a bool")


NAIVE: Final = AttackerCapabilities(False, False, False, False)
INFORMED: Final = AttackerCapabilities(True, True, True, True)
CAPABILITY_SETS: Final[Mapping[str, AttackerCapabilities]] = MappingProxyType(
    {"naive": NAIVE, "informed": INFORMED}
)


def capabilities_of(level: str) -> AttackerCapabilities:
    """The capability set of a level, ``naive`` or ``informed``."""
    if not isinstance(level, str) or level not in CAPABILITY_SETS:
        raise InjectionSpecError(f"level must be one of {tuple(CAPABILITY_SETS)}")
    return CAPABILITY_SETS[level]


def attack_signature(
    subtype: str,
    capabilities: AttackerCapabilities,
    auth_deployed: bool,
    *,
    witness_contradicts: bool | None = None,
) -> tuple[str, ...]:
    """The evidence paths that an attack can drive adverse, in the order of the contract.

    ``auth_deployed`` says that the device the attack writes to authenticates its messages; when
    it does not, ``crypto_temporal.authenticated`` is ``None`` and never a negative. The table
    that this function transcribes is the attack-to-evidence table and TX-9 of the threat model
    (``replay`` naive: stale stamp and a repeated number; informed: nothing, the cross-device
    difference only if the pulse is not patched; a message that is rewritten has no valid tag;
    ``dispense_forgery``: the witness fields read False when the robot is co-located and saw
    nothing, unless the witness is spoofed; ``presence_spoof``: only the identity check can
    contradict it). Nothing here is computed from a trace.

    ``witness_contradicts`` is read by ``dispense_forgery`` only: whether, in the stream the
    forgery is written to, a robot is co-located at the forged instant and no ``INTAKE`` of the
    robot lies in the visit (the witness fields then read False). ``None`` (the default) takes
    the capability at its word: the witness is spoofed exactly when ``spoofs_witness`` is set,
    which is the pure attacker capability, not a statement about a stream; the injector passes
    what the stream shows.
    """
    if not isinstance(subtype, str) or subtype not in C3_SUBTYPES:
        raise InjectionSpecError(f"subtype must be one of {C3_SUBTYPES}")
    if not isinstance(capabilities, AttackerCapabilities):
        raise InjectionSpecError("capabilities must be an AttackerCapabilities")
    if not isinstance(auth_deployed, bool):
        raise InjectionSpecError("auth_deployed must be a bool")
    if witness_contradicts is not None and not isinstance(witness_contradicts, bool):
        raise InjectionSpecError("witness_contradicts must be a bool or None")
    c = capabilities
    paths: set[str] = set()
    if subtype == "replay":
        if not c.fresh_metadata:
            paths |= {_C_SEQ, _C_TS}  # a stale stamp is late, a number repeats one
        elif not c.coherent_pulse:
            paths.add(
                _X_DIFF
            )  # accepted, so the unpatched pulse is compared with the ECG
        if (c.fresh_metadata or c.coherent_pulse) and auth_deployed:
            paths.add(
                _C_AUTH
            )  # a rewritten message has no valid tag, a verbatim copy has
    elif subtype in ("injection_naive", "injection_informed"):
        expected = "naive" if subtype == "injection_naive" else "informed"
        if c != CAPABILITY_SETS[expected]:
            raise InjectionSpecError(f"{subtype} is the {expected} level")
        if not c.fresh_metadata:
            paths.add(_C_SEQ)  # the stamp is the arrival time: in bounds, nothing late
        if not c.coherent_pulse:
            paths.add(_X_DIFF)
        if auth_deployed:
            paths.add(_C_AUTH)  # a forged message never has a valid tag
    elif subtype == "dispense_forgery":
        if not c.fresh_metadata:
            paths.add(_C_SEQ)
        contradicted = (
            not c.spoofs_witness if witness_contradicts is None else witness_contradicts
        )
        if contradicted:
            paths |= {_W_ROBOT, _W_INTAKE}
        if auth_deployed:
            paths.add(_C_AUTH)
    else:  # presence_spoof
        if not c.spoofs_witness:
            paths.add(_W_IDENT)
    return tuple(p for p in _PATH_ORDER if p in paths)


def load_capability_sets(
    path: str | os.PathLike[str],
) -> Mapping[str, AttackerCapabilities]:
    """The two capability sets of the ``attacker`` section of ``injections.yaml``.

    The section holds, for ``naive`` and ``informed``, the four flags as booleans plus the
    ``source_type`` and ``source_ref`` of the row (the threat model); any other key, a missing
    level or a flag that is not a bool is an ``InjectionDesignError``.
    """
    section = load_design_mapping(path, "attacker")
    sets = section.get("capability_sets")
    if not isinstance(sets, Mapping) or set(sets) != set(LEVELS):
        raise InjectionDesignError(
            f"attacker.capability_sets must hold exactly {LEVELS}"
        )
    names = tuple(f.name for f in dataclasses.fields(AttackerCapabilities))
    loaded: dict[str, AttackerCapabilities] = {}
    for level in LEVELS:
        entry = sets[level]
        if not isinstance(entry, Mapping) or set(entry) != {
            *names,
            "source_type",
            "source_ref",
        }:
            raise InjectionDesignError(
                f"attacker.capability_sets.{level} must hold exactly the flags {names}, "
                "source_type and source_ref"
            )
        if not all(isinstance(entry[name], bool) for name in names):
            raise InjectionDesignError(f"the flags of {level} must be booleans")
        loaded[level] = AttackerCapabilities(*(entry[name] for name in names))
    return MappingProxyType(loaded)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _level_of(spec: InjectionSpec) -> str:
    if spec.level is None:  # check_call requires it for the subtypes that need one
        raise InjectionSpecError(f"{spec.subtype} needs a level, one of {LEVELS}")
    return spec.level


def _record(
    spec: InjectionSpec,
    level: str,
    device: str,
    auth: bool,
    n_changed: int,
    details: Mapping[str, Any],
    witness_contradicts: bool | None = None,
) -> InjectionRecord:
    caps = capabilities_of(level)
    paths = attack_signature(
        spec.subtype, caps, auth, witness_contradicts=witness_contradicts
    )
    end = None if spec.duration_ms is None else spec.onset_ms + spec.duration_ms
    base: dict[str, Any] = {
        "target": device,
        "capabilities": dataclasses.asdict(caps),
        "auth_deployed": auth,
        EXPECTED_UNDETECTABLE: len(paths) == 0,
        "gateway_policy": GATEWAY_POLICY,
    }
    return InjectionRecord(
        spec,
        spec.onset_ms,
        end,
        n_changed > 0,
        n_changed,
        paths,
        level,
        spec.confounder_group,
        {**base, **details},
    )


def _window(spec: InjectionSpec) -> tuple[int, int]:
    assert (
        spec.duration_ms is not None
    )  # a window attack: the pipeline checked the shape
    return spec.onset_ms, spec.onset_ms + spec.duration_ms


def _gateway_failure(device: str, t: int) -> Event:
    """The failed verification of one message of ``device`` that arrived at ``t`` (policy flag)."""
    payload: dict[str, float | int | str | bool] = {
        vocab.KEY_VERIFICATION: vocab.VERIFICATION_FAILED,
        vocab.KEY_SUBJECT: device,
    }
    return Event(EventKind.VERIFICATION, t, t, vocab.SOURCE_GATEWAY, payload, None)


def _seq_in_range(value: int) -> int:
    if value > _INT64_MAX or value < -_INT64_MAX:
        raise InjectionContextError(
            "a sequence number would leave the range of the schema"
        )
    return value


def _is_dispense(event: Event) -> bool:
    return event.kind is EventKind.DISPENSE and event.source == vocab.SOURCE_DISPENSER


def _is_cuff_sample(sample: Sample) -> bool:
    return sample.signal in _CUFF_SIGNALS


def _is_cuff_event(event: Event) -> bool:
    return event.source == vocab.SOURCE_CUFF and event.kind in _CUFF_ATTEMPTS


def _item_key(item: Sample | Event) -> tuple[str, ...]:
    if isinstance(item, Sample):
        return ("S", item.signal)
    return ("E", item.kind.value, item.source)


def _count_changes(old: Sequence[Sample | Event], new: Sequence[Sample | Event]) -> int:
    """Items changed, removed or added: same kind of item paired in arrival order."""
    before: dict[tuple[str, ...], list[Sample | Event]] = {}
    after: dict[tuple[str, ...], list[Sample | Event]] = {}
    for item in old:
        before.setdefault(_item_key(item), []).append(item)
    for item in new:
        after.setdefault(_item_key(item), []).append(item)
    n = 0
    for key in before.keys() | after.keys():
        a, b = before.get(key, []), after.get(key, [])
        paired = min(len(a), len(b))
        n += sum(1 for x, y in zip(a[:paired], b[:paired], strict=True) if x != y)
        n += abs(len(a) - len(b))
    return n


@dataclass(frozen=True, slots=True)
class _Message:
    """One measurement message of the cuff: its event and the samples that share its stamp."""

    event: Event
    samples: Mapping[str, Sample]


def _messages(
    samples: Sequence[Sample], events: Sequence[Event], lo: int, hi: int
) -> list[_Message]:
    """The ``MEASUREMENT`` messages of the cuff that arrived in ``[lo, hi)``, in arrival order."""
    index: dict[tuple[int, int, int | None], list[int]] = {}
    for i, s in enumerate(samples):
        if _is_cuff_sample(s) and lo <= s.t_rx_ms < hi:
            index.setdefault((s.t_device_ms, s.t_rx_ms, s.seq), []).append(i)
    taken: set[int] = set()
    found: list[_Message] = []
    for e in events:
        if not (
            e.kind is EventKind.MEASUREMENT
            and e.source == vocab.SOURCE_CUFF
            and lo <= e.t_rx_ms < hi
        ):
            continue
        group: dict[str, Sample] = {}
        for i in index.get((e.t_device_ms, e.t_rx_ms, e.seq), []):
            if i not in taken and samples[i].signal not in group:
                group[samples[i].signal] = samples[i]
                taken.add(i)
        found.append(_Message(e, group))
    return found


class _EcgHold:
    """The ECG rate held at an instant: the value of the last sample at or before it."""

    def __init__(self, samples: Sequence[Sample]) -> None:
        points = sorted(
            (
                (s.t_device_ms, i, s.value)
                for i, s in enumerate(samples)
                if s.signal == _HR_ECG
            )
        )
        self._times = [t for t, _, _ in points]
        self._values = [v for _, _, v in points]

    def at(self, t: int) -> float | None:
        position = bisect_right(self._times, t)
        return self._values[position - 1] if position else None


def _suppress(
    samples: list[Sample], events: list[Event], lo: int, hi: int
) -> tuple[list[Sample], list[Event], list[Sample | Event]]:
    """Drop every message the cuff delivered in ``[lo, hi)``; return what is left and what went."""
    kept_s: list[Sample] = []
    kept_e: list[Event] = []
    removed: list[Sample | Event] = []
    for s in samples:
        if _is_cuff_sample(s) and lo <= s.t_rx_ms < hi:
            removed.append(s)
        else:
            kept_s.append(s)
    for e in events:
        if _is_cuff_event(e) and lo <= e.t_rx_ms < hi:
            removed.append(e)
        else:
            kept_e.append(e)
    return kept_s, kept_e, removed


def _on_sequence(t: int, skip: Sequence[tuple[int, int]]) -> bool:
    """Whether a cuff item arriving at ``t`` follows the sequence of the device."""
    return not any(a <= t < b for a, b in skip)


def _first_number(
    samples: Sequence[Sample],
    events: Sequence[Event],
    removed: Sequence[Sample | Event],
    lo: int,
    default: int,
    skip: Sequence[tuple[int, int]],
) -> int:
    """The number the first forged message of an informed attack takes (module docstring)."""
    freed = [x.seq for x in removed if x.seq is not None]
    if freed:
        return min(freed)
    earlier = [
        s.seq
        for s in samples
        if _is_cuff_sample(s)
        and s.seq is not None
        and s.t_rx_ms < lo
        and _on_sequence(s.t_rx_ms, skip)
    ]
    earlier += [
        e.seq
        for e in events
        if _is_cuff_event(e)
        and e.seq is not None
        and e.t_rx_ms < lo
        and _on_sequence(e.t_rx_ms, skip)
    ]
    return max(earlier) + 1 if earlier else default


def _shift_later(
    samples: list[Sample],
    events: list[Event],
    hi: int,
    shift: int,
    skip: Sequence[tuple[int, int]],
) -> int:
    """Add ``shift`` to the number of every cuff message of the device arriving at or after ``hi``.

    Attacker traffic in a window of ``skip`` does not follow the sequence of the device and is
    left alone.
    """
    n = 0
    if shift == 0:
        return n
    for i, s in enumerate(samples):
        if (
            _is_cuff_sample(s)
            and s.seq is not None
            and s.t_rx_ms >= hi
            and _on_sequence(s.t_rx_ms, skip)
        ):
            samples[i] = dataclasses.replace(s, seq=_seq_in_range(s.seq + shift))
            n += 1
    for i, e in enumerate(events):
        if (
            _is_cuff_event(e)
            and e.seq is not None
            and e.t_rx_ms >= hi
            and _on_sequence(e.t_rx_ms, skip)
        ):
            events[i] = dataclasses.replace(e, seq=_seq_in_range(e.seq + shift))
            n += 1
    return n


def _bump_counter(work: InjectionWork, key: str, shift: int) -> None:
    current = work.settings.get(key)
    if isinstance(current, int) and not isinstance(current, bool) and shift != 0:
        work.settings[key] = _seq_in_range(current + shift)


def _message_items(
    t_device: int,
    t_rx: int,
    seq: int | None,
    pressure: float,
    pulse: float | None,
    group: Mapping[str, Sample],
) -> tuple[list[Sample], Event]:
    """One forged cuff message: its samples and its event.

    ``group`` holds the genuine samples whose health and inflation (with their quality) the
    message repeats (the informed level; the naive one gives none and writes no group).
    """
    items: list[Sample] = []
    for (
        signal
    ) in _CUFF_SIGNALS:  # the order of a genuine message: a forged one must not differ
        if signal == _BP:
            items.append(
                Sample(_BP, t_device, t_rx, pressure, seq, _quality(group, _BP))
            )
        elif signal == _PULSE:
            if pulse is not None:
                items.append(
                    Sample(_PULSE, t_device, t_rx, pulse, seq, _quality(group, _PULSE))
                )
        elif signal in group:
            items.append(
                Sample(
                    signal,
                    t_device,
                    t_rx,
                    group[signal].value,
                    seq,
                    _quality(group, signal),
                )
            )
    event = Event(EventKind.MEASUREMENT, t_device, t_rx, vocab.SOURCE_CUFF, {}, seq)
    return items, event


def _quality(of: Mapping[str, Sample], signal: str) -> float | None:
    sample = of.get(signal)
    return None if sample is None else sample.quality


def _commit(work: InjectionWork, samples: list[Sample], events: list[Event]) -> None:
    work.samples, work.events = samples, events


# ---------------------------------------------------------------------------
# replay
# ---------------------------------------------------------------------------


def _has_numbers(samples: Sequence[Sample], events: Sequence[Event]) -> bool:
    """Whether the cuff numbers its messages: any cuff item of the stream carries a number."""
    return any(_is_cuff_sample(s) and s.seq is not None for s in samples) or any(
        _is_cuff_event(e) and e.seq is not None for e in events
    )


def replay(
    work: InjectionWork, specs: Sequence[InjectionSpec], context: InjectionContext
) -> tuple[InjectionRecord, ...]:
    """Deliver the previous day's cuff messages again, one day after they arrived."""
    specs = check_call(work, specs, context, "replay")
    if specs and work.day_index == 0:
        raise InjectionSpecError(
            "a replay needs a previous day: day_index must be above zero"
        )
    previous = check_previous_day(work, context) if specs else None
    if specs and previous is None:
        raise InjectionContextError("a replay needs context.previous_day")
    records: list[InjectionRecord] = []
    device = vocab.SOURCE_CUFF
    auth = device in context.authenticating_devices
    for spec in specs:
        assert previous is not None
        level = _level_of(spec)
        caps = capabilities_of(level)
        lo, hi = _window(spec)
        copies = _messages(
            previous.samples, previous.events, lo - T_DAY_MS, hi - T_DAY_MS
        )
        details: dict[str, Any] = {
            "n_copies": len(copies),
            "n_suppressed": 0,
            "n_renumbered": 0,
        }
        if not copies:
            details["reason"] = "the previous day sent no cuff message in the window"
            records.append(_record(spec, level, device, auth, 0, details))
            continue
        if any(m.event.t_rx_ms + T_DAY_MS > MAX_TIME_MS for m in copies):
            raise InjectionContextError(
                "a replayed message would leave the range of time"
            )
        samples, events, removed = _suppress(
            list(work.samples), list(work.events), lo, hi
        )
        genuine_s, genuine_e = work.genuine_view()
        ecg = _EcgHold(genuine_s)
        numbered = _has_numbers(genuine_s, genuine_e) or any(
            m.event.seq is not None for m in copies
        )
        renumber = caps.fresh_metadata and numbered
        freed = len({x.seq for x in removed if x.seq is not None})
        first = _first_number(
            samples, events, removed, lo, context.cuff_start, work.unsequenced
        )
        new_samples: list[Sample] = []
        new_events: list[Event] = []
        failures: list[Event] = []
        for j, m in enumerate(copies):
            t = m.event.t_rx_ms + T_DAY_MS
            number = _seq_in_range(first + j) if renumber else None
            rate = ecg.at(t) if caps.coherent_pulse else None
            for signal in _CUFF_SIGNALS:
                src = m.samples.get(signal)
                if src is None:
                    continue
                value = rate if (signal == _PULSE and rate is not None) else src.value
                t_dev = t if caps.fresh_metadata else src.t_device_ms
                seq = number if caps.fresh_metadata else src.seq
                new_samples.append(Sample(signal, t_dev, t, value, seq, src.quality))
            e = m.event
            new_events.append(
                Event(
                    e.kind,
                    t if caps.fresh_metadata else e.t_device_ms,
                    t,
                    e.source,
                    dict(e.payload),
                    number if caps.fresh_metadata else e.seq,
                )
            )
            if (caps.fresh_metadata or caps.coherent_pulse) and auth:
                failures.append(
                    _gateway_failure(device, t)
                )  # a rewritten message: no valid tag
        shift = len(copies) - freed
        n = _count_changes(removed, [*new_samples, *new_events]) + len(failures)
        shifted = (
            _shift_later(samples, events, hi, shift, work.unsequenced)
            if renumber
            else 0
        )
        n += shifted
        details.update(n_suppressed=len(removed), n_renumbered=shifted)
        if n > 0:
            _commit(work, [*samples, *new_samples], [*events, *new_events, *failures])
            if renumber:
                _bump_counter(work, "next_cuff_seq", shift)
            if not caps.fresh_metadata:
                work.unsequenced.append(
                    (lo, hi)
                )  # stale numbers: not the device's sequence
        else:
            details["reason"] = "the replayed messages equal the genuine ones"
        records.append(_record(spec, level, device, auth, n, details))
    return tuple(records)


# ---------------------------------------------------------------------------
# injection of values
# ---------------------------------------------------------------------------


def _history(
    work: InjectionWork, context: InjectionContext, lo: int
) -> tuple[float, float] | None:
    """Range of the genuine pressures captured before ``lo`` and on the previous day, or None."""
    genuine_s, _ = work.genuine_view()
    values = [s.value for s in genuine_s if s.signal == _BP and s.t_rx_ms < lo]
    previous = check_previous_day(work, context)
    if previous is not None:
        values.extend(s.value for s in previous.samples if s.signal == _BP)
    return (min(values), max(values)) if values else None


def _draw(low: float, high: float, u: float) -> float:
    # the weights keep a huge pair of bounds finite; the clamp absorbs the last rounding
    return min(max(low * (1.0 - u) + high * u, low), high)


def _inject(
    work: InjectionWork,
    specs: Sequence[InjectionSpec],
    context: InjectionContext,
    subtype: str,
    level: str,
) -> tuple[InjectionRecord, ...]:
    caps = CAPABILITY_SETS[level]
    specs = check_call(work, specs, context, subtype)
    if (
        specs
        and not caps.plausible_values
        and (context.bp_bounds_mmhg is None or context.hr_bounds_bpm is None)
    ):
        raise InjectionContextError(
            f"{subtype} needs context.bp_bounds_mmhg and context.hr_bounds_bpm"
        )
    records: list[InjectionRecord] = []
    device = vocab.SOURCE_CUFF
    auth = device in context.authenticating_devices
    for spec in specs:
        lo, hi = _window(spec)
        details: dict[str, Any] = {"n_forged": 0, "n_suppressed": 0, "n_renumbered": 0}
        slots = _messages(work.samples, work.events, lo, hi)
        if not slots:
            details["reason"] = "no genuine measurement message in the window"
            records.append(_record(spec, level, device, auth, 0, details))
            continue
        history = _history(work, context, lo) if caps.plausible_values else None
        if caps.plausible_values and history is None:
            details["reason"] = "no genuine reading captured before the window"
            records.append(_record(spec, level, device, auth, 0, details))
            continue
        draws = injection_rng(work, context, spec).random((len(slots), 2))
        ecg = _EcgHold(work.genuine_view()[0])
        samples, events, removed = _suppress(
            list(work.samples), list(work.events), lo, hi
        )
        numbered = any(m.event.seq is not None for m in slots) or any(
            x.seq is not None for x in removed
        )
        renumber = caps.fresh_metadata and numbered
        freed = len({x.seq for x in removed if x.seq is not None})
        if renumber:
            first = _first_number(
                samples, events, removed, lo, context.cuff_start, work.unsequenced
            )
        else:
            # a forger that does not know the counter keeps one of its own for the whole day
            first = work.attacker_next.get(device, FORGED_SEQ_START)
        new_samples: list[Sample] = []
        new_events: list[Event] = []
        failures: list[Event] = []
        for j, m in enumerate(slots):
            t = m.event.t_rx_ms
            seq = _seq_in_range(first + j) if numbered else None
            if history is not None:
                pressure = _draw(history[0], history[1], float(draws[j, 0]))
            else:
                assert context.bp_bounds_mmhg is not None
                pressure = _draw(*context.bp_bounds_mmhg, float(draws[j, 0]))
            pulse: float | None
            if caps.coherent_pulse:
                genuine_pulse = m.samples.get(
                    _PULSE
                )  # the device sent a pulse or it did not
                held = ecg.at(t)
                if genuine_pulse is None:
                    pulse = None
                else:
                    pulse = held if held is not None else genuine_pulse.value
            else:
                assert context.hr_bounds_bpm is not None
                pulse = _draw(*context.hr_bounds_bpm, float(draws[j, 1]))
            device_group: Mapping[str, Sample] = (
                m.samples if caps.plausible_values else {}
            )
            items, event = _message_items(t, t, seq, pressure, pulse, device_group)
            new_samples.extend(items)
            new_events.append(event)
            if auth:
                failures.append(
                    _gateway_failure(device, t)
                )  # a forged message: no valid tag
        shift = len(slots) - freed
        n = _count_changes(removed, [*new_samples, *new_events]) + len(failures)
        shifted = (
            _shift_later(samples, events, hi, shift, work.unsequenced)
            if renumber
            else 0
        )
        n += shifted
        details.update(
            n_forged=len(slots), n_suppressed=len(removed), n_renumbered=shifted
        )
        if n > 0:
            _commit(work, [*samples, *new_samples], [*events, *new_events, *failures])
            if renumber:
                _bump_counter(work, "next_cuff_seq", shift)
            if not caps.fresh_metadata:
                work.unsequenced.append(
                    (lo, hi)
                )  # a counter of its own: not the device's
                if numbered:
                    work.attacker_next[device] = _seq_in_range(first + len(slots))
        else:
            details["reason"] = "the forged messages equal the genuine ones"
        records.append(_record(spec, level, device, auth, n, details))
    return tuple(records)


def injection_naive(
    work: InjectionWork, specs: Sequence[InjectionSpec], context: InjectionContext
) -> tuple[InjectionRecord, ...]:
    """Forged readings in the population bounds, an independent pulse, a counter of its own."""
    return _inject(work, specs, context, "injection_naive", "naive")


def injection_informed(
    work: InjectionWork, specs: Sequence[InjectionSpec], context: InjectionContext
) -> tuple[InjectionRecord, ...]:
    """Forged readings in the patient's own range, the pulse of the ECG, a continuing sequence."""
    return _inject(work, specs, context, "injection_informed", "informed")


# ---------------------------------------------------------------------------
# dispense forgery and presence spoof
# ---------------------------------------------------------------------------


def dispense_forgery(
    work: InjectionWork, specs: Sequence[InjectionSpec], context: InjectionContext
) -> tuple[InjectionRecord, ...]:
    """Deliver a ``DISPENSE`` event that the dispenser did not produce (module docstring)."""
    specs = check_call(work, specs, context, "dispense_forgery")
    records: list[InjectionRecord] = []
    device = vocab.SOURCE_DISPENSER
    auth = device in context.authenticating_devices
    for spec in specs:
        level = _level_of(spec)
        caps = capabilities_of(level)
        t = spec.onset_ms
        events = list(work.events)
        counter = work.settings.get("next_dispenser_seq")
        scheme = any(_is_dispense(e) and e.seq is not None for e in events) or (
            isinstance(counter, int) and not isinstance(counter, bool)
        )
        seq: int | None = None
        shifted = 0
        if scheme and caps.fresh_metadata:
            earlier = [
                e.seq
                for e in events
                if _is_dispense(e) and e.seq is not None and e.t_rx_ms <= t
            ]
            seq = _seq_in_range(
                max(earlier) + 1 if earlier else context.dispenser_start
            )
            for i, e in enumerate(events):
                if _is_dispense(e) and e.seq is not None and e.t_rx_ms > t:
                    events[i] = dataclasses.replace(e, seq=_seq_in_range(e.seq + 1))
                    shifted += 1
        elif scheme:
            used = {
                e.seq
                for e in events
                if _is_dispense(e) and e.t_rx_ms == t and e.seq is not None
            }
            seq = work.attacker_next.get(device, FORGED_SEQ_START)
            while seq in used:
                seq += 1
            work.attacker_next[device] = _seq_in_range(seq + 1)
        events.append(Event(EventKind.DISPENSE, t, t, device, {}, seq))
        n = 1 + shifted
        if auth:
            events.append(_gateway_failure(device, t))
            n += 1
        work.events = events
        if scheme and caps.fresh_metadata:
            _bump_counter(work, "next_dispenser_seq", 1)
        details = {"seq": seq, "n_renumbered": shifted}
        records.append(
            _record(
                spec,
                level,
                device,
                auth,
                n,
                details,
                witness_contradicts=_witness_contradicts(work, t),
            )
        )
    return tuple(records)


def _witness_contradicts(work: InjectionWork, t: int) -> bool:
    """Whether the witness reads False at ``t``: a robot is co-located and saw no intake.

    The reading comes from the stream as it is when the forgery is written: a robot visit that
    covers ``t`` and no ``INTAKE`` of the robot inside that visit (a genuine one, or one that a
    ``presence_spoof`` with ``spoof_intake`` wrote before: that injector ranks first). With no
    visit the robot is away and the witness is ``None``, never a negative.
    """
    visit = next((v for v in work.visits if v.arrival_ms <= t <= v.departure_ms), None)
    if visit is None:
        return False
    return not any(
        e.kind is EventKind.INTAKE
        and e.source == vocab.SOURCE_ROBOT
        and visit.arrival_ms <= e.t_device_ms <= visit.departure_ms
        for e in work.events
    )


def presence_spoof(
    work: InjectionWork, specs: Sequence[InjectionSpec], context: InjectionContext
) -> tuple[InjectionRecord, ...]:
    """Make the robot report a presence (and, informed, an intake) while it is in the room."""
    specs = check_call(work, specs, context, "presence_spoof")
    records: list[InjectionRecord] = []
    for spec in specs:
        level = _level_of(spec)
        caps = capabilities_of(level)
        intake = spec.params.get("spoof_intake", False)
        if intake and not caps.spoofs_witness:
            raise InjectionSpecError(
                "spoof_intake needs the informed level (spoofs_witness)"
            )
        t = spec.onset_ms
        details: dict[str, Any] = {"spoof_intake": bool(intake)}
        n = 0
        if any(v.arrival_ms <= t <= v.departure_ms for v in work.visits):
            if any(
                s.signal == _PRESENCE
                and s.t_device_ms == t
                and s.t_rx_ms == t
                and s.value == 1.0
                for s in work.samples
            ):
                details["reason"] = (
                    "the robot already reports a presence of 1.0 at the instant: nothing to spoof"
                )
            else:
                work.samples.append(Sample(_PRESENCE, t, t, 1.0, None, None))
                n = 1
            if intake:
                work.events.append(
                    Event(EventKind.INTAKE, t, t, vocab.SOURCE_ROBOT, {}, None)
                )
                n += 1
        else:
            details["reason"] = (
                "the robot is not in the room at the instant: the channel is None"
            )
        records.append(_record(spec, level, vocab.SOURCE_ROBOT, False, n, details))
    return tuple(records)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


# The presence spoof runs before the forgery: a forgery reads the witness of the stream it is
# written to, and a spoofed intake is part of that stream (the pair is composed by WS04-T09).
_RUN_ORDER: Final = (
    "replay",
    "injection_naive",
    "injection_informed",
    "presence_spoof",
    "dispense_forgery",
)


def _union_signature(subtype: str, levels: Sequence[str]) -> tuple[str, ...]:
    paths: set[str] = set()
    for level in levels:
        for auth in (False, True):
            paths |= set(attack_signature(subtype, CAPABILITY_SETS[level], auth))
    return tuple(p for p in _PATH_ORDER if p in paths)


def _injector(
    subtype: str,
    apply: Any,
    *,
    shape: str,
    targets: tuple[str, ...],
    levels: tuple[str, ...],
    required: bool,
    choices: Mapping[str, tuple[str | bool, ...]] | None = None,
    group: str | None = None,
) -> Injector:
    return Injector(
        cls=InjectedClass.C3,
        subtype=subtype,
        stage=STAGE_ATTACK,
        rank=_RUN_ORDER.index(subtype),
        shape=shape,
        magnitude=MAGNITUDE_NONE,
        magnitude_unit=None,
        targets=targets,
        target_required=False,
        choices=choices or {},
        signature=_union_signature(subtype, levels),
        apply=apply,
        levels=levels,
        level_required=required,
        overlap_group=group,
    )


def _register() -> None:
    cuff = (vocab.SOURCE_CUFF,)
    table = [
        _injector("replay", replay, shape=SHAPE_WINDOW, targets=cuff, levels=LEVELS, required=True, group=_GROUP),
        _injector("injection_naive", injection_naive, shape=SHAPE_WINDOW, targets=cuff, levels=("naive",), required=False, group=_GROUP),
        _injector("injection_informed", injection_informed, shape=SHAPE_WINDOW, targets=cuff, levels=("informed",), required=False, group=_GROUP),
        _injector("dispense_forgery", dispense_forgery, shape=SHAPE_POINT, targets=(vocab.SOURCE_DISPENSER,), levels=LEVELS, required=True),
        _injector(
            "presence_spoof", presence_spoof, shape=SHAPE_POINT, targets=(vocab.SOURCE_ROBOT,),
            levels=LEVELS, required=True, choices={"spoof_intake": (False, True)},
        ),
    ]  # fmt: skip
    for injector in table:
        register_injector(injector)
    if tuple(i.subtype for i in table) != C3_SUBTYPES:
        raise InjectionError("the registered subtypes differ from C3_SUBTYPES")


_register()
