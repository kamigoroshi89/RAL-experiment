"""Section 5: main population. Log score and Brier per template, calibration curves, silent-fault members."""
import sys, math, collections
sys.path.insert(0, "/tmp/research/likelihood/scripts")
import mainlib as M, common, likelihood_attr as L
from dataclasses import replace
reg, tpl, cfg = common.load()
att = L.LikelihoodAttributor(reg)
REF = L.Params()
CL = ("C1", "C2", "C3")
TEMPL = ["range", "sched", "hold", "count", "resp"]
NB = 10

def labelled(tag, mode="injected", window=24 * 3600 * 1000):
    out = []
    for d in M.load(tag):
        for a, comp in M.label_alerts(d, window):
            t, e = M.truth_of(comp, mode)
            out.append(dict(alert=a, truth=t, event=e, day=d))
    return out

def post(a, p, ev="ev_on", mask=frozenset(), day=None, tb=10_000):
    e = a[ev]
    if e is None: return None
    pp = replace(p, mask=mask)
    return att.posterior(a["record"], e, params=pp)

def scores(items, p=REF, ev="ev_on", prior_only=False):
    """per template: n, log score, Brier, skill vs prior-only; items with truth in C1..C3"""
    by = collections.defaultdict(list)
    for it in items:
        if it["truth"] not in CL: continue
        r = post(it["alert"], p, ev)
        if r is None: continue
        if prior_only:
            pri = {c: (L.PRIORS[p.prior][c] if c in r.support else 0.0) for c in CL}; z = sum(pri.values()); post_ = {c: pri[c] / z for c in CL}
        else:
            post_ = r.posterior
        by[it["alert"]["template"]].append((it["truth"], post_, r.support))
    res = {}
    for t, v in by.items():
        ls = []; br = []; unsup = 0
        for truth, pp, sup in v:
            pt = pp[truth]
            if pt <= 0: unsup += 1; pt = 1e-12
            ls.append(-math.log(pt)); br.append(sum((pp[c] - (c == truth)) ** 2 for c in CL))
        res[t] = dict(n=len(v), log=sum(ls) / len(ls), brier=sum(br) / len(br), unsup=unsup,
                      share={c: sum(1 for x in v if x[0] == c) for c in CL})
    return res

def reliability(items, p=REF, ev="ev_on", cause="C1", template=None, nb=NB):
    bins = [[0, 0] for _ in range(nb)]
    for it in items:
        if it["truth"] not in CL: continue
        if template and it["alert"]["template"] != template: continue
        r = post(it["alert"], p, ev)
        if r is None: continue
        pc = r.posterior[cause]
        b = min(nb - 1, int(pc * nb)); bins[b][0] += 1; bins[b][1] += (it["truth"] == cause)
    return bins

def top_label(items, p=REF, ev="ev_on", template=None, nb=5):
    """confidence of the argmax against accuracy"""
    bins = [[0, 0, 0.0] for _ in range(nb)]
    for it in items:
        if it["truth"] not in CL: continue
        if template and it["alert"]["template"] != template: continue
        r = post(it["alert"], p, ev)
        if r is None: continue
        am = r.argmax(); conf = r.posterior[am]
        b = min(nb - 1, int((conf - 1 / 3) / (2 / 3) * nb)) if conf > 1 / 3 else 0
        bins[b][0] += 1; bins[b][1] += (am == it["truth"]); bins[b][2] += conf
    return bins

def ece_top(items, p=REF, ev="ev_on", template=None, nb=10):
    bins = [[0, 0, 0.0] for _ in range(nb)]; n = 0
    for it in items:
        if it["truth"] not in CL: continue
        if template and it["alert"]["template"] != template: continue
        r = post(it["alert"], p, ev)
        if r is None: continue
        am = r.argmax(); conf = r.posterior[am]; b = min(nb - 1, int(conf * nb))
        bins[b][0] += 1; bins[b][1] += (am == it["truth"]); bins[b][2] += conf; n += 1
    return sum(abs(b[1] - b[2]) for b in bins) / n if n else float("nan")

if __name__ == "__main__":
    tag = sys.argv[1] if len(sys.argv) > 1 else "m120"
    out = []; pr = lambda *a: out.append(" ".join(str(x) for x in a))
    items_inj = labelled(tag, "injected"); items_strict = labelled(tag, "strict")
    days = M.load(tag)
    pr(f"## 5. Main population `{tag}`: {len(days)} patient-days, {sum(len(d['alerts']) for d in days)} VIOLATED alerts")
    c = collections.Counter(it["truth"] for it in items_inj)
    pr("Alert truth (many-to-one, template- and time-compatible ground-truth event, injected events first):", dict(c))
    pr(f"Strict mode (alerts compatible with events of two causes excluded): {dict(collections.Counter(it['truth'] for it in items_strict))}")
    pr()
    for label, items in (("injected-first labelling", items_inj), ("strict labelling (ambiguous alerts dropped)", items_strict)):
        pr(f"### 5.1 Log score and Brier per template, {label}; reference point {REF}")
        pr("| template | n alerts | truth C1/C2/C3 | log score (nats) | Brier | prior-only log score | prior-only Brier | true cause unsupported |")
        pr("|---|---|---|---|---|---|---|---|")
        s = scores(items); s0 = scores(items, prior_only=True)
        tot_n = 0; tl = tb = t0l = t0b = 0
        for t in TEMPL:
            if t not in s: continue
            x = s[t]; y = s0[t]
            pr(f"| {t} | {x['n']} | {x['share']['C1']}/{x['share']['C2']}/{x['share']['C3']} | {x['log']:.3f} | {x['brier']:.3f} | {y['log']:.3f} | {y['brier']:.3f} | {x['unsup']} |")
            tot_n += x["n"]; tl += x["n"] * x["log"]; tb += x["n"] * x["brier"]; t0l += y["n"] * y["log"]; t0b += y["n"] * y["brier"]
        pr(f"| ALL | {tot_n} | | {tl/tot_n:.3f} | {tb/tot_n:.3f} | {t0l/tot_n:.3f} | {t0b/tot_n:.3f} | |")
        pr()
    pr("### 5.2 Calibration curves (injected-first labelling): P(truth = c) against the stated p_c, 10 equal-width bins, count per bin (n) and observed frequency")
    for t in TEMPL:
        for cause in CL:
            b = reliability(items_inj, REF, "ev_on", cause, t)
            if sum(x[0] for x in b) == 0: continue
            pr(f"- {t} / {cause}: " + "; ".join(f"[{i/NB:.1f},{(i+1)/NB:.1f}) n={x[0]} obs={x[1]/x[0]:.2f}" for i, x in enumerate(b) if x[0]))
    pr()
    pr("Top-label expected calibration error (10 bins), per template:", {t: round(ece_top(items_inj, REF, "ev_on", t), 3) for t in TEMPL})
    pr()
    # silent faults
    pr("### 5.3 Silent-fault alerts (stuck_at, cuff_silent_bias, dispenser_bounce): posterior and old rule")
    sil = [it for it in items_inj if it["truth"] == "C2" and it["event"] and it["event"][1] in M.SILENT]
    ctr = collections.Counter(); oldc = collections.Counter(); oldoff = collections.Counter()
    for it in sil:
        r = post(it["alert"], REF, "ev_on")
        ctr[(it["event"][1], r.argmax(), r.kappa(0.8))] += 1
        oldc[(it["event"][1], it["alert"]["old_on"])] += 1; oldoff[(it["event"][1], it["alert"]["old_off"])] += 1
    pr(f"alerts matched to silent faults: {len(sil)}")
    pr("| subtype | argmax | kappa @ .8 | n |"); pr("|---|---|---|---|")
    for k, v in sorted(ctr.items()): pr(f"| {k[0]} | {k[1]} | {k[2]} | {v} |")
    pr("old rule, diagnostics emitted:", dict(oldc)); pr("old rule, no diagnostics:", dict(oldoff))
    open(f"{common.ROOT}/out/main_tables_{tag}.md", "w").write("\n".join(out))
    print("\n".join(out))
