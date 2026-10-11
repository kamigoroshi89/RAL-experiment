---
id: WS08-T09
title: "Metrics for probabilistic attribution: log score, Brier, calibration curves, pair likelihood ratio, McNemar on direction (ADR-074)"
workstream: WS08-experiments
owner: agent
status: blocked
depends_on: ["WS08-T08", "WS02-T06"]
critical_path: true
non_negotiable: false
estimate_pd: 2
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
