---
id: WS04-T11
title: "Benchmark builder CLI: splits by patient, manifest, seeds, scale"
workstream: WS04-benchmark
owner: agent
status: blocked
depends_on: ["WS04-T10"]
critical_path: true
non_negotiable: false
estimate_pd: 2
sources: ["analisi §5.1 (scale, split by patient, seeds)", "analisi §5.1 (generator, released)", "analisi §5.6 (A6 cohort shift)"]
interfaces: ["02-interfaces.md#trace-schema", "02-interfaces.md#experiment-config-and-outputs"]
review_items: ["R3-W1"]
---
## Obiettivo

Assemble the generator steps into `generate_benchmark`, the public entry point of `ralmon.benchmark`, and a command line to build, verify and (with T12) validate a benchmark version at the scale of analisi §5.1: 200 virtual patients x 7 days = 1400 patient-days, split by patient, with a manifest recording generator revision, seeds and prior provenance. Also provide the reader that other workstreams use (`open_benchmark`, `BenchmarkReader`, care-plan loader, the reusable `split_patients` helper) and the confounder twin patients. Concrete output: `builder.py`, `__main__.py`, `configs/benchmark/default.yaml`, tests and a proposed ADR on seed semantics and split fractions.

## Contesto

- `docs/source/analisi.md` §5.1 ("200 pazienti virtuali x 7 giorni = 1400 giorni-paziente, con split per paziente (training del predittore, calibrazione, test), almeno 5 seed") and §5.6 (A6, calibrate on one cohort and test on the other).
- `02-interfaces.md#trace-schema` (rule 2 split by patient, rule 3 files) and `02-interfaces.md#experiment-config-and-outputs` (`ExperimentConfig.benchmark_manifest`, `seeds`, `split`).
- `docs/plan/workstreams/WS08-experiments/README.md` (E1: one benchmark version, experiment seeds re-draw the split; assumption 4: `care_plan_id` resolves to a `CarePlan` through the loader of this task).
- WS04-T01 (`trace.py`, manifest), WS04-T05 (`schedule.py`), WS04-T09 and WS04-T10 (`assemble_latent_days`, `label_latent_day`, `assemble_benchmark_day`), WS05-T03 (`load_registry`, `load_templates`, `CarePlan`) and the monitor configuration of WS05.
- `docs/plan/workstreams/WS04-benchmark/README.md` (scale and splits paragraph, parameter policy).

Unblocked when WS04-T10 is `done`.

## File toccati

- `src/ralmon/benchmark/builder.py` (create: `generate_benchmark`, `BenchmarkReader`, `open_benchmark`, `split_patients`, care-plan writer and loader; composition module).
- `src/ralmon/benchmark/__main__.py` (create: `build`, `verify` and `validate` subcommands; `validate` is completed by WS04-T12).
- `src/ralmon/benchmark/__init__.py` (modify, together with `_stubs.py`: replace the placeholder of `generate_benchmark` and export `open_benchmark`, `BenchmarkReader`, `split_patients`).
- `configs/benchmark/` (modify: create `default.yaml`; injection rates and confounder pair counts go in `injections.yaml`).
- `tests/benchmark/test_builder.py` (create).
- `docs/plan/03-decisions.md` (modify: one proposed ADR, next free number).

## Test

Builds use a fixture-only prior, a fixture registry and a small scale (for example 4 patients x 2 days). Write first.

1. `test_build_small_benchmark_end_to_end`: run through the `build` and `verify` subcommands of the CLI (subprocess, `--allow-fixture-only --git-rev fixture`), 4 patients x 2 days give 8 observed files, 8 truth files, 4 care plans and one manifest; `verify` exits 0.
2. `test_same_config_and_seed_reproduce_bytes`: two builds of the same config and generation seed produce identical bytes for every file including the manifest (bit for bit, `01-conventions.md` section 3).
3. `test_different_generation_seeds_differ`: another seed changes the day files and keeps the patient id scheme.
4. `test_split_is_by_patient_no_leak`: every patient is in exactly one split, the union is complete, and the two members of a confounder pair are in the same split.
5. `test_split_patients_largest_remainder`: 7 patients with fractions 0.5, 0.25, 0.25 give sizes 3, 2, 2 (quotas 3.5, 1.75, 1.75; ties by split order); 10 patients with 0.5, 0.2, 0.3 give 5, 2, 3; fractions that do not sum to 1 raise `BenchmarkConfigError`.
6. `test_split_helper_same_seed_same_split_different_seed_differs`: deterministic per seed, independent of the input order of ids.
7. `test_default_scale_is_200_patients_7_days`: `default.yaml` declares 200 patients and 7 days, i.e. 1400 patient-days (analisi §5.1).
8. `test_config_requires_split_and_monitor_step`: a config without `split` fractions or without a monitor configuration for `latent_step_ms` raises `BenchmarkConfigError`; no silent default exists for either.
9. `test_fixture_only_prior_needs_flag_and_marks_manifest`: without the flag `FixtureOnlyPriorError`; with it the manifest has `fixture_only: true`.
10. `test_unfilled_prior_refuses_build`: a prior with `awaiting_human_value` rows raises `UnfilledParameterError` naming them; the manifest of a successful build has `n_unfilled: 0` and reports `n_unverified`.
11. `test_manifest_records_revision_provenance_and_settings`: `generator_git_rev` (passed explicitly in tests), the provenance rows equal `prior.provenance()`, and `settings` holds `latent_measurement_mode`, `jitter_source`, `segment_source`, `disabled_subtypes`, `latent_step_ms`, `numpy_version`, `python_version`; no wall-clock field.
12. `test_verify_detects_tampered_file`: one flipped byte makes `verify` fail naming the file.
13. `test_observed_loading_needs_no_truth_directory`: after deleting `truth/`, `BenchmarkReader.observed` works for every day and `.truth` raises `TruthUnavailableError`.
14. `test_care_plan_resolves_from_observed_day`: `reader.care_plan(day.care_plan_id)` returns a `CarePlan` whose ticks equal the schedule used by the generator (single source) and whose `registry_version` equals the registry's.
15. `test_care_plan_schedule_consistent_with_registry_windows`: `check_schedule_consistency` reports no problem for every patient.
16. `test_event_counts_in_manifest_match_truth_files`: recounting ground-truth events per `class/subtype` from the truth files equals `event_counts`.
17. `test_pair_patients_share_base_and_split`: the twin members of a confounder pair have equal `PatientParams`, equal latent baseline and cuff noise, different mechanism records, `role: confounder_pair` and a `pair` key in the manifest.
18. `test_cohort_option_builds_two_cohorts`: two priors produce patient ids prefixed by cohort id and cohort labels in the manifest, so a shift experiment can select by cohort.
19. `test_manifest_has_no_wallclock_fields`: no key or value derived from the clock or the host.
20. `test_public_api_exports`: `from ralmon.benchmark import generate_benchmark, open_benchmark, BenchmarkReader, split_patients` works.
21. `test_cli_help_and_exit_codes`: `python -m ralmon.benchmark --help` exits 0 and lists `build`, `verify`, `validate`; a bad config exits 2; a provenance error exits 3.
22. `test_default_config_rows_have_source_refs`: every design-choice row of `default.yaml` (split fractions, rates, pair counts) has `source_type` and `source_ref`.

## Passi

1. Write `tests/benchmark/test_builder.py`; run it, confirm failure; commit `WS04-T11: add failing builder tests`.
2. Implement `split_patients(ids, fractions, seed) -> Mapping[str, str]` (largest-remainder sizes, deterministic shuffle with `StreamPurpose.SPLIT`) and the reader (`open_benchmark(manifest_path, verify=False)`, `BenchmarkReader` with `patients`, `days`, `observed`, `truth`, `benchmark_day`, `care_plan`).
3. Implement `generate_benchmark(config, prior, out_dir, allow_fixture_only=False, git_rev=None) -> Manifest`. Per patient, in this order: draw the patient (`StreamPurpose.PATIENT`), derive the schedule from the registry windows, draw the injection specs from the rates in `injections.yaml` (`StreamPurpose.INJECTION_PLAN`) and resolve relative magnitudes with registry references, assemble the latent days (T09), label them (T10), build the observed base (T06), apply C2 and C3 (T07, T08; replay needs the previous observed day, so days run in order), finalise and write. Confounder twin patients are generated from `build_confounder_pair` with one day each. `latent_step_ms` is read from the monitor configuration named in the config so the labeller and the monitor share a grid. The care plans are built with `load_registry` and `load_templates` and written as `plans/<care_plan_id>.json` (canonical JSON).
4. Implement `__main__.py`: `build --config PATH --out DIR [--seed N] [--prior PATH] [--allow-fixture-only] [--git-rev REV] [--n-patients N] [--n-days N]`, `verify DIR`, and a `validate DIR` placeholder subcommand that prints "provided by WS04-T12" and exits 2 (never the built-in `NotImplementedError`, which the WS05-T01 test forbids outside `_stub.py`). The revision comes from `git rev-parse HEAD` only in the CLI (with a dirty-tree flag); `generate_benchmark` receives it as an argument. Exit codes: 0, 2 configuration, 3 provenance.
5. Write `default.yaml` (scale 200 and 7 from analisi §5.1; split fractions, injection rates and pair counts as `design_choice` rows with rationale: the sources fix the three roles but not the proportions, and the calibration split must hold whole patients because the conformal calibration unit is the patient episode, analisi §4.4). Append the ADR (status `proposed`): one benchmark version is fixed by one generation seed; the at least 5 seeds of analisi §5.1 are experiment seeds in WS08 (split and model randomness) plus at least 5 generation seeds checked by T12; split fractions; twin patients for confounder pairs; alternative: one benchmark per experiment seed.
6. Refactor; run `ruff check src tests`, `mypy src/ralmon`, `pytest tests/benchmark -q`; run one small CLI build with `--allow-fixture-only` and show its output in the completion note; commit `WS04-T11: add benchmark builder, reader and CLI`; set `status: done`.

## Done when

- `pytest tests/benchmark/test_builder.py -q` exits 0 and `pytest tests/benchmark -q` exits 0.
- `ruff check src tests` exits 0 and `mypy src/ralmon` exits 0.
- `pytest tests/benchmark/test_builder.py::test_build_small_benchmark_end_to_end -q` exits 0 (it runs the CLI `build` and `verify` on a fixture-only prior and shows their output).
- `python -c "from ralmon.benchmark import generate_benchmark, open_benchmark"` exits 0.

## Notes

### Hand-over from the WS04-T02 review (orchestrator, 2026-10-05)

The accessors `fixture_only`, `n_unfilled` and `n_unverified` exist only on `LiteraturePriorSource` (`fixture_only`, `unfilled_names()`, `unverified_names()`), not on the `PriorSource` Protocol (ADR-038 G10): use `getattr` and record it in the completion note. `LiteraturePriorSource` has no default path: pass the YAML path (`configs/priors/literature_hypertension.yaml`).

### Hand-over from the WS04-T09 review (orchestrator, 2026-10-07)

- Twin patients for a pair: use `dataclasses.replace(patient, patient_id=...)` with the same `patient_index` and seed (the members of `evaluate_pair` share one `patient_id`). For the days of a pair write `confounder_log(records)` or `member.log` (tagged with `variant_id` and `indistinguishable_by_construction`), not the plain `injection_log`.
- Set `dispenser_content_sensing` identically in `build_observed_base` and in `InjectionContext` (`Scenario.content_sensing` does both in `realise_scenario`; a builder that does not use it must do the same).
- The `expected_indistinguishable` values of the YAML grid are fixture expectations (`NoJitter`, a 10-minute dwell, two doses). With arrival jitter the computed `indistinguishable_by_construction` flag of a record differs in many realisations (fresh check of the review: 18 of 40 for `stress_nocontent_robot`, 17 of 40 for `naive_robot_noauth`, 21 of 40 for `naive_norobot_noauth`). Write and use the per-record computed flag, never the YAML value.
- Decide (and record) the owner of the robot `NODE_STATE` `colocated` report: no module writes it, so under H-INIT the extractor reads the robot as absent in every variant. ADR-040 (proposed) names this task; also decide where `baseline_sbp_mmhg` (a generator-side sidecar of `LatentResult`) is stored.
- Informational: the README says "robot no-show", but variant B of `refusal_vs_robot_missed` is `manipulation_failure` (the task test prescribes it); no variant realises a true no-show.
