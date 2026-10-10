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

### Completion note (worker, 2026-10-10; status left `in_progress` for the reviewer)

Changed: `src/ralmon/baselines/b1_static_thresholds.py` (new: `B1StaticThresholds`, `B1RunStats`, `ROLE_PARAMETERS`), `src/ralmon/baselines/__init__.py` (export), `src/ralmon/baselines/_stubs.py` (the `B1StaticThresholds` placeholder removed; not in "File toccati" but the stub must go for the export), `tests/baselines/test_b1_static_thresholds.py` (new, 43 tests: the 16 of the task plus the ones below). Commits: `WS06-T02: add failing tests` (red: 41 failed), the implementation, the pins of the blind spots, a layering fix (the window alignment is checked locally; `ralmon.monitor.parameters` is not a package root, `tests/test_layering.py` caught the first version). No missing dependency edge beyond the one in the WS06 README (`SignalId`, `EventKind` from `ralmon.signals`). Step 2: all five roles have an entry in `configs/registry/hypertension.yaml` as a SET entry (`sched_window` is 3 600 000 ms since WS01-T09; the flag of 2026-09-30 is settled): band low `bp_band_low`, band high `bp_band_high`, hold threshold `bp_hold_threshold`, schedule window `sched_window`, dose limit `dose_max_24h`. They are listed in the module docstring and in `ROLE_PARAMETERS`; the numbers are nowhere in `src/`.

**Deviations from the task text, each with its reason.**
1. The constructor is `B1StaticThresholds(*, timing, registry=None, access_policy=None, access_log=None, read_log=None)` (keyword-only, like B3). The registry is optional and is read only for a name that a plan instance leaves out (the proposed method does the same, ADR-047 (g)); a name that neither the plan nor the registry gives is a `PlanFeasibilityError` that names it, never a silent switch-off. The task text does not say whether B1 takes a registry; test 13 ("with `AuditedRegistry` and `logged_plan`") and the T07 fixtures suggest it does. The stub registry of the fixtures has no `sched_window`, so the tests carry the window in the plan.
2. Where the values live in the plan: RANGE, HOLD and COUNT from the parameter record (the instance with `anchor_ms` None, at most one per template; a second one, or an anchored RANGE or HOLD, is a `PlanFeasibilityError`, as for B3); an anchored COUNT instance (the day-end obligation) is ignored; SCHED is read per anchored instance, each with its own window (an anchor outside the day of the run is not checked: empty carry-over, ADR-061). The task text says "the matching instance" without saying which; this is the convention of B3, B5 and the monitor.
3. The lateness rule of the grid of B3 and B5 (and of the monitor) is applied to the inputs B1 uses (an input received after its step is final is dropped and counted in `run_stats.late_inputs`). The task text does not mention it; without it B1 would use information the monitor discards (asymmetry (a) of `base.py`), which is not "equal information". Tests: `test_b1_drops_a_late_input_like_the_monitor` (boundary included; the mutant `< final` was run and is killed), `test_b1_schedule_rule_late_measurement_gets_no_credit`.
4. B1 extends the run to its own last SCHED deadline plus `D`, so that R3 does not depend on `tail_ms` or on `plan.schedule` (with an empty schedule and `tail_ms=0` the harness would stop before the deadline and B1 would be silent for a reason that has nothing to do with the method). Test: `test_b1_schedule_rule_decides_even_if_the_plan_schedule_is_shorter`.
5. The window must be a non-negative integer multiple of `step_ms` (the alignment rule of the monitor, docs/formal/01 section 3.6); a misaligned value is a `PlanFeasibilityError`.
6. Beyond the task: `B1StaticThresholds.run_stats` (`B1RunStats`: `rules_active`, `late_inputs`, `non_finite_samples`, `schedule_checks`), so that a caller can tell a quiet day from a vacuous baseline (see the finding on the plan below); a non-finite pressure is not a reading (no alarm, not the last pressure, no credit for R3); an input stamped before the start of its day raises no alarm but is a delivered value (last pressure for R2, a dose for R4), as in B3.
7. Test 14 is implemented as: every `ROLE_PARAMETERS` name is a SET entry of `hypertension.yaml` (an `unset` name does not count), and every string constant of the module that looks like a registry name is one of them (AST scan).

**What B1 does and does not see (fairness statement).** Sees: pressure samples, MEASUREMENT and DISPENSE events (shared causal iterator, lateness rule of the grid), the band, hold threshold, schedule window and dose limit from the plan (registry for omitted names), the anchors of the SCHED instances. `access_log.records` and `access_log.denied` are empty on a normal run (`test_b1_reads_only_declared_names`, `test_b1_fit_reads_no_days`); the read set is the five role names. Does not see, by design: RESP, SYS, INT, the robot channels, evidence, scale, priority, normalisation, intervals, verdict states, forecaster, calibrator, attribution, the physiological bounds. Output: binary, one operating point, `score` 1.0, `label` None; two rules firing at one step are two items (a `Detection` has no template field).

**Findings (each pinned by a test; none is fixed here, all need a decision).**
- F-B1-1 (blind spots by construction, pinned by `test_b1_cannot_see_response_cuff_and_integrity_violations`). For RESP, SYS and INT the monitor reports VIOLATED on three hand-built days and B1 is silent with every threshold rule active. So on the system class (C2) and on the integrity class (C3) the comparison "ours against B1" mixes the value of the specification with the absence of the templates. WS08-T02 must report B1 per class and say so. This is the analogue of the INT and SYS hole of B3, but for B1 it is the intended design (analisi §5.4), not an artefact of an entry point.
- F-B1-2 (two threshold-type conditions outside the task text, pinned by `test_b1_blind_spots_against_the_monitor_are_pinned`). (a) The HOLD template also needs a measurement in the look-back window before the dispense (the monitor reports a dispense 12 h after the last pressure, B1 does not: R2 has no window, as the task prescribes). (b) The COUNT template has a day-end obligation (`dose_min_day_end`, a missed dose); B1 knows only the upper limit. Both are threshold-type knowledge that the proposed method has, so a reviewer could call B1 weaker than a fair static-threshold baseline. I followed the task text (R2 "no look-back window", R4 the limit only, test 13 lists five role parameters). DECISION FOR GAB: keep as is (and report B1 as "minimal threshold baseline"), or add R2' (a dispense with no pressure in `hold_lookback`) and R5 (day-end count below `dose_min_day_end`), which needs two more role names and test 13 changed. Until decided, WS08-T02 must not present B1 recall on missed doses and on stale or absent measurements as "equal clinical knowledge".
- F-B1-3 (vacuity risk; needs WS04-T11 and WS08-T01). Test 9 makes a rule active only if the plan holds the matching instance. The plan that the monitor needs lists only the static instances (SCHED ticks, the day-end COUNT); the parameter records (RANGE, HOLD, COUNT with `anchor_ms` None) are optional for it. If the care plans written by the benchmark builder (WS04-T11) carry no records, B1 runs R3 only and is a straw man by accident, while B3 and B5 still evaluate all their templates from the registry. Check `B1StaticThresholds.run_stats.rules_active == ("R1", "R2", "R3", "R4")` on the real plans (WS06-T07 can assert it on the benchmark fixture), and make the builder write the three records, or decide that B1 should fall back to the registry for a template with no record (that changes test 9).
- F-B1-4 (asymmetries inherited from the harness, pinned): no deduplication (`test_b1_does_not_deduplicate_inputs`: a pressure delivered twice is two alarms, two doses delivered twice are four, so B1 raises a dose alarm that the monitor does not); a deadline after midnight is detected on the next day where the per-day monitor ends PENDING (`test_b1_schedule_rule_detects_after_midnight_where_the_monitor_ends_pending`; the open decision of WS06-T04 applies to B1 as well); B1 does not check the approved range of a per-patient value (the monitor rejects such a plan); a pressure outside the physiological bounds is an ordinary out-of-band value for B1.
- Agreement with the monitor where B1 has the rule: `test_b1_threshold_rules_agree_with_the_monitor` (RANGE, HOLD, COUNT limit, SCHED on a hand-built day, fixture registry F0 read through the registry fallback, `D = 0` and 2 steps): B1's detection times equal the first VIOLATED record of each instance plus `D`.

**Mutants run and killed** (copies of the source, restored): band lower bound exclusive; hold `<=`; dose window closed on the left; `>=` for the limit; deadline with `>`; window open at either end; no pre-day guard; R3 without the extension; events of every kind counted; lateness off by one in both directions; delay missing from the lateness rule. One mutant that survived was a no-op (`and True`).

**Verification (exit codes).** `pytest tests/baselines/test_b1_static_thresholds.py -q`: 0 (43 passed). `pytest tests/baselines -q`: 0 (189 passed). `ruff check src tests`: 0. `ruff format --check src tests`: 0. `mypy src/ralmon`: 0. `python -c "from ralmon.baselines import B1StaticThresholds"`: 0. `pytest tests/test_public_api.py -q`: 0. `grep -rnE '\b(110|140)\b' src/ralmon/baselines`: no output. `grep -lE 'LatentDay|GroundTruthEvent' src/ralmon/baselines/b1_static_thresholds.py`: no output. Full `pytest -q`: 0 (5631 passed, 1 skipped). `python3 tools/check_plan.py`: 0.
