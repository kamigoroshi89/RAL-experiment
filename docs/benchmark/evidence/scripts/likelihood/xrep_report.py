"""Item 3: the channel 'identical repeated value' for stuck_at."""
import sys, collections, math
sys.path.insert(0, "/tmp/research/likelihood/scripts"); sys.path.insert(0, "/tmp/research/likelihood")
from setlib import *
import mainlib as M, pairlib as P
out = []; pr = lambda *a: out.append(" ".join(str(x) for x in a))
LAB = sys.argv[1] if len(sys.argv) > 1 else "unscoped"
items = load_main(LAB)
LABTXT = {"unscoped": "labelling of section 5 (injected first, window 24 h, any dropout target)", "tight": "tight labelling (scope-aware dropout target, alert decided while the event window is open)"}[LAB]
SIL = ("stuck_at", "cuff_silent_bias", "dispenser_bounce")
C1S = set(SM.C1_SUBTYPES)

def sets(it, sp, r):
    res = sub_result(it["alert"], sp, r=r)
    return res.top_set(sp.level)

# ---- effective k for stuck_at (from the generator's injection log)
ks = collections.Counter(); wins = []
for d in M.load("m120b"):
    for l in d["log"]:
        if l["subtype"] == "stuck_at" and l["realised"]:
            on, en = l["onset_ms"], l["end_ms"]
            k = sum(1 for t, v in d["bp"] if on <= t < en)
            ks[k] += 1; wins.append((en - on) / 3.6e6)
pr("#### 9.3.2 Effective k of stuck_at (readings of the stream inside the frozen window), from the injection log of m120 (realised stuck_at records)")
pr("| readings in the window | records |"); pr("|---|---|")
for k, v in sorted(ks.items()): pr(f"| {k} | {v} |")
pr(f"Window durations of the records (h): {sorted(set(round(w,2) for w in wins))} (placeholders 1/4/12 h). Every reading in the window repeats the last value before the onset, so with k readings in the window the first repeats the earlier reading and the others repeat each other: all k readings are identical to their predecessor, P(A | stuck_at, alert at a reading of the window) = 1 up to the leak eps.")
pr()
# class of XREP among alerts, by truth subtype
pr(f"Labelling: {LABTXT}; {len(items)} alerts."); pr(); pr("#### 9.3.3 Reading class of the channel at the matched alerts (cuff-reading templates range, sched, hold, resp), by true subtype and display resolution r of the cuff (None = the generator's floats)")
pr("| true subtype | alerts | r | A (identical) | D (differ) | U (fewer than two readings) |"); pr("|---|---|---|---|---|---|")
cnt = collections.defaultdict(collections.Counter)
for it in items:
    if it["alert"]["t"] not in SM.CUFF_TEMPLATES: continue
    for r in RS if (RS := (None, 1.0, 2.0, 5.0)) else ():
        cnt[(it["sub"], r)][it["alert"]["rep"][r]] += 1
for (sub, r), c in sorted(cnt.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
    if sub in SIL or sub in ("spontaneous_range", "hypertensive_spike", "nav_delay", "ble_dropout", "replay", "injection_naive", "dispense_forgery"):
        n = sum(c.values()); pr(f"| {sub} | {n} | {r} | {c['A']} ({100*c['A']/n:.1f}%) | {c['D']} | {c['U']} |")
pr()
# natural A rate among non-stuck alerts, by r, vs formula
pr("Natural rate of A among the cuff-template alerts whose true subtype is not stuck_at (values rounded to r mmHg before comparing), against the fault-free formula of 9.3.1 (rep_nat):")
for r in (None, 1.0, 2.0, 5.0):
    a = n = 0
    for it in items:
        if it["sub"] == "stuck_at" or it["alert"]["t"] not in SM.CUFF_TEMPLATES: continue
        c = it["alert"]["rep"][r]
        if c != "U": n += 1; a += c == "A"
    pr(f"- r = {r}: {a}/{n} = {a/n:.4f} (rep_nat {REP_NAT[r]})")
pr()
# set effects
pr("#### 9.3.4 Effect of the channel on the subtype set (design uniform, reference cells; rep_nat = the value of 9.3.1 for the resolution r)")
pr("Silent-fault alerts of the main population (433: stuck_at 137, cuff_silent_bias 256, dispenser_bounce 40; dispenser_bounce is at COUNT, which does not read the cuff, so it cannot change). 'Contains C1': the set holds at least one C1 subtype (the masquerade). 'Exact': the set is exactly the true subtype.")
pr("| level | r | true subtype | alerts | coverage without -> with | mean size without -> with | contains C1 without -> with | exact without -> with | sets that lose all C1 subtypes |"); pr("|---|---|---|---|---|---|---|---|---|")
removed_rows = []
for lvl in (0.8, 0.9, 0.95):
    for r in (None, 1.0, 2.0, 5.0):
        sp0 = sp_of("uniform", lvl); sp1 = sp_of("uniform", lvl, rep=True, r=r)
        agg = {s: collections.Counter() for s in SIL}; sz = {s: [0, 0] for s in SIL}
        wrong = collections.Counter(); nA = 0
        for it in items:
            S0 = sets(it, sp0, r); S1 = sets(it, sp1, r); tr = it["sub"]
            if it["truth"] == "C2" and tr in SIL:
                a = agg[tr]; a["n"] += 1
                a["cov0"] += tr in S0; a["cov1"] += tr in S1
                a["c10"] += bool(set(S0) & C1S); a["c11"] += bool(set(S1) & C1S)
                a["ex0"] += S0 == [tr]; a["ex1"] += S1 == [tr]
                a["lose"] += bool(set(S0) & C1S) and not (set(S1) & C1S)
                sz[tr][0] += len(S0); sz[tr][1] += len(S1)
            elif tr != "stuck_at":
                if (tr in S0) and (tr not in S1):
                    wrong[(it["truth"], tr)] += 1
                if it["alert"]["t"] in SM.CUFF_TEMPLATES and it["alert"]["rep"][r] == "A": nA += 1
        for s in SIL:
            a = agg[s]; n = a["n"]
            pr(f"| {lvl} | {r} | {s} | {n} | {a['cov0']} -> {a['cov1']} | {sz[s][0]/n:.2f} -> {sz[s][1]/n:.2f} | {a['c10']} -> {a['c11']} | {a['ex0']} -> {a['ex1']} | {a['lose']} |")
        removed_rows.append((lvl, r, nA, sum(wrong.values()), dict(wrong)))
pr()
pr("#### 9.3.5 Alerts of other causes that the channel wrongly removes from their set (true subtype in the set without the channel, not with it), non-stuck_at alerts of the main population")
pr("| level | r | non-stuck_at cuff-template alerts with A | true subtype removed | by (cause, subtype) |"); pr("|---|---|---|---|---|")
for lvl, r, nA, tot, w in removed_rows:
    pr(f"| {lvl} | {r} | {nA} | {tot} | {w if w else '-'} |")
pr()
# overall coverage with and without, all alerts
pr("#### 9.3.6 All alerts of the main population: coverage and mean size without and with the channel (design uniform)")
pr("| level | r | coverage without | coverage with | mean size without | mean size with |"); pr("|---|---|---|---|---|---|")
for lvl in (0.8, 0.9, 0.95):
    for r in (None, 1.0, 2.0, 5.0):
        sp0 = sp_of("uniform", lvl); sp1 = sp_of("uniform", lvl, rep=True, r=r)
        c0 = c1 = z0 = z1 = n = 0
        for it in items:
            S0 = sets(it, sp0, r); S1 = sets(it, sp1, r)
            c0 += it["sub"] in S0; c1 += it["sub"] in S1; z0 += len(S0); z1 += len(S1); n += 1
        pr(f"| {lvl} | {r} | {c0}/{n} ({100*c0/n:.1f}%) | {c1}/{n} ({100*c1/n:.1f}%) | {z0/n:.3f} | {z1/n:.3f} |")
open(f"{common.ROOT}/out/xrep_report_{LAB}.md", "w").write("\n".join(out))
print("\n".join(out))
