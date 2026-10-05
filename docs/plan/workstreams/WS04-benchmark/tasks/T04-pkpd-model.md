---
id: WS04-T04
title: PK/PD response model and onset window derivation; evaluate Pulse Physiology Engine
workstream: WS04-benchmark
owner: agent
status: in_progress
depends_on: ["WS04-T03"]
critical_path: true
non_negotiable: false
estimate_pd: 3
sources: ["analisi §5.1 (1)", "analisi §5.1 (Pulse Physiology Engine alternative)"]
interfaces: ["02-interfaces.md#priorsource"]
review_items: []
---
## Obiettivo

Implement the drug response of the latent patient as in analisi §5.1 (1): one-compartment oral absorption plus an Emax effect, with linear superposition over the true intake events, behind a `ResponseModel` protocol so that another engine can replace it. Derive, per patient, the **onset window** in which the modelled effect reaches the clinical decrease threshold, so that the generator can be checked against the registry's Δ1, Δ2 and δ. Evaluate the Pulse Physiology Engine (Kitware, open source) as the analisi's alternative and record the decision: adopt it only if its substance library holds a suitable antihypertensive, otherwise keep this custom model. Concrete output: `src/ralmon/benchmark/pkpd.py`, tests, `docs/benchmark/pulse-evaluation.md` and a proposed ADR.

## Contesto

- `docs/source/analisi.md` §5.1 (1) (PK/PD with inter-patient parameters; Pulse "verificando che la sua libreria di sostanze includa antipertensivi adatti; in caso contrario resta il PK/PD custom").
- `02-interfaces.md#priorsource` (`emax_mmhg`, `ec50`, `absorption_rate_per_h`, `elimination_rate_per_h`, `onset_delay_range_ms`).
- `docs/plan/03-decisions.md` ADR-020 (no agent names a drug or a guideline; the drug is the registry's anchor) and ADR-005.
- The output of WS04-T03 (`latent.py`, the pressure trace this response is subtracted from) and the registry entries `delta_resp` (δ), `delta1` and `delta2` (working names of WS01-T02 and WS01-T03).
- `docs/plan/workstreams/WS04-benchmark/README.md` (declared assumptions).

Unblocked when WS04-T03 is `done`.

## File toccati

- `src/ralmon/benchmark/pkpd.py` (create).
- `tests/benchmark/test_pkpd.py` (create).
- `docs/benchmark/pulse-evaluation.md` (create).
- `docs/plan/03-decisions.md` (modify: one proposed ADR, next free number).

## Test

Fixture-only arithmetic values: `ka = 2 per h`, `ke = 1 per h`, `Emax = 20 mmHg`, `EC50 = 0.25` (concentration per unit dose). They are not clinical values. Expected results are hand-computed and written in the test.

1. `test_bateman_concentration_hand_values`: unit dose, `C(tau) = ka / (ka - ke) * (exp(-ke tau) - exp(-ka tau))` gives `C(1 h) = 0.465088316` (relative tolerance 1e-9) and `C(ln 2 h) = 0.5`.
2. `test_tmax_closed_form`: `t_max = ln(ka / ke) / (ka - ke) = 0.693147 h`; the argmax over a fine grid lies within one grid step of it.
3. `test_bateman_ka_equals_ke_limit`: with `ka = ke = 1`, `C(1 h) = exp(-1) = 0.367879441`; the value for `ka = 1 + 1e-9` agrees within 1e-6 (no division by zero).
4. `test_concentration_zero_before_intake_and_nonnegative`: `tau < 0` gives 0; all values are nonnegative.
5. `test_emax_hand_values`: `E(0) = 0`, `E(EC50) = 10` (`Emax / 2`), `E(0.5) = 20 * 0.5 / 0.75 = 13.3333333`; E is monotone increasing and below `Emax`.
6. `test_superposition_is_linear`: two intakes at `t = 0` and `t = 12 h`; the effect concentration at 13 h equals `C(13 h) + C(1 h)` (sum of single-dose values) before the Emax map.
7. `test_double_intake_doubles_concentration_before_emax`: two intakes at the same instant give `2 C(tau)`; at `t_max` the effect is `E(1.0) = 16.0`.
8. `test_intake_scales_scale_emax_per_intake`: `intake_scales = [0.5]` for one intake gives the effect at `t_max` equal to `0.5 * 13.3333333 = 6.6666667` (used by the C1 non-response injection).
9. `test_no_intake_means_zero_effect_and_unchanged_trace`: with no true intake the effect is identically 0 and `compose_latent_sbp(baseline, effect)` returns the baseline trace bit for bit.
10. `test_onset_window_two_crossings_closed_form`: `delta = 10 mmHg` needs `C = 0.25`; with `u = exp(-tau)` this is `u**2 - u + 0.125 = 0`, so the window is `[-ln((1 + sqrt(0.5)) / 2), -ln((1 - sqrt(0.5)) / 2)] = [0.158347, 1.921094] h`; the implementation returns integer milliseconds rounded inward, `[570 050, 6 915 939]`.
11. `test_onset_window_empty_when_peak_effect_below_delta`: `delta = 14 mmHg` exceeds the peak effect 13.3333 and the function returns `None` (a non-responder by construction).
12. `test_onset_window_contains_tmax_for_delta_just_below_peak`: `delta = 13 mmHg` gives a window that contains `t_max`.
13. `test_window_overlap_with_registry_window`: with a fixture registry window of 1 h to 2 h (`[3 600 000, 7 200 000]` ms), the overlap with `[570 050, 6 915 939]` is `[3 600 000, 6 915 939]`; a fixture window 2 h to 3 h gives no overlap (`None`).
14. `test_response_model_protocol_swappable`: a stub `ResponseModel` (constant effect) is accepted by the composer, so a Pulse-backed adapter can replace the custom model without touching callers.
15. `test_parameters_validated`: `ka <= 0`, `ke <= 0`, `ec50 <= 0` or `Emax < 0` raise `PkpdModelError`.
16. `test_delta_is_an_argument_not_a_constant`: `derive_onset_window` has no default for the threshold and the module contains no numeric parameter literal (covered by the package literal guard of T02).

## Passi

1. Write `tests/benchmark/test_pkpd.py`; run it, confirm failure; commit `WS04-T04: add failing pkpd tests`.
2. Implement `pkpd.py`: `ResponseModel` protocol (`effect_mmhg(params, intake_times_ms, t_grid_ms, intake_scales=None) -> Sequence[float]`), the custom `OneCompartmentEmax`, the Bateman function with the `ka == ke` limit branch (guarded by a relative tolerance marked `# algorithmic:`), `compose_latent_sbp(baseline, effect) = baseline - effect`, `derive_onset_window(params, delta_mmhg) -> tuple[int, int] | None` by bracketing the unimodal effect curve at `t_max` and bisecting on each side (deterministic, tolerance marked `# algorithmic:`), and `window_overlap(window, delta1_ms, delta2_ms)`. Convention stated in the module docstring: the concentration is per unit dose (`D / V = 1`); `ec50` is in the same normalised units; a literature EC50 in physical units is converted by the human in the provenance row `rationale`.
3. Only true intakes (latent INTAKE events) drive the model; a DISPENSE without intake has no effect.
4. Write `docs/benchmark/pulse-evaluation.md` with the H2 headings `## Question`, `## Local availability`, `## Substance library check`, `## Licence`, `## Cost`, `## Decision`, `## Open items for a human`. Facts come only from material present locally (an installation, or documentation files placed by a human); without network access the honest entry is `not evaluated: no local installation or documentation`, the decision is `custom PK/PD retained`, and the three questions for a human with access are listed: does the library hold an antihypertensive matching the registry anchor, under which licence, at what per-patient run time for 1400 patient-days. Adopt Pulse only if the anchored drug exists in its library and its response can be checked against the same source as the custom parameters.
5. Append the ADR (status `proposed`): custom one-compartment plus Emax retained as default behind `ResponseModel`; alternative Pulse; consequence that a Pulse adapter is a new implementation, not a change to callers.
6. Refactor, run `ruff check src tests`, `mypy src/ralmon`, `pytest tests/benchmark -q`; commit `WS04-T04: add PK/PD response model, onset window and Pulse evaluation`; set `status: done`.

## Done when

- `pytest tests/benchmark/test_pkpd.py -q` exits 0; `ruff check src tests` and `mypy src/ralmon` exit 0.
- `test -f docs/benchmark/pulse-evaluation.md && grep -c '^## ' docs/benchmark/pulse-evaluation.md` prints at least 7, and `grep -q '^## Decision' docs/benchmark/pulse-evaluation.md` exits 0.
- `grep -c '^## ADR-' docs/plan/03-decisions.md` has increased by one and the new entry names `ResponseModel`.

## Notes

### Hand-over from the WS04-T02 review (orchestrator, 2026-10-05)

ADR-038 (proposed, `[DA-CONFERMARE]`) gap G6: the contract gives `ec50` no unit and `emax_mmhg` only the comment "maximal drug effect"; WS04-T02 enforces `ec50` as dimensionless ("1") and accepts any real `emax_mmhg`, while this task validates `Emax < 0` as an error and composes `baseline - effect`: this task fixes the sign convention in practice; record it when the ADR is confirmed.

### Hand-over from the WS04-T03 review (orchestrator, 2026-10-05)

From `ralmon.benchmark.latent` (WS04-T03): `simulate_baseline_sbp` returns a `LatentPressure` (`t_ms`, `sbp_mmhg`, and the components `circadian_mmhg`, `ar_noise_mmhg`; arrays are read-only), the day has `K` points (the closing step is not emitted: hold the last value or take step 0 of the next day), and `start_day` and `ar_state_mmhg` carry the AR state across days. Streams come from `ralmon.benchmark.rng` with `StreamPurpose` members (not exported from the package root). Compose the drug effect with `baseline - effect` as this task already states; keep every test grid short (no per-millisecond arrays for a day: `MAX_GRID_POINTS` refuses them).

### Completion note (worker, 2026-10-05)

Status left `in_progress`: the orchestrator reviews, sets `done` and merges. Artefacts: `src/ralmon/benchmark/pkpd.py`, `tests/benchmark/test_pkpd.py` (317 tests, about 0.5 s, peak 72 MB), `docs/benchmark/pulse-evaluation.md`, proposed ADR-039.

**What dependents (WS04-T06, T09, T10, T11) must know**

- Public API (module `ralmon.benchmark.pkpd`, not exported from the package root: ADR-024 and the contract table do not list it): `PkpdParams` (+ `from_patient`), `ResponseModel`, `OneCompartmentEmax`, `bateman_concentration`, `t_max_hours`, `emax_effect_mmhg`, `effect_concentration`, `compose_latent_sbp`, `apply_drug_response`, `derive_onset_window`, `window_overlap`, `intake_times_from_events`, `PkpdModelError` (a `ValueError`), and the bounds `MAX_INTAKES`, `MAX_GRID_LEN` (= latent `MAX_GRID_POINTS`), `MAX_EVALUATIONS`, `RATE_LIMIT_TOLERANCE`. Every function that takes `params` accepts a `PkpdParams` or directly a `PatientParams` (a deviation from the task's bare `params`, harmless widening).
- Time: integer ms on the continuing axis, `>= 0`. `t_grid_ms` must be strictly increasing and non-empty; `intake_times_ms` may be unsorted or repeated; `intake_scales` is aligned with the order given. `effect_mmhg` returns a `tuple[float, ...]` (not an ndarray); `compose_latent_sbp` and `apply_drug_response` return a new read-only float64 array. `apply_drug_response(model, params, latent_pressure, intake_times_ms, intake_scales=None)` evaluates the effect on `LatentPressure.t_ms` and subtracts it.
- The model has no memory across calls: for day `d > 0` the caller passes every true intake of the earlier days that still matters (or computes the whole horizon in one call, bounded by `MAX_EVALUATIONS`); an intake after the grid end has no effect. Use `intake_times_from_events(events)` to turn latent events into intake times: it keeps `INTAKE` and drops `DISPENSE`.
- Per-intake scale semantics (for the C1 non-response injection of T09): effect = `Emax * sum_i s_i C_i / (EC50 + sum_i C_i)`, i.e. the Emax of intake `i` is scaled and the saturation term still sees its drug. `s_i >= 0`; `s_i > 1` is allowed and can exceed Emax. Task test 8 fixes this reading (a halved dose would not halve the effect).
- `derive_onset_window(params, delta_mmhg)` is the window after ONE intake with scale 1 (delta is the registry threshold, `delta_resp` in the working names, must be `> 0`, no default). It returns integer ms rounded inward, or `None`; it raises `PkpdModelError` if the peak or the window end lies beyond the int64 ms range. `window_overlap(window, delta1_ms, delta2_ms)` uses closed intervals and rejects a `None` window: the caller handles `None` first. `onset_delay_range_ms` of `PatientParams` is not read by this module; the Δ1 and Δ2 values for the overlap check come from the registry.
- Sign and unit conventions (also in ADR-039, which records ADR-038 G6 in practice): effect is a decrease `>= 0`, `sbp = baseline - effect`, `Emax >= 0` (negative is an error), `ec50` dimensionless on unit-dose-normalised concentration. The composer does not clip: a large effect can push the pressure below physiological bounds, which the validation report (WS04-T12) must report.

**Deviations and gaps**

- The onset window uses an exact integer bisection on the predicate `effect(t_ms) >= delta`, evaluated by the same code path as `effect_mmhg`; no float tolerance is needed, so the only `# algorithmic:` tolerance is `RATE_LIMIT_TOLERANCE` (limit branch `ka` close to `ke`). The task text asked for a tolerance on the bisection; this is stricter and gives the verified bounds of the extra requirement.
- The Bateman function is written as `(ka / d) * (1 - exp(-d tau)) * exp(-min(ka, ke) tau)` with `expm1`, which is accurate for every `ka != ke` (either order, no overflow); the limit branch only avoids the division when `d` is within `RATE_LIMIT_TOLERANCE` of zero, so some mutants of that tolerance are behaviourally equivalent (see below). No clamp of negative round-off exists because every factor is nonnegative; the nonnegativity is tested over a sweep including `ka = ke (1 +- 1e-13 ... 1e-3)`.
- Pulse: `not evaluated: no local installation or documentation`; decision `custom PK/PD retained`; three questions for a human are in `docs/benchmark/pulse-evaluation.md`. ADR-039 is `proposed [DA-CONFERMARE]`.
- Mutation self-check on a copy (deleted): 52 mutants run, 48 killed (one of them by a timeout on a hang), 4 survivors, all equivalent: the limit branch condition reduced to `gap == 0` or the tolerance reduced to `1e-15` (the `expm1` form is exact just outside the branch), a `delta >= 0` instead of `delta > 0` check (the same input fails later with a defined `PkpdModelError` from the int64 range guard), and a scale index clamp that cannot differ when the lengths are equal.
- State independence: tests use only fixture values and a `tmp_path` fixture prior; no committed config file is read. A filled-state proof (a copy of the committed tree with the 17 prior rows and the 3 design rows filled with proof-only values, table regenerated) ran the whole suite: 1181 passed.

### Fix round 1 (worker)

Review verdict was PASS with no blocker; this round closes minor test gaps with tests only. `src/ralmon/benchmark/pkpd.py` is unchanged: no test revealed a defect.

Tests added in `tests/benchmark/test_pkpd.py` (317 to 359 tests). Each was checked on a `/tmp` copy of the repo: the pre-fix test file passes 317/317 against the mutant, the new file fails it (copy deleted):

1. Window probes: delta exactly equal to the effect at `best + 1, 2, 4, ..., 2048` (falling-side exponential probes) with an integer-ms scan as the oracle; also the rising-side bisection instants and falling-side bisection instants. Mutant `effect_at(probe) <= delta` was a survivor; now killed by `test_window_end_at_delta_equal_to_the_effect_at_an_exponential_probe[1]`. The rise and fall bisection `>` mutants were already killed by `test_onset_window_at_delta_equal_to_an_attained_effect`.
2. `compose_latent_sbp([], [])` (and `()`, `range(0)`, empty array) and an empty grid with no intakes for `effect_mmhg` / `effect_concentration`: expect `PkpdModelError`. Mutant (empty-size check removed) was a survivor; now killed.
3. `intake_times_from_events` with `t_rx_ms != t_device_ms`: the device time is used. Mutant `t_rx_ms` was a survivor; now killed.
4. `t_max_hours(5e-324, 5e-324)` raises `PkpdModelError`. Mutant (finiteness guard removed) was a survivor; now killed by `test_t_max_numerics`.
5. Int64 boundary: no float hours value gives `peak_ms == 2**63` exactly (`hours * 3_600_000` skips that float), so the test uses the two float neighbours (`2**63 - 1024`: no window, `None`; `2**63 + 2048`: `PkpdModelError`, never a raw `OverflowError`), by patching the private `_t_max`. Mutant (guard removed) was a survivor; now killed.

Notes for dependents and the paper:

- (a) Windows are evaluated by the model's own float64 code path. At single-ms edges a window can differ from a high-precision reference when delta is within about 1e-16 relative of the effect at that ms (reviewer: 31 of 420 comparisons, all within 1.1e-16 relative). One sentence added to `## Decision` of `docs/benchmark/pulse-evaluation.md`.
- (b) `configs/registry/hypertension.yaml` has `delta1` and `delta2` but NO `delta_resp` (delta) entry yet. The earlier hand-over wording "delta_resp in the working names" is not true of the registry. WS04-T12 must handle it. `window_overlap` rejects a `None` window, so callers must handle `None` from `derive_onset_window` first.
- (c) A `Sequence` whose `__getitem__` raises propagates the user's own exception (accepted, not wrapped).
