"""``StreamingMonitor``: the measured half of the runtime safety monitor (WS05-T04).

The loop is the one of docs/formal/05 section 6.2. Inputs are validated, tested for lateness against
the two clocks (R-late), deduplicated by ``(source, name, seq)`` (rule R8) and put into a bounded
reorder buffer. ``advance(t)`` finalises the steps ``k <= floor((t - D) / T_s)`` in order: it releases
the inputs of the step in device-time order, updates the summaries and the derived signals (a clock
sample at every step), creates the instances anchored by the released events, evaluates every active
instance by its closed form, applies the verdict rule and emits one record per active instance.
Definitive verdicts come from the measured prefix only (ADR-008); there is no forecaster and no
conformal code here, and ``predictive=True`` is refused until WS05-T08.

Additive to the contract ``Monitor`` Protocol (ahead of the contract, ADR-029 and ADR-048): the methods
``push_availability`` (the availability mask of the robot channels, CG-6; the trace has none, ADR-035),
``late_inputs``, ``rejected_inputs``, ``stats`` and ``close``, and the keyword-only constructor
arguments ``template_ids``, ``require_signature`` and ``buffer_capacity``.
"""

from __future__ import annotations

import bisect
import math
from collections import deque
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Protocol

from ralmon.monitor._text import (
    MAX_SEQ,
    as_int,
    as_number,
    converting,
    show,
)
from ralmon.monitor.config import (
    T_DAY_MS,
    MonitorConfig,
    MonitorConfigError,
    MonitorInputError,
    MonitorInvariantError,
    PlanFeasibilityError,
    PlanVersionError,
    check_config,
)
from ralmon.monitor.forecast import Forecaster
from ralmon.monitor.formula import build_path_table, check_library_formulas
from ralmon.monitor.instances import (
    CountEndInstance,
    CountLimitInstance,
    EngineContext,
    HoldInstance,
    Instance,
    IntInstance,
    RangeInstance,
    RespInstance,
    SchedInstance,
    StepView,
    SysInstance,
    WitnessTracker,
)
from ralmon.monitor.parameters import (
    check_alignment,
    check_registry,
    layer_values,
    optional_value,
    read_bounds,
    read_latency,
    read_overrides,
    read_value,
)
from ralmon.monitor.reorder import (
    BufferedInput,
    ReorderBuffer,
    is_late,
    step_of,
    watermark_ms,
)
from ralmon.monitor.verdict import VerdictRecord
from ralmon.signals import (
    DurationMs,
    Event,
    EventKind,
    Sample,
    SignalId,
    TimeMs,
    default_derived_signals,
    event_to_sample,
)
from ralmon.spec import (
    CarePlan,
    PlanIntegrityError,
    PlanVerifier,
    Template,
    TemplateId,
    TemplateInstance,
    verify_plan,
)

__all__ = [
    "DEFAULT_BUFFER_CAPACITY",
    "MAX_STEPS_PER_ADVANCE",
    "ChannelAvailability",
    "Monitor",
    "MonitorStats",
    "RejectedInput",
    "StreamingMonitor",
]

# algorithmic: the default capacity of the reorder buffer in inputs (a day of 1 Hz inputs from a dozen
# devices is below it); the overflow policy is to report the input, never to drop it silently
DEFAULT_BUFFER_CAPACITY: Final[int] = 100_000
# algorithmic: the largest capacity that can be asked for
MAX_BUFFER_CAPACITY: Final[int] = 10_000_000
# algorithmic: the most steps one ``advance`` call finalises and the most records it may emit; a call that
# would exceed either is refused before any state changes
MAX_STEPS_PER_ADVANCE: Final[int] = 1_000_000
MAX_RECORDS_PER_ADVANCE: Final[int] = 5_000_000
# algorithmic: the most rejected inputs kept in the report lists (the counters keep the total)
REPORT_CAPACITY: Final[int] = 100_000
# algorithmic: the most (source, name, seq) keys kept for the duplicate rule
DEDUP_CAPACITY: Final[int] = 1_000_000

_PLAIN_SAMPLES: Final = frozenset(
    {
        SignalId.BP,
        SignalId.CUFF_HEALTH,
        SignalId.INFLATION_MS,
        SignalId.PRESENCE,
        SignalId.AUTH,
        SignalId.HR_ECG,
        SignalId.HR_PULSE,
        SignalId.SPO2,
    }
)
_ROBOT_CHANNELS: Final = frozenset({SignalId.PRESENCE, SignalId.INTAKE})
_USED_EVENTS: Final = frozenset(
    {
        EventKind.MEASUREMENT,
        EventKind.DISPENSE,
        EventKind.INTAKE,
        EventKind.SCHEDULE_TICK,
    }
)
# events of one device time are applied in this order whatever the order of arrival: a measurement, then
# a dispense (the usual order, M5), then the robot's intake, then the schedule tick
_EVENT_ORDER: Final[dict[object, int]] = {
    EventKind.MEASUREMENT: 0,
    EventKind.DISPENSE: 1,
    EventKind.INTAKE: 2,
    EventKind.SCHEDULE_TICK: 3,
}
_MEASUREMENT_TEMPLATES: Final = (TemplateId.RANGE, TemplateId.SYS)
_DISPENSE_TEMPLATES: Final = (
    TemplateId.HOLD,
    TemplateId.COUNT,
    TemplateId.RESP,
    TemplateId.INT,
)
# no derived signal reads this signal: the sample only advances the clock of the derived signals
_CLOCK_SIGNAL: Final = SignalId.SPO2
_NAN: Final = math.nan


class Monitor(Protocol):
    """The contract ``Monitor`` (02-interfaces.md#monitor, version 0.1.0)."""

    def load(self, plan: CarePlan) -> None: ...  # verifies plan signature if present

    def push_sample(self, sample: Sample) -> None: ...

    def push_event(self, event: Event) -> None: ...

    def advance(
        self, t_ms: TimeMs
    ) -> Sequence[
        VerdictRecord
    ]: ...  # causal: uses only inputs with t_device_ms <= t_ms - reorder_delay_ms

    def verdict_latency_bound_ms(self, template: TemplateId) -> DurationMs: ...


@dataclass(frozen=True, slots=True)
class RejectedInput:
    """An input that was not used, with the reason: ``late``, ``future_stamp``, ``duplicate``,
    ``capacity`` or ``finalised`` (it arrived after its step was finalised)."""

    item: object
    t_rx_ms: int
    reason: str
    watermark_ms: int | None


@dataclass(frozen=True, slots=True)
class ChannelAvailability:
    """The availability of a robot channel (``presence`` or ``intake``) from a device time on."""

    signal: SignalId
    available: bool
    t_device_ms: int
    t_rx_ms: int


@dataclass(frozen=True, slots=True)
class MonitorStats:
    """Counters of a monitor (no wall clock). ``node_updates`` counts constant-time units of work:
    one per instance evaluation, one per step summary and one per released input."""

    node_updates: int
    retained_samples: int
    retained_dedup_keys: int
    buffered_inputs: int
    active_instances: int
    steps_finalised: int
    records_emitted: int
    accepted_count: int
    released_count: int
    late_count: int
    future_stamped_count: int
    duplicate_count: int
    overflow_count: int
    after_finalisation_count: int
    ignored_events: int
    out_of_domain_samples: int
    rho_unavailable: int
    future_stamp_check: bool
    dedup_evicted_count: int = 0
    ignored_samples: int = 0
    anchors_without_plan: int = 0
    presence_level_older_than_window_steps: int = 0


def _seq_of(instance: Instance) -> int:
    return instance.seq


class StreamingMonitor:
    """The runtime safety monitor, measured half: a ``Monitor`` over the grid of period ``T_s``.

    Costs (docs/formal/05 section 6.4; checked by tests/monitor/test_latency_cost.py). Ingestion of one
    input is O(log b) for a reorder buffer holding b inputs, plus O(1) to validate and to update the
    summaries. Evaluation costs O(A) per finalised grid step for A active template instances, amortised:
    each instance updates and tests its closed form once per step in O(1) and emits one record. Memory is
    O(largest window in steps + b): the buffer of b inputs, the dispenses of the trailing 24 h (the
    largest window, the ``dose_count`` of 01 section 5.1), the duplicate keys of the same window and
    O(1) per active instance; nothing proportional to the length of the trace is kept. (Per sample the
    O(A) cost is met when every step receives an input; a step with no input still costs O(A), which is
    the bound reported: OP-T05-15.)

    Verdict latency (the bound ``verdict_latency_bound_ms``): a definitive record of an instance
    anchored at device time ``a`` is emitted at monitor time ``decided_at + D``, at most
    ``max_latency_<id> + reorder_delay_ms`` after ``a``, with ``max_latency_<id> = B + T_s`` and ``B``
    the deadline offset of the template: RANGE, HOLD, COUNT, SYS and INT ``T_s``; SCHED ``sched_window +
    T_s``; RESP ``delta2 + T_s`` (docs/formal/05 section 7.2, Lemma 13). The bound holds when
    ``advance`` is called at every ``t_k + D`` and no position of the decision window is stale-open
    (an unavailable robot channel, an undefined pre-dose pressure): such an instance is never decided.

    Causality: ``advance(t)`` uses only inputs with ``t_device_ms <= t - D``. Lateness is decided from
    the two clocks of an input (``t_rx > t_{k_up(t_dev)} + D``, an arrival exactly at the watermark is on
    time) and not from the calls of ``advance``; a late input is excluded, listed by ``late_inputs()``
    and never changes an emitted record. The monitor never reads ground truth.

    Instances and keys. A dynamic instance is created at its anchoring event of a finalised step and is
    keyed ``<template id>@<t_device_ms of the event>`` (``range@25200000``); a second instance with the
    same key while one is active, or a static key of the plan, gets the suffix ``#2``, ``#3``, ... in
    creation order. Static instances (SCHED, the day-end COUNT) are keyed by the plan. Two SCHED instances
    with one anchor take each other as the next tick, so the earlier one is not refined after its window.
    Anchors that arrive before any plan was loaded create nothing and are counted by
    ``stats().anchors_without_plan``.

    The witness. ``presence`` is a held level that belongs to one co-location episode (ADR-054, proposed):
    a step at which ``push_availability`` has marked the channel unavailable clears the level, and after
    the channel returns the level is undefined until a new sample arrives (``value_undefined:presence``).
    HAZARD, not a feature: a trace with no availability mark and no zero-valued presence sample (the
    output of the benchmark generator, WS04-T06 test 11) keeps the level of the last robot visit for the
    rest of the day, so INT is satisfied by an old sample (docs/formal/02 section 4.7, TG-9);
    ``stats().presence_level_older_than_window_steps`` counts the steps at which that happens.
    """

    @converting(MonitorConfigError)
    def __init__(
        self,
        config: MonitorConfig,
        registry: Any,
        templates: Sequence[Template],
        *,
        calibrator: object | None = None,
        forecaster: Forecaster | None = None,
        verifier: PlanVerifier | None = None,
        template_ids: Collection[TemplateId] | None = None,
        require_signature: bool = False,
        buffer_capacity: int = DEFAULT_BUFFER_CAPACITY,
    ) -> None:
        cfg = check_config(config)
        self._step = cfg.step_ms
        self._delay = cfg.reorder_delay_ms
        self._k_day = T_DAY_MS // self._step
        self._registry = registry
        # accepted and never called: the predictive mode is WS05-T08 (the forecaster cannot change a
        # definitive verdict, Lemma 9)
        self._calibrator = calibrator
        self._forecaster = forecaster
        self._read_registry_basics(registry, cfg)
        if verifier is not None and not callable(getattr(verifier, "verify", None)):
            raise MonitorConfigError(
                f"verifier must have a verify method, got {show(verifier)}"
            )
        self._verifier = verifier
        if not isinstance(require_signature, bool):
            raise MonitorConfigError(
                f"require_signature must be a bool, got {show(require_signature)}"
            )
        self._require_signature = require_signature
        capacity = as_int(
            buffer_capacity,
            "buffer_capacity",
            MonitorConfigError,
            low=1,
            high=MAX_BUFFER_CAPACITY,
        )
        self._buffer = ReorderBuffer(capacity)
        self._templates = self._read_templates(templates, template_ids)
        check_library_formulas(list(self._templates.values()))
        self._defaults: dict[TemplateId, dict[str, float]] = {}
        scales: dict[TemplateId, float] = {}
        self._latency: dict[TemplateId, int] = {}
        for tid, template in self._templates.items():
            self._defaults[tid] = {n: read_value(registry, n) for n in template.params}
            scale = read_value(registry, template.scale_param)
            if not scale > 0.0:
                raise MonitorConfigError(
                    f"registry: {template.scale_param!r} must be positive, got {show(scale)}"
                )
            scales[tid] = scale
            self._latency[tid] = read_latency(registry, template) + self._delay
            check_alignment(
                self._defaults[tid],
                self._step,
                f"registry value of template {tid.value}",
            )
        self._ctx = EngineContext(
            self._step,
            self._bound_lower,
            self._bound_upper,
            self._error_sd,
            scales,
            {tid: build_path_table(tid) for tid in self._templates},
        )
        self._overrides = read_overrides(registry)
        # state
        self._closed = False
        self._k_f = -1
        self._last_advance: int | None = None
        self._plan_versions: dict[str, int] = {}
        self._plan_id: str | None = None
        self._plan_loaded = False
        self._started: set[str] = set()
        self._static_keys: set[str] = set()
        self._scheduled: dict[int, list[Instance]] = {}
        self._dyn_params: dict[TemplateId, dict[str, float]] = {
            tid: dict(p) for tid, p in self._defaults.items()
        }
        self._int_window_steps = self._int_window_in_steps()
        self._active: list[Instance] = []
        self._active_keys: set[str] = set()
        self._dayend_active: list[CountEndInstance] = []
        self._seq = 0
        self._derived = list(default_derived_signals())
        self._derived_last: dict[str, float] = {}
        self._dispense_steps: deque[int] = deque()
        self._witness = WitnessTracker()
        self._view = StepView(self._witness)
        self._bp = _NAN
        self._ch = _NAN
        self._infl = _NAN
        self._presence = _NAN
        self._presence_off = False
        self._intake_off = False
        self._last_meas_step = -1
        self._meas_n = 0
        self._intake_n = 0
        self._auth_n = 0
        # dedup and reports
        self._seen: dict[tuple[object, ...], int] = {}
        self._seen_order: deque[tuple[int, tuple[object, ...]]] = deque()
        self._rejected: deque[RejectedInput] = deque(maxlen=REPORT_CAPACITY)
        # counters
        self._nodes = 0
        self._records = 0
        self._accepted = 0
        self._released = 0
        self._late = 0
        self._future = 0
        self._dup = 0
        self._overflow = 0
        self._after = 0
        self._ignored = 0
        self._out_of_domain = 0
        self._dedup_evicted = 0
        self._ignored_samples = 0
        self._unplanned = 0
        self._stale_presence = 0
        self._presence_step = -1

    # -- construction helpers ---------------------------------------------------------------------

    def _read_registry_basics(self, registry: Any, cfg: MonitorConfig) -> None:
        check_registry(registry)
        version = registry.version()
        if not isinstance(version, str):
            raise MonitorConfigError(
                f"registry version must be a str, got {show(version)}"
            )
        if cfg.registry_version != version:
            raise MonitorConfigError(
                f"config.registry_version {cfg.registry_version!r} differs from the loaded registry {version!r}"
            )
        self._registry_version = version
        registry_step = getattr(registry, "step_ms", None)
        if registry_step is not None and registry_step != cfg.step_ms:
            raise MonitorConfigError(
                f"config.step_ms {cfg.step_ms} differs from the step_ms of the registry {show(registry_step)}: "
                "load the registry with the step of the monitor"
            )
        self._bound_lower, self._bound_upper = read_bounds(registry)
        # optional names: an unset or absent name switches the feature off and the monitor says so
        self._skew = optional_value(registry, "clock_skew_max_ms", low=0.0)
        sd = optional_value(registry, "cuff_error_sd", low=None)
        self._error_sd = sd if sd is not None and sd > 0.0 else None

    @staticmethod
    def _read_templates(
        templates: Sequence[Template], template_ids: Collection[TemplateId] | None
    ) -> dict[TemplateId, Template]:
        if not isinstance(templates, (list, tuple)):
            raise MonitorConfigError(
                f"templates must be a list or a tuple, got {show(templates)}"
            )
        library: dict[TemplateId, Template] = {}
        for template in templates:
            if not isinstance(template, Template):
                raise MonitorConfigError(
                    f"templates must be Template objects, got {show(template)}"
                )
            if template.id in library:
                raise MonitorConfigError(
                    f"template {template.id.value!r} appears twice"
                )
            library[template.id] = template
        if template_ids is None:
            return library
        if isinstance(template_ids, (str, bytes)) or not isinstance(
            template_ids, Iterable
        ):
            raise MonitorConfigError(
                f"template_ids must be a collection of TemplateId, got {show(template_ids)}"
            )
        wanted = list(template_ids)
        if not wanted or not all(isinstance(t, TemplateId) for t in wanted):
            raise MonitorConfigError(
                f"template_ids must be a non-empty collection of TemplateId, got {show(template_ids)}"
            )
        missing = [t.value for t in wanted if t not in library]
        if missing:
            raise MonitorConfigError(
                f"template_ids names templates absent from the library: {missing}"
            )
        chosen = set(wanted)
        return {tid: t for tid, t in library.items() if tid in chosen}

    # -- the contract -----------------------------------------------------------------------------

    @converting(
        MonitorInputError, MonitorConfigError, PlanVersionError, PlanIntegrityError
    )
    def load(self, plan: CarePlan) -> None:
        """Load a care plan: structure, signature, exact registry version, ``plan_version`` never
        decreasing per ``care_plan_id``, feasibility. A failed load changes nothing."""
        self._check_open()
        read = _read_plan(plan)
        verify_plan(
            plan,
            self._verifier,
            registry_version=self._registry_version,
            require_signature=self._require_signature,
        )
        known = self._plan_versions.get(read.care_plan_id)
        if known is not None and read.plan_version < known:
            raise PlanVersionError(
                f"plan {read.care_plan_id!r} has plan_version {read.plan_version}, "
                f"lower than the loaded {known}"
            )
        built = self._build(read)
        self._commit(read, built)

    @converting(MonitorInputError)
    def push_sample(self, sample: Sample) -> None:
        self._check_open()
        if not isinstance(sample, Sample):
            raise MonitorInputError(f"expected a Sample, got {show(sample)}")
        signal = self._signal_of(sample.signal)
        if signal not in _PLAIN_SAMPLES and signal is not SignalId.DAY_END:
            raise MonitorInputError(
                f"signal {signal.value!r} does not travel as a Sample (impulses travel as events, "
                "derived and generated signals are computed by the monitor; a day_end sample is ignored)"
            )
        t_dev = as_int(sample.t_device_ms, "t_device_ms", MonitorInputError)
        t_rx = as_int(sample.t_rx_ms, "t_rx_ms", MonitorInputError)
        value = as_number(sample.value, "value", MonitorInputError)
        seq = self._seq_of_input(sample.seq)
        quality = sample.quality
        if quality is not None:
            as_number(quality, "quality", MonitorInputError)
        if signal is SignalId.DAY_END:
            # the end-of-day impulse is generated by the monitor from the plan (docs/formal/01 section
            # 2.2); a producer that also writes it (the benchmark generator does) is ignored and counted
            self._ignored_samples += 1
            return
        self._ingest(
            "sample",
            sample,
            t_dev,
            t_rx,
            seq,
            ("sample", None, signal.value, seq),
            (signal, value),
        )

    @converting(MonitorInputError)
    def push_event(self, event: Event) -> None:
        self._check_open()
        if not isinstance(event, Event):
            raise MonitorInputError(f"expected an Event, got {show(event)}")
        kind = event.kind
        if not isinstance(kind, EventKind):
            raise MonitorInputError(
                f"event kind must be an EventKind, got {show(kind)}"
            )
        t_dev = as_int(event.t_device_ms, "t_device_ms", MonitorInputError)
        t_rx = as_int(event.t_rx_ms, "t_rx_ms", MonitorInputError)
        source = event.source
        if not isinstance(source, str):
            raise MonitorInputError(f"event source must be a str, got {show(source)}")
        if not isinstance(event.payload, Mapping):
            raise MonitorInputError(
                f"event payload must be a mapping, got {show(event.payload)}"
            )
        seq = self._seq_of_input(event.seq)
        if kind not in _USED_EVENTS:
            self._ignored += (
                1  # evidence for the attribution layer, not a signal (01 section 2.1)
            )
            return
        self._ingest(
            "event",
            event,
            t_dev,
            t_rx,
            seq,
            ("event", source[:], kind.value, seq),
            (kind,),
        )

    @converting(MonitorInputError)
    def push_availability(
        self, signal: SignalId, available: bool, t_device_ms: TimeMs, t_rx_ms: TimeMs
    ) -> None:
        """Mark the robot channel ``signal`` (``presence`` or ``intake``) available or unavailable from
        the step that shows device time ``t_device_ms`` on (CG-6). A channel is available until marked.

        Marking ``presence`` unavailable also ends the held level of the channel (ADR-054, proposed): after
        it returns, the level is undefined until a new presence sample arrives. A sample that arrives
        while the channel is down is not held after the return."""
        self._check_open()
        channel = self._signal_of(signal)
        if channel not in _ROBOT_CHANNELS:
            raise MonitorInputError(
                f"only the robot channels can be marked, got {channel.value!r}"
            )
        if not isinstance(available, bool):
            raise MonitorInputError(f"available must be a bool, got {show(available)}")
        t_dev = as_int(t_device_ms, "t_device_ms", MonitorInputError)
        t_rx = as_int(t_rx_ms, "t_rx_ms", MonitorInputError)
        mark = ChannelAvailability(channel, available, t_dev, t_rx)
        self._ingest("avail", mark, t_dev, t_rx, None, None, (channel, available))

    @converting(MonitorInputError, MonitorInvariantError)
    def advance(self, t_ms: TimeMs) -> tuple[VerdictRecord, ...]:
        """Finalise the steps up to ``floor((t_ms - D) / T_s)`` and return their records, in step order.

        Causal: only inputs with ``t_device_ms <= t_ms - D`` are used. ``t_ms`` must not decrease; the
        same time again returns no record. A call that would finalise more than ``MAX_STEPS_PER_ADVANCE``
        steps, or emit more than ``MAX_RECORDS_PER_ADVANCE`` records, is refused before any state changes.
        """
        self._check_open()
        t = as_int(t_ms, "t_ms", MonitorInputError)
        if self._last_advance is not None and t < self._last_advance:
            raise MonitorInputError(
                f"advance time went backwards: {t} after {self._last_advance}"
            )
        k_new = (t - self._delay) // self._step
        steps = k_new - self._k_f
        if steps > MAX_STEPS_PER_ADVANCE:
            raise MonitorInputError(
                f"advance would finalise {steps} steps, more than {MAX_STEPS_PER_ADVANCE}"
            )
        waiting = len(self._active) + sum(len(v) for v in self._scheduled.values())
        if steps > 0 and steps * waiting > MAX_RECORDS_PER_ADVANCE:
            raise MonitorInputError(
                f"advance would emit up to {steps * waiting} records, more than {MAX_RECORDS_PER_ADVANCE}"
            )
        self._last_advance = t
        out: list[VerdictRecord] = []
        for k in range(self._k_f + 1, k_new + 1):
            self._finalise(k, out)
        self._k_f = max(self._k_f, k_new)
        return tuple(out)

    @converting(MonitorInputError)
    def verdict_latency_bound_ms(self, template: TemplateId) -> DurationMs:
        """``max_latency_<id> + reorder_delay_ms`` (docs/formal/05 section 7.2), without the compute time."""
        if not isinstance(template, TemplateId):
            raise MonitorInputError(f"expected a TemplateId, got {show(template)}")
        try:
            return self._latency[template]
        except KeyError:
            raise MonitorInputError(
                f"template {template.value!r} does not run in this monitor"
            ) from None

    # -- reports ------------------------------------------------------------------------------------

    def late_inputs(self) -> tuple[RejectedInput, ...]:
        """The inputs excluded as late, with their receive times (the last ``REPORT_CAPACITY``)."""
        return tuple(r for r in self._rejected if r.reason == "late")

    def rejected_inputs(self) -> tuple[RejectedInput, ...]:
        """Every input that was not used, with its reason (the last ``REPORT_CAPACITY``)."""
        return tuple(self._rejected)

    def stats(self) -> MonitorStats:
        return MonitorStats(
            dedup_evicted_count=self._dedup_evicted,
            ignored_samples=self._ignored_samples,
            anchors_without_plan=self._unplanned,
            presence_level_older_than_window_steps=self._stale_presence,
            node_updates=self._nodes,
            retained_samples=len(self._buffer) + len(self._dispense_steps),
            retained_dedup_keys=len(self._seen),
            buffered_inputs=len(self._buffer),
            active_instances=len(self._active),
            steps_finalised=self._k_f + 1,
            records_emitted=self._records,
            accepted_count=self._accepted,
            released_count=self._released,
            late_count=self._late,
            future_stamped_count=self._future,
            duplicate_count=self._dup,
            overflow_count=self._overflow,
            after_finalisation_count=self._after,
            ignored_events=self._ignored,
            out_of_domain_samples=self._out_of_domain,
            rho_unavailable=self._ctx.rho_unavailable,
            future_stamp_check=self._skew is not None,
        )

    def close(self) -> None:
        """End of the run: every later call except the reports and ``stats`` is refused."""
        self._closed = True

    # -- input handling -----------------------------------------------------------------------------

    def _check_open(self) -> None:
        if self._closed:
            raise MonitorInputError("the monitor is closed")

    @staticmethod
    def _signal_of(value: object) -> SignalId:
        if isinstance(value, SignalId):
            return value
        if not isinstance(value, str):
            raise MonitorInputError(
                f"signal must be a SignalId value, got {show(value)}"
            )
        try:
            return SignalId(value)
        except ValueError:
            raise MonitorInputError(f"unknown signal {show(value)}") from None

    @staticmethod
    def _seq_of_input(seq: object) -> int | None:
        if seq is None:
            return None
        return as_int(seq, "seq", MonitorInputError, low=-MAX_SEQ, high=MAX_SEQ)

    def _reject(self, item: object, t_rx: int, reason: str, mark: int | None) -> None:
        self._rejected.append(RejectedInput(item, t_rx, reason, mark))

    def _ingest(
        self,
        kind: str,
        item: object,
        t_dev: int,
        t_rx: int,
        seq: int | None,
        dedup_key: tuple[object, ...] | None,
        data: object,
    ) -> None:
        mark = watermark_ms(t_dev, self._step, self._delay)
        if self._skew is not None and t_dev > t_rx + self._skew:
            self._future += 1
            self._reject(item, t_rx, "future_stamp", mark)
            return
        if is_late(t_dev, t_rx, self._step, self._delay):
            self._late += 1
            self._reject(item, t_rx, "late", mark)
            return
        if step_of(t_dev, self._step) <= self._k_f:
            self._after += 1
            self._reject(item, t_rx, "finalised", mark)
            return
        if seq is not None and dedup_key is not None and dedup_key in self._seen:
            self._dup += 1
            self._reject(item, t_rx, "duplicate", mark)
            return
        order = (
            _EVENT_ORDER.get(data[0], 0)
            if kind == "event" and isinstance(data, tuple)
            else 0
        )
        if not self._buffer.push(
            BufferedInput(t_dev, t_rx, kind, item, seq, data, order)
        ):
            self._overflow += 1
            self._reject(item, t_rx, "capacity", mark)
            return
        self._accepted += 1
        if seq is not None and dedup_key is not None:
            self._seen[dedup_key] = t_dev
            self._seen_order.append((t_dev, dedup_key))
            if len(self._seen_order) > DEDUP_CAPACITY:
                _t, oldest = self._seen_order.popleft()
                self._seen.pop(oldest, None)
                self._dedup_evicted += 1

    # -- the plan -------------------------------------------------------------------------------------

    def _build(self, read: _PlanRead) -> _Built:
        """Check the plan against this monitor; no state is touched."""
        seen_keys: set[str] = set()
        for item in read.instances:
            if item.instance_key in seen_keys:
                raise PlanFeasibilityError(
                    f"instance_key {item.instance_key!r} appears twice in the plan"
                )
            seen_keys.add(item.instance_key)
        records: dict[TemplateId, dict[str, float]] = {}
        anchored: list[TemplateInstance] = []
        for item in read.instances:
            tid = item.template
            if tid not in self._templates:
                continue  # this monitor does not run the template (template_ids)
            where = f"instance {item.instance_key!r}"
            if item.anchor_ms is not None:
                anchored.append(item)
                continue
            if tid in records:
                raise PlanFeasibilityError(
                    f"template {tid.value} has more than one parameter record (anchor_ms None) in the plan"
                )
            records[tid] = layer_values(
                self._templates[tid],
                self._defaults[tid],
                self._overrides,
                item.param_values,
                where,
            )
        params_of = {
            tid: {**self._defaults[tid], **records.get(tid, {})}
            for tid in self._templates
        }
        for tid, params in params_of.items():
            check_alignment(params, self._step, f"plan values of template {tid.value}")
        statics: list[_Static] = []
        for item in anchored:
            tid, anchor = item.template, item.anchor_ms
            where = f"instance {item.instance_key!r}"
            assert anchor is not None
            if tid is TemplateId.COUNT:
                if anchor < T_DAY_MS or anchor % T_DAY_MS != 0:
                    raise PlanFeasibilityError(
                        f"{where}: a COUNT instance with an anchor is the day-end obligation; its anchor "
                        f"{anchor} must be a closing step of a day (a positive multiple of {T_DAY_MS} ms)"
                    )
            elif tid is not TemplateId.SCHED:
                raise PlanFeasibilityError(
                    f"{where}: template {tid.value} is instantiated at its anchoring event, not by the "
                    "plan; give anchor_ms None to set its parameter values"
                )
            own = layer_values(
                self._templates[tid],
                self._defaults[tid],
                self._overrides,
                item.param_values,
                where,
            )
            params = {**params_of[tid], **own}
            check_alignment(params, self._step, where)
            statics.append(_Static(anchor, item.instance_key, tid, params))
        return _Built(params_of, statics)

    def _commit(self, read: _PlanRead, built: _Built) -> None:
        """Create the static instances of the plan and keep the plan; all or nothing."""
        ticks = sorted(
            (st.anchor, i)
            for i, st in enumerate(built.statics)
            if st.template is TemplateId.SCHED
        )
        next_anchor: dict[int, int] = {
            i: ticks[n + 1][0] for n, (_a, i) in enumerate(ticks[:-1])
        }
        started = set() if read.care_plan_id != self._plan_id else set(self._started)
        planned: list[tuple[int, Instance]] = []
        seq = self._seq
        for index, static in enumerate(built.statics):
            if static.key in started:
                continue  # already running or finished: a new version does not restart it
            template = self._templates[static.template]
            k_a = step_of(static.anchor, self._step)
            if k_a <= self._k_f:
                raise PlanFeasibilityError(
                    f"instance {static.key!r}: its step {k_a} has been finalised (steps up to {self._k_f}); "
                    "a plan cannot add an instance anchored in the finalised past"
                )
            seq += 1
            if static.template is TemplateId.SCHED:
                close = ((max(k_a, 1) - 1) // self._k_day + 1) * self._k_day
                nxt = next_anchor.get(index)
                horizon = close if nxt is None else min(step_of(nxt, self._step), close)
                planned.append(
                    (
                        k_a,
                        SchedInstance(
                            self._ctx,
                            template,
                            static.key,
                            seq,
                            static.anchor,
                            k_a,
                            static.params,
                            horizon,
                        ),
                    )
                )
            else:
                day_start = k_a - self._k_day
                start = max(day_start, self._k_f + 1)
                # loaded mid-day: the dispenses seen since the start of the day count
                count = (
                    sum(1 for s in self._dispense_steps if s > day_start)
                    if start > day_start
                    else 0
                )
                planned.append(
                    (
                        start,
                        CountEndInstance(
                            self._ctx,
                            template,
                            static.key,
                            seq,
                            static.anchor,
                            k_a,
                            static.params,
                            day_start,
                            count,
                        ),
                    )
                )
        self._seq = seq
        if read.care_plan_id != self._plan_id:
            self._started = set()
        self._plan_id = read.care_plan_id
        self._plan_versions[read.care_plan_id] = read.plan_version
        self._static_keys = {static.key for static in built.statics}
        self._scheduled = {}
        for step, instance in planned:
            self._scheduled.setdefault(step, []).append(instance)
        self._dyn_params = {tid: dict(p) for tid, p in built.params.items()}
        self._int_window_steps = self._int_window_in_steps()
        self._plan_loaded = True

    def _int_window_in_steps(self) -> int | None:
        """``int_window`` in steps for the diagnostic of a stale presence level; None without INT."""
        params = self._dyn_params.get(TemplateId.INT)
        if params is None or "int_window" not in params:
            return None
        return int(params["int_window"]) // self._step

    # -- the loop ---------------------------------------------------------------------------------------

    def _finalise(self, k: int, out: list[VerdictRecord]) -> None:
        step = self._step
        t_k = k * step
        self._nodes += 1  # the summaries of the step
        # the instances of the plan that start at this step exist before the step's inputs are applied, so
        # that a day-end COUNT counts the dispense of its first step after a mid-day load
        for instance in self._scheduled.pop(k, ()):
            bisect.insort(self._active, instance, key=_seq_of)
            self._active_keys.add(instance.key)
            self._started.add(instance.key)
            if isinstance(instance, CountEndInstance):
                self._dayend_active.append(instance)
        for entry in self._buffer.release(t_k):
            self._apply(entry, k)
            self._released += 1
            self._nodes += 1
        clock = Sample(_CLOCK_SIGNAL.value, t_k, t_k, 0.0, None, None)
        for derived in self._derived:
            produced = derived.update(clock)
            if produced is not None:
                self._derived_last[produced.signal] = produced.value
        limit = k - self._k_day
        while self._dispense_steps and self._dispense_steps[0] <= limit:
            self._dispense_steps.popleft()
        horizon = t_k - T_DAY_MS
        while self._seen_order and self._seen_order[0][0] <= horizon:
            _t, key = self._seen_order.popleft()
            self._seen.pop(key, None)
        view = self._view
        view.k = k
        view.bp = self._bp
        view.cuff_health = self._ch
        view.inflation = self._infl
        view.meas_now = self._meas_n > 0
        view.last_meas_step = self._last_meas_step
        view.dose_count = self._derived_last.get(SignalId.DOSE_COUNT.value, 0.0)
        self._witness.update(
            k,
            self._presence_off,
            self._presence,
            self._intake_off,
            self._intake_n > 0,
            self._auth_n > 0,
        )
        # the level of presence belongs to one co-location episode (ADR-054): a step at which the channel
        # is unavailable clears it, so that the next available step reads "undefined until a new sample"
        if self._presence_off:
            self._presence = _NAN
        elif (
            self._presence == 1.0
            and self._int_window_steps is not None
            and k - self._presence_step > self._int_window_steps
        ):
            self._stale_presence += (
                1  # a level older than the window still in force (ADR-054)
            )
        survivors: list[Instance] = []
        for instance in self._active:
            out.append(instance.step(k, view))
            self._nodes += 1
            if instance.finished(k):
                self._active_keys.discard(instance.key)
                if isinstance(instance, CountEndInstance):
                    self._dayend_active.remove(instance)
            else:
                survivors.append(instance)
        self._records += len(self._active)
        self._active = survivors
        self._meas_n = 0
        self._intake_n = 0
        self._auth_n = 0

    def _apply(self, entry: BufferedInput, k: int) -> None:
        kind = entry.kind
        data: Any = entry.data
        if kind == "avail":
            channel, available = data
            if channel is SignalId.PRESENCE:
                self._presence_off = not available
            else:
                self._intake_off = not available
            return
        if kind == "sample":
            signal, value = data
            sample = Sample(
                signal.value, entry.t_device_ms, entry.t_rx_ms, value, entry.seq, None
            )
            self._feed(sample)
            if signal is SignalId.BP:
                self._bp = value
                if not self._bound_lower <= value <= self._bound_upper:
                    self._out_of_domain += 1
            elif signal is SignalId.CUFF_HEALTH:
                self._ch = value
            elif signal is SignalId.INFLATION_MS:
                self._infl = value
            elif signal is SignalId.PRESENCE:
                self._presence = value
                self._presence_step = k
            elif signal is SignalId.AUTH:
                self._auth_n += 1
            return
        (event_kind,) = data
        event = entry.item
        assert isinstance(event, Event)
        sample_of = event_to_sample(event)
        pre = _NAN
        if sample_of is not None:
            produced = self._feed(sample_of)
            if event_kind is EventKind.DISPENSE:
                pre = produced.get(SignalId.BP_PRE.value, _NAN)
        if event_kind is EventKind.MEASUREMENT:
            self._meas_n += 1
            self._last_meas_step = k
            self._spawn(_MEASUREMENT_TEMPLATES, entry.t_device_ms, k, pre)
        elif event_kind is EventKind.DISPENSE:
            self._dispense_steps.append(k)
            for dayend in self._dayend_active:
                if k > dayend.act:
                    dayend.count += 1
            self._spawn(_DISPENSE_TEMPLATES, entry.t_device_ms, k, pre)
        elif event_kind is EventKind.INTAKE:
            self._intake_n += 1

    def _feed(self, sample: Sample) -> dict[str, float]:
        """Give a released sample to every derived signal; return what this sample produced."""
        produced: dict[str, float] = {}
        for derived in self._derived:
            out = derived.update(sample)
            if out is not None:
                self._derived_last[out.signal] = out.value
                produced[out.signal] = out.value
        return produced

    def _spawn(
        self, tids: Sequence[TemplateId], anchor_ms: int, k: int, pre: float
    ) -> None:
        if not self._plan_loaded:
            self._unplanned += (
                1  # an anchor without a plan: no instance, and the count says so
            )
            return
        for tid in tids:
            template = self._templates.get(tid)
            if template is None:
                continue
            base = f"{tid.value}@{anchor_ms}"
            key, n = base, 1
            while key in self._active_keys or key in self._static_keys:
                n += 1
                key = f"{base}#{n}"
            self._seq += 1
            params = self._dyn_params[tid]
            ctx = self._ctx
            instance: Instance
            if tid is TemplateId.RANGE:
                instance = RangeInstance(
                    ctx, template, key, self._seq, anchor_ms, k, params
                )
            elif tid is TemplateId.SYS:
                instance = SysInstance(
                    ctx, template, key, self._seq, anchor_ms, k, params
                )
            elif tid is TemplateId.HOLD:
                instance = HoldInstance(
                    ctx, template, key, self._seq, anchor_ms, k, params
                )
            elif tid is TemplateId.COUNT:
                instance = CountLimitInstance(
                    ctx, template, key, self._seq, anchor_ms, k, params
                )
            elif tid is TemplateId.RESP:
                instance = RespInstance(
                    ctx, template, key, self._seq, anchor_ms, k, params, pre
                )
            else:
                instance = IntInstance(
                    ctx, template, key, self._seq, anchor_ms, k, params
                )
            bisect.insort(self._active, instance, key=_seq_of)
            self._active_keys.add(key)


# ---------------------------------------------------------------------------------------------------
# reading and checking a plan
# ---------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _PlanRead:
    care_plan_id: str
    plan_version: int
    instances: tuple[TemplateInstance, ...]


@dataclass(frozen=True, slots=True)
class _Static:
    anchor: int
    key: str
    template: TemplateId
    params: dict[str, float]


@dataclass(frozen=True, slots=True)
class _Built:
    params: dict[TemplateId, dict[str, float]]
    statics: list[_Static]


def _text(value: object, what: str) -> str:
    if not isinstance(value, str):
        raise PlanIntegrityError(f"{what} must be a str, got {show(value)}")
    return value[:]


def _read_plan(plan: object) -> _PlanRead:
    """The structure of a plan; anything that cannot be read raises ``PlanIntegrityError``."""
    if not isinstance(plan, CarePlan):
        raise PlanIntegrityError(f"expected a CarePlan, got {show(plan)}")
    care_plan_id = _text(plan.care_plan_id, "care_plan_id")
    if not care_plan_id:
        raise PlanIntegrityError("care_plan_id must not be empty")
    for name in ("pathway_template_id", "patient_id", "registry_version"):
        _text(getattr(plan, name), name)
    version = as_int(
        plan.plan_version, "plan_version", PlanIntegrityError, low=0, high=MAX_SEQ
    )
    if not isinstance(plan.schedule, (list, tuple)):
        raise PlanIntegrityError(
            f"schedule must be a list or a tuple, got {show(plan.schedule)}"
        )
    for i, tick in enumerate(plan.schedule):
        as_int(tick, f"schedule[{i}]", PlanIntegrityError)
    if plan.signature is not None and not isinstance(plan.signature, str):
        raise PlanIntegrityError(
            f"signature must be a str or None, got {show(plan.signature)}"
        )
    if not isinstance(plan.instances, (list, tuple)):
        raise PlanIntegrityError(
            f"instances must be a list or a tuple, got {show(plan.instances)}"
        )
    out: list[TemplateInstance] = []
    for i, item in enumerate(plan.instances):
        where = f"instances[{i}]"
        if not isinstance(item, TemplateInstance):
            raise PlanIntegrityError(
                f"{where} must be a TemplateInstance, got {show(item)}"
            )
        if not isinstance(item.template, TemplateId):
            raise PlanIntegrityError(
                f"{where}.template must be a TemplateId, got {show(item.template)}"
            )
        key = _text(item.instance_key, f"{where}.instance_key")
        if not key:
            raise PlanIntegrityError(f"{where}.instance_key must not be empty")
        anchor = item.anchor_ms
        if anchor is not None:
            anchor = as_int(anchor, f"{where}.anchor_ms", PlanIntegrityError)
        if not isinstance(item.param_values, Mapping):
            raise PlanIntegrityError(
                f"{where}.param_values must be a mapping, got {show(item.param_values)}"
            )
        values = {}
        for name, value in item.param_values.items():
            values[_text(name, f"{where}.param_values key")] = as_number(
                value, f"{where}.param_values[{name!r}]", PlanIntegrityError
            )
        out.append(TemplateInstance(item.template, key, values, anchor))
    return _PlanRead(care_plan_id, version, tuple(out))
