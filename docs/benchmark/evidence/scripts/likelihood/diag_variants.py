"""Item 2, second part: re-score with and without driver diagnostics under several labellings; counterfactual of an idle cuff reported stale."""
import sys, math, collections, dataclasses
sys.path.insert(0, "/tmp/research/likelihood/scripts"); sys.path.insert(0, "/tmp/research/likelihood")
import common, mainlib as M, main_report as R
H = 3600 * 1000
out = []; pr = lambda *a: out.append(" ".join(str(x) for x in a))
# 1. the two profiles differ in the diagnostics field only
days = M.load("m120"); diff = collections.Counter(); n = 0
for d in days:
    for a in d["alerts"]:
        if a["ev_on"] is None: continue
        n += 1
        for grp in ("system", "signal_quality", "cross_device", "witness", "crypto_temporal"):
            x, y = getattr(a["ev_on"], grp), getattr(a["ev_off"], grp)
            for f in dataclasses.fields(x):
                if getattr(x, f.name) != getattr(y, f.name): diff[f"{grp}.{f.name}"] += 1
pr(f"Fields whose value differs between the profile with and without diagnostics, over the {n} VIOLATED alerts of m120: {dict(diff)}. The log-score change is therefore the contribution of `system.diagnostics_ok` alone.")
pr()
LAB = {
    "labelling of section 5 (injected first, window 24 h, any dropout target)": lambda d: M.label_alerts(d),
    "window 1 h, any dropout target": lambda d: M.label_alerts(d, 1 * H),
    "window 0 (alert decided while the event window is open), any target": lambda d: M.label_alerts(d, 0),
    "dropout target in the template's data scope, window 24 h": lambda d: M.label_alerts_scoped(d, 24 * H),
    "dropout target in scope, window 1 h": lambda d: M.label_alerts_scoped(d, 1 * H),
    "dropout target in scope, window 0": lambda d: M.label_alerts_scoped(d, 0),
}
def score(days, fn):
    sOn = sOff = 0.0; n = 0; byc = collections.defaultdict(lambda: [0, 0.0]); cls = collections.Counter()
    for d in days:
        for a, comp in fn(d):
            t, e = M.truth_of(comp, "injected")
            if t not in R.CL or a["ev_on"] is None: continue
            rOn = R.post(a, R.REF, "ev_on"); rOff = R.post(a, R.REF, "ev_off")
            lOn = -math.log(max(rOn.posterior[t], 1e-12)); lOff = -math.log(max(rOff.posterior[t], 1e-12))
            sOn += lOn; sOff += lOff; n += 1; byc[t][0] += 1; byc[t][1] += lOn - lOff
            cls[(t, {True: "D", False: "A", None: "U"}[a["ev_on"].system.diagnostics_ok])] += 1
    return n, sOn / n, sOff / n, byc, cls
pr("#### 9.2.4 Main-population log score with and without driver diagnostics, by labelling of the truth (lower is better; the labelling is the only thing that changes between rows)")
pr("| labelling | alerts scored | with diagnostics | without | change | change summed by true cause (nats): C1 / C2 / C3 |"); pr("|---|---|---|---|---|---|")
for lab, fn in LAB.items():
    n, a, b, byc, cls = score(days, fn)
    pr(f"| {lab} | {n} | {a:.4f} | {b:.4f} | {a-b:+.4f} | " + " / ".join(f"{byc[c][1]:+.1f}" for c in R.CL) + " |")
pr()
pr("#### 9.2.5 Counterfactual: a driver that reports an IDLE cuff as stale (an aggregator with a timeout; a BLE cuff that connects only when it measures is silent between measurements). Same table, cells unchanged (P(stale | C1) = eps), dropout-scope labelling, window 24 h")
pr("| driver | timeout of the idle cuff | alerts | C1 alerts with DIAG asserted | log score with | log score without | change |"); pr("|---|---|---|---|---|---|---|")
for tag, lab in (("m120", "the switch of this run (stale only in link_down windows)"), ("idle1h", "naive: stale when no cuff message for T_idle"), ("idle6h", "naive: stale when no cuff message for T_idle")):
    dd = M.load(tag)
    n, a, b, byc, cls = score(dd, lambda d: M.label_alerts_scoped(d, 24 * H))
    c1 = sum(v for (t, c), v in cls.items() if t == "C1"); c1a = cls[("C1", "A")]
    pr(f"| {lab} | {'-' if tag=='m120' else ('1 h' if tag=='idle1h' else '6 h')} | {n} | {c1a}/{c1} ({100*c1a/c1:.1f}%) | {a:.4f} | {b:.4f} | {a-b:+.4f} |")
open(f"{common.ROOT}/out/diag_variants.md", "w").write("\n".join(out))
print("\n".join(out))
