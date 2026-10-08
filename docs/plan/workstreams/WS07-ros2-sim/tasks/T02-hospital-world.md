---
id: WS07-T02
title: "Gazebo hospital world with 4-8 rooms, staggered care plans, one robot"
workstream: WS07-ros2-sim
owner: agent
status: ready
depends_on: ["WS07-T01"]
critical_path: true
non_negotiable: false
estimate_pd: 3
sources: ["analisi §5.2"]
interfaces: ["02-interfaces.md#ros-2-interfaces"]
review_items: []
---
## Obiettivo

Deliver the ward environment of the scenario in analisi §5.2 (one robot, 4 to 8 rooms, staggered care plans): a Gazebo Harmonic (or the generation fixed by WS07-T01) hospital world with 4 to 8 patient rooms, an occupancy map, the Nav2 configuration and a launch file that brings up the world, one robot and Nav2 headless. The scenario is described by one validated file, `ward_scenario.yaml`, and its pure loader `ward_scenario.py`: rooms with door, bedside, bed and dispenser poses, one patient slot per room, the robot dock, a pose that cannot be reached, the compression factor and the per-room stagger offsets of the README clock policy, and the `MonitorConfig` values in ward-clock milliseconds. WS10-T01 mirrors one room of this world in the lab, so the pose names are stable. This task does not import `ralmon` (WS05 is not among its dependencies).

## Contesto

Blocked until WS07-T01 is done: its record `ros2/ralmon_sim/config/package_availability.yaml` fixes the world route (`hospital_world.decision`), the robot variant, the Gazebo generation and the versions to use.

- `docs/source/analisi.md` §5.2 (scenario, hospital world, Nav2, HuNavSim optional) and §4.1 item 4 (why several rooms with staggered plans matter: they make the robot's obligations compete).
- `docs/plan/workstreams/WS07-ros2-sim/README.md` (clock policy: `compression_factor`, `offset_ms`, `replay_start_ms`, `care_plan_time_entries`; module map).
- `docs/plan/03-decisions.md` ADR-003 (one robot, ward node fixed) and `docs/plan/02-interfaces.md#ros-2-interfaces`.
- `docs/plan/02-interfaces.md#time-and-units` (integer milliseconds, ADR-017).

## File toccati

- `ros2/ralmon_sim/ralmon_sim/ward_scenario.py` (create): `Pose2D`, `Room`, `WardScenario`, `ScenarioError`, `load_scenario`, `stagger_offsets`, `pose_is_free`, `reachable_from`.
- `ros2/ralmon_sim/config/ward_scenario.yaml` (create): the shipped scenario (a number of rooms in [4, 8], chosen and recorded in the file header).
- `ros2/ralmon_sim/worlds/` (create): the world SDF, the occupancy map (PGM plus map YAML), attribution and license notice; one directory because the files are generated together.
- `ros2/ralmon_sim/config/nav2_params.yaml` (create)
- `ros2/ralmon_sim/launch/sim_ward.launch.py` (create): arguments `scenario`, `headless`, `use_humans`.
- `ros2/ralmon_sim/test/test_ward_world.py` (create): pure tests and `ros` tests in one file.

## Test

Write these first. Pure tests build scenario files with `tmp_path`; numeric fixture values are labelled "test-only, not clinical".

- `test_load_scenario_accepts_four_to_eight_rooms`: scenarios with 4 and with 8 rooms load and return that many `Room` objects in file order.
- `test_load_scenario_rejects_three_and_nine_rooms`: 3 and 9 rooms raise `ScenarioError`.
- `test_room_ids_and_patient_slots_unique`: a duplicate room id, or a duplicate (`patient_id`, `day_index`) pair, raises.
- `test_required_keys_have_no_defaults`: removing any of `compression_factor`, `replay_start_ms`, `stagger`, `monitor.step_ms`, `monitor.reorder_delay_ms`, `dock`, `unreachable_pose`, `time_entries.care_plan_time_entries`, `time_entries.physical_time_entries` raises `ScenarioError` naming the key.
- `test_compression_factor_is_integer_at_least_one`: 1 and 30 accepted; 0, -1, 1.5 and "30" rejected.
- `test_stagger_offsets_from_spacing`: `stagger_offsets(n_rooms=4, spacing_ms=900_000)` equals `[0, 900_000, 1_800_000, 2_700_000]`; spacing 0 or negative raises.
- `test_explicit_room_offsets_override_and_must_be_distinct`: explicit `offset_ms` values replace generated ones; two equal offsets raise; a negative offset raises.
- `test_time_entry_lists_are_disjoint`: a registry name in both `care_plan_time_entries` and `physical_time_entries` raises.
- `test_room_poses_in_free_cells_of_map`: for the shipped scenario, every door pose, bedside pose and the dock pose falls on a free cell of the shipped map (bed and dispenser poses are furniture positions and are not required to be free), using the map YAML fields `resolution`, `origin`, `negate` and `free_thresh` and a numpy parse of the PGM.
- `test_unreachable_pose_is_occupied_or_outside_map`: the `unreachable_pose` is on an occupied cell or outside the map bounds.
- `test_every_door_connected_to_dock_in_free_space`: an 8-connected search over free cells from the dock reaches every door pose.
- `test_shipped_scenario_room_count_recorded`: the number of rooms equals the count written in the header comment of `ward_scenario.yaml` and lies in [4, 8].
- `ros` marker: `test_world_publishes_clock_headless` (launch `sim_ward.launch.py headless:=true`; `/clock` advances within the timeout of the scenario file); `test_robot_reaches_every_room_door` (a `NavigateToPose` goal to each door pose ends in success within the scenario's `nav_goal_timeout_ms`); `test_unreachable_pose_goal_does_not_succeed` (aborted, cancelled or rejected).

## Passi

1. Read the T01 record: route, robot variant, Gazebo generation, versions. Write the tests above (pure tests first, with fixtures for 3, 4, 8 and 9 rooms) and watch them fail.
2. Implement `ward_scenario.py`: dataclasses (`@dataclass(frozen=True, slots=True)`), strict loader (every required key, types, ranges, no defaults, errors name the key), `stagger_offsets`, `pose_is_free` and `reachable_from` on a numpy occupancy grid. Make the pure tests pass.
3. Build the world by the T01 decision. `port_aws`: convert the hospital world to SDF for the target Gazebo generation, keep only the rooms needed, keep the license and attribution in a notice file. `use_ros2_branch`: adapt the ROS 2 branch. `procedural`: write a deterministic generator (no randomness) that builds a corridor with N rooms from the layout. Either way each room has a door, a bed, a bedside standing pose for the robot and a dispenser position; dynamic humans are not required.
4. Produce the occupancy map for that world by a recorded method (rasterise the collision geometry or run a mapping pass) and store the map YAML and PGM next to the world.
5. Write `ward_scenario.yaml` with the rooms, poses in the map frame, dock, `unreachable_pose` inside a wall, `compression_factor`, `replay_start_ms`, stagger (spacing or explicit offsets), `monitor` (`step_ms`, `reorder_delay_ms`, `predictive`, `alpha`, `variant`, `registry_version`), `time_entries`, `nav_goal_timeout_ms` and the (`patient_id`, `day_index`) slot of each room taken from the benchmark manifest. Every value with no source is written as a declared run parameter with a comment saying so; no clinical value appears. Write the number of rooms in the header comment.
6. Write `nav2_params.yaml` from the robot package's Nav2 configuration (T01 record), with the map path and `use_sim_time` true, and `sim_ward.launch.py`: start Gazebo (headless option), spawn the robot at the dock, start Nav2 with the map and localisation, pass `ward_epoch_ms` 0. Add `use_humans` only if the T01 record marks `human_sim` available; otherwise the argument is absent and the limitation is stated in the file header.
7. Write the ROS tests and run them; fix launch, map or parameters until the robot reaches every door and fails on the unreachable pose. Record the dry-drive time from dock to the farthest door in the scenario header (an input to the choice of `compression_factor`, README clock policy).
8. Run `ruff check ros2/ralmon_sim`, `ruff format ros2/ralmon_sim`, and commit `WS07-T02: hospital world, ward scenario and Nav2 bring-up`. Tell the owner of WS10-T01 that the room pose names are frozen.

## Done when

- `pytest ros2/ralmon_sim/test/test_ward_world.py -q -m "not ros"` exits 0.
- In the sourced ROS 2 environment: `pytest ros2/ralmon_sim/test/test_ward_world.py -q -m ros` exits 0.
- `ruff check ros2/ralmon_sim` and `ruff format --check ros2/ralmon_sim` exit 0.
- `PYTHONPATH=ros2/ralmon_sim python -c "from ralmon_sim.ward_scenario import load_scenario; s = load_scenario('ros2/ralmon_sim/config/ward_scenario.yaml'); assert 4 <= len(s.rooms) <= 8"` exits 0.
- `test -f ros2/ralmon_sim/worlds/NOTICE` (attribution and license, or the statement that the world is generated) exits 0.
- `grep -rnE '^(import|from) ralmon' ros2/ralmon_sim/ralmon_sim/ward_scenario.py` prints nothing.
