# Literature-anchored parameter proposal (WS01-T09)

Status: **proposal awaiting the decisions of gab.** Produced on 2026-10-08 by three research agents in gab's interactive session (ADR-043) and assembled by the agent. This is not a clinical review and nothing in it is clinically validated: every value is a proposal anchored in a published source (or marked `no-literature-value`), to be accepted, changed or rejected by gab before it enters `configs/`. Accepted values keep `reviewed_by: null` and the rationale "literature-anchored proposal (WS01-T09), not clinically reviewed" (ADR-020, ADR-043). Every source was opened on 2026-10-08; quotes that came through a page extractor instead of the original PDF are flagged in their rows and should be spot-checked. Standards that were not opened directly (ISO 81060-2, IEC 80601-2-30, IEC 60601-1-8 Amendment 2, Bluetooth Core 5.2) need their edition and clause confirmed.

## How to decide

Fill the column `decision_gab` of the table below with `accept`, `change: <value>` or `reject` (a rejected entry keeps its illustrative value, a rejected `unset` name stays unset, a rejected prior row stays `awaiting_human_value`). The detailed rows (parts A, B, C) carry the passage, the citation and the derivation.

## Cross-cutting decisions

1. **Drug.** Part B proposes oral **carvedilol** twice daily (FDA COREG label, rev. 07/2023), alternative oral labetalol; part A used the labetalol label only to support the two daily doses. The PK/PD rows (`emax_mmhg`, `ec50`, `absorption_rate_per_h`, `elimination_rate_per_h`, `onset_delay_range_ms`, `delta1`, `delta2`, `delta_resp`) follow the drug chosen; `dose_max_24h` and `dose_min_day_end` = 2 hold for any twice-daily drug.
2. **Unit dose for `ec50`** (25 mg or 12.5 mg of carvedilol): the gap of ADR-038; 12.5 mg gives a trough-to-peak ratio closer to the label.
3. **Plausibility bounds of pressure**: part A moves them from 50-250 (analisi, unsupported) to the 30-260 mmHg range of a ward monitor's specification; the lab-demo cuff needs its own specification.
4. **Noise rows include the cuff error**: `ar_noise_sd_mmhg` (11.9) is an upper bound measured with a cuff; the latent value is `sqrt(11.9² − cuff_error_sd²)`.
5. **Cuff error**: the standard gives acceptance limits (mean ≤ 5, SD ≤ 8 mmHg); proposal SD 8, bias 0 (stress 4 and 5). The VitalDB estimate (38 pairs, 9 cases: mean −10.0, SD 17.3, SD 9.5 without one outlier; `docs/formal/evidence/ws01-t09/`) is supplementary.

## Findings for the formalization (not parameter values)

- **Count window against the dose window** (part A): `dose_count` is a trailing 24 h window while ISMP allows a dose 1 h early or late; an evening dose 1 h late followed by the next evening dose 1 h early gives three on-time doses within 22 h and violates `dose_max_24h = 2`.
- **Withheld dose** (part A): a dose correctly withheld by the hold rule, or refused, violates `dose_min_day_end = 2` although the care plan was followed.
- **Response test on one pair of readings** (part B): readings 1-2 h apart are nearly uncorrelated, so the difference of one pre-dose and one post-dose reading has an SD of about 16.8 mmHg; a 7.5 mmHg `delta_resp` on a single pair is often wrong (a question for rho and the conformal calibration).
- **Inflation signal** (part C): the `sys` template reads the inflation duration, while device manuals give the whole measurement cycle.
- **BLE clock skew** (part C): with a ±500 ppm sleep clock and a daily resynchronisation the skew bound is about 44 s, close to the 60 s monitor step; to be measured on the WS07 and WS10 hardware.

These are handed to WS01-T08 (freeze) as open points.

## Decision table

| # | name | part | file | current | proposed | status | decision_gab |
|---|---|---|---|---|---|---|---|
| 1 | `bp_band_low` | A | registry entry | 110 | - | no-literature-value |  |
| 2 | `bp_band_high` | A | registry entry | 140 | 140 | proposed |  |
| 3 | `bp_hold_threshold` | A | registry entry | 100 | 100 | proposed |  |
| 4 | `hold_lookback` | A | registry entry | 3600000 (60 min) | - | no-literature-value |  |
| 5 | `dose_max_24h` | A | registry entry | 2 | 2 (only if gab confirms a twice-daily drug) | proposed |  |
| 6 | `dose_min_day_end` | A | registry entry | 2 | 2 (only if gab confirms a twice-daily drug) | proposed |  |
| 7 | `bound_bp_lower` | A | registry entry | 50 | 30 | proposed |  |
| 8 | `bound_bp_upper` | A | registry entry | 250 | 260 | proposed |  |
| 9 | `sched_window` | A | registry unset | unset | 3600000 | proposed |  |
| 10 | `bound_dose_count_lower` | A | registry unset | unset | - | no-literature-value |  |
| 11 | `bound_dose_count_upper` | A | registry unset | unset | - | no-literature-value |  |
| 12 | `baseline_sbp_mmhg` | B | prior | awaiting_human_value | dist normal(mean 149.3, sd 9.0); truncation left to gab (design choice, e.g. ±3 SD = [1... | proposed |  |
| 13 | `circadian_amplitude_mmhg` | B | prior | awaiting_human_value | dist normal(mean 13.2, sd 6.1), truncate lo 0 (the truncation is a design choice) | proposed |  |
| 14 | `ar_noise_sd_mmhg` | B | prior | awaiting_human_value | upper bound 11.9; latent value = sqrt(11.9² − σ_cuff²) | proposed |  |
| 15 | `ar_noise_phi` | B | prior | awaiting_human_value | 0.22, reference_step_ms: 1800000 | proposed |  |
| 16 | `emax_mmhg` | B | prior | awaiting_human_value | 17.3 (sensitivity 15.1-19.9, see notes) | proposed (weak) |  |
| 17 | `ec50` | B | prior | awaiting_human_value | 0.38 if the unit dose is 25 mg (range 0.35-0.41 over the PK ranges); 0.76 if the unit d... | proposed (weak) |  |
| 18 | `absorption_rate_per_h` | B | prior | awaiting_human_value | 2.3 (range 1.4-4.2) | proposed |  |
| 19 | `elimination_rate_per_h` | B | prior | awaiting_human_value | 0.0815 (range 0.0693-0.0990) | proposed |  |
| 20 | `onset_delay_range_ms` | B | prior | awaiting_human_value | {lower_ms: 1800000, upper_ms: 7200000} | proposed |  |
| 21 | `p_delay` | B | prior | awaiting_human_value (declared_assumptio | 0.081 | proposed |  |
| 22 | `p_omission` | B | prior | awaiting_human_value (declared_assumptio | 0.057 (inpatient); alternative 0.10 (outpatient self-administration) | proposed |  |
| 23 | `p_double_take` | B | prior | awaiting_human_value (declared_assumptio | 0.0031 | proposed |  |
| 24 | `mean_delay_ms` | B | prior | awaiting_human_value (declared_assumptio | - | no-literature-value |  |
| 25 | `delta1` | B | registry entry | 3600000 (illustrative, unverified) | 3600000 (confirm current) | proposed |  |
| 26 | `delta2` | B | registry entry | 10800000 (illustrative, unverified) | 7200000 (literal label range); keeping 10800000 is a design margin | proposed |  |
| 27 | `delta_resp` | B | registry unset | unset | 7.5 | proposed |  |
| 28 | `scale_range` | C | registry entry | 20 | 20 (alternative 10) | proposed |  |
| 29 | `scale_hold` | C | registry unset | unset | 10 | proposed |  |
| 30 | `scale_resp` | C | registry unset | unset | 10 | proposed |  |
| 31 | `scale_sched` | C | registry entry | 1800000 | 1800000 | proposed |  |
| 32 | `scale_count` | C | registry entry | 1 | - | no-literature-value |  |
| 33 | `scale_sys` | C | registry unset | unset | - | no-literature-value |  |
| 34 | `scale_int` | C | registry unset | unset | - | no-literature-value |  |
| 35 | `priority_hold` | C | registry entry | 1 | - | no-literature-value |  |
| 36 | `priority_range` | C | registry entry | 2 | - | no-literature-value |  |
| 37 | `priority_sched` | C | registry entry | 3 | - | no-literature-value |  |
| 38 | `priority_count` | C | registry unset | unset | - | no-literature-value |  |
| 39 | `priority_resp` | C | registry unset | unset | - | no-literature-value |  |
| 40 | `priority_sys` | C | registry unset | unset | - | no-literature-value |  |
| 41 | `priority_int` | C | registry unset | unset | - | no-literature-value |  |
| 42 | `int_window` | C | registry entry | 300000 | - | no-literature-value |  |
| 43 | `cuff_inflation_min` | C | registry unset | unset | - (candidate 15000) | no-literature-value |  |
| 44 | `bound_inflation_ms_lower` | C | registry unset | unset | - (suggested 0) | no-literature-value |  |
| 45 | `bound_inflation_ms_upper` | C | registry unset | unset | 180000 | proposed |  |
| 46 | `cuff_error_sd` | C | registry unset | unset | 8 | proposed |  |
| 47 | `clock_skew_max_ms` | C | registry unset | unset | 1000 for synchronised nodes; for BLE devices see the bound below | proposed |  |
| 48 | `cuff_error_sd_mmhg` | C | prior | awaiting_human_value | 8 | proposed |  |
| 49 | `cuff_bias_mmhg` | C | prior | awaiting_human_value | 0 (stress 4 and 5) | proposed |  |
| 50 | `dispenser_bounce_prob` | C | prior | awaiting_human_value | 0.001 (range 0-0.005) | proposed |  |
| 51 | `ble_dropout_rate_per_h` | C | prior | awaiting_human_value | - | no-literature-value |  |

## WS01-T09 part A: clinical thresholds and care-plan counts (literature-anchored proposal, not clinically reviewed)

Summary (sources opened on 2026-10-08; nothing here is a clinical review):

- 11 rows. **7 proposed**: `bp_band_high` (140), `bp_hold_threshold` (100), `dose_max_24h` (2), `dose_min_day_end` (2), `bound_bp_lower` (30), `bound_bp_upper` (260), `sched_window` (3600000 ms). **4 no-literature-value**: `bp_band_low`, `hold_lookback`, `bound_dose_count_lower`, `bound_dose_count_upper`.
- Design or care-plan choices: `hold_lookback`, both `bound_dose_count_*`. The two dose counts follow from a prescribed frequency, so they hold only if gab confirms a twice-daily drug. `bp_band_low` has no source at 110.
- Main sources: 2024 ESC guidelines (McEvoy et al.), 2023 ESH guidelines (Mancia et al.), NICE NG136 (last updated 26 Feb 2026), ISMP timely-administration guidelines (2011), Open RN *Nursing Skills 2e* (2023), FDA labetalol label (rev. 4/2024), the Welch Allyn Connex Spot Monitor spec sheet (v3.0, 08/2026), MIMIC-IV `mimic-code`, Redfern et al. BMJ Open 2019.
- Main gap: the guidelines give office or average **treatment targets** and diagnostic thresholds, not per-reading bands for ward patients on oral drugs. No inpatient guideline sets a target (the AHA 2024 acute-care statement returned 403 and could not be opened; the 2025 AHA/ACC guideline returned 403 too).
- Two design interactions for WS01 (not literature findings): (1) a ±1 h dose tolerance plus a trailing-24 h `dose_max_24h = 2` can flag three doses that were each on time; (2) a dose correctly withheld by HOLD breaks `dose_min_day_end = 2`.

---

#### bp_band_low
- file: registry entry
- unit: mmHg
- current: 110
- status: no-literature-value
- value: -
- citation: (a) McEvoy JW, McCarthy CP, Bruno RM, et al., "2024 ESC Guidelines for the management of elevated blood pressure and hypertension", Eur Heart J 45(38):3912-4018, 2024, doi:10.1093/eurheartj/ehae178. (b) Mancia G, Kreutz R, Brunström M, et al., "2023 ESH Guidelines for the management of arterial hypertension", J Hypertens 41(12):1874-2071, 2023, doi:10.1097/HJH.0000000000003480
- passage: (a) "A major, evidence-based change in the 2024 Guidelines is the recommendation to pursue a target systolic BP of 120–129 mmHg among adults receiving BP-lowering medications." (b) "(iv) to make no attempt to decrease SBP/DBP to <120/70 mmHg." (section 10, patients aged 65-79)
- consulted_on: 2026-10-08
- derivation: None of these sources gives 110 mmHg. Both guidelines put the lower edge of the treatment target at 120 mmHg systolic (the ESC lower end of the target range; the ESH lower limit of what treatment should aim for).
- notes: The analisi value is not supported. If gab wants an anchored lower edge, 120 is the one the guidelines support, but it is a target for office or average BP, not a limit for each reading. Applied to every ward reading, a lower edge of 120 would flag many readings from patients who are at target. ESC passage (a) came through the WebFetch tool because Cloudflare blocked a direct download, so gab should check the wording against the PDF. The ESH text was downloaded in full.
- decision_gab:

#### bp_band_high
- file: registry entry
- unit: mmHg
- current: 140
- status: proposed
- value: 140
- citation: NICE, "Hypertension in adults: diagnosis and management" (NG136), published 28 Aug 2019, last updated 26 Feb 2026, https://www.nice.org.uk/guidance/ng136/chapter/recommendations ; support: Mancia et al. 2023 ESH (as above)
- passage: NICE 1.4.20: "For adults with hypertension aged under 80, reduce clinic blood pressure to below 140/90 mmHg and ensure that it is maintained below that level." ESH section 10.1: "the 2018 ESC/ESH guidelines recommended that the first objective of antihypertensive treatment should be to lower BP to <140/90 mmHg in all patients."
- consulted_on: 2026-10-08
- derivation: The systolic part of "below 140/90 mmHg" gives 140 mmHg as the upper limit of the treated range.
- notes: Supports the analisi value. Caveats: (1) NICE sets this for clinic BP and an average response, not each ward reading. (2) NICE says "below 140", while the template uses `bp <= 140`, so the two differ only at exactly 140. (3) For ages 80 and over, NICE 1.4.21 gives "below 150/90 mmHg". (4) ESC 2024 and ESH 2023 aim lower (120-129 mmHg when treatment is tolerated). 140 is therefore the lenient end, which suits an alert band better than a target does.
- decision_gab:

#### bp_hold_threshold
- file: registry entry
- unit: mmHg
- current: 100
- status: proposed
- value: 100
- citation: Ernstmeyer K, Christman E (eds.), *Nursing Skills 2e*, Open Resources for Nursing (Open RN), Chippewa Valley Technical College / WisTech Open, Eau Claire WI, 28 Aug 2023, section 15.3 "Assessments Related to Medication Administration", https://wtcs.pressbooks.pub/nursingskills/chapter/15-3-assessments-related-to-medication-administration/ ; variability: Cannon CP, "How do I make sense of my medication orders?", Harvard Health Publishing, 1 Oct 2025, https://www.health.harvard.edu/heart-health/how-do-i-make-sense-of-my-medication-orders
- passage: "For example, a patient is scheduled to receive a blood pressure medication, but their current blood pressure is 90/50, so the medication is withheld based on parameters stated on the MAR to withhold the medication if the systolic blood pressure is less than 100. If parameters are not provided, it is the nurse's responsibility to use clinical judgment and follow up with the prescribing provider with concerns before administering the medication." Harvard Health: "For metoprolol, it read: HOLD BP < 110. For losartan, it read: HOLD BP < 120 systolic." and "The detailed directions you received are what nurses are instructed to do when a person is in the hospital".
- consulted_on: 2026-10-08
- derivation: The textbook says to withhold if SBP < 100 and to give the dose otherwise, that is, when SBP >= 100. This matches the template's `bp >= bp_hold_threshold`, including the boundary at 100.
- notes: A textbook supports the analisi value as an example. It is not a standard. Hold parameters are written by the prescriber for each order. Real orders vary with drug and patient (110 and 120 in the Harvard example; AHRQ PSNet, "Hold That Order", 2008, only says such orders hold doses "when blood pressures or heart rates fall below normal values"). No guideline I opened (ESC 2024, ESH 2023, NICE NG136) gives a hold threshold.
- decision_gab:

#### hold_lookback
- file: registry entry
- unit: ms
- current: 3600000 (60 min)
- status: no-literature-value
- value: -
- citation: Open RN *Nursing Skills 2e*, section 15.3 (as above); bound: ISMP, "ISMP Acute Care Guidelines for Timely Administration of Scheduled Medications", 2011, https://www.ismp.org/sites/default/files/attachments/2018-02/tasm.pdf
- passage: "Before administering cardiac medication, the patient's blood pressure and heart rate are typically assessed to ensure they are within range of parameters for administration."
- consulted_on: 2026-10-08
- derivation: None. The sources ask for a "current" reading taken "before administering" and give no maximum age for it. Four searches for a published policy with a time limit (for example "within 30 minutes" or "within one hour" before the dose) found only clinical-trial protocols, which are not ward policy and were not opened.
- notes: This is a local-policy choice. 60 min stays illustrative and unverified. One design argument: ISMP lets a BID dose be given up to 1 h after its scheduled time. A reading taken at the scheduled time is therefore at most 60 min old at the latest allowed dispense, so `hold_lookback = 3600000` (60 steps of 60 s) covers that case.
- decision_gab:

#### dose_max_24h
- file: registry entry
- unit: dose
- current: 2
- status: proposed
- value: 2 (only if gab confirms a twice-daily drug)
- citation: U.S. FDA, Labetalol Hydrochloride Tablets, full prescribing information, NDA 018716 (S-036), revised 4/2024, https://www.accessdata.fda.gov/drugsatfda_docs/label/2024/018716s036lbl.pdf
- passage: "The recommended initial dosage of labetalol hydrochloride is 100 mg twice daily. Adjust dosage in increments of 100 mg twice daily at 2- to 3-day intervals based on response. The recommended maintenance dosage of labetalol hydrochloride is between 200 and 400 mg twice daily." (section 2.1)
- consulted_on: 2026-10-08
- derivation: Twice daily means 2 scheduled administrations per 24 h, so at most 2 doses in a 24 h period.
- notes: The count comes from the patient care plan's frequency, not from a guideline. The label is only an example of a twice-daily oral antihypertensive and does not choose the drug (the drug class is gab's decision, shared with part B). A once-daily drug gives 1. Design interaction: `dose_count` is a trailing 24 h window (01-signals-sampling §5.1). With the ISMP ±1 h tolerance (see `sched_window`), an evening dose given 1 h late followed by the next evening dose given 1 h early puts three on-time dispenses within 22 h, so `c_d = 3 > 2`. Either the window, the limit or the tolerance needs a decision.
- decision_gab:

#### dose_min_day_end
- file: registry entry
- unit: dose
- current: 2
- status: proposed
- value: 2 (only if gab confirms a twice-daily drug)
- citation: FDA labetalol label (as above)
- passage: "The recommended initial dosage of labetalol hydrochloride is 100 mg twice daily."
- consulted_on: 2026-10-08
- derivation: A twice-daily schedule means 2 scheduled doses per day, so the day-end obligation is 2.
- notes: Same caveat on the drug as `dose_max_24h`. Design interaction: a dose correctly withheld under HOLD (or refused) leaves `c_d = 1` at day end and violates this conjunct even though the care plan was followed. Analisi §4.9 cascade issue, for WS01/WS02 to resolve.
- decision_gab:

#### bound_bp_lower
- file: registry entry
- unit: mmHg
- current: 50
- status: proposed
- value: 30
- citation: Baxter (Hillrom), "Welch Allyn Connex Spot Monitor" specification sheet, US-FLC45-230026 (v3.0) 08/2026, https://www.hillrom.com/content/dam/hillrom-aem/us/en/marketing/products/connex-spot-monitor/documents/US-FLC45-230026-V2_Connex-Spot-Monitor-Spec-Sheet_LR.pdf
- passage: "Systolic Range Adult/Pediatric: 30 – 260 mmHg | Neonate: 20 – 120 mmHg"
- consulted_on: 2026-10-08
- derivation: The bound must contain every value the observed signal can take, or the robustness interval is not sound. A ward oscillometric monitor of this class cannot report adult systolic values below 30 mmHg, so 30.
- notes: The analisi value of 50 has no supporting source except one arXiv preprint (Zhang et al., arXiv:2607.04414, 2026) that labels systolic values "outside 50–250 mmHg" as invalid. The MIMIC-IV community code accepts much wider values (`valuenum > 0 AND valuenum < 400`, MIT-LCP mimic-code, `mimic-iv/concepts/measurement/vitalsign.sql`, main branch). The bound therefore depends on the device: the lab-demo cuff needs its own spec, and WS04 must clip MIMIC-derived traces to the same range. A narrower bound (50) gives tighter intervals but assumes something the device does not guarantee.
- decision_gab:

#### bound_bp_upper
- file: registry entry
- unit: mmHg
- current: 250
- status: proposed
- value: 260
- citation: Connex Spot Monitor specification sheet (as above)
- passage: "Systolic Range Adult/Pediatric: 30 – 260 mmHg | Neonate: 20 – 120 mmHg"
- consulted_on: 2026-10-08
- derivation: The device's adult systolic upper limit is 260 mmHg.
- notes: Same reasoning and caveats as `bound_bp_lower`. 250 is close but has no source. The same sheet gives a separate cuff "Overpressure Cutoff Adult/Pediatric: 300 mmHg ± 15 mmHg"; that is a cuff pressure, not a reported value, so the bound should come from the reported systolic range.
- decision_gab:

#### sched_window
- file: registry unset
- unit: ms
- current: unset
- status: proposed
- value: 3600000
- citation: ISMP, "ISMP Acute Care Guidelines for Timely Administration of Scheduled Medications", ISMP 2011, https://www.ismp.org/sites/default/files/attachments/2018-02/tasm.pdf ; for measurements: Redfern OC et al., "The association between nurse staffing levels and the timeliness of vital signs monitoring: a retrospective observational study in the UK", BMJ Open 9(9):e032157, 2019, doi:10.1136/bmjopen-2019-032157
- passage: ISMP: "Medications administered more frequently than daily but not more frequently than every 4 hours (e.g., BID, TID, q4h, q6h) Administer these medications within 1 hour before or after the scheduled time." and "The guidelines are not standards or evidence-based practices that have been proven by scientific studies". Redfern: "an observation was delayed if overdue by more than 33% of the expected time to next observation determined by the previous NEWS value. For example, if the next observation was due in 60 min, it was classified as delayed if taken >80 min after the previous observation".
- consulted_on: 2026-10-08
- derivation: ISMP allows 1 h after the scheduled time for a BID dose, and the template only checks lateness: 1 h = 3600000 ms (60 steps at F0 `step_ms = 60000`).
- notes: ISMP covers dose administration. Using it for scheduled measurements is an analogy. For measurements, the published lateness rule is relative: delayed if more than one third of the observation interval overdue, so W = I/3 (for I = 3 h, W = 1 h). The analisi does not fix the measurement interval, so the relative rule gives no number by itself. ISMP's "1 hour before" side is not modelled (an early measurement is not checked by SCHED). Consequence: `max_latency_sched` = 3660000 ms. The ISMP time-critical class (30 min) is the alternative if gab treats the drug as time-critical.
- decision_gab:

#### bound_dose_count_lower
- file: registry unset
- unit: dose
- current: unset
- status: no-literature-value
- value: -
- citation: none (follows from the definition in `docs/formal/01-signals-sampling.md` §5.1)
- passage: -
- consulted_on: 2026-10-08
- derivation: `dose_count` counts events in a window, so it cannot be negative. 0 follows from the definition, not from a clinical source.
- notes: Recommended value 0 as a mathematical bound. No literature search applies.
- decision_gab:

#### bound_dose_count_upper
- file: registry unset
- unit: dose
- current: unset
- status: no-literature-value
- value: -
- citation: none
- passage: -
- consulted_on: 2026-10-08
- derivation: No clinical source states how many dispense events can occur in 24 h. A sound bound follows from design facts instead: dispenser capacity per day (a device specification of the WS10 dispenser) or, without one, the multiplicity limit of the event stream.
- notes: Design or device choice. Do not use a pharmacological maximum (for example a daily mg ceiling) here, because a tampered or bouncing dispenser (C2/C3) can produce counts above any prescribed maximum. The bound must stay sound for those traces.
- decision_gab:

## WS01-T09 part B: patient, drug response, adherence (literature-anchored proposals)

Research agent, 2026-10-08, for gab to check. Not a clinical review: no value here is clinically validated; every row needs `decision_gab`.

### Drug-class proposal (gab confirms)

**Proposed: oral carvedilol, immediate-release, twice daily** (FDA label: hypertension start 6.25 mg twice daily, up to 25 mg twice daily, "Total daily dose should not exceed 50 mg"). This fits `dose_max_24h` = 2 and the 07:00/21:00 schedule.
- Among 23,147 non-ICU inpatients with severe hypertension it was a common treatment ("oral metoprolol (n = 1991), oral amlodipine (n = 1812), oral carvedilol (n = 1116), ...") and one of two oral agents with a significant BP fall within 6 h, whereas "Receiving metoprolol and amlodipine did not result in a drop in BP compared to no treatment" (Ghazi et al., PLoS One 2022, doi:10.1371/journal.pone.0265497).
- The label gives the RESP timing: effects "usually are seen within 30 minutes"; "The peak antihypertensive effect occurred 1 to 2 hours after a dose".
- Label used: COREG (carvedilol) tablets, FDA, Revised 07/2023, Reference ID 5215614, https://www.accessdata.fda.gov/drugsatfda_docs/label/2023/020297s039lbl.pdf (opened as PDF text).

**Alternative: oral labetalol, twice daily** (Trandate label, FDA, Revised 4/2024, Reference ID 5370606, https://www.accessdata.fda.gov/drugsatfda_docs/label/2024/018716s036lbl.pdf): "peak plasma levels occurring 1 to 2 hours after oral administration", "The plasma half-life of labetalol following oral administration is about 6 to 8 hours", "The peak effects of single oral doses of labetalol hydrochloride occur within 2 to 4 hours." This gives ke = 0.087-0.116 /h and a window of about 2-4 h. In Ghazi 2022 it is a secondary analysis ("IV and oral labetalol were administered among 337 and 129 patients"); gab should read the oral result before choosing it.

The EU SmPC was not opened.

### Summary

- 15 of 16 rows have a proposal. `mean_delay_ms` is `no-literature-value`.
- **Blocked search:** two searches for concentration-effect (Emax/EC50) studies were refused by a tool-side safeguard and not retried. `emax_mmhg` and `ec50` are derived from the label's dose-response figures only and are **weak**.
- **Pressure rows:** noise and amplitude from one general-population ABPM cosinor study (Madden 2018); baseline from an untreated outpatient MESOR (Cornelissen 2025). None is inpatient; inpatient ABPM cross-checks (Xu 2013, Pikilidou 2010) show a blunted nocturnal dip in hospital.
- **Device error:** the ABPM residual SD (11.9 mmHg) contains device error, which the benchmark adds separately; the latent SD and phi need the correction in their rows, with part A's `cuff_error_sd`.
- **Adherence:** from directly observed nurse-administered doses (Barker 2002), not patient self-administration; outpatient electronic monitoring (Vrijens 2008) is the alternative for omissions.
- **PK timing:** ka is back-computed from the time of peak effect, valid only because ADR-039's effect is a direct monotone function of concentration.
- **Quotes:** label quotes are exact PDF text; article quotes came through the fetch tool's extractor and should be spot-checked.

---

#### baseline_sbp_mmhg
- file: prior
- unit: mmHg
- current: awaiting_human_value
- status: proposed
- value: dist normal(mean 149.3, sd 9.0); truncation left to gab (design choice, e.g. ±3 SD = [122.3, 176.3])
- citation: Cornelissen G, Watanabe Y, Beaty LA, Otsuka K. Toward a personalized chronotherapy of blood pressure. Biomedical Journal 2025;48(5):100849. doi:10.1016/j.bj.2025.100849 (PMC12529489)
- passage: "In the absence of treatment, ABPM results averaged (SBP/DBP MESOR, mean ± SD) 149.3 ± 9.0/90.0 ± 6.1 mmHg in Study 1"
- consulted_on: 2026-10-08
- derivation: The MESOR (rhythm-adjusted cosinor mean) is the model's `baseline`; untreated, so no drug effect is embedded. The SD is between patients.
- notes: 47 outpatients aged 28-68, ~7-day ABPM at 30-min intervals; not inpatients. Inpatient cross-checks: (a) Xu T, Zhang Y, Tan X, BMC Cardiovasc Disord 2013;13:37, doi:10.1186/1471-2261-13-37, 155 treated cardiology inpatients: "CBP 160.79±23.19/90.74±14.46 mmHg" (clinic readings, include treatment and device error). (b) Pikilidou MI et al., Hypertens Res 2010;33(10):995-999, doi:10.1038/hr.2010.127: "Daytime systolic BP (SBP) was lower in the hospital than in the outpatient setting (mean difference 4.3 ± 10.4 mm Hg, P=0.01)".
- decision_gab:

#### circadian_amplitude_mmhg
- file: prior
- unit: mmHg
- current: awaiting_human_value
- status: proposed
- value: dist normal(mean 13.2, sd 6.1), truncate lo 0 (the truncation is a design choice)
- citation: Madden JM, Browne LD, Li X, Kearney PM, Fitzgerald AP. Morning surge in blood pressure using a random-effects multiple-component cosinor model. Statistics in Medicine 2018;37(10):1682-1695. doi:10.1002/sim.7607 (PMC5947147)
- passage: "As expected, the first cosine with period 24‐hours is the dominant curve with amplitude of 13.2 mmHg while the second cosine curve with period 12‐hours has amplitude 5.6 mmHg." / "The variation between individuals in the first cosine amplitude was greater compared with the second (SD, 6.1 vs 2.8 mmHg)."
- consulted_on: 2026-10-08
- derivation: A cosinor amplitude is already half the peak-to-trough distance of its harmonic, so it enters as A with no halving. The mean is the fixed effect and the SD is the between-person SD. The outcome is SBP: "The final 2‐component SBP cosinor model parameters estimates are presented in Table 2."
- notes: Two-harmonic model; the 12-h component (5.6 mmHg) has no place in the single-harmonic generator. Mitchelstown cohort (Ireland), 886 analysed, "Hypertension, n (%) 528 (59.7%)", community, mixed treatment. **Inpatient caveat:** Pikilidou 2010: "The nighttime SBP dip (vs. daytime) was larger in the outpatient setting (8.9 ± 7.5% and 5.2 ± 4.7%, respectively; P=0.003)"; scaling by 5.2/8.9 = 0.58 would give 7.7 mmHg (an assumption, not a source). Cross-check: Cornelissen 2025 Table 3 untreated hypertensive groups, 9.42-13.54 mmHg, from group-averaged profiles (these underestimate individual amplitudes).
- decision_gab:

#### ar_noise_sd_mmhg
- file: prior
- unit: mmHg
- current: awaiting_human_value
- status: proposed
- value: upper bound 11.9; latent value = sqrt(11.9² − σ_cuff²)
- citation: Madden et al. 2018 (as above)
- passage: "The within‐subject SD (σ) was 11.9 mmHg."
- consulted_on: 2026-10-08
- derivation: σ is the residual SD of the AR(1)-error cosinor model, i.e. the stationary SD (the contract's meaning). It contains the oscillometric device error, which the benchmark adds separately (`cuff_error_sd_mmhg`), hence sqrt(11.9² − σ_cuff²) with part A's σ_cuff.
- notes: General cohort, not inpatients. The residual is net of two harmonics.
- decision_gab:

#### ar_noise_phi
- file: prior
- unit: 1
- current: awaiting_human_value
- status: proposed
- value: 0.22, reference_step_ms: 1800000
- citation: Madden et al. 2018 (as above)
- passage: "On the basis of an LRT, incorporating an AR1 structure resulted in a significant improvement in fit compared with a model assuming independence in residuals (ρ = .22, P < .001)." / "The monitors were programmed to obtain readings every 30 minutes and remained in place for 24‐hours."
- consulted_on: 2026-10-08
- derivation: AR1 on successive 30-min readings: reference_step_ms = 1,800,000. Rescaled, phi_s = 0.22^(step/1,800,000) is 0.951 at 60 s and 0.777 at 5 min.
- notes: (1) Rescaling assumes exponential autocorrelation; the paper only says "the inclusion of an AR1 residual structure adequately accounted for the autocorrelation". (2) Missing readings make lags uneven. (3) White device error biases ρ down; with independent cuff error the latent phi = 0.22 × 11.9² / (11.9² − σ_cuff²).
- decision_gab:

#### emax_mmhg
- file: prior
- unit: mmHg
- current: awaiting_human_value
- status: proposed (weak)
- value: 17.3 (sensitivity 15.1-19.9, see notes)
- citation: COREG label, FDA, Revised 07/2023, section 14.3 (URL above)
- passage: "At 50 mg per day, COREG reduced sitting trough (12-hour) blood pressure by about 9/5.5 mm Hg; at 25 mg per day the effect was about 7.5/3.5 mm Hg. Comparisons of trough-to-peak blood pressure showed a trough-to-peak ratio for blood pressure response of about 65%."
- consulted_on: 2026-10-08
- derivation: Peak SBP effect = trough / 0.65, giving 11.5 mmHg at 25 mg/day and 13.8 mmHg at 50 mg/day. Fitting E(d) = Emax·d/(ED50 + d) through the two points gives ED50 = 12.5 mg/day (6.25 mg per dose) and Emax = 11.54 × 37.5/25 = 17.3 mmHg. Emax is a magnitude ≥ 0 (ADR-039).
- notes: Two points fix two parameters exactly (no residual), so it is fragile: 9 → 8.5 or 9.5 alone gives 15.1 or 19.9. Placebo subtraction is not stated; the trough-to-peak ratio is assumed dose-independent; outpatient trials; dose-space fit because the concentration-effect search was blocked. Inpatient cross-check: Ghazi 2022, oral carvedilol "-7 [-9.1, -4.2] lower MAP" over 6 h vs untreated. No between-patient spread.
- decision_gab:

#### ec50
- file: prior
- unit: 1 (normalised to unit dose, ADR-039)
- current: awaiting_human_value
- status: proposed (weak)
- value: 0.38 if the unit dose is 25 mg (range 0.35-0.41 over the PK ranges); 0.76 if the unit dose is 12.5 mg
- citation: COREG label (as above), sections 14.3 and 12.3
- passage: "Plasma concentrations achieved are proportional to the oral dose administered." (plus the 14.3 passage under emax_mmhg)
- consulted_on: 2026-10-08
- derivation: With C proportional to dose, at steady-state peak E = Emax·(d/u)·C_pk/(ec50 + (d/u)·C_pk), so ec50 = (ED50 per dose / u)·C_pk = (6.25 mg / u)·C_pk. For ka 2.31, ke 0.0815 and the 07:00/21:00 schedule, numerical superposition gives C_pk = 1.515 (1.385-1.655 over the PK ranges), so 0.25 × 1.515 = 0.38 for u = 25 mg.
- notes: Derived, not a measured EC50; inherits every caveat of emax_mmhg. The unit dose u is a contract gap (ADR-038) for gab. Consistency check: model trough/peak effect is 0.81 (10-h gap) and 0.74 (14-h gap) for u = 25 mg, 0.72 and 0.63 for u = 12.5 mg, against the label's about 65% at 12 h, so u = 12.5 mg fits better.
- decision_gab:

#### absorption_rate_per_h
- file: prior
- unit: 1/h
- current: awaiting_human_value
- status: proposed
- value: 2.3 (range 1.4-4.2)
- citation: COREG label, section 14.3 and section 12.3
- passage: "The peak antihypertensive effect occurred 1 to 2 hours after a dose." / "When administered with food, the rate of absorption is slowed, as evidenced by a delay in the time to reach peak plasma levels, with no significant difference in extent of bioavailability."
- consulted_on: 2026-10-08
- derivation: The effect is monotone in C (ADR-039), so it peaks with C. Solving t_max = ln(ka/ke)/(ka − ke) for t_max = 1.5 h and ke = 0.0815 gives ka = 2.31; t_max 2 h with t½ 7 h gives 1.44, t_max 1 h with t½ 10 h gives 4.17.
- notes: The label gives no Tmax number; peak effect is a proxy valid only for a direct-effect model. The label says to take it with food, which delays the peak. Labetalol states Tmax 1-2 h directly.
- decision_gab:

#### elimination_rate_per_h
- file: prior
- unit: 1/h
- current: awaiting_human_value
- status: proposed
- value: 0.0815 (range 0.0693-0.0990)
- citation: COREG label, section 12.3
- passage: "Following oral administration, the apparent mean terminal elimination half-life of carvedilol generally ranges from 7 to 10 hours."
- consulted_on: 2026-10-08
- derivation: k = ln 2 / t½: t½ 8.5 h (mid) gives 0.0815; 10 h gives 0.0693; 7 h gives 0.0990.
- notes: One compartment ignores the enantiomers ("R(+)-carvedilol range from 5 to 9 hours compared with 7 to 11 hours for the S(-)- enantiomer") and the active metabolites. Labetalol alternative: 6-8 h gives 0.087-0.116.
- decision_gab:

#### onset_delay_range_ms
- file: prior
- unit: ms
- current: awaiting_human_value
- status: proposed
- value: {lower_ms: 1800000, upper_ms: 7200000}
- citation: COREG label, sections 12.2 and 14.3
- passage: "These effects contribute to the reduction of blood pressure and usually are seen within 30 minutes of drug administration." / "The peak antihypertensive effect occurred 1 to 2 hours after a dose."
- consulted_on: 2026-10-08
- derivation: lower = start of the BP-lowering effect, 30 min = 1,800,000 ms. upper = latest labelled peak, 2 h = 7,200,000 ms.
- notes: The first passage concerns α1-blocking effects. Whether the row means "onset to peak" or "interval where effect ≥ delta" is gab's call: with 65% trough-to-peak the effect spans the dosing interval, and `derive_onset_window` depends on Emax, ec50 and delta.
- decision_gab:

#### p_delay
- file: prior
- unit: 1
- current: awaiting_human_value (declared_assumption)
- status: proposed
- value: 0.081
- citation: Barker KN, Flynn EA, Pepper GA, Bates DW, Mikeal RL. Medication errors observed in 36 health care facilities. Arch Intern Med 2002;162(16):1897-1903. doi:10.1001/archinte.162.16.1897
- passage: "In the 36 institutions, 19% of the doses (605/3216) were in error." Table 1 as rendered by the fetch tool: "Wrong time: 259 (8)". Definition: "Administration of a dose more than 60 minutes before or after the scheduled administration time."
- consulted_on: 2026-10-08
- derivation: 259 / 3216 = 0.0805.
- notes: (1) Wrong time includes early doses; DELAYED is late only. (2) The > 60 min threshold differs from DELAYED (any lateness ≥ 1 ms); the exponential-from-1-ms delay does not start near 60 min. (3) Nurse-administered, directly observed doses in hospitals and skilled nursing facilities, not dispenser self-administration. (4) A search summary mentioned another table with 675 errors; gab should confirm Table 1.
- decision_gab:

#### p_omission
- file: prior
- unit: 1
- current: awaiting_human_value (declared_assumption)
- status: proposed
- value: 0.057 (inpatient); alternative 0.10 (outpatient self-administration)
- citation: Barker et al. 2002 (as above); alternative Vrijens B, Vincze G, Kristanto P, Urquhart J, Burnier M. Adherence to prescribed antihypertensive drug treatments: longitudinal study of electronically compiled dosing histories. BMJ 2008;336:1114-1117. doi:10.1136/bmj.39553.670231.25
- passage: Barker Table 1: "Omission: 183 (6)"; "Failure to give an ordered dose. If no attempt was made to administer the dose, an omission error was counted." Vrijens: "On any day, patients who were still engaged with the drug dosing regimen omitted about 10% of the scheduled doses:"
- consulted_on: 2026-10-08
- derivation: 183 / 3216 = 0.0569. Vrijens: 0.10 per scheduled dose.
- notes: Barker: nurse omissions. Vrijens: outpatient once-daily dosing, electronically monitored; closer to dispenser self-administration but not a ward. For gap G7 (persistence): "42% of these omissions were of a single day's dose, whereas 43% were part of a sequence of several days (three or more days-that is, drug "holidays")." Omissions cluster.
- decision_gab:

#### p_double_take
- file: prior
- unit: 1
- current: awaiting_human_value (declared_assumption)
- status: proposed
- value: 0.0031
- citation: Barker et al. 2002 (as above)
- passage: Table 1: "Extra dose: 10 (0)"; definition: "Any dose given in excess of the total number of times ordered by the physician, such as a dose given based on the expired order, after a drug had been discontinued, or after a drug had been put on hold."
- consulted_on: 2026-10-08
- derivation: 10 / 3216 = 0.0031. The sum with p_delay and p_omission is 0.141, which is at most 1.
- notes: Different mechanism (expired or held order, not a patient re-opening the dispenser); only 10 events. No source on patient double-dosing from a dispenser was found.
- decision_gab:

#### mean_delay_ms
- file: prior
- unit: ms
- current: awaiting_human_value (declared_assumption)
- status: no-literature-value
- value: -
- citation: nearest: Ituk US, Dexter F, Hadlandsmyth KE. Lateness of acetaminophen and NSAID administrations ... after cesarean delivery. Cureus 2024;16(5):e61433. doi:10.7759/cureus.61433
- passage: "There were 95% of doses administered between 108 minutes early (1.8 hours, 97.5% one-sided upper confidence limit 105 minutes early) and 181 minutes late (3.0 hours, 97.5% one-sided lower confidence limit 179 minutes late)." Table 1 values as reported by the fetch tool for all 67,900 doses: mean 25 min, SD 79, median 15, quartiles -11 and 59, 90th percentile 112.
- consulted_on: 2026-10-08
- derivation: None. No source gives the mean delay of late doses only, which is the quantity of the row.
- notes: Nearest measures are signed lateness over all doses (analgesics after caesarean). Loput et al., Am J Health Syst Pharm 2022;79(Suppl 1):S1-S7, doi:10.1093/ajhp/zxab378: "Scheduled medications were frequently subject to delays of ≥60 minutes (15% of administrations, n = 275,257)". With Barker's p_delay (> 60 min), the conditional mean must exceed 3,600,000 ms.
- decision_gab:

#### delta1
- file: registry entry
- unit: ms
- current: 3600000 (illustrative, unverified)
- status: proposed
- value: 3600000 (confirm current)
- citation: COREG label, sections 2.3 and 14.3
- passage: "using standing systolic pressure measured about 1 hour after dosing as a guide" / "The peak antihypertensive effect occurred 1 to 2 hours after a dose."
- consulted_on: 2026-10-08
- derivation: The lower end of the labelled peak is 1 h = 3,600,000 ms. The label itself uses the 1-h post-dose pressure.
- notes: The effect starts earlier (about 30 min); 1 h as the start of the required-decrease window is consistent. Labetalol: 2 h (7,200,000).
- decision_gab:

#### delta2
- file: registry entry
- unit: ms
- current: 10800000 (illustrative, unverified)
- status: proposed
- value: 7200000 (literal label range); keeping 10800000 is a design margin
- citation: COREG label, sections 14.3 and 12.3
- passage: "The peak antihypertensive effect occurred 1 to 2 hours after a dose." / "When administered with food, the rate of absorption is slowed, as evidenced by a delay in the time to reach peak plasma levels"
- consulted_on: 2026-10-08
- derivation: The upper end of the labelled peak is 2 h = 7,200,000 ms.
- notes: Taken with food the peak is delayed; keeping 3 h is a design margin, not a literature value. Must be a multiple of `step_ms`. Labetalol: 4 h (14,400,000).
- decision_gab:

#### delta_resp
- file: registry unset
- unit: mmHg
- current: unset
- status: proposed
- value: 7.5
- citation: COREG label, section 14.3 (passage under emax_mmhg)
- passage: "at 25 mg per day the effect was about 7.5/3.5 mm Hg."
- consulted_on: 2026-10-08
- derivation: This is the smallest labelled SBP effect: the trough at the lowest maintenance total dose. A responder measured at the 1-2 h peak is expected to exceed it (derived peak 11.5-13.8 mmHg).
- notes: What counts as a response is a clinical decision. The label effect is an outpatient mean, possibly placebo-subtracted; inpatient: Ghazi 2022, oral carvedilol MAP −7 within 6 h. **Noise:** readings 1-2 h apart are nearly uncorrelated (0.22^(2 to 4) ≤ 0.05), so a single-pair difference has SD ≈ 11.9 × √2 ≈ 16.8 mmHg; a 7.5 mmHg single-pair test will misclassify often (a WS01 rho and conformal-calibration question).
- decision_gab:

## WS01-T09 part C: scales, priorities, device and monitor parameters (proposals for gab)

Research notes, 2026-10-08. These are proposals for gab to check. Nothing here is clinically validated or a clinical review.

**Summary.**
1. For cuff error the literature gives acceptance limits, not typical values. AAMI/ESH/ISO (ISO 81060-2) Criterion 1 requires mean ≤5 mmHg with SD ≤8 mmHg (S1). Passing devices report, for example, 0.5 (7.7) mmHg (S2). Proposal: `cuff_error_sd` = `cuff_error_sd_mmhg` = 8 and `cuff_bias_mmhg` = 0 (S1 "high accuracy"), with 4 and 5 as stress values.
2. VitalDB (supplementary): 38 NIBP-ART pairs from 9 of 14 cases. Bias -10.0 mmHg, SD 17.3 mmHg; the SD is 9.5 without one +77 mmHg pair (post hoc).
3. IEC 80601-2-30 caps an adult measurement at 180 s (S7, secondary), so `bound_inflation_ms_upper` = 180000. No source gives a minimum duration, so `cuff_inflation_min` needs device data.
4. Scales rest on analogies only: 30 min (ISMP time-critical window, S8), 20 mmHg (orthostatic hypotension threshold, S10), 10 mmHg (NEWS2 bands S9, trial effect unit S11). `scale_sys` and `scale_int` are design choices.
5. Priorities: no literature value. IEC 60601-1-8 Table 1 (S12) gives a procedure for the clinician to apply.
6. Clock skew: a bound formula from IHE CT (S13) and the BLE clock specification (S14). No per-hour BLE dropout rate was found (S15). Dispenser spurious events: 3/3150, by analogy (S16).

### Sources (all opened 2026-10-08)

- **S1** Stergiou GS, Alpert B, Mieke S, et al. A Universal Standard for the Validation of BP Measuring Devices: AAMI/ESH/ISO Collaboration Statement. Hypertension 2018;71(3):368-374, doi:10.1161/HYPERTENSIONAHA.117.10237. Accepted manuscript: https://discovery.ucl.ac.uk/id/eprint/10048123/1/AAMI-ESH-ISO%20Statement%20REVISED%2020171006.pdf. ISO 81060-2 itself was not opened (paywalled); edition and clause to be confirmed.
- **S2** Peprah YA, Lee JY, Persell SD. Validation testing of five home BP monitoring devices for the upper arm according to ISO 81060-2:2018/AMD 1:2020. J Hum Hypertens 2023;37(2):134-140, doi:10.1038/s41371-022-00795-6, https://pmc.ncbi.nlm.nih.gov/articles/PMC9957726/. Omron-funded.
- **S3** Mindray, BP10 NIBP Module Operator's Manual, rev. 5.0, 2020, §A.7, https://www.mindray.com/content/dam/xpace/en_us/resource-library/patient-monitoring/technical-document/telemetry-monitoring/H-046-011008-00-BP10-Ops-Manual-FDA-5.0.pdf
- **S4** Datex/Instrumentarium, M-NIBP service manual, doc. 885936-2, 1996, https://documents.cdn.ifixit.com/KVKECwoT2gyegiK3.pdf
- **S5** ZOLL, X Series Technical Specifications, 2015, https://www.zoll.com/-/media/LegacyMedia/uploadedfiles/public_site/products/x_series/9656_0235_xseries_spec_us-pdf.ashx
- **S6** ZOLL, M Series Non-Invasive Blood Pressure, 9650-0214-01 Rev. D, 2002, https://documents.cdn.ifixit.com/BkdXMZW5RIrE13Pi.pdf
- **S7** WhaleTeq AP note, "Using BP Simulator to Perform IEC 80601-2-30 Tests with Standard Assistant", https://www.whaleteq.com/en/app/view32. A vendor summary; the standard itself was not opened.
- **S8** ISMP, Acute Care Guidelines for Timely Administration of Scheduled Medications, 2011, https://www.ismp.org/sites/default/files/attachments/2018-02/tasm.pdf
- **S9** Royal College of Physicians, NEWS2 Chart 1, 2017, https://www.rcp.ac.uk/media/alxev00t/news2-chart-1_the-news-scoring-system_0_0.pdf
- **S10** Jordan J, Biaggioni I. Clin Auton Res 2023;33(6):609-611, doi:10.1007/s10286-023-00980-8, https://pmc.ncbi.nlm.nih.gov/articles/PMC10751266/. It quotes Freeman R et al., Clin Auton Res 2011;21:69-72; the primary text was not opened.
- **S11** Ettehad D, et al. Blood pressure lowering for prevention of cardiovascular disease and death. Lancet 2016;387:957-967, doi:10.1016/S0140-6736(15)01225-8 (PubMed 26724178 abstract).
- **S12** IEC 60601-1-8 Ed. 2.0 Amd 1:2012, 6.1.2 and Table 1, from the SIS preview https://www.sis.se/api/document/preview/571712/. Amd 2:2020 was not opened.
- **S13** IHE ITI TF Vol. 2 Rev. 20.0 (2023), ITI-1 Maintain Time, https://profiles.ihe.net/ITI/TF/Volume2/ITI-1.html
- **S14** TI SimpleLink BLE5-Stack User's Guide, "Clock accuracies and Bluetooth LE", https://software-dl.ti.com/simplelink/esd/simplelink_cc13xx_cc26xx_sdk/6.40.00.13/exports/docs/ble5stack/ble_user_guide/html/ble-stack-5.x/custom-hardware-cc13xx_cc26xx-ble.html. It cites Core Spec 5.2 Vol 6 Part B §4.2.1, which was not opened.
- **S15** Tipparaju VV, et al. Mitigation of Data Packet Loss in BLE-Based Wearable Healthcare Ecosystem. Biosensors 2021;11(10):350, doi:10.3390/bios11100350.
- **S16** De Bleser L, et al. How accurate are electronic monitoring devices? Sensors 2010;10(3):1652-60, doi:10.3390/s100301652 (PMC3264443).
- **S17** Ganssle J. A Guide to Debouncing, rev. 3, 2008, https://my.eng.utah.edu/~cs5780/debouncing.pdf

### VitalDB estimate (method)

Files are in `docs/formal/evidence/ws01-t09/`: script `cuff_vs_art.py` (output `cuff_vs_art.out`), post-hoc check `posthoc.py`, diagnostics `diag.py`, venv `venv/` (vitaldb 1.7.2). Data were read-only from `data/raw/vitaldb/vital_files/` (VitalDB 1.0.0, CC BY 4.0).

- **Readings.** NIBP_SBP repeats its held value every 2 s. A reading is a value change, a record after a gap of more than 10 s, or the first record. Identical consecutive readings merge.
- **Pairing.** Each reading at time t is paired with the median ART_SBP in [t-30 s, t+30 s]. Valid ART values are 40-250 mmHg, with at least 15 valid records required.
- **Exclusions** (147 readings in the 14 cases with both tracks):
  - cuff out of 40-250: 0
  - insufficient ART: 74, mostly before the line was connected (ART below 40)
  - ART range in the window above 40 mmHg (flush or transient): 35
- **Result** (n = 38 pairs, 9 cases; 5 cases give 1 pair each):
  - mean -10.0, SD 17.3, median -13.0, robust SD 9.3 mmHg
  - case-bootstrap 95% (seed 20261008): mean [-12.7, -5.8], SD [5.8, 27.8]
  - within-case SD 18.9
- **Post hoc.** Without the pair NIBP 174 / ART 97 (case 0020): n = 37, mean -12.4, SD 9.5.
- **Sensitivity** (mean/SD, pairs/cases):
  - ±15 s: -8.9/15.9 (52/10)
  - ±60 s: -10.4/17.5 (36/8)
  - [t-60, t]: -11.5/18.8 (38/7)
  - no range filter: -9.4/14.8 (73/12)
  - range ≤20: -10.2/18.2 (33/6)
- **Caveats.**
  - Patients were anaesthetised and intraoperative.
  - An arterial line is not the ISO 81060-2 reference (S1 keeps two-observer auscultation), and the ART numeric has its own error.
  - Only 30 cases were downloaded, with few pairs per case.
  - The thresholds are my choices.

### Rows

#### scale_range
- file: registry entry
- unit: mmHg
- current: 20
- status: proposed
- value: 20 (alternative 10)
- citation: S10; S9
- passage: S10: "reduction in systolic blood pressure of at least 20 mmHg or in diastolic blood pressure of at least 10 mmHg within 3 min of standing". S9: systolic bands "≤90 | 91–100 | 101–110 | 111–219 | ≥220" score 3 | 2 | 1 | 0 | 3.
- consulted_on: 2026-10-08
- derivation: 20 mmHg is a consensus threshold for a significant systolic change. The NEWS2 bands are 10 mmHg wide.
- notes: These are analogies, not a severity unit for a band violation. With cuff SD 8, noise moves σ̃ by 0.4 per SD at s = 20 (Lemma 6, doc 04). Keep s ≥ the cuff SD.
- decision_gab:

#### scale_hold
- file: registry unset
- unit: mmHg
- current: unset
- status: proposed
- value: 10
- citation: S9
- passage: "≤90" scores 3 and "91–100" scores 2 (systolic, mmHg).
- consulted_on: 2026-10-08
- derivation: With the illustrative `bp_hold_threshold` = 100, a 10 mmHg shortfall reaches the NEWS2 red band (≤90), so σ̃ = -1 lands there.
- notes: Valid only if the threshold is 100 (illustrative, unverified). An analogy. F0 uses 20 (FIXTURE-ONLY).
- decision_gab:

#### scale_resp
- file: registry unset
- unit: mmHg
- current: unset
- status: proposed
- value: 10
- citation: S11
- passage: "Every 10 mm Hg reduction in systolic blood pressure significantly reduced the risk of major cardiovascular disease events (relative risk [RR] 0·80, 95% CI 0·77-0·83)".
- consulted_on: 2026-10-08
- derivation: 10 mmHg is the conventional trial unit of systolic effect, so a shortfall of one unit below `delta_resp` gives σ̃ = -1.
- notes: A weak analogy: S11 concerns long-term outcomes, not an acute response after a dose. Keep s ≥ the cuff SD.
- decision_gab:

#### scale_sched
- file: registry entry
- unit: ms
- current: 1800000
- status: proposed
- value: 1800000
- citation: S8
- passage: "Time-critical scheduled medications are those where early or delayed administration of maintenance doses of greater than 30 minutes before or after the scheduled dose may cause harm or result in substantial sub-optimal therapy or pharmacological effect." For non-time-critical doses the window is "Within 1 hour" or "Within 2 hours".
- consulted_on: 2026-10-08
- derivation: s = one time-critical tolerance (30 min).
- notes: An analogy: S8 is about medication administration, not BP measurements. Alternatives are 3600000 or 7200000 if measurements are non-time-critical. S8: "The guidelines are not standards or evidence-based practices".
- decision_gab:

#### scale_count
- file: registry entry
- unit: dose
- current: 1
- status: no-literature-value
- value: -
- citation: -
- passage: -
- consulted_on: 2026-10-08
- derivation: -
- notes: A design choice. The margin is an integer, so s = 1 saturates every violation at -1 and gives no grading. Use s = `dose_max_24h` if grading is wanted. 1 dose is the smallest deviation the counter can show.
- decision_gab:

#### scale_sys
- file: registry unset
- unit: ms
- current: unset
- status: no-literature-value
- value: -
- citation: S5, S6 (context)
- passage: S6: "Measurement Cycle Time Typical: 30 seconds Worst Case: 180 seconds". S5: "15 – 30 sec – Sure BP (on inflation)".
- consulted_on: 2026-10-08
- derivation: -
- notes: A design choice that needs device data. Candidate: typical duration minus `cuff_inflation_min`, so that a typical reading gives σ̃ = +1. That is 15000 ms with the ZOLL figures (my arithmetic).
- decision_gab:

#### scale_int
- file: registry unset
- unit: ms
- current: unset
- status: no-literature-value
- value: -
- citation: -
- passage: -
- consulted_on: 2026-10-08
- derivation: -
- notes: A design choice. Suggestion: s = `int_window` (as in F0). Then a witness at the dispense gives +1, one at the window edge 0, and one two windows old -1.
- decision_gab:

#### priority_hold, priority_range, priority_sched (entries 1, 2, 3); priority_count, priority_resp, priority_sys, priority_int (unset)
Seven rows that share one finding. Each has unit `1`, status no-literature-value, value `-` and consulted_on 2026-10-08, with one decision per row.
- file: registry entry (hold, range, sched; from the analisi example) / registry unset (count, resp, sys, int)
- citation: S12
- passage: "For each HAZARDOUS SITUATION where the MANUFACTURER has chosen to use an ALARM SYSTEM as a means of RISK CONTROL, the MANUFACTURER shall assign an ALARM CONDITION and its priority using Table 1." The Table 1 rows are death or irreversible injury: High/High/Medium; reversible injury: High/Medium/Low; "Discomfort or reversible minor injury": Medium/Low/Low. The columns are "Immediate" ("not usually sufficient for manual corrective action"), "Prompt" ("usually sufficient") and "Delayed".
- derivation: -
- notes:
  - S12 gives a procedure, not a ranking of our templates. Suggestion: the clinician classifies each violation by harm and onset, then HIGH → 1, MEDIUM → 2, LOW → 3, with ties allowed and σ̃ deciding within a class (doc 04 §4).
  - Strawman, neither literature nor clinical: count excess next to hold (1); resp (delayed onset) 3.
  - SYS is a technical condition and INT an integrity one; they may need their own class (ADR).
- decision_gab:

#### int_window
- file: registry entry
- unit: ms
- current: 300000
- status: no-literature-value
- value: -
- citation: -
- passage: -
- consulted_on: 2026-10-08
- derivation: -
- notes: No literature found; this is local policy plus a workflow measurement. It must be ≥ the observed robot-observation-to-dispense delay (WS07/WS10) + `2·clock_skew_max_ms` (doc 01 §4.4), and a multiple of `step_ms`.
- decision_gab:

#### cuff_inflation_min
- file: registry unset
- unit: ms
- current: unset
- status: no-literature-value
- value: - (candidate 15000)
- citation: S4, S5, S6
- passage: S4: "Measurement time, typical adult 23s infant 20s". S5: "15 – 30 sec – Sure BP (on inflation)". S6: "This cycle takes approximately 30 seconds."
- consulted_on: 2026-10-08
- derivation: The manuals give typical and maximum times, never a minimum. The candidate is the lowest typical edge found (S5).
- notes: Needs the deployed cuff's specification. The signal is "inflation duration", but the manuals give the full cycle; this has to be clarified.
- decision_gab:

#### bound_inflation_ms_lower
- file: registry unset
- unit: ms
- current: unset
- status: no-literature-value
- value: - (suggested 0)
- citation: -
- passage: -
- consulted_on: 2026-10-08
- derivation: -
- notes: The physical lower bound of a duration, used only for interval completion (WS01-T05 decides whether it is needed).
- decision_gab:

#### bound_inflation_ms_upper
- file: registry unset
- unit: ms
- current: unset
- status: proposed
- value: 180000
- citation: S7; S6; S3; S4
- passage: S7: "Under normal conditions, A protection mechanism is used to ensure that the total duration of cyclic blood pressure measurement does not exceed 90s /180s (neonatal mode/child and adult mode)." S6: "If after 180 seconds the M Series has not been able to determine systolic, diastolic or mean pressure, it aborts the measurement and deflates the cuff." S3: "Maximum measurement time Adult and pediatric: 120 seconds". S4: "Independent timing circuit limits pressurizing (>15 mmHg) time to 2 minutes maximum in adult/child mode".
- consulted_on: 2026-10-08
- derivation: The adult limit of the device standard gives a device-independent bound. A known device's limit (120000 for S3/S4) is tighter.
- notes: Confirm clause 201.105.1 (per S7) in IEC 80601-2-30 itself.
- decision_gab:

#### cuff_error_sd
- file: registry unset
- unit: mmHg
- current: unset
- status: proposed
- value: 8
- citation: S1; S3; S2
- passage: S1: "mean difference of test versus reference BP measurements ≤5 mmHg with SD ≤8 mmHg for systolic and diastolic BP". S3: "Maximum mean error: +/- 5 mmHg Maximum standard deviation: 8 mmHg". S2: "BP7450 0.5 (7.7)", "BP5450 1.9 (7.0)".
- consulted_on: 2026-10-08
- derivation: The largest SD a passing device may have, which makes it a conservative device model. Manufacturers quote it as their specification (S3).
- notes:
  - This is an acceptance limit, not a typical value. Typical passing devices report 7.0-7.7 (S2).
  - S1: "passing these requirements does not equate to ideal accuracy".
  - The VitalDB SD (17.3; 9.5 post hoc) suits a rho mismatch stress test, not the matched case.
  - Keep one source of truth with `cuff_error_sd_mmhg` (OP-7).
- decision_gab:

#### clock_skew_max_ms
- file: registry unset
- unit: ms
- current: unset
- status: proposed
- value: 1000 for synchronised nodes; for BLE devices see the bound below
- citation: S13; S14
- passage: S13: "Implementations must support a time synchronization accuracy with a median error of less than one second." S14: "The Bluetooth Core Specifications Version 5.2 require the sleep clock to have a drift less than or equal to ±500 ppm" (active clock "±50 ppm").
- consulted_on: 2026-10-08
- derivation: For a device resynchronised every H hours with drift d ppm, skew ≤ e_sync + d·10⁻⁶·H·3.6·10⁶ ms. With e_sync = 1000 ms, d = 500 and H = 24 this gives 44200 ms (my arithmetic).
- notes:
  - S13 bounds the median, not the maximum.
  - S14 is a link-layer clock and may not be the timestamp clock.
  - 44 s is close to `step_ms`.
  - This is a system parameter: measure it on the WS07/WS10 devices.
- decision_gab:

#### cuff_error_sd_mmhg
- file: prior
- unit: mmHg
- current: awaiting_human_value
- status: proposed
- value: 8
- citation: S1; S2; VitalDB estimate, `docs/formal/evidence/ws01-t09/cuff_vs_art.py`
- passage: As in cuff_error_sd. VitalDB: SD 17.3 (38 pairs, 9 cases); 9.5 post hoc.
- consulted_on: 2026-10-08
- derivation: Matched with the registry entry. Scenario tiers from S1: "high accuracy" SD 3-6; low accuracy "0 ± 10-12".
- notes: The rationale must say "acceptance limit used as a conservative device model". VitalDB is supplementary only.
- decision_gab:

#### cuff_bias_mmhg
- file: prior
- unit: mmHg
- current: awaiting_human_value
- status: proposed
- value: 0 (stress 4 and 5)
- citation: S1; S2
- passage: S1: "'high accuracy' device (defined as mean BP difference between reference and test device measurement and its associated standard deviation 0 ± 3-6 [mean±SD] mmHg)"; "'moderate accuracy' device (difference 4±5 mmHg)"; limit "≤5 mmHg". S2: means 0.5 and 1.9 for the passing devices.
- consulted_on: 2026-10-08
- derivation: 0 is S1's high-accuracy definition. 4 (moderate accuracy) and 5 (the limit) are stress values.
- notes: The VitalDB -10.0 (NIBP below ART) comes from anaesthetised patients against an arterial reference; do not transfer it to the ward model.
- decision_gab:

#### dispenser_bounce_prob
- file: prior
- unit: 1 (per dispense)
- current: awaiting_human_value
- status: proposed
- value: 0.001 (range 0-0.005)
- citation: S16; S17 (context)
- passage: S16: "Only a few overregistrations were recorded: 2/420 (0.48%) in the HH without reminder and 1/630 (0.16%) in the HH with reminder. There were no overregistrations in either MEMS group." "In total, 3,150 manipulations were conducted." S17: "the other 16 switches exhibited an average 1557 μsec of bouncing, with, as I said, a max of 6200 μsec".
- consulted_on: 2026-10-08
- derivation: 3/3150 = 0.00095 per manipulation. The range runs from 0/1050 to 2/420 = 0.0048.
- notes: An analogy: adherence monitors, not a ward dispenser. S16 says "The MEMS is programmed to ignore extra registrations within 15 minutes after the initial registration" (and HH duplicates were deleted), so the rates hold only after debouncing. Raw bounces last milliseconds (S17); whether one survives depends on the debounce window, a design parameter.
- decision_gab:

#### ble_dropout_rate_per_h
- file: prior
- unit: 1/h
- current: awaiting_human_value
- status: no-literature-value
- value: -
- citation: S15 (context)
- passage: S15: "lowered transmission frequency and data bundling reduce the packet losses to less than 1%. The queue-based packet transmission protocol eliminates any remaining packet loss by using re-request routines."
- consulted_on: 2026-10-08
- derivation: -
- notes: No ward study reports BLE dropouts per hour. Wearable studies report % data loss mixing radio, contact and Wi-Fi causes, and S15 shows the loss depends on the protocol. Suggestion: a sweep (for example 0, 0.1, 1 per hour, a design choice) plus measurement on the WS07/WS10 hardware.
- decision_gab:

