"""Section 10.4: separate calibration on the pair population, and transfer from the main population."""
import sys, pickle, collections, math
sys.path.insert(0, "/tmp/research/likelihood/scripts"); sys.path.insert(0, "/tmp/research/likelihood")
from conflib import *
ALPHAS = (0.2, 0.1, 0.05)
members, _ = pickle.load(open(f"{common.ROOT}/out/sens3_pairs_p120r.pkl", "rb"))
for m in members: m["patient"] = m["pair"]
cal = [m for m in members if m["split"] == "calibration"]; test = [m for m in members if m["split"] == "test"]
out = []; pr = lambda *a: out.append(" ".join(str(x) for x in a))
pr(f"##### 10.4 Pair population `p120r` (3 240 pairs built = 27 variants x 120, {len({m["pair"] for m in members})} of them with at least one matched member, rounded generator, seed 0; the 1080 pairs of `p40r` were too few for a calibration part per template and group, so 3 240 pairs were built: 3x as many, new pair patients, same machinery). Split by pair (the builder's patient-level split, seed 0, fractions 0.5 / 0.25 / 0.25): calibration {len(cal)} matched members of {len({m['pair'] for m in cal})} pairs, test {len(test)} members of {len({m['pair'] for m in test})} pairs; the train part is not used. Members with a matched alert only (the unmatched are misses, not part of the alert-set).")
pr()
tc = collections.Counter(m["alert"]["t"] for m in cal); pr(f"Calibration members by template: {dict(tc)}; truth cause: {dict(collections.Counter(m['truth'] for m in cal))}")
main_t = pickle.load(open(f"{common.ROOT}/out/sens3_main_m400r_tight.pkl", "rb")); main_c = [i for i in main_t if i["split"] == "calibration"]
pr(f"Main population (tight, calibration part) for comparison: templates {dict(collections.Counter(i['alert']['t'] for i in main_c))}; truth cause {dict(collections.Counter(i['truth'] for i in main_c))}. The pair population has 50% of each mechanism and (almost) only count, resp and sched alerts; the main population is dominated by C1 range and resp alerts.")
pr()
pr("###### 10.4.1 Separate calibration on the pair calibration part: achieved coverage on the pair test part (primary method), marginal and Mondrian per template; 'pairs' = 95% cluster-bootstrap over pairs")
pr("| alpha | mode | thresholds | coverage, mean size | size distribution % (1 / 2 / 3 / 4 / 5-6 / 7-9 / 10+) |"); pr("|---|---|---|---|---|")
cals = {}
for a in ALPHAS:
    c = Cal(cal, METHODS[0], a); cals[a] = c
    for mode in ("marginal", "mondrian"):
        s = summarize(evaluate(test, c, mode)); q = f"{c.q:.3f}" if mode == "marginal" else "; ".join(f"{t} {c.qt[t]:.3f} (n {c.nt[t]})" for t in sorted(c.qt))
        pr(f"| {a} | {mode} | {q} | {fm(s).replace('patients', 'pairs')} | {dist(s['sizes'])} |")
pr()
def grp_table(title, caller, alpha):
    pr(title)
    pr("| group | stratum | test members | marginal | Mondrian per template |"); pr("|---|---|---|---|---|")
    for g in P.GROUPS:
        for key in ("dist", "indist"):
            sel = [m for m in test if m["group"] == g and (m["flag"] == (key == "indist"))]
            if not sel: continue
            pr(f"| {g} | {key} | {len(sel)} | " + " | ".join(fm(summarize(evaluate(sel, *caller(mode)), 200), False) for mode in ("marginal", "mondrian")) + " |")
    for key in ("dist", "indist"):
        sel = [m for m in test if (m["flag"] == (key == "indist"))]
        pr(f"| ALL | {key} | {len(sel)} | " + " | ".join(fm(summarize(evaluate(sel, *caller(mode)), 200), False) for mode in ("marginal", "mondrian")) + " |")
    pr()
for a in ALPHAS:
    grp_table(f"###### 10.4.2 Per group and stratum on the pair test part, SEPARATE calibration, alpha {a} (target {1-a:.2f})", lambda mode, a=a: (cals[a], mode), a)
# true subtype
pr("###### 10.4.2b Per true subtype, separate calibration, alpha 0.1, Mondrian")
pr("| group | true subtype | test members | coverage, size |"); pr("|---|---|---|---|")
for g in P.GROUPS:
    for sub in sorted({m["sub"] for m in test if m["group"] == g}):
        sel = [m for m in test if m["group"] == g and m["sub"] == sub]
        pr(f"| {g[:14]} | {sub} | {len(sel)} | {fm(summarize(evaluate(sel, cals[0.1], 'mondrian'), 200), False)} |")
pr()
# transfer
pr("###### 10.4.3 Transfer: thresholds calibrated on the MAIN population (builder's calibration part of m400r) applied to the pair test part")
for lab in ("tight", "s5"):
    thr = pickle.load(open(f"{common.ROOT}/out/thr_main_{lab}.pkl", "rb"))
    pr(f"Main calibration, {'tight (causal) labelling' if lab=='tight' else 'labelling of section 5'}:")
    pr("| alpha | mode | coverage on pair test, mean size | separate calibration (10.4.1) | coverage on main test (10.3.1) |"); pr("|---|---|---|---|---|")
    mitems = pickle.load(open(f"{common.ROOT}/out/sens3_main_m400r_{lab}.pkl", "rb")); mtest = [i for i in mitems if i["split"] == "test"]
    for a in ALPHAS:
        q, qt = thr[a]
        c = Cal([], METHODS[0], a); c.q = q; c.qt = qt
        for mode in ("marginal", "mondrian"):
            s = summarize(evaluate(test, c, mode)); sm = summarize(evaluate(test, cals[a], mode), 50); sx = summarize(evaluate(mtest, c, mode), 50)
            pr(f"| {a} | {mode} | {fm(s).replace('patients', 'pairs')} | {100*sm['rate']:.1f}%, size {sm['size']:.2f} | {100*sx['rate']:.1f}%, size {sx['size']:.2f} |")
    pr()
    pr(f"Per group and stratum, transferred thresholds, alpha 0.1, {lab}:")
    q, qt = thr[0.1]; c = Cal([], METHODS[0], 0.1); c.q = q; c.qt = qt
    pr("| group | stratum | test members | marginal | Mondrian per template |"); pr("|---|---|---|---|---|")
    for g in P.GROUPS:
        for key in ("dist", "indist"):
            sel = [m for m in test if m["group"] == g and (m["flag"] == (key == "indist"))]
            pr(f"| {g} | {key} | {len(sel)} | " + " | ".join(fm(summarize(evaluate(sel, c, mode), 200), False) for mode in ("marginal", "mondrian")) + " |")
    pr()
# methods at equal coverage on pairs
rule_cal = [(m["sub"] in rule_set(m["alert"]), len(rule_set(m["alert"]))) for m in cal]; rule_test = [(m["sub"] in rule_set(m["alert"]), len(rule_set(m["alert"]))) for m in test]
cr = sum(x[0] for x in rule_cal) / len(rule_cal)
pr("###### 10.4.4 Methods at equal coverage on the pair test part (each calibrated on the pair calibration part; Mondrian per template in brackets)")
pr("| target | " + " | ".join(METHODS) + " |"); pr("|---|---|---|---|---|")
for a in list(ALPHAS) + [1 - cr]:
    cells = []
    for m in METHODS:
        c = Cal(cal, m, a); s1 = summarize(evaluate(test, c, "marginal"), 50); s2 = summarize(evaluate(test, c, "mondrian"), 50)
        cells.append(f"{100*s1['rate']:.1f}% size {s1['size']:.2f} ({100*s2['rate']:.1f}% size {s2['size']:.2f})")
    pr(f"| {1-a:.3f}{' (= rule coverage on the calibration part)' if a not in ALPHAS else ''} | " + " | ".join(cells) + " |")
pr(f"Hierarchical rule as a set: coverage {100*sum(x[0] for x in rule_test)/len(rule_test):.1f}% on the pair test part, mean size {sum(x[1] for x in rule_test)/len(rule_test):.2f}.")
pr()
pr("Descriptive oracle-threshold comparison on the pair test part (as in 10.3.3):")
pr("| coverage reached | " + " | ".join(METHODS) + " |"); pr("|---|---|---|---|---|")
curves = {m: size_at_coverage(test, m, (0.8, 0.9, 0.95)) for m in METHODS}
for tg in (0.8, 0.9, 0.95): pr(f"| >= {tg} | " + " | ".join(f"{100*curves[m][tg][0]:.1f}% size {curves[m][tg][1]:.2f}" for m in METHODS) + " |")
open(f"{common.ROOT}/out/conformal_pairs.md", "w").write("\n".join(out))
print("\n".join(out))
