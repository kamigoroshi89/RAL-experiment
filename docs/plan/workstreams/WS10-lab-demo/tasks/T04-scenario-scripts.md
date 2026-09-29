---
id: WS10-T04
title: Compressed-timeline scenario scripts and runner
workstream: WS10-lab-demo
owner: agent
status: blocked
depends_on: ["WS07-T04", "WS10-T02", "WS10-T03"]
critical_path: false
non_negotiable: false
estimate_pd: 2
sources: ["analisi §5.3", "analisi §5.1 (3)", "analisi §4.5", "analisi §5.2"]
interfaces: ["02-interfaces.md#ros-2-interfaces", "02-interfaces.md#trace-schema"]
review_items: []
---
## Obiettivo

Encode the scenario catalogue chosen in `outputs/WS10-T01.md` as YAML scripts and write the runner that executes them against the emulated devices, the dispenser and the robot under a declared compression factor. The runner writes, per run, a directory with the scripted ground truth (as `GroundTruthEvent`), a latent (fault-free) scripted day, command, alert and event logs, and a status file. It has a dry-run mode with fake drivers (used by the tests) and a hardware mode that refuses to start without an approved safety record. Output: `hardware/lab_demo/` and `tests/hardware/`.

## Contesto

- `docs/source/analisi.md` §5.3 (compressed timeline, scenarios, repetitions), §5.1 (3) and §4.5 (injections and matrix rows).
- `docs/plan/workstreams/WS10-lab-demo/outputs/WS10-T01.md` (catalogue, `compression_factor`, `clock_policy`, `monitor_config`, `match_config`, `device_control_interface`) and `outputs/WS10-T02.md` (implemented control interface, `timestamp_policy`).
- `docs/plan/02-interfaces.md#ros-2-interfaces` (topics logged by the runner) and `#trace-schema` (`Sample`, `Event`, `GroundTruthEvent`, `InjectedClass`).
- `docs/plan/01-conventions.md` sections 2, 3, 8 and 9 (time in integer milliseconds, seeded randomness, no hard-coded clinical values, outputs layout).
- `configs/registry/hypertension.yaml` (WS01-T03) and `configs/diagnosability.yaml` (WS02-T05), read through `ralmon.spec.load_registry` and the diagnosability file schema.

Unblocked when WS07-T04 is done (robot task layer and witness) and `outputs/WS10-T02.md` exists.

## File toccati

- `hardware/lab_demo/` (create): runner package with clock, registry compression, scenario schema and loader, timeline compiler, driver protocol with fake and real drivers, safety gate, thin ROS 2 adapter (`rclpy` imported only there), CLI `scenario_runner.py`.
- `hardware/lab_demo/scenarios/` (create): one YAML per scenario of the WS10-T01 catalogue.
- `hardware/lab_demo/lab_config.yaml` (create): factor, clock policy, monitor config, match config, care-plan schedule with its source, and the payload keys `robot_task_outcome_key`, `robot_task_duration_key`, `witness_intake_key` copied from the WS07-T04 message definitions.
- `hardware/lab_demo/compression_map.yaml` (create): classification of every registry entry with unit `ms`.
- `tests/hardware/` (create): tests and small fixtures (synthetic registry, synthetic catalogue, synthetic T01 file).

## Test

Write these pytest tests first; they use a fake clock and fake drivers, no sleep, no network, no ROS 2. Fixture values are synthetic and labelled "test fixture, not clinical". Fixture registry: `fx_delta2` = 7_200_000 ms (care-plan time), `fx_gap` = 800 ms (device physics), `fx_band_high` = 100.0 mmHg, `fx_scale` = 20.0 mmHg. Factor 30 unless stated.

- `test_clock_maps_one_hour_to_two_minutes_at_factor_30`: `to_wall_ms(3_600_000) == 120_000` and `to_scenario_ms(120_000) == 3_600_000`.
- `test_clock_rejects_non_positive_factor_and_missing_factor`: factor 0 and -1 raise `ValueError`; loading a lab config without `factor` raises; there is no default factor.
- `test_compress_registry_scales_only_listed_entries`: with `fx_delta2` classified `care_plan_time` and `fx_gap` classified `device_physics`, the compressed registry returns 240_000 for `fx_delta2`, 800 for `fx_gap`, and unchanged 100.0 and 20.0 for the mmHg entries.
- `test_compress_registry_fails_on_unclassified_ms_entry`: an `ms` entry missing from the map raises (fail closed).
- `test_compress_registry_writes_yaml_loadable_by_load_registry`: the compressed registry is written as YAML in the WS01-T03 schema and `ralmon.spec.load_registry` reads it back with `get("fx_delta2").value == 240_000`.
- `test_compressed_registry_marks_version_and_unreviewed`: `version()` contains the parent version and the factor; every compressed entry has `reviewed_by is None` and a rationale containing "lab compression".
- `test_scenario_schema_requires_ground_truth_and_expected`: a scenario without `ground_truth` or `expected` is rejected; required keys are `id, class, description, stand_in, negative_control, diagnosability_row, templates, robot_present, horizon, timeline, ground_truth, expected`; `continuity` is an optional tag.
- `test_expected_block_declares_alerts_task_intake`: `expected` has `alerts` (each with `template` and `kappa` in C1, C2, C3, UNDETERMINED) and optional `trigger_command` (the id of a timeline action), `task` (`name`, `expect: success|failure`, `window_ref` naming a registry entry) and `intake` (`scripted: true|false|none`); a `trigger_command` that names no timeline action is rejected.
- `test_scenario_values_reference_registry_entries`: every `ref` in a scenario names an existing registry entry; a scenario file containing a bare clinical number (a value in mmHg or a care-plan duration not expressed through `ref`) is rejected. Device-physics offsets are allowed only as `wall_ms` with a `justification` field.
- `test_bp_value_expression_hand_computed`: `{ref: fx_band_high, offset_scales: 0.5, scale_ref: fx_scale}` evaluates to 110.0 (100.0 + 0.5 x 20.0).
- `test_catalogue_has_three_to_five_scenarios_per_class`: 3, 5, 3 scenarios for C1, C2, C3 pass; 2 for C1 or 6 for C2 fail; ids are unique.
- `test_catalogue_has_negative_control_and_continuity_checks`: the catalogue needs at least one `negative_control: true` and the two continuity checks (robot out of the room with the device stream continuing; robot heartbeat lost), identified by the `continuity` tags `robot_out_of_room` and `heartbeat_lost`.
- `test_catalogue_ids_match_t01_table`: the scenario ids equal the `C1-nn`, `C2-nn`, `C3-nn` ids of the table in a fixture `WS10-T01.md`.
- `test_timeline_is_deterministic_for_seed_and_repetition`: same (seed, scenario, repetition) gives an identical timeline; over 10 repetitions at least two distinct onsets appear.
- `test_timeline_sorted_and_within_horizon`: actions are sorted by wall time and none is later than the scenario horizon divided by the factor.
- `test_expected_ground_truth_matches_script`: scenario with tick 0 at scenario time 3_600_000 ms and an injection at `{tick: 0, offset: {ref: fx_delta2, times: 0.5}}`, jitter 0: `GroundTruthEvent.onset_ms == 240_000` (that is (3_600_000 + 0.5 x 7_200_000) / 30), `cls == InjectedClass.C2`, `injected is True`. With `jitter.fraction = 0.1` the onset stays within 240_000 +/- 12_000.
- `test_latent_contains_c1_deviation_but_not_injections`: actions with role `c1_deviation` appear in `latent.json`; role `injection` (C2, C3) does not; role `nominal` appears in both latent and observed.
- `test_dry_run_calls_fake_drivers_in_order`: the fake driver records commands in the order of the timeline with the fake-clock wall times.
- `test_hardware_mode_requires_safety_record`: hardware mode raises `SafetyGateError` if the T01 file is missing, has `safety_review_status: not_approved`, or lacks the key; it starts with `approved` or `approved_with_conditions`.
- `test_abort_stops_commands_and_marks_run_aborted`: after `abort()` no further command is issued and `run_status.json` has `status: aborted`.
- `test_run_directory_has_required_files`: the run directory `outputs/lab-<scenario_id>/<seed>/` contains `config.yaml` (scenario copy, factor, compressed registry version, monitor config, match config), `git_rev.txt`, `ground_truth.json`, `latent.json`, `commands.jsonl`, `alerts.jsonl`, `events.jsonl`, `run_status.json`.
- `test_alert_log_line_has_wall_timestamp_and_alert_fields`: a fake alert message becomes one JSON line with `t_wall_ms` and the `Alert` fields of `02-interfaces.md#alert` (`t_ms`, `label`, `score`, `tau`, `kappa`, `sigma_norm`, `rho`, `xi`, `verdict`, `priority`, `root_cause_of`, `caused_by`).

## Passi

1. Create `tests/hardware/` with the fixtures above and the tests listed, all failing.
2. Implement the clock and the registry compression (`compression_map.yaml` is read; unlisted `ms` entries fail). Build `compression_map.yaml` from the frozen registry: classify each `ms` entry as `care_plan_time`, `device_physics`, `transport` or `scale_of_compressed_time` with a one-line reason; these are proposals that the human confirms in the WS10-T05 pre-flight. Compressed entries carry `reviewed_by: None` (ADR-020).
3. Implement the scenario schema, loader and catalogue checks. Time expressions use a care-plan tick plus an offset `{ref: <registry entry>, times: <float>}`; emitted values use `{ref, offset_scales, scale_ref}`. No clinical number appears in a scenario file (`01-conventions.md` section 8).
4. Implement the timeline compiler: `numpy.random.default_rng(np.random.SeedSequence([seed, scenario_index, repetition]))`; roles `nominal`, `c1_deviation`, `injection`; ground-truth builder and latent-day builder (latent = nominal plus `c1_deviation`; `02-interfaces.md#trace-schema`, rule 1).
5. Implement the runner and its CLI (`--check-catalogue`, `--list-ids`, `--mode dry-run|hardware`, `--scenario`, `--reps`, `--seed`, `--out`): driver protocol (fake driver for tests, real drivers following `device_control_interface` of WS10-T01), safety gate, abort, run-directory writer, git revision provider (injectable, so tests do not call git).
6. Implement the thin ROS 2 adapter: subscribe to `/ralmon/alerts`, `/ralmon/samples`, `/ralmon/events`, `/ralmon/robot_evidence`, `/ralmon/heartbeat`; write JSON lines with `t_wall_ms` (alerts to `alerts.jsonl`, all other topics to `events.jsonl` with a `topic` field); keep it import-guarded so the tests never need `rclpy`.
7. Encode every scenario of the WS10-T01 catalogue in `scenarios/`; map `diagnosability_row` to the row id used in `configs/diagnosability.yaml`; fill `lab_config.yaml` from WS10-T01 (`compression_factor`, `clock_policy`, `monitor_config`, `match_config`, `repetitions_per_scenario`) and the three payload keys of `lab_config.yaml` from the WS07-T04 message definitions, and record the source of the care-plan schedule in `care_plan.source`. If no schedule source can be found, stop and record the gap in the completion note; do not invent tick times.
8. Run `ruff check hardware tests`, fix, run the full test set, commit `WS10-T04: scenario catalogue and runner`.

## Done when

- `pytest tests/hardware -q` exits 0.
- `ruff check hardware tests` exits 0.
- `python hardware/lab_demo/scenario_runner.py --check-catalogue` exits 0 and prints the count per class (each between 3 and 5), the negative controls and the continuity tags.
- `for s in $(python hardware/lab_demo/scenario_runner.py --list-ids); do python hardware/lab_demo/scenario_runner.py --mode dry-run --scenario $s --reps 1 --seed 0 --out /tmp/lab-dry || echo "fail $s"; done` prints nothing.
