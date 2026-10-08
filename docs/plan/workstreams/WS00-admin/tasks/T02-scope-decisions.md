---
id: WS00-T02
title: "Scope decisions: one pathology, C3 as integrity violations, distributed architecture"
workstream: WS00-admin
owner: human
status: done
depends_on: ["WS00-T01"]
critical_path: true
non_negotiable: false
estimate_pd: 2.5
sources: ["analisi §9 (0.2)", "analisi §3.6", "analisi §4.5", "analisi §4.9 (1)", "analisi §10"]
interfaces: []
review_items: ["R3-W2", "R2-W7"]
---
## Obiettivo

Take and record the three scope decisions of analisi §9 item 0.2, which are already written as ADR-001 (one main pathology, hypertension, with pre-clinical technical validation), ADR-002 (class C3 reduced to integrity or plausibility violations, with a threat model) and ADR-003 (distributed architecture: ward node plus robot), and confirm or overturn every ADR in status `proposed` from ADR-011 to ADR-017. Concrete output: `docs/plan/workstreams/WS00-admin/outputs/WS00-T02.md` plus updated status lines in `docs/plan/03-decisions.md`. Adopting ADR-003 is the decision that answers R3-W2 (what happens when the robot leaves the room or fails) and adopting ADR-002 is the decision behind R2-W7 (tampering read as low confidence); their technical closure sits in WS05-T09, WS07-T04, WS08-T04 and WS02-T02. This task is on the critical path: WS01-T01 and WS12-T01 wait for it.

## Contesto

- `docs/plan/03-decisions.md`: ADR-001, ADR-002, ADR-003 and ADR-011 to ADR-017 (the text to confirm).
- `docs/source/analisi.md` §9 row 0.2, §3.6 and §4.5 (C3, threat model, undetectable cases), §4.9 item 1 (distributed architecture), §10 objections 1 and 4 (pre-clinical statement; informed attacker).
- `docs/source/review.md`: R3 weakness 2 (robot structural flaw) and R2 weakness 7 (tampering as low confidence).
- `docs/plan/workstreams/WS00-admin/outputs/WS00-T01.md` (deadline, page limit, prior-publication rules that constrain scope).
- `docs/plan/01-conventions.md` section 6 (a change to a contract needs an ADR).

Blocked until WS00-T01 is done, that is until `outputs/WS00-T01.md` exists with its nine fields.

## File toccati

- `docs/plan/workstreams/WS00-admin/outputs/WS00-T02.md` (create)
- `docs/plan/03-decisions.md` (modify: status lines of ADR-001 to ADR-003 and ADR-012 to ADR-017; new superseding ADRs only for overturned decisions)
- `docs/plan/02-interfaces.md` (modify only if ADR-016 or ADR-017 is overturned, to bump the version of the affected contracts as the superseding ADR states)

## Test

Verification checks:

1. The artefact starts with `completed_by:` and `completed_on:` lines and contains the seven H2 fields of Done when, each non-empty.
2. `## ADR-001 scope` states: outcome (confirmed, amended or overturned), the main pathology, the validation type (semi-synthetic benchmark, ROS 2 simulation, optional mock-ward demo, no real patients), and the exact sentence that will appear in the abstract, the introduction and the limitations (analisi §10 objection 1).
3. `## ADR-002 C3 integrity` states: outcome; the name of class C3 as it will appear in the paper; the declared attack classes (BLE injection and replay without keys, physical access to the dispenser, perception spoofing) as confirmed or amended; the exclusions (compromised robot, compromised RSM, compromised specification); the two attacker-knowledge levels (naive and informed); and the commitment to report the undetectable cases as a result.
4. `## ADR-003 distributed architecture` states: outcome; the placement (fixed ward node with BLE gateway and RSM for continuous φ_CP monitoring; robot running the embodied specifications and providing evidence); the heartbeat and watchdog; the fallback escalation to the nurse; and the sentence that answers "what does the robot add".
5. `## ADR-011 to ADR-017` has one row per ADR (seven rows). Each row has an outcome: `confirmed` or `overturned`; for ADR-011 only, `delegated to WS00-T05` is also accepted because T05 decides it. An overturned row names the superseding ADR.
6. In `docs/plan/03-decisions.md` no heading of ADR-012 to ADR-017 still ends with the confirmation tag, and each of those ADRs has status `accepted` with a confirmation note, or `superseded by ADR-0NN`.
7. Each superseding ADR has context, decision, alternatives, consequences and status. For a superseded ADR-016 or ADR-017 it also states the old version, the new version, the affected tasks and the migration (`01-conventions.md` section 6).
8. `## Constraints from WS00-T01` shows that the scope is compatible with the page limit, the deadline and the prior-publication rules recorded in T01, or lists the conflict and the cut proposed (`00-master-plan.md` section 7).
9. Decision-makers are named and dated in `## Decision-makers and date`; at least one person named is an author of the workshop paper.

## Passi

1. Read `outputs/WS00-T01.md` and write `## Constraints from WS00-T01`: weeks available against the 14 to 16 weeks of analisi §9, page limit, prior-publication rules, and any conflict with the three ADRs.
2. Hold the decision meeting with the co-authors. Record in `## Decision-makers and date` who took part, the date and whether it was a meeting or a message exchange.
3. ADR-001: fill `## ADR-001 scope` (check 2). If the pathology changes, state the consequence for WS04 (which targets hypertension only) and for ADR-019 (second pathology optional).
4. ADR-002: fill `## ADR-002 C3 integrity` (check 3). WS02-T02 turns this into the threat model; do not write the threat model here.
5. ADR-003: fill `## ADR-003 distributed architecture` (check 4). Do not choose message formats here; they belong to `02-interfaces.md#ros-2-interfaces`, owned by WS07.
6. For ADR-011 to ADR-017 answer the question below and record the outcome in `## ADR-011 to ADR-017`, with a one-line reason for each overturned decision:
   - ADR-011 (ROS 2 distribution): decided by WS00-T05; write `delegated to WS00-T05`, or copy its outcome if `outputs/WS00-T05.md` already exists.
   - ADR-012 (source files): is `docs/source/review.md`, an extract of analisi §2, accepted as the reviewer source, or does a separate authoritative review file exist (give its path; the plan maintainer then replaces `review.md` and reruns the verifier)?
   - ADR-013 (RTAMT): is RTAMT accepted as the reference STL tool behind `ralmon.spec` and `ralmon.monitor`, with WS05-T02 deciding after its spike whether a custom monitor replaces it?
   - ADR-014 (placement of §9 items): do items 0.4 and 0.5 (title, abstract without numbers) stay in WS12 as agent tasks, with WS00 holding 0.1, 0.2, 0.3, 0.6, 0.7?
   - ADR-015 (loop script location): will `prompt/run-plan.sh` be copied or symlinked to the repository root together with `PROMPT.md` and `.claude/settings.json`, or run another way? Record the choice.
   - ADR-016 (Python toolchain): are Python 3.11 or newer, pytest, Hypothesis, ruff and mypy strict acceptable for the team's machines? If `outputs/WS00-T05.md` exists, also check the Python version of the chosen ROS 2 distribution.
   - ADR-017 (time unit): is integer milliseconds since trace start accepted for `TimeMs` and `DurationMs`?
7. Edit `docs/plan/03-decisions.md`. For each confirmed ADR, remove the confirmation tag from the heading, and change the status to `accepted` followed by ` (confirmed (WS00-T02, YYYY-MM-DD))` with the real date. For ADR-001 to ADR-003, append the same confirmation note to the existing status. For each overturned ADR, add a new ADR with the next free number and set the old status to `superseded by ADR-0NN (WS00-T02, YYYY-MM-DD)`. If ADR-016 or ADR-017 is overturned, bump the version of the contracts named in the new ADR in `docs/plan/02-interfaces.md` in the same change.
8. Fill `## Open points` (question, owner, date) for anything not settled; do not leave an ADR unresolved to save time.
9. Set `status: done` here and tell the owners of WS01-T01, WS00-T03, WS00-T06 and WS12-T01 that they are unblocked.

## Done when

From the repository root:

- `test -f docs/plan/workstreams/WS00-admin/outputs/WS00-T02.md` exits 0.
- `grep -cE '^## (Decision-makers and date|Constraints from WS00-T01|ADR-001 scope|ADR-002 C3 integrity|ADR-003 distributed architecture|ADR-011 to ADR-017|Open points)$' docs/plan/workstreams/WS00-admin/outputs/WS00-T02.md` prints `7`.
- `grep -cE '^## ADR-01[2-7] .*\[DA-' docs/plan/03-decisions.md` prints `0`.
- `grep -cE '\(WS00-T02, [0-9]{4}-[0-9]{2}-[0-9]{2}\)' docs/plan/03-decisions.md` prints at least `9` (ADR-001, 002, 003 and ADR-012 to ADR-017).
- Inspection: ADR-011 is either resolved by WS00-T05 or listed as `delegated to WS00-T05` in the artefact.

## Notes

### Status update (user attestation)

Marked `done` on 2026-09-30 at the user's explicit instruction ("le task umane iniziali sono tutte eseguite"). The artefact named in "Done when" (`docs/plan/workstreams/WS00-admin/outputs/WS00-T02.md`) was not present in the repository at that time; the agent did not create or reconstruct it. Anything downstream that needs its content will stop and report. `docs/plan/03-decisions.md` still carries `[DA-CONFERMARE]` on ADR-011 to ADR-017 (and 021 to 025), so the Done-when checks on those tags do not hold; the agent did not edit any ADR.

### Artefact recorded (agent, 2026-10-08)

`outputs/WS00-T02.md` was written by the agent from the answers of gab (2026-10-08): ADR-001, ADR-002, ADR-003, ADR-012, ADR-013, ADR-014 (as amended by ADR-037), ADR-015 and ADR-017 confirmed; ADR-011 and ADR-016 superseded by ADR-042 (ROS 2 Humble with Gazebo Classic, Python floor 3.10). The decisions were given in a conversation, not a meeting with the co-authors; check 9 (an author of the workshop paper among the decision-makers) is left as an open point for gab. Done-when checks run on 2026-10-08: the file exists, seven headings, no `[DA-` tag on the ADR-012 to ADR-017 headings, nine `(WS00-T02, 2026-10-08)` notes.
