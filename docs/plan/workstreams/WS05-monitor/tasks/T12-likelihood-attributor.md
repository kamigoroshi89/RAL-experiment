---
id: WS05-T12
title: "Likelihood attributor: posterior over C1, C2, C3 and Alert.p_kappa (ADR-074)"
workstream: WS05-monitor
owner: agent
status: ready
depends_on: ["WS02-T06", "WS05-T07", "WS05-T13", "WS05-T14"]
critical_path: true
non_negotiable: false
estimate_pd: 3
sources: ["ADR-074", "analisi §4.5", "analisi §4.9 (3)"]
interfaces: ["02-interfaces.md#attribution", "02-interfaces.md#alert", "02-interfaces.md#evidencevector"]
review_items: []
---
## Obiettivo

Implement the attribution of ADR-074 in `ralmon.attribution`: a `LikelihoodRule` that reads exactly the fields the hierarchical rule reads (invariant I1: no rho, no interval, no verdict state, no time of the record, no ground truth) and returns p(c | e, t), the per-field log-likelihood contributions (they feed `Explanation.evidence_used`), and `kappa` (argmax above the declared threshold, otherwise `UNDETERMINED`). `RuleAttributor` takes either rule; `Alert.p_kappa` is filled; the hierarchical rule stays selectable as `ours-hier`. The table, priors, mixtures and threshold come from `configs/attribution_likelihood.yaml` (WS02-T06); a row `awaiting_human_value` makes construction fail loudly unless the run option `sensitivity_values` supplies a labelled value.

## Contesto

`docs/models/attribution-likelihood.md` (WS02-T06), `docs/models/attribution-rule.md` (reading classes, relevance map, cascades, predicted violations: unchanged), `src/ralmon/attribution/{rule,attributor,render}.py`, ADR-074, the research prototype in `docs/benchmark/evidence/scripts/likelihood/`. The generator emits no driver `diagnostics` yet: that is WS04 work under ADR-074 (a switch in the benchmark config, two device profiles) and is NOT part of this task; this task works on whatever the extractor receives.

## File toccati

- `src/ralmon/attribution/likelihood.py` (create), `rule.py` and `attributor.py` (modify: the rule choice), `alert.py` (modify: `p_kappa`), `render.py` (modify: text states the probability and the decisive fields), `__init__.py`.
- `tests/attribution/test_likelihood_rule.py` (create); the existing attribution tests keep passing unchanged for `HierarchicalRule`.

## Test

1. `test_posterior_sums_to_one_and_respects_the_cells` (hand-computed example with three fields).
2. `test_none_reading_is_factor_one`: removing a field to `None` equals dropping its cell.
3. `test_diagnostics_ok_does_not_exclude_silent_faults`: with only `diagnostics_ok = True` and a violated RANGE instance, p(C2) stays above eps-scaled floor and p(C1) does not reach 1.
4. `test_prior_free_ratio`: the log likelihood ratio between two causes does not change with the priors.
5. `test_identical_evidence_gives_identical_posterior_for_two_instances` (determinism, no hidden state).
6. `test_threshold_gives_undetermined`: below the threshold kappa is `UNDETERMINED` and `p_kappa` is still filled.
7. `test_reads_only_the_relevance_map_fields`: a field outside the relevance map of the template cannot change the result.
8. `test_hierarchical_rule_unchanged` (the old golden cases still pass).
9. `test_a4_mask_removes_witness_likelihoods`: with the witness fields `None` the posterior equals the posterior of the table without the witness cells.
10. `test_awaiting_value_fails_loudly`.

## Passi

1. Tests first (red commit). 2. Likelihood module. 3. Wire into `RuleAttributor` and `Alert`. 4. Render text. 5. Notes for WS08-T02.

## Done when

- `pytest -q`, `ruff check src tests`, `ruff format --check src tests`, `mypy src/ralmon` exit 0.
- `python3 tools/check_plan.py` exits 0.

## Notes

### Amendment of 2026-10-11 (gab; ADR-074, amendments 1 to 3)

The rule works at the level of SUBTYPES: it returns the posterior over the subtypes (explicit pi(subtype | class) priors with sensitivity), the class posterior as their sum (`p_kappa`), and the prediction SET of subtypes (cumulative level or the conformal threshold of WS05-T14); `kappa` is the derived label; UNDETERMINED is the full set of the subtypes applicable at the template. It reads the fields of `#evidencevector` 0.2.0. Add tests: `test_class_posterior_is_the_sum_of_subtype_posteriors`, `test_set_is_full_set_when_evidence_is_empty`, `test_prior_weights_inside_class_are_explicit_parameters`.

### Hand-over from WS05-T13 (`#evidencevector` 0.2.0, 2026-10-11)

- The extractor has two new profile parameters: the capability `content_sensing` of the dispenser (without it `dispenser.content_change` is `None`) and `DeviceCapabilities.cuff_resolution` of the cuff (without it `signal_quality.cuff_value_repeated` is `None`; no default anywhere). The cuff resolution the generator rounds to (WS04-T18) must be the same value that the run's `DeviceProfile` gives the extractor.
- The extractor computes the dispenser group and `cuff_value_repeated` for EVERY template; it does not gate them by data scope. The relevance map of the likelihood attributor MUST mask them: the dispenser group is read for `hold`, `count`, `resp` and `int` (the templates whose data scope holds the dispenser); `cuff_value_repeated` for the templates that read a cuff measurement (`range`, `sched`, `hold`, `resp`, `sys`). Masking is a cell rule of WS02-T06, not an extractor feature.
- A re-sent copy of a frame (the same `(name, seq)` again) is not a reading and not an opening: both fields skip it, while `crypto_temporal.seq_repeat` still reports it. The latest accepted `bp` reading must lie in the evidence window or `cuff_value_repeated` is `None`.
- For the renderer: `FIELD_WORDS` in `src/ralmon/attribution/render.py` has an entry for every field; `_BOOLEAN_WORDS` and `_CONFLICT_WHY` have the two sequence fields. `cuff_value_repeated` and the dispenser fields have words in `FIELD_WORDS` only (no reading words): add them there if the likelihood alert text should state them.

### Hand-over from WS04-T18 (device profile of the generator, 2026-10-11)

- The run must give the extractor the cuff resolution of the benchmark; use `ralmon.eval.device_capabilities.device_capabilities_from_manifest(manifest, base)` (WS04-T18, fix round), which sets `cuff_resolution` (= `manifest.settings["device_profile"]["cuff_resolution_mmhg"]`), `content_sensing`, `authenticates` and `diagnostics` from the manifest and keeps the rest of `base` (default 1.0; `null` in a benchmark built without rounding: then do not declare it). A benchmark built before WS04-T18 has no such key and must be regenerated.
- Two named diagnostics profiles are recorded as `settings.device_profile.diagnostics_profile`: `without_diagnostics` (no `diagnostics` report: declare no `diagnostics` capability on the cuff and the dispenser, so `system.diagnostics_ok` is `None`) and `driver_with_diagnostics` (declare it for the nodes in `settings.device_profile.driver.devices`, default `cuff` and `dispenser`; the reports are `ok` or `stale`, never `warn` or `error`). Declaring it on a benchmark without reports would still give `None` (no report is never read as `ok`), but the run should follow the manifest.
- Fields with real values now: `signal_quality.cuff_value_repeated` (natural repeat probability about 0.02 at 1 mmHg: 0.0223 measured over 4448 pairs, 0.0204 by formula; a generator property), `dispenser.interval_since_previous_ms` (int, absent for the first opening of a day, the bounce reports its gap, a forged opening reports the interval the stream gives), `dispenser.content_change` (before minus after, present only if the build has `dispenser_content_sensing`, the committed default has false; declare `content_sensing` on the dispenser capability accordingly), `system.diagnostics_ok` (stale only for a lost message beyond the lease; never under C1 events; silent faults leave it `ok`).
- A `stuck_at` window that starts before the first reading of the day repeats the last reading of the PREVIOUS day: the extractor already compares across the day boundary (D-16); a monitor or baseline that resets each day does not see it.
- Sessions of the driver derive from what the device SENT (WS04-T18): `stale` is in practice a `ble_dropout` signal and `P(stale | cuff_detached) = 0` is a property of the generator; a requested but unanswered measurement is never `stale`. A forged `DISPENSE` of the informed level re-chains the interval of the next genuine opening (coherent attacker), a naive one does not.

### Hand-over from WS02-T06 (specification delivered, 2026-10-12)

Read `docs/models/attribution-likelihood.md` (normative) and load `configs/attribution_likelihood.yaml`. What to implement:

- `posterior_subtypes(violated, evidence) -> Mapping[str, float]` (probabilities over the subtypes applicable at the template; components, i.e. subtype at a knowledge level, are internal and merged), `posterior(...)` as the class sum (`Alert.p_kappa`, keys C1, C2, C3), `Alert.cause_set` (subtype names by decreasing probability, ties by name, to `cumulative_level`; replaced by the conformal threshold of WS05-T14). Contract `#attribution` 0.3.0 and `#alert` 0.3.0 are already bumped; `Alert.cause_set` exists (default `None`) in `src/ralmon/attribution/alert.py`; the `AttributionRule` Protocol in `rule.py` still has only `attribute` and must gain `posterior` and `posterior_subtypes` here (the hierarchical rule returns `None`).
- Fields read: `templates.<t>.reads` of the YAML (relevance map plus the masks: dispenser group for `hold`, `count`, `resp`, `int`; `signal_quality.cuff_value_repeated` for `range`, `sched`, `hold`, `resp`, `sys`; witness only at `resp`). Reading classes: those of `HierarchicalRule._readings` plus the three added in the document (interval at or below `dispense_bounce_interval_ms` is A; `content_change == 0` is A; `cuff_value_repeated` True is A). A `None`, out-of-domain or K reading is skipped (factor 1).
- Cells: for a (component, field) pair look up `cells` (key `component`, `field`); evaluate `cell_tokens[token].form` with the parameters; an unlisted pair is the default cell (`eps`). Parameters `eps`, `qc`, `q_stale`, `rep_nat`, `delta`, `dispense_bounce_interval_ms`, `tau`, `cumulative_level`, the class prior design and the `pi` design are `awaiting_human_value`: construction fails loudly unless the run option `sensitivity_values` supplies a labelled value (test 10).
- Applicable components: `components[*].templates`; a class with none at the template has prior 0 (`templates.<t>.impossible_classes`: C1 at `sys`, `int`). `ecg_noise` and `out_of_order` are applicable nowhere (they are only the common cause of the grouped variant).
- `diagnostics_profiles`: with `without_diagnostics` the field is `None` (not read); with `driver_with_diagnostics` use the `S` cells. A4: `masks.a4.cells_removed`.
- Grouped cells. The pair (`system.ble_link_quality`, `system.seq_gap`) is ONE joint cell in the REFERENCE (`grouped_cells.ble_seq_gap`, `reference_mode: grouped`; ADR-074 amendment 3, ADR-075): replace the two factors with `P(joint | s) = sum over modes m of weight(m) * [(1-eps) 1(j=m) + eps/(K-1) 1(j!=m)]`, K = 4, summing over a `None` member (factor 1 when both are `None`); the `cells` entries of the two fields are the marginals of the fully independent variant. `fully_independent` (two factors) is the labelled sensitivity option; `cross_device_signal_quality` (K = 8, with `ecg_noise` as common cause) is the only variant that relaxes independence further and is off in the reference. Option name `grouped_variant`: `reference`, `fully_independent`, `reference_plus_cross_device`.
- `kappa`: largest `p_kappa` if at least `tau`, else `UNDETERMINED`; a tie is `UNDETERMINED`. Add the test-local transcription in `tests/attribution/test_likelihood_spec.py` as a cross-check (hand example at `count`: only `authenticated` asserted, eps 0.01, uniform: p(C3) = 0.970732).

### Hand-over from WS05-T14 (conformal set calibrator delivered, 2026-10-12)

`ralmon.conformal.sets` (import from the module; the names are not in `ralmon.conformal.__all__`, see the Notes of WS05-T14):

- `posterior_subtypes` must return only the subtypes APPLICABLE at the template, summing to 1 within 1e-9 (`PosteriorError` otherwise). The full-set fallback of the calibrator is the keys of that mapping.
- Fixed set (no calibration): `cumulative_level_set(posteriors, level)`; `level` has no default.
- Calibrated set: `SubtypeSetCalibrator("marginal" | "mondrian", population="main" | "pairs", min_cell_size=None)`, `.fit([SubtypeCalibrationAlert(patient_id, template, posteriors, true_subtype), ...], model_version=token, test_patient_ids=...)`, `.predict_set(posteriors, template, alpha, patient_id=..., model_version=token)` returns an `AttributionSet` whose `.subtypes` is the value for `Alert.cause_set`.
- Define the model-version token of the posterior model (suggestion: content hash of `configs/attribution_likelihood.yaml` plus the run options that change the posterior) and expose it, so that `fit` and `predict_set` get the same string; a mismatch raises `StaleSetCalibratorError`.
- `ralmon.attribution` imports `ralmon.conformal`? Not allowed by the layering today (`attribution` depends on `signals`, `spec`, `monitor`); the adapter that joins the attributor and the set calibrator therefore lives in `baselines`/`eval` (WS08-T01 `OursDetector`), not in the attributor.
