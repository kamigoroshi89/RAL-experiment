---
id: WS04-T06
title: "Measurement process: schedule, cuff error, HR and SpO2 from public real-noise data"
workstream: WS04-benchmark
owner: agent
status: ready
depends_on: ["WS04-T04", "WS04-T05", "WS05-T02", "WS00-T09"]
critical_path: true
non_negotiable: false
estimate_pd: 2.5
sources: ["analisi §5.1 (2)", "analisi §5.1 (public sources)", "analisi §5.2 (robot arrival jitter)"]
interfaces: ["02-interfaces.md#trace-schema"]
review_items: []
---
## Obiettivo

Turn a complete latent day into the fault-free **observed base stream** that the injectors of T07 to T09 will corrupt: care-plan schedule ticks (SCHEDULE_TICK events), robot arrival jitter, cuff measurements with the device error model (bias and SD), nominal cuff inflation and health signals, cuff pulse rate, dispenser events as the device reports them, robot presence and witnessed INTAKE, and heart rate and SpO2 taken from public real segments. Also define the event payload vocabulary (`vocab.py`) and the public-source mapping document. Concrete output: `measurement.py`, `segments.py`, `vocab.py`, `docs/benchmark/public-sources.md`, tests.

## Contesto

- `docs/source/analisi.md` §5.1 (2) (schedule, robot arrival jitter "preso dalla simulazione (§5.2)", cuff error consistent with ISO 81060-2 "verificate i valori", heart rate and SpO2 "da segmenti reali") and §5.1 (public sources: VitalDB, BIDMC PPG and Respiration, MIT-BIH, Noise Stress Test Database).
- `02-interfaces.md#trace-schema` (`Sample`, `Event`, `EventKind`) and `02-interfaces.md#signals` (`SignalId`; rule: `PRESENCE` and `INTAKE` exist only while the robot is co-located, absence is not a zero).
- `docs/plan/workstreams/WS00-admin/outputs/WS00-T04.md` sections `## Open-access datasets` and `## Data handling constraints` (licence and redistribution terms; read if they exist).
- `docs/benchmark/parameter-provenance.md` (rows `cuff_error_sd_mmhg`, `cuff_bias_mmhg` and the design rows this task adds) and the outputs of WS04-T04 and WS04-T05.
- `docs/models/evidence-channels.md` (WS02-T03, if it exists: trace evidence conventions table for payload keys).

Unblocked when WS04-T04 and WS04-T05 are `done`; `SignalId` needs WS05-T02 (see README issue I2). Open-access data is not required for the tests, which use inline fixture segments.

## File toccati

- `src/ralmon/benchmark/measurement.py` (create).
- `src/ralmon/benchmark/segments.py` (create).
- `src/ralmon/benchmark/vocab.py` (create).
- `tests/benchmark/test_measurement.py` (create; covers segments too).
- `docs/benchmark/public-sources.md` (create).
- `configs/benchmark/generator_design.yaml` (modify: rows `inflation_ms_nominal`, `inflation_ms_sd`, `pulse_error_sd_bpm`, `robot_dwell_ms`, `vitals_period_ms`).

## Test

Fixture-only arithmetic: constant latent SBP 130 on a 60 000 ms grid, ticks at 08:00 and 20:00, nominal inflation 30 000 ms, dwell 600 000 ms. Write first.

1. `test_measurement_times_follow_schedule_without_jitter`: with `NoJitter` the tick 08:00:00 gives a robot arrival at 08:00:00 and a MEASUREMENT event and `bp` sample at 08:00:30 (arrival plus inflation).
2. `test_zero_error_cuff_is_identity`: bias 0 and SD 0 give `bp = 130` exactly.
3. `test_cuff_bias_shifts_value`: bias 3, SD 0 gives 133 exactly.
4. `test_cuff_error_statistics`: 20 000 measurements, seed 0, SD 5: mean within `4 * 5 / sqrt(20000)` of the bias and sample SD within four standard errors (`5 / sqrt(2 * 20000)`) of 5.
5. `test_cuff_noise_indexed_by_measurement_not_by_time`: delaying one measurement (as `nav_delay` will) leaves the noise draws of all other measurements unchanged (stream key includes the measurement index).
6. `test_empirical_jitter_uses_file_and_records_hash`: a jitter file with `delays_ms` equal to `[0, 60000, 120000]` yields delays only from that set; the descriptor equals `file:` plus the file's sha256.
7. `test_no_jitter_records_none_source`: the descriptor is `none`; negative delays in a file raise `MeasurementConfigError`.
8. `test_observed_base_signals_and_order`: per measurement the stream holds the samples `bp`, `inflation_ms`, `cuff_health` (1.0), `hr_pulse` and one MEASUREMENT event; `meas`, `dispense`, `intake` and `sched_tick` never appear as samples (the monitor derives those impulses from events with `event_to_sample`, WS05-T02, so a duplicate would be counted twice); one `day_end` sample of value 1.0 exists per day at the instant fixed by the day-boundary rule of WS01-T01; samples and events are sorted by `t_rx_ms`; `t_rx_ms == t_device_ms`.
9. `test_dispense_events_pass_through_from_latent`: observed DISPENSE times equal the latent DISPENSE times (fault-free), source `dispenser`, payload only the keys declared in `vocab.py`.
10. `test_intake_witnessed_only_during_robot_visit`: a latent intake inside the visit `[arrival, arrival + dwell]` yields an observed INTAKE event (source `robot`); an intake outside yields nothing; no INTAKE is ever copied from the latent stream directly.
11. `test_presence_sample_only_during_visit_no_zeros`: `presence` samples of value 1.0 exist at arrivals only; no zero-valued presence sample exists anywhere (contract `#signals` rule).
12. `test_delayed_dose_outside_visit_is_not_witnessed`: a dose delayed beyond the dwell has a DISPENSE event but no INTAKE and no presence.
13. `test_hr_spo2_from_segments_with_ids_recorded`: with an inline library (values 70, 71, 72, ... fixture), `hr_ecg` and `spo2` samples equal the segment values on the vitals grid; the returned settings list the segment ids and `join_count`.
14. `test_missing_segments_error_unless_allowed`: an empty library raises `SegmentUnavailableError`; with `allow_no_segments=True` no HR or SpO2 sample is emitted and `settings["segment_source"] == "none"`.
15. `test_segment_index_requires_provenance_fields`: an entry without `licence`, `dataset`, `record_id` or `sha256` raises `SegmentIndexError`; a file whose hash differs from the index raises the same error.
16. `test_segment_paths_confined_to_root`: an index path containing `..` or an absolute path raises `SegmentIndexError`.
17. `test_latent_day_not_mutated`: the input `LatentDay` is equal (`==`) before and after.
18. `test_assign_device_seq_per_device`: after `assign_device_seq`, cuff samples and dispenser events each carry their own strictly increasing counter starting at 1; robot events keep `seq = None`.
19. `test_payload_keys_declared_in_vocab`: every payload key emitted in tests 1 to 18 is a constant of `vocab.py`.
20. `test_design_rows_have_provenance`: every row this task reads from `generator_design.yaml` has `source_type` and `source_ref`.
21. `test_fault_free_inflation_not_below_registry_minimum`: with a fixture minimum of 30 000 ms (registry entry `cuff_inflation_min`, passed as an argument) no fault-free inflation draw is below it; draws that had to be raised are counted in the returned settings (so that a fault-free day cannot violate φ_SYS by generator construction).

## Passi

1. Write `tests/benchmark/test_measurement.py`; run it, confirm failure; commit `WS04-T06: add failing measurement tests`.
2. Write `vocab.py`: the payload keys and values this task emits: `SCHEDULE_TICK` with `kind` (measurement or dose), `DISPENSE` with the optional `content_change`, `INTAKE` with `witness`, `ROBOT_TASK` with `task` and `outcome`. If `docs/models/evidence-channels.md` already has the trace evidence conventions table, take the names from it; otherwise mark the module docstring "provisional until WS02-T03" and let T07 add the conformity test.
3. Implement `segments.py`: `SegmentIndex` (JSON entries `segment_id`, `dataset`, `record_id`, `kind` in `hr_clean`, `spo2_clean`, `hr_error_ecg_noise`, `sample_period_ms`, `n_samples`, `unit`, `path`, `sha256`, `licence`), `SegmentLibrary(root, index)` with path confinement and hash verification, and `draw(kind, n_samples, rng)` returning the segment ids and values, preferring segments long enough to cover the request and counting joins otherwise. Segment files are never committed (`data/raw/` is gitignored) and are produced outside this task (H2): T06 defines the file format, not the extraction from raw PhysioNet records.
4. Implement `measurement.py`: `ArrivalJitterModel` protocol with `NoJitter` (default) and `EmpiricalJitter(path)` reading a JSON file exported by the WS07 simulation (`delays_ms`: list of nonnegative integers, `source`: string naming the simulation run), plus `jitter_descriptor()`; `CuffModel` (Gaussian with bias and SD from `DeviceErrorModel`, family declared); `RobotVisit`; `build_observed_base(latent, schedule, care_plan_id, device_errors, design, jitter, library, seed, patient_index) -> ObservedStream` (samples, events, visits, measurement records and a settings mapping for the manifest); `assign_device_seq(stream)`. The latent value at an instant is the last grid value at or before it (piecewise-constant hold, consistent with the monitor). A fault-free ECG heart rate and SpO2 equal the clean segments; noise enters only through the C2 fault `ecg_noise` (declared simplification). Only `bp`, `inflation_ms`, `cuff_health`, `hr_pulse`, `hr_ecg`, `spo2`, `presence` and the end-of-day marker `day_end` are samples; the impulses `meas`, `dispense`, `intake` and `sched_tick` are events only. Fault-free inflation draws are raised to the registry minimum `cuff_inflation_min` (argument) and counted. Use the named stream `StreamPurpose.MEASUREMENT` with the measurement index as `sub_index`, and `StreamPurpose.JITTER`, `StreamPurpose.SEGMENTS`.
5. Add the five design rows to `generator_design.yaml` (`design_choice` or `published_literature`, `awaiting_human_value` unless supplied). Regenerate the provenance table. In the provenance rows of `cuff_error_sd_mmhg` and `cuff_bias_mmhg` state that the monitor's ρ computation reads its own copy of the device error in the registry entry `cuff_error_sd` (WS01), that the matched case uses the same source value for both, and that WS08 may hand the monitor a perturbed copy as a mismatch stress.
6. Write `docs/benchmark/public-sources.md` with the H2 headings `## Purpose`, `## Sources`, `## Extraction procedure`, `## Segment file format`, `## Verification status`. `## Sources` has one row per open-access source of the README table (VitalDB, BIDMC PPG and Respiration, MIT-BIH Arrhythmia, MIT-BIH Noise Stress Test Database, PhysioNet/CinC 2015) and links to the WS00-T04 rows for licence and redistribution instead of copying them; every schema, sampling-rate and unit fact stays `unverified` until a human confirms it from the dataset page, and none is written from memory. `## Extraction procedure` lists what a human with the data runs: how a clean heart-rate segment, a clean SpO2 segment and a paired clean and noisy heart-rate error trace are produced with the dataset's own tooling, into `data/raw/segments/`.
7. Refactor, run `ruff check src tests`, `mypy src/ralmon`, `pytest tests/benchmark -q`; commit `WS04-T06: add measurement process, segment library and public source mapping`; set `status: done`.

## Done when

- `pytest tests/benchmark/test_measurement.py -q` exits 0; `pytest tests/benchmark -q` exits 0; `ruff check src tests` and `mypy src/ralmon` exit 0.
- `python -m ralmon.benchmark.priors --check-table` exits 0.
- `test -f docs/benchmark/public-sources.md && grep -c '^## ' docs/benchmark/public-sources.md` prints at least 5, and `grep -c 'unverified' docs/benchmark/public-sources.md` prints at least 5.
- `grep -rnE 'TO''DO|TB''D|lo''rem|\?\?\?' docs/benchmark src/ralmon/benchmark` prints nothing.

## Notes

Reconciliation (ADR-023): the open datasets are downloaded by a human in `WS00-T09` (which this task now depends on) into `data/raw/<dataset>/` with `SHA256SUMS`, and the signal-symbol resolution of `SignalId` comes from `WS05-T02` (also a dependency now). Agents never download data.

### Hand-over from the WS05-T02 review (orchestrator, 2026-10-05)

The `day_end` impulse must be emitted at exactly `T_day` of each day (choice M7 of `ralmon.signals`: `meas_count` day `d` covers `(d*T_day, (d+1)*T_day]`, so the closing step belongs to the day it closes; docs/formal/01-signals-sampling.md section 3.1 puts an event at exactly 24:00 on a continuing axis in the next day). Impulses are emitted only as events and mapped by `event_to_sample` (WS05-T02).

### Hand-over from the WS04-T03 review (orchestrator, 2026-10-05)

The latent day of `ralmon.benchmark.latent` has `K` points and does not emit the closing step: hold the last value or take step 0 of the next day when the measurement process needs the value at 24:00. `StreamPurpose.MEASUREMENT` takes the measurement index as `sub_index`; `JITTER` and `SEGMENTS` are separate purposes.
