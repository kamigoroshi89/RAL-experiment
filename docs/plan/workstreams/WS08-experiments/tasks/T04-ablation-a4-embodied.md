---
id: WS08-T04
title: "Ablation A4: embodied channel removed"
workstream: WS08-experiments
owner: agent
status: blocked
depends_on: ["WS08-T02", "WS02-T05"]
critical_path: true
non_negotiable: true
estimate_pd: 2
sources: ["analisi §5.6 (A4)", "analisi §10 (3)", "analisi §4.8", "analisi §4.5", "analisi §9"]
interfaces: ["02-interfaces.md#evidencevector", "02-interfaces.md#attribution"]
review_items: ["R3-W2", "AE-4"]
---
## Obiettivo

This task is **NON-NEGOTIABLE** (analisi §9: "Non tagliate B5, A4 né la formalizzazione"): it is not optional, it is not on the cut list of `00-master-plan.md` section 7, and no other task may be cut to protect it or dropped to make room for it. It answers "why a robot?" (analisi §5.6, §10 objection 3, R3-W2, AE-4) with numbers: the proposed method is run with and without the embodied channel (robot lifecycle and task outcomes, perception, witness) on identical days, splits and seeds, and the loss of attribution is measured for the robotic C2 events and the forged DISPENSE events, together with the temporal coverage of the channel (analisi §4.8: "dichiarando la copertura temporale"). Concrete output: `embodied.py`, `experiments/A4.yaml`, and `outputs/A4/<seed>/...` for at least five seeds, each with `analysis.delta_vs_full`, `analysis.embodied_temporal_coverage` and `analysis.availability_sweep`.

## Contesto

- `docs/plan/workstreams/WS08-experiments/README.md` (conventions E3, E4, E5; rules H3 and H4) and `docs/source/analisi.md` §5.6 (A4 is the strategically most important ablation), §4.8 (embodiment claim row) and §10 objection 3.
- `02-interfaces.md#evidencevector` (rule: `None` is never converted to a negative observation; with the channel removed all `witness` fields and robot-derived `system` fields become `None`) and `02-interfaces.md#attribution` (hierarchical rule, UNDETERMINED).
- `docs/models/evidence-channels.md` (the A4 mask field by field, WS02-T03), `docs/models/attribution-rule.md` (WS02-T04) and `configs/diagnosability.yaml` (rows, declared limits DX-04 and DX-10, an A4 outcome per row; WS02-T05).
- `experiments/main.yaml` and `outputs/main/` from WS08-T02 (data settings, the `analysis` helpers `undetectable_rows` and `MatrixCoverageError`).
- Blocked until WS08-T02 and WS02-T05 are `done`.

## File toccati

- `src/ralmon/eval/embodied.py` (create): `EMBODIED_MASK_ALL`, `EMBODIED_MASK_WITNESS`, `mask_evidence`, `availability_mask`, `variant_components` for `ours-A4`, `ours-A4-witness-only`, `ours-A4-avail-<f>`, and `hooks_for("A4")`.
- `experiments/A4.yaml` (create).
- `tests/eval/test_embodied.py` (create).
- `tests/fixtures/eval/embodied/` (create): hand-built evidence vectors, a forged-DISPENSE day, a robot-navigation-failure day, a two-row diagnosability fixture with an A4 column in a test vocabulary ("loss", "no_change").

## Test

Write these first. Values are fixtures, not results.

`tests/eval/test_embodied.py`

1. `test_mask_paths_are_real_evidencevector_fields`: every dotted path of `EMBODIED_MASK_ALL` (for example `witness.robot_present`) resolves to a field of `EvidenceVector` by dataclass introspection; the constant contains at least the three `witness` fields, `system.nav_task_failed` and `system.manip_task_failed`, and exactly the further robot-derived fields listed in `evidence-channels.md`.
2. `test_mask_all_sets_listed_fields_to_none_and_leaves_others`: after `mask_evidence(ev, EMBODIED_MASK_ALL)` every listed path is `None` and every other field of `EvidenceVector` equals its original value.
3. `test_mask_never_converts_none_to_false`: a field that was `None` stays `None` (`is None`, not `False`); a field that was `True` or `False` becomes `None`.
4. `test_mask_is_noop_when_channel_already_absent`: evidence whose masked fields are already `None` is returned equal, and `ours` and `ours-A4` give the same attributed cause on it.
5. `test_witness_only_mask_keeps_robot_task_outcomes`: `EMBODIED_MASK_WITNESS` sets only the three `witness` fields to `None`; `system.nav_task_failed` keeps its value.
6. `test_a4_forged_dispense_loses_c3`: on the forged-DISPENSE fixture (robot present, no identity, no intake observed, no authentication evidence) `ours` attributes C3 and `ours-A4` attributes something else; the expected value without the channel is the one that `attribution-rule.md` gives for insufficient evidence (UNDETERMINED unless that document says otherwise; the fixture comment cites the rule step).
7. `test_a4_robot_navigation_failure_loses_c2`: on the navigation-failure fixture (`system.nav_task_failed = True`, no other system evidence) `ours` attributes C2 and `ours-A4` does not.
8. `test_a4_keeps_non_embodied_c2`: a cuff device-error fixture (`signal_quality.cuff_error_code` set) is attributed C2 by both.
9. `test_a4_leaves_verdicts_unchanged`: on the fixture day the `VerdictRecord` sequences of `ours` and `ours-A4` are equal (the ablation acts on attribution only; detection metrics are identical by construction and the analysis records `verdicts_unchanged: true`).
10. `test_availability_mask_pure_function_of_seed_and_key`: the uniform draw for a given `(seed, patient_id, day_index, instance_key)` is the same in any call order (entropy from `zlib.crc32` of the key, never from `hash`).
11. `test_availability_masks_are_nested`: the set of alerts with witness available at f = 0.3 is a subset of the set at f = 0.7 (one draw per key; available iff `u < f`).
12. `test_availability_endpoints`: f = 1.0 leaves every evidence vector unchanged (equal to `ours`); f = 0.0 gives the same vectors as `ours-A4` (the availability variants apply `EMBODIED_MASK_ALL` to every alert whose draw is not below f).
13. `test_availability_fraction_close_to_f`: over 2_000 keys the available fraction at f = 0.3 is within 0.031 of 0.3 (three binomial standard deviations).
14. `test_sweep_reports_effective_coverage`: with a stubbed uniform source, 10 alerts of which 6 have a natural witness and 3 of those 6 draws below f = 0.5, the effective coverage is 0.3 (the x axis of the sweep is measured coverage, natural coverage times f, not f).
15. `test_temporal_coverage_hand_count`: 10 matched events, C1 3 (witness available in 2), C2 4 (3), C3 3 (1): overall 0.6, per class 2/3, 0.75, 1/3.
16. `test_kappa_recall_by_class`: for matched C2 events, full 40 of 40 attributed C2 and ablated 20 of 40 give recalls 1.0 and 0.5 and delta 0.5; UNDETERMINED counts as not attributed.
17. `test_paired_delta_ci_excludes_zero_on_planted_effect`: the 40-event case above with seed 0 has a paired bootstrap interval with `ci_lo > 0`; with identical outcomes in both arms the interval contains 0.
18. `test_rows_without_gain_and_claim_action`: subtypes whose delta interval contains 0 are listed in `rows_without_gain`; if neither the C2 nor the C3 delta interval excludes 0 then `claim_action` reads `"reword embodiment claim (analisi 4.8)"`, otherwise `"none"`.
19. `test_a4_row_check_flags_disagreement`: a row whose declared A4 outcome is `no_change` (test vocabulary) but whose measured delta interval is (0.3, 0.6) gets `consistent: false` and stays in the report; a row declared `loss` with a positive interval is `consistent: true`.
20. `test_missing_matrix_row_raises`: a ground-truth subtype without a matrix row raises `MatrixCoverageError`.
21. `test_variant_components_names_a4`: components for `ours-A4`, `ours-A4-witness-only`, `ours-A4-avail-0.5`; `None` for `ours-A1`; `ConfigError` for `ours-A4-avail-1.5` and `ours-A4-avail-0`.
22. `test_a4_config_loads_and_shares_main_settings`: `experiments/A4.yaml` loads; detectors include `ours`, `ours-A4`, `ours-A4-witness-only` and at least three `ours-A4-avail-<f>` with 0 < f < 1; data settings equal those of `main.yaml`; `headline` is true; at least 5 unique seeds.

## Passi

1. Verify the unblock conditions. Read the A4 mask list in `evidence-channels.md`, the attribution rule steps in `attribution-rule.md` and the rows and A4 outcomes of `configs/diagnosability.yaml`. Record in the completion note which matrix rows carry an embodied dependency. Branch `ws08-t04-ablation-a4-embodied`; set `status: in_progress`.
2. Write the fixtures and tests 1 to 22; run `pytest tests/eval/test_embodied.py -q`; confirm they fail. Commit `WS08-T04: add failing A4 tests`.
3. Implement `mask_evidence` and the two mask constants. The constants are copied from `evidence-channels.md` with a docstring naming the section; no field is added from memory. Tests 1 to 9 pass.
4. Implement `availability_mask` (`numpy.random.default_rng([seed, STREAM_AVAILABILITY, zlib.crc32(key)])`, one uniform draw per key) and the variant components (mask applied through the `evidence_transform` component). Tests 10 to 14 and 21 pass.
5. Implement the hooks: `embodied_temporal_coverage` (event level: share of matched alerts with `witness.robot_present is not None`, by class and subtype; time level: the co-location schedule as recorded by WS04-T06 and WS04-T07, whose representation is stated in the completion note), `delta_vs_full` (kappa recall per class and subtype, macro-F1 and abstention-rate deltas, paired bootstrap), `availability_sweep` (macro-F1 and kappa recall for C2 and C3, and accuracy versus coverage points, against effective coverage), `rows_without_gain`, `claim_action`, `verdicts_unchanged`, `a4_row_check` (comparison rule written from the vocabulary of the WS02-T05 schema). Tests 15 to 20 pass.
6. Write `experiments/A4.yaml`: data settings copied from `main.yaml`, detectors as in test 22 with the sweep points declared in the file, `required_analysis` listing the seven keys of step 5, `headline: true`. Run `python -m ralmon.eval.runner --config experiments/A4.yaml --output outputs` and `python -m ralmon.eval.analysis --check outputs/A4`.
7. Read the results and write the answer in the completion note, in this order: temporal coverage of the channel; loss of kappa for robotic C2 and forged DISPENSE with intervals; the witness-only versus full-removal split (which part of the effect needs perception, which needs robot state); the sweep (how much co-location is needed for a given attribution level); the rows without gain and the rows where the measured effect disagrees with the WS02-T05 declared outcome. State the limits plainly: A4 changes attribution only, detection is identical by construction (test 9); the contribution of the robot to executing the obligations induced by RESP and SCHED is measured in WS07-T06 and WS07-T07, not here; the co-location schedule is a benchmark assumption of WS04. If no gain excludes 0, follow `claim_action` and tell WS12-T03 and WS12-T07.
8. Run the Done when commands, commit `WS08-T04: add ablation A4`, set `status: done`.

## Done when

- `pytest tests/eval -q` exits 0, `ruff check src tests` exits 0, `mypy src/ralmon` exits 0.
- `n=$(ls outputs/A4/*/metrics.json | wc -l); test "$n" -ge 5` exits 0.
- `python -m ralmon.eval.analysis --check outputs/A4` exits 0.
- `for k in delta_vs_full embodied_temporal_coverage availability_sweep rows_without_gain a4_row_check verdicts_unchanged claim_action; do grep -q "\"$k\"" outputs/A4/0/metrics.json || echo "missing $k"; done` prints nothing.
- `grep -c 'ours-A4-avail' outputs/A4/0/metrics.json` prints at least 3.

## Notes

### Flag from the WS02-T03 review (orchestrator, 2026-10-04)

See `docs/models/evidence-channels.md` section "Ablation A4 mask" and EC-OP-5: the mask has 6 fields forced to `None` (the three `witness` fields, `nav_task_failed`, `manip_task_failed`, `battery_low`), 4 to recompute without the robot component (`node_lifecycle`, `diagnostics_ok`, `liveliness_ok`, `qos_deadline_missed`) and 10 unchanged; a pure path mask is only a partial A4 (a robot crash stays visible through `liveliness_ok`; `mask_evidence` as a path set cannot do the recompute class). Decide here. Kept `blocked`.

### Hand-over from the WS01-T07 review (orchestrator, 2026-10-08)

Read `docs/formal/07-alert-tuple-mapping.md` section 1 (sigma_norm of VIOLATED and predicted alerts, CP13: kappa of a PREDICTED_VIOLATION alert is UNDETERMINED and the alert is superseded by the VIOLATED alert with the same `xi.instance_key`) and section 9 (open points OP-T07-1..17) and proposed ADR-041 before starting. Where this task text assumes a provisional kappa for predicted alerts (WS02-T04 check 8 and step 5; WS05-T07 tests 18, 20, 25) or counts a pair matched by a predicted alert (WS08 E3/E4), follow OP-T07-10 and ADR-041 and record any deviation here. `attribute` stays pure (kappa independent of `state`, test 5 scoped to the rule); the state check sits in `attribute_all`.

### Hand-over from the WS05-T04 review (orchestrator, 2026-10-10)

The A4 results and the dispense-forgery detection depend on ADR-054 (proposed): with the generator as it is (presence `1.0` at robot arrivals only, no zero, no availability mark) the monitor of WS05-T04 reads the level of the last robot visit at every later dispense, so INT is satisfied by an old sample and the full-system run, the ablated run and the baselines all lose the INT signal after the first visit. Before reporting anything that rests on INT or on the witness fields, read `run_offline_detailed(...).stats.presence_level_older_than_window_steps` for every day and require 0, or state the number; the mask of the A4 ablation (the robot channel removed) is the same `NODE_STATE colocated` mask of option (b). Also read `stats().rho_unavailable` (a VIOLATED RESP record with an undefined pre-dose pressure has `rho = None`, counted there) and `late_inputs()` from the detailed result, not from `run_offline`, which returns the records only.
