"""The evidence extractor: an observed trace and a violated record to an ``EvidenceVector``.

Specification: docs/models/evidence-channels.md (WS02-T03): the field semantics, the derivation table, the trace
evidence conventions for ``Event.payload``, the two-clock acceptance rules, the evidence window and cut-off (D-7),
the aggregation rule, the scope of an instance (D-10) and the ablation A4 mask. This is the step that WS02-T03
gap G-5 found without an owner. The extractor reads only the observed trace (samples, events) and the robot evidence
messages, never ``LatentDay`` or ``GroundTruthEvent``.

Inputs. ``observe_sample`` and ``observe_event`` take trace items in any order (the extractor files them by their
two clocks); impulse events (``MEASUREMENT``, ``DISPENSE``, ``INTAKE``, ``SCHEDULE_TICK``) become impulse samples
through ``event_to_sample``, and the other kinds feed the health, quality and task fields by the payload keys of the
conventions table (``NODE_STATE``, ``ROBOT_TASK``, ``DEVICE_ERROR``, ``VERIFICATION``). ``observe_robot_evidence`` takes
the witness and system fields that the robot publishes on ``/ralmon/robot_evidence``. ``evidence_for(record)`` builds
the vector of one violated record from what was *received by its cut-off* ``C(i) = Ue(i) + D + evidence_grace_ms``,
with ``Ue(i) = decided_at_ms`` of the VIOLATED record (``t_eval_ms`` of a predicted one): an input received later
is not used (D-7), so the vector is a causal function of the inputs. The extractor keeps every input it is given; it
is meant for a trace of one patient-day, or a stream that the caller drops when it is no longer needed.

Parameters. ``evidence_margin_ms``, ``evidence_grace_ms``, ``hr_coherence_max_age_ms`` and ``clock_skew_max_ms`` are
read from the registry and have no default (``RegistryError`` otherwise); the monitor step and the reorder delay of
the run are arguments. What each source can report (D-8, ADR-036 proposed) is a ``DeviceProfile``: a capability that
is not declared makes the dependent field ``None``, never a negative reading. The thresholds that compare a float
with a floor or a tolerance belong to the rule (``HierarchicalRule``), not to the extractor.

Choices not fixed by the document, recorded in the Notes of WS05-T07: the anchor of a plan instance (the
``anchor_ms`` of the call or of the plan, else the key convention of ``instance_anchor_ms``); the arrival-axis
window bound of a robot evidence snapshot; the merge rule of a snapshot with the ward-side fields (a reading from the
trace wins, an adverse reading of either side stands, the snapshot fills what the trace leaves unavailable).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Final

from ralmon.attribution.evidence import (
    CrossDeviceEvidence,
    CryptoTemporalEvidence,
    EmbodiedWitnessEvidence,
    EvidenceVector,
    ProvenanceEvidence,
    SignalQualityEvidence,
    SystemHealthEvidence,
    instance_anchor_ms,
    template_kind_of,
)
from ralmon.monitor import VerdictRecord, VerdictState
from ralmon.signals import (
    MS_PER_HOUR,
    DurationMs,
    Event,
    EventKind,
    ObservedTrace,
    Sample,
    SignalId,
    TimeMs,
    event_to_sample,
)
from ralmon.spec import CarePlan, ParameterRegistry, TemplateId, as_duration_ms

__all__ = [
    "DeviceCapabilities",
    "DeviceProfile",
    "EvidenceExtractor",
    "extract_evidence",
]

_MS_PER_DAY: Final = 24 * MS_PER_HOUR
CUFF: Final = "cuff"
DISPENSER: Final = "dispenser"
ROBOT: Final = "robot"
BLE_DEVICES: Final = ("cuff", "dispenser", "ecg", "oximeter")

#: The node that produces a signal (docs/formal/01-signals-sampling.md section 2.1): a ``Sample`` has no source.
_SIGNAL_NODE: Final[dict[str, str]] = {
    SignalId.BP.value: CUFF,
    SignalId.MEAS.value: CUFF,
    SignalId.HR_PULSE.value: CUFF,
    SignalId.CUFF_HEALTH.value: CUFF,
    SignalId.INFLATION_MS.value: CUFF,
    SignalId.DISPENSE.value: DISPENSER,
    SignalId.AUTH.value: DISPENSER,
    SignalId.HR_ECG.value: "ecg",
    SignalId.SPO2.value: "oximeter",
    SignalId.PRESENCE.value: ROBOT,
    SignalId.INTAKE.value: ROBOT,
}
#: The BLE devices of the data scope of each template (evidence-channels.md, Scope of an instance).
_DATA_SCOPE: Final[dict[TemplateId, tuple[str, ...]]] = {
    TemplateId.RANGE: (CUFF,),
    TemplateId.SCHED: (CUFF,),
    TemplateId.HOLD: (CUFF, DISPENSER),
    TemplateId.COUNT: (DISPENSER,),
    TemplateId.RESP: (CUFF, DISPENSER),
    TemplateId.SYS: (CUFF,),
    TemplateId.INT: (DISPENSER,),
}
_ROBOT_SCOPE: Final = frozenset(
    {TemplateId.SCHED, TemplateId.HOLD, TemplateId.RESP, TemplateId.INT}
)
_LIFECYCLE_STATES: Final = frozenset(
    {"unconfigured", "inactive", "active", "finalized"}
)
_FAILED: Final = frozenset({"failed", "timeout", "late"})


@dataclass(frozen=True, slots=True)
class DeviceCapabilities:
    """What one node can report (D-8). A capability that is absent makes the dependent field ``None``."""

    status_reports: bool = False  # emits NODE_STATE (lifecycle, link)
    supervised: bool = False  # its liveliness is supervised with a lease
    diagnostics: bool = False  # reports diagnostics in NODE_STATE
    deadline_ms: int | None = None  # a declared data-stream (or heartbeat) deadline
    seq: bool = False  # provides sequence numbers
    two_clocks: bool = False  # receive time independent of device time (can deny late or future-stamped)
    authenticates: bool = False  # its messages are verified by the gateway
    error_codes: bool = False  # reports error codes (DEVICE_ERROR)
    battery: bool = False  # reports a battery state (robot)


@dataclass(frozen=True, slots=True)
class DeviceProfile:
    """Run-level declaration of the capabilities per node (``cuff``, ``dispenser``, ``ecg``, ``oximeter``, ``robot``)."""

    nodes: Mapping[str, DeviceCapabilities] = field(default_factory=dict)

    def caps(self, node: str) -> DeviceCapabilities:
        return self.nodes.get(node, DeviceCapabilities())


@dataclass(frozen=True, slots=True)
class _Msg:
    """A message of a BLE device, whatever its form (sample or event)."""

    node: str
    name: str  # Sample.signal or Event.kind: members of one frame differ in the name
    t_dev: TimeMs
    t_rx: TimeMs
    seq: int | None
    status: str  # "ok", "late" or "future" (T01 sections 4.2 to 4.4)
    order: int


@dataclass(frozen=True, slots=True)
class _Window:
    template: TemplateId
    key: str
    cutoff: TimeMs  # C(i)
    lo_rx: TimeMs  # arrival axis: [a_read - margin, C]
    lo_step: int  # event axis: [k_up(a_read - margin), hi_step]
    hi_step: int  # k_up(Ue)
    wit_lo_step: int  # witness window, no margin: [k_up(a_read), hi_step]
    nodes: tuple[
        str, ...
    ]  # system scope: BLE devices of the data scope, then the robot where it applies
    devices: tuple[str, ...]  # data scope


_Snapshot = tuple[TimeMs, EmbodiedWitnessEvidence, SystemHealthEvidence]


class EvidenceExtractor:
    """Builds the ``EvidenceVector`` of a violated record from the inputs received by its cut-off."""

    def __init__(
        self,
        registry: ParameterRegistry,
        *,
        step_ms: DurationMs,
        reorder_delay_ms: DurationMs,
        profile: DeviceProfile | None = None,
        patient_id: str | None = None,
        plan: CarePlan | None = None,
        exclude_robot: bool = False,
    ) -> None:
        if isinstance(step_ms, bool) or not isinstance(step_ms, int) or step_ms <= 0:
            raise ValueError(f"step_ms must be a positive int, got {step_ms!r}")
        if (
            isinstance(reorder_delay_ms, bool)
            or not isinstance(reorder_delay_ms, int)
            or reorder_delay_ms < 0
        ):
            raise ValueError(
                f"reorder_delay_ms must be a non-negative int, got {reorder_delay_ms!r}"
            )
        # no default value: a missing name is a RegistryError (docs/models/evidence-channels.md, parameters)
        self._margin = as_duration_ms(registry.get("evidence_margin_ms"))
        self._grace = as_duration_ms(registry.get("evidence_grace_ms"))
        self._max_age = as_duration_ms(registry.get("hr_coherence_max_age_ms"))
        self._skew = as_duration_ms(registry.get("clock_skew_max_ms"))
        self._registry = registry
        self._step = step_ms
        self._delay = reorder_delay_ms
        self._profile = profile if profile is not None else DeviceProfile()
        self._patient = patient_id
        self._plan_anchor: dict[str, TimeMs | None] = {}
        if plan is not None:
            self._plan_anchor = {i.instance_key: i.anchor_ms for i in plan.instances}
        self._exclude_robot = exclude_robot
        self._order = 0
        self._samples: list[
            tuple[Sample, str, int]
        ] = []  # sample, status, arrival order
        self._events: list[tuple[Event, str, int]] = []
        self._msgs: list[_Msg] = []
        self._snapshots: list[_Snapshot] = []

    # ---- inputs -----------------------------------------------------------------------------------------

    def _classify(self, t_dev: TimeMs, t_rx: TimeMs) -> str:
        """T01 sections 4.2 to 4.4: future-stamped, late (after the watermark of its step) or accepted."""
        if t_dev > t_rx + self._skew:
            return "future"
        if t_rx > self._k_up(t_dev) * self._step + self._delay:
            return "late"
        return "ok"

    def _k_up(self, t: TimeMs) -> int:
        return -((-t) // self._step)

    def observe_sample(self, sample: Sample) -> None:
        """File a sample (any order of arrival)."""
        self._order += 1
        status = self._classify(sample.t_device_ms, sample.t_rx_ms)
        self._samples.append((sample, status, self._order))
        node = _SIGNAL_NODE.get(sample.signal)
        if node is not None and node in BLE_DEVICES:
            self._msgs.append(
                _Msg(
                    node,
                    sample.signal,
                    sample.t_device_ms,
                    sample.t_rx_ms,
                    sample.seq,
                    status,
                    self._order,
                )
            )

    def observe_event(self, event: Event) -> None:
        """File an event: impulses become samples, the evidence kinds are read by their payload keys."""
        impulse = event_to_sample(event)
        if impulse is not None:
            self.observe_sample(impulse)
            return
        self._order += 1
        status = self._classify(event.t_device_ms, event.t_rx_ms)
        self._events.append((event, status, self._order))
        if event.kind in (EventKind.DEVICE_ERROR, EventKind.MEASUREMENT_MISSED) and (
            event.source in BLE_DEVICES
        ):
            self._msgs.append(
                _Msg(
                    event.source,
                    event.kind.value,
                    event.t_device_ms,
                    event.t_rx_ms,
                    event.seq,
                    status,
                    self._order,
                )
            )

    def observe_robot_evidence(
        self,
        t_ms: TimeMs,
        witness: EmbodiedWitnessEvidence,
        system: SystemHealthEvidence,
    ) -> None:
        """File a message of ``/ralmon/robot_evidence`` received at ``t_ms`` (the witness and robot system fields)."""
        self._snapshots.append((t_ms, witness, system))

    # ---- windows ----------------------------------------------------------------------------------------

    def _lookup(self, name: str) -> DurationMs:
        return as_duration_ms(self._registry.get(name))

    def _window(self, record: VerdictRecord, anchor_ms: TimeMs | None) -> _Window:
        if record.state not in (
            VerdictState.VIOLATED,
            VerdictState.PREDICTED_VIOLATION,
        ):
            raise ValueError(
                f"{record.instance_key}: a {record.state.value} record makes no alert, so it has no evidence"
            )
        template = record.template
        if record.state is VerdictState.VIOLATED and record.decided_at_ms is not None:
            ue = record.decided_at_ms
        else:
            ue = record.t_eval_ms
        window_ms: int | None = None
        if template is TemplateId.SCHED:
            window_ms = self._lookup("sched_window")
        elif template is TemplateId.RESP:
            window_ms = self._lookup("delta2")
        if anchor_ms is None:
            anchor_ms = instance_anchor_ms(
                record.instance_key,
                template,
                decided_at_ms=record.decided_at_ms,
                t_eval_ms=record.t_eval_ms,
                pending_until_ms=record.pending_until_ms,
                window_ms=window_ms,
                plan_anchor_ms=self._plan_anchor.get(record.instance_key),
            )
        if template is TemplateId.HOLD:
            a_read = anchor_ms - self._lookup("hold_lookback")
        elif template is TemplateId.INT:
            a_read = anchor_ms - self._lookup("int_window")
        elif template is TemplateId.COUNT and "@" not in record.instance_key:
            a_read = (
                (ue - 1) // _MS_PER_DAY
            ) * _MS_PER_DAY  # the day-end obligation reads the whole day
        else:
            a_read = anchor_ms
        devices = _DATA_SCOPE[template]
        robot = template in _ROBOT_SCOPE and not self._exclude_robot
        return _Window(
            template=template,
            key=record.instance_key,
            cutoff=ue + self._delay + self._grace,
            lo_rx=a_read - self._margin,
            lo_step=self._k_up(a_read - self._margin),
            hi_step=self._k_up(ue),
            wit_lo_step=self._k_up(a_read),
            nodes=(*devices, ROBOT) if robot else devices,
            devices=devices,
        )

    # ---- the vector --------------------------------------------------------------------------------------

    def evidence_for(
        self, record: VerdictRecord, *, anchor_ms: TimeMs | None = None
    ) -> EvidenceVector:
        """The vector of a violated (or predicted) record, from the inputs received by its cut-off."""
        w = self._window(record, anchor_ms)
        robot_in_scope = ROBOT in w.nodes
        tokens = self._tokens(w)
        lifecycle = self._lifecycle(w, tokens)
        ratio, seq_flag = self._sequence(w)
        witness = (
            self._witness(w)
            if robot_in_scope
            else EmbodiedWitnessEvidence(None, None, None)
        )
        system = SystemHealthEvidence(
            node_lifecycle=lifecycle,
            diagnostics_ok=self._diagnostics(w, tokens),
            liveliness_ok=self._liveliness(w),
            qos_deadline_missed=self._deadline(w),
            ble_link_quality=ratio,
            battery_low=self._battery(w, tokens) if robot_in_scope else None,
            nav_task_failed=self._task(w, "navigate") if robot_in_scope else None,
            manip_task_failed=self._task(w, "manipulate") if robot_in_scope else None,
        )
        if robot_in_scope:
            witness, system = self._merge_snapshot(w, witness, system)
        return EvidenceVector(
            provenance=ProvenanceEvidence(
                record.template, template_kind_of(record.template)
            ),
            system=system,
            signal_quality=SignalQualityEvidence(
                ecg_sqi=self._quality(w, SignalId.HR_ECG),
                ppg_sqi=self._quality(w, SignalId.SPO2),
                cuff_error_code=self._error_code(w),
            ),
            cross_device=CrossDeviceEvidence(self._hr_difference(w)),
            witness=witness,
            crypto_temporal=CryptoTemporalEvidence(
                authenticated=self._authenticated(w),
                seq_gap_or_replay=seq_flag,
                timestamp_implausible=self._timestamps(w),
            ),
        )

    # ---- selection of inputs ---------------------------------------------------------------------------

    def _vis(self, t_dev: TimeMs) -> int:
        return self._k_up(t_dev)

    def _event_axis_samples(
        self, w: _Window, signal: SignalId, *, start: int | None = None
    ) -> list[Sample]:
        """Accepted samples of a signal received by the cut-off whose visible step is in the window."""
        lo = w.lo_step if start is None else start
        return [
            s
            for s, status, _ in self._samples
            if s.signal == signal.value
            and status == "ok"
            and s.t_rx_ms <= w.cutoff
            and lo <= self._vis(s.t_device_ms) <= w.hi_step
        ]

    def _reports(self, w: _Window, node: str) -> list[Event]:
        """Accepted ``NODE_STATE`` reports of a node received by the cut-off and visible by the last admissible step."""
        found = [
            (self._vis(e.t_device_ms), order, e)
            for e, status, order in self._events
            if e.kind is EventKind.NODE_STATE
            and e.source == node
            and status == "ok"
            and e.t_rx_ms <= w.cutoff
            and self._vis(e.t_device_ms) <= w.hi_step
        ]
        found.sort(key=lambda item: (item[0], item[1]))
        return [e for _, _, e in found]

    def _relevant_reports(self, w: _Window, node: str) -> list[Event]:
        """The report in force at the window start, then the reports of the window."""
        reports = self._reports(w, node)
        before = [e for e in reports if self._vis(e.t_device_ms) < w.lo_step]
        inside = [e for e in reports if self._vis(e.t_device_ms) >= w.lo_step]
        return ([before[-1]] if before else []) + inside

    @staticmethod
    def _text(event: Event, key: str) -> str | None:
        value = event.payload.get(key)
        return value if isinstance(value, str) else None

    @staticmethod
    def _flag(event: Event, key: str) -> bool | None:
        value = event.payload.get(key)
        return value if isinstance(value, bool) else None

    def _token(self, w: _Window, node: str) -> str:
        """The lifecycle entry of a node: the last uncommanded adverse state, else the last commanded one, else active."""
        adverse = [
            (state, bool(self._flag(e, "commanded")) and state in _LIFECYCLE_STATES)
            for e in self._relevant_reports(w, node)
            for state in [self._text(e, "state")]
            if state is not None and state != "active"
        ]
        uncommanded = [s for s, commanded in adverse if not commanded]
        if uncommanded:
            return uncommanded[-1]
        if adverse:
            return f"{adverse[-1][0]}+commanded"
        return "active"

    def _tokens(self, w: _Window) -> dict[str, str]:
        return {node: self._token(w, node) for node in (*w.nodes, ROBOT)}

    # ---- system health --------------------------------------------------------------------------------

    def _lifecycle(
        self, w: _Window, tokens: Mapping[str, str]
    ) -> Mapping[str, str] | None:
        entries = {
            node: tokens[node]
            for node in w.nodes
            if self._profile.caps(node).status_reports
        }
        return entries or None

    def _diagnostics(self, w: _Window, tokens: Mapping[str, str]) -> bool | None:
        capable = [n for n in w.nodes if self._profile.caps(n).diagnostics]
        if not capable:
            return None
        last_ok = True
        for node in capable:
            reports = [
                (e, self._text(e, "diagnostics"))
                for e in self._relevant_reports(w, node)
                if self._text(e, "diagnostics") is not None
            ]
            if any(value in ("error", "stale") for _, value in reports):
                return False
            if not reports or reports[-1][1] != "ok" or tokens[node] != "active":
                last_ok = False
        return True if last_ok else None

    def _liveliness(self, w: _Window) -> bool | None:
        supervised = [n for n in w.nodes if self._profile.caps(n).supervised]
        if not supervised:
            return None
        for node in supervised:
            if any(
                self._text(e, "state") == "unreachable"
                for e in self._relevant_reports(w, node)
            ):
                return False
        return True

    def _deadline(self, w: _Window) -> bool | None:
        declared = [n for n in w.nodes if self._profile.caps(n).deadline_ms is not None]
        if not declared:
            return None
        for node in declared:
            deadline = self._profile.caps(node).deadline_ms
            assert deadline is not None
            if node in BLE_DEVICES:
                arrivals = sorted(
                    m.t_rx for m in self._msgs if m.node == node and m.t_rx <= w.cutoff
                )
                points = [0, *arrivals, w.cutoff]
                for earlier, later in pairwise(points):
                    miss = earlier + deadline
                    if later - earlier > deadline and w.lo_rx <= miss <= w.cutoff:
                        return True
            for e, _, _ in self._events:
                if (
                    e.kind is EventKind.NODE_STATE
                    and e.source == node
                    and self._flag(e, "deadline_missed") is True
                    and w.lo_rx <= e.t_rx_ms <= w.cutoff
                ):
                    return True
        return False

    def _battery(self, w: _Window, tokens: Mapping[str, str]) -> bool | None:
        if not self._profile.caps(ROBOT).battery:
            return None
        values = [
            self._flag(e, "battery_low")
            for e in self._relevant_reports(w, ROBOT)
            if self._flag(e, "battery_low") is not None
        ]
        if any(values):
            return True
        if values and tokens[ROBOT] == "active":
            return False
        return None

    def _task(self, w: _Window, task: str) -> bool | None:
        outcomes = self._outcomes(w, task)
        if any(o in _FAILED for o in outcomes):
            return True
        if outcomes and all(o == "success" for o in outcomes):
            return False
        return None

    def _outcomes(
        self, w: _Window, task: str, *, start: int | None = None
    ) -> list[str]:
        lo = w.lo_step if start is None else start
        found: list[str] = []
        for e, status, _ in self._events:
            if (
                e.kind is not EventKind.ROBOT_TASK
                or status != "ok"
                or e.t_rx_ms > w.cutoff
                or not lo <= self._vis(e.t_device_ms) <= w.hi_step
                or self._text(e, "task") != task
            ):
                continue
            patient = e.payload.get("patient_id")
            if (
                self._patient is not None
                and patient is not None
                and patient != self._patient
            ):
                continue
            outcome = self._text(e, "outcome")
            if outcome in _FAILED or outcome == "success":
                found.append(
                    outcome
                )  # 'declined' has no evidence field (ADR-040 proposed)
        return found

    # ---- signal quality and the cross-device pair -----------------------------------------------------

    def _quality(self, w: _Window, signal: SignalId) -> float | None:
        qualities = [
            s.quality
            for s in self._event_axis_samples(w, signal)
            if s.quality is not None
        ]
        return min(qualities) if qualities else None

    def _error_code(self, w: _Window) -> str | None:
        codes = sorted(
            (e.t_device_ms, order, self._text(e, "error_code"))
            for e, status, order in self._events
            if e.kind is EventKind.DEVICE_ERROR
            and e.source == CUFF
            and status == "ok"
            and e.t_rx_ms <= w.cutoff
            and w.lo_step <= self._vis(e.t_device_ms) <= w.hi_step
            and self._text(e, "error_code")
        )
        if codes:
            return codes[-1][2]
        spoke = any(
            m.node == CUFF and w.lo_rx <= m.t_rx <= w.cutoff for m in self._msgs
        )
        if self._profile.caps(CUFF).error_codes and spoke:
            return ""
        return None

    def _hr_difference(self, w: _Window) -> float | None:
        ecg = sorted(
            (self._vis(s.t_device_ms), s.t_device_ms, order, s.value)
            for s, status, order in self._samples
            if s.signal == SignalId.HR_ECG.value
            and status == "ok"
            and s.t_rx_ms <= w.cutoff
        )
        best: float | None = None
        for pulse in self._event_axis_samples(w, SignalId.HR_PULSE):
            step = self._vis(pulse.t_device_ms)
            held = [e for e in ecg if e[0] <= step]
            if not held:
                continue
            latest = held[-1]
            if (step - latest[0]) * self._step > self._max_age:
                continue
            diff = abs(pulse.value - latest[3])
            best = diff if best is None else max(best, diff)
        return best

    # ---- sequence, time and authentication evidence (axis R) ------------------------------------------

    def _watermark(self, t_dev: TimeMs) -> TimeMs:
        return self._k_up(t_dev) * self._step + self._delay

    def _device_sequence(
        self, w: _Window, node: str
    ) -> tuple[float | None, bool | None]:
        """(delivery ratio, repeat or gap) of one capable device: D-3 and D-9 of evidence-channels.md."""
        received = [m for m in self._msgs if m.node == node and m.t_rx <= w.cutoff]
        in_window = [m for m in received if w.lo_rx <= m.t_rx <= w.cutoff]
        with_seq = [m for m in received if m.seq is not None]
        window_seq = [m for m in in_window if m.seq is not None]
        if not window_seq:
            return None, None
        # a repeat: a received (name, seq) equal to an accepted one (arrival order)
        accepted: set[tuple[str, int]] = set()
        repeat = False
        for m in sorted(with_seq, key=lambda m: (m.t_rx, m.order)):
            assert m.seq is not None
            ident = (m.name, m.seq)
            if ident in accepted and w.lo_rx <= m.t_rx <= w.cutoff:
                repeat = True
            if m.status == "ok":
                accepted.add(ident)
        finalised = [m for m in window_seq if self._watermark(m.t_dev) <= w.cutoff]
        if not finalised:
            return None, True if repeat else None
        before = [
            m.seq
            for m in with_seq
            if m.t_rx < w.lo_rx
            and self._watermark(m.t_dev) <= w.cutoff
            and m.seq is not None
        ]
        window_values = [m.seq for m in finalised if m.seq is not None]
        base = max(before) if before else min(window_values) - 1
        top = max(window_values)
        span = set(range(base + 1, top + 1))
        present = {m.seq for m in with_seq if m.seq is not None} & span
        ratio = len(present) / len(span) if span else 1.0
        gap = len(present) < len(span)
        return ratio, repeat or gap

    def _sequence(self, w: _Window) -> tuple[float | None, bool | None]:
        capable = [d for d in w.devices if self._profile.caps(d).seq]
        if not capable:
            return None, None
        ratios: list[float | None] = []
        flags: list[bool | None] = []
        for node in capable:
            ratio, flag = self._device_sequence(w, node)
            ratios.append(ratio)
            flags.append(flag)
        known = [r for r in ratios if r is not None]
        link: float | None = None
        if known:
            lowest = min(known)
            # a capable device without a basis prevents a denial, never hides a gap
            link = None if (len(known) < len(ratios) and lowest == 1.0) else lowest
        if any(flag is True for flag in flags):
            return link, True
        if all(flag is False for flag in flags):
            return link, False
        return link, None

    def _timestamps(self, w: _Window) -> bool | None:
        in_window = {
            d: [m for m in self._msgs if m.node == d and w.lo_rx <= m.t_rx <= w.cutoff]
            for d in w.devices
        }
        if any(m.status != "ok" for msgs in in_window.values() for m in msgs):
            return True
        capable = [d for d in w.devices if self._profile.caps(d).two_clocks]
        if capable and all(in_window[d] for d in capable):
            return False
        return None

    def _authenticated(self, w: _Window) -> bool | None:
        for e, _, _ in self._events:
            if (
                e.kind is EventKind.VERIFICATION
                and self._text(e, "verification") == "failed"
                and self._text(e, "subject") in w.devices
                and w.lo_rx <= e.t_rx_ms <= w.cutoff
            ):
                return False
        capable = [d for d in w.devices if self._profile.caps(d).authenticates]
        if not capable:
            return None
        for node in capable:
            if not any(
                m.node == node and w.lo_rx <= m.t_rx <= w.cutoff for m in self._msgs
            ):
                return None
        return True

    # ---- the embodied witness (H-MASK, H-INIT and the episode rule of ADR-054) -------------------------

    def _episodes(self, w: _Window) -> list[tuple[int, int]]:
        """The maximal runs of steps (start, end exclusive) in which the robot channels are available."""
        available = False
        colocated = False
        runs: list[tuple[int, int]] = []
        start = 0
        for e in self._reports(w, ROBOT):
            state = self._text(e, "state")
            flag = self._flag(e, "colocated")
            if flag is not None:
                colocated = flag
            now = state == "active" and colocated if state is not None else available
            step = self._vis(e.t_device_ms)
            if now and not available:
                start = step
            elif available and not now:
                runs.append((start, step))
            available = now
        if available:
            runs.append((start, w.hi_step + 1))
        return runs

    def _witness(self, w: _Window) -> EmbodiedWitnessEvidence:
        runs = self._episodes(w)
        steps = range(w.wit_lo_step, w.hi_step + 1)
        episode_of: dict[int, int] = {}
        for step in steps:
            for start, end in runs:
                if start <= step < end:
                    episode_of[step] = start
        presence = [
            (self._vis(s.t_device_ms), s.t_device_ms, order, s.value)
            for s, status, order in self._samples
            if s.signal == SignalId.PRESENCE.value
            and status == "ok"
            and s.t_rx_ms <= w.cutoff
        ]
        levels: dict[int, float | None] = {}
        for step, start in episode_of.items():
            held = sorted(p for p in presence if start <= p[0] <= step)
            levels[step] = held[-1][3] if held else None
        every_step_available = all(step in episode_of for step in steps)
        saw = any(level is not None and level > 0.0 for level in levels.values())
        if saw:
            robot_present: bool | None = True
        elif every_step_available and all(
            levels.get(step) is not None for step in steps
        ):
            robot_present = False
        else:
            robot_present = None
        intake_event = any(
            s.signal == SignalId.INTAKE.value
            and status == "ok"
            and s.t_rx_ms <= w.cutoff
            and w.wit_lo_step <= self._vis(s.t_device_ms) <= w.hi_step
            for s, status, _ in self._samples
        )
        failed_visit = any(
            o in _FAILED
            for task in ("manipulate", "witness")
            for o in self._outcomes(w, task, start=w.wit_lo_step)
        )
        if intake_event:
            intake: bool | None = True
        elif every_step_available and not failed_visit:
            intake = False
        else:
            intake = None
        identity: bool | None = None
        if robot_present is True:
            reported = sorted(
                (e.t_device_ms, order, e.payload["identity_confirmed"])
                for e, status, order in self._events
                if e.kind is EventKind.ROBOT_TASK
                and status == "ok"
                and e.t_rx_ms <= w.cutoff
                and w.wit_lo_step <= self._vis(e.t_device_ms) <= w.hi_step
                and self._text(e, "task") == "witness"
                and isinstance(e.payload.get("identity_confirmed"), bool)
            )
            if reported:
                value = reported[-1][2]
                identity = value if isinstance(value, bool) else None
        return EmbodiedWitnessEvidence(robot_present, identity, intake)

    # ---- the robot evidence messages (placement rules) ---------------------------------------------------

    def _merge_snapshot(
        self,
        w: _Window,
        witness: EmbodiedWitnessEvidence,
        system: SystemHealthEvidence,
    ) -> tuple[EmbodiedWitnessEvidence, SystemHealthEvidence]:
        usable = [s for s in self._snapshots if w.lo_rx <= s[0] <= w.cutoff]
        if not usable:
            return witness, system
        _, theirs_w, theirs_s = max(usable, key=lambda s: s[0])

        def fill(mine: bool | None, theirs: bool | None) -> bool | None:
            return mine if mine is not None else theirs

        def merge(mine: bool | None, theirs: bool | None, adverse: bool) -> bool | None:
            if mine is adverse or theirs is adverse:
                return adverse
            return fill(mine, theirs)

        merged_witness = EmbodiedWitnessEvidence(
            robot_present=fill(witness.robot_present, theirs_w.robot_present),
            identity_confirmed=fill(
                witness.identity_confirmed, theirs_w.identity_confirmed
            ),
            intake_observed=fill(witness.intake_observed, theirs_w.intake_observed),
        )
        lifecycle = _merge_lifecycle(system.node_lifecycle, theirs_s.node_lifecycle)
        merged_system = SystemHealthEvidence(
            node_lifecycle=lifecycle,
            diagnostics_ok=merge(system.diagnostics_ok, theirs_s.diagnostics_ok, False),
            liveliness_ok=merge(system.liveliness_ok, theirs_s.liveliness_ok, False),
            qos_deadline_missed=merge(
                system.qos_deadline_missed, theirs_s.qos_deadline_missed, True
            ),
            ble_link_quality=system.ble_link_quality,
            battery_low=merge(system.battery_low, theirs_s.battery_low, True),
            nav_task_failed=merge(
                system.nav_task_failed, theirs_s.nav_task_failed, True
            ),
            manip_task_failed=merge(
                system.manip_task_failed, theirs_s.manip_task_failed, True
            ),
        )
        return merged_witness, merged_system


def _adverse(token: str) -> bool:
    return token != "active" and not token.endswith("+commanded")


def _merge_lifecycle(
    mine: Mapping[str, str] | None, theirs: Mapping[str, str] | None
) -> Mapping[str, str] | None:
    if mine is None and theirs is None:
        return None
    out: dict[str, str] = {}
    for node in sorted({*(mine or {}), *(theirs or {})}):
        a = (mine or {}).get(node)
        b = (theirs or {}).get(node)
        if a is not None and _adverse(a):
            out[node] = a
        elif b is not None and _adverse(b):
            out[node] = b
        else:
            out[node] = a if a is not None else b if b is not None else "active"
    return out or None


def extract_evidence(
    day: ObservedTrace,
    records: Sequence[VerdictRecord],
    registry: ParameterRegistry,
    *,
    step_ms: DurationMs,
    reorder_delay_ms: DurationMs,
    profile: DeviceProfile | None = None,
    plan: CarePlan | None = None,
    exclude_robot: bool = False,
) -> dict[str, EvidenceVector]:
    """The evidence mapping ``{instance_key: EvidenceVector}`` of the violation-claiming records of a day.

    Equal to feeding the samples and events of the day into an ``EvidenceExtractor`` in receive order and asking at each
    record's cut-off. The key is ``VerdictRecord.instance_key`` (decision D-1): one vector per instance, from the first
    VIOLATED record, else from the first PREDICTED_VIOLATION record. A PENDING or SATISFIED record has none.
    """
    extractor = EvidenceExtractor(
        registry,
        step_ms=step_ms,
        reorder_delay_ms=reorder_delay_ms,
        profile=profile,
        patient_id=day.patient_id,
        plan=plan,
        exclude_robot=exclude_robot,
    )
    for sample in sorted(day.samples, key=lambda s: (s.t_rx_ms, s.t_device_ms)):
        extractor.observe_sample(sample)
    for event in sorted(day.events, key=lambda e: (e.t_rx_ms, e.t_device_ms)):
        extractor.observe_event(event)
    chosen: dict[str, VerdictRecord] = {}
    for record in records:
        if record.state not in (
            VerdictState.VIOLATED,
            VerdictState.PREDICTED_VIOLATION,
        ):
            continue
        held = chosen.get(record.instance_key)
        better = (
            held is None
            or (
                held.state is not VerdictState.VIOLATED
                and record.state is VerdictState.VIOLATED
            )
            or (held.state is record.state and record.t_eval_ms < held.t_eval_ms)
        )
        if better:
            chosen[record.instance_key] = record
    return {key: extractor.evidence_for(rec) for key, rec in chosen.items()}
