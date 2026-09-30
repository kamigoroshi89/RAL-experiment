---
id: WS05-T02
title: "Signals and derived signals; RTAMT spike (ADR-013)"
workstream: WS05-monitor
owner: agent
status: ready
depends_on: ["WS05-T01", "WS01-T01", "WS01-T02"]
critical_path: true
non_negotiable: false
estimate_pd: 2
sources: ["analisi §4.1", "analisi §3.1", "analisi §9 (5)"]
interfaces: ["02-interfaces.md#signals", "02-interfaces.md#time-and-units"]
review_items: ["R1-W10"]
---
## Obiettivo

Implement `ralmon.signals` for real (`SignalId`, `Sample`, `Event`, `EventKind`, `minutes`, `hours`, `hold_last`, the streaming derived signals `dose_count`, `meas_count`, `bp_pre`, `bp_drop`, and the helpers `event_to_sample`, `impulses_on_grid`, `default_derived_signals`, `ObservedTrace`), with fixtures taken from the worked examples of WS01-T01. Then run the RTAMT spike and update ADR-013 with a decision: RTAMT wrapped behind the monitor, or a custom evaluator with RTAMT kept as an oracle. The spike closes R1-W10 (no tool, no complexity statement) on the tool side.

## Contesto

Blocked until WS05-T01 is `done`. Two undeclared preconditions, reported to the plan lead: the signals part needs the output of WS01-T01 and the spike needs the output of WS01-T02. If one is missing, do the parts that do not need it, keep `status: in_progress`, and say so in the completion note.

- `docs/formal/01-signals-sampling.md` (signal table, grid and ceiling rule, day boundary, derived signals, worked examples W1 to W7 in fixture registry F0 with `step_ms = 60000`).
- `02-interfaces.md#signals` (contract; the rules of the time contract are quoted where used).
- `docs/formal/02-templates.md` (the seven past-time formulas in the syntax fixed by WS01-T02; its golden cases feed the spike).
- `docs/plan/03-decisions.md` (ADR-013 RTAMT reference tool, to be updated here; ADR-017 integer milliseconds).
- `docs/source/analisi.md` §3.1 (tool list: RTAMT, Breach, S-TaLiRo).

## File toccati

- `src/ralmon/signals/` (modify: real modules `ids.py`, `samples.py`, `derived.py`, functions in `units.py`; placeholders removed from `_stubs.py`, import lines updated)
- `tests/signals/` (create: `test_units.py` extended, `test_samples.py`, `test_hold_last.py`, `test_derived.py`, `test_event_mapping.py`; fixtures as literals in the files, each with a locator to its WS01-T01 example)
- `tools/rtamt_spike.py` (create: the spike script, plain Python, no network)
- `docs/plan/workstreams/WS05-monitor/rtamt-spike.md` (create: the spike record)
- `docs/plan/03-decisions.md` (modify: update ADR-013 with the decision, the tested RTAMT version and a pointer to the record; keep the confirmation tag)
- `pyproject.toml` (modify: optional extra `rtamt`, only if ADR-013 keeps RTAMT for the monitor, for the oracle or for baseline B3)

## Test

Pytest tests (write first; each fails before the implementation). Time values are `hh:mm` labels converted with `t_ms = (60*hh + mm) * 60000` (WS01 convention). Numbers are fixture-only or taken from WS01-T01; none is a clinical value.

1. `test_minutes_hours_helpers`: `minutes(5) == 300_000`, `minutes(0.5) == 30_000`, `hours(1.5) == 5_400_000`, `hours(9) + minutes(5) == 32_700_000`; the results are `int`.
2. `test_signal_id_values_match_contract`: the 17 members and their string values are exactly those of `#signals`, in that order.
3. `test_event_kind_values_match_contract`: the eight members and values of `#trace-schema`.
4. `test_sample_and_event_are_frozen_and_slotted`: assigning a field raises `dataclasses.FrozenInstanceError`; instances have no `__dict__`; field names and order equal the contract.
5. `test_observed_trace_accepts_structural_day`: a local frozen dataclass with `patient_id`, `day_index`, `seed`, `samples`, `events`, `care_plan_id` is an instance of the runtime-checkable Protocol `ObservedTrace`; an object without `care_plan_id` is not.
6. `test_hold_last_w1`: `bp` samples 138.0 at 06:52 (24_720_000) and 152.0 at 09:05 (32_700_000); grid at 06:51, 06:52, 09:04, 09:05 gives `[nan, 138.0, 138.0, 152.0]` (WS01-T01 W1; value at a sample time is visible, right-continuous).
7. `test_hold_last_no_samples_gives_nan_not_zero`: an empty sample list gives all `nan` (a signal that exists only while the robot is co-located, such as `presence`, is unavailable, never 0.0; contract rule of `#signals`).
8. `test_hold_last_uses_device_time`: a sample with `t_device_ms=100`, `t_rx_ms=500` is visible on a grid point at 200 (the reorder delay is applied by the monitor, not here).
9. `test_hold_last_rejects_unsorted_samples_or_non_increasing_grid`: `ValueError` for either.
10. `test_hold_last_is_causal_property` (Hypothesis): the value at grid point `t` is unchanged when samples with `t_device_ms > t` are appended, removed or altered.
11. `test_impulses_on_grid_w2_ceiling_rule`: a `meas` sample at 06:52:20 (24_740_000) gives 1.0 only at the step 06:53 (24_780_000); a sample at exactly 06:52:00 gives 1.0 only at 06:52 (WS01-T01 W2; an impulse is visible at the first grid step `>= t`).
12. `test_impulses_on_grid_w3_multiplicity`: the two `dispense` events of WS01-T01 W3 give the impulse grid stated there (expected values copied from the document with the locator), and `dose_count` still increases by 2 because counters read the event stream, not the grid.
13. `test_dose_count_w6_trailing_24h_half_open`: dispenses at 25_200_000 (day 1 07:00), 75_600_000 (21:00), 75_720_000 (21:02), 111_600_000 (day 2 07:00) give `dose_count` 1, 2, 3, 3; the last is 3 because the window `(t - 24h, t]` excludes the day-1 07:00 dose (WS01-T01 W6; G-COUNT-1 shows the value 3 at 21:02).
14. `test_dose_count_expires_on_any_forwarded_sample`: after the last dispense above, a forwarded `day_end` sample at 198_000_000 makes `update` return a `dose_count` sample with value 0.0 (the derived signal advances its clock on every sample it is given, including signals not in its `inputs`).
15. `test_dose_count_matches_naive_recount_property` (Hypothesis): for random sorted dispense times, the streaming value after each dispense equals `sum(1 for d in times_so_far if t - 24h < d <= t)`.
16. `test_meas_count_counts_measurements_in_the_day`: five `meas` impulses give 1, 2, 3, 4, 5; the day boundary rule is the one of WS01-T01 section 5 (the test names the rule it implements).
17. `test_bp_pre_latches_last_measurement_before_dose_and_bp_drop`: `bp` 150.0 at 06:45, `dispense` at 07:00 gives `bp_pre` 150.0; `bp` 132.0 at 08:30 gives `bp_drop` 18.0 (G-RESP-1: `150 - 132`).
18. `test_bp_pre_unavailable_before_first_dispense`: `update` returns `None` for `bp_pre` and `bp_drop` before any dispense (channel unavailable, never 0.0).
19. `test_default_derived_signals_outputs_and_inputs`: the four instances have outputs `DOSE_COUNT`, `MEAS_COUNT`, `BP_PRE`, `BP_DROP`; every `inputs` entry is a `SignalId`; feeding the same stream twice into fresh instances gives identical outputs (no hidden state).
20. `test_event_to_sample_mapping_table`: `MEASUREMENT` maps to `meas`, `DISPENSE` to `dispense`, `INTAKE` to `intake`, `SCHEDULE_TICK` to `sched_tick`, each with value 1.0, `quality=None`, both times and `seq` copied; `MEASUREMENT_MISSED`, `NODE_STATE`, `ROBOT_TASK` and `DEVICE_ERROR` map to `None` (evidence only, they are not signals).

Spike verification checks (numbered; a reviewer can run or inspect each):

1. `python tools/rtamt_spike.py` runs offline, prints the installed RTAMT version read from package metadata (or `NOT-INSTALLED`), then one line per question Q1 to Q6 with `PASS`, `FAIL`, `NOT-SUPPORTED` or `NOT-RUN` and a one-line reason; exit code 0 whenever the report was produced.
2. Q1 (past-time operators): each of the seven templates of WS01-T02 (`range`, `sched`, `hold`, `count`, `resp`, `sys`, `int`) has a row stating whether its `formula_past_time` translates mechanically into RTAMT with bounded `once`, `historically` and implication, and whether the result equals the `sigma_raw` of its golden cases within `1e-9` (or is exactly infinite where the golden case says so).
3. Q2 (sparse sampling): the record states how the fixed-step discrete-time interface of the installed RTAMT version is fed from the grid built by `hold_last` and `impulses_on_grid`, and whether irregular timestamps are needed or the monitor grid of `#time-and-units` rule 1 suffices.
4. Q3 (robustness intervals): the record states whether the installed RTAMT can return `[sigma_lo, sigma_hi]` for a prefix whose unknown future is replaced by physiological bounds, or only a point value. If only points, it states the procedure that would obtain sound intervals from point evaluations (evaluation at the two bounds is sound only for formulas monotone in the unknown signal), says for each of the seven templates whether it is monotone in each unknown signal (with a counterexample for any template that is not), and concludes whether the interval layer is custom code.
5. Q4 (guards and infinities): the record states whether RTAMT represents the guard rule of WS01-T02 (a failed guard gives minus infinity, normalised -1) and infinite margins.
6. Q5 (time robustness): the record states whether the time-margin templates (`sched`, `int`, `sys` when their unit is `ms`) are expressible, or are obtained by the margin and guard rule on derived signals.
7. Q6 (cost per sample): the script measures the number of operator updates per grid step for one formula with 1, 10 and 100 instances, from the tool if it exposes it, else from a counting wrapper; it reports the growth (linear or not). It uses no wall-clock time.
8. `docs/plan/workstreams/WS05-monitor/rtamt-spike.md` has H2 headings `## Environment`, `## Q1 Past-time operators`, `## Q2 Sparse sampling`, `## Q3 Robustness intervals`, `## Q4 Guards and infinities`, `## Q5 Time robustness`, `## Q6 Cost per sample`, `## Decision`, `## Consequences for WS05-T03, WS05-T04, WS06-T04`.
9. `## Decision` selects exactly one outcome and states the rule: (A) RTAMT is the point-robustness engine behind `ralmon.monitor`, the interval layer is custom; (B) the evaluator is custom, RTAMT stays an oracle in tests and the engine of baseline B3 (analisi §5.4: same templates with RTAMT); (C) RTAMT cannot host the templates, the evaluator is custom, B3 uses the custom point evaluator and the paper says so. Outcome C is forced by any Q1 failure on a template; outcome A requires Q1, Q2 and Q4 to pass.
10. ADR-013 in `docs/plan/03-decisions.md` has a line starting `Spike result` that names the outcome (`outcome A`, `outcome B` or `outcome C`), the RTAMT version, the entry point that WS06-T04 must call for raw robustness (`make_point_evaluator` of `ralmon.monitor`, created by WS05-T04), and keeps `[DA-CONFERMARE]` until a human confirms.
11. If RTAMT could not be installed (no network or no wheel), the record says `NOT-RUN` for Q1 to Q6, ADR-013 says "spike inconclusive, custom evaluator adopted, RTAMT to be revisited", and the completion note names the missing capability; the task is then `done` only for the signals part and the plan lead is told.

## Passi

1. Verify preconditions (Contesto). Branch `ws05-t02-signals-rtamt-spike`; `status: in_progress`. Check whether WS04-T01 already created `src/ralmon/signals/trace_types.py` (its step 1 does so when `Sample` and `Event` are missing): if yes, import and re-export those definitions, never redefine them, and note it; if no, define `SignalId`, `Sample`, `Event`, `EventKind` in `ids.py` and `samples.py` verbatim from the contract.
2. Write the tests of the Test section with fixtures copied from WS01-T01 W1, W2, W3, W6 and F0 (locators in comments). Run `pytest tests/signals -q`; watch every test fail for the right reason. Commit `WS05-T02: add failing signals tests`.
3. Implement `units.py` (`minutes`, `hours` with `round(x * unit)` to integer milliseconds), `ids.py`, `samples.py` (dataclasses `frozen=True, slots=True`; `ObservedTrace` Protocol with read-only properties so that `ObservedDay` satisfies it; `event_to_sample`; `impulses_on_grid` following the ceiling rule of WS01-T01 section 3), and `derived.py`: `hold_last` (grid strictly increasing, samples sorted by `t_device_ms`, value at a grid point includes samples with `t_device_ms <= t`, `nan` before the first sample as recommended by WS01-T01 for CP12), and the four `DerivedSignal` implementations. `DoseCount` keeps a deque of dispense times and evicts entries `<= t - 24h` on every `update`, whatever the signal of the sample, so each dispense enters and leaves once (amortised O(1) per sample; state this in the docstring and in the completion note; the contract says O(1)). `BpPre` latches the held `bp` value at each `dispense` and keeps it until the next one; the per-instance capture for overlapping doses belongs to the monitor (WS05-T04). `MeasCount` follows the day-boundary rule of WS01-T01 section 5. `default_derived_signals()` returns fresh instances.
4. Refactor; run `pytest tests/signals -q`, `ruff check src tests`, `mypy src/ralmon`. Remove the migrated names from `signals/_stubs.py` and update `signals/__init__.py`. Commit `WS05-T02: implement signals and derived signals`.
5. Spike, part 1. Install RTAMT in the development environment (network needed; if unavailable go to check 11). Read the installed version's documentation and package source for the questions Q1 to Q6; do not rely on memory of its API. Write `tools/rtamt_spike.py` with one function per question, fed by the golden cases of `docs/formal/golden/templates.yaml` and the grid helpers of `ralmon.signals`; each function returns a result and a one-line reason.
6. Spike, part 2. Run the script; write `rtamt-spike.md` with the nine headings of check 8, evidence per question (the formula tried, the input, the output), the monotonicity table of check 4 and the decision rule of check 9. Choose the outcome by that rule.
7. Update ADR-013 (check 10). If RTAMT is used (outcomes A or B), add the optional extra `rtamt` to `pyproject.toml`; do not pin a version. Run `python tools/check_plan.py`.
8. Run every command of "Done when"; commit `WS05-T02: RTAMT spike and ADR-013 decision`; set `status: done` and `status: ready` in the task files whose `depends_on` are now all `done`.

## Done when

From the repository root, inside `.venv`:

- `pytest tests/signals -q` exits 0.
- `ruff check src tests` and `ruff format --check src tests` exit 0; `mypy src/ralmon` exits 0.
- `python -c "from ralmon.signals import SignalId, Sample, Event, EventKind, DerivedSignal, hold_last, minutes, hours, default_derived_signals, event_to_sample, impulses_on_grid, ObservedTrace"` exits 0 and none of these names has `__ralmon_stub_owner__`.
- `python tools/rtamt_spike.py` exits 0 and prints six question lines.
- `test -f docs/plan/workstreams/WS05-monitor/rtamt-spike.md` and `grep -c '^## ' docs/plan/workstreams/WS05-monitor/rtamt-spike.md` prints at least 9.
- `grep -n "ADR-013" docs/plan/03-decisions.md` shows an updated entry containing the words `Spike result` and one of `outcome A`, `outcome B`, `outcome C`.
- `! grep -nE 'T[O]DO|T[B]D|[?][?][?]|lore[m]' docs/plan/workstreams/WS05-monitor/rtamt-spike.md` succeeds.
