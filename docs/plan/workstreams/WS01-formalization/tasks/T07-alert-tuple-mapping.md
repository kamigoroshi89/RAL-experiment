---
id: WS01-T07
title: Alert tuple definition, traceability wording and FHIR/BPMN mapping sketch
workstream: WS01-formalization
owner: agent
status: ready
depends_on: ["WS01-T04", "WS01-T06"]
critical_path: false
non_negotiable: true
estimate_pd: 2
sources: ["analisi §4.8", "analisi §3.4", "analisi §4.1 (decomposition)", "analisi §4.9 (3, 7)", "analisi §2 R1 (weaknesses 8, 9)"]
interfaces: ["02-interfaces.md#alert"]
review_items: ["R1-W8", "R1-W9"]
---
## Obiettivo

Write `docs/formal/07-alert-tuple-mapping.md`: the definition of the alert tuple `<tau, kappa, sigma_tilde, rho, xi>` field by field, the wording of the decomposition phi = phi_CP and phi_SYS and phi_INT, the ten claim reformulations of analisi §4.8 as a table for the paper and for the claim audit of WS12-T07, the governance of the distributed care plan (versioning and signature scope), and a partial mapping sketch from FHIR PlanDefinition and from BPMN to the templates. This task is non-negotiable (analisi §9), although it is not on the critical path. It closes R1 weakness 8 (clinical and system specification conflated) and R1 weakness 9 (integrity of the distributed specification).

## Contesto

Unblocks when WS01-T04 and WS01-T06 are `done`. Read first:

1. `docs/formal/04-normalisation-ranking.md`, `docs/formal/06-rho-proposition1.md` and `docs/formal/02-templates.md` (sigma-tilde, rho, decomposition and template ids).
2. `docs/plan/02-interfaces.md#alert` (fields, semantics), plus the rules of `#attribution` and `#monitor` that concern who produces the alert.
3. `docs/source/analisi.md` §4.8 (table of claims), §3.4 (FHIR PlanDefinition, BPMN, "mapping is strong and cheap"), §4.1 (decomposition), §4.9 items 3 and 7, §2 R1 weaknesses 8 and 9.
4. `docs/plan/03-decisions.md` ADR-002, ADR-004, ADR-010.
5. `docs/plan/workstreams/WS01-formalization/README.md` (shared conventions, CP5, CP13).

## File toccati

- `docs/formal/07-alert-tuple-mapping.md` (create)

## Test

Document task: verification checks.

1. **Headings.** `## 1 Alert tuple`, `## 2 Decomposition wording`, `## 3 Traceability wording`, `## 4 Care plan governance`, `## 5 FHIR PlanDefinition mapping sketch`, `## 6 BPMN mapping sketch`, `## 7 Coverage and limits of the mapping`, `## 8 Paper excerpt (Section III and mapping sentence)`, `## 9 Open points for WS01-T08`.
2. **Tuple table.** Section 1 has one row for each of tau, kappa, sigma-tilde, rho, xi with: contract field (`tau`, `kappa`, `sigma_norm`, `rho`, `xi`), type, unit or range, semantics in one sentence, producer (monitor or attribution), defining document (T02, WS02, T04, T06), and the meaning of `None` where a field can be absent. It also explains the remaining fields of the contract (`t_ms`, `label`, `score`, `verdict`, `priority`, `root_cause_of`, `caused_by`) and how they are filled.
3. **Tau.** Section 1 states: one alert per violated template instance; two templates violated by one event give two alerts, never a compound tau (workshop Table I row 21:02, error e); the sub-formula path in xi names the decisive sub-formula (the one attaining the minimum) and lists the others; the workshop's "sigma" without tilde is raw robustness.
4. **Sigma-tilde and rho.** Section 1 states for a VIOLATED alert that `sigma_norm` is the upper end of the normalised interval at emission (certified severity, T04) and for a PREDICTED_VIOLATION alert that it is the normalised forecast sigma-hat, which can be non-negative under the variant "possible" (CP5, contract comment says `[-1, 0)`); it states that sigma-tilde and rho are complementary, not orthogonal (analisi §4.8: near the threshold rho falls), and that rho carries its `kind` and exact guarantee (T06).
5. **Kappa and predicted alerts (CP13).** Section 1 states that kappa is produced by the attribution layer and never by the sub-formula alone, that `UNDETERMINED` is a valid output, that a device fault or an integrity violation is not a violation of the care plan, and it decides kappa for PREDICTED_VIOLATION alerts (recommended: `UNDETERMINED`, because attribution is defined on evidence available at prediction time and the contract text says the attribution step "turns violated records into alerts"); the tension with `Alert.verdict` is listed as CP13.
6. **Cascades.** Section 1 states the fields `root_cause_of` and `caused_by` (analisi §4.9 item 3): a downstream violation caused by an upstream failure carries `caused_by` and is not a top-level alert; the example is a missed measurement (C2) that makes the response obligation of the dose unmet.
7. **Decomposition wording (R1 weakness 8).** Section 2 gives the wording of phi = phi_CP and phi_SYS and phi_INT, replaces the workshop sentence "A single monitor handles all three classes" by "a single monitor evaluates the conjunction phi = phi_CP and phi_SYS and phi_INT and an attribution layer assigns each alert a cause", uses "phi_CP" only for care-plan constraints, and states the glossary rules: alert for the output, violation for a violated sub-formula, attributed cause for kappa.
8. **Claim table.** Section 3 contains a table whose ten data rows each begin with the quoted current claim (each row starts with the characters `| "`) and give the problem and the allowed wording, covering all ten rows of analisi §4.8: "intrinsic explainability", "a faulty sensor cannot masquerade as a clinical event", "two orthogonal axes", "natural taxonomy induced by the constraint structure", "Embodiment as a safety asset ... redundancy a passive network cannot", "every alert goes through a single auditable verification path", "distribution-free coverage", "beyond static edge-based solutions", "to assist nursing staff in real-world hospital wards", "ensures". The three reformulations "specification-level traceability", "complementary" and "cause-based taxonomy" appear verbatim with the sentence of analisi §4.8 for traceability (each alert references the violated template instance, its clinical parameters and the evidence used for attribution).
9. **Rendering requirements.** Section 3 states requirements for the natural-language text of `Explanation.text` for nursing staff (template in plain words, instance time, parameter values with units, evidence used, verdict state, attributed cause) and gives three example sentences with F0 numbers labelled illustrative: a clinical deviation (range), a system failure (schedule), an undetermined cause (count). It states that a user check of comprehensibility is deferred to the vignette study (WS11), so no claim of interpretability is made here.
10. **Governance (R1 weakness 9).** Section 4 defines pathway template (institutional, population level) and patient care plan (`CarePlan`), states that the clinician authors and the robot evaluates but cannot author or modify (analisi §4.9 item 7), lists the version fields (`pathway_template_id`, `registry_version`, `plan_version`), defines the signature scope (canonical serialisation of every `CarePlan` field except `signature`), the load-time behaviour (`Monitor.load` verifies; on failure the monitor refuses the plan and escalates to the nurse), and defers the algorithm and key management to WS05-T03 (recorded there as an ADR) without naming a library.
11. **FHIR sketch.** Section 5 maps at least: goal targets to the bands of RANGE and the threshold of HOLD; action timing to schedule ticks; related-action offsets to the RESP window and to HOLD precedence; conditions to guards; care plan instantiation of a plan definition to the pathway-template link of `CarePlan`; versioning and provenance to `plan_version` and `signature`. Every FHIR element name is marked `[verify: standard text]` because no network access is used and no name is written from memory as fact. Only standards named in analisi §3.4 appear (FHIR PlanDefinition and CarePlan, Clinical Quality Language, Arden Syntax, openEHR GDL).
12. **BPMN sketch.** Section 6 maps timer and boundary-timer events to SCHED and RESP windows, an exclusive gateway before the dispense task to HOLD, multi-instance or loop counters to COUNT, and message or participant events to the witness of INT; it names BPMN4CP as cited in analisi §3.4 and marks the reference `[ref-needed: WS03]`.
13. **Coverage and limits.** Section 7 states, per template, whether the source representation supports the mapping fully, partly or not at all, and what a standard representation does not carry (signal-level quantitative constraints, scales, priorities, derived signals). It words the claim as "a partial mapping from a standard representation to the templates" (analisi §3.4) and does not claim automatic translation.
14. **Paper excerpt.** Section 8 gives the LaTeX for the alert-tuple definition of Section III (about 0.15 page) and one sentence for the mapping.
15. **Open points.** Section 9 lists CP5 and CP13 with the resolution adopted and any other tension found (exact anchors).

## Passi

1. Write section 1 from `#alert`: build the tuple table, fill `None` semantics, decide tau, sigma-tilde, kappa for predicted alerts and cascades; cross-check each decision against T04 (ranking, frozen sigma-tilde) and T06 (Rho fields).
2. Write section 2 (wording) and section 3: copy the ten rows of analisi §4.8 in the format of check 8; write the rendering requirements and the three example sentences; recompute every number in them from F0.
3. Write section 4 (governance) and sections 5 to 7 (FHIR, BPMN, coverage). Keep every unverified element name marked.
4. Write section 8 (paper excerpt) and section 9 (open points).
5. Run "Done when"; set `status` to `done`; commit `WS01-T07: add alert tuple, claim wording and mapping sketch`.

## Done when

```bash
cd "/home/gab/Desktop/RAL experiment"
f=docs/formal/07-alert-tuple-mapping.md
test -f "$f"
for h in "## 1 Alert tuple" "## 2 Decomposition wording" "## 3 Traceability wording" "## 4 Care plan governance" \
         "## 5 FHIR PlanDefinition mapping sketch" "## 6 BPMN mapping sketch" \
         "## 7 Coverage and limits of the mapping" "## 8 Paper excerpt (Section III and mapping sentence)" \
         "## 9 Open points for WS01-T08"; do grep -qF "$h" "$f" || echo "missing heading: $h"; done   # prints nothing
[ "$(grep -c '^| "' "$f")" = "10" ]
for w in "specification-level traceability" "cause-based taxonomy" complementary PlanDefinition BPMN "verify: standard text" \
         CP5 CP13 UNDETERMINED caused_by; do grep -q "$w" "$f" || echo "missing: $w"; done     # prints nothing
! grep -nE 'T[O]DO|T[B]D|[?][?][?]|lore[m]' "$f"                                            # exit 0
```

## Notes

### Flag from the WS01-T04 review (orchestrator, 2026-09-30)

Line 40 states that for a VIOLATED alert `sigma_norm` is the upper end of the normalised interval at emission "(certified severity, T04)". `docs/formal/04-normalisation-ranking.md` (section 4.7, OP-9 and OP-14) does not state that rule; it offers "-1 with a guard marker, or a graded value". For a VIOLATED SCHED alert the upper-end rule gives -0.0333 (WS01-T08 R3), not -1. Reconcile in this task together with `predicted_sigma_norm` (OP-15) and record the outcome.

### Flag from the WS01-T06 review (orchestrator, 2026-10-01)

Line 40 says that for a predicted alert `sigma_norm` is "the normalised forecast sigma-hat, which can be non-negative under the variant possible". `docs/formal/06-rho-proposition1.md` (sections 2.4 and 10 item 5) adopts the conformal bound `clip(sigma_hat + q, -1, 1)`, always negative for an emitted alert, and hands the `Alert.sigma_norm` field for predicted alerts and the display of a low rho on a "possible" alert to this task. Decide here together with OP-14 and OP-15 (see the two earlier flags).
