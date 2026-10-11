import sys, json
sys.path.insert(0, "/tmp/research/pairs/scripts")
import mkcfg
cfg = mkcfg.mk("g4a", n_patients=1, pairs=3, g4=True)
sys.path.insert(0, "/tmp/research/pairs/repo_g4/src")
import ralmon.benchmark.confounders as c
print(c.__file__, c.GROUPS)
from ralmon.benchmark.builder import BuildContext
ctx = BuildContext.create(cfg, allow_fixture_only=True)
units = ctx.pair_units(); print(len(units))
for pid,g,v,o in units:
    if g!="bounce_vs_forged_dispense": continue
    print(v.variant_id, v.withheld, v.attacker, v.expected_indistinguishable)
