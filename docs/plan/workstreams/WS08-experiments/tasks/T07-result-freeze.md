---
id: WS08-T07
title: Reproducibility check and result freeze
workstream: WS08-experiments
owner: agent
status: blocked
depends_on: ["WS08-T03", "WS08-T04", "WS08-T05"]
critical_path: true
non_negotiable: false
estimate_pd: 1
sources: ["analisi §5.1", "analisi §5.5", "analisi §10 (1)"]
interfaces: ["02-interfaces.md#experiment-config-and-outputs"]
review_items: ["AE-1"]
---
## Obiettivo

Prove that the results can be regenerated and fix them: every headline experiment is re-run at one clean code revision, a second run must reproduce every `metrics.json` byte for byte (`01-conventions.md` section 3), and a lock file records the hash of every frozen file so that WS09, WS12 and WS13 can detect stale or hand-edited results. The freeze also checks that the honest-reporting rules of the README (H1 to H9) left their traces in the outputs, so a result set without the blood-pressure forecast row, the B5 failure analysis or the undetectable rows cannot be frozen. Concrete output: `src/ralmon/eval/freeze.py`, `experiments/results.lock.json` (committed; `outputs/` is not), and a completion note with the checklist. This closes AE-1 (experimental validation exists and is reproducible).

## Contesto

- `01-conventions.md` sections 3 (deterministic by construction, bit for bit) and 9 (outputs layout, numbers come from `outputs/`) and `02-interfaces.md#experiment-config-and-outputs`.
- `docs/plan/workstreams/WS08-experiments/README.md`: metrics.json layout, `meta`, `analysis`, `run_options.required_analysis`, honest-reporting rules H1 to H9.
- Completion notes of WS08-T01 to WS08-T06 (experiment ids, seeds, `required_analysis` per experiment, status of the guarded parts).
- WS13-T02 (reads the lock file) and WS09-T01 (`--check` of generated files); WS09-T03 writes `outputs/fig2/`, which the freeze must not touch.
- Blocked until WS08-T03, WS08-T04 and WS08-T05 are `done`. WS08-T06 is not required: if it is not done, the lock records it as `not_run` with the blocking task.

## File toccati

- `src/ralmon/eval/freeze.py` (create): `sha256_file`, `discover_headline`, `run_all`, `write_lock`, `check`, `check_rerun`, `checklist`, CLI (`--run`, `--write-lock`, `--check`, `--rerun`).
- `experiments/results.lock.json` (create at the freeze; sorted keys).
- `tests/eval/test_freeze.py` (create).
- `tests/fixtures/eval/freeze/` (create): a small set of fixture run directories (two experiments, five seeds each, hand-written `metrics.json`), and a stub runner.

## Test

Write these first. Fixture directories are hand-written; no experiment is run in the unit tests.

`tests/eval/test_freeze.py`

1. `test_sha256_file_known_values`: an empty file hashes to `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` and a file holding `abc` to `ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad`.
2. `test_discover_headline_ignores_other_configs`: of three YAML files in a fixture `experiments/` directory, only those with `run_options.headline: true` are discovered; a `smoke.yaml` without `headline` is ignored (WS13-T02 adds such a profile).
3. `test_discover_requires_expected_ids`: if a headline YAML for one of `main`, `A1`, `A2`, `A3`, `A4`, `A5`, `A6`, `A7`, `shift` is missing, `discover_headline` raises `MissingExperimentError` naming the id.
4. `test_lock_is_deterministic_and_sorted`: two `write_lock` calls on the same fixture give identical bytes; the top-level keys are `checklist`, `experiments`, `git_rev`, `lock_version`, `not_run` in sorted order; each seed entry has `config_yaml_sha256`, `git_rev_txt_sha256` and `metrics_sha256`.
5. `test_check_passes_on_unchanged_outputs`: `check` on the fixture returns no failures.
6. `test_check_fails_when_one_byte_of_metrics_changes`: changing one byte of one `metrics.json` gives exactly one failure that contains the file path and the first eight characters of both hashes.
7. `test_check_fails_on_config_drift`: editing `experiments/<id>.yaml` after the lock is written fails naming the id.
8. `test_check_requires_five_seeds_for_headline`: an experiment with four seed directories fails naming the id and the count.
9. `test_check_rejects_dirty_or_mixed_revision`: a `git_rev.txt` ending in `-dirty`, or two frozen seed directories with different revisions, fails.
10. `test_check_requires_analysis_keys`: a `metrics.json` of `main` without `analysis.b5_failure` fails naming the key and the seed.
11. `test_not_run_must_be_recorded_with_reason`: with no `outputs/unlabeled-real` and no `not_run` entry the check fails; with an entry whose reason names `WS04-T13` it passes; an entry with an empty reason fails.
12. `test_check_rerun_detects_nondeterminism`: with a stub runner whose second run differs in one byte the check fails naming the path; with an identical second run it passes.
13. `test_freeze_does_not_touch_figure_export_dirs`: `outputs/fig2/` is neither hashed nor deleted by `--run` or `--write-lock`.
14. `test_run_refuses_dirty_tree`: `run_all` with a revision provider returning `abc123-dirty` raises `DirtyTreeError` before any experiment starts.
15. `test_checklist_h1_to_h9`: the checklist has one entry per rule with a pass or fail derived from keys: H1 `analysis.forecast_informativeness` with a `bp` row in `A1`; H2 `analysis.b5_failure.b5_failure_found` present in `main`; H3 `analysis.undetectable_rows` with rows DX-04 and DX-10 in `main`; H4 `analysis.claim_action` in `A4`; H5 at least 5 seeds and intervals present; H6 `meta.prior_source` non-empty; H7 `meta.coverage_qualifier` non-empty; H8 `analysis.tolerance_sensitivity` in `main`; H9 `analysis.alert_load` in `main`. A fixture missing one key makes exactly that entry fail.
16. `test_lock_records_cohort_shift_status`: the `not_run` block contains `shift:cohort_shift` with reason `blocked on WS04-T13` when `analysis.cohort_shift.status` is `not_run`, and no such entry when the cohort shift ran.

## Passi

1. Verify the unblock conditions and read the completion notes of T01 to T06. Record whether T06 is done, refused or blocked. Branch `ws08-t07-result-freeze`; set `status: in_progress`.
2. Write the fixtures and tests 1 to 16; run `pytest tests/eval/test_freeze.py -q`; confirm they fail. Commit `WS08-T07: add failing freeze tests`.
3. Implement `freeze.py`: discovery (headline YAMLs plus the expected ids), `sha256_file`, `run_all` (refuses a dirty tree; runs every headline config into `outputs/`), `write_lock` (one revision for all frozen seed directories; `not_run` block always present, empty if nothing is pending), `check`, `check_rerun` (re-runs every headline config into a scratch directory and compares every `metrics.json`, `config.yaml` and `git_rev.txt` byte for byte), `checklist`. Tests 1 to 16 pass.
4. Make the tree clean: commit or discard every pending change. Any change after this point to `src/ralmon`, `experiments/*.yaml` or the benchmark version that can alter a metric means T07 must be repeated from this step.
5. Run `python -m ralmon.eval.freeze --run`, then `python -m ralmon.eval.freeze --write-lock`, then `python -m ralmon.eval.freeze --check --rerun`. A byte difference is a bug (an unseeded generator, an iteration-order dependency, a wall-clock read, a thread-count dependency of a numerical routine): find it and fix it in the owning package, never by relaxing the check.
6. Read the checklist. If any of H1 to H9 fails, do not freeze: go back to the task that owns the analysis key (T02 for H2, H3, H8, H9; T03 for H1; T04 for H4; T05 for coverage under shift) and repeat from step 4.
7. Write the completion note: experiment ids with seed counts, the frozen revision, the lock hash (`sha256sum experiments/results.lock.json`), the `not_run` entries, the checklist, and the statements WS12 must carry (for example "shift test is synthetic only", "literature priors"). Tell the owners of WS09-T05, WS12-T05 and WS13-T02 that results are frozen. Commit `WS08-T07: freeze results`; set `status: done`.

## Done when

- `pytest tests/eval -q` exits 0, `ruff check src tests` exits 0, `mypy src/ralmon` exits 0.
- `python -m ralmon.eval.freeze --check --rerun` exits 0.
- `python -c "import json; d = json.load(open('experiments/results.lock.json')); assert {'main','A1','A2','A3','A4','A5','A6','A7','shift'} <= set(d['experiments']); assert 'not_run' in d; assert all(d['checklist'].values())"` exits 0.
- `grep -c '"git_rev"' experiments/results.lock.json` prints 1 (one code revision for all frozen outputs).
