"""Pre-extract the reading classes of every matched alert once (the sweeps then only evaluate the table)."""
import sys, pickle
sys.path.insert(0, "/tmp/research/likelihood/scripts"); sys.path.insert(0, "/tmp/research/likelihood")
import pairlib as P, mainlib as M, common, likelihood_attr as L

TBS = [1_000, 10_000, 30_000, 60_000, 180_000]
reg, tpl, cfg = common.load()
att = L.LikelihoodAttributor(reg)

def rd(ev, template):
    return None if ev is None else L.classes_from_rule(att.rule, ev, template)

def alert_rec(a, mem):
    t = a["template"]
    return dict(t=t, on=rd(a["ev_on"], a["record"].template), off=rd(a["ev_off"], a["record"].template),
                ext={tb: P.ext_features(mem, a, tb) for tb in TBS}, old_on=a["old_on"], old_off=a["old_off"], key=a["key"])

def build():
    rows = P.load("p40", 1)
    pairs, members = [], []
    for r in rows:
        P.match_pair(r)
        for m in "AB":
            if r["own"][m]:
                a = r["own"][m]
                members.append(dict(group=r["group"], variant=r["variant"], number=r["number"], member=m, truth=r["cause"][m],
                                    sub=r["rel"][m]["subtype"], alert=alert_rec(a, r[m])))
        for which in ("com", "com_alt"):
            if r[which]["A"] and r[which]["B"]:
                pairs.append(dict(which=which, group=r["group"], variant=r["variant"], number=r["number"], flag=r["flag"],
                                  sep=tuple(sorted(r["separated_by"])), cA=r["cause"]["A"], cB=r["cause"]["B"],
                                  A=alert_rec(r[which]["A"], r["A"]), B=alert_rec(r[which]["B"], r["B"]), tmpl=r[which + "_template"]))
    return pairs, members

def build_main(tag, mode="injected"):
    items = []
    for d in M.load(tag):
        for a, comp in M.label_alerts(d):
            t, e = M.truth_of(comp, mode)
            if t in ("C1", "C2", "C3"):
                rec = alert_rec(a, d); items.append(dict(truth=t, sub=e[1], injected=e[5], alert=rec, patient=d["patient"], day=d["day"]))
    return items

if __name__ == "__main__":
    pairs, members = build()
    pickle.dump((pairs, members), open(f"{common.ROOT}/out/sens_pairs.pkl", "wb"))
    for tag in ("m120", "r40"):
        for mode in ("injected", "strict"):
            pickle.dump(build_main(tag, mode), open(f"{common.ROOT}/out/sens_main_{tag}_{mode}.pkl", "wb"))
    print(len(pairs), len(members))
