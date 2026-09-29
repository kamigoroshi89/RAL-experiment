---
id: WS06-T04
title: B3 STL without uncertainty (raw robustness on measured values)
workstream: WS06-baselines
owner: agent
status: blocked
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
