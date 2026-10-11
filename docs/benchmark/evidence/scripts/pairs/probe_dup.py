import sys
sys.path.insert(0, "/tmp/research/pairs/scripts"); sys.path.insert(0, "/tmp/research/pairs/repo_g4/src"); sys.path.insert(0, "/tmp/research/pairs/repo_g4")
import mkcfg
cfg = mkcfg.mk("pd", n_patients=1, pairs=2, g4=True)
from ralmon.benchmark.builder import BuildContext
from ralmon.eval import OursDetector
from ralmon.eval.ours import PipelineComponents
from ralmon.monitor import MonitorConfig
from ralmon.spec import load_registry, load_templates
sys.argv=["x","1","pd"]
import probe_pairs as P
ctx = BuildContext.create(cfg, allow_fixture_only=True)
reg = load_registry(P.REG, step_ms=60000, allow_fixture_only=True); tpl = load_templates(registry=reg)
mc = MonitorConfig(60000, 0, False, None, "likely", reg.version())
units = ctx.pair_units(); first = ctx.config.total_patients
from ralmon.signals import EventKind
for number,(pid,g,v,o) in enumerate(units):
    if v.variant_id not in ("naive_noauth_content","informed_noauth_content") or o!=0: continue
    a,b = ctx.build_pair(pid,g,v,first+number,o)
    for built in (a,b):
        day=built.days[0].observed
        print(v.variant_id, built.extra["member"], [(e.t_device_ms//60000, e.seq, dict(e.payload)) for e in day.events if e.kind is EventKind.DISPENSE])
        det = OursDetector(mc, reg, tpl, components=PipelineComponents(use_forecaster=False), profile=P.profile(False)); det.fit([],[])
        al = det.run(day, built.plan, None)
        print("   rejected:", det.last_run.rejected_inputs[:5], "alerts", [(x.tau.value,x.kappa.value) for x in al if x.tau.value in ("count","resp","int")])
