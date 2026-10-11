---
id: WS08-T09
title: "Metrics for probabilistic attribution: log score, Brier, calibration curves, pair likelihood ratio, McNemar on direction (ADR-074)"
workstream: WS08-experiments
owner: agent
status: blocked
depends_on: ["WS08-T08", "WS02-T06", "WS05-T14"]
critical_path: true
non_negotiable: false
estimate_pd: 3
sources: ["ADR-074", "analisi §5.5"]
interfaces: ["02-interfaces.md#metrics"]
review_items: []
---
## Obiettivo

Add to `ralmon.eval` what ADR-074 (3) and (4) require. (1) On the main population: the log score and the Brier score of `Alert.p_kappa` against the cause of the matched ground-truth event, PER TEMPLATE (equal-weight aggregate, RESP apart, as in ADR-072), with calibration curves (reliability bins with counts) per template. (2) On the confounder pairs: for each member, the log likelihood ratio between the two causes of its group, `Lambda = log P(e | c_A) - log P(e | c_B)`, computed from the per-field contributions of the alert (prior-free); in the indistinguishable stratum the distribution of `|Lambda|` and its distance from 0; in the distinguishable stratum the correct direction of each member, the pair statistic `D = Lambda_A - Lambda_B`, and McNemar between methods on the direction (b = X right and Y not, c = the reverse, exact binomial on b + c). No precision on pairs. (3) `#metrics` 0.2.0: new keys in `metrics.json` (`attribution_log_score`, `attribution_brier`, `attribution_calibration_curve`, `pair_llr`, `pair_direction_mcnemar`); a method without `p_kappa` (B1 to B5) gets `null`. The definitions are also written into the metric list of WS08-T02 and the README of WS08.

## Contesto

ADR-074, ADR-072 (b), `docs/models/attribution-likelihood.md`, `docs/benchmark/evidence/likelihood-attribution.md`, `src/ralmon/eval/metrics.py`, `runner.py`, WS08-T08 (per-template layout), `/tmp/research/pairs-allocation.md` section 5 (pair quantities; the pair-specific matching: the alert of the relevant template decided after the onset).

## File toccati

`src/ralmon/eval/metrics.py`, `runner.py`, `pairs.py` (create), `tests/eval/test_probabilistic_attribution.py` (create), `tests/fixtures/eval/` (hand-written cases), `docs/plan/02-interfaces.md` (`#metrics` 0.2.0), `docs/plan/workstreams/WS08-experiments/README.md` (key list).

## Test

1. `test_log_score_and_brier_hand_values` (three alerts with known p_kappa and causes).
2. `test_per_template_and_equal_weight_aggregate_without_resp`.
3. `test_calibration_curve_counts_per_bin` (bins with n = 0 are reported empty, not 0 accuracy).
4. `test_llr_is_prior_free`: changing the priors does not change Lambda.
5. `test_identical_streams_give_zero_llr` (indistinguishable stratum).
6. `test_direction_and_pair_statistic`.
7. `test_mcnemar_exact_on_discordant_pairs` (hand-computed b, c, p).
8. `test_methods_without_p_kappa_are_null`.
9. `test_no_ground_truth_in_the_attributor` (the metric code reads the truth, the attributor cannot).

## Passi

1. Tests first. 2. Per-template scores. 3. Pair module. 4. Runner keys and README.

## Done when

- `pytest tests/eval -q` and `pytest -q` exit 0; `ruff check src tests`, `ruff format --check src tests`, `mypy src/ralmon` exit 0.
- `python3 tools/check_plan.py` exits 0.

## Notes

### Amendment of 2026-10-11 (gab; ADR-074, decision 1)

Add to the metrics: set coverage (the true subtype is in the set) and mean set size, per stratum and per template; the pair likelihood ratio is taken between the two specific subtypes, not between classes. Tests: `test_set_coverage_and_size_hand_values`, `test_pair_llr_between_subtypes`.

### Amendment of 2026-10-11 (gab; ADR-074, amendments 2 and 3)

(1) Methods are compared AT EQUAL COVERAGE by mean set size: each method's sets are calibrated (WS05-T14) to the same target on the calibration part (patient-level split of the builder) and compared on the test part; the hierarchical rule's kappa as a set (kappa -> all subtypes of its class; UNDETERMINED -> all applicable) and a prior-only baseline are included. (2) The pairs get a SEPARATE calibration (50% prevalence); report also the transfer from the main population to show why. (3) Truth: the TIGHT causal labelling is primary; the looser labelling is reported next to it in every table, and the metadata states that the choice was made after seeing the result (ADR-074 amendment 2). (4) Coverage is reported marginal, per template, per true cause and per patient (cluster bootstrap); the metadata carries the exchangeability statement. Tests: `test_equal_coverage_comparison_hand_values`, `test_pair_calibration_is_separate`, `test_both_labellings_are_reported`, `test_coverage_per_patient_cluster_bootstrap`.

### Hand-over from WS02-T06 (specification delivered, 2026-10-12)

Read `docs/models/attribution-likelihood.md`: the pair quantity is Lambda_M = log P(e_M | s_A) - log P(e_M | s_B) at the common template with D = Lambda_A - Lambda_B (indistinguishable stratum: D = 0 exactly; distinguishable: Lambda_A > 0 and Lambda_B < 0 and McNemar on the direction); the labelling to score is the TIGHT one (a C2 event causes an alert only if the faulty device is in the data scope of the template and the alert is decided while the event window is active), the looser labelling is printed next to it in every table, and the report states that the choice was made after seeing the result (ADR-074 amendment 2). A method without sets (`ours-hier`, B1-B5) that abstains is scored as the FULL set of the subtypes applicable at the template (`components[*].templates` of `configs/attribution_likelihood.yaml`). The sensitivity design to sweep is `sensitivity_design` of that file (eps, qc, q_stale, rep_nat, delta, T_b, class priors, pi designs, cumulative level, tau, grouped variant, diagnostics profile, cell scope, family, labelling). Known failure modes to report: C1 against `cuff_silent_bias` at `range` has ratio exactly 1, and indistinguishable pairs have D = 0; do not describe the coverage of the conformal sets as distribution-free.

### Hand-over from WS05-T14 (conformal set calibrator delivered, 2026-10-12)

`from ralmon.conformal.sets import SubtypeSetCalibrator, SubtypeCalibrationAlert, AttributionSet, cumulative_level_set` (not in `ralmon.conformal.__all__`).

- Calibrate on the calibration patients of the builder's patient-level split: `cal = SubtypeSetCalibrator("marginal" | "mondrian", population="main")`; `cal.fit(alerts, model_version=token, test_patient_ids=test_patients)` (refuses an overlap). `fit` is level-agnostic: one fit serves every alpha; the thresholds are read with `cal.threshold(template, alpha)` (`SetThreshold`: value, n, fallback, reason, cell) and `cal.cell_sizes()`.
- THE PAIRS GET A SEPARATE INSTANCE: `SubtypeSetCalibrator(..., population="pairs")` fitted on the calibration part of the pair population (never on the main population). To show why, also evaluate the main-population instance on the pairs (the transfer) and report it next to the separate one.
- `predict_set(posteriors, template, alpha, patient_id=..., model_version=token)` returns `AttributionSet`: `subtypes`, `threshold`, `full_set_fallback`, `fallback_reason`, `top1_fill`, `cell`, `n_calibration`, `guarantee`, `assumptions`. Report the share of alerts with `full_set_fallback` and with `top1_fill` per template (a fallback inflates the mean set size; a fill raises coverage above the pure conformal rule).
- Coverage per patient with the cluster bootstrap (resampling patients) and the equal-coverage comparison are this task; the calibrator does not compute them. The guarantee strings are on every `AttributionSet`; copy them into the metadata and do not write "distribution-free coverage" without the qualification (marginal, patient-level exchangeability, alerts of a patient correlated).
- The method without sets (`ours-hier`, B1-B5) that abstains is the full set of the applicable subtypes; the calibrator does not apply to it. `cumulative_level_set(posteriors, level)` is the non-conformal set (levels 0.8, 0.9, 0.95 are sensitivity values).

- Wording of the guarantee (WS05-T14 fix round): the rank argument needs exchangeable alerts; patient-level exchangeability alone does not give it when a patient contributes several correlated alerts; the bound is exact only for one designated alert per patient; otherwise coverage is approximate and is checked empirically here (role-swap check, cluster bootstrap over patients, coverage per patient); ties make it conservative. Copy `AttributionSet.guarantee` and `assumptions` into the metadata as they are.
- `population` is only a label: nothing stops the "main" instance from predicting a pair alert. The separate instance for the pairs is the caller's discipline (fit on the pair calibration part, call on pair alerts).
- Report fallbacks PER TEMPLATE (`full_set_fallback`, `fallback_reason`, `top1_fill`). A template name that is mistyped, or not seen in calibration, silently becomes the full set of the applicable subtypes in the Mondrian variant; it is flagged by `fallback` and `reason`, so a table with an unexpected fallback share points to it.
- Writers must convert: `AttributionSet.threshold` and `SetThreshold.value` are `math.inf` for a fallback (`inf` is invalid JSON; write null plus the `fallback` flag) and `AttributionSet.alpha` is a `Fraction` (write the decimal string or a float).
- Measured fill frequency of the empty-set rule on the synthetic test generator (seed 20261012, 80 x 300): 5.4% at alpha 0.2 and 0.27% at alpha 0.1; report the real one per template.
