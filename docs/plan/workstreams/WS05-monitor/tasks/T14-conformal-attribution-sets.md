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

### Implementation notes (worker, 2026-10-12; status left `in_progress` for review)

Code: `src/ralmon/conformal/sets.py`; tests: `tests/conformal/test_sets.py` (46 tests: the 8 of the task, the cumulative-level set, validation of posteriors, degenerate inputs, determinism). Judgment calls:

1. **Names are not exported from `ralmon.conformal.__all__`.** `tests/test_public_api.py::test_dunder_all_equals_contract_names` requires `__all__` to equal the table "Package public API" of `02-interfaces.md`; adding names is a contract change (table bump 0.2.2 to 0.2.3, ADR needed) and the task forbids contract changes without an ADR. `__init__.py` is therefore untouched; import from `ralmon.conformal.sets`. If the owner wants the names at the package root: propose an ADR and a table bump (names: `SubtypeSetCalibrator`, `SubtypeCalibrationAlert`, `AttributionSet`, `SetThreshold`, `prediction_set`, `cumulative_level_set`, `nonconformity_score`, and the errors). The `ralmon.conformal` layering is respected (sets.py imports only `ralmon.conformal.scores`).
2. **Level-agnostic `fit`, like `SplitConformal`.** `fit(examples, *, model_version=None, test_patient_ids=None)` stores the sorted scores; the level `alpha` (run parameter, no default) is an argument of `threshold(template, alpha)` and `predict_set(..., alpha, ...)`, so one fit serves the sweep alpha in {0.2, 0.1, 0.05}. The fallback depends on alpha (rank above n), so it is reported by `threshold`, not by `fit`.
3. **Fallback of a cell.** A cell falls back to the full set (threshold +inf, `fallback=True`, a `reason` string) when it has no calibration alert, when its rank exceeds n (fewer than `ceil(1/alpha) - 1` alerts), or when it has fewer than the optional `min_cell_size` (no default; without it only the rank condition applies, so no number is invented). The full set is the KEYS of the posterior, i.e. the subtypes applicable at the template, as `posterior_subtypes` returns them (WS05-T12 must pass only applicable subtypes; a subtype with probability 0 that is a key is still in the full set).
4. **Never-empty set.** The pure rule (every subtype with score at most the threshold) can be empty when no subtype is probable enough; `Alert.cause_set` is never empty (`#alert`), so `predict_set` returns the most probable subtype (ties by name) and sets `top1_fill=True`. This can only raise coverage; the coverage test measures the pure rule (`prediction_set` with the threshold) and asserts that the filled coverage is at least that. `prediction_set` itself is the pure rule and may return `()`. The research prototype did not fill; the metrics of WS08-T09 should report how often `top1_fill` happens (about 3% at alpha 0.2 on the synthetic fixture).
5. **Scores are doubles `1.0 - p`; ranks are exact** (`exact_level`, `upper_quantile` of `scores.py`, ADR-030). No 1e-12 tolerance as in the prototype (`q + 1e-12`): membership is `1.0 - p <= threshold`, exact between doubles from the same expression, so a posterior equal to the one of the threshold alert is inside. `cumulative_level_set` sums the decimal literals (`repr`) of the posteriors exactly against the level read the same way (0.7 + 0.2 reaches 0.9).
6. **Patient-wise split is enforced at three points:** `fit(..., test_patient_ids=...)`, `require_disjoint(ids)`, and `predict_set(..., patient_id=...)` (keyword-only, mandatory) which refuses a calibration patient. All raise `PatientLeakError` (a `ValueError`), naming up to five shared ids.
7. **Posterior validation** (`PosteriorError`): non-empty, finite, each in [0, 1], sum 1 within `POSTERIOR_SUM_TOLERANCE = 1e-9` (a floating-point tolerance for a softmax, not a modelling value). A calibration alert with a bad posterior is reported with its patient id.
8. **Model-version token.** `calibrated_for` is set by `fit(..., model_version=...)`; `predict_set` takes a mandatory keyword `model_version` (the version of the posterior model in use) and `check_fresh(model_version)` raises `StaleSetCalibratorError` on a mismatch or when `calibrated_for is None`, the rule of `Predictor.check_fresh` and B4/B5. `StaleCalibratorError` of `ralmon.monitor` cannot be imported here (layering), hence its own class. WS05-T12 should define the token of the posterior model as the content hash of `configs/attribution_likelihood.yaml` plus the run options that change the posterior (grouped variant, diagnostics profile, pi design, scope); any change of those requires a refit.
9. **Guarantee strings** `GUARANTEE_SETS`, `GUARANTEE_SETS_MONDRIAN`, `ASSUMPTIONS_SETS` travel on every `AttributionSet`, as `Rho.guarantee` does for the predictive calibrator.

Not done by design: wiring `AttributionSet.subtypes` into `Alert.cause_set` is the job of the attributor/adapter (WS05-T12, WS08-T01), because `ralmon.conformal` may not import `ralmon.attribution` (the step 3 of the task is satisfied on the contract side: the field exists and the set is a `tuple[str, ...]` ready for it). Coverage per patient (cluster bootstrap), the equal-coverage comparison and `top1_fill` frequency are WS08-T09 metrics.
