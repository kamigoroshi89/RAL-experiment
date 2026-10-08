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
