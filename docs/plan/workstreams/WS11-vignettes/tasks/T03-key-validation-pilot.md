---
id: WS11-T03
title: Clinician answer-key validation and pilot
workstream: WS11-vignettes
owner: human
status: blocked
depends_on: [WS11-T02]
critical_path: false
non_negotiable: false
estimate_pd: 1.5
sources: ["analisi §5.7"]
interfaces: []
review_items: []
---
## Obiettivo

OPTIONAL: first item in the cut order (`docs/plan/00-master-plan.md` section 7). The clinician collaborator of WS00-T03, with the study lead, turns the draft key of WS11-T02 into the expert-defined key that analisi §5.7 requires ("una chiave definita da un esperto"), verifies the trust scale items against the original publication, and runs a small pilot with clinicians who will not be in the main sample. Concrete output: `docs/plan/workstreams/WS11-vignettes/outputs/WS11-T03.md`, the validated key `study/answer-key.yaml`, and the trust scale filled in `study/protocol.yaml`. The result decides whether WS11-T04 builds the app and with which changes.

## Contesto

- `study/` : `vignettes/pilot-pack.md` and `vignettes/manifest.json` (all families in all three renderings, no key), `answer-key-draft.yaml` (proposal to validate, every entry `status: draft`), `design.md` and `protocol.yaml` (what is measured, action vocabulary and scoring classes, provisional exclusion rule and session-length budget, empty `trust_scale`).
- `docs/plan/workstreams/WS00-admin/outputs/` : `WS00-T06.md` (section `Vignette study`: whether the pilot needs the same approval or exemption as the main study) and `WS00-T03.md` (the clinician and the partner hospital).
- `docs/source/analisi.md` §5.7 (measures; the trust scale reference carries a dagger, so it is unverified until this task) and §4.9 item 4 (safety actions are themselves hazards; clinician in the loop).
- `docs/plan/03-decisions.md` ADR-018 (unverified references are flagged) and ADR-020 (clinical content is unverified until a clinician reviews it).

Unblocked when WS11-T02 is `done`. The pilot may not start before the ethics status for pilot participants is recorded in the artefact.

## File toccati

- `docs/plan/workstreams/WS11-vignettes/outputs/WS11-T03.md` (create)
- `study/answer-key.yaml` (create; copy of `study/answer-key-draft.yaml` edited by the clinician)
- `study/protocol.yaml` (modify: `trust_scale`, and `exclusions` if the pilot changes it)

## Test

Verification checks (an agent or reviewer can run each):

1. The artefact starts with `completed_by:` and `completed_on:` lines and contains the nine H2 fields of Done when, each non-empty. Personal names, e-mail addresses and telephone numbers do not appear; the reviewer is identified as in the registry review (role label or initials).
2. `## Ethics status for the pilot` quotes the outcome for the vignette study from `outputs/WS00-T06.md` (approval, exemption or not required), states whether pilot participation is covered, and gives a date earlier than the first pilot session.
3. `## Families reviewed` has exactly one row per scored family id in `study/vignettes/manifest.json`, each with one decision: `confirmed`, `key changed`, `vignette changed` or `rejected`, and a one-line clinical note. A rejected family has a replacement family id or a statement that the family is dropped.
4. `study/answer-key.yaml` has one entry per scored family, every entry `status: validated` and a `reviewed_by` that is not null, and every expected action is in the family's option list. The key was fixed before any main-study participant answered (the date is in the artefact).
5. `## Action catalogue and key` states the number of experts who reviewed the key. If there is one, it says so as a limitation. If a second clinician reviewed independently, it gives the share of families where both chose the same expected action. It confirms that no option is a drug or dose action and that at least one `unsafe` option per family is really unsafe in the clinician's judgement.
6. `## Divergence cells` gives, for each of the four cells, whether the clinician agrees that the pilot alerts of that cell look severe or not severe and confident or not confident, and the expected action in that cell.
7. `## Trust scale verification` records the full citation as checked against the original (authors, title, year, journal, volume, pages), the number of items, the response format, which items are reverse-coded, the scoring rule, and whether the scale may be reproduced in the study. In `study/protocol.yaml`, `trust_scale.items` is non-empty and equals the original in wording and order, `verified_by` is not null, and the scoring rule is written into the `analysis` block.
8. `## Pilot` gives the number and professions of pilot participants (none of them will take part in the main study), the format (moderated walk-through of `pilot-pack.md`), whether the display of σ̃ and ρ was understood, whether the plain-language cause labels were understood, comprehension problems per condition, and the stimulus language finding.
9. `## Timing and exclusion rule` gives measured minutes per vignette and per block from the pilot, the resulting session length for the main study against the budget in `protocol.yaml`, the confirmed or changed hidden-time exclusion rule, and the families to drop if the budget is exceeded.
10. `## Decision for WS11-T04` is one of `go`, `go with changes` (changes listed) or `stop` (reason).

## Passi

1. Read `study/answer-key-draft.yaml`, `study/vignettes/pilot-pack.md` and the ethics outcome. Record in `## Ethics status for the pilot` whether pilot participants are covered; if not, apply through the route of `outputs/WS00-T06.md` or run the walk-through only with the clinician collaborator and record that.
2. Copy `study/answer-key-draft.yaml` to `study/answer-key.yaml`. With the clinician, go through every scored family and decide the expected, acceptable, incorrect and unsafe options independently of how the family is rendered. Edit the key, set `status: validated` and `reviewed_by`, and fill `## Families reviewed` and `## Action catalogue and key`. If a second clinician is available, have them classify a subset of families without seeing the first key.
3. With the clinician, go through the four divergence cells and fill `## Divergence cells`.
4. Obtain the original publication of the trust scale (the reference in analisi §5.7 is unverified). Check the citation, transcribe the items verbatim into `study/protocol.yaml` under `trust_scale.items`, set `verified_by`, and record the response format, reverse-coded items and scoring rule there and in `## Trust scale verification`. Do not take the items from memory or from a secondary source.
5. Run the pilot with clinicians outside the main sample: a moderated walk-through of `pilot-pack.md` with think-aloud, timing each vignette. Fill `## Pilot` and `## Timing and exclusion rule`, and update `exclusions` in `study/protocol.yaml` if the rule changes.
6. List in `## Changes requested to vignettes and instruments` every change that an agent must apply before WS11-T04 (wording, families to drop, cut-offs of the divergence cells), with the file each affects. Apply changes to the vignette files by rerunning `study/build_vignettes.py` (agent step), not by hand-editing the bundle.
7. Fill `## Decision for WS11-T04`, set `status: done` in this task file, and tell the owner of WS11-T04.

## Done when

From the repository root:

- `test -f docs/plan/workstreams/WS11-vignettes/outputs/WS11-T03.md` exits 0.
- `grep -cE '^## (Ethics status for the pilot|Families reviewed|Action catalogue and key|Divergence cells|Trust scale verification|Pilot|Timing and exclusion rule|Changes requested to vignettes and instruments|Decision for WS11-T04)$' docs/plan/workstreams/WS11-vignettes/outputs/WS11-T03.md` prints `9`.
- `grep -c '^completed_by: .\+' docs/plan/workstreams/WS11-vignettes/outputs/WS11-T03.md` prints `1`.
- `test -f study/answer-key.yaml && ! grep -q 'status: draft' study/answer-key.yaml && ! grep -q 'reviewed_by: null' study/answer-key.yaml` exits 0.
- `! grep -q 'verified_by: null' study/protocol.yaml && ! grep -q 'items: \[\]' study/protocol.yaml` exits 0.
- Inspection: the first non-empty line under `## Decision for WS11-T04` starts with `go`, `go with changes` or `stop`.
