# Group 1: design options after the observability analysis (facts and numbers; the decision is gab's)

2026-10-10. Read-only on the repository (builder.py was being edited by another worker: line numbers are as read). Scripts and outputs: `/tmp/research/obs2/`. Registry 0.2.1 (`allow_fixture_only=True`), readings 06:15:30, 08:15:30, 14:15:30, 20:15:30, 22:15:30 (inflation 30 s assumed, no jitter), doses 07:00 and 21:00, 60 s grid, 7 scored days plus the unscored tail day. Durations 1/4/12 h are gab's grid (committed rows still `awaiting_human_value`).

## 1. Faults anchored to k consecutive readings

**Rule A (proposed, cleanest).** First covered reading i drawn uniformly among the 6-k feasible ones; onset = grid point uniform in (r[i-1], r[i]] (for i=1: [0, r[1]]); end = grid point uniform in (r[k-th covered], r[next]] (for the last reading: up to the day end, which `_check_spec_shape` accepts since only `onset+duration > day_end` is refused). Window `[onset, end)`, so the reading at `onset` is inside and the next one (`end <= r_next`) is outside. Onset and end are independent. (Drawing all (onset, end) pairs equally likely makes the first reading depend on gap sizes, k=1: 0.165/0.158/0.473/0.158/0.046.)

Exact (script `anchored.py`): all pairs checked, 0 windows with a count different from k, 0 past the day end (max end = 86 400 000).

| k | first-reading choices | onsets x ends per choice | duration min / mean / max (ms) | hours | P(realised): detached, bias |
|---|---|---|---|---|---|
| 1 | 5 | 376x120, 120x360, 360x360, 360x120, 120x105 | 60 000 / 14 406 000 / 43 140 000 | 0.02 / 4.00 / 11.98 | 1 |
| 2 | 4 | 376x360, 120x360, 360x120, 360x105 | 7 260 000 / 30 607 500 / 51 300 000 | 2.02 / 8.50 / 14.25 | 1 |
| 3 | 3 | 376x360, 120x120, 360x105 | 28 860 000 / 48 010 000 / 72 900 000 | 8.02 / 13.34 / 20.25 | 1 |

The 60 s minimum is one grid minute around a reading at :30 s (a margin rule would be a further choice). Real injectors, 360 corner and random pairs: `realised` as predicted, `n_attempts` = k, bias `n_changed` = k.

**Real monitor, `cuff_detached` window of k readings** (`run_offline`, plan SCHED per tick + day-end COUNT, no SYS instance exists in `make_plan`). Verdicts were identical for 10 (onset, end) pairs per (k, first), so they depend only on which readings are covered. Hand-built values 135,122,138,135,122 (in band). Violated instances SCHED/HOLD/RESP:

| k | first reading 1 / 2 / 3 / 4 / 5 (06:15 ... 22:15) | mean over first choices |
|---|---|---|
| 1 | 1/1/0, 1/0/1, 1/0/0, 1/1/0, 1/0/1 | 1 / 0.40 / 0.40 |
| 2 | (1,2) 2/1/1, (2,3) 2/0/1, (3,4) 2/1/1, (4,5) 2/1/1 | 2 / 0.75 / 1.00 |
| 3 | 3/1/1 for every choice | 3 / 1 / 1 |

SCHED = k always (every lost reading violates its own SCHED). HOLD is robust when a pre-dose reading (06:15, 20:15) is lost, RESP when a post-dose reading (08:15, 22:15) is lost. With values 135,122,128,135,122 the loss of 20:15 also violates RESP (stale reference 128, drop 6 < 7.5): value dependent. Today's uniform windows give mean SCHED violations 0.217 / 0.874 / 2.479 for 1/4/12 h (1.19 over the three levels).

**Code changes (minimal).**
1. `builder.py` `_window` (~1288-1299) draws level then `onset = day*T_DAY_MS + step*int(rng.integers(0, positions))`; `_c2_spec` calls it at ~1495 for all three subtypes. Add a sibling that takes the day's readings and returns `(onset, duration, level)`. The readings are `stream_.measurements[*].t_ms` (`ObservedStream.measurements`, `measurement.py` ~736-773); `plan_observation` already receives `stream_` (it passes it to `_c3_spec`, ~1450) but not to `_c2_spec` (~1446): one more argument. Day with fewer than k readings (C1 refusals remove ticks, `builder.py` ~1650): return None, counted as skipped.
2. `InjectionSpec` needs no change (`duration_ms` is an int in ms, `injection.py` ~357-365). `params` rejects unknown keys (`_check_spec_shape`, ~1010), and the cuff injectors register no `levels`, so the count goes in `level` ("k1".."k3"). Caution: `_c2_spec` overwrites the duration label with the magnitude label (~1521: `label = mag_level.level`), so for the bias the k would be lost unless the label becomes composite. The record already carries k (detached `details.n_attempts`, bias `n_changed`).
3. `injections.yaml`: rows `*_duration_short/medium/long` of the three subtypes (lines ~459-558, unit ms, awaiting) become rows in unit "readings" with value 1, 2, 3 (integer, 1 <= k <= readings per day, ordered); the `duration:` blocks (lines 83, 92, 128) get `key: n_readings, unit: readings`. The loader refuses it: `injection.py` ~1729 `duration.unit != "ms"` raises; relax for these subtypes (or add a separate block). Tests that fill the ms rows with fixture values need the new rows.
4. Every C2 draw sequence changes (new RNG consumption): all golden files of the plan move.
Caveat: the planner sees the base stream; the robot stage (`nav_delay`, `manipulation_failure`) runs first, so "exactly k" can become k-1 or k+1. A tick is hit by a `manipulation_failure` with probability (rate/6)/7 per day: 0.7% at rate 0.3, 4% at 1.7 (my arithmetic).

## 2. Bias magnitudes 1.0 / 1.5 / 2.5 x 8 mmHg

Cuff error is drawn independently per reading (`measurement.py` ~939, `z[0]`), device bias 0. z = m sqrt(k) uses SD 8 only; the last block uses the prior's residual 11.9 (`literature_hypertension.yaml:59/64`).

| m (mmHg) | z k=1/2/3 (SD 8) | min k for z>=2 | z k=1/2/3 (SD 11.9) | min k (11.9) | x delta_resp 7.5 | in units of 11.9 | in-band reading leaving 110-140 |
|---|---|---|---|---|---|---|---|
| 1.0 (8) | 1.00 / 1.41 / 1.73 | 4 (out of grid) | 0.67 / 0.95 / 1.16 | 9 | 1.07 | 0.67 | 26.7% |
| 1.5 (12) | 1.50 / 2.12 / 2.60 | 2 | 1.01 / 1.43 / 1.75 | 4 | 1.60 | 1.01 | 40.0% |
| 2.5 (20) | 2.50 / 3.54 / 4.33 | 1 | 1.68 / 2.38 / 2.91 | 2 | 2.67 | 1.68 | 66.7% |

Band share = min(1, m/30) for a uniform in-band reading (my assumption), same for either sign. The 20 mmHg bias is also the registry `scale_range` 20.

**Threshold detectability of the 3x3 cells** (real `B1StaticThresholds` and `B3PlainSTL` with the registry, plan of `make_plan`; first reading uniform, fair sign; script `mc_b1.py`, `mc_bias.py`). P(B1 alarm) with readings i.i.d. uniform in band, 1500 trials per cell (analytic 1-(1-p)^k in brackets):

| m \ k | 1 | 2 | 3 |
|---|---|---|---|
| 1.0 | 0.26 (0.27) | 0.45 (0.46) | 0.60 (0.61) |
| 1.5 | 0.40 (0.40) | 0.66 (0.64) | 0.79 (0.78) |
| 2.5 | 0.69 (0.67) | 0.89 (0.89) | 0.97 (0.96) |

So no cell is detected by band rules with certainty; the share missed by B1 ranges 73% (m=1, k=1) to 3.5% (m=2.5, k=3). B3 adds RANGE-equivalent, HOLD and RESP. RESP sees only readings 1, 2, 4, 5 (07:00 and 21:00 doses); the 14:15 reading is visible to RANGE only. A constant bias on both the pre- and the post-dose reading of one dose cancels in the drop: real monitor, pre 135/post 125, bias +-8 on both readings: no RESP violation; on the pre reading alone (-8): RESP violated. The B3 gain over B1 therefore depends on the unknown fault-free drop d (not determined; no builder run). MC with a pre/post structure (pre uniform in [110+d,140], post = pre-d, 300 trials per cell; this concentrates readings at the band edges, so its B1 values exceed the i.i.d. ones):

| d | cell (m;k) B1 -> B3: (1;1) | (1.5;1) | (2.5;1) | (1;2) | (1.5;2) | (2.5;2) | (1;3) | (1.5;3) | (2.5;3) |
|---|---|---|---|---|---|---|---|---|---|
| 10 | .23->.61 | .32->.68 | .76->.94 | .41->.59 | .62->.76 | .95->1 | .60->.76 | .77->.85 | 1->1 |
| 20 | .37->.37 | .48->.48 | .53->.94 | .66->.66 | .85->.85 | .92->1 | .86->.86 | 1->1 | 1->1 |

With d=20 (drop 12.5 above delta_resp) the 8 and 12 mmHg biases never reach RESP. Which cells only STL/conformal evidence (B5) could add cannot be said: B5 was not run.

## 3. Sample size for about 100 realised positives per subtype in the test split

Facts: C2 injections per patient-day Poisson(rate), subtype uniform over 6 (`_C2_DRIVEN` ~250-257), so Poisson(rate/6) per subtype and day. Test = 0.25 of the patients (`default.yaml`), 7 scored days. Mean test positives = 0.25 n x 7 x (rate/6) x share. Variance = mean (Poisson thinning; overlap skips lower it slightly; test patient count varies by seed, 48-52 of 200); p5 of Poisson(100) = 84; p5 >= 100 needs a mean of 117.

Realised share per drawn injection from simulation of the planner's placement and overlap logic (re-implemented in `sim.py`, 10^6 days per cell; validated against the real injectors on 2537 random multi-fault days, 1 mismatch = an equal value of my hand-built day). Device order detached, bias, stuck is included, so detached windows shadow later cuff faults. Placement uniform "now" has `device_bias` excluded. Anchored = k uniform in {1,2,3}.

| rate | uniform now: det / bias / stuck | anchored: det / bias / stuck (no carry-over) | anchored, stuck with carry-over | planned share (not skipped), uniform / anchored |
|---|---|---|---|---|
| 0.3 | .628 / .619 / .373 | .983 / .970 / .711 | .933 | .988 / .983 |
| 0.6 | .616 / .609 / .359 | .966 / .942 / .681 | .904 | .975 / .966 |
| 1.0 | .606 / .587 / .343 | .943 / .905 / .648 | .868 | .960 / .943 |
| 1.7 | .586 / .555 / .323 | .905 / .846 / .595 | .810 | .934 / .905 |

Overlap loss (same-subtype skip, `add_window` ~1394): 1.2/2.5/4.0/6.6% (uniform) and 1.7/3.4/5.7/9.5% (anchored) at rates 0.3/0.6/1.0/1.7. Faulty days: P(at least one class-rate C2) = 1-e^-rate = 0.26 / 0.45 / 0.63 / 0.82; P(at least one of the 3 cuff subtypes) = 0.14 / 0.26 / 0.39 / 0.57. BLE windows come on top (about 0.998 per patient-day over four devices at the prior rate, previous analysis).

Expected test positives, anchored with carry-over (det / bias / stuck; the same row reads patient-days of test = 7 x 0.25 n: 350, 700, 1400, 2100):

| rate \ n_patients | 200 | 400 | 800 | 1200 |
|---|---|---|---|---|
| 0.3 | 17/17/16 | 34/34/33 | 69/68/65 | 103/102/98 |
| 0.6 | 34/33/32 | 68/66/63 | 135/132/127 | 203/198/190 |
| 1.0 | 55/53/51 | 110/106/101 | 220/211/203 | 330/317/304 |
| 1.7 | 90/84/80 | 180/168/161 | 359/336/321 | 539/504/482 |

Rate for a mean of 100 (p5 >= 100 in brackets), worst subtype:

| n_patients | uniform now (stuck) | anchored, stuck without carry | anchored, stuck with carry |
|---|---|---|---|
| 200 | 5.3 (6.0) | 2.88 (3.37) | 2.12 (2.48) |
| 400 | 2.65 (3.1) | 1.39 (1.68) | 0.99 (1.18) |
| 800 | 1.28 (1.53) | 0.63 (0.75) | 0.47 (0.55) |
| 1200 | 0.82 (0.97) | 0.41 (0.48) | 0.31 (0.36) |

At the current rate 0.3, patients for a mean of 100: 1819 / 1847 / 3066 (uniform) versus 1163 / 1179 / 1226 (anchored with carry-over). Cost, linear in patients from the recorded fixture (126 s, 2.2 GB for 200 patients, which in `T11-benchmark-builder.md:159` also includes 76 pair patients, so an upper bound per main patient): 400 -> 252 s, 4.4 GB; 800 -> 504 s, 8.8 GB; 1200 -> 756 s, 13.2 GB. The fixture vitals period is 60 s (the real row sets the size); the rate effect on size was not measured.

## 4. `stuck_at`: day concatenation and carry-over

(a) Yes, the injector sees only the current day. `build_observed_base` builds each day from that day's latent (`LatentSbpHold(latent.samples)`, `measurement.py` ~895) with fresh per-measurement noise; only the latent AR state carries (`state = latent.end_state`, `builder.py` ~1763). `stuck_at` scans `work.samples` (`inject_c2.py` 336-345); `ObservedDay` is serialised per day (`trace.py:6`, `days/<patient>/<day>.json`).

(b) A window starting before the first reading: `frozen` stays None (`inject_c2.py` 347-348), `details["reason"] = "no earlier reading to freeze"`, `n=0`, so `realised=False` (pinned by `test_stuck_at_without_an_earlier_reading_is_not_realised`). Detached and bias run first, so a reading they removed is no longer an "earlier reading".

(c) The context already has the field: `InjectionContext.previous_day` (`injection.py` ~540), set by the builder to the previous day's post-injection stream (`previous = stream_`, `builder.py` ~1774; passed at ~1666), validated by `check_previous_day` (`injection.py` ~1248, same patient, seed, `day_index-1`); only the replay uses it today. Minimal change: in `stuck_at`, when `frozen is None`, take the last `bp` sample of `check_previous_day(work, context)` (about 8 lines in `inject_c2.py` plus tests; the `previous_day=None` case stays unrealised). No builder change. It is causal and realistic: a stuck cuff repeats its last reported value, which at 06:15 is the previous 22:15 reading, and monitors see no future data. Caveats: the previous stream is post-link (a reading lost to BLE or detachment is skipped for an earlier one); a consumer that reads one day alone (B1, ADR-061) cannot see the frozen value's origin.

(d) Exact realised share of `stuck_at` for a single window (no overlap), day 0 without previous day, days 1-6 with:

| placement | no carry-over | carry-over (days 1-6) | carry-over, 7-day weighted |
|---|---|---|---|
| uniform short 1 h | 0.174 | 0.217 | 0.211 |
| uniform medium 4 h | 0.487 | 0.687 | 0.658 |
| uniform long 12 h | 0.479 | 1.000 | 0.926 |
| uniform, mean of the three | 0.380 | 0.635 | 0.598 |
| anchored k=1 (5 choices) | 0.800 | 1 | 0.971 |
| anchored k=2 (4 choices) | 0.750 | 1 | 0.964 |
| anchored k=3 (3 choices) | 0.667 | 1 | 0.952 |

Day 0 loses the choice "first reading" (1/(6-k) of the draws): for the first scored day there is no previous evening. Options: leave it unrealised (loss 1/(7(6-k)) = 2.9 / 3.6 / 4.8%), or restrict the planner to first reading >= 2 on day 0 (share 1 before shadowing, simulated realised .959 / .92 / .873 / .798 at rates 0.3..1.7, against .933 / .904 / .868 / .810 with carry-over alone). The tail day is unscored: its injections are never positives, it has a previous day, and a window never leaves its day; it only absorbs 1/8 of the generated injections.

## What could not be determined
The fault-free pre/post-dose drop of the real generator (decides how much B3 adds to B1); B5 detectability; the real inflation, jitter and duration values; effect of the robot stage on anchored counts beyond the arithmetic above; build time and size as a function of the rate.
