# Evidence channels and the EvidenceVector: field semantics, derivation, placement, ablation A4 mask, timing

Document WS02-T03. It is the single reference for the twenty fields of the `EvidenceVector` contract (`docs/plan/02-interfaces.md#evidencevector`, version 0.1.0): what each field means and which of its values is adverse, who produces it, how it is derived from the trace schema and from ROS 2, when it is `None`, in which placement it exists, which fields ablation A4 removes, and which timing rules (two clocks, reorder buffer, cut-off) decide what evidence an alert may use. It also lists the contract gaps it found and the change proposals (ADR-032 to ADR-036, appended to `docs/plan/03-decisions.md`, status proposed). It does not define attribution rules (WS02-T04), the diagnosability matrix (WS02-T05), the injectors (WS04-T07, WS04-T08) or the ROS 2 nodes (WS05-T09, WS07). Validation in this project is technical and pre-clinical: nothing here is a clinical claim, and no number in this document is a clinical, probabilistic or device value.

The semantics used is the merged formal core: signals, grid, two clocks, reorder buffer and late-sample policy of `docs/formal/01-signals-sampling.md` (called T01 below), the templates and robot obligations of `docs/formal/02-templates.md` (T02), and the verdicts and markers of `docs/formal/05-three-valued-semantics.md` (T05). The C2 side is `docs/models/fault-model.md` (FM below) and the C3 side `docs/models/threat-model.md` (TM below). The contract is not edited: what the model needs and the contract lacks is a gap `EC-GAP-n` in the section Contract gaps and change proposals.

**Reading conventions.**

1. Times are integer milliseconds since the start of the patient-day (ADR-017). A label `hh:mm:ss` converts as `t_ms = ((60 hh + mm) 60 + ss) 1000`. `T_s` is the monitor step, `D` the reorder delay (`MonitorConfig.reorder_delay_ms`), `k_up(t) = ceil(t / T_s)` the ceiling step of T01 section 3.3, `t_k = k T_s` the grid time of step `k`. In worked checks no unit is written next to a fixture number; the unit is milliseconds.
2. FIXTURE-ONLY marks a value chosen for hand arithmetic; it has no clinical meaning and is not a registry value. "illustrative, unverified" marks a value taken from analisi (ADR-020). This document gives no value for a threshold, a window or a bound: they are parameter names (section Parameters requested from the registry).
3. The worked checks `EX-1` to `EX-10` were computed by hand and re-computed by an integer-millisecond reference extractor written for this task (not committed). It was validated first on the golden cases V-LATE-1, V-LATE-2 and V-INT-1 to V-INT-3, G-INT-1 to G-INT-3 of `docs/formal/golden/`, on the worked checks FX-3, FX-4 and FX-12 of FM and TX-1, TX-5 and TX-8 of TM, and only then used on the checks below (its outputs are in the task notes).
4. Hypotheses are named `H-...` and listed once in the section Conventions. Every statement of the form "the field is X" names the hypotheses it uses. Gaps are `EC-GAP-n`, open points `EC-OP-n`.
5. Every name used (field, `EventKind`, `SignalId`, `TemplateId`, topic, trace attribute) exists in the contract with exactly that name. A proposed field that is not in the contract is written in slash notation `group/name` and is never used as if it existed.
6. No reference is cited from memory; this document cites none.
7. Glossary of `docs/plan/01-conventions.md` section 7: a violation is a violated sub-formula; the attributed cause κ (C1, C2, C3, UNDETERMINED) is a value of the alert; DISPENSE (the dispenser opened) is not INTAKE (verified only by the robot witness, ADR-004); "robustness" is reserved for STL; the latent trace is used only for ground truth and nothing at inference reads `LatentDay` or `GroundTruthEvent`.

## Conventions

### Paths and the unit of evidence

A field is written `group.field`, where `group` is the attribute name in `EvidenceVector` (`provenance`, `system`, `signal_quality`, `cross_device`, `witness`, `crypto_temporal`) and `field` the attribute name of the part. This is the canonical path used in `Explanation.evidence_used`, in configuration files and in `configs/diagnosability.yaml`. A path addresses a field, not an entry of a mapping (the entries of `system.node_lifecycle` are written in prose as nodes).

One `EvidenceVector` is built for one violated instance (or one `PREDICTED_VIOLATION` record) of a template (decision D-1). Its **evidence window** and **cut-off** are defined in the section Timing and evidence window. Its **scope** is defined below.

### Reading states

A reading of a field is in one of three states.

- **Asserted**: the field holds its adverse value (column "adverse value" of the table in Field semantics).
- **Denied**: the field holds its non-adverse value because the channel was available for the instance, the rule was evaluated, and it found nothing adverse.
- **Unavailable**: the field is `None`.

`None` is never converted to a negative observation. Precisely: the extractor writes `None` when the channel was unavailable or when the rule had no basis; the attribution layer treats `None` as "no information", so that a rule that needs a denied reading (for example the exclusion conditions for C1) is not satisfied by `None`, and the abstention reasons of WS02-T04 are the consequence; the A4 mask writes `None` for the fields it removes and recomputes the aggregate ones from the remaining sources, and writes nothing else; a consumer never reads `None` as `False`, as the empty string, as `0` or as the absence of an alert. The monitor does not read the `EvidenceVector`: it reads the availability of its own signals (the robot channels `presence` and `intake`), and T05 section 3.5 already keeps an unavailable channel apart from a zero (marker `channel_unavailable:*`) and an undefined held value apart from an unavailable channel (marker `value_undefined:*`). The two uses agree for the witness fields under H-MASK (check EX-9): when the INT instance of a dispense is VIOLATED, `witness.robot_present` is False and `witness.intake_observed` is False or `None`; when it is PENDING with a marker `channel_unavailable:presence` or `channel_unavailable:intake`, neither witness field is False; when it is PENDING with the marker `value_undefined:presence`, `witness.robot_present` is not False.

Not every `None` has the same cause, and the field alone does not say which one applies (declared limit): a capability that the device lacks (S5), a channel that is unavailable by placement (S1, S3, S4), and a rule with no basis in the window (for example no message of the device in the window) all read `None`. The section Availability per placement gives the cause per field and situation.

### Representation of "denied" for non-boolean fields

A boolean field is denied when it holds its non-adverse value (False for `crypto_temporal.timestamp_implausible`, True for `system.liveliness_ok`). The other types are written as follows.

- **Float fields** (`system.ble_link_quality`, `signal_quality.ecg_sqi`, `signal_quality.ppg_sqi`, `cross_device.pulse_vs_ecg_hr_diff`) carry the measured quantity, never a Boolean. They are asserted or denied by the consumer by comparing the value with a registry threshold named in the section Parameters requested from the registry (a floor for a quality, a tolerance for a difference). The extractor does not compare.
- **`signal_quality.cuff_error_code`** is a string. The cuff reports codes and one is present: the code (asserted). The cuff reports codes, it was observed in the window (at least one message of the cuff received in the window) and no code is present: the **empty string** (denied; the payload convention makes `error_code` non-empty, so the empty string is free to mean no code). The cuff reports no codes, or was silent in the window: `None`.
- **`system.node_lifecycle`** is a mapping from node to state. A node with a status report capability has an entry; the entry is denied when it is `active` or ends with `+commanded`, and asserted otherwise (vocabulary in D-4). The field is `None` when no node of the scope has an entry.

EX-3 (fixture, cuff and ECG frames at 20:00 and 20:30, instance `hold` at 21:00): (a) no code and cuff frames in the window give the empty string; (b) a `DEVICE_ERROR` event with `payload.error_code` equal to the fixture label E1 gives E1; (c) the cuff silent in the window gives `None`; (d) a cuff profile without error codes gives `None`; (e) a cuff pulse of 90 against an ECG rate of 72 gives the float 18.0 (the consumer compares it with `hr_coherence_tolerance`); (f) with the cuff silent in the window, the instances `sched`, `hold` and `resp` give `None` for `crypto_temporal.seq_gap_or_replay`, `crypto_temporal.timestamp_implausible`, `crypto_temporal.authenticated` and `system.ble_link_quality`, although the dispenser sent its frame.

### On-path and off-path

A field, module or input is **on-path** if it lies on the path from a sample to an alert, subject to the latency bounds of the monitor: the reorder buffer (delay `D`), the decision step of the template, and the evidence cut-off of this document. A module is **off-path** if it belongs to the back-end: forecaster training and recalibration, retrospective checks, care-plan distribution and any other module that is not required to produce an alert. The twenty fields are on-path: each is a function of inputs that the ward node holds at the cut-off (the robot fields reach it on `/ralmon/events` and `/ralmon/robot_evidence`). Nothing off-path is an input of any field, and the forecaster, the conformal calibrator and ρ are not inputs either (WS02-T04, invariant I1).

### Scope of an instance and aggregation rule

Several fields are scalars over more than one node (FM-GAP-LIVE: the contract does not say which node). This document fixes the nodes that a scalar aggregates over, per template, from the signal footprint of T02 section 3.1 and the robot obligations of T02 section 5.3.

| template | BLE device roles (data scope) | robot node in the system scope | basis |
|---|---|---|---|
| `range` | cuff | no | reads `meas`, `bp` |
| `sched` | cuff | yes | `creates_robot_obligation` is True for SCHED (T02 section 3.1, note 4); the measurement is made through the visit (H-VISIT) |
| `hold` | cuff, dispenser | yes | reads `meas`, `bp`, `dispense`; the pre-dose reading comes from a visit (H-VISIT) |
| `count` | dispenser | no | reads `dispense`, `dose_count`, `day_end` |
| `resp` | cuff, dispenser | yes | `creates_robot_obligation` is True for RESP; reads `dispense`, `meas`, `bp_drop` |
| `sys` | cuff | no | reads `meas`, `cuff_health`, `inflation_ms` |
| `int` | dispenser | yes | the robot produces `presence` and `intake`; reads `dispense`, `auth` |

The BLE device roles are the data scope of `crypto_temporal.*` and `system.ble_link_quality`. The robot is never in that scope (decision D-12). The system scope is the data scope plus the robot node where the table says yes. The ECG device and the pulse oximeter are not in the scope of any template; their fields (`signal_quality.ecg_sqi`, `signal_quality.ppg_sqi`, `cross_device.pulse_vs_ecg_hr_diff`) are computed over the evidence window whatever the template, and WS02-T04 decides for which template they are relevant.

**Aggregation rule.** A field that aggregates over a set of components (nodes, streams, devices) is asserted as soon as one component asserts the adverse value. It is denied only if every component of the set that the profile declares capable has a denied reading. Otherwise it is `None`. A component that has no basis (a device with no message in the window, a node whose status entry is not `active` and that reports no adverse reading) is a component with an unavailable reading, so it prevents the denial of the aggregate and never contributes a negative reading. This is the reason why a violation of `sched`, `hold` or `resp` whose cuff stream is silent in the window has `crypto_temporal.*` and `system.ble_link_quality` equal to `None`, and the dispenser alone cannot deny them (EX-3 (f)).

### Hypotheses used

| id | hypothesis |
|---|---|
| H-INIT | A run starts with every node `active` and the robot not co-located. A node with the status-report capability that never reports a state is read as `active`; the robot channels are unavailable until a status report says that the robot is co-located. |
| H-WARDCLK | An event that the ward node itself generates (a gateway or watchdog `NODE_STATE` event) carries the ward clock as both `t_device_ms` and `t_rx_ms`, so it is on time by construction. |
| H-SEQT | For a device that provides `seq`, the distinct `seq` values of all its Samples and Events form a run of consecutive integers in device-time order; the members of one transmission (frame) share one value and differ in `Sample.signal` or `Event.kind`. This is H-SEQMONO of TM made precise. |
| H-SEQSTATE | The accepted `(name, seq)` pairs and the largest `seq` of the previous day are retained across days (TM H-SEQSTATE, T01 section 5.5 item 4). |
| H-VLOG | The gateway logs every failed verification as an event (the policy "flag" of TM H-GW). Under the policy "drop" the failure is evidence only if it is logged. |
| H-PROF | The capabilities of each source are declared in a device profile (D-8, EC-GAP-8). |
| H-VISIT | The measurement obligations of SCHED and RESP are carried out through the robot visit (FM hypothesis 7). A deployment in which the cuff measures on its own schedule needs a scope table without the robot in `sched`, `hold` and `resp`. |
| H-MASK | The availability of the robot channels `presence` and `intake` at a step is the robot status at that step: the robot node is `active` and its last status report says co-located; one mask serves both channels. This is the mask that T01 section 2.5 takes from the robot node status and heartbeat. A monitor that masks the two channels separately, as the golden case V-INT-1 does (presence unavailable, intake available), is outside this hypothesis, and the consistency statements of EX-9 hold for the single mask. |

## Channel identifiers

The identifiers below are used by WS02-T05 (`configs/diagnosability.yaml`) verbatim; a rename needs a recorded reason. A channel is a source of evidence with its own producer and its own failure mode; the diagnosability matrix and ablation A4 are stated in terms of channels.

| id | producer | placement | fields fed | status |
|---|---|---|---|---|
| `CH-PROV` | the monitor (the `VerdictRecord` of the violated instance and the `Template.kind` of its template) | ward node | `provenance.violated_template`, `provenance.template_kind` | defined |
| `CH-SYS-WARD` | the gateway and the watchdog of the ward node: link state, liveliness and deadline QoS of the device streams, delivery ratio of the device sequences, status reports of device nodes | ward node | `system.node_lifecycle`, `system.diagnostics_ok`, `system.liveliness_ok`, `system.qos_deadline_missed`, `system.ble_link_quality` (the device components) | defined |
| `CH-SYS-ROBOT` | the robot node and its watchdog: the robot lifecycle, navigation and manipulation outcomes, the robot battery; the heartbeat supervision of the robot node is assigned to this channel by its subject (D-11) | robot (observed at the ward node for the heartbeat) | `system.node_lifecycle`, `system.diagnostics_ok`, `system.liveliness_ok`, `system.qos_deadline_missed` (the robot components), `system.battery_low`, `system.nav_task_failed`, `system.manip_task_failed` | defined |
| `CH-SQI` | the devices: `Sample.quality` of the ECG device and of the pulse oximeter, error codes of the cuff | ward node (from device messages) | `signal_quality.ecg_sqi`, `signal_quality.ppg_sqi`, `signal_quality.cuff_error_code` | defined |
| `CH-XDEV` | the ward node, computed from the cuff pulse rate and the ECG heart rate | ward node | `cross_device.pulse_vs_ecg_hr_diff` | defined |
| `CH-WIT` | the robot perception (presence, identity check, intake), valid only while the robot is co-located | robot, co-located | `witness.robot_present`, `witness.identity_confirmed`, `witness.intake_observed` | defined |
| `CH-CRYPTO` | the gateway: verification outcome of each message, sequence tracker, two-clock acceptance rules of T01 sections 4.2 to 4.4 | ward node | `crypto_temporal.authenticated`, `crypto_temporal.seq_gap_or_replay`, `crypto_temporal.timestamp_implausible` | defined |
| `CH-DISP` | the dispenser (interval since the previous opening and content change) | ward node | none: no contract field carries it (EC-GAP-1; the fields `dispenser/interval_since_previous_ms` and `dispenser/content_change` are proposed) | proposed, not in the contract |

`CH-DISP` is listed because WS02-T05 needs the identifier for the rows of the double take and the bounce; it is a proposed channel and feeds no field until ADR-032 is confirmed. The embodied channel of ablation A4 is the pair `CH-WIT` and `CH-SYS-ROBOT`.

## Field semantics

Columns. "adverse value": the value that asserts a problem (for a float, the direction of a threshold crossing, with the threshold in the section Parameters requested from the registry). "polarity": adverse-true, adverse-false, adverse-high, adverse-low, informative (both directions carry information) or context. "producer and placement": who writes the underlying input and where. "robot-derived": yes (a robot input only), partial (aggregates robot and ward components) or no.

| field | type | adverse value | polarity | producer and placement | channel | `None` when | robot-derived |
|---|---|---|---|---|---|---|---|
| `provenance.violated_template` | `TemplateId` | none: context, not a reading | context | the monitor, from `VerdictRecord.template`; ward node | `CH-PROV` | never: the type is not optional | no |
| `provenance.template_kind` | `TemplateKind` | none: context; INTEGRITY or SYSTEM says which conjunct is violated, and is never sufficient alone (WS02-T04) | context | the monitor, from `Template.kind` of the violated template; ward node | `CH-PROV` | never: the type is not optional | no |
| `system.node_lifecycle` | `Mapping[str, str]` or `None` | any entry other than `active` and other than `<state>+commanded` | adverse entry | node status reports (`NODE_STATE`): the node itself (lifecycle, diagnostics), the gateway (`link_down`, `unreachable` of a device), the watchdog (`unreachable` of the robot); ward node | `CH-SYS-WARD` and `CH-SYS-ROBOT` | no node of the scope reports status (S5), or none remains of the scope (A4) | partial |
| `system.diagnostics_ok` | `bool` or `None` | False: a node of the scope reported level error or stale in the window | adverse-false | `NODE_STATE` reports with `payload.diagnostics`; ROS 2 diagnostics aggregated at the ward node | `CH-SYS-WARD` and `CH-SYS-ROBOT` | no node of the scope declares diagnostics; or no node asserts it and a capable node has no usable ok report (a status entry that is not `active`, or no report) | partial |
| `system.liveliness_ok` | `bool` or `None` | False: a node of the scope had its liveliness lease lapse in the window | adverse-false | liveliness QoS of the device streams (gateway) and heartbeat of the robot (watchdog), both reported as `NODE_STATE` with `payload.state` equal to unreachable; ward node | `CH-SYS-WARD` and `CH-SYS-ROBOT` | no node of the scope is supervised | partial |
| `system.qos_deadline_missed` | `bool` or `None` | True: a stream of the scope with a declared deadline had a gap longer than the deadline in the window | adverse-true | arrival gaps of device streams (from `t_rx_ms`) and heartbeat deadline reports (`payload.deadline_missed`); ward node | `CH-SYS-WARD` and `CH-SYS-ROBOT` | no stream or node of the scope has a declared deadline (an event-driven device may have none) | partial |
| `system.ble_link_quality` | `float` or `None` | low: the delivery ratio of the device sequences in the window, compared with `ble_link_quality_floor`; it is 1.0 exactly when no sequence value is missing (D-3) | adverse-low | the gateway, from the `seq` of the BLE device messages; ward node | `CH-SYS-WARD` | no BLE device of the scope provides `seq`, or a capable device had no finalised message in the window | no |
| `system.battery_low` | `bool` or `None` | True: the robot reported a low battery in the window or in force at its start | adverse-true | the robot node, as `payload.battery_low` of its `NODE_STATE` reports (D-2); robot | `CH-SYS-ROBOT` | the robot is absent, not in the scope, reports no battery state, or has no report in force; or its reports are all False and its status entry in the window is adverse (a stale report is not an ok reading) | yes |
| `system.nav_task_failed` | `bool` or `None` | True: a navigation task of the patient had outcome failed, timeout or late in the window (D-5) | adverse-true | `ROBOT_TASK` events with `payload.task` equal to navigate; robot | `CH-SYS-ROBOT` | the robot is absent or not in the scope, reports no navigation outcome, or no navigation outcome of the patient lies in the window | yes |
| `system.manip_task_failed` | `bool` or `None` | True: a manipulation task of the patient had outcome failed, timeout or late in the window | adverse-true | `ROBOT_TASK` events with `payload.task` equal to manipulate; robot | `CH-SYS-ROBOT` | as `system.nav_task_failed`, for manipulation | yes |
| `signal_quality.ecg_sqi` | `float` or `None` | low: the lowest `Sample.quality` of `HR_ECG` in the window, compared with `ecg_sqi_floor` | adverse-low | the ECG device (`Sample.quality`); ward node | `CH-SQI` | no `HR_ECG` sample in the window carries a quality (device reports none, or no sample) | no |
| `signal_quality.ppg_sqi` | `float` or `None` | low: the lowest `Sample.quality` of `SPO2` in the window (D-13), compared with `ppg_sqi_floor` | adverse-low | the pulse oximeter (`Sample.quality`); ward node | `CH-SQI` | no `SPO2` sample in the window carries a quality | no |
| `signal_quality.cuff_error_code` | `str` or `None` | any non-empty string (a code is present) | adverse-nonempty | the cuff, as `DEVICE_ERROR` events with `payload.error_code`; ward node | `CH-SQI` | the cuff reports no codes, or the cuff was silent in the window | no |
| `cross_device.pulse_vs_ecg_hr_diff` | `float` or `None` | high: the largest absolute difference between a `HR_PULSE` sample of the window and the held `HR_ECG` value at its step, compared with `hr_coherence_tolerance` | adverse-high | computed at the ward node from the cuff and the ECG device | `CH-XDEV` | no `HR_PULSE` sample in the window has an `HR_ECG` value not older than `hr_coherence_max_age_ms` | no |
| `witness.robot_present` | `bool` or `None` | informative: True means the robot perceived the patient present at a step of the window; False means that, with the robot co-located at every step and a defined level at every step, no step read present (the adverse reading in a dispense context) | informative | the robot perception (`PRESENCE` Samples) and the robot status (H-MASK); robot, co-located | `CH-WIT` | the robot is absent or not in the scope; or the robot is not co-located at some step and no step read present; or a level is undefined at some step and no step read present | yes |
| `witness.identity_confirmed` | `bool` or `None` | False: the robot performed an identity check in the window and it failed (D-6) | adverse-false | the robot (`ROBOT_TASK` event with `payload.task` equal to witness and `payload.identity_confirmed`); robot, co-located | `CH-WIT` | `witness.robot_present` is not True, or the robot has no identity check, or none was reported in the window | yes |
| `witness.intake_observed` | `bool` or `None` | informative: True means an `INTAKE` event of the robot lies in the window; False means the robot was co-located at every step of the window, no `INTAKE` event lies in it and no visit failed (the adverse reading in a dispense context) | informative | the robot (`INTAKE` events, ADR-004) and the robot status; robot, co-located | `CH-WIT` | the robot is absent or not in the scope; or it was not co-located at some step and no `INTAKE` event lies in the window; or a manipulation or witness task of the patient failed in the window and no `INTAKE` event lies in it | yes |
| `crypto_temporal.authenticated` | `bool` or `None` | False: a message of a BLE device of the scope failed verification in the window | adverse-false | the gateway (failed verifications logged as events, H-VLOG); ward node | `CH-CRYPTO` | no device of the scope authenticates, or an authenticating device had no message in the window | no |
| `crypto_temporal.seq_gap_or_replay` | `bool` or `None` | True: a repeated `(name, seq)` was received in the window, or a `seq` value of a device is missing at the cut-off (the one Boolean mixes the two, D-3) | adverse-true | the gateway sequence tracker over the BLE device messages; ward node | `CH-CRYPTO` | no device of the scope provides `seq`, or a capable device had no message in the window and no other device asserts | no |
| `crypto_temporal.timestamp_implausible` | `bool` or `None` | True: a message of a BLE device of the scope was counted late (T01 section 4.3) or future-stamped (T01 section 4.4) in the window (D-9) | adverse-true | the gateway, from the two clocks `t_device_ms` and `t_rx_ms`; ward node | `CH-CRYPTO` | the two clocks are not independent for the device (no transport-delay model), or a capable device had no message in the window and no other device asserts | no |

Notes on the table.

1. **`witness.robot_present` reads the PRESENCE signal.** The name says "present" and the contract comment says "`None` if the robot was not co-located": if the field meant that the robot is co-located it could be only True or `None`. The field is the patient's presence as observed by the robot (`SignalId.PRESENCE`, "robot-observed presence of the patient"). Co-location is the condition under which the field is not `None`, not its value (EC-GAP-11, a naming note, no change proposed).
2. **Two causes of `None` for the witness fields.** The witness fields are `None` both when the robot is away (S3) and when it is down (S4), and the field alone does not tell them apart; the ward node asserts `system.liveliness_ok` False for the robot node in S4 and not in S3, which is how the two situations differ for the attribution layer.
3. **Facts are not erased by a later outage.** A reading that rests on events inside the window stays: an asserted or a denied `system.nav_task_failed` from outcome events, a `witness.robot_present` True seen before the robot went down. What a later outage turns into `None` is every reading that needs the channel to have been available to the end of the window: the denials of the witness fields (coverage) and of the node-reported statuses (a stale ok report is not an ok reading). EC-OP-4 records the difference with WS05-T07 test 36.
4. **The `system` scalars are aggregates.** The robot components of `system.node_lifecycle`, `system.diagnostics_ok`, `system.liveliness_ok` and `system.qos_deadline_missed` are what the A4 mask removes (section Ablation A4 mask).
5. **Polarity of the witness fields.** The contract rule keeps `intake_observed` False while the robot is co-located different from `None`. A False reading is informative only for a dispense-anchored instance whose window the robot covered; for an instance whose window is long (RESP) the coverage condition is rarely met and the field is mostly True or `None`.

## Derivation from the trace schema and ROS 2

The offline trace (S6) is the reference: every field must be derivable from `Sample`, `Event` and the device profile alone, and the ROS 2 path must produce the same values. The ROS 2 sources below are the live carriers of the same trace items: a ROS 2 message becomes a `Sample` or an `Event` by the converters of WS05-T09, and the extractor reads only those. The ward node also converts what the middleware reports (a liveliness lapse, a missed deadline, a robot status change) into `NODE_STATE` events, so that the offline trace and the live run feed the extractor identical items.

`/ralmon/robot_evidence` carries the witness fields and the robot system fields as a snapshot at the monitor time of the message. Its equivalence with the trace (decision D-14): a witness field that is `None` is "robot not co-located" (a `NODE_STATE` of the robot with `payload.colocated` False); `witness.robot_present` True or False is a `PRESENCE` Sample of value 1.0 or 0.0; `witness.intake_observed` True is an `INTAKE` event; `witness.identity_confirmed` is the `payload.identity_confirmed` of a `ROBOT_TASK` witness event; `system.nav_task_failed` and `system.manip_task_failed` are `ROBOT_TASK` outcomes; `system.battery_low` is `payload.battery_low` of a `NODE_STATE` report. A snapshot that cannot be written as one of these trace items is not an input of the extractor.

### Trace evidence conventions

`Event.payload` is open in `#trace-schema`, so the keys that the derivation needs are fixed here, once. Keys not listed are free; a key added by a consumer for its own use starts with `sim_` (WS07) or is declared by its owner. All payload values are `float | int | str | bool` as the contract requires.

| event kind | key | type | producer | used by |
|---|---|---|---|---|
| `NODE_STATE` | `state` | str, one of `unconfigured`, `inactive`, `active`, `finalized`, `link_down`, `unreachable`; required in every report | the node itself (the four lifecycle states), the gateway (`link_down`: the BLE connection of a device was lost, immediate; `unreachable` for a device), the watchdog (`unreachable`: the liveliness lease of a node lapsed) | `system.node_lifecycle`, `system.liveliness_ok`, availability of the robot channels |
| `NODE_STATE` | `commanded` | bool, default false; true when the transition was announced as deliberate before it happened | the supervisor, through the node that reports | `system.node_lifecycle` |
| `NODE_STATE` | `diagnostics` | str, one of `ok`, `warn`, `error`, `stale` | the node | `system.diagnostics_ok` |
| `NODE_STATE` | `battery_low` | bool; the robot node only | the robot node | `system.battery_low` |
| `NODE_STATE` | `deadline_missed` | bool; a deadline report on the heartbeat of the node | the watchdog | `system.qos_deadline_missed` |
| `NODE_STATE` | `colocated` | bool; the robot node only; true while the robot is in the room of the patient | the robot node | availability of the robot channels (H-MASK), `witness.*` |
| `ROBOT_TASK` | `task` | str, one of `navigate`, `manipulate`, `witness` | the robot node | `system.nav_task_failed`, `system.manip_task_failed`, `witness.intake_observed`, `witness.identity_confirmed` |
| `ROBOT_TASK` | `outcome` | str, one of `success`, `late`, `failed`, `timeout`; `late` means completed after the deadline induced by the schedule | the robot node | the same |
| `ROBOT_TASK` | `patient_id` | str; the patient whose obligation the task served | the robot node | the same (a ward has several patients and one robot) |
| `ROBOT_TASK` | `obligation_id` | str, optional; `<source template>:<instance_key>` of T02 section 5.2 | the robot node | traceability only; no field reads it |
| `ROBOT_TASK` | `identity_confirmed` | bool, optional; present only on a `witness` task whose identity check was performed | the robot node | `witness.identity_confirmed` |
| `DEVICE_ERROR` | `error_code` | str, non-empty; a device-defined label, never a clinical value | a device (the cuff) | `signal_quality.cuff_error_code` |
| `DEVICE_ERROR` | `verification` | str, the value `failed`; interim convention for a failed verification (EC-GAP-4, ADR-035) | the gateway | `crypto_temporal.authenticated` |
| `DEVICE_ERROR` | `subject` | str; the source identifier of the device whose message failed verification | the gateway | `crypto_temporal.authenticated` |
| `DISPENSE` | `interval_since_previous_ms` | int; proposed (EC-GAP-1); no current field reads it | the dispenser | proposed `dispenser/interval_since_previous_ms` |
| `DISPENSE` | `content_change` | float; after minus before, in the unit the dispenser declares; proposed (EC-GAP-1) | the dispenser | proposed `dispenser/content_change` |
| `INTAKE` | none | none: the event is the reading | the robot | `witness.intake_observed` |
| `MEASUREMENT_MISSED` | none | none: not an input of any of the twenty fields (a missed measurement is visible as an absent `meas` impulse) | the cuff | none |

Every `Sample` carries its own `seq` and `quality` (contract fields). The role of a `Sample` (which device produced it) is the producer of its `signal` in T01 section 2.1, because a `Sample` has no source field (TM-GAP-SEQKEY); the role of an `Event` is its `source` through the device profile.

### Derivation table

The column "rule" is the exact reading; the reading states and `None` conditions are those of the table in Field semantics.

| field | trace source | ROS 2 source | rule |
|---|---|---|---|
| `provenance.violated_template` | `VerdictRecord.template` | `/ralmon/verdicts` | copied from the record that triggers the alert |
| `provenance.template_kind` | `Template.kind` of that template | `/ralmon/verdicts` and the template library | copied |
| `system.node_lifecycle` | `Event` kind `NODE_STATE`, `payload.state`, `payload.commanded`, per node | `NODE_STATE` events produced by the node, the gateway and the watchdog | for each node of the scope with status reports: the last adverse token (`state`, with `+commanded` appended when `commanded` is true) among the report in force at the window start and the reports in the window; `active` if there is none (EX-4) |
| `system.diagnostics_ok` | `NODE_STATE`, `payload.diagnostics` | ROS 2 diagnostics aggregated by the ward node and written as `NODE_STATE` | False if a node of the scope reported `error` or `stale`; True if every capable node reported, none is adverse and its status entry is `active`; else `None` |
| `system.liveliness_ok` | `NODE_STATE` with `state` equal to `unreachable` | liveliness QoS of the device streams and `/ralmon/heartbeat` of the robot; the gateway and the watchdog write the lapse as `unreachable` | False if a node of the scope has `unreachable` in force at the window start or reported in the window; True if every supervised node has none |
| `system.qos_deadline_missed` | `t_rx_ms` of the data messages of each device stream with a declared deadline; `NODE_STATE` `payload.deadline_missed` | deadline QoS of `/ralmon/samples`; heartbeat deadline | a stream misses its deadline at `t + deadline` when the next arrival, or the cut-off, is later than that instant; the run start counts as an arrival; True if such an instant lies in the window (EX-6) |
| `system.ble_link_quality` | `Sample.seq` and `Event.seq` of each BLE device | the gateway counts the same values | per device, over its distinct `seq` values: received values divided by values between the base and the top (D-3); the field is the minimum over the devices of the scope (EX-1) |
| `system.battery_low` | `NODE_STATE` of the robot, `payload.battery_low` | the robot battery state published with its status | True if a report in the window or in force at its start is True; False if every such report is False and the robot has no adverse status entry; else `None` |
| `system.nav_task_failed` | `ROBOT_TASK`, `task` navigate, `outcome`, `patient_id` | the same event on `/ralmon/events`; or `/ralmon/robot_evidence` | True if an outcome in the window is `failed`, `timeout` or `late`; False if there is at least one navigation outcome and all are `success`; else `None` |
| `system.manip_task_failed` | `ROBOT_TASK`, `task` manipulate | the same | as for navigation |
| `signal_quality.ecg_sqi` | `Sample.quality` of `SignalId.HR_ECG` | the same value on `/ralmon/samples` | the minimum quality among the accepted `HR_ECG` samples of the window that carry one |
| `signal_quality.ppg_sqi` | `Sample.quality` of `SignalId.SPO2` (D-13) | the same | as for the ECG |
| `signal_quality.cuff_error_code` | `DEVICE_ERROR` from the cuff, `payload.error_code` | the same event | the code of the last event in the window; the empty string if none and the cuff sent messages in the window; else `None` |
| `cross_device.pulse_vs_ecg_hr_diff` | `Sample.value` of `SignalId.HR_PULSE` and `SignalId.HR_ECG` | the same | for each accepted `HR_PULSE` sample of the window, the absolute difference with the `HR_ECG` value held at its step, if that value is not older than `hr_coherence_max_age_ms`; the maximum |
| `witness.robot_present` | `Sample` `SignalId.PRESENCE` (value 1.0 or 0.0) and the robot `NODE_STATE` (`state`, `colocated`) | `/ralmon/robot_evidence` (None means not co-located) | over the steps of the window, using the availability mask and the held level (H-MASK): True if some available step reads 1.0; False if every step is available, every level is defined and none reads 1.0; else `None` (EX-5) |
| `witness.identity_confirmed` | `ROBOT_TASK`, `task` witness, `payload.identity_confirmed` | the same event | the last reported value in the window if `witness.robot_present` is True and the robot has an identity check; else `None` |
| `witness.intake_observed` | `Event` kind `INTAKE`; the availability mask; `ROBOT_TASK` outcomes | `/ralmon/robot_evidence` | True if an `INTAKE` event lies in the window; False if every step of the window is available, no `INTAKE` event lies in it and no manipulation or witness task of the patient failed in it; else `None` |
| `crypto_temporal.authenticated` | `DEVICE_ERROR` from the gateway with `payload.verification` and `payload.subject` (interim, EC-GAP-4) | the gateway verification of the message tag | False if a failure of a device of the scope was logged in the window; True if every authenticating device of the scope had a message in the window and no failure; else `None` |
| `crypto_temporal.seq_gap_or_replay` | `Sample.seq`, `Event.seq` with `Sample.signal` or `Event.kind` | the gateway tracker | True if a received `(name, seq)` repeats an accepted one (or one retained from the previous day), or a `seq` value of the device is missing at the cut-off; False if every device of the scope had a message in the window and neither holds (EX-1) |
| `crypto_temporal.timestamp_implausible` | `t_device_ms` and `t_rx_ms` of every message of a BLE device | the stamps and the arrival time of the message | True if a message received in the window is classified late (`t_rx > t_{k_up(t_dev)} + D`) or future-stamped (`t_dev > t_rx + clock_skew_max_ms`); False if every device of the scope with independent clocks had a message in the window and none is |

### Reading rules that the table cannot hold

- **Node status carries the state in force.** The report in force at the window start counts as entered at the window start, so a node deactivated before the window and still inactive is read inactive. A node deactivated and reactivated inside the window keeps its adverse token: the field says that an adverse condition occurred in the window, not that it persists. EX-4 (fixture, the cuff reports `active` at 00:00, instance `hold` at 21:00): an uncommanded deactivation at 20:10 gives `inactive` and `system.liveliness_ok` stays True (the process lives); a commanded one gives `inactive+commanded`; a deactivation at 19:00 still in force gives `inactive`; one at 20:10 undone at 20:20 gives `inactive`; one at 18:10 undone at 18:20 gives `active`; an `unreachable` report at 20:15 gives `unreachable` and `system.liveliness_ok` False; a `link_down` report at 20:15 (the BLE connection lost, the lease not yet lapsed) gives `link_down` with `system.liveliness_ok` still True.
- **Deliberate is not failed.** A transition announced beforehand carries `commanded` true and is not an adverse entry (analisi §4.6, row 15:00); a crash is a lapse of liveliness (`unreachable`), never a lifecycle transition. A missed measurement that follows a commanded deactivation is still a violated SCHED instance; what to do with it is WS02-T04's.
- **The witness window is the read window of the template, without margin.** For `int` it is the look-back of the template, from the step `k_up(a - int_window)` to the decision step; for the other templates it starts at the read start of the instance (the anchor, or the look-back of `hold`). Using the steps of T05 makes the fields agree with the INT verdict (EX-9). An input belongs to a window if its visible step (T01 section 3.3) lies in it.
- **A presence level is held.** The level at a step is the value of the latest accepted `PRESENCE` sample whose visible step is not after it. A step with no such sample has an undefined level, which prevents `witness.robot_present` from being False (T05 marker `value_undefined:presence`).
- **A failed visit is not a denial (FM OP-2).** If a manipulation or witness task of the patient has outcome `failed`, `timeout` or `late` inside the witness window and no `INTAKE` event lies in it, `witness.intake_observed` is `None` even if the robot was co-located throughout: the robot could not have witnessed. `witness.robot_present` is unchanged.
- **Out-of-order input** is covered in the section Timing and evidence window (D-9).

Worked check EX-5 (fixture, instance `int` with the dispense at 21:00, so a window from 20:55 to 21:00 at a one-minute step): (a) the robot co-located from 20:50 with presence 1 at 20:50 and 0 at 20:58 gives `witness.robot_present` True and `witness.intake_observed` False; (b) presence 0 held: False and False; (c) an `INTAKE` event at 20:58 with presence 0: False and True; (d) the robot arrives at 20:58 and sees the patient: True and `None` (coverage broken); (e) the robot becomes `unreachable` at 20:57 after presence 1 and 0 from 20:56: True and `None`; (f) the same with presence 0 only: `None` and `None`; (g) co-located with no presence sample at all: `None` (level undefined) and False; (h) never co-located: `None` and `None`; (i) a failed manipulation at 20:56 with presence 1: True and `None`; (j) the same with an `INTAKE` event: True and True; (k) a witness task reporting a failed identity check with presence 1: `witness.identity_confirmed` False; (l) the same with presence 0: `None`.

Worked check EX-6 (fixture, a cuff stream with a declared deadline of 600000 and arrivals every 300000): nominal arrivals do not miss the deadline; one message lost (a gap of 600000, equal to the deadline) does not; three consecutive messages lost (a gap of 1200000) does. A single lost message therefore leaves `system.qos_deadline_missed` False (condition LC of FM); where the device provides `seq`, the sequence evidence (`crypto_temporal.seq_gap_or_replay`, `system.ble_link_quality`) shows it.

Worked check EX-9 (random, seeded; consistency of the witness fields with the INT verdict). The INT interval of each draw follows T05 section 2.3 (`lo` and `hi` from the last determined and the last possible witness step, the tie rule, the markers of section 3.5); the evaluator was validated first on V-INT-1, V-INT-2, V-INT-3 and G-INT-1 to G-INT-3. Each of 6000 draws has a window of five steps before the dispense and random robot status events (co-located or not, `unreachable`, `inactive`), presence samples of value 0 or 1, `INTAKE` events, `auth` Samples and failed visits, with one availability mask for both robot channels (H-MASK); the draws gave 602 VIOLATED, 2185 SATISFIED and 3213 PENDING instances, 3757 with a `channel_unavailable` marker and 556 with `value_undefined:presence`. Results: (I1) every VIOLATED instance has `witness.robot_present` False and `witness.intake_observed` False or `None` (`None` only through the failed-visit rule); (I2) conversely, in the 498 draws with both fields False and no `auth` Sample in the window the instance is VIOLATED; (I3) every PENDING instance with a `channel_unavailable` marker has neither field False; (I4) every PENDING instance with the marker `value_undefined:presence` has `witness.robot_present` not False. Zero exceptions in each.

### Device capabilities used

The derivation needs the following capabilities, declared per source in its device profile (D-8): `status_reports` (the node or its watcher emits `NODE_STATE`), `supervised` (liveliness is supervised, with a lease), `heartbeat_deadline` (a deadline is declared on a heartbeat), a declared data-stream deadline (may be null for an event-driven device), `seq`, `two_clocks` (the receive time is independent of the device time), `authenticates`, `error_codes`, `diagnostics`, `battery` (robot), navigation and manipulation outcome reporting (robot), `perception` and `identity_check` (robot), and, for the proposed channel, `content_sensing` (dispenser). A capability that is not declared makes the dependent field `None` (S5); it is never defaulted to a negative reading.

## Availability per placement

Situations. S1: ward node only (no robot in the deployment, or the robot removed from the evidence). S2: robot co-located and healthy. S3: robot in the ward but not co-located (serving another room). S4: robot unavailable (crash, depleted battery, lost heartbeat; the fallback of ADR-003 is escalation to the nurse, outside the trace). S5: a device capability is missing (no message authentication, no signal quality, no sequence numbers, no error codes, no diagnostics, no content sensing); the cell names the capability and the field is `None` when the capability is missing on every in-scope source. S6: offline replay of a benchmark trace, where the trace is the only source; the cell is shown for the reference profile of EX-7 (no transport-delay model, no diagnostics reports, no battery reports, no declared deadline), because S6 depends on what the generator emits and the profile states it.

Cells: `avail` (the field exists and can be asserted or denied), `None` (unavailable), `n/a` (not applicable). A reason code follows each cell.

| field | S1 | S2 | S3 | S4 | S5 | S6 | reasons |
|---|---|---|---|---|---|---|---|
| `provenance.violated_template` | avail (R1) | avail (R1) | avail (R1) | avail (R1) | n/a (R1) | avail (R1) | R1 |
| `provenance.template_kind` | avail (R1) | avail (R1) | avail (R1) | avail (R1) | n/a (R1) | avail (R1) | R1 |
| `system.node_lifecycle` | avail (R2) | avail (R3) | avail (R3, R5) | avail (R3, R6) | None (R7) | avail (R8) | the robot entry exists only where R3 holds |
| `system.diagnostics_ok` | avail (R2) | avail (R3) | avail (R3) | None (R6) | None (R7) | None (R7, R8) | in S4 the robot component has no usable report |
| `system.liveliness_ok` | avail (R2) | avail (R3) | avail (R3, R5) | avail (R3, R6) | None (R7) | avail (R8) | in S4 the ward asserts False for the robot |
| `system.qos_deadline_missed` | avail (R2) | avail (R3) | avail (R3) | avail (R3, R6) | None (R7) | None (R7, R8) | needs a declared deadline |
| `system.ble_link_quality` | avail (R2) | avail (R2) | avail (R2) | avail (R2) | None (R7) | avail (R8) | BLE devices only |
| `system.battery_low` | None (R4) | avail (R3) | avail (R3, R5) | None (R6) | None (R7) | None (R7, R8) | in S4 True remains if a precursor report was in the window |
| `system.nav_task_failed` | None (R4) | avail (R3) | avail (R3, R5) | None (R6) | None (R7) | avail (R8) | needs a navigation outcome in the window |
| `system.manip_task_failed` | None (R4) | avail (R3) | avail (R3, R5) | None (R6) | None (R7) | avail (R8) | needs a manipulation outcome in the window |
| `signal_quality.ecg_sqi` | avail (R2) | avail (R2) | avail (R2) | avail (R2) | None (R7) | avail (R8) | ward-side |
| `signal_quality.ppg_sqi` | avail (R2) | avail (R2) | avail (R2) | avail (R2) | None (R7) | avail (R8) | ward-side |
| `signal_quality.cuff_error_code` | avail (R2) | avail (R2) | avail (R2) | avail (R2) | None (R7) | avail (R8) | ward-side |
| `cross_device.pulse_vs_ecg_hr_diff` | avail (R2) | avail (R2) | avail (R2) | avail (R2) | None (R7) | avail (R8) | ward-side |
| `witness.robot_present` | None (R4) | avail (R9) | None (R5) | None (R6) | None (R7) | avail (R8) | in S4 a True seen before the outage remains (note 3) |
| `witness.identity_confirmed` | None (R4) | avail (R9) | None (R5) | None (R6) | None (R7) | avail (R8) | needs an identity check |
| `witness.intake_observed` | None (R4) | avail (R9) | None (R5) | None (R6) | None (R7) | avail (R8) | True remains if an `INTAKE` event lies in the window |
| `crypto_temporal.authenticated` | avail (R2) | avail (R2) | avail (R2) | avail (R2) | None (R7) | avail (R8) | BLE devices only |
| `crypto_temporal.seq_gap_or_replay` | avail (R2) | avail (R2) | avail (R2) | avail (R2) | None (R7) | avail (R8) | BLE devices only |
| `crypto_temporal.timestamp_implausible` | avail (R2) | avail (R2) | avail (R2) | avail (R2) | None (R7) | None (R7, R8) | needs independent clocks |

Reasons.

- R1: set from the violated record; no source and no placement dependence. In S5 no capability is involved (not applicable).
- R2: derived at the ward node from device streams and gateway events; the robot is not in the scope or not in the data scope, so the cell does not depend on the robot.
- R3: an aggregate or a robot report that exists while the robot is deployed and in the system scope of the template (scope table); in S1 the robot component is absent.
- R4: wholly robot-derived; no robot in the deployment, so `None`.
- R5: the robot is alive and reports its tasks; its witness channel is unavailable because it is not co-located (H-MASK). Its liveliness is denied and its task outcomes exist for its own tasks.
- R6: the robot node is `unreachable`: the ward asserts liveliness False and the node status entry reads `unreachable`; the robot produces no input after the lapse, so the fields that need it are `None` unless an input inside the window before the lapse gives them a value (an asserted True, or an outcome event; note 3 of Field semantics).
- R7: capability missing on every in-scope source: `status_reports`, `supervised`, deadline, `seq`, `two_clocks`, `authenticates`, `error_codes`, quality, `diagnostics`, `battery`, navigation or manipulation reporting, `perception` or `identity_check`, or the stream itself (no pulse or ECG stream). EX-7 removes each capability in turn and lists exactly the fields that become `None`.
- R8: S6 shown for the reference profile of EX-7; the cell is `avail` when the trace carries the convention keys and the profile declares the capability, and `None` otherwise. The generator decides which keys it emits (EC-OP-2).
- R9: available while the robot is co-located and its channel covers the window (coverage condition of the field).

EX-7 (reference extractor, fixture day: cuff frames at 20:00 and 20:30, an ECG sample every ten minutes with quality, one SpO2 sample with quality, a dispense at 21:00 with its `auth` Sample, the robot co-located from 20:50 with presence samples every minute and success outcomes of its tasks, initial node reports at 00:00; instances `hold` for the system and ward-side fields and `int` for the witness fields). The matrix above for S1 to S4 and S6 equals the output of the reference extractor field by field (the cells `avail` and `None`); for S5 the extractor was run once per capability, with the result: without `authenticates` only `crypto_temporal.authenticated` is `None`; without `seq` exactly `crypto_temporal.seq_gap_or_replay` and `system.ble_link_quality`; without `two_clocks` exactly `crypto_temporal.timestamp_implausible`; without quality on the ECG samples exactly `signal_quality.ecg_sqi`, and likewise `signal_quality.ppg_sqi` for the pulse oximeter; without `error_codes` exactly `signal_quality.cuff_error_code`; without `diagnostics` exactly `system.diagnostics_ok`; without `supervised` exactly `system.liveliness_ok`; without `status_reports` the four fields `system.node_lifecycle`, `system.liveliness_ok`, `system.diagnostics_ok` and `system.battery_low`; without a declared deadline exactly `system.qos_deadline_missed`; without `battery`, navigation reporting, manipulation reporting or `identity_check` exactly `system.battery_low`, `system.nav_task_failed`, `system.manip_task_failed` or `witness.identity_confirmed`; without a pulse stream exactly `cross_device.pulse_vs_ecg_hr_diff`; without an ECG stream exactly that field and `signal_quality.ecg_sqi`; without `perception` exactly the three witness fields.

## Ablation A4 mask

Ablation A4 removes the embodied channel (analisi §5.6: robot lifecycle, perception, witness): the pair `CH-WIT` and `CH-SYS-ROBOT`. The contract rule is that all `witness` fields and all robot-derived `system` fields become `None`, and fields that aggregate ward and robot sources are recomputed from the ward-side sources and are `None` only if none remains. The mask below applies this rule field by field. WS08-T04 applies the table without further interpretation.

| field | action | what remains or why |
|---|---|---|
| `provenance.violated_template` | unchanged | no robot input |
| `provenance.template_kind` | unchanged | no robot input |
| `system.node_lifecycle` | recompute | the robot entry is removed; the device entries remain; `None` only if no device node of the scope reports status |
| `system.diagnostics_ok` | recompute | the robot component is removed; recomputed over the device nodes with the aggregation rule |
| `system.liveliness_ok` | recompute | the heartbeat supervision of the robot is removed with the robot (D-11); recomputed over the supervised device nodes |
| `system.qos_deadline_missed` | recompute | the robot heartbeat deadline and any robot stream deadline are removed; recomputed over the device streams |
| `system.ble_link_quality` | unchanged | BLE devices only; the robot is not in its scope |
| `system.battery_low` | None | wholly robot-derived (D-2) |
| `system.nav_task_failed` | None | wholly robot-derived |
| `system.manip_task_failed` | None | wholly robot-derived |
| `signal_quality.ecg_sqi` | unchanged | ward-side device |
| `signal_quality.ppg_sqi` | unchanged | ward-side device |
| `signal_quality.cuff_error_code` | unchanged | ward-side device |
| `cross_device.pulse_vs_ecg_hr_diff` | unchanged | ward-side devices |
| `witness.robot_present` | None | the witness channel is the embodied channel |
| `witness.identity_confirmed` | None | the witness channel is the embodied channel |
| `witness.intake_observed` | None | the witness channel is the embodied channel |
| `crypto_temporal.authenticated` | unchanged | BLE devices only (D-12) |
| `crypto_temporal.seq_gap_or_replay` | unchanged | BLE devices only (D-12) |
| `crypto_temporal.timestamp_implausible` | unchanged | BLE devices only (D-12) |

The three classes are: **None** (six fields, wholly robot-derived: the three `witness` fields, `system.nav_task_failed`, `system.manip_task_failed`, `system.battery_low`), **recompute** (four aggregate fields: `system.node_lifecycle`, `system.diagnostics_ok`, `system.liveliness_ok`, `system.qos_deadline_missed`) and **unchanged** (ten fields: both `provenance` fields, `system.ble_link_quality`, the three `signal_quality` fields, `cross_device.pulse_vs_ecg_hr_diff`, the three `crypto_temporal` fields).

**Constants for WS08-T04.** `EMBODIED_MASK_ALL` is the path set of the class None (six paths). `EMBODIED_MASK_WITNESS` is the three `witness` paths (the variant that keeps the robot task outcomes and the battery). The class recompute cannot be a path mask: a scalar that aggregates a robot component and device components cannot be split after the fact (EX-8 shows the difference). Applying only `EMBODIED_MASK_ALL` to the vectors of the full run leaves the robot components of the four aggregate fields in place and is therefore a partial A4: the robot lifecycle, heartbeat and deadline evidence remain, and a robot crash is still visible through `system.liveliness_ok`. The full A4 needs the extractor run with the robot sources excluded (the scope without the robot node), which is the reading of the contract rule above (EC-OP-5; the extractor option is for WS05-T07).

**What A4 does not mask.** A4 does not mask `crypto_temporal` or `cross_device`: they are computed from the BLE device streams, with the robot out of their scope (D-12), and under A4 they equal their full-run values for every template. It does not mask `signal_quality`, `system.ble_link_quality` or `provenance`. It does not change any verdict: it acts on the evidence of the records of the full run, so a VIOLATED INT instance with `no_witness` of the full run is still violated, whereas a run without the robot would leave it PENDING with a `channel_unavailable` marker (T05 section 3.5). The two implementations of A4 (evidence mask on the full run, run without the robot) therefore differ on `int` and on the obligations that the robot carries out; WS08-T04 states which one it reports (EC-OP-5).

EX-8 (reference extractor, fixture day of EX-7, the robot co-located (S2), away (S3) and down (S4); instances `sched`, `hold`, `resp`, `int`): for every one of the twelve combinations the six fields of the class None are `None` and the eight evidence fields of the class unchanged equal their full-run values (the two `provenance` fields come from the record and need no run); the evidence of A4 equals the evidence of a run without the robot (S1), field by field. In S4 the pure path mask leaves `system.liveliness_ok` False and `system.diagnostics_ok` `None` where the extractor with the robot excluded gives True and True; the robot key of `system.node_lifecycle` is removed only by the exclusion. For an instance of `sched` whose only remaining node reports no status, the four recompute fields are all `None`.

## Timing and evidence window

### Clocks and the acceptance rules

Every input has two clocks (`#time-and-units` rule 3, T01 section 4.1). `t_device_ms` orders observations and positions them on the grid; `t_rx_ms` is the arrival time in the monitor clock and drives the reorder buffer. The buffer releases inputs in device-time order and finalises step `k` at monitor time `t_k + D`. At arrival an input is classified (T01 sections 4.2 to 4.4, T05 section 6.2): **future-stamped** if `t_device_ms > t_rx_ms + clock_skew_max_ms`; otherwise **late** if `t_rx_ms > t_{k_up(t_dev)} + D` (an arrival exactly at the watermark is on time); otherwise **accepted**. A late or future-stamped input is not used for any value (no held value, no counter, no evidence of the value kinds) and is counted per source. Two axes follow, and each field uses one of them.

| axis | time | what it is used for |
|---|---|---|
| E (event) | `t_device_ms` after the reorder buffer, i.e. the visible step of an accepted input | every value field: node status, task outcomes, quality, pulse and ECG, presence, `INTAKE`, error codes |
| R (arrival) | `t_rx_ms` of every received input, accepted or not | the counters of `crypto_temporal.*`, the delivery ratio, and the arrival gaps of the deadline |

Ward-generated events carry the ward clock on both axes (H-WARDCLK). Which axis each field uses: the `provenance` fields none; `system.node_lifecycle`, `system.diagnostics_ok`, `system.liveliness_ok`, `system.battery_low`, `system.nav_task_failed`, `system.manip_task_failed` axis E; `system.qos_deadline_missed` and `system.ble_link_quality` axis R; the three `signal_quality` fields and `cross_device.pulse_vs_ecg_hr_diff` axis E; the three `witness` fields axis E on the steps of the read window; the three `crypto_temporal` fields axis R.

### Evidence window, last admissible evidence time and cut-off

For a violated instance `i` with anchor `a`, let `a_read(i)` be the start of what its body reads: `a` for `range`, `sched`, `resp`, `sys` and the limit of `count`; `a - hold_lookback` for `hold`; `a - int_window` for `int`; the start of the day for the day-end obligation of `count`. Let `Ue(i)` be `VerdictRecord.decided_at_ms` of the VIOLATED record (for a `PREDICTED_VIOLATION` record, which has none, `t_eval_ms`). Both are grid times. The rules:

1. **Last admissible evidence time** `Ue(i)`: an input on axis E is used only if its visible step is not after the step of `Ue(i)`.
2. **Window start**: an input on axis E belongs to the window if its visible step is not before `k_up(a_read(i) - evidence_margin_ms)`; the witness fields use the start `a_read(i)` without margin, so that they agree with the INT verdict (EX-9). An input on axis R belongs to it if `t_rx_ms` lies in `[a_read(i) - evidence_margin_ms, C(i)]`. The state in force at the start (a node status, a battery report) counts as entered at the start.
3. **Cut-off** `C(i) = Ue(i) + D + evidence_grace_ms` in monitor time: an input received after `C(i)` is logged and does not change κ; every field is a function of the inputs received by `C(i)` (EX-10, check P3: appending inputs received after the cut-off changes no field). The cut-off is a function of the first VIOLATED record of the instance, not of the record being processed, so the refinement records of a SCHED instance (T05 section 6.5) do not change the vector.
4. **Cost.** With `evidence_grace_ms` equal to 0, `C(i)` is the monitor time at which the verdict of the step is emitted (`t_{k_d} + D`, `emitted_at_monitor_ms` of V-LATE-1 and V-LATE-2), so attribution adds no latency to the verdict. A positive grace delays the alert by the grace, before compute time. The alternative, an alert emitted at the verdict time with a provisional κ that is revised when later evidence arrives, is not adopted (D-7).

EX-10 (random, seeded). P2: of 20000 draws of an input and a decision step on the grid, every input that is on time and has `t_device_ms` not after the decision time has `t_rx_ms` not after the decision time plus `D`, so grace 0 loses no on-time evidence. P3: 300 draws of extra inputs received after the cut-off change no field. P4 (D-3): in 5000 draws of two BLE devices with losses, silent devices and copies, a ratio below one always comes with `crypto_temporal.seq_gap_or_replay` True, and the field True with a ratio of exactly one always has an injected copy (586 draws); in 625 draws the field is True and the ratio is `None` (a capable device with no finalised message), the case in which the pair cannot separate a gap from a repeat. P1 is under D-9.

**What the cut-off cannot see.** An input is late because it arrives after the watermark of its own step. When its own step is the decision step of the instance, the verdict is emitted at that same watermark, so a late input that caused the violation arrives after the cut-off unless the grace is at least its lateness; a late input of an earlier step has more room, because its watermark precedes the cut-off by the number of steps in between. EX-2 uses the data of V-LATE-1 (tick at 09:00, measurement with device time 09:29:50 received at 09:30:40, `D` 30000, decision time 09:30:00, so `C` is 09:30:30 with grace 0). (a) With only that message from the cuff, `crypto_temporal.timestamp_implausible` is `None` at grace 0 and at 9999 (the cuff has no message in the window) and True from grace 10000 (the arrival is 10000 after `C`). (b) With an earlier on-time message of the cuff at 09:05, the field is False at grace 0 although a late input exists, and True from grace 10000; `crypto_temporal.seq_gap_or_replay` is False in both. (c) With the earlier message at 09:05 only, because the later one never arrives, the field is False and so is the sequence field (a gap is seen only when a later message arrives, condition SEQ of FM). So at grace 0 a denied `crypto_temporal.timestamp_implausible` means "no late or future-stamped input among the inputs received by the cut-off", which is weaker than "no input was late", and a violation caused by a delay can look coherent. The grace that closes the case is a registry parameter (EC-OP-3); it is not given a value here.

**Detection lag of the ward-generated evidence.** A liveliness lapse (`unreachable`), a missed heartbeat deadline and a deadline gap are detected by the ward node at the lapse of the lease or of the deadline, not at the onset of the outage, and the node stamps them with its own clock (H-WARDCLK). Evidence of an outage that began before `Ue(i)` is therefore present on axis E only if the detection instant is not after `Ue(i)`, and the deadline gap rule (axis R) only if it is not after `C(i)`. With a lease longer than the time from the onset to `Ue(i)`, `system.liveliness_ok` stays True although the outage is real (condition LC of FM); a BLE connection loss seen immediately by the gateway (`link_down`) is not subject to the lease and shows in `system.node_lifecycle`. The lease and deadline values are run parameters of the device profile; none is given here.

### Decision on out-of-order input (D-9)

Out-of-order input is input whose arrival order differs from its device-time order. Within the bound (arrival not after the watermark) the buffer restores device-time order before the accepted trace, so the verdicts do not change (FX-12). The decision for the evidence:

- `crypto_temporal.timestamp_implausible` is computed only from the classification above (late or future-stamped). Non-monotone device time in arrival order is not an input of the field: after the buffer there is no inversion to observe, and an input displaced beyond the bound is already late.
- `crypto_temporal.seq_gap_or_replay` is computed on sets, not on arrival order. A repeat is a received `(name, seq)` equal to an accepted one (earlier today or retained from the previous day, H-SEQSTATE), where `name` is `Sample.signal` or `Event.kind`; the members of one frame share a `seq` and differ in `name`, so they are not repeats of each other. A gap is a `seq` value of the device (all names together) that lies between the base and the top and is missing at the cut-off, where the base is the largest finalised `seq` received before the window (or retained) and the top the largest finalised `seq` received in it, and "finalised" means that the watermark of the message is not after the cut-off.

Reasons. The buffer already absorbs benign reordering; evidence on arrival order would raise a flag on every reordering within the bound (in the draws of EX-10 about one draw in six has a non-monotone `seq` in arrival order and nothing wrong), and C3 evidence from a benign cause is the failure ADR-010's integrity-first rule cannot afford. The set rule has no false gap from reordering: if each message of a device with consecutive sequence values (H-SEQT) arrives within its bound, every smaller value has arrived by the watermark of any larger one, whatever the cut-off (EX-10 check P1: 4000 draws, no repeat, no gap, ratio 1.0, nothing late).

Conditions. H-SEQT, delays within the bound, and a cut-off that is not before the watermark of the messages it certifies. If the real reordering exceeds `D` the late rule rejects those messages and `crypto_temporal.timestamp_implausible` is asserted for a benign cause: the false-evidence rate is set by the choice of `D`, not by this rule. A frame whose members are delivered partly (OP-7 of FM) shows no gap if one member arrives.

EX-1 (fixture, `D` 120000, a cuff stream, window from 09:00 to the cut-off 09:30; device times 09:10:20, 09:11:10, 09:12:05, 09:13:00 with `seq` 1 to 4): (a) in order: no repeat, no gap, ratio 1.0; (b) `seq` 2 arrives before `seq` 1, both within the bound: the same, nothing late; (c) `seq` 2 lost: gap, ratio 0.75; (d) `seq` 2 arrives after its watermark but before the cut-off: no gap (the value is present), ratio 1.0, and the message is late, so `crypto_temporal.timestamp_implausible` is True; (e) `seq` 2 arrives after the cut-off: gap, ratio 0.75, nothing counted late (the same reading as a loss: a delay beyond the cut-off cannot be told from a loss at the cut-off); (f) a copy of `seq` 2 on time: repeat, no gap, ratio 1.0; (g) `seq` 2 lost and a copy of `seq` 3: repeat and gap, ratio 0.75; (h) frames 9 (a `bp` Sample and a `measurement` Event), 10 (a `measurement_missed` Event only) and 11: no repeat, no gap, ratio 1.0, whereas the `bp` stream read alone (9 and 11) would show a false gap; (i) frame 10 lost: gap, ratio two thirds; (j) a verbatim copy of the `bp` Sample of frame 9: repeat, no gap; (k) a stale-stamped copy of the previous day's `bp` with `seq` 21 (retained state: 21, 22, 23) arriving with the genuine frame 24: repeat True, no gap, and the copy is late.

Consequences for earlier documents.

- **FM, row `out_of_order` and OP-14.** Resolved as FM states it: within the bound `crypto_temporal.timestamp_implausible` is not raised, and `crypto_temporal.seq_gap_or_replay` is not raised either (the MINOR of the WS02-T01 review on `seq` in arrival order is closed in the same way). A delay within the bound can still lengthen an arrival gap and assert `system.qos_deadline_missed` where a deadline is declared, so the statement is about these two fields and not about the whole vector. The step 4 text of the task that derives `timestamp_implausible` also from non-monotonic device time is not followed.
- **FM, `link_delay` beyond the bound.** The delayed input is late (`crypto_temporal.timestamp_implausible` raised) and fills its sequence value if it arrives before the cut-off (so `crypto_temporal.seq_gap_or_replay` is not raised, as FM says); if it arrives after the cut-off it reads as a loss (EX-1 (e)).
- **FM, `ble_dropout` and `message_drop`.** `system.ble_link_quality` is raised only under the same condition SEQ as the gap, because both come from the `seq` values: it needs a device with `seq` and a later message that reveals the loss. FM lists it as raised without condition for `ble_dropout`; it becomes conditional. WS04-T07 transcribes that row and must follow.
- **TM, TX-9 and the provisional reading.** `crypto_temporal.timestamp_implausible` is not "not applicable (computed from the two clocks)": it is `None` when the clocks are not independent for the device and when the device has no message in the window. A replay with stale stamps raises it as TM says (late input, EX-1 (k)).
- **WS02-T04.** A SCHED violation caused by a silent cuff has `crypto_temporal.*` `None` (no basis), so the exclusion conditions of C1 that need those fields denied are not met; this is intended (EX-3 (f)).

### Which fields the timing touches

The reorder buffer and the late rule decide which inputs are accepted: a value field never uses a late or future-stamped input. The buffer does not repair loss, delay beyond the bound or skew beyond `clock_skew_max_ms` (FM section Link and time faults); an input that is neither future-stamped nor late is accepted even when its stamp is wrong by an offset (a device ahead by at most `clock_skew_max_ms`, or behind by less than the bound), and then its grid position is wrong and no field shows it (FX-4 (a) and (d)).

## Parameters requested from the registry

Names only; no value is given in this document. The request goes to WS01-T03 (registry schema) and WS00-T07 (clinician and engineering review). A name that already exists (`clock_skew_max_ms`) is listed because this document gives it a consumer. A value quoted from analisi anywhere in the related documents is "illustrative, unverified".

| name | unit type | consumer | role |
|---|---|---|---|
| `evidence_margin_ms` | ms | extractor, WS02-T04 | lead time before the read window of an instance within which system evidence still counts |
| `evidence_grace_ms` | ms | extractor, WS05-T07 | the time after the verdict emission during which later inputs still count; the cost is alert latency (D-7) |
| `hr_coherence_tolerance` | bpm | WS02-T04 rule | threshold that makes `cross_device.pulse_vs_ecg_hr_diff` asserted |
| `hr_coherence_max_age_ms` | ms | extractor | oldest held ECG value that a pulse sample may be compared with |
| `ecg_sqi_floor` | dimensionless | WS02-T04 rule | quality below which `signal_quality.ecg_sqi` is asserted |
| `ppg_sqi_floor` | dimensionless | WS02-T04 rule | quality below which `signal_quality.ppg_sqi` is asserted |
| `ble_link_quality_floor` | dimensionless | WS02-T04 rule | delivery ratio below which `system.ble_link_quality` is asserted; a ratio below one already means a missing sequence value |
| `clock_skew_max_ms` | ms | extractor, monitor | the plausibility bound of a device stamp: a stamp later than the receive time by more than this is future-stamped (T01 section 4.4) |
| `dispense_bounce_interval_ms` | ms | proposed `dispenser/interval_since_previous_ms` (EC-GAP-1) | the interval under which two openings are a bounce; the analisi nominal "below one second" is illustrative, unverified |

Run parameters of the device profile, declared per source and not clinical (D-8): `liveliness_lease_ms` and the data-stream deadline `qos_deadline_ms` (null for an event-driven device). They are named in WS07-T03 (`qos.liveliness_lease_ms`); the other capabilities are Booleans.

## Decisions

### D-1 Key of the evidence mapping

**Options.** (a) `VerdictRecord.instance_key`; (b) `(care_plan_id, instance_key)` as a tuple (not a `str`); (c) a synthetic key made by the extractor.

**Chosen.** (a): the key of `Mapping[str, EvidenceVector]` in `#attribution` and `#detector` is `VerdictRecord.instance_key` of the violated record (or of the predicted one, replaced by the violated one when it arrives). `TemplateInstance.instance_key` is unique within a care plan only, so the mapping is per care plan; a caller that evidences several plans builds one mapping per plan or prefixes the key with `<care_plan_id>/`.

**Reason.** The key already exists on the record, it is a `str` as the contract types it, and an absent key means an all-`None` vector except provenance (WS05-T07 test 13). The multi-plan limit is a declared consequence (EC-GAP-2, ADR-033).

### D-2 Meaning of the single `system.battery_low`

**Options.** (a) the battery of the nodes that produce the signals of the violated template, with the robot part in the A4 mask (the proposal of the task); (b) the robot battery only; (c) the battery of any node.

**Chosen.** (b). `system.battery_low` is the state of the robot battery.

**Reason.** The catalogue has one battery fault, `battery_depleted` of the robot (R3 weakness 2); FM records that a device battery fault has the signature of `ble_dropout` or `process_kill` of the device (FM OP-4); the simulation has no battery model (WS07 README). Under (a) the field would aggregate a robot and a device component and could not be a pure path in the A4 mask; under (b) it is wholly robot-derived and the mask stays a path set. A device battery has no field (declared limit, EC-GAP-7).

### D-3 Sequence gap against replay inside one field

**Options.** (a) keep one Boolean for gap or repeat and give the attribution layer a way to tell them apart from other fields; (b) split the field (a repeat is integrity evidence, a gap is system evidence); (c) set the field only for a repeat and report a gap only through `system.ble_link_quality` and the deadline.

**Chosen.** (a) now, (b) proposed (ADR-034). `crypto_temporal.seq_gap_or_replay` is True for a repeat or a gap, as defined in D-9. `system.ble_link_quality` is the delivery ratio over the distinct `seq` values and equals 1.0 exactly when no value is missing. Hence the pair gives: field True with `system.ble_link_quality` equal to 1.0 means a repeat without a gap (a replay symptom; the ratio exists only if every capable device had a finalised message in the window); field True with a ratio below 1.0 means a gap is present and a repeat is not excluded (EX-1 (c), (f), (g)). The interim reading of the attribution layer, which is WS02-T04's, therefore may treat a True field with ratio 1.0 as integrity evidence, and must not treat a True field with a ratio below 1.0 as integrity evidence alone.

**Reason.** Under the hierarchy of ADR-010 integrity evidence wins, and a link loss must not become C3. (c) contradicts the field name and the consumers that read a gap as raising it (the rows of FM, the signatures of WS04-T07, the oracle of WS07-T05); (b) is the cleaner contract and needs a version bump decided at M1 (ADR-021). Declared limit of (a): a replay together with a loss is not told from a loss; the ratio is a delivery ratio, so a floor above 1.0 is meaningless and `ble_link_quality_floor` applies only to "degraded", not to "a gap exists".

### D-4 Vocabulary of `system.node_lifecycle` and the commanded marker

**Options.** (a) a closed vocabulary of states plus a suffix for the commanded transition; (b) a separate Boolean field; (c) free strings.

**Chosen.** (a). Values are `unconfigured`, `inactive`, `active`, `finalized` (the lifecycle states the sources use), `link_down` (the BLE connection of a device was lost, seen immediately by the gateway) and `unreachable` (the liveliness lease lapsed, written by the gateway or the watchdog), optionally followed by `+commanded` on a lifecycle state when the transition was announced beforehand (`payload.commanded` true). `unreachable` and `link_down` are never commanded. Asserted: any entry other than `active` and than `<state>+commanded`.

**Reason.** The contract field is `Mapping[str, str]`, so a value grammar carries the marker with no contract change (FM OP-3). Keeping `link_down` apart from `unreachable` keeps condition LC of FM: a short BLE loss changes the node status without lapsing the liveliness lease. A crash is `unreachable`, never a lifecycle transition (analisi §4.6, row 15:00).

### D-5 Meaning of `system.nav_task_failed`

**Options.** (a) failed, timeout or late outcome of a navigation task; (b) only failed and timeout; (c) any outcome other than success of any task.

**Chosen.** (a), and the same for `system.manip_task_failed` with `payload.task` equal to manipulate. `late` means completed after the deadline induced by the schedule (WS07-T04: finishing after the window end).

**Reason.** A robot late to the window is the C2 row 5 of the matrix; counting `late` as failure is what makes `nav_delay` raise the field (the proposal D-5 of the task, used by FM). A missing outcome is `None`: a crash produces no outcome, and a missing outcome is not a failed one.

### D-6 Dependency among the witness fields and the combination that counts as intake

**Options.** (a) independent fields; (b) `identity_confirmed` requires `robot_present`; (c) `intake_observed` requires identity.

**Chosen.** (b). `witness.identity_confirmed` is `None` unless `witness.robot_present` is True (an identity cannot be confirmed for a patient not perceived) and unless the robot has an identity check and reported one. `witness.intake_observed` does not depend on identity (it is the event of ADR-004). Three tiers of positive backing, for WS02-T04: perceived presence alone proves only that someone was perceived (presence is not identity, R3 weakness 5); an observed intake without a confirmed identity is the intake of whoever was seen; an observed intake with a confirmed identity (`witness.identity_confirmed` True) is the strongest reading the contract carries.

**Reason.** It keeps DISPENSE apart from INTAKE (ADR-004) and does not let the weakest field stand for the strongest claim. The failed-visit rule keeps a denial from being written when the robot could not witness (FM OP-2).

### D-7 Evidence cut-off

**Options.** (a) the emission instant of the verdict (`decided_at_ms` plus `D`); (b) that instant plus a grace `evidence_grace_ms`; (c) emit at the verdict time with a provisional κ and revise it.

**Chosen.** (b), with the grace a registry parameter whose lower bound is 0 (which is (a)). `C(i) = Ue(i) + D + evidence_grace_ms`; `Ue(i) = decided_at_ms`.

**Reason.** At grace 0 no on-time evidence is lost and no latency is added (EX-10 P2), but a late input that caused the violation is outside the cut-off unless the grace covers its lateness (EX-2). The cost of a positive grace is the grace in alert latency, before compute time. (c) is rejected for v1 because the Attribution contract takes violated records and the alert of WS05-T07 `update` already replaces predicted alerts; revising a definitive alert is a different semantics that WS02-T04 and WS01-T07 would have to define.

### D-8 Device capability declaration

**Options.** (a) a device profile that declares capabilities per source; (b) infer capabilities from the observed trace; (c) assume every capability.

**Chosen.** (a) (ADR-036). A device that cannot authenticate, report a quality, provide a sequence number, report error codes, report diagnostics or declare a deadline yields `None` for the dependent field and is never read as a negative.

**Reason.** (b) converts an absence into a negative (a device that sent no code in the window would be taken as reporting none); (c) is false for the benchmark devices. The profile is a run-level mapping (benchmark `manifest.json` settings, ADR-025, or a ROS 2 parameter file); no contract type changes.

### D-9 Out-of-order input

**Options.** (a) evidence on arrival order; (b) evidence on the accepted trace and on sets as defined in the section Timing and evidence window.

**Chosen.** (b). Recorded with reasons, conditions and consequences in that section, and checked by EX-1 and EX-10 (P1).

**Reason.** The buffer restores order within the bound; arrival-order evidence would flag benign reordering.

### D-10 Scope of the scalar `system` fields and the aggregation rule

**Options.** (a) a scope table per template and the aggregation rule of the section Conventions; (b) per-node mappings for every system field (a contract change); (c) a single global reading over all nodes.

**Chosen.** (a) now, (b) offered at M1 (ADR-033).

**Reason.** A global reading (c) lets a fault on an unrelated node turn a clinical violation into C2 (the relevance question of WS02-T04). Per-node mappings would also let the A4 mask be applied after the fact by removing the robot key, but they change four field types. The scope table is derived from sources (T02 section 3.1, section 5.3) and from H-VISIT; a deployment that violates H-VISIT edits the table.

### D-11 Channel split by subject node

**Options.** (a) split the system health evidence by the observation point (ward node or robot); (b) by the subject node (device or robot).

**Chosen.** (b). `CH-SYS-WARD` is evidence about device nodes and links; `CH-SYS-ROBOT` is evidence about the robot node, including the heartbeat supervision that the ward node performs.

**Reason.** The hypothesis of A4 is about the robot lifecycle and perception (analisi §5.6): if the supervision of the robot heartbeat stayed with the ward-side channel, a robot crash would remain attributable through liveliness after the embodied channel is removed, and A4 would measure the loss of the witness and of the task outcomes but not that of the robot lifecycle that analisi names. The task text starts from (a); the difference is exactly the robot component of `system.liveliness_ok`, `system.qos_deadline_missed` and `system.node_lifecycle`, and WS02-T05 states A4 as `CH-WIT` and `CH-SYS-ROBOT` unavailable, which holds under (b). Ward-hosted nodes other than the trusted base are out of the fault catalogue (FM hypothesis 6), so `CH-SYS-WARD` does not list them.

### D-12 Scope of `crypto_temporal.*` and `system.ble_link_quality`

**Options.** (a) every in-scope producer including the robot; (b) the BLE device streams only.

**Chosen.** (b).

**Reason.** The robot is inside the trusted base (TM, assets table), its streams are not BLE links and carry no device authentication, and with (b) `crypto_temporal.*` is unchanged under A4 for every template, which is the contract rule of the embodied-channel ablation. The cost is stated: the lateness or loss of the robot's own presence stream is not seen by these fields. FM CAS-5 (a link fault on the presence stream that reads as a violated INT) is then visible only through `system.qos_deadline_missed` where a deadline is declared on the robot stream, and otherwise leaves a violated INT with provenance only, which the decision table planned in WS02-T04 cannot read as C2 or C3 (provenance is never sufficient) or as C1 (`int` never yields C1), so the outcome is UNDETERMINED (EC-OP-6; WS02-T04 task text, checks 4 and 5).

### D-13 Source of `signal_quality.ppg_sqi`

**Options.** (a) `Sample.quality` of `SignalId.SPO2`; (b) a new signal for a PPG-derived heart rate.

**Chosen.** (a).

**Reason.** `SignalId` has no PPG-specific member; the pulse oximeter is the optical (PPG-based) device in the signal table and its sample is `SPO2`. A wearable heart rate derived from PPG has no member (EC-GAP-12, no change proposed).

### D-14 Equivalence between `/ralmon/robot_evidence` and the trace

**Options.** (a) the topic is a second source of the robot fields; (b) the topic is the live carrier of trace items.

**Chosen.** (b), by the correspondence in the section Derivation from the trace schema and ROS 2.

**Reason.** One source per field keeps the offline and live values equal and keeps the extractor free of a merge rule between two readings of the same fact.

## Contract gaps and change proposals

The contract is not edited. A gap that needs a contract change has an ADR with status proposed and the tag `[DA-CONFERMARE]`, appended to `docs/plan/03-decisions.md`; amendments are decided at M1 (ADR-021), and none of the proposals contradicts ADR-026 to ADR-031 (they do not touch the INT form, the fixture registry, the order key, the verdict extensions, the conformal quantiles or the container). G-1 to G-6 are the gaps of the task text.

| id | description | analisi rows | affected tasks | proposal | ADR |
|---|---|---|---|---|---|
| EC-GAP-1 | G-1. No field carries the dispenser content change or the interval between openings, although the double take and the bounce depend on them (FM-GAP-DISP) | 6, 7 | WS02-T04, WS02-T05, WS04-T05, WS04-T07, WS05-T07, WS07-T03, WS10-T03 | add a group `dispenser` to `EvidenceVector` with `dispenser/interval_since_previous_ms` and `dispenser/content_change`, both `None` when the dispenser has no content sensing; channel `CH-DISP` | ADR-032 |
| EC-GAP-2 | G-2. The key of `Mapping[str, EvidenceVector]` is not stated; the scalar `system` fields do not say which node they refer to (FM-GAP-LIVE); `system.battery_low` and `witness.robot_present` have an unstated meaning | 3, 5 | WS02-T04, WS05-T07, WS05-T09, WS08-T04 | key is `VerdictRecord.instance_key` per care plan (D-1); scope table and aggregation rule (D-10); `battery_low` is the robot battery (D-2); `robot_present` reads `PRESENCE` | ADR-033 |
| EC-GAP-3 | G-3. `crypto_temporal.seq_gap_or_replay` mixes a loss (a C2 symptom) and a replay (a C3 symptom); TM-GAP-SEQ, FM-GAP-SEQ | 8, 9 | WS02-T04, WS02-T05, WS04-T07, WS04-T08, WS05-T07, WS07-T05 | interim reading through `system.ble_link_quality` (D-3); split into `crypto_temporal/seq_repeat` and `system/seq_gap` at M1 | ADR-034 |
| EC-GAP-4 | G-4. `Event.payload` keys and the per-message verification outcome are not defined in `#trace-schema`; there is no `EventKind` for a gateway outcome (TM-GAP-AUTH) | 8, 9, 10 | WS04-T01, WS04-T06, WS04-T07, WS04-T08, WS05-T09, WS07-T03, WS07-T04 | adopt the trace evidence conventions as binding; interim `DEVICE_ERROR` from the gateway with `verification`; propose a new member `EventKind/VERIFICATION` | ADR-035 |
| EC-GAP-5 | G-5. No task owned the step that builds an `EvidenceVector` from an `ObservedDay` and a `VerdictRecord` | none | WS05-T07, WS08-T01 | resolved without a contract change: the public API already names `EvidenceExtractor` and `extract_evidence` (ADR-024) and WS05-T07 step 1 and 6 own them; report to the plan lead that the owner is WS05-T07 | none |
| EC-GAP-6 | G-6. No field carries clock health, so `clock_skew` is not told from `timestamp_manipulation` and a skew inside the bound is invisible (TM-GAP-TIME, CG-10) | none | WS02-T05 | accepted as a declared limit: the field is not split and no clock-health field is proposed (the monitor does not estimate offsets, T01 section 4.4); WS02-T05 marks the rows partial or not distinguishable | none |
| EC-GAP-7 | The device battery has no field; a single Boolean cannot hold two nodes (D-2) | none | WS02-T05 | declared limit: the device battery fault is read as `ble_dropout` or `process_kill` of the device (FM OP-4) | none (see ADR-033) |
| EC-GAP-8 | No contract object carries the device profile (capabilities, lease, deadline) that the derivation needs (D-8) | none | WS05-T07, WS04-T11, WS07-T03 | a run-level profile convention | ADR-036 |
| EC-GAP-9 | The meaning of `SignalId.AUTH` against the verification outcome is not stated: a keyless injector can write an `auth` Sample in a deployment without verification, and INT then reads it as a witness (the first MINOR of the WS02-T02 review). It is recorded as a hypothesis, not assumed: this document derives `crypto_temporal.authenticated` only from the verification events and never from an `auth` Sample | 9 | WS02-T04, WS04-T08, WS05-T09, WS07-T03 | the gateway must not deliver as an `auth` Sample a message that failed verification, and a source without verification must not emit `auth` (to be confirmed) | ADR-035 |
| EC-GAP-10 | The availability of the robot channels is not in the trace: `ObservedDay` has no mask (CG-6 of T01); the golden cases give it as an input | 9 | WS04-T06, WS05-T02, WS07-T04, WS08-T04 | the mask is derived from the robot `NODE_STATE` (`state`, `colocated`) and H-MASK; no field is added | ADR-035 |
| EC-GAP-11 | The name `witness.robot_present` suggests the robot is present; the field reads the patient presence (note 1 of Field semantics) | none | WS02-T04, WS11 | documentation note; no change proposed | none |
| EC-GAP-12 | `SignalId` has no member for a PPG-derived heart rate; `signal_quality.ppg_sqi` reads `SPO2` (D-13) | none | WS04-T06 | documentation note; no change proposed | none |

### Consumer check (open points)

The consumers named in the task were read; the lines below are quoted from the task files as they are, and none is edited.

- **EC-OP-1. WS07-T04 publishes `manip_task_failed` false.** Quoted: "robot evidence on `/ralmon/robot_evidence` (`nav_task_failed`, `manip_task_failed` false, `battery_low` `None` because there is no battery model". Under D-5 the field is False only with at least one manipulation outcome that is `success`; the same task says "no manipulation fault exists in simulation", and its outcome events are "navigation failed, timed out, late, success". A False without a manipulation outcome is a denial with no observation: either the robot profile declares manipulation as an abstract step reported as `success` (then the denial is a declared capability), or the field is `None`.
- **EC-OP-2. WS04-T07 and WS07-T03 NODE_STATE conventions.** Quoted: "the gateway emits NODE_STATE events at window start and end with the uncommanded flag from `vocab.py`" (WS04-T07 test 2). Here a BLE loss is `link_down` at its start, and `unreachable` only when the lease lapses (condition LC); `commanded` is a flag that is present (true) for a deliberate transition and absent otherwise, not an "uncommanded" flag. WS07-T03 test "liveliness loss becomes link-lost event within the lease plus a margin" agrees with `unreachable`. The generator must also emit the robot `NODE_STATE` with `colocated` (EC-GAP-10); WS04-T06 line 17 plans the "robot presence and witnessed INTAKE", and WS08-T04 reads "the co-location schedule as recorded by WS04-T06 and WS04-T07, whose representation is stated in the completion note", so the schedule is not yet in the observed trace.
- **EC-OP-3. The grace parameter.** WS05-T07 step 1 asks for "the cut-off rule (D-7)" and test 32 for a vector "unchanged when inputs after its evidence cut-off (decision D-7) are added": agrees with D-7; the value of `evidence_grace_ms` is requested from the registry and decides whether a late input that caused the violation is visible (EX-2).
- **EC-OP-4. WS05-T07 test 36.** Quoted: "sets `system.liveliness_ok` to false and turns every robot-derived field and every `witness.*` field to `None` from that time". Under note 3 of Field semantics a fact asserted earlier in the window (a True `witness.robot_present`, an asserted `system.nav_task_failed`) stays; only the readings that need the channel to the end of the window become `None`.
- **EC-OP-5. WS08-T04 and the A4 mask.** Quoted (WS08-T04 test 1): "the constant contains at least the three `witness` fields, `system.nav_task_failed` and `system.manip_task_failed`, and exactly the further robot-derived fields listed in `evidence-channels.md`". `EMBODIED_MASK_ALL` is those six paths (the further field is `system.battery_low`). The class recompute (four fields) cannot be applied by `mask_evidence` as a path set; the same task says the ablation "acts on attribution only" and leaves verdicts unchanged (test 9), which differs from a run without the robot on `int`. WS08-T04 must either call the extractor with the robot excluded or report the partial A4.
- **EC-OP-6. Fault model CAS-5 and D-12.** FM CAS-5 says the evidence for a link fault on the robot's presence stream is `crypto_temporal.seq_gap_or_replay` or `crypto_temporal.timestamp_implausible`; under D-12 those fields do not cover the robot stream.
- **EC-OP-7. WS05-T07 test 29 and 31.** Test 29 expects `intake_observed` False with "`presence` present and no `intake` inside the evidence window"; here a False needs the robot status to say co-located at every step of the window (H-MASK), not only presence samples. Test 31 says "a gap with asserted link evidence does not set `seq_gap_or_replay` as integrity evidence": under D-3 the extractor sets the field for a gap, and the integrity reading is the rule's (WS02-T04, W-15).
- **EC-OP-8. WS04-T08 verification key.** "emit an Event from source `gateway` with the key declared in `vocab.py`" (step 4): the conventions table gives `DEVICE_ERROR` with `verification` and `subject`; and "Not covered by the injector: a forged `auth` Sample written by a keyless injector" (its notes) is EC-GAP-9.
- **EC-OP-9. WS04-T07 and `system.node_lifecycle` for `cuff_detached`.** FM OP-16 stands: whether a cuff detachment emits a `NODE_STATE` event. Under this document a `NODE_STATE` with `state` other than `active` is what raises the field.
- **EC-OP-10. WS02-T05.** Step 2 of WS02-T05 copies the gap list: the ids here are `EC-GAP-n`; G-1 is EC-GAP-1 and G-6 is EC-GAP-6. Its A4 outcome `when` is `{CH-WIT: unavailable, CH-SYS-ROBOT: unavailable}`, which agrees with D-11. `CH-DISP` is defined as proposed only.
- **EC-OP-11. WS07-T05.** Its oracle note that a sequence gap raised by dropped messages is also the symptom of a replay: under D-3 the pair of the field and `system.ble_link_quality` tells a gap from a repeat only in part; a gap raises `system.ble_link_quality` below 1.0 in the same condition.
- **EC-OP-12. WS10-T03 dispenser schema.** Quoted: "`event_schema` lists every payload key of a DISPENSE event with type and unit, and includes at least the interval since the previous open edge and the content change before and after". The conventions table of this document has one key `content_change` (after minus before, the proposed EC-GAP-1 field); a dispenser that reports the content before and after as two keys leaves the difference to the extractor, and the keys then need their own rows in the table; WS04-T07 test 8 ("`content_change` is 0 when content sensing is on") agrees with after minus before.
- **EC-OP-13. WS05-T07 test 34.** Quoted: "constructing it without any parameter listed in 'Parameters requested from the registry' of `evidence-channels.md` raises `RegistryError` (no default values)". The consumer column of the table says which names the extractor reads (`evidence_margin_ms`, `evidence_grace_ms`, `hr_coherence_max_age_ms`, `clock_skew_max_ms`); the floors and the tolerance are read by the rule of WS02-T04, and `dispense_bounce_interval_ms` is proposed and has no consumer until ADR-032 is confirmed, so the test should require the extractor names only.

## Traceability

Sources used: analisi §4.5 (the six evidence groups, the diagnosability matrix), §4.6 (row 15:00, a deliberate transition is not a crash), §4.8 (claim wording), §4.9 items 1, 2 and 5 (distributed architecture, time semantics, DISPENSE against INTAKE), §5.1 (injections and confounders), §5.6 (ablation A4); `docs/plan/02-interfaces.md#evidencevector`, `#ros-2-interfaces`, `#trace-schema`, `#signals`, `#time-and-units`, `#monitor`, `#verdict`; `docs/formal/01-signals-sampling.md` sections 2.5, 3.3, 3.4, 4.1 to 4.5 (CG-5, CG-6, CG-10, CG-11); `docs/formal/05-three-valued-semantics.md` sections 3.5 and 6.1 to 6.5; `docs/formal/02-templates.md` sections 3.1, 4.7, 5.2, 5.3; `docs/models/fault-model.md` (subtype vocabulary, fault-to-evidence table, conditions LC and SEQ, FM-GAP-*, OP-1 to OP-16); `docs/models/threat-model.md` (attack-to-evidence table, hypotheses H-*, TM-GAP-*, TM-OP-*). Review item: R1 weakness 7 (timestamps, clock skew, reordering and transport latency): the evidence-timing side is closed by the section Timing and evidence window and by decisions D-7 and D-9, together with the fault side of FM and the attack side of TM. Decisions: ADR-003 (ward node and robot, fallback to the nurse), ADR-004 (DISPENSE is not INTAKE), ADR-010 (hierarchical rule), ADR-017 (integer milliseconds), ADR-021 (contract-gap register, amendments decided at M1), ADR-025 (trace file layout: settings carry run information), ADR-026 (INT form: the witness statements use the reference form), and the new proposals ADR-032 to ADR-036.

| item | where |
|---|---|
| fields, adverse values, `None` conditions | Field semantics |
| derivation from the trace and ROS 2, payload keys | Derivation from the trace schema and ROS 2 |
| placements S1 to S6 | Availability per placement |
| ablation A4 | Ablation A4 mask |
| two clocks, reorder buffer, cut-off | Timing and evidence window |
| consumers | WS02-T04 (reading states, A4 mask, parameters, D-3, D-6), WS02-T05 (channel ids, gap list), WS04-T07 and WS04-T08 (payload keys, signatures), WS05-T07 (extractor, cut-off, derivation rows), WS07-T03 to WS07-T05 (robot evidence, node state), WS08-T04 (A4) |

Consequences for the earlier documents, listed once. FM: the rows of `ble_dropout` and `message_drop` list `system.ble_link_quality` as conditional on SEQ; the reading of `uncommanded_lifecycle_transition` and `process_kill` on a robot target as "becomes `None`" means that no new reading exists after the onset and that facts asserted earlier in the window stay; OP-2, OP-3, OP-14 and the MINOR on `seq` in arrival order are settled here (D-6, D-4, D-9); OP-4 is settled by D-2. TM: the provisional reading table of the section Attacker capabilities is superseded by the field table above for `crypto_temporal.timestamp_implausible` (not "not applicable") and for `witness.*` (coverage condition); the first MINOR of its review is EC-GAP-9; the second MINOR (`qos_deadline_missed` separates a replay from a loss when a deadline is declared) holds for the rule of EX-6: a loss longer than the deadline asserts the field, a single lost message does not (EX-6), and a replay that keeps the nominal arrival times leaves no arrival gap because the rule reads arrival times only. WS02-T04: the reading states, the A4 mask, the scope table and the aggregation rule are its inputs; its test 3 (explained-away rules) and its worked case W-15 (a gap explained by a link fault) use D-3.
