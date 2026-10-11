import sys, time
sys.path.insert(0, "/tmp/research/pairs/scripts")
import mkcfg
cfg = mkcfg.mk("t0", n_patients=1, pairs=1)
sys.path.insert(0, "/tmp/research/pairs/repo/src")
from ralmon.benchmark.builder import BuildContext
t=time.time()
ctx = BuildContext.create(cfg, allow_fixture_only=True)
print("ctx", time.time()-t)
units = ctx.pair_units(); print(len(units))
first = ctx.config.total_patients
for number,(pid,g,v,o) in enumerate(units[:3]):
    t=time.time()
    a,b = ctx.build_pair(pid,g,v,first+number,o)
    print(g,v.variant_id,time.time()-t, a.extra, len(a.days))
