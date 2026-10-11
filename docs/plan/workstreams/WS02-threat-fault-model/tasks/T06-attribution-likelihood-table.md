---
id: WS02-T06
title: "Attribution as a likelihood table: specification, cells with their source, sensitivity design (ADR-074)"
workstream: WS02-threat-fault-model
owner: agent
status: done
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

### Hand-over from WS05-T13 (`#evidencevector` 0.2.0, 2026-10-11)

The extractor computes the dispenser group and `signal_quality.cuff_value_repeated` for every template and does not gate them by data scope. The table must list the masking as a cell rule: the dispenser fields are read only for `hold`, `count`, `resp` and `int`; `cuff_value_repeated` only for the templates that read a cuff measurement (`range`, `sched`, `hold`, `resp`, `sys`); for the other templates the cell is not read. A cell for `cuff_value_repeated` is also `None`-aware (no declared display resolution, no previous reading, or the latest reading outside the evidence window).

### Hand-over from WS04-T18 (device profile of the generator, 2026-10-11)

- **Profiles in the manifest.** `settings.device_profile` of a benchmark records: `cuff_resolution_mmhg` and `pulse_resolution_bpm` (default 1.0 and 1.0; `null` = unrounded, the benchmarks before T18), `dispenser_reports_interval` (true), `diagnostics_profile` (`without_diagnostics` or `driver_with_diagnostics`) and `driver` (`null`, or `{period_ms, stale_lease_ms, devices, activity_modes}`). The two diagnostics profiles are the two cases of the cells for `system.diagnostics_ok`; the lease and the period are `awaiting_human_value` rows (`driver_stale_lease_ms`, `driver_period_ms`) and a build with the diagnostics profile is refused while they are.
- **Fields that now carry real values.** `signal_quality.cuff_value_repeated`: True for a `stuck_at` window (frozen values repeat exactly after rounding), and a natural repeat probability of about 0.02 under no fault at 1 mmHg (a property of this generator and its noise: 0.0223 measured on 4448 pairs, 0.0204 by the formula E[max(0, 1 - |delta|/r)] on the unrounded readings; not a device constant; the cell `rep_nat` is a sensitivity parameter). `dispenser.interval_since_previous_ms`: an integer, absent for the first opening of a day (about half of the `DISPENSE` events, 0.47 to 0.51 in the 40 x 7 builds, carry it), the bounce reports its gap, a forged `DISPENSE` reports the interval the stream gives at its onset, measured from the latest opening that reached the gateway (at a bounce gap after a real opening it reads like the bounce). The INFORMED forger is coherent on the chain (the opening after its forged one reports the interval since it, as its twin would: the informed noauth pair variants stay indistinguishable, an assumption recorded in WS04-T18), the NAIVE forger is not (the next genuine opening is measured from the previous genuine one, so a naive forgery in place of a first dose leaves it without an interval). `dispenser.content_change`: before minus after (+1.0 release, 0.0 bounce), present only when the build says `dispenser_content_sensing` (the committed `default.yaml` has false: the main population has `None`, the pair variants with content have it); a forged `DISPENSE` has no `content_change`. `system.diagnostics_ok`: `ok` or `stale` only (no `warn`, no `error`).
- **What `stale` means in these data.** Only a device that was expected to publish (a measurement started, an opening made) and whose message was lost on the link, beyond the lease and until the link is reported active again. So a C1 event never causes a `stale` report (a refusal, an omission or a double take sends nothing; in a 40 x 7 build every day with a stale report had a realised `ble_dropout` of that device), and `P(stale | C1)` is the chance that a dropout of an unrelated device coincides with the alert, a small cell (`eps`), and `P(stale | ble_dropout)` is NOT near 1: a dropout of an idle device loses nothing and reports nothing, and a dropout shorter than the lease leaves `ok`. Silent faults (`cuff_silent_bias`, `stuck_at`, `dispenser_bounce`) leave `ok`. `cuff_detached` leaves `ok` too (its failed attempts are messages). The fault-model signatures were not changed; the stale path of `ble_dropout` is conditional on the profile.
- The lease must exceed the cuff's nominal start-to-reading time (the committed `inflation_ms_nominal` is 30 s), or every reading shows a short `stale` (a profile error, not a fault).
- Sessions of the driver are a modelling choice (WS04-T18, fix round): they derive from what the device SENT, so a requested but unanswered measurement (silent detachment, a cuff that never answers) is never `stale`; `stale` is in practice a `ble_dropout` signal and `P(stale | cuff_detached) = 0` here is a property of the generator, not of the contract (a real driver that tracks requests would report it).

### Worker notes (2026-10-12): what was done, judgment calls, open points

Deliverables: `docs/models/attribution-likelihood.md`, `configs/attribution_likelihood.yaml` (86 explicit cells, 38 components, 35 subtypes), `tests/attribution/test_likelihood_spec.py` (20 tests), contract bumps `#alert` 0.3.0 (`Alert.cause_set`, ADR-074 amendment 1) and `#attribution` 0.3.0 (`posterior_subtypes`), `Alert.cause_set` in `src/ralmon/attribution/alert.py` (additive, default `None`), the pointer in `attribution-rule.md`. The task text said "bump to 0.2.0"; `#alert` and `#attribution` were ALREADY 0.2.0 (ADR-074 commit), so the minimal consistent bump is 0.3.0 for both; test 6 of the task therefore checks 0.3.0 and that `p_kappa` and `cause_set` are the last two fields.

Judgment calls (each is a candidate for the lead's ADR; none changes a frozen signature other than the additive ones above):

1. **Template reach follows the fault model, not the prototype.** The fault model says `ecg_noise` violates no template, so it is applicable nowhere (kept in the catalogue; it enters only as the common cause of the grouped cross-device variant); `out_of_order` likewise. The C2 subtype at `sys` is `cuff_detached` only (fault-model variant G-SYS-3, a conditional reach); the prototype had `ecg_noise` at `sys`. `process_kill`, `uncommanded_lifecycle_transition`, `message_drop` (also `range`, `int`), `link_delay` (`int`), `battery_depleted`, `clock_skew` follow the "Effects on templates" table (the prototype restricted some to fewer templates). Numbers of the report therefore do not carry over unchanged.
2. **`system.diagnostics_ok` stale cell is conditional (`S`, parameter `q_stale`, range = the `qc` grid)** for `ble_dropout`, `message_drop`, `process_kill`, `uncommanded_lifecycle_transition`; the prototype's `1-eps` is outside the range (WS04-T18: P(stale | dropout) is not near 1). `P(stale | cuff_detached) = 0` stays a generator property.
3. **Catalogue of C1:** the five injected subtypes, `dose_omission`, and `spontaneous_<template>` for the five C1-capable templates (the labeller's rule); `spontaneous_sched` is new relative to the prototype (added to the quiet C1 group). C1 diversion cell (`delta`) only on the C1 subtypes readable at `resp`.
4. **Levels are components** (replay, dispense_forgery, presence_spoof naive/informed): `uniform` is uniform over components, as in the prototype, so a two-level subtype weighs twice a one-level one. Whether the reference should be uniform over subtypes is a point for gab; it changes the set and the posterior, not the likelihood ratio between two specific subtypes.
5. **`stuck_at` / `cuff_value_repeated`:** REP conditions availability, not value; cell `R` (`1-eps`) given a reading. Every other subtype applicable at a cuff template has the natural cell `N` (`max(rep_nat, eps)`), 30 explicit cells.
6. **Source types:** the allowed set is fault-model row, threat-model row, device specification, literature (needs `bib_key`; none used), design choice. `threat_model_row` is added to the four of the task text because the C3 cells come from the threat model. No row cites the literature.
7. **Grouped variants** re-express the prototype's G1 on the split fields (`ble_seq_gap`: four joint classes clean/gap/degraded/gap_degraded, modes from `qc`; `cross_device_signal_quality`: eight joint classes plus `ecg_noise` as co-occurrence component). The modes for `message_drop`, `injection_naive`, `dispense_forgery_naive` are inherited from the prototype and are design choices needing gab.
8. **`kappa` tie** at the maximum is `UNDETERMINED` (design choice); the `UNDETERMINED` set is the full set `full_set(t)` for methods that abstain; the table's own set is the cumulative-level set.
9. The reading classes for the three new fields are defined in the document (interval at or below T_b; `content_change` equal to 0 is A; `cuff_value_repeated` True/False/None). `dispense_bounce_interval_ms` is a proposed registry name (ADR-032), not yet a registry entry.
10. The test-local `reference_posterior` in `test_likelihood_spec.py` transcribes the pseudo-code to check a hand-computed example (count template, only `authenticated` asserted, uniform design, eps 0.01: p(C3) = 0.970732); it is not importable from `ralmon` and is not production code.

Awaiting rows by who must decide (counts over the 64 awaiting cells; plus the parameter and design rows `eps`, `qc`, `q_stale`, `rep_nat`, `delta`, `dispense_bounce_interval_ms`, `tau`, `cumulative_level`, `class_priors`, `pi_designs`, the two grouped cells, and `driver_stale_lease_ms`, `driver_period_ms` of `generator_design.yaml`): gab (witness cells of C3 when co-located, 3; D-5 lateness, 2; identity check, 1; naive stamps, 1; pulse not patched, 2; `qc`, `tau`, `cumulative_level`, class priors, `pi` designs, grouped cells); literature (the diversion share `delta`, 2 cells); device specification (LC 9, SEQ 6, natural repeat 30, DSP 1, STALE 4, link degradation 1, device target 1, ECG quality index 1; `eps`, `q_stale`, `rep_nat`, `dispense_bounce_interval_ms`, the driver lease and period).

### Hand-over to WS05-T12, WS05-T14, WS08-T09

Written in their Notes (see those files). Common facts: read `configs/attribution_likelihood.yaml` (keys `templates.<t>.reads`, `components`, `cells`, `cell_tokens`, `default_cell`, `masks`, `grouped_cells`, `diagnostics_profiles`, `parameters`, `class_priors`, `pi_designs`); evaluate a cell as `cell_tokens[token].form` over the named parameters (`eps`, `qc`, `q_stale`, `rep_nat`, `delta`); a pair without a cell entry is the default cell `Z` (`eps`).

### Fix round after the independent review (2026-10-12)

- **B1.** The pair (`system.ble_link_quality`, `system.seq_gap`) is ONE joint cell in the REFERENCE (`grouped_cells.ble_seq_gap.reference_mode: grouped`), as ADR-074 amendment 3 and ADR-075 require; the fully independent product is the labelled sensitivity variant, `cross_device_signal_quality` is the only independence-relaxing variant (off in the reference). Sensitivity `grouped_variant`: `reference`, `fully_independent`, `reference_plus_cross_device`. This replaces judgment call 7 above ("variants") and the line "off by default" of the WS05-T12 hand-over, which is corrected. The explicit `cells` of the two fields are their marginals (used by the fully independent variant; source record of the modes).
- **I1.** The reads table of the document has its header and separator again; a test parses it and compares it with `templates.*.reads`.
- **I2.** The joint formula is written (`P(j | s) = sum_m weight(m) [(1-eps) 1(j=m) + eps/(K-1) 1(j!=m)]`, K = 4 for the pair, K = 8 for the cross-device group, as `_jdist` of the prototype with eps/3); the cross-device group has its None rule (summed over the unavailable members); a test checks that every joint sums to 1 for every component and every pattern of available members, at three eps and three qc values.
- **I3.** `crypto_temporal.timestamp_implausible` of `clock_skew`, `out_of_order` and `timestamp_manipulation` is a conditional cell (token C, condition BOUND, awaiting, sensitivity range = the `qc` grid) instead of `1-eps`; the failure modes say these three are outside benchmark v1. Counts are now: 86 cells = 19 structural + 67 awaiting (29 C + 2 Cn + 4 S + 2 V = 37 conditional, 30 natural-repeat N); the reviewer's 22/64 became 19/67 because of this change. `needs` of the BOUND cells: device_specification (D and skew_max are run parameters).
- **I4.** The body states ADR-075 (proposed, DA-CONFERMARE), ADR-074 amendment 4 (the informed forger coherent on the interval chain, the all-zero C3 interval cells rest on it; the alternative would make about 7 of 16 forged-first-dose pairs of each informed noauth variant distinguishable; the naive forger is not coherent) and the sessions modelling choice.
- **I5.** The pair quantity names the within-subtype level weights: the pi design in force; the reference is `uniform` over components, a declared reference design awaiting gab.
- **Minor.** Status table recounted (37 conditional cells, 30 natural-repeat cells); the catalogue wording counts `double_take` once; the dead awaiting cells are listed and pinned by a test (`presence_spoof` naive identity at `int`, `out_of_order`, the two `ecg_noise` cells); `message_drop` independent-versus-joint difference and the `replay` naive `system.seq_gap` zero versus H-SUPP are in the failure modes; cell counts are pinned exactly (86, by status and by token; the original `> 100` floor does not apply because the config has 86 cells); the number whitelist is positional (a number under `templates.range` fails) with a test on a tampered copy. Item not done: none.
