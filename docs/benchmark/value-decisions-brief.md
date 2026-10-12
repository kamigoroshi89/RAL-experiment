# Open numeric values for the main experiment WS08-T02: briefing for an external expert

Prepared 2026-10-12 by the repository assistant, read-only on the repository, for gab (project owner) to hand to an external expert LLM. The expert advises gab on each open value that the main experiment (WS08-T02) needs. Nothing here is a clinical, device or probability value of the project: every number in a candidate table is either a grid value of the research report, a labelled placeholder of the research runs, a number quoted from a repository file (with its location), or a number computed for this brief (marked **(C)** with its formula or scenario). Validation in this project is technical and pre-clinical.

How to read the references: **[M]** = `docs/models/attribution-likelihood.md`; **[Y]** = `configs/attribution_likelihood.yaml`; **[R x.y]** = section x.y of `docs/benchmark/evidence/likelihood-attribution.md`; **[RB]** = `docs/benchmark/evidence/benchmark-size-all-subtypes.md`; **[RP]** = `docs/benchmark/evidence/pairs-allocation.md`; **[FF]** = `docs/benchmark/evidence/fault-free-diagnostic.md`; **[NA]** = `docs/benchmark/evidence/nonadditivity.md`; **[G]** = `configs/benchmark/{generator_design,injections,default}.yaml` and `configs/priors/literature_hypertension.yaml`; **[ADR-n]** = `docs/plan/03-decisions.md`; **[T02]**, **[T10]** = the task files `docs/plan/workstreams/WS08-experiments/tasks/T02-main-experiment.md` and `T10-ours-detector-likelihood-wiring.md`. **(C)** = computed for this brief.

What gab wants from the expert, per entry of Part B: a recommended headline value (or the statement that the value should stay a pure sweep), the sweep set, the reasoning, the risk if the recommendation is wrong, and what additional evidence would change it. Where the expert has no defensible basis, say so; do not fill the gap with a plausible number.

---

# Part A. Project context

## A.1 The project

The project extends the IJCAI-ECAI 2026 workshop paper "Clinical Pathways as Safety Specifications for Physical AI in Hospital Wards" (Franchini, Mallardi, De Carolis, Lanubile; University of Bari), a position paper, into a 6-page IEEE RA-L submission. A pathway template is instantiated into a patient care plan; the care plan becomes a set of instances of seven past-time Signal Temporal Logic (STL) templates, monitored online over a stream of observations from a hospital-ward cuff, an ECG device, an oximeter, a pill dispenser and a mobile robot:

| template | what it checks (registry names in brackets) |
|---|---|
| `range` | a blood-pressure (BP) measurement lies in the band (`bp_band_low`, `bp_band_high`) |
| `sched` | a measurement exists within `sched_window` of each scheduled tick |
| `hold` | before a dose, a recent measurement (`hold_lookback`) is not below `bp_hold_threshold` |
| `count` | doses in the trailing 24 h at most `dose_max_24h`; at least `dose_min_day_end` at day end |
| `resp` | after a dose, BP drops by at least `delta_resp` within the response window |
| `sys` | cuff inflation duration at least `cuff_inflation_min`, cuff health OK |
| `int` | a witness (robot presence, intake, authentication) is fresh within `int_window` after a dispense |

(Source: `docs/formal/02-templates.md`, table of section 3.1.) The monitor is three-valued and emits verdicts PENDING, PREDICTED-VIOLATION, VIOLATED or SATISFIED; robustness is clinically normalised; a conformal calibrator gives the predictive part a finite-sample level (Proposition 1).

## A.2 The attribution layer (the part with open values)

For each VIOLATED instance an extractor builds an **evidence vector** (24 fields in 7 groups, contract `#evidencevector` 0.2.0): system health (node lifecycle, diagnostics, liveliness, QoS deadline, BLE link quality, task failures, sequence gap), signal quality (ECG and PPG quality indices, cuff error code, cuff repeated value), cross-device (pulse versus ECG heart-rate difference), witness (robot presence, identity, intake observed), crypto-temporal (authenticated, sequence repeat, timestamp implausible) and dispenser (interval since the previous opening, content change). Each field has a **reading class**: A asserted, D denied, U unavailable (the field is `None`; unavailable is never a negative reading and contributes the factor 1).

The attribution (ADR-074, accepted 2026-10-11) is a **likelihood table**: for an alert at template `t`

```
p(s | e, t)  proportional to  prior_t(class(s)) * pi(s | class(s), t) * product over fields f read at t of P(class_f | s)
```

where `s` ranges over the *components* (a subtype at one attacker-knowledge level) that can violate `t`, `P(A | s, f)` is a **cell**, and `P(D) = 1 - P(A)`. The causes are **C1** clinical/physiological, **C2** fault of a device or the system, **C3** integrity violation (an attack); 35 subtypes in the catalogue (11 C1, 17 C2, 7 C3), 38 components. The output is a posterior over subtypes; the class posterior `p_kappa` is its class sum; `kappa` is the class with the largest posterior if at least `tau`, else **UNDETERMINED** (abstention); the **set** is the most probable subtypes up to a cumulative level, replaced in the headline run by a **conformal set** calibrated on the calibration patients (marginal or Mondrian per template, target level `1 - set_alpha`). The independence of fields given the component (naive Bayes) is an assumption of the model; the pair (`system.ble_link_quality`, `system.seq_gap`) is one joint cell in the reference.

Baselines B1 to B5 (static thresholds, anomaly detection, plain STL, conformal-only, conformal STL after Lindemann et al. 2023) do not read the table. Ablations A1 to A7 include A4 (embodied channel removed: the witness and robot-task cells are dropped).

## A.3 The benchmark and what WS08-T02 does

The benchmark is **semi-synthetic with latent ground truth**: a generator draws virtual patients (latent pressure with circadian, autoregressive and PK/PD components, an adherence model, device error models), injects C1, C2 and C3 events (records in an injection log), and writes an *observed* trace (what monitors see: noisy, rounded to the cuff resolution, with link losses and forged messages) next to the *latent* trace and ground-truth events (used only for scoring: monitors, attributor and baselines never read `LatentDay` or `GroundTruthEvent` at inference). Scale declared in `configs/benchmark/default.yaml`: 200 virtual patients x 7 scored days plus one unscored tail day per patient, split by patient 0.5 / 0.25 / 0.25 (train, calibration, test), plus matched *confounder pairs* (two patients that differ in cause) with a declared stratum "indistinguishable by construction".

**WS08-T02** runs B1 to B5 and the proposed method `ours` (plus `ours-hier`, the hierarchical reference rule) on the same benchmark, splits and at least five seeds, with the metrics of analisi 5.5 and the honest-reporting diagnostics (B5 failure analysis, per-subtype breakdown with the undetectable rows, tolerance sensitivity, alert load, non-circularity audit). It is `status: ready`, `critical_path: true`. A headline run (`run_options.headline: true`) is refused unless `detector_params.ours.likelihood` supplies a labelled value for every awaiting row the run reads, plus the attribution options and the background tail ([T10] fix round I1, I2; runner guards).

## A.4 Why the values are open

No clinician, no field data from a ward, and no hospital incident statistics are available; the project rule is **no invented numbers** (clinical parameters, thresholds, priors and citations come from the parameter registry, `PriorSource` provenance and the verified bibliography; unverified references cannot be cited). The likelihood table therefore has **no number chosen**: every non-structural cell and parameter is `awaiting_human_value` with a *sensitivity range* ("sensitivity, not a proposal"). Rule **E9** (WS08 README): tolerance, alpha grid, split fractions and every hyperparameter are fixed from the registry, the manifest and the train and calibration splits, written with their rationale in the YAML header, and committed **before the first run on the test split**; there is no test-split tuning. One earlier choice was made after seeing a result and is declared as such: the TIGHT causal labelling of truth (ADR-074 amendment 2; [M] "Truth for scoring"). The paper states the order of events; no other choice may repeat that pattern.

## A.5 How an answer is recorded

An answer is a **design choice of gab**: it is written into `experiments/main.yaml` as `run_options.detector_params.ours.likelihood.sensitivity_values.<name>` (and the other `run_options` keys) with the rationale in the header comment; the cell rows of `configs/attribution_likelihood.yaml` stay `awaiting_human_value`, `verified_by: null`; the value is recorded in `metrics.json` (`meta.attribution.rules.ours`) with the label "sensitivity, not a proposal"; the paper states that it is a design choice and **not literature-verified**. The headline run uses one value per parameter; the **sensitivity sweep** (one run per setting, grid in [M] "Sensitivity design") follows and is reported next to it.

How the file is consumed (checked in `src/ralmon/attribution/likelihood.py`, `LikelihoodRule._resolve`): `sensitivity_values` accepts **only** the names of the 8 parameters (`eps`, `qc`, `q_stale`, `rep_nat`, `delta`, `dispense_bounce_interval_ms`, `tau`, `cumulative_level`) and the 2 designs (`class_priors`, `pi_designs`, by declared name); an unknown name, an undeclared design or an override of a filled row raises. **The 67 awaiting cell rows are therefore not filled one by one: each is a function of one shared parameter** (30 use `rep_nat`, 31 use `qc`, 4 `q_stale`, 2 `delta`). A parameter that no live cell reads in the run is not required (`q_stale` without the driver diagnostics, `delta` under A4). `tau` and `cumulative_level` are not part of the model-version token; every other value is, so changing it refits the set calibrator (cheap, automatic in the runner) and moves every attribution number but **no detection metric** (recall, delay, false alarms, per-template and background metrics), which come from the monitor and baselines before attribution. The reference implementation of `family` (catalogue versus benchmark-v1 subtypes) and `cell_scope` is **not implemented**: the headline run uses the whole catalogue, so 11 subtypes that benchmark v1 never injects (`process_kill`, `message_drop`, `localisation_noise`, `impossible_goal`, `link_delay`, `out_of_order`, `clock_skew`, `battery_depleted`, `uncommanded_lifecycle_transition`, `dispenser_physical_tamper`, `timestamp_manipulation`) are in every posterior as competing hypotheses.

## A.6 How the worked examples of Part B were computed

The scenarios below were computed for this brief with the repository's own `LikelihoodRule` (via the test helper of `tests/attribution/test_likelihood_rule.py` and the fixture registry, in a throw-away script that is not saved in the repository), at the **reference point** eps 0.01, qc 0.5, q_stale 0.5, rep_nat 0.0197, delta 0, T_b 10 000 ms, class prior `uniform`, pi design `uniform`, profile `without_diagnostics` unless a scenario varies it. Readings are given directly as classes. "Everything else D" means every field the template reads is denied, except the fields declared `None`. They are **illustrations of how a value moves a posterior, not results**; the alert is an illustrative patient-day of benchmark `ral-bench-v1`, not a specific record. Reproduction: build `LikelihoodRule(registry, load_likelihood_table(CONFIG), sensitivity_values=..., diagnostics_profile=...)`, build the vector with `classes_to_vector`, call `posterior_subtypes` and `posterior`.

| id | template | story | readings other than D |
|---|---|---|---|
| S1 | `count` | forced `double_take`: the second dose 120 s after the first; day-end COUNT violated | `crypto_temporal.authenticated` None (no authenticating device), `dispenser.content_change` None (no content sensing) |
| S2 | `sched` | 15-min BLE dropout of the cuff; the lease is not exceeded | `system.node_lifecycle` A, `system.ble_link_quality` A, `system.seq_gap` A; `authenticated` None |
| S2b | `sched` | as S2 but a long dropout | S2 plus `liveliness_ok` A, `qos_deadline_missed` A |
| S3 | `sched` | S2 under the profile `driver_with_diagnostics` | `system.diagnostics_ok` A (stale) or D (ok) |
| S4 | `range` | frozen cuff (`stuck_at`) | `signal_quality.cuff_value_repeated` A; `authenticated` None |
| S5 | `resp` | a dose the witness did not see taken | `witness.intake_observed` A; `authenticated`, `content_change` None |
| S6 | `count` | bounce (500 ms) against double take (120 s) | `interval_since_previous_ms` raw 500 or 120000 ms |
| S8 | `sched` | late robot arrival | `system.nav_task_failed` A |
| S9 | `sched` | message loss pattern | `seq_gap` A (and `ble_link_quality` A in the long-run variant) |
| S10 | `range` | forged cuff value, pulse not patched | `cross_device.pulse_vs_ecg_hr_diff` A |
| S11 | `count` | a sequence gap and nothing else | `system.seq_gap` A; `authenticated`, `content_change` None |
| S12 | `range` | a value out of band, no field raised | `authenticated` None |
| S13 | `sched` | timestamp flagged implausible | `crypto_temporal.timestamp_implausible` A |

The placeholders quoted from the research runs (not proposals): bounce nominal 500 ms, double-take gap 2 min, intake lag 5 s, circadian peak 14:00, durations 1 / 4 / 12 h, magnitudes x0.5 / 1 / 2, vitals period 60 s, dwell 10 min, mean adherence delay 20 or 30 min ([R header], [FF 0], [RB 0]).

## A.7 Glossary

- **cell**: `P(A | component, field)`, one entry of the table; forms: Z `eps` (structural zero), R `1-eps` (raised by construction), C `eps+(1-2 eps) qc` (conditional raise), Cn `eps+(1-2 eps)(1-qc)` (the other branch of an either-or), S `eps+(1-2 eps) q_stale`, N `max(rep_nat, eps)`, V `eps+(1-2 eps) delta`. A *structural* cell needs only `eps`; an *awaiting* cell needs a value.
- **field** = an `EvidenceVector` path, e.g. `system.seq_gap`. **reading class**: A asserted, D denied, U unavailable (`None`, factor 1). The class of a raw value comes from registry thresholds (floors, tolerances) or a parameter (`T_b` for the dispenser interval).
- **component vs subtype**: a *subtype* is an identifier of the vocabularies (e.g. `replay`); a *component* is a subtype at one attacker-knowledge level (`replay_naive`, `replay_informed`; also `dispense_forgery`, `presence_spoof`). Cells are per component; the set names subtypes (levels are summed).
- **eps / qc structure**: `eps` is the leak of structural cells (floor of every probability); `qc` is the probability that the *condition* of a conditional cell (lease, deadline, sequence provision, D-5, DSP...) holds in an alert.
- **tight vs loose labelling** (truth for scoring only): TIGHT (primary) = a C2 event is the cause of an alert only if the faulty device is in the data scope of the template and the alert is decided while the event window is active; LOOSE = a fault anywhere in the window (plus `loose_after_ms`) counts. Both are reported in every table.
- **quiet subtypes**: raise no field (`stuck_at` apart, `cuff_silent_bias`, `dispenser_bounce`, informed attacks, spontaneous C1 events); they cannot be separated from C1 by evidence, which is why the output is a *set* and the diagnosability matrix declares them.
- **pair quantity**: on confounder pairs, `Lambda = log P(e | s_A) - log P(e | s_B)`, prior-free; `D = Lambda_A - Lambda_B`; identical streams give D = 0 exactly.
- **pi design / class prior design**: declared weight vectors (`uniform`, `quiet_rare`, `quiet_common`; `uniform`, `c1_heavy`, `c2_heavy`, `c3_rare`, `c3_heavy`); only declared names can be supplied.
- **profiles**: `without_diagnostics` (no driver report; the field is `None`) or `driver_with_diagnostics` (needs `driver_period_ms` and `driver_stale_lease_ms`).

## A.8 Verification of the counts quoted to the expert

- **Likelihood file**: 67 awaiting cell rows, confirmed (30 natural-repeat `N`, 29 `C`, 2 `Cn`, 4 `S`, 2 `V`; by `needs`: 56 device_specification, 9 gab, 2 literature). The file has **79** `awaiting_human_value` rows in all: 67 cells + 8 parameters + 2 designs (`class_priors`, `pi_designs`) + 2 grouped-cell rows (`ble_seq_gap`, `cross_device_signal_quality`). Structural: 19 cells. (A `grep -c` of the string gives 149 because cells repeat it in the fields `A` and `status`.)
- **Generator**: 48 awaiting rows, confirmed: 7 in `generator_design.yaml` (`circadian_peak_clock_ms`, `intake_lag_ms`, `double_take_gap_ms`, `robot_dwell_ms`, `vitals_period_ms`, `driver_period_ms`, `driver_stale_lease_ms`; a `grep -c` gives 8 because a comment repeats the string), 40 in `injections.yaml` and 1 in `literature_hypertension.yaml` (`mean_delay_ms`). The "65 rows" of older notes ([ADR-067], [FF]) are superseded: Group-1 values (BLE, cuff, inflation, pulse error) were filled by gab's acceptance on 2026-10-10. Of the 40, 6 are `ecg_noise` rows, excluded from this benchmark version by [ADR-071 (c)] (no noise-segment library).

---

# Part B. One entry per open value

Entries 1 to 10 are the parameters and designs of the model; 11 to 13 are the 67-row cell groups that need a decision beyond a shared parameter; 14 is the generator; 15 to 17 are options of the run. Each entry has the same labels. "Suggested default" is the repository assistant's **opinion**, not a fact and not a project decision.

## B1. `eps` (leak of every structural cell)

**Name / where it lives.** Row `parameters[name=eps]` of [Y]; supplied as `run_options.detector_params.ours.likelihood.sensitivity_values.eps`; dimensionless probability; `needs: device_specification`; sensitivity range 0.001, 0.01, 0.05, 0.1; `status: awaiting_human_value`, `verified_by: null`.

**What it is.** Plain language: how often a reading goes the "wrong way" for a cause, that is, a field asserted although the cause does not raise it, or denied although it does. In the code it is the floor of every probability of the table: 19 structural cells are `1-eps` (raised by construction, e.g. `system.node_lifecycle` under `ble_dropout`), every one of the unlisted (component, field) pairs is `eps` (structural zero), and `eps` is also inside the conditional forms `eps+(1-2 eps) q`, the floor `max(rep_nat, eps)` and the grouped joint classes (`1-eps` on the mode, `eps/3` on each other joint class, K = 4). No cell is ever exactly 0 or 1, so one surprising reading never rules a cause out; a small `eps` makes each surprising reading decisive, a large one dilutes all evidence.

**Concrete example.** Scenario S2 (`sched` alert, 15-min dropout of the cuff; `node_lifecycle`, `ble_link_quality`, `seq_gap` asserted, everything else denied). The raised field `node_lifecycle` has likelihood ratio (ble_dropout : C1) = (1-eps)/eps = 999, 99, 19, 9 for eps 0.001, 0.01, 0.05, 0.1 (C, arithmetic). Posterior (C, repository rule, qc 0.5):

| eps | P(C1) / P(C2) / P(C3) | P(`ble_dropout`) | subtypes in the 0.9 set | kappa at tau 0.8 |
|---|---|---|---|---|
| 0.001 | 0.000 / 1.000 / 0.000 | 0.997 | 1 | C2 |
| 0.01 | 0.003 / 0.996 / 0.001 | 0.967 | 1 | C2 |
| 0.05 | 0.062 / 0.921 / 0.017 | 0.791 | 3 | C2 |
| 0.1 | 0.175 / 0.774 / 0.051 | 0.568 | 5 | UNDETERMINED |

Where nothing is asserted `eps` hardly matters: in S1 (`count`, double take, all denied) P(C1) / P(C2) / P(C3) = 0.526 / 0.079 / 0.395 at eps 0.001 and 0.510 / 0.102 / 0.389 at 0.1 (C). So `eps` decides how much weight an asserted reading carries, which is why it interacts with `tau`.

**Who/what would decide it in a real deployment.** The false-alert and miss rate of each evidence channel, from device specifications and fault-free field logs of the ward (per channel, not one number). [Y] states "none collected". The repository has no source: the generator's own fault-free run would give only the generator's rate, which is circular as a headline value.

**Candidate values and what they change.** Class-level prototype, 1879 pair members, section-5 labelling ([R 6.1], one-at-a-time from the reference point; the numbers describe the *prototype*, read the direction only):

| eps | argmax = truth (of 1879) | UNDETERMINED / confident right / confident wrong at tau 0.8 | main-population log score / Brier | silent-fault alerts with argmax C1 (of 433) |
|---|---|---|---|---|
| 0.001 | 859 | 1634 / 245 / 0 | 0.905 / 0.536 | 425 |
| 0.01 | 859 | 1711 / 168 / 0 | 0.901 / 0.536 | 425 |
| 0.05 | 859 | 1741 / 138 / 0 | 0.923 / 0.549 | 428 |
| 0.1 | 819 | 1839 / 40 / 0 | 0.943 / 0.563 | 429 |

Subtype model with the accepted channels ([R 10.2.6]): the share of distinguishable pairs with D > 0 does not move with eps; the median `Lambda_A` of the indistinguishable group 4 is 6.68, 4.38, 2.75, 2.03 nats for eps 0.001, 0.01, 0.05, 0.1 (qc 0.5). Not measured: eps on the final headline run.

**What this value does not decide / known failure modes.** It does not change the structure (which fields a cause raises). One `eps` is applied to all channels although a sequence gap and a perception false negative have unrelated leak rates. It cannot represent a cause missing from the catalogue except as leak. Where no field is raised (S12: `range`, nothing asserted) the likelihood ratio between a C1 subtype and a silent C2 is exactly 1 for every eps ([R 7.2]); no eps cures that. A very small eps overstates confidence when the catalogue is incomplete; a large one makes `tau` 0.8 abstain almost always (1839 of 1879).

**Who else reads it / consequences.** Every cell (`LikelihoodRule`), the model-version token (so the conformal set calibrator refits), the log score, Brier score and calibration curves, the pair quantity `pair_llr` (prior-free but eps-dependent), the equal-coverage block and `ours-A4`. Not read by B1 to B5, by `ours-hier`, or by any detection metric. Changing it after the first test-split run breaks rule E9; before that it costs one rerun.

**Options for gab.**
(a) 0.01 for the headline, sweep all four: comparable to the prototype, neither extreme.
(b) 0.05 headline: more cautious, shrinks over-confidence from an incomplete catalogue, at the price of more abstentions.
(c) 0.001 headline: sharpest, shows the method's best case, most exposed to catalogue gaps.
(d) channel-specific eps: more defensible physically, but needs a specification change and a source per channel that does not exist.

**Suggested default (assistant's opinion).** 0.01, with the full four-point sweep reported: it is the reference point of the research, so the first headline is comparable with the prototype, and the sweep shows the dependence.

**Questions to put to the expert.**
1. With an incomplete catalogue, is there a principled way to tie `eps` to the probability mass of unmodelled causes instead of treating it as measurement noise?
2. Is a single global `eps` defensible in a RA-L paper, and if not, which two or three channels (sequence, witness, dispenser) are the first to deserve their own leak?

## B2. `qc` (probability that a cell's condition holds)

**Name / where it lives.** Row `parameters[name=qc]` of [Y]; `sensitivity_values.qc`; dimensionless; `needs: gab`; range 0.25, 0.5, 0.75; also the weights of the joint modes of the grouped cells.

**What it is.** Plain language: when a cause can raise a field only under a condition (a lease that lapses, a sequence number the device provides, a time bound exceeded, the robot being co-located), `qc` is the probability that the condition holds in an alert. In the code one value serves 31 cells (29 of form `eps+(1-2 eps) qc`, 2 of form `eps+(1-2 eps)(1-qc)`) and the modes of the grouped cells (`ble_dropout`: gap+degraded `qc`, degraded `1-qc`; `message_drop`: gap `qc`, clean `1-qc`; `injection_naive` and `dispense_forgery_naive`: gap `1-qc`, clean `qc`; `ecg_noise` in the cross-device variant). The 31 cells carry 12 different conditions: LC 9, SEQ 6, BOUND 3, COLOC 3, D5 2, PULSE 2, DEGRADE 1, TARGET 1, SQI 1, DSP 1, LATE 1, IDCHECK 1; the file notes that the per-condition split "is a later refinement".

**Concrete example.** S11 (`count` alert, a sequence gap and nothing else; `ble_link_quality` D, `seq_repeat` D). Two subtypes compete: `message_drop` (C2: joint mode gap with probability qc) and the naive `dispense_forgery` (C3: gap with probability 1-qc, and `seq_repeat` denied with probability 1-(eps+(1-2 eps) qc)). Hand arithmetic at qc 0.5, eps 0.01 (C): joint P(gap | message_drop) = 0.5 x 0.99 + 0.5 x 0.01/3 = 0.4967; the same for the naive forgery; the naive forgery then pays 0.5 for the denied `seq_repeat` (0.2483), `message_drop` pays 0.5 x 0.5 for the denied `liveliness_ok` and `qos_deadline_missed` (0.4967 x 0.25 x 0.99 = 0.1229). With the within-class weights (1/3 and 1/5) the ratio is (0.2483/3) / (0.1229/5) = 3.4, as in the repository output. Posterior (C):

| qc | P(C1) / P(C2) / P(C3) | top subtypes | 0.9 set | kappa at tau 0.8 |
|---|---|---|---|---|
| 0.25 | 0.015 / 0.132 / 0.853 | `dispense_forgery` 0.848, `message_drop` 0.128 | 2 subtypes | C3 |
| 0.5 | 0.029 / 0.224 / 0.747 | `dispense_forgery` 0.737, `message_drop` 0.220 | 2 | UNDETERMINED |
| 0.75 | 0.090 / 0.271 / 0.639 | `dispense_forgery` 0.609, `message_drop` 0.266, `dispenser_physical_tamper` 0.030 | 3 | UNDETERMINED |

So `qc` moves the C2/C3 boundary of this alert and the abstention; in S2 (a loud dropout) it moves almost nothing (P(C2) 0.996 / 0.996 / 0.992).

**Who/what would decide it in a real deployment.** Per condition: the device specification (does the device provide `seq`; the liveliness lease and QoS deadline of the profile, named in WS07-T03 / EC-OP-18; the time bounds), the task-layer design (D-5, D-6) and the threat-model assumptions (COLOC, PULSE, LATE). In the repository: the fault-model and threat-model rows give the *conditions*, never a probability; nothing gives `qc`.

**Candidate values and what they change.** [R 6.1] (class-level prototype): qc 0.25 / 0.5 / 0.75 give UNDETERMINED / confident right / confident wrong at tau 0.8 of 1674 / 205 / 0, 1711 / 168 / 0, 1711 / 168 / 0 of 1879 members, argmax = truth 859 in all three, main-population log score / Brier 0.923 / 0.548, 0.901 / 0.536, 0.892 / 0.531; mean `Lambda_A` of the indistinguishable group 1 is 1.86 / 2.32 / 2.84. Subtype model with accepted channels ([R 10.2.6], eps 0.01): both-members-correct among 612 distinguishable pairs 440 / 433 / 376 for qc 0.25 / 0.5 / 0.75; D > 0 does not move. The 900-combination factorial ([R 6.3]) gives both-correct between 0.210 and 0.396 over eps x qc x priors x silent share x grouping. Not measured: qc on the final run.

**What this value does not decide / known failure modes.** One number for twelve different physical conditions is an indifference prior, not a model of any of them. Against the benchmark it is wrong for LC: the generator has no lease parameter ([`inject_c2.py` docstring], EC-OP-18), so a dropout never raises `liveliness_ok` or `qos_deadline_missed` there, while the table expects it with probability `qc`; with those fields declared available, every dropout alert pays `1-qc` twice (S2 against S2b, B13c). Capability, as against event severity, is not `qc`: a device that provides no `seq` gives `None` (factor 1), not a cell value.

**Who else reads it / consequences.** As B1, plus the grouped cells (so the choice of `grouped_variant` changes how `qc` acts) and the pair stratum statistics. A post-hoc change breaks E9.

**Options for gab.**
(a) 0.5 for all conditional cells, sweep 0.25 and 0.75.
(b) 0.25 or 0.75 as headline: states a lean ("conditions mostly fail" or "mostly hold") with no source for either.
(c) split into per-condition parameters: more honest, needs a specification and code change and still has no data.
(d) remove the mismatch at the source by declaring device capabilities (B17(a)) so that the LC and SEQ fields are `None` where the generator provides no basis, and keep `qc` for the rest.

**Suggested default (assistant's opinion).** 0.5 with the 0.25 / 0.75 sweep, combined with (d) for LC: indifference is the only stance the repository can defend, and (d) removes the one place where the generator provably contradicts it.

**Questions to put to the expert.**
1. For a naive-Bayes table with 31 conditional cells and no data, is a single `qc` plus a sweep an acceptable first version, or does the LC mismatch require the split before any headline?
2. How should the paper word the fact that two cells of the same alert (e.g. `liveliness_ok` and `qos_deadline_missed`, both LC) are treated as independent although one lapse raises both?

## B3. `q_stale` (probability that the driver reports `stale`)

**Name / where it lives.** Row `parameters[name=q_stale]` of [Y]; `sensitivity_values.q_stale`; `needs: device_specification`; range 0.25, 0.5, 0.75 (the `qc` grid; the prototype used the raised cell `1-eps`, outside the grid). Needed **only** under the profile `driver_with_diagnostics` (4 cells: `ble_dropout`, `message_drop`, `process_kill`, `uncommanded_lifecycle_transition`, field `system.diagnostics_ok`); the default profile `without_diagnostics` never reads it.

**What it is.** Plain language: given a silenced device, the chance that the driver node has already reported it `stale`. The liveness contract (evidence-channels.md, Bridge node) says stale only for a device expected to publish and silent beyond `stale_lease_ms`; an idle on-demand device (a cuff between measurements) reports `ok` and a dropout shorter than the lease reports nothing. In the code: cell `S` = `eps+(1-2 eps) q_stale`; every other component, C1 and the silent faults included, has `eps`.

**Concrete example.** S3 (S2 under the driver profile). P(A | ble_dropout) = 0.01 + 0.98 q = 0.255, 0.5, 0.745; likelihood ratio (ble_dropout : C1) for a stale report = 25.5, 50, 74.5 and for an `ok` report 0.753, 0.505, 0.258 (C, arithmetic). Posterior P(C1) (C): stale reported 0.0001 / 0.0001 / 0.0000, `ok` reported 0.0041 / 0.0061 / 0.0118 for q_stale 0.25 / 0.5 / 0.75. The cost of a false `stale`: a C1 alert (`measurement_refusal`, all denied) with an unrelated `stale` reading has P(C1) / P(C2) / P(C3) = 0.404 / 0.510 / 0.085, against 0.729 / 0.117 / 0.154 with `ok` (q_stale 0.5).

**Who/what would decide it in a real deployment.** The driver (the thesis bridge node, proposal A, off limits to this task) and its lease: `driver_stale_lease_ms` and `driver_period_ms` of [G] (B14), which have no default; the build refuses the profile while they are awaiting, and the lease "must exceed the longest start-to-reading time the generator can emit", which is above 180 s with the committed registry (`bound_inflation_ms_upper` 180 000 ms; [ADR-074 amendment 4 (3)]).

**Candidate values and what they change.** Grid 0.25 / 0.5 / 0.75. Generator-side facts that bound it (C): ble_dropout durations are 2, 15 and 60 min, drawn uniformly ([G] `injections.yaml`, filled rows 120 000 / 900 000 / 3 600 000 ms); with a lease above 180 s the 2-min level can never be `stale`, so at most 2/3 of drawn dropouts can be, and only those with an open session. In the research generator (stale immediately, period 1 h, no lease) the field was asserted for 104 of 143 alerts on a cuff dropout (72.7%) and for none of 22 alerts on a dispenser dropout, so 104 of 165 (63.0%) for the two in-scope devices ([R 9.2.3], section-5 labelling; this describes the generator, not a driver). Effect on scores: with diagnostics the main log score is 0.901 against 0.894 without under the loose labelling, and improves by 0.017 to 0.032 nats under tight ones ([R 9.2.4]); D > 0 of the pairs does not change ([R 6.2]). A driver that reports an idle cuff as stale worsens the log score by 0.296 nats and asserts the field for 88.6% of C1 alerts ([R 9.2.5]).

**What this value does not decide / known failure modes.** `ok` proves the node and link are alive, not that the sensor measures correctly, so it does not exclude the silent faults. The generator derives sessions from what the device *sent*, so a silent detachment opens no session and `P(stale | cuff_detached) = 0` is a property of the generator, not of the contract ([ADR-074 amendment 4 (2)]). `q_stale` is a requirement on a driver that does not exist on hardware yet.

**Who else reads it / consequences.** Only runs with the driver profile (the manifest's `settings.device_profile.diagnostics_profile` must agree with the run, else `ConfigError`). The extractor must be told which nodes report diagnostics (taken from the manifest).

**Options for gab.**
(a) Headline with `without_diagnostics` (no `q_stale`, no driver rows needed), driver profile as a sensitivity run later.
(b) Headline with `driver_with_diagnostics`: needs `driver_period_ms`, `driver_stale_lease_ms` first, then `q_stale` 0.5.
(c) Both profiles in the headline table side by side.

**Suggested default (assistant's opinion).** (a): it is the code default (`default.yaml`), it needs no value that depends on a driver that has not been built, and [R 6.2] shows the diagnostics change no pair direction.

**Questions to put to the expert.**
1. Given a lease above 180 s, is `q_stale` best modelled as one number or as a function of dropout duration relative to the lease?
2. Should the paper present the driver profile as a deployment *requirement* with the 0.296-nat counterfactual, rather than as an evaluated feature?

## B4. `rep_nat` (natural repeat of two consecutive cuff readings)

**Name / where it lives.** Row `parameters[name=rep_nat]` of [Y]; `sensitivity_values.rep_nat`; dimensionless; `needs: device_specification`; range 0.0098, 0.0197, 0.0393 (0.5x, 1x, 2x the measured value). It sets the 30 `N` cells (`max(rep_nat, eps)`), one per component that can violate a cuff-reading template (`stuck_at` excepted: it is `1-eps`), for the field `signal_quality.cuff_value_repeated`.

**What it is.** Plain language: two successive cuff readings of a healthy device are identical by chance, because the display rounds to a resolution r mmHg. A frozen cuff (`stuck_at`) repeats its value every time; the field separates it from the rest. The generator rounds the observed cuff reading to 1 mmHg by default (decision of gab, ADR-074 amendment 2), so the natural repeat probability is a property of the generator and its noise at that resolution, not a device constant. The field is `None` when the profile declares no resolution (D-16), when fewer than two readings exist, or when the latest reading is outside the evidence window; then the factor is 1.

**Concrete example.** S4 (`range` alert, frozen cuff, `cuff_value_repeated` asserted, everything else denied). Likelihood ratio (`stuck_at` : spontaneous C1) = (1-eps)/max(rep_nat, eps) = 0.99/0.01 = 99 at rep_nat 0.0098 (the floor `eps` is larger), 50.3 at 0.0197, 25.2 at 0.0393 (C). Posterior (C):

| rep_nat | reading A: P(`stuck_at`) | P(C1) | 0.9-set size | reading D: P(`stuck_at`) |
|---|---|---|---|---|
| 0.0098 | 0.946 | 0.029 | 1 | 0.0018 |
| 0.0197 | 0.898 | 0.054 | 2 | 0.0018 |
| 0.0393 | 0.816 | 0.097 | 3 | 0.0018 |

With the field `None` (no resolution declared) P(`stuck_at`) is 0.150 and P(C1) 0.449. A denied reading costs `stuck_at` a factor eps/(1-rep_nat) = 0.0101, 0.0102, 0.0104: almost the same whatever rep_nat.

**Who/what would decide it in a real deployment.** The display resolution of the real cuff (TIAGo-class lab demo, ward cuff) and its noise: a device specification. In the repository the cuff resolution is not known ([R 9.5]); `rep_nat` follows from the 1 mmHg rounding of the generator.

**Candidate values and what they change.** Analytic values for display resolution r ([R 9.3.1]): r 0.1 mmHg 0.0021, 1 mmHg 0.0200, 2 mmHg 0.0388, 5 mmHg 0.0980 (Gaussian cross-check 0.0020, 0.0198, 0.0395, 0.0983). Measured on the fault-free run rounded to 1 mmHg: 350 of 17 797 consecutive pairs = 0.0197 (Wilson 0.0177 to 0.0218) ([R 10.1.1]); 0.0223 on 4 448 pairs in WS04-T18, 0.0204 by the formula ([Y] source_ref). At the *alerts* of the tight labelling the natural asserted rate among non-`stuck_at` cuff-template alerts is 153 of 5 106 = 0.030, above the pair-level 0.0197 because alerts are not random pairs ([R 10.1.3]). Effect on sets (tight, level 0.9, 96 `stuck_at` alerts): sets containing a C1 subtype fall from 95 to 35 and the exact set {`stuck_at`} rises from 0 to 60 at rep_nat 0.0098 and 0.0197; at 0.0393 the exact set is not reached (mean size 6.77 to 3.94); true subtype wrongly removed from the sets of other alerts at level 0.9: 4, 3, 3 of 6 496 ([R 10.1.3]). Pairs: no direction changes ([R 10.2.6]).

**What this value does not decide / known failure modes.** It does not model real cuff freezing behaviour (duration, partial freezing) nor the real display. The unrounded generator would give exactly 0, a perfect `stuck_at` detector that is an artefact ([R 9.3.1]); rounding changed the alert list of 163 of 2 160 pair members ([R 10.0]). Using the pair-level 0.0197 where alerts show 0.030 slightly overstates the evidence of a repeat.

**Who else reads it / consequences.** The 30 cells and the field's reading class (which uses the declared `cuff_resolution`, the same value the generator rounded to: `device_capabilities_from_manifest`). The cell values depend on resolution r: changing r later changes `rep_nat` AND the benchmark.

**Options for gab.**
(a) 0.0197, the value measured on the generator's own fault-free run at 1 mmHg, sweep 0.0098 and 0.0393.
(b) 0.03, the alert-level natural rate (not on the grid; (C) from 153/5106).
(c) 0.0393 headline: conservative against over-crediting the channel.
(d) a value from the real cuff of the lab demo once its resolution is known (then a different benchmark rounding too).

**Suggested default (assistant's opinion).** 0.0197: it is measured on the build that the experiment uses, so cell and generator agree; the 0.5x and 2x sweep brackets the alert-level 0.030.

**Questions to put to the expert.**
1. The cell is conditioned on "a pair of consecutive readings" but evaluated at alerts, which are not random pairs (0.030 against 0.0197): which is the right conditioning event, and does it justify a different headline?
2. How should the paper separate the benchmark artefact (generator-defined rounding) from a claim about real cuffs?

## B5. `delta` (C1 diversion share)

**Name / where it lives.** Row `parameters[name=delta]` of [Y]; `sensitivity_values.delta`; dimensionless; `needs: literature`; range 0, 0.1, 0.25. Two `V` cells: `drug_nonresponse` and `spontaneous_resp`, field `witness.intake_observed`, read only at `resp`. Not required under ablation A4 (the witness cells are removed).

**What it is.** Plain language: of the C1 events at `resp`, the share in which a dose was dispensed but not taken (the patient pockets or diverts it), so that the robot, present and watching, sees no intake. The witness field is asserted (intake not observed) in that case. The cell is `eps+(1-2 eps) delta`. In the benchmark the adherence model has **no dispensed-but-not-taken case** (declared simplification), so the generator's own value is 0 and any larger value models something the ground truth never contains.

**Concrete example.** S5 (`resp` alert, `intake_observed` asserted, everything else denied or `None`). P(A | C1) = 0.01, 0.108, 0.255 for delta 0, 0.1, 0.25 (C). Posterior (C):

| delta | intake asserted: P(C1) / P(C2) / P(C3) | kappa at tau 0.8 | intake denied: P(C1) / P(C2) / P(C3) |
|---|---|---|---|
| 0 | 0.064 / 0.014 / 0.922 | C3 | 0.617 / 0.135 / 0.248 |
| 0.1 | 0.426 / 0.009 / 0.566 | UNDETERMINED | 0.592 / 0.144 / 0.264 |
| 0.25 | 0.637 / 0.005 / 0.358 | UNDETERMINED | 0.548 / 0.160 / 0.292 |

At delta 0 a witness-denied intake is read as a forged dispense (C3) with 0.92; at 0.25 it is mostly C1. With the C3 cells at `qc` 0.5 the competing hypotheses are `dispense_forgery` 0.503 and `dispenser_physical_tamper` 0.402 at delta 0.

**Who/what would decide it in a real deployment.** Adherence literature on diversion or pocketing in supervised administration, from hospital data on refused or hidden doses, and the robot's perception false-negative rate. The repository has neither a verified source nor data ([Y] `needs: literature`; no `bib_key`). An unverified reference cannot be cited.

**Candidate values and what they change.** [R 6.1]: delta 0 / 0.1 / 0.25 leave argmax = truth at 859 of 1879; the non-response vs falsified-dispense group has D > 0 in 0.87 / 0.87 / 0.74 of its distinguishable pairs, its mean `Lambda_A` (indistinguishable) 0.97 / 0.92 / 0.84, and the main log score 0.901 / 0.902 / 0.906. Not measured on the final run.

**What this value does not decide / known failure modes.** It is one share for all C1 events at `resp`, without time or patient dependence. It does not cover witness perception false negatives or a robot not co-located (those are the COLOC cells, B11a). It affects only `resp` alerts.

**Who else reads it / consequences.** `resp` alerts of `ours`; the non-response group of the confounder pairs (its D); not `ours-A4`, B1 to B5 or `ours-hier`. With delta 0 the headline is consistent with the generator's truth; any other value is a model sensitivity and the paper must say so.

**Options for gab.**
(a) 0 for the headline (matches the generator), sweep 0.1 and 0.25 labelled "model sensitivity, not benchmark truth".
(b) 0.1 headline: protects against reading every witness-denied dose as an attack, but the benchmark has no such case, so scores are penalised for a world the ground truth does not contain.
(c) extend the generator with a dispensed-but-not-taken case (a benchmark change, not a value).

**Suggested default (assistant's opinion).** (a): the only value that is neither invented nor contradicting the declared generator.

**Questions to put to the expert.**
1. Is a headline whose delta equals the generator's own value defensible against a circularity objection, given that the table is otherwise prior-driven and not fitted?
2. What class of source would be acceptable for a diversion share in an inpatient setting, and what would you do if none is verifiable?

## B6. `dispense_bounce_interval_ms` (T_b)

**Name / where it lives.** Row `parameters[name=dispense_bounce_interval_ms]` (symbol T_b) of [Y]; `sensitivity_values.dispense_bounce_interval_ms`; milliseconds; `needs: device_specification`; range 1 000, 10 000, 30 000, 60 000, 180 000. Registry name proposed in ADR-032; **not yet an entry of the registry** ([M] "Parameters"). One `C` cell (condition DSP, `dispenser_bounce` raises the interval field with probability `qc`; counted here, not in B13) plus the reading class of `dispenser.interval_since_previous_ms`, read at `hold`, `count`, `resp`, `int`.

**What it is.** Plain language: the interval under which two consecutive openings of the dispenser are considered a contact bounce of the sensor rather than two deliberate openings. Code: the reading class of the field is A if the interval is at most T_b, D if above, `None` for the first opening of a stream or without the key. The field describes the *latest* opening of the evidence window. The interval is device-reported, so a forged dispense can copy it (declared limit).

**Concrete example.** S6 (`count`, a genuine bounce 500 ms after a dose against a double take 120 s after, the research placeholders). `Lambda_X` = log P(e_X | `dispenser_bounce`) - log P(e_X | `double_take`) for the alert of member X, `D = Lambda_bounce-member - Lambda_double-take-member` (C, repository rule):

| T_b | no content sensing: Lambda (bounce member / double-take member) | D | P(`dispenser_bounce`) at the bounce alert | content sensing: D |
|---|---|---|---|---|
| 1 000 to 60 000 ms | 3.91 / -0.68 | 4.60 | 0.847 | 13.79 |
| 180 000 ms | 3.91 / 3.91 | 0.00 | 0.847 | 9.19 |

At 180 s the double-take interval (120 s) is below T_b, so both members read A and the interval separates nothing; without content sensing D drops to exactly 0.

**Who/what would decide it in a real deployment.** The dispenser specification: contact debounce time of the opening sensor, firmware interval reporting. The analisi nominal "below one second" is illustrative and unverified. Constraint inside the project: T_b must stay below every double-take gap and above the bounce interval, so it is bounded by `double_take_gap_ms` (B14, placeholder 2 min) and `dispenser_bounce_magnitude_nominal` (placeholder 500 ms).

**Candidate values and what they change.** [R 4.7 / 10.2.6]: for T_b 1, 10, 30 and 60 s the results are identical (D > 0 in 217 of 256 distinguishable double-take-vs-bounce pairs at class level; accepted-channel model 0.85 of group 1 and both-correct 433 of 612); at 180 s group 1 falls to 147 of 256 at class level (0.57 and 363 of 612 in the subtype model); median `Lambda_A` of group 1 indistinguishable 0.68 to -3.91. Stress variants (bounce gap equal to the double-take gap) are separated by content change only; without content sensing (`stress_nocontent_*`) by nothing (D = 0 in 38 and 38 pairs). Not measured: any value between 60 and 180 s, or below 1 s.

**What this value does not decide / known failure modes.** An attacker who copies the bounce timing defeats the interval (group 4: both members `Lambda` +4.38, D = 0, [R 10.2]); the C3 interval cells are `eps` and do not model attacker timing; the informed-forger coherence on the interval chain is an unconfirmed generator choice ([ADR-074 amendment 4 (1)]; about 7 of 16 forged-first-dose pairs of each informed no-auth variant would be distinguishable under the alternative).

**Who else reads it / consequences.** The reading class of the dispenser group for every `hold`, `count`, `resp`, `int` alert; the pair groups 1 and 4; A4 (kept). Changing it after the test run breaks E9.

**Options for gab.**
(a) 10 000 ms: inside the plateau 1 to 60 s, used by the research for the accepted-channel results.
(b) 1 000 ms: the analisi nominal, most conservative, but real debounce may exceed it.
(c) 60 000 ms: tolerant of slow sensors, close to the separation limit if a real double-take gap is shorter than assumed.

**Suggested default (assistant's opinion).** 10 000 ms: inside the plateau, so no result of the research depends on the exact number, and far from the 180 s collapse.

**Questions to put to the expert.**
1. How should T_b be related to `double_take_gap_ms` so that the pair design never makes it a free parameter of the headline (e.g. T_b <= gap/2)?
2. Is a content-sensing dispenser a realistic default for the headline, given that without it the stress variants are undetectable by construction?

## B7. `tau` (abstention threshold)

**Name / where it lives.** Row `parameters[name=tau]` of [Y]; `sensitivity_values.tau`; dimensionless; `needs: gab`; range 0.5, 0.67, 0.8, 0.9, 0.95, 0.99.

**What it is.** Plain language: how sure the class posterior must be before the method names a cause rather than abstaining. `kappa` = the class with the largest `p_kappa` if that value is at least `tau`, otherwise UNDETERMINED; a tie at the maximum is UNDETERMINED. UNDETERMINED is not a key of `p_kappa` and not a cause of the model. `tau` is not in the model-version token: it changes the label and the metrics built on it, not the posterior, the log score, the Brier score or the calibrated set.

**Concrete example.** Class posteriors of three alerts (C) and the label by tau:

| tau | S1 (`count`, double take): C1 0.525 | S11 (`count`, gap only, qc 0.5): C3 0.747 | S2 (`sched`, loud dropout): C2 0.996 |
|---|---|---|---|
| 0.5 | C1 | C3 | C2 |
| 0.67 | UNDETERMINED | C3 | C2 |
| 0.8 | UNDETERMINED | UNDETERMINED | C2 |
| 0.9 to 0.99 | UNDETERMINED | UNDETERMINED | C2 (0.99 holds: 0.996) |

Under the uniform prior the quiet cases never exceed about 0.57 (S1 0.525; `range` with nothing raised 0.527, S12), so every tau above 0.57 abstains on them; tau 0.5 names a cause there.

**Who/what would decide it in a real deployment.** The cost of a wrong cause against an abstention for the people who read the alert: a clinical-safety judgement, plus the workflow (an abstention leaves the full set to the reader). A design choice meanwhile ([Y] source_ref); the repository has no clinician input.

**Candidate values and what they change.** [R 6.1] (class-level prototype, 1879 pair members; direction only): tau 0.5: UNDETERMINED / right / wrong = 308 / 739 / 832, all 832 wrong ones are C1 for a C2 or C3 member, 618 of 618 bounce members called confident C1, silent-fault alerts with confident C1 141 of 433; tau 0.67: 1375 / 307 / 197; tau 0.8, 0.9, 0.95: 1711 / 168 / 0; tau 0.99: 1839 / 40 / 0. The main-population log score and Brier are unchanged by tau.

**What this value does not decide / known failure modes.** It cannot repair the silent faults: any value that makes C1 confident makes them confident C1 ([R 7.3]); the remedy of the paper is the set and the diagnosability matrix. At the class level it interacts with the class prior (B9): under `c1_heavy` S1 becomes C1 0.832 and is labelled at tau 0.8 while `range` with nothing raised (0.784) is not.

**Who else reads it / consequences.** `kappa`, hence the kappa-based metrics of WS08-T09 (confident right, confident wrong and UNDETERMINED counts) and the comparison with `ours-hier`; not the sets, the log score, the pair quantity or detection metrics. A tau chosen after seeing test results breaks E9.

**Options for gab.**
(a) 0.8 as the reported operating point and a risk-coverage curve over all six values.
(b) 0.9: stricter, leaves almost every quiet case undetermined.
(c) 0.67: labels 336 more of the 1879 members than 0.8 (1375 against 1711 UNDETERMINED, C from [R 6.1]), 139 of them right and 197 wrong in the class-level prototype.
(d) choose tau on the calibration part by a stated cost ratio (needs a ratio that the repository does not have).

**Suggested default (assistant's opinion).** 0.8 with the curve: the prototype shows no confident-wrong member between 0.8 and 0.99 and 832 at 0.5, and the headline conclusion does not rest on a single tau.

**Questions to put to the expert.**
1. Which cost ratio (wrong cause : abstention) would you assume for a ward alert, and how should a pre-clinical paper state it without implying clinical validation?
2. Should the kappa-based metrics be demoted to secondary now that the output is a set?

## B8. `cumulative_level` (level of the cumulative subtype set)

**Name / where it lives.** Row `parameters[name=cumulative_level]` of [Y]; `sensitivity_values.cumulative_level` (required in the block, [T10] judgment call 2); `needs: gab`; range 0.8, 0.9, 0.95.

**What it is.** Plain language: the set of causes shown is the most probable subtypes whose probabilities add up to this level. In the headline run the set of an alert is the **conformal set** (target `1 - set_alpha`, B17(c)); `cumulative_level` is used only as the fallback for a population without a fitted calibrator (counted as `cumulative_fallback`) and in sensitivity runs without calibration. It is not in the model-version token. The set is a posterior under the model, **not calibrated to its level** ([R 9.4]).

**Concrete example.** S1: ranked subtypes `dispense_forgery` 0.219, then `dispenser_physical_tamper`, `dose_omission`, `double_take`, `spontaneous_count` 0.175 each, `dispenser_bounce` 0.053. The cumulative sum is 0.744 after four, 0.919 after five, 0.972 after six: the set has 5 subtypes at level 0.8 and 0.9 and 6 at 0.95 (C). In S2 one subtype (0.967) suffices at every level.

**Who/what would decide it in a real deployment.** The reader's tolerance for set size against missing the true cause; a design choice. With the conformal set the guarantee is the calibration target, not this level.

**Candidate values and what they change.** Subtype sets ([R 9.4.2], pair members, design uniform): level 0.8 / 0.9 / 0.95 give coverage 60% / 74% / 98% and mean size 4.92 / 5.88 / 6.90. Main population, section-5 labelling ([R 9.4.6], uniform): 85% / 87% / 88%, size 4.87 / 6.35 / 7.44. For the headline conformal sets (tight labelling, 100 test patients, 5 692 alerts, [R 10.3.1]): target 0.9 gives marginal 90.8% at mean size 2.93 and Mondrian per template 93.1% at 3.39; target 0.8 gives 84.9% at 2.53; target 0.95 gives 95.7% at 5.56. The marginal statement does not hold per true class: C3 48.6%, C2 81.9%, C1 96.6% ([R 10.3.2]).

**What this value does not decide / known failure modes.** Coverage of the cumulative set rests on the model being right; at level 0.9 it covers only 74% of pair members (the bounce members of group 1: 16 of 310). The conformal guarantee is **marginal**, needs exchangeable alerts and is approximate when a patient contributes several correlated alerts ([ADR-074 amendment 5]); it says nothing for another population (the transfer from the main population to the pairs gives 83.9% at the 0.9 target, [R 10.4]). Never write "distribution-free coverage" without that qualification.

**Who else reads it / consequences.** The fallback selector and the `attribution_sets` metrics of populations without a calibrator; `top1_fill` is reported next to it.

**Options for gab.**
(a) 0.9 as the declared fallback and for the cumulative-set rows of the report.
(b) 0.95: covers pair members (98%) but sets are 1 subtype larger.
(c) 0.8: smaller sets, 60% coverage on pairs.

**Suggested default (assistant's opinion).** 0.9, reported as an uncalibrated set next to the calibrated one, because it is the printed row of the research and keeps the cumulative sets comparable with it.

**Questions to put to the expert.**
1. Should the paper report cumulative-level sets at all, or only conformal sets with the cumulative set as a labelled uncalibrated baseline?
2. For one headline `set_alpha`, would you prefer marginal or Mondrian-per-template calibration given the 48.6% C3 conditional coverage?

## B9. Class priors design (`class_priors`)

**Name / where it lives.** Row `class_priors` of [Y] (`designs`); `sensitivity_values.class_priors` takes a declared name; `needs: gab`; designs `uniform` (reference), `c1_heavy`, `c2_heavy`, `c3_rare`, `c3_heavy` (the last four `illustrative`).

**What it is.** The prior probability of each class before seeing evidence, the same row for every template, restricted to the classes that have a component at the template and renormalised (C1 has none at `sys` and `int`). ADR-074 decision 2: priors come from the literature or a declared design choice, **never from the injection rates of the benchmark** (the rates 0.3 / 0.3 / 0.2 would be circular). Designs (C1, C2, C3): uniform 1/3 each; `c1_heavy` 0.6 / 0.3 / 0.1; `c2_heavy` 0.3 / 0.6 / 0.1; `c3_rare` 0.45 / 0.5 / 0.05; `c3_heavy` 0.2 / 0.2 / 0.6. Only these names can be supplied.

**Concrete example.** S1 (`count`, double take, all denied) under the five designs (C):

| design | P(C1) / P(C2) / P(C3) | kappa at 0.67 | kappa at 0.8 | kappa at 0.5 |
|---|---|---|---|---|
| uniform | 0.525 / 0.081 / 0.394 | UNDETERMINED | UNDETERMINED | C1 |
| c1_heavy | 0.832 / 0.064 / 0.104 | C1 | C1 | C1 |
| c2_heavy | 0.641 / 0.198 / 0.161 | UNDETERMINED | UNDETERMINED | C1 |
| c3_rare | 0.797 / 0.137 / 0.067 | C1 | UNDETERMINED | C1 |
| c3_heavy | 0.293 / 0.045 / 0.661 | UNDETERMINED | UNDETERMINED | C3 |

S12 (`range`, nothing raised): the likelihood ratio of a C1 subtype to the silent `cuff_silent_bias` is exactly 1 (log 0.0), so the posterior is the prior odds: P(C1) / P(C2) / P(C3) = 0.527 / 0.200 / 0.273 (uniform), 0.784 / 0.149 / 0.068 (`c1_heavy`), 0.518 / 0.393 / 0.090 (`c2_heavy`), 0.676 / 0.285 / 0.039 (`c3_rare`), 0.341 / 0.129 / 0.530 (`c3_heavy`) (C); none reaches 0.8.

**Who/what would decide it in a real deployment.** The aetiology of ward alerts: hospital incident statistics, device failure data, attacker prevalence. None collected; none verified in the bibliography. The class-frequency of the benchmark must not be used.

**Candidate values and what they change.** [R 6.1] one-at-a-time (prototype): main log score / Brier uniform 0.901 / 0.536, `c1_heavy` 0.708 / 0.397, `c2_heavy` 0.997 / 0.680, `c3_rare` 0.844 / 0.534, `c3_heavy` 1.181 / 0.718; confident C1 for members whose truth is not C1 at tau 0.8: 0, 776, 0, 700, 0; silent-fault alerts with confident C1: 0, 141, 0, 23, 0 (of 433). The prior equal to the benchmark's own class frequency per template (a CIRCULAR DIAGNOSTIC, not a method) scores 0.573 / 0.312, which is what the better scores of `c1_heavy` partly reflect ([R 5.4]). The log score of the prior alone is 1.099 ([R 0]).

**What this value does not decide / known failure modes.** Any prior that makes C1 confident makes the silent faults confident C1: 776 confident-C1 non-C1 members under `c1_heavy`, 700 under `c3_rare` ([R 7.3]). The better scores of `c1_heavy` are consistent with the benchmark's C1-dominated base rate (at `range`, 7 506 of the 8 243 alerts of the research population are C1, [R 5.4]) and would not carry to another ward. One row for all templates ignores that `range` alerts are overwhelmingly C1 by their nature.

**Who else reads it / consequences.** The posterior and everything built on it (log score, Brier, calibration curves, the conformal sets via the token), `kappa` with `tau`. Not the pair quantity (prior-free). A change after the test run breaks E9.

**Options for gab.**
(a) `uniform` as the headline, the other four as the declared sensitivity ("no prior information", states the limit plainly).
(b) `c3_rare`: encodes "attacks are rarer than faults" without a source.
(c) per-template or per-population priors (needs a spec change and sources).

**Suggested default (assistant's opinion).** `uniform`: the only design that needs no unsourced claim and is the research reference; the paper reports the four others as sensitivity and states that the benchmark base rates were deliberately not used.

**Questions to put to the expert.**
1. Is there a non-circular way to give the headline a realistic class prior in a pre-clinical benchmark, or is `uniform` plus a sweep the honest choice?
2. How should `tau` be reported alongside the prior so that readers cannot mistake a prior-driven label for evidence?

## B10. Within-class weights (`pi_designs`)

**Name / where it lives.** Row `pi_designs` of [Y]; `sensitivity_values.pi_designs`; `needs: gab`; designs `uniform` (reference), `quiet_rare`, `quiet_common` (illustrative).

**What it is.** The weight of each component inside its class, normalised over the components of the class that can violate the template. `uniform` gives every component weight 1, so it is uniform over *components*: a subtype with two knowledge levels (`replay`, `dispense_forgery`, `presence_spoof`) weighs twice a subtype with one; whether it should be uniform over subtypes is a point left to gab ([M]). `quiet_rare` / `quiet_common` multiply the weight of the quiet groups by 0.25 / 4: quiet C2 = `stuck_at`, `cuff_silent_bias`, `dispenser_bounce`; quiet C3 = `replay_informed`, `injection_informed`, `dispense_forgery_informed`, `presence_spoof_informed`, `dispenser_physical_tamper`; quiet C1 = the five `spontaneous_*` events.

**Concrete example.** S1 under the three designs (C):

| design | P(C1) / P(C2) / P(C3) | leading subtypes |
|---|---|---|
| uniform | 0.525 / 0.081 / 0.394 | `dispense_forgery` 0.219; `dispenser_physical_tamper`, `dose_omission`, `double_take`, `spontaneous_count` 0.175 each |
| quiet_rare | 0.627 / 0.058 / 0.315 | `dose_omission` 0.279, `double_take` 0.279, `dispense_forgery` 0.210, `dispenser_physical_tamper` 0.105, `spontaneous_count` 0.070 |
| quiet_common | 0.454 / 0.130 / 0.416 | `spontaneous_count` 0.303, `dispense_forgery` 0.215, `dispenser_physical_tamper` 0.202, `dispenser_bounce` 0.115 |

The same alert is led by a different subtype in each design while the 0.9 set stays at 5 subtypes.

**Who/what would decide it in a real deployment.** Ward incident statistics, device failure data and attacker prevalence; none collected.

**Candidate values and what they change.** Pair members ([R 9.4.2], level 0.9): coverage / size uniform 74% / 5.88, `quiet_rare` 65% / 5.49, `quiet_common` 82% / 5.51 (level 0.8: 60% / 4.92, 56% / 3.96, 76% / 4.24). Main population, section-5 labelling ([R 9.4.6], level 0.9): uniform 87% / 6.35, `quiet_rare` 85% / 5.50, `quiet_common` 83% / 5.84; at level 0.8 `quiet_rare` covers only 35% (size 3.69) because it is poorly matched to a population dominated by quiet C1 events. [R 10.2.6]: D > 0 unchanged; both-correct of 612 distinguishable pairs 433 / 376 / 433. The benchmark must not be used to choose among them ([R 9.4]).

**What this value does not decide / known failure modes.** The quiet-group weights are the only axes explored; nothing about C2-versus-C3 relative frequency beyond them. The pair quantity depends on the design only through the within-subtype level weights of the three two-level subtypes ([M] "The pair quantity"). The share of silent faults inside C2 is a derived quantity of the design.

**Who else reads it / consequences.** The posterior and the token; the pair `Lambda` of the three two-level subtypes. A change after the test run breaks E9.

**Options for gab.**
(a) `uniform` over components (reference), the other two as sensitivity.
(b) uniform over *subtypes* (a spec change: levels would split the subtype weight), to avoid favouring subtypes with two levels.
(c) `quiet_rare`: plausible to some readers (silent faults and sophisticated attacks are rarer) but unsourced.

**Suggested default (assistant's opinion).** `uniform`, noting in the paper that it is uniform over components and reporting (b) as a sensitivity if gab wants it.

**Questions to put to the expert.**
1. Uniform over components or over subtypes: which is easier to defend, given that the knowledge level is an attacker property, not a cause?
2. Is a two-design sweep enough, or should the sweep include a design that is C2-silent-heavy?

## B11. The cells that gab must decide (9 cells, 5 conditions)

**Name / where it lives.** Rows of `cells` in [Y] with `needs: gab`, all of form `C` = `eps+(1-2 eps) qc`, `sensitivity_range` 0.25 / 0.5 / 0.75. In this version all nine take the shared `qc` (B2); the decision of gab is first *whether the stated condition is a sensible model* and only second its probability.
- **(a) COLOC** (3 cells): `dispense_forgery_naive`, `dispense_forgery_informed`, `dispenser_physical_tamper` x `witness.intake_observed`: "the witness reads False only when the robot is co-located and saw nothing" (threat model TX-4).
- **(b) D5** (2): `nav_delay`, `localisation_noise` x `system.nav_task_failed`: "the task layer reports a late arrival as a failed task" (evidence-channels D-5, amended by ADR-040; hypothesis H-OVERRUN).
- **(c) IDCHECK** (1): `presence_spoof_naive` x `witness.identity_confirmed`: "how the robot checks identity" (D-6).
- **(d) LATE** (1): `injection_naive` x `crypto_temporal.timestamp_implausible`: "a naive injected message carries a stale or future stamp".
- **(e) PULSE** (2): `replay_informed`, `injection_naive` x `cross_device.pulse_vs_ecg_hr_diff`: "an informed attacker does not patch the pulse rate".

**What it is.** (a) The witness field is asserted (no intake seen) for a forged dispense only if the robot is in the room and looks; it is also asserted for a patient who diverts the dose or a perception false negative, so the field cannot tell them apart. (b) Whether the robot-task layer emits `ROBOT_TASK outcome=late` at the deadline determines whether a navigation delay can raise `nav_task_failed` at all; `impossible_goal` (a failed navigation) is `1-eps`. (c) Whether the robot encodes an identity check; for `int` the witness fields are context (AD-3) and no template reads this cell: it is a **dead awaiting cell**, with no effect on any posterior of the headline run. (d) A naive forger does not manage the time metadata. (e) The pulse rate reported by a forged cuff message disagrees with the ECG heart rate beyond the coherence tolerance (the forged pulse of a naive injection is drawn in the population bounds `injection_naive_pulse_lower_bpm`, `injection_naive_pulse_upper_bpm`, B14).

**Concrete example.**
(a) S5/S7 (`resp`, `intake_observed` asserted, delta 0): P(C1) / P(C2) / P(C3) = 0.116 / 0.039 / 0.845 (qc 0.25), 0.064 / 0.014 / 0.922 (0.5), 0.046 / 0.006 / 0.948 (0.75); log-likelihood ratio `dispense_forgery` : `drug_nonresponse` = 2.72, 3.44, 3.79 (C). Together with B5: at delta 0.25 and qc 0.5 the same reading is C1 0.637, C3 0.358.
(b) S8 (`sched`, `nav_task_failed` asserted): P(C2) = 0.907, 0.932, 0.949 for qc 0.25, 0.5, 0.75; leading subtypes `impossible_goal` 0.590 / 0.461 / 0.378 and `nav_delay` = `localisation_noise` 0.152 / 0.233 / 0.285; log-likelihood ratio `nav_delay` : `measurement_refusal` = +3.24, +3.91, +4.31 when asserted and -0.28, -0.68, -1.36 when denied (C). If the layer does not report lateness the right cell for `nav_delay` is `eps`, not `qc`.
(d) timestamp asserted: likelihood ratio (`injection_naive` : C1) = (eps+(1-2 eps) qc)/eps = 25.5, 50, 74.5 (C); the S13 mixture is in B13a.
(e) S10 (`range`, pulse difference asserted): P(C3) = 0.839, 0.913, 0.937; `replay` 0.693 / 0.788 / 0.878, `injection_naive` 0.099 / 0.101 / 0.044 (C).

**Who/what would decide it in a real deployment.** (a) the robot's perception false-negative rate and presence logic (lab demo WS10, field data), plus a diversion rate (B5); (b) the design of the robot task layer, a project decision, not a device property; (c) the robot's identity-check capability; (d), (e) the attacker model of the threat model (knowledge-level flags). In the repository: `threat-model.md` (Attack-to-evidence table), `evidence-channels.md`; no probability anywhere.

**Candidate values and what they change.** Grid 0.25 / 0.5 / 0.75 for all; the examples above show the effect per condition. Evidence that the witness cells matter: removing the witness lowers D > 0 for the non-response vs falsified-dispense group from 0.87 to 0.74 ([R 6.2]; McNemar b = 14, c = 0, [R 0]); `qc` as a whole moves both-correct from 440 to 376 of 612 ([R 10.2.6]). Not measured per condition.

**What this value does not decide / known failure modes.** (a) one `qc` for forgery and physical tamper though their physics differ; (b) a yes/no design fact is modelled as a probability; (c) dead; (d) and (e): the capability sets in [G] `injections.yaml` give `coherent_pulse: false` for the naive level and `true` for the informed one, while the PULSE cell of `replay_informed` is conditional on "the pulse is not patched" and the threat-model text for the informed level speaks of "the pulse patched"; the consistency of the cell with the capability flag should be checked before the cell is kept.

**Who else reads it / consequences.** (a), (c) are removed by A4 (witness cells); (b) is removed by A4 (`nav_task_failed`), which then makes `nav_delay` less distinguishable (the quantity A4 measures); (d), (e) are kept. Pair groups 2 (witness) and 3 (robot outcome) depend on (a) and (b).

**Options for gab.**
(a) keep the shared `qc` for all nine and say so (indifference).
(b) for the yes/no facts (D5, IDCHECK) declare the robot capability in the device profile: if the task layer is declared not to report lateness the field becomes `None` (factor 1) instead of a half-weight cell.
(c) a separate parameter per condition (specification and code change).
(d) drop the PULSE cell of `replay_informed` if the capability review shows it contradicts the informed attacker.

**Suggested default (assistant's opinion).** (a) for COLOC, LATE, PULSE and (b) for D5; IDCHECK needs no decision for the headline (dead cell). The D5 fact is simulated in WS07 and can be stated, so it does not need a probability.

**Questions to put to the expert.**
1. For conditions that are design facts of the test bench (D5, IDCHECK), is masking via capability better than a probability that cannot be estimated?
2. How would you test the PULSE cell against the informed attacker's capability flags without using the benchmark's own labels?

## B12. Modes of the grouped cells (`message_drop`, `injection_naive`, `dispense_forgery_naive`)

**Name / where it lives.** `grouped_cells.ble_seq_gap.modes` and `grouped_cells.cross_device_signal_quality.modes` in [Y]; `needs: gab`; sensitivity `grouped` / `independent`. The variant is a run option (`grouped_variant`: `reference`, `fully_independent`, `reference_plus_cross_device`), not a key of `sensitivity_values`. The weights are expressions in `qc` and `1-qc`.

**What it is.** `system.ble_link_quality` and `system.seq_gap` overlap: the delivery ratio is exactly 1.0 when no value is missing, so they are read as ONE joint class of four, in the order (link, gap): `clean` (D,D), `gap` (D,A), `degraded` (A,D), `gap_degraded` (A,A). Each component has modes; `P(j | s) = sum over modes of weight x [(1-eps) 1(j = mode) + eps/3 1(j != mode)]`; a component without modes is `clean`. Modes: `ble_dropout` gap_degraded `qc` / degraded `1-qc`; `message_drop` gap `qc` / clean `1-qc`; `injection_naive` and `dispense_forgery_naive` gap `1-qc` / clean `qc`. The modes of `message_drop`, `injection_naive` and `dispense_forgery` (naive) are design choices that need gab; those of `ble_dropout` are inherited from the research prototype. The cross-device group (diff, ecg_sqi, ppg_sqi) is independent in the reference; its only variant adds the common cause `ecg_noise` as a nuisance at `range`, `hold`, `resp`, `sys`.

**Concrete example.** S9 (`sched`, `message_drop`-like pattern, no lifecycle change). Reference against fully independent (C):

| reading | variant | P(C1) / P(C2) / P(C3) | leading |
|---|---|---|---|
| gap asserted, link denied | reference | 0.058 / 0.194 / 0.748 | `injection_naive` 0.738, `message_drop` 0.185 |
| gap asserted, link denied | fully independent | 0.163 / 0.114 / 0.722 | `injection_naive` 0.695, `message_drop` 0.088 |
| gap and link both asserted (long run of losses) | reference | 0.681 / 0.146 / 0.173 | `measurement_refusal` 0.341, `spontaneous_sched` 0.341 |
| gap and link both asserted | fully independent | 0.017 / 0.909 / 0.074 | `message_drop` 0.889 |

By hand: for `message_drop` the reference gives the joint (A,A) only the leak `eps/3` = 0.0033, the independent product gives 0.5 x 0.5 = 0.25 (P(gap) x P(degraded), qc 0.5): the reference explains a long loss run only by `ble_dropout` (mode gap_degraded). S11 (`count`, gap only) shows the same difference for `qc`: independent P(C2) 0.106 / 0.123 / 0.075 against reference 0.132 / 0.224 / 0.271 (B2).

**Who/what would decide it in a real deployment.** The statistics of how a real link failure shows in the delivery ratio and in the sequence numbers (device specification, field logs); the threat model for forged messages. In the repository: the fault-model row of `message_drop` lists the link degradation and the gap as two independent conditions; the reference modes are a modelling choice of ADR-074 amendment 3.

**Candidate values and what they change.** Prototype grouping variants ([R 6.1], rows "group"): main log score 0.833 and 0.884 against 0.901 ungrouped, with UNDETERMINED / right / wrong at tau 0.8 of 1674 / 205 / 0 and 1634 / 245 / 0; mean `Lambda_A` of the indistinguishable group 1 2.14 and 1.72 against 2.32. The 900-combination factorial includes the grouping ([R 6.3]). Not measured on the final model.

**What this value does not decide / known failure modes.** The independence of the other fields is an ASSUMPTION of the model, not a finding. The reference makes a degraded link without a gap nearly impossible for `message_drop` (leak only). `crypto_temporal.seq_repeat` is outside the pair. The hierarchical rule `ours-hier` treats `seq_gap` differently by design (ADR-075, proposed): it blocks C1 but is not C2 evidence; a comparison of the two methods must say so.

**Who else reads it / consequences.** All seven templates read the pair; the choice of variant changes every alert with a gap or a degraded link, the pair quantity for the dropout and forgery groups and the model-version token.

**Options for gab.**
(a) keep the reference modes and report `fully_independent` as the labelled sensitivity (already planned).
(b) add a `gap_degraded` mode to `message_drop` (a specification change, so that a long loss run is explained by it too).
(c) run the headline with `fully_independent`: matches the fault-model table literally, double-counts one dropout.

**Suggested default (assistant's opinion).** (a), plus a sentence in the paper that the fully independent product double counts; (b) is worth deciding before the headline because it changes the S9 result by a factor of six on a plausible alert.

**Questions to put to the expert.**
1. Is a joint cell with hand-set modes preferable to the independent product for a paper that claims no learned parameters, or does it add a hidden degree of freedom?
2. Should `message_drop` be allowed the `gap_degraded` mode, given the fault-model table lists both conditions?

## B13. Device-specification cells (time bound, link metric, lease/deadline, sequence, ECG quality, killed target)

**Name / where it lives.** Rows of `cells` in [Y] with `needs: device_specification` other than the natural repeat, `S` and `DSP` cells (those are B4, B3 and B6). All take `qc`.
- **(a) BOUND** (3): `clock_skew`, `out_of_order`, `timestamp_manipulation` x `crypto_temporal.timestamp_implausible`.
- **(b) DEGRADE** (1): `message_drop` x `system.ble_link_quality`.
- **(c) LC** (9): `ble_dropout`, `process_kill`, `message_drop`, `battery_depleted` x (`liveliness_ok`, `qos_deadline_missed`) (8) and `link_delay` x `qos_deadline_missed` (1).
- **(d) SEQ** (6): `ble_dropout`, `message_drop` x `seq_gap`; `injection_naive`, `dispense_forgery_naive` x `seq_gap` (form `Cn`) and x `seq_repeat` (form `C`).
- **(e) SQI** (1): `ecg_noise` x `signal_quality.ecg_sqi`.
- **(f) TARGET** (1): `process_kill` x `system.node_lifecycle`.

**What it is.** (a) The time-evidence field is raised only beyond the bound: a message late beyond the reorder delay `D`, or stamped later than the receive time by more than `skew_max`; within the bound it is accepted and leaves no evidence. (b) The losses degrade the delivery ratio below the floor only for a long run. (c) The liveliness lease or the QoS deadline lapses only when the silent interval exceeds it. (d) The device provides sequence numbers and a later message is delivered, so a gap is seen; a naive forger either repeats an accepted number or jumps ahead. (e) The ECG device reports a quality index. (f) The gateway writes a link-lost state for a device target; a robot target reports no transition.

**Concrete example.** (c) S2 against S2b (`sched`, cuff dropout, qc 0.5, eps 0.01): with `liveliness_ok` and `qos_deadline_missed` denied (a dropout shorter than the lease), P(`ble_dropout`) = 0.967; with both asserted, 0.996; each denied LC cell costs the C2 hypotheses a factor 1-(eps+(1-2 eps) qc) = 0.5 (C). The generator never raises them (no lease parameter), so in the benchmark this is a systematic mismatch if the fields are declared available. (a) S13 (`sched`, `timestamp_implausible` asserted, everything else denied): P(C1) / P(C2) / P(C3) = 0.050 / 0.428 / 0.522 (qc 0.25), 0.033 / 0.276 / 0.692 (0.5), 0.025 / 0.213 / 0.761 (0.75); leading `timestamp_manipulation` 0.424 / 0.543 / 0.631, `link_delay` 0.310 / 0.136 / 0.054, `injection_naive` 0.081 / 0.138 / 0.122, `clock_skew` 0.106 / 0.136 / 0.158: from qc 0.5 upward more than half of the mass goes to `timestamp_manipulation`, a subtype the benchmark never injects.

**Who/what would decide it in a real deployment.** The device profile: `liveliness_lease_ms` and the data-stream deadline `qos_deadline_ms` (null for an event-driven device) per source (D-8; WS07-T03; no value anywhere, EC-OP-18), the `seq` capability, the clock capability `two_clocks`, the quality-index capability, the gateway behaviour. Repository sources: registry `clock_skew_max_ms` = 1 000 ms (accepted literature-anchored proposal, IHE Consistent Time median error under 1 s, "bounds the median, not the maximum; BLE devices need measurement", illustrative, unverified); `D` is `monitor.reorder_delay_ms` of the run configuration (0 for the labeller; the run value must be a multiple of `step_ms`, guard F10); registry `ble_link_quality_floor` is **missing** (B17(b)).

**Candidate values and what they change.** Grid 0.25 / 0.5 / 0.75 for each; S13 and S2/S2b show the effect. Counting which cells the benchmark can test (C, from [Y] and the subtype table): of the 67 awaiting cells 39 belong to components that benchmark v1 injects and 28 to components it does not; BOUND (3) and TARGET (1) and DEGRADE (1) are entirely outside v1 ([M] "Time cells beyond the bound"), LC has 7 cells outside and 2 inside (`ble_dropout`), SQI is inside but `ecg_noise` is excluded from this version (ADR-071 (c)). Not measured.

**What this value does not decide / known failure modes.** Cells of subtypes that are never injected still enter every posterior as competing hypotheses (A.5); with `family` and `cell_scope` unimplemented the benchmark cannot test them. (e) is a dead cell in the reference: `ecg_noise` violates no template (no template reads `hr_ecg`); it is live only under `reference_plus_cross_device`. `uncommanded_lifecycle_transition` and `process_kill` share `node_lifecycle` with different forms (`R` and `C`).

**Who else reads it / consequences.** The posterior of `sched`, `hold`, `count`, `resp` alerts through `ble_dropout`; the extractor's capability declaration decides which of these fields exist (B17(a)); A4 keeps the aggregate system fields (recomputed over device nodes).

**Options for gab.**
(a) keep `qc` and treat the 28 outside-v1 cells as catalogue structure that cannot be tested; state it.
(b) declare the capabilities `supervised` false and `deadline_ms` null in the benchmark device profile, so that LC fields are `None` (factor 1) and the mismatch disappears; `seq` true (the generator provides it).
(c) implement `family = benchmark_v1` as a sensitivity (a code task: `family` and `cell_scope` are not implemented).

**Suggested default (assistant's opinion).** (a) plus (b): the generator has no lease, so declaring the device unsupervised is the honest statement of what it produces; (c) as a later sensitivity.

**Questions to put to the expert.**
1. When 28 of 67 cells describe subtypes the benchmark never produces, how should the paper present the catalogue-wide posterior without implying that the cells were validated?
2. Is declaring the benchmark devices unsupervised (LC fields `None`) a legitimate device-profile choice or a way of hiding a mismatch?

## B14. Generator rows still awaiting (48)

**Name / where it lives.** 48 rows with `status: awaiting_human_value`, `value: null`, `verified_by: null` ([G]; rendered in `docs/benchmark/parameter-provenance.md`; the loader refuses an unfilled row, `UnfilledParameterError`, so the real benchmark cannot be built until they are filled). They are not inputs of the likelihood table: they define the *data* that the table is scored on. Grouped (count, file, consumer):
- **(a) patient and adherence timing, 4**: `circadian_peak_clock_ms` (`generator_design`, type published_literature, WS04-T03), `mean_delay_ms` (prior file, declared assumption, WS04-T05), `intake_lag_ms`, `double_take_gap_ms` (design choice, WS04-T05).
- **(b) robot and sampling, 2**: `robot_dwell_ms`, `vitals_period_ms` (WS04-T06).
- **(c) driver, 2**: `driver_period_ms`, `driver_stale_lease_ms` (WS04-T18); read only under the profile `driver_with_diagnostics`, which is refused while they are awaiting.
- **(d) injection window durations, 21** (`injections.yaml`, level labels short < medium < long, "agent-proposed grid point for confirmation by H3"): `replay_duration_*`, `injection_naive_duration_*`, `injection_informed_duration_*` (WS04-T08), `hypertensive_spike_duration_*`, `drug_nonresponse_duration_*`, `hypotension_below_hold_duration_*` (WS04-T09), `ecg_noise_duration_*` (3, excluded, WS04-T07).
- **(e) injection magnitudes, 17**: `hypertensive_spike_magnitude_{below,near,above}` (x `scale_range`, registry 20 mmHg), `hypotension_below_hold_magnitude_{below,near,above}` (x distance baseline to `bp_hold_threshold` 100 mmHg), `drug_nonresponse_magnitude_{partial,mild}` (Emax scale in [0,1]; `complete` = 0 is filled) (WS04-T09); `nav_delay_magnitude_{low,medium,high}` (x `sched_window` = 30 min, ADR-068), `dispenser_bounce_magnitude_{nominal,stress_low,stress_high}` (ms) (WS04-T07); `ecg_noise_magnitude_*` (3, excluded).
- **(f) naive forger pulse bounds, 2**: `injection_naive_pulse_lower_bpm`, `injection_naive_pulse_upper_bpm` (WS04-T08; a physiological value: a human supplies it with a source).
(Totals: 4 + 2 + 2 + 21 + 17 + 2 = 48. Without the 6 ECG rows: 42 matter for this benchmark version.) Related defaults that are *not* awaiting rows but device-profile choices in `default.yaml`: `dispenser_content_sensing: false`, `authenticating_devices: []`, `cuff_resolution_mmhg: 1.0`, `pulse_resolution_bpm: 1.0`, `dispenser_reports_interval: true`, `diagnostics_profile: without_diagnostics`.

**What it is.** (a) The clock time at which the latent pressure peaks (model sbp = baseline + A cos(2 pi (t - peak)/24 h) + AR(1) noise, amplitude A = 13.2 mmHg mean in the prior); the mean delay of a late dose; the time from DISPENSE to true INTAKE; the gap of a double take (must exceed the intake lag and every bounce interval, be shorter than every schedule slot). (b) How long the robot stays (sets how many intakes the witness can see) and the period of ECG/SpO2 samples (must divide 86 400 000 ms; at most 100 000 samples a day). (c) Period of the `ok`/`stale` driver reports and the silence beyond which an open session is `stale`; the lease must exceed the longest cuff start-to-reading time the generator can emit (above 180 s with the committed registry). (d), (e) The size of each injected event. (f) The population bounds of a forged pulse.

**Concrete example.** (d) The realised share of a planned injection depends on the placeholder duration D: for `injection_naive` .098 at 30 min, .211 at 1 h, .672 at 4 h, .984 at 12 h, .619 for the grid 1/4/12 h; for `hypotension_below_hold` .029, .057, .231, .517 and .28 ([RB 2]). (e) `nav_delay` at x0.5 / 1 / 2 of `sched_window` (30 min) delays the robot by 15 / 30 / 60 min (C): below 1 nothing is violated, above 1 the task is late. `hypertensive_spike` at x0.5 / 1 / 2 of `scale_range` (20 mmHg) adds 10 / 20 / 40 mmHg to the latent pressure (C). (a) Circadian peak: the out-of-band share of readings moves between 51.6 and 55.8% over 08:00 to 18:00 ([FF 3]).

**Who/what would decide it in a real deployment.** (a) the circadian phase of ward patients (published literature; "no acrophase source exists in the repo", [FF 2]), adherence timing studies, dispenser logs; (b) the ward routine and the robot's visit behaviour (lab demo WS10), the sampling rate of the vitals devices; (c) the driver / bridge node design (thesis, off limits here); (d), (e) design choices ("agent-proposed ... for confirmation by H3"), with physiological values needing a source; (f) population heart-rate bounds from literature. Sources in the repository: none for the 48 rows; the research runs used labelled placeholders (A.6).

**Candidate values and what they change.** Placeholders of the research runs, not proposals: peak 14:00, intake lag 5 s, double-take gap 2 min, dwell 10 min, vitals 60 s, mean delay 20 to 30 min, bounce nominal 500 ms, durations 1 / 4 / 12 h, magnitudes x0.5 / 1 / 2. Sensitivity ranges tested in [FF 3] (one-at-a-time, out-of-band share of readings, B1 alarm day share): peak 08:00 to 18:00: 51.6 to 55.8%, B1 93.6 to 95.4%, and 86% of the variance of the out-of-band share; intake lag 0 to 10 min: no change in pressure, RESP at most 0.015 per day; double-take gap 11 to 120 min: no change in pressure, double takes 0.032 to 0.036 per day; mean delay 5 to 120 min (log): `spontaneous_hold` 0.011 to 0.082 per day (86% of its variance); vitals 1, 5, 15, 30 min: no change in cuff metrics, BLE events on ECG/oximeter 0.65 to 0.375 per day; dwell 1 to 30 min: no change. The joint 240-run design moves the out-of-band share only between 51.2 and 56.7% ([FF 3]). Durations and magnitudes: realised shares in [RB 2]; the lease has no tested value (the build refuses a lease below the longest start-to-reading time).

**What this value does not decide / known failure modes.** The fault-free population is not clean (53% of readings out of band, B1 alarms on 95.7% of days; ADR-071): no row of this group makes it clean, by decision (a population anchored on the literature priors is kept). Uniform placement of windows over the day makes few hit anything (few readings, two intakes), and C1 injections add little over the natural background for `hypertensive_spike` and `drug_nonresponse` ([RB 7]). `ecg_noise` is excluded.

**Who else reads it / consequences.** The real benchmark build (everything downstream); a change after a build invalidates every result built on it, including the sensitivity tables; the manifest records the version. The driver rows interact with `q_stale` (B3). `double_take_gap_ms` bounds `T_b` (B6).

**Options for gab.**
(a) accept the research placeholders as declared design choices (`source_type: design_choice`, `verified_by: null`), each with the rationale of the sensitivity run above, and report the sensitivity ranges.
(b) take only (a) and (f) from literature (needs verified sources) and the rest as design choices.
(c) delegate the physiological rows (peak, bounds) to the WS00 human tasks that name a clinician review, and build the benchmark after.

**Suggested default (assistant's opinion).** (a) for the 42 rows that matter, flagged as design choices; the evidence shows that apart from the peak clock and the mean delay none moves a template-level count materially. The circadian peak and `driver_stale_lease_ms` are the two that deserve a source or an explicit rationale first.

**Questions to put to the expert.**
1. Which of the 42 rows would you fix first and which would you leave as a sweep, given that one row (the peak clock) explains 86% of the variance of the out-of-band share?
2. How should the paper present design-choice durations and magnitudes so that the benchmark is not read as an epidemiological claim?

## B15. `c1_footprint_tail_ms` (with its reason) and `loose_after_ms`

**Name / where it lives.** `run_options.background.c1_footprint_tail_ms` (integer ms, or `awaiting_human_value`), `run_options.background.c1_footprint_tail_reason` (required with a number: "taken from the generator's own pharmacokinetics and not from a clinical value"), `run_options.background.footprint_margin_ms` (default the matching tolerance); and `run_options.attribution.loose_after_ms` (integer ms, `awaiting_human_value`, no default). A headline run with the tail awaiting is a hard failure (`C1_FOOTPRINT_TAIL_AWAITING`); `loose_after_ms` awaiting makes the labelled alerts, the set calibration and the attribution tables unavailable.

**What it is.** The tail: the false-alarm rate is measured on patient-time outside every injection footprint; the footprint of a C1 injection is its window plus a finite physiological tail (a pharmacokinetic effect decays but never reaches zero), so a finite horizon must be stated; it is not a clinical value. `loose_after_ms`: in the truth of an alert, an event is compatible if the alert is decided in `[ref, max(ref, end) + after]`; for the LOOSE labelling it applies to every event, under the TIGHT labelling (primary) a C2 event uses `after = 0` and **C1 and C3 events use `loose_after_ms`**; the three point C2 subtypes (`nav_delay`, `manipulation_failure`, `dispenser_bounce`) are AMBIGUOUS when the loose rule accepts and the tight rule rejects by time, and their headline is the LOOSE figure.

**Concrete example.** Tail: a `drug_nonresponse` window; the effect decays as the elimination of the prior: `elimination_rate_per_h` = 0.0815 (filled row), half-life ln 2/0.0815 = 8.5 h and a daily factor exp(-0.0815 x 24) = 0.141, i.e. a fall by a factor 7.07 per day (C), consistent with the measured decay of the maximum effect from day 1 on: 9.3 mmHg on day 0, 2.5 (day 1), 0.32 (day 2), 0.045 (day 3), 0.006 (day 4) ([NA 1]; successive factors 7.8, 7.1, 7.5, C). With a tail of 0 the natural events that follow an injection count as background false alarms; with a tail of 24 / 48 / 72 h = 86 400 000 / 172 800 000 / 259 200 000 ms the time still under the effect (2.5 / 0.32 / 0.045 mmHg at the end of the tail, read from the table above) is removed from the exposure. `loose_after_ms`: the pair research found the COUNT alert of a morning double take decided at the evening dose, about 14 h after the injected event, under an onset-based matching ([RP 5]); whether the truth rule of WS08-T09 (reference = first decidable instant of the event) already covers that case with a small `after` was not checked for this brief.

**Who/what would decide it in a real deployment.** Neither is a deployment quantity: both are evaluation conventions of the experiment. The tail needs a threshold of "negligible residual effect" (a decision, [T08] M6); `loose_after_ms` follows from how late a template decides (COUNT at day end, RESP up to `delta2` = 2 h after the dose, registry).

**Candidate values and what they change.** Tail: 0 (explicit acceptance of window-only footprints, [T08] M6); 86 400 000; 172 800 000; 259 200 000 ms. Not measured: the repository has no sweep over the tail. Effect direction: a longer tail lowers exposure and removes more natural events from the false-alarm count. `loose_after_ms`: the windows used in the research are 0 (tight, window open), 1 h and 24 h; main-population log score under the section-5 labelling 0.778 (1 h), 0.832 (6 h), 0.901 (24 h) ([R 5.4]); with versus without driver diagnostics the change is +0.007 (24 h loose) and -0.018 (1 h) and -0.031 (window 0) nats ([R 9.2.4]). The smoke test uses 60 000 ms as a TEST VALUE.

**What this value does not decide / known failure modes.** The tail is a convention, not a measurement of a drug; it moves the false-alarm figure and the excess over the natural background, not detection. The labelling choice (tight primary) was made after seeing a result and is declared; `loose_after_ms` also controls what the tight labelling does for C1 and C3, which the ADR names only for C2 (the research prototype applied the closed window to all events). Alerts matched to no event are excluded and counted.

**Who else reads it / consequences.** `background.false_alarms_per_patient_day`, `background.excess_over_background`, `meta.background` (tail value, status and reason); the truth of every alert for the log score, Brier score, calibration curves, the set calibration (fit on the labelled calibration alerts) and the equal-coverage block; both labellings are printed in every table.

**Options for gab.**
(a) tail 86 400 000 ms (one day): the maximum effect is below the cuff error SD (8 mmHg) from day 1 on (about 2.5 mmHg, approximate, C), simple to state; `loose_after_ms` 86 400 000 (the research window of the section-5 labelling).
(b) tail 172 800 000 ms (two days: residual maximum about 0.32 mmHg, below 1 mmHg); `loose_after_ms` 3 600 000.
(c) tail 0 with an explicit statement that footprints are windows only.

**Suggested default (assistant's opinion).** Tail 172 800 000 ms with the reason "residual maximum effect of the generator's own PK model below 1 mmHg (0.32 mmHg at day 2, nonadditivity.md), not a clinical value"; `loose_after_ms` 86 400 000, the window of the research labelling that covers day-end alerts. Both are conventions to be swept ({0, 1 day, 2 days} and {0, 1 h, 24 h}).

**Questions to put to the expert.**
1. What is the most defensible way to define "negligible residual" for a false-alarm denominator without a clinical threshold?
2. Is it acceptable that `loose_after_ms` also acts on C1/C3 under the primary tight labelling, or should the paper present a separate parameter?

## B16. Benchmark size D and the class rates (provisional)

**Name / where it lives.** `n_patients` 200, `n_days` 7, `split_fractions` 0.5 / 0.25 / 0.25, `generation_seed` 0 (`default.yaml`; design choices awaiting confirmation "H3", ADR-067 proposed) and `injection_rate_c1` 0.3, `injection_rate_c2` 0.3, `injection_rate_c3` 0.2, `confounder_pairs_per_variant` 2 (`injections.yaml`, `status: filled`, `source_type: design_choice`, "not a clinical frequency"). The scale 200 x 7 = 1 400 patient-days comes from analisi 5.1.

**What it is.** The size and class mix of the data; rates are Poisson means per patient-day, the subtype uniform within the class (C1 five subtypes, C2 the six driven by the class rate, C3 five); `ble_dropout` (0.0104 per device-hour) and `dispenser_bounce` (0.001 per dispense) follow the device error model, not the class rate. Pairs: 19 variants x 2 = 38 pairs (the committed `injections.yaml` has three groups; the fourth group, `bounce_vs_forged_dispense`, was found only as a research prototype patch, [RP 2]).

**Concrete example.** On the test split (0.25 x 200 = 50 patients x 7 days = 350 patient-days) the placeholder-grid estimate of expected positive events at the current rates is, for n = 200 ([RB 3], "test n=200", **provisional**): `double_take` injected 52, `hypertensive_spike` 21, `measurement_refusal` 21, `dispense_forgery` 14, `presence_spoof` 14, `injection_naive` 8, `injection_informed` 8, `replay` 7, `drug_nonresponse` 6, `hypotension_below_hold` 6, `dispenser_bounce` 0.7. The conformal set calibration needs alerts per template: scaling the research population `m400r` (100 calibration patients x 30 days = 3 000 patient-days, tight labelling, 5 624 alerts: `count` 1 291, `hold` 482, `range` 350, `resp` 3 048, `sched` 453) to 50 x 7 = 350 patient-days gives about 151, 56, 41, 356, 53 alerts, 656 in all (C, factor 350/3000); a Mondrian calibration at set alpha 0.05 needs at least 19 alerts per cell for a finite threshold.

**Who/what would decide it in a real deployment.** Not a deployment quantity; it is an experimental-design choice (power, cost). Constraints in the repository: E9, `ALPHA_BELOW_CALIBRATION_RESOLUTION` (min alpha at least 1/(n_cal + 1)), cost (about 0.58 s and 10 MB per main patient, [RB 6]).

**Candidate values and what they change.** [RB 6] (placeholder grid): n 800 at 0.3/0.3/0.2: 504 s and 8.8 GB, 12 of 13 class-driven non-cuff subtypes below 100 test positives (only `double_take` 206); n 800 at 0.6/0.6/0.6: 5 below 100; n 1 200 at 0.6/0.6/0.6: 2 below (`drug_nonresponse` 79, `hypotension` 71), 756 s, 13.2 GB; n 400 at 1.2: 5 below. Structure that size does not fix: `dispenser_bounce` needs about 28 000 patients for 100 test positives, BLE cuff and dispenser dropouts 2 525 and 6 341. Pairs ([RP 4]): half-width 0.10 / 0.15 / 0.20 for the pair-level D > 0 rate needs 97 / 43 / 25 test pairs, 3 179 / 2 137 / 1 777 pairs in all at test share 0.25; the current 38 pairs give about 9.5 test pairs. The research conformal pair calibration used 3 240 pairs (`p120r`). All are conditional on placeholders and on a single seed; marked provisional.

**What this value does not decide / known failure modes.** One seed of the generator is one benchmark version; the at least five experiment seeds re-draw the split and model randomness only. Rates are not clinical frequencies, and the benchmark's base rates must never set a prior (ADR-074 decision 2). The default pairs are too few for per-variant results; stated limits of the diagnosability matrix apply (informed attacker coherent on every channel; stress variants without content sensing).

**Who else reads it / consequences.** Everything: splits, calibration sizes, bootstrap intervals, alert load per patient-day, the detection-metric denominators; changing it later means a new benchmark version and a full rerun.

**Options for gab.**
(a) keep 200 x 7, 0.3 / 0.3 / 0.2, 2 pairs per variant (the declared design), and report the small-n limits (several subtypes with fewer than 10 test events).
(b) raise to n 800 at 0.6 / 0.6 / 0.6 (the cost table above) before the first test run.
(c) raise the pairs (to about 1 800 to 2 100 for half-width 0.20 to 0.15) and the fourth group.

**Suggested default (assistant's opinion).** (a) for the headline if the guard on the minimum alpha passes, plus (c) at least up to the number the pair claims need; (b) if compute allows, since only then do most class-driven subtypes reach about 100 test events. This is a resource decision more than a statistical one.

**Questions to put to the expert.**
1. For per-subtype claims with 6 to 21 test events, what is the honest way to report intervals and what should be left out of the paper?
2. Is an enriched stress cohort for `dispenser_bounce` (reported apart) preferable to a 35-fold rate increase?

## B17. Other values a headline run needs that were not on the list

**Name / where it lives.** Found by reading the runner (`src/ralmon/eval/runner.py`, `ours.py`, `attribution_report.py`), the notes of [T02] and [T10], the registry file against `src/ralmon/attribution/rule.py`, and `configs/benchmark/default.yaml`. Each item says how it was found.

**What it is, per item.**
- **(a) Device-capability profile of the benchmark devices** (`run_options.detector_params.ours.device_profile`, `{node: {capability: bool}}`; found in [T02] note (3) and [T10]): `status_reports`, `supervised`, `deadline_ms`, `seq`, `two_clocks`, `error_codes`, `battery`, the robot's. The manifest determines only cuff resolution, dispenser content sensing, authenticating devices and diagnostic nodes; "with none declared every capability is absent and every violation of the cuff path is UNDETERMINED". This decides which fields are `None` and therefore which cells are read at all (B2, B13).
- **(b) Registry names missing for the real registry** (found by comparing `configs/registry/hypertension.yaml` with the name list in `rule.py`): `evidence_margin_ms`, `evidence_grace_ms`, `hr_coherence_tolerance`, `hr_coherence_max_age_ms`, `ecg_sqi_floor`, `ppg_sqi_floor`, `ble_link_quality_floor` (OPF-6; consumer: extractor and reading classes) and `priority_sys`, `priority_int`; the runner refuses `ours` before the run (`ConfigError`) until they exist. They define the A/D split of `ble_link_quality`, the quality indices and the pulse difference: numeric, device-specific, owners WS01-T03 / WS00.
- **(c) Set options**: `set_alpha` (target of the calibrated set of each alert, `1 - set_alpha`), `run_options.attribution.set_alphas` (targets of the equal-coverage block), `set_mode` (`marginal` or `mondrian`), `min_cell_size` ([T10] hand-over). Research grid: alpha 0.2, 0.1, 0.05 ([R 10.3]).
- **(d) `pair_primary_templates`** per pair group (found in [T09]): group `double_take_vs_bounce` `count`, `nonresponse_vs_falsified_dispense` `resp`, `refusal_vs_robot_missed` `sched`, `bounce_vs_forged_dispense` `count` or `resp` ([R 4.1]).
- **(e) The switches**: `diagnostics_profile` (B3), `grouped_variant` (B12), the `family` and `cell_scope` dimensions (not implemented), `twins: separate`.
- **(f) The configuration values T02 step 3 assigns to its own worker** under E9, from the registry, manifest and train / calibration splits: split fractions, `alpha`, `alpha_grid`, `tolerance_ms` (at least the largest verdict-latency bound plus the forecast horizon), `time_reference`, monitor step and reorder delay (multiple of the step), `n_bootstrap`, `ci_level`, `ece_bins`, `timing_tail_ms`, forecaster, B2 parameters, `B5-bonferroni.n_tests`.
- **(g) Non-numeric gates that block reportable comparisons** (from [T02] notes): the B5 variant D2 (B5 as implemented is nearly vacuous: only RESP is predicted), the ADR-063 blind spot of the point evaluator for INT/SYS, ADR-061 history asymmetry, midnight clipping, the B4 reported unit, B2 per-signal forest. They are decisions, not values.

**Concrete example.** (a) S2 (C): with `supervised` true and `deadline_ms` set, a short cuff dropout reads `liveliness_ok` and `qos_deadline_missed` D and P(`ble_dropout`) = 0.967 (P(C1) 0.003); with both asserted 0.996; with both undeclared (`None`, factor 1) 0.989 (P(C1) 0.001). (b) Illustration: a delivery ratio of 0.8 is asserted against a floor of 0.9 (the fixture test value) and denied against a floor of 0.75 (an arbitrary comparison value); the rule asserts below the floor. The same alert changes reading class with a registry value that is not yet set.

**Who/what would decide it in a real deployment.** (a) the device profile of the real devices (WS07-T03, hardware zones off limits); (b) the registry, a human and clinician-engineering review (WS01-T03, WS00-T07); (c), (d), (e) the experiment designer (gab); (f) per E9 the T02 worker, with gab's confirmation; (g) gab.

**Candidate values and what they change.** Candidate values exist only for (c) ([R 10.3]: alpha 0.2 / 0.1 / 0.05 give marginal coverage 84.9 / 90.8 / 95.7% and mean size 2.53 / 2.93 / 5.56; Mondrian 86.4 / 93.1 / 97.3% at 2.81 / 3.39 / 5.77); the test registry of the fixtures holds labelled TEST values only. For (a), (b) not measured.

**What this value does not decide / known failure modes.** (a) is a modelling statement about the benchmark devices that the manifest does not contain; a wrong declaration changes which cells are live. (b) values in the registry file must carry provenance (`reviewed_by`), and an unsourced number cannot be invented.

**Who else reads it / consequences.** (a), (b): the extractor and `ours-hier`, `ours`, `ours-A4`; (c): the set metrics; all feed `metrics.json` and are recorded.

**Options for gab.**
(a) declare the capabilities of the simulated devices explicitly in `experiments/main.yaml` with a header rationale derived from what the generator emits (it numbers messages and emits `NODE_STATE` reports but has no lease; each capability to be checked against the generator before it is declared).
(b) fill the nine registry names as design choices with `reviewed_by: null` and the "illustrative, unverified" label, or leave the run non-headline.
(c) `set_alpha` 0.1, `set_alphas` [0.2, 0.1, 0.05], `set_mode` marginal with Mondrian reported next to it.

**Suggested default (assistant's opinion).** (a) as stated; (b) cannot be defaulted by the assistant: it needs gab and the clinician-engineering review; (c) as stated, because the three-point grid is the one the research used.

**Questions to put to the expert.**
1. Is it acceptable to declare the benchmark devices unsupervised and event-driven in the capability profile, given that the real bridge node will be supervised?
2. Which of the nine missing registry values would you derive from device standards and which would you leave as a labelled sweep?

---

# Part C. One-page summary

"Suggested default" is the repository assistant's opinion. "Blocking" = a headline run (`headline: true`) or the benchmark build is refused without it.

| # | name | kind | candidate range (source) | suggested default (opinion) | depends on | urgency for the headline run |
|---|---|---|---|---|---|---|
| 1 | `eps` | probability parameter | 0.001, 0.01, 0.05, 0.1 ([Y], [R 6.1]) | 0.01 | `qc`, `tau`, `rep_nat` floor | blocking |
| 2 | `qc` | probability parameter (31 cells + modes) | 0.25, 0.5, 0.75 | 0.5; LC fields `None` via capabilities | `eps`, B11 to B13, `grouped_variant`, B17(a) | blocking |
| 3 | `q_stale` | probability parameter | 0.25, 0.5, 0.75 | not needed if profile `without_diagnostics`; else 0.5 | driver rows (B14c), profile | only with the driver profile |
| 4 | `rep_nat` | probability parameter (30 cells) | 0.0098, 0.0197, 0.0393; analytic 0.0021 to 0.0980 by resolution | 0.0197 | `eps` floor, cuff resolution of the build | blocking if cuff templates are read |
| 5 | `delta` | share | 0, 0.1, 0.25 | 0 (generator value), sweep | COLOC `qc` (B11a); not under A4 | blocking (`resp` reads it) |
| 6 | `dispense_bounce_interval_ms` | ms threshold | 1 000, 10 000, 30 000, 60 000, 180 000 | 10 000 | `double_take_gap_ms`, bounce magnitude, content sensing | blocking |
| 7 | `tau` | threshold | 0.5, 0.67, 0.8, 0.9, 0.95, 0.99 | 0.8 + curve | class prior, `eps` | blocking |
| 8 | `cumulative_level` | level | 0.8, 0.9, 0.95 | 0.9 (fallback only) | `set_alpha` | blocking (required key) |
| 9 | `class_priors` | design name | uniform, c1_heavy, c2_heavy, c3_rare, c3_heavy | uniform | `tau`, `pi_designs` | blocking |
| 10 | `pi_designs` | design name | uniform, quiet_rare, quiet_common | uniform | class priors | blocking |
| 11 | nine cells of gab (COLOC 3, D5 2, IDCHECK 1, LATE 1, PULSE 2) | structural decision | `qc` grid | shared `qc`; D5 by capability; IDCHECK dead | `qc`, `delta`, capabilities | decision on form, no extra value |
| 12 | modes of grouped cells | structural decision | reference / fully independent | reference + independent sweep; decide `message_drop` mode | `qc` | switch; decide before the headline |
| 13 | device-specification cells (BOUND 3, DEGRADE 1, LC 9, SEQ 6, SQI 1, TARGET 1) | structural decision | `qc` grid | `qc`; unsupervised devices | `qc`, B17(a), registry | no extra value |
| 14 | 48 generator rows | design / literature values | placeholders: 14:00, 5 s, 2 min, 10 min, 60 s, 500 ms, 1 / 4 / 12 h, x0.5 / 1 / 2 | design choices for the 42 that matter | upstream of everything | blocking the benchmark build |
| 15 | `c1_footprint_tail_ms` (+ reason), `loose_after_ms` | evaluation conventions | 0 / 1 / 2 / 3 days; 0 / 1 h / 24 h | 172 800 000 ms; 86 400 000 ms | tolerance, margin, labelling | blocking |
| 16 | benchmark size D, class rates, pairs | design | 200 x 7, 0.3 / 0.3 / 0.2, 38 pairs; alternatives n 400 to 1 200, rates 0.6 to 1.2 | keep, enlarge pairs | minimum alpha, calibration | provisional, before the build |
| 17 | capability profile, 9 registry names, `set_alpha(s)`, `set_mode`, pair templates, T02 step-3 values | configuration | alpha 0.2 / 0.1 / 0.05 | `set_alpha` 0.1, marginal + Mondrian | everything | blocking (registry names need a human) |

Counts: 79 awaiting rows in the likelihood file (67 cells, 8 parameters, 2 designs, 2 grouped), 48 in the generator (4 + 2 + 2 + 21 + 17 + 2); B15 to B17 add run-level items (tail, its reason, margin, `loose_after_ms`, the capability profile, nine registry names, the set options, the pair templates and the step-3 values of T02).

---

# Part D. Dependencies, order, and what the expert must not do

## D.1 Interactions between values

- **`eps` with `tau`.** `eps` fixes how much one asserted reading is worth, `tau` how much posterior is needed to name a cause: S2 flips from kappa C2 to UNDETERMINED between eps 0.05 and 0.1 at tau 0.8 (B1). Choose them together and report the curve.
- **`eps` with `rep_nat`.** The cell is `max(rep_nat, eps)`: at eps 0.01 the lowest grid value 0.0098 is silently raised to 0.01 (B4); at eps 0.05 all three grid values collapse to 0.05.
- **`qc` with the grouped cells and the capabilities.** The modes of the pair use `qc` and `1-qc`; the LC and SEQ cells are only read if the capability exists; with the capability absent the field is `None` and `qc` plays no role (B2, B12, B13, B17(a)).
- **Class priors with `tau` and with `pi_designs`.** Under `c1_heavy` S1 crosses 0.8, `range` with nothing raised does not (B9); the pi design moves mass among quiet subtypes inside a class and shifts which class leads (B10).
- **`rep_nat` with the cuff resolution.** The resolution of the cuff in the build (1 mmHg) fixes `rep_nat`; a different resolution is a different benchmark (B4, B14).
- **`delta` with the COLOC cells.** The same witness reading is C3 0.92 at delta 0 and mostly C1 at 0.25; the COLOC `qc` moves the C3 side (B5, B11a).
- **`T_b` with `double_take_gap_ms`, the bounce magnitude and content sensing.** The 180 s collapse is a consequence of a 2-min placeholder gap (B6, B14).
- **`q_stale` with the driver rows and the dropout durations.** A lease above 180 s caps `q_stale` at the share of dropouts longer than the lease (B3, B14c).
- **`c1_footprint_tail_ms`, `footprint_margin_ms`, `tolerance_ms`.** The margin defaults to the tolerance (B15, B17f).
- **`loose_after_ms` with the labelling.** It determines the truth of every alert, hence the log score, the calibration of the sets and the equal-coverage block; both labellings are printed (B15).
- **Benchmark size with `set_alpha`, `set_mode` and the guard on the minimum alpha.** Mondrian cells can have 40 to 60 alerts at n = 200 (B16).
- **Generator rows with everything.** They define the data; a rebuild invalidates all runs (B14, B16).

## D.2 Suggested order of decisions (all before the first test-split run, rule E9)

1. Benchmark size and class rates (B16), then the 48 generator rows (B14), and the device profile (`diagnostics_profile`, content sensing, authentication, cuff resolution) of `default.yaml`.
2. The capability profile of the benchmark devices (B17a) and the registry names (B17b: a human task).
3. The model parameters in this order: `eps`, `qc` (with the structural decisions B11 to B13), `rep_nat`, `delta`, `T_b`, `q_stale` (if the driver profile is used).
4. The designs `class_priors` and `pi_designs`.
5. Output operating points: `tau`, `cumulative_level`, `set_alpha`, `set_alphas`, `set_mode`.
6. Evaluation conventions: `c1_footprint_tail_ms` with its reason, `footprint_margin_ms`, `loose_after_ms`, `pair_primary_templates`.
7. Write every value with its rationale in the header comment of `experiments/main.yaml`, commit, then run; the sensitivity sweeps (one run per setting, grid of [M]) follow and are reported next to the headline.

## D.3 What the expert must NOT do

- Do not invent clinical, physiological, device or probability values, and do not present a number from memory as a repository fact. If no defensible basis exists, say so and propose a labelled sweep.
- Do not cite a reference that is not in the verified bibliography of the project (unverified references carry a bib flag and cannot be cited); a literature suggestion is a pointer for gab to verify, never a citation.
- Do not claim or imply clinical validation: the work is technical and pre-clinical, with no real patients.
- Do not write "distribution-free coverage", "ensures", "intrinsic explainability" or "orthogonal" without the qualification of analisi 4.8 (the conformal statement is marginal, approximate for correlated alerts, benchmark-specific; see ADR-074 amendment 5).
- Do not recommend setting a prior, a cell or a threshold from the benchmark's own injection rates or from results on the test split (circularity, ADR-074 decision 2 and rule E9); a use of benchmark frequencies is allowed only as a labelled diagnostic.
- Do not propose a change of a frozen contract signature or of the formalization without an ADR; the cell and parameter names of `configs/attribution_likelihood.yaml` are the interface.
- Do not read the examples of this brief as results: they were computed with the fixture registry at one reference point; the research tables are from a prototype (class-level, unrounded generator, placeholder rows) and give directions, not final numbers.
- Do not touch or ask for changes in the paper, the thesis student's zones (`hardware/`, `ros2/ralmon_witness/`) or the hardware.

## D.4 What gab would like back

For each of B1 to B17: a recommended headline value or "sweep only", the sweep set, a two-sentence justification that uses only the evidence in this brief or an explicitly named external source for gab to verify, the main risk, a confidence level, and which other entry the answer depends on. Flag any entry where this brief's reading of the repository seems wrong; the cited locations allow a check.

## D.5 Limits of this brief

The examples (S1 to S13) use the fixture registry thresholds and the reference point; the research numbers [R] are from the prototype of 2026-10-11 and the subtype follow-ups on a placeholder-filled generator and a single seed; the benchmark-size numbers [RB] are dated 2026-10-10 on an older commit and are provisional; the real registry still lacks nine names (B17b); the count of cells outside benchmark v1 (28 of 67) is computed from the tables of [Y]; no value in this document has been confirmed by gab or checked against the literature.
