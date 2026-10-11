"""Subtype-level attribution (RESEARCH PROTOTYPE, follow-up of section 9; the class-level module likelihood_attr.py is untouched).

p(s | e, t) is proportional to prior_t(class(s)) * pi(s | class, t) * prod_f P(class_f | s), over the sub-causes (components) s that
can violate the template t. Channels are independent given the SUB-CAUSE (the latent-class model of variant G2), which is the
only assumption of the model that is not already in the class-level table. The class posterior is the sum over the sub-causes of
a class; the subtype posterior merges the knowledge levels of replay, dispense_forgery and presence_spoof.

pi(s | class, t) comes from config/subtype_priors.yaml (relative weights, normalised over the sub-causes applicable at t).
The OUTPUT is a set: the most probable subtypes up to a cumulative probability (a sensitivity value, default 0.9). UNDETERMINED
is the full set of the subtypes applicable at t.

Cells are the ones of likelihood_attr (eps, qc grid values) plus the channel XREP, 'the cuff reading is exactly equal to the
previous reading of the same stream' (item 3): P(A | stuck_at) = 1 - eps (every reading of the window repeats the last value
before the onset), P(A | any other sub-cause) = max(rep_nat, eps), rep_nat being a SENSITIVITY value derived in section 9.3.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from functools import lru_cache
from typing import Mapping

import yaml

import likelihood_attr as L
from likelihood_attr import Comp, Params, PRIORS, A, D, U, K, _READS_BY_NAME, NON_PROVENANCE_PATHS, EXT_FIELDS, EXT_TEMPLATES
from likelihood_attr import INTAKE

XREP = "cuff.identical_repeat"
SEQREP = "crypto_temporal.seq_repeat"      # ADR-034 (accepted): a received (name, seq) repeats an accepted one
SEQGAP = "system.seq_gap"                  # ADR-034 (accepted): a sequence value is missing at the cut-off
from likelihood_attr import SEQ, BLE
CUFF_TEMPLATES = ("range", "sched", "hold", "resp", "sys")
CONFIG = "/tmp/research/likelihood/config/subtype_priors.yaml"

C1_SUBTYPES = {
    "hypertensive_spike": "range", "spontaneous_range": "range", "measurement_refusal": "sched",
    "hypotension_below_hold": "hold", "spontaneous_hold": "hold", "double_take": "count", "dose_omission": "count",
    "spontaneous_count": "count", "drug_nonresponse": "resp", "spontaneous_resp": "resp",
}
_C1 = tuple(
    Comp("C1", name, frozenset({t}), {INTAKE: "D"}, frozenset({"v1"}), {}, "C1 subtype of the benchmark (labelled event template); raises no field")
    for name, t in C1_SUBTYPES.items()
)
COMPS = _C1 + tuple(c for c in L.COMPS if c.cause != "C1")
_MERGE = {"replay_naive": "replay", "replay_informed": "replay", "dispense_forgery_naive": "dispense_forgery",
          "dispense_forgery_informed": "dispense_forgery", "presence_spoof_naive": "presence_spoof",
          "presence_spoof_informed": "presence_spoof"}


def subtype_of(comp_name: str) -> str:
    return _MERGE.get(comp_name, comp_name)


@lru_cache(maxsize=None)
def load_config(path: str = CONFIG) -> dict:
    return yaml.safe_load(open(path))


def raw_weight(comp: Comp, design: str) -> float:
    cfg = load_config()
    d = cfg["designs"][design]
    for g, members in cfg["groups"].items():
        if comp.name in members:
            return float(d["weights"].get(g, d["default"]))
    return float(d["default"])


@dataclass(frozen=True)
class SubParams:
    base: Params = Params()
    design: str = "uniform"
    level: float = 0.9
    rep: bool = False            # use the XREP channel
    rep_nat: float = 0.0         # natural probability that two consecutive readings of the cuff are identical (SENSITIVITY value)
    tb_ms: int = 10_000
    adr32: bool = False          # ADR-032 accepted: dispenser interval and content_change as native cells (content zero is raised by the bounce by construction)
    adr34: bool = False          # ADR-034 accepted: seq_gap_or_replay split into seq_repeat and seq_gap (derived from the existing field and the delivery ratio)


@lru_cache(maxsize=None)
def applicable(t: str, design: str, family: str) -> tuple:
    """(comp, pi(comp | class, t)) for every component that can violate t, weights normalised per class."""
    out = []
    for cause in L.CAUSES:
        cs = [c for c in COMPS if c.cause == cause and t in c.templates and (family == "fm" or "v1" in c.tags)]
        if not cs:
            continue
        w = [raw_weight(c, design) for c in cs]
        z = sum(w)
        out += [(c, wi / z) for c, wi in zip(cs, w)]
    return tuple(out)


# ADR-034 native cells: R raised by construction, C conditional (qc), Cn the complement (1 - qc): a naive forged number either repeats an
# accepted one or jumps ahead and leaves a gap (threat model, TM-GAP-SEQ)
SEQ_RAISES = {
    "replay_naive": {SEQREP: "R"},
    "injection_naive": {SEQREP: "C", SEQGAP: "Cn"},
    "dispense_forgery_naive": {SEQREP: "C", SEQGAP: "Cn"},
    "ble_dropout": {SEQGAP: "C"},
    "message_drop": {SEQGAP: "C"},
}


def pa_sub(comp: Comp, f: str, sp: SubParams) -> float:
    p = sp.base
    if f == XREP:
        return 1 - p.eps if comp.name == "stuck_at" else max(sp.rep_nat, p.eps)
    if f in (SEQREP, SEQGAP):
        tok = SEQ_RAISES.get(comp.name, {}).get(f)
        rho = 0.0 if tok is None else {"R": 1.0, "C": p.qc, "Cn": 1 - p.qc}[tok]
        return p.eps + (1 - 2 * p.eps) * rho
    if f == L.XZERO and sp.adr32 and comp.name == "dispenser_bounce":
        return 1 - p.eps
    return L._pa(comp, f, p)


def read_classes(readings: Mapping[str, str], t: str, sp: SubParams, ext: Mapping[str, str] | None) -> dict:
    p = sp.base
    cls = {}
    reads = {f for f in NON_PROVENANCE_PATHS if f in _READS_BY_NAME[t]}
    for f in reads:
        c = readings.get(f, U)
        if f in p.mask or c in (U, K):
            continue
        if sp.adr34 and f == SEQ:
            continue
        cls[f] = A if c == A else D
    if sp.adr34 and SEQ in reads and SEQ not in p.mask:
        sq, bl = readings.get(SEQ, U), readings.get(BLE, U)
        if sq == A and bl == "F":
            cls[SEQREP] = A
        elif sq == D:
            cls[SEQREP] = D
        if bl in ("A", "G"):
            cls[SEQGAP] = A
        elif bl == "F":
            cls[SEQGAP] = D
    if (p.ext or sp.adr32) and t in EXT_TEMPLATES and ext:
        for f in EXT_FIELDS:
            c = ext.get(f, U)
            if c in (A, D) and f not in p.mask:
                cls[f] = c
    if sp.rep and t in CUFF_TEMPLATES and ext and ext.get(XREP, U) in (A, D):
        cls[XREP] = ext[XREP]
    return cls


@dataclass(frozen=True)
class SubResult:
    template: str
    comp_post: Mapping      # component name -> posterior
    sub_post: Mapping       # subtype -> posterior
    class_post: Mapping     # class -> posterior
    loglik: Mapping         # component name -> log P(e | comp)
    pi: Mapping             # component name -> pi(comp | class, t)

    def ranked(self):
        return sorted(self.sub_post.items(), key=lambda kv: (-kv[1], kv[0]))

    def top_set(self, level: float) -> list:
        out, cum = [], 0.0
        for s, pr in self.ranked():
            out.append(s)
            cum += pr
            if cum >= level - 1e-12:
                break
        return out

    def all_subtypes(self) -> list:
        return [s for s, _ in self.ranked()]


def posterior(readings: Mapping[str, str], t: str, sp: SubParams, ext: Mapping[str, str] | None = None) -> SubResult:
    return posterior_from_cls(read_classes(readings, t, sp, ext), t, sp)


def posterior_from_cls(cls: Mapping[str, str], t: str, sp: SubParams) -> SubResult:
    app = applicable(t, sp.design, sp.base.family)
    sup = {c.cause for c, _ in app}
    pri = {c: (PRIORS[sp.base.prior][c] if c in sup else 0.0) for c in L.CAUSES}
    z = sum(pri.values())
    ll, lp, pi = {}, {}, {}
    for comp, w in app:
        l = 0.0
        for f, c in cls.items():
            pa = pa_sub(comp, f, sp)
            l += math.log(pa if c == A else 1 - pa)
        ll[comp.name] = l
        pi[comp.name] = w
        lp[comp.name] = math.log(pri[comp.cause] / z) + math.log(w) + l
    m = max(lp.values())
    ex = {k: math.exp(v - m) for k, v in lp.items()}
    zz = sum(ex.values())
    cp = {k: v / zz for k, v in ex.items()}
    sub, cl = {}, {c: 0.0 for c in L.CAUSES}
    byname = {c.name: c for c, _ in app}
    for k, v in cp.items():
        sub[subtype_of(k)] = sub.get(subtype_of(k), 0.0) + v
        cl[byname[k].cause] += v
    return SubResult(t, cp, sub, cl, ll, pi)


def subtype_loglik(subtype: str, t_fields: Mapping[str, str], sp: SubParams, ext=None, template: str = "") -> float:
    """log P(e | subtype): mixture of the levels of the subtype with their pi weights (normalised within the subtype); the fields are
    those of the alert's template. The subtype need not be applicable at the template (a pair compares its two actual causes)."""
    cls = read_classes(t_fields, template, sp, ext)
    comps = [c for c in COMPS if subtype_of(c.name) == subtype and (sp.base.family == "fm" or "v1" in c.tags)]
    if not comps:
        raise KeyError(subtype)
    w = [raw_weight(c, sp.design) for c in comps]
    z = sum(w)
    tot = 0.0
    for c, wi in zip(comps, w):
        l = 0.0
        for f, k in cls.items():
            pa = pa_sub(c, f, sp)
            l += math.log(pa if k == A else 1 - pa)
        tot += (wi / z) * math.exp(l)
    return math.log(tot) if tot > 0 else -1e9


def full_set(t: str, sp: SubParams) -> list:
    return sorted({subtype_of(c.name) for c, _ in applicable(t, sp.design, sp.base.family)})


def class_subtypes(t: str, cause: str, sp: SubParams) -> list:
    return sorted({subtype_of(c.name) for c, _ in applicable(t, sp.design, sp.base.family) if c.cause == cause})
