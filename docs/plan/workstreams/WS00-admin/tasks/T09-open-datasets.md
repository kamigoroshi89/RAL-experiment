---
id: WS00-T09
title: "Download the open datasets into data/raw/ and record their licences (VitalDB, MIT-BIH noise stress test, BIDMC, CinC 2015)"
workstream: WS00-admin
owner: human
status: done
depends_on: []
critical_path: true
non_negotiable: false
estimate_pd: 0.5
sources: ["analisi §5.1", "analisi §9 (4)"]
interfaces: ["02-interfaces.md#priorsource"]
review_items: []
---
## Obiettivo

Put the open-access datasets that the measurement process needs on disk before WS04-T06, so that real noise and artefact segments (electrode and motion noise on ECG, photoplethysmography, intraoperative signals) can be used without waiting for MIMIC credentialing (ADR-005). Agents have no network access, so a human downloads them. Concrete output: the datasets under `data/raw/<dataset>/` (gitignored, never committed), and `docs/plan/workstreams/WS00-admin/outputs/WS00-T09.md` with version, licence and checksum manifest per dataset.

## Contesto

- `docs/source/analisi.md` §5.1 (open-access data: VitalDB, BIDMC PPG and Respiration, MIT-BIH Arrhythmia and Noise Stress Test databases, PhysioNet/CinC Challenge 2015).
- `docs/plan/workstreams/WS00-admin/tasks/T04-physionet-credentialing.md` (its `## Open-access datasets` section records licences and redistribution terms; this task performs the download).
- `docs/plan/workstreams/WS04-benchmark/tasks/T06-measurement-process.md` (which records and fields it reads).
- `docs/plan/01-conventions.md` section 1 (`data/raw/` gitignored).

## File toccati

- `docs/plan/workstreams/WS00-admin/outputs/WS00-T09.md` (create)
- `data/raw/vitaldb/`, `data/raw/nstdb/`, `data/raw/bidmc/`, `data/raw/cinc2015/` (create, not committed)

## Test

Verification checks:

1. The artefact has one H2 section per dataset with the fields `version:`, `source_page:`, `licence:` (as stated on the dataset page), `downloaded_on:`, `size_bytes:`, `manifest:` (path of a SHA-256 checksum list inside the dataset directory) and `redistribution:` (allowed or not, in the open-source release).
2. Each `manifest:` file exists and `sha256sum -c` on it succeeds from inside the dataset directory.
3. The MIT-BIH Noise Stress Test Database section lists which noise record types are present (electrode motion, baseline wander, muscle artefact), because WS04-T07 samples from them; nothing is filled from memory, each row has a `Source:` line.
4. `git status --short data/raw` prints nothing.
5. The artefact repeats no personal data and no credential.

## Passi

1. Read the current terms on each dataset page; if any requires a login or agreement, complete it and note the account holder (a name only).
2. Download each dataset into `data/raw/<dataset>/`; create a `SHA256SUMS` file in each directory.
3. Fill `outputs/WS00-T09.md` with the fields of check 1 for the four datasets.
4. Tell the owners of WS04-T06 and WS13-T04 (datasheet) that the artefact exists; set `status: done`.

## Done when

- `test -f docs/plan/workstreams/WS00-admin/outputs/WS00-T09.md` exits 0 and `grep -c '^## ' docs/plan/workstreams/WS00-admin/outputs/WS00-T09.md` prints at least `4`.
- `for d in vitaldb nstdb bidmc cinc2015; do (cd data/raw/$d && sha256sum -c SHA256SUMS >/dev/null) || echo FAIL $d; done` prints nothing.
- `git status --short data/raw` prints nothing.

## Notes

### Status update (user attestation)

Marked `done` on 2026-09-30 at the user's explicit instruction ("le task umane iniziali sono tutte eseguite"). The artefact named in "Done when" (`docs/plan/workstreams/WS00-admin/outputs/WS00-T09.md`) was not present in the repository at that time; the agent did not create or reconstruct it. Anything downstream that needs its content will stop and report. `data/raw/` does not exist in the repository, so any task that reads the open datasets (VitalDB, NSTDB, BIDMC, CinC 2015) cannot run until they are downloaded.
