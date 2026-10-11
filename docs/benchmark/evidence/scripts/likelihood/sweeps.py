"""Section 6: sensitivity of the headline quantities to eps, qc, priors, mixtures, threshold, grouping, divert share."""
import sys, pickle, math, itertools, collections, json
sys.path.insert(0, "/tmp/research/likelihood/scripts"); sys.path.insert(0, "/tmp/research/likelihood")
import common, likelihood_attr as L, pairlib as P
from dataclasses import replace
from multiprocessing import Pool

pairs, members = pickle.load(open(f"{common.ROOT}/out/sens_pairs.pkl", "rb"))
main_inj = pickle.load(open(f"{common.ROOT}/out/sens_main_m120_injected.pkl", "rb"))
main_str = pickle.load(open(f"{common.ROOT}/out/sens_main_m120_strict.pkl", "rb"))
main_rich = pickle.load(open(f"{common.ROOT}/out/sens_main_r40_injected.pkl", "rb"))
REF = L.Params()
WIT = P.WIT; VER = P.VER
CL = ("C1", "C2", "C3")
EPS0 = 1e-9
SILENT = {"stuck_at", "cuff_silent_bias", "dispenser_bounce"}

def post(rec, p, prof="on", tb=10_000):
    rd = rec[prof]
    if rd is None: return None
    return L.posterior_from_readings(rd, rec["t"], p, rec["ext"][tb] if p.ext else None)

def pair_metrics(p, prof="on", tb=10_000, which="com"):
    out = collections.defaultdict(lambda: [0, 0, 0, 0.0, 0])  # n, Dpos, both, sumLambdaA, LambdaA>0
    for q in pairs:
        if q["which"] != which: continue
        ra = post(q["A"], p, prof, tb); rb = post(q["B"], p, prof, tb)
        if ra is None or rb is None: continue
        la = ra.llr(q["cA"], q["cB"]); lb = rb.llr(q["cA"], q["cB"])
        key = (q["group"], "indist" if q["flag"] else "dist")
        x = out[key]; x[0] += 1; x[1] += (la - lb) > EPS0; x[2] += (la > EPS0 and lb < -EPS0); x[3] += la; x[4] += la > EPS0
    return out

def member_metrics(p, prof="on", tb=10_000):
    c = collections.Counter()
    for m in members:
        r = post(m["alert"], p, prof, tb)
        if r is None: continue
        truth = m["truth"]; k = r.kappa(p.tau)
        c["n"] += 1; c["argmax_ok"] += r.argmax() == truth
        c["und"] += k == "UNDETERMINED"; c["right"] += k == truth; c["wrong"] += (k != truth and k != "UNDETERMINED")
        c["conf_C1_not_C1"] += (k == "C1" and truth != "C1")
        c["conf_C1_true"] += (k == "C1" and truth == "C1")
        if m["sub"] == "dispenser_bounce":
            c["bounce_n"] += 1; c["bounce_conf_C1"] += k == "C1"; c["bounce_argmax_C1"] += r.argmax() == "C1"
    return c

def main_metrics(p, items=None, prof="on"):
    items = main_inj if items is None else items
    ls = br = 0.0; n = 0
    sil = collections.Counter(); percls = collections.defaultdict(lambda: [0, 0.0, 0.0])
    for it in items:
        r = post(it["alert"], p, prof)
        if r is None: continue
        pt = max(r.posterior[it["truth"]], 1e-12)
        l = -math.log(pt); b = sum((r.posterior[c] - (c == it["truth"])) ** 2 for c in CL)
        ls += l; br += b; n += 1
        x = percls[it["alert"]["t"]]; x[0] += 1; x[1] += l; x[2] += b
        if it["truth"] == "C2" and it["sub"] in SILENT:
            sil["n"] += 1; k = r.kappa(p.tau); sil["conf_C1"] += k == "C1"; sil["argmax_C1"] += r.argmax() == "C1"; sil["und"] += k == "UNDETERMINED"
    return dict(n=n, log=ls / n, brier=br / n, sil=sil, per={t: (v[1] / v[0], v[2] / v[0], v[0]) for t, v in percls.items()})

def headline(p, prof="on", tb=10_000):
    pm = pair_metrics(p, prof, tb)
    dist = [v for k, v in pm.items() if k[1] == "dist"]; ind = [v for k, v in pm.items() if k[1] == "indist"]
    nd = sum(v[0] for v in dist); dp = sum(v[1] for v in dist); bo = sum(v[2] for v in dist)
    perg = {k[0]: (v[1] / v[0] if v[0] else float("nan")) for k, v in pm.items() if k[1] == "dist"}
    leanA = {k[0]: (v[3] / v[0] if v[0] else float("nan")) for k, v in pm.items() if k[1] == "indist"}
    mm = member_metrics(p, prof, tb); mn = main_metrics(p, prof=prof)
    return dict(pairs_dist_n=nd, D_pos=dp, both=bo, D_pos_by_group=perg, indist_meanLambdaA=leanA,
                argmax_ok=mm["argmax_ok"], n_members=mm["n"], und=mm["und"], right=mm["right"], wrong=mm["wrong"],
                conf_C1_not_C1=mm["conf_C1_not_C1"], bounce_conf_C1=mm["bounce_conf_C1"], bounce_n=mm["bounce_n"], bounce_argmax_C1=mm["bounce_argmax_C1"],
                main_log=mn["log"], main_brier=mn["brier"], main_n=mn["n"], sil_n=mn["sil"]["n"], sil_conf_C1=mn["sil"]["conf_C1"], sil_argmax_C1=mn["sil"]["argmax_C1"],
                main_per=mn["per"])

def _w(p):
    return p, headline(p)

if __name__ == "__main__":
    out = {}
    grid = {
        "eps": [0.001, 0.01, 0.05, 0.1], "qc": [0.25, 0.5, 0.75],
        "prior": ["uniform", "c1_heavy", "c2_heavy", "c3_rare", "c3_heavy"],
        "family": ["fm", "v1"], "silent_share": [None, 0.05, 0.25, 0.5, 0.75],
        "informed_share": [None, 0.25, 0.75], "divert": [0.0, 0.1, 0.25],
        "group": ["none", "g1", "g2"], "scope": ["template", "all"], "tau": [0.5, 0.67, 0.8, 0.9, 0.95, 0.99],
    }
    one = []
    for k, vals in grid.items():
        for v in vals:
            one.append((k, v, replace(REF, **{k: v})))
    with Pool(26) as pool:
        res = pool.map(_w, [x[2] for x in one])
    out["one_at_a_time"] = [(k, v, r[1]) for (k, v, _), r in zip(one, res)]
    # variants: masks and profile
    var = []
    for name, kw in (("no_witness", dict(mask=WIT)), ("no_verification", dict(mask=VER)), ("neither", dict(mask=WIT | VER))):
        var.append((name, replace(REF, **kw), "on"))
    var.append(("no_diagnostics_profile", REF, "off"))
    out["variants"] = [(n, headline(p, prof)) for n, p, prof in var]
    # factorial
    combos = [replace(REF, eps=e, qc=q, prior=pr, silent_share=s, group=g)
              for e, q, pr, s, g in itertools.product(grid["eps"], grid["qc"], grid["prior"], grid["silent_share"], grid["group"])]
    with Pool(26) as pool:
        fres = pool.map(_w, combos, chunksize=8)
    out["factorial"] = [(p, h) for p, h in fres]
    pickle.dump(out, open(f"{common.ROOT}/out/sweeps.pkl", "wb"))
    print("done", len(one), len(combos))
