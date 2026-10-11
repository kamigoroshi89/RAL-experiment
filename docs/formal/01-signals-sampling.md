# 01 Signals, sampling semantics, time and decomposition

Document WS01-T01. Feeds paper Section III (problem formulation). Draft for the M1 freeze (WS01-T08); it changes no contract of `docs/plan/02-interfaces.md` (gaps are recorded in section 9). Validation in this project is technical and pre-clinical; nothing in this document is a clinical claim, and every clinical number is either fixture arithmetic or an analisi value labelled "illustrative, unverified" (ADR-020).

## 1 Scope and conventions

### 1.1 What this document fixes

1. The signal table: the symbols of analisi §4.1 mapped to the seventeen `SignalId` values of `02-interfaces.md#signals`, with kind, unit, producer and availability (section 2).
2. The discrete-time sampling semantics for sparse and irregular data: grid, piecewise-constant hold, impulses, the ceiling rule, multiplicity, undefined and unavailable values, alignment of windows, and the treatment of exact point-event windows (section 3).
3. The two clocks, the reorder buffer, the late-sample policy, the skew assumption, timestamp replay and the three latency terms (section 4).
4. The derived signals and the day-boundary convention (section 5).
5. The decomposition phi = phi_CP and phi_SYS and phi_INT and the wording rules attached to it (section 6).

It does not define template formulas (WS01-T02), normalised robustness (WS01-T04), three-valued semantics (WS01-T05), rho (WS01-T06) or the alert tuple (WS01-T07). The specification defined here is evaluated on the observed trace only: nothing in it reads `LatentDay` or `GroundTruthEvent`.

### 1.2 Scope decisions used

Hypertension is the main pathology (ADR-001). C3 means integrity violation, reduced from "adversarial tampering" (ADR-002). The architecture is a ward node plus a robot (ADR-003). The output artefact of WS00-T02 was not present in the repository when this document was written; ADR-001 to ADR-003 are used as the scope source and nothing in this document depends on the missing artefact.

### 1.3 Conventions

1. Time is integer milliseconds since the start of the patient-day trace (ADR-017, `02-interfaces.md#time-and-units`). A label `hh:mm` converts as `t_ms = (60*hh + mm) * 60000`; for example 09:05 is 32,700,000. Labels are for reading only.
2. Constraints are past-time (ADR-007). Only the past operator "once" is used in this document, written `O[a,b]`. There is no tutorial of temporal operators here (analisi §7, cut 2).
3. Terms follow the binding glossary (`01-conventions.md` section 7): tier, module, node; pathway template instantiated into a patient care plan; DISPENSE is not INTAKE; alert, violation, attributed cause; "robustness" is reserved for STL semantics; the verdict states are PENDING, PREDICTED-VIOLATION, VIOLATED, SATISFIED; latent trace versus observed trace.
4. "FIXTURE-ONLY" marks a value chosen for hand arithmetic (fixture registry F0 of `docs/plan/workstreams/WS01-formalization/README.md`); "illustrative, unverified" marks a value taken from analisi §4.1, §4.6 or §4.7. Neither carries a clinical meaning.
5. Contract anchors are written `02-interfaces.md#anchor`. No reference is cited from memory; no citation is needed in this document.

### 1.4 Notation

| Symbol | Meaning | Source |
|---|---|---|
| `T_s` | monitor step, integer ms | `step_ms` |
| `D` | maximum reorder delay, integer ms | `reorder_delay_ms` |
| `T_day` | length of a patient-day, `86,400,000` ms (24 h); a definition, not a registry parameter | this document |
| `K` | number of steps of a day, `K = T_day / T_s` | this document |
| `t_k = k * T_s` | grid time of step `k`, `k = 0, 1, ..., K` | section 3.1 |
| `t_e` | device time (`t_device_ms`) of an event or sample `e` | contract |
| `k_up(t)` | ceiling step index, `k_up(t) = ceil(t / T_s)`, in integers `(t + T_s - 1) // T_s` for `t >= 0` | section 3.3 |
| `a` | anchor: device time of the event (schedule tick or dispense) that opens an obligation instance | section 3.7 |
| `B` | deadline offset of an obligation, an aligned duration (`W`, `delta2`, `int_window`) | section 3.7 |
| `W`, `w` | `sched_window` in ms, and `w = W / T_s` in steps (not the witness signal `w(t)`, always written with its argument) | section 3.7 |
| `NaN` | undefined value, read as "unknown" | section 3.5 |
| `None` | channel unavailable (contract meaning) | section 3.5 |

### 1.5 Parameters used

Registry working names used in this document, with their F0 values, unit and origin (WS01-T02 fixes the final names, WS01-T03 registers them). The last column says whether the alignment rule of section 3.6 applies.

| Working name | F0 value | Unit | Origin | Role |
|---|---|---|---|---|
| `step_ms` (`T_s`) | 60000 | ms | FIXTURE-ONLY monitor configuration | monitor configuration |
| `reorder_delay_ms` (`D`) | 0; 30000 in W5 | ms | FIXTURE-ONLY monitor configuration | monitor configuration, not a window edge |
| `sched_window` (`W`) | 1800000 | ms | FIXTURE-ONLY | window parameter, alignment applies |
| `hold_lookback` | 3600000 | ms | analisi §4.1, 60 min (illustrative, unverified) | window parameter, alignment applies |
| `int_window` | 300000 | ms | analisi §4.1, 5 min (illustrative, unverified) | window parameter, alignment applies |
| `delta1` | 3600000 | ms | analisi §4.6 (illustrative, unverified) | window parameter, alignment applies |
| `delta2` | 10800000 | ms | analisi §4.6 (illustrative, unverified) | window parameter, alignment applies |
| `dose_max_24h` | 2 | dose | analisi §4.1 (illustrative, unverified) | count limit, used only as an illustration in W6 |
| `dose_min_day_end` | 2 | dose | analisi §4.1 (illustrative, unverified) | count limit, used only as an illustration in section 5.5 |
| `meas_min_day` | 5 | count | analisi §2 R2 weakness 5 and §4.6 (illustrative, unverified) | count limit, only if WS01-T02 adopts a measurement-count obligation (CP2) |
| `cuff_inflation_min` (`q_min`) | 30000 | ms | FIXTURE-ONLY | threshold on the value of `inflation_ms`, alignment does not apply |
| `bound_bp_lower`, `bound_bp_upper` | 50, 250 | mmHg | analisi §4.7 (illustrative, unverified) | physiological bounds named in section 3.5 |
| `clock_skew_max_ms` (`skew_max`) | not set | ms | working name proposed here; declared unset, WS01-T03 to register | monitor configuration, not a window edge |

Every other number in this document is an example time (a clock label and its millisecond conversion) or fixture arithmetic inside a worked example, and is marked as such.

## 2 Signal table

### 2.1 The seventeen signals

Columns. Kind is one of: held value (piecewise-constant between samples), impulse (an event seen as a one-step indicator), derived (computed by the monitor from other signals), status (a level with an explicit health or availability meaning). Trace form says how the signal reaches the monitor in the trace schema of `02-interfaces.md#trace-schema`. "Unavailable?" says whether the channel can be unavailable, as opposed to zero.

| SignalId | Symbol | Kind | Unit | Producer | Trace form | Unavailable? | Semantics and use |
|---|---|---|---|---|---|---|---|
| `bp` | `bp` | held value | mmHg | device (cuff) | `Sample` | no | last measured systolic pressure; NaN before the first sample (section 3.5) |
| `meas` | `m` | impulse | 1 (indicator) | device (cuff) | `Event` kind MEASUREMENT | no | a measurement was completed and produced a value; a MEASUREMENT_MISSED event is not a `meas` impulse |
| `dispense` | `d` | impulse | 1 (indicator) | device (dispenser) | `Event` kind DISPENSE | no | dispenser opened; never proves intake (section 2.3) |
| `intake` | `w` (component, section 2.4) | impulse | 1 (indicator) | robot (witness) | `Event` kind INTAKE | yes | intake verified by the robot; exists only while the robot is co-located |
| `sched_tick` | `s` | impulse | 1 (indicator) | monitor (from the care-plan schedule) | `Event` kind SCHEDULE_TICK | no | a care-plan step becomes due; anchor of SCHED obligations |
| `dose_count` | `c_d` | derived | dose | monitor | none (computed) | no | dispenses in the trailing 24 h, section 5.1 |
| `meas_count` | `c_m` (proposed here; analisi §4.6 and §4.9 item 3 use a day-end count of measurements without a symbol) | derived | measurement (count) | monitor | none (computed) | no | measurements in the current day, section 5.2 |
| `bp_pre` | `bp^{pre}` | derived | mmHg | monitor | none (computed) | no | pressure of the last measurement before a dose, captured per obligation instance, section 5.3 |
| `bp_drop` | `r` | derived | mmHg | monitor | none (computed) | no | `bp_pre - bp`, section 5.4 |
| `cuff_health` | `h_c` | status | 1 (1.0 healthy) | device (cuff node) | `Sample` | no | health of the cuff node; any other value is "not healthy" (encoding of other states belongs to WS02 and WS07) |
| `inflation_ms` | `q` | held value | ms | device (cuff) | `Sample` | no | inflation duration of the latest measurement |
| `presence` | `w` (component, section 2.4) | status | 1 (1.0 present) | robot (witness) | `Sample` | yes | robot-observed presence of the patient; exists only while the robot is co-located |
| `auth` | `a_{auth}` | impulse | 1 (indicator) | device (dispenser) | `Sample` (no EventKind exists) | no | authenticated dispense event; the trust in the authentication is WS02's subject |
| `day_end` | `e_{day}` | impulse | 1 (indicator) | monitor (day calendar) | none (generated) | no | end-of-day marker for count obligations, true at the closing step `K` of a day (section 5.5) |
| `hr_ecg` | evidence only | held value | beats per minute | device (ECG) | `Sample` | no | no template uses it; cross-device coherence evidence (analisi §4.5 group 4) and forecaster input |
| `hr_pulse` | evidence only | held value | beats per minute | device (cuff) | `Sample` | no | pulse rate reported by the cuff; same use as `hr_ecg` |
| `spo2` | evidence only | held value | percent | device (pulse oximeter) | `Sample` | no | no template uses it; forecaster input and signal-quality evidence |

Symbols of analisi §4.1 item 1 covered: `bp`, `m`, `d`, `s`, `c_d`, `h_c`, `q`, `w`, `e_{day}`, `a_{auth}`, `bp^{pre}`, `r`. The symbol `w` of analisi is not a `SignalId`: it is defined from `presence` and `intake` in section 2.4.

For the device channels a missing sample is "no sample" (section 3.5): the monitor does not conclude that the channel is unavailable. Node health is evidence, reported through the `EvidenceVector` (`02-interfaces.md#evidencevector`), not through the signal value. Only the robot channels have structural unavailability.

### 2.2 Transport form

`Sample.signal` carries a `SignalId` value (`02-interfaces.md#trace-schema`), so a signal without an `EventKind` (`auth`, `presence`, `cuff_health`) travels as a `Sample` (value 1.0 for indicators). The impulses `meas`, `dispense`, `intake` and `sched_tick` come from events of the corresponding kind. The mapping from events to grid impulses is the ceiling rule of section 3.3. This choice is a reading of the contract and is listed in section 9 (CG-5).

### 2.3 DISPENSE is not INTAKE

`dispense` is produced by the dispenser (device) and records only that the dispenser opened. It never proves intake: a patient can take the pill, refuse it, or take two (ADR-004, analisi §4.9 item 5). `intake` is produced only by the robot witness, and only while the robot is co-located and has verified the intake. No monitor, template or derived signal may construct `intake` from `dispense`, and no signal named `intake` is ever the output of the dispenser. Counters and the hold rule use `dispense`; response evidence uses `intake` where it is present (ADR-004, consequences).

### 2.4 The witness signal w

phi_INT of analisi §4.1 refers to a signal `w(t)`, "presence or intake observed by the robot". It is defined here as a function of the three signals `presence`, `intake` and `auth`, where `auth` enters only through the disjunction of phi_INT and never through `w`.

In short, `w = presence or intake`, with `intake` only when the robot is co-located. Precisely, let `presence_k` and `intake_k` be the grid values of the two robot channels at step `k` (section 3), each in `{0, 1}` when the channel is available and undefined when it is not. Then

`w(t_k) = presence_k or intake_k`, read in three-valued logic:

- `w(t_k) = 1` if an available component equals 1;
- `w(t_k) = 0` if both components are available and both equal 0;
- `w(t_k)` is unavailable (unknown) otherwise, in particular whenever the robot is not co-located. It is never converted to 0.

The witness disjunction of phi_INT is then `w(t_k)` or `a_{auth}` at step `k`, again in three-valued logic (true or unknown is true; false or unknown is unknown). A dispense with no authentication and no robot in the room is therefore not counted as "unwitnessed"; it is undecidable on the witness channel. What the verdict machinery does with this state is CP6 (WS01-T05, section 9).

**Justification.**

1. It is the definition of analisi §4.1 item 1: `w` is "presenza o assunzione osservata dal robot".
2. phi_INT tests the provenance of a dispense event: someone or the robot was there, or the event was authenticated. It does not test adherence. Requiring `intake` alone would report a patient who declines a dispensed pill as an integrity failure and would mix C1 (adherence) with C3 (integrity, ADR-002). Adherence is the subject of INTAKE as its own signal (ADR-004), used by the response template, not by phi_INT.
3. `presence` is the weaker witness but the only robot observation available before a pill is swallowed. The workshop form of phi_INT looks back from the dispense step (`d -> O[0,int_window](w or a_auth)`), so at that step an `intake` that follows the dispense cannot yet contribute; only `presence` (and `auth`) can. Whether phi_INT is evaluated at the dispense step or at a deadline `int_window` after it, where `intake` also contributes, is a template decision for WS01-T02 (section 9, CG-7). Defining `w` as the disjunction keeps both forms available.
4. The three-valued treatment of unavailability is what makes the embodied-channel ablation A4 meaningful: removing the robot channel turns `w` into "unavailable", not into "no witness".
5. Limit, to be reported with the diagnosability matrix (analisi §4.5): `presence` does not distinguish an informed attacker who is physically in the room, and a plausible, cross-modally consistent injection is undetectable by construction (ADR-002).

### 2.5 Availability

`presence` and `intake` exist only while the robot is co-located (`02-interfaces.md#signals`, rule). When it is not, the corresponding fields are `None` in the contract and "unavailable" here. Section 3.5 gives the exact separation of the four situations "value 0", "no sample", "undefined before the first sample" and "channel unavailable". The source of the availability intervals is the robot node status and heartbeat (ADR-003), reported through the `EvidenceVector` (`witness.robot_present is None`); its encoding is WS02's.

## 3 Time base and sampling semantics

### 3.1 Time base and grid

The trace of a patient-day covers device times in `[0, T_day)`, with `T_day = 86,400,000` ms; the instant 24:00 belongs to the next day. The monitor evaluates at the grid steps

`t_k = k * T_s` (equivalently `t_k = k \cdot T_s`), `k = 0, 1, ..., K`, with `K = T_day / T_s`.

The closing step `K` (24:00) exists so that events with device time in the last step `(t_{K-1}, t_K)` have a step to be seen at. A monitor configuration is rejected if `T_day mod T_s != 0` (modelling choice M2, needed by section 5.1). With the F0 value `T_s = 60000`, `K = 1440`.

All arithmetic is integer millisecond arithmetic (ADR-017); no float time is used.

### 3.2 Held signals

A held signal `x` is given by samples `(t_i, v_i)`, ordered by device time (after the reorder buffer of section 4). Two samples with equal device time are ordered by `seq` when present, else by receive time, so that the order is deterministic. The grid value is

`x_k = v_i` for the sample `i` with the largest `t_i <= t_k`, and `x_k = NaN` if no sample has `t_i <= t_k`.

A sample is therefore held piecewise-constant from its device time: it becomes visible at the first grid step `>= t_i` and stays until the next sample becomes visible. This is `hold_last` of `02-interfaces.md#signals`. The `quality` field of a sample does not change the held value; it is evidence (WS02). Several samples inside one step (for example `hr_ecg` at a rate above `1 / T_s`) are reduced to the latest one by the hold.

### 3.3 Impulses and the ceiling rule

An event with device time `t_e` is visible as an impulse at the first grid step `>= t_e`, the ceiling rule:

`k_up(t_e) = ceil(t_e / T_s)`, computed in integers as `(t_e + T_s - 1) // T_s`.

For an available impulse channel, `u_k = 1` if some event `e` has `k_up(t_e) = k`, else `u_k = 0`. Equivalently the event falls in the half-open bin `(t_{k-1}, t_k]`; an event exactly on a grid time is visible at that step. The same rule places a held sample: it is held from step `k_up(t_i)`.

The ceiling rule, not rounding and not floor, is the causal choice. With floor an event with device time `t_e` would be visible at a step `t_k < t_e`, so the evaluation of step `k` would use information from the future of `t_k`, and the causality rule of `Monitor.advance` (section 4.2, inputs with `t_device_ms <= t - D`) would be violated. With the ceiling rule step `k` uses only device times `<= t_k`.

**Effect of the grid on windows.** A continuous-time window `[a, a + B]` around an anchor `a` becomes, on the grid, the steps `k_up(a), ..., k_up(a) + B/T_s`, that is device times in `(t_{k_up(a)-1}, t_{k_up(a)} + B]`. This contains `[a, a + B]` and extends it by less than `T_s` on the left (measurements just before the anchor) and by less than `T_s` on the right (measurements just after the continuous deadline). Consequence: a grid verdict VIOLATED implies a violation of the continuous-time window, but a grid verdict SATISFIED can hide a continuous-time miss of less than `T_s`. The resolution `T_s` is therefore part of what the paper reports.

### 3.4 Multiplicity

Impulse coalescing must not lose multiplicity. Several events in one step give one impulse `u_k = 1`, but the number of events `n_k = |{e : k_up(t_e) = k}|` is kept. Counters are computed from the event stream, not from the binned impulse: two `dispense` events inside one step give `dose_count` an increment of 2, not 1 (example W3). The same holds for `meas_count`. Anchors of obligation instances are also taken from the event stream (or the plan schedule), not from the impulse (section 3.7).

When a `seq` is present, an event that repeats an already accepted `(source, seq)` is a duplicate and is not counted again; it is evidence for `crypto_temporal.seq_repeat` (section 4.5; named `seq_gap_or_replay` in contract 0.1.0, split by ADR-034 into `crypto_temporal.seq_repeat` and `system.seq_gap` in `#evidencevector` 0.2.0, WS05-T13). When `seq` is `None`, duplicates cannot be told from genuine repeated events, both are counted, and the exposure to replay is stated in section 4.5.

### 3.5 Undefined values, no sample and unavailable channels

Four situations are kept apart.

| Situation | Signal kind | Grid value |
|---|---|---|
| Held signal before its first sample | held value | `NaN`: undefined, read as "unknown, completed by physiological bounds" (CP12) |
| Held signal between samples | held value | the held value: absence of a new sample is "no sample", not a change |
| Impulse channel available, no event in the step | impulse | `0` |
| Channel unavailable (robot not co-located) | `presence`, `intake` | `None` in the contract; never converted to 0 or false |

The undefined value is `NaN`, chosen because `hold_last` returns `Sequence[float]`. Recommended reading: an atomic predicate over `NaN` is unknown, not false. In the interval semantics of WS01-T05 an unknown pressure is replaced by the physiological bounds `[bound_bp_lower, bound_bp_upper]` (F0: 50 and 250 mmHg, illustrative, unverified), never by 0 and never propagated silently as a Boolean. This is CP12; the exact interval encoding, including infinite raw intervals, is settled in WS01-T05.

A value `NaN` (the channel exists but has no value yet) and `None` (the channel does not exist at that time) are different states. `None` cannot live in a `Sequence[float]`; an availability mask next to the numeric array carries it. The encoding is WS05-T02's; the requirement stated here is that the monitor can tell, for every step and every channel, "value 0 with the channel available" from "channel unavailable" (CG-6).

### 3.6 Window parameters must be aligned

A window parameter is a registry time value used as an offset or bound of a temporal operator, a look-back or a deadline offset: F0 has `sched_window`, `hold_lookback`, `int_window`, `delta1`, `delta2`, and the derived width `delta2 - delta1`. The rule: every window parameter is a non-negative integer multiple of `T_s`. A patient care plan whose window parameters violate it is rejected at load (`Monitor.load`), with an error that names the parameter and `T_s`. The monitor never rounds a clinician-reviewed value, because rounding would silently change the care plan.

The rule does not apply to time-valued registry entries that are not window edges: scales (`scale_sched`, `scale_sys`, `scale_int`), the threshold `cuff_inflation_min` (compared with the value of `inflation_ms`), `reorder_delay_ms` and `clock_skew_max_ms`. In F0 the threshold `cuff_inflation_min = 30000` ms and `D = 30000` ms are not multiples of `T_s = 60000`, so applying the rule to "all registry time values" would reject the fixture registry itself. This is a deviation from the literal wording of the task and is recorded in section 9 (CG-1). Schedule ticks (`CarePlan.schedule`) are instants, not durations, and need not be aligned; the ceiling rule handles them.

Under the rule, all window arithmetic on the grid is exact: an operator `O[a,b]` with aligned `a <= b` looks at the steps `j` with `k - b/T_s <= j <= k - a/T_s`, `j >= 0`, and nothing is interpolated.

### 3.7 Point events with an exact window: O[W,W] and O[W,W+T_s]

**Contract rule.** A point event with an exact window `O[W,W]` is evaluated as `O[W,W+T_s]` (`02-interfaces.md#time-and-units` rule 2; analisi §4.1 aspect 5; ADR-007). With `w = W / T_s` and the impulse `u` of an anchor, the widened antecedent at step `k` is

`A_k = (O[W,W+T_s] u)_k = 1` iff `u_{k-w} = 1` or `u_{k-w-1} = 1`.

**Analysis of one anchor.** Let the anchor have device time `a` and visible step `k_a = k_up(a)`, so `u_{k_a} = 1`, and suppose no other anchor is near. Then `A_k = 1` iff `k - w = k_a` or `k - w - 1 = k_a`, that is iff `k` is in `{k_a + w, k_a + w + 1}`. The antecedent impulse is therefore true at two consecutive steps. Call `k_d = k_a + w` the first true step and `k_d + 1` the second (the shadow step). Let the consequent of the SCHED template be `C_k = (O[0,W] m)_k`, true iff a measurement impulse lies in the steps `k - w, ..., k`. Evaluating the string `always (A -> C)` naively gives three effects.

1. Two evaluations of the consequent per anchor, over the step windows `[k_a, k_a + w]` at `k_d` and `[k_a + 1, k_a + w + 1]` at `k_d + 1`. The Boolean result is `C_{k_d} and C_{k_d+1}`. The second window drops the anchor step `k_a` and adds the step after the deadline. The result differs from the single evaluation `C_{k_d}` exactly when the only qualifying measurement lies at step `k_a` (W4, case b).
2. One anchor produces two verdict records, one at each true step, with different decision times. An obligation is duplicated into two possible violations and, downstream, into two alerts.
3. Rising-edge detection of `A` does not repair it. Two anchors one step apart make `A` true at three consecutive steps with one rising edge, and two anchors in the same step give one impulse. The instance count would be wrong in both cases.

**Anchoring convention.** One obligation instance per anchor, evaluated once.

1. An instance is created for each anchor event, taken from the plan schedule (`CarePlan.schedule`, static anchors, for example SCHED) or from the event stream (dynamic anchors, for example the dispense that opens a response or witness obligation). It is not created from the binned impulse, so two anchors in one step give two instances (section 3.4).
2. Its visible anchor step is `k_a = k_up(a)`.
3. Its only decision step is `k_d = k_a + B/T_s`, decision time `t_d = t_{k_a} + B`, where `B` is the aligned deadline offset (`W` for the example). At `k_d` the consequent is evaluated once, over `[k_a, k_d]`. Verdicts already emitted are never retracted.
4. The second true step `k_d + 1` of the widened antecedent is not a decision step for that instance: `A_{k_d+1}` is ignored, and the instance is closed at `k_d`.

With this convention the reference semantics is the per-instance one, `C_{k_d}`. The Boolean value of the whole-formula string coincides with it except in the one case of effect 1, in which the string is stricter; WS01-T02 must state the relation for the template strings and WS01-T05 must not implement the string without anchoring (section 9, CG-2).

**Observation on the role of the widening.** On the aligned grid, with ceiling binning and aligned `W`, the exact operator `O[W,W]` already fires at exactly one step, `k_d`, which is the first step `>= a + W` (`t_d - (a + W)` lies in `[0, T_s)`). Under the convention above the extra true step `k_d + 1` decides nothing. I could not find a case on the aligned grid where the widening changes the decision step, so it is kept only because the contract and ADR-007 prescribe it (it would matter for a tool that bins impulses differently or does not align `W`); this is recorded, not changed, in section 9 (CG-2).

**Latency consequence.** The continuous deadline is `a + B`; the decision time is `t_d = t_{k_a} + B` with `t_{k_a} - a` in `[0, T_s)`. The event-time latency from the anchor is therefore in `[B, B + T_s)`, and `B + T_s` is the bound that the contract names ("Delta2 or W plus T_s", `#template`, `max_verdict_latency_param`). The `+ T_s` comes from ceiling the anchor, not from the second true step. Section 4.6 defines the latency terms.

## 4 Clocks, reordering and verdict latency

### 4.1 Two clocks

Every sample and event carries two clocks (`02-interfaces.md#trace-schema`, `#time-and-units` rule 3):

- `t_device_ms`: the timestamp given by the device, in the device clock. It orders observations and is the time base of all windows and of verdict latency.
- `t_rx_ms`: the time of reception at the monitor, in the monitor clock (the ward-node clock, ADR-003). It measures transport delay and drives the reorder buffer. In offline traces without transport delay `t_rx_ms = t_device_ms`.

The monitor time `t` (argument of `Monitor.advance`) is in the same time base as `t_rx_ms`.

### 4.2 Reorder buffer and causality rule

Inputs are pushed as they arrive, in `t_rx_ms` order, and held in a reorder buffer that releases them in `t_device_ms` order. The buffer has a maximum delay `D` (`reorder_delay_ms`, declared in `MonitorConfig`). The causality rule of `Monitor.advance` (`02-interfaces.md#monitor`) is:

`advance(t)` uses only inputs with `t_device_ms <= t - D`.

Step `k` is finalised, and its verdicts emitted, at the first monitor time `t >= t_k + D`, that is when the watermark `t - D` reaches `t_k`. By the ceiling rule every input visible at step `k` has device time `<= t_k`, so step `k` is evaluated with exactly the inputs it may use. The watermark of an input with device time `t_e` is `t_{k_up(t_e)} + D`: the monitor time at which the step that would first show it is finalised. An input received at `t_rx_ms <= t_{k_up(t_e)} + D` is on time (an arrival exactly at the watermark is on time: pushes with `t_rx_ms <= t` are processed before `advance(t)`).

Lateness is defined by the step and not by the frequency of `advance` calls, so the outcome does not depend on how often the caller invokes `advance`.

### 4.3 Late-sample policy

An input that arrives after its watermark (`t_rx_ms > t_{k_up(t_e)} + D`) is late. It is not used: it does not enter a held value and does not count in a counter. It is counted per source, and it is evidence for `timestamp_implausible` (`02-interfaces.md#evidencevector`, `crypto_temporal`). An emitted definitive verdict is never retracted and never changed by a late input; verdicts are causal functions of the accepted prefix.

The cost of the policy is stated: a genuine measurement delayed by more than `D` is lost to the monitor, and the held value stays older than the newest measurement. Whether `timestamp_implausible` means late delivery, a wrong device clock or replay is for the attribution layer (WS02). This is modelling choice M3; an alternative (admitting late samples for steps not yet finalised) would make the held value depend on arrival time and is not adopted.

Worked example W5 (`D = 30 s`) shows both cases.

### 4.4 Clock-skew assumption

Assumption: each device clock differs from the monitor clock by at most `skew_max` (`clock_skew_max_ms`, a monitor configuration value, declared unset here and registered by WS01-T03). A larger skew is evidence, not a value: the monitor does not estimate offsets, does not correct timestamps and does not rewrite them. Two rules follow.

1. An input with `t_device_ms > t_rx_ms + skew_max` (a timestamp from the future beyond the assumption) is not used, is counted, and is evidence for `timestamp_implausible` (modelling choice M4). A future-stamped sample would otherwise override real samples at a later step.
2. Timing statements carry the assumption. Window edges are accurate to `T_s` from the grid (section 3.3) plus up to `2 * skew_max` when the two ends of a window come from two devices (for example a dispense from the dispenser clock and a measurement from the cuff clock). Verdict latency measured between a device timestamp and a monitor time carries an error of up to `skew_max`.

### 4.5 Timestamp replay as an attack vector

Timestamp semantics is also a threat surface (analisi §4.9 item 2). Replay of an old genuine message keeps its old `t_device_ms`:

- A replayed message arriving after its watermark is late (section 4.3), unused and counted; this catches replay beyond `D` only.
- A replayed message arriving within `D` of the original, or carrying rewritten fresh timestamps, is not caught by timing. A replayed `dispense` event would increment `dose_count` (section 3.4). Deduplication needs `seq`; with `seq = None` the replay is not detectable from the trace, and the counter is exposed.
- Consistent with the diagnosability matrix (analisi §4.5): replay of pressure measurements is distinguishable with sequence numbers, timestamps and an ECG cross-check, and only partially without authentication.

The monitor does not assert authenticity: it flags what is inconsistent (late input, future stamp, repeated `seq`) as evidence and leaves the attributed cause to WS02. The threat model and the attack classes are WS02's (ADR-002).

### 4.6 Latency terms

Three quantities, for a template `pi` and an anchor with device time `a`.

- **Event-time latency** `L_{ev}(pi, a) = t_d - a`: from the anchor to the grid time of the step at which the definitive verdict becomes decidable (device-time quantity). For an obligation with deadline offset `B`, `t_d = t_{k_up(a)} + B` (section 3.7), so `B <= L_{ev} < B + T_s`. For an immediate template (`B = 0`), `L_{ev} < T_s`.
- **Processing latency** `L_{proc}`: from the decision time to the emission of the verdict. By section 4.2 the verdict of step `k` is emitted at monitor time `t_k + D`, so `L_{proc} = D` plus a compute time `eps_c` that this document does not model (measured in WS07).
- **End-to-end latency** `L_{e2e}(pi, a) = L_{ev}(pi, a) + L_{proc}`, so `L_{e2e} < B + T_s + D + eps_c`.

The per-template bound is filled in by WS01-T05, which also decides whether `Monitor.verdict_latency_bound_ms` reports the event-time bound `B + T_s` or the end-to-end bound (CG-4). Provisional structure, in the notation of `02-interfaces.md#template`:

| Obligation with deadline | `B` | Event-time bound `B + T_s` |
|---|---|---|
| SCHED | `sched_window` | `sched_window + step_ms` |
| RESP | `delta2` | `delta2 + step_ms` |
| INT (if evaluated at a deadline, CG-7) | `int_window` | `int_window + step_ms` |

Illustration with F0 (`T_s = 60000`, `sched_window = 1800000`, `D = 30000`, fixture arithmetic): the event-time bound is `1,800,000 + 60,000 = 1,860,000` ms (31 min), the end-to-end bound before compute time is `1,860,000 + 30,000 = 1,890,000` ms. These are not clinical statements.

## 5 Derived signals

Every derived signal is causal (its value at step `k` uses only inputs with device time `<= t_k` that were accepted by the rules of section 4) and streaming (updated per input, no re-scan of the history). Contract: `02-interfaces.md#signals`, `DerivedSignal`.

### 5.1 dose_count

`c_d(t_k)` is the number of accepted `dispense` events with device time in `(t_k - T_day, t_k]`, that is `(t - 24 h, t]` at `t = t_k`, a half-open window of 24 h: the left end is excluded, the right end included. Implementation: a queue of dispense device times. A new accepted event is pushed (increment by the multiplicity, section 3.4). At each step, entries with `t_e <= t_k - T_day` are popped from the front. Each event is pushed once and popped once, so the cost is amortised O(1) per event.

Because `T_s` divides `T_day` (section 3.1), the device-time form equals the binned form `c_d(t_k) = sum of n_j for j in (k - K, k]`: for the grid time `g = t_k - T_day`, an event has `t_e > g` iff `k_up(t_e) T_s > g`, because `g` is a grid time. This is why M2 is required.

The trailing window is not reset at midnight, so a day-local run needs the previous 24 h (section 5.5, CP7). A counter predicate `c_d <= dose_max_24h` has raw robustness `dose_max_24h - c_d` in doses (analisi §4.1 aspect 2, WS01-T02).

### 5.2 meas_count

`c_m(t_k)` is the number of accepted `meas` events with device time in `[0, t_k]`, that is measurements in the current day. It restarts at each day start and needs no warm-up. Only completed measurements count: a MEASUREMENT_MISSED event does not, so a cuff failure lowers `c_m` (a downstream cascade, analisi §4.9 item 3, is WS02's). Cost: O(1) per event. Whether `c_m` is a `COUNT` template term and with which robustness unit is CP2 (WS01-T02, `RobustnessUnit` has no unit for measurement counts).

### 5.3 bp_pre

`bp_pre` is the pressure of the last measurement before a dose. Two forms are defined.

**Per obligation instance (the semantic form).** When a dispense event `e` (device time `t_e`) opens an obligation instance `i`, the monitor captures once

`pre_i = ` value of the latest `bp` sample with device time `<= t_e`, or `NaN` if there is none.

It is taken from device times, not from the grid: the held value at step `k_up(t_e)` could already include a measurement taken after the dispense within the same step. A measurement with the same device time as the dispense counts as before the dose (modelling choice M5, the usual order is measure then dispense). The capture is immutable for the life of the instance. The instance-level drop is `r_i(t) = pre_i - bp(t)`. Overlapping doses (a second dispense inside the response window of the first) each hold their own `pre_i`; a single global stream would let the second overwrite the first.

**Global stream (the signal form).** The `SignalId` `bp_pre` is the projection: at each accepted dispense, the stream is set to that dispense's `pre_i` and held until the next dispense; `NaN` before the first dispense. It coincides with `pre_i` for instance `i` when no other dispense occurs between the dispense of `i` and its decision step. It serves plots, forecasts and templates that see only signals; response verdicts use the per-instance form, which needs state per active instance, consistent with the monitor cost rule "O(number of active template instances)" (`02-interfaces.md#monitor`).

Cost: O(1) per dispense event. Causal: only device times `<= t_e`. If `pre_i` is `NaN` the instance value `r_i` is unknown (section 3.5).

### 5.4 bp_drop

`bp_drop = bp_pre - bp`, so a fall in pressure gives a positive value. Global stream: `bp_pre - bp` at each step, `NaN` if either operand is `NaN`. Per instance: `r_i(t)` as in section 5.3. Cost: O(1) per sample.

### 5.5 Day-boundary convention, day_end and windows that end after 24:00

The day-boundary conventions, listed once.

1. **Trailing counter.** `c_d` is defined by the trailing window and not by the calendar day, so its value at the start of a day depends on the previous day. The day-end obligation is not affected: at the closing step `K` the window is `(0, T_day]`, that is the whole day except an event at exactly device time 0, which is then exactly 24 h old and leaves the window, as in W6 (section 3.1). With F0 the obligation reads `e_{day} -> c_d >= dose_min_day_end` (illustrative, unverified).
2. **day_end.** `e_{day}` is true at the closing step `K` of a day slice. In an online deployment there is no slice; the day calendar of the care plan produces `e_{day}` at the configured end of day.
3. **Windows crossing 24:00.** An instance belongs to the day of its anchor. Its decision step may lie in the next day (for example a dispense late in the day with a response deadline `delta2` later). The instance keeps its anchor and its captured `pre_i`, and its verdict is emitted in the coordinates of the continuing time axis.
4. **Recommended carry-over rule (CP7).** The monitor state is carried between consecutive days of the same patient. For an offline run with an `ObservedDay` this is done by a warm-up prefix: the accepted observed events of the previous days over a length `H = max(T_day, largest window parameter)` are replayed first, with negative times relative to the day start, verdicts for steps before 0 suppressed because they were emitted by the previous run. Replaying the previous accepted prefix reproduces the state exactly, because the monitor is deterministic and causal. Equivalent alternative: pass a monitor state snapshot from one run to the next. The online monitor has no day boundary; the slicing is an artefact of the offline day-by-day API.
5. **Truncation fallback.** A run that receives no history starts with empty state. Then `c_d` counts only events since the day start, so it can only under-count: a VIOLATED verdict of `c_d <= limit` is still sound, but violations that depend on the previous day are missed (W6 shows the missed case). Instances still open at the closing step are reported as PENDING at trace end, never as SATISFIED, and the labeller of ground truth must use the same rule, otherwise the two disagree on such instances. The fallback is now an option and not the only behaviour: `run_offline(..., history=...)` replays the earlier days of the patient on the continuing axis (item 4, WS05-T10), and the fallback is what a run with an empty `history` does.

`TimeMs` for a warm-up prefix would be negative, which the contract does not forbid or define (CG-11); the change of `run_offline(day, ...)` or of `ObservedDay` that carries the history is a contract change for WS01-T08 (ADR).

## 6 Decomposition of the specification

### 6.1 Three conjuncts

The specification is phi = phi_CP and phi_SYS and phi_INT, three separately evaluated conjuncts: each template instance has its own verdict, its own unit, scale and priority (`02-interfaces.md#template`, `Template.kind`).

| Conjunct | `TemplateKind` | Meaning | `TemplateId` values |
|---|---|---|---|
| phi_CP | CARE_PLAN | constraints derived from the patient care plan (the prescribed care) | RANGE, SCHED, HOLD, COUNT, RESP |
| phi_SYS | SYSTEM | constraints on the health of the monitoring system (a measurement is valid only if the cuff node is healthy and the inflation acceptable) | SYS |
| phi_INT | INTEGRITY | constraints on the provenance of events (a dispense is backed by a robot witness or an authenticated event) | INT |

The whole specification is satisfied iff every instance of the three parts is satisfied. No numeric `min` across the three parts is taken: a `min` over quantities in mmHg, milliseconds and doses is defined mathematically but has no meaning (analisi §4.2; `02-interfaces.md#template`, rules). Only normalised values are compared, per template and within a priority (WS01-T04).

### 6.2 Wording rules

Reason: in the workshop text a hardware-liveness constraint and a dose constraint appear only in a table caption, and "a single monitor handles all three classes" confuses the clinical specification with the system specification (analisi §2 R1 weakness 8; §4.1 item 4).

1. "Violation" means a violated sub-formula. It always names its conjunct: a violation of phi_CP, of phi_SYS or of phi_INT.
2. Only a violation of phi_CP is a violation of the care plan. A violated phi_SYS sub-formula (for example a measurement taken with an unhealthy cuff node) is a violation of phi_SYS. A device fault is not a violation of the care plan.
3. The attributed causes C1, C2 and C3 (and UNDETERMINED) are the values of kappa in the alert. They are not violations: "a C2 violation" is not written. The class C3 is named integrity violation (ADR-002) as a cause class; it is not a violation of phi_CP either.
4. The cause taxonomy is a cause-based taxonomy over violations of phi_CP and phi_SYS and phi_INT (analisi §4.8), not a taxonomy induced by the structure of the constraints.
5. "Care plan" means the patient care plan; the pathway template is the institutional, population-level object it instantiates. "Robustness" is used only for STL semantics; the normalised value is written with a tilde.

### 6.3 Where the parts meet

The three parts share the signals of section 2 but not the evidence: which conjunct is violated is the provenance evidence of the attribution layer (analisi §4.5 group 1). A violation of phi_SYS can invalidate downstream phi_CP instances (a missed measurement lowers `c_m`); cascades and root causes are WS02's (analisi §4.9 item 3).

## 7 Worked examples

All examples use fixture registry F0 with `step_ms = 60000` (`T_s`), `reorder_delay_ms = 0` unless stated. Times are labels; the millisecond value is given in brackets. Values that look like clinical measurements are FIXTURE-ONLY. Every calculation was computed twice: by hand as written, and by an independent script (not committed) whose outputs are quoted in the completion note of the task file.

### W1 hold_last with a value before the first sample

**Inputs.** `bp` samples: 138 at 06:52 (24,720,000) and 152 at 09:05 (32,700,000). Grid `t_k = k * 60000`.

**Expected.** Held value NaN before 06:52 (steps 0 to 411); 138 for 06:52 to 09:04 (steps 412 to 544); 152 from 09:05 to 24:00 (steps 545 to 1440).

**Hand calculation.** 06:52 = (6*60 + 52) * 60000 = 412 * 60000, so step 412; no sample has `t_i <= t_k` for `k <= 411`, so `NaN`. 09:05 = 545 * 60000, step 545; for `412 <= k <= 544` the largest `t_i <= t_k` is 06:52, value 138 (the step 544, 09:04, still has 138 because 09:05 is later than 09:04). From `k = 545` the largest is 09:05, value 152. Counts: 412 NaN steps (0 to 411), 545 - 412 = 133 steps of 138, 1440 - 545 + 1 = 896 steps of 152; 412 + 133 + 896 = 1441 = K + 1 steps.

### W2 impulse binning with the ceiling rule

**Inputs.** Two `measurement` events: one at 06:52:20 (24,740,000), one at exactly 06:52:00 (24,720,000).

**Expected.** The event at 06:52:20 is visible at step 06:53 (413, 24,780,000). The event at exactly 06:52:00 is visible at step 06:52 (412, 24,720,000).

**Hand calculation.** `k_up(24,740,000) = ceil(24,740,000 / 60,000) = ceil(412.33) = 413`, and `413 * 60,000 = 24,780,000` = 06:53. `k_up(24,720,000) = 24,720,000 / 60,000 = 412` exactly, so 06:52. Integer form: `(24,740,000 + 59,999) // 60,000 = 24,799,999 // 60,000 = 413` (413 * 60,000 = 24,780,000 <= 24,799,999 < 24,840,000). A `bp` sample at 06:52:20 would likewise start to be held at 06:53.

### W3 multiplicity: two dispenses inside one step

**Inputs.** Two `dispense` events 500 ms apart, at 20:59:59.500 (75,599,500) and 21:00:00.000 (75,600,000). Before them `c_d = 0` (fixture: no dispense in the previous 24 h).

**Expected.** One impulse `u = 1` at step 21:00 (1260, 75,600,000), multiplicity `n_{1260} = 2`, and `c_d` at step 21:00 is `0 + 2 = 2`, an increment of 2, not 1.

**Hand calculation.** `k_up(75,599,500) = ceil(75,599,500 / 60,000) = ceil(1259.99) = 1260`; `k_up(75,600,000) = 1260`. Both fall in the bin `(t_{1259}, t_{1260}] = (75,540,000, 75,600,000]`. `n_{1260} = 2`, one impulse. `c_d(t_{1260}) = c_d(t_{1259}) + n_{1260} = 0 + 2 = 2`. A counter taken from the impulse would give `0 + 1 = 1`, the loss that section 3.4 rules out.

**Note on the task wording.** The pair 21:00:00.000 and 21:00:00.500 does not coalesce under the ceiling rule: `k_up(75,600,000) = 1260` but `k_up(75,600,500) = ceil(1260.008) = 1261`. They are two impulses (21:00 and 21:01), each with `n = 1`, and `c_d` goes `0 -> 1 -> 2`. The total is again 2 and no multiplicity is lost, but the "one impulse" statement holds only for two events inside the same bin, hence the pair above (recorded in section 9, CG-8).

### W4 alignment of an exact window: tick, two true steps, one evaluation

**Inputs.** A `sched_tick` at 09:00 (32,400,000); `W = sched_window = 1,800,000` (30 min), so `w = 30`. Consequent `C_k = (O[0,W] m)_k`.

**Expected.** `A_k = (O[W,W+T_s] s)_k` is true at steps 09:30 (570, 34,200,000) and 09:31 (571, 34,260,000) and at no other step. The obligation instance is evaluated once, at 09:30. Cases:

- (a) a `meas` impulse at 09:20 (step 560): satisfied at 09:30.
- (b) a `meas` impulse only at 09:00 (step 540): instance satisfied at 09:30; the naive string `always (A -> C)` would report a violation at 09:31.
- (c) a `meas` impulse only at 09:31 (step 571): instance VIOLATED at 09:30, and it stays so; the measurement is after the deadline.
- (d) the tick at 09:00:20 (32,420,000): first true step 09:31, event-time latency 30:40 min, below `W + T_s` = 31 min.

**Hand calculation.** `k_a = 32,400,000 / 60,000 = 540`. `A_k = 1` iff `u_{k-30} = 1` or `u_{k-31} = 1`; `u` is 1 only at 540. So `k - 30 = 540` gives `k = 570`, and `k - 31 = 540` gives `k = 571`. Times: 570 * 60,000 = 34,200,000 = 09:30 and 571 * 60,000 = 34,260,000 = 09:31.

Anchoring: instance decision step `k_d = k_a + w = 540 + 30 = 570` (09:30), `t_d = 32,400,000 + 1,800,000 = 34,200,000`. One evaluation of `C_{570}`, which covers steps 540 to 570.

- (a) step 560 is in `[540, 570]`, `C_{570} = 1`, satisfied. String: `C_{571}` covers `[541, 571]`, contains 560, also 1.
- (b) step 540 is in `[540, 570]`, `C_{570} = 1`, instance satisfied. String at 09:31: `C_{571}` covers `[541, 571]`, does not contain 540, so `C_{571} = 0` and `A_{571} = 1`: violated. This is effect 1 of section 3.7: the only qualifying measurement lies at the anchor step.
- (c) step 571 is not in `[540, 570]`, `C_{570} = 0`, VIOLATED at 09:30. The string also violates at 570 (`A_{570} = 1`, `C_{570} = 0`); same result.
- (d) `a = 32,420,000`; `k_a = ceil(32,420,000 / 60,000) = ceil(540.33) = 541` (09:01); `k_d = 541 + 30 = 571` (09:31), `t_d = 60,000 * 571 = 34,260,000`. `L_{ev} = 34,260,000 - 32,420,000 = 1,840,000` ms = 30 min 40 s, and `B <= L_{ev} < B + T_s` reads `1,800,000 <= 1,840,000 < 1,860,000`. The continuous-time deadline is `a + W = 34,220,000` (09:30:20), the grid decision is 40 s later, less than `T_s`.

### W5 reorder buffer and the late-sample policy (`D = 30 s`)

**Inputs.** `reorder_delay_ms = 30000`. A `bp` sample of value 152 (fixture, as in W1), device time 09:29:50 (34,190,000). Case (i): receive time 09:30:10 (34,210,000). Case (ii): receive time 09:30:40 (34,240,000). Before it, the held value is 138 (W1).

**Expected.** Case (i): accepted for step 09:30, held value 152 from step 09:30. Case (ii): late, not used (held value stays 138 at step 09:30), counted, evidence for `timestamp_implausible`; the verdicts of step 09:30, emitted at 09:30:30, are not changed.

**Hand calculation.** `k_up(34,190,000) = ceil(569.83) = 570`, step 09:30 (34,200,000). Watermark `= t_{570} + D = 34,200,000 + 30,000 = 34,230,000` (09:30:30). Case (i): `34,210,000 <= 34,230,000`, on time. At `advance(34,230,000)` the causality rule uses inputs with `t_device_ms <= 34,230,000 - 30,000 = 34,200,000`; the sample has `34,190,000 <= 34,200,000`, so it is used, and step 09:30 is finalised now, at `t_570 + D`. Case (ii): `34,240,000 > 34,230,000`, late. An arrival at exactly 34,230,000 would be on time (section 4.2).

### W6 trailing counter across midnight (CP7)

**Inputs.** `dispense` events: day 1 at 07:00 (25,200,000), 21:00 (75,600,000), 21:02 (75,720,000); day 2 at 07:00, which is 86,400,000 + 25,200,000 = 111,600,000 on the continuing axis.

**Expected.** `c_d` at day-2 07:00, own dispense included, is 3 with carry-over. A run of day 2 that starts with empty state (truncation fallback) gives 1.

**Hand calculation.** Window `(t - T_day, t] = (111,600,000 - 86,400,000, 111,600,000] = (25,200,000, 111,600,000]`. The day-1 07:00 event, 25,200,000, is exactly 24 h before and is excluded by the open left end. Included: 75,600,000, 75,720,000 and 111,600,000: `3`. A closed window would count 4, which is why the half-open convention is stated. Truncation: events with device time `>= 86,400,000` are only 111,600,000: `1`. Illustration with the F0 limit `dose_max_24h = 2` (illustrative, unverified): `2 - 3 = -1` dose with carry-over, `2 - 1 = +1` with truncation, so the truncated run misses the excess (section 5.5, item 5). At day-1 21:02 the window is `(-10,680,000, 75,720,000]`, containing 07:00, 21:00 and 21:02, so `c_d = 3` already there.

### W7 rejection of a misaligned window

**Inputs.** `T_s = 60000`. Candidate `sched_window` values 1,800,000 and 90,500.

**Expected.** 1,800,000 is accepted; 90,500 is rejected at load.

**Hand calculation.** `1,800,000 mod 60,000 = 0` since `1,800,000 = 30 * 60,000`; accepted. `90,500 mod 60,000 = 30,500 != 0` since `90,500 = 1 * 60,000 + 30,500`; rejected. The other F0 window parameters pass: `3,600,000 = 60 * 60,000`; `300,000 = 5 * 60,000`; `delta2 = 10,800,000 = 180 * 60,000`; `delta2 - delta1 = 7,200,000 = 120 * 60,000`. The threshold `cuff_inflation_min = 30,000` is not a window parameter and is not checked (section 3.6).

## 8 Paper excerpt (Section III)

Sized to 0.5 page (analisi §7); the temporal operators are used, not explained. The alert tuple is a placeholder to be replaced by the definition of WS01-T07; in the tuple, $\tau$ is the violated template, not a time.

```latex
\section{Problem Formulation}
\label{sec:problem}

\textbf{Signals and sampling.}
The monitor observes a patient-day through signals produced by devices, by the robot and by the monitor itself.
Held signals (the last cuff pressure $bp$, cuff health $h_c$, inflation time $q$) are piecewise-constant between samples; before the first sample they are undefined ($\mathrm{NaN}$), which is read as unknown and never as a value.
Event signals (measurement $m$, dispense $d$, schedule tick $s$, authenticated dispense $a_{\mathrm{auth}}$, end of day $e_{\mathrm{day}}$) are one-step impulses.
Counters such as the doses $c_d$ in the trailing 24\,h are derived signals computed from the event stream, so that no multiplicity is lost.
Dispensing is not intake: $d$ is produced by the dispenser, while intake is produced only by the robot witness, and the witness signal $w$ is defined from robot presence and intake, undefined when the robot is not co-located.
Time is integer milliseconds. The monitor evaluates on the grid $t_k = k\,T_s$; an event with device time $t$ is visible at the first step $t_k \ge t$, a point-event window $\mathrm{O}_{[W,W]}$ is evaluated as $\mathrm{O}_{[W,W+T_s]}$ with one obligation instance per anchor, and window parameters are integer multiples of $T_s$ (a care plan violating this is rejected at load).
Every sample carries a device time and a reception time; a reorder buffer of delay $D$ makes evaluation causal, late samples are not used and are counted as evidence, and an emitted definitive verdict is never retracted.
The event-time latency of an obligation with deadline offset $B$ is below $B+T_s$, and the end-to-end latency adds $D$.

\textbf{Decomposition.}
The specification is $\varphi=\varphi_{\mathrm{CP}}\wedge\varphi_{\mathrm{SYS}}\wedge\varphi_{\mathrm{INT}}$: the care-plan constraints derived from the patient care plan, the constraints on the health of the monitoring system, and the constraints on the provenance of events.
The three parts are evaluated separately and no numeric minimum is taken across them, because their raw margins are in different units.
A violated sub-formula is a violation of its own part; only a violation of $\varphi_{\mathrm{CP}}$ is a violation of the care plan, and a device fault is not.
Each violation is reported as an alert $\langle\tau,\kappa,\tilde\sigma,\rho,\xi\rangle$ with the violated template, an attributed cause, a normalised severity, a confidence and a specification-level traceability record (Section~\ref{sec:alert}).
The attributed cause $\kappa\in\{C1,C2,C3,\mathrm{UNDETERMINED}\}$ is a cause-based taxonomy over violations of the three parts.
All numerical values are illustrative and unverified; validation is technical and pre-clinical.
```

## 9 Open points for WS01-T08

Each item gives the anchor and the resolution adopted or proposed. None edits `02-interfaces.md`.

**CP7 (`02-interfaces.md#trace-schema`, `02-interfaces.md#monitor`).** `ObservedDay` and `run_offline(day, ...)` carry no state from the previous day, but `c_d` spans 24 h and response windows can end after 24:00. Proposed resolution (section 5.5): carry state between consecutive days of a patient, offline by a warm-up prefix of length `H = max(T_day, largest window parameter)` with verdicts before step 0 suppressed, or by a state snapshot; truncation fallback with the stated limitation (under-counts, open instances reported PENDING at trace end, labeller must match). An ADR is needed because the signature or `ObservedDay` changes. Owner of the semantics: WS01-T05; WS04 labeller must use the same rule.

**CP12 (`02-interfaces.md#signals`, `02-interfaces.md#verdict`).** `hold_last` has no encoding for "before the first sample". Proposed (section 3.5): `NaN`, read as unknown and completed by the physiological bounds in the interval semantics; predicates over `NaN` are unknown, never false. The treatment of infinite raw intervals (guards of WS01-T02) is WS01-T05's. `hold_last` keeps its signature.

**CG-1 alignment scope (`02-interfaces.md#time-and-units` rule 2 and the task text).** The task says all registry time values must be integer multiples of `T_s`. F0 has time-valued entries that are not window edges (`cuff_inflation_min = 30000` ms, `scale_sys = 30000` ms, `reorder_delay_ms = 30000` ms in W5) and would be rejected by that reading. Adopted: the rule applies to window parameters only (section 3.6). Proposed for WS01-T03: a `role` attribute on registry time entries (window, threshold, scale, monitor configuration) so that the load check is mechanical.

**CG-2 widening and the string form (`02-interfaces.md#time-and-units` rule 2, ADR-007).** With ceiling binning and aligned windows the exact `O[W,W]` already fires at one step; the widened form makes the antecedent true at two consecutive steps and, evaluated without anchoring, makes the string strictly stronger than the per-instance semantics exactly when the only qualifying observation lies at the anchor step (W4 b). Adopted: anchoring convention of section 3.7. For WS01-T02: state the relation between the template strings and the per-instance semantics. For WS01-T05: do not implement the string without anchoring. For WS01-T08: decide whether an ADR should say that the widening is redundant on the aligned grid or specify the case in which it matters.

**CG-3 anchor and deadline (`02-interfaces.md#verdict`, `pending_until_ms`: "anchor + Delta2 or W").** Two readings exist: device time `a + B`, or grid `t_{k_up(a)} + B`. Adopted: the grid decision time `t_d = t_{k_up(a)} + B` (section 3.7); the continuous deadline `a + B` is earlier by less than `T_s`. WS01-T05 to confirm.

**CG-4 latency bound (`02-interfaces.md#monitor`, `verdict_latency_bound_ms`; `02-interfaces.md#template`, `max_verdict_latency_param`).** Neither says whether the bound is event-time or end-to-end. Section 4.6 defines three terms; WS01-T05 to fix which is reported and which is in `max_latency_<id>`.

**CG-5 trace form of signals (`02-interfaces.md#trace-schema`).** `EventKind` has no kind for `auth`, `presence`, `day_end`, `cuff_health`; this document reads them as `Sample` with `signal` equal to the `SignalId` (section 2.2). WS04-T01 and WS05-T02 to confirm.

**CG-6 unavailability encoding (`02-interfaces.md#signals`, `hold_last`; `02-interfaces.md#evidencevector` rule).** `hold_last` returns `Sequence[float]`, which cannot carry `None`. Required: the monitor distinguishes value 0 with an available channel from an unavailable channel (section 3.5); a mask next to the array is proposed. WS05-T02.

**CG-7 direction of the phi_INT window (analisi §4.1 phi_INT; `02-interfaces.md#template`, `INT`).** The workshop form `d -> O[0,int_window](w or a_auth)` evaluated at the dispense step looks backwards, so `intake`, which follows the dispense, cannot satisfy it there; only `presence` and `auth` can. A deadline form (anchor at the dispense, decision at `int_window` later, same pattern as SCHED and RESP) would let `intake` contribute. WS01-T02 decides; the definition of `w` (section 2.4) works with both.

**CG-8 task wording of W3.** The pair 21:00:00.000 and 21:00:00.500 falls in two bins under the ceiling rule; this document uses 20:59:59.500 and 21:00:00.000 (section 7, W3). The wording of the task should be corrected.

**CG-9 CP6 (`02-interfaces.md#verdict`).** When the witness channel is unavailable at a deadline and no `auth` event exists, `w or a_auth` is unknown and the verdict is undecidable although the deadline elapsed (sections 2.4, 3.5). Settled in WS01-T05.

**CG-10 clock evidence (`02-interfaces.md#evidencevector`, `crypto_temporal`).** `timestamp_implausible` is one Boolean fed by late arrival, future stamp and replay-related inconsistency (sections 4.3 to 4.5), and there is no clock-health field (ADR-021 already lists this). WS02 to decide whether the fields are split; the monitor exports counts per source.

**CG-11 negative `TimeMs` (`02-interfaces.md#time-and-units`).** The warm-up prefix of section 5.5 uses negative times relative to the day start; the contract defines `TimeMs` as milliseconds since the start of the trace and does not say whether it is non-negative.

**CG-12 monitor configuration validity (`02-interfaces.md#monitor`, `MonitorConfig`).** Required at configuration time: `T_s > 0`, `T_day mod T_s = 0` (M2), `D >= 0`, and the alignment of window parameters at plan load (section 3.6). WS05 to implement.

**CG-13 duplicates and multiplicity (`02-interfaces.md#trace-schema`, `seq`).** Deduplication by `(source, seq)` is possible only when `seq` is present (section 3.4). With `seq = None` a replayed `dispense` inflates `c_d`; this belongs to the diagnosability matrix (WS02).

**CG-14 persistent counter violation.** A trailing counter above its limit stays above it for several steps after one excess dose (W6 shows the excess persisting across midnight). Whether that is one violation episode or one per step is WS01-T05's (verdict episodes) and WS01-T07's (alerts).

**Modelling choices made in this document, for review.**

- M1 `w` is the three-valued disjunction of `presence` and `intake`, not `intake` alone (section 2.4).
- M2 `T_s` divides `T_day`; the closing step `K` exists; events belong to `[0, T_day)` (section 3.1).
- M3 A late input is not used at all, even for steps not yet finalised (section 4.3).
- M4 An input with a future timestamp beyond `skew_max` is not used and is counted (section 4.4).
- M5 A measurement with the same device time as a dispense counts as pre-dose (section 5.3).
- M6 An instance belongs to the day of its anchor, even when it is decided in the next day (section 5.5).

**Input gap.** The artefact `docs/plan/workstreams/WS00-admin/outputs/WS00-T02.md` is missing; the scope source used is ADR-001 to ADR-003 (section 1.2).
