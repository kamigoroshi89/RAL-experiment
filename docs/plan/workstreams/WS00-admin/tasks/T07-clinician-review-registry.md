---
id: WS00-T07
title: "Clinician review of parameter registry, taxonomy and priorities (M1 gate)"
workstream: WS00-admin
owner: human
status: blocked
depends_on: ["WS00-T03", "WS01-T03", "WS01-T04", "WS01-T05", "WS02-T04"]
critical_path: true
non_negotiable: false
estimate_pd: 1
sources: ["analisi §4.2", "analisi §2 R3 weakness 3", "analisi §2 R3 weakness 4", "analisi §4.5", "analisi §9 (0.3)"]
interfaces: ["02-interfaces.md#parameter-registry"]
review_items: ["R3-W3", "R3-W4"]
---
## Obiettivo

Have the clinician recruited in WS00-T03 review, entry by entry, the parameter registry designed in WS01-T03, together with the per-template scales and priorities and the taxonomy of classes C1, C2, C3 and UNDETERMINED. This is the clinician review that milestone M1 requires (`00-master-plan.md` section 3) and the step that turns registry values from "illustrative, unverified" into reviewed values (ADR-020). Concrete output: `docs/plan/workstreams/WS00-admin/outputs/WS00-T07.md` (the review log) and `reviewed_by` set in `configs/registry/hypertension.yaml`. It closes the clinical part of R3-W3 (parameters not anchored in a drug or guideline) and R3-W4 (clinically misleading taxonomy); the technical parts are closed in WS01-T03 and WS02-T04. The task is on the critical path.

## Contesto

- `docs/plan/02-interfaces.md#parameter-registry`: the fields `RegistryEntry` (`value`, `unit`, `rationale`, `source_ref`, `reviewed_by`), `PhysioBounds`, and the rule that no clinical numeric constant lives outside the registry.
- `docs/plan/workstreams/WS01-formalization/tasks/T03-parameter-registry.md`: registry design, YAML schema and anchoring procedure; it also names the template table of WS01-T02 that carries the scales `s_π` and the priorities.
- `docs/source/analisi.md` §4.2 (scale per predicate fixed with a clinician, lexicographic priority assigned by the clinician) and §4.5 (diagnosability matrix rows that the clinician judges).
- `docs/source/review.md`: R3 weaknesses 3 and 4 and author questions 2 to 4 (which drug and guideline anchor Δ1, Δ2 and the band; how a double take is classified; who validated the taxonomy).
- `docs/plan/03-decisions.md` ADR-020 (no agent assigns a drug or guideline anchor from memory; values without review are reported as unverified).

Blocked until both dependencies are done: WS00-T03 (a clinician is named and has given available dates in `outputs/WS00-T03.md`) and WS01-T03 (the registry file `configs/registry/hypertension.yaml`, its schema and the template table exist).

## File toccati

- `docs/plan/workstreams/WS00-admin/outputs/WS00-T07.md` (create)
- `configs/registry/hypertension.yaml` (modify: `reviewed_by`, and value, `unit`, `rationale` and `source_ref` of entries the clinician changes)

## Test

Verification checks:

1. The artefact starts with `completed_by:` and `completed_on:` lines and contains the nine H2 fields of Done when, each non-empty.
2. `## Reviewer and registry version` gives the reviewer's name, role and institution, the review date, and the registry version string that was reviewed (the value `ParameterRegistry.version()` returns for the file).
3. `## Entry review` has one row for every entry of `configs/registry/hypertension.yaml`, and the number of rows equals the number of entries in the file. Each row has: entry name, value shown to the clinician, unit, decision (`approved`, `changed`, `rejected` or `not assessable`), and for a `changed` row the new value, `rationale` and `source_ref` supplied by the clinician.
4. `## Physiological bounds review` has one row for every `PhysioBounds` signal of the registry with the same decisions; the bounds are the ones used to complete unknown future values in robustness intervals.
5. `## Scales and priorities review` has one row for every template of the template table of WS01-T02, giving the clinician's decision on its scale `s_π` and on its place in the priority order (analisi §4.2). The priority order is stated as the clinician's, not derived from the example in analisi §4.2.
6. `## Drug and guideline anchoring` names the drug class and the guideline the clinician anchors Δ1, Δ2 and the pressure band to, with the reference; or states explicitly `not anchored` for each entry that has no anchor, so it is reported as unverified (ADR-020).
7. `## Taxonomy review` answers, in the clinician's judgement: how an unscheduled dispenser opening shortly after a regular one is to be classified (double take, sensor bounce, other; R3 question 3); whether a missed measurement is a physiological or a process deviation and which cause usually produces it; which safety actions the robot may take without a clinician (the plan assumes limited autonomy: stop, retry, call) and which need one (analisi §4.9 item 4); and whether the classes C1, C2, C3 and UNDETERMINED are clinically acceptable as named, with the reviewer's name as the answer to R3 question 4.
8. In the registry file, every entry marked `approved` or `changed` has `reviewed_by` set to the reviewer identifier used in the artefact, and every entry with an empty `reviewed_by` appears in `## Unreviewed entries`. No numeric value was changed without a clinician-supplied `source_ref`.
9. `## Change requests to WS01` lists any change to templates, scales, priorities or taxonomy that the clinician asked for and that cannot be a value edit (for example a missing template), each with the WS01 task it reopens, or states `none`.
10. `## M1 sign-off` states which of the three items of the M1 gate the clinician reviewed in this session (template table, normalisation, verdict semantics) and which remain. A remaining item is reported to the plan maintainer, because M1 needs all three.

## Passi

1. Read the WS01-T03 task note and the registry file. Prepare a printout or shared view for the clinician showing every entry with its name, value, unit, rationale and source, and the template table with scales and priorities. Values must be labelled as they are in the file: an entry whose `rationale` is "illustrative, unverified" is shown as such.
2. Hold the review session with the clinician in the availability window recorded in `outputs/WS00-T03.md`. Fill `## Reviewer and registry version` first.
3. Go through the entries one by one and record the decision and, for changes, the clinician's value, rationale and reference in `## Entry review`. Do not suggest values, drugs or guidelines; record what the clinician states and the reference they give.
4. Go through the physiological bounds, then through the template table, filling `## Physiological bounds review` and `## Scales and priorities review`.
5. Ask the clinician for the drug class and guideline anchoring and record the answer, or `not anchored`, in `## Drug and guideline anchoring`.
6. Present the taxonomy and the diagnosability matrix rows of analisi §4.5 and record the answers of check 7 in `## Taxonomy review`.
7. Apply the outcome to `configs/registry/hypertension.yaml`: set `reviewed_by` for approved and changed entries; for changed entries update value, unit, rationale and source reference as supplied. Leave rejected and not assessable entries without `reviewed_by` and list them in `## Unreviewed entries`. Any structural change goes to `## Change requests to WS01` instead of the file.
8. Fill `## M1 sign-off`, set `status: done` in this task file, and tell the owners of WS01-T08, WS04-T02 and WS05-T03 that reviewed values are available and that the M1 gate depends on the sign-off.

## Done when

From the repository root:

- `test -f docs/plan/workstreams/WS00-admin/outputs/WS00-T07.md` exits 0.
- `grep -cE '^## (Reviewer and registry version|Entry review|Physiological bounds review|Scales and priorities review|Drug and guideline anchoring|Taxonomy review|Unreviewed entries|Change requests to WS01|M1 sign-off)$' docs/plan/workstreams/WS00-admin/outputs/WS00-T07.md` prints `9`.
- `grep -c '^completed_by: .\+' docs/plan/workstreams/WS00-admin/outputs/WS00-T07.md` prints `1`.
- Inspection: check 3 (rows equal registry entries), check 8 (`reviewed_by` consistent with the artefact and unreviewed entries listed) and check 10 hold.

## Notes

### Flag from the WS01-T03 review (orchestrator, 2026-09-30)

The review sheet produced by WS01-T03 (`docs/formal/03-parameter-registry.md` section 6) has 34 rows: 17 seeded entries plus 17 `unset` names, whereas test 3 expects "the number of rows equals the number of entries in the file" (17). Test 4 ("one row for every `PhysioBounds` signal") clashes with bounds stored as entries `bound_<signal>_lower` and `bound_<signal>_upper` (counted twice). This task has no notion of `unset`, and its rule "any structural change goes to Change requests to WS01" conflicts with WS01-T03 section 4.2 step 9, which moves an unset name into `entries:` once the clinician gives a value. Kept `blocked`; reconcile the counting rule (entries plus unset, bounds once) after ADR-027 (proposed) is decided.
