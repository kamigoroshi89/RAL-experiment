# WS07-ros2-sim: ROS 2 simulation

## Objective

Build the simulation tier of the technical validation (analisi §5.2, roadmap §9 item 7): a Gazebo hospital ward with 4 to 8 rooms, one assistive robot driven by Nav2, staggered patient care plans, simulated smart medical devices that replay benchmark traces as ROS 2 lifecycle nodes with the standard BLE blood-pressure profile as message model, robot tasks that realise the obligations induced by φ_resp and φ_sched (analisi §4.1 item 4; the obligation record is defined by WS01-T02) together with a witness perception stub with a declared error model, fault injection (lifecycle transitions, process kill, message drops, localisation noise, impossible navigation goals), conformal predictive monitoring of care-delivery deadlines (analisi §4.3), and measurements (end-to-end latency p50, p95, p99 with ros2_tracing, CPU and memory on hardware equivalent to the onboard computer, throughput with N patients times M template instances).

Why it exists: the analysis rates the ROS 2 simulation with robot faults and latency as indispensable for the RA-L fit (analisi §5.8) and uses it to answer objection 3 "the robot is not needed" (analisi §10): the robot executes obligations derived from the specification, is the only witness channel, and its lateness is the target of the genuinely robotic use of prediction. The workstream also gives the evidence behind reviewer finding R3-W2 (what happens when the robot leaves the room or fails; the answer is the ward node of ADR-003) and R2-W5 (prediction is moved from five-a-day blood pressure to robot deadlines).

Scope split (ADR-014): the `ralmon` core stays ROS-independent and the thin ROS 2 wrappers (RSM, attribution, event manager, watchdog, heartbeat, ward-node placement, message types, converters) are built by WS05-T09. WS07 owns the simulation environment, the robot task layer, the fault injection and the measurements. WS05-T09 depends on WS07-T01 (package availability), so WS07-T01 must not depend on WS05.

Vocabulary used below: a **node** is a ROS 2 process; the **ward node** is the fixed BLE gateway plus RSM of ADR-003; **on-path** means between a sample and its alert (gateway, RSM, attribution, event manager), **off-path** means the back-end (care-plan and model distribution), which is not required to produce an alert. Latency is reported for the on-path components only.

## Inputs

- Contracts (read in full by the tasks that cite them): `02-interfaces.md#ros-2-interfaces` (owned here), `#trace-schema`, `#evidencevector`, `#forecaster`, `#conformal-calibrator`, `#metrics`; read-only support: `#time-and-units`, `#signals`, `#template`, `#verdict`, `#alert`, `#monitor`.
- Human artefact: `docs/plan/workstreams/WS00-admin/outputs/WS00-T05.md` (robot availability, distribution and Gazebo compatibility, TIAGo Pro model, onboard computer specifications, ADR-011 decision).
- WS05 artefacts: the ROS 2 wrapper packages of WS05-T09 (message types for the `/ralmon/*` topics, converters, ward-node launch, heartbeat and watchdog nodes); `ralmon.spec` (registry and template loaders, `CarePlan`); `ralmon.monitor`; the forecaster and its ADR (WS05-T05); the conformal calibrator (WS05-T06).
- WS04 artefacts: the trace reader and the benchmark manifest (WS04-T01, WS04-T11).
- WS02 artefacts (transitive, through WS05-T07): `docs/models/fault-model.md` (fault vocabulary, fault-to-evidence table, injection parameter sheet) and `docs/models/evidence-channels.md` (evidence semantics and the trace evidence conventions table that fixes `Event.payload` keys).
- External software, verified by WS07-T01, never assumed: ROS 2 Jazzy with Gazebo Harmonic (ADR-011), the ROS-Gazebo bridge, Nav2, PAL TIAGo or TIAGo Pro simulation packages, a hospital world (analisi §5.2 names the AWS RoboMaker hospital world), HuNavSim (optional), ros2_tracing with LTTng, `tc netem`.

## Outputs

### Package layout and module map

Code lives under `ros2/` (`01-conventions.md` section 1). WS07-T01 creates the colcon workspace and declares every console-script entry point below in `ros2/ralmon_sim/setup.py`, so later tasks do not edit `setup.py`. Pure modules never import `rclpy`; they import `ralmon` only through package roots (`02-interfaces.md#package-public-api`). Node modules are thin adapters around the pure modules. No monitoring logic is written here: nothing under `ros2/ralmon_sim/` imports `rtamt` or evaluates a template.

| Module (`ros2/ralmon_sim/ralmon_sim/`) | Kind | Console scripts (`name = module:function`) | Task |
|---|---|---|---|
| `ward_scenario.py` | pure | none | WS07-T02 |
| `replay.py` (time base, plan and registry transform, trace partition, BLE mapping, gating, link drop model) | pure | none | WS07-T03 |
| `sim_devices.py` | node | `sim_device_node = ralmon_sim.sim_devices:main_device`, `sim_gateway_node = ralmon_sim.sim_devices:main_gateway`, `sim_backend_node = ralmon_sim.sim_devices:main_backend` | WS07-T03 |
| `robot_tasks.py` | pure | none | WS07-T04 |
| `witness_stub.py` (simulated perception, used inside the robot process) | pure | none | WS07-T04 |
| `robot_task_node.py` | node | `robot_task_node = ralmon_sim.robot_task_node:main` | WS07-T04 |
| `fault_injection.py` | pure | none | WS07-T05 |
| `fault_injector.py` | node | `fault_injector_node = ralmon_sim.fault_injector:main` | WS07-T05 |
| `deadline_prediction.py` | pure and CLI | `deadline_prediction = ralmon_sim.deadline_prediction:main` | WS07-T06 |
| `deadline_logger.py` | node | `deadline_logger_node = ralmon_sim.deadline_logger:main` | WS07-T06 |
| `measure.py` | pure | none | WS07-T07 |
| `measure_runner.py` | orchestration | `measure_run = ralmon_sim.measure_runner:main` | WS07-T07 |

Other trees: `ros2/ralmon_sim_msgs/` (WS07-T03, device-side message types), `ros2/ralmon_sim/{launch,config,worlds,scripts,doc,test}/`. Tests: pure tests run with plain `pytest` and `ralmon` installed; tests that need ROS 2 carry the marker `ros` and are skipped when `rclpy` cannot be imported (marker registered in `ros2/ralmon_sim/test/conftest.py`, WS07-T01).

### Simulation-internal interfaces (names are stable inside WS07)

The `/ralmon/*` topics and their QoS stay exactly as in `02-interfaces.md#ros-2-interfaces`. The interfaces below live in the `/ralmon_sim/` namespace and are not part of that contract. `Sample`, `Event` and the other contract types travel in the ROS 2 message types created by WS05-T09; WS07 imports them and never redefines them.

| Interface | Type | From, to | Defined by, used by |
|---|---|---|---|
| `/ralmon_sim/<device_id>/ble_bp` | `ralmon_sim_msgs/BleBloodPressureMeasurement` | cuff device node, gateway | T03 |
| `/ralmon_sim/<device_id>/samples`, `/ralmon_sim/<device_id>/events` | WS05-T09 `Sample` and `Event` messages | device nodes, gateway | T03 |
| `/ralmon_sim/<device_id>/trigger_measurement` | service `std_srvs/Trigger` | robot task node, cuff device node (gated mode) | T03, T04 |
| `<node>/change_state`, `<node>/transition_event` | standard `lifecycle_msgs` interfaces | fault injector to node; node to gateway (converted to `EventKind.NODE_STATE`) | T03, T05 |
| `/ralmon_sim/supervisor/commands` | `std_msgs/String` (node name announced before a commanded transition) | supervisor or injector, gateway | T03, T05 |
| gateway parameters `link_drop_probability`, `link_seed` | ROS 2 parameters (standard `SetParameters` service) | fault injector, gateway | T03, T05 |
| `/ralmon_sim/robot/state_samples` | `Sample` | robot task node, deadline logger | T04, T06 |
| `/ralmon_sim/fault/goal_override` | `geometry_msgs/PoseStamped` | fault injector, robot task node (`impossible_goal`) | T04, T05 |
| `/ralmon_sim/fault/nav_delay` | `std_msgs/Int64` (extra delay in ms before the next navigation starts; 0 clears) | fault injector, robot task node (`nav_delay`) | T04, T05 |

Device identifiers follow `device_id(room_id, kind)` in `replay.py` (`kind` in `cuff`, `dispenser`, `wearable`).

### Clocks, compression and staggering (one policy for all tasks)

WS07 follows the policy of WS10 (`WS10-lab-demo/README.md`, shared decision 3) so that simulation and lab are comparable.

1. **One real clock.** The ward clock is the ROS 2 clock in integer milliseconds. With Gazebo it is the simulation clock (`use_sim_time:=true`, ward time 0 at simulation start); in profiles without Gazebo it is the system clock minus a launch-time reference. Every node receives the parameter `ward_epoch_ms` (ROS-clock milliseconds that correspond to ward time 0; 0 under simulated time) from the launch file.
2. **Compression is a data transform, not a second clock.** The scenario declares an integer `compression_factor` F at least 1 (1 means no compression) and a per-room `offset_ms` (stagger). A trace timestamp t of a patient-day maps to ward time `origin_ms + t // F`, where `origin_ms = replay_start_ms + offset_ms`. Care-plan schedule ticks and anchors follow the same map; registry entries with unit `ms` are divided by F only if the scenario lists them under `care_plan_time_entries`; entries under `physical_time_entries` are unchanged; an unlisted `ms` entry is an error (fail closed, as in WS10-T04). Compressed registries and plans are derived artefacts: `reviewed_by` is `None` and the plan `signature` is `None` (ADR-020); the signed plan path is tested by WS05-T03, not here.
3. **Measures are wall-clock.** Latency and resource figures come from ros2_tracing and process accounting on the steady clock and are never rescaled by F. Robot motion, DDS transport and device physics are not compressed, so F is a validity threat: WS07-T04 and WS07-T07 report whether nominal robot task durations fit inside the compressed windows.
4. **`MonitorConfig` values** (`step_ms`, `reorder_delay_ms`) are stated in ward-clock milliseconds in the scenario file.

### Artefacts

- `ros2/ralmon_sim/config/package_availability.yaml` and `doc/availability.md` (T01); `config/ward_scenario.yaml`, `worlds/` (T02); `config/devices.yaml` (T03); `config/robot_tasks.yaml` (T04); `config/fault_schedules/` (T05); `config/experiments/ws07_deadline.yaml`, `config/experiments/ws07_latency.yaml` (T06, T07). These are WS07-local; `experiments/` stays reserved for WS08.
- Run outputs follow `01-conventions.md` section 9: `outputs/ws07-deadline/<seed>/` (T06) and `outputs/ws07-latency/<seed>/` (T07), each with `config.yaml`, `metrics.json`, `git_rev.txt`; T07 adds `fault_matrix.json`, `robot_arrival_delay.json` (plain JSON list of non-negative delays in ms, from runs with compression factor 1) and its `.meta.json`. `outputs/` is never committed.
- Deterministic components (replay schedule, fault expansion, witness draws, drop draws) are reproducible byte for byte from an explicit seed (`numpy.random.Generator`). Wall-clock metrics are not bit-reproducible; they are reported with the spread over at least 5 seeds (analisi §5.1) and the machine description.

### Declared assumptions (each is repeated in the paper limitations)

Witness perception is a stub whose error rates are configuration values with no defaults; the manipulation step is an abstract assist step of declared duration and there is no manipulation fault in simulation (analisi §5.2 lists none); there is no battery model, so `system.battery_low` is unavailable (`None`) in simulation runs; the robot schedules obligations with a declared non-preemptive earliest-deadline-first policy; the cuff replay does not quantise to the BLE SFLOAT format and lacks diastolic and mean pressure, which the benchmark does not produce; the timeline compression factor is a validity threat (clock policy, point 3).

## Dependencies

- Upstream, declared in INDEX: WS00-T05 (human) for WS07-T01; WS04-T01 (trace reader) and WS05-T09 (wrappers) for WS07-T03 and WS07-T04; WS05-T06 (conformal calibrator) for WS07-T06. Transitive and relied on: WS05-T05 (forecaster and its ADR), WS05-T08 (`run_offline`), WS02-T01 and WS02-T03 (fault model and evidence conventions), WS01-T02 and WS01-T03 (template table and registry).
- Downstream: WS05-T09 needs WS07-T01; WS10-T01 needs WS07-T02 (the lab room mirrors a world room); WS10-T02 reuses the message mapping of WS07-T03; WS10-T04 needs WS07-T04; WS12 takes the latency numbers from WS07-T07.
- Contract anchors: `#ros-2-interfaces` (owner), `#trace-schema`, `#evidencevector`, `#forecaster`, `#conformal-calibrator`, `#metrics`.
- Undeclared preconditions, reported to the plan lead: WS07-T06 and WS07-T07 cite `#forecaster`, `#conformal-calibrator` and `#metrics` but no dependency leads to WS08-T01 (`ralmon.eval`); both therefore compute their figures with local code and cross-check against `ralmon.eval` only if it is importable. WS07-T06 needs a benchmark version with many patients (WS04-T11) and no dependency reaches it; its real runs stop and report if none exists. WS07-T03 reads care-plan files written by WS04-T11 and falls back to plans built in code in tests. Analisi §5.1 (2) takes the robot arrival jitter of the benchmark from this simulation and WS04-T06 reads it through `EmpiricalJitter(path)` without depending on WS07; WS07-T07 exports the file `robot_arrival_delay.json` in that reader's format. Time compression follows WS10; the classification of `ms` registry entries is implemented once here (WS07-T03) and again in WS10-T04, which is duplicated work to reconcile.

## Acceptance criteria

Commands run from the repository root; ROS 2 commands need the sourced workspace.

1. `pytest ros2/ralmon_sim/test -q -m "not ros"` exits 0 with plain Python and `ralmon` installed.
2. `pytest ros2/ralmon_sim/test -q -m ros` exits 0 in the sourced ROS 2 environment recorded by `config/package_availability.yaml`.
3. `(cd ros2 && colcon build --packages-select ralmon_sim_msgs ralmon_sim)` exits 0; `ruff check ros2/ralmon_sim` and `ruff format --check ros2/ralmon_sim` exit 0.
4. Layering holds: `! grep -rnE "^(import|from) rclpy" src/ralmon` and `! grep -rnE "import rtamt|from rtamt|from ralmon\.[a-z_]+\.[a-z_]+|import ralmon\.[a-z_]+\.[a-z_]+" ros2/ralmon_sim` both succeed.
5. `ros2/ralmon_sim/config/package_availability.yaml` records, with evidence, the status of every required component and a verdict on ADR-011; `doc/availability.md` lists what remains unverified.
6. `config/ward_scenario.yaml` declares between 4 and 8 rooms with staggered care plans; the headless launch brings up the world, Nav2 and the robot, and the robot reaches every room door (WS07-T02 ROS tests).
7. A fault-free run of the full scenario gives every derived obligation exactly one `ROBOT_TASK` outcome event, publishes witness observations that are `None` whenever the robot is not co-located, and never publishes any field that exists only in `LatentDay` (WS07-T04).
8. `outputs/ws07-latency/<seed>/fault_matrix.json` has one entry for each of the six fault kinds and the commanded-transition control of WS07-T05, each with the observed symptoms and the alert (if any) with its attributed cause; the two continuity checks of R3-W2 (robot away or killed while ward monitoring continues) pass.
9. `outputs/ws07-deadline/<seed>/metrics.json` reports, per lead time and per alpha, the number of calibration and test episodes, the false predictive alarm rate, the recall of eventual violations and the lead time distribution, computed from patient-split episodes; the result is reported even when no alert can be emitted.
10. `outputs/ws07-latency/<seed>/metrics.json` reports `latency_percentiles` (p50, p95, p99), per-process CPU and memory, the throughput grid over N and M, the hardware profile and the tracing tool versions, for at least 5 seeds.
11. `grep -rnE 'TO''DO|TB''D|lo''rem|[?][?][?]' docs/plan/workstreams/WS07-ros2-sim` prints nothing; every configuration key without a source is a required parameter with no default (each config loader has a test that a missing key raises).

## Source sections

- analisi §5.2 (simulation setup: ROS 2, Gazebo, Nav2, hospital world, PAL packages, simulated devices, fault injection, scenario, measures), §4.1 item 4 (measurement obligations induced by φ_resp), §4.3 (last paragraphs: predictive monitoring of care-delivery deadlines), §4.4 (definition of ρ for predicted violations), §4.5 (system health and embodied witness evidence), §4.6 (row 15:00: a deliberate transition is not a crash), §4.9 items 1 and 2 (architecture, time semantics).
- analisi §5.1 (2) and (3) (robot arrival jitter from simulation; C2 injections), §5.5 (system metrics), §5.8 (status of the ROS 2 simulation), §9 items 0.7 and 7, §10 objection 3.
- Reviewer findings: R3-W2, AE-4 (WS07-T04); R2-W5 (WS07-T06); supporting evidence for R3-W2 in WS07-T07.
- ADR-003, ADR-011, ADR-014, ADR-017, ADR-020.

## Tasks

| id | title | owner | status | depends_on |
|---|---|---|---|---|
| WS07-T01 | Package availability check and simulation workspace | agent | blocked | WS00-T05 |
| WS07-T02 | Gazebo hospital world with 4-8 rooms, staggered care plans, one robot | agent | blocked | WS07-T01 |
| WS07-T03 | Simulated devices as lifecycle nodes replaying benchmark traces | agent | blocked | WS07-T01, WS04-T01, WS05-T09 |
| WS07-T04 | Robot task layer: care obligations, navigation, witness perception | agent | blocked | WS07-T02, WS07-T03, WS05-T09, WS05-T05 |
| WS07-T05 | Robot and link fault injection | agent | blocked | WS07-T03 |
| WS07-T06 | Predictive monitoring of care-delivery deadlines | agent | blocked | WS07-T04, WS05-T06, WS05-T05, WS08-T01, WS04-T11 |
| WS07-T07 | Latency, resource and scalability measurement | agent | blocked | WS07-T05, WS07-T06, WS08-T01 |

Total estimate: 18.0 person-days.
