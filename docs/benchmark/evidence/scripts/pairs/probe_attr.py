import sys, json
sys.path.insert(0, "/tmp/research/pairs/repo_g4/src"); sys.path.insert(0, "/tmp/research/pairs/repo_g4")
from collections import defaultdict, Counter
from ralmon.benchmark import open_benchmark
from ralmon.eval import OursDetector
from ralmon.eval.ours import PipelineComponents
from ralmon.monitor import MonitorConfig
from ralmon.spec import load_registry, load_templates
from ralmon.attribution.extract import DeviceCapabilities, DeviceProfile
OUT = sys.argv[1]
REGISTRY="/tmp/research/pairs/research_registry.yaml"
reg = load_registry(REGISTRY, step_ms=60000, allow_fixture_only=True)
tpl = load_templates(registry=reg)
cfg = MonitorConfig(60000, 0, False, None, "likely", reg.version())
full = open_benchmark(OUT, verify=False)
man = json.load(open(f"{OUT}/manifest.json"))
pats = {k: v for k, v in man["patients"].items() if v["role"] == "confounder_pair"}
CUFF = DeviceCapabilities(status_reports=True, supervised=True, seq=True, two_clocks=True, error_codes=True, diagnostics=True, deadline_ms=12*3600*1000)
def profile(auth):
    return DeviceProfile({"cuff": CUFF, "dispenser": DeviceCapabilities(status_reports=True, supervised=True, seq=True, two_clocks=True, authenticates=auth), "robot": DeviceCapabilities(status_reports=True, supervised=True)})
want = sys.argv[2:] 
seen = Counter()
for pid, info in sorted(pats.items()):
    vid, g, m = info["variant_id"], info["group"], info["member"]
    if want and vid not in want: continue
    if seen[(vid)] >= 2*int(1): continue
    seen[vid] += 1
    auth = "auth" in vid and "noauth" not in vid
    det = OursDetector(cfg, reg, tpl, components=PipelineComponents(use_forecaster=False), profile=profile(auth))
    det.fit([], [])
    day = full.observed(pid, 0); plan = full.care_plan(day.care_plan_id)
    alerts = det.run(day, plan, None)
    t = full.truth(pid, 0)
    inj = [(e.cls.value, e.subtype, e.onset_ms//60000, e.template_id) for e in t.ground_truth if e.injected]
    print(f"== {g} {vid} {m} id={pid} injected={inj}")
    for a in alerts:
        print("   ", a.tau.value if hasattr(a.tau,'value') else a.tau, a.xi.instance_key, a.kappa.value, a.verdict.value, a.t_ms//60000, "label", a.label.value)
