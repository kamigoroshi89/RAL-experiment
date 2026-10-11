import sys
sys.path.insert(0, "/tmp/research/pairs/scripts"); sys.path.insert(0, "/tmp/research/pairs/repo_g4/src"); sys.path.insert(0, "/tmp/research/pairs/repo_g4")
import mkcfg
cfg = mkcfg.mk("pw", n_patients=1, pairs=1, g4=True)
from ralmon.benchmark.builder import BuildContext
from ralmon.eval import OursDetector
from ralmon.eval.ours import PipelineComponents
from ralmon.monitor import MonitorConfig
from ralmon.spec import load_registry, load_templates
from ralmon.attribution import HierarchicalRule
sys.argv=["x","1","pw"]
import probe_pairs as P
ctx = BuildContext.create(cfg, allow_fixture_only=True)
reg = load_registry(P.REG, step_ms=60000, allow_fixture_only=True); tpl = load_templates(registry=reg)
mc = MonitorConfig(60000, 0, False, None, "likely", reg.version())
units = ctx.pair_units(); first = ctx.config.total_patients
for number,(pid,g,v,o) in enumerate(units):
    if v.variant_id not in ("outcome_reported",): continue
    a,b = ctx.build_pair(pid,g,v,first+number,o)
    for built in (a,b):
        det = OursDetector(mc, reg, tpl, components=PipelineComponents(use_forecaster=False), profile=P.profile(False)); det.fit([],[])
        al = det.run(built.days[0].observed, built.plan, None)
        rule = HierarchicalRule(reg)
        from ralmon.attribution import extract_evidence
        ev = extract_evidence(built.days[0].observed, det.last_run.records, reg, step_ms=60000, reorder_delay_ms=0, profile=P.profile(False), plan=built.plan)
        print(built.extra["member"], [(x.tau.value, x.kappa.value) for x in al])
        for r in det.last_run.records[:0]: pass
        done=set()
        for key, vec in ev.items():
            tau = key.split("@")[0]
            if tau in done: continue
            done.add(tau)
            d = rule.decide(None, vec)
            print("  ", key, d.kappa.value, "row", d.row, d.reason, "used", d.evidence_used, "missing", d.missing)
    break
