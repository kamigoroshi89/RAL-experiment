# Non-additivity of injections: reproduction, root cause, required property, fix

2026-10-11. Read-only on the repository. Code is a `git archive HEAD` copy (0feb140) in `/tmp/research/nonadd/repo`. Fixture-only prior (all patients share the same PK: ke 0.0815/h, ka 2.3/h, Emax 17.3) and the sensitivity-only placeholder grid of `/tmp/research/obs4` (durations 1/4/12 h, magnitudes x0.5/1/2); no value is a proposal. Scripts and logs: `/tmp/research/nonadd/` (`scripts/`, `exp*.log`, `test_single_injection_additivity.py`).

## 0. Result in four lines

1. **No random-number leak was found between a build with and without an injection.** In 18 subtypes x 8 patient-days (single forced injection through `PatientInjections`) the AR/circadian baseline, the adherence log of the other slots, the measurement noise, the jitter and the whole C1 truth are bit-identical outside the causal footprint.
2. **The non-additivity of event counts is causal and semantic**, not a stream problem: an injection changes the latent pressure or the dose set, so the labeller finds different natural events; and an injected label absorbs a natural event on the same reading.
3. **Two real couplings exist, both outside the RNG**: (a) `_c2_spec` robot-tick pick depends on `robot_used` (builder.py:1530-1534): the same draw picks another tick in 983 of 2000 trials when one tick is already used; (b) a forced `double_take` overwrites the natural outcome of its dose slot (latent_day.py:427).
4. **The test of gab passes today** for all 18 subtypes once the footprint is defined correctly (section 3). It should still be added, plus a randomised property test.

## 1. Reproduction (single forced injection, `build_patient(scripted=...)`)

Config `runs/b7` (7 scored days + tail), patients 0-3, injection on day 1 or 2, onset anchored on a reading or dose tick. "Spurious" = a difference outside the causal footprint after masking `seq`.

| Subtype | Latent trace differs | Observed differs | Truth differs | Spurious |
|---|---|---|---|---|
| hypertensive_spike, hypotension_below_hold | only inside the pulse window (120 samples for 2 h at 1 min); AR state and next days identical | the reading(s) in the window | injected event; a natural RANGE/RESP event on a window reading is relabelled or appears/vanishes | 0 |
| drug_nonresponse | from the first affected intake on, forever (analytic Bateman tail): max 9.3 mmHg day 0, 2.5 (d1), 0.32 (d2), 4.5e-2 (d3), 6e-3 (d4), 9e-4 (d5), 1.3e-4 (d6), 1.8e-5 (d7) | cuff values after it | natural RESP event relabelled `drug_nonresponse`, extra RANGE events later | 0 |
| double_take | extra dispense + intake; PK tail (max 3.0 mmHg d0, 1e-5 d7) | extra DISPENSE, later dispenser seq renumbered | COUNT events (also next day, rolling 24 h), RESP changes, a natural `dose_omission` can vanish | 0 |
| measurement_refusal | one MEASUREMENT event | cuff message of the tick missing; later cuff seq renumbered; a BLE window holding it can become unrealised | RANGE event on that reading replaced by a `sched` event | 0 |
| C2 (cuff_*, ecg_noise, ble_dropout, dispenser_bounce, manipulation_failure, nav_delay, stuck_at), C3 (replay, naive, informed, forgery, spoof) | identical (samples, events, baseline, behaviour log) | only inside the window/tick footprint (replay: by `t_rx`, old `t_device`) + later seq renumbering | exactly one new event, no C1 event changes | 0 |

nav_delay: the moved reading keeps its noise draw (error 11.675392 / -2.606263 ... identical to 6 decimals at 15 min delay); `z` is keyed by tick index k (measurement.py:938), jitter by `2*index+kind` (measurement.py:538).

**Event-count budget** (C1 only, scripted singles vs all together; 60 patients, 420 patient-days, rate 1.0): per template, joint result = new injected + emerged natural - vanished natural (absorbed = natural relabelled, net 0).

| Template | without | with | new injected | absorbed | emerged natural | vanished natural |
|---|---|---|---|---|---|---|
| range | 1074 | 1049 | 22 | 40 | 39 | 86 |
| resp | 477 | 542 | 5 | 18 | 77 | 17 |
| hold | 31 | 77 | 19 | 0 | 31 | 4 |
| count | 101 | 285 | 194 | 10 | 1 | 11 |

By cause (sum of single builds): hypotension: RANGE +31/-23 natural; refusal: HOLD +27 natural (missing pre-dose reading), RANGE -44; double_take: RESP +60 natural (97 double takes), RANGE -24; spike: 40 natural RANGE absorbed; non-response: 18 natural RESP absorbed, only 2 new. Sum of singles vs joint differ by 0-7 events per cell (interaction). Same sign as the earlier note at the full scale (5000 patients x 7 days, rate 0.3, C1 only, my rerun): natural RANGE -2321 (injected spike 2172), HOLD +659 (hypotension 578), RESP +734 (non-response 618), COUNT -251. Totals nearly conserve for RANGE (89450+2172 against 91771: -149). I could not recover how -1217/+821/+1358 against 124/124/108 were defined, so the figures are not reproduced, only their signs and mechanism.

## 2. Root cause of every difference

| Level | Finding (file:line) |
|---|---|
| (i) same day | None spurious. AR: `LATENT_AR` per (patient, day), 1440 normals (latent_day.py:621, latent.py:296); injections are added after it (`hypertensive_spike`/`hypotension_below_hold` pulses and the drug effect in `_assemble`, latent_day.py:~640-670). Baseline sidecar equal in 320/320 patient-days (random path, 40 patients). Adherence: `ADHERENCE` per (patient, day), `rng.random(2*n_slots)` fixed length (adherence.py:482). Noise per tick k, jitter per index, injection streams keyed by `stable_index(cls, subtype, target, onset, duration)` (injection.py:902-922). |
| (ii) later days | AR state: natural only (`pressure.ar_state_mmhg`). Adherence chain: `result.final_state` stays natural when a slot is forced (latent_day.py:430). Carried and causal: PK intake history (tail, above); device seq counters (`counters = _next_counters(stream_)`, builder.py:1775); `previous = stream_` (builder.py:1774) is the post-injection stream, so a C3 attack on day d changes what replay/informed see on d+1. |
| (iii) other patients | None: patient 3 rebuilt after patients 7, 9, 1 and in a fresh context is bit-identical; no global stream (`PATIENT`/`SPLIT` depend on counts only); segment cache only affects speed. |
| (iv) labelling | `label_latent_day_detailed` (labelling.py:1394) is deterministic, reads latent + C1 records + behaviour log + history. C2/C3: truth unchanged in 104 scripted cases and in 240 random-rate patient-days (rates 0.6/0.6 against 0). C1: changes with the latent (causal). |
| Real coupling A | builder.py:1530 `ticks = [kt for kt in ticks if kt not in robot_used]`, :1533 `self._pick(rng, ticks)`, :1534 `robot_used.add`. Slot j's tick depends on which slots k<j exist. Demo `scripts/demo_draws.py` (b): same seed, one tick used -> different tick in 983/2000. Harmless for nested rates, wrong for "delete slot k". |
| Real coupling B | latent_day.py:420-430: a forced slot replaces the natural slot log (`log[dose_index] = sub.behaviour_log[0]`): natural DELAYED becomes on-time double take (seen: p2 day 3 dispense 336108316 vanished, 334800000/334920000 appear), natural OMITTED loses its `dose_omission` event (exp2: 7 vanished; exp4: removed `dose_omission` in 2 of 4 patients). Design choice, not a draw. |
| Coupling C (planning, not draws) | overlap skips: builder.py:1393-1403 (`add_window`), plan_c1 `taken`/`seen_points` (builder.py:1306-1341). A slot is accepted given accepted slots k'<k. |
| Nesting (good) | Poisson count is nested in the rate (0 violations in 100 000 seeds, 0.3 vs 1.0), every slot has its own stream: `plan_c1` at rate 0.3 is a subset of rate 1.0 for 300 patients (684 of 684 specs). |

## 3. Required property and test

For one patient-day built without and with exactly one injection S (same context, `PatientInjections`, S inside the same day):

| Predicate | Statement | Equality |
|---|---|---|
| P1 | baseline sidecar (AR + circadian) identical, every day; behaviour log identical (except double_take slot) | exact |
| P2 | C2/C3: latent samples and events identical. C1 pulse: latent differs only in [onset, onset+dur). C1 PK (non-response, double_take): identical before the first affected intake; afterwards no equality claim (analytic tail, section 1) | exact outside region |
| P3 | C2/C3: no truth event disappears, none of class C1 appears, exactly one new event | exact |
| P4 | observed samples/events, `seq` masked, identical outside the footprint, tested on `t_rx_ms` (replay keeps its old `t_device`). Footprint: window +/- 5 min; per-tick faults [tick, tick + delay + 2 h]; refusal/PK: from the event on | exact |
| P5 | `seq` of later cuff/dispenser messages: only a constant shift (count of added/removed messages); strictly increasing | exact |
| P6 | per reading, error = observed - latent hold identical (noise keyed by tick), including nav_delay | tolerance 1e-9 (float round-off of the subtraction) |

C1 consequences to document in the test: BLE-window realisation can flip for a window that contains a removed reading (p0091: cuff window realised True -> False, NODE_STATE at 19.5 h vanishes although the refusal is at 20.25 h); COUNT events appear up to 24 h later.

Runnable script: `/tmp/research/nonadd/test_single_injection_additivity.py [config] [subtype]`. Result on `runs/b7` (4 patients x days 1, 2): all 18 subtypes PASS (cuff_detached, cuff_silent_bias, stuck_at, ecg_noise, manipulation_failure, nav_delay, ble_dropout, dispenser_bounce, replay, naive, informed, forgery, spoof, spike, hypotension, non-response, refusal, double_take). The first run failed `replay` (24 samples) only because the footprint used `t_device`; this is the test's bug, not the builder's. Weaknesses of the script: footprint is generous (2 h after a tick); 8 cases per subtype; fixture-only patients are PK-identical. Random-path check (`scripts/exp7.py`): rates C2/C3 0.6 against 0, 30 patients, 240 days: latent, baseline, behaviour, C1 truth identical; 7698 observed differences, all in a footprint.

## 4. Proposed fix

The per-component stream layout already exists; "separate streams per component" is not what is missing. Current keys, all derived from `(seed, patient, day, purpose, sub_index)`: PATIENT, LATENT_AR (day), ADHERENCE (day), CONFOUNDER (day, dose), MEASUREMENT (tick k), JITTER (2*index+kind), SEGMENTS, INJECTION_PLAN (`stable_index("plan", class, k|"count"|device)`), INJECTION_C1/C2/C3 (spec identity).

| # | Change | Where | Effect |
|---|---|---|---|
| F1 | Robot tick: pick from the full tick list (7), skip on collision with `skipped["c2/<sub>/same_tick"]` (as C1 does with `seen_points`) | builder.py:1521-1534 | The first robot slot of a day is unchanged; the second moves. P(>= 2 robot slots/day) is about 0.5% at rate 0.3 (my arithmetic), so few goldens move once, then stable |
| F2 | Counterfactual by list edit, not re-planning: `build_patient(..., drop=frozenset(spec_ids))` applied after planning, ids from `injection_sub_index` | builder.py:1731-1783 | Removing a slot never revives a skipped one or moves a tick; no draw changes |
| F3 | Decision for gab (ADR): keep the double take as an intervention that overwrites the slot, or make it additive (natural dose kept, second dispense added; omitted slot stays omitted) | latent_day.py:420-430 | Additive makes the double_take trace differ from the base only by the extra dose; goldens of double_take and confounder pairs move once. Not decided here |
| F4 | Keep `seq` renumbering (a missing cuff message is a real counter gap); test compares modulo shift | builder.py:1755, 1775 | none |
| F5 | Tests: end-to-end P1-P6 on every subtype (the script); property test over seeds 0-99, random patient, day, subtype, onset; rate nesting test (plan at r subset of plan at r' > r); builder-level event budget test (Delta total = injected + emerged - vanished, absorbed separately) | `tests/benchmark/` (existing unit versions: test_c1_confounders.py:2106, test_inject_c3.py:2034, test_latent.py:221) | Closes the end-to-end gap |

Do not key a reading by its instant: tick index k is already the key, so nav_delay keeps its draw (checked). The labelling table of section 1 should be reported next to the benchmark size: "positives" are labelled events, not injections.

**Effort**: F1 0.5 pd, F2 0.75 pd, F5 1.5 pd (script to pytest, property test, budget test), ADR + docs 0.25 pd: about 3 pd; +0.5 to 1 pd if F3 changes semantics (golden and pair tests).

## 5. Not determined

Exact reproduction of -1217/+821/+1358; real-prior behaviour (fixture-only prior has identical patients); whether C3 attacks on day d propagate to d+1 outside the footprint (P4 would flag it; only tested with one injection or rate 0.6 and found nothing); the precise labeller mechanism of RESP emergence after a double take (traced only by counts); rates other than 0.3/0.6/1.0; wall time of the proposed test.
