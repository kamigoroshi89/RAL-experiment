---
id: WS02-T05
title: Diagnosability matrix (machine-readable) and hazard and standards paragraph
workstream: WS02-threat-fault-model
owner: agent
status: blocked
depends_on: ["WS02-T04"]
critical_path: false
non_negotiable: false
estimate_pd: 2
sources: ["analisi §4.5", "analisi §3.5", "analisi §2 R3 weakness 5", "analisi §4.8", "analisi §4.9 (4)", "analisi §10", "analisi §5.6 (A4)"]
interfaces: ["02-interfaces.md#attribution"]
review_items: ["R3-W4", "R3-W5", "AE-5"]
---
## Obiettivo

Create `configs/diagnosability.yaml`, the machine-readable diagnosability matrix of the `Attribution` contract, and `docs/models/diagnosability-hazards.md`, which renders the matrix, states its declared limits and adds the hazard and standards paragraph (ISO 13482, ISO 14971, IEC 62304). The matrix keeps the ten rows of analisi §4.5, including the two rows that are "not distinguishable" (silent cuff bias; informed attacker coherent on every channel), as declared results and not as margin notes (analisi §10, fourth objection), and adds rows for every C1, C2 and C3 subtype named in the fault and threat models. Every row carries an outcome with the embodied channel removed, so that WS08-T04 can report per row what the robot contributes (A4, AE-5). The hazard part closes R3 weaknesses 4 and 5 for the paper: collisions, infection control, camera privacy, presence versus identity, safety actions as hazards, and the fallback when the robot is unavailable.

## Contesto

Blocked until WS02-T04 is done (WS02-T01 to WS02-T03 are already done by then).

- `docs/models/attribution-rule.md` (worked cases W-01 to W-15 give the expected κ per row; the action policy is reused in the hazard register).
- `docs/source/analisi.md` §4.5 (the ten matrix rows and the sentence that turns two unverifiable claims into declared limits), §4.8 (claim reformulations), §10 (fourth objection), §3.5 (standards) and §4.9 item 4.
- `docs/source/review.md` R3 weaknesses 4 and 5 (taxonomy; collisions, infection control, camera privacy, presence is not identity, ISO 14971, ISO 13482).
- `docs/plan/02-interfaces.md#attribution` (the matrix is `configs/diagnosability.yaml`, owned by WS02, used to design tests and to declare which event types are distinguishable with which channels).
- `docs/models/` (`fault-model.md` and `threat-model.md` subtype vocabularies; `evidence-channels.md` channel identifiers, A4 mask and gaps G-1 to G-6).

## File toccati

- `configs/diagnosability.yaml` (create; create the directory `configs/` if it does not exist).
- `docs/models/diagnosability-hazards.md` (create).

## Test

Document and data task: verification checks a reviewer can run or inspect.

1. Schema. The file is block-style YAML with top-level keys `schema_version` (`"0.1.0"`), `contract` (`"02-interfaces.md#attribution"`), `sources`, `vocabulary`, `contract_gaps`, `rows`. `vocabulary` lists the allowed values: `distinguishable` (`distinguishable`, `conditional`, `partial`, `not_distinguishable`), `result` (`distinguishable`, `partial`, `not_distinguishable`), `kappa` (`C1`, `C2`, `C3`, `UNDETERMINED`, `NO_ALERT`), and the channel identifiers of WS02-T03. Bare `yes`, `no`, `on`, `off` never appear as values (YAML 1.1 reads them as booleans). `contract_gaps` copies the gap list of `evidence-channels.md` (id, text, affected row ids). Each element of `rows` is written with `  - id: DX-nn` at a two-space indent and has exactly these keys: `id`, `analisi_row` (1 to 10 for the ten analisi rows, `null` for added rows), `basis` (`analisi_4_5` or `inferred`), `event` (short English name), `true_class` (`C1`, `C2` or `C3`), `subtypes` (one-line flow list of `GroundTruthEvent.subtype` identifiers), `violated_templates` (list of `TemplateId` values: `range`, `sched`, `hold`, `count`, `resp`, `sys`, `int`; may be empty), `discriminating_evidence` (list of canonical `group.field` paths), `proposed_evidence` (list of proposed fields in slash notation `group/name`, empty if none), `channels_required_all` and `channels_required_any` (lists of channel ids), `distinguishable`, `outcomes`, `declared_limit` (true or false), `note`.
2. Outcomes. Each element of `outcomes` has `when` (mapping channel id to `available` or `unavailable`; the empty mapping means every channel of the default deployment is available), `result`, `expected_kappa` (list; several values mean "depends on residual evidence or on whether a violation is raised"), and, when `result` is `partial`, `candidates` (list of classes that cannot be told apart), and, when `result` is `not_distinguishable`, `masquerades_as` (class). Every row has a default outcome (`when: {}`) and an A4 outcome whose `when` is exactly `{CH-WIT: unavailable, CH-SYS-ROBOT: unavailable}`; rows not affected by the embodied channel repeat the default result there. The default and A4 `expected_kappa` values equal those of the worked cases of `attribution-rule.md`; any difference is explained in `note`.
3. Rows. The first ten rows are `DX-01` to `DX-10` with `analisi_row` 1 to 10 in the order of analisi §4.5 (see Passi step 3 for the content of each). `DX-04` (silent cuff bias) and `DX-10` (informed attacker) have `distinguishable: not_distinguishable` and `declared_limit: true`; in general `declared_limit` is true exactly when `distinguishable` is `not_distinguishable`. Rows added after `DX-10` have `basis: inferred` and `analisi_row: null`.
4. Coverage. Every identifier listed under `## Subtype vocabulary` in `docs/models/fault-model.md` and `docs/models/threat-model.md` appears in the `subtypes` list of some row, and the C1 subtypes `hypertensive_spike`, `drug_nonresponse`, `double_take`, `hypotension_below_hold` and `measurement_refusal` appear in rows with `true_class: C1` (WS04-T09 confirms the final C1 vocabulary; if it differs, WS04 records a mapping to these identifiers).
5. References. Every `CH-` token in the file is defined in `docs/models/evidence-channels.md`; every dotted evidence path is one of the 20 contract fields.
6. Document. `docs/models/diagnosability-hazards.md` has H2 headings in this order: `## Diagnosability matrix`, `## Declared limits`, `## Reading the matrix`, `## Hazards and standards paragraph`, `## Hazard register`, `## Traceability`. The matrix section has one table row per YAML row, each starting `| DX-nn |`, with columns id, event, true class, distinguishable, discriminating evidence, conditions.
7. Declared limits. `## Declared limits` covers `DX-04` and `DX-10` (and every other `not_distinguishable` row) with the wording of analisi §4.8 for the first: "faults that manifest in node health, device error codes, or signal quality are attributed to C2; silent faults producing plausible values remain indistinguishable from clinical deviations", the statement that the informed-attacker row is undetectable by construction, and the statement that the rate at which these rows occur is measured on the benchmark by WS08 (no number is written here). `## Reading the matrix` defines the four `distinguishable` values and states that `partial` means abstention (UNDETERMINED) with a candidate set, not an error.
8. Hazards and standards paragraph. One paper-ready paragraph (about 150 to 200 words, marked "draft for WS12-T04 and WS12-T06") that: names ISO 13482, ISO 14971 and IEC 62304 by number with a one-line description in general terms (safety of personal care robots; risk management for medical devices; medical device software life cycle); states that they frame the hazard analysis and that no conformity is claimed (pre-clinical technical validation, ADR-001); covers collisions, infection control, camera privacy, presence versus identity, safety actions as hazards with the clinician-in-the-loop principle and robot autonomy limited to stop, retry and call, and the fallback to the nurse when the robot is unavailable (ADR-003). Edition years and clause numbers are not cited (no human has verified them; same policy as ADR-018 for references).
9. Hazard register. A table with columns id, hazard, source, consequence, mitigation in the architecture, residual and owner, basis, with rows `H-01` onward covering at least: collision with people or obstacles; infection control; camera privacy (RGB-D images in patient rooms); presence mistaken for identity; safety actions (blocked dispenser, interrupted procedure) causing a missed dose; robot unavailable; misattribution (a silent C2 fault read as a clinical deviation, and the reverse); cascade folding hiding an independent event; stale or tampered care plan; alert overload (pointer to the false-alarm metric of WS08 and the vignette study of WS11). Mitigations cite only what the sources and ADRs fix (limited autonomy, heartbeat and fallback, separate witness fields, witness outcomes instead of images on `/ralmon/robot_evidence`, signed care plan, UNDETERMINED); anything else is written "open: lab safety review (WS10-T01) or clinician (WS00-T07)". No procedure, dose or clinical parameter is invented.
10. No invented numbers and no forbidden tokens; glossary respected (DISPENSE and INTAKE, alert and violation and attributed cause, assistive robot).

## Passi

1. Read `attribution-rule.md` and list its worked cases W-01 to W-15 with expected κ (default and A4). These are the expected outcomes of the rows.
2. Write the YAML header: `schema_version`, `contract`, `sources`, `vocabulary` (values of check 1, channel ids copied from `evidence-channels.md`), `contract_gaps` (copied from the gap list, at least G-1 dispenser content and interval, G-6 clock health).
3. Write rows `DX-01` to `DX-10` from analisi §4.5 (`basis: analisi_4_5`). Starting content, to be checked against the worked cases (the worked cases win on κ; record differences in `note`): DX-01 real hypertension, C1, `hypertensive_spike`, `range`, distinguishable "by exclusion", needs the ward-side channels; DX-02 drug non-response, C1, `drug_nonresponse`, `resp`, conditional ("only if there is a witness": `channels_required_any` is `CH-WIT` or `CH-CRYPTO`); DX-03 cuff detached, C2, `cuff_detached`, `sys`, distinguishable (error code, node state change; the inflation duration is the φ_SYS predicate itself and is not independent evidence); DX-04 cuff silent bias or drift, C2, `cuff_silent_bias`, `range` and `resp`, not distinguishable (no independent channel on pressure; pulse rate stays coherent), `masquerades_as: C1`; DX-05 robot late to the window, C2, `nav_delay` (also `impossible_goal`, `localisation_noise` if their evidence is identical), `sched`, distinguishable through the navigation outcome, robot-derived so partial under A4; DX-06 patient double take, C1 (adherence deviation), `double_take`, `count`, conditional ("if the dispenser measures content", gap G-1, `CH-DISP`); DX-07 dispenser sensor bounce, C2, `dispenser_bounce`, `count`, distinguishable (short interval between events, no content change; any number quoted from analisi is labelled "illustrative, unverified"); DX-08 replay of pressure measurements, C3, `replay`, conditional ("yes with authentication; partial without": sequence and timestamp evidence, cross-device incoherence supports); DX-09 falsified dispense event, C3, `dispense_forgery`, `resp` and `int`, partial (no witness, response constraint violated only after Δ2; candidates C1 and C3); DX-10 plausible injection coherent on every channel from an informed attacker, C3, `injection_informed`, no discriminating evidence, not distinguishable, `expected_kappa` `[C1, NO_ALERT]` (C1 if the injected values violate a template, `NO_ALERT` if they satisfy all templates), `masquerades_as: C1`.
4. Add rows with `basis: inferred` for every remaining subtype of the fault and threat vocabularies, grouping subtypes with identical evidence in one row (one-line `subtypes` list). Starting set: `stuck_at` (C2, plausible values, not distinguishable, as `cuff_silent_bias`; analisi §4.8); `ecg_noise` (C2, distinguishable through `signal_quality.ecg_sqi`); `ble_dropout` and `message_drop` (C2, distinguishable through link and liveliness evidence; seeds cascades); `process_kill`, `uncommanded_lifecycle_transition` and `battery_depleted` (C2, node or robot unavailable; a deliberate lifecycle transition is not a crash); `manipulation_failure` (C2, robot-derived); `link_delay`, `out_of_order` (C2, absorbed by the reorder buffer within its bound, so `NO_ALERT`, otherwise link evidence); `hypotension_below_hold` (C1, `hold`, by exclusion); `measurement_refusal` (C1, `sched`, conditional on the witness and on the navigation outcome, to separate it from `nav_delay`); `presence_spoof` (C3; analisi lists perception spoofing as a capability and "simulated presence" as an injection but has no matrix row: derive from the decision table and mark `not_distinguishable` if no channel can contradict a spoofed witness); `injection_naive` (C3, plausible but incoherent across devices: conditional on cross-device evidence with signal quality available); `clock_skew` and `timestamp_manipulation` (C2 versus C3, gap G-6: `partial` or `not_distinguishable`, justify); `dispenser_physical_tamper` (C3, an authenticated event that the patient did not cause). Give every added row its default and A4 outcomes.
5. Compute the A4 outcome of every row by applying the decision table with all `witness` fields and robot-derived system fields `None` (mask of `evidence-channels.md`), and any other `when` combination named by the C1 exclusion conditions (for example authentication unavailable for DX-02, DX-08, DX-09).
6. Write `docs/models/diagnosability-hazards.md`: render the matrix table (check 6), `## Declared limits` and `## Reading the matrix` (check 7), then the hazards and standards paragraph (check 8) and the hazard register (check 9). In the register, reuse the action policy of `attribution-rule.md` for H-05 and H-06 and reference the declared limits for the misattribution hazard.
7. Write `## Traceability`: analisi §4.5, §4.8, §4.9 item 4, §3.5, §10, R3-W4, R3-W5, AE-5, ADR-001, ADR-002, ADR-003, ADR-018 (policy on unverified references), and the items awaiting the clinician (WS00-T07) and the lab safety review (WS10-T01).
8. Run every command of `## Done when` and fix until each passes.

## Done when

All of the following, from the repository root (the schema check needs PyYAML; the registry of WS01 is also YAML, so a YAML loader is part of the toolchain):

- `test -f configs/diagnosability.yaml && test -f docs/models/diagnosability-hazards.md`
- The schema check exits 0 and prints `ok`:

```
python3 - <<'EOF'
import re, yaml
d = yaml.safe_load(open("configs/diagnosability.yaml"))
assert d["schema_version"] == "0.1.0" and d["contract"] == "02-interfaces.md#attribution"
rows = d["rows"]
ids = [r["id"] for r in rows]
assert len(ids) == len(set(ids)) >= 10 and all(re.fullmatch(r"DX-\d\d", i) for i in ids)
assert ids[:10] == ["DX-%02d" % k for k in range(1, 11)]
assert [r["analisi_row"] for r in rows[:10]] == list(range(1, 11))
assert all(r["basis"] == "analisi_4_5" for r in rows[:10])
assert all(r["basis"] == "inferred" and r["analisi_row"] is None for r in rows[10:])
KEYS = {"id","analisi_row","basis","event","true_class","subtypes","violated_templates","discriminating_evidence","proposed_evidence","channels_required_all","channels_required_any","distinguishable","outcomes","declared_limit","note"}
FIELD = re.compile(r"provenance\.(violated_template|template_kind)|system\.(node_lifecycle|diagnostics_ok|liveliness_ok|qos_deadline_missed|ble_link_quality|battery_low|nav_task_failed|manip_task_failed)|signal_quality\.(ecg_sqi|ppg_sqi|cuff_error_code)|cross_device\.pulse_vs_ecg_hr_diff|witness\.(robot_present|identity_confirmed|intake_observed)|crypto_temporal\.(authenticated|seq_gap_or_replay|timestamp_implausible)")
A4 = {"CH-WIT": "unavailable", "CH-SYS-ROBOT": "unavailable"}
for r in rows:
    assert set(r) == KEYS, (r["id"], set(r) ^ KEYS)
    assert r["true_class"] in {"C1", "C2", "C3"} and r["subtypes"]
    assert r["distinguishable"] in {"distinguishable", "conditional", "partial", "not_distinguishable"}
    assert set(r["violated_templates"]) <= {"range", "sched", "hold", "count", "resp", "sys", "int"}
    assert all(FIELD.fullmatch(e) for e in r["discriminating_evidence"])
    assert all(re.fullmatch(r"[a-z_]+/[a-z_]+", e) for e in r["proposed_evidence"])
    assert r["declared_limit"] is (r["distinguishable"] == "not_distinguishable")
    assert any(o["when"] == {} for o in r["outcomes"]) and any(o["when"] == A4 for o in r["outcomes"])
    for o in r["outcomes"]:
        assert o["result"] in {"distinguishable", "partial", "not_distinguishable"}
        assert o["expected_kappa"] and set(o["expected_kappa"]) <= {"C1", "C2", "C3", "UNDETERMINED", "NO_ALERT"}
        if o["result"] == "partial": assert o["candidates"]
        if o["result"] == "not_distinguishable": assert o["masquerades_as"] in {"C1", "C2", "C3"}
by = {r["id"]: r for r in rows}
for k in ("DX-04", "DX-10"):
    assert by[k]["distinguishable"] == "not_distinguishable" and by[k]["declared_limit"] is True
print("ok", len(rows))
EOF
```

- Subtype coverage prints nothing: `for f in fault-model threat-model; do sed -n '/^## Subtype vocabulary/,/^## /p' docs/models/$f.md | grep '^- ' | sed 's/^- *//; s/ .*//; s/`//g' | while read s; do grep -Eq "subtypes:.*[[ ]${s}[],]" configs/diagnosability.yaml || echo "missing $s"; done; done`
- Channel identifiers are defined, prints nothing: `grep -o 'CH-[A-Z-]*' configs/diagnosability.yaml | sort -u | while read c; do grep -q "$c" docs/models/evidence-channels.md || echo "unknown $c"; done`
- The document renders every row: `test "$(grep -c '^| DX-' docs/models/diagnosability-hazards.md)" -eq "$(grep -c '^  - id: DX-' configs/diagnosability.yaml)"` exits 0.
- `grep -o 'ISO 13482\|ISO 14971\|IEC 62304' docs/models/diagnosability-hazards.md | sort -u | wc -l` prints 3, and `grep -ci 'infection' docs/models/diagnosability-hazards.md`, `grep -ci 'privacy'` and `grep -ci 'identity'` each print at least 1.
- The evidence-path check of README acceptance criterion 2 prints nothing for `docs/models/diagnosability-hazards.md`.
- `grep -nE 'T[O]DO|T[B]D|[?]{3}|lore[m]' configs/diagnosability.yaml docs/models/diagnosability-hazards.md` prints nothing.

## Notes

### Flag from the WS02-T01 review (orchestrator, 2026-10-02)

Step 3 (DX-03) lists "cuff detached, C2, `cuff_detached`, `sys`" and "the inflation duration is the phi_SYS predicate itself"; `docs/models/fault-model.md` (device notes) says `sys` is not violated in the injected form of `cuff_detached` (no `sys` instance is opened; G-SYS-3 is the variant) and records the hazard CAS-5 (a lost or late `presence` sample can make INT VIOLATED from a link fault) and OP-12 (a device fault can reach an INTEGRITY violation, which provenance alone cannot attribute to C3: WS02-T04 line 40). Kept `blocked`.
