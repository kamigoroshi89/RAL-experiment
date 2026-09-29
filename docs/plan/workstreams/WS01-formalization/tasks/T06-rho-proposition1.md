---
id: WS01-T06
title: Definition of rho per verdict type and Proposition 1 with proof
workstream: WS01-formalization
owner: agent
status: blocked
depends_on: ["WS01-T05"]
critical_path: true
non_negotiable: true
estimate_pd: 3
sources: ["analisi §4.4", "analisi §3.2", "analisi §2 R2 (weaknesses 2, 3, 4, 6)", "analisi §10 (2)"]
interfaces: ["02-interfaces.md#verdict", "02-interfaces.md#conformal-calibrator"]
review_items: ["R2-W2", "R2-W3", "R2-W4"]
---
## Obiettivo

Write `docs/formal/06-rho-proposition1.md` and `docs/formal/golden/conformal.yaml`: the operational definition of the confidence rho for each verdict type (measured, predicted, deterministic), Proposition 1 (one-sided conformal quantile guarantee `P(alert emitted and sigma >= 0) <= alpha` under exchangeability across patient episodes) with hypotheses and a complete proof, the "possible" variant with the quantile that actually makes it valid, the three caveats of analisi §4.4, the alpha allocation for many tests per patient-day, and hand-computed golden examples for WS05-T06. This task is non-negotiable (analisi §9). Proposition 1 is the formal piece that the analysis calls "small but new in your setting" and that R1 and R2 can check (analisi §4.4, §10 objection 2): it must be presented without inflation.

## Contesto

Unblocks when WS01-T05 is `done`. Read first:

1. `docs/formal/05-three-valued-semantics.md` (verdict states, predicted completion, the fixture case V-PRED-1 that refers to golden case C-2 of this task).
2. `docs/plan/02-interfaces.md#conformal-calibrator` (episode, score, `quantile`, `PredictedViolation`, rules 1 to 4) and `#verdict` (`Rho`, `RhoKind`, semantics 2).
3. `docs/source/analisi.md` §4.4 (table of rho, Proposition, three caveats, likely and possible), §3.2 (conformal literature to be cited, unverified), §2 R2 weaknesses 2, 3, 4, 6, §10 objection 2.
4. `docs/plan/03-decisions.md` ADR-008.
5. `docs/plan/workstreams/WS01-formalization/README.md` (fixture registry F0, golden format, CP4).

## File toccati

- `docs/formal/06-rho-proposition1.md` (create)
- `docs/formal/golden/conformal.yaml` (create)

## Test

Document task: verification checks, plus golden cases written first and reproduced by the document.

1. **Headings.** `## 1 What rho answers`, `## 2 Rho per verdict type`, `## 3 Measured violations`, `## 4 Conformal setting`, `## 5 Proposition 1`, `## 6 The three caveats and alpha allocation`, `## 7 Recalibration and shift`, `## 8 Golden examples`, `## 9 Paper excerpt (Sections IV-B and IV-C)`, `## 10 Open points for WS01-T08`.
2. **Rho versus kappa (R2 weakness 3).** Section 1 separates (i) how certain the violation is (rho) from (ii) how certain the event is authentic or due to a given cause (kappa, attribution), uses the workshop Table I value rho = 0.42 on a deterministic counter as the example of the confusion, and states that rho is defined only for VIOLATED and PREDICTED_VIOLATION records and is `None` for SATISFIED and PENDING (a "confidence" on a satisfied event has no semantics, analisi §4.6 row 07:00).
3. **Table of rho.** Section 2 has one row per `RhoKind` with definition, `Rho.value`, `Rho.kind`, the exact `Rho.guarantee` string, `Rho.alpha` and the exact `Rho.assumptions` strings: MEASURED (`P(sigma_true < 0 | measurement)` under the declared device error model, conditional on the adequacy of that model), PREDICTED (`rho = 1 - alpha*` with `alpha* = inf{alpha : sigma_hat + q_{1-alpha} < 0}`; marginal over patient episodes under exchangeability; `alpha` is the configured level), DETERMINISTIC (`rho = 1` for an event-log predicate, conditional on the integrity of the log; authenticity goes to kappa).
4. **Measured rho.** Section 3 states the model (measured value equals true value plus independent Gaussian error with standard deviation `cuff_error_sd`, zero bias after correction, flat prior on the true value; silent bias is a C2 case that rho does not see), and derives: single limit `Phi((x - limit) / s)`; band `Phi((lo - x) / s) + Phi((x - hi) / s)` for the two disjoint violation regions; difference of two measurements (RESP) with standard deviation `s * sqrt 2`, `Phi((delta_resp - r) / (s * sqrt 2))`; obligation-unmet and log predicates are DETERMINISTIC. It states that `cuff_error_sd` is unset in the registry until WS00-T07 and its source is verified by a human (analisi §5.1), and that if the benchmark generator draws cuff errors from the same standard deviation then the calibration of measured rho is trivially perfect, so WS08 needs a run with a mismatched value (own inference, labelled as such).
5. **Conformal setting.** Section 4 defines: the calibration unit (a patient episode: one decision point of one template instance of one patient-day), the score `R = sigma_tilde_true - sigma_hat` on normalised values, the protocol (forecaster fitted on the train split only; calibration and test episodes from different patients; one designated prediction instant per episode), the upper quantile `q_{1-alpha}` as the `ceil((n+1)(1-alpha))`-th smallest of the `n` scores (plus infinity if that rank exceeds `n`), the lower quantile `q^lo_alpha` as the `floor((n+1) alpha)`-th smallest (minus infinity if that rank is below 1), the rank computed in exact arithmetic (a floating-point product can change the rank, golden case C-4), and `alpha* = (n + 1 - m) / (n + 1)` with `m = #{i : R_i < -sigma_hat}` so that `rho = 1 - alpha* = m / (n + 1)` and `rho <= n / (n + 1)`.
6. **Proposition 1.** Section 5 states hypotheses H1 (the scores of the `n` calibration episodes and the test episode are exchangeable), H2 (forecaster and normalisation independent of the calibration and test episodes), H3 (quantile as in check 5) and the conclusion `P(sigma_hat + q_{1-alpha} < 0 and sigma_tilde >= 0) <= alpha`, with a complete rank-based proof that covers ties. It states the corollary that `alpha*` is a conformal p-value for the null `sigma >= 0` (`P(alpha* <= alpha and sigma >= 0) <= alpha` for every alpha), that rho is not the probability that the violation occurred, and that the joint probability is not the precision of the alerts.
7. **Sufficient condition for H1 (own inference).** Section 5 states a sufficient condition (episodes from distinct patients drawn independently from the population, one prediction instant per episode) and that pooling several episodes of one patient in calibration breaks H1 in general, so the effective sample size is the number of patients; it links this to the split by patient of the contract.
8. **The "possible" variant (CP4).** Section 5 states Proposition 1b: with the lower quantile, `P(sigma_tilde < 0 and sigma_hat + q^lo_alpha >= 0) <= alpha` (missed violations bounded), proves it, and states that the form `sigma_hat - q_{1-alpha} < 0` of analisi §4.4 and of contract rule 2 of `#verdict` is valid only if the distribution of `R` is symmetric about zero; golden case C-3 shows the two forms disagree. It states the consequence for the contract (CP4: `ConformalCalibrator` exposes only the upper quantile).
9. **Three caveats and allocation (R2 weakness 4).** Section 6 states the caveats with the wording of analisi §4.8: unit is the patient episode and never the time step; coverage is "marginal over patient episodes under exchangeability", not conditional on the patient and not "distribution-free" without qualifiers; with many tests per patient-day the level must be allocated. It defines `alpha_per_test = alpha_total / n_tests` (union bound, no independence needed) where `n_tests` counts templates times instances times prediction instants in a patient-day, the guarantee "probability of at least one false predicted alert per patient-day at most alpha_total", the minimum calibration size `n >= ceil(1 / alpha_per_test) - 1`, and the contract hook `AlphaAllocation.per_test`.
10. **Recalibration and shift (R2 weakness 6).** Section 7 states the recalibration rule of contract rule 4 (every model update triggers `fit` on held-out episodes; a calibrator older than the model version is refused), that under distribution shift (calibrate on one cohort, test on the other) Proposition 1 is not claimed and the adaptive variant is evaluated empirically in A6 (adaptive conformal inference is cited as `[ref-needed: WS03]`, analisi §3.2).
11. **Coverage test design.** Section 8 states the property tests for WS05-T06: for continuous i.i.d. scores the coverage of `q_{1-alpha}` is exactly `k / (n + 1)` with `k` the rank of check 5 (an exact identity, checked without Monte Carlo), and a Monte Carlo check uses a tolerance of three standard errors of the estimate rather than a chosen constant.
12. **Golden file.** `docs/formal/golden/conformal.yaml` contains the seven cases below in the README format with `hand_calculation`.
13. **Paper excerpt.** Section 9 gives the table of rho (three rows), Proposition 1 with a 3 to 4 line proof (analisi §7) and the two-sentence caveat paragraph, in LaTeX.
14. **Open points.** Section 10 lists CP4 and any other tension (for example whether `Rho.alpha` of a predicted alert is the configured level or `alpha*`; recommended: the configured level, with `alpha*` recoverable from `value`).

Golden cases:

| id | Content |
|---|---|
| C-1 | Fixture scores `R = [-0.30, -0.22, -0.18, -0.12, -0.05, 0.00, 0.04, 0.09, 0.15]`, `n = 9`. Upper quantile `q_{1-alpha}`: alpha 0.05 gives plus infinity (rank 10 > 9); 0.1 gives 0.15 (rank 9); 0.2 gives 0.09 (rank 8); 0.3 gives 0.04 (rank 7). Lower quantile `q^lo_alpha`: 0.05 gives minus infinity (rank 0); 0.1 gives -0.30 (rank 1); 0.2 gives -0.22 (rank 2); 0.3 gives -0.18 (rank 3). For continuous i.i.d. scores the coverage of `q_{0.8}` is exactly 8/10. |
| C-2 | Variant "likely" at alpha 0.2 (`q = 0.09`): sigma-hat -0.15 is emitted (-0.06 < 0), `m = 8`, `alpha* = 0.2`, rho 0.8; -0.05 is not emitted (0.04 >= 0), `m = 7`, `alpha* = 0.3`, rho 0.7; -0.40 is emitted (-0.31), `m = 9`, `alpha* = 0.1`, rho 0.9; +0.30 is not emitted (0.39), `m = 0`, `alpha* = 1.0`, rho 0.0; -1/3 is emitted (-0.2433), `m = 9`, `alpha* = 0.1`, rho 0.9 (used by V-PRED-1 of T05). |
| C-3 | Variant "possible" at alpha 0.2 (`q^lo = -0.22`): sigma-hat +0.15 is emitted (0.15 - 0.22 = -0.07 < 0) while the symmetric form `0.15 - 0.09 = +0.06` is not; sigma-hat +0.25 is not emitted by either (0.03 and 0.16). |
| C-4 | Rounding: `R_i = i/100` for `i = 1..99` (`n + 1 = 100`). Upper quantile at alpha 0.41: exact rank `ceil(100 * 0.59) = 59`, value 0.59; the floating-point product `100 * (1 - 0.41)` is 59.00000000000001 and gives rank 60 and value 0.60. Lower quantile at alpha 0.29: exact rank `floor(100 * 0.29) = 29`, value 0.29; the floating-point product is 28.999999999999996 and gives rank 28 and value 0.28. The expected values are the exact ones. |
| C-5 | Minimum calibration size `ceil(1/alpha) - 1`: alpha 0.05 gives 19; alpha 0.005 gives 199; `alpha_total` 0.05 with `n_tests` 10 gives `alpha_per_test` 0.005 and 199. With `n = 9` and alpha 0.05 no predicted alert can ever be emitted (C-1). |
| C-6 | Measured rho with `cuff_error_sd` 6 (F0): range limit 140, bp 152 gives `Phi(2)` = 0.9772; bp 140 gives 0.5; bp 146 gives `Phi(1)` = 0.8413; band low limit 110, bp 104 gives `Phi(1)` = 0.8413 (the other region contributes about 1e-9); RESP with `delta_resp` 10 and drop 5 gives `Phi(5 / (6 sqrt 2))` = 0.7222; RESP with `bp_pre` 138, bp 152 (drop -14) gives `Phi(24 / (6 sqrt 2))` = 0.9977. |
| C-7 | Deterministic and absent: COUNT with `c_d` 3 and limit 2 gives kind DETERMINISTIC, value 1.0; a SATISFIED record and a PENDING record give rho `None`. |

## Passi

1. **Golden first.** Write `docs/formal/golden/conformal.yaml` with C-1 to C-7 (for C-1 and C-2 include the sorted scores, the ranks and the hand calculation of `alpha*`, for example `alpha* = (9 + 1 - 8) / 10 = 0.2`; for C-6 include the standard normal values to four decimals). Recompute each independently once more, including the exact-rank cases of C-4.
2. Write sections 1 to 3 (rho versus kappa, table with the exact guarantee and assumption strings, measured model and derivations).
3. Write section 4 (setting, score, protocol, quantile ranks in exact arithmetic, `alpha*`, `rho = m / (n + 1)`), then section 5: state Proposition 1, prove it (write the rank argument in full: under H1 the rank of the test score among the `n + 1` scores is uniformly distributed after random tie-breaking, `R_{n+1} > q` implies rank above `k`, hence probability at most `1 - k/(n+1) <= alpha`), then the corollary, the sufficient condition for H1, and Proposition 1b with its proof and the symmetry remark.
4. Write section 6 (caveats, allocation, minimum sample size) and section 7 (recalibration, shift).
5. Write section 8 (property-test design and pointer to the golden file), section 9 (paper excerpt), section 10 (open points).
6. Run "Done when"; set `status` to `done`; commit `WS01-T06: add rho definitions and Proposition 1`.

## Done when

```bash
cd "/home/gab/Desktop/RAL experiment"
f=docs/formal/06-rho-proposition1.md; g=docs/formal/golden/conformal.yaml
test -f "$f" && test -f "$g"
for h in "## 1 What rho answers" "## 2 Rho per verdict type" "## 3 Measured violations" "## 4 Conformal setting" \
         "## 5 Proposition 1" "## 6 The three caveats and alpha allocation" "## 7 Recalibration and shift" \
         "## 8 Golden examples" "## 9 Paper excerpt (Sections IV-B and IV-C)" "## 10 Open points for WS01-T08"; do
  grep -qF "$h" "$f" || echo "missing heading: $h"; done       # prints nothing
grep -c '^- id: C-' "$g"                                       # prints 7
grep -c 'hand_calculation:' "$g"                               # prints 7
for w in "Proposition 1b" exchangeab "marginal over patient episodes" DETERMINISTIC MEASURED PREDICTED CP4 "p-value"; do
  grep -q "$w" "$f" || echo "missing: $w"; done                 # prints nothing
grep -q 'ceil' "$f" && grep -q 'floor' "$f"
! grep -nE 'T[O]DO|T[B]D|[?][?][?]|lore[m]' "$f" "$g"          # exit 0
```
