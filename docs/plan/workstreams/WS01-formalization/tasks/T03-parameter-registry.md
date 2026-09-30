---
id: WS01-T03
title: Parameter registry design, YAML schema and anchoring procedure
workstream: WS01-formalization
owner: agent
status: done
depends_on: ["WS01-T02"]
critical_path: true
non_negotiable: true
estimate_pd: 2
sources: ["analisi §4.1", "analisi §4.2", "analisi §2 R3 (weakness 3)", "analisi §4.7", "analisi §4.9 (7)"]
interfaces: ["02-interfaces.md#parameter-registry"]
review_items: ["R3-W3"]
---
## Obiettivo

Write `docs/formal/03-parameter-registry.md`, the versioned registry file `configs/registry/hypertension.yaml` and its schema `configs/registry/registry.schema.json`. The registry is the single source of every clinical parameter of the templates (bands, hold threshold, delta1, delta2, delta, window, dose limits, physiological bounds, per-template scale and priority) and the document defines the anchoring procedure that ties each value to a drug and guideline. This task is non-negotiable (analisi §9). It designs the registry and seeds it with the illustrative values that the analisi itself gives; it does not decide any clinical value and does not assign a drug or guideline (ADR-020). The registry is filled and clinician-reviewed by WS00-T07.

## Contesto

Unblocks when WS01-T02 is `done`. Read first:

1. `docs/formal/02-templates.md` (section 3: the final registry working names, units, `scale_param`, `priority_param`, derived latency names).
2. `docs/plan/02-interfaces.md#parameter-registry` (`RegistryEntry`, `PhysioBounds`, `ParameterRegistry`, the rule "no numeric clinical constant outside the registry loader").
3. `docs/source/analisi.md` §4.1 (illustrative values), §4.2 (scale examples 20 mmHg, 30 min, 1 dose; priority order hold > range > sched), §4.7 (physiological bounds example), §2 R3 weakness 3, §4.9 item 7 (versioning and signature).
4. `docs/plan/03-decisions.md` ADR-009 and ADR-020.
5. `docs/plan/workstreams/WS01-formalization/README.md` (fixture registry F0: which rows are analisi-derived and which are FIXTURE-ONLY; CP10).

## File toccati

- `docs/formal/03-parameter-registry.md` (create)
- `configs/registry/hypertension.yaml` (create)
- `configs/registry/registry.schema.json` (create)

## Test

Document and configuration task: verification checks.

1. **Headings.** `## 1 Purpose and rules`, `## 2 YAML schema`, `## 3 Entry inventory`, `## 4 Anchoring procedure`, `## 5 Versioning and per-patient overrides`, `## 6 Review sheet for WS00-T07`, `## 7 Open points for WS01-T08`.
2. **Entry format.** In `hypertension.yaml` every element of `entries:` is written as `  - name: <name>` followed, at four-space indent and in this order, by `value`, `unit`, `rationale`, `source_ref`, `reviewed_by` (exactly the fields of `RegistryEntry`). The counts of `- name:` lines and of each of the five keys are equal.
3. **Nothing reviewed.** Every `reviewed_by` is `null`; every `rationale` is the exact string `illustrative, unverified` or names an analisi derivation that ends with that string; every `source_ref` names an analisi section (for example `analisi §4.1`).
4. **Only sourced values.** `entries:` contains only names whose value appears in analisi §4.1, §4.2, §4.6 or §4.7 (the analisi-derived rows of the F0 table: `bp_band_low`, `bp_band_high`, `bp_hold_threshold`, `hold_lookback`, `dose_max_24h`, `dose_min_day_end`, `int_window`, `delta1`, `delta2`, `bound_bp_lower`, `bound_bp_upper`, `scale_range`, `scale_sched`, `scale_count`, `priority_hold`, `priority_range`, `priority_sched`, and `meas_min_day` if T02 adopted a measurement-count obligation). No FIXTURE-ONLY name of F0 is an entry.
5. **Unset list.** Every other parameter required by the templates of T02 (at least `sched_window`, `delta_resp`, `cuff_inflation_min`, `scale_hold`, `scale_resp`, `scale_sys`, `scale_int`, `priority_count`, `priority_resp`, `priority_sys`, `priority_int`, `cuff_error_sd`, and the bounds of every signal whose future values are completed by bounds) appears in the top-level `unset:` list written as `  - parameter: <name>` with `unit`, `required_by` (template ids) and `note` ("value to be set and reviewed by WS00-T07"). The loader specified in the document raises a specific error when a template needs an unset name.
6. **Derived entries.** Latency bounds (`max_latency_<id>`) are in a `derived:` list with a formula over registry names and `step_ms`; they are not free parameters.
7. **Physiological bounds.** Bounds are stored as entries `bound_<signal>_lower` and `bound_<signal>_upper` so that ADR-020 applies to them; the document states that `ParameterRegistry.bounds(signal)` composes the pair into a `PhysioBounds` (CP10).
8. **Types (CP10).** The document states the casts: durations are stored in ms as integral floats and cast to `DurationMs` with an integrality check; priorities are stored as integral floats and cast to `int` (1 is the highest priority, consistent with T04); unit strings are one of `mmHg`, `ms`, `dose`, `1` (dimensionless counts and ranks).
9. **Schema.** `registry.schema.json` is valid JSON and describes: `registry_version` (semantic version string), `pathology`, `review_status`, `entries`, `derived`, `unset`, optional `overrides`; the `name` pattern `^[a-z][a-z0-9_]*$`; `unit` enumeration; `reviewed_by` string or null; `additionalProperties: false` on entries.
10. **Anchoring procedure.** Section 4 is a numbered procedure that a clinician and an agent can follow, with these rules: no agent assigns a drug or guideline from memory (ADR-020); the drug class and guideline are chosen by the clinician recruited in WS00-T03; each parameter is classified by anchor type (guideline target: bands and hold threshold; pharmacology: delta1, delta2, delta_resp; local care policy: schedule window, dose counts, scales, priorities; device validation protocol: `cuff_error_sd`, whose source is verified by a human; physiological plausibility: bounds); the anchor is written into `rationale` and `source_ref`; `reviewed_by` receives the clinician identifier only after review; unreviewed values are reported as unverified in the manifest and the paper limitations; any reference is marked `[ref-needed: WS03]` until verified (ADR-018).
11. **Versioning and overrides (analisi §4.9 item 7).** Section 5 defines the version rule (patch for text, minor for a value change, major for a name or unit change), that a `CarePlan` pins `registry_version`, and the per-patient calibration policy: patient values travel in `TemplateInstance.param_values` inside the signed care plan, must lie inside clinician-approved ranges kept in an `overrides:` section (name, min, max, rationale, source_ref, reviewed_by), and the robot evaluates but cannot author or modify them. If no override is supported in v0.1.0 the section says so and the `overrides:` list is empty.
12. **Review sheet.** Section 6 is a table generated by hand from the YAML for the clinician: name, unit, current value or "unset", origin, question to the clinician, empty decision cell. It includes the open clinical questions raised by T01 to T02 (does the range constraint apply during the onset window of the drug, analisi §4.6 row 08:55; hold semantics: latest measurement or any measurement in the look-back window; whether patient-level overrides are wanted).
13. **Terminology.** The document uses "pathway template" for the institutional level and "patient care plan" for the instance (R3 weakness 3) and states that a drug-specific anchor is required before the paper may call any parameter clinically grounded.

## Passi

1. Write `registry.schema.json` from checks 2, 5 to 9; validate it with `python3 -c "import json; json.load(open('configs/registry/registry.schema.json'))"`.
2. Draft `hypertension.yaml`: header (`registry_version: "0.1.0"`, `pathology: hypertension`, `review_status: unreviewed`), then `entries:` from the analisi-derived list of check 4 in the exact layout of check 2, then `derived:`, `unset:` (names from T02 section 3 not covered by an entry), `overrides: []`.
3. Run the count and grep checks of "Done when"; fix layout until they pass.
4. Write section 1 (purpose, the rule "no numeric clinical constant in `src/ralmon` outside the loader", relation to `PriorSource`: the registry holds template parameters, `PriorSource` holds generator parameters, and they meet only through the reviewed onset window that informs delta1 and delta2, analisi §5.1).
5. Write section 2 (schema description and loader behaviour: strict load, unset error, derived computation, bounds composition, casts) and section 3 (inventory table: template, parameter, unit, entry or unset or derived, origin).
6. Write section 4 (anchoring procedure), section 5 (versioning and overrides), section 6 (review sheet), section 7 (open points, including CP10 and the state of any name that T05 or T06 still needs).
7. Set `status` to `done` and commit `WS01-T03: add parameter registry design and seed file`.

## Done when

```bash
cd "/home/gab/Desktop/RAL experiment"
f=configs/registry/hypertension.yaml; d=docs/formal/03-parameter-registry.md
test -f "$f" && test -f "$d" && test -f configs/registry/registry.schema.json
python3 -c "import json; json.load(open('configs/registry/registry.schema.json'))"   # exit 0
n=$(grep -c '^  - name:' "$f"); echo "entries: $n"
for k in value unit rationale source_ref reviewed_by; do
  c=$(grep -c "^    $k:" "$f"); [ "$n" = "$c" ] || echo "count mismatch for $k: $c"; done   # prints nothing
[ "$(grep -c '^    reviewed_by: null' "$f")" = "$n" ]
! grep -E '^  - name: (sched_window|delta_resp|cuff_inflation_min|scale_hold|scale_resp|scale_sys|scale_int|priority_count|priority_resp|priority_sys|priority_int|cuff_error_sd)$' "$f"
grep -q '^unset:' "$f" && grep -q '^derived:' "$f" && grep -q '^registry_version:' "$f"
for h in "## 1 Purpose and rules" "## 2 YAML schema" "## 3 Entry inventory" "## 4 Anchoring procedure" \
         "## 5 Versioning and per-patient overrides" "## 6 Review sheet for WS00-T07" \
         "## 7 Open points for WS01-T08"; do grep -qF "$h" "$d" || echo "missing heading: $h"; done   # prints nothing
! grep -nE 'T[O]DO|T[B]D|[?][?][?]|lore[m]' "$f" "$d" configs/registry/registry.schema.json   # exit 0
```

All commands succeed or print nothing. The `entries:` count printed by `echo` equals the number of analisi-derived names of check 4.

## Notes

Status left `in_progress` on purpose (the orchestrator sets `done` after review). Work is on branch `ws01-t03-parameter-registry`; nothing is merged.

### Verification record (real outputs)

Checks 1 to 13 of "Test", plus two consistency checks (14: every registry name used by a template string of `02-templates.md` section 3.1 is an entry, unset or derived name, units of `scale_<id>` agree with the template unit, no YAML name is unused; 15: header and placeholder scan), were written as scripts in `/tmp/t03/` (not committed). Run against the empty state (no files) all 15 failed with "missing file". After the artefacts were written:

```
check  1 headings                 PASS  7 headings present
check  2 entry format             PASS  17 entries, layout ok
check  3 nothing reviewed         PASS  reviewed_by null, rationale and source_ref ok
check  4 only sourced values      PASS  17 names equal the analisi-derived list; values equal F0
check  5 unset list               PASS  17 unset items
check  6 derived                  PASS  7 derived latencies, formulas equal 02-templates section 3.2
check  7 physio bounds            PASS  bounds stored as entries; composition stated
check  8 types CP10               PASS  casts stated
check  9 schema                   PASS  valid: metaschema ok, document valid, 15 negative mutations rejected, 2 positive variants accepted
check 10 anchoring                PASS  12 numbered steps; keywords present
check 11 versioning               PASS  versioning and overrides stated; overrides empty
check 12 review sheet             PASS  34 rows = entries + unset; decision cells empty
check 13 terminology              PASS  terminology and wording ok
check 14 template consistency     PASS  33 template names all declared; scale/priority units consistent; no unused yaml name
check 15 header / placeholders    PASS  header ok
```

"Done when" block, run verbatim (each line's exit code): file existence 0; `json.load` of the schema 0; `entries: 17`; the five key-count loop printed nothing; `reviewed_by: null` count equals 17: 0; no unset name as entry: 0; `unset:`, `derived:`, `registry_version:` present: 0; heading loop printed nothing; placeholder scan: 0. `pytest -q`: 175 passed, exit 0. `python3 tools/check_plan.py`: `check_plan: OK (103 tasks, 18 contracts, 31 findings)`, exit 0.

Schema validation: `jsonschema` is not in the repo `.venv`; the system `/usr/bin/python3` already has `jsonschema` 4.19.2 (nothing was installed). The YAML was converted to JSON by the venv PyYAML and validated by the system python in `/tmp/t03/t03_validate.py` (metaschema check, document valid, 15 negative mutations rejected, 2 positive variants accepted).

### Deviations from the task text

1. Extra top-level key `window_parameters` (list of names to which the alignment rule applies) in the YAML and schema. Reason: T01 CG-1 asks for a mechanical window role and WS05-T03 test 15 expects the schema to mark windows; an entry cannot carry a role field without leaving the `RegistryEntry` fields. Recorded as OP-5.
2. `derived:` and `unset:` elements are one-line flow mappings (`  - {parameter: x, unit: ..., ...}`), not block mappings. Reason: a block element would put `    unit:` at four-space indent and break the "Done when" per-key counts (which must equal the entry count). The key `parameter` is still greppable.
3. Unset list has 17 names: the 12 named in check 5, plus bounds `bound_inflation_ms_lower/upper` and `bound_dose_count_lower/upper` (check 5: "bounds of every signal whose future values are completed by bounds"; whether they are needed is WS01-T05's, OP-8) and `clock_skew_max_ms` (T01 section 4.4 asks T03 to register it; OP-7). Names only, no values.
4. Schema adds an if/then rule: `reviewed_by` null implies `rationale` ends with `illustrative, unverified` (mechanical ADR-020).
5. No paper-excerpt section (the task heading list has none), OP-15.

### Contract gaps recorded for WS01-T08 (section 7 of the document; no contract edited)

CP10 (float value for int quantities; `PhysioBounds` without provenance), unset names and error classes not in the API, `load_registry` signature, `param_values` semantics, `max_verdict_latency_param` as derived name, `cuff_error_sd` versus `DeviceErrorModel.cuff_error_sd_mmhg`, `clock_skew_max_ms` versus `MonitorConfig`, version compatibility, review_status granularity, experiments before WS00-T07 need a fixture registry outside `hypertension.yaml` (OP-11).

### Not done, by design

No clinician review (WS00-T07 not performed; `reviewed_by` null everywhere, decision cells of section 6 empty). No drug, guideline or clinical value assigned. WS00 artefacts not created.

### Post-task review

- Produced: `docs/formal/03-parameter-registry.md` (seven sections: purpose and rules, YAML schema and loader proposal, entry inventory of 41 names, anchoring procedure in 12 numbered steps, versioning and per-patient overrides, review sheet of 34 rows with empty decision cells, open points OP-1 to OP-11), `configs/registry/hypertension.yaml` (17 seeded entries, all `reviewed_by: null`, each rationale ending "illustrative, unverified"; 7 derived latencies; 17 names `unset`) and `configs/registry/registry.schema.json`. Orchestrator re-ran the "Done when" block (exit 0, 17 entries), validated the YAML against the schema with the system Python's `jsonschema` (nothing installed), and ran the full suite (175 tests) and `check_plan` (exit 0). Independent review: PASS, no BLOCKER. All 17 values traced to analisi (110, 140, 100, the 60 min and 5 min windows, `c_d` limits of 2, [50, 250] mmHg, "20 mmHg, 30 min, 1 dose", the order hold > range > sched) or to fixture F0 with the assignment disclosed; no fixture-only value leaked into the registry; no drug or guideline named; 29 schema mutations rejected.
- Deviations from the task text: extra required top-level key `window_parameters` (T01 CG-1; OP-5, to be ratified by WS01-T08); `unset` and `derived` items written as one-line flow mappings so that the Done-when per-key counts hold; four extra unset bound names and `clock_skew_max_ms` (OP-7, OP-8); a schema rule tying a null `reviewed_by` to the rationale ending "illustrative, unverified"; no paper-excerpt section (the task's heading list has none). All disclosed.
- Dependents: WS01-T04 to WS01-T07, WS05-T03 and the WS04-T02 chain read this registry. Four tasks have assumptions that no longer hold and were flagged (notes in their task files, proposed ADR-027 `[DA-CONFERMARE]`, kept `blocked`): WS01-T08 (its cross-document grep now prints three names), WS00-T07 (34 review-sheet rows versus 17 expected; no notion of `unset`), WS06-T02 (`sched_window` unset, step 2 would stop) and WS06-T01 (test 21 stub registry). The plan has a real gap: no task creates a fixture registry for runs before the clinician review (OP-11).
- Open MINOR: (1) the headers of the YAML (lines 3 to 5) and of the document (line 5) say every value is "taken from the analysis document", but the scale and priority assignments come from F0 (disclosed elsewhere); the `priority_*` rationales do not name F0 as the source of "1 = highest"; (2) `delta1` and `delta2` cite only analisi §4.6; analisi line 113 ("risposta in 1-3 h") supports the same numbers; (3) section 2.5 (loader) and section 5.2 (exact-string plan pinning) are worker proposals, not labelled "design proposal"; (4) the schema does not enforce `value >= 0`, `priority >= 1`, `scale > 0`, unique names, window alignment or `review_status` consistency (loader rules for WS05-T03); (5) the four `bound_inflation_ms_*` and `bound_dose_count_*` names are speculative pending WS01-T05, and `clock_skew_max_ms` conflicts with WS01-T02 section 3.4 ("monitor configuration, not a clinical registry entry"); (6) WS04 README lists `delta_resp`, `sched_window`, `cuff_inflation_min` and `cuff_error_sd` as working names to read, all four unset; (7) WS05-T03 tests 10 to 18 match the YAML, but its F0 copy needs a rationale ending "illustrative, unverified" and cannot store `step_ms`.
- Risks: nothing in the registry is clinically reviewed (`reviewed_by` null everywhere); the numbers are illustrative and unverified (ADR-020). The registry stays a design until WS00-T07, which does not exist yet as an artefact.
