# WS04-benchmark: Benchmark generator

## Objective

Build the semi-synthetic benchmark generator of analisi §5.1 (roadmap item 4, 4-6 pw): a released, inspectable generator that produces virtual hypertension patient-days (ADR-001) as two aligned traces, the **latent trace** (noise-free, fault-free, attack-free) and the **observed trace** (what the monitor and every baseline see), with the ground truth defined on the latent side. The benchmark is the evidence base for the technical, pre-clinical validation (analisi §5, ADR-001); it answers reviewer finding R3-W1 (no validation) and the first residual objection of analisi §10 (circular semi-synthetic evaluation). Estimate 32.5 person-days over 14 tasks; T14 is OPTIONAL and last.

### Generation pipeline (fixed order, one function per step)

1. `PriorSource.sample_patient` draws the latent patient (T02). Only `LiteraturePriorSource` exists until T13, because credentialing is not started (ADR-005).
2. Latent blood pressure: baseline, circadian component with nocturnal dip, autoregressive noise (T03).
3. Adherence Markov model produces true DISPENSE and INTAKE events (T05). This is an assumption declared as such: no public smart-dispenser dataset is known (analisi §5.1).
4. C1 injections modify the latent day (T09); PK/PD turns true intakes into a pressure response (T04). The latent day is then complete.
5. Ground truth for C1 is computed by evaluating the φ_CP templates on the latent day (T10).
6. Measurement process builds the fault-free observed stream from the latent day: schedule, robot arrival jitter, cuff error, heart rate and SpO2 from public segments, DISPENSE and witnessed INTAKE (T06).
7. C2 faults (T07) and C3 integrity attacks (T08) are applied to the observed stream; deliberate confounders (T09) pair matched C1, C2 and C3 mechanisms.
8. The builder writes observed files, truth files, care plans and a manifest (T11); the validation report checks the result (T12).

### Ground truth definition (analisi §5.1, contract `#trace-schema` rule 1)

- A true C1 event is a violation of φ_CP evaluated on the **latent** trace. The evaluation reuses the WS05 monitor on an ideal observation of the latent day (T10).
- True C2 and C3 events are the **injected** events, one ground-truth event per realised injection, whether or not any channel could ever detect it (silent cuff bias and the informed attacker stay in the ground truth).
- The monitor and every baseline receive only `ObservedDay`. Observed files and truth files are stored in different directories, so a detector run needs no access to `truth/`.

### Why the evaluation is not tautological (analisi §5.1 last paragraph, §10 objection 1)

The same specification appears on both sides, so the argument must be stated exactly. What the evaluation measures is the loss caused by observation: sparse sampling, cuff error, faults, attacks, missing witness. It does not measure whether φ_CP is clinically right; that is the clinician review of the registry (WS00-T07). The safeguards, each with its owner:

1. Truth on the latent trace, monitor on the corrupted trace, physically separated files (T01, T10, T11). Test `test_c1_truth_follows_latent_not_injection_intent`: truth follows latent φ_CP, not the injection log.
2. Perfect observation reproduces the truth and imperfect observation diverges from it in the expected direction (T10 tests `test_perfect_observation_equals_ground_truth_on_c1`, `test_noisy_observation_diverges_from_ground_truth`).
3. An independent reference evaluator of the φ_CP templates, written from the formulas and not from the monitor code, agrees with the labeller (T10 test `test_independent_reference_evaluator_agrees`). It guards against a monitor bug defining its own truth.
4. Baselines B1 and B3 receive the same bands and schedules (WS06-T02, WS06-T04, audit WS06-T07). Alert load on unlabeled real data (T13, WS08-T06). Parameters from priors with provenance and clinician review (T02, T13, WS00-T07). The paper states "technical pre-clinical validation" (WS12). The generator is released so circularity is inspectable (WS13).
5. Silent bias and the informed attacker are in the ground truth even though undetectable (T07, T08): truth is not "what the monitor can see".

### Scale and splits (analisi §5.1)

200 virtual patients x 7 days = 1400 patient-days; every split is by patient (training of the forecaster, calibration, test; `#trace-schema` rule 2); at least 5 seeds; bootstrap intervals over patient-days (WS08). Convention adopted with WS08 README E1: one benchmark version is fixed by one **generation seed** (population, injections, reference split); the at least 5 experiment seeds of WS08 re-draw the patient-level split and the model randomness over that version. T12 additionally checks the validation properties on at least 5 generation seeds. Patients are i.i.d. draws from the prior, so calibration and test patients are exchangeable by construction; distribution shift exists only where a shifted cohort is built explicitly (T11 cohort option, T13).

### Declared assumptions and limitations (quoted by WS12 and the datasheet)

- Adherence is a Markov model of per-dose outcomes (on time, delayed, omitted, double take) declared as an assumption. With the contract's parameters the transition rows are identical (memoryless); persistence needs a contract change (see issue I3).
- Inter-patient parameters are drawn independently unless a source states a correlation; the cuff error is Gaussian with the bias and SD of the `DeviceErrorModel`.
- Heart rate and SpO2 come from clean public segments and are not coupled to the pressure model or to the drug (no baroreflex).
- PK/PD is one-compartment oral absorption plus Emax on a unit-dose normalised concentration; the Pulse Physiology Engine is evaluated in T04 and adopted only if its substance library holds the anchored drug.
- Blood pressure between scheduled measurements does not violate φ_CP in the default ground-truth mode (`scheduled`); a `dense` mode is available and reported as a sensitivity (T10).
- Results before T13 are labelled "literature priors" (ADR-005). Every value without `verified_by` is reported as unverified (ADR-020).

## Inputs

### Contracts and upstream documents

- Contracts: `02-interfaces.md#trace-schema` and `#priorsource` (owned here); `#parameter-registry`, `#evidencevector`, `#monitor`, `#experiment-config-and-outputs` (read). Also read `#time-and-units`, `#signals`, `#template` (for `CarePlan`) and `#verdict`, which the INDEX does not list for this workstream.
- ADRs: ADR-001, 002, 004, 005, 016, 017, 019, 020.
- Upstream documents: `configs/registry/hypertension.yaml` and its schema (WS01-T03; working names `bp_hold_threshold`, `hold_lookback`, `delta1`, `delta2`, `delta_resp`, `sched_window`, `cuff_inflation_min`, `cuff_error_sd`, `scale_range`), the template document `docs/formal/02-templates.md` with its plan feasibility checks (WS01-T02), the shared fixture registry F0 (copied to `tests/fixtures/spec/` by WS05-T03); `docs/models/fault-model.md` (WS02-T01, C2 subtype vocabulary and injection parameter sheet); `docs/models/threat-model.md` (WS02-T02, attacker capabilities and levels); `docs/models/evidence-channels.md` (WS02-T03, payload conventions and gap G-1, read when it exists); the monitor of WS05-T04; `docs/plan/workstreams/WS00-admin/outputs/WS00-T04.md` (`## Open-access datasets`, `## Data handling constraints`, `access_status:` lines).
- `docs/source/analisi.md` §5.1 in full, §4.5, §4.9 (5), §3.6, §10 (1); `docs/source/review.md` R3-W1, R3-W3, R3-W4.

### Public data sources (analisi §5.1; all schema, licence and access facts are to be verified, none is assumed)

| Source | Role in the benchmark | Access as stated in analisi | To verify | First used |
|---|---|---|---|---|
| MIMIC-IV (hosp, ICU) | antihypertensive administration to pressure response pairs; inter-patient variability; baseline distributions | credentialed (CITI course, data use agreement), days to weeks | schema, licence, eMAR and intermittent non-invasive pressure tables | T13 |
| MIMIC-IV-ED | periodic vital signs and automated-cabinet dispensing: analogue of the smart dispenser; unlabeled episodes | credentialed | schema (analisi marks it unverified) | T13 |
| eICU-CRD | second cohort for the distribution-shift test; medications, periodic and aperiodic pressure | credentialed | schema, licence | T13 |
| VitalDB | high-resolution intraoperative signals: noise and artefact modelling, clean heart rate and SpO2 segments | open access | licence, signal names, sampling rates | T06 |
| BIDMC PPG and Respiration | PPG-derived signals, heart rate reference | open access (analisi marks it unverified) | licence, content | T06 |
| MIT-BIH Arrhythmia Database and MIT-BIH Noise Stress Test Database | real electrode and motion noise for realistic C2 faults on the ECG path | open access | licence, record layout | T06, T07 |
| PhysioNet/CinC Challenge 2015 | labelled false alarms: sanity check of alert load | open access | licence, label definitions | T12 |

No dataset listed here is a smart-dispenser dataset; adherence stays a declared assumption. The record of licence and redistribution terms is the human artefact of WS00-T04; T06 records only the technical mapping in `docs/benchmark/public-sources.md`.

### Parameter policy (binding for every task; ADR-005, ADR-020)

Three classes of numbers, and only one class may be chosen by an agent.

1. **Clinical, physiological and device parameters** (everything that `PriorSource` returns, plus circadian phase, heart-rate and SpO2 levels, pulse-rate error, nominal cuff inflation duration): no agent may choose or recall a value. Each lives in `configs/priors/literature_hypertension.yaml` (or `configs/benchmark/generator_design.yaml` when the contract has no field for it) with `value`, `unit`, `source_ref`, `source_type`, `verified_by`, `status`. A row without a supplied value has `status: awaiting_human_value` and `value: null`. The drug behind the PK/PD parameters is the one anchored in the registry (WS01-T03, WS00-T07); no agent names a drug.
2. **Generator design parameters** (grid step, double-take gap, injection onsets, durations and magnitude grids, event rates, split fractions): an agent may propose a value only with `source_type: design_choice`, a one-line rationale, and expressed relative to a registry quantity or a device SD wherever it has clinical meaning. They appear in the same provenance table for human confirmation.
3. **Test fixture numbers**: arithmetic values chosen so that expected results can be hand-computed. They live only under `tests/`, are marked "fixture-only", never enter a `PriorSource` used by the builder without an explicit flag, and are never described as clinical.

### Human inputs the plan cannot produce (the INDEX has no task for H1 and H2; see issue I7)

- **H1** Fill and verify the provenance table `docs/benchmark/parameter-provenance.md` (generated from the YAML): supply `value` and `source_ref` for every `awaiting_human_value` row, either in the YAML or as a short extract with the citation under `docs/benchmark/source-extracts/` for an agent to transcribe, then set `verified_by`. Artefact: the YAML rows with `status: filled` and `verified_by` set.
- **H2** Download the open-access datasets of the table above into `data/raw/<dataset>/` (never committed) and provide or approve the segment extraction of T06. Artefact: `data/raw/segments/index.json` in the format defined by T06.
- **H3** Confirm or overturn the `design_choice` rows and the proposed ADRs written by tasks of this workstream.
- **H4** Clinician anchoring of the PK/PD drug through the registry (WS00-T07).
- **H5** PhysioNet access (WS00-T04). The data use agreement may forbid sending row-level data to hosted services; then the estimation and real-episode scripts of T13 are run by the credentialed human and only aggregates come back.

Until H1 is complete every benchmark built by T11 is `provisional`: the manifest carries `n_unfilled` and `n_unverified`, and builds from fixture priors carry `fixture_only: true`.

## Outputs

### Repository artefacts

| Path | Task |
|---|---|
| `src/ralmon/benchmark/trace.py` (schema, serialisation, manifest); `src/ralmon/signals/trace_types.py` only if WS05-T02 has not yet exported `Sample`, `Event`, `EventKind` | T01 |
| `src/ralmon/benchmark/priors.py`, `configs/priors/literature_hypertension.yaml`, `docs/benchmark/parameter-provenance.md` (generated table) | T02 |
| `src/ralmon/benchmark/rng.py`, `latent.py`, `configs/benchmark/generator_design.yaml` | T03 |
| `src/ralmon/benchmark/pkpd.py`, `docs/benchmark/pulse-evaluation.md` | T04 |
| `src/ralmon/benchmark/schedule.py`, `adherence.py`, `configs/benchmark/care_plans.yaml` | T05 |
| `src/ralmon/benchmark/measurement.py`, `segments.py`, `vocab.py`, `docs/benchmark/public-sources.md` | T06 |
| `src/ralmon/benchmark/injection.py`, `inject_c2.py`, `configs/benchmark/injections.yaml` | T07 |
| `src/ralmon/benchmark/inject_c3.py` | T08 |
| `src/ralmon/benchmark/inject_c1.py`, `confounders.py`, `latent_day.py` | T09 |
| `src/ralmon/benchmark/labelling.py`, `tests/benchmark/reference_phi_cp.py`, `docs/benchmark/ground-truth.md` | T10 |
| `src/ralmon/benchmark/builder.py` (also the reader), `__main__.py`, `configs/benchmark/default.yaml` | T11 |
| `src/ralmon/benchmark/validation.py`, `docs/benchmark/validation-report.md` | T12 |
| `src/ralmon/benchmark/mimic_prior.py`, `estimate_priors.py`, `real_episodes.py`, `docs/benchmark/mimic-schema-verification.md` | T13 |
| `src/ralmon/benchmark/glucose/` | T14 (OPTIONAL) |

Tests live in `tests/benchmark/`, fixtures in `tests/fixtures/benchmark/`. Generated files (`parameter-provenance.md`) are a pure function of the YAML and are regenerated by command in every task that changes a parameter file; they are not counted against a task's six-path limit.

### Subtype vocabulary of `GroundTruthEvent.subtype` (contract: "listed in WS04 README")

Identifiers are those of the WS02 vocabularies, reused verbatim; if WS02-T01 or WS02-T02 renames one, WS02 wins and this list is updated.

- C1 (truth from φ_CP on the latent trace; `injected` is True when a C1 injection record explains the event, False otherwise): `hypertensive_spike` (template `range`), `drug_nonresponse` (`resp`), `hypotension_below_hold` (`hold`), `measurement_refusal` (`sched`), `double_take` (`count`, from the adherence model), `dose_omission` (`count` day-end obligation, from the adherence model; WS02-T05 has no row for it, see issue I8), `spontaneous_<template id>` for violations that no record explains (for example `spontaneous_range`).
- C2 (injected; from analisi §5.1 (3) and §4.5 row 3): `ble_dropout`, `stuck_at`, `cuff_silent_bias`, `ecg_noise`, `nav_delay`, `manipulation_failure`, `dispenser_bounce`, `cuff_detached`. Not injected in benchmark v1: `process_kill`, `message_drop`, `localisation_noise`, `impossible_goal`, `battery_depleted`, `uncommanded_lifecycle_transition` (WS07-T05, simulation), and the time faults `link_delay`, `out_of_order`, `clock_skew`.
- C3 (injected): `replay`, `injection_naive`, `injection_informed`, `dispense_forgery`, `presence_spoof`. The attacker level of the first, fourth and fifth is recorded in the injection log as defined by WS02-T02.

### Confounder groups (`GroundTruthEvent.confounder_group`, used to score abstention, analisi §5.1 item 4)

`double_take_vs_bounce` (C1 double take against C2 dispenser bounce), `nonresponse_vs_falsified_dispense` (C1 drug non-response against C3 dispense forgery), and `refusal_vs_robot_missed` (C1 measurement refusal against C2 robot no-show; added by this plan from R3-W4, not one of the two named in analisi §5.1).

### Benchmark directory layout (recorded as an ADR by T01)

```
<benchmark_dir>/manifest.json
<benchmark_dir>/days/<patient_id>/<day_index>.json     ObservedDay only
<benchmark_dir>/truth/<patient_id>/<day_index>.json    LatentDay, ground_truth, injection_log, behaviour_log
<benchmark_dir>/plans/<care_plan_id>.json              CarePlan
```

`injection_log` (magnitude, level, duration per injection) and `behaviour_log` (per-dose adherence outcome) are sidecars because `GroundTruthEvent` has no such fields; WS08 reads them for per-magnitude and per-level results.

## Dependencies

### Other workstreams

- Upstream: WS05-T01 (T01); WS01-T03 (T02, registry schema); WS02-T01 (T07); WS02-T02 (T08); WS05-T04 (T10, monitor); WS00-T04 (T13, credentialing).
- Soft inputs: WS02-T03 payload conventions and gap G-1 (T05, T06, T07, T08, T09); WS00-T04 open-access records (T06); robot arrival jitter exported by the WS07 simulation (T06); a clinician-reviewed registry (WS00-T07) before any headline build.
- Downstream: WS06-T01 (trace schema), WS07-T03 (replay of observed days), WS08-T01 (builder, reader, care plans, `end_ms` convention of T10), WS08-T06 (T13), WS11-T02 (benchmark events), WS13-T01 and WS13-T04 (builder CLI, manifest keys, validation report, subtype vocabulary).

### Contract anchors

Owns `02-interfaces.md#trace-schema` and `#priorsource`. Reads `#parameter-registry`, `#evidencevector`, `#monitor`, `#experiment-config-and-outputs`, `#time-and-units`, `#signals`, `#template`, `#verdict`. No task edits a contract; gaps go through an ADR (`01-conventions.md` section 6). WS04 owns two contracts, so T01 and T02 write the proposed ADRs for the gaps below that concern them.

### Issues found (for the plan lead and the contract owners)

- **I1** `01-conventions.md` section 1 says `benchmark` depends only on `signals` and the trace schema, but T10 (monitor), T11 and T12 (registry and `CarePlan` from `spec`) need `monitor` and `spec`. The layering test and ADR of WS05-T01 already allow `benchmark` to import the public API of `signals`, `spec` and `monitor` (package root only); the convention text still needs that amendment. WS04 keeps a stricter internal rule, enforced by a test in T10: only `labelling.py`, `builder.py` and `validation.py` import `spec` or `monitor`.
- **I2** T01 depends only on WS05-T01, but `Sample`, `Event`, `EventKind` are exported by `ralmon.signals`, whose real content WS05-T02 creates; T01 creates `trace_types.py` if WS05-T02 is not done (WS05-T02 step 1 expects this). T06 to T09 also need `SignalId` and `event_to_sample` from WS05-T02: missing INDEX dependency WS04-T06 on WS05-T02.
- **I3** `PatientParams`, `AdherenceParams` and `DeviceErrorModel` lack fields the generator needs: circadian phase, heart-rate and SpO2 levels, pulse-rate error, nominal inflation duration, dose normalisation, adherence persistence, double-take gap. T02 records each as a row in `generator_design.yaml` and proposes an ADR (WS04 owns the contract).
- **I4** WS02-T03 gap G-4 expects WS04-T01 to adopt the payload conventions of `evidence-channels.md`, which does not yet exist when T01 runs. Payload keys are isolated in `vocab.py` (T06) with a conformity test (T07).
- **I5** `GroundTruthEvent` has no magnitude, level or cascade link; they live in the truth-file sidecars. T10 fixes `end_ms` as the obligation deadline for windowed obligations (`resp`, `sched`, day-end `count`) and `None` otherwise, which is the convention WS08 README assumes (assumption 1).
- **I6** T06 needs the robot arrival jitter from the WS07 simulation (analisi §5.1 item 2) and has no WS07 dependency; a file import with a `NoJitter` default is used.
- **I7** No INDEX task owns H1 and H2, and T14 needs a diabetes registry with clinician review that WS01-T03 and WS00-T07 do not cover.
- **I8** WS02-T05 covers five C1 subtypes; `dose_omission` and `spontaneous_*` need a row or a mapping.
- **I9** The public API table of `#package-public-api` lists `generate_benchmark` but no reader; WS08-T01 assumes a loader (T11 exports `open_benchmark` and `BenchmarkReader`).
- **I10** The impulse signals `meas`, `dispense`, `intake` and `sched_tick` exist only as events in the observed trace, because the monitor derives them with `event_to_sample` (WS05-T02) and counters read the event stream; a duplicate sample would be counted twice. `#trace-schema` does not state this rule.

## Acceptance criteria

Run from the repository root once T01 to T12 are `done` (T13 needs WS00-T04, T14 is OPTIONAL).

1. `pytest tests/benchmark -q`, `ruff check src tests` and `mypy src/ralmon` exit 0.
2. Provenance: `python -m ralmon.benchmark.priors --check-table` exits 0; every row of `docs/benchmark/parameter-provenance.md` has a `source_ref` or the status `awaiting_human_value`; the generator contains no numeric parameter literal (test `test_no_parameter_literals_in_generator_modules`, created in T02 and scanning every module of `src/ralmon/benchmark`: a float literal other than 0.0 and 1.0, or an integer literal other than 0, 1, 2 and -1, is allowed only on a line ending with the comment `# algorithmic: <reason>`).
3. Determinism: `pytest tests/benchmark/test_builder.py::test_same_config_and_seed_reproduce_bytes -q` exits 0 (bit-for-bit, `01-conventions.md` section 3).
4. Ground truth and non-circularity: `pytest tests/benchmark/test_ground_truth.py -q` exits 0 and includes the tests named in the section on non-tautology; `docs/benchmark/ground-truth.md` exists and has the headings `## Definition`, `## Non-circularity tests`, `## Residual circularity`.
5. Splits: test `test_split_is_by_patient_no_leak` exits 0; the reference split in the manifest satisfies `#trace-schema` rule 2.
6. Leakage: `python -m ralmon.benchmark validate <dir>` prints the leakage check as PASS; observed files contain no key containing `latent` or `ground_truth`.
7. Scale: the default config declares 200 patients and 7 days (test `test_default_scale_is_200_patients_7_days`).
8. Headline gate (a human-supplied condition, not a task command): the manifest of the headline build has `fixture_only: false`, `n_unfilled: 0`, the number of unverified parameters reported, and `docs/benchmark/validation-report.md` states the prior source.
9. Forbidden tokens: `grep -rnE 'TO''DO|TB''D|lo''rem|\?\?\?' docs/benchmark src/ralmon/benchmark configs/benchmark configs/priors` prints nothing.
10. T13 (after credentialing): `pytest tests/benchmark/test_mimic_priors_and_episodes.py -q` exits 0 and `docs/benchmark/mimic-schema-verification.md` has `verified_by:` filled.

## Source sections

- analisi §5.1 (all of it: public sources, generator items 1 to 4, ground truth, scale, unlabeled real-data run), §5.2 (robot arrival jitter, fault injection), §5.8 (what is indispensable; second pathology optional), §9 items 0.6 and 4 (credentialing, generator), §10 objection 1 and the fourth objection.
- analisi §4.5 (evidence groups, diagnosability matrix rows used to design C2, C3 and confounders), §4.9 item 5 (DISPENSE versus INTAKE), §3.6 (attacker levels), §4.1 and §4.6 (templates and illustrative schedule, labelled illustrative, unverified), §4.7 (physiological bounds).
- `docs/source/review.md`: R3-W1 (no validation), R3-W3 (parameters not anchored in drug or guideline), R3-W4 (taxonomy: double take versus bounce, missed measurement as C1 or C2).

## Tasks

| id | title | owner | status | depends_on |
|---|---|---|---|---|
| WS04-T01 | Trace schema dataclasses, serialisation and manifest | agent | blocked | WS05-T01 |
| WS04-T02 | PriorSource protocol and LiteraturePriorSource with mandatory provenance | agent | blocked | WS04-T01, WS01-T03 |
| WS04-T03 | Latent patient model: baseline pressure, circadian dip, autoregressive noise | agent | blocked | WS04-T02 |
| WS04-T04 | PK/PD response model and onset window derivation; evaluate Pulse Physiology Engine | agent | blocked | WS04-T03 |
| WS04-T05 | Adherence Markov model with DISPENSE and INTAKE events | agent | blocked | WS04-T02 |
| WS04-T06 | Measurement process: schedule, cuff error, HR and SpO2 from public real-noise data | agent | blocked | WS04-T04, WS04-T05, WS05-T02, WS00-T09 |
| WS04-T07 | C2 fault injection | agent | blocked | WS04-T06, WS02-T01, WS02-T03 |
| WS04-T08 | C3 integrity attacks at naive and informed attacker levels | agent | blocked | WS04-T06, WS02-T02, WS02-T03 |
| WS04-T09 | C1 injection and deliberate confounders | agent | blocked | WS04-T07, WS04-T08 |
| WS04-T10 | Latent ground-truth labeller (phi_CP on the latent trace) and non-circularity tests | agent | blocked | WS04-T09, WS05-T04 |
| WS04-T11 | Benchmark builder CLI: splits by patient, manifest, seeds, scale | agent | blocked | WS04-T10, WS04-T15 |
| WS04-T12 | Benchmark validation report and alert-load sanity check | agent | blocked | WS04-T11 |
| WS04-T13 | MimicPriorSource and eICU variant (blocked until credentialing) | agent | blocked | WS04-T02, WS00-T04 |
| WS04-T14 | OPTIONAL: second pathology (diabetes, simglucose) | agent | blocked | WS04-T11 |
| WS04-T15 | Multi-day ground-truth labelling with history (ADR-046, ADR-055 (b)) | agent | blocked | WS04-T10, WS05-T10 |
| WS04-T16 | Cuff faults anchored to readings (durations in readings), stuck_at carry-over, effective k in the truth (ADR-070) | agent | done | WS04-T11, WS04-T15 |
| WS04-T18 | Generator: cuff resolution (rounding), driver diagnostics reports under two device profiles, dispenser interval, ADR-040 conventions (ADR-074) | agent | ready | WS05-T13, WS04-T16 |
