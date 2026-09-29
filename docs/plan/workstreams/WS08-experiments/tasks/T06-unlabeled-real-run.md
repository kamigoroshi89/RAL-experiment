---
id: WS08-T06
title: "Unlabeled real-data run for alert load (blocked until access)"
workstream: WS08-experiments
owner: agent
status: blocked
depends_on: ["WS08-T02", "WS04-T13"]
critical_path: false
non_negotiable: false
estimate_pd: 1.5
sources: ["analisi §5.1", "analisi §5.8", "analisi §10 (1)", "analisi §2 R3 weakness 6"]
interfaces: ["02-interfaces.md#priorsource"]
review_items: []
---
## Obiettivo

Report the alert load per patient-day of the proposed method on real, unlabeled episodes (MIMIC-IV-ED or eICU stays, no injection), which analisi §5.1 and §5.8 call "fortemente raccomandato, costo basso" and which analisi §10 objection 1 lists as a defence against the circular-evaluation objection. Without ground truth there is no precision, recall or attribution accuracy: the run reports counts only. Concrete output: `realdata.py` (adapter from the extract to `ObservedDay`, care-plan instantiation, aggregate-only reporting), `experiments/unlabeled-real.yaml`, `outputs/unlabeled-real/<seed>/...`, and, per ADR-005, the repetition of the main experiment with MIMIC priors (`experiments/main-mimic.yaml`, `outputs/main-mimic/<seed>/...`).

## Contesto

- Blocked until WS08-T02 and WS04-T13 are `done`. WS04-T13 itself waits for WS00-T04: `docs/plan/workstreams/WS00-admin/outputs/WS00-T04.md` must show `access_status: granted` and `access_verified_on:`. The extract sits under `data/raw/` and is never committed. If access is `refused`, see the refusal path in Passi.
- `docs/plan/workstreams/WS00-admin/outputs/WS00-T04.md`, section `## Data handling constraints` (where the data are stored, what the DUA allows; agents receive only derived parameters unless the DUA allows more) and ADR-005 (results before access are labelled "literature priors"; key experiments are repeated with MIMIC priors).
- WS04-T13 completion note: the schema note (table and column names read from the real data after access) and `MimicPriorSource`; `02-interfaces.md#priorsource`.
- `docs/plan/workstreams/WS08-experiments/README.md` (conventions E8, E10; rules H6, H9) and `docs/source/analisi.md` §5.1 (unlabeled run), §5.8, §10 objection 1.
- `outputs/main/` from WS08-T02 (the synthetic alert load to compare with).

## File toccati

- `src/ralmon/eval/realdata.py` (create): extract-to-`ObservedDay` adapter, `instantiate_care_plan`, `RealDataHooks` (`hooks_for("unlabeled-real")`, `hooks_for("main-mimic")`), `variant_components` for `ours-recal`, disclosure-control helper.
- `experiments/` (create `unlabeled-real.yaml` and `main-mimic.yaml`; the directory is one path).
- `tests/eval/test_realdata.py` (create).
- `tests/fixtures/eval/realdata/` (create): a stand-in extract in the layout recorded by the WS04-T13 schema note (invented rows, clearly labelled as a fixture, never real data).

## Test

Write these first. The fixture extract is written by hand from the schema note of WS04-T13; the plan does not name tables or columns, because analisi §5.1 asks that the MIMIC-IV-ED schema be verified after access (marked † in the analysis).

`tests/eval/test_realdata.py`

1. `test_adapter_maps_fixture_extract_to_observed_days`: the stand-in extract with 2 patients (stay 1: three pressure measurements and one medication administration; stay 2: two measurements) gives 2 `ObservedDay`s with 3 and 2 `bp` samples, one `DISPENSE` event in the first, timestamps as integer milliseconds since the start of the day, `patient_id` values that are pseudonymous keys not present in the report.
2. `test_adapter_never_builds_latent_or_ground_truth`: the adapter returns `ObservedDay` only; no `LatentDay`, `BenchmarkDay` or `GroundTruthEvent` is constructed (checked with a spy on the constructors).
3. `test_care_plan_omits_templates_without_signals`: an episode with no `intake`, `presence` or robot data gets a plan without the `INT` template; the omission is listed in `analysis.data_scope.omitted_templates`; registry values are those of the main experiment (unchanged, same `registry_version`).
4. `test_alert_load_hand_computed`: 12 alerts over 4 patient-days give 3.0 per patient-day; by template RANGE 8 and SCHED 4 give 2.0 and 1.0; by verdict kind the split of PREDICTED_VIOLATION and VIOLATED sums to 12.
5. `test_real_run_has_no_ground_truth_metrics`: `per_class_prf`, `detection_delay_ms`, `recall_vs_false_alarm_curve`, `attribution_confusion`, `accuracy_vs_coverage` and `severity_rank_agreement` are `null` for every detector; the alert load is under `analysis.alert_load_real`.
6. `test_metrics_contain_only_whitelisted_aggregate_keys`: `metrics.json` has no key named `patient_id`, no per-event timestamp list and no list longer than the number of templates times verdict kinds times causes.
7. `test_small_cells_suppressed`: with `min_cell = 5` (test value; the real value is the one in WS00-T04 `## Data handling constraints`, or absent if the DUA states none) an aggregate over 3 patient-days is `null` with `suppressed: true`.
8. `test_run_refuses_without_dua_confirmation`: `run_options.extra.dua_confirmed` false or absent raises `ConfigError`; the flag records that the processing is permitted by the DUA note.
9. `test_recal_variant_fits_on_real_calibration_split_only`: `ours-recal` calls `fit` of the calibrator with episodes from real calibration patients only (patient-level split) and never with ground truth; `ours` keeps the calibrator fitted on the synthetic benchmark.
10. `test_alert_load_comparison_with_synthetic`: `analysis.alert_load_comparison` holds the real load and the synthetic load of the same detector from `outputs/main` side by side, and a `caveats` list that names the difference in measurement cadence between the real setting and the ward scenario (reported as measurements per patient-day, mean and median, computed from the data).
11. `test_prior_source_label_in_meta`: `meta.prior_source` is `"mimic"` for `main-mimic` and `"literature"` for `main`; `analysis.prior_label` for `main-mimic` reads "MIMIC priors (parameters only; traces are synthetic)".
12. `test_yaml_files_load`: `experiments/unlabeled-real.yaml` has detectors `["B1", "ours", "ours-recal"]` and a `match` block equal to that of `main.yaml` marked unused; `experiments/main-mimic.yaml` equals `main.yaml` except `experiment_id`, `benchmark_manifest` and `prior_source`.

## Passi

1. Verify the unblock conditions: `access_status: granted` and `access_verified_on` in `WS00-T04.md`, WS04-T13 `done`, the schema note present. Read `## Data handling constraints`: if the DUA does not allow an agent to process the data, the code and tests are written on the fixture and the run of step 6 is executed by the credentialed person on the machine that holds the data; only the aggregate `metrics.json` files come back. Branch `ws08-t06-unlabeled-real`; set `status: in_progress`.
2. Write the fixtures and tests 1 to 12; run `pytest tests/eval/test_realdata.py -q`; confirm they fail. Commit `WS08-T06: add failing real-data tests`.
3. Implement the adapter from the schema note (no column name is written from memory), `instantiate_care_plan` (schedule from the recorded administration and measurement times of the episode; templates whose signals are absent are omitted and listed) and the disclosure-control helper. Tests 1 to 3, 6, 7 pass.
4. Implement the aggregate hooks and the two variants: `ours` (calibrator fitted on the synthetic benchmark as in `main`, applied unchanged: this transfer is itself a distribution shift and is stated as such) and `ours-recal` (calibrator refitted on a patient-level real calibration split using only measured completed-trace robustness, no labels; `fit` again, `02-interfaces.md#conformal-calibrator` rule 4). Tests 4, 5, 8 to 11 pass.
5. Write `unlabeled-real.yaml` and `main-mimic.yaml` (test 12). `dua_confirmed` is set to true only after the human confirms the DUA note.
6. Run `python -m ralmon.eval.runner --config experiments/unlabeled-real.yaml --output outputs` and, with the MIMIC-prior benchmark built by the WS04-T11 builder, `python -m ralmon.eval.runner --config experiments/main-mimic.yaml --output outputs`; then `python -m ralmon.eval.analysis --check outputs/unlabeled-real outputs/main-mimic`.
7. Read the results under rules H6 and H9 and write the completion note: real alert load per patient-day with intervals, by template, verdict kind and cause (with the statement that real data carry no robot evidence, so attribution is limited by construction); the comparison with the synthetic load and its caveats; whether the `main` ranking of methods is the same with MIMIC priors; the number of patient-days and patients. Do not describe alerts on real data as false alarms or as errors: there is no ground truth.
8. Refusal path. If `WS00-T04.md` records `access_status: refused` for both datasets, do not create the two configurations; write in the completion note the consequence recorded in that file, set the task to `done` with the note "not run", and T07 records `not_run: blocked on access` for `unlabeled-real` and `main-mimic`. `main` stays labelled "literature priors".
9. Run the Done when commands, commit `WS08-T06: add unlabeled real-data run and MIMIC-prior main`, set `status: done`.

## Done when

- `pytest tests/eval -q` exits 0, `ruff check src tests` exits 0, `mypy src/ralmon` exits 0.
- `for id in unlabeled-real main-mimic; do n=$(ls outputs/$id/*/metrics.json | wc -l); test "$n" -ge 5 || echo "$id has $n seeds"; done` prints nothing (or the completion note records the refusal path).
- `python -m ralmon.eval.analysis --check outputs/unlabeled-real outputs/main-mimic` exits 0.
- `grep -l 'patient_id' outputs/unlabeled-real/*/metrics.json` prints nothing.
- `git check-ignore -q outputs && git check-ignore -q data/raw` exits 0 (no real-data derived file can be committed).
