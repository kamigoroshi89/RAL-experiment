---
id: WS05-T08
title: "Predictive integration and run_offline end to end"
workstream: WS05-monitor
owner: agent
status: blocked
depends_on: ["WS05-T05", "WS05-T06", "WS05-T07", "WS01-T08"]
critical_path: true
non_negotiable: false
estimate_pd: 2
sources: ["analisi §4.7 (3)"]
interfaces: ["02-interfaces.md#monitor", "02-interfaces.md#verdict", "02-interfaces.md#detector"]
review_items: []
---
## Obiettivo

Connect the forecaster and the conformal calibrator to the monitor so that a pending obligation can raise `PREDICTED_VIOLATION`, complete `run_offline`, and prove the whole chain end to end. The predictive step acts only while a verdict is PENDING and never produces a definitive verdict (ADR-008); it makes exactly one prediction per pending instance, at its activation, so that the calibration unit stays the patient episode and the alpha allocation per patient-day is a union bound over the instances of the plan. Concrete output: predictive mode of `StreamingMonitor`, `build_calibration_episodes`, `StaleCalibratorError`, and an end-to-end test from an `ObservedTrace` to attributed alerts that reproduces the hand-worked patient-day of WS01. The adapter that makes this pipeline a `Detector` named `ours` is built by WS08-T01 from these public pieces.

## Contesto

Blocked until WS05-T05, WS05-T06 and WS05-T07 are `done`. Undeclared precondition, reported to the plan lead: the hand-worked patient-day of WS01-T08 is not in `depends_on`; write every other test, keep `status: in_progress` until it exists, and do not mark the task `done` with that test skipped.

- `docs/formal/05-three-valued-semantics.md` (predictive completion in the PENDING state, state diagram).
- `docs/formal/06-rho-proposition1.md` (rho of a predicted violation, the two variants).
- `docs/formal/09-worked-patient-day.md` (the hand-worked day used as golden in the end-to-end test).
- `02-interfaces.md#monitor` (`run_offline`, `MonitorConfig`; the verdict and detector contracts are quoted where used).
- `docs/source/analisi.md` §4.7 (step 3: predictive completion replaces the physiological bounds by the conformal region; the definitive verdict still comes from step 2).

## File toccati

- `src/ralmon/monitor/` (modify: create `predictive.py`; extend `core.py` and `offline.py`; add `build_calibration_episodes` and `StaleCalibratorError`; placeholders removed from `_stubs.py`)
- `tests/monitor/` (create: `test_predictive.py`, `test_calibration_episodes.py`; delete the temporary test `test_config_rejects_predictive_until_ws05_t08` of WS05-T04)
- `tests/test_end_to_end.py` (create: the cross-package pipeline tests)
- `tests/fixtures/monitor/` (modify: add the worked-day copy and the hand scenarios below)
- `docs/plan/03-decisions.md` (modify: append one ADR, status `proposed`, confirmation tag)
- `docs/plan/02-interfaces.md` (modify: `#monitor` semantics of `alpha` and the prediction rule, version bump)

## Test

Write first; each fails before the implementation. Stub forecasters return fixed paths; the calibrator is `SplitConformal` fitted on the nine scores of the WS05-T06 fixture (`R = [-0.2, -0.1, 0.0, 0.1, 0.1, 0.2, 0.3, 0.4, 0.6]`). F0, `step_ms = 60_000`. Time labels convert with `t_ms = (60*hh + mm) * 60000`.

Predictive semantics (`test_predictive.py`)

1. `test_predictive_false_matches_measured_only_run`: with `predictive=False` the records equal those of the measured-only monitor of WS05-T04 exactly (ablation A2: same definitive verdicts, no early warning).
2. `test_predictive_true_requires_calibrator_forecaster_and_alpha`: a missing calibrator, forecaster or `config.alpha` raises `MonitorConfigError` at construction.
3. `test_prediction_only_while_pending_and_once_per_instance`: an instance gets at most one `PREDICTED_VIOLATION` record, at its activation step, and none after a definitive record; the activation step emits `PENDING` first and `PREDICTED_VIOLATION` second (same `t_eval_ms`) so every per-instance sequence follows the allowed transitions of `#verdict`.
4. `test_forecast_never_produces_definitive_verdict` (Hypothesis): for arbitrary forecaster paths, including extreme ones, the definitive record of every instance (state and `decided_at_ms`) equals the one of the run with `predictive=False`.
5. `test_scheduled_arrival_predicted_late_then_violated`: `sched` tick 09:00 (32_400_000), window 1_800_000, scale 1_800_000; the stub predicts the measurement at 09:52, so the predicted margin is `09:30 - 09:52 = -1_320_000` ms and `sigma_hat = -1_320_000 / 1_800_000 = -0.7333`; with `alpha = 0.2` and one instance, `q = 0.4`, `-0.7333 + 0.4 < 0` gives `PREDICTED_VIOLATION` with `rho.value == pytest.approx(0.9)` (`alpha_star = (0 + 1) / 10`, no score is at least 0.7333), `rho.kind == PREDICTED`, and `predicted_sigma_norm == pytest.approx(-0.3333)`; a measurement at 09:51 (G-SCHED-3, margin -21 min, `-0.7`) then gives `VIOLATED` at the deadline: the sequence is `PENDING`, `PREDICTED_VIOLATION`, `VIOLATED`.
6. `test_predicted_then_satisfied_is_a_false_predictive_alarm`: the same prediction and a measurement at 09:20 give `PENDING`, `PREDICTED_VIOLATION`, `SATISFIED` (allowed transition of `#verdict`; the metrics module counts it as a false predictive alarm).
7. `test_variant_switch_changes_emission`: the stub predicts 09:21, so `sigma_hat = 540_000 / 1_800_000 = 0.3`; with `variant="likely"` (`0.3 + 0.4 >= 0`) no prediction is emitted; with `variant="possible"` the emission follows the definition of WS01-T06 (under the literal reading `0.3 - 0.4 < 0` it is emitted).
8. `test_alpha_is_allocated_over_pending_tests_of_the_patient_day`: a plan with two `sched` instances and one `resp` instance, all with forecast coverage, gives `n_tests == 3`; with `config.alpha = 0.3` every prediction uses `per_test(0.3, 3) == 0.1`, visible in `rho.alpha`; instances without a predictive path are not counted.
9. `test_no_forecast_coverage_means_no_predictive_path`: a `resp` instance with a forecaster that supports only `meas` makes no prediction and does not enter `n_tests`; `stats()` records the reason.
10. `test_resp_completes_bp_by_forecast_at_scheduled_ticks`: for `resp` with `bp_pre = 150`, a scheduled measurement tick at 08:30 inside `[a + delta1, a + delta2]` and a stub `bp` forecast of 145 at that tick, the unknown future is completed by the forecast for `bp` and by the plan schedule for `meas`, giving `sigma_hat = (150 - 145 - 10) / 20 = -0.25` (G-RESP-2: `-5` mmHg, `-0.25`).
11. `test_horizon_is_time_to_deadline_extended_by_scale_for_time_templates`: for `sched` at activation the forecaster is called with `horizon_ms == 1_800_000 + 1_800_000` (time to the deadline plus the template scale, so overruns up to the clipping point are representable); for `resp`, whose unit is mmHg, with the time to the deadline only.
12. `test_prediction_uses_only_released_history`: the `history` given to the forecaster contains only samples with `t_device_ms <= t_eval_ms - reorder_delay_ms`.
13. `test_insufficient_history_means_no_prediction`: a forecaster raising `InsufficientHistoryError` at activation gives no prediction, unchanged verdicts, and a counter in `stats()`; any other exception propagates.
14. `test_stale_calibrator_is_refused`: `calibrator.calibrated_for == "v1"` with `forecaster.model_version == "v2"` raises `StaleCalibratorError` at construction; after `calibrator.fit(..., model_version="v2")` it is accepted; after a forecaster refit that changes its version, the next `advance` raises `StaleCalibratorError`; `calibrated_for is None` is refused (analisi §2 R2 weakness 6).
15. `test_predicted_record_fields`: the `PREDICTED_VIOLATION` record has `rho` of kind `PREDICTED` with `alpha` equal to the per-test level, `predicted_sigma_norm` equal to `sigma_hat + q` clipped to `[-1, 1]`, `sigma_interval` and `pending_until_ms` those of the measured-prefix `PENDING` state (ADR-008: the raw interval remains the measured one), and `decided_at_ms is None`.

Calibration episodes (`test_calibration_episodes.py`)

16. `test_build_calibration_episodes_hand_case`: day A (predicted arrival 09:52, measurement at 09:51) gives an episode with `sigma_hat = -0.7333` and `sigma_true = -0.7` (`-1_260_000 / 1_800_000`); day B (predicted 09:21, measurement at 09:25) gives `sigma_hat = 0.3` and `sigma_true = 0.1667` (`300_000 / 1_800_000`); `patient_id`, `day_index` and `template == SCHED` are those of the days.
17. `test_episodes_use_measured_completion_only_and_skip_censored`: an instance whose window closes after the end of the day is skipped and counted in the second element of the returned pair `(episodes, n_censored)`; the function accepts `ObservedTrace` days and has no parameter that could carry a `LatentDay` (the monitor never receives it).
18. `test_calibration_and_deployment_share_the_code_path`: for the same instance, the `sigma_hat` of `build_calibration_episodes` equals the value the `StreamingMonitor` used when it predicted (Hypothesis over random days).

End to end (`tests/test_end_to_end.py`)

19. `test_worked_patient_day_end_to_end` (golden, WS01-T08): `run_offline` on the observed trace of `09-worked-patient-day.md`, then `extract_evidence` and `RuleAttributor.attribute_all`, gives alerts equal to the expected tuples of that document (template, attributed cause, normalised severity, kind of rho and its value, explanation template and instance key); the test is not skipped.
20. `test_cascade_row_15_00_pipeline`: a trace built from analisi §4.6 row 15:00 (missed measurement with a robot navigation failure and a later day-end measurement-count violation) gives one top-level C2 alert and one folded effect with `caused_by` set.
21. `test_alerts_are_valid_detections`: every returned alert is an instance of `Detection` with `t_ms`, `label` and `score` as WS05-T07 derives them (so WS08-T01 can wrap the pipeline as a `Detector`).
22. `test_run_offline_is_deterministic`: two runs on the same inputs give identical record tuples and identical alerts; nothing depends on dictionary order or on the clock.

## Passi

1. Verify unblock conditions (Contesto); branch `ws05-t08-predictive-integration`; `status: in_progress`. Read the ADRs of WS05-T05 and WS05-T06, ADR-008, and decisions D5, D6, D7 and D10 of the workstream README. Write in the completion note: the WS01-T06 definition of the "possible" variant, how `predicted_sigma_norm` is set for it, and the disposition of CP5 in WS01-T07 (the contract calls `Alert.sigma_norm` negative, a predicted alert with the "possible" variant can carry a non-negative value; the rule of WS01-T07 wins).
2. Write the tests and the hand scenarios (stub forecasters and calibrator fixtures); delete the temporary test of WS05-T04; run `pytest tests/monitor tests/test_end_to_end.py -q`; watch them fail for the right reason. Commit `WS05-T08: add failing predictive tests`.
3. Implement `predictive.py`: at instance activation, if `config.predictive` and the instance has a predictive path, build the completed trace (measured prefix, forecast means for the unknown signals the forecaster supports, plan-schedule impulses for `meas` where the template needs a scheduled measurement, physiological bounds are not used here), evaluate the instance body with the point evaluator, normalise with the template scale, call `calibrator.predict(sigma_hat, per_test_alpha)` with `variant=config.variant`, and emit the `PREDICTED_VIOLATION` record when `emitted`. `n_tests` is computed at `load(plan)` as the number of instances with a predictive path; `per_test` comes from `BonferroniAllocation` (`MonitorConfig.alpha` is the total alpha of the patient-day, decision D6).
4. Extend `core.py`: constructor checks (`MonitorConfigError`, `StaleCalibratorError` when `calibrated_for != forecaster.model_version`, re-checked on every `advance`), the `PENDING` then `PREDICTED_VIOLATION` emission at activation, counters in `stats()` for skipped predictions and their reasons. Extend `offline.py`. Implement `build_calibration_episodes(days, plans, config, forecaster, *, registry=None, templates=None)` on the same code path (a hook records `sigma_hat` at activation; `sigma_true` is the normalised robustness of the instance on the complete observed day, computed with the point evaluator, so a late measurement counts as in G-SCHED-3); return the pair `(episodes, n_censored)` (no new public type).
5. Write the end-to-end tests with the WS01-T08 day. If the document does not exist, stop with `status: in_progress` and say so.
6. Append the ADR (status `proposed`, confirmation tag): one prediction per pending instance at activation and why (a fixed lead makes episodes exchangeable, `n_tests` is known at load, the union bound is affordable); the consequence that continuous re-prediction as the robot estimate improves needs calibration per lead time and is not done; `MonitorConfig.alpha` means the total alpha per patient-day; the horizon rule; measured (observed) completion for calibration episodes; the honest limitation that a small `per_test` makes the finite-sample quantile infinite and silences early warnings, reported as a result. Update `#monitor` in `02-interfaces.md` and bump its version.
7. Refactor; remove migrated names from `monitor/_stubs.py`; run `pytest tests -q -k "monitor or end_to_end or public_api or layering"`, `ruff format src tests`, `ruff check src tests`, `mypy src/ralmon`. Commit `WS05-T08: integrate predictive monitoring`; set `status: done` and `status: ready` in the task files whose `depends_on` are now all `done`; tell WS08-T01 in the completion note which functions build the pipeline.

## Done when

From the repository root, inside `.venv`:

- `pytest tests/monitor tests/test_end_to_end.py -q` exits 0 with no skipped test (`-rs` prints nothing).
- `pytest tests -q` exits 0.
- `ruff check src tests` and `ruff format --check src tests` exit 0; `mypy src/ralmon` exits 0.
- `python -c "from ralmon.monitor import run_offline, StreamingMonitor, build_calibration_episodes, StaleCalibratorError"` exits 0 and none has `__ralmon_stub_owner__`.
- `python -c "import ralmon.monitor as m, inspect; assert 'LatentDay' not in inspect.getsource(m)"` exits 0.
- `! grep -rn "^from ralmon\.\(attribution\|baselines\|eval\|benchmark\)\|^import ralmon\.\(attribution\|baselines\|eval\|benchmark\)" src/ralmon/monitor` succeeds.
- `python tools/check_plan.py` exits 0.

## Notes

### Flag from the WS01-T04 review (orchestrator, 2026-09-30)

Tests 5 and 15 define `predicted_sigma_norm` as `sigma_hat + q` clipped to [-1, 1] (test 5 expects -0.3333), while `docs/formal/04-normalisation-ranking.md` section 4.6 and OP-4 propose the normalised point forecast and exclude any bound involving `q` (OP-15). WS01-T05, T06 and T07 decide; WS05-T07 test 3 says the rule of WS01-T07 wins. No status change: this task was already `blocked`.
