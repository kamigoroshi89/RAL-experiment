# Group 1: zero-offset row and a model of bias detection (facts and numbers; the decision is gab's)

2026-10-10. Read-only on the repository; scripts and outputs in `/tmp/research/obs3/`. Same hand-built day as before, real `B1StaticThresholds` and `B3PlainSTL` (registry 0.2.1, band 110-140, delta_resp 7.5); offsets added directly to the k covered readings (identical to the `cuff_silent_bias` injector in 200 random cases). First covered reading uniform, fair sign. "Covered" = alarm on a covered reading; "day" = any alarm on the day.

## 1. Zero-offset row

**The earlier 3x3 table had a zero row of 0 by construction** (its readings were observed values, uniform in band). A real reading is latent value plus cuff noise (SD 8), which alone puts 21% of in-band latent values outside the band. Two models:

- **O**: observed readings i.i.d. uniform in the band (the previous table).
- **L**: latent uniform in the band plus N(0, 8) plus the offset. Closed form (checked against quadrature and 60 000 real-B1 trials), G(u) = u Phi(u) + phi(u), w = 30, s = 8, d = m s: P(in band) = (s/w) [G((w-d)/s) - 2 G(-d/s) + G((-w-d)/s)], p(m) = 1 - its mean over the sign; k readings: 1-(1-p)^k.

B1 alarm on covered readings (model L, real B1, 20 000 trials per cell, 60 000 at m = 0; 95% half-width 0.003-0.007; analytic within 0.005):

| m \ k | 1 | 2 | 3 | excess over zero row (k=1/2/3) | share of the cell's alarms already present at m = 0 |
|---|---|---|---|---|---|
| **0 (no fault)** | **0.213** | **0.380** | **0.513** | 0 | 100% |
| 1.0 | 0.311 | 0.526 | 0.674 | +0.096 / +0.146 / +0.159 | 69% / 72% / 76% |
| 1.5 | 0.415 | 0.660 | 0.795 | +0.199 / +0.278 / +0.283 | 52% / 58% / 64% |
| 2.5 | 0.654 | 0.885 | 0.960 | +0.442 / +0.501 / +0.445 | 32% / 43% / 54% |

Model O (cells 0.265-0.964, zero row 0/180 000) agrees with the earlier table. Per day (5 readings): zero row 0.698 +- 0.004 (N = 180 000), cells 0.73 to 0.975. Paired runs show the offset also deletes alarms: at m=1, k=1 it creates an alarm in 18.2% of trials and removes one in 8.5% (net +9.6%).

B3 zero row (day, 500 trials per case, half-width 0.014-0.03): i.i.d. O 0.920, i.i.d. L 0.974 (a RESP artefact: no dose drop); structured pre/post (post = pre - d), no noise: 0.000 (0/1500 for d = 10 and 20); with noise, d = 20: 0.87-0.91 (B1: 0.80).

**Real generator, fault-free** (what I could obtain without the full build). Used: the builder's own `build_patient` with injection rates 0 and no pairs, 400 patients x 7 days (2800 days, 13 931 readings), the committed `literature_hypertension.yaml` (unverified; `mean_delay_ms` is the only unfilled row: stand-in 20 min), registry `hypertension.yaml` with `allow_fixture_only`, and the fixture-only design rows of the `test_builder.py` helpers (circadian peak 14 h, inflation 30 s). Stand-ins: those design rows and mean_delay. The patient distribution is the committed prior (baseline N(149.3, 9)).

| quantity (fault-free) | value |
|---|---|
| readings outside 110-140 | 53.1% (cluster-bootstrap 95% CI 51.1-55.1); above 49.9%, below 3.2% |
| by reading (06:15 / 08:15 / 14:15 / 20:15 / 22:15) | 43.5 / 51.8 / 80.5 / 54.7 / 35.0% |
| days with at least one out-of-band reading | 95.1% (2800 days) |
| B1 alarm on a day (120 patients, 840 days) | 95.7%; mean 2.6 alarms per day |
| B3 alarm on a day (same days) | 99.9%; mean 3.9 alarms per day |
| B1 on covered readings, k = 1 / 2 / 3, no offset | 0.531 / 0.776 / 0.912 |
| same, with fair-sign offset m = 1.0 / 1.5 / 2.5, k = 1 | 0.547 / 0.572 / 0.645 |
| same, k = 3 | 0.897 / 0.888 / 0.885 (below the no-offset 0.912) |

B1 alarms on almost every fault-free day; a bias of 8 mmHg moves the per-reading rate by 1.6 points (97% of the alarms exist without the fault). The 06:15 to 08:15 mean drop is -3.5 mmHg (fixture circadian peak), so I make no claim on RESP from this run.

**Sensitivity to band occupancy** (latent distribution, L-type noise 8 added, analytic, per reading; these are sensitivity cases, not the truth):

| latent distribution | p(m=0) | p(1.0) | p(1.5) | p(2.5) | share of the m = 1.5 alarm already at zero |
|---|---|---|---|---|---|
| uniform in band | 0.213 | 0.311 | 0.415 | 0.654 | 51% |
| concentrated N(125, 5) | 0.112 | 0.236 | 0.377 | 0.702 | 30% |
| wide N(135, 10) | 0.374 | 0.422 | 0.478 | 0.627 | 78% |
| tail U[110, 150] (25% above band) | 0.340 | 0.396 | 0.459 | 0.625 | 74% |
| N(149.3, 9) (prior mean, no drug) | 0.781 | 0.736 | 0.692 | 0.617 | offset lowers the rate |

## 2. A model on amplitude and k

Data: exact analytic B1 surfaces (L and O) on m = 0, 0.25, ..., 3, k = 1-3 (real-B1 MC, 10 000 per cell, differs by <= 0.010), and real-B3 MC on the structured day (O, d = 20, 400 per cell, SE <= 0.025). Least squares on probabilities. P1: train m = 0, .25, .75, ..., 3, test m = .5, 1, 1.5, 2, 2.5; P2: train on the 9 grid cells, test the other 30 (m > 0); P3: train k = 1, 2, test k = 3. RMSE / max error:

| candidate (parameters) | B1-L P1 | B1-L P2 | B1-L P3 | B1-O P1 | B1-O P2 | B3 P1 |
|---|---|---|---|---|---|---|
| (i) logistic/probit in z = m sqrt(k) (2) | .086 / .154 | .099 / .289 | .121 / .236 | .052 / .110 | .045 / .095 | .086 / .254 |
| (ii-geo) 1-(1-min(1, m s/w))^k (0) | .080 / .210 | .110 / .337 | .122 / .337 | **0 / 0** | **0 / 0** | .185 / .354 |
| (ii-fit) 1-(1-logistic(a+b m))^k (2) | **.021 / .037** | **.024 / .077** | **.015 / .026** | .041 / .082 | .049 / .167 | .090 / .273 |
| (iii) logistic in (log m, log k) (3, m > 0 only) | .061 / .118 | .121 / .378 | .069 / .163 | .035 / .053 | .050 / .112 | .075 / .223 |

Findings:

1. **z = m sqrt(k) does not collapse B1.** At equal z the detection differs by k: z = 1: 0.311 / 0.458 / 0.573 for k = 1/2/3 (spread 0.26); z = 2: 0.534 / 0.634 / 0.713 (0.18); z = 3: 0.765 / 0.809 / 0.850 (0.09). Model O: spreads 0.13, 0.14, 0.04. A band rule detects by leaving the band (k enters as the number of chances, 1-(1-p)^k), not by averaging. A z-logistic misses held-out cells by up to 0.15-0.29.
2. **Form (ii) is right for B1** with k separate: exact (zero parameters) for model O, and 2 fitted parameters give max error 0.04-0.08 for model L, where the zero-noise geometry fails (RMSE 0.08) because cuff noise adds p(0) = 0.21. Form (iii) is worse, and undefined at m = 0.
3. **The single index is right for a mean-offset test**: a one-sided z test at 5% on the mean of k residuals (cuff noise SD known) has power Phi(m sqrt(k) - 1.645) exactly (simulated, 400 000 draws: 0.683 vs 0.683 for m=1.5, k=2). Grid cells with sigma_eff = 8 (forecast perfect) / 11.9 (latent AR variability left in):

| m \ k | 1 | 2 | 3 |
|---|---|---|---|
| 1.0 | .26 / .17 | .41 / .24 | .54 / .32 |
| 1.5 | .44 / .26 | .68 / .41 | .83 / .54 |
| 2.5 | .80 / .51 | .97 / .77 | .996 / .90 |

   Power 0.8 needs z = 2.49; unknown sign lowers every value (0.56 at m = 1.5, k = 2). A ceiling for a pure mean test, not a statement about B5 (not run).
4. **B3 depends on more than (m, k).** On the structured day, P(detect) for m = 1.5, k = 2 is 1.00 if the first covered reading is the first or fourth, 0.73 and 0.62 if the second or third (dose-pair cancellation). Fitted RMSE 0.07-0.09, max up to 0.27. A logistic in m misfits the k = 1 B3 curve (0.48 at m = 1.5, 0.89 at m = 1.75) by up to 0.15. These curves depend on the unknown pre/post drop d.

**Levels needed to read the curve** (analytic B1, m in [1, 2.5], linear interpolation, all k): tolerance 0.05: 2-3 levels, 0.02: 3 levels, 0.01: 4 levels. The actual grid 1.0 / 1.5 / 2.5 by linear interpolation errs by at most 0.020 (L) and 0.025 (O), a quadratic through the three levels by at most 0.005. Interpolation error is therefore far smaller than sampling error below.

**Continuous draw versus cells, n = 100 realised positives** (model L truth; Bernoulli outcomes, 1 500 repetitions; pooled P(1.5) = 0.624, per k .415 / .657 / .799). SD of the estimate at m = 1.5:

| design | SD | bias |
|---|---|---|
| 3 levels, cell proportion (about 33 per level) | 0.086 | +0.001 |
| 3 levels, one logistic fit across them | 0.053 | +0.008 |
| m ~ U[1, 2.5], logistic in m | 0.055 | +0.005 |
| m ~ U[1, 2.5], k-aware form (ii) | 0.052 | +0.004 |
| 9 cells (m, k), about 11 per cell, cell (1.5, 2) | 0.148 | 0 |
| m ~ U[1, 2.5], form (ii), same cell (1.5, 2) | 0.057 | +0.005 |

The cell proportion needs 79 positives per cell to match the fit's SD (model O: 71); SD 0.05 / 0.03 / 0.02 needs 94 / 261 / 587 per cell. The gain comes from pooling under a parametric curve, not from the continuous draw: three levels fitted jointly give the same SD (0.053 vs 0.055).

**Risks.** Fitted curve: bias if the true curve is outside the family (B1 <= 0.008; B3 logistic misses 0.08-0.15 and (m, k) is insufficient); single-index forms extrapolate poorly; a continuous magnitude has no per-row provenance. Cells: 9 cells at about 11 positives have half-width about 0.29. Both: if the fault-free alarm rate is high (section 1), the quantity to estimate is the excess over the zero row, whose SE is larger.

**Could not determine.** B5 detectability; the real pre/post-dose drop; whether the real false-alarm rate persists once the design rows are fixed; B3 on the real generator beyond the day-level alarm rate; B3 curves at better than 400 trials per cell (a 1 500 run was stopped for machine load).
