"""``RuleAttributor``: violated records to alerts, with cascade root-cause propagation.

Specification: docs/models/attribution-rule.md (sections Inputs and outputs, Cascades and root-cause propagation,
Predicted violations) and docs/formal/07-alert-tuple-mapping.md sections 1.4, 1.7 and 1.8.

``attribute_all`` is stateless and deterministic and returns the *current set*, one alert per ``xi.instance_key``,
ordered by ``rank_alerts``:

* an alert is built for a record that claims a violation (VIOLATED or PREDICTED_VIOLATION); a PENDING or SATISFIED
  record makes none. The alert is a function of the first VIOLATED record of the instance and of the evidence at its
  cut-off; a later record of the same key (a refinement) changes nothing;
* a PREDICTED_VIOLATION record gives an alert with kappa UNDETERMINED and no decisive evidence, without evaluating
  the rule (CP13, ADR-041 proposed); when the same key has a VIOLATED record, only the VIOLATED alert is returned;
  a prediction whose instance ends SATISFIED is closed and is not in the current set;
* cascades (CT-1 and CT-2): a VIOLATED ``sched`` alert with a definite kappa is the root of the VIOLATED ``resp``
  and ``hold`` alerts whose decisive sub-formula is a failed guard, when the root is decided strictly earlier and its
  interval meets the effect's window. An effect with a definite cause of its own that differs from the root's
  stays top-level. An effect carries the attributed cause and the decisive evidence of its root from its first issue;
  a root lists its effects in ``root_cause_of`` (sorted). Folding hides and never deletes: the effect is returned.

``update`` is the incremental form used by the ROS 2 wrapper: it remembers the records and the alerts, and returns
only the alerts that are new or changed since the previous call (the new ones first, then the re-issued ones). An
alert already issued is frozen: later evidence for its key is ignored, and the only changes of an issued alert are the
growth of ``root_cause_of`` of a root and the sentence of its text derived from it (rules 7 and 8 of the cascade
section). ``history`` holds every issued value in issue order.

The windows of the cascade table (``sched_window``, ``hold_lookback``, ``delta1``, ``delta2``) come from the plan
instance when a plan is given and from the registry otherwise (H-10, OP-AR-3).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from ralmon.attribution.alert import Alert, AttributedCause, alert_from_record
from ralmon.attribution.evidence import (
    EvidenceVector,
    empty_evidence,
    instance_anchor_ms,
)
from ralmon.attribution.rule import (
    AttributionRule,
    Decision,
    HierarchicalRule,
    predicted_decision,
)
from ralmon.monitor import VerdictRecord, VerdictState
from ralmon.signals import DurationMs, TimeMs
from ralmon.spec import (
    CarePlan,
    ParameterRegistry,
    Template,
    TemplateId,
    as_duration_ms,
    as_priority,
    rank_alerts,
)

__all__ = ["Attributor", "RuleAttributor"]


class Attributor(Protocol):
    def attribute_all(
        self, violated: Sequence[VerdictRecord], evidence: Mapping[str, EvidenceVector]
    ) -> Sequence[Alert]: ...

    # propagates root causes over cascades (analisi 4.9 item 3)


_GUARD: dict[TemplateId, str] = {
    TemplateId.RESP: "obligation_unmet",
    TemplateId.HOLD: "no_recent_measurement",
}
_DEFINITE = (
    AttributedCause.C1_CLINICAL,
    AttributedCause.C2_SYSTEM,
    AttributedCause.C3_INTEGRITY,
)


@dataclass(frozen=True, slots=True)
class _Core:
    """What is frozen when the first alert of an instance is issued: the record and its own decision."""

    record: VerdictRecord
    decision: Decision

    @property
    def violated(self) -> bool:
        return self.record.state is VerdictState.VIOLATED

    @property
    def decided(self) -> TimeMs:
        r = self.record
        return r.decided_at_ms if r.decided_at_ms is not None else r.t_eval_ms


class RuleAttributor:
    """The default ``Attributor``: a rule per record, the state check, the cascade table and the ranking."""

    def __init__(
        self,
        registry: ParameterRegistry,
        templates: Sequence[Template],
        rule: AttributionRule | None = None,
        *,
        plan: CarePlan | None = None,
        variant: str | None = None,
    ) -> None:
        self._registry = registry
        self._templates = {t.id: t for t in templates}
        self._rule: AttributionRule = (
            rule if rule is not None else HierarchicalRule(registry)
        )
        self._variant = variant
        self._plan_params: dict[str, Mapping[str, float]] = {}
        self._plan_anchor: dict[str, TimeMs | None] = {}
        if plan is not None:
            for item in plan.instances:
                self._plan_params[item.instance_key] = item.param_values
                self._plan_anchor[item.instance_key] = item.anchor_ms
        # state of ``update``
        self._cores: dict[str, _Core] = {}
        self._issued: dict[str, Alert] = {}
        self._history: list[Alert] = []
        self._closed: list[str] = []
        self._links: dict[str, str | None] = {}

    # ---- public API -------------------------------------------------------------------------------------

    def attribute_all(
        self, violated: Sequence[VerdictRecord], evidence: Mapping[str, EvidenceVector]
    ) -> list[Alert]:
        """The current set of alerts for the records, root causes propagated, in ``rank_alerts`` order."""
        cores: dict[str, _Core] = {}
        self._admit(cores, violated, evidence, closed=[])
        return self._assemble(cores, {})

    def update(
        self, violated: Sequence[VerdictRecord], evidence: Mapping[str, EvidenceVector]
    ) -> list[Alert]:
        """Feed more records; return the alerts that are new or changed since the previous call."""
        closed: list[str] = []
        self._admit(self._cores, violated, evidence, closed=closed)
        for key in closed:
            if key not in self._closed:
                self._closed.append(key)
            self._issued.pop(key, None)
        current = self._assemble(self._cores, self._links)
        new: list[Alert] = []
        changed: list[Alert] = []
        for alert in current:
            key = alert.xi.instance_key
            before = self._issued.get(key)
            if before is None:
                new.append(alert)
            elif before != alert:
                changed.append(alert)
        out = new + changed
        for alert in out:
            key = alert.xi.instance_key
            self._issued[key] = alert
            self._history.append(alert)
            if alert.verdict is VerdictState.VIOLATED and key not in self._links:
                self._links[key] = alert.caused_by
        return out

    @property
    def history(self) -> tuple[Alert, ...]:
        """Every alert issued by ``update``, in issue order (superseded predicted alerts included)."""
        return tuple(self._history)

    @property
    def closed_predictions(self) -> tuple[str, ...]:
        """The keys of predicted alerts whose instance ended SATISFIED (false predictive alarms)."""
        return tuple(self._closed)

    # ---- records to cores ---------------------------------------------------------------------------------

    def _admit(
        self,
        cores: dict[str, _Core],
        records: Sequence[VerdictRecord],
        evidence: Mapping[str, EvidenceVector],
        *,
        closed: list[str],
    ) -> None:
        groups: dict[str, list[VerdictRecord]] = {}
        for record in records:
            groups.setdefault(record.instance_key, []).append(record)
        for key, group in groups.items():
            have = cores.get(key)
            if have is not None and have.violated:
                continue  # frozen: the alert is a function of the first VIOLATED record
            violated = [r for r in group if r.state is VerdictState.VIOLATED]
            if violated:
                first = min(violated, key=lambda r: r.t_eval_ms)
                cores[key] = _Core(first, self._decide(first, evidence.get(key)))
                continue
            if any(r.state is VerdictState.SATISFIED for r in group):
                if cores.pop(key, None) is not None or any(
                    r.state is VerdictState.PREDICTED_VIOLATION for r in group
                ):
                    closed.append(key)
                continue
            if have is None:
                predicted = [
                    r for r in group if r.state is VerdictState.PREDICTED_VIOLATION
                ]
                if predicted:
                    first = min(predicted, key=lambda r: r.t_eval_ms)
                    cores[key] = _Core(first, predicted_decision())

    def _decide(self, record: VerdictRecord, vector: EvidenceVector | None) -> Decision:
        evidence = vector if vector is not None else empty_evidence(record.template)
        rule = self._rule
        decide = getattr(rule, "decide", None)
        if decide is not None:
            result = decide(record, evidence)
            assert isinstance(result, Decision)
            return result
        return Decision(rule.attribute(record, evidence), None, None, (), ())

    # ---- windows and anchors --------------------------------------------------------------------------------

    def _window(self, name: str, key: str) -> DurationMs:
        override = self._plan_params.get(key, {})
        if name in override:
            return int(override[name])
        return as_duration_ms(self._registry.get(name))

    def _anchor(self, record: VerdictRecord) -> TimeMs:
        window: int | None = None
        if record.template is TemplateId.SCHED:
            window = self._window("sched_window", record.instance_key)
        elif record.template is TemplateId.RESP:
            window = self._window("delta2", record.instance_key)
        return instance_anchor_ms(
            record.instance_key,
            record.template,
            decided_at_ms=record.decided_at_ms,
            t_eval_ms=record.t_eval_ms,
            pending_until_ms=record.pending_until_ms,
            window_ms=window,
            plan_anchor_ms=self._plan_anchor.get(record.instance_key),
        )

    def _template(self, template: TemplateId) -> Template:
        try:
            return self._templates[template]
        except KeyError:
            raise ValueError(
                f"the template library has no template {template.value!r}"
            ) from None

    # ---- the cascade table ----------------------------------------------------------------------------------

    @staticmethod
    def _failed_guard(record: VerdictRecord) -> bool:
        """The decisive sub-formula of a ``resp`` or ``hold`` record is the guard of a missing measurement."""
        expected = _GUARD.get(record.template)
        if expected is None:
            return False
        marker = getattr(record, "guard_failed", None)
        if marker is not None:
            return bool(marker == expected)
        path = getattr(record, "subformula_path", None)
        if isinstance(path, str) and path:
            return path.split(";", 1)[0].rsplit("/", 1)[-1] == expected
        # until a carrier exists the property is read from the record: the upper end is minus infinity exactly
        # for a failed guard (T02 section 2.1, H-11); it enters the choice of links, never kappa
        return record.sigma_interval.hi == -math.inf

    def _meets(self, root: _Core, effect: _Core) -> bool:
        """CT-1 and CT-2: the root interval meets the response window or the look-back of the effect."""
        key = effect.record.instance_key
        root_lo = root.decided - self._window("sched_window", root.record.instance_key)
        if effect.record.template is TemplateId.RESP:
            span = self._window("delta2", key) - self._window("delta1", key)
        else:
            span = self._window("hold_lookback", key)
        effect_lo = effect.decided - span
        return root_lo <= effect.decided and effect_lo <= root.decided

    def _links_of(self, cores: Mapping[str, _Core]) -> dict[str, str]:
        roots = [
            (key, core)
            for key, core in cores.items()
            if core.violated
            and core.record.template is TemplateId.SCHED
            and core.decision.kappa in _DEFINITE
        ]
        links: dict[str, str] = {}
        for key, core in cores.items():
            if not core.violated or core.record.template not in _GUARD:
                continue
            if not self._failed_guard(core.record):
                continue  # independent evidence: a valid measurement exists in its window (rule 3)
            eligible = [
                (rkey, root)
                for rkey, root in roots
                if root.decided < core.decided and self._meets(root, core)
            ]
            if not eligible:
                continue
            rkey, root = min(
                eligible,
                key=lambda item: (
                    item[1].decided,
                    as_priority(
                        self._registry.get(
                            self._template(item[1].record.template).priority_param
                        )
                    ),
                    item[0],
                ),
            )
            own = core.decision.kappa
            if own in _DEFINITE and own is not root.decision.kappa:
                continue  # independent evidence (rule 4): its own result decides
            links[key] = rkey
        return links

    # ---- alerts -------------------------------------------------------------------------------------------

    def _assemble(
        self, cores: Mapping[str, _Core], frozen: Mapping[str, str | None]
    ) -> list[Alert]:
        computed = self._links_of(cores)
        links: dict[str, str] = {}
        for key in cores:
            link = frozen[key] if key in frozen else computed.get(key)
            if link is not None and link in cores:
                links[key] = link
        effects: dict[str, list[str]] = {}
        for effect, root in links.items():
            effects.setdefault(root, []).append(effect)
        alerts: list[Alert] = []
        for key, core in cores.items():
            record = core.record
            decision = core.decision
            caused_by = links.get(key)
            if caused_by is not None:
                decision = cores[caused_by].decision
            alerts.append(
                alert_from_record(
                    record,
                    decision,
                    self._template(record.template),
                    self._registry,
                    param_values=self._plan_params.get(key),
                    anchor_ms=self._anchor(record),
                    variant=self._variant,
                    caused_by=caused_by,
                    root_cause_of=tuple(sorted(effects.get(key, ()))),
                )
            )
        return rank_alerts(alerts)
