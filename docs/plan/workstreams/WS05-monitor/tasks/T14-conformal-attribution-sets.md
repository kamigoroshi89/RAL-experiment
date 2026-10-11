---
id: WS05-T14
title: "Conformal calibration of attribution sets (patient-level split, Mondrian per template)"
workstream: WS05-monitor
owner: agent
status: in_progress
depends_on: ["WS05-T06", "WS02-T06"]
critical_path: true
non_negotiable: false
estimate_pd: 2
sources: ["ADR-074"]
interfaces: ["02-interfaces.md#conformal-calibrator", "02-interfaces.md#alert"]
review_items: []
---
## Obiettivo

Implement in `ralmon.conformal` the calibration of the prediction SETS of the subtype posterior (ADR-074 amendment 1 and 2): nonconformity score of an alert = 1 - p(true subtype | e, t); threshold from the calibration part by the split-conformal quantile with the finite-sample correction, at a target level alpha (run parameter); marginal and per-template Mondrian variants; the set of a test alert = every subtype whose score is below the threshold; a cell with too few calibration members falls back to the full set of the applicable subtypes and says so. Calibration and test are separated PATIENT-WISE (the split of the builder). A separate calibrator instance is used for the confounder pairs (prevalence 50%, different template mix). Honest wording: the guarantee is marginal and holds only if calibration and test are exchangeable at patient level; alerts of one patient are correlated; coverage is also reported per patient (cluster bootstrap); the phrase 'distribution-free coverage' is not used without that qualification.

## Contesto

ADR-074, `docs/benchmark/evidence/likelihood-attribution.md` sections 9 and 10 (the prototype and its numbers; research code in `docs/benchmark/evidence/scripts/likelihood/`), WS05-T06 (`ralmon.conformal`, `per_test_exact`), WS02-T06 (the table and the subtype catalogue).

## File toccati

`src/ralmon/conformal/sets.py` (create), `src/ralmon/conformal/__init__.py`, `tests/conformal/test_sets.py` (create).

## Test

1. `test_quantile_with_finite_sample_correction` (hand-computed small case).
2. `test_set_contains_subtypes_below_threshold`.
3. `test_mondrian_cell_with_few_members_falls_back_to_full_set`.
4. `test_calibration_and_test_patients_are_disjoint` (refuses a calibration set that shares a patient with the test set).
5. `test_separate_calibrator_for_pairs_is_a_separate_instance`.
6. `test_coverage_on_exchangeable_synthetic_scores` (seeded; coverage within the binomial interval of 1 - alpha).
7. `test_calibrator_refuses_a_model_version_mismatch` (like the other calibrators).
8. `test_no_ground_truth_import_in_the_set_builder` (only the calibration function takes truth subtypes, as an argument).

## Passi

1. Tests first. 2. Calibrator. 3. Wire the output into the alert (`Alert.cause_set`, additive, with the contract bump of WS02-T06).

## Done when

`pytest -q`, `ruff check src tests`, `ruff format --check src tests`, `mypy src/ralmon` exit 0; `python3 tools/check_plan.py` exits 0.

## Notes

### Hand-over from WS02-T06 (specification delivered, 2026-10-12)

`Alert.cause_set: Sequence[str] | None = None` is already in `src/ralmon/attribution/alert.py` and in `#alert` 0.3.0. Subtype names are those of `configs/attribution_likelihood.yaml` (`subtypes[*].name`, 35 names); the posterior over them is `posterior_subtypes` of WS05-T12 (document `docs/models/attribution-likelihood.md`, section Sets and conformal calibration): score = 1 - p(true subtype | e, t), threshold = the `ceil((n+1)(1-alpha))`-th smallest calibration score (full set if the rank exceeds `n`), set = subtypes with score at most the threshold, marginal and Mondrian per template, the pairs calibrated separately. An alert whose true subtype is not applicable at the template has p = 0 and score 1. State the guarantee as marginal under patient-level exchangeability, never as a distribution-free coverage statement without that qualification; report coverage per patient with a cluster bootstrap. The cumulative-level set of the table is the fallback (`cumulative_level`, awaiting_human_value, range 0.8, 0.9, 0.95).
