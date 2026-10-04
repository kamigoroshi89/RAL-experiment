---
id: WS04-T08
title: C3 integrity attacks at naive and informed attacker levels
workstream: WS04-benchmark
owner: agent
status: blocked
depends_on: ["WS04-T06", "WS02-T02", "WS02-T03"]
critical_path: true
non_negotiable: false
estimate_pd: 2.5
sources: ["analisi §5.1 (3)", "analisi §3.6", "analisi §4.5 (matrix rows 8, 9, 10; threat model)", "analisi §10 (fourth objection)"]
interfaces: ["02-interfaces.md#trace-schema", "02-interfaces.md#evidencevector"]
review_items: []
---
## Obiettivo

Inject C3 integrity attacks (ADR-002) against the declared attack classes of the threat model, at two attacker-knowledge levels: replay of the previous day's measurements, injection of plausible pressure values, forged dispense event, simulated presence (analisi §5.1 (3)). Attacker capabilities are the flags defined by WS02-T02, not chosen here. The informed attacker who is coherent on every available channel is generated and labelled as undetectable by construction: it stays in the ground truth so that the diagnosability limit is reported as a result, not a margin note (analisi §10 fourth objection). Concrete output: `inject_c3.py`, the C3 part of `injections.yaml`, tests.

## Contesto

- `docs/models/threat-model.md` (WS02-T02: attacker capabilities, `## Knowledge levels`, `## Subtype vocabulary`, attack-to-evidence table, exclusions; the compromised robot, RSM and specification are out of scope).
- `docs/source/analisi.md` §5.1 (3) (C3 list: "replay di misure dal giorno precedente, iniezione di valori plausibili a due livelli di conoscenza dell'attaccante, erogazione falsificata, presenza simulata"), §4.5 matrix rows 8, 9, 10, §3.6 (informed attacker risk ALTO), §10.
- `02-interfaces.md#trace-schema` and `02-interfaces.md#evidencevector` (`crypto_temporal`, `cross_device`, `witness` groups; `None` is not a negative).
- WS04-T06 and WS04-T07 outputs (`ObservedStream`, `injection.py` pipeline, `vocab.py`) and `docs/models/evidence-channels.md` if it exists (conventions for per-message authentication, gap G-4).
- `docs/plan/workstreams/WS04-benchmark/README.md` (subtype vocabulary).

Unblocked when WS04-T06 and WS02-T02 are `done`.

## File toccati

- `src/ralmon/benchmark/inject_c3.py` (create).
- `src/ralmon/benchmark/injection.py` (modify: register the C3 step after sequence numbering and the link step, so that a link dropout of the genuine device cannot remove attacker traffic).
- `src/ralmon/benchmark/vocab.py` (modify: gateway verification outcome key, provisional until WS02-T03).
- `configs/benchmark/injections.yaml` (modify: C3 section and the two capability sets).
- `tests/benchmark/test_inject_c3.py` (create).

## Test

Fixture-only values: previous-day cuff readings 128, 135, 120 at 08:00, 12:00, 16:00; today's genuine readings at the same times; latent HR 70. Write first.

1. `test_capability_sets_match_threat_model_levels`: the `naive` and `informed` capability flags (`fresh_metadata`, `coherent_pulse`, `plausible_values`, `spoofs_witness`) equal the table hand-copied from `## Knowledge levels` of `threat-model.md`; a difference fails with the document line.
2. `test_replay_copies_previous_day_values_in_window`: with a window 07:00 to 17:00 today's `bp` at 08:00, 12:00, 16:00 equal 128, 135, 120 and the genuine readings in the window are suppressed.
3. `test_replay_needs_previous_day`: `day_index = 0` raises `InjectionSpecError`.
4. `test_naive_replay_keeps_stale_metadata`: replayed samples keep the previous-day sequence numbers (duplicates) and a `t_device_ms` 24 h earlier (negative values allowed by the schema) while `t_rx_ms` is the current time; the signature contains `crypto_temporal.seq_gap_or_replay` and `crypto_temporal.timestamp_implausible`.
5. `test_informed_replay_rewrites_metadata`: `t_device_ms == t_rx_ms` and the sequence continues from the last genuine number; the signature has neither path.
6. `test_injection_naive_values_and_incoherent_pulse`: injected `bp` values lie within the physiological bounds passed in (fixture 50 to 250, labelled illustrative) and ignore the patient's history; `hr_pulse` differs from `hr_ecg` at the same instant, so `cross_device.pulse_vs_ecg_hr_diff` is in the signature.
7. `test_injection_informed_values_and_coherent_pulse`: injected values lie within the minimum and maximum of the patient's own genuine readings (fixture 120 to 135); `hr_pulse` equals `hr_ecg` exactly at each injected instant; metadata is fresh.
8. `test_dispense_forgery_adds_dispense_without_latent_event`: one extra DISPENSE at the chosen time, no `auth` sample, no INTAKE, latent unchanged; one C3 ground-truth event `dispense_forgery` with `end_ms is None`.
9. `test_presence_spoof_emits_presence_and_optional_intake`: at the naive level only a `presence` sample of 1.0; at the informed level with `spoof_intake` an INTAKE event (source `robot`) coherent with the forged dispense inside the visit dwell; no latent intake exists in either case.
10. `test_informed_coherent_attack_is_undetectable_by_construction`: `injection_informed` with fresh metadata, coherent pulse, plausible values and no message authentication has an empty evidence signature and still yields a C3 ground-truth event; with authentication deployed the signature is exactly `crypto_temporal.authenticated`; this case is tagged `expected_undetectable` in the injection log (analisi §4.5 last row).
11. `test_c3_never_mutates_latent_day`: the `LatentDay` is equal before and after every injection.
12. `test_c3_subtypes_are_in_threat_model_vocabulary`: injected ids are a subset of the `- <id>` lines under `## Subtype vocabulary` of `threat-model.md`; `dispenser_physical_tamper` and `timestamp_manipulation` are listed in `injections.yaml` as `not injected in v1` and never produced.
13. `test_signature_paths_are_contract_fields`: every dotted path produced by the signature function is one of the 20 `EvidenceVector` fields.
14. `test_realised_flag_and_ground_truth_mapping`: an injection that changes nothing is logged with `realised = False` and produces no ground truth; a realised one maps to `cls = C3`, `injected = True`, `template_id is None`, `confounder_group is None`.
15. `test_c3_step_runs_after_sequence_numbering_and_link_step`: a replayed duplicate sequence number is not renumbered by finalisation, and a BLE dropout window of the genuine device does not remove injected samples; forged messages receive sequence numbers according to the `fresh_metadata` flag.
16. `test_attack_streams_independent_and_deterministic`: samples outside the effect are bit-identical with and without the attack; the same seed gives the same output; the stream is `StreamPurpose.INJECTION_C3`.
17. `test_c3_rows_have_provenance_and_levels`: every C3 row of `injections.yaml` has parameters, `source_type` and `source_ref`; the capability sets cite `docs/models/threat-model.md`.
18. `test_gateway_verification_key_declared_in_vocab`: the per-message authentication outcome used by tests 4, 5 and 10 is a constant of `vocab.py`.

## Passi

1. Read `docs/models/threat-model.md`: copy the knowledge-level table into a hand-written fixture of the test and the capability flags into `injections.yaml` with `source_ref` pointing at the section; do not invent capabilities. The plan expects the flags to mirror the knowledge items named there (message format, care-plan knowledge, cross-device invariants, sequence and timestamp scheme, authentication scheme without keys, robot perception model); map them to the four flags of test 1 and record any mismatch in the completion note.
2. Write `tests/benchmark/test_inject_c3.py`; run it, confirm failure; commit `WS04-T08: add failing C3 injection tests`.
3. Implement `inject_c3.py`: `AttackerCapabilities` (frozen), one function per subtype (`replay`, `injection_naive`, `injection_informed`, `dispense_forgery`, `presence_spoof`; the level of the first, fourth and fifth is the capability set passed in and is recorded in the injection log), `attack_signature(subtype, capabilities, auth_deployed) -> tuple[str, ...]` computing the perturbed evidence paths, and the `expected_undetectable` tag. Message authentication is a deployment property (`auth_deployed`): when absent `crypto_temporal.authenticated` is `None`, never a negative.
4. Represent the gateway's per-message verification outcome as in the conventions table of `docs/models/evidence-channels.md` if it exists; otherwise emit an Event from source `gateway` with the key declared in `vocab.py` and mark it provisional in the completion note (WS02-T03 gap G-4).
5. Fill the C3 part of `injections.yaml` (parameters, level rows as `design_choice` with a rationale, capability sets with `source_ref`), regenerate the provenance table, register the C3 step in `injection.py` after sequence numbering and the link step.
6. Refactor, run `ruff check src tests`, `mypy src/ralmon`, `pytest tests/benchmark -q`; commit `WS04-T08: add C3 integrity attacks at two attacker levels`; set `status: done`.

## Done when

- `pytest tests/benchmark/test_inject_c3.py -q` exits 0; `pytest tests/benchmark -q` exits 0.
- `ruff check src tests` exits 0 and `mypy src/ralmon` exits 0.
- `python -m ralmon.benchmark.priors --check-table` exits 0.
- `grep -c 'expected_undetectable' src/ralmon/benchmark/inject_c3.py` prints at least 1.

## Notes

### Flag from the WS02-T02 review (orchestrator, 2026-10-02)

See `docs/models/threat-model.md` open points TM-OP-1, TM-OP-2, TM-OP-3, TM-OP-7 and TM-OP-8. The document agrees with the vocabulary, the four knowledge flags (`fresh_metadata`, `coherent_pulse`, `plausible_values`, `spoofs_witness`), `auth_deployed` and `expected_undetectable`, and with tests 4, 5 and 10 under the gateway policy "flag" (which this task does not state). Disclosed mismatches: test 2 against test 4 (a stale-stamped replay is late and not accepted), knowledge items without a flag, a single `auth_deployed` against per-device authentication, and the `expected_undetectable` tag. Not covered by the injector: a forged `auth` Sample written by a keyless injector (H-GW) can make INT SATISFIED even in an unauthenticated deployment (a MINOR of the review; TM-OP to be added). Kept `blocked`.

### Flag from the WS02-T03 review (orchestrator, 2026-10-04)

See `docs/models/evidence-channels.md` EC-OP-19: test 4 expects `crypto_temporal.timestamp_implausible` in the replay signature, in a benchmark whose genuine messages have no transport-delay model; the document reads a message that arrives long after its stamp as an asserted fact whatever the capability and lets a device without independent clocks assert but never deny, so test 4 holds and test 5 holds because the field is `None`, not True; the limit that remains: without a transport-delay model the field is True or `None`, never False. Step 4 already says to use the conventions table of `evidence-channels.md` once it exists (EC-OP-8 corrected). Kept `blocked`.
