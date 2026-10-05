---
id: WS04-T05
title: Adherence Markov model with DISPENSE and INTAKE events
workstream: WS04-benchmark
owner: agent
status: done
depends_on: ["WS04-T02"]
critical_path: true
non_negotiable: false
estimate_pd: 2
sources: ["analisi §5.1", "analisi §4.9 (5)", "analisi §5.1 (adherence as declared assumption)"]
interfaces: ["02-interfaces.md#trace-schema", "02-interfaces.md#priorsource"]
review_items: []
---
## Obiettivo

Generate the patient's dosing behaviour: a Markov model over per-dose outcomes (on time, delayed, omitted, double take) declared as an assumption because no public smart-dispenser dataset is known (analisi §5.1), producing true DISPENSE events (dispenser opened) and true INTAKE events (pill taken) as **distinct** event kinds (ADR-004, analisi §4.9 item 5). Also create the care-plan schedule object (dose ticks and measurement ticks) with a derivation rule from the registry windows (`hold_lookback`, `delta1`, `delta2`, `sched_window`) and a consistency checker that reuses the WS01-T02 plan feasibility checks, so that a null latent day cannot violate φ_CP by generator construction. Concrete output: `src/ralmon/benchmark/adherence.py`, `schedule.py`, `configs/benchmark/care_plans.yaml`, tests.

## Contesto

- `02-interfaces.md#priorsource` (`AdherenceParams`: `p_delay`, `p_omission`, `p_double_take`, `mean_delay_ms`) and `02-interfaces.md#trace-schema` (`EventKind.DISPENSE`, `EventKind.INTAKE`, `Event`).
- `docs/source/analisi.md` §5.1 (adherence: "Markov con probabilità di ritardo, omissione e doppio prelievo, dichiarandolo come assunzione"), §4.9 item 5 and §4.5 matrix rows 6 and 7 (double take versus dispenser bounce).
- `docs/plan/03-decisions.md` ADR-004 and ADR-020; the WS04-T03 output (`rng.py` streams).
- `docs/formal/02-templates.md` (WS01-T02, section on plan feasibility checks: a measurement tick in `[a - hold_lookback, a)` and in `[a + delta1, a + delta2]` for each dispense tick `a`) and the registry working names `hold_lookback`, `delta1`, `delta2`, `sched_window` (WS01-T03); `docs/models/evidence-channels.md` (WS02-T03, if it exists: gap G-1 on dispenser content sensing; here only the truth side is generated, the device view is built in T06).

Unblocked when WS04-T02 is `done`.

## File toccati

- `src/ralmon/benchmark/adherence.py` (create).
- `src/ralmon/benchmark/schedule.py` (create).
- `configs/benchmark/care_plans.yaml` (create: dose times of day and measurement count, `source_type: illustrative_unverified`, `source_ref` naming analisi §4.6 and §4.3).
- `configs/benchmark/generator_design.yaml` (modify: rows `intake_lag_ms`, `double_take_gap_ms`).
- `tests/benchmark/test_adherence.py` (create).

## Test

Fixture-only arithmetic values, written first. State order is fixed: `ON_TIME`, `DELAYED`, `OMITTED`, `DOUBLE_TAKE`.

1. `test_default_transition_rows_equal_marginals`: with `p_delay = 0.2`, `p_omission = 0.1`, `p_double_take = 0.1` every row of the transition matrix is `[0.6, 0.2, 0.1, 0.1]` (memoryless special case of the Markov chain).
2. `test_marginals_above_one_rejected`: `0.5 + 0.4 + 0.3 > 1` raises `AdherenceConfigError`.
3. `test_custom_transition_matrix_validated`: rows must be nonnegative and sum to 1 within tolerance, shape 4 by 4; otherwise `AdherenceConfigError`; a Hypothesis property over random stochastic matrices checks that the simulated state sequence only visits states with positive transition probability.
4. `test_perfect_adherence_when_all_probabilities_zero`: every slot is `ON_TIME`; the number of DISPENSE events equals the number of slots; each is at its tick.
5. `test_omission_probability_one_yields_no_events`: no DISPENSE and no INTAKE at all.
6. `test_double_take_second_dispense_after_gap`: `p_double_take = 1`, gap 120 000 ms, intake lag 5 000 ms: DISPENSE at `tick` and `tick + 120 000`, INTAKE at `tick + 5 000` and `tick + 125 000`.
7. `test_delay_within_slot_bounds`: every delayed dispense lies in `[tick, next_tick - 1]` (the last slot of a day is bounded by the day end).
8. `test_truncated_exponential_delay_mean`: mean 1 h truncated at 3 h has analytic mean `1 - 3 exp(-3) / (1 - exp(-3)) = 0.842813 h`; 50 000 draws (seed 0) lie within four standard errors of it.
9. `test_empirical_state_frequencies_match_marginals`: 20 000 slots, seed 0, each state frequency within `4 * sqrt(p (1 - p) / n)` of its marginal.
10. `test_absorbing_omission_row_is_markov`: a matrix whose `OMITTED` row is absorbing produces, once the first omission occurs, only omissions afterwards.
11. `test_chain_state_carries_across_days`: a 7-day run equals seven 1-day runs that carry the chain state; the chain does not reset at midnight.
12. `test_dispense_and_intake_are_distinct_kinds`: latent events contain both kinds; each INTAKE follows its DISPENSE by the lag; the model has no dispensed-but-not-taken case, so the counts are equal (declared simplification).
13. `test_latent_events_sorted_and_times_equal`: sorted by `t_device_ms`, `t_rx_ms == t_device_ms`, `seq is None`, sources `dispenser` for DISPENSE and `patient` for INTAKE.
14. `test_behaviour_log_matches_events`: one entry per slot with `slot_tick_ms`, `day_index`, `state`, `dispense_times_ms`; the sum of dispense times equals the DISPENSE events.
15. `test_adherence_stream_independent_of_other_streams`: consuming the measurement and injection streams first does not change the events.
16. `test_double_take_gap_must_fit_between_slots`: a gap not shorter than the slot spacing raises `AdherenceConfigError`.
17. `test_schedule_derivation_hand_case`: doses at 08:00 and 20:00, `hold_lookback` 1 h, `delta1` 1 h, `delta2` 3 h, `sched_window` 30 min, five measurements (fixture values equal to the shared fixture registry F0 of WS01). Each pre-dose tick is the midpoint of `[a - hold_lookback, a - sched_window)`, i.e. `a - 45 min`; each post-dose tick is the midpoint of `[a + delta1, a + delta2 - sched_window]`, i.e. `a + 105 min`; the remaining tick is the midpoint of the largest gap between ticks (earliest gap on ties). Ticks: 07:15, 09:45, 14:30, 19:15, 21:45.
18. `test_schedule_consistency_flags_infeasible_window`: the ticks of test 17 pass both the WS01 feasibility checks and the slack requirement (a tick plus `sched_window` still inside its window, so that a robot arriving as late as the window allows cannot break `hold` or `resp` in a fault-free day); with `sched_window` equal to `hold_lookback` (1 h) no pre-dose tick can exist, `derive_schedule` raises `ScheduleInfeasibleError` naming the dose and `check_schedule_consistency` returns the same problem for a hand-written schedule.
19. `test_design_rows_have_provenance`: every parameter read from `generator_design.yaml` and `care_plans.yaml` by these modules has `source_type` and `source_ref`.

## Passi

1. Write `tests/benchmark/test_adherence.py`; run it, confirm failure; commit `WS04-T05: add failing adherence tests`.
2. Implement `schedule.py`: frozen `Schedule` (dose ticks and measurement ticks in ms since day start), `load_schedule(path)`, `derive_schedule(dose_times_ms, n_measurements, hold_lookback_ms, delta1_ms, delta2_ms, sched_window_ms)` and `check_schedule_consistency(...)` (the WS01-T02 plan feasibility checks plus the slack requirement of test 18). All windows are arguments; the builder (T11) passes the registry values, so this module never imports `ralmon.spec`.
3. Implement `adherence.py`: `AdherenceConfig` (intake lag and double-take gap read from `generator_design.yaml`), `AdherenceModel` with `transition_matrix` defaulting to identical rows from the marginals, delay by inverse-CDF sampling of the exponential truncated at the time to the next tick (the family is a declared assumption written in the provenance note), `simulate(schedule, n_days, rng) -> AdherenceResult(events, behaviour_log)`. Use the named stream `StreamPurpose.ADHERENCE`.
4. Fill the YAML rows: `care_plans.yaml` holds the illustrative schedule (two doses per day at 07:00 and 21:00 from analisi §4.6, five measurements per day from analisi §4.3), every row `source_type: illustrative_unverified`; `generator_design.yaml` gains `intake_lag_ms` and `double_take_gap_ms` as `design_choice` rows with `awaiting_human_value` unless a human supplied a value, the only qualitative constraint being analisi §4.5 rows 6 and 7 (a double take is clearly separated from a sub-second sensor bounce). Regenerate the provenance table.
5. Note in the completion note that persistence of omissions (clusters) needs an extra parameter that `AdherenceParams` does not carry; the class accepts the matrix so a later contract version supplies it without changing the generator.
6. Refactor, run `ruff check src tests`, `mypy src/ralmon`, `pytest tests/benchmark -q`; commit `WS04-T05: add adherence Markov model, schedule and derivation rule`; set `status: done`.

## Done when

- `pytest tests/benchmark/test_adherence.py -q` exits 0 (and the earlier benchmark tests still pass: `pytest tests/benchmark -q`).
- `ruff check src tests` exits 0 and `mypy src/ralmon` exits 0.
- `python -m ralmon.benchmark.priors --check-table` exits 0 and `grep -c 'double_take_gap_ms' docs/benchmark/parameter-provenance.md` prints at least 1.

## Notes

### Hand-over from the WS04-T02 review (orchestrator, 2026-10-05)

Adherence parameters are declared assumptions (`analisi §5.1`); `AdherenceParams.mean_delay_ms` is stored as an int, the onset range is one row `{lower_ms, upper_ms}` accepted as a constant only (ADR-038 G-list); the loader of `configs/benchmark/*.yaml` (`load_design_file`) reads only a top-level `parameters:` list of rows with numeric values: nested structures or strings in `care_plans.yaml` are ignored or refused, so the provenance table would not list them.

### Completion note (worker, WS04-T05; status left `in_progress` for the orchestrator)

Done when, run on the host: `pytest tests/benchmark/test_adherence.py -q` exit 0 (140 passed); `pytest tests/benchmark -q` exit 0; `ruff check src tests` exit 0; `mypy src/ralmon` exit 0; `python -m ralmon.benchmark.priors --check-table` exit 0; `grep -c 'double_take_gap_ms' docs/benchmark/parameter-provenance.md` prints 2. Full suite 797 passed on the host and in the container (`docker compose run --rm test`, then `lint`). Filled-state proof: a `git archive HEAD` copy with the three awaiting rows of `generator_design.yaml` filled with fixture-only values, table regenerated there, whole suite 797 passed (copy deleted).

What the module produces. `adherence.py` produces the TRUE events of the latent day: a DISPENSE (source `dispenser`) per dispenser opening and, `intake_lag_ms` after each, a true INTAKE (source `patient`). It does not decide what the monitor sees: the observed trace holds an INTAKE only if the robot witnessed it, a mapping that belongs to WS04-T06. Declared simplification: no dispensed-but-not-taken case (counts of DISPENSE and INTAKE are equal).

Modelling choices (all declared; none is a clinical value):
- Slot of a dose = from its tick to the next dose tick, or to the day end for the last dose (events of a slot start inside its own day). A delayed dose is `tick + d`, `1 <= d <= L - 1` (at least 1 ms late so that DELAYED differs from ON_TIME; never leaves the slot); `d - 1` is the floor of an exponential of mean `mean_delay_ms` truncated at `L - 1`, by inverse CDF. The family is a declared assumption. An INTAKE may fall after the end of its day (only for a delayed dose); it keeps its place on the continuing axis.
- Initial state: drawn from `initial_distribution`, default the marginals (the stationary law of the default chain). For a custom matrix the caller chooses it. The chain is carried across days (`final_state` returned, `state` accepted back); exactly two uniforms per slot are consumed whatever the outcome, so a run of n days equals shorter runs on one generator with the state carried (tested).
- `double_take_gap_ms` must be shorter than every slot of the schedule (always checked, also when `p_double_take = 0`), `intake_lag_ms >= 0`, and `intake_lag_ms < double_take_gap_ms`. A dose in the last millisecond of the day has a 1 ms slot and cannot hold any gap (refused).
- Tie rule: events sorted by `(t_device_ms, kind rank, slot order)`, DISPENSE before INTAKE at equal times (zero lag; an INTAKE meeting the next slot's DISPENSE); tested.
- Schedule: `derive_schedule` places the pre-dose and post-dose ticks at the midpoints (floor) of the windows, the others in the largest gaps between ticks (earliest on ties); a tick must lie in its own day (`TICK_OUTSIDE_DAY` otherwise), coinciding ticks are refused, extra ticks need at least one dose (`NO_ANCHOR`), `n_measurements >= 2 * doses`. `check_schedule_consistency` runs F2, F3 and the slack requirement only; F1 (grid alignment), F4 (robot visits), F5 (counts), F6 (registry names) need data this module does not have. `load_schedule(path, *, hold_lookback_ms, delta1_ms, delta2_ms, sched_window_ms)` takes the windows as keyword arguments (the builder passes the registry values) and reads only dose times and the measurement count from the file.
- `care_plans.yaml` holds two rows (`dose_times_clock_ms` as a list of integer ms, `n_measurements_per_day`) with `source_type: illustrative_unverified`; the measurement ticks themselves are derived, not stored (the design loader reads numbers and lists of numbers only). `generator_design.yaml` gains `intake_lag_ms` and `double_take_gap_ms` as `design_choice` rows with `awaiting_human_value`: no value was chosen by an agent. Until a human fills them `load_adherence_config` raises `UnfilledParameterError`, so no benchmark can be built from the committed design file (the expected state, ADR-020).

Persistence of omissions (clusters of missed doses) needs an extra parameter that `AdherenceParams` does not carry (ADR-038, gap G7). `AdherenceModel` accepts `transition_matrix` (and `initial_distribution`), so a later contract version supplies the persistence without changing the generator. With the contract's parameters the transition rows are identical (memoryless), as the WS04 README states.

Contract gaps and deviations from the task text:
- `simulate` has two keyword arguments beyond the task signature (`start_day`, `state`) and `AdherenceResult` a third field (`final_state`), needed by test 11 (a 7-day run equals seven 1-day runs that carry the chain state). `adherence_stream(seed, patient_index)` is the named patient-level stream (`StreamPurpose.ADHERENCE`).
- `load_schedule` takes the four windows (the task lists `load_schedule(path)` only; the windows must come from the registry, which this module must not import).
- `load_filled_rows` in `schedule.py` is a small public helper (not exported from the package root) reused by `adherence.py`.
- No contract signature changed; no ADR was added. Names of these modules are not in the `#package-public-api` table and are not exported from `ralmon.benchmark`.

### Fix round 1 (worker, after the independent review; status unchanged)

Review result: no blocker; the model, the schedule rule, the statistics and the state independence were verified and are kept. Fixed here: four code or test defects, with tests written first.

- **M1, raw `OverflowError`.** `_real` (`adherence.py`) now turns the `float()` failure of an integer or fraction beyond the float range (for example `10**400`, `2**1024`) into `AdherenceConfigError` naming the field; huge values are shown cut short in messages. `sample_delay_ms` converts the mean and the slot length through `_real` (an integer of 2**1024 or more was another raw `OverflowError`); `AdherenceModel` also checks that `mean_delay_ms` is a float-representable integer at construction. `AdherenceModel(None, cfg)` (any non-`AdherenceParams`) raises `AdherenceConfigError` instead of `AttributeError`. Checked and defined, no change needed: infinities and NaN (refused), 1e308 and subnormal products in `truncated_exponential` (finite result in `[0, upper]`, clamped), huge `n_days`, `start_day`, lag and gap (refused by the slot, int64 and gap checks), huge schedule integers (refused by `ScheduleError`). `schedule.py` messages cut a huge integer too.
- **M2, unbounded `n_measurements`.** `MAX_MEASUREMENTS = 100_000` (`# algorithmic`) in `schedule.py`; `derive_schedule` raises `ScheduleError` `TOO_MANY_MEASUREMENTS` for a larger count and `NO_POSITIONS` for a count above the `T_day` distinct integer-ms positions of a day, both before any placement. The extras placement is now a heap keyed by (-width, left end): same rule (widest gap, earliest on ties), O(n log n). Oracle: the existing tests plus a seeded comparison with an O(n^2) reference implementation on 400 random plans (coarse and millisecond windows, both outcomes including `NO_ROOM`).
- **M3, wrong text.** Corrected: an INTAKE may fall after the end of its slot's day for a delayed dose and also for the second DISPENSE of a double take (reproduction: last slot 10 min, gap 8 min, lag 5 min, the second INTAKE lands 3 min past midnight); a DISPENSE never leaves its slot. Correction of the completion note above: its sentence "An INTAKE may fall after the end of its day (only for a delayed dose)" is false; read "(for a delayed dose or for the second dispense of a double take)". The module docstring is corrected and a test pins the double-take crossing (the entry keeps the day of its dose).
- **M4, test gaps** (each mutant now fails a test, checked on a copy under /tmp, removed afterwards): A08b (delay uniform = state uniform), A22 (the clamp: `truncated_exponential(100, 5, TOP) == 5.0`, so `sample_delay_ms(100, 6, TOP) == 5`; plus a Hypothesis edge test), S01b (odd post window rounds down), S11 (a tick exactly at 24:00 is `TICK_OUTSIDE_DAY`), S21 (`delta2 < delta1` has its own message; equal windows accepted).

Notes only (not changed):
1. T09 expects a hook that T05 does not have: `simulate(..., state=...)` carries the chain state, it does not force the state of one slot (T09 test `test_forced_double_take_matches_markov_double_take`, "adherence (T05, with optional forced slot states)"). A forcing hook can be added later without moving the draws: two uniforms are consumed per slot whatever the state.
2. `load_schedule` requires integers while the registry gives floats (`RegistryEntry.value: float`, for example `3600000.0` raises `ScheduleError: hold_lookback_ms must be an integer`): the caller (WS04-T11) must convert with `int()`.
3. A dose in the last milliseconds of the day is refused when its slot is shorter than the gap, even if `p_double_take = 0` (the gap is always checked).

### Post-task review (orchestrator, 2026-10-05)

Produced: adherence Markov model with true DISPENSE and INTAKE events, derived measurement schedule, two illustrative care-plan rows, two new awaiting design rows (`intake_lag_ms`, `double_take_gap_ms`). Independent review: PASS, no blocker; one fix round applied (raw OverflowError, unbounded `n_measurements`, wrong midnight text, test gaps). Orchestrator verification on the final branch: `test_adherence.py` 207 passed (90 MB peak), full suite 864 passed, ruff, format, mypy, `--check-table` and `check_plan` all exit 0; the filled-state proof passes.
Deviations: `simulate` carries two extra keywords and `AdherenceResult.final_state`; `load_schedule` takes the four windows as keywords; no contract or ADR change.
Impact on dependents: WS04-T06 stays blocked on WS04-T04. WS04-T09 expects a forced-slot-state hook that does not exist (note 1 above); WS04-T11 must pass `int()` windows (note 2); the double take may cross midnight (its entry keeps its slot's day). `intake_lag_ms` and `double_take_gap_ms` await human values (ADR-020): no benchmark can be built from the committed design file until then.
Open MINOR: none beyond the notes above.
