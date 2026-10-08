# 09 Worked patient-day: a hand-computed day that replaces the workshop Table I

Document WS01-T08, part 2 of 2 (part 1 is `docs/formal/08-consistency-review.md`). It replaces the table of numbers of the workshop paper (analisi §4.6) with one patient-day that is computed by hand from the formal documents `01` to `07`, row by row, with the calculation shown. Its machine-readable form is `docs/formal/golden/patient-day.yaml`, which carries the observed day in milliseconds, the expected `VerdictRecord` fields at each decision instant, the expected alerts (all twelve fields of `Alert` and the six of `Explanation`, with `caused_by` and `root_cause_of`) and the ranking. Validation in this project is technical and pre-clinical. Every number below is fixture arithmetic (fixture registry F0 of the WS01 README, not the clinical registry) or an analisi example labelled "illustrative, unverified" (ADR-020); the values of registry 0.2.0 are not used. Nothing in this document is a clinical claim, and nothing is clinically validated. The specification is evaluated on the observed trace only: no row reads a latent trace or a ground-truth event.

How the numbers were obtained. Each number was computed by hand with the calculation shown in the bullet lists of section 2, recomputed once, and then reproduced by an independent scratch script (not committed, kept under `/tmp`) that implements the interval semantics of `05` (sections 2.2, 2.3 and 3.4), the bodies of the templates of `02` (sections 1.5, 3.1 and 4), the normalisation of `04` (section 2.1), the rho of `06` (sections 2.3 and 3.2), the ranking key of `04` (section 4.2) and the decision table of `docs/models/attribution-rule.md`. The script does not use the closed-form table of `05` section 2.3: it evaluates the bodies by structural recursion over determined and open positions. It reproduces 21 of the 21 non-predictive verdict cases of `verdicts.yaml`, 26 of 26 cases of `templates.yaml`, and all 32 records, the six alerts and the ranking of this day. The outcome is in `08` section 3.

## 1 Scenario and fixture

### 1.1 Fixture, conventions and sources

- Fixture registry F0 (identical to the table of the WS01 README and to the `fixture_registry` of `templates.yaml`; the rows used are under `f0_rows` in the golden file), `step_ms` 60000 (`T_s`), `reorder_delay_ms` 0 (`D`), `evidence_grace_ms` 0. Scales and priorities are F0 rows: `scale_range` 20 mmHg, `scale_sched` 1800000 ms, `scale_hold` and `scale_resp` 20 mmHg, `scale_sys` 30000 ms, `scale_int` 300000 ms, `scale_count` 1 dose; `priority_hold` 1, `priority_range` 2, `priority_sched` 3, `priority_count` 2, `priority_resp` 2, `priority_sys` 3, `priority_int` 3 (1 is the highest). `priority_count`, `priority_resp`, `priority_sys` and `priority_int` and the scales of `hold`, `resp`, `sys` and `int` are FIXTURE-ONLY.
- Time: a clock label `hh:mm` is `t_ms = (60*hh + mm) * 60000` (ADR-017); the grid step of a label is `t_ms / 60000`; an input with device time `t` is visible at the step `ceil(t / 60000)` (ceiling rule, `01` section 3.3). The day has 1440 steps; 24:00 is the closing step `K = 1440` (86,400,000 ms).
- Normalised values are `clip(x / s, -1, 1)` with `clip(+inf) = 1` and `clip(-inf) = -1` (`04` section 2.1). Raw values are in the unit of the template. "Robustness" is used only for STL semantics; the normalised value is called severity.
- Verdict states: PENDING, PREDICTED_VIOLATION, VIOLATED, SATISFIED. DISPENSE (the dispenser opened) is not INTAKE (verified by the robot). An alert is the output tuple; a violation is a violated sub-formula; the attributed cause is kappa (C1, C2, C3, UNDETERMINED). The sub-formula names follow `02` section 3.1.
- Sources used for each part: instance semantics and bodies `02` sections 1.5, 2 and 4; intervals, tie rule, early decision, state machine `05` sections 2 to 4, 7 and 11; rho `06` sections 2 and 3; alert fields, lifecycle and cascades `07` sections 1.3 to 1.8; the attributed causes `docs/models/attribution-rule.md` (the worked cases W-01, W-06, W-08 and W-11 give the evidence vectors used) and `docs/models/evidence-channels.md`.

### 1.2 The observed day (what the monitor receives)

Everything the monitor receives is the plan of section 1.3, the inputs below and the availability of the robot channels. `seq` is the device sequence number. The cuff messages (bp, cuff_health, inflation_ms and the measurement event of one measurement) share one `seq`. The 20:32 message is an informed replay (hypothesis H-W9): the monitor cannot tell it from a genuine one.

| Time | t_device_ms | Input | Value or payload | seq |
|---|---|---|---|---|
| 06:50 | 24600000 | event `schedule_tick` (care_plan) | tick_kind measure | none |
| 06:52 | 24720000 | sample `bp` | 138 | 101 |
| 06:52 | 24720000 | sample `cuff_health` | 1 | 101 |
| 06:52 | 24720000 | sample `inflation_ms` | 45000 | 101 |
| 06:52 | 24720000 | event `measurement` (cuff) | none | 101 |
| 06:58 | 25080000 | sample `presence` | 1 | none |
| 06:58 | 25080000 | event `robot_task` (robot) | task observe, outcome success, identity_confirmed True | none |
| 06:59 | 25140000 | sample `presence` | 0 | none |
| 07:00 | 25200000 | event `dispense` (dispenser) | none | 200 |
| 07:01 | 25260000 | sample `presence` | 1 | none |
| 07:01 | 25260000 | event `intake` (robot) | none | none |
| 07:03 | 25380000 | sample `presence` | 0 | none |
| 09:00 | 32400000 | event `schedule_tick` (care_plan) | tick_kind measure | none |
| 12:00 | 43200000 | event `schedule_tick` (care_plan) | tick_kind measure | none |
| 12:24 | 44640000 | sample `bp` | 152 | 102 |
| 12:24 | 44640000 | sample `cuff_health` | 1 | 102 |
| 12:24 | 44640000 | sample `inflation_ms` | 45000 | 102 |
| 12:24 | 44640000 | event `measurement` (cuff) | none | 102 |
| 20:30 | 73800000 | event `schedule_tick` (care_plan) | tick_kind measure | none |
| 20:32 | 73920000 | sample `bp` | 152 | 103 |
| 20:32 | 73920000 | sample `cuff_health` | 1 | 103 |
| 20:32 | 73920000 | sample `inflation_ms` | 45000 | 103 |
| 20:32 | 73920000 | event `measurement` (cuff) | none | 103 |
| 21:00 | 75600000 | sample `auth` | 1 | 201 |
| 21:00 | 75600000 | event `dispense` (dispenser) | none | 201 |
| 21:02 | 75720000 | sample `auth` | 1 | 202 |
| 21:02 | 75720000 | event `dispense` (dispenser) | none | 202 |
| 22:30 | 81000000 | event `schedule_tick` (care_plan) | tick_kind measure | none |
| 22:35 | 81300000 | sample `bp` | 132 | 104 |
| 22:35 | 81300000 | sample `cuff_health` | 1 | 104 |
| 22:35 | 81300000 | sample `inflation_ms` | 45000 | 104 |
| 22:35 | 81300000 | event `measurement` (cuff) | none | 104 |

Availability of the robot channels `presence` and `intake` (`channels_unavailable` in the golden file): unavailable until 06:57, available from 06:58 to 07:04, unavailable from 07:05 to 24:00. An unavailable channel is `None`, never a value of zero, and the instances that read it keep the position open (`01` section 3.5).

What the scenario is, for the reader, is not an input of the monitor: the cuff process is killed at 08:56 and restarted at 11:20 (a lapse of liveliness, not a lifecycle transition); the reading of 12:24 is a hypertensive reading with every channel coherent; the 20:32 message is an informed replay of the 12:24 reading with fresh metadata while the genuine message does not reach the gateway; the 21:02 opening of the dispenser is a second, unscheduled one that a double take by the patient and a repeated dispenser signal would both explain. These intended causes are in `scenario_description` of the golden file and are used only to compare with the attributed cause.

### 1.3 The plan and its feasibility checks

`CarePlan.schedule` (with the tick kind that finding TG-1 of `02` proposes): measurement ticks at 06:50, 09:00, 12:00, 20:30 and 22:30 and dispense ticks at 07:00 and 21:00. The static instances are the five SCHED instances of the measurement ticks and the day-end COUNT instance. The plan passes the load checks of `02` section 5.4:

| Check | Statement (`02` section 5.4) | Result for this plan |
|---|---|---|
| F1 alignment | `sched_window`, `hold_lookback`, `int_window`, `delta1`, `delta2` and `delta2 - delta1` are multiples of `step_ms`; `T_day` is a multiple of `step_ms` | 1800000 / 60000 = 30; 3600000 / 60000 = 60; 300000 / 60000 = 5; 3600000 / 60000 = 60; 10800000 / 60000 = 180; (10800000 - 3600000) / 60000 = 120; 86400000 / 60000 = 1440: all integers |
| F2 HOLD | a measurement tick in `[a - hold_lookback, a)` for each dispense tick `a` | 07:00: tick 06:50 is in [06:00, 07:00); 21:00: tick 20:30 is in [20:00, 21:00) |
| F3 RESP | a measurement tick in `[a + delta1, a + delta2]` for each dispense tick `a` | 07:00: tick 09:00 is in [08:00, 10:00]; 21:00: tick 22:30 is in [22:00, 24:00] |
| F4 INT | a robot visit covers `[a - int_window, a]`, or the dispense is authenticated | 07:00: the visit 06:58 to 07:05 covers [06:55, 07:00]; 21:00: the dispense is authenticated (`auth`) |
| F5 COUNT | at most `dose_max_24h` dispense ticks in any 24 h window and at least `dose_min_day_end` in the day | two dispense ticks in the day: 2 <= 2 and 2 >= 2 |
| F6 registry | every name resolves, scales positive, priorities integers | F0 rows: all names present, scales 20, 1800000, 1, 20, 20, 30000, 300000 > 0, priorities 1 to 3 |
| F7 day boundary | list the instances whose decision step is after 24:00 | none from the plan; the unscheduled dispense of 21:02 creates one (RESP, decision step 1442) |

The unscheduled dispense of 21:02 is not in the plan: INT, HOLD and COUNT decide it at once and no robot obligation was announced for it (`02` section 5.3, item 2). Two ticks closer than `sched_window + step_ms` would change the severity of a SCHED alert (hypothesis AH-23 of `07`); the measurement ticks of this plan are at least 2 h apart.

### 1.4 Hypotheses the day relies on

Every hypothesis is listed; none is hidden. The ones marked with a document id are taken from that document.

| Id | Hypothesis |
|---|---|
| H-W1 | Inputs arrive on time: t_rx_ms equals t_device_ms, reorder_delay_ms is 0, no late input, no future stamp, no jitter. |
| H-W2 | The plan passes the feasibility checks F1 to F7 of 02-templates.md section 5.4 (09 section 1.3 lists them). |
| H-W3 | First day of the patient: no dispense in the 24 h before 00:00 (empty history, H-hist of 05 section 2.1; 01 section 5.5). |
| H-W4 | At most one measurement event and one sample of each of bp, cuff_health, inflation_ms per grid bin (A0), and each measurement event carries its own samples (H-pair); no standalone pressure sample. |
| H-W5 | The doses of 21:00 and 21:02 overlap in their response windows; both capture pre_i = 152 (the sample of 20:32), so the global bp_pre stream and the per-instance value agree (A3 of 02-templates.md section 1.5 holds in value). |
| H-W6 | Authenticated deployment with every device capability declared: message authentication, seq, diagnostics, a data-stream deadline, independent clocks, signal quality, pulse and ECG heart rate available and coherent at every measurement; the dispenser has no content sensing and reports no interval (CP8). With the reference profile S6 of evidence-channels.md the kappa C1 of record PD-ALT-04 would be UNDETERMINED (OP-AR-1). |
| H-W7 | The evidence window of the 12:24 instance does not reach the cuff outage of 08:56 to 11:20 (evidence_margin_ms is smaller than 64 min); the cuff keeps its sequence counter across the restart; evidence_grace_ms is 0. |
| H-W8 | The robot is co-located from 06:58 to 07:05 only; the presence stream is sampled as in golden G-INT-1 (1.0 at 06:58, an explicit 0.0 at 06:59), so the witness age at 07:00 is 2 min; the robot channels presence and intake are unavailable at all other times. |
| H-W9 | The 20:32 sample is an informed replay (threat-model.md class replay, level informed, fresh_metadata): t_device_ms fresh, seq continues (no repeat, no gap), the verification of the message fails; the genuine 20:32 message does not reach the gateway (H-SUPP). Hypothesis NP-1 (08 section 2.3): a duplicate (source, seq) is not used by this day. |
| H-W10 | Cuff health 1.0 and inflation 45000 ms at every measurement (fixture); hr_pulse and hr_ecg are not templates inputs and are not listed. |
| H-W11 | Prediction: one designated instant (20 min before the deadline, 12:10), variant likely, calibrator fixture C-1 (n 9, alpha 0.2, q 0.09); the forecast is a stub (arrival 12:40). |
| H-W12 | Scales and priorities are the F0 rows (priority_count 2 and priority_resp 2 are FIXTURE-ONLY); the registry 0.2.0 values are not used. |

### 1.5 Corrections to the scenario table (R1 to R11)

The scenario table of the task is a target, not an authority. The formal documents decide, and where a row disagrees the correction is recorded here and in `08` section 3. The rows that agree are marked "kept"; additions are values that the target did not state.

| Row | Target | What the formal documents give | Disposition |
|---|---|---|---|
| R1 | SCHED +28 min, 0.9333; RANGE 2 mmHg, 0.1; SYS +15000 ms, 0.5; rho none | the same (records PD-REC-01 to 03) | kept |
| R2 | HOLD +38, 1.0 (clip of 1.9); COUNT +1 dose, 1.0; INT 300000 - 120000 = +180000 ms, 0.6; RESP created with `bp_pre` 138, PENDING, `[-inf, 78]`, normalised (-1, 1), pending until 10:00 | the same; INT needs the explicit `presence` 0.0 sample at 06:59 because `presence` is a held level (`02` section 4.7, golden G-INT-1); the day-end COUNT instance is PENDING with `[-1, +inf]` | kept; the sample and the day-end instance are additions |
| R3 | SCHED VIOLATED, decided 09:30, `[-inf, -60000]`, normalised upper end -0.0333, DETERMINISTIC 1.0, C2 (liveliness), priority 3, root cause of RESP@07:00 | the same. The alert value -0.0333 is `N_s(hi)` of the first VIOLATED record and holds because the next tick (12:00) is visible after the deadline (`H_i > k_d`, `05` section 2.3, `07` section 1.5); with a tick visible at or before the deadline it would be -1. kappa C2 by row 4 of the rule with the decisive field `system.liveliness_ok` only (the lifecycle entry stays denied, because a crash is a lapse of liveliness and not a lifecycle transition; see `evidence-channels.md` and `attribution-rule.md` W-11) | kept; the dependence on `H_i > k_d` is stated |
| R4 | RESP VIOLATED at 10:00, `[-inf, -inf]`, -1, guard `obligation_unmet`, DETERMINISTIC 1.0, `caused_by` SCHED@09:00, not a top-level alert | the same. Added: the effect carries kappa C2 and the `evidence_used` of its root from its first issue, keeps its own `sigma_norm` -1.0, rho, priority (F0 2) and time (`attribution-rule.md` cascade rules 7 and 8) | kept |
| R5 | 12:10 PREDICTED_VIOLATION of SCHED@12:00, sigma-hat -0.3333, variant likely with C-1 (q 0.09, alpha 0.2), rho PREDICTED 0.9 (alpha* 0.1), kappa UNDETERMINED; 12:24 SCHED SATISFIED +6 min, 0.2; RANGE VIOLATED -12, -0.6, MEASURED 0.9772, C1, priority 2 | the same, with four additions or corrections. (1) The `sigma_norm` of the predicted alert is `clip(sigma_hat + q, -1, 1)` = -0.3333 + 0.09 = -0.2433 (`07` section 1.5, `06` section 2.4), not the point forecast; the record's interval is `[-inf, 1140000]`, normalised (-1, 0.6333). (2) `Rho.alpha` is the configured level 0.2 and alpha* 0.1 is recoverable as 1 - 0.9 (`06` section 10 item 2). (3) kappa C1 needs every channel of the exclusion set of `range` to be available and denied (ten decisive fields), not only "no system or integrity evidence" (`attribution-rule.md` AD-8, W-01); this holds under H-W6 and would be UNDETERMINED in the reference profile S6 (OP-AR-1). (4) The predicted alert is closed as a false predictive alarm at 12:24 and leaves the current set | kept, with corrections (1) to (4) |
| R6 | SCHED SATISFIED +28 min, 0.9333; RANGE VIOLATED -12, -0.6, MEASURED 0.9772 "(model-based, conditional on authenticity)"; kappa C3 because `seq_gap_or_replay` is true and the integrity evidence is tested first; priority 2; the sample's `seq` duplicates the 12:24 sample | **Corrected.** (a) `01` section 3.4 says that an event that repeats an accepted `(source, seq)` "is a duplicate and is not counted again", while `05` section 2.1 defines the accepted trace as "not late and not future-stamped" without that rule: the two documents disagree on whether a duplicate measurement enters the trace (new point NP-1). (b) A naive replay keeps its stale stamp and is late, so it opens no RANGE instance (`threat-model.md`, class replay, verdict effect). (c) The case that the documents define without ambiguity is the informed replay in an authenticated deployment (`attribution-rule.md` W-08): fresh metadata, `seq` continues (no repeat, no gap), the verification fails, kappa C3 by row 1 with the single decisive field `crypto_temporal.authenticated`. The day uses (c). The values of the row (+28 min, -12 mmHg, -0.6, 0.9772, priority 2) are unchanged | corrected: the evidence is a failed verification, not a repeated `seq`; NP-1 carried as an open point |
| R7 | HOLD +52 (1.0); COUNT `c_d` = 2 = limit, sigma 0, SATISFIED by the tie rule; INT SATISFIED by `auth`, +300000, 1.0; RESP created, `bp_pre` 152, PENDING, `[-inf, 92]`, pending until 24:00 | the same. Added: the day-end COUNT instance is PENDING with `[0, +inf]` (the residual case lo = 0 < hi that rule 1 leaves open, CP3-b); pending until 24:00 is the closing step, so the instance is decided at 24:00 at the latest | kept; one addition |
| R8 | COUNT VIOLATED -1 dose, -1.0, DETERMINISTIC 1.0, kappa UNDETERMINED, priority 2; HOLD and INT SATISFIED; RESP@21:02 created, `bp_pre` 152, window [22:02, 00:02], pending until 00:02; the two RESP instances cannot be violated at 21:02 | the same. kappa UNDETERMINED is row 8, reason insufficient, no decisive field: `count` has no exclusion set that can be satisfied in contract 0.1.0 (the dispenser content evidence has no field: `attribution-rule.md` AD-10 and W-06, CP8). The default rule of `#attribution` step 3 ("a violation with coherent channels") is read as the exclusion set. Added: the day-end COUNT instance is SATISFIED at 21:02 by early satisfaction (c_today = 3 > 2, `05` Lemma 12) | kept; one addition |
| R9 | SCHED +25 min, 0.8333; RANGE +8 mmHg, 0.4; both RESP SATISFIED at 22:35, drop 20, margin +10, 0.5 | the same. The raw interval of the two RESP records is `[10, 92]` and the normalised interval `(0.5, 1)`: the target quotes the lower end; the upper end 92 is `pre_i - bound_bp_lower - delta_resp` while the window is open (k < k_d) | kept; the interval is stated in full |
| R10 | ranked list of four top-level alerts: COUNT@21:02, RANGE@12:24, RANGE@20:32, SCHED@09:00 | re-derived with `K0 = (priority, sigma_norm, t_ms, instance_key)`: the same four. The current set has five alerts: the folded RESP@07:00 (priority 2, -1.0, t_ms 36,000,000) precedes COUNT@21:02 (priority 2, -1.0, t_ms 75,720,000) by the `t_ms` tie-break. The closed predicted alert is not in the set | kept; the full current set is added |
| R11 | day-end count of measurements (only if CP2 adopted it) | not adopted: `02` section 4.4 keeps the day-end obligation to doses; `meas_min_day` is neither a template parameter nor a registry entry | omitted |

## 2 Timeline

One row per event of the scenario table. A record is `rec(i, k)` of one instance at one finalised step; its id points to the bullet that shows the calculation. Section 2.1 to 2.9 give, per row, the records (state, raw interval with unit, normalised interval, rho with its kind, decision time, pending-until time) and the calculation. Rows R10 and R11 are in sections 2.10 and 2.11.

| Row | Time | What happens (inputs of the monitor) | Records | Alerts |
|---|---|---|---|---|
| R1 | 06:50, 06:52 | tick 06:50; measurement bp 138, healthy cuff, inflation 45000 ms | PD-REC-01 to 03 | none |
| R2 | 06:58 to 07:01 | the robot observes the patient (identity confirmed) at 06:58, `presence` 0.0 at 06:59; 07:00 DISPENSE (no `auth`); 07:01 INTAKE observed | PD-REC-04 to 08 | none |
| R3 | 08:56, 09:00, 09:30 | the cuff process stops (no input, liveliness lapses); tick 09:00; no measurement; the deadline 09:30 passes | PD-REC-09 | A1 (SCHED, C2, root) |
| R4 | 10:00 | the response window [08:00, 10:00] of the 07:00 dose closes with no measurement | PD-REC-10 | A2 (RESP, folded under A1) |
| R5 | 11:20, 12:00, 12:10, 12:24 | the cuff restarts; tick 12:00; forecast at 12:10 (arrival 12:40); measurement bp 152 at 12:24 | PD-REC-11 to 14 | A3 (predicted, closed), A4 (RANGE, C1) |
| R6 | 20:30, 20:32 | tick 20:30; sample bp 152 at 20:32 (informed replay, failed verification) | PD-REC-15 to 17 | A5 (RANGE, C3) |
| R7 | 21:00 | DISPENSE (scheduled), `auth` true, robot absent | PD-REC-18 to 22 | none |
| R8 | 21:02 | DISPENSE (unscheduled), `auth` true, robot absent | PD-REC-23 to 27 | A6 (COUNT, UNDETERMINED) |
| R9 | 22:30, 22:35 | tick 22:30; measurement bp 132 at 22:35 | PD-REC-28 to 32 | none |
| R10 | 24:00 | end of day | none | ranked list, section 3.4 |
| R11 | none | omitted (CP2) | none | none |

### 2.1 R1: 06:52 measurement

The tick of 06:50 opens a SCHED instance at step 410; the measurement of 06:52 (step 412) decides it, a RANGE instance and a SYS instance at once. No rho: all three records are SATISFIED.

| Record | Instance | Eval | State | Raw interval | Normalised | rho | Decided | Pending until | Notes |
|---|---|---|---|---|---|---|---|---|---|
| PD-REC-01 | `sched@24600000` | 06:52 | SATISFIED | [1680000, 1680000] ms | (0.9333, 0.9333) | none | 06:52 | 07:20 |  |
| PD-REC-02 | `range@24720000` | 06:52 | SATISFIED | [2, 2] mmHg | (0.1, 0.1) | none | 06:52 | 06:52 |  |
| PD-REC-03 | `sys@24720000` | 06:52 | SATISFIED | [15000, 15000] ms | (0.5, 0.5) | none | 06:52 | 06:52 |  |

- **PD-REC-01**, `sched@24600000` at 06:52. Tick 24600000 = (6*60+50)*60000, k_a = 410; w = 1800000/60000 = 30, k_d = 440, t_d = 26400000 (07:20). The measurement at 24720000 is visible at step 24720000/60000 = 412, in [410, 440]. Slack = (440 - 412) * 60000 = 28 * 60000 = 1680000 ms. Any later measurement has slack <= 27 * 60000 = 1620000 < 1680000, so hi = 1680000 too: the interval is the point. lo > 0: SATISFIED at 412. Normalised 1680000 / 1800000 = 0.9333.
- **PD-REC-02**, `range@24720000` at 06:52. bp_412 = 138. min(138 - 110, 140 - 138) = min(28, 2) = 2 mmHg (distance to the nearer limit). 2 / 20 = 0.1. The band applies at every measurement, including a measurement inside the onset window of the drug (a question for the clinician review, TG-13).
- **PD-REC-03**, `sys@24720000` at 06:52. cuff_health = 1.0, so the guard cuff_health == 1 is +inf. inflation_ms = 45000, margin 45000 - 30000 = 15000 ms. min(+inf, 15000) = 15000. 15000 / 30000 = 0.5.

### 2.2 R2: 06:58 presence, 07:00 DISPENSE, 07:01 INTAKE

A dispense creates, at the dispense step, a HOLD, a COUNT-limit, an INT and a RESP instance (`05` section 6.2). The INTAKE event at 07:01 is a separate input and is not read by any of them: INT looks back from the dispense (`02` section 4.7), and RESP reads measurements, not the intake. The day-end COUNT instance exists from 00:00; it is shown here after the first dose.

| Record | Instance | Eval | State | Raw interval | Normalised | rho | Decided | Pending until | Notes |
|---|---|---|---|---|---|---|---|---|---|
| PD-REC-04 | `hold@25200000` | 07:00 | SATISFIED | [38, 38] mmHg | (1, 1) | none | 07:00 | 07:00 |  |
| PD-REC-05 | `count@25200000` | 07:00 | SATISFIED | [1, 1] dose | (1, 1) | none | 07:00 | 07:00 |  |
| PD-REC-06 | `int@25200000` | 07:00 | SATISFIED | [180000, 180000] ms | (0.6, 0.6) | none | 07:00 | 07:00 |  |
| PD-REC-07 | `resp@25200000` | 07:00 | PENDING | [-inf, 78] mmHg | (-1, 1) | none | none | 10:00 |  |
| PD-REC-08 | `count@86400000` | 07:00 | PENDING | [-1, +inf] dose | (-1, 1) | none | none | 24:00 |  |

- **PD-REC-04**, `hold@25200000` at 07:00. Look-back 3600000/60000 = 60 steps, [360, 420]; the measurement of 06:52 (step 412) is in it, so the guard is +inf. Held bp = 138. Margin 138 - 100 = 38 mmHg. 38 / 20 = 1.9, clipped to 1.0 (clipped value).
- **PD-REC-05**, `count@25200000` at 07:00. dose_count over (25200000 - 86400000, 25200000] = this dispense only (H-W3): c_d = 1. Margin 2 - 1 = +1 dose. 1 / 1 = 1.0 (not clipped, equal to the scale).
- **PD-REC-06**, `int@25200000` at 07:00. Presence 1.0 at 25080000 = step 418; 0.0 at step 419 (held level). Witness at step 418, age (420 - 418) * 60000 = 120000 ms. Margin int_window - age = 300000 - 120000 = 180000 ms. Steps 419 and 420 have presence 0, no intake, no auth: -inf. Earlier steps have the channel unavailable (open): a witness there is older, margin at most (420 - 417) = 3 min -> 120000 < 180000, so hi = 180000 too. 180000 / 300000 = 0.6.
- **PD-REC-07**, `resp@25200000` at 07:00. pre_i = latest bp sample with device time <= 25200000 = 138 (06:52). k_a = 420, k_d = 420 + 10800000/60000 = 600, t_d = 36000000. Window [420 + 60, 600] = [08:00, 10:00]: no measurement known, lo = -inf. hi = pre_i - bound_bp_lower - delta_resp = 138 - 50 - 10 = 78 (a measurement of 50 would give the largest drop). 78 / 20 = 3.9, clipped to 1.0; -inf maps to -1.
- **PD-REC-08**, `count@86400000` at 07:00. Day-end obligation dose_count >= dose_min_day_end, decided at the closing step K = 1440 (86400000). Known dispenses of steps 1..420: 1. lo = 1 - 2 = -1 dose; unknown future dispenses add [0, +inf), so hi = +inf. -1 / 1 = -1.0; +inf maps to 1.0. PENDING.

### 2.3 R3: 09:00 tick without measurement

The cuff process is down from 08:56. The tick of 09:00 opens a SCHED instance; nothing arrives. The interval of the instance at 09:00 is `[-inf, 1740000]` ms (the earliest measurement that can still be accepted is visible one step later, slack 29 min), and the upper end falls by one step per step until 09:30.

| Record | Instance | Eval | State | Raw interval | Normalised | rho | Decided | Pending until | Notes |
|---|---|---|---|---|---|---|---|---|---|
| PD-REC-09 | `sched@32400000` | 09:30 | VIOLATED | [-inf, -60000] ms | (-1, -0.0333) | DETERMINISTIC 1.0 | 09:30 | 09:30 | guard_failed no_measurement_after_tick |

- **PD-REC-09**, `sched@32400000` at 09:30. Tick 32400000, k_a = 540, k_d = 570, t_d = 34200000. No measurement in [540, 570]: lo = -inf. The next measurement tick is 12:00 (step 720), so the closing step is H_i = max(570, min(720, 1440)) = 720 > k_d. A measurement can still be accepted at step 571 (09:31) with slack (570 - 571) * 60000 = -60000, so hi = -60000 < 0: VIOLATED at 570. Normalised -60000 / 1800000 = -0.0333; -inf maps to -1. If the next tick were visible at or before the deadline, H_i = k_d and hi = -inf (then -1).

### 2.4 R4: 10:00 the response window closes

| Record | Instance | Eval | State | Raw interval | Normalised | rho | Decided | Pending until | Notes |
|---|---|---|---|---|---|---|---|---|---|
| PD-REC-10 | `resp@25200000` | 10:00 | VIOLATED | [-inf, -inf] mmHg | (-1, -1) | DETERMINISTIC 1.0 | 10:00 | 10:00 | guard_failed obligation_unmet |

- **PD-REC-10**, `resp@25200000` at 10:00. k = k_d = 600: every step of the window [480, 600] is known and carries no measurement (the cuff was down from 08:56 to 11:20), so the maximum over an empty set of witnesses is -inf and no open position is left: [-inf, -inf]. hi < 0: VIOLATED. -inf maps to -1 on both ends. Guard failure obligation_unmet, so rho is DETERMINISTIC 1.0 (06 section 2.3).

### 2.5 R5: 12:10 early warning, 12:24 measurement

| Record | Instance | Eval | State | Raw interval | Normalised | rho | Decided | Pending until | Notes |
|---|---|---|---|---|---|---|---|---|---|
| PD-REC-11 | `sched@43200000` | 12:10 | PREDICTED_VIOLATION | [-inf, 1140000] ms | (-1, 0.6333) | PREDICTED 0.9 (alpha 0.2, alpha* 0.1) | none | 12:30 | stateful forecast, interval untouched |
| PD-REC-12 | `sched@43200000` | 12:24 | SATISFIED | [360000, 360000] ms | (0.2, 0.2) | none | 12:24 | 12:30 | false_predictive_alarm |
| PD-REC-13 | `range@44640000` | 12:24 | VIOLATED | [-12, -12] mmHg | (-0.6, -0.6) | MEASURED 0.9772 | 12:24 | 12:24 |  |
| PD-REC-14 | `sys@44640000` | 12:24 | SATISFIED | [15000, 15000] ms | (0.5, 0.5) | none | 12:24 | 12:24 |  |

- **PD-REC-11**, `sched@43200000` at 12:10. Tick 43200000, k_a = 720, k_d = 750, t_d = 45000000. At k = 730 no measurement is known: lo = -inf; the earliest measurement that can still be accepted is visible at step 731, slack (750 - 731) * 60000 = 1140000, so hi = 1140000 (the interval is that of the measured prefix, untouched by the forecast). Normalised (-1, 1140000/1800000 = 0.6333). Forecast arrival 12:40 = step 760, slack (750 - 760) * 60000 = -600000, sigma_hat = -600000/1800000 = -0.3333, inside [-1, 0.6333] so no clipping. Calibrator C-1: n = 9, k = ceil(10 * 0.8) = 8, q = 8th smallest score = 0.09. sigma_hat + q = -0.3333 + 0.09 = -0.2433 < 0: emitted (variant likely). m = #{R_i < -sigma_hat = 0.3333} = 9 (all nine scores are below 0.15 < 0.3333); alpha* = (10 - 9) / 10 = 0.1; rho = 1 - alpha* = 9/10 = 0.9; Rho.alpha = 0.2 (the configured level). The record stays PENDING in its interval fields and the state is PREDICTED_VIOLATION (never definitive).
- **PD-REC-12**, `sched@43200000` at 12:24. The measurement at 44640000 is visible at step 744, in [720, 750]. Slack (750 - 744) * 60000 = 360000 ms; a later measurement has slack <= 5 * 60000 = 300000, so the interval is the point. lo > 0: SATISFIED at 744, from PREDICTED_VIOLATION (an allowed transition): the warning is counted as a false predictive alarm. 360000 / 1800000 = 0.2.
- **PD-REC-13**, `range@44640000` at 12:24. bp_744 = 152. min(152 - 110, 140 - 152) = min(42, -12) = -12 mmHg. -12 / 20 = -0.6. rho MEASURED, band formula Phi((110 - 152)/6) + Phi((152 - 140)/6) = Phi(-7) + Phi(2) = 1.3e-12 + 0.97725 = 0.9772 (cuff_error_sd 6, FIXTURE-ONLY).
- **PD-REC-14**, `sys@44640000` at 12:24. cuff_health 1.0 (guard +inf), inflation 45000 - 30000 = 15000 ms; 15000 / 30000 = 0.5.

### 2.6 R6: 20:32 replayed sample

The monitor accepts the 20:32 sample, so it decides the SCHED instance of the 20:30 tick as satisfied and opens a RANGE and a SYS instance. Whether the sample is a replay is not a monitor question: the attribution layer decides it from the evidence vector (section 3.2).

| Record | Instance | Eval | State | Raw interval | Normalised | rho | Decided | Pending until | Notes |
|---|---|---|---|---|---|---|---|---|---|
| PD-REC-15 | `sched@73800000` | 20:32 | SATISFIED | [1680000, 1680000] ms | (0.9333, 0.9333) | none | 20:32 | 21:00 |  |
| PD-REC-16 | `range@73920000` | 20:32 | VIOLATED | [-12, -12] mmHg | (-0.6, -0.6) | MEASURED 0.9772 | 20:32 | 20:32 |  |
| PD-REC-17 | `sys@73920000` | 20:32 | SATISFIED | [15000, 15000] ms | (0.5, 0.5) | none | 20:32 | 20:32 |  |

- **PD-REC-15**, `sched@73800000` at 20:32. Tick 73800000 = 1230 * 60000, k_a = 1230, k_d = 1260, t_d = 75600000. The sample is accepted (on time, fresh metadata, H-W9) and visible at step 1232. Slack (1260 - 1232) * 60000 = 28 * 60000 = 1680000 ms; 1680000 / 1800000 = 0.9333. The monitor cannot tell that the sample is a replay: that is the business of attribution.
- **PD-REC-16**, `range@73920000` at 20:32. Same arithmetic as PD-REC-13: min(152 - 110, 140 - 152) = -12 mmHg, -12 / 20 = -0.6, rho MEASURED Phi(-7) + Phi(2) = 0.9772, a model-based value conditional on the adequacy of the device error model and not covering authenticity (06 section 2.2).
- **PD-REC-17**, `sys@73920000` at 20:32. The informed replay writes the whole group (health 1.0, inflation 45000, threat-model.md H-GROUP): 45000 - 30000 = 15000 ms, 0.5.

### 2.7 R7: 21:00 scheduled DISPENSE

| Record | Instance | Eval | State | Raw interval | Normalised | rho | Decided | Pending until | Notes |
|---|---|---|---|---|---|---|---|---|---|
| PD-REC-18 | `hold@75600000` | 21:00 | SATISFIED | [52, 52] mmHg | (1, 1) | none | 21:00 | 21:00 |  |
| PD-REC-19 | `count@75600000` | 21:00 | SATISFIED | [0, 0] dose | (0, 0) | none | 21:00 | 21:00 | tie_rule |
| PD-REC-20 | `int@75600000` | 21:00 | SATISFIED | [300000, 300000] ms | (1, 1) | none | 21:00 | 21:00 |  |
| PD-REC-21 | `resp@75600000` | 21:00 | PENDING | [-inf, 92] mmHg | (-1, 1) | none | none | 24:00 |  |
| PD-REC-22 | `count@86400000` | 21:00 | PENDING | [0, +inf] dose | (0, 1) | none | none | 24:00 |  |

- **PD-REC-18**, `hold@75600000` at 21:00. Look-back [1200, 1260] contains the measurement at step 1232 (20:32). Held bp = 152. Margin 152 - 100 = 52 mmHg. 52 / 20 = 2.6, clipped to 1.0.
- **PD-REC-19**, `count@75600000` at 21:00. dose_count over (75600000 - 86400000, 75600000] contains the dispenses at 07:00 (step 420) and 21:00 (step 1260): c_d = 2. Margin 2 - 2 = 0. Contract rule 1 alone gives neither VIOLATED (hi < 0 false) nor SATISFIED (lo > 0 false); the instance is closed (k = k_d) and the interval is the point 0, so the tie rule (ADR-029, 05 section 3.4) gives SATISFIED. 0 / 1 = 0.
- **PD-REC-20**, `int@75600000` at 21:00. auth sample at 75600000 = step 1260, age 0: margin 300000 - 0 = 300000 ms, the largest value the template can give, so the open (unavailable) presence and intake steps cannot raise it: [300000, 300000]. 300000 / 300000 = 1.0. DISPENSE is not INTAKE: no intake is inferred.
- **PD-REC-21**, `resp@75600000` at 21:00. pre_i = 152 (the latest bp sample at or before 21:00 is the one of 20:32). k_a = 1260, k_d = 1260 + 180 = 1440 = K, t_d = 86400000. Window [1320, 1440] = [22:00, 24:00]. lo = -inf; hi = 152 - 50 - 10 = 92; 92 / 20 = 4.6, clipped to 1.0.
- **PD-REC-22**, `count@86400000` at 21:00. Known dispenses of steps 1..1260: 2. lo = 2 - 2 = 0, hi = +inf (more dispenses may come). Rule 1 gives SATISFIED only for lo > 0, the tie rule needs a closed instance (k >= K): PENDING. Every completion satisfies the non-strict atom (CP3-b, a sound refinement lo >= 0 that ADR-029 does not adopt).

### 2.8 R8: 21:02 unscheduled DISPENSE

| Record | Instance | Eval | State | Raw interval | Normalised | rho | Decided | Pending until | Notes |
|---|---|---|---|---|---|---|---|---|---|
| PD-REC-23 | `count@75720000` | 21:02 | VIOLATED | [-1, -1] dose | (-1, -1) | DETERMINISTIC 1.0 | 21:02 | 21:02 |  |
| PD-REC-24 | `hold@75720000` | 21:02 | SATISFIED | [52, 52] mmHg | (1, 1) | none | 21:02 | 21:02 |  |
| PD-REC-25 | `int@75720000` | 21:02 | SATISFIED | [300000, 300000] ms | (1, 1) | none | 21:02 | 21:02 |  |
| PD-REC-26 | `resp@75720000` | 21:02 | PENDING | [-inf, 92] mmHg | (-1, 1) | none | none | 24:02 |  |
| PD-REC-27 | `count@86400000` | 21:02 | SATISFIED | [1, +inf] dose | (1, 1) | none | 21:02 | 24:00 |  |

- **PD-REC-23**, `count@75720000` at 21:02. dose_count over (75720000 - 86400000, 75720000] = dispenses at steps 420, 1260, 1262: c_d = 3. Margin 2 - 3 = -1 dose. -1 / 1 = -1.0 (equal to the scale, not clipped). hi < 0: VIOLATED at once. Rho DETERMINISTIC 1.0: a count over the event log.
- **PD-REC-24**, `hold@75720000` at 21:02. Look-back [1202, 1262] contains step 1232; held bp 152; 152 - 100 = 52; 52 / 20 = 2.6 clipped to 1.0.
- **PD-REC-25**, `int@75720000` at 21:02. auth sample at 75720000 = step 1262, age 0: 300000 ms, 300000 / 300000 = 1.0.
- **PD-REC-26**, `resp@75720000` at 21:02. pre_i = 152. k_a = 1262, k_d = 1262 + 180 = 1442 > K = 1440, t_d = 75720000 + 10800000 = 86520000. Window [1322, 1442] = [22:02, 24:02]. lo = -inf; hi = 152 - 50 - 10 = 92. It cannot be VIOLATED at 21:02: that needs pre_i < bound_bp_lower + delta_resp = 60 (05 Lemma 12), and 152 >= 60. The same holds for the instance of 21:00, whose window opens at 22:00 (analisi §4.6 row 21:02, error b).
- **PD-REC-27**, `count@86400000` at 21:02. Known dispenses of steps 1..1262: 3. lo = 3 - 2 = +1 > 0, so SATISFIED at once (05 Lemma 12: the first step with c_today > dose_min_day_end); hi stays +inf. Normalised (1/1 = 1.0, +inf maps to 1.0). Reported, not hidden: the unscheduled dose that violates the 24 h limit also satisfies the day-end minimum.

### 2.9 R9: 22:35 measurement

| Record | Instance | Eval | State | Raw interval | Normalised | rho | Decided | Pending until | Notes |
|---|---|---|---|---|---|---|---|---|---|
| PD-REC-28 | `sched@81000000` | 22:35 | SATISFIED | [1500000, 1500000] ms | (0.8333, 0.8333) | none | 22:35 | 23:00 |  |
| PD-REC-29 | `range@81300000` | 22:35 | SATISFIED | [8, 8] mmHg | (0.4, 0.4) | none | 22:35 | 22:35 |  |
| PD-REC-30 | `sys@81300000` | 22:35 | SATISFIED | [15000, 15000] ms | (0.5, 0.5) | none | 22:35 | 22:35 |  |
| PD-REC-31 | `resp@75600000` | 22:35 | SATISFIED | [10, 92] mmHg | (0.5, 1) | none | 22:35 | 24:00 |  |
| PD-REC-32 | `resp@75720000` | 22:35 | SATISFIED | [10, 92] mmHg | (0.5, 1) | none | 22:35 | 24:02 |  |

- **PD-REC-28**, `sched@81000000` at 22:35. Tick 81000000 = 1350 * 60000, k_a = 1350, k_d = 1380, t_d = 82800000. Measurement at step 1355. Slack (1380 - 1355) * 60000 = 25 * 60000 = 1500000 ms; later measurements have slack <= 24 * 60000 = 1440000, so a point. 1500000 / 1800000 = 0.8333.
- **PD-REC-29**, `range@81300000` at 22:35. bp_1355 = 132. min(132 - 110, 140 - 132) = min(22, 8) = 8 mmHg. 8 / 20 = 0.4.
- **PD-REC-30**, `sys@81300000` at 22:35. 45000 - 30000 = 15000 ms; 15000 / 30000 = 0.5.
- **PD-REC-31**, `resp@75600000` at 22:35. Step 1355 is in the window [1320, 1440]. Drop = pre_i - bp = 152 - 132 = 20 mmHg; margin 20 - 10 = +10 mmHg, so lo = 10 > 0: SATISFIED at 22:35, before the deadline. hi = max(10, 152 - 50 - 10) = 92 because k < k_d (a lower pressure may still come). 10 / 20 = 0.5; 92 / 20 = 4.6 clipped to 1.0.
- **PD-REC-32**, `resp@75720000` at 22:35. Step 1355 is in the window [1322, 1442]. Same pre_i = 152 and margin +10 as PD-REC-31: lo = 10 > 0, SATISFIED at 22:35 although k_d = 1442 lies after the closing step (05 Lemma 12b). hi = 92 (k < k_d). 0.5 and 1.0.

### 2.10 R10: end of day

The ranked list is in section 3.4. At 24:00 no instance is undecided: of the 26 instances of the day, 21 are SATISFIED and 5 are VIOLATED (SCHED@09:00, RESP@07:00, RANGE@12:24, RANGE@20:32 and COUNT@21:02). The instance RESP@21:02, whose decision step 1442 is after the closing step, was decided at 22:35 by early satisfaction.

### 2.11 R11: omitted

R11 exists only if the measurement-count obligation of analisi §4.6 and §4.9 item 3 is a template. `02` section 4.4 does not adopt it (a measurement unit does not exist in `RobustnessUnit`, it would give COUNT two margin dimensions, and it would duplicate the SCHED instances, which is the unhandled cascade of Table I row 15:00); `meas_min_day` is neither a template parameter nor a registry entry. The day has therefore four measurements (06:52, 12:24, 20:32, 22:35) and no measurement-count record. The cascade of Table I row 15:00 appears here through the RESP effect of the same missed measurement (section 3.3).

## 3 Alerts and ranking

### 3.1 The six alerts

An alert is built from the first VIOLATED record of an instance (or from the PREDICTED_VIOLATION record) by the attribution layer; its twelve fields and the six fields of `Explanation` are in `patient-day.yaml` (`xi.text` is rendered by WS05-T07 and the golden file lists what it must contain). The columns are A1 to A6 (PD-ALT-01 to 06). `score` is `-sigma_norm`; `label` equals `kappa`; `t_ms` is `decided_at_ms` of the first VIOLATED record (`t_eval_ms` for the predicted alert).

| Field | A1 | A2 | A3 | A4 | A5 | A6 |
|---|---|---|---|---|---|---|
| `xi.instance_key` | `sched@32400000` | `resp@25200000` | `sched@43200000` | `range@44640000` | `range@73920000` | `count@75720000` |
| `tau` | sched | resp | sched | range | range | count |
| `verdict` | VIOLATED | VIOLATED | PREDICTED_VIOLATION | VIOLATED | VIOLATED | VIOLATED |
| `t_ms` | 34200000 (09:30) | 36000000 (10:00) | 43800000 (12:10) | 44640000 (12:24) | 73920000 (20:32) | 75720000 (21:02) |
| `sigma_norm` | -0.0333 | -1.0000 | -0.2433 | -0.6000 | -0.6000 | -1.0000 |
| `score` | 0.0333 | 1.0000 | 0.2433 | 0.6000 | 0.6000 | 1.0000 |
| `rho` | DETERMINISTIC 1.0 | DETERMINISTIC 1.0 | PREDICTED 0.9 (alpha 0.2, alpha* 0.1) | MEASURED 0.9772 | MEASURED 0.9772 | DETERMINISTIC 1.0 |
| `kappa` = `label` | C2 | C2 | UNDETERMINED | C1 | C3 | UNDETERMINED |
| `priority` | 3 | 2 | 3 | 2 | 2 | 2 |
| `root_cause_of` | `resp@25200000` | empty | empty | empty | empty | empty |
| `caused_by` | none | `sched@32400000` | none | none | none | none |
| `xi.evidence_used` | `system.liveliness_ok` | `system.liveliness_ok` | empty | `system.node_lifecycle`, `system.diagnostics_ok`, `system.liveliness_ok`, `system.qos_deadline_missed`, `system.ble_link_quality`, `signal_quality.cuff_error_code`, `cross_device.pulse_vs_ecg_hr_diff`, `crypto_temporal.authenticated`, `crypto_temporal.seq_gap_or_replay`, `crypto_temporal.timestamp_implausible` | `crypto_temporal.authenticated` | empty |

Lifecycle (`07` section 1.4 item 3). A1 is issued at 09:30 with `root_cause_of` empty and re-issued at 10:00 with `root_cause_of` = (`resp@25200000`); between the two issues nothing else of A1 changes except the count sentence derived from that field (`attribution-rule.md` cascade rule 7; the reading of "the other fields are those of the first issue" is confirmed in `08` section 2.3, NP-9). A2 is issued once, with `caused_by`. A3 is issued at 12:10 and closed at 12:24 when the instance ends SATISFIED (a false predictive alarm); it stays in the history and leaves the current set. A4, A5 and A6 are issued once.

### 3.2 Attributed causes

The evidence readings are those of the worked cases of `docs/models/attribution-rule.md` under H-W6; every field not listed is `None`. The rule is the decision table (rows tried in order, the first that holds decides).

| Alert | Template | Evidence vector (source case) | Row of the table and result | Decisive fields (`xi.evidence_used`) |
|---|---|---|---|---|
| A1 | `sched` | `system.node_lifecycle` {cuff active, robot active} denied; `system.liveliness_ok` False asserted (W-11, root) | no integrity evidence; system evidence SE-3 holds: row 4, **C2** | `system.liveliness_ok` |
| A2 | `resp` | `system.node_lifecycle` {cuff, dispenser, robot active}; `system.liveliness_ok` False (W-11, `resp@07:00`) | own result row 4, C2; folded under A1 (same class), takes A1's kappa and decisive fields | `system.liveliness_ok` |
| A3 | `sched` | not evaluated: the rule is not applied to a PREDICTED_VIOLATION record (CP13, `07` section 1.7) | **UNDETERMINED** by definition | none |
| A4 | `range` | authenticated deployment, every channel of the exclusion set available and denied (W-01): lifecycle active, diagnostics True, liveliness True, deadline missed False, delivery ratio 1.0, cuff error code empty, pulse coherent with the ECG, `authenticated` True, `seq_gap_or_replay` False, `timestamp_implausible` False | rows 1 to 4 do not hold; exclusion set of `range` satisfied: row 5, **C1** | the ten denied fields of the exclusion set, in contract order |
| A5 | `range` | as A4 except `crypto_temporal.authenticated` False asserted (W-08) | integrity evidence IE-1 holds: row 1, **C3**, whatever the other fields say | `crypto_temporal.authenticated` |
| A6 | `count` | dispenser-link fields only, all clean: lifecycle {dispenser active}, diagnostics True, liveliness True, deadline missed False, ratio 1.0, `authenticated` True, `seq_gap_or_replay` False, `timestamp_implausible` False (W-06) | rows 1 to 4 do not hold; `count` has no exclusion set that can be satisfied (the dispenser content evidence has no field: AD-10, CP8, ADR-032 proposed); no row 6 predicate; kind CARE_PLAN: row 8, **UNDETERMINED**, reason insufficient | none |

What the table says about A6 and why the day abstains. The analisi §4.5 matrix reads "double take by the patient: yes, if the dispenser measures content", and "dispenser sensor bounce: yes, interval below one second and no content change". With the contract fields of version 0.1.0 neither the interval nor the content change is available (hypothesis H-W6, CP8), so a double take and a bounce give the same vector and the rule abstains. The label C3 of Table I row 21:02 is not given: no integrity evidence exists for that dispense (`auth` true, `authenticated` True, `seq` consistent).

### 3.3 The cascade (R3 and R4)

The effect A2 is folded under the root A1 by the cascade table CT-1 of `attribution-rule.md`, with these checks, all computed from the records:

- the root has a definite kappa of its own (C2) and its decision time 34,200,000 (09:30) is strictly earlier than the decision time of the effect, 36,000,000 (10:00);
- the interval of the root, from its decision time minus `sched_window` to its decision time, is [32,400,000, 34,200,000] = [09:00, 09:30]; the response window of the effect, from its decision time minus (`delta2` - `delta1`) to its decision time, is [28,800,000, 36,000,000] = [08:00, 10:00]; the two intervals meet (they intersect in [09:00, 09:30]);
- the decisive sub-formula of the effect is a failed guard (`obligation_unmet`, `hi = -inf`), so the datum the root made missing (the measurement of 09:00) is the datum the effect lacks;
- the effect's own evidence gives the same class as the root (C2), so the independent-evidence rule does not keep it top-level.

`caused_by` of A2 is `sched@32400000`; `root_cause_of` of A1 is (`resp@25200000`); each is in the other's list (mutual inverses, acyclic, depth one). The effect remains an alert returned by the attribution layer and its record is untouched; a consumer that shows the top-level list filters on `caused_by` being none. The measurement-count cascade of Table I row 15:00 does not exist here because that template is not in the library (section 2.11).

### 3.4 Ranking (R10)

Key `K0(a) = (priority, sigma_norm, t_ms, instance_key)`, all ascending (ADR-028; `04` section 4.2). The current set after the cascade holds five alerts (the closed predicted alert is not in it):

| Alert | `priority` | `sigma_norm` | `t_ms` | `caused_by` |
|---|---|---|---|---|
| A2 `resp@25200000` | 2 | -1.0 | 36,000,000 | `sched@32400000` |
| A6 `count@75720000` | 2 | -1.0 | 75,720,000 | none |
| A4 `range@44640000` | 2 | -0.6 | 44,640,000 | none |
| A5 `range@73920000` | 2 | -0.6 | 73,920,000 | none |
| A1 `sched@32400000` | 3 | -0.0333 | 34,200,000 | none |

Derivation. The first component decides between priority 2 and 3: A1 is last by both keys, since its priority 3 is the lowest and its `sigma_norm` is the least negative. Inside priority 2 the second component orders -1.0 before -0.6. The ties on the second component are broken by `t_ms`: A2 (36,000,000) before A6 (75,720,000), and A4 (44,640,000) before A5 (73,920,000). Without the fold the order of the top-level list is the order above without A2, which is the list of the scenario table: **COUNT@21:02, RANGE@12:24, RANGE@20:32, SCHED@09:00**. In this day the priority order and the severity order agree on A1, so the day does not exercise a case where the priority overrides the severity (that is `ranking.yaml` RK-1 and RK-4). The order does not depend on the registry values of 0.2.0: with the F0 priorities used here COUNT and RESP share priority 2, and the order inside the class compares their severities, which is permitted by the contract (`04` section 4.3); a clinician who does not regard a fraction of one scale as comparable to a fraction of the other would give them distinct priorities.

### 3.5 Data for the figure of the patient-day (WS09-T03)

These are the hand-checked quantities that the figure of the patient-day plots; the design of the figure is WS09-T03's and nothing here is paper text.

Bands (normalised interval of an instance over time, `04` section 2.1). A SCHED instance starts at its tick with `[-inf, 1740000]` ms, normalised (-1, 0.9667), and the upper end falls by one step (60000 ms, 0.0333) per step until a measurement arrives (the interval collapses to the point of the slack) or the deadline (the interval ends at `[-inf, -60000]` for SCHED@09:00, because the next tick is visible after the deadline). A RESP instance starts at `(-1, 1)` (`[-inf, pre_i - 60]`, which is 78 and 92) and either collapses to the point `-inf` at the closing step of its window (RESP@07:00) or jumps to `(0.5, 1)` at the first measurement of the window with a positive margin (the two later RESP instances). The day-end COUNT instance starts at `(-1, 1)` (`[-2, +inf]`), is `(-1, 1)` after 07:00 (`[-1, +inf]`), `(0, 1)` after 21:00 (`[0, +inf]`) and `(1, 1)` from 21:02.

Points, in time order (instance, time, state, normalised value or interval):

| Time | Instance | State | Normalised |
|---|---|---|---|
| 06:52 | SCHED@06:50 / RANGE@06:52 / SYS@06:52 | SATISFIED | 0.9333 / 0.1 / 0.5 |
| 07:00 | HOLD / COUNT / INT / RESP (07:00 dose) | SATISFIED, SATISFIED, SATISFIED, PENDING | 1.0 / 1.0 / 0.6 / (-1, 1) |
| 09:30 | SCHED@09:00 | VIOLATED (alert A1) | (-1, -0.0333) |
| 10:00 | RESP@07:00 | VIOLATED (alert A2, folded) | (-1, -1) |
| 12:10 | SCHED@12:00 | PREDICTED_VIOLATION (alert A3) | interval (-1, 0.6333), alert -0.2433 |
| 12:24 | SCHED@12:00 / RANGE@12:24 / SYS@12:24 | SATISFIED (false predictive alarm) / VIOLATED (alert A4) / SATISFIED | 0.2 / -0.6 / 0.5 |
| 20:32 | SCHED@20:30 / RANGE@20:32 / SYS@20:32 | SATISFIED / VIOLATED (alert A5) / SATISFIED | 0.9333 / -0.6 / 0.5 |
| 21:00 | HOLD / COUNT / INT / RESP (21:00 dose) | SATISFIED, SATISFIED (tie), SATISFIED, PENDING | 1.0 / 0.0 / 1.0 / (-1, 1) |
| 21:02 | COUNT / HOLD / INT / RESP (21:02 dose) / day-end COUNT | VIOLATED (alert A6), SATISFIED, SATISFIED, PENDING, SATISFIED | -1.0 / 1.0 / 1.0 / (-1, 1) / (1, 1) |
| 22:35 | SCHED@22:30 / RANGE@22:35 / SYS@22:35 / RESP (both late doses) | SATISFIED | 0.8333 / 0.4 / 0.5 / (0.5, 1) |

Alert markers: A1 (09:30, -0.0333, C2, DETERMINISTIC 1.0, priority 3), A2 (10:00, -1.0, C2 inherited, folded), A3 (12:10, -0.2433, UNDETERMINED, PREDICTED 0.9, closed 12:24), A4 (12:24, -0.6, C1, MEASURED 0.9772, priority 2), A5 (20:32, -0.6, C3, MEASURED 0.9772, priority 2), A6 (21:02, -1.0, UNDETERMINED, DETERMINISTIC 1.0, priority 2). A cascade link from A2 to A1. The two tied severities of the RANGE alerts and of the pair A2, A6 show the `t_ms` tie-break.

## 4 Coverage matrix

Each required item of the task, the row of the day that covers it, and how to verify it. The ids are those of the golden file (`coverage` section); the check in `08` section 3 loads the file and verifies each list.

| Item | Required | Covered by | How to verify |
|---|---|---|---|
| Verdict state PENDING | at least one | PD-REC-07, 08, 21, 22, 26 | state `pending`, `decided_at_ms` none |
| Verdict state PREDICTED_VIOLATION, then SATISFIED | one instance | PD-REC-11 then PD-REC-12 (instance `sched@43200000`) | state `predicted_violation` at 12:10, `satisfied` at 12:24 with `previous_state` and `false_predictive_alarm` |
| Verdict state VIOLATED | at least one | PD-REC-09, 10, 13, 16, 23 | state `violated`, `sigma_interval` upper end below 0 |
| Verdict state SATISFIED | at least one | 21 records, for example PD-REC-01, 12, 19 | state `satisfied` |
| rho MEASURED | one | PD-REC-13, 16 (0.9772) | kind `measured`, value `Phi(-7) + Phi(2)` |
| rho PREDICTED | one | PD-REC-11 (0.9, alpha 0.2, alpha* 0.1) | `m / (n + 1)` = 9/10 |
| rho DETERMINISTIC | one | PD-REC-09, 10, 23 (1.0) | kind `deterministic` |
| rho absent | one | every SATISFIED and PENDING record, for example PD-REC-01, 07, 12, 19 | `rho` null |
| Cause C1 | one | A4 (`range@44640000`) | `kappa` C1, ten decisive fields |
| Cause C2 | one | A1 and, inherited, A2 | `kappa` C2, `system.liveliness_ok` |
| Cause C3 | one | A5 (`range@73920000`) | `kappa` C3, `crypto_temporal.authenticated` |
| Cause UNDETERMINED | one | A3 (by definition) and A6 (row 8) | `kappa` UNDETERMINED |
| Cascade with `caused_by` | one | A2 under A1 | `caused_by` and `root_cause_of` are inverses (section 3.3) |
| Tie (sigma = 0) | one | PD-REC-19 (COUNT@21:00, c_d = 2) | `sigma_interval` [0, 0], `tie_rule` true, state `satisfied` |
| Clipped value | one | PD-REC-04 (HOLD 38 / 20 = 1.9 clipped to 1.0), also 07, 18, 21, 31 | normalised value 1.0 with raw ratio above 1 |
| Unmet-obligation guard | one | PD-REC-10 (RESP@07:00, `obligation_unmet`, `[-inf, -inf]`) | `guard_failed` `obligation_unmet` |
| All seven templates | seven | range PD-REC-02, sched 01, hold 04, count 05, resp 07, sys 03, int 06 | each template id appears in `records` |
| DISPENSE distinct from INTAKE | one | DISPENSE 07:00 and INTAKE 07:01 are two events; DISPENSE 21:00 and 21:02 have no INTAKE; INT@07:00 is decided by presence, not by the intake (PD-REC-06) | `dispense_distinct_from_intake` in the golden file |
| Final ranked list | one | section 3.4 (five alerts, four top-level) | `ranking` in the golden file; recomputed with `K0` |

## 5 Table I error checklist

Each error of analisi §4.6 and the row of the day that avoids it. The workshop rows are quoted by their time label and the day replaces them with rows computed from the formal documents.

| Table I row | Error (analisi §4.6) | How the day avoids it | Row of the day |
|---|---|---|---|
| 07:00 dispense (workshop label PILL), sigma +18, rho 0.97 | (1) the formula and the unit of sigma are not stated | every record states the template, the unit of its raw interval and the scale used (HOLD in mmHg, COUNT in doses, INT in ms) | PD-REC-04 to 07 |
| | (2) the counter has margin +1 dose | the COUNT record of the first dose is +1 dose, normalised 1.0 | PD-REC-05 |
| | (3) the response window [08:00, 10:00] is open, so the response is PENDING and its sigma is undefined | RESP@07:00 is PENDING with an interval `[-inf, 78]` mmHg and no point value; `decided_at_ms` is none until 10:00 | PD-REC-07, then PD-REC-10 |
| | (4) a "confidence" on a satisfied event has no semantics | rho is none for every SATISFIED and PENDING record; it is defined only for VIOLATED and PREDICTED_VIOLATION records | PD-REC-04 to 08 |
| | (5) the dispenser opening is taken as intake | the 07:00 DISPENSE and the 07:01 INTAKE are two events; no template reads the intake as the dispense; INT is decided by presence | PD-REC-06, coverage row |
| 08:55 BP 152, sigma -12, rho 0.94 | (1) the time does not match a declared schedule | every measurement of the day answers a tick of the declared plan (06:52 to the tick 06:50, 12:24 to 12:00, 20:32 to 20:30, 22:35 to 22:30); the tick of 09:00 is the one that gets none; the schedule is listed with its tick kinds | section 1.3; PD-REC-13, 16, 29 |
| | (2) it is not stated whether the range constraint applies during the onset window of the drug | the day applies RANGE at every measurement, including 22:35, inside the response window of the 21:00 dose, and says so; the question is open for the clinician (TG-13, Q1 of `03` section 6) | PD-REC-02, 29 |
| | (3) rho should be reproducible from an error model | rho of the RANGE alerts is `Phi((110 - 152)/6) + Phi((152 - 140)/6)` = 0.9772 with `cuff_error_sd` 6 mmHg (F0), conditional on the device error model | PD-REC-13, 16 |
| 15:00 BP MEAS, sigma -21, rho 0.71 | (1) the unit of sigma is implicit | sigma is in ms for SCHED (-60000 ms) and the normalised value -0.0333 is dimensionless | PD-REC-09, PD-ALT-01 |
| | (2) a low confidence on a deterministic event | the missed measurement is a predicate over the event log: rho DETERMINISTIC 1.0 | PD-REC-09 |
| | (3) a deliberate lifecycle change is told apart from a crash detected by liveliness or heartbeat | the crash is a lapse of liveliness (`system.liveliness_ok` False) with the lifecycle entry denied; a commanded transition would give UNDETERMINED (W-11-deliberate); the attribution reads liveliness, not a transition | PD-ALT-01, section 3.2 |
| | (4) the cascade is not handled: the missed measurement makes a second alert whose cause is the first | RESP@07:00 is folded under SCHED@09:00 with `caused_by` and the inherited kappa; it is not a top-level alert | PD-ALT-02, section 3.3 |
| 21:00 dispense (workshop label PILL), sigma +15, rho 0.96 | the same errors as 07:00 | HOLD +52 mmHg (clipped to 1.0), COUNT 0 (tie, SATISFIED), INT +300000 ms by `auth`, RESP PENDING; no rho; DISPENSE without any INTAKE | PD-REC-18 to 22 |
| 21:02 unscheduled dispense (workshop label PILL), sigma -8, rho 0.42, C3 | (a) with the counter at 3 of 2 the margin is -1 dose, not -8 | COUNT@21:02 is `[-1, -1]` dose, normalised -1.0 | PD-REC-23 |
| | (b) the cross-modal sub-formula cannot be violated at 21:02: the response windows of 21:00 and 21:02 open at 22:00 and 22:02 | both RESP instances are PENDING at 21:02 (`[-inf, 92]`), cannot be VIOLATED before their windows open (that needs `pre_i` below 60), and are decided at 22:35 | PD-REC-21, 26, 31, 32 |
| | (c) a low rho on a deterministic predicate | the counter violation has rho DETERMINISTIC 1.0 | PD-REC-23 |
| | (d) the label C3 is implausible for a double take or a bounce | kappa is UNDETERMINED (row 8, reason insufficient, no dispenser content evidence); C3 appears only at 20:32, where the verification of the message fails | PD-ALT-06, PD-ALT-05 |
| | (e) tau is a single value although two sub-formulas are named | one alert per violated instance: only COUNT@21:02 is violated at 21:02; HOLD and INT of the same dispense are SATISFIED, the two RESP instances are PENDING; had two instances been violated there would be two alerts, never a compound tau | PD-REC-23 to 26 |

## 6 Paper excerpt (replacement of Table I)

Not written: paper text is outside the agent's scope (ADR-037)
