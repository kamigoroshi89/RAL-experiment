# 08 Consistency review and freeze statement of the formalization (M1)

Document WS01-T08, part 1 of 2 (part 2 is `docs/formal/09-worked-patient-day.md`). It reviews the documents `01` to `07` of `docs/formal/`, their golden files and the parameter registry against every contract of `docs/plan/02-interfaces.md`, records a disposition for each apparent gap (CP1 to CP13 of the WS01 README and every new point found), checks the cross-document consistency, proposes the ADRs that a contract change needs, and states exactly what is frozen at milestone M1. It edits no document `01` to `07`, no golden file of T02, T04, T05 or T06, no registry file and no contract. It decides no clinical value. Validation in this project is technical and pre-clinical; nothing here is a clinical claim. It closes R1 weakness 1 at document level (complete, consistent formulas) and AE-2 (absent formalization).

## 1 Method

### 1.1 What was reviewed

- The contracts of `docs/plan/02-interfaces.md` at the versions they carry: Time and units, Trace schema, Parameter registry, Template, Signals, Verdict, Forecaster, Conformal calibrator, Monitor, Alert, EvidenceVector and Attribution are all version 0.1.0 (checked by grep on the file; the Package public API is 0.2.0 and is not a contract of the formalization). The review is against the exact text of each clause.
- The documents `docs/formal/01` to `07` and the golden files `templates.yaml` (26 cases), `ranking.yaml` (16), `verdicts.yaml` (24) and `conformal.yaml` (7).
- The registry file `configs/registry/hypertension.yaml` (version 0.2.0, 31 entries, 7 derived names, 3 unset names, `review_status` unreviewed) and its schema. Registry values are not part of the freeze (ADR-043).
- For the attributed causes of the worked day: `docs/models/attribution-rule.md` (WS02-T04, normative for kappa, merged), `docs/models/evidence-channels.md` and, for the replay and the cuff outage, `docs/models/threat-model.md` and `docs/models/fault-model.md`.
- `docs/formal/parameter-literature-proposal.md` (section "Findings for the formalization"), the decisions ADR-001 to ADR-044 of `docs/plan/03-decisions.md` (the status lines of ADR-027 to ADR-030 and ADR-041 to ADR-044 matter), and analisi §4.1, §4.5, §4.6, §6.

### 1.2 Procedure

1. Read the contracts and the seven documents; build the clause table of section 2.1 clause by clause; for each mismatch decide one of the four dispositions of section 1.3.
2. For each of CP1 to CP13 write the contract text, what the documents state and the disposition (section 2.2). Collect every point that is not CP1 to CP13 with its exact contract anchor (section 2.3, NP-1 and following).
3. Run the cross-document checks (section 3) with scripts that read the files, and re-derive golden values with an independent scratch implementation (not committed, kept under `/tmp`). The scratch implementation evaluates the template bodies by structural recursion with interval arithmetic from the text of `02`, `04`, `05` and `06`; it was validated first against the golden files (it reproduces 21 of 21 non-predictive cases of `verdicts.yaml` and 26 of 26 of `templates.yaml`) and then used for the worked day.
4. Check which proposals already exist as ADRs (026 to 030, 032 to 036, 040, 041, 044) and propose only what is missing (section 4).
5. Write the worked day (`09` and `golden/patient-day.yaml`), then the freeze marker (`docs/formal/README.md`).

### 1.3 Dispositions

Each row of sections 2.1 to 2.3 carries exactly one of: **consistent** (the documents state what the contract says); **clarified in docs** (the documents state it, the contract text stays and the reading is confirmed here, section 5.3); **ADR proposed** (the contract text must change or an accepted or proposed ADR already changes it: the column names the ADR and its status); **reported to another workstream** (the point is handed to the named task, which includes a reopened WS01 task). A point that is handed over and also stays open in the freeze is listed in section 5.4 as OPF-n.

### 1.4 Rules followed

- A defect in a document or a golden file is not patched here (check 4 of the task): section 3.10 names the owning task and says whether the defect blocks the freeze. None blocks it. The statement `FROZEN: yes` is written only because of that finding; it would not have been written otherwise.
- `docs/plan/02-interfaces.md` is not edited and no contract version is bumped (`git diff --quiet -- docs/plan/02-interfaces.md` exits 0). The proposed changes are in ADR-045 to ADR-050 of `03-decisions.md`.
- Wording follows the glossary of `01-conventions.md` section 7. The four claim words of that section are used nowhere in this review, except as quoted in the claim table of `07` section 3.1.

## 2 Contract-by-contract table

### 2.1 Clauses

The quotations are short and exact. "Docs" are sections of `docs/formal/` (`01` to `07`) unless another file is named.

| Id | Contract clause | What the documents state | Disposition | ADR or owner |
|---|---|---|---|---|
| C-01 | `#time-and-units` rule 1: "The monitor evaluates at discrete steps of period `T_s` ... Sparse measurements are held piecewise-constant between samples; events are one-sample impulses" | `01` sections 3.1 to 3.4: grid `t_k = k T_s`, hold from the first step at or after the sample, impulses by the ceiling rule with the multiplicity kept; adds that `T_s` divides the day (M2) | consistent | CG-12 (validity of the configuration) is a check for WS05-T04 |
| C-02 | rule 2: "Point events with an exact window `O[W,W]` are evaluated as `O[W, W+T_s]`" | `01` section 3.7 and `02` section 1.5: the strings of SCHED and RESP carry the widened antecedent; the reference semantics is one instance per anchor, evaluated once at its decision step; on the aligned grid the widening adds a second true step that decides nothing; string and instance agree under (A1), (A2) and, for RESP, (A3) | clarified in docs | section 5.3 rule R1; no ADR (CG-2, TG-6, and the question handed over in `05` section 11.2) |
| C-03 | rule 3: "Two clocks exist per sample ... Verdict latency is measured against `t_device_ms` after reordering with a bounded reorder buffer" | `01` sections 4.1 to 4.3: watermark `t_{k_up} + D`, late inputs unused and counted; `05` section 6.1 (requirement R-late) | consistent | wording of R-late: ADR-049 |
| C-04 | rule 4: "Normalised robustness is dimensionless; raw robustness carries the unit declared in the template" | `02` section 2.6, `04` section 2.1: mmHg, ms, dose; `DIMENSIONLESS` is used by no template | consistent | |
| C-05 | `TimeMs = int # milliseconds since the start of the patient-day trace` | a warm-up prefix needs negative times (`01` CG-11); the alert time of an instance decided after 24:00 exceeds 86,400,000 (`07` AH-21; RESP of the 21:02 dose has decision step 1442) | ADR proposed | ADR-046 (new) |
| C-06 | `#trace-schema` `ObservedDay` (one patient-day) with `#monitor` `run_offline(day, plan, config, calibrator, forecaster)` | `01` section 5.5 and `05` sections 2.1, 7.5: state is carried between days by a warm-up prefix (H-hist); an instance may be decided after 24:00 (M6, Lemma 12b); `run_offline` has no input for the history (CP7) | ADR proposed | ADR-029 (accepted: semantics), ADR-046 (new: API) |
| C-07 | `EventKind`: MEASUREMENT, DISPENSE, INTAKE, SCHEDULE_TICK, NODE_STATE, ROBOT_TASK, DEVICE_ERROR | `01` section 2.2 (CG-5): `auth`, `presence` and `cuff_health` travel as `Sample`, `day_end` is generated, `meas`, `dispense`, `intake` and `sched_tick` come from events; the worked day follows this reading | clarified in docs | WS04-T01 and WS05-T02 confirm; payload keys: ADR-035 (proposed) |
| C-08 | rule 1: "a true C1 is a violation of φ_CP evaluated on the *latent* trace ... The monitor never receives `LatentDay` or `ground_truth`" | every document evaluates the observed trace only; `06` section 4.1 defaults `sigma_true` to the observed-completed trace; the worked day keeps the intended causes outside the monitor input | consistent | |
| C-09 | `Sample.seq` and `Event.seq`: "device sequence number (None if the device provides none)" | `01` section 3.4: an event that repeats an accepted `(source, seq)` "is a duplicate and is not counted again"; `05` section 2.1 accepts every input that is not late and not future-stamped, without that rule: the two documents disagree on whether a duplicate measurement enters the accepted trace (NP-1) | reported to another workstream | WS01-T05 and WS01-T01 reopen (OPF-6); the worked day avoids the case (H-W9) |
| C-10 | `hold_last`: "Piecewise-constant interpolation on the monitor grid" returning `Sequence[float]` | `01` sections 3.2, 3.5: before the first sample the value is `NaN`, read as unknown (CP12); an availability mask next to the array carries "channel unavailable" (CG-6) | clarified in docs | NaN part closed here; mask encoding: WS05-T02 |
| C-11 | `#signals` rule: "`PRESENCE` and `INTAKE` ... exist only while the robot is co-located; their absence is reported through the `EvidenceVector`, not as a value of zero" | `01` sections 2.5, 3.5 and `05` section 3.5: an unavailable channel is an open position, never 0; an INT instance of a robot-absent dispense is PENDING with a marker unless `auth` decides it (V-INT-1, V-INT-2); the worked day uses both | consistent | |
| C-12 | `DOSE_COUNT`: "derived: dispenses in the trailing 24 h" | `01` section 5.1: events in `(t - 24 h, t]`, multiplicity kept | consistent | the window against dose timing of 1 h: finding F1, OPF-1 |
| C-13 | `MEAS_COUNT`: "derived: measurements in the current day" | `01` section 5.2 defines it; no template reads it (CP2) | consistent | CP2 |
| C-14 | `INFLATION_MS`: "cuff inflation duration" | `02` section 4.6 reads it in SYS; the rationale of `cuff_inflation_min` in registry 0.2.0 says that device manuals give the whole cycle (finding F4) | reported to another workstream | WS01-T01, WS04-T06, WS10-T02 (OPF-4) |
| C-15 | the seventeen `SignalId` values; "derived signals are causal and streaming" | all seventeen appear in `01` section 2.1 (checked, section 3.3); `01` section 5: O(1) per input; `bp_pre` is captured per instance | consistent | |
| C-16 | `Template` fields: id, kind, `formula_past_time`, signals, params, unit, `scale_param`, `priority_param`, `max_verdict_latency_param`, `creates_robot_obligation` | `02` section 3.1: one row per `TemplateId` with every field; the kinds match the decomposition (`01` section 6.1) | consistent | |
| C-17 | `formula_past_time`: "past-time STL string, syntax fixed by WS01-T02 (RTAMT-compatible)" | `02` section 1.2: a grammar with the instance term `age` (section 1.4); ADR-013 outcome C: the evaluator is custom and 4 of the 7 strings translate mechanically | ADR proposed | ADR-045 (new; NP-2, TG-5) |
| C-18 | `Template.unit` and `scale_param`: one each | `02` section 2.1: exactly one margin dimension per template; every other atom is a guard equal to +inf or -inf; `unit` and `scale_param` refer to the margin (CP11) | clarified in docs | one sentence in ADR-049 |
| C-19 | `max_verdict_latency_param`: "registry entry: bound on time to a definitive verdict (Delta2 or W plus T_s)" | `02` section 3.2 and `03` section 2.3: a derived name `max_latency_<id>` equal to `B + step_ms`, computed by the loader | ADR proposed | ADR-047 (new; TG-3, OP-3) |
| C-20 | `creates_robot_obligation`: "True for RESP and SCHED (analisi §4.1 item 4)" | `02` section 5.5: True for SCHED, RESP and INT (analisi §10 objection 3) (CP1) | ADR proposed | ADR-045 (new); interplay with ADR-026 (proposed) |
| C-21 | `CarePlan.schedule`: "measurement and dispense ticks" as `Sequence[TimeMs]` | `02` section 5.4 (TG-1): the checks F2 to F5 and the creation of the SCHED and INT obligations need the kind of each tick | ADR proposed | ADR-045 (new) |
| C-22 | `TemplateInstance.param_values: Mapping[str, float]` | `03` section 5.3 and OP-6, `07` AH-14: a key that differs from the registry value must lie in an approved range of `overrides:`; the contract does not say whether the mapping holds all values or only the deviating ones | ADR proposed | ADR-047 (new) |
| C-23 | `normalise`: "sigma_tilde = clip(sigma_raw / scale, -1.0, 1.0). scale > 0." | `04` sections 2.1, 2.4: `+-inf` maps to `+-1.0`; `ValueError` for a scale that is not positive and finite and for a NaN input | ADR proposed | ADR-049 (new; TG-10, OP-7) |
| C-24 | `rank_alerts`: "template priority first (clinician-assigned), then sigma_tilde ascending within a priority" | `04` section 4.2: key `K0` adds `t_ms` and `instance_key`; priority 1 is the highest (CP5); the scope is one care plan (OP-6); the order K1 (VIOLATED before PREDICTED_VIOLATION) is undecided | ADR proposed | ADR-028 (accepted), ADR-049 (direction, scope), ADR-050 (new: K1) |
| C-25 | `#template` rules: "never a `min` over raw values in different units; only normalised values are compared ... Normalisation by the width of a conformal interval is forbidden" | `04` sections 3.2, 6 and `02` section 6.2; counterexample RK-6; the worked day compares only normalised values | consistent | |
| C-26 | `#parameter-registry` rule: "no numeric clinical constant appears in `src/ralmon` outside the registry loader. Illustrative values from analisi §4.1 may be loaded only if `rationale` states 'illustrative, unverified'" | `03` sections 1.2, 2.2: the schema makes the rationale rule mechanical; on the file 0.2.0: 31 entries, every rationale ends with the string, every `reviewed_by` is null (checked, section 3.1) | consistent | the values are outside the freeze (ADR-043) |
| C-27 | `RegistryEntry.value: float` (durations are `DurationMs`, priorities `int`) | `03` section 2.6: stored as float, cast by unit and name with an integrality check (CP10) | ADR proposed | ADR-047 (new) |
| C-28 | `PhysioBounds(signal, lower, upper)`, without rationale or reviewer | `03` sections 2.3, 2.5: two entries `bound_<signal>_lower` and `bound_<signal>_upper` carry the provenance; `bounds` composes them (CP10) | ADR proposed | ADR-047 (new) |
| C-29 | `ParameterRegistry.get(name)` and `version()` | `03` section 2.5: `get` resolves entries, derived names, and raises `UnsetParameterError` for a declared unset name (OP-2); `load_registry(path=None, *, step_ms=None)` (OP-4); the extra top-level key `window_parameters` (OP-5) | ADR proposed | ADR-047 (new) |
| C-30 | "Values live in ... `hypertension.yaml` ... and are reviewed by the clinician (WS00-T03)" | ADR-043 (accepted): the freeze runs with `clinician_review: pending`; registry 0.2.0 holds literature proposals, `review_status: unreviewed` | consistent | WS00-T07 stays a pre-submission item |
| C-31 | `#verdict` semantics 1: "VIOLATED iff `sigma_interval.hi < 0`; SATISFIED iff `sigma_interval.lo > 0`; otherwise PENDING" | `05` section 3.4: tie rule (a closed instance with `lo = hi = 0` is SATISFIED); the residual `lo = 0 < hi` stays PENDING (CP3-b); section 2.5: after an out-of-domain sample a definitive record can carry `hi >= 0` (OP-T05-13) | ADR proposed | ADR-029 (accepted), ADR-048 (new: text of rule 1) |
| C-32 | semantics 2: "`sigma_hat + q_{1-alpha} < 0` ('likely') or `sigma_hat - q < 0` ('possible')" | `06` sections 4.5, 5.7: the variant "possible" uses the lower quantile `q^lo_alpha` (Proposition 1b); the symmetric form is valid only under symmetry (CP4) | ADR proposed | ADR-030 (proposed) |
| C-33 | semantics 3: "A definitive verdict is computed only from the measured prefix. The forecast never produces VIOLATED or SATISFIED" | `05` Lemma 9 and section 1.2 | consistent | |
| C-34 | semantics 4: "Maximum latency of a definitive verdict is a property of the template ... and is reported" | `05` section 7.2 and Lemma 13: `verdict_latency_bound_ms = max_latency_<id> + reorder_delay_ms` (CG-4) | clarified in docs | wording in ADR-049 |
| C-35 | "Allowed transitions: PENDING → PREDICTED_VIOLATION → VIOLATED; PENDING → VIOLATED; PENDING → SATISFIED; PREDICTED_VIOLATION → SATISFIED" | `05` sections 4.1, 4.2 (T0 to T9): exactly these edges; self-loops are refinements; no edge back to PENDING; the worked day uses PENDING → PREDICTED_VIOLATION → SATISFIED | consistent | |
| C-36 | `VerdictRecord.decided_at_ms` and `pending_until_ms` ("anchor + Delta2 or W") | `05` section 3.1: `pending_until_ms = t_{k_up(a)} + B` on every record (CG-3); the record has no field for `undecidable`, `guard_failed`, the path or the predicted severity (CP6, OP-T05-3) | ADR proposed | ADR-029 (accepted), ADR-048 (new) |
| C-37 | `RobustnessInterval`: "unknown future values replaced by physiological bounds" | `05` section 2.2: infinite endpoints allowed, `lo <= hi`, no NaN, normalised by `N_s(+-inf) = +-1`; serialisation `"-inf"` in JSON and `-.inf` in YAML (CP12) | ADR proposed | ADR-029 (accepted) |
| C-38 | `RhoKind`: MEASURED "P(sigma_true < 0 \| measurement) under a device error model", PREDICTED "conformal, 1 - alpha_star", DETERMINISTIC "event-log predicate, rho = 1" | `06` sections 2.2, 2.3: exact guarantee and assumption strings; the kind follows the deciding sub-formula; `Rho.alpha` of a predicted alert is the configured level | ADR proposed | ADR-049 (new; `06` section 10 items 2 and 4) |
| C-39 | `VerdictRecord.rho: Rho \| None` | `06` section 1.2: None for SATISFIED and PENDING; in the worked day rho is null for all 21 SATISFIED records and for the PENDING ones | consistent | |
| C-40 | `#conformal-calibrator` rule 1: "Calibration unit is the patient episode, never the time step. Split by patient." | `06` sections 4.1, 4.2; minimum size section 4.7 | consistent | |
| C-41 | rule 2: "Coverage is marginal over the population, not conditional on the patient" | `06` section 6.1; `07` section 3.1 row 7 | consistent | |
| C-42 | rule 3: "Nonconformity score is one-sided, `R = sigma_true - sigma_hat`; Proposition 1 (WS01) states `P(alert emitted and sigma >= 0) <= alpha`"; `quantile(alpha)`: "one-sided q_{1-alpha}" | `06` section 5.1: Proposition 1, with `{sigma >= 0}` equal to the final verdict SATISFIED by the tie rule; the lower quantile is needed for "possible"; exact ranks need the decimal literal (section 4.4) | ADR proposed | ADR-030 (proposed) |
| C-43 | rule 4: "Every model update ... triggers recalibration ... the monitor refuses to use a calibrator older than the model version" | `06` section 7; the version token has no field (`06` section 10 item 13) | reported to another workstream | WS05-T06 (proposes its ADR) |
| C-44 | `CalibrationEpisode.sigma_true`: "normalised robustness of the completed trace (latent or measured)" | `06` section 4.1: default observed-completed; latent-completed is a benchmark-only oracle (item 11) | ADR proposed | ADR-049 (new) |
| C-45 | `#alert` `sigma_norm`: "normalised robustness in [-1, 0) for a violation" | `07` section 1.5: the bound that the emitting rule compared with zero, `N_s(hi)` of the first VIOLATED record (frozen) and `clip(sigma_hat + q, -1, 1)` for a predicted alert, both in `[-1, 0)` (CP5); `04` section 4.6 (point forecast, `[-1, 1]`) is superseded (NP-10) | ADR proposed | ADR-041 (proposed) |
| C-46 | `priority`: "clinician-assigned template priority" | `04` section 4.3: 1 is the highest, ascending, integers >= 1 | ADR proposed | ADR-049 (new) |
| C-47 | `kappa`: "attributed cause; UNDETERMINED is a valid output"; `verdict`: "VIOLATED or PREDICTED_VIOLATION" | `07` section 1.7 (CP13): kappa of a predicted alert is UNDETERMINED by definition, `AttributionRule.attribute` stays independent of `state`; confirmed by `attribution-rule.md` | ADR proposed | ADR-041 (proposed) |
| C-48 | `Alert(Detection)`: `t_ms`, `label`, `score` | `07` section 1.3: `t_ms` is an event time, `label` equals `kappa`, `score` equals `-sigma_norm` | ADR proposed | ADR-041 (proposed) |
| C-49 | `Explanation`: "xi: specification-level traceability" with `subformula_path`, `evidence_used`, `text` | `07` sections 1.3, 3.2 (TR-1 to TR-4): the path carries the guard marker; `evidence_used` lists the decisive fields in precedence order | consistent | carrier fields: ADR-048 |
| C-50 | semantics: "σ̃ ... ρ ... They are complementary" | `07` section 3.1 row 3 and `06` section 1.3: near a limit rho falls while the severity tends to zero | consistent | |
| C-51 | semantics: "A cascade effect ... carries `caused_by` and is not shown as a separate top-level alert" | `07` section 1.8 and `attribution-rule.md` cascade rules 1 to 11; the worked day R3 and R4 (PD-ALT-02 under PD-ALT-01) | consistent | re-issue wording: NP-9, reading confirmed in section 5.3 |
| C-52 | semantics: "Ordering of alerts uses `rank_alerts`" | `09` section 3.4: five alerts in the current set, four top-level | consistent | |
| C-53 | `MonitorConfig`: `step_ms`, `reorder_delay_ms`, `predictive`, `alpha`, `variant`, `registry_version` | `01` section 3.6 and CG-12 (validity: `T_s > 0`, `T_s` divides `T_day`, `D >= 0`, alignment at plan load); `06` section 6.2 (`alpha` is allocated over the tests); `clock_skew_max_ms` is a registry name (`03` OP-7), so `MonitorConfig` is unchanged | clarified in docs | WS05-T04 implements the validity checks |
| C-54 | `advance`: "causal: uses only inputs with `t_device_ms <= t_ms - reorder_delay_ms`" | `01` section 4.2; `05` Lemma 1 and section 6.1: lateness is decided from the two clocks of the input alone (R-late) | clarified in docs | wording in ADR-049 (OP-T05-7) |
| C-55 | monitor rule: "processing cost per sample is O(number of active template instances) and the bound is reported" | `05` section 6.4: O(active instances) per finalised step and O(1) per instance; per sample only if every step receives an input | clarified in docs | wording in ADR-049 (OP-T05-15) |
| C-56 | "the `Attribution` step turns violated records into alerts" | `07` section 1.7, AH-2: "violated" is read as "claiming a violation" (VIOLATED or PREDICTED_VIOLATION) | ADR proposed | ADR-041 (proposed), wording in ADR-049 (OP-T07-4) |
| C-57 | `Monitor.load`: "verifies plan signature if present" | `07` section 4.5 and `02` section 5.4: load checks F1 to F7, exact registry version, `plan_version` not lower, signature required in a ward deployment (AH-17); they are requirements of the documents and not contract text | reported to another workstream | WS05-T03, WS05-T04 |
| C-58 | `run_offline(day, plan, config, calibrator, forecaster)` | CP7: no input for the history | ADR proposed | ADR-046 (new) |
| C-59 | `verdict_latency_bound_ms(template)` | as C-34 | clarified in docs | ADR-049 |
| C-60 | `#evidencevector` rule: "`None` (channel unavailable) is never converted to a negative observation" | `attribution-rule.md` I3, I4 and the relevance map; the worked day: robot fields are None at 21:00 and 21:02 and the witness fields are never read as denied | consistent | |
| C-61 | `EvidenceVector`: no field for dispenser content change or interval | CP8: rows 6 and 7 of the analisi §4.5 matrix depend on it; `attribution-rule.md` AD-10, W-06, W-07: `count` has no C1 branch | reported to another workstream | WS02 (ADR-032 proposed) |
| C-62 | `#attribution` default rule: "1. Integrity evidence present → C3_INTEGRITY. 2. Otherwise system evidence present → C2_SYSTEM. 3. Otherwise a violation with coherent channels → C1_CLINICAL. 4. Otherwise ... UNDETERMINED" | `attribution-rule.md` decision table (rows 1 to 8): "coherent channels" is the exclusion set of each template (AD-8); in the worked day A4 is C1 (row 5), A1 and A2 C2 (row 4), A5 C3 (row 1), A6 UNDETERMINED (row 8) | clarified in docs | the rule document is normative (section 5.3) |
| C-63 | `Attributor.attribute_all`: "propagates root causes over cascades" | cascade rules of `attribution-rule.md`; `attribute_all` returns the current set; PD-ALT-02 is folded under PD-ALT-01 | consistent | |
| C-64 | analisi §4.5 matrix rows used by the worked day: row 1 (hypertension), row 8 with authentication (replay), rows 6 and 7 (double take, bounce) | A4 agrees with row 1; A5 agrees with row 8 under authentication; A6 differs from rows 6 and 7 (the matrix says distinguishable if the dispenser measures content, the rule abstains because no field carries content) | reported to another workstream | WS02 (CP8, ADR-032 proposed) |

### 2.2 CP1 to CP13

| CP | Anchor and contract text | What the documents state | Disposition | Where decided |
|---|---|---|---|---|
| CP1 | `#template` `creates_robot_obligation`: "True for RESP and SCHED (analisi §4.1 item 4)" | `02` section 5.5: True for SCHED, RESP and INT, from analisi §10 objection 3 | ADR proposed | ADR-045 (new): the comment and the value; ADR-026 (proposed) is the open question of the INT form |
| CP2 | `#template`, `#signals`: `MEAS_COUNT` exists, `TemplateId.COUNT` is "dose count limit and day-end count obligation", `RobustnessUnit` has no member for a count of measurements | `02` section 4.4: not adopted (no unit, two margin dimensions in COUNT, duplicates the SCHED instances); `meas_min_day` is neither a template parameter nor a registry entry; R11 of the scenario is omitted | clarified in docs | no contract change; ADR-045 records the decision "not adopted"; adopting it later needs a new `TemplateId` and unit |
| CP3 | `#verdict` semantics 1: "VIOLATED iff `sigma_interval.hi < 0`; SATISFIED iff `sigma_interval.lo > 0`" (strict) | `05` section 3.4: tie rule for a closed instance with `lo = hi = 0`; `lo >= 0` (CP3-b) recorded and not adopted | ADR proposed | ADR-029 (accepted); the new text of rule 1 is in ADR-048 (new) |
| CP4 | `#verdict` semantics 2 ("possible": `sigma_hat - q < 0`) and `#conformal-calibrator` (`quantile` is the upper one-sided quantile) | `06` sections 4.5, 5.7: the lower quantile `q^lo_alpha` (Proposition 1b); the symmetric form needs symmetry | ADR proposed | ADR-030 (proposed), unchanged by this review |
| CP5 | `#alert` `sigma_norm`: "in [-1, 0) for a violation"; `priority`: "clinician-assigned template priority" | `07` section 1.5: both verdicts in `[-1, 0)`; `04` section 4.3: 1 is the highest; `04` section 4.5: K1 | ADR proposed | ADR-041 (proposed: range), ADR-049 (new: direction), ADR-050 (new: K1) |
| CP6 | `#verdict`: no state or field says that the deadline elapsed and the verdict is undecidable because an evidence channel is unavailable | `05` section 3.5: the instance stays PENDING after `pending_until_ms` with the marker `undecidable: <reason>:<signal>`; no fifth state | ADR proposed | ADR-029 (accepted); the field is in ADR-048 (new) |
| CP7 | `#trace-schema` `ObservedDay`, `#monitor` `run_offline(day, ...)`: no state from the previous day | `01` section 5.5, `05` sections 2.1, 7.5 (H-hist, early decision, warm-up prefix) | ADR proposed | ADR-029 (accepted: semantics), ADR-046 (new: API and negative `TimeMs`) |
| CP8 | `#evidencevector`: no field for dispenser content or interval; `#attribution` rule 3 "a violation with coherent channels → C1" | `attribution-rule.md` decided it: AD-10 and W-06 — `count` has no exclusion set that can be satisfied, so the double take at 21:02 is UNDETERMINED (row 8, reason insufficient, `evidence_used` empty); the default rule's "coherent channels" is read as the exclusion set (AD-8). The worked day abstains at 21:02 (PD-ALT-06) | reported to another workstream | WS02: ADR-032 (proposed: dispenser group of `EvidenceVector`), `attribution-rule.md` OP-AR-10 |
| CP9 | no contract for the robot obligation record | `02` section 5.2: nine-field record; section 5.3 creation rules; section 5.4 load checks | ADR proposed | ADR-045 (new): `#robot-obligation` 0.1.0 |
| CP10 | `#parameter-registry` `RegistryEntry.value: float` against `DurationMs` and `int` priorities; `PhysioBounds` without provenance | `03` sections 2.3, 2.5, 2.6, 7 (OP-1 to OP-6) | ADR proposed | ADR-047 (new) |
| CP11 | `#template`: one `unit` and one `scale_param` per template | `02` section 2.1: one margin dimension, the other atoms are guards; failed guard gives -inf, normalised -1 and the marker | clarified in docs | one sentence in ADR-049; no signature change |
| CP12 | `#signals` `hold_last` before the first sample; `#verdict` infinite interval ends | `01` section 3.5: NaN read as unknown; `05` section 2.2: infinite endpoints, `lo <= hi`, serialisation | clarified in docs | NaN: closed here; intervals: ADR-029 (accepted) |
| CP13 | `#monitor` "turns violated records into alerts" against `Alert.verdict` "VIOLATED or PREDICTED_VIOLATION": kappa of a predicted alert undefined | `07` section 1.7: UNDETERMINED by definition, rule not evaluated, definitive alert supersedes; `attribution-rule.md` section Predicted violations agrees (replaced, not duplicated, no provisional kappa); worked day PD-ALT-03 | ADR proposed | ADR-041 (proposed), wording of "violated" in ADR-049 |

### 2.3 New points

Points found by this review that are not CP1 to CP13. Each carries the exact contract anchor.

| NP | Exact contract anchor | Finding | Disposition | Owner or ADR |
|---|---|---|---|---|
| NP-1 | `#trace-schema` `Sample.seq`, `Event.seq`; `#monitor` `push_sample`, `push_event` | `01` section 3.4 says that a repeated accepted `(source, seq)` is a duplicate "not counted again" (a statement about counters); `05` section 2.1 defines the accepted trace as the inputs that are not late and not future-stamped. Whether a duplicate measurement with a fresh stamp opens a RANGE instance or fills a SCHED window is not stated. The threat model treats a naive replay as late (unused) and an informed replay as continuing `seq`, so the documents never need the answer; the scenario row R6 did (it asked for a repeated `seq` with a fresh stamp) | reported to another workstream | WS01-T05 and WS01-T01 add the rule (OPF-6); the day uses the informed replay instead |
| NP-2 | `#template` `formula_past_time` comment "(RTAMT-compatible)" | the strings of SCHED and INT use the instance term `age`, which is not a `SignalId` and not defined in `01`; ADR-013 outcome C made the evaluator custom, so the comment is stale | ADR proposed | ADR-045 (new) |
| NP-3 | `#template` `Template` | the monitor needs per template the anchor signal, the deadline offset `B` and the guard names (TG-2); the dataclass has no field for them | clarified in docs | they follow from `02` sections 2.1 and 3.2 and stay in the WS05 implementation table; the contract is not extended |
| NP-4 | `#template` `TemplateId.INT` comment "a dispense is backed by robot-observed presence or authenticated event" | `02` sections 3.1 and 4.7 do not say that INT is evaluable only when a witness channel or `auth` is available; `01` section 2.4 and `05` section 3.5 (V-INT-1) say it; found by WS02-T04 | clarified in docs | section 5.3 rule R3; the owning text is `02` (WS01-T02), a wording defect that does not block (section 3.10, D9) |
| NP-5 | `#alert` (no patient or care-plan identifier); `#attribution` `Mapping[str, EvidenceVector]` (key undefined) | `Alert.xi.instance_key` is unique within a care plan only (`04` OP-6, `07` OP-T07-8, `evidence-channels.md` D-1) | ADR proposed | ADR-028 (accepted: protocol), ADR-033 (proposed: key of the mapping) |
| NP-6 | `#parameter-registry` (version 0.1.0 text) | statements about "registry 0.1.0" or about names being `unset` remain in `03` sections 3, 6, 7, `04` sections 3.1, 3.3, OP-10, `05` sections 2.7, 7.2, `06` section 3.3, `07` parameter table; the file is 0.2.0 with 31 entries and 3 unset names | reported to another workstream | WS01-T03 refreshes the inventory (OPF-13); each statement is labelled with its version, so none is false |
| NP-7 | `#template` `rank_alerts` (golden `ranking.yaml` RK-1, RK-4) | the two cases hold the value -0.7 at `t_ms` 35,460,000, the refined value of a refinement record, not an emitted alert (`07` OP-T07-17); the order is unchanged | reported to another workstream | WS01-T04 relabels or regenerates (OPF-14) |
| NP-8 | `#alert` `Explanation.evidence_used`: "EvidenceVector fields that decided kappa" | `07` section 1.9 column A lists "none asserted" and section 3.5 example 1 says "in the channels that were available"; the rule lists the ten denied fields of the exclusion set and requires every channel to be available | reported to another workstream | WS01-T07 aligns the wording (OPF-15); the worked day uses the rule |
| NP-9 | `#alert` semantics, cascade bullet | `07` section 1.4 item 3 says a re-issue for a link changes only the link field and "the other fields are those of the first issue"; `Explanation.text` is derived from `root_cause_of` (count sentence), so the text of a re-issued root differs in that sentence | clarified in docs | section 5.3 rule R4 confirms the reading of `attribution-rule.md` OP-AR-20 |
| NP-10 | `#alert` `sigma_norm`, `#template` `rank_alerts` | `04` sections 4.6, 4.7 and OP-4, OP-9, OP-14, OP-15 give the predicted severity as the point forecast with range `[-1, 1]` and the SCHED severity as -1; `05` section 3.7, `06` section 2.4 and `07` section 1.5 decide `N_s(hi)` and `clip(sigma_hat + q)` | clarified in docs | section 5.3 rule R2 (precedence); wording refresh OPF-15 |
| NP-11 | `#trace-schema` day structure | `01` section 5.5 item 5 says open instances at the closing step are "PENDING at trace end, never as SATISFIED"; `05` section 7.5 item 2 decides early satisfaction (Lemma 12b) | clarified in docs | section 5.3 rule R2; the labeller of WS04 applies the `05` rule; ADR-046 states it |
| NP-12 | `#template` `TemplateId.COUNT` "dose count limit and day-end count obligation" | an unscheduled dose violates the 24 h limit and, by `05` Lemma 12, also satisfies the day-end minimum at once (worked day PD-REC-27); with finding F2 the pair limit and minimum can mask or invent a violation | clarified in docs | stated, not hidden (section 5.3 rule R6); OPF-1, OPF-2 |
| NP-13 | `#alert` `sigma_norm` for a SCHED alert | at the deadline `hi = -T_s` (normalised -T_s / s) if the next tick is visible after the deadline and `hi = -inf` (normalised -1) otherwise (`07` AH-23); the plan check on tick spacing is optional | reported to another workstream | WS01-T02 may add a check F8 on tick spacing (OPF-11) |
| NP-14 | `#parameter-registry` `PhysioBounds` | `bound_inflation_ms_*` and `bound_dose_count_*` are declared although `05` section 2.7 does not use them; registry 0.2.0 gave values to three of the four | reported to another workstream | WS01-T03 (registry decision after the freeze; not a contract point) |
| NP-15 | `#alert` `verdict` ("VIOLATED or PREDICTED_VIOLATION") | an `Alert` has no closed state, so the closure of a predicted alert (false predictive alarm) is carried by the `VerdictRecord` (OP-T07-5) | reported to another workstream | WS05-T09, WS07 (OPF-12) |
| NP-16 | `#alert` `verdict` | an instance PENDING after its deadline with the marker `undecidable` raises no alert (OP-T07-14, OP-AR-18) | reported to another workstream | WS05-T09, WS02 (OPF-12) |
| NP-17 | `#template` (instances of RANGE and SYS), `#signals` `hold_last` | `02` section 1.5 states (A0) for measurement events (at most one event per grid bin); `05` section 2.1 needs at most one sample of each of `bp`, `cuff_health` and `inflation_ms` per bin, because the grid keeps one value per bin; two events, or a standalone sample later in a bin, make the instance read the grid value and not the payload of its own event (OP-T05-12) | reported to another workstream | WS04-T06 and WS01-T02 (OPF-10); the worked day satisfies it (H-W4) |

## 3 Cross-document checks

All checks were run by scripts that read the files (scratch under `/tmp/t08doc`, not committed). Counts are exact.

### 3.1 (a) Registry names

The command of the task, run verbatim over `docs/formal/0*.md` (documents `01` to `09`), printed:

```
not in registry: meas_min_day
not in registry: priority_param
not in registry: scale_param
```

None of the three is a defect. `meas_min_day` is deliberately not registered (WS01-T02 adopted no measurement-count obligation, CP2; it is an F0 row used "only if" the obligation is adopted); `priority_param` and `scale_param` are field names of the `Template` dataclass picked up by the pattern, not registry entries. The literal reading of README acceptance 3 ("every name is an entry, a derived bound or a declared unset name") is not met by `meas_min_day`, `step_ms` and `reorder_delay_ms`: the last two are monitor configuration (`MonitorConfig`), not clinical registry names, as `03` section 3.3 explains. The check is adapted to this reading: it excludes `meas_min_day`, `priority_param` and `scale_param` and expects `step_ms` and `reorder_delay_ms` to be absent from the pattern (they never match it). Adapted command and output:

```
for n in $(grep -hoE '`(scale|priority|max_latency|bound)_[a-z0-9_]*`|`(bp_band_low|bp_band_high|bp_hold_threshold|hold_lookback|dose_max_24h|dose_min_day_end|int_window|delta1|delta2|delta_resp|sched_window|cuff_inflation_min|cuff_error_sd|meas_min_day)`' docs/formal/0*.md | tr -d '`' | sort -u | grep -vxE 'meas_min_day|priority_param|scale_param'); do
  grep -q "$n" configs/registry/hypertension.yaml || echo "not in registry: $n"; done
(no output; the pattern and the loop are those of the task, with the filter added after sort -u)
```

Further facts read from the file: registry version 0.2.0, `review_status: unreviewed`, 31 entries, 7 derived names, 3 unset names (`priority_sys`, `priority_int`, `bound_dose_count_upper`); every entry has `reviewed_by: null` (acceptance 3: no entry has `reviewed_by` other than null before WS00-T07); every `rationale` ends with "illustrative, unverified" (the rule of `03` section 2.2; 31 of 31 entries). The names of `02` section 3.3 that are not registry names are `meas_min_day` and `step_ms`.

### 3.2 (b) Units

The unit of each template in `02` section 3.1 against the unit of its `scale_<id>` entry in the registry file and against `expected.unit` of the golden cases:

| Template | Unit in `02` | `scale_<id>` unit in the registry | `templates.yaml` cases | `verdicts.yaml` cases |
|---|---|---|---|---|
| range | mmHg | mmHg | 5 of 5 agree | |
| sched | ms | ms | 4 of 4 agree | 11 of 11 agree (V-SCHED-1 to 5b, V-PRED-1 to 3, V-LATE-1, V-LATE-2) |
| hold | mmHg | mmHg | 4 of 4 agree | |
| count | dose | dose | 3 of 3 agree | 4 of 4 agree (V-COUNT-1 to 4) |
| resp | mmHg | mmHg | 4 of 4 agree | 6 of 6 agree |
| sys | ms | ms | 3 of 3 agree | |
| int | ms | ms | 3 of 3 agree | 3 of 3 agree |

Totals: 26 of 26 template cases and 24 of 24 verdict cases carry the unit of their template; the seven `scale_<id>` units match. The cases of `patient-day.yaml` carry `unit` too and are checked by the same script (32 of 32).

### 3.3 (c) Symbols

The identifiers of the seven strings of `02` section 3.1 are: the `SignalId` values, the registry working names of section 3.3, `step_ms` (`T_s` of `01` section 1.4), the keyword `inf`, and `age`. All seventeen `SignalId` values of the contract appear in `01` section 2.1 (17 of 17) and all seven `TemplateId` values in `02` section 3.1 (7 of 7). The one identifier that `01` does not define is `age`: it is the instance term of `02` section 1.4 (the time between the evaluation step and the step of the witnessing event), listed as TG-5 of `02` and as NP-2 here. It is not a defect: `02` says so and ADR-045 proposes the comment that names it.

### 3.4 (d) Fixture registry F0

The F0 table of the WS01 README has 26 rows; the `fixture_registry` section of `templates.yaml` has 26 rows. Compared cell by cell (name, value, unit, origin): 0 differences. No other golden file uses a different value: the `f0_rows` of `verdicts.yaml` (24 cases), `ranking.yaml` (16) and `conformal.yaml` (7) were compared name by name with F0 and give 0 differences; the cases of `templates.yaml` use `step_ms` 60000 and `reorder_delay_ms` 0 only. `patient-day.yaml` lists 29 F0 rows under `f0_rows` and the same check gives 0 differences.

### 3.5 Corrections to the scenario table (worked day)

The scenario table R1 to R11 is a target. The corrections are made in the rows of `09` section 1.5 and summarised here.

| Row | Correction | Why (documents that decide) |
|---|---|---|
| R1, R4, R9 | none; additions only (raw intervals in full, `[10, 92]` for the two late RESP records) | `05` sections 2.3, 3.1 |
| R2 | kept; the explicit `presence` 0.0 sample at 06:59 and the day-end COUNT instance (PENDING, `[-1, +inf]`) are added | `02` section 4.7 (presence is a level; golden G-INT-1); `05` section 3.3 |
| R3 | kept; the alert value -0.0333 is stated to depend on `H_i > k_d` (next tick 12:00 visible after the deadline); kappa C2 with the single decisive field `system.liveliness_ok` | `05` section 2.3, `07` section 1.5 and AH-23; `attribution-rule.md` W-11 |
| R5 | kept with four corrections: predicted `sigma_norm` -0.2433 (bound, not point forecast); `Rho.alpha` 0.2 with alpha* 0.1; C1 needs the ten denied channels of the exclusion set (not only "none asserted"), valid under the full device profile (H-W6); the closed predicted alert leaves the current set | `07` section 1.5, `06` section 10 item 2, `attribution-rule.md` AD-8 and W-01, `07` section 1.4 |
| R6 | **corrected**: the 20:32 sample is an informed replay (fresh metadata, `seq` continues) in an authenticated deployment; kappa C3 by `crypto_temporal.authenticated` (row 1), not by a repeated `seq`; the scenario's duplicate-`seq` replay depends on NP-1 and is not used | `01` section 3.4 against `05` section 2.1 (NP-1); `threat-model.md` class replay; `attribution-rule.md` W-08 |
| R7 | kept; the day-end COUNT instance is PENDING with `[0, +inf]` (residual case CP3-b) | `05` section 3.4 |
| R8 | kept; kappa UNDETERMINED is row 8, reason insufficient (AD-10, W-06); the day-end COUNT instance is SATISFIED at 21:02 by early satisfaction | `attribution-rule.md`; `05` Lemma 12 |
| R10 | kept; the current set has five alerts (the folded RESP@07:00 first among priority 2 by the `t_ms` tie-break); the top-level list has the four of the target | `04` section 4.2, `attribution-rule.md` cascade rule 9 |
| R11 | omitted | `02` section 4.4 (CP2) |

### 3.6 (e) Independent re-derivation of golden values

The scratch implementation was written from the text of `02`, `04`, `05` and `06`, validated and run on the golden files. Outcome: every value agrees. Re-derived values (the first twenty are written here with the calculation; the full counts follow):

| # | Golden case | Hand calculation | Golden value | Agrees |
|---|---|---|---|---|
| 1 | G-RANGE-2 (`templates.yaml`) | min(152 - 110, 140 - 152) = min(42, -12) = -12 mmHg; -12 / 20 | -12 mmHg; -0.6 | yes |
| 2 | G-RANGE-5 | min(200 - 110, 140 - 200) = -60; -60 / 20 = -3, clipped | -60; -1.0 | yes |
| 3 | G-HOLD-3 (refined form) | latest held bp 90: 90 - 100 = -10; -10 / 20 | -10 mmHg; -0.5 | yes |
| 4 | G-SCHED-3 | measurement visible at step 591, k_d = 570: (570 - 591) * 60000 = -1,260,000 ms; / 1,800,000 | -1,260,000; -0.7 | yes |
| 5 | G-RESP-3 | max(150 - 145 - 10, 150 - 138 - 10) = max(-5, 2) = 2; 2 / 20 | 2 mmHg; 0.1 | yes |
| 6 | G-INT-1 | witness age (420 - 418) * 60000 = 120,000; 300,000 - 120,000 = 180,000; / 300,000 | 180,000 ms; 0.6 | yes |
| 7 | G-COUNT-1 | c_d = 3 (steps 420, 1260, 1262 in the window); 2 - 3 = -1; / 1 | -1 dose; -1.0 | yes |
| 8 | G-SYS-2 | 9,000 - 30,000 = -21,000; / 30,000 | -21,000 ms; -0.7 | yes |
| 9 | V-SCHED-1 (`verdicts.yaml`) | step 550, earliest acceptable measurement visible at 551: (570 - 551) * 60000 = 1,140,000; / 1,800,000 | hi 1,140,000; 0.6333 | yes |
| 10 | V-RESP-2 | M = 150 - 145 - 10 = -5; hi = 150 - 50 - 10 = 90 | [-5, 90] | yes |
| 11 | V-RESP-4 rho (Phi by `math.erf`) | Phi(5 / (6 * sqrt 2)) = Phi(0.5893) | 0.7221551 | yes |
| 12 | V-INT-3 | no witness: -inf; normalised -1 | [-inf, -inf] | yes |
| 13 | N-3 (`ranking.yaml`) | -60 / 20 = -3, clip | -1.0 | yes |
| 14 | N-5 | -1,260,000 / 1,800,000 = -0.7 | -0.7 | yes |
| 15 | RK-1 order | keys (1, -0.3), (2, -0.6), (3, -0.7): priority decides | hold, range, sched | yes |
| 16 | RK-5 K0 and K1 | K0 by sigma: -0.5 before -0.2; K1 puts VIOLATED first | both orders | yes |
| 17 | C-1 (`conformal.yaml`) upper quantile at 0.2 | k = ceil(10 * 0.8) = 8; 8th smallest score | 0.09 | yes |
| 18 | C-2 sigma_hat = -0.15 | -0.15 + 0.09 = -0.06 < 0; m = 8 scores below 0.15; alpha* = 2/10; rho = 8/10 | emitted; 0.8 | yes |
| 19 | C-4 exact rank, alpha 0.41, n = 99 | j = floor(100 * 41 / 100) = 41, k = 100 - 41 = 59 | rank 59 | yes |
| 20 | C-6 band at bp 104 (Phi by `math.erf`) | Phi(1) + Phi(-6) = 0.8413447461 + 0.0000000009866 | 0.8413447470551 | yes |

Counts. `templates.yaml`: 26 of 26 cases (sigma, normalised value and Boolean verdict). `ranking.yaml`: 10 of 10 normalisation cases (N-7 has two values, N-8 and N-9 are the errors) and 6 of 6 ranking cases (the `K0` orders of RK-1 to RK-3, the raw order of RK-4, `K0` and `K1` of RK-5, the forbidden width order of RK-6). `verdicts.yaml`: 24 of 24 cases (the 21 non-predictive cases in every field: state, raw and normalised interval, `decided_at_ms`, `pending_until_ms`, `t_eval_ms`; V-PRED-1 to V-PRED-3 by the interval record of the measured prefix and the conformal module). `conformal.yaml`: 7 of 7 cases (C-1 ranks and quantiles, C-2 five predictions, C-3 both forms of the variant "possible", C-4 two exact ranks, C-5 minimum sizes and allocation, C-6 six rho values by `math.erf`, C-7 the margin of the counter). No mismatch, so no defect was found in a golden value. `patient-day.yaml`: 32 of 32 records, 6 of 6 alerts, the ranking, the five evidence vectors with the decision table and the cascade conditions (`09` sections 2 and 3).

### 3.7 (f) Glossary sweep

Over `docs/formal` (documents `01` to `09`, the README and the goldens): the pattern of the task for the terms that the glossary of `01-conventions.md` section 7 forbids for tiers, modules, the back-end and Physical AI finds no occurrence (grep exit 1); the claim words of the same section occur only inside quoted rows of the claim table of `07` section 3.1, and the check of the task prints nothing. This review and `09` do not spell the forbidden terms at all, so that the same greps stay clean. "Robustness" is used for STL semantics, the normalised value is called severity; DISPENSE and INTAKE are kept apart; "violation" names the violated sub-formula; C2 and C3 are never called violations.

### 3.8 (g) Numeric clinical values

A scan of the lines of `01` to `07` that contain a number followed by mmHg, doses, mg or bpm (41 lines) found 0 lines without a label (F0, FIXTURE-ONLY, illustrative, unverified, analisi, golden case, workshop, example). None of the values that only registry 0.2.0 holds (7.5 mmHg for `delta_resp`, 260 mmHg, 12.5 mg) occurs in `01` to `07`. The documents `08` and `09` and `patient-day.yaml` use F0 values only and say so. This is a heuristic scan plus the labelling rule of each document; it is not a proof that no unlabelled number exists.

### 3.9 The five findings of the WS01-T09 hand-over

Each finding was verified against `02-templates.md`, `01-signals-sampling.md` and `parameter-literature-proposal.md` (section "Findings for the formalization"). No value is chosen.

| # | Finding | Verification | Disposition | Owner and effect on claims |
|---|---|---|---|---|
| F1 | `dose_count` is a trailing 24 h window while a dose may be given 1 h early or late: three on-time doses can fall within 22 h and violate `dose_max_24h` | True of the library. `01` section 5.1 defines the window as `(t - 24 h, t]` with no tolerance and `02` section 4.4 compares the count with `dose_max_24h` at each dispense. Checked with the scratch evaluator: doses at 22:00, then 07:00 and 20:00 of the next day (the last 22 h after the first) give margins +1, 0, -1 dose, so the third dose is a violation. The documents never claim a tolerance | open point OPF-1 | WS01-T02 with the clinician (WS00-T07). A COUNT alert is a statement about the count in 24 h, not about non-compliance; results that rest on COUNT must say so; WS04 adherence delays of up to the dose tolerance can generate it |
| F2 | A dose withheld by the hold rule, or refused, violates `dose_min_day_end` | True. HOLD (`02` section 4.3) says not to dispense below the threshold; COUNT day-end (`02` section 4.4) needs `dose_min_day_end` dispenses; the trace has no event kind for a documented withheld dose (`#trace-schema` `EventKind`). A compliant hold therefore yields an unmet day-end obligation | open point OPF-2 | WS01-T02, WS02 (cause), WS04 (benchmark). The alert reads "obligation unmet", never "care plan violated"; a remedy (a recorded withheld dose that counts) is a contract change and needs its own ADR after the clinician's view. NP-12 notes the converse: an excess dose satisfies the minimum |
| F3 | A single pre/post pair has a difference SD of about 16.8 mmHg against `delta_resp` 7.5 mmHg | The documents model device error only: `06` section 3.1 assumptions (a) to (d) and section 3.2 item 3 (SD of the difference is `cuff_error_sd * sqrt 2`, 8.49 mmHg for the F0 value and 11.3 for the 0.2.0 value of 8 mmHg). The 16.8 figure includes the biological variability between readings 1 to 2 h apart, which the template does not model: RESP is a statement about two readings, and the MEASURED rho of RESP is conditional on the adequacy of the declared device error model | clarified in docs (this review) and open point OPF-3 | Frozen reading: a RESP verdict and its rho are statements about the two readings, not about drug response. WS04-T04 and WS04-T10 and WS08 report the false-violation rate of RESP on the latent trace of a responder; WS01-T06 may add the sentence to `06` section 1.3. No claim of drug-response detection |
| F4 | The `sys` template reads the inflation duration while device manuals give the whole cycle | True. `01` section 2.1 and the contract define `inflation_ms` as the inflation duration; the 0.2.0 rationale of `cuff_inflation_min` (15000 ms) is a measurement time found in a manual, "the whole cycle, not the inflation alone" | open point OPF-4 | WS01-T01 (signal table), WS04-T06 (what the generator emits), WS10-T02 (what the lab cuff reports). Either the meaning of the signal changes to the cycle duration (an ADR, a change of meaning of a `SignalId`) or the threshold is set from the inflation alone; the choice depends on the device. SYS results are stated as conditional on what `inflation_ms` carries |
| F5 | The BLE clock-skew bound with a daily resynchronisation (about 44 s) is close to the 60 s step | `01` section 4.4 makes `skew_max` an assumption with consequences: window edges accurate to `T_s` plus up to `2 * skew_max` across two devices, a future stamp beyond `skew_max` is not used (M4). The statements hold for any `skew_max`; the value is a parameter. With 44 s the edge accuracy is 60 + 88 = 148 s, about 2.5 steps. The 0.2.0 value `clock_skew_max_ms` 1000 ms is, by its own rationale, a median error and not a bound | clarified in docs and open point OPF-5 | WS07-T03 and WS10 measure the bound on the hardware; WS01-T03 revises the registry value after the freeze. Timing claims in the paper must carry `T_s + 2 * skew_max` with the measured bound |

### 3.10 Defects found in `01` to `07` and in the goldens

No document and no golden file is edited here. None of the defects below makes the freeze statement false; each is a stale or incomplete statement that the freeze statement corrects by a precedence rule (section 5.3 rule R2) or lists as an open point (section 5.4).

| # | Anchor | Defect | Owning task | Blocks the freeze? |
|---|---|---|---|---|
| D1 | `03` sections 3.1, 3.2, 6, 7 (counts "17 entries, 17 unset names"; the review sheet) | The inventory describes registry 0.1.0; the file is 0.2.0 with 31 entries and 3 unset names. `03` section 5.1 notes the change but the inventory is not refreshed | WS01-T03 | no (NP-6, OPF-13; the registry is outside the freeze) |
| D2 | `04` sections 3.1, 3.3, 4.6, 4.7 and OP-4, OP-9, OP-10, OP-14, OP-15 | Sections about the severity of a predicted alert (point forecast, range `[-1, 1]`) and of a SCHED alert (-1) and the registry 0.1.0 table are superseded by `05` section 3.7, `06` section 2.4, `07` section 1.5 | WS01-T04 | no (NP-10, OPF-15) |
| D3 | `05` sections 2.7, 7.2 | "unset in `hypertension.yaml`" for `sched_window` and the bounds; `bound_bp_*` "seeded from analisi §4.7" (values changed in 0.2.0) | WS01-T05 | no (OPF-13) |
| D4 | `06` section 3.3 | `cuff_error_sd` "unset"; the file has 8.0 in 0.2.0 | WS01-T06 | no (OPF-13) |
| D5 | `07` parameter table and section 1.9 column A, section 3.5 example 1 | "registry 0.1.0"; `xi.evidence_used` "none asserted" and "channels that were available" against the rule's ten denied fields (NP-8) | WS01-T07 | no (OPF-15) |
| D6 | `01` section 5.5 item 5 | "PENDING at trace end, never as SATISFIED" contradicts the early-decision rule of `05` section 7.5 item 2 (NP-11) | WS01-T01 | no (rule R2) |
| D7 | `01` section 3.4 against `05` section 2.1 | duplicate `(source, seq)`: neither the acceptance rule nor the counter rule says whether a duplicate measurement enters the trace (NP-1) | WS01-T05 and WS01-T01 | no (OPF-6; the worked day does not use it) |
| D8 | `golden/ranking.yaml` RK-1, RK-4 | the fixtures hold the refined value -0.7 of a refinement record at `t_ms` 35,460,000 and not an emitted alert; the order is correct (NP-7) | WS01-T04 | no (OPF-14) |
| D9 | `02` sections 3.1, 4.7 | no evaluability condition for INT (found by WS02-T04); stated in `01` section 2.4 and `05` section 3.5 (NP-4) | WS01-T02 | no (rule R3) |

The check "D7 blocks nothing" rests on the facts that no golden case, no lemma and no statement of the freeze depends on the rule, and that the replay row of the worked day was changed to avoid it. If a later task needs the rule, WS01-T05 is reopened.

### 3.11 (h) Open points of `01` to `07`

Every "Open points for WS01-T08" section of `01` to `07` is resolved or carried: the 125 items below are all the items of those sections (16, 18, 15, 16, 25, 16 and 19). The table of inherited questions in `05` section 11.2 restates items that appear here under their own ids (CG-2, CG-3, CG-4, CG-14, TG-4, TG-8, TG-11, TG-12, OP-9, OP-14, OP-15 of `04`, and the prediction instants) and is covered by them. Codes: **RES** resolved inside the document, the adopted reading stands; **CLR** clarified in this review (sections 2, 3, 5); **ADR-n** covered by ADR n (existing: section 4.2; new: section 4.1); **DS** downstream task note, the named task file adapts and no formal text changes; **OPF-n** carried open point of the freeze (section 5.4); **REG** a registry or value matter outside the freeze (ADR-043); **CLIN** a clinical question for WS00-T07, pending. A code with two parts means both apply.

| Document | Item | Topic | Code | Where or owner |
|---|---|---|---|---|
| `01` | CP7 | state carried between days, warm-up prefix | ADR-029, ADR-046 | semantics accepted; API proposed |
| `01` | CP12 | value before the first sample; infinite endpoints | CLR, ADR-029 | C-10; NaN is a float, no signature change |
| `01` | CG-1 | alignment applies to window parameters only | RES, ADR-047 | `window_parameters` list of 03 |
| `01` | CG-2 | widening and the string form | CLR | C-02, section 5 rule R1; no ADR |
| `01` | CG-3 | deadline is `t_{k_up(a)} + B` | RES | 05 section 3.1 confirms |
| `01` | CG-4 | event-time against end-to-end latency bound | RES, ADR-049 | 05 section 7.2 |
| `01` | CG-5 | trace form of `auth`, `presence`, `cuff_health`, `day_end` | DS | WS04-T01, WS05-T02; ADR-035 |
| `01` | CG-6 | availability mask next to `hold_last` | DS | WS05-T02 |
| `01` | CG-7 | direction of the phi_INT window | RES | 02 section 4.7; ADR-026 pending (OPF-8) |
| `01` | CG-8 | wording of the task example W3 | RES | the document uses 20:59:59.500; nothing to freeze |
| `01` | CG-9 | witness unavailable at the deadline | ADR-029 | marker `undecidable`; ADR-048 field |
| `01` | CG-10 | one Boolean for late, future-stamped and replay inconsistencies | DS | WS02 (EC-GAP-6) |
| `01` | CG-11 | negative `TimeMs` in a warm-up prefix | ADR-046 |  |
| `01` | CG-12 | validity of `MonitorConfig` | DS | WS05-T04 (C-53) |
| `01` | CG-13 | duplicates when `seq` is absent or repeated | OPF-6 | NP-1 |
| `01` | CG-14 | persistent counter violation | RES | 05 section 3.8, 07 section 1.4: one alert per instance |
| `02` | CP1 | `creates_robot_obligation` for INT | ADR-045 |  |
| `02` | CP2 | measurement-count obligation | CLR | not adopted; ADR-045 records it |
| `02` | CP9 | robot obligation record | ADR-045 |  |
| `02` | CP11 | one unit and scale per template | CLR, ADR-049 | C-18 |
| `02` | TG-1 | `CarePlan.schedule` has no tick kind | ADR-045 |  |
| `02` | TG-2 | anchor, deadline offset and guard names not in `Template` | CLR | kept in the WS05 implementation table (NP-3) |
| `02` | TG-3 | `max_verdict_latency_param` is a derived name | ADR-047 |  |
| `02` | TG-4 | graded lateness after the decision step | RES | 05 section 6.5 refinement records; 07 section 1.5 frozen alert |
| `02` | TG-5 | the term `age` and the tool string | ADR-045 | NP-2 |
| `02` | TG-6 | string against reference semantics for SCHED and RESP | CLR | C-02, section 5 rule R1; no ADR |
| `02` | TG-7 | HOLD refined form | ADR-045, CLIN | recorded in ADR-045 (f); clinical confirmation OPF-7 |
| `02` | TG-8 | INT direction and forward witness | OPF-8 | ADR-026 proposed |
| `02` | TG-9 | `presence` as a held level | DS | WS02, WS05-T02; the day uses an explicit 0.0 sample (H-W8) |
| `02` | TG-10 | `normalise` and infinities | ADR-049 |  |
| `02` | TG-11 | ties and strictness | ADR-029 | tie rule |
| `02` | TG-12 | COUNT limit stated with a trigger | RES | 05 section 3.8 |
| `02` | TG-13 | RANGE during drug onset | CLIN | OPF-7 |
| `02` | TG-14 | fixture choices in the golden file | RES | fixture arithmetic, labelled |
| `03` | OP-1 | types of `RegistryEntry.value` and `PhysioBounds` | ADR-047 | CP10 |
| `03` | OP-2 | `UnsetParameterError`, `RegistryError`, helper methods | ADR-047 |  |
| `03` | OP-3 | derived latency names | ADR-047 | TG-3 |
| `03` | OP-4 | `load_registry` signature | ADR-047 |  |
| `03` | OP-5 | top-level `window_parameters` | ADR-047 | required key |
| `03` | OP-6 | meaning of `param_values` | ADR-047 |  |
| `03` | OP-7 | `cuff_error_sd` and `clock_skew_max_ms` source of truth | RES | 06 section 3.3; both are registry names, `MonitorConfig` unchanged (C-53) |
| `03` | OP-8 | bounds beyond `bp` | REG | NP-14; 05 section 2.7 does not use them |
| `03` | OP-9 | version compatibility | ADR-047 | exact match kept |
| `03` | OP-10 | `meas_min_day` | RES | CP2: not adopted |
| `03` | OP-11 | fixture registry before the review | RES | ADR-027 (accepted) |
| `03` | OP-12 | names that T04 to T06 still needed | RES | no new name; `cuff_error_sd` and the bounds exist |
| `03` | OP-13 | `review_status` granularity | RES | rule kept; the file is `unreviewed` |
| `03` | OP-14 | registry file is not signed | DS | WS02, WS13 governance |
| `03` | OP-15 | no paper excerpt | RES | ADR-037 |
| `04` | OP-1 | range of `sigma_norm` | ADR-041 | CP5 |
| `04` | OP-2 | direction of `priority` | ADR-049 | CP5 |
| `04` | OP-3 | VIOLATED before PREDICTED_VIOLATION (K1) | ADR-050 |  |
| `04` | OP-4 | `sigma_norm` of a predicted alert | ADR-041 | 07 section 1.5 decides; 04 section 4.6 superseded (NP-10) |
| `04` | OP-5 | failed guard against clipped value, marker | ADR-041, ADR-048 | marker travels in the path |
| `04` | OP-6 | tie-break and typing of `rank_alerts` | ADR-028 | accepted |
| `04` | OP-7 | error types | ADR-049 |  |
| `04` | OP-8 | raw robustness for ablation A3 | DS | WS08-T03 |
| `04` | OP-9 | frozen `sigma_tilde`, graded lateness | ADR-041 | frozen at emission |
| `04` | OP-10 | state of the registry (0.1.0) | REG | NP-6 |
| `04` | OP-11 | clip loses order beyond the scale | RES | limitation, reported |
| `04` | OP-12 | references | DS | WS03 |
| `04` | OP-13 | floating point | DS | WS05-T03 tests |
| `04` | OP-14 | upper-end rule for a VIOLATED alert | ADR-041 | 05 section 3.7, 07 section 1.5 |
| `04` | OP-15 | `predicted_sigma_norm` | ADR-041, ADR-048 | carrier field |
| `04` | OP-16 | test-name conflicts of WS05-T03 | DS | WS05-T03; ADR-028 |
| `05` | CP3 | tie rule | ADR-029 | accepted; text in ADR-048 |
| `05` | CP6 | unavailable channel at the deadline | ADR-029, ADR-048 |  |
| `05` | CP7 | carry-over, instances after the closing step | ADR-029, ADR-046 |  |
| `05` | CP12 | infinite endpoints | ADR-029 |  |
| `05` | OP-T05-1 | grid slack against device-time slack (V-LATE-2) | RES | grid slack kept; finer resolution is a clinical choice |
| `05` | OP-T05-2 | closure condition, `lo >= 0` refinement | ADR-029 | tie rule adopted, `lo >= 0` not adopted |
| `05` | OP-T05-3 | fields the record does not have | ADR-048 |  |
| `05` | OP-T05-4 | downstream tasks to adapt | DS | WS05-T04, WS05-T08, WS01-T07 text |
| `05` | OP-T05-5 | unset bounds for counters and durations | REG | NP-14 |
| `05` | OP-T05-6 | emission rule | RES | section 6.5 adopted |
| `05` | OP-T05-7 | requirement R-late | ADR-049 |  |
| `05` | OP-T05-8 | early VIOLATED by the bounds | OPF-9 | default early, dependence logged |
| `05` | OP-T05-9 | INT form and ADR-026 | OPF-8 |  |
| `05` | OP-T05-10 | forecast clipping, designated instants | RES | 06 sections 4.1, 4.3 confirm |
| `05` | OP-T05-11 | horizon of the graded SCHED value, tick spacing | OPF-11 | AH-23, NP-13 |
| `05` | OP-T05-12 | stronger (A0): one sample per bin | OPF-10 | NP-17 |
| `05` | OP-T05-13 | definitive record after an out-of-domain sample | ADR-048 |  |
| `05` | OP-T05-14 | instances with `k_d > K` | CLR, ADR-046 | NP-11: 05 section 7.5 supersedes 01 section 5.5 item 5 |
| `05` | OP-T05-15 | complexity per sample or per step | ADR-049 |  |
| `05` | OP-T05-16 | prediction once or designated instants | DS | WS05-T08; 06 section 4.3 covers both |
| `05` | OP-T05-17 | `pending_until_ms` on every record | DS | WS04-T10; 05 section 3.1 confirmed |
| `05` | OP-T05-18 | replay of goldens through `StreamingMonitor` | DS | WS05-T04, WS05-T02, WS05-T08 |
| `05` | OP-T05-19 | refinement records and `update` | RES | 07 section 1.5 (c): not a changed alert |
| `05` | OP-T05-20 | RESP fixture of WS09-T03 | DS | WS09-T03 |
| `05` | OP-T05-21 | evaluator cost model of WS05-T04 | DS | WS05-T04 |
| `06` | item 1 | lower quantile for the variant "possible" (CP4) | ADR-030 | proposed |
| `06` | item 2 | `Rho.alpha` is the configured level | ADR-049 |  |
| `06` | item 3 | rho of the variant "possible" | RES | same value, guarantee is Proposition 1b |
| `06` | item 4 | `PredictedViolation.rho` when not emitted | ADR-049 |  |
| `06` | item 5 | severity of a predicted alert | ADR-041 |  |
| `06` | item 6 | kind of rho for VIOLATED records, SYS | RES | SYS DETERMINISTIC; alternative needs a registry entry |
| `06` | item 7 | prediction instants and allocation of the level | RES | DS WS05-T08 |
| `06` | item 8 | clipping of the forecast | RES |  |
| `06` | item 9 | downstream tasks contradicted | DS | WS05-T06, WS05-T08 |
| `06` | item 10 | guarantee string of the adaptive calibrator | DS | WS05-T06, WS08-T05 |
| `06` | item 11 | which completed trace defines `sigma_true` | ADR-049 |  |
| `06` | item 12 | `fit` and `quantile` both take a level | DS | WS05-T06 |
| `06` | item 13 | model-version token | DS | WS05-T06 |
| `06` | item 14 | source of truth of the device error | RES | 06 section 3.3 |
| `06` | item 15 | confirmed from T05 | RES |  |
| `06` | item 16 | deviations from the task text | RES |  |
| `07` | CP5 | range and direction | ADR-041, ADR-049 | CP5 |
| `07` | CP13 | kappa of a predicted alert | ADR-041 | confirmed by attribution-rule.md |
| `07` | OP-T07-1 | severity of a VIOLATED alert | ADR-041 |  |
| `07` | OP-T07-2 | severity of a predicted alert | ADR-041 |  |
| `07` | OP-T07-3 | carrier, degenerate "possible", K1 | ADR-048, ADR-050 | DS WS05-T08 |
| `07` | OP-T07-4 | word "violated" in `#monitor` and `#attribution` | ADR-049 |  |
| `07` | OP-T07-5 | closure of a predicted alert | OPF-12 | NP-15 |
| `07` | OP-T07-6 | carrier and syntax of the path | ADR-048 |  |
| `07` | OP-T07-7 | predictive variant not carried by the alert | DS | WS05-T08, renderer reads `MonitorConfig.variant` |
| `07` | OP-T07-8 | identity beyond one care plan | ADR-028 | NP-5 |
| `07` | OP-T07-9 | meaning of `t_ms` | ADR-041 |  |
| `07` | OP-T07-10 | which alerts feed which metrics | ADR-041, DS | WS08-T01 |
| `07` | OP-T07-11 | frozen alert, displayed lateness | ADR-041, CLIN | OPF-7 |
| `07` | OP-T07-12 | governance of plans | DS, ADR-049 | WS05-T03, WS05-T04, WS07; wording (b) in ADR-049 |
| `07` | OP-T07-13 | FHIR and BPMN mapping | DS | WS03 verifies element names |
| `07` | OP-T07-14 | undecidable instance raises no alert | OPF-12 | NP-16 |
| `07` | OP-T07-15 | cascade fields | RES | attribution-rule.md decided |
| `07` | OP-T07-16 | rendering | DS | WS05-T07, WS11 |
| `07` | OP-T07-17 | RK-1 and RK-4 hold a refinement-record value | OPF-14 | NP-7 |

## 4 Proposed ADRs

### 4.1 ADR lines

Six entries are appended to `docs/plan/03-decisions.md`, all proposed with the confirmation tag, in the format of the existing entries (context, decision, alternatives, consequences, status), each with the old contract text, the new text, the affected tasks and the migration of `01-conventions.md` section 6. The contract file is not edited and no version is bumped by this task.

- ADR-045: Template contract: robot-obligation flag and record, tick kinds, grammar term `age`, measurement count not adopted, HOLD refined form (contract points: CP1, CP2, CP9; TG-1, TG-2, TG-5, TG-7)
- ADR-046: Cross-day carry-over: history input of `run_offline` and negative `TimeMs` (contract points: CP7; CG-11, OP-T05-14)
- ADR-047: Registry typing and loader surface (contract points: CP10; TG-3, OP-1, OP-2, OP-3, OP-4, OP-5, OP-6, OP-9)
- ADR-048: VerdictRecord carrier fields and the text of rule 1 (contract points: CP3, CP6; OP-T05-3, OP-T05-13, OP-T07-3, OP-T07-6)
- ADR-049: Clarifications of contract comments without signature change (contract points: CP5, CP11, CP13; TG-10, OP-7, OP-T05-7, OP-T05-15, OP-T07-4, OP-T07-12, CG-4, CG-2)
- ADR-050: `rank_alerts` order K1, VIOLATED before PREDICTED_VIOLATION inside a priority (contract points: CP5; OP-3 of `04`)

### 4.2 Proposals that already exist (not duplicated)

| Group | Contract points | Existing ADR and status | What remains for this review |
|---|---|---|---|
| (i) verdict semantics | CP3, CP6, CP7 (semantics), CP12 | ADR-029, accepted (confirmed by gab, 2026-10-08): tie rule, `undecidable` marker, warm-up prefix as known prefix, infinite endpoints | this review ratifies it as the reference semantics (section 5.3); the contract text and the carrier fields are in ADR-048; the carry-over API is in ADR-046 |
| (ii) lower conformal quantile | CP4 | ADR-030, proposed [DA-CONFERMARE] | nothing; unchanged |
| (iv) alert fields | CP5 (range), CP13 | ADR-041, proposed [DA-CONFERMARE]: `sigma_norm`, kappa of predicted alerts, `t_ms`, `score`, `label`, path, lifecycle | the direction of `priority` and the contract wording go to ADR-049; K1 goes to ADR-050 |
| order key | CP5, `04` OP-6 | ADR-028, accepted: `K0` and the protocol | K1 only (ADR-050) |
| attribution | CP8, C1 reachability | ADR-032 (dispenser group), ADR-033, ADR-034, ADR-035, ADR-036, ADR-040, ADR-044, all proposed; ADR-043 accepted | nothing for WS01; they are WS02 and WS04 decisions |
| INT form | TG-8, CG-7 | ADR-026, proposed | nothing; carried as OPF-8 |
| fixture registry | OP-11 of `03` | ADR-027, accepted | nothing |

### 4.3 Tasks that wait for an ADR

By ADR-021 (c) no implementation task that consumes a gap starts before the ADR of the owning task is accepted. The new entries make these tasks wait: WS05-T03 (ADR-045, ADR-047, ADR-049), WS05-T04 (ADR-045, ADR-046, ADR-048), WS05-T07 and WS05-T08 (ADR-046, ADR-048), WS07-T04 and WS07-T06 (ADR-045), WS04-T10 and WS04-T11 (ADR-045, ADR-046). Their task files are not edited here; the orchestrator or the human adds the notes.

## 5 Freeze statement

### 5.1 What is frozen

At milestone M1, with the clinician review pending (ADR-043):

- The documents `docs/formal/01-signals-sampling.md` to `docs/formal/09-worked-patient-day.md` and this review (`08`) are frozen at version 1.0, as they stand at the commit that carries this file. They are the formal specification: signals and sampling, the seven past-time templates with their units and margin and guard rule, the parameter registry design, normalised robustness and the lexicographic order, the three-valued semantics with intervals and the tie rule, rho per verdict type and Proposition 1, the alert tuple and its wording.
- The five golden files `templates.yaml` (26 cases), `ranking.yaml` (16), `verdicts.yaml` (24), `conformal.yaml` (7) and `patient-day.yaml` (32 records, 6 alerts), the fixture registry F0 of the WS01 README, and the hand-worked day of `09`.
- The contracts as consumed, all at version 0.1.0 (`#time-and-units`, `#trace-schema`, `#parameter-registry`, `#template`, `#signals`, `#verdict`, `#conformal-calibrator`, `#monitor`, `#alert`, `#evidencevector`, `#attribution`). They are unchanged; the changes that the documents need are proposed in ADR-045 to ADR-050 and in the existing ADRs of section 4.2.
- The decisions on which the semantics rests: ADR-029 (accepted) as the reference semantics of the verdict layer and ADR-028 (accepted) for the order key `K0`.

### 5.2 What is not frozen

- The registry values. `configs/registry/hypertension.yaml` is version 0.2.0, `review_status: unreviewed`, every value `reviewed_by: null`; the values are literature proposals accepted by gab (WS01-T09) and no clinician has reviewed them (ADR-043). Registry values are not part of the freeze; the documents use F0 values and say so.
- The clinical review (WS00-T07): pending. M1 is called reached with the review pending, as ADR-043 decides, and the paper states that the parameters come from the literature without a clinician's review.
- The contract text. No ADR of section 4 is accepted; until each is accepted the contract file keeps its text and the tasks of section 4.3 wait.
- The open points of section 5.4, the proposed ADRs and the downstream task files named in the ledger.
- Everything about devices, the ROS 2 stack, the benchmark, the baselines and the paper.

### 5.3 Readings fixed by the review

These are the frozen readings; they are consequences of the dispositions "clarified in docs" and are binding on implementers.

- **R1 Per-instance reference semantics.** WS05 implements one instance per anchor, evaluated at its decision step, with early decision by the interval rule (`01` section 3.7, `02` section 1.5, `05` section 3.3). The whole-formula strings of `02` section 3.1 are tool forms and are not implemented without anchoring. Contract rule 2 of `#time-and-units` holds for the string form.
- **R2 Precedence where documents disagree.** For the fields of an alert, `07` section 1.5 and `06` section 2.4 over `04` sections 4.6, 4.7; for the kind of rho of a VIOLATED record, `06` section 2.3 over `05` section 3.2; for the state of the registry, the file over every statement labelled "registry 0.1.0"; for kappa, the decisive fields and the cascades, `docs/models/attribution-rule.md` over `07` section 1.9 and section 3.5; for instances open at the closing step, `05` section 7.5 item 2 over `01` section 5.5 item 5.
- **R3 Evaluability of INT.** INT is evaluable only when a witness channel or `auth` is available; otherwise the instance stays PENDING with the marker `undecidable: channel_unavailable:<signal>` (`01` section 2.4, `05` section 3.5, V-INT-1).
- **R4 Re-issue of a root.** A re-issue for a cascade link changes only the link field and the sentence of the text derived from it (`attribution-rule.md` cascade rules 7 and 8, OP-AR-20).
- **R5 Closure of a predicted alert.** A predicted alert whose instance ends SATISFIED is closed as a false predictive alarm, leaves the current set and stays in the history.
- **R6 COUNT day-end.** The day-end obligation is satisfied as soon as the dispenses of the day exceed `dose_min_day_end` (`05` Lemma 12), including by an unscheduled dose that violates the 24 h limit; this is stated and not hidden.
- **R7 Hypotheses of the worked day** are listed in `09` section 1.4 (H-W1 to H-W12); results of the day hold under them and under F0.

### 5.4 Open points carried

| OPF | Open point | Owner | Effect on claims |
|---|---|---|---|
| OPF-1 | Dose count window against dose timing (F1) | WS01-T02, WS00-T07 | COUNT alerts are about the 24 h count |
| OPF-2 | Withheld or refused dose against the day-end minimum (F2) | WS01-T02, WS02, WS04 | the alert is "obligation unmet" |
| OPF-3 | Response test on one pair of readings (F3) | WS01-T06, WS04-T04, WS04-T10, WS08 | no claim of detecting drug response |
| OPF-4 | Inflation duration against the device cycle (F4) | WS01-T01, WS04-T06, WS10-T02 | SYS results conditional on the signal |
| OPF-5 | Clock-skew bound against the step (F5) | WS07-T03, WS10, WS01-T03 | timing claims carry `T_s + 2 * skew_max` |
| OPF-6 | Duplicate `(source, seq)` in the accepted trace (NP-1) | WS01-T05, WS01-T01 | replay results use the informed replay |
| OPF-7 | Clinical questions Q1 to Q5 of `03` section 6 (RANGE during onset, refined HOLD, per-patient overrides, measurement count, scales and priorities) and the displayed lateness | WS00-T07 | wording "illustrative, unverified" |
| OPF-8 | Form of INT (ADR-026, proposed) | gab | INT as in `02` section 4.7 until decided |
| OPF-9 | Early VIOLATED by the registry bounds (OP-T05-8) | WS05-T04 | log the dependence on the bounds |
| OPF-10 | At most one sample per bin (A0 of `05`) (NP-17) | WS04-T06, WS01-T02 | RANGE and SYS instances read the grid value |
| OPF-11 | Tick spacing and the severity of a SCHED alert (AH-23, NP-13) | WS01-T02 | -T_s / s or -1 at the deadline |
| OPF-12 | Closure of a predicted alert and undecidable instances have no alert path (NP-15, NP-16) | WS05-T09, WS02 | recorded in the log only |
| OPF-13 | Stale registry statements in `03` to `07` (D1, D3, D4) | WS01-T03 | none; each is labelled with its version |
| OPF-14 | Fixtures RK-1 and RK-4 hold a refinement-record value (D8) | WS01-T04 | none; the order is correct |
| OPF-15 | Wording mismatches of `04` and `07` against later documents (D2, D5, D6) | WS01-T04, WS01-T07, WS01-T01 | rule R2 |
| OPF-16 | Reachability of C1 in the reference device profile (`attribution-rule.md` OP-AR-1, ADR-044 proposed) | WS02, gab | C1 recall is reported per profile |

### 5.5 Statement

Documents `01` to `09` are frozen at version 1.0, with the golden files, the fixture registry F0 and the contract versions listed in `docs/formal/README.md`. Registry 0.2.0 and the clinician review are not part of the freeze. The statement `FROZEN: yes (M1 formalization freeze)` and the field `clinician_review: pending` are in `docs/formal/README.md`. A frozen document is reopened by setting the status of its owning task to `in_progress`, fixing it there, rerunning that task's checks and recording the change in this review.
