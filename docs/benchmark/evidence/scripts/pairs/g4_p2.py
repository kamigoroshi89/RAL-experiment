import sys, dataclasses
sys.path.insert(0, "/tmp/research/pairs/scripts")
import mkcfg
cfg = mkcfg.mk("g4p2", n_patients=1, pairs=30, g4=True)
sys.path.insert(0, "/tmp/research/pairs/repo_g4/src")
from collections import Counter, defaultdict
from ralmon.benchmark.builder import BuildContext
from ralmon.benchmark.confounders import evaluate_pair
from ralmon.benchmark.rng import stream, StreamPurpose
ctx = BuildContext.create(cfg, allow_fixture_only=True)
units = ctx.pair_units(); first = ctx.config.total_patients
res=defaultdict(Counter)
for number,(pid,g,v,o) in enumerate(units):
    if g!="bounce_vs_forged_dispense": continue
    pi=first+number
    shared = ctx.cohorts[ctx.config.cohorts[0].id].prior.sample_patient(stream(ctx.config.generation_seed, pi, None, StreamPurpose.PATIENT), pi)
    ids = dict(zip(("A","B"), ctx.planned_ids()[1][number], strict=True))
    base = ctx.pair_base(dataclasses.replace(shared, patient_id=ids["A"]), pi, o)
    ev = evaluate_pair(g, v, base)
    res[v.variant_id][(ev.indistinguishable_by_construction, ev.separated_by)]+=1
for k,c in res.items(): print(k, dict(c))
