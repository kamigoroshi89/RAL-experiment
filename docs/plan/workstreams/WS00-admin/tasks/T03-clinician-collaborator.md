---
id: WS00-T03
title: "Recruit a clinician and, if possible, an RV/STL collaborator"
workstream: WS00-admin
owner: human
status: ready
depends_on: ["WS00-T02"]
critical_path: false
non_negotiable: false
estimate_pd: 1
sources: ["analisi §9 (0.3)", "analisi §2 R3 weakness 3", "analisi §5.7"]
interfaces: []
review_items: ["R3-W3"]
---
## Obiettivo

Recruit one clinician (an internist, a cardiologist or a nursing coordinator, analisi §9 item 0.3) who will review parameters, taxonomy and vignettes, and, if possible, one collaborator with runtime-verification (RV) or STL experience. Concrete output: `docs/plan/workstreams/WS00-admin/outputs/WS00-T03.md`, which records who agreed, for what, when they are available and on what authorship terms. The clinician is the person who can anchor the clinical parameters in a drug and a guideline, which is what R3-W3 asks; the review itself is WS00-T07, so this task provides the reviewer without closing the finding. Without this person the M1 gate cannot pass.

## Contesto

- `docs/source/analisi.md` §9 row 0.3 (who to involve and why: R3 and R1) and §5.7 (vignette study with 8 to 15 nurses or physicians of a partner hospital).
- `docs/source/review.md`: R3 weaknesses 3 and 4 and the author questions 2 and 4 (which drug and guideline anchor the parameters; who validated the taxonomy clinically).
- `docs/plan/workstreams/WS00-admin/outputs/WS00-T02.md` (the scope the clinician is asked to review) and `outputs/WS00-T01.md` (field `Author and title changes`).
- `docs/plan/00-master-plan.md` section 3 (M1 needs the clinician review) and section 7 (WS11 is the first item to cut).
- `docs/plan/03-decisions.md` ADR-020 (clinical parameters stay unverified until a clinician reviews them).

Blocked until WS00-T02 is done: the scope decisions (ADR-001 to ADR-003) are what the clinician is told and asked to review, so `outputs/WS00-T02.md` must exist first.

## File toccati

- `docs/plan/workstreams/WS00-admin/outputs/WS00-T03.md` (create)

## Test

Verification checks:

1. The artefact starts with `completed_by:` and `completed_on:` lines and contains the seven H2 fields of Done when, each non-empty.
2. `## Clinician` names the person, the role (internist, cardiologist, nursing coordinator or another role with a reason), the institution and the clinical area that covers hypertension care. It is not `none` (see Passi step 6).
3. `## Agreed involvement` lists, with a yes or no for each: review of the parameter registry, the taxonomy and the priorities (WS00-T07, M1 gate); design input for the vignette study (WS11-T01); validation of the answer key (WS11-T03). It records the time commitment in the clinician's own words and the dates the clinician is available for WS00-T07.
4. `## Authorship and acknowledgement` states co-author or acknowledged, and shows that the choice is allowed by the rule recorded in `outputs/WS00-T01.md` under `Author and title changes`, including the last allowed date.
5. `## RV or STL collaborator` names a person and their agreed involvement, or states that none was found, lists who was contacted, and states the fallback (the internal devil's-advocate review of WS12-T07 stays the only formal-methods check).
6. `## Candidate log` has one row per person contacted with role, institution, date and outcome (agreed, declined, no answer).
7. `## Partner hospital access` states whether the clinician can give access to 8 to 15 nurses or physicians for the vignette study (analisi §5.7), at which institution, and whether that institution must authorise the involvement.
8. No e-mail address or telephone number appears in the file (`grep -cE '@|\+[0-9]{6}' <file>` prints `0`).

## Passi

1. Read `outputs/WS00-T02.md` and prepare a one-page note for candidates: the pathology (hypertension), what will be asked (parameters and their anchoring, taxonomy, vignettes), and the tasks involved (WS00-T07, and WS11-T01 and WS11-T03 if the vignette study goes ahead). Ask the candidate for their own estimate of the hours; do not propose a figure that the plan does not contain.
2. Contact candidates among internists, cardiologists and nursing coordinators. Record every contact in `## Candidate log` on the day it happens.
3. In parallel, contact people with RV or STL experience; record them in the same log with their role type.
4. When a clinician agrees, fill `## Clinician`, `## Agreed involvement` and `## Partner hospital access`. Ask the clinician which drug class and which guideline they would use to anchor the parameters, but do not record an answer here: that is the content of WS00-T07.
5. Check the author-change rule in `outputs/WS00-T01.md` before promising authorship; fill `## Authorship and acknowledgement`. If the rule forbids adding an author after the commitment letter, decide with the co-authors whether the clinician is added before the letter or acknowledged.
6. If no clinician has agreed when the candidate list is exhausted, leave this task `in_progress`, write the blocker in `## Open points`, and report it to the decision-makers of WS00-T02: WS00-T07 and WS11 stay blocked and the M1 gate cannot pass. Do not mark the task done with a placeholder person.
7. Fill `## RV or STL collaborator` and `## Open points`, then set `status: done` in this task file and tell the owners of WS00-T07, WS00-T06 and WS11-T01.

## Done when

From the repository root:

- `test -f docs/plan/workstreams/WS00-admin/outputs/WS00-T03.md` exits 0.
- `grep -cE '^## (Candidate log|Clinician|Agreed involvement|Authorship and acknowledgement|RV or STL collaborator|Partner hospital access|Open points)$' docs/plan/workstreams/WS00-admin/outputs/WS00-T03.md` prints `7`.
- `grep -c '^completed_by: .\+' docs/plan/workstreams/WS00-admin/outputs/WS00-T03.md` prints `1`.
- Inspection: check 2 holds (a named clinician), and check 8 prints `0`.
