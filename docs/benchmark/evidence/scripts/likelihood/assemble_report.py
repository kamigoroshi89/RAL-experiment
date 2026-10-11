import re, sys
O = "/tmp/research/likelihood/out/"
def rd(name, strip_first_header=False):
    s = open(O + name).read()
    s = re.sub(r"^## ", "#### ", s, flags=re.M)
    s = re.sub(r"^### ", "#### ", s, flags=re.M)
    return s.strip()

R = []
w = R.append

w("""# Attribution by a likelihood table: prototype, recompute of the 2160 pair members, pairs, main population, sensitivity

Research run of 2026-10-11 for ADR-074 (gab's decision to replace the exclusion rule). Technical and pre-clinical; nothing here is a clinical claim. Read-only on the repository: everything was done on a copy under `/tmp/research/likelihood/` (`repo/` = working tree of HEAD `a968cb2` without `.git`, `data`, `outputs`, `ros2`, `tesista`, plus the fourth-group patch `/tmp/research/pairs/g4_confounders.patch` and four marked research-copy changes listed in section 1.7). Scripts, logs and raw outputs: `/tmp/research/likelihood/{likelihood_attr.py,scripts/,logs/,out/}`.

**Every awaiting row of the builder is a labelled PLACEHOLDER** (research registry `/tmp/research/pairs/research_registry.yaml`: the real one lacks 7 names, OPF-6; circadian peak 14:00, intake lag 5 s, double-take gap 2 min, nominal bounce 500 ms, durations 1/4/12 h, magnitudes). Every shape-dependent share below is conditional on them. **Every number in the likelihood table is a sensitivity-grid value, not a proposal**: eps in {0.001, 0.01, 0.05, 0.1}; qc in {0.25, 0.5, 0.75}; priors uniform plus four ILLUSTRATIVE alternatives; mixtures uniform plus alternatives; tau in {0.5, 0.67, 0.8, 0.9, 0.95, 0.99}. The "reference point" used in the headline tables (eps 0.01, qc 0.5, uniform prior, uniform mixture over the fault-model/threat-model catalogue, tau 0.8, channels independent given the cause) is the middle of the grid, chosen only so that one row can be printed; it has no other status.

## 0. Headline

All counts are at the reference point unless stated; denominators are stated. Members of a pair are correlated and the Wilson intervals treat them as independent (section 7).

| quantity | value |
|---|---|
| Reproduction of the old probe | the rebuilt 1080 pairs (27 variants x 40, same configuration and seed 0 as `runs/prp40`) give the same alert lists as `probe_p40.jsonl` for **2160 of 2160** members; hierarchical rule with no diagnostics: kappa = C1 for **0 of 2160** members, 0 of 10 662 alerts |
| Old rule with driver diagnostics emitted | still **0 of 2160** pair members reach C1 (matched alerts: C2 40, C3 205, UNDETERMINED 1634 of 1879). C1 now appears for 6 249 of the 10 662 alerts of those days, all of them `range` alerts; the matched `count`, `sched` and `resp` alert of every C1 member stays UNDETERMINED (section 3.6) |
| Members with the relevant event realised / with a matched alert | 2043 of 2160 / 1879 of 2160 |
| Table, argmax = true cause | **859 of 1879** (45.7%; 43-48): C1 members 614 of 614, C2 members 40 of 738, C3 members 205 of 527 |
| Table, kappa at tau 0.8 | 1711 UNDETERMINED, 168 confident right, **0 confident wrong**; at tau 0.5: 308 UNDETERMINED, 739 right, **832 confident wrong (all of them C1 for a C2 or C3 member)**; at tau 0.67: 1375 / 307 / 197 |
| Pairs, distinguishable stratum, primary template, V0 | log-likelihood-ratio difference D > 0 in **257 of 613** (42%; 38-46); correct direction for both members in 169 of 613 (28%). By group: g1 double_take_vs_bounce **0 of 256**, g2 94 of 108 (87%), g3 40 of 40, g4 123 of 209 (59%) |
| Pairs, indistinguishable stratum | D = 0 exactly in **210 of 210**; but Lambda itself is not 0: median +2.32 (g1), +0.87 (g2), +0.76 (g3), -1.92 (g4) nats, the same for both members: a systematic lean fixed by the catalogue (section 4.2) |
| McNemar on D > 0 (V0 against ...) | no diagnostics: 0 discordant pairs; no witness: b = 14, c = 0 (p 1.2e-4); no verification: b = 100, c = 0 (p 1.6e-30); neither: b = 133, c = 0; **with the ADR-032 dispenser channels (prototype): b = 0, c = 281 (p 5e-85), D > 0 in 538 of 613 (88%)** |
| Silent faults, main population (m120, 433 alerts of stuck_at / cuff_silent_bias / dispenser_bounce) | old rule with diagnostics emitted: **278 confident C1** (64%); table: **0 confident C1** at tau 0.8 with the uniform prior, but argmax C1 for 425 of 433; with the C1-heavy illustrative prior and silent share <= 0.25: 141 confident C1 (0 at silent share >= 0.5) |
| Main population (m120: 3 600 patient-days, 17 015 VIOLATED alerts, 15 084 scored) | log score 0.901 nats, Brier 0.536 (prior only: 1.099, 0.667); per template log score: range 0.913, sched 0.444, hold 0.808, count 1.110, resp 0.894. Over the grid: log score 0.567-1.322 |

**Decisions that gab has to take** (details in section 7.3):
1. **What C1 means when nothing is raised, and what the method does with the silent faults.** With a uniform prior the table does not reach 0.8 for C1 at the reference point (the posterior of C1 on an all-denied reading is 0.41 at `range`, 0.57 at `count`, because silent C2 and informed C3 predict the same silence); over the whole eps x qc x silent-share x grouping grid with the uniform prior it reaches 0.8 for at most 50 of the 614 C1 members (and for 16 non-C1 members). The ways to a confident C1 are a C1-heavy prior or a catalogue without the quiet alternatives (`family = v1`); both also make the silent members confident C1 (776 and 179 confident C1 for members whose cause is not C1). Choose between a prior/threshold policy and a set-valued output (a candidate set instead of UNDETERMINED, as the "partial" cells of the diagnosability matrix say).
2. **Adopt the dispenser channels of ADR-032 and the repeat/gap split of ADR-034 (or the grouped cell).** Without them group 1 has D = 0 for 100% of its pairs and group 4 59%; the independent table drops the IE-2 distinction (37 group-4 members go from C3 to UNDETERMINED); with them D > 0 rises from 42% to 88%.
3. **Scope and values of the C2/C3 cells.** Whether a cell describes the fault that *causes* the violation of the template (`scope = template`) or any fault *present* in the scope (`scope = all`) moves the main log score from 0.901 to 0.776 and decides whether system evidence at `range` counts at all; plus eps, qc, the mixture weights and the priors, all awaiting values. Emitting driver diagnostics changes Lambda by a constant (+0.86 nats at COUNT) and no direction (section 4.5): it is not a reason by itself to require it from the bridge node.

## 1. Design of the likelihood table

### 1.1 The model

p(c | e, t) is proportional to prior_t(c) times the product over the fields f read by template t of P(class_f | c, t), for c in {C1, C2, C3}. UNDETERMINED is not a cause: kappa = argmax if the maximum posterior is at least tau, else UNDETERMINED. A cause that has no component for the template is impossible for it (probability 0).

* **Inputs.** `LikelihoodAttributor.posterior(violated, evidence)` takes the same two objects as `HierarchicalRule.attribute`. The reading classes come from `HierarchicalRule._readings` (same registry thresholds, same relevance map `_READS`), so the table reads exactly the fields the rule reads, and nothing else: not rho, not the interval, not the verdict state, not a time, not the ground truth (check: the posterior with `violated=None` equals the posterior with the record; `scripts/test_likelihood.py`, 22 checks, log in `logs/test_likelihood.log`).
* **Classes.** A (asserted) and D (denied) have cells. U (`None`, or out of domain) contributes the factor 1 and is never a negative reading. K (a deliberate lifecycle transition) is treated as U (no cause of the model produces it); it did not occur in any alert of either population. The finer classes of `ble_link_quality` (F complete, G gap without degradation) count as D in the independent table, and enter as joint classes in the grouped variant G1. `system.battery_low` and `witness.robot_present` are context (not read), as before.
* **Cells.** Built from a catalogue of components, not typed in. P(f = A | c, t) = sum over the components s of cause c that can violate t of w(s | c, t) times (eps + (1 - 2 eps) rho(s, f)), with rho = 1 when the fault-model row (C2) or the threat-model row (C3) raises f by construction (R), rho = qc when the raise is conditional (C: the conditions LC, SEQ, D-5 of the fault-model table), rho = 0 when it does not. eps is the leak of every structural cell: a field raised by construction is 1 - eps, one raised by no component is eps. Intermediate cells are the declared mixture over the components. **The mixture weights, qc, eps, the priors and tau are the only free numbers; none is a proposal; all are grid values (section 6).**
* **Templates.** A component enters the cells of a template only if the fault-model table (column "template_kind of the violations it can cause") or the threat-model table lists the template for it (`scope = template`); `scope = all` (every component of the cause, a co-occurrence reading) is a sensitivity. C1 has one component whose cells are all eps (analisi 4.5: C1 raises no system or integrity evidence), except `witness.intake_observed`, which has the diverted-dose share delta (0 in the benchmark: the adherence model has no dispensed-but-not-taken case). C1 exists for `count` (double_take, dose_omission, spontaneous count) although the old rule had no C1 row for it; it does not exist for `sys` and `int` (no catalogued C1 cause).
* **Independence.** Naive Bayes (channels independent given the cause) is an **assumption**, and it is false for the obviously dependent fields: `ble_dropout` raises node_lifecycle, ble_link_quality, diagnostics_ok together, so the independent table counts one fault several times. Two grouped variants are tested: **G1** groups (ble_link_quality, seq_gap_or_replay) in a joint four-class reading (repeat = sequence asserted with complete ratio; gap = sequence asserted with ratio below one; degraded; clean) and (pulse_vs_ecg_hr_diff, ecg_sqi, ppg_sqi) with `ecg_noise` as a common cause also for the care-plan templates; **G2** makes the channels independent given the sub-cause instead of the cause (a latent-class mixture over all fields).
* **Extension fields (outside the contract).** To test whether a dispenser evidence field (ADR-032, proposed) closes the COUNT gap, the prototype adds two fields computed from the observed `DISPENSE` events up to the decision time (24 h window): `dispenser.short_interval` (an opening within T_b of the previous one) and `dispenser.no_content_change` (an opening with content_change = 0; `None` for a dispenser without content sensing or a forged dispense with no payload). They enter only in variant V5; T_b is a grid value {1, 10, 30, 60, 180 s}.

### 1.2 to 1.5 Cells, sources, parameters

Per cell the source of the value is the column "source of the row" (fault-model row, threat-model row, device specification, design choice). "GAB" marks the cells and parameters whose value, or the declaration that it stays a sensitivity range, needs a human decision; **all of eps, qc, the weights, the priors, tau, T_b and delta are in that class**. Cells that are structural 0 (eps) need only eps.

""")
w(rd("cells_tables.md"))
w("""

### 1.6 What the generator now emits (research copy, as a switch)

`RALMON_DRIVER_DIAG=1` in `repo/src/ralmon/benchmark/injection.py:finalize_observed` calls `repo/src/ralmon/benchmark/driver_diag.py`, which adds NODE_STATE events with `payload.diagnostics` (ok / stale; vocabulary of `evidence-channels.md`) for the nodes `cuff` and `dispenser`: `ok` at t = 0 and every period (1 h; a 10-minute period gives the identical evidence vector for all 10 662 alerts, `logs/run_members_period10min.log`), `stale` at the start and each period of a `link_down` ... `active` window that the gateway wrote for a `ble_dropout`, and `ok` again at its end. The reports are derived from the observed trace only. A silent fault (cuff_silent_bias, stuck_at, dispenser_bounce) leaves the device publishing, so the driver reports `ok`. The monitor ignores non-robot NODE_STATE events, so verdicts are unchanged (checked: the alert lists equal those of the old probe). Robot diagnostics are not emitted (robot capability `diagnostics` stays False).

* **Profile "driver with diagnostics"**: switch ON, capability `diagnostics = True` for cuff and dispenser. **Profile "without diagnostics"**: capability False (equivalently, switch OFF: a capability without reports gives `None`; checked on the second full build, `run_members.py 40 p40 0`: 0 of 10 662 alerts differ between "switch OFF" and "switch ON, capability False"). The rest of the profile is as in `probe_pairs.py` (cuff: status, supervised, seq, two clocks, error codes, 12 h deadline; dispenser: status, supervised, seq, two clocks, authenticates in the variants that keep verification).
* `system.diagnostics_ok` is asserted (A) for 135 of the 2 679 C2 alerts of the main population (5%), almost all `ble_dropout`; denied (D) for all 11 256 C1 and 1 057 C3 alerts that have it, and for **2 205 C2 alerts**, i.e. also under the silent faults.

### 1.7 Changes to the copy (all marked `RESEARCH COPY`)

`repo/src/ralmon/benchmark/driver_diag.py` (new), `vocab.py` (key `diagnostics`, values ok/warn/error/stale), `injection.py` (switch in `finalize_observed`), `confounders.py` (fourth group, the patch of the earlier run). Nothing in `/home/gab/Desktop/RAL experiment` was written.

## 2. What changed with respect to the hierarchical rule

### 2.1 What the old rule decided by exclusion or precedence, and where it now enters

| old element | what the rule did | in the table |
|---|---|---|
| Row 1, IE-1: `authenticated` asserted | C3, first, whatever else is asserted | P(A given C3) is the share of C3 components that synthesise or rewrite a message (0.66 to 0.99 at the reference point) against eps for C1 and C2: a likelihood ratio of 66 to 99 (about 1e3 at eps 0.001), not a precedence. With system evidence asserted at the same time the two factors compete and the posterior can end UNDETERMINED (the old rule said C3) |
| Row 2, IE-2: sequence asserted and ratio complete (a repeat) -> C3; a gap -> C2 or conflict | needs the joint reading of two fields | the independent table loses the distinction (a cell for the sequence field alone): 37 group-4 members (naive, no verification) fall from old C3 to posterior C3 = 0.795, i.e. UNDETERMINED at tau 0.8. G1 and G2 restore it: 205 of 205 old-C3 members are confident C3 (section 3.7) |
| Row 3, IE-3, SE-9, AM-1: the explained-away rule for the cross-device incoherence | C3 only if both quality fields are denied | independent table: the cross-device cell alone, with no explaining away and with quality `None` read as factor 1; example in 2.2 (case c). G1 adds `ecg_noise` as a common cause, which is the same explaining away as a likelihood |
| Row 4, SE-1 to SE-9: any system evidence | C2, whatever the template | a field is evidence only through the components that can violate the template: an asserted `node_lifecycle` at a `range` alert is uninformative (every `range`-capable C2 component is silent: eps for all three causes) under `scope = template`, informative under `scope = all` (case d) |
| Row 5, EX(t): all fields of the exclusion set available and denied | C1; a `None` blocks it | C1 is "nothing raised": every available D contributes (1 - eps) / (1 - P(A given c)) and U contributes 1, so nothing blocks it. 614 of 614 C1 members have argmax C1; the old rule gave 0 |
| Row 6, RS-1 to RS-4 | abstain with reason conflict | K = factor 1 (never occurred); G counts as D (never occurred as G); `timestamp_implausible` is a mixture cell (link_delay, clock_skew for C2; naive replay, timestamp manipulation, naive injection for C3), decisive in proportion to the mixture instead of never alone; the RS-4 witness case is the `intake_observed` cell of C3 |
| Rows 7, 8: provenance only, insufficient | abstain | the posterior is prior times the denied-reading likelihoods; UNDETERMINED is derived (max below tau). The template enters only as the set of components that can violate it (so `sys` and `int` exclude C1); no component reads provenance as evidence. Neither `sys` nor `int` produced an alert in either population: **the rows for them are untested** |
| Invariant I1 (no rho, interval, state, time) | holds | holds (test 14) |
| A4 mask (hide the embodied channel) | recompute | the witness fields are set to U: factor 1 (variants V2 and V4) |

### 2.2 Cases where the two disagree

(a) **Silent faults with diagnostics emitted.** Main population, 433 alerts of stuck_at, cuff_silent_bias and dispenser_bounce: old rule with diagnostics C1 for 182 + 96 = 278 (cuff_silent_bias 182 of 250, stuck_at 96 of 137), UNDETERMINED for the rest; old rule without diagnostics UNDETERMINED for all but 6. Table: argmax C1 for 425, kappa C1 for 0 at tau 0.8 (uniform prior).

(b) **Unavailable fields.** Main population, truth C1, 11 342 alerts: old rule with diagnostics C1 7 342, C2 39, UNDETERMINED 3 961; table argmax C1 11 292, C2 3, C3 47. The 3 961 are blocked by the exclusion set; for the pair members the blocking fields are listed in section 3.6 (`manip_task_failed`, the cuff fields in a `sched` window, identity and intake at `resp`); the main-population alerts were not decomposed.

(c) **Cross-device incoherence with the quality fields unavailable.** Hold alert of a `ble_dropout` (truth C2): old rule C2 (SE-5 on `ble_link_quality`); independent table posterior C1 0.003, C2 0.119, **C3 0.878**, from `pulse_vs_ecg_hr_diff` asserted (C3 cell 0.133 against eps), `seq_gap_or_replay` asserted (0.316 against 0.085) and `ble_link_quality` asserted (0.123 against eps for C2). The old rule would have abstained on the first alone (AM-1); the table counts it as C3 evidence because the quality fields, being unavailable, contribute 1. This is the dependence of the cross-device group with its quality fields that G1 is meant to catch.

(d) **System evidence outside the template's causes.** Range alert with `node_lifecycle` asserted (truth C1 spontaneous, or C3 replay): old C2; table {C1 0.414, C2 0.414, C3 0.172}, i.e. no information, because no C2 component that can violate `range` raises that field. With `scope = all` the field counts (main log score 0.776 instead of 0.901).

(e) **Hard C3 evidence overruled by the mixture.** Old C3 -> table UNDETERMINED for 37 members (see Row 2 above); the pair `bounce_vs_forg naive_noauth_content #846B` has posterior {C1 0.051, C2 0.154, C3 0.795}.

(f) **Refusal against robot missed (outcome reported).** Old rule C2 for the manipulation_failure member (`manip_task_failed` asserted); table posterior C2 0.669 -> UNDETERMINED at tau 0.8: one raised field out of ten C2 components, a likelihood ratio of 10.8 at eps 0.01 (about 100 at eps 0.001).

Cross-tabulation on the matched pair members: old C2 -> table UNDETERMINED 40; old C3 -> C3 168, -> UNDETERMINED 37; old UNDETERMINED -> UNDETERMINED 1634 (section 3.5). Main population confusion: section 5.5.

## 3. Recompute of the 2160 pair members

Setting: 27 variants x 40 pairs (seed 0, the configuration of `runs/prp40` rebuilt in `runs/pairs_p40`), measured-only monitor (no forecaster) on day 0 of each member, evidence under both profiles; the alert of a member is matched provisionally as in `pairs-allocation.md` section 5 item 2: the earliest VIOLATED alert, decided at or after the onset of the member's relevant ground-truth event, of a template in that event's template set (template of the labelled C1 event; `details["templates"]` of a C2 record; the threat-model list for the C3 forgery), the primary template of the group first (count g1 and g4, resp g2, sched g3). A COUNT alert of a morning extra dispense is therefore the one decided at the next dose step. Alerts of the tail day are not included. The ground truth is read only to define the true cause and the match (scoring side).

""")
w(rd("recompute_tables.md"))
w("""

### 3.6 Why the old rule still cannot reach C1 for the members, with diagnostics emitted

Decision row and missing fields of the old rule at the matched alert of each of the 614 C1 members (profile with diagnostics). `system.diagnostics_ok` is no longer in the list: emitting it opens only the `range` alerts of the background. What remains:

""")
w(rd("structural.md").split("#### 7.2")[0].replace("#### 7.1", "Table 3.6:"))
w("""
* **COUNT** (294 of 294 group-1 C1 members): no C1 row at all (row 8), and no dispenser evidence field (ADR-032). The table gives COUNT a C1 component (double_take, dose_omission, spontaneous count) and a dispenser-bounce component that is silent for the twenty fields, so the structural gap is handled by a cell, but the bounce cannot be told from the double take until a dispenser field exists (section 4.7).
* **SCHED** (120 members, group 3): the cuff is silent in the evidence window, so `cuff_error_code`, `ble_link_quality`, `seq_gap_or_replay`, `timestamp_implausible` are `None`, plus the robot manipulation outcome. The table is not blocked by `None`.
* **RESP** (200 members): `manip_task_failed` is `None` in all (the benchmark base emits no `success` outcome of the manipulation), `nav_task_failed` often, and the witness backing (`identity_confirmed` never emitted, `intake_observed` not always) is missing: the old rule needs `authenticated` denied or both witness fields denied. Neither is available in the variants without authentication.
* **Verification and the witness backing**: at `resp` the old rule needs `authenticated` denied, or both witness fields denied, as backing of C1; in the variants without authentication `authenticated` is `None` and `identity_confirmed` is never emitted, which is why 3.6 lists them as missing.
* The new table handles all of these as factor 1. What it cannot do is separate what the channels do not separate (section 4).

### 3.7 Grouping and the 37 members

The 205 members whose old kappa is C3: independent table 168 confident C3 and 37 UNDETERMINED; **G1 205 of 205 confident C3; G2 205 of 205** (`scripts/grouped_c3.py`, `logs/grouped_c3.log`).

### 3.8 Silent-fault members of the pairs

The 618 matched members whose mechanism is `dispenser_bounce` (group 1 member B, group 4 member A): kappa C1 at tau 0.5 for **618 of 618** at the reference point, at tau 0.67 for 153 (all in group 4), at tau 0.8 for 0. Over the whole eps x qc x silent-share x grouping grid with the uniform prior (180 combinations of the factorial): at tau 0.8 for at most 9 of 618; at tau 0.5 between 9 and 618 (618 in 90 of the 180 combinations, lower values in the other 90, mostly with G2 (51) or a silent share of 0.5 or more (59)). With the C1-heavy illustrative prior at tau 0.8: 610 of 618 at the reference point (section 6.1, row prior c1_heavy).

## 4. Pairs: likelihood ratio, direction, McNemar

Lambda_M = log P(e_M | c_A) - log P(e_M | c_B) of the alert matched to the member's relevant event (prior-free; c_A = C1 in groups 1 to 3 and C2 in group 4; c_B = C2 in groups 1 and 3 and C3 in groups 2 and 4); D = Lambda_A - Lambda_B; stratum from the per-pair `indistinguishable_by_construction` flag. The pair uses the **common template** of the two members (primary template of the group first, the next common template if one member has no alert of it, e.g. the naive forged dispense that the monitor rejects as a duplicate in group 4). "Correct direction" needs Lambda_A > 0 and Lambda_B < 0.

""")
w(rd("pairs_tables.md"))
w("\n\n")
w(rd("ext_tables.md"))
w("""

Reading of section 4.

* **Group 1 (double take against bounce): the table gives the same likelihood ratio to both members in all 294 matched pairs** (Lambda = +2.322 for A and B, D = 0). The fields that COUNT reads are all denied in both, so the ratio is the lean of the catalogue (four of five C2 components at COUNT are loud and predict a raised field), not evidence. The bounce member is leaned toward C1: this is the silent fault masquerading as C1. The witness separates the *streams* (two INTAKEs against one), but the instance-level boolean `intake_observed` reads True in both (4.1b: D = 0 for 80 of 80 pairs that have a RESP alert of the extra opening), so only the prototype dispenser fields separate them: D > 0 in 217 of 256 (T_b <= 60 s), and **at T_b = 180 s, above the double-take gap, the interval stops separating (D > 0 in 147 of 256)**; the `stress` variants (bounce gap equal to the double-take gap) are separated by content change only, and the stress variants without content sensing (`stress_nocontent_*`) by nothing (D = 0 in 38 and 38).
* **Group 2 (non-response against falsified dispense)**: D > 0 in 94 of 108; of the 14 with D = 0, 13 are the pairs separated only by `dispense_seq` (4.4: the forged sequence number is not turned into an asserted field at the RESP alert) and 1 by verification. Without verification D > 0 falls to 31% of the group-2 pairs (V3), and with neither witness nor verification to 0% (V4): in the unauthenticated variants without a robot the channels do not separate the pair, as the diagnosability matrix says.
* **Group 3**: D > 0 for 40 of 40 distinguishable pairs (the manipulation outcome); indistinguishable 80 of 80 with D = 0 (`outcome_withheld`, `robot_absent`).
* **Group 4 (bounce against forged dispense)**: Lambda_A is negative for most bounce members (a silent bounce is read as closer to the quiet forgery than to the loud mixture of C2): Lambda_A > 0 only in 56 of 209; D > 0 in 123 of 209 (the forgeries that raise authentication, sequence). `content_change`-only pairs (39): D = 0.
* **Indistinguishable stratum**: D = 0 exactly for 210 of 210 matched pairs, in all four groups (4.3); Lambda is not 0: the identical-stream pairs get the same non-zero ratio (the lean), +2.32 in group 1 and -1.92 in group 4.
* **Diagnostics** (4.5, 4.6): V0 and V1 have the same D > 0 set in all pairs; Lambda shifts by a constant, +0.861 nats in group 1, +0.161 in group 3, 0 in group 2, between -0.861 (COUNT) and -0.132 (RESP) in group 4. "Both correct direction" is higher without diagnostics (243 against 169 of 613) only because the group-4 lean moves; it is not a gain.

## 5. Main population

""")
w(rd("main_tables_m120.md"))
w("\n\n")
w(rd("main_sens_tables.md"))
w("""

Notes on section 5.

* **Population.** Ordinary builder (`run_main.py m120 120 30 default`): 120 virtual patients x 30 days, seed 0, fault-free background (ADR-071) plus the injections of the research registry (rates 0.3 / 0.3 / 0.2 for C1 / C2 / C3: placeholders), default device profile (no authentication, no content sensing) and, in `r40`, an authenticating dispenser with content sensing. Measured-only monitor with the history of the previous day (the builder's `history_days` is 1 for this configuration; the `ours` history mode); tail-day closing-step events are not used. Predicted alerts are UNDETERMINED by definition and are not scored.
* **Truth of an alert** (scoring code only): the ground-truth events of the day whose template set contains the alert's template and whose time window (first decidable time, end of the event, plus 24 h) contains the decision time; if the compatible events have one cause that is the truth, if two causes the injected one (injected-first) or the alert is dropped (strict). 1 272 alerts match no event (false alarms of the background) and are not scored; 659 are ambiguous. Alerts of one event are correlated; no patient-level bootstrap was run.
* **The uniform prior is not the base rate of the benchmark and the calibration curves show it**: at `range` the table states C1 = 0.41 for 8 034 alerts of which 93% are C1, because nothing in the evidence separates C1 from the silent C2 at `range` (the only C2 components that can violate `range` are silent), so the posterior is the prior odds. The row "prior = benchmark class frequency" is a labelled circular diagnostic (log score 0.573) that shows how much of the miscalibration is the prior and not the cells; it is not a method.
* The old rule has no probability, so there is no old-rule log score; its confusion is in 5.5.

## 6. Sensitivity

One-at-a-time sweeps from the reference point over every parameter of the model, the evidence-set variants, a full factorial over eps x qc x prior x silent share x grouping (900 combinations), and the silent-fault shares by eps and silent share. `scripts/sweeps.py`, `scripts/sweeps_report.py`, `logs/sweeps.log`.

""")
w(rd("sweeps_tables.md"))
w("""

Notes on section 6.

* **D > 0 does not move with eps, qc, the priors, the silent share or the grouping** (the directions are fixed by the catalogue, 900 combinations: group 1 0.000, group 2 0.870, group 3 1.000, group 4 0.589); it moves with the evidence that exists (V2 to V5), with `divert` (group 2 0.87 -> 0.74 at 0.25) and with the extension channels. The lean (mean Lambda_A of the indistinguishable stratum) moves with qc, the silent share, `family`, `informed_share`, `scope` and `group`.
* **The prior decides everything that depends on tau**: at tau 0.8 the uniform prior gives 168 confident right and 0 wrong; the C1-heavy illustrative prior 579 right and 776 wrong (all confident C1 for a non-C1 member: 610 of the 618 silent bounce members); the C2-heavy prior 208 right and 0 wrong; c3_rare 411 right and 700 wrong.
* **Silent faults and eps / silent share** (6.4, 6.5): with the uniform prior the share of silent-fault alerts with confident C1 is 0 for every eps and silent share; with the C1-heavy prior it is 141 of 433 (silent share <= 0.25, every eps) and 0 at silent share >= 0.5. The share with argmax C1 is 425 to 433 of 433 whatever eps and silent share, and falls only with a C2-heavy prior (146) or C3-heavy prior (0).
* `family = v1` (only the 8 + 5 subtypes injected by benchmark v1) gives 179 confident wrong where `fm` gives 0: restricting the catalogue to what the generator injects removes the quiet alternatives and makes C1 confident, which is the circularity the ADR warns about.
* `group`: log score 0.901 (independent), 0.833 (G1), 0.884 (G2); per template in `logs/extras.log`: G1 helps `range` (0.913 -> 0.801) and G2 helps `count` and `resp`.
* `scope = all` improves the main log score to 0.776 and the lean of group 4 to -0.35.
* Variant "no diagnostics profile": main log score 0.894 against 0.901 with diagnostics emitted.

## 7. What could not be determined, and why

### 7.1 Not determined

* **The numeric cells.** No value of eps, qc, the mixture weights, the priors, tau, delta or T_b can be sourced from the repository, the fault model or the literature collected so far; the report gives how the results move over the grid. The catalogue (which sub-causes exist and which fields they raise) is sourced from the fault-model and threat-model tables, but those tables were written in the project that wrote the generator: the `fm` family is wider than the 8 + 5 subtypes the generator injects, but not independent evidence of what a ward produces.
* **The thesis-student bridge.** How a real ROS 2 driver reports STALE for a device that is connected but stops publishing, and whether a silent fault leaves it at OK, is assumed from `DiagnosticStatus`; it is not tested on hardware (the thesis zones were not touched).
* **Matching** is provisional (the earliest alert of a compatible template after the onset); the denominators of section 3 are conditional on it, on the placeholders and on a single generation seed and 40 pairs per variant (about 10 test pairs per variant if the split of the allocation is used). Alerts decided in the tail day are not matched, which loses some positives (the evening bounce whose COUNT alert would be decided at the closing step). No confidence intervals over seeds; members of a pair are correlated.
* **Brier and log score** have no bootstrap interval; alerts of one event and of one patient are correlated.
* **Predicted violations and the forecaster** are not used: the attribution of a PREDICTED_VIOLATION is UNDETERMINED by definition (CP13) and the scores here are for VIOLATED alerts of the measured-only monitor.
* **`sys` and `int`**: no alert of either template occurs in either population, so their cells and the "C1 impossible" support are untested.
* **The extension fields** read the DISPENSE events of the day up to the decision time; in a real EvidenceVector ADR-032 would define them per instance. A forged dispense that mimics the bounce timing (group 4 uses the nominal gap) defeats the interval field by construction; the table does not model attacker timing (cell eps for C3).
* **Cascade folding** of the old attributor (a SCHED root decides its RESP and HOLD effects) is not applied to the posterior. For the pair members it changes nothing: `check_repro.py` compares `HierarchicalRule.decide` at every alert with the (folded) kappa of the old probe and finds 0 differences in 2160 members.
* **C1 with diversion.** The adherence model has no dispensed-but-not-taken case, so the witness cell of C1 is eps in the benchmark although the threat model says a False witness also arises from a patient who diverted the dose; `divert` > 0 is a sensitivity only.

### 7.2 Where it fails (stated plainly)

* The silent faults masquerade as C1: argmax C1 for 425 of 433 silent-fault alerts of the main population at the reference point (425 to 433 over eps and silent share), and kappa C1 for all 618 bounce members of the pairs at tau 0.5; at tau 0.8 they are confident C1 only when the prior (or the catalogue) favours C1: 141 of 433 and 610 of 618 under the C1-heavy illustrative prior.
* At `range` (8 243 of the 15 084 scored alerts of the main population) the likelihood ratio between C1 and C2 is exactly 1 on every reading, since every C2 component that can violate `range` is silent; the posterior is the prior.
* Group 1: D = 0 for all 256 distinguishable pairs. Group 3 `outcome_withheld` / `robot_absent`, group 4 `informed_noauth_nocontent` and the stress `nocontent` variants of group 1: D = 0 by construction, as the flags say.
* With uniform priors, 1 711 of 1 879 matched members are UNDETERMINED at tau 0.8 (91%).
* The independent table double counts correlated channels (one dropout raises three or four system fields) and loses the repeat/gap distinction; G1/G2 repair both at the cost of more declared structure.
* Emitting driver diagnostics adds little: D > 0 identical, McNemar V0 against V1 with no discordant pair, main log score 0.894 without against 0.901 with.

### 7.3 The three decisions

1. **C1 and the silent faults.** Under the uniform prior the table is at most about 0.57 sure of C1 where nothing is raised (0.41 at `range`), because silent C2 and informed C3 predict the same readings; any prior, catalogue or threshold that makes C1 confident makes the silent faults confident C1 as well (776 confident C1 for non-C1 members of the 1879 under the C1-heavy prior; 179 with `family = v1`; 832 at tau 0.5). Decide: (a) a declared prior and tau (and accept the silent faults as the stated limit of analisi 4.8, reported through the diagnosability matrix), or (b) a set-valued output {C1, undetectable C2 or C3} when the evidence is silent, instead of UNDETERMINED. The data cannot choose between them.
2. **Dispenser channels and the sequence split.** Accept ADR-032 (interval since the previous opening, content change) and ADR-034 (repeat against gap), or the grouped (ble_link_quality, seq_gap_or_replay) cell: without them groups 1 and 4 are not separable and 37 members lose C3.
3. **Scope and values of the C2/C3 cells.** Cause-of-the-violation (`scope = template`) or any-fault-present (`scope = all`), the weights of the sub-causes, qc, eps and the C1 diversion share delta: each is an `awaiting_human_value` row. Whether to require the driver diagnostics from the bridge node should be judged on other grounds than this table, which gains almost nothing from it.

## 8. Reproduction

All with `/tmp/research/likelihood/scripts` as the working directory (fixed seeds, no network, no GPU):

```
python3 run_members.py 40 p40 1        # 1080 pairs, switch ON  (logs/run_members_sw1.log)
python3 run_members.py 40 p40 0        # switch OFF             (logs/run_members_sw0.log)
python3 check_repro.py                 # 2160 members vs probe_p40.jsonl: 0 mismatches; switch OFF == capability False
python3 run_main.py m120 120 30 default; python3 run_main.py r40 40 30 rich
python3 test_likelihood.py             # 22 checks
python3 recompute_2160.py; python3 pairs_report.py; python3 ext_report.py; python3 structural_gaps.py
python3 sens_data.py; python3 sweeps.py; python3 sweeps_report.py
python3 main_report.py m120; python3 main_sens.py; python3 extras.py; python3 cells_table.py
python3 assemble_report.py             # this file
```
""")
open("/tmp/research/likelihood-attribution.md", "w").write("\n".join(R))
print(len("\n".join(R).split("\n")), "lines")
