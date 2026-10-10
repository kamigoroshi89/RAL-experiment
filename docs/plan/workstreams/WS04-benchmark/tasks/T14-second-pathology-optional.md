---
id: WS04-T14
title: "OPTIONAL: second pathology (diabetes, simglucose)"
workstream: WS04-benchmark
owner: agent
status: ready
depends_on: ["WS04-T11"]
critical_path: false
non_negotiable: false
estimate_pd: 4
sources: ["analisi §5.8", "analisi §9", "analisi §5.8 (diabete con simulatore UVA/Padova open-source, simglucose)"]
interfaces: ["02-interfaces.md#priorsource"]
review_items: []
---
## Obiettivo

OPTIONAL. Add a second pathology to the generator, diabetes with the open-source UVA/Padova simulator (simglucose), as the analisi lists it: optional, "forte segnale di generalità" (analisi §5.8). It is the last item of the cut order of `docs/plan/00-master-plan.md` section 7 (after the vignette study and the lab demo) and is excluded from the critical path (ADR-019): it starts only after M3, that is when the main comparison of WS08 has produced its table, even though the only dependency listed is WS04-T11. Concrete output: a `glucose` subpackage that reuses the trace schema, measurement, injection and builder machinery through the `PriorSource` and `ResponseModel` seams, a `GlucosePriorSource` with the same mandatory provenance, the simulator check document, and the decisions needed to represent a non-pressure patient without changing the hypertension contracts.

## Contesto

- `docs/source/analisi.md` §5.8 (second pathology optional) and §9 (cut order); `docs/plan/03-decisions.md` ADR-019 (optional and last, `ready` only after M3), ADR-001 and ADR-020.
- `docs/plan/00-master-plan.md` section 7 (cut order) and `docs/plan/workstreams/WS04-benchmark/README.md` (parameter policy, subtype vocabulary, issue I7).
- `02-interfaces.md#priorsource` (`PatientParams` is pressure-specific), `02-interfaces.md#signals` (`SignalId` has no glucose member) and `02-interfaces.md#trace-schema`.
- The outputs of WS04-T02, WS04-T04 (`ResponseModel`), WS04-T06 and WS04-T11 (`builder.py`), and the WS08 main results as evidence that M3 was reached.
- `docs/plan/workstreams/WS01-formalization/` (registry and template library exist for hypertension only) and `docs/plan/workstreams/WS00-admin/tasks/T07-clinician-review-registry.md`.

Unblocked when WS04-T11 is `done` and, by ADR-019, M3 is reached (`outputs/main/` holds the main-experiment results). A second registry with clinician review is also needed for ground truth; no INDEX task provides it (README issue I7), so this task delivers the generator side and states the labelling precondition instead of inventing clinical parameters.

## File toccati

- `src/ralmon/benchmark/glucose/` (create: `latent_glucose.py` wrapping simglucose behind a physiology protocol, `prior_glucose.py`, `measurement_glucose.py`).
- `src/ralmon/benchmark/builder.py` (modify: `pathology` option `hypertension` or `glucose`, default unchanged).
- `tests/benchmark/test_glucose.py` (create).
- `configs/priors/literature_diabetes.yaml` (create: rows with `awaiting_human_value`, same schema as T02).
- `docs/benchmark/second-pathology.md` (create: simulator check, decisions, blocked items).
- `docs/plan/03-decisions.md` (modify: one proposed ADR, next free number).

## Test

The simulator is replaced by a stub in unit tests; tests that need the real package are skipped with an explicit reason when it is absent. Fixture-only values. Write first.

1. `test_glucose_prior_source_enforces_provenance`: same rules as T02 (missing `source_ref` fails, unfilled rows raise on use, fixture-only files need a flag).
2. `test_latent_glucose_deterministic_given_seed`: the wrapper around the stub gives identical output for the same seed and named stream; it never uses global random state.
3. `test_latent_glucose_on_integer_ms_grid`: times are integer milliseconds (ADR-017) and the step divides the day.
4. `test_dose_and_meal_events_use_existing_event_kinds`: no new `EventKind` is required; the substance is a payload key declared in `vocab.py`; a new `SignalId` is used only if `ralmon.signals` already exports it (an accepted ADR), otherwise `SignalIdNotAvailableError`.
5. `test_cgm_error_model_requires_source_ref`: the glucose device error rows follow the T02 schema and carry a standard or a datasheet as `source_ref`, verified by a human; none is written from memory.
6. `test_hypertension_outputs_unchanged`: a fixture hypertension build is byte-identical before and after this task (regression, default `pathology`).
7. `test_builder_selects_pathology_by_config`: `pathology: glucose` builds days with the glucose signals; an unknown value raises `BenchmarkConfigError`.
8. `test_c2_c3_injection_reuse_on_glucose_device_chain`: dropout, silent bias and replay apply to the glucose device stream through the shared machinery of T07 and T08 with no copy of their code.
9. `test_missing_diabetes_registry_blocks_labelling`: labelling a glucose day without `configs/registry/diabetes.yaml` and its clinician review raises `RegistryNotAvailableError` naming WS00-T07; the generator itself still runs and the manifest states `labelling: unavailable`.
10. `test_simglucose_check_recorded`: `docs/benchmark/second-pathology.md` has the required headings and a `status:` line for each item (installed, version, licence, patient roster, API surface used).

## Passi

1. Confirm the precondition (M3 reached, ADR-019) and record it in the completion note; if not reached, stay `blocked`.
2. Check simglucose only from what is available locally (an installed package or documentation supplied by a human): installation, version, licence, the virtual patient roster and the API the wrapper uses. Without a local copy the honest entry is `not evaluated: no local installation`; do not write the API or the roster from memory. Fill `docs/benchmark/second-pathology.md` with the H2 headings `## Question`, `## Local availability`, `## Licence`, `## Patient roster and API`, `## Representation decisions`, `## Blocked items`, `## Decision`.
3. Write the ADR (status `proposed`): a separate `GlucosePatientParams` dataclass in `ralmon.benchmark.glucose` instead of changing `PatientParams`; new `SignalId` members (glucose reading, insulin and meal events) are a change to the `#signals` contract owned by WS05 and go through an ADR by that owner; the second pathology needs its own registry and clinician review.
4. Write `tests/benchmark/test_glucose.py`; run, confirm failure; commit `WS04-T14: add failing glucose tests`.
5. Implement the subpackage: the physiology protocol with the simglucose wrapper (named stream, integer-ms grid), `GlucosePriorSource` (values from the simulator's virtual patients with `source_ref` naming package and version, or awaiting a human), the glucose measurement chain (error model rows awaiting a source), and the `pathology` option of the builder (default unchanged).
6. Write `configs/priors/literature_diabetes.yaml` with `awaiting_human_value` rows; regenerate the provenance table.
7. Refactor; run `ruff check src tests`, `mypy src/ralmon`, `pytest tests/benchmark -q`; commit `WS04-T14: add second pathology generator (glucose)`; set `status: done`. If the task is dropped under the cut order, record `status` unchanged and state in `docs/benchmark/second-pathology.md` `## Decision` that the paper reports one pathology (ADR-001).

## Done when

- `pytest tests/benchmark/test_glucose.py -q` exits 0 and `pytest tests/benchmark -q` exits 0 (hypertension outputs unchanged).
- `ruff check src tests` exits 0 and `mypy src/ralmon` exits 0.
- `grep -cE '^## (Question|Local availability|Licence|Patient roster and API|Representation decisions|Blocked items|Decision)$' docs/benchmark/second-pathology.md` prints `7`.
- `grep -c '^## ADR-' docs/plan/03-decisions.md` has increased by one and the new entry names `GlucosePatientParams`.
