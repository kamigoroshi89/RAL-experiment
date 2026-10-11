"""Likelihood-table attributor (RESEARCH PROTOTYPE, not in the repository).

p(c | e, t)  proportional to  prior_t(c) * prod_f P(reading class of f | c, t),   c in {C1, C2, C3}.

Inputs. Exactly what ``HierarchicalRule`` reads: a ``VerdictRecord`` (only its template is used, through the
provenance of the vector; no rho, no interval, no verdict state, no time) and an ``EvidenceVector``. The reading
classes and the relevance map per template are the ones of docs/models/attribution-rule.md: the classes come from
``HierarchicalRule._readings`` (same thresholds, same relevance map). A class U (``None`` or out of domain)
contributes the factor 1; K (a deliberate lifecycle transition) is treated as U (no cause of the model produces
it); the finer classes F/G of ``ble_link_quality`` count as D in the independent table and as separate joint classes
in the grouped variant G1.

Cells. NO NUMBER IS A PROPOSAL. A cell is built from a catalogue of *components* (fault-model subtypes for C2,
threat-model attack classes at a knowledge level for C3, the clinical subtypes for C1) and a mixture over the
components that can violate the template:

    P(f = A | c, t) = sum_s w(s | c, t) * ( eps + (1 - 2 eps) * rho(s, f) )

with rho = 1 when the component raises the field by construction ('R' in the catalogue), rho = qc when the raise is
conditional ('C': conditions LC, SEQ, ... of the fault-model table), rho = 0 when it does not. eps, qc, the
mixture weights w, the priors and the abstention threshold are SENSITIVITY GRID values (class ``Params``). Each cell's
source (fault-model row, threat-model row, device specification, design choice) is listed in ``CATALOGUE`` and
reported by ``cell_sources``.

Independence of the channels given the cause (naive Bayes) is an ASSUMPTION. Variants: ``group='g1'`` groups
(ble_link_quality, seq_gap_or_replay) in a joint 4-class reading (repeat, gap, degraded, clean) and
(pulse_vs_ecg_hr_diff, ecg_sqi, ppg_sqi) with the ecg_noise common cause; ``group='g2'`` makes the channels
independent given the *subtype* instead of the cause (latent-class mixture over all fields).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from functools import lru_cache
from typing import Iterable, Mapping

from ralmon.attribution.evidence import NON_PROVENANCE_PATHS
from ralmon.attribution.rule import (
    A, D, U, K, F, G, HierarchicalRule, _READS,
    LIFE, DIAG, LIVE, QOS, BLE, NAV, MANIP, ECG, PPG, CUFF, DIFF, IDENT, INTAKE, AUTH, SEQ, TIME,
)

CAUSES = ("C1", "C2", "C3")
XSHORT = "dispenser.short_interval"      # EXTENSION (ADR-032 proposed, outside the contract): an opening within T_b of the previous one
XZERO = "dispenser.no_content_change"   # EXTENSION: an opening with content_change == 0 (dispenser with content sensing)
EXT_FIELDS = (XSHORT, XZERO)
EXT_TEMPLATES = ("count", "hold", "resp", "int")
_ORDER = {p: i for i, p in enumerate((*NON_PROVENANCE_PATHS, *EXT_FIELDS))}


# ---------------------------------------------------------------------------------------------------------------
# Catalogue of components
# ---------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Comp:
    cause: str
    name: str
    templates: frozenset
    raises: Mapping  # field -> 'R' | 'C' | 'D' (D: divert share, C1 only)
    tags: frozenset
    jmain: Mapping = field(default_factory=dict)  # (BLE,SEQ) joint main classes for G1: class -> prob
    source: str = ""


def _c(cause, name, templates, raises, tags, jmain=None, source=""):
    return Comp(cause, name, frozenset(templates.split()), dict(raises), frozenset(tags.split()), dict(jmain or {}), source)


CARE = "range sched hold count resp"
COMPS = (
    # ---- C1: clinical subtypes; they raise no evidence field by construction (analisi 4.5, fault-model "non-faults").
    _c("C1", "clinical", CARE, {INTAKE: "D"}, "v1", source="analisi 4.5 (C1 raises no system/integrity evidence); INTAKE: diverted dose share delta (design, awaiting gab; the benchmark adherence model has none)"),
    # ---- C2: fault-model.md Fault-to-evidence table (raised R / conditional C); templates from the same table
    _c("C2", "cuff_detached", "sched resp hold", {CUFF: "R", LIFE: "R"}, "loud v1", source="fault-model row cuff_detached"),
    _c("C2", "cuff_silent_bias", "range hold resp", {}, "silent v1", source="fault-model row cuff_silent_bias (silent, declared limit)"),
    _c("C2", "stuck_at", "range hold resp", {}, "silent v1", source="fault-model row stuck_at (silent, declared limit)"),
    _c("C2", "ecg_noise", "sys", {DIFF: "R", ECG: "C"}, "loud v1", source="fault-model row ecg_noise (violation only through sys; also a nuisance in G1)"),
    _c("C2", "dispenser_bounce", "count hold resp int", {XSHORT: "C", XZERO: "C"}, "silent v1", source="fault-model row dispenser_bounce (silent for the 20 fields; EXTENSION fields ADR-032)"),
    _c("C2", "ble_dropout", "sched resp hold count", {LIFE: "R", BLE: "R", DIAG: "R", LIVE: "C", QOS: "C", SEQ: "C"}, "loud v1",
       {"gap": "qc", "degraded": "1-qc"}, source="fault-model row ble_dropout; DIAG: driver reports stale while the device is silent (ADR-074)"),
    _c("C2", "message_drop", "sched resp hold count int", {BLE: "C", SEQ: "C", QOS: "C", LIVE: "C", DIAG: "C"}, "loud",
       {"gap": "qc", "clean": "1-qc"}, source="fault-model row message_drop (all conditional); DIAG: device alive, stale only for a long run of losses"),
    _c("C2", "link_delay", "sched resp hold count int", {TIME: "R", QOS: "C"}, "loud", source="fault-model row link_delay"),
    _c("C2", "clock_skew", "sched hold", {TIME: "R"}, "loud", source="fault-model row clock_skew"),
    _c("C2", "nav_delay", "sched resp hold", {NAV: "C"}, "loud v1", source="fault-model row nav_delay (D-5)"),
    _c("C2", "impossible_goal", "sched resp hold", {NAV: "R"}, "loud", source="fault-model row impossible_goal"),
    _c("C2", "localisation_noise", "sched resp hold", {NAV: "C"}, "loud", source="fault-model row localisation_noise"),
    _c("C2", "manipulation_failure", "sched resp hold", {MANIP: "R"}, "loud v1", source="fault-model row manipulation_failure"),
    _c("C2", "process_kill", "count", {LIVE: "C", QOS: "C", LIFE: "C", DIAG: "R"}, "loud", source="fault-model row process_kill (device target); DIAG stale"),
    _c("C2", "uncommanded_lifecycle_transition", "count", {LIFE: "R", DIAG: "R"}, "loud", source="fault-model row uncommanded_lifecycle_transition"),
    _c("C2", "battery_depleted", "sched resp hold", {LIVE: "C", QOS: "C"}, "loud", source="fault-model row battery_depleted (robot has no driver diagnostics in the profile)"),
    # ---- C3: threat-model.md attack-to-evidence table, by knowledge level
    _c("C3", "replay_naive", "sched hold resp", {SEQ: "R", TIME: "R"}, "naive v1", {"repeat": "1"}, source="threat-model row replay (naive; verbatim copy keeps a valid tag)"),
    _c("C3", "replay_informed", "range hold resp sys", {AUTH: "R", DIFF: "C"}, "informed v1", source="threat-model row replay (informed)"),
    _c("C3", "injection_naive", "range hold resp sched sys", {AUTH: "R", SEQ: "C", TIME: "C", DIFF: "C"}, "naive v1", {"repeat": "qc", "clean": "1-qc"}, source="threat-model row injection_naive"),
    _c("C3", "injection_informed", "range hold resp sys", {AUTH: "R"}, "informed v1", source="threat-model row injection_informed"),
    _c("C3", "dispense_forgery_naive", "count hold resp int", {AUTH: "R", SEQ: "R", INTAKE: "C"}, "naive v1", {"repeat": "qc", "gap": "1-qc"}, source="threat-model row dispense_forgery (naive); INTAKE False when the robot is co-located and saw nothing"),
    _c("C3", "dispense_forgery_informed", "count hold resp int", {AUTH: "R", INTAKE: "C"}, "informed v1", source="threat-model row dispense_forgery (informed)"),
    _c("C3", "presence_spoof_naive", "int", {IDENT: "C"}, "naive v1", source="threat-model row presence_spoof (naive)"),
    _c("C3", "presence_spoof_informed", "int", {}, "informed v1", source="threat-model row presence_spoof (informed)"),
    _c("C3", "timestamp_manipulation", "sched hold range resp", {TIME: "R", AUTH: "R"}, "naive", source="threat-model row timestamp_manipulation (modelled, not injected in v1)"),
    _c("C3", "dispenser_physical_tamper", "count hold resp int", {INTAKE: "C"}, "informed", source="threat-model row dispenser_physical_tamper (modelled, not injected in v1)"),
)
NUISANCE = _c("C2", "ecg_noise_nuisance", "range hold resp", {DIFF: "R", ECG: "C"}, "loud nuisance", source="G1 only: ecg_noise as a common cause of the cross-device group")

PRIORS = {
    "uniform": {"C1": 1 / 3, "C2": 1 / 3, "C3": 1 / 3},
    "c1_heavy": {"C1": 0.6, "C2": 0.3, "C3": 0.1},   # ILLUSTRATIVE (sensitivity value only)
    "c2_heavy": {"C1": 0.3, "C2": 0.6, "C3": 0.1},   # ILLUSTRATIVE
    "c3_rare": {"C1": 0.45, "C2": 0.5, "C3": 0.05},  # ILLUSTRATIVE
    "c3_heavy": {"C1": 0.2, "C2": 0.2, "C3": 0.6},   # ILLUSTRATIVE
}


@dataclass(frozen=True)
class Params:
    eps: float = 0.01                 # sensitivity grid {0.001, 0.01, 0.05, 0.1}
    qc: float = 0.5                   # probability that a conditional raise holds; grid {0.25, 0.5, 0.75}
    prior: str = "uniform"
    family: str = "fm"                # 'fm': all fault-model/threat-model components; 'v1': the subtypes injected by benchmark v1
    silent_share: float | None = None  # total within-C2 weight of the silent components; None: uniform over components
    informed_share: float | None = None  # total within-C3 weight of the informed-level components; None: uniform
    divert: float = 0.0               # share of C1 in which a dispensed dose is not taken (witness INTAKE False); 0 in the benchmark
    group: str = "none"               # 'none' | 'g1' | 'g2'
    ext: bool = False                 # use the EXTENSION dispenser fields
    scope: str = "template"           # 'template': cells of C2/C3 use the components that can violate the template; 'all': every component of the cause (co-occurrence reading)
    mask: frozenset = frozenset()     # fields read as unavailable (witness / verification ablations)
    tau: float = 0.8                  # abstention threshold; grid {0.5, 0.67, 0.8, 0.9, 0.95, 0.99}


# ---------------------------------------------------------------------------------------------------------------
# Cells
# ---------------------------------------------------------------------------------------------------------------
def _rho(comp: Comp, f: str, p: Params) -> float:
    r = comp.raises.get(f)
    if r is None:
        return 0.0
    if r == "R":
        return 1.0
    if r == "C":
        return p.qc
    if r == "D":
        return p.divert
    raise ValueError(r)


def _pa(comp: Comp, f: str, p: Params) -> float:
    return p.eps + (1 - 2 * p.eps) * _rho(comp, f, p)


def components(cause: str, t: str, p: Params, for_support: bool = False) -> list[Comp]:
    wide = p.scope == "all" and cause in ("C2", "C3") and not for_support
    comps = [c for c in COMPS if c.cause == cause and (wide or t in c.templates) and (p.family == "fm" or "v1" in c.tags)]
    if p.group == "g1" and cause == "C2" and t in NUISANCE.templates:
        comps.append(NUISANCE)
    return comps


def weights(cause: str, t: str, p: Params) -> tuple[list[Comp], list[float]]:
    comps = components(cause, t, p)
    if not comps:
        return [], []
    w = [1.0] * len(comps)
    def split(tag: str, share: float | None):
        if share is None:
            return
        a = [i for i, c in enumerate(comps) if tag in c.tags]
        b = [i for i, c in enumerate(comps) if tag not in c.tags]
        if a and b:
            for i in a:
                w[i] = share / len(a)
            for i in b:
                w[i] = (1 - share) / len(b)
    if cause == "C2":
        split("silent", p.silent_share)
    if cause == "C3":
        split("informed", p.informed_share)
    z = sum(w)
    return comps, [x / z for x in w]


def support(t: str, p: Params) -> tuple[str, ...]:
    return tuple(c for c in CAUSES if components(c, t, p, for_support=True))


@lru_cache(maxsize=None)
def cell(cause: str, t: str, f: str, p: Params) -> float | None:
    """P(f = A | cause, t); None when the cause has no component for the template (the cause is impossible)."""
    comps, w = weights(cause, t, p)
    if not comps:
        return None
    return sum(wi * _pa(c, f, p) for c, wi in zip(comps, w))


def cell_sources(f: str, t: str, p: Params = Params()) -> dict:
    """For each cause, the components that make the cell and why (for the report)."""
    out = {}
    for c in CAUSES:
        comps, w = weights(c, t, p)
        out[c] = [(x.name, round(wi, 4), x.raises.get(f, "-"), x.source) for x, wi in zip(comps, w)]
    return out


# joint reading J of (BLE, SEQ) in G1
_J = ("repeat", "gap", "degraded", "clean")


def _jdist(comp: Comp, p: Params) -> dict:
    main = {}
    for j, pr in (comp.jmain or {"clean": "1"}).items():
        main[j] = {"1": 1.0, "qc": p.qc, "1-qc": 1 - p.qc}[pr]
    out = {}
    for j in _J:
        out[j] = sum(m * ((1 - p.eps) if j == mj else p.eps / 3) for mj, m in main.items())
    return out


def _jprob(comp: Comp, ble: str, seq: str, p: Params) -> float:
    d = _jdist(comp, p)
    if ble != U and seq != U:
        if seq == A:
            return d["repeat"] if ble == F else d["gap"]
        return d["degraded"] if ble == A else d["clean"]
    if seq != U:  # BLE unavailable
        return (d["repeat"] + d["gap"]) if seq == A else (d["degraded"] + d["clean"])
    if ble != U:  # SEQ unavailable
        return {A: d["gap"] + d["degraded"], G: d["gap"], F: d["repeat"] + d["clean"], D: d["clean"] + d["repeat"]}[ble]
    return 1.0


# ---------------------------------------------------------------------------------------------------------------
# Posterior
# ---------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Result:
    template: str
    posterior: Mapping
    loglik: Mapping
    used: tuple      # (field, class, {cause: log P(class | cause)}) in contract order; grouped: ('+'.join(fields), classes, ...)
    support: tuple

    def kappa(self, tau: float) -> str:
        best = max(self.posterior, key=self.posterior.get)
        return best if self.posterior[best] >= tau else "UNDETERMINED"

    def argmax(self) -> str:
        return max(self.posterior, key=self.posterior.get)

    def llr(self, ca: str, cb: str) -> float:
        return self.loglik[ca] - self.loglik[cb]


def _field_ll(cause, t, f, cls, p) -> float | None:
    pa = cell(cause, t, f, p)
    if pa is None:
        return None
    return math.log(pa if cls == A else 1 - pa)


def classes_from_rule(rule: HierarchicalRule, evidence, template) -> dict:
    r = rule._readings(evidence, template)
    out = {}
    for f, cls in r.items():
        out[f] = cls
    return out


def posterior_from_readings(readings: Mapping[str, str], template: str, p: Params, ext: Mapping[str, str] | None = None) -> Result:
    """readings: reading class per non-provenance field (U for fields the template does not read)."""
    t = template
    reads = {f for f in NON_PROVENANCE_PATHS if f in _READS_BY_NAME[t]}
    if p.ext and t in EXT_TEMPLATES and ext:
        reads |= {f for f in EXT_FIELDS if f in ext}
    cls = {}
    for f in reads:
        c = readings.get(f, U) if f in readings else (ext or {}).get(f, U)
        if f in p.mask or c in (U, K):
            continue
        if f == BLE:
            cls[f] = c if p.group == "g1" else (A if c == A else D)
        else:
            cls[f] = c
    sup = support(t, p)
    ll = {c: 0.0 for c in CAUSES}
    used = []
    if p.group == "none":
        for f in sorted(cls, key=_ORDER.get):
            parts = {}
            for c in CAUSES:
                v = _field_ll(c, t, f, cls[f], p)
                parts[c] = v
                if v is not None:
                    ll[c] += v
            used.append((f, cls[f], parts))
    else:
        groups = _groups(cls, p)
        for gname, gfields in groups:
            parts = {}
            for c in CAUSES:
                comps, w = weights(c, t, p)
                if not comps:
                    parts[c] = None
                    continue
                tot = 0.0
                for comp, wi in zip(comps, w):
                    tot += wi * _group_prob(comp, gname, gfields, cls, p)
                parts[c] = math.log(tot) if tot > 0 else -1e9
                ll[c] += parts[c]
            used.append(("+".join(gfields), "".join(cls[x] for x in gfields), parts))
    pri = {c: (PRIORS[p.prior][c] if c in sup else 0.0) for c in CAUSES}
    z = sum(pri.values())
    lp = {c: (math.log(pri[c] / z) + ll[c] if pri[c] > 0 else -math.inf) for c in CAUSES}
    m = max(lp.values())
    ex = {c: math.exp(lp[c] - m) for c in CAUSES}
    zz = sum(ex.values())
    post = {c: ex[c] / zz for c in CAUSES}
    llc = {c: (ll[c] if c in sup else -math.inf) for c in CAUSES}
    return Result(t, post, llc, tuple(used), sup)


_READS_BY_NAME = {k.value: v for k, v in _READS.items()}


def _groups(cls, p: Params):
    fs = set(cls)
    if p.group == "g2":
        return [("all", sorted(fs, key=_ORDER.get))]
    out, used = [], set()
    if BLE in fs and SEQ in fs:
        out.append(("ble_seq", [BLE, SEQ])); used |= {BLE, SEQ}
    xd = [f for f in (DIFF, ECG, PPG) if f in fs]
    if len(xd) > 1:
        out.append(("xdev", xd)); used |= set(xd)
    for f in sorted(fs - used, key=_ORDER.get):
        out.append((f, [f]))
    return sorted(out, key=lambda g: _ORDER[g[1][0]])


def _group_prob(comp: Comp, gname: str, gfields, cls, p: Params) -> float:
    if gname == "ble_seq":
        return _jprob(comp, cls[BLE], cls[SEQ], p)
    pr = 1.0
    for f in gfields:
        pa = _pa(comp, f, p)
        pr *= pa if (A if cls[f] == A else D) == A else (1 - pa)
    return pr


class LikelihoodAttributor:
    """Same inputs as ``HierarchicalRule.attribute``: a VerdictRecord and an EvidenceVector."""

    def __init__(self, registry, params: Params = Params()):
        self.rule = HierarchicalRule(registry)  # for the reading classes only (same thresholds, same relevance map)
        self.params = params

    def posterior(self, violated, evidence, ext: Mapping[str, str] | None = None, params: Params | None = None) -> Result:
        p = params or self.params
        template = evidence.provenance.violated_template
        r = classes_from_rule(self.rule, evidence, template)
        return posterior_from_readings(r, template.value, p, ext)

    def attribute(self, violated, evidence) -> str:
        return self.posterior(violated, evidence).kappa(self.params.tau)
