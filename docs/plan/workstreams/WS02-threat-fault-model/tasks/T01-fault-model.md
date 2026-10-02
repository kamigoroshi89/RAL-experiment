---
id: WS02-T01
title: Fault model for C2 (device, link, robot)
workstream: WS02-threat-fault-model
owner: agent
status: in_progress
depends_on: ["WS01-T01"]
critical_path: true
non_negotiable: false
estimate_pd: 1.5
sources: ["analisi §4.5", "analisi §5.1 (C2 injections)", "analisi §5.2", "analisi §4.9 (1, 2)", "analisi §4.6"]
interfaces: ["02-interfaces.md#evidencevector"]
review_items: ["R1-W7"]
---
## Obiettivo

Write `docs/models/fault-model.md`, the catalogue of C2 faults (system or embodiment failure) in three families: device (cuff, ECG and PPG path, dispenser), link (BLE, transport, time) and robot (navigation, manipulation, node, battery). For every fault the document gives its observable signature in trace-schema terms, the `EvidenceVector` fields it raises, the templates it can make violated, the cascades it seeds and the injection parameters (names only) that WS04-T07 and WS07-T05 will use. The document also fixes the fault hypothesis and the boundary between a fault, a clinical deviation (C1) and an integrity event (C3). It closes the fault side of R1 weakness 7: timestamps, clock skew, reordering and transport latency are modelled as link faults.

## Contesto

Blocked until WS01-T01 is done; its output fixes the signal list and the sampling semantics that this document must use.

- `docs/source/analisi.md` §4.5 (evidence groups, diagnosability matrix rows 3, 4, 5, 7), §4.6 (row 15:00: a deliberate lifecycle transition is not a crash) and §4.9 items 1 and 2.
- `docs/source/analisi.md` §5.1 (3) (C2 injections with onset, duration and magnitude) and §5.2 (fault injection in simulation).
- `docs/plan/02-interfaces.md#evidencevector` (20 fields; `None` means channel unavailable, never negative).
- `docs/plan/02-interfaces.md#trace-schema` (`Sample.seq`, `Sample.quality`, `EventKind`, event payload).
- `docs/plan/02-interfaces.md#time-and-units` (two clocks `t_device_ms` and `t_rx_ms`, reorder buffer with a declared maximum delay).

## File toccati

- `docs/models/fault-model.md` (create; create the directory `docs/models/` if it does not exist).

## Test

Document task: verification checks a reviewer can run or inspect.

1. Required H2 headings, in this order: `## Scope and fault hypothesis`, `## Subtype vocabulary`, `## Device faults`, `## Link and time faults`, `## Robot faults`, `## Fault effects on templates and cascade seeds`, `## Fault-to-evidence table`, `## Injection parameter sheet`, `## Non-faults and boundaries`, `## Traceability`. Check: `grep -n '^## ' docs/models/fault-model.md`.
2. `## Subtype vocabulary` lists one identifier per line as `- <id>` and contains at least these starting identifiers (an identifier may be renamed only with a recorded reason, because WS04-T07, WS02-T05 and WS07-T05 reuse them verbatim). From the sources: `ble_dropout`, `stuck_at`, `cuff_silent_bias`, `ecg_noise`, `nav_delay`, `manipulation_failure`, `dispenser_bounce`, `cuff_detached`, `process_kill`, `message_drop`, `localisation_noise`, `impossible_goal`. Added by this task from R1 weakness 7 and R3 weakness 2 (marked inferred in the catalogue): `link_delay`, `out_of_order`, `clock_skew`, `battery_depleted`, `uncommanded_lifecycle_transition`.
3. Every catalogue entry (tables under the three family headings) has these columns: id, mechanism, observable signature in trace-schema terms (which `Sample.signal`, `Sample.quality`, `Sample.seq`, `t_device_ms` versus `t_rx_ms`, `EventKind` and payload keys change), `EvidenceVector` paths raised, evident or silent, templates that may become violated (`TemplateId` values), cascade seeds, analisi matrix row number or "none", basis (`source` or `inferred`).
4. Every evidence path in the file is one of the 20 contract fields, written `group.field`: `grep -ohE '\b(provenance|system|signal_quality|cross_device|witness|crypto_temporal)\.[a-z_]+' docs/models/fault-model.md | sort -u | grep -vxE 'provenance\.(violated_template|template_kind)|system\.(node_lifecycle|diagnostics_ok|liveliness_ok|qos_deadline_missed|ble_link_quality|battery_low|nav_task_failed|manip_task_failed)|signal_quality\.(ecg_sqi|ppg_sqi|cuff_error_code)|cross_device\.pulse_vs_ecg_hr_diff|witness\.(robot_present|identity_confirmed|intake_observed)|crypto_temporal\.(authenticated|seq_gap_or_replay|timestamp_implausible)'` prints nothing. Evidence that has no field (for example dispenser content sensing, which the analisi rows 6 and 7 use) is written in words as "no EvidenceVector field yet" and listed for WS02-T03.
5. The fault hypothesis section states, in separate sentences: what a unit of failure is (device node, link, robot node), the duration classes used (transient, intermittent, persistent), whether faults may overlap in time (the same assumption WS04-T07 will inject), and that a fault is not itself a violation of the care plan (glossary: alert, violation, attributed cause).
6. The link and time section states, per fault, its effect on `t_device_ms`, `t_rx_ms` and `seq`, and which faults the reorder buffer can absorb (delay and reordering within its declared bound) and which it cannot (loss, delay beyond the bound, skew beyond the bound). Monitor behaviour on late samples is deferred to WS05-T04, not defined here.
7. `## Non-faults and boundaries` contains: a deliberate lifecycle transition is not a crash (detection uses liveliness and heartbeat, `02-interfaces.md#ros-2-interfaces`); a patient who refuses or delays a measurement is C1; message-level integrity attacks belong to WS02-T02.
8. No invented numbers: `grep -nE '[0-9]+ ?(mmHg|ms|min|bpm)' docs/models/fault-model.md | grep -v 'illustrative, unverified'` prints nothing; the analisi example "interval below one second" for a dispenser bounce, if quoted, is labelled "illustrative, unverified".
9. `## Injection parameter sheet` lists for each injected fault the parameters onset, duration and magnitude by name and unit type (ms or dimensionless) and states where WS04-T07 takes the value: from the `DeviceErrorModel` fields of `02-interfaces.md#priorsource` (`cuff_bias_mmhg` for `cuff_silent_bias`, `dispenser_bounce_prob` for `dispenser_bounce`, `ble_dropout_rate_per_h` for `ble_dropout`) or from the ROS 2 simulation (robot arrival jitter, analisi §5.1 (2)). No value is given.

## Passi

1. Create `docs/models/` if absent. Read the Contesto sources and the WS01-T01 output; note the signal identifiers (`SignalId` values) you will reference.
2. Write `## Scope and fault hypothesis`: define C2 as a cause-based class (analisi §4.8: "cause-based taxonomy over violations of φ_CP ∧ φ_SYS ∧ φ_INT"); state the fault hypothesis (unit of failure, duration classes, overlap assumption, causal chain fault to violation to cascade). State that the class boundary follows ADR-002: patient behaviour is C1, attacks are C3.
3. Write `## Device faults`: `cuff_detached` (evident; analisi row 3: error code, abnormal inflation duration, node state change), `cuff_silent_bias` and `stuck_at` (silent; analisi matrix row 4 and §4.8: plausible values remain indistinguishable from clinical deviations, injected on purpose to measure the limit honestly), `ecg_noise` (evident through signal quality; noise from the MIT-BIH Noise Stress Test Database on the ECG, analisi §5.1), `dispenser_bounce` (row 7). For each, fill the columns of check 3.
4. Write `## Link and time faults`: `ble_dropout` (with node transition), `message_drop` (tc netem style drop, analisi §5.2), then the time faults from R1 weakness 7 and §4.9 item 2: `link_delay`, `out_of_order`, `clock_skew`. Describe each on the two clocks and on `seq`. Note that time is also an attack vector (replay): the C3 side is in WS02-T02, the boundary is by cause, not by symptom.
5. Write `## Robot faults`: `nav_delay`, `impossible_goal`, `localisation_noise`, `manipulation_failure`, `process_kill`, `uncommanded_lifecycle_transition`, `battery_depleted` (R3 weakness 2: the robot fails or runs out of charge; ADR-003 fallback to the nurse). Mark which of them makes the robot unavailable as a witness (witness fields become `None`, see WS02-T03).
6. Write `## Fault effects on templates and cascade seeds`: table fault, `TemplateId` values that may become violated (`sched`, `count`, `resp`, `hold`, `sys`, `range`), and the downstream violations it seeds (missed measurement leads to a measurement-count violation at day end and to an unverifiable response; analisi §4.9 item 3 and §4.6 row 15:00). Do not define propagation rules; WS02-T04 does.
7. Write `## Fault-to-evidence table` (fault versus the evidence paths it raises, one row per fault) and `## Injection parameter sheet` (check 9).
8. Write `## Non-faults and boundaries` (check 7) and `## Traceability` (analisi sections used per entry, review item R1-W7, the analisi matrix rows covered).
9. Run every command of `## Test` and fix until each prints what it should.

## Done when

All of the following, from the repository root:

- `test -f docs/models/fault-model.md`
- `grep -c '^## ' docs/models/fault-model.md` prints at least 10, and the ten headings of check 1 are present.
- `sed -n '/^## Subtype vocabulary/,/^## D/p' docs/models/fault-model.md | grep -c '^- '` prints at least 17.
- The evidence-path check of Test item 4 prints nothing.
- `grep -nE 'T[O]DO|T[B]D|[?]{3}|lore[m]' docs/models/fault-model.md` prints nothing.
- `grep -nE '[0-9]+ ?(mmHg|ms|min|bpm)' docs/models/fault-model.md | grep -v 'illustrative, unverified'` prints nothing.
