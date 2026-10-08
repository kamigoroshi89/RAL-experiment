"""WS01-T09 part C: supplementary estimate of cuff (NIBP) minus arterial-line (ART) systolic difference.

Data: PhysioNet VitalDB 1.0.0 (CC BY 4.0), 30 local cases, read-only.
Tracks: Solar8000/NIBP_SBP (oscillometric cuff) and Solar8000/ART_SBP (arterial line numeric).

Reading rule. The Solar8000 numeric NIBP_SBP is re-emitted about every 2 s while the value is held.
A cuff reading is the first record of a run: the first record of the case, a record whose value differs
from the previous record, or a record that follows a gap > 10 s in the NIBP stream. Consecutive readings
with an identical value and no gap cannot be separated (undercount, stated as a caveat).

Pairing rule (main). For each cuff reading at time t, take the ART_SBP records in [t - W, t + W]
(W = 30 s), keep the valid ones (40 <= ART_SBP <= 250 mmHg), require >= 50% of the expected 2 s samples
(>= W/2 records... i.e. >= 15 for W = 30 s) to be valid, and pair the cuff value with the median of the
valid ART values. Exclusions: cuff value outside [40, 250] mmHg; ART window with too few valid samples;
ART window whose valid values span more than 40 mmHg (max - min), taken as an artefact or a transient
(flush, zeroing, rapid change), counted separately.

Sensitivity variants: W = 15 s and W = 60 s; a window before the reading [t - 60 s, t] (the cuff value
refers to the deflation that precedes the reported time); no span filter.

Statistics: n pairs, n cases, mean (bias) and SD of NIBP - ART over pooled pairs; per-case mean and SD;
cluster (case-level) bootstrap 95% intervals for pooled bias and SD (2000 resamples, seed 20261008);
within-case pooled SD (sqrt of mean of per-case variances weighted by df).
"""

from __future__ import annotations

import glob
import os

import numpy as np
import vitaldb

DATA = os.environ.get("VITALDB_DIR", "data/raw/vitaldb/vital_files")  # run from the repository root
NIBP, ART = "Solar8000/NIBP_SBP", "Solar8000/ART_SBP"
LO, HI = 40.0, 250.0
SEED = 20261008


def readings(recs):
    dt = np.array([r["dt"] for r in recs], dtype=float)
    v = np.array([r["val"] for r in recs], dtype=float)
    order = np.argsort(dt, kind="stable")
    dt, v = dt[order], v[order]
    keep = np.zeros(len(v), dtype=bool)
    if len(v):
        keep[0] = True
        keep[1:] = (np.diff(v) != 0) | (np.diff(dt) > 10.0)
    return dt[keep], v[keep]


def load():
    cases = {}
    for f in sorted(glob.glob(os.path.join(DATA, "*.vital"))):
        vf = vitaldb.VitalFile(f, [NIBP, ART])
        n, a = vf.trks.get(NIBP), vf.trks.get(ART)
        if not n or not a or not n.recs or not a.recs:
            continue
        tn, vn = readings(n.recs)
        ta = np.array([r["dt"] for r in a.recs], dtype=float)
        va = np.array([r["val"] for r in a.recs], dtype=float)
        o = np.argsort(ta, kind="stable")
        cases[os.path.basename(f)[:4]] = (tn, vn, ta[o], va[o])
    return cases


def pair(cases, before=None, w=30.0, span_max=40.0, drop_first=False):
    out = {}
    excl = {"cuff_out_of_range": 0, "art_insufficient": 0, "art_span": 0}
    total = 0
    for cid, (tn, vn, ta, va) in cases.items():
        diffs = []
        for idx, (t, v) in enumerate(zip(tn, vn)):
            if drop_first and idx == 0:
                continue
            total += 1
            if not (LO <= v <= HI):
                excl["cuff_out_of_range"] += 1
                continue
            lo, hi = (t - before, t) if before else (t - w, t + w)
            i0, i1 = np.searchsorted(ta, lo, "left"), np.searchsorted(ta, hi, "right")
            seg = va[i0:i1]
            seg = seg[(seg >= LO) & (seg <= HI)]
            need = ((hi - lo) / 2.0) * 0.5
            if len(seg) < need:
                excl["art_insufficient"] += 1
                continue
            if span_max is not None and seg.max() - seg.min() > span_max:
                excl["art_span"] += 1
                continue
            diffs.append(v - float(np.median(seg)))
        if diffs:
            out[cid] = np.array(diffs)
    return out, excl, total


def stats(out, rng):
    allx = np.concatenate(list(out.values()))
    ids = list(out)
    boots_m, boots_s = [], []
    for _ in range(2000):
        pick = rng.choice(len(ids), size=len(ids), replace=True)
        x = np.concatenate([out[ids[i]] for i in pick])
        boots_m.append(x.mean())
        boots_s.append(x.std(ddof=1))
    num = sum(((d - d.mean()) ** 2).sum() for d in out.values() if len(d) > 1)
    den = sum(len(d) - 1 for d in out.values() if len(d) > 1)
    return {
        "n_pairs": len(allx),
        "n_cases": len(ids),
        "mean": allx.mean(),
        "sd": allx.std(ddof=1),
        "median": float(np.median(allx)),
        "robust_sd_1.4826MAD": float(1.4826 * np.median(np.abs(allx - np.median(allx)))),
        "p2.5": float(np.percentile(allx, 2.5)),
        "p97.5": float(np.percentile(allx, 97.5)),
        "frac_abs_le5": float(np.mean(np.abs(allx) <= 5)),
        "frac_abs_le10": float(np.mean(np.abs(allx) <= 10)),
        "boot_mean_95": (float(np.percentile(boots_m, 2.5)), float(np.percentile(boots_m, 97.5))),
        "boot_sd_95": (float(np.percentile(boots_s, 2.5)), float(np.percentile(boots_s, 97.5))),
        "within_case_sd": float(np.sqrt(num / den)) if den else float("nan"),
        "sd_of_case_means": float(np.std([d.mean() for d in out.values()], ddof=1)),
    }


def main():
    cases = load()
    print(f"cases with both tracks: {len(cases)} -> {sorted(cases)}")
    variants = [
        ("main: +-30 s, span<=40", dict(w=30.0, span_max=40.0)),
        ("+-15 s, span<=40", dict(w=15.0, span_max=40.0)),
        ("+-60 s, span<=40", dict(w=60.0, span_max=40.0)),
        ("[t-60 s, t], span<=40", dict(before=60.0, span_max=40.0)),
        ("+-30 s, no span filter", dict(w=30.0, span_max=None)),
        ("+-30 s, span<=20", dict(w=30.0, span_max=20.0)),
        ("+-30 s, span<=40, first reading of each case dropped", dict(w=30.0, span_max=40.0, drop_first=True)),
    ]
    for name, kw in variants:
        rng = np.random.default_rng(SEED)
        out, excl, total = pair(cases, **kw)
        s = stats(out, rng)
        print(f"\n== {name}: cuff readings in paired cases={total}, exclusions={excl}")
        for k, v in s.items():
            print(f"  {k}: {v if not isinstance(v, float) else round(v, 2)}")
        if name.startswith("main"):
            allx = np.concatenate(list(out.values()))
            print("  largest |diff| pairs:", sorted(allx, key=abs)[-3:])
            print("  per case (id: n, mean, sd):")
            for cid, d in out.items():
                sd = d.std(ddof=1) if len(d) > 1 else float("nan")
                print(f"    {cid}: {len(d)}, {d.mean():.1f}, {sd:.1f}")


if __name__ == "__main__":
    main()
