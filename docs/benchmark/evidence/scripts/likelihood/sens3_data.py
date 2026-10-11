"""Section 10 data: matched alerts with all channels, patient/pair identifiers and the builder's split."""
import sys, pickle
sys.path.insert(0, "/tmp/research/likelihood/scripts"); sys.path.insert(0, "/tmp/research/likelihood")
import pairlib as P, mainlib as M, common
import sens_data2 as S2

def ctx_for(kind, tag):
    from ralmon.benchmark.builder import BuildContext
    return BuildContext.create(f"{common.ROOT}/runs/{kind}_{tag}/configs/benchmark/default.yaml", allow_fixture_only=True)

def split_pairs(tag):
    from ralmon.benchmark.builder import split_patients
    ctx = ctx_for("pairs", tag)
    units = ctx.pair_units(); ids = [p for p, _, _ in ctx.patient_units()] + [u[0] for u in units]
    sp = split_patients(ids, ctx.config.split_fractions, ctx.config.generation_seed)
    return {n: sp[u[0]] for n, u in enumerate(units)}, {n: u[0] for n, u in enumerate(units)}

def split_main(tag):
    from ralmon.benchmark.builder import split_patients
    ctx = ctx_for("main", tag)
    ids = [p for p, _, _ in ctx.patient_units()]
    return dict(split_patients(ids, ctx.config.split_fractions, ctx.config.generation_seed))

def build_pairs(tag):
    rows = P.load(tag, 1)
    splits, pid = split_pairs(tag)
    members = []
    for r in rows:
        P.match_pair(r)
        for m in "AB":
            if r["own"][m]:
                members.append(dict(group=r["group"], variant=r["variant"], number=r["number"], pair=pid[r["number"]], split=splits[r["number"]],
                                    member=m, truth=r["cause"][m], sub=P.MECH[r["group"]][0 if m == "A" else 1][1], flag=r["flag"],
                                    alert=S2.alert_rec(r["own"][m], r[m])))
    pairs = []
    for r in rows:
        if r["com"]["A"] and r["com"]["B"]:
            pairs.append(dict(group=r["group"], variant=r["variant"], number=r["number"], split=splits[r["number"]], flag=r["flag"],
                              sep=tuple(sorted(r["separated_by"])), sA=P.MECH[r["group"]][0][1], sB=P.MECH[r["group"]][1][1],
                              cA=r["cause"]["A"], cB=r["cause"]["B"], A=S2.alert_rec(r["com"]["A"], r["A"]), B=S2.alert_rec(r["com"]["B"], r["B"])))
    return members, pairs

def build_main(tag, lab):
    sp = split_main(tag)
    items = []
    for d in M.load(tag):
        fn = (lambda dd: M.label_alerts(dd)) if lab == "s5" else (lambda dd: M.label_alerts_scoped(dd, 0))
        for a, comp in fn(d):
            t, e = M.truth_of(comp, "injected")
            if t in ("C1", "C2", "C3"):
                items.append(dict(truth=t, sub=e[1], patient=d["patient"], day=d["day"], split=sp[d["patient"]], alert=S2.alert_rec(a, d)))
    return items

if __name__ == "__main__":
    kind, tag = sys.argv[1], sys.argv[2]
    if kind == "pairs":
        pickle.dump(build_pairs(tag), open(f"{common.ROOT}/out/sens3_pairs_{tag}.pkl", "wb"))
    else:
        for lab in ("s5", "tight"):
            pickle.dump(build_main(tag, lab), open(f"{common.ROOT}/out/sens3_main_{tag}_{lab}.pkl", "wb"))
    print("done", kind, tag)
