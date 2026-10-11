"""Section 10.1.3-10.1.5: the repeated-value channel with the really rounded readings (m120r)."""
import sys, collections, json
sys.path.insert(0, "/tmp/research/likelihood/scripts"); sys.path.insert(0, "/tmp/research/likelihood")
from setlib import *
import pickle
REPN = json.load(open(f"{common.ROOT}/out/rep_nat_rounded.json"))["rep_nat"]
SIL = ("stuck_at", "cuff_silent_bias", "dispenser_bounce"); C1S = set(SM.C1_SUBTYPES)
out = []; pr = lambda *a: out.append(" ".join(str(x) for x in a))
def load(lab): return pickle.load(open(f"{common.ROOT}/out/sens3_main_m120r_{lab}.pkl", "rb"))
LABN = {"tight": "tight (causal) labelling", "s5": "labelling of section 5"}
def sp_(level, rep, mult=1.0): return SM.SubParams(base=REF, design="uniform", level=level, rep=rep, rep_nat=REPN * mult)
for lab in ("tight", "s5"):
    items = load(lab)
    pr(f"##### {LABN[lab]}: {len(items)} alerts; silent-fault alerts: " + ", ".join(f"{s} {sum(1 for i in items if i['truth']=='C2' and i['sub']==s)}" for s in SIL) + f" (total {sum(1 for i in items if i['truth']=='C2' and i['sub'] in SIL)})")
    pr()
    pr("Reading class of the channel (really rounded readings, cuff templates) by true subtype:")
    pr("| true subtype | alerts | A | D | U |"); pr("|---|---|---|---|---|")
    c = collections.defaultdict(collections.Counter)
    for it in items:
        if it["alert"]["t"] in SM.CUFF_TEMPLATES: c[it["sub"]][it["alert"]["rep"][None]] += 1
    for s in sorted(c):
        n = sum(c[s].values())
        if n >= 30 or s in SIL: pr(f"| {s} | {n} | {c[s]['A']} ({100*c[s]['A']/n:.1f}%) | {c[s]['D']} | {c[s]['U']} |")
    nat_a = sum(v["A"] for s, v in c.items() if s != "stuck_at"); nat_n = sum(v["A"] + v["D"] for s, v in c.items() if s != "stuck_at")
    pr(f"Natural A rate among the non-stuck_at alerts: {nat_a}/{nat_n} = {nat_a/nat_n:.4f} (fault-free pairs: {REPN:.4f}).")
    pr()
    pr("Effect on the subtype set (design uniform; rep_nat = the measured value x multiplier). 'Contains C1': the set holds a C1 subtype; 'exact': the set is exactly the true subtype; 'lose C1': sets that contained a C1 subtype and no longer do.")
    pr("| level | rep_nat | true subtype | alerts | coverage without -> with | mean size without -> with | contains C1 without -> with | exact without -> with | lose C1 |"); pr("|---|---|---|---|---|---|---|---|---|")
    wrong_rows = []
    for lvl in (0.8, 0.9, 0.95):
        for mult in (0.5, 1.0, 2.0):
            sp0 = sp_(lvl, False); sp1 = sp_(lvl, True, mult)
            agg = {s: collections.Counter() for s in SIL}; sz = {s: [0, 0] for s in SIL}; wrong = collections.Counter(); nA = 0; nn = 0
            for it in items:
                S0 = sub_result(it["alert"], sp0).top_set(lvl); S1 = sub_result(it["alert"], sp1).top_set(lvl); tr = it["sub"]
                if it["truth"] == "C2" and tr in SIL:
                    a = agg[tr]; a["n"] += 1; a["cov0"] += tr in S0; a["cov1"] += tr in S1
                    a["c10"] += bool(set(S0) & C1S); a["c11"] += bool(set(S1) & C1S); a["ex0"] += S0 == [tr]; a["ex1"] += S1 == [tr]
                    a["lose"] += bool(set(S0) & C1S) and not (set(S1) & C1S); sz[tr][0] += len(S0); sz[tr][1] += len(S1)
                elif tr != "stuck_at":
                    nn += 1
                    if tr in S0 and tr not in S1: wrong[(it["truth"], tr)] += 1
                    if it["alert"]["t"] in SM.CUFF_TEMPLATES and it["alert"]["rep"][None] == "A": nA += 1
            for s in SIL:
                a = agg[s]; n = a["n"]
                if n: pr(f"| {lvl} | {REPN*mult:.4f} | {s} | {n} | {a['cov0']} -> {a['cov1']} | {sz[s][0]/n:.2f} -> {sz[s][1]/n:.2f} | {a['c10']} -> {a['c11']} | {a['ex0']} -> {a['ex1']} | {a['lose']} |")
            wrong_rows.append((lvl, REPN * mult, nn, nA, sum(wrong.values()), dict(wrong)))
    pr()
    pr("Alerts of other causes (not stuck_at, not in the silent-fault set) whose true subtype leaves the set because of the channel:")
    pr("| level | rep_nat | other alerts | with A (identical) | true subtype removed | by (cause, subtype) |"); pr("|---|---|---|---|---|---|")
    for lvl, rn, nn, nA, tot, w in wrong_rows: pr(f"| {lvl} | {rn:.4f} | {nn} | {nA} | {tot} | {w if w else '-'} |")
    pr()
open(f"{common.ROOT}/out/silent_native.md", "w").write("\n".join(out))
print("\n".join(out))
