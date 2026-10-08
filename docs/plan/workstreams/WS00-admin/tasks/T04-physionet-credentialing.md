---
id: WS00-T04
title: "Start PhysioNet credentialing for MIMIC-IV and eICU"
workstream: WS00-admin
owner: human
status: ready
depends_on: []
critical_path: true
non_negotiable: false
estimate_pd: 1
sources: ["analisi §9 (0.6)", "analisi §5.1"]
interfaces: ["02-interfaces.md#priorsource"]
review_items: []
---
## Obiettivo

Start PhysioNet credentialing on day one so that access to MIMIC-IV (with its emergency-department module, MIMIC-IV-ED) and to the eICU Collaborative Research Database exists as early as possible. Credentialing needs a CITI course and a data use agreement (DUA) and can take from a few days to a few weeks (analisi §5.1); the 1 person-day estimate covers the active work only, and the wait is external. Concrete output: `docs/plan/workstreams/WS00-admin/outputs/WS00-T04.md`, created at submission and updated until access is granted or refused, plus a record of the terms of the open-access datasets that ADR-005 allows the plan to use immediately. The task is on the critical path: WS04-T13 (`MimicPriorSource` and the eICU variant) and WS08-T06 (unlabeled real-data run) wait for it, while WS04 proceeds with `LiteraturePriorSource` meanwhile (ADR-005).

## Contesto

- `docs/source/analisi.md` §5.1 (public sources, access constraints, "avviatelo subito", licences and access times to verify) and §9 row 0.6.
- `docs/plan/03-decisions.md` ADR-005 (`PriorSource`, results before access are labelled "literature priors").
- `docs/plan/02-interfaces.md#priorsource` (what `MimicPriorSource` must deliver: parameters with a mandatory `source_ref`, never raw data in the repository).
- `docs/plan/01-conventions.md` section 1 (`data/raw/` is never committed and is gitignored).
- The PhysioNet pages of MIMIC-IV, MIMIC-IV-ED and eICU-CRD, and of the open-access datasets, which the human consults for the current requirements.

No dependency: this task is `ready` and starts on day one.

## File toccati

- `docs/plan/workstreams/WS00-admin/outputs/WS00-T04.md` (create)

## Test

Verification checks:

1. The artefact starts with `completed_by:` and `completed_on:` lines and contains the six H2 fields of Done when, each non-empty. `completed_on` is updated at each edit.
2. `## Account and course` names the credentialed person (a name, no credentials), the exact name of the CITI course as PhysioNet requires it at the time of registration, and the completion date. The completion report is kept outside the repository and only its existence is noted.
3. `## MIMIC-IV application` and `## eICU-CRD application` each contain the lines `submitted_on:`, `dua_signed_on:`, `access_status:` (one of `submitted`, `granted`, `refused`), `expected_decision:` and, once granted, `access_verified_on:` (the date on which a table of the dataset was actually opened). The MIMIC-IV section also lists the modules requested (hospital, ICU, emergency department) and records that the schema of MIMIC-IV-ED was checked, as analisi §5.1 asks.
4. `## Data handling constraints` records where the data is stored (a path under `data/raw/` or an institutional server), who may access it, and what the DUA says about sending data to third-party or hosted services. The consequence for the plan is stated: agents receive only derived parameters and their provenance unless the DUA explicitly allows more.
5. `## Open-access datasets` has one row each for VitalDB, the MIT-BIH Noise Stress Test Database, BIDMC PPG and Respiration, and PhysioNet/CinC Challenge 2015, with the licence or terms as stated on the dataset page, the access condition, and whether derived traces or parameters may be redistributed in the open-source release (WS13). Nothing is filled from memory; each row has a `Source:` line.
6. `## Timeline and fallback` states the expected decision date, the date of each follow-up, and the consequence of a refusal: which WS08 results stay labelled "literature priors" and which tasks (WS04-T13, WS08-T06) are dropped or reduced.
7. The file contains no credential, no certificate identifier and no personal contact detail.

## Passi

1. Day one: create or check the PhysioNet account of the person who will hold access, and read the credentialing requirements on the PhysioNet pages of MIMIC-IV and eICU-CRD. Write the requirements as found in `## Account and course`.
2. Complete the CITI course PhysioNet requires and note the completion date. Complete the PhysioNet credentialing application, including any reference or supervisor it asks for.
3. Sign the DUA of MIMIC-IV, then of eICU-CRD, and request access to each. Record `submitted_on`, `dua_signed_on`, `access_status: submitted` and the expected decision date in the two application sections. Create `outputs/WS00-T04.md` at this point; this is the active work of the 1 person-day.
4. While waiting, fill `## Data handling constraints` from the DUA text and `## Open-access datasets` from the dataset pages, so that WS04-T06 can use them for noise and artefact modelling without waiting for credentialing.
5. Follow up on the expected decision date. On approval, open one table of each dataset, set `access_status: granted` and `access_verified_on`, and add the storage path to `## Data handling constraints`. On refusal, set `access_status: refused` and write the consequence in `## Timeline and fallback`.
6. When both datasets are `granted` or `refused`, set `status: done` in this task file and tell the owners of WS04-T13 and WS08-T06. Until then the task stays `in_progress`, so that WS04-T13 stays blocked (it depends on this task and cannot run before access exists).

## Done when

From the repository root:

- `test -f docs/plan/workstreams/WS00-admin/outputs/WS00-T04.md` exits 0 (reached at submission, within the active work of the task).
- `grep -cE '^## (Account and course|MIMIC-IV application|eICU-CRD application|Data handling constraints|Open-access datasets|Timeline and fallback)$' docs/plan/workstreams/WS00-admin/outputs/WS00-T04.md` prints `6`.
- `grep -E '^access_status: (granted|refused)$' docs/plan/workstreams/WS00-admin/outputs/WS00-T04.md` prints two lines, one per dataset. This final condition is what sets the task to `done`; a `refused` line requires its consequence in `## Timeline and fallback`.
- `grep -c '^access_verified_on: [0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}' docs/plan/workstreams/WS00-admin/outputs/WS00-T04.md` prints a number equal to the count of datasets with `access_status: granted`.

## Notes

### Status update (user attestation)

Marked `done` on 2026-09-30 at the user's explicit instruction ("le task umane iniziali sono tutte eseguite"). The artefact named in "Done when" (`docs/plan/workstreams/WS00-admin/outputs/WS00-T04.md`) was not present in the repository at that time; the agent did not create or reconstruct it. Anything downstream that needs its content will stop and report. No `access_status` line exists in the repository, so the credentialed datasets (MIMIC-IV, eICU-CRD) are not usable by agent tasks until the artefact is recorded.

### Status correction (agent, 2026-10-08)

Asked on 2026-10-08, gab clarified that the attestation of 2026-09-30 referred to the open-access datasets (WS00-T09), not to PhysioNet credentialing: no CITI course, no application and no DUA exist for MIMIC-IV, MIMIC-IV-ED or eICU-CRD, and no credentialed data is on the machine. Status set back from `done` to `ready`; the decision whether to start credentialing is postponed by gab. No artefact is created: by step 3 it is created at submission. The licences of the four open-access datasets are recorded in `outputs/WS00-T09.md` (PhysioNet pages read on 2026-10-08). Consequence: WS04-T13 goes back to `blocked`; until this task closes, results stay labelled "literature priors" (ADR-005) and the defence of analisi §10 objection 1 that relies on MIMIC is not available.
