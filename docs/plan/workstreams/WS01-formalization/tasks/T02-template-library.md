---
id: WS01-T02
title: Past-time STL template library with units and robot obligations
workstream: WS01-formalization
owner: agent
status: ready
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
