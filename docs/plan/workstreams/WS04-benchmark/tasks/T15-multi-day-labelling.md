---
id: WS04-T15
title: "Multi-day ground-truth labelling with history (ADR-046, ADR-055 (b))"
workstream: WS04-benchmark
owner: agent
status: in_progress
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

### Decision on the shared midnight step (gab, 2026-10-10; ADR-064)

The rule is decided and this task implements it. (a) The truth of an event is the verdict of a run that has all the data stamped up to and including the instant of decision. (b) A record decided at the shared step (the closing step of day d-1, which is the first step of day d) belongs to day d (half-open days): the labelling of day d-1 discards its records at its closing step; the labelling of day d with history keeps those decided at its first step, whatever the anchor day. (c) Exception: the day-end COUNT that closes day d-1 stays with day d-1. (d) No tolerance parameter. Add to the Test section, written first:

8. `test_the_shared_midnight_step_belongs_to_the_day_that_starts_there`: a dose at 21:00 with the RESP window closing exactly at 24:00 and a response measurement stamped 24:00. The labelling of day 0 returns no event for the instance; the labelling of day 1 with the history of day 0 returns no violation either (SATISFIED). The same day with the measurement stamped 24:00:01 or later is a violation, and it is an event of day 1.
9. `test_a_record_decided_at_the_closing_step_is_discarded_from_the_closing_day`: for a violated instance that the full run decides at the shared step, the event is in the truth of day 1 and not in that of day 0.
10. `test_the_day_end_count_stays_with_the_day_it_closes`: the missing doses of day 0 are an event of day 0, not of day 1 (as WS05-T10 returns it).
11. `test_the_truth_does_not_depend_on_where_the_days_are_cut`: for a seeded patient of three days, the union of the events of the three labellings equals the events of one run over the three days (each event once), with the ownership above.
The `docs/benchmark/ground-truth.md` convention section states ADR-064 in its words. The earlier note in this file on the record at the shared step ("the owner is the run whose first step is the decision step") is superseded by this decision.


### Completion note (worker, 2026-10-10; status left `in_progress` for the orchestrator's review, nothing merged)

Branch `ws04-t15-multi-day-labelling`. Files: `src/ralmon/benchmark/labelling.py`, `tests/benchmark/test_ground_truth.py`, `tests/benchmark/reference_phi_cp.py`, `tests/fixtures/benchmark/latent_days_phi_cp.yaml`, `docs/benchmark/ground-truth.md`, `docs/plan/03-decisions.md` (ADR-055 status line, (b) only), and one hand-over note each in WS04-T11 and WS08-T01. No contract file was edited.

**API.** `HistoryDay(latent, records=(), behaviour_log=())` (frozen dataclass, exported in `__all__`) and a final keyword-only `history: Sequence[HistoryDay] = ()` on `label_latent_day`, `label_latent_day_detailed` and `assemble_benchmark_day`; `MAX_HISTORY_DAYS` (14, defined in the labeller with a test that it equals `ralmon.monitor.offline.MAX_HISTORY_DAYS`: the layering test forbids a cross-package import below the package root). `LabelledDay` gains `history_record_index` (default `()`; `(history day, record)` for an event that a record of a history day explains, `None` otherwise). The labeller builds the ideal observation of each history day (same mode, signals and plan id) and calls the runner with `history=<tuple of ObservedDay>` only when the history is not empty, so a stub or a runner that does not take the keyword is called as before. Ownership (ADR-064): of the first VIOLATED record of each key, one decided before the first step is skipped (it is an earlier day's, only with a history; without one it stays a `RunnerError`), one decided at the closing step is discarded unless it is a day-end COUNT of this day, the rest is kept; the onset may lie as early as the first history day.

**Tests.** Written first and committed red (`72cab97`, 106 failed, 287 passed). Tests 1 to 11 of the task and of the ADR-064 note are `test_a_day_with_history_equals_the_full_run` (40 seeded three-day patients, days 1 and 2 against the independent reference over all the days), `test_evening_double_take_gives_the_morning_count_event`, `test_response_window_across_midnight_is_labelled_where_it_is_decided`, `test_day_without_history_is_unchanged` (18 cases x 2 days), `test_patient_level_plan_with_history`, `test_the_per_day_truth_is_a_subset_of_the_history_truth`, `test_hostile_history_raises_only_named_errors`, `test_the_shared_midnight_step_belongs_to_the_day_that_starts_there`, `test_a_record_decided_at_the_closing_step_is_discarded_from_the_closing_day`, `test_the_day_end_count_stays_with_the_day_it_closes`, `test_the_truth_does_not_depend_on_where_the_days_are_cut`; extras: seven hand-computed two-day patients HC-01 to HC-07 in the fixture file (each against the labeller, the reference and the partition of the run), the ownership rules with a stub runner, history records never produce events, `assemble_benchmark_day` with history, the history keyword on every entry point, the document. `test_ground_truth.py`: 137 test functions (116 before), 394 collected. The reference evaluator got `n_days` (one run over several days) and `owned_by_day` (the rule of ADR-064, written from the rule and not from the labeller); it still imports nothing from `ralmon`. Mutants checked by hand: no closing-step discard, discarding the day-end COUNT too, no skip of an earlier day's decision, the half-open day reversed: each killed.

**Measured effect of the history on the natural events** (days 1 and 2 of 40 seeded three-day patients per schedule, fixture prior, natural adherence, no injection; events of the history truth that the per-day truth lacks): doses 08:00 and 20:00, 22 of 485 (4.5%: 20 COUNT, 2 RESP); doses 08:00 and 22:00, 50 of 523 (9.6%: 20 COUNT, 30 RESP). The 7 to 12% of T10 was measured on other days and another schedule; the loss depends on how close the last dose is to midnight. The per-day truth is a subset of the history truth on these patients; it is not in general (case HC-06: a dose within the HOLD look-back of midnight is a HOLD violation of the day with no history and satisfied with it).

**Deviations from the task text, each with its reason.** (1) "Day without history is unchanged" holds for the 18 hand cases except that an event decided at the closing step is no longer in the day's own truth (ADR-064 (b) and test 8 require it for day 0, which has no history): GT-16 now expects `[]` and lists the two events under `expected_next_day`; `test_count_limit_is_explained_through_the_24_hour_window_of_the_counter` and `test_natural_double_take_needs_a_surplus_dispense_inside_the_counter_window` moved their COUNT limit from the closing step to a minute before it (a record may not have a negative onset, so the first moved to day 1); `test_labeller_takes_no_observed_day` pins the new parameter; `test_perfect_observation_equals_ground_truth_on_c1` and `test_hand_computed_cases_label_as_computed_by_hand` apply the ownership to the monitor's set and to the reference. Nothing else of T10 changed (five of its 116 test functions are modified, as listed; the other 111 pass unmodified). Process note: these five were changed in the alignment commit `3e78d75`, not in the red commit `72cab97`, because they change expected values and could only be written after the rule was applied; no case was removed (GT-16 moved to a next-day expectation). (2) Test 1 says "two-day patient"; the fixture patients have three days and both day 1 and day 2 are compared. (3) The seeded patients of tests 1, 6 and 11 use doses at 08:00 and 22:00 (the doses of 08:00 and 20:00 give only 2 events across midnight in 40 patients and the non-vacuity check needs more). (4) The link from an event to a record of a history day is in `LabelledDay.history_record_index` only; `AssembledDay` and the sidecar are not extended (the sidecar lists the records of the day), so such an event is `injected` and in no `truth_indices` of its day; WS04-T11, WS04-T12 and WS08-T01 are told. (5) Python 3.10 was not run (no 3.11-only construct added).

**Where the sources are silent (conservative reading taken).** A plan that lists the instances of one day only labels that day: the SCHED and day-end instances of earlier days do not exist for the monitor. A history day's `behaviour_log` keeps only the entries of its own day. The first VIOLATED record of a key decided before the first step is skipped without error only when there is a history. The last day of a patient has no next day: what its closing step decides is in no truth. CORRECTED by the review (below): the first version of this note said this was stated in `ground-truth.md` and in the hand-overs; it was not. No tolerance, no new number.

**Assumptions of dependents that turn out false.** WS04-T11: "a day is labelled with empty history" (hand-over of T10) and the advice "doses at least `delta2` before midnight" is withdrawn (see the fixes below: the last day of a patient has a hole that doses do not close); an injected C1 event can have its record in the previous day's sidecar. WS08-T01: `record_index` and `truth_indices` join every injected event to a record of its own day (false for a forced `double_take` or a `drug_nonresponse` of the evening); `onset_ms` lies in the day of the file (false: it may be in the day before); a detection at the closing step of day d-1 is matched to day d-1 (false by ADR-064; the baselines run one day at a time are the residual asymmetry, F12, stated in `ground-truth.md`). Not done here, left to gab as recorded in the Notes above: ADR-061 (history on `Detector.run`), ADR-065, the sentence of ADR-064 in `#trace-schema` rule 4 at its next bump.

### Fixes after the independent review (worker, 2026-10-10; status left `in_progress`)

The review returned PASS (ownership rule verified on 320 patients and 2073 events, 0 disagreements; 17 of 17 mutants killed) with one real hole and four minors, fixed on this branch; red test first (`a14f1eb`), then the fix.

**The last-day hole (real).** The last day of a patient has no next day, so every record the monitor decides at the final closing step is in no truth (the day-end COUNT of the last day excepted), and the monitor and the baselines emit those records on that day, which WS08 would score as false positives (reviewer: 76 of 200 patients had at least one, with SCHED ticks at 23:30 and 23:59; a plain dose at exactly 21:00 lands on it because its RESP deadline is 24:00). Corrected: `docs/benchmark/ground-truth.md` has a new subsection "The last day of a patient" that says it plainly with that figure; the earlier claim in this note and in the hand-overs that it was already stated was false and is corrected here and in the hand-overs of WS04-T11 and WS08-T01. The advice "keep the last doses at least `delta2` before midnight" is withdrawn (wrong at the boundary, ignores SCHED ticks near midnight and a HOLD or COUNT limit from a dose in the last minute; and nothing is decided after the closing step). Two policies are recorded as PROPOSALS for gab, with the choice open and WS04-T11 not to pick one silently: P1 (recommended by the reviewer and the coordinator) one extra unscored tail day per patient labelled with history, so the closing step of the last scored day is owned and the monitor and baseline runs are unchanged; P2 WS08 drops the detections decided at the final closing step of each patient, identically for all methods, losing real events. Test `test_the_last_day_of_a_patient_has_no_owner_for_its_closing_step` pins the facts (the monitor decides a dose at 21:00 and a tick at 23:30 at the final closing step, no day owns them, a tail day with history owns both, the day-end COUNT of the last day stays with it).

**Minor 3.** The ADR-055 status line (b) no longer says that the per-day truth "never adds a spurious one": it says it can contain an event the history truth does not (HC-06) and lacks others.

**Minor 4.** `test_the_truth_does_not_depend_on_where_the_days_are_cut` and the partition test of the hand cases excluded the final closing step with `decided_at_ms <= PATIENT_DAYS * DAY`, which would have included records no labelling can produce and passed only because those patients had none. They now use `owned_in_run` (the union of `owned_by_day` over the days: the final closing step is excluded explicitly, except the day-end COUNT of the last day), with the reason in a comment pointing to the last-day section. Tests 1 and 11 are run for both schedules (doses at 08:00 and 22:00, and at 08:00 and 20:00; 80 and 2 parametrised cases); the non-vacuity checks say which schedule they rely on: cross-midnight events by onset on 08:00/22:00, COUNT events gained by the history on 08:00/20:00 (where no RESP window crosses midnight).

**Process.** See the process note in the completion note above (the five T10 tests were changed in `3e78d75`).
