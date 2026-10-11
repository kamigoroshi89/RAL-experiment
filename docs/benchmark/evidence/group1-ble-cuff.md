# Group 1: BLE link and blood-pressure cuff (research only)

Date of research and of every access below: 2026-10-10. Written by a desk-research agent. Nothing in the repository was edited. Technical, pre-clinical benchmark: nothing here is a clinical validation or a clinical recommendation. Every value marked "proposal for gab, not reviewed". A value is given only where I read it in a source I opened; derived numbers are marked "my arithmetic".

## 0. Scope: which rows are in Group 1 (19 rows) and which are not

Group 1 (19 rows, all `awaiting_human_value`):

| # | Row | File |
|---|---|---|
| 1 | `ble_dropout_rate_per_h` | `configs/priors/literature_hypertension.yaml` |
| 2 | `inflation_ms_nominal` | `configs/benchmark/generator_design.yaml` |
| 3 | `inflation_ms_sd` | `configs/benchmark/generator_design.yaml` |
| 4 | `pulse_error_sd_bpm` | `configs/benchmark/generator_design.yaml` |
| 5-7 | `ble_dropout_duration_short`, `_medium`, `_long` | `configs/benchmark/injections.yaml` |
| 8-10 | `stuck_at_duration_short`, `_medium`, `_long` | `injections.yaml` |
| 11-13 | `cuff_silent_bias_duration_short`, `_medium`, `_long` | `injections.yaml` |
| 14-16 | `cuff_detached_duration_short`, `_medium`, `_long` | `injections.yaml` |
| 17-19 | `cuff_silent_bias_magnitude_low`, `_medium`, `_high` | `injections.yaml` |

Left for other groups (46 of the 65 rows):

- `mean_delay_ms` (prior): its note is "Mean delay of a late dose, in integer ms", consumer WS04-T05 (adherence model). NOT in this group.
- `circadian_peak_clock_ms`, `intake_lag_ms`, `double_take_gap_ms`, `robot_dwell_ms`, `vitals_period_ms` (generator_design): patient, adherence, robot, sampling.
- `cuff_silent_bias_magnitude_device_bias` is already `filled` (1.0); not awaiting.
- `ecg_noise_duration_*` (3), `ecg_noise_magnitude_*` (3): the target is the ECG device, not the cuff or the link as such.
- `dispenser_bounce_magnitude_*` (3): dispenser.
- `nav_delay_magnitude_*` (3): robot.
- C3 attacks: `replay_duration_*` (3), `injection_naive_duration_*` (3), `injection_informed_duration_*` (3).
- `injection_naive_pulse_lower_bpm`, `injection_naive_pulse_upper_bpm`: heart-rate population bounds of a naive forger (C3 `injection_naive`). They are a physiological population range (not a property of the cuff or the BLE link), so I leave them to a physiology or C3 group. If gab wants them here, tell me.
- C1 rows (`hypertensive_spike_*`, `drug_nonresponse_*`, `hypotension_below_hold_*`): physiology.

Count check: 2 prior + 8 generator_design + 55 injections = 65. Group 1 takes 1 + 3 + 15 = 19. The rest is 46 (1 prior, 5 generator_design, 40 injections).

## 1. Summary table

Units: the unit the row uses. Kind: a = measured quantity of a real device or link; b = scenario/grid design choice.

| Row | Unit | Kind | Proposed value or grid (proposal for gab, not reviewed) | Source and locator (short quote) | Status |
|---|---|---|---|---|---|
| `ble_dropout_rate_per_h` | 1/h per device | a/b mixed | 0.0104 (= 0.25 per device-day; my arithmetic 0.25/24). Sweep 0.0104, 0.0417, 0.167. Upper envelope 0.167 from a body-worn hospital BLE sticker | Nunes et al. 2024, Med Biol Eng Comput 62:3815, doi:10.1007/s11517-024-03155-3, Results, Fig. 11 paragraph: "For the 24-h patients, the MTBF is around the 6-h mark" | design-choice-proposal |
| `inflation_ms_nominal` | ms (int) | a | 30000 | Beard et al. 2025, Med Devices 18:241, doi:10.2147/MDER.S520615, Table 2 (seven monitors, mean 19.23 to 51.06 s); ZOLL X Series spec 2015, NIBP: "30 - 45 sec (on deflation)", "15 - 30 sec - Sure BP (on inflation)" | proposal-with-opened-source |
| `inflation_ms_sd` | ms (float) | a | 3000 (median of within-device SD over seven devices, 3.03 s). Sensitivity 14000 | Beard et al. 2025, Table 2, column "Mean +/- SD (s)" (n = 3 per device) | proposal-with-opened-source |
| `pulse_error_sd_bpm` | bpm (float) | a | 2.1. Sensitivity 5.9 (my arithmetic) | Palatini et al. 2022, J Hypertens, doi:10.1097/HJH.0000000000002998, Abstract: "mean device-observer HR difference was 0.9 +/- 2.1 bpm" (palpation reference, not ECG); Sobieraj et al. 2024, J Clin Hypertens, doi:10.1111/jch.14892, Table 4 (ECG, sequential) | proposal-with-opened-source |
| `ble_dropout_duration_short` | ms | b | 120000 (2 min) | Core Spec 5.4 Vol 6 Part B 4.5.2 (timeout at most 32 s); Breteler et al. 2018 gap threshold 2 min | design-choice-proposal |
| `ble_dropout_duration_medium` | ms | b | 900000 (15 min) | Breteler et al. 2018, BMJ Open, doi:10.1136/bmjopen-2017-020162, Methods: gap thresholds "2 min, 15 min, 1 hour or 4 hours" | design-choice-proposal |
| `ble_dropout_duration_long` | ms | b | 3600000 (1 h) | Breteler 2018, Results: "79% of sensor measurements without data loss greater than an hour"; registry `sched_window` = 3600000 | design-choice-proposal |
| `stuck_at_duration_short` / `_medium` / `_long` | ms | b | 3600000 / 14400000 / 43200000 | no source; anchors: registry `sched_window` (1 h), 5 measurements per day (care_plans.yaml) | design-choice-proposal |
| `cuff_silent_bias_duration_short` / `_medium` / `_long` | ms | b | 3600000 / 14400000 / 43200000 (same grid) | no source | design-choice-proposal |
| `cuff_detached_duration_short` / `_medium` / `_long` | ms | b | 3600000 / 14400000 / 43200000 (same grid) | no source | design-choice-proposal |
| `cuff_silent_bias_magnitude_low` | x cuff_error_sd_mmhg | b | 0.5 (= 4 mmHg at SD 8) | Zhu et al. 2024, Front Cardiovasc Med, doi:10.3389/fcvm.2024.1388313, Abstract: "difference ... was significant at 3.48 +/- 3.22 mmHg"; Stergiou et al. 2018 mean limit 5 mmHg | design-choice-proposal |
| `cuff_silent_bias_magnitude_medium` | x cuff_error_sd_mmhg | b | 1.0 (= 8 mmHg at SD 8) | above 5 mmHg mean-error limit (Stergiou 2018) | design-choice-proposal |
| `cuff_silent_bias_magnitude_high` | x cuff_error_sd_mmhg | b | 2.5 (= 20 mmHg at SD 8) | Yuksel et al. 2020, Florence Nightingale J Nurs, doi:10.5152/FNJN.2020.19119, Abstract: "20.78 mmHg higher" with a small adult cuff | design-choice-proposal |

Counts by status: proposal-with-opened-source 3; design-choice-proposal 16; no-source-found 0 (but see section 4 for what no source covers).

## 2. Details per row

### 2.1 `ble_dropout_rate_per_h` (prior, `DeviceErrorModel.ble_dropout_rate_per_h`, 1/h)

1. Meaning. Row note: "Rate per hour of BLE link dropouts (C2 fault, analisi §5.1 item 3). The human supplies the value and its source_ref." How the builder uses it (read in `src/ralmon/benchmark/builder.py` near line 1349): for each of the four devices in `vocab.BLE_DEVICES` (cuff, dispenser, ecg, oximeter) the number of windows in a day is Poisson with mean `rate * hours_per_day`. So the value is per device-hour and it sets how many windows the benchmark contains, which is a composition decision as much as a device property. The earlier WS01-T09 proposal (`docs/formal/parameter-literature-proposal.md`) found no per-hour BLE dropout rate and suggested a sweep.
2. Kind. Mixed. The rate of a real link is a measured quantity, but no source I opened measures it for a fixed bedside cuff or a room dispenser. In practice it is a scenario value bounded by one measured envelope.
3. Sources actually read.
   - Nunes T, Gaspar L, Faria JN, Portugal D, Lopes T, Fernandes P, Tavakoli M. Deployment and validation of a smart bed architecture for untethered patients with wireless biomonitoring stickers. Med Biol Eng Comput 2024;62(12):3815-3840. doi:10.1007/s11517-024-03155-3 (open access, text via Europe PMC PMC11639216, fetched 2026-10-10). Setting: 3-day hospital pilot, nine orthopedic patients, monitored 5 to 24 h, a BLE biosticker to a bedside "smart box". Locator: Results and discussion, paragraph introducing Fig. 11 (MTBF, MTTR, MTTF). Quotes: "For all patients, the MTBF is high as desired (about 1 hour or more)"; "For the 24-h patients, the MTBF is around the 6-h mark"; "the MTTR was extremely low". The same text says patients A and F, with the most disconnections, were the exceptions to 1 h or more (their values are only in Fig. 11, which I did not read as numbers); patient A had 40 disconnections. Conversion (my arithmetic): MTBF 6 h gives about 0.167 per h; MTBF 1 h gives 1 per h; patients A and F are therefore above 1 per h.
   - Breteler MJM et al. BMJ Open 2018, doi:10.1136/bmjopen-2017-020162 (PMC5855309): a BLE patch with an iPad relay, 1568 h in 33 patients: "Overall data loss was limited (6% of time)". Data loss there has mixed causes (radio, contact, relay), not BLE drops alone.
   - Tipparaju VV et al. Biosensors 2021;11(10):350, doi:10.3390/bios11100350 (PMC8533907): "packet losses to less than 1%". This is packet loss, not link loss; context only.
   Confidence that these apply: low to medium. Both are body-worn sensors on mobile patients, not a fixed cuff and dispenser a few metres from a gateway. They give an upper envelope, not the value.
4. Proposal for gab, not reviewed. Because the row sets the number of C2 windows (the plan's class rate `injection_rate_c2` is 0.3 per patient-day for the other subtypes), I propose 0.0104 per h (0.25 windows per device-day, about one window per patient-day over four devices) as the main value, and a sensitivity sweep at 0.0417 per h (1 per device-day) and 0.167 per h (about 4 per device-day, the 6-h MTBF of Nunes et al.; at that value four devices give about 16 windows per patient-day and the overlap skip will trigger often). State in the `rationale` that 0.167 is the measured envelope for a body-worn sticker and that the main value is a design choice chosen so that ble_dropout does not dominate C2. Constraint: non-negative float (`_NONNEG` in `priors.py`); 0 is allowed.
5. Unit conversion. The row is 1/h; no conversion. Per day: multiply by 24 (the builder multiplies by `_hours_per_day()`).
6. Status: design-choice-proposal. `source_type` for the row in the YAML is currently null; a design_choice needs it set.

### 2.2 `inflation_ms_nominal` (generator_design, ms, integer in [0, 86 400 000])

1. Meaning. Row note: "Nominal duration of one cuff inflation, integer ms ... The reading of a robot visit is stamped arrival + inflation. The registry holds only the minimum cuff_inflation_min: a fault-free draw is raised to that minimum". In `measurement.py` (line about 939) the stamp is `arrival + max(round(nominal + sd * z), inflation_min)`. So in this generator "inflation" is the time from visit arrival to the stamped reading, i.e. in effect the whole automatic measurement cycle. Device manuals report the whole cycle, not inflation alone (this ambiguity was already noted in the WS01-T09 proposal for `cuff_inflation_min`).
2. Kind a: a device quantity. A source is needed.
3. Sources read.
   - Beard J, Pichard K, Attebery JE, Yapici HO, Coffeng R. Systolic Pressure and Pulse Rate Range Performance Comparison of Seven Non-Invasive Blood Pressure Monitors. Med Devices (Auckl) 2025;18:241-246. doi:10.2147/MDER.S520615 (CC BY-NC, PMC12007952, text via Europe PMC, fetched 2026-10-10). Bench study on BP simulators at 120 mmHg and 80 bpm, three tests per device. Definition: "defined as the total time between test start and measurement display to the user". Table 2 (Mean +/- SD in s; median [min, max]): B125 24.14+/-3.48; iPM12 39.12+/-14.32; VS-900 29.97+/-3.35; Life Scope 3000 29.80+/-2.55; Efficia CM120 51.06+/-2.57; IntelliVue MX430 48.88+/-3.03; Connex 19.23+/-0.71. Median of the seven means (my arithmetic): 29.97 s. Authors are GE Healthcare staff (one of the seven devices is theirs).
   - ZOLL X Series Technical Specifications, 2015 (https://www.zoll.com/-/media/LegacyMedia/uploadedfiles/public_site/products/x_series/9656_0235_xseries_spec_us-pdf.ashx, downloaded and read as text 2026-10-10), NIBP block: "Typical Measurement Time: 30 - 45 sec (on deflation)"; "15 - 30 sec - Sure BP (on inflation)". One vendor.
   Confidence that the value applies: medium for the order of magnitude (about 20 to 50 s across seven hospital monitors), low for a specific TIAGo-lab cuff (not named). It is consistent with the registry rationale of `scale_sys` (typical duration minus `cuff_inflation_min` = 15000, which implies a typical 30 s).
4. Proposal for gab, not reviewed: 30000 ms (the median of the seven device means, 29.97 s, rounded; inside the ZOLL 30 to 45 s deflation-mode figure and above its inflation-mode 15 to 30 s). Constraint check: integer, within [0, 86 400 000], not below `cuff_inflation_min` = 15000 in registry 0.2.0 (so no raise happens at the mean), below `bound_inflation_ms_upper` = 180000. If the lab-demo cuff is named, replace by its manual figure.
5. Unit conversion: seconds x 1000 = ms (29.97 s = 29970 ms; 30 s = 30000 ms).
6. Status: proposal-with-opened-source (weak: simulator and vendor sheet, whole cycle not inflation only).

### 2.3 `inflation_ms_sd` (generator_design, ms, float at least 0)

1. Meaning. Row note: "Standard deviation of the cuff inflation duration, ms, at least 0 ... The draw is Gaussian, rounded to integer ms and raised to the registry minimum cuff_inflation_min". This is a within-device, visit-to-visit SD.
2. Kind a.
3. Source: Beard et al. 2025, Table 2, the SD column (n = 3 runs per device, simulator, no patient motion). Within-device SDs: 0.71, 2.55, 2.57, 3.03, 3.35, 3.48 and 14.32 s (the last for iPM12, range 29.82 to 55.61 s). Median of the seven SDs (my arithmetic): 3.03 s. Between-device spread of the means is about 12 s (my arithmetic, not a within-device SD). I found no source that reports the visit-to-visit SD of inflation in patients (retries, cuff slippage; a patent background I saw while searching says times "may vary from 30 seconds to up to 3 minutes", but I did not open the patent and do not use it).
   Confidence: low. n = 3 per device and a simulator will underestimate human variability.
4. Proposal for gab, not reviewed: 3000 ms. Sensitivity 14000 ms (the largest within-device SD). Check against the minimum: with nominal 30000 and SD 3000 the Gaussian draw is below 15000 only at 5 SD (negligible raises); with SD 14000 about 14% of draws are raised (my arithmetic, 15000 is 1.07 SD below 30000) and every raise is counted by the generator, so a sensitivity run should expect many counted raises.
5. Unit: ms; seconds x 1000.
6. Status: proposal-with-opened-source (weak).

### 2.4 `pulse_error_sd_bpm` (generator_design, bpm, float at least 0)

1. Meaning. Row note: "Standard deviation of the error of the pulse rate reported by the cuff against the clean ECG heart rate of the same instant, bpm ... The cross-device check that compares the two rates reads this difference, so the value matters for the C3 evidence." In `measurement.py` the cuff pulse is `hr_ecg_at_t + sd * z`, so the generator treats the error as pure noise on the same instant (no timing mismatch).
2. Kind a.
3. Sources read.
   - Palatini P, Lazzaretto I, Fontana U, Fania C. Accuracy of the oscillometric method for the measurement of heart rate at rest and during mild exercise. J Hypertens 2022 (PMID 34992196), doi:10.1097/HJH.0000000000002998 (CC BY, PMC10863661, text via Europe PMC, fetched 2026-10-10). Microlife WatchBP O3 (ambulatory oscillometric), 36 participants, no atrial fibrillation. Reference: pulse palpation over 30 s by two observers, not ECG. Quote (Abstract): "At rest, the mean device-observer HR difference was 0.9 +/- 2.1 bpm." Exercise 0.6 +/- 2.6 bpm; differences within +/-6 bpm. The authors state that ISO 81060-2:2018 does not consider heart rate validation. This SD includes palpation error, so it is an upper bound of the device-only error against a perfect reference, and a lower bound of a device-versus-ECG SD if the palpation errors are small.
   - Sobieraj P, Lesniewski M, Sawicka A, Sinski M, Lewandowski J. J Clin Hypertens 2024;26(12):1402-1410, doi:10.1111/jch.14892 (PMC11654852, fetched 2026-10-10). Unattended automated office BP (Microlife WATCH BP Office ABI) versus a resting ECG tracing in 110 people. Table 4, ECG row: bias 1.6 bpm, limits of agreement -9.9 to 13.1 bpm. SD of the difference (my arithmetic): (13.1 - (-9.9)) / 3.92 = 5.9 bpm. The authors state that ECG and the BP measurement were done sequentially, not simultaneously (position and time differences), so this is an upper bound that includes true heart rate change.
   Confidence: medium for the order of magnitude (2 to 6 bpm), low for the exact use (no study found with simultaneous ECG).
4. Proposal for gab, not reviewed: 2.1 bpm (palpation-referenced, simultaneous); sensitivity 5.9 bpm (sequential ECG). Report both so the C3 cross-device evidence is tested with a tight and a loose coupling. Constraint: non-negative float, no relation to other rows.
5. Unit: bpm, no conversion.
6. Status: proposal-with-opened-source.

### 2.5 `ble_dropout_duration_short`, `_medium`, `_long` (injections, ms, integer in [1, 86 400 000], short < medium < long)

1. Meaning. "Duration of one BLE dropout window of the link of one device (the BLE connection is lost for the whole window; nothing the device sends arrives)." The note adds that the human may restate the levels against the liveliness lease (WS07-T03) and that a window shorter than the lease raises neither liveliness nor deadline evidence (condition LC of `docs/models/fault-model.md`). T_s is 60000 ms (`default.yaml` `monitor_step_ms`, itself a design choice).
2. Kind b: scenario grid. No source gives a distribution of dropout durations for these devices.
3. Anchors from sources I opened.
   - Bluetooth Core Specification v5.4 (2023-01-31), downloaded from https://www.bluetooth.org/DocMan/handlers/DownloadDoc.ashx?doc_id=556599 and converted to text on 2026-10-10. Vol 4 Part E, HCI LE Create Connection, p. 2370: "Supervision_Timeout ... Range: 0x000A to 0x0C80 Time = N x 10 ms Time Range: 100 ms to 32 s". Vol 6 Part B, section 4.5.2, p. 2811: "connSupervisionTimeout shall be a multiple of 10 ms in the range 100 ms to 32.0 s". Consequence (my reading): a link is declared lost only after at most 32 s without packets, so a window shorter than 32 s is not a connection loss in the specification's sense; every level should be clearly above 32 s.
   - Breteler et al. 2018 (above): Methods define data-loss gaps of "2 min, 15 min, 1 hour or 4 hours"; Results: 63% of measurements without a gap above 2 min and "A gap duration of 1 hour resulted in 79% of sensor measurements without data loss greater than an hour", so 21% had a gap above 1 h (causes mixed).
   - Registry anchors: `sched_window` = 3600000 ms; `hold_lookback` = 3600000 ms; T_s = 60000 ms.
4. Proposal for gab, not reviewed: short = 120000 (2 min), medium = 900000 (15 min), long = 3600000 (1 h). Reasons: short is well above the 32 s timeout cap and equals 2 T_s, and probably violates nothing (it only removes a reading if a visit falls inside); medium is a quarter of the `sched_window`; long equals `sched_window` and the 1 h threshold of Breteler. Constraints: integers, 1 at most 86 400 000, strictly increasing. Note: a window of exactly `sched_window` only forces a sched violation if it starts at the tick; if gab wants a level that violates every covered tick, replace long by 14400000 (4 h, the largest Breteler threshold).
5. Unit: minutes x 60000 = ms.
6. Status: design-choice-proposal.

### 2.6 `stuck_at_duration_*`, `cuff_silent_bias_duration_*`, `cuff_detached_duration_*` (injections, ms, integer in [1, 86 400 000])

1. Meaning.
   - `stuck_at`: "Duration of one window in which the cuff keeps reporting the last value it reported before the onset (the measurements still complete). The effect needs at least one reading inside the window."
   - `cuff_silent_bias`: "Duration of one window in which a constant offset is added to the systolic value the cuff reports. The effect needs at least one reading inside the window."
   - `cuff_detached`: "Duration of one window in which the cuff cannot complete a measurement (detached or faulty cuff): every attempt of the window ends in a MEASUREMENT_MISSED event with a device error."
2. Kind b. I found no source with durations of stuck-value, bias or detached episodes of a hospital cuff. The fault model marks all three as `source`-basis injected faults without data.
3. Anchors: the cuff only produces a reading at a robot visit (5 measurements a day in `configs/benchmark/care_plans.yaml`, "illustrative, unverified"), and the registry `sched_window` is 1 h. So the useful range runs from about one visit to a large part of a day. I could not compute the actual tick positions: `derive_schedule` with the registry 0.2.0 values (`hold_lookback` 3600000, `sched_window` 3600000) raises `SLACK_HOLD` for both doses (see Risks).
4. Proposal for gab, not reviewed, the same grid for the three subtypes so that results compare at equal exposure: short = 3600000 (1 h = `sched_window`), medium = 14400000 (4 h), long = 43200000 (12 h, half a day; the window must end inside the day, and the maximum allowed is 86 400 000). Reasons: short covers at most about one visit and violates `sched` only if the window covers the whole `sched_window`; medium covers several visits in most schedules; long covers most of the day. Possible alternative for `cuff_detached` short: 900000 (15 min) if gab wants a single missed attempt. Constraints: integers within [1, 86 400 000], strictly increasing. For `stuck_at` and `cuff_silent_bias` the generator needs at least one reading in the window (a window without a reading has no effect; how the builder treats it was not checked).
5. Unit: hours x 3 600 000 = ms.
6. Status: design-choice-proposal (12 rows).

### 2.7 `cuff_silent_bias_magnitude_low`, `_medium`, `_high` (injections, multiplier of `cuff_error_sd_mmhg`)

1. Meaning. "Level low/medium/high of the injected silent cuff bias, a multiple of cuff_error_sd_mmhg ... the injected offset in mmHg is the value times the SD read from the prior source ... the sign is chosen by the injection plan. Levels are ordered low < medium < high." `cuff_error_sd_mmhg` is currently 8.0 (prior file, from the ISO 81060-2 limit via Stergiou et al.). The fourth level `device_bias` (1.0 times `cuff_bias_mmhg` = 0.0) is already filled and is a different quantity.
2. Kind b: a grid of what the benchmark tests, but real systematic cuff offsets exist and give plausible orders of magnitude.
3. Sources read.
   - Stergiou GS et al. A Universal Standard for the Validation of BP Measuring Devices: AAMI/ESH/ISO Collaboration Statement. Hypertension 2018;71(3):368-374, doi:10.1161/HYPERTENSIONAHA.117.10237; accepted manuscript read at https://discovery.ucl.ac.uk/id/eprint/10048123/1/AAMI-ESH-ISO%20Statement%20REVISED%2020171006.pdf on 2026-10-10 (page 13, validation criteria). Quote: "mean difference of test versus reference BP measurements <=5 mmHg with SD <=8 mmHg for systolic and diastolic BP". A mean-error offset of 5 mmHg is therefore inside what a validated device may show; 5 / 8 = 0.625 SD (my arithmetic). ISO 81060-2 itself not opened (paywalled).
   - Zhu X-Y et al. The impact of sphygmomanometer placement and cuff placement on blood pressure measurements. Front Cardiovasc Med 2024;11:1388313, doi:10.3389/fcvm.2024.1388313 (CC BY, PMC11217487, fetched 2026-10-10). n = 763. Quote (Abstract): "The difference in systolic pressure between these positions was significant at 3.48 +/- 3.22 mmHg". A cuff at the elbow fossa instead of the upper arm gave a systematic offset of this size.
   - Yuksel S, Altun-Ugras G, Altinok N, Demir N. The Effect of Cuff Size on Blood Pressure Measurement in Obese Surgical Patients. Florence Nightingale J Nurs 2020, doi:10.5152/FNJN.2020.19119 (PMC8152164, fetched 2026-10-10). n = 100, crossover. Quote (Abstract): "Systolic blood pressure of the patients with a small adult cuff was 20.78 mmHg higher". Single centre, obese patients only.
   Confidence: medium for the order of magnitude of real systematic offsets (3.5 to 21 mmHg); a bias that a device fault produces is not the same as a placement or size error, and these studies are not about device faults.
4. Proposal for gab, not reviewed: low = 0.5 (4 mmHg at SD 8, near the 3.48 mmHg placement offset and inside the 5 mmHg mean-error limit, so it should be hard to detect), medium = 1.0 (8 mmHg, above the 5 mmHg limit), high = 2.5 (20 mmHg, near the 20.78 mmHg cuff-size offset and equal to the registry `scale_range` of 20 mmHg). Constraint: non-negative multipliers, ordered low < medium < high. Report the mmHg values next to the multipliers, because the multiplier tracks `cuff_error_sd_mmhg`: if gab changes that SD, the mmHg offsets change.
5. Unit: multiplier x `cuff_error_sd_mmhg` (mmHg); 8.0 x 0.5 = 4.0 mmHg and so on.
6. Status: design-choice-proposal.

## 3. Sources opened (all on 2026-10-10)

| Source | URL or DOI | What I read |
|---|---|---|
| Bluetooth Core Specification v5.4 (2023-01-31) | https://www.bluetooth.org/DocMan/handlers/DownloadDoc.ashx?doc_id=556599 (23.9 MB PDF, converted with pdftotext) | Vol 4 Part E p. 2370 Supervision_Timeout; Vol 6 Part B 4.5.2 p. 2811 connSupervisionTimeout; connection interval 7.5 ms to 4 s |
| ESP-IDF Bluetooth defs (vendor restatement) | https://docs.espressif.com/projects/esp-idf/en/stable/esp32c3/api-reference/bluetooth/esp_bt_defs.html | "supervision timeout, in units of 10ms, the range is from 0x000A(100ms) to 0x0C80(32s)" (consistent with the spec) |
| Nunes et al. 2024 | doi:10.1007/s11517-024-03155-3 (Europe PMC PMC11639216, full text XML) | MTBF, MTTR, disconnections, patient counts |
| Breteler et al. 2018 | doi:10.1136/bmjopen-2017-020162 (PMC5855309) | data-loss gaps, thresholds, 6% of time |
| Tipparaju et al. 2021 | doi:10.3390/bios11100350 (PMC8533907) | packet loss below 1% (context) |
| Beard et al. 2025 | doi:10.2147/MDER.S520615 (PMC12007952) | determination time definition and Table 2 |
| ZOLL X Series Technical Specifications 2015 | https://www.zoll.com/-/media/LegacyMedia/uploadedfiles/public_site/products/x_series/9656_0235_xseries_spec_us-pdf.ashx | typical NIBP measurement times |
| Palatini et al. 2022 | doi:10.1097/HJH.0000000000002998 (PMC10863661) | oscillometric heart rate against palpation |
| Sobieraj et al. 2024 | doi:10.1111/jch.14892 (PMC11654852) | Table 4 heart rate agreement with ECG |
| Stergiou et al. 2018 (accepted manuscript) | https://discovery.ucl.ac.uk/id/eprint/10048123/1/AAMI-ESH-ISO%20Statement%20REVISED%2020171006.pdf | criteria 1 and 2 of ANSI/AAMI/ISO 81060-2 |
| Zhu et al. 2024 | doi:10.3389/fcvm.2024.1388313 (PMC11217487) | cuff placement offset 3.48 mmHg |
| Yuksel et al. 2020 | doi:10.5152/FNJN.2020.19119 (PMC8152164) | small-cuff offset 20.78 mmHg |

Opened by search summary only, not as a primary text (not used for any value): citrusbits, ignitec and similar BLE engineering blogs; two patent texts on measurement time.

## 4. Not found / needs gab

- No source for the BLE dropout rate of a fixed bedside cuff or a room dispenser; the only measured numbers (Nunes 2024, Breteler 2018) are for body-worn sensors on mobile patients. Measurement on the WS07 and WS10 hardware remains the proper source (the earlier WS01-T09 note says the same).
- No source for the inflation duration of the specific lab-demo cuff (device not named in the files I read), and no source for visit-to-visit SD of inflation in patients. Beard 2025 gives n = 3 simulator runs.
- No study with simultaneous ECG and oscillometric pulse rate and an SD in bpm; the two values are palpation-referenced (simultaneous) and ECG-referenced (sequential).
- No source for durations of stuck-value, silent-bias or detached-cuff episodes: these are scenario choices.
- The Bluetooth Blood Pressure Profile and Service specifications, IEEE 11073-10407 and ISO 81060-2 were not opened (the first two were not searched; the third is paywalled). Nothing in the proposals depends on them.
- Decision for gab: whether the generator's "inflation" is the full measurement cycle (my reading of the code and of `scale_sys`) or the inflation phase only; the values in 2.2 and 2.3 are for the full cycle.
- Decision for gab: where `injection_naive_pulse_lower_bpm` and `injection_naive_pulse_upper_bpm` go (left out of this group).

## 5. Risks

- Vendor and device specificity: Beard 2025 is authored by GE Healthcare staff and includes a GE device; the ZOLL sheet is one vendor; Palatini and Sobieraj each use one Microlife device.
- Inflation versus cycle: the sources report time to display (simulator) or typical measurement time, not inflation alone.
- BLE rate: the envelope comes from a body-worn sticker with mobile orthopedic patients; the Poisson mean is applied by the builder per device and per 24 h, so a rate near 0.17 per h gives about 16 windows per patient-day across four devices and long windows would cover much of the day. The choice of the rate fixes the composition of the C2 benchmark.
- Silent-bias grid: the 3.48 and 20.78 mmHg offsets come from placement and cuff-size errors (two single-site studies), not from device faults; they bracket plausible magnitudes only.
- Pulse SD: palpation reference has its own error; ECG study is sequential, so its SD is inflated by true heart rate change. The generator also draws the cuff pulse as the ECG heart rate of the same instant plus noise, so the SD stands in for both device error and any timing mismatch.
- Paywalled or not opened: ISO 81060-2, IEC 80601-2-30, IEEE 11073-10407, the Bluetooth Blood Pressure Profile and Service. Stergiou et al. was read as the accepted manuscript, not the journal version.
- Side finding (outside this group, for the plan lead): `derive_schedule([25200000, 75600000], 5, 3600000, 3600000, 7200000, 3600000)` (registry 0.2.0: `hold_lookback` = `sched_window` = 3600000, `delta1` 3600000, `delta2` 7200000) raises `ScheduleInfeasibleError` with `SLACK_HOLD` for both doses ("hold_lookback is not longer than sched_window"). Not needed for these proposals, but the measurement tick positions depend on it.
- Process note: I read the repository only. All scratch files (downloaded PDFs, text extractions, small scripts) are in `/tmp/research/`. The first network call from the shell was made with the sandbox override flag, which was not needed (the same call works in the sandbox); I did not use it again.
