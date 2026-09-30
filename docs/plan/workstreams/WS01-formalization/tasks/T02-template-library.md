---
id: WS01-T02
title: Past-time STL template library with units and robot obligations
workstream: WS01-formalization
owner: agent
status: in_progress
depends_on: ["WS01-T01"]
critical_path: true
non_negotiable: true
estimate_pd: 3
sources: ["analisi §4.1", "analisi §4.2", "analisi §2 R1", "analisi §10 (3)", "analisi §5.6 (A7)"]
interfaces: ["02-interfaces.md#template"]
review_items: ["R1-W1", "R1-W3", "R1-W5", "R1-W8"]
---
## Obiettivo

Write `docs/formal/02-templates.md` and `docs/formal/golden/templates.yaml`: the complete past-time STL template library for the running example (hypertension, ADR-001) with, for each of the seven `TemplateId` values, the formula (LaTeX and past-time string), signals, parameters, robustness unit, scale, priority, latency bound and robot obligation, plus 26 hand-computed golden examples that WS05 will reuse as fixtures. This task is non-negotiable (analisi §9). It answers R1 weaknesses 1 (no formulas), 3 (Boolean predicates), 5 (expressiveness) and 8 (phi_HW and phi_DOSE only in a caption). Numeric values stay "illustrative, unverified" (ADR-020); the registry is filled and clinician-reviewed by WS00-T07.

## Contesto

Unblocks when WS01-T01 is `done`. Read first:

1. `docs/formal/01-signals-sampling.md` (output of T01: signals, grid, ceiling rule, derived signals, decomposition).
2. `docs/plan/02-interfaces.md#template` (the `Template` dataclass, `TemplateId`, `RobustnessUnit`, `normalise`).
3. `docs/source/analisi.md` §4.1 (LaTeX templates and five aspects), §4.2 (time robustness for timing constraints), §2 R1 weaknesses 1, 3, 5, 8, §10 objection 3, §5.6 (A7).
4. `docs/plan/03-decisions.md` ADR-004, ADR-007, ADR-013, ADR-020.
5. `docs/plan/workstreams/WS01-formalization/README.md` (fixture registry F0, golden format, CP1, CP2, CP9, CP11).

## File toccati

- `docs/formal/02-templates.md` (create)
- `docs/formal/golden/templates.yaml` (create)

## Test

Document task: verification checks, plus golden examples written first (Passi step 1) and then reproduced by the document.

1. **Headings.** `## 1 Syntax and semantics`, `## 2 Margin and guard rule`, `## 3 Template table`, `## 4 Template details`, `## 5 Robot obligations`, `## 6 Expressiveness notes`, `## 7 Golden examples`, `## 8 Paper excerpt (Section IV-A, Table I)`, `## 9 Open points for WS01-T08`.
2. **Syntax.** Section 1 gives an EBNF for the past-time string (operators `historically`, `once[a,b]`, `since`, implication, `and`, `or`, `not`, atomic predicates on signals and registry names) and states that "RTAMT-compatible" means a mechanical translation exists, to be checked by the WS05-T02 spike (ADR-013); it does not assume RTAMT API details. It defines quantitative semantics recursively (min for and, max for or, negation, `once` as max over the window, `historically` as min over the window) with windows truncated at the trace start (`once` over an empty window is minus infinity, `historically` over an empty window is plus infinity).
3. **Seven rows.** The table of section 3 has one row for each of RANGE, SCHED, HOLD, COUNT, RESP, SYS, INT with every field of the `Template` dataclass: `kind`, `formula_past_time`, `signals` (only `SignalId` values), `params`, `unit`, `scale_param` (`scale_<id>`), `priority_param` (`priority_<id>`), `max_verdict_latency_param` (`max_latency_<id>`), `creates_robot_obligation`. Kinds: RANGE, SCHED, HOLD, COUNT, RESP are CARE_PLAN; SYS is SYSTEM; INT is INTEGRITY. Each `max_latency_<id>` is declared as a derived value with its formula (for example `delta2 + step_ms` for RESP, `sched_window + step_ms` for SCHED), not as a free parameter.
4. **LaTeX and workshop forms.** Section 4 reproduces the seven formulas of analisi §4.1 in LaTeX, labelled "illustrative, unverified" for their numbers, and states for each which signals are Boolean indicators and which carry a margin.
5. **Margin and guard rule (CP11, R1 weakness 3).** Section 2 states the rule: each template has exactly one margin dimension (its `unit`); every other atom is a guard equal to plus infinity when true and minus infinity when false; a failed guard gives raw sigma minus infinity, normalised value -1, and the record carries the marker `guard_failed: <name>`. It defines the time margin as the slack to the far edge of the response window (deadline slack): for SCHED `(a + W) - t_m` for a measurement `t_m >= a`; for INT `int_window - age` where `age` is the time since the witness or authenticated event; events on the near side of the trigger do not count. It explains why the symmetric two-sided distance to the window is not used (a measurement exactly on time would get margin 0) and marks the missing literature reference as `[ref-needed: WS03]`.
6. **HOLD.** Section 4 gives the workshop form `d -> once[0,hold_lookback](m and bp >= bp_hold_threshold)` and the refined form `d -> (once[0,hold_lookback] m and bp >= bp_hold_threshold)` (latest held measurement, recency as guard), shows with golden case G-HOLD-3 that the workshop form accepts a low latest reading when an earlier reading in the window is high, and records the decision (recommended: refined form) with the clinical intent of analisi §4.1 aspect 3.
7. **Five aspects (R1 weakness 5).** Section 6 has one subsection each for: pre-dose reference (derived `bp_pre` captured per instance, STL freeze operator cited as alternative and not implemented, `[ref-needed: WS03]`), counters as derived signals with atomic predicates `limit - count` in doses, hold and sequence constraints (why past operators are needed), the measurement obligation in the response window (satisfiable only if a measurement falls in `[a + delta1, a + delta2]`), and point events (`O[W, W+T_s]`, referring to T01 section 3).
8. **Decomposition and glossary (R1 weakness 8).** Every template is tagged phi_CP, phi_SYS or phi_INT; "phi_CP" is used only for care-plan constraints; a device fault is not called a violation of the care plan.
9. **Robot obligations (CP1, CP9).** Section 5 defines a document-level obligation record (fields: `obligation_id`, `source_template`, `instance_key`, `patient_id`, `action` in {measure_bp, witness_dispense}, `window_start_ms`, `window_end_ms`, `deadline_ms`, `created_at_ms`), states how each is created (static from schedule ticks for SCHED; dynamic at each DISPENSE for RESP and INT), decides `creates_robot_obligation` for INT with the reason (recommended True: analisi §10 objection 3 derives measurement and witness obligations from phi_resp and phi_INT) and lists the plan feasibility checks a care plan must pass at load (a measurement tick in `[a - hold_lookback, a)` and in `[a + delta1, a + delta2]` for every dispense tick `a`).
10. **COUNT and measurement counts (CP2).** Section 4 states whether the day-end measurement-count obligation (five measurements a day, analisi §4.6 and §4.9 item 3) is part of COUNT, with its unit rule; if the unit cannot be expressed with `RobustnessUnit` the section says so and Section 9 lists it for an ADR.
11. **Instance semantics.** Section 1 states that the reference semantics is per template instance: the body of the formula is evaluated once at the instance's decision step, the outer `historically` is the universal quantification over instances, and the string in `formula_past_time` is the full formula for tools. It states the relation and the assumption (grid-aligned ticks) under which they coincide.
12. **Future-time forms (ADR-007, ablation A7).** For SCHED and RESP the document gives the future-time equivalent (`s -> F[0,W] m`, `d -> F[delta1,delta2](m and r >= delta_resp)`) and states that T05 proves the equivalence of verdicts.
13. **Golden file.** `docs/formal/golden/templates.yaml` has a `fixture_registry` section identical to the F0 table of the README, then exactly the 26 cases below, each with `id`, `contract`, `source`, `fixture`, `inputs`, `eval_at_ms`, `expected` and `hand_calculation`, in the format of the README.
14. **Paper excerpt.** Section 8 is the LaTeX for Table I of the paper (columns: template, formula, unit, scale, priority) plus the Section IV-A text, sized to 0.5 page (analisi §7).
15. **Open points.** Section 9 lists CP1, CP2, CP9 and CP11 with the resolution adopted and whether an ADR is needed, plus any other tension found with an exact anchor.

Golden cases (F0; `step_ms = 60000`; "sat" and "viol" are the Boolean verdicts; sigma-tilde is `clip(sigma / scale, -1, 1)` with the scale of the template; a tie is sigma = 0, which is Boolean satisfied for non-strict predicates, see T05):

| id | Template and inputs | sigma raw | sigma-tilde | Boolean |
|---|---|---|---|---|
| G-RANGE-1 | measurement 09:00, bp 125 | +15 mmHg | 0.75 | sat |
| G-RANGE-2 | measurement 09:05, bp 152 (analisi §4.6 row 08:55: 140 - 152) | -12 mmHg | -0.6 | viol |
| G-RANGE-3 | bp 104 | -6 mmHg | -0.3 | viol |
| G-RANGE-4 | bp 140 (boundary) | 0 | 0 | sat (tie) |
| G-RANGE-5 | bp 200 | -60 mmHg | -1 (clipped) | viol |
| G-COUNT-1 | dispenses 07:00, 21:00, 21:02; at 21:02 `c_d` = 3 (analisi §4.6: -1 dose, not -8) | -1 dose | -1.0 | viol |
| G-COUNT-2 | dispenses 07:00, 21:00; at 21:00 `c_d` = 2 | 0 | 0 | sat (tie) |
| G-COUNT-3 | one dispense (07:00); day-end obligation `c_d >= dose_min_day_end` at `e_day` | -1 dose | -1.0 | viol |
| G-HOLD-1 | measurement 20:35 bp 128; dispense 21:00 | +28 mmHg | 1.0 (clip of 1.4) | sat |
| G-HOLD-2 | measurement 06:50 bp 94; dispense 07:00 | -6 mmHg | -0.3 | viol |
| G-HOLD-3 | measurements 06:15 bp 120 and 06:55 bp 90; dispense 07:00 | refined form -10 mmHg, -0.5, viol; workshop form +20 mmHg, 1.0, sat | | |
| G-HOLD-4 | last measurement 05:30; dispense 07:00 (age 90 min) | minus infinity, guard `no_recent_measurement` | -1 | viol |
| G-RESP-1 | dispense 07:00 with `bp_pre` 150; measurement 08:30 bp 132 (drop 18) | +8 mmHg | 0.4 | sat |
| G-RESP-2 | same dose; measurement 08:30 bp 145 (drop 5) | -5 mmHg | -0.25 | viol |
| G-RESP-3 | same dose; measurements 08:30 bp 145 and 09:30 bp 138 (drops 5, 12) | +2 mmHg | 0.1 | sat |
| G-RESP-4 | same dose; measurements only at 07:45 and 10:30 (both outside `[08:00, 10:00]`) | minus infinity, guard `obligation_unmet` | -1 | viol |
| G-SCHED-1 | tick 09:00, `sched_window` 30 min; measurement 09:05 | +25 min = +1500000 ms | 0.8333 | sat |
| G-SCHED-2 | measurement 09:30 (on the deadline) | 0 | 0 | sat (tie) |
| G-SCHED-3 | measurement 09:51 (21 min late) | -21 min = -1260000 ms | -0.7 | viol |
| G-SCHED-4 | measurement only at 08:50 (before the tick) | minus infinity, guard `no_measurement_after_tick` | -1 | viol |
| G-SYS-1 | measurement with `cuff_health` 1, `inflation_ms` 45000 | +15000 ms | 0.5 | sat |
| G-SYS-2 | `cuff_health` 1, `inflation_ms` 9000 | -21000 ms | -0.7 | viol |
| G-SYS-3 | `cuff_health` 0, `inflation_ms` 45000 | minus infinity, guard `cuff_unhealthy` | -1 | viol |
| G-INT-1 | presence 06:58; dispense 07:00; no auth | +180000 ms | 0.6 | sat |
| G-INT-2 | presence 06:52 (age 8 min); dispense 07:00; no auth | -180000 ms | -0.6 | viol |
| G-INT-3 | dispense 21:00 with `auth` at 21:00; no presence | +300000 ms | 1.0 | sat |

## Passi

1. **Golden first.** Write `docs/formal/golden/templates.yaml`: the `fixture_registry` copied from the README F0 table, then the 26 cases above, converting each `hh:mm` to integer milliseconds and writing the hand calculation (for example G-INT-2: `int_window - age = 300000 - 480000 = -180000; -180000 / 300000 = -0.6`). Recompute each value independently once more.
2. Write section 1 (syntax, quantitative semantics, instance semantics, relation to the full formula). Check that G-SCHED-1 and G-COUNT-2 follow from your definitions; if a definition would change a golden value, change the definition or record and justify the change in section 9, and recompute every affected golden case.
3. Write section 2 (margin and guard rule, time margin as far-edge slack, degenerate Boolean predicates, infinite values and their normalisation). Resolve CP11 here.
4. Write section 4 template by template, in the order RANGE, SCHED, HOLD, COUNT, RESP, SYS, INT: intent (care-plan constraint or system or integrity constraint), LaTeX formula (workshop form and, for HOLD, refined form), past-time string, future-time form for SCHED and RESP, atoms and which are guards, margin unit, decision instant, latency formula.
5. Write section 3 (the seven-row table) from section 4, with registry working names fixed here (`bp_band_low`, `bp_band_high`, `bp_hold_threshold`, `hold_lookback`, `dose_max_24h`, `dose_min_day_end`, `delta1`, `delta2`, `delta_resp`, `sched_window`, `cuff_inflation_min`, `int_window`, and the pattern names of check 3); this is the list T03 registers.
6. Write section 5 (obligation record, creation rules, plan feasibility checks; resolve CP1 and CP9) and section 6 (five aspects).
7. Write section 7 (pointer to the golden file and a summary table) and section 8 (Table I and Section IV-A excerpt).
8. Write section 9 (open points). Run the checks of "Done when", fix, set `status` to `done`, commit `WS01-T02: add past-time template library`.

## Done when

```bash
cd "/home/gab/Desktop/RAL experiment"
f=docs/formal/02-templates.md; g=docs/formal/golden/templates.yaml
test -f "$f" && test -f "$g"
for h in "## 1 Syntax and semantics" "## 2 Margin and guard rule" "## 3 Template table" \
         "## 4 Template details" "## 5 Robot obligations" "## 6 Expressiveness notes" \
         "## 7 Golden examples" "## 8 Paper excerpt (Section IV-A, Table I)" \
         "## 9 Open points for WS01-T08"; do grep -qF "$h" "$f" || echo "missing heading: $h"; done   # prints nothing
for t in RANGE SCHED HOLD COUNT RESP SYS INT; do grep -q "$t" "$f" || echo "missing template: $t"; done   # prints nothing
grep -c '^- id: G-' "$g"                     # prints 26
grep -c 'hand_calculation:' "$g"             # prints 26
grep -q '^fixture_registry:' "$g"
for c in CP1 CP2 CP9 CP11; do grep -q "$c" "$f" || echo "missing $c"; done   # prints nothing
! grep -nE 'T[O]DO|T[B]D|[?][?][?]|lore[m]' "$f" "$g"    # exit 0
```

Also inspect by hand that the `fixture_registry` section equals the F0 table of `docs/plan/workstreams/WS01-formalization/README.md` row for row.

## Notes

Completion note of the executing agent (status left `in_progress`; the orchestrator sets `done` after review, and the orchestrator merges). Work is on branch `ws01-t02-template-library` (base `master`; the repository has no `main`).

**Order of work.** Golden file first (commit `WS01-T02: add golden template examples ...`), then the document. Before any artefact existed, the "Done when" block failed (`FAIL: files missing`, nine `missing heading:` lines, seven `missing template:` lines, four `missing CP` lines, `id count` and `hand_calculation` counts not 26). All checks below were run after the artefacts existed.

**Done when, run from the repository root (real exit codes).**

| Command | Exit | Output |
|---|---|---|
| `test -f "$f" && test -f "$g"` | 0 | none |
| heading loop (9 headings, `grep -qF`) | 0 | prints nothing |
| template loop (RANGE SCHED HOLD COUNT RESP SYS INT) | 0 | prints nothing |
| `grep -c '^- id: G-' "$g"` | 0 | `26` |
| `grep -c 'hand_calculation:' "$g"` | 0 | `26` |
| `grep -q '^fixture_registry:' "$g"` | 0 | none |
| CP loop (CP1 CP2 CP9 CP11) | 0 | prints nothing |
| `! grep -nE 'T[O]DO\|T[B]D\|[?][?][?]\|lore[m]' "$f" "$g"` | 0 | prints nothing |

`fixture_registry` versus the F0 table of the WS01 README, row for row: checked by a script in `/tmp` (not committed) that parses the README table and compares the verbatim cells (name cell, value cell, unit, origin) and the parsed names and values with the yaml: `F0 rows in README: 26 rows in yaml: 26 mismatching rows: 0`. The yaml section was generated from the README table, not typed.

**Test section checks 1 to 15** (script `/tmp/ws01t02/test_checks.py`, not committed; check 16 is an extra wording hygiene check). Exit 0:

```
ok   check 1: nine headings present and in order
ok   check 2: EBNF, RTAMT statement, recursive semantics, empty windows
ok   check 3: seven rows, ten fields, kinds, SignalIds, names, derived latency formulas
ok   check 4: LaTeX block and indicator/margin statement in each of the seven subsections
ok   check 5: margin and guard rule, time margin, symmetric distance, ref-needed
ok   check 6: HOLD workshop and refined forms, G-HOLD-3, decision
ok   check 7: five aspects
ok   check 8: decomposition tags and wording
ok   check 9: obligation record, creation, feasibility
ok   check 10: COUNT and measurement count, listed for ADR
ok   check 11: instance semantics and relation
ok   check 12: future-time forms
ok   check 13: 26 cases with the eight keys in order and a fixture_registry
ok   check 14: Table I LaTeX and Section IV-A text   (Section IV-A text: 340 words, excluding the table)
ok   check 15: open points list CP1, CP2, CP9, CP11 with resolution
ok   check 16: no forbidden wording ("ensures", "orthogonal", "intrinsic explainab", "distribution-free", "Clinical Pathway", "PILL")
```

These checks are mechanical (presence and structure); the substantive review of the semantics is by hand and by the evaluator below.

**Golden cases: hand calculation plus two independent computations.** Every hand calculation is written out in the yaml. Independent script `/tmp/ws01t02/verify.py` (not committed; integer arithmetic on the grid, ceiling rule `(t + T_s - 1) // T_s`, half-open 24 h counter window, per-instance `pre_i`, unknown read as `[-inf, +inf]`): path A parses the seven strings of the section 3.1 table (extracted from the document, so the table strings are checked against the EBNF) with a recursive-descent parser of the EBNF and evaluates them on the whole trace grid (`historically` over all steps, widened antecedent, `age` relative to the enclosing temporal operator); path B computes the per-instance formula per template directly. Both are compared with `expected` (raw value, unit, normalised value, Boolean, guard marker, and for G-HOLD-3 the workshop form). Result, exit 0:

```
PASS G-RANGE-1 A=15.0 B=15.0 exp=15.0      PASS G-HOLD-4 A=-inf B=-inf exp=-inf       PASS G-SCHED-4 A=-inf B=-inf exp=-inf
PASS G-RANGE-2 A=-12.0 B=-12.0 exp=-12.0   PASS G-RESP-1 A=8.0 B=8.0 exp=8.0          PASS G-SYS-1 A=15000.0 B=15000.0 exp=15000.0
PASS G-RANGE-3 A=-6.0 B=-6.0 exp=-6.0      PASS G-RESP-2 A=-5.0 B=-5.0 exp=-5.0       PASS G-SYS-2 A=-21000.0 B=-21000.0 exp=-21000.0
PASS G-RANGE-4 A=0.0 B=0.0 exp=0.0         PASS G-RESP-3 A=2.0 B=2.0 exp=2.0          PASS G-SYS-3 A=-inf B=-inf exp=-inf
PASS G-RANGE-5 A=-60.0 B=-60.0 exp=-60.0   PASS G-RESP-4 A=-inf B=-inf exp=-inf       PASS G-INT-1 A=180000 B=180000 exp=180000.0
PASS G-COUNT-1 A=-1 B=-1 exp=-1.0          PASS G-SCHED-1 A=1500000 B=1500000 exp=1500000.0   PASS G-INT-2 A=-180000 B=-180000 exp=-180000.0
PASS G-COUNT-2 A=0 B=0 exp=0.0             PASS G-SCHED-2 A=0 B=0 exp=0.0             PASS G-INT-3 A=300000 B=300000 exp=300000.0
PASS G-COUNT-3 A=-1 B=-1 exp=-1.0          PASS G-SCHED-3 A=-1260000 B=-1260000 exp=-1260000.0
PASS G-HOLD-1 A=28.0 B=28.0 exp=28.0       (G-HOLD-2 -6.0 and G-HOLD-3 -10.0, workshop +20.0, also PASS)
total fail: 0
```

Caveat on G-SCHED-3: the whole-string evaluation (path A) cannot see the graded lateness, because the string is the decision-time form; for this case path A is checked only at the decision step 570 (value `[-inf, -inf]`, asserted) and the graded value `-1260000` is verified by path B (document sections 1.5 and 2.3). Other verifications: a mutation of one expected value (G-RESP-3 `2.0` to `3.0`) makes the script report `FAIL` (exit 1); an arithmetic checker of the equations written in the `hand_calculation` strings: `equations checked: 59 mismatches: 0`; the `hh:mm` comments against the millisecond values: `labelled times checked: 99 bad: 0`.

Demonstrations quoted in document section 1.5 (same evaluator): SCHED tick 09:00 with measurements 09:00 and 09:20: string `1800000` at step 570 and `660000` at 571 (instance value `1800000`); with a measurement only at 09:00: string `1800000` at 570 and `-inf` at 571 (the Boolean verdict of the string differs); RESP with a sole qualifying measurement at 08:00 after a 07:00 dispense: string `10.0` at 600 and `-inf` at 601.

**Full suite.** `pytest -q`: `175 passed`, exit 0. `python3 tools/check_plan.py`: `check_plan: OK (103 tasks, 18 contracts, 31 findings)`, exit 0. (Run before this Notes section was appended; re-run below.)

**Deviations from the task text.**

1. INT obligation creation (Test check 9 says "dynamic at each DISPENSE for RESP and INT"): INT is created statically from the dispense ticks of the schedule (anticipatory window `[a - int_window, a]`); RESP is dynamic. Reason: the INT window looks back from the dispense (fixed by the goldens G-INT-1 to G-INT-3), so an obligation created when the DISPENSE event arrives is created after its window has closed and cannot change the verdict. `creates_robot_obligation` for INT is True as recommended (CP1). The alternative (forward witness after each dispense) is an open design question (document section 9, TG-8).
2. Goldens G-INT-1 and G-INT-2 carry an explicit `presence = 0.0` sample one step after the observation, and G-RESP-1 to G-RESP-4 carry a pre-dose measurement (150 mmHg at 06:55): the task table lists neither. `presence` is a held level (T01 section 2.1), so without the `0.0` sample the witness would still be present at the dispense (age 0); `pre_i` needs a measurement before the dose. Numbers of the task table are unchanged. G-INT-3 declares presence and intake channels unavailable ("no presence").
3. G-SCHED-3 is evaluated at 09:51 (the step at which the late measurement is visible); at the decision step 09:30 the value is `-inf` (guard). The task table lists only the graded value.
4. Extra keys inside `inputs` and `expected` of the golden file (listed in its header); the eight required case keys are present in the required order. `fixture_registry` entries carry the verbatim README cells plus parsed `names` and `values`.
5. The scope artefact of WS00-T02 is missing; ADR-001 to ADR-003 are the scope source, nothing reconstructed, no ADR edited.
6. Section IV-A text is 340 words (excluding Table I); sized to the 0.5 page of analisi §7 with the table.

**Contract gaps and tensions (no contract or ADR edited); details in document section 9.** CP1, CP2, CP9, CP11 resolved at document level (ADR needed for CP1 comment, CP9 new contract; CP2 only if adopted; CP11 clarification). TG-1 `CarePlan.schedule` has no tick kind; TG-2 `Template` has no anchor, deadline offset or guard-name fields; TG-3 `max_verdict_latency_param` is a "registry entry" but declared derived; TG-4 graded lateness after the decision step; TG-5 the `age` term and the tool string (WS05-T02 spike); TG-6 string versus reference semantics for SCHED and RESP (T01 CG-2, conditions (A1) and (A2)); TG-7 HOLD refined form needs confirmation; TG-8 INT direction and forward witness; TG-9 `presence` as a held level; TG-10 `normalise` and infinities; TG-11 ties (CP3); TG-12 COUNT limit stated with a trigger; TG-13 RANGE during drug onset (clinical question); TG-14 fixture choices.

**Modelling choices made here and why.**

1. Guards are `+-inf`, not `+-1` (a `+-1` guard would be compared with mmHg or ms margins); a failed guard is normalised `-1` and carries `guard_failed`. Touches: none of M1 to M6.
2. Time margin is the slack to the far edge, computed on grid times (sign coincides with the grid Boolean verdict, T01 section 3.3). Touches CG-3 (deadline `t_{k_up(a)} + B`, adopted).
3. SCHED and INT grade beyond the window (time is their margin dimension); HOLD and RESP treat timing as a guard (G-HOLD-4 versus G-INT-2). SCHED grading needs an evaluation after the decision step (TG-4), with a proposed horizon (next tick or closing step). Touches T01 anchoring "evaluated once": the state is fixed at `k_d`, only the raw value of a violated instance is refined.
4. Instance semantics is the reference; the strings of SCHED and RESP (widened antecedent) coincide with it at `k = k_d` and under (A1) and (A2), and are never weaker afterwards. Answers CG-2; keeps the widening of ADR-007.
5. New reserved instance term `age` (time from an event to the decision step), not a `SignalId`, with a Boolean skeleton for tools.
6. HOLD: refined form recommended (recency guard, margin on the latest held `bp`). COUNT: limit restated with the trigger `dispense` (same value; one instance per dispense). Touches CG-14 (persistence unchanged).
7. INT decided at the dispense step (CG-7 resolved: look-back), `intake` kept in the disjunction (M1) although in a look-back window it can only come from an earlier dose.
8. Measurement-count obligation not part of COUNT (CP2).
9. `max_latency_<id>` is the event-time bound `B + step_ms` (CG-4 provisional structure of T01 section 4.6; WS01-T05 confirms).
10. Robot obligation record (nine fields), static SCHED and INT, dynamic RESP; load-time feasibility checks F1 to F7.

**What a reviewer should check hardest.** (a) The arithmetic and inputs of each golden case in `docs/formal/golden/templates.yaml` (especially G-COUNT-3 day-end window `(0, T_day]`, G-HOLD-3 both forms, G-RESP-3 max over the window, G-SCHED-3 graded lateness at 09:51, G-INT-1 and G-INT-2 with the `presence = 0.0` fixture sample). (b) Sign conventions and the guard rule (sections 1.3, 2.1, 2.5): `sigma >= 0` satisfied, ties satisfied, `-inf` guard versus clipped `-1`. (c) The instance versus string relation and the conditions (A1), (A2) in section 1.5, and the claim that B = 0 templates coincide exactly. (d) The robot-obligation formulas of section 5.3 (windows, deadlines, `created_at_ms`) and deviation 1 (INT static). (e) That the seven strings of the section 3.1 table parse under the EBNF (they do, by the script) and carry only `SignalId` values in `signals`. (f) Wording: no "ensures", no clinical claim, DISPENSE never intake.

### Fix round 1

Review round 1 found one blocker and several minor defects in the text of `docs/formal/02-templates.md`. Only that file and this note were changed; `docs/formal/golden/templates.yaml`, the contracts and the ADRs are untouched (`git diff` of the yaml is empty). Status stays `in_progress`. Every fix was reproduced first with scripts in `/tmp/ws01t02/` (not committed: `fix1_checks.py`, `fix1_b0.py`, evaluator `verify.py`; fixed seeds, `T_s = 60000`, windows of a few steps).

| Item | What was wrong | Evidence | Change (`docs/formal/02-templates.md`) |
|---|---|---|---|
| B1 (blocker) | Section 1.4 said replacing every `age` atom by `true` gives a skeleton with the same verdict. False for INT (enclosing `once[0, inf]`). | G-INT-2: string `-180000`, rule-based skeleton `+inf`. Random, 2000 traces: `once[0, inf]` skeleton disagrees with the string in 650, the bounded skeleton `once[0, int_window]` in 0. SCHED skeleton (`once[0, sched_window] meas`): 0 of 2000, and G-SCHED-1 to G-SCHED-4 agree; G-INT-1 to G-INT-3 agree with the bounded skeleton. | Section 1.4 (line 104 onwards): skeleton defined per template; SCHED equivalent; INT skeleton defined explicitly with the bounded window; the general rule and the "tool can check verdicts on the skeleton for all templates" sentence removed. Pointers in 1.2 (RTAMT paragraph, `age` rule) and 1.6. |
| M1 | Section 1.5 omitted the RESP overlapping-dose assumption (string uses global `bp_drop`, reference uses `pre_i`). | RESP, 3751 random traces with 1 to 3 dispenses: value relation holds in 1824 of 1824 with no other dispense in `k_a..k_d+1`, fails in 102 of 1927 otherwise; string above `min sigma_i` in 21; with (A2), Boolean disagreement 0 of 1559 with (A3), 19 of 1442 without. | Assumption (A3) added to section 1.5 (line 135), to the "never weaker" claim, to the references in 1.5, 4.2, 4.5, 6.5, and TG-6 in section 9. |
| M2 | "Boolean verdict differs exactly when the only observation with a non-negative margin lies at `E`" too broad. | SCHED single anchor, 6000 traces: 703 differ; old predicate mispredicts 415, refined predicate ("and no qualifying observation at `k_d + 1`") 0. RESP single anchor: 317 differ; old 89, refined 0. Example tick step 6, `W = 5`, measurements at 6 and 12: string `+300000`, `0`, same verdict. | Section 1.5 sentence corrected and example added; TG-6. |
| M3 | "B = 0 ... no further assumption" assumes at most one measurement per bin. | RANGE with `bp` 150 at 09:00:10 and 120 at 09:00:40 (step 541): string `+10`, instances `-10` and `+10`. Random: RANGE 0 mismatches with one measurement per bin, 14 of 1500 with up to two; SYS 0 and 6; HOLD 0 and 0. | Assumption (A0) added in the `B = 0` bullet of section 1.5, linked to T01 section 3.4, scope stated (RANGE and SYS need it; HOLD, COUNT, INT do not); TG-6 mentions it. |
| M5 | `age` is a freeze-like term in `formula_past_time`, tension with "RTAMT-compatible" (contract) and ADR-007 (no freeze). | Document review. | TG-5 rewritten: ADR needed if `age` cannot be expressed with WS05-T02 spike operators; `age` is not a `SignalId` and not defined in T01, WS01-T08 check (c) must be told. Line added to the `age` reading rule (section 1.2). |
| M6 | Paper excerpt said latency is bounded by the deadline offset plus one step (event time not named). Table I is a wide table. | Document review (T01 section 4.6, CG-4). | Excerpt says "decidable, in event time, within the deadline offset plus one monitor step of the anchor; the end-to-end latency adds the reorder delay". Table I changed from `table` to `table*` (two-column float), with a note in the section 8 preamble. |

Not acted on (logged by the orchestrator): M4, M7, M8 and the downstream INT-obligation mismatches with WS07-T04 and WS04-T10.

Re-verification after the fix (real exit codes): the exact "Done when" block extracted from this file: exit 0, prints `26`, `26`; Test checks 1 to 16 (`/tmp/ws01t02/test_checks.py`, check 14 now accepts `table*`): exit 0, no failures, Section IV-A text 349 words (was 340); the independent golden verification `/tmp/ws01t02/verify.py` against the unchanged yaml: exit 0, 26 PASS, 0 FAIL; `pytest -q`: 175 passed, exit 0; `python3 tools/check_plan.py`: `check_plan: OK (103 tasks, 18 contracts, 31 findings)`, exit 0.
