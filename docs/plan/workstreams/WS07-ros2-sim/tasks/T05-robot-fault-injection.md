---
id: WS07-T05
title: "Robot and link fault injection"
workstream: WS07-ros2-sim
owner: agent
status: blocked
depends_on: ["WS07-T03"]
critical_path: false
non_negotiable: false
estimate_pd: 2
sources: ["analisi §5.2", "analisi §5.1 (3)"]
interfaces: ["02-interfaces.md#ros-2-interfaces", "02-interfaces.md#evidencevector"]
review_items: []
---
## Obiettivo

Inject the system and embodiment faults of analisi §5.2 into the running simulation from a seeded schedule file: lifecycle transitions (`uncommanded_lifecycle_transition`), process kill (`process_kill`), message drops (`message_drop`, through the gateway link model or `tc netem`), localisation noise (`localisation_noise`), impossible navigation goals (`impossible_goal`) and an extra navigation delay (`nav_delay`), plus the non-fault control `commanded_lifecycle_transition` of analisi §4.6 row 15:00 (a deliberate transition is not a crash). Identifiers are those of `docs/models/fault-model.md` (WS02-T01) and are reused verbatim. Output: a schedule loader and expander, a fault injector node, a fault log, a machine-readable oracle `EXPECTED_EVIDENCE` (which symptoms and `EvidenceVector` fields each fault should raise, checked against the fault-to-evidence table of WS02-T01), example schedules and a netem script. Scope note: this task depends only on WS07-T03, so the robot-side faults (`localisation_noise`, `impossible_goal`, `nav_delay`) are implemented against the interfaces of the README table and unit-tested with fakes; their end-to-end check on the full scenario is done in WS07-T07.

## Contesto

Blocked until WS07-T03 is done (device nodes, gateway, link drop parameters, supervisor announcements).

- `docs/models/fault-model.md` (WS02-T01: `Subtype vocabulary`, `Fault-to-evidence table`, `Injection parameter sheet`, `Non-faults and boundaries`) and `docs/models/evidence-channels.md` (WS02-T03: what each `EvidenceVector` field means and how it is derived).
- `docs/source/analisi.md` §5.2 (fault list: lifecycle transitions, process kill, message drops with tc netem, localisation noise, impossible goals), §5.1 (3) (C2 injections with onset, duration and magnitude), §4.6 row 15:00.
- `docs/plan/02-interfaces.md#ros-2-interfaces` (liveliness, heartbeat: a lost heartbeat is C2 evidence) and `#evidencevector` (20 fields; `None` means unavailable).
- `docs/plan/workstreams/WS07-ros2-sim/README.md` (internal interfaces: gateway parameters, supervisor announcements, robot hooks) and the T03 task file.
- `ros2/ralmon_sim/config/package_availability.yaml` (`tc_netem` and RMW findings from WS07-T01).

## File toccati

- `ros2/ralmon_sim/ralmon_sim/fault_injection.py` (create): `FaultKind`, `FaultSpec`, `FaultRecord`, `load_schedule`, `expand_schedule`, `localisation_offsets`, `resolve_targets`, `EXPECTED_EVIDENCE`, `FaultScheduleError`.
- `ros2/ralmon_sim/ralmon_sim/fault_injector.py` (create): `main`, the injector node.
- `ros2/ralmon_sim/config/fault_schedules/` (create): one example schedule per kind and one mixed schedule; one directory because the files share a schema.
- `ros2/ralmon_sim/scripts/netem.sh` (create): `add`, `del`, `status` for one interface.
- `ros2/ralmon_sim/launch/faults.launch.py` (create): starts the injector with `schedule:=<file>` next to any scenario or device launch.
- `ros2/ralmon_sim/test/test_fault_injection.py` (create): pure tests and `ros` tests.

## Test

Write these first. Fixture values are test-only. Parameter names follow the `Injection parameter sheet` of the fault model (onset, duration, magnitude); where the sheet differs from the names below, the sheet wins and the tests are adapted.

- `test_schedule_requires_kind_specific_parameters`: `message_drop` needs `magnitude.probability` in [0, 1]; `localisation_noise` needs `magnitude.sigma_xy_m`, `magnitude.sigma_yaw_rad`, `magnitude.period_ms`; `nav_delay` needs `magnitude.delay_ms`; `process_kill`, `impossible_goal` and the lifecycle kinds need none; a missing required key raises `FaultScheduleError`; `seed` and `onset_ms` are required and have no default.
- `test_unknown_kind_rejected`.
- `test_kinds_are_in_fault_model_vocabulary`: every kind except the control appears in the `Subtype vocabulary` list of `docs/models/fault-model.md`; the control appears in its `Non-faults and boundaries` section.
- `test_expand_schedule_sorted_and_deterministic`: two faults given out of order expand to actions sorted by ward time (start and end actions), and two expansions with one seed serialise to identical JSON; seeds 0 and 1 differ for `localisation_noise`.
- `test_localisation_offsets_moments_and_identity`: sigma 0 gives all-zero offsets; for `sigma_xy_m` 0.5 (test-only), 10_000 draws with seed 0 have mean within four standard errors of 0 and sample standard deviation within 5 percent of 0.5.
- `test_resolve_targets_from_groups`: group `robot` resolves to its node names; an unknown target raises; a device id resolves to its device node.
- `test_control_is_recorded_as_non_fault`: the commanded transition produces a record with `is_fault` false; all other kinds produce `is_fault` true and `injected_class` "C2".
- `test_fault_records_use_ward_clock`: onset and end in `FaultRecord` are ward-clock milliseconds; permanent faults have `end_ward_ms` `None`.
- `test_expected_evidence_covers_every_kind`: every kind has an entry with `ros_symptoms` (non-empty) and `raised_paths`.
- `test_expected_evidence_paths_are_contract_fields`: every path is one of the 20 `group.field` names of `EvidenceVector` (derived from the dataclass fields).
- `test_expected_evidence_matches_fault_model_table`: for each kind, the set of paths equals the set in its row of the `Fault-to-evidence table` of `docs/models/fault-model.md`, except paths listed in `not_producible_in_sim` (each with a reason string).
- `ros` marker (with WS07-T03 nodes only): `test_uncommanded_deactivation_emits_node_state_and_keeps_liveliness`; `test_commanded_transition_carries_the_commanded_marking` (the marking of WS02-T03, set through `/ralmon_sim/supervisor/commands`); `test_process_kill_removes_process_and_liveliness_is_lost` (gateway link-lost `NODE_STATE` within lease plus margin); `test_message_drop_window_sets_and_clears_gateway_parameter` (no frames forwarded inside the window, frames after it); `test_action_times_follow_ward_clock` (each action within the declared timing tolerance); `test_localisation_noise_publishes_pose_offsets` (fake pose source; offsets published on the initial-pose topic at the period); `test_impossible_goal_and_nav_delay_publish_hooks` (fake subscriber on the hook topics; unreachable pose taken from the scenario file).
- `netem` marker (skipped without the privilege recorded in the T01 record): `test_netem_drops_reach_the_ros_topic` (a message-count probe shows loss with netem added and none after removal).

## Passi

1. Read `docs/models/fault-model.md` (vocabulary, parameter sheet, fault-to-evidence table, non-faults) and the T01 record for `tc_netem`. Write the tests above and watch them fail.
2. Implement `fault_injection.py` (pure): frozen dataclasses, strict schedule loader, `expand_schedule` (start and end actions, ward-clock milliseconds), seeded `numpy.random.Generator` for offsets, target resolution from a `groups` mapping in the schedule, and the oracle `EXPECTED_EVIDENCE` built from the fault model: for each kind the ROS-level symptoms (for `process_kill` on a device: liveliness lost on its publisher and a link-lost `NODE_STATE`; on the robot: a gap on `/ralmon/heartbeat` and no `ROBOT_TASK` events; for `message_drop`: fewer samples, gaps in `seq`; for the lifecycle kinds: a `NODE_STATE` event and unchanged liveliness; for `impossible_goal`: a failed `ROBOT_TASK` navigation outcome; for `nav_delay` and `localisation_noise`: late or failed outcomes), the evidence paths, and `not_producible_in_sim` (for example `system.battery_low`: no battery model). Note in the oracle that a sequence gap raised by dropped messages is also the symptom that a replay attack raises; whether attribution separates the two is a question for WS02-T03 and WS05-T07, and this task only records that the gap channel fires.
3. Implement `fault_injector.py`: one node that executes the expanded actions on the ward clock: lifecycle changes through the standard `change_state` service; a commanded control first announces the node on `/ralmon_sim/supervisor/commands`; kill by matching the process command line of `__node:=<name>` and sending SIGKILL to the group members; `message_drop` by setting the gateway parameters `link_drop_probability` and `link_seed` (mechanism `gateway_model`) or calling `netem.sh` (mechanism `netem`, needs the privilege); `localisation_noise` by publishing seeded offsets on the initial-pose topic at the given period; `impossible_goal` and `nav_delay` by publishing on the hook topics; write one JSON line per `FaultRecord` to the run directory (`fault_log.jsonl`). The injector is not on the alert path and never publishes on `/ralmon/*`.
4. Write the example schedules (one per kind, one mixed with overlapping faults on different targets), `netem.sh` (refuses to run without the privilege, never touches an interface not named on the command line, always prints what it changed) and `faults.launch.py`.
5. Make the pure tests pass, then the `ros` tests with the T03 nodes; run the netem probe if the privilege exists, otherwise leave the test skipped and write in the completion note that WS07-T07 must run it with the required human action.
6. Run `ruff check ros2/ralmon_sim`, `ruff format ros2/ralmon_sim`; commit `WS07-T05: fault injector and oracle`.

## Done when

- `pytest ros2/ralmon_sim/test/test_fault_injection.py -q -m "not ros and not netem"` exits 0.
- In the sourced ROS 2 environment: `pytest ros2/ralmon_sim/test/test_fault_injection.py -q -m "ros and not netem"` exits 0.
- `ruff check ros2/ralmon_sim` and `ruff format --check ros2/ralmon_sim` exit 0.
- `for k in uncommanded_lifecycle_transition commanded_lifecycle_transition process_kill message_drop localisation_noise impossible_goal nav_delay; do test -f ros2/ralmon_sim/config/fault_schedules/$k.yaml || echo "missing $k"; done` prints nothing.
- `bash ros2/ralmon_sim/scripts/netem.sh status lo` exits 0 and changes nothing.
- `grep -nE 'TO''DO|TB''D|lo''rem|[?][?][?]' ros2/ralmon_sim/ralmon_sim/fault_injection.py ros2/ralmon_sim/scripts/netem.sh` prints nothing.

## Notes

### Flag from the WS02-T01 review (orchestrator, 2026-10-02)

See `docs/models/fault-model.md` OP-13 to OP-16: the schedule format here uses a `magnitude.<key>` mapping with `seed`, while WS04-T07 `InjectionSpec` has a scalar `magnitude` and `params`; time faults, `battery_depleted` and the simulated `manipulation_failure` have no injector here (OP-6); `process_kill` and `uncommanded_lifecycle_transition` can also violate `count` when the dispenser node is the target (FX-15). Kept `blocked`.
