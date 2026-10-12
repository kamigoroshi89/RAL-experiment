"""The text of ``Explanation.text``: a deterministic English rendering for nursing staff.

Specification: docs/formal/07-alert-tuple-mapping.md section 3.4 (requirements 1 to 14), section 3.3 (the template
names in plain words) and docs/models/attribution-rule.md (section Abstention, what the text must say for each
reason; section Action policy). The text is specification-level traceability: it names the violated template
instance, the clinical parameters, the margin, the confidence with its kind and declared guarantee, the attributed
cause and the evidence fields that decided it. It is not an explanation of the cause, not a proof that the rule is
right, and nobody has tested whether it is understood (the vignette study of WS11 is that check).

The text is a plain function of the alert, its record, the decision of the rule and the template: no clock, no
locale, no dictionary order (TR-4). Numbers are formatted with fixed formats, parameters are listed in the order
of ``Template.params``, evidence in the precedence order of the decision. A registry value whose entry has
``reviewed_by`` null carries the label "unreviewed" (ADR-020). The text states no clinical recommendation: the
only actions it names are the automatic robot actions of the action policy (stop, retry, call), and it says that
clinical actions are never automatic.

A decision of the likelihood attributor (``Decision.p_kappa`` is set, ADR-074) is rendered by ``_cause_likelihood``:
the class posterior, the declared threshold, the evidence fields that favour the leading class with their readings,
and the set of subtypes; an UNDETERMINED label names every subtype applicable to the constraint. The posterior comes
from a likelihood table whose numbers are sensitivity values, and the text says that it is not a measured frequency.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Final

from ralmon.attribution.alert import Alert, AttributedCause
from ralmon.attribution.likelihood import NUMERICAL_ZERO
from ralmon.attribution.rule import AbstentionReason, Decision
from ralmon.monitor import (
    MonitorConfigError,
    MonitorInputError,
    VerdictRecord,
    VerdictState,
    resolve_subformula_paths,
)
from ralmon.signals import MS_PER_HOUR, MS_PER_MINUTE, MS_PER_SECOND, TimeMs
from ralmon.spec import ParameterRegistry, RhoKind, Template, TemplateId

__all__ = ["render_text"]

_MS_PER_DAY: Final = 24 * MS_PER_HOUR

#: Section 3.3 of docs/formal/07-alert-tuple-mapping.md, derived from the contract comments of ``TemplateId``.
TEMPLATE_WORDS: Final[dict[TemplateId, str]] = {
    TemplateId.RANGE: "the measured blood pressure inside the prescribed band",
    TemplateId.SCHED: "a blood pressure measurement within the allowed time after the scheduled time",
    TemplateId.HOLD: "no dose dispensed while the latest blood pressure is below the hold threshold",
    TemplateId.COUNT: "the number of doses dispensed in 24 hours within the prescribed limit, and the day-end count obligation",
    TemplateId.RESP: "the prescribed blood pressure decrease, measured in the response window after a dose, relative to the pre-dose reference",
    TemplateId.SYS: "a measurement taken with a healthy cuff node and an acceptable inflation time",
    TemplateId.INT: "a dispense backed by robot-observed presence or by an authenticated event",
}

#: The evidence fields in plain words (the canonical path follows in parentheses in the text).
FIELD_WORDS: Final[dict[str, str]] = {
    "system.node_lifecycle": "status of the monitored nodes",
    "system.diagnostics_ok": "diagnostics of the monitored nodes",
    "system.liveliness_ok": "liveliness of the monitored nodes",
    "system.qos_deadline_missed": "message deadlines of the monitored streams",
    "system.ble_link_quality": "delivery ratio of the device link",
    "system.battery_low": "robot battery",
    "system.nav_task_failed": "robot navigation outcome",
    "system.manip_task_failed": "robot manipulation outcome",
    "system.seq_gap": "missing message sequence values",
    "signal_quality.ecg_sqi": "ECG signal quality",
    "signal_quality.ppg_sqi": "pulse-oximeter signal quality",
    "signal_quality.cuff_error_code": "cuff error code",
    "signal_quality.cuff_value_repeated": "repeat of the previous cuff reading",
    "cross_device.pulse_vs_ecg_hr_diff": "agreement between the cuff pulse rate and the ECG heart rate",
    "witness.robot_present": "patient presence perceived by the robot",
    "witness.identity_confirmed": "patient identity check by the robot",
    "witness.intake_observed": "intake observed by the robot",
    "crypto_temporal.authenticated": "message authentication",
    "crypto_temporal.seq_repeat": "repeated message sequence numbers",
    "crypto_temporal.timestamp_implausible": "message timestamps",
    "dispenser.interval_since_previous_ms": "interval since the previous dispenser opening",
    "dispenser.content_change": "dispenser content change at the opening",
}

#: What anchors an instance (docs/formal/02-templates.md section 3.1): DISPENSE is the dispenser opened, not INTAKE.
_ANCHOR_KIND: Final[dict[TemplateId, str]] = {
    TemplateId.RANGE: "measurement",
    TemplateId.SYS: "measurement",
    TemplateId.SCHED: "scheduled tick",
    TemplateId.HOLD: "dispense event",
    TemplateId.COUNT: "dispense event",
    TemplateId.RESP: "dispense event",
    TemplateId.INT: "dispense event",
}

_CONFLICT_WHY: Final[dict[str, str]] = {
    "system.node_lifecycle": "a deliberate transition is not a failure and does not allow a clinical cause",
    "system.ble_link_quality": "a loss that does not degrade the link is not an explanation",
    "system.seq_gap": "a loss that does not degrade the link is not an explanation",
    "crypto_temporal.seq_repeat": "a loss that does not degrade the link is not an explanation",
    "crypto_temporal.timestamp_implausible": "a late or future-stamped input has several causes",
    "witness.identity_confirmed": "a witness reading is not backing",
    "witness.intake_observed": "a witness reading is not backing",
}

_CAUSE_WORDS: Final[dict[AttributedCause, str]] = {
    AttributedCause.C1_CLINICAL: "clinical or adherence deviation",
    AttributedCause.C2_SYSTEM: "system or embodiment failure",
    AttributedCause.C3_INTEGRITY: "integrity or plausibility violation",
    AttributedCause.UNDETERMINED: "not determined",
}

#: The action policy (attribution-rule.md, section Action policy): only these automatic robot actions exist.
_ACTIONS: Final[dict[AttributedCause, str]] = {
    AttributedCause.C1_CLINICAL: "call (notify the nurse)",
    AttributedCause.C2_SYSTEM: (
        "stop of the robot's own operation when the decisive evidence is about the robot, "
        "retry of a failed robot task, and call"
    ),
    AttributedCause.C3_INTEGRITY: (
        "call, and stop of a robot task that depends on the suspect input"
    ),
    AttributedCause.UNDETERMINED: "call (ask the nurse to verify)",
}


def _number(value: float) -> str:
    if value == 0:
        return "0"
    if float(value).is_integer() and abs(value) < 1e15:
        return str(int(value))
    return f"{value:.4g}"


def _quantity(value: float, unit: str) -> str:
    """A value with its unit in plain words (``140 mmHg``, ``30 minutes``, ``2 doses``)."""
    if unit == "ms" and math.isfinite(value):
        ms = int(value)
        if ms % MS_PER_MINUTE == 0:
            n = ms // MS_PER_MINUTE
            return f"{n} {'minute' if abs(n) == 1 else 'minutes'}"
        if ms % MS_PER_SECOND == 0:
            n = ms // MS_PER_SECOND
            return f"{n} {'second' if abs(n) == 1 else 'seconds'}"
        return f"{ms} ms"
    if unit == "dose":
        return f"{_number(value)} {'dose' if abs(value) == 1 else 'doses'}"
    if unit == "1":
        return _number(value)
    return f"{_number(value)} {unit}"


def _clock(t_ms: TimeMs) -> str:
    day, rest = divmod(t_ms, _MS_PER_DAY)
    hh = rest // MS_PER_HOUR
    mm = (rest // MS_PER_MINUTE) % 60
    suffix = f" (day +{day})" if day else ""
    return f"{hh:02d}:{mm:02d}{suffix}"


def _unreviewed(registry: ParameterRegistry, name: str) -> str:
    return " (unreviewed)" if registry.get(name).reviewed_by is None else ""


def _state_word(token: str) -> str:
    if token.endswith("+commanded"):
        return f"{token[: -len('+commanded')]} (commanded)"
    return token


def _reading_words(path: str, value: object) -> str | None:
    """The actual reading of a field in words (evidence-channels.md, section Field semantics), or ``None``.

    The words state the value, not only the name of the field: a failed check, an intake that was not seen and a
    lapse are written as such, so that "no intake observed" is never read as "intake observed" (ADR-004).
    """
    if path == "system.node_lifecycle" and isinstance(value, tuple):
        entries = ", ".join(f"{node} {_state_word(state)}" for node, state in value)
        return f"node status reported: {entries}"
    if isinstance(value, bool):
        pair = _BOOLEAN_WORDS.get(path)
        return None if pair is None else pair[0 if value else 1]
    if isinstance(value, str) and path == "signal_quality.cuff_error_code":
        return (
            f"the cuff reported error code {value}"
            if value
            else "the cuff reported no error code"
        )
    if isinstance(value, (int, float)) and math.isfinite(value):
        if path == "dispenser.interval_since_previous_ms":
            return f"interval since the previous dispenser opening {_number(float(value))} ms"
        if path == "dispenser.content_change":
            return f"dispenser content change {_number(float(value))} at the opening"
        if path == "system.ble_link_quality":
            return f"delivery ratio of the device link {value:.2f}"
        if path == "signal_quality.ecg_sqi":
            return f"ECG signal quality {value:.2f}"
        if path == "signal_quality.ppg_sqi":
            return f"pulse-oximeter signal quality {value:.2f}"
        if path == "cross_device.pulse_vs_ecg_hr_diff":
            return (
                "the cuff pulse rate and the ECG heart rate differ by "
                f"{_number(float(value))} beats per minute"
            )
    return None


#: (words when the field is True, words when it is False) for the Boolean fields.
_BOOLEAN_WORDS: Final[dict[str, tuple[str, str]]] = {
    "system.diagnostics_ok": (
        "diagnostics reported ok",
        "diagnostics reported an error or a stale report",
    ),
    "system.liveliness_ok": (
        "no liveliness lapse of a monitored node",
        "the liveliness of a monitored node lapsed",
    ),
    "system.qos_deadline_missed": (
        "a message deadline was missed",
        "no message deadline was missed",
    ),
    "system.battery_low": (
        "the robot battery was reported low",
        "the robot battery was not reported low",
    ),
    "system.nav_task_failed": (
        "a robot navigation task failed, timed out or was late",
        "the robot navigation tasks succeeded",
    ),
    "system.manip_task_failed": (
        "a robot manipulation task failed, timed out or was late",
        "the robot manipulation tasks succeeded",
    ),
    "witness.robot_present": (
        "the robot perceived the patient present",
        "the robot did not perceive the patient present",
    ),
    "witness.identity_confirmed": (
        "the robot confirmed the patient identity",
        "the robot identity check failed",
    ),
    "witness.intake_observed": (
        "intake observed by the robot",
        "no intake observed by the robot",
    ),
    "crypto_temporal.authenticated": (
        "message authentication succeeded",
        "message authentication failed",
    ),
    "signal_quality.cuff_value_repeated": (
        "the cuff reading equals the previous reading of the same cuff",
        "the cuff reading differs from the previous reading of the same cuff",
    ),
    "system.seq_gap": (
        "a missing sequence value was found",
        "no missing sequence value was found",
    ),
    "crypto_temporal.seq_repeat": (
        "a repeated sequence value was found",
        "no repeated sequence value was found",
    ),
    "crypto_temporal.timestamp_implausible": (
        "a late or future-stamped message was received",
        "no late or future-stamped message was received",
    ),
}


def _evidence_list(
    paths: Sequence[str], readings: Sequence[tuple[str, object]] = ()
) -> str:
    """The fields with their reading in words and the canonical path in parentheses."""
    values = dict(readings)
    out: list[str] = []
    for path in paths:
        words = _reading_words(path, values[path]) if path in values else None
        out.append(
            f"{words if words is not None else FIELD_WORDS.get(path, path)} ({path})"
        )
    return ", ".join(out)


def _unavailable_list(paths: Sequence[str]) -> str:
    return ", ".join(f"{FIELD_WORDS.get(p, p)} unavailable ({p})" for p in paths)


def render_text(
    alert: Alert,
    record: VerdictRecord,
    decision: Decision,
    template: Template,
    registry: ParameterRegistry,
    *,
    anchor_ms: TimeMs | None = None,
    variant: str | None = None,
) -> str:
    """The text of an alert, regenerated from the alert, its record, the decision and the template (TR-4)."""
    predicted = alert.verdict is VerdictState.PREDICTED_VIOLATION
    words = TEMPLATE_WORDS[alert.tau]
    parts: list[str] = []

    # 1. the template in plain words and the verdict state (requirements 1, 5 and 9)
    if predicted:
        kind = f"a {variant}-violation early warning" if variant else "an early warning"
        parts.append(
            f'Predicted violation of the constraint "{words}": this is {kind}, '
            "not a definitive verdict."
        )
    else:
        parts.append(f'Violation of the constraint "{words}".')

    # 2. the instance and the times (requirement 2)
    where = (
        f"instance {alert.xi.instance_key} (anchored by the {_ANCHOR_KIND[alert.tau]}"
    )
    if anchor_ms is not None:
        where += f" at {_clock(anchor_ms)}"
    where += ")"
    if predicted:
        parts.append(f"Predicted at {_clock(alert.t_ms)} for {where}.")
    else:
        parts.append(
            f"This is a violated (definitive) verdict, decided at {_clock(alert.t_ms)} for {where}."
        )

    # the violated sub-formula(s), decisive first, when the record carries a path that resolves
    formulas = _sub_formulas(record, template)
    if formulas:
        parts.append(
            "Violated sub-formula: "
            + formulas[0]
            + (
                "; also violated: " + "; ".join(formulas[1:])
                if len(formulas) > 1
                else ""
            )
            + "."
        )

    # 3. the clinical parameters with units (requirement 3)
    items = [
        f"{name} {_quantity(value, registry.get(name).unit)}{_unreviewed(registry, name)}"
        for name, value in _ordered_params(alert, template)
    ]
    if items:
        parts.append("Clinical parameters used: " + ", ".join(items) + ".")

    # 4. the margin or the predicted bound (requirements 7, 8, 9)
    scale = registry.get(template.scale_param)
    scale_text = f"{_quantity(scale.value, scale.unit)}{_unreviewed(registry, template.scale_param)}"
    unit = template.unit.value
    if predicted:
        bound = f"Predicted severity bound: {alert.sigma_norm:.2f} on the normalised scale of {scale_text}"
        if variant == "possible":
            bound += ", the value at the pessimistic end of the range"
        elif variant == "likely":
            bound += ", at least this severe"
        parts.append(bound + ".")
    else:
        upper = record.sigma_interval.hi
        if math.isfinite(upper):
            label = (
                "Certified bound of the margin"
                if alert.tau is TemplateId.SCHED
                else "Margin"
            )
            parts.append(
                f"{label}: {_quantity(upper, unit)} (native unit); normalised {alert.sigma_norm:.2f} "
                f"of the registry scale of {scale_text}."
            )
        else:
            guard = getattr(record, "guard_failed", None)
            marker = (
                f" (failed guard: {guard})" if isinstance(guard, str) and guard else ""
            )
            parts.append(
                f"Margin: not defined, a required observation is missing{marker}; normalised "
                f"{alert.sigma_norm:.2f} of the registry scale of {scale_text}."
            )
        if alert.tau is TemplateId.SCHED:
            if math.isfinite(upper):
                parts.append(
                    "The measurement was not taken by the deadline; a measurement taken later will count "
                    "as late by at least one monitor step."
                )
            else:
                parts.append(
                    "The measurement was not taken by the deadline; the severity is the maximum of the scale."
                )

    # 5. the confidence with its kind and declared guarantee (requirement 7)
    parts.append(_confidence(alert, predicted))

    # 6. the attributed cause and the evidence (requirements 4 and 6)
    parts.append(_cause(alert, decision, predicted))

    # 7. the action policy
    parts.append(
        f"Automatic robot actions allowed for this cause: {_ACTIONS[alert.kappa]}. "
        "Clinical actions are never automatic; the clinician confirms them."
    )

    # 8. the priority (unreviewed labels, requirement 14)
    reviewed = registry.get(template.priority_param).reviewed_by is not None
    parts.append(
        f"Priority {alert.priority} ("
        + ("" if reviewed else "unreviewed; ")
        + "1 is the highest)."
    )

    # 9. cascades (requirement 11)
    if alert.caused_by is not None:
        parts.append(
            f"This alert follows from, or shares its cause with, alert {alert.caused_by}."
        )
    elif alert.root_cause_of:
        n = len(alert.root_cause_of)
        parts.append(
            f"This alert also accounts for {n} further violation{'s' if n != 1 else ''}."
        )
    return " ".join(parts)


def _sub_formulas(record: VerdictRecord, template: Template) -> tuple[str, ...]:
    """The canonical text of the sub-formulas that ``record.subformula_path`` names (empty if there is none)."""
    path = getattr(record, "subformula_path", None)
    if not isinstance(path, str) or not path:
        return ()
    try:
        return resolve_subformula_paths(template, path)
    except (MonitorInputError, MonitorConfigError):
        return ()  # a path that does not resolve is not a reason to lose the alert


def _ordered_params(alert: Alert, template: Template) -> list[tuple[str, float]]:
    values = alert.xi.param_values
    names = [n for n in template.params if n in values]
    names += sorted(n for n in values if n not in template.params)
    return [(n, float(values[n])) for n in names]


def _confidence(alert: Alert, predicted: bool) -> str:
    rho = alert.rho
    if rho is None:
        return "Confidence: not available (no probability was given for this check)."
    kind = {
        RhoKind.MEASURED: "measured",
        RhoKind.PREDICTED: "predicted",
        RhoKind.DETERMINISTIC: "deterministic",
    }[rho.kind]
    if predicted:
        return (
            f"Confidence: {rho.value:.2f} (kind: {kind}; a conformal score whose guarantee is marginal over "
            f"patient episodes under exchangeability, declared guarantee: {rho.guarantee}); "
            "it is not the probability that the violation will occur."
        )
    return f"Confidence: {rho.value:.2f} (kind: {kind}; guarantee: {rho.guarantee})."


_CLASSES: Final = (
    AttributedCause.C1_CLINICAL,
    AttributedCause.C2_SYSTEM,
    AttributedCause.C3_INTEGRITY,
)


def _cause_likelihood(alert: Alert, decision: Decision) -> str:
    """The cause of a likelihood decision: probabilities, threshold, favouring evidence, set of subtypes."""
    posterior = decision.p_kappa
    subtypes = decision.posterior_subtypes
    assert posterior is not None and subtypes is not None
    kappa = alert.kappa
    tau = decision.abstention_threshold
    classes = ", ".join(f"{c.value} {posterior[c]:.2f}" for c in _CLASSES)
    best = max(_CLASSES, key=lambda c: (posterior[c], -_CLASSES.index(c)))
    tied = [c for c in _CLASSES if posterior[c] >= posterior[best] - NUMERICAL_ZERO]
    head = f"Attributed cause: {_CAUSE_WORDS[kappa]}"
    table_note = (
        "The posterior comes from a likelihood table whose numbers are sensitivity values; it is not a "
        "measured frequency."
    )
    if kappa is AttributedCause.UNDETERMINED:
        if len(tied) > 1:
            names = " and ".join(
                [", ".join(c.value for c in tied[:-1]), tied[-1].value]
            )
            why = f"{names} share the largest posterior ({posterior[best]:.2f})"
            if tau is not None and posterior[best] < tau:
                why += f", which is also below the declared threshold tau {tau:.2f}"
        else:
            why = (
                f"the largest class posterior ({best.value} {posterior[best]:.2f}) is below the declared "
                f"threshold tau {tau:.2f}"
                if tau is not None
                else "no class posterior reaches the declared threshold"
            )
        text = (
            f"{head}. Reason: {why}. Class posterior: {classes}. No class is attributed, so every one of "
            f"the {len(subtypes)} subtypes applicable to this constraint remains possible: "
            + ", ".join(sorted(subtypes))
            + f". {table_note}"
        )
        lead = f"the class with the largest posterior ({_CAUSE_WORDS[best]})"
    else:
        threshold = (
            f" the declared threshold tau {tau:.2f}"
            if tau is not None
            else " the declared threshold"
        )
        text = (
            f"{head}, class posterior {classes}: the most probable class, and its posterior reaches{threshold}. "
            f"{table_note}"
        )
        lead = "this class"
    if decision.evidence_used:
        text += (
            f" Evidence that favours {lead} over the others, most favourable first: "
            + _evidence_list(decision.evidence_used, decision.readings)
            + "."
        )
    if kappa is AttributedCause.C1_CLINICAL:
        text += (
            " Silent device faults raise none of the channels read, so this does not exclude them: "
            "see the set of subtypes."
        )
    if alert.cause_set:
        text += (
            " Most probable subtypes (the set reported): "
            + ", ".join(
                f"{name} {subtypes[name]:.2f}" if name in subtypes else name
                for name in alert.cause_set
            )
            + "."
        )
    return text


def _cause(alert: Alert, decision: Decision, predicted: bool) -> str:
    kappa = alert.kappa
    head = f"Attributed cause: {_CAUSE_WORDS[kappa]}"
    if predicted:
        return head + " (an early warning names no cause)."
    if decision.p_kappa is not None:
        return _cause_likelihood(alert, decision)
    if kappa is AttributedCause.C1_CLINICAL:
        return (
            head
            + ", because no system or integrity evidence was found and every channel required for the "
            "exclusion was available and showed no problem. Channels checked: "
            + _evidence_list(decision.evidence_used, decision.readings)
            + "."
        )
    if kappa in (AttributedCause.C2_SYSTEM, AttributedCause.C3_INTEGRITY):
        return (
            head
            + ", because of the evidence: "
            + _evidence_list(decision.evidence_used, decision.readings)
            + "."
        )
    reason = decision.reason
    if reason is AbstentionReason.CONFLICT:
        why = sorted({_CONFLICT_WHY.get(p, "") for p in decision.evidence_used} - {""})
        return (
            head
            + ". Reason: conflicting evidence. Readings that neither the integrity rule nor the system rule "
            "accepts: "
            + _evidence_list(decision.evidence_used, decision.readings)
            + " ("
            + "; ".join(why)
            + ")."
        )
    if reason is AbstentionReason.PROVENANCE_ONLY:
        return (
            head
            + ". Reason: the system or integrity constraint is violated and no other channel corroborates "
            "a cause."
        )
    text = (
        head
        + ". Reason: insufficient evidence, the channels needed to exclude the other causes were not available"
    )
    if decision.missing:
        text += ": " + _unavailable_list(decision.missing)
    if alert.tau is TemplateId.COUNT:
        text += "; the dispenser content evidence has no field in this contract version"
    return text + "."
