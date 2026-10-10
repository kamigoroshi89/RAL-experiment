"""B5: conformal STL predictive monitoring after Lindemann et al., applied to the pathway templates (WS06-T06).

Source. L. Lindemann, X. Qin, J. V. Deshmukh and G. J. Pappas, "Conformal Prediction for STL Runtime Verification",
ICCPS 2023, author preprint arXiv:2211.01539v2 [ref-needed: the bibliography entry is not verified]. Every statement
about the method below carries a locator into that preprint (printed page numbers); the full record of what was
read, how it maps to the templates and every departure is ``docs/plan/workstreams/WS06-baselines/notes/
B5-deviations.md`` (deviations D1 to D20), and where B5 fails on this problem is
``notes/B5-failure-analysis.md``.

What B5 is. The direct method (Section 3.2, Theorem 1, equation (4), p. 8): a trajectory predictor completes the
observed prefix (equation (2), p. 7); the robustness of the completed trace is ``rho_hat``; the nonconformity score
of a calibration trajectory is the difference between the predicted and the true robustness; the constant ``C`` is
a finite-sample quantile of those scores (``ceil((n + 1)(1 - alpha))``-th smallest); the guarantee is marginal over
the test trajectory and the calibration set (Remark 2, p. 8). The paper certifies satisfaction. The alert about
violation applies the same theorem to the negated formula, whose robustness is minus the robustness (Appendix A,
p. 24): the score is ``R = rho_true - rho_hat`` (the one-sided score of ``#conformal-calibrator``), the alert is
emitted iff ``rho_hat + C < 0`` and the error event "alert emitted and ``rho_true >= 0``" has marginal probability
at most ``alpha`` under exchangeability across patient-days (D4).

What B5 is not. It has no three-valued semantics (a decided instance is violated iff its raw robustness is strictly
negative; before the deadline the only information is the prediction), no clinically scaled robustness (the values
stay in the unit of the template and are compared as they are), no attribution (``Detection.label`` is ``None``
and the evidence is dropped at the harness), no ranking and no abstention. A single ``alpha`` is used per
test, with no allocation over the many instances of a patient-day (D10): the union bound belongs to the proposed
method.

Mapping to the templates (``B5-deviations.md``, Mapping). One trajectory is one observed patient-day on the grid of
``step_ms`` with empty carry-over (ADR-061, proposed). One instance of a template is one specification, created as the
monitor creates it. Decided at the anchor means ``H = 0`` (equation (2) with no future part): RANGE, SYS, HOLD,
COUNT (limit) and INT have no predictive part and the decision is the sign of the measured raw robustness. RESP is
the only template whose open part is a continuous signal that the forecaster can predict: at the activation step the
forecast of ``bp`` and the measurement ticks of the plan complete the trace. SCHED and COUNT (day end) depend on
events and counters, which the trajectory model of the paper (real-valued states, Section 2, p. 4) does not predict,
so they get no predictive part (D2).

Aggregation. ``"conjunction"`` (name ``B5``): the robustness of a conjunction is the minimum of the conjuncts
(Appendix A, p. 24), so the instances evaluated at the same step are combined by the minimum of their raw values,
and a single calibrator is fitted on one score per prediction step. ``"per_template"`` (name ``B5-per-template``):
one calibrator per template and one decision per instance, the strongest fair setting. A detection is emitted on the
rising edge of the decision of an instance; once an instance is decided the decision is the sign of its measured raw
robustness (equation (2) with nothing left to predict).

Calibration. ``fit`` fits the forecaster on the observed training days, builds the episodes of the observed
calibration days with the same code path as ``run`` (the true robustness is that of the instance on the complete
observed day; the latent trace is never read), and fits the calibrator(s) with ``model_version`` set to the version
of the forecaster. ``plan_for_day`` supplies the care plan of a calibration day, because ``Detector.fit`` receives
days only (D14). Coverage statements read "marginal over patient episodes under exchangeability"; days of one
patient are not independent, which the harness does not check (D6).

Steelman. B5 receives every advantage the published method allows: the forecaster passed in (the same class and
seed as the proposed method), the same calibration days, the same ``alpha`` grid, both aggregations, an exact
quantile rule, and the measured verdict at the deadline. It is not weakened to make it fail.

Hyperparameter selection. The only operating parameter is ``alpha``, the level of the conformal constant (the
paper's failure probability, Theorem 1, p. 8). It has no default: WS08 sweeps it on its grid and nothing is tuned on
test days. The forecaster and the aggregation are fixed by the experiment config, not by B5.

Numbers. No clinical constant appears here; the parameters come from the registry and the care plan through the
point evaluator, and the registry reads are logged.
"""

from __future__ import annotations

import math
import sys
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Final, Literal

from ralmon.attribution import Detection
from ralmon.baselines.access import (
    AccessLog,
    AccessPolicy,
    GuardedDay,
    ReadLog,
    logged_plan,
)
from ralmon.baselines.base import BaselineBase, TimingConfig
from ralmon.baselines.raw_robustness import (
    LoggingRegistry,
    RawRobustnessEvaluator,
    SignalGrid,
    make_evaluator,
)
from ralmon.benchmark import ObservedDay
from ralmon.conformal import CalibrationEpisode, SplitConformal
from ralmon.monitor import (
    Forecaster,
    InsufficientHistoryError,
    PlanFeasibilityError,
    StaleCalibratorError,
)
from ralmon.signals import MS_PER_HOUR, Sample, SignalId
from ralmon.spec import CarePlan, Template, TemplateId, TemplateInstance

__all__ = [
    "AGGREGATIONS",
    "B5ConformalSTL",
    "B5Prediction",
    "Evaluation",
    "GroupValue",
    "aggregate_raw",
]

AGGREGATIONS: Final = ("conjunction", "per_template")
Aggregation = Literal["conjunction", "per_template"]
Phase = Literal["measured", "predicted"]
EvaluatorFactory = Callable[[Template, Any, int, str | None], RawRobustnessEvaluator]

_T_DAY_MS: Final = 24 * MS_PER_HOUR
# the score of a detection whose raw robustness is infinite (a failed Boolean guard): the largest finite number,
# so that the score stays finite (the harness refuses an infinite one) and ranks above every finite score (D20)
_LARGEST_SCORE: Final = sys.float_info.max

# the template whose open part is a continuous signal that the forecaster can predict, and that signal (D2)
_PREDICTIVE: Final[dict[TemplateId, str]] = {TemplateId.RESP: SignalId.BP.value}
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
_IMPULSE_KEYS: Final = frozenset(
    {
        SignalId.MEAS.value,
        SignalId.DISPENSE.value,
        SignalId.INTAKE.value,
        SignalId.SCHED_TICK.value,
        SignalId.AUTH.value,
    }
)


@dataclass(frozen=True, slots=True)
class Evaluation:
    """The raw robustness of one instance at one step, measured (decided) or predicted (``rho_hat``)."""

    key: str
    template: TemplateId
    value: float
    phase: Phase


@dataclass(frozen=True, slots=True)
class GroupValue:
    """The value that one decision is taken on: the minimum of a conjunction, or one instance.

    ``template`` is the template of the instance that attains the value (the first one on a tie).
    """

    label: str
    members: tuple[str, ...]
    value: float
    template: TemplateId


def aggregate_raw(
    evaluations: Sequence[Evaluation], aggregation: Aggregation
) -> list[GroupValue]:
    """Group the evaluations of one step and phase.

    ``"conjunction"``: one group, the minimum of the raw values whatever their units (the conjunction rule of
    Appendix A, p. 24); ``"per_template"``: one group per evaluation. The input order is kept.
    """
    if aggregation not in AGGREGATIONS:
        raise ValueError(
            f"aggregation must be one of {AGGREGATIONS}, got {aggregation!r}"
        )
    if not evaluations:
        return []
    if aggregation == "per_template":
        return [GroupValue(e.key, (e.key,), e.value, e.template) for e in evaluations]
    lowest = min(evaluations, key=lambda e: e.value)
    return [
        GroupValue(
            "conjunction",
            tuple(e.key for e in evaluations),
            lowest.value,
            lowest.template,
        )
    ]


@dataclass(frozen=True, slots=True)
class B5Prediction:
    """One predictive decision of the last ``run``: the value tested, the constant and the outcome.

    ``quantile`` is ``None`` when no calibrator was fitted for the group (no calibration episode); it is
    ``math.inf`` when the level is below ``1 / (n + 1)`` (nothing can be emitted).
    """

    keys: tuple[str, ...]
    template: TemplateId
    t_ms: int
    sigma_hat: float
    quantile: float | None
    emitted: bool


class _Tracker:
    """One instance followed through the day."""

    __slots__ = (
        "done",
        "evaluator",
        "flag",
        "has_value",
        "instance",
        "key",
        "kind",
        "predictable",
        "template",
        "value",
    )

    def __init__(
        self,
        key: str,
        template: Template,
        instance: TemplateInstance,
        kind: str,
        evaluator: RawRobustnessEvaluator,
        predictable: bool,
    ) -> None:
        self.key = key
        self.template = template
        self.instance = instance
        self.kind = kind
        self.evaluator = evaluator
        self.predictable = predictable
        self.has_value = False
        self.value: float | None = None
        self.flag = False
        self.done = False


@dataclass(slots=True)
class _Point:
    """A prediction recorded for the calibration (``rho_hat`` of an instance at its activation step)."""

    step: int
    key: str
    template: TemplateId
    sigma_hat: float


@dataclass(slots=True)
class _Outcome:
    detections: list[Detection] = field(default_factory=list)
    records: list[B5Prediction] = field(default_factory=list)
    points: list[_Point] = field(default_factory=list)
    final: dict[str, float | None] = field(default_factory=dict)
    skips: Counter[str] = field(default_factory=Counter)


@dataclass(frozen=True, slots=True)
class _Static:
    template: Template
    instance: TemplateInstance  # on the axis of the day
    kind: str


def _score(value: float) -> float:
    """A finite detection score from a non-negative robustness deficit."""
    if math.isnan(value):
        raise ValueError("a detection score cannot be NaN")
    return min(value, _LARGEST_SCORE)


def _check_alpha(alpha: object) -> float | Fraction:
    if isinstance(alpha, bool) or not isinstance(alpha, (float, Fraction)):
        raise ValueError(  # noqa: TRY004 - one named error for every bad level
            f"alpha must be a float or a Fraction in (0, 1), got {alpha!r}"
        )
    if not 0 < alpha < 1:
        raise ValueError(f"alpha must lie in (0, 1), got {alpha!r}")
    return alpha


class B5ConformalSTL(BaselineBase):
    """Baseline B5; see the module docstring for the method, its locators and what it leaves out.

    Parameters: ``templates`` (the library of ``load_templates``, or a subset), ``registry``, ``forecaster``
    (fitted by ``fit`` on the observed training days), ``calibrator_factory`` (default ``SplitConformal``; called once
    for ``"conjunction"`` and once per template for ``"per_template"``), ``alpha`` (the operating parameter, no
    default), ``aggregation``, ``timing``, ``plan_for_day`` (the care plan of an observed calibration day) and an
    optional ``evaluator_factory(template, registry, step_ms, anchor_kind)`` (default ``make_evaluator``).

    Hyperparameter selection. The only operating parameter is ``alpha``; see the module docstring.
    """

    name = "B5"

    def __init__(
        self,
        templates: Sequence[Template],
        registry: Any,
        forecaster: Forecaster,
        calibrator_factory: Callable[[], Any] = SplitConformal,
        *,
        alpha: float | Fraction,
        aggregation: Aggregation = "conjunction",
        timing: TimingConfig,
        plan_for_day: Callable[[ObservedDay], CarePlan],
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
        if aggregation not in AGGREGATIONS:
            raise ValueError(
                f"aggregation must be one of {AGGREGATIONS}, got {aggregation!r}"
            )
        by_id: dict[TemplateId, Template] = {}
        for template in templates:
            if template.id in by_id:
                raise ValueError(f"template {template.id.value} is given twice")
            by_id[template.id] = template
        if not by_id:
            raise ValueError("B5 needs at least one template")
        if _T_DAY_MS % timing.step_ms != 0:
            raise ValueError(f"step_ms {timing.step_ms} must divide the day")
        self._alpha = _check_alpha(alpha)
        self._aggregation: Aggregation = aggregation
        self.name = "B5" if aggregation == "conjunction" else "B5-per-template"
        self._templates = by_id
        self._registry = LoggingRegistry(registry, self.read_log)
        self._forecaster = forecaster
        self._calibrator_factory = calibrator_factory
        self._plan_for_day = plan_for_day
        self._evaluator_factory: EvaluatorFactory = (
            make_evaluator if evaluator_factory is None else evaluator_factory
        )
        supported = frozenset(forecaster.supported_signals)
        self._predictive = frozenset(
            tid
            for tid, signal in _PREDICTIVE.items()
            if tid in by_id and signal in supported
        )
        self._history_signals = supported
        self._with_signal = _accepts_signal(forecaster)
        self._calibrators: dict[str, Any] = {}
        self._fitted_groups: frozenset[str] = frozenset()
        self._episodes: tuple[CalibrationEpisode, ...] = ()
        self._censored = 0
        self.predictions: tuple[B5Prediction, ...] = ()
        self.skips: Mapping[str, int] = {}

    # -- what the last fit and run produced ---------------------------------------------------------------

    @property
    def n_calibration_episodes(self) -> int:
        return len(self._episodes)

    @property
    def n_censored(self) -> int:
        """Predictions of the calibration days whose true robustness was not defined (dropped)."""
        return self._censored

    @property
    def calibration_episodes(self) -> tuple[CalibrationEpisode, ...]:
        return self._episodes

    # -- fit ------------------------------------------------------------------------------------------------

    def _group_of(self, template: TemplateId) -> str:
        return "conjunction" if self._aggregation == "conjunction" else template.value

    def _fit(self, train: Sequence[GuardedDay], calib: Sequence[GuardedDay]) -> None:
        self._forecaster.fit([g.observed for g in train])
        groups = (
            ["conjunction"]
            if self._aggregation == "conjunction"
            else [tid.value for tid in self._templates]
        )
        calibrators = {g: self._calibrator_factory() for g in groups}
        episodes: list[CalibrationEpisode] = []
        censored = 0
        for guarded in calib:
            day = guarded.observed
            plan = logged_plan(self._plan_for_day(day), self.read_log)
            outcome = self._process(day, plan, calibrators=None)
            made, lost = self._episodes_of(day, outcome)
            episodes.extend(made)
            censored += lost
        fitted: set[str] = set()
        for group, calibrator in calibrators.items():
            mine = [e for e in episodes if self._group_of(e.template) == group]
            if mine:
                calibrator.fit(
                    mine, self._alpha, model_version=self._forecaster.model_version
                )
                fitted.add(group)
        self._calibrators = calibrators
        self._fitted_groups = frozenset(fitted)
        self._episodes = tuple(episodes)
        self._censored = censored
        self.predictions = ()
        self.skips = {}

    def _episodes_of(
        self, day: ObservedDay, outcome: _Outcome
    ) -> tuple[list[CalibrationEpisode], int]:
        """One episode per group of predictions: ``(rho_hat, rho_true)`` with the same aggregation as ``run``."""
        by_step: dict[int, list[_Point]] = {}
        for point in outcome.points:
            by_step.setdefault(point.step, []).append(point)
        episodes: list[CalibrationEpisode] = []
        censored = 0
        for step in sorted(by_step):
            points = sorted(by_step[step], key=lambda p: p.key)
            hats = [
                Evaluation(p.key, p.template, p.sigma_hat, "predicted") for p in points
            ]
            trues: list[Evaluation] = []
            for p in points:
                true = outcome.final.get(p.key)
                if true is not None and math.isfinite(true):
                    trues.append(Evaluation(p.key, p.template, true, "measured"))
            for group in aggregate_raw(hats, self._aggregation):
                members = set(group.members)
                known = [t for t in trues if t.key in members]
                if len(known) != len(members):
                    censored += 1
                    continue
                (true_group,) = aggregate_raw(known, self._aggregation)
                episodes.append(
                    CalibrationEpisode(
                        day.patient_id,
                        day.day_index,
                        group.template,
                        group.value,
                        true_group.value,
                    )
                )
        return episodes, censored

    # -- run ------------------------------------------------------------------------------------------------

    def _check_fresh(self) -> None:
        model = self._forecaster.model_version
        for group in self._fitted_groups:
            calibrated = self._calibrators[group].calibrated_for
            if calibrated is None or calibrated != model:
                raise StaleCalibratorError(
                    f"the calibrator of {group!r} was calibrated for {calibrated!r}, the forecaster is {model!r}: "
                    "fit B5 again"
                )

    def _run(self, day: ObservedDay, plan: CarePlan) -> Sequence[Detection]:
        self._check_fresh()
        outcome = self._process(day, plan, calibrators=self._calibrators)
        self.predictions = tuple(outcome.records)
        self.skips = dict(outcome.skips)
        return outcome.detections

    # -- one day, shared by fit and run ---------------------------------------------------------------------

    def _read_plan(
        self, plan: CarePlan, t0: int, step: int
    ) -> tuple[dict[TemplateId, Mapping[str, float]], list[_Static], frozenset[int]]:
        """The parameter records, the instances anchored by the plan and the measurement ticks of the day.

        Local times are on the axis of the day. An instance anchored outside the day is not part of it (empty
        carry-over, ADR-061). The measurement ticks are the anchors of the SCHED instances of the plan (the other
        ticks of ``CarePlan.schedule`` are dose ticks), whether or not SCHED is among the templates of B5.
        """
        records: dict[TemplateId, Mapping[str, float]] = {}
        statics: list[_Static] = []
        ticks: set[int] = set()
        for inst in plan.instances:
            tid = inst.template
            anchor = inst.anchor_ms
            if tid is TemplateId.SCHED and anchor is not None:
                if t0 <= anchor < t0 + _T_DAY_MS:
                    ticks.add(-(-(anchor - t0) // step))
                    if tid in self._templates:
                        statics.append(
                            _Static(
                                self._templates[tid],
                                TemplateInstance(
                                    tid,
                                    inst.instance_key,
                                    inst.param_values,
                                    anchor - t0,
                                ),
                                "sched_tick",
                            )
                        )
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
                    statics.append(
                        _Static(
                            self._templates[tid],
                            TemplateInstance(
                                tid, inst.instance_key, inst.param_values, _T_DAY_MS
                            ),
                            "day_end",
                        )
                    )
            else:
                raise PlanFeasibilityError(
                    f"instance {inst.instance_key!r}: template {tid.value} is instantiated at its anchoring "
                    "event, not by the plan; give anchor_ms None to set its parameter values"
                )
        return records, statics, frozenset(ticks)

    def _process(
        self,
        day: ObservedDay,
        plan: CarePlan,
        *,
        calibrators: Mapping[str, Any] | None,
    ) -> _Outcome:
        """Run one day through the grid, the instances and the decisions.

        With ``calibrators`` the predictive decisions are taken; without (the calibration pass) the predictions are
        recorded and nothing is emitted, and the final robustness of every instance is kept for the true score.
        """
        step = self._timing.step_ms
        t0 = day.day_index * _T_DAY_MS
        k_day = _T_DAY_MS // step
        records, statics, ticks = self._read_plan(plan, t0, step)
        grid = SignalGrid(step, delay_ms=self._timing.reorder_delay_ms, origin_ms=t0)
        rows: list[dict[str, float | None]] = []
        live: list[_Tracker] = []
        trackers: dict[str, _Tracker] = {}
        history: list[Sample] = []
        out = _Outcome()
        for batch in self._steps(day, plan):
            gs = grid.apply(batch)
            k = gs.k
            rows.append(gs.values)
            for sample in batch.samples:
                if sample.signal in self._history_signals:
                    history.append(sample)
            measured: list[Evaluation] = []
            for tracker in live:
                self._observe(
                    tracker, tracker.evaluator.step(k * step, gs.values), measured
                )
            new: list[_Tracker] = []
            if k == 0:
                for static in statics:
                    new.append(
                        self._make_tracker(
                            static.instance.instance_key,
                            static.template,
                            static.instance,
                            static.kind,
                            trackers,
                        )
                    )
            for anchors, kinds in (
                (gs.measurements, _MEASUREMENT_TEMPLATES),
                (gs.dispenses, _DISPENSE_TEMPLATES),
            ):
                for anchor in anchors:
                    if anchor < 0:
                        continue  # stamped before the day: not part of it
                    for tid in kinds:
                        template = self._templates.get(tid)
                        if template is None:
                            continue
                        key = _fresh_key(f"{tid.value}@{t0 + anchor}", trackers)
                        instance = TemplateInstance(
                            tid, key, records.get(tid, {}), anchor
                        )
                        new.append(
                            self._make_tracker(
                                key, template, instance, _ANCHOR_KIND[tid], trackers
                            )
                        )
            for tracker in new:
                value: float | None = None
                for kk in range(k + 1):
                    value = tracker.evaluator.step(kk * step, rows[kk])
                self._observe(tracker, value, measured)
            live.extend(new)
            self._decide_measured(measured, trackers, batch.t_ms, out, calibrators)
            self._predict(
                [t for t in new if t.predictable and not t.has_value],
                k,
                batch.t_ms,
                rows,
                history,
                ticks,
                k_day,
                trackers,
                out,
                calibrators,
            )
            live = [t for t in live if not t.done]
        for key, tracker in trackers.items():
            out.final[key] = tracker.value
        return out

    def _make_tracker(
        self,
        key: str,
        template: Template,
        instance: TemplateInstance,
        kind: str,
        trackers: dict[str, _Tracker],
    ) -> _Tracker:
        evaluator = self._evaluator_factory(
            template, self._registry, self._timing.step_ms, kind
        )
        evaluator.reset(instance)
        tracker = _Tracker(
            key,
            template,
            instance,
            kind,
            evaluator,
            template.id in self._predictive,
        )
        trackers[key] = tracker
        return tracker

    @staticmethod
    def _observe(
        tracker: _Tracker, value: float | None, measured: list[Evaluation]
    ) -> None:
        """Record the measured raw robustness of an instance: the first value, or a later turn to negative."""
        if value is None:
            return
        first = not tracker.has_value
        tracker.has_value = True
        tracker.value = value
        if first or (value < 0 and not tracker.flag):
            measured.append(
                Evaluation(tracker.key, tracker.template.id, value, "measured")
            )
        if tracker.template.id is not TemplateId.SCHED:
            tracker.done = True  # decided: the value of the other templates is final

    def _decide_measured(
        self,
        measured: list[Evaluation],
        trackers: dict[str, _Tracker],
        t_ms: int,
        out: _Outcome,
        calibrators: Mapping[str, Any] | None,
    ) -> None:
        if not measured:
            return
        measured.sort(key=lambda e: e.key)
        if calibrators is not None:
            fresh = [e for e in measured if not trackers[e.key].flag]
            for group in aggregate_raw(fresh, self._aggregation):
                if group.value < 0:
                    out.detections.append(Detection(t_ms, None, _score(-group.value)))
        for e in measured:
            trackers[e.key].flag = e.value < 0

    def _predict(
        self,
        activated: list[_Tracker],
        k: int,
        t_ms: int,
        rows: list[dict[str, float | None]],
        history: list[Sample],
        ticks: frozenset[int],
        k_day: int,
        trackers: dict[str, _Tracker],
        out: _Outcome,
        calibrators: Mapping[str, Any] | None,
    ) -> None:
        if not activated:
            return
        hats: list[Evaluation] = []
        for tracker in sorted(activated, key=lambda t: t.key):
            sigma_hat = self._sigma_hat(
                tracker, k, t_ms, rows, history, ticks, k_day, out
            )
            if sigma_hat is not None:
                hats.append(
                    Evaluation(tracker.key, tracker.template.id, sigma_hat, "predicted")
                )
        if not hats:
            return
        if calibrators is None:
            out.points.extend(_Point(k, e.key, e.template, e.value) for e in hats)
            return
        for group in aggregate_raw(hats, self._aggregation):
            name = self._group_of(group.template)
            if name not in self._fitted_groups:
                out.skips["no_calibration"] += 1
                out.records.append(
                    B5Prediction(
                        group.members, group.template, t_ms, group.value, None, False
                    )
                )
                continue
            calibrator = calibrators[name]
            emitted = bool(calibrator.predict(group.value, self._alpha).emitted)
            quantile = float(calibrator.quantile(self._alpha))
            out.records.append(
                B5Prediction(
                    group.members, group.template, t_ms, group.value, quantile, emitted
                )
            )
            if emitted:
                out.detections.append(
                    Detection(t_ms, None, _score(-(group.value + quantile)))
                )
                for e in hats:
                    if e.key in group.members:
                        trackers[e.key].flag = e.value + quantile < 0

    def _sigma_hat(
        self,
        tracker: _Tracker,
        k: int,
        t_ms: int,
        rows: list[dict[str, float | None]],
        history: list[Sample],
        ticks: frozenset[int],
        k_day: int,
        out: _Outcome,
    ) -> float | None:
        """``rho_hat``: the raw robustness of the instance on the trace completed at its activation step.

        The prefix is the rows delivered so far; the unknown future is the forecast of the signal of the template
        (equation (2), p. 7) and the measurement ticks of the plan; held status signals and counters keep their
        last value and no other event happens (D3). The forecast covers the rest of the day; the deadline is the
        first step at which the completed trace gives a value (D8).
        """
        step = self._timing.step_ms
        signal = _PREDICTIVE[tracker.template.id]
        horizon_steps = k_day - k
        if horizon_steps <= 0:
            out.skips["closes_after_day"] += 1
            return None
        try:
            forecast = self._forecast(signal, t_ms, horizon_steps * step, history)
        except InsufficientHistoryError:
            out.skips["insufficient_history"] += 1
            return None
        path = _checked_path(forecast, signal, t_ms, horizon_steps)
        if path is None:
            out.skips["invalid_forecast"] += 1
            return None
        evaluator = self._evaluator_factory(
            tracker.template, self._registry, step, tracker.kind
        )
        evaluator.reset(tracker.instance)
        value: float | None = None
        for kk in range(k + 1):
            value = evaluator.step(kk * step, rows[kk])
        if value is not None:
            out.skips["decided_at_activation"] += 1
            return None
        carried = {n: v for n, v in rows[k].items() if n not in _IMPULSE_KEYS}
        for kk in range(k + 1, k_day + 1):
            row: dict[str, float | None] = dict(carried)
            row.update(dict.fromkeys(_IMPULSE_KEYS, 0.0))
            row[signal] = path[kk - k - 1]
            if kk in ticks:
                row[SignalId.MEAS.value] = 1.0
            value = evaluator.step(kk * step, row)
            if value is not None:
                break
        if value is None:
            out.skips["closes_after_day"] += 1
            return None
        if not math.isfinite(value):
            out.skips["non_finite"] += 1
            return None
        return value

    def _forecast(
        self, signal: str, t_ms: int, horizon_ms: int, history: list[Sample]
    ) -> Any:
        if self._with_signal:
            return self._forecaster.predict(history, t_ms, horizon_ms, signal=signal)  # type: ignore[call-arg]
        supported = frozenset(self._forecaster.supported_signals)
        clean = [s for s in history if s.signal == signal or s.signal not in supported]
        return self._forecaster.predict(clean, t_ms, horizon_ms)


def _fresh_key(base: str, taken: Mapping[str, object]) -> str:
    key, n = base, 1
    while key in taken:
        n += 1
        key = f"{base}#{n}"
    return key


def _accepts_signal(forecaster: Any) -> bool:
    import inspect

    try:
        parameters = inspect.signature(forecaster.predict).parameters
    except (TypeError, ValueError):
        return False
    return "signal" in parameters or any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters.values()
    )


def _checked_path(
    forecast: Any, signal: str, t_ms: int, horizon_steps: int
) -> list[float] | None:
    """The path of a forecast if it is the one that was asked for and finite, else ``None``."""
    try:
        ok = (
            forecast.signal == signal
            and forecast.t_from_ms == t_ms
            and len(forecast.mean) == horizon_steps
        )
        values = [float(v) for v in forecast.mean] if ok else []
    except (AttributeError, TypeError, ValueError, OverflowError):
        return None
    if not ok or not all(math.isfinite(v) for v in values):
        return None
    return values
