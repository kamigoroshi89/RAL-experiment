# Evidence: RESP reformulations and `drug_nonresponse` (2026-10-11)

Read-only on the repository (HEAD 0feb140, copy in `/tmp/research/resp/repo`; scripts `sim*.py` model, `real1.py`, `real2.py` real builder at rates 0, registry 0.2.1). **Ranges and design sizes (m run-in days, n treated days) are sensitivity values, not proposals.**

## 0. Method and assumptions

Real `OneCompartmentEmax` (Emax 17.3, EC50 0.76, ka 2.3, ke 0.0815, per-intake scales as the C1 injector sets them) and real `circadian`. Readings 06:15, 08:15, 14:15, 20:15, 22:15; doses 07:00, 21:00. Per reading: AR SD 8.8 (readings 2 h apart: correlation 0.002, taken as 0) and cuff SD 8, so 11.9 observed and 8.8 latent (the labeller's view); a pair difference has SD 16.8 observed, 12.4 latent. Circadian: fixture peak 14:00, amplitude N(13.2, 6.1), acrophase assumed. Every patient has the same Emax (no spread in the committed prior; real spread would worsen every number). Conventions: one-sided 5% test and 80% power (d' = 2.49); TPR is read at 5% false-violation rate; AUC = P(non-responder scores above responder).

Check on the real builder (200 patients x 7 days): violation per dose 0.78 / 0.41 at steady state (model 0.77 / 0.40), day 0 0.66 / 0.31 (model 0.65 / 0.36); SD of the daily mean 5.33 observed, 4.00 latent (model 5.37, 4.0).

## 1. The current RESP (single pair 06:15 to 08:15, 20:15 to 22:15)

| case (observed) | D = pre - post, responder | P(viol) | non-responder D | P(viol) | AUC, 1 dose |
|---|---|---|---|---|---|
| steady state 07:00, persistent NR | -3.8 | 0.745 | -6.7 | 0.797 | 0.548 |
| steady state 21:00, persistent NR | 10.1 | 0.441 | 6.5 | 0.524 | 0.559 |
| 07:00 dose alone scaled 0 (current injection) | -3.8 | 0.745 | -10.5 | 0.853 | 0.609 |
| 21:00 dose alone scaled 0 | 10.1 | 0.441 | 3.0 | 0.605 | 0.615 |
| first dose, day 0 (circadian fixture) | 2.6 | 0.613 | -6.7 | 0.797 | 0.649 |
| first dose, circadian known | 9.3 | 0.458 | 0.0 | 0.672 | 0.652 |

The steady-state swing between pre and post effect is 2.9 (morning) and 3.6 (evening) mmHg against delta_resp 7.5, so the circadian term (-6.7 / +6.5) decides. The AUC does not depend on delta_resp; at a 5% false-violation rate delta_resp would be about -32 / -18 mmHg and TPR 7% / 8%.

Pooled over n doses (circadian cancels over a morning plus evening pair): AUC 0.55 (1), 0.58 (2), 0.61 (4), 0.70 (14 = 7 days), 0.77 (28); 165 doses (82 days) for 5%/80%. Ceiling of any pair: with the pre-dose value exact, d' = 0.27 (AUC 0.58) for one post reading, 0.55 (AUC 0.65) for four averaged. More post readings under the max rule: AUC 0.555 to 0.563 (k = 1..4), P(viol | responder) 0.60 to 0.29.

Labeller view of the current injection, steady state, P(label) responder / dose scaled 0.0 / 0.5 / 0.75: morning 0.81 / 0.92 / 0.87 / 0.84; evening 0.42 / 0.64 / 0.53 / 0.48. Share of labelled events caused by the injection: 12% and 34% (scale 0), 7% and 21% (0.5), 4% and 12% (0.75): the "positives mostly natural" of `benchmark-size-all-subtypes.md` (realised share 0.28). A one-day complete non-response lowers the daily mean effect by 5.3, 3.8, 0.5 mmHg on that day and the next two.

## 2. Reformulations

Drug effect on the daily mean of five readings: 6.2 (day 0), 9.1, 9.3, then 9.4 mmHg; SD of a daily mean 5.4. After a persistent switch to scale 0 the shortfall is 5.3, 9.1, 9.6 mmHg on the switch day and the next two.

| option | statistic | shift, SD (mmHg) | AUC | TPR 5% | days for 5%/80% |
|---|---|---|---|---|---|
| **R1a** n-day mean vs population untreated 149.3 | n=7 | 8.9, 8.9 | 0.76 | 0.26 | never: baseline SD 8.7 caps d' at 1.08 (AUC 0.78) |
| **R1b** n treated vs m run-in days, same slots | (3,5) / (5,5) / (7,7) | 8.7, 3.9 / 8.7, 3.4 / 8.9, 2.9 | 0.94 / 0.965 / 0.986 | 0.72 / 0.82 / 0.93 | m=3: 9; m=5: 5; m=7: 4; m=inf: 3; m<=2: not reached |
| **R1c** n days after vs m earlier treated days (loss) | m=5, n=3 / n=5 | 8.0, 3.9 / 8.7, 3.4 | 0.925 / 0.965 | 0.65 / 0.82 | as R1b; CUSUM (4.4% false alarm in 15 days) alarms within 7 days of the loss in 82% |
| **R2a** first dose, current pair | one pair | 9.3, 16.8 | 0.65 | 0.14 | 1 dose only |
| **R2b** first 24 h / 48 h post readings vs m=3 run-in | mean of 4 / 9 | 8.2, 6.9 / 8.9, 5.0 | 0.80 / 0.89 | 0.32 / 0.55 | not reached |
| **R2c** dose change x2 | before vs after | +2.7 (2.3 to 3.0 by slot), 5.4 | | | m >= 26 days; n = m: 51 days each |
| omission contrast (not a template) | missed 21:00 dose | d' 0.54 per event | | | 21 events = 185 days |

R1b errors with the threshold at half the effect (about 4.3 mmHg; no source), observed / latent: P(viol | responder) 0.13 / 0.07 (3,5), 0.10 / 0.04 (5,5), 0.06 / 0.02 (7,7); P(viol | NR) 0.87 / 0.93, 0.90 / 0.96, 0.94 / 0.98; scale 0.5 gives 0.50 by construction. **With the registry delta_resp = 7.5 as level threshold** the responder margin is 1.2 mmHg at (5,5) (the model's trough effect is 7.6 to 8.6): P(viol | responder) 0.38 / 0.34 (3,5), 0.36 / 0.32 (5,5), 0.32 / 0.26 (7,7). A threshold below 7.5 has no literature source.

## 3. Interaction with the monitor

- **Three-valued semantics.** Instance anchored at treatment start (or a review day), k_d = anchor + n days. Unseen readings are bounded by bound_bp_lower/upper (30, 260), so no early decision: PENDING for the whole window. `max_latency_resp` (2 h 01 min) becomes n x 24 h + step. R1c with a rolling instance would emit a violation per day; a merge rule is needed (05, 3.8).
- **History.** `MAX_HISTORY_DAYS` = 14, so m + n <= 14; the builder history H must count m + n days.
- **Rho and conformal.** `difference_rho` is Gaussian on one pair; a mean needs SE = 11.9 sqrt(1/N + 1/M) under independence (declared). The predictive step has nothing to predict at the anchor (ADR-060); a mid-window prediction needs its own calibration. B5 loses its only continuous predictive path. n_tests per day falls from 7 to 5.
- **Baselines.** B1, B2, B4 do not read RESP. B3 and B5 run one day at a time (ADR-061 proposed): R1 needs it accepted and both evaluators changed.

## 4. What each needs

- **Spec.** R1: RESP changed in place (TemplateId kept) with derived signals `bp_ref` (frozen at the anchor, like `bp_pre`) and a rolling mean. The grammar (02, 1.2) has no mean; `once` is a maximum, which over 5n noisy readings is satisfied by a non-responder too. New names for n, m and a level threshold. R2: a care-plan event "dose start / dose change" (none exists) creating the instance instead of every dispense.
- **Reference.** R1a: not identifiable per patient. R1b: untreated days; an inpatient/outpatient offset of a few mmHg (`fault-free-diagnostic.md` 4b) would eat part of the 9.4 margin if the run-in came from another setting. R1c: own history.
- **Generator.** `schedule.py`: the same schedule every day; no dose-change event. Every patient starts untreated, so day 0 is a first dose already (R2a needs no change). R1b needs a dose-start day with no dispense before it (adherence, schedule, plan instances).

## 5. `drug_nonresponse` as an injection

| option | injection | P(label) NR scale 0 vs natural | caused by injection | patients for 100 test positives |
|---|---|---|---|---|
| current / keep | window of hours | 0.92 vs 0.81 (am), 0.64 vs 0.42 (pm) | 12% to 34% | 3373 (27k patient-days) |
| R2a | day-0 doses | 0.87 vs 0.65 | 25% | label does not separate |
| R1b (5,5) | persistent patient state from dose start | 0.96 vs 0.04 | 96% | share q of patients: 0.1 / 0.25 / 0.5 gives 4167 / 1667 / 833 (46k / 18k / 9k patient-days) |
| R1c | state from day d0 to the end (the injector refuses windows crossing midnight) | same | same | same |

Positives = 0.25 N q P. The label (phi_CP on the latent days, history m + n) begins at the anchor and ends at the decision n days later, not at the Emax change (ADR-064 allows an onset in an earlier day). Pair `nonresponse_vs_falsified_dispense`: pressure cannot separate NR from a forged dispense or a dispense without intake under any option (zero exposure in both); witness and authentication still do (DX-02 unchanged). Pair positivity rises from 0.73 to 0.96 (R1b) but the unit grows from 4 day-files to 22, and the forgery member must forge every dose of the window (new design). The `resp` backing in attribution must read the doses of the window.

## 6. Keep and declare, or narrow

Keep: RESP at steady state is violated at 58% of doses because the committed swing (3.3 mmHg) is below delta_resp (7.5), whatever the responsiveness (AUC 0.55); `spontaneous_resp` 1.15 per patient-day is declared (ADR-071 (a)); `drug_nonresponse` is reported as a confounder class that RESP detects at chance level. Narrow to initiation: day 0 is the only swing above delta_resp (9.3), yet a responder violates at 0.65 (latent): no detection gained.

## 7. Cost of reopening M1 (own estimates from analogue tasks, plus or minus 40%)

| option | person-days | documents and golden files | code |
|---|---|---|---|
| keep and declare | 0.5 to 1 | note in 02 4.5, ground-truth.md; none move | none |
| R4 narrow claims | 1.5 to 2 | none | eval filter |
| R2 | 10 to 12 | 02 (3.1, 4.5, 5), 05 (6.2); golden templates, verdicts, patient-day | plan event, load_plan, labeller |
| R1c | 20 to 25 | 01, 02, 03, 05, 06, 07 to 09; five golden files (about 110 RESP lines); `#signals` bump | RespInstance, measured_rho, predictive, labelling, inject_c1, builder, pairs, B3/B5, attribution; 79 test files mention resp |
| R1b | 26 to 32 | as R1c | as R1c plus dose-start in schedule, adherence, plan |

## 8. Not determined

Real spread of the drug effect; the acrophase; the monitor, B3, B5 under any reformulation (not run); a sourced level threshold; cuff faults and omissions inside the statistic.
