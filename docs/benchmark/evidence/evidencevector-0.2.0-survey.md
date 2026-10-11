# Survey for `#evidencevector` 0.2.0 (contract bump bundle)

Date of the survey: 2026-10-11, repository HEAD `955a43a`. Read-only; nothing in the repository was edited.
Paths are relative to `/home/gab/Desktop/RAL experiment`. Line numbers are those of HEAD (note: `docs/models/evidence-channels.md` and `docs/plan/03-decisions.md` changed in commit `d301607` while this survey was running; all numbers below are re-checked after it).

Baseline (0.1.0): `docs/plan/02-interfaces.md:545-598`, twenty fields in six groups (provenance 2, system 8, signal_quality 3, cross_device 1, witness 3, crypto_temporal 3). Implemented verbatim in `src/ralmon/attribution/evidence.py:41-113`.

Status vocabulary: ACCEPTED (decided by gab), PROPOSED (an ADR with `[DA-CONFERMARE]` or a proposal that needs gab), OPEN (a question or a declared limit that no ADR proposes to change).

## 0. Summary table

| id | item | source | fields touched | status |
|---|---|---|---|---|
| EV-01 | dispenser evidence group | ADR-032 | + `dispenser.interval_since_previous_ms`, `dispenser.content_change` | ACCEPTED (details open) |
| EV-02 | split of the sequence Boolean | ADR-034 | `crypto_temporal.seq_gap_or_replay` -> `crypto_temporal.seq_repeat` + `system.seq_gap` | ACCEPTED |
| EV-03 | identical repeated cuff value (for `stuck_at`) | ADR-074 amendment 2 (2) | + one field (name, group, type not fixed) | ACCEPTED in principle, shape OPEN |
| EV-04 | key, scope, `battery_low`, `robot_present` meaning (+ optional per-node mappings) | ADR-033 | none (text); optional type change of 4 `system` fields | PROPOSED |
| EV-05 | A4 sentence of the contract rule | ADR-049 (n) | none (text) | PROPOSED |
| EV-06 | sign of `content_change` | ADR-040 (2) | semantics of EV-01 field | PROPOSED |
| EV-07 | outcome `declined` | ADR-040 (1) | semantics of `system.manip_task_failed` (no field) | PROPOSED |
| EV-08 | liveness contract for `diagnostics = stale` | ADR-074 amendment 2 (5) | semantics of `system.diagnostics_ok` (no field) | ACCEPTED, already in `evidence-channels.md` |
| EV-09 | declared-channel set of the rule | ADR-044 | none; uses the canonical path list | PROPOSED |
| EV-10 | device capability profile | ADR-036 | none; capabilities of the new fields | PROPOSED |
| EV-11 | contract-gap register | ADR-021 | umbrella; lists "no clock-health field" | PROPOSED |
| EV-12 | clock health | EC-GAP-6, OP-AR-7, TM-GAP-TIME, DX-19/26 | + clock-health field (not proposed) | OPEN (declared limit) |
| EV-13 | device battery | EC-GAP-7, FM OP-4 | + device-battery field (not proposed) | OPEN (declared limit) |
| EV-14 | name `witness.robot_present` | EC-GAP-11, ADR-033 (4) | rename (not proposed) | OPEN |
| EV-15 | witness quality / modality | TM-OP-13 | + field (explicitly "none proposed") | OPEN |
| EV-16 | minimum interval between doses | ADR-065 | its alternative reads `dispenser.interval_since_previous_ms` | PROPOSED, dependency only |

Adjacent contract bumps that are not `#evidencevector` but ride on the same decisions (section 6): `#alert` 0.2.0 (`p_kappa`, `cause_set`), `#metrics` 0.2.0, `#priorsource` 0.2.0 (ADR-038, now also the cuff display resolution), `#detector` 0.2.0 (ADR-061).

## 1. Accepted items

### EV-01 Dispenser evidence group (ADR-032) - ACCEPTED

- Source: `docs/plan/03-decisions.md:267-273`. Status line 273: "accepted (decision of gab, 2026-10-11, decision 2 of ADR-074). The contract change `#evidencevector` 0.2.0 is bundled with every other change already in sight (survey of 2026-10-11), not bumped alone." Confirmed in ADR-074 amendment 2 (1), `03-decisions.md:666`.
- Fields (decision text, line 270): "add a group `dispenser: DispenserEvidence` to `EvidenceVector`, with `interval_since_previous_ms: int | None` ... and `content_change: float | None` (content after minus before, in the unit the dispenser declares), both `None` when the dispenser reports no interval or has no content sensing, never a negative reading." Group "appended last" with default `None` "so that existing constructors keep working". Channel `CH-DISP` (`evidence-channels.md:98`), registry name `dispense_bounce_interval_ms` (`evidence-channels.md:379`; value awaiting).
- Why: rows 6 (double take) and 7 (dispenser bounce) of the matrix, group `double_take_vs_bounce`. Measured: without the channels the groups 1 and 4 have a log likelihood ratio of exactly 0; with them the share of distinguishable pairs with D > 0 rises from 42% to 88% (`docs/benchmark/evidence/likelihood-attribution.md:15`, 550, 866; `03-decisions.md:666`).
- Affected tasks named by the ADR (line 270): WS02-T04, WS02-T05, WS04-T05, WS04-T07, WS05-T07, WS07-T03, WS10-T03. Also: WS02-T06 (cells), WS05-T12, WS04-T06 (`vocab.py`), WS04-T09, WS04-T11.
- Open details the ADR does not close (all need a statement before the bump, otherwise the contract text is a second jump away):
  1. Per-instance semantics. The ADR gives a per-opening quantity ("interval since the previous opening"), but a vector is built per violated instance with an evidence window (`evidence-channels.md:23`, D-7). Which opening(s) does the field describe (the one that anchors the instance, the latest before the cut-off, the minimum over the window)? The research says it plainly: "The extension fields read the DISPENSE events of the day up to the decision time; in a real EvidenceVector ADR-032 would define them per instance" (`likelihood-attribution.md:850`).
  2. Producer. The ADR says the values "come from the `DISPENSE` payload keys". The generator emits `content_change` only (`src/ralmon/benchmark/vocab.py:12`, `measurement.py:198, 874, 998`) and never `interval_since_previous_ms` (no hit in `src/`); the prototype derives the interval from timestamps (`docs/benchmark/evidence/scripts/likelihood/likelihood_attr.py:44-45`). Device-reported versus gateway-derived is undecided (matters for a forged dispense that copies the bounce timing, `likelihood-attribution.md:850`).
  3. `None` for the first opening of a stream and across midnight (no previous opening): not stated.
  4. Reading classes. The prototype uses two Booleans (`dispenser.short_interval`: interval below `T_b`; `dispenser.no_content_change`: `content_change == 0`) while the contract has numbers; the thresholds (`dispense_bounce_interval_ms`, "zero") must be named for the rule and for WS02-T06.
  5. Scope table (D-10, `evidence-channels.md:459`) needs a row: which templates read the dispenser (`count`, `hold`, `resp`, `int` in the prototype, `EXT_TEMPLATES`, `likelihood_attr.py:47`).
  6. Sign: see EV-06 (contradiction).
- Migration named by the ADR (line 270): "the A4 mask lists the two fields as unchanged; WS05-T07 test 1 counts twenty-two fields; WS04 payload keys move from provisional to the conventions table". The count "twenty-two" is stale once EV-02 and EV-03 are in (section 4).
- Rows that go from `conditional` to evidence-backed: DX-06 and DX-07 (`configs/diagnosability.yaml:335, 372`, `proposed_evidence: [dispenser/content_change, dispenser/interval_since_previous_ms]`); `docs/models/diagnosability-hazards.md:61`; DX-22/DX-27 cited in gap G-1 (`configs/diagnosability.yaml:62`). `diagnosability-hazards.md:58` says the dispenser evidence "does not change" DX-27 because no rule row reads it.
- Rule consequence (not decided): `attribution-rule.md:949` (OP-AR-10) "If `dispenser/interval_since_previous_ms` and `dispenser/content_change` are adopted, the table gains rows for the double take (C1) and the bounce (C2) ... They are not part of the enumeration." ADR-074 keeps the hierarchical rule only as reference (`ours-hier`), so whether it reads the new fields is open (section 5, point 9).

### EV-02 Split of `crypto_temporal.seq_gap_or_replay` (ADR-034) - ACCEPTED

- Source: `03-decisions.md:283-289`; status line 289 identical to EV-01; `03-decisions.md:666`.
- Change (line 286): "replace the field by two, `crypto_temporal/seq_repeat` (a received `(name, seq)` repeats an accepted one: integrity evidence) and `system/seq_gap` (a sequence value is missing at the cut-off: system evidence), ... each `bool | None` with the `None` conditions of the single field today." The old field disappears: this is a breaking rename, not an additive change.
- Why: a pure loss (C2 `ble_dropout`, `message_drop`) must not become C3 under the integrity-first order (`evidence-channels.md:509`, EC-GAP-3; `fault-model.md:530` FM-GAP-SEQ; `threat-model.md:419` TM-GAP-SEQ; `attribution-rule.md:945` OP-AR-6). Research: the repeat/gap split is one of the two things without which groups 1 and 4 are not separable and 37 members lose C3 (`likelihood-attribution.md:26`, 866).
- Group placement: `seq_gap` goes in `system`, `seq_repeat` stays in `crypto_temporal`; the field order matters (`EVIDENCE_PATHS` is "in contract order", `evidence.py:113`; `rule.py:174` `_ORDER`).
- Migration named by the ADR: "the A4 mask lists both as unchanged; WS04-T07 `EVIDENCE_SIGNATURES` and WS07-T05 `EXPECTED_EVIDENCE` rename the path in the rows of `ble_dropout`, `message_drop`, `replay` and `dispense_forgery`; WS02-T04 drops the explained-away rule for the sequence gap (the case W-15 becomes a reading of `system/seq_gap`)". Affected: WS02-T04, WS02-T05, WS04-T07, WS04-T08, WS05-T07, WS07-T05 (+ WS02-T06, whose grouped-field variant names `seq_gap_or_replay`, `T06-attribution-likelihood-table.md:23`).
- Not changed by the split (`evidence-channels.md` D-3 text, `attribution-rule.md:959` OP-AR-19): a forged number that jumps ahead is a gap under both definitions.
- Scope: BLE devices only (D-12, `evidence-channels.md:475`); so `system.seq_gap` is a `system` field that is not robot-derived. See section 5, point 5, for the `/ralmon/robot_evidence` topic.

### EV-03 Identical repeated cuff value (`stuck_at`) - ACCEPTED in principle, shape OPEN

- Source: ADR-074 amendment 2 (2), `03-decisions.md:666`: "A new field for the 'identical repeated value' of the cuff (the reading equals the previous reading of the same stream) separates `stuck_at`; the generator ROUNDS the cuff readings to the device resolution, a device-profile parameter with default 1 mmHg (before: unrounded floats, natural repeat probability exactly 0 ...); the value for a real cuff ... is not in the repository and is a sensitivity range." Announced in amendment 1 (`03-decisions.md:665`: "a field 'identical repeated value' for `stuck_at` (in progress)").
- Prototype definition (`likelihood-attribution.md:1168`): `cuff.identical_repeat` "(outside the contract, prototype): A if the last two cuff `bp` readings received by the decision time of the alert (the previous day's readings included) are exactly equal, D if they differ, `None` if fewer than two exist. It is read by the templates that read the cuff (range, sched, hold, resp, sys)." Cells: P(A | stuck_at) = 1 - eps; P(A | other) = max(rep_nat, eps).
- Earlier statements that this item reverses: `fault-model.md:532` FM-GAP-FLAT ("No field for a run of identical values ... the plausible stuck value stays a declared limit"); `fault-model.md:536`; `configs/diagnosability.yaml:563-568` (DX-11 note: "no field is proposed here because that would be a contract change that no source asks for"); `evidence-channels.md`/`fault-model.md:418` (coverage: "Not raised by any fault" list, `stuck_at` row "none").
- What is not fixed (ADR text gives none): the field name, the group, the type, the `None` conditions. Suggestion only (the survey invents no decision): a `bool | None` in `signal_quality` (a frozen value is a signal-quality symptom; keeps 7 groups), `None` when fewer than two readings exist or the cuff is out of scope; alternatives are a one-field group (8 groups). gab must choose.
- Data semantics that must be stated with it: ordering across days (the prototype includes the previous day), the window (last two readings received by the decision time versus readings inside the evidence window), and the effect of rounding: natural repeats appear at rate rep_nat (0.0200 / 0.0388 / 0.0980 for r = 1 / 2 / 5 mmHg, `likelihood-attribution.md:1170-1190`); effective k of `stuck_at` is 1 reading for 30 of 67 realised records (`likelihood-attribution.md:1191-1196`), so the field cannot be asserted when the window holds one reading.
- Adjacent contract change: the cuff display resolution is a new generator parameter; `DeviceErrorModel` belongs to `#priorsource`, whose 0.2.0 bump is already proposed by ADR-038 (`03-decisions.md:318`). Bundling it there avoids another bump.
- Tasks/modules to migrate: WS04-T06 (`measurement.py` rounding), WS04-T07 (`stuck_at` signature, `inject_c2.py:186-197`, currently `()`), WS04-T11, WS02-T03 (field semantics row), WS02-T04/T05 (DX-11 leaves `declared_limit`), WS02-T06 (cells), WS05-T07/T12 (extractor), fault model coverage table (`fault-model.md:395-418`; `stuck_at` row `:402`).

### EV-08 Liveness contract of `diagnostics = stale` (ADR-074 amendment 2 (5)) - ACCEPTED, semantics only

- Source: `03-decisions.md:666` (5); text already committed at `docs/models/evidence-channels.md:218-229` ("Bridge node: liveness contract for `diagnostics = stale`") and in `WS07-T03` Notes. No field changes. It fixes when `system.diagnostics_ok` is `False` (stale) and states that `ok` "does NOT mean that the sensor measures correctly". The contract text of 0.2.0 may cite it. `stale_lease_ms` and the driver period are device-profile parameters with no default (`evidence-channels.md:226`).

## 2. Proposed items awaiting gab

### EV-04 ADR-033: key of the mapping, scope of scalar system fields, `battery_low`, `robot_present` - PROPOSED

- Source: `03-decisions.md:275-281` (status 281: proposed). Statement of meaning, "no signature change": (1) mapping key = `VerdictRecord.instance_key`, per care plan; (2) scalar `system` fields aggregate over the scope of the instance (asserted if one component asserts, denied only if every capable component is denied); (3) `system.battery_low` = robot battery; (4) `witness.robot_present` = patient presence observed by the robot, name kept. Version: "0.1.1 if adopted alone (text only), or part of 0.2.0 with ADR-032 and ADR-034" (line 278). ADR-032 (line 270) and ADR-034 (line 286) both say 0.2.0 is "shared with" / "together with" ADR-033, but amendment 2 accepted only 032 and 034.
- Already implemented without the ADR: WS05-T07 completion note "G-2 implemented as D-1, D-2 (robot battery), D-10 (scope table)" (`WS05-monitor/tasks/T07-attribution-package.md`, "Gaps G-1 to G-6"). So acceptance changes text, not code.
- Optional type change (the only part that would be a second jump if chosen later): the alternative at line 279 "Per-node mappings for the four scalar fields (`Mapping[str, bool | None]`) ... changes four types and is a version bump with a migration of every consumer"; line 280: "The per-node alternative can be taken at M1 without changing the scope table." Fields: `system.diagnostics_ok`, `liveliness_ok`, `qos_deadline_missed`, `battery_low` (FM-GAP-LIVE, `fault-model.md:534`). Would also change the A4 recompute class (`evidence-channels.md:300-302`: the robot entry becomes a key removal, which a path mask cannot express). gab should confirm "declined" explicitly if the bump is meant to be the last.
- Tasks: WS02-T04, WS05-T07, WS05-T09, WS08-T04 (line 278).

### EV-05 ADR-049 (n): A4 sentence of the contract rule - PROPOSED (text)

- Source: `03-decisions.md:440` (n), status 443. Old (contract, `02-interfaces.md:598`): "with the channel removed, all `witness` fields and robot-derived `system` fields become `None`." New: the six wholly robot-derived fields become `None` (three `witness`, `nav_task_failed`, `manip_task_failed`, `battery_low`) and the four aggregate `system` fields (`node_lifecycle`, `diagnostics_ok`, `liveliness_ok`, `qos_deadline_missed`) are "recomputed over the device nodes".
- Today the contract sentence and `evidence-channels.md:273-302` (A4 mask) disagree; ADR-049 lists `#evidencevector` among the contracts to be bumped "text-only" (`03-decisions.md:442`). It should be folded into 0.2.0. The new fields add to the "unchanged" class (section 3).

### EV-06 ADR-040 (2): sign of `content_change` - PROPOSED

- Source: `03-decisions.md:334` (2) "define `content_change` as before minus after, the number of units released by the opening, so that a release is positive and a bounce is zero; this is what the generated traces already hold, and the table row changes" (status 337). Today the conventions table says "after minus before" (`evidence-channels.md:164`) and ADR-032 (line 270) repeats it. `attribution-rule.md:949` already points to ADR-040 (2) for the sign. EV-01 cannot be written in the contract without choosing.
- Consequence for tests: the bounce is zero in both conventions; a release is +1.0 in the generator (`measurement.py:198`), -1.0 under ADR-032 as written. WS10-T03 check 4 (`WS10-lab-demo/tasks/T03-dispenser-build.md`, "content change before and after") asks for two values, EC-OP-12 (`evidence-channels.md:535`).

### EV-07 ADR-040 (1): outcome `declined` - PROPOSED

- Source: `03-decisions.md:334` (1): a manipulate outcome `declined` does not make `system.manip_task_failed` True; "it makes it False for the window". No new field. The extractor currently has none: `src/ralmon/attribution/extract.py:573` ("'declined' has no evidence field (ADR-040 proposed)"). If accepted it amends D-5 (`evidence-channels.md`, "False only after a manipulate `success`") and the semantics of an existing field, so it belongs to the same contract text. `attribution-rule.md:950` (OP-AR-11) keeps refusal away from C1.

### EV-09 ADR-044: declared-channel set of the rule - PROPOSED

- Source: `03-decisions.md:363-369`. "The signature of `attribute` and of `Attributor`, `#evidencevector` and `#attribution` are not changed; what changes is the meaning of `None` for an undeclared channel inside the rule" (line 366). It addresses the rule through "canonical `group.field` paths", so it must be written against the 0.2.0 path list; with the new fields the exhaustive counts (18 / 2 / 18 / 90 combinations reaching C1) are no longer valid. Also: `count` still has no C1 without the dispenser evidence (line 368), which EV-01 now provides.

### EV-10 ADR-036: device capability profile - PROPOSED

- Source: `03-decisions.md:299-305`. No contract type changes. The capability list (`evidence-channels.md:214-216`) already contains `content_sensing` for the proposed dispenser channel; EV-03 needs a capability or a parameter (display resolution) and EV-02 uses the existing `seq`. Needed by the extractor (`DeviceProfile` / `DeviceCapabilities` in `extract.py`).

### EV-11 ADR-021: contract-gap register - PROPOSED

- Source: `03-decisions.md:171-185`. Its EvidenceVector line (175, "no field for dispenser content or dispense interval ..., `seq_gap_or_replay` mixing message loss (C2) and replay (C3), no clock-health field, undefined key of the evidence mapping, and no owner for building an `EvidenceVector`"). Of the five items: dispenser = EV-01 (accepted), seq = EV-02 (accepted), key = EV-04 (proposed), owner = closed (EC-GAP-5, `evidence-channels.md:511`), clock health = EV-12 (open).

### EV-16 ADR-065: minimum interval between doses - PROPOSED (dependency only)

- Source: `03-decisions.md:581-587`. Its alternative "encode the spacing as `interval_since_previous_ms` evidence for the attribution only, without a template" (line 585) reads the EV-01 field. If ADR-065 adds a template or a COUNT instance kind, `provenance.violated_template` has a new value (`TemplateId`, no field change) and the relevance map and DX-22/DX-27 are affected. No effect on the field list.

## 3. Open questions and declared limits (no ADR proposes a change)

| id | question | evidence | note |
|---|---|---|---|
| EV-12 | clock-health field | `evidence-channels.md:512` EC-GAP-6 "accepted as a declared limit: the field is not split and no clock-health field is proposed"; `attribution-rule.md:946` OP-AR-7 "ADR not proposed"; `threat-model.md:421` TM-GAP-TIME; `diagnosability-hazards.md:53` DX-19/DX-26; `fault-model.md:528` CG-10 | the only moment to add it without another bump is now; the monitor does not estimate offsets (T01 4.4) |
| EV-13 | device battery | `evidence-channels.md:513` EC-GAP-7 "declared limit"; `fault-model.md:543` OP-4 | `system.battery_low` is the robot battery (ADR-033 (3)) |
| EV-14 | rename `witness.robot_present` (it reads patient presence) | `evidence-channels.md:517` EC-GAP-11 "documentation note; no change proposed"; ADR-033 (4) "the name being kept" | a rename is breaking; now or never |
| EV-15 | witness quality (modality, confidence) | `threat-model.md:438` TM-OP-13 "No field is proposed here" | tesista proposal B does not ask for it (`tesista/proposta-B-percezione-witness.md:59`, outcome and `identity_confirmed` only) |
| - | verification failure with no attacker | `threat-model.md:440` TM-OP-15 | rule/hazard question, no field |
| - | cross-device as integrity or context | `threat-model.md:437` TM-OP-12, `attribution-rule.md:944` OP-AR-5 | rule question |
| - | `declined` has no field, refusal vs missed robot | `03-decisions.md:334, 336`; `extract.py:573` | handled by EV-07 semantics, not by a field |
| - | `system.node_lifecycle` for robot `unreachable` | `evidence-channels.md` EC-OP-16 | semantics, no field |

Not EvidenceVector changes (checked and excluded): TM-GAP-AUTH (closed by ADR-035, accepted, `#trace-schema` 0.2.0), TM-GAP-SEQKEY and TM-GAP-HIST (`threat-model.md:420, 422`, trace), FM-GAP-NODE (closed by ADR-035), EC-GAP-8/9/10 (ADR-036, ADR-035), EC-GAP-12 (PPG HR, no change), ADR-041/048/057-063/067/069/073 (no EvidenceVector content: only ADR-061 mentions `Detector.run(..., evidence)`, `#detector`), tesista proposal A (it consumes the DISPENSE keys of ADR-032, `proposta-A-...md:70, 80`, and asks the student to propose any extra field to the supervisor).

## 4. (a) Proposed final field list of EvidenceVector 0.2.0

### 4.1 Accepted items only (EV-01, EV-02; EV-03 as one field of undecided shape)

```
provenance        (2)  violated_template, template_kind
system            (9)  node_lifecycle, diagnostics_ok, liveliness_ok, qos_deadline_missed,
                       ble_link_quality, battery_low, nav_task_failed, manip_task_failed,
                       seq_gap                       # NEW (EV-02), bool | None, appended last
signal_quality    (3)  ecg_sqi, ppg_sqi, cuff_error_code
cross_device      (1)  pulse_vs_ecg_hr_diff
witness           (3)  robot_present, identity_confirmed, intake_observed
crypto_temporal   (3)  authenticated, seq_repeat      # RENAMED (EV-02, was seq_gap_or_replay),
                       timestamp_implausible          #   bool | None
dispenser         (2)  interval_since_previous_ms, content_change   # NEW group, last (EV-01)
                       #   int | None, float | None, both default None
```

Plus EV-03: one field, accepted in principle, shape to be fixed by gab. Suggested default (not decided): `signal_quality.<name>: bool | None` (the prototype name is `cuff.identical_repeat`, `likelihood-attribution.md:1168`).

### 4.2 Proposed items that would change the list if accepted

- EV-04 optional: `system.diagnostics_ok`, `liveliness_ok`, `qos_deadline_missed`, `battery_low` become `Mapping[str, bool | None] | None` (count unchanged, four types change).
- EV-12 / EV-13 / EV-14 / EV-15: each would add a field (12, 13, 15) or rename one (14); none is proposed by a source.
- EV-05, EV-06, EV-07, EV-08, EV-09, EV-10, EV-16: no field change.

## 5. (b) Counts

| variant | fields | non-provenance | groups |
|---|---|---|---|
| 0.1.0 (now) | 20 | 18 | 6 |
| EV-01 + EV-02 | 23 | 21 | 7 |
| EV-01 + EV-02 + EV-03 in an existing group (`signal_quality` 4) | 24 | 22 | 7 |
| EV-01 + EV-02 + EV-03 as its own group | 24 | 22 | 8 |

`03-decisions.md:270` says "twenty-two fields" (only the dispenser group); that figure predates ADR-034 and EV-03.

A4 classification of the 24-field variant (`evidence-channels.md:300`: None 6, recompute 4, unchanged 10): the new fields are all ward-side, hence "unchanged": 10 + `system.seq_gap` + 2 dispenser + EV-03 = 14. Totals 6 + 4 + 14 = 24. `EMBODIED_MASK_ALL` stays six paths; the claim "A4 does not mask `crypto_temporal` or `cross_device`" (`evidence-channels.md:304`) stays true; `system.seq_gap` must be listed as an exception to "system fields are partly robot-derived".

## 6. (c) Migration surface

Rule `01-conventions.md:76-78`: the ADR states old version, new version, affected tasks, migration; version bump in the same commit. Tasks citing `#evidencevector` in frontmatter: WS02-T01, T02, T03 (done), WS04-T07, T08 (done), WS05-T07 (done), WS05-T12 (blocked), WS07-T04, T05 (blocked), WS08-T04 (blocked).

Contract and documents
- `docs/plan/02-interfaces.md:545-598` (the block), `:28` (consumers), `:512` (`evidence_used`), `:700` (`/ralmon/robot_evidence`), `:720` (public names). Tests parse this block as text (see below), so the format of the new class and fields is load-bearing.
- `docs/models/evidence-channels.md`: field semantics table (`:109-130`), derivation table (`:170-196`), availability matrix (`:218-260`), A4 mask (`:273-302`), D-2/D-3/D-10/D-12 (`:393, 401, 459, 475`), gaps table (`:507-518`), CH-DISP row (`:98`), conventions rows `DISPENSE` (`:163-164`), parameters (`:379`), traceability. 22 occurrences of `seq_gap_or_replay`.
- `docs/models/attribution-rule.md`: 38 occurrences of `seq_gap_or_replay`; "twenty fields" (`:3`); enumeration check `:168-180` (87,351,696 combinations, per-template counts; "a template reads at most sixteen fields" `:166`); IE-2, W-08, W-15 cases; OP-AR-6, -10, -19 (`:945, 949, 959`); "Dependencies on proposed ADRs" (`:982-991`); invariants I2/I4 counts (`:301-303`).
- `docs/models/fault-model.md` (11 occurrences): tables rows `:103, 118-125`, coverage `:418`, FM-GAP list `:530-536`; `docs/models/threat-model.md` (12): `:63, 156-158, 242-246, 316, 328, 336-338`; `docs/models/diagnosability-hazards.md` (6): `:9, 52, 58, 61`; `configs/diagnosability.yaml` (12 occurrences of the old path, `proposed_evidence` at `:335, 372`, gap list `:60-82`, DX-11 note `:563-568`).
- Frozen formal documents that quote field paths: `docs/formal/07-alert-tuple-mapping.md:291` (TR-3, "twenty fields"), `docs/formal/09-worked-patient-day.md:109, 287, 300, 302`, `docs/formal/01-signals-sampling.md:168`, golden `docs/formal/golden/patient-day.yaml` (5 occurrences) and its test copy `tests/fixtures/monitor/golden_patient_day.yaml:220-239` (`evidence_used` lists the ten non-provenance paths by name). Frozen at M1 (ADR-043), so a rename needs an explicit note.
- `docs/plan/workstreams/WS02-threat-fault-model/README.md:47` (check "20 fields"), WS02-T03 (`:17, 43-44`), WS02-T06 (cells, `:23`), WS04-T07 (`:23, 58` test 18), WS05-T07 (`:41` test 1, `:50` test 7 "all 18"), WS07-T05 (`:25, 50-52` `EXPECTED_EVIDENCE`), WS08-T04 (`:40, 86`), WS05-T12, WS10-T03 (`event_schema`), and the PROGRESS/INDEX entries.

Source code
- `src/ralmon/attribution/evidence.py`: dataclasses `:41-100`, `EVIDENCE_PATHS` `:113`, `NON_PROVENANCE_PATHS` `:114-118`, `_paths()` hard-codes the six group classes (`:102-111`), docstrings "twenty" `:5, 113`, "eighteen" `:115`.
- `src/ralmon/attribution/rule.py`: `SEQ` `:146`, `_REST` `:150`, `_READS` `:154`, `_EX_CP` `:167`, `_ORDER` `:174`, IE-2 `:348-350`, `:405`, `:430`; docstring "eighteen" `:4`. The relevance map and the exclusion sets must say where `seq_repeat`, `seq_gap` and the new fields are read.
- `src/ralmon/attribution/extract.py`: sequence tracker `:354, 386`, `DISPENSER` scope `:82-106`, `declined` `:573`; new derivations for dispenser, `seq_gap`, EV-03.
- `src/ralmon/attribution/render.py`: per-field word tables `:69, 87, 233` (every field in both polarities is tested).
- `src/ralmon/attribution/__init__.py:20-47` and `tests/test_public_api.py:26-31` (the parts of the vector are public names: `DispenserEvidence` must be added to `__all__`, API table `02-interfaces.md:720`).
- `src/ralmon/benchmark/inject_c2.py:186-197` (`EVIDENCE_SIGNATURES`: `ble_dropout` path rename, `stuck_at` and `dispenser_bounce` currently `()`), `inject_c3.py:203-210` (`_C_SEQ`, `_PATH_ORDER`, replay/forgery signatures), `vocab.py` (DISPENSE keys), `measurement.py:198, 874, 998` (content sign, rounding), `builder.py:2453`, `labelling.py:180`, `injection.py:436, 1450`: `GroundTruthEvent.evidence_paths` is written into the benchmark sidecars, so benchmarks already generated carry the old path and must be regenerated or versioned.
- Research code that imports the path lists: `docs/benchmark/evidence/scripts/likelihood/{likelihood_attr.py:37,44-48,271, cells_table.py:5,32,42, subtype_model.py:26,100, test_likelihood.py:7,11}` (its `XSHORT`/`XZERO` extension fields become real fields).
- Not yet existing, will be written against the new list: `configs/attribution_likelihood.yaml` (WS02-T06, test 1 "every read field has a cell for every cause"), `src/ralmon/attribution/likelihood.py` (WS05-T12), `src/ralmon/eval/embodied.py` (WS08-T04), `ros2/` message `RobotEvidence` (WS05-T09, test 2 compares message fields with the dataclass).

Tests that count fields or enumerate paths (they fail the moment `02-interfaces.md` or `evidence.py` change)
- `tests/attribution/test_types.py:79` (`total == 20 == len(CONTRACT_PATHS)`), `:85-88` (`EVIDENCE_PATHS == CONTRACT_PATHS`).
- `tests/fixtures/attribution/__init__.py:31-60` (`CONTRACT_PATHS`, `NON_PROVENANCE_PATHS = CONTRACT_PATHS[2:]`), `:163` (group tuple), `strategies.py:24`, `trace.py:206`, `worked_cases.json` (49 occurrences of the old path), `build_worked_cases.py`.
- `tests/attribution/test_rule.py:189` (`len(EVIDENCE_PATHS) == 20`), `:99, 111, 129`; `test_invariants.py:62, 160, 185` (`len(NON_PROVENANCE_PATHS) == 18`), `:239`; `test_diagnosability.py:82, 94, 153` (skips `CH-DISP` outcomes); `test_extract.py` (22 occurrences); `test_render.py` (2).
- `tests/benchmark/test_inject_c2.py:2198-2201` (reads the contract text), `:2247` (`len(fields) == 20`), `:2248-2252` (`stuck_at == ()`); `tests/benchmark/test_inject_c3.py:130, 1665`; `tests/benchmark/test_ground_truth.py:1472`.
- Also hidden dependence: the signature tests compare `EVIDENCE_SIGNATURES` with the "EvidenceVector paths raised" column of `fault-model.md` (`test_inject_c2.py`, `fault_model_vocabulary`), so the fault-model tables must change in the same commit.
- Enumeration checks outside code: the 87,351,696 exhaustive check (`attribution-rule.md:168`, WS05-T07 completion note) and the C1-reachability counts of ADR-044 (`03-decisions.md:366`).

Mask and constants
- A4: `EMBODIED_MASK_ALL` (six paths) and `EMBODIED_MASK_WITNESS` (three) are unchanged by EV-01..03 (all ward-side); `evidence-channels.md:300-302`, WS08-T04 test 1 ("exactly the further robot-derived fields"). Changes only if EV-04 per-node mappings or a new robot-derived field is chosen. The "unchanged ten" figure is written in `evidence-channels.md:300`, WS08-T04 note (`:86`), EC-OP-5.
- `NON_PROVENANCE_PATHS` also drives the exhaustive checks and the Hypothesis strategies.

## 7. (d) Items that look contradictory

1. Stale counts. ADR-032 says WS05-T07 test 1 "counts twenty-two fields" (`03-decisions.md:270`); with ADR-034 and EV-03 the number is 23 or 24 (section 5). ADR-032 also promises that the append-last group with `None` defaults lets "existing constructors keep working"; ADR-034 removes a field and adds one in `system`, so constructors and `EVIDENCE_PATHS` order break anyway (only the dispenser group and EV-03 are additive).
2. Sign of `content_change`: ADR-032 (`03-decisions.md:270`) and `evidence-channels.md:164` say "after minus before" (release negative); ADR-040 (2) (`:334`, proposed) and the generator (`measurement.py:198`, +1.0 per release) say release positive; WS10-T03 wants "before and after" as two values (`evidence-channels.md:535` EC-OP-12). Needs EV-06 decided in the same commit.
3. "Silent faults raise no field". ADR-074's context (`03-decisions.md:660`, observation (i): `cuff_silent_bias`, `stuck_at`, `dispenser_bounce` "raise no evidence field, coverage table") and the prototype (`likelihood_attr.py`, `stuck_at` and `cuff_silent_bias` tagged "silent v1") predate amendment 2, which gives `stuck_at` (EV-03) and `dispenser_bounce` (EV-01) a field. The coverage table (`fault-model.md:395-418`; `stuck_at` row `:402`), DX-11 (`configs/diagnosability.yaml:563`), DX-04/05 notes, WS02-T06 test 3 (`test_silent_faults_do_not_zero_diagnostics_ok`) and WS02-T06's list of silent faults must be updated; only `cuff_silent_bias` remains silent for every reading.
4. `system.seq_gap` against `system.ble_link_quality`: the delivery ratio is 1.0 "exactly when no sequence value between the base and the top value of the window is missing" (`evidence-channels.md:114`, D-3), so `seq_gap` is nearly a function of the ratio; the two differ only in the span (cut-off versus top value of the window). The naive-Bayes table counts both ("one dropout raises three or four system fields", `likelihood-attribution.md:860`); the grouped variant of WS02-T06 (`T06:23`) names the old field. Decide the span of `seq_gap` and re-state the grouping.
5. `/ralmon/robot_evidence` carries "witness and system fields of `EvidenceVector`" (`02-interfaces.md:700`, WS05-T09 test 2 "witness and robot system fields"); `system.seq_gap` is a system field that is BLE-only (D-12), so the topic text must say "robot-derived `system` fields". Same for the new `dispenser` group (ward-side).
6. ADR-033 is bundled by text (`03-decisions.md:270, 286`) but is still `[DA-CONFERMARE]` (`:281`), and says "0.1.1 if adopted alone" (`:278`). Amendment 2 (`:666`) accepted ADR-032 and ADR-034 only. Also the survey path cited by ADR-032/034/074 is `docs/benchmark/evidence/evidencevector-0.2.0-survey.md` (`:666`), which does not yet exist; this file is the source.
7. Owner gap. Tasks that implement EV-01..03 in the extractor, rule and fixtures: WS05-T07 is `done` and says "The dispenser evidence group (ADR-032) ... not implemented"; WS05-T12 is `blocked` and its text reads "exactly the fields the hierarchical rule reads". WS02-T06 (ready, critical path) writes the cells for every field of the relevance map, so the field list must be frozen before it starts. No task currently owns the extractor/rule/test migration of 0.2.0.
8. DX-06 / DX-07 `conditional` on `CH-DISP` (`diagnosability-hazards.md:61`, `127`; WS05-T07 note "skip `CH-DISP` outcomes") become reproducible only if a `count` row reads the new fields (OP-AR-10, `attribution-rule.md:949`), but ADR-074 keeps the hierarchical table "as the reference rule" and does not say it gains rows. Without that decision the hierarchical baseline `ours-hier` ignores accepted evidence.
9. Contract rule vs A4 mask (`02-interfaces.md:598` against `evidence-channels.md:273-302`): "all robot-derived `system` fields become `None`" versus "recompute" for four aggregates. ADR-049 (n) fixes it but is proposed; a 0.2.0 text that restates the rule must settle it.
10. Per-opening versus per-instance (EV-01 detail 1) and device-reported versus derived interval (detail 2): the ADR (`:270`) says payload keys, the generator emits none, the prototype derives them. WS10-T03 and tesista proposal A (`proposta-A-...md:70`) already commit to the payload keys.
11. ADR-044 variant B and `attribution-rule.md:231` count "C1 combinations" with `count` unreachable; with EV-01 the count rows exist. Numbers 18/2/18/90 will change.
