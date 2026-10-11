"""Pair data: relevant events, alert matching (provisional, pairs-allocation.md section 5 item 2), method variants."""
import sys, pickle, math, collections
sys.path.insert(0, "/tmp/research/likelihood"); sys.path.insert(0, "/tmp/research/likelihood/scripts")
import common, likelihood_attr as L
from dataclasses import replace

MECH = {
    "double_take_vs_bounce": (("C1", "double_take"), ("C2", "dispenser_bounce")),
    "nonresponse_vs_falsified_dispense": (("C1", "drug_nonresponse"), ("C3", "dispense_forgery")),
    "refusal_vs_robot_missed": (("C1", "measurement_refusal"), ("C2", "manipulation_failure")),
    "bounce_vs_forged_dispense": (("C2", "dispenser_bounce"), ("C3", "dispense_forgery")),
}
GROUPS = list(MECH)
PRIMARY = {"double_take_vs_bounce": "count", "nonresponse_vs_falsified_dispense": "resp",
           "refusal_vs_robot_missed": "sched", "bounce_vs_forged_dispense": "count"}
PRIO = ["count", "resp", "sched", "hold", "int", "range", "sys"]
C3_TEMPLATES = {"dispense_forgery": ["count", "hold", "resp", "int"]}
SILENT = {"stuck_at", "cuff_silent_bias", "dispenser_bounce"}


def load(tag="p40", sw=1):
    return pickle.load(open(f"{common.ROOT}/out/pairs_{tag}_sw{sw}.pkl", "rb"))


def relevant_event(group, member, mem):
    """(cause, subtype, templates, onset_ms) of the injected ground-truth event of the member's mechanism, or None.
    Scoring-side use of the ground truth: the attributor never sees it."""
    cls, sub = MECH[group][0 if member == "A" else 1]
    ev = [g for g in mem["gt"] if g[0] == cls and g[1] == sub and g[5]]
    if not ev:
        return None
    g = sorted(ev, key=lambda x: x[3])[0]
    if g[2] is not None:
        temps = [g[2]]
    else:
        lg = [l for l in mem["log"] if l["cls"] == cls and l["subtype"] == sub and l["realised"]]
        temps = list(lg[0]["templates"]) if lg and lg[0]["templates"] else C3_TEMPLATES.get(sub, [])
    return dict(cause=cls, subtype=sub, templates=temps, onset=g[3])


def first_alert(mem, templates, onset, prefer=None):
    cands = [a for a in mem["alerts"] if a["template"] in templates and a["decided"] >= onset]
    if not cands:
        return None
    order = ([prefer] if prefer else []) + PRIO
    if prefer:
        pc = [a for a in cands if a["template"] == prefer]
        if pc:
            return min(pc, key=lambda a: a["decided"])
    return min(cands, key=lambda a: (a["decided"], order.index(a["template"]) if a["template"] in order else 99))


ALT_PRIMARY = {"double_take_vs_bounce": "resp", "bounce_vs_forged_dispense": "resp",
               "nonresponse_vs_falsified_dispense": "resp", "refusal_vs_robot_missed": "sched"}


def extra_resp_alert(mem, mech):
    """RESP alert anchored at the extra opening of the dispenser (second dispense of a double take; bounce; forged dispense)."""
    cls, sub = mech
    lg = [l for l in mem["log"] if l["cls"] == cls and l["subtype"] == sub and l["realised"]]
    if not lg:
        return None
    lo = lg[0]["onset_ms"] + (1 if sub == "dispenser_bounce" else 0)
    c = []
    for a in mem["alerts"]:
        if a["template"] != "resp":
            continue
        try:
            anchor = int(a["key"].split("@")[1])
        except Exception:
            continue
        if lo <= anchor <= lo + 60_000:
            c.append(a)
    return min(c, key=lambda a: a["decided"]) if c else None


def common_match(r, primary):
    rel = r["rel"]; g = r["group"]
    if not (rel["A"] and rel["B"]):
        return None, None, None
    inter = [t for t in PRIO if t in rel["A"]["templates"] and t in rel["B"]["templates"]]
    order = [primary] + [t for t in inter if t != primary]
    for t in order:
        if t not in inter:
            continue
        a = first_alert(r["A"], [t], rel["A"]["onset"])
        b = first_alert(r["B"], [t], rel["B"]["onset"])
        if a and b:
            return t, a, b
    return None, None, None


def match_pair(r):
    """Fill r['rel'] (per member relevant event), r['own'] (own match), r['com'] (pair-common template match, primary
    template first) and r['com_resp'] (the same with the RESP alert as primary where both members have one)."""
    g = r["group"]
    rel = {m: relevant_event(g, m, r[m]) for m in "AB"}
    r["rel"] = rel
    r["cause"] = {"A": MECH[g][0][0], "B": MECH[g][1][0]}
    r["both_realised"] = bool(rel["A"] and rel["B"])
    r["own"] = {m: (first_alert(r[m], rel[m]["templates"], rel[m]["onset"], PRIMARY[g]) if rel[m] else None) for m in "AB"}
    t, a, b = common_match(r, PRIMARY[g])
    r["com"] = {"A": a, "B": b}; r["com_template"] = t
    t2 = None
    r["com_alt"] = {"A": None, "B": None}
    if g in ("double_take_vs_bounce", "bounce_vs_forged_dispense"):
        a2 = extra_resp_alert(r["A"], MECH[g][0]); b2 = extra_resp_alert(r["B"], MECH[g][1])
        if a2 and b2:
            t2 = "resp(extra opening)"; r["com_alt"] = {"A": a2, "B": b2}
    elif rel["A"] and rel["B"]:
        a2 = first_alert(r["A"], [ALT_PRIMARY[g]], rel["A"]["onset"]); b2 = first_alert(r["B"], [ALT_PRIMARY[g]], rel["B"]["onset"])
        if a2 and b2:
            t2 = ALT_PRIMARY[g]; r["com_alt"] = {"A": a2, "B": b2}
    r["com_alt_template"] = t2
    return r


def ext_features(mem, alert, tb_ms):
    """EXTENSION dispenser channels from the observed DISPENSE events up to the decision time (window 24 h)."""
    ts = sorted(((t, c) for t, c in mem["dispenses"] if alert["decided"] - 24 * 3600 * 1000 <= t <= alert["decided"]), key=lambda x: x[0])
    if not ts:
        return {L.XSHORT: "U", L.XZERO: "U"}
    short = any(b[0] - a[0] < tb_ms for a, b in zip(ts, ts[1:]))
    cc = [c for _, c in ts if c is not None]
    zero = "U" if not cc else ("A" if any(abs(c) < 1e-9 for c in cc) else "D")
    return {L.XSHORT: "A" if short else "D", L.XZERO: zero}


WIT = frozenset({"witness.identity_confirmed", "witness.intake_observed", "witness.robot_present"})
VER = frozenset({"crypto_temporal.authenticated"})
VARIANTS = {
    "V0 full (diag ON)":            dict(ev="ev_on", mask=frozenset(), ext=False),
    "V1 full, no diagnostics":      dict(ev="ev_off", mask=frozenset(), ext=False),
    "V2 no witness":                dict(ev="ev_on", mask=WIT, ext=False),
    "V3 no verification":           dict(ev="ev_on", mask=VER, ext=False),
    "V4 no witness, no verif.":     dict(ev="ev_on", mask=WIT | VER, ext=False),
    "V5 + dispenser channels (ADR-032 proto)": dict(ev="ev_on", mask=frozenset(), ext=True),
}


class Scorer:
    def __init__(self, reg):
        self.att = L.LikelihoodAttributor(reg)
        self.cache = {}

    def result(self, alert, variant, params, tb_ms=10_000, mem=None):
        v = VARIANTS[variant]
        ev = alert[v["ev"]]
        if ev is None:
            return None
        p = replace(params, mask=v["mask"], ext=v["ext"])
        ext = ext_features(mem, alert, tb_ms) if v["ext"] else None
        return self.att.posterior(alert["record"], ev, ext=ext, params=p)


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    ph = k / n
    d = 1 + z * z / n
    c = (ph + z * z / (2 * n)) / d
    h = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def exact_binom_p(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    from math import comb
    p = sum(comb(n, i) for i in range(0, k + 1)) / 2 ** n
    return min(1.0, 2 * p)
