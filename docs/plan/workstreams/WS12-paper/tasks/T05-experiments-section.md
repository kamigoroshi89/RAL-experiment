---
id: WS12-T05
title: Section V experiments and results
workstream: WS12-paper
owner: agent
status: blocked
depends_on: ["WS09-T05", "WS08-T07", "WS07-T07", "WS10-T06"]
critical_path: true
non_negotiable: false
estimate_pd: 2.5
sources: ["analisi §5", "analisi §7", "analisi §10", "analisi §4.8"]
interfaces: ["02-interfaces.md#metrics"]
review_items: []
---
## Obiettivo

Write Section V in `paper/sections/05-experiments.tex` (V-A/B setup 0.50 page, V-C results 0.60, V-D ablations and shift 0.35, V-E robot deployment 0.25) from the frozen results, and create the script `tools/paper_numbers.py` that turns `outputs/`, the benchmark manifest and the WS09 sidecars into the LaTeX macros of `paper/generated/numbers.tex` that the WS09 macro files do not already provide, so that no number of the paper is typed by hand (`01-conventions.md` section 9).

The section reports honestly: per-class detection, false alarms per patient-day, detection delay, coverage in distribution and under shift, attribution with abstention, at least one result where the closest published method (B5) fails, the A4 result that answers "why a robot", and the on-board latency. Concrete output: the section file with the captions of Fig. 2, Table II, Table III, Fig. 3 (and Fig. 4 if included), the script with tests, the generated macro file, and the updated ledger in `paper/PAGE_BUDGET.md`.

## Contesto

Blocked until WS09-T05 (Table II, Table III, Fig. 3 and their macro file) and WS08-T07 (result freeze, `experiments/results.lock.json`) are `done`.

- `docs/source/analisi.md` §5 (5.1 benchmark and ground truth, 5.4 baselines, 5.5 metrics, 5.6 ablations) and §7 rows V-A to V-E.
- `docs/plan/02-interfaces.md#metrics` (metric names, matching configuration, bootstrap and seed rules).
- `docs/plan/02-interfaces.md#experiment-config-and-outputs` (layout `outputs/<experiment_id>/<seed>/{config.yaml, metrics.json, git_rev.txt}`).
- `docs/plan/workstreams/WS08-experiments/README.md` (experiment ids, `metrics.json` layout with `meta` and `analysis`, evaluation conventions E1 to E10).
- `docs/plan/workstreams/WS09-figures/README.md` (paths of figures, tables and macro files; `tools/figures` loader, aggregator and macro formatter).

## File toccati

- `paper/sections/05-experiments.tex` (modify)
- `tools/paper_numbers.py` (create)
- `tests/tools/test_paper_numbers.py` and its fixtures under `tests/tools/fixtures/paper_numbers/` (create; the fixture directory counts as one path)
- `paper/generated/numbers.tex` (create, generated)
- `paper/PAGE_BUDGET.md` (modify: measured sizes, ledger)

## Test

Two parts. Part A, pytest tests of `tools/paper_numbers.py`, written first, with hand-written fixtures in the WS08-T01 layout: `outputs/main/<seed>/{metrics.json, git_rev.txt}` for seeds 0 to 4, `outputs/ws07-latency/<seed>/metrics.json`, a manifest fixture, and a sidecar fixture. The script builds on `tools.figures` of WS09-T01 (loader, aggregator, `fmt.macro`), so it inherits the rules "fewer than five seeds is an error" and "unknown metric key is an error".

Part A:

- `test_macro_value_matches_hand_computed_mean`: `false_alarms_per_patient_day.ours.value` equal to 1.0, 2.0, 3.0, 4.0 and 5.0 gives `\ResFalseAlarms` equal to `3.00` (mean 3.0); `per_class_prf.ours.any.recall.value` equal to 0.80, 0.82, 0.84, 0.86 and 0.88 gives `\ResRecall` equal to `0.84`.
- `test_coverage_gap_is_max_abs_gap_in_points_averaged_over_seeds`: for `empirical_coverage.ours.in_distribution` with nominal 0.9 and 0.8 and `alert_level` chosen so that the per-seed maximum gaps are 1, 2, 3, 4 and 5 points, `\ResCoverageGap` is `3.0`.
- `test_manifest_macros`: a manifest fixture with 7 day files under `days/`, `event_counts` of 3 and 2, and `n_unverified` 4 gives `\NPatientDays` 7, `\NInjectedEvents` 5, `\NUnverifiedParams` 4.
- `test_latency_macro_from_ws07_outputs`: `latency_percentiles.ours.p95` equal to 10.0, 12.0, 14.0, 16.0 and 18.0 in `outputs/ws07-latency` gives `\ResLatencyMs` equal to `14.0`.
- `test_sidecar_facts_exported_as_macros`: a Fig. 2 sidecar fixture with `alpha`, `day_index`, `seed` gives the macros `\FigTwoAlpha`, `\FigTwoDay`, `\FigTwoSeed`; a string value with an underscore is LaTeX-escaped.
- `test_fewer_than_five_seeds_is_an_error`: four seed directories give exit code 1 and a message naming the experiment.
- `test_missing_metric_key_is_an_error_naming_the_key`: deleting the key from one seed gives exit code 1 naming key and seed; the value is never replaced by zero.
- `test_fixture_only_manifest_is_refused`: a manifest with `fixture_only: true` gives exit code 1 (the headline gate of WS04 requires `fixture_only: false`).
- `test_unresolved_macros_are_listed_not_zero_filled`: a macro whose experiment directory is absent is missing from `numbers.tex`, is printed in a list on standard output, and the exit code is 3.
- `test_output_is_byte_identical_on_rerun`: two runs on the same fixtures produce identical files.
- `test_header_records_git_rev_per_experiment` and `test_inconsistent_git_rev_across_seeds_is_an_error`: the header comments carry one `git_rev.txt` value per experiment id; differing revisions across the seeds of one experiment give exit code 1.
- `test_check_mode_detects_stale_file`: after editing one fixture value, `--check` exits 1; on unchanged fixtures it exits 0.
- `test_ledger_and_script_macro_sets_match`: the macro names in the `Number macros` table of `paper/PAGE_BUDGET.md` (emitted-by column `T05`) equal the macro set defined in the script.

Part B, verification checks of the section:

1. `python tools/check_paper.py numerals paper/sections/05-experiments.tex` exits 0: every number in prose and captions is a macro; tables and figures are included from WS09 and never retyped.
2. V-A/B defines ground truth on the latent trace (a true C1 is a violation of phi_CP on the latent trace; true C2 and C3 are the injected events) and says that monitors and baselines see only the observed trace. The hypertension scenario takes at most four lines and the workshop Table I is absent (cut ledger item 3).
3. Baselines B1 to B5 are named; the text says that B1 and B3 receive the same bands and schedules as the proposed method; B5 is described as the method of Lindemann et al. 2023 applied to the same templates, cited only through a verified bibliography entry.
4. The section declares, through macros added to the script and the ledger: matching tolerance and time reference (`meta.match`), the calibration unit (patient episode), that coverage is marginal, the bootstrap resamples and level (`meta.bootstrap`), the number of seeds, and the split by patient. The Table II note macro of WS09 is used as is.
5. The prior source is stated from `meta.prior_source` and the manifest (`prior_source_name`, `n_unverified`): literature priors, or derived from MIMIC-IV or eICU. If only literature priors were used the text says so (ADR-005) and agrees with the abstract wording of `paper/front/title-abstract-decision.md`; the number of unverified parameters is reported (ADR-020). The ROS 2 distribution and simulator are those of `## ADR-011 decision` in `WS00-T05.md`.
6. Table II has the rows B1 to B5 and the proposed method and the columns F1 for C1, C2 and C3, false alarms per patient-day, median detection delay and coverage; every column is discussed in the text; the caption is written here and the note is the WS09 macro.
7. Fig. 2 is referenced, explained and captioned from its sidecar (day drawn from the semi-synthetic test split, how it was selected, alpha and variant): PENDING, PREDICTED-VIOLATION and VIOLATED shown, injected events highlighted.
8. B5: the text reports the failure condition recorded in `analysis` of `outputs/main/<seed>/metrics.json` (`b5_failure_found`), with its cause among those of analisi §5.4 (sparse sampling, mixed units, no attribution) and the number from `outputs`. If `b5_failure_found` is false the text says so plainly and the completion note reports it to WS12-T07; no case is constructed.
9. Forecasting is reported as measured: usefulness for continuous signals and robot deadlines (results of WS07-T06 are cited, not recomputed), and the width of blood-pressure predictions. Negative outcomes are stated.
10. Attribution: confusion including UNDETERMINED, abstention rate, accuracy against coverage, and the measured rates for the rows declared not distinguishable by construction (`analysis.declared_not_distinguishable`: silent cuff bias, informed attacker).
11. Ablations A1, A2, A3, A5, A7 (WS08-T03), A4 (WS08-T04) and A6 with shift (WS08-T05) each have a sentence with the measured effect and whether it agrees with the hypothesis of analisi §5.6. A4 reports the change of kappa for robot C2 and forged dispenses and the temporal coverage of the robot channel. Unconfirmed hypotheses are stated as unconfirmed. If Table III or Fig. 3 is dropped for space, the outcomes are still given through macros.
12. Coverage is reported in distribution and under shift with the shift definition used by WS08-T05, and the caption note carries the qualifier "marginal over the population, not conditional on the patient".
13. V-E reports latency percentiles, CPU, memory and scalability from `outputs/ws07-latency/`, states that the timeline compression of the simulation is a validity threat (WS07 policy), and reports the lab outcome exactly as `outputs/WS10-T05.md` (`outcome`): for `completed` or `partial` the numbers of `outputs/lab-summary/metrics.json` through macros and the limits of `hardware/lab_demo/claims.md`; for `cut` the fallback (simulation video, `hardware/lab_demo/fallback/storyboard.md`) with the statement that the lab demo was not run and no claim of real-robot validation.
14. The alert load on unlabeled real data appears only if `outputs/unlabeled-real/` exists (WS08-T06); otherwise the ledger notes the absence for Section VI.
15. Budgets: V-A/B 0.50, V-C 0.60, V-D 0.35, V-E 0.25 page, each within 0.10.
16. `python tools/check_paper.py terms claims tokens paper/sections/05-experiments.tex` exits 0; DISPENSE and INTAKE are never interchanged; "violation" is not used for C2 and C3 events. Citation keys are verified (`python3 tools/check_bib.py`).

## Passi

1. Preconditions. Confirm that these exist and are frozen: `experiments/results.lock.json` listing the experiment ids the paper cites (`main`, `A1` to `A7`, `shift`, and `unlabeled-real` if run), `outputs/` for them, `outputs/ws07-latency/` (WS07-T07), `outputs/WS10-T05.md` with `outcome` filled (and `outputs/lab-summary/metrics.json` unless `cut`), the benchmark manifest with `fixture_only: false`, and the WS09 files and macro files. If something is missing, stop and write a blocking note naming the missing artefact and its upstream task; do not estimate.
2. Write `tests/tools/test_paper_numbers.py` and the fixtures from Part A. Run `pytest tests/tools/test_paper_numbers.py -q`; all tests fail.
3. Implement `tools/paper_numbers.py` on top of `tools/figures` (loader, `aggregate`, `fmt.macro`; if the loader rejects the layout of the WS07 outputs, read that file with `json` and say so in the completion note). Interface: `python tools/paper_numbers.py --outputs outputs --out paper/generated/numbers.tex [--check]`. Exit codes: 0 success, 1 error (missing input, fewer than five seeds, missing key, inconsistent revision, fixture-only manifest), 2 usage, 3 some macros unresolved (listed). The macro table (name, source file and key path, aggregation, format) lives in the script. Run the tests until green.
4. Fill the `Number macros` table of `paper/PAGE_BUDGET.md` for the macros marked T05 in the table "Binding number macros" of `docs/plan/workstreams/WS12-paper/README.md`, with the source key path, aggregation and format of each. Choose and record: the class behind `\ResRecall` (pooled `any` by default), the level behind `\ResCoverageGap` (`alert_level`, the empirical form of Proposition 1, or `band_level`), and the percentile behind `\ResLatencyMs`. Add any further macro Section V needs (declarations of check 4, lab numbers, caption facts) to the script and the table in the same commit.
5. Run the script on the real `outputs/`. Every macro used by Section V must resolve; unresolved ones block the task.
6. Write V-A/B, then V-C, V-D, V-E, using macros for every number, `\input` or `\includegraphics` of the WS09 files wrapped in `table`, `table*`, `figure` or `figure*` with the captions written here. Use "in this benchmark" and similar qualifiers; never write that the method "ensures" anything. State in V-C which aggregation the abstract's recall number refers to (the abstract is filled by WS12-T06 from the same macros).
7. Compile with `make -C paper pdf`, measure and trim to the budgets. Trim prose first; never remove the B5 failure result, the A4 result, the coverage statement or the declarations of check 4. Decide between Fig. 3 and Table III by measured height (rule in `PAGE_BUDGET.md`) and record it.
8. Run Part B checks and `make -C paper check-numbers`. Update `PAGE_BUDGET.md`.
9. Set `status: done`; set WS12-T06 to `ready` if its other dependencies are done. Commit `WS12-T05: write section V and number export`.

## Done when

```
pytest tests/tools/test_paper_numbers.py -q                                                  # exit 0
ruff check tools tests/tools                                                                  # exit 0
python tools/paper_numbers.py --outputs outputs --out paper/generated/numbers.tex             # exit 0 (no unresolved macro)
make -C paper check-numbers                                                                   # exit 0
python tools/check_paper.py numerals terms claims tokens paper/sections/05-experiments.tex    # exit 0
python3 tools/check_bib.py                                                                    # exit 0
make -C paper pdf                                                                             # exit 0
```

`paper/PAGE_BUDGET.md` shows Section V measured within its budgets by 0.10 page per subsection, and records the Fig. 3 or Table III decision.
