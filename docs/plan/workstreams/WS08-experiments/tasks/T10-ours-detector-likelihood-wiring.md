---
id: WS08-T10
title: "OursDetector with the likelihood rule: alert_inputs, set_selector from calibrated sets, ours-hier and A4 variants, end-to-end run (ADR-074)"
workstream: WS08-experiments
owner: agent
status: in_progress
depends_on: ["WS08-T09", "WS05-T12", "WS05-T14"]
critical_path: true
non_negotiable: true
estimate_pd: 3
sources: ["ADR-074", "analisi §5.4", "analisi §5.6 (A4)"]
interfaces: ["02-interfaces.md#detector", "02-interfaces.md#alert", "02-interfaces.md#metrics"]
review_items: []
---
## Obiettivo

`OursDetector` (`src/ralmon/eval/ours.py`) still builds the hierarchical `RuleAttributor`, so no detector produces `Alert.p_kappa` or `Alert.cause_set` and the runner path of WS08-T09 is tested only with scripted stubs. Wire the proposed method of ADR-074: (1) `ours` builds the `LikelihoodRule` of WS05-T12 from `configs/attribution_likelihood.yaml` and the run option `sensitivity_values` (labelled sensitivity values; an `awaiting_human_value` row without a supplied value fails loudly) and exposes `alert_inputs(patient_id, alert)` (built with `alert_inputs_from_rule`) and `likelihood_rule`, keeping the evidence vectors it needs; (2) `ours-hier` is the same detector with the hierarchical rule (unchanged behaviour, `p_kappa` and `cause_set` None); (3) the `set_selector` of `RuleAttributor` is built from a `SubtypeSetCalibrator` fitted on the calibration part (patient-level split of the builder), with a separate instance for the confounder pairs; before a calibrator is fitted the selector is `cumulative_level_set` with the declared level; (4) the A4 variant (`ours-A4`): the witness cells removed and the robot-derived system fields `None` through the existing A4 mask; (5) the device profile of the run (`driver_with_diagnostics` / `without_diagnostics`, cuff resolution) reaches the extractor through `device_capabilities_from_manifest`; (6) `run_options.attribution` examples in `experiments/` configs (`loose_after_ms`, `set_alphas`, `pair_primary_templates`, `twins: separate`) as labelled test values for a smoke run, never as headline values.

## Contesto

WS08-T09 Notes (hand-over: what the runner expects from a detector), WS05-T12 Notes (how to build the rule with `sensitivity_values`, how to get `p_kappa`, `cause_set`, contributions), WS05-T14 Notes (calibrator API, model-version token, `top1_fill`), WS04-T18 Notes (profiles and manifest), `docs/models/attribution-likelihood.md`, `src/ralmon/eval/{ours,runner,attribution_sets,device_capabilities}.py`.

## File toccati

`src/ralmon/eval/ours.py`, `runner.py` (only if the wiring needs it), `tests/eval/` (create `test_ours_likelihood.py`), `tests/fixtures/eval/` (a mini benchmark config with test values), `experiments/` smoke configs.

## Test

1. `test_ours_emits_p_kappa_and_cause_set`: on the mini benchmark every VIOLATED alert of `ours` has `p_kappa` summing to 1 and a non-empty `cause_set`; `ours-hier` has both `None`.
2. `test_awaiting_value_fails_loudly_without_sensitivity_values`.
3. `test_sensitivity_values_are_recorded_in_the_metadata`.
4. `test_set_selector_uses_the_fitted_calibrator_and_refuses_a_stale_model_version`.
5. `test_pairs_use_a_separate_calibrator`.
6. `test_a4_variant_removes_witness_cells_and_robot_system_fields`.
7. `test_end_to_end_run_writes_the_new_metric_keys`: running the runner on the mini benchmark with `ours`, `ours-hier` and one baseline writes `attribution_log_score`, `attribution_brier`, `attribution_sets`, `attribution_equal_coverage`, `pair_llr` and `pair_direction_mcnemar` with non-null values for `ours` and `null` for the baseline.
8. `test_byte_identical_metrics_across_two_runs`.
9. `test_device_profile_reaches_the_extractor` (the cuff resolution of the manifest, `cuff_value_repeated` None when the profile has none).
10. `test_no_ground_truth_reaches_the_detector` (existing access guards remain).

## Passi

1. Tests first (red commit). 2. Likelihood wiring and the variants. 3. Calibrator selector. 4. Configs. 5. Notes for WS08-T02 and WS08-T04.

## Done when

- `pytest -q`, `ruff check src tests`, `ruff format --check src tests`, `mypy src/ralmon` exit 0.
- `python -m ralmon.eval.runner --config <the mini likelihood config> --output "$(mktemp -d)"` exits 0 and its `metrics.json` has the new keys with non-null values for `ours`.
- `python3 tools/check_plan.py` exits 0.

## Notes
