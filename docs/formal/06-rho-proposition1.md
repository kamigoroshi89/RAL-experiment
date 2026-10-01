# 06 The confidence rho per verdict type and Proposition 1

Document WS01-T06. Feeds paper Sections IV-B (the definitions of rho) and IV-C (Proposition 1 with its short proof), the conformal calibrator of WS05-T06 and the predictive integration of WS05-T08, the baselines B5 (WS06-T06) and the measured-versus-predicted comparisons of WS06-T05, the ablations A1 (conformal replaced by a point forecast), A2 and A6 (distribution shift) of WS08, and the alert tuple of WS01-T07. Draft for the M1 freeze (WS01-T08); it changes no contract of `docs/plan/02-interfaces.md` (gaps and clarifications are recorded in section 10). It builds on `docs/formal/05-three-valued-semantics.md` (WS01-T05, "T05" below: verdict states, the predicted channel of its section 5, the golden cases V-PRED-1 to V-PRED-3 that use the fixture of C-1 and C-2 of this document; its open points OP-T05-4, OP-T05-10 and OP-T05-16), on `docs/formal/04-normalisation-ranking.md` (WS01-T04, "T04": normalised robustness; open points OP-4, OP-14, OP-15 on the severity of predicted and VIOLATED alerts), on `docs/formal/02-templates.md` (WS01-T02, "T02": the seven templates, the margin and guard rule) and on `docs/formal/03-parameter-registry.md` with `configs/registry/hypertension.yaml` (WS01-T03, "T03": `cuff_error_sd` is declared `unset`; open point OP-7). Validation in this project is technical and pre-clinical: nothing in this document is a clinical claim, and no sentence about "coverage" or "confidence" refers to patients in a hospital. Every numeric clinical value is either fixture arithmetic (FIXTURE-ONLY, fixture registry F0 of `docs/plan/workstreams/WS01-formalization/README.md`) or a value of analisi §4.1 labelled "illustrative, unverified" (ADR-020); the calibration scores of the golden file have no clinical meaning and carry no claim about any forecaster.

**What is proved and what is tested.** Proposition 1, Proposition 1b, Lemma 1 and the union-bound statement of section 6 are proved in this document. Every statement that can be tested was also tested with seeded scripts that are not part of the repository (exact rational enumeration, Monte Carlo with a tolerance of three standard errors, quadrature); section 5.8 and the paragraphs "Checked" give the number of draws and the distributions. These are tests, not proofs: a passing test does not extend a hypothesis, and no result of the paper is claimed from them.

**Ground truth discipline.** Nothing in this document reads `LatentDay` or `GroundTruthEvent` at inference. The conformal calibrator receives numbers (`sigma_hat`, `sigma_true`) offline at calibration time, and at inference only the quantile; where the score target could be a latent quantity the choice is stated in section 4.1 and the use of the latent trace is restricted to the fit step of a benchmark run.

**Notation.** `sigma` is raw robustness (native unit), `sigma_tilde` (code `sigma_norm`) is normalised robustness in `[-1, 1]` (T04); `sigma_hat` is the normalised forecast of `sigma_tilde`, `sigma_tilde_true` (also written `sigma_true` in the contract) the normalised robustness of the completed trace. "Robustness" is used only for STL semantics. `Phi` is the standard normal cdf, `s` is `cuff_error_sd`. `n` is the number of calibration episodes, `alpha` a level in `(0, 1)`, `alpha_star` is written `alpha*`. `R_i` are scores, `R_(i)` the `i`-th smallest. The `kappa` of the alert tuple is the attributed cause (C1, C2, C3, UNDETERMINED); `rho` is never an attributed cause.

**Parameters used.** All are registry names or fixture rows; none is invented here.

| Name | Unit | Origin |
|---|---|---|
| `cuff_error_sd` | mmHg | registry: `unset` (T03, awaiting WS00-T07); F0 value 6 mmHg is FIXTURE-ONLY |
| `bp_band_low`, `bp_band_high` | mmHg | analisi §4.1 (illustrative, unverified): 110 and 140 in F0 |
| `bp_hold_threshold` | mmHg | analisi §4.1 (illustrative, unverified): 100 in F0 |
| `delta_resp` | mmHg | registry: `unset`; F0 value 10 mmHg is FIXTURE-ONLY |
| `bound_bp_lower` | mmHg | analisi §4.7 example (illustrative, unverified): 50 in F0; used only in sections 2.3 and 3.2 (early VIOLATED of RESP) |
| `cuff_inflation_min`, `int_window` | ms | registry names that appear only in the table of section 2.3 (SYS and INT rows); no value is used (`cuff_inflation_min` is `unset`, FIXTURE-ONLY in F0) |
| `dose_max_24h` | dose | analisi §4.1 (illustrative, unverified): 2 in F0 |

The levels `alpha`, `alpha_total`, the number of calibration episodes `n` and the prediction instants are monitor and experiment configuration, not registry entries (T02 section 3.4).

## 1 What rho answers

### 1.1 Two questions that the workshop paper merged

In the workshop Table I the row of the unscheduled dispense at 21:02 carries `sigma = -8`, `rho = 0.42` and the class C3 (analisi §4.6). The violated predicate there is a counter over the event log (three doses against a limit of two). A counter is either above its limit or it is not; there is no uncertainty about the violation, so a value of 0.42 can only express doubt about something else. Analisi §4.4 and R2 weakness 3 identify the confusion: the single symbol rho is used for two different things.

1. **How certain is the violation** (rho): given what the monitor received, how confidently can the sentence "the prescribed care is violated" be claimed, with the guarantee that belongs to the kind of evidence (a measured value, a forecast, an event log).
2. **How certain is it that the event is authentic, or due to a given cause** (kappa, the attributed cause of WS02): a double take, a sensor bounce, a replayed message and a tampered dispenser all violate the same counter.

This document defines rho for the first question only. The second belongs to the attribution layer (analisi §4.5, ADR-010) and is never folded into rho: the counter of the 21:02 row has `rho = 1` (kind DETERMINISTIC, conditional on the integrity of the log, case C-7) and its cause is `UNDETERMINED` or whatever the evidence supports (WS02-T04); a "low confidence" that mixes the two is exactly the signal that, in analisi §4.4 and R2 weakness 7, is not identifiable.

### 1.2 Where rho is defined

`rho` is defined only for the two verdict states that claim a violation:

- a record in state VIOLATED carries a `Rho` of kind MEASURED or DETERMINISTIC (which one: section 2.3);
- a record in state PREDICTED_VIOLATION carries a `Rho` of kind PREDICTED (section 2.4).

`rho` is `None` for SATISFIED and for PENDING. A "confidence" attached to a satisfied obligation has no semantics (analisi §4.6, row 07:00: a response that cannot yet be observed is reported with a confidence; the row is one of the errors of the workshop table), and a PENDING record claims nothing. This is what T05 already does (its transition table sets `rho := None` in T0, T4 and T7, and T6 replaces the predicted `rho` by the one of the definitive record) and the golden case C-7 of this document checks it. When a PREDICTED_VIOLATION record becomes VIOLATED (T05 transition T6) the predicted `rho` is dropped and replaced by the one of the definitive record; when it becomes SATISFIED (T7, a false predictive alarm) `rho` becomes `None`.

### 1.3 What rho is not

- It is not the attributed cause and carries no information about authenticity (section 1.1).
- For kind PREDICTED it is not the posterior probability that the violation will occur, and not the precision of the alerts (section 5.5 gives a no-skill forecaster whose alerts carry rho of at least 0.9 while about 14 percent of them are true violations).
- It is not a per-alert guarantee: the guarantee of kind PREDICTED is marginal over patient episodes under exchangeability (sections 5 and 6).
- It is not independent of the severity. `sigma_tilde` answers "how badly is the prescribed care violated" and `rho` answers "how confidently can the violation be claimed"; they are complementary and correlated (analisi §4.8): for a measured violation, `rho` tends to one half as the measured value approaches the limit, while `sigma_tilde` tends to zero (section 3, case C-6 with a measurement on the limit).

## 2 Rho per verdict type

### 2.1 The contract text relied upon, quoted exactly

From `docs/plan/02-interfaces.md#verdict` (version 0.1.0):

```python
class RhoKind(str, Enum):
    MEASURED = "measured"           # P(sigma_true < 0 | measurement) under a device error model
    PREDICTED = "predicted"         # conformal, 1 - alpha_star
    DETERMINISTIC = "deterministic" # event-log predicate, rho = 1

@dataclass(frozen=True, slots=True)
class Rho:
    value: float              # in [0, 1]
    kind: RhoKind
    guarantee: str            # exact statement, e.g. "marginal over patient episodes under exchangeability"
    alpha: float | None       # nominal level for PREDICTED
    assumptions: Sequence[str]
```

Semantics, rule 2: "PREDICTED_VIOLATION is emitted only while PENDING, when the conformal completion satisfies `sigma_hat + q_{1-alpha} < 0` ("likely") or `sigma_hat - q < 0` ("possible"); which one is used is a monitor option with a clinical justification (analisi §4.4)."

From `docs/plan/02-interfaces.md#conformal-calibrator` (version 0.1.0):

```python
class ConformalCalibrator(Protocol):
    mode: Literal["split", "adaptive"]
    def fit(self, episodes: Sequence[CalibrationEpisode], alpha: float) -> None: ...
    def quantile(self, alpha: float) -> float: ...                    # one-sided q_{1-alpha} of R = sigma_true - sigma_hat
    def predict(self, sigma_hat: float, alpha: float) -> "PredictedViolation": ...
    def update(self, sigma_hat: float, sigma_true: float) -> None: ... # adaptive mode only; no-op in split mode

@dataclass(frozen=True, slots=True)
class PredictedViolation:
    emitted: bool
    rho: Rho | None           # RhoKind.PREDICTED with alpha_star = inf{alpha : sigma_hat + q_{1-alpha} < 0}
    variant: Literal["likely", "possible"]
```

Rules: "1. Calibration unit is the **patient episode**, never the time step. Split by patient. 2. Coverage is marginal over the population, not conditional on the patient; this is stated wherever coverage is reported. 3. Nonconformity score is one-sided, `R = sigma_true - sigma_hat`; Proposition 1 (WS01) states `P(alert emitted and sigma >= 0) <= alpha` under exchangeability across episodes. 4. Every model update pushed from the back-end triggers recalibration on held-out episodes (`fit` is called again); the monitor refuses to use a calibrator older than the model version (analisi §2 R2 weakness 6)."

### 2.2 The table of rho

| `Rho.kind` | Definition | `Rho.value` | `Rho.guarantee` (exact string) | `Rho.alpha` | `Rho.assumptions` (exact strings) |
|---|---|---|---|---|---|
| MEASURED | `P(sigma_true < 0 \| measurement)` under the declared device error model of section 3; the model is Gaussian with standard deviation `cuff_error_sd`, errors independent, flat prior on the true value | `Phi(...)` of the formulas of section 3 (limit, band, difference), in `[0, 1]` | `conditional on the adequacy of the declared device error model` | `None` | (a) `measured value equals the true value plus an independent Gaussian error with standard deviation cuff_error_sd`<br>(b) `zero bias after correction (a silent bias is not seen by rho)`<br>(c) `flat prior on the true value`<br>(d) `errors of distinct measurements are independent` |
| PREDICTED | `rho = 1 - alpha*` with `alpha* = inf{alpha : sigma_hat + q_{1-alpha} < 0}`; equal to `m / (n + 1)` with `m = #{i : sigma_hat + R_i < 0}` (section 4.6); a conformal p-value (section 5.4) | `m / (n + 1)`, at most `n / (n + 1)` | `marginal over patient episodes under exchangeability` | the configured level `alpha` of the monitor (adopted: not `alpha*`; `alpha* = 1 - value` is recoverable from `value`) | (a) `calibration unit is the patient episode; calibration and test episodes are exchangeable`<br>(b) `forecaster and normalisation are fixed before calibration and independent of the calibration and test episodes`<br>(c) `one designated prediction instant per episode, with the same rule for calibration and test episodes`<br>(d) `calibrator fitted on the current model version` |
| DETERMINISTIC | `rho = 1` for a predicate over the event log or over timestamps: counts, windows, the obligation-unmet guard, a missing witness, a device-reported duration | `1.0` | `conditional on the integrity of the event log` | `None` | (a) `the predicate is evaluated on the accepted event log or timestamps without error`<br>(b) `authenticity of the events is attributed by kappa and is not covered by rho` |

The three strings per kind are the literal contents of the fields; the golden file uses them verbatim (cases C-2 and C-7). The guarantee of PREDICTED is the example string of the contract, and it must be reported with its hypotheses wherever it is shown (rule 2 of the calibrator). "Conditional on the adequacy of the declared device error model" includes the prior and the independence of the errors (assumptions (c) and (d)); "conditional on the integrity of the event log" says that a forged or lost event changes the log and not the predicate.

The same `Rho` object does not mix kinds: a record carries exactly one `Rho`, and the kind is that of the evidence that decided or predicted the verdict.

### 2.3 Which kind a VIOLATED record carries (resolves the provisional rule of T05 section 3.2)

The kind follows the deciding sub-formula at the decision-step value, as T05 section 3.2 proposes (adopted here, which closes the item "provisional, WS01-T06 owns it"). The SYS row, which T05 left open, is decided here.

| Template and deciding evidence | Kind | Value |
|---|---|---|
| RANGE: margin on a measured pressure (`bp` below `bp_band_low` or above `bp_band_high`) | MEASURED | band formula (section 3.2) |
| HOLD: margin on the held pressure (`bp` below `bp_hold_threshold`) | MEASURED | lower-limit formula (section 3.2) |
| HOLD: guard `no_recent_measurement` | DETERMINISTIC | 1 |
| RESP: margin on the measured drop in a closed window (one or more measurements) | MEASURED | difference formula (section 3.2), several measurements: section 3.2, item 4 |
| RESP: early VIOLATED because `pre_i < bound_bp_lower + delta_resp` (T05 section 3.3; rests on the bounds, T05 section 2.5) | MEASURED | `Phi((bound_bp_lower + delta_resp - x_pre) / s)`, conditional also on the registry bound (derivation in section 3.2, item 5) |
| RESP: guard `obligation_unmet` | DETERMINISTIC | 1 |
| SCHED: no measurement by the deadline, or graded lateness | DETERMINISTIC | 1 (a predicate over timestamps) |
| COUNT: limit exceeded or day-end minimum unmet | DETERMINISTIC | 1 |
| SYS: guard `cuff_unhealthy`, or `inflation_ms` below `cuff_inflation_min` | DETERMINISTIC | 1 (the duration is device-reported; the registry has no error model for durations, so none is applied) |
| INT: guard `no_witness`, or a witness older than `int_window` | DETERMINISTIC | 1 |

Reasons. A measured physiological value has a declared error model, so uncertainty about the violation is real and `rho < 1` is the honest value. A predicate over the log or over timestamps has no such model in the specification; applying one would again confuse rho with kappa. For SYS the margin is a duration reported by the device, no parameter of the registry describes its error, and a SYS violation concerns the monitoring system (phi_SYS), not a physiological quantity; a MEASURED rho for it would need a registry parameter that does not exist, so SYS is DETERMINISTIC and the alternative (a MEASURED rho with a timing error model) is left as a possible extension (section 10).

### 2.4 Rho of a PREDICTED_VIOLATION record, and when nothing is emitted

A record in state PREDICTED_VIOLATION carries `Rho(value = m / (n + 1), kind = PREDICTED, guarantee, alpha = configured level, assumptions)` for both variants of rule 2 (section 4.5). `alpha*` is defined by the upper quantile as in the contract comment of `PredictedViolation.rho`, whatever the variant: the value is a statistic of the episode (the fraction, out of `n + 1`, of the calibration residuals that, added to `sigma_hat`, give a negative robustness), and the variant selects only the emission rule. For the variant "possible" the guarantee that the level `alpha` provides is a bound on missed violations (Proposition 1b), not on the value; an alert of that variant can therefore carry a value well below `1 - alpha` (golden C-3: value 0.3 at `alpha = 0.2`), which is not an inconsistency (section 10, item 3).

When `PredictedViolation.emitted` is false, `PredictedViolation.rho` is `None` (adopted here: there is no alert whose confidence could be stated; the number `1 - alpha*` is a diagnostic that the golden file lists in `one_minus_alpha_star`). The reading of the contract that returns a `Rho` also for a non-emitted prediction is not adopted; WS05-T06 test 3 (`rho is None` for an infinite quantile) already assumes this, and C-2 shows two non-emitted rows (section 10, item 4).

**Severity of a predicted alert (OP-4 of T04, OP-15, OP-T05-4).** This document defines the conformal quantities, and the severity candidates are two functions of them: the normalised point forecast `clip(sigma_hat, -1, 1)` (T04 section 4.6, OP-4) and the conformal bound `clip(sigma_hat + q, -1, 1)` of the emission condition (WS05-T04 step 8, WS05-T08 tests 5 and 15), with `q` the quantile that triggered the alert (`q_{1-alpha}` for "likely", `q^lo_alpha` for "possible"). Adopted here, at the level of the quantity that this document supplies: the bound `clip(sigma_hat + q, -1, 1)`. Reasons. (i) It is negative for every emitted alert by construction (`sigma_hat + q < 0` is the emission condition, and `clip` keeps the sign), so the contract range of `Alert.sigma_norm`, `[-1, 0)`, holds for both variants and CP5 (a predicted alert with a non-negative `sigma_norm`) cannot arise; the point forecast can be non-negative whenever the quantile is negative (a forecaster biased towards optimism has `q < 0`, and an alert is then emitted for a positive `sigma_hat`), and under the variant "possible". (ii) It is the analogue of the certified severity of a VIOLATED alert (T05 section 3.7: a bound that holds for the whole interval), and it is the quantity that the emission condition tests. (iii) It matches WS05-T04 step 8 and WS05-T08 tests 5 and 15 (WS05-T08 test 5 expects `-0.3333` for `sigma_hat = -0.7333` and `q = 0.4`, which is `-0.7333 + 0.4`; for V-PRED-1 the bound is `-0.3333 + 0.09 = -0.2433`). The cost, which T04 section 6 names, is that the severity moves with the calibration set, with `alpha` and with the forecaster version, and mixes severity with the uncertainty that rho carries; the point forecast stays available in the log. The choice of what `Alert.sigma_norm` carries is nevertheless WS01-T07's (it owns the tuple, and WS05-T07 says its rule wins): **adopted here as the definition of the quantity, handed to WS01-T07 for the alert field**, with the consequence that if T07 prefers the point forecast, only that field changes and nothing in the propositions does.

## 3 Measured violations

### 3.1 The model

A measured physiological value is read as `x = x_true + e` where `x_true` is the true value, `x` the value that reaches the monitor (the measured value) and `e` the device error. The model (adopted here, analisi §4.4 first row) is:

1. `e` is Gaussian with mean zero (zero bias after the device's own correction) and standard deviation `cuff_error_sd = s`;
2. the errors of distinct measurements are independent (in particular the pre-dose and the response measurement of RESP);
3. the prior on the true value is flat (improper uniform), so that `x_true | x ~ N(x, s^2)`.

The assumptions (a) to (d) of the MEASURED row of section 2.2 are these three, the zero bias and the independence. A **silent bias or drift** (a cuff that reads 10 mmHg low and passes every health check) violates assumption (b): the monitor then reports a `rho` computed on a wrong value, and no channel of the evidence vector may be able to see it (the diagnosability matrix of analisi §4.5, row "silent bias or drift": not distinguishable). Rho does not see it, and the document does not pretend otherwise: it is a C2 case that rho does not cover, reported as a limit.

### 3.2 Derivations

Let `Phi` be the standard normal cdf and `phi` its density. In the formulas `x` is the measured value and `x_true` the true one.

1. **Single limit.** For a violation region `{x_true > L}` (an upper limit): `rho = P(x_true > L | x) = 1 - Phi((L - x) / s) = Phi((x - L) / s)`. For a violation region `{x_true < L}` (a lower limit, the hold threshold) the value is `Phi((L - x) / s)`. At `x = L` the value is `0.5`; for `x = 152` and `L = 140` with `s = 6` it is `Phi(2) = 0.9772` (analisi §4.4 writes the same example as `Phi(12 / s_dev)`).
2. **Band.** For the band `[lo, hi]` (`lo < hi`) the violation region is the union of the two disjoint regions `{x_true < lo}` and `{x_true > hi}`, so
   `rho = P(x_true < lo | x) + P(x_true > hi | x) = Phi((lo - x) / s) + Phi((x - hi) / s)`.
   The two terms are the posterior masses of the two regions, and they are added because the regions are disjoint. For `x = 104` with `lo = 110`, `hi = 140`, `s = 6`: `Phi(1) + Phi(-6) = 0.8413447461 + 0.0000000010`; the second region contributes about 1e-9 (case C-6).
3. **Difference of two measurements (RESP).** The measured drop is `r = x_pre - x_resp`, the difference of two independent measurements, and the true drop is `r_true = x_pre_true - x_resp_true`. With flat priors `x_pre_true | x_pre ~ N(x_pre, s^2)` and `x_resp_true | x_resp ~ N(x_resp, s^2)` are independent, so `r_true | data ~ N(r, 2 s^2)`. The violation region is `{r_true < delta_resp}`, hence
   `rho = Phi((delta_resp - r) / (s * sqrt 2))`.
   The standard deviation of the difference is `s * sqrt 2` (`6 * 1.41421 = 8.48528` for `s = 6`). For a drop of 5 against `delta_resp = 10` it is `Phi(5 / 8.48528) = Phi(0.589256) = 0.722155`, the value of V-RESP-4 in `verdicts.yaml`; for a drop of `-14` (`bp_pre` 138, `bp` 152) it is `Phi(24 / 8.48528) = Phi(2.828427) = 0.997661`.
4. **RESP with several measurements in the window.** The obligation is violated only if every measurement of the closed window has a true drop below `delta_resp` (`once` is a maximum, T02 section 4.5). The true pre-dose pressure is shared by all the drops, so they are positively correlated and the product of the single-measurement values is not the answer. With `x_pre_true = x_pre + s z`, `z ~ N(0, 1)`, and `x_resp,j_true ~ N(x_resp,j, s^2)` independent given the data,
   `rho = integral over z of phi(z) * product over j of Phi((x_resp,j + delta_resp - x_pre) / s - z) dz`,
   one-dimensional, computed by quadrature. For one measurement it reduces to item 3 (`integral of phi(z) Phi(c - z) dz = Phi(c / sqrt 2)`).
5. **Early VIOLATED of RESP by the bounds.** When T05 decides VIOLATED at the anchor step because `x_pre < bound_bp_lower + delta_resp`, every possible later pressure `b >= bound_bp_lower` gives a drop `x_pre_true - b <= x_pre_true - bound_bp_lower`, so the violation holds iff `x_pre_true < bound_bp_lower + delta_resp`, and `rho = Phi((bound_bp_lower + delta_resp - x_pre) / s)`. It is conditional on the model and on the bound (T05 section 2.5, OP-T05-8); a value outside the bounds is not an expected input.
6. **Predicates that are not measured**: counts, windows, timestamps, the obligation-unmet guard, missing witness, device-reported durations. They are DETERMINISTIC (section 2.3); there is no error model to apply.

**Two readings of the value, and which one the guarantee string uses.** (i) *Bayesian:* under the flat prior the value is the posterior probability of the violation, which is what `P(sigma_true < 0 | measurement)` means. (ii) *Frequentist, one-sided cases only:* for a single limit, `1 - rho` is a one-sided p-value for the null "the true value is within the limit": for every true value `x_true <= L`, `P(rho >= 1 - a) <= a` for every `a` in `(0, 1)`, because `rho >= 1 - a` iff `x >= L + s * Phi^{-1}(1 - a)` and `x = x_true + e` with `e ~ N(0, s^2)` (the probability is `a` at `x_true = L` and smaller inside the limit); this reading does not use the prior and holds pointwise in `x_true`, not only on average. For the band and for RESP with several measurements the exact one-sided property is not claimed (at the edge of the band the opposite tail adds a term of at most `Phi(-(hi - lo) / s)`, and the several-measurement value is a posterior mass). In both readings the guarantee is **conditional on the adequacy of the declared model**; it is not a statement about any device.

**Checked (tests, not proofs).** (1) The closed forms against trapezoid integration of the flat-prior posterior over 400,001 nodes, 13 cases (single limit at 152, 146, 140 and 138 against 140; band at 104, 115, 125, 145, 109.9; RESP drops of 5, -14, 20 and 9.5): largest absolute difference 1.2e-5 (the trapezoid error; the two sides are the same integral). (2) RESP with one, two and three measurements and with two measurements at a pre-dose of 140: quadrature of item 4 against a Monte Carlo of the posterior (2,000,000 draws each): differences of 0.27, 0.41, 1.99 and 0.05 standard errors (0.722155 against 0.722242 for one measurement; 0.647032 against 0.647169 for two; 0.628804 against 0.628125 for three; 0.775707 against 0.775721 for the fourth case). (3) The one-sided p-value reading, 400,000 draws per cell, `s = 6`, `L = 140`: at `x_true = 140` `P(rho >= 0.95) = 0.0500` and `P(rho >= 0.80) = 0.1999` (bounds 0.05 and 0.2); at `x_true = 135` 0.0068 and 0.0469; at `x_true = 120` 0 and 0. (4) The values of case C-6 are recomputed from `math.erf` in the independent check of the golden file.

### 3.3 Status of `cuff_error_sd`, and the source of truth (T03 OP-7)

`cuff_error_sd` is `unset` in `configs/registry/hypertension.yaml` (line 161: "not used by a template: parameter of the device error model of rho (WS01-T06); its source is a device validation protocol and is verified by a human"). Its value comes from the device validation protocol of the cuff, which a human verifies (analisi §5.1); WS00-T07 supplies it, and until then nothing in this project states a clinical value for it. The value 6 mmHg in the golden file is the F0 row, FIXTURE-ONLY, chosen so that `Phi(2)` is a round number; it is a claim about no device. A monitor that has no value for `cuff_error_sd` cannot produce a MEASURED rho: it must report that the value is missing (not substitute a default), and benchmark runs before the review use the F0 value through the fixture registry of ADR-027 (proposed) and say so.

**Source of truth (adopted here, T03 OP-7 asked WS01-T06 to state it).** The monitor reads its own `cuff_error_sd` from the registry; the benchmark generator draws device errors from `DeviceErrorModel.cuff_error_sd_mmhg` of its `PriorSource`. They are two parameters with two provenances. In the matched run both are set from the same source value; WS08 also runs a **mismatched** run in which the monitor receives a different value (this is what WS04-T06 step 5 and WS08-T05 already provide for), so that the reported calibration of the measured rho is not a property of the generator.

### 3.4 Calibration of the measured rho (own inference)

The task text states that when the generator draws errors from the same standard deviation the calibration of the measured rho is "trivially perfect". That needs a second condition. The flat prior is part of the model (assumption (c)); the measured rho is calibrated against a generator that draws the true values from a distribution **only if that distribution is flat over the relevant range** (or the prior is changed to the generator's). Test (own inference, 400,000 draws per row, bins of the reported rho among records with `x > L`, `L = 140`): with true values uniform over `[60, 220]` and matched `s = 6`, the observed fraction of true violations in the bins `[0.5, 0.6)`, `[0.6, 0.7)`, `[0.7, 0.8)`, `[0.8, 0.9)`, `[0.9, 0.99)` is 0.559, 0.657, 0.744, 0.847, 0.959 for mean rho 0.550, 0.651, 0.751, 0.854, 0.958; with a true error sd of 9 against the assumed 6 the same bins give 0.529, 0.606, 0.664, 0.767, 0.879 (over-confident); with true values drawn from `N(130, 8^2)` (an informative population prior) and the matched `s = 6` they give 0.261, 0.320, 0.413, 0.532, 0.719 (strongly over-confident). So a matched run does not by itself make rho a calibrated frequency, and a mismatched sd is one of two stresses that WS08 reports; the other is a non-flat population of true values. Under the flat-prior model the value is a posterior probability; it is not claimed to be an empirical frequency in a population of patients.

## 4 Conformal setting

### 4.1 The calibration unit, the episode and the targets

The **calibration unit is a patient episode**: one decision point of one template instance of one patient-day, at its designated prediction instant (section 4.3). It is never a time step: scores at consecutive steps of one trace are strongly dependent and not exchangeable (analisi §4.4, R2 weakness 4). An episode is the pair that `CalibrationEpisode` carries (`patient_id`, `day_index`, `template`, `sigma_hat`, `sigma_true`).

- `sigma_hat` is the normalised forecast of the robustness of the instance at its closing step, `sigma_hat = N_s(V_i(omega_hat))` (T05 section 5.1), **clipped into the normalised interval of the record** `[N_s(lo), N_s(hi)]` of the measured prefix at the prediction instant (T05 rule P4; confirmed here: the clipping is a function of the episode's own measured prefix and of its forecast, applied by the same procedure to calibration and test episodes, so it is part of the fixed map of H2 and keeps exchangeability; under (H-dom) the clipping brings the forecast nearer to every completion, so it never increases the absolute residual).
- `sigma_true` is the normalised robustness of the completed trace, `N_s(sigma_i^dec)` of T05 Lemma 7: the decision-step value of the reference semantics, whose sign is the final verdict (SATISFIED if `sigma_true >= 0`, by the tie rule). An instance that is never decided (a stale-open position, T05 section 3.5) has no `sigma_true`; it is excluded from calibration and from the false-alarm event, and counted apart (T05 section 4.3, consequence 3). The guarantee then concerns the decided instances (section 5.2, remark on selection).

**Which completed trace (offline use of ground truth, stated precisely).** The contract says "latent or measured". Two choices exist. (a) *Observed-completed (adopted as the default):* `sigma_true` is computed on the accepted observed trace, as the monitor itself will eventually compute it. The guarantee is then about the event "the final verdict of the instance will be SATISFIED", which is the event that T05 counts as a false predictive alarm; it needs no latent data, it is deployable, and it includes the effect of measurement noise and faults in the same way for calibration and test episodes (the calibration set must then contain the same mix of faults as the test population, which is part of H1). (b) *Latent-completed:* `sigma_true` is computed on the latent trace of the benchmark. The guarantee is then about the latent event, valid only if the evaluated event is the latent one too, and the calibrator reads `LatentDay` at **fit** time; this is an oracle-calibrated variant that exists only in the benchmark and is reported as such, never as a monitor that would run on a ward. At inference neither choice reads any latent object: the calibrator hands the monitor a quantile, which is a number. The target of the calibration and the event whose probability is bounded must be the same quantity; mixing them (fit on latent, evaluate on observed) leaves Proposition 1 without a statement. The choice for each WS08 experiment is declared in its configuration (handed to WS08, section 10).

### 4.2 The protocol

1. **Split by patient.** The forecaster is fitted on the train split only. The calibration episodes and the test episodes come from **different patients**, disjoint from each other and from the train patients (contract rule 1).
2. **Fixed forecaster and normalisation.** After training, the forecaster and the scales `s` (registry) are fixed; they do not depend on the calibration or test episodes. If the forecaster is retrained, the calibrator is refitted (section 7).
3. **One designated prediction instant per episode** (section 4.3), the same rule for calibration and test episodes.
4. **Selection by the prefix.** Only episodes whose record is PENDING at the prediction instant can be warned (T05 P1), so the calibration set is the set of episodes PENDING at their instants (and decided, section 4.1); its size `n` is the number of such episodes (section 5.2, remark).
5. **Scores** are computed by one fixed function of the episode (section 4.3).
6. **Quantile** at the configured level, from the `n` scores, by the exact rank rule of section 4.4.
7. **One calibrator per template and per prediction-instant class** is recommended: scores of different templates, or of forecasts made at different lead times, have different distributions and a pooled calibrator gives a guarantee that is marginal over the mix (section 6.1, caveat 2).

### 4.3 The score and the prediction instants

The score is **one-sided and signed**:

```
R = sigma_tilde_true - sigma_hat
```

(`R` is not an absolute residual: only the direction `sigma_true < sigma_hat` matters for a warning, which is why a one-sided quantile suffices and why the width of a two-sided interval is never used, ADR-009 and T04 section 6). `R` is dimensionless, because both terms are normalised with the scale of the template; no scale is ever taken from the conformal width.

**Prediction instants (adopted here, resolves OP-T05-10 and the question of T05 sections 4.3 and 5.2, P5).** A **designated prediction instant** is an instant that a rule derives from the care plan and from the information available at that instant alone, for example a fixed lead time before the deadline of the instance (V-PRED-1: 09:10, 20 minutes before the 09:30 deadline) or the activation step; the rule must not depend on the outcome and must treat every episode alike. Proposition 1 is stated for **one designated instant per episode**. If a monitor evaluates several instants `Pi_i` of one instance, each instant has its own calibration set (scores at different lead times are different random variables) and the level is split, `alpha_s = alpha_i / |Pi_i|`, by the union bound of section 6.2; a re-evaluation at every PENDING step is not covered. This is the consequence that T05 section 4.3 asks this task to state; the decision of WS05-T08 D6 "prediction once, at activation" is the special case of the activation instant, and V-PRED-1 (a forecast at 09:10 on an instance activated at 09:00) is a lead-time instant; both are covered by the proposition if the calibration episodes are scored at the same kind of instant (OP-T05-16 is therefore a WS05-T08 decision, not a conflict with the proposition: section 10).

### 4.4 The quantiles and the exact rank

With `n` scores sorted `R_(1) <= ... <= R_(n)`:

- the **upper quantile** `q_{1-alpha}` is `R_(k)` with `k = ceil((n + 1)(1 - alpha))`, and `+infinity` if `k > n`;
- the **lower quantile** `q^lo_alpha` is `R_(j)` with `j = floor((n + 1) alpha)`, and `-infinity` if `j < 1`.

For `alpha` in `(0, 1)` the two ranks satisfy `k = n + 1 - j`, because `n + 1 - floor(x) = ceil(n + 1 - x)`; one integer `j` gives both. Hence the `k`-th smallest score is the `j`-th largest, and `k >= 1` always. The rank `k` exceeds `n` exactly when `j = 0`, that is when `(n + 1) alpha < 1`.

**The rank must be computed in exact arithmetic, and `alpha` is the decimal literal.** A floating-point product can change the rank (golden case C-4): for `n + 1 = 100` and `alpha = 0.41`, `100 * (1 - 0.41)` evaluates to 59.00000000000001 and its ceiling is 60 instead of 59, a quantile one score too conservative; for `alpha = 0.29`, `100 * 0.29` evaluates to 28.999999999999996 and its floor is 28 instead of 29. The finding of this task (not in the task text) is that **converting the float to an exact fraction does not repair it**: the binary double nearest to 0.41 is 0.40999999999999997558, below 41/100, and exact arithmetic on that value gives rank 60 again; likewise for 0.29, rank 28. The level has to be read as the decimal literal that the user wrote. The rule:

```
a = Fraction(repr(alpha))                # shortest round-trip decimal, e.g. Fraction('0.41') = 41/100
j = ((n + 1) * a.numerator) // a.denominator
k = n + 1 - j                            # = ceil((n + 1)(1 - alpha))
```

All integer arithmetic. It assumes that `alpha` has at most 15 significant decimal digits (the shortest round-trip form is the literal), which every configured level has.

**Checked (a test).** Over `n = 1..999` and `alpha = 0.01, 0.02, ..., 0.99` (98,901 pairs): the float product `ceil((n + 1) * (1 - alpha))` gives a wrong upper rank in 577 pairs and `floor((n + 1) * alpha)` a wrong lower rank in 49; exact arithmetic on the binary value of the float gives 1,280 wrong upper ranks and 1,280 wrong lower ranks; the integer rule above gives 0 (asserted against the direct definition with `Fraction(str)` in the same run); the workaround `ceil(round((n + 1)(1 - alpha), 9))` of WS05-T06 step 3 gave 0 wrong ranks on the same grid, which is evidence for levels of at most two decimals, not a proof for every level. Examples of the float failure: `n = 9`, `alpha = 0.7`: the product is 3.0000000000000004 and the rank 4 instead of 3.

**Floating point in the emission test.** The emission test `sigma_hat + q < 0` and the count `m` of section 4.6 are the same comparison: in IEEE-754 double arithmetic with round-to-nearest, `fl(a + b)` has the sign of `a + b` and is zero only if `a + b = 0`, so `sigma_hat + R_i < 0` holds iff `R_i < -sigma_hat` holds in exact arithmetic. A random test (200,000 samples with scores and `sigma_hat` on a 0.01 grid) found no difference between the two expressions, so this is not a pitfall; the implementation may count either way. The inclusion used in the proof (`sigma_tilde >= 0` implies `R >= -sigma_hat` for `R = fl(sigma_tilde - sigma_hat)`) also survives rounding, because `fl` is monotone in its first argument.

### 4.5 The emission rules (the two variants)

Both apply only to a record that is PENDING at the prediction instant (T05 P1), and never produce a definitive verdict (ADR-008, contract semantics rule 3).

- **Variant "likely":** emit PREDICTED_VIOLATION iff `sigma_hat + q_{1-alpha} < 0`. Proposition 1 bounds the **false alarms** (an alert on an instance that ends with `sigma >= 0`).
- **Variant "possible":** emit iff `sigma_hat + q^lo_alpha < 0`, with the lower quantile. Proposition 1b bounds the **missed violations** (an instance that ends with `sigma < 0` and was not flagged). The form `sigma_hat - q_{1-alpha} < 0` of analisi §4.4 and of contract rule 2 equals this one **only if** `q^lo_alpha = -q_{1-alpha}` for the calibration set at hand; for a distribution that is symmetric about zero this holds in distribution, not for every calibration set, and it is not the quantile that makes the statement valid in general (section 5.7, CP4).

A negative `q_{1-alpha}` is allowed: it says that the forecaster tends to over-estimate the robustness; an alert is then emitted for a `sigma_hat` that is positive but below `-q`.

### 4.6 `alpha*`, the count `m` and `rho = m / (n + 1)`

Let `m = #{i : sigma_hat + R_i < 0}`, the number of calibration scores that, added to `sigma_hat`, give a negative robustness; equivalently `#{i : R_i < -sigma_hat}` (strict). `m` is an integer in `{0, ..., n}`.

**Lemma 1.** Let `n >= 1`, `alpha` in `(0, 1)`, `k = ceil((n + 1)(1 - alpha))` and `j = floor((n + 1) alpha)`. (i) The variant "likely" emits iff `m >= k`, iff `alpha >= (n + 1 - m) / (n + 1)`. (ii) The variant "possible" emits iff `m >= j`, iff `alpha < (m + 1) / (n + 1)`.
*Proof.* (i) If `k > n` the quantile is `+infinity`, no emission, and `m <= n < k`: consistent. If `k <= n`: `sigma_hat + R_(k) < 0` iff `R_(k) < -sigma_hat` iff at least `k` scores are below `-sigma_hat` iff `m >= k`. As `m` is an integer, `m >= ceil((n + 1)(1 - alpha))` iff `m >= (n + 1)(1 - alpha)` iff `alpha >= 1 - m / (n + 1) = (n + 1 - m) / (n + 1)`. (ii) If `j = 0` the lower quantile is `-infinity` and the alert is always emitted, and `m >= 0` holds; if `j >= 1`: `sigma_hat + R_(j) < 0` iff `m >= j`; as `m` is an integer, `m >= floor((n + 1) alpha)` iff `m + 1 > (n + 1) alpha`. ∎

**Definition (alpha* and rho).** For the variant "likely" the set of levels `alpha` in `(0, 1)` at which an alert is emitted is, by Lemma 1(i), `[(n + 1 - m) / (n + 1), 1)` if `m >= 1` (a minimum, because the condition is `alpha >=`) and empty if `m = 0`. Hence

```
alpha* = inf{alpha : sigma_hat + q_{1-alpha} < 0} = (n + 1 - m) / (n + 1)   if m >= 1
alpha* = 1                                                                   if m = 0   (convention: inf of the empty set, capped at 1)
rho    = 1 - alpha* = m / (n + 1)
```

So `rho <= n / (n + 1)` (attained when every calibration score is below `-sigma_hat`), `rho = 0` iff `m = 0`, and `alpha* >= 1 / (n + 1)`: **no alert can have `alpha* < 1 / (n + 1)`, so a level below `1 / (n + 1)` never emits** (section 4.7). An alert is emitted at the configured level `alpha` iff `alpha >= alpha*`, that is iff `rho >= 1 - alpha`. The value `alpha*` is the smallest level at which the monitor would have emitted this alert; it is recoverable from `Rho.value` (`alpha* = 1 - value`), which is why `Rho.alpha` can carry the configured level (section 10).

Golden C-2 checks the relation on five rows (`m = 8, 7, 9, 0, 9`, giving `alpha* = 0.2, 0.3, 0.1, 1, 0.1`): the value 0.9 of V-PRED-1 is `m / (n + 1) = 9 / 10`.

**Checked (tests).** (1) Brute force of the definition: for 3,000 random samples (scores and `sigma_hat` on a 0.1 grid, so with many ties, `n` from 1 to 24) the smallest level of the exact grid `{i / (10 (n + 1))}` at which the emission test fires equals `(n + 1 - m) / (n + 1)` (and 1 when `m = 0`): 0 mismatches. (2) Emission at `alpha = i / 20`, `i = 1..19`, against `alpha >= alpha*`: 380,000 (sample, level) pairs with ties, 0 mismatches. (3) The same for C-2 by hand and by the independent check of the golden file.

**A heuristic reading, not a claim.** `m / (n + 1)` is the empirical distribution function of the scores at `-sigma_hat`, with `n + 1` in the denominator. If the residual `R` were independent of `sigma_hat` it would estimate `P(sigma_true < 0 | sigma_hat)`. That independence is not assumed anywhere and is typically false (errors are larger for extreme forecasts); the guarantee of the value is Proposition 1 (a marginal statement), and the heuristic reading must not be used in the paper.

### 4.7 Minimum calibration size

The upper quantile is finite iff `k <= n` iff `(n + 1)(1 - alpha) <= n` iff `alpha (n + 1) >= 1` iff `n >= 1 / alpha - 1`; as `n` is an integer, **`n >= ceil(1 / alpha) - 1`**. The lower quantile is finite under the same condition (`j >= 1` iff `(n + 1) alpha >= 1`). Below it the upper quantile is `+infinity`, no predicted alert is ever emitted, and this is **reported, not hidden**: `alpha = 0.05` needs 19 episodes, `alpha = 0.005` needs 199 (case C-5), and with `n = 9` at `alpha = 0.05` no alert is possible (case C-1). The count is of **episodes of distinct patients** (section 5.6): the effective sample size is the number of patients, not the number of time steps or days.

## 5 Proposition 1

### 5.1 Hypotheses and statement

**Hypotheses.**

- **H1 (exchangeability across patient episodes).** The scores `R_1, ..., R_n` of the `n` calibration episodes and `R_{n+1}` of the test episode, as a vector, have a joint distribution that is invariant under every permutation of the indices. Here `R_i = sigma_tilde_true,i - sigma_hat,i` is the score of episode `i`, of the same template and prediction-instant class as the test episode when the calibrator is per template (the guarantee is then for that template), or of the mix of templates when one calibrator pools them (the guarantee is then marginal over the mix).
- **H2 (fixed forecaster and normalisation).** The forecaster, the scales `s_i` (registry) and the clipping rule of section 4.1 are fixed before the calibration and test episodes are drawn and do not depend on them: the map `episode -> (sigma_hat, sigma_true) -> R` is one fixed function applied alike to all `n + 1` episodes. The probabilities below are conditional on that map (and so on the training data and the model version).
- **H3 (quantile).** `q_{1-alpha}` is the `k`-th smallest of the `n` calibration scores, `k = ceil((n + 1)(1 - alpha))`, and `+infinity` if `k > n` (section 4.4), with `alpha` fixed in advance.
- **H4 (one designated instant, selection by the prefix).** Every episode has one designated prediction instant (section 4.3), the same rule for all; the `n` calibration episodes are the decided episodes that are PENDING at their instants, and the test episode is evaluated under the same rule (remark in section 5.2).

**Proposition 1 (false predictive alarms).** Under H1 to H4, for every `alpha` in `(0, 1)` and every `n >= 1`,

```
P( sigma_hat + q_{1-alpha} < 0  and  sigma_tilde >= 0 )  <=  (n + 1 - k) / (n + 1)  <=  alpha        if k <= n,
P( sigma_hat + q_{1-alpha} < 0  and  sigma_tilde >= 0 )  =   0                                       if k > n,
```

where `sigma_hat` and `sigma_tilde` are those of the test episode, `k = ceil((n + 1)(1 - alpha))`, and `P` is the **marginal** probability over the joint draw of the `n` calibration episodes **and** the test episode (given the fixed map of H2). The first inequality is an equality for the event `{R_{n+1} > q_{1-alpha}}` when the scores have no ties almost surely; the event of the proposition is contained in it, so for it the statement is `<=`. The value `(n + 1 - k) / (n + 1)` equals `floor((n + 1) alpha) / (n + 1)` and equals `alpha` only if `(n + 1)(1 - alpha)` is an integer.

In words: the probability, over the calibration set and the test episode, that the monitor emits a PREDICTED_VIOLATION (likely variant) at level `alpha` on an episode that ends with `sigma_tilde >= 0` (that is, ends SATISFIED, by the tie rule of T05 section 3.4 and Lemma 7) is at most `alpha`. The statement is **marginal over patient episodes under exchangeability**; it is not conditional on the patient, not conditional on the calibration set, not per time step, and it says nothing under distribution shift (section 7). It is a statement about the false alarms of this one level at this one instant: the allocation over many tests is section 6.

### 5.2 Proof

**Lemma A (counting).** Let `Z_1, ..., Z_{n+1}` be exchangeable real random variables and `1 <= k <= n`. For each `i` let `Z^{(-i)}_{(k)}` be the `k`-th smallest of the `n` variables other than `Z_i`, and `E_i = {Z_i > Z^{(-i)}_{(k)}}`. Then `P(E_{n+1}) <= (n + 1 - k) / (n + 1)`, with equality if the `Z_i` have no ties almost surely.
*Proof.* (1) *Symmetry.* `P(E_i) = P(E_{n+1})` for every `i`: let `tau` swap `i` and `n + 1`; the vector `Z o tau` has the same distribution as `Z` (exchangeability), `E_i` is the event `E_{n+1}` evaluated on `Z o tau`, and `Z^{(-i)}_{(k)}` is a symmetric function of the other `n` coordinates. Hence `P(E_{n+1}) = (1 / (n + 1)) E[ sum over i of 1(E_i) ]`. (2) *Pointwise count.* Let `W_(1) <= ... <= W_(n+1)` be the order statistics of the whole vector. If `E_i` holds, the `k` smallest of the other coordinates are all at most `Z^{(-i)}_{(k)}`, which is below `Z_i`, so at least `k` coordinates are strictly below `Z_i`, and therefore `W_(k) < Z_i` (the `k`-th smallest of the whole vector is at most the largest of `k` values that are below `Z_i`). The number of indices `i` with `Z_i > W_(k)` is at most `n + 1 - k`, because at least `k` coordinates (those at positions `1..k`) are `<= W_(k)`. Hence `sum over i of 1(E_i) <= n + 1 - k` for every outcome, ties included. (3) Taking expectations gives the bound. *Equality without ties:* if `Z_i > W_(k)` then `Z_i` has position `>= k + 1`, the `k` smallest of the others are `W_(1), ..., W_(k)`, and `Z^{(-i)}_{(k)} = W_(k) < Z_i`, so `E_i` holds; hence `sum 1(E_i)` equals the number of `i` with `Z_i > W_(k)`, which is exactly `n + 1 - k` when there are no ties. ∎

**Proof of Proposition 1.** If `k > n` then `q_{1-alpha} = +infinity`, `sigma_hat + q = +infinity` is not below 0, and the event is empty. Let `k <= n`. *Inclusion:* if `sigma_hat + q_{1-alpha} < 0` and `sigma_tilde >= 0`, then `q_{1-alpha} < -sigma_hat` and `R_{n+1} = sigma_tilde - sigma_hat >= -sigma_hat > q_{1-alpha}`. So the event is contained in `{R_{n+1} > q_{1-alpha}} = E_{n+1}` for `Z = (R_1, ..., R_{n+1})`, whose `k`-th smallest of the others is `q_{1-alpha}` by H3. By H1 the vector is exchangeable, and `P(E_{n+1}) <= (n + 1 - k) / (n + 1)` by Lemma A. Finally `k >= (n + 1)(1 - alpha)` gives `(n + 1 - k) / (n + 1) <= alpha`. ∎

The argument uses exchangeability only through Lemma A and needs no continuity: with ties the bound is still `<=`; the equality of the no-ties case is not claimed (exact enumeration of discrete laws, section 5.8, finds the inequality strict in most cells). The same argument in the language of ranks: with random tie-breaking the rank of `R_{n+1}` among the `n + 1` scores is uniform on `{1, ..., n + 1}` and `R_{n+1} > R_(k)` forces rank above `k`, with probability `(n + 1 - k) / (n + 1)`; Lemma A avoids the tie-breaking device.

**Remark (selection by the prefix and by decidedness; H4).** Let the `N` calibration episodes and the test episode be independent and identically distributed (the sufficient condition of section 5.6), and let `S_i` be the indicator that episode `i` is PENDING at its instant and is later decided (`S_i` is a function of the episode itself). The calibration set is the set of the `n` selected calibration episodes (random size), and the test episode contributes to the event only if selected. Conditionally on the selection indicators, the selected episodes are independent with the law of one episode given `S = 1`; so, given that the test episode is selected and that `n` calibration episodes are selected, the `n + 1` selected episodes are independent and identically distributed, hence exchangeable, and Proposition 1 applies to them: `P(alarm and sigma_tilde >= 0 | test selected, n) <= alpha`; averaging over `n`, `P(alarm and sigma_tilde >= 0 | test selected) <= alpha`, and the unconditional joint probability is at most `alpha P(test selected) <= alpha`. A calibration set that is **not** selected by the same rule breaks it: a test (own inference, 100,000 draws, about 130 of 400 calibration episodes selected, residuals shifted by the latent variable that also drives the selection, alpha 0.1) gives `P(R_{n+1} > q | selected) = 0.0962` for the matched set and `0.2919` when the calibrator is fitted on all episodes and the test episodes are selected. With the selection rule applied to both (about 270 of 400 selected, 100,000 draws, residuals again driven by the selecting variable) the joint conditional probability `P(alert and sigma_tilde >= 0 | test selected)` was 0.0134, below `alpha = 0.1`.

### 5.3 The equality case

If the scores are exchangeable with no ties almost surely, `P(R_{n+1} > q_{1-alpha}) = (n + 1 - k) / (n + 1)` and `P(R_{n+1} <= q_{1-alpha}) = k / (n + 1)` exactly, over the calibration set and the new score. Example: `n = 9`, `alpha = 0.2`, `k = 8`, probability `8/10` (case C-1). This is an identity about the **procedure**; it says nothing about the coverage of the particular number computed from one calibration set (0.09 in C-1). For continuous scores the coverage `F(q)` of the realised quantile has the distribution of the `k`-th order statistic of `n` uniform variables, Beta(`k`, `n + 1 - k`), with mean `k / (n + 1)` and standard deviation `sqrt(k (n + 1 - k) / ((n + 1)^2 (n + 2)))`; for `n = 9`, `k = 8` the standard deviation is 0.12. **Checked (a test):** 400,000 calibration sets of nine standard normal scores gave mean 0.8000, standard deviation 0.1204, 5th percentile 0.572 and a fraction 0.196 below 0.7. With small `n` the guarantee holds on average and the realised coverage of a given calibration set varies widely.

### 5.4 Corollary: `alpha*` is a conformal p-value for the null `sigma >= 0`

By Lemma 1(i), `{alpha* <= alpha}` is the event that the monitor emits at level `alpha`. Hence, under H1 to H4, **for every fixed `alpha` in `(0, 1)`**,

```
P( alpha* <= alpha  and  sigma_tilde >= 0 )  <=  alpha.
```

For `alpha < 1 / (n + 1)` the left side is zero because `alpha* >= 1 / (n + 1)`. `alpha*` is a (conformal) p-value for the null "the instance ends with `sigma_tilde >= 0`" in the **joint** sense of the display. It is not a p-value in the conditional sense `P(alpha* <= alpha | sigma_tilde >= 0) <= alpha`, which is not claimed and can fail: **checked (a test):** with `sigma_hat = -2` constant and `R ~ N(0, 1)`, `n = 99`, `alpha = 0.2` (200,000 pairs), `P(alert and sigma >= 0) = 0.0228`, below 0.2, while `P(alert | sigma >= 0) = 1.000`. The level `alpha` must be fixed in advance: the statement is for each `alpha` separately, not for an `alpha` chosen after seeing `alpha*` (which is the sense in which the guarantee is attached to the configured level and `Rho.alpha` carries it).

### 5.5 What the proposition does not say

- **`rho` is not the probability that the violation occurred, and not its posterior probability.** `rho = 1 - alpha*` is a function of `m`; the proposition bounds a joint probability of the **alarm** and of the **absence** of the violation, averaged over episodes.
- **The joint bound is not the precision of the alerts.** `P(alert and sigma >= 0) <= alpha` says nothing about `P(sigma < 0 | alert)`, which also depends on how often alerts are emitted: if alerts are rare, the bound is vacuous for them. **Checked (a test):** a no-skill forecaster (`sigma_true` independent of `sigma_hat`, `sigma_hat ~ N(0, 1)`, `sigma_true ~ N(1, 1)`, `n = 99`, 200,000 pairs): at `alpha = 0.1` the joint probability `P(alert and sigma >= 0)` is 0.0026, below 0.1, the alerts are emitted with probability 0.003, each carries `rho >= 0.9`, and the observed fraction of alerts that end with `sigma >= 0` is 0.857, so the precision is 0.143, about the base rate of violations (0.158); at `alpha = 0.3` the precision is 0.160. A forecaster of no skill is calibrated in the sense of the proposition and useless as a warning, which is why WS08 reports precision, recall and the lead time of the warnings beside the coverage.
- **It is not conditional on the patient.** **Checked (a test):** two patient types (scores `N(2, 1)` and `N(0, 1)`, half each, `n = 99`, `alpha = 0.1`, 200,000 pairs): marginal `P(R_{n+1} > q) = 0.0996`, but 0.1965 for the type with the larger scores and 0.0026 for the other. Marginal coverage is an average over patients; an individual patient can be systematically above the average.
- **It is not conditional on the calibration set** (section 5.3), **not per time step**, **not per instant of an instance with several instants**, and says nothing under distribution shift (section 7).

### 5.6 A sufficient condition for H1 (own inference), and what breaks it

**Sufficient condition.** The `n + 1` episodes come from `n + 1` **distinct patients** drawn independently from one population, with one episode per patient (one designated instant of one designated template instance, chosen by a rule that does not look at the other patients). Then the pairs `(sigma_hat, sigma_true)` are independent and identically distributed, hence the scores are independent and identically distributed, hence exchangeable. The same holds for a calibration set of patients and a test patient drawn from the same population when the episodes are selected by the rule of H4. This is the **split by patient** of the contract (rule 1): the calibration and test patients are disjoint from each other and from the train patients, and the forecaster is trained on patients that are not in the calibration set.

**What breaks H1.**

- **Pooling several episodes of one patient in the calibration set** breaks it in general: the calibration scores come in clusters (a patient effect in `R`), the test episode is a single draw, and the vector of scores is not exchangeable. The **effective sample size is the number of patients**, not the number of episodes. **Checked (a test):** a patient effect of standard deviation 1 against an episode noise of 0.05 (so almost all the variance is between patients), 100,000 draws: 9 patients with 10 episodes each pooled (n = 90, a finite quantile at `alpha = 0.05`, although `ceil(1 / 0.05) - 1 = 19` patients are needed) gave `P(R_{n+1} > q) = 0.0979` instead of 0.05; at `alpha = 0.1` it gave 0.1067 for the same set, and with 19 patients of 10 episodes 0.0535 and 0.1069; with 99 patients of one episode, 0.0499 and 0.1011 (the exact levels). So pooling made the quantile finite with too few patients and the level anti-conservative.
- **Episodes of the same patient in calibration and in test** (a patient that is deployed and was also in the calibration set) break it by the same mechanism.
- **A different population** (another ward, another cohort, another season) breaks it (section 7).
- **A calibration set selected by a different rule than the test** (the remark of section 5.2).
- **A forecaster that was trained on, or selected using, the calibration episodes** breaks H2.

### 5.7 Proposition 1b (the variant "possible") and the symmetric form (CP4)

**Proposition 1b (missed violations).** Under H1, H2 and H4, with the lower quantile `q^lo_alpha = R_(j)`, `j = floor((n + 1) alpha)` (and `-infinity` if `j < 1`, H3 with the lower rank), for every `alpha` in `(0, 1)`,

```
P( sigma_tilde < 0  and  sigma_hat + q^lo_alpha >= 0 )  <=  j / (n + 1)  <=  alpha        if j >= 1,
P( sigma_tilde < 0  and  sigma_hat + q^lo_alpha >= 0 )  =   0                              if j = 0.
```

The probability is marginal over the calibration set and the test episode, as in Proposition 1. The bound `j / (n + 1)` is the same number as `(n + 1 - k) / (n + 1)` of Proposition 1.

*Proof.* If `j = 0` the lower quantile is `-infinity` and the alert is always emitted: the event is empty. Let `j >= 1`. *Inclusion:* if `sigma_tilde < 0` and `sigma_hat + q^lo >= 0` then `R_{n+1} = sigma_tilde - sigma_hat < -sigma_hat <= q^lo`, so the event is contained in `E'_{n+1} = {R_{n+1} < R^{(-(n+1))}_{(j)}}`. *Lemma A' (mirror image):* for exchangeable `Z` and `1 <= j <= n`, `P(Z_{n+1} < Z^{(-(n+1))}_{(j)}) <= j / (n + 1)`, with equality without ties. Proof: by the symmetry step of Lemma A it is enough to bound `sum over i of 1(E'_i)` pointwise. If `E'_i` holds then the `n - j + 1` coordinates among the others that are at least `Z^{(-i)}_{(j)}` are all strictly above `Z_i`, so at most `j` coordinates (including `Z_i`) are at most `Z_i`, and therefore `W_(j+1) > Z_i`; the number of indices with `Z_i < W_(j+1)` is at most `j` (they sit at positions `1..j`). Hence `sum 1(E'_i) <= j`, and the average gives `j / (n + 1)`; without ties `E'_i` holds iff `Z_i < W_(j+1)`, which gives equality. ∎ And `j / (n + 1) <= alpha` because `j = floor((n + 1) alpha)`.

**Duality (a convenient fact, own inference).** `q^lo_alpha(R) = - q_{1-alpha}(-R)`: the lower quantile of the scores at level `alpha` is minus the upper quantile, at the same level `alpha`, of the flipped scores `-R`, because the `j`-th smallest of `R` is minus the `(n + 1 - j)`-th smallest of `-R` and `n + 1 - j = k`. So a calibrator fitted on the episodes in which `sigma_hat` and `sigma_true` are exchanged (`R' = sigma_hat - sigma_true = -R`) returns `q^lo_alpha` through the existing `quantile` method and a sign change; this needs no change of the contract. **Checked (a test):** 380,000 (sample, level) pairs with ties, 0 mismatches of the identity in exact ranks.

**The symmetric form of contract rule 2 and analisi §4.4.** The rule `sigma_hat - q_{1-alpha} < 0`, with the upper quantile, gives the miss bound of Proposition 1b only if `-q_{1-alpha}` can replace `q^lo_alpha`. Sufficient: the `n + 1` scores are **independent and identically distributed with a distribution that is symmetric about zero** (`R_i` and `-R_i` have the same law). Then `R_{n+1}` is independent of the calibration scores and `-R_{n+1}` has the same law as `R_{n+1}`, so `P(R_{n+1} < -q_{1-alpha}) = P(-R_{n+1} > q_{1-alpha})` is the probability of Proposition 1 for the exchangeable vector `(R_1, ..., R_n, -R_{n+1})`, at most `alpha`. Without symmetry the symmetric form can have a miss probability far above `alpha`, and the statement "valid only if the distribution of `R` is symmetric about zero" of the task text is to be read as "valid under symmetry and not in general", not as a necessary condition. Golden C-3 shows the disagreement on the fixture scores (asymmetric: `q^lo_0.2 = -0.22` against `-q_{0.8} = -0.09`): `sigma_hat = 0.15` is flagged by the lower-quantile form (`-0.07 < 0`) and not by the symmetric form (`+0.06`).

**Checked (tests).** (1) *Exact:* a finite asymmetric model (`sigma_hat = 1/2`, `R` equal to `-1` or `0` with probability 1/2 each), enumerated exactly for `n = 1..8` and 19 levels: the symmetric form has a miss probability above `alpha` in 41 of 152 cells (for example `n = 2`, `alpha = 7/20`: probability 1/2), the lower-quantile form in none. (2) *Monte Carlo:* a forecaster biased towards optimism (`R = -X`, `X ~ Exp(1)`, `sigma_hat = 0.5`, `n = 99`, `alpha = 0.1`, 200,000 pairs): `P(sigma_tilde < 0 and no alert)` is 0.6058 for the symmetric form (the true violation probability is 0.6065: it almost never alerts) and 0 for the lower-quantile form. (3) With a symmetric law (Laplace, `n = 99`, `alpha = 0.1`) the symmetric form had a miss probability of 0.0065 (below `alpha`; 0 of 20 cells above `alpha + 3` standard errors in that law).

**Consequence for the contract (CP4).** `ConformalCalibrator` exposes only the upper one-sided quantile `quantile(alpha)`. Adopted here: Proposition 1 and `rho` are stated for the upper quantile; for the variant "possible" this document defines the valid rule with the lower quantile (section 4.5), obtainable from `quantile` by the duality above or from a second method `quantile_lower` (a change of the contract, an ADR, handed to WS01-T08 and WS05-T06, section 10). The literal reading `sigma_hat - q_{1-alpha} < 0` is not adopted for the variant "possible" because it carries no guarantee for asymmetric scores; it is kept as an alternative only if the symmetry of the scores is itself checked.

### 5.8 Checks of this section (tests, not proofs)

All scripts are seeded and not part of the repository (`/tmp`); draws are counted per cell; a tolerance is **three standard errors** of the estimate, never a chosen constant, and the expected number of chance exceedances at three standard errors is reported with the result.

| Statement | Test | Size | Result |
|---|---|---|---|
| Lemma A and A', exact identity without ties | all orderings of `n + 1` distinct values, exact rational probabilities, `n = 1..7`, `alpha = i / 20` | 133 cells (up to 8! = 40,320 orderings) | `P(R_{n+1} > q) = (n + 1 - k) / (n + 1)` and `P(R_{n+1} < q^lo) = j / (n + 1)` exactly in every cell |
| Proposition 1 and 1b with ties, and exchangeable but not independent scores | exact enumeration of 6 finite laws (uniform on 3 values, skewed on 3 and on 5 values, two points, two mixtures of two iid laws), `n` up to 6, 19 levels | 627 cells | both probabilities at most the bound and at most `alpha` in all; strict inequality in 472 cells (upper and lower alike); largest ratio to the bound 0.889 |
| Proposition 1 and 1b end to end | exact enumeration of `(sigma_hat, R)` pairs on an 8-point support, two laws, `n = 1..4`, 19 levels | 152 cells | `P(alert and sigma >= 0) <= alpha` and `P(sigma < 0 and no alert) <= alpha` in all; largest ratios to `alpha` 0.350 and 0.571 |
| Coverage of the quantiles (continuous and discrete scores) | Monte Carlo, fresh calibration set per draw, 7 laws (normal, lognormal, left-skewed exponential, Student `t` with 1.5 degrees of freedom, bimodal; Poisson(3) and `N(0, 1)` rounded to 0.1 with many ties), `n` in 4, 9, 19, 49, 99, `alpha` in 0.05, 0.1, 0.2, 0.3 | 140 cells of 200,000 pairs (28,000,000 pairs) | continuous laws: 170 equality tests, one outside three standard errors (3.24, with 0.46 expected by chance; five independent replicates of that cell gave `|z| <= 1.28`); mean `z` -0.039, standard deviation 1.036; discrete laws: all at most the bound, ratio at most 0.949; 3 `(n, alpha)` pairs with `n < 1 / alpha - 1`: no alert in 200,000 pairs each |
| Proposition 1 and 1b with `sigma_hat` | Monte Carlo, 7 laws of `(sigma_hat, R)`: independent, heteroscedastic and right-skewed, heavy-tailed and dependent, discrete with ties, a no-skill forecaster, symmetric Laplace, left-skewed | 140 cells of 200,000 pairs | Proposition 1 event above `alpha + 3` standard errors in 0 cells (largest ratio to `alpha` 0.270); Proposition 1b event in 0 cells (0.339); the symmetric form above `alpha + 3` standard errors in 3 cells, all in the left-skewed law at `alpha = 0.05` (0.0577 to 0.0588) |
| `alpha*` and Lemma 1 | brute force over an exact grid; emission against `alpha >= alpha*`; ties | 3,000 and 380,000 cases | 0 mismatches |
| Rank formula and floating point | float product, binary fraction, integer rule | 98,901 `(n, alpha)` pairs | section 4.4 |
| Selection by the prefix | calibration set selected by the same rule against all episodes | 100,000 draws | section 5.2 |
| Pooling several episodes of one patient | patient effect, episodes pooled | 100,000 draws per row | section 5.6 |

Power of the Monte Carlo check: a rank one too low or one too high (`k - 1`, `k + 1`) was detected with `|z|` between 13.5 and 102.6 in three cells (`n = 19, 49, 99`; `alpha = 0.05, 0.2, 0.1`; 200,000 pairs each), so a one-rank error of the kind of section 4.4 does not pass at these sizes. Reading. The tests are consistent with the propositions, including laws with heavy tails, asymmetry, ties and a small `n` for which the quantile is infinite; none of them is a proof and none enlarges a hypothesis. The counterexamples found are all outside the hypotheses and are listed in sections 5.4 to 5.7: the conditional form of the corollary, the symmetric form on asymmetric scores, pooled episodes of one patient, a mismatched selection, and the shift of section 7.

### 5.9 Relation to prior work, without inflation

The proposition is the one-sided split-conformal quantile bound `[ref-needed: WS03]` (analisi §3.2 recalls the conformal literature, all of it unverified, ADR-018) applied to the false predictive alarm of a three-valued verdict, with the patient episode as unit and the selection of section 5.2; the proof above is the standard counting argument on ranks and is not claimed as new. Analisi §4.4 calls the statement small but new in this setting, and §10 objection 2 asks that it be presented as small but new in the three-valued setting, without inflating it: what is specific is the setting (the event is a false predictive alarm on a PENDING record of a three-valued monitor, the calibration unit is the patient episode, the allocation of section 6 is over tests per patient-day, and the verdict itself never depends on the forecast, ADR-008), not the inequality. Against conformal STL runtime verification on dense predicted trajectories (`lindemann-conformal-stl`, the closest published work according to analisi §3.2 and the baseline B5), the element of difference that belongs to this document is the formal separation of the verdict on measured data from the predictive verdict, with conformal prediction confined to PENDING (`docs/related-work/conformal-predictive-monitoring.md`, difference sentence, element 2). Hedge that travels with it: the characterisation "dense predicted trajectories" is taken from analisi §3.2, which recalls the paper from memory; it has not been checked against the paper text (WS03-T06), and no priority claim is made. The entries `lindemann-conformal-stl`, `cairoli-conformal-quantitative-monitoring`, `gibbs-candes-adaptive-conformal`, `barber-beyond-exchangeability` and `zhao-robust-conformal-stl` of `paper/refs/references.bib` are all `verified = {false}`; they are named here by topic only (closest work; conformal quantitative predictive monitoring; adaptive conformal inference; conformal prediction beyond exchangeability; robust conformal prediction under shift) and none may be cited in the paper until a human verifies it.

## 6 The three caveats and alpha allocation

### 6.1 The three caveats, in the wording of analisi §4.8

1. **The unit is the patient episode, never the time step.** Scores of consecutive steps of one trace are dependent; the calibration set counts episodes of distinct patients (section 5.6).
2. **Coverage is "marginal over patient episodes under exchangeability".** It is not conditional on the patient (checked in section 5.5: 0.1965 against 0.0026 for two patient types at a marginal 0.0996), not conditional on the template when one calibrator pools templates (it is marginal over the template mix; one calibrator per template gives the statement for that template), not conditional on the calibration set (section 5.3), and the word "distribution-free" is not used without these hypotheses (analisi §4.8): the bound needs exchangeability, a fixed forecaster and the selection rule of section 4.2.
3. **With many tests per patient-day the level must be allocated**, otherwise the false alarms grow linearly with the number of tests (analisi §4.4); section 6.2.

### 6.2 The allocation over the tests of a patient-day

A **test** is one predictive decision at one level: one (template instance, prediction instant) pair of the patient-day at which the monitor may emit PREDICTED_VIOLATION. `n_tests` is an upper bound on the number of tests, fixed before the day from the care plan (templates times instances times prediction instants, over the templates that have a predictive channel); whether a given test occurs may depend on that test's own prefix (it is then an empty event when it does not occur), but the bound must not depend on outcomes or on other patients.

```
alpha_per_test = alpha_total / n_tests          (contract hook: AlphaAllocation.per_test(alpha_total, n_tests))
```

**Statement (union bound).** Suppose each test `t` of the patient-day has its own calibration set and satisfies H1 to H4 at the level `alpha_per_test`. Let `A_t` be the event "test `t` emits an alert and its instance ends with `sigma_tilde >= 0`" (a false predictive alert), with `A_t` empty if test `t` does not occur. Then

```
P( A_1 or ... or A_{n_tests} )  <=  sum over t of P(A_t)  <=  n_tests * alpha_per_test  =  alpha_total,
E[ number of false predictive alerts of the patient-day ]  <=  alpha_total.
```

*Proof.* Boole's inequality (the union bound) and Proposition 1 for each term; the expectation is the sum of the probabilities (linearity). No independence among the tests, among the instances of one patient, or among the calibration sets is used, and the calibration sets may be shared or not. ∎ The probability is over the randomness of the calibration sets and of the patient-day (the test patient is a fresh draw from the population), and the guarantee of each term is marginal (section 5.1).

**What it does not say.** (i) It is not conditional on the patient or on the history of the patient-day: given that a patient already received three alerts today, nothing is bounded. (ii) It says nothing about several days: over `D` days the union bound gives `D * alpha_total`, and the false alerts of one patient across days are not controlled by `alpha_total`. (iii) It does not say that the alerts of a patient-day are correct with probability `1 - alpha_total`: it bounds the probability of at least one false predictive alert, not the precision (section 5.5). (iv) It does not control the **missed** violations (Proposition 1b is a separate bound). (v) It is conservative when the tests are positively dependent (the union bound is then loose: the equicorrelated rows of the table below). (vi) It holds only for the tests that satisfy H1 to H4: a test whose calibration set is too small has no alert at all (below).

**Minimum calibration size.** Each test needs `n >= ceil(1 / alpha_per_test) - 1` calibration episodes of distinct patients (section 4.7). With `alpha_total = 0.05` and `n_tests = 10`: `alpha_per_test = 0.005` and `n >= 199` (case C-5). An illustration, labelled as arithmetic and not as a statement about any care plan: five scheduled ticks a day with one prediction instant each give `n_tests = 5`, `alpha_per_test = 0.01` and `n >= 99` episodes per calibrator; with fewer calibration patients the options are fewer tests, a larger `alpha_total`, or no predicted alerts, and the last is reported as a finding (the monitor emits no alert and says why), not hidden.

**The contract hook.** `AlphaAllocation.per_test(alpha_total, n_tests)` returns `alpha_total / n_tests` for the uniform split (the Bonferroni allocation). Any weights `w_t >= 0` with `sum w_t <= 1` and `alpha_t = w_t * alpha_total` give the same bound; the uniform split is the only one that the contract names.

**Checked (tests, not proofs).** 40,000 simulated patient-days of 10 tests, `n = 399` calibration episodes per test (so that `alpha_per_test = 0.005` has a finite quantile), forecasts set just below minus the population quantile of the test level, so that alerts are frequent and false alerts are possible:

| Test scores within the day | Level per test | `P(at least one false alert)` | Mean number of false alerts |
|---|---|---|---|
| independent | 0.05 (no allocation) | 0.2356 | 0.2645 |
| independent | 0.005 (Bonferroni, `alpha_total = 0.05`) | 0.0192 | 0.0194 |
| equicorrelation 0.9 | 0.05 | 0.0934 | 0.2663 |
| equicorrelation 0.9 | 0.005 | 0.0097 | 0.0196 |
| one calibration set shared by the 10 tests, independent test scores | 0.05 | 0.2150 | 0.2657 |
| the same shared set | 0.005 | 0.0197 | 0.0200 |

Without allocation the probability of at least one false alert exceeds `alpha_total = 0.05` and the mean number of false alerts grows with the number of tests (0.26 for ten tests at 0.05 each); with the allocation the probability is below `alpha_total` in all three dependence structures. The numbers are far below the bound because the scenario is not tight; the test shows that the union bound needs no independence, not that it is sharp.

### 6.3 Multiple prediction instants of one instance

The `|Pi_i|` instants of one instance count as tests in `n_tests` (T05 section 4.3, consequence 2); a warning is sticky, so an instance contributes at most one alert, and counting every instant is conservative.

## 7 Recalibration and shift

**Recalibration (contract rule 4, R2 weakness 6).** Every model update pushed from the back-end (a new forecaster, a new scale, a change of the clipping rule, a new set of prediction instants) triggers `fit` of the calibrator on episodes held out from the training of the new model (H2): the quantile of a calibrator fitted for another model has no guarantee for the new one. The monitor refuses a calibrator older than the model version. The contract text gives no way to compare versions (the interface has no token for it); WS05-T06 step 6 plans one (`calibrated_for`, `model_version`), and this is recorded as a contract gap (section 10). Two cautions that follow from H2: (i) the held-out episodes are consumed by the calibration, so the number of calibration patients required (section 4.7) is a recurring cost of each update; (ii) selecting the new model by its performance on the calibration episodes breaks H2 (the model then depends on the calibration set), and a separate set is needed for the selection.

**Distribution shift (R2 weakness 6, question 4).** If the test population differs from the calibration population (another cohort, another ward, a changed measurement process) H1 fails and **Proposition 1 is not claimed**. **Checked (a test):** calibration on `N(0, 1)` scores and test scores from `N(mu, 1)`, `n = 99`, `alpha = 0.1`, 200,000 pairs: `P(R_{n+1} > q)` is 0.1003 for `mu = 0` and 0.1495, 0.2145, 0.3833 for `mu = 0.25, 0.5, 1.0`. The adaptive variant (adaptive conformal inference, analisi §3.2, `[ref-needed: WS03]`; the key `gibbs-candes-adaptive-conformal` is recalled and unverified) updates the level online and is **evaluated empirically in ablation A6**, calibrating on one cohort and testing on the other; the corresponding non-exchangeable analyses (`barber-beyond-exchangeability`, `zhao-robust-conformal-stl`, same status) are named by topic only. What the adaptive variant guarantees is a statement of the cited work that is not reproduced here; the claim of this project for it is empirical.

The guarantee string of section 2.2 describes the **split** calibrator. For the adaptive mode (`mode = "adaptive"`) whether it describes the procedure depends on what is proved for it, which this document does not reproduce (the cited work is unverified), so WS05-T06 must give the adaptive calibrator its own guarantee string stating what is claimed; until a verified statement exists the claim for the adaptive mode is the empirical one of A6 (section 10, item 10).

## 8 Golden examples

### 8.1 The file

`docs/formal/golden/conformal.yaml`, seven cases in the README format (the format key `eval_at_ms` is omitted because the cases test functions, not records at a monitor time); every case has a `hand_calculation`, and the file was written before this document and recomputed independently once more, with integer rank arithmetic and with `math.erf` for the normal cdf, by a script that is not part of the repository.

| Case | What it fixes | Section |
|---|---|---|
| C-1 | the quantiles of the fixture scores `[-0.30, -0.22, -0.18, -0.12, -0.05, 0.00, 0.04, 0.09, 0.15]` (`n = 9`) at levels 0.05, 0.1, 0.2, 0.3, upper and lower; the exact coverage identity `8/10` | 4.4, 5.3 |
| C-2 | the variant "likely" at `alpha = 0.2`: five `sigma_hat`, the count `m`, `alpha*`, `rho`, the `Rho` fields; the case `-1/3` is the calibrator part of V-PRED-1 | 4.5, 4.6, 2.2 |
| C-3 | the variant "possible": the lower quantile and the symmetric form disagree | 5.7 |
| C-4 | exact ranks against the floating-point product (`n + 1 = 100`; alpha 0.41 and 0.29) | 4.4 |
| C-5 | the minimum calibration size, the allocation, and no alert at `n = 9`, `alpha = 0.05` | 4.7, 6.2 |
| C-6 | measured rho with `cuff_error_sd = 6`: limit, band, RESP (two cases) | 3.2 |
| C-7 | DETERMINISTIC `rho = 1`; `None` for SATISFIED and PENDING | 2.3, 1.2 |

### 8.2 How WS05-T06 loads the file, and what each case needs

- Levels are decimal literals: read `alpha` as `Fraction(repr(alpha))` and compute ranks in integers (section 4.4); `alpha_exact` is given where the fraction matters (C-4, C-5).
- `m` is counted with the expression of the emission test (`sigma_hat + R_i < 0`).
- `PredictedViolation.rho` is `None` when `emitted` is false (C-2, rows 2 and 4); the golden key `one_minus_alpha_star` is a diagnostic and not a field.
- The `Rho` of an emitted prediction has `alpha` equal to the configured level and the exact strings of section 2.2.
- C-3 asks for the variant "possible" with the lower quantile; a calibrator that exposes only `quantile` can obtain it by the duality of section 5.7 (or by a new method, CP4). The fixture of WS05-T06 (`R = [-0.2, -0.1, 0.0, 0.1, 0.1, 0.2, 0.3, 0.4, 0.6]`) gives `q_{0.8} = 0.4` and `q^lo_{0.2} = -0.1`: for `sigma_hat = 0.3` the lower-quantile form `0.3 - 0.1 = 0.2 >= 0` does **not** emit, while the symmetric reading `0.3 - 0.4 < 0` emits; WS05-T06 test 8 and WS05-T08 test 7 quote the literal reading as the expected example while deferring to this document's definition, and are to be adapted (section 10, item 9).
- C-6: the sub-case "bp 140 gives 0.5" evaluates the function at the limit; the record with `bp = 140` is SATISFIED (the atom `bp <= 140` is non-strict, T02, tie rule of T05 section 3.4) and has `rho = None`; the golden item has `record: null`.

### 8.3 Property-test design for WS05-T06

1. **Exact identity (no Monte Carlo).** For continuous i.i.d. scores the coverage of `q_{1-alpha}` is exactly `k / (n + 1)` with `k = ceil((n + 1)(1 - alpha))`: checked by enumerating all orderings of `n + 1` distinct values for `n` up to 7, or in rational arithmetic as `(n + 1 - k) / (n + 1) <= alpha` for `n` in `1..30` and `alpha = i / 20` (WS05-T06 test 12).
2. **Ties, exact.** A finite alphabet with repeated values, `P(R_{n+1} > q_{1-alpha})` computed exactly by enumeration: at most `(n + 1 - k) / (n + 1)`, never above, and strictly below in most cells.
3. **Monte Carlo coverage with a tolerance of three standard errors of the estimate, not a chosen constant.** Use a fresh calibration set for every test point; the indicator `R_{n+1} > q` of one pair is then a Bernoulli variable with the exact probability `(n + 1 - k) / (n + 1)` for continuous scores, and the standard error is `sqrt(p (1 - p) / N)`. If one calibration set is reused for many test points the binomial error is too small (the realised coverage of one set varies, section 5.3) and the standard error must be that of the per-set rates (the rule of WS05-T06 test 13). Fix the seed and the tolerance rule before the run. At `z = 3` about 0.27 percent of the equality tests exceed by chance (section 5.8 observed one of 170): a rerun with an independent seed, not a wider tolerance, separates chance from a defect.
4. **The false-alarm event with `sigma_hat`:** `P(alert and sigma >= 0) <= alpha + 3` standard errors, with `sigma_hat` independent of `R`, heteroscedastic, heavy-tailed and discrete.
5. **No alert for `n < 1 / alpha - 1`:** `quantile` is `+infinity` and `predict` has `emitted` false and `rho` `None`.
6. **Floating point:** the cases C-4 and a grid of the form of section 4.4; a mutant that computes the rank with the float product must fail.
7. **Negative controls:** a mutant that uses the symmetric form on the asymmetric fixture must fail C-3; a calibrator fitted on the wrong population must fail the coverage test of section 7; a mutant that returns `rho` for a non-emitted prediction must fail C-2.
8. The three-sentence caveat of section 6.1 appears in the docstrings (WS05-T06 step 4).

## 9 Paper excerpt (Sections IV-B and IV-C)

Size, measured on a stub `IEEEtran` journal document at 10 pt (two columns): see the paragraph after the block. Packages assumed: `amsthm` (with `\newtheorem{proposition}{Proposition}`), `amsmath`. Citations are not written (all conformal entries are unverified, ADR-018): the places where a reference belongs carry `[ref-needed: WS03]` as a comment. Table I of the workshop paper (rho = 0.42 on a deterministic counter) is the example of the confusion that the first paragraph removes. The excerpt gives the table of rho (three rows), Proposition 1 with a short proof, and the two-sentence caveat paragraph.

```latex
\subsection{Confidence $\rho$ per Verdict Type}
\label{sec:rho}

The confidence $\rho\in[0,1]$ answers one question: how confidently can the violation be claimed.
It is defined only for \textsc{violated} and \textsc{predicted-violation} records and is absent for \textsc{satisfied} and \textsc{pending}.
Whether an event is authentic, or due to a given cause, is the question of the attributed cause $\kappa$, not of $\rho$; a counter over the event log has $\rho=1$ whatever its cause.

\begin{table}[t]
\caption{Confidence $\rho$ by verdict type. $s$ is the device-error standard deviation (to be set from a device validation protocol).}
\label{tab:rho}
\centering
\footnotesize
\begin{tabular}{@{}p{1.95cm}p{2.9cm}p{2.5cm}@{}}
\hline
Kind & Definition of $\rho$ & Guarantee \\
\hline
\textsc{measured} & $\Pr[\sigma_{\mathrm{true}}<0\mid\text{measurement}]$; e.g.\ $\Phi((x-L)/s)$ for a limit $L$, $\Phi((\delta-r)/(s\sqrt2))$ for a drop $r$ & conditional on the adequacy of the declared device error model \\
\textsc{predicted} & $1-\alpha^*$, $\alpha^*=\inf\{\alpha:\hat\sigma+q_{1-\alpha}<0\}$, a conformal $p$-value & marginal over patient episodes under exchangeability \\
\textsc{deterministic} & $1$, for a predicate over the event log & conditional on the integrity of the log; authenticity goes to $\kappa$ \\
\hline
\end{tabular}
\end{table}

\subsection{Conformal Early Warning}
\label{sec:prop}

An episode is one decision point of one template instance of one patient-day.
Let $R=\tilde\sigma-\hat\sigma$ be its one-sided score, where $\hat\sigma$ is the forecast and $\tilde\sigma$ the normalised robustness of the completed trace.
Let $q_{1-\alpha}$ be the $\lceil(n{+}1)(1-\alpha)\rceil$-th smallest of $n$ calibration scores ($+\infty$ if that rank exceeds $n$), and $m=\#\{i:\hat\sigma+R_i<0\}$.
A \textsc{predicted-violation} is emitted only while the record is \textsc{pending} and when $\hat\sigma+q_{1-\alpha}<0$; then $\rho=m/(n{+}1)$.
% [ref-needed: WS03] split conformal quantile; conformal STL runtime verification

\begin{proposition}\label{prop:alarm}
Let the scores of $n$ calibration episodes and of the test episode, taken from distinct patients, be exchangeable, with the forecaster and the normalisation fixed before they are drawn, and one designated prediction instant per episode.
Then $\Pr[\hat\sigma+q_{1-\alpha}<0\ \wedge\ \tilde\sigma\ge0]\le\alpha$, the probability being taken jointly over the calibration set and the test episode.
\end{proposition}
\begin{proof}
Let $k=\lceil(n{+}1)(1-\alpha)\rceil$; if $k>n$ nothing is emitted.
The event implies $R_{n+1}>q_{1-\alpha}$, so $R_{n+1}$ exceeds the $k$-th smallest of all $n{+}1$ scores, which at most $n{+}1-k$ scores do (ties only lower the count).
By exchangeability each score is equally likely to be the test one, so the probability is at most $(n{+}1-k)/(n{+}1)\le\alpha$.
\end{proof}

The calibration unit is the patient episode, not the time step, and the guarantee is marginal over patient episodes under exchangeability: it is not conditional on a patient, it says nothing under distribution shift, and $\rho$ is neither the posterior probability of a violation nor the precision of the alerts.
With several predictive tests per patient-day the level is split, $\alpha_{\mathrm{test}}=\alpha_{\mathrm{tot}}/n_{\mathrm{tests}}$, which bounds the probability of at least one false predictive alert per patient-day by $\alpha_{\mathrm{tot}}$ by the union bound.
```

Size, measured on a stub `IEEEtran` journal document at 10 pt (column width 252 pt, text height 696 pt, so one page is 1,392 pt of column height; the excerpt compiles with `pdflatex` with no undefined reference and no overfull box after the second pass, and the stub is not part of the repository): the whole excerpt is 631 pt, about 0.45 page; the table 137 pt, about 0.10 page; Proposition 1 with its proof 147 pt, about 0.11 page (the proof is three sentences, about five lines in a 252 pt column, one or two lines more than the 3 to 4 lines that analisi §7 budgets); the caveat paragraph 103 pt, about 0.07 page. The budgets are 0.3 page for Section IV-B (the whole row of definitions of rho and severity, T04 included) and 0.45 page for Section IV-C (monitoring, T05 included), so the excerpt alone uses the whole of the second budget and more than the first; WS12 trims in the final layout (candidates: the third row of the table, the last sentence of the caveat paragraph, or the first paragraph of the conformal subsection).

## 10 Open points for WS01-T08

Each item gives the anchor, the resolution adopted or the question handed over, and whether an ADR is needed. None edits `02-interfaces.md`. The numbering is used by the Notes of the task file.

**1. CP4 (`02-interfaces.md#verdict` rule 2, `#conformal-calibrator`).** *Gap:* the "possible" variant uses `sigma_hat - q < 0`; the calibrator exposes only the upper quantile; the form is valid only under symmetry (section 5.7). *Adopted meanwhile:* Proposition 1b with the lower quantile `q^lo_alpha`; the symmetric form is not adopted for the variant "possible"; the lower quantile is obtainable from `quantile` on episodes with `sigma_hat` and `sigma_true` exchanged (duality, section 5.7). *Options for the contract:* a method `quantile_lower(alpha)` (ADR, version bump), or the duality documented in the calibrator text, or the symmetric form with an explicit symmetry check. *ADR:* needed. *Handed to:* WS01-T08 (ADR), WS05-T06 (it plans `quantile_lower` if this document defines a lower tail: it does), WS05-T08 test 7.

**2. `Rho.alpha` of a predicted alert.** *Adopted here:* the configured level (the contract field is "nominal level for PREDICTED"); `alpha*` is recoverable as `1 - value`. *Alternative not adopted:* `alpha*` itself, which would repeat `value` and lose the configured level at which the monitor ran. *ADR:* no (a clarification of the field comment, to be made in the contract text at the discretion of WS01-T08). *Handed to:* WS01-T08 (wording), WS05-T06 (golden C-2 checks it).

**3. Rho of the variant "possible".** *Adopted here:* the same value `m / (n + 1)` as the variant "likely" (the contract defines `alpha*` with the upper quantile); the guarantee string is the same; the variant is an emission rule whose guarantee is Proposition 1b. A possible-variant alert can carry a small value (C-3: 0.3 at `alpha = 0.2`). *Handed to:* WS01-T07 (how the alert shows a low `rho` with a flagged variant), WS05-T06, WS05-T08. *ADR:* no.

**4. `PredictedViolation.rho` when not emitted.** *Adopted here:* `None`. *Gap:* the contract comment does not say. *Handed to:* WS01-T08 (clarification), WS05-T06 (test 3).

**5. Severity of a predicted alert (OP-4 of T04, OP-15, OP-T05-4).** *Adopted here (the quantity):* `clip(sigma_hat + q, -1, 1)` with the quantile of the variant that emitted; negative for every emitted alert, so the contract range `[-1, 0)` holds and CP5 does not arise for predicted alerts (section 2.4). *Alternative:* `clip(sigma_hat, -1, 1)` (T04), with the range `[-1, 1]`. *Handed to WS01-T07* (the field of the tuple; the T07 task text, line 40, assumes the point forecast and the range `[-1, 1]` and is to be reconciled; WS05-T08 tests 5 and 15 and WS05-T04 step 8 assume the bound). *ADR:* together with CP5 if T07 changes the contract comment.

**6. Mapping of the `rho` kind for VIOLATED records.** *Adopted here (section 2.3):* RANGE, HOLD margin and RESP margin are MEASURED; guards, SCHED, COUNT, SYS and INT are DETERMINISTIC; the SYS row (open in T05) is DETERMINISTIC because the registry has no error model for durations. *Alternative:* a MEASURED rho for SYS with a timing error parameter (a new registry entry). *Handed to:* WS01-T08 (registry, if wanted), WS01-T07 (the alert table). *ADR:* no.

**7. Prediction instants and the allocation of the level (OP-T05-10, OP-T05-16).** *Adopted here (section 4.3):* one designated instant per episode (a rule from the care plan and the information at that instant); several instants need their own calibration sets and the union bound; per-step re-evaluation is not covered. *Handed to:* WS05-T08, which must reconcile "prediction once, at activation" (README D6, T08 lines 17, 46, 77) with V-PRED-1 (instant 09:10 on an instance activated at 09:00): both are single designated instants, so Proposition 1 covers both, provided the calibration episodes are scored at the same kind of instant; and WS01-T08 for the plan. *ADR:* no.

**8. Clipping of the forecast into the interval (T05 P4, OP-T05-10).** *Confirmed here* (section 4.1): `sigma_hat` is clipped into `[N_s(lo), N_s(hi)]` of the record, for calibration and test episodes alike; it is part of the fixed map of H2. *Handed to:* WS05-T08 (the calibration episodes must be built by the same function).

**9. Downstream tasks whose text this document contradicts or refines (their files are not edited here).** WS05-T06 test 8 and WS05-T08 test 7 (both defer to the definition of WS01-T06 and quote the literal reading `0.3 - 0.4 < 0`, emitted, as the example; the fixture gives `0.3 - 0.1 = 0.2 >= 0` with the lower quantile: not emitted); WS05-T06 step 3 (`ceil(round((n + 1) * (1 - alpha), 9))`: gave no wrong rank on the grid of section 4.4 for levels of at most two decimals, but the exact rule of section 4.4 is preferable); WS05-T06 test 2 (its remark that `10 * (1 - 0.3)` is a float-boundary case is not right in IEEE doubles: it evaluates to exactly 7.0 and its ceiling is 7, so that assertion does not exercise the pitfall; the boundary level of that fixture is `alpha = 0.7`, where `10 * (1 - 0.7)` evaluates to 3.0000000000000004, a float rank of 4 instead of 3, so `quantile(0.7)` must be 0.0, the third smallest score, and not 0.1); WS05-T08 lines 17, 46, 77 (item 7); WS01-T07 line 40 (item 5).

**10. Adaptive calibrator, guarantee string.** The string `marginal over patient episodes under exchangeability` is the guarantee of the split mode (section 7); `Rho.guarantee` for `mode = "adaptive"` is to be written by WS05-T06 with what is claimed for it (empirical until a verified statement exists), and ablation A6 reports it. *Handed to:* WS05-T06, WS08-T05.

**11. Which completed trace defines `sigma_true` (section 4.1).** The contract field says "latent or measured". *Adopted here:* observed-completed as the default (it is deployable and defines the false predictive alarm of T05); the latent-completed variant is a benchmark-only oracle, reported as such. *Handed to:* WS08 (declare the choice per experiment), WS01-T08 (a sentence in the contract text).

**12. `fit(episodes, alpha)` and `quantile(alpha)` both take a level.** A minor tension: the split calibrator is level-agnostic, so the level of `fit` is unused in split mode. *Handed to:* WS05-T06 (documentation).

**13. Model-version token (rule 4).** The contract text has no field that records the model version a calibrator was fitted for; WS05-T06 step 6 plans `calibrated_for` and `model_version`. *ADR:* WS05-T06 proposes it.

**14. Source of truth of the device error (T03 OP-7), and the mismatched run.** *Adopted here* (section 3.3): the monitor reads `cuff_error_sd` from the registry; the generator has its own `DeviceErrorModel.cuff_error_sd_mmhg`; the matched run uses one source value for both; WS08 runs a mismatched value and a non-flat population of true values (section 3.4). The task text's "trivially perfect calibration" is corrected: it requires also a flat prior. *Handed to:* WS01-T08 (registry wording), WS08, WS04-T06.

**15. Confirmed from T05.** `{sigma >= 0}` of Proposition 1 is the event "final verdict SATISFIED" for a decided instance (tie rule, Lemma 7); the numbers of V-PRED-1 (`q = 0.09`, `m = 9`, `alpha* = 0.1`, `rho = 0.9`, `Rho.alpha = 0.2`) are those of C-1 and C-2, recomputed in exact arithmetic (the check script of the golden file); the undecided instances are excluded from the false-alarm count and reported apart (section 4.1).

**16. Deviations from the task text (details in the Notes of the task file).** (a) C-4: the floating-point failure is real, but exact arithmetic on the binary value of `alpha` fails in the same way; the exact ranks need the decimal literal. (b) C-6: the item "bp 140 gives 0.5" is not a VIOLATED record. (c) C-2 and C-3: `rho` is `None` for a non-emitted prediction; the values 0.7 and 0.0 appear as `one_minus_alpha_star`. (d) The statement that the symmetric form is "valid only if" the distribution is symmetric is stated as "valid under symmetry, not in general". (e) "Trivially perfect" calibration of the measured rho needs a flat prior as well as a matched standard deviation.
