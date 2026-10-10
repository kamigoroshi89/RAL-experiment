---
id: WS05-T11
title: "Robot-channel availability from NODE_STATE colocated reports (ADR-054 (b))"
workstream: WS05-monitor
owner: agent
status: in_progress
depends_on: ["WS05-T10"]
critical_path: true
non_negotiable: false
estimate_pd: 1.5
sources: ["ADR-054", "docs/models/evidence-channels.md H-MASK, H-INIT, EX-5, EX-9", "docs/formal/02-templates.md section 4.7 and TG-9"]
interfaces: ["02-interfaces.md#monitor", "02-interfaces.md#signals"]
review_items: []
---
## Obiettivo

Implement option (b) of ADR-054, chosen by gab on 2026-10-09: the availability of the two robot channels `presence` and `intake` comes from the robot `NODE_STATE` reports with `payload.colocated` (true at an arrival, false at a departure), one mask for both channels, and the held level of `presence` belongs to one co-location episode (the episode rule already in the monitor). After this task a generated day whose trace carries the reports no longer witnesses a later dispense with the presence of an earlier visit, and `stats().presence_samples_without_availability_marks` is 0 on it. `estimate_pd` is a rough planning figure.

## Contesto

Blocked until WS05-T10 is `done` (both tasks edit `offline.py` and `core.py`; this keeps them in sequence).

- `docs/plan/03-decisions.md` ADR-054 (reproducers 1 and 2, the options, the known divergence with the extractor) and ADR-035 (the `Event.payload` conventions of `NODE_STATE`; proposed: if it changes the key, this task follows it).
- `docs/models/evidence-channels.md` (the `NODE_STATE` row with `colocated`, H-MASK, H-INIT, EX-5, EX-9, EC-GAP-10).
- `src/ralmon/monitor/core.py` (`StreamingMonitor.push_event`, `push_availability`, the episode rule) and `tests/monitor/test_witness.py` (the pinned hazard and divergence tests).
- Design rule: the translation lives inside `StreamingMonitor.push_event` (a robot `NODE_STATE` event with a boolean `payload.colocated` becomes an availability mark of both channels at the same device time and receive time, ordered and late by the same rule). Then `run_offline` and the ROS 2 node of WS05-T09 get the same mask from the same code, and no public name is added.

## File toccati

- `src/ralmon/monitor/core.py` (modify: `NODE_STATE colocated` handled in `push_event`; a counter of reports in `MonitorStats`)
- `tests/monitor/test_witness.py` (modify: the pinned hazard test is replaced by the tests below, as ADR-054 Migration asks) and `tests/monitor/test_availability_reports.py` (create)
- `docs/models/evidence-channels.md` (modify: the extractor reads the presence level with the episode rule, EX-5; the known divergence of ADR-054 is closed in the text)
- `docs/plan/03-decisions.md` (modify: ADR-054 status, one line: implemented)

## Test

Write first; each fails before the implementation. Fixture-only, F0, `step_ms = 60000`.

1. `test_departure_report_ends_the_witness`: presence `1.0` at 07:00 with `colocated` true at 07:00 and false at 07:10, a DISPENSE at 21:00 with no INTAKE: INT is not SATISFIED (PENDING with `undecidable: channel_unavailable:presence`, or the verdict the semantics gives for an unavailable channel, `docs/formal/05` section 3.5); before this task it was SATISFIED (reproducer 2 of ADR-054 with reports).
2. `test_a_visit_at_the_dispense_witnesses_it`: `colocated` true at 20:58, presence `1.0` at 21:00, DISPENSE 21:00: INT SATISFIED.
3. `test_reports_drive_both_channels`: the same mask applies to `intake`.
4. `test_gate_is_zero_with_reports`: on a day with reports `presence_samples_without_availability_marks == 0`; on a day without reports it stays positive (the hazard is still reported, never hidden).
5. `test_traces_without_reports_are_unchanged`: every golden case and every existing monitor test without `NODE_STATE colocated` gives the same records as before (H-INIT is applied only to a trace that carries reports; the test states the reading chosen and why).
6. `test_a_report_is_ordered_and_late_like_an_input`: a late report is refused and listed in `late_inputs()`; a report of another node or without a boolean `colocated` is ignored and counted.
7. `test_offline_and_streaming_agree`: `run_offline` and a hand-driven `StreamingMonitor` give the same records on a day with reports.
8. `test_hostile_reports_raise_only_named_errors`: junk payloads (the pattern of `tests/monitor/test_field_fuzz.py`).

## Passi

1. Tests first; read the failures.
2. Handle the report in `push_event`; keep the episode rule; add the counter.
3. Replace the pinned hazard test of `test_witness.py` by tests 1 and 4; keep `test_known_divergence_with_the_extractor_of_evidence_channels` until WS05-T07 implements the extractor with the episode rule, then that task turns it into an agreement test.
4. Amend `docs/models/evidence-channels.md` (EX-5: the level of a step is the latest sample of the current co-location episode, otherwise undefined).
5. Run "Done when", set `status: done`, and tell WS04-T11 (the builder writes the reports) and WS05-T07 in their Notes.

## Done when

- `pytest tests/monitor -q` and `pytest -q` exit 0.
- `ruff check src tests`, `ruff format --check src tests` and `mypy src/ralmon` exit 0.
- `grep -c "test_documented_hazard_a_trace_without_zeros_or_marks_witnesses_every_later_dispense" tests/monitor/test_witness.py` prints `0`.
- `python3 tools/check_plan.py` exits 0.

## Notes

### Completion note (worker, 2026-10-10)

- Implemented in `StreamingMonitor.push_event` (`src/ralmon/monitor/core.py`): a `NODE_STATE` event with source `robot` and a boolean `payload.colocated` is buffered as one availability entry (kind `avail`) that marks both `presence` and `intake`; it is ordered, late, duplicate (key `("event", source, "node_state", seq)`) and finalised like any input, and a late report is listed in `late_inputs()`. `push_availability` keeps its signature and meaning. No public name is added; `MonitorStats` gains two counters, `availability_reports` (reports applied as marks) and `colocated_reports_ignored` (a `colocated` key from another source or with a value that is not a `bool`; these are also in `ignored_events`, like every NODE_STATE without the key).
- Reading of H-INIT (stated in the module docstring of `tests/monitor/test_availability_reports.py` and in the class docstring): the mask starts "available until the first mark", as the monitor always started, because a streaming monitor cannot know at step 0 that a trace will carry reports and the traces without reports must be unchanged (test 5). Consequence: before the first arrival of a day the INT marker is `value_undefined:presence` where the evidence-channels reading gives `channel_unavailable:presence`; both are PENDING and both keep `witness.robot_present` not False (EX-9 I3 and I4). Recorded in the H-INIT row of `docs/models/evidence-channels.md`.
- Not applied: the H-MASK condition "the robot node is `active`". Only `colocated` is read; a robot `NODE_STATE` with `state` `inactive`/`unreachable` and no `colocated` is still ignored by the monitor. Open for gab: if the C2 injector of the robot lifecycle (WS04-T07) must also mask the channels in the monitor, the builder has to write `colocated` false for the window, or the monitor must read `state` (this would change the meaning of the mask and needs an ADR).
- Test 2 and the arrival case of test 3 and test 8 pass before the implementation too (an unmarked channel is available, and the old code ignored every NODE_STATE without error); the red state of the commit `WS05-T11: add failing tests` has 11 failing tests. `test_known_divergence_with_the_extractor_of_evidence_channels` is kept (it drives `push_availability` directly and still pins the monitor side).
- `docs/formal/` was not touched. `vocab.py` of the benchmark does not yet declare `colocated` in `PAYLOAD_KEYS[NODE_STATE]` (WS04-T11 hand-over below).
