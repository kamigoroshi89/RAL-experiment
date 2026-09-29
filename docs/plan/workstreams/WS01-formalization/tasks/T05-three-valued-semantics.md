---
id: WS01-T05
title: Three-valued online semantics with robustness intervals and latency bounds
workstream: WS01-formalization
owner: agent
status: blocked
depends_on: ["WS01-T02"]
critical_path: true
non_negotiable: true
estimate_pd: 3
sources: ["analisi §4.3", "analisi §4.7", "analisi §4.6", "analisi §2 R1 (weakness 6)", "analisi §2 R2 (weakness 2)", "analisi §5.6 (A2, A7)"]
interfaces: ["02-interfaces.md#verdict"]
review_items: ["R1-W6", "R2-W2", "AE-5"]
---
## Obiettivo

Write `docs/formal/05-three-valued-semantics.md` and `docs/formal/golden/verdicts.yaml`: the online semantics of the monitor. It defines robustness intervals on measured prefixes (unknown future values replaced by physiological bounds), the verdicts PENDING, PREDICTED-VIOLATION, VIOLATED and SATISFIED with the state diagram, the rule that conformal prediction acts only in PENDING and never produces a definitive verdict, the soundness and stability lemmas with proofs, the per-template verdict latency bounds, the monitoring loop as pseudocode with its complexity per sample, and the equivalence to the future-time formulation (ablation A7). It contains 24 hand-computed golden cases that WS05-T04 and WS05-T06 reuse as fixtures. This task is non-negotiable (analisi §9). It closes R1 weakness 6 (the workshop Table I emits at 21:02 a cross-modal verdict that the declared semantics can decide only much later) and R2 weakness 2 (measured values versus conformal envelope).

## Contesto

Unblocks when WS01-T02 is `done`. Read first:

1. `docs/formal/02-templates.md` (instance semantics, margin and guard rule, decision instants, future-time forms) and `docs/formal/01-signals-sampling.md` (grid, two clocks, day boundary).
2. `docs/plan/02-interfaces.md#verdict` (states, `RobustnessInterval`, `VerdictRecord`, semantics 1 to 4, allowed transitions) and `#monitor` (causality, latency bound, complexity rule).
3. `docs/source/analisi.md` §4.3 (readings A and B), §4.7 (three tools, state diagram, pseudocode), §4.6 (row 21:02), §2 R1 weakness 6, R2 weakness 2, §5.6 (A2, A7).
4. `docs/plan/03-decisions.md` ADR-007 and ADR-008.
5. `docs/plan/workstreams/WS01-formalization/README.md` (fixture registry F0, golden format, CP3, CP6, CP7, CP12).

## File toccati

- `docs/formal/05-three-valued-semantics.md` (create)
- `docs/formal/golden/verdicts.yaml` (create)

## Test

Document task: verification checks, plus golden cases written first and reproduced by the document.

1. **Headings.** `## 1 Measured versus predicted`, `## 2 Robustness intervals on prefixes`, `## 3 Three-valued verdict`, `## 4 State diagram`, `## 5 Predicted completion`, `## 6 Monitoring loop and complexity`, `## 7 Latency bounds`, `## 8 Relation to the future-time formulation`, `## 9 Golden examples`, `## 10 Paper excerpt (Section IV-C)`, `## 11 Open points for WS01-T08`.
2. **Separation (R2 weakness 2).** Section 1 states the two readings of analisi §4.3, adopts the separation of ADR-008 (definitive verdicts only from the measured prefix with robustness intervals; measurement uncertainty is modelled by the device error model in rho, not by the forecaster; conformal prediction only in PENDING and only for early warning), and states that the sentence "final safety verdicts remain grounded in measured values" holds by construction. It does not use the phrase "flagged only when the uncertainty envelope exits the safe region".
3. **Intervals.** Section 2 defines the completion set of a prefix (all extensions consistent with the samples received; unknown future values inside the physiological bounds of the registry; any future step may or may not carry an event; data still inside the reorder window unknown), the interval `[lo, hi]` as infimum and supremum of raw robustness over that set, computed by structural recursion with interval arithmetic (min, max monotone; negation swaps ends), the empty maximum equal to minus infinity, and guards with values plus and minus infinity (T02).
4. **Soundness lemma.** Section 2 proves by induction on the formula that for every completion the robustness lies in `[lo, hi]`, hence VIOLATED (`hi < 0`) means every completion violates and SATISFIED (`lo > 0`) means every completion satisfies (analisi §4.7: "sound by construction with respect to the measurement model"). It states that interval arithmetic is not claimed tight when a signal occurs twice in a formula.
5. **Stability lemma.** Section 2 proves that intervals computed on a longer prefix are contained in those of a shorter prefix, so a definitive verdict never changes (states VIOLATED and SATISFIED are absorbing) and the "never retracted" rule of T01 is consistent.
6. **Verdict rule and ties (CP3).** Section 3 restates rule 1 of the contract and adds the tie rule: when an instance is closed (no unknown step remains in its window) and its interval is the point 0, the verdict is the Boolean value of the formula (non-strict atomic predicates: equality satisfies), so `bp = bp_band_high` and `c_d = dose_max_24h` are SATISFIED and PENDING never remains open on a closed instance. It states early satisfaction for existential obligations (SATISFIED as soon as `lo > 0`, before the deadline).
7. **Unavailable channel (CP6).** Section 3 separates unknown-because-future from unknown-because-unavailable (`presence`, `intake` when the robot is not co-located, contract rule "absence is reported through the EvidenceVector"): the record stays PENDING after `pending_until_ms`, with an auxiliary marker `undecidable: channel_unavailable:<signal>` kept in the monitor log, and the section lists the contract change that would make this explicit (CP6).
8. **Infinite endpoints (CP12).** Section 2 states that endpoints may be plus or minus infinity, how they are normalised (T04) and the required serialisation (recommended: the strings `-inf` and `inf` in JSON, `-.inf` and `.inf` in YAML).
9. **State diagram.** Section 4 gives the diagram (PENDING to PREDICTED-VIOLATION to VIOLATED; PENDING to VIOLATED; PENDING to SATISFIED; PREDICTED-VIOLATION to SATISFIED as a false predictive alarm) as Mermaid or ASCII, plus a transition table with the guard, the fields of `VerdictRecord` that change (`state`, `rho`, `decided_at_ms`, `pending_until_ms`) and the rule that a warning is sticky (no retraction to PENDING) with its consequence for alarm counts and for Proposition 1 (the union over prediction instants is what is bounded, hence a designated set of prediction instants or an alpha allocation, T06).
10. **Predicted completion.** Section 5 states that the completion uses the forecaster's path instead of the physiological bounds, that emission is only while PENDING, that VIOLATED and SATISFIED are never produced by a forecast, that the variants "likely" and "possible" are defined in T06 (CP4), that the targets in scope are continuous signals and robot care-delivery deadlines (analisi §4.3, blood pressure with five measurements a day is not a candidate), and that removing the forecaster (A2) leaves every definitive verdict unchanged.
11. **Loop and complexity.** Section 6 gives the monitoring loop (reorder buffer, grid step, per-instance update, verdict emission) and states the cost per sample as O(number of active template instances) time with amortised O(1) sliding-window extrema per instance, memory bounded by the window lengths, and the reorder buffer as a separate O(log B) term; it repeats the contract rule that `advance` is causal. It states explicitly that the bound is reported and how WS05-T04 measures it.
12. **Latency (R1 weakness 6).** Section 7 tabulates, for each of the seven templates: anchor, decision step, `pending_until_ms`, event-time latency bound from the anchor (SCHED: `sched_window + step_ms`; RESP: `delta2 + step_ms`; RANGE, HOLD, COUNT limit, SYS, INT: the step of the triggering event; COUNT day-end: the `day_end` step), processing latency `D`, and the value returned by `Monitor.verdict_latency_bound_ms`. It proves the bound by the interval argument (after the decision step no unknown step remains in the window) and shows with the workshop Table I row 21:02 that the cross-modal verdict of a dispense at 21:02 cannot be decided before its window closes (F0: 24:02, after the day end, CP7).
13. **A7.** Section 8 proves for SCHED and RESP that the verdict of the past-time form at the deadline equals the verdict of the future-time form at the anchor, and states what A7 must compare (verdict equality and latency, implementation cost).
14. **Golden file.** `docs/formal/golden/verdicts.yaml` contains exactly the 24 cases below, each with `hand_calculation`, in the README format; `expected` carries `state`, `sigma_interval`, `sigma_norm_interval`, `rho` (null or kind and value), `decided_at_ms`, `pending_until_ms`.
15. **Paper excerpt.** Section 10 is the Section IV-C text: state diagram, the algorithm in at most ten lines, the soundness statement and the latency bound, sized to 0.45 page together with Proposition 1 (analisi §7).
16. **Open points.** Section 11 lists CP3, CP6, CP7 and CP12 with the resolution adopted and whether an ADR is needed.

Golden cases (F0; `step_ms` 60000; `reorder_delay_ms` 0 unless stated; intervals are raw, in the native unit of the template; sigma-tilde intervals use the F0 scale; an earliest possible future measurement is one step after the evaluation instant):

| id | Situation | State | Raw interval | Normalised interval | rho | decided_at |
|---|---|---|---|---|---|---|
| V-SCHED-1 | tick 09:00, W 30 min; no measurement; eval 09:10 | PENDING | [-inf, 1140000 ms] (hi = 09:30 - 09:11 = 19 min) | (-1, 0.6333) | none | none; pending_until 09:30 |
| V-SCHED-2 | measurement 09:05; eval 09:05 | SATISFIED | [1500000, 1500000] | (0.8333, 0.8333) | none | 09:05 |
| V-SCHED-3 | no measurement; eval 09:30 | VIOLATED | [-inf, -60000] (hi = 09:30 - 09:31) | (-1, -0.0333) | DETERMINISTIC 1.0 | 09:30 |
| V-SCHED-4 | measurement exactly 09:30; eval 09:30 | SATISFIED by the tie rule | [0, 0] | (0, 0) | none | 09:30 |
| V-SCHED-5a | no measurement; eval 09:40 | VIOLATED | [-inf, -660000] | (-1, -0.3667) | DETERMINISTIC 1.0 | 09:30 |
| V-SCHED-5b | measurement 09:51; eval 09:51 | VIOLATED | [-1260000, -1260000] | (-0.7, -0.7) | DETERMINISTIC 1.0 | 09:30 |
| V-PRED-1 | as V-SCHED-1 at 09:10; forecast arrival 09:40 gives sigma-hat -10 min = -0.3333; calibrator fixture C-1 of T06 (n = 9, alpha 0.2, q = 0.09), variant likely: -0.3333 + 0.09 < 0 | PREDICTED_VIOLATION | [-inf, 1140000] | (-1, 0.6333) | PREDICTED 0.9 (alpha* = 0.1), alpha 0.2 | none |
| V-PRED-2 | continuation of V-PRED-1; measurement 09:25 | SATISFIED (false predictive alarm) | [300000, 300000] | (0.1667, 0.1667) | none | 09:25 |
| V-PRED-3 | continuation of V-PRED-1; no measurement; eval 09:30 | VIOLATED (from PREDICTED) | [-inf, -60000] | (-1, -0.0333) | DETERMINISTIC 1.0 | 09:30 |
| V-RESP-1 | dispense 07:00, bp_pre 150; no measurement; eval 07:30 | PENDING | [-inf, 90 mmHg] (150 - 50 - 10) | (-1, 1) | none | none; pending_until 10:00 |
| V-RESP-2 | measurement 08:30 bp 145; eval 08:30 | PENDING | [-5, 90] | (-0.25, 1) | none | none |
| V-RESP-3 | measurement 08:30 bp 132; eval 08:30 | SATISFIED | [8, 90] | (0.4, 1) | none | 08:30 |
| V-RESP-4 | measurement 08:30 bp 145 only; eval 10:00 | VIOLATED | [-5, -5] | (-0.25, -0.25) | MEASURED 0.7222 (Phi(5 / (6 * sqrt 2))) | 10:00 |
| V-RESP-5 | no measurement in [08:00, 10:00]; eval 10:00 | VIOLATED (guard `obligation_unmet`) | [-inf, -inf] | (-1, -1) | DETERMINISTIC 1.0 | 10:00 |
| V-RESP-6 | measurement 10:00 bp 140 (drop 10, margin 0); eval 10:00 | SATISFIED by the tie rule | [0, 0] | (0, 0) | none | 10:00 |
| V-COUNT-1 | dispenses 07:00, 21:00, 21:02; eval 21:02 | VIOLATED | [-1, -1] dose | (-1, -1) | DETERMINISTIC 1.0 | 21:02 |
| V-COUNT-2 | dispenses 07:00, 21:00; eval 21:00 | SATISFIED by the tie rule | [0, 0] | (0, 0) | none | 21:00 |
| V-COUNT-3 | one dispense (07:00); day-end obligation; eval 21:30 | PENDING | [-1, +inf] | (-1, 1) | none | none; pending_until 24:00 |
| V-COUNT-4 | same; eval 24:00 | VIOLATED | [-1, -1] | (-1, -1) | DETERMINISTIC 1.0 | 24:00 |
| V-INT-1 | dispense 21:00, `presence` unavailable in [20:55, 21:00], no auth; eval 21:00 | PENDING, marker `channel_unavailable:presence` | [-inf, 300000 ms] | (-1, 1) | none | none; pending_until 21:00 (elapsed) |
| V-INT-2 | dispense 21:00 with `auth` at 21:00 | SATISFIED | [300000, 300000] | (1, 1) | none | 21:00 |
| V-INT-3 | dispense 21:00, robot co-located, `presence` observed false in [20:55, 21:00], no auth | VIOLATED (guard `no_witness`) | [-inf, -inf] | (-1, -1) | DETERMINISTIC 1.0 | 21:00 |
| V-LATE-1 | tick 09:00, W 30 min, `reorder_delay_ms` 30000; measurement device time 09:29:50, receive time 09:30:40 (after the watermark); eval at monitor time 09:30:30 | VIOLATED emitted at 09:30:30; the late sample is counted and never retracts the verdict | [-inf, -60000] | (-1, -0.0333) | DETERMINISTIC 1.0 | 09:30:00 |

A twenty-fourth case, V-LATE-2, has the same setting with receive time 09:30:10 (before the watermark): SATISFIED, raw interval [10000, 10000] ms (slack 09:30:00 - 09:29:50), normalised (0.0056, 0.0056), decided_at 09:30:00 (device time), emitted at monitor time 09:30:30.

## Passi

1. **Golden first.** Write `docs/formal/golden/verdicts.yaml` with the 24 cases (V-LATE-2 included), converting `hh:mm` to milliseconds and writing each hand calculation (for V-SCHED-1: `hi = (a + W) - (t + T_s) = 09:30 - 09:11 = 19 min = 1140000 ms; 19/30 = 0.6333`). For the PREDICTED and MEASURED cases, cross-check rho against the derivations you will write in T06 (alpha* = (n + 1 - m) / (n + 1) with n = 9 and m = 9 gives 0.1; the Gaussian value for V-RESP-4 uses the standard deviation of a difference of two measurements, `6 * sqrt 2`).
2. Write sections 1 and 2: separation, completion set, interval recursion, lemmas with proofs. Check that every golden interval follows from your recursion; if one does not, fix the definition or the case and record why.
3. Write section 3 (verdict rule, tie rule, early satisfaction, unavailable channel) and section 4 (diagram, transition table, sticky warning).
4. Write section 5 (predicted completion) and section 6 (loop, complexity, reorder buffer).
5. Write section 7 (latency table with proofs, the Table I row 21:02 example) and section 8 (past-time versus future-time equivalence).
6. Write section 9 (summary of the golden cases and how WS05 loads them), section 10 (paper excerpt) and section 11 (open points).
7. Run "Done when"; set `status` to `done`; commit `WS01-T05: add three-valued online semantics`.

## Done when

```bash
cd "/home/gab/Desktop/RAL experiment"
f=docs/formal/05-three-valued-semantics.md; g=docs/formal/golden/verdicts.yaml
test -f "$f" && test -f "$g"
for h in "## 1 Measured versus predicted" "## 2 Robustness intervals on prefixes" "## 3 Three-valued verdict" \
         "## 4 State diagram" "## 5 Predicted completion" "## 6 Monitoring loop and complexity" \
         "## 7 Latency bounds" "## 8 Relation to the future-time formulation" "## 9 Golden examples" \
         "## 10 Paper excerpt (Section IV-C)" "## 11 Open points for WS01-T08"; do
  grep -qF "$h" "$f" || echo "missing heading: $h"; done       # prints nothing
grep -c '^- id: V-' "$g"                                       # prints 24
grep -c 'hand_calculation:' "$g"                               # prints 24
for w in PENDING PREDICTED VIOLATED SATISFIED CP3 CP6 CP7 CP12 "Lemma"; do grep -q "$w" "$f" || echo "missing: $w"; done   # prints nothing
! grep -nE 'T[O]DO|T[B]D|[?][?][?]|lore[m]' "$f" "$g"          # exit 0
```
