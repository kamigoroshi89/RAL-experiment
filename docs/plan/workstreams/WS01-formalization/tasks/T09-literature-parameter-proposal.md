---
id: WS01-T09
title: Literature-anchored proposal of registry and prior values (agent-assisted, human-checked)
workstream: WS01-formalization
owner: human
status: in_progress
depends_on: ["WS01-T03", "WS04-T02"]
critical_path: false
non_negotiable: true
estimate_pd: 2
sources: ["analisi §4.1", "analisi §5.1", "analisi §10 (1)", "ADR-043"]
interfaces: ["02-interfaces.md#parameter-registry", "02-interfaces.md#priorsource"]
review_items: []
---
## Obiettivo

Replace, for now, the clinician's choice of values (WS00-T07, deferred by ADR-043) with a proposal anchored in published sources, and have gab check it before any value enters `configs/`. Research agents, run from gab's interactive session (the task needs network access, which the autonomous loop does not have: that is why the owner is `human`), propose for every name of `configs/registry/hypertension.yaml` (entries and `unset`) and every row of `configs/priors/literature_hypertension.yaml` either a value or the reason why no literature value exists (design choice, device standard, needs data). Each proposal carries the verbatim passage, the citation with URL or DOI and the step from passage to value. Nothing here is a clinical review and nothing may be described as one. Concrete output: `docs/formal/parameter-literature-proposal.md`, then the values accepted by gab in the two YAML files with their provenance.

## Contesto

- `docs/plan/03-decisions.md` ADR-043 (this task), ADR-020 (unverified values are labelled), ADR-027 (fixture registry for tests, separate from the clinical registry), ADR-018 (references verified by a human), ADR-037 (nothing under `paper/`).
- `docs/formal/03-parameter-registry.md` (schema, layout rules, version bump on change) and `configs/registry/hypertension.yaml`.
- `docs/benchmark/parameter-provenance.md`, `configs/priors/literature_hypertension.yaml` and the `PriorSource` row conventions (`source_type`, `source_ref`, `verified_by`).
- `docs/benchmark/datasets-overview-for-advisor.md` section 8 (open questions: cuff error from VitalDB or from the device standard; clean-segment rule).
- Decision of gab (2026-10-08, with ADR-027): `cuff_error_sd` gets, beside the device standard, a supplementary estimate from the 30 VitalDB cases on disk (cuff `Solar8000/NIBP_SBP` against arterial `Solar8000/ART_SBP`), reported with its method and caveats (intraoperative patients, arterial line not the reference of the standard).
- The drug class behind the PK/PD rows is not named anywhere in the plan: the proposal names the class it assumes and gab confirms it.

## File toccati

- `docs/formal/parameter-literature-proposal.md` (create)
- `configs/registry/hypertension.yaml` (modify, only rows accepted by gab; registry version bump)
- `configs/priors/literature_hypertension.yaml` (modify, only rows accepted by gab)
- `docs/benchmark/parameter-provenance.md` (regenerate)

## Test

Verification checks:

1. The proposal has one row per name of `hypertension.yaml` (entries and `unset`) and per row of `literature_hypertension.yaml`; each row has `status` in {`proposed`, `no-literature-value`}, and a `proposed` row has value, unit, citation (authors, title, venue or issuer, year, URL or DOI), verbatim passage and derivation.
2. Every citation was opened by an agent on the date given in the row; nothing is filled from memory; a guideline is cited in the version that was opened.
3. A row whose value comes from analisi §4.1 is `proposed` only if a published source supports it; otherwise it keeps the analisi value marked "illustrative, unverified".
4. No sentence of the proposal or of the YAML rationales claims clinical validation or a clinician's review.
5. After gab's check: accepted rows are in the YAML files with `reviewed_by: null` (registry) or `verified_by` set only for sources gab opened (priors); the rationale says "literature-anchored proposal (WS01-T09), not clinically reviewed"; `python -m ralmon.benchmark.priors --check-table` and the registry loader tests pass.

## Passi

1. Agents: build the row list from the two YAML files; group the names by kind (clinical threshold, schedule or window, response, scale, priority, device, monitor configuration).
2. Agents: for each clinical name search guidelines (for example the ESC/ESH and NICE hypertension guidelines), drug labels for the assumed class and device validation standards; record the passage and the derivation, or `no-literature-value` with the reason.
3. Agents: write `docs/formal/parameter-literature-proposal.md` with a summary of what is anchored, what is a design choice and what needs data or a clinician.
4. gab: accept, change or reject each row in the document (one column `decision_gab`).
5. Agents: write the accepted rows into the YAML files, bump the registry version, regenerate the provenance table, run the checks of item 5. Bibliography entries for the cited sources are added by gab under `paper/` (ADR-037), with the `verified` flag of ADR-018.

## Done when

- `test -f docs/formal/parameter-literature-proposal.md` exits 0.
- Every row of the proposal has a `decision_gab` value.
- `python -m ralmon.benchmark.priors --check-table` exits 0 and `pytest -q` exits 0.
- `python3 tools/check_plan.py` exits 0.

## Notes

### In progress in the interactive session (agent, 2026-10-08)

Started on 2026-10-08 in gab's interactive session: three research agents (A: clinical thresholds and care-plan counts; B: patient, drug response and adherence; C: scales, priorities, device and monitor parameters, plus the VitalDB cuff-error estimate). `owner: human`: the autonomous loop does not resume or select this task (it needs network access).
