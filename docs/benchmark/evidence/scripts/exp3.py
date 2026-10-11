"""Sensitivity to the empty / weakly sourced design rows. RANGES ARE SENSITIVITY RANGES, NOT PROPOSALS."""
import time, pickle, sys
from lib import *
from scipy.stats import qmc
# name: (kind, lo, hi) ; kind 'design' / 'delay' / 'prior' ; vitals_period discrete
FACT = {
 "circadian_peak_clock_ms": ("design", 8*H, 18*H),
 "intake_lag_ms": ("design", 0, 10*MIN),
 "double_take_gap_ms": ("design", 11*MIN, 120*MIN),
 "mean_delay_ms": ("delay", 5*MIN, 120*MIN),
 "vitals_period_ms": ("vit", None, None),
 "robot_dwell_ms": ("design", 1*MIN, 30*MIN),
 "inflation_ms_nominal": ("design", 20000, 50000),
 "inflation_ms_sd": ("design", 0, 14000),
 "pulse_error_sd_bpm": ("design", 1.0, 6.0),
 "ble_dropout_rate_per_h": ("prior", 0.0, 0.167),
}
VIT = [60000, 300000, 900000, 1800000]
names = list(FACT)
def build(u):
    sp = {"design": {}, "prior": {}}
    for x, n in zip(u, names):
        k, lo, hi = FACT[n]
        if k == "vit":
            v = VIT[min(int(x*4), 3)]; sp["design"][n] = v
        elif k == "design":
            v = lo + x*(hi-lo)
            sp["design"][n] = float(v) if n == "pulse_error_sd_bpm" else int(round(v))
        elif k == "delay":
            sp["mean_delay"] = int(round(np.exp(np.log(lo) + x*(np.log(hi)-np.log(lo)))))   # log-uniform
        elif k == "prior":
            sp["prior"][n] = dict(value=float(lo + x*(hi-lo)))
    return sp
NP = int(sys.argv[1]) if len(sys.argv) > 1 else 60
specs = {}; U = {}
mid = np.full(len(names), 0.5)
specs["centre_fixture"] = {}   # the fixture-default configuration (as in the fault-free run)
U["centre_fixture"] = None
# OAT: each factor at 5 levels, others at fixture defaults
for i, n in enumerate(names):
    for q in [0.0, 0.25, 0.5, 0.75, 1.0]:
        u = np.full(len(names), np.nan); u[i] = q
        sp = {"design": {}, "prior": {}}
        full = build(np.where(np.isnan(u), 0.5, u))
        # only the varied factor is overridden
        k = FACT[n][0]
        if k in ("design", "vit"): sp["design"][n] = full["design"][n]
        elif k == "delay": sp["mean_delay"] = full["mean_delay"]
        else: sp["prior"][n] = full["prior"][n]
        if n == "intake_lag_ms":
            sp["design"]["double_take_gap_ms"] = max(120000, sp["design"]["intake_lag_ms"] + 60000)
        specs[f"OAT|{n}|{q}"] = sp
        U[f"OAT|{n}|{q}"] = (n, q)
# LHS joint design
S = qmc.LatinHypercube(d=len(names), seed=20261011).random(240)
for j in range(240):
    specs[f"LHS|{j}"] = build(S[j]); U[f"LHS|{j}"] = S[j]
t = time.time()
out = run_many(specs, n_patients=NP, with_alarms=True, chunk=max(1, NP // 2))
print("time", time.time() - t)
res = {n: summarize(*v) for n, v in out.items() if v is not None}
pickle.dump(dict(res=res, U=U, names=names, specs=specs), open(f"exp3_{NP}.pkl", "wb"))
print(len(res), "runs ok of", len(specs))
