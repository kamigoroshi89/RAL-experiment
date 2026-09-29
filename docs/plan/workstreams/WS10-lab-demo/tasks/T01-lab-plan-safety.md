---
id: WS10-T01
title: Lab setup plan and safety review
workstream: WS10-lab-demo
owner: human
status: blocked
depends_on: ["WS07-T02", "WS00-T06", "WS02-T05"]
critical_path: false
non_negotiable: false
estimate_pd: 1.5
sources: ["analisi §5.3", "analisi §2 R3 weakness 5", "analisi §4.9 (1, 4)", "analisi §4.5", "analisi §5.8"]
interfaces: []
review_items: []
---
## Obiettivo

Fix in one artefact, `outputs/WS10-T01.md`, everything the other WS10 tasks need: the lab room (mirroring one room of the WS07-T02 hospital world), the patient stand-in permitted by the ethics decision, the compression factor and clock policy, the scenario catalogue (3 to 5 scenarios per class C1, C2, C3), the control and log interfaces for the boards and the dispenser, and a written safety review. The review covers the items of analisi §2 R3 weakness 5 (collisions, infection control, camera privacy, presence versus identity) and the hazard of locking medication (analisi §4.9 item 4), with ISO 14971 and ISO 13482 as references to verify, not as claimed compliance. The lab demo is strongly recommended, not indispensable, and second in the cut order (`00-master-plan.md` section 7).

## Contesto

- `docs/source/analisi.md` §5.3 (lab demo), §2 R3 weakness 5 (risks), §4.5 (diagnosability matrix, threat model), §4.9 items 1 and 4.
- `docs/plan/workstreams/WS00-admin/outputs/WS00-T06.md` (ethics decision on volunteers) and `WS00-T05.md` (robot availability).
- `docs/plan/workstreams/WS07-ros2-sim/tasks/T02-hospital-world.md` and the resulting world (the room to replicate).
- `docs/plan/03-decisions.md` ADR-002 (C3 scope), ADR-003 (ward node plus robot), ADR-004 (DISPENSE versus INTAKE).
- `docs/plan/workstreams/WS10-lab-demo/README.md` (shared design decisions 1 to 8).

Unblocked when WS07-T02 is done (hospital world available) and `WS00-T06.md` exists. If `WS00-T05.md` records that no real robot is available, write `robot_platform: unavailable` and hand the cut decision to the project lead; WS10-T05 then records `outcome: cut`.

## File toccati

- `docs/plan/workstreams/WS10-lab-demo/outputs/WS10-T01.md` (create)
- `hardware/lab_demo/lab_plan/` (create): floor plan sketch, equipment list, any notice or consent material.

## Test

Verification checks (a reviewer runs or inspects them):

1. Every key listed in "Done when" is present, one `key: value` line each.
2. `patient_stand_in` is one of `mannequin`, `mannequin_plus_team_actor`, `healthy_volunteer`. If it is not `mannequin`, `ethics_reference` quotes the sentence of `WS00-T06.md` that permits it and names the consent or notice document under `lab_plan/`. If `WS00-T06.md` has no explicit permission, the value must be `mannequin`.
3. `compression_factor` is a positive integer and the file states the equivalence in the form "1 hour = N minutes". The starting point is the analysis example (1 hour = 2 minutes, factor 30). `factor_check` records the dry-drive time of the robot from its home pose to the bedside and states whether it fits inside the compressed measurement window; if the registry file `configs/registry/hypertension.yaml` does not exist yet, `factor_check: deferred to WS10-T05 pre-flight`.
4. `clock_policy` states the chosen policy. Default: one real clock; care plan and care-plan time entries compressed by the WS10-T04 transform; wall-clock latency never rescaled. Any other policy needs a written reason.
5. The scenario catalogue table has rows `C1-nn`, `C2-nn`, `C3-nn` with 3 to 5 rows per class; each row has: description, injection method, scripted ground truth (class, subtype, onset rule), expected attributed cause (C1, C2, C3 or UNDETERMINED), the analisi §4.5 matrix row it comes from, robot present (yes or no), negative control (yes or no), continuity tag (`robot_out_of_room`, `heartbeat_lost` or empty).
6. At least one row is a negative control taken from a matrix row marked not distinguishable or partial (silent cuff bias, informed plausible injection, forged dispense event), and the catalogue contains the two architecture-continuity checks, tagged in the continuity column: `robot_out_of_room` (robot out of the room while the device stream continues) and `heartbeat_lost` (robot heartbeat lost).
7. The hazard table has rows H1 to H9, each with source, mitigation, residual risk, owner and status. H1 to H5 cite analisi §2 R3 weakness 5; H6 cites analisi §4.9 item 4.
8. `standards_checked` has one line for ISO 14971 and one for ISO 13482 with: edition consulted, where the text was obtained, applicability to a lab demo without patients, and the words "no compliance claim". No clause is summarised from memory.
9. `safety_review_status` is one of `approved`, `approved_with_conditions`, `not_approved`; `reviewed_by` names at least the lab safety officer of the institution and the demo lead; conditions (if any) are listed.
10. `no_real_medication: yes` and the candy used is described in `dispenser_requirements`.

## Passi

1. Read `WS00-T06.md`; record the ethics decision and choose `patient_stand_in`. Default to the mannequin. Record `intake_perception_method` for that stand-in: how the robot witnesses INTAKE (for a mannequin, an operator-performed gesture or an emulated intake step) and what the measure does and does not show.
2. Read `WS00-T05.md`; record `robot_platform` (model, software stack, where the robot is stored, who may operate it).
3. Open the WS07-T02 world; choose the room to replicate; measure the lab; place bed, door, patient waypoint and dispenser so that simulation and lab waypoints correspond. Fill `lab_room` and `room_reference_sim_world`.
4. Choose the host layout: `ward_node_host` (RSM and BLE gateway), `ble_gateway`, `runner_host` (the scenario runner runs on the ward node host so that injection time and alert arrival share one clock), and `clock_sync` (method between ward node and robot, plus the measured residual offset).
5. Choose `compression_factor` and `clock_policy` (checks 3 and 4). Choose `monitor_config` (T_s, reorder delay, whether predictive verdicts are evaluated; default: definitive verdicts only) and `match_config` (tolerance, time reference), with a one-line justification each. Do not copy numbers from analisi §4.1; they are illustrative.
6. Build the scenario catalogue from these candidates (analisi §5.1 (3) and §4.5), keeping 3 to 5 per class and the required negative control and continuity checks:
   - C1: hypertensive spike (RANGE violated, coherent channels); non-response with intake witnessed; hypotension below the hold parameter followed by a dispense attempt; measurement refused with robot present and device healthy; double-take (dispenser content confirms).
   - C2: BLE dropout with node transition; cuff error code or detached cuff; robot late to the measurement window (injected navigation delay, no physical obstacle); dispenser sensor bounce (interval under one second, no content change); robot heartbeat lost; silent cuff bias (negative control).
   - C3: replay of earlier measurements; plausible values from a naive attacker (no valid sequence numbers or authentication); plausible values from an informed attacker consistent on all channels (negative control); forged DISPENSE event; simulated presence in front of the camera.
7. Write `device_control_interface`: the commands the runner needs from the boards and the dispenser (emit a sample with a given value and scenario timestamp, drop and restore the link, stuck-at, bias, replay, enter and leave test mode, forge a DISPENSE event, inject a bounce) and the log format (JSON lines with wall-clock time). WS10-T02 and WS10-T03 implement it; WS10-T04 codes against it.
8. Run the safety review with the institution's safety officer. Fill rows H1 to H9:
   - H1 robot and person collision, including who holds the emergency stop and who may abort a run.
   - H2 robot and object collision (bed, stands, dispenser, cables).
   - H3 infection control: surfaces touched by the robot, dispenser, mannequin and candy; cleaning between runs.
   - H4 camera privacy: what the RGB-D stack records, whether raw frames are stored (`data_handling`), retention, who has access, treatment of anyone in view.
   - H5 presence versus identity: the witness confirms presence, not identity; the lab uses one stand-in, so identity errors are out of scope and declared as a limit.
   - H6 locking medication: the lock opens only in the scheduled window, releases without power or has a manual override, and the monitor never commands the lock in response to an alert.
   - H7 placebo and ingestion: no real medication; no human ingests candy unless `WS00-T06.md` permits and allergens and choking risk are handled.
   - H8 robot unavailable: in the lab an operator console receives the escalation that the nurse would receive.
   - H9 electrical, battery and radio hazards of boards and dispenser (generic lab safety, not from the analysis; the institution's rules apply).
9. Consult the text of ISO 14971 and ISO 13482 (analisi §2 R3 weakness 5) through the institution; fill `standards_checked`.
10. Set `safety_review_status`, `reviewed_by`, `reviewed_on` (ISO date). Save attachments under `hardware/lab_demo/lab_plan/`.

## Done when

`docs/plan/workstreams/WS10-lab-demo/outputs/WS10-T01.md` exists and the two loops below print nothing:

```
f=docs/plan/workstreams/WS10-lab-demo/outputs/WS10-T01.md
for k in lab_room room_reference_sim_world patient_stand_in ethics_reference robot_platform ward_node_host ble_gateway runner_host clock_sync compression_factor factor_check clock_policy monitor_config match_config repetitions_per_scenario intake_perception_method dispenser_requirements device_control_interface data_handling standards_checked safety_review_status reviewed_by reviewed_on no_real_medication; do grep -q "^$k:" $f || echo "missing $k"; done
for c in C1 C2 C3; do n=$(grep -c "^| $c-" $f); [ "$n" -ge 3 ] && [ "$n" -le 5 ] || echo "bad scenario count $c"; done
```

and `grep -c '^| H[1-9] ' $f` prints 9, and `grep '^safety_review_status:' $f` does not show `not_approved` when WS10-T05 starts.
