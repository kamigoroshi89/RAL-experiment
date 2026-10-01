---
id: WS05-T04
title: "Monitor core: past-time evaluation, robustness intervals, verdicts, reorder buffer, latency bounds"
workstream: WS05-monitor
owner: agent
status: blocked
depends_on: ["WS05-T03", "WS01-T05"]
critical_path: true
non_negotiable: false
estimate_pd: 4
sources: ["analisi §4.7", "analisi §4.9 (2)"]
interfaces: ["02-interfaces.md#monitor", "02-interfaces.md#verdict", "02-interfaces.md#time-and-units"]
review_items: ["R1-W6", "R1-W7", "R1-W10"]
---
## Obiettivo

Implement the measured half of the runtime safety monitor in `ralmon.monitor`: causal past-time evaluation of the template instances of a care plan on the grid of period `T_s`, robustness intervals in which every unknown future value is replaced by the physiological bounds of the registry, three-valued verdicts (`PENDING`, `VIOLATED`, `SATISFIED`; the fourth state is added by WS05-T08), a bounded reorder buffer, a reported per-template latency bound and a reported cost per sample. Concrete output: `StreamingMonitor` (the `Monitor` protocol), the measured-only `run_offline`, the point-robustness entry point `make_point_evaluator` that baselines B3 and B5 call, and the tests that reproduce the golden cases of WS01. Definitive verdicts come from the measured prefix only (ADR-008); this task contains no forecaster and no conformal code.

## Contesto

Blocked until WS05-T03 and WS01-T05 are `done`.

- `docs/formal/05-three-valued-semantics.md` (interval semantics on prefixes, state diagram, emission of records, latency bounds, dispositions of CP3, CP6, CP7, CP12; verdict golden cases).
- `docs/formal/02-templates.md` (EBNF of `formula_past_time`, margin and guard rule, instance semantics, decision instants; the 26 template golden cases, fixture registry F0, `step_ms = 60000`).
- `02-interfaces.md#monitor` (`Monitor`, `MonitorConfig`, `run_offline`; the verdict and time contracts are quoted where used).
- `docs/formal/01-signals-sampling.md` (sections 3 and 4: ceiling rule, late-sample policy, reorder buffer).
- `docs/source/analisi.md` §4.7 (three steps of online monitoring, state diagram, complexity per sample).

## File toccati

- `src/ralmon/monitor/` (modify: real modules `verdict.py`, `config.py`, `reorder.py`, `evaluator.py`, `core.py`, `offline.py`, `forecast.py` for the `Forecast` and `Forecaster` contract types only; placeholders removed from `_stubs.py`)
- `tests/monitor/` (create: `test_golden.py`, `test_intervals.py`, `test_verdicts.py`, `test_reorder.py`, `test_latency_cost.py`, `test_load_plan.py`, `test_run_offline.py`)
- `tests/fixtures/monitor/` (create: copies of the golden cases used with their ids and `source`, hand-written traces of a few dozen samples, and a naive full-trace reference evaluator used as oracle)
- `docs/plan/02-interfaces.md` (modify: `#verdict` and `#monitor` additions of step 8 and their version bumps, unless an ADR of WS01-T05 or WS01-T08 already made them)
- `docs/plan/03-decisions.md` (modify: append one ADR, status `proposed`; append the entry-point name to ADR-013)

## Test

Write first; each fails before the implementation. Fixture registry F0 and `step_ms = 60_000` unless stated; all values are "illustrative, unverified" or fixture-only. Time labels convert with `t_ms = (60*hh + mm) * 60000`. `ObservedTrace` structural days are built locally (no dependency on WS04).

Golden and hand cases (`test_golden.py`, `test_verdicts.py`)

1. `test_point_robustness_matches_golden_templates[<id>]`: for each of the 26 cases of `docs/formal/golden/templates.yaml`, `make_point_evaluator(template, instance, registry, step_ms)` stepped through the case inputs returns `sigma_raw` at `eval_at_ms` (infinite values and the guard marker where the case says so).
2. `test_monitor_records_match_golden_verdicts[<id>]`: each case of `docs/formal/golden/verdicts.yaml`, replayed through `StreamingMonitor` (push inputs, `advance`), yields the expected `VerdictRecord` fields (`state`, `sigma_interval`, `sigma_norm_interval`, `t_eval_ms`, `decided_at_ms`, `pending_until_ms`).
3. `test_range_violation_g_range_2`: bp 152 at 09:05 (32_700_000) gives `VIOLATED`, raw interval `(-12.0, -12.0)`, normalised `(-0.6, -0.6)` (140 - 152 = -12; -12 / 20 = -0.6; analisi §4.6).
4. `test_count_violation_g_count_1`: dispenses at 07:00, 21:00, 21:02 give at 21:02 a `VIOLATED` record with raw `(-1.0, -1.0)` dose and normalised `(-1.0, -1.0)` (`2 - 3 = -1`, not -8; analisi §4.6).
5. `test_sched_pending_then_satisfied_or_violated`: tick 09:00 (32_400_000), window 1_800_000: `pending_until_ms == 34_200_000`; a measurement at 09:05 gives `SATISFIED` with `decided_at_ms == 32_700_000` (G-SCHED-1); with no measurement the record is `VIOLATED` with `decided_at_ms <= 34_260_000` (deadline plus `T_s`).
6. `test_resp_pending_until_deadline_then_violated`: dispense 07:00 (25_200_000), `delta1 = 3_600_000`, `delta2 = 10_800_000`, no measurement in the window: `PENDING` at every step from 07:00 to 09:59, `pending_until_ms == 36_000_000`, then `VIOLATED` with `decided_at_ms <= 36_060_000` (G-RESP-4).
7. `test_resp_satisfied_early_with_physiological_completion`: `bp_pre = 150`, measurement 08:30 (30_600_000) with bp 132 (drop 18, `delta_resp = 10`): `SATISFIED` at `decided_at_ms == 30_600_000`, well before `pending_until_ms`; raw interval `(8.0, 90.0)` (`lo` = 18 - 10 from G-RESP-1; `hi` = 150 - 50 - 10 = 90 with the unknown later measurement completed at the lower bound of F0), normalised `(0.4, 1.0)` (90 / 20 clipped). If WS01-T05 defines the upper end differently, its golden value wins and this line is corrected in the same commit.
8. `test_resp_violated_early_when_bounds_cannot_satisfy`: `bp_pre = 55` (bp 55 at 06:45, dispense at 07:00): the largest drop the bounds allow is `55 - 50 = 5 < 10`, so `hi = 5 - 10 = -5 < 0` and the record is `VIOLATED` at the first step that sees the dispense, before the window opens (sign and value per WS01-T05; if it forbids a decision before the window opens, follow it and state so).
9. `test_zero_margin_with_nothing_unknown_is_decided` (CP3): bp 140 (G-RANGE-4) and `c_d = 2` (G-COUNT-2) give `SATISFIED`, not `PENDING`.
10. `test_verdict_states_follow_allowed_transitions` (Hypothesis over random valid traces): per `instance_key` the sequence of emitted states is a path of the allowed graph of `#verdict` (only `PENDING`, `VIOLATED`, `SATISFIED` occur here).
11. `test_definitive_records_are_never_revised` (Hypothesis): after a `VIOLATED` or `SATISFIED` record for an instance no later record for that instance exists, even if later inputs would change the robustness.
12. `test_measured_verdicts_ignore_forecaster`: with `predictive=False` a forecaster whose methods raise is never called.

Intervals (`test_intervals.py`)

13. `test_interval_contains_true_robustness_for_every_completion` (Hypothesis): for random traces, a random cut time and random completions of the future inside the physiological bounds, the robustness computed by the naive full-trace oracle of the fixtures lies in `[sigma_lo, sigma_hi]` at the cut (soundness, analisi §4.7 step 2).
14. `test_interval_inclusion_is_monotone_in_bounds` (Hypothesis): widening the physiological bounds yields an interval that contains the previous one.
15. `test_interval_endpoints_are_ordered_and_may_be_infinite`: `lo <= hi` always; `-inf` and `+inf` are allowed and normalise to -1.0 and 1.0 in `sigma_norm_interval` (CP12).

Time and buffer (`test_reorder.py`)

16. `test_advance_releases_only_inputs_up_to_t_minus_delay`: with `reorder_delay_ms = 30_000`, a sample with device time 09:29:50 (34_190_000) pushed before `advance(34_230_000)` is used for step 09:30 (34_200_000); before that `advance` the step is not evaluated (contract of `Monitor.advance`).
17. `test_late_input_is_excluded_reported_and_never_retracts` (WS01-T01 W5): the same sample pushed after `advance(34_230_000)` (received 09:30:40) is excluded from the verdicts, is listed by `late_inputs()` with its receive time, and no emitted record changes.
18. `test_reorder_buffer_orders_by_device_time`: a shuffled arrival order (all within the delay) gives the same records as the sorted order.
19. `test_step_alignment_of_impulses`: a `meas` event at 06:52:20 counts at step 06:53 (ceiling rule of `impulses_on_grid`); consequences for `O[W, W+T_s]` as in WS01-T01 W4.
20. `test_verdict_latency_bound_reported_per_template`: with `reorder_delay_ms = 30_000`, `verdict_latency_bound_ms(RESP) == 10_890_000` and `verdict_latency_bound_ms(SCHED) == 1_890_000` (registry latency `delta2 + step_ms` or `sched_window + step_ms`, plus the reorder delay).
21. `test_definitive_records_are_emitted_within_the_bound` (Hypothesis): for every anchored instance, the argument of the first `advance` that returns its definitive record minus its anchor is at most `verdict_latency_bound_ms(template)` when `advance` is called at every step.
22. `test_advance_is_causal` (Hypothesis): two runs whose inputs agree on `t_device_ms <= tau` and differ arbitrarily after produce identical records with `t_eval_ms <= tau`.

Cost and state (`test_latency_cost.py`)

23. `test_node_updates_per_sample_are_linear_in_active_instances`: `stats().node_updates` per ingested sample for 1, 10 and 100 identical instances grows at most linearly with the instance count and does not depend on trace length (10 versus 1000 steps); no wall-clock is used.
24. `test_retained_state_is_bounded_by_windows`: after a long trace, `stats().retained_samples` does not exceed the number of grid steps in the largest window plus the reorder buffer capacity used in the test.

Plans and offline (`test_load_plan.py`, `test_run_offline.py`)

25. `test_load_verifies_signature_and_monotonic_plan_version`: a tampered signed plan raises `PlanIntegrityError`; after plan version 2 is loaded, a plan of version 1 with the same `care_plan_id` raises `PlanVersionError`; a plan whose `registry_version` differs from the registry raises `PlanIntegrityError` (analisi §4.9 item 7).
26. `test_config_rejects_predictive_until_ws05_t08`: constructing a `StreamingMonitor` with `MonitorConfig(predictive=True, ...)` raises `MonitorConfigError` with the text "added by WS05-T08" (the config dataclass itself is verbatim from the contract and validates nothing); the test is deleted by WS05-T08.
27. `test_run_offline_equals_manual_stream_feed`: `run_offline` and a manual push/advance loop give identical record tuples, and `run_offline` advances at `t_k + reorder_delay_ms` after pushing every input with `t_rx_ms` up to that instant (this is what makes W5 hold).
28. `test_run_offline_default_registry_and_templates`: with no keyword arguments the registry and templates come from `load_registry()` and `load_templates()`; explicit `registry=`, `templates=`, `verifier=` override them.
29. `test_monitor_sources_do_not_reference_ground_truth`: no file under `src/ralmon/monitor` mentions `LatentDay`, `GroundTruthEvent` or `BenchmarkDay` (the monitor never receives them; `Monitor` contract).
30. `test_rtamt_oracle_agrees_on_completed_traces`: only if ADR-013 says outcome A or B and RTAMT is installed (`pytest.importorskip("rtamt")`), the point robustness of the custom evaluator equals RTAMT's on the golden cases and on random completed traces.

## Passi

1. Verify unblock conditions; branch `ws05-t04-monitor-core`; `status: in_progress`. Read the Contesto documents and write in the completion note, one line each: the instance model and decision instants (WS01-T02 section 1 and section 4), the emission rule of records (WS01-T05), the treatment of CP3 (ties), CP6 (deadline elapsed with an unavailable channel), CP7 (state across days), CP12 (infinite intervals), and the engine outcome of ADR-013. Where WS01 is silent use this conservative rule and say so: never claim `SATISFIED` when an unknown remains that could still violate; records are emitted at instance activation (`PENDING`) and at each state change.
2. Copy the golden cases used into `tests/fixtures/monitor/` with `id` and `source`; write the naive oracle evaluator there (dense arrays, no incremental state, written from the semantics text, not from the implementation); write the tests of the Test section. Run `pytest tests/monitor -q`; watch them fail for the right reason. Commit `WS05-T04: add failing monitor tests`.
3. Implement `verdict.py` (`VerdictState`, `RobustnessInterval`, `VerdictRecord` verbatim from `#verdict`, plus the two fields of step 8; `Rho` and `RhoKind` are imported from `ralmon.spec` and re-exported) and `config.py` (`MonitorConfig` verbatim, `MonitorConfigError`, `PlanVersionError`).
4. Implement `reorder.py`: a buffer keyed by `t_device_ms`; `release(watermark)` returns inputs with `t_device_ms <= watermark` in device-time order; an input at or below the last released watermark is late: it is excluded, appended to a `late_inputs()` list (never dropped silently, never an exception, never a retraction) and counted.
5. Implement `evaluator.py`: parse `Template.formula_past_time` with the grammar of WS01-T02 section 1 into a tree; evaluate the body per instance with interval semantics (atomic predicates give `[lo, hi]` from the held value or, for unknown future steps, from the `PhysioBounds` of the registry; `not` swaps and negates; `and` and `or` are componentwise `min` and `max`; `once[a,b]` and `historically[a,b]` are sliding-window `max` and `min` kept with monotone deques so each node costs amortised O(1) per grid step; guards give infinities per the margin and guard rule). Record at each node which child attained the deciding bound, to build `subformula_path`. Expose `make_point_evaluator(template, instance, registry, step_ms) -> PointEvaluator` with `step(t_ms, values) -> float | None` (body robustness in `Template.unit`, `None` until defined); it is the entry point WS06-T04 wraps. If ADR-013 kept RTAMT for point robustness, delegate point evaluation to it behind the same seam and keep the custom interval evaluator; if not, RTAMT is used only in test 30.
6. Implement `core.py` (`StreamingMonitor(config, registry, templates, *, calibrator=None, forecaster=None, verifier=None, template_ids=None)`; `template_ids` lets a placement run only a subset of templates, used by WS05-T09): `load` (signature and registry checks of WS05-T03, monotonic `plan_version`, instance creation from `CarePlan.instances`), `push_sample` and `push_event` (events go through `event_to_sample`; derived signals from `default_derived_signals()` receive every released sample; per-instance capture of `bp_pre` at each dispense anchor), `advance`, `late_inputs`, `stats`, `verdict_latency_bound_ms`. The class docstring states the reported costs: ingestion O(log b) for a buffer of b inputs, evaluation O(A) per grid step for A active instances (amortised), state O(largest window in steps + b). Implement `offline.py` (`run_offline` as in test 27, keyword-only `registry`, `templates`, `verifier`).
7. Refactor; remove migrated names from `monitor/_stubs.py`; update `monitor/__init__.py`; run `pytest tests/monitor -q`, `ruff format src tests`, `ruff check src tests`, `mypy src/ralmon`.
8. Contract additions, one ADR (status `proposed`, confirmation tag) and one version bump per touched contract in the same commit: `#verdict` gains two defaulted fields at the end of `VerdictRecord`: `subformula_path: str | None = None` (path of the sub-formula that attained the deciding bound; without it `Explanation.subformula_path` has no source; format: child-index path from the formula root, with the labels of `02-templates.md` when it names conjuncts) and `predicted_sigma_norm: float | None = None` (the conformal upper bound `sigma_hat + q` of a `PREDICTED_VIOLATION`, `None` in every record of this task, filled by WS05-T08; without it a predicted alert has no severity); `#monitor` gains keyword-only `registry`, `templates` and `verifier` on `run_offline` because `MonitorConfig` carries only a registry version string. Read the ADRs already appended by WS01-T05 and WS01-T08 for `#verdict` and fold into them instead of bumping twice. Append the entry-point name `make_point_evaluator` to ADR-013.
9. Run every command of "Done when". Commit `WS05-T04: implement monitor core`; set `status: done` and `status: ready` in the task files whose `depends_on` are now all `done`.

## Done when

From the repository root, inside `.venv`:

- `pytest tests/monitor -q` exits 0, and the ids of the golden cases used appear in `pytest tests/monitor -q --collect-only | grep -c "G-"` (at least 26 template cases).
- `ruff check src tests` and `ruff format --check src tests` exit 0; `mypy src/ralmon` exits 0.
- `python -c "from ralmon.monitor import Monitor, MonitorConfig, VerdictRecord, VerdictState, RobustnessInterval, Rho, RhoKind, run_offline, StreamingMonitor, Forecast, Forecaster, PointEvaluator, make_point_evaluator, MonitorConfigError, PlanVersionError"` exits 0 and none has `__ralmon_stub_owner__` (`build_calibration_episodes` and `StaleCalibratorError` remain placeholders owned by WS05-T08).
- `python -c "import ralmon.monitor as m; d = m.StreamingMonitor.__doc__ or ''; assert 'O(' in d and 'latency' in d.lower()"` exits 0.
- `python -c "import ralmon.monitor as m, ralmon.spec as s; assert m.Rho is s.Rho"` exits 0.
- `grep -n "make_point_evaluator" docs/plan/03-decisions.md` shows the ADR-013 entry; `python tools/check_plan.py` exits 0.

## Notes

### Flag from the WS01-T02 review (orchestrator, 2026-09-30)

Test 5 expects an early SATISFIED (`decided_at_ms == 32_700_000`) for G-SCHED-1, while WS01-T01 section 3.7 and WS01-T02 section 1.5 decide at the decision step `k_d` (09:30, 34_200_000); the document nowhere permits early decision. WS01-T05 (three-valued semantics) rules on this ("at the latest at k_d" is the suggested reading). The INT obligation of this task is static and backward per WS01-T02 section 5.3 (ADR-026 proposed). No status change: this task was already `blocked`.

### Flag from the WS01-T04 review (orchestrator, 2026-09-30)

Step 8 defines `predicted_sigma_norm` as the conformal upper bound `sigma_hat + q` of a PREDICTED_VIOLATION, whereas `docs/formal/04-normalisation-ranking.md` section 4.6 and OP-4 propose the normalised point forecast (OP-15; WS01-T05, T06 and T07 decide). Kept `blocked`.

### Flag from the WS01-T05 review (orchestrator, 2026-10-01)

See OP-T05-16 to OP-T05-21 of `docs/formal/05-three-valued-semantics.md`. Step 1 (emission rule: records per active instance per step, stricter than "activation and state change"), step 4 (lateness decided from the two clocks, `t_rx > t_{k_up(t_dev)} + D`, independent of the `advance` calls; an arrival exactly at the watermark is on time), step 5 (the evaluator is per instance, not a whole-formula evaluator), test 5 (decision at `k_d`, not an early SATISFIED), tests 10 and 11 (the emitted state sequence repeats states and SCHED refinement records change the upper end every step; test 11 conflicts), test 20 (latency 1_890_000 and 10_890_000 match) and the replay of `verdicts.yaml` through a `StreamingMonitor` without forecaster (WS05-T02 defines no `channels_unavailable` input). Kept `blocked` until ADR-029 (proposed) is decided.
