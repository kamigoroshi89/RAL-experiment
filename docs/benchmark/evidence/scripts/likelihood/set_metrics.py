"""Item 4: set metrics (coverage of the true subtype, mean size) on the 1879 pair members and the main population."""
import sys, collections, math
sys.path.insert(0, "/tmp/research/likelihood/scripts"); sys.path.insert(0, "/tmp/research/likelihood")
from setlib import *
import pairlib as P

pairs, members = load_pairs()
out = []; pr = lambda *a: out.append(" ".join(str(x) for x in a))

def eval_members(sp, rows_sel=lambda m: True, groupkey=lambda m: m["group"]):
    """returns dict key -> dict(method -> list of rows)"""
    res = collections.defaultdict(lambda: collections.defaultdict(list))
    for m in members:
        if not rows_sel(m): continue
        rec = m["alert"]; t = rec["t"]; truth = m["sub"]
        r = sub_result(rec, sp)
        if r is None: continue
        S = r.top_set(sp.level)
        full = SM.full_set(t, sp)
        k = groupkey(m)
        res[k]["subtype set"].append((truth in S, len(S), len({c for c in L.CAUSES if set(S) & set(SM.class_subtypes(t, c, sp))}), 0, 0))
        ko = rec["old_on"]; So = kappa_set(ko, t, sp)
        res[k]["old rule (diag ON), kappa as set"].append((truth in So, len(So), 0, 0, 0))
        kt = class_kappa(rec, sp.base); St = kappa_set(kt, t, sp)
        res[k]["class table, kappa at tau 0.8 as set"].append((truth in St, len(St), 0, 0, 0))
        res[k]["full set (no information)"].append((truth in full, len(full), 0, 0, 0))
        res[k]["top-1 subtype"].append((truth == r.ranked()[0][0], 1, 0, 0, 0))
    return res

METH = ["subtype set", "class table, kappa at tau 0.8 as set", "old rule (diag ON), kappa as set", "top-1 subtype", "full set (no information)"]
sp = sp_of("uniform", 0.9)
pr(f"#### 9.4.1 Pair members (1879 with a matched alert), by group and stratum: coverage of the true subtype and mean set size. Subtype set: cumulative level {sp.level}, design {sp.design}, reference cells, V0 evidence. UNDETERMINED of a kappa = the full set of the subtypes applicable at the alert's template.")
res = eval_members(sp, groupkey=lambda m: (m["group"], "indist" if m["flag"] else "dist"))
pr("| group | stratum | members | " + " | ".join(METH) + " |"); pr("|---|---|---|" + "---|" * len(METH))
allr = collections.defaultdict(lambda: collections.defaultdict(list))
for g in P.GROUPS:
    for key in ("dist", "indist"):
        d = res.get((g, key))
        if not d: continue
        for mth in METH: allr[key][mth] += d[mth]
        pr(f"| {g} | {key} | {len(d[METH[0]])} | " + " | ".join(fmt(stats(d[m])) for m in METH) + " |")
for key in ("dist", "indist"):
    pr(f"| ALL | {key} | {len(allr[key][METH[0]])} | " + " | ".join(fmt(stats(allr[key][m])) for m in METH) + " |")
pr()
pr("By true subtype (design uniform, level 0.9): coverage and mean size of the subtype set")
bysub = collections.defaultdict(list)
for m in members:
    r = sub_result(m["alert"], sp)
    if r is None: continue
    S = r.top_set(sp.level)
    bysub[(m["group"][:14], m["sub"])].append((m["sub"] in S, len(S), 0, 0, 0))
pr("| group | true subtype | members | coverage, size |"); pr("|---|---|---|---|")
for k, v in sorted(bysub.items()): pr(f"| {k[0]} | {k[1]} | {len(v)} | {fmt(stats(v))} |")
pr()
# sensitivity: level x design on pairs
pr("#### 9.4.2 Pair members, all strata: coverage and mean size by cumulative level and within-class prior design (cells at the reference point)")
pr("| design | level | coverage, size (all 1879) | distinguishable | indistinguishable |"); pr("|---|---|---|---|---|")
for design in SM.load_config()["designs"]:
    for lvl in (0.8, 0.9, 0.95):
        s = sp_of(design, lvl)
        rr = eval_members(s, groupkey=lambda m: "indist" if m["flag"] else "dist")
        allm = rr["dist"]["subtype set"] + rr["indist"]["subtype set"]
        pr(f"| {design} | {lvl} | {fmt(stats(allm))} | {fmt(stats(rr['dist']['subtype set']))} | {fmt(stats(rr['indist']['subtype set']))} |")
pr()
pr("Class posterior (sum over the subtypes) of the pair members under the three designs, against the class-level table of section 3 (reference cells, uniform class prior): argmax class = truth class and kappa at tau 0.8")
pr("| design | argmax = truth /1879 | UNDETERMINED / confident right / confident wrong at 0.8 | confident C1 for non-C1 |"); pr("|---|---|---|---|")
base_ok = 859
for design in SM.load_config()["designs"]:
    s = sp_of(design, 0.9)
    ok = und = right = wrong = c1w = 0
    for m in members:
        r = sub_result(m["alert"], s)
        am = max(r.class_post, key=r.class_post.get); k = am if r.class_post[am] >= 0.8 else "UNDETERMINED"
        truth = m["truth"]
        ok += am == truth; und += k == "UNDETERMINED"; right += k == truth; wrong += (k != truth and k != "UNDETERMINED"); c1w += (k == "C1" and truth != "C1")
    pr(f"| {design} | {ok} | {und} / {right} / {wrong} | {c1w} |")
pr("(class-level table, independence given the class: 859, 1711 / 168 / 0, 0; the subtype model is the latent-class variant G2: 859, 1634 / 245 / 0 in section 6.1)")
pr()
# main population
for scoped in (False, True, 'tight'):
    items = load_main(scoped)
    lab = {False: "labelling of section 5 (injected first, 24 h)", True: "scope-aware labelling (a dropout counts only if its target is in the template's data scope, window 24 h)", 'tight': "tight labelling (scope-aware, alert decided while the event window is open)"}[scoped]
    pr(f"#### 9.4.{ {False: 3, True: 4, 'tight': 5}[scoped] } Main population m120, {lab}: coverage of the true subtype and mean set size per template; subtype set at level 0.9, design uniform")
    d = collections.defaultdict(lambda: collections.defaultdict(list))
    for it in items:
        rec = it["alert"]; t = rec["t"]; truth = it["sub"]
        r = sub_result(rec, sp)
        if r is None: continue
        S = r.top_set(sp.level)
        full = SM.full_set(t, sp)
        for key in (t, "ALL"):
            d[key]["subtype set"].append((truth in S, len(S), 0, 0, 0))
            So = kappa_set(rec["old_on"], t, sp); d[key]["old rule (diag ON), kappa as set"].append((truth in So, len(So), 0, 0, 0))
            St = kappa_set(class_kappa(rec, sp.base), t, sp); d[key]["class table, kappa at tau 0.8 as set"].append((truth in St, len(St), 0, 0, 0))
            d[key]["top-1 subtype"].append((truth == r.ranked()[0][0], 1, 0, 0, 0))
            d[key]["full set (no information)"].append((truth in full, len(full), 0, 0, 0))
    pr("| template | alerts | " + " | ".join(METH) + " |"); pr("|---|---|" + "---|" * len(METH))
    for key in ["range", "sched", "hold", "count", "resp", "ALL"]:
        if key not in d: continue
        pr(f"| {key} | {len(d[key][METH[0]])} | " + " | ".join(fmt(stats(d[key][m])) for m in METH) + " |")
    pr()
    # by cause
    dc = collections.defaultdict(lambda: collections.defaultdict(list))
    for it in items:
        rec = it["alert"]; t = rec["t"]; truth = it["sub"]
        r = sub_result(rec, sp)
        if r is None: continue
        S = r.top_set(sp.level)
        So = kappa_set(rec["old_on"], t, sp); St = kappa_set(class_kappa(rec, sp.base), t, sp)
        for key in (it["truth"],):
            dc[key]["subtype set"].append((truth in S, len(S), 0, 0, 0)); dc[key]["old rule (diag ON), kappa as set"].append((truth in So, len(So), 0, 0, 0))
            dc[key]["class table, kappa at tau 0.8 as set"].append((truth in St, len(St), 0, 0, 0))
    pr("By true cause: " + "; ".join(f"{c}: " + ", ".join(f"{m.split(',')[0]}: {fmt(stats(dc[c][m]))}" for m in METH[:3]) for c in ("C1", "C2", "C3")))
    pr()
    if scoped is False:
        pr("By true subtype (subtype set, level 0.9, design uniform):")
        bs = collections.defaultdict(list)
        for it in items:
            r = sub_result(it["alert"], sp)
            if r is None: continue
            S = r.top_set(sp.level); bs[(it["truth"], it["sub"])].append((it["sub"] in S, len(S), 0, 0, 0))
        pr("| cause | true subtype | alerts | coverage, size |"); pr("|---|---|---|---|")
        for k, v in sorted(bs.items()): pr(f"| {k[0]} | {k[1]} | {len(v)} | {fmt(stats(v))} |")
        pr()
pr("#### 9.4.6 Main population (labelling of section 5): cumulative level x design")
items = load_main(False)
pr("| design | level | all alerts: coverage, size | C1 | C2 | C3 | silent faults (stuck_at, cuff_silent_bias, dispenser_bounce) |"); pr("|---|---|---|---|---|---|---|")
for design in SM.load_config()["designs"]:
    for lvl in (0.8, 0.9, 0.95):
        s = sp_of(design, lvl)
        rows = collections.defaultdict(list)
        for it in items:
            r = sub_result(it["alert"], s)
            if r is None: continue
            S = r.top_set(lvl); row = (it["sub"] in S, len(S), 0, 0, 0)
            rows["all"].append(row); rows[it["truth"]].append(row)
            if it["truth"] == "C2" and it["sub"] in ("stuck_at", "cuff_silent_bias", "dispenser_bounce"): rows["sil"].append(row)
        pr(f"| {design} | {lvl} | {fmt(stats(rows['all']))} | {fmt(stats(rows['C1']))} | {fmt(stats(rows['C2']))} | {fmt(stats(rows['C3']))} | {fmt(stats(rows['sil']))} |")
open(f"{common.ROOT}/out/set_metrics.md", "w").write("\n".join(out))
print("\n".join(out))
