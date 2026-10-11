"""Split-conformal sets of subtypes (follow-up 10.3, 10.4)."""
import sys, math, json, pickle, collections
sys.path.insert(0, "/tmp/research/likelihood/scripts"); sys.path.insert(0, "/tmp/research/likelihood")
import numpy as np
import common, likelihood_attr as L, subtype_model as SM, pairlib as P
from setlib import kappa_set
from dataclasses import replace

REPN = json.load(open(f"{common.ROOT}/out/rep_nat_rounded.json"))["rep_nat"]
REF = L.Params()
SP_ACC = SM.SubParams(base=REF, design="uniform", rep=True, rep_nat=REPN, adr32=True, adr34=True)
SP_OLD = SM.SubParams(base=REF, design="uniform")           # the section-9 channels
METHODS = ["subtype model, accepted channels", "subtype model, section-9 channels", "class-level table (section 1)", "prior only"]
_memo = {}

def subtype_probs(rec, sp, key):
    ext = None
    if sp.adr32 or sp.rep or sp.base.ext:
        ext = dict(rec["ext"][10_000]); ext[SM.XREP] = rec["rep"][None]
    cls = SM.read_classes(rec["on"], rec["t"], sp, ext)
    k = (key, rec["t"], frozenset(cls.items()))
    r = _memo.get(k)
    if r is None:
        r = _memo[k] = SM.posterior_from_cls(cls, rec["t"], sp).sub_post
    return r

def class_probs(rec):
    k = ("cls", rec["t"], tuple(sorted(rec["on"].items())))
    r = _memo.get(k)
    if r is None:
        cp = L.posterior_from_readings(rec["on"], rec["t"], REF, None).posterior
        out = {}
        for comp, w in SM.applicable(rec["t"], "uniform", "fm"):
            s = SM.subtype_of(comp.name); out[s] = out.get(s, 0.0) + cp[comp.cause] * w
        r = _memo[k] = out
    return r

def prior_probs(rec):
    k = ("prior", rec["t"])
    r = _memo.get(k)
    if r is None:
        r = _memo[k] = SM.posterior_from_cls({}, rec["t"], SP_OLD).sub_post
    return r

def probs(rec, method):
    if method == METHODS[0]: return subtype_probs(rec, SP_ACC, "acc")
    if method == METHODS[1]: return subtype_probs(rec, SP_OLD, "old")
    if method == METHODS[2]: return class_probs(rec)
    return prior_probs(rec)

def rule_set(rec):
    return kappa_set(rec["old_on"], rec["t"], SP_OLD)

def qhat(scores, alpha):
    n = len(scores); k = math.ceil((n + 1) * (1 - alpha))
    return math.inf if k > n else float(sorted(scores)[k - 1])

class Cal:
    """thresholds of one method: marginal and Mondrian per template"""
    def __init__(self, cal_items, method, alpha):
        self.method, self.alpha = method, alpha
        sc = []; byt = collections.defaultdict(list)
        for it in cal_items:
            p = probs(it["alert"], method).get(it["sub"], 0.0); s = 1.0 - p
            sc.append(s); byt[it["alert"]["t"]].append(s)
        self.q = qhat(sc, alpha); self.n = len(sc)
        self.qt = {t: qhat(v, alpha) for t, v in byt.items()}; self.nt = {t: len(v) for t, v in byt.items()}
    def make_set(self, rec, mode, q_override=None):
        pr = probs(rec, self.method)
        q = self.q if mode == "marginal" else self.qt.get(rec["t"], math.inf)
        if q_override is not None: q = q_override
        return [s for s, p in pr.items() if 1.0 - p <= q + 1e-12]

def evaluate(items, cal, mode):
    """rows (patient, template, truth cause, truth sub, covered, size)"""
    rows = []
    for it in items:
        S = cal.make_set(it["alert"], mode)
        rows.append((it["patient"], it["alert"]["t"], it["truth"], it["sub"], it["sub"] in S, len(S)))
    return rows

def summarize(rows, B=1000, seed=0):
    n = len(rows)
    if n == 0: return None
    cov = sum(r[4] for r in rows); size = sum(r[5] for r in rows) / n
    lo, hi = P.wilson(cov, n)
    # cluster bootstrap over patients
    pats = collections.defaultdict(lambda: [0, 0])
    for r in rows: pats[r[0]][0] += r[4]; pats[r[0]][1] += 1
    keys = list(pats); a = np.array([pats[k][0] for k in keys], float); c = np.array([pats[k][1] for k in keys], float)
    rng = np.random.default_rng(seed); bs = []
    for _ in range(B):
        idx = rng.integers(0, len(keys), len(keys)); bs.append(a[idx].sum() / c[idx].sum())
    pp = a / c
    return dict(n=n, cov=cov, rate=cov / n, wlo=lo, whi=hi, size=size, blo=float(np.percentile(bs, 2.5)), bhi=float(np.percentile(bs, 97.5)),
                npat=len(keys), pat_med=float(np.median(pp)), pat_p10=float(np.percentile(pp, 10)), sizes=[r[5] for r in rows])

BINS = [(1, 1), (2, 2), (3, 3), (4, 4), (5, 6), (7, 9), (10, 99)]
def dist(sizes):
    n = len(sizes)
    return " / ".join(f"{100*sum(1 for s in sizes if a <= s <= b)/n:.0f}" for a, b in BINS)
def fm(s, cluster=True):
    if not s: return "-"
    t = f"{s['cov']}/{s['n']} = {100*s['rate']:.1f}% (W {100*s['wlo']:.0f}-{100*s['whi']:.0f}"
    t += f"; patients {100*s['blo']:.0f}-{100*s['bhi']:.0f})" if cluster else ")"
    return t + f", size {s['size']:.2f}"

def size_at_coverage(items, method, targets):
    """DESCRIPTIVE (not conformal): mean size of the marginal set at the smallest threshold whose coverage ON THE SAME ITEMS reaches the target."""
    sc = []; allp = []
    for it in items:
        pr = probs(it["alert"], method); sc.append(1.0 - pr.get(it["sub"], 0.0)); allp.append(sorted(1.0 - p for p in pr.values()))
    cand = sorted(set(sc))
    out = {}
    n = len(items)
    for tg in targets:
        for q in cand:
            cov = sum(1 for s in sc if s <= q + 1e-12) / n
            if cov >= tg:
                size = sum(sum(1 for v in a if v <= q + 1e-12) for a in allp) / n
                out[tg] = (cov, size); break
        else:
            out[tg] = (None, None)
    return out
