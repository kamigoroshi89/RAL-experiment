---
id: WS05-T05
title: "Forecaster for continuous signals and robot deadlines"
workstream: WS05-monitor
owner: agent
status: in_progress
depends_on: ["WS05-T04"]
critical_path: true
non_negotiable: false
estimate_pd: 3
sources: ["analisi §4.3", "analisi §2 R2"]
interfaces: ["02-interfaces.md#forecaster"]
review_items: ["R2-W1", "R2-W5", "R2-W8"]
---
## Obiettivo

Give the forecaster a technical definition, as R2-W1 demands: implement the `Forecaster` protocol of `#forecaster` with three concrete forecasters in `ralmon.monitor` (a persistence reference, an autoregressive forecaster for continuous signals, and an additive forecaster of robot arrival for care-delivery deadlines), and record the model choice, targets, inputs, horizon and training data in an ADR. Blood pressure with about five measurements a day is expected to be uninformative as a forecasting target (analisi §4.3, R2-W5): the same code path serves it so that WS08 can report the interval width honestly as a finding, and this task makes no accuracy claim. The forecaster emits paths only; it never scores anomalies (R2-W8: that is baseline B2).

## Contesto

Blocked until WS05-T04 is `done` (it defines the `Forecast` and `Forecaster` contract types in `ralmon.monitor`).

- `02-interfaces.md#forecaster` (`Forecast`, `Forecaster`; the signals contract and ADR-008 are quoted where used).
- `docs/source/analisi.md` §4.3 (last two paragraphs: five-a-day pressure is a poor target; heart rate, SpO2 and robot care-delivery deadlines are the candidates).
- `docs/source/review.md` (R2 weaknesses 1, 5 and 8).
- `docs/formal/01-signals-sampling.md` (section 3: grid, hold, ceiling rule).
- `docs/plan/workstreams/WS07-ros2-sim/README.md` (the robot task node publishes robot state as `Sample` on `/ralmon_sim/robot/state_samples`; WS07-T04 and WS07-T06 consume the signal names fixed here).

## File toccati

- `src/ralmon/monitor/` (modify: create `forecasters.py`; extend `forecast.py` docstrings with the index convention; update `__init__.py`)
- `src/ralmon/signals/` (modify: two new `SignalId` members in `ids.py`)
- `tests/monitor/` (create: `test_forecasters.py`, `test_deadline_forecaster.py`)
- `tests/signals/` (modify: the `SignalId` values test of WS05-T02)
- `docs/plan/03-decisions.md` (modify: append the model-choice ADR, status `proposed`, confirmation tag)
- `docs/plan/02-interfaces.md` (modify: `#signals` and `#forecaster` additions and version bumps, `#package-public-api` additions)

## Test

Write first; each fails before the implementation. All series are fixture-only arithmetic, not clinical values. Step `T_s = 60_000` ms. Time labels convert with `t_ms = (60*hh + mm) * 60000`.

Contract of `Forecast` and the reference (`test_forecasters.py`)

1. `test_forecast_index_convention_and_length`: a forecast issued at 09:00 (32_400_000) with horizon 300_000 has `t_from_ms == 32_400_000`, `len(mean) == 5`, and `mean[k]` predicts the value at `t_from_ms + (k + 1) * step_ms`; a horizon of 330_000 still gives 5 (floor). The docstring of `Forecast` states this convention (WS06-T03 reads it).
2. `test_persistence_repeats_last_value`: `hr_ecg` samples 70.0 at 08:00 and 72.0 at 08:58 give, from 09:00 with horizon 180_000, `[72.0, 72.0, 72.0]`.
3. `test_forecasters_use_only_history_up_to_t` (Hypothesis): appending samples with `t_device_ms > t_ms` to `history` never changes the forecast.
4. `test_predict_before_fit_raises`: `ForecasterNotFittedError` for the autoregressive and deadline forecasters (persistence needs no fit).
5. `test_insufficient_history_and_unsupported_signal_raise_specific_errors`: an autoregressive forecaster of order 2 with one sample raises `InsufficientHistoryError`; a request for a signal outside `supported_signals` raises `UnsupportedSignalError`; nothing returns a silent default.
6. `test_fit_is_deterministic_and_seedless`: two fits on the same days give equal parameters and equal `model_version`; the constructors accept no random generator.
7. `test_model_version_is_content_hash`: `model_version` is a hex digest of the sorted fitted parameters (floats through `repr`), equal after refitting the same data, different after fitting other data, and independent of the clock; `PersistenceForecaster` has a constant version.

Autoregressive forecaster (`test_forecasters.py`)

8. `test_ar1_recovers_noise_free_coefficients`: one training day with an `hr_ecg` sample on every grid step following `x[k+1] = 0.5 * x[k] + 10` from `x[0] = 40` (values 40, 30, 25, 22.5, 21.25, 20.625, ...) gives fitted intercept `10.0` and coefficient `0.5` within `1e-9` (least squares on data that lie exactly on a line).
9. `test_ar1_multistep_matches_closed_form`: with that fit and a history ending in 40.0, `predict(..., horizon_ms=180_000)` returns `[30.0, 25.0, 22.5]` (0.5 * 40 + 10, 0.5 * 30 + 10, 0.5 * 25 + 10).
10. `test_order_is_an_explicit_argument`: `AutoRegressiveForecaster()` without `order` raises `TypeError` (no default order is invented; WS08 chooses it on validation days).
11. `test_training_series_is_the_hold_last_grid`: the private helper that builds a training series from a day returns, for `bp` samples 150.0 at 06:00 and 140.0 at 09:00 and the grid 06:00 to 09:01, 180 values of 150.0 followed by 2 values of 140.0 (the series is `hold_last` on the monitor grid, so sparse pressure becomes a piecewise-constant series and the forecaster is not fitted on the raw irregular samples).
12. `test_bp_path_exists_and_expectation_is_documented`: an autoregressive forecaster fitted on sparse `bp` days returns a path of the right length, and its class docstring states that blood pressure with about five measurements a day is expected to be uninformative (analisi §4.3, R2-W5) and that no accuracy claim is made.
13. `test_no_anomaly_scoring_in_forecaster_api`: the public attributes of the three classes contain no name with `score`, `residual` or `anomaly` (R2-W8; residual-based detection is baseline B2).

Robot-deadline forecaster (`test_deadline_forecaster.py`)

14. `test_deadline_forecast_places_impulse_at_predicted_arrival`: latest samples at 09:00: `nav_eta_ms = 1_500_000` (25 min) and `task_queue_ms = 600_000` (10 min), bias 0, so predicted arrival is 09:35 (34_500_000); with horizon 2_400_000 the forecast has `signal == "meas"`, 40 entries, `mean[34] == 1.0` (grid time `t + 35 * step`) and every other entry 0.0.
15. `test_deadline_forecast_all_zero_beyond_horizon`: the same state with horizon 1_800_000 gives 30 entries, all 0.0 (predicted arrival after the horizon).
16. `test_deadline_fit_learns_mean_signed_bias_and_counts_censoring`: training episode 1: `sched_tick` at 09:00, `nav_eta_ms` 1_500_000 and `task_queue_ms` 600_000 just before it, first `meas` at 09:37, residual `+120_000`; episode 2: tick at 21:00, ETA 300_000, queue 0, first `meas` at 21:04, residual `-60_000`; episode 3: a tick with no later `meas` that day is censored. After `fit`: bias `+30_000`, `n_train_episodes == 2`, `n_censored == 1`.
17. `test_deadline_forecast_uses_learned_bias`: after that fit, the state of test 14 predicts arrival 09:35:30 (34_530_000) and puts the impulse at the first grid step at or after it, `mean[35] == 1.0` (ceiling rule).
18. `test_deadline_state_without_robot_signals_raises`: no `nav_eta_ms` or `task_queue_ms` sample at or before `t_ms` raises `InsufficientHistoryError` (the robot state channel is unavailable, not zero).
19. `test_signal_id_includes_robot_state_signals` (`tests/signals`): `SignalId` has the two added members `nav_eta_ms` and `task_queue_ms` and still has the 17 original ones.

## Passi

1. Verify unblock conditions; branch `ws05-t05-forecaster`; `status: in_progress`. Read the Contesto sources, ADR-008, and decisions D6 and D10 of the workstream README.
2. Write the tests; run `pytest tests/monitor/test_forecasters.py tests/monitor/test_deadline_forecaster.py tests/signals -q`; watch them fail for the right reason. Commit `WS05-T05: add failing forecaster tests`.
3. Add the two `SignalId` members `NAV_ETA = "nav_eta_ms"` (remaining navigation time to the patient room, published by the robot task layer, integer milliseconds) and `TASK_QUEUE = "task_queue_ms"` (summed estimated duration of the tasks queued ahead of the care-delivery task, integer milliseconds). The contract has no signal for the robot state that "from task queue and navigation state" (analisi §4.3) requires; the ADR of step 6 records the contract change.
4. Implement `forecasters.py`: `PersistenceForecaster(step_ms)`; `AutoRegressiveForecaster(step_ms, order)` (least squares by `numpy.linalg.lstsq` on the hold-last grid series of the training days, iterated multi-step prediction, one model per signal); `DeadlineForecaster(step_ms)` (predicted arrival = `t_ms` + latest `nav_eta_ms` + latest `task_queue_ms` + learned bias; both robot-state signals are assumed refreshed at least once per step by the robot task layer, staleness is not compensated and this is stated in the docstring; `fit` builds episodes from `sched_tick`, the robot-state samples at or before the tick and the first `meas` at or after it, and stores the mean signed residual). Each class has `name`, `supported_signals`, `model_version`, `fit`, `predict`, and the errors `ForecasterNotFittedError`, `InsufficientHistoryError`, `UnsupportedSignalError`. Inputs are `ObservedTrace` days.
5. Refactor; run `pytest tests/monitor tests/signals -q`, `ruff format src tests`, `ruff check src tests`, `mypy src/ralmon`.
6. Write the ADR (status `proposed`, confirmation tag). It must state: what is predicted (`hr_ecg`, `hr_pulse`, `spo2`, `bp` as continuous or sparse signals; `meas` arrival for robot deadlines), the inputs of each model, the horizon (chosen by the caller: the monitor passes the time to the deadline, extended by the template scale when its unit is `ms`, WS05-T08), the training data (the train split of the benchmark, by patient, `fit(train_days)`), the model class per target and why (autoregression by least squares needs no dependency and is auditable; persistence is the mandatory reference reported next to it; the additive model answers the deadline example of analisi §4.3), the order `p` left to validation days in WS08, the expectation that blood pressure is uninformative and will be reported as a finding, and, after checking the section-3 table of `docs/formal/02-templates.md` (in analisi §4.1 no template uses `hr_ecg`, `hr_pulse` or `spo2`), that these forecasts are then evaluated on their own by WS08 and do not produce `PREDICTED_VIOLATION` (only `sched` and `resp` do, WS05-T08). Contract changes in the same commit: `#signals` gains the two members; `#forecaster` gains `model_version: str` and `supported_signals: frozenset[str]` on the protocol; `#package-public-api` gains `PersistenceForecaster`, `AutoRegressiveForecaster`, `DeadlineForecaster`, `ForecasterNotFittedError`, `InsufficientHistoryError`, `UnsupportedSignalError`; bump each version.
7. Run every command of "Done when". Commit `WS05-T05: implement forecasters`; set `status: done` and `status: ready` in the task files whose `depends_on` are now all `done`; tell WS07-T04 and WS06-T03 (through the completion note) the class names, the signal names and the `Forecast.mean` convention.

## Done when

From the repository root, inside `.venv`:

- `pytest tests/monitor tests/signals -q` exits 0.
- `ruff check src tests` and `ruff format --check src tests` exit 0; `mypy src/ralmon` exits 0.
- `python -c "from ralmon.monitor import PersistenceForecaster, AutoRegressiveForecaster, DeadlineForecaster, Forecast, Forecaster, ForecasterNotFittedError, InsufficientHistoryError, UnsupportedSignalError"` exits 0.
- `python -c "from ralmon.signals import SignalId; assert len(SignalId) == 19"` exits 0.
- `grep -n "uninformative" docs/plan/03-decisions.md` shows the sentence of the new ADR, and `grep -c "Forecaster" docs/plan/02-interfaces.md` is unchanged or larger (the contract was extended, not replaced).
- `python tools/check_plan.py` exits 0.

## Notes

Completion note (worker, branch `ws05-t05-forecaster`; status left `in_progress` for the reviewer).

- **Done.** `src/ralmon/monitor/forecasters.py` (new) holds `PersistenceForecaster(step_ms)`, `AutoRegressiveForecaster(step_ms, order)`, `DeadlineForecaster(step_ms)` and the errors `ForecasterNotFittedError`, `InsufficientHistoryError`, `UnsupportedSignalError`, all exported from `ralmon.monitor`. `SignalId` has `NAV_ETA = "nav_eta_ms"` and `TASK_QUEUE = "task_queue_ms"` (19 members). `Forecast` documents the index convention. ADR-057 (proposed, `[DA-CONFERMARE]`) records the model choice; `#signals` 0.2.0, `#forecaster` 0.2.0 and `#package-public-api` 0.2.2 carry the contract changes.
- **Hand-over to WS05-T08, WS06-T03, WS06-T05, WS06-T06, WS07-T04, WS07-T06.** Import path: `from ralmon.monitor import PersistenceForecaster, AutoRegressiveForecaster, DeadlineForecaster, InsufficientHistoryError, ...` (the public API table now lists them). `Forecast.mean[k]` predicts `t_from_ms + (k + 1) * step_ms`, `len(mean) == horizon_ms // step_ms`; the value at `t_from_ms` is not in the path, so to read the path at `t` use index `(t - t_from_ms) // step_ms - 1`, not `floor((t - t_from_ms) / step_ms)` as WS06-T03 test text writes it (the wording of WS06-T03 and WS06-T05 must be aligned with the docstring of `Forecast`). Signals: the deadline forecaster forecasts `meas` and reads `nav_eta_ms` and `task_queue_ms` (integer ms, published by WS07-T04 as `Sample`s); the continuous forecasters support `bp`, `hr_ecg`, `hr_pulse`, `spo2`.
- **Deviations and assumptions that did not hold.** (1) The protocol `predict(history, t_ms, horizon_ms)` has no target signal, so WS06-T03's "requested signal" and WS05-T08's "unknown signals the forecaster supports" cannot be expressed; the concrete classes take an optional keyword-only `signal=` and otherwise infer the single supported signal present in the history (several candidates: `ValueError`). Recorded in ADR-057 (i); the `Forecaster` Protocol is unchanged in its call signature. (2) A benchmark `ObservedDay` carries `meas` and `sched_tick` as events only (`measurement.py`), so `DeadlineForecaster.fit` reads both events (via `event_to_sample`) and same-name samples, de-duplicated by time. (3) The WS04 generator does not emit `nav_eta_ms` or `task_queue_ms`: until WS04 or WS07 supplies them, `DeadlineForecaster.fit` on benchmark days counts every tick in `n_no_robot_state` and raises `ValueError` (no bias is invented); `n_no_robot_state` is an extra counter beyond the task text. (4) `AutoRegressiveForecaster.predict` needs at least `order` samples of the signal (test 5: one sample with order 2 raises), and a signal with fewer training rows than parameters has no model. (5) An arrival at or before `t_ms` (negative bias) is placed on the first step. (6) The test `tests/monitor/test_public_api.py` classification sets gained the new module and classes; `tests/signals/test_samples.py` was updated to 19 members. (7) Status not set to `done` and dependents not unblocked, as the worker instruction says; WS05-T08 and WS06 tasks still need the reviewer.
