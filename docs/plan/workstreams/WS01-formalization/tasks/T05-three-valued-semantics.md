---
id: WS01-T05
title: Three-valued online semantics with robustness intervals and latency bounds
workstream: WS01-formalization
owner: agent
status: in_progress
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


## Notes

Completion note of the worker run (status left at `in_progress` on purpose; the orchestrator sets `done` after review). Branch `ws01-t05-three-valued-semantics`, cut from `master` (the repository has no `main`). Files changed: `docs/formal/05-three-valued-semantics.md` (new), `docs/formal/golden/verdicts.yaml` (new), this task file (status and Notes only). No contract, ADR, other task file or registry file was edited.

**Done when, run as written (real output; the block was extracted from this file and run with `bash`).**

| Command | Exit | Output |
|---|---|---|
| `test -f "$f" && test -f "$g"` | 0 | (nothing) |
| headings loop over the eleven `## n ...` headings | 0 | prints nothing (no "missing heading") |
| `grep -c '^- id: V-' "$g"` | 0 | `24` |
| `grep -c 'hand_calculation:' "$g"` | 0 | `24` |
| loop over `PENDING`, `PREDICTED`, `VIOLATED`, `SATISFIED`, `CP3`, `CP6`, `CP7`, `CP12`, `Lemma` | 0 | prints nothing (no "missing:") |
| `! grep -nE 'T[O]DO\|T[B]D\|[?][?][?]\|lore[m]' "$f" "$g"` | 0 | prints nothing |
| whole block (`bash /tmp/t05/done_when_literal.sh`) | 0 | `24`, `24` |

Against the empty state (before any artefact existed) the same checks printed `files missing` and exited 1 (`test -f` fails first), so the check fails when the artefacts are absent. Also: `grep -rnE 'T[O]DO|T[B]D|[?][?][?]|lore[m]' docs/formal configs/registry` prints nothing (exit 1 = no match); `git diff --quiet -- docs/plan/02-interfaces.md` exits 0.

**Test section (items 1 to 16).** `/tmp/t05/checks_doc.py` (not committed): 16 groups of checks, all PASS, exit 0 (headings; separation and the absence of the banned phrase; completion set, empty maximum, infinities; Lemma 3 and the tightness caveat; Lemma 4; ties; marker `undecidable: channel_unavailable:presence`; CP12 serialisation; diagram, transition table, sticky warning, alpha allocation; predicted completion; loop and cost; latency table with the 24:02 example; A7; the 24 golden ids in order with the README key order and the `expected` keys; the F0 rows of every case equal to the README table, row for row, and the rows of the header comment; algorithm of at most ten lines; open points CP3, CP6, CP7, CP12 with ADR statements; no banned wording). The paper excerpt was compiled with `pdflatex` on a stub `IEEEtran` document (exit 0, no undefined reference after the second pass, figure and algorithm rendered and looked at).

**Full suite.** `pytest -q`: `175 passed in 0.89s`, exit 0. `python3 tools/check_plan.py`: `check_plan: OK (103 tasks, 18 contracts, 31 findings)`, exit 0.

**Golden file.** Written first (before the document). Reproduced by a reference implementation written for this task in `/tmp/t05` (not committed; own parser and interval evaluator of the T02 grammar, device-time input model with the reorder buffer, direct oracles): `check_golden.py` reports 24 of 24 cases matching in `state`, `t_eval_ms`, raw and normalised intervals, `decided_at_ms`, `pending_until_ms`, the guard, tie and marker annotations and the rho kind and value (`Phi(5 / (6 sqrt 2)) = 0.7221551...`; `alpha* = 0.1`, `rho = 0.9` for V-PRED-1 recomputed in exact rationals from the scores of C-1 of the WS01-T06 task text).

**Lemmas, hypotheses and randomized tests (all seeded; none is part of the repository; a test is stated as a test in the document).** Hypotheses are those named in section 2.1 and in each lemma of the document.

| Lemma | Statement (short) | Draws and edge cases | Counterexamples found |
|---|---|---|---|
| 1 causality | prefix depends on inputs received by `t_k + D`; late inputs never enter | 40,000 scenarios, 13,492,709 comparisons, 82,650 late inputs; independent streaming simulation of the acceptance rule, 40,000 draws, 498,164 inputs; mutants (future read, late accepted) caught | the literal reading of the `advance` watermark differs from the by-step rule in 1,092 of 40,000 draws when `advance` is not called at `t_k + D` (hence requirement R-late) |
| 2 isotonicity | smaller atom intervals give smaller intervals | proof; used by the tests of Lemmas 3 to 6 | none |
| 3 soundness | every completion lies in `[lo, hi]` | 200,000 draws (SCHED 43,298, RESP 38,450, INT 38,892, day end 79,360), 127,725 exhaustive; 1,437,987 completions with value exactly 0; decimal pressures: 150,000 draws, 0 outside | none; mutants caught; interval arithmetic is not tight when a position occurs twice (RANGE example `[-110, 90]` against exact `[-110, 15]`) |
| 4 stability | intervals nest, verdicts absorbing, transitions allowed | 40,000 scenarios, 441,655 instances (all seven templates), 4,910,330 (instance, step) pairs, 90,273 random warnings | none |
| 5 graded sign | the graded SCHED value has the sign of the decision-step value | 40,000 complete scenarios, 491,697 instances, 87,432 ties | the graded value differs from the decision-step one in 8,393 instances (all with decision value `-inf`) |
| 6 tightness | computed interval equals the exact range for the bodies | same 200,000 and 150,000 draws, endpoints attained; mutant caught | RANGE or SYS with an open pressure or inflation: not tight (stated, excluded) |
| 7 verdict agrees with T02 | VIOLATED implies `sigma^dec < 0`, SATISFIED implies `>= 0` | 40,000 complete scenarios, 491,697 instances | none |
| 8 certified severity | `N_s(hi)` at emission is never more severe than the resolved value | 40,000 scenarios, 236,103 VIOLATED instances | none (strictly milder in 25,459) |
| 9 forecaster independence | definitive records do not depend on the forecaster | 441,655 streams, 117,096 adversarial warnings; mutant caught | none (holds by construction; tests the specified machine) |
| 10 closed forms and O(1) state | closed forms and a left-to-right engine with constant state equal the recursion | 4,907,328 and 4,928,961 (instance, step) pairs | none |
| 11 decidedness | decided at `k_d` if no stale-open position in the decision window | 441,655 instances: 409,797 decided by `k_d`, 31,858 undecided, all with a stale-open position | none |
| 12 decision steps | exact first decision step and state for SCHED, RESP, day end | 40,000 scenarios (SCHED 38,386, RESP 25,454 with 429 ties at `k_d`, day end 40,000) | none; 2,850 early VIOLATED, all with `pre_i - bound_bp_lower - delta_resp < 0` |
| 13 latency | `0 <= L_ev < B + T_s`, `L_e2e < B + T_s + D` | all instances decided by `k_d`; largest ratio 0.9833 | none |
| 14 R equals F | future-time and past-time per-instance values equal | 85,000 seeds: SCHED 63,895 scenarios (116,881 instances), RESP 58,158 (115,607 instances, overlaps allowed) | none |
| 15 string against F | value identity, never weaker, exact disagreement predicate (A2*) | SCHED 3,953 disagreements, all predicted; RESP under (A3) 988, all predicted; 0 disagreements under (A2*) (SCHED 55,213 scenarios, RESP with (A3) 28,142) | without (A3) the string differs from F in 596 RESP scenarios (566 stronger, 30 weaker); the SCHED shadow counterexample is in section 8.2 |

Seven mutants of the reference implementation (wrong pressure bound, SCHED `hi` one step too small, tie rule removed (two tests), forecast that can decide, prefix reading the future, late inputs accepted) were each caught by the corresponding test (`/tmp/t05/mutate.py`: `all mutants caught: True`), so the tests are not vacuous. Floating point: a seeded search (3,000,000 draws, seed 7) shows that a different association order of the RESP margin puts `hi` one ulp below the value of a completion in 536,761 draws; the document requires the order of T02.

**Deviations from the task text.** (a) `status` is left `in_progress`, no other task status is touched, nothing merged (orchestrator override). (b) **V-LATE-2**: the task text gives `[10000, 10000]` ms and `(0.0056, 0.0056)`; the file gives `[0, 0]`, `(0, 0)`, SATISFIED by the tie rule, because slack is measured on grid times (merged T02 section 2.3, ceiling rule) and a device-time slack would make `hi = 19` min of V-SCHED-1 (also in the task text) unsound (a measurement at 09:10:30 has a device-time slack of 19.5 min); the task text value is kept in the file under `alternative_not_adopted` and discussed in section 9.4 and OP-T05-1. (c) V-INT-1 and V-INT-2 keep `intake` available and make only `presence` unavailable so that the marker is exactly `channel_unavailable:presence`; V-INT-3 needs a `presence` sample of 0 at device time 0 to reach `[-inf, -inf]` (a first sample at 20:55 would give `hi = -60000`, still VIOLATED). (d) The golden file carries the F0 rows used as a header comment and per case (`fixture.f0_rows`), as `ranking.yaml` does; extra keys are listed in its header. (e) Per-step emission of records (section 6.5) is stricter than the "activation and state change" default of WS05-T04 step 1.

**Contract gaps found (contract not changed; each recorded in section 11 for WS01-T08).** CP3: rule 1 says "iff" and cannot resolve a closed point-zero instance; adopted the tie rule (extension), plus CP3-b (`lo = 0 < hi` stays PENDING; refinement `lo >= 0` proposed). CP6: no way to say deadline elapsed but undecidable; adopted "stay PENDING with a log marker", proposed an optional `undecidable: str | None = None` field (and `guard_failed`). CP7: warm-up prefix as a known prefix, hypothesis (H-hist), open instances PENDING at trace end, API gap (`run_offline`, negative `TimeMs`). CP12: infinite endpoints, serialisation `"-inf"`/`"inf"` (JSON) and `-.inf`/`.inf` (YAML), no registry bound for `dose_count` and `inflation_ms` (T03 OP-8 can drop them). `pending_until_ms` on every record of the instance and `t_eval_ms` as grid time are adoptions of an ambiguous contract text.

**Questions inherited from earlier tasks, and their disposition** (full table in section 11.2). Adopted here: decision at `k_d` versus early SATISFIED (the value is defined at `k_d`, the verdict is decided by `k_d` and earlier whenever the interval resolves; WS05-T04 test 5 is consistent), graded lateness TG-4 (refinement records until `H_i`), ties, episodes (CG-14), latency reported (`max_latency_<id> + reorder_delay_ms`), CG-3 confirmed, A7 equivalence. Handed to WS01-T07: the severity field of a VIOLATED alert (the verdict layer fixes the certified severity `N_s(hi)`, OP-14, Lemma 8), use of the refinement record, aggregation of episodes. Handed to WS01-T06 and WS01-T07: the severity of a predicted alert (OP-15), the `rho` kind mapping, prediction instants and forecast clipping. Handed to WS01-T08: the ADRs for CP3, CP6, CP7, the widening (CG-2, TG-6), strict atoms if ever introduced, ADR-026 (INT form; independent of this semantics: the INT verdict is decided at the dispense step).

**Downstream tasks whose assumptions this document contradicts or refines (their files are not edited here; to be flagged by the orchestrator).** WS05-T04: step 4 (lateness must be by step, requirement R-late), step 1 (emission rule: one record per active instance per step), test 10 (the emitted state sequence repeats states; compare consecutive distinct states), test 11 ("no later record after a definitive one" conflicts with the SCHED refinement records, which keep the state), step 8 and WS05-T08 tests 5 and 15 (`predicted_sigma_norm` as `sigma_hat + q`: OP-15 still open). WS01-T07 line 40 (the "upper end" rule is now stated in section 3.7 of this document, not in T04). WS01-T06 (V-PRED-1 uses the fixture C-1 and C-2 of its task text; `sigma_hat` clipping into the interval, prediction instants). WS01-T03 OP-8 (the unset bounds for `dose_count` and `inflation_ms` are not needed).

**What a reviewer should check hardest.** (1) The hypotheses of each lemma, in particular (H-dom) (Lemma 3 is about completions; section 2.5 gives the counterexample and the adopted policy) and (H-hist). (2) The arithmetic of every golden case, in particular the grid slack of V-LATE-2 and the `hi` of V-SCHED-1 and V-RESP-1 (derivations in section 2.3). (3) The coverage of the state diagram (section 4.2, Lemmas 4, 9, 11) and the sticky-warning consequence for Proposition 1. (4) The latency table and Lemma 13 (hypotheses: no stale-open position, `advance` at every `t_k + D`, `k_d <= K`). (5) The A7 equivalence: `R = F` exact, the string equals `F` only under (A2*) and, for RESP, (A3); the shadow counterexample.
