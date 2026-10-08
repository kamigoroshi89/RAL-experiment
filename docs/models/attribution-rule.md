# Attribution rule: hierarchy, abstention, cascades and the clinician in the loop

Document WS02-T04. It is the normative specification of `HierarchicalRule.attribute` and of `Attributor.attribute_all` of the `Attribution` contract (`docs/plan/02-interfaces.md#attribution`, version 0.1.0, not edited here). It defines, in terms of the twenty fields of the `EvidenceVector` (`#evidencevector`), the evidence predicates, the hierarchical decision table (integrity evidence gives C3, otherwise system evidence gives C2, otherwise a violation with coherent channels gives C1, otherwise UNDETERMINED), the per-template conditions for claiming C1 by exclusion, the abstention reasons, the propagation of a root cause over cascades (analisi §4.9 item 3), the treatment of predicted violations, and the action policy with autonomy limited to robot actions (analisi §4.9 item 4). It ends with test-ready invariants and the worked cases that WS05-T07 lifts into pytest fixtures. It closes R2 weakness 7 (the attributed cause is not derived from low confidence) and, with the hazard paper of WS02-T05, R3 weakness 4 (taxonomy and safety actions). Validation in this project is technical and pre-clinical: nothing here is a clinical claim, no number in this document is a clinical, probabilistic or device value, and no statement says that a rule or an action is clinically validated.

The semantics used is the merged core: `docs/models/evidence-channels.md` (called EC below: field semantics, reading states, the A4 mask, decisions D-1 to D-14, gaps EC-GAP-1 to EC-GAP-12, open points EC-OP-1 to EC-OP-21), `docs/models/fault-model.md` (FM), `docs/models/threat-model.md` (TM), `docs/formal/07-alert-tuple-mapping.md` (F07: the alert tuple, CP13, the open points OP-T07-1 to OP-T07-17), `docs/formal/02-templates.md` (T02) and `docs/formal/05-three-valued-semantics.md` (T05). The glossary of `docs/plan/01-conventions.md` section 7 is binding: an **alert** is the output tuple, a **violation** is a violated sub-formula and names its conjunct, the **attributed cause** κ is a value of the alert (C1, C2, C3, UNDETERMINED); C3 means integrity violation (ADR-002); DISPENSE (the dispenser opened) is not INTAKE (verified only by the robot witness, ADR-004); a robot that is unavailable is not a robot that reports a denial.

**Reading conventions.**

1. A field is written `group.field` (EC, section Conventions). This is the canonical path used in `Explanation.evidence_used`, in configuration and in the fixtures. A proposed field that is not in the contract is written in slash notation `group/name` and is never read by the table.
2. A reading is asserted, denied or unavailable (`None`), as defined by EC (section Reading states). Two fields need a finer classification than EC gives, written out in the section Evidence predicates (`system.node_lifecycle` has a deliberate class, `system.ble_link_quality` separates a loss from a degraded link). A reading of a float or string field is obtained by the consumer by comparing the value with a registry threshold; this document uses four named thresholds, all requested from the registry by EC (section Parameters requested from the registry): `hr_coherence_tolerance`, `ecg_sqi_floor`, `ppg_sqi_floor`, `ble_link_quality_floor`. No value is given for any of them, and no fixture in this document carries a clinical value: a float reading is given by its relation to the named threshold.
3. Decisions are numbered AD-n, hypotheses H-n and open points OP-AR-n. Each decision quotes the line it rests on in the text where it is taken and is listed once in the section Traceability. Whatever depends on a proposed ADR (`[DA-CONFERMARE]`) says which one; the list of dependencies is in the section Traceability.
4. The decision table was checked by an exhaustive enumeration of the relevant fields of each template and by two independent implementations (a scalar one that follows the table row by row and a vectorised one written from the predicates), which agree on every combination (scalar against vectorised: exhaustively for `range`, `sched`, `count`, `sys` and `int`, on a seeded random sample of four hundred thousand combinations each for `hold` and `resp`). The scripts are scratch files and are not committed; the counts are in the section Decision table and in the notes of the task file. The worked cases were computed with the scalar implementation and, for the cases marked in them, by hand.
5. Times are `hh:mm` labels of a fixture day. A fixture value written FIXTURE-ONLY or a name of a registry parameter has no clinical meaning.
6. Quotations from `docs/source/analisi.md` and `docs/source/review.md` are translations from the Italian source; quotations from the other project documents are verbatim.

## Inputs and outputs

**Signatures** (quoted from `#attribution`; the Protocols are not changed by this document).

```python
class AttributionRule(Protocol):
    def attribute(self, violated: VerdictRecord, evidence: EvidenceVector) -> AttributedCause: ...

class Attributor(Protocol):
    def attribute_all(self, violated: Sequence[VerdictRecord], evidence: Mapping[str, EvidenceVector]) -> Sequence[Alert]: ...
    # propagates root causes over cascades (analisi §4.9 item 3)
```

`HierarchicalRule.attribute` is the decision table of this document. `RuleAttributor.attribute_all` (WS05-T07) is the alert builder: it applies the rule to each record, applies the state check of the section Predicted violations, folds cascades by the section Cascades and root-cause propagation and returns the alerts ordered by `rank_alerts` (`#template`: template priority first, then σ̃ ascending, then `t_ms` and `xi.instance_key`: F07 section 1.3, T04 section 4.2; the order is a function of the alerts, so folded effects are in the list). The table produces a **decision record** ⟨κ, row, reason, decisive fields⟩ from the same two inputs; WS05-T07 exposes it through a method outside the Protocol (the Protocol is unchanged), and `Explanation.evidence_used` and the abstention text are rendered from it.

**The evidence key.** The mapping `evidence` is keyed by `VerdictRecord.instance_key` of the violated record (EC decision D-1, which ADR-033 proposes to put in the contract), per care plan. An absent key means a vector with `provenance` taken from the record and every other field `None`; the result is UNDETERMINED, with no exception (WS05-T07 test 13, invariant I3).

**What κ is a function of.** κ is a function of `provenance.violated_template`, `provenance.template_kind` and the other 18 fields, and of nothing else; the table reads fewer than the 18 for every template (the relevance map in the section Evidence predicates), so this is an upper bound. `provenance.template_kind` is determined by the template (T02 section 3.1: SYSTEM and INTEGRITY only for `sys` and `int`); it selects the abstention reason of row 7 and a record whose kind does not match its template is a defect of the caller. Two of the 18 fields are never read: `system.battery_low` and `witness.robot_present` are context (AD-11).

**What κ is not a function of.** ρ is not an input: neither `VerdictRecord.rho` nor `Alert.rho` is read by the rule, and a low ρ is not evidence of an integrity violation (R2 weakness 7: noise, distribution shift and faults also lower ρ, which therefore does not identify a cause). σ̃, the raw interval `sigma_interval` and `sigma_norm_interval` are not inputs. `VerdictRecord.state`, `t_eval_ms`, `decided_at_ms` and `pending_until_ms` are not inputs of the rule (time and verdict state enter `attribute_all` only, as stated in the sections Cascades and root-cause propagation and Predicted violations). The registry values other than the four thresholds, the care plan, the forecaster, the conformal calibrator, `LatentDay` and `GroundTruthEvent` are not inputs either; the attribution layer reads only the observed trace through the evidence vector (FM hypothesis 8).

**What the outputs say.**

- `Alert.kappa` and `Alert.label` carry κ; UNDETERMINED is a valid, scored output and not an error (ADR-010, `#alert`). κ never suppresses an alert: a violated verdict is always reported, and κ changes the wording of the alert and the offered action (F07 section 1.7).
- `Explanation.evidence_used` lists the decisive fields as canonical `group.field` paths, **in precedence order**: the rows in the order of the decision table; within a row the predicates in the order in which the section Decision table lists them; within a predicate the fields in the order of the contract (AD-17). It is empty when no field decided κ (an abstention of reason insufficient or provenance-only, a predicted alert).
- `Explanation.text` follows the requirements of F07 section 3.4 (specification-level traceability, not an explanation of the cause); this document adds what it must contain for each abstention reason (section Abstention) and for an effect of a cascade (section Cascades and root-cause propagation).
- `Alert.caused_by` and `Alert.root_cause_of` are set by the cascade rule and only there.

## Evidence predicates

### Reading classes

The classes of a reading, per field, are those of EC (section Reading states and Representation of denied for non-boolean fields). The letters used in the tables and in the scripts are A (asserted), D (denied), U (unavailable, `None`), and two further letters for the two fields below.

| field | A | D | U | extra classes |
|---|---|---|---|---|
| `system.node_lifecycle` | at least one entry other than `active` and other than `<state>+commanded` (EC D-4) | every entry is `active` | `None` or an empty mapping (H-3) | K: no uncommanded adverse entry and at least one `+commanded` entry (a deliberate transition, denied in EC, kept apart here: AD-7) |
| `system.ble_link_quality` | value below `ble_link_quality_floor` (a degraded link) | value at or above the floor | `None` | F: exactly 1.0, no sequence value missing; G: at or above the floor and below 1.0, a sequence value is missing but the link is not degraded (EC D-3: the floor applies to degraded, not to "a gap exists"; H-2: the floor is at most 1.0) |
| `system.diagnostics_ok`, `system.liveliness_ok` | False | True | `None` | none |
| `system.qos_deadline_missed`, `system.nav_task_failed`, `system.manip_task_failed` | True | False | `None` | none |
| `signal_quality.ecg_sqi`, `signal_quality.ppg_sqi` | below `ecg_sqi_floor`, `ppg_sqi_floor` | at or above the floor | `None` | none |
| `signal_quality.cuff_error_code` | a non-empty string | the empty string | `None` | none |
| `cross_device.pulse_vs_ecg_hr_diff` | above `hr_coherence_tolerance` | at or below it | `None` | none |
| `witness.identity_confirmed`, `witness.intake_observed` | False (the adverse reading in a dispense context, EC Field semantics) | True (positive backing) | `None` | none |
| `crypto_temporal.authenticated` | False | True | `None` | none |
| `crypto_temporal.seq_gap_or_replay`, `crypto_temporal.timestamp_implausible` | True | False | `None` | none |
| `system.battery_low`, `witness.robot_present`, `provenance.*` | not read | not read | not read | context (AD-11) |

`None` is never converted to a negative observation (`#evidencevector` rule, EC section Reading states): every predicate below that needs a denied reading is not satisfied by `None`.

### Integrity evidence (C3)

Integrity evidence is evidence that an input is not backed by an authentic origin or that the trace contradicts itself (TM section Scope and claim). Three predicates count, in this order.

- **IE-1.** `crypto_temporal.authenticated` is asserted: a message of a device of the scope failed verification in the window. Source: TM attack-to-evidence table (the A column of the forging classes) and TM hypothesis H-AUTHCAUSE (no C2 fault makes the verification of a genuine message fail; FM lists no fault that raises it). Not explained away by anything in the vector (H-5).
- **IE-2.** `crypto_temporal.seq_gap_or_replay` is asserted and `system.ble_link_quality` is complete (F): a repeated sequence value without a missing one. Source: EC D-3: "may treat a True field with ratio 1.0 as integrity evidence, and must not treat a True field with a ratio below 1.0 as integrity evidence alone". A gap, that is any asserted sequence field with a ratio below 1.0 (class A or G), is **not** integrity evidence, and a sequence field with an unavailable ratio is not either (AD-4).
- **IE-3** (templates that read the cross-device pair, see the relevance map). `cross_device.pulse_vs_ecg_hr_diff` is asserted and both `signal_quality.ecg_sqi` and `signal_quality.ppg_sqi` are denied (good quality). Source: the explained-away rule of the task and FM section Non-faults and boundaries (the evidence confound of `ecg_noise`: "`signal_quality.ecg_sqi` is the field that marks the noise; whether the rule uses it first is WS02-T04's decision"). H-7 records that `signal_quality.ppg_sqi` reads `SPO2` (EC D-13) and is included because the task names both quality fields; the choice is the conservative one.

Explained-away rules (AD-4, AD-5, AD-6).

1. **Cross-device incoherence.** With both quality fields denied it is integrity evidence (IE-3). With a quality problem asserted (either field) it counts as system evidence (SE-9): the incoherence is attributed to a signal-quality problem of the measurement system. With the quality unavailable (and neither field asserted) it is neither: the table abstains (AM-1, reason insufficient). A quality field that is asserted while the incoherence is denied or unavailable decides nothing.
2. **Sequence gap.** A gap is explained by asserted link evidence (SE-1 to SE-5 of the list below, in particular the degraded link of SE-5) and is then not integrity evidence: the link fields decide (C2). The table does not check which system evidence explains the gap: any asserted system evidence decides C2 (row 4) and the gap is then not integrity evidence either. A gap of class G with no other system evidence is evidence of a loss that neither rule accepts (RS-2, abstention, reason conflict). An asserted sequence field with an unavailable ratio cannot be told from a repeat or a gap (EC D-3, EX-10 check P4) and is ambiguous (AM-2, reason insufficient).
3. **Late or future-stamped input.** `crypto_temporal.timestamp_implausible` mixes late arrival, future stamp and replay-related inconsistency in one Boolean (EC-GAP-6, CG-10 of T01, TM-GAP-TIME): a link delay and a clock skew (C2) and a replay or a delayed relay (C3) give the same reading (TM section Time as an attack vector, "no field separates them"). It is therefore never decisive alone (RS-3: abstention, reason conflict); it is decisive only through IE-1 or IE-2 when those hold.
4. **Deliberate transition.** A node entry `<state>+commanded` is not a failure (analisi §4.6, row 15:00; EC section Reading rules: "what to do with it is WS02-T04's"). It is not system evidence and it does not allow C1 either: the datum may have been withheld by an operator, which is neither a failure nor a clinical cause (RS-1, abstention, reason conflict).

### System evidence (C2)

System evidence is evidence that a device, a link or the robot failed. The fields count as follows, in this order (the order of the contract), each only for the templates whose relevance map reads it.

| id | condition | templates |
|---|---|---|
| SE-1 | `system.node_lifecycle` asserted | all |
| SE-2 | `system.diagnostics_ok` asserted | all |
| SE-3 | `system.liveliness_ok` asserted | all |
| SE-4 | `system.qos_deadline_missed` asserted | all |
| SE-5 | `system.ble_link_quality` asserted (class A) | all |
| SE-6 | `system.nav_task_failed` asserted | `sched`, `hold`, `resp`, `int` |
| SE-7 | `system.manip_task_failed` asserted | `sched`, `hold`, `resp`, `int` |
| SE-8 | `signal_quality.cuff_error_code` asserted | `range`, `sched`, `hold`, `resp`, `sys` |
| SE-9 | `cross_device.pulse_vs_ecg_hr_diff` asserted and at least one of `signal_quality.ecg_sqi`, `signal_quality.ppg_sqi` asserted | `range`, `hold`, `resp`, `sys` |

The scalar `system` fields are aggregates over the scope of the instance (EC section Scope of an instance and aggregation rule, decision D-10, which ADR-033 proposes to put in the contract): the scope table of EC says which nodes a field aggregates for each template, and that scope is what makes the relevance map below meaningful. A fault on a node outside the scope of the violated template is not in the vector, so it cannot turn a clinical violation into C2 (EC D-10: "A global reading (c) lets a fault on an unrelated node make C2 the attributed cause of a violation of φ_CP"). **Provenance is context and never sufficient**: no predicate reads `provenance.violated_template` or `provenance.template_kind` as evidence, and C2 and C3 require at least one asserted field outside the `provenance` group (analisi §4.5: recognising C2 only because φ_SYS is violated is circular, and the same holds for C3 and φ_INT; TM Non-claims 6).

### Evidence that no rule accepts, and ambiguity

These asserted readings are neither integrity nor system evidence. They block C1 and send the table to an abstention.

| id | condition | reason |
|---|---|---|
| RS-1 | `system.node_lifecycle` of class K (a deliberate transition) | conflict |
| RS-2 | `system.ble_link_quality` of class G (a missing sequence value, link not degraded) | conflict |
| RS-3 | `crypto_temporal.timestamp_implausible` asserted | conflict |
| RS-4 (`resp` only) | `crypto_temporal.authenticated` unavailable, the witness backing of the section C1 exclusion conditions not satisfied, and `witness.intake_observed` or `witness.identity_confirmed` asserted | conflict |
| AM-1 | `cross_device.pulse_vs_ecg_hr_diff` asserted, neither quality field asserted, and not both denied | insufficient |
| AM-2 | `crypto_temporal.seq_gap_or_replay` asserted and `system.ble_link_quality` unavailable | insufficient |

### Coherent channels

"Coherent channels" (contract step 3) is made precise per template as the **exclusion set** EX(t) of the section C1 exclusion conditions: the channels that the relevance map reads for the template must be available and denied. The word is not used for any weaker reading in this document (AD-8).

### Relevance map

Which fields the table reads for which template, derived from the scope table of EC (the BLE device roles and the robot node per template), the signal footprint of T02 (what the template reads) and the fault and attack rows that can make the template violated (FM section Effects on templates, TM section Attack classes). Legend. **E**: read; asserted decides C2 or C3 (or abstains); required, with a denied reading, for C1 (the exclusion set). **s**: read; asserted gives C3; for C1 the reading must not be asserted (`None` is tolerated: the unauthenticated deployment, AD-8). **b**: read as part of the witness backing of `resp`. **q**: qualifier read only inside IE-3, SE-9 and AM-1. **r**: read (asserted decides C2 or C3 or abstains) for a template that has no C1. **ctx**: context, never read by the table. **-**: not read, because the field is `None` by construction for the template (EC scope table) or does not bear on it.

| field | `range` | `sched` | `hold` | `count` | `resp` | `sys` | `int` |
|---|---|---|---|---|---|---|---|
| `provenance.violated_template` | ctx | ctx | ctx | ctx | ctx | ctx | ctx |
| `provenance.template_kind` | ctx | ctx | ctx | ctx | ctx | ctx | ctx |
| `system.node_lifecycle` | E | E | E | r | E | r | r |
| `system.diagnostics_ok` | E | E | E | r | E | r | r |
| `system.liveliness_ok` | E | E | E | r | E | r | r |
| `system.qos_deadline_missed` | E | E | E | r | E | r | r |
| `system.ble_link_quality` | E | E | E | r | E | r | r |
| `system.battery_low` | ctx | ctx | ctx | ctx | ctx | ctx | ctx |
| `system.nav_task_failed` | - | E | E | - | E | - | r |
| `system.manip_task_failed` | - | E | E | - | E | - | r |
| `signal_quality.ecg_sqi` | q | - | q | - | q | q | - |
| `signal_quality.ppg_sqi` | q | - | q | - | q | q | - |
| `signal_quality.cuff_error_code` | E | E | E | - | E | r | - |
| `cross_device.pulse_vs_ecg_hr_diff` | E | - | E | - | E | r | - |
| `witness.robot_present` | ctx | ctx | ctx | ctx | ctx | ctx | ctx |
| `witness.identity_confirmed` | ctx | ctx | ctx | ctx | b | ctx | ctx |
| `witness.intake_observed` | ctx | ctx | ctx | ctx | b | ctx | ctx |
| `crypto_temporal.authenticated` | s | s | s | r | b | r | r |
| `crypto_temporal.seq_gap_or_replay` | E | E | E | r | E | r | r |
| `crypto_temporal.timestamp_implausible` | E | E | E | r | E | r | r |

Notes on the map.

- `count` and `sys` have no robot-derived field: EC states that for `range`, `count` and `sys` the three `witness` fields, `system.battery_low`, `system.nav_task_failed` and `system.manip_task_failed` are `None`. `hold` is in the robot scope (EC scope table, H-VISIT: the pre-dose reading comes from a visit), so it reads the robot task outcomes (AD-9).
- `signal_quality.cuff_error_code` is computed whatever the template (EC) and is read only for the templates that read a cuff measurement; for `count` and `int` it is usually `None` and decides nothing.
- **Witness fields on `int` are context (AD-3).** For a violated INT instance the pair `witness.robot_present` and `witness.intake_observed` restates the violation: EC check EX-9 (6000 seeded draws) found that every VIOLATED INT instance has `witness.robot_present` asserted and `witness.intake_observed` asserted or `None`, and that both asserted with no `auth` sample is a VIOLATED instance. A reading that is the violated predicate itself is not independent evidence, for the reason that makes a φ_SYS violation not evidence of C2.
- **φ_INT is evaluable only when a witness channel or authentication is available.** A dispense whose robot channels are unavailable and that has no `auth` event is not "unwitnessed": the instance stays PENDING with a marker `undecidable: channel_unavailable:*` and raises no alert (T01 section 2.4, T05 section 3.5, golden case V-INT-1, F07 OP-T07-14). A violated INT instance therefore reaches the rule only when the robot channel was available (V-INT-3), and a falsified dispense in any other situation surfaces only through the response constraint after the response window (analisi §4.5 row 9, partial). Whether the elapsed-deadline PENDING instance itself should raise a review item is left open by TM-OP-15 to this task: the rule is defined on records that claim a violation (contract and F07 AH-2), such an instance has no alert path in contract 0.1.0, and the proposal is that it stays outside the rule (OP-AR-18). The table of T02 section 3.1 and the section 4.7 of T02 do not state this condition; it is stated in T01 and T05. The mismatch is recorded in the section Traceability for the plan lead.

## Decision table

**Rule.** The rows are tried in the order of the precedence number and the first row whose condition holds decides. Conditions are written with the predicates of the section Evidence predicates; "all" in the last column means every template, and a predicate that a template does not read (the relevance map) is false for it. The order is the hierarchy of ADR-010 and of the four steps of the default rule of `#attribution` (analisi §4.5): integrity evidence present gives C3; otherwise system evidence present gives C2; otherwise a violation with coherent channels gives C1; otherwise, with conflicting or insufficient evidence, UNDETERMINED. The abstention branch is split into three rows, one per reason, so that every UNDETERMINED result carries exactly one reason.

| precedence | condition on the fields | resulting κ | decisive fields (`Explanation.evidence_used`, precedence order) | templates |
|---|---|---|---|---|
| 1 | IE-1: `crypto_temporal.authenticated` asserted | C3 | `crypto_temporal.authenticated`, followed by the fields of IE-2 and IE-3 if those also hold | all |
| 2 | IE-2: `crypto_temporal.seq_gap_or_replay` asserted and `system.ble_link_quality` complete | C3 | `system.ble_link_quality`, `crypto_temporal.seq_gap_or_replay`, followed by the fields of IE-3 if it also holds | all |
| 3 | IE-3: `cross_device.pulse_vs_ecg_hr_diff` asserted, `signal_quality.ecg_sqi` and `signal_quality.ppg_sqi` denied | C3 | `signal_quality.ecg_sqi`, `signal_quality.ppg_sqi`, `cross_device.pulse_vs_ecg_hr_diff` | `range`, `hold`, `resp`, `sys` |
| 4 | at least one of SE-1 to SE-9 holds | C2 | the fields of every SE predicate that holds, in the order SE-1 to SE-9 (SE-9: the asserted quality fields, then `cross_device.pulse_vs_ecg_hr_diff`) | all |
| 5 | EX(t): the exclusion set of the template is satisfied (section C1 exclusion conditions) | C1 | the fields of EX(t) whose reading is denied, in contract order (for `resp` the backing actually used) | `range`, `sched`, `hold`, `resp` |
| 6 | at least one of RS-1 to RS-4 holds | UNDETERMINED, reason conflict | the asserted fields named by the RS predicates that hold, in contract order | all |
| 7 | `provenance.template_kind` is SYSTEM or INTEGRITY, and neither AM-1 nor AM-2 holds | UNDETERMINED, reason provenance-only | none | `sys`, `int` |
| 8 | otherwise | UNDETERMINED, reason insufficient | none | all |

**Decidability and totality.** Every field the table reads has a finite set of reading classes (three, or four for `system.node_lifecycle` and `system.ble_link_quality`), a template reads at most sixteen fields, and row 8 is the "otherwise" branch, so the table is a total function of the reading classes of the relevant fields: exactly one row, hence exactly one κ and, for UNDETERMINED, exactly one reason (rows 6, 7 and 8 are the three reasons), is selected for every combination. The twenty fields give no other source of variation: the fields a template does not read cannot change the result, because no row reads them.

**Enumeration check.** For each template every combination of the reading classes of the fields it reads was enumerated (87,351,696 combinations in all). The table below gives the number of combinations that each row decides and the number of combinations per outcome. Results: (i) the first matching row of the conditions written independently of the precedence (non-exclusive) is the row selected, for every combination; (ii) exactly one row fires in the exclusive form for every combination, with no combination left over; (iii) precedence is needed and exercised, since the non-exclusive conditions of rows 1 to 7 overlap in 62,979,376 of the 76,527,504 combinations of `resp` (and in a similar share of the other templates), and integrity evidence together with system evidence (C3 against C2) occurs in 30,155,328 of them; no combination satisfies both integrity evidence and the exclusion set; (iv) every row that applies to a template is reached by some combination (no unreachable row; "n/a" marks a row that does not apply to the template, which is not an unreachable row); (v) the outcome set of each template is exactly the one in the last four columns, including the design-unreachable cases: C1 does not exist for `count` (AD-10), `sys` and `int` (T02: a φ_SYS or φ_INT violation never yields C1). The scripts are not committed.

| template | fields read | combinations | row 1 | row 2 | row 3 | row 4 | row 5 | row 6 | row 7 | row 8 | C3 | C2 | C1 | UNDETERMINED |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `range` | 12 | 944,784 | 314,928 | 52,488 | 21,384 | 507,600 | 18 | 34,944 | n/a | 13,422 | 388,800 | 507,600 | 18 | 48,366 |
| `sched` | 11 | 314,928 | 104,976 | 17,496 | n/a | 183,240 | 2 | 6,656 | n/a | 2,558 | 122,472 | 183,240 | 2 | 9,214 |
| `hold` | 14 | 8,503,056 | 2,834,352 | 472,392 | 192,456 | 4,810,320 | 18 | 139,776 | n/a | 53,742 | 3,499,200 | 4,810,320 | 18 | 193,518 |
| `count` | 8 | 11,664 | 3,888 | 648 | n/a | 5,976 | n/a | 832 | n/a | 320 | 4,536 | 5,976 | 0 | 1,152 |
| `resp` | 16 | 76,527,504 | 25,509,168 | 4,251,528 | 1,732,104 | 43,292,880 | 90 | 1,392,384 | n/a | 349,350 | 31,492,800 | 43,292,880 | 90 | 1,741,734 |
| `sys` | 12 | 944,784 | 314,928 | 52,488 | 21,384 | 507,600 | n/a | 34,944 | 9,216 | 4,224 | 388,800 | 507,600 | 0 | 48,384 |
| `int` | 10 | 104,976 | 34,992 | 5,832 | n/a | 59,544 | n/a | 3,328 | 1,024 | 256 | 40,824 | 59,544 | 0 | 4,608 |

**Combinations the extractor cannot produce.** The table is total over all classes, including combinations that are inconsistent by construction (for example a sequence field denied with a ratio below 1.0: the ratio of class A is system evidence, class G is evidence that no rule accepts). It does not rely on the extractor being consistent.

**Cost of the integrity-first order, stated.** The rows 1 and 2 give C3 even when system evidence is asserted too (ADR-010: integrity first; invariant I2). A benign repeated sequence value (a device restart, a counter reset, an application-layer re-send, a bounce that repeats the real number: TM hypothesis H-SEQMONO) is therefore read as integrity evidence when the delivery ratio is complete (H-6, OP-AR-6). ADR-034 (proposed) splits the field into a repeat and a gap; until it is accepted the pair of D-3 is the reading.

### Resolution (a): the integrity-first false C3 of D-12, EX-12 and CAS-5

The hazard (EC D-12, EX-12, EC-OP-6; FM CAS-5 and OP-12): a violated INT instance caused by a lost or late `presence` sample, or by a duplicate instance of a dispenser bounce, has both witness fields asserted, the `crypto_temporal.*` fields denied (they cover the BLE devices only: D-12) and the `system` fields denied or `None`; the same pattern is what a dispense that nobody witnessed leaves (TM `dispense_forgery`, TX-4 (c)). EC offers three options.

**Chosen (AD-3): the witness pair of a violated INT instance is not integrity evidence; the table reads the vector as UNDETERMINED (option "read the pair as UNDETERMINED").** Derivation from the sources, not a preference: (1) EC check EX-9 shows that the pair is the violated predicate restated (every VIOLATED INT instance has `witness.robot_present` asserted and `witness.intake_observed` asserted or `None`; both asserted with no `auth` sample is VIOLATED); (2) analisi §4.5 says that recognising a cause only because the sub-formula is violated is circular; (3) the matrix verdict of analisi §4.5 row 9 is "partial" (no embodied witness; the response constraint violated after the response window), and TM defines partial as "attribution abstains with a candidate set, not an error"; (4) TM Non-claims 6: a violated φ_INT instance can come from an attack, from a patient who left, and from C2 causes (CAS-5, OP-12), and the rule "requires at least one asserted field outside `provenance`". The witness pair is outside the `provenance` group but it adds nothing to the violation. The cases W-09 (and its variants W-09-A4, W-09-A, W-09-lag, W-09-lag-late, W-09-resp) show the table.

**Cost, stated.** (i) UNDETERMINED instead of C3 for an unauthenticated forged dispense whose only trace is the missing witness: the C3 recall of that case is not obtained from the embodied channel; the matrix row 9 says partial, so the table agrees with the matrix, and the rate is measured by WS08. (ii) A forgery in an authenticated deployment is C3 through IE-1 (`crypto_temporal.authenticated`), not through the witness (W-09-A). (iii) The A4 mask has no effect on the κ of `int` through the witness fields; the hypothesis of analisi §5.6 for A4 ("collapse of κ on forged dispenses") is not produced by this rule, and the exhaustive transition check of the path mask (section C1 exclusion conditions) shows that C3 never changes under A4. WS08-T04 test 6, which expects C3 for `ours` and a different cause for `ours-A4` on a forged-DISPENSE fixture with robot present and no authentication evidence, does not hold under this rule; it is recorded in the section Traceability. (iv) The case does not turn into a false C3: a lost presence sample, a late one and a duplicate bounce instance all give UNDETERMINED, reason provenance-only, when nothing else is asserted.

**Alternatives rejected.** *Accept the false-C3 hazard* (read the witness pair as integrity evidence, WS08-T04 test 6): it makes a link fault on the robot's presence stream, a perception false negative and a patient who left read as C3; it contradicts the "partial" of row 9; its benefit (a larger C3 recall and an A4 effect on forged dispenses) would be produced by the rule and not by evidence. *Widen the scope of `crypto_temporal.*` and `system.qos_deadline_missed` to the robot's presence stream* (reverse EC D-12): it changes the field semantics and the A4 statement that `crypto_temporal.*` is unchanged under A4, needs an ADR and an extractor change, and does not close the case: a loss that no later message reveals is not seen by the sequence evidence (EC D-3 and EX-1 (l); in EX-12 the lost sample is the last one sent). The option can be taken later by a decision of the human (OP-AR-2); the table would then read the robot stream like a device stream.

### Resolution (c): the lagging availability mask (FM hypothesis 9, OP-10)

If the robot channels are marked unavailable after the dispense step, a robot outage gives a VIOLATED INT instance with the held level 0 (FX-9 (e)). Under AD-3 the instance does not become C3. Whether it becomes C2 depends on the evidence at the cut-off: the watchdog's lapse (`system.liveliness_ok` asserted) is evidence of the robot outage if it is detected by the last admissible evidence time (EC section Detection lag of the ward-generated evidence): then SE-3 gives C2 (W-09-lag). If the lapse is detected later, the vector holds nothing asserted and the result is UNDETERMINED, reason provenance-only (W-09-lag-late): the rule does not read the outage from the witness pair. The lease and the lag are run parameters of the profile (EC-OP-18); no value is given.

## C1 exclusion conditions

C1 is claimed by exclusion: no integrity evidence, no system evidence, and **every channel that the relevance map marks E for the template is available and denied**. This is the reading of the matrix verdict "yes, by exclusion" of analisi §4.5 row 1 ("violation of the range constraint with all channels coherent") and of the statement of EC that "a rule that needs a denied reading (for example the exclusion conditions for C1) is not satisfied by `None`, and the abstention reasons of WS02-T04 are the consequence". It also follows from invariant I4: a field that, asserted, can lead to C2, to C3 or to an abstention must be required to be denied, otherwise replacing the asserted reading by `None` would turn that result into C1 (AD-8). A silent device in the window makes the `crypto_temporal.*` fields, `system.ble_link_quality` and `signal_quality.cuff_error_code` `None` (EC decision D-9 and check EX-3 (f): "a violation of `sched`, `hold` or `resp` whose cuff stream is silent in the window has `crypto_temporal.*` and `system.ble_link_quality` equal to `None`"), so the exclusion conditions that need them are not met: this is the intended consequence recorded by EC ("this is intended"), resolution (d): UNDETERMINED, reason insufficient, never C1 (W-05-silent).

| template | predicates that must all be available and satisfied | robot-derived (None under A4) | needs G-1 evidence | not satisfied in the reference profile S6 of EC |
|---|---|---|---|---|
| `range` | EX-CP, `signal_quality.cuff_error_code` denied, `cross_device.pulse_vs_ecg_hr_diff` denied, `crypto_temporal.authenticated` not asserted | none | no | `system.diagnostics_ok`, `system.qos_deadline_missed`, `crypto_temporal.timestamp_implausible` |
| `sched` | EX-CP, `system.nav_task_failed` denied, `system.manip_task_failed` denied, `signal_quality.cuff_error_code` denied, `crypto_temporal.authenticated` not asserted | `system.nav_task_failed`, `system.manip_task_failed` (the aggregates of EX-CP lose their robot component, see below) | no | as `range` |
| `hold` | EX-CP, `system.nav_task_failed` denied, `system.manip_task_failed` denied, `signal_quality.cuff_error_code` denied, `cross_device.pulse_vs_ecg_hr_diff` denied, `crypto_temporal.authenticated` not asserted | `system.nav_task_failed`, `system.manip_task_failed` | no | as `range` |
| `count` | none can be satisfied: the exclusion of a bounce and of a double take needs the dispenser interval and content change (`dispenser/interval_since_previous_ms`, `dispenser/content_change`), which have no field in contract 0.1.0 | none | yes (EC-GAP-1, ADR-032 proposed) | not applicable |
| `resp` | the conditions of `hold` with the backing below in place of `crypto_temporal.authenticated` not asserted | `system.nav_task_failed`, `system.manip_task_failed`, `witness.identity_confirmed`, `witness.intake_observed` (the backing alternative) | no | as `range` |
| `sys`, `int` | never: C1 is not defined for a φ_SYS or φ_INT violation | not applicable | not applicable | not applicable |

EX-CP, the cuff-path conditions of the exclusion set: `system.node_lifecycle` denied with every entry `active` (class D, not K), `system.diagnostics_ok` denied, `system.liveliness_ok` denied, `system.qos_deadline_missed` denied, `system.ble_link_quality` complete (class F), `crypto_temporal.seq_gap_or_replay` denied, `crypto_temporal.timestamp_implausible` denied. The signal-quality fields are not part of the exclusion set: they only qualify the cross-device pair (the starting expectation of the task, "cross-device coherence with signal quality available", is narrowed to "cross-device coherence", because a denied incoherence needs no explanation, AD-5).

**Backing for `resp`** (analisi §4.5 row 2: "intake seen by the robot or authenticated by the dispenser; only if there is a witness"; step 4 of the task). `resp` is anchored on a dispense, and a pressure that does not fall after a dispense is C1 only if the dispense is backed. The backing is satisfied by `crypto_temporal.authenticated` denied, or by `crypto_temporal.authenticated` unavailable together with `witness.intake_observed` denied (True: an `INTAKE` event of the robot) and `witness.identity_confirmed` denied (True) (EC D-6: three tiers of backing; an observed intake with a confirmed identity is the strongest reading the contract carries, and presence alone proves only that someone was perceived: R3 weakness 5). A robot that watched and saw no intake (`witness.intake_observed` asserted) or whose identity check failed is not backing and, with the authentication unavailable, is evidence that no rule accepts (RS-4): whether the dose was taken or not, and whether the dispense was forged or not, is not told apart, which is the abstention of the matrix. DISPENSE is not INTAKE: the dispense event never backs an intake.

**The unauthenticated deployment (AD-8).** `crypto_temporal.authenticated` is `None` when the device does not authenticate (TM reading table, hypothesis H-DEP: the unauthenticated deployment U is a named deployment of the threat model, and S5 of EC). The exclusion conditions require that it is not asserted but tolerate `None`, for every template except the backing of `resp`. Reason: with it required, C1 would be unreachable in U, which contradicts the matrix row 10 and the expected κ of the informed injection in U (C1 or no alert: TM-OP-11 and the starting content of DX-10 in WS02-T05), and the declared limit of the matrix would turn into an abstention. This is the one exception to the strict reading of I4 (see the section Invariants). Cost: when the verification channel is simply down, a forged message is read as clean (the generic hazard of a soft channel); the other integrity channels (sequence, cross-device, time) stay required.

**Robot-derived conditions and the A4 mask (resolution (b)).** The starting text of step 4 reads "for `sched` add navigation outcome and robot liveliness denied (robot-derived, so removed by A4)". The contract field is the single scalar `system.liveliness_ok`, an aggregate over the supervised nodes of the scope (cuff and robot for `sched`), and A4 recomputes it from the device nodes: it is not set to `None` (EC section Ablation A4 mask, class recompute; EC-OP-17). The exclusion condition is therefore stated on the aggregate, and what A4 removes is: the two task outcomes (`None`), and, from the four aggregate fields, their robot component (recomputed, not `None`). Under A4 the C1 of `sched`, `hold` and `resp` is unreachable, because the two outcomes are required and become `None`; a robot crash that was visible only through the robot component of the liveliness aggregate is no longer visible (W-05-live, W-05-live-A4: UNDETERMINED, reason insufficient, not C1). Applying only the path mask `EMBODIED_MASK_ALL` of EC is a partial A4 (EC-OP-5); the transitions below are those of the path mask restricted to the fields the table reads.

| template | fields of the path mask that the table reads | κ before, κ after the mask (exhaustive over the relevant fields) |
|---|---|---|
| `range`, `count`, `sys` | none | unchanged for every combination |
| `sched`, `hold`, `int` | `system.nav_task_failed`, `system.manip_task_failed` | C3 stays C3; C2 stays C2 or becomes UNDETERMINED (when only a robot outcome was asserted); C1 becomes UNDETERMINED; UNDETERMINED stays UNDETERMINED |
| `resp` | the two outcomes and `witness.identity_confirmed`, `witness.intake_observed` | as above |

The mask never creates a definite class and never turns C2 into C1 (invariant I4 for these fields). **Refusal against robot-missed and ADR-040 (resolution (f)).** The confounder group `refusal_vs_robot_missed` (WS04-T09) separates a refused measurement (C1) from a missed robot task (C2) only by the outcome `declined` against `failed`. Without ADR-040 `declined` has no evidence field: the manipulation field is `None` for a refusal (the robot did not report a manipulation outcome that the conventions of EC define), the missed robot task gives `system.manip_task_failed` asserted and C2 (W-05 for navigation; the manipulation variant is the same row), and the refusal gives UNDETERMINED, reason insufficient (W-05-silent). With ADR-040 accepted the outcome `declined` makes `system.manip_task_failed` denied for the window and the robot-derived part of the exclusion is met; **the refusal still does not reach C1**, because a refusal leaves the cuff silent and `signal_quality.cuff_error_code`, `system.ble_link_quality` and the `crypto_temporal.*` fields are `None` (decision D-9): UNDETERMINED, reason insufficient (W-05-silent-040). ADR-040 is therefore necessary but not sufficient for C1 on a refusal under this rule; what it changes is the list of unavailable fields in the text, and it keeps the C2 side of the pair (a failed manipulation) separated. A patient who delays the measurement, which then arrives with every channel clean, is C1 (W-05-late-patient). The rule depends on ADR-040 only for this pair, and every statement about `declined` in this document is conditional on it.

**Profile coverage (OP-AR-1).** The exclusion set needs the fields to be available, which is a property of the device profile (EC D-8, ADR-036 proposed). In the reference profile S6 of EC (EX-7: no diagnostics reports, no declared deadline, no independent clocks) `system.diagnostics_ok`, `system.qos_deadline_missed` and `crypto_temporal.timestamp_implausible` are `None` (EC-OP-19: "in a benchmark without a transport-delay model the field is True or `None`, never False, so a rule that needs it denied cannot be satisfied there"). **C1 is then unreachable for every template in that profile**, and the abstention rate on clinical events equals one. This is a result of the rule, not a defect of the table; the ways out are decisions for the human and the owners: (i) the benchmark and simulation profiles declare the capabilities and the generators emit the reports (WS04-T06, WS04-T07, WS04-T11, WS07-T03); (ii) a rule that receives the profile and treats a channel the profile does not declare as not applicable instead of unavailable (an amendment of ADR-036; I4 then holds for the declared channels), which this document does not adopt because `attribute` has no profile input in contract 0.1.0 and ADR-036 is proposed. `system.battery_low` is not in the exclusion set for the same practical reason and for the reason of AD-11.

## Abstention

UNDETERMINED is a valid, scored output (ADR-010; analisi §4.5: "the class UNDETERMINED is essential: without it every attribution error becomes an undeclared classification error"; `#alert`: "A value of `UNDETERMINED` is not an error"). It is reported with a reason and its text; **κ never suppresses an alert**: a violated verdict is always reported, κ changes the wording and the offered action (section Action policy). The three reasons partition the abstention (rows 6, 7 and 8 of the decision table).

| reason | row | meaning | `evidence_used` | `Explanation.text` must say | examples |
|---|---|---|---|---|---|
| insufficient | 8 | a required condition is unavailable (a field of the exclusion set is `None`), or an asserted reading cannot be resolved because its qualifier is unavailable (AM-1, AM-2) | empty | that the cause is not determined; that the channels needed to exclude the other causes were not available, listing the unavailable fields of the exclusion set by canonical `group.field` path (for `count`, that the dispenser content evidence has no field in this contract version) | W-02-A4, W-05-A4, W-05-silent, W-06, W-13-U, W-12 |
| conflict | 6 | asserted evidence that neither the integrity rule nor the system rule accepts (RS-1 to RS-4) | the asserted fields named by the RS predicates, in contract order | that the cause is not determined; which asserted fields the rules do not accept and why (a deliberate transition is not a failure; a loss that does not degrade the link is not an explanation; a late or future-stamped input has several causes; a witness reading is not backing) | W-05-deliberate, W-08-U-noseq, W-09-resp, W-15-alone |
| provenance-only | 7 | a φ_SYS or φ_INT violation with nothing asserted outside `provenance` (no corroboration) | empty | that the system or integrity constraint is violated and that no other channel corroborates a cause; for `int` it may state the context that the robot was co-located and perceived no one, as context and not as evidence (AD-3) | W-09, W-09-A4, W-14, W-12 |

The text never names a class as the cause of an abstention, and the candidate set of a "partial" row is declared by the diagnosability matrix of WS02-T05, not computed by the rule. The text of a C1 alert states that every channel required for the exclusion was available and showed no problem (F07 section 3.5 example 1 says "in the channels that were available"; the difference is recorded in the section Traceability). The wording follows the claim reformulations of analisi §4.8 (F07 section 3.1): specification-level traceability, a cause-based taxonomy; no sentence says that a cause is established beyond the evidence listed.

## Cascades and root-cause propagation

A C2 (and also a C1 or a C3) cause upstream generates violations downstream that look like independent ones: a missed measurement makes the response obligation unmet and the hold check without a recent measurement, and, were the template in the library, the end-of-day measurement count (analisi §4.9 item 3: "an upstream cause generates clinical-looking violations downstream; attribution must propagate the cause, otherwise the alerts multiply"; analisi §4.6, row 15:00, "the cascade is not handled"). The propagation is performed by `attribute_all` over the alerts of one care plan (EC D-1: the keys are per care plan). The fields are `Alert.caused_by` (on the effect: the `xi.instance_key` of the root) and `Alert.root_cause_of` (on the root: the keys of its effects).

**Template-level cascade table.** The decision times are `decided_at_ms` of the first VIOLATED record (EC: `Ue(i)`); the windows use the registry names `sched_window`, `hold_lookback`, `delta1` and `delta2` of T02 section 3.1 (per-patient values from the plan where it carries them: H-10). The temporal condition is the intersection of closed intervals.

| id | root | effect | datum that the root made missing | temporal condition |
|---|---|---|---|---|
| CT-1 | a VIOLATED `sched` instance with κ C1, C2 or C3 | a VIOLATED `resp` instance whose decisive sub-formula is a failed guard (`obligation_unmet`) | the measurement that the response check needs | the root interval, from its decision time minus `sched_window` to its decision time, meets the response window, from the effect's decision time minus (`delta2` minus `delta1`) to its decision time |
| CT-2 | the same root | a VIOLATED `hold` instance whose decisive sub-formula is a failed guard (`no_recent_measurement`) | the recent measurement that the hold check needs | the root interval meets the look-back, from the effect's decision time minus `hold_lookback` to its decision time |
| CT-3 (inactive) | the same root | the end-of-day measurement-count violation of analisi §4.6, row 15:00 | the measurements of the day | the template is not in the library (T02 section 4.4, CP2: a new template id and a new unit would need an ADR); the row exists so that adopting it needs no change of the rule; with seven `TemplateId` values it cannot fire |

**Rules.**

1. Only alerts of VIOLATED records take part. A predicted alert is never folded and never a root (F07 section 1.8, item 4).
2. A root has a definite κ of its own. A `sched` instance whose own κ is UNDETERMINED explains nothing: its candidate effects stay top-level, each with its own κ (AD-14; the cost is that alerts are not reduced in that case, the benefit is that no event is hidden under a cause that the rule did not determine).
3. **An effect is folded under a root only if its decisive datum is the one the root made missing.** The effect's decisive sub-formula must be a failed guard (no accepted measurement in its window). A `resp` or `hold` instance that has a measurement in its window and fails on the margin (an insufficient drop, a pressure below the threshold) has independent evidence and stays a top-level alert: a valid out-of-band measurement is not a cascade effect. The failed guard is read from the guard marker recoverable from `xi.subformula_path` (F07 section 1.4 item 2, OP-T07-6; the carrier is proposed in WS05-T04 step 8). Until the carrier exists the property is read from the record: the upper end of `sigma_interval` is minus infinity exactly when the decisive sub-formula is a failed guard (T02 section 2.1); it is a structural property of the sub-formula, not a severity, and it enters only the choice of links, never κ of the rule (H-11).
4. **Independent evidence.** An effect is also not folded when its own rule result is a definite class different from the root's κ (for example C3 from a failed verification against a C2 root): its evidence decides. An effect whose own result is UNDETERMINED or the root's class is folded.
5. **Root selection and tie-breaking.** Among the eligible roots of an effect the root with the smallest `decided_at_ms` is chosen; ties are broken by the smaller numeric `priority_<id>` of the root's template (1 is the highest), then by the lexicographically smaller `xi.instance_key`. The choice is a function of the set of alerts, independent of the order in which they are given. An effect has at most one root; the other eligible roots do not list it.
6. **Acyclicity.** Roots are `sched` alerts and effects are `resp` or `hold` alerts: an effect is never a root, the relation has depth one and cannot contain a cycle (invariant I6). A table with chains would have to keep this property by a check at load.
7. **Fields.** `caused_by` of the effect is the key of its root; `root_cause_of` of the root is the sorted tuple of the keys of its effects; the two are mutual inverses: `b.caused_by` equals `a.xi.instance_key` if and only if the key of `b` is in `a.root_cause_of`. A link can appear after the first issue of an alert; the alert is then issued again with only the link fields changed (F07 section 1.4, item 3).
8. **κ of an effect is the κ of its root.** `Explanation.evidence_used` of an effect is that of its root, and its text says that it follows from the root alert and names it; a root's text says how many further violations it accounts for (F07 section 3.4, item 11). An effect keeps its own σ̃, confidence, priority and time; nothing else is inherited.
9. **Folding hides and never deletes.** The effect remains an `Alert` returned by `attribute_all` and its `VerdictRecord` is untouched; a consumer that shows only the top-level list filters on `caused_by is None`.
10. **Not cascades.** Violations that share an emptied position but have no `sched` instance to name it (a cuff outage with no tick in the window) stay top-level, each with its own κ (FM CAS-1: a fan-out whose members do not cause one another). The duplicate instances of a dispenser bounce (FM CAS-3, M-DUPWIN) are not linked; the carry-over of the dose counter would be a `count` to `count` row that needs a root with a definite κ, which a `count` violation does not have while G-1 is open (AD-10).
11. A deliberate transition is not a root: a missed measurement after a commanded deactivation has κ UNDETERMINED (row 6, AD-7), so it seeds nothing (W-11-deliberate).

The worked case W-11 reproduces analisi §4.6, row 15:00 with the templates of the library.

## Predicted violations

**What the layer does.** `attribute_all` builds an alert for a record in either violation-claiming state (F07 AH-2): VIOLATED or PREDICTED_VIOLATION. For a PREDICTED_VIOLATION record it sets `kappa` and `label` to UNDETERMINED and `Explanation.evidence_used` to the empty list **without evaluating the rule**. The alert that supersedes it, issued when the same instance becomes VIOLATED, has the same `xi.instance_key`, replaces the predicted alert in the current set (the predicted alert stays in the history), and carries the κ of the rule on the evidence at the cut-off of the first VIOLATED record; a predicted alert whose instance ends SATISFIED is closed as a false predictive alarm and produces no attribution; an instance that stays undecided leaves its predicted alert open (F07 section 1.4, item 3, and CP13). A predicted alert takes no part in a cascade. The rule `attribute` stays pure: κ does not depend on `state` (invariant I1) and the test on the verdict state is made by `attribute_all`, the alert builder (F07 section 1.2 note 3, section 9 CP13 tension 5). The rule neither reads a prediction nor feeds one: ρ is not an input of κ, and κ is not an input of the confidence of a predicted alert.

**Deviation from the task text.** Check 8 and step 5 of the task propose that attribution runs on PREDICTED_VIOLATION records with a provisional κ from the evidence available at `t_eval_ms`, replaced when the definitive verdict arrives. This document adopts "replaced, not duplicated" and **does not adopt the provisional κ**, following F07 section 1.7 (CP13) and proposed ADR-041, which the task text itself asks to follow (hand-over of the WS01-T07 review). Reasons, from F07: (1) κ names the cause of a violation and at the prediction instant there is none (the verdict is "early warning, never definitive"); (2) the evidence is not there yet in the main predictive case: the overrun report of a late robot task is stamped at the deadline (EC H-OVERRUN), after the evidence window of an undecided record, so the rule would find no system evidence and, with the channels coherent, reach C1 for a warning that the robot will be late; (3) the attribution metrics of WS08 (E3, E4) would count a pair matched by a predicted alert as an abstention by construction, so they read the label from the superseding alert (OP-T07-10); (4) the plan scenario R5 of WS01-T08 assumes UNDETERMINED. Not adopted, as a possible refinement if the benchmark shows a gain: a provisional κ restricted to C2 and C3 when system or integrity evidence is already asserted. **Dependency:** this section rests on ADR-041, which is proposed; if it were rejected in favour of a provisional κ, only this section and the builder change: the table is the same function of the evidence vector that EC D-1 already builds for a predicted record (with `t_eval_ms` as the last admissible evidence time) and that is unused today. WS05-T07 tests 18, 20 and 25 assume a provisional κ and must follow this section (recorded in the section Traceability).

## Action policy

**WS02 proposal for clinician review (WS00-T07).** Analisi §4.9 item 4 fixes the principle and the three robot actions and does not fix the mapping: "safety actions are themselves hazards: blocking the dispenser or interrupting a procedure can cause missed doses; clinical actions need an explicit clinician-in-the-loop principle, and autonomy limited to the robot's actions (stop, retry, call)". The table below is a proposal of WS02, not a clinically validated policy. ADR-043 (accepted) decouples the freeze of the formalization from the clinician review, which remains a pre-submission item (WS00-T07); the review and the lab safety review (WS10-T01) are open points of this document (OP-AR-8), not a gate, and no sentence of it claims clinical validation.

| κ | automatic robot actions allowed (only these three exist) | clinical actions: block the dispenser, withhold or change a dose, interrupt a procedure | if the robot is unavailable |
|---|---|---|---|
| C1 | `call` (notify the nurse); no `stop`, no `retry` | never automatic; offered to the clinician, who confirms | the ward node escalates to the nurse (ADR-003) |
| C2 | `stop` of the robot's own operation when the decisive evidence is about the robot (its task outcomes or its lifecycle); `retry` of a failed robot task of the care plan; `call` | never automatic; offered to the clinician, who confirms | as above |
| C3 | `call`; `stop` of a robot task that depends on the suspect input | never automatic; offered to the clinician, who confirms | as above |
| UNDETERMINED | `call` (ask the nurse to verify); no `stop`, no `retry` | never automatic; offered to the clinician, who confirms | as above |

Notes. (1) The automatic actions are exactly `stop`, `retry` and `call`; any other action is a clinical or care-plan action and needs the clinician's confirmation. (2) Clinical actions are **never automatic**, for every κ and for a predicted alert (which has κ UNDETERMINED): a blocked dispenser can cause a missed dose and an interrupted procedure can harm, so a safety action is itself a hazard and is treated as one in the hazard register of WS02-T05 (analisi §4.9 item 4; R3 weakness 4, translated: blocking the dispenser after the fact mitigates nothing, and blocking medication is itself a hazard). Which clinical action is offered for which κ is not fixed here (OP-AR-8). (3) The number of `retry` attempts and the conditions of `stop` are parameters of the robot layer (WS07, WS10), not set here. (4) The fallback when the robot is unavailable is escalation to the nurse by the ward node (ADR-003, analisi §4.9 item 1); `call` is then performed by the ward node. (5) κ never suppresses an alert, and an alert is always shown to staff: the table limits what the robot does by itself, not what staff are told. (6) DISPENSE is not INTAKE: no action is justified by the statement that a dose was taken because the dispenser opened.

## Invariants

The six invariants are stated for the rule and for `attribute_all` where they say so; WS05-T07 lifts them into property tests (Hypothesis-style) and the worked cases into fixtures. They were verified by the scratch scripts of the section Decision table on every combination of the relevant fields (and, for I6, on random sets of records).

- I1 purity: for a fixed template and a fixed `EvidenceVector`, `HierarchicalRule.attribute` returns the same κ, row, reason and `evidence_used` whatever the other fields of the `VerdictRecord` hold (σ̃ and the raw interval, `state`, `t_eval_ms`, `decided_at_ms`, `pending_until_ms`, and ρ, which is not an input and whose field is never read); the test varies those fields with Hypothesis (WS05-T07 test 5 is scoped to the rule; the PREDICTED_VIOLATION state check sits in `attribute_all`); verified by construction, since the scratch function takes only the template and the readings of the relevant fields.
- I2 precedence: if IE-1, IE-2 or IE-3 holds (integrity evidence asserted and not explained away), κ is C3 whatever the other fields say; verified exhaustively, with no violation in 87,351,696 combinations, and with the overlap of integrity and system evidence exercised (30,155,328 combinations of `resp` alone).
- I3 provenance is never sufficient: with all 18 non-provenance fields `None`, κ is UNDETERMINED for every `TemplateId` (reason insufficient for `range`, `sched`, `hold`, `count`, `resp`, provenance-only for `sys` and `int`), and so is an absent evidence key; C2 and C3 need an asserted field outside `provenance`; verified for the seven templates (W-12).
- I4 no certainty from missing data: (a) setting any field to `None` never turns UNDETERMINED into a definite class; (b) setting any field to `None` never turns a non-C1 result into C1, except for the field `crypto_temporal.authenticated`, whose `None` is the unauthenticated deployment (AD-8); verified exhaustively: (a) no violation in any template; (b) violations only for that field, 9 combinations in `range`, 1 in `sched`, 9 in `hold` and 9 in `resp`, each a C3 from a failed verification with every other required channel clean; the unrestricted form of (b) would make C1 unreachable in the unauthenticated deployment, against the matrix row 10 and TM-OP-11, so it is restated here and not enforced; the test runs over all fields but that one and checks W-08 and W-10-A explicitly.
- I5 locality: masking (setting to `None`) a field that is neither decisive for the result (`evidence_used`) nor in the exclusion set of the template leaves κ unchanged; verified exhaustively, with no violation; it is what makes the A4 mask analysable: the path mask changes κ only through `system.nav_task_failed`, `system.manip_task_failed` and the witness backing of `resp` (section C1 exclusion conditions).
- I6 cascade consistency: the relation `caused_by` over the alerts of `attribute_all` is acyclic, `caused_by` and `root_cause_of` are mutual inverses, an effect never has a κ different from its root's, only VIOLATED alerts take part, an effect with independent evidence stays top-level, and the output is independent of the order of the input; verified on 200,000 random sets of records (14,914 links made) with no violation.

The statements about missing data are the ones the A4 ablation depends on: with the embodied channel removed the rule can lose C1 and C2 but never gains a definite class (the transition table in the section C1 exclusion conditions).

## Worked cases

Each case is a table that WS05-T07 lifts into a fixture: the template (`provenance.violated_template`), the kind (`provenance.template_kind`), the fields that are not `None` with their values, every other field `None`, the expected κ, the decisive fields in precedence order, and for UNDETERMINED the reason. The expected values were computed with the scalar implementation of the table and, for the cases marked "checked by hand: yes", by hand (derivations after the cases). Conventions. (1) A float or string reading is given by its relation to the named registry threshold: "at or above `ecg_sqi_floor`" is any value that satisfies the relation, chosen by the fixture builder; `system.ble_link_quality` complete is exactly 1.0; the empty string is the denied `signal_quality.cuff_error_code`; `"E1"` is a device-defined label and never a clinical value. No fixture carries a clinical value. (2) `system.node_lifecycle` lists the nodes of the scope of the template (EC scope table): `cuff` for `range` and `sys`, `cuff` and `robot` for `sched`, `cuff`, `dispenser` and `robot` for `hold` and `resp`, `dispenser` for `count`, `dispenser` and `robot` for `int`. (3) A **variant** is the base case with the listed fields replaced (`None` removes the field); its template is the base template unless the variant has its own tables. (4) The source of W-01 to W-10 is the row of the diagnosability matrix; the "matrix verdict" is the verdict of that row and "table against matrix" says whether the table agrees, and where it differs the difference is recorded in the case and in the section Traceability. (5) The A4 variants apply the None class of the A4 mask of EC (the three `witness` fields, `system.nav_task_failed`, `system.manip_task_failed`, `system.battery_low`) and leave the recomputed aggregates as the case says. (6) Instance keys such as `sched@09:00` are illustrative (H-14). (7) The cases use authenticated and unauthenticated deployments (`crypto_temporal.authenticated` `None`) as named.


### W-01

Real hypertension: every channel the table reads is available and denied. `crypto_temporal.authenticated` is True here (authenticated deployment).

| item | value |
|---|---|
| source | analisi §4.5 row 1 |
| `provenance.violated_template` | `range` |
| `provenance.template_kind` | phi_cp (`TemplateKind.CARE_PLAN`) |
| expected κ | C1 |
| decisive fields, precedence order | `system.node_lifecycle`, `system.diagnostics_ok`, `system.liveliness_ok`, `system.qos_deadline_missed`, `system.ble_link_quality`, `signal_quality.cuff_error_code`, `cross_device.pulse_vs_ecg_hr_diff`, `crypto_temporal.authenticated`, `crypto_temporal.seq_gap_or_replay`, `crypto_temporal.timestamp_implausible` |
| reason (UNDETERMINED only) | not applicable |
| table row | 5 |
| matrix verdict | yes, by exclusion |
| table against matrix | agrees |
| checked by hand | yes |

| field | value | reading |
|---|---|---|
| `system.node_lifecycle` | `{"cuff": "active"}` | denied |
| `system.diagnostics_ok` | `True` | denied |
| `system.liveliness_ok` | `True` | denied |
| `system.qos_deadline_missed` | `False` | denied |
| `system.ble_link_quality` | `1.0` | denied (complete) |
| `signal_quality.ecg_sqi` | at or above `ecg_sqi_floor` | denied |
| `signal_quality.ppg_sqi` | at or above `ppg_sqi_floor` | denied |
| `signal_quality.cuff_error_code` | `"" (empty string)` | denied |
| `cross_device.pulse_vs_ecg_hr_diff` | within `hr_coherence_tolerance` | denied |
| `crypto_temporal.authenticated` | `True` | denied |
| `crypto_temporal.seq_gap_or_replay` | `False` | denied |
| `crypto_temporal.timestamp_implausible` | `False` | denied |

Every other field is `None`.

### W-02

Drug non-response, unauthenticated deployment, backing by the robot witness: intake observed and identity confirmed.

| item | value |
|---|---|
| source | analisi §4.5 row 2 |
| `provenance.violated_template` | `resp` |
| `provenance.template_kind` | phi_cp (`TemplateKind.CARE_PLAN`) |
| expected κ | C1 |
| decisive fields, precedence order | `system.node_lifecycle`, `system.diagnostics_ok`, `system.liveliness_ok`, `system.qos_deadline_missed`, `system.ble_link_quality`, `system.nav_task_failed`, `system.manip_task_failed`, `signal_quality.cuff_error_code`, `cross_device.pulse_vs_ecg_hr_diff`, `witness.identity_confirmed`, `witness.intake_observed`, `crypto_temporal.seq_gap_or_replay`, `crypto_temporal.timestamp_implausible` |
| reason (UNDETERMINED only) | not applicable |
| table row | 5 |
| matrix verdict | conditional: only if there is a witness |
| table against matrix | agrees |
| checked by hand | no (scratch implementation) |

| field | value | reading |
|---|---|---|
| `system.node_lifecycle` | `{"cuff": "active", "dispenser": "active", "robot": "active"}` | denied |
| `system.diagnostics_ok` | `True` | denied |
| `system.liveliness_ok` | `True` | denied |
| `system.qos_deadline_missed` | `False` | denied |
| `system.ble_link_quality` | `1.0` | denied (complete) |
| `system.nav_task_failed` | `False` | denied |
| `system.manip_task_failed` | `False` | denied |
| `signal_quality.ecg_sqi` | at or above `ecg_sqi_floor` | denied |
| `signal_quality.ppg_sqi` | at or above `ppg_sqi_floor` | denied |
| `signal_quality.cuff_error_code` | `"" (empty string)` | denied |
| `cross_device.pulse_vs_ecg_hr_diff` | within `hr_coherence_tolerance` | denied |
| `witness.identity_confirmed` | `True` | denied |
| `witness.intake_observed` | `True` | denied |
| `crypto_temporal.seq_gap_or_replay` | `False` | denied |
| `crypto_temporal.timestamp_implausible` | `False` | denied |

Every other field is `None`.

| variant | change from the base case | expected κ | decisive fields | reason | row |
|---|---|---|---|---|---|
| W-02-A4 | the embodied channel removed (the None class of the A4 mask); the aggregates are recomputed from the device nodes and stay denied (`system.nav_task_failed` None; `system.manip_task_failed` None; `witness.identity_confirmed` None; `witness.intake_observed` None) | UNDETERMINED | none (`evidence_used` empty) | insufficient | 8 |
| W-02-auth | authenticated deployment, robot channel not co-located: no witness (`crypto_temporal.authenticated` `True`; `witness.identity_confirmed` None; `witness.intake_observed` None) | C1 | `system.node_lifecycle`, `system.diagnostics_ok`, `system.liveliness_ok`, `system.qos_deadline_missed`, `system.ble_link_quality`, `system.nav_task_failed`, `system.manip_task_failed`, `signal_quality.cuff_error_code`, `cross_device.pulse_vs_ecg_hr_diff`, `crypto_temporal.authenticated`, `crypto_temporal.seq_gap_or_replay`, `crypto_temporal.timestamp_implausible` | not applicable | 5 |
| W-02-nowit | unauthenticated deployment and no witness (`witness.identity_confirmed` None; `witness.intake_observed` None) | UNDETERMINED | none (`evidence_used` empty) | insufficient | 8 |
| W-02-witness-only | only the witness fields removed (the variant `EMBODIED_MASK_WITNESS` of EC) (`witness.identity_confirmed` None; `witness.intake_observed` None) | UNDETERMINED | none (`evidence_used` empty) | insufficient | 8 |
| W-02-auth-A4 | authenticated deployment, no witness, the embodied channel removed: the robot task outcomes are None as well (`crypto_temporal.authenticated` `True`; `witness.identity_confirmed` None; `witness.intake_observed` None; `system.nav_task_failed` None; `system.manip_task_failed` None) | UNDETERMINED | none (`evidence_used` empty) | insufficient | 8 |

### W-03

Cuff detached, variant that still reports a measurement (G-SYS-3): the violated predicate is the cuff health, the independent evidence is the device error code and the node state.

| item | value |
|---|---|
| source | analisi §4.5 row 3 |
| `provenance.violated_template` | `sys` |
| `provenance.template_kind` | phi_sys (`TemplateKind.SYSTEM`) |
| expected κ | C2 |
| decisive fields, precedence order | `system.node_lifecycle`, `signal_quality.cuff_error_code` |
| reason (UNDETERMINED only) | not applicable |
| table row | 4 |
| matrix verdict | yes |
| table against matrix | agrees |
| checked by hand | yes |

| field | value | reading |
|---|---|---|
| `system.node_lifecycle` | `{"cuff": "inactive"}` | asserted |
| `system.diagnostics_ok` | `True` | denied |
| `system.liveliness_ok` | `True` | denied |
| `system.qos_deadline_missed` | `False` | denied |
| `system.ble_link_quality` | `1.0` | denied (complete) |
| `signal_quality.ecg_sqi` | at or above `ecg_sqi_floor` | denied |
| `signal_quality.ppg_sqi` | at or above `ppg_sqi_floor` | denied |
| `signal_quality.cuff_error_code` | `"E1" (device label)` | asserted |
| `cross_device.pulse_vs_ecg_hr_diff` | within `hr_coherence_tolerance` | denied |
| `crypto_temporal.authenticated` | `True` | denied |
| `crypto_temporal.seq_gap_or_replay` | `False` | denied |
| `crypto_temporal.timestamp_implausible` | `False` | denied |

Every other field is `None`.

Variant W-03-sched: the injected form of `cuff_detached`: a `sched` instance with the same evidence and the robot outcomes denied.

| item | value |
|---|---|
| `provenance.violated_template` | `sched` |
| `provenance.template_kind` | phi_cp (`TemplateKind.CARE_PLAN`) |
| expected κ | C2 |
| decisive fields, precedence order | `system.node_lifecycle`, `signal_quality.cuff_error_code` |
| reason (UNDETERMINED only) | not applicable |
| table row | 4 |

| field | value | reading |
|---|---|---|
| `system.node_lifecycle` | `{"cuff": "inactive", "robot": "active"}` | asserted |
| `system.diagnostics_ok` | `True` | denied |
| `system.liveliness_ok` | `True` | denied |
| `system.qos_deadline_missed` | `False` | denied |
| `system.ble_link_quality` | `1.0` | denied (complete) |
| `system.nav_task_failed` | `False` | denied |
| `system.manip_task_failed` | `False` | denied |
| `signal_quality.cuff_error_code` | `"E1" (device label)` | asserted |
| `crypto_temporal.authenticated` | `True` | denied |
| `crypto_temporal.seq_gap_or_replay` | `False` | denied |
| `crypto_temporal.timestamp_implausible` | `False` | denied |

Every other field is `None`.

### W-04

Silent cuff bias or stuck value: no field is raised, the pulse rate stays coherent. The vector equals W-01, so is the result: C1, the declared limit.

| item | value |
|---|---|
| source | analisi §4.5 row 4 |
| `provenance.violated_template` | `range` |
| `provenance.template_kind` | phi_cp (`TemplateKind.CARE_PLAN`) |
| expected κ | C1 |
| decisive fields, precedence order | `system.node_lifecycle`, `system.diagnostics_ok`, `system.liveliness_ok`, `system.qos_deadline_missed`, `system.ble_link_quality`, `signal_quality.cuff_error_code`, `cross_device.pulse_vs_ecg_hr_diff`, `crypto_temporal.authenticated`, `crypto_temporal.seq_gap_or_replay`, `crypto_temporal.timestamp_implausible` |
| reason (UNDETERMINED only) | not applicable |
| table row | 5 |
| matrix verdict | no (declared limit) |
| table against matrix | agrees (same vector as W-01) |
| checked by hand | no (scratch implementation) |

| field | value | reading |
|---|---|---|
| `system.node_lifecycle` | `{"cuff": "active"}` | denied |
| `system.diagnostics_ok` | `True` | denied |
| `system.liveliness_ok` | `True` | denied |
| `system.qos_deadline_missed` | `False` | denied |
| `system.ble_link_quality` | `1.0` | denied (complete) |
| `signal_quality.ecg_sqi` | at or above `ecg_sqi_floor` | denied |
| `signal_quality.ppg_sqi` | at or above `ppg_sqi_floor` | denied |
| `signal_quality.cuff_error_code` | `"" (empty string)` | denied |
| `cross_device.pulse_vs_ecg_hr_diff` | within `hr_coherence_tolerance` | denied |
| `crypto_temporal.authenticated` | `True` | denied |
| `crypto_temporal.seq_gap_or_replay` | `False` | denied |
| `crypto_temporal.timestamp_implausible` | `False` | denied |

Every other field is `None`.

### W-05

Robot late to the window: the navigation outcome `late`, stamped at the deadline (H-OVERRUN of evidence-channels.md); the cuff is healthy. The profile declares no diagnostics, no deadline and no independent clocks, so `system.diagnostics_ok`, `system.qos_deadline_missed` and `crypto_temporal.timestamp_implausible` are None.

| item | value |
|---|---|
| source | analisi §4.5 row 5 |
| `provenance.violated_template` | `sched` |
| `provenance.template_kind` | phi_cp (`TemplateKind.CARE_PLAN`) |
| expected κ | C2 |
| decisive fields, precedence order | `system.nav_task_failed` |
| reason (UNDETERMINED only) | not applicable |
| table row | 4 |
| matrix verdict | yes (A4: partial) |
| table against matrix | agrees |
| checked by hand | yes |

| field | value | reading |
|---|---|---|
| `system.node_lifecycle` | `{"cuff": "active", "robot": "active"}` | denied |
| `system.liveliness_ok` | `True` | denied |
| `system.ble_link_quality` | `1.0` | denied (complete) |
| `system.nav_task_failed` | `True` | asserted |
| `system.manip_task_failed` | `False` | denied |
| `signal_quality.cuff_error_code` | `"" (empty string)` | denied |
| `crypto_temporal.seq_gap_or_replay` | `False` | denied |

Every other field is `None`.

| variant | change from the base case | expected κ | decisive fields | reason | row |
|---|---|---|---|---|---|
| W-05-A4 | the embodied channel removed (None class of the A4 mask) (`system.nav_task_failed` None; `system.manip_task_failed` None) | UNDETERMINED | none (`evidence_used` empty) | insufficient | 8 |
| W-05-live | robot crash instead of a late arrival (EC-OP-17): the aggregate is False because of the robot node, and a crash leaves no task outcome (`system.nav_task_failed` None; `system.manip_task_failed` None; `system.liveliness_ok` `False`) | C2 | `system.liveliness_ok` | not applicable | 4 |
| W-05-live-A4 | the same crash under A4: the aggregate is recomputed over the device nodes and is True (`system.nav_task_failed` None; `system.manip_task_failed` None) | UNDETERMINED | none (`evidence_used` empty) | insufficient | 8 |
| W-05-silent | patient refusal pattern, cuff silent, without ADR-040 (decision AD-12): navigation succeeded, no manipulation outcome, every message-derived field None (`system.nav_task_failed` `False`; `system.manip_task_failed` None; `signal_quality.cuff_error_code` None; `crypto_temporal.seq_gap_or_replay` None; `system.ble_link_quality` None) | UNDETERMINED | none (`evidence_used` empty) | insufficient | 8 |
| W-05-silent-040 | the same with ADR-040 accepted: the `declined` outcome makes the manipulation field False (`system.nav_task_failed` `False`; `system.manip_task_failed` `False`; `signal_quality.cuff_error_code` None; `crypto_temporal.seq_gap_or_replay` None; `system.ble_link_quality` None) | UNDETERMINED | none (`evidence_used` empty) | insufficient | 8 |
| W-05-late-patient | the patient delayed the measurement, which arrives after the deadline: the cuff messages exist and every channel is clean (`system.diagnostics_ok` `True`; `system.qos_deadline_missed` `False`; `crypto_temporal.timestamp_implausible` `False`; `system.nav_task_failed` `False`; `system.manip_task_failed` `False`) | C1 | `system.node_lifecycle`, `system.diagnostics_ok`, `system.liveliness_ok`, `system.qos_deadline_missed`, `system.ble_link_quality`, `system.nav_task_failed`, `system.manip_task_failed`, `signal_quality.cuff_error_code`, `crypto_temporal.seq_gap_or_replay`, `crypto_temporal.timestamp_implausible` | not applicable | 5 |
| W-05-deliberate | the cuff node deactivated by a command before the tick (analisi §4.6, row 15:00) (`system.node_lifecycle` `{"cuff": "inactive+commanded", "robot": "active"}`; `system.nav_task_failed` `False`; `system.manip_task_failed` `False`) | UNDETERMINED | `system.node_lifecycle` | conflict | 6 |

### W-06

Double take by the patient: the dispenser-link channels are clean, nothing separates a double take from a bounce.

| item | value |
|---|---|
| source | analisi §4.5 row 6 |
| `provenance.violated_template` | `count` |
| `provenance.template_kind` | phi_cp (`TemplateKind.CARE_PLAN`) |
| expected κ | UNDETERMINED |
| decisive fields, precedence order | none (`evidence_used` empty) |
| reason (UNDETERMINED only) | insufficient |
| table row | 8 |
| matrix verdict | yes, if the dispenser measures content |
| table against matrix | DIFFERS: the table gives UNDETERMINED (insufficient); the content evidence has no field in contract 0.1.0 (G-1, ADR-032 proposed) |
| checked by hand | no (scratch implementation) |

| field | value | reading |
|---|---|---|
| `system.node_lifecycle` | `{"dispenser": "active"}` | denied |
| `system.diagnostics_ok` | `True` | denied |
| `system.liveliness_ok` | `True` | denied |
| `system.qos_deadline_missed` | `False` | denied |
| `system.ble_link_quality` | `1.0` | denied (complete) |
| `crypto_temporal.authenticated` | `True` | denied |
| `crypto_temporal.seq_gap_or_replay` | `False` | denied |
| `crypto_temporal.timestamp_implausible` | `False` | denied |

Every other field is `None`.

### W-07

Dispenser sensor bounce: the evidence that separates it (interval and content change) has no field, so the vector equals that of W-06.

| item | value |
|---|---|
| source | analisi §4.5 row 7 |
| `provenance.violated_template` | `count` |
| `provenance.template_kind` | phi_cp (`TemplateKind.CARE_PLAN`) |
| expected κ | UNDETERMINED |
| decisive fields, precedence order | none (`evidence_used` empty) |
| reason (UNDETERMINED only) | insufficient |
| table row | 8 |
| matrix verdict | yes (interval and content change) |
| table against matrix | DIFFERS: same vector as W-06, same result (G-1, ADR-032 proposed) |
| checked by hand | no (scratch implementation) |

| field | value | reading |
|---|---|---|
| `system.node_lifecycle` | `{"dispenser": "active"}` | denied |
| `system.diagnostics_ok` | `True` | denied |
| `system.liveliness_ok` | `True` | denied |
| `system.qos_deadline_missed` | `False` | denied |
| `system.ble_link_quality` | `1.0` | denied (complete) |
| `crypto_temporal.authenticated` | `True` | denied |
| `crypto_temporal.seq_gap_or_replay` | `False` | denied |
| `crypto_temporal.timestamp_implausible` | `False` | denied |

Every other field is `None`.

### W-08

Replay with rewritten metadata in an authenticated deployment: the verification of the message fails.

| item | value |
|---|---|
| source | analisi §4.5 row 8 |
| `provenance.violated_template` | `range` |
| `provenance.template_kind` | phi_cp (`TemplateKind.CARE_PLAN`) |
| expected κ | C3 |
| decisive fields, precedence order | `crypto_temporal.authenticated` |
| reason (UNDETERMINED only) | not applicable |
| table row | 1 |
| matrix verdict | yes with authentication, partial without |
| table against matrix | agrees |
| checked by hand | no (scratch implementation) |

| field | value | reading |
|---|---|---|
| `system.node_lifecycle` | `{"cuff": "active"}` | denied |
| `system.diagnostics_ok` | `True` | denied |
| `system.liveliness_ok` | `True` | denied |
| `system.qos_deadline_missed` | `False` | denied |
| `system.ble_link_quality` | `1.0` | denied (complete) |
| `signal_quality.ecg_sqi` | at or above `ecg_sqi_floor` | denied |
| `signal_quality.ppg_sqi` | at or above `ppg_sqi_floor` | denied |
| `signal_quality.cuff_error_code` | `"" (empty string)` | denied |
| `cross_device.pulse_vs_ecg_hr_diff` | within `hr_coherence_tolerance` | denied |
| `crypto_temporal.authenticated` | `False` | asserted |
| `crypto_temporal.seq_gap_or_replay` | `False` | denied |
| `crypto_temporal.timestamp_implausible` | `False` | denied |

Every other field is `None`.

| variant | change from the base case | expected κ | decisive fields | reason | row |
|---|---|---|---|---|---|
| W-08-U | unauthenticated deployment, naive replay of the previous day from a device that provides `seq` (`crypto_temporal.authenticated` None; `crypto_temporal.seq_gap_or_replay` `True`; `crypto_temporal.timestamp_implausible` `True`) | C3 | `system.ble_link_quality`, `crypto_temporal.seq_gap_or_replay` | not applicable | 2 |
| W-08-U-noseq | the same replay from a device that provides no `seq` (`crypto_temporal.authenticated` None; `crypto_temporal.seq_gap_or_replay` None; `system.ble_link_quality` None; `crypto_temporal.timestamp_implausible` `True`) | UNDETERMINED | `crypto_temporal.timestamp_implausible` | conflict | 6 |

### W-09

Forged dispense, robot co-located, nobody perceived, unauthenticated: the witness pair restates the violation of the INT predicate (context, not read, decision (a)). The same vector arises from a lost presence sample (CAS-5 of fault-model.md).

| item | value |
|---|---|
| source | analisi §4.5 row 9 |
| `provenance.violated_template` | `int` |
| `provenance.template_kind` | phi_int (`TemplateKind.INTEGRITY`) |
| expected κ | UNDETERMINED |
| decisive fields, precedence order | none (`evidence_used` empty) |
| reason (UNDETERMINED only) | provenance-only |
| table row | 7 |
| matrix verdict | partial |
| table against matrix | agrees (abstention) |
| checked by hand | yes |

| field | value | reading |
|---|---|---|
| `system.node_lifecycle` | `{"dispenser": "active", "robot": "active"}` | denied |
| `system.diagnostics_ok` | `True` | denied |
| `system.liveliness_ok` | `True` | denied |
| `system.qos_deadline_missed` | `False` | denied |
| `system.ble_link_quality` | `1.0` | denied (complete) |
| `system.nav_task_failed` | `False` | denied |
| `system.manip_task_failed` | `False` | denied |
| `witness.robot_present` | `False` | asserted, context, not read |
| `witness.intake_observed` | `False` | asserted, context, not read |
| `crypto_temporal.seq_gap_or_replay` | `False` | denied |
| `crypto_temporal.timestamp_implausible` | `False` | denied |

Every other field is `None`.

| variant | change from the base case | expected κ | decisive fields | reason | row |
|---|---|---|---|---|---|
| W-09-A4 | the embodied channel removed (WS08-T04 test 6 expects a loss here: none occurs) (`system.nav_task_failed` None; `system.manip_task_failed` None) | UNDETERMINED | none (`evidence_used` empty) | provenance-only | 7 |
| W-09-A | synthesised forgery in an authenticated deployment (`crypto_temporal.authenticated` `False`) | C3 | `crypto_temporal.authenticated` | not applicable | 1 |
| W-09-lag | robot outage whose availability mask lags (FM hypothesis 9), the watchdog lapse lies before the cut-off (`system.liveliness_ok` `False`) | C2 | `system.liveliness_ok` | not applicable | 4 |
| W-09-lag-late | the same outage, the lapse is detected after the last admissible evidence time (no field changes) | UNDETERMINED | none (`evidence_used` empty) | provenance-only | 7 |

Variant W-09-resp: the response part of row 9: a `resp` instance violated at the end of its window, the robot co-located throughout and no intake observed, unauthenticated.

| item | value |
|---|---|
| `provenance.violated_template` | `resp` |
| `provenance.template_kind` | phi_cp (`TemplateKind.CARE_PLAN`) |
| expected κ | UNDETERMINED |
| decisive fields, precedence order | `witness.intake_observed` |
| reason (UNDETERMINED only) | conflict |
| table row | 6 |

| field | value | reading |
|---|---|---|
| `system.node_lifecycle` | `{"cuff": "active", "dispenser": "active", "robot": "active"}` | denied |
| `system.diagnostics_ok` | `True` | denied |
| `system.liveliness_ok` | `True` | denied |
| `system.qos_deadline_missed` | `False` | denied |
| `system.ble_link_quality` | `1.0` | denied (complete) |
| `system.nav_task_failed` | `False` | denied |
| `system.manip_task_failed` | `False` | denied |
| `signal_quality.ecg_sqi` | at or above `ecg_sqi_floor` | denied |
| `signal_quality.ppg_sqi` | at or above `ppg_sqi_floor` | denied |
| `signal_quality.cuff_error_code` | `"" (empty string)` | denied |
| `cross_device.pulse_vs_ecg_hr_diff` | within `hr_coherence_tolerance` | denied |
| `witness.intake_observed` | `False` | asserted |
| `crypto_temporal.seq_gap_or_replay` | `False` | denied |
| `crypto_temporal.timestamp_implausible` | `False` | denied |

Every other field is `None`.

### W-10

Informed injection coherent on every channel, unauthenticated deployment (`crypto_temporal.authenticated` None): the vector equals a clinical day.

| item | value |
|---|---|
| source | analisi §4.5 row 10 |
| `provenance.violated_template` | `range` |
| `provenance.template_kind` | phi_cp (`TemplateKind.CARE_PLAN`) |
| expected κ | C1 |
| decisive fields, precedence order | `system.node_lifecycle`, `system.diagnostics_ok`, `system.liveliness_ok`, `system.qos_deadline_missed`, `system.ble_link_quality`, `signal_quality.cuff_error_code`, `cross_device.pulse_vs_ecg_hr_diff`, `crypto_temporal.seq_gap_or_replay`, `crypto_temporal.timestamp_implausible` |
| reason (UNDETERMINED only) | not applicable |
| table row | 5 |
| matrix verdict | no, by construction |
| table against matrix | agrees (masquerades as C1) |
| checked by hand | yes |

| field | value | reading |
|---|---|---|
| `system.node_lifecycle` | `{"cuff": "active"}` | denied |
| `system.diagnostics_ok` | `True` | denied |
| `system.liveliness_ok` | `True` | denied |
| `system.qos_deadline_missed` | `False` | denied |
| `system.ble_link_quality` | `1.0` | denied (complete) |
| `signal_quality.ecg_sqi` | at or above `ecg_sqi_floor` | denied |
| `signal_quality.ppg_sqi` | at or above `ppg_sqi_floor` | denied |
| `signal_quality.cuff_error_code` | `"" (empty string)` | denied |
| `cross_device.pulse_vs_ecg_hr_diff` | within `hr_coherence_tolerance` | denied |
| `crypto_temporal.seq_gap_or_replay` | `False` | denied |
| `crypto_temporal.timestamp_implausible` | `False` | denied |

Every other field is `None`.

| variant | change from the base case | expected κ | decisive fields | reason | row |
|---|---|---|---|---|---|
| W-10-A | BLE injection in an authenticated deployment (the attacker holds no key, H-KEY of threat-model.md) (`crypto_temporal.authenticated` `False`) | C3 | `crypto_temporal.authenticated` | not applicable | 1 |

### W-11

The cascade of analisi §4.6, row 15:00: a missed measurement, the response check that cannot be verified and the hold check that needs a recent measurement, with the templates of the library (the end-of-day measurement-count template is not in it: row CT-3, deviation 4). Fixture registry F0 values for `sched_window`, `hold_lookback`, `delta1` and `delta2` (FIXTURE-ONLY): the root window is 09:00 to 09:30, the window of the `resp` instance of the 07:00 dispense is 08:00 to 10:00 and the look-back of the `hold` instance of the 09:45 dispense is 08:45 to 09:45. The cuff process stops before the tick (a crash is a lapse of liveliness, not a lifecycle transition). Checked by hand: yes (CT-1, CT-2, rules 3 to 5 of the cascade section).

| instance key | template | state | decision time | decisive sub-formula | fields that are not `None` (every other field `None`) | κ of the rule on its own evidence | alert after the cascade: κ, `caused_by`, `root_cause_of` |
|---|---|---|---|---|---|---|---|
| `sched@09:00` | `sched` | VIOLATED | 09:30 | failed guard `no_measurement_after_tick` | `system.node_lifecycle` `{"cuff": "active", "robot": "active"}` (denied), `system.liveliness_ok` False (asserted) | C2, row 4, `system.liveliness_ok` | C2, none, (`hold@09:45`, `resp@07:00`) |
| `resp@07:00` | `resp` | VIOLATED | 10:00 | failed guard `obligation_unmet` | the same two readings | C2 | C2, `sched@09:00`, () |
| `hold@09:45` | `hold` | VIOLATED | 09:45 | failed guard `no_recent_measurement` | the same two readings | C2 | C2, `sched@09:00`, () |
| `resp@07:30` | `resp` | VIOLATED | 10:30 | margin (a measurement exists in its window, the drop is insufficient) | every field of the exclusion set of `resp` denied, authentication denied | C1 | C1, none, () (independent evidence: a valid measurement in the window is not a cascade effect) |

The two effects keep their own σ̃, confidence and priority, are returned by `attribute_all` and are not top-level (`caused_by` is not `None`); the effect `resp@07:30` is top-level.

| variant | change | outcome |
|---|---|---|
| W-11-deliberate | the cuff node was deactivated by a command: `system.node_lifecycle` `{"cuff": "inactive+commanded", "robot": "active"}` instead of the liveliness lapse, in the root and in `resp@07:00` | the root has κ UNDETERMINED (row 6, reason conflict, AD-7): it seeds nothing; `resp@07:00` has κ UNDETERMINED and stays top-level; no `caused_by`, empty `root_cause_of` |
| W-11-c3 | `resp@07:00` also has `crypto_temporal.authenticated` False | its own result is C3 (row 1), different from the root's C2: independent evidence, it stays top-level with κ C3 |
| W-11-predicted | `resp@07:00` is in the state PREDICTED_VIOLATION | its alert has κ UNDETERMINED (section Predicted violations), no link, `caused_by` none, and it is not in the `root_cause_of` of the root |

### W-12

Every non-provenance field `None`, for each template (invariant I3, the evidence key absent). Checked by hand: yes (no row 1 to 5 can fire without an asserted or denied reading; row 8 or row 7 remains).

| `provenance.violated_template` | `provenance.template_kind` | expected κ | decisive fields | reason | table row |
|---|---|---|---|---|---|
| `range` | phi_cp (`TemplateKind.CARE_PLAN`) | UNDETERMINED | none | insufficient | 8 |
| `sched` | phi_cp (`TemplateKind.CARE_PLAN`) | UNDETERMINED | none | insufficient | 8 |
| `hold` | phi_cp (`TemplateKind.CARE_PLAN`) | UNDETERMINED | none | insufficient | 8 |
| `count` | phi_cp (`TemplateKind.CARE_PLAN`) | UNDETERMINED | none | insufficient | 8 |
| `resp` | phi_cp (`TemplateKind.CARE_PLAN`) | UNDETERMINED | none | insufficient | 8 |
| `sys` | phi_sys (`TemplateKind.SYSTEM`) | UNDETERMINED | none | provenance-only | 7 |
| `int` | phi_int (`TemplateKind.INTEGRITY`) | UNDETERMINED | none | provenance-only | 7 |

### W-13

Cuff pulse rate against ECG rate beyond the tolerance, the ECG signal quality low: explained away, it counts as system evidence.

| item | value |
|---|---|
| source | heart-rate incoherence with low signal quality |
| `provenance.violated_template` | `range` |
| `provenance.template_kind` | phi_cp (`TemplateKind.CARE_PLAN`) |
| expected κ | C2 |
| decisive fields, precedence order | `signal_quality.ecg_sqi`, `cross_device.pulse_vs_ecg_hr_diff` |
| reason (UNDETERMINED only) | not applicable |
| table row | 4 |
| checked by hand | yes |

| field | value | reading |
|---|---|---|
| `system.node_lifecycle` | `{"cuff": "active"}` | denied |
| `system.diagnostics_ok` | `True` | denied |
| `system.liveliness_ok` | `True` | denied |
| `system.qos_deadline_missed` | `False` | denied |
| `system.ble_link_quality` | `1.0` | denied (complete) |
| `signal_quality.ecg_sqi` | below `ecg_sqi_floor` | asserted |
| `signal_quality.ppg_sqi` | at or above `ppg_sqi_floor` | denied |
| `signal_quality.cuff_error_code` | `"" (empty string)` | denied |
| `cross_device.pulse_vs_ecg_hr_diff` | above `hr_coherence_tolerance` | asserted |
| `crypto_temporal.authenticated` | `True` | denied |
| `crypto_temporal.seq_gap_or_replay` | `False` | denied |
| `crypto_temporal.timestamp_implausible` | `False` | denied |

Every other field is `None`.

| variant | change from the base case | expected κ | decisive fields | reason | row |
|---|---|---|---|---|---|
| W-13-C3 | both quality fields denied (good quality) (`cross_device.pulse_vs_ecg_hr_diff` above `hr_coherence_tolerance`; `signal_quality.ecg_sqi` at or above `ecg_sqi_floor`; `signal_quality.ppg_sqi` at or above `ppg_sqi_floor`) | C3 | `signal_quality.ecg_sqi`, `signal_quality.ppg_sqi`, `cross_device.pulse_vs_ecg_hr_diff` | not applicable | 3 |
| W-13-U | the pulse-oximeter quality unavailable (`cross_device.pulse_vs_ecg_hr_diff` above `hr_coherence_tolerance`; `signal_quality.ecg_sqi` at or above `ecg_sqi_floor`; `signal_quality.ppg_sqi` None) | UNDETERMINED | none (`evidence_used` empty) | insufficient | 8 |

### W-14

Every channel is clean or unavailable: the violation of the system predicate is not evidence of itself (circular, analisi §4.5).

| item | value |
|---|---|
| source | phi_SYS violation with no corroboration |
| `provenance.violated_template` | `sys` |
| `provenance.template_kind` | phi_sys (`TemplateKind.SYSTEM`) |
| expected κ | UNDETERMINED |
| decisive fields, precedence order | none (`evidence_used` empty) |
| reason (UNDETERMINED only) | provenance-only |
| table row | 7 |
| checked by hand | no (scratch implementation) |

| field | value | reading |
|---|---|---|
| `system.node_lifecycle` | `{"cuff": "active"}` | denied |
| `system.diagnostics_ok` | `True` | denied |
| `system.liveliness_ok` | `True` | denied |
| `system.qos_deadline_missed` | `False` | denied |
| `system.ble_link_quality` | `1.0` | denied (complete) |
| `signal_quality.ecg_sqi` | at or above `ecg_sqi_floor` | denied |
| `signal_quality.ppg_sqi` | at or above `ppg_sqi_floor` | denied |
| `signal_quality.cuff_error_code` | `"" (empty string)` | denied |
| `cross_device.pulse_vs_ecg_hr_diff` | within `hr_coherence_tolerance` | denied |
| `crypto_temporal.authenticated` | `True` | denied |
| `crypto_temporal.seq_gap_or_replay` | `False` | denied |
| `crypto_temporal.timestamp_implausible` | `False` | denied |

Every other field is `None`.

| variant | change from the base case | expected κ | decisive fields | reason | row |
|---|---|---|---|---|---|
| W-14-code | the device error code present (`signal_quality.cuff_error_code` "E1" (device label)) | C2 | `signal_quality.cuff_error_code` | not applicable | 4 |

### W-15

Missing sequence values with the link degraded and the node reported as link down: not integrity evidence (decision D-3).

| item | value |
|---|---|
| source | sequence gap explained by a link fault |
| `provenance.violated_template` | `range` |
| `provenance.template_kind` | phi_cp (`TemplateKind.CARE_PLAN`) |
| expected κ | C2 |
| decisive fields, precedence order | `system.node_lifecycle`, `system.ble_link_quality` |
| reason (UNDETERMINED only) | not applicable |
| table row | 4 |
| checked by hand | yes |

| field | value | reading |
|---|---|---|
| `system.node_lifecycle` | `{"cuff": "link_down"}` | asserted |
| `system.diagnostics_ok` | `True` | denied |
| `system.liveliness_ok` | `True` | denied |
| `system.qos_deadline_missed` | `False` | denied |
| `system.ble_link_quality` | below `ble_link_quality_floor` | asserted |
| `signal_quality.ecg_sqi` | at or above `ecg_sqi_floor` | denied |
| `signal_quality.ppg_sqi` | at or above `ppg_sqi_floor` | denied |
| `signal_quality.cuff_error_code` | `"" (empty string)` | denied |
| `cross_device.pulse_vs_ecg_hr_diff` | within `hr_coherence_tolerance` | denied |
| `crypto_temporal.authenticated` | `True` | denied |
| `crypto_temporal.seq_gap_or_replay` | `True` | asserted |
| `crypto_temporal.timestamp_implausible` | `False` | denied |

Every other field is `None`.

| variant | change from the base case | expected κ | decisive fields | reason | row |
|---|---|---|---|---|---|
| W-15-alone | the gap with no other link evidence (loss not below the floor) (`crypto_temporal.seq_gap_or_replay` `True`; `system.ble_link_quality` below 1.0, at or above `ble_link_quality_floor`; `system.node_lifecycle` `{"cuff": "active"}`) | UNDETERMINED | `system.ble_link_quality`, `crypto_temporal.seq_gap_or_replay` | conflict | 6 |
| W-15-repeat | a repeated sequence value without gap (`crypto_temporal.seq_gap_or_replay` `True`; `system.ble_link_quality` `1.0`; `system.node_lifecycle` `{"cuff": "active"}`) | C3 | `system.ble_link_quality`, `crypto_temporal.seq_gap_or_replay` | not applicable | 2 |


**Hand derivations** (seven of the cases marked "checked by hand: yes"). W-01: no field is asserted, so rows 1 to 4 fail; every field of the exclusion set of `range` is denied (all four cuff-path system fields, the ratio complete, the error code empty, the cross-device difference within the tolerance, sequence and time denied) and authentication is not asserted: row 5, C1. W-03: no integrity predicate; SE-1 (the node entry `inactive`, uncommanded) and SE-8 (the error code) hold: row 4, C2, decisive fields in the order SE-1, SE-8. W-05: no integrity predicate; SE-6 (navigation outcome asserted) holds: row 4, C2, decisive `system.nav_task_failed`; under A4 SE-6 cannot hold and the exclusion set needs both outcomes, which are `None`: row 8. W-09: no integrity or system predicate; `provenance.template_kind` is INTEGRITY; no RS and no AM predicate holds (ratio complete, node entries `active`, time denied); the witness pair is not read: row 7. W-10: authentication is `None` and tolerated, every other required channel is denied: row 5, C1. W-13: IE-3 fails (the ECG quality is asserted, not denied); SE-9 holds: row 4, C2, decisive `signal_quality.ecg_sqi` then `cross_device.pulse_vs_ecg_hr_diff`. W-15: IE-2 fails (the ratio is below the floor, not complete); SE-1 and SE-5 hold: row 4, C2, decisive `system.node_lifecycle`, `system.ble_link_quality`; W-15-repeat has the complete ratio: IE-2 holds, row 2, C3.


## Traceability

Sources used: analisi §4.5 (the six evidence groups, the hierarchical rule, the abstention class, the diagnosability matrix of ten rows, the threat-model sentence), §4.6 (row 15:00: a deliberate transition is not a crash; the unhandled cascade), §4.8 (claim reformulations, specification-level traceability, cause-based taxonomy), §4.9 item 3 (cascades and root cause), item 4 (safety actions are hazards, clinician in the loop, autonomy limited to stop, retry and call), item 5 (DISPENSE against INTAKE), §5.6 (A4); `docs/source/review.md` R2 weakness 7 and R3 weakness 4; the contracts `#attribution`, `#alert`, `#evidencevector`, `#template`; EC, FM, TM, F07 (sections 1.2, 1.3, 1.4, 1.7, 1.8, 3.4, 3.5 and 9), T02 (sections 3.1, 4.4, 4.7) and T05 (section 3.5). Review items: **R2 weakness 7** (integrity violations treated as low confidence, no adversary model) is closed on the attribution side by the sections Inputs and outputs and Invariants: ρ is not an input of κ, C3 is claimed only from integrity evidence defined per field, and a low ρ is not integrity evidence; **R3 weakness 4** (taxonomy and safety actions: a missed measurement is often caused by the robot, blocking the dispenser is a hazard) by the sections Cascades and root-cause propagation (a missed measurement seeds its downstream violations and the robot outcomes separate a late robot from a patient) and Action policy (the three robot actions, clinical actions never automatic). Decisions: ADR-002 (C3 is integrity violation), ADR-003 (fallback to the nurse), ADR-004 (DISPENSE is not INTAKE), ADR-010 (hierarchical rule with abstention), ADR-017 (integer milliseconds), ADR-020 (values unverified until reviewed), ADR-037 (no paper text: the excerpt section of the task is not part of this document), ADR-043 (the freeze does not wait for the clinician review).

### Decisions

| id | decision | rests on |
|---|---|---|
| AD-1 | The rule is the four-step hierarchy of the contract, split into eight rows (three integrity rows, one system row, one C1 row, three abstention rows) | `#attribution`; ADR-010; analisi §4.5 |
| AD-2 | Two fields get finer reading classes than the three states of EC: `system.node_lifecycle` (class K) and `system.ble_link_quality` (classes G and F) | EC D-3, D-4; EC section Reading rules ("deliberate is not failed") |
| AD-3 | The witness fields are not integrity evidence; for `int` they are context (resolution (a), and (c)) | EC EX-9, D-12, EX-12, EC-OP-6; TM Non-claims 6; analisi §4.5 row 9 |
| AD-4 | Integrity evidence from the sequence field only for a repeat without gap; a gap is link evidence or abstention; an unavailable ratio is ambiguous | EC D-3; EX-1; EX-10 |
| AD-5 | Cross-device incoherence: C3 with both quality fields denied, C2 with a quality field asserted, abstention if the quality is unavailable; the quality fields are not in the exclusion set | task check 3; FM section Non-faults and boundaries |
| AD-6 | `crypto_temporal.timestamp_implausible` is never decisive alone; asserted it blocks C1 and abstains | EC-GAP-6; TM section Time as an attack vector |
| AD-7 | A deliberate (commanded) transition is neither C2 nor allows C1: abstention, reason conflict | analisi §4.6 row 15:00; EC section Reading rules |
| AD-8 | C1 by exclusion needs every channel of the exclusion set available and denied; the only exception is `crypto_temporal.authenticated`, tolerated as `None` (the unauthenticated deployment) | EC (Reading states, EX-3 (f), D-9); TM H-DEP, TM-OP-11; analisi §4.5 rows 1 and 10 |
| AD-9 | `hold` is in the robot scope and its exclusion set contains the robot task outcomes; `sched` contains both outcomes | EC scope table; H-VISIT; FM effect rows on `hold` |
| AD-10 | `count` has no C1 branch in contract 0.1.0 | EC-GAP-1; F07 section 3.5 example 3 |
| AD-11 | `system.battery_low` and `witness.robot_present` are context, never read | FM `battery_depleted` row; EC D-2, D-6; AD-3 |
| AD-12 | Refusal against robot-missed: the C2 side is separated, the refusal abstains, with or without ADR-040 | ADR-040 (proposed); EC D-5, D-9 |
| AD-13 | Predicted violations: κ UNDETERMINED without evaluating the rule; replaced, not duplicated | F07 section 1.7 (CP13); ADR-041 (proposed) |
| AD-14 | Cascades: roots are `sched` alerts with a definite κ, effects are `resp` and `hold` alerts whose decisive sub-formula is a failed guard and whose own result is not a different definite class | analisi §4.9 item 3; F07 section 1.8; FM CAS-1 |
| AD-15 | The abstention reason has a priority: conflict, then provenance-only (kinds SYSTEM and INTEGRITY), then insufficient | task check 6 |
| AD-16 | The action policy is a proposal: three robot actions, clinical actions never automatic | analisi §4.9 item 4; ADR-003 |
| AD-17 | `evidence_used`: rows in precedence order, predicates in table order, fields in contract order | task check 2; F07 section 1.3 |

### Hypotheses

Each is verified where stated or is open and says why.

| id | hypothesis | where verified, or why open |
|---|---|---|
| H-1 | The rule compares floats and strings with four registry thresholds (`hr_coherence_tolerance`, `ecg_sqi_floor`, `ppg_sqi_floor`, `ble_link_quality_floor`) and with the empty string, as EC prescribes; the extractor does not compare | EC section Representation of denied for non-boolean fields. Open: the registry has no value for the four names (requested, unset); constructing the rule without them is an error, no default |
| H-2 | `ble_link_quality_floor` is at most 1.0, so that a degraded link (class A) implies a missing sequence value | EC D-3 ("a floor above 1.0 is meaningless"). Open: a load check is requested from WS05-T07 |
| H-3 | An empty `system.node_lifecycle` mapping is read as `None` | EC: `None` when no node of the scope has an entry. Verified by reading |
| H-4 | The witness pair of a violated INT instance restates the violation (EX-9, 6000 seeded draws, one availability mask for both robot channels) | Holds for the reference form of INT (decided at the dispense step, backward window; ADR-026 proposed) and the single mask of H-MASK; open if ADR-026 changes the form or the two channels are masked separately |
| H-5 | A failed verification has no benign cause | TM H-AUTHCAUSE; open (TM-OP-15: a payload corruption, a key mismatch or a firmware error would raise it) |
| H-6 | A repeated sequence value with a complete delivery ratio is a replay symptom, and benign repeats (restart, counter reset, re-send, a bounce that repeats the number) are rare | TM H-SEQMONO, H-SEQSTATE; open until ADR-034 splits the field (OP-AR-6) |
| H-7 | A cross-device difference with a quality field asserted is a device-quality problem and counts as system evidence; `signal_quality.ppg_sqi` is included although it reads `SPO2` (EC D-13) because check 3 names both quality fields; a healthy cuff pulse is within the tolerance | TM H-TOL. Open (OP-AR-5): a real clinical deviation during an ECG noise episode is read as C2 |
| H-8 | The scalar `system` fields aggregate over the scope table of EC, and the measurements of `sched`, `hold` and `resp` are carried out through the robot visit | EC D-10 (ADR-033 proposed), FM hypothesis 7. A deployment where the cuff measures on its own schedule edits the scope table and the relevance map |
| H-9 | A low battery report without a lapse or a failed task does not explain a violated template, and the stop that depletion causes is visible in `system.liveliness_ok` and the task outcomes | FM `battery_depleted` row; the simulation has no battery model (EC D-2). Open for a deployment where the robot reports its battery and stops without a lapse |
| H-10 | The attributor can resolve the windows of a record from its decision time and the registry names `sched_window`, `hold_lookback`, `delta1`, `delta2` (per-patient values from the plan where present) | Open (OP-AR-3): `RuleAttributor(registry, templates, rule=None)` of WS05-T07 step 5 has no plan input; the contract Protocol is not affected |
| H-11 | The upper end of `sigma_interval` is minus infinity exactly for a failed guard | T02 section 2.1 (guard failure gives an infinite value); interim, until the path carrier of OP-T07-6 exists (OP-AR-4) |
| H-12 | The rule cannot tell why a field is `None` (capability missing, channel unavailable by placement, no basis in the window) and treats all as unavailable | EC section Reading states, declared limit |
| H-13 | The ten rows of analisi §4.5 are the acceptance cases; "partial" means abstention with a candidate set | Task step 1; TM section Attack-to-evidence table |
| H-14 | Instance keys such as `sched@09:00` are illustrative | F07 AH-13 |

### Open points

- **OP-AR-1 Profile coverage of C1.** In the reference profile S6 of EC (diagnostics, deadline and independent clocks undeclared) C1 is unreachable for every template (section C1 exclusion conditions). Owners: WS04-T06, WS04-T07, WS04-T11 and WS07-T03 (declare and emit the capabilities; EC-OP-19 asks for a transport-delay model), or the human (a profile-aware rule, an amendment of ADR-036). Until then the abstention rate on clinical events measured on such a profile is a property of the profile.
- **OP-AR-2 Scope of the sequence and time evidence to the robot's presence stream** (the third option of EC D-12), and the consequence for the A4 hypothesis on forged dispenses. Not adopted (AD-3); the human may reverse EC D-12.
- **OP-AR-3 Window values at the attributor** (H-10).
- **OP-AR-4 Carrier of the guard marker** (F07 OP-T07-6, WS05-T04 step 8).
- **OP-AR-5 Cross-device difference with a quality problem** (H-7): the choice of reading it as system evidence, and the inclusion of the pulse-oximeter quality, are for engineering review; the alternative is neutral (abstention).
- **OP-AR-6 Benign repeats read as C3** until ADR-034 (H-6), and the case of a replay together with a loss, which D-3 declares not told from a loss.
- **OP-AR-7 The time Boolean.** `crypto_temporal.timestamp_implausible` has no clock-health companion (EC-GAP-6, ADR not proposed); the table never lets it decide alone.
- **OP-AR-8 The action policy**, and which clinical action is offered for which κ: "WS02 proposal for clinician review (WS00-T07)", with the lab safety review (WS10-T01). ADR-043 (accepted) decouples the freeze from the clinician review, which stays a pre-submission item; the policy is an open point, not a gate, and the parameter work of WS01-T09 does not set any action.
- **OP-AR-9 The exclusion conditions of C1** (which channels must be available and denied for each template): also for the clinician review and carried as an open point under ADR-043. The four thresholds are registry names whose values WS01-T09 may propose; none is given here.
- **OP-AR-10 `count` rows with ADR-032.** If `dispenser/interval_since_previous_ms` and `dispenser/content_change` are adopted, the table gains rows for the double take (C1) and the bounce (C2) of analisi §4.5 rows 6 and 7; the sign convention of `content_change` is the one of ADR-040 (2). They are not part of the enumeration.
- **OP-AR-11 Refusal reaching C1.** Under AD-8 and AD-12 a refusal never reaches C1 because the cuff is silent; a relaxation would let the robot's `declined` report stand for the cuff-path fields. Not adopted; it would weaken invariant I4.
- **OP-AR-12 Roots of cascades.** C1 roots fold and UNDETERMINED roots do not (AD-14); whether C1 roots should fold, and the cost of not folding under an UNDETERMINED root, are for review.
- **OP-AR-13 The exception of I4 for `crypto_temporal.authenticated`** and the strict alternative (C1 unreachable without authentication); a verification channel that is down is read as clean (AD-8).
- **OP-AR-14 Candidate sets** of the abstentions are declared by the matrix of WS02-T05, not computed.
- **OP-AR-15 The decision record** (row, reason, decisive fields) is exposed by a method outside the Protocol; WS05-T07 names it.
- **OP-AR-16 Mixed deployments.** An aggregated `crypto_temporal.authenticated` can be denied for the capable devices only (EC declared limit, partial coverage); the rule cannot check the coverage without the profile.
- **OP-AR-17 Node status across the day boundary** (EC-OP-21) changes the readings of `system.node_lifecycle` at the start of a day.
- **OP-AR-18 A PENDING INT instance after its deadline with an `undecidable` marker** (TM-OP-15, F07 OP-T07-14) has no alert path in contract 0.1.0; the rule does not attribute it. How the nurse learns that the dispense could not be checked (a review item, or the subscription to the verdict stream) is not decided here.

### Deviations from the task text

1. **Check 8 and step 5 (provisional κ for predicted violations):** not adopted; replaced by CP13 and ADR-041 (section Predicted violations).
2. **Step 4, starting expectations, corrected against the matrix, the scope table and invariant I4:** (i) `hold` is not "without the robot": it is in the robot scope and needs the two task outcomes (AD-9); only `range` is without the robot; (ii) `sched` also needs the manipulation outcome, because a failed manipulation makes the measurement absent (FM `manipulation_failure` row); (iii) the signal-quality fields are not required for C1 (only the cross-device pair is, AD-5); (iv) the `crypto_temporal.*` fields are all required except `crypto_temporal.authenticated`, which may be `None` (AD-8); (v) "robot liveliness denied" is the aggregate `system.liveliness_ok` (EC-OP-17), and A4 recomputes it.
3. **Invariant I4** is restated with one exception (AD-8): the unrestricted form contradicts the matrix row 10 in the unauthenticated deployment.
4. **Worked case W-11** uses the templates of the library (`sched` root; `resp` and `hold` effects): the end-of-day measurement-count template of analisi §4.6 row 15:00 is not a `TemplateId` (CP2), so WS05-T07 test 14 cannot use it.
5. **Check 3, signal quality "unavailable"** is followed as written; `signal_quality.ppg_sqi` is included as the task names both quality fields (H-7).
6. **Quotations from analisi and review.md** are translations from the Italian source.

### Mismatches with other documents and tasks (none edited here)

- **T02 (WS01-T02) states no evaluability condition for φ_INT** (a witness channel or authentication must be available): the table of section 3.1 and section 4.7 do not say it; it is in T01 section 2.4 and T05 section 3.5 (V-INT-1, V-INT-3). For the plan lead and WS01-T08.
- **WS08-T04 test 6** (a forged-DISPENSE fixture with robot present, no identity, no intake observed and no authentication evidence expects C3, and `ours-A4` something else) does not hold under AD-3: the fixture gives UNDETERMINED for both (W-09, W-09-A4); a fixture with `crypto_temporal.authenticated` asserted gives C3 for both (W-09-A). The A4 effect appears on the robot task outcomes (W-05, W-05-A4) and on the backing of `resp` (W-02, W-02-A4); with the `EMBODIED_MASK_WITNESS` variant only the backing of `resp` is lost (W-02), and W-02-auth is unchanged. In an authenticated deployment the robot task outcomes still remove C1 from `resp` under A4 (W-02-auth under A4 is UNDETERMINED).
- **WS05-T07 tests 5, 18, 20, 25** assume a provisional κ for predicted alerts or a purity test over the verdict state; they follow F07 (CP13), with test 5 scoped to the rule. **Test 14** names a day-end measurement-count effect (deviation 4). **Tests 8 and 9** (I4, I5) take the restated I4. **Tests 11 and 31** need the delivery ratio: a sequence field asserted with a complete ratio gives C3 and with a ratio below 1.0 never gives C3 by itself (W-08-U, W-15, W-15-alone, W-15-repeat).
- **F07 section 3.5 example 1** says C1 "because no system or integrity evidence was found in the channels that were available"; under AD-8 C1 needs the channels of the exclusion set to be available. F07 section 1.9 column A lists `xi.evidence_used` as "none asserted" for a C1 alert; here it lists the denied fields of the exclusion set. For the renderer (WS05-T07, WS11-T02).
- **WS02-T05** (the matrix): DX-06 and DX-07 expect "yes" and get UNDETERMINED (insufficient) with the current contract (W-06, W-07; EC-GAP-1); DX-08 in an unauthenticated deployment with a device that provides `seq` gets C3 where the matrix says partial (W-08-U), and partial (UNDETERMINED) without `seq` (W-08-U-noseq); DX-09 is partial in an unauthenticated deployment (W-09, W-09-resp) and C3 for a synthesised forgery in an authenticated one (W-09-A); DX-10 is C1 in the unauthenticated deployment (W-10) and C3 for a BLE injection in an authenticated one (W-10-A); DX-05 under A4 is UNDETERMINED (W-05-A4); DX-02 is C1 with a witness without authentication (W-02) and with authentication without a witness (W-02-auth), and UNDETERMINED under A4 in both because of the task outcomes. DX-03 is C2 on `sys` (W-03) and on `sched` (W-03-sched).
- **WS04-T09 and ADR-040:** AD-12.
- **FM OP-12 and CAS-5** are listed as hazards by WS02-T05; under AD-3 they give UNDETERMINED (provenance-only), not C3.

### Dependencies on proposed ADRs

| ADR (status) | what in this document depends on it |
|---|---|
| ADR-032 (proposed) | the `count` rows for the double take and the bounce (OP-AR-10); until accepted `count` has no C1 |
| ADR-033 (proposed) | the evidence key (EC D-1) and the scope table behind the relevance map (EC D-10) |
| ADR-034 (proposed) | the sequence pair of AD-4; accepting it removes the ratio qualifier and the explained-away rule of the gap |
| ADR-035 (proposed) | the payload conventions from which the readings are derived |
| ADR-036 (proposed) | the device profile behind the profile coverage (OP-AR-1) |
| ADR-040 (proposed) | the `declined` outcome (AD-12) |
| ADR-041 (proposed) | the κ of predicted alerts (AD-13) and the alert fields |
| ADR-026 (proposed) | the form of INT behind H-4 |
| ADR-043 (accepted) | the action policy and the exclusion conditions are open points, not a gate of the freeze |

### Consumers

WS05-T07 (the rule, the builder, the cascade, the renderer, the fixtures W-01 to W-15), WS02-T05 (the matrix rows and the hazard register, which reuses the action policy), WS08-T04 (the A4 transitions), WS09-T02 and WS11-T02 (the explanation text).
