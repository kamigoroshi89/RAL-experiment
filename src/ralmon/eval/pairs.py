"""The confounder pairs: the prior-free log likelihood ratio, the direction, the pair statistic and McNemar (WS08-T09, ADR-074).

A pair has two members that differ in cause (``double_take`` against ``dispenser_bounce``, ``drug_nonresponse`` against
``dispense_forgery``, ``measurement_refusal`` against ``manipulation_failure``, ``dispenser_bounce`` against ``dispense_forgery``)
and a per-pair flag ``indistinguishable_by_construction``. The quantity (``docs/models/attribution-likelihood.md``, The pair
quantity) is the log likelihood ratio between the two SPECIFIC SUBTYPES, prior-free::

    Lambda_M = log P(e_M | s_A) - log P(e_M | s_B)      for the alert of member M at the common template
    D        = Lambda_A - Lambda_B

``P(e | s)`` is the product of the cells read at the template (the pair ``ble_seq_gap`` as one joint term); it depends on neither
the class priors nor the weights BETWEEN subtypes (``LikelihoodRule.log_likelihood_ratio`` and ``pair_statistic`` compute it).

* INDISTINGUISHABLE stratum (identical streams by construction): ``D`` is exactly 0 (a necessary property), and the quantity
  reported is the distance of ``Lambda`` from 0, ``|Lambda|``; ``Lambda`` itself is not 0 on identical streams, it is the lean of
  the catalogue and the cells.
* DISTINGUISHABLE stratum: the correct DIRECTION. A member is in the right direction when its ``Lambda`` points to its own cause
  (``Lambda_A > 0`` for member A, ``Lambda_B < 0`` for member B); the pair is right when both are, and ``D > 0``. Methods are
  compared by McNemar on the pair indicator ``both_right`` (``b`` = X right and Y not, ``c`` = the reverse, the exact two-sided
  binomial test on the ``b + c`` discordant pairs). The unit of McNemar is the PAIR; the members of one pair are not independent.
* NO PRECISION on pairs: the members are positives by construction, so a precision would be a rate of nothing.

Matching of the members (``docs/benchmark/evidence/pairs-allocation.md`` section 5). The relevant event of a member is its
injected ground-truth event of the confounder group (earliest; ``presence_spoof`` is a co-event of the forgery, not the
mechanism). Its alert is a VIOLATED alert of a template that event can violate, decided at or after the onset (the earliest, then
by template name); the pair compares the two members at a COMMON template: the primary template of the group if given, then
the templates in the order of ``TEMPLATES``, the first where both members have an alert. This is a provisional rule of the
research that the pairs allocation left open (it did not define the window): it is reported, not tuned.

Scoring side only: the evidence vector comes from the detector's ``AlertInputs``; the truth fixes the strata and the subtypes.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from math import comb
from typing import Any, Final, Protocol

import numpy as np

from ralmon.attribution import Alert, EvidenceVector
from ralmon.benchmark import GroundTruthEvent
from ralmon.eval.attribution_sets import wilson_interval
from ralmon.eval.attribution_truth import EventContext, event_templates
from ralmon.eval.metrics import TEMPLATES
from ralmon.monitor import VerdictState

__all__ = [
    "PAIR_CO_EVENTS",
    "MemberMatch",
    "PairMember",
    "PairResult",
    "align_directions",
    "common_match",
    "exact_two_sided_p",
    "match_member",
    "pair_direction_mcnemar",
    "pair_llr",
    "pair_result",
    "summarize_strata",
    "unshared_pairs",
]

#: injected events that accompany the mechanism of a pair without being it (group 2 with a robot has the forgery and a spoof)
PAIR_CO_EVENTS: Final[frozenset[str]] = frozenset({"presence_spoof"})


class _Rule(Protocol):
    def log_likelihood_ratio(
        self, subtype_a: str, subtype_b: str, evidence: EvidenceVector
    ) -> float: ...


@dataclass(frozen=True, slots=True)
class PairMember:
    """One member of a pair with the alert of the common template and its evidence.

    ``subtype_a`` and ``subtype_b`` are the two SPECIFIC subtypes of the pair (the same for both members: A's mechanism and B's);
    ``indistinguishable`` is the per-pair flag (None: not recorded)."""

    pair_id: str
    member: str  # "A" or "B"
    group: str
    variant_id: str | None
    indistinguishable: bool | None
    subtype_a: str
    subtype_b: str
    template: str  # lower case, the common template of the matched alert
    evidence: EvidenceVector | None
    alert: Alert | None = None


def pair_llr(members: Sequence[PairMember], rule: _Rule) -> list[float]:
    """``Lambda = log P(e | subtype_a) - log P(e | subtype_b)`` of each member, prior-free; ``nan`` for a member without evidence.

    ``rule`` is a ``LikelihoodRule`` (``02-interfaces.md#metrics`` 0.2.0 lists ``pair_llr(members)`` only; the rule is the
    source of the cells)."""
    out: list[float] = []
    for m in members:
        if m.evidence is None:
            out.append(math.nan)
        else:
            out.append(
                float(rule.log_likelihood_ratio(m.subtype_a, m.subtype_b, m.evidence))
            )
    return out


@dataclass(frozen=True, slots=True)
class PairResult:
    """The quantities of one pair at its common template."""

    pair_id: str
    group: str
    variant_id: str | None
    indistinguishable: bool | None
    template: str
    lambda_a: float
    lambda_b: float
    d: float
    a_right: bool  # Lambda_A > 0
    b_right: bool  # Lambda_B < 0
    both_right: bool
    d_positive: bool
    d_zero: bool  # D exactly 0.0


def pair_result(a: PairMember, b: PairMember, rule: _Rule) -> PairResult:
    """The result of the pair of members ``a`` (member A) and ``b`` (member B); both need evidence."""
    if a.pair_id != b.pair_id or a.member != "A" or b.member != "B":
        raise ValueError("pair_result takes member A and member B of the same pair")
    lam_a, lam_b = pair_llr([a, b], rule)
    if math.isnan(lam_a) or math.isnan(lam_b):
        raise ValueError(f"pair {a.pair_id!r}: a member has no evidence")
    d = lam_a - lam_b
    return PairResult(
        a.pair_id,
        a.group,
        a.variant_id,
        a.indistinguishable,
        a.template,
        lam_a,
        lam_b,
        d,
        lam_a > 0.0,
        lam_b < 0.0,
        lam_a > 0.0 and lam_b < 0.0,
        d > 0.0,
        d == 0.0,
    )


# ---- McNemar ----------------------------------------------------------------------------------------------------------------


def exact_two_sided_p(b: int, c: int) -> float:
    """The exact two-sided binomial p of ``b`` and ``c`` discordant pairs: ``min(1, 2 P(X <= min(b, c)))``, ``X ~ Binomial(b + c,
    1/2)``; 1 without a discordant pair. Computed in exact integer arithmetic."""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(comb(n, i) for i in range(min(b, c) + 1))
    return float(min(Fraction(1), Fraction(2 * tail, 2**n)))


def pair_direction_mcnemar(x: Sequence[bool], y: Sequence[bool]) -> dict[str, float]:
    """McNemar between methods X and Y on the indicator ``both_right`` of the same pairs: ``b`` = X right and Y not, ``c`` = the
    reverse, ``n_discordant`` = ``b + c``, ``p`` the exact two-sided binomial p."""
    if len(x) != len(y):
        raise ValueError("x and y must have the same length (one entry per pair)")
    b = sum(1 for i, j in zip(x, y, strict=True) if i and not j)
    c = sum(1 for i, j in zip(x, y, strict=True) if j and not i)
    return {"b": b, "c": c, "n_discordant": b + c, "p": exact_two_sided_p(b, c)}


def align_directions(
    x: Sequence[PairResult], y: Sequence[PairResult]
) -> tuple[list[bool], list[bool], list[str]]:
    """The ``both_right`` indicators of two methods on the pairs they share, in the order of ``x`` (by ``pair_id``)."""
    by_y = {r.pair_id: r for r in y}
    ids = [r.pair_id for r in x if r.pair_id in by_y]
    by_x = {r.pair_id: r for r in x}
    return [by_x[i].both_right for i in ids], [by_y[i].both_right for i in ids], ids


def unshared_pairs(
    x: Sequence[PairResult], y: Sequence[PairResult]
) -> tuple[list[str], list[str]]:
    """The pairs matched (given a result) by ``x`` only and by ``y`` only: McNemar uses the shared ones, the others are reported."""
    ids_x, ids_y = [r.pair_id for r in x], [r.pair_id for r in y]
    return (
        [i for i in ids_x if i not in set(ids_y)],
        [i for i in ids_y if i not in set(ids_x)],
    )


# ---- strata --------------------------------------------------------------------------------------------------------------------


def _abs_lambda(results: Sequence[PairResult]) -> dict[str, Any]:
    values = np.array(
        [abs(v) for r in results for v in (r.lambda_a, r.lambda_b)], dtype=np.float64
    )
    if values.size == 0:
        return {"n": 0, "mean": None, "min": None, "median": None, "max": None}
    return {
        "n": int(values.size),
        "mean": float(values.mean()),
        "min": float(values.min()),
        "median": float(np.median(values)),
        "max": float(values.max()),
    }


def summarize_strata(results: Sequence[PairResult], *, level: float) -> dict[str, Any]:
    """The two strata of the pair results (module docstring). The stratum is the per-pair flag; a pair without it is counted in
    ``unknown`` and in neither stratum. There is NO precision: the members are positives by construction."""
    ind = [r for r in results if r.indistinguishable is True]
    dist = [r for r in results if r.indistinguishable is False]
    n_dist = len(dist)
    both = sum(1 for r in dist if r.both_right)
    members_right = sum(int(r.a_right) + int(r.b_right) for r in dist)
    lo, hi = wilson_interval(both, n_dist, level)
    return {
        "unknown": sum(1 for r in results if r.indistinguishable is None),
        "indistinguishable": {
            "n_pairs": len(ind),
            "n_d_exactly_zero": sum(1 for r in ind if r.d_zero),
            "abs_lambda": _abs_lambda(ind),
            "note": (
                "identical streams: D is exactly 0; Lambda is the lean of the catalogue and the cells, not 0 (its distance from 0 is "
                "|Lambda|)"
            ),
        },
        "distinguishable": {
            "n_pairs": n_dist,
            "n_both_right": both,
            "both_right_rate": both / n_dist if n_dist else None,
            "both_right_wilson": [lo, hi] if n_dist else [None, None],
            "n_d_positive": sum(1 for r in dist if r.d_positive),
            "n_members": 2 * n_dist,
            "n_member_right": members_right,
            "note": "the unit of the comparison between methods is the pair; the two members of a pair are not independent",
        },
    }


# ---- matching of the members ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MemberMatch:
    """The relevant event of a member and the alerts it can be matched to (violated, a template of the event, at or after
    the onset), earliest first."""

    event: GroundTruthEvent
    event_index: int
    templates: tuple[str, ...] | None
    candidates: tuple[Alert, ...]


def match_member(
    events: Sequence[GroundTruthEvent],
    contexts: Sequence[EventContext] | None,
    alerts: Sequence[object],
    *,
    group: str | None = None,
) -> MemberMatch | None:
    """The relevant event of a member (the earliest injected event of the confounder group, ``presence_spoof`` aside) and its
    candidate alerts; ``None`` when the member has no such event."""
    ctxs = list(contexts) if contexts is not None else [EventContext()] * len(events)
    if len(ctxs) != len(events):
        raise ValueError("contexts must align with the ground truth")
    pool = [
        (i, e)
        for i, e in enumerate(events)
        if e.injected
        and e.confounder_group is not None
        and (group is None or e.confounder_group == group)
        and e.subtype not in PAIR_CO_EVENTS
    ]
    if not pool:
        return None
    index, event = min(pool, key=lambda item: (item[1].onset_ms, item[0]))
    templates = event_templates(event, ctxs[index])
    chosen = [
        a
        for a in alerts
        if isinstance(a, Alert)
        and a.verdict is VerdictState.VIOLATED
        and a.caused_by
        is None  # a cascade effect carries its root's posterior: the root is the alert of the mechanism
        and a.t_ms >= event.onset_ms
        and (templates is None or _template(a) in templates)
    ]
    chosen.sort(key=lambda a: (a.t_ms, _template(a)))
    return MemberMatch(event, index, templates, tuple(chosen))


def _template(alert: Alert) -> str:
    return str(getattr(alert.tau, "value", alert.tau)).lower()


def common_match(
    a: MemberMatch, b: MemberMatch, *, primary: str | None = None
) -> tuple[str, Alert, Alert] | None:
    """The common template of two members and their alerts: the templates both events can violate (when one is unconstrained,
    those of the other), the ``primary`` one first, then in the order of ``TEMPLATES``; the first with a candidate alert in both
    members, each member's earliest alert there."""
    if a.templates is None and b.templates is None:
        shared = [t.lower() for t in TEMPLATES]
    elif a.templates is None:
        shared = list(b.templates or ())
    elif b.templates is None:
        shared = list(a.templates)
    else:
        shared = [t for t in a.templates if t in b.templates]
    order = [t.lower() for t in TEMPLATES]
    shared.sort(
        key=lambda t: (t != primary, order.index(t) if t in order else len(order))
    )
    for template in shared:
        left = next((x for x in a.candidates if _template(x) == template), None)
        right = next((x for x in b.candidates if _template(x) == template), None)
        if left is not None and right is not None:
            return template, left, right
    return None
