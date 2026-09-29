---
id: WS10-T05
title: Demo runs and data collection on the real robot
workstream: WS10-lab-demo
owner: human
status: blocked
depends_on: ["WS10-T02", "WS10-T03", "WS10-T04"]
critical_path: false
non_negotiable: false
estimate_pd: 4
sources: ["analisi §5.3", "analisi §2 R3 weakness 1", "analisi §2 R3 weakness 2", "analisi §5.5", "analisi §9 (cut order)"]
interfaces: ["02-interfaces.md#metrics"]
review_items: ["R3-W1", "R3-W2"]
---
## Obiettivo

Bring up the ward node and the real robot in the lab room, run the scripted scenarios of the WS10-T01 catalogue (3 to 5 per class C1, C2, C3, about 10 repetitions each, 90 to 150 runs) with the runner of WS10-T04, and archive complete run directories from which WS10-T06 computes latency, attribution correctness, task success and intake confirmation. The runs are the first real-robot evidence for R3-W1 (no validation) and, through the two continuity scenarios, for R3-W2 (what happens when the robot leaves the room or fails). If the demo is cut (cut order in `00-master-plan.md` section 7), the same artefact records `outcome: cut` and WS10-T06 produces the simulation-video fallback.

## Contesto

- `docs/source/analisi.md` §5.3 (measures, repetitions), §2 R3 weaknesses 1 and 2, §5.5 (metric definitions used later).
- `docs/plan/workstreams/WS10-lab-demo/outputs/WS10-T01.md`, `WS10-T02.md`, `WS10-T03.md` (setup, safety status, hooks, dispenser schema).
- `docs/plan/workstreams/WS10-lab-demo/tasks/T04-scenario-scripts.md` (runner CLI, run-directory layout, safety gate).
- `docs/plan/02-interfaces.md#metrics` (what WS10-T06 will compute, so the logs must allow it).
- `docs/plan/00-master-plan.md` section 7 (cut order and the wording "weakens the robotics fit").

Unblocked when `outputs/WS10-T02.md` and `outputs/WS10-T03.md` exist and WS10-T04 is done (`pytest tests/hardware -q` exits 0). Real-robot bring-up (lab map, waypoints, running the WS05-T09 and WS07-T04 stack on the physical robot) has no separate task and is part of this task's estimate; if it cannot be completed inside it, declare `partial` or `cut` instead of extending silently.

## File toccati

- `docs/plan/workstreams/WS10-lab-demo/outputs/WS10-T05.md` (create)
- `outputs/lab-<scenario_id>/<seed>/` (create; gitignored raw run data; the archive location is recorded in the artefact)
- `hardware/lab_demo/lab_plan/photos/` (create, optional): photos and ROS graph export for the optional Fig. 4 (WS09-T06).

## Test

Verification checks:

1. Before the first hardware run the pre-flight checklist is recorded with dates and results: emergency stop tested, abort tested, room walk-through against hazard rows H1 to H9 of WS10-T01, all scenarios run in `--mode dry-run` without error, dry-drive timing of the robot compared with the compressed windows, camera settings as in `data_handling` of WS10-T01.
2. `compression_map_confirmed_by` names the person who confirmed the classification of `ms` registry entries proposed in `hardware/lab_demo/compression_map.yaml`; any change is committed before the runs.
3. The clock offset between ward node and robot is measured and recorded with the method used; the runner runs on the ward node host.
4. One code revision for all runs: `cat outputs/lab-*/*/git_rev.txt | sort -u | wc -l` prints 1. If a defect forces a code change, earlier affected runs are marked `invalid` with reason `code revision` and the affected scenarios are rerun.
5. The scenario order is randomised with a recorded seed (`run_order_seed`) so that drift of the lab conditions is not confounded with a class.
6. Every run directory contains the eight files of the WS10-T04 layout (`config.yaml`, `git_rev.txt`, `ground_truth.json`, `latent.json`, `commands.jsonl`, `alerts.jsonl`, `events.jsonl`, `run_status.json`).
7. Invalid or aborted runs are kept, not deleted, with `status` and `reason` in `run_status.json`; the run table gives planned, valid, invalid and aborted counts per scenario. For `outcome: completed`, valid equals planned for every scenario.
8. Both continuity scenarios (`robot_out_of_room`, `heartbeat_lost`) and at least one negative control were run.
9. Safety incidents, near misses and emergency-stop uses are listed (`incidents: none` if none). After any incident the run day stops and the safety officer named in WS10-T01 reviews before more runs.
10. Raw logs are archived outside git with a checksum manifest (`raw_log_archive`), because `outputs/` is never committed.
11. If photos are taken, the artefact states who or what is in them and, if any person is, the consent given; no photo shows raw camera frames beyond what `data_handling` allows.
12. If `outcome` is `partial`, the missing scenarios and reasons are listed; if `cut`, `decision_owner`, `decision_date` and `cut_reason` are filled and the reason cites the cut order.

## Passi

1. Read the three artefacts of WS10-T01, T02, T03; confirm `safety_review_status` is `approved` or `approved_with_conditions` and read the conditions.
2. Bring up the stack in the lab: map the room, set the bed and door waypoints to those of `room_reference_sim_world`, start the ward node (RSM, attribution, event manager, watchdog, gateway bridge) and the robot side (heartbeat, task layer, witness perception). Record software revisions in `robot_platform_used`.
3. Run the pre-flight (check 1), the clock-offset measurement (check 3) and the confirmation of the compression map (check 2). Fix `run_order_seed`.
4. For every run: reset devices and dispenser (refill placebo candy), robot at its home pose, stand-in in position; start recording the `/ralmon/*` topics with rosbag2 (no raw camera frames unless `data_handling` permits); start the runner in hardware mode with `--scenario <id> --reps 1 --seed <seed> --out outputs`; the operator stays within reach of the emergency stop and aborts on any hazard; when the run ends, read `run_status.json` and note the outcome.
5. Repeat in the randomised order until every scenario has its planned valid runs (about 10 each). Never edit a run directory by hand.
6. After the last run, verify checks 4, 6 and 7 with the commands in "Done when"; archive the raw logs and write the checksum manifest.
7. Write `outputs/WS10-T05.md` with the fields below. If the demo was cut, fill only `outcome`, `decision_owner`, `decision_date`, `cut_reason` and write `not applicable` in the other fields.
8. Optional: photos and a ROS graph export for Fig. 4 (check 11).

## Done when

`docs/plan/workstreams/WS10-lab-demo/outputs/WS10-T05.md` exists and the following prints nothing (for `outcome: cut` the other fields read `not applicable`):

```
f=docs/plan/workstreams/WS10-lab-demo/outputs/WS10-T05.md
for k in outcome decision_owner decision_date cut_reason git_rev catalogue_version compression_factor patient_stand_in robot_platform_used compression_map_confirmed_by clock_offset preflight_checklist run_order_seed incidents deviations raw_log_archive operators; do grep -q "^$k:" $f || echo "missing $k"; done
grep -Eq '^outcome: (completed|partial|cut)$' $f || echo "bad outcome"
```

For `outcome: completed` or `partial`, this also prints nothing (the run table lists every catalogue scenario):

```
for s in $(python hardware/lab_demo/scenario_runner.py --list-ids); do grep -q "^| $s " $f || echo "no run table row $s"; done
```

For `outcome: completed`, additionally every run-table row has valid runs equal to planned runs, `cat outputs/lab-*/*/git_rev.txt | sort -u | wc -l` prints 1, and `for d in outputs/lab-*/*/; do for x in config.yaml git_rev.txt ground_truth.json latent.json commands.jsonl alerts.jsonl events.jsonl run_status.json; do test -f $d$x || echo "missing $d$x"; done; done` prints nothing. The run table has the columns `scenario_id | planned | valid | invalid | aborted`.
