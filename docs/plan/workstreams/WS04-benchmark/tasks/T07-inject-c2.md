---
id: WS04-T07
title: C2 fault injection
workstream: WS04-benchmark
owner: agent
status: blocked
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
