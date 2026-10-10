---
id: WS06-T05
title: B4 conformal without STL
workstream: WS06-baselines
owner: agent
status: blocked
depends_on: ["WS06-T01", "WS05-T06", "WS05-T05"]
critical_path: true
non_negotiable: false
estimate_pd: 2
sources: ["analisi §5.4 (B4)", "analisi §4.4", "analisi §10 (1)"]
interfaces: ["02-interfaces.md#detector", "02-interfaces.md#conformal-calibrator"]
review_items: []
---
## Obiettivo

Implement `B4ConformalOnly`: conformal anomaly detection that raises a detection when a measurement leaves the conformal prediction interval of a forecaster, with no STL template, no band and no schedule knowledge (analisi §5.4 B4). It isolates the contribution of the specification: whatever B4 misses that the proposed method finds is due to having a clinical specification. Concrete output: `src/ralmon/baselines/b4_conformal_only.py` and its tests, built on the public API of `ralmon.conformal` (the same calibrator code as the proposed method).

## Contesto

- `02-interfaces.md#detector` and `02-interfaces.md#conformal-calibrator` (`CalibrationEpisode`, `ConformalCalibrator.fit/quantile`, `AlphaAllocation`; rules 1 and 2: calibration unit is the patient episode, coverage is marginal over the population under exchangeability).
- The harness of WS06-T01 in `src/ralmon/baselines/` and the calibrator implementation of WS05-T06 in `src/ralmon/conformal/` (read the `SplitConformal` docstring for the quantile rule and the sign convention).
- `docs/source/analisi.md` §5.4 row B4, §4.4 (score, one-sided quantile, caveats), §10 objection 1.
- The forecaster class and import path fixed by WS05-T05 (same as in WS06-T03; the package public API table does not list `Forecaster`). WS05-T05 is not in `depends_on`: if it is not `done`, stay blocked and record the missing edge in the completion note.
- Blocked until `WS06-T01` and `WS05-T06` are `done`.

## File toccati

- `src/ralmon/baselines/b4_conformal_only.py` (create)
- `tests/baselines/test_b4_conformal_only.py` (create)
- `src/ralmon/baselines/__init__.py` (modify: export `B4ConformalOnly`)

## Test

Write these first. Stub forecaster: persistence (forecast = last value of the requested signal in `history`), no-op `fit`. Stub calibrator: a `ConformalCalibrator` that returns a preset `q` from `quantile(alpha)` and records every call and every episode passed to `fit`. Timing: `step_ms=60_000`, `reorder_delay_ms=0`. The residual definition is exactly the one written in WS06-T03 (value minus the forecast issued at the previous delivered sample of the same signal, horizon equal to the gap, first sample has none), and WS06-T07 tests that B2 and B4 agree on it.

1. `test_b4_interval_alarm_hand_computed`: `q = 5.0`; HR samples 60, 62, 70, 50 give residuals 2, 8, -20; detections at the delivery steps of the 70 and 50 samples with scores `8 / 5 = 1.6` and `20 / 5 = 4.0` (score is the residual magnitude divided by `q`; above 1 is an alarm).
2. `test_b4_boundary_is_inside_interval`: a residual of exactly `5.0` gives no detection (closed interval).
3. `test_b4_first_sample_has_no_forecast`: a single sample gives no detection.
4. `test_b4_day_max_episodes_hand_computed`: calibration day 1 HR 60, 62, 70 (residual magnitudes 2, 8) and day 2 HR 60, 61, 61 (1, 0): with `unit="day_max"` the stub receives two `CalibrationEpisode`s, `sigma_hat = 0.0` and `sigma_true = 8.0` then `1.0`, with the `patient_id` and `day_index` of the days.
5. `test_b4_sample_unit_episodes_hand_computed`: the same days with `unit="sample"` give four episodes with `sigma_true` 2.0, 8.0, 1.0, 0.0. This variant is the classical time-step conformal anomaly detection and is labelled as such in the docstring (it does not follow rule 1 of the contract; `day_max` is the default).
6. `test_b4_alpha_allocation_hand_computed`: four monitored signals, `alpha = 0.2`, an allocation stub with `per_test(a, n) = a / n`: every calibrator is fitted with `alpha = 0.05`. Without an allocation each calibrator gets `alpha = 0.2`.
7. `test_b4_one_calibrator_per_signal`: the factory is called once per monitored signal; two signals with different preset quantiles give different alarm thresholds (units never pooled).
8. `test_b4_uses_only_public_calibrator_api`: the stub records only `fit` and `quantile` calls from B4 (no attribute access outside the `ConformalCalibrator` protocol).
9. `test_b4_placeholder_template_does_not_change_quantile`: with the real `SplitConformal`, episodes that differ only in the `template` placeholder give the same `quantile(alpha)`.
10. `test_b4_real_split_conformal_matches_definition`: four calibration days with residual magnitudes 1, 2, 3, 4 and `alpha = 0.25`: the threshold equals the value obtained by the rule documented in the `SplitConformal` docstring, derived by hand in the test (with the usual finite-sample rule, the `ceil(5 * 0.75) = 4`th smallest magnitude, that is 4.0); an alarm is raised for residual 4.5 and not for 4.0.
11. `test_b4_smaller_alpha_gives_subset_property` (Hypothesis): with the real calibrator, the detections at `alpha_1 < alpha_2` are a subset of the detections at `alpha_2` (wider interval, fewer alarms).
12. `test_b4_invariant_to_plan_parameters`: changing every `param_values` entry of the plan (bands, windows, limits) leaves the output unchanged; the plan and registry read logs are empty (B4 has no clinical specification; it uses no schedule either).
13. `test_b4_calibration_reads_observed_only`: after `fit` the `AccessLog` shows only `observed` reads under the default `AccessPolicy`.
14. `test_b4_ignores_evidence_and_never_labels`: identical output with and without an `EvidenceVector`; all labels `None`.
15. `test_b4_is_causal_property` (Hypothesis): detections with `t_ms <= T` are the same for the full day and for the day truncated to inputs with `t_rx_ms <= T`.
16. `test_b4_deterministic`: two fits on the same days give identical outputs; no randomness is used.

## Passi

1. Verify unblock conditions. Branch `ws06-t05-b4-conformal-only`; `status: in_progress`. Read the `SplitConformal` docstring: sign convention of `quantile`, quantile rule, whether `CalibrationEpisode.template` partitions the episodes.
2. Write the 16 tests; run them; watch them fail.
3. Implement `B4ConformalOnly(BaselineBase)` with `name = "B4"`, constructor arguments `forecaster`, `calibrator_factory` (default `SplitConformal`), `alpha`, `allocation` (optional `AlphaAllocation`), `signals` (default as in WS06-T03), `unit` (`"day_max"` default, or `"sample"`) and `timing`. `_fit`: fit the forecaster on observed train days; compute residuals on observed calibration days; build one `CalibrationEpisode` per (patient, day, signal) with `sigma_hat = 0.0` and `sigma_true` equal to the largest residual magnitude of that day (or one per residual for `unit="sample"`), so that the calibrator's one-sided quantile of `sigma_true - sigma_hat` is the quantile of residual magnitudes; call `fit(episodes, alpha_signal)` on a fresh calibrator per signal. `_run`: one detection per delivered sample whose residual magnitude exceeds `quantile(alpha_signal)`, score = magnitude divided by that quantile.
4. `CalibrationEpisode.template` is required and is a `TemplateId`, but B4 has no template. Use one module constant as a placeholder, documented as "ignored by the calibrator, one calibrator per signal", after checking in step 1 that `SplitConformal` does not partition by `template`. If it does, or if the `sigma_*` fields cannot carry a residual without changing the calibrator's meaning, do not edit the contract: describe the issue in the completion note and ask for an ADR.
5. Class docstring: what B4 knows (nothing clinical, no schedule) and what it cannot see by construction (event-driven obligations, dispenses, counts); `Hyperparameter selection`: `alpha` (and the optional allocation) is the operating parameter, swept by WS08 over the grid of the experiment config; the residual scale is estimated on calibration days only; coverage statements read "marginal over patient episodes under exchangeability", and calibration days are unlabelled, so injected anomalies contaminate the quantile (state this as a limitation shared with any conformal method that does not use labels).
6. Export from `__init__.py`; run `ruff format`, `ruff check src tests`, `mypy src/ralmon`, `pytest tests/baselines -q`; refactor.
7. Commit `WS06-T05: add B4 conformal-only baseline`; `status: done`; paste outputs in the completion note.

## Done when

- `pytest tests/baselines/test_b4_conformal_only.py -q` exits 0, and `pytest tests/baselines -q` still exits 0.
- `ruff check src tests` and `mypy src/ralmon` exit 0.
- `python -c "from ralmon.baselines import B4ConformalOnly"` exits 0.
- `grep -lE 'normalise|rank_alerts|load_templates|param_values|LatentDay|GroundTruthEvent' src/ralmon/baselines/b4_conformal_only.py` prints nothing.

## Notes

**Hand-over from WS05-T05 (forecaster, ADR-057).** The index of a `Forecast` path is `(t - t_from_ms) // step_ms - 1` (`mean[k]` predicts `t_from_ms + (k + 1) * step_ms`), not `floor((t - t_from_ms) / step_ms)` as the test text above writes it. The Protocol call `predict(history, t_ms, horizon_ms)` has no target signal: a baseline that needs a given signal must call the concrete class with the keyword `signal=` (or pass a history that holds one signal only). `supported_signals` and `model_version` exist on every forecaster; import the classes and `InsufficientHistoryError` from `ralmon.monitor`, which now lists them in the public API table.

### Hand-over (worker, 2026-10-10, from WS05-T06)

If this baseline works with an allocated level, take it from `BonferroniAllocation.per_test_exact(alpha_total, n_tests)` (a `Fraction`) and pass it to `fit`, `quantile` and `predict`: the float `per_test` can misrank (for example 0.05 / 3 on 59 scores gives `+inf` instead of 58). Levels given as floats are read as their decimal literal; a string or a bool is refused with `ValueError`. See ADR-058.
