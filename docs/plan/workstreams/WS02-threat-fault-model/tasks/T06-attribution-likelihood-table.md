---
id: WS02-T06
title: "Attribution as a likelihood table: specification, cells with their source, sensitivity design (ADR-074)"
workstream: WS02-threat-fault-model
owner: agent
status: blocked
depends_on: ["WS02-T04", "WS02-T05", "WS05-T13"]
critical_path: true
non_negotiable: false
estimate_pd: 2
sources: ["ADR-074", "analisi §4.5"]
interfaces: ["02-interfaces.md#attribution", "02-interfaces.md#alert"]
review_items: []
---
## Obiettivo

Specify the attribution layer of ADR-074: the method returns p(c | e, t) for c in {C1, C2, C3}, computed from a likelihood table P(reading class of field f | c) and a prior per template, with `UNDETERMINED` derived from a declared threshold. Concrete output: `docs/models/attribution-likelihood.md`, the machine-readable table `configs/attribution_likelihood.yaml`, the contract bumps in `docs/plan/02-interfaces.md` (`#attribution` 0.2.0, `#alert` 0.2.0: `Alert.p_kappa`) and a completeness test. No number is invented: structural cells are written `1 - eps` / `eps` with `eps` a parameter; every other cell is an `awaiting_human_value` row with a sensitivity range and the source it would have to come from.

## Contesto

- `docs/plan/03-decisions.md` ADR-074 (read in full) and ADR-010; `docs/models/attribution-rule.md` (reading classes, relevance map, exclusion conditions, worked cases W-01 to W-15), `docs/models/fault-model.md` (coverage table around lines 395-418: which fields each fault raises; the silent faults raise none), `docs/models/evidence-channels.md`, `docs/models/threat-model.md`.
- The research prototype and its report: `docs/benchmark/evidence/likelihood-attribution.md` (written by the research run of 2026-10-11 from `/tmp/research/likelihood-attribution.md`; copy it to the repository first, with its scripts under `docs/benchmark/evidence/scripts/likelihood/`, if the copy is not there yet).
- Sensitivity design in the report: eps grid, priors (uniform and declared alternatives), within-C2 subtype mixture (share of silent faults), abstention threshold, one grouped-field variant for the channels that are not independent given the cause (`ble_link_quality` with `system.seq_gap` (contract 0.2.0 split of `seq_gap_or_replay`, WS05-T13); `cross_device` with the signal-quality fields).

## File toccati

- `docs/models/attribution-likelihood.md` (create).
- `configs/attribution_likelihood.yaml` (create: cells, priors, mixtures, threshold; each with `source`, `status`, `sensitivity_range`).
- `docs/plan/02-interfaces.md` (modify: `#attribution` 0.2.0 adds `posterior(violated, evidence) -> Mapping[AttributedCause, float]` to the rule protocol; `#alert` 0.2.0 adds `p_kappa: Mapping[AttributedCause, float] | None` as the last field, default `None`; the hierarchical rule stays the reference rule).
- `docs/models/attribution-rule.md` (modify: a pointer to the new document and the statement that the table is the reference rule, `ours-hier`).
- `tests/attribution/test_likelihood_spec.py` (create).
- `docs/plan/workstreams/WS05-monitor/tasks/T12-likelihood-attributor.md`, `WS08-experiments/tasks/T09-probabilistic-attribution-metrics.md` (Notes only, to say what changed).

## Test

1. `test_every_read_field_has_a_cell_for_every_cause`: for each template, each field of its relevance-map row (E, s, b, q, r) has a cell for each of C1, C2, C3 and for each of the classes A and D, and a cell row sums to 1 over the classes of that field.
2. `test_structural_cells_use_eps_and_no_literal_probability`: a cell is `eps`, `1-eps`, a mixture expression over the declared subtypes, or `awaiting_human_value`; no bare number other than 0 and 1 in the exclusion of eps.
3. `test_silent_faults_do_not_zero_diagnostics_ok`: with the fault model's silent faults in the C2 mixture, `P(diagnostics ok | C2)` is strictly greater than `eps`.
4. `test_unavailable_contributes_one`: a `None` reading has no cell and the specification states the factor 1.
5. `test_every_cell_names_its_source_and_status`: source is one of fault-model row, device specification, literature (with a verified bibliography key), design choice; `verified_by` is null unless the human recorded it.
6. `test_contract_versions_bumped`: `#alert` and `#attribution` read 0.2.0 and cite ADR-074; the `p_kappa` field is last and optional.
7. `test_sensitivity_design_is_listed`: the document lists eps, priors, mixtures, threshold and the grouped-field variant, each with a range.

## Passi

1. Tests first (red commit).
2. Cells from the fault-model coverage table and the relevance map; priors and mixtures as declared design choices with alternatives.
3. The abstention threshold as a parameter; the derivation of `kappa` from `p_kappa`.
4. Contract bumps and the pointer in `attribution-rule.md`; Notes in the dependent tasks.

## Done when

- `pytest tests/attribution/test_likelihood_spec.py -q` exits 0.
- `python3 tools/check_plan.py` exits 0.

## Notes

### Amendment of 2026-10-11 (gab; ADR-074, decision 1)

The output is a set of SUBTYPES (cumulative probability level, sensitivity value) and the cells are at subtype level; the table gives pi(subtype | class) as explicit priors with sensitivity; `p_kappa` is the class-level sum. Add a contract field for the set (`Alert.cause_set`, additive) in the same contract bump. Metrics: coverage and mean set size per stratum (WS08-T09).

### Amendment of 2026-10-11 (gab; ADR-074, amendment 3)

The cells use the fields of `#evidencevector` 0.2.0 (WS05-T13): the dispenser group, `crypto_temporal.seq_repeat`, `system.seq_gap`, `signal_quality.cuff_value_repeated`. `system.seq_gap` and `system.ble_link_quality` form ONE grouped cell (they overlap). The contract bump of `#evidencevector` is NOT made here (WS05-T13); this task bumps `#alert` (`cause_set`) and `#attribution`. The truth used for the scoring of cells and metrics is the TIGHT causal labelling (a C2 event is the cause of an alert only if the faulty device is in the data scope of the template and the alert is decided while the event window is active); the looser labelling is reported next to it.
