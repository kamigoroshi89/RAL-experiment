# Benchmark size and rates for all subtypes except the cuff trio (facts for gab)

2026-10-10. Read-only on the repository. Code read from a snapshot of HEAD 0d3f0c0 (`/tmp/research/obs4/repo`; one research-only patch there: the C1 "levels span the reference" check is bypassed for the magnitude scan). Scripts and raw JSON: `/tmp/research/obs4/`. Technical, pre-clinical.

## 0. Method

- **Real builder in memory** (`BuildContext.build_patient`, injectors, labeller, monitor), registry 0.2.1, the real literature prior. Every awaiting row got a labelled PLACEHOLDER (vitals period 60 s, dwell 10 min, intake lag 5 s, adherence mean delay 30 min, magnitudes x0.5/1/2, windows 1/4/12 h unless stated, a noise segment inline). None is a proposal.
- 12 000 patients (84 000 scored patient-days) at the current rates 0.3/0.3/0.2; 4 000, 4 000, 3 000 patients at 0.6, 1.0, 1.7 on all classes; five single-duration scans (5 000 patients); magnitude scan (3 000 patients, C1 rate 1.0, D = 4 h).
- **Positive** = ground-truth event of a scored day (C2/C3: one per realised record; C1: labelled event, which can be several per injection). Test = 0.25 n x 7 patient-days. Monte Carlo error on a share: about 0.5 to 1 point.
- Window rules also done **exactly**: closed form over every 60 s onset on 40 real patients x 7 days, checked against the real injectors on 48 real patient-days (18 144 calls), 0 mismatches. The Monte Carlo reproduces the earlier cuff re-implementation (uniform: 0.633/0.617/0.375 against 0.628/0.619/0.373).
- One in eight drawn injections falls on the unscored tail day (all classes).

## 1. How each subtype is drawn (builder.py `plan_c1` 1302, `plan_observation` 1380, `_c2_spec` 1485, `_c3_spec` 1555)

Counts are Poisson per patient-day with the class rate; the subtype is uniform in the class (C1: 5 subtypes, including the forced `double_take`; C2: the 6 of `_C2_DRIVEN`; C3: 5).

| Subtype | draws / patient-day | onset | levels | positive iff |
|---|---|---|---|---|
| nav_delay | 0.05 | tick uniform among 7 (5 measurement, 2 dose); a tick hosts one robot fault | delay x{.5,1,2} sched_window (30 min), uniform | always (a visit exists per tick) |
| manipulation_failure | 0.05 | same ticks | none | always |
| ecg_noise | 0.05 | uniform 60 s grid | 3 durations, 3 noise levels (awaiting) | an `hr_ecg` sample in the window AND a noise segment kind in the library |
| ble_dropout x4 devices | 0.2496 per device (0.0104/h x 24, a prior row) = 0.998 | uniform grid | 2 / 15 / 60 min uniform (filled) | an item of that device in the window |
| dispenser_bounce | ~0.0019 (p 0.001 per real dispense, ~1.9/day; literature row) | the dispense | gap = nominal only; `stress_*` gaps are drawn by pairs only | always |
| replay | 0.04 | uniform grid, day 0 skipped | attacker naive/informed; duration awaiting | previous-day cuff message at that clock inside the window |
| injection_naive / informed | 0.04 each | uniform grid | duration awaiting | a cuff MEASUREMENT in the window (informed: also an earlier bp, same or previous day) |
| dispense_forgery | 0.04 | informed: a dose tick; naive: uniform instant | attacker | always |
| presence_spoof | 0.04 | uniform instant inside a random robot visit | attacker | robot in the room (nav_delay moves 0.8% of visits) |
| hypertensive_spike | 0.06 | uniform grid | duration and 3 magnitudes x20 mmHg (awaiting) | labeller finds RANGE out of band at a scheduled latent reading in the window |
| hypotension_below_hold | 0.06 | uniform grid | magnitudes x(baseline-100) | HOLD violated: the reading in the 1 h before a dose is below 100 |
| drug_nonresponse | 0.06 | uniform grid | Emax scale {0 (filled), partial, mild} | a true intake in the window and a RESP violation |
| measurement_refusal | 0.06 | one of 5 measurement ticks | none | SCHED (always) |
| double_take (forced) | 0.06 | one of 2 dose ticks | none | COUNT limit; 2.45 events per injection (mechanism not traced) |
| natural (no rate) | per slot: omission 0.057, double take 0.0031, delay 0.081 | Markov chain | | `dose_omission`, `double_take`, `spontaneous_range/resp/hold/count`; `late_dose` and natural refusal have no truth subtype |

The C1 `realised` flag is useless here (1.000 for spike and hypotension): what counts is a labelled event.

## 2. Realised share against the null parameters

Duration D (all three levels equal), share of planned injections realised (C1: with at least one labelled event; magnitudes x.5/1/2):

| D | 30 min | 1 h | 2 h | 4 h | 12 h | grid 1/4/12 h |
|---|---|---|---|---|---|---|
| injection_naive | .098 | .211 | .447 | .672 | .984 | .619 |
| injection_informed | .095 | .201 | .426 | .644 | .912 | .586 |
| replay (days 1-6) | .102 | .205 | .433 | .673 | .978 | .629 |
| spike | .094 | .193 | .380 | .617 | .985 | .59 |
| hypotension | .029 | .057 | .108 | .231 | .517 | .28 |
| non-response | .025 | .050 | .106 | .217 | .610 | .29 |

- **ecg_noise and BLE of ECG/oximeter**: share 1 when D >= vitals period V; otherwise about D/V. BLE (2/15/60 min) averaged: V = 1/5/15/30 min gives 1.00/.80/.71/.52. `ecg_noise` cannot be realised today: `data/raw/segments` does not exist, so the library has no `hr_error_ecg_noise` kind.
- **BLE cuff .091 and dispenser .037** (per level 2/15/60 min: .007/.053/.217 and .003/.020/.082).
- **Magnitude (D = 4 h)**: spike at 5/10/20/30/40 mmHg .50/.56/.62/.65/.66; hypotension at x.25/.5/.75/1/1.5 .03/.055/.17/.32/.365; non-response at Emax .0/.25/.5/.75/.9 .26/.25/.24/.22/.21.
- **Many labelled C1 events already exist naturally**: 2.53 `spontaneous_range` and 1.18 `spontaneous_resp` events per patient-day (about 0.51 of readings out of band; about 0.6 of doses RESP-violating), so a 5 mmHg spike or an Emax of 0.9 is already "positive" in 50% and 21% of draws.
- **Anchored placement (real builder/injectors)**: C3 cuff attacks on k = 1, 2, 3 readings: naive 1.000, replay 1.000, informed .970/.971/.952 (day 0 has no history). Spike on a reading (2 min) .64/.91/1.00 at 5/20/40 mmHg; hypotension on a pre-dose reading .08/.76/.89 at x.5/1/1.5; non-response on a dose tick .65/.58/.52 at Emax 0/.5/.9 (realised .87: omitted or late doses).

## 3. Synthesis (placeholder grid 1/4/12 h, V = 60 s; positives are events; n_100 = patients for mean 100 at current rates)

| Subtype | cls | events per drawn | per 1000 pd | test n=200 | test n=800 | n_100 |
|---|---|---|---|---|---|---|
| cuff_detached / bias / stuck_at (uniform, for comparison) | C2 | .63/.62/.38 | 31.7/30.8/18.8 | 11/11/7 | 44/43/26 | 1805/1853/3044 |
| same, anchored with carry-over (earlier note) | C2 | .98/.97/.93 | | 17/17/16 (rate .3) | 69/68/65 | 1163/1179/1226 |
| ecg_noise | C2 | .99 | 49.3 | 17 | 69 | 1159 |
| nav_delay | C2 | .99 | 49.6 | 17 | 69 | 1152 |
| manipulation_failure | C2 | 1.0 | 50.8 | 18 | 71 | 1124 |
| ble_dropout cuff | C2 | | 22.6 | 8 | 32 | 2525 |
| ble_dropout dispenser | C2 | | 9.0 | 3 | 13 | 6341 |
| ble_dropout ecg / oximeter | C2 | | 250 / 249 | 88 / 87 | 351 / 349 | 228 / 229 |
| dispenser_bounce | C2 | 1.0 | 2.0 | 0.7 | 2.8 | 28 235 |
| replay | C3 | .52 | 20.8 | 7 | 29 | 2746 |
| injection_naive / informed | C3 | .59 / .58 | 23.6 / 23.2 | 8 / 8 | 33 / 32 | 2424 / 2462 |
| dispense_forgery / presence_spoof | C3 | 1.0 / .98 | 39.9 / 39.3 | 14 / 14 | 56 / 55 | 1431 / 1453 |
| hypertensive_spike | C1 | 1.02 | 60.9 | 21 | 85 | 938 |
| drug_nonresponse | C1 | .28 | 16.9 | 6 | 24 | 3373 |
| hypotension_below_hold | C1 | .28 | 16.6 | 6 | 23 | 3448 |
| measurement_refusal | C1 | 1.00 | 60.0 | 21 | 84 | 953 |
| double_take (injected) | C1 | 2.45 | 147 | 52 | 206 | 388 |
| double_take (natural) | C1 | | 13.6 | 5 | 19 | 4192 |
| dose_omission (natural) | C1 | | 105.7 | 37 | 148 | 540 |
| spontaneous range / resp / hold / count | C1 | | 2533 / 1184 / 107 / 110 | 886 / 414 / 38 / 39 | 3546 / 1658 / 150 / 154 | 23 / 48 / 533 / 520 |

Test positives are linear in n (n = 400 is twice the n = 200 column; n = 1200 is 1.5 times the n = 800 column). For a 5th percentile of 100 (Poisson) the mean must be 117: multiply n_100 or the rate by 1.17. Events of one injection are correlated (double_take: 2.45): Poisson understates the spread there.

Events per drawn at rates 0.3/0.6/1.0/1.7 (overlap skips): ecg_noise .99/.98/.97/.95; naive .59/.54/.50/.44; replay .52/.47/.44/.38; nav_delay, forgery, spoof about 1.0.

## 4. Class rate needed so the WORST subtype of the class reaches a test mean of 100 (x1.17 for p5)

| n | C1 (worst: hypotension, then non-response) | C2 six, cuff trio excluded (ecg_noise) | C2 with cuff trio uniform (stuck_at) | C3 uniform windows (replay) | C3 if cuff attacks anchored (forgery/spoof) |
|---|---|---|---|---|---|
| 400 | 2.4* | .88 | 3.3* | 1.9* | .72 |
| 800 | 1.22 | .44 | 1.46 | .79 | .36 (informed .37) |
| 1200 | .83 | .29 | .87 | .50 | .24 |

`*` = beyond the 1.7 run, linear extrapolation. Cuff trio anchored (earlier note): .99/.47/.31 (stuck_at with carry-over). C1 at n = 800 is also .35 for spike/refusal and .15 for double_take: only hypotension (1.22) and non-response (1.17) bind, and only because of the placeholder placement. Not class-driven, so no class rate helps: ble cuff, ble dispenser, dispenser_bounce.

## 5. Overlap, faulty days, clean days

Same-subtype overlap loss at class rates 0.3/0.6/1.0/1.7: C2 and C1 subtypes about 1/2/4/7%; the three cuff attacks (one shared overlap group) 3/8/12/19%. Clean day = no planned injection of any class, BLE windows included:

| rates C1/C2/C3 | P(clean) | P(no realised injection) | clean test days at n = 800 | P(clean) ignoring ECG/oximeter BLE |
|---|---|---|---|---|
| .3/.3/.2 | .166 | .308 | 232 | .27 |
| .6/.6/.6 | .064 | .140 | 90 | .10 |
| 1/1/1 | .019 | .052 | 27 | .03 |
| 1.7/1.7/1.7 | .002 | .010 | 3 | |
| 1.2/.6/.8 | .027 | | 38 | |

The prior BLE rate alone puts a window on 63% of the days. A day with no ground-truth event at all (natural C1 included) is 0.13% of days at the current rates.

## 6. Options for one global size (test positives from the interpolated Monte Carlo; cuff trio uniform)

| Option | cost (fixture, linear; upper bound per patient) | class-driven non-cuff subtypes below 100 | cuff trio |
|---|---|---|---|
| n 800, .3/.3/.2 | 504 s, 8.8 GB | 12 of 13 (only double_take 206) | 44/43/26 |
| n 800, .6/.6/.6 | same | 5: replay 79, naive 90, informed 88, non-response 52, hypotension 47 | 87/83/49 |
| n 800, 1.2/.6/.8 | same | none below 98 (hypotension 98) | 87/83/49 |
| n 1200, .6/.6/.6 | 756 s, 13.2 GB | 2: non-response 79, hypotension 71 | 130/125/74 |
| n 1200, .9/.45/.6 | same | none (hypotension 109) | 98/95/57 |
| n 400, 1.2 on all | 252 s, 4.4 GB | 5 (replay 69 ... hypotension 49) | 81/77/43 |

Build time per patient did not rise with the rate (0.05 to 0.06 s wall per patient on 30 processes at 0.3 and at 1.7); disk growth with rate was not measured (my runs wrote nothing). By days, a main patient costs about 0.58 s and 10 MB (the 126 s/2.2 GB includes 76 pair patients).

## 7. What more patients do not fix (structure, not size)

- **dispenser_bounce**: 0.0019 per patient-day from the literature probability; 100 test positives need about 28 000 patients, or the row about 35x at n = 800 (0.001 to 0.035, away from its source).
- **ble_dropout cuff and dispenser**: uniform windows hit a message in 9% and 4%; ECG and oximeter 100%. Anchoring to the device messages (as ADR-070 does for the cuff windows) would give about .98 (the cuff-window value of the earlier note; my arithmetic: n_100 about 230 to 260); raising the single rate row would inflate ECG/oximeter by the same factor (7.9x needed for the dispenser at n = 800). ECG/oximeter BLE and ecg_noise events are evidence-only: no template reads those signals.
- **C3 cuff attacks** (replay, naive, informed): .52 to .59 per drawn now; anchoring gives .95 to 1.00 (section 2). replay also loses day 0.
- **hypotension_below_hold**: dose-tied, only the two pre-dose readings can decide HOLD; 12 h windows reach .52, a reading-anchored window .76 at x1.0.
- **drug_nonresponse and spike**: a large part of their labelled events are natural violations that happen to lie in the window (at Emax 0.9 the share is still .52 when anchored); the injected effect adds little over the 0.59 natural RESP-violation rate per dose. Counterfactual builds (no C1 injections) were not additive (RANGE -1217, HOLD +821 against 124 labelled, RESP +1358 against 108 labelled over 35 000 pd); I did not find why (refusals remove readings; the forced double take adds doses).
- **ecg_noise**: needs the noise segment library (absent) and V <= D.
- **Robot subtypes and forgery**: reach 100 with n alone (share 1.0).

## 8. Confounder pairs (real `build_pair`, 60 pairs per variant, 19 variants)

A pair is one unit (4 day-files, half a patient); the B member (bounce, forgery, manipulation failure) is always positive. Pair positive = the A member has its labelled event: double_take_vs_bounce .93 (8 variants .90 to .97), nonresponse_vs_falsified_dispense .73 (.63 to .78), refusal_vs_robot_missed 1.00 (3 variants); overall .857. Default 2 pairs per variant = 38 pairs, about 9.5 in test. A test mean of 100 pairs means 400 pairs per variant (7 600 pairs, about 3 800 patient-equivalents), or 400 per group (1 200 pairs, about 600 patient-equivalents, x1.4 for non-response). The pair count does not depend on n or on the rates.

## 9. Not determined

Real vitals period, dwell, intake lag, adherence mean delay (they move ECG shares, nav presence and the share of late doses); the nulls of all durations and magnitudes (only the sensitivity above); whether the monitor detects any of these positives (not run); the noise library; disk growth with rate; wall time on a quiet machine; why C1 totals are not additive; the effect of an end-of-stage erasure (a realised flag is set at its stage, a later BLE window can remove the effect: expected below 1% for the cuff, not measured).
