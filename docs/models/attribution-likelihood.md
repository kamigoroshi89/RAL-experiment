# Attribution as a likelihood table: model, cells, sources and sensitivity design

Document WS02-T06. It is the normative specification of the attribution method of the paper (ADR-074): the posterior over the SUBTYPES of the causes C1, C2 and C3 given the evidence vector, computed from a likelihood table, its class sum `p_kappa`, the set of subtypes, and the label `kappa` derived from them. The machine-readable table is `configs/attribution_likelihood.yaml`; the completeness tests are `tests/attribution/test_likelihood_spec.py`. The hierarchical rule of `docs/models/attribution-rule.md` stays as the reference rule and the comparison method (`ours-hier`); the reading classes and the relevance map of that document are inputs of this one, not repeated. The implementation is WS05-T12 (the attributor), WS05-T14 (the conformal set calibrator) and WS08-T09 (the metrics); no production code is written here.

Validation in this project is technical and pre-clinical. Nothing in this document is a clinical, device or probability value: every number that is not structural is an `awaiting_human_value` row with a sensitivity range taken from the research report (`docs/benchmark/evidence/likelihood-attribution.md`, sections 1.5, 6, 9, 10; the prototype is in `docs/benchmark/evidence/scripts/likelihood/`). A sensitivity range is a sensitivity, not a proposal.

## Status of the numbers, in one table

| kind | what | how it is written |
|---|---|---|
| structural | a field raised by construction by a subtype; a field raised by no subtype | `1-eps` and `eps`, with `eps` a parameter; 19 structural cells are explicit, every unlisted (subtype, field) pair is the structural zero `eps` |
| conditional | a field raised only when a stated condition holds (lease, deadline, sequence provision, time bound, profile, attacker behaviour) | `awaiting_human_value`, with the form `eps + (1-2 eps) * qc` (or `1-qc`, `q_stale`, `delta`); 37 conditional cells (tokens C, Cn, S, V) |
| natural | the coincidence of two consecutive cuff readings | `max(rep_nat, eps)`, `rep_nat` a sensitivity parameter; 30 natural-repeat cells, one per component that can violate a cuff-reading template (apart from `stuck_at`), with a single parameter |
| priors | class priors, `pi(subtype given class)`, thresholds | `awaiting_human_value` with a sensitivity range, designs labelled `illustrative` |

The file has 86 explicit cells over 38 components of 35 subtypes: 19 structural and 67 awaiting (37 conditional plus 30 natural-repeat). `verified_by` is `null` in every row: no human has recorded a check. No row cites the literature; a row of source type `literature` would need a verified bibliography key (`bib_key`), and none has one.

## The model

**Components and subtypes.** A *subtype* is an identifier of the vocabularies (below). A *component* is a subtype at one knowledge level: `replay`, `dispense_forgery` and `presence_spoof` have the components `naive` and `informed` (threat model, Knowledge levels), every other subtype has one component. The cells are defined per component. A subtype posterior is the sum over its components, so the output set names subtypes only.

For a violated instance of template `t` with evidence vector `e`:

```
p(s | e, t)  proportional to  prior_t(class(s)) * pi(s | class(s), t) * product over f in R_t of P(class_f | s)
```

- `s` runs over the components that can violate `t` (the column "templates" of the catalogue below; the fault model's "Effects on templates" and the threat model's "templates it can change").
- `prior_t(c)`: the class prior, restricted to the classes that have a component at `t` and renormalised; a class with no component at `t` (C1 at `sys` and at `int`) has prior 0.
- `pi(s | c, t)`: the weight of the component inside its class, normalised over the components of that class applicable at `t` (the designs `uniform`, `quiet_rare`, `quiet_common` below).
- `R_t`: the cells read for `t`: the fields of the table below minus the fields masked in the run, where the pair (`system.ble_link_quality`, `system.seq_gap`) counts as ONE joint cell in the reference (below).
- `P(class_f | s)`: the cell: the probability that field `f` has the reading class `class_f` in {A, D} under `s`; `P(D | s) = 1 - P(A | s)`.
- **A field whose reading is `None` has no cell in the product and contributes the factor 1** (the rule of `#evidencevector`: unavailable is never a negative reading). The same holds for an out-of-domain reading and for the class K of `system.node_lifecycle` (a deliberate transition; no subtype of the model produces it).
- **The class posterior** `p_kappa(c)` is the sum of `p(s | e, t)` over the components of the class; it fills `Alert.p_kappa`. The subtype posterior (the sum over the levels of a subtype) is what `posterior_subtypes` returns.
- **The independence assumption.** The read fields are treated as independent given the component (naive Bayes), with one exception that is part of the REFERENCE: `system.ble_link_quality` and `system.seq_gap` overlap (the delivery ratio is exactly 1.0 when no value is missing) and are ONE joint cell, so they are not multiplied as two factors (ADR-074 amendment 3; ADR-075). The independence of the other fields is an **ASSUMPTION** of the model, not a finding: it is false for fields that a single event raises together. Two sensitivity variants relax or restore it: the fully independent product (the pair counted as two factors, which double counts one dropout) and the cross-device group (`cross_device_signal_quality`, with the common cause `ecg_noise`). The assumption is stated in the paper with its sensitivity.

**Pseudo-code** (the reference that WS05-T12 implements; `tests/attribution/test_likelihood_spec.py` holds a test-local transcription used to check hand-computed examples).

```
def posterior_subtypes(t, reading_classes, params, design, mask):
    comps = [s for s in COMPONENTS if t in s.templates]               # applicable at t
    classes = {s.cls for s in comps}
    prior_t = {c: prior[c] / sum(prior[k] for k in classes) for c in classes}
    for s in comps:
        pi = weight(s, design) / sum(weight(x, design) for x in comps if x.cls == s.cls)
        logp[s] = log(prior_t[s.cls]) + log(pi)
        for f in reads[t] - mask:
            r = reading_classes[f]                                    # 'A', 'D' or None
            if r is None: continue                                    # factor 1
            pa = cell(s, f, params)                                   # eps, 1-eps or a conditional form
            logp[s] += log(pa if r == 'A' else 1 - pa)
        # REFERENCE: the pair (system.ble_link_quality, system.seq_gap) is one joint term, log P(joint class | s), not two factors;
        # variant reference_plus_cross_device: the terms of (pulse_vs_ecg_hr_diff, ecg_sqi, ppg_sqi) are replaced the same way;
        # variant fully_independent: every field is its own factor
    p = softmax(logp)
    sub[subtype(s)] += p[s] for each component s
    p_kappa[class(s)] += p[s] for each component s                    # equals the sum of the subtype posteriors
    return sub, p_kappa
```

**The set and the label.**

- *Set of subtypes* (`Alert.cause_set`): the subtypes sorted by decreasing posterior (ties by name), taken until the cumulative probability reaches `cumulative_level` (a sensitivity value). The calibrated version replaces the level with a conformal threshold (section Sets and conformal calibration).
- *UNDETERMINED as a set*: for a method that abstains (`ours-hier` with `kappa = UNDETERMINED`), the set is the FULL set of the subtypes applicable at the template, `full_set(t)`. This is the convention of the metrics (coverage and mean set size per stratum), not a stored value.
- *Abstention label* `kappa`: the class with the largest `p_kappa` if that value is at least `tau`, otherwise `UNDETERMINED`; a tie at the maximum is `UNDETERMINED`. `UNDETERMINED` is not a key of `p_kappa` and not a cause of the model.
- `kappa` and `p_kappa` are at class level; the subtype posterior is the finer output. Where nothing is raised, the class posterior is the prior (see the failure modes).

## Reading classes

The classes of `attribution-rule.md` (A asserted, D denied, U unavailable; K treated as U; F and G of `system.ble_link_quality` count as D in the independent table) are used unchanged for the fields of 0.1.0. The three fields that `#evidencevector` 0.2.0 adds for this attributor have their classes defined here:

| field | A | D | U |
|---|---|---|---|
| `signal_quality.cuff_value_repeated` | True | False | `None` (no declared resolution, no previous reading, or the latest reading outside the evidence window; D-16) |
| `dispenser.interval_since_previous_ms` | value at or below `dispense_bounce_interval_ms` | value above it | `None` (first opening of a stream, key absent; D-15) |
| `dispenser.content_change` | value equal to 0 (nothing left the dispenser: a bounce) | any other finite value (a release) | `None` (no content sensing, key absent) |

The dispenser group describes the LATEST accepted opening of the evidence window (D-15), so an earlier bounce in the same window is not seen by it. The interval is device-reported: a forged dispense can copy the bounce timing, a declared limit. The table gives the structural zero `eps` to every C3 subtype for the interval, which does not model attacker timing.

## Fields read per template, and the masks

The relevance map of `attribution-rule.md` (fields marked E, s, b, q, r) is the set `R_t`, plus two additions that apply masks by data scope. The extractor computes the dispenser group and `signal_quality.cuff_value_repeated` for every template and does not gate them (hand-over of WS05-T13); the table gates them:

- **Dispenser fields** (`dispenser.interval_since_previous_ms`, `dispenser.content_change`) are read only for `hold`, `count`, `resp` and `int`, the templates whose data scope holds the dispenser. For `range`, `sched` and `sys` the cell is not read.
- **`signal_quality.cuff_value_repeated`** is read only for the templates that read a cuff measurement: `range`, `sched`, `hold`, `resp`, `sys`. For `count` and `int` the cell is not read. The cell is also `None`-aware: the reading is `None` when the profile declares no display resolution, when fewer than two readings of the cuff stream exist, or when the latest accepted reading lies outside the evidence window, and then it contributes the factor 1.
- **Witness fields** (`witness.identity_confirmed`, `witness.intake_observed`) are read only for `resp` (backing of the response), as in the relevance map; for `int` they are context (AD-3), so the `presence_spoof` cells exist but no template reads them.
- **Mask A4** (ablation of the embodied channel; `evidence-channels.md`, Ablation A4 mask): the cells of the fields that become `None` are removed, that is, read as unavailable with the factor 1: `witness.identity_confirmed`, `witness.intake_observed`, `system.nav_task_failed`, `system.manip_task_failed` (`system.battery_low` and `witness.robot_present` are not read). The four aggregate `system` fields (`node_lifecycle`, `diagnostics_ok`, `liveliness_ok`, `qos_deadline_missed`) are recomputed by the extractor over the device nodes and keep their cells. The set of applicable subtypes does not change under A4: the robot-side subtypes become less distinguishable and the sets larger, which is the quantity A4 measures. `mask` of the pseudo-code is this set (in `masks.a4.cells_removed`).

| field | range | sched | hold | count | resp | sys | int |
|---|---|---|---|---|---|---|---|
| `system.node_lifecycle` | read | read | read | read | read | read | read |
| `system.diagnostics_ok` | read | read | read | read | read | read | read |
| `system.liveliness_ok` | read | read | read | read | read | read | read |
| `system.qos_deadline_missed` | read | read | read | read | read | read | read |
| `system.ble_link_quality` | read | read | read | read | read | read | read |
| `system.nav_task_failed` | - | read | read | - | read | - | read |
| `system.manip_task_failed` | - | read | read | - | read | - | read |
| `system.seq_gap` | read | read | read | read | read | read | read |
| `signal_quality.ecg_sqi` | read | - | read | - | read | read | - |
| `signal_quality.ppg_sqi` | read | - | read | - | read | read | - |
| `signal_quality.cuff_error_code` | read | read | read | - | read | read | - |
| `signal_quality.cuff_value_repeated` | read | read | read | - | read | read | - |
| `cross_device.pulse_vs_ecg_hr_diff` | read | - | read | - | read | read | - |
| `witness.identity_confirmed` | - | - | - | - | read | - | - |
| `witness.intake_observed` | - | - | - | - | read | - | - |
| `crypto_temporal.authenticated` | read | read | read | read | read | read | read |
| `crypto_temporal.seq_repeat` | read | read | read | read | read | read | read |
| `crypto_temporal.timestamp_implausible` | read | read | read | read | read | read | read |
| `dispenser.interval_since_previous_ms` | - | - | read | read | read | - | read |
| `dispenser.content_change` | - | - | read | read | read | - | read |

(Contract order. `read` = a cell of the table is used for the template. The C1 class is impossible at `sys` and `int`, no C1 cause being catalogued there.)

## The subtype catalogue

The catalogue is the union of the C2 identifiers of `docs/models/fault-model.md` (Subtype vocabulary, 17), the C3 identifiers of `docs/models/threat-model.md` (Subtype vocabulary, 7) and the C1 labels of the benchmark: the five injected subtypes of `ralmon.benchmark.inject_c1` (`double_take` is both an injected subtype and a natural label of the labeller), the natural label `dose_omission`, and one label `spontaneous_<template>` for each of the five C1-capable templates (`range`, `sched`, `hold`, `count`, `resp`; the labeller names a violation with no injection behind it by the template). A test compares the file with these sources. The templates of a component are those where the fault model's "Effects on templates" lists the outcome violated (or shifted, for a loss that makes an instance decide on an older value), and the threat model's "templates it can change". `in benchmark v1` marks the subtypes that benchmark v1 produces.

| subtype | class | levels | templates it can violate | in benchmark v1 |
|---|---|---|---|---|
| `hypertensive_spike` | C1 | - | `range` | yes |
| `drug_nonresponse` | C1 | - | `resp` | yes |
| `hypotension_below_hold` | C1 | - | `hold` | yes |
| `measurement_refusal` | C1 | - | `sched` | yes |
| `double_take` | C1 | - | `count` | yes |
| `dose_omission` | C1 | - | `count` | yes |
| `spontaneous_range` | C1 | - | `range` | yes |
| `spontaneous_sched` | C1 | - | `sched` | yes |
| `spontaneous_hold` | C1 | - | `hold` | yes |
| `spontaneous_count` | C1 | - | `count` | yes |
| `spontaneous_resp` | C1 | - | `resp` | yes |
| `ble_dropout` | C2 | - | `sched`, `hold`, `count`, `resp` | yes |
| `stuck_at` | C2 | - | `range`, `hold`, `resp` | yes |
| `cuff_silent_bias` | C2 | - | `range`, `hold`, `resp` | yes |
| `ecg_noise` | C2 | - | none | yes |
| `nav_delay` | C2 | - | `sched`, `hold`, `resp` | yes |
| `manipulation_failure` | C2 | - | `sched`, `hold`, `resp` | yes |
| `dispenser_bounce` | C2 | - | `hold`, `count`, `resp`, `int` | yes |
| `cuff_detached` | C2 | - | `sched`, `hold`, `resp`, `sys` | yes |
| `process_kill` | C2 | - | `sched`, `hold`, `count`, `resp` | no |
| `message_drop` | C2 | - | `range`, `sched`, `hold`, `count`, `resp`, `int` | no |
| `localisation_noise` | C2 | - | `sched`, `hold`, `resp` | no |
| `impossible_goal` | C2 | - | `sched`, `hold`, `resp` | no |
| `link_delay` | C2 | - | `sched`, `hold`, `resp`, `int` | no |
| `out_of_order` | C2 | - | none | no |
| `clock_skew` | C2 | - | `sched`, `hold` | no |
| `battery_depleted` | C2 | - | `sched`, `hold`, `resp` | no |
| `uncommanded_lifecycle_transition` | C2 | - | `sched`, `hold`, `count`, `resp` | no |
| `replay` | C3 | naive, informed | `range`, `sched`, `hold`, `resp`, `sys` | yes |
| `injection_naive` | C3 | - | `range`, `sched`, `hold`, `resp`, `sys` | yes |
| `injection_informed` | C3 | - | `range`, `hold`, `resp`, `sys` | yes |
| `dispense_forgery` | C3 | naive, informed | `hold`, `count`, `resp`, `int` | yes |
| `presence_spoof` | C3 | naive, informed | `int` | yes |
| `dispenser_physical_tamper` | C3 | - | `hold`, `count`, `resp`, `int` | no |
| `timestamp_manipulation` | C3 | - | `range`, `sched`, `hold`, `resp` | no |

Two C2 subtypes are applicable nowhere: `ecg_noise` (no template reads `hr_ecg`, so the fault changes no verdict) and `out_of_order` (the reorder buffer absorbs it within the bound). They stay in the catalogue because the fault model names them and because `ecg_noise` is the common cause of the grouped cross-device variant. At `sys`, the C2 subtype is `cuff_detached` only, through the variant of the fault model that reports a measurement with a failed cuff health (G-SYS-3); this is a judgement of this document (Notes of the task).

## The cells

A cell is `P(A | component, field)`. The token says how it is formed:

| token | form | meaning |
|---|---|---|
| `Z` | `eps` | structural zero: the field is in neither the raised nor the conditional column of the row of the component; the default of every unlisted pair |
| `R` | `1-eps` | raised by construction (column raised of the fault-to-evidence or attack-to-evidence table) |
| `C` | `eps + (1-2 eps) * qc` | conditional raise; the condition of the row (LC, SEQ, DSP, D-5, ...) holds with probability `qc` |
| `Cn` | `eps + (1-2 eps) * (1-qc)` | the other branch of an either-or: a naive forger either repeats an accepted sequence number (`seq_repeat`) or jumps ahead and leaves a gap (`seq_gap`) |
| `S` | `eps + (1-2 eps) * q_stale` | stale report of the driver (profile `driver_with_diagnostics`) |
| `N` | `max(rep_nat, eps)` | natural repeat of the cuff reading |
| `V` | `eps + (1-2 eps) * delta` | diverted dose (C1) |

Every cell of the file has a `source_type` (fault-model row, threat-model row, device specification, literature, design choice), a `source_ref`, a `status` (`structural` or `awaiting_human_value`), `needs` (gab, literature, device_specification, none) and, for awaiting rows, a `sensitivity_range`. The cells that the components raise:

| component | class | templates | cells (field, token, condition) |
|---|---|---|---|
| `hypertensive_spike` | C1 | range | `cuff_value_repeated` N (NATREP) |
| `drug_nonresponse` | C1 | resp | `cuff_value_repeated` N (NATREP); `intake_observed` V (DIVERT) |
| `hypotension_below_hold` | C1 | hold | `cuff_value_repeated` N (NATREP) |
| `measurement_refusal` | C1 | sched | `cuff_value_repeated` N (NATREP) |
| `double_take` | C1 | count | none (silent) |
| `dose_omission` | C1 | count | none (silent) |
| `spontaneous_range` | C1 | range | `cuff_value_repeated` N (NATREP) |
| `spontaneous_sched` | C1 | sched | `cuff_value_repeated` N (NATREP) |
| `spontaneous_hold` | C1 | hold | `cuff_value_repeated` N (NATREP) |
| `spontaneous_count` | C1 | count | none (silent) |
| `spontaneous_resp` | C1 | resp | `cuff_value_repeated` N (NATREP); `intake_observed` V (DIVERT) |
| `ble_dropout` | C2 | sched, resp, hold, count | `node_lifecycle` R; `diagnostics_ok` S (STALE); `liveliness_ok` C (LC); `qos_deadline_missed` C (LC); `ble_link_quality` R; `seq_gap` C (SEQ); `cuff_value_repeated` N (NATREP) |
| `stuck_at` | C2 | range, hold, resp | `cuff_value_repeated` R (REP) |
| `cuff_silent_bias` | C2 | range, hold, resp | `cuff_value_repeated` N (NATREP) |
| `ecg_noise` | C2 | none | `ecg_sqi` C (SQI); `pulse_vs_ecg_hr_diff` R |
| `nav_delay` | C2 | sched, resp, hold | `nav_task_failed` C (D5); `cuff_value_repeated` N (NATREP) |
| `manipulation_failure` | C2 | sched, resp, hold | `manip_task_failed` R; `cuff_value_repeated` N (NATREP) |
| `dispenser_bounce` | C2 | hold, count, resp, int | `cuff_value_repeated` N (NATREP); `interval_since_previous_ms` C (DSP); `content_change` R (DSP) |
| `cuff_detached` | C2 | sched, resp, hold, sys | `node_lifecycle` R; `cuff_error_code` R; `cuff_value_repeated` N (NATREP) |
| `process_kill` | C2 | sched, hold, resp, count | `node_lifecycle` C (TARGET); `diagnostics_ok` S (STALE); `liveliness_ok` C (LC); `qos_deadline_missed` C (LC); `cuff_value_repeated` N (NATREP) |
| `message_drop` | C2 | sched, hold, resp, count, int, range | `diagnostics_ok` S (STALE); `liveliness_ok` C (LC); `qos_deadline_missed` C (LC); `ble_link_quality` C (DEGRADE); `seq_gap` C (SEQ); `cuff_value_repeated` N (NATREP) |
| `localisation_noise` | C2 | sched, resp, hold | `nav_task_failed` C (D5); `cuff_value_repeated` N (NATREP) |
| `impossible_goal` | C2 | sched, resp, hold | `nav_task_failed` R; `cuff_value_repeated` N (NATREP) |
| `link_delay` | C2 | sched, hold, resp, int | `qos_deadline_missed` C (LC); `cuff_value_repeated` N (NATREP); `timestamp_implausible` R |
| `out_of_order` | C2 | none | `timestamp_implausible` C (BOUND) |
| `clock_skew` | C2 | sched, hold | `cuff_value_repeated` N (NATREP); `timestamp_implausible` C (BOUND) |
| `battery_depleted` | C2 | sched, hold, resp | `liveliness_ok` C (LC); `qos_deadline_missed` C (LC); `cuff_value_repeated` N (NATREP) |
| `uncommanded_lifecycle_transition` | C2 | sched, hold, resp, count | `node_lifecycle` R; `diagnostics_ok` S (STALE); `cuff_value_repeated` N (NATREP) |
| `replay_naive` | C3 | sched, hold, resp | `cuff_value_repeated` N (NATREP); `seq_repeat` R; `timestamp_implausible` R |
| `replay_informed` | C3 | range, hold, resp, sys | `cuff_value_repeated` N (NATREP); `pulse_vs_ecg_hr_diff` C (PULSE); `authenticated` R (AUTHDEP) |
| `injection_naive` | C3 | range, hold, resp, sched, sys | `seq_gap` Cn (SEQ); `cuff_value_repeated` N (NATREP); `pulse_vs_ecg_hr_diff` C (PULSE); `authenticated` R (AUTHDEP); `seq_repeat` C (SEQ); `timestamp_implausible` C (LATE) |
| `injection_informed` | C3 | range, hold, resp, sys | `cuff_value_repeated` N (NATREP); `authenticated` R (AUTHDEP) |
| `dispense_forgery_naive` | C3 | count, hold, resp, int | `seq_gap` Cn (SEQ); `cuff_value_repeated` N (NATREP); `intake_observed` C (COLOC); `authenticated` R (AUTHDEP); `seq_repeat` C (SEQ) |
| `dispense_forgery_informed` | C3 | count, hold, resp, int | `cuff_value_repeated` N (NATREP); `intake_observed` C (COLOC); `authenticated` R (AUTHDEP) |
| `presence_spoof_naive` | C3 | int | `identity_confirmed` C (IDCHECK) |
| `presence_spoof_informed` | C3 | int | none (silent) |
| `dispenser_physical_tamper` | C3 | count, hold, resp, int | `cuff_value_repeated` N (NATREP); `intake_observed` C (COLOC) |
| `timestamp_manipulation` | C3 | sched, hold, range, resp | `cuff_value_repeated` N (NATREP); `authenticated` R (AUTHDEP); `timestamp_implausible` C (BOUND) |

Notes on individual cells.

- **C1 raises no evidence field** (analisi 4.5), whatever its subtype: its cells are all `Z`, with two exceptions. The witness `intake_observed` has the diversion share `delta` for the C1 subtypes that can be read at `resp` (`V`; 0 in the benchmark, whose adherence model has no dispensed-but-not-taken case), and the cuff repeat has the natural probability `rep_nat` (`N`). A C1 event never causes a stale report.
- **Silent faults** raise no field: `cuff_silent_bias` has no cell, `dispenser_bounce` raises only the dispenser group, and `stuck_at` raises only `signal_quality.cuff_value_repeated`. For `stuck_at` the condition REP of the fault model conditions the AVAILABILITY of the reading (the profile declares a resolution and a previous reading exists), not its value: given a reading, a frozen window repeats it by construction (`R`).
- **`dispenser_bounce`.** `content_change` is zero by construction (`R`, where the dispenser has content sensing); the interval is below `dispense_bounce_interval_ms` only if the latest opening of the window is the bounce (`C`, condition DSP). A double take has a release (D) and an interval above the threshold (D, `Z`); a forged dispense has no `content_change` (`None`).
- **Naive forgery and sequence evidence.** `injection_naive` and `dispense_forgery` (naive) repeat an accepted number (`seq_repeat`, `C`) or jump ahead and leave a gap (`seq_gap`, `Cn`); the informed level is coherent on the sequence and on the timestamps (flags `fresh_metadata`) and raises only `crypto_temporal.authenticated`, which is `None` in an unauthenticated deployment (factor 1).
- **`crypto_temporal.authenticated`** is a deployment property: it is `None` for a device that does not authenticate; the cells `R` of the C3 subtypes apply only when the reading exists.
- **The witness cells of C3** (`intake_observed` for `dispense_forgery` and `dispenser_physical_tamper`, `identity_confirmed` for the naive `presence_spoof`) are conditional (`C`): the witness reads False only when the robot is co-located and saw nothing, and False also arises from a patient who diverted the dose or a perception false negative (threat model, TX-4).

### What each awaiting row needs, and from whom

- **gab**
  - witness reads False only when the robot is co-located and saw nothing: 3 cell(s), components `dispense_forgery_informed`, `dispense_forgery_naive`, `dispenser_physical_tamper`
  - task layer reports lateness as failure (D-5): 2 cell(s), components `localisation_noise`, `nav_delay`
  - how the robot checks identity (D-6): 1 cell(s), components `presence_spoof_naive`
  - a naive injected message carries a stale or future stamp: 1 cell(s), components `injection_naive`
  - an informed attacker does not patch the pulse rate: 2 cell(s), components `injection_naive`, `replay_informed`
- **literature**
  - diverted dose (delta): 2 cell(s), components `drug_nonresponse`, `spontaneous_resp`
- **device_specification**
  - time evidence raised only beyond the bound D or skew_max (clock_skew, out_of_order, timestamp_manipulation): 3 cell(s), components `clock_skew`, `out_of_order`, `timestamp_manipulation`
  - link metric degraded by a long run of losses: 1 cell(s), components `message_drop`
  - interval below T_b for a bounce (dispenser reports the key, D-15): 1 cell(s), components `dispenser_bounce`
  - conditional raise of `liveliness_ok` / `qos_deadline_missed` (lease and deadline condition LC): 9 cell(s), components `battery_depleted`, `ble_dropout`, `link_delay`, `message_drop`, `process_kill`
  - natural repeat probability of the cuff reading (rep_nat): 30 cell(s), components `battery_depleted`, `ble_dropout`, `clock_skew`, `cuff_detached`, `cuff_silent_bias`, `dispense_forgery_informed`, `dispense_forgery_naive`, `dispenser_bounce`, `dispenser_physical_tamper`, `drug_nonresponse`, `hypertensive_spike`, `hypotension_below_hold`, `impossible_goal`, `injection_informed`, `injection_naive`, `link_delay`, `localisation_noise`, `manipulation_failure`, `measurement_refusal`, `message_drop`, `nav_delay`, `process_kill`, `replay_informed`, `replay_naive`, `spontaneous_hold`, `spontaneous_range`, `spontaneous_resp`, `spontaneous_sched`, `timestamp_manipulation`, `uncommanded_lifecycle_transition`
  - conditional raise of `seq_gap` / `seq_repeat` (sequence condition SEQ; naive forger repeat or jump): 6 cell(s), components `ble_dropout`, `dispense_forgery_naive`, `injection_naive`, `message_drop`
  - ECG device reports a quality index: 1 cell(s), components `ecg_noise`
  - stale report of the driver (q_stale; liveness contract): 4 cell(s), components `ble_dropout`, `message_drop`, `process_kill`, `uncommanded_lifecycle_transition`
  - node_lifecycle of a killed device target: 1 cell(s), components `process_kill`

The structural cells need only `eps`. The parameters themselves (below) also need gab or a device specification.

## Grouped cells (the reference pair and the sensitivity variants)

Two groups of fields are not independent given a single event. The pair `ble_seq_gap` is the REFERENCE of the table; the cross-device group is the only variant that relaxes the independence assumption further; the fully independent product is a labelled sensitivity variant (`grouped_cells` in the file; sensitivity `grouped_variant` with the values `reference`, `fully_independent`, `reference_plus_cross_device`).

**`ble_seq_gap`: `system.ble_link_quality` with `system.seq_gap` (ADR-074 amendment 3; REFERENCE).** The two fields overlap: the delivery ratio is exactly 1.0 when no value of the observed span is missing, so a gap implies a ratio below 1 (and an asserted gap with a complete ratio is an extractor defect, RS-2). The reference reads them as ONE joint class of four values, in the order (`ble_link_quality`, `seq_gap`), A asserted and D denied: `clean` (D,D), `gap` (D,A: class G, a value is missing and the link is not degraded), `degraded` (A,D) and `gap_degraded` (A,A). The joint probability of a component is, with `K = 4` joint classes and the weights of its modes summing to 1:

```
P(j | s) = sum over the modes m of s of  weight(m) * [ (1 - eps) * 1(j = m)  +  eps / (K - 1) * 1(j != m) ]
```

so it sums to 1 over the four joint classes (this is `_jdist` of the prototype, `likelihood_attr.py`, with `eps/3`). A component with no entry in the modes has the single mode `clean` with weight 1. **None rule:** if one member is `None` the joint probability is summed over (marginalised over) the unavailable member; if both are `None` the factor is 1. The explicit cells of `system.ble_link_quality` and `system.seq_gap` in `cells` are the marginals that the fully independent variant multiplies and the source record of the modes; in the reference they are not multiplied.

| component | modes (joint class: probability) |
|---|---|
| `ble_dropout` | gap_degraded: qc, degraded: 1-qc |
| `message_drop` | gap: qc, clean: 1-qc |
| `injection_naive` | gap: 1-qc, clean: qc |
| `dispense_forgery_naive` | gap: 1-qc, clean: qc |

The modes are inherited from the research prototype (variant G1) and re-expressed on the two split fields; the probabilities are `qc` and `1-qc`, so the cell has no number of its own, and the modes of `message_drop`, `injection_naive` and `dispense_forgery` (naive) are design choices that need gab. `crypto_temporal.seq_repeat` is outside the pair (it is integrity evidence, `system.seq_gap` is system evidence). **A difference to know:** for `message_drop` the fault model lists the link degradation and the gap as two independent conditions, so the independent product allows a degraded link without a gap and both together with probability `qc^2`; the reference modes make the loss either seen as a gap with a link that is not degraded (`gap`) or unseen (`clean`), and give a degraded link without a gap only the leak `eps/3`. The fully independent variant restores the fault model's reading.

**`cross_device_signal_quality`: `cross_device.pulse_vs_ecg_hr_diff` with `signal_quality.ecg_sqi` and `signal_quality.ppg_sqi` (variant `reference_plus_cross_device`; independent in the reference).** Under this variant the three fields (for `range`, `hold`, `resp`, `sys`) are read as one joint class of eight values (each member A or D, in the order diff, ecg_sqi, ppg_sqi). For a component with no modes it is the product of its marginals; for the common cause `ecg_noise` the subtype is made applicable at those templates as a co-occurrence nuisance (it violates no template by itself) with the modes `A,A,D: qc` and `A,D,D: 1-qc`, and the same formula with `K = 8` (`eps/7` on every other joint class), which sums to 1. **None rule:** the same as above: summed over the unavailable members, factor 1 when all three are `None`. The reason is the evidence confound of the fault model: a noisy ECG during a real clinical violation raises the cross-device difference, which the independent product would count as integrity evidence.

The two rows are `awaiting_human_value`; their sensitivity ranges are `grouped`, `independent` (cross-device: reference `independent`; ble_seq_gap: reference `grouped`). The normalisation of every joint, for every component and every pattern of available members, is a test.

## System diagnostics: the two profiles

`system.diagnostics_ok` has two cases, set by the device profile (`settings.device_profile.diagnostics_profile` of the benchmark manifest; the profile of the real deployment):

- **`driver_with_diagnostics`.** The driver or bridge node of each device reports `ok` or `stale` under the liveness contract of `evidence-channels.md` (Bridge node: an idle on-demand device reports `ok` and is never `stale`; `stale` means expected to publish and silent beyond `stale_lease_ms`). The cell is a structural zero (`eps`: `ok` with probability `1-eps`) for C1 and for the silent faults (`cuff_silent_bias`, `stuck_at`, `dispenser_bounce`) and for `cuff_detached` (its failed attempts are messages), and it is a CONDITIONAL cell (`S`: `eps + (1-2 eps) * q_stale`) for the subtypes that silence a device with an open session: `ble_dropout`, `message_drop`, `process_kill`, `uncommanded_lifecycle_transition`. The conditional cell is not near 1: a dropout of an idle device loses nothing and reports nothing, and a dropout shorter than the lease leaves `ok` (WS04-T18, measured in the generator). `P(stale | C1) = eps` is the chance that a dropout of an unrelated device coincides with the alert. The research prototype used the raised cell `1-eps` for these subtypes; the range of `q_stale` is the `qc` grid and the prototype's value is outside it (Notes). The profile needs the rows `driver_stale_lease_ms` and `driver_period_ms` of `configs/benchmark/generator_design.yaml`, which are `awaiting_human_value`; a build with this profile is refused while they are.
- **`without_diagnostics`.** No driver report: the field is `None` for every instance, it is not read, and the factor is 1 (never a default `ok`).

A report `ok` proves that the node and the link are alive, not that the sensor measures correctly; it is the expected reading under the silent faults, which is why `diagnostics = ok` has likelihood close to 1 under them and does not exclude them. `P(D | C2)`, the probability of `ok` under the C2 mixture, stays strictly above `eps` at every template (tested).

## Priors

**Class priors** `prior(c)`: designs `uniform` (reference) and four declared examples, labelled `illustrative`. The priors come from the literature on the aetiology of ward alerts or from a declared design choice, never from the injection rates of the benchmark (ADR-074 decision 2). The same row is used for every template and restricted to the classes that have a component there.

| design | status | C1 | C2 | C3 |
|---|---|---|---|---|
| `uniform` | reference | 1/3 | 1/3 | 1/3 |
| `c1_heavy` | illustrative | 0.6 | 0.3 | 0.1 |
| `c2_heavy` | illustrative | 0.3 | 0.6 | 0.1 |
| `c3_rare` | illustrative | 0.45 | 0.5 | 0.05 |
| `c3_heavy` | illustrative | 0.2 | 0.2 | 0.6 |

**Within-class weights** `pi(s | c, t)`: relative weights per component, normalised per class at the template. The reference design `uniform` gives every component weight 1, so it is uniform over COMPONENTS: a subtype with two knowledge levels weighs twice a subtype with one (the prototype's reference; whether the reference should be uniform over subtypes is a point for gab). The two alternatives change the weight of the QUIET groups, the subtypes that raise nothing or that an informed attacker makes coherent. Groups: quiet C2 = `stuck_at`, `cuff_silent_bias`, `dispenser_bounce`; quiet C3 = `replay_informed`, `injection_informed`, `dispense_forgery_informed`, `presence_spoof_informed`, `dispenser_physical_tamper`; quiet C1 (events with no injection behind them; `spontaneous_sched` is added to the research group) = `spontaneous_range`, `spontaneous_sched`, `spontaneous_hold`, `spontaneous_count`, `spontaneous_resp`.

| design | status | default weight | quiet_c2 | quiet_c3 | quiet_c1 |
|---|---|---|---|---|---|
| `uniform` | reference | 1 | 1 | 1 | 1 |
| `quiet_rare` | illustrative | 1 | 0.25 | 0.25 | 0.25 |
| `quiet_common` | illustrative | 1 | 4 | 4 | 4 |

All weights are `awaiting_human_value`; ward incident statistics, device failure data and the attacker prevalence would have to supply them (none collected).

## Parameters

| name | meaning | sensitivity range (not a proposal) | who must decide |
|---|---|---|---|
| `eps` | 1-eps if a component raises a field by construction, eps if it does not. | 0.001, 0.01, 0.05, 0.1 | device_specification |
| `qc` | One value for every conditional cell of the first version; the per-condition split is a later refinement (each cell carries its condition). | 0.25, 0.5, 0.75 | gab |
| `q_stale` | Conditional cell of system.diagnostics_ok under the profile driver_with_diagnostics. | 0.25, 0.5, 0.75 | device_specification |
| `rep_nat` | Natural probability that two consecutive cuff readings are identical at the display resolution; depends on the resolution of the profile and on the noise. | 0.0098, 0.0197, 0.0393 | device_specification |
| `delta` | C1 diversion share; the cell of witness.intake_observed for C1 subtypes at resp. | 0, 0.1, 0.25 | literature |
| `dispense_bounce_interval_ms` | Threshold of the reading class of dispenser.interval_since_previous_ms (A: interval at or below T_b). | 1000, 10000, 30000, 60000, 180000 | device_specification |
| `tau` | Abstention threshold: kappa = UNDETERMINED if the largest class posterior is below tau. | 0.5, 0.67, 0.8, 0.9, 0.95, 0.99 | gab |
| `cumulative_level` | The set is the most probable subtypes up to this level. The conformal set of WS05-T14 replaces it with a calibrated threshold. | 0.8, 0.9, 0.95 | gab |

`rep_nat` is a property of the generator and its noise at a given display resolution (0.0197 measured at 1 mmHg in the research, 0.0223 on 4448 pairs in WS04-T18), not a device constant. The threshold `dispense_bounce_interval_ms` is the registry name proposed in ADR-032, in milliseconds; it is not yet a registry entry.

## Truth for scoring

The truth used to score the cells and the metrics is the **TIGHT** causal labelling (ADR-074 amendment 3; amendment 2 (4)): a C2 event is the cause of an alert only if the faulty device is in the data scope of the violated template and the alert is decided while the event window is active (the cells describe the fault that CAUSES the violation of the template, not any fault present in the scope). The **looser** labelling (a dropout anywhere in the window counts, including the ECG and the oximeter for `count` and `resp` alerts) is reported next to it in every table. **The choice of the tight labelling was made after seeing the result of the recompute** (ADR-074 amendment 2: the driver diagnostics worsen the log score by 0.007 nats under the loose labelling and improve it under the tight one); it is a decision of gab, not a finding, and the paper states the order of events. The labelling enters only the scoring, never the table.

Monitors, the attributor and the baselines never read `LatentDay` or `GroundTruthEvent` at inference.

## The pair quantity

On the confounder pairs (two members that differ in cause, with a declared stratum `indistinguishable_by_construction`), the quantity is the **log likelihood ratio between the two specific subtypes**, prior-free (ADR-074 decision 3 and amendment 1):

```
Lambda_M = log P(e_M | s_A) - log P(e_M | s_B)        for the alert of member M at the common template
D        = Lambda_A - Lambda_B
```

`P(e | s)` is the product of the cells read at the alert's template for the subtype `s` (the pair `ble_seq_gap` as one joint term); for a subtype with two knowledge levels it is the mixture over its levels, `P(e | s) = sum over the levels l of w(l) / sum(w) * P(e | s at l)`, with the **within-subtype level weights `w(l)` of the pi design in force**. The reference is the design `uniform`, uniform over components (weight 1 per component, so the two levels of `replay`, `dispense_forgery` and `presence_spoof` weigh equally); it is a declared reference design awaiting gab, not a value from the literature, and `quiet_rare` and `quiet_common` change it (they weigh the informed level of those subtypes by 0.25 and 4). The subtypes need not be applicable at the template: a pair compares its two actual causes. It does not depend on the class priors or on the weights BETWEEN subtypes (`pi(subtype | class)`); it depends on the within-subtype weights only for the three subtypes with two levels. In the indistinguishable stratum identical streams give `D = 0` exactly (a necessary property, tested on identical readings); in the distinguishable stratum the criterion is the correct direction (`Lambda_A > 0` and `Lambda_B < 0`) with McNemar between methods on that direction, and `D > 0`. `Lambda` itself is not 0 on identical streams: it is the lean of the catalogue and the cells.

## Sets and conformal calibration (for WS05-T14)

The cumulative-level set is the specification of the table. The calibrated set follows the research (section 10.3): nonconformity score of an alert = `1 - p(true subtype | e, t)`; the threshold is the `ceil((n+1)(1-alpha))`-th smallest calibration score (the full set if the rank exceeds `n`); the prediction set is all subtypes with score at most the threshold; marginal and Mondrian per template; the pairs are calibrated SEPARATELY (prevalence 50% and a different template mix). The statement is marginal; the rank argument needs exchangeable alerts, which patient-level exchangeability alone does not give when a patient contributes several correlated alerts, so the bound is exact only for one designated alert per patient and otherwise the coverage is approximate and checked empirically (role-swap check, coverage per patient with a cluster bootstrap); ties make it conservative; it says nothing about another population, as the transfer from the main population to the pairs shows. `Alert.cause_set` is never empty: when the rule gives an empty set the calibrator returns the most probable subtype alone (`top1_fill`), which can only raise coverage and must be reported (its frequency per template). The metrics are coverage of the true subtype and mean set size per stratum, and the methods are compared at equal coverage.

## Known failure modes (from the research, stated plainly)

- **Where nothing is raised, C1 cannot be told from the silent faults.** At `range` the likelihood ratio between a C1 subtype and `cuff_silent_bias` is **exactly 1** on every reading, because every cell is `Z` or `N` for both; the posterior is the prior. Any prior, catalogue or threshold that makes C1 confident makes the silent faults confident C1 (research 7.2). The remedy of the paper is the SET of subtypes and the diagnosability matrix, not a better threshold. `stuck_at` is the exception only through `signal_quality.cuff_value_repeated`, and only when the reading exists.
- **Indistinguishable pairs have `D = 0`.** Streams that are identical by construction (an informed attacker coherent on every channel; a bounce and a forged dispense that copies the bounce timing, where `Lambda` is the same non-zero number for both members) cannot be separated by any method of this family; they are declared, not repaired.
- **The fully independent product double counts correlated channels**: one dropout raises several system fields. The reference therefore reads `system.ble_link_quality` and `system.seq_gap` as one joint cell; the fully independent product and the cross-device group are the sensitivity variants.
- **Time cells beyond the bound.** `crypto_temporal.timestamp_implausible` is raised by `clock_skew`, `out_of_order` and `timestamp_manipulation` only beyond the bound (late beyond `D`, or future-stamped beyond `skew_max`; fault-model Fault-to-evidence table, threat-model Attack-to-evidence table and TX-8 (a)), so these cells are conditional (`C`, condition BOUND), not `1-eps`. All three subtypes are outside benchmark v1 (`clock_skew` and `timestamp_manipulation` are modelled and not injected; `out_of_order` is absorbed by the reorder buffer within the bound), so the benchmark cannot test these cells.
- **A dead awaiting cell.** `presence_spoof` (naive) is applicable at `int` and its cell is the identity check (`witness.identity_confirmed`), but the witness fields are context for `int` (AD-3) and no template reads that cell for it: it is a dead awaiting cell, and the naive `presence_spoof` is indistinguishable from the informed one at `int`. The other cells that no applicable template reads are those of `out_of_order` (applicable nowhere) and the two of `ecg_noise` (live only in the cross-device variant).
- **`message_drop`.** The reference (joint) and the fully independent readings differ for it (previous section): the link degradation and the gap are coupled in the reference, independent in the fault model's table.
- **`replay` (naive) and `system.seq_gap`.** The threat model says that the suppressed genuine messages would leave a gap in the device's own sequence (`system.seq_gap`) and that this is not modelled at the naive level (H-SUPP): the cell of `replay` (naive) for `system.seq_gap` is the structural zero `eps` although a replay with suppression would add a gap; a replay together with a loss is read as a loss (TM-GAP-SEQ).
- **The interval channel is defeated by an attacker who copies the bounce timing**, and by a threshold above the double-take gap (the research found the interval stops separating at 180 s).
- **The cells describe the generator's and the catalogue's own view**; the fault and threat tables were written in this project, so they are not independent evidence of what a ward produces.
- **A predicted violation** is not attributed by this table (its attribution is UNDETERMINED by definition); cascades and the multi-alert aggregation of one event are not treated.

## Declared dependencies on decisions that are proposed or unconfirmed

- **ADR-075 (proposed, DA-CONFERMARE).** In the hierarchical rule `ours-hier`, `system.seq_gap` blocks C1 (RS-2, AM-2) but is not a C2 predicate: the delivery ratio below the floor remains the C2 evidence, and the paper must not say that the gap is C2 evidence for `ours-hier`. The likelihood table is not bound by this: it gives `system.seq_gap` cells (the pair `ble_seq_gap` is one joint cell). The two methods therefore treat the same field differently by design, and a comparison must say so.
- **ADR-074 amendment 4 (generator modelling choices of WS04-T18, to be confirmed by gab).** (1) The INFORMED forger is coherent on the interval chain: the forged opening counts in the chain of `dispenser.interval_since_previous_ms`, so the next genuine opening carries the interval of its non-response twin. The all-structural-zero interval cells of the C3 subtypes rest on this, and they await gab's confirmation. If the alternative holds (an informed attacker that cannot rewrite the device's own counter), about 7 of 16 forged-first-dose pairs of each informed noauth variant (`informed_norobot_noauth`, `informed_robot_noauth`) would be distinguishable by the interval, the declared `expected_indistinguishable: true` of those two variants would become false, and the interval cell of the informed `dispense_forgery` would no longer be the structural zero. The naive forger is not coherent: the next genuine opening is measured from the previous genuine one, so a naive forgery in place of a first dose leaves it without an interval. (2) The driver sessions derive from what the device SENT: a requested but unanswered measurement (silent detachment, refusal, a cuff that never answers) opens no session, so `stale` is in practice a `ble_dropout` signal and `P(stale | cuff_detached) = 0` is a property of the generator, not of the liveness contract (a real driver that tracks requests would report it). This is why only the four subtypes listed in the diagnostics section have a stale cell.

## Sensitivity design

Every dimension of the study, with its range (`sensitivity_design` in the file). None is a proposal.

| dimension | range | applies to |
|---|---|---|
| `eps` | 0.001, 0.01, 0.05, 0.1 | all structural cells |
| `qc` | 0.25, 0.5, 0.75 | conditional cells (tokens C and Cn) |
| `q_stale` | 0.25, 0.5, 0.75 | stale cells of system.diagnostics_ok |
| `rep_nat` | 0.0098, 0.0197, 0.0393 | natural repeat of the cuff reading |
| `delta` | 0, 0.1, 0.25 | C1 diversion share |
| `dispense_bounce_interval_ms` | 1000, 10000, 30000, 60000, 180000 | threshold of the interval reading |
| `class_priors` | uniform, c1_heavy, c2_heavy, c3_rare, c3_heavy | prior_t(c) |
| `pi_designs` | uniform, quiet_rare, quiet_common | pi(component | class, t) |
| `cumulative_level` | 0.8, 0.9, 0.95 | level of the subtype set |
| `tau` | 0.5, 0.67, 0.8, 0.9, 0.95, 0.99 | abstention threshold of kappa |
| `grouped_variant` | reference, fully_independent, reference_plus_cross_device | independence assumption: reference = ble_seq_gap grouped, cross-device independent; fully_independent relaxes nothing; reference_plus_cross_device adds the common cause ecg_noise |
| `diagnostics_profile` | driver_with_diagnostics, without_diagnostics | profile of system.diagnostics_ok |
| `cell_scope` | template, all | components of a cell: those that can violate t (reference) or every component of the class |
| `family` | catalogue, benchmark_v1 | all subtypes of the catalogue or only those the benchmark injects |
| `labelling` | tight, loose | truth used to score; tight is primary (decided after seeing the result, ADR-074 amendment 2) |

`eps`, `qc`, `q_stale`, `rep_nat`, `delta`, `dispense_bounce_interval_ms`, the class priors, the within-class designs, `cumulative_level` and `tau` are the parameters and designs listed above; `grouped_variant` is the independence variant (reference: the pair `ble_seq_gap` grouped; `fully_independent` and `reference_plus_cross_device` are the variants); `diagnostics_profile` is a case of the device profile, not a parameter; `cell_scope` (components of a cell: those that can violate the template, or every component of the class as a co-occurrence reading), `family` (the whole catalogue or only the subtypes that benchmark v1 injects) and `labelling` (tight, loose) are the switches of the study. The mixtures that the task calls the within-cause weights are the designs `pi_designs`; the share of silent faults inside C2 is a derived quantity of them.

## Differences from the research prototype

The specification is not a copy of the prototype. Where it differs, the reason is the source of truth of the repository, and the effect is that numbers of the report do not carry over unchanged.

1. **Fields.** `#evidencevector` 0.2.0: `system.seq_gap` and `crypto_temporal.seq_repeat` replace the single sequence field, the dispenser group and `signal_quality.cuff_value_repeated` are native cells, with the masks above.
2. **Template reach follows the fault model.** `ecg_noise` violates no template (the prototype made it a C2 component at `sys`); the C2 subtypes at `sys` are `cuff_detached` only; `process_kill`, `uncommanded_lifecycle_transition`, `message_drop`, `link_delay` and `battery_depleted` follow the "Effects on templates" table (the prototype restricted some of them).
3. **`diagnostics_ok`.** Conditional cell `S` for the subtypes that silence a device, not the raised cell of the prototype (WS04-T18).
4. **`stuck_at`** raises `cuff_value_repeated` by construction given a reading (as the prototype); every other subtype has the natural probability.
5. **C1 subtypes** include `spontaneous_sched`; the diversion cell is attached to the C1 subtypes that can be read at `resp`.
6. **Components and subtypes.** Knowledge levels are components, as in the prototype; the output set names subtypes.
7. **The reference is grouped for the pair.** The prototype's reference was the independent product, with the grouped pair as variant G1; ADR-074 amendment 3 and ADR-075 make `system.seq_gap` with `system.ble_link_quality` ONE cell, so it is the reference here and the fully independent product is the variant.
8. **Time cells** of `clock_skew`, `out_of_order` and `timestamp_manipulation` are conditional (beyond the bound), not raised by construction.

## Contract

- `#alert` 0.3.0 (ADR-074 amendment 1): `Alert.cause_set: Sequence[str] | None = None`, after `p_kappa`; the names of the subtypes of the set.
- `#attribution` 0.3.0: the rule protocol gains `posterior_subtypes(violated, evidence) -> Mapping[str, float] | None` next to `posterior` (0.2.0); `None` for the hierarchical rule; `posterior` is the class sum of `posterior_subtypes`.
- `#evidencevector` is not changed (0.2.0, WS05-T13).

## Traceability

ADR-074 (decision and amendments 1 to 4), ADR-032, ADR-033, ADR-034, ADR-040, ADR-075 (the hierarchical rule's treatment of `system.seq_gap`; this attributor reads the gap and the delivery ratio as one grouped cell). Sources: `fault-model.md` (Fault-to-evidence table, Effects on templates, Subtype vocabulary), `threat-model.md` (Attack-to-evidence table, Knowledge levels, Subtype vocabulary), `evidence-channels.md` (D-15, D-16, Bridge node liveness contract, Ablation A4 mask), `attribution-rule.md` (reading classes, relevance map), the research report sections 1, 6, 9, 10. Consumers: WS05-T12 (reads `configs/attribution_likelihood.yaml`; a row `awaiting_human_value` makes construction fail unless the run supplies a labelled sensitivity value), WS05-T14 (the set calibrator), WS08-T09 (the metrics), WS08-T02 and WS08-T04.
