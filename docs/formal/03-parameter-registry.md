# 03 Parameter registry: design, schema and anchoring procedure

Document WS01-T03. It designs the parameter registry, fixes its YAML schema and loader behaviour, lists every registry name required by the templates of `docs/formal/02-templates.md` (WS01-T02) and the time semantics of `docs/formal/01-signals-sampling.md` (WS01-T01), and defines the procedure that anchors each value to a drug and a guideline. It is a design document plus the seed file `configs/registry/hypertension.yaml` and the schema `configs/registry/registry.schema.json`. It changes no contract of `docs/plan/02-interfaces.md`: gaps and clarifications are recorded in section 7 for WS01-T08. Validation in this project is technical and pre-clinical; nothing in this document or in the registry file is a clinical claim.

The registry is filled with clinical values and reviewed by the clinician in WS00-T07 (the clinician is recruited in WS00-T03). This task does not decide any clinical value, does not assign a drug or a guideline to any parameter and does not review anything (ADR-020). The seed file therefore contains 17 entries, each a number that analisi §4.1, §4.2, §4.6 or §4.7 itself gives, each labelled "illustrative, unverified", each with `reviewed_by: null`; every other parameter that the templates need is declared `unset` and awaits a human value.

What this document answers (review items): R3 weakness 3 (parameters not anchored to a drug or a guideline; institutional pathway template versus per-patient care plan: sections 1, 4 and 5) and analisi §4.9 item 7 (versioning of the specification and per-patient calibration: section 5).

## 1 Purpose and rules

### 1.1 Purpose

The registry is the single source of every clinical parameter of the templates: the pressure band, the hold threshold, the look-back and window widths, the response-window bounds `delta1` and `delta2`, the response threshold, the dose limits, the per-template scales and priorities, and the physiological bounds used to complete unknown values in robustness intervals (`02-interfaces.md#parameter-registry`). It exists so that (a) no clinical number is written twice, (b) every number carries the reason it has and the person who reviewed it, and (c) an unreviewed number can be found and reported as unverified (ADR-020).

### 1.2 Rules

1. **Single source.** A template names its parameters (`Template.params`, `scale_param`, `priority_param`, `max_verdict_latency_param`); it never carries a value. Every value is read through `ParameterRegistry.get(name)`.
2. **No numeric clinical constant outside the loader.** No numeric clinical constant appears in `src/ralmon` outside the registry loader (`02-interfaces.md#parameter-registry`, rule). The check is mechanical and belongs to WS05-T03: an AST scan of the core packages for the illustrative values 50, 100, 110, 140 and 250. Fixture values live in `tests/fixtures/` and in `docs/formal/golden/`, never in `src/ralmon`.
3. **Every value carries its reason and its reviewer.** An entry has `rationale`, `source_ref` and `reviewed_by` (the fields of `RegistryEntry`). While `reviewed_by` is null, `rationale` ends with the string `illustrative, unverified`; the schema enforces this (section 2.2).
4. **No invented numbers.** The entries of version 0.1.0 are exactly the analisi-derived rows of the fixture registry F0 (`docs/plan/workstreams/WS01-formalization/README.md`): the numbers of analisi §4.1, §4.2, §4.6 and §4.7. The FIXTURE-ONLY rows of F0 (`sched_window`, `delta_resp`, `cuff_inflation_min`, `scale_hold`, `scale_resp`, `scale_sys`, `scale_int`, `priority_count`, `priority_resp`, `priority_sys`, `priority_int`, `cuff_error_sd`, `step_ms`, `reorder_delay_ms`) were chosen for hand arithmetic, have no clinical meaning and are not registry values. The names of those that a template needs are declared `unset`.
5. **The scale and priority examples are examples.** Analisi §4.2 gives 20 mmHg, 30 min and 1 dose as examples of scales and the order hold > range > sched as an example of priorities. Their assignment to the templates range, sched and count follows the F0 table, not the text of the analysis; the registry seeds them as illustrative, unverified, and the priority order is the clinician's own decision at review (WS00-T07, check 5).
6. **Relation to `PriorSource`.** The registry holds the parameters of the specification (what the monitor checks). `PriorSource` (`02-interfaces.md#priorsource`) holds the parameters of the benchmark generator (how synthetic patients behave). They are separate files with separate provenance. They meet at one point only: the reviewed onset window of the drug (`PatientParams.onset_delay_range_ms`) informs the clinician's choice of `delta1` and `delta2` (analisi §5.1); the numbers are not copied from one to the other. One name is shared in meaning and needs a decision: the cuff error standard deviation is `DeviceErrorModel.cuff_error_sd_mmhg` in `PriorSource` and `cuff_error_sd` in the registry (declared unset because the Gaussian error model of rho, WS01-T06, needs it); section 7 (OP-7) asks WS01-T06 and WS01-T08 to keep one source of truth.
7. **Terminology.** A pathway template is the institutional, population-level level; a patient care plan is the instance for one patient (`CarePlan`). The registry holds the parameters of the pathway template for one pathology (hypertension); per-patient values, if any, travel in the patient care plan (section 5). The words "Clinical Pathway" are never used for one patient's prescription (R3 weakness 3).
8. **What "clinically grounded" needs.** A drug-specific anchor is required before the paper may call any parameter clinically grounded: a named drug class and a named guideline, chosen by the clinician, with a verified reference, written in `rationale` and `source_ref`, and `reviewed_by` set (section 4). Until then the paper says "illustrative, unverified" (analisi §4.8 wording discipline, ADR-020).
9. **Unreviewed values are reported.** The run manifest and the paper limitations list every name whose `reviewed_by` is null as unverified.

## 2 YAML schema

The schema is `configs/registry/registry.schema.json` (JSON Schema, draft 2020-12). The file `configs/registry/hypertension.yaml` validates against it. The schema is the normative statement of the file format; the loader rules of section 2.5 are the normative statement of its behaviour.

### 2.1 Top-level keys

| Key | Type | Required | Meaning |
|---|---|---|---|
| `registry_version` | semantic version string `MAJOR.MINOR.PATCH` | yes | returned by `ParameterRegistry.version()`; pinned by `CarePlan.registry_version` (section 5) |
| `pathology` | string | yes | `hypertension` (ADR-001) |
| `review_status` | `unreviewed`, `partially_reviewed` or `reviewed` | yes | derived state of the review; consistency with the entries is checked at load (section 2.5, rule 9) |
| `window_parameters` | list of names | yes | names that are window parameters (section 2.4) |
| `entries` | list of entries | yes | parameters that have a value |
| `derived` | list of derived names | yes | latency bounds computed from a formula (section 2.3) |
| `unset` | list of unset names | yes | parameters that a consumer needs and that have no value yet |
| `overrides` | list of override ranges | no | clinician-approved ranges for per-patient values; empty in 0.1.0 (section 5) |

No other top-level key is allowed (`additionalProperties: false`).

### 2.2 Elements

**Entry.** Exactly the fields of the contract `RegistryEntry`, in this order, and nothing else (`additionalProperties: false`):

| Field | Schema | Contract type |
|---|---|---|
| `name` | string matching `^[a-z][a-z0-9_]*$` | `str` |
| `value` | number | `float` |
| `unit` | one of `mmHg`, `ms`, `dose`, `1` | `str` (`"mmHg"`, `"ms"`, `"dose"`, `"1"` ...) |
| `rationale` | non-empty string | `str` |
| `source_ref` | non-empty string | `str` |
| `reviewed_by` | non-empty string or null | `str | None` |

A conditional in the schema (`if reviewed_by is null then rationale matches illustrative, unverified$`) makes the ADR-020 rule mechanical: an unreviewed value cannot be written without saying that it is unverified. The `rationale` of an entry may be exactly `illustrative, unverified` or a derivation that ends with that string (for example "60 min of the hold formula, converted to ms: illustrative, unverified"). After review the `rationale` names the anchor (section 4) and the conditional no longer applies.

The unit strings are the four of the contract comment: `mmHg`, `ms`, `dose` and `1` (dimensionless counts and ranks). `1` is written as the string `"1"` in YAML so that it is not read as an integer.

**Derived.** `{name, unit, formula, template}`: a name computed by the loader (section 2.3). `formula` is a sum of terms; a term is a registry name or `step_ms`.

**Unset.** `{parameter, unit, required_by, note}`: a name that a consumer needs and that has no value yet. `required_by` is a list of template ids (`range`, `sched`, `hold`, `count`, `resp`, `sys`, `int`); it is empty for a name needed by another consumer, and the `note` says which. For the bounds `required_by` names the template whose interval semantics needs the bound. The `note` always begins with "value to be set and reviewed by WS00-T07".

**Override.** `{name, min, max, rationale, source_ref, reviewed_by}` (section 5).

**Layout of the seed file.** An element of `entries:` is a block mapping that starts with `  - name: <name>` and carries the five other keys at four-space indent in the contract order, so that a line-oriented tool can count them. Elements of `derived:` and `unset:` are one-line flow mappings; a block layout would put a `unit:` key at four-space indent under those lists too and would make the per-key line counts differ from the number of entries (the counts are a verification of this task, and a tool that counts `    unit:` lines must count entries only).

### 2.3 Serialisation of the contract

| Contract | In the file |
|---|---|
| `RegistryEntry` (`name`, `value`, `unit`, `rationale`, `source_ref`, `reviewed_by`) | one element of `entries`, field for field |
| `PhysioBounds(signal, lower, upper)` | not stored as such: bounds are stored as two entries `bound_<signal>_lower` and `bound_<signal>_upper` so that ADR-020 applies to them; `ParameterRegistry.bounds(signal)` composes the pair into a `PhysioBounds` (CP10, section 2.5, rule 5) |
| `ParameterRegistry.get(name)` | looks the name up in `entries`, then in `derived` (computed), then in `unset` (error) |
| `ParameterRegistry.version()` | `registry_version` |
| `Template.max_verdict_latency_param` ("registry entry") | a name in `derived`: the loader synthesises a `RegistryEntry` for it |

### 2.4 Window parameters

`docs/formal/01-signals-sampling.md` section 3.6 requires every window parameter to be a non-negative integer multiple of `T_s` and exempts time-valued entries that are not window edges (scales, `cuff_inflation_min`, `reorder_delay_ms`, `clock_skew_max_ms`); its CG-1 proposes a role attribute so that the check is mechanical. A role field cannot be added to an entry without breaking the rule that an entry has exactly the fields of `RegistryEntry`. The file therefore carries one extra top-level list, `window_parameters`, with the names to which the alignment rule applies: `sched_window`, `hold_lookback`, `int_window`, `delta1`, `delta2`. The derived width `delta2 - delta1` (the width of the RESP consequent window) is a difference of two listed names, checked as such (section 2.5, rule 8). The list is not a field of `RegistryEntry` and does not change the contract; it is recorded in section 7 (OP-5). The same list can be recomputed from the templates (the registry names that occur inside an interval bracket of `formula_past_time`); the list in the file lets a registry be checked without loading templates.

### 2.5 Loader behaviour (specification for `load_registry`, WS05-T03)

`load_registry(path=None, *, step_ms=None)` reads the file with a safe YAML loader (no object construction), validates it and returns an object that implements `ParameterRegistry`. The signature is the one WS05-T03 plans; it is not in the contract (section 7, OP-4). The rules below are the normative behaviour whether or not a JSON Schema validator is admitted as a dependency: the loader re-implements the checks of the schema in code.

1. **Strict load.** Structural violations of the schema raise `RegistryError`, naming the element (entry name or list index) and the rule. A name that occurs twice in `entries`, `derived` and `unset` together raises `RegistryError`. An unknown top-level key raises `RegistryError`. A value that is not finite raises `RegistryError`.
2. **Errors.** `RegistryError` is the base error. `UnsetParameterError` is a subclass of `RegistryError`. Both are proposed names; they are not in the public API list of the contract (section 7, OP-2).
3. **Name resolution, `get(name)`.** In this order: an entry returns its `RegistryEntry` (unreviewed entries are returned, never dropped); a derived name returns a computed entry (rule 4); an unset name raises `UnsetParameterError` naming the parameter and its `required_by`; any other name raises `RegistryError`.
4. **Unset names.** A template needs an unset name when a name in its `params`, its `scale_param`, its `priority_param` or the formula of its `max_verdict_latency_param` is unset. Loading the template table succeeds if every needed name is declared (an entry, a derived name or an unset name), because the template's structure does not depend on the value. Asking for the value raises `UnsetParameterError`; evaluating a template that needs it raises the same error and never substitutes a default. The registry object also exposes `is_declared(name)`, `is_set(name)` and the list of unset names (concrete methods, not in the `ParameterRegistry` protocol; OP-2).
5. **Bounds, `ParameterRegistry.bounds(signal)`.** Bounds are stored as entries, one lower and one upper, so that the rationale and reviewer rule of ADR-020 applies to them; `bounds(signal)` composes the pair into a `PhysioBounds` (CP10). The loader reads `bound_<signal>_lower` and `bound_<signal>_upper`, where `<signal>` is a `SignalId` value (which may contain underscores, for example `inflation_ms`: the prefix `bound_` and the suffix `_lower` or `_upper` are removed). Both must be entries; it returns `PhysioBounds(signal, lower, upper)` and raises `RegistryError` if `lower >= upper`. If either name is unset it raises `UnsetParameterError`; if neither is declared it raises `RegistryError`. `PhysioBounds` carries no rationale and no reviewer (CP10); the provenance of a bound is that of its two entries, read with `get`.
6. **Derived names.** The grammar of `formula` is `formula = term { "+" term } ; term = registry_name | "step_ms"`. The loader evaluates it by its own parser and never by `eval`. `step_ms` is the monitor step `T_s` and comes from the argument `step_ms` of `load_registry` (from `MonitorConfig.step_ms`); it is not stored in the file, because it is a monitor configuration value and not a clinical parameter (`docs/formal/02-templates.md` section 3.4). If a derived name is requested while `step_ms` is `None` the loader raises `RegistryError`. If a term is unset the loader raises `UnsetParameterError` naming the derived name and the unset term. The computed entry has the unit of the `derived` element, `source_ref = "docs/formal/03-parameter-registry.md section 3"`, `reviewed_by = None`, and a `rationale` that reads `derived: <formula>` and, if any term is an unreviewed entry, ends with `; illustrative, unverified`. A derived value is never itself reviewed; its inputs are.
7. **Casts (CP10).** Section 2.6.
8. **Window alignment.** When `step_ms` is given, every name of `window_parameters` that is an entry must be an integer multiple of `step_ms`, and `delta2 - delta1` must be a non-negative multiple of `step_ms`; a violation raises `RegistryError` naming the parameter and `step_ms`. The loader never rounds a value (T01 section 3.6). Names of `window_parameters` that are unset are checked when they receive a value.
9. **Review status.** `review_status` must agree with the entries: `unreviewed` requires every `reviewed_by` to be null; `reviewed` requires every `reviewed_by` to be non-null and `unset` to be empty; otherwise it must be `partially_reviewed`. A disagreement raises `RegistryError`.
10. **Template checks with the registry.** For every template, `scale_<id>` has the unit of the template margin (`mmHg`, `ms` or `dose`) and a value greater than 0; `priority_<id>` has unit `1`; both checks apply when the name is set (plan feasibility check F6 of `02-templates.md` section 5.4).
11. **Unverified list.** The registry object exposes the names whose `reviewed_by` is `None`, for the run manifest (rule 9 of section 1.2).

### 2.6 Casts and types (CP10)

`RegistryEntry.value` is a `float` for every unit, while durations are `DurationMs` (an `int`, `02-interfaces.md#time-and-units`) and priorities are `int`. The file stores every value as a float; the loader casts by unit and name:

| Kind | Stored as | Cast | Check |
|---|---|---|---|
| duration, unit `ms` | integral float, for example `3600000.0` | `DurationMs` (`int(value)`) | integrality: `value == int(value)`, else `RegistryError`; `value >= 0`; window parameters also aligned (rule 8); scales also `> 0` |
| priority, `priority_<id>`, unit `1` | integral float, for example `2.0` | `int(value)` | integrality; `value >= 1`; 1 is the highest priority, consistent with the ranking convention of WS01-T04 (`rank_alerts` orders lower numbers first; the F0 table states "1 = highest" and the contract does not, CP5) |
| pressure, unit `mmHg` | float | `float` | finite; scales `> 0` |
| dose count or limit, unit `dose` | float | `float` | finite; scales `> 0` |

Consumers that need an integer duration call the cast (WS05-T03 provides a helper, for example `as_duration_ms(entry)`); `RegistryEntry.value` stays a `float` as in the contract. `PhysioBounds` is composed from two float entries and stays float. The contract is unchanged; the gap (a float value for an integer quantity, and a bounds type without provenance) is recorded in section 7 (OP-1).

## 3 Entry inventory

### 3.1 Inventory

One row per name declared by `configs/registry/hypertension.yaml`: 17 entries, 17 unset names and 7 derived names. "Needed by" follows `docs/formal/02-templates.md` section 3 (the strings, the scale, priority and latency fields). "Origin" is the analisi section of an entry; an unset name has no value yet. "Anchor type (proposed)" classifies the parameter for the procedure of section 4; it is a proposal of this document that the clinician confirms or changes at review, and it is not an anchor. The values shown are the illustrative, unverified numbers of the seed file and are not clinical recommendations.

| Parameter | Unit | Status | Value | Needed by | Origin | Anchor type (proposed) | Cast at load |
|---|---|---|---|---|---|---|---|
| `bp_band_low` | `mmHg` | entry | `110` | range | analisi §4.1, illustrative, unverified | guideline target | `float` |
| `bp_band_high` | `mmHg` | entry | `140` | range | analisi §4.1, illustrative, unverified | guideline target | `float` |
| `bp_hold_threshold` | `mmHg` | entry | `100` | hold | analisi §4.1, illustrative, unverified | guideline target | `float` |
| `hold_lookback` | `ms` | entry | `3600000` | hold | analisi §4.1, illustrative, unverified | local care policy | `DurationMs`, integral, multiple of `step_ms` |
| `dose_max_24h` | `dose` | entry | `2` | count | analisi §4.1, illustrative, unverified | local care policy | `float` |
| `dose_min_day_end` | `dose` | entry | `2` | count | analisi §4.1, illustrative, unverified | local care policy | `float` |
| `int_window` | `ms` | entry | `300000` | int | analisi §4.1, illustrative, unverified | local care policy | `DurationMs`, integral, multiple of `step_ms` |
| `delta1` | `ms` | entry | `3600000` | resp | analisi §4.6, illustrative, unverified | pharmacology | `DurationMs`, integral, multiple of `step_ms` |
| `delta2` | `ms` | entry | `10800000` | resp | analisi §4.6, illustrative, unverified | pharmacology | `DurationMs`, integral, multiple of `step_ms` |
| `bound_bp_lower` | `mmHg` | entry | `50` | range, hold, resp (through `bp`) | analisi §4.7 (step 2), illustrative, unverified | physiological plausibility | `float` |
| `bound_bp_upper` | `mmHg` | entry | `250` | range, hold, resp (through `bp`) | analisi §4.7 (step 2), illustrative, unverified | physiological plausibility | `float` |
| `scale_range` | `mmHg` | entry | `20` | range | analisi §4.2, illustrative, unverified | local care policy | `float`, > 0 |
| `scale_sched` | `ms` | entry | `1800000` | sched | analisi §4.2, illustrative, unverified | local care policy | `DurationMs`, integral, > 0 |
| `scale_count` | `dose` | entry | `1` | count | analisi §4.2, illustrative, unverified | local care policy | `float`, > 0 |
| `priority_hold` | `1` | entry | `1` | hold | analisi §4.2, illustrative, unverified | local care policy | `int`, rank >= 1 |
| `priority_range` | `1` | entry | `2` | range | analisi §4.2, illustrative, unverified | local care policy | `int`, rank >= 1 |
| `priority_sched` | `1` | entry | `3` | sched | analisi §4.2, illustrative, unverified | local care policy | `int`, rank >= 1 |
| `sched_window` | `ms` | unset | none | sched | awaiting a human value (WS00-T07) | local care policy | `DurationMs`, integral, multiple of `step_ms` |
| `delta_resp` | `mmHg` | unset | none | resp | awaiting a human value (WS00-T07) | pharmacology | `float` |
| `cuff_inflation_min` | `ms` | unset | none | sys | awaiting a human value (WS00-T07) | device validation protocol | `DurationMs`, integral |
| `scale_hold` | `mmHg` | unset | none | hold | awaiting a human value (WS00-T07) | local care policy | `float`, > 0 |
| `scale_resp` | `mmHg` | unset | none | resp | awaiting a human value (WS00-T07) | local care policy | `float`, > 0 |
| `scale_sys` | `ms` | unset | none | sys | awaiting a human value (WS00-T07) | local care policy | `DurationMs`, integral, > 0 |
| `scale_int` | `ms` | unset | none | int | awaiting a human value (WS00-T07) | local care policy | `DurationMs`, integral, > 0 |
| `priority_count` | `1` | unset | none | count | awaiting a human value (WS00-T07) | local care policy | `int`, rank >= 1 |
| `priority_resp` | `1` | unset | none | resp | awaiting a human value (WS00-T07) | local care policy | `int`, rank >= 1 |
| `priority_sys` | `1` | unset | none | sys | awaiting a human value (WS00-T07) | local care policy | `int`, rank >= 1 |
| `priority_int` | `1` | unset | none | int | awaiting a human value (WS00-T07) | local care policy | `int`, rank >= 1 |
| `bound_inflation_ms_lower` | `ms` | unset | none | sys (interval semantics) | awaiting a human value (WS00-T07) | device validation protocol | `DurationMs`, integral |
| `bound_inflation_ms_upper` | `ms` | unset | none | sys (interval semantics) | awaiting a human value (WS00-T07) | device validation protocol | `DurationMs`, integral |
| `bound_dose_count_lower` | `dose` | unset | none | count (interval semantics) | awaiting a human value (WS00-T07) | local care policy | `float` |
| `bound_dose_count_upper` | `dose` | unset | none | count (interval semantics) | awaiting a human value (WS00-T07) | local care policy | `float` |
| `cuff_error_sd` | `mmHg` | unset | none | none (error model of rho, WS01-T06) | awaiting a human value (WS00-T07) | device validation protocol | `float` |
| `clock_skew_max_ms` | `ms` | unset | none | none (monitor configuration) | awaiting a human value (WS00-T07) | system configuration (not clinical) | `DurationMs`, integral |
| `max_latency_range` | `ms` | derived | `step_ms` | range | docs/formal/02-templates.md section 3.2 | not a parameter | `DurationMs`, computed |
| `max_latency_sched` | `ms` | derived | `sched_window + step_ms` | sched | docs/formal/02-templates.md section 3.2 | not a parameter | `DurationMs`, computed |
| `max_latency_hold` | `ms` | derived | `step_ms` | hold | docs/formal/02-templates.md section 3.2 | not a parameter | `DurationMs`, computed |
| `max_latency_count` | `ms` | derived | `step_ms` | count | docs/formal/02-templates.md section 3.2 | not a parameter | `DurationMs`, computed |
| `max_latency_resp` | `ms` | derived | `delta2 + step_ms` | resp | docs/formal/02-templates.md section 3.2 | not a parameter | `DurationMs`, computed |
| `max_latency_sys` | `ms` | derived | `step_ms` | sys | docs/formal/02-templates.md section 3.2 | not a parameter | `DurationMs`, computed |
| `max_latency_int` | `ms` | derived | `step_ms` | int | docs/formal/02-templates.md section 3.2 | not a parameter | `DurationMs`, computed |

Counts: 17 entries (`reviewed_by` null for all); 17 unset names (11 needed by templates: `sched_window`, `delta_resp`, `cuff_inflation_min`, four scales and four priorities; 4 bounds; `cuff_error_sd`; `clock_skew_max_ms`); 7 derived latency names.

### 3.2 Which templates resolve with version 0.1.0

| Template | `params` | `scale_param` | `priority_param` | `max_verdict_latency_param` | Resolvable with 0.1.0 |
|---|---|---|---|---|---|
| RANGE | `bp_band_low` (entry), `bp_band_high` (entry) | `scale_range` (entry) | `priority_range` (entry) | `max_latency_range` (derived) | yes |
| SCHED | `sched_window` (unset) | `scale_sched` (entry) | `priority_sched` (entry) | `max_latency_sched` (derived, needs an unset name) | no: `sched_window` |
| HOLD | `bp_hold_threshold` (entry), `hold_lookback` (entry) | `scale_hold` (unset) | `priority_hold` (entry) | `max_latency_hold` (derived) | no: `scale_hold` |
| COUNT | `dose_max_24h` (entry), `dose_min_day_end` (entry) | `scale_count` (entry) | `priority_count` (unset) | `max_latency_count` (derived) | no: `priority_count` |
| RESP | `delta1` (entry), `delta2` (entry), `delta_resp` (unset) | `scale_resp` (unset) | `priority_resp` (unset) | `max_latency_resp` (derived) | no: `delta_resp`, `scale_resp`, `priority_resp` |
| SYS | `cuff_inflation_min` (unset) | `scale_sys` (unset) | `priority_sys` (unset) | `max_latency_sys` (derived) | no: `cuff_inflation_min`, `scale_sys`, `priority_sys` |
| INT | `int_window` (entry) | `scale_int` (unset) | `priority_int` (unset) | `max_latency_int` (derived) | no: `scale_int`, `priority_int` |

Only RANGE resolves completely. Every other template needs at least one value that a human has to supply. This is intended by ADR-020, and it has a consequence for the experiments (section 7, OP-11): the benchmark runs of WS08 that need scales and priorities for all seven templates cannot read them from this file until WS00-T07 has supplied them.

### 3.3 Names that are deliberately not registered

1. `step_ms` (`T_s`) and `reorder_delay_ms` (`D`) are monitor configuration (`MonitorConfig`), not clinical parameters, and their F0 values are FIXTURE-ONLY. The grammar of the templates and the derived formulas may mention `step_ms`; the loader receives it as an argument (section 2.5, rule 6). Their F0 values are not in the registry.
2. `meas_min_day` (five measurements a day, analisi §2 R2 weakness 5 and §4.6) is an analisi-derived F0 row, but WS01-T02 did not adopt a measurement-count obligation (CP2, `02-templates.md` section 4.4), so no template needs it and it is neither an entry nor an unset name. If the obligation is adopted, `meas_min_day` becomes an entry with a minor version bump (section 5) after the ADR that creates the template.
3. The FIXTURE-ONLY values of F0 (the numbers of the rows marked FIXTURE-ONLY in the WS01 README) stay in `docs/formal/golden/templates.yaml` and in test fixtures. They are not copied here even as unreviewed values, and none is quoted in this document.
4. `age` is an instance term of the templates (`02-templates.md` section 1.4), `T_day` is a definition (T01 section 1.4) and `bp_pre`, `bp_drop`, `dose_count`, `meas_count` are derived signals: none is a registry name.
5. The Boolean and status signals (`meas`, `dispense`, `intake`, `sched_tick`, `day_end`, `auth`, `presence`, `cuff_health`) take values in {0, 1} by construction; their completion in an interval is structural and needs no clinical bound. The evidence-only signals `hr_ecg`, `hr_pulse` and `spo2` are used by no template and have no bound entry. The derived pressure signals `bp_pre` and `bp_drop` take their interval from the bounds of `bp`.

### 3.4 Notes on the inventory

1. **Bounds.** `bound_bp_lower` and `bound_bp_upper` (analisi §4.7 step 2, the example interval for systolic pressure) are seeded. The bounds for `inflation_ms` and for the derived counter `dose_count` are declared unset because a template's margin reads those signals and the interval semantics (WS01-T05, CP12) has to complete their unknown future values. Whether they are needed is WS01-T05's decision; the names are declared now so that the loader has an error to raise, and they are removed by a major version bump if WS01-T05 decides that no bound is needed (OP-8).
2. **Latency.** `max_latency_<id>` is `B + step_ms` for the deadline offset `B` of the template (`02-templates.md` section 3.2). Only `sched_window` (SCHED) and `delta2` (RESP) enter, so `max_latency_sched` is derived from an unset name and cannot be computed until `sched_window` has a value.
3. **Scales.** The scale of a template has the unit of its margin dimension (`02-templates.md` section 2.6): mmHg for RANGE, HOLD, RESP; ms for SCHED, SYS, INT; dose for COUNT. The units in the inventory follow that rule and are checked against the template table.
4. **Provenance of the scale examples.** `scale_range`, `scale_sched` and `scale_count` come from the three examples of analisi §4.2 (20 mmHg, 30 min, 1 dose). Analisi §4.2 does not say which template each belongs to; the assignment is that of the F0 table and is recorded as such in their `rationale`.

## 4 Anchoring procedure

The procedure turns an "illustrative, unverified" value into a reviewed, anchored one. It is followed by the clinician recruited in WS00-T03, the human who runs the review (WS00-T07), and an agent that edits the file on their instruction. It contains no clinical content: it says who decides, what is recorded, and what may never be filled in by an agent.

### 4.1 Anchor types

Every parameter has one anchor type. The classification below is proposed by this document and is confirmed or changed by the clinician at review; it is not an anchor.

| Anchor type | Parameters | Who supplies the anchor | What the anchor is |
|---|---|---|---|
| guideline target | `bp_band_low`, `bp_band_high`, `bp_hold_threshold` | the clinician | a named guideline and the target or threshold it states, for a named drug class |
| pharmacology | `delta1`, `delta2`, `delta_resp` | the clinician | the onset and response timing and the expected pressure change of a named drug class, from a named reference |
| local care policy | `sched_window`, `hold_lookback`, `int_window`, `dose_max_24h`, `dose_min_day_end`, `scale_<id>`, `priority_<id>`, `bound_dose_count_lower`, `bound_dose_count_upper` | the clinician, for the institution | a statement of the local policy, with the institution and date of the policy, or the clinician's own judgement written as such |
| device validation protocol | `cuff_error_sd`, `cuff_inflation_min`, `bound_inflation_ms_lower`, `bound_inflation_ms_upper` | the clinician or the device owner, source verified by a human | the device specification or the validation protocol that the source refers to; the source is verified by a human (analisi §5.1: the values are to be verified) |
| physiological plausibility | `bound_bp_lower`, `bound_bp_upper` | the clinician | a plausibility statement for the signal (the range outside which a reading is not credible), with a reference if the clinician gives one |
| system configuration (not clinical) | `clock_skew_max_ms` | the system owner | measured clock behaviour of the devices; not a clinical parameter and not anchored to a drug or a guideline |

### 4.2 Procedure

1. **Freeze the input.** The reviewer starts from one committed version of `hypertension.yaml`. Every entry is shown exactly as it is stored: value, unit, `rationale`, `source_ref`. An entry whose `rationale` ends with "illustrative, unverified" is shown as such and is not presented as a recommendation.
2. **No agent anchors from memory.** No agent assigns a drug, a drug class, a guideline, a threshold, a timing or a bound from memory, from a fixture or from general knowledge (ADR-020). An agent does not propose a value, does not "complete" an unset name and does not search for a reference to fill a gap. The clinician states each anchor.
3. **Choose the drug class and the guideline.** The clinician chooses the drug class and the guideline of the pathway template for the pathology. The choice is recorded once, in the review log of WS00-T07 (`## Drug and guideline anchoring`), and then per parameter in `rationale` and `source_ref`. If the clinician does not anchor a parameter, the log says `not anchored` for it and the parameter stays unverified.
4. **Classify.** Each parameter is checked against its anchor type (section 4.1). The clinician may change the type. The type decides what evidence the anchor must give.
5. **Decide entry by entry.** For every entry the clinician decides `approved`, `changed`, `rejected` or `not assessable`. For every unset name the clinician supplies a value and its anchor or says `not assessable`.
6. **Write the anchor into the file.** For an approved entry, `rationale` and `source_ref` are replaced by the anchor as the clinician states it: a drug class and guideline (guideline target, pharmacology), a policy (local care policy), a protocol (device validation protocol), a plausibility statement (physiological plausibility). For a changed entry the value and unit are updated too. `source_ref` names the source (a guideline document with its section, a protocol, a policy, or the review log entry). The agent writes what the clinician states and adds nothing.
7. **References are unverified until a human checks them.** Any reference in `source_ref` or `rationale` is marked `[ref-needed: WS03]` until a human sets it as verified in the bibliography (ADR-018); the paper build fails on an unverified cited reference. An unmarked reference is not allowed.
8. **Set the reviewer.** `reviewed_by` receives the clinician identifier used in the review log, for approved and changed entries only, and only after the decision of step 5. It is never set by an agent on its own authority, and never before the review. Rejected and `not assessable` entries keep `reviewed_by: null`.
9. **Promote unset names.** A name that receives a value moves from `unset:` to `entries:` in the entry layout of section 2.2, with the unit stated in the `unset` element (a different unit is a major version bump, section 5). A name is never in both lists. If the name is a window parameter it must pass the alignment rule (section 2.5, rule 8).
10. **Update the status and the version.** Set `review_status` (section 2.5, rule 9) and bump `registry_version` by the rule of section 5. Validate the file against the schema and run the loader tests.
11. **Report what is not reviewed.** The run manifest and the paper limitations list every name whose `reviewed_by` is null as unverified (section 1.2, rule 9). Values that were changed at review are reported with their `source_ref`. Undetectable and unanchored parameters are reported, not hidden.
12. **Claim wording.** The paper may call a parameter clinically grounded only if its entry is reviewed and its anchor is drug-specific (rule 8 of section 1.2). All other parameters are described as illustrative or unverified. No sentence of the paper implies clinical validation of the values or of the system.

## 5 Versioning and per-patient overrides

The analysis (analisi §4.9 item 7) asks that the "patient-specific calibration" of parameters be reconciled with "the robot only evaluates specifications it cannot author or modify": the answer is versioning and signature. This section fixes the version rule and the per-patient policy.

### 5.1 Version rule

`registry_version` is a semantic version `MAJOR.MINOR.PATCH`, and the file version is the one returned by `ParameterRegistry.version()`.

| Change | Bump |
|---|---|
| text only: `rationale`, `source_ref`, `note`, comments; setting `reviewed_by` or `review_status` without changing a value | patch |
| a value change; a new entry; moving an unset name into `entries`; a new unset name; a change of `derived.formula` that keeps the name and unit | minor |
| a name change; a unit change; removing an entry, a derived name or an unset name; a change of the file format | major |

The first version is `0.1.0`. The version chosen when a clinician review is applied follows this rule and is recorded in the review log of WS00-T07.

Version `0.2.0` (2026-10-08, WS01-T09, ADR-043): values replaced or added from the literature-anchored proposals and design choices accepted by gab (`docs/formal/parameter-literature-proposal.md`); fourteen unset names moved into `entries` (minor bump); `priority_sys`, `priority_int` and `bound_dose_count_upper` stay unset; `review_status` stays `unreviewed` because no clinician has reviewed the file. The WS01-T03 check that no promoted name is an entry describes version 0.1.0 only. The AST scan of rule 2 reads the values of the current registry file (version 0.1.0: 50, 100, 110, 140 and 250), except monitor-configuration names such as `clock_skew_max_ms`.

### 5.2 Pinning and verification

A `CarePlan` pins `registry_version` (`02-interfaces.md#template`). The monitor rejects a plan whose `registry_version` is not the version of the loaded registry (WS05-T03, `verify_plan`, and `MonitorConfig.registry_version`); the match is exact string equality in 0.1.0, so every bump, including a patch, requires the plans to be issued again. A range of compatible versions is not defined (section 7, OP-9). The registry version and the SHA-256 digest of the registry file are proposed as fields of every run manifest so that a reported number can be tied to the exact file (proposal to WS04, WS05 and WS08 through WS01-T08; not a contract change of this task).

### 5.3 Per-patient calibration policy

1. **Where patient values live.** A value that differs from the pathway template for one patient travels in `TemplateInstance.param_values` inside the patient care plan. The plan is signed (`CarePlan.signature`, analisi §2 R1 weakness 9 and §4.9 item 7); the registry file is not patient-specific.
2. **Approved ranges.** A patient value is valid only for a name that has an element in `overrides:` and only inside its `[min, max]`. An element of `overrides:` carries `name`, `min`, `max`, `rationale`, `source_ref` and `reviewed_by`, with the same discipline as an entry: `reviewed_by` is null until the clinician has approved the range. The range is set by the clinician and never by an agent.
3. **Nothing else may be overridden.** A name that has no element in `overrides:` cannot appear in `param_values` with a value different from the registry value. Derived names are computed and cannot be overridden. A window parameter that receives a patient value must still pass the alignment rule.
4. **The robot evaluates, it does not author.** The robot node and the ward node evaluate the plan; they cannot author or modify a plan, a patient value or the registry (`CarePlan.signature`, `verify_plan`, WS05-T03).
5. **Version 0.1.0.** No per-patient override is supported: `overrides:` is empty in `hypertension.yaml`, and `param_values` may repeat registry values only. Whether patient-level overrides are wanted, and for which names, is a question to the clinician (Q3, section 6). If they are wanted, adding the ranges is a minor version bump.
6. **Open interpretation.** The contract does not say whether `param_values` holds only the values that differ from the registry or all values of the instance. This document assumes that a plan verifier compares each key of `param_values` with the registry value and with `overrides:`; the interpretation is recorded in section 7 (OP-6).

## 6 Review sheet for WS00-T07

The sheet lists every name of `hypertension.yaml` that has an entry or is unset, with its current state. It is generated from the YAML by a script that is not committed (verification 12 of the task compares it with the file). The decision column is empty: it is filled by the clinician, not by an agent. `reviewed_by` is null for every entry. The derived latency names are not reviewed rows: their value follows from `step_ms`, `sched_window` and `delta2`.

The questions ask the clinician to decide; none of them contains a proposed value, a drug or a guideline. The decision values are those of WS00-T07: `approved`, `changed`, `rejected`, `not assessable`.

| Name | Unit | Current value | Origin | Question to the clinician | Decision |
|---|---|---|---|---|---|
| `bp_band_low` | `mmHg` | `110` | analisi §4.1, illustrative, unverified | Confirm, change or reject. Name the guideline and the drug class it is anchored to, or write `not anchored`. See Q1. | |
| `bp_band_high` | `mmHg` | `140` | analisi §4.1, illustrative, unverified | Confirm, change or reject. Name the guideline and the drug class it is anchored to, or write `not anchored`. See Q1. | |
| `bp_hold_threshold` | `mmHg` | `100` | analisi §4.1, illustrative, unverified | Confirm, change or reject. Name the guideline and the drug class it is anchored to, or write `not anchored`. See Q2. | |
| `hold_lookback` | `ms` | `3600000` | analisi §4.1, illustrative, unverified | Confirm, change or reject as the institution's policy. See Q2. | |
| `dose_max_24h` | `dose` | `2` | analisi §4.1, illustrative, unverified | Confirm, change or reject as the institution's policy. See Q4 for the related count obligation. | |
| `dose_min_day_end` | `dose` | `2` | analisi §4.1, illustrative, unverified | Confirm, change or reject as the institution's policy. See Q4. | |
| `int_window` | `ms` | `300000` | analisi §4.1, illustrative, unverified | Confirm, change or reject as the institution's policy. | |
| `delta1` | `ms` | `3600000` | analisi §4.6, illustrative, unverified | Confirm, change or reject. Name the drug class and the source of the timing, or write `not anchored`. | |
| `delta2` | `ms` | `10800000` | analisi §4.6, illustrative, unverified | Confirm, change or reject. Name the drug class and the source of the timing, or write `not anchored`. | |
| `bound_bp_lower` | `mmHg` | `50` | analisi §4.7 (step 2), illustrative, unverified | Confirm, change or reject as a plausibility bound of the signal. | |
| `bound_bp_upper` | `mmHg` | `250` | analisi §4.7 (step 2), illustrative, unverified | Confirm, change or reject as a plausibility bound of the signal. | |
| `scale_range` | `mmHg` | `20` | analisi §4.2, illustrative, unverified | Confirm, change or reject. See Q5. | |
| `scale_sched` | `ms` | `1800000` | analisi §4.2, illustrative, unverified | Confirm, change or reject. See Q5. | |
| `scale_count` | `dose` | `1` | analisi §4.2, illustrative, unverified | Confirm, change or reject. See Q5. | |
| `priority_hold` | `1` | `1` | analisi §4.2, illustrative, unverified | Confirm, change or reject. See Q5. | |
| `priority_range` | `1` | `2` | analisi §4.2, illustrative, unverified | Confirm, change or reject. See Q5. | |
| `priority_sched` | `1` | `3` | analisi §4.2, illustrative, unverified | Confirm, change or reject. See Q5. | |
| `sched_window` | `ms` | `unset` | no value yet | Supply a value and its anchor, or write `not assessable`. A window parameter: an integer multiple of the monitor step. | |
| `delta_resp` | `mmHg` | `unset` | no value yet | Supply a value and its anchor, or write `not assessable`. The minimum pressure fall for the response template. | |
| `cuff_inflation_min` | `ms` | `unset` | no value yet | Supply a value with the device specification or validation protocol, or write `not assessable`; a human verifies the source. | |
| `scale_hold` | `mmHg` | `unset` | no value yet | Supply a value, or write `not assessable`. See Q5. | |
| `scale_resp` | `mmHg` | `unset` | no value yet | Supply a value, or write `not assessable`. See Q5. | |
| `scale_sys` | `ms` | `unset` | no value yet | Supply a value, or write `not assessable`. See Q5. | |
| `scale_int` | `ms` | `unset` | no value yet | Supply a value, or write `not assessable`. See Q5. | |
| `priority_count` | `1` | `unset` | no value yet | Supply a value, or write `not assessable`. See Q5. | |
| `priority_resp` | `1` | `unset` | no value yet | Supply a value, or write `not assessable`. See Q5. | |
| `priority_sys` | `1` | `unset` | no value yet | Supply a value, or write `not assessable`. See Q5. | |
| `priority_int` | `1` | `unset` | no value yet | Supply a value, or write `not assessable`. See Q5. | |
| `bound_inflation_ms_lower` | `ms` | `unset` | no value yet | Supply a value with the device specification or validation protocol, or write `not assessable`; a human verifies the source. | |
| `bound_inflation_ms_upper` | `ms` | `unset` | no value yet | Supply a value with the device specification or validation protocol, or write `not assessable`; a human verifies the source. | |
| `bound_dose_count_lower` | `dose` | `unset` | no value yet | Supply a value and its anchor, or write `not assessable`. | |
| `bound_dose_count_upper` | `dose` | `unset` | no value yet | Supply a value and its anchor, or write `not assessable`. | |
| `cuff_error_sd` | `mmHg` | `unset` | no value yet | Supply a value with the device specification or validation protocol, or write `not assessable`; a human verifies the source. | |
| `clock_skew_max_ms` | `ms` | `unset` | no value yet | Not a clinical decision: to be set from the measured device clocks by the system owner. | |

**Open clinical questions raised by WS01-T01 and WS01-T02.**

* **Q1 (RANGE during drug onset; analisi §4.6 row 08:55; `02-templates.md` section 4.1, TG-13).** The range constraint applies at every measurement in the template library, including measurements inside the onset window of the drug. Does the range constraint apply during the onset window of the drug, and if not, how is a measurement inside that window to be treated?
* **Q2 (hold semantics; `02-templates.md` section 4.3, TG-7).** The template library adopts the refined form of the hold constraint: the decision at the dispense rests on the latest measurement before the dispense, and a measurement must exist in the look-back window. The workshop form accepts the dispense if any measurement in the look-back window is at or above the threshold. Which is clinically intended: the latest measurement or any measurement in the look-back window?
* **Q3 (patient-level overrides; section 5).** Are per-patient values wanted, for which names, and within which approved ranges? If none is wanted, version 0.1.0 stands.
* **Q4 (measurement-count obligation; `02-templates.md` section 4.4, CP2).** Is a day-end obligation on the number of measurements (analisi §4.6 mentions five a day) clinically wanted? It is not registered because no template uses it. A yes needs a new template and a new entry.
* **Q5 (scales and priorities; analisi §4.2).** For each template, what deviation is clinically significant (the scale, in the unit of the template), and what is the priority order among the seven templates? The order hold > range > sched of analisi §4.2 is an example: the order used by the paper is the clinician's own.

## 7 Open points for WS01-T08

Each item gives the anchor, the resolution adopted or proposed, and whether an ADR is needed. None edits `docs/plan/02-interfaces.md`.

**OP-1 (`#parameter-registry`, CP10: types).** `RegistryEntry.value` is `float` for every unit; durations are `DurationMs` (int) and priorities are `int`; `PhysioBounds` has no `rationale` and no `reviewed_by` although ADR-020 requires both for every value. Resolution adopted: values are stored as floats, cast by unit and name with an integrality check (section 2.6); `PhysioBounds` is composed from two entries that carry the provenance (section 2.5, rule 5); unit strings are `mmHg`, `ms`, `dose`, `1`. No signature changes. ADR: a clarification of the contract text (one sentence on casts and on bounds provenance), at the discretion of WS01-T08.

**OP-2 (`#parameter-registry`, unset names and errors).** The contract has no representation of "declared but has no value": `get` returns a `RegistryEntry`. Resolution adopted: `UnsetParameterError` (a subclass of `RegistryError`) is raised; the registry object also has `is_declared`, `is_set` and an unverified-names list, which are not in the `ParameterRegistry` protocol. Neither exception name is in the `ralmon.spec` row of the `Package public API` contract; WS05-T03 already expects `RegistryError`. ADR: yes for the public API additions (the protocol itself is unchanged).

**OP-3 (`#template`, `max_verdict_latency_param` is "a registry entry").** Adopted: it is a name in `derived:`, computed by the loader as `B + step_ms` (section 2.5, rule 6); this is TG-3 of `02-templates.md`. Which latency the monitor reports, event-time or end-to-end, remains CG-4 and WS01-T05.

**OP-4 (`#parameter-registry`, `load_registry` has no signature in the contract).** The contract lists the name `load_registry` in the package public API but gives no signature. This document assumes `load_registry(path=None, *, step_ms=None)` as planned by WS05-T03, with `step_ms` from `MonitorConfig`. ADR: with OP-2.

**OP-5 (`window_parameters`, T01 CG-1).** T01 proposed a role attribute on registry time entries. An entry cannot carry an extra field, so the roles that the alignment check needs are given by the extra top-level list `window_parameters` (section 2.4). It is a deviation from the list of top-level keys of the task text (which names `registry_version`, `pathology`, `review_status`, `entries`, `derived`, `unset` and `overrides`), justified by T01 CG-1 and by WS05-T03 test 15 ("the entries the WS01-T03 schema marks as windows"). It does not change the contract classes. The other roles (threshold, scale, limit, configuration) are implied by the name prefix and the inventory of section 3.

**OP-6 (`#template`, `TemplateInstance.param_values`).** The contract does not say whether `param_values` holds all the parameters of the instance or only the deviations from the registry, or what the monitor does when a key differs from the registry value. Adopted here: a key that differs from the registry must be in `overrides:` and inside its range (section 5.3). WS05-T03 and WS01-T08 to confirm and to state where the check lives.

**OP-7 (`cuff_error_sd` and `clock_skew_max_ms`).** Two names do not belong to a template. `cuff_error_sd` is needed by the Gaussian error model of rho (WS01-T06) and has a counterpart `DeviceErrorModel.cuff_error_sd_mmhg` in `PriorSource` (contract `#priorsource`); the monitor and the benchmark generator must not use two different numbers silently. Proposed: WS01-T06 states which of the two is the source of truth for the monitor's rho and how the generator's value is related to it. `clock_skew_max_ms` is registered as unset because `docs/formal/01-signals-sampling.md` section 4.4 asks WS01-T03 to register it, although `02-templates.md` section 3.4 lists monitor configuration names as "not clinical registry entries" and `MonitorConfig` has no skew field; T08 to decide whether it lives in the registry or in `MonitorConfig` (ADR if `MonitorConfig` changes).

**OP-8 (bounds beyond `bp`).** `bound_inflation_ms_lower/upper` and `bound_dose_count_lower/upper` are declared unset for the two other signals that carry a margin (`inflation_ms`, `dose_count`). WS01-T05 (CP12) decides whether the interval semantics needs them and how it completes a derived counter; if not, they are removed with a major version bump before the freeze. The signals `hr_ecg`, `hr_pulse` and `spo2` are used by no template and have no bound entry.

**OP-9 (version compatibility).** Plans pin the exact version string; no compatibility range is defined and any bump invalidates issued plans (section 5.2). WS05-T03 and WS01-T08 decide whether a patch bump (text only) should keep plans valid.

**OP-10 (`meas_min_day`, CP2).** Not registered (section 3.3). If CP2 is resolved by adopting the measurement-count obligation, the entry is added by a minor bump after the ADR.

**OP-11 (scales and priorities of four templates, and experiments before review).** `scale_hold`, `scale_resp`, `scale_sys`, `scale_int`, `priority_count`, `priority_resp`, `priority_sys`, `priority_int` have no seed value in the registry, because only F0 (FIXTURE-ONLY) gives numbers for them. Consequences for consumers: `rank_alerts` and `normalise` on the real registry raise `UnsetParameterError` for those templates; `load_templates` succeeds; WS06-T01 (test 21: names of `stub_registry` are entry names of the file) must draw its names from the entries only; WS09-T04 (Table I) shows an unset scale or priority as unset. Benchmark runs before WS00-T07 need a registry with FIXTURE-ONLY values; where it lives (a test fixture, never `hypertension.yaml`), who creates it and how results obtained with it are labelled as unverified is a decision for WS05-T03 and WS08-T01. ADR: proposed.

**OP-12 (state of the names that WS01-T04, T05 and T06 still need).** WS01-T04 (normalisation and ranking) reads `scale_<id>` and `priority_<id>`; it confirms the direction "1 = highest" (CP5) and how a failed guard is normalised. WS01-T05 (three-valued semantics) reads the bounds and the derived latencies and decides OP-8. WS01-T06 (rho) reads `cuff_error_sd` (OP-7). Their documents did not exist when this one was written; any additional name they need is added as an unset name or an entry by a minor version bump, and is added to the inventory of section 3.

**OP-13 (`review_status` granularity).** The three values (`unreviewed`, `partially_reviewed`, `reviewed`) are derived from the entries (section 2.5, rule 9); `reviewed` also requires an empty `unset`. If the freeze allows a registry with some unset names to be called reviewed, the rule is relaxed by T08.

**OP-14 (registry file integrity).** The registry file is not signed; the care plan is. The digest proposal of section 5.2 is the only integrity link. Whether the registry itself needs a signature is a governance question for WS02 and WS13.

**OP-15 (no paper excerpt).** The task headings of this document do not include a paper-excerpt section. The registry appears in the paper only through the scale and priority columns of Table I (`02-templates.md` section 8, whose caption says that the values are illustrative and unverified) and through the limitations sentence of section 4.2, step 11.
