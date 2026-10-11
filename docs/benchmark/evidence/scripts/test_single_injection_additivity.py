"""Runnable form of the proposed test (to become tests/benchmark/test_additivity.py).

For a patient-day built (a) with no injection and (b) with exactly ONE injection forced through
PatientInjections, check the predicates P1..P7 of the report. Prints a table of failures per subtype.
Exact equality everywhere, except the pharmacokinetic tail (see PK_ENVELOPE_MMHG) and the device
sequence numbers of later messages (compared modulo a constant shift).
"""
import dataclasses, sys
from collections import Counter
sys.path.insert(0, "/tmp/research/nonadd/repo/src")
from ralmon.benchmark import builder as B
from ralmon.benchmark.builder import BuildContext, PatientInjections
from ralmon.benchmark.injection import InjectionSpec
from ralmon.benchmark.latent import T_DAY_MS
from ralmon.benchmark.measurement import LatentSbpHold
from ralmon.benchmark.rng import StreamPurpose, stream
from ralmon.benchmark.trace import InjectedClass

CFG = sys.argv[1] if len(sys.argv) > 1 else "/tmp/research/nonadd/runs/b7/configs/benchmark/default.yaml"
MIN, HOUR, DAY = 60_000, 3_600_000, T_DAY_MS
PK_SUBTYPES = ("drug_nonresponse", "double_take")
PULSE_SUBTYPES = ("hypertensive_spike", "hypotension_below_hold")
BAND = 5 * MIN            # slack around a window for the sampling of a reading
TICK_FOOTPRINT = 2 * HOUR  # robot per-tick faults: footprint [tick, tick + delay + this]

def mask_seq(x): return dataclasses.replace(x, seq=None)
def mk(c, idx, day, cls, sub, p, b0):
    meas, doses = c.schedule.measurement_ticks_ms, c.schedule.dose_ticks_ms
    rng = stream(c.config.generation_seed, idx, day, StreamPurpose.INJECTION_PLAN, 99)
    start = day * DAY
    if cls == "C1":
        spec = c._c1_spec(sub, rng, day, p)
        if sub in ("hypertensive_spike", "hypotension_below_hold"):
            return dataclasses.replace(spec, onset_ms=start + meas[1] - 20 * MIN, duration_ms=2 * HOUR)
        if sub == "drug_nonresponse":
            return dataclasses.replace(spec, onset_ms=start + doses[0] - 10 * MIN, duration_ms=HOUR)
        return B.c1_spec(sub, start + (meas[2] if sub == "measurement_refusal" else doses[0]))
    anchor = start + meas[1]
    coh = c.cohorts[c.config.cohorts[0].id]
    if cls == "C2":
        if sub == "ble_dropout":
            return InjectionSpec(InjectedClass.C2, sub, anchor - 5 * MIN, 2 * HOUR, params={"target": "cuff"}, level="long")
        if sub == "dispenser_bounce":
            t = min(e.t_device_ms for e in b0.days[day].truth.latent.events if e.kind.value == "dispense")
            return InjectionSpec(InjectedClass.C2, sub, t, None, float(c.design.nominal_bounce_gap_ms), "ms")
        spec = c._c2_spec(sub, rng, day, c.design.c2[sub], coh, set())
        if sub in ("manipulation_failure", "nav_delay"):
            return dataclasses.replace(spec, onset_ms=start + meas[1], params={**spec.params, "kind": "measurement"})
        return dataclasses.replace(spec, onset_ms=anchor - 5 * MIN, duration_ms=2 * HOUR)
    if sub in ("replay", "injection_naive", "injection_informed"):
        spec = c._c3_spec(sub, rng, day, c.design.c3[sub], None)
        return dataclasses.replace(spec, onset_ms=anchor - 5 * MIN, duration_ms=2 * HOUR)
    if sub == "dispense_forgery":
        return InjectionSpec(InjectedClass.C3, sub, start + doses[0] + 5 * MIN, level="naive")
    return InjectionSpec(InjectedClass.C3, sub, anchor + MIN, level="naive", params={"spoof_intake": False})

def footprint(spec):
    lo = spec.onset_ms
    if spec.duration_ms: return lo - BAND, lo + spec.duration_ms + BAND
    delay = int(spec.magnitude) if spec.subtype == "nav_delay" else 0
    return lo - BAND, lo + delay + TICK_FOOTPRINT

def multiset_diff(a, b):
    ca, cb = Counter(map(repr, a)), Counter(map(repr, b))
    return list((ca - cb).elements()), list((cb - ca).elements()), a, b

def diff_times(a, b, key=lambda x: x.t_device_ms):
    ca, cb = Counter(), Counter()
    for x in a: ca[repr(x)] += 1
    for x in b: cb[repr(x)] += 1
    out = []
    for x in a:
        if ca[repr(x)] > cb[repr(x)]: out.append(x); ca[repr(x)] -= 1
    cb2 = Counter(map(repr, a))
    for x in b:
        if cb[repr(x)] > cb2[repr(x)]: out.append(x); cb[repr(x)] -= 1
    return out

def check(c, idx, day, cls, sub, tol_pk=1e-3):
    p = c.draw_patient(idx)
    b0 = c.build_patient(p, idx, PatientInjections())
    spec = mk(c, idx, day, cls, sub, p, b0)
    inj = PatientInjections(c1=(spec,)) if cls == "C1" else PatientInjections(**{cls.lower(): {day: (spec,)}})
    b1 = c.build_patient(p, idx, inj)
    lo, hi = footprint(spec)
    fails = Counter()
    seq_shift = set()
    first_pk = spec.onset_ms
    for d in range(len(b0.days)):
        D0, D1 = b0.days[d], b1.days[d]
        L0, L1 = D0.truth.latent, D1.truth.latent
        # P1 latent baseline (AR + circadian) and adherence of all other slots: always identical
        if D0.baseline_sbp_mmhg != D1.baseline_sbp_mmhg: fails["P1 AR/circadian baseline differs"] += 1
        if sub != "double_take" and D0.truth.behaviour_log != D1.truth.behaviour_log: fails["P1 behaviour log differs"] += 1
        # P2 latent trace
        s0 = {(s.signal, s.t_device_ms): s.value for s in L0.samples}; s1 = {(s.signal, s.t_device_ms): s.value for s in L1.samples}
        if s0.keys() != s1.keys(): fails["P2 latent sample grid differs"] += 1
        dd = {k: abs(s0[k] - s1[k]) for k in s0 if s0[k] != s1[k]}
        if cls != "C1":
            if dd or L0.events != L1.events: fails["P2 latent differs for a C2/C3 injection"] += 1
        else:
            for (sig, t), v in dd.items():
                if sub in PULSE_SUBTYPES and not (spec.onset_ms <= t < spec.onset_ms + spec.duration_ms): fails["P2 latent differs outside the pulse window"] += 1
                if sub in PK_SUBTYPES and t < first_pk - 6 * MIN: fails["P2 latent differs before the first affected intake"] += 1
                if sub in ("measurement_refusal",) : fails["P2 latent pressure differs for a refusal"] += 1
                if sig != "bp": fails[f"P2 latent {sig} differs"] += 1
            if sub in PK_SUBTYPES and dd and max(dd.values()) > 30: fails["P2 PK effect > 30 mmHg (suspicious)"] += 1
        # P3 truth: C2/C3 injections change no C1 event, the only new event is the injected one
        g0 = Counter((g.cls.value, g.subtype, g.onset_ms, g.end_ms, g.injected, g.template_id) for g in D0.truth.ground_truth)
        g1 = Counter((g.cls.value, g.subtype, g.onset_ms, g.end_ms, g.injected, g.template_id) for g in D1.truth.ground_truth)
        if cls != "C1":
            extra = g1 - g0; gone = g0 - g1
            if gone: fails["P3 a truth event disappeared"] += sum(gone.values())
            if any(k[0] == "C1" for k in extra): fails["P3 a C1 truth event appeared"] += 1
            if sum(extra.values()) > 1: fails["P3 more than one new truth event"] += 1
        # P4 observed samples/events: identical outside the footprint, seq masked
        for name, a, b in (("samples", D0.observed.samples, D1.observed.samples), ("events", D0.observed.events, D1.observed.events)):
            a_m, b_m = [mask_seq(x) for x in a], [mask_seq(x) for x in b]
            for x in diff_times(a_m, b_m):
                t = x.t_rx_ms  # a replayed message keeps its old t_device but arrives in the window
                inside = lo <= t < hi
                after_pk = cls == "C1" and sub in PK_SUBTYPES and t >= first_pk - 6 * MIN
                refus = cls == "C1" and sub == "measurement_refusal"
                if not (inside or after_pk) and not (d == day and t >= lo and cls != "C1" and spec.duration_ms is None):
                    fails[f"P4 observed {name} differ outside footprint"] += 1
        # P5 seq numbers: record the constant shift of the later cuff/dispenser counters
        for sx0, sx1 in ((D0.observed.samples, D1.observed.samples), (D0.observed.events, D1.observed.events)):
            q0 = [x.seq for x in sx0 if x.seq is not None]; q1 = [x.seq for x in sx1 if x.seq is not None]
            if q0 != q1: seq_shift.add((d, len(q0) - len(q1), (q0[-1] - q1[-1]) if q0 and q1 else None))
    # P6 noise draw per reading is keyed by tick: error = obs - hold(latent) is identical for readings present in both
    for d in range(len(b0.days)):
        D0, D1 = b0.days[d], b1.days[d]
        h0, h1 = LatentSbpHold(D0.truth.latent.samples), LatentSbpHold(D1.truth.latent.samples)
        r0 = [s for s in D0.observed.samples if s.signal == "bp"]; r1 = [s for s in D1.observed.samples if s.signal == "bp"]
        if len(r0) == len(r1):
            for a, b in zip(r0, r1):
                if a.value != b.value and not (lo <= a.t_device_ms < hi or lo <= b.t_device_ms < hi) and not (cls == "C1" and sub in PK_SUBTYPES):
                    fails["P6 reading value differs outside footprint"] += 1
                if cls == "C2" and sub == "nav_delay" and abs((a.value - h0.at(a.t_device_ms)) - (b.value - h1.at(b.t_device_ms))) > 1e-9:
                    fails["P6 nav_delay: cuff error of a moved reading changed"] += 1
    return fails, seq_shift, spec

if __name__ == "__main__":
    c = BuildContext.create(CFG, allow_fixture_only=True)
    ONLY = sys.argv[2] if len(sys.argv) > 2 else None
    from ralmon.benchmark.builder import _C2_DRIVEN, _C3_ORDER
    plan = [("C1", s) for s in B.C1_SUBTYPES] + [("C2", s) for s in (*_C2_DRIVEN, "ble_dropout", "dispenser_bounce")] + [("C3", s) for s in _C3_ORDER]
    for cls, sub in plan:
        if ONLY and sub != ONLY: continue
        tot, shifts = Counter(), set()
        n = 0
        for idx in range(4):
            for day in (1, 2):
                try:
                    f, sh, spec = check(c, idx, day, cls, sub)
                except Exception as e:
                    tot[f"ERROR {type(e).__name__}: {str(e)[:80]}"] += 1; continue
                tot.update(f); shifts |= {x[:2] for x in sh}; n += 1
        print(f"{cls}/{sub:24s} cases={n:2d} " + ("PASS" if not tot else "FAIL " + "; ".join(f"{k} x{v}" for k, v in tot.items())) + f"   seq-shift days/counts: {sorted(shifts)[:3]}")
