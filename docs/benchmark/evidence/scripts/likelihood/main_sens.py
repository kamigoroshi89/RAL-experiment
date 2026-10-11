"""Section 5 sensitivity: labelling window and mode, profile, prior (incl. the benchmark-frequency prior as a LABELLED, CIRCULAR diagnostic), confusion with the old rule."""
import sys, collections, math
sys.path.insert(0, "/tmp/research/likelihood/scripts"); sys.path.insert(0, "/tmp/research/likelihood")
import main_report as R, mainlib as M, likelihood_attr as L, common
from dataclasses import replace
out = []; pr = lambda *a: out.append(" ".join(str(x) for x in a))
H = 3600 * 1000
def overall(items, p=R.REF, ev="ev_on"):
    s = R.scores(items, p, ev); n = sum(v["n"] for v in s.values())
    return n, sum(v["n"] * v["log"] for v in s.values()) / n, sum(v["n"] * v["brier"] for v in s.values()) / n, s

pr("### 5.4 Sensitivity of the main-population scores (reference table parameters unless stated)")
pr("| setting | alerts scored | log score | Brier |"); pr("|---|---|---|---|")
for tag in ("m120", "r40"):
    for mode in ("injected", "strict"):
        for w in (1, 6, 24):
            items = R.labelled(tag, mode, w * H)
            n, l, b, _ = overall(items)
            pr(f"| {tag} ({'default profile' if tag=='m120' else 'authenticating dispenser + content sensing'}), labelling {mode}, window {w} h | {n} | {l:.3f} | {b:.3f} |")
items = R.labelled("m120", "injected", 24 * H)
n, l, b, _ = overall(items, R.REF, "ev_off"); pr(f"| m120, injected, 24 h, profile WITHOUT diagnostics | {n} | {l:.3f} | {b:.3f} |")
for pn in ("uniform", "c1_heavy", "c2_heavy", "c3_rare", "c3_heavy"):
    n, l, b, _ = overall(items, replace(R.REF, prior=pn)); pr(f"| m120, injected, 24 h, prior {pn} | {n} | {l:.3f} | {b:.3f} |")
# benchmark-frequency prior per template: circular diagnostic
freq = collections.defaultdict(collections.Counter)
for it in items:
    if it["truth"] in R.CL: freq[it["alert"]["template"]][it["truth"]] += 1
def emp_scores():
    ls = br = 0.0; n = 0; per = {}
    for it in items:
        if it["truth"] not in R.CL: continue
        t = it["alert"]["template"]
        r = R.post(it["alert"], R.REF)
        pri = {c: freq[t][c] / sum(freq[t].values()) for c in R.CL}
        lp = {c: (math.log(pri[c]) + r.loglik[c] if pri[c] > 0 and r.loglik[c] > -1e8 else -math.inf) for c in R.CL}
        m = max(lp.values()); ex = {c: math.exp(lp[c] - m) for c in R.CL}; z = sum(ex.values()); pp = {c: ex[c] / z for c in R.CL}
        pt = max(pp[it["truth"]], 1e-12)
        l = -math.log(pt); b = sum((pp[c] - (c == it["truth"])) ** 2 for c in R.CL)
        ls += l; br += b; n += 1
        x = per.setdefault(t, [0, 0.0, 0.0]); x[0] += 1; x[1] += l; x[2] += b
    return n, ls / n, br / n, per
n, l, b, per = emp_scores()
pr(f"| m120, injected, 24 h, prior = benchmark class frequency per template (CIRCULAR DIAGNOSTIC, not a method) | {n} | {l:.3f} | {b:.3f} |")
pr()
pr("Per template, benchmark-frequency-prior diagnostic: " + "; ".join(f"{t}: n={v[0]} log={v[1]/v[0]:.3f} Brier={v[2]/v[0]:.3f} (class counts {dict(freq[t])})" for t, v in per.items()))
pr()
# confusion with old rule
pr("### 5.5 Attributed cause against the truth cause of the matched alert: old rule (diagnostics emitted / not) and likelihood table (argmax; kappa at tau .8), m120, injected-first labelling")
for label, getter in (("old rule, diagnostics emitted", lambda it: it["alert"]["old_on"]), ("old rule, no diagnostics", lambda it: it["alert"]["old_off"]),
                      ("table, argmax", lambda it: R.post(it["alert"], R.REF).argmax()), ("table, kappa at .8", lambda it: R.post(it["alert"], R.REF).kappa(0.8)),
                      ("table, kappa at .5", lambda it: R.post(it["alert"], R.REF).kappa(0.5)), ("table, argmax, C1-heavy illustrative prior", lambda it: R.post(it["alert"], replace(R.REF, prior="c1_heavy")).argmax())):
    ct = collections.defaultdict(collections.Counter)
    for it in items:
        if it["truth"] in R.CL: ct[it["truth"]][getter(it)] += 1
    pr(f"- {label}: " + "; ".join(f"truth {t}: " + ", ".join(f"{k}={v}" for k, v in sorted(ct[t].items())) for t in R.CL))
open(f"{common.ROOT}/out/main_sens_tables.md", "w").write("\n".join(out))
print("\n".join(out))
