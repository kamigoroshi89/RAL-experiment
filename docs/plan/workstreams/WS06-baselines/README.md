# WS06-baselines: Baselines B1 to B5

## Objective

Implement the five baselines of analisi §5.4 behind the `Detector` contract of `02-interfaces.md#detector`, so that WS08 evaluates them with the same code as the proposed method and its ablations, and audit them so that the comparison survives the first residual objection of analisi §10 ("the evaluation is circular: whoever writes the specification wins").

| Baseline | What it is (analisi §5.4) | What it isolates |
|---|---|---|
| B1 | Static thresholds: the plan's bands, an alarm on every out-of-band sample, plus simple schedule logic | Value of temporal structure, windows and attribution at equal clinical knowledge |
| B2 | Anomaly detection: forecast-residual z-score and Isolation Forest | The approach the paper moves away from (review item R2-W8) |
| B3 | The same STL templates with RTAMT, verdicts on measured values, raw non-normalised robustness | Contribution of conformal prediction and of normalisation |
| B4 | Conformal anomaly detection without STL | Contribution of the specification |
| B5 | Conformal STL predictive monitoring after Lindemann, Qin, Deshmukh and Pappas (ICCPS 2023) applied to our templates | Novelty against the closest published method |

B5 is **NON-NEGOTIABLE** (analisi §9: "Non tagliate B5"; `00-master-plan.md` section 5). Its task WS06-T06 requires an explicit failure analysis showing where B5 fails on this problem (sparse sampling, mixed units, no attribution; analisi §10 objection 2), it is on the critical path, and it is not on any cut list. The implementer reads the paper (a human supplies the PDF) and records every deviation; the plan does not describe the published algorithm, to avoid inventing it.

Design rules shared by all tasks (they are what the fairness audit WS06-T07 verifies):

1. **Same clinical knowledge.** Baselines get the bands, schedules and template parameters that the proposed method gets, read only through the patient care plan (`TemplateInstance.param_values`, `CarePlan.schedule`) and the parameter registry. No numeric clinical constant appears in `src/ralmon/baselines`.
2. **No latent trace and no ground truth at inference.** `run` accepts only an `ObservedDay`. `fit` receives guarded views: ground truth on training days only, latent traces on no calibration day, every read logged.
3. **Same causal visibility.** Every baseline is driven by one step iterator that delivers an input at step `t` only if `t_device_ms <= t - reorder_delay_ms` and it has been received, exactly as `Monitor.advance` does.
4. **No attribution.** Every `Detection.label` is `None`; the `EvidenceVector` is dropped at the harness boundary. This asymmetry is documented, not hidden.
5. **Explicit operating parameters.** Each baseline exposes at most one operating parameter (`z_threshold` and `score_quantile` for B2, `alpha` for B4 and B5), without a numeric default; WS08 sweeps it from the experiment config. Each class docstring has a `Hyperparameter selection` section; nothing is tuned on test days.

## Inputs

- Contracts in `docs/plan/02-interfaces.md`: `#detector`, `#trace-schema`, `#forecaster`, `#template`, `#conformal-calibrator`, and for types used inside the baselines `#alert` (`Detection`), `#time-and-units`, `#parameter-registry`, `#signals`, `#verdict`.
- `docs/source/analisi.md`: §5.4 (B1 to B5), §10 objections 1 and 2, §3.2 (closest work), §4.1 to §4.4 (templates, normalisation, conformal caveats).
- `docs/plan/03-decisions.md`: ADR-013 (RTAMT and its wrapper), ADR-016 (toolchain), ADR-017 (integer milliseconds), ADR-020 (clinical parameters unverified).
- Code from other workstreams (as they land): trace-schema types (WS04-T01), the parameter registry `configs/registry/hypertension.yaml` (WS01-T03), `ralmon.spec` (WS05-T03), the forecaster (WS05-T05), the conformal calibrator (WS05-T06), and `ralmon.attribution.Detection`.
- The PDF of Lindemann et al. (ICCPS 2023), supplied by a human through WS00-T08, for WS06-T06 only.
- Benchmark days (`ObservedDay`, `BenchmarkDay`) from WS04 for the benchmark-scale section of the B5 failure analysis, if available when WS06-T06 runs.

## Outputs

| Path | Produced by | Content |
|---|---|---|
| `src/ralmon/baselines/__init__.py` | T01, extended by T02 to T06 | Public names `Detector`, `B1StaticThresholds`, `B2AnomalyDetection`, `B3PlainSTL`, `B4ConformalOnly`, `B5ConformalSTL` |
| `src/ralmon/baselines/base.py`, `access.py` | T01 | `Detector` protocol, `BaselineBase`, causal step iterator, rising-edge helper, guarded day views, read logs |
| `src/ralmon/baselines/b1_static_thresholds.py` | T02 | B1 |
| `src/ralmon/baselines/b2_anomaly_detection.py`, `b2_features.py` | T03 | B2 (residual z-score and Isolation Forest) |
| `src/ralmon/baselines/raw_robustness.py`, `b3_plain_stl.py` | T04 (T06 if it starts first) | Raw-robustness adapter over the WS05 evaluator; B3 |
| `src/ralmon/baselines/b4_conformal_only.py` | T05 | B4 |
| `src/ralmon/baselines/b5_conformal_stl.py` | T06 | B5 (both aggregations) |
| `src/ralmon/baselines/audit.py` | T07 | Knowledge-matrix generator from access logs |
| `tests/baselines/` | T01 to T07 | One test module per baseline, harness and access tests, failure-mode tests for B5, audit tests |
| `docs/plan/workstreams/WS06-baselines/notes/B5-deviations.md` | T06 | Published method as read (with locators), mapping to the templates, deviations |
| `docs/plan/workstreams/WS06-baselines/notes/B5-failure-analysis.md` | T06 | Failure analysis: sparse sampling, mixed units, no attribution, control, benchmark-scale evidence, wording for the paper |
| `docs/plan/workstreams/WS06-baselines/notes/fairness-audit.md` | T07 | Generated knowledge matrix, checks, documented asymmetries, findings, conclusion for WS08-T02 |

## Dependencies

- Upstream tasks (INDEX, unchanged): WS05-T01 (scaffolding), WS04-T01 (trace schema), WS01-T03 (parameter registry), WS05-T03 (spec package), WS05-T05 (forecaster), WS05-T06 (conformal calibrator). Inside the workstream: T02 to T06 need T01; T07 needs T02 to T06.
- Downstream: WS08-T01 (runner: `Detector` names, timing and operating-parameter conventions from the harness), WS08-T02 (main experiment; runs only after T07; should cite `notes/B5-failure-analysis.md` and add benchmark-scale numbers if T06 could not), WS12 (experiments section and the difference sentence to Lindemann et al.).
- Edges the code needs but INDEX does not declare (recorded here, `depends_on` left unchanged; each task says to stay blocked until the missing piece exists):
  - T01: `Detection`, `AttributedCause` and `EvidenceVector` are exported by `ralmon.attribution` (WS05-T07), and `CarePlan`, `TemplateInstance`, `ParameterRegistry` by `ralmon.spec` (WS05-T03); neither is a declared dependency.
  - T02: `SignalId` and `EventKind` from `ralmon.signals` (WS05-T02).
  - T04 and T06: the raw-robustness entry point may live in `ralmon.monitor` (WS05-T04) instead of `ralmon.spec`.
  - T05 and T06: both use a `Forecaster` (WS05-T05); only T03 declares it. `Forecaster` and `Forecast` are not in the public API table of `02-interfaces.md`.
  - T06: the human-supplied PDF, delivered by WS00-T08 (reconciliation, ADR-023).
- Contract anchors used: `02-interfaces.md#detector`, `#trace-schema`, `#forecaster`, `#template`, `#conformal-calibrator`.

## Acceptance criteria

1. `python -c "from ralmon.baselines import Detector, B1StaticThresholds, B2AnomalyDetection, B3PlainSTL, B4ConformalOnly, B5ConformalSTL"` exits 0.
2. `pytest tests/baselines -q`, `ruff check src tests` and `mypy src/ralmon` exit 0.
3. Every baseline is a `BaselineBase` subclass whose `fit` and `run` signatures match the `Detector` protocol; `run` given a `BenchmarkDay` or `LatentDay` raises `LeakageError`.
4. `grep -lE 'LatentDay|GroundTruthEvent' src/ralmon/baselines/b[1-5]_*.py src/ralmon/baselines/raw_robustness.py src/ralmon/baselines/base.py` prints nothing.
5. `grep -rnE '\b(110|140)\b' src/ralmon/baselines` prints nothing (no clinical constants in `src/`; illustrative values live in tests only).
6. B5 non-negotiable checks: `notes/B5-deviations.md` exists and every bullet under its `## Published method as read` heading carries `locator:`; `notes/B5-failure-analysis.md` has the headings `## Sparse sampling`, `## Mixed units`, `## No attribution`, `## Control: where B5 works`, `## Benchmark-scale evidence`; `pytest tests/baselines/test_b5_failure_modes.py -q` exits 0.
7. `notes/fairness-audit.md` exists with the headings named in WS06-T07, its knowledge matrix equals the regenerated one (`test_knowledge_matrix_is_generated`), and `grep -nE '^- F[0-9]+ \[open\]' docs/plan/workstreams/WS06-baselines/notes/fairness-audit.md` prints nothing.
8. Each task file has the six template headings and its frontmatter matches the INDEX row: `python3 tools/check_plan.py` exits 0 once the verifier exists.
9. The forbidden-token scan of rule 5 of `docs/plan/workstreams/AUTHORING-BRIEF.md` finds nothing under `docs/plan/workstreams/WS06-baselines`.

## Source sections

- analisi §5.4 (baseline table B1 to B5), §5.5 (metrics computed on their `Detection` outputs), §5.6 (ablations use the same `Detector` contract).
- analisi §3.2 (Lindemann et al. 2023 as the closest work, risk "MOLTO ALTO") and §10 objection 2 (B5 must show at least one failure); §10 objection 1 (same clinical knowledge; latent ground truth not visible to any method).
- analisi §4.1 to §4.4 (templates, normalisation, conformal score and caveats) for what B3 to B5 deliberately omit; §4.3 (blood pressure is a poor forecasting target) for B2 and B4 signal choices.
- analisi §9 item 6 (B1 to B5, 2 to 3 pw, depends on item 4; "Non tagliate B5") and `docs/source/review.md` (R2 weakness 8, meta-review item 3).

## Tasks

| id | title | owner | status | depends_on |
|---|---|---|---|---|
| WS06-T01 | Detector protocol implementation and common harness | agent | blocked | WS05-T01, WS04-T01, WS05-T03, WS05-T07 |
| WS06-T02 | B1 static thresholds with simple schedule logic | agent | blocked | WS06-T01, WS01-T03, WS05-T02 |
| WS06-T03 | B2 anomaly detection (forecast residual and isolation forest) | agent | blocked | WS06-T01, WS05-T05 |
| WS06-T04 | B3 STL without uncertainty (raw robustness on measured values) | agent | blocked | WS06-T01, WS05-T03, WS05-T04 |
| WS06-T05 | B4 conformal without STL | agent | blocked | WS06-T01, WS05-T06, WS05-T05 |
| WS06-T06 | B5 conformal STL predictive monitoring after Lindemann et al. 2023, with failure analysis | agent | blocked | WS06-T01, WS05-T03, WS05-T06, WS05-T04, WS05-T05, WS00-T08 |
| WS06-T07 | Baseline fairness audit | agent | blocked | WS06-T02, WS06-T03, WS06-T04, WS06-T05, WS06-T06 |
