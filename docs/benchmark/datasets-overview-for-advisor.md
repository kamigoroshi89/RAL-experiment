# Open datasets for the semi-synthetic benchmark: overview for discussion

Prepared 2026-10-06 for the project meeting. Project: extension of "Clinical Pathways as Safety Specifications for Physical AI in Hospital Wards" into an IEEE RA-L submission. Validation is technical and pre-clinical: no real patients, no clinical claims.

All facts below were read from the files in `data/raw/` and from the PhysioNet and VitalDB dataset pages on 2026-10-06. Nothing is recalled from memory. They are **not yet verified by a human** in the sense of the plan (`docs/benchmark/public-sources.md`, section "Verification status"): licence and mapping rows still need a `verified_by` entry.

## 1. Why we need external data at all

The benchmark is generated, not recorded (`docs/plan/workstreams/WS04-benchmark/README.md`). A virtual patient gets a latent blood-pressure trace, an adherence process, a drug response, and then a measurement process that turns the latent day into the observed day the monitors see. Faults (C2) and attacks (C3) are injected on the observed side. Ground truth is computed on the latent trace, and monitors never read it.

Real data is used for exactly two things:

1. **Realism of the observed signals that are not pressure**: heart rate, SpO2, and real ECG noise for the C2 fault `ecg_noise`.
2. **Clinical priors** (drug response, inter-patient variability, thresholds): this needs MIMIC-IV, which is credentialed and **not available yet**.

No public dataset contains smart-dispenser data, so adherence stays a declared assumption.

## 2. What is downloaded

All under `data/raw/`, gitignored, never committed, never redistributed. Downloaded 2026-10-05.

| Dataset | Version | Licence (as stated on the dataset page) | Access | Size on disk | Integrity check |
|---|---|---|---|---|---|
| MIT-BIH Noise Stress Test (NSTDB) | 1.0.0 | Open Data Commons Attribution 1.0 | open | 68 MB | upstream `SHA256SUMS.txt`, 97 entries, all pass |
| BIDMC PPG and Respiration | 1.0.0 | Open Data Commons Attribution 1.0 | open | 209 MB | upstream `SHA256SUMS.txt`, 483 entries, all pass |
| PhysioNet/CinC Challenge 2015 (training set) | 1.0.0 | Open Data Commons Attribution 1.0 | open | 741 MB (ZIP plus extracted copy) | upstream checksums of `training/` pass; ZIP and licence file checksummed locally |
| VitalDB (**subset: 30 of 6,388 cases** plus metadata files) | 1.0.0 on PhysioNet | **see section 8, item 1** | open | 585 MB | 36 entries (30 cases, licence, 5 metadata files) all pass |

Not downloaded: MIT-BIH Arrhythmia Database (not needed, see NSTDB), and the credentialed datasets MIMIC-IV, MIMIC-IV-ED and eICU-CRD (see section 5).

## 3. What each dataset contains, and whether we can use it

The generator reads three kinds of segment (`src/ralmon/benchmark/segments.py`): `hr_clean`, `spo2_clean`, and `hr_error_ecg_noise` (heart-rate error caused by ECG noise, for the C2 fault).

### 3.1 MIT-BIH Noise Stress Test: use, for the C2 fault `ecg_noise`

| Parameter | Value |
|---|---|
| Records | 15: 12 ECG with added noise (`118e*`, `119e*`) and 3 noise-only records |
| Signals | ECG leads MLII and V1 (ECG records); two noise channels (noise records) |
| Sampling | 360 Hz; 30 min per record (1806 s) |
| Noise-only records | `bw` baseline wander, `ma` muscle artefact, `em` electrode motion |
| Noise level (SNR) | 24, 18, 12, 6, 0, -6 dB, one record per level and subject |
| Noise schedule | starts after the first 5 min; alternates 2 min noisy and 2 min clean |
| Noise source in the mixed records | `em` only |
| Reference beats | `.atr` annotations copied from the clean originals, so true beats are known even where the trace is unreadable |
| Subjects | 2 (records 118 and 119 of the MIT-BIH Arrhythmia Database) |

**Why use it.** The error of a QRS detector's heart rate against the reference annotations is a real-noise error trace, with six intensity levels and a natural intermittent pattern. This covers the requirement of at least three fault magnitudes (WS04-T07). The plan's proposal to add the MIT-BIH Arrhythmia Database is not needed for this.

**Limits.** Only two subjects. Mixed records contain `em` noise only; `bw` and `ma` would have to be added by us. Ambulatory noise, not ward noise. A QRS detector must be chosen and named in the extraction note.

### 3.2 BIDMC PPG and Respiration: use as secondary source for heart rate and SpO2, and for pulse-rate error

| Parameter | Value |
|---|---|
| Records | 53 ICU patients, 8 min each (about 7 h in total) |
| Numerics, 1 Hz | HR (from ECG), PULSE (from plethysmography), RESP, SpO2 |
| Waveforms, 125 Hz | RESP, PLETH, II in all 53; V (49), AVR (47), CVP (10), ABP (8), I, MCL, ART, III |
| Other | manual breath annotations; age, sex, unit; source ids in MIMIC-II |
| Measured values | HR p5/p50/p95 = 67/89/115 bpm; SpO2 = 92/98/100 %; 132 of 25,493 numeric rows missing |
| Patients | age 19 to 90+ (one missing); 32 F, 20 M, 1 unspecified |

**Why use it.** Real HR and SpO2 at the sampling period the generator wants. HR and PULSE are recorded at the same instants, as our `hr_ecg` and `hr_pulse`, so their difference gives an empirical estimate of the pulse-rate error, which is currently an empty parameter.

**Limits.** About 7 h in total against 1,400 patient-days: segments would have to be stitched, and every stitch is a discontinuity that the validation report must disclose (`join_count`). ICU patients are sicker than ward patients. The pulse-rate error value would be a proposal for human approval (ADR-020).

### 3.3 VitalDB: use for heart rate and SpO2; optionally for the cuff error; not for pharmacology

The full dataset has 6,388 surgical cases and 196 tracks. We hold 30 cases.

| Parameter | Value |
|---|---|
| Monitor numerics (`Solar8000`, 44) | HR, PLETH_HR, PLETH_SPO2, NIBP_SBP/DBP/MBP (cuff), ART_SBP/DBP/MBP (invasive), CVP, temperature, ETCO2, respiratory rate, ST levels, ventilator values |
| Waveforms (`SNUADC`) | ART, CVP, ECG_II, ECG_V5, FEM, PLETH, all at 500 Hz |
| Other devices | anaesthesia machine (37 tracks), infusion pumps (51: nitroglycerin, nitroprusside, diltiazem, vasopressors, propofol, remifentanil, others), depth of anaesthesia (8), cerebral oximetry (2), cardiac output (4 devices), fluid warmer (7) |
| Clinical table | 6,388 cases, 74 columns: age, sex, BMI, ASA class, department, `preop_htn`, preoperative labs, intraoperative totals |
| Whole dataset | age p5/p50/p95 = 30/59/78 years; **1,965 cases with `preop_htn` = 1**; departments: general surgery 4,930, thoracic 1,111, gynaecology 230, urology 117 |
| Our 30 cases | duration median 3.5 h (0.8 to 8.7 h); HR, SpO2 and ECG in 30/30; cuff pressure in 26; invasive pressure in 18; **both cuff and invasive in 14** |
| Cuff cadence in our cases | median 17.5 distinct cuff values per case; about one new value every 2.5 min (our estimate from value changes) |

**Why use it.**
- *HR and SpO2*: segments last hours, so far fewer joins than BIDMC. Thousands of cases are available, and selection can be restricted to hypertensive patients.
- *Cuff error*: cuff-minus-invasive differences in the 14 cases that have both give an empirical estimate for the empty parameter `cuff_error_sd`. Caution: the invasive line has its own error and the patients are anaesthetised.

**Why not for pharmacology.** The drugs are intravenous and intraoperative. There are no oral antihypertensive doses, and nitroglycerin appears in only 1 of our 30 cases.

**Limits.** Anaesthetised and ventilated patients: HR and SpO2 are more stable and shifted compared with a ward. This must be stated as a limitation.

### 3.4 PhysioNet/CinC Challenge 2015: use only as an external reference for alarm load

| Parameter | Value |
|---|---|
| Records | 750 training records, 250 Hz, 300 to 330 s around one alarm |
| Signals | II (728), V (684), PLETH (627), ABP (343), RESP (278), a few others |
| Labels | 294 true and 456 false alarms (61% false) |
| By alarm type (true / false) | asystole 22/100; bradycardia 46/43; tachycardia 131/9; ventricular flutter or fibrillation 6/52; ventricular tachycardia 89/252 |

**Why use it.** A real reference for how often commercial bedside alarms are false, to frame alarm fatigue (reviewer finding R3-W6, honest-reporting rule H9).

**Limits.** Records are cut around alarms, not continuous monitoring, so no alerts-per-patient-day figure can come out of it, and the false-alarm share reflects the challenge's selection. Their arrhythmia alarms are a different thing from our care-plan alerts. It supplies no segments to the benchmark.

## 4. Summary of use

| Need of the generator | Source | Status |
|---|---|---|
| `hr_error_ecg_noise` (C2 `ecg_noise`) | NSTDB | usable now |
| `hr_clean`, `spo2_clean` | VitalDB (preferably hypertensive cases), BIDMC as secondary | usable now |
| Pulse-rate error | BIDMC | usable now, value needs approval |
| `cuff_error_sd` | VitalDB, optional | usable now, value needs approval |
| Alarm-load reference | CinC 2015 | usable now, comparison only |
| Drug response (PK/PD), inter-patient variability, baselines, response window | MIMIC-IV | **blocked: no credentialed access** |
| Dispenser analogue (`pyxis` table) | MIMIC-IV-ED | blocked, same reason |
| Real distribution shift for ablation A6 | eICU-CRD | blocked, same reason; A6 stays synthetic-only |
| Adherence | none | declared assumption |
| Clinical content of the pathway template (bands, thresholds, windows, drug) | no dataset: guideline and drug label, anchored by a clinician | **blocked: needs the clinician review (WS00-T07)**, see section 7 |
| Care plans of the virtual patients | generated by the builder from the template | synthetic by construction, see section 7 |

## 5. What the public data does not give us

Every clinical, physiological and device parameter of the generator is still unfilled: all 17 rows of `configs/priors/literature_hypertension.yaml` are `awaiting_human_value`, and 17 names of the clinical registry are `unset`. The plan forbids an agent to choose such values (ADR-020), so any number derived from these datasets is a proposal with a documented extraction rule, to be approved by a human.

Until MIMIC access exists, all results are labelled "semi-synthetic, literature priors" (ADR-005, rule H6). The credentialed datasets also require the CITI course and a data use agreement. These may forbid sending row-level data to hosted services, in which case only aggregates reach the agents.

## 6. Where the code stands

- WS04-T06 (measurement process, segment library) is merged. It reads segment files from `data/raw/segments/`, which **does not exist yet**: no segment has been extracted. Without it the benchmark builds with `allow_no_segments=True` and no HR or SpO2 samples.
- WS04-T07 (C2 injection) is in progress on a separate branch.
- The human artefacts WS00-T04 (credentialing record) and WS00-T09 (dataset licences, versions, checksums) are marked done but their files do not exist. This document and the checksum results above cover part of the T09 content; it still needs the human confirmation.

## 7. Clinical pathway and care plans: dataset or generation?

**There is no clinical-pathway dataset to download, and the benchmark does not need one.** The pathway is the input of the system, the specification to be monitored, not data to learn from. The care plans of the virtual patients can be generated synthetically. The clinical content of the template can neither be invented nor derived from a dataset.

### 7.1 The two levels

The project distinguishes two levels (glossary in `CLAUDE.md`):

- **Pathway template** (institutional level, for hypertension): the 7 STL templates RANGE, SCHED, HOLD, COUNT, RESP, SYS, INT (`docs/formal/02-templates.md`, section 3.1). Their parameters live in the clinical registry: pressure band, hold threshold, response window Δ1/Δ2, maximum number of doses, and so on.
- **Patient care plan** (`CarePlan`): the instance of the template for one patient, with the template instances and the measurement and dispensing times.

| Level | Where it comes from | Can it be arbitrary? |
|---|---|---|
| Clinical content of the template (bands, thresholds, windows, drug) | guideline and drug label, anchored by a clinician (WS00-T03 and T07, ADR-020) | No. No agent chooses values or drugs, and no dataset supplies them. |
| Care plans of the 200 virtual patients | the builder (WS04-T11) instantiates them from the template, the registry and the drawn patient | Yes. Synthetic by construction. |
| Ground truth | computed by evaluating the plan's formulas on the latent trace | Nothing has to be annotated by hand. |

### 7.2 Current state and a risk

`configs/benchmark/care_plans.yaml` today holds two doses (07:00 and 21:00) and 5 measurements a day, both with `dist: null` and marked `illustrative_unverified` (taken from the analysis example). The clinical registry `configs/registry/hypertension.yaml` is `unreviewed`.

**Risk:** with this configuration all 200 patients would have the same plan, and the benchmark would test one plan, not generalisation across plans. The registry provides per-patient overrides, but only inside clinician-approved ranges (`docs/formal/03-parameter-registry.md`, section 5), and in version 0.1.0 they are empty. Non-clinical quantities (dose times, number of measurements) can be varied safely as `design_choice` rows. Thresholds can be varied only with approved ranges.

### 7.3 Datasets that help, as statistics

None contains formalised pathways with temporal constraints.

- **MIMIC-IV (eMAR):** the plan names it for antihypertensive administrations (`docs/plan/workstreams/WS04-benchmark/README.md`, table of sources). It would give real dosing times and frequencies to make plan variability realistic. It needs credentials, and the table structure is still to be verified.
- **eICU-CRD:** its page lists "care plan documentation" among the contents, but we have not verified its structure. It can only be inspected after access.
- **FHIR PlanDefinition and CarePlan:** not a dataset but a standard. The plan includes a mapping sketch to our templates (WS01-T07). The analysis (§3.4) calls it a strong and cheap point, because it answers the criticism that the templates do not derive from a standard representation.

### 7.4 The open point for the paper

The draft abstract says the templates cover "[M] of [M′] constraints of [two] clinician-reviewed care pathways" (`docs/source/analisi.md`, abstract draft). Supporting that needs one or two real or public pathway documents, for example a hospital protocol or a guideline. From them the constraints are listed (M′) and the ones the templates express are shown (M). This is a small hand-built corpus, not a dataset. In the plan files we checked (INDEX, the WS01 README, the master plan) no task provides it.

### 7.5 Proposed approach

1. A single hypertension pathway (ADR-001), anchored by the clinician to one drug and one guideline.
2. Patient plans generated with variability in dose times and number of measurements, and with clinical overrides only where approved.
3. One public or hospital pathway document as the basis for the M/M′ count and for the FHIR mapping.

## 8. Decisions and inputs requested

1. **VitalDB licence.** The PhysioNet copy declares CC BY 4.0. The official site's data use agreement declares CC BY-NC-SA 4.0. Which applies to us, and does the non-commercial share-alike clause restrict redistributing derived segments in the open-source release (WS13)?
2. **PhysioNet credentialing for MIMIC-IV, MIMIC-IV-ED and eICU-CRD.** Who holds the account, and has the CITI course been done? It is the only route to real clinical priors and to a real shift test.
3. **Segment extraction rule.** Approve or amend the proposal: NSTDB reference-annotation heart rate versus QRS-detector heart rate for `hr_error_ecg_noise`; VitalDB hypertensive cases for `hr_clean` and `spo2_clean`; BIDMC as a secondary source and for the pulse-rate error. A "clean" criterion and the detector must be named.
4. **Cuff error.** Do we derive `cuff_error_sd` from VitalDB cuff versus invasive pressure, or take it from the device standard (ISO 81060-2 is cited in the prior file, "edition and clause to be confirmed")?
5. **Number of VitalDB cases.** 30 are enough to check the pipeline. How many do we want for the release, given the size of the full set (about 95 GB on PhysioNet)? The VitalDB API allows single cases.
6. **Clinical review.** The clinical registry and the 17 priors need a clinician (WS00-T07) before any result can drop the "unverified" label.
7. **How many pathways.** Are the "[two]" pathways of the abstract two drugs or protocols for hypertension, or two pathologies? In the second case diabetes enters (WS04-T14, optional) and the workload changes.
8. **Care-plan variability.** Approve that dose times and number of measurements vary across patients as `design_choice` rows, keeping the clinical thresholds fixed until the clinician approves ranges for the overrides.
9. **Pathway corpus.** Which document (hospital protocol or public guideline) do we use for the M/M′ count, who provides it, and who extracts the constraints? Also decide whether to entrust the FHIR mapping sketch to WS01-T07.

## 9. Scope reminder

Technical, pre-clinical validation only. No dataset here is used to make a claim about real patients. The open datasets feed the signal-realism of the observed trace. They do not feed the pressure response to treatment.
