"""Item 3: natural probability that two consecutive cuff readings of the same stream are exactly equal (fault-free run)."""
import sys, math, collections, statistics
sys.path.insert(0, "/tmp/research/likelihood/scripts"); sys.path.insert(0, "/tmp/research/likelihood")
import mainlib as M, common, yaml
import numpy as np
days = M.load("ff")
by = collections.defaultdict(list)
for d in days:
    by[d["patient"]] += d["bp"]
diffs = []; n_pairs = 0; n_eq = 0; vals = []
for p, s in by.items():
    s = sorted(s)
    v = [x[1] for x in s]; vals += v
    for a, b in zip(v, v[1:]):
        n_pairs += 1; n_eq += (a == b); diffs.append(b - a)
diffs = np.array(diffs)
out = []; pr = lambda *a: out.append(" ".join(str(x) for x in a))
pr(f"Fault-free run `ff` (injection rates 0, 120 patients x 30 days, seed 0): {len(vals)} cuff readings, {n_pairs} consecutive pairs, **exactly equal: {n_eq}** (observed frequency {n_eq/n_pairs:.4f}).")
pr(f"Share of readings that are integers: {np.mean([abs(v-round(v))<1e-9 for v in vals]):.4f}; smallest non-zero |difference| between consecutive readings: {np.min(np.abs(diffs[diffs!=0])):.3g} mmHg; readings at the clip bounds: min {min(vals):.2f}, max {max(vals):.2f}, share equal to the min or max: {np.mean([v in (min(vals), max(vals)) for v in vals]):.4f}.")
sd_d = float(np.std(diffs))
pr(f"SD of the difference of consecutive readings: {sd_d:.2f} mmHg (median |difference| {np.median(np.abs(diffs)):.2f}).")
# analytic: cuff noise SD from the prior file
pri = yaml.safe_load(open("/tmp/research/likelihood/repo/configs/priors/literature_hypertension.yaml"))
sd_e = None
for r in pri["parameters"]:
    if r["parameter"] == "cuff_error_sd_mmhg":
        sd_e = r.get("value"); src = (r.get("source_ref"), r.get("status"))
pr(f"Generator measurement process: bp = latent SBP + cuff_bias + cuff_error_sd * z, a float with no rounding in `measurement.py` (no resolution parameter exists); `cuff_error_sd_mmhg` in the prior file = {sd_e} ({src}).")
pr("Analytic: two floats drawn from continuous noise are equal with probability 0, so **rep_nat = 0 exactly in this generator** and the fault-free frequency 0/%d agrees." % n_pairs)
pr()
pr("For a device with a display resolution r mmHg (a SENSITIVITY value: the cuff specification is not in the repository) the natural probability that two consecutive readings are equal is E[max(0, 1 - |Delta| / r)] over the difference Delta of consecutive pre-rounding readings (valid when the first reading falls uniformly in its quantisation cell). With the empirical Delta of the fault-free run and, as a cross-check, a Gaussian Delta with the same SD:")
pr("| r (mmHg) | rep_nat, empirical Delta | rep_nat, Gaussian Delta (SD %.1f) |" % sd_d); pr("|---|---|---|")
rs = {}
for r in (0.1, 1.0, 2.0, 5.0):
    emp = float(np.mean(np.maximum(0, 1 - np.abs(diffs) / r)))
    g = np.random.default_rng(0).normal(0, sd_d, 400000); gau = float(np.mean(np.maximum(0, 1 - np.abs(g) / r)))
    pr(f"| {r} | {emp:.4f} | {gau:.4f} |"); rs[r] = emp
open(f"{common.ROOT}/out/xrep_nat.md", "w").write("\n".join(out))
print("\n".join(out))
import json; json.dump(rs, open(f"{common.ROOT}/out/xrep_nat.json", "w"))
