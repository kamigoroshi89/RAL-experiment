---
id: WS05-T07
title: "Attribution package: hierarchical rule, cascades, Attributor, natural-language rendering"
workstream: WS05-monitor
owner: agent
status: blocked
depends_on: ["WS05-T04", "WS02-T04", "WS02-T05"]
critical_path: true
non_negotiable: false
estimate_pd: 3
sources: ["analisi §4.5", "analisi §4.9 (3)", "analisi §2 R3 weakness 6"]
interfaces: ["02-interfaces.md#attribution", "02-interfaces.md#alert", "02-interfaces.md#evidencevector"]
review_items: ["R3-W6"]
---
## Obiettivo

Implement `ralmon.attribution`: the `EvidenceVector` with its six parts, `AttributedCause`, `Explanation`, `Detection`, `Alert`, the `HierarchicalRule` (integrity evidence gives C3, else system evidence gives C2, else a violation with coherent channels gives C1, else UNDETERMINED), the `RuleAttributor` that turns violated records into alerts with cascade root-cause propagation, a deterministic natural-language rendering of `Explanation.text` for nursing staff (specification-level traceability, not "intrinsic explainability", analisi §4.8), and the `EvidenceExtractor` that builds an `EvidenceVector` from samples, events and violated records (the step that WS02-T03 gap G-5 found without an owner). Predicates, tables and worked cases come from the WS02 documents; nothing is decided from memory. It closes R3-W6 on the tool side (the wording is tested with clinicians by WS11).

## Contesto

Blocked until WS05-T04, WS02-T04 and WS02-T05 are `done`.

- `docs/models/attribution-rule.md` (WS02-T04: evidence predicates, decision table, C1 exclusion conditions, abstention reasons, cascade table, invariants I1 to I6, worked cases W-01 to W-15).
- `docs/models/evidence-channels.md` (WS02-T03: field semantics, derivation from the trace schema and ROS 2, trace evidence conventions for `Event.payload`, decisions D-1 to D-8, A4 mask, last admissible evidence time, parameters requested from the registry).
- `configs/diagnosability.yaml` (WS02-T05: one row per event type, declared limits DX-04 and DX-10, A4 outcome per row).
- `docs/formal/07-alert-tuple-mapping.md` (WS01-T07: alert tuple, traceability wording, disposition of CP5 and CP13).
- `docs/source/analisi.md` §4.5 (six evidence groups, hierarchical rule, matrix).

## File toccati

- `src/ralmon/attribution/` (modify: real modules `evidence.py`, `alert.py`, `rule.py`, `attributor.py`, `render.py`, `extract.py`; placeholders removed from `_stubs.py`)
- `tests/attribution/` (create: `test_types.py`, `test_rule.py`, `test_invariants.py`, `test_diagnosability.py`, `test_cascades.py`, `test_render.py`, `test_extract.py`)
- `tests/fixtures/attribution/` (create: worked cases W-01 to W-15 copied from `attribution-rule.md` with their case ids, and the derivation-table rows of `evidence-channels.md` as event and sample fixtures)

## Test

Write first; each fails before the implementation. Expected values come from the WS02 documents (worked cases, derivation table, diagnosability rows) and are copied with their ids; the numeric examples below use the F0 fixture registry and are fixture-only.

Types and alert fields (`test_types.py`)

1. `test_evidence_dataclasses_match_contract`: field names and order of `ProvenanceEvidence`, `SystemHealthEvidence`, `SignalQualityEvidence`, `CrossDeviceEvidence`, `EmbodiedWitnessEvidence`, `CryptoTemporalEvidence` and `EvidenceVector` equal `#evidencevector` (20 fields); all are frozen and slotted.
2. `test_alert_extends_detection_and_matches_contract`: `Alert` subclasses `Detection`; field order is `t_ms, label, score, tau, kappa, sigma_norm, rho, xi, verdict, priority, root_cause_of, caused_by`; `AttributedCause` values are `C1`, `C2`, `C3`, `UNDETERMINED`.
3. `test_alert_fields_derive_from_the_record`: a `VIOLATED` record with `decided_at_ms = 32_700_000` and `sigma_norm_interval = (-0.6, -0.6)` gives `t_ms == 32_700_000`, `label == kappa`, `score == 0.6` (minus sigma-tilde, higher is more anomalous), `sigma_norm == -0.6`; an interval `(-0.9, -0.2)` gives `sigma_norm == -0.2` (the upper end, the smallest violation that is certain); a `PREDICTED_VIOLATION` record uses `t_eval_ms` as `t_ms` and its `predicted_sigma_norm` as `sigma_norm`; `priority` comes from the registry entry named by the template's `priority_param`. If WS01-T07 fixes a different rule, its rule wins and this test is corrected with a note.

Rule and invariants (`test_rule.py`, `test_invariants.py`)

4. `test_rule_matches_worked_cases[<W-nn>]`: every worked case W-01 to W-15 of `attribution-rule.md` (template, kind, non-`None` fields, all others `None`) gives its expected cause, decisive fields in precedence order and, for UNDETERMINED, its reason.
5. `test_invariant_i1_purity`: kappa is unchanged when `rho`, `sigma_norm_interval`, `state` and `t_eval_ms` of the record vary (Hypothesis).
6. `test_invariant_i2_precedence`: asserted integrity evidence that is not explained away gives C3 whatever the other fields say (Hypothesis).
7. `test_invariant_i3_provenance_is_never_sufficient`: all 18 non-provenance fields `None` gives UNDETERMINED for every `TemplateId`.
8. `test_invariant_i4_no_certainty_from_missing_data`: setting any single field to `None` never turns UNDETERMINED into a definite class and never turns a non-C1 result into C1 (Hypothesis over the fixture vectors).
9. `test_invariant_i5_locality`: masking a field that is neither decisive nor part of the template's C1 exclusion conditions leaves kappa unchanged; masking with the A4 mask of `evidence-channels.md` changes only the fields that table lists.
10. `test_invariant_i6_cascade_consistency`: over random violated-record sets the graph is acyclic, `caused_by` and `root_cause_of` are mutual inverses and an effect never has a kappa different from its root's.
11. `test_analisi_matrix_rows_by_hand`: the rows of analisi §4.5 reproduced by hand: `seq_gap_or_replay` asserted with no link fault gives C3; a cuff error code gives C2; `nav_task_failed` asserted with a violated `sched` gives C2; a violated `range` with every relevant channel available and coherent gives C1; a silent cuff bias (all channels coherent) gives C1 and row DX-04 declares it not distinguishable.
12. `test_diagnosability_rows_reproduced[<row id>]` (`test_diagnosability.py`): each row of `configs/diagnosability.yaml` is turned into an `EvidenceVector` from its evidence pattern; distinguishable rows give the stated cause; rows declared not distinguishable (DX-04, DX-10) give the documented result and keep their flag; each row is its own test id and the rows are read through the file schema, never re-typed.
13. `test_missing_evidence_entry_is_all_unavailable`: an `instance_key` absent from the evidence mapping gets a vector with provenance from the record and every other field `None`, hence UNDETERMINED, and no exception (the key is `VerdictRecord.instance_key`, decision D-1).

Cascades and incremental use (`test_cascades.py`)

14. `test_cascade_row_15_00_of_analisi`: case W-11 (analisi §4.6): a missed measurement (violated `sched` with navigation-failure evidence, root C2) followed by the day-end measurement-count violation gives the effect `caused_by == root.instance_key`, kappa C2 inherited, and the root `root_cause_of == [effect.instance_key]`.
15. `test_independent_evidence_prevents_folding`: an effect violation whose decisive datum is not the one the root made missing stays top-level (`caused_by is None`), as the cascade rules of `attribution-rule.md` require.
16. `test_effects_are_returned_but_filterable`: `attribute_all` returns roots and effects; `[a for a in alerts if a.caused_by is None]` lists only top-level alerts.
17. `test_alerts_come_out_in_rank_order`: the output order equals `rank_alerts` applied to it (priority direction from `ralmon.spec`).
18. `test_update_returns_only_new_or_changed_alerts`: `RuleAttributor.update` returns `[root]` for the first record; when the effect arrives it returns `[effect, root]` with the root now carrying `root_cause_of`; an identical repeated call returns `[]`.
19. `test_update_equals_attribute_all_for_any_batching` (Hypothesis): splitting a time-sorted list of violated records into consecutive batches and applying `update` gives the same final alert set as one `attribute_all` call.
20. `test_predicted_alert_is_replaced_not_duplicated`: a `PREDICTED_VIOLATION` record gives an alert with a provisional kappa (WS02-T04 section "Predicted violations"); the later `VIOLATED` record of the same `instance_key` makes `update` return one alert for that key with `verdict == VIOLATED`; a predicted alert whose instance ends `SATISFIED` is kept in history and produces no new alert.

Rendering (`test_render.py`)

21. `test_rendering_contains_traceability_fields`: for a `VIOLATED` `range` alert from bp 152 against the F0 band, `Explanation.text` names the violated template in words, the clinical parameters used with units, the margin in native units and normalised (`-12 mmHg`, `-0.60`), the confidence with its kind and the declared guarantee, the attributed cause and the decisive evidence fields; expected fragments are fixed strings in the test.
22. `test_rendering_is_deterministic_and_locale_free`: identical inputs give identical text; no dependence on locale, clock or dictionary order.
23. `test_rendering_never_uses_forbidden_terms`: the text never contains `PILL`, `subsystem`, `tampering`, `ensures`, `intrinsic explainab`, `orthogonal`, `edge cloud` or `distribution-free` (binding glossary and claim wording of `01-conventions.md` section 7, and ADR-002 for C3).
24. `test_undetermined_rendering_names_the_missing_channels`: for UNDETERMINED the text says the cause is not determined, gives the abstention reason of `attribution-rule.md` and lists the unavailable fields by canonical `group.field` path.
25. `test_predicted_rendering_says_early_warning`: for `PREDICTED_VIOLATION` the text says the violation is predicted, that it is not a definitive verdict, and states the guarantee wording (marginal over patient episodes under exchangeability) in plain words.
26. `test_dispense_and_intake_are_not_conflated`: text about the dispenser event says "dispense" and text about the robot witness says "intake" (ADR-004).
27. `test_explanation_fields`: `Explanation.template`, `instance_key`, `subformula_path` (from `VerdictRecord.subformula_path`), `param_values` (the instance values) and `evidence_used` (decisive fields in precedence order, canonical `group.field` paths) are filled.

Extractor (`test_extract.py`)

28. `test_extractor_channel_unavailable_is_none_not_false`: no event of a kind means the corresponding fields are `None`; a declared "denied" reading uses the representation of `evidence-channels.md` section Conventions.
29. `test_extractor_witness_none_without_robot`: no `presence` sample gives every `witness.*` field `None`; with `presence` present and no `intake` inside the evidence window, `robot_present` is true and `intake_observed` is false (asserted absence, different from `None`).
30. `test_extractor_derivation_table[<row>]`: each row of the derivation table of `evidence-channels.md` (trace source to field) is a fixture with its documented value.
31. `test_extractor_sequence_gap_explained_by_link_fault`: decision D-3: a gap with asserted link evidence does not set `seq_gap_or_replay` as integrity evidence.
32. `test_extractor_is_causal_property` (Hypothesis): the vector for a record is unchanged when inputs after its evidence cut-off (decision D-7) are added.
33. `test_offline_equals_streaming`: `extract_evidence(day, records)` equals feeding the same samples and events into `EvidenceExtractor` in `t_rx_ms` order and asking at each record's cut-off.
34. `test_extractor_requires_registry_parameters`: constructing it without any parameter listed in "Parameters requested from the registry" of `evidence-channels.md` raises `RegistryError` (no default values).
35. `test_extractor_merges_robot_evidence`: `observe_robot_evidence(t_ms, witness, system)` (the fields the robot publishes on `/ralmon/robot_evidence`) appear in the vectors of records with a cut-off at or after `t_ms`, merged with the ward-side fields by the placement rules of `evidence-channels.md`; before any robot message the witness and robot-derived fields are `None`.
36. `test_robot_unavailable_makes_robot_fields_none`: a `NODE_STATE` event for the robot node that reports liveliness lost (payload keys of the trace evidence conventions) sets `system.liveliness_ok` to false and turns every robot-derived field and every `witness.*` field to `None` from that time (placement S4: the robot is unavailable, the channel is missing, not negative).

## Passi

1. Verify unblock conditions; branch `ws05-t07-attribution-package`; `status: in_progress`. Read the Contesto documents, `02-interfaces.md#alert` and decision D7 of the workstream README; write in the completion note: the evidence key (D-1), the cut-off rule (D-7), the priority direction, the accepted treatment of predicted alerts (CP13) and any WS02 gap that changes a field (G-1 to G-6): a field that is not in the contract is not implemented here, it is reported.
2. Copy W-01 to W-15 and the derivation-table rows into `tests/fixtures/attribution/` with their ids; write the tests; run `pytest tests/attribution -q`; watch them fail for the right reason. Commit `WS05-T07: add failing attribution tests`.
3. Implement `evidence.py` and `alert.py` verbatim from the contracts (`Alert` a slotted frozen dataclass inheriting `Detection`; the derivation of test 3 in one function `alert_from_record`).
4. Implement `rule.py`: `AttributionRule` protocol and `HierarchicalRule`, one small pure function per evidence predicate of `attribution-rule.md`, the decision table in precedence order, the abstention reasons; `None` never counts as a negative reading.
5. Implement `attributor.py`: `RuleAttributor(registry, templates, rule=None)` with `attribute_all` (stateless, deterministic, cascade folding by the table of `attribution-rule.md`, output ordered by `rank_alerts`) and `update` (returns alerts new or changed since the previous call by comparing with the alerts it holds; used by the ROS 2 wrapper of WS05-T09 so that the wrapper needs no comparison logic).
6. Implement `render.py`: template-driven English text from the fields of the alert, the record and the template; plain functions, no locale, no clock; wording follows the traceability rules of WS01-T07 and the glossary. Implement `extract.py`: `EvidenceExtractor(registry, ...)` with `observe_sample`, `observe_event` (events go through `event_to_sample` for signals; `NODE_STATE`, `DEVICE_ERROR`, `ROBOT_TASK` events feed the health, quality and task fields by the payload keys of the trace evidence conventions) and `evidence_for(record)`, `observe_robot_evidence` (used by the ROS 2 attribution node of WS05-T09) and `extract_evidence(day, records)`.
7. Refactor; remove migrated names from `attribution/_stubs.py`; update `attribution/__init__.py`; run `pytest tests/attribution -q`, `ruff format src tests`, `ruff check src tests`, `mypy src/ralmon`.
8. Run every command of "Done when". Commit `WS05-T07: implement attribution package`; set `status: done` and `status: ready` in the task files whose `depends_on` are now all `done`; tell WS06-T01 (`Detection` is now real), WS08-T01 (name of the evidence function) and WS11-T02 (renderer entry point) in the completion note.

## Done when

From the repository root, inside `.venv`:

- `pytest tests/attribution -q` exits 0 (worked-case ids `W-01` to `W-15` and the diagnosability row ids appear in `pytest tests/attribution -q --collect-only`).
- `ruff check src tests` and `ruff format --check src tests` exit 0; `mypy src/ralmon` exits 0.
- `python -c "from ralmon.attribution import EvidenceVector, ProvenanceEvidence, SystemHealthEvidence, SignalQualityEvidence, CrossDeviceEvidence, EmbodiedWitnessEvidence, CryptoTemporalEvidence, AttributionRule, Attributor, AttributedCause, Alert, Explanation, Detection, HierarchicalRule, RuleAttributor, EvidenceExtractor, extract_evidence"` exits 0 and none has `__ralmon_stub_owner__`.
- `! grep -nEi "intrinsic explainab|orthogonal|ensures|tampering|subsystem" src/ralmon/attribution/render.py` succeeds.
- `! grep -rn "^from ralmon\.\(baselines\|eval\|benchmark\)\|^import ralmon\.\(baselines\|eval\|benchmark\)" src/ralmon/attribution` succeeds.
- `python tools/check_plan.py` exits 0.

## Notes

### Flag from the WS01-T05 review (orchestrator, 2026-10-01)

Line 64 says `update` returns only new or changed alerts, but the SCHED refinement records of `docs/formal/05-three-valued-semantics.md` change the upper end of a VIOLATED-pending instance at every step (OP-T05-19). Reconcile with WS01-T07 (alert severity) after ADR-029 (proposed). Kept `blocked`.

### Flag from the WS02-T03 review (orchestrator, 2026-10-04)

See `docs/models/evidence-channels.md` EC-OP-1 to EC-OP-21 and decisions D-3, D-9, D-11, D-14: test 29 needs the robot status, not only presence samples, for `intake_observed` False; test 31 puts the gap-explained-away reading in the extractor whereas D-3 puts it in the rule; test 34 should require only the extractor parameters; test 35 and WS05-T09 (`observe_robot_evidence(t_ms, witness, system)`) merge the robot published field values directly, while the document does not treat a `/ralmon/robot_evidence` snapshot that is not a trace item as an extractor input (EC-OP-15); test 36 says robot fields go `None` "from that time", while facts asserted earlier in the window stay. Kept `blocked`.

### Hand-over from the WS04-T09 review (orchestrator, 2026-10-07)

- Do not count `presence` samples when comparing the observed streams of the pair `informed_robot_noauth`: a spoof can add one extra sample at tick plus lag (about 15 of 40 realisations). The reading of `declined` and of the `colocated` `NODE_STATE` is proposed in ADR-040.

### Hand-over from the WS01-T07 review (orchestrator, 2026-10-08)

Read `docs/formal/07-alert-tuple-mapping.md` section 1 (sigma_norm of VIOLATED and predicted alerts, CP13: kappa of a PREDICTED_VIOLATION alert is UNDETERMINED and the alert is superseded by the VIOLATED alert with the same `xi.instance_key`) and section 9 (open points OP-T07-1..17) and proposed ADR-041 before starting. Where this task text assumes a provisional kappa for predicted alerts (WS02-T04 check 8 and step 5; WS05-T07 tests 18, 20, 25) or counts a pair matched by a predicted alert (WS08 E3/E4), follow OP-T07-10 and ADR-041 and record any deviation here. `attribute` stays pure (kappa independent of `state`, test 5 scoped to the rule); the state check sits in `attribute_all`.

### Hand-over from the WS05-T03 review (orchestrator, 2026-10-09)

WS05-T03 (`ralmon.spec`, branch `ws05-t03-spec-package`, status `in_progress` when this note was written) is implemented. (1) Where this task says to load the F0 copy or the fixture registry, `load_registry(path, step_ms=..., allow_fixture_only=True)` is required: without the flag the first run raises a `RegistryError` that names the FIXTURE-ONLY rows (ADR-027); the shared file is `configs/registry/fixture.yaml` (version 0.0.0) and the test-owned copy is `tests/fixtures/spec/registry_f0.yaml`. (2) The real registry (0.2.0) has three unset names (`priority_sys`, `priority_int`, `bound_dose_count_upper`): `get()` raises `UnsetParameterError` (a `RegistryError`) for them while `load_templates` still succeeds, so ranking SYS and INT alerts, or reading the dose-count bound, must be handled explicitly or done with the fixture registry. (3) `rank_alerts` reads `alert.xi.instance_key` (the real `Alert`); a flat `instance_key` is only a fallback for objects without `xi`, and `xi` wins if both exist.

### Hand-over (worker, 2026-10-09, from the WS05-T04 review, round 2)

(1) Hazard: No INT-based result on a generated day is evidence until ADR-054 is decided (the presence level of the last robot visit is read at every later dispense when the trace has no availability mark and no zero). Gate on `run_offline_detailed(...).stats.presence_samples_without_availability_marks`: it must be 0 (or the trace must carry the explicit zeros of option (a)), and report it when it is not. `presence_level_older_than_window_steps` is information only and is positive even on a correct trace, because a robot visit (10 minutes in the generator) is longer than `int_window` (5).

(2) Known divergence between the extractor of `docs/models/evidence-channels.md` and the monitor, for EX-5 and EX-9: the extractor holds a presence level across an outage ("the latest accepted PRESENCE sample whose visible step is not after it"); the monitor of WS05-T04 clears the level when the channel is marked unavailable (ADR-054, provisional), so after the return the level is undefined until a new sample. Example: `presence = 0.0` at 06:00, the channel down from 06:10 to 20:50, a dispense at 21:00, no INTAKE, no `auth`: the extractor reads `witness.robot_present` False and `witness.intake_observed` False, so invariant I2 of EX-9 expects the INT instance VIOLATED, while the monitor says PENDING with `undecidable: value_undefined:presence`, and invariant I4 (a PENDING instance with that marker has `witness.robot_present` not False) fails for the pair. A test of this task that takes the invariants of EX-9 from a monitor run will see it. It is closed either by adopting the episode rule in the extractor (a window step reads the latest sample of the current co-location episode, otherwise undefined) or by reverting the monitor to the literal hold; ADR-054 does not decide it. Pinned on the monitor side by `tests/monitor/test_witness.py::test_known_divergence_with_the_extractor_of_evidence_channels`. WS02 owns the evidence document.

(3) For `Explanation.subformula_path` and the text of the violated sub-formula use `resolve_subformula_path(template, path)` and `resolve_subformula_paths(template, path)` from the package root `ralmon.monitor` (outside `__all__`); a `subformula_path` can hold several parts joined by `;`, the decisive part first. Dynamic instance keys are `<template id>@<t_device_ms of the anchoring event>` with `#2`, `#3` on a clash. A VIOLATED RESP record with an undefined pre-dose pressure has `rho = None` (counted in `stats().rho_unavailable`): read it as "no probability available", not 0. Read the late and rejected inputs and the counters from `run_offline_detailed`, not from `run_offline`.

### ADR-054 decided (gab, 2026-10-09)

The known divergence of note (2) is decided: the extractor adopts the episode rule (the presence level of a window step is the latest sample of the current co-location episode, otherwise undefined). WS05-T11 amends EX-5 of `docs/models/evidence-channels.md`; this task implements the extractor with it and turns `test_known_divergence_with_the_extractor_of_evidence_channels` into an agreement test.

### Hand-over from WS05-T11 (worker, 2026-10-10)

EX-5 and the held-level bullet of `docs/models/evidence-channels.md` now state the episode rule (the level of a window step is the latest sample of the current co-location episode, otherwise undefined; EX-5 item (m)). The monitor side is implemented: a robot `NODE_STATE` with boolean `colocated` marks both channels in `StreamingMonitor.push_event`. Two differences remain between the extractor of this document and the monitor, to keep in mind when the tests take EX-9 invariants from a monitor run: (1) H-INIT: the extractor reads the channels unavailable until the first report, the monitor reads them available until the first mark and, when the first mark is a `colocated` report, clears a presence level held from before it (before the first arrival the level is undefined, so I3 and I4 hold either way, only the marker name differs: `value_undefined:presence` against `channel_unavailable:presence`); (2) H-MASK "the robot node is `active`": the monitor does not read the robot `state`, only `colocated`, so a run with random robot status events (inactive, unreachable) and a co-located report left true gives a monitor mask that is on where the extractor's is off; build such traces with `colocated` false for the window, or open an ADR. `test_known_divergence_with_the_extractor_of_evidence_channels` still drives `push_availability` and pins the monitor side; turn it into the agreement test with the extractor as said above.

### Hand-over from WS02-T05 (worker, 2026-10-10)

Test 12 reads each row of `configs/diagnosability.yaml` "from its evidence pattern": a row carries the canonical evidence paths (`discriminating_evidence`) and the expected causes per outcome (`outcomes[].expected_kappa`), not the readings of a vector. Build the `EvidenceVector` from the worked case that the row `note` names (W-01 to W-15 of `attribution-rule.md`) and read the expected cause from the outcome whose `when` matches (the empty mapping is the unauthenticated default deployment; `CH-CRYPTO: available` is the authenticated one; the A4 pair is the A4 outcome). Skip, with a recorded reason, an outcome whose `when` names the proposed channel `CH-DISP` (the analisi verdict of DX-06 and DX-07, not reproducible by the rule until ADR-032) and the expected cause `NO_ALERT` (a statement about detection; the rule runs on violated records only). Several expected causes in one outcome are the union over the templates in `violated_templates`, not alternatives for one vector.
