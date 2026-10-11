"""Section 3: rerun of the 1080 pairs (2160 members) with the likelihood table; old rule next to it."""
import sys, collections, json
sys.path.insert(0, "/tmp/research/likelihood/scripts")
import pairlib as P, common, likelihood_attr as L
from dataclasses import replace

TAUS = [0.5, 0.67, 0.8, 0.9, 0.95, 0.99]
REF = L.Params()          # reference point of the grid (eps .01, qc .5, uniform prior, fm family, uniform mixture, tau .8)
reg, tpl, cfg = common.load()
S = P.Scorer(reg)
rows = P.load("p40", 1)
for r in rows:
    P.match_pair(r)

def members():
    for r in rows:
        for m in "AB":
            yield r, m

def status(r, m):
    if r["rel"][m] is None: return "no_event"
    if r["own"][m] is None: return "no_alert"
    return "matched"

def table_for(sel, params=REF, variant="V0 full (diag ON)", tb=10_000):
    """counts over the members selected by sel(r, m)"""
    c = collections.Counter(); old = collections.Counter(); oldon = collections.Counter(); kp = {t: collections.Counter() for t in TAUS}
    n = 0
    for r, m in members():
        if not sel(r, m): continue
        n += 1
        st = status(r, m); c[st] += 1
        if st != "matched": continue
        a = r["own"][m]; truth = r["cause"][m]
        old[a["old_off"]] += 1; oldon[a["old_on"]] += 1
        res = S.result(a, variant, params, tb, r[m])
        c["argmax_ok"] += res.argmax() == truth
        c[f"argmax_{res.argmax()}"] += 1
        for t in TAUS:
            k = res.kappa(t)
            kp[t]["und" if k == "UNDETERMINED" else ("right" if k == truth else "wrong")] += 1
            if k == "C1": kp[t][f"C1_for_{truth}"] += 1
    return n, c, old, oldon, kp

def fmt_ci(k, n):
    lo, hi = P.wilson(k, n)
    return f"{k}/{n} ({100*k/n:.1f}%; {100*lo:.0f}-{100*hi:.0f})" if n else "0/0"

if __name__ == "__main__":
    out = []
    pr = lambda *a: out.append(" ".join(str(x) for x in a))
    pr("## 3.1 Per group, reference point", REF)
    pr("| group | members | event realised | alert matched | old rule (diag OFF) C1/C2/C3/UND | old rule (diag ON) C1/C2/C3/UND | argmax = truth | UNDET @.8 | confident right @.8 | confident wrong @.8 |")
    pr("|---|---|---|---|---|---|---|---|---|---|")
    tot = collections.Counter(); totold = collections.Counter(); totoldon = collections.Counter(); totkp = collections.Counter()
    for g in P.GROUPS:
        n, c, old, oldon, kp = table_for(lambda r, m, g=g: r["group"] == g)
        mt = c["matched"]; ev = n - c["no_event"]
        o = lambda d: "/".join(str(d.get(k, 0)) for k in ("C1", "C2", "C3", "UNDETERMINED"))
        pr(f"| {g} | {n} | {ev} | {mt} | {o(old)} | {o(oldon)} | {fmt_ci(c['argmax_ok'], mt)} | {kp[0.8]['und']} | {kp[0.8]['right']} | {kp[0.8]['wrong']} |")
        tot.update(c); totold.update(old); totoldon.update(oldon)
        for k, v in kp[0.8].items(): totkp[k] += v
    o = lambda d: "/".join(str(d.get(k, 0)) for k in ("C1", "C2", "C3", "UNDETERMINED"))
    pr(f"| ALL | 2160 | {2160-tot['no_event']} | {tot['matched']} | {o(totold)} | {o(totoldon)} | {fmt_ci(tot['argmax_ok'], tot['matched'])} | {totkp['und']} | {totkp['right']} | {totkp['wrong']} |")
    pr()
    pr("## 3.2 Per variant (27), reference point; members of the variant = 80")
    pr("| group | variant | matched | old C1 (OFF/ON) | argmax=truth | UND@.8 | right@.8 | wrong@.8 |")
    pr("|---|---|---|---|---|---|---|---|")
    vs = sorted({(r["group"], r["variant"]) for r in rows})
    for g, v in vs:
        n, c, old, oldon, kp = table_for(lambda r, m, g=g, v=v: r["group"] == g and r["variant"] == v)
        pr(f"| {g[:14]} | {v} | {c['matched']}/{n} | {old.get('C1',0)}/{oldon.get('C1',0)} | {c['argmax_ok']} | {kp[0.8]['und']} | {kp[0.8]['right']} | {kp[0.8]['wrong']} |")
    pr()
    pr("## 3.3 Threshold sweep (labelled sensitivity values), all matched members; by group")
    pr("| group | tau | UNDETERMINED | confident right | confident wrong | confident C1 for true C1 / C2 / C3 |")
    pr("|---|---|---|---|---|---|")
    for g in P.GROUPS + ["ALL"]:
        n, c, old, oldon, kp = table_for(lambda r, m, g=g: g == "ALL" or r["group"] == g)
        for t in TAUS:
            k = kp[t]
            pr(f"| {g[:14]} | {t} | {k['und']} | {k['right']} | {k['wrong']} | {k['C1_for_C1']}/{k['C1_for_C2']}/{k['C1_for_C3']} |")
    pr()
    # diagnostics emission: V0 vs V1, per truth cause
    pr("## 3.4 Effect of the diagnostics reports (profile with vs without), matched members, reference point")
    pr("| truth cause | n | V0 (diag ON) argmax right | V1 (no diag) argmax right | V0 conf. C1 @.8 | V1 conf. C1 @.8 | old rule C1 ON | old rule C1 OFF |")
    pr("|---|---|---|---|---|---|---|---|")
    mc = {"b": 0, "c": 0}
    for cause in ("C1", "C2", "C3"):
        n = ok0 = ok1 = c10 = c11 = o_on = o_off = 0
        for r, m in members():
            if status(r, m) != "matched" or r["cause"][m] != cause: continue
            a = r["own"][m]; n += 1
            x = S.result(a, "V0 full (diag ON)", REF, 10000, r[m]); y = S.result(a, "V1 full, no diagnostics", REF, 10000, r[m])
            ok0 += x.argmax() == cause; ok1 += y.argmax() == cause
            c10 += x.kappa(.8) == "C1"; c11 += y.kappa(.8) == "C1"
            o_on += a["old_on"] == "C1"; o_off += a["old_off"] == "C1"
            if (x.argmax() == cause) and not (y.argmax() == cause): mc["b"] += 1
            if (y.argmax() == cause) and not (x.argmax() == cause): mc["c"] += 1
        pr(f"| {cause} | {n} | {ok0} | {ok1} | {c10} | {c11} | {o_on} | {o_off} |")
    pr(f"McNemar V0 vs V1 on 'argmax = truth' (all matched members): b (V0 right, V1 not) = {mc['b']}, c = {mc['c']}, exact p = {P.exact_binom_p(mc['b'], mc['c']):.3g}")
    pr()
    # old vs new crosstab at reference point (diag ON), matched members
    pr("## 3.5 Old rule (diag ON) vs likelihood table (kappa @ .8), matched members")
    ct = collections.Counter(); ex = {}
    for r, m in members():
        if status(r, m) != "matched": continue
        a = r["own"][m]
        res = S.result(a, "V0 full (diag ON)", REF, 10000, r[m])
        key = (a["old_on"], res.kappa(.8))
        ct[key] += 1
        if key not in ex: ex[key] = (r["group"], r["variant"], r["number"], m, a["template"], res)
    pr("| old (diag ON) | new @.8 | n | example (group, variant, pair no., member, template, posterior) |")
    pr("|---|---|---|---|")
    for k, v in sorted(ct.items()):
        e = ex[k]
        pr(f"| {k[0]} | {k[1]} | {v} | {e[0][:14]} {e[1]} #{e[2]}{e[3]} {e[4]} {({c: round(x,3) for c, x in e[5].posterior.items()})} |")
    open(f"{common.ROOT}/out/recompute_tables.md", "w").write("\n".join(out))
    print("\n".join(out))
