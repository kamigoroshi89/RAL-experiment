# WS01-formalization: Formalization

## Objective

Produce the formal core of the paper and freeze it as milestone M1: signals and sampling semantics, the past-time STL template library, the parameter registry, normalised robustness and lexicographic ranking, three-valued online semantics with robustness intervals, the definition of rho per verdict type with Proposition 1, the alert tuple with its traceability wording, and a hand-worked patient-day that replaces the workshop Table I.

Every WS01 task is `non_negotiable: true` (analisi §9: "Non tagliate ... la formalizzazione"; `00-master-plan.md` section 5). The tasks are document and specification tasks. Their outputs are Markdown and LaTeX files under `docs/formal/`, machine-readable golden examples under `docs/formal/golden/`, and the registry `configs/registry/hypertension.yaml`. They feed paper Sections III (problem formulation) and IV-A to IV-C (templates, severity and confidence, three-valued monitoring), the code tasks of WS05, the benchmark labeller of WS04 and the attribution spec of WS02.

No numeric clinical value is decided in this workstream (ADR-020). Values that appear are either taken from analisi §4.1, §4.2, §4.6 and §4.7 and labelled "illustrative, unverified", or are fixture-only arithmetic choices that live in `docs/formal/golden/` and never in the registry. The registry is filled and clinician-reviewed by WS00-T07.

## Inputs

- `docs/source/analisi.md`: §4.1 (signals, five discussion aspects, LaTeX templates, decomposition), §4.2 (normalisation, ranking), §4.3 and §4.7 (three-valued semantics), §4.4 (rho, Proposition 1), §4.6 (errors of the workshop Table I), §4.8 (claim rewording), §3.4 (FHIR and BPMN), §4.9 items 2, 3, 5, 7, §2 R1, R2 and R3 weaknesses cited in the task files, §6 (contributions), §7 (page budget).
- `docs/plan/02-interfaces.md`: `#time-and-units`, `#signals`, `#template`, `#parameter-registry`, `#verdict`, `#conformal-calibrator`, `#alert` (owned or consumed by WS01), plus `#monitor`, `#evidencevector`, `#attribution` for the consistency review in T08. WS01 never edits this file (`01-conventions.md` section 6).
- `docs/plan/03-decisions.md`: ADR-002, 004, 007, 008, 009, 017, 018, 020.
- Output of WS00-T02 (scope decisions) unblocks T01. Output of WS00-T03 and WS00-T07 (clinician and registry review) is a later consumer, not an input.

### Shared conventions for all WS01 documents

1. Files are English Markdown. Formulas are LaTeX in fenced blocks or `$...$`. Each document has numbered H2 headings of the form `## n Title` (the task files name the required headings so that `grep -F` can check them), a "Paper excerpt" section sized to the page budget of analisi §7, and a last section "Open points for WS01-T08".
2. Terms follow the binding glossary of `01-conventions.md` section 7 (tier, module, node, forecaster, conformal calibrator, pathway template and patient care plan, DISPENSE and INTAKE, alert, violation, attributed cause, robustness reserved to STL). The claim wordings of analisi §4.8 are used verbatim where a claim is made.
3. Every parameter used in a formula is a registry name (working names below; WS01-T02 fixes the final names, WS01-T03 registers them). A "Parameters used" table in each document lists name, unit and origin so that T08 can grep it against the registry.
4. References: no citation is written from memory. Analisi §3 marks references as unverified until a human checks them (ADR-018). Where a document needs a reference (quantitative STL semantics, robustness intervals on prefixes, AGM robustness, weighted STL, conformal quantile), it writes the marker `[ref-needed: WS03]` and names the analisi section that mentions the work.
5. Time: a trace starts at 00:00 of the patient-day. `hh:mm` labels convert to integer milliseconds as `t_ms = (60*hh + mm) * 60000` (ADR-017); for example 09:05 is 32,700,000. Clock times are labels only; contracts use `TimeMs`.
6. Symbols: raw robustness sigma (native unit), normalised robustness sigma-tilde in [-1, 1], scale s (registry `scale_<template>`), monitor step T_s (`step_ms`), reorder delay D (`reorder_delay_ms`).

### Fixture registry F0 (test-only, shared by T02, T04, T05, T06, T08)

F0 is the parameter set used by every golden example so that hand-computed numbers agree across documents. It is written once, identically, in the `fixture_registry` section of `docs/formal/golden/templates.yaml` (T02) and is checked against this table by T02 and T08. It is NOT the clinical registry and its fixture-only rows must never be copied into `configs/registry/hypertension.yaml`.

| Working name | Value | Unit | Origin |
|---|---|---|---|
| `bp_band_low` | 110 | mmHg | analisi §4.1 (illustrative, unverified) |
| `bp_band_high` | 140 | mmHg | analisi §4.1 (illustrative, unverified) |
| `bp_hold_threshold` | 100 | mmHg | analisi §4.1 (illustrative, unverified) |
| `hold_lookback` | 3600000 | ms | analisi §4.1, 60 min (illustrative, unverified) |
| `dose_max_24h` | 2 | dose | analisi §4.1 (illustrative, unverified) |
| `dose_min_day_end` | 2 | dose | analisi §4.1 (illustrative, unverified) |
| `int_window` | 300000 | ms | analisi §4.1, 5 min (illustrative, unverified) |
| `delta1` | 3600000 | ms | analisi §4.6 window [08:00, 10:00] of a 07:00 dispense (illustrative, unverified) |
| `delta2` | 10800000 | ms | same source |
| `bound_bp_lower`, `bound_bp_upper` | 50, 250 | mmHg | analisi §4.7 example (illustrative, unverified) |
| `scale_range` | 20 | mmHg | analisi §4.2 example |
| `scale_sched` | 1800000 | ms | analisi §4.2 example, 30 min |
| `scale_count` | 1 | dose | analisi §4.2 example |
| `priority_hold`, `priority_range`, `priority_sched` | 1, 2, 3 | rank, 1 = highest | analisi §4.2 order example (hold > range > sched) |
| `meas_min_day` | 5 | count | analisi §2 R2 weakness 5 and §4.6 (five measurements a day); used only if T02 adopts a measurement-count obligation (CP2) |
| `sched_window` | 1800000 | ms | FIXTURE-ONLY |
| `delta_resp` | 10 | mmHg | FIXTURE-ONLY |
| `cuff_inflation_min` | 30000 | ms | FIXTURE-ONLY |
| `scale_hold`, `scale_resp` | 20 | mmHg | FIXTURE-ONLY (same as `scale_range`) |
| `scale_sys` | 30000 | ms | FIXTURE-ONLY |
| `scale_int` | 300000 | ms | FIXTURE-ONLY |
| `priority_count`, `priority_resp` | 2, 2 | rank | FIXTURE-ONLY |
| `priority_sys`, `priority_int` | 3, 3 | rank | FIXTURE-ONLY |
| `cuff_error_sd` | 6 | mmHg | FIXTURE-ONLY (Gaussian error model of rho, T06) |
| `step_ms` (T_s) | 60000 | ms | FIXTURE-ONLY monitor configuration |
| `reorder_delay_ms` (D) | 0; 30000 in the reorder examples | ms | FIXTURE-ONLY monitor configuration |

FIXTURE-ONLY means: chosen for hand arithmetic, no clinical meaning, no claim about any device or guideline.

### Golden file format (`docs/formal/golden/*.yaml`)

One YAML list per file; each case has these keys, in this order. Times are integer milliseconds (the `hh:mm` label goes in a comment). WS05 tasks load these files read-only or copy them into `tests/fixtures/`; a change to a golden case requires re-deriving its `hand_calculation` and shows in the diff (`01-conventions.md` section 3).

```yaml
- id: G-RANGE-2
  contract: ["02-interfaces.md#template"]
  source: "analisi §4.6 row 08:55 (arithmetic 140 - 152)"     # or "plan fixture"
  fixture: {registry: F0, step_ms: 60000, reorder_delay_ms: 0}
  inputs:
    samples: [{signal: bp, t_device_ms: 32700000, t_rx_ms: 32700000, value: 152.0, seq: null, quality: null}]   # 09:05
    events:  [{kind: measurement, t_device_ms: 32700000, t_rx_ms: 32700000, source: cuff, payload: {}, seq: null}]
  eval_at_ms: 32700000
  expected: {sigma_raw: -12.0, unit: mmHg, sigma_norm: -0.6, boolean: violated}
  hand_calculation: "min(152-110, 140-152) = min(42, -12) = -12; -12/20 = -0.6"
```

`expected` uses the field names of the contract type that WS05 will compare against (`VerdictRecord`, `Rho`, `PredictedViolation`, or the return value of `normalise` and `rank_alerts`). Infinite values are written `-.inf` and `.inf`.

## Outputs

| File | Task | Feeds |
|---|---|---|
| `docs/formal/01-signals-sampling.md` | T01 | Paper Section III (signals, sampling, time, decomposition); WS05-T02 fixtures for `hold_last` and derived signals |
| `docs/formal/02-templates.md`, `docs/formal/golden/templates.yaml` | T02 | Paper Section IV-A and Table I; WS05-T03, WS04-T10, WS06-T04, WS07-T04 |
| `docs/formal/03-parameter-registry.md`, `configs/registry/hypertension.yaml`, `configs/registry/registry.schema.json` | T03 | WS00-T07 clinician review; WS04-T02, WS05-T03, WS06-T02 |
| `docs/formal/04-normalisation-ranking.md`, `docs/formal/golden/ranking.yaml` | T04 | Paper Section IV-B; WS05-T03; WS08-T03 (ablation A3) |
| `docs/formal/05-three-valued-semantics.md`, `docs/formal/golden/verdicts.yaml` | T05 | Paper Section IV-C; WS05-T04; WS08-T03 (ablation A7) |
| `docs/formal/06-rho-proposition1.md`, `docs/formal/golden/conformal.yaml` | T06 | Paper Sections IV-B and IV-C (Proposition 1); WS05-T06; WS06-T05, WS06-T06 |
| `docs/formal/07-alert-tuple-mapping.md` | T07 | Paper Sections II, III (alert tuple, wording); WS02-T04; WS11-T01; WS12-T04 and T07 |
| `docs/formal/08-consistency-review.md`, `docs/formal/09-worked-patient-day.md`, `docs/formal/golden/patient-day.yaml`, `docs/formal/README.md`; proposed ADR entries appended to `docs/plan/03-decisions.md`; one note in `docs/plan/PROGRESS.md` | T08 | M1 freeze; paper Fig. 2 and the Table I replacement (WS09-T03, WS09-T04); the hand-worked day can serve as an end-to-end fixture for WS05-T08 and as a scenario for the kappa rules of WS02-T04 (a reuse suggestion, not a dependency) |

Mapping to the page budget of analisi §7: Section III (0.5 p) from 01, the decomposition of 02 and the alert tuple of 07; IV-A (0.5 p) from 02; IV-B (0.3 p) from 04 and 06 (definitions of rho); IV-C (0.45 p) from 05 and 06 (Proposition 1 with a 3 to 4 line proof).

## Dependencies

- **Upstream.** WS00-T02 (scope decisions: hypertension, C3 as integrity violation, distributed architecture) unblocks T01. Inside the workstream: T01 to T02; T02 to T03, T04 and T05; T05 to T06; T04 and T06 to T07; T03 to T07 to T08.
- **Downstream.** WS00-T07 (clinician review of registry, taxonomy and priorities; M1 gate) depends on T03. WS02-T01 to T03 depend on T01; WS02-T04 depends on T07. WS04-T02 depends on T03. WS05-T03 depends on T03 and T04, WS05-T04 on T05, WS05-T06 on T06. WS09-T02, WS09-T04 and WS12-T03 and T04 depend on T08. WS11-T01 depends on T07.
- **Contract anchors** owned by WS01: `#parameter-registry` (T03), `#template` (T02, T04), `#verdict` (T05, T06), `#alert` (T07). Consumed: `#time-and-units`, `#signals` (T01), `#conformal-calibrator` (T06).

### Contract points to settle in WS01 (feed T08)

These are apparent gaps or tensions found while reading `02-interfaces.md` against the analisi. Each task below resolves its own item inside `docs/formal/` and records it in its "Open points" section; T08 decides which need an ADR. No task edits `02-interfaces.md`.

| Id | Anchor | Apparent issue | Settled in |
|---|---|---|---|
| CP1 | `#template` | The comment on `creates_robot_obligation` says True for RESP and SCHED, but analisi §10 (3) also derives a witness obligation from phi_INT | T02 |
| CP2 | `#template`, `#signals` | `MEAS_COUNT` exists and analisi §4.6 and §4.9 (3) use a day-end counter of five measurements, but `TemplateId.COUNT` is described as a dose count and `RobustnessUnit` has no unit for measurement counts | T02 |
| CP3 | `#verdict` rule 1 | Strict inequalities leave sigma = 0 undecided even when nothing is unknown (for example `c_d` equal to the limit): PENDING would never resolve | T05 |
| CP4 | `#verdict` rule 2, `#conformal-calibrator` | The "possible" variant uses `sigma_hat - q`, but the calibrator exposes only the upper one-sided quantile; validity needs the lower quantile of R or a symmetry assumption | T06 |
| CP5 | `#alert` | `sigma_norm` is documented in [-1, 0) but PREDICTED_VIOLATION alerts (variant "possible", or a negative quantile) can carry sigma_hat >= 0; the direction of `priority` is not stated | T04, T07 |
| CP6 | `#verdict` | No way to say "deadline elapsed but undecidable because an evidence channel (presence, intake) is unavailable" | T05 |
| CP7 | `#trace-schema`, `#monitor` | `ObservedDay` and `run_offline(day, ...)` carry no state from the previous day, but `c_d` spans 24 h and response windows can end after 24:00 | T01, T05 |
| CP8 | `#evidencevector` (owner WS02) | No field for dispenser content or weight change, although the double-take versus bounce rows of analisi §4.5 depend on it | T08 reports to WS02 |
| CP9 | none | No contract for the robot obligation record that WS07-T04 must consume (analisi §4.1 aspect 4) | T02 defines, T08 proposes |
| CP10 | `#parameter-registry`, `#alert` | `RegistryEntry.value` is float while priorities are `int` and durations are `DurationMs`; `PhysioBounds` carries no rationale or reviewer although ADR-020 requires both | T03 |
| CP11 | `#template` | One `unit` and one `scale_param` per template, but HOLD, RESP and SYS combine atoms of different kinds | T02 |
| CP12 | `#signals`, `#verdict` | Raw intervals can be infinite, and `hold_last` has no encoding for "before the first sample" | T01, T05 |
| CP13 | `#monitor`, `#attribution`, `#alert` | "Attribution turns violated records into alerts" while `Alert.verdict` admits PREDICTED_VIOLATION, so kappa of a predicted alert is undefined | T07 |

### INDEX observations

- WS01-T08 is the M1 freeze, and `00-master-plan.md` section 3 makes M1 depend on clinician review, but WS01-T08 has no dependency on WS00-T07. T08 therefore records the review status in `docs/formal/README.md` and marks the freeze "pending clinician review" until the WS00-T07 output exists. Suggested fix: add WS00-T07 to the dependencies of the M1 gate, not necessarily of T08.
- `04-review-traceability.md` does not exist yet. Finding ids are read from `docs/source/review.md`: `Rk-Wn` is weakness n of reviewer k; `AE-1` to `AE-4` are the four numbered problems of the meta-review; `AE-5` is the paragraph on internal inconsistencies (sigma units, cross-modal timing of Table I, measured versus conformal contradiction, non-identifiable C3).

## Acceptance criteria

1. All files listed under Outputs exist, each `docs/formal/0n-*.md` contains the required headings named in its task file, and `grep -nE 'T[O]DO|T[B]D|[?][?][?]|lore[m]' docs/formal -r configs/registry` prints nothing.
2. Every SignalId and every TemplateId of `02-interfaces.md` appears in `01-signals-sampling.md` and `02-templates.md` respectively; every template row has unit, `scale_param`, `priority_param`, `max_verdict_latency_param` and `creates_robot_obligation`.
3. Every parameter name used in any `docs/formal` document is an entry, a derived bound, or a declared unset name of `configs/registry/hypertension.yaml`; no entry has `reviewed_by` other than null before WS00-T07.
4. The five golden files (`templates.yaml`, `ranking.yaml`, `verdicts.yaml`, `conformal.yaml`, `patient-day.yaml`) exist, their cases carry a `hand_calculation` or the calculation shown in `09-worked-patient-day.md`, the F0 table of this README is identical to the `fixture_registry` section of `templates.yaml`, and each numeric example of the task files is reproduced (26 template cases, 16 normalisation and ranking cases, 24 verdict cases, 7 conformal cases).
5. Proposition 1 is stated with hypotheses, a complete proof and the three caveats; the "possible" variant is stated with its own quantile; rho is defined for MEASURED, PREDICTED and DETERMINISTIC verdicts and is absent (None) for SATISFIED and PENDING records.
6. `docs/formal/09-worked-patient-day.md` reproduces no error of the workshop Table I (checklist of analisi §4.6 answered row by row).
7. `git diff --quiet -- docs/plan/02-interfaces.md` exits 0 after T08, and every contract point CP1 to CP13 has a disposition (consistent, clarified, ADR proposed, or reported to another workstream) in `docs/formal/08-consistency-review.md`.
8. `docs/formal/README.md` carries the freeze marker and the clinician-review status field; the freeze is not declared complete without it.

## Source sections

| Analisi | Used by |
|---|---|
| §4.1 (signals, sampling, templates, five aspects, decomposition) | T01, T02, T03, T07, T08 |
| §4.2 (normalisation, ranking, alternatives, never normalise by conformal width) | T03, T04 |
| §4.3, §4.7 (three-valued semantics, intervals, state diagram, pseudocode, complexity) | T05 |
| §4.4 (rho per verdict type, Proposition 1, three caveats, likely and possible) | T06 |
| §4.6 (errors of Table I) | T08 |
| §4.8 (claim rewording), §3.4 (FHIR PlanDefinition, BPMN) | T07 |
| §4.9 items 2, 3, 5, 7 (time, cascades, DISPENSE and INTAKE, plan governance) | T01, T02, T05, T07 |
| §2 R1 weaknesses 1 to 9, R2 weaknesses 2 to 4 and 6, R3 weakness 3 | task files as listed in `review_items` |
| §6 (contributions), §7 (page budget) | T08 and the paper excerpts |

## Tasks

| id | title | owner | status | depends_on |
|---|---|---|---|---|
| WS01-T01 | Problem formulation: signals, sampling semantics, time, decomposition | agent | blocked | WS00-T02 |
| WS01-T02 | Past-time STL template library with units and robot obligations | agent | blocked | WS01-T01 |
| WS01-T03 | Parameter registry design, YAML schema and anchoring procedure | agent | blocked | WS01-T02 |
| WS01-T04 | Normalised robustness and lexicographic alert ranking | agent | blocked | WS01-T02 |
| WS01-T05 | Three-valued online semantics with robustness intervals and latency bounds | agent | blocked | WS01-T02 |
| WS01-T06 | Definition of rho per verdict type and Proposition 1 with proof | agent | blocked | WS01-T05 |
| WS01-T07 | Alert tuple definition, traceability wording and FHIR/BPMN mapping sketch | agent | blocked | WS01-T04, WS01-T06 |
| WS01-T08 | Formalization freeze: consistency review and hand-worked patient-day (M1) | agent | blocked | WS01-T03, WS01-T04, WS01-T05, WS01-T06, WS01-T07, WS00-T07 |
