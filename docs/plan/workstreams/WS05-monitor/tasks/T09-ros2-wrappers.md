---
id: WS05-T09
title: "ROS 2 wrapper packages: RSM, attribution, event manager, watchdog, heartbeat, ward-node placement"
workstream: WS05-monitor
owner: agent
status: blocked
depends_on: ["WS05-T08", "WS07-T01"]
critical_path: true
non_negotiable: false
estimate_pd: 3
sources: ["analisi §4.9 (1)", "analisi §9 (5)"]
interfaces: ["02-interfaces.md#ros-2-interfaces"]
review_items: ["R3-W2", "AE-4"]
---
## Obiettivo

Build the thin ROS 2 package `ralmon_ros` under `ros2/`: message types for the topics of the `ROS 2 interfaces` contract, converters between messages and the `ralmon` dataclasses, and the nodes RSM, attribution, event manager, watchdog and heartbeat, plus launch files that realise the placement of ADR-003 (a ward node runs the runtime safety monitor for the continuous phi_CP constraints and supervises the robot by heartbeat; the robot runs the embodied specifications, provides evidence, and is supervised in return; if the robot is unavailable the fallback escalates to the nurse). The wrappers contain no monitoring logic: a ROS 2 replay of a trace must give the same verdicts and alerts as `run_offline`. It answers R3-W2 (who monitors the monitor, what happens when the robot leaves or fails) and the robotic side of AE-4.

## Contesto

Blocked until WS05-T08 and WS07-T01 are `done`; read the completion note of WS07-T01 first (distribution and Gazebo decision of ADR-011, workspace layout, marker `ros`, whether interface generation needs a separate package).

- `02-interfaces.md#ros-2-interfaces` (seven topics, producers and consumers, liveliness and deadline QoS on `/ralmon/heartbeat` and `/ralmon/samples`, a deliberate lifecycle transition is not a crash).
- `docs/plan/workstreams/WS07-ros2-sim/README.md` (module map, clock policy with the parameter `ward_epoch_ms`, the rule that contract types travel in the message types created here and that WS07 imports them).
- `docs/models/evidence-channels.md` (availability per placement S1 to S6, trace evidence conventions for `Event.payload`, how NODE_STATE events carry liveliness).
- `docs/plan/03-decisions.md` (ADR-003 placement of the ward node and the robot, ADR-011 distribution).
- `docs/source/analisi.md` §4.9 item 1 (distributed architecture: ward node, robot, heartbeat, fallback to the nurse).

## File toccati

- `ros2/ralmon_ros/` (create: `package.xml` and build files following the WS07-T01 workspace; `msg/`, `ralmon_ros/{topics,clock,converters,rsm_node,attribution_node,event_manager_node,watchdog_node,heartbeat_node}.py`, `launch/{ward,robot}.launch.py`, `config/{ward,robot,placement}.yaml`, `test/`)
- `ros2/ralmon_ros_msgs/` (create only if WS07-T01 found that interface generation needs its own package; then the messages live there and `ralmon_ros.converters` stays the single import point)
- `docs/plan/03-decisions.md` (modify: append one ADR, status `proposed`, confirmation tag, for the placement table and the wrapper conventions)

## Test

Write first; each fails before the implementation. Tests live in `ros2/ralmon_ros/test/`. Tier A runs with plain `pytest` and `ralmon` installed (`-m "not ros"`); tier B needs the sourced ROS 2 workspace and carries the marker `ros` registered by WS07-T01. Trace values are fixture-only.

Tier A: structure, layering and logic-freedom

1. `test_topics_match_contract_table`: the topic names in `ralmon_ros/topics.py` equal, as a set, the seven names of the table under `## ROS 2 interfaces` of `docs/plan/02-interfaces.md` (`/ralmon/samples`, `/ralmon/events`, `/ralmon/robot_evidence`, `/ralmon/verdicts`, `/ralmon/alerts`, `/ralmon/heartbeat`, `/ralmon/care_plan`) and no other string starting with `/ralmon/` appears in `ros2/ralmon_ros` (no invented topic).
2. `test_message_fields_match_dataclasses`: each `.msg` file of the contract types parses (plain text); its field names, with the companion availability flags `has_<field>` removed, equal the field names of the dataclass (`Sample`, `Event`, `VerdictRecord`, `Alert`, `CarePlan`), of the witness and robot system fields of `EvidenceVector` (`RobotEvidence`), and of the heartbeat triple (node id, sequence number, `t_ms`); every dataclass field typed `X | None` has a `has_<field>` flag, every other field has none.
3. `test_wrappers_import_only_allowed_modules`: an AST scan of `ros2/ralmon_ros` accepts imports of `rclpy` and its submodules, the message packages used (own messages, `builtin_interfaces`, `lifecycle_msgs`, `diagnostic_msgs`), the standard library, the package itself, and `ralmon.<package>` roots; anything else fails.
4. `test_wrappers_use_ralmon_public_api_only`: no `from ralmon.<package>.<module>` and no `import ralmon.<package>.<module>` in `ros2/ralmon_ros`.
5. `test_wrappers_do_not_import_numeric_or_stl_libraries`: no `numpy`, `scipy`, `sklearn` or `rtamt` in `ros2/ralmon_ros`.
6. `test_callbacks_are_logic_free`: for every function registered with `create_subscription`, `create_timer` or an event callback, the AST contains no arithmetic operator, no comparison other than `is` and `is not`, and loops only of the form `for x in seq:` whose body is one call statement (one publish or one log per item); allowed calls are conversions, one `ralmon` method, publish, log, `next()`. `if` on a boolean attribute is allowed (state change detection); `while` is not.
7. `test_conversions_call_no_ralmon_functions`: `converters.py` and `clock.py` call only dataclass and enum constructors from `ralmon` (no `advance`, `load`, `normalise`, `rank_alerts`, `attribute_all`, `update`); arithmetic is allowed only in `clock.py`.
8. `test_clock_conversion_hand_values`: `ros_time_to_ms(sec=1, nanosec=500_000_000) == 1500`; `ward_time_ms(now_ms=100_000, ward_epoch_ms=40_000) == 60_000`; a clock earlier than `ward_epoch_ms` raises `ValueError` (never a negative ward time).
9. `test_placement_table_covers_every_template_once`: `config/placement.yaml` assigns each of the seven `TemplateId` values to exactly one placement (`ward` or `robot`); proposal recorded in the ADR: ward `range`, `hold`, `count`, `resp`, `sys`; robot `sched`, `int` (task deadlines and witness).
10. `test_parameters_have_no_defaults_in_code`: every `declare_parameter` call passes a type and no default value; every numeric value in `config/*.yaml` sits next to the marker `provisional` (period, deadline, lease, `step_ms`, `reorder_delay_ms` are engineering values to be fixed by WS07-T07, not clinical values).
11. `test_core_never_imports_ros`: `! grep -rnE "^(import|from) rclpy" src/ralmon` holds (same check as WS05-T01, re-run here).

Tier B: behaviour in the ROS 2 workspace (marker `ros`)

12. `test_message_roundtrip_preserves_none_and_types`: for `Sample`, `Event`, `VerdictRecord`, `Alert`, `CarePlan`, convert to message and back and compare with `==`; a `Sample` with `seq=None` and `quality=None` returns `None` for both (flags false); an `Event.payload` keeps `True` as bool, `1` as int, `1.5` as float and `"x"` as str.
13. `test_evidence_none_is_not_false`: a `RobotEvidence` message whose `diagnostics_ok` is unavailable converts to `None`, never to `False` (contract rule of `#evidencevector`); an available `False` stays `False`.
14. `test_rsm_replay_equals_run_offline`: the RSM node with `use_sim_time`, `ward_epoch_ms = 0`, the F0 registry and a plan replays a hand-written day through `/ralmon/samples`, `/ralmon/events` and `/ralmon/care_plan` with a test clock; the messages on `/ralmon/verdicts`, converted back, equal `run_offline` on the same day, record for record.
15. `test_rsm_rejects_tampered_plan_and_keeps_previous`: a plan with a broken signature is not loaded, the error is logged by exception type (`PlanIntegrityError`), the previous plan stays active, and a plan with a lower `plan_version` is refused (`PlanVersionError`).
16. `test_rsm_placement_filter`: with `placement=robot` no verdict for `range` is published; with `placement=ward` none for `sched`.
17. `test_attribution_node_publishes_update_results`: a `VIOLATED` record plus robot evidence and NODE_STATE events produce on `/ralmon/alerts` exactly the alerts returned by `RuleAttributor.update` for the same inputs, converted.
18. `test_watchdog_callbacks_publish_node_state_and_escalate_once`: invoking the liveliness-lost callback with a synthetic event object publishes one `Event` of kind `NODE_STATE` for the supervised node (payload keys of the trace evidence conventions) and calls the nurse port once; invoking it again without an intervening recovery does not call it again; a commanded lifecycle transition announced beforehand is not treated as a crash (analisi §4.6, row 15:00).
19. `test_event_manager_hides_cascade_effects_and_ranks`: alerts with `caused_by` set are not delivered as top-level; the delivered list is `rank_alerts` of the active top-level alerts; a `VIOLATED` alert with the same `instance_key` replaces a `PREDICTED_VIOLATION` alert.
20. `test_heartbeat_fields_and_sequence`: consecutive heartbeats carry the configured node id, strictly increasing sequence numbers and the ward-time `t_ms`.
21. `test_launch_files_declare_placement`: `ward.launch.py` declares RSM (`placement=ward`), attribution, event manager, watchdog supervising the robot and the ward heartbeat; `robot.launch.py` declares RSM (`placement=robot`), a watchdog supervising the ward node and the robot heartbeat; nothing else.
22. `test_qos_of_samples_and_heartbeat_declare_liveliness_and_deadline`: the QoS profiles built from `topics.py` for `/ralmon/samples` and `/ralmon/heartbeat` set a liveliness policy and a deadline taken from the parameter files.

Tier C (marker `ros_integration`, excluded from "Done when", run by WS07-T07): killing the robot process makes the ward watchdog report loss and the nurse port receive one escalation while ward monitoring continues; the robot leaving the room does not stop `/ralmon/verdicts` (the two continuity checks behind R3-W2).

## Passi

1. Verify unblock conditions; branch `ws05-t09-ros2-wrappers`; `status: in_progress`. Read the Contesto sources, decision D9 of the workstream README and the action policy (fallback to the nurse) of `docs/models/attribution-rule.md`; read the WS07-T01 completion note and record: distribution, build tool layout, whether messages need a separate package, and the marker registration.
2. Write the tier A and tier B tests; run `pytest ros2/ralmon_ros/test -q -m "not ros"`; watch them fail. Commit `WS05-T09: add failing wrapper tests`.
3. Write `msg/` (one message per contract type; optional fields as value plus `has_<field>`; `Event.payload` as typed key-value items so that bool, int, float and str survive), `topics.py` (topic names and QoS descriptors; heartbeat and samples with liveliness and deadline taken from parameters), `clock.py` and `converters.py` (pure field copying; the only arithmetic is the time conversion in `clock.py`).
4. Write the nodes, each a shell around one `ralmon` call:
   - `rsm_node` (parameters `placement`, `step_ms`, `reorder_delay_ms`, `registry_version`, `predictive`, `alpha`, `variant`, `ward_epoch_ms`, `require_signature`, the verification key path): subscriptions to samples, events and care plan call `push_sample`, `push_event`, `load`; a timer of period `step_ms` calls `advance` with the ward time and publishes each returned record on `/ralmon/verdicts`; the template subset comes from `placement.yaml` through `template_ids` of `StreamingMonitor`. It catches only `PlanIntegrityError` and `PlanVersionError`, logging by type.
   - `attribution_node`: feeds samples and events to an `EvidenceExtractor`, robot evidence to its `observe_robot_evidence`, and each `VIOLATED` or `PREDICTED_VIOLATION` record to `RuleAttributor.update`; publishes the returned alerts on `/ralmon/alerts`.
   - `event_manager_node`: keeps active top-level alerts by `instance_key`, orders them with `rank_alerts`, and delivers them through a `NursePort` (a small Protocol with a logging default; the concrete nurse interface is out of scope and no topic is added); it hides alerts with `caused_by` set (they stay available on `/ralmon/alerts`).
   - `watchdog_node`: subscribes to `/ralmon/heartbeat` of the supervised node with liveliness and deadline QoS; its event callbacks publish `Event(kind=NODE_STATE)` on `/ralmon/events` and, on loss, call `NursePort.escalate` once per transition (composed in one process with the event manager in `ward.launch.py`, so they share the port; the ADR records this); lifecycle transitions announced as commanded are not losses.
   - `heartbeat_node`: publishes node id, `next(counter)` and ward time at the configured period.
   Provide `RobotEvidencePublisher`, a thin class around the `/ralmon/robot_evidence` publisher and converter, for WS07-T04; this task does not implement perception or navigation.
5. Write launch files and `config/*.yaml` (values marked `provisional`; no clinical value; no default in code). Run `colcon build --packages-select ralmon_ros` (and the message package if split), source the install space, run the tests of both tiers until green; `ruff format ros2/ralmon_ros`, `ruff check ros2/ralmon_ros`.
6. Append the ADR (status `proposed`, confirmation tag): the placement table of test 9 (a proposal: ADR-003 fixes only "continuous phi_CP at the ward node, embodied specifications at the robot"; WS07 owns `#ros-2-interfaces` and may overturn it); `/ralmon/care_plan` QoS reliable and transient-local so a restarted RSM receives the current plan (the contract states QoS only for heartbeat and samples); the watchdog publishes NODE_STATE events on `/ralmon/events`; the definition of "no logic in a wrapper" of test 6; the message conventions (availability flags). List any contract gap found (no field for the plan verification failure as evidence) without editing the contract.
7. Run every command of "Done when" in the sourced workspace. Commit `WS05-T09: add ros2 wrappers`; set `status: done` and `status: ready` in the task files whose `depends_on` are now all `done`; tell WS07-T03 and WS07-T04 in the completion note the module names (`converters`, `RobotEvidencePublisher`) they import.

## Done when

From the repository root; steps needing ROS 2 run in the workspace sourced as in WS07-T01:

- `pytest ros2/ralmon_ros/test -q -m "not ros"` exits 0.
- `(cd ros2 && colcon build --packages-select ralmon_ros)` exits 0 (plus the message package if split), and `pytest ros2/ralmon_ros/test -q -m ros -rs` exits 0 with no skipped test.
- `ruff check ros2/ralmon_ros` and `ruff format --check ros2/ralmon_ros` exit 0.
- `! grep -rnE "^(import|from) rclpy" src/ralmon` succeeds.
- `! grep -rnE "from ralmon\.[a-z_]+\.[a-z_]+|import ralmon\.[a-z_]+\.[a-z_]+|import (numpy|scipy|sklearn|rtamt)|from (numpy|scipy|sklearn|rtamt)" ros2/ralmon_ros` succeeds.
- `ros2 launch ralmon_ros ward.launch.py --show-args` and `ros2 launch ralmon_ros robot.launch.py --show-args` exit 0.
- `python tools/check_plan.py` exits 0.

## Notes

### Hand-over (worker, 2026-10-09, from the WS05-T04 review)

(1) The availability of `presence` and `intake` must come from the robot `NODE_STATE` report with `payload.colocated` (H-MASK, H-INIT: a run starts with the robot not co-located) through `StreamingMonitor.push_availability(signal, available, t_device_ms, t_rx_ms)`, for both channels; ADR-054 (proposed) recommends it, and the offline path (`run_offline`, WS05-T08) must produce the same mask. Marking `presence` unavailable ends its held level. The owner of the `colocated` report is still open (WS04-T06 Fix round 1, M2). (2) The task text says `rsm_node` catches only `PlanIntegrityError` and `PlanVersionError`; `load` can also raise `PlanFeasibilityError` (a `MonitorConfigError`, not a subclass of those two: a plan that is trusted but cannot run, for example an anchor in the finalised past or a window off the grid), so catch `MonitorConfigError` as well, log it by type and keep the previous plan. (3) `advance` can raise `MonitorInvariantError` (an internal check, never for valid input); do not swallow it as a bad argument. (4) Load the plan before the first measurement or dispense: anchors that arrive with no plan create no instance and are counted in `stats().anchors_without_plan`.

### ADR-054 decided (gab, 2026-10-09)

Point (1) is settled by WS05-T11: pass the robot `NODE_STATE` events to `push_event` as they arrive; the monitor derives the availability of both channels itself. Do not call `push_availability` for the same report a second time.
