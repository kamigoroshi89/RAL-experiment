# 04 Normalised robustness and lexicographic alert ranking

Document WS01-T04. Feeds paper Section IV-B (the severity part; the rho part comes from WS01-T06), `normalise` and `rank_alerts` of WS05-T03, the raw-robustness view of baseline B3 (WS06-T04) and the ablation A3 (WS08-T03). Draft for the M1 freeze (WS01-T08); it changes no contract of `docs/plan/02-interfaces.md` (gaps and clarifications are recorded in section 10). It builds on `docs/formal/02-templates.md` (WS01-T02: margin and guard rule, one unit per template, registry names `scale_<id>` and `priority_<id>`, open points TG-1 to TG-14, all respected and not overridden), `docs/formal/03-parameter-registry.md` and `configs/registry/hypertension.yaml` (WS01-T03: which scales and priorities are seeded and which are unset) and `docs/formal/01-signals-sampling.md` (WS01-T01). Validation in this project is technical and pre-clinical; nothing in this document is a clinical claim.

Every clinical number is either fixture arithmetic (FIXTURE-ONLY, fixture registry F0 of `docs/plan/workstreams/WS01-formalization/README.md`) or a value of analisi §4.1, §4.2, §4.6 or §4.7 labelled "illustrative, unverified" (ADR-020). Scales and priorities are registry values fixed by the clinician at the review of WS00-T07, which has not happened: no scale and no priority in this project is clinically anchored yet. The order of the priorities is the clinician's; this document defines how an order is used and never claims that any order is clinically correct. Inputs of `normalise` and `rank_alerts` are raw robustness values of the observed trace (or forecasts made from it) and registry values; nothing here reads `LatentDay` or `GroundTruthEvent`.

What this document answers (review items): R1 weakness 2 (a `min` over mmHg, minutes and doses is defined but empty of meaning: sections 1 to 4) and the unit part of AE-5 (the workshop Table I compares -12, -21 and -8 with no unit).

**Notation.** `sigma` is raw robustness in the unit of the template margin (`mmHg`, `ms` or `dose`); `s` is the scale of the template (registry entry `scale_<id>`, same unit as `sigma`, `s > 0`); `sigma_tilde` (code name `sigma_norm`) is normalised robustness, dimensionless in `[-1, 1]`. "Robustness" is used only for STL semantics; "severity" is used for the reading of `sigma_tilde`. `t_ms` is the alert time of `Detection.t_ms`. References are not cited from memory: where a reference would be needed the marker `[ref-needed: WS03]` is written, together with the key of the candidate entry of `paper/refs/references.bib` when one exists (every such entry has `verified = {false}`, ADR-018, and none may be cited in the paper until a human verifies it).

## 1 The unit problem

**1.1 What is wrong.** The workshop paper composes templates by `sigma(phi_1 and phi_2) = min(sigma_1, sigma_2)` and claims that the robustness "allows the RSM to rank alerts by severity". The three quantities that meet in that `min` are in different units: a pressure margin in mmHg (RANGE, HOLD, RESP), a timing margin in minutes or milliseconds (SCHED, SYS, INT) and a count margin in doses (COUNT) (analisi §4.2). The workshop Table I shows the result: -12 (mmHg), -21 (seconds?) and -8 (unit unknown) (analisi §2 R1 weakness 2). The `min` of those three numbers is -21, a number without a unit, and which of the three is "worst" changes with the unit in which the time and the count happen to be written.

**1.2 A worked instance.** Take three violated instances with the raw values of the golden cases of `docs/formal/golden/templates.yaml`: hold -6 mmHg (G-HOLD-2), range -12 mmHg (G-RANGE-2) and sched -1260000 ms (G-SCHED-3). Ordered by raw value, ascending, in the units of the templates the order is sched (-1260000), range (-12), hold (-6). Write the timing margin in hours, `-1260000 / 3600000 = -0.35`, and the order becomes range (-12), hold (-6), sched (-0.35). The same three facts, two different orders: the raw comparison is a comparison of the unit chosen, not of the severity. Section 7 uses this instance (golden case RK-4) as the null ranking of ablation A3.

**1.3 The two problems and what solves each.**

1. *Comparability.* A number in mmHg and a number in ms cannot be compared or combined. Solved by normalisation per template, `sigma_tilde = clip(sigma / s, -1, 1)` with a clinically fixed scale `s` (section 2). After normalisation, `min` and `max` have a meaning (section 3).
2. *Relevance.* Even after normalisation, a timing deviation of 0.7 of its scale is not "worse" than a pressure deviation of 0.6 of its scale in any way the specification can decide: which class of deviation matters more is a clinical judgement. Solved by the lexicographic order between classes: clinician priority first, `sigma_tilde` inside a priority (section 4).

The degenerate spatial robustness of Boolean predicates (R1 weakness 3) is treated by the margin and guard rule of `02-templates.md` section 2, which gives every template exactly one margin dimension; this document starts from that rule. The three steps of analisi §4.2 (normalisation per predicate, lexicographic order between classes, alternatives to cite) are sections 2 to 5, and the prohibition of normalising by the width of a conformal interval is section 6. Time robustness for timing constraints, recommended by analisi §4.2, is the far-edge slack of `02-templates.md` section 2.3; the literature on it is `[ref-needed: WS03]` (candidate keys `rodionova-time-robustness` and `donze-maler-robust`, both unverified).

## 2 Normalised robustness

### 2.1 Definition

Let the extended reals be `R* = R union {-inf, +inf}` (the raw robustness of an instance is in `R*`: a failed guard gives `-inf`, `02-templates.md` section 2.5). For a scale `s` with `0 < s < inf` and `sigma` in `R*` and not NaN:

```
sigma_tilde = normalise(sigma, s) = clip(sigma / s, -1, 1)
clip(x)     = max(-1, min(1, x))
```

with the conventions `(+inf) / s = +inf`, `(-inf) / s = -inf`, `clip(+inf) = +1` and `clip(-inf) = -1`. So `normalise(-inf, s) = -1.0` and `normalise(+inf, s) = +1.0`. The scale `s` is the registry entry named by `Template.scale_param` (`scale_range`, `scale_sched`, ...), in the unit of the template's margin dimension (`02-templates.md` section 2.6). The return value is a `float` for every real argument, integers included. The contract signature is `normalise(sigma_raw: float, scale: float) -> float` (argument order: raw value first, scale second) and is not changed.

### 2.2 Properties (lemmas)

Let `N_s(sigma) = normalise(sigma, s)` with `s` finite and `s > 0`, and `sigma`, `a`, `b` in `R*` (not NaN) unless stated.

**Lemma 1 (range).** `-1 <= N_s(sigma) <= 1`.
*Proof.* `clip` maps `R*` into `[-1, 1]`.

**Lemma 2 (sign preservation).** `N_s(sigma) >= 0` if and only if `sigma >= 0`; `N_s(sigma) < 0` if and only if `sigma < 0`; `N_s(sigma) = 0` if and only if `sigma = 0`.
*Proof.* Since `s > 0`, `sigma / s` has the sign of `sigma` (also for `+-inf`). `clip` fixes 0, gives `min(1, x) > 0` for `x > 0` and `max(-1, x) < 0` for `x < 0`. Consequence: the Boolean verdict of a template instance, "satisfied iff `sigma >= 0`" (`02-templates.md` section 1.3), is the same on `sigma` and on `sigma_tilde`. Normalisation never changes a verdict; it only grades it. For the same reason the event `sigma >= 0` in Proposition 1 (WS01-T06) is the same in raw and in normalised units (to be confirmed by WS01-T06).

**Lemma 3 (monotonicity).** If `a <= b` then `N_s(a) <= N_s(b)`. On `[-s, s]` the function is strictly increasing in exact arithmetic (in floating point it is non-decreasing and can tie on adjacent doubles, section 2.3 (c)). `N_s(sigma) = -1` iff `sigma <= -s`, and `N_s(sigma) = +1` iff `sigma >= s`.
*Proof.* Division by `s > 0` is strictly increasing on `R*`; `max` and `min` with constants are non-decreasing; a composition of non-decreasing functions is non-decreasing. On `[-s, s]`, `sigma / s` lies in `[-1, 1]` and `clip` is the identity, so the composition is strictly increasing over the reals (not over doubles: section 2.3 (c)). `sigma / s <= -1` iff `sigma <= -s` (and likewise at `+1`).
*Corollary (intervals).* If a raw robustness interval is `[lo, hi]` (`#verdict`, `RobustnessInterval`), then `N_s(x)` lies in `[N_s(lo), N_s(hi)]` for every `x` in `[lo, hi]`; the field `sigma_norm_interval` of a `VerdictRecord` is `(normalise(lo, s), normalise(hi, s))`, and infinite endpoints are allowed.
*Cost of the clip.* Two violations that both exceed the scale, at `sigma <= -s`, receive the same value `-1`: below a clinically significant deviation the ordering is graded, beyond it it is not (the tie is then decided by `t_ms` and `instance_key`, section 4). This is a deliberate design choice, and it is reported as a limitation where severity ordering is evaluated.

**Lemma 4 (scale equivariance and unit invariance).** For `k > 0` (finite), `N_{k s}(k sigma) = N_s(sigma)`; that is, `normalise(k * sigma, k * s) = normalise(sigma, s)`.
*Proof.* `(k sigma) / (k s) = sigma / s`, and `k * (+-inf) = +-inf`.
*Corollary.* Changing the unit in which `sigma` and `s` are written, both by the same factor (ms to minutes, `k = 1/60000`), does not change `sigma_tilde`, if scale and value are in the same unit. The precondition is a property of the registry, not of the function: `normalise` receives two floats and cannot see units; the loader checks that `scale_<id>` has the unit of the template margin (`03-parameter-registry.md` section 2.5, rule 10). Raw comparisons (section 7) are not unit invariant (section 1.2).

**Lemma 5 (identity zone).** If `|sigma| <= s` then `N_s(sigma) = sigma / s` (the clip changes nothing).
*Proof.* `sigma / s` is in `[-1, 1]`.

**Lemma 6 (Lipschitz).** For finite `a`, `b`, in exact arithmetic: `|N_s(a) - N_s(b)| <= |a - b| / s` (in floating point the bound can fail by one unit in the last place, section 2.3 (d); it is not a Hypothesis property).
*Proof.* Division by `s` scales differences by `1 / s` and `clip` is 1-Lipschitz. A measurement error of size `e` in `sigma` therefore moves `sigma_tilde` by at most `e / s`.

**Lemma 7 (dependence on the scale).** For `sigma <= 0` and `0 < s_1 <= s_2`: `N_{s_1}(sigma) <= N_{s_2}(sigma)`; for `sigma >= 0` the inequality is reversed.
*Proof.* For `sigma <= 0`, `sigma / s_1 <= sigma / s_2`, and `clip` is non-decreasing. A larger scale makes the same violation less severe, monotonically; a sensitivity analysis over the scale has no surprises.

**Properties that WS05-T03 must implement (Hypothesis).** `tests/spec/test_normalise.py` must contain a Hypothesis test for each line, with `s` drawn from positive finite floats, `sigma` from floats including `+-inf` and excluding NaN, and a fixed seed:

| Id | Property | Note for the strategy |
|---|---|---|
| P-N1 | `-1.0 <= normalise(sigma, s) <= 1.0` | Lemma 1 |
| P-N2 | `normalise(sigma, s) >= 0` iff `sigma >= 0`; `< 0` iff `sigma < 0` | Lemma 2; restrict to `sigma = 0` or `|sigma| >= 1e-300` and `s <= 1e12` (section 2.3, underflow) |
| P-N3 | `a <= b` implies `normalise(a, s) <= normalise(b, s)` | Lemma 3; holds exactly in IEEE arithmetic, because correctly rounded division by a positive number is non-decreasing |
| P-N4 | `normalise(k * sigma, k * s) == normalise(sigma, s)` | Lemma 4; precondition: `k` finite and positive and `k * s` finite and positive (otherwise `normalise` raises `ValueError` on correct code, section 2.3 (e)); exact equality when `sigma`, `s` and `k` are integer-valued floats with all products below `2**53`; otherwise `pytest.approx(rel=1e-12, abs=1e-12)` |
| P-N5 | `abs(sigma) <= s` implies `normalise(sigma, s) == sigma / s` | Lemma 5 |
| P-N6 | `sigma <= -s` implies `-1.0`; `sigma >= s` implies `+1.0` | Lemma 3 (saturation) |
| P-N7 | `normalise(-inf, s) == -1.0` and `normalise(+inf, s) == 1.0` | section 2.4 |
| P-N8 | `s <= 0`, `s` NaN or infinite, or `sigma` NaN raises `ValueError` and never returns | section 2.4 |
| P-N9 | `a <= b` implies `normalise(a, s) <= normalise(b, s)` for the two ends of an interval, so `sigma_norm_interval` encloses `normalise(x, s)` | Corollary of Lemma 3 |

A loader of the golden file (WS05-T03 test 1) must handle three shapes: N-7 gives `sigma_norm` as a two-element list, one value per element of `inputs.calls`; N-8 and N-9 give `expected.error` instead of a value, and each input listed there must raise. The golden cases N-1 to N-10 of `docs/formal/golden/ranking.yaml` are the example-based tests: N-10 is P-N4 with `k = 3`, N-3 and N-6 are P-N6, N-7 is P-N7, N-8 and N-9 are P-N8.

### 2.3 Floating point

`normalise` is specified on the real numbers. In IEEE 754 double arithmetic, division is correctly rounded, so when the exact quotient is a decimal such as `-12 / 20` the result is the double nearest to `-0.6`, and `normalise(-12, 20) == -0.6` holds (likewise `normalise(-1260000, 1800000) == -0.7`, golden cases N-1 and N-5). Two caveats are stated so that a test does not assert more than the arithmetic gives. (a) Underflow: for a tiny `sigma` the quotient can round to `-0.0` or `0.0` (for example `-5e-324 / 1e10`), so Lemma 2 holds in exact arithmetic and for `|sigma| / s` above the smallest positive double; the Boolean verdict is always taken from the raw `sigma` and never from `sigma_tilde`, so no verdict is affected, and the contract range "`[-1, 0)` for a violation" reads `[-1, 0]` in floating point. The value `-0.0` compares equal to `0.0` and sorts equal to it. (b) Equivariance is exact for integer-valued arguments (the products are exact and the quotient is the correctly rounded value of the same rational number) and holds only up to a relative error of the order of one unit in the last place for general floats. (c) Strict monotonicity on `[-s, s]` (Lemma 3) holds in exact arithmetic only: two adjacent doubles `a < b` can give the same quotient, for example `a = 30.406514242198472`, `b = 30.406514242198476` with `s = 587993.0255374159` (and at the underflow of caveat (a)), so in floating point `N_s` is non-decreasing, which is what P-N3 states, and a test must never assert strict increase on doubles. (d) The Lipschitz bound of Lemma 6 can fail by one unit in the last place in floating point, because the quotients are rounded; a test of it needs a relative tolerance of a few units in the last place, and it is not one of the properties of section 2.2. (e) In P-N4 the products `k * sigma` and `k * s` are themselves rounded and can overflow or underflow: if `k * s` is not finite and positive (for example a factor `k` that overflows `k * s`, or underflows it to `0.0`), `normalise` raises `ValueError` as section 2.4 requires; the strategy of the test must draw `k` so that `k * s` is finite and positive, and must not treat that `ValueError` as a failure of the function.

### 2.4 Errors and infinities (no silent default)

| Condition | Behaviour |
|---|---|
| `scale <= 0` | raise `ValueError`, before any division (golden N-8: `normalise(5, 0)`) |
| `scale` NaN or `+-inf` | raise `ValueError` (an infinite scale would give `0` for every finite deviation; the registry never stores a non-finite value, `03-parameter-registry.md` section 2.5 rule 1) |
| `sigma_raw` NaN | raise `ValueError` (golden N-9): NaN has no value, and an unknown atom is handled by the interval semantics of WS01-T05, never by a NaN |
| `sigma_raw = -inf` | return `-1.0` (a failed guard, golden N-7); the marker `guard_failed` of `02-templates.md` section 2.1 travels with the alert, not with the number |
| `sigma_raw = +inf` | return `+1.0` (the vacuous whole-formula value; it does not occur in a decided instance, `02-templates.md` section 2.5 item 1) |
| the scale entry is unset in the registry | `normalise` is never reached with it: the caller resolves the scale with `registry.get(template.scale_param)`, which raises `UnsetParameterError` (`03-parameter-registry.md` section 2.5 rule 4), and the error propagates; no default scale, no fallback to `1.0` |

The builtin `ValueError` is the specific error required; the contract names no error type, and WS05-T03 may raise a subclass of `ValueError` (the test of WS05-T03 catches `ValueError`). A message names the argument and the rule. This resolves TG-10 of `02-templates.md` (the contract text says nothing about infinities): `+-inf` maps to `+-1`, and a finite value that is clipped (`sigma <= -s`) and a failed guard have the same `sigma_tilde = -1` and are told apart by the marker.

### 2.5 Meaning of the scale

The scale `s` is the clinically significant deviation: the size of a deviation, in the unit of the template, that the clinician considers to be one full unit of severity, fixed with the clinician and reported in the template table (analisi §4.2). Analisi §4.2 gives three examples: 20 mmHg, 30 min and 1 dose; they are illustrative, unverified. Analisi §4.2 does not say which template each belongs to; the assignment used here (`scale_range` 20 mmHg, `scale_sched` 30 min, `scale_count` 1 dose) is the one of the F0 table and of the seed registry, and it is illustrative, unverified. This document assigns no scale to any template that the analisi does not name: `scale_hold`, `scale_resp`, `scale_sys` and `scale_int` are unset in `configs/registry/hypertension.yaml` until WS00-T07. The F0 values of those four (20 mmHg, 20 mmHg, 30000 ms, 300000 ms) are FIXTURE-ONLY, live in `docs/formal/golden/` and must not be copied into the registry.

Reading of the value, conditional on the clinician's scale: `sigma_tilde = -0.6` means "0.6 of a clinically significant deviation beyond the limit"; `sigma_tilde = -1` means "at least one clinically significant deviation beyond the limit, or a failed guard"; `sigma_tilde = +0.75` means "satisfied with a margin of three quarters of the scale".

## 3 Where normalisation is applied

### 3.1 Per template decision, in the template's own unit

Normalisation is applied to the raw robustness of one template instance at its decision step (`02-templates.md` section 1.5), using the scale of that template and the unit of its margin dimension (the margin rule of `02-templates.md` section 2.1: one margin dimension per template, every other atom a guard equal to `+-inf`). The chain in the monitor is `sigma_i` (raw, template unit) then `s = registry.get(template.scale_param)` then `normalise(sigma_i, s)`. A guard never turns into a finite number, and a failed guard gives `-1`.

| Template | Margin unit | `scale_param` | Scale in registry 0.1.0 | F0 value | `priority_param` | Priority in registry 0.1.0 | F0 value |
|---|---|---|---|---|---|---|---|
| RANGE | mmHg | `scale_range` | seeded, 20 (illustrative, unverified) | 20 | `priority_range` | seeded, 2 (illustrative, unverified) | 2 |
| SCHED | ms | `scale_sched` | seeded, 1800000 (illustrative, unverified) | 1800000 | `priority_sched` | seeded, 3 (illustrative, unverified) | 3 |
| HOLD | mmHg | `scale_hold` | unset | 20 (FIXTURE-ONLY) | `priority_hold` | seeded, 1 (illustrative, unverified) | 1 |
| COUNT | dose | `scale_count` | seeded, 1 (illustrative, unverified) | 1 | `priority_count` | unset | 2 (FIXTURE-ONLY) |
| RESP | mmHg | `scale_resp` | unset | 20 (FIXTURE-ONLY) | `priority_resp` | unset | 2 (FIXTURE-ONLY) |
| SYS | ms | `scale_sys` | unset | 30000 (FIXTURE-ONLY) | `priority_sys` | unset | 3 (FIXTURE-ONLY) |
| INT | ms | `scale_int` | unset | 300000 (FIXTURE-ONLY) | `priority_int` | unset | 3 (FIXTURE-ONLY) |

Consequence, stated because it limits what can run, as far as scale and priority are concerned (other unset names, such as `sched_window`, limit evaluation further): with registry 0.1.0, RANGE and SCHED can be normalised and ranked; COUNT can be normalised but not ranked (its priority is unset); HOLD can be ranked but not normalised (its scale is unset); RESP, SYS and INT can be neither. Asking for an unset name raises `UnsetParameterError` until the clinician review sets the value; no agent supplies it (ADR-020).

The same normalisation applies wherever a robustness value enters a comparison, a report or a calibration: the `sigma_norm` of an alert, the `sigma_norm_interval` of a `VerdictRecord` (Lemma 3, corollary), and the forecast `sigma_hat` of the forecaster and the conformal calibrator, which `#conformal-calibrator` defines in normalised units. The scale is a fixed registry value: it is not estimated from data (from the residuals of a forecaster, from the spread of a patient's measurements or from the width of a conformal interval), because a data-dependent scale would change the severity of the same clinical deviation whenever the data change (section 6).

### 3.2 `min` and `max` over templates

A `min` or `max` over robustness values of different templates is meaningful only on normalised values, and only for reporting: the contract rule reads "the conjunction of templates is never a `min` over raw values in different units; only normalised values are compared" (`#template`). It is used, for example, for the worst instance of a patient-day in Fig. 2 (`min` over the `sigma_tilde` of the instances of the day). It is not used to order alerts, because it ignores priority (section 4), and it is never used to merge alerts.

Alerts are per template instance. They are never merged into one number, and the decomposition `phi = phi_CP and phi_SYS and phi_INT` is kept as separately evaluated conjuncts, each with its own unit, scale and priority (`02-templates.md`, last paragraph of section 9). Raw robustness stays inside `spec` (the `sigma_interval` of a `VerdictRecord`, in the native unit) and inside baseline B3, which reports raw robustness in native units and never normalises (section 7).

### 3.3 Parameters used

| Name | Unit | Origin | Status in registry 0.1.0 |
|---|---|---|---|
| `scale_range` | mmHg | analisi §4.2 example (assignment as F0) | entry, 20.0, `reviewed_by` null |
| `scale_sched` | ms | analisi §4.2 example, 30 min | entry, 1800000.0, `reviewed_by` null |
| `scale_count` | dose | analisi §4.2 example | entry, 1.0, `reviewed_by` null |
| `scale_hold`, `scale_resp` | mmHg | F0: FIXTURE-ONLY (20) | unset |
| `scale_sys`, `scale_int` | ms | F0: FIXTURE-ONLY (30000; 300000) | unset |
| `priority_hold` | rank, 1 = highest | analisi §4.2 order example | entry, 1.0, `reviewed_by` null |
| `priority_range` | rank | analisi §4.2 order example | entry, 2.0, `reviewed_by` null |
| `priority_sched` | rank | analisi §4.2 order example | entry, 3.0, `reviewed_by` null |
| `priority_count`, `priority_resp` | rank | F0: FIXTURE-ONLY (2, 2) | unset |
| `priority_sys`, `priority_int` | rank | F0: FIXTURE-ONLY (3, 3) | unset |

## 4 Lexicographic ranking

### 4.1 Fields read

`rank_alerts(alerts: Sequence[Alert]) -> list[Alert]` reads five fields of an alert: `priority` (an `int`), `sigma_norm` (a `float`), `t_ms` (a `TimeMs`, from `Detection`), `xi.instance_key` (a `str`) and, for the extension of section 4.5, `verdict`. It reads nothing else: not `kappa`, not `rho`, not the patient. `t_ms` is the time at which the alert is emitted; its exact meaning is fixed by WS01-T05 and WS01-T07; this document requires only an integer. Golden cases list exactly these fields per alert.

### 4.2 The order

Define the key of an alert `a`:

```
K0(a) = (priority ascending, sigma_tilde ascending, t_ms ascending, instance_key ascending)
```

compared lexicographically: the first component decides unless it is equal, then the second, and so on. Numbers compare as numbers and instance keys as strings by code point (Python `str` comparison). `rank_alerts` returns the alerts sorted ascending by `K0`, with a stable sort. The first two components are the contract docstring ("template priority first, then `sigma_tilde` ascending within a priority"). The last two are added by this document as a deterministic tie-break, so that the output does not depend on the order in which the monitor hands the alerts over (which may depend on callback or thread order). It refines the docstring, it does not contradict it: two alerts that the docstring orders are ordered the same way by `K0`.

**Lemma 8 (properties of the order).** For alerts whose `sigma_norm` is not NaN and whose `priority` are integers:

1. *Permutation.* The output is a permutation of the input.
2. *Total preorder.* The relation `a <= b` iff `K0(a) <= K0(b)` is reflexive, transitive and total. It is antisymmetric on distinct keys; two alerts are equivalent only if their keys are equal.
3. *Priority.* If `priority(a) < priority(b)` then `a` precedes `b` (no alert is preceded by one of strictly lower urgency).
4. *Severity inside a priority.* If the priorities are equal and `sigma_norm(a) < sigma_norm(b)` then `a` precedes `b`.
5. *Determinism.* If all keys are distinct the output is independent of the input order; if several alerts have equal keys, those alerts keep their input order (stable sort).
6. *No arithmetic across classes.* `sigma_norm` values of different priorities are never compared.

*Proof.* (1) is a property of sorting. (2): the product of totally ordered sets with the lexicographic order is a total order (the first differing component decides; transitivity follows by considering the first component at which the three keys are not all equal), and comparing `K0` values induces a total preorder on alerts, with equivalent alerts being those with equal keys. (3) and (4) follow because the first (second) component of the key is compared first and decides. (5) follows from the totality on distinct keys and from stability. (6) holds because the second component is reached only if the priorities are equal. A randomized property test of the verification of this task (a script that is not committed; fixed seed; 3000 random alert sets with ties on every component; keys `K0` and `K1`) checked (1) to (5).

**Properties that WS05-T03 must implement (Hypothesis).** `tests/spec/test_rank_alerts.py`: (P-R1) permutation; (P-R2) for every pair of positions `i < j` in the output, `priority(out[i]) <= priority(out[j])`, so no alert is preceded by one with a strictly larger priority number; (P-R3) inside equal priority, `sigma_norm` is non-decreasing along the output; (P-R4) shuffling the input leaves the output unchanged when the keys are distinct; (P-R5) idempotence, `rank_alerts(rank_alerts(x)) == rank_alerts(x)`; (P-R6) equal keys keep input order. The golden cases RK-1 to RK-3 are the example-based tests.

### 4.3 Priority: direction and source

**Direction (CP5).** Priority 1 is the highest and the order is ascending: an alert of priority 1 precedes an alert of priority 2. The contract does not state the direction; the F0 table states "1 = highest", the registry rule of `03-parameter-registry.md` section 2.6 (priority `value >= 1`, an integral number) is consistent with it, and this document fixes it here for WS05-T03. Priorities are non-negative integers `>= 1`; the registry loader enforces this; `rank_alerts` rejects a non-integer priority or a priority below 1 (section 4.9).

**Source.** A priority is the registry entry `priority_<id>` of the template `tau` of the alert (`Alert.priority` is "the clinician-assigned template priority"). The only order given by the analisi is hold > range > sched (analisi §4.2), coded in the registry seed as 1, 2, 3 and labelled "illustrative, unverified"; `priority_count`, `priority_resp`, `priority_sys` and `priority_int` are unset. The order is the clinician's decision. This document says nothing about whether that order is clinically correct, and no result of this project may be described as if it were.

**Equal priorities.** Two templates may have equal priority (F0 gives COUNT and RESP both 2). Inside such a class the second component compares the `sigma_tilde` of alerts of different templates. This is permitted by the contract and is meaningful only to the extent that the clinician regards a given fraction of the scale of the one as comparable to the same fraction of the scale of the other. If the clinician does not, the remedy is a distinct priority for each template (recorded as an open point for the review).

### 4.4 Why lexicographic

After normalisation `-0.7` and `-0.6` are both numbers in `[-1, 1]`, but a timing violation of `-0.7` and a pressure violation of `-0.6` are not the same kind of event, and the specification cannot decide which is worse: that is the clinician's judgement, expressed as priority. Analisi §4.2 says the same: a timing -0.6 is not ordered against a pressure -0.6 as if they were equivalent. Example (golden RK-1): the hold alert `-0.3` (priority 1), the range alert `-0.6` (priority 2) and the sched alert `-0.7` (priority 3) are ranked hold, range, sched. The sched alert has the most negative `sigma_tilde` and is last only because its priority is the lowest; sorting by `sigma_tilde` alone would give the exact reverse. The check of the first components is all that is needed: `1 < 2 < 3`. Golden RK-2 shows the second component at work (`range@09:05` with `-0.6` before `range@12:24` with `-0.3`, and the same values with the times swapped give the reverse of the time order), and RK-3 shows the tie-break: equal priority and equal `sigma_tilde` are ordered by `t_ms` (50 before 100, although the key strings order the other way) and then by `instance_key` (`a` before `b`).

### 4.5 Decision: a PREDICTED_VIOLATION alert against a VIOLATED alert of the same priority

The literal contract key `K0` sorts by `sigma_tilde` regardless of the verdict, so a PREDICTED_VIOLATION alert with `-0.5` precedes a VIOLATED alert with `-0.2` of the same priority (golden RK-5, `literal_contract`). Recommended: a VIOLATED alert first. The extended key is

```
K1(a) = (priority ascending, verdict class ascending, sigma_tilde ascending, t_ms ascending, instance_key ascending)
verdict class: VIOLATED = 0, PREDICTED_VIOLATION = 1
```

Reasons: a VIOLATED verdict is definitive and computed from the measured prefix only, while a PREDICTED_VIOLATION is an early warning that is never definitive (`#verdict`, rule 3); a forecast of a large deviation should not displace a certified violation of the same priority in the list a nurse reads; and the confidence in a prediction (`rho`, kind PREDICTED) is a separate field that the order does not read, so severity of a forecast and certainty of a fact are not exchanged. Cost: a forecast of a severe deviation ranks after a certified mild one inside the same priority class; that is a clinical trade-off for the reviewer. `K1` extends the literal docstring of `rank_alerts`, and an extension of a frozen contract needs an ADR: WS01-T08 proposes it (open point OP-3). Until it is accepted, `rank_alerts` implements `K0`, and WS05-T03 tests `literal_contract` of RK-5; if it is accepted, `K1` replaces `K0` and `recommended_extension` becomes the expected order. Both orders are recorded in the golden file, and the file states that the ADR must confirm the recommended one. The lemmas of section 4.2 hold for `K1` with the verdict class inserted as the second component (properties (3) and (5) unchanged; (4) reads "same priority and same verdict class").

### 4.6 The `sigma_tilde` of a predicted alert

A predicted alert has no measured raw value. Its `sigma_tilde` is the normalised point forecast, `clip(sigma_hat, -1, 1)` with `sigma_hat` in normalised units (equal to `normalise(sigma_hat_raw, s)` if the forecaster works in the unit of the template), and not `sigma_hat + q` or any other bound that involves the conformal quantile. Golden RK-6 supports only the ban on dividing by the conformal width (section 6); excluding `sigma_hat + q` as the severity is a design proposal (OP-4) with its own reasons: the quantile depends on the calibration set, on `alpha` and on the forecaster version (section 6, further reason (1)), so a severity that contains it would change whenever the calibration changes, and it would mix severity with the uncertainty that `rho` carries. The quantile enters `rho` (confidence), not the severity. As `sigma_hat` may be `>= 0` (the "possible" variant of `#verdict` rule 2, or a negative quantile), the range of `Alert.sigma_norm` is: `[-1, 0)` for a VIOLATED alert (a violation has `sigma < 0` in exact arithmetic, `[-1, 0]` in floating point) and `[-1, 1]` for a PREDICTED_VIOLATION alert. Predicted alerts with `sigma_tilde >= 0` sort after all alerts of their class with negative values, which is the intended order (they are the least severe). This is CP5 (range of `sigma_norm`); the contract comment "in [-1, 0) for a violation" is to be clarified by WS01-T08 (OP-1). The severity of a predicted alert is a proposal to be confirmed by WS01-T06 and WS01-T07 (OP-4).

### 4.7 Is `sigma_tilde` frozen at emission?

Recommended: yes. The `sigma_norm` of an alert is the value of the record at emission and does not change afterwards; `rank_alerts` is a pure function of the alerts it receives; new information produces a new record, not a modified one. The reasons: an alert that a nurse has seen must not move in the list because a later measurement arrives, and the `sigma_norm` of the alert must be reproducible from the log.

Limitation, to be reported: for a timing violation, what is certified at emission is a bound, not the final lateness. A SCHED instance is decided VIOLATED at its deadline when no measurement has arrived; what the monitor can then certify is that the measurement is late by at least the time elapsed since the deadline, and `02-templates.md` section 2.3 gives the instance the value `-inf` at that step (guard `no_measurement_after_tick`), which normalises to `-1`. The measurement may arrive later and be, for example, 21 minutes late (`-1260000 / 1800000 = -0.7`, golden N-5): the lateness at resolution is not in the alert but goes to the log (the refined value of `02-templates.md` section 2.3), and, under the `-inf` choice of `02-templates.md` section 2.3, the frozen `sigma_norm` can be more severe than the final value. Consequence for the golden RK-1 and RK-4: the value `-0.7` of the sched alert is what a record emitted at 09:51 with the graded lateness would carry; an alert emitted at the deadline would carry `-1` with the guard marker, and the order of RK-1 and RK-4 is the same (the priority decides). Which record is emitted at which time, and whether a second refined record exists, is TG-4 of `02-templates.md`, decided by WS01-T05 and WS01-T07 (OP-9). An alternative that was considered and not adopted is to re-emit `sigma_norm = -elapsed / s` at every step: it makes the severity depend on the monitor step and on the reorder delay, and it contradicts the value `-inf` of `02-templates.md` section 2.3.

### 4.8 Scope of the order

`rank_alerts` is specified for the alerts of one care plan (one patient). The contract says `instance_key` is "unique within a care plan"; the `Alert` type carries no patient identifier, so for a list that mixes patients the last component of `K0` would not be a total tie-break, and the ordering would ignore patient-level acuity altogether. A ward-level view needs a patient identifier (a contract gap, OP-6); until then the ranking is applied per care plan.

### 4.9 Preconditions of `rank_alerts`

`sigma_norm` must not be NaN (a NaN breaks totality, Lemma 8 (2)), `priority` must be an integer `>= 1`, `t_ms` an integer, `instance_key` a string, and under `K1` the verdict must be VIOLATED or PREDICTED_VIOLATION. A violation raises `ValueError`; the empty sequence returns `[]`; the input is not modified and a new list is returned. The contract says nothing about errors of `rank_alerts` (OP-7).

## 5 Alternatives

Analisi §4.2 lists three alternatives to cite, and ADR-009 keeps them as alternatives, not as the adopted method. None is implemented here.

1. **AGM robustness** `[ref-needed: WS03]` (candidate entry `mehdipour-agm-robustness`, `verified = {false}`, flagged uncertain by WS03; analisi §3.1 marks it with a dagger).
2. **Weighted STL** `[ref-needed: WS03]` (candidate entry `mehdipour-weighted-stl`, `verified = {false}`, flagged uncertain; analisi gives no venue or year for it).
3. **Ordinal NEWS2-style bands** `[ref-needed: WS03]` (candidate entry `rcp-news2`, `verified = {false}`; analisi §3.3 names NEWS2 as the early warning score).

What each would need, as far as the analisi says: AGM robustness and weighted STL "still require normalised predicates" (analisi §4.2), so they do not remove the need for step 1 of this document: the scale per predicate stays. This document does not describe their definitions, because they are not cited from memory; the definitions are for WS03 to state from the verified reference. The ordinal-band alternative maps the deviation of a template onto ordinal bands (analisi §4.2). It would need clinician-defined band boundaries for each template instead of one scale, which is more clinical input and coarser output; `sigma_tilde` can be read as a continuous version with one boundary per template (`s`). Whether these alternatives change the need for a clinician-fixed priority order between classes is not stated in the analisi or in the related-work notes (which give only authors, year and "require normalised predicates"); to be checked against the papers in WS03-T06 `[ref-needed: WS03]`. The choice of the adopted method (clip normalisation with lexicographic priority) is ADR-009.

## 6 Why not the conformal width

**Prohibition.** Normalising severity by the width of a conformal interval (a z-score style division of the forecast by the half-width, or by the quantile) is forbidden (analisi §4.2, last paragraph; `#template`, rules; ADR-009). It would mix severity and uncertainty, which the paper keeps separate: `sigma_tilde` answers "how badly is the prescribed care violated", `rho` answers "how confidently can the violation be claimed" (`#alert`). The two are complementary (analisi §4.8): near the threshold `rho` falls, so they are correlated, and neither is a function of the other's scale.

**Counterexample (golden RK-6).** Two PREDICTED_VIOLATION alerts of the same priority, both with `sigma_hat = -0.5`: `resp@07:00`, conformal half-width `0.4`, emitted at 08:30, and `resp@12:00`, half-width `0.05`, emitted at 13:30 (fixture values, half-width in normalised units, illustrative; the contract calibrator exposes a one-sided quantile, and the argument does not depend on symmetry). The two have equal severity: the severity keys `(2, -0.5)` are equal, and the tie-break `t_ms` orders `resp@07:00` first. Divided by the half-width, the severities would be `-0.5 / 0.4 = -1.25` and `-0.5 / 0.05 = -10`; the order flips, `resp@12:00` first, only because its interval is narrower. Clipping the divided values to `[-1, 1]` gives `-1` for both, which erases the severity altogether; without the clip the value is unbounded as the width goes to zero and leaves the range of Lemma 1.

**Further reasons.** (1) The width depends on the calibration set, on `alpha` and on the forecaster version (`#conformal-calibrator`, rule 4: every model update triggers recalibration), so the same clinical deviation would change its severity, and its place in the ranking, whenever the model or the cohort changes; under distribution shift (ablation A6) the width changes with no change in the patient. (2) A precise forecast of a mild deviation would outrank an imprecise forecast of a severe one. (3) The scale must be a clinician's decision, not derived from data: `s` is a registry value and `normalise` has no argument through which a width could enter (the signature is `normalise(sigma_raw, scale)`, and `scale` is the value of `scale_<id>`). What is allowed: reporting the width next to the alert, and `rho`.

## 7 Ablation A3 and baseline B3

**Ablation A3 (analisi §5.6): removal of the normalisation of sigma.** The hypothesis is a worse agreement of the alert ordering. The **A3 null ranking** replaces the key of section 4.2 by the raw robustness in native units, with the units ignored:

```
KA3(a) = (raw sigma ascending, t_ms ascending, instance_key ascending)
```

with `sigma` the raw robustness of the alert's instance, `-inf` (a failed guard) sorting first. Priority is not read and no scale is applied. Ties use the same tie-break as section 4.2 (`t_ms`, then `instance_key`). Verdicts do not change (Lemma 2): the ablation changes the order only.

**Worked case (golden RK-4).** Alerts hold `sigma = -6` mmHg, range `-12` mmHg and sched `-1260000` ms; normalised with the F0 scales (20, 20, 1800000) they are `-0.3`, `-0.6` and `-0.7` with priorities 1, 2 and 3. The lexicographic order is hold, range, sched. The A3 null order is `-1260000 < -12 < -6`: sched, range, hold. The two orders are exact reverses of each other. The A3 order compares milliseconds with millimetres of mercury; in hours the sched value is `-0.35` and the A3 order becomes range, hold, sched (section 1.2).

**Variant A3-prio.** Keep the priority and remove only the normalisation inside a class: `(priority, raw sigma, t_ms, instance_key)`. It differs from the full order wherever normalisation changes the order inside a priority: where the scales differ (different units, or the same unit with different scales) and where values beyond the scale tie at `-1` after clipping and are then ordered by `t_ms` in the full order but by raw value in A3-prio. Example with F0 fixture values: COUNT (priority 2, `sigma = -1` dose, `sigma_tilde = -1.0`) and RANGE (priority 2, `sigma = -12` mmHg, `sigma_tilde = -0.6`): full order COUNT then RANGE; A3-prio order RANGE (`-12`) then COUNT (`-1`). Two further fixture-only lines (fixture arithmetic, checked by a script with the sort keys of section 4.2, not golden cases): (i) same template RANGE, same unit and priority 2, scale 20, both beyond the scale: `a` with `sigma = -40` at `t_ms = 100` and `b` with `sigma = -60` at `t_ms = 200` both normalise to `-1`, so the full order is `a`, `b` (tie broken by `t_ms`) and A3-prio gives `b`, `a` (`-60 < -40`); (ii) same unit and priority 2, different scales: `a` with `sigma = -10` and scale 10 (`sigma_tilde = -1.0`) and `b` with `sigma = -12` and scale 40 (`sigma_tilde = -0.3`): full order `a`, `b`; A3-prio gives `b`, `a`. On RK-4, where the three priorities differ, A3-prio equals the full order. WS08-T03 names the two variants `ours-A3` and `ours-A3-prio`.

**What A3 needs (contract gap).** The `Alert` type carries `sigma_norm` but not the raw value. A3 takes the raw value from the `VerdictRecord` of the same instance (`sigma_interval`, native unit), joined on `instance_key`; the case RK-4 lists it as an extra field. This is recorded in OP-8.

**Baseline B3** (analisi §5.4: same templates, verdicts on the measured values, raw robustness not normalised) has only the raw-robustness view: its detections are ordered by the raw value in native units, which is the ordering `KA3`. B3 has no priority, no `kappa`, no interval and no forecast, so it differs from ablation A3 in more than the ordering: A3 removes the normalisation from the proposed method and leaves everything else in place, and B3 is a separate detector. WS06-T04 owns B3 and the harness of WS06-T01 decides what it emits; this document states only that its severity view is the raw, unit-dependent one of section 1.2. The A3 agreement measured against the registry-lexicographic order is a consistency measure and not an independent validation (the order it is compared with comes from the same registry); the independent comparison is the clinician ranking of section 8, if the optional study is run.

## 8 Optional agreement with clinician ranking

Analisi §5.5 (last bullet) lists as optional the agreement between the ordering by normalised severity and an ordering given by clinicians. The metric is `severity_rank_agreement(auto, clinician)` of `#metrics`, a Kendall tau or a Spearman coefficient in `[-1, 1]`: for `n` alerts of the vignette study of WS11, `auto` holds the position of each alert in the lexicographic order of section 4 (1 for the first) and `clinician` the position given by the clinician to the same alert; a coefficient of 1 is the same order and -1 the reverse. Ties in the clinician's order (a clinician who declares two alerts equally urgent) call for the tau-b variant, which corrects for ties; the choice between Kendall and Spearman and the treatment of ties belong to the metric task of WS08. The same measure is computed for the A3 order of section 7, so the study shows whether the normalised lexicographic order is closer to the clinician than the raw one. Because the priorities are themselves the clinician's, agreement on pairs from different priority classes tests the registry order, and agreement on pairs inside a class tests the scales; the two groups can be reported separately. This document does not choose clinician data or vignettes; the study, if run, is WS11's and the clinician's.

## 9 Paper excerpt (Section IV-B, severity)

Sized to 0.15 page (analisi §7, Section IV-B is 0.3 page in total; the definitions of rho come from WS01-T06). Citations are markers until WS03-T06 and WS00-T08 verify the references.

```latex
\subsection{Severity}
\label{sec:severity}

The raw robustness $\sigma_\pi$ of a template $\pi$ carries the unit of its margin (mmHg, ms or doses), so a $\min$ over templates has no meaning.
We normalise per template, $\tilde\sigma_\pi=\mathrm{clip}(\sigma_\pi/s_\pi,-1,1)$, where the scale $s_\pi$ is the clinically significant deviation, a registry entry fixed with the clinician (Table~\ref{tab:templates}).
The map preserves the sign, so verdicts are unchanged; it is monotone and invariant to a common change of the unit of $\sigma_\pi$ and $s_\pi$, and a failed guard maps to $-1$.
Alerts are ordered lexicographically: first by the clinician-assigned priority of the template (1 is the highest), then by $\tilde\sigma$ ascending, then by time and instance key.
A timing violation with $\tilde\sigma=-0.7$ is therefore not ranked against a pressure violation of a different priority with $-0.6$ as if they were equivalent.
We never normalise by the width of a conformal interval, which would mix severity with uncertainty; confidence is carried separately by $\rho$.
AGM robustness, weighted STL and ordinal NEWS2-style bands [ref-needed: WS03] are alternatives; the first two still require normalised predicates.
Scales and priorities are illustrative and unverified until reviewed by the clinician.
```

## 10 Open points for WS01-T08

Each item gives the anchor, the resolution adopted or proposed, and whether an ADR is needed. None edits `02-interfaces.md`.

**OP-1 CP5, range of `sigma_norm` (`#alert`).** The contract comment says "in [-1, 0) for a violation", but a PREDICTED_VIOLATION alert can carry `sigma_hat >= 0` (the "possible" variant, or a negative quantile). Resolution adopted (section 4.6): `[-1, 0)` for a VIOLATED alert (`[-1, 0]` in floating point), `[-1, 1]` for a PREDICTED_VIOLATION alert. ADR: a clarification of the comment; no signature change.

**OP-2 CP5, direction of `priority` (`#alert`, `#template`).** The contract does not state it. Resolution adopted (section 4.3): 1 is the highest, ascending order, integers `>= 1`, consistent with the F0 table and `03-parameter-registry.md`. ADR: a clarification of the comment.

**OP-3 CP5, PREDICTED_VIOLATION against VIOLATED (`#template`, `rank_alerts`).** Recommended (section 4.5): `K1`, VIOLATED first within a priority. It extends the docstring of a frozen contract, so it needs an ADR, proposed by WS01-T08, after the clinician's view on the trade-off. Until accepted, `K0` is implemented; golden RK-5 records both orders.

**OP-4 `sigma_norm` of a predicted alert (section 4.6).** Proposed: normalised point forecast, `clip(sigma_hat, -1, 1)`, never a bound that involves the quantile. To be confirmed by WS01-T06 (definition of rho and of the "likely" and "possible" variants) and WS01-T07 (alert tuple). ADR: with OP-3, if WS01-T06 defines it differently.

**OP-5 Infinities and failed guards (TG-10 of `02-templates.md`).** Confirmed (section 2.4): `normalise(+-inf, s) = +-1`; `sigma_tilde = -1` has two origins (a clipped finite value and a failed guard) told apart by the marker `guard_failed`, which WS01-T07 must put in the alert record. `rank_alerts` does not read the marker: a failed-guard alert and a clipped alert of the same priority tie at `-1` and are ordered by `t_ms` and `instance_key`.

**OP-6 Tie-break and typing (`rank_alerts`, ADR-024 (proposed), WS05-T03).** The tie-break `(t_ms, instance_key)` of section 4.2 refines the docstring and makes the output independent of input order. Three consequences for WS05-T03: (a) the structural type of `rank_alerts` in ADR-024 (a Protocol with `priority` and `sigma_norm` only) must also expose `t_ms` and `xi.instance_key` (and `verdict` if `K1` is accepted); (b) the test "stable on ties" of WS05-T03 (equal `(priority, sigma_norm)` keep the input order) holds only when `t_ms` and `instance_key` are also equal, and should be restricted to that case; (c) the WS05-T03 test 9 (`test_rank_alerts_accepts_any_object_with_priority_and_sigma_norm`: a local dataclass with only those two fields is accepted) conflicts with `K0`, which also needs `t_ms` and `xi.instance_key` (and `verdict` under `K1`), and must be rewritten with the fields of section 4.1. Contract gap: `instance_key` is unique within a care plan and `Alert` has no patient identifier, so `rank_alerts` is specified per care plan (section 4.8); a ward-wide list needs a patient identifier. ADR: yes for the type (with ADR-024) and for the patient identifier if a ward-wide ranking is wanted.

**OP-7 Errors (`normalise`, `rank_alerts`).** The contract names no error type. Adopted (sections 2.4 and 4.9): `ValueError` for `scale <= 0`, non-finite scale, NaN `sigma_raw`, NaN `sigma_norm`, invalid priority; an unset scale is `UnsetParameterError` from the registry (a name proposed by WS01-T03, itself not in the contract API list). ADR: a sentence in the contract text at the discretion of WS01-T08.

**OP-8 Raw robustness for A3 (`#alert`, `#verdict`, WS08-T03).** `Alert` carries no raw `sigma`; A3 joins the alert to its `VerdictRecord` on `instance_key` (section 7). A failed guard has raw `-inf`. Two variants are defined, `ours-A3` (raw, no priority) and `ours-A3-prio` (priority kept). The null ranking removes the priority together with the normalisation, so the ablation as defined in analisi §5.6 changes two things at once; `ours-A3-prio` isolates the normalisation. ADR: none, a note for WS08-T03.

**OP-9 Frozen `sigma_tilde` and the graded lateness of SCHED (TG-4 of `02-templates.md`).** Recommended (section 4.7): frozen at emission, the lateness at resolution goes to the log. The value carried by a SCHED alert at emission (`-1` with a guard marker, or a graded value) depends on the record emitted at the deadline, which WS01-T05 and WS01-T07 decide. The order of RK-1 and RK-4 does not depend on it.

**OP-10 State of the registry (WS00-T07, ADR-020).** With registry 0.1.0, four scales (`scale_hold`, `scale_resp`, `scale_sys`, `scale_int`) and four priorities (`priority_count`, `priority_resp`, `priority_sys`, `priority_int`) are unset, so HOLD cannot be normalised, COUNT can be normalised but not ranked, and RESP, SYS and INT can be neither. No scale or priority in the seed is reviewed, and the priority order is the clinician's. The F0 fixture values must not be copied into the registry. Question for the clinician review: whether templates in one priority class have comparable scales, or should have distinct priorities (section 4.3), and whether the priority of an INT or SYS alert should sit above the care-plan classes (the order uses the template, not the attributed cause `kappa`).

**OP-11 Loss of order by the clip (Lemma 3).** Two violations beyond the scale tie at `-1`. Reported as a limitation of the severity evaluation; if the clinician wants grading beyond `s`, the fix is a larger scale, not a change of the function.

**OP-12 References.** AGM robustness, weighted STL, NEWS2-style bands and time robustness are markers `[ref-needed: WS03]` with the candidate keys `mehdipour-agm-robustness`, `mehdipour-weighted-stl`, `rcp-news2`, `rodionova-time-robustness` and `donze-maler-robust`, all unverified (ADR-018). The paper excerpt cannot cite them until a human verifies them.

**OP-13 Floating point (section 2.3).** The Hypothesis tests of WS05-T03 must restrict the sign property (underflow) use exact arithmetic or a tolerance for equivariance, draw `k` so that `k * s` is finite and positive (P-N4, section 2.3 (e)), and not assert strict monotonicity or the Lipschitz bound on doubles (section 2.3 (c), (d)); otherwise they will fail on correct code.

**OP-14 Severity of a VIOLATED alert: the "upper end" rule (WS01-T07, WS01-T08, WS05).** WS01-T07 (line 40: "for a VIOLATED alert `sigma_norm` is the upper end of the normalised interval at emission (certified severity, T04)"), WS01-T08 R3 ("SCHED@09:00 VIOLATED, decided 09:30, [-inf, -60000 ms], normalised upper end -0.0333"), WS05 README D7 and WS05-T07 test 3 all attribute to this document an "upper end of the normalised interval" rule for the severity of a VIOLATED alert. This document (section 4.7, OP-9) offers only "`-1` with a guard marker, or a graded value" and never states the upper-end rule. Under the upper-end rule a VIOLATED SCHED alert would carry `-0.0333`, not `-1`; and the remark of section 4.7 that the frozen value "can be more severe than the final value" holds only under the `-inf` choice. Open reconciliation point before M1, to be decided by WS01-T05, WS01-T07 and WS01-T08; not decided here. The golden orders are unaffected, because the priority decides (RK-1, RK-4).

**OP-15 Severity of a predicted alert: `predicted_sigma_norm` (WS05-T04 step 8, WS05-T08 tests 5 and 15, WS05 README D7).** These define `predicted_sigma_norm` as the conformal upper bound `sigma_hat + q` of a PREDICTED_VIOLATION, clipped to `[-1, 1]` (WS05-T08 test 5 expects `-0.3333`), whereas section 4.6 and OP-4 propose the normalised point forecast and exclude any bound that involves `q`. The conflict is recorded, not decided here; WS05-T07 says that the rule of WS01-T07 wins. Deferred to WS01-T06 and WS01-T07.

**OP-16 Test-name conflicts in WS05-T03.** Test 7 ("equal `(priority, sigma_norm)` keep input order") conflicts with the tie-break `(t_ms, instance_key)` of `K0` (OP-6 (b)), and test 9 (a local dataclass with only `priority` and `sigma_norm` is accepted) conflicts with the fields `K0` reads (OP-6 (c)). Both are named so that WS05-T03 corrects them; no other task file is edited here.

**Touch points with WS01-T02 (respected, not overridden).** CP11 and the margin and guard rule (section 3.1 uses the one margin dimension per template); TG-4 (OP-9); TG-10 (OP-5, confirmed); TG-11 (a tie `sigma = 0` is satisfied; `normalise(0, s) = 0`, golden N-4); TG-13 (RANGE during onset is a clinical question and does not change here); TG-14 (the fixture values in the golden file are fixture choices, no clinical statements).
