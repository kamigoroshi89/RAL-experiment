---
id: WS05-T10
title: "Monitor history input: run_offline replays the earlier days of the patient (ADR-046)"
workstream: WS05-monitor
owner: agent
status: ready
depends_on: ["WS05-T04"]
critical_path: true
non_negotiable: false
estimate_pd: 2
sources: ["ADR-046", "ADR-053 (h)", "docs/formal/01 section 5.5 and worked case W6", "docs/formal/05 sections 7.5 and 11"]
interfaces: ["02-interfaces.md#monitor", "02-interfaces.md#time-and-units", "02-interfaces.md#trace-schema"]
review_items: []
---
## Obiettivo

Implement the keyword-only `history: Sequence[ObservedDay] = ()` of `run_offline` and `run_offline_detailed`, as `02-interfaces.md#monitor` 0.2.0 states it. The earlier days of the same patient are replayed first on the continuing axis, the verdicts of the steps before the first step of `day` are not returned, and the state that crosses midnight (the trailing 24 h dose counter, the held pressure and the measurement look-back, the instances whose window ends after the closing step) carries into the day. With an empty `history` the behaviour is exactly the present one. `estimate_pd` is a rough planning figure, not a measurement.

## Contesto

gab adopted ADR-046 on 2026-10-09 and applied it with ADR-053 (`#monitor` 0.2.0, `#time-and-units` 0.1.1, `#trace-schema` 0.1.1). The days of a patient are on one continuing axis (`day_index * T_day + clock time`), so a replayed day keeps its own times and no time is negative. The monitor already runs the day `day_index` from the step `day_index * K` (`_start_at`, ADR-053 (h)); this task starts the run at the first step of the first history day and suppresses the output before `day_index * K`.

- `docs/formal/01-signals-sampling.md` section 5.5 (carry-over, truncation fallback, worked case W6: the counter at day-2 07:00 is 3 with history and 1 without) and `docs/formal/05-three-valued-semantics.md` sections 7.5 and 11 (instances open at the closing step; hypothesis H-hist of ADR-029).
- `src/ralmon/monitor/offline.py` (`run_offline`, `run_offline_detailed`, `_run`) and `core.py` (`StreamingMonitor`).
- `docs/plan/workstreams/WS05-monitor/tasks/T04-monitor-core.md` (what the run does today, the review rounds).
- Out of scope: the `Detector` contract has no history input yet; WS06-T01 proposes it by a separate ADR (see ADR-046, status).

## File toccati

- `src/ralmon/monitor/offline.py` (modify: `history` in both entry points, validation, the replay and the suppression)
- `src/ralmon/monitor/core.py` (modify only if the suppression needs a seam, for example an `emit_from` step)
- `tests/monitor/test_history.py` (create)
- `tests/fixtures/monitor/` (modify: a two-day fixture for W6; hand-computed)
- `docs/formal/01-signals-sampling.md` (modify: one sentence saying that the truncation fallback is now an option, not the only behaviour)

## Test

Write first; each fails before the implementation. Fixture-only (registry F0, `step_ms = 60000`), no clock, no network.

1. `test_no_history_is_the_present_behaviour`: every golden case of `tests/monitor` gives the same records with `history=()` and without the argument.
2. `test_w6_counter_across_midnight`: day 1 has the doses 21:00 and 21:02, day 2 the dose 07:00. With the day-1 history the limit instance of the 07:00 dose is VIOLATED (count 3, window `(t - T_day, t]`, the 21:00 dose of day 1 is inside, the 07:00 of day 1 would be excluded); without it SATISFIED (count 1).
3. `test_no_record_before_the_day_is_returned`: with a two-day history no record has `t_eval_ms < day_index * K * step`.
4. `test_resp_window_across_midnight_is_decided_in_the_next_day`: a dose at 22:00 on day 1 with no reading afterwards: day 1 alone leaves it PENDING (not a violation); the run of day 2 with history returns the VIOLATED record at the step 01:00 with the anchor on day 1.
5. `test_held_pressure_and_lookback_cross_midnight`: a reading at 23:50 on day 1 is the pre-dose value and the HOLD look-back evidence of a dose at 00:30 on day 2; without history the guard fails.
6. `test_the_day_end_count_of_the_previous_day_is_decided_once`: its VIOLATED record comes from the run of its own day, not again from the next day's run.
7. `test_history_is_validated`: another patient, a day index not smaller than `day.day_index`, indices not increasing, a history longer than the named bound, a non-`ObservedDay` item: each raises `MonitorInputError` and nothing else.
8. `test_history_days_are_on_the_continuing_axis`: a history day written on the per-day axis (times of day 0 with `day_index = 1`) is reported as rejected inputs, as a day is today.
9. `test_detailed_run_agrees`: `run_offline_detailed(..., history=h).records == run_offline(..., history=h)`.
10. `test_contract_signature`: `inspect.signature(run_offline)` equals the `#monitor` 0.2.0 text (names, order, keyword-only, defaults).
11. `test_hostile_history_raises_only_named_errors`: junk in every position of `history` (the pattern of `tests/monitor/test_field_fuzz.py`).

## Passi

1. Write the tests above; run them and read the failures.
2. Add the parameter, validate it (named bound, `# algorithmic: <reason>` comment like the other bounds), start the run at the first history step, suppress the output before `day_index * K`.
3. Keep `plan_instances_before_start` meaningful: instances anchored in a history day are now part of the run, not skipped.
4. Update the docstrings of `offline.py` and `__init__.py` (no "history is not implemented" text).
5. Run the checks of "Done when", set `status: done`, unblock WS04-T15, and write one line in the Notes of WS04-T15 and WS04-T11 with the real signature.

## Done when

- `pytest tests/monitor/test_history.py -q` exits 0 and `pytest -q` exits 0.
- `ruff check src tests`, `ruff format --check src tests` and `mypy src/ralmon` exit 0.
- `pytest tests/test_public_api.py -q` exits 0 and `python3 tools/check_plan.py` exits 0.
