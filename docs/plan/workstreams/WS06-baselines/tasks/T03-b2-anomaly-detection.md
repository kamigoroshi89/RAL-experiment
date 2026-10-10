---
id: WS06-T03
title: B2 anomaly detection (forecast residual and isolation forest)
workstream: WS06-baselines
owner: agent
status: blocked
depends_on: ["WS06-T01", "WS05-T05"]
critical_path: true
non_negotiable: false
estimate_pd: 2
sources: ["analisi §5.4 (B2)", "analisi §2 R2 weakness 8", "analisi §4.3", "analisi §10 (1)"]
interfaces: ["02-interfaces.md#detector", "02-interfaces.md#forecaster"]
review_items: ["R2-W8"]
---
## Obiettivo

Implement `B2AnomalyDetection`, the approach the paper says it moves away from (analisi §5.4 B2): a forecast-residual z-score and an Isolation Forest on features, both purely data-driven, unsupervised, and blind to the STL templates and to the clinical bands. It closes review item R2-W8 ("a multivariate time-series learner ... is in fact residual-based anomaly detection") by making that reading an explicit, measurable comparison. Concrete output: `src/ralmon/baselines/b2_anomaly_detection.py`, `b2_features.py` and their tests.

## Contesto

- `02-interfaces.md#detector` and `02-interfaces.md#forecaster` (`Forecaster.fit(train_days)`, `predict(history, t_ms, horizon_ms) -> Forecast`); the class and its import path are fixed by WS05-T05 (the package public API table does not list `Forecaster`; if it is not exported from a package `__init__`, do not import a private module, raise it in the completion note).
- The harness of WS06-T01 in `src/ralmon/baselines/` (`BaselineBase`, `iter_steps`, `rising_edges`, `GuardedDay`, `AccessLog`).
- `docs/source/analisi.md` §5.4 row B2, §4.3 (blood pressure with about five measurements per day is a poor forecasting target; heart rate and SpO2 are the in-scope continuous signals) and §10 objection 1.
- `docs/source/review.md`, R2 weakness 8.
- Blocked until `WS06-T01` and `WS05-T05` are `done`. Package `scikit-learn` provides `IsolationForest`; if it is not yet a declared dependency, this task adds it to `pyproject.toml` and says so in the completion note (the version constraint is taken from the installed environment, not from this plan).

## File toccati

- `src/ralmon/baselines/b2_anomaly_detection.py` (create)
- `src/ralmon/baselines/b2_features.py` (create)
- `tests/baselines/test_b2_anomaly_detection.py` (create)
- `tests/baselines/test_b2_features.py` (create)
- `src/ralmon/baselines/__init__.py` (modify: export `B2AnomalyDetection`)
- `pyproject.toml` (modify only if `scikit-learn` is not declared yet)

## Test

Write these first. Stub forecaster in tests: a persistence forecaster (its forecast for every grid point is the last value in `history` of the requested signal); its `fit` is a no-op. Timing: `step_ms=60_000`, `reorder_delay_ms=0`. Values are test-local and hand-computed.

Residual definition (the same wording is used in WS06-T05 and checked by WS06-T07): the residual of a delivered sample of signal `s` at `t` is `value - forecast`, where the forecast is issued at the time `t_prev` of the previous delivered sample of `s` with horizon `t - t_prev`, and read from the path at index `floor((t - t_from_ms) / step_ms)` following the index convention documented by WS05-T05. The first sample of a signal has no residual.

`tests/baselines/test_b2_features.py`

1. `test_features_hand_computed`: BP 150 at 1 h, DISPENSE at 2 h, `plan.schedule = [3 h]`; at `t = 2.5 h` the row is `last_bp = 150`, `age_bp_ms = 5_400_000`, `dose_count_24h = 1`, `since_last_dispense_ms = 1_800_000`, `to_next_tick_ms = 1_800_000`.
2. `test_features_undefined_before_first_input`: at `t = 0` every feature that needs a delivered input is `None`; `to_next_tick_ms` is `None` after the last scheduled tick.
3. `test_features_are_causal_property` (Hypothesis): the row at `t` is unchanged when later inputs are appended.
4. `test_features_use_only_observed_inputs_and_schedule`: the extractor's signature accepts step batches and `plan.schedule` only; it never reads `param_values`.

`tests/baselines/test_b2_anomaly_detection.py`

5. `test_b2_residual_zscore_hand_computed`: calibration HR at 1 h to 5 h = 60, 63, 60, 63, 60 gives residuals +3, -3, +3, -3 (mean 0, population standard deviation 3). Test day HR 60, 60, 72 with `z_threshold=3.0`: residuals 0 and +12, `z = 4.0`, one detection at the delivery step of the 72 sample with `score = 4.0 / 3.0` (scores are normalised by their own threshold; above 1 means alarm).
6. `test_b2_zscore_threshold_strict_and_two_sided`: a sample with residual +9 (`z = 3.0`) gives no detection; residual -12 gives a detection with the same score as +12.
7. `test_b2_first_sample_has_no_residual`: a day with a single HR sample gives no residual detection.
8. `test_b2_residual_scale_from_calibration_days_only`: changing the train days (forecaster input) does not change mean and standard deviation; changing the calibration days does; the `AccessLog` shows `observed` reads only.
9. `test_b2_quantile_threshold_hand_computed`: scores `[1, 2, 3, 4]` with `score_quantile=0.75` give threshold `3.25` (`numpy.quantile`, linear interpolation).
10. `test_b2_iforest_scores_outlier_above_inlier`: 200 synthetic training rows (`numpy.random.Generator` seeded 0) around a fixed centre; a row far outside the cloud scores above a row at the centre (rank assertion; no absolute expected value, isolation forests are randomised).
11. `test_b2_iforest_one_detection_per_rising_edge`: with a stub scorer returning `[0.1, 0.9, 0.95, 0.2, 0.8]` and threshold `0.5`, detections are at steps 1 and 4 with scores `1.8` and `1.6`.
12. `test_b2_deterministic_given_seed`: two instances built with the same integer `seed` and fitted on the same days give identical detection lists; omitting `seed` raises `TypeError`.
13. `test_b2_modes_and_names`: `mode="residual"` gives `name == "B2-residual"`, `"iforest"` gives `"B2-iforest"`, `"both"` gives `"B2"` and the detection list is the time-sorted union of the two.
14. `test_b2_operating_parameters_have_no_numeric_defaults`: `z_threshold` and `score_quantile` default to `None` and the constructor raises if the parameter required by the chosen mode is missing (values come from WS08 configs).
15. `test_b2_ignores_evidence_and_never_labels`: identical output with and without an `EvidenceVector`; all labels `None`.
16. `test_b2_reads_no_ground_truth_latent_or_clinical_thresholds`: after `fit`, the `AccessLog` has no `ground_truth` or `latent` read; during `run`, the plan read log is empty (only `plan.schedule` is used) and the registry read log is empty.
17. `test_b2_is_causal_property` (Hypothesis): detections with `t_ms <= T` are the same for the full day and for the day truncated to inputs with `t_rx_ms <= T`.

## Passi

1. Verify unblock conditions. Branch `ws06-t03-b2-anomaly-detection`; `status: in_progress`. Read the docstring of the WS05-T05 forecaster for the index convention of `Forecast.mean` and for which signals it supports.
2. Write the 17 tests; run them; watch them fail.
3. Implement `b2_features.py`: a streaming extractor over `StepBatch` values. Required features: last value and age (ms since the last delivered sample) of each monitored signal, `dose_count_24h` over `(t - 24 h, t]`, `since_last_dispense_ms`, `to_next_tick_ms` and `since_last_tick_ms` from `plan.schedule`, and time of day (`t_ms` modulo 24 h). No band, no hold threshold, no window parameter, no template (B2 is the baseline without the specification). Record the final `FEATURE_NAMES` in the module docstring.
4. Implement `B2AnomalyDetection(BaselineBase)` with constructor arguments `forecaster`, `mode` (`"residual"`, `"iforest"`, `"both"`), `signals` (default: the `SignalId` members for BP, HR_ECG, HR_PULSE and SPO2), `z_threshold`, `score_quantile`, `seed`, `feature_step_ms` and `timing` (`TimingConfig` of WS06-T01, equal to the monitor's `step_ms` and `reorder_delay_ms` in the experiment config). `_fit`: fit the forecaster on the observed train days; estimate residual mean and standard deviation per signal from the observed calibration days (population standard deviation, computed the same way in B4); estimate feature means for imputation on the train days; fit `IsolationForest` on train-day feature rows (unlabelled, seeded through the estimator's random-state argument with the integer `seed`); set the isolation threshold as the `score_quantile` quantile of calibration-day scores. `_run`: residual detections per delivered sample; isolation detections on rising edges of `score > threshold`; union sorted by time.
5. Write the class docstring with `Hyperparameter selection`: `z_threshold` and `score_quantile` are operating parameters, swept by WS08 over a grid declared in the experiment config; no value is tuned on test days; `n_estimators` and other estimator settings are left at the library defaults unless the completion note justifies a change from calibration days.
6. Export from `__init__.py`; add `scikit-learn` to `pyproject.toml` if needed; run `ruff format`, `ruff check src tests`, `mypy src/ralmon`, `pytest tests/baselines -q`; refactor.
7. In the completion note add three sentences for the paper's baseline paragraph: what B2 is, that it uses the same forecaster class as the proposed method, and that it has no access to bands or templates (this is what R2-W8 says the paper must be distinguished from).
8. Commit `WS06-T03: add B2 anomaly detection baseline`; `status: done`; paste outputs in the completion note.

## Done when

- `pytest tests/baselines/test_b2_features.py tests/baselines/test_b2_anomaly_detection.py -q` exits 0, and `pytest tests/baselines -q` still exits 0.
- `ruff check src tests` and `mypy src/ralmon` exit 0.
- `python -c "from ralmon.baselines import B2AnomalyDetection"` exits 0.
- `grep -lE 'LatentDay|GroundTruthEvent|normalise|rank_alerts' src/ralmon/baselines/b2_anomaly_detection.py src/ralmon/baselines/b2_features.py` prints nothing.

## Notes

**Hand-over from WS05-T05 (forecaster, ADR-057).** The index of a `Forecast` path is `(t - t_from_ms) // step_ms - 1` (`mean[k]` predicts `t_from_ms + (k + 1) * step_ms`), not `floor((t - t_from_ms) / step_ms)` as the test text above writes it. The Protocol call `predict(history, t_ms, horizon_ms)` has no target signal: a baseline that needs a given signal must call the concrete class with the keyword `signal=` (or pass a history that holds one signal only). `supported_signals` and `model_version` exist on every forecaster; import the classes and `InsufficientHistoryError` from `ralmon.monitor`, which now lists them in the public API table.
