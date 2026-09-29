---
id: WS09-T04
title: Table I template library
workstream: WS09-figures
owner: agent
status: blocked
depends_on: ["WS01-T08", "WS09-T01", "WS05-T03"]
critical_path: false
non_negotiable: false
estimate_pd: 1
sources: ["analisi §7"]
interfaces: ["02-interfaces.md#template"]
review_items: []
---
## Obiettivo

Generate Table I of the paper (section IV-A): one row per pathway template of the library with its past-time STL formula, the unit of its raw robustness, its scale s_π and its clinician-assigned priority, as a LaTeX table `paper/tables/table1_templates.tex`. Every cell comes from the template library and the parameter registry delivered by WS01 (the only sources of clinical values, `01-conventions.md` section 8); nothing is typed by hand, and any value that has no clinician review is marked as unverified (ADR-020).

## Contesto

- `docs/source/analisi.md` §7 (Table I: template, formula, unit, scale s_π, priority), §4.1 (illustrative templates φ_range, φ_sched, φ_hold, φ_count, φ_resp, φ_SYS, φ_INT and their decomposition) and §4.2 (normalisation scales and priorities; the examples 20 mmHg, 30 min, 1 dose are illustrative).
- `docs/plan/02-interfaces.md#template`: `Template` (fields `formula_past_time`, `unit`, `scale_param`, `priority_param`, `kind`) and the rule that only normalised values are compared. The registry side is `#parameter-registry` (`RegistryEntry.reviewed_by`, `rationale`).
- `docs/plan/workstreams/WS01-formalization/tasks/T02-template-library.md`: the grammar and syntax of `formula_past_time` and the template list. (WS01-T03 gives the registry YAML schema and WS01-T04 the priority ordering rule; read them in step 1.)
- `docs/plan/03-decisions.md` ADR-020 (values without review are reported as unverified) and ADR-007 (past-time formulation).
- `docs/plan/workstreams/WS09-figures/README.md`: shared conventions.

Unblocked when WS01-T08 is done (library, registry and normalisation frozen). Undeclared preconditions: WS09-T01 is done (scaffold, formatter, provenance) and WS05-T03 is done (`ralmon.spec.load_templates` and `load_registry` exist). First step of this task: run `python -c "from ralmon.spec import load_templates, load_registry"`; if it fails, or `tools.figures` does not exist, stop and report which precondition is missing; do not write a second YAML reader.

## File toccati

- `tools/figures/latex_stl.py` (create): converts the ASCII past-time STL syntax fixed by WS01-T02 into LaTeX (token map, parameter names mapped to symbols).
- `tools/figures/targets/table1_templates.py` (create): the `table1` target.
- `tests/figures/test_table1_templates.py` (create): tests below.
- `tests/figures/fixtures/table1/` (create): a small hand-written registry and template library in the formats of WS01-T02 and WS01-T03.
- `paper/tables/table1_templates.tex` (create, generated), with its sidecar `table1_templates.data.json` and `table1_macros.tex` in the same directory.

## Test

Fixture facts (fixtures only, not results): a registry with entries whose `rationale` is "illustrative, unverified", including a scale of 20 (unit `mmHg`) for `range`, a scale of 1 800 000 (unit `ms`) for `sched`, a scale of 1 (unit `dose`) for `count`; one entry with `reviewed_by` set, all others `None`; priority values 2, 3, 1 on three templates (the order these induce is written by hand in the fixture, following the direction fixed by WS01-T04). The ASCII strings are copied from the library syntax of WS01-T02 for the analisi §4.1 templates. Unit of the scale of `sched` in the table is minutes: 1 800 000 ms / 60 000 = 30.

1. `test_render_formula_range`: the ASCII form of φ_range renders to the hand-written expected string of the fixture, whose structure follows analisi §4.1: `\square\,(m \rightarrow (bp \ge p_{1} \wedge bp \le p_{2}))`, where `p_1` and `p_2` are the symbols the fixture's parameter-name map assigns to the two band limits.
2. `test_render_formula_sched_uses_once_and_window`: φ_sched renders with `\mathrm{O}_{[W,W+T_s]}` for the point-event window (ADR-007 and `02-interfaces.md` Time and units rule 2) and `\mathrm{O}_{[0,W]}` for the measurement obligation.
3. `test_render_formula_unknown_token_raises`: a token outside the WS01-T02 grammar raises `UnsupportedFormulaError` naming the token; raw ASCII is never printed into the table.
4. `test_table1_one_row_per_template_in_library`: the number of data rows equals `len(load_templates())` of the fixture (7 in the fixture: range, sched, hold, count, resp, sys, int).
5. `test_table1_columns`: header cells are exactly Template, Formula, Unit, Scale $s_\pi$, Priority.
6. `test_table1_scale_and_priority_from_registry`: the `range` row shows scale `20 mmHg`, the `sched` row shows `30 min` (converted from 1 800 000 ms), the `count` row shows `1 dose`; the priority cell equals the registry value of `priority_param`.
7. `test_table1_unreviewed_values_marked`: a value whose `reviewed_by` is `None` carries a dagger and the generated note reads "illustrative, unverified"; the one reviewed value has no dagger.
8. `test_table1_row_order_follows_priority_rule`: within a kind, rows are ordered by the same rule as `rank_alerts` (priority first, direction as fixed by WS01-T04); the fixture with priority values 2, 3, 1 yields the hand-written expected order; ties keep library order (stable sort).
9. `test_table1_kind_grouping`: the phi_CP templates come first, then phi_SYS, then phi_INT, with the kind shown in the Template column (decomposition φ = φ_CP ∧ φ_SYS ∧ φ_INT).
10. `test_table1_missing_registry_entry_raises`: a template whose `scale_param` is not in the registry raises an error naming the template and parameter.
11. `test_table1_latex_specials_escaped`: an entry name containing an underscore is escaped or set in math mode.
12. `test_table1_no_literal_outside_registry`: every numeric token in the generated `.tex` appears in the sidecar's list of registry-derived cells (no other number is present).
13. `test_table1_macros`: `table1_macros.tex` defines `\NTemplates` equal to the number of rows (7 in the fixture) and `\NCarePlanTemplates` equal to the number of phi_CP rows.
14. `test_table1_check_detects_registry_change`: changing a registry value makes `python -m tools.figures table1 --check` fail until regenerated.

## Passi

1. Verify the preconditions above. Read WS01-T02 to copy the exact ASCII grammar (operators, interval syntax, how parameters and signals are named) and WS01-T03 and WS01-T04 for the registry fields and the direction of the priority order.
2. Write the fixture library and registry, the expected LaTeX strings by hand, and the tests. Run `pytest tests/figures/test_table1_templates.py -q` and watch them fail. Commit `WS09-T04: add failing Table I tests`.
3. Implement `latex_stl.py` as a table-driven renderer: operators follow the notation of analisi §4.1 (`\square` for always-historically, `\mathrm{O}` for once, `\rightarrow`, `\wedge`, `\vee`, `\ge`, `\le`); signals and parameters map to symbols through a dictionary derived from `Template.signals` and `Template.params`; a name without a mapping is set as `\mathit{name}` with escaped underscores. Formula values are never substituted: the formula column shows symbols, and only scale and priority show registry values.
4. Implement the target: load with `ralmon.spec`, build rows, convert `ms` scales to minutes with `MS_PER_MINUTE` from `ralmon.signals`, mark unreviewed values, order rows, write `paper/tables/table1_templates.tex` with `booktabs` rules through `write_generated`. The formula column is a `p{}` column whose width comes from the `--width` option (single or double column), not a `\resizebox` (which would shrink the fonts).
5. Emit the sidecar (each cell with its registry entry name, `rationale`, `reviewed_by`, and the hashes of the registry and template files) and `table1_macros.tex`.
6. Compile the generated table inside a minimal standalone document if a LaTeX toolchain is present (`latexmk` or `pdflatex` with `booktabs`) and check that it fits the column; otherwise record in the commit message that compilation was not possible and leave it to WS12-T08.
7. Run `ruff format`, `ruff check` and the tests until green. Commit `WS09-T04: add Table I template library` and set `status` to `done`.

## Done when

- `pytest tests/figures/test_table1_templates.py -q` exits 0 and `ruff check tools/figures tests/figures` exits 0.
- `python -m tools.figures table1` exits 0 and `test -f paper/tables/table1_templates.tex && test -f paper/tables/table1_macros.tex`.
- `head -1 paper/tables/table1_templates.tex` starts with `% GENERATED by tools/figures`.
- `python -m tools.figures table1 --check` exits 0.
