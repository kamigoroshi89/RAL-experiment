---
id: WS04-T01
title: Trace schema dataclasses, serialisation and manifest
workstream: WS04-benchmark
owner: agent
status: in_progress
depends_on: ["WS05-T01"]
critical_path: true
non_negotiable: false
estimate_pd: 2
sources: ["analisi §5.1", "analisi §5.1 (ground truth definition, latent versus observed)", "analisi §4.9 (5)"]
interfaces: ["02-interfaces.md#trace-schema"]
review_items: ["R3-W1"]
---
## Obiettivo

Implement the trace schema of `02-interfaces.md#trace-schema` exactly as written (`EventKind`, `InjectedClass`, `GroundTruthEvent`, `ObservedDay`, `LatentDay`, `BenchmarkDay`; `Sample` and `Event` have a single definition in `ralmon.signals`), plus canonical JSON serialisation with a bit-exact round trip and a `Manifest` with integrity hashes. Observed files and truth files go to different directories so that a detector run never needs the truth. Concrete output: `src/ralmon/benchmark/trace.py`, its tests and fixtures, and a proposed ADR recording the file format and layout that the contract delegates to this task.

## Contesto

- `02-interfaces.md#trace-schema` (types, rule 3 on files) and the ownership note at the end of `02-interfaces.md` (single definition of `Sample` and `Event` in `ralmon.signals`).
- `docs/plan/03-decisions.md` ADR-004 (DISPENSE and INTAKE are distinct), ADR-016 (toolchain), ADR-017 (integer milliseconds).
- `docs/plan/workstreams/WS04-benchmark/README.md` (directory layout, sidecar keys, parameter policy).
- `docs/plan/01-conventions.md` sections 2 and 3 (style, determinism, golden files).

Unblocked when WS05-T01 is `done` (the package skeleton `src/ralmon/benchmark/` with its placeholders and `src/ralmon/signals/` exist and `pytest` runs). WS05-T02 may not be done yet; step 1 handles both cases.

## File toccati

- `src/ralmon/signals/` (create `trace_types.py` and re-export in `__init__.py`, only if `Sample`, `Event`, `EventKind` are not yet exported by WS05-T02; otherwise untouched).
- `src/ralmon/benchmark/trace.py` (create).
- `src/ralmon/benchmark/__init__.py` (modify, together with `_stubs.py`: replace the WS05-T01 placeholders of the names owned by this task with the real definitions and export them).
- `tests/benchmark/test_trace_io.py` (create).
- `tests/fixtures/benchmark/` (create: `observed_day_minimal.json`, `truth_minimal.json`, `manifest_minimal.json`, and `README.md` naming the regeneration command; hand-written, a few dozen samples).
- `docs/plan/03-decisions.md` (modify: append one ADR with status `proposed`, next free number).

## Test

Fixture numbers are arithmetic and fixture-only. Write these tests first; each must fail before the implementation exists.

1. `test_sample_and_event_have_single_definition`: `ralmon.benchmark.trace.Sample is ralmon.signals.Sample` and the same for `Event` and `EventKind`; `ralmon.benchmark.__init__` exports every name of the trace-schema part of the public API table.
2. `test_dataclass_fields_match_contract`: the field names and order of `GroundTruthEvent`, `ObservedDay`, `LatentDay`, `BenchmarkDay` equal the lists written in the contract (hand-copied into the test).
3. `test_observed_day_roundtrip_bit_exact`: write the hand-written fixture day (12 samples, 6 events), read it back, `==` holds; writing the read object again yields identical bytes.
4. `test_serialisation_is_canonical`: keys sorted, two-space indent, final newline, floats written with `repr` (so `0.1` round-trips), no timestamp or host field; two writes of the same object are byte-identical.
5. `test_fixture_bytes_equal_writer_output`: `tests/fixtures/benchmark/observed_day_minimal.json` equals the bytes produced by the writer for the object built in code (golden test; regenerate only through the command named in the fixtures README).
6. `test_samples_must_be_sorted_by_t_rx`: a day whose `samples` or `events` are not non-decreasing in `t_rx_ms` raises `TraceOrderError`; equal `t_rx_ms` are allowed.
7. `test_negative_t_device_allowed_negative_t_rx_rejected`: a stale replayed sample (C3) may have `t_device_ms < 0`; `t_rx_ms < 0` raises `TraceTypeError`.
8. `test_time_values_must_be_integer_ms`: a float or bool in `t_device_ms`, `t_rx_ms`, `onset_ms`, `end_ms` raises `TraceTypeError` (ADR-017).
9. `test_non_finite_values_rejected`: NaN and infinity in `Sample.value` raise `TraceTypeError`; a missing signal is an absent sample, never NaN.
10. `test_payload_types_preserved`: an `Event.payload` with a bool, an int, a float and a str returns the same Python types (`True` does not become `1`).
11. `test_observed_file_has_no_latent_or_truth_keys`: the key set of an observed file equals `{patient_id, day_index, seed, samples, events, care_plan_id}`; no key anywhere contains `latent` or `ground_truth`.
12. `test_truth_file_holds_latent_ground_truth_and_sidecars`: the truth file has `latent`, `ground_truth`, and the optional JSON-native sidecars `injection_log` and `behaviour_log`; `read_benchmark_day` recombines observed and truth into a `BenchmarkDay` equal to the original.
13. `test_read_observed_day_needs_no_truth_directory`: with `truth/` deleted, `read_observed_day` still works.
14. `test_manifest_required_fields`: the manifest has `benchmark_version`, `generator_git_rev`, `generation_seed`, `prior_source_name`, `prior_provenance` (list of `name`, `source_ref`, `verified_by`), `fixture_only`, `n_unfilled`, `n_unverified`, `patients` (mapping patient id to `split` and `cohort`; entries may carry further JSON-native keys such as `role` and `pair`, used by T11), `files` (relative path to sha256), `event_counts` (key `"C1/hypertensive_spike"` and so on), `settings` (JSON-native mapping); a missing key raises `ManifestError`; no wall-clock field exists.
15. `test_split_membership_is_by_patient`: a manifest listing a patient in two splits raises `SplitLeakError` (contract rule 2).
16. `test_verify_detects_tampered_or_missing_file`: flipping one byte of a day file, or deleting one, makes `verify_manifest` raise `ManifestError` naming the path.
17. `test_roundtrip_property_random_days` (Hypothesis): random valid days (finite floats, integer times, sorted) round-trip exactly.

## Passi

1. Check whether `ralmon.signals` already exports real (non-placeholder) `Sample`, `Event`, `EventKind` (WS05-T02; WS05-T01 leaves only placeholders marked `__ralmon_stub_owner__`). If not, create `src/ralmon/signals/trace_types.py` with the types copied verbatim from the contract and re-export them from `ralmon/signals/__init__.py` in place of the placeholders; WS05-T02 step 1 then imports and does not redefine them, and the completion note says so. `TimeMs` and `DurationMs` come from `ralmon/signals/units.py` (real since WS05-T01). Cross-package imports use the package root only (`from ralmon.signals import ...`), as the layering test of WS05-T01 requires; never write the built-in `NotImplementedError` in this package (WS05-T01 test).
2. Write `tests/benchmark/test_trace_io.py` and the fixtures (hand-written values, a few dozen samples, expected bytes derived by hand from the rules of test 4). Run `pytest tests/benchmark/test_trace_io.py -q`; confirm every test fails for the right reason; commit `WS04-T01: add failing trace io tests`.
3. Implement `trace.py`: dataclasses exactly as the contract (and delete the matching placeholders from `ralmon/benchmark/_stubs.py`); `validate_day` (order, integer times, finite values); `write_observed_day`, `read_observed_day`, `write_truth`, `read_truth`, `read_benchmark_day`; `Manifest` dataclass, `write_manifest`, `read_manifest`, `verify_manifest` (sha256 of every file listed). Errors: `TraceOrderError`, `TraceTypeError`, `SplitLeakError`, `ManifestError`. Files use `days/<patient_id>/<day_index>.json` for `ObservedDay` and `truth/<patient_id>/<day_index>.json` for the latent day, ground truth and sidecars; the sidecars are stored as given after a JSON-native check.
4. Add the fixtures README with the exact regeneration command, run the tests until green, then refactor (no duplicated conversion code between observed and truth writers).
5. Write the ADR (status `proposed`): format JSON with sorted keys chosen over Parquet because it needs no extra dependency and gives byte-identical output for the bit-for-bit reproducibility rule of `01-conventions.md` section 3; alternative Parquet, to be reconsidered only if a measured size or speed problem appears at 1400 patient-days; layout with observed and truth in separate directories, a refinement of contract rule 3 that keeps `truth/` out of every detector run. Note the extra sidecar keys `injection_log` and `behaviour_log`.
6. Run `ruff check src tests`, `mypy src/ralmon`, then `pytest tests/benchmark -q`; commit `WS04-T01: add trace schema, canonical JSON io and manifest`; set `status: done`.

## Done when

- `pytest tests/benchmark/test_trace_io.py -q` exits 0.
- `ruff check src tests` exits 0 and `mypy src/ralmon` exits 0.
- `python -c "from ralmon.benchmark import ObservedDay, LatentDay, BenchmarkDay, GroundTruthEvent, InjectedClass; from ralmon.signals import Sample, Event, EventKind"` exits 0.
- `grep -c '^## ADR-' docs/plan/03-decisions.md` has increased by one and the new entry names `manifest.json`, `days/` and `truth/`.
