---
id: WS05-T13
title: "EvidenceVector 0.2.0: dispenser group, seq_repeat / seq_gap, cuff_value_repeated, ADR-033 and ADR-040 conventions (contract, extractor, rule, tests, documents)"
workstream: WS05-monitor
owner: agent
status: ready
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
