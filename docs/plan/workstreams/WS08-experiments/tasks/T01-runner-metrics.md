---
id: WS08-T01
title: Experiment runner, config and metrics module
workstream: WS08-experiments
owner: agent
status: blocked
depends_on: ["WS04-T11", "WS06-T01", "WS05-T08", "WS05-T11"]
critical_path: true
non_negotiable: false
estimate_pd: 3
sources: ["analisi §5.5", "analisi §5.1", "analisi §5.4", "analisi §4.4"]
interfaces: ["02-interfaces.md#metrics", "02-interfaces.md#experiment-config-and-outputs"]
review_items: []
---
## Obiettivo

Implement `ralmon.eval`: every function of the `Metrics` contract with the matching, bootstrap and serialisation conventions E1 to E10 of the workstream README, the `ExperimentConfig` loader with a companion `RunOptions`, the seeded runner `run_experiment` that writes `outputs/<experiment_id>/<seed>/{config.yaml, metrics.json, git_rev.txt}`, and the `OursDetector` adapter (the proposed method as a `Detector`, with a seam for the ablation variants of T03 to T05). Concrete output: the package, its tests, a smoke configuration under `tests/fixtures/eval/`, and a `metrics.json` writer whose layout is the one documented in the README (WS09-T01 copies it).

## Contesto

- `02-interfaces.md#metrics` and `02-interfaces.md#experiment-config-and-outputs` (signatures, rules: bootstrap over patient-days, at least 5 seeds, coverage in distribution and under shift).
- `02-interfaces.md#detector` (`Detector.fit` and `run`, detectors never see `LatentDay` or `GroundTruthEvent`) and `02-interfaces.md#monitor` (`run_offline`).
- `docs/plan/workstreams/WS08-experiments/README.md`: metrics.json layout, conventions E1 to E10, the five assumptions about upstream deliverables.
- `docs/source/analisi.md` §5.5 (metric list) and §5.1 (scale, seeds, ground truth).
- Blocked until WS04-T11, WS06-T01 and WS05-T08 are `done` (the benchmark loader, the `Detector` harness and `run_offline` must import).

## File toccati

- `src/ralmon/eval/metrics.py` (create): `Matching`, `match_events`, `first_decidable_ms`, the eleven metric functions, helpers (`reliability_bins`, `residual_coverage`, `attribution_macro_f1`, `abstention_rate`), `bootstrap_ci`, `paired_bootstrap_ci`.
- `src/ralmon/eval/runner.py` (create): `ExperimentConfig`, `RunOptions`, `load_experiment`, `split_patients`, `build_detector`, `run_experiment`, `HookResult`, `current_git_rev`, layout writer, CLI `main`.
- `src/ralmon/eval/ours.py` (create): `PipelineComponents`, `OursDetector`.
- `src/ralmon/eval/__init__.py` (modify): exports the public names of `02-interfaces.md#package-public-api` for `ralmon.eval` plus the contract functions omitted there, `Matching`, `RunOptions`, `load_experiment`, `build_detector`, `split_patients`.
- `tests/eval/` (create): `test_metrics.py`, `test_runner.py`, `test_ours.py`.
- `tests/fixtures/eval/` (create): hand-written mini benchmark (6 patients, 2 days each), test registry marked "illustrative, unverified", `smoke.yaml` (experiment id `smoke`, one seed, `headline: false`).

## Test

Write these first; `pytest tests/eval -q` must fail on imports before any implementation. All values below are test fixtures, not results and not clinical claims.

**Fixture M1** (one patient-day, `tolerance_ms = 1_000`, `time_reference = "onset"`): ground truth g1 = C1 at 10_000, g2 = C2 at 50_000, g3 = C3 at 90_000. Detections: d1 t=10_400 label C1, d3 t=10_700 label C1, d2 t=50_900 label C3, d4 t=200_000 label C1. Hand-computed: g1 matches d1 (earliest in window), d3 is a duplicate, g2 matches d2 (900 <= 1_000), g3 is missed, d4 is the one false alarm.

`tests/eval/test_metrics.py`

1. `test_match_events_fixture_m1`: 2 pairs, 1 missed (g3), 1 duplicate (d3), 1 false alarm (d4).
2. `test_per_class_prf_fixture_m1`: C1 precision 0.5, recall 1.0, f1 2/3; C2 precision 0.5, recall 1.0, f1 2/3; C3 precision 0.0, recall 0.0, f1 0.0; `any` precision 2/3, recall 2/3, f1 2/3 (`precision_c = TP_c / (TP_c + FA)`).
3. `test_per_class_prf_undefined_is_nan_not_zero`: a class with no ground-truth events has recall `nan`; precision with `TP_c + FA = 0` is `nan`.
4. `test_false_alarms_per_patient_day`: M1 concatenated with one empty day (n_days = 2) gives 0.5; a wrong `n_patient_days` raises `ValueError`.
5. `test_detection_delay_onset_reference`: delays `[400.0, 900.0]` for M1; a detection 200 ms before an onset gives `-200.0` (early warning negative).
6. `test_first_decidable_ms_rules`: C1 `RESP` onset 100_000 end 400_000 gives 400_000; C1 `RANGE` onset 100_000 end None gives 100_000; C2 onset 100_000 end 200_000 gives 100_000; C3 gives onset.
7. `test_match_first_decidable_reference_and_window`: for the `RESP` event, a detection at 399_000 matches with delay `-1_000.0`; one at 402_000 does not match (2_000 > 1_000).
8. `test_detection_delay_rejects_misaligned_days`: `days` whose ground truth differs from the matching raises `ValueError`.
9. `test_recall_vs_false_alarm_curve_hand_computed`: 10 patient-days, 4 events; alpha 0.05 gives 2 matched, 1 false alarm; alpha 0.2 gives 3 matched, 3 false alarms; result `[(0.1, 0.5), (0.3, 0.75)]` as (false alarms per patient-day, recall).
10. `test_empirical_coverage_alert_level`: four predictions (emitted, sigma_true) = (T, -0.2), (T, +0.1), (F, -0.5), (F, +0.3) at alpha 0.2 give 0.75 (`1 - 1/4`); an emitted prediction whose `rho.alpha` differs from the `alpha` argument raises `ValueError`.
11. `test_residual_coverage_band_level`: sigma_hat `[0, 0, 0, 0]`, sigma_true `[-0.1, 0.05, 0.3, 0.6]`, q 0.35 gives 0.75.
12. `test_mean_interval_width`: `[(-0.2, 0.2), (0.0, 0.5)]` gives 0.45; empty input raises `ValueError`.
13. `test_expected_calibration_error_hand_computed`: rho `[0.95, 0.85, 0.7, 0.65]`, outcome `[T, T, F, F]`, 5 equal-width bins give 0.3875 (bin [0.8, 1.0]: |0.9 - 1.0| x 0.5; bin [0.6, 0.8): |0.675 - 0| x 0.5); `reliability_bins` returns n = 2 and observed_rate 1.0 for the top bin.
14. `test_expected_calibration_error_rho_one_in_last_bin`: rho `[1.0]`, outcome `[T]` gives 0.0 with no index error.
15. `test_attribution_confusion_fixture_m1`: cells (C1, C1) = 1 and (C2, C3) = 1, all other cells of the 3 x 4 matrix present and 0.
16. `test_attribution_metrics_with_abstention`: matched pairs (C1 to C1), (C2 to UNDETERMINED), (C3 to C3), (C1 to C2) give abstention rate 0.25, `accuracy_vs_coverage` `[(0.75, 2/3)]`, macro-F1 5/9 (C1: P 1, R 0.5, F1 2/3; C2: F1 0; C3: F1 1).
17. `test_attribution_none_for_unlabelled_detector`: detections with `label=None` give `None` for the attribution metrics.
18. `test_latency_percentiles_hand_computed`: `[1, ..., 10]` gives p50 5.5, p95 9.55, p99 9.91 (linear interpolation).
19. `test_severity_rank_agreement_kendall`: `[1, 2, 3, 4]` against `[1, 3, 2, 4]` gives 2/3; with ties `[1, 1, 2]` against `[1, 2, 3]` gives `2 / sqrt(6)` (tau-b).
20. `test_bootstrap_ci_two_days_hand_computed`: per-day values `[0.0, 1.0]`, 2_000 resamples, level 0.95, seed 0 give `(0.0, 1.0)`.
21. `test_bootstrap_ci_constant_values_degenerate`: identical per-day values give `lo == hi == value`.
22. `test_bootstrap_ci_reproducible_and_stream_independent`: same seed gives identical output; the interval does not change when the split stream is consumed first.
23. `test_paired_bootstrap_constant_positive_difference`: paired differences all +1 give `(1.0, 1.0)`.
24. `test_prop_matching_is_one_to_one` (Hypothesis): for random ground-truth and detection times, `len(pairs) + len(missed) == len(gt)` and `len(pairs) + len(duplicates) + len(false_alarms) == len(det)`.
25. `test_prop_matching_invariant_to_input_order` (Hypothesis): shuffling detections leaves the matching unchanged.
26. `test_prop_prf_and_ece_in_unit_interval` (Hypothesis): precision, recall, f1 and ECE are `nan` or in [0, 1].

`tests/eval/test_runner.py`

27. `test_split_sizes_largest_remainder`: 7 patients with `{train: 0.5, calibration: 0.25, test: 0.25}` give sizes (3, 2, 2); 10 patients with 0.6 / 0.2 / 0.2 give (6, 2, 2).
28. `test_prop_split_is_patient_disjoint_and_complete` (Hypothesis): every patient id is in exactly one split, for any seed and valid fractions.
29. `test_split_same_seed_same_split_different_seed_differs_and_manifest_order_irrelevant`.
30. `test_seed_streams_are_independent`: changing `n_bootstrap` does not change the split of the same seed.
31. `test_load_experiment_roundtrip`: a YAML with the `ExperimentConfig` keys and a `run_options` block loads to `(config, options)`; dumping the resolved config and loading it again gives equal objects.
32. `test_load_experiment_rejects_invalid`: split fractions summing to 0.9, duplicate seeds, `headline: true` with fewer than 5 seeds, unknown detector name and unknown `time_reference` each raise `ConfigError`.
33. `test_run_writes_three_files_per_seed`: for seeds `[0, 1]` the directories `outputs/smoke/0/` and `outputs/smoke/1/` each hold `config.yaml`, `metrics.json`, `git_rev.txt`.
34. `test_git_rev_txt_content`: with `git_rev=lambda: "abc123"` the file equals `"abc123\n"`; `config.yaml` records `seeds: [<seed>]`.
35. `test_metrics_json_top_level_keys`: keys are a subset of the eleven metric names plus `meta` and `analysis`, and `meta` has the keys of the README layout.
36. `test_metrics_json_layout_metric_first`: `m["per_class_prf"]["ours"]["C1"]["f1"]` has keys `value`, `ci_lo`, `ci_hi`, `ci_cluster_lo`, `ci_cluster_hi`.
37. `test_metrics_json_no_nan_and_sorted`: the text contains no `NaN` or `Infinity`; undefined values are `null`; keys are sorted.
38. `test_run_is_bit_reproducible`: two runs into two directories give byte-identical `metrics.json`.
39. `test_detector_receives_observed_day_only`: a spy detector never receives a `LatentDay`, a `BenchmarkDay` or ground truth in `run`.
40. `test_fit_receives_no_test_patient`: the patient ids passed to `fit` are disjoint from the test patients.
41. `test_cli_smoke_exit_zero_and_missing_config_nonzero`: `main(["--config", ..., "--output", ...])` returns 0 for the smoke config and non-zero for a missing file.

`tests/eval/test_ours.py`

42. `test_ours_emits_c1_alert_for_out_of_band_measurement`: on a hand-built day with one out-of-band measurement and coherent channels, `OursDetector` returns exactly one alert with `tau == TemplateId.RANGE`, `kappa == AttributedCause.C1_CLINICAL`, `verdict == VerdictState.VIOLATED` (registry values from the fixture registry).
43. `test_ours_name_and_default_components`: `name == "ours"`; default `PipelineComponents` uses `run_offline`, the split calibrator, the forecaster, identity plan and evidence transforms, and `rank_alerts`.
44. `test_pipeline_components_frozen`: assigning a field raises `FrozenInstanceError`.
45. `test_resolve_variant_delegates_to_modules`: `build_detector("ours-XYZ", ...)` calls `variant_components` of the first extension module that returns non-`None` (a stub module is injected), and an unknown name raises `ConfigError`.
46. `test_ours_updates_calibrator_after_episode_completion`: with a spy calibrator, `update(sigma_hat, sigma_true)` is called once per completed episode and never before the episode's deadline.

`tests/eval/test_runner.py` (continued)

47. `test_current_git_rev_appends_dirty_suffix`: with `subprocess.run` stubbed to return revision `abc123`, a clean status gives `abc123` and a non-empty status of tracked files gives `abc123-dirty` (no real git call in the test).
48. `test_hook_metric_contributions_merged_under_contract_names`: an analysis hook returning `HookResult(analysis={"k": 1}, metrics={"empirical_coverage": {"ours": {"shift_x": [...]}}})` appears in `metrics.json` as `analysis.k` and as `empirical_coverage.ours.shift_x`, next to the `in_distribution` entry the runner wrote.
49. `test_hook_metric_with_non_contract_name_rejected`: a hook returning a metric key that is not one of the eleven contract names raises `ConfigError`.

## Passi

1. Verify the unblock conditions and the five assumptions of the README: find the benchmark loader and `generate_benchmark` signature (WS04-T11), the harness and guard classes (WS06-T01), `run_offline`, `SplitConformal`, `AdaptiveConformal`, `Attributor`, the evidence-extraction function (WS05-T07/T08), and the convention for `end_ms` (WS04-T10). Write the findings in the completion note. Branch `ws08-t01-runner-metrics`; set `status: in_progress`.
2. Write the fixtures and tests 1 to 49. Run `pytest tests/eval -q`; confirm every test fails for the right reason. Commit `WS08-T01: add failing tests for metrics and runner`.
3. Implement `Matching`, `match_events` and `first_decidable_ms` (rules E3, one patient-day per call; `Matching.concat`, `select_days`, `restrict_subtypes` for the bootstrap and the subtype breakdown). Tests 1 to 8 and 24, 25 pass.
4. Implement the remaining metric functions and helpers (E4, E6, E7) with numpy only; `nan` for undefined ratios. Tests 9 to 19 and 26 pass. Kendall tau-b is implemented directly; use scipy only as a cross-check if it is already a dependency.
5. Implement `bootstrap_ci` and `paired_bootstrap_ci` (resampling patient-days and, for the cluster interval, patients; percentile method; `numpy.random.default_rng([seed, STREAM_BOOTSTRAP])`). Tests 20 to 23 pass.
6. Implement `ExperimentConfig` and `MatchConfig` verbatim from the contract, `RunOptions` (`alpha_grid`, `n_bootstrap`, `ci_level`, `ece_bins`, `headline`, `required_analysis`, `extra`), `ConfigError`, `load_experiment` and `split_patients`. The YAML reader is the one already used by `load_registry` (WS05-T03). `RunOptions` is a companion of the contract dataclass because `ExperimentConfig` has no field for the alpha grid or bootstrap settings; it is parsed from the `run_options` key of the same YAML and copied into `config.yaml`. Tests 27 to 32 pass.
7. Implement `PipelineComponents` (frozen; fields `calibrator_factory`, `use_forecaster`, `plan_transform`, `evidence_transform(evidence, seed)`, `verdict_runner` defaulting to `run_offline`, and `rank(alerts, records_by_instance_key)` defaulting to `rank_alerts`) and `OursDetector` (fit forecaster on train days, build calibration episodes from calibration days, run the verdict runner, attribution, ranking; no `LatentDay` access) and `build_detector`: names `B1` to `B5` map to `ralmon.baselines`, `ours` to `OursDetector`, and `ours-*` names are resolved by convention through the extension modules `ralmon.eval.ablations`, `ralmon.eval.embodied`, `ralmon.eval.shift` and `ralmon.eval.realdata`, each optionally exposing `variant_components(name) -> PipelineComponents | None`; analysis hooks are found the same way (`hooks_for(experiment_id)` in `ralmon.eval.analysis`, `ablations`, `embodied`, `shift`, `realdata`); a hook receives a `RunContext` (config, options, seed, split, fitted detectors, per-detector outputs and matchings, bootstrap generator) and returns `HookResult(analysis, metrics)`, where `metrics` may only use the eleven contract metric names and is merged into the metric-first layout (this is how the shift and real-data tasks add coverage conditions). Modules that do not exist yet are skipped. Tests 42 to 46, 48 and 49 pass.
8. Implement `run_experiment(config, options, output_root, *, git_rev=current_git_rev)`: for each seed split by patient, build and fit detectors, run each on the test days passing `ObservedDay` only, match per day, compute metrics and both bootstrap intervals, run the analysis hooks, write the three files (sorted JSON, `null` for `nan`), return the seed directories. `current_git_rev()` runs `git rev-parse HEAD` and appends `-dirty` when tracked files differ from the commit (test 47). Add `main(argv)` with `--config` and `--output`. Tests 33 to 41 and 47 pass.
9. Refactor; export names in `__init__.py`; run `ruff format`, `ruff check src tests`, `mypy src/ralmon`, the full `pytest tests/eval -q`. Commit `WS08-T01: add metrics, runner and OursDetector`; set `status: done`; paste command outputs in the completion note.

## Done when

- `pytest tests/eval -q` exits 0.
- `ruff check src tests` exits 0 and `mypy src/ralmon` exits 0.
- `python -c "from ralmon.eval import MatchConfig, match_events, per_class_prf, detection_delay_ms, false_alarms_per_patient_day, recall_vs_false_alarm_curve, empirical_coverage, mean_interval_width, expected_calibration_error, attribution_confusion, accuracy_vs_coverage, latency_percentiles, severity_rank_agreement, ExperimentConfig, run_experiment, build_detector"` exits 0.
- `python -m ralmon.eval.runner --config tests/fixtures/eval/smoke.yaml --output "$(mktemp -d)"` exits 0.
- `grep -rnE 'np\.random\.(seed|rand|randn|randint)|default_rng\(\)|time\.time|datetime\.now' src/ralmon/eval` prints nothing.
- `grep -rnE 'LatentDay|GroundTruthEvent' src/ralmon/eval/ours.py` prints nothing.

## Notes

### Hand-over from the WS01-T07 review (orchestrator, 2026-10-08)

Read `docs/formal/07-alert-tuple-mapping.md` section 1 (sigma_norm of VIOLATED and predicted alerts, CP13: kappa of a PREDICTED_VIOLATION alert is UNDETERMINED and the alert is superseded by the VIOLATED alert with the same `xi.instance_key`) and section 9 (open points OP-T07-1..17) and proposed ADR-041 before starting. Where this task text assumes a provisional kappa for predicted alerts (WS02-T04 check 8 and step 5; WS05-T07 tests 18, 20, 25) or counts a pair matched by a predicted alert (WS08 E3/E4), follow OP-T07-10 and ADR-041 and record any deviation here. `attribute` stays pure (kappa independent of `state`, test 5 scoped to the rule); the state check sits in `attribute_all`.

### Hand-over from the WS05-T03 review (orchestrator, 2026-10-09)

Step 6 assumes a YAML reader that `load_registry` already uses and that this task can reuse. WS05-T03 implements that reader as a private module (`ralmon.spec._yaml`: bounded read of a regular file, safe loader, no anchors, aliases, merge keys or duplicate keys), and `tests/test_layering.py` forbids a deep import (`ralmon.spec._yaml`) from `ralmon.eval`. Either an ADR exports a reader through `ralmon.spec` or this task keeps its own strict reader; do not import the private module.

### Hand-over from WS05-T07 (worker, 2026-10-10, review fixes)

The evidence function is `ralmon.attribution.extract_evidence(day, records, registry, *, step_ms, reorder_delay_ms, profile=None, plan=None, exclude_robot=False)`; `RuleAttributor.attribute_all` and `update` build the alerts. (1) Do not gate on EX-9 invariant I1 (a VIOLATED INT has `witness.robot_present` False) in runs where a robot status report may be dropped: the monitor reads the robot channels available until marked and the extractor reads them unavailable until the first report (H-INIT), so with the first report dropped the monitor says VIOLATED while every witness field is `None` (44 of 1000 random draws); kappa is unaffected. (2) `Alert.rho` may be `None` (ADR-059): filter `None` before ECE and coverage statistics. (3) `priority_sys` and `priority_int` are unset in registry 0.2.0: once the seven missing evidence names exist, a batch with a `sys` or `int` alert raises `UnsetParameterError`. (4) The registry lacks `evidence_margin_ms`, `evidence_grace_ms`, `hr_coherence_max_age_ms`, `hr_coherence_tolerance`, `ecg_sqi_floor`, `ppg_sqi_floor` and `ble_link_quality_floor` (OPF-6): the rule and the extractor cannot be built from the real registry.

### Hand-over from WS05-T08 (worker, 2026-10-10)

(1) Test 10 assumes that an emitted prediction's `rho.alpha` is the `alpha` of the experiment: it is the PER-TEST level `alpha_total / n_tests` (ADR-060, ADR-049 (d)); `MonitorConfig.alpha` is the total level of a patient-day, and `run_offline_detailed(...).stats.per_test_alpha` has the level that `empirical_coverage` must be given. (2) The calibrator must be fitted with `model_version=forecaster.model_version` or the monitor raises `StaleCalibratorError`. (3) `build_calibration_episodes(days, plans, config, forecaster)` returns `(episodes, n_censored)`; report `n_censored`. (4) A predicted instance has two records with the same `(instance_key, t_eval_ms)` (PENDING, PREDICTED_VIOLATION) and keeps emitting PREDICTED records until decided: key predictive alarms by instance and first PREDICTED record. See the completion note of WS05-T08.

### Hand-over from WS06-T01 (agent, 2026-10-10, review fixes)

Do not pass `history` to the proposed method (`run_offline(history=...)`) in a comparison with the baselines until ADR-061 (history input of `Detector.run`, proposed) is accepted: the baselines are run one day at a time with empty state and would be handicapped on any counter that crosses midnight. Either run the proposed method per day as well, or report both variants. `BaselineBase.fit` refuses a day object listed in both `train_days` and `calib_days` and any non-`BenchmarkDay` item (`LeakageError`).

### Hand-over (worker, 2026-10-10, from WS06-T02 review round 1)

B1 (`B1StaticThresholds`, keyword-only `timing`, optional `registry`) runs only the rules whose parameter record the care plan holds, and exposes `run_stats.rules_active`. The runner must HARD-FAIL a benchmark run of B1 unless `run_stats.rules_active == ("R1", "R2", "R3", "R4")` on every plan (the care plans of WS04-T11 must carry RANGE, HOLD and COUNT parameter records with `anchor_ms` None; the monitor's own plan helper emits only static SCHED and COUNT instances, which gives `("R3",)`). B1's score is constant 1.0 (one operating point, no AUROC or AP) and it has no RESP, SYS or INT rule, so metrics for B1 are per class. Open decisions for gab: Notes of WS06-T02.
