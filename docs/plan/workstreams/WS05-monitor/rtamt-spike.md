# RTAMT spike (WS05-T02, closes the tool side of R1-W10 and decides ADR-013)

Question: can RTAMT host the seven past-time templates of `docs/formal/02-templates.md` so that it is the point-robustness engine of `ralmon.monitor` (outcome A), an oracle and the engine of baseline B3 (outcome B), or neither (outcome C)? Technical, pre-clinical work: every number below is fixture arithmetic of the golden file `docs/formal/golden/templates.yaml` (registry F0, `step_ms = 60000`), not a clinical value.

Every statement below is backed by a command that was run and whose output is pasted, or by a source file of the installed package that was read (path given). What was not tested is listed in the last section of `## Decision`. The script is `tools/rtamt_spike.py` (plain Python, no network, no wall-clock time, no randomness); `python tools/rtamt_spike.py --detail` prints the tables quoted here.

## Environment

| Item | Value | Command |
|---|---|---|
| RTAMT resolved | 0.4.10 (with `antlr4-python3-runtime` 4.7) | `uv pip install --python /tmp/rtamt-venv312/bin/python rtamt pyyaml numpy` printed `+ rtamt==0.4.10`, `+ antlr4-python3-runtime==4.7` |
| Python used for the results | 3.12.8 (throwaway venv under `/tmp`, outside the repository) | `uv venv /tmp/rtamt-venv312 --python 3.12` printed `Using CPython 3.12.8` |
| Python of the project container | 3.12.15 (`ralmon-dev`) | `docker compose run --rm -T --entrypoint bash dev -c "python --version"` printed `Python 3.12.15` |
| Host Python | 3.14.4 (`.venv`; `rtamt` not installed there, and not added to `[project] dependencies`) | `python --version` |

Python 3.14.4 cannot import RTAMT 0.4.10. Command and last lines of the output:

```text
$ uv venv /tmp/rtamt-venv --python 3.14 && uv pip install --python /tmp/rtamt-venv/bin/python rtamt
 + antlr4-python3-runtime==4.7
 + rtamt==0.4.10
$ /tmp/rtamt-venv/bin/python -c "import rtamt"
  File "/tmp/rtamt-venv/lib/python3.14/site-packages/antlr4/Lexer.py", line 12, in <module>
    from typing.io import TextIO
ModuleNotFoundError: No module named 'typing.io'; 'typing' is not a package
```

The cause is the pinned ANTLR runtime 4.7, which imports `typing.io`. I did not test whether a newer ANTLR runtime would work with RTAMT 0.4.10, and I did not test other RTAMT versions. Consequence for the project: the Python of the repository (3.14.4) cannot run an RTAMT-based path; the project container (3.12) can.

The container has no network (`pip install rtamt` there printed `ERROR: No matching distribution found for rtamt`). The container run therefore used the pure-Python packages `rtamt` and `antlr4` copied from the 3.12.8 venv onto `PYTHONPATH`. Its report equals the host 3.12.8 report line by line:

```text
$ diff <(grep -v "^Python" host312_detail.txt) <(grep -v "^Python" container_detail.txt) && echo IDENTICAL
IDENTICAL
```

Default output of the script in the repository environment (`.venv`, Python 3.14.4, no RTAMT) and in the 3.14 venv with RTAMT installed but not importable:

```text
RTAMT version: NOT-INSTALLED
Q1 NOT-RUN past-time operators: rtamt is not installed
...
RTAMT version: 0.4.10
Q1 NOT-RUN past-time operators: import rtamt failed: ModuleNotFoundError: No module named 'typing.io'; 'typing' is not a package
```

Both exit with code 0 and print six question lines. Summary of the run that produced the results (Python 3.12.8, RTAMT 0.4.10):

```text
Q1 FAIL past-time operators: 4 of 7 templates translate mechanically and equal the goldens; not: sched, sys, int (age term, == atom)
Q2 PASS sparse sampling: fixed-step interface fed from the monitor grid; timestamps are only audited (counter 0 on the grid, 1260 when jittered, values unchanged); unaligned bounds rejected; ...
Q3 NOT-SUPPORTED robustness intervals: update() returns one float for every Semantics member: point values only, intervals need custom code; endpoint evaluation is unsound for range, count (coincident triggers) and sys (multi-valued status)
Q4 FAIL guards and infinities: infinities propagate exactly when the host feeds +-inf indicators, but the atoms do not apply the guard rule (== is -|a-b|) and NaN is silently absorbed or read as a verdict
Q5 FAIL time robustness: not native; with a derived time signal tau and arithmetic over a sub-formula 8 of 10 time-margin goldens are equal; differs: G-SCHED-3, G-INT-3 (...)
Q6 PASS cost per sample: operator updates per step are linear in the number of instances (6 per instance); a timed once or historically scans its whole window at every step, so the cost per update is O(window), not O(1)
```

Method. The golden cases are turned into grid signals with `ralmon.signals` (`event_to_sample`, `hold_last`, `impulses_on_grid`, the derived signals `dose_count` and `bp_drop`, all fed with every sample and event in device-time order). Indicators are encoded `+inf` (impulse or level 1) and `-inf` (otherwise), the encoding of the atoms in `02-templates.md` section 1.3; held values are NaN before their first sample; a counter that has produced no output reads 0. The RTAMT value at the evaluation step of the case is compared with `expected.sigma_raw` within 1e-9, or for the same infinity. The template strings are read from the table of `02-templates.md` section 3.1 and translated syntax-directed: registry names are replaced by their F0 values, `once[a, b]` and `historically[a, b]` get explicit `ms` units, `once[0, inf]` is written `once`; nothing else is rewritten.

Two facts about the RTAMT interface were needed to get correct results and are recorded because the documentation is misleading on the first:

```text
$ (probe in tools/rtamt_spike.py, Q2 detail lines)
  Q2 bare bound 'once[0,120000]' with spec.unit = 'ms': the impulse of step 0 is forgotten never within 6 steps (a 120000 ms window at a 60000 ms period is forgotten at step 3)
  Q2 bare bound 'once[0,120000]' with spec.ast.unit = 'ms': the impulse of step 0 is forgotten at step 3 (...)
  Q2 bare bound 'once[0,120000]' with no unit set: the impulse of step 0 is forgotten never within 6 steps (...)
```

The README of the installed distribution (`rtamt-0.4.10.dist-info/METADATA`, section "Working with time units") shows `spec.unit = 'ms'`; in 0.4.10 that sets an attribute of the specification object but not the unit that the interpreter reads (`rtamt/syntax/ast/parser/abstract_ast_parser.py` line 89 sets `self.unit = 's'` on the AST; `rtamt/semantics/discrete_time_interpreter.py` line 112 reads `self.ast.unit`). A bare bound is then read in seconds. The script avoids the problem by writing the unit on every bound (`once[0ms,1800000ms]`). Second, the precedence of the arithmetic operators differs from that of the other operators (Q1).

## Q1 Past-time operators

Result: FAIL (4 of 7 templates translate mechanically and equal the goldens).

| Template | Mechanical translation | Value equals the golden `sigma_raw`? | Why |
|---|---|---|---|
| `range` | yes | yes, 5 of 5 | none |
| `hold` | yes | yes, 4 of 4 (G-HOLD-3 gives -10, the refined form; G-HOLD-4 gives exactly `-inf`) | none |
| `count` | yes | yes, 3 of 3 | none |
| `resp` | yes (global `bp_drop` stream) | yes, 4 of 4 (G-RESP-4 gives exactly `-inf`) | the goldens have one dispense, so assumption (A3) of `02-templates.md` 1.5 holds |
| `sys` | yes | no: G-SYS-1 gives `-0` (golden 15000), G-SYS-3 gives `-1` (golden `-inf`); G-SYS-2 equals | the atom `cuff_health == 1` is `-abs(x - 1)` in RTAMT, not `+inf` or `-inf` (guard rule, Q4) |
| `sched` | no | not computable | the string contains `age`, a function of the inner step and the evaluation step; RTAMT variables are functions of one step |
| `int` | no | not computable | same reason (`age <= int_window`) |

The rows of this table come from these lines of `python tools/rtamt_spike.py --detail`:

```text
  Q1 template range: literal translation equal on all goldens
  Q1 template sched: literal translation not expressible (age)
  Q1 template hold: literal translation equal on all goldens
  Q1 template count: literal translation equal on all goldens
  Q1 template resp: literal translation equal on all goldens
  Q1 template sys: literal translation differs on G-SYS-1, G-SYS-3
  Q1 template int: literal translation not expressible (age)
```

Translated strings (output of the translator, F0 values):

```text
resp   historically(once[10800000ms,10860000ms] dispense -> once[0ms,7200000ms] (meas and bp_drop >= 10))
sys    historically(meas -> (cuff_health == 1 and inflation_ms >= 30000))
sched skeleton   historically(once[1800000ms,1860000ms] sched_tick -> once[0ms,1800000ms] meas)
int   skeleton   historically(dispense -> once[0ms,300000ms] (presence or intake or auth))
```

The Boolean skeletons of `02-templates.md` section 1.4 translate and agree in sign with the goldens in 6 of 7 cases (G-SCHED-1 to G-SCHED-4, G-INT-1, G-INT-2; the failing case is G-INT-3, where the robot channels are unavailable and fed as NaN, see Q4). A skeleton carries the verdict only, not the margin.

Precedence probe (the string `once[a,b] meas and bp >= x` of HOLD is read as `(once meas) and (bp >= x)` by RTAMT, which is the reading of the document, because G-HOLD-3 gives -10; but arithmetic binds tighter than a temporal operator):

```text
  Q1 precedence probe 'once[0ms,60000ms] a + b' on a=[5.0, 1.0, 1.0, 1.0] b=[0.0, 10.0, 20.0, 30.0]: [5.0, 11.0, 21.0, 31.0]
  Q1 precedence probe '(once[0ms,60000ms] a) + b' on a=[5.0, 1.0, 1.0, 1.0] b=[0.0, 10.0, 20.0, 30.0]: [5.0, 15.0, 21.0, 31.0]
```

`once a + b` is `once (a + b)`. This is why the hand rewrites of Q5 put the temporal sub-formula in parentheses or on the right of the `+`.

Operators of the fragment used: `historically` (untimed), `once` (timed and untimed), implication `->`, `and`, `or`, comparison atoms. All parse. `once[0,inf]` is rejected (`  Q1 unbounded bound 'once[0,inf] meas': RTAMTException: RTAMT Exception: Bound inf not declared`); the untimed `once` is the equivalent. `since` is not used by any template and was not exercised.

## Q2 Sparse sampling

Result: PASS (with a precise meaning).

```text
  Q2 grid feed (range, hold, count, resp, literal strings): 16 of 16 golden evaluations equal
  Q2 G-HOLD-1 grid timestamps: sampling_violation_counter=0; jittered timestamps (deterministic, up to 30 s): counter=1260, values identical=True
  Q2 bound 90500 ms with a 60000 ms period: rejected at first update: RTAMTException: RTAMT Exception: The operator bound must be a multiple of the sampling period
```

How the interface is fed. `StlDiscreteTimeSpecification` is a fixed-step interface: `update(timestamp, [(name, value), ...])` takes one value per declared variable per step. The monitor grid of `02-interfaces.md#time-and-units` rule 1 suffices: the script builds the arrays with `hold_last` (held values) and `impulses_on_grid` (impulses, ceiling rule) and calls `update(k * 60000, ...)` for `k = 0 .. K`. Irregular timestamps are not needed. In `rtamt/semantics/abstract_discrete_time_online_interpreter.py` the timestamp is used only to increment `sampling_violation_counter` (read from that file); the jittered run above gives the same values with a counter of 1260, so timestamps are audited, not used in the evaluation. RTAMT therefore offers no sparse or irregular-time evaluation; the hold of the sparse data stays in `ralmon.signals`.

Alignment. RTAMT rejects a bound that is not a multiple of the sampling period (above), at the first `update` and not at `parse`. The rule agrees with the alignment of window parameters of `01-signals-sampling.md` section 3.6 (W7: 90,500 is rejected, 1,800,000 accepted); the check of a care plan at load remains the monitor's (`Monitor.load`, CG-12), with an error that names the parameter.

Limits of this answer: only the Python implementation was tested; the optional C++ backend (`StlDiscreteTimeOnlineSpecificationCpp`) and the dense-time interface were not.

## Q3 Robustness intervals

Result: NOT-SUPPORTED.

```text
  Q3 type returned by update(), per Semantics member: {'standard': 'float', 'output-robustness': 'float', 'input-vacuity': 'float', 'input-robustness': 'float', 'output-vacuity': 'float'}
  Q3 rtamt.semantics.interval.Interval stores integer time bounds (begin, end, begin_unit, end_unit), not robustness bounds
```

`update` returns a single float for every member of `rtamt.Semantics` (the interface-aware variants included; I called each on the trivial formula `historically(x >= y)` only). The only class named `Interval` in the package (`rtamt/semantics/interval/interval.py`) holds time bounds. I did not search for an interval API outside the Python package or in other versions.

Procedure that obtains intervals from point evaluations. For a prefix whose unknown future signal `u` ranges in `[u_lo, u_hi]`, evaluate the formula with `u` at each bound; the two values are the bounds of the robustness interval only if the formula is monotone in `u` (then the lower bound is the evaluation at the bound that minimises the value, the upper bound at the other). Checks with RTAMT point values, by template (probes run by `--detail`; "scan" is a finite scan over the listed values on one golden fixture, a check and not a proof; the direction is also read from the formulas: `min`, `max`, `once` and `historically` are monotone, an implication is antitone in its antecedent, `x >= c` is increasing in `x`):

| Template | Unknown signal | Monotone? | Evidence |
|---|---|---|---|
| `range` | `bp` | NO | counterexample below |
| `sched` | future `meas` impulse | yes, non-decreasing (the `sched_tick` comes from the plan, not unknown) | scan over `-inf`, `+inf` on the skeleton: non-decreasing |
| `hold` | `bp`; `meas` | yes, both non-decreasing | scan over 201 integer pressures; scan over `-inf`, `+inf` |
| `count` | `dose_count` | each conjunct is monotone (limit: non-increasing; day-end: non-decreasing); the whole formula is NOT when a dispense and `day_end` coincide | counterexample below |
| `resp` | `meas`; `bp_drop` (so the later `bp` is non-increasing) | yes | scan over 41 drop values and over `-inf`, `+inf`; the per-instance reference `bp_pre` was not scanned |
| `sys` | `inflation_ms`; `cuff_health` | `inflation_ms` yes (scan); `cuff_health` NO if the status takes values other than 0 and 1, yes if Boolean | counterexample below |
| `int` | `auth` (and `presence`, `intake`) | yes, non-decreasing | scan over `-inf`, `+inf` for `auth` on the skeleton; `presence` and `intake` were not scanned (same `or`) |

Counterexamples (RTAMT values, fixture bounds):

```text
  Q3 range, unknown bp in [50, 250]: endpoint values [-110, -60], scan over all integer values [-110, 15] -> endpoint rule UNSOUND (upper bound too low)
  Q3 count (dispense and day_end at step 1440), unknown dose_count in [0, 5]: endpoints [-3, -2], scan [-3, 0] -> endpoint rule UNSOUND
  Q3 sys, unknown cuff_health in [0, 2] (equality guard): endpoints ['-inf', '-inf'], scan ['-inf', '-inf', '15000', '-inf', '-inf'] -> endpoint rule UNSOUND (healthy interior value missed)
```

The physiological bounds 50 and 250 are the F0 values of `bound_bp_lower` and `bound_bp_upper` (analisi §4.7, illustrative, unverified); the range `[0, 5]` for the counter is fixture-only. Conclusion: RTAMT gives point values; the interval layer (WS05-T04) is custom code, and for `range` (clamp the unknown pressure into the band to reach the maximum), `count` (treat the two conjuncts separately) and `sys` (a Boolean status) the two-bound evaluation must not be used as is.

## Q4 Guards and infinities

Result: FAIL (infinities are carried, the guard rule and the unknown value are not).

```text
  Q4 infinite goldens (failed guards) reproduced exactly: ['G-HOLD-4', 'G-RESP-4'] of ['G-HOLD-4', 'G-RESP-4', 'G-SYS-3']
  Q4 vacuous truth (no anchor) is exactly +inf: inf
  Q4 native equality atom 'cuff_health == 1' on healthy, 0, 2: ['-0', '-1', '-1'] (guard rule of 02-templates.md 2.1 would give +inf, -inf, -inf)
  Q4 range with a measurement and an unknown (NaN) pressure: -inf (T01 3.5 requires unknown, never a verdict)
  Q4 'presence or intake or auth' with unavailable robot channels (NaN) and auth=+inf: nan; operands reordered 'auth or presence or intake': inf (order-dependent)
```

1. RTAMT propagates `+inf` and `-inf` exactly through `min`, `max`, implication, `once` and `historically` when the host feeds indicators as `+inf` and `-inf` (a failed guard gives exactly `-inf`, no anchor gives exactly `+inf`).
2. RTAMT does not apply the guard rule to its own atoms: a bare variable is its numeric value and `x == c` is `-abs(x - c)`. The guard rule needs the host to compute `+inf` and `-inf` indicators first (the `guard indicator` variant of `sys` in Q5 does so and equals all three goldens).
3. RTAMT has no unknown value. Its operators are the Python `min` and `max` (read in `rtamt/semantics/stl/discrete_time/online/*_operation.py`, for example `max(-sample_left, sample_right)` for implication), so a NaN is dropped or kept depending on operand order; the two lines above show a NaN read as a violation (`-inf`) and a NaN in `or` that depends on the order of the operands. This contradicts `01-signals-sampling.md` section 3.5 (unknown is not false). Unavailable channels (G-INT-3) must be fed as `-inf`, which collapses "unavailable" into "false": the value then equals the golden, but only because `auth` decides.

## Q5 Time robustness

Result: FAIL (not native; a hand rewrite with a derived time signal reproduces 8 of 10 goldens).

`sched` and `int` use `age`, not expressible (Q1). The slack to the far edge (`02-templates.md` section 2.3) is linear in the grid times, so it can be obtained with a derived signal `tau` (the grid time in ms) and arithmetic over a sub-formula, as follows. Hand rewrites, not syntax-directed:

```text
sched   once[0, W] (meas and age >= 0)                         ->  (tau + once[0ms,1800000ms] (meas and (0 - tau)))
int     once[0, inf] ((presence or intake or auth) and age <= int_window)
                                                               ->  ((300000 - tau) + once ((presence or intake or auth) and tau))
sys     cuff_health == 1                                       ->  cuff_ok   (a +inf / -inf indicator computed by the host)
```

```text
  Q5 G-SCHED-1 [time-signal rewrite] expected 1.5e+06 got 1.5e+06 equal
  Q5 G-SCHED-2 [time-signal rewrite] expected 0 got 0 equal
  Q5 G-SCHED-3 [time-signal rewrite] expected -1.26e+06 got -inf DIFFERENT
  Q5 G-SCHED-4 [time-signal rewrite] expected -inf got -inf equal
  Q5 G-SYS-1 [guard indicator] expected 15000 got 15000 equal
  Q5 G-SYS-2 [guard indicator] expected -21000 got -21000 equal
  Q5 G-SYS-3 [guard indicator] expected -inf got -inf equal
  Q5 G-INT-1 [time-signal rewrite] expected 180000 got 180000 equal
  Q5 G-INT-2 [time-signal rewrite] expected -180000 got -180000 equal
  Q5 G-INT-3 [time-signal rewrite] expected 300000 got -inf DIFFERENT
  Q5 G-INT-3 [time-signal rewrite (unavailable fed as -inf)] expected 300000 got 300000 equal
```

The two differences are known and structural. G-SCHED-3 (graded lateness): the string is `-inf` at the decision step and the minimum over the history never recovers, whereas the golden value is the per-instance value defined in `02-templates.md` section 2.3; a late measurement can only be graded by per-instance evaluation. G-INT-3: the NaN of the unavailable robot channels (Q4). The `sys` margin is a threshold on a duration, not a slack, and needs no time signal, only the guard indicator. Conclusion: time-margin templates are obtained by the margin and guard rule on derived signals, not by RTAMT; the per-instance evaluator of WS05-T04 computes the slack directly.

## Q6 Cost per sample

Result: PASS for the number of operator updates (linear in the number of instances); the cost of one update is not O(1).

The counting wrapper replaces `update` of every operator object of each specification (`spec.online_interpreter.online_operator_dict`) and the window buffer of each timed operator by a counting object; no wall-clock time is used. Formula: the RESP string, 239 grid steps.

```text
  Q6   1 instances: operator updates per grid step 6 (6 per instance), timed-window buffer reads per step 123 (123 per instance)
  Q6  10 instances: operator updates per grid step 60 (6 per instance), timed-window buffer reads per step 1230 (123 per instance)
  Q6 100 instances: operator updates per grid step 600 (6 per instance), timed-window buffer reads per step 12300 (123 per instance)
  Q6 once[0, 30 steps]: buffer reads per update 31 (the whole window is scanned at each step)
  Q6 once[0, 120 steps]: buffer reads per update 121 (the whole window is scanned at each step)
  Q6 historically[0, 30 steps]: buffer reads per update 31 (the whole window is scanned at each step)
  Q6 historically[0, 120 steps]: buffer reads per update 121 (the whole window is scanned at each step)
```

Growth: the operator updates per step are exactly proportional to the number of instances (6, 60, 600), because RTAMT keeps one specification object per instance (an instance is evaluated separately; there is no sharing of state between instances). Inside one specification, the timed `once` and `historically` read `end - begin + 1` buffer entries at every update (`rtamt/semantics/stl/discrete_time/online/once_timed_operation.py` and `historically_timed_operation.py`, read and measured above), so the cost per update is O(window in steps), not O(1): 123 reads per step per instance for the RESP string with a 120-step window. The timed `since` (`since_timed_operation.py`) has nested loops over the window; this was read, not measured, and no template uses `since`. These are statements about RTAMT 0.4.10; nothing here states the complexity of the custom evaluator, which WS05-T04 has to state and test on its own.

## Decision

Outcome C. The rule (WS05-T02 check 9): (A) RTAMT is the point-robustness engine behind `ralmon.monitor`, the interval layer is custom; (B) the evaluator is custom, RTAMT stays an oracle in tests and the engine of baseline B3; (C) RTAMT cannot host the templates, the evaluator is custom, B3 uses the custom point evaluator and the paper says so. Outcome C is forced by any Q1 failure on a template; outcome A requires Q1, Q2 and Q4 to pass.

Application: Q1 is FAIL (`sched` and `int` contain `age` and cannot be translated, `sys` translates but its equality atom gives a different value). The rule therefore forces outcome C. Q4 is FAIL too, so outcome A would be excluded as well. Decision output of the script: `outcome C (forced by a Q1 failure): custom evaluator; B3 uses the custom point evaluator`.

Reasoning for the reviewer. Outcome B was considered: with two hand rewrites (a derived time signal, a guard indicator) 8 of the 10 time-margin goldens are reproduced, and four templates translate unchanged. It is not adopted because (i) the rule of the task says C, (ii) the rewrites are per-template and not syntax-directed, so a B3 built on them would not be "the same templates with RTAMT" in the sense of analisi §5.4 for three of the seven, (iii) the graded lateness of G-SCHED-3 and the unavailable-channel case G-INT-3 are not reproduced, and (iv) RTAMT 0.4.10 does not import on the Python of the repository (3.14.4). If a human prefers B, the work is the rewrite layer, a NaN policy (unavailable as `-inf`, which loses the three-valued reading) and a Python 3.12 test environment; the choice is left in ADR-013 as `[DA-CONFERMARE]`.

No extra `rtamt` is added to `pyproject.toml`: the monitor, the oracle and baseline B3 do not use RTAMT under outcome C. RTAMT 0.4.10 reproduced the golden values of `range`, `hold`, `count` and `resp` (16 of 16 evaluations) on Python 3.12, so it may be used as an optional cross-check in a test on a Python it supports; that is a decision of WS05-T04 and would need the extra then.

Not tested: other versions of RTAMT; a newer ANTLR runtime on Python 3.14; the C++ backend; the dense-time specification class; `since`; `rise` and `fall`; Breach and S-TaLiRo (MATLAB, listed in analisi §3.1, not evaluated); multi-patient state sharing; wall-clock performance (deliberately not measured).

## Consequences for WS05-T03, WS05-T04, WS06-T04

| Task | Consequence |
|---|---|
| WS05-T03 (`ralmon.spec`) | `ralmon.spec` does not import RTAMT. The `formula_past_time` strings stay as documentation and as the source of the grammar; the loader checks that every window parameter is a multiple of the step (the same rule RTAMT enforces, W7). |
| WS05-T04 (`ralmon.monitor`) | The point evaluator and the interval layer are custom. Required properties from this spike: indicator atoms are `+inf` and `-inf`; equality atoms on a status are guards, not `-abs(a - b)`; an unknown value is carried as an interval or as NaN with an explicit rule, never fed into `min` and `max` of the language; slack is computed per instance (`age` is a property of the instance); the non-monotone cases of Q3 (`range`, `count` with coincident triggers, `sys` with a multi-valued status) need the special handling stated there; the complexity of the sliding windows must be stated and tested (the RTAMT baseline is O(window) per update). `make_point_evaluator` is the entry point for raw robustness. |
| WS06-T04 (baseline B3, plain STL) | B3 calls `make_point_evaluator` of `ralmon.monitor`, not RTAMT, and the paper says that the point-robustness evaluator of B3 is the project's own, evaluated on the same templates (analisi §5.4 reads "same templates with RTAMT"; this wording must not be used). The reporting of B3 is unchanged otherwise. |
| Test environment | RTAMT does not import on Python 3.14; any future use of it as an oracle needs Python 3.12 or 3.13 (3.13 was not tested). |
