---
id: WS04-T15
title: "Multi-day ground-truth labelling with history (ADR-046, ADR-055 (b))"
workstream: WS04-benchmark
owner: agent
status: ready
depends_on: ["WS04-T10", "WS05-T10"]
critical_path: true
non_negotiable: false
estimate_pd: 1.5
sources: ["ADR-046", "ADR-055 (b)", "analisi §5.1 (ground truth)"]
interfaces: ["02-interfaces.md#trace-schema", "02-interfaces.md#monitor"]
review_items: []
---
## Obiettivo

Close ADR-055 (b): the labeller of WS04-T10 labels a day with the earlier days of the patient as history, so that the truth no longer loses the violations that depend on the previous day (the 24 h counter after an evening double take, and the response windows that end after midnight). The per-day truth was a strict subset of the full-history truth (the review of T10 measured a loss of 7 to 12% of the natural events). Event ownership: an event belongs to the day in which the monitor decides it; its onset may lie in the previous day.

## Contesto

Blocked until WS04-T10 and WS05-T10 are `done`.

- `src/ralmon/benchmark/labelling.py`, `docs/benchmark/ground-truth.md` and the review notes in `docs/plan/workstreams/WS04-benchmark/tasks/T10-latent-ground-truth.md` (the hand-overs, the measured loss, the day-end COUNT guard of fix B1).
- `docs/plan/03-decisions.md` ADR-046 (status: event ownership and the open `Detector` point) and ADR-055.
- `tests/benchmark/reference_phi_cp.py` (the independent evaluator; it needs the same history to stay independent).

## File toccati

- `src/ralmon/benchmark/labelling.py` (modify: `history` of previous latent days, injection records and behaviour entries; the ideal observation of each history day; the day bounds apply to the decision, not to the onset)
- `tests/benchmark/test_ground_truth.py` and `tests/benchmark/reference_phi_cp.py` (modify)
- `tests/fixtures/benchmark/latent_days_phi_cp.yaml` (modify: cases that start on day 1 with a history day)
- `docs/benchmark/ground-truth.md` (modify: the convention on ownership; the residual-circularity section)
- `docs/plan/03-decisions.md` (modify: ADR-055 status line (b) only)

## Test

Write first. Fixture-only; the real monitor with `history`.

1. `test_a_day_with_history_equals_the_full_run`: for a seeded two-day patient, the truth of day 2 with history equals the events decided in day 2 of one run over both days (the reference evaluator extended to two days).
2. `test_evening_double_take_gives_the_morning_count_event`: day 1 double take at 21:00 and 21:02, day 2 dose 07:00: the COUNT-limit event is in the truth of day 2, linked to the day-1 `double_take` record (`injected` true) or, for a natural double take, labelled `double_take`.
3. `test_response_window_across_midnight_is_labelled_where_it_is_decided`: a dose at 22:00 on day 1 with no response is an event of day 2 (onset 22:00 on day 1, end 01:00).
4. `test_day_without_history_is_unchanged`: day 0 and a day given an empty history give exactly the present output (the 286 tests of T10 stay green).
5. `test_patient_level_plan_with_history`: the B1 guard still holds (the day-end COUNT of another day is skipped) with a history.
6. `test_the_per_day_truth_is_a_subset_of_the_history_truth`: on 40 seeded days, every per-day event is in the history truth.
7. `test_hostile_history_raises_only_named_errors`.

## Passi

1. Tests first, then the `history` argument of `label_latent_day`, `label_latent_day_detailed` and `assemble_benchmark_day`.
2. Extend the reference evaluator with the same history, without importing `ralmon`.
3. Update `ground-truth.md`, close ADR-055 (b) in its status line, and tell WS04-T11 (Notes) the signature.

## Done when

- `pytest tests/benchmark/test_ground_truth.py -q` and `pytest tests/benchmark -q` exit 0.
- `ruff check src tests`, `ruff format --check src tests` and `mypy src/ralmon` exit 0.
- `grep -cE '^## (Definition|Onset and end conventions|Injection records versus truth|Modes|Non-circularity tests|Residual circularity)$' docs/benchmark/ground-truth.md` prints `6`.
- `python3 tools/check_plan.py` exits 0.

## Notes

### Real signature of the monitor history input (worker of WS05-T10, 2026-10-10)

`run_offline(day, plan, config, calibrator, forecaster, *, registry=None, templates=None, verifier=None, history=())` and `run_offline_detailed(...)` with the same arguments (`history: Sequence[ObservedDay] = ()`, typed in code as `Sequence[ObservedTrace]`). Pass the days that precede the day to label, on the continuing axis, in increasing `day_index` order, the same `patient_id`; at most `ralmon.monitor.offline.MAX_HISTORY_DAYS` (14) days before `day`, one day is enough with the registry of today. Records of steps before the first step of `day` are not returned; the day-end COUNT that closes the previous day at that first step is not returned either (its own day's run decides it). Every other record at the first step of `day` is returned, including those of instances anchored in an earlier day: the closing step of a day is also the first step of the next, so an instance that is decided exactly at that step appears in both runs, and the two records can DISAGREE (review of WS05-T10: a RESP deadline exactly at `T_DAY` is VIOLATED in the run of day 0, whose slice ends before an input stamped `T_DAY`, and SATISFIED in the run of day 1, which sees that input; `decided_at_ms` is the same in both). Neither a key on `(instance_key, t_eval_ms)` nor `decided_at_ms` alone picks one: the rule to adopt here, and to state in the ADR of the ownership across midnight, is that the run whose first step is the decision step owns the record, so the record at the closing step of day d-1 is dropped from the labelling of day d-1 when it is also the first step of day d. With an empty `history` the run is unchanged, including the day-end COUNT record of the previous day at the first step of a day that follows another (the labeller's guard on the day-end COUNT of another day stays needed for the no-history call).
