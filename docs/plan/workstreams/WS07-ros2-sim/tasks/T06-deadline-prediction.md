---
id: WS07-T06
title: "Predictive monitoring of care-delivery deadlines"
workstream: WS07-ros2-sim
owner: agent
status: blocked
depends_on: ["WS07-T04", "WS05-T06", "WS05-T05", "WS08-T01", "WS04-T11"]
critical_path: false
non_negotiable: false
estimate_pd: 2.5
sources: ["analisi §4.3", "analisi §5.2", "analisi §10 (3)"]
interfaces: ["02-interfaces.md#forecaster", "02-interfaces.md#conformal-calibrator"]
review_items: ["R2-W5"]
---
## Obiettivo

Deliver the genuinely robotic use of prediction (analisi §4.3): conformal predictive monitoring of care-delivery deadlines. For each MEASURE obligation of the simulated robot (from SCHED and RESP), the pipeline forecasts at declared lead times before the window closes whether the robot will be late, from the task queue and navigation state published by WS07-T04; the conformal calibrator (WS05-T06) is calibrated on patient episodes split by patient; a PREDICTED-VIOLATION early warning is emitted only while the obligation is PENDING, and the definitive verdict comes only from the measured completion (ADR-008). Output: a ROS recorder node, a pure pipeline (episodes, split, calibration, scoring, bootstrap), a run driver and `outputs/ws07-deadline/<seed>/{config.yaml, metrics.json, git_rev.txt}` with, per lead time and alpha, the episode counts, the false predictive alarm rate, the recall of eventual violations, the lead-time distribution and whether an alert is possible at all. This closes R2-W5: prediction is moved from five-a-day blood pressure to a target with dense state, and the result is reported even when it is negative. The evaluation replays the ROS-recorded runs through the same causal monitor code as the online path; it does not require an online predictive RSM.

## Contesto

Blocked until WS07-T04 (features and outcome events) and WS05-T06 (conformal calibrator) are done. Undeclared precondition for the real runs of step 6: a benchmark version with enough patients (built by WS04-T11; no dependency of this task reaches it). The pure pipeline and its tests need only fixtures; if no benchmark version exists when step 6 starts, stop and report instead of inventing patients.

- `docs/source/analisi.md` §4.3 (last paragraphs: forecast that the robot arrives late to the window; the candidate targets), §4.4 (definition of ρ for predicted violations, marginal guarantee, calibration unit), §5.2, §10 objection 3.
- `docs/plan/02-interfaces.md#forecaster`, `#conformal-calibrator` (rules 1 to 4: episode is the unit, marginal coverage, one-sided score, recalibration) and `#verdict` (state transitions; a warning followed by SATISFIED is a false predictive alarm).
- `docs/plan/workstreams/WS07-ros2-sim/README.md` and `tasks/T04-robot-task-layer.md` (`DEADLINE_FEATURES`, `ROBOT_TASK` payload keys, release at window start).
- The ADR of WS05-T05 (model class, input features and horizon of the deadline forecaster) and the WS05-T06 and WS05-T08 code (`SplitConformal`, `run_offline`, any helper that builds `CalibrationEpisode` objects).

## File toccati

- `ros2/ralmon_sim/ralmon_sim/deadline_prediction.py` (create): pure pipeline and CLI `main`.
- `ros2/ralmon_sim/ralmon_sim/deadline_logger.py` (create): recorder node `main`.
- `ros2/ralmon_sim/config/experiments/ws07_deadline.yaml` (create): seeds, run list (scenario files and slots), lead times, alpha grid, patient split, bootstrap size, variant; required keys, no defaults.
- `ros2/ralmon_sim/launch/deadline_run.launch.py` (create): scenario launch plus the recorder.
- `ros2/ralmon_sim/test/test_deadline_prediction.py` (create): pure tests with fake monitor, forecaster and calibrator, and `ros` tests.

## Test

Write these first. Fixtures use fakes that implement the Protocols of `#forecaster` and `#conformal-calibrator`; numbers are test-only.

- `test_split_by_patient_is_disjoint_complete_and_deterministic`: every patient is in exactly one of train, calibration, test; the same seed gives the same split; a patient with several episodes never spans two splits.
- `test_split_sizes_hand_computed`: 10 patients with fractions (0.5, 0.2, 0.3) give 5, 2 and 3.
- `test_episode_dropped_when_completion_unobserved`: an obligation whose measurement never arrives before the run ends is not labelled; it is counted in `n_dropped_unobserved`.
- `test_definitive_label_uses_only_measured_completion`: a fake forecaster that always predicts lateness cannot change `sigma_true`; the label depends only on the recorded measurement time and the window.
- `test_lead_time_definition`: verdict sequence PENDING at 1000, PREDICTED_VIOLATION at 2000, VIOLATED with `decided_at_ms` 5000 gives lead time 3000.
- `test_warning_then_satisfied_counts_as_false_predictive_alarm`.
- `test_false_alarm_rate_and_recall_hand_computed`: ten test episodes with emitted flags [T, T, T, F, F, F, F, F, F, F] and `sigma_true` [-0.5, -0.2, 0.3, -0.4, 0.1, 0.2, 0.5, 0.6, 0.7, 0.8] give false predictive alarm rate 0.1 (emitted and `sigma_true >= 0`: one of ten) and recall 2/3 (two of the three violated episodes were warned).
- `test_recall_is_null_when_no_violation_in_test_set`: the value is `null` in the report, never 0.
- `test_alert_possible_false_when_quantile_at_least_one`: quantile 1.0 gives `alert_possible` false, 0.4 gives true (a warning needs `sigma_hat + q < 0` and `sigma_hat >= -1`).
- `test_lead_time_percentiles_hand_computed`: lead times [10, 20, 30, 40, 50] give p50 30.0, p95 48.0, p99 49.6 (linear interpolation, method recorded in the report).
- `test_bootstrap_is_seeded_and_resamples_patients`: constant data gives a degenerate interval equal to the point estimate; the same seed gives the same interval; seeds 0 and 1 differ on non-constant data.
- `test_sigma_convention_matches_monitor_on_toy_day`: on the SCHED golden cases of WS01-T02 (`docs/formal/golden/templates.yaml`, for example the case with tick 09:00, window 30 minutes and a measurement at 09:05, hand-computed there as +1_500_000 ms raw and 0.8333 normalised) the local `sigma_true` (or the WS05 helper's) equals the `sigma_norm_interval` returned by `ralmon.monitor.run_offline`; this pins the convention to the monitor and the golden file, not to a formula copied here.
- `test_config_requires_lead_times_alpha_grid_split_and_seeds`: removing any raises `DeadlineConfigError`.
- `test_outputs_layout_and_required_keys`: the output directory has `config.yaml`, `metrics.json`, `git_rev.txt` (git provider injectable); `metrics.json` has `n_cal`, `n_test`, `n_dropped_unobserved`, `alpha_grid`, `lead_times_ms` and per (lead time, alpha) the keys `quantile`, `alert_possible`, `emitted_rate`, `false_predictive_alarm_rate`, `violation_recall`, `lead_time_ms` (with `p50`, `p95`, `p99`) and the bootstrap intervals.
- `test_local_coverage_matches_ralmon_eval_if_available`: when `ralmon.eval.empirical_coverage` is importable, the local rate agrees with it on the hand-computed fixture; otherwise the test is skipped (WS08-T01 is not a dependency of this task).
- `ros` marker: `test_logger_records_task_events_and_state_samples` (synthetic publishers; JSONL lines carry `t_ward_ms`, `topic` and the record); `test_logger_flushes_on_shutdown`; `test_short_run_produces_at_least_one_episode` (one short scenario through `deadline_run.launch.py`).

## Passi

1. Read the WS05-T05 ADR (model class, input features, horizon, the signal it forecasts), the calibrator and `run_offline` code, and the WS07-T04 payload keys. Decide whether a public helper builds `CalibrationEpisode` objects from a forecaster and days. If it does, use it; if the public API has none (the Package public API table lists none), build the episodes here (forecast the completion of the pending obligation at the lead time, convert to a normalised time robustness of the SCHED or RESP instance, take `sigma_true` from the measured completion) and report the gap.
2. Write the tests; run `pytest ros2/ralmon_sim/test/test_deadline_prediction.py -q` and watch them fail.
3. Implement `deadline_prediction.py`: log reader; reconstruction of an `ObservedDay` and the derived `CarePlan` per patient and run from the recorded state samples, `measurement` events and the plan; patient split with a seeded generator; one `SplitConformal` calibrator per lead time fitted on calibration episodes (unit: obligation episode; split by patient); scoring per alpha (definitions of the tests; false predictive alarm rate is the empirical counterpart of "alert emitted and `sigma >= 0`", the quantity bounded by alpha in Proposition 1 under exchangeability); seeded bootstrap over patients; percentiles with `numpy.percentile` linear interpolation, method named in the report; output writer in the `01-conventions.md` section 9 layout. Coverage is marginal over the population and the report says so.
4. Implement `deadline_logger.py` (subscribe to `/ralmon_sim/robot/state_samples`, `/ralmon/events`, `/ralmon/samples`, `/ralmon/care_plan`; write one JSON line per message with the ward time) and `deadline_run.launch.py`.
5. Write `ws07_deadline.yaml`. Alpha grid, lead times, split fractions and bootstrap size are declared run parameters; do not choose them to obtain alerts.
6. Collect runs: for each seed run the scenarios listed in the config with different patient slots (the number of distinct patients per split is reported; no minimum is asserted here, WS05-T06 documents what the calibrator does with too few episodes and the run must surface that message). Run the pipeline; keep the raw logs in `outputs/ws07-deadline/<seed>/runs/`.
7. Inspect the result without tuning it: if `alert_possible` is false for every setting, or the false predictive alarm rate exceeds alpha beyond the bootstrap interval, write that in the completion note as a finding for WS08 and the paper (limitations), together with the compression factor used. Do not change features, lead times or alpha after seeing the test split.
8. Run `ruff check ros2/ralmon_sim`, `ruff format ros2/ralmon_sim`; commit `WS07-T06: deadline predictive monitoring`.

## Done when

- `pytest ros2/ralmon_sim/test/test_deadline_prediction.py -q -m "not ros"` exits 0.
- In the sourced ROS 2 environment: `pytest ros2/ralmon_sim/test/test_deadline_prediction.py -q -m ros` exits 0.
- `ruff check ros2/ralmon_sim` and `ruff format --check ros2/ralmon_sim` exit 0.
- `PYTHONPATH=ros2/ralmon_sim python -m ralmon_sim.deadline_prediction --config ros2/ralmon_sim/config/experiments/ws07_deadline.yaml --seed 0` exits 0 after the runs of step 6 and writes `outputs/ws07-deadline/0/metrics.json`.
- `python -c "import json; m = json.load(open('outputs/ws07-deadline/0/metrics.json')); assert {'n_cal', 'n_test', 'n_dropped_unobserved', 'alpha_grid', 'lead_times_ms'} <= set(m)"` exits 0.
- `test -f outputs/ws07-deadline/0/config.yaml && test -f outputs/ws07-deadline/0/git_rev.txt` exits 0, and `grep -nE 'TO''DO|TB''D|lo''rem|[?][?][?]' ros2/ralmon_sim/config/experiments/ws07_deadline.yaml` prints nothing.
