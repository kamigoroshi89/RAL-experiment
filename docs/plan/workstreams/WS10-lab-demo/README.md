# WS10-lab-demo: Lab demo

## Objective

Show that the monitoring architecture of ADR-003 (ward node plus robot) runs end to end with real hardware in a lab room that simulates a ward room: a bed, a patient stand-in, devices that emit controlled events, a bedside smart dispenser and a real assistive robot. The demo is a technical feasibility demonstration, not a clinical evaluation and not a statistical benchmark (analisi §5, §5.3). It supports the "robot deployment" part of the paper (analisi §7, section V-E) and answers reviewer R3 on validation and on what happens when the robot leaves the room or fails (R3-W1, R3-W2).

Status in the analysis: strongly recommended for RA-L, not strictly indispensable (analisi §5.3, §5.8). In the cut order (`00-master-plan.md` section 7) it is cut second, after WS11, and replaced by a simulation video, accepting that this weakens the robotics fit. WS10-T06 carries that fallback.

### Design decisions shared by all WS10 tasks

These decisions are derived from analisi §5.3 and the contracts. Values that the sources do not fix are recorded by a human in `outputs/WS10-T01.md`.

1. **Patient stand-in.** The default is a mannequin with emulated signals, which avoids the ethics question (analisi §5.3). A research-team member acting as patient, or a healthy volunteer, is allowed only if `outputs/WS00-T06.md` (WS00-admin) permits it. Every result states which stand-in was used. If the stand-in is a mannequin, "intake confirmation via perception" measures the witness path (perception, `EvidenceVector.witness`, INTAKE event), not the behaviour of a real person, and the results say so.
2. **Devices.** Signals come from emulated devices on programmable BLE boards (events fully controllable), plus one commercial device for realism, used in a mode consistent with the ethics decision. The dispenser is built from a microcontroller, a lock, an open sensor and a load cell, and holds placebo candy only. No real medication, no real patient data.
3. **Compressed timeline.** A declared integer factor compresses care-plan time (the analysis' example, 1 hour = 2 minutes, is a factor of 30). Policy: one real clock everywhere; the care plan and the care-plan time entries of the parameter registry are compressed by a documented, reproducible transform (WS10-T04); latency and resource measures are wall-clock and never rescaled. Robot motion, BLE transport and device physics cannot be compressed, so the factor is a validity threat: WS10-T06 reports whether nominal robot task durations fit inside the compressed windows.
4. **Scenarios.** 3 to 5 scripted scenarios per class C1, C2, C3, about 10 repetitions each, that is 90 to 150 runs (analisi §5.3). Candidates come from the injections of analisi §5.1 (3) and the diagnosability matrix of analisi §4.5. The catalogue must include at least one negative control (a row the matrix marks as not distinguishable or only partly distinguishable) and two architecture-continuity checks required by R3-W2: the robot is out of the room while the device stream continues, and the robot heartbeat is lost (loss of a heartbeat is C2 evidence, `02-interfaces.md#ros-2-interfaces`).
5. **Ground truth.** Each run has a scripted ground truth expressed as `GroundTruthEvent` (`02-interfaces.md#trace-schema`), written by the runner before the run, never derived from the monitor output. The monitor never receives it.
6. **Measures** (analisi §5.3): latency (wall-clock p50, p95, p99), attribution correctness including UNDETERMINED and abstention rate, task success, and intake confirmation via perception. Counts per scenario are the primary report; with about 10 runs per scenario no significance claim is made.
7. **Safety gate.** No run in hardware mode starts unless `outputs/WS10-T01.md` records `safety_review_status` as approved or approved_with_conditions. The runner enforces this (WS10-T04). The safety review covers the items of analisi §2 R3 weakness 5 (collisions, infection control, camera privacy, presence versus identity) and the hazard of locking medication (analisi §4.9 item 4). ISO 14971 and ISO 13482 are named there by reviewer R3; they are references to verify, and no compliance claim is made.
8. **Dispense and intake.** DISPENSE comes from the dispenser, INTAKE only from the robot witness (ADR-004). The dispenser reports facts (open edges, content change); it never classifies. The monitor never commands the lock in response to an alert (clinician-in-the-loop, analisi §4.9 item 4).

## Inputs

- `docs/plan/workstreams/WS00-admin/outputs/WS00-T05.md`: availability of the real robot (TIAGo or TIAGo Pro) and ROS 2 packages.
- `docs/plan/workstreams/WS00-admin/outputs/WS00-T06.md`: ethics decision for lab volunteers.
- WS07: hospital world (WS07-T02) that the lab room mirrors; simulated-device message mapping (WS07-T03); robot task layer with witness perception (WS07-T04).
- WS05: `ralmon` monitor, attribution and ROS 2 wrappers (WS05-T08, WS05-T09).
- WS01 and WS02 artefacts read by the runner: `configs/registry/hypertension.yaml` (WS01-T03) and `configs/diagnosability.yaml` (WS02-T05).
- `docs/source/analisi.md` sections listed below.

## Outputs

- Human artefacts (created by the owners, never by agents): `docs/plan/workstreams/WS10-lab-demo/outputs/WS10-T01.md`, `WS10-T02.md`, `WS10-T03.md`, `WS10-T05.md`.
- Hardware sources: `hardware/emulated_devices/` (firmware and BLE gateway bridge, WS10-T02), `hardware/dispenser/` (firmware and wiring, WS10-T03), `hardware/lab_demo/lab_plan/` (floor plan, equipment list, WS10-T01).
- Runner and catalogue: `hardware/lab_demo/` (runner, compression transform, `scenarios/`, `lab_config.yaml`, `compression_map.yaml`) and `tests/hardware/` (WS10-T04).
- Run data, one directory per run following `01-conventions.md` section 9 with experiment id `lab-<scenario_id>`: `outputs/lab-<scenario_id>/<seed>/{config.yaml, git_rev.txt, ground_truth.json, latent.json, commands.jsonl, alerts.jsonl, events.jsonl, run_status.json}`. `outputs/` is never committed, so WS10-T05 records where the raw logs are archived.
- Analysis (WS10-T06): `hardware/lab_demo/analysis.py`, `outputs/lab-summary/metrics.json`, `hardware/lab_demo/claims.md`, and, for the partial or cut outcomes, `hardware/lab_demo/fallback/storyboard.md`.

## Dependencies

- Other workstreams: WS00 (T05, T06), WS07 (T02, T03, T04), WS05 (T08, T09), WS01 (T03), WS02 (T05), WS04 (trace schema types), WS08 (metrics implementation in `ralmon.eval`).
- Downstream: WS09-T06 (optional Fig. 4) consumes the WS10-T05 artefact; WS12 consumes `claims.md` and `outputs/lab-summary/metrics.json`.
- Contract anchors used: `02-interfaces.md#ros-2-interfaces`, `#trace-schema`, `#metrics` (as bound by INDEX); read-only support: `#signals`, `#evidencevector`, `#alert`, `#template`, `#parameter-registry`, `#time-and-units`.
- Important: WS10-T06 needs `ralmon.eval` (WS08-T01), which is not in its `depends_on` chain; its Contesto states the condition that unblocks it.

## Acceptance criteria

1. The four human artefacts exist and contain every field named in their tasks; each task lists a `grep` loop that prints nothing when complete.
2. `outputs/WS10-T01.md` records `safety_review_status` different from `not_approved` before any hardware run, and its hazard table has rows H1 to H9.
3. `python hardware/lab_demo/scenario_runner.py --check-catalogue` exits 0 and reports 3 to 5 scenarios for each of C1, C2, C3, with at least one negative control and both architecture-continuity checks.
4. `pytest tests/hardware -q` exits 0 (runner, compression transform, safety gate, analysis).
5. `outputs/WS10-T05.md` has `outcome` equal to `completed`, `partial` or `cut`. For `completed`, every catalogue scenario has its planned number of valid runs; invalid runs are listed with reasons, never deleted.
6. For `completed` or `partial`: `outputs/lab-summary/metrics.json` exists with latency percentiles, attribution confusion, abstention rate, task success, intake confirmation and the compression-feasibility check, all computed from the run directories by `hardware/lab_demo/analysis.py`. Paper numbers come from this file only.
7. `hardware/lab_demo/claims.md` states the stand-in, the compression factor, the number of runs, and the limits (no clinical validity, no significance claim, silent bias and informed attacker not detectable by construction).
8. For `partial` or `cut`: `hardware/lab_demo/fallback/storyboard.md` exists and states that a simulation video weakens the robotics fit.
9. The forbidden-token scan of the authoring brief (rule 5) finds nothing in `docs/plan/workstreams/WS10-lab-demo/`.

## Source sections

- analisi §5.3 (real robot in the lab), §5.8 (status of the demo), §5.1 (injections, ground truth), §5.2 (simulated devices, latency measurement), §5.5 (metrics).
- analisi §2 R3 weakness 5 (collisions, infection control, camera privacy, ISO 14971, ISO 13482), weakness 2 (robot leaves the room or fails), weakness 4 (dispenser lock as hazard), weakness 1 (no validation).
- analisi §4.5 (diagnosability matrix, threat model), §4.9 items 1, 4, 5 (distributed architecture, safety actions, DISPENSE versus INTAKE).
- analisi §9 item 10 and the cut order; §10 objection 3 ("the robot is not needed").
- `00-master-plan.md` sections 3 (M4) and 7; ADR-002, ADR-003, ADR-004, ADR-020.

## Tasks

| id | title | owner | status | depends_on |
|---|---|---|---|---|
| WS10-T01 | Lab setup plan and safety review | human | blocked | WS07-T02, WS00-T06, WS02-T05 |
| WS10-T02 | Emulated BLE devices on programmable boards | human | blocked | WS10-T01 |
| WS10-T03 | Smart dispenser build (lock, open sensor, load cell, placebo) | human | blocked | WS10-T01 |
| WS10-T04 | Compressed-timeline scenario scripts and runner | agent | blocked | WS07-T04, WS10-T02, WS10-T03 |
| WS10-T05 | Demo runs and data collection on the real robot | human | blocked | WS10-T02, WS10-T03, WS10-T04 |
| WS10-T06 | Lab results analysis and simulation-video fallback | agent | blocked | WS10-T05, WS08-T01 |
