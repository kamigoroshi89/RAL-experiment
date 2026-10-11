"""Monitor-only (no forecaster) + RuleAttributor on the day-0 observed days of pair members (research registry, probe profile)."""
import sys, json, time, dataclasses
sys.path.insert(0, "/tmp/research/pairs/scripts")
N = int(sys.argv[1]); TAG = sys.argv[2]
import mkcfg
CFG = mkcfg.mk(f"pr{TAG}", n_patients=1, pairs=N, g4=True)
sys.path.insert(0, "/tmp/research/pairs/repo_g4/src"); sys.path.insert(0, "/tmp/research/pairs/repo_g4")
from multiprocessing import Pool
from collections import Counter, defaultdict
from ralmon.benchmark.builder import BuildContext
from ralmon.eval import OursDetector
from ralmon.eval.ours import PipelineComponents
from ralmon.monitor import MonitorConfig
from ralmon.spec import load_registry, load_templates
from ralmon.attribution.extract import DeviceCapabilities, DeviceProfile
REG = "/tmp/research/pairs/research_registry.yaml"
CUFF = DeviceCapabilities(status_reports=True, supervised=True, diagnostics=True, seq=True, two_clocks=True, authenticates=False, error_codes=True, deadline_ms=12*3600*1000)
def profile(auth):
    return DeviceProfile({"cuff": CUFF,
        "dispenser": DeviceCapabilities(status_reports=True, supervised=True, seq=True, two_clocks=True, authenticates=auth),
        "robot": DeviceCapabilities(status_reports=True, supervised=True, battery=True)})
def work(args):
    lo, hi = args
    ctx = BuildContext.create(CFG, allow_fixture_only=True)
    reg = load_registry(REG, step_ms=60000, allow_fixture_only=True); tpl = load_templates(registry=reg)
    cfg = MonitorConfig(60000, 0, False, None, "likely", reg.version())
    units = ctx.pair_units(); first = ctx.config.total_patients
    out = []
    for number in range(lo, hi):
        pid, g, v, o = units[number]
        a, b = ctx.build_pair(pid, g, v, first + number, o)
        auth = ("verification" not in v.withheld) and g in ("nonresponse_vs_falsified_dispense", "bounce_vs_forged_dispense")
        row = dict(group=g, variant=v.variant_id, ordinal=o, dose=o % len(ctx.schedule.dose_ticks_ms), tick_idx=o % len(ctx.schedule.measurement_ticks_ms))
        for built in (a, b):
            m = built.extra["member"]
            det = OursDetector(cfg, reg, tpl, components=PipelineComponents(use_forecaster=False), profile=profile(auth))
            det.fit([], [])
            day = built.days[0].observed
            alerts = det.run(day, built.plan, None)
            truth = built.days[0].truth
            inj = [(e.cls.value, e.subtype, e.template_id) for e in truth.ground_truth if e.injected]
            row[m] = dict(inj=inj, alerts=[(al.tau.value, al.xi.instance_key, al.kappa.value, al.verdict.value, al.t_ms) for al in alerts])
        out.append(row)
    return out
if __name__ == "__main__":
    ctx = BuildContext.create(CFG, allow_fixture_only=True)
    total = len(ctx.pair_units()); chunk = 20
    jobs = [(i, min(i + chunk, total)) for i in range(0, total, chunk)]
    t = time.time()
    with Pool(28) as p, open(f"/tmp/research/pairs/probe_{TAG}.jsonl", "w") as f:
        for res in p.imap_unordered(work, jobs):
            for r in res: f.write(json.dumps(r) + "\n")
    print("done", total, time.time() - t)
