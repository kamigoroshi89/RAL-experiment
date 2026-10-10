"""B3: the pathway templates evaluated on the measured values, with raw robustness and no uncertainty (WS06-T04).

What B3 is. The same seven templates as the proposed method, with the parameters that the proposed method reads
(the registry and the parameter records of the patient care plan), instantiated as the monitor instantiates them
(RANGE and SYS at a MEASUREMENT event; HOLD, COUNT, RESP and INT at a DISPENSE event; SCHED and the day-end COUNT
from the plan) and evaluated by the same STL evaluator, the point evaluator of ``ralmon.monitor`` (ADR-013 outcome C:
RTAMT 0.4.10 does not run on the repository Python and translates only part of the templates, so B3 is the plain
Boolean and STL reading of the templates without margin scaling, not an RTAMT run). The values the evaluator sees are
the measured ones, built by the signal construction of ``ralmon.baselines.raw_robustness`` (held signals, one-step
impulses, the derived signals, the robot channels of ADR-054 (b)): nothing is forecast and nothing is calibrated.
The raw robustness is in the native unit of each template (mmHg, ms or dose). An instance whose raw robustness is
strictly negative is a violation (``VIOLATED iff hi < 0``, ``#verdict``); B3 emits one ``Detection`` on the rising
edge of that condition, with ``score`` equal to minus the raw robustness at the edge (the largest finite number when
it is minus infinity, a failed Boolean guard) and ``t_ms`` equal to the time at which the step is final
(``t_eval + D``, the reorder delay ``D`` of the timing). It isolates what conformal prediction and the clinical
normalisation add to the specification (analisi section 5.4, row B3).

What B3 is not. It has no normalisation by a clinical scale, no priority ranking, no robustness interval, no
verdict states (nothing is PENDING or PREDICTED-VIOLATION: an instance without a value yet is silent), no forecaster,
no conformal calibrator and no uncertainty of any kind. It makes no attribution (``Detection.label`` is ``None``,
the evidence is dropped at the harness). Its scores are in different units for different templates, so a score is
comparable only within a template; detections of one step are kept in the order of their ``instance_key`` and are
never ordered across units. It is fitted on nothing: ``fit`` reads no day.

Handicaps, stated because B3 is a fair competitor. (a) The ones above, which are what the baseline is. (b) Apart from the
differences listed next, nothing: all seven templates are evaluated, the threshold direction is that of the templates, the registry and the plan
are read through the same logged wrappers as for every baseline, the lateness rule of the monitor is applied (an
input that arrives after its step is final is dropped), and the availability of the robot channels is read from the
``NODE_STATE colocated`` reports as the monitor reads it.

Known differences from the monitor, which the audit lists. (1) The harness does not deduplicate inputs by
``(source, name, seq)``: an event delivered twice on time creates a second instance and counts twice (a dispense
delivered twice is two doses in ``dose_count``), so B3 can report violations of the daily limit that the monitor does
not (asymmetry (b) of ``base.py``; pinned by ``test_b3_does_not_deduplicate_inputs_and_double_counts_doses``). Inputs
that arrive after their step is final are dropped as in the monitor. (2) The point evaluator gives a value only when
the interval of an instance is a point, while the monitor decides VIOLATED from the sign of the upper bound: B3 is
silent on INT and SYS violations whose history holds an undefined or unavailable step (ADR-063, proposed, open
decision for gab). (3) The detectors are run one day at a time with empty carry-over state (ADR-061, proposed): a
counter over 24 h can lack the doses of the day before, for B3 as for the proposed method. (4) B3 runs on after the
end of the day for the tail of the timing, so an instance whose deadline passes after midnight (RESP of a late dose)
can be detected at a step of the next day, where the per-day monitor ends PENDING (open decision for gab, Notes of
WS06-T04).

The INT gate. The held level of ``presence`` is a hazard when the trace carries no availability mark (ADR-054): the
level of the last robot visit then witnesses every later dispense. ``run_stats`` of the last run reports
``presence_samples_without_availability_marks`` with the definition of ``MonitorStats`` and ``int_gate_passed`` is
true only if it is 0. A detection of an INT instance, and an absence of one, is evidence only when the gate passed;
a caller that reports INT-based results must report the gate (the INT-based results of WS08 are conditional on it).

Hyperparameter selection. B3 has no operating parameter: its recall against false alarms is one operating point,
fixed by the templates and the registry. Nothing is tuned on any day.

Numbers. No clinical constant appears here; every value comes from the registry and the care plan through the
point evaluator, and the reads are logged.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from ralmon.attribution import Detection
from ralmon.baselines.access import AccessLog, AccessPolicy, GuardedDay, ReadLog
from ralmon.baselines.base import BaselineBase, TimingConfig
from ralmon.baselines.raw_robustness import (
    GridStep,
    LoggingRegistry,
    RawRobustnessEvaluator,
    RunStats,
    SignalGrid,
    make_evaluator,
)
from ralmon.benchmark import ObservedDay
from ralmon.monitor import PlanFeasibilityError
from ralmon.signals import MS_PER_HOUR
from ralmon.spec import CarePlan, Template, TemplateId, TemplateInstance

__all__ = ["B3PlainSTL", "B3RunStats"]

EvaluatorFactory = Callable[[Template, Any, int, str | None], RawRobustnessEvaluator]

_T_DAY_MS: Final = 24 * MS_PER_HOUR
# the score of a detection whose raw robustness is minus infinity (a failed Boolean guard): the largest finite
# number, because the harness refuses an infinite score (the rule of B5)
_LARGEST_SCORE: Final = sys.float_info.max

# the templates created by the anchoring events, as the monitor creates them
_MEASUREMENT_TEMPLATES: Final = (TemplateId.RANGE, TemplateId.SYS)
_DISPENSE_TEMPLATES: Final = (
    TemplateId.HOLD,
    TemplateId.COUNT,
    TemplateId.RESP,
    TemplateId.INT,
)
_ANCHOR_KIND: Final[dict[TemplateId, str]] = {
    TemplateId.RANGE: "measurement",
    TemplateId.SYS: "measurement",
    TemplateId.HOLD: "dispense",
    TemplateId.COUNT: "dispense",
    TemplateId.RESP: "dispense",
    TemplateId.INT: "dispense",
}


B3RunStats = RunStats  # the counters of a run; the same type as for B5


class _Tracker:
    """One instance followed through the day."""

    __slots__ = ("evaluator", "flag", "key", "value")

    def __init__(self, key: str, evaluator: RawRobustnessEvaluator) -> None:
        self.key = key
        self.evaluator = evaluator
        self.value: float | None = None
        self.flag = False


@dataclass(slots=True)
class _DayState:
    t0: int
    records: dict[TemplateId, Mapping[str, float]]
    statics: list[tuple[Template, TemplateInstance, str]]
    rows: list[dict[str, float | None]] = field(default_factory=list)
    live: list[_Tracker] = field(default_factory=list)
    keys: set[str] = field(default_factory=set)
    detections: list[Detection] = field(default_factory=list)


def _score(value: float) -> float:
    """A finite detection score from a negative raw robustness."""
    return min(-value, _LARGEST_SCORE)


def _fresh_key(base: str, taken: set[str]) -> str:
    key, n = base, 1
    while key in taken:
        n += 1
        key = f"{base}#{n}"
    return key


class B3PlainSTL(BaselineBase):
    """Baseline B3; see the module docstring for what it is, what it leaves out and the INT gate.

    Parameters: ``templates`` (the library of ``load_templates``, or a subset), ``registry`` (wrapped so that every
    read is logged), ``timing`` and an optional ``evaluator_factory(template, registry, step_ms, anchor_kind)``
    (default ``make_evaluator``; tests inject a scripted evaluator). There is no forecaster, no calibrator and no
    operating parameter. B3 is not a conformal method and has no normalisation, no ranking, no robustness interval,
    no verdict state and no uncertainty.

    Hyperparameter selection. None: B3 has no operating parameter, so its detections are one operating point and
    nothing is tuned on any day.
    """

    name = "B3"

    def __init__(
        self,
        templates: Sequence[Template],
        registry: Any,
        *,
        timing: TimingConfig,
        evaluator_factory: EvaluatorFactory | None = None,
        access_policy: AccessPolicy | None = None,
        access_log: AccessLog | None = None,
        read_log: ReadLog | None = None,
    ) -> None:
        super().__init__(
            timing,
            access_policy=access_policy,
            access_log=access_log,
            read_log=read_log,
        )
        by_id: dict[TemplateId, Template] = {}
        for template in templates:
            if template.id in by_id:
                raise ValueError(f"template {template.id.value} is given twice")
            by_id[template.id] = template
        if not by_id:
            raise ValueError("B3 needs at least one template")
        if _T_DAY_MS % timing.step_ms != 0:
            raise ValueError(f"step_ms {timing.step_ms} must divide the day")
        self._templates = by_id
        self._registry = LoggingRegistry(registry, self.read_log)
        self._evaluator_factory: EvaluatorFactory = (
            make_evaluator if evaluator_factory is None else evaluator_factory
        )
        self._run_stats: B3RunStats | None = None

    # -- what the last run counted ------------------------------------------------------------------------

    @property
    def run_stats(self) -> B3RunStats | None:
        """The counters of the last ``run``; ``None`` before the first one."""
        return self._run_stats

    @property
    def int_gate_passed(self) -> bool:
        """Whether the last run passed the INT gate of ADR-054 (no presence sample used without a mark)."""
        stats = self._run_stats
        return (
            stats is not None and stats.presence_samples_without_availability_marks == 0
        )

    # -- fit and run --------------------------------------------------------------------------------------

    def _fit(self, train: Sequence[GuardedDay], calib: Sequence[GuardedDay]) -> None:
        """Nothing to fit, and no day is read."""
        self._run_stats = None

    def _run(self, day: ObservedDay, plan: CarePlan) -> Sequence[Detection]:
        step = self._timing.step_ms
        t0 = day.day_index * _T_DAY_MS
        records, statics = self._read_plan(plan, t0)
        grid = SignalGrid(step, delay_ms=self._timing.reorder_delay_ms, origin_ms=t0)
        state = _DayState(t0, records, statics)
        for batch in self._steps(day, plan):
            for grid_step in grid.apply(batch):
                self._row(state, grid_step, batch.t_ms)
        self._run_stats = RunStats.of(grid, len(state.keys))
        return state.detections

    def _read_plan(
        self, plan: CarePlan, t0: int
    ) -> tuple[
        dict[TemplateId, Mapping[str, float]],
        list[tuple[Template, TemplateInstance, str]],
    ]:
        """The parameter records and the instances anchored by the plan, on the axis of the day.

        An instance anchored outside the day is not part of it (empty carry-over, ADR-061). A parameter record has
        ``anchor_ms`` None and is the ``param_values`` of the instances that the events create.
        """
        records: dict[TemplateId, Mapping[str, float]] = {}
        statics: list[tuple[Template, TemplateInstance, str]] = []
        for inst in plan.instances:
            tid = inst.template
            anchor = inst.anchor_ms
            if tid is TemplateId.SCHED and anchor is not None:
                if tid in self._templates and t0 <= anchor < t0 + _T_DAY_MS:
                    local = TemplateInstance(
                        tid, inst.instance_key, inst.param_values, anchor - t0
                    )
                    statics.append((self._templates[tid], local, "sched_tick"))
                continue
            if tid not in self._templates:
                continue
            if anchor is None:
                if tid in records:
                    raise PlanFeasibilityError(
                        f"template {tid.value} has more than one parameter record (anchor_ms None) in the plan"
                    )
                records[tid] = inst.param_values
            elif tid is TemplateId.COUNT:
                if anchor < _T_DAY_MS or anchor % _T_DAY_MS != 0:
                    raise PlanFeasibilityError(
                        f"instance {inst.instance_key!r}: a COUNT instance with an anchor is the day-end "
                        f"obligation; its anchor {anchor} must be a closing step of a day"
                    )
                if anchor == t0 + _T_DAY_MS:
                    local = TemplateInstance(
                        tid, inst.instance_key, inst.param_values, _T_DAY_MS
                    )
                    statics.append((self._templates[tid], local, "day_end"))
            else:
                raise PlanFeasibilityError(
                    f"instance {inst.instance_key!r}: template {tid.value} is instantiated at its anchoring "
                    "event, not by the plan; give anchor_ms None to set its parameter values"
                )
        return records, statics

    def _row(self, state: _DayState, grid_step: GridStep, t_det: int) -> None:
        """One step of the device-time grid, final at the harness time ``t_det`` (the time of its detections)."""
        step = self._timing.step_ms
        k = grid_step.k
        state.rows.append(grid_step.values)
        stepped: list[_Tracker] = []
        for tracker in state.live:
            tracker.value = tracker.evaluator.step(k * step, grid_step.values)
            stepped.append(tracker)
        new: list[_Tracker] = []
        if k == 0:
            for static_template, static, static_kind in state.statics:
                new.append(self._make(static_template, static, static_kind, state))
        for anchors, kinds in (
            (grid_step.measurements, _MEASUREMENT_TEMPLATES),
            (grid_step.dispenses, _DISPENSE_TEMPLATES),
        ):
            for anchor in anchors:
                if anchor < 0:
                    continue  # stamped before the day: not part of it
                for tid in kinds:
                    template = self._templates.get(tid)
                    if template is None:
                        continue
                    key = _fresh_key(f"{tid.value}@{state.t0 + anchor}", state.keys)
                    instance = TemplateInstance(
                        tid, key, state.records.get(tid, {}), anchor
                    )
                    new.append(self._make(template, instance, _ANCHOR_KIND[tid], state))
        for tracker in new:
            for kk in range(k + 1):  # the evaluator needs consecutive steps from step 0
                tracker.value = tracker.evaluator.step(kk * step, state.rows[kk])
            stepped.append(tracker)
        state.live.extend(new)
        for tracker in sorted(stepped, key=lambda t: t.key):
            value = tracker.value
            violated = value is not None and value < 0
            if violated and not tracker.flag:
                assert value is not None
                state.detections.append(Detection(t_det, None, _score(value)))
            tracker.flag = violated
        # an evaluator that says it is done (the point evaluator, once an instance other than SCHED has a value) is
        # not stepped again: its value is final
        state.live = [t for t in state.live if not getattr(t.evaluator, "done", False)]

    def _make(
        self,
        template: Template,
        instance: TemplateInstance,
        kind: str,
        state: _DayState,
    ) -> _Tracker:
        evaluator = self._evaluator_factory(
            template, self._registry, self._timing.step_ms, kind
        )
        evaluator.reset(instance)
        state.keys.add(instance.instance_key)
        return _Tracker(instance.instance_key, evaluator)
