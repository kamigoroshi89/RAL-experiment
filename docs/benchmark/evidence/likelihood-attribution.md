# Attribution by a likelihood table: prototype, recompute of the 2160 pair members, pairs, main population, sensitivity

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


#### 1.2 Component catalogue (the sub-causes whose mixture makes a cell)
| cause | component | templates it can violate | raises (R by construction, C conditional) | tags | source of the row |
|---|---|---|---|---|---|
| C1 | clinical | count hold range resp sched | none | v1 | analisi 4.5 (C1 raises no system/integrity evidence); INTAKE: diverted dose share delta (design, awaiting gab; the benchmark adherence model has none) |
| C2 | cuff_detached | hold resp sched | cuff_error_code:R, node_lifecycle:R | loud v1 | fault-model row cuff_detached |
| C2 | cuff_silent_bias | hold range resp | none (silent) | silent v1 | fault-model row cuff_silent_bias (silent, declared limit) |
| C2 | stuck_at | hold range resp | none (silent) | silent v1 | fault-model row stuck_at (silent, declared limit) |
| C2 | ecg_noise | sys | pulse_vs_ecg_hr_diff:R, ecg_sqi:C | loud v1 | fault-model row ecg_noise (violation only through sys; also a nuisance in G1) |
| C2 | dispenser_bounce | count hold int resp | short_interval:C, no_content_change:C | silent v1 | fault-model row dispenser_bounce (silent for the 20 fields; EXTENSION fields ADR-032) |
| C2 | ble_dropout | count hold resp sched | node_lifecycle:R, ble_link_quality:R, diagnostics_ok:R, liveliness_ok:C, qos_deadline_missed:C, seq_gap_or_replay:C | loud v1 | fault-model row ble_dropout; DIAG: driver reports stale while the device is silent (ADR-074) |
| C2 | message_drop | count hold int resp sched | ble_link_quality:C, seq_gap_or_replay:C, qos_deadline_missed:C, liveliness_ok:C, diagnostics_ok:C | loud | fault-model row message_drop (all conditional); DIAG: device alive, stale only for a long run of losses |
| C2 | link_delay | count hold int resp sched | timestamp_implausible:R, qos_deadline_missed:C | loud | fault-model row link_delay |
| C2 | clock_skew | hold sched | timestamp_implausible:R | loud | fault-model row clock_skew |
| C2 | nav_delay | hold resp sched | nav_task_failed:C | loud v1 | fault-model row nav_delay (D-5) |
| C2 | impossible_goal | hold resp sched | nav_task_failed:R | loud | fault-model row impossible_goal |
| C2 | localisation_noise | hold resp sched | nav_task_failed:C | loud | fault-model row localisation_noise |
| C2 | manipulation_failure | hold resp sched | manip_task_failed:R | loud v1 | fault-model row manipulation_failure |
| C2 | process_kill | count | liveliness_ok:C, qos_deadline_missed:C, node_lifecycle:C, diagnostics_ok:R | loud | fault-model row process_kill (device target); DIAG stale |
| C2 | uncommanded_lifecycle_transition | count | node_lifecycle:R, diagnostics_ok:R | loud | fault-model row uncommanded_lifecycle_transition |
| C2 | battery_depleted | hold resp sched | liveliness_ok:C, qos_deadline_missed:C | loud | fault-model row battery_depleted (robot has no driver diagnostics in the profile) |
| C3 | replay_naive | hold resp sched | seq_gap_or_replay:R, timestamp_implausible:R | naive v1 | threat-model row replay (naive; verbatim copy keeps a valid tag) |
| C3 | replay_informed | hold range resp sys | authenticated:R, pulse_vs_ecg_hr_diff:C | informed v1 | threat-model row replay (informed) |
| C3 | injection_naive | hold range resp sched sys | authenticated:R, seq_gap_or_replay:C, timestamp_implausible:C, pulse_vs_ecg_hr_diff:C | naive v1 | threat-model row injection_naive |
| C3 | injection_informed | hold range resp sys | authenticated:R | informed v1 | threat-model row injection_informed |
| C3 | dispense_forgery_naive | count hold int resp | authenticated:R, seq_gap_or_replay:R, intake_observed:C | naive v1 | threat-model row dispense_forgery (naive); INTAKE False when the robot is co-located and saw nothing |
| C3 | dispense_forgery_informed | count hold int resp | authenticated:R, intake_observed:C | informed v1 | threat-model row dispense_forgery (informed) |
| C3 | presence_spoof_naive | int | identity_confirmed:C | naive v1 | threat-model row presence_spoof (naive) |
| C3 | presence_spoof_informed | int | none (silent) | informed v1 | threat-model row presence_spoof (informed) |
| C3 | timestamp_manipulation | hold range resp sched | timestamp_implausible:R, authenticated:R | naive | threat-model row timestamp_manipulation (modelled, not injected in v1) |
| C3 | dispenser_physical_tamper | count hold int resp | intake_observed:C | informed | threat-model row dispenser_physical_tamper (modelled, not injected in v1) |

#### 1.3 Cell structure per field and cause (over the whole catalogue; 'structural 0' = eps, 'structural 1' = 1 - eps, 'mixture' = declared weights, 'cond.' = involves qc)
| field | C1 | C2 | C3 | what has to be decided and by whom |
|---|---|---|---|---|
| system.node_lifecycle | structural 0 (eps) | mixture; R: cuff_detached, ble_dropout, uncommanded_lifecycle_transition; C: process_kill | structural 0 (eps) | fault-model/threat-model row; qc and mixture weights - GAB |
| system.diagnostics_ok | structural 0 (eps) | mixture; R: ble_dropout, process_kill, uncommanded_lifecycle_transition; C: message_drop | structural 0 (eps) | driver profile: which faults make the driver report stale (design, WS07-T03) - GAB; mixture weights - GAB |
| system.liveliness_ok | structural 0 (eps) | mixture; C: ble_dropout, message_drop, process_kill, battery_depleted | structural 0 (eps) | fault-model/threat-model row; qc and mixture weights - GAB |
| system.qos_deadline_missed | structural 0 (eps) | mixture; C: ble_dropout, message_drop, link_delay, process_kill, battery_depleted | structural 0 (eps) | fault-model/threat-model row; qc and mixture weights - GAB |
| system.ble_link_quality | structural 0 (eps) | mixture; R: ble_dropout; C: message_drop | structural 0 (eps) | fault-model/threat-model row; qc and mixture weights - GAB |
| system.nav_task_failed | structural 0 (eps) | mixture; R: impossible_goal; C: nav_delay, localisation_noise | structural 0 (eps) | fault-model/threat-model row; qc and mixture weights - GAB |
| system.manip_task_failed | structural 0 (eps) | mixture; R: manipulation_failure | structural 0 (eps) | fault-model/threat-model row; qc and mixture weights - GAB |
| signal_quality.ecg_sqi | structural 0 (eps) | mixture; C: ecg_noise | structural 0 (eps) | fault-model/threat-model row; qc and mixture weights - GAB |
| signal_quality.ppg_sqi | structural 0 (eps) | structural 0 (eps) | structural 0 (eps) | fault-model/threat-model row; qc and mixture weights - GAB |
| signal_quality.cuff_error_code | structural 0 (eps) | mixture; R: cuff_detached | structural 0 (eps) | fault-model/threat-model row; qc and mixture weights - GAB |
| cross_device.pulse_vs_ecg_hr_diff | structural 0 (eps) | mixture; R: ecg_noise | mixture; C: replay_informed, injection_naive | fault-model/threat-model row; qc and mixture weights - GAB |
| witness.identity_confirmed | structural 0 (eps) | structural 0 (eps) | mixture; C: presence_spoof_naive | D-6 of evidence-channels: how identity is checked; C3 naive spoof only - GAB |
| witness.intake_observed | mixture; divert share delta | structural 0 (eps) | mixture; C: dispense_forgery_naive, dispense_forgery_informed, dispenser_physical_tamper | delta (C1 diverted dose, 0 in the benchmark adherence model) - GAB; qc for the forgery with a co-located robot - GAB |
| crypto_temporal.authenticated | structural 0 (eps) | structural 0 (eps) | mixture; R: replay_informed, injection_naive, injection_informed, dispense_forgery_naive, dispense_forgery_informed, timestamp_manipulation | deployment property (device authenticates); None otherwise. Cell = share of C3 classes that synthesise or rewrite a message - GAB (mixture) |
| crypto_temporal.seq_gap_or_replay | structural 0 (eps) | mixture; C: ble_dropout, message_drop | mixture; R: replay_naive, dispense_forgery_naive; C: injection_naive | fault-model/threat-model row; qc and mixture weights - GAB |
| crypto_temporal.timestamp_implausible | structural 0 (eps) | mixture; R: link_delay, clock_skew | mixture; R: replay_naive, timestamp_manipulation; C: injection_naive | fault-model/threat-model row; qc and mixture weights - GAB |
| dispenser.short_interval (EXTENSION, ADR-032 proposed) | structural 0 (eps) | mixture; C: dispenser_bounce | structural 0 (eps) (timing chosen by the attacker is not modelled) | T_b (registry name dispense_bounce_interval_ms, unverified) - GAB |
| dispenser.no_content_change (EXTENSION) | structural 0 (eps) | mixture; C: dispenser_bounce | structural 0 (eps) (a forged DISPENSE has no payload: U) | content-sensing sign convention (ADR-032 note) - GAB |

#### 1.4 Numeric cells P(A | cause) at the reference point of the grid (eps .01, qc .5, uniform mixtures, fault-model family); `-` = the cause has no component for the template (impossible)
**range** (support: C1, C2, C3)
| field | C1 | C2 | C3 |
|---|---|---|---|
| system.node_lifecycle | 0.010 | 0.010 | 0.010 |
| system.diagnostics_ok | 0.010 | 0.010 | 0.010 |
| system.liveliness_ok | 0.010 | 0.010 | 0.010 |
| system.qos_deadline_missed | 0.010 | 0.010 | 0.010 |
| system.ble_link_quality | 0.010 | 0.010 | 0.010 |
| signal_quality.ecg_sqi | 0.010 | 0.010 | 0.010 |
| signal_quality.ppg_sqi | 0.010 | 0.010 | 0.010 |
| signal_quality.cuff_error_code | 0.010 | 0.010 | 0.010 |
| cross_device.pulse_vs_ecg_hr_diff | 0.010 | 0.010 | 0.255 |
| crypto_temporal.authenticated | 0.010 | 0.010 | 0.990 |
| crypto_temporal.seq_gap_or_replay | 0.010 | 0.010 | 0.133 |
| crypto_temporal.timestamp_implausible | 0.010 | 0.010 | 0.378 |

**sched** (support: C1, C2, C3)
| field | C1 | C2 | C3 |
|---|---|---|---|
| system.node_lifecycle | 0.010 | 0.206 | 0.010 |
| system.diagnostics_ok | 0.010 | 0.157 | 0.010 |
| system.liveliness_ok | 0.010 | 0.157 | 0.010 |
| system.qos_deadline_missed | 0.010 | 0.206 | 0.010 |
| system.ble_link_quality | 0.010 | 0.157 | 0.010 |
| system.nav_task_failed | 0.010 | 0.206 | 0.010 |
| system.manip_task_failed | 0.010 | 0.108 | 0.010 |
| signal_quality.cuff_error_code | 0.010 | 0.108 | 0.010 |
| crypto_temporal.authenticated | 0.010 | 0.010 | 0.663 |
| crypto_temporal.seq_gap_or_replay | 0.010 | 0.108 | 0.500 |
| crypto_temporal.timestamp_implausible | 0.010 | 0.206 | 0.827 |

**hold** (support: C1, C2, C3)
| field | C1 | C2 | C3 |
|---|---|---|---|
| system.node_lifecycle | 0.010 | 0.161 | 0.010 |
| system.diagnostics_ok | 0.010 | 0.123 | 0.010 |
| system.liveliness_ok | 0.010 | 0.123 | 0.010 |
| system.qos_deadline_missed | 0.010 | 0.161 | 0.010 |
| system.ble_link_quality | 0.010 | 0.123 | 0.010 |
| system.nav_task_failed | 0.010 | 0.161 | 0.010 |
| system.manip_task_failed | 0.010 | 0.085 | 0.010 |
| signal_quality.ecg_sqi | 0.010 | 0.010 | 0.010 |
| signal_quality.ppg_sqi | 0.010 | 0.010 | 0.010 |
| signal_quality.cuff_error_code | 0.010 | 0.085 | 0.010 |
| cross_device.pulse_vs_ecg_hr_diff | 0.010 | 0.010 | 0.133 |
| crypto_temporal.authenticated | 0.010 | 0.010 | 0.745 |
| crypto_temporal.seq_gap_or_replay | 0.010 | 0.085 | 0.316 |
| crypto_temporal.timestamp_implausible | 0.010 | 0.161 | 0.316 |
| dispenser.short_interval | 0.010 | 0.048 | 0.010 |
| dispenser.no_content_change | 0.010 | 0.048 | 0.010 |

**count** (support: C1, C2, C3)
| field | C1 | C2 | C3 |
|---|---|---|---|
| system.node_lifecycle | 0.010 | 0.418 | 0.010 |
| system.diagnostics_ok | 0.010 | 0.582 | 0.010 |
| system.liveliness_ok | 0.010 | 0.255 | 0.010 |
| system.qos_deadline_missed | 0.010 | 0.337 | 0.010 |
| system.ble_link_quality | 0.010 | 0.255 | 0.010 |
| crypto_temporal.authenticated | 0.010 | 0.010 | 0.663 |
| crypto_temporal.seq_gap_or_replay | 0.010 | 0.173 | 0.337 |
| crypto_temporal.timestamp_implausible | 0.010 | 0.173 | 0.010 |
| dispenser.short_interval | 0.010 | 0.092 | 0.010 |
| dispenser.no_content_change | 0.010 | 0.092 | 0.010 |

**resp** (support: C1, C2, C3)
| field | C1 | C2 | C3 |
|---|---|---|---|
| system.node_lifecycle | 0.010 | 0.173 | 0.010 |
| system.diagnostics_ok | 0.010 | 0.132 | 0.010 |
| system.liveliness_ok | 0.010 | 0.132 | 0.010 |
| system.qos_deadline_missed | 0.010 | 0.173 | 0.010 |
| system.ble_link_quality | 0.010 | 0.132 | 0.010 |
| system.nav_task_failed | 0.010 | 0.173 | 0.010 |
| system.manip_task_failed | 0.010 | 0.092 | 0.010 |
| signal_quality.ecg_sqi | 0.010 | 0.010 | 0.010 |
| signal_quality.ppg_sqi | 0.010 | 0.010 | 0.010 |
| signal_quality.cuff_error_code | 0.010 | 0.092 | 0.010 |
| cross_device.pulse_vs_ecg_hr_diff | 0.010 | 0.010 | 0.133 |
| witness.identity_confirmed | 0.010 | 0.010 | 0.010 |
| witness.intake_observed | 0.010 | 0.010 | 0.194 |
| crypto_temporal.authenticated | 0.010 | 0.010 | 0.745 |
| crypto_temporal.seq_gap_or_replay | 0.010 | 0.092 | 0.316 |
| crypto_temporal.timestamp_implausible | 0.010 | 0.092 | 0.316 |
| dispenser.short_interval | 0.010 | 0.051 | 0.010 |
| dispenser.no_content_change | 0.010 | 0.051 | 0.010 |

**sys** (support: C2, C3)
| field | C1 | C2 | C3 |
|---|---|---|---|
| system.node_lifecycle | - | 0.010 | 0.010 |
| system.diagnostics_ok | - | 0.010 | 0.010 |
| system.liveliness_ok | - | 0.010 | 0.010 |
| system.qos_deadline_missed | - | 0.010 | 0.010 |
| system.ble_link_quality | - | 0.010 | 0.010 |
| signal_quality.ecg_sqi | - | 0.500 | 0.010 |
| signal_quality.ppg_sqi | - | 0.010 | 0.010 |
| signal_quality.cuff_error_code | - | 0.010 | 0.010 |
| cross_device.pulse_vs_ecg_hr_diff | - | 0.990 | 0.337 |
| crypto_temporal.authenticated | - | 0.010 | 0.990 |
| crypto_temporal.seq_gap_or_replay | - | 0.010 | 0.173 |
| crypto_temporal.timestamp_implausible | - | 0.010 | 0.173 |

**int** (support: C2, C3)
| field | C1 | C2 | C3 |
|---|---|---|---|
| system.node_lifecycle | - | 0.010 | 0.010 |
| system.diagnostics_ok | - | 0.173 | 0.010 |
| system.liveliness_ok | - | 0.173 | 0.010 |
| system.qos_deadline_missed | - | 0.337 | 0.010 |
| system.ble_link_quality | - | 0.173 | 0.010 |
| system.nav_task_failed | - | 0.010 | 0.010 |
| system.manip_task_failed | - | 0.010 | 0.010 |
| crypto_temporal.authenticated | - | 0.010 | 0.402 |
| crypto_temporal.seq_gap_or_replay | - | 0.173 | 0.206 |
| crypto_temporal.timestamp_implausible | - | 0.337 | 0.010 |
| dispenser.short_interval | - | 0.173 | 0.010 |
| dispenser.no_content_change | - | 0.173 | 0.010 |

#### 1.5 Parameters of the model (none is a proposal; every number is a grid value)
| parameter | role | grid values used | where its value would have to come from | awaiting gab |
|---|---|---|---|---|
| eps | leak of every structural cell: 1-eps if a cause raises the field by construction, eps if not (reading noise, an unmodelled cause) | 0.001, 0.01, 0.05, 0.1 | device specification and literature on the false-alert rate of each channel (none collected); design choice meanwhile | yes |
| qc | probability that a conditional raise (LC, SEQ, D-5 conditions) holds | 0.25, 0.5, 0.75 | fault-model conditions LC/SEQ with the device lease, deadline and sequence provision of the real deployment (WS07-T03/EC-OP-18) | yes |
| component weights (family) | which sub-causes are in each cause's mixture and with which weights (uniform over those that can violate the template) | uniform over the fault-model/threat-model catalogue; uniform over the 8+5 subtypes injected by benchmark v1 | design choice; ward incident statistics would be the literature source (none identified) | yes |
| silent_share | total within-C2 weight of {stuck_at, cuff_silent_bias, dispenser_bounce} | uniform, 0.05, 0.25, 0.5, 0.75 | design choice (declared limit of analisi 4.8); device failure statistics | yes |
| informed_share | total within-C3 weight of the informed-level attacks | uniform, 0.25, 0.75 | threat model (attacker capability levels); design choice | yes |
| divert | share of C1 in which a dispensed dose is not taken (witness intake False) | 0, 0.1, 0.25 | adherence literature (diversion/pocketing); 0 in the benchmark adherence model (declared simplification) | yes |
| prior_t(c) | prior over causes for the template | uniform; c1_heavy (.6/.3/.1), c2_heavy (.3/.6/.1), c3_rare (.45/.5/.05), c3_heavy (.2/.2/.6): ILLUSTRATIVE | literature on alert aetiology on wards or a declared design choice; never the injection rates | yes |
| tau | abstention threshold: UNDETERMINED if max posterior < tau | 0.5, 0.67, 0.8, 0.9, 0.95, 0.99 | design choice (clinical cost of a wrong cause vs an abstention) | yes |
| T_b (extension) | interval under which two openings are a bounce | 1 s, 10 s, 30 s, 60 s, 180 s | dispenser specification; registry name proposed in ADR-032 | yes |
| profile | which channels exist: diagnostics reports, authentication, content sensing, robot witness | with / without diagnostics; authenticating or not; content sensing or not | device specification; ADR-036 | decided per run |


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


#### 3.1 Per group, reference point Params(eps=0.01, qc=0.5, prior='uniform', family='fm', silent_share=None, informed_share=None, divert=0.0, group='none', ext=False, scope='template', mask=frozenset(), tau=0.8)
| group | members | event realised | alert matched | old rule (diag OFF) C1/C2/C3/UND | old rule (diag ON) C1/C2/C3/UND | argmax = truth | UNDET @.8 | confident right @.8 | confident wrong @.8 |
|---|---|---|---|---|---|---|---|---|---|
| double_take_vs_bounce | 640 | 614 | 604 | 0/0/0/604 | 0/0/0/604 | 294/604 (48.7%; 45-53) | 604 | 0 | 0 |
| nonresponse_vs_falsified_dispense | 640 | 549 | 475 | 0/0/89/386 | 0/0/89/386 | 289/475 (60.8%; 56-65) | 386 | 89 | 0 |
| refusal_vs_robot_missed | 240 | 240 | 240 | 0/40/0/200 | 0/40/0/200 | 160/240 (66.7%; 60-72) | 240 | 0 | 0 |
| bounce_vs_forged_dispense | 640 | 640 | 560 | 0/0/116/444 | 0/0/116/444 | 116/560 (20.7%; 18-24) | 481 | 79 | 0 |
| ALL | 2160 | 2043 | 1879 | 0/40/205/1634 | 0/40/205/1634 | 859/1879 (45.7%; 43-48) | 1711 | 168 | 0 |

#### 3.2 Per variant (27), reference point; members of the variant = 80
| group | variant | matched | old C1 (OFF/ON) | argmax=truth | UND@.8 | right@.8 | wrong@.8 |
|---|---|---|---|---|---|---|---|
| bounce_vs_forg | informed_auth_content | 72/80 | 0/0 | 18 | 54 | 18 | 0 |
| bounce_vs_forg | informed_auth_nocontent | 76/80 | 0/0 | 21 | 55 | 21 | 0 |
| bounce_vs_forg | informed_noauth_content | 78/80 | 0/0 | 0 | 78 | 0 | 0 |
| bounce_vs_forg | informed_noauth_nocontent | 78/80 | 0/0 | 0 | 78 | 0 | 0 |
| bounce_vs_forg | naive_auth_content | 68/80 | 0/0 | 24 | 44 | 24 | 0 |
| bounce_vs_forg | naive_auth_nocontent | 66/80 | 0/0 | 16 | 50 | 16 | 0 |
| bounce_vs_forg | naive_noauth_content | 60/80 | 0/0 | 16 | 60 | 0 | 0 |
| bounce_vs_forg | naive_noauth_nocontent | 62/80 | 0/0 | 21 | 62 | 0 | 0 |
| double_take_vs | nominal_content_norobot | 76/80 | 0/0 | 37 | 76 | 0 | 0 |
| double_take_vs | nominal_content_robot | 76/80 | 0/0 | 37 | 76 | 0 | 0 |
| double_take_vs | nominal_nocontent_norobot | 72/80 | 0/0 | 34 | 72 | 0 | 0 |
| double_take_vs | nominal_nocontent_robot | 74/80 | 0/0 | 36 | 74 | 0 | 0 |
| double_take_vs | stress_content_norobot | 79/80 | 0/0 | 39 | 79 | 0 | 0 |
| double_take_vs | stress_content_robot | 72/80 | 0/0 | 35 | 72 | 0 | 0 |
| double_take_vs | stress_nocontent_norobot | 77/80 | 0/0 | 38 | 77 | 0 | 0 |
| double_take_vs | stress_nocontent_robot | 78/80 | 0/0 | 38 | 78 | 0 | 0 |
| nonresponse_vs | informed_norobot_auth | 53/80 | 0/0 | 51 | 26 | 27 | 0 |
| nonresponse_vs | informed_norobot_noauth | 57/80 | 0/0 | 27 | 57 | 0 | 0 |
| nonresponse_vs | informed_robot_auth | 56/80 | 0/0 | 54 | 28 | 28 | 0 |
| nonresponse_vs | informed_robot_noauth | 50/80 | 0/0 | 24 | 50 | 0 | 0 |
| nonresponse_vs | naive_norobot_auth | 68/80 | 0/0 | 42 | 54 | 14 | 0 |
| nonresponse_vs | naive_norobot_noauth | 66/80 | 0/0 | 26 | 66 | 0 | 0 |
| nonresponse_vs | naive_robot_auth | 64/80 | 0/0 | 44 | 44 | 20 | 0 |
| nonresponse_vs | naive_robot_noauth | 61/80 | 0/0 | 21 | 61 | 0 | 0 |
| refusal_vs_rob | outcome_reported | 80/80 | 0/0 | 80 | 80 | 0 | 0 |
| refusal_vs_rob | outcome_withheld | 80/80 | 0/0 | 40 | 80 | 0 | 0 |
| refusal_vs_rob | robot_absent | 80/80 | 0/0 | 40 | 80 | 0 | 0 |

#### 3.3 Threshold sweep (labelled sensitivity values), all matched members; by group
| group | tau | UNDETERMINED | confident right | confident wrong | confident C1 for true C1 / C2 / C3 |
|---|---|---|---|---|---|
| double_take_vs | 0.5 | 0 | 294 | 310 | 294/310/0 |
| double_take_vs | 0.67 | 604 | 0 | 0 | 0/0/0 |
| double_take_vs | 0.8 | 604 | 0 | 0 | 0/0/0 |
| double_take_vs | 0.9 | 604 | 0 | 0 | 0/0/0 |
| double_take_vs | 0.95 | 604 | 0 | 0 | 0/0/0 |
| double_take_vs | 0.99 | 604 | 0 | 0 | 0/0/0 |
| nonresponse_vs | 0.5 | 97 | 289 | 89 | 200/0/89 |
| nonresponse_vs | 0.67 | 282 | 191 | 2 | 102/0/2 |
| nonresponse_vs | 0.8 | 386 | 89 | 0 | 0/0/0 |
| nonresponse_vs | 0.9 | 386 | 89 | 0 | 0/0/0 |
| nonresponse_vs | 0.95 | 386 | 89 | 0 | 0/0/0 |
| nonresponse_vs | 0.99 | 475 | 0 | 0 | 0/0/0 |
| refusal_vs_rob | 0.5 | 200 | 40 | 0 | 0/0/0 |
| refusal_vs_rob | 0.67 | 240 | 0 | 0 | 0/0/0 |
| refusal_vs_rob | 0.8 | 240 | 0 | 0 | 0/0/0 |
| refusal_vs_rob | 0.9 | 240 | 0 | 0 | 0/0/0 |
| refusal_vs_rob | 0.95 | 240 | 0 | 0 | 0/0/0 |
| refusal_vs_rob | 0.99 | 240 | 0 | 0 | 0/0/0 |
| bounce_vs_forg | 0.5 | 11 | 116 | 433 | 0/308/125 |
| bounce_vs_forg | 0.67 | 249 | 116 | 195 | 0/153/42 |
| bounce_vs_forg | 0.8 | 481 | 79 | 0 | 0/0/0 |
| bounce_vs_forg | 0.9 | 481 | 79 | 0 | 0/0/0 |
| bounce_vs_forg | 0.95 | 481 | 79 | 0 | 0/0/0 |
| bounce_vs_forg | 0.99 | 520 | 40 | 0 | 0/0/0 |
| ALL | 0.5 | 308 | 739 | 832 | 494/618/214 |
| ALL | 0.67 | 1375 | 307 | 197 | 102/153/44 |
| ALL | 0.8 | 1711 | 168 | 0 | 0/0/0 |
| ALL | 0.9 | 1711 | 168 | 0 | 0/0/0 |
| ALL | 0.95 | 1711 | 168 | 0 | 0/0/0 |
| ALL | 0.99 | 1839 | 40 | 0 | 0/0/0 |

#### 3.4 Effect of the diagnostics reports (profile with vs without), matched members, reference point
| truth cause | n | V0 (diag ON) argmax right | V1 (no diag) argmax right | V0 conf. C1 @.8 | V1 conf. C1 @.8 | old rule C1 ON | old rule C1 OFF |
|---|---|---|---|---|---|---|---|
| C1 | 614 | 614 | 614 | 0 | 0 | 0 | 0 |
| C2 | 738 | 40 | 40 | 0 | 0 | 0 | 0 |
| C3 | 527 | 205 | 205 | 0 | 0 | 0 | 0 |
McNemar V0 vs V1 on 'argmax = truth' (all matched members): b (V0 right, V1 not) = 0, c = 0, exact p = 1

#### 3.5 Old rule (diag ON) vs likelihood table (kappa @ .8), matched members
| old (diag ON) | new @.8 | n | example (group, variant, pair no., member, template, posterior) |
|---|---|---|---|
| C2 | UNDETERMINED | 40 | refusal_vs_rob outcome_reported #640B sched {'C1': 0.166, 'C2': 0.669, 'C3': 0.166} |
| C3 | C3 | 168 | nonresponse_vs naive_robot_auth #362B resp {'C1': 0.031, 'C2': 0.009, 'C3': 0.96} |
| C3 | UNDETERMINED | 37 | bounce_vs_forg naive_noauth_content #846B resp {'C1': 0.051, 'C2': 0.154, 'C3': 0.795} |
| UNDETERMINED | UNDETERMINED | 1634 | double_take_vs nominal_content_robot #0A count {'C1': 0.566, 'C2': 0.055, 'C3': 0.379} |


### 3.6 Why the old rule still cannot reach C1 for the members, with diagnostics emitted

Decision row and missing fields of the old rule at the matched alert of each of the 614 C1 members (profile with diagnostics). `system.diagnostics_ok` is no longer in the list: emitting it opens only the `range` alerts of the background. What remains:


Table 3.6: Old rule on the matched alerts of C1 members of the pairs, diagnostics emitted (decision row, abstention reason, fields missing for the exclusion)
| template | row | reason | missing fields (exclusion set) | n |
|---|---|---|---|---|
| count | 8 | insufficient | - | 294 |
| sched | 8 | insufficient | ble_link_quality, nav_task_failed, manip_task_failed, cuff_error_code, seq_gap_or_replay, timestamp_implausible | 80 |
| resp | 8 | insufficient | nav_task_failed, manip_task_failed, identity_confirmed, intake_observed, authenticated | 53 |
| resp | 8 | insufficient | nav_task_failed, manip_task_failed | 52 |
| resp | 8 | insufficient | manip_task_failed | 50 |
| resp | 8 | insufficient | manip_task_failed, identity_confirmed, authenticated | 45 |
| sched | 8 | insufficient | ble_link_quality, manip_task_failed, cuff_error_code, seq_gap_or_replay, timestamp_implausible | 40 |



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


#### 4.1 Pairs, primary variant V0 full (diag ON), reference point Params(eps=0.01, qc=0.5, prior='uniform', family='fm', silent_share=None, informed_share=None, divert=0.0, group='none', ext=False, scope='template', mask=frozenset(), tau=0.8)
Pairs with a common-template match in both members; Lambda = log P(e|c_A) - log P(e|c_B) in nats (prior-free); D = Lambda_A - Lambda_B.
| group | stratum | pairs (matched/ all) | Lambda_A > 0 | Lambda_B < 0 | both (correct direction) | D > 0 | D = 0 | D < 0 | Lambda_A = 0 | Lambda_B = 0 |
|---|---|---|---|---|---|---|---|---|---|---|
| double_take_vs_bounce | dist | 256 / 280 | 256/256 (100%; 99-100) | 0/256 (0%; 0-1) | 0/256 (0%; 0-1) | 0/256 (0%; 0-1) | 256 | 0 | 0 | 0 |
| double_take_vs_bounce | indist | 38 / 40 | 38/38 (100%; 91-100) | 0/38 (0%; 0-9) | 0/38 (0%; 0-9) | 0/38 (0%; 0-9) | 38 | 0 | 0 | 0 |
| nonresponse_vs_falsified_dispense | dist | 108 / 238 | 108/108 (100%; 97-100) | 80/108 (74%; 65-81) | 80/108 (74%; 65-81) | 94/108 (87%; 79-92) | 14 | 0 | 0 | 0 |
| nonresponse_vs_falsified_dispense | indist | 53 / 82 | 53/53 (100%; 93-100) | 0/53 (0%; 0-7) | 0/53 (0%; 0-7) | 0/53 (0%; 0-7) | 53 | 0 | 0 | 0 |
| refusal_vs_robot_missed | dist | 40 / 40 | 40/40 (100%; 91-100) | 40/40 (100%; 91-100) | 40/40 (100%; 91-100) | 40/40 (100%; 91-100) | 0 | 0 | 0 | 0 |
| refusal_vs_robot_missed | indist | 80 / 80 | 80/80 (100%; 95-100) | 0/80 (0%; 0-5) | 0/80 (0%; 0-5) | 0/80 (0%; 0-5) | 80 | 0 | 0 | 0 |
| bounce_vs_forged_dispense | dist | 209 / 280 | 56/209 (27%; 21-33) | 202/209 (97%; 93-98) | 49/209 (23%; 18-30) | 123/209 (59%; 52-65) | 86 | 0 | 0 | 0 |
| bounce_vs_forged_dispense | indist | 39 / 40 | 0/39 (0%; 0-9) | 39/39 (100%; 91-100) | 0/39 (0%; 0-9) | 0/39 (0%; 0-9) | 39 | 0 | 0 | 0 |
| ALL | dist | 613 | 460/613 (75%; 71-78) | 322/613 (53%; 49-56) | 169/613 (28%; 24-31) | 257/613 (42%; 38-46) | 356 | 0 | 0 | 0 |
| ALL | indist | 210 | 171/210 (81%; 76-86) | 39/210 (19%; 14-24) | 0/210 (0%; 0-2) | 0/210 (0%; 0-2) | 210 | 0 | 0 | 0 |

Pairs by stage (all pairs of the group / both events realised / common-template alert in both members):
| group | stratum | pairs | both events realised | matched (primary template) | primary template |
|---|---|---|---|---|---|
| double_take_vs_bounce | dist | 280 | 256 | 256 | {'count': 256} |
| double_take_vs_bounce | indist | 40 | 38 | 38 | {'count': 38} |
| nonresponse_vs_falsified_dispense | dist | 238 | 169 | 108 | {'resp': 108} |
| nonresponse_vs_falsified_dispense | indist | 82 | 60 | 53 | {'resp': 53} |
| refusal_vs_robot_missed | dist | 40 | 40 | 40 | {'sched': 40} |
| refusal_vs_robot_missed | indist | 80 | 80 | 80 | {'sched': 80} |
| bounce_vs_forged_dispense | dist | 280 | 280 | 209 | {'resp': 99, 'count': 110} |
| bounce_vs_forged_dispense | indist | 40 | 40 | 39 | {'count': 37, 'resp': 2} |

#### 4.1b Same, evaluated on the alert of an alternative template (RESP of the extra opening for groups 1 and 4, where the witness fields are read; RESP for group 2; SCHED for group 3)
| group | stratum | pairs matched | both correct direction | D > 0 | D = 0 | D < 0 |
|---|---|---|---|---|---|---|
| double_take_vs_bounce | dist | 80 | 0/80 (0%; 0-5) | 0/80 (0%; 0-5) | 80 | 0 |
| double_take_vs_bounce | indist | 0 | 0/0 | 0/0 | 0 | 0 |
| nonresponse_vs_falsified_dispense | dist | 108 | 80/108 (74%; 65-81) | 94/108 (87%; 79-92) | 14 | 0 |
| nonresponse_vs_falsified_dispense | indist | 53 | 0/53 (0%; 0-7) | 0/53 (0%; 0-7) | 53 | 0 |
| refusal_vs_robot_missed | dist | 40 | 40/40 (100%; 91-100) | 40/40 (100%; 91-100) | 0 | 0 |
| refusal_vs_robot_missed | indist | 80 | 0/80 (0%; 0-5) | 0/80 (0%; 0-5) | 80 | 0 |
| bounce_vs_forged_dispense | dist | 58 | 35/58 (60%; 47-72) | 35/58 (60%; 47-72) | 23 | 0 |
| bounce_vs_forged_dispense | indist | 15 | 0/15 (0%; 0-20) | 0/15 (0%; 0-20) | 15 | 0 |

#### 4.2 Distribution of Lambda (nats) per group and stratum: min / q25 / median / q75 / max
| group | stratum | member | min | q25 | median | q75 | max |
|---|---|---|---|---|---|---|---|
| double_take_vs_bounce | dist | A | 2.322 | 2.322 | 2.322 | 2.322 | 2.322 |
| double_take_vs_bounce | dist | B | 2.322 | 2.322 | 2.322 | 2.322 | 2.322 |
| double_take_vs_bounce | dist | D | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| double_take_vs_bounce | indist | A | 2.322 | 2.322 | 2.322 | 2.322 | 2.322 |
| double_take_vs_bounce | indist | B | 2.322 | 2.322 | 2.322 | 2.322 | 2.322 |
| double_take_vs_bounce | indist | D | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| nonresponse_vs_falsified_dispense | dist | A | 0.872 | 1.941 | 2.229 | 2.434 | 2.434 |
| nonresponse_vs_falsified_dispense | dist | B | -3.438 | -3.438 | -3.438 | 0.872 | 2.229 |
| nonresponse_vs_falsified_dispense | dist | D | 0.000 | 0.205 | 5.667 | 5.667 | 5.873 |
| nonresponse_vs_falsified_dispense | indist | A | 0.872 | 0.872 | 0.872 | 1.078 | 1.078 |
| nonresponse_vs_falsified_dispense | indist | B | 0.872 | 0.872 | 0.872 | 1.078 | 1.078 |
| nonresponse_vs_falsified_dispense | indist | D | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| refusal_vs_robot_missed | dist | A | 0.983 | 0.983 | 0.983 | 0.983 | 0.983 |
| refusal_vs_robot_missed | dist | B | -1.396 | -1.396 | -1.396 | -1.396 | -1.396 |
| refusal_vs_robot_missed | dist | D | 2.380 | 2.380 | 2.380 | 2.380 | 2.380 |
| refusal_vs_robot_missed | indist | A | 0.763 | 0.763 | 0.763 | 0.763 | 0.763 |
| refusal_vs_robot_missed | indist | B | 0.763 | 0.763 | 0.763 | 0.763 | 0.763 |
| refusal_vs_robot_missed | indist | D | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| bounce_vs_forged_dispense | dist | A | -1.922 | -0.843 | -0.843 | 1.239 | 1.239 |
| bounce_vs_forged_dispense | dist | B | -6.117 | -5.951 | -1.922 | -1.640 | 1.239 |
| bounce_vs_forged_dispense | dist | D | 0.000 | 0.000 | 1.522 | 5.273 | 7.190 |
| bounce_vs_forged_dispense | indist | A | -1.922 | -1.922 | -1.922 | -1.922 | -0.118 |
| bounce_vs_forged_dispense | indist | B | -1.922 | -1.922 | -1.922 | -1.922 | -0.118 |
| bounce_vs_forged_dispense | indist | D | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |

#### 4.3 Indistinguishable stratum: pairs with D != 0 (identical streams must give D = 0 except where the pressure differs)
- double_take_vs_bounce: 0 of 38 matched indistinguishable pairs have D != 0
- nonresponse_vs_falsified_dispense: 0 of 53 matched indistinguishable pairs have D != 0
- refusal_vs_robot_missed: 0 of 80 matched indistinguishable pairs have D != 0
- bounce_vs_forged_dispense: 0 of 39 matched indistinguishable pairs have D != 0

#### 4.4 Distinguishable pairs by separating channel set (separated_by of evaluate_pair): D > 0 rate
| group | separated_by | pairs | D > 0 | D = 0 | D < 0 | mean D |
|---|---|---|---|---|---|---|
| bounce_vs_forg | content_change | 39 | 0 | 39 | 0 | 0.000 |
| bounce_vs_forg | content_change,dispense_seq | 20 | 16 | 4 | 0 | 1.218 |
| bounce_vs_forg | content_change,dispense_seq,verification | 28 | 25 | 3 | 0 | 6.419 |
| bounce_vs_forg | content_change,verification | 36 | 18 | 18 | 0 | 2.637 |
| bounce_vs_forg | dispense_seq | 22 | 21 | 1 | 0 | 1.453 |
| bounce_vs_forg | dispense_seq,verification | 26 | 22 | 4 | 0 | 6.084 |
| bounce_vs_forg | verification | 38 | 21 | 17 | 0 | 2.935 |
| double_take_vs | content_change | 39 | 0 | 39 | 0 | 0.000 |
| double_take_vs | content_change,dispense_interval | 37 | 0 | 37 | 0 | 0.000 |
| double_take_vs | content_change,dispense_interval,witness | 37 | 0 | 37 | 0 | 0.000 |
| double_take_vs | content_change,witness | 35 | 0 | 35 | 0 | 0.000 |
| double_take_vs | dispense_interval | 34 | 0 | 34 | 0 | 0.000 |
| double_take_vs | dispense_interval,witness | 36 | 0 | 36 | 0 | 0.000 |
| double_take_vs | witness | 38 | 0 | 38 | 0 | 0.000 |
| nonresponse_vs | dispense_seq | 13 | 0 | 13 | 0 | 0.000 |
| nonresponse_vs | dispense_seq,verification | 14 | 14 | 0 | 0 | 5.667 |
| nonresponse_vs | dispense_seq,verification,witness | 15 | 15 | 0 | 0 | 5.873 |
| nonresponse_vs | dispense_seq,witness | 14 | 14 | 0 | 0 | 0.205 |
| nonresponse_vs | verification | 48 | 47 | 1 | 0 | 5.549 |
| nonresponse_vs | verification,witness | 4 | 4 | 0 | 0 | 5.873 |
| refusal_vs_rob | robot_task_outcome | 40 | 40 | 0 | 0 | 2.380 |

#### 4.5 McNemar between method variants on the indicator 'D > 0' (distinguishable pairs matched in both variants); exact binomial on the discordant pairs
| group | variant X | variant Y | pairs | b (X right, Y not) | c (Y right, X not) | exact p |
|---|---|---|---|---|---|---|
| double_take_vs | V0 full (diag ON) | V1 full, no diagnostics | 256 | 0 | 0 | 1 |
| nonresponse_vs | V0 full (diag ON) | V1 full, no diagnostics | 108 | 0 | 0 | 1 |
| refusal_vs_rob | V0 full (diag ON) | V1 full, no diagnostics | 40 | 0 | 0 | 1 |
| bounce_vs_forg | V0 full (diag ON) | V1 full, no diagnostics | 209 | 0 | 0 | 1 |
| ALL | V0 full (diag ON) | V1 full, no diagnostics | 613 | 0 | 0 | 1 |
| double_take_vs | V0 full (diag ON) | V2 no witness | 256 | 0 | 0 | 1 |
| nonresponse_vs | V0 full (diag ON) | V2 no witness | 108 | 14 | 0 | 0.000122 |
| refusal_vs_rob | V0 full (diag ON) | V2 no witness | 40 | 0 | 0 | 1 |
| bounce_vs_forg | V0 full (diag ON) | V2 no witness | 209 | 0 | 0 | 1 |
| ALL | V0 full (diag ON) | V2 no witness | 613 | 14 | 0 | 0.000122 |
| double_take_vs | V0 full (diag ON) | V3 no verification | 256 | 0 | 0 | 1 |
| nonresponse_vs | V0 full (diag ON) | V3 no verification | 108 | 61 | 0 | 8.67e-19 |
| refusal_vs_rob | V0 full (diag ON) | V3 no verification | 40 | 0 | 0 | 1 |
| bounce_vs_forg | V0 full (diag ON) | V3 no verification | 209 | 39 | 0 | 3.64e-12 |
| ALL | V0 full (diag ON) | V3 no verification | 613 | 100 | 0 | 1.58e-30 |
| double_take_vs | V0 full (diag ON) | V4 no witness, no verif. | 256 | 0 | 0 | 1 |
| nonresponse_vs | V0 full (diag ON) | V4 no witness, no verif. | 108 | 94 | 0 | 1.01e-28 |
| refusal_vs_rob | V0 full (diag ON) | V4 no witness, no verif. | 40 | 0 | 0 | 1 |
| bounce_vs_forg | V0 full (diag ON) | V4 no witness, no verif. | 209 | 39 | 0 | 3.64e-12 |
| ALL | V0 full (diag ON) | V4 no witness, no verif. | 613 | 133 | 0 | 1.84e-40 |
| double_take_vs | V0 full (diag ON) | V5 + dispenser channels (ADR-032 proto) | 256 | 0 | 217 | 9.5e-66 |
| nonresponse_vs | V0 full (diag ON) | V5 + dispenser channels (ADR-032 proto) | 108 | 0 | 0 | 1 |
| refusal_vs_rob | V0 full (diag ON) | V5 + dispenser channels (ADR-032 proto) | 40 | 0 | 0 | 1 |
| bounce_vs_forg | V0 full (diag ON) | V5 + dispenser channels (ADR-032 proto) | 209 | 0 | 64 | 1.08e-19 |
| ALL | V0 full (diag ON) | V5 + dispenser channels (ADR-032 proto) | 613 | 0 | 281 | 5.15e-85 |

#### 4.6 Summary of the variants (distinguishable stratum, all groups): both-correct-direction, D > 0; indistinguishable: D = 0
| variant | dist pairs | both correct | D > 0 | D = 0 | D < 0 | indist pairs | indist D = 0 |
|---|---|---|---|---|---|---|---|
| V0 full (diag ON) | 613 | 169/613 (28%; 24-31) | 257/613 (42%; 38-46) | 356 | 0 | 210 | 210 |
| V1 full, no diagnostics | 613 | 243/613 (40%; 36-44) | 257/613 (42%; 38-46) | 356 | 0 | 210 | 210 |
| V2 no witness | 613 | 169/613 (28%; 24-31) | 243/613 (40%; 36-44) | 370 | 0 | 210 | 210 |
| V3 no verification | 613 | 40/613 (7%; 5-9) | 157/613 (26%; 22-29) | 456 | 0 | 210 | 210 |
| V4 no witness, no verif. | 613 | 40/613 (7%; 5-9) | 124/613 (20%; 17-24) | 489 | 0 | 210 | 210 |
| V5 + dispenser channels (ADR-032 proto) | 613 | 316/613 (52%; 48-55) | 538/613 (88%; 85-90) | 75 | 0 | 210 | 210 |



#### 4.7 Prototype of the dispenser channels of ADR-032 (interval since the previous opening below T_b; opening with content_change = 0), V5
T_b is a SENSITIVITY value (the analisi nominal 'below one second' is illustrative, unverified). Distinguishable pairs, primary template; D > 0 rate and both-correct-direction by group; indistinguishable stratum D = 0 count.
| T_b | group | dist pairs | D > 0 | both correct | indist pairs | indist D = 0 | indist Lambda_A > 0 |
|---|---|---|---|---|---|---|---|
| 1 s | double_take_vs_bounce | 256 | 217 | 73 | 38 | 38 | 38 |
| 1 s | nonresponse_vs_falsified_dispense | 108 | 94 | 80 | 53 | 53 | 53 |
| 1 s | refusal_vs_robot_missed | 40 | 40 | 40 | 80 | 80 | 80 |
| 1 s | bounce_vs_forged_dispense | 209 | 187 | 123 | 39 | 39 | 39 |
| 10 s | double_take_vs_bounce | 256 | 217 | 73 | 38 | 38 | 38 |
| 10 s | nonresponse_vs_falsified_dispense | 108 | 94 | 80 | 53 | 53 | 53 |
| 10 s | refusal_vs_robot_missed | 40 | 40 | 40 | 80 | 80 | 80 |
| 10 s | bounce_vs_forged_dispense | 209 | 187 | 123 | 39 | 39 | 39 |
| 30 s | double_take_vs_bounce | 256 | 217 | 73 | 38 | 38 | 38 |
| 30 s | nonresponse_vs_falsified_dispense | 108 | 94 | 80 | 53 | 53 | 53 |
| 30 s | refusal_vs_robot_missed | 40 | 40 | 40 | 80 | 80 | 80 |
| 30 s | bounce_vs_forged_dispense | 209 | 187 | 123 | 39 | 39 | 39 |
| 60 s | double_take_vs_bounce | 256 | 217 | 73 | 38 | 38 | 38 |
| 60 s | nonresponse_vs_falsified_dispense | 108 | 94 | 80 | 53 | 53 | 53 |
| 60 s | refusal_vs_robot_missed | 40 | 40 | 40 | 80 | 80 | 80 |
| 60 s | bounce_vs_forged_dispense | 209 | 187 | 123 | 39 | 39 | 39 |
| 180 s | double_take_vs_bounce | 256 | 147 | 147 | 38 | 38 | 38 |
| 180 s | nonresponse_vs_falsified_dispense | 108 | 94 | 80 | 53 | 53 | 53 |
| 180 s | refusal_vs_robot_missed | 40 | 40 | 40 | 80 | 80 | 80 |
| 180 s | bounce_vs_forged_dispense | 209 | 187 | 123 | 39 | 39 | 39 |

By variant (T_b = 10 s): groups 1 and 4, D > 0 / pairs
| group | variant | pairs | D > 0 | D = 0 | flag indist |
|---|---|---|---|---|---|
| bounce_vs_forg | informed_auth_content | 36 | 36 | 0 | False |
| bounce_vs_forg | informed_auth_nocontent | 38 | 21 | 17 | False |
| bounce_vs_forg | informed_noauth_content | 39 | 39 | 0 | False |
| bounce_vs_forg | informed_noauth_nocontent | 39 | 0 | 39 | True |
| bounce_vs_forg | naive_auth_content | 28 | 28 | 0 | False |
| bounce_vs_forg | naive_auth_nocontent | 26 | 22 | 4 | False |
| bounce_vs_forg | naive_noauth_content | 20 | 20 | 0 | False |
| bounce_vs_forg | naive_noauth_nocontent | 22 | 21 | 1 | False |
| double_take_vs | nominal_content_norobot | 37 | 36 | 1 | False |
| double_take_vs | nominal_content_robot | 37 | 37 | 0 | False |
| double_take_vs | nominal_nocontent_norobot | 34 | 34 | 0 | False |
| double_take_vs | nominal_nocontent_robot | 36 | 36 | 0 | False |
| double_take_vs | stress_content_norobot | 39 | 39 | 0 | False |
| double_take_vs | stress_content_robot | 35 | 35 | 0 | False |
| double_take_vs | stress_nocontent_norobot | 38 | 0 | 38 | True |
| double_take_vs | stress_nocontent_robot | 38 | 0 | 38 | False |


Reading of section 4.

* **Group 1 (double take against bounce): the table gives the same likelihood ratio to both members in all 294 matched pairs** (Lambda = +2.322 for A and B, D = 0). The fields that COUNT reads are all denied in both, so the ratio is the lean of the catalogue (four of five C2 components at COUNT are loud and predict a raised field), not evidence. The bounce member is leaned toward C1: this is the silent fault masquerading as C1. The witness separates the *streams* (two INTAKEs against one), but the instance-level boolean `intake_observed` reads True in both (4.1b: D = 0 for 80 of 80 pairs that have a RESP alert of the extra opening), so only the prototype dispenser fields separate them: D > 0 in 217 of 256 (T_b <= 60 s), and **at T_b = 180 s, above the double-take gap, the interval stops separating (D > 0 in 147 of 256)**; the `stress` variants (bounce gap equal to the double-take gap) are separated by content change only, and the stress variants without content sensing (`stress_nocontent_*`) by nothing (D = 0 in 38 and 38).
* **Group 2 (non-response against falsified dispense)**: D > 0 in 94 of 108; of the 14 with D = 0, 13 are the pairs separated only by `dispense_seq` (4.4: the forged sequence number is not turned into an asserted field at the RESP alert) and 1 by verification. Without verification D > 0 falls to 31% of the group-2 pairs (V3), and with neither witness nor verification to 0% (V4): in the unauthenticated variants without a robot the channels do not separate the pair, as the diagnosability matrix says.
* **Group 3**: D > 0 for 40 of 40 distinguishable pairs (the manipulation outcome); indistinguishable 80 of 80 with D = 0 (`outcome_withheld`, `robot_absent`).
* **Group 4 (bounce against forged dispense)**: Lambda_A is negative for most bounce members (a silent bounce is read as closer to the quiet forgery than to the loud mixture of C2): Lambda_A > 0 only in 56 of 209; D > 0 in 123 of 209 (the forgeries that raise authentication, sequence). `content_change`-only pairs (39): D = 0.
* **Indistinguishable stratum**: D = 0 exactly for 210 of 210 matched pairs, in all four groups (4.3); Lambda is not 0: the identical-stream pairs get the same non-zero ratio (the lean), +2.32 in group 1 and -1.92 in group 4.
* **Diagnostics** (4.5, 4.6): V0 and V1 have the same D > 0 set in all pairs; Lambda shifts by a constant, +0.861 nats in group 1, +0.161 in group 3, 0 in group 2, between -0.861 (COUNT) and -0.132 (RESP) in group 4. "Both correct direction" is higher without diagnostics (243 against 169 of 613) only because the group-4 lean moves; it is not a gain.

## 5. Main population


#### 5. Main population `m120`: 3600 patient-days, 17015 VIOLATED alerts
Alert truth (many-to-one, template- and time-compatible ground-truth event, injected events first): {None: 1272, 'C1': 11342, 'C2': 2679, 'C3': 1063, 'AMB': 659}
Strict mode (alerts compatible with events of two causes excluded): {None: 1272, 'C1': 11342, 'C2': 827, 'AMB': 3136, 'C3': 438}

#### 5.1 Log score and Brier per template, injected-first labelling; reference point Params(eps=0.01, qc=0.5, prior='uniform', family='fm', silent_share=None, informed_share=None, divert=0.0, group='none', ext=False, scope='template', mask=frozenset(), tau=0.8)
| template | n alerts | truth C1/C2/C3 | log score (nats) | Brier | prior-only log score | prior-only Brier | true cause unsupported |
|---|---|---|---|---|---|---|---|
| range | 8243 | 7506/280/457 | 0.913 | 0.560 | 1.099 | 0.667 | 0 |
| sched | 699 | 159/476/64 | 0.444 | 0.236 | 1.099 | 0.667 | 0 |
| hold | 639 | 283/256/100 | 0.808 | 0.469 | 1.099 | 0.667 | 0 |
| count | 1490 | 975/325/190 | 1.110 | 0.621 | 1.099 | 0.667 | 0 |
| resp | 4013 | 2419/1342/252 | 0.894 | 0.516 | 1.099 | 0.667 | 0 |
| ALL | 15084 | | 0.901 | 0.536 | 1.099 | 0.667 | |

#### 5.1 Log score and Brier per template, strict labelling (ambiguous alerts dropped); reference point Params(eps=0.01, qc=0.5, prior='uniform', family='fm', silent_share=None, informed_share=None, divert=0.0, group='none', ext=False, scope='template', mask=frozenset(), tau=0.8)
| template | n alerts | truth C1/C2/C3 | log score (nats) | Brier | prior-only log score | prior-only Brier | true cause unsupported |
|---|---|---|---|---|---|---|---|
| range | 7620 | 7506/37/77 | 0.892 | 0.550 | 1.099 | 0.667 | 0 |
| sched | 699 | 159/476/64 | 0.444 | 0.236 | 1.099 | 0.667 | 0 |
| hold | 503 | 283/142/78 | 0.646 | 0.367 | 1.099 | 0.667 | 0 |
| count | 1193 | 975/51/167 | 0.758 | 0.463 | 1.099 | 0.667 | 0 |
| resp | 2592 | 2419/121/52 | 0.574 | 0.287 | 1.099 | 0.667 | 0 |
| ALL | 12607 | | 0.779 | 0.463 | 1.099 | 0.667 | |

#### 5.2 Calibration curves (injected-first labelling): P(truth = c) against the stated p_c, 10 equal-width bins, count per bin (n) and observed frequency
- range / C1: [0.0,0.1) n=109 obs=0.20; [0.1,0.2) n=75 obs=0.31; [0.3,0.4) n=25 obs=0.92; [0.4,0.5) n=8034 obs=0.93
- range / C2: [0.0,0.1) n=109 obs=0.01; [0.1,0.2) n=75 obs=0.00; [0.3,0.4) n=25 obs=0.04; [0.4,0.5) n=8034 obs=0.03
- range / C3: [0.1,0.2) n=8034 obs=0.04; [0.2,0.3) n=25 obs=0.04; [0.7,0.8) n=75 obs=0.69; [0.8,0.9) n=109 obs=0.79
- sched / C1: [0.0,0.1) n=317 obs=0.00; [0.1,0.2) n=167 obs=0.00; [0.2,0.3) n=9 obs=0.00; [0.4,0.5) n=202 obs=0.78; [0.7,0.8) n=4 obs=0.00
- sched / C2: [0.1,0.2) n=258 obs=0.15; [0.2,0.3) n=3 obs=0.00; [0.6,0.7) n=123 obs=1.00; [0.7,0.8) n=53 obs=1.00; [0.8,0.9) n=55 obs=0.98; [0.9,1.0) n=207 obs=1.00
- sched / C3: [0.0,0.1) n=275 obs=0.01; [0.1,0.2) n=167 obs=0.00; [0.4,0.5) n=202 obs=0.02; [0.7,0.8) n=3 obs=1.00; [0.8,0.9) n=52 obs=1.00
- hold / C1: [0.0,0.1) n=108 obs=0.02; [0.1,0.2) n=73 obs=0.00; [0.2,0.3) n=5 obs=0.00; [0.3,0.4) n=45 obs=0.11; [0.4,0.5) n=264 obs=0.69; [0.5,0.6) n=144 obs=0.65
- hold / C2: [0.0,0.1) n=15 obs=0.07; [0.1,0.2) n=402 obs=0.27; [0.2,0.3) n=73 obs=0.04; [0.6,0.7) n=55 obs=0.95; [0.7,0.8) n=11 obs=1.00; [0.8,0.9) n=20 obs=0.90; [0.9,1.0) n=63 obs=1.00
- hold / C3: [0.0,0.1) n=83 obs=0.00; [0.1,0.2) n=63 obs=0.00; [0.2,0.3) n=144 obs=0.06; [0.3,0.4) n=55 obs=0.76; [0.4,0.5) n=257 obs=0.06; [0.7,0.8) n=21 obs=1.00; [0.8,0.9) n=15 obs=0.87; [0.9,1.0) n=1 obs=1.00
- count / C1: [0.0,0.1) n=16 obs=0.00; [0.4,0.5) n=384 obs=0.55; [0.5,0.6) n=1090 obs=0.70
- count / C2: [0.0,0.1) n=1474 obs=0.22; [0.6,0.7) n=16 obs=0.00
- count / C3: [0.3,0.4) n=1106 obs=0.17; [0.4,0.5) n=384 obs=0.00
- resp / C1: [0.0,0.1) n=152 obs=0.01; [0.1,0.2) n=81 obs=0.01; [0.2,0.3) n=20 obs=0.00; [0.3,0.4) n=70 obs=0.59; [0.4,0.5) n=93 obs=0.68; [0.5,0.6) n=365 obs=0.51; [0.6,0.7) n=3232 obs=0.66
- resp / C2: [0.0,0.1) n=33 obs=0.33; [0.1,0.2) n=3676 obs=0.30; [0.2,0.3) n=100 obs=0.32; [0.6,0.7) n=67 obs=0.96; [0.7,0.8) n=25 obs=0.12; [0.8,0.9) n=26 obs=1.00; [0.9,1.0) n=86 obs=1.00
- resp / C3: [0.0,0.1) n=134 obs=0.00; [0.1,0.2) n=43 obs=0.00; [0.2,0.3) n=3622 obs=0.05; [0.3,0.4) n=159 obs=0.21; [0.4,0.5) n=6 obs=0.00; [0.7,0.8) n=25 obs=0.68; [0.8,0.9) n=18 obs=0.94; [0.9,1.0) n=6 obs=0.33

Top-label expected calibration error (10 bins), per template: {'range': 0.502, 'sched': 0.202, 'hold': 0.195, 'count': 0.13, 'resp': 0.067}

#### 5.3 Silent-fault alerts (stuck_at, cuff_silent_bias, dispenser_bounce): posterior and old rule
alerts matched to silent faults: 433
| subtype | argmax | kappa @ .8 | n |
|---|---|---|---|
| cuff_silent_bias | C1 | UNDETERMINED | 248 |
| cuff_silent_bias | C2 | C2 | 2 |
| cuff_silent_bias | C2 | UNDETERMINED | 4 |
| cuff_silent_bias | C3 | C3 | 2 |
| dispenser_bounce | C1 | UNDETERMINED | 40 |
| stuck_at | C1 | UNDETERMINED | 137 |
old rule, diagnostics emitted: {('cuff_silent_bias', 'C1'): 182, ('stuck_at', 'C1'): 96, ('stuck_at', 'UNDETERMINED'): 41, ('cuff_silent_bias', 'UNDETERMINED'): 68, ('dispenser_bounce', 'UNDETERMINED'): 40, ('cuff_silent_bias', 'C2'): 6}
old rule, no diagnostics: {('cuff_silent_bias', 'UNDETERMINED'): 250, ('stuck_at', 'UNDETERMINED'): 137, ('dispenser_bounce', 'UNDETERMINED'): 40, ('cuff_silent_bias', 'C2'): 6}



#### 5.4 Sensitivity of the main-population scores (reference table parameters unless stated)
| setting | alerts scored | log score | Brier |
|---|---|---|---|
| m120 (default profile), labelling injected, window 1 h | 14174 | 0.778 | 0.456 |
| m120 (default profile), labelling injected, window 6 h | 14554 | 0.832 | 0.493 |
| m120 (default profile), labelling injected, window 24 h | 15084 | 0.901 | 0.536 |
| m120 (default profile), labelling strict, window 1 h | 13436 | 0.756 | 0.443 |
| m120 (default profile), labelling strict, window 6 h | 13038 | 0.768 | 0.454 |
| m120 (default profile), labelling strict, window 24 h | 12607 | 0.779 | 0.463 |
| r40 (authenticating dispenser + content sensing), labelling injected, window 1 h | 4799 | 0.710 | 0.412 |
| r40 (authenticating dispenser + content sensing), labelling injected, window 6 h | 4937 | 0.751 | 0.446 |
| r40 (authenticating dispenser + content sensing), labelling injected, window 24 h | 5128 | 0.828 | 0.500 |
| r40 (authenticating dispenser + content sensing), labelling strict, window 1 h | 4557 | 0.686 | 0.395 |
| r40 (authenticating dispenser + content sensing), labelling strict, window 6 h | 4444 | 0.691 | 0.404 |
| r40 (authenticating dispenser + content sensing), labelling strict, window 24 h | 4318 | 0.716 | 0.422 |
| m120, injected, 24 h, profile WITHOUT diagnostics | 15084 | 0.894 | 0.536 |
| m120, injected, 24 h, prior uniform | 15084 | 0.901 | 0.536 |
| m120, injected, 24 h, prior c1_heavy | 15084 | 0.708 | 0.397 |
| m120, injected, 24 h, prior c2_heavy | 15084 | 0.997 | 0.680 |
| m120, injected, 24 h, prior c3_rare | 15084 | 0.844 | 0.534 |
| m120, injected, 24 h, prior c3_heavy | 15084 | 1.181 | 0.718 |
| m120, injected, 24 h, prior = benchmark class frequency per template (CIRCULAR DIAGNOSTIC, not a method) | 15084 | 0.573 | 0.312 |

Per template, benchmark-frequency-prior diagnostic: range: n=8243 log=0.333 Brier=0.152 (class counts {'C1': 7506, 'C3': 457, 'C2': 280}); resp: n=4013 log=0.879 Brier=0.541 (class counts {'C1': 2419, 'C2': 1342, 'C3': 252}); sched: n=699 log=0.381 Brier=0.222 (class counts {'C2': 476, 'C1': 159, 'C3': 64}); hold: n=639 log=0.733 Brier=0.425 (class counts {'C2': 256, 'C3': 100, 'C1': 283}); count: n=1490 log=1.096 Brier=0.572 (class counts {'C2': 325, 'C1': 975, 'C3': 190})

#### 5.5 Attributed cause against the truth cause of the matched alert: old rule (diagnostics emitted / not) and likelihood table (argmax; kappa at tau .8), m120, injected-first labelling
- old rule, diagnostics emitted: truth C1: C1=7342, C2=39, UNDETERMINED=3961; truth C2: C1=278, C2=761, UNDETERMINED=1640; truth C3: C1=312, C2=98, C3=5, UNDETERMINED=648
- old rule, no diagnostics: truth C1: C2=39, UNDETERMINED=11303; truth C2: C2=694, UNDETERMINED=1985; truth C3: C2=98, C3=5, UNDETERMINED=960
- table, argmax: truth C1: C1=11292, C2=3, C3=47; truth C2: C1=1905, C2=760, C3=14; truth C3: C1=755, C2=44, C3=264
- table, kappa at .8: truth C1: C2=3, C3=23, UNDETERMINED=11316; truth C2: C2=454, C3=7, UNDETERMINED=2218; truth C3: C3=171, UNDETERMINED=892
- table, kappa at .5: truth C1: C1=3170, C2=3, C3=47, UNDETERMINED=8122; truth C2: C1=1321, C2=760, C3=14, UNDETERMINED=584; truth C3: C1=344, C2=44, C3=264, UNDETERMINED=411
- table, argmax, C1-heavy illustrative prior: truth C1: C1=11293, C2=3, C3=46; truth C2: C1=1912, C2=760, C3=7; truth C3: C1=772, C2=44, C3=247


Notes on section 5.

* **Population.** Ordinary builder (`run_main.py m120 120 30 default`): 120 virtual patients x 30 days, seed 0, fault-free background (ADR-071) plus the injections of the research registry (rates 0.3 / 0.3 / 0.2 for C1 / C2 / C3: placeholders), default device profile (no authentication, no content sensing) and, in `r40`, an authenticating dispenser with content sensing. Measured-only monitor with the history of the previous day (the builder's `history_days` is 1 for this configuration; the `ours` history mode); tail-day closing-step events are not used. Predicted alerts are UNDETERMINED by definition and are not scored.
* **Truth of an alert** (scoring code only): the ground-truth events of the day whose template set contains the alert's template and whose time window (first decidable time, end of the event, plus 24 h) contains the decision time; if the compatible events have one cause that is the truth, if two causes the injected one (injected-first) or the alert is dropped (strict). 1 272 alerts match no event (false alarms of the background) and are not scored; 659 are ambiguous. Alerts of one event are correlated; no patient-level bootstrap was run.
* **The uniform prior is not the base rate of the benchmark and the calibration curves show it**: at `range` the table states C1 = 0.41 for 8 034 alerts of which 93% are C1, because nothing in the evidence separates C1 from the silent C2 at `range` (the only C2 components that can violate `range` are silent), so the posterior is the prior odds. The row "prior = benchmark class frequency" is a labelled circular diagnostic (log score 0.573) that shows how much of the miscalibration is the prior and not the cells; it is not a method.
* The old rule has no probability, so there is no old-rule log score; its confusion is in 5.5.

## 6. Sensitivity

One-at-a-time sweeps from the reference point over every parameter of the model, the evidence-set variants, a full factorial over eps x qc x prior x silent share x grouping (900 combinations), and the silent-fault shares by eps and silent share. `scripts/sweeps.py`, `scripts/sweeps_report.py`, `logs/sweeps.log`.


#### 6.1 One-at-a-time sweeps from the reference point (eps .01, qc .5, uniform prior, fm family, uniform mixtures, no grouping, tau .8)
Columns. Pairs (distinguishable, primary template): D>0 rate per group g1 double_take_vs_bounce / g2 nonresponse / g3 refusal / g4 bounce_vs_forged; mean Lambda_A of the indistinguishable stratum per group (lean toward c_A, nats). Members (1879 matched, own match): argmax = truth, UND / confident right / confident wrong at the row's tau, confident C1 for a member whose truth is not C1, confident-C1 bounce members (of 618). Main population (m120): log score, Brier, silent-fault alerts with confident C1 / with argmax C1 (of n).

| parameter | value | D>0 g1/g2/g3/g4 | indist mean Lambda_A g1/g2/g3/g4 | argmax=truth /1879 | UND / right / wrong | conf. C1 for non-C1 | bounce members with conf. C1 (of 618: g1 B + g4 A) | main log / Brier | silent conf C1 / argmax C1 (of n) |
|---|---|---|---|---|---|---|---|---|---|
| eps | 0.001 | 0.00/0.87/1.00/0.59 | 2.35/0.98/0.77/-1.85 | 859 | 1634 / 245 / 0 | 0 | 0/618 | 0.905 / 0.536 | 0 / 425 (of 433) |
| eps | 0.01 | 0.00/0.87/1.00/0.59 | 2.32/0.97/0.76/-1.83 | 859 | 1711 / 168 / 0 | 0 | 0/618 | 0.901 / 0.536 | 0 / 425 (of 433) |
| eps | 0.05 | 0.00/0.87/1.00/0.59 | 2.19/0.92/0.73/-1.72 | 859 | 1741 / 138 / 0 | 0 | 0/618 | 0.923 / 0.549 | 0 / 428 (of 433) |
| eps | 0.1 | 0.00/0.87/1.00/0.59 | 2.02/0.85/0.68/-1.59 | 819 | 1839 / 40 / 0 | 0 | 0/618 | 0.943 / 0.563 | 0 / 429 (of 433) |
| qc | 0.25 | 0.00/0.87/1.00/0.59 | 1.86/0.76/0.53/-1.39 | 859 | 1674 / 205 / 0 | 0 | 0/618 | 0.923 / 0.548 | 0 / 425 (of 433) |
| qc | 0.5 | 0.00/0.87/1.00/0.59 | 2.32/0.97/0.76/-1.83 | 859 | 1711 / 168 / 0 | 0 | 0/618 | 0.901 / 0.536 | 0 / 425 (of 433) |
| qc | 0.75 | 0.00/0.87/1.00/0.59 | 2.84/1.18/1.02/-2.32 | 859 | 1711 / 168 / 0 | 0 | 0/618 | 0.892 / 0.531 | 0 / 425 (of 433) |
| prior | uniform | 0.00/0.87/1.00/0.59 | 2.32/0.97/0.76/-1.83 | 859 | 1711 / 168 / 0 | 0 | 0/618 | 0.901 / 0.536 | 0 / 425 (of 433) |
| prior | c1_heavy | 0.00/0.87/1.00/0.59 | 2.32/0.97/0.76/-1.83 | 859 | 524 / 579 / 776 | 776 | 610/618 | 0.708 / 0.397 | 141 / 425 (of 433) |
| prior | c2_heavy | 0.00/0.87/1.00/0.59 | 2.32/0.97/0.76/-1.83 | 822 | 1671 / 208 / 0 | 0 | 0/618 | 0.997 / 0.680 | 0 / 146 (of 433) |
| prior | c3_rare | 0.00/0.87/1.00/0.59 | 2.32/0.97/0.76/-1.83 | 822 | 768 / 411 / 700 | 700 | 590/618 | 0.844 / 0.534 | 23 / 146 (of 433) |
| prior | c3_heavy | 0.00/0.87/1.00/0.59 | 2.32/0.97/0.76/-1.83 | 625 | 1674 / 205 / 0 | 0 | 0/618 | 1.181 / 0.718 | 0 / 0 (of 433) |
| family | fm | 0.00/0.87/1.00/0.59 | 2.32/0.97/0.76/-1.83 | 859 | 1711 / 168 / 0 | 0 | 0/618 | 0.901 / 0.536 | 0 / 425 (of 433) |
| family | v1 | 0.00/0.87/1.00/0.59 | 2.62/1.08/1.23/-1.83 | 859 | 1495 / 205 / 179 | 179 | 144/618 | 0.899 / 0.534 | 0 / 425 (of 433) |
| silent_share | None | 0.00/0.87/1.00/0.59 | 2.32/0.97/0.76/-1.83 | 859 | 1711 / 168 / 0 | 0 | 0/618 | 0.901 / 0.536 | 0 / 425 (of 433) |
| silent_share | 0.05 | 0.00/0.87/1.00/0.59 | 2.79/0.97/0.76/-2.29 | 859 | 1674 / 205 / 0 | 0 | 0/618 | 0.921 / 0.541 | 0 / 425 (of 433) |
| silent_share | 0.25 | 0.00/0.87/1.00/0.59 | 2.02/0.97/0.76/-1.55 | 859 | 1711 / 168 / 0 | 0 | 0/618 | 0.897 / 0.535 | 0 / 425 (of 433) |
| silent_share | 0.5 | 0.00/0.87/1.00/0.59 | 1.24/0.97/0.76/-0.78 | 859 | 1711 / 168 / 0 | 0 | 0/618 | 0.881 / 0.530 | 0 / 425 (of 433) |
| silent_share | 0.75 | 0.00/0.87/1.00/0.59 | 0.58/0.97/0.76/-0.13 | 859 | 1674 / 205 / 0 | 0 | 0/618 | 0.879 / 0.532 | 0 / 425 (of 433) |
| informed_share | None | 0.00/0.87/1.00/0.59 | 2.32/0.97/0.76/-1.83 | 859 | 1711 / 168 / 0 | 0 | 0/618 | 0.901 / 0.536 | 0 / 425 (of 433) |
| informed_share | 0.25 | 0.00/0.87/1.00/0.59 | 2.32/1.46/0.76/-0.90 | 859 | 1495 / 205 / 179 | 179 | 144/618 | 0.853 / 0.515 | 0 / 425 (of 433) |
| informed_share | 0.75 | 0.00/0.87/1.00/0.59 | 2.32/0.58/0.76/-1.96 | 859 | 1711 / 168 / 0 | 0 | 0/618 | 0.950 / 0.561 | 0 / 425 (of 433) |
| divert | 0.0 | 0.00/0.87/1.00/0.59 | 2.32/0.97/0.76/-1.83 | 859 | 1711 / 168 / 0 | 0 | 0/618 | 0.901 / 0.536 | 0 / 425 (of 433) |
| divert | 0.1 | 0.00/0.87/1.00/0.59 | 2.32/0.92/0.76/-1.83 | 859 | 1711 / 168 / 0 | 0 | 0/618 | 0.902 / 0.537 | 0 / 425 (of 433) |
| divert | 0.25 | 0.00/0.74/1.00/0.59 | 2.32/0.84/0.76/-1.83 | 859 | 1674 / 205 / 0 | 0 | 0/618 | 0.906 / 0.539 | 0 / 425 (of 433) |
| group | none | 0.00/0.87/1.00/0.59 | 2.32/0.97/0.76/-1.83 | 859 | 1711 / 168 / 0 | 0 | 0/618 | 0.901 / 0.536 | 0 / 425 (of 433) |
| group | g1 | 0.00/0.87/1.00/0.59 | 2.14/0.97/0.76/-1.65 | 859 | 1674 / 205 / 0 | 0 | 0/618 | 0.833 / 0.477 | 0 / 422 (of 433) |
| group | g2 | 0.00/0.87/1.00/0.59 | 1.72/0.93/0.53/-1.23 | 859 | 1634 / 245 / 0 | 0 | 0/618 | 0.884 / 0.532 | 0 / 427 (of 433) |
| scope | template | 0.00/0.87/1.00/0.59 | 2.32/0.97/0.76/-1.83 | 859 | 1711 / 168 / 0 | 0 | 0/618 | 0.901 / 0.536 | 0 / 425 (of 433) |
| scope | all | 0.00/0.87/1.00/0.59 | 0.91/0.75/0.79/-0.35 | 859 | 1674 / 205 / 0 | 0 | 0/618 | 0.776 / 0.432 | 0 / 425 (of 433) |
| tau | 0.5 | 0.00/0.87/1.00/0.59 | 2.32/0.97/0.76/-1.83 | 859 | 308 / 739 / 832 | 832 | 618/618 | 0.901 / 0.536 | 141 / 425 (of 433) |
| tau | 0.67 | 0.00/0.87/1.00/0.59 | 2.32/0.97/0.76/-1.83 | 859 | 1375 / 307 / 197 | 197 | 153/618 | 0.901 / 0.536 | 0 / 425 (of 433) |
| tau | 0.8 | 0.00/0.87/1.00/0.59 | 2.32/0.97/0.76/-1.83 | 859 | 1711 / 168 / 0 | 0 | 0/618 | 0.901 / 0.536 | 0 / 425 (of 433) |
| tau | 0.9 | 0.00/0.87/1.00/0.59 | 2.32/0.97/0.76/-1.83 | 859 | 1711 / 168 / 0 | 0 | 0/618 | 0.901 / 0.536 | 0 / 425 (of 433) |
| tau | 0.95 | 0.00/0.87/1.00/0.59 | 2.32/0.97/0.76/-1.83 | 859 | 1711 / 168 / 0 | 0 | 0/618 | 0.901 / 0.536 | 0 / 425 (of 433) |
| tau | 0.99 | 0.00/0.87/1.00/0.59 | 2.32/0.97/0.76/-1.83 | 859 | 1839 / 40 / 0 | 0 | 0/618 | 0.901 / 0.536 | 0 / 425 (of 433) |

#### 6.2 Variants of the evidence set at the reference point
| variant | D>0 g1/g2/g3/g4 | argmax=truth | UND / right / wrong | main log / Brier |
|---|---|---|---|---|
| no_witness | 0.00/0.74/1.00/0.59 | 859 | 1674 / 205 / 0 | 0.909 / 0.540 |
| no_verification | 0.00/0.31/1.00/0.40 | 731 | 1879 / 0 / 0 | 0.901 / 0.536 |
| neither | 0.00/0.00/1.00/0.40 | 731 | 1802 / 77 / 0 | 0.909 / 0.540 |
| no_diagnostics_profile | 0.00/0.87/1.00/0.59 | 859 | 1711 / 168 / 0 | 0.894 / 0.536 |

#### 6.3 Full factorial over eps x qc x prior x silent_share x grouping (900 combinations): range of the headline quantities
| quantity | min | max | where |
|---|---|---|---|
| D>0 rate, double_take_vs_bounce | 0.000 | 0.000 | min at eps=0.001 qc=0.25 prior=uniform silent=None group=none; max at eps=0.001 qc=0.25 prior=uniform silent=None group=none |
| D>0 rate, nonresponse_vs_falsified_dispense | 0.870 | 0.870 | min at eps=0.001 qc=0.25 prior=uniform silent=None group=none; max at eps=0.001 qc=0.25 prior=uniform silent=None group=none |
| D>0 rate, refusal_vs_robot_missed | 1.000 | 1.000 | min at eps=0.001 qc=0.25 prior=uniform silent=None group=none; max at eps=0.001 qc=0.25 prior=uniform silent=None group=none |
| D>0 rate, bounce_vs_forged_dispense | 0.589 | 0.589 | min at eps=0.001 qc=0.25 prior=uniform silent=None group=none; max at eps=0.001 qc=0.25 prior=uniform silent=None group=none |
| D>0 rate, all distinguishable pairs | 0.419 | 0.419 | min at eps=0.001 qc=0.25 prior=uniform silent=None group=none; max at eps=0.001 qc=0.25 prior=uniform silent=None group=none |
| both-correct-direction, all distinguishable pairs | 0.210 | 0.396 | min at eps=0.05 qc=0.75 prior=uniform silent=None group=none; max at eps=0.001 qc=0.25 prior=uniform silent=0.5 group=none |
| members with argmax = truth (of 1879) | 519 | 983 | min at eps=0.1 qc=0.25 prior=c2_heavy silent=0.5 group=g1; max at eps=0.001 qc=0.25 prior=c2_heavy silent=0.75 group=none |
| confident right members @ tau .8 | 0 | 739 | min at eps=0.05 qc=0.25 prior=c3_rare silent=None group=none; max at eps=0.001 qc=0.5 prior=c1_heavy silent=0.05 group=g1 |
| confident wrong members @ tau .8 | 0 | 940 | min at eps=0.001 qc=0.25 prior=uniform silent=None group=none; max at eps=0.001 qc=0.5 prior=c1_heavy silent=0.05 group=none |
| confident C1 for members whose truth is not C1 @ .8 | 0 | 940 | min at eps=0.001 qc=0.25 prior=uniform silent=None group=none; max at eps=0.001 qc=0.5 prior=c1_heavy silent=0.05 group=none |
| bounce members (618) with confident C1 @ .8 | 0 | 618 | min at eps=0.001 qc=0.25 prior=uniform silent=None group=none; max at eps=0.001 qc=0.5 prior=c1_heavy silent=None group=none |
| main log score (nats) | 0.567 | 1.322 | min at eps=0.001 qc=0.25 prior=c3_rare silent=0.05 group=g1; max at eps=0.1 qc=0.25 prior=c3_heavy silent=0.05 group=none |
| main Brier | 0.306 | 0.826 | min at eps=0.001 qc=0.25 prior=c3_rare silent=0.05 group=g1; max at eps=0.1 qc=0.25 prior=c3_heavy silent=0.05 group=none |
| silent-fault alerts with confident C1 @ .8 (share) | 0.000 | 0.968 | min at eps=0.001 qc=0.25 prior=uniform silent=None group=none; max at eps=0.001 qc=0.5 prior=c1_heavy silent=0.05 group=g1 |
| silent-fault alerts with argmax C1 (share) | 0.000 | 1.000 | min at eps=0.001 qc=0.25 prior=c2_heavy silent=0.5 group=g2; max at eps=0.1 qc=0.25 prior=c1_heavy silent=0.75 group=none |

#### 6.4 Silent-fault alerts of the main population (stuck_at, cuff_silent_bias, dispenser_bounce): share with confident C1 at tau .8 and with argmax C1, by eps and silent share (uniform prior, qc .5, no grouping)
| eps | silent share | confident C1 | argmax C1 | n |
|---|---|---|---|---|
| 0.001 | None | 0 | 425 | 433 |
| 0.001 | 0.05 | 0 | 425 | 433 |
| 0.001 | 0.25 | 0 | 425 | 433 |
| 0.001 | 0.5 | 0 | 425 | 433 |
| 0.001 | 0.75 | 0 | 425 | 433 |
| 0.01 | None | 0 | 425 | 433 |
| 0.01 | 0.05 | 0 | 425 | 433 |
| 0.01 | 0.25 | 0 | 425 | 433 |
| 0.01 | 0.5 | 0 | 425 | 433 |
| 0.01 | 0.75 | 0 | 425 | 433 |
| 0.05 | None | 0 | 428 | 433 |
| 0.05 | 0.05 | 0 | 428 | 433 |
| 0.05 | 0.25 | 0 | 428 | 433 |
| 0.05 | 0.5 | 0 | 427 | 433 |
| 0.05 | 0.75 | 0 | 425 | 433 |
| 0.1 | None | 0 | 429 | 433 |
| 0.1 | 0.05 | 0 | 429 | 433 |
| 0.1 | 0.25 | 0 | 429 | 433 |
| 0.1 | 0.5 | 0 | 429 | 433 |
| 0.1 | 0.75 | 0 | 429 | 433 |

#### 6.5 The same with the C1-heavy illustrative prior (0.6/0.3/0.1)
| eps | silent share | confident C1 | argmax C1 | n |
|---|---|---|---|---|
| 0.001 | None | 141 | 425 | 433 |
| 0.001 | 0.05 | 141 | 425 | 433 |
| 0.001 | 0.25 | 141 | 425 | 433 |
| 0.001 | 0.5 | 0 | 425 | 433 |
| 0.001 | 0.75 | 0 | 425 | 433 |
| 0.01 | None | 141 | 425 | 433 |
| 0.01 | 0.05 | 141 | 425 | 433 |
| 0.01 | 0.25 | 141 | 425 | 433 |
| 0.01 | 0.5 | 0 | 425 | 433 |
| 0.01 | 0.75 | 0 | 425 | 433 |
| 0.05 | None | 141 | 431 | 433 |
| 0.05 | 0.05 | 141 | 431 | 433 |
| 0.05 | 0.25 | 141 | 431 | 433 |
| 0.05 | 0.5 | 0 | 431 | 433 |
| 0.05 | 0.75 | 0 | 431 | 433 |
| 0.1 | None | 135 | 431 | 433 |
| 0.1 | 0.05 | 141 | 431 | 433 |
| 0.1 | 0.25 | 135 | 431 | 433 |
| 0.1 | 0.5 | 0 | 431 | 433 |
| 0.1 | 0.75 | 0 | 433 | 433 |


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


## 9. Follow-up of 2026-10-11 (decision 1 taken: the output is a set of subtypes)

### 9.0 What changed, and what did not

* **Decision recorded.** gab chose a SET of causes at the level of SUBTYPES: the most probable subtypes up to a declared cumulative probability (0.8, 0.9 and 0.95 are sensitivity values; 0.9 is the printed row); UNDETERMINED is the full set of the subtypes applicable at the alert's template. Metrics: coverage (the true subtype is in the set) and mean set size.
* **Sections 0 to 8 are unchanged**, and so are their numbers. The class-level module `likelihood_attr.py` is untouched; everything new is in `subtype_model.py`, `config/subtype_priors.yaml` and the scripts of section 9.8. The pairs and the main population were rebuilt with the same seeds to also store the cuff readings (`p40b`, `m120b`): 0 of 10 662 pair alerts differ from the earlier build and the main population has the same 3600 days and 17 015 alerts. One change to the generator copy: an optional counterfactual switch `RALMON_DIAG_IDLE_STALE_MS` in `driver_diag.py` (off by default; section 9.2.5). No generator defect was found (9.2.3).
* **The subtype model.** p(s | e, t) is proportional to prior_t(class(s)) times pi(s | class, t) times the product over the fields of P(class_f | s): the channels are independent given the SUB-CAUSE (the latent-class variant G2 of section 1.1), the class posterior is the sum over the sub-causes of a class, and a subtype merges the knowledge levels of replay, dispense_forgery and presence_spoof. C1 now has its own subtypes (double_take, dose_omission, spontaneous_count at `count`; drug_nonresponse, spontaneous_resp at `resp`; hypertensive_spike, spontaneous_range at `range`; hypotension_below_hold, spontaneous_hold at `hold`; measurement_refusal at `sched`), all with the same all-eps cells.
* **pi(subtype | class) is explicit** in `/tmp/research/likelihood/config/subtype_priors.yaml` as RELATIVE weights normalised over the sub-causes applicable at the template. Designs (all sensitivity values; none is a proposal): `uniform` (reference), `quiet_rare` (the quiet sub-causes get weight 0.25: the silent faults stuck_at, cuff_silent_bias, dispenser_bounce; the informed-level attacks; the spontaneous C1 events), `quiet_common` (weight 4), the last two labelled illustrative. Where the values would have to come from: ward incident statistics and device failure data (none collected); awaiting gab.
* **Truth.** The true subtype is the subtype of the ground-truth event matched to the alert (scoring side only). Three labellings of the main population are reported because item 2 shows that the labelling matters: the labelling of section 5; the same with the dropout target restricted to the template's data scope ("scope-aware"); and "tight" (scope-aware and the alert decided while the event window is open).

### 9.1 Pairs at the level of subtypes


#### 9.1.1 Subtype level, variant V0, design uniform, reference point of the cells (eps .01, qc .5)
Lambda = log P(e | subtype_A) - log P(e | subtype_B) at the alert of the common template; pairs, strata and matching as in section 4. Subtype pairs: g1 double_take against dispenser_bounce; g2 drug_nonresponse against dispense_forgery; g3 measurement_refusal against manipulation_failure; g4 dispenser_bounce against dispense_forgery.
| group | stratum | pairs | Lambda_A > 0 | Lambda_B < 0 | both (correct direction) | D > 0 | D = 0 | D < 0 | median Lambda_A (nats) | median Lambda_B | class-level median Lambda_A (section 4.2) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| double_take_vs_bounce | dist | 256 | 0/256 (0%; 0-1) | 0/256 (0%; 0-1) | 0/256 (0%; 0-1) | 0/256 (0%; 0-1) | 256 | 0 | 0.000 | 0.000 | 2.322 |
| double_take_vs_bounce | indist | 38 | 0/38 (0%; 0-9) | 0/38 (0%; 0-9) | 0/38 (0%; 0-9) | 0/38 (0%; 0-9) | 38 | 0 | 0.000 | 0.000 | 2.322 |
| nonresponse_vs_falsified_dispense | dist | 108 | 108/108 (100%; 97-100) | 80/108 (74%; 65-81) | 80/108 (74%; 65-81) | 94/108 (87%; 79-92) | 14 | 0 | 5.278 | -3.912 | 2.229 |
| nonresponse_vs_falsified_dispense | indist | 53 | 53/53 (100%; 93-100) | 0/53 (0%; 0-7) | 0/53 (0%; 0-7) | 0/53 (0%; 0-7) | 53 | 0 | 0.683 | 0.683 | 0.872 |
| refusal_vs_robot_missed | dist | 40 | 0/40 (0%; 0-9) | 40/40 (100%; 91-100) | 0/40 (0%; 0-9) | 40/40 (100%; 91-100) | 0 | 0 | 0.000 | -4.595 | 0.983 |
| refusal_vs_robot_missed | indist | 80 | 0/80 (0%; 0-5) | 0/80 (0%; 0-5) | 0/80 (0%; 0-5) | 0/80 (0%; 0-5) | 80 | 0 | 0.000 | 0.000 | 0.763 |
| bounce_vs_forged_dispense | dist | 209 | 209/209 (100%; 98-100) | 123/209 (59%; 52-65) | 123/209 (59%; 52-65) | 123/209 (59%; 52-65) | 86 | 0 | 5.278 | -3.229 | -0.843 |
| bounce_vs_forged_dispense | indist | 39 | 39/39 (100%; 91-100) | 0/39 (0%; 0-9) | 0/39 (0%; 0-9) | 0/39 (0%; 0-9) | 39 | 0 | 0.683 | 0.683 | -1.922 |
| ALL | dist | 613 | 317/613 (52%; 48-56) | 243/613 (40%; 36-44) | 203/613 (33%; 30-37) | 257/613 (42%; 38-46) | 356 | 0 | | | |
| ALL | indist | 210 | 92/210 (44%; 37-51) | 0/210 (0%; 0-2) | 0/210 (0%; 0-2) | 0/210 (0%; 0-2) | 210 | 0 | | | |

In the indistinguishable stratum D = 0 exactly in all pairs, as for classes; the lean (Lambda of an identical stream) is now between the two actual subtypes and is much smaller than the class-level lean, because the mixture over the loud sub-causes of the class is gone.

#### 9.1.2 Distribution of Lambda (nats), subtype level, V0: min / q25 / median / q75 / max
| group | stratum | member | min | q25 | median | q75 | max |
|---|---|---|---|---|---|---|---|
| double_take_vs_bounce | dist | A | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| double_take_vs_bounce | dist | B | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| double_take_vs_bounce | dist | D | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| double_take_vs_bounce | indist | A | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| double_take_vs_bounce | indist | B | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| double_take_vs_bounce | indist | D | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| nonresponse_vs_falsified_dispense | dist | A | 0.683 | 4.300 | 5.278 | 5.961 | 5.961 |
| nonresponse_vs_falsified_dispense | dist | B | -3.912 | -3.912 | -3.912 | 0.683 | 5.278 |
| nonresponse_vs_falsified_dispense | dist | D | 0.000 | 0.683 | 9.190 | 9.190 | 9.873 |
| nonresponse_vs_falsified_dispense | indist | A | 0.683 | 0.683 | 0.683 | 1.366 | 1.366 |
| nonresponse_vs_falsified_dispense | indist | B | 0.683 | 0.683 | 0.683 | 1.366 | 1.366 |
| nonresponse_vs_falsified_dispense | indist | D | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| refusal_vs_robot_missed | dist | A | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| refusal_vs_robot_missed | dist | B | -4.595 | -4.595 | -4.595 | -4.595 | -4.595 |
| refusal_vs_robot_missed | dist | D | 4.595 | 4.595 | 4.595 | 4.595 | 4.595 |
| refusal_vs_robot_missed | indist | A | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| refusal_vs_robot_missed | indist | B | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| refusal_vs_robot_missed | indist | D | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| bounce_vs_forged_dispense | dist | A | 0.683 | 1.366 | 5.278 | 5.961 | 5.961 |
| bounce_vs_forged_dispense | dist | B | -7.824 | -3.912 | -3.229 | 0.683 | 5.961 |
| bounce_vs_forged_dispense | dist | D | 0.000 | 0.000 | 4.595 | 9.190 | 13.785 |
| bounce_vs_forged_dispense | indist | A | 0.683 | 0.683 | 0.683 | 0.683 | 1.366 |
| bounce_vs_forged_dispense | indist | B | 0.683 | 0.683 | 0.683 | 0.683 | 1.366 |
| bounce_vs_forged_dispense | indist | D | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |

#### 9.1.3 Distinguishable pairs by separating channel set: D > 0 rate, subtype level (V0)
| group | separated_by | pairs | D > 0 | D = 0 | D < 0 | mean D |
|---|---|---|---|---|---|---|
| bounce_vs_forg | content_change | 39 | 0 | 39 | 0 | 0.000 |
| bounce_vs_forg | content_change,dispense_seq | 20 | 16 | 4 | 0 | 3.676 |
| bounce_vs_forg | content_change,dispense_seq,verification | 28 | 25 | 3 | 0 | 12.308 |
| bounce_vs_forg | content_change,verification | 36 | 18 | 18 | 0 | 4.595 |
| bounce_vs_forg | dispense_seq | 22 | 21 | 1 | 0 | 4.386 |
| bounce_vs_forg | dispense_seq,verification | 26 | 22 | 4 | 0 | 11.665 |
| bounce_vs_forg | verification | 38 | 21 | 17 | 0 | 5.079 |
| double_take_vs | content_change | 39 | 0 | 39 | 0 | 0.000 |
| double_take_vs | content_change,dispense_interval | 37 | 0 | 37 | 0 | 0.000 |
| double_take_vs | content_change,dispense_interval,witness | 37 | 0 | 37 | 0 | 0.000 |
| double_take_vs | content_change,witness | 35 | 0 | 35 | 0 | 0.000 |
| double_take_vs | dispense_interval | 34 | 0 | 34 | 0 | 0.000 |
| double_take_vs | dispense_interval,witness | 36 | 0 | 36 | 0 | 0.000 |
| double_take_vs | witness | 38 | 0 | 38 | 0 | 0.000 |
| nonresponse_vs | dispense_seq | 13 | 0 | 13 | 0 | 0.000 |
| nonresponse_vs | dispense_seq,verification | 14 | 14 | 0 | 0 | 9.190 |
| nonresponse_vs | dispense_seq,verification,witness | 15 | 15 | 0 | 0 | 9.873 |
| nonresponse_vs | dispense_seq,witness | 14 | 14 | 0 | 0 | 0.683 |
| nonresponse_vs | verification | 48 | 47 | 1 | 0 | 8.999 |
| nonresponse_vs | verification,witness | 4 | 4 | 0 | 0 | 9.873 |
| refusal_vs_rob | robot_task_outcome | 40 | 40 | 0 | 0 | 4.595 |

#### 9.1.4 McNemar between method variants, subtype level, on 'D > 0' (distinguishable pairs matched in both); exact binomial on the discordant pairs
| group | variant X | variant Y | pairs | b (X right, Y not) | c (Y right, X not) | exact p |
|---|---|---|---|---|---|---|
| double_take_vs | V0 full (diag ON) | V1 full, no diagnostics | 256 | 0 | 0 | 1 |
| nonresponse_vs | V0 full (diag ON) | V1 full, no diagnostics | 108 | 0 | 0 | 1 |
| refusal_vs_rob | V0 full (diag ON) | V1 full, no diagnostics | 40 | 0 | 0 | 1 |
| bounce_vs_forg | V0 full (diag ON) | V1 full, no diagnostics | 209 | 0 | 0 | 1 |
| ALL | V0 full (diag ON) | V1 full, no diagnostics | 613 | 0 | 0 | 1 |
| double_take_vs | V0 full (diag ON) | V2 no witness | 256 | 0 | 0 | 1 |
| nonresponse_vs | V0 full (diag ON) | V2 no witness | 108 | 14 | 0 | 0.000122 |
| refusal_vs_rob | V0 full (diag ON) | V2 no witness | 40 | 0 | 0 | 1 |
| bounce_vs_forg | V0 full (diag ON) | V2 no witness | 209 | 0 | 0 | 1 |
| ALL | V0 full (diag ON) | V2 no witness | 613 | 14 | 0 | 0.000122 |
| double_take_vs | V0 full (diag ON) | V3 no verification | 256 | 0 | 0 | 1 |
| nonresponse_vs | V0 full (diag ON) | V3 no verification | 108 | 61 | 0 | 8.67e-19 |
| refusal_vs_rob | V0 full (diag ON) | V3 no verification | 40 | 0 | 0 | 1 |
| bounce_vs_forg | V0 full (diag ON) | V3 no verification | 209 | 39 | 0 | 3.64e-12 |
| ALL | V0 full (diag ON) | V3 no verification | 613 | 100 | 0 | 1.58e-30 |
| double_take_vs | V0 full (diag ON) | V4 no witness, no verif. | 256 | 0 | 0 | 1 |
| nonresponse_vs | V0 full (diag ON) | V4 no witness, no verif. | 108 | 94 | 0 | 1.01e-28 |
| refusal_vs_rob | V0 full (diag ON) | V4 no witness, no verif. | 40 | 0 | 0 | 1 |
| bounce_vs_forg | V0 full (diag ON) | V4 no witness, no verif. | 209 | 39 | 0 | 3.64e-12 |
| ALL | V0 full (diag ON) | V4 no witness, no verif. | 613 | 133 | 0 | 1.84e-40 |
| double_take_vs | V0 full (diag ON) | V5 + dispenser channels (ADR-032 proto) | 256 | 0 | 217 | 9.5e-66 |
| nonresponse_vs | V0 full (diag ON) | V5 + dispenser channels (ADR-032 proto) | 108 | 0 | 0 | 1 |
| refusal_vs_rob | V0 full (diag ON) | V5 + dispenser channels (ADR-032 proto) | 40 | 0 | 0 | 1 |
| bounce_vs_forg | V0 full (diag ON) | V5 + dispenser channels (ADR-032 proto) | 209 | 0 | 64 | 1.08e-19 |
| ALL | V0 full (diag ON) | V5 + dispenser channels (ADR-032 proto) | 613 | 0 | 281 | 5.15e-85 |

#### 9.1.5 Summary of the variants at subtype level (distinguishable stratum, all groups) next to the class level of section 4.6
| variant | dist pairs | D > 0 (subtype) | both correct (subtype) | D > 0 by group g1/g2/g3/g4 (subtype) | D > 0 (class level, 4.6) | indist D = 0 |
|---|---|---|---|---|---|---|
| V0 full (diag ON) | 613 | 257/613 (42%; 38-46) | 203/613 (33%; 30-37) | 0/256 / 94/108 / 40/40 / 123/209 | 257/613 (42%) | 210/210 |
| V1 full, no diagnostics | 613 | 257/613 (42%; 38-46) | 203/613 (33%; 30-37) | 0/256 / 94/108 / 40/40 / 123/209 | 257/613 (42%) | 210/210 |
| V2 no witness | 613 | 243/613 (40%; 36-44) | 203/613 (33%; 30-37) | 0/256 / 80/108 / 40/40 / 123/209 | 243/613 (40%) | 210/210 |
| V3 no verification | 613 | 157/613 (26%; 22-29) | 84/613 (14%; 11-17) | 0/256 / 33/108 / 40/40 / 84/209 | 157/613 (26%) | 210/210 |
| V4 no witness, no verif. | 613 | 124/613 (20%; 17-24) | 84/613 (14%; 11-17) | 0/256 / 0/108 / 40/40 / 84/209 | 124/613 (20%) | 210/210 |
| V5 + dispenser channels (ADR-032 proto) | 613 | 538/613 (88%; 85-90) | 362/613 (59%; 55-63) | 217/256 / 94/108 / 40/40 / 187/209 | 538/613 (88%) | 210/210 |

#### 9.1.6 Sensitivity to the within-class prior pi(subtype | class) (config/subtype_priors.yaml): Lambda and D at subtype level, V0 and V5
Only the level split inside dispense_forgery enters Lambda (naive against informed: the other subtypes have one component), so the design moves the pairs of groups 2 and 4 only.
| design | status | variant | D > 0 g1/g2/g3/g4 | median Lambda_A, indist g1/g2/g3/g4 | both correct (all dist) |
|---|---|---|---|---|---|
| uniform | reference | V0 | 0.00 / 0.87 / 1.00 / 0.59 | 0.00 / 0.68 / 0.00 / 0.68 | 203/613 |
| uniform | reference | V5 | 0.85 / 0.87 / 1.00 / 0.89 | 0.68 / 0.68 / 0.00 / 4.60 | 362/613 |
| quiet_rare | illustrative | V0 | 0.00 / 0.87 / 1.00 / 0.59 | 0.00 / 1.57 / 0.00 / 1.57 | 203/613 |
| quiet_rare | illustrative | V5 | 0.85 / 0.87 / 1.00 / 0.89 | 0.68 / 1.57 / 0.00 / 5.48 | 360/613 |
| quiet_common | illustrative | V0 | 0.00 / 0.87 / 1.00 / 0.59 | 0.00 / 0.22 / 0.00 / 0.22 | 203/613 |
| quiet_common | illustrative | V5 | 0.85 / 0.87 / 1.00 / 0.89 | 0.68 / 0.22 / 0.00 / 4.13 | 381/613 |

Sensitivity to eps and qc (design uniform, V0): D > 0 and median Lambda_A of the indistinguishable stratum
| eps | qc | D > 0 g1/g2/g3/g4 | median Lambda_A indist g1/g2/g3/g4 |
|---|---|---|---|
| 0.001 | 0.25 | 0.00 / 0.87 / 1.00 / 0.59 | 0.00 / 0.69 / 0.00 / 0.69 |
| 0.001 | 0.5 | 0.00 / 0.87 / 1.00 / 0.59 | 0.00 / 0.69 / 0.00 / 0.69 |
| 0.001 | 0.75 | 0.00 / 0.87 / 1.00 / 0.59 | 0.00 / 0.69 / 0.00 / 0.69 |
| 0.01 | 0.25 | 0.00 / 0.87 / 1.00 / 0.59 | 0.00 / 0.68 / 0.00 / 0.68 |
| 0.01 | 0.5 | 0.00 / 0.87 / 1.00 / 0.59 | 0.00 / 0.68 / 0.00 / 0.68 |
| 0.01 | 0.75 | 0.00 / 0.87 / 1.00 / 0.59 | 0.00 / 0.68 / 0.00 / 0.68 |
| 0.05 | 0.25 | 0.00 / 0.87 / 1.00 / 0.59 | 0.00 / 0.64 / 0.00 / 0.64 |
| 0.05 | 0.5 | 0.00 / 0.87 / 1.00 / 0.59 | 0.00 / 0.64 / 0.00 / 0.64 |
| 0.05 | 0.75 | 0.00 / 0.87 / 1.00 / 0.59 | 0.00 / 0.64 / 0.00 / 0.64 |
| 0.1 | 0.25 | 0.00 / 0.87 / 1.00 / 0.59 | 0.00 / 0.59 / 0.00 / 0.59 |
| 0.1 | 0.5 | 0.00 / 0.87 / 1.00 / 0.59 | 0.00 / 0.59 / 0.00 / 0.59 |
| 0.1 | 0.75 | 0.00 / 0.87 / 1.00 / 0.59 | 0.00 / 0.59 / 0.00 / 0.59 |


Reading of 9.1.
* **The directions are those of the class level** (D > 0 in 257 of 613 distinguishable pairs, the same McNemar counts: no diagnostics 0 discordant, no witness b = 14, no verification b = 100, neither b = 133, with the ADR-032 channels c = 281), because D compares the same fields and the only field-level mixture that disappears is the one over the loud sub-causes of the class.
* **The lean collapses.** At class level a quiet pair carried a lean of +2.32 (group 1) and -1.92 (group 4) from the mixture over the loud C2 sub-causes; between the two actual subtypes the median Lambda of an identical stream is 0.00 (group 1: double take against bounce, 294 of 294 pairs have Lambda = 0 for both members: **the table gives likelihood ratio exactly 1**), 0.68 (groups 2 and 4: ln 2, the naive level of the forgery excluded by a denied sequence field) and 0.00 (group 3). The remaining lean is the level split inside dispense_forgery, and it moves with the design (1.57 / 0.68 / 0.22 for quiet_rare / uniform / quiet_common).
* **Both-correct-direction rises** from 169 to 203 of 613 (V0) and from 316 to 362 (V5), for the same reason.
* **The class posterior as the sum of the subtypes** (9.4.2): argmax = truth 859 of 1879 under all designs; kappa at tau 0.8: 1634 UNDETERMINED / 245 right / 0 wrong (uniform), 1455 / 245 / **179 wrong** (quiet_rare: all confident C1 for quiet members), 1671 / 208 / 0 (quiet_common). On the main population the class posterior has log score / Brier 0.884 / 0.532 (uniform), 0.837 / 0.512 (quiet_rare), 0.938 / 0.564 (quiet_common), against 0.901 / 0.536 for the independent class table.

### 9.2 Diagnostics and the log score

**Short answer.** With diagnostics the main-population log score is 0.9010 against 0.8940 without (0.0070 nats per alert, 105.6 nats over 15 084 alerts): worse. The two profiles differ in one field only, `system.diagnostics_ok` (checked on all 17 015 alerts), so the whole change is that field's. The worsening is real under the labelling of section 5, but it is produced by the labelling and by one cell, not by the diagnostics: it reverses under a labelling that respects the dropout's target (-0.0174) and under a tight time window (-0.0312). The driver switch does not make idle cuffs stale.


alerts scored 15084; mean log score with diagnostics 0.9010, without 0.8940; difference (with minus without) +0.0070 nats per alert, total +105.6 nats

#### 9.2.1 Change of the log score caused by the diagnostics field, by template, true cause and reading class (sum of the per-alert differences; positive = worse with diagnostics)
| template | truth | DIAG class | alerts | sum of change (nats) | mean change |
|---|---|---|---|---|---|
| count | C1 | D | 975 | -79.13 | -0.0812 |
| count | C2 | D | 325 | +249.83 | +0.7687 |
| count | C3 | D | 190 | -23.09 | -0.1215 |
| hold | C1 | D | 283 | -6.95 | -0.0245 |
| hold | C2 | A | 24 | -16.26 | -0.6774 |
| hold | C2 | D | 174 | +12.76 | +0.0734 |
| hold | C2 | U | 58 | +0.00 | +0.0000 |
| hold | C3 | D | 100 | -2.48 | -0.0248 |
| range | C1 | D | 7420 | +0.00 | +0.0000 |
| range | C1 | U | 86 | +0.00 | +0.0000 |
| range | C2 | D | 280 | +0.00 | +0.0000 |
| range | C3 | D | 451 | +0.00 | +0.0000 |
| range | C3 | U | 6 | +0.00 | +0.0000 |
| resp | C1 | D | 2419 | -62.11 | -0.0257 |
| resp | C2 | A | 34 | -8.51 | -0.2504 |
| resp | C2 | D | 1214 | +123.47 | +0.1017 |
| resp | C2 | U | 94 | +0.00 | +0.0000 |
| resp | C3 | D | 252 | -7.87 | -0.0312 |
| sched | C1 | D | 159 | -4.42 | -0.0278 |
| sched | C2 | A | 77 | -81.01 | -1.0521 |
| sched | C2 | D | 212 | +12.67 | +0.0598 |
| sched | C2 | U | 187 | +0.00 | +0.0000 |
| sched | C3 | D | 64 | -1.35 | -0.0210 |

By template: count +147.6, hold -12.9, range +0.0, resp +45.0, sched -74.1
By true cause: C1 -152.6, C2 +293.0, C3 -34.8
By reading class: A -105.8, D +211.3, U +0.0

#### 9.2.2 The cell P(DIAG = A | cause) against the empirical rate of A among the alerts of that cause (diagnostic only, not used to fit)
| template | cause | model P(A) | empirical A | empirical A or D | alerts |
|---|---|---|---|---|---|
| count | C1 | 0.010 | 0.000 (0/975) | 975 | 975 |
| count | C2 | 0.582 | 0.000 (0/325) | 325 | 325 |
| count | C3 | 0.010 | 0.000 (0/190) | 190 | 190 |
| hold | C1 | 0.010 | 0.000 (0/283) | 283 | 283 |
| hold | C2 | 0.123 | 0.121 (24/198) | 198 | 256 |
| hold | C3 | 0.010 | 0.000 (0/100) | 100 | 100 |
| range | C1 | 0.010 | 0.000 (0/7420) | 7420 | 7506 |
| range | C2 | 0.010 | 0.000 (0/280) | 280 | 280 |
| range | C3 | 0.010 | 0.000 (0/451) | 451 | 457 |
| resp | C1 | 0.010 | 0.000 (0/2419) | 2419 | 2419 |
| resp | C2 | 0.132 | 0.027 (34/1248) | 1248 | 1342 |
| resp | C3 | 0.010 | 0.000 (0/252) | 252 | 252 |
| sched | C1 | 0.010 | 0.000 (0/159) | 159 | 159 |
| sched | C2 | 0.157 | 0.266 (77/289) | 289 | 476 |
| sched | C3 | 0.010 | 0.000 (0/64) | 64 | 64 |

#### 9.2.3 Alerts matched to a ble_dropout: reading class of DIAG by dropout target
| target | template | DIAG | alerts |
|---|---|---|---|
| cuff | count | D | 14 |
| cuff | hold | A | 19 |
| cuff | hold | D | 1 |
| cuff | resp | A | 25 |
| cuff | resp | D | 22 |
| cuff | sched | A | 60 |
| cuff | sched | D | 2 |
| dispenser | count | D | 18 |
| dispenser | resp | D | 4 |
| ecg | count | D | 135 |
| ecg | hold | A | 2 |
| ecg | hold | D | 44 |
| ecg | hold | U | 1 |
| ecg | resp | A | 1 |
| ecg | resp | D | 433 |
| ecg | resp | U | 2 |
| ecg | sched | A | 4 |
| ecg | sched | D | 19 |
| ecg | sched | U | 8 |
| oximeter | count | D | 135 |
| oximeter | hold | A | 1 |
| oximeter | hold | D | 52 |
| oximeter | hold | U | 1 |
| oximeter | resp | A | 5 |
| oximeter | resp | D | 449 |
| oximeter | resp | U | 5 |
| oximeter | sched | A | 9 |
| oximeter | sched | D | 23 |
| oximeter | sched | U | 9 |


**Why, exactly.**
1. *Which alerts get worse:* only the alerts whose true cause is C2 and whose diagnostics field is **denied** (D): `count` +249.8 nats (325 alerts, +0.77 each), `resp` +123.5 (1 214), `hold` +12.8, `sched` +12.7. A denied `diagnostics_ok` lowers the posterior of C2 by the cell (1 - P(A | C2)): 0.42 at `count`, 0.87 at `resp`, 0.84 at `sched`. The alerts with C1 (-152.6 nats) and C3 (-34.8) improve, and the C2 alerts with the field asserted improve most (`sched` -1.05 each, -81 in all); `range` is unchanged (no C2 sub-cause that can violate `range` raises the field).
2. *The cell does not fit the benchmark at `count`:* the uniform mixture over the five C2 sub-causes that can violate `count` (bounce, ble_dropout, message_drop, process_kill, uncommanded transition) gives P(stale | C2) = 0.582, while the benchmark injects only the bounce and the dropout, and **0 of the 325 `count` alerts labelled C2 has the field asserted** (9.2.2).
3. *Most of those alerts are not caused by a fault of their scope:* 9.2.3 splits the alerts labelled `ble_dropout` by the dropout's target. At `count` 284 of the 302 alerts labelled `ble_dropout` sit on a dropout of the cuff, the ECG device or the oximeter (270 of them ECG or oximeter), none of which is in the data scope of COUNT (dispenser only; the 18 on the dispenser also read D, presumably alerts decided after the recovery, not checked), and at `resp` 895 of 946 sit on an ECG or oximeter dropout, outside the scope (cuff and dispenser); the label comes from `TEMPLATES_AFFECTED`, which lists `count`, `resp`, `hold` and `sched` for any `ble_dropout` whatever its target, plus a 24-hour window after the event. The driver reports `ok` for the cuff and the dispenser, which is right; the truth label says C2, which is not. With the dropout restricted to targets in the template's scope the sign reverses (9.2.4).
4. *Per field contribution:* there is only one field. Its contribution per class: asserted -105.8 nats (better), denied +211.3 (worse), unavailable 0; by cause C1 -152.6, C2 +293.0, C3 -34.8 (labelling of section 5).


Fields whose value differs between the profile with and without diagnostics, over the 17015 VIOLATED alerts of m120: {'system.diagnostics_ok': 16535}. The log-score change is therefore the contribution of `system.diagnostics_ok` alone.

#### 9.2.4 Main-population log score with and without driver diagnostics, by labelling of the truth (lower is better; the labelling is the only thing that changes between rows)
| labelling | alerts scored | with diagnostics | without | change | change summed by true cause (nats): C1 / C2 / C3 |
|---|---|---|---|---|---|
| labelling of section 5 (injected first, window 24 h, any dropout target) | 15084 | 0.9010 | 0.8940 | +0.0070 | -152.6 / +293.0 / -34.8 |
| window 1 h, any dropout target | 14174 | 0.7776 | 0.7960 | -0.0184 | -206.8 / -34.0 / -20.7 |
| window 0 (alert decided while the event window is open), any target | 6751 | 0.6673 | 0.6985 | -0.0312 | -176.2 / -18.4 / -16.0 |
| dropout target in the template's data scope, window 24 h | 15393 | 0.8002 | 0.8176 | -0.0174 | -208.4 / -13.8 / -46.0 |
| dropout target in scope, window 1 h | 14188 | 0.7642 | 0.7854 | -0.0211 | -212.3 / -66.6 / -21.1 |
| dropout target in scope, window 0 | 6755 | 0.6606 | 0.6930 | -0.0324 | -177.4 / -25.5 / -16.2 |

#### 9.2.5 Counterfactual: a driver that reports an IDLE cuff as stale (an aggregator with a timeout; a BLE cuff that connects only when it measures is silent between measurements). Same table, cells unchanged (P(stale | C1) = eps), dropout-scope labelling, window 24 h
| driver | timeout of the idle cuff | alerts | C1 alerts with DIAG asserted | log score with | log score without | change |
|---|---|---|---|---|---|---|
| the switch of this run (stale only in link_down windows) | - | 15393 | 0/12606 (0.0%) | 0.8002 | 0.8176 | -0.0174 |
| naive: stale when no cuff message for T_idle | 1 h | 15393 | 11170/12606 (88.6%) | 1.1137 | 0.8176 | +0.2961 |
| naive: stale when no cuff message for T_idle | 6 h | 15393 | 10897/12606 (86.4%) | 1.1124 | 0.8176 | +0.2948 |


**STALE for the cuff: what the documents say, and what the switch does.**
* `evidence-channels.md` (field table, derivation table, D-8): `system.diagnostics_ok` is False "if a node of the scope reported level error or stale in the window", True if every capable node reported ok, else `None`. The payload is `NODE_STATE.diagnostics` in {ok, warn, error, stale}. **No document defines when a node is STALE: no period, no timeout, no lease for the diagnostics.** The lease (`liveliness_lease_ms`) and the data-stream deadline (`qos_deadline_ms`, "null for an event-driven device") are run parameters of the device profile without a value (D-8, EC-OP-18: the generator has no lease parameter), and they feed `liveliness_ok` and `qos_deadline_missed`, not `diagnostics_ok`. Nothing in `evidence-channels.md` or `fault-model.md` says that a BLE cuff connects only when it measures; the closest statement is that an event-driven device may declare no deadline.
* **What the switch does** (`driver_diag.py`): `ok` at t = 0 and every hour (period 1 h; 10 minutes gives the identical vectors), for the cuff whether or not it measures; `stale` only in the `link_down` ... `active` windows that the gateway wrote for a `ble_dropout`, at the start and every hour inside it; there is no lease (stale is immediate). **An idle cuff is not reported stale**: 0 of the 12 606 C1 alerts and 0 of the 1 268 C3 alerts (scope-aware labelling) have the field asserted, 135 C2 alerts have it, all in dropout windows (9.2.3). The cell P(stale | C1) = eps is therefore consistent with the generator. It is a REQUIREMENT on the real driver (9.2.5): ROS 2 diagnostics aggregators mark an item STALE when it has not been updated within a timeout, so a naive bridge for a device that is silent between measurements would report STALE continuously (general ROS 2 behaviour, not checked in this repository); in the counterfactual 88.6% of the C1 alerts have the field asserted and the log score worsens by +0.296 nats. That is a statement about this prototype's generator, not a measurement of a real driver.
* **No generator defect, so no fix and no rerun was needed.** The requested rerun "both ways" is 9.2.4 (with and without diagnostics, six labellings) plus 9.2.5 (the idle-stale counterfactual).
* The choice of the scope-aware labelling was made after seeing the sign of the change; all rows are printed.

### 9.3 The channel 'identical repeated value' (for stuck_at)

**Definition.** `cuff.identical_repeat` (outside the contract, prototype): A if the last two cuff `bp` readings received by the decision time of the alert (the previous day's readings included) are exactly equal, D if they differ, `None` if fewer than two exist. It is read by the templates that read the cuff (range, sched, hold, resp, sys). Cells: P(A | stuck_at) = 1 - eps (every reading of the window repeats the last value before the onset); P(A | any other sub-cause) = max(rep_nat, eps), rep_nat a SENSITIVITY value derived below. A denied reading lowers stuck_at by (eps against 1 - rep_nat).

#### 9.3.1 Natural probability of an identical repeat


Fault-free run `ff` (injection rates 0, 120 patients x 30 days, seed 0): 17917 cuff readings, 17797 consecutive pairs, **exactly equal: 0** (observed frequency 0.0000).
Share of readings that are integers: 0.0000; smallest non-zero |difference| between consecutive readings: 0.00137 mmHg; readings at the clip bounds: min 82.44, max 206.15, share equal to the min or max: 0.0001.
SD of the difference of consecutive readings: 20.09 mmHg (median |difference| 13.67).
Generator measurement process: bp = latent SBP + cuff_bias + cuff_error_sd * z, a float with no rounding in `measurement.py` (no resolution parameter exists); `cuff_error_sd_mmhg` in the prior file = 8.0 (('Stergiou GS et al., AAMI/ESH/ISO collaboration statement, Hypertension 2018;71:368-374 (ISO 81060-2 criterion 1: SD of differences at most 8 mmHg; edition and clause to be confirmed) (detail: docs/formal/parameter-literature-proposal.md)', 'filled')).
Analytic: two floats drawn from continuous noise are equal with probability 0, so **rep_nat = 0 exactly in this generator** and the fault-free frequency 0/17797 agrees.

For a device with a display resolution r mmHg (a SENSITIVITY value: the cuff specification is not in the repository) the natural probability that two consecutive readings are equal is E[max(0, 1 - |Delta| / r)] over the difference Delta of consecutive pre-rounding readings (valid when the first reading falls uniformly in its quantisation cell). With the empirical Delta of the fault-free run and, as a cross-check, a Gaussian Delta with the same SD:
| r (mmHg) | rep_nat, empirical Delta | rep_nat, Gaussian Delta (SD 20.1) |
|---|---|---|
| 0.1 | 0.0021 | 0.0020 |
| 1.0 | 0.0200 | 0.0198 |
| 2.0 | 0.0388 | 0.0395 |
| 5.0 | 0.0980 | 0.0983 |


The generator has **no resolution**: the cuff value is a float (`latent + bias + sd * z`, `measurement.py`; no rounding, no resolution parameter), so the analytic natural probability is 0 and the fault-free run agrees (0 of 17 797 consecutive pairs). That makes the channel a perfect detector of stuck_at in this benchmark, which is an artefact. For a real cuff the resolution r is a device-specification value that is not in the repository; the table above gives rep_nat for r = 1, 2, 5 mmHg (grid values) from the fault-free differences, and the channel is evaluated by rounding the benchmark's readings to r before comparing (the frozen window stays identical, natural equality arises at about rep_nat: observed 0.0299 / 0.0483 / 0.1297 against the formula's 0.0200 / 0.0388 / 0.0980 for r = 1 / 2 / 5; the alerts are not a random sample of consecutive pairs: for example 12 of the 20 float-equal cases are alerts raised inside an active stuck_at window that carry another cause's label, the others replays and cuff_detached; see 9.3.3).


#### 9.3.2 Effective k of stuck_at (readings of the stream inside the frozen window), from the injection log of m120 (realised stuck_at records)
| readings in the window | records |
|---|---|
| 1 | 30 |
| 2 | 29 |
| 3 | 8 |
Window durations of the records (h): [1.0, 4.0, 12.0] (placeholders 1/4/12 h). Every reading in the window repeats the last value before the onset, so with k readings in the window the first repeats the earlier reading and the others repeat each other: all k readings are identical to their predecessor, P(A | stuck_at, alert at a reading of the window) = 1 up to the leak eps.

Labelling: labelling of section 5 (injected first, window 24 h, any dropout target); 15084 alerts.



#### 9.3.3 (tight labelling) Reading class of the channel at the matched alerts (cuff-reading templates range, sched, hold, resp), by true subtype and display resolution r of the cuff (None = the generator's floats)
| true subtype | alerts | r | A (identical) | D (differ) | U (fewer than two readings) |
|---|---|---|---|---|---|
| ble_dropout | 47 | 1.0 | 2 (4.3%) | 44 | 1 |
| ble_dropout | 47 | 2.0 | 3 (6.4%) | 43 | 1 |
| ble_dropout | 47 | 5.0 | 5 (10.6%) | 41 | 1 |
| ble_dropout | 47 | None | 0 (0.0%) | 46 | 1 |
| cuff_silent_bias | 156 | 1.0 | 5 (3.2%) | 148 | 3 |
| cuff_silent_bias | 156 | 2.0 | 6 (3.8%) | 147 | 3 |
| cuff_silent_bias | 156 | 5.0 | 20 (12.8%) | 133 | 3 |
| cuff_silent_bias | 156 | None | 0 (0.0%) | 153 | 3 |
| dispense_forgery | 60 | 1.0 | 0 (0.0%) | 60 | 0 |
| dispense_forgery | 60 | 2.0 | 2 (3.3%) | 58 | 0 |
| dispense_forgery | 60 | 5.0 | 8 (13.3%) | 52 | 0 |
| dispense_forgery | 60 | None | 0 (0.0%) | 60 | 0 |
| injection_naive | 157 | 1.0 | 0 (0.0%) | 156 | 1 |
| injection_naive | 157 | 2.0 | 1 (0.6%) | 155 | 1 |
| injection_naive | 157 | 5.0 | 3 (1.9%) | 153 | 1 |
| injection_naive | 157 | None | 0 (0.0%) | 156 | 1 |
| nav_delay | 2 | 1.0 | 0 (0.0%) | 2 | 0 |
| nav_delay | 2 | 2.0 | 0 (0.0%) | 2 | 0 |
| nav_delay | 2 | 5.0 | 0 (0.0%) | 2 | 0 |
| nav_delay | 2 | None | 0 (0.0%) | 2 | 0 |
| replay | 201 | 1.0 | 5 (2.5%) | 196 | 0 |
| replay | 201 | 2.0 | 9 (4.5%) | 192 | 0 |
| replay | 201 | 5.0 | 18 (9.0%) | 183 | 0 |
| replay | 201 | None | 3 (1.5%) | 198 | 0 |
| stuck_at | 96 | 1.0 | 90 (93.8%) | 6 | 0 |
| stuck_at | 96 | 2.0 | 90 (93.8%) | 6 | 0 |
| stuck_at | 96 | 5.0 | 90 (93.8%) | 6 | 0 |
| stuck_at | 96 | None | 90 (93.8%) | 6 | 0 |

Natural rate of A among the cuff-template alerts whose true subtype is not stuck_at (values rounded to r mmHg before comparing), against the fault-free formula of 9.3.1 (rep_nat):
- r = None: 20/5110 = 0.0039 (rep_nat 0.0)
- r = 1.0: 153/5110 = 0.0299 (rep_nat 0.02)
- r = 2.0: 247/5110 = 0.0483 (rep_nat 0.0388)
- r = 5.0: 663/5110 = 0.1297 (rep_nat 0.098)



**Effect on the set, tight labelling.**

#### 9.3.4 (tight labelling) Effect of the channel on the subtype set (design uniform, reference cells; rep_nat = the value of 9.3.1 for the resolution r)
Silent-fault alerts of the main population (433: stuck_at 137, cuff_silent_bias 256, dispenser_bounce 40; dispenser_bounce is at COUNT, which does not read the cuff, so it cannot change). 'Contains C1': the set holds at least one C1 subtype (the masquerade). 'Exact': the set is exactly the true subtype.
| level | r | true subtype | alerts | coverage without -> with | mean size without -> with | contains C1 without -> with | exact without -> with | sets that lose all C1 subtypes |
|---|---|---|---|---|---|---|---|---|
| 0.8 | None | stuck_at | 96 | 92 -> 90 | 5.07 -> 1.33 | 95 -> 6 | 0 -> 89 | 89 |
| 0.8 | None | cuff_silent_bias | 156 | 151 -> 151 | 4.60 -> 4.37 | 151 -> 151 | 0 -> 0 | 0 |
| 0.8 | None | dispenser_bounce | 3 | 0 -> 0 | 5.00 -> 5.00 | 3 -> 3 | 0 -> 0 | 0 |
| 0.8 | 1.0 | stuck_at | 96 | 92 -> 89 | 5.07 -> 1.93 | 95 -> 35 | 0 -> 60 | 60 |
| 0.8 | 1.0 | cuff_silent_bias | 156 | 151 -> 146 | 4.60 -> 4.27 | 151 -> 148 | 0 -> 0 | 3 |
| 0.8 | 1.0 | dispenser_bounce | 3 | 0 -> 0 | 5.00 -> 5.00 | 3 -> 3 | 0 -> 0 | 0 |
| 0.8 | 2.0 | stuck_at | 96 | 92 -> 89 | 5.07 -> 1.95 | 95 -> 35 | 0 -> 60 | 60 |
| 0.8 | 2.0 | cuff_silent_bias | 156 | 151 -> 145 | 4.60 -> 4.25 | 151 -> 148 | 0 -> 0 | 3 |
| 0.8 | 2.0 | dispenser_bounce | 3 | 0 -> 0 | 5.00 -> 5.00 | 3 -> 3 | 0 -> 0 | 0 |
| 0.8 | 5.0 | stuck_at | 96 | 92 -> 89 | 5.07 -> 3.80 | 95 -> 95 | 0 -> 0 | 0 |
| 0.8 | 5.0 | cuff_silent_bias | 156 | 151 -> 150 | 4.60 -> 4.24 | 151 -> 151 | 0 -> 0 | 0 |
| 0.8 | 5.0 | dispenser_bounce | 3 | 0 -> 0 | 5.00 -> 5.00 | 3 -> 3 | 0 -> 0 | 0 |
| 0.9 | None | stuck_at | 96 | 94 -> 90 | 6.77 -> 2.09 | 95 -> 35 | 0 -> 60 | 60 |
| 0.9 | None | cuff_silent_bias | 156 | 152 -> 152 | 6.04 -> 5.10 | 154 -> 153 | 0 -> 0 | 1 |
| 0.9 | None | dispenser_bounce | 3 | 0 -> 0 | 5.00 -> 5.00 | 3 -> 3 | 0 -> 0 | 0 |
| 0.9 | 1.0 | stuck_at | 96 | 94 -> 90 | 6.77 -> 2.43 | 95 -> 35 | 0 -> 60 | 60 |
| 0.9 | 1.0 | cuff_silent_bias | 156 | 152 -> 147 | 6.04 -> 4.97 | 154 -> 150 | 0 -> 0 | 4 |
| 0.9 | 1.0 | dispenser_bounce | 3 | 0 -> 0 | 5.00 -> 5.00 | 3 -> 3 | 0 -> 0 | 0 |
| 0.9 | 2.0 | stuck_at | 96 | 94 -> 90 | 6.77 -> 3.94 | 95 -> 35 | 0 -> 0 | 60 |
| 0.9 | 2.0 | cuff_silent_bias | 156 | 152 -> 152 | 6.04 -> 5.02 | 154 -> 150 | 0 -> 0 | 4 |
| 0.9 | 2.0 | dispenser_bounce | 3 | 0 -> 0 | 5.00 -> 5.00 | 3 -> 3 | 0 -> 0 | 0 |
| 0.9 | 5.0 | stuck_at | 96 | 94 -> 89 | 6.77 -> 5.51 | 95 -> 95 | 0 -> 0 | 0 |
| 0.9 | 5.0 | cuff_silent_bias | 156 | 152 -> 152 | 6.04 -> 5.04 | 154 -> 153 | 0 -> 0 | 1 |
| 0.9 | 5.0 | dispenser_bounce | 3 | 0 -> 0 | 5.00 -> 5.00 | 3 -> 3 | 0 -> 0 | 0 |
| 0.95 | None | stuck_at | 96 | 95 -> 90 | 7.78 -> 2.85 | 95 -> 35 | 0 -> 60 | 60 |
| 0.95 | None | cuff_silent_bias | 156 | 152 -> 152 | 7.09 -> 6.33 | 155 -> 155 | 0 -> 0 | 0 |
| 0.95 | None | dispenser_bounce | 3 | 3 -> 3 | 6.00 -> 6.00 | 3 -> 3 | 0 -> 0 | 0 |
| 0.95 | 1.0 | stuck_at | 96 | 95 -> 90 | 7.78 -> 4.99 | 95 -> 95 | 0 -> 0 | 0 |
| 0.95 | 1.0 | cuff_silent_bias | 156 | 152 -> 152 | 7.09 -> 6.25 | 155 -> 155 | 0 -> 0 | 0 |
| 0.95 | 1.0 | dispenser_bounce | 3 | 3 -> 3 | 6.00 -> 6.00 | 3 -> 3 | 0 -> 0 | 0 |
| 0.95 | 2.0 | stuck_at | 96 | 95 -> 90 | 7.78 -> 5.93 | 95 -> 95 | 0 -> 0 | 0 |
| 0.95 | 2.0 | cuff_silent_bias | 156 | 152 -> 152 | 7.09 -> 6.27 | 155 -> 155 | 0 -> 0 | 0 |
| 0.95 | 2.0 | dispenser_bounce | 3 | 3 -> 3 | 6.00 -> 6.00 | 3 -> 3 | 0 -> 0 | 0 |
| 0.95 | 5.0 | stuck_at | 96 | 95 -> 90 | 7.78 -> 7.14 | 95 -> 95 | 0 -> 0 | 0 |
| 0.95 | 5.0 | cuff_silent_bias | 156 | 152 -> 152 | 7.09 -> 6.33 | 155 -> 155 | 0 -> 0 | 0 |
| 0.95 | 5.0 | dispenser_bounce | 3 | 3 -> 3 | 6.00 -> 6.00 | 3 -> 3 | 0 -> 0 | 0 |

#### 9.3.5 (tight labelling) Alerts of other causes that the channel wrongly removes from their set (true subtype in the set without the channel, not with it), non-stuck_at alerts of the main population
| level | r | non-stuck_at cuff-template alerts with A | true subtype removed | by (cause, subtype) |
|---|---|---|---|---|
| 0.8 | None | 20 | 12 | {('C1', 'spontaneous_resp'): 10, ('C1', 'spontaneous_hold'): 2} |
| 0.8 | 1.0 | 148 | 1 | {('C3', 'injection_informed'): 1} |
| 0.8 | 2.0 | 241 | 2 | {('C3', 'injection_informed'): 1, ('C3', 'injection_naive'): 1} |
| 0.8 | 5.0 | 643 | 0 | - |
| 0.9 | None | 20 | 1 | {('C3', 'replay'): 1} |
| 0.9 | 1.0 | 148 | 3 | {('C3', 'injection_informed'): 2, ('C3', 'replay'): 1} |
| 0.9 | 2.0 | 241 | 4 | {('C3', 'injection_informed'): 2, ('C3', 'replay'): 2} |
| 0.9 | 5.0 | 643 | 8 | {('C3', 'injection_informed'): 6, ('C3', 'replay'): 2} |
| 0.95 | None | 20 | 2 | {('C3', 'replay'): 2} |
| 0.95 | 1.0 | 148 | 6 | {('C3', 'injection_informed'): 2, ('C3', 'replay'): 4} |
| 0.95 | 2.0 | 241 | 7 | {('C3', 'injection_informed'): 2, ('C3', 'replay'): 5} |
| 0.95 | 5.0 | 643 | 8 | {('C3', 'replay'): 8} |

#### 9.3.6 (tight labelling) All alerts of the main population: coverage and mean size without and with the channel (design uniform)
| level | r | coverage without | coverage with | mean size without | mean size with |
|---|---|---|---|---|---|
| 0.8 | None | 6264/6755 (92.7%) | 6346/6755 (93.9%) | 5.872 | 5.246 |
| 0.8 | 1.0 | 6264/6755 (92.7%) | 6347/6755 (94.0%) | 5.872 | 5.204 |
| 0.8 | 2.0 | 6264/6755 (92.7%) | 6347/6755 (94.0%) | 5.872 | 5.172 |
| 0.8 | 5.0 | 6264/6755 (92.7%) | 6350/6755 (94.0%) | 5.872 | 5.217 |
| 0.9 | None | 6449/6755 (95.5%) | 6445/6755 (95.4%) | 7.825 | 7.169 |
| 0.9 | 1.0 | 6449/6755 (95.5%) | 6438/6755 (95.3%) | 7.825 | 7.094 |
| 0.9 | 2.0 | 6449/6755 (95.5%) | 6442/6755 (95.4%) | 7.825 | 7.145 |
| 0.9 | 5.0 | 6449/6755 (95.5%) | 6437/6755 (95.3%) | 7.825 | 7.162 |
| 0.95 | None | 6524/6755 (96.6%) | 6517/6755 (96.5%) | 8.983 | 8.693 |
| 0.95 | 1.0 | 6524/6755 (96.6%) | 6513/6755 (96.4%) | 8.983 | 8.678 |
| 0.95 | 2.0 | 6524/6755 (96.6%) | 6512/6755 (96.4%) | 8.983 | 8.690 |
| 0.95 | 5.0 | 6524/6755 (96.6%) | 6511/6755 (96.4%) | 8.983 | 8.766 |



**Effect on the set, labelling of section 5.**

#### 9.3.4 (labelling of section 5) Effect of the channel on the subtype set (design uniform, reference cells; rep_nat = the value of 9.3.1 for the resolution r)
Silent-fault alerts of the main population (433: stuck_at 137, cuff_silent_bias 256, dispenser_bounce 40; dispenser_bounce is at COUNT, which does not read the cuff, so it cannot change). 'Contains C1': the set holds at least one C1 subtype (the masquerade). 'Exact': the set is exactly the true subtype.
| level | r | true subtype | alerts | coverage without -> with | mean size without -> with | contains C1 without -> with | exact without -> with | sets that lose all C1 subtypes |
|---|---|---|---|---|---|---|---|---|
| 0.8 | None | stuck_at | 137 | 134 -> 84 | 4.93 -> 2.39 | 137 -> 53 | 0 -> 84 | 84 |
| 0.8 | None | cuff_silent_bias | 256 | 248 -> 246 | 4.76 -> 4.46 | 251 -> 249 | 0 -> 0 | 2 |
| 0.8 | None | dispenser_bounce | 40 | 17 -> 13 | 5.85 -> 5.17 | 40 -> 38 | 0 -> 0 | 2 |
| 0.8 | 1.0 | stuck_at | 137 | 134 -> 85 | 4.93 -> 2.77 | 137 -> 79 | 0 -> 58 | 58 |
| 0.8 | 1.0 | cuff_silent_bias | 256 | 248 -> 242 | 4.76 -> 4.43 | 251 -> 246 | 0 -> 0 | 5 |
| 0.8 | 1.0 | dispenser_bounce | 40 | 17 -> 13 | 5.85 -> 5.28 | 40 -> 40 | 0 -> 0 | 0 |
| 0.8 | 2.0 | stuck_at | 137 | 134 -> 88 | 4.93 -> 2.71 | 137 -> 77 | 0 -> 60 | 60 |
| 0.8 | 2.0 | cuff_silent_bias | 256 | 248 -> 240 | 4.76 -> 4.40 | 251 -> 245 | 0 -> 0 | 6 |
| 0.8 | 2.0 | dispenser_bounce | 40 | 17 -> 13 | 5.85 -> 5.33 | 40 -> 40 | 0 -> 0 | 0 |
| 0.8 | 5.0 | stuck_at | 137 | 134 -> 90 | 4.93 -> 3.98 | 137 -> 137 | 0 -> 0 | 0 |
| 0.8 | 5.0 | cuff_silent_bias | 256 | 248 -> 248 | 4.76 -> 4.40 | 251 -> 251 | 0 -> 0 | 0 |
| 0.8 | 5.0 | dispenser_bounce | 40 | 17 -> 11 | 5.85 -> 5.38 | 40 -> 40 | 0 -> 0 | 0 |
| 0.9 | None | stuck_at | 137 | 136 -> 84 | 6.53 -> 3.09 | 137 -> 80 | 0 -> 57 | 57 |
| 0.9 | None | cuff_silent_bias | 256 | 251 -> 249 | 6.27 -> 5.29 | 253 -> 251 | 0 -> 0 | 2 |
| 0.9 | None | dispenser_bounce | 40 | 17 -> 15 | 7.08 -> 6.40 | 40 -> 40 | 0 -> 0 | 0 |
| 0.9 | 1.0 | stuck_at | 137 | 136 -> 85 | 6.53 -> 3.28 | 137 -> 79 | 0 -> 58 | 58 |
| 0.9 | 1.0 | cuff_silent_bias | 256 | 251 -> 245 | 6.27 -> 5.24 | 253 -> 247 | 0 -> 0 | 6 |
| 0.9 | 1.0 | dispenser_bounce | 40 | 17 -> 15 | 7.08 -> 6.50 | 40 -> 40 | 0 -> 0 | 0 |
| 0.9 | 2.0 | stuck_at | 137 | 136 -> 88 | 6.53 -> 4.24 | 137 -> 77 | 0 -> 0 | 60 |
| 0.9 | 2.0 | cuff_silent_bias | 256 | 251 -> 251 | 6.27 -> 5.26 | 253 -> 246 | 0 -> 0 | 7 |
| 0.9 | 2.0 | dispenser_bounce | 40 | 17 -> 15 | 7.08 -> 6.60 | 40 -> 40 | 0 -> 0 | 0 |
| 0.9 | 5.0 | stuck_at | 137 | 136 -> 90 | 6.53 -> 5.32 | 137 -> 137 | 0 -> 0 | 0 |
| 0.9 | 5.0 | cuff_silent_bias | 256 | 251 -> 251 | 6.27 -> 5.29 | 253 -> 252 | 0 -> 0 | 1 |
| 0.9 | 5.0 | dispenser_bounce | 40 | 17 -> 17 | 7.08 -> 6.65 | 40 -> 40 | 0 -> 0 | 0 |
| 0.95 | None | stuck_at | 137 | 137 -> 84 | 7.54 -> 3.99 | 137 -> 80 | 0 -> 57 | 57 |
| 0.95 | None | cuff_silent_bias | 256 | 251 -> 250 | 7.32 -> 6.52 | 254 -> 253 | 0 -> 0 | 1 |
| 0.95 | None | dispenser_bounce | 40 | 40 -> 38 | 8.12 -> 7.83 | 40 -> 40 | 0 -> 0 | 0 |
| 0.95 | 1.0 | stuck_at | 137 | 137 -> 85 | 7.54 -> 5.39 | 137 -> 137 | 0 -> 0 | 0 |
| 0.95 | 1.0 | cuff_silent_bias | 256 | 251 -> 251 | 7.32 -> 6.51 | 254 -> 254 | 0 -> 0 | 0 |
| 0.95 | 1.0 | dispenser_bounce | 40 | 40 -> 40 | 8.12 -> 7.92 | 40 -> 40 | 0 -> 0 | 0 |
| 0.95 | 2.0 | stuck_at | 137 | 137 -> 88 | 7.54 -> 5.98 | 137 -> 137 | 0 -> 0 | 0 |
| 0.95 | 2.0 | cuff_silent_bias | 256 | 251 -> 251 | 7.32 -> 6.52 | 254 -> 254 | 0 -> 0 | 0 |
| 0.95 | 2.0 | dispenser_bounce | 40 | 40 -> 40 | 8.12 -> 7.97 | 40 -> 40 | 0 -> 0 | 0 |
| 0.95 | 5.0 | stuck_at | 137 | 137 -> 90 | 7.54 -> 6.82 | 137 -> 137 | 0 -> 0 | 0 |
| 0.95 | 5.0 | cuff_silent_bias | 256 | 251 -> 251 | 7.32 -> 6.56 | 254 -> 254 | 0 -> 0 | 0 |
| 0.95 | 5.0 | dispenser_bounce | 40 | 40 -> 40 | 8.12 -> 8.03 | 40 -> 40 | 0 -> 0 | 0 |

#### 9.3.5 (labelling of section 5) Alerts of other causes that the channel wrongly removes from their set (true subtype in the set without the channel, not with it), non-stuck_at alerts of the main population
| level | r | non-stuck_at cuff-template alerts with A | true subtype removed | by (cause, subtype) |
|---|---|---|---|---|
| 0.8 | None | 18 | 25 | {('C2', 'manipulation_failure'): 1, ('C1', 'spontaneous_range'): 23, ('C1', 'spontaneous_hold'): 1} |
| 0.8 | 1.0 | 319 | 178 | {('C2', 'manipulation_failure'): 5, ('C1', 'spontaneous_range'): 163, ('C3', 'injection_informed'): 5, ('C3', 'dispense_forgery'): 1, ('C1', 'hypertensive_spike'): 4} |
| 0.8 | 2.0 | 559 | 303 | {('C2', 'manipulation_failure'): 10, ('C1', 'spontaneous_range'): 278, ('C1', 'hypertensive_spike'): 11, ('C3', 'injection_informed'): 3, ('C3', 'injection_naive'): 1} |
| 0.8 | 5.0 | 1468 | 697 | {('C2', 'manipulation_failure'): 17, ('C1', 'spontaneous_range'): 680} |
| 0.9 | None | 18 | 5 | {('C2', 'manipulation_failure'): 4, ('C3', 'replay'): 1} |
| 0.9 | 1.0 | 319 | 162 | {('C2', 'manipulation_failure'): 8, ('C1', 'spontaneous_range'): 142, ('C3', 'dispense_forgery'): 3, ('C1', 'hypertensive_spike'): 4, ('C3', 'injection_informed'): 4, ('C3', 'replay'): 1} |
| 0.9 | 2.0 | 559 | 282 | {('C1', 'spontaneous_range'): 256, ('C2', 'manipulation_failure'): 3, ('C1', 'hypertensive_spike'): 11, ('C3', 'injection_informed'): 5, ('C3', 'dispense_forgery'): 5, ('C3', 'replay'): 2} |
| 0.9 | 5.0 | 1468 | 19 | {('C2', 'manipulation_failure'): 3, ('C1', 'spontaneous_range'): 3, ('C3', 'injection_informed'): 10, ('C3', 'replay'): 3} |
| 0.95 | None | 18 | 24 | {('C2', 'manipulation_failure'): 1, ('C1', 'spontaneous_range'): 20, ('C3', 'injection_informed'): 1, ('C3', 'replay'): 2} |
| 0.95 | 1.0 | 319 | 172 | {('C1', 'spontaneous_range'): 162, ('C3', 'injection_informed'): 5, ('C3', 'replay'): 5} |
| 0.95 | 2.0 | 559 | 34 | {('C1', 'spontaneous_range'): 21, ('C3', 'injection_informed'): 6, ('C3', 'replay'): 7} |
| 0.95 | 5.0 | 1468 | 33 | {('C1', 'spontaneous_range'): 20, ('C3', 'replay'): 12, ('C3', 'injection_informed'): 1} |

#### 9.3.6 (labelling of section 5) All alerts of the main population: coverage and mean size without and with the channel (design uniform)
| level | r | coverage without | coverage with | mean size without | mean size with |
|---|---|---|---|---|---|
| 0.8 | None | 12873/15084 (85.3%) | 12949/15084 (85.8%) | 4.866 | 4.558 |
| 0.8 | 1.0 | 12873/15084 (85.3%) | 12789/15084 (84.8%) | 4.866 | 4.506 |
| 0.8 | 2.0 | 12873/15084 (85.3%) | 12664/15084 (84.0%) | 4.866 | 4.464 |
| 0.8 | 5.0 | 12873/15084 (85.3%) | 12273/15084 (81.4%) | 4.866 | 4.493 |
| 0.9 | None | 13136/15084 (87.1%) | 13076/15084 (86.7%) | 6.353 | 5.525 |
| 0.9 | 1.0 | 13136/15084 (87.1%) | 12916/15084 (85.6%) | 6.353 | 5.454 |
| 0.9 | 2.0 | 13136/15084 (87.1%) | 12805/15084 (84.9%) | 6.353 | 5.472 |
| 0.9 | 5.0 | 13136/15084 (87.1%) | 13072/15084 (86.7%) | 6.353 | 5.515 |
| 0.95 | None | 13309/15084 (88.2%) | 13272/15084 (88.0%) | 7.443 | 6.796 |
| 0.95 | 1.0 | 13309/15084 (88.2%) | 13128/15084 (87.0%) | 7.443 | 6.766 |
| 0.95 | 2.0 | 13309/15084 (88.2%) | 13269/15084 (88.0%) | 7.443 | 6.772 |
| 0.95 | 5.0 | 13309/15084 (88.2%) | 13267/15084 (88.0%) | 7.443 | 6.829 |




Reading of 9.3.
* **Effective k.** 67 realised stuck_at records in m120: 30 with one reading in the window, 29 with two, 8 with three (windows of 1, 4 and 12 h, placeholders). Every reading repeats its predecessor, so the cell for the alert's reading is 1 - eps; in the tight labelling 90 of the 96 stuck_at alerts read A (6 read D: decided inside the window, but the last two readings are not both frozen).
* **Labelling of section 5 (n = 137 stuck_at alerts):** 47 to 53 of them read D: they are alerts decided after the frozen window, labelled stuck_at only because of the 24-hour window (49 of the 53 D cases at r = None are decided after the window, 4 inside it); the channel correctly reads D for them and removes stuck_at from their set, so coverage of stuck_at falls (136 to 84-90 at level 0.9). This is the channel working and the label being wrong.
* **How many silent-fault alerts stop being confusable with C1** (level 0.9, r = 1 mmHg, rep_nat 0.0200; the numbers of the generator's floats, r = None, in brackets): tight labelling, stuck_at 96 alerts: sets containing a C1 subtype 95 -> 35 (35), sets that are exactly {stuck_at} 0 -> 60 (60), true subtype kept in 90 of 94; labelling of section 5, stuck_at 137: contains C1 137 -> 79 (80), coverage 136 -> 85 (84). cuff_silent_bias (256): at most 7 sets lose their C1 subtypes (a denied reading only removes stuck_at), coverage 251 -> 245..251. dispenser_bounce (40): unchanged in practice (the COUNT template does not read the cuff; its hold and resp alerts do).
* **What it wrongly removes** (non-stuck_at alerts whose true subtype leaves the set; level 0.9): tight labelling 1 of 20 A-reading alerts (r = None), 3 of 148 (r = 1), 4 of 241 (r = 2), 8 of 643 (r = 5), mostly injection_informed and replay; labelling of section 5: 5 of 18, 162 of 319, 282 of 559, 19 of 1468, mostly spontaneous_range C1 alerts (r = 1 and 2: 142 and 256) because of the level 0.9 cut. The cost grows with rep_nat, and at level 0.95 it is 24 / 172 / 34 / 33 (section-5 labelling). With r = 5 mmHg (rep_nat 0.098) the channel no longer separates stuck_at from C1 at level 0.9 (contains C1 95 of 96 either way).
* **Sensitivity to the cumulative level:** at 0.8 the same pattern with smaller sets (stuck_at tight, r = None: contains C1 95 -> 6, exact 0 -> 89); at 0.95 the sets keep more subtypes (r = 1: contains C1 95 -> 95).
* **Whole main population** (9.3.6): coverage 95.5% -> 95.4% (tight, level 0.9, r = None) and mean size 7.83 -> 7.17 (6.35 -> 5.53 under the labelling of section 5, coverage 87.1% -> 86.7%).
* **Not determined:** the real resolution and noise of the cuff (the formula needs the difference of consecutive readings of a real stream; here the benchmark's, SD 20.1 mmHg, supplies it), and whether a real stuck cuff repeats exactly (a frozen display would; a frozen internal value re-measured would not).

### 9.4 Set metrics: coverage and mean size

Coverage = the true subtype is in the set. The old kappa and the class table at tau 0.8 are written as sets: a definite class kappa is the set of the subtypes of that class applicable at the template (coverage if the class is right), UNDETERMINED is the full set of the subtypes applicable at the template (coverage 1, large size). 'top-1' keeps only the most probable subtype. Level 0.9 and design uniform unless stated; Wilson 95% intervals; members/alerts of one event are correlated.


#### 9.4.1 Pair members (1879 with a matched alert), by group and stratum: coverage of the true subtype and mean set size. Subtype set: cumulative level 0.9, design uniform, reference cells, V0 evidence. UNDETERMINED of a kappa = the full set of the subtypes applicable at the alert's template.
| group | stratum | members | subtype set | class table, kappa at tau 0.8 as set | old rule (diag ON), kappa as set | top-1 subtype | full set (no information) |
|---|---|---|---|---|---|---|---|
| double_take_vs_bounce | dist | 527 | 271/527 (51%; 47-56) size 5.16 | 527/527 (100%; 99-100) size 11.26 | 527/527 (100%; 99-100) size 11.26 | 0/527 (0%; 0-1) size 1.00 | 527/527 (100%; 99-100) size 11.26 |
| double_take_vs_bounce | indist | 77 | 39/77 (51%; 40-62) size 5.08 | 77/77 (100%; 95-100) size 11.12 | 77/77 (100%; 95-100) size 11.12 | 0/77 (0%; 0-5) size 1.00 | 77/77 (100%; 95-100) size 11.12 |
| nonresponse_vs_falsified_dispense | dist | 364 | 362/364 (99%; 98-100) size 6.86 | 364/364 (100%; 99-100) size 14.20 | 364/364 (100%; 99-100) size 14.20 | 304/364 (84%; 79-87) size 1.00 | 364/364 (100%; 99-100) size 17.63 |
| nonresponse_vs_falsified_dispense | indist | 111 | 111/111 (100%; 97-100) size 10.51 | 111/111 (100%; 97-100) size 19.92 | 111/111 (100%; 97-100) size 19.92 | 54/111 (49%; 40-58) size 1.00 | 111/111 (100%; 97-100) size 19.92 |
| refusal_vs_robot_missed | dist | 80 | 80/80 (100%; 95-100) size 4.50 | 80/80 (100%; 95-100) size 14.00 | 80/80 (100%; 95-100) size 12.00 | 80/80 (100%; 95-100) size 1.00 | 80/80 (100%; 95-100) size 14.00 |
| refusal_vs_robot_missed | indist | 160 | 160/160 (100%; 98-100) size 8.00 | 160/160 (100%; 98-100) size 14.00 | 160/160 (100%; 98-100) size 14.00 | 80/160 (50%; 42-58) size 1.00 | 160/160 (100%; 98-100) size 14.00 |
| bounce_vs_forged_dispense | dist | 482 | 325/482 (67%; 63-71) size 4.60 | 482/482 (100%; 99-100) size 10.99 | 482/482 (100%; 99-100) size 9.92 | 163/482 (34%; 30-38) size 1.00 | 482/482 (100%; 99-100) size 12.90 |
| bounce_vs_forged_dispense | indist | 78 | 41/78 (53%; 42-63) size 5.26 | 78/78 (100%; 95-100) size 11.46 | 78/78 (100%; 95-100) size 11.46 | 37/78 (47%; 37-58) size 1.00 | 78/78 (100%; 95-100) size 11.46 |
| ALL | dist | 1453 | 1038/1453 (71%; 69-74) size 5.36 | 1453/1453 (100%; 100-100) size 12.06 | 1453/1453 (100%; 100-100) size 11.59 | 547/1453 (38%; 35-40) size 1.00 | 1453/1453 (100%; 100-100) size 13.55 |
| ALL | indist | 426 | 351/426 (82%; 78-86) size 7.62 | 426/426 (100%; 99-100) size 14.56 | 426/426 (100%; 99-100) size 14.56 | 171/426 (40%; 36-45) size 1.00 | 426/426 (100%; 99-100) size 14.56 |

By true subtype (design uniform, level 0.9): coverage and mean size of the subtype set
| group | true subtype | members | coverage, size |
|---|---|---|---|
| bounce_vs_forg | dispense_forgery | 252 | 210/252 (83%; 78-87) size 4.19 |
| bounce_vs_forg | dispenser_bounce | 308 | 156/308 (51%; 45-56) size 5.11 |
| double_take_vs | dispenser_bounce | 310 | 16/310 (5%; 3-8) size 5.28 |
| double_take_vs | double_take | 294 | 294/294 (100%; 99-100) size 5.00 |
| nonresponse_vs | dispense_forgery | 275 | 273/275 (99%; 97-100) size 6.59 |
| nonresponse_vs | drug_nonresponse | 200 | 200/200 (100%; 98-100) size 9.26 |
| refusal_vs_rob | manipulation_failure | 120 | 120/120 (100%; 97-100) size 6.33 |
| refusal_vs_rob | measurement_refusal | 120 | 120/120 (100%; 97-100) size 7.33 |

#### 9.4.2 Pair members, all strata: coverage and mean size by cumulative level and within-class prior design (cells at the reference point)
| design | level | coverage, size (all 1879) | distinguishable | indistinguishable |
|---|---|---|---|---|
| uniform | 0.8 | 1132/1879 (60%; 58-62) size 4.92 | 888/1453 (61%; 59-64) size 4.65 | 244/426 (57%; 53-62) size 5.83 |
| uniform | 0.9 | 1389/1879 (74%; 72-76) size 5.88 | 1038/1453 (71%; 69-74) size 5.36 | 351/426 (82%; 78-86) size 7.62 |
| uniform | 0.95 | 1835/1879 (98%; 97-98) size 6.90 | 1409/1453 (97%; 96-98) size 6.35 | 426/426 (100%; 99-100) size 8.77 |
| quiet_rare | 0.8 | 1056/1879 (56%; 54-58) size 3.96 | 847/1453 (58%; 56-61) size 3.71 | 209/426 (49%; 44-54) size 4.79 |
| quiet_rare | 0.9 | 1217/1879 (65%; 63-67) size 5.49 | 869/1453 (60%; 57-62) size 4.99 | 348/426 (82%; 78-85) size 7.21 |
| quiet_rare | 0.95 | 1381/1879 (73%; 71-75) size 6.39 | 1031/1453 (71%; 69-73) size 5.80 | 350/426 (82%; 78-86) size 8.39 |
| quiet_common | 0.8 | 1428/1879 (76%; 74-78) size 4.24 | 1147/1453 (79%; 77-81) size 3.95 | 281/426 (66%; 61-70) size 5.21 |
| quiet_common | 0.9 | 1541/1879 (82%; 80-84) size 5.51 | 1153/1453 (79%; 77-81) size 5.04 | 388/426 (91%; 88-93) size 7.08 |
| quiet_common | 0.95 | 1835/1879 (98%; 97-98) size 6.67 | 1409/1453 (97%; 96-98) size 6.18 | 426/426 (100%; 99-100) size 8.35 |

Class posterior (sum over the subtypes) of the pair members under the three designs, against the class-level table of section 3 (reference cells, uniform class prior): argmax class = truth class and kappa at tau 0.8
| design | argmax = truth /1879 | UNDETERMINED / confident right / confident wrong at 0.8 | confident C1 for non-C1 |
|---|---|---|---|
| uniform | 859 | 1634 / 245 / 0 | 0 |
| quiet_rare | 859 | 1455 / 245 / 179 | 179 |
| quiet_common | 859 | 1671 / 208 / 0 | 0 |
(class-level table, independence given the class: 859, 1711 / 168 / 0, 0; the subtype model is the latent-class variant G2: 859, 1634 / 245 / 0 in section 6.1)

#### 9.4.3 Main population m120, labelling of section 5 (injected first, 24 h): coverage of the true subtype and mean set size per template; subtype set at level 0.9, design uniform
| template | alerts | subtype set | class table, kappa at tau 0.8 as set | old rule (diag ON), kappa as set | top-1 subtype | full set (no information) |
|---|---|---|---|---|---|---|
| range | 8243 | 8037/8243 (98%; 97-98) size 4.98 | 8220/8243 (100%; 100-100) size 7.95 | 7564/8243 (92%; 91-92) size 2.16 | 215/8243 (3%; 2-3) size 1.00 | 8243/8243 (100%; 100-100) size 8.00 |
| sched | 699 | 501/699 (72%; 68-75) size 3.67 | 698/699 (100%; 99-100) size 11.68 | 698/699 (100%; 99-100) size 11.45 | 444/699 (64%; 60-67) size 1.00 | 699/699 (100%; 99-100) size 14.00 |
| hold | 639 | 491/639 (77%; 73-80) size 9.12 | 635/639 (99%; 98-100) size 19.59 | 634/639 (99%; 98-100) size 19.10 | 146/639 (23%; 20-26) size 1.00 | 639/639 (100%; 99-100) size 21.00 |
| count | 1490 | 1165/1490 (78%; 76-80) size 5.23 | 1490/1490 (100%; 100-100) size 11.00 | 1474/1490 (99%; 98-99) size 10.95 | 174/1490 (12%; 10-13) size 1.00 | 1490/1490 (100%; 100-100) size 11.00 |
| resp | 4013 | 2942/4013 (73%; 72-75) size 9.62 | 4008/4013 (100%; 100-100) size 19.69 | 3987/4013 (99%; 99-100) size 19.59 | 176/4013 (4%; 4-5) size 1.00 | 4013/4013 (100%; 100-100) size 20.00 |
| ALL | 15084 | 13136/15084 (87%; 87-88) size 6.35 | 15051/15084 (100%; 100-100) size 12.04 | 14357/15084 (95%; 95-96) size 8.81 | 1155/15084 (8%; 7-8) size 1.00 | 15084/15084 (100%; 100-100) size 12.32 |

By true cause: C1: subtype set: 11319/11342 (100%; 100-100) size 6.26, class table: 11316/11342 (100%; 100-100) size 11.21, old rule (diag ON): 11303/11342 (100%; 100-100) size 7.32; C2: subtype set: 1057/2679 (39%; 38-41) size 6.87, class table: 2672/2679 (100%; 99-100) size 15.68, old rule (diag ON): 2401/2679 (90%; 88-91) size 14.44; C3: subtype set: 760/1063 (71%; 69-74) size 6.02, class table: 1063/1063 (100%; 100-100) size 11.66, old rule (diag ON): 653/1063 (61%; 58-64) size 10.55

By true subtype (subtype set, level 0.9, design uniform):
| cause | true subtype | alerts | coverage, size |
|---|---|---|---|
| C1 | dose_omission | 198 | 198/198 (100%; 98-100) size 6.00 |
| C1 | double_take | 437 | 437/437 (100%; 99-100) size 5.02 |
| C1 | drug_nonresponse | 52 | 52/52 (100%; 93-100) size 10.08 |
| C1 | hypertensive_spike | 326 | 324/326 (99%; 98-100) size 4.99 |
| C1 | hypotension_below_hold | 37 | 37/37 (100%; 91-100) size 9.08 |
| C1 | measurement_refusal | 159 | 159/159 (100%; 98-100) size 5.99 |
| C1 | spontaneous_count | 340 | 340/340 (100%; 99-100) size 5.02 |
| C1 | spontaneous_hold | 246 | 246/246 (100%; 98-100) size 11.30 |
| C1 | spontaneous_range | 7180 | 7160/7180 (100%; 100-100) size 5.00 |
| C1 | spontaneous_resp | 2367 | 2366/2367 (100%; 100-100) size 10.07 |
| C2 | ble_dropout | 1503 | 61/1503 (4%; 3-5) size 8.25 |
| C2 | cuff_detached | 327 | 287/327 (88%; 84-91) size 2.35 |
| C2 | cuff_silent_bias | 256 | 251/256 (98%; 96-99) size 6.27 |
| C2 | dispenser_bounce | 40 | 17/40 (42%; 29-58) size 7.08 |
| C2 | manipulation_failure | 252 | 246/252 (98%; 95-99) size 5.36 |
| C2 | nav_delay | 164 | 59/164 (36%; 29-44) size 6.73 |
| C2 | stuck_at | 137 | 136/137 (99%; 96-100) size 6.53 |
| C3 | dispense_forgery | 355 | 355/355 (100%; 99-100) size 7.41 |
| C3 | injection_informed | 214 | 208/214 (97%; 94-99) size 6.18 |
| C3 | injection_naive | 232 | 160/232 (69%; 63-75) size 4.59 |
| C3 | replay | 262 | 37/262 (14%; 10-19) size 5.24 |

#### 9.4.4 Main population m120, scope-aware labelling (a dropout counts only if its target is in the template's data scope, window 24 h): coverage of the true subtype and mean set size per template; subtype set at level 0.9, design uniform
| template | alerts | subtype set | class table, kappa at tau 0.8 as set | old rule (diag ON), kappa as set | top-1 subtype | full set (no information) |
|---|---|---|---|---|---|---|
| range | 8243 | 8037/8243 (98%; 97-98) size 4.98 | 8220/8243 (100%; 100-100) size 7.95 | 7564/8243 (92%; 91-92) size 2.16 | 215/8243 (3%; 2-3) size 1.00 | 8243/8243 (100%; 100-100) size 8.00 |
| sched | 767 | 602/767 (78%; 75-81) size 3.84 | 766/767 (100%; 99-100) size 11.67 | 766/767 (100%; 99-100) size 11.67 | 531/767 (69%; 66-72) size 1.00 | 767/767 (100%; 100-100) size 14.00 |
| hold | 669 | 606/669 (91%; 88-93) size 9.12 | 665/669 (99%; 98-100) size 19.56 | 663/669 (99%; 98-100) size 19.17 | 159/669 (24%; 21-27) size 1.00 | 669/669 (100%; 99-100) size 21.00 |
| count | 1646 | 1599/1646 (97%; 96-98) size 5.20 | 1646/1646 (100%; 100-100) size 11.00 | 1625/1646 (99%; 98-99) size 10.94 | 228/1646 (14%; 12-16) size 1.00 | 1646/1646 (100%; 100-100) size 11.00 |
| resp | 4068 | 3835/4068 (94%; 94-95) size 9.60 | 4063/4068 (100%; 100-100) size 19.67 | 4035/4068 (99%; 99-99) size 19.58 | 213/4068 (5%; 5-6) size 1.00 | 4068/4068 (100%; 100-100) size 20.00 |
| ALL | 15393 | 14679/15393 (95%; 95-96) size 6.35 | 15360/15393 (100%; 100-100) size 12.06 | 14653/15393 (95%; 95-96) size 8.92 | 1346/15393 (9%; 8-9) size 1.00 | 15393/15393 (100%; 100-100) size 12.36 |

By true cause: C1: subtype set: 12582/12606 (100%; 100-100) size 6.49, class table: 12579/12606 (100%; 100-100) size 11.81, old rule (diag ON): 12567/12606 (100%; 100-100) size 8.31; C2: subtype set: 1176/1519 (77%; 75-79) size 5.23, class table: 1513/1519 (100%; 99-100) size 13.99, old rule (diag ON): 1241/1519 (82%; 80-84) size 11.79; C3: subtype set: 921/1268 (73%; 70-75) size 6.23, class table: 1268/1268 (100%; 100-100) size 12.25, old rule (diag ON): 845/1268 (67%; 64-69) size 11.53

#### 9.4.5 Main population m120, tight labelling (scope-aware, alert decided while the event window is open): coverage of the true subtype and mean set size per template; subtype set at level 0.9, design uniform
| template | alerts | subtype set | class table, kappa at tau 0.8 as set | old rule (diag ON), kappa as set | top-1 subtype | full set (no information) |
|---|---|---|---|---|---|---|
| range | 425 | 363/425 (85%; 82-88) size 4.57 | 424/425 (100%; 99-100) size 7.13 | 95/425 (22%; 19-27) size 3.33 | 115/425 (27%; 23-31) size 1.00 | 425/425 (100%; 99-100) size 8.00 |
| sched | 534 | 440/534 (82%; 79-85) size 3.84 | 532/534 (100%; 99-100) size 11.12 | 530/534 (99%; 98-100) size 12.21 | 420/534 (79%; 75-82) size 1.00 | 534/534 (100%; 99-100) size 14.00 |
| hold | 611 | 567/611 (93%; 90-95) size 9.49 | 601/611 (98%; 97-99) size 19.64 | 590/611 (97%; 95-98) size 19.80 | 116/611 (19%; 16-22) size 1.00 | 611/611 (100%; 99-100) size 21.00 |
| count | 1530 | 1521/1530 (99%; 99-100) size 5.23 | 1530/1530 (100%; 100-100) size 11.00 | 1524/1530 (100%; 99-100) size 10.98 | 153/1530 (10%; 9-12) size 1.00 | 1530/1530 (100%; 100-100) size 11.00 |
| resp | 3655 | 3558/3655 (97%; 97-98) size 9.60 | 3607/3655 (99%; 98-99) size 19.65 | 3541/3655 (97%; 96-97) size 19.60 | 122/3655 (3%; 3-4) size 1.00 | 3655/3655 (100%; 100-100) size 20.00 |
| ALL | 6755 | 6449/6755 (95%; 95-96) size 7.83 | 6694/6755 (99%; 99-99) size 16.23 | 6280/6755 (93%; 92-94) size 16.05 | 926/6755 (14%; 13-15) size 1.00 | 6755/6755 (100%; 100-100) size 16.82 |

By true cause: C1: subtype set: 5365/5437 (99%; 98-99) size 8.59, class table: 5385/5437 (99%; 99-99) size 17.48, old rule (diag ON): 5304/5437 (98%; 97-98) size 17.37; C2: subtype set: 580/617 (94%; 92-96) size 3.57, class table: 614/617 (100%; 99-100) size 11.40, old rule (diag ON): 441/617 (71%; 68-75) size 9.42; C3: subtype set: 504/701 (72%; 68-75) size 5.67, class table: 695/701 (99%; 98-100) size 10.79, old rule (diag ON): 535/701 (76%; 73-79) size 11.73

#### 9.4.6 Main population (labelling of section 5): cumulative level x design
| design | level | all alerts: coverage, size | C1 | C2 | C3 | silent faults (stuck_at, cuff_silent_bias, dispenser_bounce) |
|---|---|---|---|---|---|---|
| uniform | 0.8 | 12873/15084 (85%; 85-86) size 4.87 | 11318/11342 (100%; 100-100) size 4.85 | 1039/2679 (39%; 37-41) size 4.99 | 516/1063 (49%; 46-52) size 4.70 | 399/433 (92%; 89-94) size 4.91 |
| uniform | 0.9 | 13136/15084 (87%; 87-88) size 6.35 | 11319/11342 (100%; 100-100) size 6.26 | 1057/2679 (39%; 38-41) size 6.87 | 760/1063 (71%; 69-74) size 6.02 | 404/433 (93%; 91-95) size 6.42 |
| uniform | 0.95 | 13309/15084 (88%; 88-89) size 7.44 | 11342/11342 (100%; 100-100) size 7.32 | 1085/2679 (41%; 39-42) size 8.07 | 882/1063 (83%; 81-85) size 7.22 | 428/433 (99%; 97-100) size 7.47 |
| quiet_rare | 0.8 | 5294/15084 (35%; 34-36) size 3.69 | 3839/11342 (34%; 33-35) size 3.65 | 990/2679 (37%; 35-39) size 3.85 | 465/1063 (44%; 41-47) size 3.75 | 279/433 (64%; 60-69) size 3.66 |
| quiet_rare | 0.9 | 12874/15084 (85%; 85-86) size 5.50 | 11288/11342 (100%; 99-100) size 5.35 | 996/2679 (37%; 35-39) size 6.17 | 590/1063 (56%; 53-58) size 5.39 | 280/433 (65%; 60-69) size 5.50 |
| quiet_rare | 0.95 | 13175/15084 (87%; 87-88) size 6.98 | 11298/11342 (100%; 99-100) size 6.75 | 1118/2679 (42%; 40-44) size 8.11 | 759/1063 (71%; 69-74) size 6.57 | 397/433 (92%; 89-94) size 7.02 |
| quiet_common | 0.8 | 11904/15084 (79%; 78-80) size 4.52 | 10360/11342 (91%; 91-92) size 4.54 | 1006/2679 (38%; 36-39) size 4.54 | 538/1063 (51%; 48-54) size 4.25 | 425/433 (98%; 96-99) size 4.61 |
| quiet_common | 0.9 | 12523/15084 (83%; 82-84) size 5.84 | 10585/11342 (93%; 93-94) size 5.79 | 1011/2679 (38%; 36-40) size 6.11 | 927/1063 (87%; 85-89) size 5.67 | 429/433 (99%; 98-100) size 5.87 |
| quiet_common | 0.95 | 13352/15084 (89%; 88-89) size 7.13 | 11340/11342 (100%; 100-100) size 7.03 | 1074/2679 (40%; 38-42) size 7.59 | 938/1063 (88%; 86-90) size 7.07 | 430/433 (99%; 98-100) size 7.14 |


Reading of 9.4.
* **Pair members (1879), level 0.9, uniform:** coverage 1389 of 1879 (74%), mean size 5.88; distinguishable 71% (size 5.36), indistinguishable 82% (size 7.62). The old kappa and the class table cover 100% at sizes 11.6 to 14.6 because UNDETERMINED is the full set (91% of the members). Coverage at levels 0.8 / 0.9 / 0.95: 60% / 74% / 98% (sizes 4.9 / 5.9 / 6.9).
* **The set is not calibrated to its level**: it is a posterior under a model, and coverage 74% at level 0.9 says the model is wrong for the part that fails: the bounce members of group 1 (**16 of 310 covered, 5%**: a silent bounce is outweighed by three silent C1 subtypes at COUNT, with the table giving likelihood ratio 1), the bounce members of group 4 (51%), the forged dispenses of group 4 (83%). Double take, drug non-response, the refusal and the manipulation failure are covered 100%.
* **Main population, section-5 labelling:** coverage 87% (13 136 of 15 084), mean size 6.35, against the old rule 95% (size 8.81) and the class table 100% (size 12.04). By cause: C1 100% (size 6.26), C2 39% (6.87), C3 71% (6.02); the C2 figure is the mislabelled `ble_dropout` alerts (4% of 1 503; the dropout targets outside the template's scope). Scope-aware labelling: 95% (14 679 of 15 393), size 6.35, old rule 95% (8.92); C2 77%. Tight labelling: **95% (6 449 of 6 755), size 7.83, against the old rule 93% at size 16.05 and the class table 99% at size 16.23**; C2 94% (size 3.57). By template (tight): range 85%, sched 82%, hold 93%, count 99%, resp 97%. The old rule's coverage at `range` is 22% in the tight labelling (a confident C1 for alerts caused by silent faults and attacks).
* **Design and level:** on the pair members quiet_common covers most (76% / 82% / 98% at levels 0.8 / 0.9 / 0.95 against 60% / 74% / 98% for uniform and 56% / 65% / 73% for quiet_rare); in the main population uniform covers most at 0.8 and 0.9 (85%, 87%), quiet_common 79% and 83%, and quiet_rare only 35% at 0.8 (85% at 0.9), being poorly matched to a population dominated by quiet C1 events. The benchmark is not used to choose among them.

### 9.5 What could not be determined, and what to decide

* The within-class weights, eps, qc, the cumulative level and the class priors remain sensitivity values awaiting gab; the coverage of the set is conditional on them, and the benchmark's base rates were deliberately not used to set them.
* Item 3 cannot say what the channel costs on a real cuff: the false-removal figures are for rounding the benchmark's float readings to r mmHg; the real resolution, noise and freezing behaviour are device properties not in the repository.
* The real driver's STALE semantics (item 2) is a requirement, not a measurement.
* Matching is still the provisional matching of section 3; the labellings of the main population are three, and the conclusion about diagnostics depends on which is used (9.2.4).
* The set output is defined per alert; cascades, predicted alerts and the multi-alert aggregation of one event are not treated.

### 9.6 Files added by this follow-up

`/tmp/research/likelihood/{subtype_model.py,config/subtype_priors.yaml}`; scripts `pairs_subtype.py`, `diag_decomp.py`, `diag_variants.py`, `xrep_nat.py`, `xrep_report.py {tight|unscoped}`, `set_metrics.py`, `setlib.py`, `sens_data2.py`, `assemble_section9.py`; logs and tables in `logs/` and `out/` (`pairs_subtype.md`, `diag_decomp.md`, `diag_variants.md`, `xrep_nat.md`, `xrep_report_*.md`, `set_metrics.md`); data `out/pairs_p40b_sw1.pkl`, `out/main_{m120b,ff,idle1h,idle6h}.pkl`.

Reproduction (from `scripts/`): `python3 run_members.py 40 p40b 1`; `python3 run_main.py m120b 120 30 default`; `RALMON_RATES=0,0,0 python3 run_main.py ff 120 30 default`; `RALMON_DIAG_IDLE_STALE_MS=3600000 python3 run_main.py idle1h 120 30 default`; `python3 sens_data2.py`; then the report scripts above and `python3 assemble_section9.py`.
