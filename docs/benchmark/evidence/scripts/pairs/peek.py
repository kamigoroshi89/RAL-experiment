import sys, time, json
sys.path.insert(0, "/tmp/research/pairs/scripts")
import mkcfg
cfg = mkcfg.mk("t1", n_patients=1, pairs=40)
sys.path.insert(0, "/tmp/research/pairs/repo/src")
from ralmon.benchmark.builder import BuildContext
ctx = BuildContext.create(cfg, allow_fixture_only=True)
units = ctx.pair_units()
first = ctx.config.total_patients
n=0
for number,(pid,g,v,o) in enumerate(units):
    if v.variant_id!="naive_robot_auth": continue
    a,b = ctx.build_pair(pid,g,v,first+number,o)
    t=a.days[0].truth
    inj=[x for x in t.ground_truth if x.injected]
    print(o, "inj", len(inj), "n_gt", len(t.ground_truth), [ (x.cls.value,x.subtype) for x in inj][:3])
    if not inj and n<2:
        n+=1
        print(type(t)); print(t.injection_log)
        for x in t.ground_truth: print(x)
        print([f for f in t.__dataclass_fields__])
    if o>12: break
