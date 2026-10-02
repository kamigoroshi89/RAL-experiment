---
id: WS02-T01
title: Fault model for C2 (device, link, robot)
workstream: WS02-threat-fault-model
owner: agent
status: done
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

## Notes

Written by the worker agent of WS02-T01. Status is left `in_progress` on purpose (the orchestrator sets `done` after review). The work is committed on branch `ws02-t01-fault-model`; nothing is merged and no other task file was changed.

### Verification (real commands, run from the repository root with `.venv` active)

Scripts for the checks are in `/tmp/ws02t01/` (not committed): `check_doc.py` (all ten checks of the task `## Test`, plus programmatic cross-checks against `docs/plan/02-interfaces.md` and the golden files), `sem.py` (a small reference implementation of the instance semantics of T02 section 1.5 and T05), `test_golden.py` (the evaluator reproduces 30 golden or worked cases of the merged documents before it is used on any fixture), `test_fx.py` (the 14 worked checks FX-1 to FX-14 of the document). Before the document existed, `check_doc.py` failed (`FAIL doc exists`, exit 1); after an empty file it failed 49 checks.

Done-when commands (output of the run, exit codes as shown):

```
== Done-when 1: test -f
exit=0
== Done-when 2: grep -c '^## '
10
exit=0
16:## Scope and fault hypothesis
48:## Subtype vocabulary
94:## Device faults
113:## Link and time faults
143:## Robot faults
164:## Fault effects on templates and cascade seeds
374:## Fault-to-evidence table
400:## Injection parameter sheet
426:## Non-faults and boundaries
459:## Traceability
== Done-when 3: sed vocabulary count
17
exit(pipe last)=0
== Done-when 4 / Test 4: evidence-path check
grep-v exit=1 (1 = printed nothing)
== Done-when 5: forbidden tokens
grep exit=1 (1 = printed nothing)
== Done-when 6 / Test 8: numbers
grep-v exit=1 (1 = printed nothing)
== glossary sweep (WS02 README 7)
grep exit=1 (1 = printed nothing)
```

`python3 /tmp/ws02t01/check_doc.py`: SUMMARY: 104 passed, 0 failed (exit 0). It covers: headings in order (Test 1); vocabulary identifiers, one `- <id>` per line, 17 of them (Test 2); catalogue columns, rows, basis `source` or `inferred`, `TemplateId` values and matrix row numbers in the three family tables (Test 3); every `group.field` path is one of the 20 fields parsed from the contract, and every one of the 20 is mentioned (Test 4); the five sentences of the fault hypothesis (Test 5); the timing table with `t_device_ms`, `t_rx_ms`, `seq` for the five link faults and the absorbable and non-absorbable statement (Test 6); non-faults (Test 7); no invented numbers and no citation from memory (Test 8); a sheet row per fault with a named consumer, the three `DeviceErrorModel` field names and the arrival-jitter source (Test 9); catalogue template sets equal the template sets of the effect rows (own check); the evidence paths of the catalogue equal those of the fault-to-evidence table (own check); every golden id quoted exists in `docs/formal/golden/*.yaml`; every capitalised backtick token is an `EventKind`, verdict state or template kind name of the contract.

`python3 /tmp/ws02t01/test_golden.py` (exit 0), the evaluator reproduces the cases the document quotes, before FX use:

```
PASS G-RANGE-2 
PASS G-RANGE-1 
PASS G-SCHED-1 
PASS G-SCHED-2/V-SCHED-4 
PASS V-SCHED-3 
PASS G-SCHED-4 
PASS V-SCHED-5b state at kd (09:51 after deadline) 
PASS V-LATE-1 
PASS V-LATE-2 
PASS G-HOLD-4 
PASS G-HOLD-3 
PASS G-RESP-1 
PASS G-RESP-2/V-RESP-4 
PASS G-RESP-3 
PASS G-RESP-4 
PASS V-RESP-5 
PASS V-RESP-6 tie 
PASS G-COUNT-1/V-COUNT-1 
PASS G-COUNT-2/V-COUNT-2 
PASS G-COUNT-3 
PASS G-SYS-3 
PASS G-SYS-2 
PASS V-INT-1 
PASS V-INT-2/G-INT-3 
PASS V-INT-3 
PASS G-INT-1 
PASS G-INT-2 
PASS Lemma 3 example [-110, 90] 
PASS W6 carry-over count 3 
PASS W6 truncated count 1 
golden/evaluator self-check: 30 passed
```

`python3 /tmp/ws02t01/test_fx.py` (exit 0), the worked checks of the document (values are those hand-computed in the document; the evaluator was independent of the hand arithmetic, and the golden file is the common reference):

```
PASS FX-1a sched nominal
PASS FX-1a sched removed
PASS FX-1b resp nominal +8
PASS FX-1b resp removed violated obligation_unmet at 10:00
PASS FX-1b2 resp pre removed too still violated
PASS FX-1c hold nominal +20
PASS FX-1c hold removed guard
PASS FX-1d range/sys no instance without meas event
PASS FX-2a nominal 09:05 slack 1500000
PASS FX-2a delayed 09:51 violated at 09:30 (-inf, guard)
PASS FX-2a graded value at 09:51 = -1260000  -1260000
PASS FX-2a interval hi at kd = (kd-(kd+1))*TS = -60000
PASS FX-2b resp nominal 09:30 drop 12 -> +2
PASS FX-2b resp delayed 10:30 violated obligation_unmet
PASS FX-2c tick1 violated, tick2 satisfied by the delayed measurement (1200000)
PASS FX-3 watermark 09:30:30  34230000
PASS FX-3 max absorbed total delay = D + phase = 40000  40000
PASS FX-3 arrival 09:30:30 accepted -> sched satisfied tie
PASS FX-3 arrival 09:30:31 late -> sched violated, counted late
PASS FX-3 delay equal to D is always on time (phase sweep)
PASS FX-3 delay equal to D + T_s is always late (phase sweep)
PASS FX-3 late meas event: no accepted measurement event (no RANGE instance)
PASS FX-4a skew within skew_max: accepted, stamped step 571 outside [540,570] -> violated, no counted future stamp
PASS FX-4b skew beyond skew_max: future stamp, counted, not used -> violated
PASS FX-4c device behind: late (watermark 09:27:30 < rx 09:29:00) -> violated, counted late
PASS FX-4d device behind within D: accepted at step 567, slack 180000 (true slack would be 60000)
PASS FX-4 fault-free: slack 60000 satisfied
PASS FX-4 fault-free step 569 -> slack (570-569)*60000 = 60000
PASS FX-5 fault-free HOLD +20
PASS FX-5 cuff ahead by 3 min (accepted): HOLD violated no_recent_measurement
PASS FX-6a steps: real 1260, bounce 1261
PASS FX-6a real dispense instance count 2 tie satisfied (0)
PASS FX-6a bounce instance count 3 -> -1 violated
PASS FX-6b next-day real dispense: trailing count 3 -> margin -1  3
PASS FX-6b without carry-over the next-day count is 1
PASS FX-6c day-end: omission -1 violated; with bounce 0 tie satisfied
PASS FX-6d hold: both the real and the bounce instance violated (guard)
PASS FX-7a stuck: drop 0 each, margin -10, violated at 10:00
PASS FX-7b frozen 152 -> -12 each measurement (G-RANGE-2)
PASS FX-7b frozen 125 -> +15 (G-RANGE-1) while latent 152 would give -12
PASS FX-7c frozen 94 at dispense -> -6 (G-HOLD-2)
PASS FX-8a latent 125 + 27 = 152 -> -12 violated (false)
PASS FX-8a latent 152 - 27 = 125 -> +15 satisfied (masks latent -12)
PASS FX-8b hold latent 119 -25 = 94 -> -6 violated
PASS FX-8b hold latent 94 +25 = 119 -> +19 masks
PASS FX-8c resp bias on both pre and window cancels (+8 both)
PASS FX-8d resp bias onset between pre-dose and window: (150-159)-10 = -19 violated
PASS FX-9a robot out (presence unavailable in window): PENDING marker channel_unavailable:presence, [-inf, 300000]
PASS FX-9a2 robot out (presence and intake unavailable): same interval, marker names both
PASS FX-9b auth present, robot out: SATISFIED 300000
PASS FX-9c latent: presence seen at 20:58 -> +300000 satisfied
PASS FX-9c presence=1 sample lost, earlier 0 held: VIOLATED no_witness
PASS FX-9d no presence sample at or before the dispense, channel available: PENDING value_undefined:presence
PASS FX-10a sample dropped, event kept, no earlier sample: [-110, 90] PENDING value_undefined:bp
PASS FX-10b earlier sample 125 read: +15 satisfied (stale)
PASS FX-11 day-end count nominal 0 tie satisfied; 21:00 dispense lost -> -1 violated
PASS FX-12 reordered within D: both accepted, held values identical at every step
PASS FX-12 held at step 552 is 152 and at 551 is 125
PASS FX-13 outage: SCHED(09:00) violated decided 09:30, RESP(07:00) violated decided 10:00
PASS FX-13 fault-free: SCHED +1500000, RESP +8
PASS FX-14 INT undecided with marker naming presence and intake
PASS FX-14 SCHED(21:30) violated decided 22:00; RESP(21:00) violated decided 24:00
FAILS 0
```

Full suite: `pytest -q`: 175 passed (exit 0). `python3 tools/check_plan.py`: `check_plan: OK (103 tasks, 18 contracts, 31 findings)` (exit 0). Only `docs/models/fault-model.md` and this task file were changed.

### Deviations from the task text (kept minimal)

1. The sheet's unit types are `ms`, `dimensionless`, `mmHg`, `m` and `rad`, not only `ms` or `dimensionless`: the parameters of WS07-T05 (`sigma_xy_m`, `sigma_yaw_rad`) and the bias (`bias_mmhg`) have physical units that are not times. Unit types carry no value.
2. Open points and contract gaps are two H3 subsections inside `## Traceability`, so that the document has exactly the ten required H2 headings in the required order.
3. `## Subtype vocabulary` holds the bullet list of the 17 identifiers (nothing else begins with `- `), then a table of family, basis and injectors; the table is after the list so that the Done-when `sed` count and a line parser see only identifiers.
4. The effects section carries the mechanism classes M-REM, M-LATE, M-VAL, M-DUP, M-DLOSS, M-ROBOT-OUT, M-PRES, M-STALE, M-SKEW, the signal-footprint table, the table of effects (fault, template, effect, mechanism, check) and the worked checks FX-1 to FX-14 and the cascades CAS-1 to CAS-5; the task asked for a table of faults, templates and cascade seeds, and the rigour rule (every claim with a mechanism and a check) required the rest.
5. The task text says `uncommanded_lifecycle_transition` is `inferred` (its qualifier "uncommanded" is made explicit from analisi §4.6, although §5.2 mentions lifecycle transitions); the catalogue follows the task.

### Contract gaps found (not changed; recorded in the document, section Traceability)

CG-5 of T01 (no `EventKind` for `auth`, `presence`, `day_end`, `cuff_health`); CG-10 of T01 and ADR-021 (one Boolean `crypto_temporal.timestamp_implausible`, no clock-health field); FM-GAP-SEQ (ADR-021, `crypto_temporal.seq_gap_or_replay` mixes loss and replay); FM-GAP-DISP (ADR-021, no field for dispenser content or dispense interval); FM-GAP-FLAT (no field for a run of identical values); FM-GAP-NODE (no payload keys fixed for `NODE_STATE`, `DEVICE_ERROR`, `ROBOT_TASK`, `DISPENSE`); FM-GAP-LIVE (scalar system fields do not say which node; per-device liveliness and deadline QoS assumed). Open points OP-1 to OP-9 (witness perception false negative not catalogued; failed-visit encoding on the witness channel; commanded marker; diagnostics source and device battery; publication of an inactive node; injectors for the modelled-only faults; separate or joint drops of `Sample` and `Event`; propagation rules; ward node failure).

### Modelling choices

- A fault is a cause, not a violation or an alert (hypothesis 5); a C2 true event is the injected event (analisi §5.1).
- Effects on templates are derived only through the signal footprint of each template (T02 section 3.1), and every claim carries a mechanism class and a check (a golden case or an FX). "No row" means no derived mechanism, not "cannot", except where the footprint excludes it.
- The measurement of SCHED and RESP is assumed to go through the robot visit (hypothesis 7), as T02 section 5.1 and the plan of WS04-T07 do; this makes robot faults reach `sched`, `resp`, `hold` and `range`.
- A robot outage leaves INT undecided, never VIOLATED (T05 section 3.5); the one path from a C2 cause to a violated INT found is a lost or late `presence` Sample with the channel available (CAS-5), recorded as a hazard for the integrity-first rule.
- `cuff_detached` in the injected form opens no SYS instance (a `MEASUREMENT_MISSED` Event is not a `meas` impulse); the SYS-violating variant is named but not injected.
- Cascade seeds are fan-outs from one emptied position or chains through the derived counter; the root-cause rules are WS02-T04's and are not defined.
- Time faults: absorbed iff the total delay is at most `D` plus the phase term of the step (derived from T01 section 4.2, checked by a phase sweep in FX-3); `clock_skew` is a constant offset (drift is not modelled); `out_of_order` is the observable consequence of unequal delays.
- Names of injection parameters follow WS07-T05 (`delay_ms`, `probability`, `sigma_xy_m`, `sigma_yaw_rad`, `period_ms`) and WS04-T07 (`gap_ms`, `bias_mmhg`, `noise_level`); `offset_ms` and the common `onset_ms`, `duration_ms`, `seed`, `target` are new names with no conflict.

### What a reviewer should check hardest

1. The twenty field names and the meaning attached to each use (the Fault-to-evidence table and its coverage paragraph), especially the conditional fields (QoS and liveliness per device stream, FM-GAP-LIVE) and the fields made `None` by robot faults.
2. Each row of the effects table: the mechanism class, the signal, the stale-open position or marker, the verdict state and the check. Hardest: `cuff_detached` and SYS (none), `stuck_at` on RESP (zero drop needs onset at or before the dose and a window covering the response), M-PRES (the held 0 must cover the whole decision window, otherwise PENDING with `value_undefined:presence`), `clock_skew` rows (FX-4, FX-5), the bounce downstream row (needs carry-over, CP7).
3. The C1, C2 and C3 boundary and the undetectable cases (rows 4 and 10 of the analisi matrix, rows 6 and 7 without content sensing) in `## Non-faults and boundaries`.
4. The cascades CAS-1 to CAS-5: order of events, why each is a fan-out or a chain, and the separating evidence; CAS-5 is a new hazard (a link fault that reaches a violated INT).
5. The injection parameter sheet: every name has a consumer in WS04-T07 or WS07-T05, or is explicitly "none in v1"; `delay_ms`, `offset_ms`, `probability` versus `dispenser_bounce_prob` are the names to compare with the plans of the two consumers.
6. The assumptions that are not in a source and are flagged as open: inactive nodes do not publish (OP-5), samples and events can be dropped independently (OP-7), per-device liveliness and deadline QoS (FM-GAP-LIVE).

### Fix round 1

Independent review found three blockers (B1 to B3) and eleven minor defects (M1 to M11) in the text of `docs/models/fault-model.md`. Only that document and these Notes were changed; status stays `in_progress`. Scripts of this round are in `/tmp/fix1/` (not committed): `repro.py` (B1, B2, FX-15, FX-16; two evaluators, the reviewer's `/tmp/rev13/ev.py` and the earlier `/tmp/ws02t01/sem.py`, which must agree) and `repro2.py` (M1 and M5, sweeps over phases, offsets and delays). Every defect was reproduced before any edit.

- **B1 (robot-node faults and `count`).** The sentence "no robot fault can violate `count` or `sys`" was false because `process_kill` and `uncommanded_lifecycle_transition` may target the dispenser node, and a silent dispenser loses a real `dispense` (M-DLOSS). Evidence: day-end margin 0 SATISFIED with dispenses 07:00 and 21:00, margin -1 VIOLATED with the 21:00 one lost (both evaluators). Change: the footprint paragraph now says a robot-node fault with the robot as target cannot violate `count` or `sys`, and names the dispenser-target exceptions; the two catalogue rows and two new effect rows (`count`, violated, dispenser target only) restore the equality of catalogue and effect-row template sets (checked by script); M-DLOSS states that a lost dispense also opens no HOLD, RESP, INT or COUNT-limit instance (masked violations, new FX-15, with the latent verdicts reproduced); the fault-to-evidence table, the family paragraph of the robot section and hypothesis 7 are aligned.
- **B2 (`dispenser_bounce` windows).** The claim "VIOLATED when the real one is, except possibly for a reading on the oldest edge step" was false in both directions and for `resp` and `int`. Evidence (both evaluators, step 420 real, 421 bounce): HOLD reading at step 360 gives real +20, bounce VIOLATED `no_recent_measurement`; reading at step 421 gives real VIOLATED, bounce +20; RESP single reading at step 480 gives real +8, bounce VIOLATED `obligation_unmet`, at step 601 the reverse; INT witness at age equal to `int_window` gives real margin 0 (tie, SATISFIED) and bounce -60000 VIOLATED, interior witness gives margins 180000 and 120000, a presence level rising at step 421 gives the reverse; with a real dispense off the grid the offset is 0 and the verdicts are equal. New mechanism class M-DUPWIN (offset 1 iff a grid time lies in `[t, t + gap)`, verified by a sweep). Added `resp` and `int` to the catalogue, effect rows (three rows, both-direction wording), fault-to-evidence table (`int` is INTEGRITY kind), device notes, CAS-3, footprint paragraph and a new open point OP-12 (a device fault reaching an integrity violation); FX-6 kept as it was; new FX-16 gives one fixture example per template. In the reverse direction the real violation is kept: only "real SATISFIED, bounce VIOLATED" adds a violation.
- **B3 (consumer names).** The earlier Notes and the sheet said WS04-T07 and WS07-T05 both use the sheet names. Read from the task files: WS04-T07 has `onset_ms`, `duration_ms`, a scalar `magnitude`, `magnitude_unit` and `params` (line 66) and none of `gap_ms`, `bias_mmhg`, `noise_level`, `delay_ms`, `seed`, `target`; the mapping form `magnitude.<key>` and the keys `probability`, `sigma_xy_m`, `sigma_yaw_rad`, `period_ms`, `delay_ms` (nav_delay) are WS07-T05 only (line 42). Change: the sheet now has a comparison table by consumer, with task and line references and a match column; the old claim is replaced; open points OP-13 (names and shape), OP-15 (`nav_delay` duration). **Correction of the Notes above ("Modelling choices", last bullet):** "Names of injection parameters follow WS07-T05 ... and WS04-T07 (`gap_ms`, `bias_mmhg`, `noise_level`)" is wrong for WS04-T07; those three names, `delay_ms`, `seed` and `target` are not in the plan of WS04-T07, and only `onset_ms` and `duration_ms` match it. The old text is kept above on purpose; this paragraph supersedes it.
- **M1 (outage lag).** New hypothesis 9 and OP-10: the claim "a robot outage cannot produce a VIOLATED `int`" assumes the channels are marked unavailable no later than the dispense step. Evidence: held presence 0, dispense 21:00 (step 1260): marking from step 1255, 1258 or 1260 gives PENDING; marking from step 1261 or never gives VIOLATED `no_witness` (both evaluators); FX-9 (e). Rows, M-ROBOT-OUT, the limits paragraph and the "do not do" list now carry the hypothesis.
- **M2 (ADR-026).** M-PRES, FX-9, CAS-5 and the bounce `int` row state that they use the reference form of INT (T02 section 4.7), that ADR-026 is proposed and not confirmed; OP-11.
- **M3 (evidence conditions).** The fault-to-evidence table now defines LC (lease or deadline), SEQ (device with `seq` and a later delivered message) and D-5, and moves `ble_dropout` (liveliness, deadline, gap), `message_drop` (gap), `process_kill`, `battery_depleted` (liveliness, deadline) and `nav_delay` (`system.nav_task_failed`) to the conditional column; the catalogue and CAS-1 text are aligned; the equality of catalogue paths and the union of raised and conditional columns was re-checked by script.
- **M4 (set of paths).** Rule stated before the table: the set of a fault is the union of "raised" and "conditional"; "becomes `None`" and "not raised" are excluded.
- **M5 (time-fault conditions).** Future-stamped iff offset above transport delay plus `skew_max` (strict, T01 section 4.4 rule 1); late iff transport delay plus offset above `D` plus the phase term of the stamp; over-statement of the slack is the offset rounded to whole steps (exact for an offset that is a multiple of `T_s`); a stamp before `k_a` leaves the SCHED window empty. All verified by sweeps (1656, 2484 and 17940 cases); FX-4 states zero transport delay.
- **M6, M7, M8 (downstream mismatches, disclosed, not edited elsewhere).** OP-14 (WS02-T03 derives `timestamp_implausible` also from non-monotonic device time; this document says `out_of_order` within the bound raises no evidence), OP-16 (`NODE_STATE` for `cuff_detached` against WS04-T07 test 5), OP-15 (`nav_delay` duration against WS04-T07 tests 10 and 13).
- **M9.** Row 6 of the analisi matrix is the C1 double take: the covered rows are now 3, 4, 5 and 7 as C2 rows, row 6 as a confounder of `dispenser_bounce`, and the C1 and C3 rows list includes 6.
- **M10.** The authentication sentence is qualified (where it exists, through sequence numbers and timestamps, for an attacker without the keys; analisi §4.5 row 8).
- **M11.** `G-SEQ`, `G-DISP`, `G-FLAT`, `G-NODE`, `G-LIVE` renamed to `FM-GAP-SEQ`, `FM-GAP-DISP`, `FM-GAP-FLAT`, `FM-GAP-NODE`, `FM-GAP-LIVE` in the document and in the Notes above (labels only; no other repository file used them).

Verification of this round (real exit codes, from the repository root with `.venv`): the six Done-when commands (`test -f` 0; `grep -c '^## '` prints 10; vocabulary count prints 17; evidence-path check prints nothing; forbidden tokens print nothing; numbers-with-units check prints nothing); `python3 /tmp/ws02t01/check_doc.py` 104 passed, 0 failed (exit 0; it covers the ten Test checks, catalogue against effect-row template sets and catalogue against fault-to-evidence paths); `/tmp/ws02t01/test_fx.py` (FX-1 to FX-14, all PASS, exit 0) and `test_golden.py` (30 golden or worked cases, exit 0); `/tmp/fix1/repro.py` 0 failures (exit 0; includes the new FX-15 and FX-16 values and the M-DUPWIN offset rule); `/tmp/fix1/repro2.py` 0 failures (exit 0); the reviewer's `fx*.py` re-run without error (they print values and assert nothing; the asserting check of FX-1 to FX-14 is `test_fx.py`). The 232 earlier backtick identifiers were re-listed with `/tmp/rev13/ids.py`: the new tokens are numbers, intervals, `[DA-CONFERMARE]`, the WS07-T05 keys `magnitude.*` and the variable `t`; every contract field path, EventKind, SignalId, TemplateId, DeviceErrorModel field and golden id of the document exists in the contract or the golden files (script output: 20 of 20 evidence fields, no missing golden id). `pytest -q`: 175 passed (exit 0). `python3 tools/check_plan.py`: `check_plan: OK (103 tasks, 18 contracts, 31 findings)` (exit 0).


### Post-task review

- Produced: `docs/models/fault-model.md` (ten sections: scope and fault hypothesis with nine hypotheses, a vocabulary of 17 subtype identifiers, device, link and time, and robot fault catalogues, fault effects on templates with mechanism classes M-REM, M-LATE, M-VAL, M-DUP, M-DUPWIN, M-DLOSS, M-ROBOT-OUT, M-PRES, M-STALE, M-SKEW, a signal-footprint table, worked examples FX-1 to FX-16 and cascades CAS-1 to CAS-5, a fault-to-evidence table, an injection parameter sheet with a consumer comparison, non-faults and boundaries, traceability with contract gaps `FM-GAP-*` and open points OP-1 to OP-16). Orchestrator re-ran the "Done when" block (10 headings, 17 subtypes, token and numbers-with-units greps empty, exit 0), the full suite (175 tests) and `check_plan` (exit 0). Two independent reviews with their own integer-ms evaluators (validated on 47 golden cases): FAIL (three BLOCKERS: "no robot fault can violate count or sys" false for a dispenser-node target; the `dispenser_bounce` HOLD row false in both directions with `resp` and `int` missing; the parameter sheet misread WS04-T07), fix round 1 (`9eedf5f`), PASS (no BLOCKER; FX-1 to FX-16 and CAS-1 to CAS-5 VERIFIED; 251 backtick identifiers checked against the contract, no invented name; time-fault conditions confirmed on 400000 random cases).
- Deviations from the task text: the parameter sheet also uses unit types mmHg, m and rad (no values); contract gaps and open points sit as H3 subsections inside `## Traceability` to keep exactly ten H2 headings; the vocabulary section lists only the 17 id bullets; the effects section is larger than the task's table (mechanism classes, footprint table, FX and CAS) because the rigour rule required it.
- Dependents: WS02-T03 (needs WS02-T02 too) and WS04-T07 (needs WS04-T06 and WS02-T03 too) stay `blocked`. Assumptions of four downstream tasks no longer hold or are ambiguous and were flagged (notes in their files, kept `blocked`): WS04-T07 (`InjectionSpec` fields, `nav_delay` per tick, `cuff_detached` events, `dispenser_bounce` reach), WS07-T05 (`magnitude.<key>` mapping, missing injectors, node faults reaching `count`), WS02-T03 (`timestamp_implausible` from non-monotonic time versus the reorder bound), WS02-T05 (DX-03). No ADR was needed.
- Open MINOR (apply at the next touch or when the owning task runs): (1) "silent within `skew_max`" and "within `skew_max` the input is accepted" (lines ~125, ~137, ~314) are over-broad: the reorder bound is independent of `skew_max`; a device behind by 120000 with D 30000 is late even within a `skew_max` of 180000 (FX-4 (c) is that case); (2) "within the bound ... raise no evidence" (lines ~123, ~288, ~407) conflicts with the table: `link_delay` lists `qos_deadline_missed` without its condition, `out_of_order` also makes `seq` non-monotone (`seq_gap_or_replay`), and the "beyond the bound only" entries are conditional by the column's own definition; (3) the `uncommanded_lifecycle_transition` row omits `system.qos_deadline_missed` (condition LC) which `process_kill` carries; (4) FX-11 "the day-end instance is the only COUNT instance affected" is over-broad: the trailing counter carries a lost dispense into the next day's limit margin (0 to +1) and can mask a later limit violation; (5) OP-12 and lines ~222 and ~235 read a bounce-induced INT violation as integrity evidence, but a bounce raises no evidence field, so the violated INT carries provenance only, which is context and never sufficient (WS02-T04 line 40), and the glossary reserves "integrity violation" for C3; (6) "over-stated by the offset rounded to whole steps" (line ~243) is imprecise (floor or ceil of offset / T_s depending on phase; exact for multiples of T_s regardless of phase); (7) the `provenance.template_kind` column for `process_kill` and `uncommanded_lifecycle_transition` lists only `count`; (8) "VIOLATED at `k_d`, whatever `pre_i`" (lines ~190, ~216) is false for a low pre-dose value (RESP is VIOLATED at `k_a` with [-inf, -5]); (9) "offset 0 gives the real verdict" assumes no `bp` sample in the gap `(t, t + gap]`; (10) "VIOLATED at `k_d`" assumes `k_d <= K` (T05 section 3.3); (11) line ~125 has the wrong sign (`t_rx_ms - t_device_ms` shifts by minus the offset); (12) line ~196 says "no `auth` Event" but `auth` is a `Sample` (CG-5) and line ~366 writes "a C2 violation", which the glossary forbids.
- Risks: effects are stated only where a mechanism and a check exist ("no row" means no derived mechanism, not "cannot"); several effects depend on INT being decided at the dispense step with a backward window (ADR-026, proposed); injection parameter names have no value and two consumers with different formats until OP-13 is reconciled.
