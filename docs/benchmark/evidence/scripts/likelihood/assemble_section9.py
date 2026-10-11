import re
O = "/tmp/research/likelihood/out/"
REP = "/tmp/research/likelihood-attribution.md"
def rd(name):
    return open(O + name).read().strip()
def sub(text, suffix):
    return re.sub(r"^#### (9\.3\.\d)", lambda m: f"#### {m.group(1)}{suffix}", text, flags=re.M)
def part(text, start, end=None):
    i = text.index(start); j = text.index(end) if end else len(text)
    return text[i:j].strip()

xs5 = rd("xrep_report_unscoped.md"); xt = rd("xrep_report_tight.md")
W = []; w = W.append
w("""

## 9. Follow-up of 2026-10-11 (decision 1 taken: the output is a set of subtypes)

### 9.0 What changed, and what did not

* **Decision recorded.** gab chose a SET of causes at the level of SUBTYPES: the most probable subtypes up to a declared cumulative probability (0.8, 0.9 and 0.95 are sensitivity values; 0.9 is the printed row); UNDETERMINED is the full set of the subtypes applicable at the alert's template. Metrics: coverage (the true subtype is in the set) and mean set size.
* **Sections 0 to 8 are unchanged**, and so are their numbers. The class-level module `likelihood_attr.py` is untouched; everything new is in `subtype_model.py`, `config/subtype_priors.yaml` and the scripts of section 9.8. The pairs and the main population were rebuilt with the same seeds to also store the cuff readings (`p40b`, `m120b`): 0 of 10 662 pair alerts differ from the earlier build and the main population has the same 3600 days and 17 015 alerts. One change to the generator copy: an optional counterfactual switch `RALMON_DIAG_IDLE_STALE_MS` in `driver_diag.py` (off by default; section 9.2.5). No generator defect was found (9.2.3).
* **The subtype model.** p(s | e, t) is proportional to prior_t(class(s)) times pi(s | class, t) times the product over the fields of P(class_f | s): the channels are independent given the SUB-CAUSE (the latent-class variant G2 of section 1.1), the class posterior is the sum over the sub-causes of a class, and a subtype merges the knowledge levels of replay, dispense_forgery and presence_spoof. C1 now has its own subtypes (double_take, dose_omission, spontaneous_count at `count`; drug_nonresponse, spontaneous_resp at `resp`; hypertensive_spike, spontaneous_range at `range`; hypotension_below_hold, spontaneous_hold at `hold`; measurement_refusal at `sched`), all with the same all-eps cells.
* **pi(subtype | class) is explicit** in `/tmp/research/likelihood/config/subtype_priors.yaml` as RELATIVE weights normalised over the sub-causes applicable at the template. Designs (all sensitivity values; none is a proposal): `uniform` (reference), `quiet_rare` (the quiet sub-causes get weight 0.25: the silent faults stuck_at, cuff_silent_bias, dispenser_bounce; the informed-level attacks; the spontaneous C1 events), `quiet_common` (weight 4), the last two labelled illustrative. Where the values would have to come from: ward incident statistics and device failure data (none collected); awaiting gab.
* **Truth.** The true subtype is the subtype of the ground-truth event matched to the alert (scoring side only). Three labellings of the main population are reported because item 2 shows that the labelling matters: the labelling of section 5; the same with the dropout target restricted to the template's data scope ("scope-aware"); and "tight" (scope-aware and the alert decided while the event window is open).

### 9.1 Pairs at the level of subtypes

""")
w(rd("pairs_subtype.md").replace("#### 9.1.1", "#### 9.1.1", 1))
w("""

Reading of 9.1.
* **The directions are those of the class level** (D > 0 in 257 of 613 distinguishable pairs, the same McNemar counts: no diagnostics 0 discordant, no witness b = 14, no verification b = 100, neither b = 133, with the ADR-032 channels c = 281), because D compares the same fields and the only field-level mixture that disappears is the one over the loud sub-causes of the class.
* **The lean collapses.** At class level a quiet pair carried a lean of +2.32 (group 1) and -1.92 (group 4) from the mixture over the loud C2 sub-causes; between the two actual subtypes the median Lambda of an identical stream is 0.00 (group 1: double take against bounce, 294 of 294 pairs have Lambda = 0 for both members: **the table gives likelihood ratio exactly 1**), 0.68 (groups 2 and 4: ln 2, the naive level of the forgery excluded by a denied sequence field) and 0.00 (group 3). The remaining lean is the level split inside dispense_forgery, and it moves with the design (1.57 / 0.68 / 0.22 for quiet_rare / uniform / quiet_common).
* **Both-correct-direction rises** from 169 to 203 of 613 (V0) and from 316 to 362 (V5), for the same reason.
* **The class posterior as the sum of the subtypes** (9.4.2): argmax = truth 859 of 1879 under all designs; kappa at tau 0.8: 1634 UNDETERMINED / 245 right / 0 wrong (uniform), 1455 / 245 / **179 wrong** (quiet_rare: all confident C1 for quiet members), 1671 / 208 / 0 (quiet_common). On the main population the class posterior has log score / Brier 0.884 / 0.532 (uniform), 0.837 / 0.512 (quiet_rare), 0.938 / 0.564 (quiet_common), against 0.901 / 0.536 for the independent class table.

### 9.2 Diagnostics and the log score

**Short answer.** With diagnostics the main-population log score is 0.9010 against 0.8940 without (0.0070 nats per alert, 105.6 nats over 15 084 alerts): worse. The two profiles differ in one field only, `system.diagnostics_ok` (checked on all 17 015 alerts), so the whole change is that field's. The worsening is real under the labelling of section 5, but it is produced by the labelling and by one cell, not by the diagnostics: it reverses under a labelling that respects the dropout's target (-0.0174) and under a tight time window (-0.0312). The driver switch does not make idle cuffs stale.

""")
w(rd("diag_decomp.md").replace("#### 9.2.1", "#### 9.2.1", 1))
w("""

**Why, exactly.**
1. *Which alerts get worse:* only the alerts whose true cause is C2 and whose diagnostics field is **denied** (D): `count` +249.8 nats (325 alerts, +0.77 each), `resp` +123.5 (1 214), `hold` +12.8, `sched` +12.7. A denied `diagnostics_ok` lowers the posterior of C2 by the cell (1 - P(A | C2)): 0.42 at `count`, 0.87 at `resp`, 0.84 at `sched`. The alerts with C1 (-152.6 nats) and C3 (-34.8) improve, and the C2 alerts with the field asserted improve most (`sched` -1.05 each, -81 in all); `range` is unchanged (no C2 sub-cause that can violate `range` raises the field).
2. *The cell does not fit the benchmark at `count`:* the uniform mixture over the five C2 sub-causes that can violate `count` (bounce, ble_dropout, message_drop, process_kill, uncommanded transition) gives P(stale | C2) = 0.582, while the benchmark injects only the bounce and the dropout, and **0 of the 325 `count` alerts labelled C2 has the field asserted** (9.2.2).
3. *Most of those alerts are not caused by a fault of their scope:* 9.2.3 splits the alerts labelled `ble_dropout` by the dropout's target. At `count` 284 of the 302 alerts labelled `ble_dropout` sit on a dropout of the cuff, the ECG device or the oximeter (270 of them ECG or oximeter), none of which is in the data scope of COUNT (dispenser only; the 18 on the dispenser also read D, presumably alerts decided after the recovery, not checked), and at `resp` 895 of 946 sit on an ECG or oximeter dropout, outside the scope (cuff and dispenser); the label comes from `TEMPLATES_AFFECTED`, which lists `count`, `resp`, `hold` and `sched` for any `ble_dropout` whatever its target, plus a 24-hour window after the event. The driver reports `ok` for the cuff and the dispenser, which is right; the truth label says C2, which is not. With the dropout restricted to targets in the template's scope the sign reverses (9.2.4).
4. *Per field contribution:* there is only one field. Its contribution per class: asserted -105.8 nats (better), denied +211.3 (worse), unavailable 0; by cause C1 -152.6, C2 +293.0, C3 -34.8 (labelling of section 5).

""")
w(rd("diag_variants.md"))
w("""

**STALE for the cuff: what the documents say, and what the switch does.**
* `evidence-channels.md` (field table, derivation table, D-8): `system.diagnostics_ok` is False "if a node of the scope reported level error or stale in the window", True if every capable node reported ok, else `None`. The payload is `NODE_STATE.diagnostics` in {ok, warn, error, stale}. **No document defines when a node is STALE: no period, no timeout, no lease for the diagnostics.** The lease (`liveliness_lease_ms`) and the data-stream deadline (`qos_deadline_ms`, "null for an event-driven device") are run parameters of the device profile without a value (D-8, EC-OP-18: the generator has no lease parameter), and they feed `liveliness_ok` and `qos_deadline_missed`, not `diagnostics_ok`. Nothing in `evidence-channels.md` or `fault-model.md` says that a BLE cuff connects only when it measures; the closest statement is that an event-driven device may declare no deadline.
* **What the switch does** (`driver_diag.py`): `ok` at t = 0 and every hour (period 1 h; 10 minutes gives the identical vectors), for the cuff whether or not it measures; `stale` only in the `link_down` ... `active` windows that the gateway wrote for a `ble_dropout`, at the start and every hour inside it; there is no lease (stale is immediate). **An idle cuff is not reported stale**: 0 of the 12 606 C1 alerts and 0 of the 1 268 C3 alerts (scope-aware labelling) have the field asserted, 135 C2 alerts have it, all in dropout windows (9.2.3). The cell P(stale | C1) = eps is therefore consistent with the generator. It is a REQUIREMENT on the real driver (9.2.5): ROS 2 diagnostics aggregators mark an item STALE when it has not been updated within a timeout, so a naive bridge for a device that is silent between measurements would report STALE continuously (general ROS 2 behaviour, not checked in this repository); in the counterfactual 88.6% of the C1 alerts have the field asserted and the log score worsens by +0.296 nats. That is a statement about this prototype's generator, not a measurement of a real driver.
* **No generator defect, so no fix and no rerun was needed.** The requested rerun "both ways" is 9.2.4 (with and without diagnostics, six labellings) plus 9.2.5 (the idle-stale counterfactual).
* The choice of the scope-aware labelling was made after seeing the sign of the change; all rows are printed.

### 9.3 The channel 'identical repeated value' (for stuck_at)

**Definition.** `cuff.identical_repeat` (outside the contract, prototype): A if the last two cuff `bp` readings received by the decision time of the alert (the previous day's readings included) are exactly equal, D if they differ, `None` if fewer than two exist. It is read by the templates that read the cuff (range, sched, hold, resp, sys). Cells: P(A | stuck_at) = 1 - eps (every reading of the window repeats the last value before the onset); P(A | any other sub-cause) = max(rep_nat, eps), rep_nat a SENSITIVITY value derived below. A denied reading lowers stuck_at by (eps against 1 - rep_nat).

#### 9.3.1 Natural probability of an identical repeat

""")
w(rd("xrep_nat.md"))
w("""

The generator has **no resolution**: the cuff value is a float (`latent + bias + sd * z`, `measurement.py`; no rounding, no resolution parameter), so the analytic natural probability is 0 and the fault-free run agrees (0 of 17 797 consecutive pairs). That makes the channel a perfect detector of stuck_at in this benchmark, which is an artefact. For a real cuff the resolution r is a device-specification value that is not in the repository; the table above gives rep_nat for r = 1, 2, 5 mmHg (grid values) from the fault-free differences, and the channel is evaluated by rounding the benchmark's readings to r before comparing (the frozen window stays identical, natural equality arises at about rep_nat: observed 0.0299 / 0.0483 / 0.1297 against the formula's 0.0200 / 0.0388 / 0.0980 for r = 1 / 2 / 5; the alerts are not a random sample of consecutive pairs: for example 12 of the 20 float-equal cases are alerts raised inside an active stuck_at window that carry another cause's label, the others replays and cuff_detached; see 9.3.3).

""")
w(part(xs5, "#### 9.3.2", "#### 9.3.3"))
w("\n\n")
w(sub(part(xt, "#### 9.3.3", "#### 9.3.4"), " (tight labelling)"))
w("\n\n")
for lab, text, suf in (("tight labelling", xt, " (tight labelling)"), ("labelling of section 5", xs5, " (labelling of section 5)")):
    w(f"**Effect on the set, {lab}.**\n")
    w(sub(part(text, "#### 9.3.4"), suf))
    w("\n\n")
w("""
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

""")
w(rd("set_metrics.md"))
w("""

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
""")
base = open(REP).read()
if "\n## 9. Follow-up" in base:
    base = base[: base.index("\n\n## 9. Follow-up")]
open(REP, "w").write(base.rstrip() + "\n" + "\n".join(W))
print(len(("\n".join(W)).split("\n")), "lines added")
