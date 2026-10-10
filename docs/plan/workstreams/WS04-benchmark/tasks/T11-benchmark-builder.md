---
id: WS04-T11
title: "Benchmark builder CLI: splits by patient, manifest, seeds, scale"
workstream: WS04-benchmark
owner: agent
status: blocked
depends_on: ["WS04-T10", "WS04-T15"]
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

### Hand-over from the WS05-T03 review (orchestrator, 2026-10-09)

WS05-T03 (`ralmon.spec`, branch `ws05-t03-spec-package`, status `in_progress` when this note was written) is implemented. (1) Where this task says to load the F0 copy or the fixture registry, `load_registry(path, step_ms=..., allow_fixture_only=True)` is required: without the flag the first run raises a `RegistryError` that names the FIXTURE-ONLY rows (ADR-027); the shared file is `configs/registry/fixture.yaml` (version 0.0.0) and the test-owned copy is `tests/fixtures/spec/registry_f0.yaml`. (2) The real registry (0.2.0) has three unset names (`priority_sys`, `priority_int`, `bound_dose_count_upper`): `get()` raises `UnsetParameterError` (a `RegistryError`) for them while `load_templates` still succeeds, so ranking SYS and INT alerts, or reading the dose-count bound, must be handled explicitly or done with the fixture registry. (3) A plan builder signs with `HmacSha256PlanVerifier(key).sign(plan)`; integers of the plan (`schedule`, `anchor_ms`, `plan_version`) must be Python or NumPy integers in the signed 64-bit range, `param_values` are written as floats.

### Hand-over (worker, 2026-10-09, from the WS05-T04 review)

(1) The builder must emit what the option chosen in ADR-054 needs. With the current generator (presence `1.0` at arrivals, no zero, no availability) INT is blind after the first robot visit of a day: `run_offline` has no availability input, so the level of the last visit is read at every later dispense. Recommended option (b): write a robot `NODE_STATE` report (`payload.state` `active`, `payload.colocated` true at each arrival and false at each departure, from `ObservedStream.visits`; this is the open M2 item of WS04-T06) and have `run_offline` turn it into availability marks (WS05-T08). Gate every INT-based number on `run_offline_detailed(...).stats.presence_level_older_than_window_steps == 0`. (2) `run_offline` returns the records only; `run_offline_detailed` (package root, outside `__all__`) returns `OfflineResult(records, late_inputs, rejected_inputs, stats)` for the validation report and the alert-load check. (3) A plan needs at most one parameter record per template (`anchor_ms` None), SCHED ticks and the day-end COUNT as anchored instances (COUNT anchor a positive multiple of `T_day`), `registry_version` equal to the registry in use, `plan_version` not lower per `care_plan_id`; dynamic instances are keyed `<template id>@<t_device_ms of the anchoring event>` with `#2`, `#3` on a clash. (4) The generator's `day_end` Sample is now ignored by the monitor (counted in `stats().ignored_samples`).

### Hand-over (worker, 2026-10-09, from the WS05-T04 review, round 2)

Correction of the gate in the hand-over above: it said to require `presence_level_older_than_window_steps == 0`, which cannot be met (the generator's dwell of 10 minutes exceeds `int_window` of 5, so any visit counts, with or without marks). The gate is `stats().presence_samples_without_availability_marks == 0`: non-zero exactly when presence samples were used and no availability mark for `presence` ever arrived. Emit the robot `NODE_STATE` reports (ADR-054 option (b)) or the explicit zeros (option (a)) and read that counter from `run_offline_detailed`.

Time axis and plan anchors of `run_offline`: the days of a patient are written on one continuing axis (`day_index * T_day + clock time`, WS04-T06), and `run_offline` now runs the day `day_index` from the step `day_index * K` on that axis (it used to run steps 0 to K whatever the day, so a day with `day_index >= 1` was accepted with 0 inputs and no error). Consequences for the builder: (1) the times of day `d` must be on the continuing axis (a day written on the per-day axis with `day_index >= 1` has every input rejected as finalised, visible in `stats().after_finalisation_count`); (2) the plan may list the instances of other days: those anchored before the first step of the run are skipped and counted in `stats().plan_instances_before_start`, those anchored in the finalised past of the run still raise `PlanFeasibilityError`; the day-end COUNT of day `d` has the anchor `(d + 1) * T_day`; (3) there is no carry-over between days (ADR-046 is not implemented): the 24 h counter and the held levels start empty at the first step of the run, so a counter that depends on the previous day under-counts. The contract text of `TimeMs` ("since the start of the patient-day trace") reads as the per-day axis; ADR-053 (h) asks the plan owner to settle the axis in `02-interfaces.md`.

### ADR-046 adopted (gab, 2026-10-09)

The history input is in the contract (`#monitor` 0.2.0): WS05-T10 adds `history` to `run_offline` and WS04-T15 labels a day with the earlier days as history, so point (3) of the paragraph on the time axis ("no carry-over between days") stops being true once they are done. The builder passes to the labeller and to the detectors the days that precede the day to build (at least `H = max(T_day, largest window parameter)` of history; one day is enough with the registry of today), and an event belongs to the day in which the monitor decides it (its onset may lie in the previous day). The `Detector` contract has no history input yet: see ADR-046, status.

### ADR-054 decided (gab, 2026-10-09)

Option (b) is chosen. The builder writes a robot `NODE_STATE` report per visit of `ObservedStream.visits`: `payload.colocated` true at the arrival and false at the departure (`payload.state` `active`; the payload key follows ADR-035). WS05-T11 turns the reports into the availability of both robot channels. Gate every INT-based number on `run_offline_detailed(...).stats.presence_samples_without_availability_marks == 0` (the correction above stands: `presence_level_older_than_window_steps` is information only).

### Real signature of the monitor history input (worker of WS05-T10, 2026-10-10)

`run_offline(day, plan, config, calibrator, forecaster, *, registry=None, templates=None, verifier=None, history=())` and `run_offline_detailed(...)` with the same arguments (`history: Sequence[ObservedDay] = ()`, typed in code as `Sequence[ObservedTrace]`). The builder passes the earlier days of the patient (continuing axis, increasing `day_index`, same `patient_id`, at most `MAX_HISTORY_DAYS` = 14 days before the day); the detectors of WS06 still run per day (the `Detector` contract has no history, ADR-046 status). The labeller signature is WS04-T15's.

### Hand-over from WS05-T11 (worker, 2026-10-10)

The monitor reads the reports now (`StreamingMonitor.push_event`, so `run_offline` too). What the builder must write, checked against the code: (1) an `Event(EventKind.NODE_STATE, t, t_rx, "robot", {"state": "active", "colocated": True|False}, seq)` per arrival (true) and per departure (false); the source must be exactly `"robot"` (`vocab.SOURCE_ROBOT`), otherwise the report is ignored and counted in `stats().colocated_reports_ignored`; the value must be a real `bool`. (2) `ralmon.benchmark.vocab` does not declare `colocated` yet: `PAYLOAD_KEYS[EventKind.NODE_STATE]` is `{state, commanded}`, so `check_payload` would refuse the key; add `KEY_COLOCATED` there (and to `__all__`). (3) The mask starts as "available until the first report" (not H-INIT unavailable), so write an arrival report for every visit, including the first of the day, at or before its presence sample. A presence sample used before the first report of the run does not witness later dispenses (the held level is cleared at that report) and is counted by the gate, so a dropped first arrival report (a C2 fault of the report stream, an injector that removes events) makes `presence_samples_without_availability_marks` positive on that day: keep it in mind in the builder and in the injectors, and report such days instead of filtering them silently. (4) The gate `presence_samples_without_availability_marks == 0` is satisfied by the first applied report of either value; a day with no visit has no presence sample and passes trivially. (5) A report with the same device time as the presence sample of the arrival is fine (marks are applied before samples at one device time).
