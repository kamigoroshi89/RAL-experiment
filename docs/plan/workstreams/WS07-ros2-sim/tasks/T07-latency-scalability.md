---
id: WS07-T07
title: "Latency, resource and scalability measurement"
workstream: WS07-ros2-sim
owner: agent
status: blocked
depends_on: ["WS07-T05", "WS07-T06", "WS08-T01"]
critical_path: true
non_negotiable: false
estimate_pd: 2.5
sources: ["analisi §5.2", "analisi §5.5"]
interfaces: ["02-interfaces.md#ros-2-interfaces", "02-interfaces.md#metrics"]
review_items: []
---
## Obiettivo

Produce the system measures of analisi §5.2 and §5.5 for the on-path pipeline (gateway, RSM, attribution, event manager): end-to-end latency from a sample to its alert as p50, p95 and p99 measured with ros2_tracing, CPU and memory per process on hardware equivalent to the onboard computer (specification from the WS07-T01 record), and throughput with N patients times M template instances in parallel, including the saturation point. The task also completes the fault work of WS07-T05 on the full scenario: it runs all six fault kinds and the commanded-transition control end to end, records the observed symptoms and the resulting alerts in `fault_matrix.json`, checks the two architecture-continuity cases behind R3-W2 (robot away, robot killed, ward monitoring continues and the loss of the heartbeat is C2 evidence), and exports the measured robot arrival delays for WS04-T06, which reads them through `EmpiricalJitter(path)` (a JSON list of non-negative delays in milliseconds). Output: `measure.py`, `measure_runner.py`, `ws07_latency.yaml`, `doc/measurement-method.md`, and `outputs/ws07-latency/<seed>/{config.yaml, metrics.json, git_rev.txt, fault_matrix.json, robot_arrival_delay.json, robot_arrival_delay.meta.json}`. These numbers are simulation on onboard-equivalent hardware; latency on the real robot is measured in WS10-T05.

## Contesto

Blocked until WS07-T05 and WS07-T06 are done.

- `docs/source/analisi.md` §5.2 (measures: end-to-end latency with ros2_tracing p50, p95, p99; CPU and memory on onboard-equivalent hardware; throughput N patients times M templates) and §5.5 (system metrics), §5.1 (2) (robot arrival jitter is taken from simulation).
- `docs/plan/02-interfaces.md#ros-2-interfaces` (topics, QoS, heartbeat) and `#metrics` (`latency_percentiles` returns p50, p95, p99); `#time-and-units` (verdict latency is defined against `t_device_ms`; wall-clock latency here is a different quantity and is reported as such).
- `docs/plan/workstreams/WS07-ros2-sim/README.md` (clock policy: measures are wall-clock and never rescaled; reproducibility rules) and the T05 task file (oracle, schedules) and T06 outputs.
- `ros2/ralmon_sim/config/package_availability.yaml` (WS07-T01: tracing tools, onboard computer specification, RMW and netem findings) and `docs/plan/workstreams/WS00-admin/outputs/WS00-T05.md` (equivalent hardware, if any).
- `ros2/ralmon_ros/` (WS05-T09: alert message fields, event manager escalation path, RSM step callback).

## File toccati

- `ros2/ralmon_sim/ralmon_sim/measure.py` (create): pure analysis of normalised trace events and resource samples.
- `ros2/ralmon_sim/ralmon_sim/measure_runner.py` (create): `main` for `measure_run`; workloads `latency`, `resources`, `throughput`, `fault_matrix`, `arrival_delay`.
- `ros2/ralmon_sim/config/experiments/ws07_latency.yaml` (create): seeds, workload parameters, grids, duration; required keys, no defaults.
- `ros2/ralmon_sim/test/test_measure.py` (create): pure tests.
- `ros2/ralmon_sim/test/test_fault_matrix_e2e.py` (create): `ros` tests on the full scenario.
- `ros2/ralmon_sim/doc/measurement-method.md` (create): method, hardware profile, limitations, for the paper.

## Test

Write these first. `measure.py` reads a normalised JSON-lines event file (`{"ts_ns": int, "event": "publish" | "callback_start" | "callback_end", "node": str, "topic": str | null}`), produced by the runner from the ros2_tracing session; fixtures are hand-built. Values are test-only.

- `test_probe_day_uses_registry_upper_bound_and_isolates_probes`: `make_probe_day` with `bounds_upper` 250.0, three probes, period 10_000 ms and start 5_000 ms gives `bp` samples at 5_000, 15_000, 25_000 with value 250.0 and `seq` 0, 1, 2 (violating the range band by construction, without a clinical constant of its own; the upper bound comes from `ParameterRegistry.bounds` in the runner).
- `test_latency_pairs_probe_with_next_alert`: probe publishes at 1_000_000_000 ns and 3_000_000_000 ns, alerts at 1_012_000_000 ns and 3_020_000_000 ns give latencies 12.0 ms and 20.0 ms.
- `test_unmatched_probe_is_counted_lost_and_overlap_is_invalid`: a probe with no alert before the next probe is counted in `n_lost`; if an alert arrives after the next probe's publish, the run is flagged `probe_overlap` and excluded.
- `test_percentiles_hand_computed`: latencies [10, 20, 30, 40, 50] ms give p50 30.0, p95 48.0, p99 49.6 (linear interpolation; the method name is in the report).
- `test_hop_breakdown_sums_to_total`: hop timestamps 0, 4, 9, 15 ms give hops 4, 5, 6 ms summing to 15 ms.
- `test_step_processing_time_and_overrun_rate`: callback pairs of durations 1, 2, 3, 9 ms with step 5 ms give overrun rate 0.25 and p50 2.5 ms.
- `test_saturation_point_is_first_overrun_cell`: a hand-built grid over N in {1, 2, 4} and M in {1, 2} with overrun in (2, 2) and (4, 2) gives (2, 2) as the saturation point (the overrun cell with the smallest N times M); a grid without overrun gives `null` and the text "not reached within the grid".
- `test_replicate_instances_unique_keys_and_cycle`: a plan with three instances replicated to M = 7 has seven instances with unique `instance_key` values, the first three unchanged and the rest cycling through them; the derived plan has `signature` `None`.
- `test_cpu_and_memory_summary`: CPU samples [10.0, 20.0, 30.0] give mean 20.0 and max 30.0; resident memory samples of 104_857_600 and 125_829_120 bytes give a peak of 120.0 MiB.
- `test_hardware_profile_records_limits_and_privilege`: a T01 onboard record with `cores` 4 and `ram_gb` 8 (test-only) and an unprivileged host gives an affinity set of 4 cores, `memory_limit_applied` false and `equivalence` `emulated`; a config flag for an equivalent machine gives `equivalent_machine`; a record with `not stated in <source>` fields gives `equivalence` `none` and no limit.
- `test_arrival_delay_export`: `ROBOT_TASK` outcome events of `measure_bp` obligations with `sim_arrival_delay_ms` 50_000, -10_000, 0 give the list [50_000, 0, 0] (an arrival before the window start counts as zero delay) and a meta record with `compression_factor`, seeds, scenario file and the sha256 of the list.
- `test_arrival_delay_export_refuses_compressed_runs`: events from a run with `compression_factor` 30 raise `ExportError` (robot travel and queueing are physical, so delays are exported only from runs with factor 1, where ward time is real time).
- `test_deterministic_artifacts_are_byte_identical`: the probe day, the slot expansion for N patients and the replicated plans serialise identically on two builds with one seed.
- `test_metrics_layout_and_keys`: `metrics.json` has `latency_percentiles` (p50, p95, p99), `percentile_method`, `n_probes`, `n_matched`, `n_lost`, `hop_breakdown_ms`, `cpu_percent`, `rss_mib`, `throughput_grid`, `saturation_point`, `hardware_profile`, `tools`, `compression_factor`, `rtf`, and per-seed spread; the run directory has the files named in the Objective.
- `test_headline_config_has_at_least_five_seeds` and `test_config_requires_all_keys`: fewer than 5 seeds or a missing key raises `MeasureConfigError`.
- `test_percentiles_agree_with_ralmon_eval_if_available`: agreement with `ralmon.eval.latency_percentiles` on the fixture, skipped if `ralmon.eval` is not importable (WS08-T01 is not a dependency of this task).
- `ros` marker (`test_fault_matrix_e2e.py`): `test_each_fault_kind_shows_its_ros_symptoms` (parametrised over the schedules of WS07-T05; every entry of `ros_symptoms` in the oracle is observed); `test_robot_side_faults_end_to_end` (`impossible_goal` gives a failed navigation outcome and `nav_task_failed` true in the robot evidence; `nav_delay` increases the arrival delay by at least the injected delay minus the declared tolerance; `localisation_noise` is applied and logged, with late or failed outcomes recorded, not asserted); `test_devices_stream_continues_while_robot_away` (a probe on a device produces an alert while the witness fields are `None`); `test_robot_kill_keeps_ward_monitoring_and_raises_heartbeat_evidence` (after `process_kill` on the `robot` group: heartbeat gap observed, a probe still produces an alert within `continuity_timeout_ms`, and the nurse escalation of WS05-T09 is triggered); `test_fault_matrix_rows_are_complete` (one row for each of the seven schedule kinds with observed symptoms, alert presence, attributed cause and `evidence_used`; the attributed cause is recorded, not asserted).

## Passi

1. Read the Contesto sources. Note from the T01 record the tracing tool and its event names, the onboard computer specification and the netem status; from WS05-T09 the alert message fields (is there a patient identifier), the RSM step callback and the escalation path.
2. Write the tests above and run `pytest ros2/ralmon_sim/test/test_measure.py -q`; watch them fail.
3. Implement `measure.py` (pure): normalised event reader, probe day and slot expansion, probe-to-alert pairing by time order (probes are isolated by construction: only one probe is in flight, rotating over the patients, background traffic is benign), percentiles with `numpy.percentile` linear interpolation, hop breakdown, callback durations and overrun rate against `step_ms`, saturation rule (first grid cell in which the RSM step overruns), resource summaries, hardware profile, arrival-delay export, instance replication, metrics writer in the `01-conventions.md` section 9 layout.
4. Implement `measure_runner.py`: start a ros2_tracing session with the tool recorded in T01; convert the trace to the normalised JSON lines (write the tracepoint-to-event mapping in `doc/measurement-method.md`); sample per-process CPU and resident memory at the configured period by matching the node names on the process command line; launch the profile; stop and analyse. Profiles: `latency` and `throughput` run without Gazebo (devices, gateway, ward node, attribution, event manager; N patients, M instances per patient, benign background samples of a channel that no template checks, confirmed against the template table of WS01-T02, at a configured rate); `resources` runs the full scenario of WS07-T04 and reports the Gazebo and Nav2 processes separately from the on-path nodes and the achieved real-time factor. Apply the hardware profile (CPU affinity to the onboard core count; a memory limit only if privileged) and record it. The latency of a probe is reported as a total and per hop; the deliberate holding of the monitor (reorder buffer delay and step alignment, both from the scenario `monitor` values) is named separately in the report and is not subtracted.
5. Implement the `fault_matrix` workload and `test_fault_matrix_e2e.py` on the full scenario with `faults.launch.py`; run the netem probe here if the privilege exists (WS07-T05 left it open otherwise) and record `netem: unverified` with the human action if not. Do not tune the scenario to make attribution look right: record the attributed cause found, and list mismatches with the oracle as findings for WS02 and WS08.
6. Write `ws07_latency.yaml` (seeds at least 5, probe count and period, N and M grids, duration, sampling period, background rate, `continuity_timeout_ms`, timing tolerance; all declared run parameters). Run the workloads for each seed. Run the `arrival_delay` workload (fault-free full scenario, `compression_factor` 1, horizon and scenario from the config) and export `robot_arrival_delay.json` (plain JSON list of non-negative integers, the format `EmpiricalJitter` reads) with its `.meta.json`.
7. Write `doc/measurement-method.md` with the H2 headings `Scope`, `Definitions`, `Workloads`, `Hardware profile`, `Tracing`, `Limitations`, `Reproducibility`: what is measured and what is excluded, the wall-clock policy, the equivalence claim allowed by the hardware profile (equivalent machine, emulated limits, or none), RMW and transport in use, that deterministic artefacts are byte-identical from a seed while wall-clock values vary and are reported with the spread over seeds, and that real on-board latency is WS10-T05.
8. Run `ruff check ros2/ralmon_sim`, `ruff format ros2/ralmon_sim`; commit `WS07-T07: latency, resources, scalability and fault matrix`. Tell the WS12 owner where `latency_percentiles` lives and which claim the hardware profile permits.

## Done when

- `pytest ros2/ralmon_sim/test/test_measure.py -q` exits 0.
- In the sourced ROS 2 environment: `pytest ros2/ralmon_sim/test/test_fault_matrix_e2e.py -q -m ros` exits 0.
- `ruff check ros2/ralmon_sim` and `ruff format --check ros2/ralmon_sim` exit 0.
- `measure_run --config ros2/ralmon_sim/config/experiments/ws07_latency.yaml --seed 0` exits 0 and writes `outputs/ws07-latency/0/`; `for f in config.yaml metrics.json git_rev.txt fault_matrix.json robot_arrival_delay.json robot_arrival_delay.meta.json; do test -f outputs/ws07-latency/0/$f || echo "missing $f"; done` prints nothing.
- `python -c "import json; m = json.load(open('outputs/ws07-latency/0/metrics.json')); assert {'latency_percentiles', 'cpu_percent', 'rss_mib', 'throughput_grid', 'hardware_profile', 'tools'} <= set(m); assert {'p50', 'p95', 'p99'} <= set(m['latency_percentiles'])"` exits 0, and `python -c "import json; assert len(json.load(open('outputs/ws07-latency/0/fault_matrix.json'))) == 7"` exits 0.
- `grep -cE '^## (Scope|Definitions|Workloads|Hardware profile|Tracing|Limitations|Reproducibility)$' ros2/ralmon_sim/doc/measurement-method.md` prints `7`, and `grep -nE 'TO''DO|TB''D|lo''rem|[?][?][?]' ros2/ralmon_sim/doc/measurement-method.md ros2/ralmon_sim/config/experiments/ws07_latency.yaml` prints nothing.
