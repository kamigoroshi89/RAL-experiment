# Group 1: observability table of the cuff faults, computed from the generator

2026-10-10. Read-only on the repository (branch `values-group1-blocks-1-2`; I used only the grid values you quoted, not the files another worker is editing). Technical, pre-clinical. Scripts and raw outputs: `/tmp/research/obs/`.

## 0. Method and assumptions

- Schedule from `derive_schedule` with registry 0.2.1 (hold 3600000, delta1 3600000, delta2 7200000, sched_window 1800000): doses 07:00, 21:00; measurement ticks **06:15, 08:15, 14:15, 20:15, 22:15** (gaps 2, 6, 6, 2 h, then 8 h overnight). Pre-dose ticks 06:15 and 20:15; post-dose 08:15 and 22:15.
- Reading instant = tick + jitter + inflation (`measurement.py:922-941`). `default.yaml` has `arrival_jitter: null`, so no jitter (`builder.py:997`). `inflation_ms_nominal` is `null` in `generator_design.yaml`; **assumed 30 s**, so readings at 06:15:30, 08:15:30, 14:15:30, 20:15:30, 22:15:30. Inflation 0 to 60 s changes only the 4th decimal; a jitter of 10 min to 1 h lowers medium mean n from 0.874 to 0.858-0.774.
- Exact enumeration of every onset on the 60 s grid (`builder.py:428-430`). I ran the **real injectors** on a hand-built fault-free day of this structure for all 3303 onsets of the three durations and 5 fault kinds: realised flags equal the closed-form count (0 mismatches).
- Not modelled: C1 refusals, robot faults, adherence delay of dispenses. The full builder was not run (inflation, dwell, vitals period unfilled).

## 1. Readings inside the window

Window is `[onset, onset+duration)` on `t_device_ms`. Realised rules: `cuff_silent_bias` needs a `bp` sample in the window and a non-zero shift (`inject_c2.py:374-376`); `cuff_detached` needs a cuff `MEASUREMENT` event in the window (`:400-403, 447`); `stuck_at` needs a `bp` sample strictly before the onset in the **same day stream** (`:341, 347`) and a differing one in the window (`:354-355`).

No wrap: the planner draws onsets only from `(T_DAY - duration)//step + 1` positions (`builder.py:1236-1237`); the injector would refuse a window leaving the day (`injection.py:986-990`), never clips. Long windows therefore start between 00:00 and 12:00 (721 onsets).

| Duration | onsets | P(n=0) = not realised (detached, bias) | P(n=1) | P(n=2) | P(n=3) | mean n | mean n given n>=1 | stuck_at realised |
|---|---|---|---|---|---|---|---|---|
| short 1 h | 1381 | 0.7828 | 0.2172 | 0 | 0 | 0.2172 | 1.00 | 0.1738 |
| medium 4 h | 1201 | 0.3131 | 0.4996 | 0.1873 | 0 | 0.8743 | 1.27 | 0.4871 |
| long 12 h | 721 | 0 | 0 | 0.5215 | 0.4785 | 2.4785 | 2.48 | 0.4785 |

Maximum n is 3. A 1 h window can never hold two readings (spacing at least 2 h). `stuck_at` loses every onset before 06:15:30 (376 of 721 long onsets).

z = m x sqrt(n), convention only (z >= 2 is not a requirement):

| m | n=1 | n=2 | n=3 | n=4 | n=5 | n for z>=2 |
|---|---|---|---|---|---|---|
| 0.5 (4 mmHg) | 0.50 | 0.71 | 0.87 | 1.00 | 1.12 | 16 |
| 1.0 (8 mmHg) | 1.00 | 1.41 | 1.73 | 2.00 | 2.24 | 4 |
| 2.5 (20 mmHg) | 2.50 | 3.54 | 4.33 | 5.00 | 5.59 | 1 |

`cuff_silent_bias`, per combination (P(z>=2) unconditional; given realised it is 1 for high, 0 otherwise):

| Duration x magnitude | mean n | P(realised) | P(z>=2) |
|---|---|---|---|
| short x low / medium / high | 0.2172 | 0.2172 | 0 / 0 / 0.2172 |
| medium x low / medium / high | 0.8743 | 0.6869 | 0 / 0 / 0.6869 |
| long x low / medium / high | 2.4785 | 1.0 | 0 / 0 / 1.0 |

`stuck_at` and `cuff_detached` use the duration table (detached realised: 0.217, 0.687, 1.0). z counts the cuff error only (SD 8); the prior's single-reading residual is 11.9 mmHg (`literature_hypertension.yaml:64`), which makes the multipliers 0.34, 0.67, 1.68 in that unit (my arithmetic).

## 2. How the injector places faults

Window faults are **not anchored** to a visit, tick or intake: uniform on the 60 s grid, independent of the schedule, at 60000 ms resolution.

```
builder.py:1232-1237  duration = round(level.value); step = self.config.latent_step_ms
                      positions = (T_DAY_MS - duration) // step + 1
                      onset = day * T_DAY_MS + step * int(rng.integers(0, positions))
```
The level is drawn first, uniformly (`_pick` `:1223`; `injections.yaml:240`). The C2 count per day is Poisson(`injection_rate_c2` 0.3) (`:1377-1378`); the subtype is uniform over the six `_C2_DRIVEN` (`:250-257, 1382`); the magnitude level is uniform (`:1441`) with a fair sign except `device_bias` (`:1456`). That is 0.05 injections per patient-day per subtype, **70 over 1400 scored patient-days** (200 x 7; the tail day is unscored). Only `nav_delay`, `manipulation_failure` (a tick, `:1457-1480`) and `dispenser_bounce` (a real dispense) are anchored. Same-subtype overlaps are skipped (`:1331-1340`).

Seed: `_plan_rng` = `stream(generation_seed, patient_index, day, StreamPurpose.INJECTION_PLAN, stable_index("plan", ...))` (`builder.py:1212-1221`); a pure function of the key (`rng.py` docstring), no global state. The injectors' own `INJECTION_C2` stream (`injection.py:902-925`) is not used for placement.

**Finding.** The silent-bias magnitude block has **four** levels (`low, medium, high, device_bias`). `device_bias` = 1.0 x `cuff_bias_mmhg` = 0.0 mmHg, so `shifted != s.value` is false and it is **never realised** (real injector: 0 of 3303 onsets). With uniform draws 25% of silent-bias injections are lost: realised share 0.476 overall, 0.635 on the three non-zero levels.

## 3. BLE dropout of the cuff

`ble_dropout` removes every cuff sample (`bp`, `inflation_ms`, `cuff_health`, `hr_pulse`) and every `source == cuff` event with `t_device_ms` in the window (`inject_c2.py:296-303`); loss, not delay; realised if anything is removed (`:309`).

Real monitor (`run_offline`, registry 0.2.1 loaded with `allow_fixture_only=True`, SCHED per tick plus day-end COUNT, no violation fault-free), all 4246 onsets:

| Window | P(reading lost) = P(SCHED violated) | P(HOLD violated) | P(RESP violated): robust / with stale reference |
|---|---|---|---|
| 2 min | 0.0069 | 0.0028 | 0.0028 / 0.0056 |
| 15 min | 0.0526 | 0.0210 | 0.0210 / 0.0421 |
| 1 h | 0.2172 | 0.0869 | 0.0869 / 0.1738 |

Every lost reading violates its own SCHED (no other reading lies within 30 min of a tick). Lost 06:15 or 20:15 reading: HOLD violated. Lost 08:15 or 22:15: RESP violated (robust). A lost pre-dose reading also violated RESP, but only because my hand-built values (135, 122, 128, 135, 122 mmHg) make the stale reference give a drop below `delta_resp` 7.5: value dependent (on day 0 without history the 07:00 case did not). A dispenser drop hiding a dispense violated only COUNT.

C2 BLE windows: 0.0104 x 24 = 0.2496 per device-day, **0.998 per patient-day over the four devices** (`builder.py:1348-1351`, `vocab.py:112`). Cuff: 349 windows over 1400 patient-days. With equal draws over 2 min, 15 min, 1 h (mean hit probability 0.0922): **0.023 per patient-day, about 32 windows** hit a reading. Dispenser windows hitting a dispense: about 13. ECG and oximeter windows are realised when a vitals sample falls inside; no template reads `hr_ecg` or `spo2`.

## 4. Does any rule use heart rate?

No template does (`configs/templates/hypertension.yaml:17-86` lists signals: RANGE `meas, bp`; SCHED `sched_tick, meas`; HOLD `dispense, meas, bp`; COUNT `dispense, dose_count, day_end`; RESP `dispense, meas, bp_drop`; SYS `meas, cuff_health, inflation_ms`; INT `dispense, presence, intake, auth`).

| Hit | Role |
|---|---|
| `monitor/core.py:138-139`, `forecasters.py:50-58`, `predictive.py:86-94` | accepted and forecastable, but predictive targets are only `meas` (SCHED) and `bp` (RESP); no verdict reads them |
| `attribution/extract.py:612-640`, `evidence.py:62-69`, `rule.py:139-142, 296-305` | **attribution evidence only**: `pulse_vs_ecg_hr_diff` and `ecg_sqi` feed rule step 3 (cross-device incoherence with both SQI denied gives C3). Thresholds `hr_coherence_tolerance`, `ecg_sqi_floor` exist only in the attribution fixture registry, not in `configs/registry/hypertension.yaml` |
| `baselines/b2_*.py`, `b4_conformal_only.py:145-146` | baseline features |
| `measurement.py:952-954`, `inject_c2.py:489` (`ecg_noise`, `TEMPLATES_AFFECTED` empty `:209`) | generated signal only |
| `inject_c3.py:281-296, 852-863` | forged C3 messages: naive forger draws the pulse in `hr_bounds_bpm`, informed copies the held ECG rate |

So `pulse_error_sd_bpm` (`measurement.py:954`) affects no VIOLATED verdict, only the evidence value and B2/B4 features. `injection_naive_pulse_lower/upper_bpm` (read at `builder.py:1077-1078`, used at `inject_c3.py:862-863`) matter only for the pulse of `injection_naive`.

## 5. What this means for the proposed grids (facts only)

- Short (1 h): at most 1 reading, 78.3% of windows hold none; medium (4 h) holds 0, 1, 2 readings in 31.3%, 50.0%, 18.7%; long (12 h) holds 2 or 3.
- Not realised for detached and silent bias: 78.3%, 31.3%, 0%. For `stuck_at`: 82.6%, 51.3%, 52.2%.
- z >= 2: low never (16 readings needed), medium never (4 needed, grid maximum 3, z = 1.73), high with a single reading.
- High (20 mmHg) equals `scale_range` (20) and 67% of the 30 mmHg band 110-140: a mid-band reading leaves it with either sign. For a uniformly placed in-band reading, 4 and 8 mmHg leave the band in 13% and 27% of cases (my arithmetic). 8 mmHg exceeds `delta_resp` 7.5; 4 does not.
- Expected realised positives at rate 0.3 (70 injected per subtype, before overlap skips): `cuff_detached` 44.4 (5.1 / 16.0 / 23.3 short / medium / long); `stuck_at` 26.6 (4.1 / 11.4 / 11.2); `cuff_silent_bias` 33.3 = 11.1 per non-zero level, per duration x magnitude cell 1.3 / 4.0 / 5.8. Only high reaches z >= 2: 11.1 in total. A test split of about a quarter of the patients divides these by about 4.
- BLE: a 1 h cuff drop costs a reading in 21.7% of cases, 2 min in 0.7%; about 32 of 349 cuff windows hit one.

Could not determine from code: the real inflation, jitter and dispense times; whether stale-reference RESP violations occur with the generator's latent pressures; HR thresholds of the attribution rule for the real registry.
