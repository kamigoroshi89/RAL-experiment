---
id: WS02-T02
title: "Threat model: attacker capabilities, attack classes, exclusions"
workstream: WS02-threat-fault-model
owner: agent
status: ready
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
