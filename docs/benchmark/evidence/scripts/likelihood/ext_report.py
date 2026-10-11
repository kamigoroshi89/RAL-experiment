"""Prototype of the ADR-032 dispenser channels (outside the contract): effect on the pairs, by threshold T_b and by variant."""
import sys, pickle, collections
sys.path.insert(0, "/tmp/research/likelihood/scripts"); sys.path.insert(0, "/tmp/research/likelihood")
import common, likelihood_attr as L, pairlib as P
from dataclasses import replace
from sweeps import pairs, post, REF, EPS0
out = []; pr = lambda *a: out.append(" ".join(str(x) for x in a))
pr("### 4.7 Prototype of the dispenser channels of ADR-032 (interval since the previous opening below T_b; opening with content_change = 0), V5")
pr("T_b is a SENSITIVITY value (the analisi nominal 'below one second' is illustrative, unverified). Distinguishable pairs, primary template; D > 0 rate and both-correct-direction by group; indistinguishable stratum D = 0 count.")
pr("| T_b | group | dist pairs | D > 0 | both correct | indist pairs | indist D = 0 | indist Lambda_A > 0 |"); pr("|---|---|---|---|---|---|---|---|")
for tb in (1_000, 10_000, 30_000, 60_000, 180_000):
    p = replace(REF, ext=True)
    st = collections.defaultdict(collections.Counter)
    for q in pairs:
        if q["which"] != "com": continue
        ra = post(q["A"], p, "on", tb); rb = post(q["B"], p, "on", tb)
        la = ra.llr(q["cA"], q["cB"]); lb = rb.llr(q["cA"], q["cB"])
        k = (q["group"], "indist" if q["flag"] else "dist"); st[k]["n"] += 1
        st[k]["Dpos"] += (la - lb) > EPS0; st[k]["both"] += (la > EPS0 and lb < -EPS0); st[k]["Dzero"] += abs(la - lb) <= EPS0; st[k]["lamA_pos"] += la > EPS0
    for g in P.GROUPS:
        d = st[(g, "dist")]; i = st[(g, "indist")]
        pr(f"| {tb/1000:g} s | {g} | {d['n']} | {d['Dpos']} | {d['both']} | {i['n']} | {i['Dzero']} | {i['lamA_pos']} |")
pr()
pr("By variant (T_b = 10 s): groups 1 and 4, D > 0 / pairs")
pr("| group | variant | pairs | D > 0 | D = 0 | flag indist |"); pr("|---|---|---|---|---|---|")
p = replace(REF, ext=True); st = collections.defaultdict(collections.Counter)
for q in pairs:
    if q["which"] != "com" or q["group"] not in ("double_take_vs_bounce", "bounce_vs_forged_dispense"): continue
    ra = post(q["A"], p, "on", 10_000); rb = post(q["B"], p, "on", 10_000)
    d = ra.llr(q["cA"], q["cB"]) - rb.llr(q["cA"], q["cB"])
    k = (q["group"], q["variant"], q["flag"]); st[k]["n"] += 1; st[k]["pos"] += d > EPS0; st[k]["zero"] += abs(d) <= EPS0
for (g, v, fl), c in sorted(st.items()):
    pr(f"| {g[:14]} | {v} | {c['n']} | {c['pos']} | {c['zero']} | {fl} |")
open(f"{common.ROOT}/out/ext_tables.md", "w").write("\n".join(out))
print("\n".join(out))
