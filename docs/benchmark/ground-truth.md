# Ground truth of the benchmark: definition, conventions and what it shows

Document of WS04-T10. It states exactly how the ground truth of a benchmark day is computed
(`src/ralmon/benchmark/labelling.py`), the conventions that the evaluation (WS08) reads, and what the
construction does and does not show. Validation in this project is technical and pre-clinical: nothing here
is a clinical claim, and every number quoted below is fixture arithmetic (the fixture registry F0 of
ADR-027) used to explain a rule.

## Definition

The contract (`docs/plan/02-interfaces.md#trace-schema`, rule 1) and analisi section 5.1 define the truth on
two traces. The **latent trace** is the patient-day without cuff error, faults or attacks; the **observed
trace** is what the monitor and every baseline see.

* A **true C1 event** is a violation of phi_CP (the templates RANGE, SCHED, HOLD, COUNT and RESP) evaluated on
  the **latent** trace. It is computed by `label_latent_day`, never read from an observed day.
* A **true C2 or C3 event** is an injected event: one event per **realised** injection record, whether or not
  any channel could ever detect it (a silent cuff bias and an informed attacker stay in the truth).
* The monitor and every baseline receive an `ObservedDay` only. `label_latent_day` takes a `LatentDay`, the
  care plan, the injection records, the behaviour log and a runner; it has no observed-day parameter (test
  `test_labeller_takes_no_observed_day`).

How the C1 truth is computed. The labeller reuses the WS05 monitor on an **ideal observation** of the latent
day (`ideal_observation`): an `ObservedDay`-shaped view built only from latent values, with exact values,
`t_rx_ms == t_device_ms`, no quality, no sequence number and no noise. It supplies the signals that the five
phi_CP templates use and nothing else:

| Signal | Source in the latent day |
|---|---|
| `bp` | the held latent pressure at the latent MEASUREMENT instants (mode `scheduled`) or the latent grid (mode `dense`) |
| `meas` | one MEASUREMENT event per reading; no `meas` sample (impulses are events only, README issue I10) |
| `dispense` | the true DISPENSE events (the dispenser opened; not INTAKE) |
| `sched_tick` | the SCHEDULE_TICK events |
| `day_end` | the end-of-day impulse at `(day_index + 1) * T_day`, added when a template needs it (COUNT) |

The templates SYS and INT are not run: no `cuff_health`, `inflation_ms`, `presence` or `auth` exists in a
latent day, SYS and INT never become C1 (they are a system and an integrity specification, not the care
plan), and the presence hazard of ADR-054 (a held presence level that is stale) cannot reach a C1 label.
`derived` signals (`dose_count`, `meas_count`, `bp_pre`, `bp_drop`) are computed by the monitor. If a template
needs a signal that a latent day cannot supply, or the latent day lacks a pressure to hold, the labeller raises
`IdealObservationError`; it never guesses. Two readings in one grid bin of the monitor step are refused as
well, because hypothesis (A0) of `docs/formal/05-three-valued-semantics.md` section 2.1 (at most one pressure
per bin) would not hold.

The runner is an argument (`run_fn`, default `run_offline` with no calibrator and no forecaster), called as
`run_fn(day, plan, config, None, None, registry=registry, templates=phi_cp_templates)`. A stub is accepted so
that the mapping can be unit-tested. The labeller refuses a plan whose `registry_version` differs from
`MonitorConfig.registry_version` (`RegistryMismatchError`), takes `step_ms` from the configuration and asserts
that the registry agrees, and reads the window length `delta2` from the registry only when a RESP violation
needs it; a name that the registry declares but does not set raises a `LabellingError` that names it (no
number is substituted).

## Onset and end conventions

Time is the continuing axis `day_index * T_day + clock time` (ADR-017, ADR-053 (h)); `run_offline` starts the
monitor at the step `day_index * K`. The monitor emits one record per active instance per step: SCHED keeps
emitting until its horizon (the graded refinement), VIOLATED intervals may refine, and every record carries
`pending_until_ms` (`docs/formal/05` section 3.1, OP-T05-17).

**Which record defines an event.** One event per violated instance, identified by `instance_key`. The **first**
VIOLATED record of a key defines it; later VIOLATED records of the key must agree with it on `decided_at_ms`
and `pending_until_ms`, a record that leaves the definitive state (a key that is VIOLATED and later SATISFIED
or PENDING) is incoherent, and an incoherent runner is refused with `RunnerError`. PENDING, SATISFIED and
PREDICTED_VIOLATION records give nothing. Records of SYS and INT are ignored. Records outside the day, a
SCHED record whose instance the plan does not have, items that are not `VerdictRecord`, unsorted records and a
runner that raises are `RunnerError`.

**`onset_ms` and `end_ms`, by template kind** (not by the presence of `pending_until_ms`, which every real
record has):

| Violation | `onset_ms` | `end_ms` |
|---|---|---|
| RANGE, HOLD, COUNT limit | `decided_at_ms` | `None` |
| SCHED | the tick, `TemplateInstance.anchor_ms` of the plan | `pending_until_ms`, the deadline |
| RESP | the anchor of the instance: the plan's `anchor_ms` if the instance is in the plan, else `pending_until_ms - delta2` (instances are created at each DISPENSE, so they are not in the plan) | `pending_until_ms` |
| COUNT day end | the closing step of the day, `anchor_ms` of the plan instance | `pending_until_ms`, which is the same instant: `onset_ms == end_ms` |

`delta2` is the registry value, overlaid by the plan's own parameter record of RESP when it carries one. A RESP
instance that the monitor decides at its anchor (the pre-dose value that no pressure of the physiological domain
can answer, `docs/formal/05` Lemma 12) has `decided_at_ms` equal to the anchor and `end_ms` equal to the
deadline. INT is static in `docs/formal/02-templates.md` section 5.3 (ADR-026 proposed) and is not a care-plan
template, so it never gives a C1 event whatever its obligation window is. `end_ms` for the windowed obligations is
what WS08 uses as the deadline when it measures a detection delay "relative to the deadline" (analisi section 5.5);
`None` marks a point event.

**Instances open at the end of the day.** An instance whose decision step lies after the closing step (a RESP
window that crosses midnight, a SCHED deadline after 24:00) is decided early where the early-decision rule
applies and is otherwise PENDING at trace end: **it is not a violation** (`docs/formal/05` section 7.5 item 2; the
monitor and the labeller apply one rule). A day is labelled with empty history, as the monitor runs it
(ADR-046 is proposed): a counter that depends on the previous day under-counts, and a RESP window that ends
after the closing step is not labelled on either day. A dispense at exactly the start of the day (00:00) is
seen by the first step of the run, so it creates its HOLD and RESP instances on this day and counts in the trailing
24 h counter; by the day boundary (the day covers `(d * T_day, (d + 1) * T_day]`) it is not one of the dispenses of
the day that the day-end count adds up (case GT-10).

**Order of the truth.** The events of a day are sorted by `(onset_ms, cls, subtype, end_ms)` with `end_ms = None`
first; ties are broken by template, injected flag, group and record position, so the order is a function of the
content and not of the order of the arguments.

## Injection records versus truth

A C1 injection record is a statement of intent: it says what the generator did, and the truth is computed on the
latent trace. A spike that keeps every scheduled reading inside the band is in the injection log and not in the
truth (test `test_c1_truth_follows_latent_not_injection_intent`).

**Link table.** A record explains a C1 event (the event gets the subtype of the record, `injected = True` and the
`confounder_group` of the record) only if its template matches:

| Record subtype | Template of the event |
|---|---|
| `hypertensive_spike` | `range` |
| `drug_nonresponse` | `resp` |
| `hypotension_below_hold` | `hold` |
| `measurement_refusal` | `sched` |
| `double_take` (forced) | `count` (the limit, never the day-end obligation) |

The instant rule. The event time is `decided_at_ms` of the defining record. A record with the window
`[onset, end)` (a point record: the instant) explains the event iff `onset <= t < end + b`, where `b` is the
template latency bound of the monitor (`verdict_latency_bound_ms`, that is `max_latency + reorder delay`; a
function can be passed as `latency_bound_fn`). Three template-specific readings of the same idea:

* **RESP, `drug_nonresponse`.** The window of the record selects intakes by their intake time; the RESP anchor is
  the dispense, one lag earlier. A link of the form "the window contains the anchor" would miss a window that
  starts between the dispense and the intake, so the link goes through `details["intake_times_ms"]`: the
  k-th DISPENSE of the latent day is paired with its k-th INTAKE, and the record explains the event iff the
  intake of the dispense that created the instance is in the list. (When the numbers of DISPENSE and INTAKE
  events differ the pairing is unknown and the dispense instant stands in for the intake instant.)
* **HOLD, `hypotension_below_hold`.** HOLD is decided at the dispense but caused by the latest reading before it;
  the record explains the event if its window reaches the decision instant or the instant of the latest latent
  MEASUREMENT at or before it.
* **COUNT limit, `double_take`.** The counter looks back 24 h: a surplus dispense at 07:02 violates the limit at
  the next dispense, 21:00, when the trailing count is 3. The record explains the event iff its instant lies in
  `(decision - 24 h, decision]`, the window of `dose_count`.

Several candidates: the record whose own window contains the instant (without the extension) is preferred, then the
earliest onset, then the position. An unrealised record explains nothing. A C2 or C3 record never explains a C1
event. A realised `drug_nonresponse` record without `details["intake_times_ms"]`, or a C1 record of a subtype that is
not in the table, is a `LabellingError`.

**Cross-template consequences are not linked.** A hypotension window that pushes a reading below the band lower
limit also violates RANGE, but the table has no `hypotension_below_hold` to `range` entry: that RANGE event is
`spontaneous_range`, `injected = False`. The truth is the latent trace's, the label says which injection is the
documented cause only where the table names it.

**Natural subtypes** (an event no record explains; `injected = False`, no group):

| Event | Condition | Subtype |
|---|---|---|
| COUNT limit | a `DOUBLE_TAKE` entry of the behaviour log of this day whose surplus dispense lies in `(decision - 24 h, decision]` | `double_take` |
| COUNT day end | an `OMITTED` entry of the behaviour log of this day | `dose_omission` |
| anything else | | `spontaneous_<template id>` (`spontaneous_range`, `spontaneous_sched`, ...) |

A forced `OMITTED` slot (a scenario control of the confounder pairs) has no record: the log makes it
`dose_omission`, not injected, with no group. Entries of another day are not this day's slots.

**C2 and C3.** One event per realised record, from `record_to_ground_truth` (class and subtype of the spec, the
window or the instant, `injected = True`, no template, the group of the record). Unrealised records are absent from
the truth and present in the injection log. No C1 record is ever passed to `record_to_ground_truth` (it would
answer `injected = True` and no template).

**The `injection_log` sidecar** (`TruthRecord.injection_log`, one entry per record, in the order of the argument
`records`; WS08 reads it for per-magnitude and per-level results). The keys of each entry are
`cls`, `subtype`, `onset_ms`, `duration_ms`, `end_ms`, `magnitude`, `magnitude_unit`, `params`, `level`,
`confounder_group`, `realised`, `n_changed`, `evidence_paths` and `details` (from `injection_log`), and two keys
added by the labeller: `record_index` (the position of the record) and `truth_indices` (the positions in the
`ground_truth` sequence of the events the record explains or produced; empty for an unrealised record or one that
explains nothing). `behaviour_log` is the list of `BehaviourEntry.to_json()` dictionaries. `BenchmarkDay` has no
room for sidecars, so `assemble_benchmark_day` returns an `AssembledDay` with the `BenchmarkDay` and the
`TruthRecord` (what `write_truth` takes). The observed day is stored as given: it must be an `ObservedDay` of the
same patient, day, seed and care plan; an `ObservedStream` (which carries the latent pressure of each reading) is
refused.

## Modes

`scheduled` (default). `bp` exists only at the latent MEASUREMENT instants, with the exact held latent value, one
MEASUREMENT event each. Blood pressure between scheduled measurements does not violate phi_CP in this mode
(README, declared assumptions): the truth is "what the care plan would have seen had every scheduled
measurement been perfect". This is the mode of the headline results.

`dense`. `bp` and a MEASUREMENT event at every latent grid step. A spike between two scheduled readings is a range
event here, and a SCHED tick is satisfied by the reading of the next step (a refusal never violates SCHED in
this mode); RESP takes the pre-dose value from the latent pressure at the dispense step. Dense mode is a
sensitivity analysis, reported as such. The latent grid must hold one point per monitor step (a finer grid is
refused).

The latent day has `K` points and no closing step; its last value holds to the day end, and the `day_end` impulse
is the sample at `(d + 1) * T_day`. The same function labels a day at any `day_index` on the continuing axis.

## Non-circularity tests

The same specification defines the truth and the monitored constraints, so the argument must be exact (analisi
section 10 objection 1): the evaluation measures the loss caused by observation (sparse sampling, cuff error,
faults, attacks, a missing witness), not whether phi_CP is clinically right. The tests that answer the objection,
all in `tests/benchmark/test_ground_truth.py` (the reference evaluator is `tests/benchmark/reference_phi_cp.py`):

| Test | What it shows |
|---|---|
| `test_perfect_observation_equals_ground_truth_on_c1` | With zero cuff error, no fault, no attack and readings at the ticks, the set of `(template, anchor)` of the VIOLATED phi_CP verdicts on the observed day (built from the case data, not from the labeller) equals the C1 truth, on eighteen hand-computed cases and two days of the continuing axis |
| `test_noisy_observation_diverges_from_ground_truth` | Latent 139 with bias +3 reads 142 (a false positive); latent 141 with bias -3 reads 138 (a false negative), through the measurement process of WS04-T06 and the real monitor |
| `test_c1_truth_follows_latent_not_injection_intent` | A spike that keeps the reading in the band has a record and no event; one that crosses the edge has one `hypertensive_spike` event |
| `test_ground_truth_unchanged_by_observation_corruption` | Cuff noise, a C2 fault and a C3 attack on one latent day give the identical set of C1 events while the monitor's violated set changes |
| `test_undetectable_injection_still_in_ground_truth` | A silent cuff bias is a C2 truth event with an empty evidence signature while the monitor emits no SYS or INT violation |
| `test_independent_reference_evaluator_agrees` | Over 20 seeded random latent days (fixture prior, natural adherence, no injection; and the same days shifted across the band) the labeller and the independent evaluator give the same violated instances, anchors and deadlines |
| `test_labeller_takes_no_observed_day` | The labeller has no parameter, annotation or name that refers to an observed day |
| `test_import_boundaries` | Only `labelling.py`, `builder.py` and `validation.py` import `ralmon.monitor` or `ralmon.spec`; every other module of `src/ralmon/benchmark/` imports `ralmon.signals`, numpy, YAML and the standard library (and its own package) |

The reference evaluator (`tests/benchmark/reference_phi_cp.py`) evaluates the five templates on plain lists and a
dense grid from the formulas of `docs/formal/02-templates.md` and the semantics of `docs/formal/05`; it imports
nothing from `ralmon` (an AST test checks it) and shares no code with the monitor or the labeller. It is checked
against the golden patient-day (`docs/formal/golden/patient-day.yaml`, the five phi_CP violations of the worked
day) and against the verdict cases of `docs/formal/golden/verdicts.yaml` that it can express (SCHED, RESP and
COUNT cases with a definitive verdict).

## Residual circularity

What the evaluation does and does not show, stated so that it cannot be read as more.

* The **same specification** defines the truth and the monitored constraints. The tests show that observation
  loss is what is measured: with a perfect observation the monitor reproduces the truth exactly, and every
  divergence in the results is caused by what is added between the latent day and the monitor (sampling, error,
  faults, attacks). They do not show that phi_CP is clinically right. "A perfect observation equals the truth"
  holds by construction, since one specification defines both; what the test adds is that the ideal observation
  equals an independently built one and that the hand-computed cases agree.
* The **clinical validity of phi_CP rests on the registry review** (WS00-T07): the band, the hold threshold, the
  response window and the other values are literature proposals that no clinician has reviewed (registry 0.2.0,
  `review_status: unreviewed`, ADR-043). A result computed on them is a technical, pre-clinical result.
* The **independent reference evaluator** guards against a defect of the monitor defining its own truth. It
  cannot guard against a mistake that the specification and the reference share, because it is written from the
  same formulas.
* The **latent day is a model** (baseline, circadian component, autoregressive noise, one-compartment PK/PD,
  a Markov adherence model, all declared assumptions with priors that carry provenance); the truth inherits its
  limits.
* **Per-day labelling.** The truth of a day uses empty history, as the monitor does. Violations that need the
  previous day (a counter over 24 h across midnight) and RESP windows that end after the closing step are not
  labelled; the corresponding monitor results are not scored either.
* **Cross-template consequences** of an injection (a hypotension window that also leaves the band) are labelled
  `spontaneous_<template id>`, not injected.
* The label `injected` says that a record explains the event by the link table, not that the event would not have
  happened without it.
* The **scheduled mode** does not see pressure between readings; the dense mode is the sensitivity analysis.
* Undetectable cases stay in the truth (a silent bias, the informed attacker): the truth is not what a monitor can
  see, and the diagnosability matrix says which cases no channel can separate.
