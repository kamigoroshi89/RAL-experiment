---
id: WS01-T01
title: "Problem formulation: signals, sampling semantics, time, decomposition"
workstream: WS01-formalization
owner: agent
status: in_progress
depends_on: ["WS00-T02"]
critical_path: true
non_negotiable: true
estimate_pd: 2
sources: ["analisi §4.1", "analisi §4.9 (2)", "analisi §2 R1 (weaknesses 4 and 7)", "analisi §4.9 (5)"]
interfaces: ["02-interfaces.md#time-and-units", "02-interfaces.md#signals"]
review_items: ["R1-W4", "R1-W7"]
---
## Obiettivo

Write `docs/formal/01-signals-sampling.md`: the problem-formulation core of paper Section III. It fixes the signal table (symbols of analisi §4.1 mapped to the `SignalId` values of the contract), the discrete-time sampling semantics for sparse and irregular data, the two clocks with reorder buffer and their effect on verdict latency, the derived signals, and the decomposition phi = phi_CP and phi_SYS and phi_INT. This task is non-negotiable (analisi §9): it may not be cut or shortened to a sketch. It contains no numeric clinical value; illustrative numbers carry the label "illustrative, unverified" (ADR-020).

## Contesto

Unblocks when WS00-T02 is `done` (its output fixes the pathology, C3 as integrity violation and the ward-node-plus-robot architecture, ADR-001 to ADR-003). Read first:

1. `docs/source/analisi.md` §4.1 (signals, sampling, aspects 2 and 5), §4.9 items 2 and 5, §2 R1 weaknesses 4 and 7.
2. `docs/plan/02-interfaces.md#time-and-units` and `#signals` (rules and `SignalId` list).
3. `docs/plan/03-decisions.md` ADR-004 (DISPENSE is not INTAKE), ADR-007 (past-time, derived counters), ADR-017 (integer milliseconds).
4. `docs/plan/workstreams/WS01-formalization/README.md` (shared conventions, fixture registry F0, golden format).

## File toccati

- `docs/formal/01-signals-sampling.md` (create)

## Test

Document task: verification checks a reviewer can run or inspect.

1. **Headings.** The file contains exactly these H2 headings: `## 1 Scope and conventions`, `## 2 Signal table`, `## 3 Time base and sampling semantics`, `## 4 Clocks, reordering and verdict latency`, `## 5 Derived signals`, `## 6 Decomposition of the specification`, `## 7 Worked examples`, `## 8 Paper excerpt (Section III)`, `## 9 Open points for WS01-T08`.
2. **Signal coverage.** Every one of the 17 `SignalId` values (`bp meas dispense intake sched_tick dose_count meas_count bp_pre bp_drop cuff_health inflation_ms presence auth day_end hr_ecg hr_pulse spo2`) appears in section 2 with: analisi symbol (bp, m, d, s, c_d, h_c, q, w, e_day, a_auth, bp^pre, r, or "evidence only" for `hr_ecg`, `hr_pulse`, `spo2`), kind (held value, impulse, derived, status), unit, producer (device, robot, monitor), and whether the signal can be unavailable (`presence`, `intake`) as opposed to zero.
3. **DISPENSE and INTAKE.** Section 2 states that `dispense` (device) never proves intake and that `intake` is produced only by the robot witness (ADR-004); `w` of phi_INT is defined explicitly as a function of `presence`, `intake` and `auth`, and the choice is justified.
4. **Grid rules.** Section 3 states: grid `t_k = k * T_s`; a sample is held piecewise-constant from its device time; an event with device time `t` is visible as an impulse at the first grid step `>= t` (ceiling rule); `O[W,W]` is evaluated as `O[W, W+T_s]` (contract rule 2) and the document analyses the consequence that the antecedent impulse is then true at two consecutive steps and states the anchoring convention (one obligation instance per anchor, evaluated once) that removes double evaluation; all registry time values must be integer multiples of `T_s` and a plan that violates this is rejected at load.
5. **Multiplicity.** Section 3 states that impulse coalescing must not lose multiplicity: counters are computed from the event stream, not from the binned impulse (two `dispense` events inside one step give `c_d` an increment of 2).
6. **Undefined and unavailable.** Section 3 defines the held value before the first sample (recommended: NaN, read as "unknown, completed by physiological bounds", CP12) and separates "no sample" from "channel unavailable" (`None` in the contract, never converted to 0 or false).
7. **Two clocks.** Section 4 defines `t_device_ms` and `t_rx_ms`, the reorder buffer with maximum delay `D`, the causality rule of `Monitor.advance` (inputs with `t_device_ms <= t - D`), the late-sample policy (a sample arriving after its watermark is not used, is counted, and is evidence for `timestamp_implausible`; an emitted definitive verdict is never retracted), the clock-skew assumption (bounded skew; larger skew is evidence, not a value), and timestamp replay as an attack vector (analisi §4.9 item 2).
8. **Latency terms.** Section 4 defines three quantities with symbols: event-time latency from the anchor, processing latency `D`, and end-to-end latency; it states that the per-template bound is filled in by WS01-T05.
9. **Derived signals.** Section 5 defines `dose_count` (dispenses in `(t - 24h, t]`, half-open, amortised O(1) per event), `meas_count` (measurements in the current day), `bp_pre` (pressure of the last measurement before the dose, captured per obligation instance so that overlapping doses do not overwrite each other; the global stream and the per-instance capture are both described) and `bp_drop = bp_pre - bp`; each is causal and streaming (contract rule). It states the day-boundary convention for the trailing 24 h counter and for windows that end after 24:00 and gives a recommended carry-over rule (CP7).
10. **Decomposition.** Section 6 defines phi = phi_CP and phi_SYS and phi_INT as three separately evaluated conjuncts, maps the seven `TemplateId` values to the three `TemplateKind` values (RANGE, SCHED, HOLD, COUNT, RESP to CARE_PLAN; SYS to SYSTEM; INT to INTEGRITY), states that no numeric `min` across the three parts is taken, and uses the glossary: only phi_CP violations are violations of the care plan; a device fault is not a violation of the care plan (R1 weakness 8).
11. **Worked examples W1 to W7** (section 7, F0 with `step_ms = 60000`), each with inputs, expected output and a one-line hand calculation:
    - W1 `hold_last`: `bp` samples 138 at 06:52 and 152 at 09:05 give held value NaN before 06:52, 138 for 06:52 to 09:04, 152 from 09:05.
    - W2 impulse binning: a `measurement` event at 06:52:20 is visible at step 06:53; one at exactly 06:52:00 is visible at 06:52.
    - W3 multiplicity: two `dispense` events at 21:00:00.000 and 21:00:00.500 give one impulse and `c_d` incremented by 2.
    - W4 alignment: tick at 09:00, `W = sched_window` (F0, 30 min): `O[W, W+T_s] s` is true at steps 09:30 and 09:31; the obligation is evaluated once, at 09:30.
    - W5 reorder (D = 30 s): a sample with device time 09:29:50 and receive time 09:30:10 is accepted for step 09:30; the same device time with receive time 09:30:40 is late and not used.
    - W6 trailing counter: dispenses at 07:00, 21:00, 21:02 on day 1 and at 07:00 on day 2: `c_d` at day-2 07:00 (own dispense included) is 3, because `(07:00 day 1, 07:00 day 2]` excludes the day-1 07:00 dose; this is the cross-midnight case of CP7.
    - W7 alignment rejection: `T_s = 60000` accepts `sched_window = 1800000` and rejects a window of 90500 ms.
12. **No clinical constants.** Every number in the document is either in the F0 table of the README, an analisi value labelled "illustrative, unverified", or an example time; a `Parameters used` table lists registry working names, unit and origin.
13. **Paper excerpt.** Section 8 is a LaTeX/Markdown block for Section III sized to 0.5 page (analisi §7): signals, sampling, alert-tuple placeholder, decomposition; it contains no tutorial on box and diamond operators (analisi §7, cut 2).
14. **Open points.** Section 9 lists at least CP7 and CP12 with the proposed resolution, and any other contract tension found (with the exact contract anchor).

## Passi

1. Create `docs/formal/` if absent. Write the section skeleton with the nine headings of check 1.
2. Section 2: build the signal table from `#signals` and analisi §4.1 item 1 (add columns of check 2). Decide `w` explicitly (recommended: `w = presence or intake`, with `intake` only when the robot is co-located) and justify it against phi_INT of analisi §4.1.
3. Section 3: write the discretisation (grid, hold, ceiling rule, multiplicity, undefined value, unavailable channel, alignment of `O[W,W]`). Work through W4 by hand before writing the convention: list at which steps the antecedent holds and what each step's consequent window covers.
4. Section 4: write the two-clock model, reorder buffer, late-sample policy, skew assumption, replay note and the three latency terms. Work through W5 by hand.
5. Section 5: define the four derived signals and the day-boundary convention. Work through W6 by hand and state the recommended carry-over rule (a warm-up prefix of the previous 24 h supplied with the day, or monitor state carried between days) and the truncation fallback with its limitation; mark CP7.
6. Section 6: write the decomposition and the wording rules; cite R1 weakness 8 as the reason.
7. Section 7: write W1 to W7 with hand calculations; recompute each twice.
8. Section 8: write the Section III excerpt. Section 9: list open points.
9. Run the checks of "Done when"; fix; then set this task's `status` to `done` and commit `WS01-T01: add signals and sampling semantics`.

## Done when

```bash
cd "/home/gab/Desktop/RAL experiment"
f=docs/formal/01-signals-sampling.md
test -f "$f"
for h in "## 1 Scope and conventions" "## 2 Signal table" "## 3 Time base and sampling semantics" \
         "## 4 Clocks, reordering and verdict latency" "## 5 Derived signals" \
         "## 6 Decomposition of the specification" "## 7 Worked examples" \
         "## 8 Paper excerpt (Section III)" "## 9 Open points for WS01-T08"; do
  grep -qF "$h" "$f" || echo "missing heading: $h"; done          # prints nothing
for s in bp meas dispense intake sched_tick dose_count meas_count bp_pre bp_drop cuff_health \
         inflation_ms presence auth day_end hr_ecg hr_pulse spo2; do
  grep -qw "$s" "$f" || echo "missing signal: $s"; done            # prints nothing
for w in W1 W2 W3 W4 W5 W6 W7 CP7 CP12; do grep -q "$w" "$f" || echo "missing: $w"; done   # prints nothing
! grep -nE 'T[O]DO|T[B]D|[?][?][?]|lore[m]' "$f"                   # exit 0
```

All commands print nothing and the last exits 0.

## Notes

Completion note of the executing agent (status left `in_progress`; the orchestrator sets `done` after review).

**Done when, run from the repository root.**

| Command | Exit | Output |
|---|---|---|
| `test -f docs/formal/01-signals-sampling.md` | 0 | none |
| heading loop (9 headings, `grep -qF`) | 0 | prints nothing |
| signal loop (17 `SignalId`, `grep -qw`) | 0 | prints nothing |
| `W1 ... W7 CP7 CP12` loop | 0 | prints nothing |
| `! grep -nE 'T[O]DO\|T[B]D\|[?][?][?]\|lore[m]'` | 0 | prints nothing |

**Test section checks 1 to 14.** Run with a script kept outside the repository (`/tmp/check_ws01_t01.py`); it failed on all checks before the document existed ("file missing", exit 1) and passes now (exit 0):

```
check  1 PASS  exact H2 list: 9 headings, exact order
check  2 PASS  17 signals with symbol, kind, unit, producer, unavailability: 17 rows complete
check  3 PASS  DISPENSE vs INTAKE and w: ok
check  4 PASS  grid rules, ceiling, O[W,W], anchoring, alignment: ok
check  5 PASS  multiplicity: ok
check  6 PASS  undefined vs unavailable: ok
check  7 PASS  two clocks, buffer, late policy, skew, replay: ok
check  8 PASS  three latency terms: ok
check  9 PASS  derived signals and day boundary: ok
check 10 PASS  decomposition: ok
check 11 PASS  worked examples W1-W7: 7 examples with inputs, expected, hand calculation
check 12 PASS  parameters table: ok (numeric audit is manual)
check 13 PASS  paper excerpt (0.5 page): words=492 []
check 14 PASS  open points: ok
check 15 PASS  glossary/claim hygiene: no hits
```

Check 12 (no clinical constants) was completed by hand: every numeric token of the document was listed and is a section number, an ADR or analisi reference, an example time with its millisecond conversion, an F0 value, or fixture arithmetic. Check 13: the 492 tokens include LaTeX command words; the excerpt has no operator tutorial.

**Second calculation of W1 to W7.** Each worked example was recomputed by an independent simulation (`/tmp/w_verify.py`, not committed). Result: 22 assertions PASS, last line `ALL OK`. It includes the equality, on 300 random events, of the device-time and the binned form of `dose_count` (needs `T_s | T_day`).

**Full suite.** `pytest -q`: `175 passed`, exit 0. `python3 tools/check_plan.py`: `check_plan: OK (103 tasks, 18 contracts, 31 findings)`, exit 0.

**Deviations from the task text (all recorded in `docs/formal/01-signals-sampling.md` section 9).**

1. W3: the pair 21:00:00.000 and 21:00:00.500 falls in two bins under the ceiling rule (steps 21:00 and 21:01), so it does not give "one impulse". The document uses 20:59:59.500 and 21:00:00.000 (same bin, `c_d` increment 2) and shows the original pair as a note (CG-8).
2. Grid rule (Test check 4): "all registry time values must be integer multiples of `T_s`" would reject F0 itself (`cuff_inflation_min` 30000 ms, `scale_sys` 30000 ms and `D` = 30000 ms in W5 with `T_s` = 60000). The rule is applied to window parameters (operator offsets, look-backs, deadline offsets) only (CG-1).
3. The scope artefact `docs/plan/workstreams/WS00-admin/outputs/WS00-T02.md` is missing; ADR-001 to ADR-003 were used as the scope source and nothing was reconstructed.
4. Branch base is `master` (the repository has no `main`).

**Contract gaps and tensions (no contract or ADR edited).** CP7, CP12 with proposed resolutions; CG-1 to CG-14 as listed in section 9, notably: the widened `O[W,W+T_s]` is redundant on the aligned grid under the ceiling rule and, evaluated without anchoring, makes the string stricter than the per-instance semantics (CG-2, W4 case b); `pending_until_ms` anchor reading (CG-3); event-time versus end-to-end latency bound (CG-4); no `EventKind` for `auth`, `presence`, `day_end`, `cuff_health` (CG-5); `hold_last` cannot carry `None` (CG-6); the look-back direction of phi_INT prevents `intake` from contributing at the dispense step (CG-7).
