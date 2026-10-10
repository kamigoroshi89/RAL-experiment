---
id: WS06-T02
title: B1 static thresholds with simple schedule logic
workstream: WS06-baselines
owner: agent
status: in_progress
depends_on: ["WS06-T01", "WS01-T03", "WS05-T02"]
critical_path: true
non_negotiable: false
estimate_pd: 1.5
sources: ["analisi §5.4 (B1)", "analisi §10 (1)", "analisi §4.1 (templates, decomposition)"]
interfaces: ["02-interfaces.md#detector"]
review_items: []
---
## Obiettivo

Implement `B1StaticThresholds`, the baseline that "raises an alarm on every sample outside the plan's bands, plus simple schedule logic" (analisi §5.4). It receives the same bands and schedules as the proposed method, read from the patient care plan, and no temporal-window structure, no robustness, no uncertainty and no attribution. Its job is to show the value of temporal structure, windows and attribution at equal clinical knowledge (analisi §10 objection 1). Concrete output: `src/ralmon/baselines/b1_static_thresholds.py` and its tests.

## Contesto

- `02-interfaces.md#detector`, and the harness of WS06-T01 in `src/ralmon/baselines/` (`BaselineBase`, `iter_steps`, `AuditedRegistry`, `logged_plan`; read the module docstrings for the timing conventions).
- `02-interfaces.md#template`: `TemplateInstance.param_values` and `anchor_ms` carry the patient's bands and schedule anchors.
- `configs/registry/hypertension.yaml`: the entry names (band, hold threshold, window, dose limit) come from here and never from this file.
- `docs/source/analisi.md` §5.4 row B1, §4.1 (templates range, sched, hold, count) and §10 objection 1.
- Blocked until `WS06-T01` and `WS01-T03` are `done`. It also imports `SignalId` and `EventKind` from `ralmon.signals`: if `WS05-T02` is not done yet, stay blocked (this edge is not in `depends_on`; see the workstream README).

## File toccati

- `src/ralmon/baselines/b1_static_thresholds.py` (create)
- `tests/baselines/test_b1_static_thresholds.py` (create)
- `src/ralmon/baselines/__init__.py` (modify: export `B1StaticThresholds`)

## Test

Write these first. Fixtures use the `stub_registry` and builders from WS06-T01. Test-local values (illustrative, unverified, from analisi §4.1 except the window): band 110 to 140 mmHg (closed), hold threshold 100 mmHg, dose limit 2, schedule window 30 min. Timing for all tests: `step_ms=60_000`, `reorder_delay_ms=0`, `tail_ms=hours(1)` unless stated. Every expected detection has `label=None` and `score=1.0` (B1 is binary: one operating point, documented in the class docstring).

1. `test_b1_band_rule_hand_computed`: BP samples at 1 h = 152, 2 h = 125, 3 h = 105 give detections at `3_600_000` and `10_800_000` only (152 is above 140, 125 inside, 105 below 110).
2. `test_b1_band_limits_are_inclusive`: samples of exactly 110 and exactly 140 give no detection.
3. `test_b1_hold_rule_uses_last_held_bp`: BP 95 at 3.5 h then DISPENSE at 4 h gives a detection at `12_600_000` (band rule on 95) and one at `14_400_000` (hold rule, 95 < 100); a DISPENSE with no BP delivered before it gives no hold detection.
4. `test_b1_schedule_rule_missed_measurement`: SCHED instance with `anchor_ms=hours(6)` and 30 min window, no measurement in `[6 h, 6.5 h]`, gives one detection at `23_400_000` (first step with `t >= anchor + window`).
5. `test_b1_schedule_rule_boundary`: a BP sample at exactly `23_400_000` (window closed) gives no detection; a sample at `23_400_001` gives the detection at `23_400_000`. A `MEASUREMENT` event counts like a BP sample.
6. `test_b1_schedule_rule_waits_for_reorder_delay`: same day with `reorder_delay_ms=120_000`: the detection moves to `23_520_000`.
7. `test_b1_dose_limit_rule_hand_computed`: limit 2, DISPENSE events at 1 h, 2 h, 3 h, 4 h give detections at `10_800_000` and `14_400_000` (trailing count 3, then 4).
8. `test_b1_dose_window_is_left_open_24h`: DISPENSE at 0, 12 h, 25 h gives no detection; DISPENSE at 0, 1 h, 24 h gives none (the event at 0 is outside `(0, 24 h]`); DISPENSE at 0, 1 h, 2 h gives one at 2 h.
9. `test_b1_rule_inactive_without_plan_instance`: a plan with no RANGE instance produces no band detections for out-of-band BP; the same for SCHED, HOLD and COUNT (the plan is the only source of clinical knowledge).
10. `test_b1_excludes_window_and_cross_signal_templates`: a plan containing RESP, SYS and INT instances yields the same detections as the plan without them (B1 has no response, cuff-health or presence logic).
11. `test_b1_ignores_evidence_and_never_labels`: identical output with and without an `EvidenceVector`; all labels `None`.
12. `test_b1_fit_reads_no_days`: after `fit` with train and calibration days, the `AccessLog` shows no reads at all (B1 has no fitted state); `run` works after `fit([], [])`.
13. `test_b1_reads_only_declared_names`: with `AuditedRegistry` and `logged_plan`, the names read during `run` include the five role parameters (band low, band high, hold threshold, schedule window, dose limit) and are a subset of the parameters of the RANGE, HOLD, SCHED and COUNT instances; no `scale_param`, no `priority_param`, no RESP, SYS or INT parameter is read.
14. `test_b1_parameter_names_exist_in_registry_yaml`: each entry name that `b1_static_thresholds.py` references as a string exists in `configs/registry/hypertension.yaml`.
15. `test_b1_is_causal_property` (Hypothesis): detections with `t_ms <= T` are the same for the full day and for the day truncated to inputs with `t_rx_ms <= T`.
16. `test_b1_in_band_only_days_are_silent_property` (Hypothesis): BP samples drawn inside the band, no dispenses, no SCHED instance, give an empty result.

## Passi

1. Verify unblock conditions. Branch `ws06-t02-b1-static-thresholds`; `status: in_progress`.
2. Read `configs/registry/hypertension.yaml` and the WS01 template table; write down (in the module docstring) which registry entry names play the roles band low, band high, hold threshold, schedule window and dose limit. If a role has no entry, stop and report it; do not add a number.
3. Write the 16 tests; run `pytest tests/baselines/test_b1_static_thresholds.py -q`; watch them fail.
4. Implement `B1StaticThresholds(BaselineBase)` with `name = "B1"`. Rules, each active only if the plan holds the matching instance:
   - R1 band: one detection per delivered BP sample outside the closed band, at the delivery step.
   - R2 hold: one detection per delivered DISPENSE when the last delivered BP value is below the hold threshold (no look-back window; no BP yet means no detection).
   - R3 scheduled measurement: for each SCHED instance, at the first step with `t_ms - reorder_delay_ms >= anchor_ms + window`, one detection if no BP sample and no `MEASUREMENT` event with `t_device_ms` in `[anchor_ms, anchor_ms + window]` was delivered. Deliver a step's inputs before evaluating deadlines.
   - R4 dose limit: one detection per delivered DISPENSE that makes the count over `(t - 24 h, t]` exceed the limit (count kept by B1 itself).
   - Not implemented, by design: RESP, SYS, INT, robustness, intervals, forecasting, conformal, attribution (analisi §5.4: B1 measures the value of temporal structure, windows and attribution).
5. Write the class docstring with a section `Hyperparameter selection`: B1 has none and no operating parameter; its recall against false alarms is a single point. Record that rule R2 and R4 are included on purpose (same threshold-type knowledge as the proposed method) and that the choice is audited in WS06-T07.
6. Export from `__init__.py`; run `ruff format`, `ruff check src tests`, `mypy src/ralmon`, `pytest tests/baselines -q`; refactor.
7. Commit `WS06-T02: add B1 static thresholds baseline`; set `status: done`; paste outputs in the completion note.

## Done when

- `pytest tests/baselines/test_b1_static_thresholds.py -q` exits 0, and `pytest tests/baselines -q` still exits 0.
- `ruff check src tests` and `mypy src/ralmon` exit 0.
- `python -c "from ralmon.baselines import B1StaticThresholds"` exits 0.
- `grep -rnE '\b(110|140)\b' src/ralmon/baselines` prints nothing (no clinical constant in `src/`).
- `grep -lE 'LatentDay|GroundTruthEvent' src/ralmon/baselines/b1_static_thresholds.py` prints nothing.

## Notes

### Flag from the WS01-T03 review (orchestrator, 2026-09-30)

Step 2 asks which registry entry plays the schedule-window role and says to stop if a role has no entry. `sched_window` is `unset` in `configs/registry/hypertension.yaml` (WS01-T03) until the clinician review, so this step would stop. Kept `blocked` until ADR-027 (proposed, fixture registry for runs before the clinician review) is decided. Test 14 ("exists in hypertension.yaml") is ambiguous for an unset name.

### ADR-027 accepted (agent, 2026-10-08)

ADR-027 (fixture registry `configs/registry/fixture.yaml`, FIXTURE-ONLY rows, created by WS05-T03) was accepted by gab on 2026-10-08; the flag above is settled in that sense. Literature-anchored values for the clinical registry come from WS01-T09 (ADR-043).
