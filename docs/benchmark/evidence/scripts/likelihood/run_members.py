"""Rebuild the 27 variants x N pairs (same configuration and seeds as /tmp/research/pairs/runs/prp40), run the measured-only
monitor on day 0 of each member and store, per member, the VerdictRecord and the EvidenceVector of every violated
instance under the two device profiles ('driver with diagnostics' / 'without diagnostics').
Usage: run_members.py N TAG DIAG_SWITCH   (DIAG_SWITCH 1 = generator emits driver diagnostics, 0 = does not)."""
import sys, os, time, pickle, dataclasses
N = int(sys.argv[1]); TAG = sys.argv[2]; SWITCH = sys.argv[3]
os.environ["RALMON_DRIVER_DIAG"] = SWITCH
import common, mkcfg
CFG = mkcfg.mk(f"pairs_{TAG}", n_patients=1, pairs=N, g4=True)
from multiprocessing import Pool
from ralmon.benchmark.builder import BuildContext
from ralmon.benchmark.confounders import evaluate_pair
from ralmon.benchmark.rng import stream, StreamPurpose
from ralmon.monitor import run_offline_detailed, VerdictState
from ralmon.attribution.extract import extract_evidence
from ralmon.attribution.rule import HierarchicalRule
from ralmon.signals import EventKind

def member_row(built, reg, tpl, cfg, auth, rule):
    day = built.days[0].observed
    res = run_offline_detailed(day, built.plan, cfg, None, None, registry=reg, templates=tpl)
    recs = list(res.records)
    out = {}
    for name, diag in (("on", True), ("off", False)):
        out[name] = extract_evidence(day, recs, reg, step_ms=cfg.step_ms, reorder_delay_ms=cfg.reorder_delay_ms,
                                     profile=common.profile(auth, diag), plan=built.plan)
    first = {}
    for r in recs:
        if r.state is VerdictState.VIOLATED and r.instance_key not in first:
            first[r.instance_key] = r
    alerts = []
    for key, r in first.items():
        alerts.append(dict(key=key, template=r.template.value, decided=(r.decided_at_ms if r.decided_at_ms is not None else r.t_eval_ms),
                           record=r, ev_on=out["on"].get(key), ev_off=out["off"].get(key),
                           old_on=rule.decide(r, out["on"][key]).kappa.value if key in out["on"] else None,
                           old_off=rule.decide(r, out["off"][key]).kappa.value if key in out["off"] else None))
    truth = built.days[0].truth
    disp = [(e.t_device_ms, e.payload.get("content_change")) for e in day.events if e.kind is EventKind.DISPENSE]
    return dict(
        log=[dict(cls=e["cls"], subtype=e["subtype"], realised=e["realised"], onset_ms=e["onset_ms"], end_ms=e["end_ms"],
                  templates=list(e["details"].get("templates", [])), level=e["level"], params=e["params"]) for e in truth.injection_log],
        gt=[(g.cls.value, g.subtype, g.template_id, g.onset_ms, g.end_ms, g.injected) for g in truth.ground_truth],
        alerts=alerts, dispenses=disp, n_events=len(day.events))

def work(args):
    lo, hi = args
    ctx = BuildContext.create(CFG, allow_fixture_only=True)
    reg, tpl, cfg = common.load()
    rule = HierarchicalRule(reg)
    units = ctx.pair_units(); first = ctx.config.total_patients
    out = []
    for number in range(lo, hi):
        pid, g, v, o = units[number]
        a, b = ctx.build_pair(pid, g, v, first + number, o)
        shared = ctx.cohorts[ctx.config.cohorts[0].id].prior.sample_patient(
            stream(ctx.config.generation_seed, first + number, None, StreamPurpose.PATIENT), first + number)
        ids = dict(zip(("A", "B"), ctx.planned_ids()[1][number], strict=True))
        base = ctx.pair_base(dataclasses.replace(shared, patient_id=ids["A"]), first + number, o)
        ev = evaluate_pair(g, v, base)
        auth = ("verification" not in v.withheld) and g in ("nonresponse_vs_falsified_dispense", "bounce_vs_forged_dispense")
        row = dict(group=g, variant=v.variant_id, number=number, ordinal=o, dose=o % len(ctx.schedule.dose_ticks_ms),
                   flag=ev.indistinguishable_by_construction, separated_by=list(ev.separated_by),
                   expected=v.expected_indistinguishable, auth=auth, withheld=list(v.withheld))
        for built in (a, b):
            row[built.extra["member"]] = member_row(built, reg, tpl, cfg, auth, rule)
        out.append(row)
    return out

if __name__ == "__main__":
    ctx = BuildContext.create(CFG, allow_fixture_only=True)
    total = len(ctx.pair_units()); chunk = 10
    jobs = [(i, min(i + chunk, total)) for i in range(0, total, chunk)]
    t = time.time(); rows = []
    with Pool(28) as p:
        for res in p.imap_unordered(work, jobs):
            rows.extend(res)
    rows.sort(key=lambda r: r["number"])
    with open(f"{common.ROOT}/out/pairs_{TAG}_sw{SWITCH}.pkl", "wb") as f:
        pickle.dump(rows, f)
    print("done", total, len(rows), round(time.time() - t, 1), "s")
