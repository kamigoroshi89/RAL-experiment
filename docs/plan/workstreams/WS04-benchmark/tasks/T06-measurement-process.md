---
id: WS04-T06
title: "Measurement process: schedule, cuff error, HR and SpO2 from public real-noise data"
workstream: WS04-benchmark
owner: agent
status: done
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

### Completion note (worker, 2026-10-05; status left `in_progress` for the orchestrator's review)

Files: `src/ralmon/benchmark/{vocab,segments,measurement}.py`, `tests/benchmark/test_measurement.py` (443 tests: the 21 listed plus extremes, boundaries, streams, immutability, design rows on `tmp_path` copies), `docs/benchmark/public-sources.md`, five design rows in `configs/benchmark/generator_design.yaml` (all `awaiting_human_value`, no value chosen), regenerated `docs/benchmark/parameter-provenance.md`. One file outside "File toccati": `configs/priors/literature_hypertension.yaml` (only the `note` text of `cuff_error_sd_mmhg` and `cuff_bias_mmhg`), because Passo 5 asks for the provenance wording and the table is generated from that file. No export added to `ralmon.benchmark.__init__`; no `data/raw/`; nothing downloaded.

Modelling choices (all documented in the module docstrings):

- **Latent input.** The latent pressure is read from the `bp` samples of `LatentDay.samples` (strictly increasing times); of `LatentDay.events` only the times of DISPENSE and INTAKE are read. Latent SCHEDULE_TICK, MEASUREMENT and every latent source or payload are ignored: the ticks come from the schedule, the readings from the device model. Hold = last grid value at or before the instant; before the first grid point it raises `MeasurementConfigError` (`hold_last` gives nan, never a reading); after the last point it holds the last value (the latent day has no closing step), and readings stamped after `(d + 1) * T_day` are counted in `settings["n_measurements_after_day_end"]`.
- **Visits.** One robot visit per dose tick and per measurement tick, arrival = tick + delay (jitter stream `(seed, patient, day, JITTER, 2 * index + kind)`, kind 0 measurement, 1 dose), closed dwell interval `[arrival, arrival + dwell]`. One presence sample (1.0) and one ROBOT_TASK (`navigate`, `success`, `patient_id`) per visit. A witnessed INTAKE needs a visit that covers the latent intake time; the observed INTAKE repeats that time, source `robot`.
- **Cuff.** Per measurement index `k` (position in `measurement_ticks_ms`, realised or not) the stream `(seed, patient, day, MEASUREMENT, k)` gives three normals (cuff error, inflation, pulse error), always all three, so a skipped or delayed measurement shifts nothing. Reading = latent at the reading instant + bias + sd * z0, stamped `arrival + inflation`. Inflation = round(nominal + sd * z1) raised to `design.inflation_min_ms` (the registry `cuff_inflation_min`, passed by the caller), raises counted in `settings["n_inflation_raised"]`. Pulse = clean heart rate at the reading instant + sd * z2; no heart-rate segment means no `hr_pulse` sample.
- **Vitals.** `draw_clean_vitals(library, design, seed, patient_index, day_index)` is a pure function of the key (stream `SEGMENTS`, sub 0 heart rate, 1 SpO2); a segment of another period is held to the vitals grid. A segment draw takes a uniformly drawn segment that is long enough at a uniformly drawn offset, or joins whole segments and counts the joins.
- **Day end.** `day_end` at exactly `(d + 1) * T_day` (WS01-T01 section 5.5 item 2 with the M7 choice of `ralmon.signals`); items generated from the ticks of day `d` stay in the stream of day `d` whatever their time (documented; see T11 below).
- **Sequence numbers.** `assign_device_seq` follows `docs/models/threat-model.md` "(source, name, seq)": the four cuff samples and the MEASUREMENT event of one message share one number, each DISPENSE has its own counter, everything else stays `None`. Extension beyond the task text: `cuff_start` and `dispenser_start` keyword arguments and `settings["next_cuff_seq"]` and `["next_dispenser_seq"]`, so days chain; a counter that restarts at 1 every day looks like a replay to a monitor that keeps the previous day's accepted `(source, name, seq)` (H-SEQSTATE).
- **Skipped measurements.** `build_observed_base(..., skip_measurement_ticks_ms=())` (extension): ticks the patient refuses; the robot still visits, no draw of another measurement changes. `allow_no_segments=True` tolerates a library without a kind (that kind, and `hr_pulse` without heart rate, is omitted; `segment_source` is `none` only if nothing was used).

Deviations from the task text and contract gaps:

1. **INTAKE has no payload key `witness`.** The conventions table of `docs/models/evidence-channels.md` says the INTAKE event carries no payload ("the event is the reading"); `vocab.py` follows the table and declares none (test `test_vocab_matches_the_evidence_conventions_table`). `SCHEDULE_TICK.kind` is not in the table: owned by `vocab.py`. `DISPENSE.content_change` is declared but not emitted by the fault-free base (a dispenser with content sensing is a capability of the T09 variants).
2. `ObservedStream` carries generator-side records (`visits`, `measurements` with `latent_sbp_mmhg`) next to `samples` and `events`; the injectors must write only samples and events into an `ObservedDay`. The last three fields default to empty so that T07 can hand-write fixture streams.
3. The Protocol of the jitter is `delay_ms(rng, *, kind, index)` plus a `descriptor` attribute (the task names a `jitter_descriptor()` function: provided, it reads the attribute). The jitter file needs `delays_ms` and `source` (extra keys ignored); WS07 must export exactly these. Segment index and file format: `docs/benchmark/public-sources.md`.
4. The robot co-location status (`NODE_STATE` with `colocated`, needed by the availability mask H-MASK of the evidence conventions) is not emitted here (no key declared for this task by Passo 2); `ObservedStream.visits` has the arrival and departure for whoever emits it (T07 or the builder).
5. Statistical test 4 uses 20 days of 1000 readings (20 000 measurements) of the same stream layout; each test file runs in about 1.5 s and about 100 MB.

Hand-overs (read from the task files of T07 to T11):

- **T07.** (a) Locate the visit of a measurement by `ObservedStream.measurements[i]` and `visits` (the ROBOT_TASK of a visit is the event of source `robot` at `visit.arrival_ms`; a late or failed outcome replaces its `outcome` value, with the stamp rule H-OVERRUN of EC-OP-14, which this base does not apply). (b) Test 2 "delivered seq [1, 4]" holds with the per-message numbering. (c) Test 6 needs `library.draw("hr_error_ecg_noise", n, rng)` and `library.has_kind`; `quality` comes from `SegmentDraw.quality`. (d) `vocab.py`: extend `PAYLOAD_KEYS`, `OUTCOMES` and `_ENUMERATED` rather than emit undeclared keys (`check_payload` refuses them); its conformity test against the conventions table already exists in `test_measurement.py` for the keys of this task. (e) Call `assign_device_seq` once per day with the previous day's `next_*` numbers.
- **T08.** The visit dwell for a spoofed INTAKE is `visit.departure_ms`; `hr_ecg` is on the vitals grid, held to any instant; per-message seq as above; the fresh-metadata level continues `settings["next_cuff_seq"]`.
- **T09.** The latent assembly must put the latent pressure in `bp` samples and obtain latent heart rate and SpO2 from `draw_clean_vitals` with the same `(library, design, seed, patient_index, day_index)` so they equal the observed ones; refused measurements go in `skip_measurement_ticks_ms`; the declined-task outcome is a new member of `vocab.OUTCOMES`.
- **T10.** Nothing: it reads latent data only, and the generator-side `MeasurementRecord.latent_sbp_mmhg` is for the injectors.
- **T11.** (a) Per-day `settings` keys `jitter_source` and `segment_source` match the manifest keys of T11 test 11; `library.descriptor` and `jitter_descriptor` give the run-level values. (b) A day's stream may hold items later than `(d + 1) * T_day` (jitter after midnight, an intake after midnight): decide, together with the monitor's carry-over rule (CP7), whether the builder keeps them in the day of their tick (as done here) or moves them to the next day's file; the contract does not say. (c) The registry minimum `cuff_inflation_min` must be read by the builder and passed as `inflation_min_ms` (`load_measurement_design(path, inflation_min_ms=...)`). (d) The loader raises `UnfilledParameterError` while the five rows are `awaiting_human_value`.

Verification evidence is in the final report of the worker (commands and exit codes), not repeated here.

### Fix round 1 (worker)

Review round 1 gave PASS with no blocker; the minor items below are fixed with tests written first (each red before the fix, green after). Contracts, ADRs and other task files are untouched.

Code and test fixes.

- **M3 (state pin on a human-edited document).** The test that required five `unverified` in each Sources row is replaced by a structural check (`check_public_sources` in `tests/benchmark/test_measurement.py`): the five headings, the Sources column header, every fact cell either starts with `unverified` or carries the marker `verified_by:`, every Verification-status row is `unverified` or `verified` (a `verified` row names `verified_by` and `verified_on`). The marker convention is defined in the `## Verification status` section of `docs/benchmark/public-sources.md` (no fact is invented). The test also runs on an edited copy (one fact confirmed: passes) and on copies with an unmarked fact, an anonymous verification and a missing heading or row (refused). The count of `unverified` is only the Done-when grep (>= 5), not a test pin.
- **M4 (raw `TypeError`).** Fixed: `InlineSegment` `quality` or `values` that is not a sequence or one-dimensional array (a mapping, an iterator and a zero-dimensional array were accepted or raised `TypeError`), `draw_clean_vitals(day_index=None)` (`rng.stream` accepts `None`; `_key` now requires integers), `assign_device_seq` on a stream whose `settings` is not a mapping with string keys or whose `samples` or `events` are not sequences, or whose members have an unhashable `signal` or `kind`, `os.fspath` of a path-like with a misbehaving `__fspath__` (both `_path` and `_as_path`), and `skip_measurement_ticks_ms` given as a zero-dimensional array (found by a fuzz of every public function with 30 junk values; the only remaining non-named errors are the documented `PriorConfigError` and `UnfilledParameterError` of `load_measurement_design`). A skip list of more than `MAX_VISITS_PER_DAY` entries is now refused by name.
- **M5 (duplicate JSON keys).** `object_pairs_hook` refuses a duplicate key (named errors) in the index (top level and inside an entry), the segment file and the jitter file.
- **M6 (surviving mutants).** Tests added: exact-limit and limit+1 for every bound (by `monkeypatch` of the module constant to a small value, plus one test with the real `MAX_LATENT_EVENTS` through a lazy sequence), a test that pins the documented values of the bound constants (a deliberate decision to change one), the `n_past_end` boundary at exactly `(d + 1) * T_day`, `segment_source` `none` with a library that holds only the noise kind, `long_enough` at `n_samples == count` over 40 seeds, the tie order at the closing instant (presence, cuff message, `day_end`; ROBOT_TASK, MEASUREMENT, DISPENSE, INTAKE), the order of `SCHEDULE_TICK` and visits at one instant (dose first), and a FIFO test for the index, segment and jitter files run in a child process with a timeout (a regression that opens the FIFO fails instead of hanging).
- **M7.** The vacuous `latent_day` import assertion is dropped (no such module exists; the allowlist below covers the intent). The layering test now forbids `ralmon.spec`, `conformal`, `monitor`, `attribution`, `baselines` and `eval` in all three modules and confines each to an allowlist of `ralmon.*` modules (`ALLOWED_EDGES` in `tests/test_layering.py` lets `benchmark` import `spec` and `monitor`, which is wider than these modules need; the tightening lives in `test_measurement.py` only). No module mentions `GroundTruthEvent`, `BenchmarkDay` or `TruthRecord`, and `segments.py` and `vocab.py` do not mention `LatentDay`.
- **M8.** Step 5 of the extraction procedure no longer claims tooling or mixing levels of the noise database: the human confirms them from the dataset page and they stay `unverified`.
- **M9.** `LatentDay` has a `seed`: `build_observed_base` refuses a `seed` that differs from `latent.seed` (named error, documented in the module docstring). The test helper `build` gives its latent day the seed of the build; `keep_latent_seed=True` exercises the refusal.
- **M1.** Test that `latent_sbp_mmhg` exists only in `MeasurementRecord`, that `ObservedDay` has no latent, `measurements`, `visits` or `settings` field, and that nothing observed mentions "latent". There is no `ObservedStream` to `ObservedDay` conversion yet: the test is a fields assertion; WS04-T11 should extend it to the conversion it writes.

Open hand-overs (notes only, no code).

- **M2 (owner to assign).** No fault-free base task or WS04 task emits the robot `NODE_STATE` report with `colocated`. H-INIT and H-MASK of the evidence conventions make `presence` and `intake` unavailable until it exists. Proposal: WS04-T11 emits it from `ObservedStream.visits` unless WS04-T07 decides otherwise; the owner is to be assigned (T07 or T11).
- **M10 (for T07).** A dose tick and a measurement tick at the same instant give two visits: two ROBOT_TASK events and two presence samples at one instant. This is the documented behaviour (see the tie rule), not a duplicate.
- **M11 (for T07).** `SCHEDULE_TICK.kind` and the sources `ward` and `cuff` are not in the evidence-channels table: T07 test 19 ("each key also in the table") must cover only T07's own keys, or the table must be extended. `vocab.PAYLOAD_KEYS` must be extended for the `NODE_STATE` and `DEVICE_ERROR` keys. `assign_device_seq` overwrites every cuff `seq`, so T08 must not call it after replay injection.
- **T09.** A new `OUTCOMES` member is needed for the declined-task outcome.
- **T10.** The `day_end` instant is exactly `(d + 1) * T_day` (WS05-T02 M7); T10's wording says only "end of the day".
- **T11.** Pass the registry `cuff_inflation_min` as `inflation_min_ms`; `load_measurement_design` raises `UnfilledParameterError` while rows are unfilled; items after `(d + 1) * T_day` stay in the day of their tick, and a day-d intake after midnight cannot be witnessed by a day-(d + 1) visit (carry-over rule CP7).

### Post-task review (orchestrator, 2026-10-05)

Produced: `vocab.py`, `segments.py` (segment index and library, fixture-driven), `measurement.py` (observed base stream: schedule ticks, jitter, cuff with device error, dispenser pass-through, witnessed INTAKE, presence, HR and SpO2 from segments), `docs/benchmark/public-sources.md` (all facts `unverified`), five design rows `awaiting_human_value`. Independent review: PASS, no blocker (1400 random fixtures against an independent reference, 0 mismatches; about 10 000 fuzz calls; 114 mutants). One fix round closed raw `TypeError` sites, duplicate JSON keys, a state-pinning doc test, mutant gaps and the seed check. Orchestrator verification on the final branch: `test_measurement.py` 514 passed (101 MB peak), full suite 1737 passed, ruff, format, mypy, `--check-table`, `check_plan` exit 0, public-sources greps 5 and 21, forbidden-words grep empty.
Deviations: INTAKE has no `witness` key (evidence-channels table prevails); only the `note` text of two prior rows changed (Passo 5 wording); extensions to the task API (`cuff_start`, `dispenser_start`, `skip_measurement_ticks_ms`, `allow_no_segments`, `draw_clean_vitals`).
Impact on dependents: WS04-T07 and WS04-T08 are now `ready`. Open hand-overs (details in "Fix round 1" above): nobody yet emits the robot `NODE_STATE colocated` report (proposed owner WS04-T11 unless WS04-T07 decides otherwise); `vocab.PAYLOAD_KEYS` needs the T07 keys; T08 must not call `assign_device_seq` after replay injection; T10 and T11 notes on `day_end` and items after midnight. `ObservedStream` carries latent values in `measurements`/`visits` (never to cross to `ObservedDay`).
Open MINOR: none beyond the hand-overs.

### Hand-over from the WS05-T04 review (orchestrator, 2026-10-10)

Append-only note on a done task. The presence stream of this task (test 11: samples of `1.0` at robot arrivals only, no zero) combined with the monitor of WS05-T04 leaves INT blind after the first robot visit of a generated day: `presence` is a held level (docs/formal/02 section 4.7, TG-9), so the level of the last visit is read at every later dispense. Reproduced with this task's own fixture `test_delayed_dose_outside_visit_is_not_witnessed` (a dose at 08:15 after the 08:00 visit has no INTAKE and no presence) through `run_offline_detailed`: `int@29700000` is SATISFIED with `[300000, 300000]` and `stats().presence_level_older_than_window_steps` is 955. The monitor now clears the level at an outage that is marked (`push_availability`), but a generated day has no mark. What is needed is decided in ADR-054 (proposed `[DA-CONFERMARE]`): recommended option (b), a robot `NODE_STATE` report with `payload.colocated` true at each arrival and false at each departure (the M2 item of the Fix round 1 above, the owner is still open); option (a) would change test 11 (an explicit `0.0` at departure) and the `#signals` rule. Until then no INT-based result on a generated day is evidence. Also: the `day_end` Sample of test 8 was refused by `push_sample` and aborted `run_offline` on every generated day; the monitor now ignores it and counts it (`stats().ignored_samples`), nothing to change here.
