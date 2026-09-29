---
id: WS09-T01
title: Figure and table generation scaffold from outputs/
workstream: WS09-figures
owner: agent
status: blocked
depends_on: [WS08-T01]
critical_path: false
non_negotiable: false
estimate_pd: 1
sources: ["analisi §7"]
interfaces: ["02-interfaces.md#experiment-config-and-outputs"]
review_items: []
---
## Obiettivo

Build the shared scaffold in `tools/figures/` that every later WS09 task plugs a target into: a typed reader of `outputs/<experiment_id>/<seed>/{config.yaml, metrics.json, git_rev.txt}`, seed aggregation, number formatting, IEEE figure style, provenance stamping and a CLI (`python -m tools.figures <target> [--check]`). Concrete output: the package with its tests, seven registered target names (`fig1`, `fig2`, `fig3`, `fig4`, `table1`, `table2`, `table3`), and the guarantee that a generated file cannot contain a number that was not read from a recorded input.

## Contesto

- `docs/plan/02-interfaces.md#experiment-config-and-outputs`: the output directory layout and the rule that tables and figures are generated only from those files.
- `docs/plan/02-interfaces.md#metrics`: metric names, at least five seeds, bootstrap intervals over patient-days, the coverage qualifier.
- `docs/plan/workstreams/WS08-experiments/tasks/T01-runner-metrics.md` and the `metrics.json` writer it produces: they fix the exact nesting of keys. **Unblocked when** WS08-T01 is done, so that a real `metrics.json` layout exists to copy.
- `docs/plan/workstreams/WS09-figures/README.md`: shared conventions of all generators (they restate `01-conventions.md` sections 8 and 9).
- The `dataviz` skill (`references/color-formula.md`, `references/marks-and-anatomy.md`, `references/anti-patterns.md`, `references/palette.md`, `scripts/validate_palette.js`).

## File toccati

- `tools/figures/` (create): `__init__.py`, `__main__.py` (CLI), `schema.py` (metric keys and nesting), `loader.py`, `aggregate.py`, `fmt.py`, `style.py`, `provenance.py`, `targets/__init__.py` (target registry with a decorator).
- `tests/figures/` (create): test modules named below and `tests/figures/fixtures/outputs/main/{0,1,2,3,4}/` (hand-written run directories).
- `pyproject.toml` (modify): an optional dependency group `figures` holding matplotlib (and numpy if not already declared), without version pins beyond the policy of WS05-T01; `pythonpath = ["."]` under `[tool.pytest.ini_options]` so that `tools.figures` is importable from tests.

Location note: `01-conventions.md` section 1 does not list a home for figure scripts. `tools/figures/` is used because `src/ralmon` must not depend on matplotlib. The final report of the planning run flags this for an ADR.

## Test

Fixture facts (all values are fixtures for the tests, not results): five seeds 0-4, each with a `metrics.json` in the WS08-T01 layout. Seed values of the `per_class_prf` F1 for C1 are 0.70, 0.72, 0.74, 0.76, 0.78, so the mean is 0.74 and the sample standard deviation (ddof = 1) is sqrt(0.004 / 4) = 0.0316...

Loader and schema (`tests/figures/test_loader.py`):

1. `test_loader_reads_all_seeds_sorted_numerically`: with seed directories 0, 1, 2, 10, 11 the order returned is 0, 1, 2, 10, 11 (not lexicographic).
2. `test_loader_rejects_fewer_than_five_seeds_unless_draft`: four seed directories raise `InsufficientSeedsError` naming the experiment id; with `allow_fewer_seeds=True` the result carries `draft=True`.
3. `test_loader_rejects_unknown_metric_key`: a `metrics.json` with a key that is not a metric name of `#metrics` raises `UnknownMetricError` naming file and key.
4. `test_loader_missing_file_error_names_path`: deleting `git_rev.txt` of seed 3 raises an error whose message contains the full path.
5. `test_loader_records_sha256_of_every_input_file`: the returned `Runs.inputs` maps each of the 15 files (5 seeds, 3 files) to its SHA-256; changing one byte changes exactly one hash.

Aggregation (`tests/figures/test_aggregate.py`):

6. `test_aggregate_mean_and_sample_sd`: F1 C1 over the fixture gives mean 0.74 and SD 0.0316 (to 4 decimals), `interval_kind == "sd_over_seeds"`.
7. `test_aggregate_uses_recorded_bootstrap_interval_when_present`: if `metrics.json` records a bootstrap interval for a metric (only if WS08-T01 defines one), `interval_kind == "bootstrap"` and the recorded bounds are used, never recomputed.
8. `test_aggregate_missing_everywhere_is_none`: a metric absent in all seeds aggregates to `None`.
9. `test_aggregate_mixed_presence_raises`: absent in seed 2 only raises `InconsistentMetricError` (a partial metric is never averaged silently).

Formatting (`tests/figures/test_fmt.py`):

10. `test_fmt_number_negative_uses_math_minus`: `number(-12.5, 1) == "$-12.5$"`.
11. `test_fmt_number_no_negative_zero`: `number(-0.001, 2) == "0.00"`.
12. `test_fmt_none_is_na`: `number(None, 2) == "n/a"`.
13. `test_fmt_cell_mean_sd`: `cell(0.74, 0.0316, 2) == "$0.74\\pm0.03$"`.
14. `test_fmt_latex_escape`: `latex_escape("bp_band_low & 5%")` escapes underscore, ampersand and percent.
15. `test_fmt_macro_names_letters_only`: `macro("NSeeds", 5) == "\\newcommand{\\NSeeds}{5}"`; `macro("N5", 5)` raises (LaTeX control sequence names contain letters only).
16. `test_fmt_roundtrip_property` (Hypothesis, ADR-016): for finite floats in [-1e4, 1e4] and 0 to 4 decimals, the parsed output differs from the input by at most 0.5 * 10^-decimals.

Provenance and CLI (`tests/figures/test_provenance_cli.py`):

17. `test_generated_tex_has_header_first_line`: a file written through `write_generated` starts with `% GENERATED by tools/figures`.
18. `test_sidecar_lists_input_hashes_and_git_rev`: the `.data.json` written for a fake target contains the input hashes and the `git_rev.txt` contents of every seed.
19. `test_check_detects_stale_input`: after regeneration, changing an input file makes `--check` return non-zero and name the file.
20. `test_check_detects_hand_edited_output`: appending one character to a generated `.tex` makes `--check` non-zero.
21. `test_check_fails_on_draft_output`: output generated with `allow_fewer_seeds` makes `--check` non-zero.
22. `test_targets_write_only_through_write_generated`: a static scan of `tools/figures/targets/*.py` finds no `open(`, `write_text(` or `savefig(` call outside `provenance.py` and `style.py` (this is what makes "no hand-typed file in `paper/`" enforceable).
23. `test_cli_list_names_all_targets`: `--list` prints `fig1 fig2 fig3 fig4 table1 table2 table3`.
24. `test_cli_unknown_target_exit_2`, `test_cli_missing_outputs_dir_exit_nonzero_names_path`.
25. `test_cli_all_excludes_optional_fig4`: `all` does not run `fig4`; `all --with-optional` does.

Style (`tests/figures/test_style.py`):

26. `test_widths_are_ieee_column_values`: `FIG_WIDTH_SINGLE_IN == 3.5` and `FIG_WIDTH_DOUBLE_IN == 7.16`.
27. `test_rcparams_embed_fonts`: after `apply_rcparams()`, `pdf.fonttype == 42` and `ps.fonttype == 42`.
28. `test_save_pdf_keeps_figure_size`: a 3.5 x 2 in figure saved with `save_pdf` has `/MediaBox` width 252 pt and height 144 pt (tolerance 0.01), read from the PDF bytes.
29. `test_save_pdf_is_deterministic`: two saves of the same figure are byte-identical (creation date removed from the metadata).
30. `test_method_style_fixed_order_and_secondary_encoding`: `METHOD_ORDER == ["B1", "B2", "B3", "B4", "B5", "ours"]`; the six entries have pairwise different colour, and pairwise different (marker, linestyle) pairs.
31. `test_state_style_distinguishable_without_colour`: `PENDING`, `PREDICTED_VIOLATION`, `VIOLATED`, `SATISFIED` have pairwise different (marker, hatch) pairs.

## Passi

1. Read the WS08-T01 task file and its `metrics.json` writer and tests. Copy the exact key nesting (for example how `per_class_prf`, `detection_delay_ms`, `attribution_confusion`, `recall_vs_false_alarm_curve` are stored, whether bootstrap intervals are stored, whether the test-split patient-day count is stored) into the docstring of `schema.py`. If any of these is not defined, stop and report it to the WS08 owner; do not invent a layout.
2. Create the fixture run directories under `tests/figures/fixtures/outputs/main/` in that layout, with the values above.
3. Write the tests of the Test section. Run `pytest tests/figures -q` and confirm every test fails (ImportError or assertion), then commit `WS09-T01: add failing scaffold tests`.
4. Implement `schema.py`, `loader.py`, `aggregate.py`, `fmt.py` until tests 1-16 pass. Aggregation rules: mean over seeds, sample SD (ddof = 1), recorded bootstrap interval preferred over SD, `None` handling as in tests 8 and 9. The kind of interval is part of the result and is printed in table notes by later tasks; both kinds are never mixed silently.
5. Implement `style.py`: width constants, `apply_rcparams()`, `save_pdf(fig, path)` (no `bbox_inches="tight"`, `metadata={"CreationDate": None}`), `METHOD_STYLE` and `STATE_STYLE`. Take colours from the default categorical order in the dataviz skill's `references/palette.md` (slots 1 to 6 for B1-B5 and `ours`, in that fixed order) and the status palette for the verdict states. Run `node <skill base>/scripts/validate_palette.js "<hex,...>" --mode light` (the skill also ships `validate_palette.py`), fix every FAIL, and record the command and its verdict in the module docstring. The all-pairs mode cannot clear its floors for six series: the docstring must say that identity is therefore also carried by marker, line style and direct labels.
6. Implement `provenance.py` (`write_generated`, header, sidecar, SHA-256, `--check` comparison) and `targets/__init__.py` (a `@target("name")` decorator; the seven names registered with a placeholder that exits with code 2 and the message "owned by WS09-T0x, not implemented yet").
7. Implement `__main__.py` with `--list`, `--check`, `--outputs DIR` (default `outputs`), `--paper DIR` (default `paper`), `--allow-fewer-seeds`, `--with-optional`, `--width single|double`. Exit codes: 0 success, 1 check failure or missing input, 2 usage or unknown target.
8. Modify `pyproject.toml` as described. Run `ruff format tools/figures tests/figures`, `ruff check tools/figures tests/figures`, then `pytest tests/figures -q` until green.
9. Commit `WS09-T01: add figure and table scaffold` and set this task's `status` to `done`.

## Done when

- `pytest tests/figures -q` exits 0.
- `ruff check tools/figures tests/figures` exits 0.
- `python -m tools.figures --list` exits 0 and prints the seven target names.
- The docstring of `tools/figures/style.py` names the validator command and its verdict for the method palette: `grep -n 'validate_palette' tools/figures/style.py` prints at least one line.
