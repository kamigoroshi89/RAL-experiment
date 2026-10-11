"""Section 4: likelihood ratio between the two causes of each pair (prior-free), direction, McNemar between variants."""
import sys, collections, statistics, math
sys.path.insert(0, "/tmp/research/likelihood/scripts")
import pairlib as P, common, likelihood_attr as L

reg, tpl, cfg = common.load()
S = P.Scorer(reg)
rows = P.load("p40", 1)
for r in rows: P.match_pair(r)
REF = L.Params()
EPS0 = 1e-9

def lam_pair(r, variant, params=REF, tb=10_000, which="com"):
    """(Lambda_A, Lambda_B) = log P(e|c_A) - log P(e|c_B) for the two common-template alerts; None if not available."""
    if not r[which]["A"] or not r[which]["B"]: return None
    cA, cB = r["cause"]["A"], r["cause"]["B"]
    out = []
    for m in "AB":
        res = S.result(r[which][m], variant, params, tb, r[m])
        if res is None: return None
        out.append(res.llr(cA, cB))
    return tuple(out)

def pair_stats(variant, params=REF, tb=10_000, sel=lambda r: True, which="com"):
    st = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in rows:
        if not sel(r): continue
        lam = lam_pair(r, variant, params, tb, which)
        g = r["group"]; key = "indist" if r["flag"] else "dist"
        if lam is None:
            st[(g, key)]["none"].append(r["number"]); continue
        st[(g, key)]["lam"].append((r["number"], lam[0], lam[1], r))
    return st

def sgn(x): return 0 if abs(x) < EPS0 else (1 if x > 0 else -1)

def summarize(variant, params=REF, tb=10_000, which="com"):
    st = pair_stats(variant, params, tb, which=which)
    res = {}
    for (g, key), d in st.items():
        L_ = d["lam"]; n = len(L_)
        a = [x[1] for x in L_]; b = [x[2] for x in L_]; dd = [x[1] - x[2] for x in L_]
        res[(g, key)] = dict(n=n, nomatch=len(d["none"]),
            both=sum(1 for x in L_ if sgn(x[1]) > 0 and sgn(x[2]) < 0), A_ok=sum(1 for x in a if sgn(x) > 0), B_ok=sum(1 for x in b if sgn(x) < 0),
            A_zero=sum(1 for x in a if sgn(x) == 0), B_zero=sum(1 for x in b if sgn(x) == 0),
            Dpos=sum(1 for x in dd if sgn(x) > 0), Dzero=sum(1 for x in dd if sgn(x) == 0), Dneg=sum(1 for x in dd if sgn(x) < 0),
            A=a, B=b, D=dd, rows=L_)
    return res

def q(x, p):
    if not x: return float("nan")
    s = sorted(x); i = p * (len(s) - 1); lo = int(math.floor(i)); hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (i - lo)

def ci(k, n):
    lo, hi = P.wilson(k, n); return f"{k}/{n} ({100*k/n:.0f}%; {100*lo:.0f}-{100*hi:.0f})" if n else "0/0"

if __name__ == "__main__":
    out = []; pr = lambda *a: out.append(" ".join(str(x) for x in a))
    V0 = "V0 full (diag ON)"
    res = summarize(V0)
    pr(f"### 4.1 Pairs, primary variant {V0}, reference point {REF}")
    pr("Pairs with a common-template match in both members; Lambda = log P(e|c_A) - log P(e|c_B) in nats (prior-free); D = Lambda_A - Lambda_B.")
    pr("| group | stratum | pairs (matched/ all) | Lambda_A > 0 | Lambda_B < 0 | both (correct direction) | D > 0 | D = 0 | D < 0 | Lambda_A = 0 | Lambda_B = 0 |")
    pr("|---|---|---|---|---|---|---|---|---|---|---|")
    tot = collections.defaultdict(lambda: collections.Counter())
    nall = collections.Counter((r["group"], "indist" if r["flag"] else "dist") for r in rows)
    for g in P.GROUPS:
        for key in ("dist", "indist"):
            x = res.get((g, key))
            if not x: continue
            n = x["n"]
            pr(f"| {g} | {key} | {n} / {nall[(g,key)]} | {ci(x['A_ok'],n)} | {ci(x['B_ok'],n)} | {ci(x['both'],n)} | {ci(x['Dpos'],n)} | {x['Dzero']} | {x['Dneg']} | {x['A_zero']} | {x['B_zero']} |")
            for k in ("n","A_ok","B_ok","both","Dpos","Dzero","Dneg","A_zero","B_zero"): tot[key][k] += x[k]
    for key in ("dist", "indist"):
        t = tot[key]; n = t["n"]
        pr(f"| ALL | {key} | {n} | {ci(t['A_ok'],n)} | {ci(t['B_ok'],n)} | {ci(t['both'],n)} | {ci(t['Dpos'],n)} | {t['Dzero']} | {t['Dneg']} | {t['A_zero']} | {t['B_zero']} |")
    pr()
    pr("Pairs by stage (all pairs of the group / both events realised / common-template alert in both members):")
    pr("| group | stratum | pairs | both events realised | matched (primary template) | primary template |")
    pr("|---|---|---|---|---|---|")
    for g in P.GROUPS:
        for key in ("dist", "indist"):
            rs = [r for r in rows if r["group"] == g and (r["flag"] == (key == "indist"))]
            ts = collections.Counter(r["com_template"] for r in rs if r["com"]["A"])
            pr(f"| {g} | {key} | {len(rs)} | {sum(1 for r in rs if r['both_realised'])} | {sum(1 for r in rs if r['com']['A'])} | {dict(ts)} |")
    pr()
    pr("### 4.1b Same, evaluated on the alert of an alternative template (RESP of the extra opening for groups 1 and 4, where the witness fields are read; RESP for group 2; SCHED for group 3)")
    resb = summarize(V0, which="com_alt")
    pr("| group | stratum | pairs matched | both correct direction | D > 0 | D = 0 | D < 0 |")
    pr("|---|---|---|---|---|---|---|")
    for g in P.GROUPS:
        for key in ("dist", "indist"):
            x = resb.get((g, key))
            if not x: continue
            n = x["n"]
            pr(f"| {g} | {key} | {n} | {ci(x['both'],n)} | {ci(x['Dpos'],n)} | {x['Dzero']} | {x['Dneg']} |")
    pr()
    pr("### 4.2 Distribution of Lambda (nats) per group and stratum: min / q25 / median / q75 / max")
    pr("| group | stratum | member | min | q25 | median | q75 | max |")
    pr("|---|---|---|---|---|---|---|---|")
    for g in P.GROUPS:
        for key in ("dist", "indist"):
            x = res.get((g, key))
            if not x: continue
            for nm, v in (("A", x["A"]), ("B", x["B"]), ("D", x["D"])):
                pr(f"| {g} | {key} | {nm} | " + " | ".join(f"{q(v,p):.3f}" for p in (0, .25, .5, .75, 1)) + " |")
    pr()
    pr("### 4.3 Indistinguishable stratum: pairs with D != 0 (identical streams must give D = 0 except where the pressure differs)")
    for g in P.GROUPS:
        x = res.get((g, "indist"))
        if not x: continue
        bad = [(r["number"], r["variant"], la, lb, r["com_template"]) for (_, la, lb, r) in x["rows"] if abs(la - lb) > EPS0]
        pr(f"- {g}: {len(bad)} of {x['n']} matched indistinguishable pairs have D != 0" + (f"; first: {bad[:3]}" if bad else ""))
    pr()
    # by separating channel
    pr("### 4.4 Distinguishable pairs by separating channel set (separated_by of evaluate_pair): D > 0 rate")
    pr("| group | separated_by | pairs | D > 0 | D = 0 | D < 0 | mean D |")
    pr("|---|---|---|---|---|---|---|")
    bych = collections.defaultdict(list)
    for g in P.GROUPS:
        x = res.get((g, "dist"))
        if not x: continue
        for (_, la, lb, r) in x["rows"]: bych[(g, tuple(sorted(r["separated_by"])))].append(la - lb)
    for (g, sb), v in sorted(bych.items()):
        pr(f"| {g[:14]} | {','.join(sb)} | {len(v)} | {sum(1 for d in v if d>EPS0)} | {sum(1 for d in v if abs(d)<=EPS0)} | {sum(1 for d in v if d<-EPS0)} | {statistics.mean(v):.3f} |")
    pr()
    # McNemar between variants on D > 0, distinguishable pairs
    pr("### 4.5 McNemar between method variants on the indicator 'D > 0' (distinguishable pairs matched in both variants); exact binomial on the discordant pairs")
    pr("| group | variant X | variant Y | pairs | b (X right, Y not) | c (Y right, X not) | exact p |")
    pr("|---|---|---|---|---|---|---|")
    base = {k: {x[0]: (x[1] - x[2]) for x in v["rows"]} for k, v in res.items() if k[1] == "dist"}
    for Y in [v for v in P.VARIANTS if v != V0]:
        resY = summarize(Y)
        for g in P.GROUPS + ["ALL"]:
            b = c = n = 0
            for (gg, key), v in resY.items():
                if key != "dist" or (g != "ALL" and gg != g): continue
                dy = {x[0]: (x[1] - x[2]) for x in v["rows"]}
                for num, d0 in base.get((gg, key), {}).items():
                    if num not in dy: continue
                    n += 1
                    ok0 = d0 > EPS0; ok1 = dy[num] > EPS0
                    b += ok0 and not ok1; c += ok1 and not ok0
            pr(f"| {g[:14]} | {V0} | {Y} | {n} | {b} | {c} | {P.exact_binom_p(b, c):.3g} |")
    pr()
    # per variant summary
    pr("### 4.6 Summary of the variants (distinguishable stratum, all groups): both-correct-direction, D > 0; indistinguishable: D = 0")
    pr("| variant | dist pairs | both correct | D > 0 | D = 0 | D < 0 | indist pairs | indist D = 0 |")
    pr("|---|---|---|---|---|---|---|---|")
    for Y in P.VARIANTS:
        rY = summarize(Y)
        t = collections.Counter(); ti = collections.Counter()
        for (g, key), v in rY.items():
            tt = t if key == "dist" else ti
            for k in ("n","both","Dpos","Dzero","Dneg"): tt[k] += v[k]
        pr(f"| {Y} | {t['n']} | {ci(t['both'],t['n'])} | {ci(t['Dpos'],t['n'])} | {t['Dzero']} | {t['Dneg']} | {ti['n']} | {ti['Dzero']} |")
    open(f"{common.ROOT}/out/pairs_tables.md", "w").write("\n".join(out))
    print("\n".join(out))
