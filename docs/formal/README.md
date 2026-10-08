# docs/formal: formal specification of clinical-pathway safety specifications (M1 freeze)

This directory holds the formal core of the RA-L paper: signals and sampling semantics, the library of seven past-time STL templates, the parameter registry design, normalised robustness and the lexicographic order of alerts, three-valued online semantics with robustness intervals, the confidence rho with Proposition 1, the alert tuple, a consistency review and one hand-worked patient-day. It is technical and pre-clinical: no real patients, no claim of clinical validation, and every clinical number is either fixture arithmetic (fixture registry F0) or labelled "illustrative, unverified" (ADR-020). The paper text is not here (ADR-037).

## Freeze marker

FROZEN: yes (M1 formalization freeze)

clinician_review: pending

The field `clinician_review` is `pending` because `docs/plan/workstreams/WS00-admin/outputs/WS00-T07.md` does not exist (the task WS00-T07 is blocked). By ADR-043 (accepted, gab, 2026-10-08) the freeze runs without the review and the missing review does not hold M1. The M1 row of `docs/plan/00-master-plan.md` also needs the contract amendments decided by ADR and the versions of `02-interfaces.md` agreed: that gate stays open until gab decides the proposed ADRs listed below. The values of the registry are not part of the freeze.

What is frozen: documents `01` to `09` at version 1.0 as they stand at the commit that carries this file, the five golden files, the fixture registry F0 and the contract versions listed below. What is not frozen: the registry values (version 0.2.0, `review_status: unreviewed`, every `reviewed_by` null), the clinical review, the contract text that the proposed ADRs would change, the open points OPF-1 to OPF-17 of `08-consistency-review.md` section 5.4 and everything about devices, ROS 2, the benchmark, the baselines and the paper. The exact statement, the readings fixed by the review (R1 to R7) and the precedence rule between documents are in `08-consistency-review.md` section 5.

## Index of documents

| Document | Version | Task | Content | Feeds |
|---|---|---|---|---|
| `01-signals-sampling.md` | 1.0 | WS01-T01 | seventeen signals, grid and ceiling rule, two clocks and the reorder buffer, derived signals, day boundary, decomposition phi = phi_CP and phi_SYS and phi_INT | paper Section III; WS05-T02 |
| `02-templates.md` | 1.0 | WS01-T02 | grammar and quantitative semantics, margin and guard rule, the seven templates with units, latency and robot obligations, expressiveness notes | paper Section IV-A and Table I; WS05-T03, WS05-T04, WS07-T04 |
| `03-parameter-registry.md` | 1.0 | WS01-T03 | registry design, YAML schema, loader behaviour, anchoring procedure, versioning and per-patient overrides, review sheet | WS00-T07; WS05-T03 |
| `04-normalisation-ranking.md` | 1.0 | WS01-T04 | normalised robustness `clip(sigma / s, -1, 1)`, lemmas, lexicographic ranking, ablation A3 | paper Section IV-B; WS05-T03, WS08-T03 |
| `05-three-valued-semantics.md` | 1.0 | WS01-T05 | robustness intervals on prefixes, three-valued verdict, tie rule, state diagram, predicted channel, monitoring loop, latency bounds | paper Section IV-C; WS05-T04 |
| `06-rho-proposition1.md` | 1.0 | WS01-T06 | rho for MEASURED, PREDICTED and DETERMINISTIC verdicts, conformal setting, Proposition 1 and 1b, caveats and allocation | paper Sections IV-B and IV-C; WS05-T06, WS05-T08 |
| `07-alert-tuple-mapping.md` | 1.0 | WS01-T07 | alert tuple fields, lifecycle, cascades, decomposition and claim wording, care-plan governance, FHIR and BPMN sketch | WS02-T04, WS05-T07, WS11-T01 |
| `08-consistency-review.md` | 1.0 | WS01-T08 | contract-by-contract review, CP1 to CP13 and new points, cross-document checks, proposed ADRs, freeze statement | M1 |
| `09-worked-patient-day.md` | 1.0 | WS01-T08 | a hand-computed patient-day that replaces the workshop Table I | WS09-T03, WS09-T04, WS05-T08 |

## Contract versions consumed

All twelve contracts that the formalization reads are at version 0.1.0 and are unchanged by the freeze (`docs/plan/02-interfaces.md`; `git diff --quiet -- docs/plan/02-interfaces.md` exits 0).

| Contract | Version | Read by |
|---|---|---|
| `#time-and-units` | 0.1.0 | `01`, `05` |
| `#trace-schema` | 0.1.0 | `01`, `05`, `08`, `09` |
| `#parameter-registry` | 0.1.0 | `03` |
| `#template` | 0.1.0 | `02`, `03`, `04` |
| `#signals` | 0.1.0 | `01` |
| `#verdict` | 0.1.0 | `05`, `06` |
| `#forecaster` | 0.1.0 | `05`, `08` (review only: the contract has no carrier for an arrival time, NP-18) |
| `#conformal-calibrator` | 0.1.0 | `06` |
| `#monitor` | 0.1.0 | `01`, `05`, `07` |
| `#alert` | 0.1.0 | `07` |
| `#evidencevector` | 0.1.0 | `08`, `09` (as read by the worked day) |
| `#attribution` | 0.1.0 | `07`, `08`, `09` |

## Registry

`configs/registry/hypertension.yaml` version **0.2.0** (2026-10-08, WS01-T09, ADR-043): 31 entries, 7 derived latency names, 3 unset names (`priority_sys`, `priority_int`, `bound_dose_count_upper`), `review_status: unreviewed`. The values are literature-anchored proposals and design choices accepted by gab, none reviewed by a clinician. The documents `03` to `07` describe the registry of version 0.1.0 in places (see `08` section 3.10, D1 to D5); the file is authoritative for the state of the registry. The worked day uses F0 only. Names used by the documents or the golden that are in no registry entry, no F0 row and no unset list: `evidence_margin_ms`, `evidence_grace_ms` (used as the fixture value 0), `hr_coherence_tolerance`, `ecg_sqi_floor` and `ppg_sqi_floor` (used only as relations to a reading); `docs/models/evidence-channels.md` requests nine such names and only `clock_skew_max_ms` is registered (`08` section 3.1, OPF-6). `meas_min_day`, `step_ms` and `reorder_delay_ms` are not registry names by design.

## Golden files

| File | Cases | Task | Checked by |
|---|---|---|---|
| `golden/templates.yaml` | 26 cases and the 26-row `fixture_registry` | WS01-T02 | `08` section 3: 26 of 26 re-derived; F0 identical to the WS01 README |
| `golden/ranking.yaml` | 16 (10 normalisation, 6 ranking) | WS01-T04 | 10 of 10 normalisation cases and 6 of 6 ranking cases re-derived; RK-1 and RK-4 hold a refinement-record value (OPF-14) |
| `golden/verdicts.yaml` | 24 | WS01-T05 | 24 of 24: the 21 non-predictive cases in every field; V-PRED-1 to V-PRED-3 by the interval record and the conformal module |
| `golden/conformal.yaml` | 7 | WS01-T06 | 7 of 7 cases (ranks, quantiles, alpha*, both variants, minimum sizes, rho by `math.erf`) |
| `golden/patient-day.yaml` | 1 day: 32 records, 6 alerts, the ranking | WS01-T08 | 32 of 32 records, 6 of 6 alerts, ranking, attribution table and cascade re-derived by the scratch script |

## Proposed ADRs

New, appended to `docs/plan/03-decisions.md` by WS01-T08, all proposed with the confirmation tag: **ADR-045** (template contract: robot-obligation flag and record, tick kinds, grammar term `age`, measurement count not adopted, HOLD refined form), **ADR-046** (cross-day carry-over), **ADR-047** (registry typing and loader surface), **ADR-048** (`VerdictRecord` carrier fields and the text of rule 1), **ADR-049** (clarifications of contract comments), **ADR-050** (`rank_alerts` order K1). They cover CP1, CP2, CP3, CP5, CP6, CP7, CP9, CP10, CP11 and CP13 together with the existing ADR-029 (accepted), ADR-030, ADR-041 and ADR-028 (accepted); CP8 is reported to WS02 (ADR-032 proposed) and CP4 is ADR-030. The contract file is not edited and no contract version is bumped; the ADRs state the old version, the new version, the affected tasks and the migration.

## How to use

- Implementation tasks read the document of their contract point and the golden file named in its task file; a golden file is read-only, and a change to a case requires re-deriving its hand calculation (`01-conventions.md` section 3).
- `golden/patient-day.yaml` can serve as an end-to-end fixture for WS05-T08 and as a scenario for the attribution rules of WS02-T04; the intended causes under `scenario_description` are not an input of the monitor.
- A frozen document is reopened by setting the status of its owning task to `in_progress`, fixing it there, rerunning that task's checks and recording the change in `08-consistency-review.md`.
