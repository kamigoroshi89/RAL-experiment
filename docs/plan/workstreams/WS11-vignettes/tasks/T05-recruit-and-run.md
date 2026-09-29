---
id: WS11-T05
title: Recruitment and study run (8-15 participants)
workstream: WS11-vignettes
owner: human
status: blocked
depends_on: [WS11-T04]
critical_path: false
non_negotiable: false
estimate_pd: 3
sources: ["analisi §5.7"]
interfaces: []
review_items: []
---
## Obiettivo

OPTIONAL: first item in the cut order (`docs/plan/00-master-plan.md` section 7). Recruit 8 to 15 nurses or physicians of the partner hospital (analisi §5.7), run the online study with the app built in WS11-T04, and collect one response file per participant. Concrete output: `docs/plan/workstreams/WS11-vignettes/outputs/WS11-T05.md` recording ethics status, consent handling, dry run, recruitment, participant counts, data files and deviations from the protocol, and the response files in `data/raw/vignette-responses/`, which are gitignored and never committed. Analisi §9 item 11 adds the ethics lead time to the 3 person-weeks of the workstream: the application, if one is needed, is lodged as soon as WS11-T01 has produced `study/ethics-dossier.md`, in parallel with WS11-T02 to WS11-T04, and no invitation goes out before the outcome is recorded here.

## Contesto

- `docs/plan/workstreams/WS00-admin/outputs/` : `WS00-T06.md` (sections `Vignette study`, `Data protection for study data`, `Decision and schedule`: what the ethics body requires, the lead time, the latest submission date) and `WS00-T03.md` (the clinician who gives access to the participants).
- `study/` : `ethics-dossier.md` (information text, consent text, data handling), `protocol.yaml` (sample, counterbalancing, response schema), `app/` (the built app), `responses.py` (validator, run as `python3 study/responses.py <directory>`).
- `docs/plan/workstreams/WS11-vignettes/outputs/WS11-T03.md` (pilot findings, confirmed timing, decision `go`).
- `docs/source/analisi.md` §5.7 (8 to 15 nurses or physicians, online, within-subject; "verificate se serve approvazione etica o se basta un'esenzione").
- `docs/plan/01-conventions.md` section 1 (`data/raw/` is never committed).

Unblocked when WS11-T04 is `done`. Recruitment starts only when `## Ethics status and reference` of the artefact is filled and dated.

## File toccati

- `docs/plan/workstreams/WS11-vignettes/outputs/WS11-T05.md` (create)
- `data/raw/vignette-responses/` (create; one JSON file per participant, named with the participant code; gitignored)
- `study/ethics-dossier.md` (modify only if the ethics body requires changes to the information or consent text; then rebuild `study/app/` with `python3 study/build_app.py`)

## Test

Verification checks (an agent or reviewer can run each):

1. The artefact starts with `completed_by:`, `completed_on:`, `completed_count:` and `app_bundle_sha256:` lines and contains the nine H2 fields of Done when, each non-empty. It contains no participant name, no e-mail address, no hospital or committee name, and no participant code linked to a person.
2. `## Ethics status and reference` gives the outcome (approval, exemption or not required) with its source and date, consistent with `outputs/WS00-T06.md`. The date is earlier than the first invitation and earlier than the first participant response file. If the ethics body required changes to the information or consent text, it says so and states that the app was rebuilt.
3. `app_bundle_sha256` equals the SHA-256 of the `study/app/bundle.json` that was deployed, and equals the value in the WS11-T04 completion note (or the rebuild is explained under `## Deviation log`).
4. `## Consent and data handling` states how consent was collected (the consent page of the app), where consent records and the participant-code-to-person mapping are stored (outside the repository, with the location named by role, not by path of a personal drive), who can access them, and when they are deleted.
5. `## Dry run` lists the browsers and device types tried, the date, and the result of each manual browser check of WS11-T04 (tab-hidden time recorded, no answer change, reload resumes, keyboard use, exported file named with the code).
6. `## Participants` reports aggregates only: invited, started, completed (`completed_count`), dropped out, withdrew (and that their data were deleted), counts by profession and by experience band.
7. `## Data files` gives the directory, the number of files (equal to `completed_count`), a checksum list (SHA-256 per file name, code only) and the output of `python3 study/responses.py data/raw/vignette-responses`, with no invalid file.
8. `completed_count` is between 8 and 15. If it is lower, `## Shortfall note` says so and states that WS11-T06 must label the study a descriptive pilot; if it is higher than 15, the extra responses are reported as they are, with the reason.
9. `## Deviation log` lists every deviation from `study/protocol.yaml` with date and reason (changed sequence assignment, replaced participant, extended deadline, changed invitation channel); "none" is a valid entry.
10. `git status --porcelain data/raw` prints nothing and `git check-ignore data/raw/vignette-responses` prints the path (the responses are ignored by git).

## Passi

1. Read `outputs/WS00-T06.md`. If an application is required, lodge it with `study/ethics-dossier.md` and the documents the ethics body lists (this should already have happened while WS11-T02 to T04 were running). If an exemption or "not required" is the outcome, keep the written statement. Fill `## Ethics status and reference`. Do not go on until it is dated.
2. If the ethics body changed the information or consent text, edit the matching section of `study/ethics-dossier.md` and rebuild the app (`python3 study/build_app.py`); record the new `app_bundle_sha256`.
3. Deploy `study/app/` as static files on a host approved by the institution or the partner hospital (no third-party analytics; the app sends nothing, participants return the exported file through the channel agreed with the ethics body). Fill `## Consent and data handling`.
4. Dry run: open the deployed app in the browsers and devices that participants are likely to use, walk one sequence with a test code, and check each manual browser check of WS11-T04. Fill `## Dry run`. Fix and rebuild if a check fails.
5. With the clinician collaborator, invite the nurses and physicians who agreed to be approached (voluntary, no pressure from hierarchy, invitation text approved with the dossier). Give each a participant code from the schedule; keep the code-to-person mapping outside the repository. Aim for a number of participants that keeps the counterbalancing balanced (see `sample` in `study/protocol.yaml`). Record dates and counts in `## Participants`.
6. As files come back, save each as `data/raw/vignette-responses/<participant code>.json`, run `python3 study/responses.py data/raw/vignette-responses`, and remove or ask to repeat any file that does not validate only if the protocol allows a replacement (log it). Never edit a response file by hand.
7. Close the run: disable the link, count files, compute checksums, fill `## Data files`, `## Deviation log`, `## Shortfall note` (write `not applicable` if the count is 8 or more) and `## Close-out`. Set `status: done` in this task file and tell the owner of WS11-T06.

## Done when

From the repository root:

- `test -f docs/plan/workstreams/WS11-vignettes/outputs/WS11-T05.md` exits 0.
- `grep -cE '^## (Ethics status and reference|Consent and data handling|Dry run|Recruitment|Participants|Data files|Deviation log|Shortfall note|Close-out)$' docs/plan/workstreams/WS11-vignettes/outputs/WS11-T05.md` prints `9`.
- `grep -cE '^(completed_by|completed_on|completed_count|app_bundle_sha256): .+' docs/plan/workstreams/WS11-vignettes/outputs/WS11-T05.md` prints `4`.
- `n=$(ls data/raw/vignette-responses/*.json | wc -l); c=$(grep -m1 '^completed_count: ' docs/plan/workstreams/WS11-vignettes/outputs/WS11-T05.md | cut -d' ' -f2); test "$n" = "$c"` exits 0.
- `python3 study/responses.py data/raw/vignette-responses` exits 0.
- `n=$(ls data/raw/vignette-responses/*.json | wc -l); test "$n" -ge 8 || grep -q 'descriptive pilot' docs/plan/workstreams/WS11-vignettes/outputs/WS11-T05.md` exits 0.
