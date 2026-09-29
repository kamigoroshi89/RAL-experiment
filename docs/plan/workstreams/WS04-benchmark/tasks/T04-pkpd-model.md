---
id: WS04-T04
title: PK/PD response model and onset window derivation; evaluate Pulse Physiology Engine
workstream: WS04-benchmark
owner: agent
status: blocked
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
