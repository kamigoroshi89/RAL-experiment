# 02 Past-time STL template library

Document WS01-T02. Feeds paper Section IV-A and Table I. Draft for the M1 freeze (WS01-T08); it changes no contract of `docs/plan/02-interfaces.md` (gaps and clarifications are recorded in section 9). It builds on `docs/formal/01-signals-sampling.md` (WS01-T01: signals, grid, ceiling rule, anchoring convention, derived signals, decomposition), whose modelling choices M1 to M6 and gaps CG-1 to CG-14 are respected and not overridden. Validation in this project is technical and pre-clinical; nothing in this document is a clinical claim. Every clinical number is either fixture arithmetic (FIXTURE-ONLY, fixture registry F0 of `docs/plan/workstreams/WS01-formalization/README.md`) or a value taken from analisi §4.1, §4.2, §4.6 or §4.7 and labelled "illustrative, unverified" (ADR-020). The specification is evaluated on the observed trace only: nothing in it reads `LatentDay` or `GroundTruthEvent`.

Scope source: hypertension is the running example (ADR-001), C3 means integrity violation (ADR-002), the architecture is a ward node plus a robot (ADR-003). The output artefact of WS00-T02 was not present in the repository when this document was written; ADR-001 to ADR-003 are the scope source and nothing here depends on the missing artefact.

What this document answers (review items): R1 weakness 1 (no formulas: sections 3 and 4), weakness 3 (Boolean predicates: section 2), weakness 5 (expressiveness: section 6) and weakness 8 (phi_HW and phi_DOSE only in a caption: sections 3.1 and 6.6).

## 1 Syntax and semantics

### 1.1 Conventions

1. Time, grid, ceiling rule, alignment of window parameters, the trailing 24 h window, the derived signals and the anchoring convention are those of `docs/formal/01-signals-sampling.md` (called "T01" below). Time is integer milliseconds (ADR-017); the monitor grid is `t_k = k * T_s`, `k = 0, ..., K`; an event with device time `t` is visible at step `k_up(t) = ceil(t / T_s)`; window parameters are integer multiples of `T_s` (T01 section 3.6).
2. Raw robustness is written sigma (native unit of the template), normalised robustness sigma-tilde (`clip(sigma / s, -1, 1)`, contract `normalise`). The word "robustness" is used only for STL semantics.
3. The workshop operator "always" (`\square`) is, in an online monitor, the past-time operator `historically` over the trace prefix. The workshop "once" `O[a,b]` is `once[a,b]`.
4. "Illustrative, unverified" marks a number of analisi §4.1, §4.2, §4.6 or §4.7. "FIXTURE-ONLY" marks a number chosen for hand arithmetic. Neither has a clinical meaning.
5. References are not cited from memory. Where a reference would be needed the marker `[ref-needed: WS03]` is written and the analisi section that mentions the work is named.

### 1.2 Grammar of the past-time string

The string `formula_past_time` of a template is a sentence of the following EBNF (ISO 14977 style; terminals are quoted, `{ x }` is repetition, `[ x ]` is option, `( a | b )` is alternation).

```ebnf
formula      = implication ;
implication  = disjunction , [ "->" , implication ] ;
disjunction  = conjunction , { "or" , conjunction } ;
conjunction  = since_expr , { "and" , since_expr } ;
since_expr   = unary , [ "since" , [ interval ] , unary ] ;
unary        = "not" , unary
             | "historically" , [ interval ] , unary
             | "once" , interval , unary
             | "(" , formula , ")"
             | atom ;
interval     = "[" , bound , "," , bound , "]" ;
bound        = "inf" | expr ;
atom         = expr , cmp , expr        (* comparison atom *)
             | signal_id ;              (* indicator atom: a Boolean signal *)
cmp          = ">=" | "<=" | "==" ;
expr         = term , { ( "+" | "-" ) , term } ;
term         = number | registry_name | signal_id | "age" ;
number       = digit , { digit } ;      (* digit = "0" | ... | "9" *)
signal_id    = "bp" | "meas" | "dispense" | "intake" | "sched_tick" | "dose_count"
             | "meas_count" | "bp_pre" | "bp_drop" | "cuff_health" | "inflation_ms"
             | "presence" | "auth" | "day_end" | "hr_ecg" | "hr_pulse" | "spo2" ;
registry_name = letter , { letter | digit | "_" } ;   (* letter = "a" | ... | "z" ; a registry working name, section 3.4, or step_ms *)
```

Reading rules.

1. Precedence, loosest to tightest: `->` (right associative), `or`, `and`, `since`, then the prefix operators `not`, `historically`, `once`. Parentheses group.
2. `historically` without an interval means `historically[0, inf]`; `since` without an interval means `since[0, inf]`. `once` always carries an interval (an unbounded look-back is written `once[0, inf]`).
3. Interval bounds are non-negative integer multiples of `T_s` after substituting the registry values (T01 section 3.6); `inf` is allowed as the upper bound. `step_ms` denotes `T_s` and is a monitor-configuration constant, not a clinical registry entry.
4. Only non-strict comparisons occur (`>=`, `<=`) and equality on a status signal (`==`). No template uses `>` or `<`; the treatment of ties on strict predicates is WS01-T05 (CP3).
5. `age` is the only name that is not a `SignalId` or a registry name. It is the reserved instance term of section 1.4 (time elapsed between an event and the decision step). It is used by the two time-margin templates, SCHED and INT. It is not defined in `docs/formal/01-signals-sampling.md`, which is why WS01-T08 check (c) must be told about it (section 9, TG-5).
6. Every atom is exactly one of three kinds (section 2.1): an indicator atom (a Boolean signal), an equality atom, or a margin atom (`>=` or `<=`). A bare `signal_id` that is not followed by a comparison is an indicator atom; the parser tries `expr cmp expr` first.
7. `since` is part of the language (sequence constraints, section 6.3) but none of the seven templates uses it.

**"RTAMT-compatible".** The operator names follow the vocabulary of common past-time STL tools (`historically`, `once`, `since`, implication). In this document "RTAMT-compatible" means only that a mechanical, syntax-directed translation of this grammar into the input syntax of such a tool exists for the fragment without `age`, and that `age` can be supplied as a derived per-instance signal or, for the Boolean verdict only, replaced by the Boolean skeleton of section 1.4 (equivalent for SCHED and INT, with the INT skeleton given explicitly there). That translation is not checked here: it is the subject of the spike of WS05-T02 (ADR-013, `[DA-CONFERMARE]`). This document assumes no API detail of any tool.

### 1.3 Quantitative semantics

Let `x_k` be the grid value of signal `x` at step `k` (T01 section 3). Robustness `sigma(phi, k)` takes values in the extended reals `R` together with `-inf` and `+inf`. Negation is `-(+inf) = -inf` and `-(-inf) = +inf`. No operation below subtracts two infinities: only `min`, `max` and negation are applied to infinite values.

**Window.** For an interval `[a, b]` with `a, b` integer multiples of `T_s`, at step `k`:
`W(k, [a, b]) = { j : k - b/T_s <= j <= k - a/T_s, j >= 0 }`, with `b = inf` meaning no lower limit other than `j >= 0`. The window is truncated at the trace start (`j >= 0`). Windows are closed at both ends on the grid.

**Atoms** (section 2.1 gives the reason for the split).

| Atom | Value of `sigma(atom, k)` |
|---|---|
| indicator `u` (impulse, status level read as Boolean) | `+inf` if `u_k = 1`, `-inf` if `u_k = 0` |
| equality `x == c` on a status signal | `+inf` if `x_k = c`, `-inf` otherwise |
| margin `e1 >= e2` | `e1_k - e2_k` |
| margin `e1 <= e2` | `e2_k - e1_k` |

where an expression is evaluated at step `k` (sums and differences of numbers, registry values and signal values; `age` as in section 1.4).

**Operators.**

| Formula | `sigma(., k)` |
|---|---|
| `not f` | `-sigma(f, k)` |
| `f and g` | `min(sigma(f, k), sigma(g, k))` |
| `f or g` | `max(sigma(f, k), sigma(g, k))` |
| `f -> g` | `max(-sigma(f, k), sigma(g, k))` |
| `once[a,b] f` | `max` over `j` in `W(k, [a, b])` of `sigma(f, j)`; `-inf` if the window is empty |
| `historically[a,b] f` | `min` over `j` in `W(k, [a, b])` of `sigma(f, j)`; `+inf` if the window is empty |
| `f since[a,b] g` | `max` over `j` in `W(k, [a, b])` of `min( sigma(g, j), min over i in (j, k] of sigma(f, i) )`; the inner `min` over an empty range is `+inf`; `-inf` if the window is empty |

An empty `once` window is `-inf` (minus infinity) and an empty `historically` window is `+inf` (plus infinity): at the trace start, and before an offset has elapsed, `once` has no witness and `historically` has no counter-example.

**Boolean value.** A formula is satisfied at step `k` iff `sigma(phi, k) >= 0`. This is the Boolean semantics of the atoms above (all non-strict; a tie `sigma = 0` is satisfied). The sign of `sigma` therefore always agrees with the Boolean verdict of the grid semantics.

**Unknown values.** An atom over `NaN` (undefined before the first sample) or over an unavailable channel (T01 section 3.5) has no point value. The point semantics above is defined where all evaluated atoms are known; the interval semantics with physiological bounds is WS01-T05 (CP12). The golden cases of section 7 are constructed so that no unknown atom changes the result: each was also evaluated with unknown atoms read as the interval `[-inf, +inf]`, and the lower and upper bound coincide.

**Vacuous truth.** With no anchor the implication of every template is `+inf` at every step, so `sigma(phi, k) = +inf` (no instance to decide). The verdict layer treats an instance that is not yet decided as PENDING (WS01-T05).

### 1.4 The instance term `age` and the Boolean skeleton

`age` is defined by this rule: an atom that mentions `age`, evaluated at step `j` inside the innermost enclosing `once`, `historically` or `since` that is evaluated at step `k`, reads `age = (k - j) * T_s` (a duration in ms, `>= 0`). Outside any temporal operator `age = 0`. In the strings of SCHED and INT the enclosing operator is the `once` that holds the consequent, evaluated at the decision step, so `age` is "how long before the decision step the witnessing event is".

`age` is not a signal: it is a function of two grid positions, like the freeze variable of STL with freeze (cited as an alternative in section 6.1, `[ref-needed: WS03]`), restricted to the one use that the two time-margin templates need. It does not appear in the `signals` field of a template.

**Boolean skeleton.** The Boolean skeleton of a template is a string without `age`, for tools that cannot supply a per-instance derived signal. It carries the Boolean verdict only; the margin needs the instance. It is not obtained by the mechanical rule "replace every `age` atom by `true`", which is unsound in general (below). Per template:

* RANGE, HOLD, COUNT, RESP, SYS: the string has no `age`; the skeleton is the string.
* SCHED: replacing the atom `age >= 0` by `true` (that is, `once[0, sched_window] (meas and age >= 0)` becomes `once[0, sched_window] meas`) preserves the verdict. Inside `once[0, sched_window]` the value of `age` is `(k - j) * T_s >= 0` at every step of the window, so the atom `age >= 0` is satisfied at every step (a tie, `age = 0`, is satisfied). Skeleton: `historically(once[sched_window, sched_window + step_ms] sched_tick -> once[0, sched_window] meas)`.
* INT: the same replacement is **not** sound. The enclosing operator is `once[0, inf]`, so the window decides nothing and the atom `age <= int_window` is what excludes a witness that is too old. With the atom replaced by `true`, the skeleton `historically(dispense -> once[0, inf] (presence or intake or auth))` is satisfied by a witness of any age. The INT skeleton must keep the bounded window, as in the workshop form:
  `historically(dispense -> once[0, int_window] (presence or intake or auth))`.
  Here the window carries the sign that `age` carries in the string: a candidate step `j` lies in `once[0, int_window]` iff `age_j <= int_window`.

Check (a script, not committed, run for this correction): on G-INT-2 (presence at 06:52, dispense at 07:00) the string gives `-180000` (violated) while the rule-based skeleton `once[0, inf]` gives `+inf` (satisfied), a wrong verdict; the bounded skeleton gives `-inf` (violated). On G-INT-1 and G-INT-3 the bounded skeleton and the string are both satisfied, on G-SCHED-1 to G-SCHED-4 the SCHED skeleton and the string agree in sign. On 2000 random traces the sign of the string and of the bounded INT skeleton agree in all 2000 (0 mismatches), while the `once[0, inf]` skeleton disagrees in 650. For SCHED (2000 random traces, one to three ticks) the skeleton and the string agree in all 2000. The claim is therefore limited to SCHED and INT with the skeletons stated here: a tool may check the verdict on the skeleton for those two, and for the five templates without `age` on the string itself; no general skeleton rule is claimed for a future template that uses `age`, which needs its own check.

### 1.5 Instance semantics (reference semantics) and its relation to the string

The reference semantics is per template instance (T01 section 3.7). It is stated here for the template library.

**Definitions.** An instance `i` of a template is opened by an anchor: a device event (a measurement or a dispense), a schedule tick, or the end-of-day marker. Let `a_i` be the anchor device time and `k_a = k_up(a_i)` its visible step (`k_a = K` for the end-of-day marker). Each template has a deadline offset `B` (section 3.2): `B = 0` for RANGE, HOLD, COUNT, SYS, INT; `B = sched_window` for SCHED; `B = delta2` for RESP. The decision step is `k_d = k_a + B / T_s`, the decision time `t_d = t_{k_a} + B`. The body `C_T` of the template is the consequent of the implication in its string (for COUNT the consequent of the respective conjunct).

1. The instance robustness is `sigma_i = sigma(C_T, k_d)`, evaluated once at `k_d` with the per-instance terms of the instance: `age` relative to `k_d`, and for RESP the pre-dose value `pre_i` captured at the anchor (T01 section 5.3).
2. The Boolean verdict of the instance is decided at `k_d` by the sign of `sigma_i`. It is never retracted (T01 section 3.7).
3. Two anchors in the same step are two instances (T01 section 3.4). An instance belongs to the day of its anchor (M6).
4. SCHED only: after `k_d` the value of an instance with no observation up to `k_d` can be graded by a late observation (section 2.3); the sign cannot change.

**The whole-formula string.** With `phi_T = historically(A -> C)` and `A` a guard, `sigma(phi_T, k) = min over j <= k with A true at j of sigma(C, j)`, and `+inf` if there is none: at a step where the antecedent is false the implication is `+inf` and does not affect the minimum.

* **Templates with `B = 0`** (RANGE, HOLD, COUNT, SYS, INT). The antecedent is the impulse of the anchor itself, true exactly at `k_a = k_d`. Hence `sigma(phi_T, k) = min { sigma_i : k_d(i) <= k }` for every `k`, under section 3.6 of T01 and one instance per anchor, and under one further assumption for the two templates whose instance value reads the payload of the anchoring measurement: **(A0)** at most one measurement event per bin `(t_{k-1}, t_k]`. RANGE reads `bp`, SYS reads `cuff_health` and `inflation_ms`; the grid keeps only the last sample in a bin (T01 section 3.4: several events in one step give one impulse and the anchors are taken from the event stream, but the held value is one). With two measurements in one bin the string sees one step and the last value, while the reference semantics has two instances with their own values. Example (RANGE, `bp_band_low` 110, `bp_band_high` 140): `bp` 150 at 09:00:10 and `bp` 120 at 09:00:40 fall in the bin of step 541; the string body has value `+10` (held `bp` 120), the instances have `-10` and `+10`, so the string reports a satisfied constraint where the reference semantics reports a violation. A random check (1500 traces with 1 to 5 measurements) gives 0 mismatches between the string value and the minimum of the instance values with one measurement per bin, and 14 mismatches with up to two per bin (RANGE); the same for SYS: 0 and 6. HOLD, COUNT and INT read only grid values and counts at the decision step (the counter keeps multiplicity, T01 section 3.4), so two anchors in one bin give two instances with the same value and the equality holds without (A0) (HOLD checked with up to two dispenses per bin: 0 mismatches). Under (A0) the string and the reference semantics coincide, and the outer `historically` is the universal quantification over instances. Where (A0) cannot be guaranteed the reference semantics (per event) is the one to implement, and the string is a tool form.
* **Templates with `B > 0`** (SCHED, RESP). The antecedent is `once[B, B + T_s] x`, which is true at two consecutive steps per anchor, `k_d` and `k_d + 1` (the widening of ADR-007, T01 section 3.7). Write `E` for the first step of the consequent window (`E = k_a` for SCHED, `E = k_a + delta1 / T_s` for RESP), `sigma_i` for the value of the body at `k_d` and `sigma_i^+` for the value of the body at the shadow step `k_d + 1` (window shifted right by one step; `age` measured from `k_d + 1`). Then for every `k`:

  `sigma(phi_T, k) = min( { sigma_i : k_d(i) <= k } union { sigma_i^+ : k_d(i) + 1 <= k } )`.

  Two consequences. (a) At the decision step itself (`k = k_d`) the string equals the reference semantics: only the first true step has been seen. (b) Under (A3) below, from `k_d + 1` on the string is never weaker than the reference semantics: `sigma(phi_T, k) <= min sigma_i`. The relation above and the coincidence of the two, for the whole formula and for every `k`, hold under the assumptions
  **(A1)** window parameters are multiples of `T_s` (T01 section 3.6) and anchors are read as impulses at `k_up(a)` (grid alignment), one instance per anchor;
  **(A2)** for every instance the maximum that defines `sigma_i` is not attained only at the step `E` (or `sigma_i = -inf`);
  **(A3)** (RESP only) no other dispense is visible in the steps `k_a, ..., k_d + 1` of an instance, that is no other dispense in `(a_i, a_i + delta2 + T_s]` up to the ceiling rule; equivalently, the string is evaluated with the per-instance `bp_drop = pre_i - bp` instead of the global stream. The string of RESP uses the global derived stream `bp_drop = bp_pre - bp`, in which `bp_pre` is the pre-dose value of the latest dispense; the reference semantics uses `pre_i` of the instance (section 4.5). With an overlapping dose the global stream carries the pre-dose value of the later dose inside the window of the earlier one.
  Without (A2) the value differs, and the Boolean verdict differs exactly when the instance is satisfied, its only qualifying observation (non-negative margin at `k_d`) lies at `E`, and there is no qualifying observation at `k_d + 1` (the shadow window `[E + 1, k_d + 1]` then holds none, and the string reports a violation at `k_d + 1` that the instance semantics does not). For SCHED every measurement in the window qualifies, so this reads: the only measurement in `[E, k_d]` is at `E`, and there is none at `k_d + 1`. Example: tick at step 6, `W = 5` steps (`k_d = 11`), measurements at steps 6 and 12: the string values at 11 and 12 are `+300000` and `0`, the verdicts do not differ, because the measurement at step 12 lies in the shadow window. Without (A3) the relation of this paragraph fails, in either direction.
  Checks (scripts, not committed, run for this correction, `T_s = 60000` ms, windows of a few steps, random traces, evaluator of the grammar of section 1.2 against the per-instance definitions): for SCHED with a single anchor, the Boolean verdicts of string and instance differ in 703 of 6000 traces; the earlier predicate ("the only observation with a non-negative margin lies at `E`") mispredicts 415 of them, the refined predicate 0. For RESP with a single anchor, 317 of 6000 differ, and the refined predicate (with "qualifying" meaning margin `>= 0` at the step considered) has 0 mispredictions, the earlier one 89. For RESP with one to three dispenses (3751 traces): with (A3) the value relation `sigma(phi_T, K) = min(sigma_i, sigma_i^+)` held in 1824 of 1824 traces; without (A3) it failed in 102 of 1927; the string value was above `min sigma_i` (weaker than the reference) in 21 of these; and when (A2) holds the Boolean verdicts of string and instance agreed in 1559 of 1559 traces with (A3) and disagreed in 19 of 1442 without it.

**Worked check (SCHED, tick 09:00, `sched_window` 30 min, F0).** With a measurement only at 09:00 (`E = 540`): instance value `+1800000` ms at `k_d = 570`; string `+1800000` at 570 and `-inf` at 571 (violated: A2 fails, the Boolean verdict differs). With measurements at 09:00 and 09:20: instance value `+1800000`; string `+1800000` at 570 and `+660000` at 571 (`(571 - 560) * 60000`; same Boolean verdict, smaller value). RESP behaves the same at `E = k_a + delta1/T_s`: a sole qualifying measurement at 08:00 after a 07:00 dispense gives `+10` mmHg at 600 and `-inf` at 601. These values were computed by an independent evaluator of the grammar of section 1.2 (not committed; outputs in the completion note and in the "Fix round 1" note of the task file).

**Consequence for implementers.** The string is the form for tools; the reference semantics is the per-instance one. WS05 must not implement the SCHED and RESP strings without anchoring (T01 CG-2, section 9). WS01-T05 proves the equivalence of verdicts between the past-time and the future-time forms of SCHED and RESP under (A1) and (A2) (and (A3) for RESP) and states what happens without them (ADR-007, ablation A7); the future-time forms are given in section 4.

### 1.6 What section 1 hands over

To WS01-T04: sigma is in the unit of the template, `sigma >= 0` is satisfied, `sigma_tilde = clip(sigma / s, -1, 1)` with `clip(+-inf) = +-1` (section 2.5). To WS01-T05: point semantics, ties, `+-inf`, the instance decision step, the shadow step, the `age` term. To WS05: the grammar, the per-instance capture, the Boolean skeletons of SCHED and INT (section 1.4).

## 2 Margin and guard rule

### 2.1 The rule (CP11, R1 weakness 3)

Contract `Template` has one `unit` and one `scale_param` per template, but HOLD, RESP and SYS combine atoms of different kinds (a pressure and the existence of a measurement; a health flag and a duration). Rule:

1. **One margin dimension.** Each template has exactly one margin dimension, its `unit` (`mmHg`, `ms`, `dose`). Several margin atoms may occur if they are all in that unit (RANGE has a lower and an upper limit, COUNT a limit and a day-end minimum).
2. **Everything else is a guard.** Every other atom is a guard: an indicator atom or an equality atom. A guard is `+inf` when it is true and `-inf` when it is false (section 1.3).
3. **Failed guard.** A failed guard gives raw `sigma = -inf` for the instance (the guard sits inside a `min`), normalised value `-1`, and the alert or verdict record carries the marker `guard_failed: <name>` (names in section 2.2). If more than one guard could fail, the first in the order of the string is reported; no template has more than one guard that can fail besides its trigger.
4. **Trigger guards** (the anchor impulse of an instance: `meas`, `dispense`, `sched_tick`, `day_end`) are true by construction inside an instance; they only select the steps where the implication is not vacuous.

This resolves CP11 without changing the `Template` dataclass: `unit` is read as "the unit of the margin dimension", and `scale_param` is the scale of that dimension (section 9).

| Template | Margin atoms (dimension) | Guard atoms | Marker on failure |
|---|---|---|---|
| RANGE | `bp >= bp_band_low`, `bp <= bp_band_high` (mmHg) | trigger `meas` | none (a `meas` instance always has a measurement) |
| SCHED | `age >= 0`, deadline slack (ms) | trigger `sched_tick`; `meas` in the window | `no_measurement_after_tick` |
| HOLD | `bp >= bp_hold_threshold` (mmHg) | trigger `dispense`; `once[0, hold_lookback] meas` | `no_recent_measurement` |
| COUNT | `dose_count <= dose_max_24h`, `dose_count >= dose_min_day_end` (dose) | triggers `dispense`, `day_end` | none |
| RESP | `bp_drop >= delta_resp` (mmHg) | trigger `dispense`; `meas` in the response window | `obligation_unmet` |
| SYS | `inflation_ms >= cuff_inflation_min` (ms) | trigger `meas`; `cuff_health == 1` | `cuff_unhealthy` |
| INT | `age <= int_window`, staleness of the witness (ms) | trigger `dispense`; `presence or intake or auth` | `no_witness` |

Indicators (Boolean signals with a margin of `+-inf`): `meas`, `dispense`, `sched_tick`, `day_end`, `presence`, `intake`, `auth`, and the equality `cuff_health == 1`. Signals that carry a margin: `bp`, `bp_drop`, `dose_count`, `inflation_ms`, and the term `age`.

### 2.2 Why guards are `+-inf` and not `+-1`

Analisi §2 R1 weakness 3 notes that for a Boolean signal the spatial robustness is degenerate (`+-1` or `+-inf`) and expresses no margin. A guard of `+-1` would enter a `min` or `max` next to a pressure margin of 15 mmHg or a time margin of 180000 ms, and its value would be silently compared with them in a different unit. With `+-inf` a guard never changes a finite margin when it passes, and dominates the result when it fails, which is the meaning of a structural failure (no measurement, unhealthy cuff, no witness). The price, stated in section 2.5, is that a failed guard cannot be graded.

### 2.3 Time margin: slack to the far edge of the window

For SCHED and INT the unit is `ms` and the margin is a time. The time margin is defined as the slack to the far edge of the window, computed on grid times (T01 section 3.3), where the far edge is the edge of the window that lies farthest from the anchor.

* **SCHED (window after the anchor).** Anchor step `k_a`, deadline step `k_d = k_a + sched_window / T_s`, a measurement visible at step `j`, `j >= k_a`:
  `slack(j) = t_{k_d} - t_j = (k_d - j) * T_s`. For grid-aligned events this is `(a + W) - t_m`. The far edge is the deadline. Measurements before the anchor (`j < k_a`) are on the near side of the trigger and do not count (guard `no_measurement_after_tick`).
* **INT (window before the anchor).** Anchor and decision step `k_d` (the dispense), a witnessing event visible at step `j`, `j <= k_d`, `age = (k_d - j) * T_s`:
  `slack(j) = t_j - (t_{k_d} - int_window) = int_window - age`. The far edge is the start of the look-back window. Events after the dispense (`j > k_d`) are on the near side of the trigger and do not count.

The value of an instance is the maximum slack over its candidate events (the earliest measurement of SCHED, the latest witness of INT: the disjunction of `once` picks the best witness). The sign of the slack is the Boolean verdict of the grid semantics: `slack >= 0` iff the event lies inside the window `[k_a, k_d]` (SCHED) or `[k_d - int_window / T_s, k_d]` (INT). Grid times are used so that this equivalence is exact; a continuous-time slack could differ in sign from the grid verdict by less than `T_s` (T01 section 3.3).

**Graded lateness.** Both templates grade beyond the window because time is their margin dimension: a SCHED measurement after the deadline has negative slack (in G-SCHED-3, 21 min late is `-1260000` ms) and an INT witness older than the window has negative slack (G-INT-2). For SCHED the graded value is only observable from the step at which the late measurement is visible: at the decision step the instance has no candidate and its value is `-inf` (guard `no_measurement_after_tick`, verdict already VIOLATED). The instance semantics therefore defines `sigma_i(k_e)` for every evaluation step `k_e >= k_a` as the maximum of `slack(j)` over measurement steps `j` in `[k_a, k_e]`, with `slack` measured to `k_d` (negative after `k_d`). It is non-decreasing in `k_e`, equals the string value at `k_e = k_d`, and its sign is fixed at `k_d`. The evaluation horizon of the grading ends at the next tick of the same schedule or at the closing step, whichever comes first, so that a measurement is not read as the late answer to a tick that another tick already supersedes. Whether the monitor emits a second, refined record after `k_d` (the state does not change; only the raw value) is WS01-T05's and WS01-T07's decision (section 9).

For templates whose unit is not time (HOLD, RESP), timing is a guard, not a margin: a measurement outside the look-back window or outside the response window is a failed guard (`-inf`, `no_recent_measurement`, `obligation_unmet`), not a graded lateness. Compare G-HOLD-4 with G-INT-2.

**Why the symmetric two-sided distance is not used.** The distance of a time `t_m` to the window `[a, a + W]` taken as `min(t_m - a, (a + W) - t_m)` would give `0` to a measurement taken exactly at the tick `a`, the earliest possible and perfectly punctual one, the same value as a measurement that only just meets the deadline; and it would penalise a measurement for being early. The far-edge slack gives `W` to a measurement at the tick and `0` only to one that just meets the deadline, which is the reading of "how much later could this measurement have been without violating the constraint". The literature on the time robustness of temporal-logic formulas is not cited here: `[ref-needed: WS03]` (analisi §4.2 recommends "time robustness" for timing constraints without giving a reference).

### 2.4 Degenerate Boolean predicates (R1 weakness 3)

The dispense, measurement, tick, end-of-day, authentication, presence and intake predicates are Boolean signals lifted to indicators. Their spatial robustness has no margin; they are guards (section 2.1) and never the margin dimension of a template. A margin is always taken from a quantity that has one: a pressure, a count, a duration, or a time distance.

### 2.5 Infinite values and normalisation

1. `sigma` of an instance is a real number or `-inf` (failed guard). No template body can be `+inf` inside a decided instance because each body contains a margin atom; `+inf` arises only for the whole formula with no decided instance (vacuous truth, section 1.3).
2. Normalisation. The contract gives `normalise(sigma_raw, scale) = clip(sigma_raw / scale, -1, 1)` with `scale > 0`. The convention adopted here for the infinite case is `+-inf / scale = +-inf` and `clip(+-inf, -1, 1) = +-1`. A failed guard gives `sigma_tilde = -1`; the contract text does not mention infinities (section 9).
3. The value `sigma_tilde = -1` has two origins: a finite raw value of at most `-scale` (clipped, for example G-RANGE-5 with `-60` mmHg and scale 20) and a failed guard (`-inf`, for example G-HOLD-4). They are different situations (a large deviation, and a missing or invalid observation). The marker `guard_failed` keeps them apart; an alert derived from a failed guard must carry it (WS01-T07).
4. A finite `sigma` never becomes an infinity; a guard never turns into a finite value.

### 2.6 Sign convention, units and scales (stated once)

* `sigma > 0`: the constraint is satisfied with that margin; `sigma < 0`: violated with that margin; `sigma = 0`: tie, satisfied (non-strict atoms).
* Units: `sigma` is in the `unit` of the template: `mmHg` (RANGE, HOLD, RESP), `ms` (SCHED, SYS, INT), `dose` (COUNT). `RobustnessUnit.DIMENSIONLESS` is not used by any of the seven templates.
* Scale `s` (registry entry `scale_<id>`, same unit as `sigma`, `s > 0`) is the clinically significant deviation; `sigma_tilde = clip(sigma / s, -1, 1)` is dimensionless in `[-1, 1]`. Values are compared across templates only after normalisation and within a priority class (analisi §4.2; ranking is WS01-T04).

## 3 Template table

### 3.1 The seven templates

The row is the `Template` dataclass of `02-interfaces.md#template`. `kind` is the enum member (`CARE_PLAN` value `phi_cp`, `SYSTEM` value `phi_sys`, `INTEGRITY` value `phi_int`); `unit` is the `RobustnessUnit` member. RANGE, SCHED, HOLD, COUNT, RESP are constraints of the patient care plan (phi_CP); SYS is a constraint on the health of the monitoring system (phi_SYS); INT is a constraint on the provenance of events (phi_INT).

| id | kind | formula_past_time | signals | params | unit | scale_param | priority_param | max_verdict_latency_param | creates_robot_obligation |
|---|---|---|---|---|---|---|---|---|---|
| RANGE | CARE_PLAN | `historically(meas -> (bp >= bp_band_low and bp <= bp_band_high))` | meas, bp | bp_band_low, bp_band_high | MMHG | scale_range | priority_range | max_latency_range | False |
| SCHED | CARE_PLAN | `historically(once[sched_window, sched_window + step_ms] sched_tick -> once[0, sched_window] (meas and age >= 0))` | sched_tick, meas | sched_window | MS | scale_sched | priority_sched | max_latency_sched | True |
| HOLD | CARE_PLAN | `historically(dispense -> (once[0, hold_lookback] meas and bp >= bp_hold_threshold))` | dispense, meas, bp | bp_hold_threshold, hold_lookback | MMHG | scale_hold | priority_hold | max_latency_hold | False |
| COUNT | CARE_PLAN | `historically(dispense -> dose_count <= dose_max_24h) and historically(day_end -> dose_count >= dose_min_day_end)` | dispense, dose_count, day_end | dose_max_24h, dose_min_day_end | DOSE | scale_count | priority_count | max_latency_count | False |
| RESP | CARE_PLAN | `historically(once[delta2, delta2 + step_ms] dispense -> once[0, delta2 - delta1] (meas and bp_drop >= delta_resp))` | dispense, meas, bp_drop | delta1, delta2, delta_resp | MMHG | scale_resp | priority_resp | max_latency_resp | True |
| SYS | SYSTEM | `historically(meas -> (cuff_health == 1 and inflation_ms >= cuff_inflation_min))` | meas, cuff_health, inflation_ms | cuff_inflation_min | MS | scale_sys | priority_sys | max_latency_sys | False |
| INT | INTEGRITY | `historically(dispense -> once[0, inf] ((presence or intake or auth) and age <= int_window))` | dispense, presence, intake, auth | int_window | MS | scale_int | priority_int | max_latency_int | True |

Notes on the table.

1. `signals` lists only `SignalId` values that the string mentions. The derived signal `bp_drop` is `bp_pre - bp` (T01 section 5.4); its inputs `bp` and `bp_pre` are not repeated. `age` is not a signal (section 1.4). `hr_ecg`, `hr_pulse` and `spo2` are used by no template.
2. `params` lists the registry names that occur in the string. `scale_<id>`, `priority_<id>` and `max_latency_<id>` are separate fields; `step_ms` is a monitor-configuration constant (section 3.4).
3. Strings of SCHED and RESP contain the widened antecedent of ADR-007; their relation to the reference semantics is section 1.5. The strings of COUNT and INT differ from the workshop forms of analisi §4.1 in a way that does not change the Boolean verdict (sections 4.4 and 4.7).
4. `creates_robot_obligation` is True for SCHED, RESP and INT. The contract comment names only RESP and SCHED; INT follows analisi §10 objection 3 (CP1, section 5.5).

### 3.2 Latency: derived values, not free parameters

`max_verdict_latency_param` names a value derived from the deadline offset `B` of the template and the monitor step. It is not an independent registry parameter, because a free value could contradict `T_s`, `sched_window` or `delta2`. The value is the event-time bound `B + T_s` (T01 section 4.6): the definitive verdict is decidable at `t_d = t_{k_up(a)} + B`, so `B <= t_d - a < B + T_s`. The end-to-end latency adds the reorder delay `D` and a compute time (T01 section 4.6); which of the two the monitor reports as `verdict_latency_bound_ms` is CG-4, settled in WS01-T05. The bound is stated as a strict upper bound on the event-time latency.

| Template | Anchor | Deadline offset `B` | Decision step `k_d` | `max_latency_<id>` = `B + step_ms` (derived) |
|---|---|---|---|---|
| RANGE | measurement | 0 | `k_up(t_m)` | `max_latency_range` = `step_ms` |
| SCHED | schedule tick | `sched_window` | `k_up(a) + sched_window / T_s` | `max_latency_sched` = `sched_window + step_ms` |
| HOLD | dispense | 0 | `k_up(t_d)` | `max_latency_hold` = `step_ms` |
| COUNT | dispense; end of day | 0 | `k_up(t_d)`; `K` | `max_latency_count` = `step_ms` |
| RESP | dispense | `delta2` | `k_up(a) + delta2 / T_s` | `max_latency_resp` = `delta2 + step_ms` |
| SYS | measurement | 0 | `k_up(t_m)` | `max_latency_sys` = `step_ms` |
| INT | dispense | 0 | `k_up(t_d)` | `max_latency_int` = `step_ms` |

Illustration with F0 (`step_ms = 60000`, fixture arithmetic): `max_latency_sched = 1800000 + 60000 = 1860000` ms; `max_latency_resp = 10800000 + 60000 = 10860000` ms; the other five are `60000` ms.

### 3.3 Parameters used

Registry working names fixed here (WS01-T03 registers them). F0 values are in the `fixture_registry` section of `docs/formal/golden/templates.yaml`. "Role" follows the proposal of T01 CG-1 (window, threshold, limit, scale, priority, derived, configuration); the alignment rule applies to window roles.

| Working name | F0 value | Unit | Origin | Role |
|---|---|---|---|---|
| `bp_band_low` | 110 | mmHg | analisi §4.1 (illustrative, unverified) | threshold |
| `bp_band_high` | 140 | mmHg | analisi §4.1 (illustrative, unverified) | threshold |
| `bp_hold_threshold` | 100 | mmHg | analisi §4.1 (illustrative, unverified) | threshold |
| `hold_lookback` | 3600000 | ms | analisi §4.1, 60 min (illustrative, unverified) | window |
| `dose_max_24h` | 2 | dose | analisi §4.1 (illustrative, unverified) | limit |
| `dose_min_day_end` | 2 | dose | analisi §4.1 (illustrative, unverified) | limit |
| `delta1` | 3600000 | ms | analisi §4.6 (illustrative, unverified) | window |
| `delta2` | 10800000 | ms | analisi §4.6 (illustrative, unverified) | window |
| `delta_resp` | 10 | mmHg | FIXTURE-ONLY | threshold |
| `sched_window` | 1800000 | ms | FIXTURE-ONLY | window |
| `cuff_inflation_min` | 30000 | ms | FIXTURE-ONLY | threshold (not a window) |
| `int_window` | 300000 | ms | analisi §4.1, 5 min (illustrative, unverified) | window |
| `scale_range` | 20 | mmHg | analisi §4.2 example | scale |
| `scale_sched` | 1800000 | ms | analisi §4.2 example, 30 min | scale |
| `scale_count` | 1 | dose | analisi §4.2 example | scale |
| `scale_hold`, `scale_resp` | 20 | mmHg | FIXTURE-ONLY | scale |
| `scale_sys` | 30000 | ms | FIXTURE-ONLY | scale |
| `scale_int` | 300000 | ms | FIXTURE-ONLY | scale |
| `priority_hold`, `priority_range`, `priority_sched` | 1, 2, 3 | rank, 1 = highest | analisi §4.2 order example (hold > range > sched) | priority |
| `priority_count`, `priority_resp` | 2, 2 | rank | FIXTURE-ONLY | priority |
| `priority_sys`, `priority_int` | 3, 3 | rank | FIXTURE-ONLY | priority |
| `max_latency_range` ... `max_latency_int` (seven names) | derived | ms | section 3.2 | derived |
| `step_ms` (`T_s`) | 60000 | ms | FIXTURE-ONLY monitor configuration | configuration |
| `meas_min_day` | 5 | count | analisi §2 R2 weakness 5, §4.6 (illustrative, unverified) | not adopted (CP2, section 4.4) |

The direction of `priority` ("1 = highest") is stated in the F0 table; the contract does not state it (CP5, WS01-T04).

### 3.4 Registry names to register (list for WS01-T03)

* Clinical entries used by the strings: `bp_band_low`, `bp_band_high`, `bp_hold_threshold`, `hold_lookback`, `dose_max_24h`, `dose_min_day_end`, `delta1`, `delta2`, `delta_resp`, `sched_window`, `cuff_inflation_min`, `int_window`.
* Scales: `scale_range`, `scale_sched`, `scale_hold`, `scale_count`, `scale_resp`, `scale_sys`, `scale_int`. Priorities: `priority_range`, `priority_sched`, `priority_hold`, `priority_count`, `priority_resp`, `priority_sys`, `priority_int`.
* Derived names (computed, not free): `max_latency_range`, `max_latency_sched`, `max_latency_hold`, `max_latency_count`, `max_latency_resp`, `max_latency_sys`, `max_latency_int`. The contract says `max_verdict_latency_param` is a "registry entry"; a derived name is resolved by the registry loader from the formula of section 3.2 (contract gap, section 9).
* Monitor configuration, not clinical registry entries: `step_ms`; from T01: `reorder_delay_ms`, `clock_skew_max_ms`.
* Physiological bounds used by WS01-T05, not by a template string: `bound_bp_lower`, `bound_bp_upper`.
* `meas_min_day` is declared but not adopted by any template (CP2).
* Window parameters subject to the alignment rule: `sched_window`, `hold_lookback`, `int_window`, `delta1`, `delta2` and the derived width `delta2 - delta1`.

## 4 Template details

### 4.0 Common form and the formulas of the workshop analysis

Each subsection gives: the intent and the conjunct (phi_CP, phi_SYS or phi_INT); the LaTeX form of analisi §4.1 (numbers illustrative, unverified) and, where it differs, the registry form; the past-time string; the future-time form for SCHED and RESP; the atoms with their kind (indicator, guard or margin); the unit; the decision instant; and the latency formula.

The seven formulas of analisi §4.1 as written there (numbers are illustrative and unverified; they are examples to be anchored to a drug and a guideline by the clinician review of WS00-T07):

```latex
% Care-plan constraints (phi_CP), past-time formulations monitorable without look-ahead
\varphi_{\mathrm{range}} = \square\,\big(m \rightarrow (bp \ge 110 \wedge bp \le 140)\big)
\varphi_{\mathrm{sched}} = \square\,\big(\mathrm{O}_{[W,W]}\, s \rightarrow \mathrm{O}_{[0,W]}\, m\big)
\varphi_{\mathrm{hold}}  = \square\,\big(d \rightarrow \mathrm{O}_{[0,60\,\mathrm{min}]}\,(m \wedge bp \ge 100)\big)
\varphi_{\mathrm{count}} = \square\,\big(c_d \le 2\big) \;\wedge\; \square\,\big(e_{\mathrm{day}} \rightarrow c_d \ge 2\big)
\varphi_{\mathrm{resp}}  = \square\,\big(\mathrm{O}_{[\Delta_2,\Delta_2]}\, d \rightarrow \mathrm{O}_{[0,\Delta_2-\Delta_1]}\,(m \wedge r \ge \delta)\big),
\quad r(t) = bp^{\mathrm{pre}}(t) - bp(t)
% System constraints (phi_SYS) and integrity constraints (phi_INT)
\varphi_{\mathrm{SYS}} = \square\,\big(m \rightarrow (h_c = 1 \wedge q \ge q_{\min})\big)
\varphi_{\mathrm{INT}} = \square\,\big(d \rightarrow \mathrm{O}_{[0,5\,\mathrm{min}]}\,(w \vee a_{\mathrm{auth}})\big)
```

Where the strings of section 3.1 differ from these forms: SCHED and RESP use the widened window `O[W, W+T_s]` (contract, ADR-007); COUNT restates `c_d <= 2` with the trigger `d` (section 4.4); INT is given with an unbounded `once` and the margin atom `age <= int_window`, which has the same Boolean verdict as `O[0, int_window]` (section 4.7); HOLD is decided between a workshop form and a refined form (section 4.3). Signal symbols are those of T01 section 2.1 (`m` is `meas`, `d` is `dispense`, `s` is `sched_tick`, `e_day` is `day_end`, `h_c` is `cuff_health`, `q` is `inflation_ms`, `a_auth` is `auth`, `w` is `presence or intake`, `r` is `bp_drop`).

### 4.1 RANGE

**Intent (phi_CP).** Every completed measurement lies inside the prescribed band. One instance per measurement event.

**LaTeX.** `\varphi_{\mathrm{range}} = \square\,\big(m \rightarrow (bp \ge 110 \wedge bp \le 140)\big)` (numbers illustrative, unverified).

**Past-time string.** `historically(meas -> (bp >= bp_band_low and bp <= bp_band_high))`.

**Atoms.** Indicator (guard, trigger): `meas`. Margin (mmHg): `bp >= bp_band_low` and `bp <= bp_band_high`. Body value `min(bp - bp_band_low, bp_band_high - bp)`: the distance to the nearer limit.

**Unit and scale.** mmHg; `scale_range`. **Decision instant.** The step `k_up(t_m)` of the measurement (`B = 0`); `bp` at that step is the measurement value (the sample and the event of one measurement share a device time). **Latency.** `max_latency_range = step_ms`. **Golden.** G-RANGE-1 to G-RANGE-5 (interior, violation with the workshop Table I arithmetic, lower violation, boundary tie, clipping).

The template applies at every measurement, including measurements inside the drug onset window; analisi §4.6 (row 08:55) says it must be clarified clinically whether the band constraint applies during onset. The library has no exemption; this is a question for the clinician review (section 9).

### 4.2 SCHED

**Intent (phi_CP).** A measurement occurs within `sched_window` after every schedule tick of the care plan. One instance per tick, static anchors from the plan schedule.

**LaTeX.** `\varphi_{\mathrm{sched}} = \square\,\big(\mathrm{O}_{[W,W]}\, s \rightarrow \mathrm{O}_{[0,W]}\, m\big)`; evaluated with the widened window `\mathrm{O}_{[W,W+T_s]}` (ADR-007).

**Past-time string.** `historically(once[sched_window, sched_window + step_ms] sched_tick -> once[0, sched_window] (meas and age >= 0))`.

**Future-time form.** `historically(sched_tick -> eventually[0, sched_window] meas)`, that is `s -> F[0,W] m` under `historically`. WS01-T05 proves that the verdicts of the past-time and future-time forms coincide under (A1) and (A2) of section 1.5 (ablation A7; for RESP also (A3), section 4.5).

**Atoms.** Indicators (guards): `sched_tick` (trigger) and `meas` (the response). Margin (ms): `age >= 0`, which contributes the deadline slack `age` of a measurement (section 2.3). Guard failure: `no_measurement_after_tick`.

**Unit and scale.** ms (time margin); `scale_sched`. **Decision instant.** `k_d = k_up(a) + sched_window / T_s`, decision time `t_{k_up(a)} + sched_window`. **Latency.** `max_latency_sched = sched_window + step_ms`. **Robot obligation.** `measure_bp` (section 5). **Golden.** G-SCHED-1 to G-SCHED-4 (slack, deadline tie, graded lateness, near-side measurement).

### 4.3 HOLD

**Intent (phi_CP).** Do not dispense if the last measured pressure is below the hold threshold. This is a real sequence constraint (analisi §4.1 aspect 3): the decision at the dispense needs a measurement that came before.

**Workshop form.** `\varphi_{\mathrm{hold}} = \square\,\big(d \rightarrow \mathrm{O}_{[0,60\,\mathrm{min}]}\,(m \wedge bp \ge 100)\big)`, string `historically(dispense -> once[0, hold_lookback] (meas and bp >= bp_hold_threshold))`. It requires some measurement in the look-back window with a pressure at or above the threshold.

**Refined form (adopted).** `\varphi_{\mathrm{hold}}^{\mathrm{ref}} = \square\,\big(d \rightarrow (\mathrm{O}_{[0,60\,\mathrm{min}]}\, m \wedge bp \ge 100)\big)`, string `historically(dispense -> (once[0, hold_lookback] meas and bp >= bp_hold_threshold))`. Recency is a guard (a measurement exists in the look-back window) and the margin is taken on `bp`, the latest held value, which at the dispense step is the pressure of the latest measurement.

**Decision (recommended and adopted: the refined form).** The two forms differ when the look-back window holds two measurements. Golden case G-HOLD-3 (measurements at 06:15 with bp 120 and 06:55 with bp 90, dispense 07:00): the workshop form evaluates `max(120 - 100, 90 - 100) = +20` mmHg and accepts the dispense, although the latest reading, the clinically relevant one, is below the threshold; the refined form evaluates `90 - 100 = -10` mmHg and reports a violation. The clinical intent of analisi §4.1 aspect 3 is "do not dispense when the (current) systolic pressure is below the threshold", which is the latest reading; an old high reading must not mask a recent low one. The refined form is recommended and used in the golden file; the workshop expected value is recorded in G-HOLD-3 as `workshop_form`. Because it changes a formula of the workshop paper it is flagged for confirmation at the clinician review and the M1 freeze (section 9).

**Atoms.** Indicators (guards): `dispense` (trigger), `once[0, hold_lookback] meas` (recency). Margin (mmHg): `bp >= bp_hold_threshold`. Guard failure: `no_recent_measurement` (G-HOLD-4: last measurement 90 min old with a 60 min look-back).

**Unit and scale.** mmHg; `scale_hold`. **Decision instant.** `k_up(t_d)` of the dispense (`B = 0`); a measurement with the same device time as the dispense counts as before it (M5). **Latency.** `max_latency_hold = step_ms`. **Robot obligation.** None of its own: the measurement it needs is a plan feasibility property (section 5.4). **Golden.** G-HOLD-1 to G-HOLD-4.

### 4.4 COUNT

**Intent (phi_CP).** Dose count limit and day-end count obligation. Counters are derived signals with atomic predicates (analisi §4.1 aspect 2, ADR-007), not "outside STL".

**LaTeX.** `\varphi_{\mathrm{count}} = \square\,\big(c_d \le 2\big) \;\wedge\; \square\,\big(e_{\mathrm{day}} \rightarrow c_d \ge 2\big)` (numbers illustrative, unverified).

**Past-time string.** `historically(dispense -> dose_count <= dose_max_24h) and historically(day_end -> dose_count >= dose_min_day_end)`.

**Restatement of the limit.** The workshop conjunct `historically(dose_count <= dose_max_24h)` is written here with the trigger `dispense`. The two have the same value: `dose_count` (T01 section 5.1) increases only at dispense steps and otherwise only decreases when events leave the 24 h window, so `dose_max_24h - dose_count` reaches its minimum over the steps at a dispense step. The restatement lets the instance be the dispense event (one instance per dispense, T01 section 3.4) and gives an unscheduled dose its own alert (analisi §4.6 row 21:02); it is a restatement, not a change of the constraint. That a violation persists over several steps after one excess dose (T01 CG-14) is WS01-T05's and WS01-T07's question.

**Atoms.** Indicators (guards): `dispense` and `day_end` (triggers). Margin (dose): `dose_count <= dose_max_24h` with value `dose_max_24h - dose_count` (analisi §4.1 aspect 2: "robustness 2 - c_d in doses") and `dose_count >= dose_min_day_end` with value `dose_count - dose_min_day_end`. No guard can fail inside an instance.

**Unit and scale.** dose; `scale_count`. **Decision instant.** The dispense step (limit); the closing step `K` of the day (day-end obligation, `day_end` is generated there, T01 section 5.5). At `K` the window is `(0, T_day]` (G-COUNT-3). **Latency.** `max_latency_count = step_ms`. **Golden.** G-COUNT-1 (counter 3 over 2: `-1` dose, not the `-8` of the workshop Table I), G-COUNT-2 (`c_d` equal to the limit, tie), G-COUNT-3 (day-end obligation, one dose).

**Measurement-count obligation (CP2).** Analisi §4.6 and §4.9 item 3 use a day-end obligation of five measurements a day (`meas_count` of T01 section 5.2, `meas_min_day`). It is not part of COUNT. Reasons: (1) its margin is in measurements, and `RobustnessUnit` has no member for it (`MMHG`, `MS`, `DOSE`, `DIMENSIONLESS`); mapping it to `DIMENSIONLESS` would give COUNT two units, which the one-margin-dimension rule (section 2.1) forbids; (2) each scheduled measurement is already an instance of SCHED, so a missed measurement is reported there and again by a day-end count, which is the unhandled cascade of analisi §4.6 row 15:00 (a second alert with a cause that lies in the first). The definition, should it be adopted, is `historically(day_end -> meas_count >= meas_min_day)` with margin `meas_count - meas_min_day` in measurements; it needs a new template id and a new unit, so it needs an ADR (section 9). Nothing in the seven templates depends on it.

### 4.5 RESP

**Intent (phi_CP).** After a dose, the pressure falls by at least `delta_resp` relative to the pre-dose reference at some measurement in the response window `[a + delta1, a + delta2]`. One instance per dispense event, dynamic anchors.

**LaTeX.** `\varphi_{\mathrm{resp}} = \square\,\big(\mathrm{O}_{[\Delta_2,\Delta_2]}\, d \rightarrow \mathrm{O}_{[0,\Delta_2-\Delta_1]}\,(m \wedge r \ge \delta)\big)`, `r(t) = bp^{pre}(t) - bp(t)`; evaluated with the widened window `\mathrm{O}_{[\Delta_2,\Delta_2+T_s]}` (numbers illustrative, unverified).

**Past-time string.** `historically(once[delta2, delta2 + step_ms] dispense -> once[0, delta2 - delta1] (meas and bp_drop >= delta_resp))`. At the decision step the consequent window `[k_d - (delta2 - delta1)/T_s, k_d]` is `[a + delta1, a + delta2]` on the grid.

**Future-time form.** `historically(dispense -> eventually[delta1, delta2] (meas and bp_drop >= delta_resp))`, that is `d -> F[delta1, delta2](m and r >= delta_resp)`, with `bp_pre` captured at the dispense. WS01-T05 proves the equivalence of verdicts under (A1), (A2) and (A3) of section 1.5; (A3) (no other dispense visible in `k_a, ..., k_d + 1`) is needed because the string uses the global `bp_drop` stream and the future-time form the per-instance `pre_i`.

**Atoms.** Indicators (guards): `dispense` (trigger), `meas` (a measurement in the window). Margin (mmHg): `bp_drop >= delta_resp`, value `bp_drop - delta_resp`. The per-instance drop is `r_i(j) = pre_i - bp_j` with `pre_i` captured once at the dispense (T01 section 5.3); a global stream `bp_pre` would let overlapping doses overwrite each other, so the instance form is the reference and the string coincides with it only under (A3) of section 1.5. Guard failure: `obligation_unmet`. If `pre_i` is `NaN` (no measurement before the dose) the margin is unknown (section 1.3); plan feasibility check F2 of section 5.4 prevents this in a scheduled plan.

**Max over the window.** `once` is a maximum: one measurement with a large enough drop satisfies the obligation even if another measurement in the window has a small drop (G-RESP-3, `max(-5, +2) = +2`).

**Unit and scale.** mmHg; `scale_resp`. **Decision instant.** `k_d = k_up(a) + delta2 / T_s`. **Latency.** `max_latency_resp = delta2 + step_ms`. **Robot obligation.** `measure_bp` (section 5): the specification is satisfiable only if a measurement falls in `[a + delta1, a + delta2]` (analisi §4.1 aspect 4). **Golden.** G-RESP-1 to G-RESP-4 (satisfied, violated, max over two measurements, no measurement in the window).

### 4.6 SYS

**Intent (phi_SYS).** A measurement is valid only if the cuff node is healthy and the inflation duration is acceptable. A violation of phi_SYS is a violation of the monitoring system's specification; a device fault is not a violation of the care plan.

**LaTeX.** `\varphi_{\mathrm{SYS}} = \square\,\big(m \rightarrow (h_c = 1 \wedge q \ge q_{\min})\big)` (illustrative, unverified).

**Past-time string.** `historically(meas -> (cuff_health == 1 and inflation_ms >= cuff_inflation_min))`.

**Atoms.** Indicators (guards): `meas` (trigger); the equality `cuff_health == 1` (status). Margin (ms): `inflation_ms >= cuff_inflation_min`, value `inflation_ms - cuff_inflation_min`, a duration compared with a threshold (not a deadline slack). Guard failure: `cuff_unhealthy`. In the workshop Table I the row "15:00, sigma = -21" has an implicit unit; here the unit is stated: 21000 ms in the fixture (G-SYS-2).

**Unit and scale.** ms; `scale_sys`. **Decision instant.** `k_up(t_m)` of the measurement. **Latency.** `max_latency_sys = step_ms`. **Golden.** G-SYS-1 to G-SYS-3.

### 4.7 INT

**Intent (phi_INT).** A dispense is backed by robot-observed presence, robot-verified intake, or an authenticated dispense event, seen at or before the dispense. INT tests the provenance of the event, not adherence (T01 section 2.4, M1). A dispense that no robot witnessed and no authentication backs is an integrity constraint violation (a violation of phi_INT; the class C3 is an attributed cause, not a violation).

**LaTeX (workshop).** `\varphi_{\mathrm{INT}} = \square\,\big(d \rightarrow \mathrm{O}_{[0,5\,\mathrm{min}]}\,(w \vee a_{\mathrm{auth}})\big)` (illustrative, unverified), with `w = presence or intake` of T01 section 2.4.

**Past-time string.** `historically(dispense -> once[0, inf] ((presence or intake or auth) and age <= int_window))`. The Boolean verdict equals that of the workshop form: a candidate step `j` has value `int_window - age_j >= 0` iff `age_j <= int_window`, that is iff `j` lies in `O[0, int_window]`. The unbounded `once` only adds the graded negative values for a witness older than the window (section 2.3).

**Direction and decision (T01 CG-7).** The formula looks back from the dispense step, and INT is decided at that step (`B = 0`), with events after the dispense on the near side of the trigger (not counted). This is the reading that the golden cases G-INT-1 to G-INT-3 fix (the witness precedes the dispense, `age` is measured back from it). A deadline form (decision at `int_window` after the dispense) would let a later `intake` contribute; it is not adopted. Consequently an `intake` inside the look-back window can only come from an earlier dose and evidences that the robot was there; keeping `intake` in the disjunction preserves M1 and costs nothing. Whether to add a forward clause for the intake that follows a dispense is a design question recorded in section 9.

**Presence is a level.** `presence` is a status level held between samples (T01 section 2.1). The "age" of the witness is the time since the last step with `presence = 1`; a witness that has left needs an explicit `presence = 0` sample, as in the fixtures G-INT-1 and G-INT-2 (a `0.0` sample one step after the observation). The unavailability of the robot channels (never converted to `0`, T01 CG-6) is handled by the interval semantics of WS01-T05; G-INT-3 shows the case in which an authenticated event decides the value while both robot channels are unavailable.

**Atoms.** Indicators (guards): `dispense` (trigger), `presence`, `intake`, `auth`. Margin (ms): `age <= int_window`, value `int_window - age`. Guard failure: `no_witness`.

**Unit and scale.** ms (time margin: slack to the far edge, section 2.3); `scale_int`. **Decision instant.** `k_up(t_d)`. **Latency.** `max_latency_int = step_ms`. **Robot obligation.** `witness_dispense` (section 5), created statically from the dispense ticks of the schedule because the window looks back (section 5.3). **Golden.** G-INT-1 (`+180000`), G-INT-2 (`-180000`), G-INT-3 (`+300000`).

Limit, to be reported with the diagnosability matrix (analisi §4.5): a plausible, cross-modally consistent injection by an informed attacker who is physically present is not detectable from `presence`; INT does not claim to detect it.

## 5 Robot obligations

### 5.1 Why obligations exist

A response template is satisfiable only if a measurement falls in its window (analisi §4.1 aspect 4), and phi_INT is satisfiable only if a witness or an authenticated event exists. The care specification therefore induces tasks for the assistive robot: the measurement and witness obligations of analisi §10 objection 3 ("the robot is part of the specification"), executed by the robot, monitored and predicted (deadlines of care delivery, analisi §4.3). This gives the robot a role in the specification that does not depend on hosting the monitor (ADR-003).

### 5.2 The obligation record (document level, CP9)

`02-interfaces.md` has no contract for the record that WS07-T04 consumes (CP9). This document defines it at document level; WS01-T08 proposes a contract.

| Field | Type | Meaning |
|---|---|---|
| `obligation_id` | str | `"<source_template>:<instance_key>"`, unique within a care plan |
| `source_template` | TemplateId | SCHED, RESP or INT |
| `instance_key` | str | the `TemplateInstance.instance_key` it belongs to |
| `patient_id` | str | patient of the care plan |
| `action` | `measure_bp` or `witness_dispense` | the task type requested from the robot |
| `window_start_ms` | TimeMs | first device time at which the action counts |
| `window_end_ms` | TimeMs | last device time at which the action counts (continuous-time end) |
| `deadline_ms` | TimeMs | the decision time of the instance on the grid, `t_{k_up(a)} + B` (T01 CG-3) |
| `created_at_ms` | TimeMs | monitor time at which the record is issued |

The record does not say how the action is carried out (who operates the cuff, how presence is observed): that is the robot node's (WS07). `measure_bp` is met by a completed measurement event in the window; `witness_dispense` by a `presence`, `intake` or `auth` observation in the window. The obligation is derived from the instance and is not a second specification: its failure is the violation of the instance, and the record links that violation to the robot task outcome (`ROBOT_TASK` event) so that the attribution layer can separate a robot late to the window (embodiment failure, cause C2) from a missing patient response (analisi §4.5 matrix). The status of an obligation does not enter sigma.

### 5.3 Creation rules

| Source | `action` | Creation | `window_start_ms` | `window_end_ms` | `deadline_ms` | `created_at_ms` |
|---|---|---|---|---|---|---|
| SCHED | `measure_bp` | static: one per measurement tick `a` of `CarePlan.schedule` | `a` | `a + sched_window` | `t_{k_up(a)} + sched_window` | plan activation (at or before `a`) |
| RESP | `measure_bp` | dynamic: one per DISPENSE event with device time `a` | `a + delta1` | `a + delta2` | `t_{k_up(a)} + delta2` | `t_{k_up(a)} + D` (finalisation of the anchor step) |
| INT | `witness_dispense` | static: one per dispense tick `a` of `CarePlan.schedule` (anticipatory) | `a - int_window` | `a` | `t_{k_up(a)}` | plan activation |

1. SCHED is static because its anchors are plan ticks. RESP is dynamic because its anchor is the actual dispense (which may be late, early, or unscheduled, and whose device time defines `a`).
2. INT is created statically from the dispense ticks, not dynamically at each DISPENSE event. The task text of WS01-T02 says dynamic for RESP and INT; this document deviates for INT and records it. The INT window looks back from the dispense, so an obligation created when the DISPENSE event arrives would be created after its window has closed, and could not change the verdict; what the robot can do to satisfy INT is to be co-located and observing before the dispense, which needs lead time and therefore the plan. An unscheduled dispense gets no anticipatory obligation (nothing was announced); INT still decides it, and a missing witness is then a real finding. If a forward witness after each dispense is wanted (to verify the intake that follows, ADR-004), it is a separate design choice (section 9).
3. For a dispense tick within `int_window` of the day start, `window_start_ms` is negative (previous day): T01 section 5.5, M6 and CP7.
4. One measurement may satisfy several obligations (a SCHED window and a RESP window can overlap); the library does no matching between measurements and obligations, and the record does not claim exclusivity.
5. `deadline_ms` is the quantity a forecaster predicts when it warns that the robot will be late (analisi §4.3); `window_end_ms` is the continuous-time end, `deadline_ms` the grid decision time (they differ by less than `T_s`).

### 5.4 Plan feasibility checks at load

A patient care plan passes these checks when it is loaded (`Monitor.load`, together with the signature check of the plan and the alignment rule of T01 section 3.6). A failed check rejects the plan, with the name of the check and the offending tick.

| Check | Statement | If it fails |
|---|---|---|
| F1 alignment | `sched_window`, `hold_lookback`, `int_window`, `delta1`, `delta2` and `delta2 - delta1` are non-negative multiples of `step_ms`; `T_day mod step_ms = 0` | reject (T01 section 3.6, M2) |
| F2 HOLD | for every dispense tick `a` there is a measurement tick in `[a - hold_lookback, a)` | HOLD fails by construction with `no_recent_measurement` (the check is conservative: a measurement at the same instant as the dispense also counts, M5) |
| F3 RESP | for every dispense tick `a` there is a measurement tick in `[a + delta1, a + delta2]` | RESP fails by construction with `obligation_unmet` |
| F4 INT | for every dispense tick `a` the robot task plan has a visit that covers `[a - int_window, a]`, or the dispense is authenticated | INT can only be decided by `auth`; otherwise `no_witness` is certain. The data comes from the robot task plan (WS07), not from `CarePlan.schedule` |
| F5 COUNT | the schedule has at most `dose_max_24h` dispense ticks in any 24 h window and at least `dose_min_day_end` in a day | COUNT fails by construction |
| F6 registry | every name of the strings resolves (section 3.4); `scale_<id> > 0`; priorities are integers | reject |
| F7 day boundary | list the instances whose decision step lies after 24:00 (M6) | informational |

`CarePlan.schedule` is a `Sequence[TimeMs]` of "measurement and dispense ticks" and does not say which tick is which (contract gap, section 9); the checks F2, F3, F4 and F5 need the kind of each tick.

### 5.5 Resolution of CP1 and CP9

* **CP1.** `creates_robot_obligation` is True for SCHED, RESP and INT, False for RANGE, HOLD, COUNT and SYS. Reason for INT: analisi §10 objection 3 derives the witness obligation from phi_INT; without it the answer to "why is the robot needed" would rest on RESP and SCHED alone. The contract comment names only RESP and SCHED. Proposed disposition for WS01-T08: clarify the comment (ADR-021 lists it).
* **CP9.** The obligation record of section 5.2 is proposed as a new contract `#robot-obligation`, owner WS01, consumer WS07-T04. ADR needed (a new contract).

## 6 Expressiveness notes

The five aspects of analisi §4.1, one subsection each (R1 weakness 5), and the decomposition (R1 weakness 8).

### 6.1 Pre-dose reference (aspect 1)

"Pressure decrease" needs a reference to a past value. It is obtained by a derived signal `bp_pre`, captured per obligation instance at the dispense (T01 section 5.3): the pressure of the latest measurement with device time not after the dispense. Inside the instance, `bp_drop = bp_pre - bp` is an ordinary signal, so the formula stays inside standard past-time STL and is supported by tools without a freeze operator. STL with a freeze operator (STL*) is the alternative: the pre-dose value would be frozen at the dispense and referred to inside the window. It is cited and not implemented (ADR-007; `[ref-needed: WS03]`, analisi §4.1 aspect 1). The per-instance capture is the freeze at the anchor, restricted to the one use RESP needs. In G-RESP-1 to G-RESP-4 the pre-dose value is 150 mmHg from a fixture measurement at 06:55.

### 6.2 Counters as derived signals (aspect 2)

`dose_count` is a derived signal (trailing 24 h, half-open window, T01 section 5.1), and `dose_count <= dose_max_24h` is an atomic predicate whose robustness is `dose_max_24h - dose_count` in doses. So counters are not "outside STL": sigma and the traceability record stay uniform across templates (analisi §4.1 aspect 2; R1 weakness 5). The count-limit and the day-end obligation share the unit `dose` (section 4.4). The day-end obligation depends on the carry-over of state across days (CP7, T01 section 5.5).

### 6.3 Hold and sequence constraints (aspect 3)

HOLD is a sequence constraint: the constraint at the dispense refers to what happened before it (a measurement, its value). A past operator states it without look-ahead and without waiting for a future window: at the dispense step the verdict is immediate. This is why the library is past-time (ADR-007) and why HOLD is the strongest example of the need for past operators. Ordering constraints beyond `once` use `since`; an illustration of the syntax (not a template, no clinical content): `cuff_health == 1 since meas` states that the cuff was healthy at every step after some earlier measurement. None of the seven templates needs `since`, but the language and the semantics of section 1 include it so that a sequence constraint can be added as a template later.

### 6.4 Measurement obligation in the response window (aspect 4)

The RESP formula is satisfiable only if a measurement falls in `[a + delta1, a + delta2]`: with no measurement there, the guard fails and the instance is violated with `obligation_unmet`, whatever the patient's pressure did (G-RESP-4). The specification therefore induces a measurement task. Section 5 turns this into the obligation record, the creation rules and the load-time feasibility checks; the same holds for SCHED (measurement after a tick) and, through the witness, for INT.

### 6.5 Point events (aspect 5)

Impulse windows with an exact offset, `O[W,W]`, are evaluated as `O[W, W+T_s]` (ADR-007, `02-interfaces.md#time-and-units` rule 2). T01 section 3.7 shows that on the aligned grid the widened antecedent is true at two consecutive steps per anchor and fixes the anchoring convention: one obligation instance per anchor, evaluated once at `k_d`. Section 1.5 states the relation between the strings of SCHED and RESP (which carry the widened antecedent) and that reference semantics, together with the assumptions (A1), (A2) and, for RESP, (A3) under which they coincide.

### 6.6 Decomposition and wording (R1 weakness 8)

The library tags each template with its conjunct: RANGE, SCHED, HOLD, COUNT, RESP are phi_CP; SYS is phi_SYS; INT is phi_INT (section 3.1, `kind`). "phi_CP" is used only for constraints derived from the patient care plan. A violation always names its conjunct; a violated SYS instance is a violation of phi_SYS, and a device fault is not a violation of the care plan. The attributed causes C1, C2, C3 and UNDETERMINED are values of kappa in the alert tuple and are not violations. The dispense event is DISPENSE (dispenser opened), never intake: INTAKE is produced only by the robot witness (ADR-004), and `intake` never derives from `dispense`. In the workshop paper phi_HW and phi_DOSE appear only in a table caption; here phi_SYS is SYS with a formula, and the dose constraint is COUNT with a formula.

## 7 Golden examples

The golden file is `docs/formal/golden/templates.yaml`. Format: `fixture_registry` (the F0 table of the WS01 README, row for row, with the verbatim cells and the parsed values) and `cases`, exactly 26 in the order below, each with `id`, `contract`, `source`, `fixture`, `inputs`, `eval_at_ms`, `expected` and the hand calculation, in the format of the README. Extra keys inside `inputs` (`template`, `anchor_ms`, `anchor_kind`, `generated`, `channels_unavailable`) and `expected` (`guard_failed`, `workshop_form`) are additions of this file and are listed in its header. Times are integer milliseconds. Infinite values are `-.inf`. `step_ms = 60000` and `reorder_delay_ms = 0` in all cases; sigma-tilde is `clip(sigma / scale, -1, 1)` with the scale of the template; "sat" and "viol" are Boolean verdicts and a tie (`sigma = 0`) is satisfied for non-strict predicates.

**Verification.** Each case was computed by hand (the arithmetic is written out in the file) and reproduced by two independent paths in a script that is not committed: a parser and evaluator of the grammar of section 1.2 applied to the strings of section 3.1 over the whole grid trace (interval semantics, integer arithmetic, ceiling rule, half-open 24 h window, anchoring), and a direct per-instance formula per template. The outputs are quoted in the completion note of the task file. Two facts on fixtures: in G-RESP-1 to G-RESP-4 a pre-dose measurement (150 mmHg at 06:55) is part of the inputs because `pre_i` needs it; in G-INT-1 and G-INT-2 a `presence = 0` sample follows the observation by one step, because `presence` is a held level (section 4.7).

| id | Inputs (fixture) | sigma raw | sigma-tilde | Boolean |
|---|---|---|---|---|
| G-RANGE-1 | measurement 09:00, bp 125 | +15 mmHg | 0.75 | sat |
| G-RANGE-2 | measurement 09:05, bp 152 (analisi §4.6 row 08:55, 140 - 152) | -12 mmHg | -0.6 | viol |
| G-RANGE-3 | bp 104 | -6 mmHg | -0.3 | viol |
| G-RANGE-4 | bp 140 (boundary) | 0 | 0 | sat (tie) |
| G-RANGE-5 | bp 200 | -60 mmHg | -1 (clipped) | viol |
| G-COUNT-1 | dispenses 07:00, 21:00, 21:02; `c_d` = 3 at 21:02 | -1 dose | -1.0 | viol |
| G-COUNT-2 | dispenses 07:00, 21:00; `c_d` = 2 at 21:00 | 0 | 0 | sat (tie) |
| G-COUNT-3 | one dispense 07:00; day end at `K` | -1 dose | -1.0 | viol |
| G-HOLD-1 | measurement 20:35 bp 128; dispense 21:00 | +28 mmHg | 1.0 (clip of 1.4) | sat |
| G-HOLD-2 | measurement 06:50 bp 94; dispense 07:00 | -6 mmHg | -0.3 | viol |
| G-HOLD-3 | measurements 06:15 bp 120 and 06:55 bp 90; dispense 07:00 | refined -10 mmHg; workshop +20 mmHg | refined -0.5; workshop 1.0 | refined viol; workshop sat |
| G-HOLD-4 | last measurement 05:30; dispense 07:00 (age 90 min) | -inf, guard `no_recent_measurement` | -1 | viol |
| G-RESP-1 | dispense 07:00, `pre` 150; measurement 08:30 bp 132 (drop 18) | +8 mmHg | 0.4 | sat |
| G-RESP-2 | same dose; measurement 08:30 bp 145 (drop 5) | -5 mmHg | -0.25 | viol |
| G-RESP-3 | same dose; measurements 08:30 bp 145 and 09:30 bp 138 (drops 5, 12) | +2 mmHg | 0.1 | sat |
| G-RESP-4 | same dose; measurements only at 07:45 and 10:30 | -inf, guard `obligation_unmet` | -1 | viol |
| G-SCHED-1 | tick 09:00, `sched_window` 30 min; measurement 09:05 | +1500000 ms | 0.8333 | sat |
| G-SCHED-2 | measurement 09:30 (on the deadline) | 0 | 0 | sat (tie) |
| G-SCHED-3 | measurement 09:51 (21 min late), evaluated at 09:51 | -1260000 ms | -0.7 | viol |
| G-SCHED-4 | measurement only at 08:50 (before the tick) | -inf, guard `no_measurement_after_tick` | -1 | viol |
| G-SYS-1 | `cuff_health` 1, `inflation_ms` 45000 | +15000 ms | 0.5 | sat |
| G-SYS-2 | `cuff_health` 1, `inflation_ms` 9000 | -21000 ms | -0.7 | viol |
| G-SYS-3 | `cuff_health` 0, `inflation_ms` 45000 | -inf, guard `cuff_unhealthy` | -1 | viol |
| G-INT-1 | presence 06:58; dispense 07:00; no auth | +180000 ms | 0.6 | sat |
| G-INT-2 | presence 06:52 (age 8 min); dispense 07:00; no auth | -180000 ms | -0.6 | viol |
| G-INT-3 | dispense 21:00 with `auth` at 21:00; robot channels unavailable | +300000 ms | 1.0 | sat |

G-SCHED-1 follows from the definitions of sections 1.5 and 2.3 (`k_a = 540`, `k_d = 570`, slack `(570 - 545) * 60000 = 1500000`); G-COUNT-2 follows from the trailing window of T01 section 5.1 and the counter margin of section 4.4 (`2 - 2 = 0`). No definition of sections 1 and 2 had to be changed to reproduce a golden value. The value of G-SCHED-3 is the graded lateness of section 2.3, observable from the step 09:51; at the decision step 09:30 the value is `-inf` with the guard `no_measurement_after_tick`.

## 8 Paper excerpt (Section IV-A, Table I)

Sized to 0.5 page (analisi §7). Table I is wide (formulas with a nested interval) and is set as a two-column float (`table*`) in the final layout; at the 6-page limit this costs space in the 0.5-page budget, to be re-checked by WS12. Table I replaces the workshop table of numbers (analisi §4.6) with the formula, unit, scale and priority of each template. The scale and priority columns are registry entries assigned by the clinician; their values are not fixed here. The alert tuple in the text is a placeholder to be replaced by the definition of WS01-T07.

```latex
\subsection{Specification Templates}
\label{sec:templates}

The specification is a library of seven past-time STL templates over the signals of Section~\ref{sec:problem} (Table~\ref{tab:templates}).
A template is evaluated per \emph{instance}: an anchor event (a measurement, a dispense, a schedule tick, the end of the day) opens an instance, and its body is evaluated once at the decision step, so the definitive verdict is decidable, in event time, within the deadline offset plus one monitor step of the anchor; the end-to-end latency adds the reorder delay.
Templates $\varphi_{\mathrm{range}},\varphi_{\mathrm{sched}},\varphi_{\mathrm{hold}},\varphi_{\mathrm{count}},\varphi_{\mathrm{resp}}$ constrain the patient care plan ($\varphi_{\mathrm{CP}}$), $\varphi_{\mathrm{sys}}$ the health of the cuff node ($\varphi_{\mathrm{SYS}}$), and $\varphi_{\mathrm{int}}$ the provenance of a dispense ($\varphi_{\mathrm{INT}}$).

\textbf{One margin per template.}
Each template has exactly one margin dimension, its unit (mmHg, ms or dose); every other atom is a guard, equal to $+\infty$ when true and $-\infty$ when false.
The raw robustness $\sigma$ is therefore expressed in one unit, and a failed guard (no measurement in the response window, an unhealthy cuff, no witness) is reported as such, with $\tilde\sigma=-1$, instead of as a number.
Timing constraints use a time margin, the slack to the far edge of the window: for $\varphi_{\mathrm{sched}}$ the deadline slack of the first measurement after the tick, for $\varphi_{\mathrm{int}}$ the window minus the age of the latest witness.
Counters are derived signals, so $c_d\le N$ is an atomic predicate with margin $N-c_d$ in doses, and the pre-dose reference $bp^{\mathrm{pre}}$ is a derived signal captured per instance at the dispense.
The normalised value is $\tilde\sigma=\mathrm{clip}(\sigma/s,-1,1)$ with a clinician-assigned scale $s$ per template.

\textbf{Obligations.}
$\varphi_{\mathrm{resp}}$ is satisfiable only if a measurement falls in $[t_d+\Delta_1,t_d+\Delta_2]$, and $\varphi_{\mathrm{int}}$ only if a witness precedes the dispense, so the specification induces measurement and witness tasks for the assistive robot; the deadlines of these tasks are what the forecaster predicts (Section~\ref{sec:predictive}).
All numerical values are illustrative and unverified; validation is technical and pre-clinical.

\begin{table*}[t]
\caption{Specification templates. $\square$ is evaluated on the observed prefix; $\mathrm{O}_{[a,b]}$ is once. Scales $s_\pi$ and priorities $p_\pi$ are registry entries assigned by the clinician; the parameters $b_{lo},b_{hi},b_h,L,W,N_{\max},N_{\min},\Delta_1,\Delta_2,\delta,q_{\min},T_{\mathrm{int}}$ are registry entries whose values are illustrative and unverified.}
\label{tab:templates}
\centering\small
\begin{tabular}{@{}llccc@{}}
\toprule
Template & Formula & Unit & Scale & Priority\\
\midrule
$\varphi_{\mathrm{range}}$ & $\square\,(m\rightarrow b_{lo}\le bp\le b_{hi})$ & mmHg & $s_{\mathrm{range}}$ & $p_{\mathrm{range}}$\\
$\varphi_{\mathrm{sched}}$ & $\square\,(\mathrm{O}_{[W,W+T_s]}\,s\rightarrow \mathrm{O}_{[0,W]}\,m)$ & ms & $s_{\mathrm{sched}}$ & $p_{\mathrm{sched}}$\\
$\varphi_{\mathrm{hold}}$ & $\square\,(d\rightarrow(\mathrm{O}_{[0,L]}\,m\wedge bp\ge b_h))$ & mmHg & $s_{\mathrm{hold}}$ & $p_{\mathrm{hold}}$\\
$\varphi_{\mathrm{count}}$ & $\square\,(d\rightarrow c_d\le N_{\max})\wedge\square\,(e_{\mathrm{day}}\rightarrow c_d\ge N_{\min})$ & dose & $s_{\mathrm{count}}$ & $p_{\mathrm{count}}$\\
$\varphi_{\mathrm{resp}}$ & $\square\,(\mathrm{O}_{[\Delta_2,\Delta_2+T_s]}\,d\rightarrow \mathrm{O}_{[0,\Delta_2-\Delta_1]}(m\wedge r\ge\delta))$ & mmHg & $s_{\mathrm{resp}}$ & $p_{\mathrm{resp}}$\\
$\varphi_{\mathrm{sys}}$ & $\square\,(m\rightarrow h_c=1\wedge q\ge q_{\min})$ & ms & $s_{\mathrm{sys}}$ & $p_{\mathrm{sys}}$\\
$\varphi_{\mathrm{int}}$ & $\square\,(d\rightarrow \mathrm{O}_{[0,T_{\mathrm{int}}]}(w\vee a_{\mathrm{auth}}))$ & ms & $s_{\mathrm{int}}$ & $p_{\mathrm{int}}$\\
\bottomrule
\end{tabular}
\end{table*}
```

## 9 Open points for WS01-T08

Each item gives the anchor, the resolution adopted or proposed, and whether an ADR is needed. None edits `02-interfaces.md`.

**CP1 (`02-interfaces.md#template`, `creates_robot_obligation`).** Resolution adopted (section 5.5): True for SCHED, RESP and INT. Reason: analisi §10 objection 3 derives the witness obligation from phi_INT. The contract comment lists only RESP and SCHED. ADR: a small one (clarify the comment; the field values follow ADR-021 item on `creates_robot_obligation`).

**CP2 (`02-interfaces.md#template`, `#signals`; measurement count).** Resolution adopted (section 4.4): the day-end measurement count is not part of COUNT. COUNT is the dose count with the unit `dose`; a measurement count needs a measurement unit that `RobustnessUnit` lacks, would give COUNT two margin dimensions, and duplicates the SCHED instances (the cascade of analisi §4.6 row 15:00). `meas_min_day` and `MEAS_COUNT` remain declared and unused by the seven templates. ADR: only if the obligation is adopted, in which case a new template id and unit are required (contract change).

**CP9 (no contract for the robot obligation record).** Resolution adopted (section 5.2): document-level record with nine fields, creation rules (section 5.3) and load-time feasibility checks (section 5.4). Proposed: a new contract `#robot-obligation` (owner WS01, consumer WS07-T04). ADR: yes (new contract).

**CP11 (`02-interfaces.md#template`, one `unit` and one `scale_param` per template).** Resolution adopted (section 2.1): exactly one margin dimension per template, every other atom is a guard (`+-inf`), a failed guard gives raw `-inf`, normalised `-1` and the marker `guard_failed: <name>`. `unit` and `scale_param` refer to the margin dimension. No signature change; ADR: clarification only (one sentence in the contract text), at the discretion of WS01-T08.

**TG-1 `CarePlan.schedule` has no tick kind (`#template`).** It is a `Sequence[TimeMs]` of measurement and dispense ticks. Checks F2 to F5 and the creation of SCHED and INT obligations need to know which is which. Proposed: `schedule` becomes a sequence of `(TimeMs, TickKind)` or two sequences. ADR: yes.

**TG-2 `Template` has no fields for anchor, deadline offset and guard names (`#template`).** The monitor needs, per template, the anchor signal, the offset `B` (section 3.2) and the list of guard markers (section 2.1), and the per-instance terms (`age`, `pre_i`). Proposed: keep them in the implementation table of WS05 (they follow from this document) and not in the contract, or extend `Template` with an ADR. The `signals` field lists only signals mentioned in the string.

**TG-3 `max_verdict_latency_param` is a "registry entry" (`#template`).** Declared here as a derived value (section 3.2), not a free parameter, as the task requires. The registry loader must resolve derived names. Which latency (event-time `B + T_s` adopted here, or end-to-end with `D`) the monitor reports is T01 CG-4 and belongs to WS01-T05. ADR: with CP10 (registry).

**TG-4 Graded lateness after the decision step (SCHED, section 2.3).** The value of an instance decided VIOLATED with no observation is `-inf`; a later measurement grades it (G-SCHED-3, `-1260000` ms, from step 09:51) without changing the state. WS01-T05 and WS01-T07 decide whether a second, refined record is emitted (a value refinement is not a retraction of the verdict, T01 section 3.7) and whether the grade is used in the alert. The evaluation horizon (next tick of the same schedule, or the closing step) is proposed here.

**TG-5 The `age` term and the tool string (section 1.4).** `age` is a freeze-like term added to `formula_past_time`: it reads the distance between the step of the enclosing temporal operator and the step of the witness, which is what STL with a freeze operator provides. The contract says the string is "RTAMT-compatible" and ADR-007 says the freeze operator is not implemented, so the term is a tension with both. To be checked by the WS05-T02 spike (ADR-013, `[DA-CONFERMARE]`): if `age` cannot be expressed with operators available in the spike (a per-instance derived signal, or the Boolean skeleton of section 1.4 for the verdict only), an ADR is needed, either to admit the term (or a freeze operator) in `formula_past_time` or to drop `age` from the string and keep the margin in the per-instance evaluator. The Boolean skeleton is equivalent to the string for SCHED and for INT only with the bounded window `once[0, int_window]` (section 1.4); the rule "replace `age` atoms by `true`" is unsound for INT. `age` is not a `SignalId` and is not defined in `docs/formal/01-signals-sampling.md`: WS01-T08 check (c) (consistency of the signals used by the templates with T01) must be told that `age` is an instance term of this document, listed in neither the signal table nor the derived signals of T01.

**TG-6 String versus reference semantics for SCHED and RESP (T01 CG-2, section 1.5).** The strings carrying the widened antecedent coincide with the reference semantics under (A1) and (A2) for SCHED, and under (A1), (A2) and (A3) for RESP (A3: no other dispense visible in the steps `k_a, ..., k_d + 1` of the instance, or evaluation with the per-instance `bp_drop`; the string uses the global `bp_drop` stream and the reference semantics uses `pre_i`). Under (A3) the string is never weaker than the reference semantics; without (A3) the relation fails in either direction (random check of section 1.5: 102 of 1927 traces). Without (A2) the strings report a violation at `k_d + 1` when the instance is satisfied, its only qualifying observation lies at the first step `E` of the window and there is no qualifying observation at `k_d + 1`. Proposed: WS05 implements the reference semantics (per-instance `pre_i`) and treats the string as a tool form; WS01-T05 states the equivalence proof (A7) with (A2) and (A3); the plan feasibility checks may exclude overlapping doses (dispense ticks closer than `delta2 + T_s`) or the monitor must evaluate RESP per instance. WS01-T08 decides whether an ADR should record that the widening is redundant on the aligned grid. The B = 0 templates coincide with the reference semantics under (A0) (at most one measurement per bin for RANGE and SYS, section 1.5).

**TG-7 HOLD refined form (section 4.3).** Recommended and used: refined form with recency as a guard. It changes a workshop formula, so it needs confirmation at the clinician review (WS00-T07) and the freeze. ADR: recommended (a decision on a formula of the paper).

**TG-8 INT direction and forward witness (T01 CG-7, sections 4.7 and 5.3).** Resolved: look-back at the dispense step, `intake` kept in the disjunction (M1) although in a look-back window it can only come from an earlier dose. Deviation from the task text: the INT obligation is static from the dispense ticks, not dynamic at each DISPENSE (section 5.3, reason: the window closes at the dispense). Open design question: whether to add a forward witness obligation after each dispense (to obtain the INTAKE evidence of ADR-004 for the attribution of double takes, bounces and forged events) and whether it belongs in INT or in evidence collection (WS02). ADR: with the answer.

**TG-9 `presence` as a held level (T01 section 2.1, CG-6).** The age of a witness is the time since the last step with `presence = 1`, so a witness that has left needs an explicit `0` sample (G-INT-1, G-INT-2). If the robot node instead emits `presence` only while it observes the patient, the trace needs the availability mask of T01 CG-6 or an event kind. WS02 and WS05-T02.

**TG-10 `normalise` and infinities (`#template`).** The contract text gives `clip(sigma_raw / scale, -1, 1)` and says nothing about `+-inf`. Convention used (section 2.5): `+-inf` maps to `+-1`, and the marker `guard_failed` distinguishes a failed guard from a clipped finite value. WS01-T04 confirms; WS01-T07 puts the marker in the alert record.

**TG-11 Ties and strictness (CP3).** All atoms are non-strict; a tie is satisfied (G-RANGE-4, G-COUNT-2, G-SCHED-2). WS01-T05.

**TG-12 COUNT limit with a trigger (section 4.4).** The limit is stated with `dispense ->`, equivalent in value to the workshop `historically(c_d <= limit)`. Persistence of the violation over steps (T01 CG-14) is WS01-T05 and WS01-T07.

**TG-13 RANGE during drug onset (section 4.1).** Analisi §4.6 row 08:55 asks whether the band applies during the onset of the drug. The library applies it at every measurement. Clinical question for WS00-T07.

**TG-14 Fixture choices in the golden file.** The bp values of the measurements that do not affect the result (G-HOLD-4 at 05:30, G-RESP-4 at 07:45 and 10:30) and the pre-dose measurement of G-RESP-1 to G-RESP-4 (150 mmHg at 06:55), the `presence = 0` samples of G-INT-1 and G-INT-2 and the unavailable robot channels of G-INT-3 are fixture choices, not clinical statements. G-SCHED-3 is evaluated at 09:51 (section 2.3). The F0 fixture-only rows must not be copied into the clinical registry.

**Touch points with WS01-T01 (respected, not overridden).** M1 (`w` as a three-valued disjunction of `presence` and `intake`) is used by INT; M2 (`T_s` divides `T_day`) by the day-end case; M5 (a measurement with the dispense's device time counts as pre-dose) by HOLD and RESP; M6 (an instance belongs to the day of its anchor) by RESP and INT windows crossing midnight. CG-2 (widening) is answered in section 1.5; CG-3 (deadline `t_{k_up(a)} + B`) is adopted for `deadline_ms`; CG-4 (latency) is adopted as the event-time bound pending WS01-T05; CG-6 (unavailability mask) and CG-9 (CP6, undecidable witness after the deadline) are assumed by INT and left to WS01-T05; CG-7 (INT direction) is resolved in section 4.7; CG-14 (persistent counter violation) is noted in section 4.4.

**Other tension found.** The claim "a single monitor handles all three classes" (workshop paper Section III-A) conflates the clinical and the system specification (R1 weakness 8); this document keeps phi_CP, phi_SYS and phi_INT as separately evaluated conjuncts with their own unit, scale and priority, and takes no minimum across them.
