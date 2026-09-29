---
id: WS13-T02
title: "Reproduction scripts: one command per table and figure"
workstream: WS13-release
owner: agent
status: blocked
depends_on: ["WS08-T07", "WS09-T05", "WS09-T02", "WS09-T03", "WS09-T04"]
critical_path: false
non_negotiable: false
estimate_pd: 1.5
sources: ["analisi §9 (13)", "analisi §5.1", "analisi §7"]
interfaces: ["02-interfaces.md#experiment-config-and-outputs"]
review_items: []
---
## Obiettivo

Give a reader one command per table and figure of the paper, so that the results can be regenerated from the frozen configurations and seeds without reading the code. Concrete output: `tools/reproduce.py` (targets `table1`, `table2`, `table3`, `fig1`, `fig2`, `fig3`, `all`; profiles `full` and `smoke`; a `--check` mode that compares generated files with reference hashes), `experiments/smoke.yaml` (a small profile that runs in the normal test time and is never used for reporting), `docs/reproduce.md`, and the reference hash file `docs/reproduce-reference.sha256`. The script only orchestrates: experiments run through the WS08 runner, tables and figures through the WS09 generators, and every number comes from `outputs/` (`01-conventions.md` section 9). Nothing is published; pushing to any remote requires explicit human approval.

## Contesto

- `docs/plan/02-interfaces.md#experiment-config-and-outputs` (`ExperimentConfig`, the layout `outputs/<experiment_id>/<seed>/{config.yaml, metrics.json, git_rev.txt}`, tables and figures generated only from these files).
- `docs/plan/01-conventions.md` section 3 (same config and seed reproduce the same table bit for bit on the same machine; no wall-clock, no network, explicit seeds) and section 9 (documentation of results).
- `docs/plan/workstreams/WS08-experiments/` task files T01 (runner and configs) and T07 (reproducibility check and result freeze): the completion notes give the experiment ids, config paths, seeds, git revision and the freeze record.
- `docs/plan/workstreams/WS09-figures/` task files T01 to T05: the completion notes give the generator entry point and the input files of each table and figure.
- `docs/source/analisi.md` §5.1 (scale and seeds), §5.5 (metrics) and §7 (which tables and figures the paper has).

Blocked until WS08-T07 and WS09-T05 are `done`. Also confirm before starting that the generators of Table I (WS09-T04), Fig. 1 (WS09-T02) and Fig. 2 (WS09-T03) exist: they are not in `depends_on`. If one is missing, stop and report it in the completion note; do not write a stand-in generator and do not drop the target silently.

## File toccati

- `tools/reproduce.py` (create)
- `tests/tools/test_reproduce.py` (create)
- `experiments/smoke.yaml` (create)
- `docs/reproduce.md` (create)
- `docs/reproduce-reference.sha256` (create)
- `README.md` (modify: add the link in `## Documentation`; create nothing if WS13-T01 has not created the file, and say so in the completion note)

## Test

Pytest names, written before the steps. Tests use stubs injected into `reproduce.main(argv, runner=..., generator=...)` and small files in `tmp_path`; only tests 13, 15 and 16 touch the real repository and pipeline. The test module is loaded by path with `importlib.util.spec_from_file_location`, because `tests/tools/` and `tools/` would otherwise clash on the package name `tools`.

1. `test_list_prints_one_line_per_artefact`: `--list` prints exactly the ids `table1`, `table2`, `table3`, `fig1`, `fig2`, `fig3` in this order, each with its command, and a line `fig4: not reproducible from this repository (needs lab hardware)`.
2. `test_unknown_target_exits_2`: target `table9` exits with status 2 and lists the valid ids.
3. `test_missing_experiment_outputs_trigger_runner_once_per_experiment`: with a test registry where target `t` needs experiments `e1` and `e2` and no outputs exist, the stub runner is called once for `e1`, once for `e2`, then the stub generator once.
4. `test_existing_outputs_are_reused`: when `outputs/e1/0/metrics.json` and `outputs/e1/1/metrics.json` exist for seeds `[0, 1]`, the runner is not called.
5. `test_partial_seed_outputs_count_as_missing`: with seeds `[0, 1]` and only `outputs/e1/0/` present, the runner is called for `e1`.
6. `test_force_reruns_experiments`: `--force` calls the runner even when all outputs exist.
7. `test_check_passes_when_hashes_match_reference`: an artefact file with content `b"abc"` and a reference line `ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad  table2.md` (the SHA-256 of `abc`, written by hand) gives exit status 0.
8. `test_check_fails_on_hash_mismatch`: the same reference and an artefact with content `b"abd"` gives exit status 1 and the message names `table2.md`.
9. `test_check_fails_when_reference_entry_is_missing`: an artefact without a reference line gives exit status 1 with `no reference hash`.
10. `test_report_json_records_git_rev_and_seeds`: after a run, `reproduction-report.json` contains for each experiment its seeds and the content of its `git_rev.txt`, with keys sorted.
11. `test_report_has_no_timestamps_absolute_paths_or_user_names`: the report text contains no `/home/`, no `/Users/`, no drive letter, no value of `getpass.getuser()` and no ISO date; it is byte-identical on a second run.
12. `test_smoke_profile_uses_smoke_config_and_separate_outputs`: with `--profile smoke` the stub runner receives the overrides of `experiments/smoke.yaml` (benchmark scale and seeds) and every path written lies under `outputs/smoke/`, never under the frozen `outputs/<experiment_id>/`; the report states `profile: smoke` and the sentence `not for reporting`.
13. `test_every_target_experiment_has_a_config_file`: for the real registry, every experiment id named by a target has a YAML in `experiments/` whose `experiment_id` equals it.
14. `test_tool_has_no_network_or_remote_git_calls`: parsing `tools/reproduce.py` with `ast`, none of the modules `socket`, `urllib`, `http`, `requests`, `ftplib`, `smtplib` is imported and no call passes a `push`, `remote` or `clone` argument to `subprocess` (pushing to any remote requires explicit human approval, so the tool never does it).
15. `test_smoke_end_to_end_produces_every_artefact`: on the real pipeline, `main(["all", "--profile", "smoke", "--outputs-dir", str(tmp_path)])` exits 0 and every table and figure file of the registry exists and is non-empty.
16. `test_smoke_end_to_end_is_deterministic`: the same call run twice into two directories gives identical SHA-256 for every generated table and figure data file and for the report (bit for bit on the same machine, `01-conventions.md` section 3; for figures in a lossy or timestamped format, the hash is taken over the data file that the WS09 generator writes next to the figure).

## Passi

1. Create the branch `ws13-t02-repro-scripts` from `main` and record `git remote -v`. Do not run any command that writes to a remote: pushing to any remote requires explicit human approval, which this task does not have; if a step seems to need it, stop and report.
2. Collect facts (no value from memory): from the WS08-T07 completion note, the experiment ids, the config path of each, the seeds, the result-freeze record (whether it holds checksums of `metrics.json`, and where); from the WS09-T01 to WS09-T05 notes, the entry point of each generator and the `experiment_id` values each reads; from `ls experiments/` and the WS08-T01 note, how an experiment is run (the public `run_experiment` of `ralmon.eval`, or the run script in `experiments/`); from the builder `--help`, the options that set scale and seed. Keep these facts in a scratch note that is not committed; they become the target registry.
3. Write `tests/tools/test_reproduce.py` with the sixteen tests above (stubs first). Run `pytest tests/tools/test_reproduce.py -q` and watch every test fail because `tools/reproduce.py` does not exist.
4. Implement the CLI skeleton and the target registry (a constant table: target id, paper artefact, experiment ids, generator command, output path). Tests 1, 2 and 13 pass. Fig. 4 is listed as not reproducible; Table I and Fig. 1 have an empty experiment list because they are built from the registry and templates or from a drawing source, not from experiment outputs.
5. Implement experiment provisioning: an experiment counts as present only if `outputs/<experiment_id>/<seed>/metrics.json`, `config.yaml` and `git_rev.txt` exist for every seed of its config; otherwise call the runner; `--force` reruns. Tests 3 to 6 pass.
6. Implement `--check` and `--write-reference`. The reference file has one line per artefact, `<sha256>  <relative path>`, sorted by path. `--write-reference` is used once, after the WS08-T07 freeze, and its diff is reviewed; if WS08-T07 froze checksums of `metrics.json`, `--check` first verifies the frozen `metrics.json` files against that record and reports a mismatch as a different failure from an artefact mismatch. Tests 7 to 9 pass.
7. Implement the report: sorted keys, no timestamps, no absolute paths, git revision read from `git_rev.txt`, profile and seeds. Tests 10 and 11 pass.
8. Implement the smoke profile: `experiments/smoke.yaml` holds the overrides (builder scale arguments as named by the builder `--help`, seeds, and the sentence `smoke profile: not for reporting`); choose the smallest scale for which every experiment of every target runs and each split by patient (train, calibration, test) is non-empty, found by trying, and record the chosen scale and the measured time in `docs/reproduce.md`. Smoke outputs go under `outputs/smoke/`. Tests 12, 15 and 16 pass.
9. Add the AST guard test (test 14) and make it pass; the script never imports a network module and never invokes a remote git operation.
10. Write `docs/reproduce.md`: prerequisites (link to `docs/install.md` if it exists), one table with columns artefact, paper item, command, experiments, generator, output file, measured wall-clock for `smoke` and `full` (measured on the machine used, described by CPU model and memory, not by host name), the rule that paper numbers come only from `outputs/` through these commands, the statement that results are bit-for-bit reproducible on the same machine only and that on another machine differences are reported as observed with no tolerance claimed, the note that `outputs/` is gitignored so the frozen results are regenerated by `full` and not shipped, and the note that Fig. 4 (lab photo and ROS graph, optional) needs the lab hardware and is not part of the release.
11. After the WS08-T07 freeze, run `python tools/reproduce.py all --profile full --write-reference`, review the resulting `docs/reproduce-reference.sha256` line by line against the freeze record, then run `python tools/reproduce.py all --profile full --check`.
12. Add the link to `docs/reproduce.md` in the `## Documentation` section of `README.md` if the file exists. Run `ruff check src tests tools`. Commit on the branch with messages `WS13-T02: <summary>`; the last commit sets `status: done` in this task file. Merge to `main` locally. Do not push (pushing to any remote requires explicit human approval).

## Done when

From the repository root, each command exits 0:

- `pytest tests/tools/test_reproduce.py -q`
- `ruff check src tests tools`
- `mypy src/ralmon`
- `python tools/reproduce.py --list` (six ids and the Fig. 4 line)
- `python tools/reproduce.py all --profile smoke`
- `python tools/reproduce.py all --profile full --check` on the machine that produced the frozen results; the completion note shows its output and the wall-clock time.

Also: `test -f docs/reproduce.md && test -f docs/reproduce-reference.sha256 && test -f experiments/smoke.yaml` exits 0, and `grep -c 'not for reporting' experiments/smoke.yaml` prints 1 or more.
