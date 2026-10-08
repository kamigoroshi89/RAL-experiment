---
id: WS07-T03
title: "Simulated devices as lifecycle nodes replaying benchmark traces"
workstream: WS07-ros2-sim
owner: agent
status: blocked
depends_on: ["WS07-T01", "WS04-T01", "WS05-T09"]
critical_path: true
non_negotiable: false
estimate_pd: 3
sources: ["analisi §5.2"]
interfaces: ["02-interfaces.md#ros-2-interfaces", "02-interfaces.md#trace-schema"]
review_items: []
---
## Obiettivo

Implement the sensing tier of the simulation (analisi §5.2 asks for simulated devices as lifecycle nodes that replay the benchmark traces and use the standard BLE blood-pressure profile as message model): a cuff, a dispenser and a wearable node that replay the `ObservedDay` of one patient, a simulated BLE gateway that turns device frames into `Sample` and `Event` messages on `/ralmon/samples` and `/ralmon/events`, a simulated back-end node that publishes the compressed and staggered care plan on `/ralmon/care_plan`, and the pure module `replay.py` with the README time base (compression and stagger), the trace partition, the BLE mapping, the robot-gated measurement mode and a seeded link drop model. Output: `ralmon_sim_msgs`, `replay.py`, `sim_devices.py`, `devices.yaml`, `devices.launch.py` and tests. The message mapping in Passi step 6 is normative: WS10-T02 makes its hardware bridge match it.

## Contesto

Blocked until WS05-T09 (message types, converters, ward-node consumers) and WS04-T01 (trace reader) are done; WS07-T01 fixes the distribution and package versions.

- `docs/source/analisi.md` §5.2 (devices, lifecycle transitions, kill, drops), §4.6 row 15:00 (a deliberate lifecycle transition is not a crash; crashes are detected by liveliness), §4.9 items 1 and 2 (placement, time semantics).
- `docs/plan/02-interfaces.md#trace-schema` (`ObservedDay`, `Sample`, `Event`, `EventKind`, two clocks) and `#ros-2-interfaces` (topics, liveliness and deadline QoS); `#signals` for the `SignalId` values.
- `docs/plan/workstreams/WS07-ros2-sim/README.md` (clock policy, internal interfaces, module map).
- `docs/models/evidence-channels.md` (WS02-T03: trace evidence conventions table that fixes the `Event.payload` keys of `NODE_STATE`, and the decision on a commanded flag)
- `ros2/ralmon_ros/` (WS05-T09: message types and converters; reuse them, do not redefine), the trace reader of WS04-T01 (`read_observed_day`, `read_benchmark_day`) and the benchmark layout of the WS04 README (`days/`, `truth/`, `plans/<care_plan_id>.json`).

## File toccati

- `ros2/ralmon_sim_msgs/` (create): package with `msg/BleBloodPressureMeasurement.msg`, `CMakeLists.txt`, `package.xml`.
- `ros2/ralmon_sim/ralmon_sim/replay.py` (create)
- `ros2/ralmon_sim/ralmon_sim/sim_devices.py` (create): `main_device`, `main_gateway`, `main_backend`.
- `ros2/ralmon_sim/config/devices.yaml` (create): device kinds, QoS, mode, transport delay, link model; required keys, no defaults.
- `ros2/ralmon_sim/launch/devices.launch.py` (create): argument `slots` (YAML list of patient slots: room, patient, day index, offset) so that WS07-T07 can launch N slots without a ward layout.
- `ros2/ralmon_sim/test/test_sim_devices.py` (create): pure tests and `ros` tests.

## Test

Write these first. Fixture days are built in code (`ObservedDay` with a few samples); values are labelled "test-only, not clinical".

Time base and transform (pure):
- `test_timebase_maps_trace_time_to_ward_time`: factor 30, `origin_ms` 1_000_000: t 3_600_000 gives 1_120_000; t 1_000 gives 1_000_033 (floor).
- `test_timebase_property_order_and_inverse`: (Hypothesis) `t1 <= t2` implies `to_ward(t1) <= to_ward(t2)`; for every ward time w at or after the origin, `to_ward(to_trace(w)) == w`.
- `test_timebase_rejects_invalid_factor_and_negative_origin`: factor 0, -1, 1.5 and origin -1 raise.
- `test_compress_plan_shifts_schedule_anchors_and_time_params`: plan with schedule [3_600_000, 7_200_000], one instance anchored at 3_600_000 with params `{"win": 1_800_000.0, "band": 140.0}` (registry names of the fixture registry), factor 30, origin 1_000_000, `win` listed as care-plan time: schedule [1_120_000, 1_240_000], anchor 1_120_000, `win` 60_000.0, `band` unchanged, `signature is None`, `patient_id` and `care_plan_id` unchanged.
- `test_compress_registry_scales_only_listed_entries`: fixture registry file in the WS01-T03 schema with `w` (ms, listed care-plan time, 1_800_000), `gap` (ms, listed physical, 800) and `band_hi` (mmHg): output values 60_000, 800 and unchanged.
- `test_compress_fails_on_unclassified_ms_entry`: an `ms` entry in neither list raises `TimebaseError` naming it (registry file and plan transform).
- `test_compressed_registry_loads_with_load_registry`: `ralmon.spec.load_registry` reads the written file; `get("w").value == 60_000.0`, `reviewed_by is None`, rationale mentions the factor.

Partition, BLE mapping, gating, link model (pure):
- `test_partition_assigns_each_item_to_exactly_one_owner`: a day with `bp`, `hr_pulse`, `meas`, `cuff_health`, `dispense`, `hr_ecg`, `sched_tick` and matching events is split into `cuff`, `dispenser`, `wearable`, `scheduler`; nothing is lost or duplicated.
- `test_robot_origin_and_node_state_items_not_replayed`: `intake`, `presence`, `robot_task` and every `node_state` item are excluded from replay (the simulation produces them); a derived signal (`dose_count`, `meas_count`, `bp_pre`, `bp_drop`) in the trace raises.
- `test_replay_accepts_only_observed_days`: passing a `LatentDay` raises `TypeError` (latent data never reaches a device).
- `test_emission_schedule_sorted_and_stable`: items at trace times [1_000, 2_000, 2_000] give ward times computed by the time base, sorted, ties in original order.
- `test_bp_group_builds_one_frame`: `bp` 137.0, `hr_pulse` 72.0, `meas` and a `measurement` event at one `t_device_ms` give one frame with `systolic_mmhg` 137.0, `pulse_rate` 72.0, `has_pulse_rate` true, `has_diastolic` false, `has_map` false, extension `seq` and `quality` copied.
- `test_frame_without_pulse_marks_pulse_unavailable`: no `hr_pulse` at that instant gives `has_pulse_rate` false.
- `test_gateway_reproduces_measurement_items`: decoding the frame returns the original `bp`, `hr_pulse`, `meas` samples and `measurement` event with equal fields except `t_rx_ms`.
- `test_gateway_t_rx_is_ward_time_plus_transport_delay`: reception at ward time 500 with transport delay 0 gives `t_rx_ms` 500 and with 250 gives 750 (test-only values).
- `test_gated_mode_holds_measurements_until_trigger`: two measurement groups; before any trigger nothing is emitted; a trigger at ward time 900 emits group 1 with every item restamped 900; a second trigger emits group 2; a third returns failure.
- `test_open_loop_mode_emits_at_trace_times`: the same day in `open_loop` emits both groups at their mapped times.
- `test_link_drop_model_extremes_and_seed`: probability 0.0 keeps 1000 of 1000, 1.0 keeps 0, the same seed gives identical decisions, seeds 0 and 1 differ.
- `test_link_drop_rate_close_to_probability`: probability 0.3, seed 0, 10_000 draws: rate within 0.02 of 0.3 (four standard deviations).
- `test_replay_schedule_is_deterministic`: two builds from one day and one time base serialise to identical JSON.
- `test_devices_config_requires_qos_mode_and_transport_delay`: removing `mode`, `transport_delay_ms`, `qos.liveliness_lease_ms` or `link.seed` raises `DeviceConfigError`; `mode` other than `open_loop` and `gated` raises.

Nodes (`ros` marker):
- `test_device_publishes_only_when_active`: nothing on the device topics while unconfigured or inactive; frames after activation.
- `test_items_during_inactive_period_are_not_replayed_after_reactivation`: deactivate for a span that covers one item, reactivate: the item is never emitted (the device was offline); activation after `origin_ms` is refused.
- `test_transition_becomes_node_state_event`: deactivating a device makes the gateway publish an `Event` with kind `NODE_STATE`, `source` the device id and the payload keys of the trace evidence conventions table; if the node was announced on `/ralmon_sim/supervisor/commands` first, the commanded marking chosen in WS02-T03 is set, otherwise it is not.
- `test_liveliness_loss_becomes_link_lost_event`: killing a device process makes the gateway publish a `NODE_STATE` link-lost event within the lease plus a margin, and a restored event when the device returns; deactivation alone does not lose liveliness.
- `test_gateway_topics_and_qos_match_contract`: `/ralmon/samples` and `/ralmon/events` exist with the liveliness and deadline QoS of `02-interfaces.md#ros-2-interfaces` (checked through the publisher info of the gateway).
- `test_link_drop_parameters_apply_at_runtime`: setting `link_drop_probability` to 1.0 through the parameter service stops forwarding; 0.0 restores it.
- `test_trigger_service_emits_next_measurement_in_gated_mode`.
- `test_backend_publishes_compressed_staggered_plan_transient_local`: a late-joining subscriber receives the derived plan (`signature` is `None`).

## Passi

1. Read the WS05-T09 message types and converters, the WS04-T01 trace reader, and how a `CarePlan` file `plans/<care_plan_id>.json` is read (the reader of WS04-T11, `open_benchmark` and `BenchmarkReader`, or a loader of WS05-T03; WS04-T11 is not a dependency of this task, so when neither exists the tests build `CarePlan` objects in code and the launch refuses a slot whose plan it cannot read, naming the missing reader), the evidence conventions table (payload keys of `NODE_STATE`, commanded marking) and the Bluetooth SIG Blood Pressure profile text (primary source).
2. Write the tests above; run `pytest ros2/ralmon_sim/test/test_sim_devices.py -q` and watch them fail.
3. Implement `replay.py` (pure, `@dataclass(frozen=True, slots=True)`, integer milliseconds, seeded `numpy.random.Generator` only): `Timebase(factor, origin_ms)` with `to_ward`, `to_trace`; `compress_plan` and `write_compressed_registry` (README clock policy, fail closed); `device_id`; `partition_day` (owner table below); `emission_schedule`; `bp_frames` and `frames_to_items`; `GatedCuff`; `LinkDropModel`; `load_device_config` with `DeviceConfigError`. Ownership table: `cuff` owns `bp`, `hr_pulse`, `meas`, `cuff_health`, `inflation_ms` and `measurement`, `measurement_missed`, `device_error`; `dispenser` owns `dispense`, `auth` and `dispense`; `wearable` owns `hr_ecg`, `spo2`; `scheduler` owns `sched_tick`, `day_end` and `schedule_tick`. A measurement group is every cuff item that shares the `t_device_ms` of a `bp` sample. Make the pure tests pass.
4. Create `ralmon_sim_msgs` with `BleBloodPressureMeasurement.msg`: transcribe the field list of the SIG Blood Pressure Measurement characteristic from the specification into the message, with the source URL and the date in the header comment (expected: systolic, diastolic, mean arterial pressure, time stamp, pulse rate, user id, measurement status; check against the text). Use the working names of the tests (`systolic_mmhg`, `pulse_rate`, `has_pulse_rate`, `has_diastolic`, `has_map`) and extend them with the specification's names for the remaining fields. Every optional profile field gets a `has_*` boolean. Fields of the trace that the profile lacks are declared extensions with their own `has_*` flag: `t_device_ms`, `seq`, `quality`. Diastolic and mean pressure are absent because the benchmark does not produce them; the message does not quantise to the profile's number format. List each deviation in the header comment (WS10-T02 records its own).
5. Implement `sim_devices.py`: `sim_device_node` (`rclpy` lifecycle node; configure loads the day and builds the schedule, activate starts the replay timer and enables the lifecycle publishers, deactivate stops it; items whose time passes while inactive are dropped; activation after `origin_ms` is refused; `mode: gated` exposes `/ralmon_sim/<device_id>/trigger_measurement`); `sim_gateway_node` (subscribes to device topics, applies `LinkDropModel` with parameters `link_drop_probability` and `link_seed`, stamps `t_rx_ms`, publishes on `/ralmon/samples` and `/ralmon/events` with the QoS of the contract, converts each device `<node>/transition_event` into a `NODE_STATE` event and each liveliness change into a link-lost or restored `NODE_STATE` event, reads `/ralmon_sim/supervisor/commands`); `sim_backend_node` (publishes the derived plan of each slot on `/ralmon/care_plan`, transient-local, unsigned). Convert messages with the WS05-T09 converters only.
6. Message mapping (normative for WS10-T02; keep it as `MESSAGE_MAPPING` in `replay.py` and check it in a test):

   | Trace item | Device side | Gateway output |
   |---|---|---|
   | `bp`, `hr_pulse`, `meas` samples and `measurement` event at one `t_device_ms` | one `BleBloodPressureMeasurement` on `/ralmon_sim/<id>/ble_bp` | `Sample` `bp`, `Sample` `hr_pulse` (if present), `Sample` `meas` (1.0), `Event` `measurement`; same `t_device_ms`, `seq`, `quality`; `t_rx_ms` = reception ward time plus transport delay |
   | other cuff samples and events (`cuff_health`, `inflation_ms`, `measurement_missed`, `device_error`) | contract-type message on `/ralmon_sim/<id>/samples` or `/events` | forwarded, `t_rx_ms` stamped |
   | dispenser and wearable items, scheduler items | same as above | same |
   | lifecycle transition of a device node | `<node>/transition_event` | `Event` `node_state` with the payload keys of the evidence conventions table |
   | liveliness lost or restored on a device publisher | none | `Event` `node_state` (link lost or restored) |

7. Write `devices.yaml` and `devices.launch.py` (spawn one device node per kind per slot, one gateway, one back-end; pass `ward_epoch_ms`, `use_sim_time`, the QoS and link parameters). Write the header of `devices.yaml`: every value with no source is a declared run parameter; deadline QoS is declared only for streams with an expected period and may be `null` for event-driven devices.
8. Make the node tests pass in the sourced environment. Run `ruff check ros2/ralmon_sim`, `ruff format ros2/ralmon_sim`, and commit `WS07-T03: simulated devices, gateway and time base`. If no plan reader exists yet, say so in the completion note for the plan lead.

## Done when

- `pytest ros2/ralmon_sim/test/test_sim_devices.py -q -m "not ros"` exits 0 (plain Python with `ralmon`).
- In the sourced ROS 2 environment: `pytest ros2/ralmon_sim/test/test_sim_devices.py -q -m ros` exits 0 and `(cd ros2 && colcon build --packages-select ralmon_sim_msgs ralmon_sim)` exits 0.
- `ruff check ros2/ralmon_sim` and `ruff format --check ros2/ralmon_sim` exit 0.
- `grep -rnE '^(import|from) rclpy' ros2/ralmon_sim/ralmon_sim/replay.py` prints nothing, and `grep -c "MESSAGE_MAPPING" ros2/ralmon_sim/ralmon_sim/replay.py` prints at least 1.
- `grep -nE 'TO''DO|TB''D|lo''rem|[?][?][?]' ros2/ralmon_sim_msgs/msg/BleBloodPressureMeasurement.msg` prints nothing and the file header names the SIG source and date.

## Notes

### Hand-over from the WS05-T03 review (orchestrator, 2026-10-09)

A compressed registry that this task writes for `ralmon.spec.load_registry` (test `test_compressed_registry_loads_with_load_registry`) must carry every top-level key (`registry_version`, `pathology`, `review_status`, `window_parameters`, `entries`, `derived`, `unset`), the `window_parameters` list, integral non-negative values for every unit `ms` entry, unit strings `mmHg`, `ms`, `dose` or `"1"`, the suffix `illustrative, unverified` in the `rationale` of every entry whose `reviewed_by` is null, and a `review_status` that agrees with the reviewers; a row whose `rationale` or `source_ref` starts with `FIXTURE-ONLY` needs `allow_fixture_only=True`. The loader refuses anything else with a `RegistryError`.
