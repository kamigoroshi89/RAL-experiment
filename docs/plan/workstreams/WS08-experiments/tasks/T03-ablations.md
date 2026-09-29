---
id: WS08-T03
title: "Ablations A1, A2, A3, A5, A7"
workstream: WS08-experiments
owner: agent
status: blocked
depends_on: ["WS08-T02"]
critical_path: true
non_negotiable: false
estimate_pd: 3
sources: ["analisi §5.6", "analisi §4.2", "analisi §4.3", "analisi §4.4", "analisi §4.7", "analisi §2 R2 weaknesses 1 and 9"]
interfaces: ["02-interfaces.md#experiment-config-and-outputs"]
review_items: ["R2-W1", "R2-W9"]
---
## Obiettivo

Run the five ablations that change one component of the proposed method at a time, each as a paired comparison with `ours` on identical days, splits and seeds: A1 (conformal calibrator replaced by the point forecast), A2 (no forecaster: measured three-valued verdicts only), A3 (no normalisation of sigma), A5 (no RESP and HOLD templates) and A7 (past-time versus delayed future-time formulation). Also produce the forecaster evaluation that closes R2-W1 and R2-W9: per-target error and interval width, including the blood-pressure row that is expected to be uninformative (rule H1), and the noise tolerance of the forecaster measured on days with injected signal noise. Concrete output: `ablations.py`, `future_time.py`, `experiments/A1.yaml`, `A2.yaml`, `A3.yaml`, `A5.yaml`, `A7.yaml`, and `outputs/A<k>/<seed>/...` for at least five seeds.

## Contesto

- `docs/plan/workstreams/WS08-experiments/README.md` (experiment ids, conventions E1 to E10, rules H1 and H4) and `docs/source/analisi.md` §5.6 (hypothesis per ablation).
- `02-interfaces.md#conformal-calibrator`, `#verdict` (semantics 1 to 3: the forecast never produces VIOLATED or SATISFIED) and `#forecaster`; ADR-007, ADR-008, ADR-009.
- WS01 equivalence document between the past-time and future-time forms of each template (required by ADR-007) and the registry priorities and scales (`configs/registry/hypertension.yaml`).
- The `PipelineComponents` seam and the extension-module convention of WS08-T01 (`variant_components`, `hooks_for`).
- Blocked until WS08-T02 is `done` (`experiments/main.yaml` supplies the data settings).

## File toccati

- `src/ralmon/eval/ablations.py` (create): `PointForecastCalibrator`, `variant_components` for `ours-A1`, `ours-A2`, `ours-A3`, `ours-A3-prio`, `ours-A5`, `ours-A7`, and `hooks_for` for the five experiment ids.
- `src/ralmon/eval/future_time.py` (create): `evaluate_future_time`, `compare_verdicts`, look-ahead buffer accounting.
- `tests/eval/test_ablations.py` (create).
- `tests/eval/test_future_time.py` (create).
- `experiments/` (create `A1.yaml`, `A2.yaml`, `A3.yaml`, `A5.yaml`, `A7.yaml`; the directory is one path).
- `tests/fixtures/eval/ablations/` (create): hand-built days, a test registry with priorities and scales marked "illustrative, unverified".

## Test

Write these first. All numbers are test fixtures (scales, priorities, windows are test-local), not results and not clinical claims.

`tests/eval/test_ablations.py`

1. `test_variant_components_names`: `variant_components` returns components for `ours-A1`, `ours-A2`, `ours-A3`, `ours-A3-prio`, `ours-A5`, `ours-A7` and `None` for `ours-A4`, `ours-A6` and `foo`.
2. `test_point_forecast_calibrator_quantile_zero`: `quantile(alpha) == 0.0` for any alpha; `update` and `fit` do nothing.
3. `test_point_forecast_emits_iff_sigma_hat_negative`: sigma_hat -0.1 emits, +0.1 does not, exactly 0.0 does not.
4. `test_point_forecast_rho_is_one_without_guarantee`: an emitted prediction has `rho.value == 1.0`, `kind == RhoKind.PREDICTED`, `alpha is None` and a `guarantee` text that states there is none (a point forecast carries no confidence statement; this is the fixed rule of the plan, changing it needs an ADR).
5. `test_a1_emits_superset_when_quantile_positive`: with a conformal quantile fixed at +0.2 and sigma_hat in `[-0.3, -0.1, 0.1]`, the "likely" conformal rule emits for one (-0.3) and the point forecast for two (-0.3, -0.1).
6. `test_a1_ece_of_constant_rho`: rho `[1, 1, 1, 1]` with outcomes `[T, F, F, T]` gives ECE 0.5.
7. `test_a1_coverage_metrics_are_null`: `empirical_coverage` and `mean_interval_width` are `null` for `ours-A1`; the analysis key `false_predictive_alarms_per_patient_day` counts episodes with `emitted and sigma_true >= 0` over patient-days (3 such episodes in 6 patient-days gives 0.5).
8. `test_a2_definitive_verdicts_identical_to_full`: on the fixture day the multiset of `(instance_key, state, decided_at_ms, sigma_interval)` for states VIOLATED and SATISFIED is equal for `ours` and `ours-A2`.
9. `test_a2_no_predicted_violation_and_no_negative_delay`: no `VerdictState.PREDICTED_VIOLATION` appears and every delay of `ours-A2` is at least 0.
10. `test_a3_raw_order_ignores_units_and_priority`: alerts A (priority 1, raw -1 dose, scale 5), B (priority 2, raw -1_800_000 ms, scale 2_000_000), C (priority 2, raw -1_000_000 ms, scale 2_000_000) have sigma-tilde -0.2, -0.9, -0.5; the full order is A, B, C; `ours-A3` orders B, C, A; `ours-A3-prio` orders A, B, C.
11. `test_priority_inversion_rate_hand_computed`: for the order B, C, A against the reference A, B, C the rate is 1.0 (2 of 2 cross-priority pairs inverted); for the full order it is 0.0.
12. `test_a3_rank_agreement_hand_computed`: Kendall tau-b between reference ranks (A=1, B=2, C=3) and ablated ranks (B=1, C=2, A=3) is -1/3; `analysis.a3_reference` reads `"registry_lexicographic"` and `severity_rank_agreement` against clinician rankings is `null` unless WS11 rankings are supplied.
13. `test_a3_verdict_signs_unchanged`: `ours` and `ours-A3` emit the same set of `(instance_key, state)`; only the order differs.
14. `test_a5_plan_transform_drops_resp_and_hold_only`: instances of `TemplateId.RESP` and `TemplateId.HOLD` are removed, all others unchanged, `plan_version` unchanged and `signature` set to `None` (the modified plan is evaluated offline in trusted mode; the change is stated in the run's `analysis`).
15. `test_a5_recall_drops_on_resp_and_hold_events_only`: fixture with 2 RESP events, 1 HOLD event and 2 RANGE events (by `template_id`): recall of the RESP or HOLD group is 1.0 for `ours` and 0.0 for `ours-A5`; the RANGE group is 1.0 for both.
16. `test_a5_collateral_effects_listed`: every ground-truth subtype outside the RESP or HOLD group appears in `analysis.collateral_effects` with its recall difference, and a nonzero difference outside the group is flagged.
17. `test_forecast_informativeness_straddle_fraction_per_target`: blood-pressure intervals `[(-1.0, 1.0), (-0.8, 0.9)]` give straddle fraction 1.0 and mean width 1.85; heart-rate intervals `[(-0.3, -0.1), (-0.2, 0.1)]` give 0.5 and 0.25.
18. `test_forecast_informativeness_always_lists_blood_pressure`: rows are keyed by `SignalId` value (`bp`, `hr_ecg`, `hr_pulse`, `spo2`); with no blood-pressure forecast episode the `bp` row still exists with `n_episodes: 0` and `null` values (rule H1).
19. `test_forecast_noise_strata`: absolute errors `[0.1, 0.3]` on clean days and `[0.4, 0.6]` on days with injected signal noise give mean errors 0.2 and 0.5 in strata `clean` and `noise_injected`.
20. `test_ablation_configs_share_data_settings_with_main`: for each of the five YAMLs, `benchmark_manifest`, `seeds`, `split`, `match`, `alpha` and `monitor` equal those of `experiments/main.yaml`; `detectors` equals `["ours", "ours-<id>"]` (A3 adds `ours-A3-prio`); `headline` is true; `required_analysis` is non-empty.

`tests/eval/test_future_time.py`

21. `test_future_time_matches_past_time_on_fixture`: on a hand-built day with tick 0 measured inside the window and tick 3_600_000 not measured (test window W = 1_800_000 ms, step 60_000 ms), both formulations give `SATISFIED` and `VIOLATED` for the two SCHED instances and `0 <= decided_past - decided_future <= step_ms` (future decides at anchor + W = 1_800_000 and 5_400_000; the difference is the alignment `O[W, W+T_s]`, ADR-007).
22. `test_future_time_look_ahead_buffer`: peak look-ahead buffer for SCHED is 1_800_000 ms, that is 30 grid steps.
23. `test_compare_verdicts_lists_discrepancies`: with 4 instances and one planted mismatch (past VIOLATED, future SATISFIED) `equivalence_rate` is 0.75 and `discrepancies` holds that instance key with both states.
24. `test_templates_without_future_form_not_compared`: a template with no documented future-time form is listed in `not_compared` and never given an invented formula.
25. `test_logical_latency_percentiles`: latencies `[0, 60_000, 60_000, 120_000]` give p50 60_000, p95 111_000, p99 118_200 (trace time only; no wall clock is read).

## Passi

1. Verify the unblock condition. Read the WS01 equivalence document and record, per template, whether a future-time form exists. Read `experiments/main.yaml`. Branch `ws08-t03-ablations`; set `status: in_progress`.
2. Write the fixtures and tests 1 to 25. Run `pytest tests/eval/test_ablations.py tests/eval/test_future_time.py -q`; confirm they fail. Commit `WS08-T03: add failing ablation tests`.
3. Implement `PointForecastCalibrator` (structural `ConformalCalibrator`, `mode = "split"` by convention, documented) and the A1 and A2 components (A2: `MonitorConfig.predictive = False`, no calibrator, no forecaster). Tests 1 to 9 pass.
4. Implement the A3 and A5 components (A3 supplies the `rank` component with raw sigma taken from the verdict record; A5 supplies `plan_transform`). Tests 10 to 16 pass.
5. Implement `future_time.py` directly from the future-time forms documented by WS01, for the templates that have one; no formula is written from memory, and the look-ahead buffer is counted in grid steps. Supply the A7 `verdict_runner`. Tests 21 to 25 pass.
6. Implement `hooks_for`: `forecast_informativeness` (A1, A2), `false_predictive_alarms_per_patient_day` and `rho_reliability` (A1), `definitive_verdicts_identical` (A2), `priority_inversions` and `a3_reference` (A3), `collateral_effects` (A5), `verdict_equivalence`, `logical_latency` and `not_compared` (A7); each key is added to the `required_analysis` of its YAML. Tests 17 to 19 pass.
7. Write the five YAML files by copying the data settings of `main.yaml` (test 20). Run each: `for id in A1 A2 A3 A5 A7; do python -m ralmon.eval.runner --config experiments/$id.yaml --output outputs || exit 1; done`, then `python -m ralmon.eval.analysis --check outputs/A1 outputs/A2 outputs/A3 outputs/A5 outputs/A7`.
8. Read the results against the hypotheses and rules H1 and H4 and write them in the completion note: A1 (predictive false alarms per patient-day and ECE, ours versus point forecast, with paired intervals); A2 (definitive verdicts identical, early-warning lead-time distribution that A2 lacks); A3 (inversion rate and agreement, stated as a consistency measure against the registry order, not an independent validation); A5 (recall drop on the RESP or HOLD group and any collateral effect); A7 (equivalence rate, every discrepancy explained, latency and buffer differences); the forecaster table with the blood-pressure row and the noise strata. A hypothesis that fails is reported as it is.
9. Run the Done when commands, commit `WS08-T03: add ablations A1 A2 A3 A5 A7`, set `status: done`.

## Done when

- `pytest tests/eval -q` exits 0, `ruff check src tests` exits 0, `mypy src/ralmon` exits 0.
- `for id in A1 A2 A3 A5 A7; do n=$(ls outputs/$id/*/metrics.json | wc -l); test "$n" -ge 5 || echo "$id has $n seeds"; done` prints nothing.
- `python -m ralmon.eval.analysis --check outputs/A1 outputs/A2 outputs/A3 outputs/A5 outputs/A7` exits 0.
- `grep -c '"bp"' outputs/A1/0/metrics.json` prints at least 1 (the H1 blood-pressure row is present).
