---
id: WS08-T02
title: "Main experiment: B1-B5 versus proposed method"
workstream: WS08-experiments
owner: agent
status: blocked
depends_on: ["WS08-T01", "WS06-T07"]
critical_path: true
non_negotiable: false
estimate_pd: 2.5
sources: ["analisi §5.4", "analisi §5.5", "analisi §5.1", "analisi §10 (1)", "analisi §10 (2)", "analisi §4.5"]
interfaces: ["02-interfaces.md#metrics", "02-interfaces.md#detector"]
review_items: ["R3-W1", "R3-W6", "AE-1"]
---
## Obiettivo

Run the main experiment: baselines B1 to B5 and the proposed method (`ours`) on the same benchmark, the same patient-level splits and the same seeds, with the metrics of analisi §5.5, and produce the honest-reporting diagnostics of the README (rules H2, H3, H8, H9): the B5 failure analysis, the per-subtype breakdown with every row of the diagnosability matrix (including the undetectable rows), the tolerance sensitivity, the alert load and the non-circularity audit. Concrete output: `experiments/main.yaml`, `src/ralmon/eval/analysis.py`, and `outputs/main/<seed>/{config.yaml, metrics.json, git_rev.txt}` for at least five seeds, checked by `python -m ralmon.eval.analysis --check outputs/main`. This closes R3-W1 and AE-1 (no validation) and R3-W6 (alert load) for the synthetic benchmark.

## Contesto

- `docs/plan/workstreams/WS08-experiments/README.md`: layout, conventions E1 to E10, honest-reporting rules H1 to H9, `run_options.required_analysis`.
- `02-interfaces.md#detector` and `02-interfaces.md#metrics`; `docs/source/analisi.md` §5.4 (B5: show where it fails: sparse sampling, mixed units, no attribution) and §10 objections 1 and 2.
- WS06-T06 (B5 failure analysis) and WS06-T07 (fairness audit) completion notes; `configs/diagnosability.yaml` (WS02-T05) and `configs/registry/hypertension.yaml` (WS01-T03).
- `docs/plan/workstreams/WS00-admin/outputs/WS00-T07.md` (clinician-supplied shift length, if any).
- Blocked until WS08-T01 and WS06-T07 are `done`. Do not start if the WS06-T07 audit lists an open finding.

## File toccati

- `experiments/main.yaml` (create): detectors `["B1", "B2", "B3", "B4", "B5", "ours"]`, seeds `[0, 1, 2, 3, 4]`, `headline: true`, the values chosen in step 3 with a rationale in the header comment.
- `src/ralmon/eval/analysis.py` (create): `subtype_breakdown`, `undetectable_rows`, `b5_failure`, `tolerance_sensitivity`, `alert_load`, `non_circularity`, `hooks_for`, and the `--check` command.
- `tests/eval/test_analysis.py` (create).
- `tests/eval/test_main_experiment.py` (create).
- `tests/fixtures/eval/main/` (create): a two-row diagnosability fixture, matchings built by hand, a fixture access log.

## Test

Write these first. Values are fixtures, not results.

`tests/eval/test_analysis.py`

1. `test_subtype_breakdown_row_per_subtype_and_detector`: 3 subtypes and 2 detectors give 6 rows, each with `n_events` and recall as a scalar with interval.
2. `test_undetectable_rows_flagged_and_kept`: with a diagnosability fixture whose rows DX-04 (silent bias, 4 events, 1 matched) and DX-10 (informed injection, 2 events, 0 matched) are declared not distinguishable, the report keeps both, marks `declared_not_distinguishable: true` and shows recall 0.25 and 0.0.
3. `test_matrix_row_without_events_is_listed`: a matrix row with no event in the test split appears with `n_events: 0` and recall `null`.
4. `test_missing_matrix_row_raises`: a ground-truth subtype with no matrix row raises `MatrixCoverageError` naming the subtype.
5. `test_b5_failure_records_delta_and_interval`: with a planted gap (B5 detects 0 of 10 events in the blood-pressure-driven stratum, ours 8 of 10) the condition `sparse_sampling` has `delta_recall` 0.8, a paired interval above 0 and `b5_worse: true`; a stratum with equal results has `b5_worse: false`.
6. `test_b5_failure_found_false_is_reported_explicitly`: when no condition has an interval excluding 0, `b5_failure_found` is `false` and `note` says no measured condition shows B5 worse.
7. `test_b5_no_attribution_is_structural`: `attribution_confusion["B5"]` is `None` and the `no_attribution` condition has `structural: true`.
8. `test_b5_mixed_units_stratum_uses_template_units`: patient-days with at least two violated instances whose templates have different `RobustnessUnit` form the `mixed_units` stratum; on a two-day fixture only the day with `MMHG` and `MS` templates is in it.
9. `test_tolerance_sensitivity_three_windows`: factors 0.5, 1, 2 give `tolerance_ms` of half, once and twice the configured value; on a fixture with detections at +400 ms and +900 ms and tolerance 1_000, recall is 0.5, 1.0, 1.0.
10. `test_alert_load_per_patient_day_and_shift`: 24 alerts over 3 patient-days give 8.0 per patient-day; with `shift_hours = 8` (test input only) 8.0 x 8 / 24 = 2.667 per shift; with `shift_hours = None` the per-shift value is `null`.
11. `test_alert_load_by_verdict_and_class`: 6 PREDICTED_VIOLATION and 18 VIOLATED alerts are counted separately, and by attributed cause including UNDETERMINED.
12. `test_non_circularity_counts_reads`: an access log with zero latent or ground-truth reads at inference gives `latent_reads_at_inference: 0` and passes; one planted read makes the check fail with the detector name.
13. `test_check_cli_reports_missing_required_keys`: `--check` on a directory whose `metrics.json` lacks `analysis.b5_failure` exits non-zero and names the key and the seed.

`tests/eval/test_main_experiment.py`

14. `test_main_yaml_loads_and_resolves`: `experiments/main.yaml` loads through `load_experiment`; detectors equal `["B1", "B2", "B3", "B4", "B5", "ours"]`; seeds are at least five unique integers; `headline` is true; split fractions sum to 1; `required_analysis` lists the six analysis keys `subtype_breakdown`, `undetectable_rows`, `b5_failure`, `tolerance_sensitivity`, `alert_load` and `non_circularity`.
15. `test_main_alpha_grid_supports_calibration_size`: the smallest alpha of the grid is at least `1 / (n_cal + 1)` for the calibration episode count computed from the manifest and the split.
16. `test_main_smoke_on_fixture_benchmark`: running the main configuration with the fixture benchmark and one seed writes the three files and has entries for all six detectors under every metric key that applies (`null` for attribution and coverage of B1 to B3).
17. `test_baselines_share_clinical_knowledge_with_ours`: the registry version in `meta` and in each detector's recorded parameter reads (WS06-T01 read log) is the same for B1, B3, B5 and `ours`.

## Passi

1. Verify the unblock conditions; read the WS06-T06 failure-analysis conditions and the WS06-T07 audit; read the diagnosability schema (WS02-T05) and the WS00-T07 shift length. Branch `ws08-t02-main-experiment`; set `status: in_progress`.
2. Write the tests. Run `pytest tests/eval/test_analysis.py tests/eval/test_main_experiment.py -q`; confirm they fail. Commit `WS08-T02: add failing tests for analysis and main config`.
3. Choose the configuration values before looking at any test-split result (rule E9), using only the registry, the manifest and the train and calibration splits: split fractions (the calibration split must give enough episodes for the smallest alpha, rule E6); `alpha` and the alpha grid; `tolerance_ms` (at least the largest verdict-latency bound of the windowed templates from the registry plus the forecast horizon of WS05-T05, so that early warnings can match); `time_reference: first_decidable`; monitor step and reorder delay (from WS05 and WS07); `n_bootstrap` and `ci_level`. Write each value with its rationale in the header comment of `experiments/main.yaml`. Confirm the manifest records 200 patients x 7 days (analisi §5.1 scale).
4. Implement `analysis.py`: the six analyses, `hooks_for("main")`, and `--check` (reads `run_options.required_analysis` from the `config.yaml` of each seed and verifies the keys). Strata for B5 come from `Template.signals` (blood pressure is the sparse signal) and `Template.unit`; the conditions and their order are those of WS06-T06. Tests 1 to 17 pass.
5. Run `python -m ralmon.eval.runner --config experiments/main.yaml --output outputs` (five seeds). Run `python -m ralmon.eval.analysis --check outputs/main`.
6. Read the results against the honest-reporting rules before accepting them: (a) H2: is there a condition where B5 is worse? If not, record `b5_failure_found: false` and flag it for WS12-T03 and WS12-T07; do not weaken B5. (b) H3: if `ours` or any baseline detects DX-04 or DX-10 events at a rate that contradicts "not distinguishable by construction", investigate leakage (a detector reading latent data, evidence not derived from the observed trace) before accepting. (c) H9: compare false alarms per patient-day on the synthetic test split with the alert-load sanity check of WS04-T12 and note the difference. (d) Read the tolerance sensitivity and state whether the ranking of methods changes at half and double tolerance.
7. Write the completion note: config values and rationale, per-method headline numbers with intervals, the B5 finding, the undetectable rows with measured values, alert load, and the deviations from the upstream assumptions. Run the Done when commands, commit `WS08-T02: add main experiment and analysis`, set `status: done`.

## Done when

- `pytest tests/eval -q` exits 0, `ruff check src tests` exits 0, `mypy src/ralmon` exits 0.
- `for s in 0 1 2 3 4; do for f in config.yaml metrics.json git_rev.txt; do test -f outputs/main/$s/$f || echo "missing $s/$f"; done; done` prints nothing.
- `python -m ralmon.eval.analysis --check outputs/main` exits 0.
- `grep -c '"b5_failure_found"' outputs/main/0/metrics.json` prints 1 and `grep -c 'declared_not_distinguishable' outputs/main/0/metrics.json` prints at least 2.

## Notes

### Hand-over (worker, 2026-10-09, from the WS05-T04 review, round 2)

No INT-based result on a generated day is evidence until ADR-054 is decided (the presence level of the last robot visit is read at every later dispense when the trace has no availability mark and no zero). Gate on `run_offline_detailed(...).stats.presence_samples_without_availability_marks`: it must be 0 (or the trace must carry the explicit zeros of option (a)), and report it when it is not. `presence_level_older_than_window_steps` is information only and is positive even on a correct trace, because a robot visit (10 minutes in the generator) is longer than `int_window` (5).

### Hand-over (worker, 2026-10-10, from WS06-T06)

B5 is built as `B5ConformalSTL(templates, registry, forecaster, calibrator_factory, *, alpha, aggregation, timing, plan_for_day, evaluator_factory=None)`: the runner must supply `plan_for_day` (care plan of an observed calibration day), the same forecaster class and training days as `ours`, a `TimingConfig` whose `tail_ms` covers the longest window and the reorder delay, and both aggregations (`"conjunction"` is named `B5`, `"per_template"` is named `B5-per-template`). B5 is stepped on the device-time grid (detection time `t_eval_ms + D`). Detections are not nested in `alpha`; a sweep trades lead time, not the set of detected events. The benchmark-scale numbers of `notes/B5-failure-analysis.md` (recall on C1, C2, C3 per B3, B4, B5; the fraction of patient-days on which the predictive part of B5 emitted anything, from `B5ConformalSTL.predictions`; the median `quantile` against the band margin; `n_censored`) were not measured in WS06-T06 and are this task's to add. The mixed-units failure does not show in the predicted decision of B5 as configured (only RESP has a predictive part); expect it in the score and the ranking, and say so if `b5_failure_found` rests on it.

### Open decision for gab (D2) (worker, 2026-10-10, review round 1)

As implemented to the task text (test 15), the predictive part of B5 is nearly vacuous for this problem: only RESP is predicted, from about five blood-pressure samples per day, which the contract itself expects to be a useless prediction target (`02-interfaces.md#forecaster`, Targets in scope), so B5 reduces to B3 plus a rarely firing RESP test. The proposed method also predicts SCHED (`DeadlineForecaster`, WS05-T05). A reviewer may call this a straw man. The recommended remedy is a B5 variant that completes SCHED with the `DeadlineForecaster`, changing D2 and test 15 together; it would also make the mixed-unit masking of a predicted alert reproducible at the level of the decision (two predictive templates then share a pooled constant). It is not implemented here, because it changes the task text. WS08-T02 must not present B5 results as the B5 comparison for the paper until gab decides.

Also recorded for WS08. D10: the per-test level of B5 is `alpha`, that of the proposed method `alpha / n_tests`; the direction of the net effect is ambiguous (a larger level fires more, but B5 has fewer tested instances), so WS08 should also run B5 at `BonferroniAllocation.per_test_exact(alpha, n_tests)`; no code change is needed, B5 accepts a `Fraction` as `alpha`. D4: running the literal rule of the paper (alert unless satisfaction is certified, score `R = rho_hat - rho_true`) is a cheap WS08 variant.

### Hand-over (worker, 2026-10-10, from WS06-T04)

B3 is built as `B3PlainSTL(templates, registry, *, timing, evaluator_factory=None)` (no forecaster, calibrator, `alpha` or other operating parameter; `fit([], [])` is enough; `tail_ms` of the `TimingConfig` must cover the longest window). Detection time is `t_eval_ms + D`; scores are minus the raw robustness in the unit of each template, so rank B3 only within a template. After each `run` read `b3.run_stats` and `b3.int_gate_passed`: while the generator emits no `NODE_STATE colocated` report (WS04-T11) the gate is positive and INT-based results are not evidence. B3 and B5 do not detect most INT violations whatever the gate (the point evaluator has no value when the monitor decides from the sign of an interval bound; Notes of WS06-T04): do not present C3 recall of B3 or B5 against `ours` until gab decides the point-evaluator extension. B5 now applies the `colocated` reports as well (same `SignalGrid`).
