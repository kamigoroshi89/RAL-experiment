---
id: WS09-T05
title: Table II, Table III and Fig. 3
workstream: WS09-figures
owner: agent
status: blocked
depends_on: ["WS09-T01", "WS08-T03", "WS08-T05", "WS08-T04"]
critical_path: true
non_negotiable: false
estimate_pd: 2
sources: ["analisi §7", "analisi §5.5", "analisi §5.6"]
interfaces: ["02-interfaces.md#metrics"]
review_items: []
---
## Obiettivo

Generate the three result artefacts of section V from `outputs/`: Table II (main results: rows B1-B5 and the proposed method; columns F1 for C1, C2 and C3, false alarms per patient-day, median delay, coverage), Table III (ablations A1-A7) and Fig. 3 (two panels: recall versus false alarms per patient-day, and empirical coverage versus nominal level over the alpha grid, in distribution and under shift). Output: `paper/tables/table2_main.tex`, `table3_ablations.tex`, `paper/figures/fig3_recall_coverage.pdf`, their `.data.json` sidecars and the LaTeX macros for the numbers that section V quotes.

## Contesto

- `docs/source/analisi.md` §7 (Table II columns, Fig. 3 panels, "Fig. 3 or Table III"), §5.5 (metrics: per-class event-level F1, detection delay relative to the first decidable instant with negative values as early warning, false alarms per patient-day, recall versus false alarms over alpha, empirical coverage against nominal, ECE, abstention rate) and §5.6 (ablations A1-A7 and the component each removes).
- `docs/plan/02-interfaces.md#metrics`: the metric functions, `MatchConfig`, bootstrap intervals over patient-days, at least five seeds, coverage reported in distribution and under shift, and the rule that coverage is marginal over the population.
- `docs/plan/workstreams/WS08-experiments/tasks/` (directory): T02 (main experiment), T03 (A1, A2, A3, A5, A7), T04 (A4), T05 (shift and A6) fix the experiment ids, detector names, alpha grids and the exact `metrics.json` keys for these artefacts.
- `docs/plan/workstreams/WS09-figures/README.md`: shared conventions (n/a, seeds, widths, fonts, provenance, terminology, coverage qualifier).
- The `dataviz` skill: `references/choosing-a-form.md`, `references/color-formula.md`, `references/marks-and-anatomy.md`, `references/anti-patterns.md`.

Unblocked when WS09-T01, WS08-T03 and WS08-T05 are done. Undeclared precondition: the Table III row for A4 needs `outputs/A4/` from WS08-T04, and Table II needs `outputs/main/` from WS08-T02 (reachable through WS08-T03). The target fails naming every missing experiment directory at once, so a missing A4 cannot be dropped silently. Final regeneration for submission runs after WS08-T07 (result freeze).

## File toccati

- `tools/figures/targets/results_tables.py` (create): targets `table2` and `table3` with shared row building, abstention rate, per-seed medians, paired differences.
- `tools/figures/targets/fig3_recall_coverage.py` (create): model builder, renderer and the `fig3` target.
- `tests/figures/test_results_tables_fig3.py` (create): tests below.
- `tests/figures/fixtures/results/` (create): hand-written `outputs/` trees for `main`, `A1`-`A7` and `shift`, five seeds each, in the WS08-T01 layout.
- `paper/tables/` (create, generated): `table2_main.tex`, `table3_ablations.tex`, their `.data.json`, and `table2_macros.tex` (holding the results macros and the note text of both tables).
- `paper/figures/` (create, generated): `fig3_recall_coverage.pdf` and `.data.json`.

## Test

Fixture facts (fixtures only, not results): detector names `B1`, `B2`, `B3`, `B4`, `B5`, `ours`; alpha 0.1; `MatchConfig.tolerance_ms` 900 000 with `time_reference` `first_decidable`; `ours` F1 for C1 per seed 0.80, 0.82, 0.84, 0.86, 0.88 (mean 0.84, sample SD 0.0316); `ours` false alarms per patient-day 0.50 and `B4` 0.20 (lowest); `B1`, `B2` and `B3` record no coverage; `ours` detection delays for seed 0 are [-120 000, -60 000, 0] ms (median -60 000 ms, that is -1.0 min); an `attribution_confusion` of 8 alerts of which 2 have predicted label UNDETERMINED; ablation `A1` F1 for C1 per seed 0.70, 0.74, 0.78, 0.80, 0.84 (per-seed differences to `ours`: 0.10, 0.08, 0.06, 0.06, 0.04; mean 0.068). Detector and experiment names of the real runs come from WS08-T02 to T05 (the contract example is `ours-A1`); the tests use them through constants.

Table II:

1. `test_table2_rows_and_columns`: rows appear in the fixed order B1, B2, B3, B4, B5, ours; header has exactly the columns F1 C1, F1 C2, F1 C3, false alarms per patient-day, median delay, coverage.
2. `test_table2_values_are_seed_means`: the `ours` F1 C1 cell is `$0.84\pm0.03$` (mean and sample SD over the five seeds).
3. `test_table2_none_renders_na_not_zero`: the coverage cells of `B1`, `B2`, `B3` are `n/a`, and the note explains that `n/a` means "not produced by the detector".
4. `test_table2_bold_best_f1_and_lowest_false_alarms`: `ours` is bold in F1 C1 and `B4` is bold in false alarms per patient-day; the delay and coverage columns have no bold.
5. `test_table2_median_delay_in_minutes_signed`: the seed-0 median of -60 000 ms is converted with `MS_PER_MINUTE` to -1.0 min; the per-seed medians are aggregated like every other column; the note states that negative values are early warnings.
6. `test_table2_coverage_header_uses_nominal_from_config`: with alpha 0.1 the coverage header or note reads nominal 0.90 (`1 - alpha`, read from `config.yaml`).
7. `test_table2_notes_state_matching_and_marginal_coverage`: the note macro contains the tolerance "15 min" (900 000 ms), the time reference, the number of seeds (5), the kind of interval (`sd_over_seeds` or bootstrap, as reported by the aggregator), and the words "marginal" and "not conditional on the patient".
8. `test_table2_macros`: `table2_macros.tex` defines `\NSeeds` (5), `\AlphaMain` (0.1) and `\NTestPatientDays` (taken from the count recorded by WS08-T01; if `metrics.json` records none, the target stops and reports the gap, it does not count files itself).
9. `test_table2_fewer_than_five_seeds_fails_without_flag`: four seeds make `table2` exit non-zero; with `--allow-fewer-seeds` the output carries the `DRAFT` stamp.
10. `test_table2_missing_seed_dir_names_path`: removing `outputs/main/3` gives a non-zero exit and the path in the message.

Table III:

11. `test_table3_rows_and_ablation_labels`: rows are the full method, then A1, A2, A3, A4, A5, A6 (split and adaptive, both marked as evaluated under shift) and A7, each with the removed component named as in analisi §5.6; columns are F1 C1, C2, C3, false alarms per patient-day, median delay, coverage, ECE and abstention rate.
12. `test_table3_missing_experiment_dir_fails_naming_all`: with `outputs/A4` and `outputs/A7` removed the error lists both ids.
13. `test_abstention_rate_from_confusion`: for the fixture confusion (8 alerts, 2 predicted UNDETERMINED) the rate is 0.25; the key order of `attribution_confusion` follows WS08-T01.
14. `test_table3_paired_differences_in_sidecar`: the sidecar holds, per ablation and metric, the mean of per-seed differences to the full method; for `A1` and F1 C1 it is 0.068 (`pytest.approx`); the table itself shows the values, not the differences.
15. `test_table3_not_applicable_metric_is_na`: a metric an ablation cannot produce (for example coverage when the predictor is removed, A2) is `n/a`.

Fig. 3:

16. `test_fig3_model_has_two_panels`: panel (a) has x = false alarms per patient-day and y = recall; panel (b) has x = nominal level `1 - alpha` and y = empirical coverage, with a diagonal reference line; the orientation of the pairs returned by `recall_vs_false_alarm_curve` is the one fixed by WS08-T01.
17. `test_fig3_series_use_fixed_method_style`: every series named B1-B5 or `ours` uses `style.METHOD_STYLE`; methods with a single operating point are markers, methods with an alpha sweep are lines with markers.
18. `test_fig3_series_have_distinct_marker_and_linestyle`: secondary encoding is present for every pair of series in a panel.
19. `test_fig3_error_bars_from_aggregator`: the vertical bars equal the aggregated interval (SD over seeds or recorded bootstrap) of the fixture.
20. `test_fig3_panel_b_covers_in_distribution_and_shift`: panel (b) contains series for the split and adaptive calibrators both in distribution and under shift when the fixture provides them (A6), and the sidecar records the calibration cohort and the test cohort.
21. `test_fig3_render_width_fonts_determinism`: width equals `FIG_WIDTH_DOUBLE_IN` by default (single column supported with stacked panels), fonts embedded, sidecar identical on two runs.
22. `test_fig3_legend_and_direct_labels`: a legend exists in each panel with two or more series; at most four series per panel are direct-labelled.

## Passi

1. Read the WS08 task files listed in Contesto and the real `outputs/` (or the WS08 fixtures) to get experiment ids, detector names, alpha grids, the meaning and orientation of `recall_vs_false_alarm_curve` pairs, the key order of `attribution_confusion`, how the median delay and the test-split patient-day count are stored, and whether bootstrap intervals are recorded. Record each answer in a comment block of `results_tables.py`. If one is missing, stop and report it to the WS08 owner.
2. Write the fixture `outputs/` trees by hand with the values above (other values arbitrary but fixed), and the tests. Run `pytest tests/figures/test_results_tables_fig3.py -q`, confirm failure, commit `WS09-T05: add failing results tests`.
3. Implement Table II: load `main`, aggregate through `tools.figures.aggregate`, build rows in `METHOD_ORDER`, format cells with `fmt`, mark best values with bold, write the `tabular` (booktabs) through `write_generated`. The file holds the tabular only; WS12 wraps it in `table` or `table*` with caption and label. Put the notes (seeds, patient-days, alpha and nominal coverage, matching tolerance and time reference, interval kind, n/a and delay-sign explanations, coverage qualifier) in `table2_macros.tex` as macros such as `\TableTwoNote`.
4. Implement Table III with the same machinery, the removed-component labels of analisi §5.6, the abstention rate and the paired differences in the sidecar. Do not add hypotheses or claims to the table text.
5. Implement Fig. 3 in the same module style: two panels, one axis each, fixed method style, direct labels on at most four series, legend always present, reference diagonal in panel (b), mean marks with interval bars. Apply the dataviz checklist (form choice, validated palette from `style.py`, thin marks, recessive grid, text in text colour, no dual axis).
6. Render, convert to PNG and inspect for overlaps, unreadable labels and legends over data; iterate until the render is readable at final size.
7. Run `python -m tools.figures table2 table3 fig3`, then the same command with `--check`. Run `ruff format`, `ruff check` and the tests until green. Commit `WS09-T05: add Table II, Table III and Fig. 3` and set `status` to `done`.
8. Do not regenerate for submission here: the last regeneration happens after WS08-T07, using `python -m tools.figures all`, and its `--check` must pass.

## Done when

- `pytest tests/figures/test_results_tables_fig3.py -q` exits 0 and `ruff check tools/figures tests/figures` exits 0.
- `python -m tools.figures table2 table3 fig3` exits 0 and `test -f paper/tables/table2_main.tex && test -f paper/tables/table3_ablations.tex && test -f paper/tables/table2_macros.tex && test -f paper/figures/fig3_recall_coverage.pdf`.
- `grep -c 'marginal' paper/tables/table2_macros.tex` prints a number of at least 1.
- `python -m tools.figures table2 table3 fig3 --check` exits 0.
