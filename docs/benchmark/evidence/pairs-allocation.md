# Confounder pairs: variants, realised share, allocation (HEAD a968cb2, read-only analysis)

Technical, pre-clinical. Real builder pieces (`BuildContext.build_pair`, `evaluate_pair`, labeller) on a copy under `/tmp/research/pairs/`. Every awaiting row is a labelled PLACEHOLDER (circadian peak 14:00, intake lag 5 s, double-take gap 2 min, nominal bounce 500 ms, durations 1/4/12 h), so shares that depend on them are conditional. 1000 pairs per variant, 27 variants (19 committed plus 8 prototype). Scripts and rows: `scripts/`, `rows_k1.jsonl`, `rows_g4.jsonl`; patch of the prototype: `g4_confounders.patch`.

## 1. The 19 committed variants

Computed flag against YAML `expected_indistinguishable`: **19 of 19 agree** on the test fixture base, and on the real builder base for 18 (below). `test_committed_grid_matches_the_computed_separation` (tests/benchmark/test_c1_confounders.py:1889) loops over all 19, but with one fixed base (`BASE`, :1325, dose 0, one patient), so it cannot see per-pair variation.

| group | indistinguishable | computed `separated_by` of the distinguishable ones |
|---|---|---|
| double_take_vs_bounce | 1 of 8 (`stress_nocontent_norobot`) | nominal: dispense_interval (+ content_change, witness when available); stress: content_change, witness |
| nonresponse_vs_falsified_dispense | 2 of 8 (`informed_robot_noauth`, `informed_norobot_noauth`) | naive: witness, dispense_seq; auth: verification; informed+auth: verification only |
| refusal_vs_robot_missed | 2 of 3 (`outcome_withheld`, `robot_absent`) | `outcome_reported`: robot_task_outcome |

**Discrepancy found (per pair, not per variant).** `naive_norobot_noauth` is computed indistinguishable in **67 of 1000 pairs** (YAML: False). The naive forger numbers from `FORGED_SEQ_START = 1` (inject_c3.py:174); when the patient's other dose is naturally omitted (about 6 to 7% of days) the real dispense also carries number 1, so both days hold one dispense `(420, seq 1)`. In the other naive variants dispense_seq fails to separate in 4.5 to 6.7% of pairs, but witness or verification still separates. Consequence: the stratum must come from the per-pair flag in the sidecar (`injection_log[].indistinguishable_by_construction`), never from the variant id. Group 2 therefore has a small incidental indistinguishable stratum (5.0% of the pairs of that variant are positive and indistinguishable).

## 2. Fourth group `bounce_vs_forged_dispense` (prototype)

Members: A = C2 `dispenser_bounce` at a real dispense (gap = nominal 500 ms placeholder); B = C3 `dispense_forgery` at the same instant (tick + gap); both keep the real dose (`ForcedSlot ON_TIME`), so the latent days are identical (`pressure_differs=False`). The forger does not need a spoofed INTAKE because the real one exists in both members. Robot present, so witness never differs. Grid: attacker x verification x content_change.

**Machinery: expressible without redesign.** Minimal edits in `confounders.py` (82-line patch): constant and `GROUPS` (:137-143, `__all__` :117), `_GROUP_INFO` entry (:211-224), `Variant.__post_init__` branch (:382, :387), `content_sensing` (:399) and `authenticating` (:415) properties extended to the new group, one branch in `build_confounder_pair` (before :815). `load_confounder_design` (:486) then needs the YAML group. `builder.pair_units` (:1792) and `_leak_words` (:2459) iterate `GROUPS` unchanged. `build_pair`, `generate` and `python -m ralmon.benchmark verify` pass on a 270-pair build.

| variant (attacker, verification, content) | indistinguishable | separated_by (1000 pairs, constant) |
|---|---|---|
| naive, any, any (4 variants) | no | dispense_seq always (+verification, +content_change when available) |
| informed, auth, content / nocontent | no | verification (+content_change) |
| informed, noauth, content | no | content_change only |
| informed, noauth, nocontent | **yes** | none |

1 of 8 indistinguishable. Two limits of the injector, not of the machinery: (a) a forged DISPENSE always has payload `{}` (inject_c3.py:962), so content_change separates the informed attacker; if the informed attacker copies `content_change = 0.0` (optional patch, `g4_inject_c3_optional.patch`) `informed_noauth_content` also becomes indistinguishable: 2 of 8. (b) An attacker that "copies a valid tag" is not expressible: every forgery adds a failed gateway verification when the dispenser authenticates (inject_c3.py:964-966; keyless, EC-GAP-9). Needs a new capability level (a relay with a genuine tag), a design decision.

## 3. Realised share of a pair (day-0 positives: A's labelled event and B's injection both realised)

B is realised in 27000 of 27000 pairs. So the share is the A-side share. n = 1000 per variant, Monte Carlo se = 0.007 (g1), 0.014 (g2), 0 (g3, g4); pooled per group about 0.004.

| group | per-variant range | pooled | with closing-step events |
|---|---|---|---|
| double_take_vs_bounce | .930 to .952 | .942 | .963 to .979 (.969) |
| nonresponse_vs_falsified_dispense | .703 to .755 | .729 | same |
| refusal_vs_robot_missed | 1.000 | 1.000 | 1.000 |
| bounce_vs_forged_dispense | 1.000 | 1.000 | 1.000 |

Why nonresponse loses 27%: the labelled C1 event is a RESP violation, and RESP is satisfied if the single reading in [dose+1 h, dose+2 h] (08:15 and 22:15, exactly one per window) is at least `delta_resp` = 7.5 mmHg below the pre-dose reading. A complete non-response (scale 0) still lets the latent pressure fall by chance or by the circadian trend. Measured: positive 86.5% for the morning dose (3461/4000), 60.4% for the evening (2416/4000); recomputed from the latent readings of 300 pairs, spontaneous satisfaction 10% (15/150) and 39% (59/150). The evening figure depends on the placeholder circadian peak. Group 1 loses 5.8% for the same arithmetic as natural omission of the other dose (count stays at 2); for the evening dose 5.3 of those 5.5 points re-appear as closing-step events of the tail day.

## 4. Allocation

Rules: equal n per distinguishable variant (positive and flag False); test count X ~ Poisson-binomial with each pair in test with prob. 0.25 thinned by its stratum probability; "P5 >= 56" means CDF(55) < 0.05; indistinguishable variants: equal n, pooled per group, incidental indistinguishable pairs of the distinguishable variants counted. Half-width: normal approximation at p = 0.5 (worst case): test pairs needed **97 / 43 / 25** for 0.10 / 0.15 / 0.20 (96.04, 42.68, 24.01).

Distinguishable stratum:

| group | d_g | s (per pair) | n per variant, mean >= 56 | n per variant, P5 >= 56 | pairs (P5) |
|---|---|---|---|---|---|
| double_take | 7 | .942 | 34 | **41** | 287 |
| nonresponse | 6 | .729 | 52 | **62** | 372 |
| refusal | 1 | 1.000 | 224 | **269** | 269 |
| bounce_vs_forged | 7 | 1.000 | 32 | **39** | 273 |
| total | | | | | 1201 |

Indistinguishable stratum (n per indistinguishable variant, P5 rule; i_g = 1, 2, 2, 1 variants):

| half-width | g1 | g2 | g3 | g4 | total pairs (all strata) | day-records | disk | build (1 core) | day-records vs 6400 |
|---|---|---|---|---|---|---|---|---|---|
| 0.10 | 472 | 307 | 223 | 446 | **3179** | 12716 | 16.3 GB | 15 min | 1.99x |
| 0.15 | 223 | 145 | 106 | 211 | **2137** | 8548 | 10.9 GB | 10 min | 1.34x |
| 0.20 | 138 | 89 | 65 | 130 | **1777** | 7108 | 9.1 GB | 8.4 min | 1.11x |

Per group totals (P5): h=0.10: 759 / 986 / 715 / 719; h=0.15: 510 / 662 / 481 / 484; h=0.20: 425 / 550 / 399 / 403. Mean-only rule (no P5 margin): 2716 / 1758 / 1440. The indistinguishable stratum is 62% of the pairs at 0.10.

Cost, measured on builds of 81 and 270 pairs (verified): a pair has 2 members x (scored day + tail day) = **4 day-records**, 3 files each (days, truth, generator) plus 2 care plans = **14 files**; 5.115 MB and 0.282 s per pair (serial `generate`); a virtual patient costs 1.29 MB and 0.071 s per day-record, the same as a pair (so the recorded 126 s / 2.2 GB for 200 + 76 patients is consistent). Current design: 38 pairs = 152 day-records = 2.4% of 6400. Day-records, not files, are the unit of the 6400 (800 x 8).

Test share (P5 rule; total pairs at h = 0.10 / 0.15 / 0.20; distinguishable stratum only):

| test share | totals | dist-only |
|---|---|---|
| 0.20 | 3994 / 2689 / 2238 | 1512 |
| **0.25** | 3179 / 2137 / 1777 | 1201 |
| 0.30 | 2638 / 1773 / 1475 | 997 |
| 1/3 | 2369 / 1593 / 1322 | 896 |
| 0.50 | 1558 / 1043 / 865 | 589 |

Rule "equal pairs per variant": the total of the distinguishable stratum does not depend on it (every pair of a distinguishable variant counts), only on the mean s; weighting by 1/s changes counts by under 4% (g2: s from .703 to .755). The rule only decides per-variant precision: at 41 pairs a variant has about 10 test pairs. A real split is hypergeometric over 200 + pairs units (Monte Carlo, 20000 draws, h = 0.15 allocation): P5 = 56 or 57, minimum 40 to 41, same as the binomial. Even n for group 2 keeps morning and evening doses balanced (`dose_index = ordinal % 2`, builder.py:1814).

**Builder needs a change:** `confounder_pairs_per_variant` is one integer (builder.py:1162, loop :1796). Per-variant counts need new parameter rows (numbers cannot live in the `confounders` YAML section).

## 5. Quantities to report on the pairs

Unit: a positive pair of the test split, stratum from its own flag. For member M the **relevant event** is the injected ground-truth event of the mechanism (C2/C3), or for a C1 member the labelled event with `injected = True` and the subtype, in day 0 or in `closing_step_truth`; its alert is the VIOLATED detection matched to it, with label kappa; none matched = NONE (a miss, neither right nor abstention). Truth cause c_A = C1 (g1, g2, g3), C2 (g4); c_B = C2 (g1, g3), C3 (g2, g4).

* **A mistaken for B**: kappa_A = c_B. **B mistaken for A**: kappa_B = c_A. Confident wrong: any definite kappa other than c_M (includes the third cause). Abstention: kappa = UNDETERMINED. Pair level: both correct; pair abstention (both UNDETERMINED).
* **Distinguishable stratum**: P(both correct); McNemar between methods X, Y on that indicator: b = X right and Y not, c = the reverse, exact binomial test on b + c.
* **Indistinguishable stratum**: pair abstention rate (Wilson 95%) and the rate of pairs with a confident kappa (wrong for at least one member by construction; with identical streams kappa_A = kappa_B, except groups 1 and 2 where the pressure differs).
* B in g2 informed with a robot has two events (forgery and spoof): use the forgery.

Not determined, with evidence:
1. **Current RuleAttributor cannot reach the "correct" cell for A.** I ran the measured-only `OursDetector` (no forecaster) on 40 pairs per variant (research registry: the real one lacks 7 names, OPF-6; probe profile mine): kappa = C1 for **0 of 2160 members** (1080 pairs). Reason: the benchmark emits no NODE_STATE `diagnostics` report, so `system.diagnostics_ok` is None and exclusion never completes (attribution-rule.md; ADR proposals near 03-decisions.md:365). COUNT has no C1 and no dispenser evidence field (ADR-032 proposed), so g1 and g4 give UNDETERMINED for both members whatever "distinguishable by construction" says; g3 gives B = C2 (40/40) and A UNDETERMINED; C3 appears only with verification (g2: 27 to 28/40; g4: 28 to 31/40) or a repeated sequence number. The "both correct" cell is empty until those contracts change; the by-construction flag measures the streams, not the attributor.
2. **Time matching.** For groups 1 and 4 the COUNT alert is decided at the evening dose: 14 h after the injected event when the extra dispense is the morning one (about 45% of members: 143 of 320 in g1). A one-to-one `match_events` with a narrow tolerance would score B as missed. The pair needs its own matching (alert of a template in the record's `details["templates"]`, decided after the onset); I did not define the window.
3. **Naive forgery in g4** produces no COUNT alert in 162 of 314 B members: the monitor rejects the dispense as a duplicate (same number), so B is a miss, not a wrong attribution.
4. A single device profile per run (`detector_params.ours.device_profile`) does not fit pair variants that differ in authentication; the profile must follow the variant (not recorded per pair, only `variant_id`).
5. Positive-pair share was measured at day 0 with placeholders; group 2 especially.
