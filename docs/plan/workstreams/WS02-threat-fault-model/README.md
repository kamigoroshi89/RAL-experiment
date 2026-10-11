# WS02-threat-fault-model: Threat model, fault model, attribution

## Objective

Turn the classes C2 (system or embodiment failure) and C3 (integrity or plausibility violation, ADR-002) and the attributed cause κ into defined, testable objects. The workstream delivers five documents under `docs/models/` and one machine-readable file, `configs/diagnosability.yaml`:

- a fault model for C2 (device, link, robot);
- a threat model for C3 with declared attacker capabilities, two attacker-knowledge levels and explicit exclusions;
- the semantics of the six evidence groups of the `EvidenceVector`, including which fields exist under which placement (ward node, robot co-located, robot away, robot down);
- the attribution rule specification: hierarchy, UNDETERMINED as a valid output, cascade root-cause propagation, and the clinician-in-the-loop principle with autonomy limited to robot actions;
- the diagnosability matrix, in which the rows that are "not distinguishable" are kept as declared results, plus a paragraph on hazards and standards (ISO 13482, ISO 14971, IEC 62304).

Analisi §5.8 marks the threat model, the fault model and the diagnosability matrix as indispensable, and analisi §10 asks that undetectable C3 cases appear in the matrix as a result and not as a margin note. Estimate: 8.5 person-days (analisi §9 item 2: 1-2 pw).

## Inputs

- `docs/plan/01-conventions.md` (glossary, units, style) and `docs/plan/02-interfaces.md` (contracts `#evidencevector`, `#attribution`; read-only: `#alert`, `#trace-schema`, `#signals`, `#time-and-units`, `#ros-2-interfaces`, `#template`).
- `docs/plan/03-decisions.md`: ADR-002 (C3 as integrity violations), ADR-003 (ward node plus robot, fallback to the nurse), ADR-004 (DISPENSE is distinct from INTAKE), ADR-010 (hierarchical rule with abstention), ADR-017 (integer milliseconds).
- `docs/source/analisi.md` §3.5, §3.6, §4.5, §4.6, §4.8, §4.9, §5.1, §5.2, §5.6 (A4), §5.8, §10, and `docs/source/review.md` (R1 weakness 7, R2 weakness 7, R3 weaknesses 4 and 5, meta-review).
- Output of WS01-T01 (signals, sampling semantics, time) and of WS01-T07 (alert tuple definition), read when the dependent task starts.

## Outputs

| Output | Task | Main consumers |
|---|---|---|
| `docs/models/fault-model.md` | WS02-T01 | WS02-T03, WS04-T07, WS07-T05 |
| `docs/models/threat-model.md` | WS02-T02 | WS02-T03, WS04-T08, WS12 |
| `docs/models/evidence-channels.md` (and ADR proposals for contract gaps in `03-decisions.md`) | WS02-T03 | WS02-T04, WS04, WS05-T07, WS07, WS08-T04 |
| `docs/models/attribution-rule.md` | WS02-T04 | WS02-T05, WS05-T07, WS05-T09, WS09-T02 |
| `configs/diagnosability.yaml` | WS02-T05 | WS05-T07 (tests), WS08-T04, WS12-T04 |
| `docs/models/diagnosability-hazards.md` | WS02-T05 | WS10-T01, WS12-T04, WS12-T06 |

The EvidenceVector and Attribution contracts stay at version 0.1.0 unless an ADR accepted by a human changes them (`01-conventions.md` section 6). WS02 owns both contracts, so gaps found here are proposed as ADRs, never edited into `02-interfaces.md` by this workstream.

## Dependencies

- Upstream workstreams: WS01-T01 (signals, sampling, time) for T01 and T02; WS01-T07 (alert tuple and traceability wording) for T04. Nothing else.
- Downstream workstreams: WS04-T07 (needs T01), WS04-T08 (needs T02), WS05-T07 (needs T04 and T05), WS08-T04 (needs T05), WS09-T02 (needs T04), WS12-T04 (needs T05).
- Contract anchors: owns `02-interfaces.md#evidencevector` and `02-interfaces.md#attribution`; reads `#alert`, `#trace-schema`, `#signals`, `#time-and-units`, `#ros-2-interfaces`, `#template`.
- Human input: none required to start. The clinician review of the taxonomy, the action policy and the hazard register is part of WS00-T07 and of the M1 gate (R3 weakness 4 asks who validated the taxonomy clinically); the documents mark every clinical judgement as "for clinician review".

## Acceptance criteria

Run from the repository root; every command must print nothing (or the stated result) and exit 0 where noted.

1. All six outputs exist: `for f in fault-model threat-model evidence-channels attribution-rule diagnosability-hazards; do test -f docs/models/$f.md || echo "missing $f"; done; test -f configs/diagnosability.yaml`.
2. Every evidence path written in the five documents is a real `EvidenceVector` field (contract `#evidencevector`, 20 fields, written `group.field`): `grep -ohE '\b(provenance|system|signal_quality|cross_device|witness|crypto_temporal)\.[a-z_]+' docs/models/*.md configs/diagnosability.yaml | sort -u | grep -vxE 'provenance\.(violated_template|template_kind)|system\.(node_lifecycle|diagnostics_ok|liveliness_ok|qos_deadline_missed|ble_link_quality|battery_low|nav_task_failed|manip_task_failed)|signal_quality\.(ecg_sqi|ppg_sqi|cuff_error_code)|cross_device\.pulse_vs_ecg_hr_diff|witness\.(robot_present|identity_confirmed|intake_observed)|crypto_temporal\.(authenticated|seq_gap_or_replay|timestamp_implausible)'` prints nothing.
3. The diagnosability file passes the schema check of WS02-T05 (rows, allowed values, the two declared limits DX-04 and DX-10).
4. Every subtype listed in the `## Subtype vocabulary` sections of `fault-model.md` and `threat-model.md` appears as a `subtype:` in `configs/diagnosability.yaml` (loop in WS02-T05, Done when).
5. The ablation A4 mask (which fields become `None` when the embodied channel is removed) is stated field by field in `evidence-channels.md`, and every matrix row has an A4 outcome.
6. The hazard paragraph names ISO 13482, ISO 14971 and IEC 62304 and covers collisions, infection control, camera privacy, presence versus identity, safety actions as hazards, and the fallback when the robot is unavailable: `grep -o 'ISO 13482\|ISO 14971\|IEC 62304' docs/models/diagnosability-hazards.md | sort -u | wc -l` prints 3.
7. Glossary and claims sweep: `grep -nEi 'subsyste[m]|orthogona[l]|intrinsic explainab[i]|distribution-fre[e]|edge clou[d]' docs/models/*.md` prints nothing.
8. Forbidden tokens: `grep -nE 'T[O]DO|T[B]D|[?]{3}|lore[m]' docs/models/*.md configs/diagnosability.yaml` prints nothing.
9. No numeric clinical value is invented: `grep -nE '[0-9]+ ?(mmHg|ms|min|bpm)' docs/models/*.md | grep -v 'illustrative, unverified'` prints nothing.
10. All five task files have `status: done`: `grep -L 'status: done' docs/plan/workstreams/WS02-threat-fault-model/tasks/*.md` prints nothing.

## Source sections

- analisi §3.5 (assistive robots in the ward, standards), §3.6 (security and tampering of wearable medical devices, risk ALTO).
- analisi §4.5 (κ, six evidence groups, hierarchical rule, diagnosability matrix, threat model), §4.6 (time coherence, cascades, deliberate lifecycle transition versus crash), §4.8 (claim reformulations), §4.9 items 1 to 5 (distributed architecture, time, cascades, safety actions as hazards, DISPENSE versus INTAKE).
- analisi §5.1 (C2 and C3 injections, confounders, ground truth), §5.2 (fault injection in simulation), §5.6 (A4), §5.8, §9 item 2, §10 (objections 3 and 4).
- analisi §2 (`review.md`): R1 weakness 7, R2 weakness 7, R3 weaknesses 4 and 5, meta-review (fault and attack model, embodiment evidence).

## Tasks

| id | title | owner | status | depends_on |
|---|---|---|---|---|
| WS02-T01 | Fault model for C2 (device, link, robot) | agent | blocked | WS01-T01 |
| WS02-T02 | Threat model: attacker capabilities, attack classes, exclusions | agent | blocked | WS01-T01 |
| WS02-T03 | Evidence channels and EvidenceVector semantics, availability per placement | agent | blocked | WS02-T01, WS02-T02 |
| WS02-T04 | Attribution rule spec: hierarchy, abstention, cascades, clinician-in-the-loop | agent | blocked | WS02-T03, WS01-T07 |
| WS02-T05 | Diagnosability matrix (machine-readable) and hazard and standards paragraph | agent | blocked | WS02-T04 |
| WS02-T06 | Attribution as a likelihood table: specification, cells with their source, sensitivity design (ADR-074) | agent | ready | WS02-T04, WS02-T05 |
