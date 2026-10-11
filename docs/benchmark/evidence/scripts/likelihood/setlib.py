"""Set outputs at subtype level for matched alerts, and the old-kappa / class-kappa results expressed as sets."""
import sys, pickle, collections, math
sys.path.insert(0, "/tmp/research/likelihood/scripts"); sys.path.insert(0, "/tmp/research/likelihood")
import common, likelihood_attr as L, subtype_model as SM, pairlib as P
from dataclasses import replace

REF = L.Params()
REP_NAT = {None: 0.0, 1.0: 0.0200, 2.0: 0.0388, 5.0: 0.0980}   # section 9.3 (fault-free Delta, E[max(0,1-|Delta|/r)])
EPS0 = 1e-12

def load_pairs():
    return pickle.load(open(f"{common.ROOT}/out/sens2_pairs.pkl", "rb"))

def load_main(scoped=False):
    name = scoped if isinstance(scoped, str) else ('scoped' if scoped else 'unscoped')
    return pickle.load(open(f"{common.ROOT}/out/sens2_main_{name}.pkl", "rb"))

def sub_result(rec, sp, prof="on", tb=10_000, r=None):
    rd = rec[prof]
    if rd is None: return None
    ext = dict(rec["ext"][tb]) if sp.base.ext else {}
    if sp.rep:
        ext[SM.XREP] = rec["rep"][r]
    return SM.posterior(rd, rec["t"], sp, ext)

def sp_of(design="uniform", level=0.9, rep=False, r=None, base=REF, **kw):
    return SM.SubParams(base=base, design=design, level=level, rep=rep, rep_nat=REP_NAT[r], **kw)

def kappa_set(kappa, t, sp):
    """a definite class kappa as the set of the subtypes of that class applicable at t; UNDETERMINED as the full set"""
    if kappa == "UNDETERMINED":
        return SM.full_set(t, sp)
    return SM.class_subtypes(t, kappa, sp)

def class_kappa(rec, base=REF, prof="on", tau=0.8):
    res = L.posterior_from_readings(rec[prof], rec["t"], base, None)
    return res.kappa(tau)

def stats(rows):
    """rows: list of (covered, size, nclasses, has_C1, exact)"""
    n = len(rows)
    if not n: return None
    return dict(n=n, cov=sum(r[0] for r in rows), size=sum(r[1] for r in rows) / n, ncls=sum(r[2] for r in rows) / n)

def fmt(s):
    if not s: return "-"
    lo, hi = P.wilson(s["cov"], s["n"])
    return f"{s['cov']}/{s['n']} ({100*s['cov']/s['n']:.0f}%; {100*lo:.0f}-{100*hi:.0f}) size {s['size']:.2f}"
