import time, pickle
from lib import *
E0, EC0, B0, S0 = 17.3, 0.76, 149.3, 9.0
def bl(mean, sd):
    if sd == 0: return {"baseline_sbp_mmhg": dict(value=float(mean), dist=None)}
    return {"baseline_sbp_mmhg": dict(value=None, dist={"family": "normal", "mean": float(mean), "sd": float(sd),
                                                       "truncate": {"lo": float(mean - 3*sd), "hi": float(mean + 3*sd)}})}
specs = {}; meta = {}
specs["committed"] = {}; meta["committed"] = dict(grp="ref")
for m in [0.5, 0.75, 1.25, 1.5, 2, 2.5, 3]:
    n = f"emax x{m}"; specs[n] = dict(prior={"emax_mmhg": dict(value=E0*m)}); meta[n] = dict(grp="emax", m=m)
for m in [0.1, 0.25, 0.5, 2, 4]:
    n = f"ec50 x{m}"; specs[n] = dict(prior={"ec50": dict(value=EC0*m)}); meta[n] = dict(grp="ec50", m=m)
for me in [1.5, 2, 3]:
    for mc in [0.25, 0.5]:
        n = f"emax x{me} ec50 x{mc}"; specs[n] = dict(prior={"emax_mmhg": dict(value=E0*me), "ec50": dict(value=EC0*mc)}); meta[n] = dict(grp="emax_ec50", m=me, mc=mc)
for sh in [-30, -25, -20, -15, -10, -5, 0]:
    for sd in [0, 4.5, 9.0, 13.5]:
        if sh == 0 and sd == 9.0: continue
        n = f"base shift {sh} sd {sd}"; specs[n] = dict(prior=bl(B0 + sh, sd)); meta[n] = dict(grp="base", shift=sh, sd=sd)
# joint (a)+(b)
for me in [1.5, 2, 3]:
    for sh in [-30, -25, -20, -15, -10, -5]:
        n = f"joint emax x{me} shift {sh} sd 9"; specs[n] = dict(prior={**bl(B0 + sh, 9.0), "emax_mmhg": dict(value=E0*me)}); meta[n] = dict(grp="joint", m=me, shift=sh, sd=9.0)
# floors
Z = lambda n: {n: dict(value=0.0, dist=None)}
specs["floor: const 125, no circ, no drug, AR+cuff only"] = dict(prior={**bl(125, 0), **Z("circadian_amplitude_mmhg"), **Z("emax_mmhg")}); meta["floor: const 125, no circ, no drug, AR+cuff only"] = dict(grp="floor")
specs["floor: const 125, no drug, circ+AR+cuff"] = dict(prior={**bl(125, 0), **Z("emax_mmhg")}); meta["floor: const 125, no drug, circ+AR+cuff"] = dict(grp="floor")
specs["floor: SD9 mean 125, no circ, no drug"] = dict(prior={**bl(125, 9.0), **Z("circadian_amplitude_mmhg"), **Z("emax_mmhg")}); meta["floor: SD9 mean 125, no circ, no drug"] = dict(grp="floor")
t = time.time()
out = run_many(specs, n_patients=200, with_alarms=True, chunk=20)
print("time", time.time() - t)
res = {n: summarize(*v) for n, v in out.items() if v is not None}
pickle.dump(dict(res=res, meta=meta, raw={n: np.array(v[0]) for n, v in out.items() if v is not None}, days={n: v[1] for n, v in out.items() if v is not None}), open("exp4.pkl", "wb"))
for n, s in res.items():
    print(f"{n:48s} out={s['p_out']:.3f} mean={s['mean_all']:.1f} slots={[round(x,2) for x in s['p_out_slot']]} B1={s['p_b1']:.3f} range/d={s['events_per_day'].get('spontaneous_range',0):.2f} resp/d={s['events_per_day'].get('spontaneous_resp',0):.2f}")
