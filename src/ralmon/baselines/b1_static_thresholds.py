"""B1: static thresholds on the values of the care plan, plus simple schedule logic (WS06-T02; analisi section 5.4, row B1).

What B1 is. One alarm for every delivered value that breaks a fixed threshold of the patient care plan, and one for every
scheduled measurement that did not happen in its window. It has the clinical knowledge of the proposed method for four of
the seven templates (the bands, the hold threshold, the schedule window and the dose limit; analisi section 10
objection 1) and none of its machinery: no temporal formula, no robustness, no interval, no uncertainty, no forecast and
no attribution. It measures the value of temporal structure, windows and attribution at equal clinical knowledge.

Registry entries that play the five roles (``ROLE_PARAMETERS``; the numbers are in ``configs/registry/hypertension.yaml``
and never in this file):

* band low: ``bp_band_low`` and band high: ``bp_band_high`` (template RANGE);
* hold threshold: ``bp_hold_threshold`` (template HOLD);
* schedule window: ``sched_window`` (template SCHED);
* dose limit: ``dose_max_24h`` (template COUNT).

Where the values come from. A rule is active only if the patient care plan holds the matching instance, and the value is
read from ``TemplateInstance.param_values`` of that instance through the logged plan; a name that the instance leaves out
is read from the registry (when one is given), as the monitor does for an omitted name (ADR-047 (g)); a name that neither
gives is a ``PlanFeasibilityError`` that names it (a rule is never switched off silently). RANGE, HOLD and COUNT are read
from the parameter record of the plan (the instance of the template with ``anchor_ms`` None, at most one per template); a
SCHED instance is one scheduled measurement, anchored at its tick. The registry (if any) is wrapped in an
``AuditedRegistry``, so that the audit sees every name B1 asked for.

Rules, each at the delivery step of its input (``Detection.t_ms`` is the grid time, which already includes the reorder
delay):

* R1 band: one detection per delivered pressure sample outside the closed band.
* R2 hold: one detection per delivered DISPENSE event when the last delivered pressure is below the hold threshold
  (no look-back window; before the first pressure there is no detection).
* R3 scheduled measurement: for each anchored SCHED instance, at the first step with ``t - D >= anchor + window``, one
  detection if no pressure sample and no MEASUREMENT event with a device time in ``[anchor, anchor + window]`` was
  delivered. The inputs of a step are delivered before the deadlines of that step are evaluated. B1 extends the run to its
  own last deadline, so that its result does not depend on the ``tail_ms`` of the timing or on ``plan.schedule``.
* R4 dose limit: one detection per delivered DISPENSE event that makes the number of delivered doses with a device time in
  ``(t - 24 h, t]`` exceed the limit (B1 keeps the count itself).

Every detection has ``label`` None and ``score`` 1.0: B1 is binary, one operating point. Detections of different rules at
one step are separate items (a ``Detection`` has no template field).

What B1 sees and does not see. It sees pressure samples and MEASUREMENT and DISPENSE events, delivered by the shared causal
step iterator, the four parameters above and the anchors of the SCHED instances. It does not see, by design (analisi
section 5.4): RESP (the response to a dose), SYS (cuff health and inflation time) and INT (presence, intake and
authentication of a dispense), the robot channels, the evidence, scale, priority, normalisation, intervals, verdict
states, a forecaster or a conformal calibrator. Two threshold-type conditions of the templates are also outside what the
task prescribes, and the monitor reports both (pinned by ``test_b1_blind_spots_against_the_monitor_are_pinned``): the HOLD
template needs a measurement in its look-back window before the dispense, and B1 has no look-back window, so a dispense
long after the last in-range pressure is silent; the COUNT template has a day-end obligation (a minimum number of doses),
and B1 knows only the upper limit, so a missed dose is silent. Whether B1 should have them is a decision for the project
owner (Notes of WS06-T02). A violation that the monitor reports on a RESP, SYS or INT instance cannot be seen by B1 (pinned by
``test_b1_cannot_see_response_cuff_and_integrity_violations``): the comparison with the proposed method on the system
class (C2) and on the integrity class (C3) is therefore not a comparison of equals. A pressure outside the physiological
bounds of the registry is an ordinary out-of-band value to B1 (it does not read the bounds).

Known differences from the monitor, which the audit lists. (1) The lateness rule of the grid of B3 and B5 is applied: an
input received after its step is final is dropped and counted. (2) The harness does not deduplicate inputs by
``(source, name, seq)``: a pressure delivered twice raises two alarms and a dose delivered twice counts twice (pinned by
``test_b1_does_not_deduplicate_inputs``). (3) An input stamped before the start of its day raises no alarm (it is not part of
the day, ADR-061) but is a delivered value: it can be the last pressure of R2 and a dose of R4. (4) The detectors are run
one day at a time with empty carry-over state (ADR-061): the count over 24 h can lack the doses of the day before. (5) B1 does
not check that a per-patient value lies in an approved range of the registry (the monitor rejects such a plan); it checks
that a value is a finite number, that the band is ordered and that the window is a non-negative multiple of the step.
(6) A deadline that passes after midnight (R3 of a late tick) is detected at a step of the next day, where the per-day monitor
ends PENDING (the open decision of WS06-T04 about the closing step applies to B1 as well). (7) A non-finite pressure is not a
reading: it is neither an alarm, nor the last pressure, nor a measurement for R3 (counted in ``run_stats``).

Hyperparameter selection. None. B1 has no operating parameter and nothing is fitted or tuned: its recall against false alarms
is a single operating point, fixed by the plan. Rules R2 and R4 are included on purpose (the same threshold-type knowledge as
the proposed method, stronger than the minimal B1 of the analysis, which has only the band and the schedule); the choice is
audited in WS06-T07.

Numbers. No clinical constant appears here; every value comes from the care plan or the registry and the reads are logged.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from ralmon.attribution import Detection
from ralmon.baselines.access import (
    AccessLog,
    AccessPolicy,
    AuditedRegistry,
    GuardedDay,
    ReadLog,
)
from ralmon.baselines.base import (
    BaselineBase,
    TimingConfig,
    evaluation_end_ms,
    iter_steps,
)
from ralmon.benchmark import ObservedDay
from ralmon.monitor import PlanFeasibilityError
from ralmon.signals import MS_PER_HOUR, Event, EventKind, Sample, SignalId
from ralmon.spec import CarePlan, RegistryError, TemplateId, TemplateInstance

__all__ = ["ROLE_PARAMETERS", "B1RunStats", "B1StaticThresholds"]

BAND_LOW: Final = "bp_band_low"
BAND_HIGH: Final = "bp_band_high"
HOLD_THRESHOLD: Final = "bp_hold_threshold"
SCHED_WINDOW: Final = "sched_window"
DOSE_LIMIT: Final = "dose_max_24h"

# the role of each registry entry that B1 reads (the keys are prose, not registry names)
ROLE_PARAMETERS: Final[Mapping[str, str]] = {
    "band low": BAND_LOW,
    "band high": BAND_HIGH,
    "hold threshold": HOLD_THRESHOLD,
    "schedule window": SCHED_WINDOW,
    "dose limit": DOSE_LIMIT,
}

_T_DAY_MS: Final = 24 * MS_PER_HOUR
_RULES: Final = ("R1", "R2", "R3", "R4")
_SCORE: Final = 1.0


@dataclass(frozen=True, slots=True)
class B1RunStats:
    """What the last ``run`` of B1 counted (no wall clock).

    ``rules_active`` lists the rules that the plan of the run switched on (a plan without the matching instances makes B1
    silent, so a caller can tell a quiet day from a vacuous baseline); ``late_inputs`` the relevant inputs dropped because
    they arrived after their step was final; ``non_finite_samples`` the pressure samples that were not numbers;
    ``schedule_checks`` the scheduled measurements that B1 checked on the day.
    """

    rules_active: tuple[str, ...]
    late_inputs: int
    non_finite_samples: int
    schedule_checks: int


@dataclass(frozen=True, slots=True)
class _Check:
    anchor: int
    deadline: int  # anchor + window


@dataclass(frozen=True, slots=True)
class _Rules:
    band: tuple[float, float] | None
    hold: float | None
    limit: float | None
    checks: tuple[_Check, ...]

    def active(self) -> tuple[str, ...]:
        flags = (
            self.band is not None,
            self.hold is not None,
            bool(self.checks),
            self.limit is not None,
        )
        return tuple(rule for rule, flag in zip(_RULES, flags, strict=True) if flag)


class B1StaticThresholds(BaselineBase):
    """Baseline B1; see the module docstring for the rules, what B1 sees and does not see, and the known differences.

    Parameters: ``timing`` (keyword-only, the shared time base) and an optional ``registry`` from which a name that the
    plan leaves out is read (through an ``AuditedRegistry`` on this baseline's read log). There is no forecaster, no
    calibrator and no operating parameter. B1 makes no attribution (every ``label`` is None) and ignores the evidence.

    Hyperparameter selection. None: B1 has no operating parameter and nothing is fitted or tuned, so its detections are one
    operating point. Rules R2 and R4 are included on purpose (the same threshold-type knowledge as the proposed method).
    """

    name = "B1"

    def __init__(
        self,
        *,
        timing: TimingConfig,
        registry: Any = None,
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
        self._registry = (
            None if registry is None else AuditedRegistry(registry, self.read_log)
        )
        self._run_stats: B1RunStats | None = None

    @property
    def run_stats(self) -> B1RunStats | None:
        """The counters of the last ``run``; ``None`` before the first one and after a ``fit``."""
        return self._run_stats

    # -- fit -----------------------------------------------------------------------------------------------------------

    def _fit(self, train: Sequence[GuardedDay], calib: Sequence[GuardedDay]) -> None:
        """Nothing to fit, and no day is read."""
        self._run_stats = None

    # -- the plan ------------------------------------------------------------------------------------------------------

    def _number(self, instance: TemplateInstance, name: str) -> float:
        """The value of ``name`` for ``instance``: its own, else the registry's, else an error that names it."""
        where = f"instance {instance.instance_key!r}"
        try:
            raw: Any = instance.param_values[name]
        except KeyError:
            raw = self._from_registry(name, where)
        try:
            value = float(raw)
        except (TypeError, ValueError):
            raise PlanFeasibilityError(
                f"{where}: {name} must be a number, got {raw!r}"
            ) from None
        if not math.isfinite(value):
            raise PlanFeasibilityError(
                f"{where}: {name} must be a finite number, got {raw!r}"
            )
        return value

    def _from_registry(self, name: str, where: str) -> Any:
        if self._registry is None:
            raise PlanFeasibilityError(
                f"{where}: the plan gives no value for {name} and B1 has no registry to read it from"
            )
        try:
            return self._registry.get(name).value
        except RegistryError as exc:
            raise PlanFeasibilityError(
                f"{where}: the plan gives no value for {name} and the registry cannot ({exc})"
            ) from exc

    def _record(self, plan: CarePlan, template: TemplateId) -> TemplateInstance | None:
        """The parameter record of ``template`` (anchor None); at most one."""
        found: TemplateInstance | None = None
        for instance in plan.instances:
            if instance.template is not template:
                continue
            if instance.anchor_ms is not None:
                if template is TemplateId.COUNT:
                    continue  # the day-end obligation, which B1 does not have
                raise PlanFeasibilityError(
                    f"instance {instance.instance_key!r}: template {template.value} is instantiated by B1 from its "
                    "parameter record; give anchor_ms None"
                )
            if found is not None:
                raise PlanFeasibilityError(
                    f"template {template.value} has more than one parameter record (anchor_ms None) in the plan"
                )
            found = instance
        return found

    def _read_plan(self, plan: CarePlan, t0: int) -> _Rules:
        step = self._timing.step_ms
        band: tuple[float, float] | None = None
        hold: float | None = None
        limit: float | None = None
        record = self._record(plan, TemplateId.RANGE)
        if record is not None:
            low, high = (
                self._number(record, BAND_LOW),
                self._number(record, BAND_HIGH),
            )
            if low > high:
                raise PlanFeasibilityError(
                    f"instance {record.instance_key!r}: the band is empty ({BAND_LOW} {low} above {BAND_HIGH} {high})"
                )
            band = (low, high)
        record = self._record(plan, TemplateId.HOLD)
        if record is not None:
            hold = self._number(record, HOLD_THRESHOLD)
        record = self._record(plan, TemplateId.COUNT)
        if record is not None:
            limit = self._number(record, DOSE_LIMIT)
        checks: list[_Check] = []
        for instance in plan.instances:
            anchor = instance.anchor_ms
            if instance.template is not TemplateId.SCHED or anchor is None:
                continue
            if not t0 <= anchor < t0 + _T_DAY_MS:
                continue  # an instance of another day (empty carry-over, ADR-061)
            window = self._number(instance, SCHED_WINDOW)
            if not (window >= 0.0 and window.is_integer() and int(window) % step == 0):
                raise PlanFeasibilityError(
                    f"instance {instance.instance_key!r}: window parameter {SCHED_WINDOW} = {window} is not a "
                    f"non-negative multiple of step_ms {step}"
                )
            checks.append(_Check(anchor, anchor + int(window)))
        checks.sort(key=lambda c: (c.deadline, c.anchor))
        return _Rules(band, hold, limit, tuple(checks))

    # -- run -----------------------------------------------------------------------------------------------------------

    def _run(self, day: ObservedDay, plan: CarePlan) -> Sequence[Detection]:
        timing = self._timing
        step, delay = timing.step_ms, timing.reorder_delay_ms
        t0 = day.day_index * _T_DAY_MS
        rules = self._read_plan(plan, t0)
        end = evaluation_end_ms(day, plan, timing.tail_ms)
        if rules.checks:
            end = max(end, max(c.deadline for c in rules.checks) + delay)
        out: list[Detection] = []
        measured: list[
            int
        ] = []  # device times of the delivered measurements (pressure samples, MEASUREMENT events)
        doses: list[int] = []  # device times of the delivered dispenses
        last_bp: float | None = None
        late = non_finite = 0
        pending = list(rules.checks)
        previous: int | None = None
        for batch in iter_steps(day, timing, end):
            # the steps of the device-time grid that were final at the previous batch (the lateness rule of the grid
            # of B3 and B5, which is that of the monitor when the delay is a multiple of the step)
            final = -1 if previous is None else (previous - t0 - delay) // step
            for item in batch.inputs():
                is_pressure = (
                    isinstance(item, Sample) and item.signal == SignalId.BP.value
                )
                is_event = isinstance(item, Event) and item.kind in (
                    EventKind.MEASUREMENT,
                    EventKind.DISPENSE,
                )
                if not (is_pressure or is_event):
                    continue
                device = item.t_device_ms
                if max(0, -(-(device - t0) // step)) <= final:
                    late += 1
                    continue
                in_day = device >= t0
                if isinstance(item, Sample):
                    value = item.value
                    if not math.isfinite(value):
                        non_finite += 1
                        continue
                    last_bp = value
                    measured.append(device)
                    if (
                        rules.band is not None
                        and in_day
                        and not rules.band[0] <= value <= rules.band[1]
                    ):
                        out.append(Detection(batch.t_ms, None, _SCORE))
                elif item.kind is EventKind.MEASUREMENT:
                    measured.append(device)
                else:  # DISPENSE
                    doses.append(device)
                    if (
                        rules.hold is not None
                        and in_day
                        and last_bp is not None
                        and last_bp < rules.hold
                    ):
                        out.append(Detection(batch.t_ms, None, _SCORE))
                    if rules.limit is not None and in_day:
                        count = sum(
                            1 for d in doses if device - _T_DAY_MS < d <= device
                        )
                        if count > rules.limit:
                            out.append(Detection(batch.t_ms, None, _SCORE))
            # deadlines are evaluated after the inputs of the step were delivered
            while pending and batch.t_ms - delay >= pending[0].deadline:
                check = pending.pop(0)
                if not any(check.anchor <= m <= check.deadline for m in measured):
                    out.append(Detection(batch.t_ms, None, _SCORE))
            previous = batch.t_ms
        self._run_stats = B1RunStats(
            rules.active(), late, non_finite, len(rules.checks)
        )
        return out
