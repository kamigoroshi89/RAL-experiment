# WS08-experiments: Experiments

## Objective

Run the evaluation of analisi §5 on the semi-synthetic benchmark of WS04 (200 virtual patients x 7 days = 1400 patient-days, split by patient, at least 5 seeds, bootstrap confidence intervals over patient-days; analisi §5.1) and produce every number that WS09 and WS12 will cite, only through `outputs/<experiment_id>/<seed>/{config.yaml, metrics.json, git_rev.txt}`.

The workstream delivers the metrics module and the experiment runner in `src/ralmon/eval/` (T01), the main comparison of B1-B5 against the proposed method (T02), the ablations A1, A2, A3, A5 and A7 (T03), ablation A4 (T04), the distribution-shift test with ablation A6 (T05), the unlabeled real-data run (T06) and the reproducibility check with result freeze (T07). Experiment configurations live in `experiments/*.yaml`, one YAML per experiment.

The experiments answer the three residual objections of analisi §10: the circular semi-synthetic evaluation (objection 1: ground truth from the latent trace, identical clinical knowledge for the baselines, alert load on real data), the incremental-application objection (objection 2: B5 with a shown failure, or an honest statement that none was found) and "why a robot?" (objection 3: ablation A4). **WS08-T04 (ablation A4) is NON-NEGOTIABLE** (analisi §5.6 and §9: "Non tagliate B5, A4 né la formalizzazione"); it is not on the cut list of `00-master-plan.md` section 7 and it is scheduled immediately after T02. Validation is technical and pre-clinical on semi-synthetic data with literature priors (ADR-001, ADR-005).

## Inputs

- Contracts (read in full by each task that cites them): `02-interfaces.md#metrics` and `#experiment-config-and-outputs` (owned here); `#detector`, `#trace-schema`, `#monitor`, `#verdict`, `#alert`, `#conformal-calibrator`, `#forecaster`, `#evidencevector`, `#attribution`, `#priorsource`, `#template`, `#parameter-registry` (read only).
- ADRs: ADR-001 (scope), ADR-002 (C3 as integrity violations, undetectable rows are results), ADR-003 (ward node plus robot), ADR-004 (DISPENSE versus INTAKE), ADR-005 (literature priors first), ADR-007 (past-time formulation, basis of A7), ADR-008 (conformal only in PENDING), ADR-009 (normalisation, basis of A3), ADR-010 (attribution with abstention), ADR-016 (toolchain), ADR-017 (integer milliseconds), ADR-020 (unverified clinical parameters).
- Upstream artefacts: benchmark builder, manifest and loader (WS04-T11, WS04-T10 ground-truth labeller, WS04-T12 alert-load check, WS04-T13 for MIMIC and eICU priors); `run_offline`, calibrators, forecaster and `Attributor` (WS05-T04 to WS05-T08); baselines B1-B5, harness and fairness audit (WS06-T01 to WS06-T07); `docs/models/evidence-channels.md` and `configs/diagnosability.yaml` (WS02-T03, WS02-T05); parameter registry `configs/registry/hypertension.yaml` (WS01-T03); credentialing status `docs/plan/workstreams/WS00-admin/outputs/WS00-T04.md` (`access_status:` lines).
- `docs/source/analisi.md` §5.1, §5.4, §5.5, §5.6, §5.8, §4.3, §4.4, §4.5, §4.8, §10 and `docs/source/review.md` (R2 weaknesses 1, 4, 5, 9; R3 weaknesses 1, 2, 6; meta-review).

### Assumptions about upstream deliverables

The INDEX and the contracts leave five points open. WS08-T01 step 1 checks each against the completion notes of the upstream tasks and records any mismatch in its own completion note. A mismatch changes only the adapter code named below, never a metric definition.

1. **First decidable instant.** `GroundTruthEvent` has no such field. Convention used here: for a C1 event on a windowed obligation (`RESP`, `SCHED`, day-end `COUNT`) WS04-T10 stores the obligation deadline in `end_ms`; for every other event the first decidable instant is `onset_ms`. One function, `first_decidable_ms`, encodes this (T01).
2. **The proposed method as a `Detector`.** No INDEX task builds a `Detector` named `ours`; WS05-T08 delivers `run_offline`. T01 builds the thin adapter `OursDetector` from public APIs (`run_offline`, `SplitConformal`, `AdaptiveConformal`, `Attributor`, `HierarchicalRule`) and exposes a public factory `build_detector` (WS09-T03 needs it to re-run one day).
3. **Evidence per violated record.** `Detector.run(day, plan, evidence)` receives a `Mapping[str, EvidenceVector]`. The function that extracts it from an `ObservedDay` is expected in WS05-T07 or in the WS06-T01 harness; T01 records its name.
4. **Care plans.** `ObservedDay.care_plan_id` resolves to a `CarePlan` through the WS04-T11 loader.
5. **Diagnosability matrix.** `configs/diagnosability.yaml` has one row per event type, a `subtype:` key that joins to `GroundTruthEvent.subtype`, the declared limits DX-04 (silent cuff bias) and DX-10 (informed attacker), and an A4 outcome per row (WS02 README, acceptance criteria 3 to 5). The exact key names are those of the WS02-T05 schema; WS08 reads them through its loader and never re-types them.

## Outputs

| Output | Task | Consumers |
|---|---|---|
| `src/ralmon/eval/{metrics,runner,ours}.py`, public API of `ralmon.eval` | T01 | WS06, WS09-T01, WS09-T03, WS10-T06, WS11-T06 |
| `experiments/main.yaml`, `outputs/main/<seed>/...`, `src/ralmon/eval/analysis.py` | T02 | WS09-T03, WS09-T05 (Table II), WS12-T05 |
| `experiments/A1.yaml`, `A2.yaml`, `A3.yaml`, `A5.yaml`, `A7.yaml`, `outputs/A<k>/...`, `ablations.py`, `future_time.py` | T03 | WS09-T05 (Table III) |
| `experiments/A4.yaml`, `outputs/A4/...`, `embodied.py` | T04 | WS09-T05 (Table III), WS12-T04, WS12-T05 |
| `experiments/shift.yaml`, `A6.yaml`, `outputs/shift/...`, `outputs/A6/...`, `shift.py` | T05 | WS09-T05 (Fig. 3, Table III) |
| `experiments/unlabeled-real.yaml`, `main-mimic.yaml`, `outputs/unlabeled-real/...`, `realdata.py` | T06 | WS12-T05, WS12-T06 |
| `experiments/results.lock.json`, `src/ralmon/eval/freeze.py` | T07 | WS12-T05, WS13-T02 |

### Experiment ids

| id | Detectors (names of the Detector contract) | Question |
|---|---|---|
| `main` | B1, B2, B3, B4, B5, ours | Per-class detection, delay, false alarms, coverage, attribution against baselines with identical clinical knowledge |
| `A1` | ours, ours-A1 | Conformal replaced by point forecast: more predictive false alarms, uncalibrated rho |
| `A2` | ours, ours-A2 | No forecaster: no early warning, same definitive verdicts |
| `A3` | ours, ours-A3, ours-A3-prio | No normalisation of sigma: worse alert ordering |
| `A4` | ours, ours-A4, ours-A4-witness-only, ours-A4-avail-\<f\> | Embodied channel removed: loss of kappa on robotic C2 and forged DISPENSE (the "why a robot?" answer) |
| `A5` | ours, ours-A5 | No RESP and HOLD templates: recall on non-response and hypotension |
| `A6` | ours, ours-A6 | Split (ours) versus adaptive conformal under shift |
| `A7` | ours, ours-A7 | Past-time versus delayed future-time formulation |
| `shift` | B4, B5, ours | Empirical coverage in distribution and under shift (synthetic first, cohort shift when WS04-T13 exists) |
| `unlabeled-real` | B1, ours | Alert load per patient-day on real unlabeled episodes (T06, blocked) |
| `main-mimic` | as `main` | Key experiment repeated with MIMIC priors (ADR-005; T06, blocked) |

`ours` is the split conformal calibrator variant. Ablation variants are `Detector`s named `ours-<id>`, so every ablation is a paired comparison with the full method on identical days, splits and seeds.

### metrics.json layout (reading contract for WS09)

Top-level keys are the eleven metric names of `#metrics` (`per_class_prf`, `detection_delay_ms`, `false_alarms_per_patient_day`, `recall_vs_false_alarm_curve`, `empirical_coverage`, `mean_interval_width`, `expected_calibration_error`, `attribution_confusion`, `accuracy_vs_coverage`, `latency_percentiles`, `severity_rank_agreement`) plus two reserved non-metric keys, `meta` and `analysis`. Under each metric name the next key is the detector name; a metric that does not apply to a detector is `null` (never `NaN`, never omitted).

- `meta`: `experiment_id`, `seed`, `n_test_patients`, `n_test_patient_days`, `detectors` (ordered), `match` (`tolerance_ms`, `time_reference`), `alpha`, `alpha_grid`, `prior_source`, `coverage_qualifier` (the sentence "marginal over patient episodes under exchangeability; calibration unit: patient episode"), `bootstrap` (`n_resamples`, `level`, `unit: "patient_day"`).
- Scalar leaf ("S"): `{"value", "ci_lo", "ci_hi", "ci_cluster_lo", "ci_cluster_hi"}`; `ci_*` is the bootstrap over patient-days required by the contract, `ci_cluster_*` the bootstrap over patients (days of one patient are correlated, so the cluster interval is the conservative one). `value` is `null` when undefined (for example precision with no detection and no match).
- `per_class_prf.<det>.<C1|C2|C3|any>.<precision|recall|f1>` are S. Detection is label-agnostic (see E3).
- `detection_delay_ms.<det>`: `n_matched`, `values_ms` (sorted list), `p05`, `p25`, `p50`, `p75`, `p95`, `mean` (S), `fraction_early` (S, share of negative delays).
- `false_alarms_per_patient_day.<det>`: S plus `n_false_alarms` and `duplicates_per_patient_day`.
- `recall_vs_false_alarm_curve.<det>`: list of `{"alpha", "false_alarms_per_patient_day", "recall"}`; one entry with `alpha: null` for detectors without alpha.
- `empirical_coverage.<det>.<condition>`: list over the alpha grid of `{"alpha", "nominal", "alert_level", "band_level"}`; `condition` is `in_distribution` or `shift_<level_id>`. `mean_interval_width.<det>.<condition>` has the same shape with `value`.
- `expected_calibration_error.<det>`: S plus `bins` and `reliability_bins` (`lo`, `hi`, `n`, `mean_rho`, `observed_rate`).
- `attribution_confusion.<det>`: `matrix` (rows C1, C2, C3; columns C1, C2, C3, UNDETERMINED), `macro_f1` (S), `abstention_rate` (S), `accuracy_answered` (S). `accuracy_vs_coverage.<det>`: list of `{"coverage", "accuracy"}`.
- `latency_percentiles.<det>`: `p50`, `p95`, `p99` of logical verdict latency in trace time.
- `per_template.<det>` (WS08-T08, ADR-072 (b); additive, `null` for a detector it does not apply to): `templated`, `templates.<RANGE|SCHED|HOLD|COUNT|SYS|INT>`, `resp` and `aggregate`. A template block is `{n_events, n_matched, precision (S|null), precision_pooled_fa (S), recall (S), f1 (S|null), delay_ms: {n_matched, mean (S), fraction_early (S)}}`; a template without a truth event is `{n_events: 0, n_matched, precision: null, precision_pooled_fa: null, recall: null, f1: null, delay_ms: null}`, never 0. The template of a C1 event is its `template_id`. **SYS counts the C2 events and INT the C3 events: class proxies** (the ground truth gives C2 and C3 events no template), not the violations of the SYS and INT templates; the SYS and INT blocks carry `class_proxy: true`. `precision` and `f1` exist only for a detector whose detections carry a template (`templated: true`: the proposed method, whose alerts have `tau`): `TP_t / (TP_t + FA_t)` with `FA_t` the unmatched alerts of template t outside every injection footprint; for B1 to B5 (plain detections) they are `null`. `precision_pooled_fa` is `TP_t / (TP_t + FA)` with the false alarms pooled over all templates, true positives counted anywhere and false alarms only outside the footprints: it depends on the number of events of the template as much as on the detector, and it never enters an aggregate F1. For a template WITH events, recall, precision and F1 are 0 when it has no true positive (never missing). `resp` is the block of RESP, reported apart: it does NOT enter `aggregate`. `aggregate` is `{templates, templates_with_events, weights: "equal", precision (S|null), recall (S), f1 (S|null), delay_ms_mean (S)}`: the plain mean of the template values with each template weighted 1 (not the pooled ratio); every leaf lists the exact templates it averaged in `templates_averaged` (recall, precision and F1: the templates with events; the delay: those with at least one match). Aggregate precision and F1 are `null` for a plain detector; aggregate recall and delay exist for every detector. `meta.aggregate` states the set, the weights, why RESP is excluded (`excluded_reason`, ADR-072), the class proxies, `average_rule` and `precision_rule`.
- `background.<false_alarms_per_patient_day|excess_over_background>.<det>` (WS08-T08, ADR-071 (b), (f); additive): `false_alarms_per_patient_day` is S plus `n_false_alarms_background`, `n_false_alarms_in_footprint` and `exposure_patient_days`: the false alarms OUTSIDE every injection footprint per patient-day of time outside every footprint (natural events are truth, a noise alarm is a false alarm; an unmatched detection inside a footprint is counted apart, in neither rate). The footprint of a C2 or C3 record is its window (a replay on the receive axis, `t_rx`), of a C1 record its window plus the finite tail `run_options.background.c1_footprint_tail_ms` (`awaiting_human_value` until a human sets it: then the window only, flag `C1_FOOTPRINT_TAIL_AWAITING`, hard failure of a headline run), widened on both sides by `footprint_margin_ms` (default: the matching tolerance); it also holds the events a record explains in a later day. `excess_over_background.<det>.<subtype>` for each injected C1 subtype with a footprint (the template of the subtype comes from the static link table of the labeller, `LINK_TABLE`; `template: null` and null leaves for a subtype the table does not know): `{template, events_per_record (S), detected_per_record (S), recall (S), events_per_patient_day (S), detected_per_patient_day (S), counts, note}`. The headline figures are `events_per_record` and `detected_per_record`, the excess COUNT per injection record: `(events in the footprints - background rate x exposure in the footprints) / records`, the background rate being the rate of the events of the template outside every footprint; `recall` is the recall inside the footprints minus the recall outside; the `per_patient_day` figures are secondary and depend on the footprint length (the C1 tail and the margin). Of the excess leaves only the cluster intervals `ci_cluster_lo` and `ci_cluster_hi` are usable. The counterfactual is the natural rate in the windows without injections, which ignores the time-of-day structure (natural RANGE and HOLD events cluster near the dosing times): it is a fair counterfactual only if the injection windows are placed like the rest of the day. The block is `{}` when the benchmark has no injected C1 record. `meta.background` records the tail (value, status, reason), the margin and its source and the two notes; `analysis.run.background` holds what does not depend on the detector (number of records and footprints, exposure, events and natural events per patient-day by template).
- `analysis`: free-form diagnostics per experiment; the keys each experiment must provide are listed in `run_options.required_analysis` of its YAML and checked by `python -m ralmon.eval.analysis --check` and by T07.

Files are written with sorted keys, two-space indent, a final newline, no `NaN` or `Infinity` tokens.

### Evaluation conventions (binding for T01 to T07)

- **E1 Unit and split.** The unit is the patient-day. Every split is by patient (`02-interfaces.md#trace-schema` rule 2). A seed re-draws the patient-level split and all model randomness (forecaster, isolation forest, calibrators, bootstrap, availability sweep); the benchmark version is the one named by `benchmark_manifest`. Headline experiments list seeds `[0, 1, 2, 3, 4]` or more.
- **E2 Random streams.** `numpy.random.default_rng([seed, STREAM])` with one named integer constant per component (split, forecaster, calibration, bootstrap, availability sweep), never one generator shared between components, so that adding a metric cannot shift another stream (`01-conventions.md` section 2).
- **E3 Matching.** Per patient-day and one-to-one. A detection matches a ground-truth event when `|t_det - t_ref| <= tolerance_ms`, with `t_ref = onset_ms` or `first_decidable_ms(event)` according to `MatchConfig.time_reference`. For each event, in onset order, the earliest unmatched detection in the window is matched (so an early warning is the matched detection); later detections in the same window are `duplicates` (neither true positive nor false alarm); detections matching nothing are false alarms and count in full (no deduplication outside the window), because that is what a nurse receives. Detection is label-agnostic, so every detector has per-class values: `TP_c` counts matched events of class c, `precision_c = TP_c / (TP_c + FA)`, `recall_c = TP_c / GT_c`, `f1_c` their harmonic mean (0 when `TP_c = 0` and the denominator is defined). Undefined ratios are `null`.
- **E4 Attribution.** Computed on matched pairs only. The confusion matrix has rows C1, C2, C3 and columns C1, C2, C3, UNDETERMINED. `macro_f1` averages F1 over the classes that appear in a row or a column; UNDETERMINED is an abstention: a false negative for the true class, never a false positive. `abstention_rate` is the UNDETERMINED share of matched pairs. The accuracy-versus-coverage curve of a rule-based attributor has one operating point per condition (no per-alert confidence exists in the contract); curves are assembled over conditions (A4 availability sweep).
- **E5 Bootstrap.** Resample test patient-days with replacement, recompute the metric, percentile interval. Ablation differences use the paired bootstrap on the same resampled days. Number of resamples and level are declared in `run_options` and stored in `meta.bootstrap`. Across-seed spread is reported separately by WS09, never merged into the bootstrap.
- **E6 Coverage.** Coverage is marginal over the population under exchangeability of patient episodes and is stated so wherever reported (analisi §4.8: coverage is never claimed without its qualifiers). `alert_level` is the empirical form of Proposition 1, `1 - P(alert emitted and sigma >= 0)`, compared with the nominal `1 - alpha`; `band_level` is `P(sigma_true <= sigma_hat + q)`. The truth is `sigma_true` of the episode, the normalised robustness of the completed measured trace (ADR-008), not the latent trace. Alpha grids satisfy `alpha >= 1 / (n_cal + 1)` for `n_cal` calibration episodes, otherwise the finite-sample quantile does not exist.
- **E7 rho.** Reliability and ECE cover PREDICTED alerts only; the outcome is the definitive VIOLATED verdict on the measured completed trace; bins are equal-width on [0, 1]. Proposition 1 is a marginal guarantee, not a promise that rho equals P(violation | alert); a large ECE is a finding to report, not a contradiction, and rho is never re-mapped to improve it.
- **E8 Determinism.** `metrics.json` holds only deterministic quantities. Wall-clock measurements are excluded (they belong to WS07-T07); "latency" here is logical verdict latency in trace time. The same config and seed give byte-identical files on the same machine (`01-conventions.md` section 3).
- **E9 No test-split tuning.** Tolerance, alpha grid, split fractions, monitor step and any hyperparameter are fixed from the train and calibration splits and the registry, written in the YAML header comment, and committed before the first run on the test split. `git_rev.txt` is the revision of that run; frozen results (T07) come from a clean tree.
- **E10 Labels.** Results carry `meta.prior_source` (`literature` until WS04-T13 exists). Values from the parameter registry without `reviewed_by` are reported as unverified (ADR-020).

## Dependencies

- Upstream workstreams: WS04 (T11 builder; T10 labeller; T12 alert-load check; T13 MIMIC and eICU priors, needed only by the guarded parts of T05 and by T06), WS05 (T04 monitor, T06 calibrators, T08 `run_offline`; T07 attribution reached through T08), WS06 (T01 harness, T06 B5, T07 fairness audit), WS02 (T03 evidence channels, T05 diagnosability matrix), WS01 (registry and templates), WS00-T04 (credentialing status). Robot-deadline forecast results come from WS07-T06 and are cited, not recomputed.
- Downstream: WS09-T01 reads the layout above (metric-first, `meta`, `analysis`); WS09-T03 uses `build_detector` and `outputs/main/<seed>/config.yaml`; WS09-T05 reads `main`, `A1` to `A7`, `shift`; WS12-T05 and WS13-T02 read the freeze record. WS10-T06 and WS11-T06 import metric functions.
- Contract anchors: owns `02-interfaces.md#metrics` and `#experiment-config-and-outputs`; reads `#detector`, `#trace-schema`, `#monitor`, `#verdict`, `#alert`, `#conformal-calibrator`, `#forecaster`, `#evidencevector`, `#attribution`, `#priorsource`, `#template`, `#parameter-registry`. No task edits a contract; gaps are listed in the final report of the planning run and, if accepted, go through an ADR (`01-conventions.md` section 6).
- Missing INDEX dependency: T05 contains a cohort-shift step that needs WS04-T13 (ADR-005) but does not list it. The step is written as a guarded addendum (see T05) so the task can close on synthetic shift alone.

## Acceptance criteria

1. `pytest tests/eval -q`, `ruff check src tests` and `mypy src/ralmon` exit 0.
2. For every id in `main A1 A2 A3 A4 A5 A6 A7 shift`: `ls outputs/<id>/*/metrics.json | wc -l` prints at least 5, and each seed directory holds `config.yaml`, `metrics.json` and `git_rev.txt`.
3. `python -m ralmon.eval.freeze --check --rerun` exits 0: re-running every headline config reproduces every `metrics.json` byte for byte, and `experiments/results.lock.json` matches.
4. `grep -rl 'NaN' outputs/*/*/metrics.json` prints nothing; top-level keys of every `metrics.json` are metric names of `#metrics` plus `meta` and `analysis` (test `test_metrics_json_top_level_keys`).
5. A4 is present with at least 5 seeds and each `outputs/A4/<seed>/metrics.json` contains `analysis.delta_vs_full` (with paired bootstrap intervals for C2 and C3 and per subtype), `analysis.embodied_temporal_coverage` and `analysis.availability_sweep`.
6. Parts that cannot run yet are recorded, not omitted: `analysis.cohort_shift.status` in `outputs/shift/<seed>/metrics.json` and the `not_run` block of `experiments/results.lock.json` name the blocking task (WS04-T13) when T05 or T06 could not be completed.
7. Every claim of the honest-reporting rules below has its `analysis` key present, checked by `python -m ralmon.eval.analysis --check outputs/main outputs/A1 outputs/A4` (exit 0).
8. No number of the paper is typed by hand: WS09 and WS12 read `outputs/` (checked in their own workstreams).

### Honest-reporting rules

These rules bind T02 to T07. A result that contradicts a hypothesis of analisi §5.6 is reported and the claim is reworded (analisi §4.8); it is never dropped, re-tuned on the test split or moved to an appendix without mention.

- **H1 Blood-pressure forecasting.** For every forecast target (blood pressure, heart rate, SpO2) report horizon, error, mean conformal interval width in sigma-tilde units and the fraction of intervals that straddle the decision boundary, with the blood-pressure row always present. Blood pressure with about five measurements per day is expected to be uninformative (analisi §4.3; R2 weakness 5); if it is, the paper says so and restricts the predictive claim to continuous signals and robot deadlines. If it is unexpectedly informative, check for leakage before reporting.
- **H2 B5.** Report the conditions where B5 is worse than the proposed method, with numbers and paired intervals: sparse sampling, mixed units, no attribution (analisi §5.4). If no measured condition shows B5 worse, report exactly that (`b5_failure_found: false`) and correct the novelty claim (analisi §10 objection 2). B5 is tuned with the same care and the same clinical knowledge as the proposed method (WS06-T07 audit).
- **H3 Undetectable rows.** Every row of the diagnosability matrix appears in the results with its measured recall and attribution, including the rows declared not distinguishable (DX-04 silent cuff bias, DX-10 informed attacker) and the partial or conditional rows. A row with no events in the test split is listed as such. If a method appears to solve a row declared undetectable by construction, investigate leakage before reporting (analisi §10 objection 4, ADR-002).
- **H4 Null and negative results.** A2 is expected to leave definitive verdicts unchanged and A7 to give equivalent verdicts; disagreements are listed. If A4 shows no gain whose interval excludes 0 for C2 and C3, that is reported and the "embodiment as a safety asset" wording is changed (analisi §4.8).
- **H5 Seeds and intervals.** Headline numbers come from at least 5 seeds with bootstrap intervals; single-seed numbers are never quoted; per-seed spread is shown.
- **H6 Ground truth and scope.** Ground truth is defined on the latent trace; detectors receive an `ObservedDay` only (asserted at run time). Every result is labelled "semi-synthetic, literature priors, pre-clinical technical validation" until WS04-T13 results exist.
- **H7 Coverage wording.** Coverage is always stated as marginal, under exchangeability of patient episodes, with the calibration unit named, in distribution and under shift.
- **H8 Matching declared.** The tolerance window and matching rules are declared and results are shown for half and double the tolerance (T02).
- **H9 Alert load.** False alarms and total alerts per patient-day are reported for every detector (alarm fatigue, R3 weakness 6); the per-shift figure is given only with a shift length supplied by the clinician (WS00-T07), never assumed.

## Source sections

- analisi §5.1 (scale, seeds, ground truth on the latent trace, unlabeled real run), §5.4 (B1-B5, B5 failure), §5.5 (metrics), §5.6 (ablations A1-A7, A4 strategic), §5.8 (indispensable elements), §9 item 8 (roadmap: main experiments, A1-A6, shift, unlabeled run; 3 pw) and the "do not cut" sentence.
- analisi §4.3 (blood pressure is a poor forecasting target), §4.4 (rho, Proposition 1, alpha allocation), §4.5 (diagnosability matrix), §4.8 (claim reformulations), §10 objections 1 to 4.
- analisi §2 (`review.md`): R2 weaknesses 1, 4, 5, 9; R3 weaknesses 1, 2, 6; meta-review points 1 and 4.

## Tasks

| id | title | owner | status | depends_on |
|---|---|---|---|---|
| WS08-T01 | Experiment runner, config and metrics module | agent | blocked | WS04-T11, WS06-T01, WS05-T08, WS05-T11 |
| WS08-T02 | Main experiment: B1-B5 versus proposed method | agent | blocked | WS08-T01, WS06-T07, WS04-T16, WS08-T08 |
| WS08-T03 | Ablations A1, A2, A3, A5, A7 | agent | blocked | WS08-T02 |
| WS08-T04 | Ablation A4: embodied channel removed | agent | blocked | WS08-T02, WS02-T05 |
| WS08-T05 | Distribution shift and A6: split versus adaptive conformal | agent | blocked | WS08-T02 |
| WS08-T06 | Unlabeled real-data run for alert load (blocked until access) | agent | blocked | WS08-T02, WS04-T13 |
| WS08-T07 | Reproducibility check and result freeze | agent | blocked | WS08-T03, WS08-T04, WS08-T05 |
| WS08-T08 | Per-template metrics, equal-weight aggregate without RESP, false alarms outside injection windows (ADR-071 (b), ADR-072 (b)) | agent | done | WS08-T01 |
| WS08-T09 | Metrics for probabilistic attribution: log score, Brier, calibration curves, pair likelihood ratio, McNemar on direction (ADR-074) | agent | ready | WS08-T08, WS02-T06, WS05-T14 |
