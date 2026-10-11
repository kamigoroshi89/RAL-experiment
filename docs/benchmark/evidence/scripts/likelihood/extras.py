import sys, pickle, collections
sys.path.insert(0, "/tmp/research/likelihood/scripts"); sys.path.insert(0, "/tmp/research/likelihood")
import common, likelihood_attr as L, pairlib as P, main_report as R
from dataclasses import replace
out = []; pr = lambda *a: out.append(" ".join(str(x) for x in a))
# class counts across matched/all alerts
cnt = collections.Counter(); n = 0
for tag in ("pairs", "m120"):
    pass
rows = P.load("p40", 1)
att = L.LikelihoodAttributor(*[common.load()[0]])
for r in rows:
    for m in "AB":
        for a in r[m]["alerts"]:
            if a["ev_on"] is None: continue
            rd = L.classes_from_rule(att.rule, a["ev_on"], a["record"].template)
            for f, c in rd.items():
                if c in ("K", "G"): cnt[("pairs", f, c)] += 1
import mainlib as M
for d in M.load("m120"):
    for a in d["alerts"]:
        if a["ev_on"] is None: continue
        rd = L.classes_from_rule(att.rule, a["ev_on"], a["record"].template)
        for f, c in rd.items():
            if c in ("K", "G"): cnt[("main", f, c)] += 1
pr("Occurrences of the reading classes K (deliberate transition) and G (gap, link not degraded) in all VIOLATED alerts:", dict(cnt) or "none")
# per template log score by grouping
items = R.labelled("m120", "injected", 24 * 3600 * 1000)
pr("Per template log score / Brier by independence assumption (reference point otherwise):")
for g in ("none", "g1", "g2"):
    s = R.scores(items, replace(R.REF, group=g))
    pr(f"- group={g}: " + "; ".join(f"{t}: {s[t]['log']:.3f}/{s[t]['brier']:.3f}" for t in R.TEMPL if t in s))
# C2 overconfidence: calibration of C2 at sched
for g in ("none", "g2"):
    b = R.reliability(items, replace(R.REF, group=g), "ev_on", "C2", "sched")
    pr(f"- sched / C2 reliability, group={g}: " + "; ".join(f"[{i/10:.1f},{(i+1)/10:.1f}) n={x[0]} obs={x[1]/x[0]:.2f}" for i, x in enumerate(b) if x[0]))
# examples of disagreement old vs new in main
ex = {}
for it in items:
    if it["truth"] not in R.CL: continue
    r = R.post(it["alert"], R.REF)
    key = (it["alert"]["old_on"], r.argmax(), it["truth"], it["alert"]["template"])
    ex.setdefault(key, (it, r))
pr("Examples (main population) where the old rule with diagnostics and the table disagree:")
for key, (it, r) in sorted(ex.items(), key=str):
    if key[0] != key[1] and key[0] != "UNDETERMINED" and key[0] in R.CL:
        pr(f"- old={key[0]} table-argmax={key[1]} truth={key[2]} template={key[3]} sub={it['event'][1]} posterior={ {c: round(v,3) for c, v in r.posterior.items()} } used={[(u[0].split('.')[-1], u[1]) for u in r.used if u[1] != 'D']}")
open(f"{common.ROOT}/out/extras.md", "w").write("\n".join(out))
print("\n".join(out))
