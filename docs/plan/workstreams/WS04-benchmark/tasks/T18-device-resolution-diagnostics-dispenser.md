---
id: WS04-T18
title: "Generator: cuff resolution (rounding), driver diagnostics reports under two device profiles, dispenser interval, ADR-040 conventions (ADR-074)"
workstream: WS04-benchmark
owner: agent
status: in_progress
depends_on: ["WS05-T13", "WS04-T16"]
critical_path: true
non_negotiable: false
estimate_pd: 3
sources: ["ADR-032", "ADR-040", "ADR-074"]
interfaces: ["02-interfaces.md#trace-schema", "02-interfaces.md#evidencevector"]
review_items: []
---
## Obiettivo

Make the generator emit what the evidence fields of `#evidencevector` 0.2.0 read, under declared device profiles. (1) Round the cuff readings (`bp` and the cuff `hr_pulse`) at the device boundary to the device resolution, a device-profile parameter with default 1 mmHg / 1 bpm; the resolution is also what the extractor's `cuff_value_repeated` assumes (prototype: natural repeat probability 0.0197 for the generator's noise, 0 without rounding; this is a property of the generator, not of a real cuff). (2) `NODE_STATE` `diagnostics` reports of the device driver under the liveness contract of `docs/models/evidence-channels.md` ("Bridge node: liveness contract"): `ok` at start and each driver period for every device with the capability; an idle on-demand device never reports `stale`; `stale` only after the lease with an open session or a continuous device; the profile 'driver with diagnostics' and the profile 'without' are two named profiles in the manifest. `stale_lease_ms` and the driver period are profile parameters without default (`awaiting_human_value`); a run with the profile 'driver with diagnostics' and an unset lease fails loudly. (3) `DISPENSE` payload `interval_since_previous_ms` (the generator emits none today) and `content_change` before minus after, release positive, bounce zero (ADR-040 (2)); the informed attacker's forged dispense copies the bounce timing as in the pair prototype. (4) ADR-040 (3): the builder (WS04-T11) writes `colocated` True/False for the robot visits in variants with the robot, none otherwise; verify and fix. (5) Goldens move: list every file that changes and why.

## Contesto

`docs/benchmark/evidence/likelihood-attribution.md` sections 9 and 10 and `docs/benchmark/evidence/scripts/likelihood/` (the research copy with the switch `RALMON_DRIVER_DIAG`, the rounding at the device boundary, and the pair variants), `docs/benchmark/evidence/pairs-allocation.md`, ADR-032, 040, 074, `src/ralmon/benchmark/{measurement,base,inject_c2,inject_c3,confounders,builder}.py`.

## File toccati

`src/ralmon/benchmark/measurement.py`, `base.py`, `inject_c3.py`, `builder.py`, `configs/benchmark/generator_design.yaml` (profile rows as `awaiting_human_value` where no value exists), `docs/benchmark/builder.md`, `tests/benchmark/**`, the golden files that move.

## Test

1. `test_cuff_readings_are_multiples_of_the_resolution` (default 1; resolution 5 gives multiples of 5).
2. `test_fault_free_repeat_rate_matches_the_rounding_formula` (seeded; within the binomial interval of the analytic value).
3. `test_idle_cuff_never_reports_stale_over_24h`.
4. `test_open_session_with_stopped_publisher_goes_stale_after_the_lease`.
5. `test_profile_without_diagnostics_emits_no_diagnostics_report`.
6. `test_unset_lease_with_diagnostics_profile_fails_loudly`.
7. `test_dispense_payload_has_interval_and_signed_content_change`.
8. `test_bounce_has_content_change_zero_and_release_positive`.
9. `test_colocated_events_follow_the_robot_visits`.
10. `test_rounding_does_not_change_ground_truth` (latent trace and truth unchanged; observed readings are the rounded ones).

## Passi

1. Tests first. 2. Rounding. 3. Diagnostics reports and profiles. 4. Dispenser payload. 5. `colocated`. 6. Regenerate goldens and list them.

## Done when

`pytest -q`, `ruff check src tests`, `ruff format --check src tests`, `mypy src/ralmon` exit 0; `python3 tools/check_plan.py` exits 0.

## Notes

### Hand-over from WS05-T13 (`#evidencevector` 0.2.0, 2026-10-11)

- The `dispenser_bounce` sidecar declares the paths `dispenser.interval_since_previous_ms` and `dispenser.content_change`, and `stuck_at` declares `signal_quality.cuff_value_repeated`. The declaration is conditional by design (the fault-model union of raised and conditional fields). The generator does not raise `interval_since_previous_ms` until this task emits the key, so a sidecar generated before this task declares a path that the trace cannot show; benchmarks generated before WS05-T13 also carry the old empty signatures and `seq_gap_or_replay` and must be regenerated.
- The cuff resolution parameter that the generator rounds to must be the same value that the run's `DeviceProfile` gives the extractor as `cuff_resolution`; nothing else couples them, and a profile without it makes `cuff_value_repeated` `None`.
- Emit `interval_since_previous_ms` as an `int` >= 0, omit it for the first opening of a stream and across midnight, and keep `content_change` before minus after (+1.0 for a release, 0.0 for a bounce). Give each DISPENSE its own `seq`: a re-sent copy with the same `seq` is skipped by the extractor.

### Hand-over from WS04-T16 (worker, 2026-10-11): what the anchored cuff faults change for this task

- **Rounding and `stuck_at`.** The injector freezes the last earlier reading it finds in the stream (or the last `bp` sample of `InjectionContext.previous_day`, ADR-070 (d)) and counts a window sample as changed only when its value differs from the frozen one. If the cuff resolution rounds the readings at the device boundary (before the injectors run), a covered reading that equals the frozen value by chance (the natural repeat probability of the prototype, about 0.02 at 1 mmHg) is not changed, and a `stuck_at` window of k = 1 whose single reading equals the frozen value is unrealised although `details.n_readings_covered` is 1. The realised share of k = 1 therefore falls by about that probability. Decide, and record, whether the share is acceptable or `realised` for `stuck_at` should become `n_readings_covered > 0`; do not change it silently (the test `test_realised_share_is_one_for_detached_and_bias` is for the other two subtypes, and the `stuck_at` share is pinned on days 1 to 6 with values that differ by construction).
- **`cuff_value_repeated` across midnight.** A `stuck_at` window that precedes the first reading of the day freezes the last reading of the PREVIOUS evening (`details.frozen_from == "previous_day"`). The repeated value is then split over two days: the first reading of day d repeats the last reading of day d-1. An extractor that reads one day alone, or a baseline that resets its state each day (ADR-061), cannot see that repeat; the extractor of `cuff_value_repeated` must carry the last cuff value across the day boundary, or the declared signature of `stuck_at` is not raised for these windows. The rounding must be applied to the previous day's stream in the same way (the frozen value is taken from the stored post-injection stream, so it is already a rounded value).
- **Diagnostics under detachment.** `cuff_detached` windows now cover k readings by construction (the injector's `details.n_attempts` equals `n_readings_covered`), so the reports of a driver that stays `ok` while the cuff attempts fail (or goes stale after the lease) have exactly k failed attempts to follow; the window is anchored to the readings of the day, not to the driver period.
- **Dispenser interval.** Not touched by this task: the dispenser stream, `dispenser_bounce` and its payload are unchanged. The only coupling is the order of the device stage (`cuff_detached`, `cuff_silent_bias`, `stuck_at`, `ecg_noise`, `dispenser_bounce`), which is unchanged.
- **Records and the manifest.** The three cuff subtypes add the reading ledger (`n_readings_drawn`, `n_readings_lost_robot`, `n_readings_removed_robot`, `n_readings_gained_robot`, `n_readings_lost_device`, `n_readings_covered`, written by the injectors) to `details` and `settings.anchored_cuff_faults` to the manifest; a record of another subtype is unchanged. Benchmarks generated before WS04-T16 have uniform windows and no such keys and must be regenerated.


### Worker notes (WS04-T18, 2026-10-11): what was built, the judgment calls, the pins that moved

Built (branch `ws04-t18-device-resolution-diagnostics`; the status is NOT set to done here): `src/ralmon/benchmark/device_profile.py` (new: `GeneratorDeviceProfile`, `DriverDiagnostics`, the rounding, the driver rule `driver_reports`, `UnsetDriverParameterError`), `vocab.py` (keys `diagnostics`, `interval_since_previous_ms`), `measurement.py` (`assign_dispense_intervals`), `injection.py` (`InjectionContext.device_profile`, interval and driver steps of the pipeline, rounding in `finalize_observed`), `inject_c3.py` (forged `DISPENSE` interval), `confounders.py` (`PairBase.device_profile`, the pair comparison reads the interval), `builder.py` (the `device_profile` section, the two awaiting rows, the manifest), `configs/benchmark/{default,generator_design}.yaml`, `docs/benchmark/{builder,parameter-provenance}.md`, `tests/benchmark/test_device_profile.py` (26 test functions, 32 cases: the 10 tests of this task and 16 more). `DISPENSE.content_change`, `NODE_STATE.diagnostics` and `DISPENSE.interval_since_previous_ms` are all in the conventions table of `evidence-channels.md`; no payload key outside it was added and `02-interfaces.md` is untouched.

Judgment calls (conservative readings):

1. **Rounding is in `finalize_observed`, after the injectors, and the stream is not touched.** The next day's `previous_day` is the unrounded post-injection stream, so `stuck_at` still freezes an unrounded value and its realisation (a covered reading that differs from the frozen one) is decided BEFORE the display. The hand-over concern of WS04-T16 (a `stuck_at` window of k = 1 whose reading equals the frozen value by chance, about 0.02 at 1 mmHg) therefore does not arise: `realised` keeps its meaning and the realised share of ADR-070 is not lowered; nothing in `inject_c2` changed. The frozen value is displayed as the rounding of the previous evening's unrounded reading, i.e. exactly the value shown the evening before, so the repeat across midnight exists in the shown data and is read only by an extractor that carries the last cuff value across the day boundary (D-16 does; a baseline that resets each day, ADR-061, cannot see it).
2. **The profile is declared configuration**: the `device_profile` section of the build configuration (optional keys `cuff_resolution_mmhg`, `pulse_resolution_bpm`, `dispenser_reports_interval`, `diagnostics_profile`; defaults 1.0 / 1.0 / true / `without_diagnostics`; `null` for a resolution means no rounding, the pre-T18 behaviour). The library calls without a profile (`finalize_observed(stream)`, an `InjectionContext` without `device_profile`) keep the old behaviour; only the builder passes it, so the low-level tests did not move. `dispenser_reports_interval` is an addition of mine (a capability toggle next to `dispenser_content_sensing`, so that a dispenser without the interval stays a sensitivity case; the extractor reads `None`).
3. **Sessions and `stale`.** A session is derived from what the device SENT (the stream before the link stage): a cuff reading's session opens at the reading instant minus its `inflation_ms` and closes at the reading; a dispenser opening is instantaneous; a message lost by a dropout leaves the session open until the gateway reports the link `active` (or another message arrives). `stale` is strictly MORE than the lease (first stale ms = open + lease + 1), a report marks the first stale ms and the recovery besides the periodic ones. A refused measurement, a manipulation failure or an omitted dose sends nothing and opens no session: C1 events never make a device stale (checked: in a 40 x 7 build every day with a stale report has a realised `ble_dropout` of that device). Derived from the stream and the node reports only, never from a record. The lease must exceed the nominal start-to-reading time of the cuff (inflation 30 s in the committed rows) or every reading shows a short `stale`. `ecg` and `oximeter` (continuous) are supported by the rule and the profile (`devices`), but the default `devices` are the two devices the templates read (`cuff`, `dispenser`), as in the research copy.
4. **`warn` and `error` are not produced.** The fault model attributes no fault to `system.diagnostics_ok` (OP-4) and the contract says they come from the device's own status; reusing `cuff_error_code`/`DEVICE_ERROR` would raise a new field for `cuff_detached` (a new fault semantic). The vocabulary accepts all four levels. `EVIDENCE_SIGNATURES` in `inject_c2.py` is unchanged: under the driver profile a `ble_dropout` over a message (and only then, and only if the outage outlasts the lease) can also raise `system.diagnostics_ok` (False), a CONDITIONAL path that the fault-model table does not list; WS02-T06 should treat it as a profile-dependent cell, not as a signature change.
5. **The two rows have no default and are conditional.** `driver_period_ms` and `driver_stale_lease_ms` are `awaiting_human_value` rows of `generator_design.yaml` (`awaiting` 46 to 48). The build check ignores them while the profile is `without_diagnostics` (so a build is not blocked by rows it does not read) and refuses with `UnfilledParameterError` naming them under `driver_with_diagnostics`; the library raises `UnsetDriverParameterError`. The tests use `GENERATOR_VALUES` of `test_builder.py` (1 h and 10 min, labelled TEST VALUE).
6. **Dispense interval.** Computed on the openings the device made, in order of device time, after the numbering and before the link stage: a lost opening still counts for the next one and a forged opening never does. Absent for the first opening of the stream (a stream is a day, so across midnight too). The forged `DISPENSE` carries the interval the stream gives at its onset at BOTH levels (naive: whatever the stream gives; informed: it copies the bounce timing by where it is placed, so one bounce gap after a real opening it reports the bounce gap, as in the pair prototype); the forged event keeps no `content_change`. The fourth pair group of the research copy (`bounce_vs_forged_dispense`) is NOT added: it is outside this task. `compare_observed` now includes the interval key in its dispense-timing field (a pair whose members differ only in a reported interval is distinguishable); no test pinned a pair flag, none changed.
7. **`colocated` (ADR-040 (3)) was already implemented** by WS04-T11 (`BuildContext._reports`, `_with_reports`, the pair path through `_finish_pair_member`): True at each arrival, False at the departure of each run of overlapping visits, none in a variant without the robot. Nothing to fix; `test_colocated_events_follow_the_robot_visits` now pins it for a normal patient and for the twins of a robot and a no-robot variant.

Goldens and pins that moved (no golden file of the repository is produced by the generator; the monitor, spec and conformal goldens are untouched): `tests/benchmark/test_builder.py` `test_manifest_records_revision_provenance_and_settings` (the manifest `device_profile` now has the five new keys), `tests/benchmark/test_values_group1.py` (`AWAITING_DESIGN` +2, `AWAITING_NOW` 46 to 48, test renamed `..._other_48`: the two driver rows), `tests/benchmark/test_inject_c2.py` and `tests/benchmark/test_c1_confounders.py` (the import allow-lists of `injection.py` and `confounders.py` gain `ralmon.benchmark.device_profile`), `docs/benchmark/parameter-provenance.md` (regenerated: 96 rows, 48 awaiting). Benchmarks built before this task differ (unrounded readings, no interval, no diagnostics, manifest without the new keys) and must be regenerated (stated in `builder.md`).

Measured on a small build (40 patients x 7 days, generation seed 11, the real registry and literature prior with fixture design values, inline segments; the lease and period are TEST VALUES): see the completion report of the worker for the table. The prototype's natural repeat rate of 0.0197 is reproduced as a property of the generator (pooled over four more seeds of the same size: 99 repeats in 4448 consecutive pairs, 0.0223, against 0.0204 predicted by the formula on the unrounded readings).

### Hand-over for WS02-T06 and WS05-T12 (worker, 2026-10-11, from WS04-T18)

See the same-named notes of those two tasks.

### Hand-over for WS08-T02 (worker, 2026-10-11, from WS04-T18)

See the same-named note of that task.
