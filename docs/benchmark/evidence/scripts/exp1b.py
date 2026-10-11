import time, pickle, itertools
from lib import *
Z = lambda n: {n: dict(value=0.0, dist=None)}
OFF = {"circ": Z("circadian_amplitude_mmhg"), "drug": Z("emax_mmhg"), "AR": Z("ar_noise_sd_mmhg"), "cuff": {"cuff_error_sd_mmhg": dict(value=0.001, dist=None)}}
comps = list(OFF)
specs = {}
for r in range(5):
    for on in itertools.combinations(comps, r):
        pr = {}
        for c in comps:
            if c not in on: pr.update(OFF[c])
        specs["+".join(on) or "baseline"] = dict(prior=pr)
out = run_many(specs, n_patients=400, with_alarms=False, chunk=20)
res = {n: summarize(*v) for n, v in out.items() if v is not None}
json.dump(res, open("exp1b.json", "w"), indent=1)
for n, s in res.items(): print(f"{n:25s} out={s['p_out']:.4f} slots={[round(x,3) for x in s['p_out_slot']]}")
