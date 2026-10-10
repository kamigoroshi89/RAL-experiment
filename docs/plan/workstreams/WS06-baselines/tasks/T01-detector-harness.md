---
id: WS06-T01
title: Detector protocol implementation and common harness
workstream: WS06-baselines
owner: agent
status: ready
depends_on: ["WS05-T01", "WS04-T01", "WS05-T03", "WS05-T07"]
critical_path: true
non_negotiable: false
estimate_pd: 1.5
sources: ["analisi §5.4", "analisi §10 (1)", "analisi §4.1 (sampling semantics)", "analisi §4.7 (causal monitoring)"]
interfaces: ["02-interfaces.md#detector", "02-interfaces.md#trace-schema"]
review_items: []
---
## Obiettivo

Create the shared base that every baseline B1 to B5 is built on, so that all of them are evaluated by identical code and cannot see more than the proposed method sees. Concrete output: `ralmon.baselines` with the `Detector` protocol (verbatim from the contract), an abstract `BaselineBase` template class, a causal step iterator that delivers inputs exactly as `Monitor.advance` does, and guard objects that make "no latent trace and no ground truth at inference" (analisi §10 objection 1) true by construction and auditable by logs.

## Contesto

- `02-interfaces.md#detector` (rules: same clinical knowledge, no `LatentDay`, no `GroundTruthEvent`, `fit` may use ground truth from training days only) and `02-interfaces.md#trace-schema` (`ObservedDay`, `LatentDay`, `BenchmarkDay`, `GroundTruthEvent`).
- `02-interfaces.md#alert`: `Detection` is the output type; it is exported by `ralmon.attribution` (package public API table). Baselines return plain `Detection` with `label=None`.
- `02-interfaces.md#time-and-units`, rules 1 and 3 (discrete step `T_s`, reorder delay). The causality rule to copy is the one stated for `Monitor.advance`: it uses only inputs with `t_device_ms <= t_ms - reorder_delay_ms`.
- `docs/source/analisi.md` §5.4 and §10 objection 1.
- Blocked until `WS05-T01` and `WS04-T01` are `done` and these imports work: `from ralmon.benchmark import ObservedDay, BenchmarkDay`, `from ralmon.attribution import Detection, AttributedCause, EvidenceVector`, `from ralmon.spec import CarePlan, TemplateInstance, ParameterRegistry, RegistryEntry, PhysioBounds`. The `ralmon.attribution` import needs WS05-T07 and the `ralmon.spec` import needs WS05-T03; neither is in `depends_on` (see the workstream README): if they fail, stay blocked and say so in the completion note; never define a stand-in for a contract type.

## File toccati

- `src/ralmon/baselines/__init__.py` (create; exports `Detector` only; T02 to T06 each add one export)
- `src/ralmon/baselines/base.py` (create)
- `src/ralmon/baselines/access.py` (create)
- `tests/baselines/conftest.py` (create)
- `tests/baselines/test_base.py` (create)
- `tests/baselines/test_access.py` (create)

## Test

Write these first (`pytest tests/baselines -q` must fail with import errors before any implementation). Fixtures are hand-written in `conftest.py`: `make_observed_day(samples, events)`, `make_benchmark_day(...)`, `make_care_plan(instances, schedule)` and a `stub_registry` whose numeric values are test-local, "illustrative, unverified" (band 110 to 140 mmHg, hold threshold 100 mmHg, dose limit 2 from analisi §4.1; window 30 min chosen for the test only). Signal names in T01 tests are opaque strings; the harness never looks at what a signal means. Helpers stay in their submodules and are not added to the public API table.

`tests/baselines/test_base.py`

1. `test_baseline_base_signatures_match_detector`: `inspect.signature` of `BaselineBase.fit` and `BaselineBase.run` has the parameter names and order of the `Detector` protocol (`train_days`, `calib_days`; `day`, `plan`, `evidence`).
2. `test_run_before_fit_raises_not_fitted`: `run` on a fresh subclass raises `NotFittedError`.
3. `test_refit_replaces_state`: two `fit` calls with different days call `_fit` twice; state of the second call wins (recalibration semantics, `02-interfaces.md#conformal-calibrator` rule 4).
4. `test_run_rejects_latent_and_benchmark_days`: passing a `LatentDay` or a `BenchmarkDay` as `day` raises `LeakageError`; an `ObservedDay` is accepted.
5. `test_evidence_is_not_forwarded_to_subclass`: `_run` has no evidence parameter; a subclass output is identical for `evidence=None` and for a populated mapping.
6. `test_run_rejects_non_none_label`: a subclass emitting `label=AttributedCause.C1_CLINICAL` raises `InvalidDetectionError` (baselines do not attribute, analisi §5.4).
7. `test_run_sorts_by_time_and_rejects_non_finite_score`: unsorted subclass output comes back sorted by `t_ms` (stable); a `nan` or `inf` score raises `InvalidDetectionError`; a negative or non-integer `t_ms` raises the same.
8. `test_iter_steps_hand_computed`: `step_ms=60_000`, `reorder_delay_ms=30_000`, `end_ms=120_000`, samples with `t_device_ms` 0 and 45_000 (`t_rx_ms` equal). Batches: `t=0` empty; `t=60_000` holds the sample at 0; `t=120_000` holds the sample at 45_000 (0 <= 60_000 - 30_000; 45_000 > 30_000 so it waits for t=120_000).
9. `test_iter_steps_late_arrival_waits_for_receive_time`: sample with `t_device_ms=0`, `t_rx_ms=100_000`, delay 0, step 60_000, end 180_000 is delivered at `t=120_000`, not earlier.
10. `test_iter_steps_orders_batch_by_device_time_then_seq`: two samples with `t_device_ms` 10 and 20 whose `t_rx_ms` are 50 and 30 arrive in one batch ordered 10 then 20; equal device times are ordered by `seq`.
11. `test_iter_steps_grid_covers_end`: `end_ms=180_000`, step 60_000 gives exactly four batches (0, 60_000, 120_000, 180_000) even when there are no inputs; `step_ms <= 0` raises `InvalidTimingError`.
12. `test_iter_steps_prefix_causality_property` (Hypothesis, ADR-016): for generated small days, the batches at every step `t <= T` are equal for the full day and for the day truncated to inputs with `t_rx_ms <= T`.
13. `test_rising_edges_hand_computed`: flags `[F, T, T, F, T]` give indices `[1, 4]`; `[T, T]` gives `[0]`; `[]` gives `[]`.
14. `test_evaluation_end_ms_hand_computed`: last input `t_rx_ms = hours(5)`, last schedule tick `hours(6)`, `tail_ms = hours(1)` gives `hours(7)`; no inputs and empty schedule give `tail_ms`.

`tests/baselines/test_access.py`

15. `test_fit_passes_guarded_days_with_split_labels`: `_fit` receives `GuardedDay` objects, never `BenchmarkDay`; the train list is labelled `Split.TRAIN`, the calibration list `Split.CALIB`.
16. `test_observed_always_allowed_and_logged`: reading `.observed` on either split succeeds and appears in the `AccessLog`.
17. `test_ground_truth_train_only`: `.ground_truth` on a train day returns the events and is logged; on a calibration day it raises `LeakageError` (contract: ground truth from training days only).
18. `test_latent_denied_on_calibration_by_default`: `.latent` on a calibration day raises `LeakageError` under the default `AccessPolicy`; with `AccessPolicy(calib_latent=True)` it is allowed and the log marks the read (used only if `WS05-T06` fixes latent trace as the calibration target for the proposed method; see T05 and T07).
19. `test_audited_registry_logs_reads`: `AuditedRegistry(stub_registry).get("x")` and `.bounds("bp")` add `"x"` and `"bounds:bp"` to the `ReadLog`; unread names stay out.
20. `test_logged_plan_records_param_reads`: a plan with one instance holding `{"a": 1.0, "b": 2.0}`; reading only `"a"` through the logged plan puts `"a"` in the log for that instance key and never `"b"`; `plan` fields other than `param_values` are unchanged.
21. `test_stub_registry_names_exist_in_yaml`: every name used by `stub_registry` is an entry name in `configs/registry/hypertension.yaml` (parameter names come from WS01-T03, not from this plan).

## Passi

1. Verify the unblock conditions of Contesto. Create branch `ws06-t01-detector-harness`; set `status: in_progress`.
2. Write `conftest.py` and the 21 tests above. Run `pytest tests/baselines -q`; confirm they fail for the right reason (missing modules).
3. Implement `access.py`: `Split`, `AccessPolicy(calib_latent=False)`, `AccessLog`, `LeakageError`, `GuardedDay` (properties `observed`, `ground_truth`, `latent` enforcing the rules of tests 16 to 18), `ReadLog`, `AuditedRegistry` (implements `ParameterRegistry`), `LoggedMapping` (a `Mapping[str, float]` that logs `__getitem__`), `logged_plan(plan, log)`.
4. Implement `base.py`: exceptions (`NotFittedError`, `LeakageError` re-exported from `access.py`, `InvalidDetectionError`, `InvalidTimingError`), the `Detector` protocol copied verbatim from `02-interfaces.md#detector`, frozen `TimingConfig(step_ms, reorder_delay_ms, tail_ms)`, `StepBatch`, `iter_steps`, `evaluation_end_ms`, `rising_edges`, and `BaselineBase` (template methods `fit` and `run` wrap `_fit(train: Sequence[GuardedDay], calib: Sequence[GuardedDay])` and `_run(day, plan)`; validation of tests 4, 6 and 7 happens in `run`, which raises `LeakageError` unless `isinstance(day, ObservedDay)`; the harness drops `evidence` at its boundary).
5. State the conventions in module docstrings (they are what T02 to T06 and T07 rely on): `Detection.t_ms` is the grid time at which the detector emits; deadline rules decide at the first step with `t_ms - reorder_delay_ms >= deadline`; inputs are delivered before deadlines are evaluated at a step; interval closedness follows the STL formulas (closed windows); one `Detection` per rising edge for state-like conditions and one per input for sample-like conditions.
6. Export `Detector` from `__init__.py`. Run `ruff format`, `ruff check src tests`, `mypy src/ralmon`, `pytest tests/baselines -q`; fix; refactor.
7. Commit `WS06-T01: add detector base, causal step iterator and access guards`; set `status: done`; paste the command outputs in the completion note.

## Done when

- `pytest tests/baselines -q` exits 0.
- `ruff check src tests` exits 0 and `mypy src/ralmon` exits 0.
- `python -c "from ralmon.baselines import Detector"` exits 0.
- `grep -rnE 'LatentDay|GroundTruthEvent' src/ralmon/baselines/base.py` prints nothing (only `access.py` touches those types).

## Notes

### Flag from the WS01-T03 review (orchestrator, 2026-09-30)

Test 21 ("every name used by `stub_registry` is an entry name in hypertension.yaml") uses a 30 min window "chosen for the test only", whose registry name (`sched_window`) is `unset` in `configs/registry/hypertension.yaml` (WS01-T03, open point OP-11). Kept `blocked`; align after ADR-027 (proposed) is decided.

### ADR-027 accepted (agent, 2026-10-08)

ADR-027 (fixture registry `configs/registry/fixture.yaml`, FIXTURE-ONLY rows, created by WS05-T03) was accepted by gab on 2026-10-08; the flag above is settled in that sense. Literature-anchored values for the clinical registry come from WS01-T09 (ADR-043).

### Hand-over from the WS05-T03 review (orchestrator, 2026-10-09)

WS05-T03 (`ralmon.spec`, branch `ws05-t03-spec-package`, status `in_progress` when this note was written) is implemented. (1) Where this task says to load the F0 copy or the fixture registry, `load_registry(path, step_ms=..., allow_fixture_only=True)` is required: without the flag the first run raises a `RegistryError` that names the FIXTURE-ONLY rows (ADR-027); the shared file is `configs/registry/fixture.yaml` (version 0.0.0) and the test-owned copy is `tests/fixtures/spec/registry_f0.yaml`. (2) The real registry (0.2.0) has three unset names (`priority_sys`, `priority_int`, `bound_dose_count_upper`): `get()` raises `UnsetParameterError` (a `RegistryError`) for them while `load_templates` still succeeds, so ranking SYS and INT alerts, or reading the dose-count bound, must be handled explicitly or done with the fixture registry.
