---
id: WS05-T12
title: "Likelihood attributor: posterior over C1, C2, C3 and Alert.p_kappa (ADR-074)"
workstream: WS05-monitor
owner: agent
status: blocked
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
