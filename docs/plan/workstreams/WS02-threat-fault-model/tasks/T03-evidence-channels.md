---
id: WS02-T03
title: Evidence channels and EvidenceVector semantics, availability per placement
workstream: WS02-threat-fault-model
owner: agent
status: done
depends_on: ["WS02-T01", "WS02-T02"]
critical_path: true
non_negotiable: false
estimate_pd: 1.5
sources: ["analisi §4.5", "analisi §4.9 (1, 2, 5)", "analisi §5.6 (A4)", "analisi §4.6", "analisi §5.1"]
interfaces: ["02-interfaces.md#evidencevector"]
review_items: ["R1-W7"]
---
## Obiettivo

Write `docs/models/evidence-channels.md`: for each of the 20 fields of the `EvidenceVector` contract it fixes what the value means (which value is adverse), who produces it, how it is derived from the trace schema and from ROS 2, when it is `None`, and under which placement it exists (ward node, robot co-located, robot away, robot down). It defines channel identifiers (`CH-*`) used later by the diagnosability file, the exact mask applied by ablation A4, the evidence timing rules (two clocks, reorder buffer, cut-off), and the list of contract gaps with ADR proposals. The output is the single reference that WS04 (injectors), WS05-T07 (attribution package), WS07 (robot evidence) and WS08-T04 (A4) read. It closes the evidence-timing side of R1 weakness 7.

## Contesto

Blocked until WS02-T01 and WS02-T02 are done; read `docs/models/fault-model.md` and `docs/models/threat-model.md` first (their subtype vocabularies and evidence tables are the inputs of this task).

- `docs/source/analisi.md` §4.5 (six evidence groups, matrix), §4.9 items 1, 2 and 5 (distributed architecture, time semantics, DISPENSE versus INTAKE) and §5.6 (A4).
- `docs/plan/02-interfaces.md#evidencevector` (contract, version 0.1.0; rule: `None` is never converted to a negative observation).
- `docs/plan/02-interfaces.md#ros-2-interfaces` (topics `/ralmon/robot_evidence`, `/ralmon/heartbeat`; liveliness and deadline QoS; ward node versus robot placement).
- `docs/plan/02-interfaces.md#trace-schema` (`Sample`, `Event`, `EventKind`; the `#signals` rule that `PRESENCE` and `INTAKE` exist only while the robot is co-located).
- `docs/plan/03-decisions.md` ADR-003 (ward node plus robot, fallback to the nurse) and ADR-004 (DISPENSE is distinct from INTAKE).

## File toccati

- `docs/models/evidence-channels.md` (create).
- `docs/plan/03-decisions.md` (modify: append ADR proposals for the contract gaps of check 10; do not edit `docs/plan/02-interfaces.md`).

## Test

Document task: verification checks a reviewer can run or inspect.

1. Required H2 headings, in this order: `## Conventions`, `## Channel identifiers`, `## Field semantics`, `## Derivation from the trace schema and ROS 2`, `## Availability per placement`, `## Ablation A4 mask`, `## Timing and evidence window`, `## Parameters requested from the registry`, `## Decisions`, `## Contract gaps and change proposals`, `## Traceability`.
2. All 20 contract fields are documented, each written in backticks as `group.field` (loop in Done when prints nothing).
3. `## Field semantics` has, per field: type, adverse value (which of True, False, a string or a threshold crossing asserts a problem), polarity, producer and placement, channel id, condition under which the field is `None`, robot-derived (yes, no or partial).
4. `## Conventions` defines: canonical path names `group.field` (used in `Explanation.evidence_used` and in configs); the three reading states of a field, asserted, denied and unavailable (`None`), with the sentence that `None` is never converted to a negative observation; how "denied" is represented for non-boolean fields (for example a cuff error code that means "the device reports codes and none is present" needs a non-`None` value, and a float field is compared with a registry threshold); the definition of on-path (on the path from sample to alert, subject to latency bounds) and off-path (the back-end, not required to produce an alert), stated once and reused.
5. `## Channel identifiers` defines at least `CH-PROV`, `CH-SYS-WARD`, `CH-SYS-ROBOT`, `CH-SQI`, `CH-XDEV`, `CH-WIT`, `CH-CRYPTO`, each with producer, placement and the fields it feeds. WS02-T05 reuses these identifiers verbatim, so a rename needs a recorded reason.
6. `## Derivation from the trace schema and ROS 2` covers all 20 fields with the trace source (`Sample.signal`, `Sample.quality`, `Sample.seq`, `Event.kind`, payload key) and the ROS 2 source (topic, QoS event, diagnostics). Every payload key the derivation needs is listed once in a "trace evidence conventions" table (event kind, key, type, producer), because `#trace-schema` leaves `Event.payload` open.
7. `## Availability per placement` is a matrix of the 20 fields (or the six groups with per-field exceptions) against at least six situations: S1 ward node only; S2 robot co-located and healthy; S3 robot in the ward but not co-located; S4 robot unavailable (crash, depleted battery, lost heartbeat; ADR-003 fallback to the nurse); S5 device capability missing (no message authentication, no signal quality, no dispenser content sensing); S6 offline replay of a benchmark trace. Each cell is available, `None` or not applicable, with a reason.
8. `## Ablation A4 mask` lists field by field what happens when the embodied channel is removed: `None`, recomputed from ward-side sources only, or unchanged. It must agree with the contract rule: all `witness` fields and all robot-derived `system` fields become `None`; fields that aggregate ward and robot sources are recomputed from the ward-side sources and become `None` only if none remains. `provenance`, `signal_quality`, `cross_device` and `crypto_temporal` are unchanged. WS08-T04 applies this table without further interpretation.
9. `## Decisions` records each of D-1 to D-8 of the Passi with the chosen option and the reason.
10. `## Contract gaps and change proposals` lists each gap with id, description, affected analisi matrix rows, affected tasks and proposal, using at least G-1 to G-6 of the Passi. Proposed fields not in the contract are written in slash notation `group/name` so that the path check ignores them. For every gap that needs a contract change, an ADR with status `proposed` (and the confirmation tag defined at the top of `docs/plan/03-decisions.md`) is appended to that file with old version, new version, affected tasks and migration (`01-conventions.md` section 6). The file `docs/plan/02-interfaces.md` is unchanged: `grep -c '^Version 0.1.0. Owner WS02' docs/plan/02-interfaces.md` still prints 2.
11. Every dotted evidence path in the file is a contract field: `grep -ohE '\b(provenance|system|signal_quality|cross_device|witness|crypto_temporal)\.[a-z_]+' docs/models/evidence-channels.md | sort -u | grep -vxE 'provenance\.(violated_template|template_kind)|system\.(node_lifecycle|diagnostics_ok|liveliness_ok|qos_deadline_missed|ble_link_quality|battery_low|nav_task_failed|manip_task_failed)|signal_quality\.(ecg_sqi|ppg_sqi|cuff_error_code)|cross_device\.pulse_vs_ecg_hr_diff|witness\.(robot_present|identity_confirmed|intake_observed)|crypto_temporal\.(authenticated|seq_gap_or_replay|timestamp_implausible)'` prints nothing.
12. `## Parameters requested from the registry` lists parameter names only (for example an evidence window, a heart-rate coherence tolerance, signal-quality floors, a link-quality floor, a clock plausibility bound, a bounce interval), each with unit type and the consumer; no value is given. Any number quoted from analisi is labelled "illustrative, unverified". The request goes to WS01-T03 (registry schema) and WS00-T07 (clinician review).

## Passi

1. Read the Contesto sources and the two model documents. Write the checks above into a scratch list (they are the acceptance test).
2. `## Conventions` and `## Channel identifiers` (checks 4 and 5). Start from: `CH-PROV` provenance; `CH-SYS-WARD` system health observed at the ward node (gateway link, ward-hosted nodes, diagnostics, heartbeat supervision of the robot); `CH-SYS-ROBOT` system health produced by the robot (robot lifecycle, navigation and manipulation outcomes, robot battery); `CH-SQI` signal quality and cuff error code; `CH-XDEV` cross-device coherence; `CH-WIT` embodied witness; `CH-CRYPTO` authentication, sequence numbers, timestamp plausibility. Add `CH-DISP` (dispenser content and dispense interval) only if gap G-1 is confirmed.
3. `## Field semantics` (check 3). Take the field list from `02-interfaces.md#evidencevector`. Use these starting readings and correct them where the sources say otherwise: adverse values are `qos_deadline_missed` true, `battery_low` true, `nav_task_failed` true, `manip_task_failed` true, `seq_gap_or_replay` true, `timestamp_implausible` true, `diagnostics_ok` false, `liveliness_ok` false, `authenticated` false; `witness` fields are informative in both directions (`intake_observed` false while the robot is co-located is different from `None`).
4. `## Derivation from the trace schema and ROS 2` (check 6). Starting mapping to verify: `provenance.*` from `VerdictRecord.template` and the template kind; `system.node_lifecycle` from `EventKind.NODE_STATE`; `system.liveliness_ok` and `system.qos_deadline_missed` from `/ralmon/heartbeat` and QoS events (offline: gaps in heartbeat events and in the arrival period of a stream); `system.ble_link_quality` from a gateway metric; `system.nav_task_failed` and `system.manip_task_failed` from `EventKind.ROBOT_TASK`; `signal_quality.ecg_sqi` from `Sample.quality` of `SignalId.HR_ECG`; `signal_quality.ppg_sqi` from the quality of the PPG-derived signal (`SignalId` has no PPG-specific member; `SPO2` is the candidate, record the choice); `signal_quality.cuff_error_code` from `EventKind.DEVICE_ERROR`; `cross_device.pulse_vs_ecg_hr_diff` from `SignalId.HR_PULSE` versus `SignalId.HR_ECG` at the same instant; `witness.robot_present` from `SignalId.PRESENCE`; `witness.intake_observed` from `SignalId.INTAKE`; `witness.identity_confirmed` from a witness outcome event (proposal: `EventKind.ROBOT_TASK` with a witness payload); `crypto_temporal.authenticated` from `SignalId.AUTH` and a gateway verification outcome; `crypto_temporal.seq_gap_or_replay` from `Sample.seq` and `Event.seq`; `crypto_temporal.timestamp_implausible` from `t_device_ms` versus `t_rx_ms` and non-monotonic device time. State that the offline trace is the only source in S6 and that the ROS 2 path must produce the same field values.
5. `## Availability per placement` and `## Ablation A4 mask` (checks 7 and 8). Starting expectations from ADR-003 and `#signals`: witness fields are `None` in S1, S3 and S4 (contract: `robot_present` is `None` if the robot was not co-located); robot-derived system fields are available in S2 and S3 while the robot is alive and `None` in S4, where the ward node instead asserts `system.liveliness_ok` false for the robot node; ward-side fields are unaffected by the robot; S5 makes the corresponding field `None`.
6. `## Timing and evidence window` (R1 weakness 7). Evidence is timestamped with `t_device_ms` after the reorder buffer (`#time-and-units` rule 3); evidence older or newer than the window of the violated instance is not used; evidence arriving after the cut-off is logged but does not change κ. Decide and record the cut-off (proposal: the definitive-verdict instant `decided_at_ms` plus the reorder delay) and its cost in attribution latency; time is also an attack vector, so `crypto_temporal.timestamp_implausible` must define its plausibility bound as a named parameter. Then write `## Parameters requested from the registry` (check 12): collect every threshold and window that the field semantics and timing rules name.
7. `## Decisions`, each recorded with option and reason: D-1 key of the `Mapping[str, EvidenceVector]` in `#attribution` and `#detector` (the contract does not state it; proposal `VerdictRecord.instance_key`); D-2 meaning of the single `system.battery_low` (device or robot battery; proposal: battery of the nodes that produce the signals of the violated template, robot part in the A4 mask); D-3 how a sequence gap (message loss, a C2 symptom) is separated from a replay (a C3 symptom) inside the single field `crypto_temporal.seq_gap_or_replay`, because under the hierarchy of ADR-010 integrity evidence wins and a link fault must not become C3; D-4 `system.node_lifecycle` value vocabulary and a "commanded" flag so that a deliberate transition is not evidence of failure (analisi §4.6, row 15:00); D-5 `system.nav_task_failed` (proposal: aborted, timed out or completed after the deadline induced by the schedule); D-6 the dependency among `witness.robot_present`, `witness.identity_confirmed` and `witness.intake_observed` (presence is not identity, R3 weakness 5) and which combination counts as INTAKE; D-7 the evidence cut-off; D-8 device capability declaration (a device that cannot authenticate or report quality yields `None`, declared in its device profile).
8. `## Contract gaps and change proposals`. Minimum list: G-1 no field carries dispenser content change or the interval between dispense events, although analisi matrix rows 6 and 7 and the confounder `double_take_vs_bounce` (§5.1 item 4) depend on them (proposal: extend `CrossDeviceEvidence` or add a group, `None` when the dispenser has no content sensing; affected tasks WS02-T04, WS02-T05, WS04-T05, WS04-T07, WS05-T07, WS07-T03, WS10-T03); G-2 the mapping key (D-1); G-3 the gap-versus-replay conflation (D-3), with the option to split the field; G-4 `Event.payload` keys and per-sample authentication status are not defined in `#trace-schema` (propose the conventions table, to be adopted by WS04-T01); G-5 the step that builds an `EvidenceVector` from an `ObservedDay` and a `VerdictRecord` has no owning task (propose WS05-T07; report to the plan lead); G-6 no field carries clock health, so a `clock_skew` fault cannot be told from `timestamp_manipulation` (accept as a declared limit for WS02-T05 or propose a field).
9. Append the ADR proposals for the gaps that need a contract change (at least G-1; G-2 and G-3 if the contract text or fields change). Use the next free ADR number at the time of the task. Do not bump `02-interfaces.md`.
10. `## Traceability`, then run every command of `## Test`.

## Done when

All of the following, from the repository root:

- `test -f docs/models/evidence-channels.md`
- `for f in provenance.violated_template provenance.template_kind system.node_lifecycle system.diagnostics_ok system.liveliness_ok system.qos_deadline_missed system.ble_link_quality system.battery_low system.nav_task_failed system.manip_task_failed signal_quality.ecg_sqi signal_quality.ppg_sqi signal_quality.cuff_error_code cross_device.pulse_vs_ecg_hr_diff witness.robot_present witness.identity_confirmed witness.intake_observed crypto_temporal.authenticated crypto_temporal.seq_gap_or_replay crypto_temporal.timestamp_implausible; do grep -q "\`$f\`" docs/models/evidence-channels.md || echo "missing $f"; done` prints nothing.
- `grep -c '^## ' docs/models/evidence-channels.md` prints at least 11, and the headings of check 1 are present.
- `grep -o 'CH-[A-Z-]*' docs/models/evidence-channels.md | sort -u | wc -l` prints at least 7.
- `grep -c '^## ADR-' docs/plan/03-decisions.md` prints at least 21 (the ADR proposals were appended), and `grep -c '^Version 0.1.0. Owner WS02' docs/plan/02-interfaces.md` prints 2 (the contract is unchanged at the time this task closes).
- The evidence-path check of Test item 11 prints nothing.
- `grep -nE 'T[O]DO|T[B]D|[?]{3}|lore[m]' docs/models/evidence-channels.md` prints nothing.

## Notes

### Flag from the WS02-T01 review (orchestrator, 2026-10-02)

Passi step 4 derives `timestamp_implausible` also from "non-monotonic device time"; `docs/models/fault-model.md` says `out_of_order` within the reorder bound raises no evidence (OP-14), and that `seq` is non-monotone in arrival order so `crypto_temporal.seq_gap_or_replay` needs the same decision (a MINOR of the review). Decide here. Kept `blocked`.



Written by the worker agent of WS02-T03. Status is left `in_progress` on purpose (the orchestrator sets `done` after review). The work is committed on branch `ws02-t03-evidence-channels`; nothing is merged and no other task file was changed. Files changed: `docs/models/evidence-channels.md` (created), `docs/plan/03-decisions.md` (ADR-032 to ADR-036 appended, no existing ADR edited), this task file (status and Notes). `docs/plan/02-interfaces.md` is unchanged.

### Verification (real commands, run from the repository root with `.venv` active)

Scripts are in `/tmp/ws02t03/` (not committed): `check_doc.py` (the twelve checks of `## Test`, the six `## Done when` commands, programmatic checks against the contract with its own parser of `02-interfaces.md`: 20 fields in 6 groups, `EventKind`, `SignalId`, `TemplateId`, topics, `Class.attr` names, numbers with units, glossary tokens, ADR structure, agreement of the availability matrix and of the A4 mask with the reference extractor), `ref.py` (the integer-millisecond reference extractor that implements the rules of the document), `test_golden.py`, `test_prior.py` (validation of the extractor on V-LATE-1, V-LATE-2 and on FX-3, FX-4, FX-12 of the fault model and TX-1, TX-5, TX-8 of the threat model), `int_check.py` (INT interval evaluator validated on V-INT-1 to V-INT-3 and G-INT-1 to G-INT-3, then 6000 random draws), `ex.py` (EX-1 to EX-6), `matrix.py` and `caps.py` (EX-7), `a4.py` (EX-8), `props.py` and `props2.py` (EX-10). Before the document existed `check_doc.py` failed (`FAIL DW1 test -f docs/models/evidence-channels.md`, exit 1); against an empty file it failed 136 of 171 checks.

Done-when commands (output and exit code):

```
$ test -f docs/models/evidence-channels.md

[exit 0]

$ for f in provenance.violated_template provenance.template_kind system.node_lifecycle system.diagnostics_ok system.liveliness_ok system.qos_deadline_missed system.ble_link_quality system.battery_low system.nav_task_failed system.manip_task_failed signal_quality.ecg_sqi signal_quality.ppg_sqi signal_quality.cuff_error_code cross_device.pulse_vs_ecg_hr_diff witness.robot_present witness.identity_confirmed witness.intake_observed crypto_temporal.authenticated crypto_temporal.seq_gap_or_replay crypto_temporal.timestamp_implausible; do grep -q "\`$f\`" docs/models/evidence-channels.md || echo "missing $f"; done

[exit 0]

$ grep -c '^## ' docs/models/evidence-channels.md
11
[exit 0]

$ grep '^## ' docs/models/evidence-channels.md
H2: Conventions
H2: Channel identifiers
H2: Field semantics
H2: Derivation from the trace schema and ROS 2
H2: Availability per placement
H2: Ablation A4 mask
H2: Timing and evidence window
H2: Parameters requested from the registry
H2: Decisions
H2: Contract gaps and change proposals
H2: Traceability
[exit 0]

$ grep -o 'CH-[A-Z-]*' docs/models/evidence-channels.md | sort -u | wc -l
8
[exit 0]

$ grep -c '^## ADR-' docs/plan/03-decisions.md
36
[exit 0]

$ grep -c '^Version 0.1.0. Owner WS02' docs/plan/02-interfaces.md
2
[exit 0]

$ grep -ohE '\b(provenance|system|signal_quality|cross_device|witness|crypto_temporal)\.[a-z_]+' docs/models/evidence-channels.md | sort -u | grep -vxE 'provenance\.(violated_template|template_kind)|system\.(node_lifecycle|diagnostics_ok|liveliness_ok|qos_deadline_missed|ble_link_quality|battery_low|nav_task_failed|manip_task_failed)|signal_quality\.(ecg_sqi|ppg_sqi|cuff_error_code)|cross_device\.pulse_vs_ecg_hr_diff|witness\.(robot_present|identity_confirmed|intake_observed)|crypto_temporal\.(authenticated|seq_gap_or_replay|timestamp_implausible)'

[exit 1]

$ grep -nE 'T[O]DO|T[B]D|[?]{3}|lore[m]' docs/models/evidence-channels.md

[exit 1]

$ git diff --stat master -- docs/plan/02-interfaces.md

[exit 0]

$ pytest -q 2>&1 | tail -2
...............................                                          [100%]
175 passed in 0.84s
[exit 0]

$ python3 tools/check_plan.py
check_plan: OK (103 tasks, 18 contracts, 31 findings)
[exit 0]

$ python /tmp/ws02t03/check_doc.py | tail -1
SUMMARY: 599 checks, 0 failed
[exit 0]
```

`python /tmp/ws02t03/check_doc.py`: `SUMMARY: 599 checks, 0 failed` (exit 0). Full suite: `pytest -q`: 175 passed (exit 0). `python3 tools/check_plan.py`: `check_plan: OK (103 tasks, 18 contracts, 31 findings)` (exit 0). The count `grep -c '^Version 0.1.0. Owner WS02' docs/plan/02-interfaces.md` is 2 on master before any change (checked first) and 2 after.

Outputs of the reference extractor checks:

```
== test_golden.py
PASS V-LATE-1 measurement classified late
PASS V-LATE-1 decided_at + D == emitted_at_monitor_ms == eval_at_ms
PASS V-LATE-1 watermark of the measurement after the cut-off
PASS V-LATE-2 measurement classified ok
PASS V-LATE-2 decided_at + D == emitted_at_monitor_ms == eval_at_ms
PASS V-LATE-2 watermark of the measurement not after the cut-off
PASS arrival exactly at the watermark is on time
PASS one ms later is late
PASS only V-LATE-1 and V-LATE-2 carry a t_rx different from t_device
FAILS 0

== test_prior.py
PASS FX-3 watermark 09:30:30
PASS FX-3 arrival 09:30:30 on time
PASS FX-3 arrival 09:30:31 late
PASS FX-3 delay D always on time, D+Ts always late (phase sweep)
PASS FX-4 (a) ahead 2 min, skew_max 180000: accepted
PASS FX-4 (b) skew_max 60000: future-stamped
PASS FX-4 (c) behind 2 min, D 30000: late
PASS FX-4 (d) behind 2 min, D 150000: accepted
PASS FX-12 both on time
PASS TX-1 stale-stamped replay is late (negative device time)
PASS TX-8 (c) relayed 09:30:40 is late
PASS TX-8 (d) arrival 09:30:30 on time
PASS TX-8 (a) stamp two steps later, skew 180000: accepted
PASS TX-8 (b) skew 60000: future
PASS TX-1 (c) loss: gap True, repeat False, ratio < 1
PASS TX-5 (a) verbatim copy: repeat True, no gap, ratio 1.0
PASS TX-5 (e) later genuine message repeats the inserted number: repeat True
FAILS 0

== int_check.py
PASS V-INT-1 [-inf, 300000] pending, marker channel_unavailable:presence | (-inf, 300000, 'pending', {'channel_unavailable:presence'})
PASS V-INT-2 [300000, 300000] satisfied | (300000, 300000, 'satisfied', {'channel_unavailable:presence'})
PASS V-INT-3 [-inf, -inf] violated | (-inf, -inf, 'violated', set())
PASS G-INT-1 sigma_raw 180000 satisfied | (180000, 180000, 'satisfied', set())
PASS G-INT-2 sigma_raw -180000 violated | (-180000, -180000, 'violated', set())
PASS G-INT-3 300000 satisfied (auth decides, robot channels unavailable) | (300000, 300000, 'satisfied', {'channel_unavailable:presence', 'channel_unavailable:intake'})
PASS I1 INT violated => robot_present False and intake_observed False or None (6000 draws) | {'I1': 0, 'I2': 0, 'I3': 0, 'I4': 0}
PASS I2 robot_present False, intake_observed False and no auth in the window => INT violated | ({'I1': 0, 'I2': 0, 'I3': 0, 'I4': 0}, {'violated': 602, 'satisfied': 2185, 'pending': 3213, 'mark_unavail': 3757, 'mark_undef': 556, 'I2_pre': 498})
PASS I3 INT pending with a channel_unavailable marker => neither witness field is False | ({'I1': 0, 'I2': 0, 'I3': 0, 'I4': 0}, {'violated': 602, 'satisfied': 2185, 'pending': 3213, 'mark_unavail': 3757, 'mark_undef': 556, 'I2_pre': 498})
PASS I4 INT pending with value_undefined:presence => robot_present is not False | ({'I1': 0, 'I2': 0, 'I3': 0, 'I4': 0}, {'violated': 602, 'satisfied': 2185, 'pending': 3213, 'mark_unavail': 3757, 'mark_undef': 556, 'I2_pre': 498})
counts {'violated': 602, 'satisfied': 2185, 'pending': 3213, 'mark_unavail': 3757, 'mark_undef': 556, 'I2_pre': 498} bad {'I1': 0, 'I2': 0, 'I3': 0, 'I4': 0}
FAILS 0

== props.py
PASS P1 reorder within the bound: no repeat, no gap, ratio 1.0, nothing late (4000 draws, any cut-off C) bad=0; draws whose arrival order has non-monotone seq: 682
PASS P2 on-time input with t_dev <= decided_at has t_rx <= decided_at + D (20000 draws) bad=0
PASS P3 appending inputs received after the cut-off changes no field (300 draws) bad=0
FAILS 0

== props2.py
PASS D-3: ratio below one implies the field is True (5000 draws) | {'ratio1_implies_no_gap_and_repeat_if_true': 0, 'ratio_lt1_implies_gap': 0, 'true_with_ratio1_has_repeat': 0}
PASS D-3: field True with ratio exactly one implies a repeat was injected (5000 draws) | ({'ratio1_implies_no_gap_and_repeat_if_true': 0, 'ratio_lt1_implies_gap': 0, 'true_with_ratio1_has_repeat': 0}, 586, 1763, 625, 1028)
counts repeat-only 586 gap(+/-repeat) 1763 True with ratio None 625 False 1028
FAILS 0

== ex.py (EX-1 to EX-6)
PASS EX-1 a in order | (False, False, 1.0, False)
PASS EX-1 b seq 2 before seq 1 | (False, False, 1.0, False)
PASS EX-1 c seq 2 lost | (False, True, 0.75, False)
PASS EX-1 d seq 2 after its watermark | (False, False, 1.0, True)
PASS EX-1 e seq 2 after the cut-off | (False, True, 0.75, False)
PASS EX-1 f copy of seq 2 | (True, False, 1.0, False)
PASS EX-1 g seq 2 lost, copy of seq 3 | (True, True, 0.75, False)
PASS EX-1 (h) frames 9 (bp + measurement), 10 (missed-measurement event only), 11: no repeat, no gap, ratio 1.0 | (False, False, 1.0)
PASS EX-1 (h) the same stream read per signal (bp only: 9, 11) would show a false gap | (False, True, 0.6666666666666666)
PASS EX-1 (i) frame 10 lost: gap True, ratio 2/3 | (False, True, 0.6666666666666666)
PASS EX-1 (j) verbatim copy of the bp Sample of frame 9: repeat True (the members of a frame are not repeats of each other) | (True, False, 1.0)
PASS EX-1 (k) stale-stamped replay of the previous day's bp seq 21, retained state: repeat True, no gap, the copy is late | (True, False, 1.0)
PASS EX-2 (a) only the late message, G 0: timestamp None (no message of the cuff in the window) | (None, None, 34230000)
PASS EX-2 (a) G 10000: timestamp True | (True, False, 34240000)
PASS EX-2 (a) G 9999: still None (one ms short of the arrival)
PASS EX-2 (b) earlier on-time message too, G 0: timestamp False although a late input exists | (False, False, 34230000)
PASS EX-2 (b) G 10000: True
PASS EX-2 (b) seq: no gap at G 0 or G 10000 (late input is received, so its number is present)
PASS EX-2 (c) the input never arrives: timestamp False, seq False (no later message reveals a gap)
PASS EX-3 cuff error code: no code, cuff messages in window -> empty string (denied)
PASS EX-3 cuff error code present -> the code (asserted)
PASS EX-3 cuff silent in the window -> None (unavailable, not denied)
PASS EX-3 device that reports no codes -> None
PASS EX-3 pulse 90 against ECG 72 -> float difference 18.0
PASS EX-3 (f) cuff silent in the window, instance sched: seq, timestamp, authenticated and ble_link_quality are None | {'crypto_temporal.seq_gap_or_replay': None, 'crypto_temporal.timestamp_implausible': None, 'crypto_temporal.authenticated': None, 'system.ble_link_quality': None}
PASS EX-3 (f) cuff silent in the window, instance hold: seq, timestamp, authenticated and ble_link_quality are None | {'crypto_temporal.seq_gap_or_replay': None, 'crypto_temporal.timestamp_implausible': None, 'crypto_temporal.authenticated': None, 'system.ble_link_quality': None}
PASS EX-3 (f) cuff silent in the window, instance resp: seq, timestamp, authenticated and ble_link_quality are None | {'crypto_temporal.seq_gap_or_replay': None, 'crypto_temporal.timestamp_implausible': None, 'crypto_temporal.authenticated': None, 'system.ble_link_quality': None}
PASS EX-4 nominal: cuff active
PASS EX-4 uncommanded deactivation inside the window: 'inactive', liveliness stays True
PASS EX-4 commanded deactivation: 'inactive+commanded'
PASS EX-4 state in force from before the window is carried in
PASS EX-4 deactivated and reactivated inside the window: the adverse state is kept
PASS EX-4 reactivated before the window: 'active'
PASS EX-4 liveliness lapse: 'unreachable' and liveliness False
PASS EX-4 BLE link loss before the lease lapses: 'link_down', liveliness True
PASS EX-5 (a) co-located from 20:50, presence 1 at 20:50 and 0 at 20:58: (True, False)
PASS EX-5 (b) co-located, presence 0 held: (False, False)
PASS EX-5 (c) an INTAKE event at 20:58, presence 0: (False, True)
PASS EX-5 (d) the robot arrives at 20:58 and sees the patient: robot_present True, intake None (coverage broken) | (True, None, None)
PASS EX-5 (e) the robot goes unreachable at 20:57 after presence 1 and 0 afterwards: (True, None)
PASS EX-5 (f) the robot goes unreachable at 20:57 with presence 0 only: (None, None)
PASS EX-5 (g) co-located, no presence sample at all: robot_present None (level undefined), intake False
PASS EX-5 (h) never co-located (default): (None, None)
PASS EX-5 (i) failed manipulation in the window, robot in the room, presence 1: (True, None)
PASS EX-5 (j) the same with an INTAKE event: (True, True)
PASS EX-5 (k) identity check failed with presence 1: identity_confirmed False
PASS EX-5 (l) identity check reported but presence 0 (robot_present False): identity_confirmed None
PASS EX-6 (a) nominal arrivals every 300000, deadline 600000: not missed
PASS EX-6 (b) one message lost (gap 600000, equal to the deadline): not missed
PASS EX-6 (c) three consecutive messages lost (gap 1200000): missed
FAILS 0

== matrix.py (EX-7, placements S1 to S6, reference profile)
field                                   S1     S2     S3     S4     S5     S6    
system.node_lifecycle                   avail  avail  avail  avail  avail  avail 
system.diagnostics_ok                   avail  avail  avail  None   None   None  
system.liveliness_ok                    avail  avail  avail  avail  avail  avail 
system.qos_deadline_missed              avail  avail  avail  avail  avail  None  
system.ble_link_quality                 avail  avail  avail  avail  None   avail 
system.battery_low                      None   avail  avail  None   None   None  
system.nav_task_failed                  None   avail  avail  None   avail  avail 
system.manip_task_failed                None   avail  avail  None   None   avail 
signal_quality.ecg_sqi                  avail  avail  avail  avail  None   avail 
signal_quality.ppg_sqi                  avail  avail  avail  avail  None   avail 
signal_quality.cuff_error_code          avail  avail  avail  avail  None   avail 
cross_device.pulse_vs_ecg_hr_diff       avail  avail  avail  avail  avail  avail 
witness.robot_present                   None   avail  None   None   avail  avail 
witness.identity_confirmed              None   avail  None   None   None   avail 
witness.intake_observed                 None   avail  None   None   avail  avail 
crypto_temporal.authenticated           avail  avail  avail  avail  None   avail 
crypto_temporal.seq_gap_or_replay       avail  avail  avail  avail  None   avail 
crypto_temporal.timestamp_implausible   avail  avail  avail  avail  avail  None  

== caps.py (EX-7, S5 per capability)
PASS baseline: every one of the 18 non-provenance fields is non-None in the fully capable healthy case
PASS S5 without authenticates: None set is exactly ['crypto_temporal.authenticated'] | ['crypto_temporal.authenticated']
PASS S5 without seq: None set is exactly ['crypto_temporal.seq_gap_or_replay', 'system.ble_link_quality'] | ['crypto_temporal.seq_gap_or_replay', 'system.ble_link_quality']
PASS S5 without two_clocks: None set is exactly ['crypto_temporal.timestamp_implausible'] | ['crypto_temporal.timestamp_implausible']
PASS S5 without ecg quality: None set is exactly ['signal_quality.ecg_sqi'] | ['signal_quality.ecg_sqi']
PASS S5 without spo2 quality: None set is exactly ['signal_quality.ppg_sqi'] | ['signal_quality.ppg_sqi']
PASS S5 without error_codes: None set is exactly ['signal_quality.cuff_error_code'] | ['signal_quality.cuff_error_code']
PASS S5 without diagnostics: None set is exactly ['system.diagnostics_ok'] | ['system.diagnostics_ok']
PASS S5 without supervised: None set is exactly ['system.liveliness_ok'] | ['system.liveliness_ok']
PASS S5 without lifecycle: None set is exactly ['system.battery_low', 'system.diagnostics_ok', 'system.liveliness_ok', 'system.node_lifecycle'] | ['system.battery_low', 'system.diagnostics_ok', 'system.liveliness_ok', 'system.node_lifecycle']
PASS S5 without deadline: None set is exactly ['system.qos_deadline_missed'] | ['system.qos_deadline_missed']
PASS S5 without battery: None set is exactly ['system.battery_low'] | ['system.battery_low']
PASS S5 without nav: None set is exactly ['system.nav_task_failed'] | ['system.nav_task_failed']
PASS S5 without manip: None set is exactly ['system.manip_task_failed'] | ['system.manip_task_failed']
PASS S5 without identity_check: None set is exactly ['witness.identity_confirmed'] | ['witness.identity_confirmed']
PASS S5 without no pulse stream: None set is exactly ['cross_device.pulse_vs_ecg_hr_diff'] | ['cross_device.pulse_vs_ecg_hr_diff']
PASS S5 without no ecg stream: None set is exactly ['cross_device.pulse_vs_ecg_hr_diff', 'signal_quality.ecg_sqi'] | ['cross_device.pulse_vs_ecg_hr_diff', 'signal_quality.ecg_sqi']
PASS S5 without no perception: None set is exactly ['witness.identity_confirmed', 'witness.intake_observed', 'witness.robot_present'] | ['witness.identity_confirmed', 'witness.intake_observed', 'witness.robot_present']
FAILS 0

== a4.py (EX-8)
PASS partition: 6 + 4 + 10 (18 non-provenance fields counted without provenance) = 20 fields with provenance
PASS UNCHANGED lists 8 evidence fields here (+2 provenance fields = 10) | ['system.ble_link_quality', 'signal_quality.ecg_sqi', 'signal_quality.ppg_sqi', 'signal_quality.cuff_error_code', 'cross_device.pulse_vs_ecg_hr_diff', 'crypto_temporal.authenticated', 'crypto_temporal.seq_gap_or_replay', 'crypto_temporal.timestamp_implausible']
PASS A4 S2/sched: None class is None, unchanged class equal
PASS A4 S2/hold: None class is None, unchanged class equal
PASS A4 S2/resp: None class is None, unchanged class equal
PASS A4 S2/int: None class is None, unchanged class equal
PASS A4 S3/sched: None class is None, unchanged class equal
PASS A4 S3/hold: None class is None, unchanged class equal
PASS A4 S3/resp: None class is None, unchanged class equal
PASS A4 S3/int: None class is None, unchanged class equal
PASS A4 S4/sched: None class is None, unchanged class equal
PASS A4 S4/hold: None class is None, unchanged class equal
PASS A4 S4/resp: None class is None, unchanged class equal
PASS A4 S4/int: None class is None, unchanged class equal
PASS A4(S2)/sched equals the run without the robot (S1), all 18 evidence fields
PASS A4(S2)/hold equals the run without the robot (S1), all 18 evidence fields
PASS A4(S2)/resp equals the run without the robot (S1), all 18 evidence fields
PASS A4(S2)/int equals the run without the robot (S1), all 18 evidence fields
PASS A4(S3)/sched equals the run without the robot (S1), all 18 evidence fields
PASS A4(S3)/hold equals the run without the robot (S1), all 18 evidence fields
PASS A4(S3)/resp equals the run without the robot (S1), all 18 evidence fields
PASS A4(S3)/int equals the run without the robot (S1), all 18 evidence fields
PASS A4(S4)/sched equals the run without the robot (S1), all 18 evidence fields
PASS A4(S4)/hold equals the run without the robot (S1), all 18 evidence fields
PASS A4(S4)/resp equals the run without the robot (S1), all 18 evidence fields
PASS A4(S4)/int equals the run without the robot (S1), all 18 evidence fields
S2 pure-mask versus source-exclusion, recompute class: {'system.node_lifecycle': ({'cuff': 'active', 'dispenser': 'active', 'robot': 'active'}, {'cuff': 'active', 'dispenser': 'active'})}
S4 pure-mask versus source-exclusion, recompute class: {'system.node_lifecycle': ({'cuff': 'active', 'dispenser': 'active', 'robot': 'unreachable'}, {'cuff': 'active', 'dispenser': 'active'}), 'system.liveliness_ok': (False, True), 'system.diagnostics_ok': (None, True)}
PASS S4: pure mask leaves liveliness_ok False (robot unreachable), source exclusion gives True
PASS S4: node_lifecycle loses the robot key under exclusion
PASS int under A4: node_lifecycle has only the dispenser
PASS sched under A4 with a cuff that reports no lifecycle: node_lifecycle, liveliness_ok, qos, diagnostics all None | {'system.node_lifecycle': None, 'system.liveliness_ok': None, 'system.qos_deadline_missed': None, 'system.diagnostics_ok': None}
FAILS 0
```

### Deviations from the task text (kept minimal)

1. **Channel split by subject node (D-11).** The task text starts `CH-SYS-WARD` with "heartbeat supervision of the robot". The document assigns the heartbeat supervision of the robot to `CH-SYS-ROBOT` (by subject), so that ablation A4 removes the robot lifecycle that analisi §5.6 names; the ward-hosted nodes of the task text are not listed because the ward node is the trusted base (FM hypothesis 6). WS02-T05 states A4 as `CH-WIT` and `CH-SYS-ROBOT` unavailable, which holds. If the plan lead prefers the task text, the only A4 rows that change are the robot components of `system.liveliness_ok`, `system.qos_deadline_missed` and `system.node_lifecycle`.
2. **D-2 chosen option.** `system.battery_low` is the robot battery only (not the battery of the nodes of the template), so that the field is wholly robot-derived and the A4 mask stays a path set for it.
3. **Step 4 of the task text** derives `timestamp_implausible` also from non-monotonic device time; the decision of the flag (D-9) does not use it, with reasons and consequences in the document.
4. **More than the minimum.** Decisions D-9 to D-14 beyond D-1 to D-8; gaps `EC-GAP-1` to `EC-GAP-12` (G-1 to G-6 of the task are `EC-GAP-1` to `EC-GAP-6`); consumer check `EC-OP-1` to `EC-OP-13`; worked checks EX-1 to EX-10 inside the sections; five ADR proposals (the task required at least G-1). The H2 headings are exactly the eleven required; everything else is H3.
5. **`CH-DISP`** is listed as proposed, not defined as a feeding channel: the task says to add it only if G-1 is confirmed, but WS02-T05 needs the identifier for the rows of the double take and the bounce; it feeds no field.
6. **A4 has three classes** (None, recompute, unchanged), because the contract rule has the third one; `EMBODIED_MASK_ALL` is the class None (six paths) and the class recompute cannot be a path mask (EC-OP-5).
7. **Availability matrix, column S6** is shown for a stated reference profile (no transport-delay model, no diagnostics, no battery, no declared deadline), because S6 depends on what the generator emits. The column `S5` printed by `matrix.py` above is a combined profile that is not compared with the document; the document's S5 column is the per-capability result of `caps.py`.
8. The ADR index line at the top of `docs/plan/03-decisions.md` (it stops at ADR-023) is not edited, since existing text is not to be changed.

### Contract gaps found (not changed) and ADRs proposed

`EC-GAP-1` (G-1) dispenser content change and dispense interval, ADR-032 "EvidenceVector: a dispenser evidence group (content change and dispense interval)"; `EC-GAP-2` (G-2) key of the mapping, scope of the scalar `system` fields, meaning of `battery_low` and `robot_present`, ADR-033 "EvidenceVector: key of the evidence mapping, scope of the scalar system fields, meaning of `battery_low` and `robot_present`"; `EC-GAP-3` (G-3) gap against replay in `seq_gap_or_replay`, ADR-034 "EvidenceVector: split of `crypto_temporal.seq_gap_or_replay`"; `EC-GAP-4` (G-4) payload keys and per-message verification outcome, `EC-GAP-9` forged `auth` Sample (hypothesis, not assumed), `EC-GAP-10` availability of the robot channels not in the trace, all three in ADR-035 "Trace schema: evidence conventions for `Event.payload`, the gateway verification outcome, `auth` Samples and the availability of the robot channels"; `EC-GAP-8` device capability profile, ADR-036 "Device capability profile". No ADR for `EC-GAP-5` (G-5: the owner is WS05-T07, which already owns `EvidenceExtractor` and `extract_evidence`; report to the plan lead), `EC-GAP-6` (G-6: clock health accepted as a declared limit), `EC-GAP-7` (device battery has no field), `EC-GAP-11` (name `robot_present`), `EC-GAP-12` (PPG heart rate has no `SignalId`). Every ADR carries context, decision with old version, new version, affected tasks and migration, alternatives, consequences, status `proposed [DA-CONFERMARE]`, says that amendments are decided at M1 (ADR-021) and that ADR-026 to ADR-031 are not touched. The contract is not edited and not bumped.

### Summary of the field table, A4 mask and the out-of-order decision

Robot-derived: yes for `witness.robot_present`, `witness.identity_confirmed`, `witness.intake_observed`, `system.battery_low`, `system.nav_task_failed`, `system.manip_task_failed`; partial for `system.node_lifecycle`, `system.diagnostics_ok`, `system.liveliness_ok`, `system.qos_deadline_missed`; no for the other ten. Adverse values: True for `system.qos_deadline_missed`, `system.battery_low`, `system.nav_task_failed`, `system.manip_task_failed`, `crypto_temporal.seq_gap_or_replay`, `crypto_temporal.timestamp_implausible`; False for `system.diagnostics_ok`, `system.liveliness_ok`, `witness.identity_confirmed`, `crypto_temporal.authenticated`; low for `system.ble_link_quality`, `signal_quality.ecg_sqi`, `signal_quality.ppg_sqi`; high for `cross_device.pulse_vs_ecg_hr_diff`; non-empty for `signal_quality.cuff_error_code`; an entry other than `active` or `<state>+commanded` for `system.node_lifecycle`; informative in both directions for `witness.robot_present` and `witness.intake_observed`.

A4 mask: class None (six): the three `witness` fields, `system.nav_task_failed`, `system.manip_task_failed`, `system.battery_low`; class recompute (four): `system.node_lifecycle`, `system.diagnostics_ok`, `system.liveliness_ok`, `system.qos_deadline_missed` (robot component removed, `None` only if no device node of the scope remains); class unchanged (ten): both `provenance` fields, `system.ble_link_quality`, the three `signal_quality` fields, `cross_device.pulse_vs_ecg_hr_diff`, the three `crypto_temporal` fields. A4 does not mask `crypto_temporal` or `cross_device` (their scope is the BLE device streams, D-12). A path mask alone realises only the class None, a partial A4.

Decision on out-of-order input (D-9): within the bound neither `crypto_temporal.timestamp_implausible` nor `crypto_temporal.seq_gap_or_replay` is raised; the first reads only the late and future-stamped classification, the second is computed on sets of `(name, seq)` and on the sequence values of the device, not on arrival order. Reason: the reorder buffer restores device-time order within the bound, and an arrival-order rule would flag benign reordering (about one draw in six of the random draws has a non-monotone `seq` in arrival order); checked by EX-1 and by P1 (4000 draws, no false gap for any cut-off). Conditions: consecutive device sequence values (H-SEQT), delays within the bound, a cut-off not before the watermark of the messages it certifies. Consequences: FM `out_of_order` row and OP-14 resolved as FM states (and its MINOR on `seq`); FM rows of `ble_dropout` and `message_drop` must list `system.ble_link_quality` as conditional on SEQ; FM `link_delay` beyond the bound fills its sequence value only if it arrives by the cut-off; TM provisional reading of `timestamp_implausible` ("not applicable") is superseded; WS02-T04 gets a `None` for `crypto_temporal.*` when a device of the scope is silent in the window; WS04-T07 transcribes the FM rows and must follow.

### Findings that change what other tasks may assume (consumer mismatches EC-OP-1 to EC-OP-13, no task edited)

WS07-T04 publishes `manip_task_failed` false with no manipulation outcome; WS04-T07 test 2 has an "uncommanded flag" and `NODE_STATE` events at the window start where this document has `link_down` at the start, `unreachable` at the lease lapse and a positive `commanded` key; the robot co-location is not in the trace (`NODE_STATE` with `colocated` needed); WS05-T07 test 36 says robot fields become `None` "from that time" where asserted facts of the window stay; WS05-T07 test 29 needs the robot status and not only presence samples for `intake_observed` False; test 31 puts the explained-away reading in the extractor where D-3 puts it in the rule; test 34 should require only the extractor's parameters; WS08-T04 `mask_evidence` as a path set cannot do the class recompute and "acts on attribution only" differs from a run without the robot on `int`; FM CAS-5 assumes robot streams feed `crypto_temporal.*` (D-12 says they do not); WS04-T08 step 4 verification key and the forged `auth` Sample; WS10-T03 content before and after against one `content_change`; WS07-T05 oracle gap-or-replay.

### Modelling choices and why

- Evidence unit is the violated instance; window = visible steps from the read start (minus a margin) to `decided_at_ms`; cut-off `decided_at_ms + D + grace`; two axes (device time after the buffer for values, arrival time for counters). Why: causality, and the same step grid the monitor uses (the witness window then agrees with the INT verdict, 6000 draws, zero exceptions).
- Strict aggregation: an aggregate is denied only if every capable component is denied. Why: `None` must never become a negative observation, and a silent cuff must not be exculpated by another device.
- `seq` is a device-level counter whose frame members share a value: repeats are keyed by `(name, seq)`, gaps by the device. Why: keying gaps by signal gives a false gap when a device sends other message kinds in between (EX-1 (h)).
- `ble_link_quality` is the delivery ratio over the distinct `seq` values (1.0 iff no value missing). Why: it gives the attribution layer an exact way to tell a repeat without a gap from a gap inside the one contract Boolean, until the split of ADR-034.
- Robot channels' availability is the robot status (`NODE_STATE`: `state`, `colocated`), with the run starting not co-located. Why: the monitor needs an explicit mask (T01 CG-6); lease inference from presence samples cannot reproduce a held level of 0 with the channel available (V-INT-3).
- Crypto fields cover BLE devices only. Why: A4 leaves them unchanged and the robot is inside the trusted base; the cost (CAS-5) is stated.
- `unreachable` and `link_down` are different node states. Why: it keeps condition LC of the fault model (a short BLE loss does not lapse the lease).

### What a reviewer should check hardest

1. Each of the 20 fields: adverse value and `None` condition per placement (Field semantics, Availability); the matrix S1 to S4 and S6 equals the extractor output, S5 equals `caps.py`; the aggregation rule against a counterexample (a field denied while a capable component has no basis).
2. The A4 mask: the six, four and ten fields and the choice D-11 that puts the robot heartbeat supervision in the embodied channel; the statement that crypto and cross-device are unchanged under A4 for every template (D-12); the partial A4 of a pure path mask.
3. Every "only", "never", "always", "exactly" sentence and its hypothesis (H-INIT, H-WARDCLK, H-SEQT, H-SEQSTATE, H-VLOG, H-PROF, H-VISIT, H-MASK); in particular D-9 (no false gap), D-3 (ratio 1.0 iff no gap; the pair separates a repeat only when every capable device has a finalised message), EX-9 (witness fields against the INT verdict, valid for one availability mask).
4. The timing rules: the cut-off and the case where a late input that caused the violation is outside it (EX-2); the detection lag of ward-generated evidence.
5. The ADR proposals 032 to 036 (self-contained, versions, migration, consistency with ADR-021 and ADR-026 to ADR-031) and the contract names (the extractor script parsed the contract itself; the Test 11 path check prints nothing).
6. The consumer mismatches EC-OP-1 to EC-OP-13 (quotes taken from the task files as they are).

### Fix round 1 (review of the independent reviewer: two BLOCKERS and eleven MINOR defects in the text)

Status is left `in_progress` (the orchestrator sets `done`). Files changed in this round: `docs/models/evidence-channels.md`, the wording of ADR-032 to ADR-036 only (`docs/plan/03-decisions.md`, lines 276, 277, 284), and this subsection. `docs/plan/02-interfaces.md`, `docs/formal/` and every other task file are unchanged. Scripts (scratch, not committed) are in `/tmp/ws02t03/fix1/`: `b1_repro.py` (B1, an evaluator written from the rules of the timing section and the V-LATE-1 numbers read from `docs/formal/golden/verdicts.yaml`), `b1_ex.py` (EX-11 with the reference extractor), `b2_repro.py` (B2), `m_checks.py` (M1, M5 to M8, M10, M11, written new for this round), and the earlier scripts re-run on the changed `ref.py` (two rule changes, see M8 and M11). The statement "the notes of the first round say about one draw in six" is withdrawn (M1); everything else in the first-round notes that this round does not mention stands.

**B1 (D-5, `late` outcomes).** Wrong: a `late` outcome is stamped when the task completes, after the deadline, and the deadline of a `sched` or `resp` task is the decision time `Ue` of the instance (T02 section 5.2, `deadline_ms`); rule 1 of the timing section (an axis-E input is used only if its visible step is not after the step of `Ue`) excludes it for every grace. Evidence (`b1_repro.py`, exit 0): on the V-LATE-1 fixture (tick 09:00, `Ue` 34200000) a `late` stamped 09:52:00, 09:30:01 or 09:30:00.001 is admitted at none of the graces 0, 10000, 600000, 5000000, and in 200000 random draws of a completion after the deadline none is admitted; `b1_ex.py` (exit 0): `system.nav_task_failed` is `None`, or False with an earlier success in the window, for the completion-stamped `late` at every grace tried (0, 10000, 1300000, 6000000). Decision: option (c), recorded in D-5 (`docs/models/evidence-channels.md` lines 405 to 418) and the new hypothesis H-OVERRUN (line 82): the robot reports the overrun at the deadline instant, stamped with the deadline (`deadline_ms` of the obligation record), `late` meaning "deadline passed with the task not complete"; a later completion is a separate event that does not retract it. Reason: (a) cannot work and its denial (False) would let a C1-by-exclusion rule read a delayed robot as no robot fault; (b) leaves `nav_delay` with no field at all (witness `None` is shared with a robot that is elsewhere); (c) keeps the field and the matrix row 5 at the price of a convention on the producer. Conditions (D-5, line 412 area): the stamp is the deadline itself (one millisecond later is outside for a deadline on the grid), the report is received by the watermark of its step, the robot is alive at the deadline, an outcome of any kind stamped after `Ue` is invisible, and the field reads the outcomes of the patient in the window and not those of the instance (declared limit). Where `hold` has no obligation of its own the report is visible only if the visit's deadline is not after its decision time. Updated: the conventions table row `outcome` (line 156), the field rows `system.nav_task_failed` and `system.manip_task_failed`, the derivation rows, the availability rows (R3 notes), rule 1 of the timing section, the new paragraph and the worked check EX-11 (lines 322 to 324, with the V-LATE-1 numbers; the manipulation field is treated alike). A4 and the placement matrix are not affected (the class None and the cells stay). Disclosed mismatches (EC-OP-14, line 525; none of the tasks edited): FM row `nav_delay` and its D-5 proposal, analisi §4.5 row 5, WS04-T07 test 10 (the stamp of the `late` outcome is not stated; it must be the deadline, not the delayed measurement time), WS07-T04 (`test_outcome_arrival_delay_and_lateness` stamps at the finishing of the task, and `test_every_obligation_gets_exactly_one_outcome` conflicts with an overrun report followed by a completion event), WS07-T05 oracle ("late or failed outcomes") and WS02-T05 DX-05 ("distinguishable through the navigation outcome") hold only under H-OVERRUN. No ADR was needed: ADR-035 item (1) makes the conventions table binding for the payload keys, and the stamp convention is part of the table row, so ADR-035 was not edited (its text is only to be re-read when it is confirmed).

**B2 (D-12, CAS-5).** Wrong: D-12 said CAS-5 "leaves a violated INT with provenance only", but the robot is co-located and only the presence Sample is lost, so by the invariant I1 of EX-9 both witness fields are present and adverse. Evidence (`b2_repro.py`, exit 0): the INT interval of the CAS-5 fixture is VIOLATED and the vector has `witness.robot_present` False, `witness.intake_observed` False, `crypto_temporal.*` False/True (denied), `system.liveliness_ok` True, `system.ble_link_quality` 1.0; with a logged verification failure only `crypto_temporal.authenticated` differs; with the robot away both witness fields are `None`. Change: D-12 rewritten (lines 463 to 473; the new paragraph "Cost, stated as a hazard" at 471) to say what the fields show, why the attribution cannot separate a link fault from an integrity event by them (same pair as an unwitnessed dispense: TM `dispense_forgery` TX-4 (c); WS08-T04 test 6 builds its C3 fixture from a witness pattern), and what ADR-010 and WS02-T04 must decide (accept the false-C3 hazard, read the pair as UNDETERMINED, or widen the scope of `crypto_temporal.*` and `system.qos_deadline_missed` to the robot presence stream, which reverses D-12); EC-OP-6 (line 517) rewritten with the quotes and the consequences for WS02-T04, WS02-T05 (CAS-5 and OP-12 as hazards) and WS08-T04; the new worked check EX-12 (line 212); the Traceability sentence for WS02-T04. The attribution rule is not decided here. "Robot present" in WS08-T04 test 6 is read as "robot co-located, channel available"; the wording ambiguity is EC-GAP-11.

**M1.** The figure "one draw in six" depended on an undescribed generator. `m_checks.py` (exit 0): with one fixture-only generator (six messages, delays uniform inside `D`) the share of draws with non-monotone `seq` in arrival order goes from 0 (message spacing at least `D`) to 98.5% (spacing a tenth of `D`). The figure is removed (line 335) and replaced by the dependence on the spacing, stated as a property of the generator.

**M2.** EC-OP-8 (line 519) misquoted WS04-T08 step 4. Re-read: the step says to use the conventions table of `evidence-channels.md` if it exists. Corrected: the table applies, the keys go to `vocab.py` (test 18), they stay provisional until ADR-035 is confirmed; the keyless-forged `auth` Sample note is EC-GAP-9. The quote was checked programmatically against the task file.

**M3.** Added EC-OP-15 (line 526) and a clause in D-14 and in the section text: WS05-T07 test 35, WS05-T09 and WS07-T04 (per-tick `intake_observed` False and identity values published as field values) against D-14 "a snapshot that is not a trace item is not an input"; `intake_observed` False has no trace item. Open, not decided.

**M4.** Added to the Traceability consequence list and as EC-OP-16 (line 527): `unreachable` for a robot-target `process_kill` and for `battery_depleted` makes `system.node_lifecycle` asserted here, where FM says "not raised (limit)"; WS07-T05's oracle is checked against FM.

**M5.** The aggregation rule now states the declared limit "partial coverage" (line 69) and EX-3 (g): with `hold`, a cuff with `seq` and a dispenser without it, `crypto_temporal.seq_gap_or_replay` is False and `system.ble_link_quality` 1.0 while the dispenser loses two values (`m_checks.py`: True and 0.5 with a capable dispenser, False and 1.0 without); same for `crypto_temporal.authenticated`; reconciled with EX-3 (f) (a capable silent component prevents the denial, an incapable one never does).

**M6.** D-3 (line 389) now lists the forged message whose number jumps ahead as a second declared limit (TM `injection_naive`, naive `dispense_forgery`, TX-9), with the consequence for those rows and EX-1 (m) (`m_checks.py`: gap True, ratio 0.12). ADR-034's own context still lists only "a replay together with a loss"; it was not edited (the instruction limits the ADR edits to the wording of M9), so it should be extended when ADR-034 is confirmed.

**M7.** "1.0 exactly when no sequence value is missing" now reads "between the base and the top value of the window" in the field row, the derivation, D-3 and the D-9 definition (with the base-less case: smallest value minus one; trailing loss not seen). EX-1 (h), (i), (k) carry the base; new (i2) first value lost, (l) trailing loss, (m) jump-ahead (`m_checks.py`, exit 0; the reviewer's evaluator `/tmp/rev16/ex1.py` gives the same (a) to (k) values). The sentence of the ADR-034 context, "1.0 exactly when no value is missing", was not edited (the instruction limits the ADR edits to the wording of M9); it needs the same qualification when ADR-034 is confirmed.

**M8.** (i) The entry of `system.node_lifecycle` is now the last uncommanded adverse token, else the last commanded one, else `active` (rule in the derivation row, the reading rules, D-4 and EX-4 with three new cases; `ref.py` changed, `m_checks.py` checks them). (ii) H-INIT (line 75) now says that `NODE_STATE` events are transition reports and that this is the one place where an absence is read as a reading (lifecycle state and lease state), with its declared limit; the aggregation rule points to it; `m_checks.py` shows a silent node reads `active` and `system.diagnostics_ok` stays `None`.

**M9.** ADR-033 line 277: "a pure path mask" replaced by "the robot entry of each mapping could then be removed after the fact, but that is the removal of a key and not a pure path mask (a path addresses a field, not an entry of a mapping)"; ADR-033 line 276: the scope summary now names INT's reason for including the robot (it reads the witness channels `presence` and `intake`); ADR-034 line 284 and the migration: `crypto_temporal.seq_repeat` and `system.seq_gap` are written `crypto_temporal/seq_repeat` and `system/seq_gap`. `git diff master -- docs/plan/03-decisions.md` removes no line.

**M10.** EX-6 (line 208) and the Traceability sentence now say "with exactly periodic arrivals" (`m_checks.py`: with exactly periodic arrivals a single loss never exceeds a deadline of two periods; with jitter inside `D` it does in 9973 of 20000 draws of that fixture generator, which is not a device rate and is not quoted in the document as one).

**M11.** (i) `evidence_grace_ms` (line 360) now says that only axis-R counters are affected; `m_checks.py`: admission of an axis-E input is independent of the grace in 50000 draws. (ii) `crypto_temporal.timestamp_implausible` for a device without independent clocks is now `None` unless a message of it was classified late or future-stamped (then True), never False: the field row, derivation row, availability note, line 346 (TM TX-9 consequence), EX-1 (k), the capability description and EC-OP-19 (WS04-T08 test 4 holds; test 5 holds; the limit that a rule needing a denial cannot be satisfied in a benchmark without a transport-delay model is stated); `ref.py` changed, `caps.py` and `matrix.py` re-run unchanged (S5 and S6 cells). (iii) The scope table column is now "robot node in the scope (system and witness fields)" with a sentence (line 65): for `range`, `count` and `sys` all robot-derived fields are `None`; `signal_quality.cuff_error_code` is computed whatever the template and is `None` for `count` and `int` when the cuff was silent in the window (`m_checks.py`).

**Consumer mismatches added as open points (quotes checked programmatically against the task files, no task edited):** EC-OP-14 (B1), EC-OP-15 (M3), EC-OP-16 (M4), EC-OP-17 (WS02-T04 step 4, "robot liveliness denied ... removed by A4" against the aggregated scalar and the recompute class), EC-OP-18 (WS04-T07 has no lease parameter to choose between `link_down` and `unreachable`), EC-OP-19 (WS04-T08 test 4 against `two_clocks`), EC-OP-20 (the extractor with the robot excluded is not in WS05-T07), EC-OP-21 (node status across the day boundary against the retained `seq` state). The A4 section now states that "cannot be done after the fact" is true of the three aggregate scalars and of path sets, not of `system.node_lifecycle` (already a per-node mapping; a key removal is not a path mask).

Verification of the round (real commands, run from the repository root, `.venv` active): `python /tmp/ws02t03/fix1/check_doc.py` exit 0, `SUMMARY: 603 checks, 0 failed` (the twelve checks of `## Test`, the Done-when commands, the contract-name checks with its own parser, matrix and A4 agreement with the extractor, and the scripts listed above); each of `b1_repro.py`, `b1_ex.py`, `b2_repro.py`, `m_checks.py`, `test_golden.py`, `test_prior.py`, `props.py`, `props2.py`, `ex.py`, `matrix.py`, `caps.py`, `a4.py`, `int_check.py` exit 0; the Done-when block: `test -f` exit 0, the 20-field loop prints nothing, `grep -c '^## '` 11, `CH-` identifiers 8, `grep -c '^## ADR-'` 36, `grep -c '^Version 0.1.0. Owner WS02' docs/plan/02-interfaces.md` 2, the evidence-path check prints nothing (grep exit 1), the token grep prints nothing (grep exit 1); `git diff master -- docs/plan/02-interfaces.md` empty; `git diff master -- docs/plan/03-decisions.md` removes no line; `pytest -q` 175 passed (exit 0); `python3 tools/check_plan.py` exit 0.

### Post-task review

- Produced: `docs/models/evidence-channels.md` (eleven sections: conventions, eight channel identifiers CH-*, field semantics for the 20 `EvidenceVector` fields with adverse value, producer and None condition, derivation from the trace schema and ROS 2, availability per placement (ward node, robot co-located, robot away, robot down), the ablation A4 mask (6 None, 4 recompute, 10 unchanged), timing and evidence window with hypotheses H-*, decisions D-1 to D-14, contract gaps EC-GAP-1 to EC-GAP-12, traceability with open points EC-OP-1 to EC-OP-21, worked checks EX-1 to EX-12) and ADR-032 to ADR-036 appended to `docs/plan/03-decisions.md` (all `proposed [DA-CONFERMARE]`; no existing ADR edited; `docs/plan/02-interfaces.md` unchanged, version count 2). Orchestrator re-ran the "Done when" block twice (20-field loop empty, 11 headings, 8 `CH-` identifiers, 36 ADRs, contract version count 2, token greps empty, exit 0), checked that the diff of `03-decisions.md` removes no line, re-ran the full suite (175 tests) and `check_plan` (exit 0), and re-checked the B1 rule with an own few-line evaluator. Two independent reviews with own evaluators (validated on golden cases): FAIL (two BLOCKERS: the `late` navigation outcome could never reach `system.nav_task_failed` under the cut-off rule; decision D-12 hid the integrity-first hazard of CAS-5), fix round 1 (`c5308d7`), PASS (no BLOCKER; B1 fix checked on the V-LATE-1 fixture; CAS-5 reproduced; decision D-9 held in 40000 multi-frame draws; EX-1 to EX-12 verified; 299 identifiers checked).
- Decisions taken here (all recorded with reasons and conditions in the document): in-bound reordering raises neither `timestamp_implausible` nor `seq_gap_or_replay` (D-9; consequences listed for the fault-model rows `ble_dropout`, `message_drop`, `link_delay`, the threat-model "not applicable" reading, WS02-T04 and WS04-T07); the robot reports `late` at the deadline instant and stamps it with the deadline (H-OVERRUN, D-5); `battery_low` is the robot battery only (D-2); robot heartbeat supervision is split by subject node in `CH-SYS-ROBOT` (D-11); the gap-explained-away reading sits in the rule, not the extractor (D-3).
- Deviations from the task text: `CH-DISP` is listed as proposed, not as a feeding channel; the step-4 idea of deriving `timestamp_implausible` from non-monotonic device time is not followed; five ADRs instead of the minimum, gaps EC-GAP-1 to 12 and open points EC-OP-1 to 21 beyond the minimum; the ADR index line at the top of `03-decisions.md` still stops at ADR-023 (existing text not edited).
- Dependents: WS02-T04 (needs WS01-T07 too), WS04-T07 (needs WS04-T06) and WS04-T08 (needs WS04-T06) stay `blocked`. Assumptions of six downstream tasks no longer hold or are ambiguous and were flagged (notes in their files, kept `blocked`): WS02-T04, WS04-T07, WS04-T08, WS05-T07, WS07-T04, WS08-T04.
- Open MINOR (apply at the next touch): (m1) EX-11 (b) to (d) and the D-5 reason say None for a late report, a +1 ms stamp or a `failed` stamped after Ue, but with an earlier success in the window the field reads False (grace 0 and 10000), which is exactly the denial hazard that D-5 uses to reject option (a); declared limit (v) covers only the assertion direction; (m2) H-INIT ("the one place where an absence is read as a reading") is over-broad: `cuff_error_code` is the empty string with no DEVICE_ERROR event, `authenticated` is True when no failure event is logged (H-VLOG), `intake_observed` is False when no INTAKE event exists; (m3) the delivery ratio is 0/0 when the top value is at or below the base (688 + 599 of 11070 random windows), which the None condition does not cover (no false repeat or gap arises); (m4) undisclosed consumer mismatches on `failed` outcomes: fault-model rows `impossible_goal` and `manipulation_failure` list `nav_task_failed` and `manip_task_failed` as raised unconditionally, true only if the failure is stamped by Ue; and FM `nav_delay` on `hold` and DX-05 get the field only if the visit deadline is not after the hold decision (EX-11 (e)); (m5) a third instance of the CAS-5 pattern is missing from D-12 and EC-OP-6: the robot outage with a lagging availability mask (FM hypothesis 9, OP-10, FX-9 (e)): robot dead at 20:50, `unreachable` stamped 21:05, presence 0 held gives a VIOLATED INT with both witness fields False and `liveliness_ok` still True; (m6) the D-12 sentence "a forged dispense that the robot did not witness is not attributed to C3 either" needs "with no authentication evidence"; (m7) ADR-034 context still lacks "between base and top" and the jump-ahead forgery, and ADR-035 makes the conventions table binding while its text speaks only of keys (the H-OVERRUN stamp rule lives in that table); (m8) the S3 witness cells assume a constant placement (a robot that leaves mid-window after seeing the patient gives True); (m9) EX-12 omits the capabilities behind `timestamp_implausible` False and `authenticated` True, the polarity vocabulary of the Columns line differs from the table, and review-round labels ("B1 of review round 1", "M3", "M11") sit in a reference document.
- Risks: EX-7 and EX-8 were not independently re-run by the reviewer (consistent with the field-table None conditions); several downstream tasks (WS04-T07, WS05-T07, WS07-T04) hold their expectations only under H-OVERRUN and the decisions above; ADR-032 to ADR-036 are proposals until M1 (ADR-021).
