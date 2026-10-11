"""Section 9.1: pairs at subtype level. Lambda = log P(e | subtype_A) - log P(e | subtype_B)."""
import sys, pickle, collections, statistics, math
sys.path.insert(0, "/tmp/research/likelihood/scripts"); sys.path.insert(0, "/tmp/research/likelihood")
import common, likelihood_attr as L, subtype_model as SM, pairlib as P
from dataclasses import replace

pairs, members = pickle.load(open(f"{common.ROOT}/out/sens2_pairs.pkl", "rb"))
EPS0 = 1e-9
WIT, VER = P.WIT, P.VER
VARS = {  # same variants as section 4
    "V0 full (diag ON)": ("on", frozenset(), False), "V1 full, no diagnostics": ("off", frozenset(), False),
    "V2 no witness": ("on", WIT, False), "V3 no verification": ("on", VER, False),
    "V4 no witness, no verif.": ("on", WIT | VER, False), "V5 + dispenser channels (ADR-032 proto)": ("on", frozenset(), True),
}
REFB = L.Params()

def lam(q, var, design="uniform", base=REFB, tb=10_000, which="com"):
    prof, mask, ext = VARS[var]
    sp = SM.SubParams(base=replace(base, mask=mask, ext=ext), design=design)
    out = []
    for m in ("A", "B"):
        rec = q[m]
        rd = rec[prof]
        if rd is None: return None
        e = rec["ext"][tb] if ext else None
        out.append(SM.subtype_loglik(q["sA"], rd, sp, e, rec["t"]) - SM.subtype_loglik(q["sB"], rd, sp, e, rec["t"]))
    return tuple(out)

def sgn(x): return 0 if abs(x) < EPS0 else (1 if x > 0 else -1)

def summarize(var, design="uniform", base=REFB, which="com"):
    res = collections.defaultdict(lambda: collections.defaultdict(list))
    for q in pairs:
        if q["which"] != which: continue
        l = lam(q, var, design, base)
        if l is None: continue
        res[(q["group"], "indist" if q["flag"] else "dist")]["lam"].append((q["number"], l[0], l[1]))
    return res

def q_(x, p):
    s = sorted(x); i = p * (len(s) - 1); lo = int(math.floor(i)); hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (i - lo)

def ci(k, n):
    lo, hi = P.wilson(k, n); return f"{k}/{n} ({100*k/n:.0f}%; {100*lo:.0f}-{100*hi:.0f})" if n else "0/0"

if __name__ == "__main__":
    out = []; pr = lambda *a: out.append(" ".join(str(x) for x in a))
    V0 = "V0 full (diag ON)"
    res = summarize(V0)
    pr("#### 9.1.1 Subtype level, variant V0, design uniform, reference point of the cells (eps .01, qc .5)")
    pr("Lambda = log P(e | subtype_A) - log P(e | subtype_B) at the alert of the common template; pairs, strata and matching as in section 4. Subtype pairs: g1 double_take against dispenser_bounce; g2 drug_nonresponse against dispense_forgery; g3 measurement_refusal against manipulation_failure; g4 dispenser_bounce against dispense_forgery.")
    pr("| group | stratum | pairs | Lambda_A > 0 | Lambda_B < 0 | both (correct direction) | D > 0 | D = 0 | D < 0 | median Lambda_A (nats) | median Lambda_B | class-level median Lambda_A (section 4.2) |")
    pr("|---|---|---|---|---|---|---|---|---|---|---|---|")
    classmed = {("double_take_vs_bounce", "dist"): 2.322, ("double_take_vs_bounce", "indist"): 2.322, ("nonresponse_vs_falsified_dispense", "dist"): 2.229,
                ("nonresponse_vs_falsified_dispense", "indist"): 0.872, ("refusal_vs_robot_missed", "dist"): 0.983, ("refusal_vs_robot_missed", "indist"): 0.763,
                ("bounce_vs_forged_dispense", "dist"): -0.843, ("bounce_vs_forged_dispense", "indist"): -1.922}
    tot = collections.defaultdict(collections.Counter)
    for g in P.GROUPS:
        for key in ("dist", "indist"):
            L_ = res.get((g, key), {}).get("lam", [])
            if not L_: continue
            a = [x[1] for x in L_]; b = [x[2] for x in L_]; n = len(L_)
            c = collections.Counter()
            for _, la, lb in L_:
                c["Apos"] += sgn(la) > 0; c["Bneg"] += sgn(lb) < 0; c["both"] += (sgn(la) > 0 and sgn(lb) < 0)
                d = la - lb; c["Dpos"] += sgn(d) > 0; c["Dzero"] += sgn(d) == 0; c["Dneg"] += sgn(d) < 0
            for k, v in c.items(): tot[key][k] += v
            tot[key]["n"] += n
            pr(f"| {g} | {key} | {n} | {ci(c['Apos'],n)} | {ci(c['Bneg'],n)} | {ci(c['both'],n)} | {ci(c['Dpos'],n)} | {c['Dzero']} | {c['Dneg']} | {statistics.median(a):.3f} | {statistics.median(b):.3f} | {classmed[(g,key)]} |")
    for key in ("dist", "indist"):
        t = tot[key]; n = t["n"]
        pr(f"| ALL | {key} | {n} | {ci(t['Apos'],n)} | {ci(t['Bneg'],n)} | {ci(t['both'],n)} | {ci(t['Dpos'],n)} | {t['Dzero']} | {t['Dneg']} | | | |")
    pr()
    pr("In the indistinguishable stratum D = 0 exactly in all pairs, as for classes; the lean (Lambda of an identical stream) is now between the two actual subtypes and is much smaller than the class-level lean, because the mixture over the loud sub-causes of the class is gone.")
    pr()
    # distribution of Lambda
    pr("#### 9.1.2 Distribution of Lambda (nats), subtype level, V0: min / q25 / median / q75 / max")
    pr("| group | stratum | member | min | q25 | median | q75 | max |"); pr("|---|---|---|---|---|---|---|---|")
    for g in P.GROUPS:
        for key in ("dist", "indist"):
            L_ = res.get((g, key), {}).get("lam", [])
            if not L_: continue
            for nm, v in (("A", [x[1] for x in L_]), ("B", [x[2] for x in L_]), ("D", [x[1] - x[2] for x in L_])):
                pr(f"| {g} | {key} | {nm} | " + " | ".join(f"{q_(v,p):.3f}" for p in (0, .25, .5, .75, 1)) + " |")
    pr()
    # by separating channel
    pr("#### 9.1.3 Distinguishable pairs by separating channel set: D > 0 rate, subtype level (V0)")
    pr("| group | separated_by | pairs | D > 0 | D = 0 | D < 0 | mean D |"); pr("|---|---|---|---|---|---|---|")
    by = collections.defaultdict(list)
    for q in pairs:
        if q["which"] != "com" or q["flag"]: continue
        l = lam(q, V0)
        if l is None: continue
        by[(q["group"], q["sep"])].append(l[0] - l[1])
    for (g, sb), v in sorted(by.items()):
        pr(f"| {g[:14]} | {','.join(sb)} | {len(v)} | {sum(1 for d in v if d>EPS0)} | {sum(1 for d in v if abs(d)<=EPS0)} | {sum(1 for d in v if d<-EPS0)} | {statistics.mean(v):.3f} |")
    pr()
    # McNemar
    pr("#### 9.1.4 McNemar between method variants, subtype level, on 'D > 0' (distinguishable pairs matched in both); exact binomial on the discordant pairs")
    pr("| group | variant X | variant Y | pairs | b (X right, Y not) | c (Y right, X not) | exact p |"); pr("|---|---|---|---|---|---|---|")
    base = {k: {x[0]: x[1] - x[2] for x in v["lam"]} for k, v in res.items() if k[1] == "dist"}
    summ = {}
    for Y in [v for v in VARS if v != V0]:
        resY = summarize(Y)
        for g in P.GROUPS + ["ALL"]:
            b = c = n = 0
            for (gg, key), v in resY.items():
                if key != "dist" or (g != "ALL" and gg != g): continue
                dy = {x[0]: x[1] - x[2] for x in v["lam"]}
                for num, d0 in base.get((gg, key), {}).items():
                    if num not in dy: continue
                    n += 1; ok0 = d0 > EPS0; ok1 = dy[num] > EPS0
                    b += ok0 and not ok1; c += ok1 and not ok0
            pr(f"| {g[:14]} | {V0} | {Y} | {n} | {b} | {c} | {P.exact_binom_p(b, c):.3g} |")
    pr()
    pr("#### 9.1.5 Summary of the variants at subtype level (distinguishable stratum, all groups) next to the class level of section 4.6")
    cls46 = {"V0 full (diag ON)": "257/613 (42%)", "V1 full, no diagnostics": "257/613 (42%)", "V2 no witness": "243/613 (40%)", "V3 no verification": "157/613 (26%)",
             "V4 no witness, no verif.": "124/613 (20%)", "V5 + dispenser channels (ADR-032 proto)": "538/613 (88%)"}
    pr("| variant | dist pairs | D > 0 (subtype) | both correct (subtype) | D > 0 by group g1/g2/g3/g4 (subtype) | D > 0 (class level, 4.6) | indist D = 0 |"); pr("|---|---|---|---|---|---|---|")
    for Y in VARS:
        rY = summarize(Y)
        n = dp = bo = 0; per = []; iz = ni = 0
        for g in P.GROUPS:
            L_ = rY.get((g, "dist"), {}).get("lam", [])
            per.append(f"{sum(1 for x in L_ if x[1]-x[2] > EPS0)}/{len(L_)}")
            n += len(L_); dp += sum(1 for x in L_ if x[1]-x[2] > EPS0); bo += sum(1 for x in L_ if x[1] > EPS0 and x[2] < -EPS0)
            Li = rY.get((g, "indist"), {}).get("lam", []); ni += len(Li); iz += sum(1 for x in Li if abs(x[1]-x[2]) <= EPS0)
        pr(f"| {Y} | {n} | {ci(dp,n)} | {ci(bo,n)} | {' / '.join(per)} | {cls46[Y]} | {iz}/{ni} |")
    pr()
    # design sensitivity
    pr("#### 9.1.6 Sensitivity to the within-class prior pi(subtype | class) (config/subtype_priors.yaml): Lambda and D at subtype level, V0 and V5")
    pr("Only the level split inside dispense_forgery enters Lambda (naive against informed: the other subtypes have one component), so the design moves the pairs of groups 2 and 4 only.")
    pr("| design | status | variant | D > 0 g1/g2/g3/g4 | median Lambda_A, indist g1/g2/g3/g4 | both correct (all dist) |"); pr("|---|---|---|---|---|---|")
    cfg = SM.load_config()
    for dname, d in cfg["designs"].items():
        for var in (V0, "V5 + dispenser channels (ADR-032 proto)"):
            rY = summarize(var, dname)
            per = []; med = []; bo = n = 0
            for g in P.GROUPS:
                L_ = rY.get((g, "dist"), {}).get("lam", []); per.append(f"{sum(1 for x in L_ if x[1]-x[2] > EPS0)/len(L_):.2f}")
                bo += sum(1 for x in L_ if x[1] > EPS0 and x[2] < -EPS0); n += len(L_)
                Li = rY.get((g, "indist"), {}).get("lam", []); med.append(f"{statistics.median([x[1] for x in Li]):.2f}" if Li else "-")
            pr(f"| {dname} | {d['status']} | {var[:2]} | {' / '.join(per)} | {' / '.join(med)} | {bo}/{n} |")
    pr()
    pr("Sensitivity to eps and qc (design uniform, V0): D > 0 and median Lambda_A of the indistinguishable stratum")
    pr("| eps | qc | D > 0 g1/g2/g3/g4 | median Lambda_A indist g1/g2/g3/g4 |"); pr("|---|---|---|---|")
    for e in (0.001, 0.01, 0.05, 0.1):
        for qc in (0.25, 0.5, 0.75):
            rY = summarize(V0, "uniform", replace(REFB, eps=e, qc=qc))
            per = []; med = []
            for g in P.GROUPS:
                L_ = rY.get((g, "dist"), {}).get("lam", []); per.append(f"{sum(1 for x in L_ if x[1]-x[2] > EPS0)/len(L_):.2f}")
                Li = rY.get((g, "indist"), {}).get("lam", []); med.append(f"{statistics.median([x[1] for x in Li]):.2f}")
            pr(f"| {e} | {qc} | {' / '.join(per)} | {' / '.join(med)} |")
    open(f"{common.ROOT}/out/pairs_subtype.md", "w").write("\n".join(out))
    print("\n".join(out))
