"""Main population: ordinary builder (fault-free background + injections), measured-only monitor per patient-day with the
history of the earlier days, evidence under the two device profiles, ground truth kept for the scoring code only.
Usage: run_main.py TAG N_PATIENTS N_DAYS PROFILE   (PROFILE: default | rich = authenticating dispenser + content sensing)"""
import sys, os, time, pickle, yaml
TAG, NP, ND, PROF = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
os.environ["RALMON_DRIVER_DIAG"] = "1"
import common, mkcfg
RATES = tuple(float(x) for x in os.environ.get("RALMON_RATES", "0.3,0.3,0.2").split(","))
CFG = mkcfg.mk(f"main_{TAG}", n_patients=NP, n_days=ND, pairs=0, g4=True, rates=RATES)
if PROF == "rich":
    doc = yaml.safe_load(open(CFG)); doc["device_profile"] = {"dispenser_content_sensing": True, "authenticating_devices": ["dispenser"]}
    open(CFG, "w").write(yaml.safe_dump(doc, sort_keys=False))
from multiprocessing import Pool
from ralmon.benchmark.builder import BuildContext
from ralmon.monitor import run_offline_detailed, VerdictState
from ralmon.attribution.extract import extract_evidence
from ralmon.attribution.rule import HierarchicalRule
from ralmon.signals import EventKind

def work(args):
    lo, hi = args
    ctx = BuildContext.create(CFG, allow_fixture_only=True)
    reg, tpl, cfg = common.load()
    rule = HierarchicalRule(reg)
    auth = "dispenser" in ctx.config.authenticating_devices
    H = ctx.history_days
    units = ctx.patient_units()
    out = []
    for pid, index, cohort_id in units[lo:hi]:
        params = ctx.draw_patient(index, cohort_id)
        built = ctx.build_patient(params, index, None, cohort=cohort_id)
        days = built.days
        for d in range(built.n_scored_days):
            bd = days[d]
            day = bd.observed
            hist = tuple(x.observed for x in days[max(0, d - H):d])
            kw = dict(registry=reg, templates=tpl)
            if hist: kw["history"] = hist
            res = run_offline_detailed(day, built.plan, cfg, None, None, **kw)
            recs = list(res.records)
            evs = {name: extract_evidence(day, recs, reg, step_ms=cfg.step_ms, reorder_delay_ms=cfg.reorder_delay_ms,
                                          profile=common.profile(auth, diag), plan=built.plan)
                   for name, diag in (("on", True), ("off", False))}
            first = {}
            for r in recs:
                if r.state is VerdictState.VIOLATED and r.instance_key not in first:
                    first[r.instance_key] = r
            alerts = []
            for key, r in first.items():
                alerts.append(dict(key=key, template=r.template.value,
                                   decided=(r.decided_at_ms if r.decided_at_ms is not None else r.t_eval_ms), record=r,
                                   ev_on=evs["on"].get(key), ev_off=evs["off"].get(key),
                                   old_on=rule.decide(r, evs["on"][key]).kappa.value if key in evs["on"] else None,
                                   old_off=rule.decide(r, evs["off"][key]).kappa.value if key in evs["off"] else None))
            t = bd.truth
            out.append(dict(patient=pid, day=d, alerts=alerts,
                gt=[(g.cls.value, g.subtype, g.template_id, g.onset_ms, g.end_ms, g.injected) for g in t.ground_truth],
                log=[dict(cls=e["cls"], subtype=e["subtype"], realised=e["realised"], onset_ms=e["onset_ms"], end_ms=e["end_ms"],
                          templates=list(e["details"].get("templates", [])), level=e["level"], params=e["params"]) for e in t.injection_log],
                dispenses=[(e.t_device_ms, e.payload.get("content_change")) for e in day.events if e.kind is EventKind.DISPENSE],
                bp=[(x.t_rx_ms, x.value) for x in day.samples if x.signal == "bp"],
                bp_prev=[(x.t_rx_ms, x.value) for x in days[d - 1].observed.samples if x.signal == "bp"] if d > 0 else []))
    return out

if __name__ == "__main__":
    ctx = BuildContext.create(CFG, allow_fixture_only=True)
    total = len(ctx.patient_units())
    jobs = [(i, i + 1) for i in range(total)]
    t = time.time(); rows = []
    with Pool(28) as p:
        for res in p.imap_unordered(work, jobs):
            rows.extend(res)
    rows.sort(key=lambda r: (r["patient"], r["day"]))
    pickle.dump(rows, open(f"{common.ROOT}/out/main_{TAG}.pkl", "wb"))
    print("done", total, "patients", len(rows), "days", round(time.time() - t, 1), "s")
