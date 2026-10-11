import time, pickle
from lib import *
specs = {f"peak{h:02d}": dict(design={"circadian_peak_clock_ms": h*H}) for h in range(0, 24, 2)}
specs["peak_none(A=0)"] = dict(prior={"circadian_amplitude_mmhg": dict(value=0.0, dist=None)})
t = time.time()
out = run_many(specs, n_patients=300, with_alarms=True, chunk=10)
print("time", time.time() - t)
res = {n: summarize(*v) for n, v in out.items() if v is not None}
# also component mean per slot for decomposition
json.dump(res, open("exp2.json", "w"), indent=1)
pickle.dump({n: np.array(v[0]) for n, v in out.items() if v is not None}, open("exp2_raw.pkl", "wb"))
for n, s in res.items():
    print(f"{n:16s} out={s['p_out']:.3f} slots={[round(x,3) for x in s['p_out_slot']]} mean={[round(x,1) for x in s['mean_slot']]} B1={s['p_b1']:.3f} B3={s['p_b3']:.3f} resp/d={s['events_per_day'].get('spontaneous_resp',0):.2f} range/d={s['events_per_day'].get('spontaneous_range',0):.2f}")
