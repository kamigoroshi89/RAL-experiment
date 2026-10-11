import time, pickle
from lib import *
Z = lambda n: {n: dict(value=0.0, dist=None)}
NOAMP = Z("circadian_amplitude_mmhg"); NODRUG = Z("emax_mmhg"); NOAR = Z("ar_noise_sd_mmhg"); NOCUFF = {"cuff_error_sd_mmhg": dict(value=0.001, dist=None)}  # 0.001 mmHg: exactly 0 makes the bias magnitudes resolve to zero (builder refuses)
FIXB = {"baseline_sbp_mmhg": dict(value=149.3, dist=None)}
PERF = {"p_delay": dict(value=0.0), "p_omission": dict(value=0.0), "p_double_take": dict(value=0.0)}
def m(*ds):
    o = {}
    for d in ds: o.update(d)
    return o
specs = {
 "full": {},
 "baseline_only": dict(prior=m(NOAMP, NODRUG, NOAR, NOCUFF)),
 "base+circ": dict(prior=m(NODRUG, NOAR, NOCUFF)),
 "base+drug": dict(prior=m(NOAMP, NOAR, NOCUFF)),
 "base+AR": dict(prior=m(NOAMP, NODRUG, NOCUFF)),
 "base+cuff": dict(prior=m(NOAMP, NODRUG, NOAR)),
 "base+circ+drug": dict(prior=m(NOAR, NOCUFF)),
 "base+circ+drug+AR (no cuff)": dict(prior=m(NOCUFF)),
 "full-no-AR": dict(prior=m(NOAR)),
 "full-no-circ": dict(prior=m(NOAMP)),
 "full-no-drug": dict(prior=m(NODRUG)),
 "full-fixed-baseline-149.3": dict(prior=m(FIXB)),
 "full-perfect-adherence": dict(prior=m(PERF)),
 "base+circ+drug perfect adh (no AR,cuff)": dict(prior=m(NOAR, NOCUFF, PERF)),
 "base+drug perfect adh (no circ,AR,cuff)": dict(prior=m(NOAMP, NOAR, NOCUFF, PERF)),
}
t = time.time()
out = run_many(specs, n_patients=400, with_alarms=True, chunk=10)
print("time", time.time() - t)
res = {}
for n, v in out.items():
    if v is None: continue
    R, D = v
    res[n] = summarize(R, D)
pickle.dump({n: (np.array(v[0]), v[1]) for n, v in out.items() if v is not None}, open("exp1_raw.pkl", "wb"))
json.dump(res, open("exp1.json", "w"), indent=1)
for n, s in res.items():
    print(f"{n:45s} out={s['p_out']:.3f} ab={s['p_above']:.3f} be={s['p_below']:.3f} slots={[round(x,3) for x in s['p_out_slot']]} mean={[round(x,1) for x in s['mean_slot']]} B1={s['p_b1']:.3f} B3={s['p_b3']:.3f}")
