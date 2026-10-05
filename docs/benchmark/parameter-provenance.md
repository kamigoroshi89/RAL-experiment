# Parameter provenance of the benchmark generator

Document WS04-T02. This is the table that a human verifies before any benchmark is used for a reported result (H1 of `docs/plan/workstreams/WS04-benchmark/README.md`). Everything between the two `GENERATED` markers is produced from the parameter files; edit the YAML, never the table.

Validation in this project is technical and pre-clinical: no real patients are involved, and nothing in this table is a clinical claim.

## Purpose

Every parameter of the latent patient, the PK/PD response, the adherence model and the device error model enters the generator through `PriorSource` (ADR-005, `docs/plan/02-interfaces.md#priorsource`). `LiteraturePriorSource` reads `configs/priors/literature_hypertension.yaml`, which has one row for each of the 17 contract fields. When present, the rows of `configs/benchmark/generator_design.yaml`, `configs/benchmark/care_plans.yaml` and `configs/benchmark/injections.yaml` are rendered too, so that one table lists every number that is not code.

The rule behind the table (ADR-020, parameter policy of the WS04 README): no agent chooses or recalls a clinical, physiological or device value. A row for which no human has supplied a value has `value: null` and the status `awaiting_human_value`; the loader refuses to use it. A value without a `source_ref` makes the loader fail. A prior built from arithmetic test numbers is marked `fixture_only` and is refused unless a test asks for it.

## How a human verifies a row

1. Open the row in `configs/priors/literature_hypertension.yaml` (or in the design config that holds it).
2. Supply the value (`value`, or `dist` for a patient row) together with the `source_ref` that supports it. Alternatively, place a short extract with its citation under `docs/benchmark/source-extracts/` for an agent to transcribe; the agent transcribes only what that extract states.
3. Open the source. Confirm the value, the unit, the population it describes and, for `ar_noise_phi`, the sampling step; write that step in `reference_step_ms`.
4. Set `source_type` and write the reason in `rationale` (the fields mirror `source_ref`, `rationale` and `reviewed_by` of the parameter registry, `docs/formal/03-parameter-registry.md`).
5. Set `status: filled` and `verified_by` to your name. Leave `verified_by` null if you have not opened the source.
6. Regenerate the table with `python -m ralmon.benchmark.priors --write-table` and review the diff. `python -m ralmon.benchmark.priors --check-table` exits 1 when the committed table no longer matches the YAML.

The drug behind the PK/PD rows is the one anchored in the parameter registry (`configs/registry/hypertension.yaml`, clinical review WS00-T07). No drug is named here or in the YAML.

## Meaning of `source_type`

- `published_literature`: a value taken from a named publication, cited in `source_ref`.
- `standard`: a limit or procedure of a named standard, with edition and clause in `source_ref`.
- `public_dataset`: a value estimated or read from a named public dataset table.
- `design_choice`: a generator design parameter proposed by an agent with a one-line rationale; a human confirms it (H3).
- `declared_assumption`: no source exists; the model is declared as an assumption (for example adherence, analisi §5.1).
- `illustrative_unverified`: an example value taken from the analysis document, labelled illustrative and unverified.
- `fixture_only`: an arithmetic number for a test; allowed only in a file with `fixture_only: true`, never in this repository's priors.

## Meaning of `status`

- `filled`: a value or distribution is present with its `source_ref`; `verified_by` says whether a human checked it.
- `awaiting_human_value`: no value; a strict load fails, and a use of the parameter fails with the name of the row.

A benchmark is `provisional` while any row is `awaiting_human_value`, and every filled row without `verified_by` is reported as unverified in the benchmark manifest and in the limitations (ADR-020).

## Standing notes

- `cuff_error_sd_mmhg` and `cuff_bias_mmhg` cite ISO 81060-2. The standard gives acceptance limits for a device under validation, not the error of a particular device. The human declares whether the benchmark uses the limits as a conservative device model or a typical performance from a validation study, and writes the choice in `rationale`. The edition and the clause are to be confirmed by the human.
- The adherence rows are declared assumptions: no public smart-dispenser dataset is known (analisi §5.1).
- The contract has no field for several parameters that the generator needs (reference step of the autoregressive coefficient, circadian phase, heart-rate and SpO2 levels, pulse-rate error, nominal cuff inflation duration, dose normalisation, adherence persistence, double-take gap). They are listed in ADR-038 and enter as rows of `configs/benchmark/generator_design.yaml` until the contract changes.

## Generated table

<!-- BEGIN GENERATED -->
- Source files: `configs/priors/literature_hypertension.yaml`
- Parameter rows: 17
- Rows by status: filled: 0, awaiting_human_value: 17
- Rows verified by a human (verified_by set): 0 of 17
- Filled rows still without verified_by (unfilled rows are not counted): 0
- Fixture-only rows: 0

| parameter | field | unit | value or distribution | source_ref | source_type | verified_by | status | consumer task | note |
|---|---|---|---|---|---|---|---|---|---|
| baseline_sbp_mmhg | PatientParams.baseline_sbp_mmhg | mmHg | - | - | - | - | awaiting_human_value | WS04-T03 | Baseline systolic pressure of the latent patient. Supply a value or a distribution (dist) and its source_ref; analisi §5.1 item 1 expects distributions estimated on a cohort, which WS04-T13 provides once credentialing exists. No value has been chosen by an agent. |
| circadian_amplitude_mmhg | PatientParams.circadian_amplitude_mmhg | mmHg | - | - | - | - | awaiting_human_value | WS04-T03 | Amplitude of the circadian component of the latent pressure (analisi §5.1 item 1). Circadian phase has no contract field: see the contract gaps in ADR-038. |
| ar_noise_sd_mmhg | PatientParams.ar_noise_sd_mmhg | mmHg | - | - | - | - | awaiting_human_value | WS04-T03 | Standard deviation of the autoregressive pressure noise (analisi §5.1 item 1), in mmHg. |
| ar_noise_phi | PatientParams.ar_noise_phi | 1 | - | - | - | - | awaiting_human_value | WS04-T03 | Autoregressive coefficient of the pressure noise. It is meaningless without its sampling step: the human supplies reference_step_ms (integer ms) with the value, and WS04-T03 rescales to the generator step. |
| emax_mmhg | PatientParams.emax_mmhg | mmHg | - | - | - | - | awaiting_human_value | WS04-T04 | Maximal drug effect of the Emax model (analisi §5.1 item 1). Drug anchor: none yet. configs/registry/hypertension.yaml anchors no drug or guideline (its delta1 and delta2 are labelled illustrative, unverified, and nothing in it is reviewed); this row must carry the anchor chosen at the clinical review of the registry (WS00-T07) and cite the same drug. No agent names a drug. The sign convention of the effect (a reduction as a positive magnitude or a signed value) is a contract gap, see ADR-038. |
| ec50 | PatientParams.ec50 | 1 | - | - | - | - | awaiting_human_value | WS04-T04 | Concentration giving half of the maximal effect, read as dimensionless on a concentration normalised to the unit dose (the contract gives no unit; the dose normalisation convention is a gap, see ADR-038). Drug anchor: none yet, as for emax_mmhg: the anchor is the registry's, set at WS00-T07. |
| absorption_rate_per_h | PatientParams.absorption_rate_per_h | 1/h | - | - | - | - | awaiting_human_value | WS04-T04 | First-order oral absorption rate of the one-compartment model (analisi §5.1 item 1), per hour. Drug anchor: none yet, as for emax_mmhg: the anchor is the registry's, set at WS00-T07. |
| elimination_rate_per_h | PatientParams.elimination_rate_per_h | 1/h | - | - | - | - | awaiting_human_value | WS04-T04 | First-order elimination rate of the one-compartment model, per hour. Drug anchor: none yet, as for emax_mmhg: the anchor is the registry's, set at WS00-T07. |
| onset_delay_range_ms | PatientParams.onset_delay_range_ms | ms | - | - | - | - | awaiting_human_value | WS04-T04 | Lower and upper bound of the onset window of the response, as value: {lower_ms, upper_ms} in integer ms, equal for every patient. It informs the clinician's choice of delta1 and delta2 in the registry (docs/formal/03-parameter-registry.md section 1.2 rule 6); the numbers are not copied between the files. Drug anchor: none yet in the registry; set at WS00-T07. |
| p_delay | AdherenceParams.p_delay | 1 | - | analisi §5.1: adherence is declared as an assumption (no public smart-dispenser dataset known) | declared_assumption | - | awaiting_human_value | WS04-T05 | Probability that a dose is taken late (Markov adherence model, analisi §5.1). The sum of the three probabilities must not exceed 1; persistence between doses is a contract gap, see ADR-038. |
| p_omission | AdherenceParams.p_omission | 1 | - | analisi §5.1: adherence is declared as an assumption (no public smart-dispenser dataset known) | declared_assumption | - | awaiting_human_value | WS04-T05 | Probability that a dose is omitted (Markov adherence model, analisi §5.1). |
| p_double_take | AdherenceParams.p_double_take | 1 | - | analisi §5.1: adherence is declared as an assumption (no public smart-dispenser dataset known) | declared_assumption | - | awaiting_human_value | WS04-T05 | Probability of a double take (Markov adherence model, analisi §5.1). The double-take gap in time has no contract field, see ADR-038. |
| mean_delay_ms | AdherenceParams.mean_delay_ms | ms | - | analisi §5.1: adherence is declared as an assumption (no public smart-dispenser dataset known) | declared_assumption | - | awaiting_human_value | WS04-T05 | Mean delay of a late dose, in integer ms. |
| cuff_error_sd_mmhg | DeviceErrorModel.cuff_error_sd_mmhg | mmHg | - | ISO 81060-2 (edition and clause to be confirmed by the human); named in analisi §5.1 | standard | - | awaiting_human_value | WS04-T06 | Standard deviation of the cuff error. ISO 81060-2 gives acceptance limits for a device under validation, not the error of one particular device: the human must declare whether the benchmark uses the limits as a conservative device model or a typical performance from a validation study, and states the choice in rationale. The edition and the clause are to be confirmed by the human (analisi §5.1: the values are to be verified). The registry has the same quantity as cuff_error_sd (unset): keep one source of truth. |
| cuff_bias_mmhg | DeviceErrorModel.cuff_bias_mmhg | mmHg | - | ISO 81060-2 (edition and clause to be confirmed by the human); named in analisi §5.1 | standard | - | awaiting_human_value | WS04-T06 | Systematic cuff error (bias). ISO 81060-2 gives acceptance limits for a device under validation, not the error of one particular device: the human must declare whether the benchmark uses the limits as a conservative device model or a typical performance from a validation study, and states the choice in rationale. The edition and the clause are to be confirmed by the human. |
| dispenser_bounce_prob | DeviceErrorModel.dispenser_bounce_prob | 1 | - | - | - | - | awaiting_human_value | WS04-T07 | Probability that a dispenser sensor bounce produces a spurious DISPENSE event (C2 fault, analisi §5.1 item 3). The human supplies the value and its source_ref. |
| ble_dropout_rate_per_h | DeviceErrorModel.ble_dropout_rate_per_h | 1/h | - | - | - | - | awaiting_human_value | WS04-T07 | Rate per hour of BLE link dropouts (C2 fault, analisi §5.1 item 3). The human supplies the value and its source_ref. |
<!-- END GENERATED -->
