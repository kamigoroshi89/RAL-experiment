# Task index (binding skeleton)

Generated during bootstrap phase F6. Task ids, titles, owners, `depends_on`, `critical_path`, `non_negotiable`, `estimate_pd`, `sources`, `interfaces` and `review_items` in each task file must match this table. The task files add the detailed content. `status` at bootstrap: `ready` when `depends_on` is empty, otherwise `blocked`.

Finding ids (`review_items`) are defined in `04-review-traceability.md`.

## WS00-admin: Admin and human decisions

| id | slug | title | owner | depends_on | crit | nonneg | pd | sources | interfaces | review_items |
|---|---|---|---|---|---|---|---|---|---|---|
| WS00-T01 | cfp-check | Verify CFP: deadlines, page limit, prior-publication policy, commitment letter content | human | - | yes | no | 0.5 | analisi §9 (0.1), §7 | - | - |
| WS00-T02 | scope-decisions | Scope decisions: one pathology, C3 as integrity violations, distributed architecture | human | WS00-T01 | yes | no | 2.5 | analisi §9 (0.2), §3.6, §4.9 | - | R3-W2 R2-W7 |
| WS00-T03 | clinician-collaborator | Recruit a clinician and, if possible, an RV/STL collaborator | human | WS00-T02 | no | no | 1 | analisi §9 (0.3) | - | R3-W3 |
| WS00-T04 | physionet-credentialing | Start PhysioNet credentialing for MIMIC-IV and eICU | human | - | yes | no | 1 | analisi §9 (0.6), §5.1 | #priorsource | - |
| WS00-T05 | tiago-availability | Check real TIAGo or TIAGo Pro availability and ROS 2 simulation packages | human | - | no | no | 1 | analisi §9 (0.7), §5.2 | #ros-2-interfaces | - |
| WS00-T06 | ethics-check | Check ethics rules for lab volunteers and the vignette study | human | WS00-T02 | no | no | 0.5 | analisi §5.3, §5.7 | - | - |
| WS00-T07 | clinician-review-registry | Clinician review of parameter registry, taxonomy and priorities (M1 gate) | human | WS00-T03, WS01-T03, WS01-T04, WS01-T05, WS02-T04 | no | no | 1 | analisi §4.2, §2 R3, §9 (0.3) | #parameter-registry | R3-W3 R3-W4 |
| WS00-T08 | reference-pdfs | Obtain full text of the key reference papers needed by implementers (Lindemann et al. ICCPS 2023 first) | human | - | no | no | 0.25 | analisi §5.4 (B5), §3.2 | - | - |
| WS00-T09 | open-datasets | Download the open datasets into data/raw/ and record their licences (VitalDB, MIT-BIH noise stress test, BIDMC, CinC 2015) | human | - | yes | no | 0.5 | analisi §5.1 | #priorsource | - |
| WS00-T10 | verify-provenance | Verify the literature-prior provenance table produced by WS04-T02 | human | WS04-T02 | no | no | 1 | analisi §5.1, §2 R3 weakness 3 | #priorsource #parameter-registry | R3-W3 |

Total estimate: 9.25 person-days.

## WS01-formalization: Formalization

| id | slug | title | owner | depends_on | crit | nonneg | pd | sources | interfaces | review_items |
|---|---|---|---|---|---|---|---|---|---|---|
| WS01-T01 | signals-sampling | Problem formulation: signals, sampling semantics, time, decomposition | agent | WS00-T02 | yes | yes | 2 | analisi §4.1, §4.9 (2) | #time-and-units #signals | R1-W4 R1-W7 |
| WS01-T02 | template-library | Past-time STL template library with units and robot obligations | agent | WS01-T01 | yes | yes | 3 | analisi §4.1, §4.2, §2 R1 | #template | R1-W1 R1-W3 R1-W5 R1-W8 |
| WS01-T03 | parameter-registry | Parameter registry design, YAML schema and anchoring procedure | agent | WS01-T02 | yes | yes | 2 | analisi §4.1, §4.2, §2 R3 weakness 3 | #parameter-registry | R3-W3 |
| WS01-T04 | normalisation-ranking | Normalised robustness and lexicographic alert ranking | agent | WS01-T02 | yes | yes | 2 | analisi §4.2 | #template | R1-W2 AE-5 |
| WS01-T05 | three-valued-semantics | Three-valued online semantics with robustness intervals and latency bounds | agent | WS01-T02 | yes | yes | 3 | analisi §4.3, §4.7 | #verdict | R1-W6 R2-W2 AE-5 |
| WS01-T06 | rho-proposition1 | Definition of rho per verdict type and Proposition 1 with proof | agent | WS01-T05 | yes | yes | 3 | analisi §4.4, §3.2 | #verdict #conformal-calibrator | R2-W2 R2-W3 R2-W4 |
| WS01-T07 | alert-tuple-mapping | Alert tuple definition, traceability wording and FHIR/BPMN mapping sketch | agent | WS01-T04, WS01-T06 | no | yes | 2 | analisi §4.8, §3.4, §4.1 (decomposition) | #alert | R1-W8 R1-W9 |
| WS01-T08 | formalization-freeze | Formalization freeze: consistency review and hand-worked patient-day (M1) | agent | WS01-T03, WS01-T04, WS01-T05, WS01-T06, WS01-T07 | yes | yes | 2 | analisi §4.1, §4.6, §6 | #template #alert | R1-W1 AE-2 |
| WS01-T09 | literature-parameter-proposal | Literature-anchored proposal of registry and prior values (agent-assisted, human-checked) | human | WS01-T03, WS04-T02 | no | yes | 2 | analisi §4.1, §5.1, §10 (1), ADR-043 | #parameter-registry #priorsource | - |

Total estimate: 19 person-days.

## WS02-threat-fault-model: Threat model, fault model, attribution

| id | slug | title | owner | depends_on | crit | nonneg | pd | sources | interfaces | review_items |
|---|---|---|---|---|---|---|---|---|---|---|
| WS02-T01 | fault-model | Fault model for C2 (device, link, robot) | agent | WS01-T01 | yes | no | 1.5 | analisi §4.5, §5.1 (C2 injections) | #evidencevector | R1-W7 |
| WS02-T02 | threat-model | Threat model: attacker capabilities, attack classes, exclusions | agent | WS01-T01 | yes | no | 1.5 | analisi §3.6, §4.5, §10 | #evidencevector | R2-W7 |
| WS02-T03 | evidence-channels | Evidence channels and EvidenceVector semantics, availability per placement | agent | WS02-T01, WS02-T02 | yes | no | 1.5 | analisi §4.5, §4.9 (1, 2) | #evidencevector | R1-W7 |
| WS02-T04 | attribution-rule | Attribution rule spec: hierarchy, abstention, cascades, clinician-in-the-loop | agent | WS02-T03, WS01-T07 | yes | no | 2 | analisi §4.5, §4.9 (3, 4) | #attribution | R2-W7 R3-W4 |
| WS02-T05 | diagnosability-hazards | Diagnosability matrix (machine-readable) and hazard and standards paragraph | agent | WS02-T04 | no | no | 2 | analisi §4.5, §3.5, §2 R3 weakness 5 | #attribution | R3-W4 R3-W5 AE-5 |

Total estimate: 8.5 person-days.

## WS03-related-work: Related work and bibliography

| id | slug | title | owner | depends_on | crit | nonneg | pd | sources | interfaces | review_items |
|---|---|---|---|---|---|---|---|---|---|---|
| WS03-T01 | bib-infrastructure | Bibliography infrastructure with verified flag and check tool | agent | - | no | no | 1 | analisi §3 (note), §7 | - | AE-3 |
| WS03-T02 | rw-stl-conformal | Related work: STL runtime monitoring, RV in robotics, conformal and predictive monitoring | agent | - | no | no | 2 | analisi §3.1, §3.2 | - | R1-W10 AE-3 |
| WS03-T03 | rw-medical-guidelines | Related work: medical CPS monitoring and guideline formalization | agent | - | no | no | 1.5 | analisi §3.3, §3.4 | - | AE-3 |
| WS03-T04 | rw-robots-security | Related work: assistive ward robots and wearable-device security | agent | - | no | no | 1.5 | analisi §3.5, §3.6 | - | AE-3 |
| WS03-T05 | rw-section-draft | Related Work section draft (four paragraphs with difference sentences) | agent | WS03-T01, WS03-T02, WS03-T03, WS03-T04 | no | no | 1 | analisi §3.7, §7 | - | AE-3 |
| WS03-T06 | reference-verification | Human verification of every reference marked unverified | human | WS03-T05 | yes | no | 1 | analisi §3 (note) | - | - |

Total estimate: 8.0 person-days.

## WS04-benchmark: Benchmark generator

| id | slug | title | owner | depends_on | crit | nonneg | pd | sources | interfaces | review_items |
|---|---|---|---|---|---|---|---|---|---|---|
| WS04-T01 | trace-io | Trace schema dataclasses, serialisation and manifest | agent | WS05-T01 | yes | no | 2 | analisi §5.1 | #trace-schema | R3-W1 |
| WS04-T02 | priorsource-literature | PriorSource protocol and LiteraturePriorSource with mandatory provenance | agent | WS04-T01, WS01-T03 | yes | no | 2.5 | analisi §5.1 | #priorsource #parameter-registry | R3-W3 |
| WS04-T03 | latent-patient | Latent patient model: baseline pressure, circadian dip, autoregressive noise | agent | WS04-T02 | yes | no | 2 | analisi §5.1 (1) | #priorsource | - |
| WS04-T04 | pkpd-model | PK/PD response model and onset window derivation; evaluate Pulse Physiology Engine | agent | WS04-T03 | yes | no | 3 | analisi §5.1 (1) | #priorsource | - |
| WS04-T05 | adherence-dispenser | Adherence Markov model with DISPENSE and INTAKE events | agent | WS04-T02 | yes | no | 2 | analisi §5.1, §4.9 (5) | #trace-schema #priorsource | - |
| WS04-T06 | measurement-process | Measurement process: schedule, cuff error, HR and SpO2 from public real-noise data | agent | WS04-T04, WS04-T05, WS05-T02, WS00-T09 | yes | no | 2.5 | analisi §5.1 (2) | #trace-schema | - |
| WS04-T07 | inject-c2 | C2 fault injection | agent | WS04-T06, WS02-T01, WS02-T03 | yes | no | 2.5 | analisi §5.1 (3) | #trace-schema #evidencevector | - |
| WS04-T08 | inject-c3 | C3 integrity attacks at naive and informed attacker levels | agent | WS04-T06, WS02-T02, WS02-T03 | yes | no | 2.5 | analisi §5.1 (3), §3.6 | #trace-schema #evidencevector | - |
| WS04-T09 | inject-c1-confounders | C1 injection and deliberate confounders | agent | WS04-T07, WS04-T08 | yes | no | 2 | analisi §5.1 (3, 4) | #trace-schema | R3-W4 |
| WS04-T10 | latent-ground-truth | Latent ground-truth labeller (phi_CP on the latent trace) and non-circularity tests | agent | WS04-T09, WS05-T04 | yes | no | 2 | analisi §5.1, §10 (1) | #trace-schema #monitor | R3-W1 |
| WS04-T11 | benchmark-builder | Benchmark builder CLI: splits by patient, manifest, seeds, scale | agent | WS04-T10, WS04-T15 | yes | no | 2 | analisi §5.1 | #trace-schema #experiment-config-and-outputs | R3-W1 |
| WS04-T12 | benchmark-validation | Benchmark validation report and alert-load sanity check | agent | WS04-T11 | no | no | 1.5 | analisi §5.1, §10 (1) | #trace-schema | R3-W1 |
| WS04-T13 | mimic-priorsource | MimicPriorSource and eICU variant (blocked until credentialing) | agent | WS04-T02, WS00-T04 | no | no | 2 | analisi §5.1 | #priorsource | - |
| WS04-T14 | second-pathology-optional | OPTIONAL: second pathology (diabetes, simglucose) | agent | WS04-T11, WS08-T02 | no | no | 4 | analisi §5.8, §9 | #priorsource | - |
| WS04-T15 | multi-day-labelling | Multi-day ground-truth labelling with history (ADR-046, ADR-055 (b)) | agent | WS04-T10, WS05-T10 | yes | no | 1.5 | ADR-046, ADR-055 (b), analisi §5.1 | #trace-schema #monitor | - |

Total estimate: 34.0 person-days.

## WS05-monitor: Monitor, conformal calibrator, attribution, ROS 2 wrappers

| id | slug | title | owner | depends_on | crit | nonneg | pd | sources | interfaces | review_items |
|---|---|---|---|---|---|---|---|---|---|---|
| WS05-T01 | scaffolding | Scaffolding of src/ralmon and toolchain | agent | - | yes | no | 0.5 | analisi §9 (5), §8.1 | #package-public-api | - |
| WS05-T02 | signals-rtamt-spike | Signals and derived signals; RTAMT spike (ADR-013) | agent | WS05-T01, WS01-T01, WS01-T02 | yes | no | 2 | analisi §4.1, §3.1, §9 (5) | #signals #time-and-units | R1-W10 |
| WS05-T03 | spec-package | spec package: registry and template loaders, normalisation, ranking, plan signature check | agent | WS05-T02, WS01-T03, WS01-T04 | yes | no | 3 | analisi §4.1, §4.2, §4.9 (7) | #template #parameter-registry | R1-W9 |
| WS05-T04 | monitor-core | Monitor core: past-time evaluation, robustness intervals, verdicts, reorder buffer, latency bounds | agent | WS05-T03, WS01-T05 | yes | no | 4 | analisi §4.7, §4.9 (2) | #monitor #verdict #time-and-units | R1-W6 R1-W7 R1-W10 |
| WS05-T05 | forecaster | Forecaster for continuous signals and robot deadlines | agent | WS05-T04 | yes | no | 3 | analisi §4.3, §2 R2 | #forecaster | R2-W1 R2-W5 R2-W8 |
| WS05-T06 | conformal-calibrator | Split and adaptive conformal calibrator, rho, alpha allocation, recalibration rule | agent | WS05-T04, WS01-T06 | yes | no | 3 | analisi §4.4, §5.6 (A1, A6) | #conformal-calibrator | R2-W3 R2-W4 R2-W6 |
| WS05-T07 | attribution-package | Attribution package: hierarchical rule, cascades, Attributor, natural-language rendering | agent | WS05-T04, WS02-T04, WS02-T05 | yes | no | 3 | analisi §4.5, §4.9 (3), §2 R3 weakness 6 | #attribution #alert #evidencevector | R3-W6 |
| WS05-T08 | predictive-integration | Predictive integration and run_offline end to end | agent | WS05-T05, WS05-T06, WS05-T07, WS01-T08 | yes | no | 2 | analisi §4.7 (3) | #monitor #verdict #detector | - |
| WS05-T09 | ros2-wrappers | ROS 2 wrapper packages: RSM, attribution, event manager, watchdog, heartbeat, ward-node placement | agent | WS05-T08, WS07-T01 | yes | no | 3 | analisi §4.9 (1), §9 (5) | #ros-2-interfaces | R3-W2 AE-4 |
| WS05-T10 | monitor-history-input | Monitor history input: run_offline replays the earlier days of the patient (ADR-046) | agent | WS05-T04 | yes | no | 2 | ADR-046, ADR-053 (h), docs/formal/01 §5.5 | #monitor #time-and-units #trace-schema | - |
| WS05-T11 | robot-channel-availability | Robot-channel availability from NODE_STATE colocated reports (ADR-054 (b)) | agent | WS05-T10 | yes | no | 1.5 | ADR-054, docs/models/evidence-channels.md | #monitor #signals | - |

Total estimate: 27.0 person-days.

## WS06-baselines: Baselines

| id | slug | title | owner | depends_on | crit | nonneg | pd | sources | interfaces | review_items |
|---|---|---|---|---|---|---|---|---|---|---|
| WS06-T01 | detector-harness | Detector protocol implementation and common harness | agent | WS05-T01, WS04-T01, WS05-T03, WS05-T07 | yes | no | 1.5 | analisi §5.4 | #detector #trace-schema | - |
| WS06-T02 | b1-static-thresholds | B1 static thresholds with simple schedule logic | agent | WS06-T01, WS01-T03, WS05-T02 | yes | no | 1.5 | analisi §5.4 (B1), §10 (1) | #detector | - |
| WS06-T03 | b2-anomaly-detection | B2 anomaly detection (forecast residual and isolation forest) | agent | WS06-T01, WS05-T05 | yes | no | 2 | analisi §5.4 (B2) | #detector #forecaster | R2-W8 |
| WS06-T04 | b3-plain-stl | B3 STL without uncertainty (raw robustness on measured values) | agent | WS06-T01, WS05-T03, WS05-T04 | yes | no | 1.5 | analisi §5.4 (B3) | #detector #template | - |
| WS06-T05 | b4-conformal-only | B4 conformal without STL | agent | WS06-T01, WS05-T06, WS05-T05 | yes | no | 2 | analisi §5.4 (B4) | #detector #conformal-calibrator | - |
| WS06-T06 | b5-lindemann | B5 conformal STL predictive monitoring after Lindemann et al. 2023, with failure analysis | agent | WS06-T01, WS05-T03, WS05-T06, WS05-T04, WS05-T05, WS00-T08 | yes | yes | 3.5 | analisi §5.4 (B5), §3.2, §10 (2) | #detector #conformal-calibrator | AE-3 |
| WS06-T07 | baseline-fairness-audit | Baseline fairness audit | agent | WS06-T02, WS06-T03, WS06-T04, WS06-T05, WS06-T06 | yes | no | 1 | analisi §10 (1), §5.4 | #detector | - |

Total estimate: 13.0 person-days.

## WS07-ros2-sim: ROS 2 simulation

| id | slug | title | owner | depends_on | crit | nonneg | pd | sources | interfaces | review_items |
|---|---|---|---|---|---|---|---|---|---|---|
| WS07-T01 | sim-workspace | Package availability check and simulation workspace | agent | WS00-T05 | yes | no | 2 | analisi §5.2 | #ros-2-interfaces | - |
| WS07-T02 | hospital-world | Gazebo hospital world with 4-8 rooms, staggered care plans, one robot | agent | WS07-T01 | yes | no | 3 | analisi §5.2 | #ros-2-interfaces | - |
| WS07-T03 | simulated-devices | Simulated devices as lifecycle nodes replaying benchmark traces | agent | WS07-T01, WS04-T01, WS05-T09 | yes | no | 3 | analisi §5.2 | #ros-2-interfaces #trace-schema | - |
| WS07-T04 | robot-task-layer | Robot task layer: care obligations, navigation, witness perception | agent | WS07-T02, WS07-T03, WS05-T09, WS05-T05 | yes | no | 3 | analisi §4.1 (4), §4.9 (1), §5.2 | #ros-2-interfaces #evidencevector | R3-W2 AE-4 |
| WS07-T05 | robot-fault-injection | Robot and link fault injection | agent | WS07-T03 | no | no | 2 | analisi §5.2, §5.1 (3) | #ros-2-interfaces #evidencevector | - |
| WS07-T06 | deadline-prediction | Predictive monitoring of care-delivery deadlines | agent | WS07-T04, WS05-T06, WS05-T05, WS08-T01, WS04-T11 | no | no | 2.5 | analisi §4.3, §5.2, §10 (3) | #forecaster #conformal-calibrator | R2-W5 |
| WS07-T07 | latency-scalability | Latency, resource and scalability measurement | agent | WS07-T05, WS07-T06, WS08-T01 | yes | no | 2.5 | analisi §5.2, §5.5 | #ros-2-interfaces #metrics | - |

Total estimate: 18.0 person-days.

## WS08-experiments: Experiments

| id | slug | title | owner | depends_on | crit | nonneg | pd | sources | interfaces | review_items |
|---|---|---|---|---|---|---|---|---|---|---|
| WS08-T01 | runner-metrics | Experiment runner, config and metrics module | agent | WS04-T11, WS06-T01, WS05-T08, WS05-T11 | yes | no | 3 | analisi §5.5 | #metrics #experiment-config-and-outputs | - |
| WS08-T02 | main-experiment | Main experiment: B1-B5 versus proposed method | agent | WS08-T01, WS06-T07 | yes | no | 2.5 | analisi §5.4, §5.5 | #metrics #detector | R3-W1 R3-W6 AE-1 |
| WS08-T03 | ablations | Ablations A1, A2, A3, A5, A7 | agent | WS08-T02 | yes | no | 3 | analisi §5.6 | #experiment-config-and-outputs | R2-W1 R2-W9 |
| WS08-T04 | ablation-a4-embodied | Ablation A4: embodied channel removed | agent | WS08-T02, WS02-T05 | yes | yes | 2 | analisi §5.6 (A4), §10 (3) | #evidencevector #attribution | R3-W2 AE-4 |
| WS08-T05 | shift-a6 | Distribution shift and A6: split versus adaptive conformal | agent | WS08-T02 | no | no | 2 | analisi §5.6 (A6), §5.5 | #conformal-calibrator | R2-W4 |
| WS08-T06 | unlabeled-real-run | Unlabeled real-data run for alert load (blocked until access) | agent | WS08-T02, WS04-T13 | no | no | 1.5 | analisi §5.1, §5.8 | #priorsource | - |
| WS08-T07 | result-freeze | Reproducibility check and result freeze | agent | WS08-T03, WS08-T04, WS08-T05 | yes | no | 1 | analisi §5.1, §5.5 | #experiment-config-and-outputs | AE-1 |

Total estimate: 15.0 person-days.

## WS09-figures: Figures and tables

| id | slug | title | owner | depends_on | crit | nonneg | pd | sources | interfaces | review_items |
|---|---|---|---|---|---|---|---|---|---|---|
| WS09-T01 | figure-scaffold | Figure and table generation scaffold from outputs/ | agent | WS08-T01 | no | no | 1 | analisi §7 | #experiment-config-and-outputs | - |
| WS09-T02 | fig1-architecture | Fig. 1 redesigned architecture | agent | WS01-T08, WS02-T04, WS09-T01 | no | no | 1.5 | analisi §4.9 (6), §7 | #ros-2-interfaces | R3-W7 AE-5 |
| WS09-T03 | fig2-patient-day | Fig. 2 patient-day trace with states and conformal band | agent | WS09-T01, WS08-T02 | yes | no | 1.5 | analisi §7, §4.6 | #verdict | - |
| WS09-T04 | table1-templates | Table I template library | agent | WS01-T08, WS09-T01, WS05-T03 | no | no | 1 | analisi §7 | #template | - |
| WS09-T05 | results-tables-fig3 | Table II, Table III and Fig. 3 | agent | WS09-T01, WS08-T03, WS08-T05, WS08-T04 | yes | no | 2 | analisi §7, §5.5, §5.6 | #metrics | - |
| WS09-T06 | fig4-lab-optional | OPTIONAL: Fig. 4 lab setup photo and ROS graph | agent | WS10-T05 | no | no | 0.5 | analisi §7 | - | - |

Total estimate: 7.5 person-days.

## WS10-lab-demo: Lab demo

| id | slug | title | owner | depends_on | crit | nonneg | pd | sources | interfaces | review_items |
|---|---|---|---|---|---|---|---|---|---|---|
| WS10-T01 | lab-plan-safety | Lab setup plan and safety review | human | WS07-T02, WS00-T06, WS02-T05 | no | no | 1.5 | analisi §5.3, §2 R3 weakness 5 | - | - |
| WS10-T02 | emulated-devices | Emulated BLE devices on programmable boards | human | WS10-T01 | no | no | 3 | analisi §5.3 | #ros-2-interfaces | - |
| WS10-T03 | dispenser-build | Smart dispenser build (lock, open sensor, load cell, placebo) | human | WS10-T01 | no | no | 3 | analisi §5.3 | - | - |
| WS10-T04 | scenario-scripts | Compressed-timeline scenario scripts and runner | agent | WS07-T04, WS10-T02, WS10-T03 | no | no | 2 | analisi §5.3 | #ros-2-interfaces #trace-schema | - |
| WS10-T05 | demo-runs | Demo runs and data collection on the real robot | human | WS10-T02, WS10-T03, WS10-T04 | no | no | 4 | analisi §5.3 | #metrics | R3-W1 R3-W2 |
| WS10-T06 | lab-analysis-fallback | Lab results analysis and simulation-video fallback | agent | WS10-T05, WS08-T01 | no | no | 1.5 | analisi §5.3, §9 (cut order) | #metrics | - |

Total estimate: 15.0 person-days.

## WS11-vignettes: Clinician vignette study

| id | slug | title | owner | depends_on | crit | nonneg | pd | sources | interfaces | review_items |
|---|---|---|---|---|---|---|---|---|---|---|
| WS11-T01 | study-design | Vignette study design and measures | agent | WS00-T03, WS00-T06, WS01-T07 | no | no | 2 | analisi §5.7, §2 R3 weakness 6 | #alert | R3-W6 |
| WS11-T02 | vignette-generation | Vignette generation, natural-language alerts, answer key draft | agent | WS11-T01, WS05-T07, WS04-T11, WS06-T02, WS06-T03 | no | no | 3 | analisi §5.7 | #alert #trace-schema | R3-W6 |
| WS11-T03 | key-validation-pilot | Clinician answer-key validation and pilot | human | WS11-T02 | no | no | 1.5 | analisi §5.7 | - | - |
| WS11-T04 | study-implementation | Online study implementation | agent | WS11-T03 | no | no | 2 | analisi §5.7 | - | - |
| WS11-T05 | recruit-and-run | Recruitment and study run (8-15 participants) | human | WS11-T04 | no | no | 3 | analisi §5.7 | - | - |
| WS11-T06 | study-analysis | Study analysis and write-up | agent | WS11-T05 | no | no | 2 | analisi §5.7 | #metrics | - |

Total estimate: 13.5 person-days.

## WS12-paper: Paper

| id | slug | title | owner | depends_on | crit | nonneg | pd | sources | interfaces | review_items |
|---|---|---|---|---|---|---|---|---|---|---|
| WS12-T01 | title-abstract | Title selection and abstract without numbers (commitment letter) | human | WS00-T02, WS08-T07, WS09-T05, WS07-T07 | yes | no | 0.5 | analisi §8.3, §8.4, §9 (0.4, 0.5) | - | - |
| WS12-T02 | paper-skeleton | Paper skeleton with page budget | human | WS00-T01, WS08-T07, WS09-T05, WS07-T07 | no | no | 1 | analisi §7 | - | - |
| WS12-T03 | intro-contributions | Introduction and contributions rewrite | human | WS01-T08, WS12-T02, WS00-T07 | no | no | 1.5 | analisi §6, §7, §10 (3) | - | R3-W3 |
| WS12-T04 | methods-sections | Sections III and IV (formulation and methods) | human | WS01-T08, WS02-T05, WS12-T02, WS00-T07 | yes | no | 3 | analisi §4, §7, §8.1 | #template #alert | R2-W8 R2-W9 AE-5 |
| WS12-T05 | experiments-section | Section V experiments and results | human | WS09-T05, WS08-T07, WS07-T07, WS10-T06 | yes | no | 2.5 | analisi §5, §7 | #metrics | - |
| WS12-T06 | discussion-conclusion-rw | Discussion, limitations, conclusion, related work insertion and terminology sweep | human | WS12-T05, WS03-T06, WS12-T03, WS12-T04 | yes | no | 1.5 | analisi §7, §8.1, §10 | - | R3-W7 |
| WS12-T07 | devils-advocate | Internal devil's-advocate review and claim audit | human | WS12-T06 | yes | no | 2 | analisi §2, §4.8, §10 | - | - |
| WS12-T08 | final-compile | Final compile, page fit, index terms, anonymisation check | human | WS12-T07, WS13-T03 | yes | no | 1 | analisi §7, §8.2 | - | - |

Total estimate: 13.0 person-days.

## WS13-release: Open-source release

| id | slug | title | owner | depends_on | crit | nonneg | pd | sources | interfaces | review_items |
|---|---|---|---|---|---|---|---|---|---|---|
| WS13-T01 | repo-hygiene | Repository hygiene: README, install docs, license decision | agent | WS05-T08, WS04-T11 | no | no | 1.5 | analisi §9 (13) | #package-public-api | - |
| WS13-T02 | repro-scripts | Reproduction scripts: one command per table and figure | agent | WS08-T07, WS09-T05, WS09-T02, WS09-T03, WS09-T04 | no | no | 1.5 | analisi §9 (13), §5.1 | #experiment-config-and-outputs | - |
| WS13-T03 | anonymised-snapshot | Anonymised release snapshot for double-blind review | agent | WS13-T01, WS13-T02, WS13-T04, WS00-T01 | no | no | 1 | analisi §9 (13) | - | - |
| WS13-T04 | generator-datasheet | Benchmark and generator documentation and datasheet | agent | WS04-T12, WS13-T01 | no | no | 1 | analisi §5.1, §10 (1) | #trace-schema | - |

Total estimate: 5.0 person-days.

## Totals

| WS | person-days | person-weeks (5 pd) |
|---|---|---|
| WS00-admin | 9.25 | 1.9 |
| WS01-formalization | 19 | 3.8 |
| WS02-threat-fault-model | 8.5 | 1.7 |
| WS03-related-work | 8.0 | 1.6 |
| WS04-benchmark | 32.5 | 6.5 |
| WS05-monitor | 23.5 | 4.7 |
| WS06-baselines | 13.0 | 2.6 |
| WS07-ros2-sim | 18.0 | 3.6 |
| WS08-experiments | 15.0 | 3.0 |
| WS09-figures | 7.5 | 1.5 |
| WS10-lab-demo | 15.0 | 3.0 |
| WS11-vignettes | 13.5 | 2.7 |
| WS12-paper | 13.0 | 2.6 |
| WS13-release | 5.0 | 1.0 |
| all | 200.75 | 40.1 |
