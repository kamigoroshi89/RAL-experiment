import sys, dataclasses
sys.path.insert(0, "/tmp/research/pairs/scripts")
import mkcfg
cfg = mkcfg.mk("rw", n_patients=1, pairs=300)
sys.path.insert(0, "/tmp/research/pairs/repo/src")
from collections import Counter
from ralmon.benchmark.builder import BuildContext
from ralmon.benchmark.confounders import build_confounder_pair, realise_scenario
from ralmon.benchmark.labelling import ideal_observation
from ralmon.benchmark.rng import stream, StreamPurpose
ctx = BuildContext.create(cfg, allow_fixture_only=True)
units = ctx.pair_units(); first = ctx.config.total_patients
print("dose ticks", ctx.schedule.dose_ticks_ms, "meas ticks", ctx.schedule.measurement_ticks_ms)
cnt = Counter()
D1, D2, DR = 3_600_000, 7_200_000, 7.5
for number,(pid,g,v,o) in enumerate(units):
    if v.variant_id!="naive_robot_noauth": continue
    pi = first+number
    shared = ctx.cohorts[ctx.config.cohorts[0].id].prior.sample_patient(stream(ctx.config.generation_seed, pi, None, StreamPurpose.PATIENT), pi)
    ids = dict(zip(("A","B"), ctx.planned_ids()[1][number], strict=True))
    base = ctx.pair_base(dataclasses.replace(shared, patient_id=ids["A"]), pi, o)
    a,_ = build_confounder_pair(g, v, base)
    ra = realise_scenario(a, base)
    obs = ideal_observation(ra.latent.latent, "x")
    bp = sorted((s.t_device_ms, s.value) for s in obs.samples if s.signal=="bp")
    d = ctx.schedule.dose_ticks_ms[base.dose_index]
    pre = [x for x in bp if x[0] < d]
    inwin = [x for x in bp if d + D1 <= x[0] <= d + D2]
    key = ("dose%d"%base.dose_index)
    if not pre: cnt[key,"no_pre"]+=1; continue
    ok = any(pre[-1][1]-x[1] >= DR for x in inwin)
    cnt[key, "n_in_window=%d"%len(inwin), "spont_ok" if ok else "violated"] += 1
for k,v in sorted(cnt.items()): print(k,v)
