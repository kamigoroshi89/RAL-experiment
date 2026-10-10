---
id: WS06-T07
title: Baseline fairness audit
workstream: WS06-baselines
owner: agent
status: blocked
depends_on: ["WS06-T02", "WS06-T03", "WS06-T04", "WS06-T05", "WS06-T06"]
critical_path: true
non_negotiable: false
estimate_pd: 1
sources: ["analisi §10 (1)", "analisi §5.4", "analisi §4.4", "analisi §10 (2)"]
interfaces: ["02-interfaces.md#detector"]
review_items: []
---
## Obiettivo

Audit B1 to B5 against the objection "the evaluation is circular: whoever writes the specification wins" (analisi §10 objection 1). Show, by tests and by a written note, that every baseline receives the same clinical knowledge as the proposed method (bands and schedules for B1, all templates for B3 and B5), sees the same inputs at the same time, never reads a latent trace or ground truth at inference, and is calibrated and tuned only on data the proposed method may also use. Concrete output: `src/ralmon/baselines/audit.py`, `tests/baselines/test_fairness_audit.py` and `notes/fairness-audit.md` with a knowledge matrix generated from access logs (not typed by hand), the documented asymmetries and the resolved findings. WS08-T02 runs the main experiment only after this audit passes.

## Contesto

- `02-interfaces.md#detector` (rules: same clinical knowledge; no `LatentDay` or `GroundTruthEvent`; `fit` may use ground truth from training days only) and `02-interfaces.md#conformal-calibrator` (`CalibrationEpisode.sigma_true` is "latent or measured": the audit must find out which the proposed method uses).
- `src/ralmon/baselines/`: the harness (`access.py`, `base.py`) and the five baselines with their module docstrings and completion notes.
- `docs/plan/workstreams/WS06-baselines/notes/B5-deviations.md` (the B5 choices to be audited).
- `docs/source/analisi.md` §10 objection 1 (prevention list), §5.4 (what each baseline is meant to show), §4.4.
- Blocked until WS06-T02 to WS06-T06 are `done`. The proposed method's monitor and calibrator (WS05-T04, WS05-T06) exist by then because B3, B4 and B5 depend on them.

## File toccati

- `src/ralmon/baselines/audit.py` (create)
- `tests/baselines/test_fairness_audit.py` (create)
- `tests/baselines/conftest.py` (modify: add fixtures `all_baselines`, `poisoned_benchmark_days`, `full_plan`)
- `docs/plan/workstreams/WS06-baselines/notes/fairness-audit.md` (create)

## Test

Write these first. `all_baselines` builds B1 to B5 from one timing configuration, stub forecaster and stub calibrator factory, with `AuditedRegistry` and logged plans; `full_plan` holds one instance of each of the seven templates with test-local parameter values (illustrative, unverified); `poisoned_benchmark_days` are `BenchmarkDay` objects whose latent trace and ground truth raise on any access. Parametrised over B1 to B5 unless stated. The knowledge set K of the proposed method is the union, over the loaded templates, of `params`, `scale_param`, `priority_param` and `max_verdict_latency_param`.

1. `test_baselines_exported_and_named`: `ralmon.baselines` exports `Detector` and the five classes; names are `B1` to `B5` (component and variant names such as `B2-residual` or `B5-per-template` are allowed only as documented suffixes).
2. `test_shared_timing_configuration`: all five baselines carry the same `step_ms` and `reorder_delay_ms`, equal to those of the `MonitorConfig` used for the proposed method in the same experiment config, and the same `tail_ms`.
3. `test_no_latent_or_ground_truth_at_inference`: with the poisoned days, `fit` then `run(day.observed, ...)` succeeds; the `AccessLog` has no `latent` read on either split and no `ground_truth` read on calibration days; `run` given a `BenchmarkDay` or `LatentDay` raises `LeakageError`.
4. `test_evidence_and_labels`: output is identical with `evidence=None` and with a populated mapping; every `label` is `None`; every `score` is finite.
5. `test_knowledge_is_subset_of_proposed_method`: the names read through the logged plan and `AuditedRegistry` during `run` are a subset of K.
6. `test_b1_receives_bands_and_schedules`: B1's read set contains the band, hold, schedule-window and dose-limit parameters that its docstring declares (analisi §10 objection 1: "bande e schedule per B1").
7. `test_b3_receives_all_templates_without_normalisation`: B3's read set contains every `Template.params` name of the instantiated templates and no `scale_param` or `priority_param` name.
8. `test_b5_knowledge_equals_b3_knowledge`: B5's read set equals B3's (same templates, raw robustness).
9. `test_b2_and_b4_read_no_clinical_thresholds`: their read sets over `param_values` and the registry are empty; B2 uses `plan.schedule` only.
10. `test_calibration_target_is_shared`: no baseline reads `latent` on calibration days under the default `AccessPolicy`; the proposed method's calibration-episode construction (read in `src/ralmon/conformal` and the WS08 or WS05 code that builds `CalibrationEpisode`) uses observed traces only, or, if it uses latent traces, the test fails and the finding is written up (see Passi step 5).
11. `test_residual_definitions_agree`: on one fixture with the persistence stub, the residual series computed by B2 and by B4 are equal.
12. `test_b3_detection_time_equals_monitor_violation_time`: on a one-violation day (BP outside the band), the B3 detection time equals the `t_eval_ms` of the first `VIOLATED` record of `run_offline` under the same timing configuration; a documented, justified difference is written into the note and the assertion changed to the documented relation.
13. `test_hyperparameter_selection_documented`: `"Hyperparameter selection" in cls.__doc__` for each class.
14. `test_operating_parameters_have_no_numeric_defaults`: `alpha`, `z_threshold` and `score_quantile` have no numeric default in the constructors that have them.
15. `test_conformal_baselines_monotone_in_alpha`: on a fixture day, detections of B4 and of B5 at `alpha = 0.05` are a subset of those at `alpha = 0.2`.
16. `test_baseline_sources_do_not_touch_latent_types`: the source files `b1_*.py` to `b5_*.py` and `raw_robustness.py` contain neither `LatentDay` nor `GroundTruthEvent`.
17. `test_audit_note_complete`: `notes/fairness-audit.md` has the headings `## Scope and method`, `## Knowledge matrix`, `## Checks`, `## Documented asymmetries`, `## Findings`, `## Conclusion for WS08-T02`; no finding line matches `^- F[0-9]+ \[open\]`.
18. `test_knowledge_matrix_is_generated`: the text between the markers `<!-- matrix:start -->` and `<!-- matrix:end -->` in the note equals `render_markdown(run_audit(...))` on the audit fixtures (the matrix is regenerated, never typed by hand).

## Passi

1. Verify unblock conditions; read the completion notes of WS06-T02 to WS06-T06 and `B5-deviations.md`. Branch `ws06-t07-baseline-fairness-audit`; `status: in_progress`.
2. Read how the proposed method builds its `CalibrationEpisode`s (which trace gives `sigma_true`) and which `MonitorConfig` values it uses. Write down the result; test 10 hinges on it.
3. Write fixtures and the 18 tests; run them; watch them fail.
4. Implement `audit.py`: `KnowledgeRow` (item, per-detector read flags), `AuditReport`, `run_audit(detectors, days, plan, registry)` (fits every detector through the harness on the same days, runs it on the same observed day, collects `AccessLog` and read logs), `render_markdown(report)` producing the matrix with rows for: band, hold threshold, schedule window and ticks, dose limit, response parameters, physiological bounds, scale, priority, forecaster, calibration days (observed only), `EvidenceVector`, plan signature check; columns B1 to B5 and the proposed method (K). Cell values are `read`, `not read`, or `by design` with a one-line reason drawn from the module docstrings.
5. Run the audit. For each failing check decide: fix the baseline (small edit inside `src/ralmon/baselines`, with its own test), or record a finding and escalate. Never edit `02-interfaces.md`: a contract problem becomes an ADR request in the completion note. If the proposed method calibrates on the latent trace, this is finding F1: either B4 and B5 are given the identical calibration target through `AccessPolicy(calib_latent=True)` under a shared, declared policy (and the note says so), or the proposed method is changed; escalate the decision to the WS05 owner and the human.
6. Write `notes/fairness-audit.md`: `## Scope and method`; `## Knowledge matrix` (between the two markers, generated); `## Checks` (table: check, test name, result); `## Documented asymmetries` with a justification each: baselines produce no attribution and receive no `EvidenceVector` (analisi §5.4: B1 shows the value of attribution, B5 fails on it); baselines carry no probabilistic confidence and B5 has no alpha allocation (analisi §4.4); plan signature verification is not applied to baselines (a security check, not clinical knowledge); B1 also receives the hold threshold and the dose limit as static thresholds (stronger than the minimal B1 of the analysis, chosen on purpose); B2 and B4 receive no clinical thresholds (data-driven by design); all conformal methods calibrate on unlabelled data, so injected anomalies contaminate their quantiles equally; `## Findings` with one line per finding in the form `- F<n> [resolved|escalated]: text; owner; resolution`, covering at least the calibration target, the absence of a template field in `Detection` (B3 and B5 cannot report the violated template), the `CalibrationEpisode.template` placeholder used by B4, the missing `Forecaster` entry in the public API table, and any check that failed; `## Conclusion for WS08-T02` stating whether B1 to B5 may be used as configured, and the exact timing and operating-parameter conventions WS08 must pass.
7. Run `ruff format`, `ruff check src tests`, `mypy src/ralmon`, `pytest tests/baselines -q`; refactor.
8. Commit `WS06-T07: add baseline fairness audit`; `status: done`; paste outputs in the completion note.

## Done when

- `pytest tests/baselines/test_fairness_audit.py -q` exits 0, and `pytest tests/baselines -q` still exits 0.
- `ruff check src tests` and `mypy src/ralmon` exit 0.
- `test -f docs/plan/workstreams/WS06-baselines/notes/fairness-audit.md` exits 0 and `grep -c -E '^## (Scope and method|Knowledge matrix|Checks|Documented asymmetries|Findings|Conclusion for WS08-T02)$' docs/plan/workstreams/WS06-baselines/notes/fairness-audit.md` prints `6`.
- `grep -nE '^- F[0-9]+ \[open\]' docs/plan/workstreams/WS06-baselines/notes/fairness-audit.md` prints nothing.

### Hand-over from WS06-T01 (agent, 2026-10-10)

Test 12 assumes the B3 detection time equals the `t_eval_ms` of the first `VIOLATED` record. With the harness grid (a monitor time: step `t` sees device times up to `t - reorder_delay_ms`) this holds for `reorder_delay_ms = 0` only; for `D > 0` the detection time is `t_eval_ms + D` rounded up to the grid (see the module docstring of `ralmon.baselines.base`), so use the documented-difference clause. `BaselineBase.run` already passes the plan through `logged_plan(plan, detector.read_log)`: read `detector.read_log` and `detector.access_log` and build `AuditedRegistry(registry, detector.read_log)` so that registry and plan reads land in one log.

### Hand-over from WS06-T01 (agent, 2026-10-10, review fixes): threat model and documented asymmetries

1. **The guards are a defence against accidents plus an audit log, not a sandbox.** A deliberate cheat is feasible: `guarded._day` returns the whole `BenchmarkDay`; `_policy` and `_split` can be reassigned; `copy`, `deepcopy` and `pickle` keep `_day`; a subclass that overrides `fit` can read `calib_days[i].latent` without a log entry; `detector.access_log.clear()` works; `LoggedMapping._inner` exposes the values; `import ralmon.benchmark` is open; the split label is trusted (only a day object listed in both lists is refused). The read logs are only as complete as the code paths that use the wrappers (`plan.schedule` and an unwrapped registry are not logged). The note `fairness-audit.md` must say that the audit shows what well-behaved baselines read and does not prove that no baseline could read more.
2. **Asymmetries of `iter_steps` against the monitor (add to `## Documented asymmetries`).** (a) The monitor excludes a late input (`is_late`, `t_rx_ms` after the watermark); `iter_steps` delivers it later (T01 test 9), so baselines get information the monitor discards. (b) The monitor deduplicates by (source, name, seq); the harness does not, so duplicates reach the baselines (B1 would raise extra alarms). (c) The monitor rejects future-stamped inputs; the harness does not. The net direction of (a) to (c) is unclear; whether `iter_steps` should mirror these rules is open for gab. The offset of `D` (previous hand-over line) stays.
3. **Cross-midnight state.** Until ADR-061 is accepted baselines run per day with empty state; see its Consequences for the fairness effect.

### Hand-over (worker, 2026-10-10, from WS06-T06)

1. Test 15 (detections at `alpha = 0.05` are a subset of those at `alpha = 0.2`) does not hold for B5 as stated: a smaller level removes the predicted alert, and then the measured verdict at the deadline supplies the detection, so the detection time moves from the activation step to the deadline step (`test_b5_predicted_alerts_are_nested_in_alpha_but_detections_are_not`). The predicted alerts (`B5ConformalSTL.predictions`, `emitted`) are nested; assert the subset on those, and document the shift. 2. `B5ConformalSTL` needs `plan_for_day` (required keyword) and a `tail_ms` of at least the longest window, besides the arguments listed for `all_baselines`; `evaluator_factory` has the signature `(template, registry, step_ms, anchor_kind)`. 3. Documented asymmetry to add: B5 builds its values on the device-time grid of the monitor and drops late inputs (`SignalGrid.late`), so asymmetry (a) of `base.py` does not apply to B5 when `D` is a multiple of `T`, while B1 to B4 may use a late input; B5 detection times are `t_eval_ms + D`. 4. Read set of B5: the `Template.params` names of the loaded templates and `bounds:bp` through `LoggingRegistry(registry, detector.read_log)`, plus the plan parameter names of the records that the plan carries; no `scale_*`, `priority_*` or `max_latency_*` name (`test_b5_raw_robustness_never_normalised`). 5. `CalibrationEpisode.template` of B5 is the template of the instance that attains the minimum of the group (conjunction) or the template itself (per template); the calibrators are fitted on raw values, not on the normalised ones of the contract field comment. 6. Finding for `## Findings`: `Detection` has no template field, so B3 and B5 cannot report the violated template; B5 saturates the score of a minus-infinity robustness at `sys.float_info.max`.

### Open decision for gab (D2) (worker, 2026-10-10, review round 1)

As implemented to the task text (test 15), the predictive part of B5 is nearly vacuous for this problem: only RESP is predicted, from about five blood-pressure samples per day, which the contract itself expects to be a useless prediction target (`02-interfaces.md#forecaster`, Targets in scope), so B5 reduces to B3 plus a rarely firing RESP test. The proposed method also predicts SCHED (`DeadlineForecaster`, WS05-T05). A reviewer may call this a straw man. The recommended remedy is a B5 variant that completes SCHED with the `DeadlineForecaster`, changing D2 and test 15 together; it would also make the mixed-unit masking of a predicted alert reproducible at the level of the decision (two predictive templates then share a pooled constant). It is not implemented here, because it changes the task text. WS08-T02 must not present B5 results as the B5 comparison for the paper until gab decides.

Also recorded for WS08. D10: the per-test level of B5 is `alpha`, that of the proposed method `alpha / n_tests`; the direction of the net effect is ambiguous (a larger level fires more, but B5 has fewer tested instances), so WS08 should also run B5 at `BonferroniAllocation.per_test_exact(alpha, n_tests)`; no code change is needed, B5 accepts a `Fraction` as `alpha`. D4: running the literal rule of the paper (alert unless satisfaction is certified, score `R = rho_hat - rho_true`) is a cheap WS08 variant.

### Hand-over (worker, 2026-10-10, from WS06-T04)

1. `B3PlainSTL(templates, registry, *, timing, evaluator_factory=None, ...)`: `timing` is keyword-only; `fit([], [])` is valid and reads no day; `run` still needs a `fit` call. B3 reads exactly the `Template.params` names of the templates that the day instantiates plus `bounds:bp` (test 7 of this task holds; test 8, B5 against B3, holds on the same templates and day). 2. Test 12 holds as `t_eval_ms + D` for six templates; it does NOT hold for INT: the monitor decides VIOLATED from the sign of the upper bound of a non-point interval and the point evaluator returns no value, so B3 and B5 are silent on most INT violations (reproducer `test_b3_known_difference_a_violation_without_a_point_value_is_not_detected`; Notes of WS06-T04). Put it under `## Documented asymmetries` and as a finding for gab. 3. `SignalGrid` (shared by B3 and B5) now applies the `NODE_STATE colocated` reports as the monitor does; `B3PlainSTL.run_stats` and `B5`'s grid expose the ADR-054 gate. The knowledge matrix should list the reports as shared knowledge.
