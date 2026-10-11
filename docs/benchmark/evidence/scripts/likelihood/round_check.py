"""Section 10.1: cuff resolution in the generator (research copy): natural repeat, stuck_at, silent-fault table, side effects."""
import sys, collections, math, pickle, json
sys.path.insert(0, "/tmp/research/likelihood/scripts"); sys.path.insert(0, "/tmp/research/likelihood")
import numpy as np
import common, mainlib as M, pairlib as P
from setlib import *
out = []; pr = lambda *a: out.append(" ".join(str(x) for x in a))
REPN = None  # measured below

# ---- 10.1.1 natural repeat in the fault-free run with the generator's own noise
def chain(tag):
    by = collections.defaultdict(list)
    for d in M.load(tag): by[d["patient"]] += d["bp"]
    return by
by = chain("ffr"); n = eq = 0; vals = []
for p, s in by.items():
    v = [x[1] for x in sorted(s)]; vals += v
    for a, b in zip(v, v[1:]): n += 1; eq += (a == b)
lo, hi = P.wilson(eq, n)
REPN = eq / n
pr("#### 10.1.1 Natural repeat probability, fault-free run with the cuff rounded to 1 mmHg in the generator (`RALMON_CUFF_RES_MMHG=1`, pulse 1 bpm)")
pr(f"Fault-free run `ffr` (injection rates 0, 120 patients x 30 days, seed 0): {len(vals)} readings, all integers: {all(abs(x-round(x))<1e-9 for x in vals)}; consecutive pairs {n}, **exactly equal {eq}: observed frequency {REPN:.4f} (Wilson 95% {lo:.4f}-{hi:.4f})**. The formula of 9.3.1 (E[max(0, 1 - |Delta|/r)] on the unrounded differences) predicted 0.0200; the unrounded run had 0 of 17 797. This measured value is the cell rep_nat used in section 10 (a grid value: 0.5 x, 1 x and 2 x of it are swept in 10.1.4).")
pr()
json.dump({"rep_nat": REPN}, open(f"{common.ROOT}/out/rep_nat_rounded.json", "w"))
# ---- 10.1.2 side effects: alert lists, flags, bands
pr("#### 10.1.2 Does rounding change anything else? Pairs (1080 pairs, 2160 members), unrounded build `p40b` against rounded build `p40r`")
a = pickle.load(open(f"{common.ROOT}/out/pairs_p40b_sw1.pkl", "rb")); b = pickle.load(open(f"{common.ROOT}/out/pairs_p40r_sw1.pkl", "rb"))
chg = []; flagchg = 0; gtchg = 0; sepchg = 0; nal = 0; keychg = 0
for x, y in zip(a, b):
    assert x["number"] == y["number"]
    flagchg += x["flag"] != y["flag"]; sepchg += x["separated_by"] != y["separated_by"]
    for m in "AB":
        la = sorted((al["template"], al["key"], al["decided"], al["old_on"], al["old_off"]) for al in x[m]["alerts"])
        lb = sorted((al["template"], al["key"], al["decided"], al["old_on"], al["old_off"]) for al in y[m]["alerts"])
        nal += len(la)
        if x[m]["gt"] != y[m]["gt"]: gtchg += 1
        if la != lb:
            sa, sb = set(la), set(lb)
            chg.append((x["group"], x["variant"], x["number"], m, sorted(sa - sb)[:2], sorted(sb - sa)[:2]))
rem = collections.Counter(); add = collections.Counter(); kap = 0
for x, y in zip(a, b):
    for m in "AB":
        da = {(al["template"], al["key"]): al for al in x[m]["alerts"]}; db = {(al["template"], al["key"]): al for al in y[m]["alerts"]}
        for k in da.keys() - db.keys(): rem[k[0]] += 1
        for k in db.keys() - da.keys(): add[k[0]] += 1
        for k in da.keys() & db.keys(): kap += da[k]["old_on"] != db[k]["old_on"] or da[k]["decided"] != db[k]["decided"]
pr(f"- pair alerts present only in the unrounded build: {dict(rem)}; only in the rounded build: {dict(add)}; alerts present in both whose old kappa or decision time changes: {kap}.")
pr(f"- members whose alert list (template, key, decision time, old kappa with and without diagnostics) differs: **{len(chg)} of 2160** (alerts compared: {nal}); members whose ground-truth event list differs: {gtchg}; pairs whose `indistinguishable_by_construction` flag changes: {flagchg}; pairs whose `separated_by` changes: {sepchg}.")
for c in chg[:8]: pr(f"  - {c[0]} {c[1]} #{c[2]}{c[3]}: only unrounded {c[4]}; only rounded {c[5]}")
if len(chg) > 8: pr(f"  - ... {len(chg)-8} more")
# main population
a = M.load("m120b"); b = M.load("m120r")
chg2 = []; nd = 0; gt2 = 0
for x, y in zip(a, b):
    la = sorted((al["template"], al["key"], al["decided"], al["old_on"]) for al in x["alerts"]); lb = sorted((al["template"], al["key"], al["decided"], al["old_on"]) for al in y["alerts"])
    nd += 1; gt2 += x["gt"] != y["gt"]
    if la != lb:
        sa, sb = set(la), set(lb); chg2.append((x["patient"], x["day"], sorted(sa - sb)[:2], sorted(sb - sa)[:2], len(la), len(lb)))
remm = collections.Counter(); addm = collections.Counter(); kapm = 0
for x, y in zip(M.load("m120b"), M.load("m120r")):
    da = {(al["template"], al["key"]): al for al in x["alerts"]}; db = {(al["template"], al["key"]): al for al in y["alerts"]}
    for k in da.keys() - db.keys(): remm[k[0]] += 1
    for k in db.keys() - da.keys(): addm[k[0]] += 1
    for k in da.keys() & db.keys(): kapm += da[k]["old_on"] != db[k]["old_on"] or da[k]["decided"] != db[k]["decided"]
pr(f"- main population: alerts only in the unrounded build {dict(remm)}; only in the rounded build {dict(addm)}; in both with a changed old kappa or decision time: {kapm}.")
pr(f"- main population m120 (3600 patient-days, {sum(len(x['alerts']) for x in a)} unrounded alerts, {sum(len(y['alerts']) for y in b)} rounded): patient-days whose alert list differs: **{len(chg2)}**; ground-truth lists that differ: {gt2}.")
for c in chg2[:8]: pr(f"  - {c[0]} day {c[1]}: only unrounded {c[2]}; only rounded {c[3]}")
if len(chg2) > 8: pr(f"  - ... {len(chg2)-8} more")
# band checks on readings
lo_, hi_, hold = 110.0, 140.0, 100.0
nr = ch_band = ch_hold = 0; examples = []
ra = {(d["patient"], d["day"]): d["bp"] for d in M.load("m120b")}; rb = {(d["patient"], d["day"]): d["bp"] for d in M.load("m120r")}
for k, s in ra.items():
    t = rb[k]
    if len(s) != len(t): continue
    for (t1, v1), (t2, v2) in zip(s, t):
        nr += 1
        in1 = lo_ <= v1 <= hi_; in2 = lo_ <= v2 <= hi_
        ch_band += in1 != in2; ch_hold += (v1 < hold) != (v2 < hold)
pr(f"- static band checks (B1-style, registry bp_band_low {lo_}, bp_band_high {hi_}, bp_hold_threshold {hold}): of {nr} readings, **{ch_band} change in-band status and {ch_hold} change the below-hold status** when rounded to 1 mmHg ({100*ch_band/nr:.2f}% and {100*ch_hold/nr:.2f}%); the readings are those of m120b and m120r (same latent days).")
pr()
open(f"{common.ROOT}/out/round_check.md", "w").write("\n".join(out))
print("\n".join(out))
