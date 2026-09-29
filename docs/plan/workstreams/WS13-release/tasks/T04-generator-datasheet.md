---
id: WS13-T04
title: Benchmark and generator documentation and datasheet
workstream: WS13-release
owner: agent
status: blocked
depends_on: ["WS04-T12", "WS13-T01"]
critical_path: false
non_negotiable: false
estimate_pd: 1
sources: ["analisi §5.1", "analisi §10 (1)"]
interfaces: ["02-interfaces.md#trace-schema"]
review_items: []
---
## Obiettivo

Document the benchmark and its generator so that a reader can regenerate it, understand what it contains and where it must not be used, and inspect the circularity objection instead of trusting it. Concrete output: `docs/benchmark/generator.md` (how the generator works, how to run it, how to extend it, where the non-circularity tests are) and `docs/benchmark/datasheet.md`, a datasheet with thirteen fixed sections covering provenance of parameters, licences of the source data, limitations, intended use and the semi-synthetic nature of the data. Every number in the datasheet is copied from the benchmark manifest or the WS04-T12 validation report, and every licence statement is either taken from a human artefact or marked `unverified`. Nothing is published; pushing to any remote requires explicit human approval.

## Contesto

- `docs/plan/02-interfaces.md#trace-schema` (latent trace versus observed trace, `GroundTruthEvent`, the rules on ground truth definition, splits by patient and files on disk).
- `docs/source/analisi.md` §5.1 (public sources with licences and access times to verify, generator stages, ground truth on the latent trace, scale) and §10 objection 1 (prevention list: latent ground truth, same clinical knowledge for baselines, real unlabeled run, released generator).
- `docs/plan/workstreams/WS04-benchmark/README.md` and the task files of WS04-T10 (non-circularity tests) and WS04-T12 (validation report): the subtype vocabulary of `GroundTruthEvent`, the test file paths and the report path.
- `docs/plan/03-decisions.md`: ADR-001 (one pathology, pre-clinical), ADR-002 (C3 threat model, undetectable rows), ADR-005 (literature priors first, credentialed data later), ADR-018 (unverified flag pattern), ADR-020 (clinical parameters unverified until reviewed).
- Human artefact `docs/plan/workstreams/WS00-admin/outputs/WS00-T04.md`, sections `## Open-access datasets` and `## Data handling constraints`, and the `manifest.json` of a generated benchmark (its keys are those of the WS04-T01 serialiser).

Blocked until WS04-T12 is `done` (validation report and alert-load check exist). The datasheet cites the licence ADR written by WS13-T01; if that ADR does not exist yet, write the sentence `licence: see the licence ADR of WS13-T01 (not yet recorded)` in the section `## Distribution and licence` and list this in the completion note, so that WS13-T03 can flag it.

## File toccati

- `docs/benchmark/datasheet.md` (create)
- `docs/benchmark/generator.md` (create)
- `README.md` (modify: add the two links to `## Documentation`; create nothing if WS13-T01 has not created the file, and say so in the completion note)

## Test

Verification checks (a reviewer can run or inspect each one; the agent runs them all and shows the output in the completion note):

1. `test -f docs/benchmark/datasheet.md && test -f docs/benchmark/generator.md` exits 0.
2. The datasheet has exactly these thirteen H2 headings, in this order: `## Summary`, `## Motivation`, `## Composition`, `## Generation process`, `## Provenance of parameters`, `## Source data and licences`, `## Semi-synthetic nature and non-circularity`, `## Intended use`, `## Out-of-scope use`, `## Limitations`, `## Distribution and licence`, `## Maintenance and versioning`, `## Ethical considerations` (`grep -n '^## ' docs/benchmark/datasheet.md` shows them).
3. No number typed by hand: every count, rate and scale figure that describes the data in the `## Composition` section (identifiers, versions and dates excluded) occurs in the cited source (`manifest.json` or the WS04-T12 validation report, named by path in the section); for each such number, `grep -c '<number>' <cited file>` prints 1 or more. The section also states the generator git revision recorded in the manifest.
4. Provenance table: the rows of `## Provenance of parameters` equal the provenance entries of the manifest (same count, same `name` and `source_ref`, `verified_by` copied); the section states how many rows have `verified_by` empty and that these values are reported as unverified (ADR-020, `02-interfaces.md#priorsource`).
5. Source data table in `## Source data and licences`: one row per source that the manifest declares as used, taken from this candidate list of analisi §5.1 (MIMIC-IV including MIMIC-IV-ED, eICU Collaborative Research Database, VitalDB, BIDMC PPG and Respiration, MIT-BIH Arrhythmia Database, MIT-BIH Noise Stress Test Database, PhysioNet/CinC Challenge 2015, the Pulse Physiology Engine if WS04-T04 adopted it, simglucose only if WS04-T14 was executed) plus one row for the published literature behind `LiteraturePriorSource`; columns: source, what was taken, access condition (open or credentialed), licence or terms as stated by the provider, source of that statement, `licence_verified_by`, `verified_on`. A licence cell is copied from `WS00-T04.md` (`## Open-access datasets`, with its `Source:` line) or from another human-supplied artefact; otherwise it is the word `unverified` and `licence_verified_by` is empty. No licence is filled from memory. The section states how many rows are unverified.
6. Credentialed data rule: the section says whether the release contains any record or value derived from MIMIC-IV or eICU; if it does, it cites the human finding on what the data use agreement allows (`WS00-T04.md`, `## Data handling constraints`); if that finding is absent, the section states that the release contains only `LiteraturePriorSource` parameters (ADR-005).
7. `## Semi-synthetic nature and non-circularity` states: the latent trace is noise-free, fault-free and attack-free and is used only to compute ground truth; a true C1 is a violation of phi_CP on the latent trace; true C2 and C3 are the injected events; the monitor and every baseline see only the observed trace; baselines receive the same clinical knowledge (bands and schedules); the generator and its tests are released so that the circularity can be inspected; and it cites the non-circularity tests of WS04-T10 by file path (`test -f` on each cited path exits 0). It also states the residual risk in one sentence: the templates and the generator share clinical assumptions, so results say nothing about real patients.
8. `## Limitations` lists at least: one main pathology (ADR-001); simplified PK/PD; adherence model is an assumption because no public smart-dispenser dataset is known (analisi §5.1); literature priors versus MIMIC priors labelling (ADR-005); clinical parameter values unverified unless `reviewed_by` is set (ADR-020); C3 limited to declared attack classes and the undetectable rows reported as a result (ADR-002); alert load on synthetic days does not replace the unlabeled real-data run (WS08-T06, if it was done); sparse blood-pressure sampling. Each item ends with a source (an ADR id or an analisi section).
9. `## Composition` lists the `GroundTruthEvent.subtype` vocabulary exactly as in the WS04 README, states that `DISPENSE` (dispenser opening) and `INTAKE` (verified by the robot) are distinct signals and that opening does not prove intake (ADR-004), and cites the trace schema version by the `Version` line of `02-interfaces.md#trace-schema` (`grep -n 'Version' docs/plan/02-interfaces.md` near that heading agrees with the datasheet).
10. `## Summary` and `## Intended use` contain the phrases `semi-synthetic`, `pre-clinical technical validation` and `no real patients`; `## Out-of-scope use` names at least clinical decision making, estimating drug effect sizes or prevalence, and claims about performance on real patients.
11. Glossary and claims (`01-conventions.md` section 7, analisi §4.8): `grep -niE 'subsystem|edge cloud|ensures|distribution-free|intrinsic explainab|orthogonal' docs/benchmark/*.md` prints nothing; the word `robust` is not used for noise tolerance; no clinical numeric value appears outside a quotation of the registry (`grep -nE '[0-9] ?mmHg' docs/benchmark/*.md` is reviewed line by line).
12. Generator document: every command in `generator.md` was run and exited 0 (the `## Quick generation` section produces a `manifest.json` from an explicit seed at a small scale); command options are copied from the `--help` output of the builder CLI of WS04-T11; the manifest keys listed are exactly those the WS04-T01 serialiser writes.
13. `## Distribution and licence` cites an ADR id that exists (`grep -n '^## ADR-<id>' docs/plan/03-decisions.md` prints one line) or carries the sentence required in Contesto; it states which benchmark files are released (manifest, seeds and a sample of days, or the full set) as listed in the manifest, and that the generator and seeds allow regeneration.
14. Anonymity: neither file contains a name, affiliation or funding statement; `python tools/check_anonymity.py docs/benchmark --terms outputs/anonymity/terms.txt` exits 0 if the tool and the terms file exist (WS13-T03), otherwise the completion note says the check is left to WS13-T03.
15. `## Ethical considerations` states that no real patient data is released, that the data must not be used for clinical decisions, and that credentialed data terms are respected (check 6).
16. `git remote -v` printed at the start and at the end of the task is identical.

## Passi

1. Create the branch `ws13-t04-generator-datasheet` from `main` and record `git remote -v`. Do not run any command that writes to a remote: pushing to any remote requires explicit human approval, which this task does not have; if a step seems to need it, stop and report.
2. Collect facts, each with its source: generate a small benchmark with the builder CLI (`--help` first) at an explicit seed if none exists, and open its `manifest.json`; read the WS04-T12 validation report and note its path; read the WS04 README for the subtype vocabulary; list the tests of WS04-T10 (`ls tests/benchmark`) and note which files show the latent versus observed separation; read `WS00-T04.md` if it exists; grep for the licence ADR of WS13-T01 in `docs/plan/03-decisions.md`.
3. Write `docs/benchmark/generator.md`, in this order: `## Overview` (the stages: `PriorSource`, latent patient with baseline pressure, circadian component and autoregressive noise, PK/PD response with onset window, adherence model with `DISPENSE` and `INTAKE`, measurement process, injection of C2, C3 at the naive and informed attacker levels and C1 with deliberate confounders, ground truth on the latent trace; one sentence each, taken from analisi §5.1), `## Modules` (each stage mapped to its file in `src/ralmon/benchmark/`, from `ls`), `## Configuration` (seed, scale, split by patient, from `--help`), `## Quick generation` (commands run and shown), `## Manifest` (keys), `## Determinism` (explicit seed for every `numpy.random.Generator`; same seed, same bytes on the same machine, `01-conventions.md` section 3), `## Extending` (adding a `PriorSource` implementation such as `MimicPriorSource` as in ADR-005; adding an injection subtype, which needs an entry in the subtype vocabulary and a ground truth rule), `## Inspecting circularity` (where the latent ground-truth labeller lives, the WS04-T10 tests by path and the command that runs them).
4. Write `docs/benchmark/datasheet.md` section by section in the order of check 2. Fill `## Composition`, `## Provenance of parameters` and the source data table with a throwaway Python snippet that prints markdown rows from `manifest.json` and the validation report, so no number is typed by hand; the snippet is not committed. Follow the structure of the Datasheets for Datasets proposal (Gebru et al.); do not cite its year or venue in the file, since bibliography entries are verified by a human first (ADR-018).
5. Write `## Source data and licences` as check 5 and check 6 require. For each row, copy the licence text and its `Source:` line from `WS00-T04.md`; where the human artefact is silent or absent, write `unverified` and leave `licence_verified_by` empty. State the count of unverified rows and add the sentence that a human must verify them before the public release.
6. Write `## Semi-synthetic nature and non-circularity`, `## Intended use`, `## Out-of-scope use`, `## Limitations` (each item with its source), `## Distribution and licence`, `## Maintenance and versioning` (benchmark version directory, manifest with generator revision, trace schema version, changes through an ADR) and `## Ethical considerations` as in checks 7 to 15. Do not name authors, funders or institutions.
7. Add the two links to `## Documentation` of `README.md` if the file exists.
8. Run checks 1 to 16 and fix failures. Commit on the branch with messages `WS13-T04: <summary>`; the last commit sets `status: done` in this task file. Merge to `main` locally. Do not push (pushing to any remote requires explicit human approval).
9. Write the completion note: check output, count of unverified licence rows, whether the licence ADR was found, and the open human actions (verify source-data licences, state what the data use agreements allow, confirm the licence ADR).

## Done when

From the repository root:

- `test -f docs/benchmark/datasheet.md && test -f docs/benchmark/generator.md` exits 0.
- `grep -cE '^## (Summary|Motivation|Composition|Generation process|Provenance of parameters|Source data and licences|Semi-synthetic nature and non-circularity|Intended use|Out-of-scope use|Limitations|Distribution and licence|Maintenance and versioning|Ethical considerations)$' docs/benchmark/datasheet.md` prints `13`.
- `grep -cE '^## (Overview|Modules|Configuration|Quick generation|Manifest|Determinism|Extending|Inspecting circularity)$' docs/benchmark/generator.md` prints `8`.
- `grep -c 'unverified' docs/benchmark/datasheet.md` prints a number of 1 or more whenever at least one licence or parameter row is unverified, and the count of unverified rows in the text equals the count of `unverified` cells in the two tables.
- `grep -c 'pre-clinical technical validation' docs/benchmark/datasheet.md` prints 1 or more.
- The command of `## Quick generation` in `generator.md`, run from the repository root, exits 0 and writes a `manifest.json`.
- The completion note shows the output of checks 1 to 16.
