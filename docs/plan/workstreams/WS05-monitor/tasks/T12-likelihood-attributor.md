---
id: WS05-T12
title: "Likelihood attributor: posterior over C1, C2, C3 and Alert.p_kappa (ADR-074)"
workstream: WS05-monitor
owner: agent
status: in_progress
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

### Notes of the implementation (agent, 2026-10-12)

Delivered: `src/ralmon/attribution/likelihood.py` (`load_likelihood_table`, `LikelihoodTable`, `LikelihoodRule`, `AwaitingValueError`, `LikelihoodConfigError`, `LikelihoodInputError`), the `AttributionRule` Protocol with `posterior` and `posterior_subtypes` (`HierarchicalRule` returns `None` for both and gains the public `reading_class`), `Decision` with the probabilistic fields (all optional, default `None`), `RuleAttributor(..., set_selector=...)`, `alert_from_record` filling `Alert.p_kappa` and `Alert.cause_set`, the likelihood text in `render.py`, and `tests/attribution/test_likelihood_rule.py` (76 tests). The module is a submodule (`ralmon.attribution.likelihood`); `ralmon.attribution.__all__` is unchanged because it is bound to the contract table. No contract text changed (`#attribution` 0.3.0, `#alert` 0.3.0, `#evidencevector` 0.2.0 as bumped before); `Decision` is not a contract type.

#### Hand-over for WS08-T02 / WS08-T04 / WS08-T09

- **Build the rule.** `table = load_likelihood_table(<repo>/configs/attribution_likelihood.yaml)` (a path is required; there is no default location). `rule = LikelihoodRule(registry, table, sensitivity_values={...}, diagnostics_profile=<manifest.settings["device_profile"]["diagnostics_profile"]>, grouped_variant=None, a4=False)`. `registry` must carry the four thresholds of the reading classes (`hr_coherence_tolerance`, `ecg_sqi_floor`, `ppg_sqi_floor`, `ble_link_quality_floor`), as for `HierarchicalRule`. `sensitivity_values` maps the name of each awaiting row to a value: `eps`, `qc`, `q_stale`, `rep_nat`, `delta`, `dispense_bounce_interval_ms`, `tau`, `cumulative_level` (numbers) and `class_priors`, `pi_designs` (the NAME of a design of the file: `uniform`, `c1_heavy`, `c2_heavy`, `c3_rare`, `c3_heavy`; `uniform`, `quiet_rare`, `quiet_common`). Which names a run needs follows from the cells it reads: `q_stale` only with `driver_with_diagnostics`; `delta` not under A4; `cumulative_level` not with `needs_cumulative_level=False`. A missing name raises `AwaitingValueError` (`.names`), an unknown name or an out-of-domain value raises `LikelihoodConfigError`. The values are recorded, labelled "sensitivity, not a proposal", in `rule.metadata` (JSON-serialisable: write it next to the output). `grouped_variant` is `reference` (default, read from the file), `fully_independent` or `reference_plus_cross_device`.
- **Attributor.** `RuleAttributor(registry, templates, rule=rule)` gives `Alert.p_kappa` (keys C1, C2, C3), `Alert.cause_set` (cumulative-level set) and `Alert.xi.evidence_used`; `RuleAttributor(registry, templates)` is still `ours-hier` (p_kappa and cause_set `None`).
- **Conformal sets.** Build the rule with `needs_cumulative_level=False` (then `cumulative_level` is neither required nor used) and give the attributor a selector `(posteriors, template, instance_key) -> subtype names`, for example a closure over a fitted `SubtypeSetCalibrator`: `calibrator.predict_set(posteriors, template.value, alpha, patient_id=<patient of the day>, model_version=rule.model_version).subtypes`. `rule.model_version` is the token for `fit` and `predict_set` (hash of the file and of every option that changes p(s | e, t); `tau` and `cumulative_level` are not in it). Calibration alerts: `SubtypeCalibrationAlert(patient_id, template, rule.posterior_subtypes(record, evidence), true_subtype)`. The attributor refuses a selector result that is empty or not inside the applicable subtypes (`ValueError`), and refuses `needs_cumulative_level=False` without a selector.
- **Per-alert log-likelihood contributions.** Call `rule.decide(record, evidence)` with the record and the evidence the attributor used (pure and deterministic): `.contributions[component_id][field]` is log P(reading class | component) (a grouped cell is the key `"system.ble_link_quality+system.seq_gap"`; the sum over the fields of a component is log P(e | component)), `.class_contributions[class][field]` the log of the posterior-weighted mean of the class, `.posterior_subtypes`, `.p_kappa`, `.cause_set`, `.evidence_used`, `.abstention_threshold`. The alert itself does not carry them.
- **A4.** `a4=True` removes the cells of `masks.a4.cells_removed` (witness identity and intake, nav and manip task failure); the applicable subtypes do not change; the same `sensitivity_values` can be used (`delta` is then not needed).
- **Pair quantity.** `rule.log_likelihood_ratio(subtype_a, subtype_b, evidence)` (Lambda) and `rule.pair_statistic(subtype_a, subtype_b, evidence_member_a, evidence_member_b)` (D = Lambda_A - Lambda_B; exactly 0.0 on identical evidence). Prior-free: it uses neither the class priors nor the weights between subtypes; the subtypes need not be applicable at the template; two-level subtypes are mixed with the within-subtype weights of the pi design in force.
- **Evidence.** The rule trusts the vector: the extractor of the run must declare the same profile (`device_capabilities_from_manifest`), in particular `diagnostics` only for `driver_with_diagnostics`, `content_sensing` and `cuff_resolution`. Under `without_diagnostics` the rule does not read `system.diagnostics_ok` even if a vector carries it.

#### Judgment calls

1. **`posterior`/`posterior_subtypes` never raise on a normal vector; a provenance mismatch** (template kind not matching the template) makes `decide` return UNDETERMINED with no posterior (logged, like the hierarchical rule), while `posterior` and `posterior_subtypes` raise `LikelihoodInputError` (a `ValueError`).
2. **No default for `diagnostics_profile`** (required keyword). `grouped_variant` defaults to the reference declared in the file (`sensitivity_design`, entry `grouped_variant`, key `reference`), not to a constant of the code.
3. **Required parameters are those a live cell uses** (see the hand-over), not always all ten. This is stricter about nothing and avoids asking for a value that cannot change the result; the supplied-but-unused value is accepted and not recorded as used.
4. **Numerical domains.** Values must keep the logarithms finite: `0 < eps < 0.5`, `qc`, `q_stale`, `delta` in [0, 1], `0 <= rep_nat < 1`, `0 < tau <= 1`, `0 < cumulative_level < 1`, `dispense_bounce_interval_ms >= 0`. These are domain checks, not values. A cell that evaluates to a probability not strictly inside (0, 1) raises.
5. **`cumulative_set` is a local transcription of `ralmon.conformal.sets.cumulative_level_set`** (exact on the decimal literals), because `attribution` may not import `conformal` (`tests/test_layering.py`); a test compares the two on random posteriors. The conformal set joins through the injected selector.
6. **Cascade effects carry the `p_kappa` and the `cause_set` of their root**, like the attributed cause and the decisive evidence (the alert is about the root's cause); a predicted violation has `p_kappa` and `cause_set` `None` (CP13). WS08-T09 scores a `None` set as the full applicable set by its convention.
7. **`Explanation.evidence_used` for the likelihood rule is "the fields that FAVOUR the class with the largest posterior", not "the fields that decided kappa"** (fix round of 2026-10-13). A field is listed if the single-field log likelihood ratio between the posterior-weighted mean likelihood of its reading in that class and in the components of the other classes (weights: the component posteriors inside every class, the class posterior across classes) exceeds numerical zero 1e-12; most favourable first; both members of a grouped cell when they have readings. With a tie at the maximum there is no such class and the list is empty. The criterion is the worker's own and deterministic; the specification asks for "decisive fields" without defining them. `Decision.class_contributions` uses the same posterior weights. For C1 the text adds that silent faults raise none of the channels, so the attribution is not an exclusion of them. **Semantic note for the lead (contract / ADR, `Explanation.evidence_used` comment "EvidenceVector fields that decided kappa"): for a likelihood alert the field means "readings that pull towards the class with the largest posterior", traceability of the table, NOT a cause and NOT what decided the label (that is the posterior against tau); WS11 and WS12 must not read it as causal.**
8. **Tie at the maximum** uses numerical zero 1e-12 on the class posteriors (not exact float equality).
9. **Text of UNDETERMINED** names the full set of the applicable subtypes (the abstention at class level) AND the reported cumulative/conformal set, so the two statements do not contradict each other: the label abstains, the set says which subtypes are most probable. Both branches carry the sentence that the posterior is not a measured frequency; a tie names the tied classes ("C1 and C3 share the largest posterior") and calls no class "leading".
10. **Not implemented: the study switches `family` (catalogue vs benchmark_v1) and `cell_scope` (template vs all)** of `sensitivity_design`; the task did not ask for them. The rule uses the whole catalogue and the components that can violate the template. They are filters that can be added in the rule without touching the file.
11. **`reference_plus_cross_device`** is implemented (K = 8, `ecg_noise` applicable at `range`, `hold`, `resp`, `sys` with the modes of the file, weight of the default pi design); the test-local transcription of the specification does not cover it, so it is tested by normalisation and by applicability only.
12. **The grouped cell `ble_seq_gap` has `status: awaiting_human_value` in the file** (the modes of `message_drop`, `injection_naive` and `dispense_forgery_naive` are design choices that need gab) but no number of its own: the modes use `qc` and `1-qc`. It does not block construction; `rule.metadata["awaiting_groups"]` lists it, and `awaiting_cells` counts the awaiting cells of the file.
13. **Reading classes** reuse `HierarchicalRule` (new public method `reading_class`, wrapper of the private classifier), with F and G of the delivery ratio counted as D and K as unavailable; the three added classes are in `likelihood.py` (interval at or below `dispense_bounce_interval_ms` is A; `content_change == 0` is A; a negative or non-finite interval, a boolean or a non-finite content change is out of domain and read as unavailable, logged).

#### What a run still needs from gab

All ten names below have no value in the repository (`awaiting_human_value`); every test uses explicit TEST values from the sensitivity grid. A run must supply a labelled sensitivity value for: `eps`, `qc`, `q_stale` (driver profile), `rep_nat`, `delta` (not under A4), `dispense_bounce_interval_ms`, `tau`, `cumulative_level` (unless the conformal selector is used), the class prior design and the pi design. Open confirmations that change cells (not parameters): the modes of `message_drop`, `injection_naive` and `dispense_forgery_naive` in the grouped cell; the interval-chain coherence of the informed forger (ADR-074 amendment 4 (1)); ADR-075 (the hierarchical rule treats `system.seq_gap` differently from this table, by design).

#### Fix round after the independent review (2026-10-13)

- Decisive fields use posterior weights consistently (item 7 above); `Decision.class_contributions` likewise. Wording: text, docstrings and Notes say "evidence that favours".
- `family` and `cell_scope` are not implemented (judgment call 10); the hand-over lines are in the Notes of WS08-T09 and WS08-T02, with the cascade-effect remark.
- Seeded sweep against the test-local transcription extended (160 cases over eps, qc, q_stale, rep_nat, delta, the interval threshold, the five class-prior designs, the three pi designs, the three grouped variants, A4 and both diagnostics profiles). `reference_posterior` of `test_likelihood_spec.py` gained two optional arguments (`pi_weights`, `cross_device`) and stays independent of `likelihood.py` (no import of production internals); the existing spec tests are unchanged.
- `_needed` collects the names inside each token form; every live cell (and the default cell) is evaluated in `__init__`, so a missing name or a probability outside (0, 1) fails at construction (tests with a tampered copy of the YAML).
- `metadata["config_path"]` is the path from the `configs` directory (`configs/attribution_likelihood.yaml`), else the file name; `config_sha256` is unchanged.
- Left as asked: the `tau = 1.0` float edge and the existing hierarchical COUNT text.
