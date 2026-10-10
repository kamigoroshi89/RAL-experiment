---
id: WS08-T05
title: "Distribution shift and A6: split versus adaptive conformal"
workstream: WS08-experiments
owner: agent
status: blocked
depends_on: ["WS08-T02"]
critical_path: false
non_negotiable: false
estimate_pd: 2
sources: ["analisi §5.6 (A6)", "analisi §5.5", "analisi §4.4", "analisi §5.1", "analisi §2 R2 weakness 4"]
interfaces: ["02-interfaces.md#conformal-calibrator"]
review_items: ["R2-W4"]
---
## Obiettivo

Measure what happens to conformal coverage when calibration and test populations differ, and whether the adaptive calibrator recovers it (ablation A6), and check the alpha allocation that controls false predictive alarms per patient-day (R2-W4). Synthetic shift comes first and is the deliverable that closes the task: a `ShiftedPriorSource` wraps any `PriorSource` and produces shifted cohorts through the normal benchmark generator; the `shift` experiment reports empirical coverage and interval width in distribution and under shift for B4, B5 and `ours` (split calibrator); the `A6` experiment compares `ours` (split) with `ours-A6` (adaptive) on a chronological stream that changes population. The cohort shift of analisi §5.5 (calibrate on one real cohort, test on the other) needs MIMIC and eICU priors and is a guarded addendum (step 9): it runs only when WS04-T13 is done, otherwise the task records `not_run` with the blocking task and still closes.

## Contesto

- `docs/plan/workstreams/WS08-experiments/README.md` (conventions E1, E5, E6; rule H7) and `docs/source/analisi.md` §5.6 (A6: coverage degrades under shift, partial recovery with the adaptive variant), §5.5 (coverage in distribution and under shift), §4.4 (three caveats: calibration unit, marginal coverage, alpha allocation).
- `02-interfaces.md#conformal-calibrator` (rules 1 to 4; `AlphaAllocation.per_test`; `update` is adaptive only) and `02-interfaces.md#priorsource` (the wrapper must satisfy the protocol and keep one `ParamProvenance` per numeric field).
- ADR-005 (MIMIC and eICU priors added when access exists) and `docs/plan/workstreams/WS00-admin/outputs/WS00-T04.md` (`access_status:` lines).
- WS05-T06 completion note (update rule of `AdaptiveConformal`, the `AlphaAllocation` implementation) and WS04-T11 (how `generate_benchmark` receives a `PriorSource`).
- Blocked until WS08-T02 is `done`. Step 9 additionally needs WS04-T13 (not in `depends_on`; see README, section Dependencies).

## File toccati

- `src/ralmon/eval/shift.py` (create): `ShiftSpec`, `ShiftedPriorSource`, benchmark builder command (`python -m ralmon.eval.shift --build`), chronological stream, rolling coverage and recovery, `variant_components` for `ours-A6`, `hooks_for` for `shift` and `A6`.
- `experiments/` (create `shift.yaml` and `A6.yaml`; the directory is one path).
- `tests/eval/test_shift.py` (create).
- `tests/fixtures/eval/shift/` (create): synthetic exchangeable residual streams, two stub `PriorSource` implementations, a stub allocation.

## Test

Write these first. Values are fixtures with dummy parameters, not clinical claims.

`tests/eval/test_shift.py`

1. `test_shifted_prior_source_scales_declared_fields_only`: with a dummy base `cuff_error_sd_mmhg` of 3.0 and factor 2.0 the shifted value is 6.0; every other field of `PatientParams`, `AdherenceParams` and `DeviceErrorModel` is unchanged.
2. `test_shift_factor_one_is_identity`: all factors 1.0 give identical `PatientParams`, `AdherenceParams` and `DeviceErrorModel` for the same generator seed and patient index.
3. `test_shifted_provenance_marks_synthetic_shift`: each shifted field has a `ParamProvenance` whose `source_ref` contains "synthetic shift" and whose `verified_by` is `None`; unshifted fields keep the base provenance.
4. `test_shifted_probability_clipped_and_logged`: `p_omission` 0.6 with factor 2.0 is clipped to 1.0 and the clipping appears in `analysis.shift_levels`.
5. `test_shifted_source_has_priorsource_methods`: `name`, `sample_patient`, `adherence`, `device_errors`, `provenance` exist and return the contract types (the structural check is `mypy` in Done when).
6. `test_shifted_patients_disjoint_from_split`: no patient id of a shifted cohort appears in the train or calibration patients of any seed.
7. `test_stream_chronological_order`: episodes come out ordered by `(day_index, completion time, patient_id)` for any input order.
8. `test_stream_change_point_recorded`: 6 in-distribution episodes followed by 4 shifted ones give `change_point == 6`.
9. `test_adaptive_update_once_per_completed_episode_in_order`: a spy calibrator receives `update(sigma_hat, sigma_true)` once per episode in stream order, each after the episode's deadline.
10. `test_split_update_is_noop`: `SplitConformal.update` leaves `quantile(alpha)` unchanged after 100 updates.
11. `test_zero_shift_control_coverage_within_binomial_tolerance`: exchangeable Gaussian residuals (seed 0), 2_000 calibration and 2_000 test episodes, alpha 0.1: band-level coverage differs from 0.9 by at most 0.03 (three standard deviations of test plus calibration sampling error, 3 x sqrt(2) x sqrt(0.9 x 0.1 / 2000) = 0.0285).
12. `test_shift_degrades_split_coverage_on_synthetic_stream`: with the same sizes, test residual scale twice the calibration scale gives band-level coverage of the split calibrator in [0.70, 0.78] (hand-computed: the 90 percent quantile is 1.2816 calibration standard deviations, so coverage is Phi(1.2816 / 2) = Phi(0.6408) = 0.739).
13. `test_adaptive_final_window_coverage_not_below_split`: on the same stream the adaptive coverage over the last 500 episodes is at least the split coverage over the same window (this checks the plumbing with the update rule of WS05-T06; the convergence property is tested in WS05-T06).
14. `test_rolling_coverage_hand_computed`: hit flags `[1, 1, 0, 1]` with window 2 give `[1.0, 0.5, 0.5]`.
15. `test_time_to_recovery_hand_computed`: rolling coverage `[0.6, 0.7, 0.85, 0.9]`, nominal 0.9, tolerance 0.1 gives recovery index 2; a series that never gets within tolerance gives `null`.
16. `test_alpha_allocation_applied_per_patient_day`: with a stub allocation `per_test = alpha_total / n_tests`, alpha_total 0.1 and 5 instances in a patient-day, the calibrator receives 0.02 for each instance (and 0.1 in the naive setting).
17. `test_alpha_allocation_report_counts_per_patient_day`: fixture with 3 false predictive alarms in 6 patient-days (naive) and 1 in 6 (allocated) reports 0.5 and 1/6.
18. `test_coverage_null_for_detector_without_predictions`: a detector that exposes no per-episode predictions has `null` coverage and width and the analysis says so (B4 or B5 if WS06 does not expose them).
19. `test_cohort_shift_not_run_without_mimic`: when `cohort_shift.enabled` is false or the MIMIC prior source cannot be imported, `analysis.cohort_shift` equals `{"status": "not_run", "blocked_on": "WS04-T13"}` and nothing raises.
20. `test_cohort_shift_with_stub_sources`: with stub sources `cohort_a` and `cohort_b`, calibrating on `cohort_a` and testing on `cohort_b` yields the condition `cohort_a_to_cohort_b` under `empirical_coverage`.
21. `test_shift_and_a6_yaml_load`: `experiments/shift.yaml` has detectors `["B4", "B5", "ours"]`; `experiments/A6.yaml` has `["ours", "ours-A6"]`; data settings equal those of `main.yaml`; at least three shift levels, one of them the zero-shift control (all factors 1.0); `headline` is true; `required_analysis` is non-empty.
22. `test_variant_components_names_a6`: components for `ours-A6` (adaptive calibrator), `None` for every other name.

## Passi

1. Verify the unblock condition. Read how `generate_benchmark` receives a `PriorSource`, the `AdaptiveConformal` update rule and `AlphaAllocation` implementation, and whether B4 and B5 expose per-episode predictions. Read `WS00-T04.md` and the status of WS04-T13 to decide whether step 9 can run. Branch `ws08-t05-shift-a6`; set `status: in_progress`.
2. Write the fixtures and tests 1 to 22; run `pytest tests/eval/test_shift.py -q`; confirm they fail. Commit `WS08-T05: add failing shift tests`.
3. Implement `ShiftSpec` (per field: multiplicative `factor` or additive `offset`, clipping range for probabilities) and `ShiftedPriorSource` (wraps any `PriorSource`; provenance rule of test 3). Tests 1 to 6 pass.
4. Implement the chronological stream, `change_point`, rolling coverage and time to recovery. Tests 7, 8, 14, 15 pass.
5. Implement `ours-A6` (adaptive calibrator through `PipelineComponents`, `update` after each completed episode) and the checks of tests 9 to 13.
6. Implement the alpha-allocation analysis (tests 16, 17) and the null-coverage rule (test 18).
7. Write `shift.yaml` and `A6.yaml` with the data settings of `main.yaml`. Shift levels: at least three, one zero-shift control; magnitudes are declared in the file as factors or offsets on the fields of the contract (baseline systolic pressure, autoregressive noise, `cuff_error_sd_mmhg`, `p_omission`), described as stress levels and not clinical claims, and chosen before any result is read (rule E9). Build the shifted benchmarks: `python -m ralmon.eval.shift --build experiments/shift.yaml`. Test 21 passes.
8. Run `python -m ralmon.eval.runner --config experiments/shift.yaml --output outputs` and the same for `A6.yaml`; run `python -m ralmon.eval.analysis --check outputs/shift outputs/A6`.
9. Guarded addendum. If WS04-T13 is `done` and `WS00-T04.md` shows `access_status: granted` for both datasets, set `run_options.extra.cohort_shift.enabled: true` in `shift.yaml`, calibrate on the MIMIC-prior cohort and test on the eICU-variant cohort (both directions), and re-run `shift`; the data stay under `data/raw/` and only aggregates are written. Otherwise leave it disabled: `analysis.cohort_shift` then records `{"status": "not_run", "blocked_on": "WS04-T13"}`, the completion note says "shift test is synthetic only", and WS12 states the same in the paper (rule H6). Do not fabricate a second cohort from the same prior source.
10. Read the results under rule H7 and write them in the completion note: coverage of B4, B5 and `ours` in distribution and at each shift level against nominal; interval width; recovery of the adaptive calibrator (or its absence, reported as measured); false predictive alarms per patient-day with and without allocation. Run the Done when commands, commit `WS08-T05: add shift test and A6`, set `status: done`.

## Done when

- `pytest tests/eval -q` exits 0, `ruff check src tests` exits 0, `mypy src/ralmon` exits 0.
- `for id in shift A6; do n=$(ls outputs/$id/*/metrics.json | wc -l); test "$n" -ge 5 || echo "$id has $n seeds"; done` prints nothing.
- `python -m ralmon.eval.analysis --check outputs/shift outputs/A6` exits 0.
- `grep -A2 '"cohort_shift"' outputs/shift/0/metrics.json` shows either `"status": "not_run"` with `"blocked_on": "WS04-T13"` or a completed result with the two conditions `<a>_to_<b>` and `<b>_to_<a>` named after the two prior sources.

## Notes

### Hand-over (worker, 2026-10-10, from WS06-T06)

Test 18 assumes that B4 or B5 may expose no per-episode predictions. `B5ConformalSTL` exposes them: after `fit`, `calibration_episodes` (raw robustness, not normalised; `CalibrationEpisode.sigma_hat` and `sigma_true` hold `rho_hat` and the measured raw robustness of the instance on the observed day) and `n_calibration_episodes`, `n_censored`; after `run`, `predictions`, a tuple of `B5Prediction(keys, template, t_ms, sigma_hat, quantile, emitted, sigma_true)` with `sigma_true` the measured raw robustness of the same group (`None` while undecided or not finite). The error event of the contract (alert emitted and `sigma_true >= 0`) can be counted from them; widths are in raw units of the template, so a comparison with `ours` needs a per-template reading (variant `B5-per-template`) or the band margin as the common scale. The level is `alpha` itself, with no allocation over the instances of a day (deviation D10 in `notes/B5-deviations.md`), which matters for the false predictive alarms per patient-day that this task also reports.
