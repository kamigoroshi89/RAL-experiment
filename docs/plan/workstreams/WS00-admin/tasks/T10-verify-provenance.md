---
id: WS00-T10
title: "Verify the literature-prior provenance table produced by WS04-T02"
workstream: WS00-admin
owner: human
status: blocked
depends_on: ["WS04-T02"]
critical_path: false
non_negotiable: false
estimate_pd: 1
sources: ["analisi §5.1", "analisi §2 R3 weakness 3"]
interfaces: ["02-interfaces.md#priorsource", "02-interfaces.md#parameter-registry"]
review_items: ["R3-W3"]
---
## Obiettivo

Turn the literature priors from "cited" into "verified". WS04-T02 produces a provenance table in which every parameter of the latent patient, PK/PD, adherence and device-error models carries a `source_ref` and `verified_by: null`. A human (with the clinician of WS00-T03 for clinical values) checks each value against its cited source and records the result, so that the paper can state which parameters are verified (ADR-020, analisi §2 R3 weakness 3). Not blocking for the pipeline: unverified values are allowed but reported. Concrete output: `docs/plan/workstreams/WS00-admin/outputs/WS00-T10.md` and updated `verified_by` fields in the prior YAML.

## Contesto

- `docs/plan/workstreams/WS04-benchmark/tasks/T02-priorsource-literature.md` (where the table and the YAML are, and how the table is regenerated).
- `docs/plan/02-interfaces.md#priorsource` (`ParamProvenance`: `source_ref`, `verified_by`).
- `docs/plan/03-decisions.md` ADR-005 and ADR-020.
- `docs/source/analisi.md` §5.1 (values from published literature, device validation protocol to verify).

## File toccati

- `docs/plan/workstreams/WS00-admin/outputs/WS00-T10.md` (create)
- `configs/priors/literature_hypertension.yaml` (modify: only the `verified_by` and, where wrong, `value` and `source_ref` fields)

## Test

Verification checks:

1. The artefact has one row per parameter of the provenance table with the fields `parameter:`, `value:`, `source_ref:`, `checked_against:` (page or table of the source), `result:` (one of `confirmed`, `corrected`, `rejected`, `unverifiable`) and `verified_by:` (a name).
2. Every parameter whose `result` is `confirmed` or `corrected` has `verified_by` set in the YAML; every `rejected` or `unverifiable` parameter keeps `verified_by: null` and is listed in `## Unverified parameters`.
3. The count of rows equals the count of rows of `docs/benchmark/parameter-provenance.md` (regenerated after the edit).
4. The artefact states the date and whether the clinician of WS00-T03 checked the clinical parameters.

## Passi

1. Regenerate `docs/benchmark/parameter-provenance.md` (command in WS04-T02) and read it row by row.
2. For each row open the cited source and check value and units; record the four fields of check 1.
3. Edit the YAML `verified_by` fields; regenerate the table and compare the row count.
4. List the unverified parameters in `## Unverified parameters`; the paper limitations paragraph (WS12-T06) reads that list. Set `status: done`.

## Done when

- `test -f docs/plan/workstreams/WS00-admin/outputs/WS00-T10.md` exits 0.
- `grep -c '^parameter:' docs/plan/workstreams/WS00-admin/outputs/WS00-T10.md` equals the number of data rows of `docs/benchmark/parameter-provenance.md`.
- `grep -c '^## Unverified parameters$' docs/plan/workstreams/WS00-admin/outputs/WS00-T10.md` prints `1`.
