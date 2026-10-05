---
id: WS04-T13
title: MimicPriorSource and eICU variant (blocked until credentialing)
workstream: WS04-benchmark
owner: agent
status: ready
depends_on: ["WS04-T02", "WS00-T04"]
critical_path: false
non_negotiable: false
estimate_pd: 2
sources: ["analisi §5.1", "analisi §5.1 (MIMIC-IV, MIMIC-IV-ED, eICU; unlabeled real-data run)", "analisi §9 (0.6)"]
interfaces: ["02-interfaces.md#priorsource"]
review_items: []
---
## Obiettivo

Add the second `PriorSource` implementation announced by ADR-005: `MimicPriorSource`, with its eICU variant used as the second cohort of the distribution-shift test (analisi §5.1, §5.6 A6), so that parameters (pressure baseline and variability, drug response, onset window, inter-patient spread) come from real data instead of literature values. Add the estimation script, run by the credentialed person, that turns local tables into an aggregate-only estimates file with provenance, and the adapter that turns real, unlabeled episodes (MIMIC-IV-ED or eICU, no injection) into `ObservedDay`s for the alert-load run of WS08-T06. No consumer changes: everything flows through `PriorSource`. Concrete output: `mimic_prior.py`, `estimate_priors.py`, `real_episodes.py`, `docs/benchmark/mimic-schema-verification.md`, the estimates files, tests.

## Contesto

- `docs/source/analisi.md` §5.1 (MIMIC-IV eMAR and intermittent non-invasive pressure; MIMIC-IV-ED "dovrebbe contenere segni vitali periodici e dispensazioni da armadi automatici ... verificate lo schema"; eICU as second cohort; "run su dati reali non etichettati (episodi MIMIC-IV-ED o eICU senza iniezione)").
- `docs/plan/workstreams/WS00-admin/outputs/WS00-T04.md` (`access_status:` and `access_verified_on:` lines, `## Data handling constraints`: where the data lives and whether row-level data may be sent to hosted services).
- `docs/plan/03-decisions.md` ADR-005 (results before access are labelled "literature priors"), ADR-020; `02-interfaces.md#priorsource`.
- WS04-T02 (`priors.py`, row schema, provenance table) and WS04-T06 (`docs/benchmark/public-sources.md`).
- `docs/plan/workstreams/WS08-experiments/README.md` (`unlabeled-real`, `main-mimic` and `shift` experiments that consume this task).

Unblocked when WS00-T04 is `done` (both `access_status:` lines are `granted` or `refused`; if refused, this task and WS08-T06 are dropped and the results stay labelled "literature priors") and WS04-T02 is `done`. Read `## Data handling constraints` first: unless the data use agreement explicitly allows more, the agent receives only the schema description and aggregate estimates, and the human runs `estimate_priors.py` and the adapter on the credentialed data.

## File toccati

- `src/ralmon/benchmark/mimic_prior.py` (create: `MimicPriorSource`, cohort variants `mimic` and `eicu`, hybrid fallback).
- `src/ralmon/benchmark/estimate_priors.py` (create: estimation script, aggregate-only output).
- `src/ralmon/benchmark/real_episodes.py` (create: unlabeled episode adapter).
- `tests/benchmark/test_mimic_priors_and_episodes.py` (create).
- `docs/benchmark/mimic-schema-verification.md` (create).
- `configs/priors/` (modify: add `schema_map_mimic.yaml`, `schema_map_eicu.yaml` and the human-produced estimates files `mimic_hypertension.yaml`, `eicu_hypertension.yaml`).

## Test

Fixtures are tiny synthetic tables written after step 1, in the column layout that the human-verified schema description gives; their numbers are arithmetic and fixture-only. No real data appears in the repository. Write first.

1. `test_mimic_prior_source_satisfies_protocol_and_covers_fields`: the four `PriorSource` members exist and `provenance()` covers every numeric field of the contract dataclasses.
2. `test_estimates_without_source_ref_rejected`: a row with a value and no `source_ref` raises `MissingProvenanceError` (same rule as T02).
3. `test_estimates_must_be_aggregates_only`: an estimates file with per-patient keys (`subject_id`, `patient_id`, row arrays) raises `DisclosureError`; cells below the declared minimum group size are suppressed (the size is read from `## Data handling constraints`, not chosen here).
4. `test_hybrid_fallback_marks_origin_per_parameter`: parameters absent from the estimates come from `LiteraturePriorSource`; each provenance entry states its origin, so a mixed prior is never presented as fully dataset-derived.
5. `test_eicu_variant_selected_by_cohort_and_differs`: `cohort="eicu"` reads the eICU estimates, has its own `name`, and yields different parameters from the MIMIC fixture.
6. `test_estimator_recovers_known_parameters_from_synthetic_tables`: tables generated from known fixture parameters (seed 0) give baseline mean, SD and response magnitude within four standard errors.
7. `test_estimator_declares_unidentifiable_parameter`: with sparse sampling (fixture) the absorption and elimination rates are reported as unidentifiable and the estimates file leaves them to the fallback, with the reason in the provenance note.
8. `test_estimator_refuses_without_local_data`: a missing data root raises `DataNotAvailableError` naming WS00-T04.
9. `test_estimator_reads_only_data_raw_and_writes_only_configs_priors`: path confinement in both directions.
10. `test_estimates_header_requires_release_approval`: an estimates file needs a non-null `aggregates_release_approved_by` (the human who checked the data use agreement) to load, unless `allow_unapproved=True` is passed for development.
11. `test_real_episode_adapter_returns_observed_days_only`: outputs are `ObservedDay` values; no `LatentDay` and no `GroundTruthEvent` is constructed in the module (AST scan).
12. `test_adapter_times_are_integer_ms_and_days_are_24h_windows`: times are integer milliseconds from the episode start (ADR-017); an episode of 30 hours gives two days.
13. `test_adapter_pseudonymises_ids_with_salt`: same input and salt give the same `patient_id`, another salt another id, and the source identifier never appears in the output.
14. `test_adapter_ignores_unmapped_columns_and_reports_count`: columns outside the verified mapping are ignored and counted.
15. `test_gitignore_covers_data_raw_and_outputs`: `.gitignore` lists `data/raw/` and `outputs/`.
16. `test_manifest_flags_credentialed_source`: a build with `MimicPriorSource` records the prior source name and dataset versions in `settings`, and no row-level data.
17. `test_only_aggregate_yaml_in_configs_priors`: every file under `configs/priors/` other than schema maps validates as an aggregate estimates file.

## Passi

1. Verify the schema before coding. From the dataset pages and documentation (or the human's notes if the agreement forbids more), fill `docs/benchmark/mimic-schema-verification.md` with the H2 headings `## Purpose`, `## Access and handling`, `## MIMIC-IV hosp and ICU`, `## MIMIC-IV-ED`, `## eICU-CRD`, `## Column mapping`, `## Estimators`, `## Evaluable templates for the unlabeled run`, `## Verification`. Write only what was verified: which tables hold medication administration, intermittent non-invasive pressure, periodic vital signs and automated-cabinet dispensing, with their real column names and dataset versions; whether MIMIC-IV-ED contains what analisi §5.1 expects. `## Verification` has the fields `verified_by:`, `verified_on:` and `dataset_version:`, filled by the human.
2. Write `tests/benchmark/test_mimic_priors_and_episodes.py` and the synthetic tables from the verified layout; run, confirm failure; commit `WS04-T13: add failing mimic prior tests`.
3. Implement `mimic_prior.py` (same row schema and enforcement as T02; `cohort` in `mimic`, `eicu`; hybrid fallback with per-parameter origin; release-approval gate).
4. Implement `estimate_priors.py` and the two `schema_map_*.yaml` files. Each estimator is defined in `## Estimators` (cohort inclusion, target parameter, method, identifiability check, minimum group size) before it is coded. The drug is the registry anchor; if the data cannot identify a parameter at the available sampling density, the parameter stays with the literature fallback and the provenance note says why. No estimator is tuned to improve results.
5. Implement `real_episodes.py` and list in `## Evaluable templates for the unlabeled run` which φ_CP templates the real data can support (those needing a care-plan schedule may not be evaluable); WS08-T06 builds the care plan and runs the monitor.
6. Hand the scripts to the credentialed person with the exact commands; the estimates files are committed only after `aggregates_release_approved_by` is set. Note in the completion note whether the run happened on the agent side or the human side (README H5).
7. Refactor; run `ruff check src tests`, `mypy src/ralmon`, `pytest tests/benchmark -q`; commit `WS04-T13: add MimicPriorSource, eICU variant and unlabeled episode adapter`; set `status: done`.

## Done when

- `pytest tests/benchmark/test_mimic_priors_and_episodes.py -q` exits 0 and `pytest tests/benchmark -q` exits 0.
- `ruff check src tests` exits 0 and `mypy src/ralmon` exits 0.
- `grep -cE '^## (Purpose|Access and handling|MIMIC-IV hosp and ICU|MIMIC-IV-ED|eICU-CRD|Column mapping|Estimators|Evaluable templates for the unlabeled run|Verification)$' docs/benchmark/mimic-schema-verification.md` prints `9`, and `grep -E '^verified_by: .+' docs/benchmark/mimic-schema-verification.md` prints one line.
- `python -c "from ralmon.benchmark.mimic_prior import MimicPriorSource"` exits 0.

## Notes

### Blocking note (orchestrator, 2026-10-05)

SKIPPED by the loop (the status is `ready` only because `tools/check_plan.py` rejects `blocked` when every dependency is `done`; the loop skips tasks that carry an unresolved blocking note). WS04-T02 is done and WS00-T04 is `done` by the human's attestation, but the task needs the credentialed MIMIC-IV and eICU data under `data/raw/` and the record `docs/plan/workstreams/WS00-admin/outputs/WS00-T04.md` (`access_status: granted`), and neither exists in the repository (PhysioNet data is under a data use agreement and is never redistributed or fetched by the agent). Set the status aside (delete this subsection) once the data and the record exist.
