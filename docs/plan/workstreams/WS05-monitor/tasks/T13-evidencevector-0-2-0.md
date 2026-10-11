---
id: WS05-T13
title: "EvidenceVector 0.2.0: dispenser group, seq_repeat / seq_gap, cuff_value_repeated, ADR-033 and ADR-040 conventions (contract, extractor, rule, tests, documents)"
workstream: WS05-monitor
owner: agent
status: done
depends_on: ["WS05-T07"]
critical_path: true
non_negotiable: false
estimate_pd: 4
sources: ["ADR-032", "ADR-033", "ADR-034", "ADR-040", "ADR-074"]
interfaces: ["02-interfaces.md#evidencevector", "02-interfaces.md#attribution"]
review_items: []
---
## Obiettivo

Migrate the contract `#evidencevector` from 0.1.0 to 0.2.0 in ONE commit set (contract text, extractor, hierarchical rule, fault-model signature table, diagnosability file, fixtures, tests), as decided in ADR-074 amendment 3. Final field list (24 fields, 7 groups; 22 non-provenance):
- `provenance` (2): unchanged.
- `system` (9): the existing eight and `seq_gap: bool | None` (a sequence value is missing at the cut-off; system evidence; BLE sources only).
- `signal_quality` (4): the existing three and `cuff_value_repeated: bool | None` (True when the cuff reading equals the previous reading of the same cuff stream; `None` without a previous reading or when the device profile declares no resolution; False otherwise).
- `cross_device` (1), `witness` (3): unchanged.
- `crypto_temporal` (3): `authenticated`, `seq_repeat: bool | None` (a received (name, seq) repeats an accepted one; integrity evidence), `timestamp_implausible`. The old `seq_gap_or_replay` is REMOVED (breaking rename).
- `dispenser` (2), appended last: `interval_since_previous_ms: int | None`, `content_change: float | None` (before minus after: a release is positive, a bounce is zero; ADR-040 (2)); `None` when the dispenser reports none or has no content sensing, never a negative interval.
Meaning conventions (ADR-033): the key of the evidence mapping is `VerdictRecord.instance_key`; scalar `system` fields aggregate over the scope of the instance; `system.battery_low` is the robot battery; `witness.robot_present` is the patient presence observed by the robot. Outcome `declined` (ADR-040 (1)) does not make `system.manip_task_failed` True. The hierarchical rule keeps its eight rows: it reads `crypto_temporal.seq_repeat` where it read the repeat of the old field, `system.seq_gap` as the gap (system evidence, SE-class), and treats the dispenser group and `cuff_value_repeated` as context (relevance map `ctx`); it gains no `count` rows (OP-AR-10 stays open and is stated). The likelihood attributor (WS05-T12) is what reads the new fields.

## Contesto

`docs/benchmark/evidence/evidencevector-0.2.0-survey.md` (read in full: the migration surface with file:line), ADR-032, 033, 034, 040, 074 (amendment 3), `docs/models/evidence-channels.md`, `docs/models/attribution-rule.md`, `docs/models/fault-model.md`, `configs/diagnosability.yaml`, `src/ralmon/attribution/{evidence,rule,extract,render,__init__}.py`, `src/ralmon/benchmark/{inject_c2,inject_c3,measurement}.py` (`EVIDENCE_SIGNATURES`, the sidecars that write `evidence_paths`). Several tests parse `02-interfaces.md` as text and compare it with `fault-model.md`, so the contract and the fault-model signature table land in the same commit. Thesis-student zones are NOT touched; `tesista/` is untracked and not edited.

## File toccati

`docs/plan/02-interfaces.md` (EvidenceVector section, version, A4 sentence of the contract rule consistent with the A4 mask), `docs/models/{evidence-channels,attribution-rule,fault-model,threat-model}.md` (path names, field count 22, `declined`, `content_change` sign, enumeration check recomputed for the changed relevance map and the count of combinations), `configs/diagnosability.yaml`, `src/ralmon/attribution/*`, `src/ralmon/benchmark/{inject_c2,inject_c3,measurement}.py` (path names in signatures and sidecars only; the generator's NEW emissions are WS04-T18), `tests/**` that hard-code 20 or 18 fields or enumerate paths (`test_types.py`, `test_rule.py`, `test_invariants.py`, `test_inject_c2.py`, `test_inject_c3.py`, `tests/fixtures/attribution/`, `worked_cases.json`, `tests/test_public_api.py`), the Notes of the dependent tasks.

## Test

Write first; expected values hand-derived.
1. `test_evidence_vector_fields_match_contract_0_2_0` (24 fields, group order, dispenser last).
2. `test_old_sequence_field_is_gone_and_split_fields_exist`.
3. `test_extractor_seq_repeat_and_gap_from_the_trace`: a repeated (name, seq) gives `seq_repeat` True; a missing value gives `system.seq_gap` True; both can hold; `None` conditions of the old field carry over.
4. `test_extractor_dispenser_group_from_dispense_payload`: `interval_since_previous_ms` and `content_change` read from the DISPENSE payload keys; `None` when absent; the sign test (release positive).
5. `test_extractor_cuff_value_repeated`: equal consecutive cuff readings True, different False, first reading `None`, `None` when the profile declares no resolution (new capability / parameter `cuff_resolution`; no default value in the rule, the profile states it).
6. `test_hierarchical_rule_unchanged_on_the_old_cases`: every worked case W-01 to W-15 keeps its kappa with the renamed paths (re-derive the cases that used `seq_gap_or_replay`; document each re-derivation).
7. `test_new_fields_are_context_for_the_hierarchical_rule` (changing them alone never changes kappa).
8. `test_a4_mask_counts`: new fields are ward-side: unchanged under A4.
9. `test_declined_does_not_set_manip_task_failed`.
10. `test_contract_and_fault_model_signature_tables_agree`.
11. Enumeration check of `attribution-rule.md` recomputed by script (state the new combination count).

## Passi

1. Tests first (red commit). 2. Contract text and fault-model table in one commit with the dataclasses. 3. Extractor, rule, render. 4. Documents and diagnosability file. 5. Notes to WS02-T06, WS05-T12, WS04-T18.

## Done when

- `pytest -q`, `ruff check src tests`, `ruff format --check src tests`, `mypy src/ralmon` exit 0.
- `python3 tools/check_plan.py` exits 0.

## Notes

### Worker report (2026-10-11): implementation done, status left `in_progress` for the lead's review

**What changed.** `#evidencevector` is 0.2.0 in `docs/plan/02-interfaces.md` and in `src/ralmon/attribution/evidence.py` in the same commit set: 24 fields in 7 groups (22 non-provenance), the group `dispenser` last with `DispenserEvidence()` as the default of `EvidenceVector.dispenser` (so a constructor that omits it works; the other new fields have no default on purpose, a missed field is a type error), `DispenserEvidence` exported from `ralmon.attribution`. The extractor, the hierarchical rule, the renderer, the signatures of `inject_c2.py` and `inject_c3.py`, the fault-model signature tables, the diagnosability file, the golden worked day (both copies) and the worked-case fixture follow. Tests: `tests/attribution/test_evidencevector_0_2_0.py` (the 11 tests of the task, expanded), `tests/attribution/test_rule_enumeration.py` (test 11, a committed vectorised enumeration), and the 0.1.0 tests and fixtures updated to the new list.

**Enumeration (test 11).** `attribution-rule.md` section Enumeration check is recomputed: **262,055,088 combinations** (87,351,696 in 0.1.0; every template reads the new `system.seq_gap`, so each old combination gives three). C1 is reached by the same 18, 2, 18 and 90 combinations of `range`, `sched`, `hold`, `resp`. The vectorised table reproduces every number of the 0.1.0 section (including the 62,979,376 overlapping combinations of `resp`), agrees with `HierarchicalRule.decide` on 3,000 seeded random combinations per template (the whole space for `count`), and agrees with the 0.1.0 table on all 87,351,696 old combinations through the mapping old field to (`seq_repeat`, `seq_gap`): 0 differences. I2, I3, I4 (the same 9, 1, 9, 9 exceptions for `authenticated`) and the I5 reason moves (12,288 states of `sys`, 1,024 of `int`) are recomputed in the document.

**Re-derivation of the worked cases (test 6).** Old `True` with ratio 1.0 is `seq_repeat` True, `seq_gap` False (W-08-U, W-15-repeat); old `True` with a ratio below one is `seq_gap` True, `seq_repeat` False (W-09-jump, W-15, W-15-alone, W-15-jump); old `False` is both False (all base cases), old `None` both `None` (W-05-silent, W-05-silent-040, W-08-U-noseq). All 55 verdicts (kappa, row, reason) are unchanged; the decisive-field lists of the C1 cases gain `system.seq_gap` and name `crypto_temporal.seq_repeat`; W-15-alone names `system.ble_link_quality`, `system.seq_gap`. The 0.1.0 verdicts are frozen as literals in the test, so the check does not depend on the regenerated `worked_cases.json`.

**Contradictions of the survey (section d), as resolved here.** (1) Stale count: ADR-032 carries a dated note (24 fields, 22 non-provenance; the old "twenty-two" counted only the dispenser group; the sign is before minus after). (2) Sign of `content_change`: before minus after in the contract, the conventions table of `evidence-channels.md` and EC-OP-12 (the generator already wrote +1.0 per release). (3) "Silent faults raise no field": `stuck_at` now raises `signal_quality.cuff_value_repeated` and `dispenser_bounce` the two dispenser fields, both conditional (display resolution declared and a previous reading; the dispenser reports the key); `cuff_silent_bias` is the one fault silent for every reading. See judgment call 7. (4) `system.seq_gap` against `system.ble_link_quality`: only documented (EC-GAP-13, EC-OP-22, OP-AR-21), not resolved. (5) `/ralmon/robot_evidence` carries the witness fields and the robot-derived `system` fields, not `system.seq_gap`, not the dispenser group. (6) ADR-033 is accepted (its Status says so). (8) DX-06 and DX-07 stay `conditional`: the hierarchical rule does not read the dispenser group. (9) The A4 sentence of the contract rule now agrees with the A4 mask: six wholly robot-derived fields become `None`, four aggregates are recomputed, fourteen are unchanged. (10) Per-opening semantics: EC decision D-15. (11) The C1 counts of ADR-044 are unchanged (18/2/18/90).

**Judgment calls (each is the most conservative reading; each can be reversed locally).**
1. `system.seq_gap` is NOT a C2 predicate of the hierarchical rule. The spec asks for "system evidence, SE-class" and for the old verdicts to be kept: making the gap decisive would turn W-15-alone (gap with a ratio below one but at or above the floor) from UNDETERMINED to C2. The rule reads the gap where it read the loss: it blocks C1, RS-2 names it, AM-2 counts it; the delivery ratio decides C2 (SE-5).
2. A gap reported with a complete delivery ratio (the extractor cannot produce it) is read as a conflict (RS-2, row 6), not as a clean stream and not as C3.
3. C1 requires `system.seq_gap` and `crypto_temporal.seq_repeat` both denied (invariant I4: a field that asserted leads to an abstention must be required denied).
4. Dispenser group: the LATEST accepted `DISPENSE` of the evidence window received by the cut-off describes the instance (both keys from that event); `content_change` is read only with the new capability `content_sensing`; the interval is device-reported, an `int` >= 0 (a negative, bool, float or string value is `None`). Alternatives (minimum interval over the window, first opening) are in D-15.
5. `cuff_value_repeated`: plain equality of the two latest accepted `bp` readings by device time received by the cut-off and visible by the last admissible step (the previous day counts), computed for every template; gated by the new capability parameter `DeviceCapabilities.cuff_resolution` (a positive finite number or `None`; no default anywhere in the extractor or the rule; the generator default of 1 mmHg of ADR-074 amendment 2 belongs to WS04-T18's device-error model). Equality of unrounded floats is exact; D-16 records the alternatives (a tolerance of one resolution step, a run length).
6. `declined` counts as a task that did not fail for both `nav_task_failed` and `manip_task_failed` (the field is False when every outcome of the window is `success` or `declined`; True if any is `failed`, `timeout` or `late`).
7. The signatures `stuck_at` and `dispenser_bounce` of `EVIDENCE_SIGNATURES` are no longer `()` (a change beyond a rename; the spec says "path names in signatures and sidecars only"). I made them consistent with the fault-model tables, which a test compares with the signatures and which the amendment (stuck_at separated by the new field, bounce by the dispenser group) requires to be non-empty. The sidecars of a benchmark generated before this commit carry the old path and the empty signatures and must be regenerated. If the lead wants the signatures to stay empty until WS04-T18 emits the keys, revert the two entries, the two rows of the fault-model catalogue and the two assertions in `test_inject_c2.py` (`test_signature_paths_are_contract_fields`, the bounce and stuck_at record tests).
8. Frozen formal documents (`01`, `07`, `09`, golden worked day and its test copy) are edited in place with the old name stated, and `docs/formal/README.md` carries an amendment paragraph; no verdict or number of the freeze changed. The `evidence` block of the golden is read by no test.
9. `configs/diagnosability.yaml`: `schema_version` 0.2.0, `proposed_channels` renamed `context_channels`; no outcome, expected kappa or row verdict changed. `system.seq_gap` is assigned to `CH-SYS-WARD`, `crypto_temporal.seq_repeat` to `CH-CRYPTO`, `cuff_value_repeated` to `CH-SQI`.
10. The research prototype under `docs/benchmark/evidence/` and the done tasks (WS02-T01 to T05, WS04-T07/T08, WS05-T07, WS01-T08) keep the old field name as history; the survey is untouched.

**Hand-over to WS05-T12 (likelihood attributor).** Read all 22 fields. The hierarchical rule is context-blind to `cuff_value_repeated` and the dispenser group; the likelihood table reads them. `system.seq_gap` and `system.ble_link_quality` are one grouped cell (EC-OP-22). `dispenser.interval_since_previous_ms` is compared with the registry name `dispense_bounce_interval_ms` by the attributor (the extractor never reads it; the value is still awaiting a human). The cuff display resolution is a device-profile parameter, not a registry name. `declined` makes `manip_task_failed` False, so a refusal and a missed robot task differ in that field. `Decision.missing` and `evidence_used` of the hierarchical rule now include `system.seq_gap`.

**Hand-over to WS02-T06 (cells).** The field list is frozen at 24. A cell per cause is needed for `system.seq_gap`, `crypto_temporal.seq_repeat`, `signal_quality.cuff_value_repeated`, `dispenser.interval_since_previous_ms`, `dispenser.content_change`. The grouped-field variant names `system.seq_gap` with `system.ble_link_quality` (the task text was updated). Conditions that make a cell `None` rather than a reading: `cuff_value_repeated` is `None` without a declared display resolution or without a previous reading; the dispenser fields are `None` when the dispenser reports no key (first opening of a stream, no content sensing). `stuck_at` is no longer silent for every reading (test `test_silent_faults_do_not_zero_diagnostics_ok` lists only `cuff_silent_bias` as silent for every reading).

**Hand-over to WS04-T18 (generator).** Emit the DISPENSE keys `interval_since_previous_ms` (an `int`, never negative; omit the key for the first opening of a stream and across midnight) and `content_change` (before minus after: +1.0 for a release and 0.0 for a bounce, as it already does). Round the cuff readings to the device resolution; the extractor needs the same value in the run's `DeviceProfile` as `cuff_resolution` (nothing else couples them), and a profile that declares no resolution makes `cuff_value_repeated` `None`. The signatures of `stuck_at` and `dispenser_bounce` in `inject_c2.py` are already the 0.2.0 ones; a naive replay, injection or forgery is numbered from `FORGED_SEQ_START` and raises `crypto_temporal.seq_repeat` (the C3 signatures use that name). Regenerate any benchmark sidecar written before this commit.

**Other consumers.** WS05-T09 (ROS message `RobotEvidence`): the topic carries the witness fields and the robot-derived `system` fields; `observe_robot_evidence` needs a `SystemHealthEvidence`, so the node must pass `seq_gap=None`. WS07-T05 `EXPECTED_EVIDENCE` renames `seq_gap_or_replay` to `system.seq_gap` in `ble_dropout` and `message_drop` and to `crypto_temporal.seq_repeat` in `replay` and `dispense_forgery`. WS08-T04: A4 lists the new fields as unchanged (14 unchanged, 6 None, 4 recompute); `EMBODIED_MASK_ALL` stays six paths.

**Open points left open.** OP-AR-10 (no `count` rows; stated), EC-OP-22 (span of `seq_gap`), EC-GAP-13. The registry value `dispense_bounce_interval_ms` and the display resolution of a real cuff are still not in the repository.

### Fix round after the independent review (2026-10-11)

- Duplicate frames: `_cuff_value_repeated` and `_dispenser` skip the second and later arrivals of the same `(node, name, seq)` (docs/formal/01-signals-sampling.md section 3.4), as `crypto_temporal.seq_repeat` counts them. Tests: `test_cuff_value_repeated_skips_a_resent_frame`, `test_dispenser_group_skips_a_restamped_copy_of_an_earlier_opening`.
- `cuff_value_repeated` is `None` when the latest accepted reading is before the evidence window (D-16 updated); the previous reading may precede it.
- Other contracts changed by this task: `#ros-2-interfaces` 0.1.0 to 0.1.1 (text only, no message change: the row of `/ralmon/robot_evidence` now says which `EvidenceVector` fields the robot publishes, ADR-074 amendment 3). Nothing pins the old version string (grep over `tests/`, `tools/`, `src/`, `ros2/`). `#evidencevector` 0.2.0 is the only contract with a changed signature.
- The dispenser group and `cuff_value_repeated` are NOT gated by scope in the extractor; masking is the job of the relevance map of the likelihood table (hand-over notes of WS05-T12 and WS02-T06).
- Minor: the A4 test parses the contract sentence and compares the six and four names and the count of fourteen with the A4 table; the contract sentence says the fourteen are the two `provenance` fields and twelve ward-side evidence fields; the enumeration agreement test gained the C1 exclusion-set neighbourhood (every C1 combination and all single-field changes of each); the 'Sequence gap' explained-away item of the rule document no longer says the link fields decide the gap; stale 'twenty fields' in the yaml, WS04-T08 test 4 and the WS02 README check (`grep` prints nothing with the 24-field list) updated. The old field is named in the migration notes without the group prefix so that the README grep stays empty.
