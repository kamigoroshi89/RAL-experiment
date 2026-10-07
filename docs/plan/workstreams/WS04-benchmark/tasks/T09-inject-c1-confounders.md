---
id: WS04-T09
title: C1 injection and deliberate confounders
workstream: WS04-benchmark
owner: agent
status: ready
depends_on: ["WS04-T07", "WS04-T08"]
critical_path: true
non_negotiable: false
estimate_pd: 2
sources: ["analisi §5.1 (3, 4)", "analisi §4.5 (matrix rows 2, 6, 7, 9)", "analisi §2 R3 weakness 4"]
interfaces: ["02-interfaces.md#trace-schema"]
review_items: ["R3-W4"]
---
## Obiettivo

Complete the latent day and add the C1 injections of analisi §5.1 (3): hypertensive spikes, drug non-response (reduced Emax), hypotension below the hold parameter, and patient measurement refusal. Then build the **deliberate confounders** of §5.1 (4) as matched pairs that share the same base day and seed and differ only in the labelled mechanism: real non-response versus forged dispense, double take versus sensor bounce, and (from R3-W4, a third group added by this plan) patient measurement refusal versus robot no-show. C1 injections change the latent day; they produce injection records, never ground-truth events, because C1 truth is computed by the labeller on the latent trace (T10). The pairs include variants that are observationally identical once the discriminating channel is withheld, so that abstention can be scored. Concrete output: `inject_c1.py`, `confounders.py`, `latent_day.py`, the C1 and confounder parts of `injections.yaml`, tests.

## Contesto

- `docs/source/analisi.md` §5.1 (3) (C1: "picchi ipertensivi, non-risposta (Emax ridotto), ipotensione sotto l'hold parameter, rifiuto della misura") and (4) (confounders), §4.5 matrix rows 2, 6, 7, 9 (which evidence separates each pair) and `docs/source/review.md` R3 weakness 4 (double take versus sensor bounce; a missed measurement is often C2, not a physiological C1).
- `02-interfaces.md#trace-schema` (`GroundTruthEvent.confounder_group`, `injected`, `template_id`).
- WS04-T03 (latent pressure), WS04-T04 (`intake_scales`), WS04-T05 (behaviour, forced states), WS04-T06 (`ObservedStream`, `vocab.py`), WS04-T07 and WS04-T08 (`injection.py`, injectors, capability sets).
- `docs/models/evidence-channels.md` and `configs/diagnosability.yaml` if they exist (rows DX-02, DX-06, DX-07, DX-09; gap G-1 on dispenser content sensing).
- `docs/plan/workstreams/WS04-benchmark/README.md` (confounder groups and vocabulary).

Unblocked when WS04-T07 and WS04-T08 are `done`.

## File toccati

- `src/ralmon/benchmark/inject_c1.py` (create).
- `src/ralmon/benchmark/confounders.py` (create).
- `src/ralmon/benchmark/latent_day.py` (create: assembly of the complete `LatentDay`).
- `src/ralmon/benchmark/vocab.py` (modify: robot task outcome for a declined measurement).
- `configs/benchmark/injections.yaml` (modify: C1 section, confounder variant grid).
- `tests/benchmark/test_c1_confounders.py` (create).

## Test

Fixture-only values: constant baseline SBP 130 with zero AR noise; one dose at 08:00; PK/PD fixture of T04 (`ka = 2 per h`, `ke = 1 per h`, `Emax = 20 mmHg`, `EC50 = 0.25`); intake lag 5 000 ms. Write first.

1. `test_hypertensive_spike_adds_magnitude_inside_window_only`: a spike of 40 mmHg over `[t1, t2)` gives 170 inside and 130 outside, exactly.
2. `test_hypotension_pulse_subtracts_magnitude`: magnitude 40 gives 90 inside, 130 outside.
3. `test_drug_nonresponse_scales_emax_for_intakes_in_window`: the effect at `t_max` is 13.3333333 unscaled, 6.6666667 with scale 0.5 and 0 with scale 0; an intake outside the window keeps its full effect.
4. `test_measurement_refusal_removes_latent_and_observed_measurement`: the latent MEASUREMENT event at the tick is absent; the observed stream has the robot visit and a declined-task event and no `bp` sample.
5. `test_c1_injectors_return_records_not_ground_truth`: the C1 entry point returns `InjectionRecord` values with `cls = C1` and no `GroundTruthEvent` is constructed in `inject_c1.py` (checked by an AST scan).
6. `test_latent_day_has_no_observation_only_fields`: the assembled `LatentDay` contains no `cuff_health`, `inflation_ms`, `presence`, no `quality`, and only the event kinds DISPENSE, INTAKE, MEASUREMENT (ideal) and SCHEDULE_TICK.
7. `test_latent_measurements_at_scheduled_ticks_with_exact_values`: latent MEASUREMENT events sit exactly at the schedule ticks and the latent `bp` value at a tick equals the held latent trace value.
8. `test_assembly_without_injections_equals_baseline_minus_effect`: bit-for-bit equality with `compose_latent_sbp(baseline, pkpd_effect)` (paired baseline, T03 and T04).
9. `test_forced_double_take_matches_markov_double_take`: forcing the double-take state for a slot produces the same latent events as the chain in that state with the same gap.
10. `test_magnitude_levels_are_relative_to_named_reference`: a spec level 2 with reference quantity 20 mmHg resolves to 40 mmHg; the YAML contains no absolute mmHg magnitude for C1 (fixture check of the file structure).
11. `test_double_take_vs_bounce_pair_shares_base_and_seed`: both variants have equal latent baseline, cuff noise draws and schedule; only the mechanism differs.
12. `test_double_take_vs_bounce_identical_when_discriminators_withheld`: with content sensing off, the robot absent and the bounce gap set to the double-take gap (stress level), the two observed dispense streams are equal while the latent days differ (two intakes against one) and the records are C1 `double_take` against C2 `dispenser_bounce`, both with group `double_take_vs_bounce`.
13. `test_double_take_vs_bounce_separable_with_sensing_or_interval`: with content sensing on the second DISPENSE carries `content_change` 1 in the double take and 0 in the bounce; at the sub-second nominal gap the interval alone separates them.
14. `test_nonresponse_vs_forgery_identical_without_witness`: real non-response (C1 `drug_nonresponse`, scale 0) and informed forged dispense with spoofed witness (C3 `dispense_forgery` plus `presence_spoof`) give equal observed streams when the robot is co-located and spoofed, and equal streams without witness when the robot is absent; the latent days differ (a dose against none).
15. `test_nonresponse_vs_forgery_separable_by_witness`: with the robot present and a naive attacker the forged variant lacks the INTAKE event that the real variant has.
16. `test_refusal_vs_robot_missed_pair`: C1 `measurement_refusal` against C2 `manipulation_failure` at the same tick: both lack the measurement; the robot task outcome differs (declined against failed); group `refusal_vs_robot_missed`.
17. `test_confounder_group_carried_by_records_of_both_members`: both records of a pair carry the group string; ordinary injections carry `None`.
18. `test_pair_records_flag_indistinguishable_by_construction`: the injection log of each variant has `variant_id` and `indistinguishable_by_construction`, computed by comparing the observed streams of the pair up to the declared discriminating fields.
19. `test_c1_and_confounder_rows_have_provenance`: every C1 parameter row and every variant-grid row of `injections.yaml` has `source_type` and `source_ref`, and at least three magnitude levels exist per C1 magnitude.

## Passi

1. Write `tests/benchmark/test_c1_confounders.py`; run it, confirm failure; commit `WS04-T09: add failing C1 and confounder tests`.
2. Implement `latent_day.py`: `assemble_latent_days(patient, schedule, n_days, c1_specs, response_model, library, seed, patient_index) -> tuple[LatentResult, ...]` (one `LatentResult(latent, behaviour_log, c1_records)` per day; the autoregressive noise, the adherence chain and the drug accumulation are continuous across midnight) in this order: baseline (T03), adherence (T05, with optional forced slot states), per-intake Emax scales from `drug_nonresponse` records, response (T04), spike and hypotension pulses added to the pressure, latent heart rate and SpO2 from clean segments (T06), latent events (SCHEDULE_TICK, ideal MEASUREMENT at ticks except refused ones, true DISPENSE and INTAKE).
3. Implement `inject_c1.py`: `hypertensive_spike`, `hypotension_below_hold`, `drug_nonresponse`, `measurement_refusal` as effects on the latent assembly; each returns an `InjectionRecord` (`StreamPurpose.INJECTION_C1`); magnitudes are stored as `level` times a named reference (`scale_range` of the registry for pressure pulses; for hypotension the distance between the patient's baseline and the registry entry `bp_hold_threshold`; a dimensionless Emax scale for non-response), resolved by the caller. No clinical constant appears in the code.
4. Implement `confounders.py`: `build_confounder_pair(group, variant, base_context) -> (ScenarioA, ScenarioB)` for the three groups; a scenario is a list of C1, C2 and C3 specs plus capability flags; variants vary content sensing, robot co-location, attacker level and bounce gap (nominal and stress); `indistinguishable_by_construction` is computed by comparing the observed streams of the two members with the declared discriminating fields (`content_change`, INTAKE and presence events, robot task outcome, dispense interval) masked as declared for that variant. The members share the latent baseline, the cuff noise and the schedule (paired design).
5. Add the C1 rows and the variant grid to `injections.yaml` (`design_choice` rows with rationale; at least three magnitude levels spanning below, near and above the reference quantity, so that some levels deliberately do not violate the template) and the declined-task outcome to `vocab.py` (name from the WS02-T03 conventions if defined). Regenerate the provenance table.
6. In the completion note list which analisi §4.5 rows each variant realises and which variants are expected to be indistinguishable; the third group (`refusal_vs_robot_missed`) is marked as added from R3-W4.
7. Refactor, run `ruff check src tests`, `mypy src/ralmon`, `pytest tests/benchmark -q`; commit `WS04-T09: add C1 injection, latent assembly and confounder pairs`; set `status: done`.

## Done when

- `pytest tests/benchmark/test_c1_confounders.py -q` exits 0; `pytest tests/benchmark -q` exits 0.
- `ruff check src tests` exits 0 and `mypy src/ralmon` exits 0.
- `python -m ralmon.benchmark.priors --check-table` exits 0.
- `grep -c 'double_take_vs_bounce\|nonresponse_vs_falsified_dispense\|refusal_vs_robot_missed' src/ralmon/benchmark/confounders.py` prints at least 3.
