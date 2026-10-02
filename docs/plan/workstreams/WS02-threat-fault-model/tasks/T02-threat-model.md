---
id: WS02-T02
title: "Threat model: attacker capabilities, attack classes, exclusions"
workstream: WS02-threat-fault-model
owner: agent
status: done
depends_on: ["WS01-T01"]
critical_path: true
non_negotiable: false
estimate_pd: 1.5
sources: ["analisi §3.6", "analisi §4.5", "analisi §10", "analisi §4.8", "analisi §5.1 (C3 injections)", "analisi §4.9 (2)"]
interfaces: ["02-interfaces.md#evidencevector"]
review_items: ["R2-W7"]
---
## Obiettivo

Write `docs/models/threat-model.md`, the explicit threat model behind class C3, which the plan claims only as "integrity or plausibility violations" against declared attack classes (ADR-002). The document lists the attacker capabilities and exclusions of analisi §4.5, defines two attacker-knowledge levels (naive and informed, analisi §5.1), catalogues the attack classes with the trace changes and `EvidenceVector` footprint each one leaves, and states the non-claims: no general adversarial detection, no inference of C3 from low ρ, and no detection of an informed attacker who is coherent on every available channel. It closes R2 weakness 7 (tampering treated as "low confidence", with no adversary model).

## Contesto

Blocked until WS01-T01 is done; its output fixes the signal list and the time semantics that attack descriptions refer to.

- `docs/source/analisi.md` §3.6 (risk ALTO, informed attacker), §4.5 (last paragraph: capabilities and exclusions; matrix rows 8, 9, 10), §4.8 (claim reformulations) and §10 (fourth objection).
- `docs/source/analisi.md` §5.1 (3) (C3 injections at two knowledge levels; confounders) and §4.9 item 2 (time as an attack vector).
- `docs/plan/02-interfaces.md#evidencevector` (`crypto_temporal`, `witness`, `cross_device` groups; `None` is never negative).
- `docs/plan/03-decisions.md` ADR-002 (C3 as integrity violations) and ADR-004 (DISPENSE is distinct from INTAKE).
- `docs/source/review.md` R2 weakness 7 and the meta-review sentence on a "fault and attack model".

## File toccati

- `docs/models/threat-model.md` (create; create `docs/models/` if it does not exist, another task may have created it first).

## Test

Document task: verification checks a reviewer can run or inspect.

1. Required H2 headings, in this order: `## Scope and claim`, `## Assets and trust boundaries`, `## Attacker capabilities`, `## Knowledge levels`, `## Subtype vocabulary`, `## Attack classes`, `## Attack-to-evidence table`, `## Exclusions`, `## Non-claims`, `## Attacks that raise no violation`, `## Traceability`.
2. `## Scope and claim` contains the exact phrase "integrity or plausibility violations" and states that C3 is claimed only against the attack classes listed in this document (ADR-002).
3. `## Attacker capabilities` has three in-scope capabilities taken from analisi §4.5: BLE injection and replay without keys; physical access to the dispenser; perception spoofing. Each row has columns: what the attacker can do, what the attacker cannot do, preconditions, trace changes, basis (`source` or `inferred`).
4. `## Exclusions` contains the three analisi exclusions verbatim in meaning: compromised robot, compromised RSM, compromised specification. Any further exclusion (for example key compromise or extraction, compromised back-end or plan authoring, insiders with valid credentials) is marked `inferred` and has a one-line reason.
5. `## Knowledge levels` defines "naive" and "informed" as sets of what the attacker knows (message format; care-plan parameters and schedule; cross-device invariants such as cuff pulse rate versus ECG heart rate; sequence-number and timestamp scheme; authentication scheme but not keys; robot perception model). It states that the informed attacker who is coherent on every available channel is not distinguishable by construction (analisi §4.5 last matrix row) and that this is a declared result, not a defect.
6. `## Subtype vocabulary` lists one identifier per line as `- <id>` with at least: `replay`, `injection_naive`, `injection_informed`, `dispense_forgery`, `presence_spoof` (the injections of analisi §5.1 (3), used by WS04-T08 and WS02-T05), and, marked `inferred` and "modelled, not injected in benchmark v1 unless WS04-T08 decides otherwise": `dispenser_physical_tamper`, `timestamp_manipulation`.
7. `## Non-claims` states in separate sentences: (a) C3 is not inferred from low ρ, noise, distribution shift or faults, which also produce low ρ (R2 weakness 7; ρ answers how confidently the violation is claimed, κ answers why); (b) an authenticated dispense event proves the origin device, not INTAKE and not the actor (physical access defeats authentication; ADR-004); (c) robot presence is not identity (R3 weakness 5); (d) no claim about detecting the informed attacker.
8. `## Attacks that raise no violation` states the assumption that attribution runs only on violated verdicts, so an attack whose injected data satisfies every template raises no alert and is counted by WS08 as an undetected C3 event in the detection metric, not as an attribution error. It names which subtypes can behave this way.
9. Every evidence path in the file is one of the 20 contract fields, written `group.field`: `grep -ohE '\b(provenance|system|signal_quality|cross_device|witness|crypto_temporal)\.[a-z_]+' docs/models/threat-model.md | sort -u | grep -vxE 'provenance\.(violated_template|template_kind)|system\.(node_lifecycle|diagnostics_ok|liveliness_ok|qos_deadline_missed|ble_link_quality|battery_low|nav_task_failed|manip_task_failed)|signal_quality\.(ecg_sqi|ppg_sqi|cuff_error_code)|cross_device\.pulse_vs_ecg_hr_diff|witness\.(robot_present|identity_confirmed|intake_observed)|crypto_temporal\.(authenticated|seq_gap_or_replay|timestamp_implausible)'` prints nothing.
10. `## Attack-to-evidence table` has one row per attack subtype with the paths it perturbs and the analisi matrix row it corresponds to (rows 8, 9, 10 or "none"), and states for the authenticated and the unauthenticated deployment separately (whether a device authenticates messages is a per-device capability; `crypto_temporal.authenticated` is `None` when unsupported).
11. No invented numbers: `grep -nE '[0-9]+ ?(mmHg|ms|min|bpm)' docs/models/threat-model.md | grep -v 'illustrative, unverified'` prints nothing. No literature citation is invented; references such as Halperin et al. named in analisi §3.6 are left to WS03-T04.

## Passi

1. Create `docs/models/` if absent. Read the Contesto sources and the WS01-T01 output.
2. Write `## Scope and claim`: the ADR-002 statement, the renaming from "adversarial tampering" to "integrity or plausibility violations", the rule that a device fault is not a violation of the care plan and an attack is not a fault (boundary by cause).
3. Write `## Assets and trust boundaries`: BLE links from devices to the ward node; the dispenser as a physical asset; the robot perception (RGB-D) and its witness output; timestamps and sequence numbers; the care-plan distribution from the back-end (off the safety-critical path) to the RSM with `CarePlan.signature`; the trusted computing base (robot, RSM, specification), which is outside the attacker's reach by assumption.
4. Write `## Attacker capabilities` and `## Knowledge levels` (checks 3 and 5). State the assumption on keys: attackers hold no keys; an attacker with keys is the compromised-device case and is excluded.
5. Write `## Subtype vocabulary` and `## Attack classes`: one subsection per subtype with mechanism, preconditions, effect on the observed trace in trace-schema terms (which `Sample` or `Event` is forged, replayed, retimed or suppressed), the level (naive or informed) at which WS04-T08 injects it, and whether it can raise a violation. Include `replay` of the previous day's measurements, `injection_naive` (plausible values, incoherent across devices), `injection_informed` (plausible and coherent on every available channel), `dispense_forgery`, `presence_spoof`, and the two modelled-only subtypes.
6. Write `## Attack-to-evidence table` (check 10) and `## Attacks that raise no violation` (check 8).
7. Write `## Exclusions`, `## Non-claims` (checks 4 and 7) and `## Traceability` (analisi §3.6, §4.5, §4.8, §5.1, §10, review item R2-W7, ADR-002 and ADR-004). Record that mitigations outside attribution exist (care-plan signature and versioning; reorder buffer) and are owned by WS05.
8. Run every command of `## Test` and fix until each prints what it should.

## Done when

All of the following, from the repository root:

- `test -f docs/models/threat-model.md`
- `grep -c '^## ' docs/models/threat-model.md` prints at least 11, and the headings of check 1 are present.
- `grep -c 'integrity or plausibility violations' docs/models/threat-model.md` prints at least 1.
- `sed -n '/^## Subtype vocabulary/,/^## A/p' docs/models/threat-model.md | grep -c '^- '` prints at least 7.
- `grep -ci 'compromised robot' docs/models/threat-model.md` prints at least 1, and the same for `compromised RSM` and `compromised specification`.
- The evidence-path check of Test item 9 prints nothing.
- `grep -nE 'T[O]DO|T[B]D|[?]{3}|lore[m]' docs/models/threat-model.md` prints nothing.

## Notes

Written by the worker agent of WS02-T02. Status is left `in_progress` on purpose (the orchestrator sets `done` after review). The work is committed on branch `ws02-t02-threat-model`; nothing is merged and no other task file was changed. Only `docs/models/threat-model.md` and this file were touched.

### Verification (real commands, run from the repository root with `.venv` active)

Scripts are in `/tmp/ws02t02/` (not committed): `check_doc.py` (all eleven checks of the task `## Test`, the Done-when commands, glossary and wording sweeps, programmatic cross-checks of every contract name, golden id, fault-model reference, bib key, hypothesis and TX/TM label), `sem2.py` (an integer-millisecond evaluator: the instance semantics of T02 section 1.5 and T05 section 3.5 at the decision step, plus the acceptance rules of T01 sections 3.4 and 4.2 to 4.4), `test_golden.py` (validation of the evaluator on the golden files), `test_tx.py` (the worked checks TX-1 to TX-9). Before the document existed `check_doc.py` printed `FAIL doc exists` and exited 1; on an empty file (`# x`) it gave `SUMMARY: 17 passed, 37 failed of 54` and exit 1; after the document, all 64 checks pass.

The evaluator was written for this task from the merged documents, so it is not an independent implementation of the monitor. It was validated first on 46 golden and worked cases (all 26 cases of `templates.yaml`, the `V-` cases that it covers, FX-3 and FX-4 of `fault-model.md`, W6 and the duplicate and multiplicity rules of T01 section 3.4); while the checks were written it caught errors in my own hand derivations (a presence sample placed after the dispense in two checks, wrong `seq` bookkeeping in two fixtures), which were corrected before the numbers entered the document. Some checks derive a statement from the definition of two signatures or of the schema (TX-3, TX-5 (c), TX-8 (c)) and some set an input from a hypothesis (the tag state in TX-9); the document marks them and none is an independent test.

Done-when commands (output of the run, exit codes as shown):

```
== Done-when 1: test -f docs/models/threat-model.md
exit=0
== Done-when 2: grep -c '^## '
11
exit=0
17:## Scope and claim
27:## Assets and trust boundaries
40:## Attacker capabilities
83:## Knowledge levels
118:## Subtype vocabulary
142:## Attack classes
310:## Attack-to-evidence table
344:## Exclusions
365:## Non-claims
378:## Attacks that raise no violation
396:## Traceability
== Done-when 3: grep -c 'integrity or plausibility violations'
4
exit=0
== Done-when 4: sed vocabulary count
7
exit=0
== Done-when 5: compromised robot / RSM / specification (grep -ci)
compromised robot: 3
compromised RSM: 3
compromised specification: 3
== Done-when 6 / Test 9: evidence-path check
grep-v exit=1 (1 = printed nothing)
== Done-when 7: forbidden tokens
exit=1 (1 = printed nothing)
== Test 11: numbers with units
grep-v exit=1 (1 = printed nothing)
== WS02 README check 7: glossary sweep
exit=1 (1 = printed nothing)
```

Test checks 1 to 11 and the extra checks of `check_doc.py` (exit 0):

```
PASS T1 headings: required H2 in order
PASS T1b at least 11 H2
PASS T2 exact phrase in Scope and claim
PASS T2b claimed only against listed classes + ADR-002
PASS T2c phrase appears in doc and never as claim of tampering in general
PASS T3 capability table with required columns
PASS T3b exactly three capability rows
PASS T3c basis column is source or inferred
PASS T3d three capabilities named
PASS T3e basis of the three is source
PASS T3f keys assumption stated
PASS T4 three analisi exclusions
PASS T4b exclusion table
PASS T4c three source exclusions
PASS T4d every further exclusion is inferred and has a reason
PASS T4e inferred exclusions cover keys, back-end/plan authoring, insiders
PASS T5 knowledge items named
PASS T5b naive and informed defined
PASS T5c by construction + declared result
PASS T5d four flags of WS04-T08 named
PASS T5e analisi last matrix row cited
PASS T6 vocabulary base + inferred ids
PASS T6b only identifier bullets, no duplicates, none from the C2 vocabulary
PASS T6c done-when sed count >= 7
PASS T6d inferred ids marked inferred and "modelled, not injected in benchmark v1 unless WS04-T08 decides otherwise"
PASS T6e vocabulary table covers every id
PASS T7a no C3 from low rho
PASS T7b authenticated dispense proves origin device, not INTAKE, not actor
PASS T7c presence is not identity R3 weakness 5
PASS T7d no claim about informed attacker
PASS T7e no general adversarial detection
PASS T7f provenance alone never sufficient
PASS T8 assumption attribution runs only on violated verdicts
PASS T8b names subtypes
PASS T9 evidence-path check prints nothing
PASS T9b every path used is a contract field (python)
PASS T9c raised/perturbed paths include the three crypto, pulse, witness fields
PASS T10 table with subtype column
PASS T10b one row per subtype
PASS T10c matrix row column with 8/9/10/none
PASS T10d separate unauthenticated and authenticated columns
PASS T10e `crypto_temporal.authenticated` is None when unsupported is stated
PASS T11 no unlabeled numbers with units
PASS T11b no invented citations (author-year patterns)
PASS DW grep -c "^## " >= 11
PASS DW grep -ci compromised robot
PASS DW grep -ci compromised RSM
PASS DW grep -ci compromised specification
PASS DW forbidden tokens none
PASS W1 forbidden wording absent
PASS W2 no "C2 violation"/"C3 violation" phrasing
PASS W3 ADR-002 and ADR-004 and ADR-010 cited
PASS W4 no "clinical validation" claim; pre-clinical stated
PASS W5 no unqualified "tampering in general" claim (only negated)
PASS B1 bib keys named exist
PASS B2 ref-needed marker used for unverified references
PASS X1 fault-model OP-n and FM-GAP-* and CG-n references exist
PASS X2 golden ids referenced exist
PASS X3 EventKind names used exist
PASS X4 SignalId used exist (sanity)
PASS X5 every TM-GAP used is defined and every defined one is used outside its definition
PASS X6 every TM-OP used is defined and used
PASS X7 TX-n referenced are defined; defined are referenced
PASS X8 WS04-T08 subtype names covered
SUMMARY: 64 passed, 0 failed of 64
```

Full suite: `pytest -q` printed `175 passed in 0.85s` (exit 0); `python3 tools/check_plan.py` printed `check_plan: OK (103 tasks, 18 contracts, 31 findings)` (exit 0).

Evaluator validation (`python3 /tmp/ws02t02/test_golden.py`):

```
PASS G-RANGE-1 
PASS G-RANGE-2 
PASS G-RANGE-3 
PASS G-RANGE-4 
PASS G-RANGE-5 
PASS G-COUNT-1 
PASS G-COUNT-2 
PASS G-COUNT-3 
PASS G-HOLD-1 
PASS G-HOLD-2 
PASS G-HOLD-3 
PASS G-HOLD-4 
PASS G-RESP-1 
PASS G-RESP-2 
PASS G-RESP-3 
PASS G-RESP-4 
PASS G-SCHED-1 
PASS G-SCHED-2 
PASS G-SCHED-3 state at k_d is VIOLATED (decided), graded value read at eval_at_ms 
PASS G-SCHED-4 
PASS G-SYS-1 
PASS G-SYS-2 
PASS G-SYS-3 
PASS G-INT-1 
PASS G-INT-2 
PASS G-INT-3 
PASS V-SCHED-3 
PASS V-SCHED-4 
PASS V-RESP-4 
PASS V-RESP-5 
PASS V-RESP-6 
PASS V-COUNT-1 
PASS V-COUNT-2 
PASS V-COUNT-4 
PASS V-INT-1 
PASS V-INT-2 
PASS V-INT-3 
PASS V-LATE-1 
PASS V-LATE-2 
PASS FX-3 arrival at the watermark is on time (V-LATE-2 slack 0) 
PASS FX-3 arrival one ms after the watermark is late 
PASS FX-4 (a) stamped two steps ahead, accepted, visible after the deadline: VIOLATED, nothing counted 
PASS FX-4 (b) future-stamped beyond skew_max: not used, counted 
PASS W6 trailing count 3 
PASS T01 3.4 duplicate (source, seq) not counted 
PASS T01 3.4 seq None: both counted (W3 multiplicity: two in one step count two) 
golden/evaluator self-check: 46 passed, 0 failed of 46
test_golden exit=0
```

Worked checks (`python3 /tmp/ws02t02/test_tx.py`):

```
PASS TX-1a naive replay with the genuine reading suppressed: SCHED VIOLATED no_measurement_after_tick
PASS TX-1a replayed Sample and Event are late (two inputs counted) and duplicates of accepted (source, name, seq)
PASS TX-1a no RANGE instance: the replayed Event is not accepted
PASS TX-1b replay without suppression: SCHED SATISFIED slack 1500000, evidence raised but no violation
PASS TX-1 evidence reading: timestamp_implausible True, seq_gap_or_replay True (naive replay, U)
PASS TX-1 without the previous-day seq state only the timestamp evidence remains
PASS TX-1 device without seq: seq_gap_or_replay is None (channel unavailable, not negative)
PASS TX-1c a loss (seq 22 missing) with a late input (seq 24 arrives late) gives timestamp True and seq True, as the naive replay does
PASS TX-2 genuine 152 RANGE VIOLATED -12 (G-RANGE-2); replayed 128 RANGE SATISFIED +12: a latent violation is masked
PASS TX-2 SCHED slack identical for the replay and the genuine reading (1500000)
PASS TX-2 informed replay with fresh metadata: no crypto_temporal evidence; unpatched replayed pulse (64 against ECG 80) exceeds a fixture tolerance (5)
PASS TX-2 informed replay with the pulse patched: every evidence reading is False (nothing raised)
PASS TX-2 reverse direction: the replayed 152 gives RANGE VIOLATED -12 where the latent reading 125 gives +15 (G-RANGE-1)
PASS TX-2c informed replay of the whole group (cuff_health 1.0, inflation 45000): SYS SATISFIED +15000 (G-SYS-1 arithmetic)
PASS TX-2c the same forged measurement without its group, with an earlier genuine group held: SYS reads the held values, SATISFIED +15000
PASS TX-2c with no earlier group: SYS PENDING with value_undefined:cuff_health and value_undefined:inflation_ms (T05 3.5)
PASS TX-2c a forged group that reports an unhealthy cuff: SYS VIOLATED with cuff_unhealthy (G-SYS-3)
PASS TX-3 genuine non-response 145 -> RESP VIOLATED -5 (G-RESP-2); forged in-range 138 -> SATISFIED +2 (G-RESP-3): non-response hidden
PASS TX-3 genuine response 132 -> +8 (G-RESP-1); forged 150 (inside the patient own range) -> VIOLATED -10: an apparent non-response
PASS TX-3 informed injection of 150 and the C2 fault stuck_at (frozen 150, FX-7), each built from its own signature on the same genuine day, give equal observed Samples and Events and the same RESP record
PASS TX-3 informed series equal to latent plus the bias (137) and cuff_silent_bias (offset 5), each from its own signature on the same genuine day (bp Samples, Events, t, seq, quality): equal, same RESP record (+3)
PASS TX-3 a forged 150 also violates RANGE (-10): inside the patient own range does not mean inside the band
PASS TX-4a forged unscheduled dispense at 21:02: COUNT limit VIOLATED -1 (G-COUNT-1 arithmetic)
PASS TX-4b day with the 07:00 dose only: day-end COUNT VIOLATED -1 (G-COUNT-3); a forged dispense at the scheduled 21:00 makes it SATISFIED 0: a missed dose is masked
PASS TX-4c robot co-located, presence 0 held, no auth: INT VIOLATED no_witness (V-INT-3)
PASS TX-4c robot not co-located (presence unavailable), no auth: INT PENDING with a marker, not VIOLATED (V-INT-1)
PASS TX-4c informed forgery with a spoofed presence at 20:58: INT SATISFIED 180000 (G-INT-1 arithmetic)
PASS TX-4d forged 21:00 dispense, no real dose: reading 148 at 22:30 gives RESP VIOLATED -8 at Delta2; a reading 135 gives SATISFIED +5 (the pressure fell anyway): both depend on the latent pressure only
PASS TX-4e forged dispense while the last reading is 94: HOLD VIOLATED -6 (G-HOLD-2): a violation raised by a dose that was never released
PASS TX-5a verbatim copy of the 21:00 DISPENSE with the same seq: on time, a duplicate, not counted (count 2, margin 0, SATISFIED), one repeat flagged
PASS TX-5b the same verbatim copy from a device without seq: on time, counted (count 3 at the step), the COUNT instance of the real 21:00 dispense is VIOLATED -1 too, nothing flagged, nothing late
PASS TX-5c a re-stamped copy (t_device = t_rx) from a device without seq and a dispenser_bounce event are the same Event field for field; the verbatim copy of (b) differs in t_device_ms (equal to the original), a cue that the policy of T01 3.4 does not use
PASS TX-5d the verbatim copy arrives within D of its own step, so it is on time
PASS TX-5e an inserted DISPENSE that takes seq 7 makes the device own next DISPENSE (23:00, seq 7) a duplicate: flagged and not counted (T01 3.4); count at 23:01 is 3 instead of 3 genuine plus the inserted one = 4
PASS TX-6a presence_spoof alone (no dispense, nothing else) changes no template instance: no INT instance exists without a DISPENSE anchor
PASS TX-6b property: adding presence=1 samples never lowers the INT interval and never turns a non-VIOLATED INT into VIOLATED (4000 seeded draws, 972 verdict changes, all upward)
PASS TX-6c spoofed presence turns the V-INT-3 verdict VIOLATED into SATISFIED (180000)
PASS TX-6d spoofed INTAKE Event two steps before the dispense: INT SATISFIED 180000
PASS TX-6e robot not co-located: both witness channels unavailable, no spoofed value can enter (hypothesis); INT stays PENDING with both markers
PASS TX-7a authenticated extra release at 14:00, robot co-located and presence 0: INT SATISFIED 300000 (V-INT-2 arithmetic): the authenticated event satisfies INT whatever the witness says
PASS TX-7b the same release on a device that does not authenticate: INT VIOLATED no_witness
PASS TX-7c COUNT: the 14:00 instance is SATISFIED at margin 0, the later genuine 21:00 instance is VIOLATED -1 (three dispenses in the trailing day)
PASS TX-8a measurement taken at 09:29:00 relayed with t_device 09:31:00, skew bound 180000: accepted, SCHED(09:00) VIOLATED, nothing counted (FX-4 (a))
PASS TX-8b with a skew bound of 60000 the same stamp is future-stamped: not used, counted (FX-4 (b))
PASS TX-8c a genuine message relayed late by an attacker (V-LATE-1) and the same message delayed by a link fault (link_delay) are the same Event: late, counted, SCHED VIOLATED
PASS TX-8d a delay up to the bound plus the phase term is silent (V-LATE-2): accepted, SATISFIED 0, nothing counted
TX-9  ('replay', 'naive', False) -> ['seq_gap_or_replay', 'timestamp_implausible'] {'authenticated': None, 'pulse_vs_ecg_hr_diff': None}
TX-9  ('replay', 'naive', True) -> ['authenticated', 'seq_gap_or_replay', 'timestamp_implausible'] {'pulse_vs_ecg_hr_diff': None}
TX-9  ('replay', 'informed', False) -> [] {'authenticated': None}
TX-9  ('replay', 'informed', True) -> [] {}
TX-9  ('injection', 'naive', False) -> ['pulse_vs_ecg_hr_diff', 'seq_gap_or_replay'] {'authenticated': None}
TX-9  ('injection', 'naive', True) -> ['pulse_vs_ecg_hr_diff', 'seq_gap_or_replay'] {}
TX-9  ('injection', 'informed', False) -> [] {'authenticated': None}
TX-9  ('injection', 'informed', True) -> [] {}
TX-9  ('dispense_forgery', 'naive', False) -> ['seq_gap_or_replay'] {'authenticated': None, 'pulse_vs_ecg_hr_diff': None}
TX-9  ('dispense_forgery', 'naive', True) -> ['seq_gap_or_replay'] {'pulse_vs_ecg_hr_diff': None}
TX-9  ('dispense_forgery', 'informed', False) -> [] {'authenticated': None, 'pulse_vs_ecg_hr_diff': None}
TX-9  ('dispense_forgery', 'informed', True) -> [] {'pulse_vs_ecg_hr_diff': None}
TX-9  ('presence_spoof', 'naive', False) -> [] {'authenticated': None, 'pulse_vs_ecg_hr_diff': None}
TX-9  ('presence_spoof', 'naive', True) -> [] {'authenticated': None, 'pulse_vs_ecg_hr_diff': None}
TX-9  ('presence_spoof', 'informed', False) -> [] {'authenticated': None, 'pulse_vs_ecg_hr_diff': None}
TX-9  ('presence_spoof', 'informed', True) -> [] {'authenticated': None, 'pulse_vs_ecg_hr_diff': None}
TX-9  ('physical', 'naive', False) -> [] {'authenticated': None, 'pulse_vs_ecg_hr_diff': None}
TX-9  ('physical', 'naive', True) -> ['authenticated'] {'pulse_vs_ecg_hr_diff': None}
TX-9  ('physical', 'informed', False) -> [] {'authenticated': None, 'pulse_vs_ecg_hr_diff': None}
TX-9  ('physical', 'informed', True) -> ['authenticated'] {'pulse_vs_ecg_hr_diff': None}
TX-9  ('timestamp', 'naive', False) -> ['timestamp_implausible'] {'authenticated': None, 'pulse_vs_ecg_hr_diff': None}
TX-9  ('timestamp', 'naive', True) -> ['timestamp_implausible'] {'pulse_vs_ecg_hr_diff': None}
TX-9  ('timestamp', 'informed', False) -> [] {'authenticated': None, 'pulse_vs_ecg_hr_diff': None}
TX-9  ('timestamp', 'informed', True) -> [] {'pulse_vs_ecg_hr_diff': None}
PASS TX-9 footprint ('replay', 'naive', False): ['seq_gap_or_replay', 'timestamp_implausible']
PASS TX-9 footprint ('replay', 'naive', True): ['seq_gap_or_replay', 'timestamp_implausible']
PASS TX-9 footprint ('replay', 'informed', False): []
PASS TX-9 footprint ('replay', 'informed', True): ['authenticated']
PASS TX-9 footprint ('injection', 'naive', False): ['pulse_vs_ecg_hr_diff', 'seq_gap_or_replay']
PASS TX-9 footprint ('injection', 'naive', True): ['authenticated', 'pulse_vs_ecg_hr_diff', 'seq_gap_or_replay']
PASS TX-9 footprint ('injection', 'informed', False): []
PASS TX-9 footprint ('injection', 'informed', True): ['authenticated']
PASS TX-9 footprint ('dispense_forgery', 'naive', False): ['seq_gap_or_replay']
PASS TX-9 footprint ('dispense_forgery', 'naive', True): ['authenticated', 'seq_gap_or_replay']
PASS TX-9 footprint ('dispense_forgery', 'informed', False): []
PASS TX-9 footprint ('dispense_forgery', 'informed', True): ['authenticated']
PASS TX-9 footprint ('presence_spoof', 'naive', False): []
PASS TX-9 footprint ('presence_spoof', 'naive', True): []
PASS TX-9 footprint ('presence_spoof', 'informed', False): []
PASS TX-9 footprint ('presence_spoof', 'informed', True): []
PASS TX-9 footprint ('physical', 'naive', False): []
PASS TX-9 footprint ('physical', 'naive', True): []
PASS TX-9 footprint ('physical', 'informed', False): []
PASS TX-9 footprint ('physical', 'informed', True): []
PASS TX-9 footprint ('timestamp', 'naive', False): ['timestamp_implausible']
PASS TX-9 footprint ('timestamp', 'naive', True): ['authenticated', 'timestamp_implausible']
PASS TX-9 footprint ('timestamp', 'informed', False): []
PASS TX-9 footprint ('timestamp', 'informed', True): ['authenticated']
worked checks: 70 passed, 0 failed of 70
test_tx exit=0
```

TX-9 lines show, for each scenario, the fields whose reading is True (and the fields that are `None`); in the `A` scenarios the `authenticated` reading is True when no message failed verification, so the adverse reading (False) is the one that the table of the document lists as `auth`.

### Review rounds

The draft was reviewed twice by an independent read-only reviewer (a sub-agent, not the author). Round 1 found no blocker and 7 major findings, all fixed: the evidence-steering path (H-EVID, TM-OP-14), the SYS template and the measurement group (H-GROUP, TX-2 (c)), the relay position that the row-10 result needs (marked `inferred`, stated in the result and in non-claim 4), the sequence-number monotonicity (H-SEQMONO), vacuous or circular checks (relabelled; TX-6 (b) stated as a lemma), TX-9 against the witness fields (caption), and the over-broad equality of an informed injection with the C2 silent faults (restricted, TX-3). Round 1 also gave 19 minor findings (a fixture inconsistency in TX-2, the `seq` numbers of TX-5 (e), cross-references, guard against marker, `if present` for the plan signature, extra exclusions, and others), all fixed. Round 2 found no blocker and 4 major findings, fixed: the TX-3 equality (now restricted to the `bp` Samples, Events, timing, `seq` and `quality`, with an offset inside the assumed range, and `hr_pulse` excluded under H-TOL), row 8 under authentication (only the informed, rewritten replay is distinguishable), the benign verification failure (H-AUTHCAUSE, TM-OP-15) and missing hypotheses in four A-column claims; and 12 minor findings, fixed.

### Deviations from the task text

- None of the Passi was skipped. The additions are those the constraints asked for (`TM-GAP-*` labels, open points) and sub-sections under existing H2 headings: `### Time as an attack vector and the C2 time faults`, `### The C1, C2 and C3 boundary`, `### Worked checks (fixture-only)` and `### TX-1` to `### TX-9` under `## Attack classes`, and `### Contract gaps` and `### Open points` under `## Traceability`. No extra H2 heading.
- Basis column of the capability table: the three capabilities are `source`. The sub-capabilities that the benchmark and the informed result need (a relay position: suppression, delay, renumbering; passive capture) are listed as `inferred` below the table, because analisi §4.5 names only "injection and replay without keys".
- The task text asks for `## Knowledge levels` to define the levels as sets of knowledge items, and WS04-T08 test 1 expects four flags: the four flags are given in a second table with the mapping from the knowledge items (TM-OP-1).

### Contract gaps found (not changed here)

- TM-GAP-AUTH: no per-message verification outcome in `Sample`, `Event` or `EventKind`, and no definition of the adverse value of `crypto_temporal.authenticated`.
- TM-GAP-SEQ: one Boolean for a repeat (replay) and a gap (loss); the same gap as FM-GAP-SEQ.
- TM-GAP-SEQKEY: a `Sample` has `seq` but no `source`, whereas T01 section 3.4 states the duplicate rule for events by `(source, seq)`.
- TM-GAP-TIME: one Boolean for late, future-stamped and replay-related inputs, no clock health (the CG-10 gap).
- TM-GAP-HIST: no previous-day history for the day-by-day run and no definition of a negative `TimeMs` (T01 CG-11), both needed by a previous-day replay.

### Open points (TM-OP-1 to TM-OP-15, in the document)

TM-OP-1 knowledge items without a flag in WS04-T08; TM-OP-2 WS04-T08 test 2 against test 4 (a stale-stamped replay is late and not accepted); TM-OP-3 gateway policy flag or drop; TM-OP-4 sequence state across days and the order of the duplicate and late checks; TM-OP-5 authentication in the confounder pairs of WS04-T09; TM-OP-6 the simulation injects no C3; TM-OP-7 informed forgery of an extra event needs renumbering; TM-OP-8 per-device authentication and the `expected_undetectable` tag; TM-OP-9 INT form (ADR-026); TM-OP-10 `auth` masks the witness in INT; TM-OP-11 row 10 per deployment; TM-OP-12 cross-device evidence and the hierarchy; TM-OP-13 witness quality; TM-OP-14 evidence steering; TM-OP-15 benign verification failure and PENDING instances.

### Consumer consistency (task files quoted, none edited)

- WS04-T08: the five subtype names (test 12, README) and the four flags (test 1) are used verbatim; test 10 (empty signature without authentication, exactly `crypto_temporal.authenticated` with it) agrees with TX-9 under the policy "flag", which the task does not state. Mismatches disclosed: test 2 against test 4 (TM-OP-2), knowledge items without a flag and the mapping of the flags (TM-OP-1), one `auth_deployed` against per-device authentication and the `expected_undetectable` tag, which holds only for an empty signature (TM-OP-8), and the informed forgery of an extra event (TM-OP-7).
- WS04-T09: tests 14 and 15 agree in the unauthenticated deployment and with `spoof_intake`; in the authenticated deployment the synthesised forgery has no valid tag (TM-OP-5).
- WS02-T03: decisions D-3 and G-6 are the gaps TM-GAP-SEQ and TM-GAP-TIME; the evidence derivations of its step 4 (`Sample.quality`, DEVICE_ERROR, NODE_STATE) are attacker-writable in the unauthenticated deployment (TM-OP-14).
- WS02-T04: the rule that provenance alone is not enough (its line 40) is non-claim 6; TM-OP-12 and TM-OP-15 are decisions for it.
- WS02-T05: the rows for `injection_naive`, `presence_spoof`, `dispenser_physical_tamper` and `timestamp_manipulation` follow the diagnosability readings of the classes; its DX-10 expected κ holds for the unauthenticated deployment (TM-OP-11).
- WS07-T03 and WS07-T05: no verification outcome and no C3 injector (TM-OP-6); the oracle note of WS07-T05 about a replay raising a sequence gap is reconciled in the Traceability section (a replay raises a repeat of a number; the Boolean is the same).

### Post-task review

- Produced: `docs/models/threat-model.md` (eleven sections: scope and claim, assets and trust boundaries, attacker capabilities (three sourced, the rest labelled `inferred`), knowledge levels (naive and informed with the four WS04-T08 flags), seven attack-class subtypes, attack classes with worked checks TX-1 to TX-9, an attack-to-evidence table over unauthenticated and authenticated deployments, the three source exclusions plus nine inferred, ten non-claims, attacks that raise no violation, traceability with contract gaps `TM-GAP-*` and open points TM-OP-1 to TM-OP-15; fifteen named hypotheses H-*). Orchestrator re-ran the "Done when" block (11 headings, "integrity or plausibility violations" four times, 7 subtypes, exclusions, empty token and numbers-with-units greps, exit 0), a scan for operational detail (only the document's own disclaimer matches), the full suite (175 tests) and `check_plan` (exit 0). Independent review with its own integer-ms evaluator (validated on 39 golden checks): PASS, no BLOCKER; TX-1 to TX-9 VERIFIED (TX-6 on 20000 random draws, 8567 changed verdicts, none downward); all 20 `EvidenceVector` fields exact; no operational content.
- Deviations from the task text: the three capabilities are the sourced ones (`injection and replay without keys`); relay position and passive capture are `inferred`; the four WS04-T08 flags sit in a second table inside `## Knowledge levels`; only H3 sub-sections were added (time versus C2, the C1/C2/C3 boundary, TX-1 to TX-9, gaps and open points).
- Dependents: WS02-T03 (its dependencies WS02-T01 and WS02-T02 are done) is now `ready`; it carries the earlier flag about `timestamp_implausible` from non-monotonic time and must also decide `seq_gap_or_replay` for out-of-order input. WS04-T08 (needs WS04-T06 too) stays `blocked`. WS02-T05 stays `blocked`; two mismatches of its DX-08 and DX-09 were not disclosed in the document and were flagged here.
- Open MINOR (the first five are over-broad statements of the kind earlier tasks failed on; apply at the next touch): (M1) a forged `auth` Sample is never considered: `SignalId.AUTH` travels as a `Sample` (CG-5), so a keyless injector can write `presence` 0 plus `auth` 1.0 at the dispense step and make INT SATISFIED at 300000 (same arithmetic as V-INT-2) with nothing flagged in an unauthenticated deployment; the INT claims (lines ~192 to 201, ~329) rest on the unstated hypothesis that `auth` is written only by a verified message: add a hypothesis and an open point; (M2) "separable only through `seq`" (line ~242, overlap row 1) is refuted by `system.qos_deadline_missed` (conditional, derived from arrival-period gaps): a replay at nominal arrival times leaves no gap, so qualify with "when no deadline is declared"; (M3) the "raises no violation when" conditions (lines ~386 to 389) omit `resp` for `injection_naive` and the informed `replay` (pre-dose 130, forged 128 at 08:30 gives RANGE +12, HOLD +30, SYS +15000 but RESP -8), and `dispense_forgery` (line ~193) omits the guard routes (HOLD `no_recent_measurement`, RESP `obligation_unmet`); (M4) the `dispense_forgery` table cells are inconsistent with TX-9 and the class text (line ~319 lists only `seq_gap_or_replay` for U naive, omits `timestamp_implausible`; A synthesised omits `seq_gap_or_replay`; line ~312 promises the union over the levels); (M5) `dispenser_physical_tamper` (line ~321: "`int` violated in U, satisfied in A" without the condition "robot co-located and nobody seen"; a tamperer seen by the robot gives INT SATISFIED in U) and line ~223 ("only a co-located robot that checks identity can contradict it" contradicts line ~220, which lists `witness.robot_present` and `witness.intake_observed` reading False); (M6) the "partial" verdict for a verbatim naive replay in A deviates from analisi §4.5 row 8 ("yes with authentication; partial without") without saying so (lines ~158, ~160, ~328); (M7) the equalities of TX-3 and TX-5 (c) need the hypothesis `t_device_ms == t_rx_ms` for the forged or re-stamped message (no nominal transport delay, or the attacker copies the true stamp). Also: `hr_coherence_tolerance` does not exist in the repository (offered as a proposal); WS02-T04 test 3 already fixes the cross-device explained-away rule and TM-OP-12 does not cite it.
- Risks: the row-10 result (an informed attacker coherent on every available channel is undetectable by construction) assumes a relay position, which is `inferred` and stronger than analisi's wording; an add-only attacker is "not covered"; the A-column claims about `crypto_temporal.authenticated` rest on H-KEY, H-TAG, H-GW, H-AUTHCAUSE and on `TM-GAP-AUTH` (the contract defines no adverse value), not on a computation; INT statements use the reference form of INT and so depend on ADR-026 (proposed).
