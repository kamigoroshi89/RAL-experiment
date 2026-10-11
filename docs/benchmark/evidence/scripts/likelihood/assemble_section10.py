import re
O = "/tmp/research/likelihood/out/"
REP = "/tmp/research/likelihood-attribution.md"
rd = lambda n: open(O + n).read().strip()
W = []; w = W.append
w("""

## 10. Second follow-up of 2026-10-11 (ADR-032 and ADR-034 accepted; tight labelling primary; conformal sets)

### 10.0 Summary, and what changed

**Decisions taken by gab and applied.** ADR-032 (dispenser group: interval since the previous opening, content change) and ADR-034 (repeat against gap) are accepted and enter the subtype model as native cells; the TIGHT (causal) labelling of the main population is the primary one, and **every table that depends on the labelling is printed for both versions (tight, labelling of section 5). The choice of the tight labelling was made after seeing the result of 9.2 (that diagnostics improve the log score under it) and after seeing that the labelling of section 5 gives C2 coverage 44.6% in 10.3; it is a decision, not a finding.** The tight labelling: a ground-truth event is compatible with an alert only if the template can be violated by the event, the dropout target is in the template's data scope, and the alert is decided while the event window is open.

**What changed in the prototype.** (i) The generator copy rounds the cuff readings (`bp`, and the `hr_pulse` the cuff reports) at its output, as run parameters `RALMON_CUFF_RES_MMHG` (1.0) and `RALMON_CUFF_PULSE_RES_BPM` (1.0), in `finalize_observed`; from here on the main population `m400r`, the pairs `p40r`, `p120r` and the fault-free run `ffr` are rounded builds. (ii) `subtype_model.py` has native cells for the accepted fields (`SubParams.adr32`, `adr34`, `rep`). (iii) New builds: `m400r` (400 patients x 30 days), `p120r` (3 240 pairs). Sections 0 to 9 are unchanged and describe the unrounded generator.

| quantity | value |
|---|---|
| Natural repeat probability, rounded generator, fault-free run | **350 of 17 797 = 0.0197** (Wilson 0.0177-0.0218); the formula of 9.3.1 predicted 0.0200; unrounded: 0 |
| Repeat at stuck_at (tight, rounded readings) | 90 of 96 alerts read A (93.8%); natural A among the other cuff-template alerts 153 of 5 106 (3.0%) |
| Rounding side effects | alert lists change for **163 of 2 160 pair members** (141 `range` and 22 `resp` alerts only in the unrounded build, 15 `resp` only in the rounded one) and for 263 of 3 600 patient-days of the main population; ground truth, pair flags and `separated_by` unchanged; 230 of 17 363 readings (1.32%) change in-band status, 13 (0.07%) the below-hold status |
| Silent-fault table, tight (stuck_at 96, cuff_silent_bias 156, dispenser_bounce 3), level 0.9, rep_nat 0.0197 | stuck_at: sets containing a C1 subtype 95 -> 35, exact {stuck_at} 0 -> 60, coverage 94 -> 90; cuff_silent_bias: C1 154 -> 150 (4 sets lose C1), coverage 152 -> 147; wrongly removed: 3 of 6 496 other alerts (148 with the channel asserted) |
| Silent-fault table, labelling of section 5 (136 / 255 / 40, 431 in all) | stuck_at: contains C1 136 -> 78, exact 0 -> 58, coverage 135 -> 85 (the 51 alerts that read D are decided after the frozen window); cuff_silent_bias 252 -> 246; wrongly removed 159 of 14 484 (mostly spontaneous_range) |
| Pairs, subtype level, accepted channels (612 distinguishable / 210 indistinguishable) | D > 0 **537 of 612 (88%)** against 255 of 612 (42%) with the section-4 channels; both members in the right direction 433 (71%) against 201 (33%); McNemar ACC against V0 b = 282, c = 0 (p 2.6e-85); all of the gain is ADR-032 (b = 282, c = 0 against the variant without it); ADR-034 and the repeated value change no direction in the pairs; indistinguishable D = 0 in 210 of 210 |
| Conformal, main population, tight, test part 5 692 alerts of 100 patients, alpha 0.1 | marginal **90.8%** (Wilson 90-92, patients 90-92) mean size 2.93; Mondrian per template 93.1% size 3.39; alpha 0.2: 84.9% / 86.4%; alpha 0.05: 95.7% / 97.3% |
| Where the marginal guarantee does not reach (alpha 0.1, tight) | per template: sched 74.9%, range 85.1%, hold 87.6% (Mondrian: all >= 90.0%); per true class: **C3 48.6%** (Mondrian 67.0%), C2 81.9% (87.3%), C1 96.6% |
| Methods at equal coverage (tight, oracle threshold, size at coverage >= 0.9) | subtype model with the accepted channels 2.93 (90.8%); without them 2.73 (90.7%); class-level table 3.12 (91.3%); prior only 4.47 (93.4%); hierarchical rule kappa as a set 16.20 at 93.4% |
| Conformal, pairs, separate calibration, alpha 0.1 (test 1 419 members of 771 pairs) | marginal 93.4% size 4.22, Mondrian 94.5% size 3.57; distinguishable 96.8%, **indistinguishable 80.6% (Mondrian 86.4%)** |
| Transfer main (tight) -> pairs, alpha 0.1 | marginal **83.9%** (size 2.83), Mondrian 87.8% (3.64), against 93.4% / 94.5% with the separate calibration; alpha 0.05 marginal 93.4% against 97.3% |

### 10.1 Cuff resolution in the generator

Implementation (research copy only): in `repo/src/ralmon/benchmark/injection.py:finalize_observed`, after the injections and before the driver reports, every `bp` sample is rounded to the multiple of `RALMON_CUFF_RES_MMHG` and every `hr_pulse` sample to the multiple of `RALMON_CUFF_PULSE_RES_BPM` (both device-profile parameters; the run default of section 10 is 1 and 1). The rounding is the last step at the device boundary, so a silent bias or a frozen value is added or repeated BEFORE the display rounds it; a frozen window therefore stays exactly identical after rounding, natural readings are rounded independently. Nothing else is touched (latent days, ground truth, labeller).

""")
w(rd("round_check.md").replace("#### 10.1.1", "#### 10.1.1"))
w("""
**Reading of 10.1.2.** The rounding changes what the monitor sees at the band edges: readings within 0.5 mmHg of a limit move across it. In the pairs, 141 `range` alerts and 22 `resp` alerts of the unrounded build disappear and 15 `resp` alerts appear; the 2160 alert lists of sections 3 to 9 are therefore those of the unrounded generator, and the pair counts in 10.2 differ slightly from section 9 (612 against 613 distinguishable pairs). The ground-truth events are identical (they come from the latent day), and so are the pair flags. This is a change of the benchmark that a real device resolution would also make; it is reported, not corrected.

#### 10.1.3 The repeated-value channel with the really rounded readings (main population m120r; rep_nat = the measured 0.0197, x0.5 and x2 as grid values)

""")
w(rd("silent_native.md"))
w("""

**Reading of 10.1.3.** Tight labelling: of 96 stuck_at alerts 90 read A (identical) and 6 read D; with rep_nat 0.0197 and level 0.9 the stuck_at sets containing a C1 subtype fall from 95 to 35 and 60 sets become exactly {stuck_at}; coverage of the true subtype falls from 94 to 90 (the 6 D alerts remove stuck_at). Smaller rep_nat makes the channel more decisive (level 0.8: 95 -> 6 containing C1) and costs more false removals when the cell is too small (rep_nat 0.0098, level 0.8: 121 other alerts, 112 of them spontaneous_resp); larger rep_nat leaves the C1 subtype in the set at level 0.95. cuff_silent_bias loses its C1 subtypes in 0 to 5 of 156 sets (a denied reading can only remove stuck_at) and dispenser_bounce does not change (tight labelling keeps only 3 bounce alerts: the COUNT alert of a bounce is decided at the next dose step, outside the open window; the 40 of the labelling of section 5 keep the table of section 9). The natural A rate among alerts that are not stuck_at is 3.0% (tight) and 2.5% (section 5), above the fault-free 1.97% because some alerts are raised inside an active stuck window that carries another cause's label, and because readings around a dose are not a random pair.

### 10.2 The accepted channels in the subtype model: pairs

Native cells. ADR-032: `dispenser.short_interval` (the interval since the previous opening is below T_b, 10 s as the reference grid value) with the bounce conditional (qc) and every other sub-cause at eps; `dispenser.no_content_change` (content change = 0) raised by the bounce by construction (1 - eps) and `None` for a dispenser without content sensing or a forged dispense with no payload. ADR-034: the field `seq_gap_or_replay` is replaced by `seq_repeat` and `seq_gap`, derived from the existing field and the delivery ratio (repeat = asserted with a complete ratio; gap = ratio below one; `None` where the two cannot be told), with cells replay_naive: repeat; naive injection and naive forged dispense: repeat with probability qc, gap with 1 - qc; ble_dropout and message_drop: gap with qc. Repeated value: P(A | stuck_at) = 1 - eps, P(A | any other) = rep_nat = 0.0197 (10.1.1). No grouped variant is used. ACC = the section-4 channels plus the three; the older variants are printed for comparison. Pairs `p40r` (rounded), design uniform.

""")
w(rd("pairs_accepted.md"))
w("""

**Reading of 10.2.**
* **All the gain is ADR-032**: D > 0 rises from 255 to 537 of 612 distinguishable pairs (group 1: 0 -> 217 of 256; group 4: 123 -> 188 of 210), the same discordant pairs as the class-level prototype of 4.5 (b = 282, c = 0). ADR-034 and the repeated value change no direction in the pairs (no stuck_at in the pairs, and the sequence evidence adds nothing beyond the verification and the dispenser fields), but they change the lean: the median Lambda of an identical stream is 0.47 (groups 2) instead of 0.68, because a denied repeat excludes the naive forgery less than a denied combined field did.
* **Group 4 indistinguishable: Lambda = +4.38 for BOTH members.** The forger in these pairs copies the bounce timing, so the interval field reads A in both members; the table, which does not model attacker timing, leans 4.4 nats toward the bounce. For the bounce member this is right, for the forged dispense it is wrong, D = 0. This is a declared limit of the interval field against an informed attacker (T_b 180 s collapses group 1: D > 0 217 -> 146).
* **Witness and verification** keep their effect: removing verification costs 81 pairs (b = 81, c = 0), removing the witness 14, both 113; diagnostics change nothing (0 discordant).
* **Sensitivity.** D > 0 does not move with eps, qc, rep_nat or the design; the lean and the both-correct count do (376 to 440 of 612 over qc 0.25 to 0.75; 376 with quiet_rare against 433).

### 10.3 Conformal sets on the main population

**Procedure.** Population `m400r`: 400 virtual patients x 30 days, rounded generator, default device profile (no authentication, no content sensing), measured-only monitor with one earlier day of history, VIOLATED alerts only. Split by patient with the builder's own function (`split_patients`, fractions 0.5 / 0.25 / 0.25, generation seed 0): 200 train, 100 calibration, 100 test patients. The model has no trained parameter, so the train part is unused (a variant that calibrates on train + calibration is in 10.3.4). Nonconformity score of an alert = 1 - p(true subtype | e, t) from the subtype model (accepted channels, design uniform, reference cells; an alert whose true subtype cannot violate the template has p = 0 and score 1). Threshold = the ceil((n+1)(1-alpha))-th smallest calibration score (the standard split-conformal quantile with the finite-sample correction; infinity, i.e. the full set, if that rank exceeds n). Prediction set = all subtypes with score <= threshold. (a) marginal: one threshold from all calibration alerts; (b) Mondrian: one threshold per template, from the calibration alerts of that template. alpha in {0.2, 0.1, 0.05} are sensitivity values.

**What the guarantee is, and is not.** Split conformal gives marginal coverage >= 1 - alpha for a new alert if calibration and test alerts are EXCHANGEABLE. Here the unit of exchange is the patient: alerts of one patient (and of one event) are strongly correlated, the benchmark injects at rates fixed by the generator (placeholders), and the split is by patient, so the statement is only that the coverage holds for the test distribution OF THIS BENCHMARK when calibration and test patients are exchangeable draws from it. It says nothing about another population (10.4 shows that it fails across populations), nothing conditional on the template or the true cause for the marginal version (10.3.2), and nothing for a real ward. Ties in the score make the coverage conservative. The intervals printed are Wilson over alerts (which ignores the correlation) and a cluster bootstrap over test patients (1 000 resamples, seed 0), which is the honest one; the per-patient coverage is also given.

""")
w(re.sub(r"^###### ", "##### ", rd("conformal_main_tight.md"), flags=re.M))
w("\n\n")
w(re.sub(r"^###### ", "##### ", rd("conformal_main_s5.md"), flags=re.M))
w("""

**Reading of 10.3.**
* **Marginal coverage holds on the test patients, with the tight labelling**: 84.9%, 90.8%, 95.7% for targets 80%, 90%, 95% (cluster intervals 83-86, 90-92, 95-96); swapping the roles of the calibration and test patients gives 83.9%, 90.3%, 95.0%. The coverage is above the target by a few points because the score is discrete (many subtypes share a probability).
* **It does not hold conditionally.** Marginal sets cover 74.9% of `sched` alerts at alpha 0.1 (target 90%), 85.1% of `range`; Mondrian per template restores 90-99% for each template at a larger mean size (3.39 against 2.93). By true cause the marginal set covers C1 96.6%, C2 81.9% and **C3 48.6%** (Mondrian 96.7 / 87.3 / 67.0): the guarantee is about the average alert, which is mostly C1, and an attack is under-covered. No threshold per cause is possible at deployment because the cause is unknown; a Mondrian partition by true class is not a usable method here.
* **Per patient** (alpha 0.1, marginal): median coverage 0.92, 10th percentile 0.83.
* **Labelling of section 5** (second table): 89.8% marginal and 92.8% Mondrian at alpha 0.1 but with mean sizes 8.4 and 9.3, because the label noise (C2 labels on dropouts outside the template's scope) pushes the thresholds toward 1; C2 coverage is 44.6% (marginal). The sets under this labelling are larger by a factor three for the same nominal coverage.
* **Methods at equal coverage.** With the oracle threshold (descriptive), at coverage >= 0.9 on the tight test part: subtype model with the accepted channels 2.93, without them 2.73, class-level table of section 1 3.12 (a class posterior spread over its subtypes by pi), prior only 4.47; at >= 0.95: 5.56 / 6.07 / 3.53 / 9.11. The hierarchical rule's kappa as a set has coverage 93.4% at mean size 16.20 (94% of its sets are of size 10 or more: UNDETERMINED is the full set). With conformal calibration to the same targets the ordering is the same (10.3.3). **The accepted channels do not shrink the sets in the main population** (the dispenser group is absent from the default profile and stuck_at is rare); their benefit is in the pairs (10.4.4). At the 0.95 target the class-level table is smaller than the subtype model, which is not what one would hope and is reported as it is.
* The comparison with the sets of section 9 (level 0.9, coverage 95% at size 7.83 under the tight labelling) is not like for like: that was a posterior-mass set, this one is calibrated.

### 10.4 Conformal sets on the pair population: separate calibration and transfer

""")
w(re.sub(r"^###### ", "##### ", rd("conformal_pairs.md"), flags=re.M))
w("""

**Reading of 10.4.**
* **The pair population needs its own calibration.** It has 50% of each mechanism and almost only `count`, `resp` and `sched` alerts (874 / 361 / 174 calibration members); the main population is 80% C1 and dominated by `resp` and `range`. Thresholds from the main population (tight) give on the pair test part 83.9% (marginal, target 90%), 87.8% (Mondrian), 93.4% (marginal, target 95%), against 93.4%, 94.5%, 97.3% with the separate calibration; the labelling of section 5 over-covers (97.7% to 100%) at sets of 7 to 13 subtypes. The drop is the non-exchangeability of the two populations, not noise.
* **Separate calibration holds marginally** (93.4% and 94.5% at alpha 0.1, cluster interval over pairs 92-95 and 93-96), but **not for the indistinguishable stratum**: 80.6% (marginal) and 86.4% (Mondrian) at alpha 0.1, 49% to 68% at alpha 0.2. By construction two identical streams give the same set for both members, so a set that holds one subtype of the pair covers only one of the two members unless it holds both; coverage 50% is the structural value of a set that picks one (group 3 `outcome_withheld`, 110 members: 50% marginal, 100% Mondrian at set size 9, i.e. by listing everything).
* **Group 4 forged dispenses** are covered 70.6% (Mondrian, alpha 0.1) while the bounce is covered 100%: the interval field makes the forgery that copies the bounce timing look like a bounce.
* **Methods at equal coverage on the pairs** (10.4.4): the subtype model with the accepted channels has the smallest sets (93.4% at size 4.22; 94.5% at 3.57 with Mondrian) against 90.6% at 4.68 without the new channels, 8.18 for the prior only and 12.6 for the class-level table (whose score cannot separate the members: its threshold is the full set); the hierarchical rule as a set covers 100% at size 12.34.
* Hold has 3 calibration members in the pairs, so its Mondrian threshold is the full set (infinity); one of the 1 419 test members is a `hold` alert.

### 10.5 What could not be determined

* **Real cuff.** The resolution of 1 mmHg is a device-profile parameter that I set as the default as instructed; the true resolution, the noise and the way a frozen cuff repeats are not in the repository. rep_nat = 0.0197 is a property of this generator with this rounding (and of the benchmark's SD of consecutive readings, 20 mmHg), not a device constant.
* **Exchangeability.** The conformal statements are marginal, over this benchmark, for patient-level exchangeable calibration and test parts; the patients of one benchmark share the generator's placeholders. They do not transfer to another population (10.4), to a real ward, or to a conditional statement. I did not use any phrase stronger than that.
* **The labelling.** The tight labelling is primary by decision, taken after the result; the section-5 labelling is printed everywhere. The ground truth of an alert is still an inference (template, time, scope); alerts caused by two co-occurring events are assigned to one.
* **ADR-034** is applied through the existing field and the delivery ratio (the extractor was not changed), so cases with a repeat and a gap in the same window read `None` for the repeat; a native extractor could do better. **ADR-032** fields are computed from the observed DISPENSE events up to the decision time, not per instance.
* **Pairs.** 3 240 pairs were built, 3 071 have a matched member; Mondrian per group is not possible at deployment (the group is unknown); Mondrian per template has 3 calibration members at `hold`. The unrounded 1080 pairs of sections 3 to 9 were not rebuilt with the accepted channels.
* **Eps, qc, the within-class weights, T_b and the levels** are still sensitivity values awaiting gab; only the sensitivity of 10.2 and 10.1.3 was run, not a full factorial of the conformal sets.

### 10.6 Files and reproduction

Files in `/tmp/research/likelihood/`: `subtype_model.py` (native ADR-032/034/repeat cells), `scripts/{round_check,silent_native,pairs_accepted,conflib,conformal_main,conformal_pairs,sens3_data}.py`, tables in `out/{round_check,silent_native,pairs_accepted,conformal_main_tight,conformal_main_s5,conformal_pairs}.md`, data `out/main_{ffr,m120r,m400r}.pkl`, `out/pairs_{p40r,p120r}_sw1.pkl`, `out/sens3_*.pkl`.

From `scripts/`:
```
export RALMON_CUFF_RES_MMHG=1 RALMON_CUFF_PULSE_RES_BPM=1
python3 run_members.py 40 p40r 1 ; python3 run_members.py 120 p120r 1
RALMON_RATES=0,0,0 python3 run_main.py ffr 120 30 default
python3 run_main.py m120r 120 30 default ; python3 run_main.py m400r 400 30 default
python3 round_check.py                       # 10.1.1, 10.1.2
python3 sens3_data.py pairs p40r ; python3 sens3_data.py main m120r ; python3 sens3_data.py pairs p120r ; python3 sens3_data.py main m400r
python3 silent_native.py                     # 10.1.3
python3 pairs_accepted.py                    # 10.2
python3 conformal_main.py                    # 10.3 (also writes the thresholds used by 10.4)
python3 conformal_pairs.py                   # 10.4
python3 assemble_section10.py                # this section
```
""")
base = open(REP).read()
if "\n## 10. Second follow-up" in base:
    base = base[: base.index("\n\n## 10. Second follow-up")]
open(REP, "w").write(base.rstrip() + "\n" + "\n".join(W))
print(len("\n".join(W).split("\n")), "lines")
