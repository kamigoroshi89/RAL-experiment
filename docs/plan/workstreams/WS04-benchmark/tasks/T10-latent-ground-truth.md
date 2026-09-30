---
id: WS04-T10
title: Latent ground-truth labeller (phi_CP on the latent trace) and non-circularity tests
workstream: WS04-benchmark
owner: agent
status: blocked
depends_on: ["WS04-T09", "WS05-T04"]
critical_path: true
non_negotiable: false
estimate_pd: 2
sources: ["analisi §5.1 (ground truth)", "analisi §10 (1)", "analisi §5.5 (first decidable instant)"]
interfaces: ["02-interfaces.md#trace-schema", "02-interfaces.md#monitor"]
review_items: ["R3-W1"]
---
## Obiettivo

Implement the ground-truth labeller of analisi §5.1: a true C1 is a violation of φ_CP evaluated on the **latent** trace; true C2 and C3 are the injected events; the monitor sees only the corrupted observations. The labeller runs the WS05 monitor on an ideal observation of the latent day and turns VIOLATED verdicts of the care-plan templates into `GroundTruthEvent`s. Then prove the evaluation is not tautological (analisi §10 objection 1) with a dedicated test suite and a written definition. Concrete output: `labelling.py`, `tests/benchmark/test_ground_truth.py`, the independent reference evaluator `tests/benchmark/reference_phi_cp.py`, and `docs/benchmark/ground-truth.md`. The completion note states the `end_ms` convention because WS08-T01 reads it.

## Contesto

- `docs/source/analisi.md` §5.1 (ground truth: "una violazione C1 vera è una violazione di φ_CP sulla traccia latente ... C2 e C3 veri sono gli eventi iniettati ... questo rende la valutazione non tautologica"), §10 objection 1 (prevention list), §5.5 (detection delay relative to the first decidable instant; for windowed constraints the deadline Δ2).
- `02-interfaces.md#trace-schema` (rule 1, `GroundTruthEvent`) and `02-interfaces.md#monitor` (`VerdictRecord`, `run_offline`, `MonitorConfig`); `02-interfaces.md#template` for `CarePlan` and the φ_CP template ids (`range`, `sched`, `hold`, `count`, `resp`).
- The template definitions and semantics of WS01-T02 and WS01-T05 (documents under `docs/formal/`), the registry `configs/registry/hypertension.yaml` (WS01-T03) and the monitor of WS05-T04.
- WS04-T07 to WS04-T09 outputs (`InjectionRecord`, `record_to_ground_truth`, `latent_day.py`, confounder groups).
- `docs/plan/workstreams/WS04-benchmark/README.md` (definition, non-tautology section, issues I1 and I5).

Unblocked when WS04-T09 and WS05-T04 are `done`. `run_offline` is delivered by WS05-T04 (its predictive parts by WS05-T08); the labeller takes the runner as an argument, defaulting to `run_offline` without calibrator and forecaster, so that mapping logic is unit-tested with a stub.

## File toccati

- `src/ralmon/benchmark/labelling.py` (create; composition module, allowed to import `ralmon.monitor` and `ralmon.spec`).
- `tests/benchmark/test_ground_truth.py` (create).
- `tests/benchmark/reference_phi_cp.py` (create: independent evaluator of the five φ_CP templates on plain lists).
- `tests/fixtures/benchmark/` (modify: hand-written latent-day fixtures; the registry is the F0 copy of WS05-T03, not a new file).
- `docs/benchmark/ground-truth.md` (create).

## Test

Fixture-only: the shared fixture registry F0 of WS01 (copied in `tests/fixtures/spec/` by WS05-T03; band 110 to 140 mmHg, `bp_hold_threshold`, `delta1`, `delta2`, `sched_window`, priorities) with `step_ms = 60000`; measurements and doses hand-placed. Tests 1 to 12 and 23 use a stub runner returning hand-written `VerdictRecord`s; tests 13 to 22 use the real monitor. Write first.

1. `test_ideal_observation_scheduled_mode`: `bp` samples exist only at latent MEASUREMENT times with the exact latent value, each with one MEASUREMENT event (no `meas` sample: impulses are events only), `t_rx_ms == t_device_ms`, no quality, no noise.
2. `test_ideal_observation_dense_mode`: `bp` at every latent grid step, each with a MEASUREMENT event.
3. `test_ideal_observation_rejects_missing_template_signal`: a φ_CP template signal that the latent day cannot supply raises `IdealObservationError` instead of guessing; the `day_end` impulse is added at the end of the day when a template needs it.
4. `test_violated_records_become_events_with_end_ms_convention`: RANGE, HOLD and COUNT-limit violations (records without `pending_until_ms`) give `onset_ms = decided_at_ms` and `end_ms is None`; RESP, SCHED and day-end COUNT violations give `onset_ms` at the instance anchor and `end_ms = pending_until_ms` (the deadline); PENDING, SATISFIED and PREDICTED_VIOLATION records give nothing.
5. `test_duplicate_records_of_one_instance_give_one_event`: several VIOLATED records with the same `instance_key` yield one event.
6. `test_only_care_plan_templates_become_c1`: SYS and INT VIOLATED records never become C1 events.
7. `test_c1_subtype_and_injected_flag_from_explaining_record`: a `hypertensive_spike` record whose window (extended by the template latency bound) contains the RANGE event gives that subtype and `injected = True`; no record gives `spontaneous_range` and `injected = False`; a record of another template (spike against COUNT) does not explain the event.
8. `test_adherence_deviations_labelled_from_behaviour_log`: an omitted slot gives a day-end COUNT event `dose_omission`, a Markov double take gives `double_take`, both `injected = False`; a forced double take (confounder record) gives `injected = True`.
9. `test_confounder_group_propagates_from_record`: the group of the explaining record appears on the event; unexplained events have `None`.
10. `test_c2_c3_events_are_realised_records_only`: realised C2 and C3 records map one to one to events; unrealised ones are absent from the truth and present in the injection log.
11. `test_ground_truth_sorted_and_deterministic`: order by `(onset_ms, cls, subtype, end_ms)`; two runs are equal.
12. `test_registry_version_mismatch_raises`: `plan.registry_version` different from `MonitorConfig.registry_version` raises `RegistryMismatchError`.
13. `test_perfect_observation_equals_ground_truth_on_c1`: with zero cuff error, no fault, no attack and measurements at the ticks, the set of `(template, anchor)` of VIOLATED φ_CP verdicts on the observed day equals the set of C1 ground-truth events.
14. `test_noisy_observation_diverges_from_ground_truth`: latent 139 with cuff bias +3 gives an observed 142: the monitor flags a range violation that the truth lacks (false positive); latent 141 with bias -3 gives 138: the truth has a C1 event that the monitor misses (false negative). Both hand-computed against the fixture band.
15. `test_c1_truth_follows_latent_not_injection_intent`: an injected spike that keeps the scheduled measurement inside the band produces no C1 event although its record exists; a larger one crossing the band edge produces one `hypertensive_spike` event with `injected = True`.
16. `test_ground_truth_unchanged_by_observation_corruption`: for one latent day, three observed variants (cuff noise, a C2 fault, a C3 attack) give the identical set of C1 events.
17. `test_undetectable_injection_still_in_ground_truth`: a silent cuff bias yields a C2 truth event although the monitor emits no φ_SYS or φ_INT violation and the evidence signature is empty.
18. `test_independent_reference_evaluator_agrees`: over 20 random latent days (seeds 0 to 19, fixture prior, natural adherence, no injection) the set of `(template, anchor_ms)` violated per `reference_phi_cp` equals the labeller's set.
19. `test_scheduled_and_dense_modes_differ_only_where_expected`: a spike between two scheduled measurements is no C1 event in `scheduled` mode and a range event in `dense` mode.
20. `test_null_latent_day_has_no_care_plan_violation`: no injection, full adherence, constant in-band pressure and a schedule from `derive_schedule` give zero C1 events (catches schedule and registry mismatches in the generator).
21. `test_labeller_takes_no_observed_day`: the signature of `label_latent_day` has no `ObservedDay` parameter.
22. `test_import_boundaries`: an AST scan shows that only `labelling.py`, `builder.py` and `validation.py` import `ralmon.monitor` or `ralmon.spec`; every other module of `src/ralmon/benchmark/` imports only `ralmon.signals`, numpy, YAML and the standard library (README issue I1).
23. `test_dynamic_instance_anchor_recovered_from_deadline`: a RESP record whose instance is not in the plan (created at a DISPENSE), with `pending_until_ms` at 10:00 and `delta2` of 3 h (F0), gives `onset_ms` at 07:00 and `end_ms` at 10:00.

## Passi

1. Read the WS01-T02 template definitions and WS01-T05 semantics, the WS05-T04 monitor API (`run_offline`, `StreamingMonitor`) and the F0 registry copy in `tests/fixtures/spec/`. Write `tests/benchmark/reference_phi_cp.py` from the template formulas, not from any monitor code.
2. Write `tests/benchmark/test_ground_truth.py`; run it, confirm failure; commit `WS04-T10: add failing ground-truth tests`.
3. Implement `labelling.py`: `ideal_observation(latent, care_plan_id, mode)` (modes `scheduled` default and `dense`), `label_latent_day(latent, plan, records, behaviour_log, run_fn, config, latency_bound_fn, mode) -> tuple[GroundTruthEvent, ...]` (the runner defaults to `run_offline` with no calibrator and no forecaster), the injection-to-template link table (`hypertensive_spike` to `range`, `drug_nonresponse` to `resp`, `hypotension_below_hold` to `hold`, `measurement_refusal` to `sched`, forced `double_take` to `count`), the natural-subtype rule, and `RegistryMismatchError`. Conventions: for windowed obligations (records with `pending_until_ms`: RESP, SCHED, day-end COUNT) `onset_ms` is the anchor of the violated instance (`TemplateInstance.anchor_ms` when the instance is in the plan; for instances the monitor creates at each DISPENSE, RESP and INT, WS01-T02 section 5, the deadline `pending_until_ms` minus the template's window length from the registry, `delta2` for RESP) and `end_ms = pending_until_ms`; for every other violation `onset_ms = decided_at_ms` and `end_ms is None`.
4. Add `assemble_benchmark_day(observed, latent, plan, records, behaviour_log, ...) -> BenchmarkDay` (with the sidecars) to `labelling.py`, so that the import of `ralmon.monitor` stays in one module.
5. Write `docs/benchmark/ground-truth.md` with the H2 headings `## Definition`, `## Onset and end conventions`, `## Injection records versus truth`, `## Modes`, `## Non-circularity tests`, `## Residual circularity`. `## Non-circularity tests` names each test of this file that answers analisi §10 objection 1 (tests 13 to 18, 21 and 22) with its path. `## Residual circularity` states what the evaluation does and does not show: the same specification defines the truth and the monitored constraints, the tests show that observation loss is what is measured, and the clinical validity of φ_CP rests on the registry review (WS00-T07); the independent reference evaluator guards against a monitor defect defining its own truth.
6. Refactor; run `ruff check src tests`, `mypy src/ralmon`, `pytest tests/benchmark -q`; commit `WS04-T10: add latent ground-truth labeller and non-circularity tests`; in the completion note state the `end_ms` convention and the `injection_log` sidecar keys; set `status: done`.

## Done when

- `pytest tests/benchmark/test_ground_truth.py -q` exits 0 and `pytest tests/benchmark -q` exits 0.
- `ruff check src tests` exits 0 and `mypy src/ralmon` exits 0.
- `grep -cE '^## (Definition|Onset and end conventions|Injection records versus truth|Modes|Non-circularity tests|Residual circularity)$' docs/benchmark/ground-truth.md` prints `6`.
- `grep -c 'def test_' tests/benchmark/test_ground_truth.py` prints at least 23.

## Notes

### Flag from the WS01-T02 review (orchestrator, 2026-09-30)

Step 3 assumes instances "created at each DISPENSE, RESP and INT" (dynamic INT obligation). WS01-T02 (`docs/formal/02-templates.md` section 5.3, TG-8) makes the INT obligation static from the schedule with the backward window `[a - int_window, a]`, so the `pending_until_ms` rule for INT differs. Kept `blocked` until ADR-026 (proposed, `[DA-CONFERMARE]`) is decided; then align this step.
