"""The truth of an alert for the scoring of the probabilistic attribution (WS08-T09, ADR-074 amendments 2 and 3).

SCORING SIDE ONLY. This module reads the ground truth (``GroundTruthEvent`` and the injection log of the truth sidecar). A
detector, the attributor and the set builder never do (``ralmon.attribution`` and ``ralmon.conformal`` do not import this
package). What a detector hands to the scoring side is ``AlertInputs``: posteriors, fixed sets and the evidence vector, no truth.

The cause of an alert. An alert is caused by a ground-truth event, and one alert can be compatible with several events (a
fault that overlaps a violation of the clinical template). The relation is MANY-TO-ONE and independent of the one-to-one
matching of ``match_events`` (which is template-agnostic and would let an ECG fault take the alert of a COUNT violation):

* TEMPLATE. The template of the alert (``Alert.tau``) must be one the event can violate: the ``template_id`` of a C1 event, the
  ``templates`` of the injection-log entry that explains a C2 event, the static table of the threat model for a C3 subtype. A
  context with ``templates`` None is unconstrained.
* TIME. The alert is decided (``Alert.t_ms``) in ``[ref, max(ref, end) + after]``, ``ref`` the first decidable instant of the
  event (``end_ms`` of a windowed C1 obligation, the onset otherwise), ``end`` its end or its onset, ``after`` the run parameter
  ``loose_after_ms`` (``awaiting_human_value``; no default).
* TIGHT (primary, ADR-074 amendment 2). A C2 event is the cause of an alert only if the faulty device is in the data scope of the
  template of the alert (the cells of the likelihood table describe the fault that CAUSES the violation, not any fault present in
  the scope) and the alert is decided while the event window is ACTIVE (``after`` = 0 for a C2 event). A target that is the robot
  must have the robot in the scope of the template; a target that is neither a BLE device nor the robot is not scope-checked.
  C1 and C3 events are read with the loose rule. The ADR names the C2 event only; the research prototype applied the closed
  window to all events, which is not what the ADR says.
* LOOSE (reported next to it in every table). A fault anywhere in the window counts (the ECG and the oximeter for COUNT and RESP
  alerts included), with ``after`` for every event.

THE CHOICE OF THE TIGHT LABELLING WAS MADE AFTER SEEING THE RESULT of the recompute (the driver diagnostics worsen the log score
by 0.007 nats under the loose labelling and improve it under the tight one): it is a decision of gab, not a finding, and the
paper states the order of events (``LABELLING_STATEMENT``).

AMBIGUOUS (B1, decided by gab; no horizon is invented). A point or per-tick C2 fault (``end_ms`` None: ``nav_delay``,
``manipulation_failure``, ``dispenser_bounce``) is active only at its instant, so the tight rule rejects it for any later alert. When the
LOOSE rule accepts an injected C2 event that the tight rule rejects only by TIME (the faulty device is in the data scope), the tight
label of the alert is AMBIGUOUS, never the natural C1 cause that happens to be compatible too: the alert leaves the tight tables and is
counted in its own bucket (``LabelResult.ambiguous``, ``excluded["ambiguous"]``), reported per injected subtype and with its loose
label. A fault OUTSIDE the data scope stays a definite non-cause. The headline figure of the three point subtypes is the LOOSE one. A
structural link ("the alert of the instance the fault targets") would be a later refinement.

From the compatible events the cause is: the class they all share; else the class of the INJECTED events if exactly one class
is injected; else the alert is ambiguous and left out (counted). The true subtype is the subtype of the first injected event of
that class (then by onset). An alert with no compatible event is a false alarm for this purpose and is left out (counted). A
predicted violation has no posterior; a cascade effect carries the ROOT's ``p_kappa`` and ``cause_set``, so under the default
policy ``effects="fold"`` it is left out (counted), under ``"include"`` it is scored against its own compatible events.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from ralmon.attribution import Alert, EvidenceVector
from ralmon.benchmark import GroundTruthEvent, InjectedClass
from ralmon.monitor import VerdictState

__all__ = [
    "BLE_DEVICES",
    "C3_EVENT_TEMPLATES",
    "DATA_SCOPE",
    "EFFECT_POLICIES",
    "LABELLINGS",
    "LABELLING_STATEMENT",
    "ROBOT_SCOPE",
    "AlertInputs",
    "AmbiguousAlert",
    "EventContext",
    "LabelResult",
    "LabelledAlert",
    "ambiguous_summary",
    "both_labellings",
    "day_contexts",
    "event_templates",
    "label_alerts",
    "subtype_alert_table",
]

LABELLINGS: Final[tuple[str, ...]] = ("tight", "loose")
EFFECT_POLICIES: Final[tuple[str, ...]] = ("fold", "include")

#: The BLE devices of the data scope of each template (``docs/models/evidence-channels.md``, Scope of an instance; the extractor
#: holds the same table privately, a test compares the two).
DATA_SCOPE: Final[Mapping[str, tuple[str, ...]]] = {
    "range": ("cuff",),
    "sched": ("cuff",),
    "hold": ("cuff", "dispenser"),
    "count": ("dispenser",),
    "resp": ("cuff", "dispenser"),
    "sys": ("cuff",),
    "int": ("dispenser",),
}
#: The templates that have the robot node in their scope (the same document).
ROBOT_SCOPE: Final[frozenset[str]] = frozenset({"sched", "hold", "resp", "int"})
BLE_DEVICES: Final[tuple[str, ...]] = ("cuff", "dispenser", "ecg", "oximeter")
_ROBOT: Final = "robot"
#: The templates a C3 subtype can change (``docs/models/attribution-likelihood.md``, catalogue; the injection log of a C3 record
#: lists none). Subtypes of the threat model; the two not injected in benchmark v1 are listed for completeness.
C3_EVENT_TEMPLATES: Final[Mapping[str, tuple[str, ...]]] = {
    "replay": ("range", "sched", "hold", "resp", "sys"),
    "injection_naive": ("range", "sched", "hold", "resp", "sys"),
    "injection_informed": ("range", "hold", "resp", "sys"),
    "dispense_forgery": ("hold", "count", "resp", "int"),
    "presence_spoof": ("int",),
    "dispenser_physical_tamper": ("hold", "count", "resp", "int"),
    "timestamp_manipulation": ("range", "sched", "hold", "resp"),
}

LABELLING_STATEMENT: Final = (
    "The TIGHT labelling is primary: a C2 event is the cause of an alert only if the faulty device is in the data scope of the "
    "template of the alert and the alert is decided while the event window is active (ADR-074 amendment 2). The LOOSE labelling "
    "(a fault anywhere in the window counts, including the ECG and the oximeter for COUNT and RESP alerts) is reported next to it in "
    "every table. The choice of the tight labelling was made after seeing the result of the recompute (the driver diagnostics worsen "
    "the log score by 0.007 nats under the loose labelling and improve it under the tight one): it is a decision, not a finding, and "
    "the paper states the order of events."
)


@dataclass(frozen=True, slots=True)
class EventContext:
    """What the injection log says about one ground-truth event (scoring side): the templates it can violate and the faulty
    device. ``templates`` None: unconstrained; ``target`` None: unknown (not scope-checked)."""

    templates: tuple[str, ...] | None = None
    target: str | None = None


@dataclass(frozen=True, slots=True)
class AlertInputs:
    """What a detector hands to the scoring side besides the alert: NO truth.

    * ``posteriors``: method name to the posterior over the subtypes applicable at the template (the keys of
      ``LikelihoodRule.posterior_subtypes``; it sums to 1). The method ``lik`` is the likelihood model, ``prior`` the prior-only
      baseline (the same call with an empty evidence vector), by convention; any name is accepted.
    * ``fixed_sets``: method name to a set with no threshold to tune (the hierarchical rule's kappa as a set).
    * ``evidence``: the evidence vector of the alert (for the pair quantity Lambda).
    """

    posteriors: Mapping[str, Mapping[str, float]] = field(default_factory=dict)
    fixed_sets: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    evidence: EvidenceVector | None = None


@dataclass(frozen=True, slots=True)
class LabelledAlert:
    """A VIOLATED alert with its cause (the truth, scoring side). ``template`` is lower case; ``true_class`` is C1, C2 or C3."""

    patient_id: str
    alert: Alert
    template: str
    true_class: str
    true_subtype: str
    event_index: int  # in the ground truth the labelling was given
    injected: bool
    n_compatible: int
    inputs: AlertInputs | None = None


@dataclass(frozen=True, slots=True)
class AmbiguousAlert:
    """An alert whose TIGHT label is AMBIGUOUS (B1, decided by gab): it is compatible under the loose rule with an injected C2 event
    that the tight rule rejects only because of TIME (the faulty device is in the data scope, the alert is decided outside the
    window: a point or per-tick fault is active only at its instant). The tight label must not become the natural C1 cause in that
    case, so the alert has its own bucket, with the injected subtypes in question and its LOOSE label (``loose_class`` and
    ``loose_subtype``, None when the loose rule gives none)."""

    patient_id: str
    alert: Alert
    template: str
    injected_subtypes: tuple[str, ...]
    loose_class: str | None
    loose_subtype: str | None


@dataclass(frozen=True, slots=True)
class LabelResult:
    """The labelled alerts, the AMBIGUOUS ones (tight labelling only) and the counts of those left out, by reason."""

    labelled: tuple[LabelledAlert, ...]
    excluded: Mapping[str, int]
    ambiguous: tuple[AmbiguousAlert, ...] = ()


#: the reasons an alert is left out: ``ambiguous`` is the AMBIGUOUS class of the tight labelling (own bucket, reported apart);
#: ``class_conflict`` is an alert compatible with events of two classes that the injected-first rule cannot resolve
_EXCLUDED_KEYS: Final[tuple[str, ...]] = (
    "not_an_alert",
    "predicted_violation",
    "cascade_effect",
    "no_compatible_event",
    "class_conflict",
    "ambiguous",
)


def _first_decidable(event: GroundTruthEvent) -> int:
    """Same rule as ``ralmon.eval.metrics.first_decidable_ms`` (a test compares the two; ``metrics`` imports this module)."""
    if event.cls is InjectedClass.C1 and event.end_ms is not None:
        return event.end_ms
    return event.onset_ms


def _text_tuple(value: object) -> tuple[str, ...] | None:
    if isinstance(value, (list, tuple)) and all(isinstance(x, str) for x in value):
        return tuple(x.lower() for x in value)
    return None


def day_contexts(
    ground_truth: Sequence[GroundTruthEvent],
    injection_log: Sequence[Mapping[str, Any]],
) -> list[EventContext]:
    """One ``EventContext`` per ground-truth event of a day, from the injection log of the same day.

    A C1 event takes its ``template_id``; a C3 event the static table (``C3_EVENT_TEMPLATES``) unless its log entry lists
    ``details["templates"]``; a C2 event the ``details["templates"]`` and ``details["target"]`` of the entry that links it
    (``truth_indices``). An event that no entry links is unconstrained."""
    linked: dict[int, Mapping[str, Any]] = {}
    for entry in injection_log:
        indices = entry.get("truth_indices", ())
        if isinstance(indices, (list, tuple)):
            for index in indices:
                if isinstance(index, int) and not isinstance(index, bool):
                    linked.setdefault(index, entry)
    out: list[EventContext] = []
    for i, event in enumerate(ground_truth):
        found = linked.get(i)
        raw = found.get("details") if found is not None else None
        details: Mapping[str, Any] = raw if isinstance(raw, Mapping) else {}
        target = details.get("target")
        target = target if isinstance(target, str) else None
        templates = _text_tuple(details.get("templates"))
        if event.cls is InjectedClass.C1:
            name = (event.template_id or "").lower()
            templates = (name,) if name else None
        elif event.cls is InjectedClass.C3 and templates is None:
            templates = C3_EVENT_TEMPLATES.get(event.subtype)
        out.append(EventContext(templates, target))
    return out


def _alert_template(alert: Alert) -> str:
    return str(getattr(alert.tau, "value", alert.tau)).lower()


def event_templates(
    event: GroundTruthEvent, ctx: EventContext
) -> tuple[str, ...] | None:
    """The templates an event can violate (lower case): the ``template_id`` of a C1 event, else the templates of its context
    (None: unconstrained)."""
    if event.cls is InjectedClass.C1:
        return ((event.template_id or "").lower(),)
    return ctx.templates


def _in_scope(target: str | None, template: str) -> bool:
    if target is None:
        return True
    if target in BLE_DEVICES:
        return target in DATA_SCOPE.get(template, ())
    if target == _ROBOT:
        return template in ROBOT_SCOPE
    return True


def _compatible(
    alert: Alert,
    event: GroundTruthEvent,
    ctx: EventContext,
    *,
    labelling: str,
    after_ms: int,
) -> bool:
    template = _alert_template(alert)
    allowed = event_templates(event, ctx)
    if allowed is not None and template not in allowed:
        return False
    ref = _first_decidable(event)
    end = event.end_ms if event.end_ms is not None else event.onset_ms
    slack = after_ms
    if labelling == "tight" and event.cls is InjectedClass.C2:
        if not _in_scope(ctx.target, template):
            return False
        slack = 0
    return ref <= alert.t_ms <= max(ref, end) + slack


def _point_ambiguity(
    alert: Alert,
    compatible_loose: Sequence[tuple[int, GroundTruthEvent]],
    compatible_tight: Sequence[tuple[int, GroundTruthEvent]],
    contexts: Sequence[EventContext],
) -> list[GroundTruthEvent]:
    """The injected C2 events that the loose rule accepts and the tight rule rejects only by TIME (scope passes)."""
    tight_ids = {i for i, _ in compatible_tight}
    template = _alert_template(alert)
    return [
        e
        for i, e in compatible_loose
        if e.cls is InjectedClass.C2
        and e.injected
        and i not in tight_ids
        and _in_scope(contexts[i].target, template)
    ]


def _cause_of(
    compatible: Sequence[tuple[int, GroundTruthEvent]],
) -> tuple[int, GroundTruthEvent] | None:
    """The event that gives the class and subtype of the alert, or None when the alert is ambiguous."""
    classes = {e.cls for _, e in compatible}
    chosen: list[tuple[int, GroundTruthEvent]]
    if len(classes) == 1:
        chosen = list(compatible)
    else:
        injected = [(i, e) for i, e in compatible if e.injected]
        if len({e.cls for _, e in injected}) != 1:
            return None
        chosen = injected
    return min(
        chosen, key=lambda item: (not item[1].injected, item[1].onset_ms, item[0])
    )


def label_alerts(
    gt: Sequence[GroundTruthEvent],
    det: Sequence[object],
    contexts: Sequence[EventContext] | None,
    *,
    labelling: str,
    loose_after_ms: int,
    patient_id: str,
    effects: str = "fold",
) -> LabelResult:
    """Label the VIOLATED alerts among ``det`` with their cause (module docstring); ``contexts`` aligns with ``gt``.

    ``loose_after_ms`` has no default (``awaiting_human_value`` in the run options). ``effects`` is ``fold`` (a cascade effect is
    left out) or ``include``."""
    if labelling not in LABELLINGS:
        raise ValueError(f"labelling must be one of {LABELLINGS}, got {labelling!r}")
    if effects not in EFFECT_POLICIES:
        raise ValueError(f"effects must be one of {EFFECT_POLICIES}, got {effects!r}")
    if (
        isinstance(loose_after_ms, bool)
        or not isinstance(loose_after_ms, int)
        or loose_after_ms < 0
    ):
        raise ValueError(
            f"loose_after_ms must be a non-negative integer, got {loose_after_ms!r}"
        )
    ctxs = list(contexts) if contexts is not None else [EventContext()] * len(gt)
    if len(ctxs) != len(gt):
        raise ValueError("contexts must align with the ground truth")
    excluded = dict.fromkeys(_EXCLUDED_KEYS, 0)
    ambiguous: list[AmbiguousAlert] = []
    out: list[LabelledAlert] = []
    for item in det:
        if not isinstance(item, Alert):
            excluded["not_an_alert"] += 1
            continue
        if item.verdict is VerdictState.PREDICTED_VIOLATION:
            excluded["predicted_violation"] += 1
            continue
        if item.caused_by is not None and effects == "fold":
            excluded["cascade_effect"] += 1
            continue
        compatible = [
            (i, e)
            for i, e in enumerate(gt)
            if _compatible(
                item, e, ctxs[i], labelling=labelling, after_ms=loose_after_ms
            )
        ]
        if labelling == "tight":
            loose_set = [
                (i, e)
                for i, e in enumerate(gt)
                if _compatible(
                    item, e, ctxs[i], labelling="loose", after_ms=loose_after_ms
                )
            ]
            lost = _point_ambiguity(item, loose_set, compatible, ctxs)
            if lost:
                loose_cause = _cause_of(loose_set)
                ambiguous.append(
                    AmbiguousAlert(
                        patient_id,
                        item,
                        _alert_template(item),
                        tuple(sorted({e.subtype for e in lost})),
                        None if loose_cause is None else loose_cause[1].cls.value,
                        None if loose_cause is None else loose_cause[1].subtype,
                    )
                )
                excluded["ambiguous"] += 1
                continue
        if not compatible:
            excluded["no_compatible_event"] += 1
            continue
        cause = _cause_of(compatible)
        if cause is None:
            excluded["class_conflict"] += 1
            continue
        index, event = cause
        out.append(
            LabelledAlert(
                patient_id,
                item,
                _alert_template(item),
                event.cls.value,
                event.subtype,
                index,
                event.injected,
                len(compatible),
            )
        )
    return LabelResult(tuple(out), excluded, tuple(ambiguous))


def both_labellings(
    gt: Sequence[GroundTruthEvent],
    det: Sequence[object],
    contexts: Sequence[EventContext] | None,
    *,
    loose_after_ms: int,
    patient_id: str,
    effects: str = "fold",
) -> dict[str, LabelResult]:
    """The same alerts under both labellings, TIGHT (primary) first and LOOSE next to it."""
    return {
        name: label_alerts(
            gt,
            det,
            contexts,
            labelling=name,
            loose_after_ms=loose_after_ms,
            patient_id=patient_id,
            effects=effects,
        )
        for name in LABELLINGS
    }


def subtype_alert_table(
    results: Mapping[str, LabelResult], injected_subtypes: Sequence[str]
) -> dict[str, dict[str, int]]:
    """Injected subtype x alert count under the TIGHT label, the AMBIGUOUS bucket of the tight labelling and the LOOSE label, ZEROS
    SHOWN (a subtype with no tight alert is visible). ``results`` has the keys ``tight`` and ``loose``."""
    table: dict[str, dict[str, int]] = {}
    for name in injected_subtypes:
        table[name] = {
            "tight": sum(
                1 for x in results["tight"].labelled if x.true_subtype == name
            ),
            "ambiguous": sum(
                1 for a in results["tight"].ambiguous if name in a.injected_subtypes
            ),
            "loose": sum(
                1 for x in results["loose"].labelled if x.true_subtype == name
            ),
        }
    return table


def ambiguous_summary(
    ambiguous: Sequence[AmbiguousAlert],
) -> dict[str, dict[str, Any]]:
    """The AMBIGUOUS alerts per injected subtype with the count of their LOOSE labels (``class/subtype``, or ``none``)."""
    out: dict[str, dict[str, Any]] = {}
    for item in ambiguous:
        label = (
            "none"
            if item.loose_class is None
            else f"{item.loose_class}/{item.loose_subtype}"
        )
        for name in item.injected_subtypes:
            entry = out.setdefault(name, {"n": 0, "loose_labels": {}})
            entry["n"] += 1
            entry["loose_labels"][label] = entry["loose_labels"].get(label, 0) + 1
    return {k: out[k] for k in sorted(out)}


#: the type of the optional detector hook that supplies the inputs of an alert: ``(patient_id, alert) -> AlertInputs | None``
InputSource = Callable[[str, Alert], "AlertInputs | None"]
