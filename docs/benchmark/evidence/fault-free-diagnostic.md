# Diagnostic of the fault-free day (facts and numbers; the decision is gab's)

2026-10-11. Read-only on the repository. Scripts and raw output in `/tmp/research/diag/`.

## 0. Method and assumptions

- Real `BuildContext.create` and `build_patient`, injection rates 0, no pairs, registry 0.2.1 (band 110-140, delta_resp 7.5), committed `literature_hypertension.yaml`, same helpers as `obs3/real_gen.py`. Overrides are written to temp copies of the prior and design files in `/tmp`; nothing in the repo changed.
- Empty rows take fixture values (peak 14:00, intake lag 5 s, double-take gap 2 min, dwell 10 min, vitals 60 s) and `mean_delay_ms` 20 min. **Every range below is a sensitivity range, not a proposal.**
- Components per reading come from the real code: baseline from `PatientParams`; circadian from `latent.circadian` (`latent.py:221`, `sbp = (baseline + circ) + noise` at `:308`); drug from `OneCompartmentEmax` (`pkpd.py:408`, effect = Emax*sum C/(EC50+C_total)); AR as the residual; cuff = observed minus latent (`measurement.py:941-945`: latent held at arrival + inflation, plus N(0,8)).
- Sizes: decomposition 400 patients x 7 days (2800 days, 13 931 readings); ablations 400; peak scan 300; Option 2 scans 200; sensitivity 40 per run (common random numbers, same patients in every run, so differences between runs are parameter effects). B1 on every day, B3 on a subset (140 to 1400 days). Binomial SE of a share: about 1 point at 400 patients, 1.4 at 200.
- The base run reproduces the earlier figures (53.1% out, by reading 43.5/51.8/80.5/54.7/35.0%, B1 day 95.4%, B3 99.8%).

## 1. Decomposition

Mean by reading (mmHg), obs = baseline + circadian - drug + AR + cuff (sums checked to 0.1):

| reading | observed | baseline | circadian | drug | AR+cuff | SD obs |
|---|---|---|---|---|---|---|
| 06:15 | 136.0 | 149.2 | -5.9 | -7.0 | -0.4 | 15.1 |
| 08:15 | 139.5 | 149.2 | +0.9 | -10.8 | +0.2 | 14.8 |
| 14:15 | 153.5 | 149.2 | +13.3 | -9.0 | -0.1 | 16.0 |
| 20:15 | 141.3 | 149.2 | -0.9 | -6.9 | -0.1 | 15.0 |
| 22:15 | 131.2 | 149.2 | -7.4 | -10.7 | +0.1 | 14.8 |
| mean | **140.3** | 149.2 | 0.0 | -8.9 | -0.1 | 16.9 |

Variance (mmHg^2, all readings pooled 285; per reading 219-256): baseline 75 (SD 8.7 across patients, prior 9.0), circadian 64 (pooled; 0.2 at 08:15 and 20:15, 34 at 14:15), drug 6, AR 77 (SD 8.8, rho 0.22 per 30 min, so readings 2 h apart are uncorrelated, measured 0.00-0.03), cuff 65 (SD 8.05). Shares 26/23/2/27/23%.

Drug effect: perfectly adherent steady state at the five instants 8.6/11.5/9.7/7.6/11.2 mmHg (day 0: 0.0/9.3/7.4/5.5/10.5, no prior dose; steady from day 3). Adherence model (5.7% omissions, 8.1% late, 0.31% double): days >= 1 8.1/11.2/9.3/7.3/10.8, SD about 1 mmHg, 1.89 doses per day; cost 0.4 points of out-of-band share.

Ablation (out-of-band share, 400 patients; the subsets "baseline" + any of circ, drug, AR, cuff = switched on):

| configuration | out | 06:15 | 08:15 | 14:15 | 20:15 | 22:15 | B1 day |
|---|---|---|---|---|---|---|---|
| baseline only (patient spread 8.7) | 84.8 | 84.8 | 84.7 | 84.7 | 84.8 | 84.8 | 85.3 |
| + circadian | 78.0 | 65.1 | 86.5 | 98.5 | 82.3 | 57.8 | 98.5 |
| + drug | 52.0 | 59.1 | 44.4 | 50.8 | 60.9 | 45.1 | 65.2 |
| + AR | 77.1 | | | | | | 97.3 |
| + cuff | 78.0 | | | | | | 96.1 |
| circadian + drug (no noise) | 49.0 | 35.0 | 48.0 | 89.3 | 56.3 | 16.6 | 90.4 |
| all but cuff | 50.9 | 39.5 | 49.5 | 82.7 | 54.9 | 27.9 | 93.5 |
| all but AR | 51.2 | 39.5 | 49.5 | 83.8 | 55.1 | 28.1 | 92.3 |
| all but circadian | 52.8 | 56.1 | 49.8 | 52.1 | 57.6 | 48.5 | 91.8 |
| all but drug | 71.0 | 58.9 | 76.3 | 91.7 | 71.7 | 56.3 | 98.5 |
| all, patient baseline fixed 149.3 | 51.3 | | | | | | 98.6 |
| all, perfect adherence | 52.7 | | | | | | 95.4 |
| **all (committed)** | **53.1** | 43.5 | 51.8 | 80.5 | 54.7 | 35.0 | 95.4 |

(Rows "all but cuff" use cuff SD 0.001, because 0 makes the builder refuse the bias magnitudes.) Shapley values of the four components, from the 16 subsets, relative to baseline-only 84.8: drug **-24.9**, circadian -2.8, AR -2.2, cuff -1.8, total -31.7. Reading: the 53% is the untreated population (85% out) pulled down by the drug to a treated mean of 140.3, the upper band edge. Noise matters little at this centring and a lot once the mean is centred (section 4).

## 2. Why 14:15 reaches 80%

At 14:15: baseline 149.2 + circadian 13.3 - drug 9.0 = 153.5, SD 16.0, so P(>140) is 0.80 (Gaussian check by reading: 43.7/50.9/80.4/55.3/35.3%). Against 08:15 the 14.0 mmHg gap splits into circadian +12.4 and drug +1.8 (the effect is 10.8 at 08:15 and 9.0 at 14:15, all days).

- **Drug curve (`literature_hypertension.yaml`: ka 2.3 /h, ke 0.0815 /h).** Peak at 1.51 h, half-life 8.5 h (proposal ranges 1.4-4.2 /h and 0.069-0.099 /h). Single dose: effect 9.27 mmHg at 1.25 h, 7.45 at 7.25 h (C 0.878 vs 0.574). With both doses at steady state the effect is only 11.5 (08:15) against 9.7 (14:15), 7.6 (20:15), 11.2 (22:15): a total swing of 4 mmHg over the day. The curve is flat because Emax*C/(EC50+C) saturates (EC50 0.76 against C of 0.5-1.5). The drug is not what makes 14:15 special.
- **Circadian.** A = 13.2 (SD 6.1), fixture peak 14:00: +13.3 at 14:15 (cos about 1), +0.9 at 08:15, -7.4 at 22:15.
- Shares at 14:15 (Shapley, from baseline-only 84.7): circadian **+23.6** points, drug -20.3, AR -4.1, cuff -3.5. Switching off in turn: no circadian 52.1 (-28.4), no drug 91.7 (+11.2).
- **Dependence on the peak clock (sensitivity range, all 12 peaks 00:00-22:00 in steps of 2 h, 300 patients):** share at 14:15 is 31.8/32.1/31.2/36.7/49.6/66.3/76.3/80.4/78.0/68.9/54.3/39.7% for peaks 00, 02, ... 22. So the 80% **depends on the fixture peak** (it needs a peak within about 3 h of 14:15). **The overall share does not:** 52.9-56.1% across all 12 peaks (53.0% with amplitude 0), and the worst reading is always 70-82%, because one of the five readings sits near the peak. What the peak chooses is which reading is the bad one. No acrophase source exists in the repo or `/tmp/research`; the range is an assumption.

## 3. Sensitivity to the empty rows

Design: 51 one-at-a-time runs (centre plus 5 levels per row) and a 240-run scrambled Latin hypercube over 10 rows (scipy `qmc`, seed 20261011), 40 patients x 7 days per run. Ranges (sensitivity ranges, not proposals, assumptions unless noted):

| row | range | p_out over its 5 levels | B1 day | range/d | resp/d | hold/d | other |
|---|---|---|---|---|---|---|---|
| circadian_peak_clock_ms | 08:00-18:00 | 51.6-55.8 | 93.6-95.4 | 2.51-2.71 | 1.10-1.27 | 0.068 | |
| intake_lag_ms | 0-10 min | 52.92 (identical) | 94.3 | 2.496 | 1.164-1.171 | 0.068 | |
| double_take_gap_ms | 11-120 min | identical | identical | 2.496 | 1.164-1.179 | 0.068-0.082 | double take 0.032-0.036 |
| mean_delay_ms | 5-120 min (log) | 52.92-52.99 | 94.3 | 2.496-2.504 | 1.146-1.182 | **0.011-0.082** | |
| vitals_period_ms | 1, 5, 15, 30 min | identical | identical | 2.496 | 1.164 | 0.068 | ble_dropout events 0.65 to 0.375 |
| robot_dwell_ms | 1-30 min | identical | identical | 2.496 | 1.164 | 0.068 | |
| inflation_ms_nominal / _sd | 20-50 s / 0-14 s (device means 19-51 s, max within-device SD 14 s) | identical | identical | 2.496 | 1.164 | 0.068 | |
| pulse_error_sd_bpm | 1-6 bpm | identical | identical | same | same | same | |
| ble_dropout_rate_per_h (filled row, included: it moves B1) | 0-0.167 | 52.4-53.1 | 93.9-96.4 | same | same | same | ble events 0 to 8.1/d |

Five rows (vitals period, dwell, inflation x2, pulse error) leave out-of-band share, B1 and RANGE/RESP/HOLD events unchanged to four decimals; intake lag and double-take gap leave the pressure unchanged to four decimals and move RESP by at most 0.015 per day. `spontaneous_count` (0.118/d) and `dose_omission` (0.129/d) do not move in any run.

Joint design (240 runs): out-of-band share **51.2-56.7%** (5-95%: 51.7-56.3; centre 52.9; SD 1.6 points); B1 day 92.9-96.4%; B3 98.6-100%; range/d 2.48-2.72; resp/d 1.12-1.31; hold/d 0.014-0.100. Variance of the out-of-band share (8-bin first-order index; additive quadratic fit in brackets, R^2 0.70, which misfits the periodic peak): peak clock **86%** (69%); ble_dropout rate 11% (1%); every other row 1-5% (the estimator's noise floor is about 3%). For `spontaneous_resp` the peak clock explains 95%; for `spontaneous_hold` `mean_delay_ms` explains 86% (a late dose is dispensed far from the last reading). For B1 day: peak 37%, ble rate 37%.

Answer: the empty rows can move the 53% by roughly -2 to +4 points, almost entirely through the peak clock; they cannot explain it.

## 4. Option 2 separately

Runs of 200 patients each (1400 days; band centre 125; the five slot means averaged). Out of band / B1 day / events per patient-day (range, resp, hold):

(a) **drug only** (committed Emax 17.3, EC50 0.76):

| Emax x | 0.5 | 1 | 1.5 | 2 | 2.5 | 3 |
|---|---|---|---|---|---|---|
| mean of slot means | 144.7 | 140.3 | 135.8 | 131.4 | 127.0 | 122.5 |
| out of band | 61.4 | 52.7 | 45.1 | 40.3 | **39.5** | 42.2 |
| B1 day | 96.7 | 95.4 | 94.0 | 91.9 | 92.1 | 93.6 |
| range / resp / hold | 3.08/1.24/.07 | 2.51/1.15/.08 | 2.06/1.03/.08 | 1.77/.93/.09 | 1.72/.85/.11 | 1.86/.77/.14 |

EC50 x 4/2/1/0.5/0.25/0.1 (0.76 times): out 62.8/57.7/52.7/47.9/44.2/42.0, mean 145.3/143.0/140.3/137.7/135.6/133.9, resp/d 1.15-1.21, B1 97.4 to 92.1. Mean of slot means = 125 at Emax x**2.72** (47 mmHg); out-of-band minimum near x2.4 (parabola; grid x2.5: 39.5%). EC50 alone cannot centre: as EC50 goes to 0 the effect tends to Emax = 17.3, mean about 131.9. Joint Emax x2, EC50 x0.5: 38.9% (mean 126.2). **Against the proposal:** Emax 17.3 with label-rounding range 15.1-19.9 (`parameter-literature-proposal.md`); x2.4-2.7 is 41-47 mmHg, 2.1-2.4 times the top of that range, and a mean effect of 22 mmHg against the label's 7.5-9 mmHg trough reductions. EC50 0.38 (25 mg unit) to 0.76 (12.5 mg): x0.1 is 5 to 10 times below. No repo source supports either; a combination-therapy effect would need its own source.

(b) **baseline only** (prior mean 149.3, SD 9.0; truncation moved with it at mean +/- 3 SD):

| mean shift (mmHg) | -25 | -20 | -15 | -10 | -5 | 0 |
|---|---|---|---|---|---|---|
| out, SD 9 | 46.2 | 39.9 | **37.4** | 37.9 | 43.8 | 52.7 |
| out, SD 0 | 41.0 | 32.8 | **30.0** | 32.0 | 39.6 | 51.6 |
| out, SD 4.5 / 13.5 | 43.0/50.9 | 35.9/46.1 | 31.5/44.2 | 33.8/44.5 | 40.5/48.9 | 51.0/55.2 |
| B1 day, SD 9 / SD 0 | 93.6/93.9 | 91.4/86.8 | 90.6/83.9 | 90.1/87.0 | 93.3/94.4 | 95.4/98.6 |
| range/d, SD 9 | 2.13 | 1.70 | 1.55 | 1.61 | 1.97 | 2.51 |
| resp/d | 1.15 throughout | | | | | |
| hold/d, SD 9 | 0.31 | 0.20 | 0.13 | 0.10 | 0.08 | 0.08 |

Minimum near -13 to -15 (baseline mean 134-136; the slot mean reaches 125 at -15.3). Shift -30: 54.7% out, 50% below 110, hold 0.50/d. **Sources:** the 149.3 is the untreated 24-h MESOR of 47 outpatients (Cornelissen 2025); a mean of 134 would describe a milder untreated cohort, not "treated and controlled". The only downward shift with a source in the repo is -4.3 (SD 10.4) mmHg, daytime inpatient against outpatient (Pikilidou 2010); the -5 run gives 43.8% out, B1 93.3%. Treated inpatients' clinic SBP in the other cross-check is higher (160.8, Xu 2013). **Floor:** a constant 125 with AR and cuff only gives 21.0% (analytic 2(1-Phi(15/11.9)) = 20.8%), B1 day 70%, 1.05 out readings per day. With the committed circadian amplitude 29.4% (B1 82.6%); with patient SD 9 and no circadian 30.5%.

(c) Best achievable (out % / days with any out-of-band reading %; the B1 day-alarm rate is within 0.3-1.3 points of the latter at 110-140; widened bands are arithmetic on the stored readings, B1 extras not rerun):

| case | 110-140 | 105-145 | 100-150 |
|---|---|---|---|
| committed | 52.7 / 95.1 | 39.0 / 87.0 | 27.4 / 74.0 |
| (a) alone, Emax x2.5 | 39.5 / 91.5 | 26.2 / 78.1 | 16.1 / 58.1 |
| (b) alone, shift -15, SD 9 | 37.4 / 90.0 | 23.3 / 72.9 | 13.8 / 52.6 |
| (a)+(b), Emax x1.5, shift -10 | 37.8 / 90.4 | 23.9 / 73.6 | 14.4 / 54.4 |
| (b), shift -15, SD 0 | 30.0 / 83.1 | 16.6 / 58.6 | 8.2 / 34.6 |
| floor: const 125, AR+cuff only | 21.0 / 68.7 | 8.8 / 36.2 | 3.3 / 15.4 |

Combining (a) and (b) does not beat (b) alone (grid minimum 37.8%). With the committed patient SD 9, AR 8.8 and cuff 8.0, no tested combination brings the B1 day-alarm rate under 90% with the 110-140 band (best 90.1%; with patient SD 4.5, 86.8%; SD 0, 83.9%).

## 5. Natural event load (fault-free; 2800 days committed, 1400 days the other columns)

| per patient-day | committed | (a) Emax x2.5 | (b) shift -15 SD 9 | floor (const 125, AR+cuff) |
|---|---|---|---|---|
| spontaneous_range | 2.54 | 1.72 | 1.55 | 0.43 |
| spontaneous_resp | 1.15 | 0.85 | 1.15 | 1.40 |
| spontaneous_hold | 0.07 | 0.11 | 0.13 | 0.08 |
| spontaneous_count | 0.12 | 0.12 | 0.12 | 0.12 |
| days with no spontaneous event | 0.4% | 1.8% | 2.0% | 4.1% |
| days with no ground-truth event | 0.11% | 0.6% | 0.6% | 1.2% |

The earlier 2.53 range, 1.18 resp and 0.13% empty days are confirmed (2.54, 1.15, 0.11% here; ble_dropout natural 0.55/d is part of the ground truth). Two mechanisms:

- **RANGE counts the latent trace, not the observed one**: 2.533 latent scheduled readings per day out of band against 2.543 events (observed readings: 2.64). The floor has 0.43 events but 1.05 observed out-of-band readings: cuff noise creates B1 alarms that are not events.
- **RESP**: an instance is violated when pre-dose minus post-dose latent reading (06:15 to 08:15, 20:15 to 22:15) is below 7.5. Latent drop: -3.07 (SD 13.1) for the 07:00 dose, +10.35 (SD 12.8) for the 21:00 dose; violation 0.79 + 0.42 = 1.21 per day, times 0.945 of doses taken = 1.15. Causes: (i) the drug swing between trough and peak is only 2.9-3.6 mmHg at steady state (8.6 to 11.5; 7.6 to 11.2), against delta_resp 7.5, so a noise-free steady-state patient violates RESP at every dose (1.75/d in the "baseline + drug" run); (ii) the fixture circadian peak adds a +6.8 rise between 06:15 and 08:15 and a -6.5 fall between 20:15 and 22:15, so the morning dose looks like a rise. The 7.5 is a label effect against placebo, not a steady-state pre/post change. RESP events move with the peak clock (1.10-1.27) and with Emax (0.77 at x3) and not with the baseline.

## 6. Could not determine

A source for the acrophase or for a treated-controlled baseline; B5 and the monitor under any setting (not run); B3 on more than 20 patients per Option 2 configuration; peak-by-amplitude interaction (amplitude not varied); the care-plan tick times were taken as built from the registry windows.
