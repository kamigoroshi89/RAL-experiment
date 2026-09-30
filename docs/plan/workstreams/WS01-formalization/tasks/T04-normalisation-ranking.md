---
id: WS01-T04
title: Normalised robustness and lexicographic alert ranking
workstream: WS01-formalization
owner: agent
status: ready
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
