---
id: WS10-T06
title: Lab results analysis and simulation-video fallback
workstream: WS10-lab-demo
owner: agent
status: blocked
depends_on: ["WS10-T05", "WS08-T01"]
critical_path: false
non_negotiable: false
estimate_pd: 1.5
sources: ["analisi §5.3", "analisi §9 (cut order)", "analisi §5.5", "analisi §5.8", "analisi §10 (3)"]
interfaces: ["02-interfaces.md#metrics"]
review_items: []
---
## Obiettivo

Turn the archived lab runs into `outputs/lab-summary/metrics.json` with the four measures of analisi §5.3 (latency, attribution correctness, task success, intake confirmation via perception) plus a compression-feasibility check, computed by a script from the run directories, and write `hardware/lab_demo/claims.md` stating what the demo does and does not show. This task also carries the fallback of the cut order (`00-master-plan.md` section 7, analisi §9): if WS10-T05 has `outcome: partial` or `cut`, write the storyboard of a simulation video that replaces the missing lab scenarios, and state in the paper wording that a simulation video weakens the robotics fit. The agent prepares the storyboard and wording; recording the video needs the Gazebo GUI and is a human hand-off step written into the storyboard.

## Contesto

- `docs/source/analisi.md` §5.3 (measures), §5.5 (metric definitions), §9 (cut order), §10 objection 3 ("the robot is not needed").
- `docs/plan/workstreams/WS10-lab-demo/outputs/WS10-T05.md` (`outcome`, run table) and `tasks/T04-scenario-scripts.md` (run-directory layout, `expected` block, `lab_config.yaml`).
- `docs/plan/02-interfaces.md#metrics` (`MatchConfig`, `match_events`, `per_class_prf`, `detection_delay_ms`, `attribution_confusion`, `latency_percentiles`).
- `docs/plan/00-master-plan.md` sections 3 (M4) and 7.
- `docs/plan/01-conventions.md` sections 2, 3 and 9 (seeded randomness, tests, outputs layout).

Unblocked when `outputs/WS10-T05.md` exists with `outcome` filled. For `completed` and `partial`, `python -c "from ralmon.eval import MatchConfig, match_events, per_class_prf, detection_delay_ms, attribution_confusion, latency_percentiles"` must exit 0 (`ralmon.eval` comes from WS08-T01, which is not in this task's `depends_on` chain); until then the analysis branch stays blocked. The `cut` branch needs only the fallback documents.

## File toccati

- `hardware/lab_demo/analysis.py` (create): loaders, conversion of a run to `BenchmarkDay`, measures, bootstrap, CLI.
- `tests/hardware/` (modify): `test_lab_analysis.py` and fixtures `fixtures/lab_runs/` (synthetic run directories).
- `hardware/lab_demo/claims.md` (create)
- `hardware/lab_demo/fallback/storyboard.md` (create; only for outcome `partial` or `cut`)

## Test

Pytest tests, written first, on synthetic run directories (test fixture, not real data), with the expected values computed by hand:

- `test_load_run_rejects_missing_factor_or_status`: a run directory whose `config.yaml` lacks the compression factor, or without `run_status.json`, raises.
- `test_invalid_runs_are_reported_not_dropped`: 5 fixture runs (3 completed, 1 invalid, 1 aborted) give `n_runs_valid == 3`, `n_runs_invalid == 1`, `n_runs_aborted == 1`, `n_runs_planned == 5`.
- `test_run_to_benchmark_day_conversion`: a fixture run with 3 sample lines, 2 event lines, 1 latent sample and 1 ground-truth event gives an `ObservedDay` with 3 samples and 2 events sorted by `t_rx_ms`, a `LatentDay` with 1 sample, and one `GroundTruthEvent` with the fixture class and onset.
- `test_detection_delay_and_command_to_alert_use_wall_clock_only`: four runs whose alerts arrive exactly 250 ms after the trigger command give `command_to_alert_ms` percentiles p50, p95, p99 all equal to 250 (constant input, so any percentile method gives the same value); no factor is applied to any latency.
- `test_attribution_confusion_and_abstention_hand_computed`: four fixture runs with injected classes C2, C2, C3, C1 and attributed causes C2, C1, C3, UNDETERMINED give confusion counts `(C2,C2)=1`, `(C2,C1)=1`, `(C3,C3)=1`, `(C1,UNDETERMINED)=1`, `abstention_rate == 0.25` and accuracy among answered alerts 2/3.
- `test_task_success_separates_injected_failures`: four runs where success is expected with outcomes success, success, failure, success give `task_success.rate == 0.75` with counts 3 of 4; a run where the script injects a navigation failure and the task fails is counted as `failure_as_scripted`, not as a system failure.
- `test_intake_confirmation_treats_none_as_unavailable`: 5 runs with scripted intake true and witness observations True, True, False, None, None give detected 2, missed 1, unavailable 2, `rate_when_available == 2/3`, `availability == 3/5` (a `None` is never converted to a miss, `02-interfaces.md#evidencevector` rule).
- `test_compression_feasibility_flags_task_slower_than_window`: nominal robot task duration 20_000 ms against a compressed window of 15_000 ms is flagged with margin -5_000 ms; 10_000 ms against 15_000 ms is not flagged, margin 5_000 ms.
- `test_bootstrap_ci_is_reproducible_for_seed`: same seed gives identical intervals; the CLI refuses to run without `--bootstrap-seed` and `--bootstrap-resamples` (no silent defaults).
- `test_summary_json_has_required_keys`: `metrics.json` has `factor`, `stand_in`, `n_runs_planned`, `n_runs_valid`, `n_runs_invalid`, `n_runs_aborted`, `per_scenario`, `per_class_prf`, `latency`, `attribution_confusion`, `abstention_rate`, `task_success`, `intake_confirmation`, `compression_feasibility`, `bootstrap`.
- `test_analysis_is_deterministic`: two runs of the CLI on the same fixture directories with the same seed write identical `metrics.json` bytes.

Verification checks for the documents:

1. `claims.md` has the headings `## Scope of the demo`, `## What the demo shows`, `## What it does not show`, `## Fallback wording (cut order)`; for outcome `completed` or `partial` also `## Setup statement`, `## Limits carried from the diagnosability matrix`, `## Compression validity`.
2. `claims.md` contains no typed numbers about results; every quantitative statement points to a key of `outputs/lab-summary/metrics.json` or a field of `outputs/WS10-T05.md`.
3. `claims.md` states: technical feasibility demonstration, pre-clinical, stand-in used, compression factor declared, no significance claim at about 10 runs per scenario, presence not identity, silent cuff bias and an informed attacker not detectable by construction (negative controls), and that with a mannequin the intake measure covers the witness path only. Its wording follows the claims reformulations of analisi §4.8 (`01-conventions.md` section 7): no guarantee language, and "specification-level traceability" for the alert text.
4. `storyboard.md` (partial or cut) has the headings `## Purpose and status`, `## Scenes`, `## On-screen elements`, `## Numbers policy`, `## Recording hand-off`, `## Limitation statement`, `## Acceptance checklist`.
5. Every scene cites an existing run directory under `outputs/` produced by WS07 or WS08 (`test -d`), the alert fields shown (tau, kappa, sigma tilde, rho, xi and the verdict state) and the lab scenario it stands in for; scenes the simulation cannot show (for example the physical dispenser) are listed as not shown.
6. `## Limitation statement` contains the sentence "a simulation video weakens the robotics fit" (`00-master-plan.md` section 7) and points to ablation A4 and the latency results of WS07 and WS08 as the robot evidence that remains.
7. For outcome `cut` the storyboard covers at least one scene per class C1, C2, C3 and the two continuity checks as far as WS07-T05 fault injection supports them.

## Passi

1. Read `outputs/WS10-T05.md`; note `outcome` and route the work: `completed` (analysis and claims), `partial` (analysis, claims and storyboard for the missing scenarios), `cut` (claims fallback sections and storyboard only).
2. For `completed` or `partial`: create the fixtures and the tests above; run them and watch them fail.
3. Implement the loaders and the conversion of a run to `BenchmarkDay` (latent from `latent.json`, ground truth from `ground_truth.json`, observed from `events.jsonl`; `patient_id`, `day_index`, `seed`, `care_plan_id` from `config.yaml`).
4. Build `Detection` objects from `alerts.jsonl` (label from the attributed cause) and score with `match_events` using the `MatchConfig` stored in each run's `config.yaml`; compute per-class precision, recall, F1, `detection_delay_ms`, `command_to_alert_ms`, `attribution_confusion`, abstention rate with the functions of `#metrics`, not with local copies. Compute task success, intake confirmation and compression feasibility locally (the `#metrics` contract has no functions for them); the outcome keys come from `robot_task_outcome_key` and `witness_intake_key` of `lab_config.yaml`.
5. Add the seeded bootstrap over runs (resampling runs within scenario) for rates and percentiles, labelled supplementary; counts stay the primary report.
6. Write the CLI: `python hardware/lab_demo/analysis.py --runs outputs --out outputs/lab-summary --bootstrap-seed <int> --bootstrap-resamples <int>`.
7. Run on the real runs; read `metrics.json`; write `claims.md` (checks 1 to 3). Values are cited by key, not typed.
8. For `partial` or `cut`: write `fallback/storyboard.md` (checks 4 to 7). List the human recording steps under `## Recording hand-off`, with output path `outputs/fallback-video/` and a reviewer.
9. Run `ruff check hardware tests`, run the tests, commit `WS10-T06: lab analysis and fallback`.

## Done when

- `test -f hardware/lab_demo/claims.md` and each required heading of check 1 is found with `grep -q`.
- For `completed` or `partial`: `pytest tests/hardware -q` exits 0; `ruff check hardware tests` exits 0; `python hardware/lab_demo/analysis.py --runs outputs --out outputs/lab-summary --bootstrap-seed 0 --bootstrap-resamples 200` exits 0 (the value 200 is only the smoke-test setting; the reported setting is recorded in `metrics.json` under `bootstrap`) and `python -c "import json; m=json.load(open('outputs/lab-summary/metrics.json')); k='factor stand_in n_runs_planned n_runs_valid n_runs_invalid n_runs_aborted per_scenario per_class_prf latency attribution_confusion abstention_rate task_success intake_confirmation compression_feasibility bootstrap'.split(); assert all(x in m for x in k)"` exits 0.
- For `partial` or `cut`: `test -f hardware/lab_demo/fallback/storyboard.md`, its seven headings are found, and `grep -q 'weakens the robotics fit' hardware/lab_demo/fallback/storyboard.md` exits 0.
