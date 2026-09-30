---
id: WS01-T04
title: Normalised robustness and lexicographic alert ranking
workstream: WS01-formalization
owner: agent
status: in_progress
depends_on: ["WS01-T02"]
critical_path: true
non_negotiable: true
estimate_pd: 2
sources: ["analisi §4.2", "analisi §2 R1 (weakness 2)", "analisi §5.6 (A3)", "analisi §5.5"]
interfaces: ["02-interfaces.md#template"]
review_items: ["R1-W2", "AE-5"]
---
## Obiettivo

Write `docs/formal/04-normalisation-ranking.md` and `docs/formal/golden/ranking.yaml`: the definition of clinically normalised robustness `sigma_tilde = clip(sigma / s, -1, 1)`, its properties, the lexicographic ordering of alerts (clinician priority first, normalised robustness within a priority), the alternatives to cite (AGM robustness, weighted STL, ordinal NEWS2-style bands), the reason why normalising by conformal interval width is forbidden, and the definition of the ablation A3 null ranking. Golden examples are hand-computed for WS05-T03 and WS08-T03. This task is non-negotiable (analisi §9). It closes R1 weakness 2 (a `min` over mmHg, minutes and doses is empty of meaning) and the unit part of AE-5. Scales and priorities are registry values, illustrative and unverified until WS00-T07.

## Contesto

Unblocks when WS01-T02 is `done`. Read first:

1. `docs/formal/02-templates.md` (margin and guard rule, units per template, registry names `scale_<id>` and `priority_<id>`).
2. `docs/plan/02-interfaces.md#template` (`normalise`, `rank_alerts`, the rule against normalising by conformal width) and `#alert` (`priority`, `sigma_norm`).
3. `docs/source/analisi.md` §4.2 (three steps, alternatives, prohibition), §2 R1 weakness 2, §5.6 (A3), §5.5 (last bullet: agreement with clinician ranking).
4. `docs/plan/03-decisions.md` ADR-009.
5. `docs/plan/workstreams/WS01-formalization/README.md` (fixture registry F0, golden format, CP5).

## File toccati

- `docs/formal/04-normalisation-ranking.md` (create)
- `docs/formal/golden/ranking.yaml` (create)

## Test

Document task: verification checks.

1. **Headings.** `## 1 The unit problem`, `## 2 Normalised robustness`, `## 3 Where normalisation is applied`, `## 4 Lexicographic ranking`, `## 5 Alternatives`, `## 6 Why not the conformal width`, `## 7 Ablation A3 and baseline B3`, `## 8 Optional agreement with clinician ranking`, `## 9 Paper excerpt (Section IV-B, severity)`, `## 10 Open points for WS01-T08`.
2. **Definition and properties.** Section 2 defines `sigma_tilde = clip(sigma / s, -1, 1)` with `s > 0` from the registry (`scale_<template>`), maps plus and minus infinity to +1 and -1, and proves or states as lemmas: range `[-1, 1]`; sign preservation (`sigma_tilde >= 0` iff `sigma >= 0`, so the Boolean verdict is unchanged); monotonicity; scale equivariance `normalise(k*sigma, k*s) = normalise(sigma, s)` for `k > 0`; identity zone `normalise(sigma, s) = sigma / s` when `|sigma| <= s`. It lists these as the Hypothesis properties WS05-T03 must implement.
3. **Errors.** Section 2 states that `s <= 0`, an unset scale or a NaN input raise a specific error (no silent default), consistent with the registry rules of T03.
4. **Meaning of the scale.** Section 2 states that `s` is "the clinically significant deviation" fixed with the clinician (analisi §4.2), gives the three illustrative examples of the analisi (20 mmHg, 30 min, 1 dose) as "illustrative, unverified", and does not assign a scale to any template the analisi does not name (those are unset until WS00-T07).
5. **Where applied.** Section 3 states: normalisation is per template decision, using the template's own unit (T02 margin rule); `min` and `max` over templates are meaningful only on normalised values and are used for reporting (for example Fig. 2), while alerts are per template instance and are never merged into one number; raw robustness stays inside `spec` and in baseline B3 (native units).
6. **Ranking.** Section 4 defines the total order with key `(priority ascending, sigma_tilde ascending, t_ms ascending, instance_key ascending)`, states that priority 1 is the highest (CP5: the contract does not state the direction), that priorities come from the registry (`priority_<id>`; only the order hold > range > sched is given by the analisi, illustratively), and explains with the example that a timing -0.7 is not compared with a pressure -0.6 as if equivalent. It decides how a PREDICTED_VIOLATION alert ranks against a VIOLATED alert of the same priority (recommended: VIOLATED first, which extends the literal docstring of `rank_alerts` and therefore needs an ADR proposed by T08) and whether the sigma-tilde of an alert is frozen at emission (recommended: frozen, with the limitation that a timing violation is certified only as late by at least the elapsed time; the lateness at resolution goes to the log).
7. **Alternatives.** Section 5 describes AGM robustness, weighted STL and ordinal NEWS2-style bands as alternatives, states what each would need (AGM and weighted STL still require normalised predicates, analisi §4.2), and marks every citation `[ref-needed: WS03]` without writing authors or years from memory.
8. **Forbidden normalisation.** Section 6 states the prohibition of normalising by the width of a conformal interval and shows the counterexample of golden case RK-6 (equal severity, different width, opposite ordering after width normalisation).
9. **A3 and B3.** Section 7 defines the A3 null ranking (ascending raw sigma in native units with units ignored, ties by the same tie-break) and the raw-robustness view used by B3, and shows on RK-4 that the two orderings are exact reverses.
10. **Agreement study.** Section 8 states, in one paragraph, how `severity_rank_agreement` (Kendall tau or Spearman, `#metrics`) compares the lexicographic order with a clinician order in the optional vignette study (WS11), without choosing clinician data.
11. **Golden file.** `docs/formal/golden/ranking.yaml` holds the cases below in the README format, each with `hand_calculation`.
12. **Paper excerpt.** Section 9 is the Section IV-B text on severity (about 0.15 page; the rho part comes from T06), including the prohibition and one alternative sentence.
13. **Open points.** Section 10 lists CP5 (range of `sigma_norm`, priority direction, predicted versus violated order) and any other tension, each with the resolution adopted.

Golden cases (F0):

| id | Input | Expected |
|---|---|---|
| N-1 | `normalise(-12, 20)` | -0.6 |
| N-2 | `normalise(15, 20)` | 0.75 |
| N-3 | `normalise(-60, 20)` | -1.0 (clipped) |
| N-4 | `normalise(0, 20)` | 0.0 |
| N-5 | `normalise(-1260000, 1800000)` (21 min late, scale 30 min) | -0.7 |
| N-6 | `normalise(-1, 1)` (one dose over the limit) | -1.0 |
| N-7 | `normalise(-inf, 20)` and `normalise(+inf, 20)` | -1.0 and +1.0 |
| N-8 | `normalise(5, 0)` | error (scale must be positive) |
| N-9 | `normalise(nan, 20)` | error |
| N-10 | `normalise(-12 * 3, 20 * 3)` | -0.6 (scale equivariance with N-1) |
| RK-1 | alerts: hold sigma-tilde -0.3 (priority 1), range -0.6 (priority 2), sched -0.7 (priority 3), given in shuffled order | order hold, range, sched (sched has the most negative value but the lowest priority) |
| RK-2 | two range alerts, `range@09:05` -0.6 and `range@12:24` -0.3 | `range@09:05` first |
| RK-3 | same priority 2 and same sigma-tilde -0.6; `t_ms` 50 versus 100; then equal `t_ms` with keys `a` and `b` | earlier `t_ms` first; then `a` before `b` |
| RK-4 | hold sigma -6 mmHg, range -12 mmHg, sched -1260000 ms | lexicographic on normalised values: hold, range, sched; A3 null ranking on raw values: sched, range, hold (exact reverse) |
| RK-5 | same priority; one VIOLATED with sigma-tilde -0.2 and one PREDICTED_VIOLATION with -0.5 | literal contract docstring: predicted first; recommended extension: violated first; both recorded, the file states which one the ADR of T08 must confirm |
| RK-6 | two predicted alerts, sigma-hat -0.5 each, conformal half-width 0.4 and 0.05 | severity keys equal (-0.5 and -0.5); width-normalised values would be -1.25 and -10, which is the forbidden behaviour |

## Passi

1. Write `docs/formal/golden/ranking.yaml` with N-1 to N-10 and RK-1 to RK-6 (times in ms, alerts with `tau`, `instance_key`, `priority`, `sigma_norm`, `t_ms`, `verdict`), each with the hand calculation (for N-5: `-1260000 / 1800000 = -0.7`).
2. Write sections 1 and 2 (unit problem with the three unit examples of the analisi; definition; lemmas with short proofs; error rules).
3. Write section 3 (where applied) and section 4 (ranking, priority direction, tie-break, predicted versus violated, frozen sigma-tilde); check RK-1 to RK-5 against your rules.
4. Write sections 5 to 8 (alternatives, prohibition with RK-6, A3 and B3, agreement study).
5. Write section 9 (paper excerpt) and section 10 (open points).
6. Run the checks of "Done when"; set `status` to `done`; commit `WS01-T04: add normalised robustness and ranking`.

## Done when

```bash
cd "/home/gab/Desktop/RAL experiment"
f=docs/formal/04-normalisation-ranking.md; g=docs/formal/golden/ranking.yaml
test -f "$f" && test -f "$g"
for h in "## 1 The unit problem" "## 2 Normalised robustness" "## 3 Where normalisation is applied" \
         "## 4 Lexicographic ranking" "## 5 Alternatives" "## 6 Why not the conformal width" \
         "## 7 Ablation A3 and baseline B3" "## 8 Optional agreement with clinician ranking" \
         "## 9 Paper excerpt (Section IV-B, severity)" "## 10 Open points for WS01-T08"; do
  grep -qF "$h" "$f" || echo "missing heading: $h"; done      # prints nothing
grep -c '^- id: N-' "$g"                                     # prints 10
grep -c '^- id: RK-' "$g"                                    # prints 6
grep -c 'hand_calculation:' "$g"                             # prints 16
for w in AGM "weighted STL" NEWS2 CP5 monoton; do grep -qi "$w" "$f" || echo "missing: $w"; done   # prints nothing
! grep -nE 'T[O]DO|T[B]D|[?][?][?]|lore[m]' "$f" "$g"        # exit 0
```

## Notes

Completion note of the worker run (status left at `in_progress` on purpose; the orchestrator sets `done` after review). Branch `ws01-t04-normalisation-ranking`, cut from `master` (the repository has no `main`).

**Done when, run as written (real output).**

| Command | Exit | Output |
|---|---|---|
| `test -f "$f" && test -f "$g"` | 0 | (nothing) |
| headings loop over the ten `## n ...` headings | 0 | prints nothing (no "missing heading") |
| `grep -c '^- id: N-' "$g"` | 0 | `10` |
| `grep -c '^- id: RK-' "$g"` | 0 | `6` |
| `grep -c 'hand_calculation:' "$g"` | 0 | `16` |
| loop over `AGM`, `weighted STL`, `NEWS2`, `CP5`, `monoton` | 0 | prints nothing (no "missing:") |
| `! grep -nE 'T[O]DO\|T[B]D\|[?][?][?]\|lore[m]' "$f" "$g"` | 0 | prints nothing |

Against the empty state (before the artefacts existed) the same script printed `missing heading` for all ten headings, empty counts and `missing: AGM` (exit 1 on the first `test -f`), so the checks fail when the artefacts are absent.

**Test section (items 1 to 13).** Verified by an independent script that is not committed (`/tmp/t04/verify.py`; final run: 196 checks PASS, 0 FAIL, exit 0). It covers: (1) exactly ten H2 headings, in order; (2) and (3) the definition, infinities, lemmas, the Hypothesis property list, error behaviour (keywords in section 2 and the reference implementation); (4) the three illustrative scales and no scale assigned outside the registry seed; (5) section 3 keywords; (6) the order key string, direction, RK-1 to RK-5 evaluated by two independent implementations of the sort; (7) section 5 markers and no year or author in section 5; (8) RK-6 including the reversed order under the forbidden width normalisation; (9) RK-4 A3 null order and exact reverse; (10) section 8 keywords; (11) golden file: 16 cases in the README key order, each with `hand_calculation`; every `normalise` case evaluated with exact rationals (`fractions.Fraction`, compared with the decimal literal) and with the float implementation; every f0 row compared with the F0 table parsed from the WS01 README; (12) section 9 size (60 to 260 word tokens, counting the framing paragraph and LaTeX commands; the excerpt body is about 150 words, roughly 0.15 page); (13) section 10 keywords. Mutation check: three deliberately wrong golden values (N-5, RK-4 A3 order, RK-6 forbidden value) were each reported as FAIL and then restored.

Properties verified with fixed seeds (20260930 to 20260932, 7 and 11): range, sign preservation, monotonicity, scale equivariance (exact rationals over 20000 trials; float with integer-valued arguments exactly equal; general floats within 1e-12), identity zone, saturation, 1/s-Lipschitz, interval enclosure, dependence on the scale (Lemma 7), float monotonicity/saturation/sign away from underflow, the underflow caveat (`-5e-324 / 1e10` is `-0.0`), and, over 3000 random alert sets with ties on every component, permutation, totality, transitivity, no priority inversion, severity order inside a priority, determinism under shuffling, agreement of two independent sort implementations, plus stability, idempotence and the `K1` (VIOLATED first) lemma.

**Full suite.** `pytest -q`: `175 passed in 0.86s`, exit 0. `python3 tools/check_plan.py`: `check_plan: OK (103 tasks, 18 contracts, 31 findings)`, exit 0.

**Deviations from the task text.** (a) `status` is left `in_progress` and no other task status is touched (orchestrator override). (b) The golden file is a top-level YAML list (README format) and carries the F0 rows it uses as a header comment and as a per-case `fixture.f0_rows` mapping, not a `fixture_registry` section as `templates.yaml` does; the F0 table itself stays single-sourced in `templates.yaml`. (c) RK-2 has an extra input/expected pair (`alerts_swapped_times`, `order_swapped_times`): the specified case does not separate `sigma_norm` from `t_ms` (both favour `range@09:05`), so the same two values with the times swapped were added inside the same case; the case count is unchanged. (d) RK-5 and RK-6 use `resp` alerts (F0 fixture-only `priority_resp = 2`, `scale_resp = 20`), because a RANGE instance is decided at its measurement and has nothing pending to predict. (e) N-8 lists three further inputs that must raise (`scale = -20`, NaN, `+inf`); the task specified only `scale = 0`. (f) The task's "Passi" 6 says to set `status: done` and commit `WS01-T04: add normalised robustness and ranking`; not done, per the override; commits are `WS01-T04: add ranking golden file ...` and `WS01-T04: add normalised robustness and ranking document`, plus the one that adds this note.

**Contract gaps and tensions (recorded, contracts untouched; details in section 10 of the document).** OP-1 range of `sigma_norm` (`[-1, 0)` for VIOLATED, `[-1, 1]` for PREDICTED_VIOLATION); OP-2 priority direction (1 = highest); OP-3 VIOLATED before PREDICTED_VIOLATION within a priority extends the `rank_alerts` docstring and needs an ADR proposed by WS01-T08 (until then the literal key is implemented, RK-5 records both); OP-4 severity of a predicted alert is the normalised point forecast (to be confirmed by WS01-T06 and T07); OP-6 the tie-break `(t_ms, instance_key)` is not in the docstring, ADR-024's structural type (priority and sigma_norm only) and the WS05-T03 test "stable on ties" need adjusting, and `Alert` has no patient identifier although `instance_key` is unique only within a care plan; OP-7 the contract names no error types; OP-8 `Alert` carries no raw sigma, so ablation A3 joins the verdict record on `instance_key`, and the null ranking removes priority together with normalisation (`ours-A3-prio` isolates normalisation); OP-9 frozen `sigma_tilde` versus the graded lateness of SCHED (TG-4 of `02-templates.md`); OP-10 with registry 0.1.0 HOLD cannot be normalised, COUNT cannot be ranked, RESP, SYS and INT neither.


### Fix round 1

Independent review found one blocker and several minor defects in the text of `docs/formal/04-normalisation-ranking.md`. Only that file and this Notes section changed; `docs/formal/golden/ranking.yaml` is unchanged (all 16 cases re-verified with a new script, 0 mismatches). Status left at `in_progress`.

- **B1 (blocker, section 7, variant A3-prio).** The claim "differs only among alerts of the same priority whose templates have different units" was false. Fixed: A3-prio differs wherever normalisation changes the within-priority order (different scales, including different units; clip ties at `-1` broken by `t_ms` in the full order). Two fixture-only counterexamples added as worked lines: (i) same unit and scale, `-40` at t 100 and `-60` at t 200: full order (a, b), A3-prio (b, a); (ii) same unit, scales 10 and 40, `-10` and `-12`: full order (a, b), A3-prio (b, a). Checked that RK-4 (A3-prio equals the full order, the three priorities differ), the COUNT/RANGE example and OP-8 stay true. Also hedged section 4.7 ("under the `-inf` choice").
- **M1** Lemma 3 and section 2.3 (c): strictly increasing in exact arithmetic, non-decreasing in floats (example pair and underflow named).
- **M2** P-N4, section 2.3 (e) and OP-13: precondition that `k * s` is finite and positive.
- **M3** Lemma 6 and section 2.3 (d): Lipschitz bound in exact arithmetic only; not a Hypothesis property.
- **M4** Section 5: the claim about AGM, weighted STL and ordinal bands not replacing priority removed; replaced by a statement that the analisi does not say, "to be checked against the papers in WS03-T06 `[ref-needed: WS03]`".
- **M5** Paper excerpt: "of a different priority" added.
- **M6** Section 4.6: RK-6 now cited only for the ban on dividing by the width; excluding `sigma_hat + q` is a design proposal (OP-4) with its own reasons.
- **M8** `donze-maler-robust` added to the time-robustness candidate keys (section 1.3 and OP-12).
- **Downstream disclosure** (new open points, nothing decided, no other task file edited): OP-14 (upper-end rule for a VIOLATED alert, WS01-T07, WS01-T08 R3, WS05 README D7, WS05-T07 test 3), OP-15 (`predicted_sigma_norm` as `sigma_hat + q` in WS05-T04 step 8 and WS05-T08 tests 5 and 15, versus OP-4), OP-16 and OP-6 (c) (WS05-T03 test 7 and test 9), and one sentence in section 2.2 for the golden loader (N-7 list, N-8 and N-9 `expected.error`).

Verification after the fixes: "Done when" block run as written, all exit 0 (counts 10, 6, 16, no missing heading or word, no placeholder); the uncommitted checker `/tmp/t04/verify.py` reports no failure; `pytest -q` 175 passed; `python3 tools/check_plan.py` OK (exit 0).
