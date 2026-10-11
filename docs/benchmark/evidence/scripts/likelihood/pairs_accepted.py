"""Section 10.2: pairs at subtype level with the accepted channel set (ADR-032, ADR-034, repeated value), rounded generator (p40r)."""
import sys, pickle, collections, statistics, math, json
sys.path.insert(0, "/tmp/research/likelihood/scripts"); sys.path.insert(0, "/tmp/research/likelihood")
import common, likelihood_attr as L, subtype_model as SM, pairlib as P
from dataclasses import replace
REPN = json.load(open(f"{common.ROOT}/out/rep_nat_rounded.json"))["rep_nat"]
members, pairs = pickle.load(open(f"{common.ROOT}/out/sens3_pairs_p40r.pkl", "rb"))
EPS0 = 1e-9; WIT, VER = P.WIT, P.VER; REF = L.Params()
def spx(design="uniform", mask=frozenset(), a32=False, a34=False, rep=False, base=REF, rn=REPN):
    return SM.SubParams(base=replace(base, mask=mask), design=design, rep=rep, rep_nat=rn, adr32=a32, adr34=a34)
VARS = {
  "V0 (section-4 channels)":         ("on", spx()),
  "+ ADR-032 only":                  ("on", spx(a32=True)),
  "+ ADR-034 only":                  ("on", spx(a34=True)),
  "+ repeated value only":           ("on", spx(rep=True)),
  "ACC (V0 + ADR-032 + ADR-034 + repeated value)": ("on", spx(a32=True, a34=True, rep=True)),
  "ACC, no witness":                 ("on", spx(mask=WIT, a32=True, a34=True, rep=True)),
  "ACC, no verification":            ("on", spx(mask=VER, a32=True, a34=True, rep=True)),
  "ACC, no witness, no verification": ("on", spx(mask=WIT | VER, a32=True, a34=True, rep=True)),
  "ACC, profile without diagnostics": ("off", spx(a32=True, a34=True, rep=True)),
  "ACC without ADR-032":             ("on", spx(a34=True, rep=True)),
  "ACC without ADR-034":             ("on", spx(a32=True, rep=True)),
  "ACC without repeated value":      ("on", spx(a32=True, a34=True)),
}
ACC = "ACC (V0 + ADR-032 + ADR-034 + repeated value)"
def ext_of(rec, tb=10_000):
    e = dict(rec["ext"][tb]); e[SM.XREP] = rec["rep"][None]; return e
def lam(q, name, tb=10_000, sp=None, prof=None):
    pf, s = VARS[name] if sp is None else (prof, sp)
    out = []
    for m in ("A", "B"):
        rec = q[m]; rd = rec[pf]
        if rd is None: return None
        e = ext_of(rec, tb)
        out.append(SM.subtype_loglik(q["sA"], rd, s, e, rec["t"]) - SM.subtype_loglik(q["sB"], rd, s, e, rec["t"]))
    return tuple(out)
def sgn(x): return 0 if abs(x) < EPS0 else (1 if x > 0 else -1)
def summarize(name=None, tb=10_000, sp=None, prof=None):
    res = collections.defaultdict(list)
    for q in pairs:
        l = lam(q, name, tb, sp, prof) if sp is None else lam(q, None, tb, sp, prof)
        if l is None: continue
        res[(q["group"], "indist" if q["flag"] else "dist")].append((q["number"], l[0], l[1], q))
    return res
def q_(x, p):
    s = sorted(x); i = p * (len(s) - 1); lo = int(math.floor(i)); hi = min(lo + 1, len(s) - 1); return s[lo] + (s[hi] - s[lo]) * (i - lo)
def ci(k, n):
    lo, hi = P.wilson(k, n); return f"{k}/{n} ({100*k/n:.0f}%; {100*lo:.0f}-{100*hi:.0f})" if n else "0/0"
out = []; pr = lambda *a: out.append(" ".join(str(x) for x in a))
res = summarize(ACC)
pr("#### 10.2.1 Pairs at subtype level with the accepted channel set (ACC), rounded generator, design uniform, reference cells (eps .01, qc .5), T_b 10 s, rep_nat = the measured %.4f" % REPN)
pr("Lambda = log P(e | subtype_A) - log P(e | subtype_B) at the alert of the common template; subtype pairs as in 9.1. The alert lists of the rounded build differ slightly from the unrounded one (10.1.2), so the pair counts differ slightly from section 9.")
pr("| group | stratum | pairs | Lambda_A > 0 | Lambda_B < 0 | both (correct direction) | D > 0 | D = 0 | D < 0 | median Lambda_A | median Lambda_B | 9.1.1 (section-4 channels) median Lambda_A |"); pr("|---|---|---|---|---|---|---|---|---|---|---|---|")
v0 = summarize("V0 (section-4 channels)")
tot = collections.defaultdict(collections.Counter)
for g in P.GROUPS:
    for key in ("dist", "indist"):
        L_ = res.get((g, key), [])
        if not L_: continue
        n = len(L_); c = collections.Counter()
        for _, la, lb, _ in L_:
            c["Apos"] += sgn(la) > 0; c["Bneg"] += sgn(lb) < 0; c["both"] += sgn(la) > 0 and sgn(lb) < 0
            d = la - lb; c["Dpos"] += sgn(d) > 0; c["Dzero"] += sgn(d) == 0; c["Dneg"] += sgn(d) < 0
        for k, v in c.items(): tot[key][k] += v
        tot[key]["n"] += n
        m0 = statistics.median([x[1] for x in v0[(g, key)]])
        pr(f"| {g} | {key} | {n} | {ci(c['Apos'],n)} | {ci(c['Bneg'],n)} | {ci(c['both'],n)} | {ci(c['Dpos'],n)} | {c['Dzero']} | {c['Dneg']} | {statistics.median([x[1] for x in L_]):.3f} | {statistics.median([x[2] for x in L_]):.3f} | {m0:.3f} |")
for key in ("dist", "indist"):
    t = tot[key]; n = t["n"]
    pr(f"| ALL | {key} | {n} | {ci(t['Apos'],n)} | {ci(t['Bneg'],n)} | {ci(t['both'],n)} | {ci(t['Dpos'],n)} | {t['Dzero']} | {t['Dneg']} | | | |")
pr()
pr("#### 10.2.2 Distribution of Lambda (nats), ACC: min / q25 / median / q75 / max")
pr("| group | stratum | member | min | q25 | median | q75 | max |"); pr("|---|---|---|---|---|---|---|---|")
for g in P.GROUPS:
    for key in ("dist", "indist"):
        L_ = res.get((g, key), [])
        if not L_: continue
        for nm, v in (("A", [x[1] for x in L_]), ("B", [x[2] for x in L_]), ("D", [x[1] - x[2] for x in L_])):
            pr(f"| {g} | {key} | {nm} | " + " | ".join(f"{q_(v,p):.3f}" for p in (0, .25, .5, .75, 1)) + " |")
pr()
pr("#### 10.2.3 Distinguishable pairs by separating channel set: D > 0, ACC")
pr("| group | separated_by | pairs | D > 0 | D = 0 | D < 0 | mean D |"); pr("|---|---|---|---|---|---|---|")
by = collections.defaultdict(list)
for key in ("dist",):
    for g in P.GROUPS:
        for num, la, lb, q in res.get((g, key), []): by[(g, q["sep"])].append(la - lb)
for (g, sb), v in sorted(by.items()):
    pr(f"| {g[:14]} | {','.join(sb)} | {len(v)} | {sum(1 for d in v if d>EPS0)} | {sum(1 for d in v if abs(d)<=EPS0)} | {sum(1 for d in v if d<-EPS0)} | {statistics.mean(v):.3f} |")
pr()
pr("#### 10.2.4 McNemar on 'D > 0' (distinguishable pairs matched in both variants), ACC against each other variant; exact binomial on the discordant pairs")
pr("| group | variant X | variant Y | pairs | b (X right, Y not) | c (Y right, X not) | exact p |"); pr("|---|---|---|---|---|---|---|")
base = {k: {x[0]: x[1] - x[2] for x in v} for k, v in res.items() if k[1] == "dist"}
for Y in [v for v in VARS if v != ACC]:
    resY = summarize(Y)
    for g in P.GROUPS + ["ALL"]:
        b = c = n = 0
        for (gg, key), v in resY.items():
            if key != "dist" or (g != "ALL" and gg != g): continue
            dy = {x[0]: x[1] - x[2] for x in v}
            for num, d0 in base.get((gg, key), {}).items():
                if num not in dy: continue
                n += 1; ok0 = d0 > EPS0; ok1 = dy[num] > EPS0; b += ok0 and not ok1; c += ok1 and not ok0
        if g == "ALL" or b or c: pr(f"| {g[:14]} | ACC | {Y} | {n} | {b} | {c} | {P.exact_binom_p(b, c):.3g} |")
pr("(rows with no discordant pair are printed for ALL only)")
pr()
pr("#### 10.2.5 Variants side by side (distinguishable stratum, all groups)")
pr("| variant | dist pairs | D > 0 | both correct | D > 0 by group g1/g2/g3/g4 | indist D = 0 | median Lambda_A, indist g1/g2/g3/g4 |"); pr("|---|---|---|---|---|---|---|")
for Y in VARS:
    rY = summarize(Y); n = dp = bo = iz = ni = 0; per = []; med = []
    for g in P.GROUPS:
        L_ = rY.get((g, "dist"), []); per.append(f"{sum(1 for x in L_ if x[1]-x[2] > EPS0)}/{len(L_)}")
        n += len(L_); dp += sum(1 for x in L_ if x[1]-x[2] > EPS0); bo += sum(1 for x in L_ if x[1] > EPS0 and x[2] < -EPS0)
        Li = rY.get((g, "indist"), []); ni += len(Li); iz += sum(1 for x in Li if abs(x[1]-x[2]) <= EPS0); med.append(f"{statistics.median([x[1] for x in Li]):.2f}" if Li else "-")
    pr(f"| {Y} | {n} | {ci(dp,n)} | {ci(bo,n)} | {' / '.join(per)} | {iz}/{ni} | {' / '.join(med)} |")
pr()
pr("#### 10.2.6 Sensitivity of ACC: T_b, within-class design, eps and qc, rep_nat")
pr("| setting | value | D > 0 g1/g2/g3/g4 | both correct (all dist) | median Lambda_A indist g1/g2/g3/g4 |"); pr("|---|---|---|---|---|")
def row(label, val, **kw):
    tb = kw.pop("tb", 10_000)
    sp = spx(a32=True, a34=True, rep=True, **kw)
    rY = summarize(None, tb, sp, "on"); per = []; med = []; bo = n = 0
    for g in P.GROUPS:
        L_ = rY.get((g, "dist"), []); per.append(f"{sum(1 for x in L_ if x[1]-x[2] > EPS0)/len(L_):.2f}")
        bo += sum(1 for x in L_ if x[1] > EPS0 and x[2] < -EPS0); n += len(L_)
        Li = rY.get((g, "indist"), []); med.append(f"{statistics.median([x[1] for x in Li]):.2f}")
    pr(f"| {label} | {val} | {' / '.join(per)} | {bo}/{n} | {' / '.join(med)} |")
for tb in (1_000, 10_000, 30_000, 60_000, 180_000): row("T_b", f"{tb/1000:g} s", tb=tb)
for d in SM.load_config()["designs"]: row("design", d, design=d)
for e in (0.001, 0.01, 0.05, 0.1):
    for qc in (0.25, 0.5, 0.75): row("eps, qc", f"{e}, {qc}", base=replace(REF, eps=e, qc=qc))
for m in (0.5, 1, 2): row("rep_nat", f"{REPN*m:.4f}", rn=REPN * m)
open(f"{common.ROOT}/out/pairs_accepted.md", "w").write("\n".join(out))
print("\n".join(out))
