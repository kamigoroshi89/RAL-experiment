"""Section 10.3: split-conformal sets on the main population (m400r), tight and section-5 labellings."""
import sys, pickle, collections, math
sys.path.insert(0, "/tmp/research/likelihood/scripts"); sys.path.insert(0, "/tmp/research/likelihood")
from conflib import *
ALPHAS = (0.2, 0.1, 0.05)
out = []; pr = lambda *a: out.append(" ".join(str(x) for x in a))
LABN = {"tight": "tight (causal) labelling [primary]", "s5": "labelling of section 5"}
for lab in ("tight", "s5"):
    items = pickle.load(open(f"{common.ROOT}/out/sens3_main_m400r_{lab}.pkl", "rb"))
    cal = [i for i in items if i["split"] == "calibration"]; test = [i for i in items if i["split"] == "test"]; train = [i for i in items if i["split"] == "train"]
    npat = collections.Counter()
    for i in items: npat[i["split"]] |= set() if False else 0
    pr(f"##### 10.3 {LABN[lab]}: m400r, 400 patients x 30 days; the builder's patient-level split (seed 0, fractions 0.5 / 0.25 / 0.25): calibration {len(cal)} alerts of {len({i['patient'] for i in cal})} patients, test {len(test)} alerts of {len({i['patient'] for i in test})} patients (the {len(train)} alerts of the train patients are not used: the model has no trained parameter).")
    pr()
    # (a) marginal and (b) Mondrian, primary method
    pr(f"###### 10.3.1 Primary method (subtype model, accepted channels): achieved coverage on the test part, marginal and Mondrian per template. W = Wilson 95% interval over alerts; 'patients' = 95% cluster-bootstrap interval over test patients (1000 resamples, seed 0).")
    pr("| alpha | mode | threshold q (marginal) | achieved coverage, mean size | set size distribution % (1 / 2 / 3 / 4 / 5-6 / 7-9 / 10+) | per-patient coverage: median, 10th percentile |"); pr("|---|---|---|---|---|---|")
    store = {}
    for a in ALPHAS:
        c = Cal(cal, METHODS[0], a)
        for mode in ("marginal", "mondrian"):
            s = summarize(evaluate(test, c, mode)); store[(a, mode)] = s
            qtxt = f"{c.q:.3f}" if mode == "marginal" else "; ".join(f"{t} {c.qt[t]:.3f} (n {c.nt[t]})" for t in sorted(c.qt))
            pr(f"| {a} (target {1-a:.2f}) | {mode} | {qtxt} | {fm(s)} | {dist(s['sizes'])} | {s['pat_med']:.2f}, {s['pat_p10']:.2f} |")
    pr()
    # per template and per cause class
    for a in (0.1,):
        c = Cal(cal, METHODS[0], a)
        for key, ix, names in (("template", 1, ["range", "sched", "hold", "count", "resp"]), ("true cause class", 2, ["C1", "C2", "C3"])):
            pr(f"###### 10.3.2 Coverage and mean size per {key} on the test part, alpha {a} (target {1-a:.2f})")
            pr(f"| {key} | alerts | marginal | Mondrian per template |"); pr("|---|---|---|---|")
            for nm in names:
                r1 = [r for r in evaluate(test, c, "marginal") if r[ix] == nm]; r2 = [r for r in evaluate(test, c, "mondrian") if r[ix] == nm]
                if r1: pr(f"| {nm} | {len(r1)} | {fm(summarize(r1, 300), False)} | {fm(summarize(r2, 300), False)} |")
            pr()
    # per template for all alphas compact
    pr("###### 10.3.2b Coverage per template, Mondrian, all alpha (test part)")
    pr("| template | cal. alerts | alpha 0.2 | alpha 0.1 | alpha 0.05 |"); pr("|---|---|---|---|---|")
    cs = {a: Cal(cal, METHODS[0], a) for a in ALPHAS}
    for t in ["range", "sched", "hold", "count", "resp"]:
        row = []
        for a in ALPHAS:
            rr = [r for r in evaluate(test, cs[a], "mondrian") if r[1] == t]
            row.append(fm(summarize(rr, 300), False) if rr else "-")
        pr(f"| {t} | {cs[0.1].nt.get(t, 0)} | " + " | ".join(row) + " |")
    pr()
    # methods at equal coverage
    rule_cal = [(it["sub"] in rule_set(it["alert"]), len(rule_set(it["alert"]))) for it in cal]
    rule_test = [(it["sub"] in rule_set(it["alert"]), len(rule_set(it["alert"]))) for it in test]
    cr = sum(x[0] for x in rule_cal) / len(rule_cal); ct = sum(x[0] for x in rule_test) / len(rule_test)
    pr("###### 10.3.3 Methods at equal coverage (each method calibrated to the same target on the calibration part; test part; Mondrian per template in brackets)")
    pr("| target coverage | " + " | ".join(METHODS) + " |"); pr("|---|---|---|---|---|")
    rule_alpha = 1 - cr
    for a in list(ALPHAS) + [rule_alpha]:
        cells = []
        for m in METHODS:
            c = Cal(cal, m, a)
            s1 = summarize(evaluate(test, c, "marginal"), 200); s2 = summarize(evaluate(test, c, "mondrian"), 200)
            cells.append(f"{100*s1['rate']:.1f}% size {s1['size']:.2f} ({100*s2['rate']:.1f}% size {s2['size']:.2f})")
        tag = f"{1-a:.2f}" if a in ALPHAS else f"{1-a:.3f} (= coverage of the hierarchical rule on the calibration part)"
        pr(f"| {tag} | " + " | ".join(cells) + " |")
    pr()
    sz_t = sum(x[1] for x in rule_test) / len(rule_test)
    pr()
    pr("Descriptive size-coverage comparison with an oracle threshold (the smallest marginal threshold that reaches the stated coverage ON THE TEST PART ITSELF; this is not conformal, it removes the discreteness of the quantile so that sizes can be compared at the same coverage):")
    pr("| coverage reached | " + " | ".join(METHODS) + " | hierarchical rule (fixed) |"); pr("|---|---|---|---|---|---|")
    curves = {m: size_at_coverage(test, m, (0.8, 0.9, 0.932, 0.95)) for m in METHODS}
    for tg in (0.8, 0.9, 0.932, 0.95):
        pr(f"| >= {tg} | " + " | ".join(f"{100*curves[m][tg][0]:.1f}% size {curves[m][tg][1]:.2f}" for m in METHODS) + f" | {100*ct:.1f}% size {sz_t:.2f} |")
    pr(f"Hierarchical rule (diagnostics emitted), kappa as a set (kappa -> all subtypes of that class applicable at the template, UNDETERMINED -> all applicable): coverage {100*sum(x[0] for x in rule_test)/len(rule_test):.1f}% on the test part ({100*cr:.1f}% on the calibration part), mean size {sz_t:.2f}. It has no tunable threshold, so the other methods are calibrated to its calibration-part coverage in the last row.")
    # size by method distribution at alpha .1
    pr()
    pr("Set-size distribution (%, 1 / 2 / 3 / 4 / 5-6 / 7-9 / 10+) at alpha 0.1, marginal, test part:")
    for m in METHODS:
        c = Cal(cal, m, 0.1); s = summarize(evaluate(test, c, "marginal"), 50)
        pr(f"- {m}: {dist(s['sizes'])}; mean {s['size']:.2f}")
    pr(f"- hierarchical rule: " + " / ".join(f"{100*sum(1 for x in rule_test if a<=x[1]<=b)/len(rule_test):.0f}" for a, b in BINS) + f"; mean {sz_t:.2f}")
    pr()
    # sensitivity: calibration = train + calibration
    pr("###### 10.3.4 Sensitivity: calibration on train + calibration patients (75% of the patients; the model uses no training data)")
    pr("| alpha | mode | achieved coverage, mean size |"); pr("|---|---|---|")
    for a in ALPHAS:
        c = Cal(cal + train, METHODS[0], a)
        for mode in ("marginal", "mondrian"):
            pr(f"| {a} | {mode} | {fm(summarize(evaluate(test, c, mode), 300))} |")
    pr()
    # swap: calibrate on test, evaluate on calibration (exchangeability check)
    pr("###### 10.3.5 Exchangeability check at the patient level: roles of the calibration and test parts swapped (calibrate on the test patients, evaluate on the calibration patients)")
    pr("| alpha | mode | achieved coverage, mean size |"); pr("|---|---|---|")
    for a in ALPHAS:
        c = Cal(test, METHODS[0], a)
        for mode in ("marginal", "mondrian"):
            pr(f"| {a} | {mode} | {fm(summarize(evaluate(cal, c, mode), 300))} |")
    pr()
    open(f"{common.ROOT}/out/conformal_main_{lab}.md", "w").write("\n".join(out)); out.clear()
    # keep thresholds for the transfer
    thr = {a: (Cal(cal, METHODS[0], a)) for a in ALPHAS}
    pickle.dump({a: (c.q, c.qt) for a, c in thr.items()}, open(f"{common.ROOT}/out/thr_main_{lab}.pkl", "wb"))
print("done")
