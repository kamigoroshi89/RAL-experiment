import sys, pickle, collections
sys.path.insert(0, "/tmp/research/likelihood"); sys.path.insert(0, "/tmp/research/likelihood/scripts")
import common, likelihood_attr as L
from dataclasses import replace
reg, tpl, cfg = common.load()
att = L.LikelihoodAttributor(reg, L.Params())
rows = pickle.load(open(f"{common.ROOT}/out/pairs_p40_sw1.pkl", "rb"))
c = collections.Counter(); ex = {}
for r in rows[:200]:
    for m in "AB":
        for a in r[m]["alerts"]:
            if a["ev_on"] is None: continue
            res = att.posterior(a["record"], a["ev_on"])
            c[(a["template"], res.kappa(0.8), res.argmax())] += 1
            ex.setdefault(a["template"], (a, res))
for k, v in sorted(c.items()): print(k, v)
for t, (a, res) in ex.items():
    print("\n", t, {k: round(v, 3) for k, v in res.posterior.items()}, res.support)
    for u in res.used: print("   ", u[0], u[1], {k: (None if v is None else round(v, 3)) for k, v in u[2].items()})
