# Evaluation of the Pulse Physiology Engine as the PK/PD engine of the benchmark

Document WS04-T04. It records whether the Pulse Physiology Engine (Kitware, named as an open-source alternative in `docs/source/analisi.md` section 5.1 item 1) can replace the custom one-compartment plus Emax model of `src/ralmon/benchmark/pkpd.py`. The decision rule is the analisi's: adopt Pulse only if its substance library holds a suitable antihypertensive, otherwise the custom PK/PD remains. Validation in this project is technical and pre-clinical, and nothing here is a clinical claim.

## Question

Does the Pulse Physiology Engine provide, for the drug anchored in the parameter registry (WS01-T03, WS00-T07), a pharmacokinetic and pharmacodynamic response that can be (a) checked against the same source as the parameters of the custom model and (b) run for 200 patients over 7 days (1400 patient-days) in a reasonable time? No agent names the drug (ADR-020): the question is asked of the registry anchor, which a human supplies.

## Local availability

not evaluated: no local installation or documentation

On 2026-10-05 no Pulse installation, Python package or documentation file was found (pip package list, repository documents, and a file-name search of the development machine to depth 4), and the agent has no network access. Nothing in this document is taken from memory about Pulse's contents: its substance library, licence, interfaces and speed are all unverified.

## Substance library check

not evaluated: no local installation or documentation

Whether the library holds an antihypertensive that matches the registry anchor, with a pressure response that can be compared with the source of `emax_mmhg`, `ec50`, `absorption_rate_per_h` and `elimination_rate_per_h`, is open (question 1 below).

## Licence

not evaluated: no local installation or documentation

The licence terms of the engine and of its data, and their compatibility with the open-source release of the generator (WS13), are open (question 2 below).

## Cost

not evaluated: no local installation or documentation

The run time per patient and the integration work (an adapter implementing `ResponseModel`, a build of the engine in the container, patient-specific parameterisation) are unknown. For the custom model the cost is measured: a call is vectorised over the time grid and bounded by `MAX_EVALUATIONS`; one patient-week (672 grid points, 21 intakes) runs in a fraction of a second in `tests/benchmark/test_pkpd.py`. The adapter effort for a Pulse engine is not estimated here (question 3 below).

## Decision

custom PK/PD retained.

The custom one-compartment oral absorption plus Emax model with linear superposition over the true intakes stays the default of the benchmark generator. It is implemented behind the `ResponseModel` protocol (`effect_mmhg(params, intake_times_ms, t_grid_ms, intake_scales=None)`), so that a Pulse-backed adapter can be added later as a new implementation without changing any caller (proposed ADR-039 in `docs/plan/03-decisions.md`). Onset windows of the custom model are evaluated by its own float64 code path, so at a single-millisecond edge a window can differ from a high-precision reference when delta lies within about 1e-16 relative of the effect at that millisecond. The decision is reversible and conditional: it is revisited only if a human answers the three questions below in favour of Pulse.

## Open items for a human

1. Does the substance library of the engine hold an antihypertensive matching the registry anchor, and can its pressure response be checked against the same source as the custom parameters (not against a different source)?
2. Under which licence are the engine and its substance data distributed, and does that licence allow redistribution inside the open-source generator release?
3. What is the run time per patient, and what is the integration effort, for 1400 patient-days (200 patients, 7 days each)?

If the answers are positive, the next step is an adapter class with the `ResponseModel` method, tested against the custom model on a fixture scenario; if they are negative or unknown, the decision above stands.
