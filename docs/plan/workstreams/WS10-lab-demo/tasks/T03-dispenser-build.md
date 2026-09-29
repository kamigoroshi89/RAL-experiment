---
id: WS10-T03
title: Smart dispenser build (lock, open sensor, load cell, placebo)
workstream: WS10-lab-demo
owner: human
status: blocked
depends_on: ["WS10-T01"]
critical_path: false
non_negotiable: false
estimate_pd: 3
sources: ["analisi §5.3", "analisi §4.5", "analisi §4.9 (4, 5)", "analisi §2 R3 weakness 4"]
interfaces: []
review_items: []
---
## Obiettivo

Build a bedside smart dispenser for the lab from a microcontroller, a lock, an open sensor and a load cell, loaded with placebo candy only, that reports DISPENSE events with the facts the attribution layer needs to tell a patient double-take from a sensor bounce: every open edge, the interval since the previous edge and the change of content measured by the load cell. Add two test modes for the scenarios (forged DISPENSE event, injected bounce). Output: firmware and wiring under `hardware/dispenser/` and the artefact `outputs/WS10-T03.md`.

## Contesto

- `docs/source/analisi.md` §5.3 (dispenser build), §4.5 (matrix rows for double-take, bounce, forged dispense), §4.9 items 4 and 5 (safety actions are hazards; DISPENSE is not INTAKE), §2 R3 weakness 4.
- `docs/plan/workstreams/WS10-lab-demo/outputs/WS10-T01.md` (`dispenser_requirements`, `device_control_interface`, hazard rows H6, H7, H9).
- `docs/plan/workstreams/WS10-lab-demo/tasks/T02-emulated-devices.md` (the gateway bridge that will forward the dispenser frames as `EventKind.DISPENSE` events).
- `docs/plan/03-decisions.md` ADR-004 (DISPENSE versus INTAKE).
- `docs/plan/02-interfaces.md#trace-schema` (`Event` fields; `payload` values are float, int, str or bool).

Unblocked when `outputs/WS10-T01.md` exists with `safety_review_status` not equal to `not_approved`. The integration test with the bridge needs WS10-T02; if the bridge is not ready, record `integration_test: deferred to WS10-T05 pre-flight`.

## File toccati

- `docs/plan/workstreams/WS10-lab-demo/outputs/WS10-T03.md` (create)
- `hardware/dispenser/firmware/` (create)
- `hardware/dispenser/wiring/` (create): wiring diagram, parts list, photos.
- `hardware/dispenser/bench_logs/` (create)

## Test

Verification checks:

1. The dispenser holds placebo candy only; `no_real_medication: yes`. It is described as a bedside device, not a wearable.
2. Bench table rows B1 to B6, each with trials, passed and a log path:
   - B1: every open and close of the lid is reported as one DISPENSE event with a timestamp.
   - B2: removal of one candy is detected by the load cell, in a repeated test of about 10 trials (the repetition count of analisi §5.3); trials and detections are written down.
   - B3: two open edges less than one second apart are both reported, each with the interval since the previous edge and the content change; the dispenser does not classify them (analisi §4.5: bounce means interval under one second and no content change).
   - B4: test mode `forge_dispense` produces a DISPENSE event without a physical opening; the transmitted frame does not reveal the test mode, while the test log records it (the monitor must never see ground truth).
   - B5: fail-safe: with power removed the lock is in the state declared in `fail_safe_behaviour` and a person can still reach a due dose (manual override tested).
   - B6: `timestamp_resolution_ms` is measured and is well below one second, so that sub-second intervals are resolvable.
3. `lock_policy` states when the lock is open and closed (authorised window supplied by the runner or by an internal compressed schedule) and confirms that no alert or monitor output can lock the dispenser (analisi §4.9 item 4, hazard H6 of WS10-T01).
4. `event_schema` lists every payload key of a DISPENSE event with type and unit, and includes at least the interval since the previous open edge and the content change before and after.
5. `event_authentication` states whether events are authenticated; if yes, how the bridge verifies them, so that the `auth` signal and the forged-event scenario (analisi §4.5: partial detection) can be interpreted.
6. `safety_signoff` cites rows H6, H7 and H9 of `outputs/WS10-T01.md` and is signed by the lab safety officer named there.
7. The firmware directory builds from a clean checkout following the instructions in its own README file; `firmware_git_rev` is recorded.

## Passi

1. Read `outputs/WS10-T01.md`, in particular `dispenser_requirements` and rows H6, H7, H9.
2. Choose and record the parts: microcontroller, lock type, open sensor type, load cell type. Record the choice and reason in the artefact; no default is assumed.
3. Assemble the dispenser; draw the wiring diagram; take photos; store them under `hardware/dispenser/wiring/`.
4. Calibrate the load cell with known placebo counts; record the procedure and results (`calibration_record`).
5. Write the firmware: edge detection with timestamps, content change, DISPENSE frames with the schema of check 4, lock policy of check 3, fail-safe behaviour, event authentication if chosen.
6. Add the test modes `forge_dispense` and `inject_bounce` (two open edges within one second, no content change), enabled only by the control interface of WS10-T01 and logged only in the test log.
7. Run bench tests B1 to B6 and store the logs under `bench_logs/`.
8. Run the integration test with the gateway bridge of WS10-T02: a physical opening appears as `EventKind.DISPENSE` on `/ralmon/events` with the payload keys of `event_schema`.
9. Ask the lab safety officer to sign row H6, H7, H9 items (`safety_signoff`).
10. Write `outputs/WS10-T03.md` and commit with `WS10-T03: smart dispenser firmware and build record`.

## Done when

`docs/plan/workstreams/WS10-lab-demo/outputs/WS10-T03.md` exists, the loop below prints nothing, `grep -c '^| B[1-6] '` prints 6 and each log path in the bench table exists (`test -f`):

```
f=docs/plan/workstreams/WS10-lab-demo/outputs/WS10-T03.md
for k in mcu_model lock_type open_sensor_type load_cell_type calibration_record event_schema timestamp_resolution_ms lock_policy fail_safe_behaviour test_modes event_authentication placebo_description no_real_medication integration_test safety_signoff firmware_path firmware_git_rev known_limitations; do grep -q "^$k:" $f || echo "missing $k"; done
```

and `grep '^no_real_medication:' $f` shows `yes`.
