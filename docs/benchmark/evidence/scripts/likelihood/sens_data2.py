"""Section 9 data: reading classes of every matched alert plus the extension channels and the XREP channel at several resolutions."""
import sys, pickle
sys.path.insert(0, "/tmp/research/likelihood/scripts"); sys.path.insert(0, "/tmp/research/likelihood")
import pairlib as P, mainlib as M, common, likelihood_attr as L
import sens_data as S
RS = [None, 1.0, 2.0, 5.0]       # display resolution of the cuff in mmHg (None: the generator's float values)
XREP = "cuff.identical_repeat"

def xrep(mem, a, r):
    """A: the last two cuff readings received by the decision time are identical (after rounding to r mmHg), D: they differ, U: fewer than two."""
    s = sorted([x for x in (mem.get("bp_prev") or []) + (mem.get("bp") or []) if x[0] <= a["decided"]], key=lambda x: x[0])
    if len(s) < 2: return "U"
    v1, v2 = s[-2][1], s[-1][1]
    if r:
        v1, v2 = round(v1 / r) * r, round(v2 / r) * r
    return "A" if abs(v1 - v2) < 1e-9 else "D"

def alert_rec(a, mem):
    rec = S.alert_rec(a, mem)
    rec["rep"] = {r: xrep(mem, a, r) for r in RS}
    rec["decided"] = a["decided"]
    return rec

def build_pairs():
    rows = P.load("p40b", 1)
    pairs, members = [], []
    for r in rows:
        P.match_pair(r)
        for m in "AB":
            if r["own"][m]:
                members.append(dict(group=r["group"], variant=r["variant"], number=r["number"], member=m, truth=r["cause"][m],
                                    sub=r["rel"][m]["subtype"], flag=r["flag"], alert=alert_rec(r["own"][m], r[m])))
        for which in ("com", "com_alt"):
            if r[which]["A"] and r[which]["B"]:
                pairs.append(dict(which=which, group=r["group"], variant=r["variant"], number=r["number"], flag=r["flag"],
                                  sep=tuple(sorted(r["separated_by"])), cA=r["cause"]["A"], cB=r["cause"]["B"],
                                  sA=P.MECH[r["group"]][0][1], sB=P.MECH[r["group"]][1][1],
                                  A=alert_rec(r[which]["A"], r["A"]), B=alert_rec(r[which]["B"], r["B"]), tmpl=r[which + "_template"]))
    return pairs, members

def build_main(tag, scoped, window=24 * 3600 * 1000):
    items = []
    for d in M.load(tag):
        for a, comp in (M.label_alerts_scoped(d, window) if scoped else M.label_alerts(d, window)):
            t, e = M.truth_of(comp, "injected")
            if t in ("C1", "C2", "C3"):
                items.append(dict(truth=t, sub=e[1], injected=e[5], alert=alert_rec(a, d), patient=d["patient"], day=d["day"]))
    return items

if __name__ == "__main__":
    pairs, members = build_pairs()
    pickle.dump((pairs, members), open(f"{common.ROOT}/out/sens2_pairs.pkl", "wb"))
    for sc in (False, True):
        pickle.dump(build_main("m120b", sc), open(f"{common.ROOT}/out/sens2_main_{'scoped' if sc else 'unscoped'}.pkl", "wb"))
    pickle.dump(build_main('m120b', True, 0), open(f"{common.ROOT}/out/sens2_main_tight.pkl", "wb"))
    print(len(pairs), len(members))
