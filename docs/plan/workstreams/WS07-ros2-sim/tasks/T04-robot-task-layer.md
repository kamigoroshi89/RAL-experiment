---
id: WS07-T04
title: "Robot task layer: care obligations, navigation, witness perception"
workstream: WS07-ros2-sim
owner: agent
status: blocked
depends_on: ["WS07-T02", "WS07-T03", "WS05-T09", "WS05-T05"]
critical_path: true
non_negotiable: false
estimate_pd: 3
sources: ["analisi §4.1 (4)", "analisi §4.9 (1)", "analisi §5.2"]
interfaces: ["02-interfaces.md#ros-2-interfaces", "02-interfaces.md#evidencevector"]
review_items: ["R3-W2", "AE-4"]
---
## Obiettivo

Make the robot part of the specification (analisi §4.1 item 4, §10 objection 3): derive robot tasks from the care plan instead of from a fixed route, execute them with Nav2 in the WS07-T02 ward against the WS07-T03 devices, and provide the embodied evidence. Concretely: obligations in the record defined by WS01-T02 (`docs/formal/02-templates.md` section 5), with the actions `measure_bp` (from SCHED and RESP) and `witness_dispense` (from INT, analisi §10 objection 3), queued with a declared non-preemptive earliest-deadline-first policy; navigation to the bedside, an abstract assist step, and a gated cuff trigger; a witness perception stub with a declared error model that is the only source of `INTAKE` and `PRESENCE` (ADR-004) and yields `None` whenever the robot is not co-located; task outcomes as `ROBOT_TASK` events; robot state samples for WS07-T06; and `scenario.launch.py`, which composes ward, devices, robot and the WS05-T09 nodes. It closes the robot-role part of R3-W2 and AE-4 (the robot is not a host of the monitor; the ward node keeps monitoring when the robot is away, which WS07-T07 checks). The fallback to the nurse when the robot is unavailable belongs to WS05-T09.

## Contesto

Blocked until WS07-T02, WS07-T03 and WS05-T09 are done.

- `docs/source/analisi.md` §4.1 item 4 (measurement obligation induced by φ_resp), §4.5 group 5 (embodied witness), §4.9 items 1, 4, 5 (placement; safety actions are hazards, so the robot only stops, retries or calls; DISPENSE is not INTAKE), §10 objection 3.
- `docs/formal/02-templates.md` sections 3 and 5 (WS01-T02: registry working names of the windows, the obligation record and how each obligation is created, the decision on `creates_robot_obligation` for INT) and `docs/formal/03-parameter-registry.md` check 8 (priority 1 is the highest); contracts `02-interfaces.md#template` and `#evidencevector` (`None` never becomes a negative observation).
- `docs/plan/02-interfaces.md#ros-2-interfaces` (`/ralmon/events`, `/ralmon/robot_evidence`, `/ralmon/heartbeat`) and `docs/plan/workstreams/WS07-ros2-sim/README.md` (clock policy, declared assumptions, internal interfaces), with the T02 scenario and T03 `replay.py` they build on.
- `docs/models/evidence-channels.md` (WS02-T03: witness field semantics, `ROBOT_TASK` payload keys, the definition of a failed navigation task, the presence versus identity decision).
- `ros2/ralmon_ros/` (WS05-T09: robot-side nodes, heartbeat, RSM clock parameters, launch file) and the ADR of WS05-T05 (input features of the deadline forecaster).

## File toccati

- `ros2/ralmon_sim/ralmon_sim/robot_tasks.py` (create): `Obligation` (the WS01-T02 record: `obligation_id`, `source_template`, `instance_key`, `patient_id`, `action`, `window_start_ms`, `window_end_ms`, `deadline_ms`, `created_at_ms`), `OBLIGATION_RULES`, `derive_from_plan`, `derive_from_event`, `EdfQueue`, `TaskOutcome`, `PAYLOAD_KEYS`, `DEADLINE_FEATURES`, `load_robot_config`.
- `ros2/ralmon_sim/ralmon_sim/witness_stub.py` (create): pure error model and observation builder (no console script; used inside the robot process).
- `ros2/ralmon_sim/ralmon_sim/robot_task_node.py` (create): lifecycle node with Nav2 client, cuff trigger client, hooks of the README table, publishers.
- `ros2/ralmon_sim/config/robot_tasks.yaml` (create): policy name, assist and dwell durations, timeouts, perception period, witness error model, seed; required keys, no defaults.
- `ros2/ralmon_sim/launch/scenario.launch.py` (create)
- `ros2/ralmon_sim/test/test_robot_tasks.py` (create): pure tests and `ros` tests.

## Test

Write these first. Fixture templates and values are test-only, not clinical; ward times are in milliseconds after the README transform.

- `test_sched_obligation_from_care_plan_instance`: a compressed plan with one SCHED instance anchored at 1_120_000 and `sched_window` 60_000 gives one obligation with action `measure_bp`, window [1_120_000, 1_180_000] and `source_template` `sched`.
- `test_resp_obligation_created_on_dispense_event`: a `DISPENSE` event at 2_000_000 with delta1 100_000 and delta2 200_000 gives a `measure_bp` obligation with window [2_100_000, 2_200_000] and `source_template` `resp` (created at the dispense, not from the plan).
- `test_witness_obligation_from_int_instance`: a `DISPENSE` at 2_000_000 with `int_window` 10_000 gives a `witness_dispense` obligation with window [2_000_000, 2_010_000]; if the frozen template table keeps `creates_robot_obligation` false for INT, the rule row carries the source `analisi §10 (3)`.
- `test_no_obligation_from_templates_without_flag`: `range`, `hold`, `count` and `sys` instances create nothing; for `measure_bp` the derivation reads `creates_robot_obligation`, not template names.
- `test_obligation_roles_exist_in_template_table`: every registry name used by `OBLIGATION_RULES` is listed in `params` of the template table returned by `ralmon.spec.load_templates`.
- `test_edf_orders_by_deadline_then_priority`: obligations of two rooms with different offsets are ordered by ward-time deadline; equal deadlines are ordered by template priority with 1 as the highest priority (WS01-T03, consistent with `rank_alerts` of WS01-T04).
- `test_scheduler_is_non_preemptive`: a task under way is not replaced by a newly released earlier deadline.
- `test_release_at_window_start`: an obligation is not eligible before its window start.
- `test_outcome_arrival_delay_and_lateness`: arrival at 1_170_000 for window start 1_120_000 gives `arrival_delay_ms` 50_000; finishing after the window end gives outcome `late`; arriving before the window start gives a negative delay and the trigger waits for the window start.
- `test_witness_channel_none_when_robot_not_colocated`: `robot_present`, `identity_confirmed` and `intake_observed` are all `None`, never `False`.
- `test_witness_exact_when_error_rates_zero`: with miss, false and identity error probabilities 0, a co-located tick that contains a latent intake gives `intake_observed` true, a tick without gives false, identity true.
- `test_witness_full_miss_never_observes_intake`: miss probability 1 gives false while co-located.
- `test_witness_seeded_reproducible_and_seed_sensitive`: same seed, same observations; seeds 0 and 1 differ on a 200-tick fixture with probabilities 0.5.
- `test_witness_output_has_no_latent_only_fields`: every key of an observation is in the allowed set (`robot_present`, `identity_confirmed`, `intake_observed`, `t_ms`, `patient`); latent identifiers and latent values never appear.
- `test_state_features_match_declared_list`: the signals published on `/ralmon_sim/robot/state_samples` are exactly `DEADLINE_FEATURES`, the list fixed by the WS05-T05 ADR.
- `test_task_event_payload_keys_follow_conventions`: `PAYLOAD_KEYS` contains the `ROBOT_TASK` keys of the evidence conventions table; any key added for WS07-T06 or WS07-T07 starts with `sim_`.
- `test_config_requires_every_key`: removing any key of `robot_tasks.yaml` raises `RobotConfigError`; `policy` other than the declared one raises.
- `test_robot_layer_has_no_monitoring_logic`: an AST scan of the three modules finds no `rtamt`, `Monitor`, `run_offline` and no submodule imports of `ralmon`.
- `ros` marker: `test_robot_visits_room_and_triggers_cuff` (one SCHED obligation, gated cuff: navigation, service call, measurement group emitted, one `ROBOT_TASK` success event); `test_every_obligation_gets_exactly_one_outcome` (fault-free run of the shipped scenario); `test_robot_evidence_none_when_away` (between visits the witness fields on `/ralmon/robot_evidence` are `None`); `test_goal_override_hook_fails_navigation` and `test_nav_delay_hook_delays_arrival` (publish to the hooks of the README table); `test_lifecycle_transition_reports_node_state`; `test_robot_side_heartbeat_present` (the WS05-T09 heartbeat is on `/ralmon/heartbeat` while the robot processes run).

## Passi

1. Read the Contesto sources. From the WS01-T02 template table take the registry names that play the roles of the window (SCHED, working name `sched_window`), delta1 and delta2 (RESP) and the integrity window (INT, `int_window`); if the frozen names differ, the frozen names win. From WS05-T09 note which robot-side nodes exist, how the RSM derives the `t_ms` of `advance` (message stamps or ROS time) and which parameters carry the clock.
2. Write the tests; run `pytest ros2/ralmon_sim/test/test_robot_tasks.py -q`; watch them fail.
3. Implement `robot_tasks.py`: obligations are released at their window start and scheduled by earliest ward-time deadline, ties by template priority, non-preemptive; this policy is a declared assumption. `OBLIGATION_RULES` is a table (template id, action, role names, source) with one row per rule; the INT row follows the WS01-T02 decision on `creates_robot_obligation` and, if that stays false, is an explicit exception marked `analisi §10 (3)`. Outcome payloads use the keys of the conventions table plus `sim_`-prefixed extensions (action, room, deadline, `sim_arrival_delay_ms` = arrival minus window start, finish time). `DEADLINE_FEATURES` is copied from the WS05-T05 ADR.
4. Implement `witness_stub.py`: while co-located, every perception tick reads the latent intake events of that patient (`BenchmarkDay.latent`, the only place where the ROS side reads latent data, and only inside the simulated perception) and emits an observation under the declared error model (`intake_miss_prob`, `intake_false_prob`, `identity_error_prob`, seeded `numpy.random.Generator`); while not co-located it emits nothing and the evidence fields are `None`. Its outputs are `PRESENCE` samples, `INTAKE` samples and events and the witness part of the robot evidence.
5. Implement `robot_task_node.py`: lifecycle node; subscribes to `/ralmon/events` for `DISPENSE` and to `/ralmon/care_plan` for the derived plans; Nav2 `NavigateToPose` to the bedside pose of the room; an assist step of the configured duration (no manipulation fault exists in simulation, declared); in gated mode calls `/ralmon_sim/<device_id>/trigger_measurement` at the later of arrival and window start; a `witness_dispense` task dwells for the configured time with the stub active. Publish `ROBOT_TASK` outcome events (navigation failed, timed out, late, success), `NODE_STATE` on its own lifecycle transitions, robot evidence on `/ralmon/robot_evidence` (`nav_task_failed`, `manip_task_failed` false, `battery_low` `None` because there is no battery model, witness fields from the stub; use the WS05-T09 converters), and the feature samples on `/ralmon_sim/robot/state_samples`. Implement the two hooks `/ralmon_sim/fault/goal_override` and `/ralmon_sim/fault/nav_delay` exactly as in the README table. The robot only navigates, waits, retries and reports; it never commands a dispenser (analisi §4.9 item 4).
6. Write `robot_tasks.yaml` (header: every value with no source is a declared run parameter) and `scenario.launch.py`: include `sim_ward.launch.py`, `devices.launch.py` with the slots of the scenario, `robot_task_node`, and the WS05-T09 launch (ward node, robot-side nodes); pass `ward_epoch_ms` and the scenario clock parameters to each node that declares them (check with `ros2 param list`); do not edit `ros2/ralmon_ros`. If a WS05-T09 node derives time from raw ROS time and has no clock parameter, restrict the scenario to `compression_factor` 1 and offsets 0, state it in the launch file header and put the request for a parameter in the completion note.
7. Run a fault-free scenario and record in the scenario header the shortest compressed obligation window and the longest task duration observed (the compression-fit check of the README: task durations must fit inside the windows, otherwise the factor is lowered).
8. Make all tests pass in both environments; run `ruff check ros2/ralmon_sim`, `ruff format ros2/ralmon_sim`; commit `WS07-T04: robot task layer and witness stub`. Tell the owner of WS10-T04 that the task layer is available.

## Done when

- `pytest ros2/ralmon_sim/test/test_robot_tasks.py -q -m "not ros"` exits 0.
- In the sourced ROS 2 environment: `pytest ros2/ralmon_sim/test/test_robot_tasks.py -q -m ros` exits 0.
- `ruff check ros2/ralmon_sim` and `ruff format --check ros2/ralmon_sim` exit 0.
- `grep -rnE "rtamt|run_offline|import Monitor" ros2/ralmon_sim/ralmon_sim/robot_tasks.py ros2/ralmon_sim/ralmon_sim/robot_task_node.py ros2/ralmon_sim/ralmon_sim/witness_stub.py` prints nothing.
- `grep -c "witness_dispense" ros2/ralmon_sim/ralmon_sim/robot_tasks.py` prints at least 1 and `grep -c "measure_bp" ros2/ralmon_sim/ralmon_sim/robot_tasks.py` prints at least 1.
- `grep -nE 'TO''DO|TB''D|lo''rem|[?][?][?]' ros2/ralmon_sim/config/robot_tasks.yaml` prints nothing.
