---
id: WS02-T04
title: "Attribution rule spec: hierarchy, abstention, cascades, clinician-in-the-loop"
workstream: WS02-threat-fault-model
owner: agent
status: ready
depends_on: ["WS02-T03", "WS01-T07"]
critical_path: true
non_negotiable: false
estimate_pd: 2
sources: ["analisi §4.5", "analisi §4.9 (3, 4)", "analisi §4.6", "analisi §4.8", "analisi §2 R3 weakness 4"]
interfaces: ["02-interfaces.md#attribution"]
review_items: ["R2-W7", "R3-W4"]
---
## Obiettivo

Write `docs/models/attribution-rule.md`, the normative specification of `HierarchicalRule.attribute` and `Attributor.attribute_all` from the `Attribution` contract. It defines, in terms of the 20 `EvidenceVector` fields: the evidence predicates, the hierarchical decision table (integrity evidence gives C3, otherwise system evidence gives C2, otherwise a violation with coherent channels gives C1, otherwise UNDETERMINED), the per-template conditions for claiming C1 by exclusion, cascade root-cause propagation (analisi §4.9 item 3), and the clinician-in-the-loop principle with autonomy limited to robot actions (analisi §4.9 item 4). It ends with test-ready invariants and worked cases that WS05-T07 lifts into pytest fixtures. It closes R2 weakness 7 (κ is not derived from low ρ) and R3 weakness 4 (taxonomy and safety actions).

## Contesto

Blocked until WS02-T03 and WS01-T07 are done; the WS01-T07 output defines the alert tuple fields and the traceability wording that `Explanation` must follow.

- `docs/models/evidence-channels.md` (output of WS02-T03: field semantics, polarity, channel identifiers, A4 mask, decisions D-1 to D-8, gaps).
- `docs/source/analisi.md` §4.5 (six groups, hierarchical rule, matrix rows 1 to 10), §4.6 (row 15:00 cascade), §4.9 items 3 and 4.
- `docs/plan/02-interfaces.md#attribution` (rule signatures and the four-step default rule).
- `docs/plan/02-interfaces.md#alert` (`AttributedCause`, `Alert.caused_by`, `Alert.root_cause_of`, `Explanation.evidence_used`).
- `docs/plan/03-decisions.md` ADR-010 (hierarchical rules with abstention) and ADR-003 (fallback to the nurse when the robot is unavailable).

## File toccati

- `docs/models/attribution-rule.md` (create).

## Test

Document task: verification checks a reviewer can run or inspect.

1. Required H2 headings, in this order: `## Inputs and outputs`, `## Evidence predicates`, `## Decision table`, `## C1 exclusion conditions`, `## Abstention`, `## Cascades and root-cause propagation`, `## Predicted violations`, `## Action policy`, `## Invariants`, `## Worked cases`, `## Traceability`.
2. `## Inputs and outputs` states that κ is a function of `provenance.violated_template`, `provenance.template_kind` and the other 18 fields only; that ρ, σ̃, `VerdictRecord.state` and time are not inputs (R2 weakness 7: low confidence is not evidence of an integrity violation); and that `Explanation.evidence_used` lists the decisive fields, in precedence order, with canonical `group.field` paths.
3. `## Evidence predicates` defines integrity evidence, system evidence and "coherent channels" per field using the reading states of WS02-T03 (asserted, denied, unavailable), and includes a relevance map (template to the fields that are relevant for it, so that a fault on an unrelated node cannot turn a clinical violation into C2). It contains the explained-away rules: cross-device heart-rate incoherence counts as integrity evidence only when both signal-quality fields are denied (good quality); with a signal-quality problem asserted it counts as system evidence; with signal quality unavailable it leads to UNDETERMINED. A sequence gap explained by asserted link evidence is not integrity evidence (decision D-3 of WS02-T03).
4. `## Decision table` has one row per branch with: precedence number, condition on fields, resulting κ, decisive fields. Provenance is context and never sufficient: C2 and C3 require at least one asserted field outside the `provenance` group (analisi §4.5: recognising C2 only because φ_SYS is violated is circular).
5. `## C1 exclusion conditions` gives, per `TemplateId` (`range`, `sched`, `hold`, `count`, `resp`; `sys` and `int` never yield C1), the predicates that must all be available and satisfied for C1 by exclusion, and marks which of them are robot-derived (WS02-T03 A4 mask) or depend on gap G-1.
6. `## Abstention` says that UNDETERMINED is a valid, scored output, lists its reasons (insufficient: a required condition is unavailable; conflict: asserted evidence that neither the integrity nor the system rule accepts; provenance-only: a φ_SYS or φ_INT violation with no corroboration) and states what appears in `Explanation.text` and `evidence_used` for each reason. It states that κ never suppresses an alert: a violated verdict is always reported; κ changes the wording and the offered action.
7. `## Cascades and root-cause propagation` contains: a template-level cascade table (root event or root template, effect templates, temporal condition on shared anchors and windows; for example a missed measurement seeds the end-of-day measurement-count violation, an unverifiable response and a hold check that needs a recent measurement); the rule that an effect is folded under a root only if its decisive datum is the one the root made missing or invalid, and stays a top-level alert if it has independent evidence (a valid out-of-band measurement is not a cascade effect); root selection and tie-breaking (deterministic by time, then template priority); acyclicity; the fields `caused_by` (effect) and `root_cause_of` (root) as inverses; folding hides the effect from the top level but never deletes its `VerdictRecord` or its `Alert` (`attribute_all` returns roots and effects; consumers filter on `caused_by is None`). One worked case reproduces analisi §4.6 row 15:00.
8. `## Predicted violations` states whether attribution runs on `PREDICTED_VIOLATION` records (proposal: yes, provisional κ from the evidence available at `t_eval_ms`, replaced, not duplicated, when the definitive verdict arrives) and is consistent with the WS01-T07 output.
9. `## Action policy` contains a table κ (C1, C2, C3, UNDETERMINED) versus allowed automatic robot actions (stop, retry, call: exactly the three of analisi §4.9 item 4) versus clinical actions (block the dispenser, withhold or change a dose, interrupt a procedure), which are never automatic and always require clinician confirmation; the fallback when the robot is unavailable (escalate to the nurse, ADR-003); the sentence that safety actions are hazards (a blocked dispenser can cause a missed dose). The table is labelled "WS02 proposal for clinician review (WS00-T07)", because analisi fixes the principle and the three robot actions but not the mapping.
10. `## Invariants` lists, each on a line starting `- I1` to `- I6` with a test-ready statement for WS05-T07 (Hypothesis-style where possible): I1 purity (κ independent of ρ, σ̃, state and time); I2 precedence (integrity evidence asserted and not explained away gives C3 whatever the other fields say); I3 provenance is never sufficient (all 18 non-provenance fields `None` gives UNDETERMINED for every template); I4 no certainty from missing data (setting any field to `None` never turns UNDETERMINED into a definite class and never turns a non-C1 result into C1); I5 locality (masking a field that is neither decisive nor in the template's exclusion conditions does not change κ; this is what makes the A4 mask analysable); I6 cascade consistency (acyclic; `caused_by` and `root_cause_of` are mutual inverses; an effect never has κ different from its root's).
11. `## Worked cases` has subsections `### W-01` and following, each as a table lifted directly into a fixture: template, `template_kind`, the non-`None` fields with values (all others `None`), expected κ, decisive fields, and for UNDETERMINED the reason. Required: W-01 to W-10 one per row of analisi §4.5 (each cites `analisi §4.5 row N`), with an A4 variant where robot-derived fields matter (rows 2, 5, 9); W-11 the cascade of analisi §4.6 row 15:00; W-12 all non-provenance fields `None`; W-13 heart-rate incoherence with low signal quality (explained away); W-14 a φ_SYS violation with no corroboration; W-15 a sequence gap explained by a link fault.
12. Every dotted evidence path in the file is a contract field: `grep -ohE '\b(provenance|system|signal_quality|cross_device|witness|crypto_temporal)\.[a-z_]+' docs/models/attribution-rule.md | sort -u | grep -vxE 'provenance\.(violated_template|template_kind)|system\.(node_lifecycle|diagnostics_ok|liveliness_ok|qos_deadline_missed|ble_link_quality|battery_low|nav_task_failed|manip_task_failed)|signal_quality\.(ecg_sqi|ppg_sqi|cuff_error_code)|cross_device\.pulse_vs_ecg_hr_diff|witness\.(robot_present|identity_confirmed|intake_observed)|crypto_temporal\.(authenticated|seq_gap_or_replay|timestamp_implausible)'` prints nothing.
13. `grep -n 'rho\|ρ' docs/models/attribution-rule.md`: every hit is a sentence saying that ρ is not an input. No numeric clinical value appears (`grep -nE '[0-9]+ ?(mmHg|ms|min|bpm)' docs/models/attribution-rule.md | grep -v 'illustrative, unverified'` prints nothing); thresholds are named registry parameters from `## Parameters requested from the registry` of WS02-T03.

## Passi

1. Read the Contesto sources. Copy the ten rows of analisi §4.5 into a scratch list: they are the acceptance cases of the rule. Note the D-1 to D-8 decisions and the gaps G-1 to G-6 of WS02-T03; the rule must be written against those decisions, not around them.
2. Write `## Inputs and outputs` (check 2): the signatures `attribute(violated: VerdictRecord, evidence: EvidenceVector) -> AttributedCause` and `attribute_all(violated, evidence) -> Sequence[Alert]`, the evidence key of D-1, the ordering of returned alerts (`rank_alerts` from `#template`).
3. Write `## Evidence predicates` (check 3): per family (integrity, system) list the fields that count, their adverse values from WS02-T03, and the relevance map. Include the note that a φ_INT verdict is meaningful only when at least one of witness and authentication is available; otherwise a falsified dispense surfaces only through the response constraint after Δ2 (analisi matrix row 9, partial). Check that the WS01-T02 template table states this evaluability condition; if it does not, record the mismatch in `## Traceability` for the plan lead.
4. Write `## Decision table` and `## C1 exclusion conditions` (checks 4 and 5). Starting expectations to confirm or correct with the matrix rows: for `range` and `hold`, C1 needs the cuff-path system fields, the cuff error code, the cross-device coherence with signal quality available, and the crypto-temporal fields all available and denied (row 1: yes, by exclusion, without the robot); for `sched` add navigation outcome and robot liveliness denied (robot-derived, so removed by A4); for `count` add the dispenser content and interval evidence of G-1 (rows 6 and 7); for `resp` add positive backing of the dispense, either `witness.intake_observed` with `witness.identity_confirmed`, or `crypto_temporal.authenticated` (row 2: only if there is a witness).
5. Write `## Abstention` (check 6), then `## Cascades and root-cause propagation` (check 7) and `## Predicted violations` (check 8).
6. Write `## Action policy` (check 9). Do not invent clinical actions beyond the three robot actions and the clinical actions named by the sources.
7. Write `## Invariants` (check 10) as statements a property test can check, then `## Worked cases` (check 11). Compute each expected κ by applying the decision table by hand; where the table gives a different result from the analisi matrix verdict (yes, partial, no), do not bend the table: record the difference in `## Traceability` and in the case, because WS02-T05 needs both.
8. Write `## Traceability`: analisi §4.5, §4.6, §4.9 items 3 and 4, §4.8 (specification-level traceability wording), review items R2-W7 and R3-W4, ADR-010 and ADR-003, and the open points for the clinician review of WS00-T07 (the action policy, the C1 exclusion conditions).
9. Run every command of `## Test` and fix until each prints what it should.

## Done when

All of the following, from the repository root:

- `test -f docs/models/attribution-rule.md`
- `grep -c '^## ' docs/models/attribution-rule.md` prints at least 11, and the headings of check 1 are present.
- `grep -c '^### W-' docs/models/attribution-rule.md` prints at least 15.
- `grep -c '^- I[1-6]' docs/models/attribution-rule.md` prints 6.
- `grep -o 'analisi §4.5 row [0-9]*' docs/models/attribution-rule.md | sort -u | wc -l` prints 10.
- `grep -ci 'clinician' docs/models/attribution-rule.md` prints at least 1, and each of `stop`, `retry` and `call` appears in the action policy section.
- The evidence-path check of Test item 12 prints nothing.
- `grep -nE 'T[O]DO|T[B]D|[?]{3}|lore[m]' docs/models/attribution-rule.md` prints nothing.

## Notes

### Flag from the WS02-T03 review (orchestrator, 2026-10-04)

See `docs/models/evidence-channels.md`: step 4 wants "robot liveliness denied ... removed by A4" while the document has an aggregated scalar field `system.liveliness_ok` (EC-OP-17); decision D-12 and the worked check EX-12 record the integrity-first hazard of the fault model CAS-5 (a violated INT with the robot co-located, `witness.robot_present` and `witness.intake_observed` both False, and the BLE-only `crypto_temporal.*` fields denied) and leave the attribution rule to this task with three options (accept the false-C3 hazard, read the pair as UNDETERMINED, widen the scope to the robot presence stream); the same pattern arises with a lagging availability mask (FM hypothesis 9, OP-10). Provenance alone is never sufficient (line 40). `None` for `crypto_temporal.*` when a device of the scope is silent in the window (D-9). Kept `blocked`.

### Hand-over from the WS04-T09 review (orchestrator, 2026-10-07)

- The refusal against the missed robot task (group `refusal_vs_robot_missed`) is separated only by the outcome `declined` against `failed`, and `declined` has no evidence field (ADR-040, proposed): the rule for this pair depends on that ADR.

### Hand-over from the WS01-T07 review (orchestrator, 2026-10-08)

Read `docs/formal/07-alert-tuple-mapping.md` section 1 (sigma_norm of VIOLATED and predicted alerts, CP13: kappa of a PREDICTED_VIOLATION alert is UNDETERMINED and the alert is superseded by the VIOLATED alert with the same `xi.instance_key`) and section 9 (open points OP-T07-1..17) and proposed ADR-041 before starting. Where this task text assumes a provisional kappa for predicted alerts (WS02-T04 check 8 and step 5; WS05-T07 tests 18, 20, 25) or counts a pair matched by a predicted alert (WS08 E3/E4), follow OP-T07-10 and ADR-041 and record any deviation here. `attribute` stays pure (kappa independent of `state`, test 5 scoped to the rule); the state check sits in `attribute_all`.
