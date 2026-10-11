"""Real builder pieces on N pairs per variant (19 committed variants). Rows to /tmp/research/pairs/rows_<tag>.jsonl"""
import sys, json, time, os
from multiprocessing import Pool
sys.path.insert(0, "/tmp/research/pairs/scripts")
N = int(sys.argv[1]); TAG = sys.argv[2]
import mkcfg
CFG = mkcfg.mk(f"p{TAG}", n_patients=1, pairs=N)
sys.path.insert(0, "/tmp/research/pairs/repo/src")
from ralmon.benchmark.builder import BuildContext
from ralmon.benchmark.confounders import evaluate_pair

def work(args):
    lo, hi = args
    ctx = BuildContext.create(CFG, allow_fixture_only=True)
    units = ctx.pair_units()
    first = ctx.config.total_patients
    out = []
    ndoses = len(ctx.schedule.dose_ticks_ms)
    for number in range(lo, hi):
        pid, group, variant, ordinal = units[number]
        pi = first + number
        t0 = time.time()
        a, b = ctx.build_pair(pid, group, variant, pi, ordinal)
        dt = time.time() - t0
        # evaluate_pair for separated_by (same base as build_pair uses for member A)
        import dataclasses
        from ralmon.benchmark.rng import stream, StreamPurpose
        shared = ctx.cohorts[ctx.config.cohorts[0].id].prior.sample_patient(
            stream(ctx.config.generation_seed, pi, None, StreamPurpose.PATIENT), pi)
        ids = dict(zip(("A","B"), ctx.planned_ids()[1][number], strict=True))
        base = ctx.pair_base(dataclasses.replace(shared, patient_id=ids["A"]), pi, ordinal)
        ev = evaluate_pair(group, variant, base)
        row = dict(group=group, variant=variant.variant_id, ordinal=ordinal, number=number, dose_index=ordinal % ndoses,
                   flag=ev.indistinguishable_by_construction, separated_by=list(ev.separated_by),
                   expected=variant.expected_indistinguishable, secs=dt)
        for built in (a, b):
            m = built.extra["member"]
            t = built.days[0].truth
            inj = [g for g in t.ground_truth if g.injected]
            row[m] = dict(
                n_inj_events=len(inj),
                inj_events=[(g.cls.value, g.subtype, g.template_id, g.onset_ms, g.end_ms) for g in inj],
                records=[(e["cls"], e["subtype"], e["realised"], e["onset_ms"], len(e["truth_indices"]), len(e["explains_in_later_days"])) for e in t.injection_log],
                n_gt=len(t.ground_truth),
                tail_closing=None,
            )
        out.append(row)
    return out

if __name__ == "__main__":
    ctx = BuildContext.create(CFG, allow_fixture_only=True)
    total = len(ctx.pair_units())
    chunk = 40
    jobs = [(i, min(i+chunk, total)) for i in range(0, total, chunk)]
    t = time.time()
    with Pool(28) as p, open(f"/tmp/research/pairs/rows_{TAG}.jsonl", "w") as f:
        for res in p.imap_unordered(work, jobs):
            for r in res: f.write(json.dumps(r) + "\n")
    print("done", total, time.time() - t)
