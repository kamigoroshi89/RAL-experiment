---
id: WS04-T07
title: C2 fault injection
workstream: WS04-benchmark
owner: agent
status: done
depends_on: ["WS04-T06", "WS02-T01", "WS02-T03"]
critical_path: true
non_negotiable: false
estimate_pd: 2.5
sources: ["analisi §5.1 (3)", "analisi §4.5 (matrix rows 3, 4, 5, 7)", "analisi §4.8"]
interfaces: ["02-interfaces.md#trace-schema", "02-interfaces.md#evidencevector"]
review_items: []
---
## Obiettivo

Inject C2 faults (system or embodiment failure) into the observed base stream with parametrised onset, duration and magnitude (analisi §5.1 (3)): BLE dropout with node transition, stuck-at, silent cuff bias (kept on purpose, to measure the limit honestly), noise from the Noise Stress Test Database on the ECG path, robot navigation delay, manipulation failure, dispenser sensor bounce and the evident cuff fault of matrix row 3. Also create the shared injection machinery: `InjectionSpec`, `InjectionRecord`, the canonical application order and the mapping from a realised record to a `GroundTruthEvent`. C2 truth is the injected event itself, whether or not any channel can detect it. Concrete output: `injection.py`, `inject_c2.py`, `configs/benchmark/injections.yaml` (C2 part), tests.

## Contesto

- `docs/models/fault-model.md` (WS02-T01: subtype vocabulary reused verbatim, injection parameter sheet, fault-to-evidence table, non-faults and boundaries).
- `docs/source/analisi.md` §5.1 (3) (C2 list), §4.5 matrix rows 3 (cuff detached), 4 (silent bias, declared limit), 5 (robot late), 7 (dispenser bounce, interval under one second, labelled illustrative, unverified), §4.8 (claim reformulation for silent faults).
- `02-interfaces.md#trace-schema` (`GroundTruthEvent` fields, `EventKind.NODE_STATE`, `ROBOT_TASK`, `DEVICE_ERROR`, `MEASUREMENT_MISSED`) and `02-interfaces.md#evidencevector` (the 20 fields; `None` is never a negative).
- WS04-T06 outputs (`ObservedStream`, `vocab.py`, `segments.py`) and `docs/models/evidence-channels.md` if it exists (trace evidence conventions, gap G-1).
- `docs/plan/workstreams/WS04-benchmark/README.md` (subtype vocabulary, parameter policy).

Unblocked when WS04-T06 and WS02-T01 are `done`.

## File toccati

- `src/ralmon/benchmark/injection.py` (create).
- `src/ralmon/benchmark/inject_c2.py` (create).
- `src/ralmon/benchmark/vocab.py` (modify: payload keys of node state, device error, robot task outcome).
- `configs/benchmark/injections.yaml` (create: C2 section).
- `tests/benchmark/test_inject_c2.py` (create).

## Test

Hand-written fixture stream, fixture-only values: cuff measurements at 08:00, 10:00, 12:00, 14:00 with `bp` 128, 131, 127, 133 and device sequence numbers 1 to 4; dispenser events at 08:10 (seq 1) and 20:00 (seq 2); constant latent HR 70 and SBP 130. Write first.

1. `test_pipeline_order_is_canonical_and_spec_order_irrelevant`: the same specs in any order give an identical stream and identical records; the order is fixed as robot faults, then device faults, then sequence numbering, then link faults (removal last).
2. `test_ble_dropout_removes_device_data_and_leaves_sequence_gap`: window 09:00 to 13:00 on the cuff removes the measurements at 10:00 and 12:00; delivered sequence numbers are `[1, 4]`; the gateway emits NODE_STATE events at window start and end with the uncommanded flag from `vocab.py`; a deliberate transition is never produced here.
3. `test_silent_cuff_bias_shifts_values_in_window_only`: bias 5 mmHg (fixture) over 09:00 to 13:00 gives `bp = [128, 136, 132, 133]`; no DEVICE_ERROR event; the record's evidence signature is empty.
4. `test_stuck_at_repeats_last_value_before_onset`: window 09:00 to 15:00 gives `[128, 128, 128, 128]`; silent (empty evidence signature).
5. `test_cuff_detached_signature`: an attempt inside the window has no `bp` sample, a MEASUREMENT_MISSED event, a DEVICE_ERROR event with an `error_code` payload key, `cuff_health` 0.0 and an abnormal `inflation_ms`; the signature lists the fields the fault-model table names.
6. `test_ecg_noise_adds_paired_error_trace`: with an inline error trace `[+5, -3, +8]` bpm and latent HR 70, `hr_ecg` becomes `[75, 67, 78]`; `quality` is set from the trace's quality when the library carries one, otherwise `None`.
7. `test_ecg_noise_disabled_when_library_lacks_kind`: no `hr_error_ecg_noise` segments records the subtype in `disabled_subtypes` and raises nothing.
8. `test_dispenser_bounce_adds_extra_dispense_within_gap`: a forced bounce with gap 500 ms puts a second DISPENSE at the real time plus 500 ms; `content_change` is 0 when content sensing is on; INTAKE count unchanged; one record per bounce, `end_ms is None`.
9. `test_dispenser_bounce_probability_statistics`: with probability 0.3 (fixture) over 10 000 dispenses the bounced fraction lies within `4 * sqrt(0.3 * 0.7 / 10000)` of 0.3.
10. `test_nav_delay_shifts_measurement_and_marks_task_late`: a delay of 900 000 ms on the 10:00 tick moves the measurement to 10:15:30, sets the ROBOT_TASK outcome `late`, keeps the cuff noise draw unchanged.
11. `test_manipulation_failure_removes_measurement_and_witness`: the visit's measurement is absent, the ROBOT_TASK outcome is `failed`; at a dose tick no INTAKE is witnessed.
12. `test_injection_without_effect_is_logged_not_ground_truth`: a bias window that covers no measurement has `realised = False`, appears in the injection log, and yields no `GroundTruthEvent`.
13. `test_ground_truth_mapping_fields`: `record_to_ground_truth` gives `cls = C2`, the subtype, `onset_ms`, `end_ms` (window end for window faults, `None` for point faults: bounce, and per-tick faults where `onset_ms` is the tick time), `injected = True`, `template_id is None`, `confounder_group is None`.
14. `test_c2_injection_never_mutates_latent_day`: the `LatentDay` is equal before and after.
15. `test_samples_outside_effect_are_bit_identical`: adding one injection leaves every sample and event it does not touch unchanged (paired design).
16. `test_invalid_specs_rejected`: a window extending beyond the day, negative duration, or two overlapping windows of the same subtype on the same device raise `InjectionSpecError`.
17. `test_every_injected_subtype_is_in_fault_model_vocabulary`: the `- <id>` lines under `## Subtype vocabulary` of `docs/models/fault-model.md` include every C2 subtype this module injects; the module does not inject any identifier outside that vocabulary.
18. `test_signature_paths_are_contract_fields`: every dotted path of `EVIDENCE_SIGNATURES` is one of the 20 `EvidenceVector` fields; `cuff_silent_bias` and `stuck_at` have empty signatures (declared diagnosability limit).
19. `test_payload_keys_conform_to_evidence_conventions`: every payload key emitted is declared in `vocab.py`; if `docs/models/evidence-channels.md` exists, each is also in its trace evidence conventions table (skipped with an explicit reason if the document is absent).
20. `test_injection_rows_have_provenance_units_and_levels`: every subtype in `injections.yaml` names its parameters (onset, duration, magnitude with unit), each level row has `source_type` and `source_ref`, and at least three magnitude levels exist where a magnitude applies.

## Passi

1. Read `docs/models/fault-model.md`: take the C2 vocabulary, the injection parameter sheet and the fault-to-evidence table. Where the sheet names a `DeviceErrorModel` field as the source of a rate or magnitude (dropout rate, bounce probability), use it; otherwise the value comes from the `injections.yaml` design grid. If a subtype name in this task differs from the vocabulary, the vocabulary wins; record it in the completion note.
2. Write `tests/benchmark/test_inject_c2.py`; run it, confirm failure; commit `WS04-T07: add failing C2 injection tests`.
3. Implement `injection.py`: frozen `InjectionSpec` (`cls`, `subtype`, `onset_ms`, `duration_ms`, `magnitude`, `magnitude_unit`, `params`), `InjectionRecord` (spec plus realised onset and end, `realised`, `n_changed`, `evidence_paths`, `level`, `confounder_group`), `apply_observation_injections(stream, specs, context)` with the canonical order, `assign_device_seq` call between device and link steps, `finalize_observed(stream) -> ObservedDay`, `record_to_ground_truth(record)`, and `InjectionSpecError`. Only realised injections (`n_changed > 0`) become ground truth; unrealised ones stay in the injection log with `realised: false` (T12 reports the realisation rate).
4. Implement `inject_c2.py`: one function per subtype (`ble_dropout`, `stuck_at`, `cuff_silent_bias`, `ecg_noise`, `nav_delay`, `manipulation_failure`, `dispenser_bounce`, `cuff_detached`), each returning a sequence of records and using `StreamPurpose.INJECTION_C2`; `EVIDENCE_SIGNATURES` transcribed by hand from the fault-to-evidence table (a reviewer compares the two). The device error code of `cuff_detached` is a generator-defined label, not a vendor code.
5. Fill the C2 part of `injections.yaml`: parameters and magnitude levels as `design_choice` rows, magnitudes expressed relative to a reference quantity where they have clinical meaning (silent bias in multiples of `cuff_error_sd_mmhg` plus one level equal to `cuff_bias_mmhg`; bounce gap with the analisi sub-second nominal value labelled "illustrative, unverified" and stress levels labelled "stress, physical plausibility unverified"). Propose levels, do not assert them; H3 confirms. Regenerate the provenance table.
6. Add the payload keys of node state, device error and robot task outcome to `vocab.py` (names from the WS02-T03 conventions table if it exists).
7. Refactor, run `ruff check src tests`, `mypy src/ralmon`, `pytest tests/benchmark -q`; commit `WS04-T07: add C2 fault injection and injection machinery`; set `status: done`.

## Done when

- `pytest tests/benchmark/test_inject_c2.py -q` exits 0; `pytest tests/benchmark -q` exits 0.
- `ruff check src tests` exits 0 and `mypy src/ralmon` exits 0.
- `python -m ralmon.benchmark.priors --check-table` exits 0.
- `grep -c 'cuff_silent_bias' configs/benchmark/injections.yaml` prints at least 1.

## Notes

### Flag from the WS02-T01 review (orchestrator, 2026-10-02)

See `docs/models/fault-model.md` open points OP-13, OP-15 and OP-16. `InjectionSpec` here has `onset_ms`, `duration_ms`, a scalar `magnitude`, `magnitude_unit` and `params` and none of `seed`, `target`, `gap_ms`, `bias_mmhg`, `noise_level` or `delay_ms`, whereas the fault model parameter sheet and WS07-T05 use a `magnitude.<key>` mapping; `nav_delay` is injected per tick here (test 10, per-tick faults have `end_ms` None, test 13) while the sheet gives it a `duration_ms`; test 5 for `cuff_detached` lists `MEASUREMENT_MISSED`, `DEVICE_ERROR`, `cuff_health` 0.0 and `inflation_ms` but not the `NODE_STATE` event of the fault model; the fault `dispenser_bounce` also affects `resp` and `int` (mechanism M-DUPWIN, FX-16), not only `count` and `hold`. Kept `blocked`; reconcile when this task is taken.

### Flag from the WS02-T03 review (orchestrator, 2026-10-04)

See `docs/models/evidence-channels.md` EC-OP-14 to EC-OP-21 and decision D-9. In-bound reordering raises neither `timestamp_implausible` nor `seq_gap_or_replay`; the `late` outcome of test 10 is visible to `system.nav_task_failed` only if the robot stamps it with the deadline (hypothesis H-OVERRUN), and any outcome (`failed`, `timeout`) stamped after the first VIOLATED record is invisible to that instance, which also applies to the fault-model rows `impossible_goal`, `manipulation_failure` and `localisation_noise` (test 11 does not state the stamp); there is no lease parameter to produce `unreachable` (EC-OP-18); the uncommanded flag and window-start `NODE_STATE` events differ from the document (`link_down` at the start, `unreachable` at lease lapse, a positive `commanded` key). Kept `blocked`.

### Hand-over from the WS04-T02 review (orchestrator, 2026-10-05)

Structured content (level rows, capability sets, time strings) in `injections.yaml` is not read by `load_design_file` of WS04-T02 (top-level `parameters:` list, numeric values only): either keep numbers in that list or extend the loader in this task with a test; the table header claims it lists every number that is not code.

### Hand-over from the WS04-T06 review (orchestrator, 2026-10-05)

Read the "Completion note" and "Fix round 1" in `T06-measurement-process.md` before starting: vocabulary in `vocab.py` (extend `PAYLOAD_KEYS` for your own keys), `assign_device_seq` overwrites every cuff `seq` (do not call it after replay injection), `ObservedStream.visits` and `measurements` carry latent values and must never be written into an `ObservedDay`, and nobody emits the robot `NODE_STATE colocated` report yet (owner open, proposed WS04-T11).

### Completion note (worker, 2026-10-05; status left `in_progress` for the orchestrator's review)

Files: `src/ralmon/benchmark/{injection,inject_c2}.py` (new), `src/ralmon/benchmark/vocab.py` (extended), `configs/benchmark/injections.yaml` (C2 section: 28 rows, 27 `awaiting_human_value`), regenerated `docs/benchmark/parameter-provenance.md`, `tests/benchmark/test_inject_c2.py` (331 tests: the 20 listed plus extremes, edges of every window, a paired-design test for every subtype, randomised invariants, a fuzz of every public function, design loader on `tmp_path` copies in both states, layering). One file outside "File toccati": `src/ralmon/benchmark/measurement.py` (see deviation 1). Nothing under `paper/`, `data/raw/` or `outputs/`; no contract, ADR or other task file touched; nothing exported from `ralmon.benchmark.__init__`.

Reconciliation (fault-model vocabulary and evidence conventions win over the task text; the seven flags):

- (i) **Spec shape.** `InjectionSpec(cls, subtype, onset_ms, duration_ms, magnitude, magnitude_unit, params, level, confounder_group)`; the two last fields are optional additions. `magnitude` is the value of the single `magnitude.<key>` of the sheet (`bias_mmhg` mmHg, `noise_level` unit `1`, `gap_ms` ms, `delay_ms` ms); `params["target"]` is the sheet's `target` (`cuff`, `dispenser`, `ecg`, `oximeter`, `robot`) and `params["kind"]` (`measurement` or `dose`) picks the visit of a robot fault; `seed` is not a field (the stream is keyed by a digest of subtype, target, onset and duration: `injection_sub_index`). WS07-T05 maps `magnitude.delay_ms` to `magnitude` with unit `ms`, its `target` to `params["target"]` and ignores a `duration_ms` for `nav_delay` (OP-15).
- (ii) **`nav_delay` is per tick** (`duration_ms` None, `end_ms` None, `onset_ms` the tick); the sheet's duration is for the simulation (OP-15).
- (iii) **`cuff_detached` emits `NODE_STATE`**: `inactive` at the window start and `active` at its end (uncommanded, source `cuff`), only when the window contains an attempt (OP-16: the benchmark adds the event, so `system.node_lifecycle` stays in the signature). Included in test 5.
- (iv) **`dispenser_bounce`**: the evidence signature is empty (catalogue); the templates it reaches (`count`, `hold`, `resp`, `int`, M-DUPWIN, FX-16) are listed in `TEMPLATES_AFFECTED` (hand transcribed from the catalogue column and compared with it by a test) and in `details["templates"]` of every record.
- (v) **`NODE_STATE` conventions** of `evidence-channels.md`: `ble_dropout` writes `link_down` at the window start and `active` at the end (ward clock, source the device, `commanded` False, no `seq`); the node reports of the device inside the window are lost with it, the gateway's are not. The `unreachable` report at the lease lapse is **not produced**: no lease parameter exists (EC-OP-18), none was invented; the LC paths of the signature are only listed.
- (vi) **`late` stamp rule (H-OVERRUN, EC-OP-14)**: the deadline is the tick plus `context.task_deadline_offset_ms` (the registry `sched_window`, passed by the caller; `nav_delay` raises `InjectionContextError` without it); if the delayed arrival is after it the navigation outcome is `late` and the `ROBOT_TASK` is stamped with the deadline, not with the arrival or the delayed measurement; on time it stays `success` at the new arrival (the delay still moves the measurement). One outcome per visit. A `manipulation_failure` outcome `failed` is stamped where the missing item would have been (reading instant, arrival at a dose visit); EC-OP-14 (iii) applies to it.
- (vii) **Robot `NODE_STATE colocated` is not emitted** here (the fault model and the evidence document do not assign it to a C2 injection); owner still open, proposed WS04-T11. `vocab.py` has no `colocated` key yet.

Other modelling decisions (docstrings of the two modules).

- Canonical order: robot (`nav_delay`, `manipulation_failure`), device (`cuff_detached`, `cuff_silent_bias`, `stuck_at`, `ecg_noise`, `dispenser_bounce`), `assign_device_seq` once, link (`ble_dropout`), then an empty `attack` stage reserved for T08. The order inside the device stage is my choice (a detached attempt has nothing to bias; a stuck cuff freezes the biased value).
- Windows are half open `[onset, onset + duration)` on `t_device_ms`; windows outside the day, a zero or negative duration, a duplicate tick or dispense, and overlaps of one subtype on one target are `InjectionSpecError`; touching windows are allowed. Point and per-tick onsets may lie in the day or in the following day (items stay in the day of their tick).
- **Realised** means the stream changed (`n_changed > 0`: items removed, changed, moved or added); an injection that finds nothing (no reading in the window, no earlier reading to freeze, no real dispense at the onset, no visit at the tick, a zero bias) is logged, emits no node event and yields no ground truth.
- `ecg_noise`: `noise_level` is read as the factor on the paired error trace (the library has no level attribute); error index `(t - onset) // period`; quality from the trace or None; without the kind `hr_error_ecg_noise` the record is unrealised and the subtype is in `InjectionResult.disabled_subtypes` (and `settings["injection_disabled_subtypes"]`).
- `nav_delay` re-reads `bp` from `context.latent` at the new instant with the same cuff error (the paired design; the draw is unchanged because nothing is redrawn); without a latent day the value is kept; the pulse keeps its value; an intake that no visit covers any more is no longer witnessed.
- `cuff_detached` abnormal inflation is `DETACHED_INFLATION_MS` = 0 (below any positive registry minimum), health `DETACHED_HEALTH` = 0.0, error code the generator-defined label `cuff_detached`; the failed attempt keeps its sequence number (no gap).
- `dispenser_bounce` probability is not part of the spec: `plan_dispenser_bounces(dispense_times, DeviceErrorModel.dispenser_bounce_prob, gap, seed, patient_index, day_index)` draws per dispense from `(seed, patient, day, INJECTION_C2, stable_index("bounce_plan", time))`; the rate of `ble_dropout` windows is named in `injections.yaml` (`rate.source`) for the plan of WS04-T11.
- Design file: the structured `injections.c2` section holds no number; every number is a row of `parameters:` (so the provenance table lists them; this closes the WS04-T02 hand-over without extending `load_design_file`). Levels of the bias are multiples of `cuff_error_sd_mmhg` plus `device_bias` (the only filled row: multiplier 1.0 by definition, unit `x cuff_bias_mmhg`); `nav_delay` levels are multiples of the registry `sched_window`; the bounce gap rows carry "illustrative, unverified" (nominal, no number in analisi) and "stress, physical plausibility unverified" (two stress levels); durations and the ECG factor are plain `design_choice` rows. `load_injection_design(path, section="c2")` and `resolve_magnitude` read them; the loader checks subtypes against the registered injectors and units against the injector.

Deviations from the task text and contract gaps.

1. **`measurement.assign_device_seq` was changed** (outside "File toccati"; all 514 T06 tests still pass): a cuff message also ends when the instant changes, `MEASUREMENT_MISSED` shares the counter of `MEASUREMENT`, and a cuff `DEVICE_ERROR` at the instant of the last attempt shares its number. Without it a failed attempt (no `bp`) merged with the next message and the event counter drifted from the sample messages. Documented in the module docstring and tested in `test_inject_c2.py`.
2. `vocab.py`: new keys `state` (`STATES` of D-4), `commanded`, `error_code`, sources `ecg` and `oximeter`, `MEASUREMENT_MISSED` with no payload, and `REQUIRED_ALTERNATIVES` (a `NODE_STATE` needs `state`, a `DEVICE_ERROR` needs `error_code`; a later task adds an alternative instead of loosening it, for example the gateway verification keys of T08). The existing T06 test that refuses an empty `NODE_STATE` payload still holds.
3. `apply_observation_injections` returns an `InjectionResult` (stream, records in execution order, disabled subtypes), not a bare stream; `record_to_ground_truth` returns None for an unrealised record (`ground_truth_events` lists the realised ones sorted by onset and subtype).
4. Test 2 of the task text ("uncommanded flag") follows the evidence document instead: `link_down` and `active` with `commanded: False`. Test 10 holds with a fixture deadline offset of 10 min (a 15 min delay is then late). Test 19 covers only the keys of this task (`SCHEDULE_TICK.kind` and the sources are owned by `vocab.py`, T06 note M11).
5. The signature of a record is the union (raised plus conditional) of the catalogue, whether or not its condition holds in the realised injection; a test compares `EVIDENCE_SIGNATURES` with the catalogue column.

Hand-overs (read from the task files of T08 to T12 and WS07-T05).

- **T08 (C3).** Reuse as is: `InjectionSpec` (`cls` C3 works), `InjectionRecord`, `InjectionContext`, `InjectionResult`, `Injector` and `register_injector(Injector(..., stage=STAGE_ATTACK))`, `check_call` (validates an injector called directly), `injection_rng` (purpose `INJECTION_C3` is mapped), `injection_sub_index`, `stable_index`, `finalize_observed`, `record_to_ground_truth`, `ground_truth_events`, `injection_log`, `load_injection_design(path, section="c3")` and `resolve_magnitude`. The `attack` stage already runs after numbering and the link stage (an injected duplicate sequence number is never renumbered; a dropout of the genuine device cannot remove attacker traffic; a stand-in test proves the order): the only edit to `injection.py` is appending `"ralmon.benchmark.inject_c3"` to `_INJECTOR_MODULES`. Differences you must handle: the context has no previous day (add a keyword-only `previous_day: ObservedStream | None`); the loader requires `injections.c3` to list exactly the registered C3 subtypes and no number, so put the two capability sets under another top-level key (booleans are fine) or extend the loader with a test; a `DEVICE_ERROR` with the gateway verification keys needs a new alternative in `vocab.REQUIRED_ALTERNATIVES` and the keys in `PAYLOAD_KEYS`; `Sample.t_device_ms` may be negative (accepted by `_check_sample` and `finalize_observed`); `assign_device_seq` is called once by the pipeline before the link stage, never after your step.
- **T09.** C1 records fit `InjectionRecord` (`cls` C1, `INJECTION_C1` is mapped in `injection_rng`); there is no observed-stream stage for C1 (the injectors act on the latent assembly), so only the spec, record, log, `injection_sub_index`, `injection_rng` and the design loader are reusable. `record_to_ground_truth` always sets `template_id` None: the template of a C1 truth is T10's. The double-take confounder needs `confounder_group` on the bounce spec and, for the content-sensing variant, `InjectionContext.dispenser_content_sensing` plus a `content_change` on the real dispense (the base emits none). The declined-task outcome is still a new `vocab.OUTCOMES` member.
- **T10.** `ground_truth_events(records)` gives the C2 and C3 events (realised only); `end_ms` is the window end for a window fault and None for a bounce and for a per-tick fault (onset = the tick); the log is `injection_log(records)` (keys `cls, subtype, onset_ms, duration_ms, end_ms, magnitude, magnitude_unit, params, level, confounder_group, realised, n_changed, evidence_paths, details`).
- **T11.** Per day: `apply_observation_injections(stream, specs, InjectionContext(patient_index, library=, latent=, task_deadline_offset_ms=<registry sched_window>, dispenser_content_sensing=, cuff_start=<previous next_cuff_seq>, dispenser_start=<previous next_dispenser_seq>))`, then `finalize_observed(result.stream)`; `result.stream.settings` has `next_cuff_seq`, `next_dispenser_seq`, `injection_n_records`, `injection_n_realised`, `injection_disabled_subtypes` (manifest key `disabled_subtypes`). Specs come from `load_injection_design` (rows `awaiting_human_value` give `value` None and `resolve_magnitude` refuses them), `resolve_magnitude(level, reference_value, reference)` with the prior or registry value of the quantity the level names (`level.reference`, e.g. `cuff_bias_mmhg` for the level `device_bias` inside a block whose other levels are multiples of `cuff_error_sd_mmhg`; a wrong or absent reference is an `InjectionDesignError`, and a millisecond quantity comes back rounded to whole ms), and `plan_dispenser_bounces`; the plan stream is `INJECTION_PLAN`. The robot `colocated` report is still nobody's (add the key to `vocab.py` when you emit it).
- **T12.** The realisation rate is `sum(r.realised) / len(records)` over `result.records`; unrealised records carry `details["reason"]` or `details["disabled"]`.
- **WS07-T05.** `EVIDENCE_SIGNATURES` is the catalogue's union per subtype (compare as sets; `system.nav_task_failed` holds only under H-OVERRUN, the LC and SEQ paths of `ble_dropout` only when their conditions hold); `nav_delay` is per tick here and a window in your schedule (OP-15); the other subtypes of your list (`process_kill`, `message_drop`, `localisation_noise`, `impossible_goal`, `uncommanded_lifecycle_transition`) are not injected by the benchmark; your `late` outcome must be stamped with the deadline (rule vi) and one outcome per obligation.

Verification (final report of the worker has the commands and exit codes). Mutation self-check on copies under `/tmp` (deleted): about 240 distinct mutants over three rounds (pipeline order, numbering position, every window edge, bias sign and scale, stuck-at value source, detached signature, ECG sign, scale and quality, disabling, bounce gap, content change, probability, nav shift, `late` rule and stamp, latent re-read, manipulation removals and witness coverage, ground-truth fields, `end_ms` rules, spec validation branches, bounds, vocabulary, signatures against the catalogue, record fields, design loader); every survivor of the first two rounds got a test and was killed in the third; one equivalent survivor remains (removing `validate_day` in `finalize_observed`: `_check_stream` already enforces the same). Filled-state proof: all 52 awaiting rows of `configs/priors/literature_hypertension.yaml` and `configs/benchmark/*.yaml` filled with fixture-only values in a `git archive` copy, table regenerated there, full suite 2068 passed.

### Fix round 1 (orchestrator, 2026-10-06; independent read-only review, then TDD)

The review found no blocker and no leak of ground truth into an `ObservedDay` (a day written with `write_observed_day` read back equal; the `nav_delay` re-read of `bp` writes `latent(new) + record.error_mmhg`, the same formula as the base stream, bit-identical when the latent value is unchanged). Output is deterministic (9 runs with shuffled specs and different `PYTHONHASHSEED`: one hash), layering and exports are intact. Defects fixed, each with a test that failed first (the last block of `tests/benchmark/test_inject_c2.py`):

1. `canonical_order` raised a raw `TypeError` when two specs differed only in the type of a param value (`kind="measurement"` against `kind=5`): the sort key compared raw values. The params part of the key is now a tuple of strings (`repr(key)`, type name, `repr(value)`), sorted by key, so the order is also independent of the order of the params.
2. `resolve_magnitude` returned `990000.0000000001` for `1.1 * 900000`, which the `nav_delay` spec check refused ("whole number of ms"): the documented path of the builder failed. `LevelRow` now carries `quantity_unit` (the unit of the block) and a quantity in ms is rounded to whole ms.
3. The level `device_bias` is a multiple of `cuff_bias_mmhg` inside a block whose reference is `cuff_error_sd_mmhg`, and `resolve_magnitude(level, value)` took the value of whatever reference the caller passed (7.0 instead of the bias). New signature `resolve_magnitude(level, reference_value, reference)`: `reference` is the name of the quantity `reference_value` is the value of; `LevelRow.reference` derives it from the unit (`"x <name>"`); a mismatch or an absolute row (no reference) is an `InjectionDesignError`. Contract note for T11: the hand-over text above is updated.
4. `injection_sub_index` hashed an omitted default target as `None` but an explicit `target="ecg"` as `"ecg"`, so a design-loaded spec and a hand-written one drew different noise. The default target is now resolved through the injector (`_target_of`) before hashing. The pinned digest of the `ecg_noise` spec without target changed from 101811575 to 3505845073 (no benchmark exists yet, T11 is blocked, so no data changed).
5. Two cuff attempts at one instant (a delayed visit landing on another attempt, both detached) produced `[MISSED 2, MISSED 3, ERROR 3, ERROR 3]`: a duplicate `(DEVICE_ERROR, seq)` that a monitor reads as replay. `assign_device_seq` (in `measurement.py`, T06) now pairs the n-th error of an instant with the n-th missed attempt of that instant; with no missed attempt waiting it keeps the previous rule (the last attempt).
6. `_has_number` walked a YAML alias bomb as a tree (exponential; no result after 8 s for nine alias levels). It now keeps the ids of the nodes already walked.
7. (MINOR 10 of the review) The cuff error code `cuff_detached` equalled the ground-truth subtype name; the generator-defined code is now the opaque `CUFF_E01` (a test requires that it is no subtype name and contains none).

Not changed, recorded for the owners (suspected by the review, not reproduced as a failure, each needs a decision):

- **Late rule for dose visits.** `nav_delay` uses `deadline = tick + task_deadline_offset_ms` for every visit; the INT obligation of a dose tick has deadline `t_{k_up(a)}` (`docs/formal/02-templates.md` section 5.3), so `kind="dose"` can under-report `late`. To reconcile with WS07-T05 and hypothesis H-OVERRUN of `evidence-channels.md` before WS07 uses the benchmark.
- **Pulse after a long delay.** The pulse keeps its value while `hr_ecg` is read at the new instant; with a delay of more than one vitals period `cross_device.pulse_vs_ecg_hr_diff` could rise although the fault model does not list it for `nav_delay` (decision recorded in the completion note, item "nav_delay re-reads bp"). Revisit if the evidence for `nav_delay` is audited (WS02-T05).
- **`nav_delay` without a latent day** keeps the old `bp` and records only `details["reread_latent"] = False`; T11 always passes the latent day, so this is a convenience for tests, not a path of the builder.
- **Extra intakes for a later robot.** The base stream emits only the intakes the original visit witnessed; a delayed robot that would witness more of them does not add any (`_drop_unwitnessed_intakes` only removes). Recorded limitation of the injection (conservative: fewer witnesses).

Verification after the fixes (fresh, 2026-10-06): `pytest tests/benchmark/test_inject_c2.py -q` 338 passed; `pytest -q` (whole repository) 2075 passed; `ruff check src tests` and `ruff format --check src tests` clean; `mypy src/ralmon` no issues in 35 files; `python -m ralmon.benchmark.priors --check-table` exit 0; `grep -c 'cuff_silent_bias' configs/benchmark/injections.yaml` prints 13.

### Post-task review (orchestrator, 2026-10-06)

Produced: `injection.py` (machinery: specs, canonical order, pipeline, ground-truth mapping, design loader), `inject_c2.py` (the eight C2 subtypes), `vocab.py` and `measurement.py` extensions, `configs/benchmark/injections.yaml` (28 C2 rows, 27 `awaiting_human_value`), 338 tests.
Deviations: one file outside "File toccati" (`measurement.py`, see the completion note, and its `assign_device_seq` fixed in round 1).
Impact on dependents: WS04-T09 still waits for WS04-T08 (`ready`); WS04-T11 and WS04-T10 wait for their other dependencies. Open hand-overs: `resolve_magnitude` signature (above), the robot `NODE_STATE colocated` report still has no owner (proposed WS04-T11), the four recorded limitations above.
Open MINOR: none beyond the recorded limitations.
