import sys, os, time
os.environ["RALMON_DRIVER_DIAG"] = sys.argv[1] if len(sys.argv) > 1 else "1"
import common, mkcfg
CFG = mkcfg.mk("pilot", n_patients=1, pairs=2, g4=True)
from ralmon.benchmark.builder import BuildContext
from ralmon.monitor import run_offline_detailed
from ralmon.attribution.extract import extract_evidence
from ralmon.attribution.rule import HierarchicalRule
reg, tpl, cfg = common.load()
ctx = BuildContext.create(CFG, allow_fixture_only=True)
units = ctx.pair_units(); first = ctx.config.total_patients
print(len(units))
t=time.time()
for number in (0, 9, 30, 60):
    pid, g, v, o = units[number]
    a, b = ctx.build_pair(pid, g, v, first + number, o)
    print(number, g, v.variant_id, "build s", round(time.time()-t,2))
    for built in (a, b):
        day = built.days[0].observed
        res = run_offline_detailed(day, built.plan, cfg, None, None, registry=reg, templates=tpl)
        recs = res.records
        ev = extract_evidence(day, recs, reg, step_ms=60000, reorder_delay_ms=cfg.reorder_delay_ms, profile=common.profile(False, True), plan=built.plan)
        rule = HierarchicalRule(reg)
        print(" member", built.extra["member"], "n events", len(day.events), "n diag", sum(1 for e in day.events if "diagnostics" in e.payload))
        for k, e in list(ev.items())[:4]:
            print("   ", k, e.provenance.violated_template.value, e.system.diagnostics_ok, e.system.liveliness_ok, rule.decide(None, e).kappa.value)
