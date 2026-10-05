---
id: WS04-T03
title: "Latent patient model: baseline pressure, circadian dip, autoregressive noise"
workstream: WS04-benchmark
owner: agent
status: in_progress
depends_on: ["WS04-T02"]
critical_path: true
non_negotiable: false
estimate_pd: 2
sources: ["analisi §5.1 (1)", "analisi §5.1 (generator, latent patient)"]
interfaces: ["02-interfaces.md#priorsource"]
review_items: []
---
## Obiettivo

Implement the first layer of the latent patient of analisi §5.1 (1): a systolic pressure trace on an integer-millisecond grid made of the patient's baseline, a circadian component with a nocturnal dip, and autoregressive noise, driven only by `PatientParams` from a `PriorSource`. Also create the named random-stream helper that every later generator step uses, so that adding an injection can never change another component's random numbers. Concrete output: `src/ralmon/benchmark/rng.py`, `src/ralmon/benchmark/latent.py`, `configs/benchmark/generator_design.yaml` (first rows) and their tests. No drug effect (T04) and no measurement (T06) here.

## Contesto

- `02-interfaces.md#priorsource` (`PatientParams` fields `baseline_sbp_mmhg`, `circadian_amplitude_mmhg`, `ar_noise_sd_mmhg`, `ar_noise_phi`) and `02-interfaces.md#time-and-units` (integer milliseconds, `MS_PER_HOUR`).
- `docs/benchmark/parameter-provenance.md` (the rows this task consumes and the rows it adds) and the parameter policy in the workstream README.
- `docs/plan/01-conventions.md` section 2 (randomness only through `numpy.random.Generator` from an explicit integer seed).
- `docs/source/analisi.md` §5.1 (1): "componente circadiana con dip notturno, rumore autoregressivo".

Unblocked when WS04-T02 is `done` (`PatientParams`, the loader and `make_fixture_prior` exist).

## File toccati

- `src/ralmon/benchmark/rng.py` (create).
- `src/ralmon/benchmark/latent.py` (create).
- `configs/benchmark/generator_design.yaml` (create: row `circadian_peak_clock_ms`, physiological, `awaiting_human_value`, note stating the amplitude convention).
- `tests/benchmark/test_latent.py` (create; covers `rng.py` as well).

The generated provenance table is regenerated and not counted.

## Test

Arithmetic fixtures, fixture-only (for example baseline 130, amplitude 10, SD 8, phi 0.6; none of these is a clinical value and none enters a prior file used by the builder). Write first.

1. `test_stream_same_keys_same_numbers`: `stream(0, 3, None, StreamPurpose.LATENT_AR)` called twice yields identical first five draws.
2. `test_stream_purposes_are_independent`: draws of two purposes differ, and drawing from purpose B before or after purpose A leaves A's draws unchanged.
3. `test_stream_purpose_ids_are_frozen`: the integer value of every `StreamPurpose` member equals a hand-copied table (changing one silently would change every benchmark).
4. `test_circadian_hand_values`: amplitude A, baseline B, peak clock time 12:00 (fixture): value at 12:00 is `B + A`, at 00:00 is `B - A`, at 06:00 is `B` within 1e-9; the mean over one 24 h period equals `B` within 1e-9.
5. `test_no_noise_trace_equals_baseline_plus_circadian`: with `ar_noise_sd_mmhg = 0` the trace equals `B + circadian(t)` exactly on the grid.
6. `test_ar_innovation_sd_closed_form`: `innovation_sd(8, 0.6) == 6.4` within 1e-12 (`8 * sqrt(1 - 0.36)`).
7. `test_rescale_ar1_phi`: `rescale_ar1_phi(0.5, ref_step_ms=2, step_ms=1) == 0.7071067811865476` within 1e-15; the same step returns 0.5; step twice the reference returns 0.25.
8. `test_ar_stationary_variance_and_lag1_autocorrelation`: seed 0, 200 000 grid steps: sample variance within four standard errors of `sd**2` and lag-1 autocorrelation within four standard errors of `phi` (tolerances computed in the test from the closed-form standard errors).
9. `test_ar_state_continues_across_midnight`: a 2-day call equals the concatenation of two 1-day calls that carry the AR state; there is no reset at midnight.
10. `test_grid_is_integer_ms_and_step_divides_day`: with step 900 000 ms one day has 96 points at `t = 0, 900 000, ...`; a step that does not divide 86 400 000 raises `LatentModelError`; a Hypothesis property over the divisors of the day and over `n_days` checks that the length is `n_days * 86 400 000 / step` and the times are strictly increasing.
11. `test_invalid_ar_parameters_rejected`: `|phi| >= 1` or `sd < 0` raises `LatentModelError`.
12. `test_latent_trace_unchanged_by_other_streams`: consuming numbers from the adherence, measurement and injection streams before generating the latent trace does not change it (pairing property used by T07 to T09).
13. `test_values_finite_and_not_clipped`: values are finite; the function never clips (fraction outside registry bounds is reported by T12, not hidden here).
14. `test_no_unseeded_randomness_in_benchmark_package`: an AST scan of `src/ralmon/benchmark/` finds no `numpy.random.seed`, no legacy global draws (`numpy.random.normal` and similar) and no `default_rng()` without an argument.

## Passi

1. Write `tests/benchmark/test_latent.py`; run it, confirm all fail; commit `WS04-T03: add failing latent patient tests`.
2. Implement `rng.py`: `StreamPurpose` (integer enum with fixed values: patient, latent AR, adherence, measurement, segments, jitter, injection plan, injection C1, injection C2, injection C3, split, confounder) and `stream(seed, patient_index, day_index_or_none, purpose, sub_index=0) -> numpy.random.Generator` built from `numpy.random.SeedSequence` over the integer key list, `None` encoded as a reserved value distinct from every day index.
3. Implement `latent.py`: `innovation_sd`, `rescale_ar1_phi`, `circadian`, `simulate_baseline_sbp(params, latent_step_ms, n_days, circadian_peak_clock_ms, ar_reference_step_ms, rng)` returning integer-ms times and mmHg values; `ar_reference_step_ms` is read from the `reference_step_ms` of the `ar_noise_phi` row through `LiteraturePriorSource.reference_step_ms(name)`, an extension outside the `PriorSource` protocol that the T02 ADR lists among the contract gaps. Model: `sbp(t) = baseline + A * cos(2 * pi * (t - t_peak) / 24 h) + x(t)`; `A` is half the peak-to-trough difference (the provenance row note says so, a human transcribing a source must convert); `x` is AR(1) started from its stationary distribution with stationary SD `ar_noise_sd_mmhg` and coefficient rescaled from the literature reference step to `latent_step_ms`. A single harmonic is a declared simplification: dipper and non-dipper patterns would need additional literature parameters.
4. Add the row `circadian_peak_clock_ms` to `configs/benchmark/generator_design.yaml` with `value: null`, `status: awaiting_human_value`, `source_type: published_literature`, and a `note` naming the model above; regenerate the provenance table.
5. Implement the AST scan of test 14 and run the literal guard of T02 over the new modules (every literal that is an algorithmic constant carries the `# algorithmic:` marker).
6. Refactor, run `ruff check src tests`, `mypy src/ralmon`, `pytest tests/benchmark -q`; commit `WS04-T03: add latent pressure model and named random streams`; set `status: done`.

## Done when

- `pytest tests/benchmark/test_latent.py tests/benchmark/test_priorsource.py -q` exits 0.
- `ruff check src tests` exits 0 and `mypy src/ralmon` exits 0.
- `python -m ralmon.benchmark.priors --check-table` exits 0 and `grep -c circadian_peak_clock_ms docs/benchmark/parameter-provenance.md` prints at least 1.

## Notes

### Hand-over from the WS04-T02 review (orchestrator, 2026-10-05)

`LiteraturePriorSource` (WS04-T02, `src/ralmon/benchmark/priors.py`) reads the reference step through `LiteraturePriorSource.reference_step_ms(name)`, which raises `UnfilledParameterError` while the committed YAML row is unfilled; `make_fixture_prior(tmp_path)` in `tests/benchmark/conftest.py` builds FIXTURE-ONLY priors for tests. Every row of `configs/benchmark/generator_design.yaml` must carry all 11 keys explicitly (see the loader `load_design_file`, which reads a top-level `parameters:` list and numeric values only). Every distribution row consumes exactly one uniform and a plain value none, in the documented draw order (do not reorder draws). `patient_index` may be any integral numpy integer.

### Implementation notes (worker, 2026-10-05; status left `in_progress` for the orchestrator)

- **Streams.** `rng.stream(seed, patient_index, day_index_or_none, purpose, sub_index=0)` returns `default_rng(SeedSequence(entropy=seed, spawn_key=(patient_index, day_code, purpose, sub_index)))`, `day_code` = 0 for `None` and `day_index + 1` otherwise. `StreamPurpose` is an `IntEnum` with frozen ids 1 to 12 (order of the task text). Streams are named by this enum, not by free strings: the derivation uses integers only (no `hash()`), so stability across processes and platforms is by construction and tested (two `PYTHONHASHSEED` values, a pinned `generate_state`, a pinned first draw). Keys are bounded because `SeedSequence` splits an integer into 32-bit words and concatenates the `spawn_key` entries, so a value of 2**32 or more could alias two keys: every `spawn_key` entry is in [0, 2**32), the seed in [0, 2**64), anything else (negative, bool, float, string, a non-member purpose) raises `StreamKeyError`.
- **Amplitude convention.** `A = circadian_amplitude_mmhg` is HALF the peak-to-trough difference (curve from `baseline - A` to `baseline + A`). Stated in the module docstring, in the note of the design row (rendered into the provenance table) and tested by hand arithmetic and by a mutation check (halving `A` fails 6 tests).
- **AR(1).** `phi_s = phi ** (step / reference_step)`, innovation SD `sd * sqrt(1 - phi_s**2)`, first value drawn from `N(0, sd**2)` (no burn-in; tested with a 2000-run ensemble at the first six points). One standard normal per grid point whatever the parameters, so a call over `n` days equals consecutive calls with the AR state carried (`start_day`, `ar_state_mmhg`, `LatentPressure.ar_state_mmhg`). A negative `phi` is accepted only at an integer multiple of the reference step (a real value exists only there); a rescaled coefficient that rounds to 1.0 is refused.
- **Grid.** Half-open `t_k = start_day * T_day + k * T_s`, `k = 0 .. n_days * T_day / T_s - 1`; `T_s` must divide `T_day`. `MAX_GRID_POINTS = 1_000_000` (annotated algorithmic memory guard) is checked on Python integers before any allocation, so a per-millisecond day is refused (tested with `tracemalloc`, peak under 1 MB).
- **Baseline.** Refused when not finite or `<= 0`, mirroring the prior domain of `baseline_sbp_mmhg`; amplitude and SD refused when negative; the trace itself is never clipped (a test drives it below zero).
- **Contract gaps and notes (no frozen contract changed).** (1) `rng` and `latent` are not in the `02-interfaces.md#package-public-api` table, so they are imported from their modules and not exported from `ralmon.benchmark`; if later tasks want them at the root the contract table needs a version bump and an ADR. (2) `ar_reference_step_ms` is read by the caller through `LiteraturePriorSource.reference_step_ms("ar_noise_phi")`, outside the `PriorSource` protocol (ADR-038 G1). (3) `circadian_peak_clock_ms` has no accessor yet: a consumer reads the row with `load_design_file` and must obtain a filled value from a human; the committed row is `awaiting_human_value`. (4) The day-boundary rule follows `docs/formal/01-signals-sampling.md` section 3.1 and 5.5 item 3 on the continuing axis; the closing step `K` of a slice is the next day's step 0 here (CG-11 on negative `TimeMs` is not needed: `circadian` is defined for negative times by integer modulo, tested, but the generator never emits them).
- **Verification evidence** is in the final report of the worker, not duplicated here.
