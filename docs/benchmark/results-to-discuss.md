# Results to discuss in the paper

A list kept by the coordinator of facts that the analyses produced and that the authors may want to discuss. It is not paper text (the paper is the authors' work, ADR-037) and none of these figures is a result of the final experiment: they come from the analyses in `docs/benchmark/evidence/`, run on the generator with labelled sensitivity ranges for the rows that still have no value. Technical, pre-clinical; nothing here is a clinical validation. Each entry names the decision that records it.

## 1. RESP separates responders from non-responders at chance level for one dose, and well over several days (ADR-072 (d))

| Statistic | Reference | AUC | True-positive rate at 5% false positives |
|---|---|---|---|
| Current RESP, one pre/post pair per dose | the pre-dose reading | **0.55** | 0.07 |
| Level over 5 treated days | the patient's own 5 untreated run-in days | **0.965** | 0.82 |
| Level over several days | the population untreated mean (149.3 mmHg) | at most 0.78 | 0.26 |

Why: with twice-daily dosing the drug effect swings only 2.9-3.6 mmHg between trough and peak, against `delta_resp` 7.5 mmHg, and the SD of a single pre/post difference is 16.8 mmHg (AR noise, cuff noise, circadian term). Separating at 5% error and 80% power takes 165 doses (82 days) with the current rule, and 5 + 5 days with the patient's own run-in. The registry value of `delta_resp` comes from the COREG label (smallest labelled mean systolic effect, trough) and was derived against the absence of the drug, while the rule compares with the pre-dose reading. Source: `evidence/resp/evidence.md`. The multi-day reformulation (R1b) is archived as future work in ADR-072.

## 2. The fault-free day is not clean (ADR-071)

53% of the readings outside 110-140 mmHg; a static-threshold rule (B1) alarms on 95.7% of the days without any fault; 2.54 natural `spontaneous_range` and 1.15 natural `spontaneous_resp` events per patient-day. The treated mean (140.3 mmHg) sits at the upper edge of the band (baseline 149.2, drug effect -8.9). Even a patient constant at 125 mmHg gives 21% of readings out of band and 70% of the days with a B1 alarm because of the cuff error alone (SD 8 mmHg on a 30 mmHg band): the share of alarms that are noise and not events is what an uncertainty-aware monitor is expected to reduce. Source: `evidence/fault-free-diagnostic.md`.

## 3. A band rule detects by leaving the band, not by averaging (ADR-070 (f))

For a silent cuff bias of m times the cuff SD over k readings the detection probability of a band rule is 1 - (1 - p(m))^k, not a function of m*sqrt(k): at equal z = m*sqrt(k) the probability differs by k (z = 1: 0.31 / 0.46 / 0.57 for k = 1, 2, 3). A mean-offset test has power Phi(m*sqrt(k) - 1.645) exactly. Source: `evidence/group1-bias-model.md`.

## 4. Most of the injected positives of two C1 subtypes exist without the injection (ADR-071 (f))

A 5 mmHg hypertensive spike is a labelled positive in 50% of the draws and a non-response with Emax 0.9 in 21% of them without the injection having any effect; evaluate these two subtypes on the excess over the background. Source: `evidence/benchmark-size-all-subtypes.md`.

## 5. Open comparisons that must not be reported yet

B3 and B5 are silent on INT and SYS violations that the monitor reports (ADR-063, proposed); B5 predicts only RESP while the proposed method predicts SCHED and RESP (D2, open); see the Conclusion of `docs/plan/workstreams/WS06-baselines/notes/fairness-audit.md`.
