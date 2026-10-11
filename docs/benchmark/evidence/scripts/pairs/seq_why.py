import sys, dataclasses
sys.path.insert(0, "/tmp/research/pairs/scripts")
import mkcfg
cfg = mkcfg.mk("sw", n_patients=1, pairs=300)
sys.path.insert(0, "/tmp/research/pairs/repo/src")
from collections import Counter
from ralmon.benchmark.builder import BuildContext
from ralmon.benchmark.confounders import evaluate_pair
from ralmon.benchmark.rng import stream, StreamPurpose
from ralmon.signals import EventKind
ctx = BuildContext.create(cfg, allow_fixture_only=True)
units = ctx.pair_units(); first = ctx.config.total_patients
shown=0; kinds=Counter()
for number,(pid,g,v,o) in enumerate(units):
    if v.variant_id!="naive_norobot_noauth": continue
    pi = first+number
    shared = ctx.cohorts[ctx.config.cohorts[0].id].prior.sample_patient(stream(ctx.config.generation_seed, pi, None, StreamPurpose.PATIENT), pi)
    ids = dict(zip(("A","B"), ctx.planned_ids()[1][number], strict=True))
    base = ctx.pair_base(dataclasses.replace(shared, patient_id=ids["A"]), pi, o)
    ev = evaluate_pair(g, v, base)
    def disp(r): return [(e.t_device_ms//60000, e.seq) for e in sorted(r.observed.events, key=lambda e:e.t_device_ms) if e.kind is EventKind.DISPENSE]
    da, db = disp(ev.a), disp(ev.b)
    sa=tuple(s for _,s in da); sb=tuple(s for _,s in db)
    kinds[(base.dose_index, len(da), len(db), sa==sb)]+=1
    if sa==sb and shown<4:
        shown+=1; print(o, base.dose_index, da, db)
print(sorted(kinds.items()))
