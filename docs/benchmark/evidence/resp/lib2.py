"""Harness: real BuildContext/build_patient with in-memory (tmp-file) parameter overrides.
Nothing in the repository is modified; configs are written under /tmp/research/resp/tmp_*/.
Fault-free: injection rates 0, no pairs. Registry 0.2.1 (committed), band 110-140.
Design rows still empty are filled with FIXTURE values (test_builder.GENERATOR_VALUES) unless overridden;
mean_delay_ms stand-in 20 min unless overridden. These are SENSITIVITY / stand-in values, not proposals."""
import os, sys, pathlib, copy, hashlib, bisect, json
sys.dont_write_bytecode = True
ROOT = pathlib.Path("/tmp/research/resp/repo")
sys.path.insert(0, str(ROOT))
import yaml, numpy as np
import tests.benchmark.test_builder as tb
pass
from ralmon.benchmark.builder import BuildContext, load_config
from ralmon.benchmark.priors import LiteraturePriorSource
from ralmon.benchmark.latent import circadian
from ralmon.benchmark.pkpd import OneCompartmentEmax, intake_times_from_events
from ralmon.baselines import B1StaticThresholds, B3PlainSTL
from ralmon.baselines.base import TimingConfig

H = 3_600_000
MIN = 60_000
DAY = 86_400_000
LO, HI = 110.0, 140.0
TICKS_MIN = [375, 495, 855, 1215, 1335]  # 06:15 08:15 14:15 20:15 22:15
SLOT_NAMES = ["06:15", "08:15", "14:15", "20:15", "22:15"]

DEFAULT_DESIGN = dict(tb.GENERATOR_VALUES)  # fixture-only values of the empty rows
DEFAULT_MEAN_DELAY = 1_200_000  # stand-in 20 min
B3_N = int(os.environ.get('B3_N', '20'))  # B3 (slow STL) only on the first B3_N patients of a run; B1 on all


def make_ctx(tag, prior_over=None, design_over=None, mean_delay=DEFAULT_MEAN_DELAY, n_patients=400, n_days=7):
    prior_over = prior_over or {}
    design_over = design_over or {}
    h = hashlib.md5(json.dumps([tag, prior_over, design_over, mean_delay], sort_keys=True, default=str).encode()).hexdigest()[:10]
    tmp = pathlib.Path(f"/tmp/research/resp/tmp_{os.getpid()}_{h}")
    tmp.mkdir(parents=True, exist_ok=True)
    doc = yaml.safe_load((ROOT / "configs/priors/literature_hypertension.yaml").read_text())
    for r in doc["parameters"]:
        if r["parameter"] == "mean_delay_ms":
            r.update(value=int(mean_delay), status="filled", source_ref="SENSITIVITY stand-in (research script)",
                     source_type="design_choice", rationale="stand-in", verified_by=None)
        if r["parameter"] in prior_over:
            r.update(prior_over[r["parameter"]])
    pp = tmp / "prior_standin.yaml"
    pp.write_text(yaml.safe_dump(doc, sort_keys=False))
    # design rows: fixture values + overrides, written by the test helper then patched
    saved = dict(tb.GENERATOR_VALUES)
    tb.GENERATOR_VALUES.update(design_over)
    try:
        cd = tb.config_document(tmp, prior=pp, n_patients=n_patients, n_days=n_days, pairs=0, variants=[],
                                rates=(0.0, 0.0, 0.0))
    finally:
        tb.GENERATOR_VALUES.clear(); tb.GENERATOR_VALUES.update(saved)
    cd["paths"]["registry"] = str(ROOT / "configs/registry/hypertension.yaml")
    cfg = load_config(tb.write_config(tmp, cd))
    prior = LiteraturePriorSource(pp, strict=False, allow_fixture_only=True)
    return BuildContext.create(cfg, prior, allow_fixture_only=True)


_EFF = OneCompartmentEmax()


def patient_readings(ctx, idx, with_alarms=False, b1=None, b3=None):
    """Return (reading rows, day rows) for one patient. Reading row:
    idx, day, slot, t_clock_ms, obs, latent, base, circ, effect, ar, cuff_err."""
    params = ctx.draw_patient(idx)
    bp = ctx.build_patient(params, idx)
    # all intakes (true) across all days incl. tail
    intakes = []
    for d in bp.days:
        intakes.extend(intake_times_from_events(d.truth.latent.events))
    intakes = sorted(intakes)
    peak = ctx.cohorts[ctx.config.cohorts[0].id].assembly.circadian_peak_clock_ms
    rows = []
    dayrows = []
    tstamps = []
    meta = []
    for d in bp.days:
        if d.tail:
            continue
        o = d.observed
        lat = [s for s in d.truth.latent.samples if s.signal == "bp"]
        lt = [s.t_device_ms for s in lat]
        lv = [s.value for s in lat]
        meas = [s for s in o.samples if s.signal == "bp"]
        for s in meas:
            t = s.t_device_ms
            pos = bisect.bisect_right(lt, t) - 1
            L = lv[pos]
            clock = t % DAY
            slot = int(np.argmin([abs(clock / MIN - m) for m in TICKS_MIN]))
            meta.append((o.day_index, slot, t, clock, s.value, L))
        cnt = {}
        for e in d.truth.ground_truth:
            cnt[e.subtype] = cnt.get(e.subtype, 0) + 1
        nout = sum((s.value < LO) or (s.value > HI) for s in meas)
        a1 = a3 = -1
        if with_alarms:
            a1 = len(b1.run(o, bp.plan)); a3 = len(b3.run(o, bp.plan)) if idx < B3_N else -1
        dayrows.append(dict(idx=idx, day=o.day_index, n=len(meas), nout=int(nout), a1=a1, a3=a3, counts=cnt,
                            n_intake=sum(1 for e in d.truth.latent.events if e.kind.name == "INTAKE")))
    if meta:
        order = np.argsort([m[2] for m in meta])
        meta = [meta[i] for i in order]
        tg = [m[2] for m in meta]
        eff = np.array(_EFF.effect_mmhg(params, intakes, tg)) if intakes else np.zeros(len(tg))
        tarr = np.array(tg, dtype=np.int64)
        circ = circadian(tarr, params.circadian_amplitude_mmhg, int(peak))
        for j, m in enumerate(meta):
            day, slot, t, clock, obs, L = m
            base = params.baseline_sbp_mmhg
            ar = L - (base + circ[j] - eff[j])
            rows.append((idx, day, slot, clock, obs, L, base, circ[j], eff[j], ar, obs - L))
    return rows, dayrows


def baselines(ctx):
    reg = ctx.registry
    T = TimingConfig(60000, 0, 3_600_000)
    b1 = B1StaticThresholds(timing=T, registry=reg); b1.fit([], [])
    b3 = B3PlainSTL(tuple(ctx.templates), reg, timing=T); b3.fit([], [])
    return b1, b3


def summarize(rows, dayrows):
    """rows: array N x 11 ; dayrows: list of dicts"""
    a = np.array(rows, dtype=float)
    out = {}
    obs = a[:, 4]
    outb = (obs < LO) | (obs > HI)
    out["n_readings"] = len(a)
    out["p_out"] = float(outb.mean())
    out["p_above"] = float((obs > HI).mean())
    out["p_below"] = float((obs < LO).mean())
    out["p_out_slot"] = [float(outb[a[:, 2] == s].mean()) for s in range(5)]
    out["mean_slot"] = [float(obs[a[:, 2] == s].mean()) for s in range(5)]
    out["mean_all"] = float(obs.mean())
    nd = len(dayrows)
    out["n_days"] = nd
    out["p_day_any_out"] = float(np.mean([d["nout"] > 0 for d in dayrows]))
    if dayrows[0]["a1"] >= 0:
        out["p_b1"] = float(np.mean([d["a1"] > 0 for d in dayrows]))
        d3 = [d for d in dayrows if d["a3"] >= 0]
        out["p_b3"] = float(np.mean([d["a3"] > 0 for d in d3])) if d3 else float('nan')
        out["n_b1"] = float(np.mean([d["a1"] for d in dayrows]))
        out["n_b3"] = float(np.mean([d["a3"] for d in d3])) if d3 else float('nan')
        out["n_b3_days"] = len(d3)
    ev = {}
    for d in dayrows:
        for k, v in d["counts"].items():
            ev[k] = ev.get(k, 0) + v
    out["events_per_day"] = {k: v / nd for k, v in sorted(ev.items())}
    out["p_day_no_event"] = float(np.mean([len(d["counts"]) == 0 for d in dayrows]))
    return out


def _worker(args):
    try:
        return _worker0(args)
    except Exception as e:
        import traceback
        return ("ERR", args[0], traceback.format_exc()[-1500:])


def _worker0(args):
    tag, prior_over, design_over, mean_delay, idxs, with_alarms = args
    ctx = make_ctx(tag, prior_over, design_over, mean_delay, n_patients=400)
    b1 = b3 = None
    if with_alarms:
        b1, b3 = baselines(ctx)
    R = []; D = []
    for i in idxs:
        r, d = patient_readings(ctx, i, with_alarms, b1, b3)
        R.extend(r); D.extend(d)
    return R, D


def run_cohort(tag, prior_over=None, design_over=None, mean_delay=DEFAULT_MEAN_DELAY, n_patients=100,
               with_alarms=False, pool=None, chunk=None):
    idxs = list(range(n_patients))
    chunk = chunk or max(1, n_patients // 16)
    chunks = [idxs[i:i + chunk] for i in range(0, n_patients, chunk)]
    args = [(tag, prior_over or {}, design_over or {}, mean_delay, c, with_alarms) for c in chunks]
    if pool is None:
        res = [_worker(a) for a in args]
    else:
        res = pool.map(_worker, args)
    R = [r for x in res for r in x[0]]
    D = [d for x in res for d in x[1]]
    return R, D


def run_many(specs, n_patients=100, with_alarms=False, chunk=None, procs=30):
    """specs: dict name -> dict(prior=..., design=..., mean_delay=...). Returns name -> (R, D)."""
    import multiprocessing as mp; Pool = mp.get_context("fork").Pool
    chunk = chunk or max(1, min(10, n_patients // 4))
    tasks = []; owner = []
    for name, sp in specs.items():
        idxs = list(range(n_patients))
        for i in range(0, n_patients, chunk):
            tasks.append((name, sp.get("prior", {}), sp.get("design", {}), sp.get("mean_delay", DEFAULT_MEAN_DELAY),
                          idxs[i:i + chunk], with_alarms))
            owner.append(name)
    with Pool(procs) as p:
        res = p.map(_worker, tasks, chunksize=1)
    out = {n: ([], []) for n in specs}
    for n, r in zip(owner, res):
        if isinstance(r, tuple) and len(r) == 3 and r[0] == "ERR":
            print("ERROR in", n, r[2]); out[n] = None; continue
        if out[n] is None: continue
        out[n][0].extend(r[0]); out[n][1].extend(r[1])
    return out
