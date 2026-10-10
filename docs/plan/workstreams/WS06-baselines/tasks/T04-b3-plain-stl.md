---
id: WS06-T04
title: B3 STL without uncertainty (raw robustness on measured values)
workstream: WS06-baselines
owner: agent
status: in_progress
depends_on: ["WS06-T01", "WS05-T03", "WS05-T04"]
critical_path: true
non_negotiable: false
estimate_pd: 1.5
sources: ["analisi §5.4 (B3)", "analisi §4.2", "analisi §4.7", "analisi §10 (1)"]
interfaces: ["02-interfaces.md#detector", "02-interfaces.md#template"]
review_items: []
---
## Obiettivo

Implement `B3PlainSTL`: the same pathway templates as the proposed method, evaluated with the same STL evaluator (RTAMT unless WS05-T02 replaced it, ADR-013) on the measured values only, with raw robustness in native units, no normalisation, no priority ranking, no robustness intervals, no forecaster and no conformal calibrator (analisi §5.4 B3). It isolates the contribution of conformal prediction and of normalisation. Concrete output: `src/ralmon/baselines/raw_robustness.py`, `b3_plain_stl.py` and their tests.

## Contesto

- `02-interfaces.md#detector` and `02-interfaces.md#template` (`Template.formula_past_time`, `unit`, `params`; `TemplateInstance`; `CarePlan`).
- The harness of WS06-T01 in `src/ralmon/baselines/`. The loaders (`load_templates`, `load_registry`) and the raw-robustness entry point of WS05 are found through the ADR-013 update made by WS05-T02 in `docs/plan/03-decisions.md` (RTAMT or custom monitor).
- `docs/source/analisi.md` §5.4 row B3, §4.2 (why raw robustness over mixed units is not comparable) and §10 objection 1.
- Blocked until `WS06-T01` and `WS05-T03` are `done`. If the function that returns the raw robustness of a template instance at a grid step lives in `ralmon.monitor` (WS05-T04) and not in `ralmon.spec`, stay blocked until WS05-T04 is `done` and record that missing dependency edge in the completion note. Never re-implement STL semantics in `ralmon.baselines`.

## File toccati

- `src/ralmon/baselines/raw_robustness.py` (create; also created by WS06-T06 if that task starts first: the later task reuses it)
- `src/ralmon/baselines/b3_plain_stl.py` (create)
- `tests/baselines/test_raw_robustness.py` (create)
- `tests/baselines/test_b3_plain_stl.py` (create)
- `src/ralmon/baselines/__init__.py` (modify: export `B3PlainSTL`)

## Test

Write these first. Timing: `step_ms=60_000`, `reorder_delay_ms=0`. Stub evaluator: a scripted `RawRobustnessEvaluator` returning a fixed list of raw robustness values, one per step. `RawRobustnessEvaluator` is the adapter defined here: `reset(instance)` starts a fresh online evaluation of one template instance; `step(t_ms, values) -> float | None` receives the values of that step (held-last continuous signals, one-step impulses for events, derived signals) and returns the raw robustness in `Template.unit`, or `None` if the evaluator has no value yet.

`tests/baselines/test_raw_robustness.py`

1. `test_adapter_reports_template_unit`: the real adapter built for a template returns `unit == Template.unit` (mmHg, ms, dose or dimensionless).
2. `test_adapter_reset_gives_independent_state`: two instances of the same template stepped with different values do not influence each other; `reset` forgets history.
3. `test_adapter_rejects_unknown_param`: a `TemplateInstance` whose `param_values` lack a name listed in `Template.params` raises a specific exception (never a silent default).

`tests/baselines/test_b3_plain_stl.py`

4. `test_b3_rising_edge_of_negative_robustness`: scripted values per step `[5, 3, -2, -4, 1, -1]` (steps at 0, 60_000, ...) give detections at `120_000` with `score = 2.0` and at `300_000` with `score = 1.0` (score is minus the raw robustness at the edge step).
5. `test_b3_zero_robustness_is_not_a_violation`: a step with `0.0` gives no detection (violation is strictly negative, as `VIOLATED iff hi < 0` in `02-interfaces.md#verdict`).
6. `test_b3_score_is_raw_not_normalised`: two instances in one plan return `-12.0` (mmHg) and `-1.0` (dose) at the same step; scores are `12.0` and `1.0`, not `0.6` and `1.0`. `ralmon.spec.normalise` is monkeypatched to raise; the test passes, so it is never called.
7. `test_b3_two_instances_same_step_both_kept`: both detections are returned with the same `t_ms`, ordered by `instance_key` ascending (deterministic tie break; no cross-unit ordering by score).
8. `test_b3_evaluates_every_instance_of_the_plan`: a plan with three instances calls `reset` three times, including SYS and INT instances (same templates as the proposed method).
9. `test_b3_uses_measured_values_only`: the constructor has no forecaster or calibrator parameter (`inspect.signature`); after a BP sample of 152 is delivered the evaluator sees `values["bp"] == 152.0` at that step and at every later step until the next BP sample; before any BP sample the key is absent.
10. `test_b3_impulses_last_one_step`: a DISPENSE event delivered at a step appears as `values["dispense"] == 1.0` at that step and `0.0` at the next.
11. `test_b3_detection_time_after_reorder_delay`: BP sample at `3_600_000` with `reorder_delay_ms=120_000` reaches the evaluator at step `3_720_000`, and so does the detection.
12. `test_b3_reads_all_template_params_but_no_scale_or_priority`: with `AuditedRegistry` and `logged_plan`, every name in `Template.params` of the instantiated templates is read, and no name that is a `scale_param`, `priority_param` or `max_verdict_latency_param` of any template is read.
13. `test_b3_ignores_evidence_and_never_labels`: identical output with and without an `EvidenceVector`; all labels `None`.
14. `test_b3_is_causal_property` (Hypothesis): detections with `t_ms <= T` are the same for the full day and for the day truncated to inputs with `t_rx_ms <= T`.
15. `test_b3_range_template_matches_hand_derivation` (integration, real evaluator): for the RANGE template with the test-local band 110 to 140 mmHg (illustrative, unverified), BP samples 125, 152, 105 produce the raw values derived by hand from `formula_past_time`. The derivation goes in the test as comments: margin of the atomic band predicate is `min(v - 110, 140 - v)` = 15, -12, -5; the treatment of the measurement indicator follows WS01-T02 and is stated in the comment; the test asserts the detection times and scores with `pytest.approx`.

## Passi

1. Verify unblock conditions. Branch `ws06-t04-b3-plain-stl`; `status: in_progress`. Read the ADR-013 update and find the raw-robustness entry point; write its name in the `raw_robustness.py` docstring.
2. Write the 15 tests; run them; watch them fail.
3. Implement `raw_robustness.py`: the `RawRobustnessEvaluator` protocol, `TemplateRawEvaluator(template, registry)` wrapping the WS05 entry point, and a factory `make_evaluator(template, registry)`. The wrapper builds nothing of the STL semantics itself.
4. Implement `B3PlainSTL(BaselineBase)` with `name = "B3"`, constructor arguments `templates` (from `load_templates`), `registry`, `timing` and an optional `evaluator_factory` (default `make_evaluator`; tests inject the stub). `_run`: for every step of `iter_steps`, update held values and impulses with the signal construction that the monitor uses (`ralmon.signals`: `hold_last`, derived signals; the mapping from `EventKind` to `SignalId` is the one documented by WS05-T02); step every instance's evaluator; emit on the rising edge of `sigma_raw < 0` (`rising_edges` of the harness) with `score = -sigma_raw`.
5. Class docstring: what B3 is not (no normalisation, no ranking, no intervals, no verdict states, no uncertainty), and `Hyperparameter selection`: B3 has no operating parameter; its recall against false alarms is a single operating point.
6. Export from `__init__.py`; run `ruff format`, `ruff check src tests`, `mypy src/ralmon`, `pytest tests/baselines -q`; refactor.
7. Commit `WS06-T04: add B3 plain STL baseline`; `status: done`; paste outputs in the completion note.

## Done when

- `pytest tests/baselines/test_raw_robustness.py tests/baselines/test_b3_plain_stl.py -q` exits 0, and `pytest tests/baselines -q` still exits 0.
- `ruff check src tests` and `mypy src/ralmon` exit 0.
- `python -c "from ralmon.baselines import B3PlainSTL"` exits 0.
- `grep -lE 'normalise|rank_alerts|scale_param|priority_param|Conformal|Forecaster|LatentDay|GroundTruthEvent' src/ralmon/baselines/b3_plain_stl.py src/ralmon/baselines/raw_robustness.py` prints nothing.

## Notes

### Hand-over from the WS05-T02 review (orchestrator, 2026-10-05)

ADR-013 spike result (WS05-T02, `docs/plan/workstreams/WS05-monitor/rtamt-spike.md`): outcome C. RTAMT 0.4.10 does not run on the repository Python (3.14.4, `No module named typing.io`; Python 3.13 fails the same way) and only 4 of the 7 templates translate and equal the golden cases (`sched` and `int` contain the `age` term; the equality atom of `sys` is `-abs(a-b)` in RTAMT, which the document already encodes on the host side as an indicator, so `sys` translates too once fed that way). The task conditions B3 on RTAMT ("unless WS05-T02 replaced it"): use `make_point_evaluator` and say in the baseline description that B3 is the plain Boolean/STL reading without margin normalisation, not an RTAMT run.

### Hand-over (worker, 2026-10-09, from the WS05-T04 review, round 2)

No INT-based result on a generated day is evidence until ADR-054 is decided (the presence level of the last robot visit is read at every later dispense when the trace has no availability mark and no zero). Gate on `run_offline_detailed(...).stats.presence_samples_without_availability_marks`: it must be 0 (or the trace must carry the explicit zeros of option (a)), and report it when it is not. `presence_level_older_than_window_steps` is information only and is positive even on a correct trace, because a robot visit (10 minutes in the generator) is longer than `int_window` (5). When calling `make_point_evaluator`, build `presence` per co-location episode: `None` while the channel is unavailable, absent from the step at which it returns until the first new sample (`tests/monitor/helpers.py::step_values` does it); the evaluator cannot tell a held level from a new sample, so a baseline that holds the level across an outage disagrees with the monitor.

### Hand-over (worker, 2026-10-10, from WS06-T06)

`src/ralmon/baselines/raw_robustness.py` already exists (created by WS06-T06, which started first). Differences from the text of this task: `make_evaluator(template, registry, step_ms, anchor_kind=None)` and `TemplateRawEvaluator(template, registry, step_ms, *, anchor_kind=None)` take `step_ms` and the anchor kind of the point evaluator; the evaluator is stepped on the axis of the day (it needs consecutive steps from 0), so a baseline shifts the anchor of the instance and the times of the steps by the start of the day, as `SignalGrid(step_ms, delay_ms=..., origin_ms=day_start)` does for the values; `SignalGrid.apply(batch)` returns the steps of the device-time grid that the batch makes final (none while the reorder delay has not elapsed) and drops late inputs as the monitor does, so for B3 the detection time of a step is the time at which the step is final (`t_eval_ms + D`); `LoggingRegistry` forwards `overrides()` and `step_ms` that `AuditedRegistry` does not. The instance creation (RANGE and SYS at MEASUREMENT events, HOLD, COUNT, RESP and INT at DISPENSE events, SCHED and the day-end COUNT from the plan) is in `B5ConformalSTL._row`; B3 can reuse the same rules, and `test_b5_measured_decisions_agree_with_the_monitor` shows that they reproduce the first violated record of every instance of `run_offline` on a hand-built day with `D = 0` and `D = 2` steps. Test 3 of this task (a missing parameter name is an error) does not match the point evaluator, which fills omitted names from the registry (ADR-047 (g)); reconcile. The detection score for a minus-infinity robustness is `sys.float_info.max` in B5 (the harness refuses an infinite score); use the same rule.

### Completion note (worker, 2026-10-10; status left `in_progress` for the reviewer)

Changed: `src/ralmon/baselines/b3_plain_stl.py` (new: `B3PlainSTL`, `B3RunStats`), `src/ralmon/baselines/raw_robustness.py` (extended, it existed from WS06-T06), `src/ralmon/baselines/__init__.py` (export), `src/ralmon/baselines/_stubs.py` (the `B3PlainSTL` placeholder removed; not in "File toccati" but the stub must go for the export), `tests/baselines/test_raw_robustness.py` and `tests/baselines/test_b3_plain_stl.py` (new). Commits: `WS06-T04: add failing tests` (red: 36 failed, 6 passed), signal grid (availability marks), B3 implementation. The entry point named in the `raw_robustness.py` docstring is `ralmon.monitor.make_point_evaluator` (ADR-013 outcome C: not RTAMT); no missing dependency edge beyond the one already in the WS06 README (T04 needs WS05-T04, not only WS05-T03).

**Deviations from the task text, each with its reason.**
1. `raw_robustness.py` was not recreated: `make_evaluator(template, registry, step_ms, anchor_kind=None)` and `TemplateRawEvaluator(..., step_ms, *, anchor_kind=None)` keep the T06 signatures (the point evaluator needs both). The tests of the adapter that T06 left in `test_b5_conformal_stl.py` (unit, independent reset, grid) were not moved or duplicated; `test_raw_robustness.py` extends them (all seven templates, `done`, the parameter rules, the availability marks of the grid).
2. Test 3 (a missing parameter name raises) does not match the point evaluator, which fills omitted names from the registry (ADR-047 (g)). The reconciled test: a name not in `Template.params` raises `PlanFeasibilityError`, an omitted name is read from the registry, a value outside the registry and every approved range raises.
3. Test 8 ("a plan with three instances") is a day with a MEASUREMENT and a DISPENSE: the instances are created as the monitor creates them (RANGE and SYS at measurements, HOLD, COUNT, RESP and INT at dispenses, SCHED and the day-end COUNT from the plan), not listed by the plan. The creation rules are a copy of `B5ConformalSTL._row` and `_read_plan` (a shared helper would need a change to `b5_conformal_stl.py`, outside the files of this task); `test_b3_decisions_agree_with_the_monitor` checks them against `run_offline` for all seven templates at `D = 0` and `D = 2` steps.
4. Test 11: the detection time is the time at which the step is final (`t_eval + D`), as T06 recorded; the evaluator argument `t_ms` stays on the device grid (the sample at 3 600 000 reaches the evaluator at `t_ms = 3 600 000`, the detection is at 3 720 000).
5. The constructor takes `timing` as a keyword (`B3PlainSTL(templates, registry, *, timing, evaluator_factory=None, access_policy=None, access_log=None, read_log=None)`), like B5. `fit` is a no-op that reads no day (`test_b3_fit_reads_no_day`), but `run` still requires `fit` (the harness rule).
6. Beyond the task: `TemplateRawEvaluator.done` (optional member; true once an instance other than SCHED has a value, so B3 stops stepping it; a stub without it is stepped to the end, which test 4 needs), and the robot channels in `SignalGrid` (next paragraph).

**The INT hand-over (WS05-T04 review, ADR-054).** ADR-054 is accepted (option (b)) and the monitor reads `NODE_STATE colocated` reports of the robot as availability marks (WS05-T11, done). `SignalGrid` now does the same, so B3 and B5 no longer hold the presence level across an outage: `presence` and `intake` are `None` while the channel is down, the level is absent from the return until the first sample of the new episode, a first report clears a level held from before it, and a mark is ordered before a sample of the same device time. A trace without reports is read as before. The gate is `SignalGrid.presence_samples_without_availability_marks` (the definition of `MonitorStats`), exposed as `B3PlainSTL.run_stats` (`B3RunStats`: gate, `availability_reports`, `late_inputs`, `instances`) and `B3PlainSTL.int_gate_passed` (true only if the gate is 0). `test_b3_presence_follows_the_colocation_reports_like_the_monitor` shows B3 and `run_offline_detailed` agree on the detections and on the gate, with and without reports, at `D = 0` and 2 steps. The benchmark generator emits no report yet (WS04-T11, blocked), so on generated days the gate is positive and INT-based results of B3 and B5 are not evidence; report the gate. This changes B5 as well (it uses the same grid): for a day with reports its INT values change, for a day without nothing changes (the existing B5 tests pass unchanged).

**Finding: B3 (and B5) cannot detect most INT violations (handicap, needs a decision).** The point evaluator returns a value only when the interval of the instance is a point. The monitor decides VIOLATED from the sign of the upper bound alone. For INT, a step of the history where `presence` is undefined or the channel is unavailable is a possible witness, so after any dispense without a witness the interval is `[-inf, hi]` with `hi < 0` (best case: a witness at the last such step, older than the window) and no point. Reproducer, pinned by `test_b3_known_difference_a_violation_without_a_point_value_is_not_detected`: the robot is co-located from step 470 and sees no patient, a dispense at step 480; the monitor says VIOLATED at 08:00, B3 is silent. B3 detects an INT violation only when presence is defined at every step of the day before it (the dense test day). For the other six templates the hand-built day of the agreement test (D = 0 and 2) shows no difference; I did not prove that no other case exists (an undefined `bp` or `cuff_health` keeps those instances open in the monitor too, so they are PENDING there and silent here). This is a property of the entry point chosen by ADR-013 and ADR-053 (c), not of B3's design, but it lowers B3's recall on the integrity class (C3 dispense forgery) for a reason that has nothing to do with conformal prediction or normalisation, so the comparison "ours against B3" on C3 mixes two effects. Not fixed here (it needs a change in `ralmon.monitor`, WS05-T04, and I did not reach into the private evaluator). Proposed for gab, as an ADR of the next free number: (i) extend `PointEvaluator` with a public bound (for example `upper_bound()` or a `decided_violated` flag that is true when the upper bound of the interval is negative) so that B3 and B5 detect on the sign, which is the Boolean reading of "VIOLATED iff hi < 0" and needs no interval in the output, or (ii) keep the point rule and report INT/C3 of B3 and B5 as "not detectable by construction" with this reproducer. Until decided, WS08 must not present INT-based or C3 B3/B5 recall as a comparison.

**Fairness statement (what B3 gets and lacks).** Gets: all seven templates, the registry and plan parameters through the logged wrappers (`access_log.denied` is empty and `access_log.records` is empty on a normal run, `test_b3_reads_all_template_params_but_no_scale_or_priority`), the lateness rule of the monitor, the robot-channel marks. Lacks, by definition: scale, priority, intervals, verdict states, forecaster, calibrator, evidence, attribution. Score is minus the raw robustness (largest finite float for minus infinity): scores of different templates are in different units and are not comparable, so any metric that ranks B3's detections by score across templates mixes units (WS08 should treat B3 as an unranked set, or rank within a template). No clinical number in the sources (grep for 110 and 140 prints nothing).

**Verification (exit codes).** `pytest tests/baselines/test_raw_robustness.py tests/baselines/test_b3_plain_stl.py -q`: 0 (44 passed). `pytest tests/baselines -q`: 0 (141 passed). Full `pytest -q`: 0 (5583 passed, 1 skipped). `ruff check src tests`: 0. `ruff format --check src tests`: 0. `mypy src/ralmon`: 0. `python -c "from ralmon.baselines import B3PlainSTL"`: 0. `pytest tests/test_public_api.py -q`: 0. The grep of "Done when" prints nothing. `python3 tools/check_plan.py`: 0. Run time of a 24 h day with all seven templates and 40 instances: about 0.1 s.

Stale text outside this task (not edited): `docs/plan/workstreams/WS06-baselines/notes/B5-failure-analysis.md` line 74 says that B5 holds the last presence level and has no availability marks; since this task B5 applies the `colocated` reports like the monitor (the gate still applies). The T06 owner should update that sentence.
