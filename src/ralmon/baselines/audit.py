"""Fairness audit of the baselines B1 to B5: a knowledge matrix generated from access logs (WS06-T07).

The objection (analisi section 10, objection 1): "the evaluation is circular, whoever writes the specification wins". The
prevention is that every baseline receives the clinical knowledge of the proposed method that its definition allows, sees
the same inputs at the same time, never reads a latent trace or ground truth at inference, and is calibrated and tuned
only on data that the proposed method may also use. This module turns that into something that can be run: it fits every
detector through the harness on the same days, runs it on the same observed day, and reads what each one touched from
the logs of ``ralmon.baselines.access`` (``AccessLog`` for days, ``ReadLog`` for registry names and plan parameters). The
proposed method is audited the same way: its monitor runs on the same day through the same logging wrappers.

What a cell of the matrix means. ``read``: the logs show a read of every name of the row. ``partly read``: of some of
them (B1 is a minimal threshold baseline). ``not read``: the logs show none, although the detector had a channel for it.
``by design``: the detector has no channel at all (B2 and B4 take no registry; B1 and B3 take no forecaster; the
proposed method consumes the ``EvidenceVector`` and verifies the plan signature by construction); a by-design claim is
checked against the logs, and a read of a name declared by design is a problem of the report. The reasons are drawn from
the module docstrings of the baselines.

What the audit does not prove (the threat model of ``access.py``): the guards are a defence against accidents plus an
audit log, not a sandbox. The read logs are as complete as the code paths that use the wrappers: ``plan.schedule`` and the
anchors are not logged by name, so the schedule row comes from a spy on ``plan.schedule``; nothing in the logs shows which
read made a decision. The audit shows what well-behaved baselines read, not that no baseline could read more.

Knowledge set K. The task text defines it as the union, over the loaded templates, of ``params``, ``scale_param``,
``priority_param`` and ``max_verdict_latency_param``. The monitor of the proposed method also reads names that are not
template fields (the physiological bounds of ``bp`` and two global parameters, the device error and the clock-skew bound);
``run_audit`` adds the names that the proposed method read on the audited day, so ``AuditReport.knowledge`` is the union
and ``AuditReport.knowledge_task`` the text of the task; the difference is listed in the note, not hidden.

The probes (``Probe``, ``run_probe``) measure the size of the documented asymmetries between the harness and the monitor
on small fixtures: each probe is a control day and a perturbed day that differ in one thing, and the result is the number
of detections that the perturbation adds, per detector.

Numbers. No clinical constant appears here; everything is read from the objects under audit.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Final, SupportsIndex, overload

from ralmon.baselines.access import (
    AccessLog,
    GuardedDay,
    ReadLog,
    Split,
    logged_plan,
)
from ralmon.baselines.b1_static_thresholds import B1StaticThresholds
from ralmon.baselines.base import BaselineBase
from ralmon.baselines.raw_robustness import LoggingRegistry
from ralmon.benchmark import BenchmarkDay, ObservedDay
from ralmon.monitor import (
    Forecast,
    MonitorConfig,
    build_calibration_episodes,
    run_offline_detailed,
)
from ralmon.signals import Sample
from ralmon.spec import CarePlan, Template, TemplateId

__all__ = [
    "BY_DESIGN",
    "ITEMS",
    "OURS",
    "AuditDays",
    "AuditError",
    "AuditReport",
    "DetectorTrace",
    "ForecasterProbe",
    "KnowledgeRow",
    "Probe",
    "ProbeResult",
    "ProposedMethod",
    "assert_b1_not_vacuous",
    "item_names",
    "knowledge_set",
    "render_markdown",
    "render_probe_table",
    "run_audit",
    "run_probe",
]

OURS: Final = "ours (K)"
_T_DAY_MS: Final = 24 * 3_600_000
_BOUNDED_SIGNALS: Final = (
    "bp",
)  # the signals whose physiological bounds the monitor reads

# rows of the knowledge matrix, in the order of the note
ITEM_BAND: Final = "band (RANGE)"
ITEM_HOLD: Final = "hold threshold and look-back (HOLD)"
ITEM_WINDOW: Final = "schedule window (SCHED)"
ITEM_TICKS: Final = "schedule ticks (plan.schedule)"
ITEM_DOSE: Final = "dose limit and day-end minimum (COUNT)"
ITEM_RESP: Final = "response parameters (RESP)"
ITEM_SYSINT: Final = "system and integrity parameters (SYS, INT)"
ITEM_BOUNDS: Final = "physiological bounds"
ITEM_SCALE: Final = "scale"
ITEM_PRIORITY: Final = "priority"
ITEM_LATENCY: Final = "verdict-latency bound"
ITEM_FORECASTER: Final = "forecaster (fitted on training days)"
ITEM_CALIB: Final = "calibration days (observed trace only)"
ITEM_TRUTH: Final = "ground truth of training days"
ITEM_LATENT: Final = "latent trace (any day)"
ITEM_EVIDENCE: Final = "EvidenceVector"
ITEM_SIGNATURE: Final = "plan signature check"

ITEMS: Final = (
    ITEM_BAND,
    ITEM_HOLD,
    ITEM_WINDOW,
    ITEM_TICKS,
    ITEM_DOSE,
    ITEM_RESP,
    ITEM_SYSINT,
    ITEM_BOUNDS,
    ITEM_SCALE,
    ITEM_PRIORITY,
    ITEM_LATENCY,
    ITEM_FORECASTER,
    ITEM_CALIB,
    ITEM_TRUTH,
    ITEM_LATENT,
    ITEM_EVIDENCE,
    ITEM_SIGNATURE,
)
_NAME_ITEMS: Final = (
    ITEM_BAND,
    ITEM_HOLD,
    ITEM_WINDOW,
    ITEM_DOSE,
    ITEM_RESP,
    ITEM_SYSINT,
    ITEM_BOUNDS,
    ITEM_SCALE,
    ITEM_PRIORITY,
    ITEM_LATENCY,
)
_SOURCE_OF_ITEM: Final[Mapping[str, str]] = {
    ITEM_TICKS: "spy on `plan.schedule` (the anchors of the instances are not logged)",
    ITEM_FORECASTER: "probe on the forecaster: `fit` and `predict` calls",
    ITEM_CALIB: "`AccessLog`, calibration split",
    ITEM_TRUTH: "`AccessLog`, training split",
    ITEM_LATENT: "`AccessLog`, any split",
    ITEM_EVIDENCE: "output with `evidence=None` against a populated mapping",
    ITEM_SIGNATURE: "output with the plan signature replaced by a forged one",
}

_NO_REGISTRY = "takes no registry and no template and reads no plan parameter (its `read_log` stays empty)"
# (base name of the detector, item) -> reason; the detector has no channel for the item (module docstrings)
BY_DESIGN: Final[Mapping[tuple[str, str], str]] = {
    **{("B2", item): _NO_REGISTRY for item in _NAME_ITEMS},
    **{("B4", item): _NO_REGISTRY for item in _NAME_ITEMS},
    ("B1", ITEM_FORECASTER): "no forecaster and no calibrator (B1 docstring)",
    (
        "B3",
        ITEM_FORECASTER,
    ): "no forecaster, no calibrator, no uncertainty (B3 docstring)",
}
# cells of the proposed method that no log can show: declared by the contract
_OURS_BY_DESIGN: Final[Mapping[str, str]] = {
    ITEM_EVIDENCE: "the attribution layer consumes the EvidenceVector (analisi section 4.5)",
    ITEM_SIGNATURE: "`run_offline(verifier=...)` verifies the plan signature (ADR-053)",
}

READ, PARTLY, NOT_READ, DESIGN = "read", "partly read", "not read", "by design"


class AuditError(Exception):
    """A condition that the audit treats as a hard failure (a vacuous baseline, an unusable configuration)."""


class _SpySchedule(list[int]):
    """``plan.schedule`` that remembers whether anything looked at it (a list: the monitor requires a list or a tuple)."""

    def __init__(self, items: Sequence[int]) -> None:
        super().__init__(items)
        self.accessed = False

    def __iter__(self) -> Iterator[int]:
        self.accessed = True
        return super().__iter__()

    def __len__(self) -> int:
        self.accessed = True
        return super().__len__()

    def __contains__(self, item: object) -> bool:
        self.accessed = True
        return super().__contains__(item)

    def __reversed__(self) -> Iterator[int]:
        self.accessed = True
        return super().__reversed__()

    @overload
    def __getitem__(self, index: SupportsIndex) -> int: ...

    @overload
    def __getitem__(self, index: slice) -> list[int]: ...

    def __getitem__(self, index: SupportsIndex | slice) -> int | list[int]:
        self.accessed = True
        return super().__getitem__(index)


class ForecasterProbe:
    """A forecaster that delegates to another and records the calls of ``fit`` and ``predict``.

    ``fit_patients`` holds the patient ids of the days handed to each ``fit`` (a forecaster must be fitted on training
    days only). The probe has the members of the ``Forecaster`` protocol and the keyword ``signal`` of the concrete
    classes, so the baselines treat it as the forecaster it wraps.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.name = f"probe({getattr(inner, 'name', type(inner).__name__)})"
        self.fit_calls = 0
        self.predict_calls = 0
        self.fit_patients: list[tuple[str, ...]] = []

    @property
    def model_version(self) -> str:
        return str(self._inner.model_version)

    @property
    def supported_signals(self) -> frozenset[str]:
        return frozenset(self._inner.supported_signals)

    def fit(self, train_days: Sequence[Any]) -> None:
        self.fit_calls += 1
        self.fit_patients.append(tuple(d.patient_id for d in train_days))
        self._inner.fit(train_days)

    def predict(
        self,
        history: Sequence[Sample],
        t_ms: int,
        horizon_ms: int,
        *,
        signal: str | None = None,
    ) -> Forecast:
        self.predict_calls += 1
        result: Forecast = self._inner.predict(history, t_ms, horizon_ms, signal=signal)
        return result


@dataclass(frozen=True)
class AuditDays:
    """The days of one audit: the baselines are fitted on ``train`` and ``calib`` and run on ``test``."""

    train: Sequence[BenchmarkDay]
    calib: Sequence[BenchmarkDay]
    test: ObservedDay


@dataclass(frozen=True)
class ProposedMethod:
    """The proposed method as the audit runs it: the monitor with the calibrator built on the observed calibration days.

    ``plan_for_day`` gives the care plan of a calibration day (ADR-062); ``config`` is the ``MonitorConfig`` of the
    experiment (the timing of the baselines is compared with it).
    """

    config: MonitorConfig
    templates: Sequence[Template]
    forecaster: Any
    plan_for_day: Callable[[ObservedDay], CarePlan]
    calibrator_factory: Callable[[], Any]


@dataclass(frozen=True)
class DetectorTrace:
    """What one detector touched during the audited fit and run (names are registry names, ``bounds:<signal>`` and plan
    parameter names; the instance keys are dropped)."""

    name: str
    timing: tuple[int, int, int] | None
    fit_reads: frozenset[str]
    run_reads: frozenset[str]
    train_fields: frozenset[str]
    calib_fields: frozenset[str]
    all_fields: frozenset[str]
    denied: int
    by_exception: int
    schedule_accessed: bool
    forecaster_fit_calls: int | None
    forecaster_predict_calls: int | None
    evidence_invariant: bool | None
    signature_invariant: bool | None
    n_detections: int


@dataclass(frozen=True)
class KnowledgeRow:
    """One row of the matrix: the item, the names behind it (empty for items that are not names) and one cell per column."""

    item: str
    names: frozenset[str]
    cells: Mapping[str, str]
    notes: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class AuditReport:
    columns: tuple[str, ...]
    traces: Mapping[str, DetectorTrace]
    rows: tuple[KnowledgeRow, ...]
    knowledge_task: frozenset[str]
    knowledge: frozenset[str]
    problems: tuple[str, ...]


def knowledge_set(templates: Sequence[Template]) -> frozenset[str]:
    """K of the task text: ``params``, ``scale_param``, ``priority_param`` and ``max_verdict_latency_param`` of the templates."""
    names: set[str] = set()
    for template in templates:
        names.update(template.params)
        names.update(
            (
                template.scale_param,
                template.priority_param,
                template.max_verdict_latency_param,
            )
        )
    return frozenset(names)


def item_names(templates: Sequence[Template]) -> dict[str, frozenset[str]]:
    """The names behind every row that is a set of registry or parameter names."""
    by_template: dict[TemplateId, frozenset[str]] = {
        t.id: frozenset(t.params) for t in templates
    }

    def of(*ids: TemplateId) -> frozenset[str]:
        names: set[str] = set()
        for tid in ids:
            names.update(by_template.get(tid, ()))
        return frozenset(names)

    return {
        ITEM_BAND: of(TemplateId.RANGE),
        ITEM_HOLD: of(TemplateId.HOLD),
        ITEM_WINDOW: of(TemplateId.SCHED),
        ITEM_DOSE: of(TemplateId.COUNT),
        ITEM_RESP: of(TemplateId.RESP),
        ITEM_SYSINT: of(TemplateId.SYS, TemplateId.INT),
        ITEM_BOUNDS: frozenset(f"bounds:{s}" for s in _BOUNDED_SIGNALS),
        ITEM_SCALE: frozenset(t.scale_param for t in templates),
        ITEM_PRIORITY: frozenset(t.priority_param for t in templates),
        ITEM_LATENCY: frozenset(t.max_verdict_latency_param for t in templates),
    }


def _base_name(name: str) -> str:
    return name.split("-")[0]


def _cell(names: frozenset[str], reads: frozenset[str]) -> tuple[str, str]:
    hit = names & reads
    if not names:
        return NOT_READ, ""
    if hit == names:
        return READ, ""
    if hit:
        return (
            PARTLY,
            f"reads {', '.join(sorted(hit))}; not {', '.join(sorted(names - hit))}",
        )
    return NOT_READ, ""


_EVIDENCE: Final[Mapping[str, Any]] = {"audit-evidence": object()}


def _audit_detector(
    det: BaselineBase,
    days: AuditDays,
    plan: CarePlan,
    probe: ForecasterProbe | None,
    names: Mapping[str, frozenset[str]],
    problems: list[str],
) -> DetectorTrace:
    name = det.name
    det.access_log.clear()
    det.read_log.clear()
    det.fit(days.train, days.calib)
    fit_reads = det.read_log.all_names()
    log = det.access_log
    train_fields = log.fields(Split.TRAIN)
    calib_fields = log.fields(Split.CALIB)
    all_fields = log.fields()
    denied = len(log.denied)
    by_exception = sum(1 for r in log.records if r.by_exception)
    det.read_log.clear()
    spy = _SpySchedule(plan.schedule)
    base = tuple(det.run(days.test, replace(plan, schedule=spy), None))
    run_reads = det.read_log.all_names()
    with_evidence = tuple(det.run(days.test, plan, _EVIDENCE))
    forged = tuple(
        det.run(days.test, replace(plan, signature="forged-signature"), None)
    )
    evidence_invariant = base == with_evidence
    signature_invariant = base == forged
    if not evidence_invariant:
        problems.append(f"{name}: the output depends on the EvidenceVector")
    if not signature_invariant:
        problems.append(f"{name}: the output depends on the plan signature")
    if "latent" in all_fields:
        problems.append(f"{name}: a latent trace was read")
    if denied:
        problems.append(f"{name}: {denied} read(s) were refused by the access guard")
    if by_exception:
        problems.append(f"{name}: {by_exception} read(s) allowed only by calib_latent")
    extra_calib = calib_fields - {"observed"}
    if extra_calib:
        problems.append(
            f"{name}: calibration days gave more than the observed trace: {sorted(extra_calib)}"
        )
    t = det.timing
    if t.reorder_delay_ms % t.step_ms:
        problems.append(
            f"{name}: reorder_delay_ms {t.reorder_delay_ms} is not a multiple of step_ms {t.step_ms}; "
            "the lateness rule of the grid then differs from the monitor's (open decision, WS06-T05)"
        )
    normalising = names[ITEM_SCALE] | names[ITEM_PRIORITY] | names[ITEM_LATENCY]
    if normalising & (fit_reads | run_reads):
        problems.append(
            f"{name}: read a scale, priority or verdict-latency name "
            f"({', '.join(sorted(normalising & (fit_reads | run_reads)))}); the baselines are defined without normalisation"
        )
    base_name = _base_name(name)
    for item in _NAME_ITEMS:
        reason = BY_DESIGN.get((base_name, item))
        if reason is not None and names[item] & (fit_reads | run_reads):
            problems.append(f"{name}: read a name of '{item}', declared by design")
    fit_calls = predict_calls = None
    if probe is not None:
        fit_calls, predict_calls = probe.fit_calls, probe.predict_calls
        trained = {d.observed.patient_id for d in days.train}
        used = {p for patients in probe.fit_patients for p in patients}
        if not used <= trained:
            problems.append(
                f"{name}: the forecaster was fitted on days outside the training days: {sorted(used - trained)}"
            )
    return DetectorTrace(
        name,
        (t.step_ms, t.reorder_delay_ms, t.tail_ms),
        fit_reads,
        run_reads,
        train_fields,
        calib_fields,
        all_fields,
        denied,
        by_exception,
        spy.accessed,
        fit_calls,
        predict_calls,
        evidence_invariant,
        signature_invariant,
        len(base),
    )


def _violated_instances(result: Any) -> list[tuple[str, int]]:
    """``(instance_key, t_eval_ms)`` of the first VIOLATED record of every instance, in order of time."""
    first: dict[str, int] = {}
    for record in result.records:
        if record.state.value == "violated" and record.instance_key not in first:
            first[record.instance_key] = record.t_eval_ms
    return sorted(first.items(), key=lambda kv: (kv[1], kv[0]))


def _audit_proposed(
    proposed: ProposedMethod,
    days: AuditDays,
    plan: CarePlan,
    registry: Any,
    probe: ForecasterProbe | None,
    problems: list[str],
) -> DetectorTrace:
    log = AccessLog()
    reads = ReadLog()
    train = [GuardedDay(d, Split.TRAIN, log).observed for d in days.train]
    calib = [GuardedDay(d, Split.CALIB, log).observed for d in days.calib]
    forecaster = proposed.forecaster
    forecaster.fit(train)
    logging_registry = LoggingRegistry(registry, reads)
    plans = [logged_plan(proposed.plan_for_day(d), reads) for d in calib]
    episodes, _ = build_calibration_episodes(
        calib,
        plans,
        proposed.config,
        forecaster,
        registry=logging_registry,
        templates=proposed.templates,
    )
    calibrator = proposed.calibrator_factory()
    alpha = proposed.config.alpha if proposed.config.alpha is not None else 0.1
    calibrator.fit(episodes, alpha, model_version=forecaster.model_version)
    fit_reads = reads.all_names()
    reads.clear()
    spy = _SpySchedule(plan.schedule)
    result = run_offline_detailed(
        days.test,
        logged_plan(replace(plan, schedule=spy), reads),
        proposed.config,
        calibrator,
        forecaster,
        registry=logging_registry,
        templates=proposed.templates,
    )
    run_reads = reads.all_names()
    if "latent" in log.fields():
        problems.append("ours: a latent trace was read")
    config = proposed.config
    if config.reorder_delay_ms % config.step_ms:
        problems.append("ours: reorder_delay_ms is not a multiple of step_ms")
    fit_calls = predict_calls = None
    if probe is not None:
        fit_calls, predict_calls = probe.fit_calls, probe.predict_calls
    return DetectorTrace(
        "ours",
        None,
        fit_reads,
        run_reads,
        log.fields(Split.TRAIN),
        log.fields(Split.CALIB),
        log.fields(),
        len(log.denied),
        sum(1 for r in log.records if r.by_exception),
        spy.accessed,
        fit_calls,
        predict_calls,
        None,
        None,
        len(_violated_instances(result)),
    )


def run_audit(
    detectors: Sequence[BaselineBase],
    days: AuditDays,
    plan: CarePlan,
    registry: Any,
    *,
    templates: Sequence[Template],
    proposed: ProposedMethod | None = None,
    probes: Mapping[str, ForecasterProbe] | None = None,
) -> AuditReport:
    """Fit every detector on the same days, run it on the same observed day and read the logs (module docstring).

    ``probes`` maps a detector name (or ``"ours"``) to the ``ForecasterProbe`` that wraps its forecaster. The detectors
    are left fitted, with their logs filled, so that a caller can inspect them.
    """
    probes = {} if probes is None else probes
    names = item_names(templates)
    problems: list[str] = []
    traces: dict[str, DetectorTrace] = {}
    for det in detectors:
        if det.name in traces:
            raise AuditError(f"two detectors are named {det.name!r}")
        traces[det.name] = _audit_detector(
            det, days, plan, probes.get(det.name), names, problems
        )
    timings = {t.timing for t in traces.values()}
    if len(timings) > 1:
        problems.append(
            f"the baselines do not share one timing configuration: {sorted(str(t) for t in timings)}"
        )
    k_task = knowledge_set(templates)
    knowledge = k_task
    if proposed is not None:
        pfc = probes.get("ours") or (
            proposed.forecaster
            if isinstance(proposed.forecaster, ForecasterProbe)
            else None
        )
        ours = _audit_proposed(proposed, days, plan, registry, pfc, problems)
        traces["ours"] = ours
        knowledge = k_task | ours.fit_reads | ours.run_reads
        for trace in traces.values():
            if trace.timing is not None and (
                trace.timing[0],
                trace.timing[1],
            ) != (proposed.config.step_ms, proposed.config.reorder_delay_ms):
                problems.append(
                    f"{trace.name}: step_ms or reorder_delay_ms differs from the MonitorConfig of the proposed method"
                )
    columns = tuple(d.name for d in detectors) + ((OURS,) if proposed else ())
    rows = _rows(columns, traces, names, k_task, knowledge)
    return AuditReport(
        columns, traces, rows, k_task, knowledge, tuple(dict.fromkeys(problems))
    )


def _rows(
    columns: tuple[str, ...],
    traces: Mapping[str, DetectorTrace],
    names: Mapping[str, frozenset[str]],
    k_task: frozenset[str],
    knowledge: frozenset[str],
) -> tuple[KnowledgeRow, ...]:
    rows: list[KnowledgeRow] = []
    for item in ITEMS:
        cells: dict[str, str] = {}
        notes: dict[str, str] = {}
        for column in columns:
            ours = column == OURS
            trace = traces["ours" if ours else column]
            reads = trace.fit_reads | trace.run_reads
            cell, note = _one_cell(
                item, column, ours, trace, reads, names, knowledge, k_task
            )
            cells[column] = cell
            if note:
                notes[column] = note
        rows.append(KnowledgeRow(item, names.get(item, frozenset()), cells, notes))
    return tuple(rows)


def _one_cell(
    item: str,
    column: str,
    ours: bool,
    trace: DetectorTrace,
    reads: frozenset[str],
    names: Mapping[str, frozenset[str]],
    knowledge: frozenset[str],
    k_task: frozenset[str],
) -> tuple[str, str]:
    if item in _NAME_ITEMS:
        behind = names[item]
        if ours:
            cell, note = _cell(behind, knowledge)
            unread = (behind & k_task) - reads
            if cell != NOT_READ and unread:
                note = f"in K, not read by the monitor on the audited day: {', '.join(sorted(unread))}"
            return cell, note
        reason = BY_DESIGN.get((_base_name(column), item))
        if reason is not None:
            return DESIGN, reason
        return _cell(behind, reads)
    if item == ITEM_TICKS:
        return (READ, "") if trace.schedule_accessed else (NOT_READ, "")
    if item == ITEM_FORECASTER:
        if not ours:
            reason = BY_DESIGN.get((_base_name(column), item))
            if reason is not None:
                return DESIGN, reason
        return (READ, "") if (trace.forecaster_fit_calls or 0) > 0 else (NOT_READ, "")
    if item == ITEM_CALIB:
        if "observed" in trace.calib_fields:
            return READ, "observed trace only" if trace.calib_fields == {
                "observed"
            } else ""
        return NOT_READ, ""
    if item == ITEM_TRUTH:
        return (READ, "") if "ground_truth" in trace.train_fields else (NOT_READ, "")
    if item == ITEM_LATENT:
        return (READ, "") if "latent" in trace.all_fields else (NOT_READ, "")
    if item in (ITEM_EVIDENCE, ITEM_SIGNATURE):
        if ours:
            return DESIGN, _OURS_BY_DESIGN[item]
        invariant = (
            trace.evidence_invariant
            if item == ITEM_EVIDENCE
            else trace.signature_invariant
        )
        return (NOT_READ, "") if invariant else (READ, "")
    raise AssertionError(item)


# ---- rendering --------------------------------------------------------------------------------------------------------


def render_markdown(report: AuditReport) -> str:
    """The knowledge matrix of the audit as Markdown: the table, the names behind each row, the reasons of the by-design
    cells, the partial reads and the names of the proposed method outside the text of K. Deterministic."""
    cols = report.columns
    lines = [
        "| Item | " + " | ".join(cols) + " |",
        "|---|" + "---|" * len(cols),
    ]
    for row in report.rows:
        lines.append(f"| {row.item} | " + " | ".join(row.cells[c] for c in cols) + " |")
    lines += ["", "Names behind each row, and where the cell comes from:", ""]
    for row in report.rows:
        if row.names:
            lines.append(
                f"- {row.item}: " + ", ".join(f"`{n}`" for n in sorted(row.names))
            )
        else:
            lines.append(f"- {row.item}: {_SOURCE_OF_ITEM[row.item]}")
    reasons = [
        (row.item, c, row.notes[c])
        for row in report.rows
        for c in cols
        if row.cells[c] == DESIGN
    ]
    lines += ["", "Reasons of the `by design` cells:", ""]
    by_reason: dict[tuple[str, str], list[str]] = {}
    for item, column, reason in reasons:
        by_reason.setdefault((column, reason), []).append(item)
    for (column, reason), items in by_reason.items():
        lines.append(f"- {column}, {len(items)} row(s) ({'; '.join(items)}): {reason}")
    partial = [
        (row.item, c, row.notes[c])
        for row in report.rows
        for c in cols
        if row.cells[c] == PARTLY or row.notes.get(c, "").startswith("in K")
    ]
    if partial:
        lines += [
            "",
            "Partial reads, and names of K that the monitor did not read on the audited day:",
            "",
        ]
        for item, column, note in partial:
            lines.append(f"- {item}, {column}: {note}")
    extras = sorted(report.knowledge - report.knowledge_task)
    lines += [
        "",
        "Names read by the proposed method that are not template fields (K of the task text is extended by them): "
        + (", ".join(f"`{n}`" for n in extras) if extras else "none")
        + ".",
        "",
        "Problems found by the audit: " + ("none." if not report.problems else ""),
    ]
    for problem in report.problems:
        lines.append(f"- {problem}")
    return "\n".join(lines) + "\n"


# ---- probes ------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Probe:
    """A control day and a perturbed day that differ in one thing, run with the same plan.

    ``history`` holds the days before ``perturbed`` that only the proposed method can be given (``Detector.run`` has no
    ``history``, ADR-061); the control is always run without it. ``registry`` replaces the registry of the audit for the
    monitor of this probe (the fixture registry has no ``clock_skew_max_ms``, so the monitor's future-stamp check is off).
    """

    label: str
    control: ObservedDay
    perturbed: ObservedDay
    plan: CarePlan
    note: str
    history: tuple[ObservedDay, ...] = ()
    registry: Any = None


@dataclass(frozen=True)
class ProbeResult:
    """Detections added by the perturbation, per detector (``ours`` counts violated instances of the monitor).

    ``extra_after_close`` counts the added detections at or after the closing step of the day;
    ``extra_without_history`` is the monitor run without the history of the probe.
    """

    probe: Probe
    extra: Mapping[str, int]
    extra_after_close: Mapping[str, int]
    extra_without_history: Mapping[str, int]


def _monitor_count(
    day: ObservedDay,
    probe: Probe,
    registry: Any,
    proposed: ProposedMethod,
    history: Sequence[ObservedDay],
) -> tuple[int, int]:
    config = replace(proposed.config, predictive=False, alpha=None)
    result = run_offline_detailed(
        day,
        probe.plan,
        config,
        None,
        None,
        registry=probe.registry if probe.registry is not None else registry,
        templates=proposed.templates,
        history=list(history),
    )
    close = (day.day_index + 1) * _T_DAY_MS
    violated = _violated_instances(result)
    return len(violated), sum(1 for _, t in violated if t >= close)


def run_probe(
    detectors: Sequence[BaselineBase],
    probe: Probe,
    registry: Any,
    proposed: ProposedMethod | None = None,
) -> ProbeResult:
    """Run the control and the perturbed day through every fitted detector and the monitor; report what was added."""
    extra: dict[str, int] = {}
    after: dict[str, int] = {}
    close = (probe.perturbed.day_index + 1) * _T_DAY_MS
    for det in detectors:
        control = det.run(probe.control, probe.plan, None)
        perturbed = det.run(probe.perturbed, probe.plan, None)
        extra[det.name] = len(perturbed) - len(control)
        after[det.name] = sum(1 for d in perturbed if d.t_ms >= close) - sum(
            1 for d in control if d.t_ms >= close
        )
    without: dict[str, int] = {}
    if proposed is not None:
        c_n, c_after = _monitor_count(probe.control, probe, registry, proposed, ())
        p_n, p_after = _monitor_count(
            probe.perturbed, probe, registry, proposed, probe.history
        )
        extra["ours"], after["ours"] = p_n - c_n, p_after - c_after
        c0, _ = _monitor_count(probe.control, probe, registry, proposed, ())
        p0, _ = _monitor_count(probe.perturbed, probe, registry, proposed, ())
        without["ours"] = p0 - c0
    return ProbeResult(probe, extra, after, without)


def render_probe_table(results: Sequence[ProbeResult]) -> str:
    """The probe table as Markdown: per probe and detector, the detections that the perturbation adds (and, in
    brackets, how many of them are at or after the closing step of the day). Deterministic."""
    if not results:
        return ""
    cols = list(results[0].extra)
    lines = [
        "| Probe | " + " | ".join(cols) + " |",
        "|---|" + "---|" * len(cols),
    ]
    for r in results:
        cells = []
        for c in cols:
            text = f"{r.extra[c]:+d}"
            if r.extra_after_close.get(c):
                text += f" ({r.extra_after_close[c]:+d} after close)"
            cells.append(text)
        lines.append(f"| {r.probe.label} | " + " | ".join(cells) + " |")
    lines.append("")
    for r in results:
        line = f"- {r.probe.label}: {r.probe.note}"
        if r.probe.history:
            line += f"; ours without the history of the probe: {r.extra_without_history['ours']:+d}"
        lines.append(line)
    return "\n".join(lines) + "\n"


# ---- gates for the callers ---------------------------------------------------------------------------------------------


def assert_b1_not_vacuous(b1: B1StaticThresholds) -> None:
    """Fail unless the last run of ``b1`` had all four rules active (the vacuity policy, Notes of WS06-T02).

    A rule is silent when the plan has no parameter record for its template, so a plan that carries only the schedule
    (the monitor's own helper) makes B1 a straw man by accident. WS08 calls this on the plans of every benchmark run.
    """
    stats = b1.run_stats
    if stats is None:
        raise AuditError("B1 has not run: call run() before the vacuity gate")
    expected = ("R1", "R2", "R3", "R4")
    if tuple(stats.rules_active) != expected:
        raise AuditError(
            f"B1 is vacuous on this plan: rules_active is {tuple(stats.rules_active)}, expected {expected}; "
            "the plan lacks the RANGE, HOLD or COUNT parameter record, or a SCHED instance"
        )
