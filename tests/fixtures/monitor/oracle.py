"""Naive full-trace reference evaluator for the monitor tests (WS05-T04, step 2).

This module is written from the *text* of docs/formal/05-three-valued-semantics.md (sections 2.1 to
2.3, 3.1, 3.3, 3.4), docs/formal/02-templates.md (sections 1.2, 1.3, 1.5, 2.3, 3.1) and
docs/formal/01-signals-sampling.md (sections 3 and 5). It imports nothing from ``ralmon``: not the
monitor, not the spec package, not the signal helpers. Its only inputs are plain numbers, the
formula strings of the template library and the accepted trace.

How it differs from the monitor on purpose (so that agreement is evidence and not a tautology):

* it parses the template *strings* (its own tokenizer and recursive-descent parser of the EBNF of
  02-templates.md section 1.2) and evaluates the *body* of an instance by the structural interval
  recursion of 05 section 2.2, node by node, with no closed form;
* it keeps dense arrays: one interval per signal per grid step, rebuilt from scratch for every cut
  step ``k`` (no incremental state, no running extrema, no deque);
* a position is "determined" when its step is at most the cut ``k`` and its grid value is a number,
  otherwise it is "open" and takes the hull of its domain (05 section 2.1);
* at a cut equal to or beyond the last input of a *complete* trace every position is determined and
  the interval is the point robustness of 02-templates.md section 1.3 (Lemma 2), which is what the
  soundness tests use for "the robustness of a completion".

Out of scope here: lateness and reordering (the oracle receives the *accepted* trace), rho,
markers and paths.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

INF = math.inf
T_DAY_MS = 86_400_000  # definition of 01-signals-sampling.md section 1.4

# ------------------------------------------------------------------------------------------
# Grammar of 02-templates.md section 1.2: tokenizer and recursive-descent parser
# ------------------------------------------------------------------------------------------

_TOKEN = re.compile(
    r"\s*(?:(->|>=|<=|==)|([A-Za-z_][A-Za-z0-9_]*)|(\d+)|([()\[\],+\-]))"
)
_KEYWORDS = {"not", "and", "or", "since", "historically", "once", "inf", "age"}
_CMP = {">=", "<=", "=="}


@dataclass(frozen=True)
class Expr:
    """``term (+|- term)*``; a term is ('num', n), ('name', s) or ('age',)."""

    terms: tuple[tuple[int, tuple[object, ...]], ...]  # (sign, term)


@dataclass(frozen=True)
class Node:
    op: str  # hist once since not and or imp cmp ind
    kids: tuple[Node, ...] = ()
    lo: Expr | str | None = None  # interval lower bound (Expr) for temporal ops
    hi: Expr | str | None = None  # interval upper bound (Expr or 'inf')
    cmp: str | None = None
    left: Expr | None = None
    right: Expr | None = None
    name: str | None = None  # indicator signal


def _tokens(text: str) -> list[str]:
    out: list[str] = []
    pos = 0
    text = text.strip()
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if m is None or m.end() == pos:
            raise ValueError(f"bad character at {pos} in {text!r}")
        out.append(m.group(m.lastindex))  # type: ignore[arg-type]
        pos = m.end()
        while pos < len(text) and text[pos].isspace():
            pos += 1
    return out


class _Parser:
    def __init__(self, text: str) -> None:
        self.toks = _tokens(text)
        self.i = 0

    def peek(self) -> str | None:
        return self.toks[self.i] if self.i < len(self.toks) else None

    def take(self, expect: str | None = None) -> str:
        tok = self.peek()
        if tok is None or (expect is not None and tok != expect):
            raise ValueError(f"expected {expect!r}, got {tok!r}")
        self.i += 1
        return tok

    def formula(self) -> Node:
        return self.implication()

    def implication(self) -> Node:
        left = self.disjunction()
        if self.peek() == "->":
            self.take()
            return Node("imp", (left, self.implication()))
        return left

    def disjunction(self) -> Node:
        node = self.conjunction()
        while self.peek() == "or":
            self.take()
            node = Node("or", (node, self.conjunction()))
        return node

    def conjunction(self) -> Node:
        node = self.since_expr()
        while self.peek() == "and":
            self.take()
            node = Node("and", (node, self.since_expr()))
        return node

    def since_expr(self) -> Node:
        node = self.unary()
        if self.peek() == "since":
            raise ValueError("since is not used by the library and not implemented")
        return node

    def interval(self) -> tuple[Expr | str, Expr | str]:
        self.take("[")
        lo = self.bound()
        self.take(",")
        hi = self.bound()
        self.take("]")
        return lo, hi

    def bound(self) -> Expr | str:
        if self.peek() == "inf":
            self.take()
            return "inf"
        return self.expr()

    def unary(self) -> Node:
        tok = self.peek()
        if tok == "not":
            self.take()
            return Node("not", (self.unary(),))
        if tok == "historically":
            self.take()
            lo: Expr | str = Expr(((1, ("num", 0)),))
            hi: Expr | str = "inf"
            if self.peek() == "[":
                lo, hi = self.interval()
            return Node("hist", (self.unary(),), lo=lo, hi=hi)
        if tok == "once":
            self.take()
            lo, hi = self.interval()
            return Node("once", (self.unary(),), lo=lo, hi=hi)
        if tok == "(":
            self.take()
            node = self.formula()
            self.take(")")
            return node
        return self.atom()

    def atom(self) -> Node:
        left = self.expr()
        if self.peek() in _CMP:
            cmp = self.take()
            right = self.expr()
            return Node("cmp", cmp=cmp, left=left, right=right)
        if (
            len(left.terms) == 1
            and left.terms[0][0] == 1
            and left.terms[0][1][0] == "name"
        ):
            return Node("ind", name=str(left.terms[0][1][1]))
        raise ValueError("an atom without a comparison must be a signal")

    def expr(self) -> Expr:
        terms = [(1, self.term())]
        while self.peek() in ("+", "-"):
            sign = 1 if self.take() == "+" else -1
            terms.append((sign, self.term()))
        return Expr(tuple(terms))

    def term(self) -> tuple[object, ...]:
        tok = self.take()
        if tok == "age":
            return ("age",)
        if tok.isdigit():
            return ("num", int(tok))
        return ("name", tok)


def parse(text: str) -> Node:
    parser = _Parser(text)
    node = parser.formula()
    if parser.peek() is not None:
        raise ValueError(f"trailing tokens in {text!r}")
    return node


def body_of(formula: str, conjunct: int = 0) -> Node:
    """The consequent of ``historically(A -> C)``; for COUNT the consequent of conjunct 0 or 1."""
    root = parse(formula)
    if root.op == "and":
        root = root.kids[conjunct]
    assert root.op == "hist", root.op
    imp = root.kids[0]
    assert imp.op == "imp", imp.op
    return imp.kids[1]


# ------------------------------------------------------------------------------------------
# The accepted trace and its dense grid values
# ------------------------------------------------------------------------------------------


@dataclass
class Trace:
    """An accepted trace: no lateness, no reorder. Times are integer ms."""

    step_ms: int
    samples: list[tuple[str, int, float]] = field(
        default_factory=list
    )  # (signal, t, value)
    events: list[tuple[str, int]] = field(default_factory=list)  # (kind, t)
    # robot channel -> inclusive (first_step, last_step) ranges of unavailability
    unavailable: dict[str, list[tuple[int, int]]] = field(default_factory=dict)

    def k_up(self, t: int) -> int:
        return (t + self.step_ms - 1) // self.step_ms


@dataclass(frozen=True)
class Params:
    values: Mapping[str, float]
    bp_lower: float
    bp_upper: float
    step_ms: int

    def value(self, name: str) -> float:
        if name == "step_ms":
            return float(self.step_ms)
        return float(self.values[name])


@dataclass(frozen=True)
class Inst:
    template: str  # range sched hold count resp sys int
    key: str
    anchor_ms: int
    k_a: int
    k_d: int
    horizon: int  # closing step H of the body (05 section 2.3)
    conjunct: int = 0  # COUNT: 0 limit, 1 day end
    act: int = 0
    pre: float = math.nan  # captured pre-dose value (RESP)
    day_end: bool = False


_IMPULSE_KINDS = {
    "meas": "measurement",
    "dispense": "dispense",
    "intake": "intake",
    "sched_tick": "schedule_tick",
}
_HELD = ("bp", "cuff_health", "inflation_ms", "presence")


class Grid:
    """Dense intervals of every signal position for the prefix ``cut``, steps 0..n."""

    def __init__(self, trace: Trace, params: Params, cut: int, n: int) -> None:
        self.trace = trace
        self.params = params
        self.cut = cut
        self.n = n
        ts = trace.step_ms
        # multiplicities of the impulses per step, steps <= cut only
        self.mult: dict[str, list[int]] = {s: [0] * (n + 1) for s in _IMPULSE_KINDS}
        for sig, kind in _IMPULSE_KINDS.items():
            for knd, t in trace.events:
                if knd == kind:
                    j = trace.k_up(t)
                    if 0 <= j <= min(cut, n):
                        self.mult[sig][j] += 1
        self.mult["auth"] = [0] * (n + 1)
        for sig, t, _v in trace.samples:
            if sig == "auth":
                j = trace.k_up(t)
                if 0 <= j <= min(cut, n):
                    self.mult["auth"][j] += 1
        # held values: the sample with the largest device time <= t_j (last in list order on ties)
        self.held: dict[str, list[float]] = {}
        for sig in _HELD:
            arr = [math.nan] * (n + 1)
            samples = sorted(
                (t, idx, v) for idx, (s, t, v) in enumerate(trace.samples) if s == sig
            )
            pointer = 0
            current = math.nan
            for j in range(min(cut, n) + 1):
                while pointer < len(samples) and samples[pointer][0] <= j * ts:
                    current = samples[pointer][2]
                    pointer += 1
                arr[j] = current
            self.held[sig] = arr

    # -- positions -----------------------------------------------------------------------

    def unavailable(self, sig: str, j: int) -> bool:
        return any(a <= j <= b for a, b in self.trace.unavailable.get(sig, ()))

    def pos(self, sig: str, j: int) -> tuple[float, float]:
        """Value interval of a position (05 section 2.1)."""
        assert j >= 0, "windows are truncated at the first step of the trace"
        p = self.params
        if sig == "bp":
            if j <= self.cut and j <= self.n and not math.isnan(self.held["bp"][j]):
                v = self.held["bp"][j]
                return (v, v)
            return (p.bp_lower, p.bp_upper)
        if sig in ("cuff_health", "presence"):
            if j <= self.cut and not math.isnan(self.held[sig][j]):
                if sig == "presence" and self.unavailable(sig, j):
                    return (0.0, 1.0)
                v = self.held[sig][j]
                return (v, v)
            return (0.0, 1.0)
        if sig == "inflation_ms":
            if j <= self.cut and not math.isnan(self.held[sig][j]):
                v = self.held[sig][j]
                return (v, v)
            return (0.0, INF)
        if sig in ("meas", "dispense", "intake", "sched_tick", "auth"):
            if sig == "intake" and self.unavailable("intake", j):
                return (0.0, 1.0)
            if j <= self.cut:
                v = float(min(self.mult[sig][j], 1))
                return (v, v)
            return (0.0, 1.0)
        raise KeyError(sig)

    def dose_count(self, j: int) -> tuple[float, float]:
        """Trailing 24 h window of dispense multiplicities, steps (j - K, j] (01 section 5.1)."""
        k_day = T_DAY_MS // self.trace.step_ms
        known = 0
        open_step = False
        for s in range(max(j - k_day + 1, 0), j + 1):
            if s <= self.cut:
                known += self.mult["dispense"][s] if s <= self.n else 0
            else:
                open_step = True
        return (float(known), INF if open_step else float(known))


# ------------------------------------------------------------------------------------------
# Structural interval recursion (05 section 2.2)
# ------------------------------------------------------------------------------------------


def _ind_interval(v: tuple[float, float]) -> tuple[float, float]:
    return (INF if v[0] == 1 else -INF, INF if v[1] == 1 else -INF)


class Evaluator:
    def __init__(self, grid: Grid, inst: Inst) -> None:
        self.g = grid
        self.inst = inst
        self.ts = grid.trace.step_ms

    # terms ---------------------------------------------------------------------------------

    def term(self, t: tuple[object, ...], j: int) -> tuple[float, float]:
        kind = t[0]
        if kind == "num":
            v = float(t[1])  # type: ignore[arg-type]
            return (v, v)
        if kind == "age":
            v = float((self.inst.k_d - j) * self.ts)
            return (v, v)
        name = str(t[1])
        if name in self.g.params.values or name == "step_ms":
            v = self.g.params.value(name)
            return (v, v)
        if name == "bp_drop":
            lo_pre, hi_pre = self.pre_interval()
            lo_bp, hi_bp = self.g.pos("bp", j)
            return (lo_pre - hi_bp, hi_pre - lo_bp)
        if name == "dose_count":
            return self.g.dose_count(j)
        return self.g.pos(name, j)

    def pre_interval(self) -> tuple[float, float]:
        if math.isnan(self.inst.pre):
            return (self.g.params.bp_lower, self.g.params.bp_upper)
        return (self.inst.pre, self.inst.pre)

    def expr(self, e: Expr, j: int) -> tuple[float, float]:
        lo = hi = 0.0
        first = True
        for sign, t in e.terms:
            a, b = self.term(t, j)
            if first:
                lo, hi = a, b
                first = False
            elif sign > 0:
                lo, hi = lo + a, hi + b
            else:
                lo, hi = lo - b, hi - a
        return lo, hi

    def bound_steps(self, b: Expr | str | None) -> float:
        if b == "inf":
            return INF
        assert isinstance(b, Expr)
        v, _ = self.expr(b, 0)
        assert v % self.ts == 0, f"window bound {v} is not a multiple of {self.ts}"
        return v // self.ts

    # nodes ---------------------------------------------------------------------------------

    def ev(
        self, node: Node, j: int, rewrite: Callable[[Node], Node] | None = None
    ) -> tuple[float, float]:
        op = node.op
        if op == "ind":
            assert node.name is not None
            return _ind_interval(self.g.pos(node.name, j))
        if op == "cmp":
            assert node.left is not None and node.right is not None
            if node.cmp == "==":
                (vl, vh) = self.expr(node.left, j)
                (cl, ch) = self.expr(node.right, j)
                assert cl == ch
                if vl == vh == cl:
                    return (INF, INF)
                if cl < vl or cl > vh:
                    return (-INF, -INF)
                return (-INF, INF)
            (l1, h1) = self.expr(node.left, j)
            (l2, h2) = self.expr(node.right, j)
            if node.cmp == ">=":
                return (l1 - h2, h1 - l2)
            return (l2 - h1, h2 - l1)
        if op == "not":
            lo, hi = self.ev(node.kids[0], j)
            return (-hi, -lo)
        if op == "and":
            a = self.ev(node.kids[0], j)
            b = self.ev(node.kids[1], j)
            return (min(a[0], b[0]), min(a[1], b[1]))
        if op == "or":
            a = self.ev(node.kids[0], j)
            b = self.ev(node.kids[1], j)
            return (max(a[0], b[0]), max(a[1], b[1]))
        if op == "imp":
            a = self.ev(node.kids[0], j)
            b = self.ev(node.kids[1], j)
            return (max(-a[1], b[0]), max(-a[0], b[1]))
        if op in ("once", "hist"):
            lo_steps = self.bound_steps(node.lo)
            hi_steps = self.bound_steps(node.hi)
            first = 0 if hi_steps == INF else max(int(j - hi_steps), 0)
            last = int(j - lo_steps)
            steps = range(first, last + 1)
            if not steps:
                return (-INF, -INF) if op == "once" else (INF, INF)
            vals = [self.ev(node.kids[0], s) for s in steps]
            if op == "once":
                return (max(v[0] for v in vals), max(v[1] for v in vals))
            return (min(v[0] for v in vals), min(v[1] for v in vals))
        raise ValueError(op)


# ------------------------------------------------------------------------------------------
# Instances (02-templates.md section 1.5, 05 section 2.3) and the verdict rule (05 section 3.4)
# ------------------------------------------------------------------------------------------

_B_PARAM = {"sched": "sched_window", "resp": "delta2"}


def body_steps(template: str, params: Params) -> int:
    name = _B_PARAM.get(template)
    if name is None:
        return 0
    return int(params.value(name) // params.step_ms)


def capture_pre(trace: Trace, dispense_ms: int) -> float:
    """01 section 5.3: the latest bp sample with device time <= the dispense (M5: ties count)."""
    best_t = None
    best = math.nan
    for sig, t, v in trace.samples:
        if sig == "bp" and t <= dispense_ms and (best_t is None or t >= best_t):
            best_t, best = t, v
    return best


def make_instances(
    trace: Trace,
    params: Params,
    *,
    sched_anchors: Sequence[int] = (),
    day_end_anchors: Sequence[int] = (),
    day_close_step: int | None = None,
) -> list[Inst]:
    """The instances of a trace: dynamic ones from the events, static ones from the plan."""
    ts = trace.step_ms
    k_day = T_DAY_MS // ts

    def close_of(k_a: int) -> int:
        return (
            ((max(k_a, 1) - 1) // k_day + 1) * k_day
            if day_close_step is None
            else day_close_step
        )

    out: list[Inst] = []
    for kind, t in sorted(trace.events, key=lambda e: e[1]):
        k_a = trace.k_up(t)
        if kind == "measurement":
            for tid in ("range", "sys"):
                out.append(Inst(tid, f"{tid}@{t}", t, k_a, k_a, k_a, act=k_a))
        elif kind == "dispense":
            pre = capture_pre(trace, t)
            b = body_steps("resp", params)
            for tid in ("hold", "count", "resp", "int"):
                kd = k_a + (b if tid == "resp" else 0)
                out.append(
                    Inst(
                        tid,
                        f"{tid}@{t}",
                        t,
                        k_a,
                        kd,
                        kd,
                        act=k_a,
                        pre=pre if tid == "resp" else math.nan,
                    )
                )
    ticks = sorted(sched_anchors)
    for idx, a in enumerate(ticks):
        k_a = trace.k_up(a)
        k_d = k_a + body_steps("sched", params)
        k_next = trace.k_up(ticks[idx + 1]) if idx + 1 < len(ticks) else INF
        horizon = max(k_d, int(min(k_next, close_of(k_a))))
        out.append(Inst("sched", f"sched@{a}", a, k_a, k_d, horizon, act=k_a))
    for a in day_end_anchors:
        k_a = trace.k_up(a)
        out.append(
            Inst(
                "count",
                f"count@{a}",
                a,
                k_a,
                k_a,
                k_a,
                conjunct=1,
                act=max(k_a - k_day, 0),
                day_end=True,
            )
        )
    return out


def grid_for(trace: Trace, params: Params, k: int, insts: Sequence[Inst]) -> Grid:
    """The dense grid of the prefix ``k`` wide enough for every instance in ``insts``."""
    return Grid(trace, params, k, max([k, *(i.horizon for i in insts)]) + 1)


def interval(
    trace: Trace,
    params: Params,
    formulas: Mapping[str, str],
    inst: Inst,
    k: int,
    grid: Grid | None = None,
) -> tuple[float, float]:
    """Robustness interval of ``inst`` on the prefix of step ``k`` (05 section 2.2 and 2.3)."""
    if grid is None:
        grid = grid_for(trace, params, k, [inst])
    assert grid.cut == k and grid.n >= inst.horizon
    ev = Evaluator(grid, inst)
    body = body_of(formulas[inst.template], inst.conjunct)
    if inst.template == "sched":
        # graded body: once[0, H - k_a] (meas and age >= 0) at the closing step (05 section 2.3)
        width = (inst.horizon - inst.k_a) * params.step_ms
        body = Node(
            "once",
            body.kids,
            lo=body.lo,
            hi=Expr(((1, ("num", width)),)),
        )
    return ev.ev(body, inst.horizon)


def classify(lo: float, hi: float, k: int, k_d: int) -> str:
    """Rule 1 and the tie rule (05 section 3.4); the instance is PENDING when no rule fires."""
    if hi < 0:
        return "violated"
    if lo > 0 or (k >= k_d and lo == 0 and hi == 0):
        return "satisfied"
    return "pending"


def first_decision(
    trace: Trace,
    params: Params,
    formulas: Mapping[str, str],
    inst: Inst,
    until: int,
) -> tuple[str, int | None]:
    """State at ``until`` and the first deciding step, by applying the rule step by step.

    A definitive state is absorbing (05 section 6.2): the rule is applied afresh only while PENDING.
    """
    state, decided = "pending", None
    for k in range(inst.act, until + 1):
        lo, hi = interval(trace, params, formulas, inst, k)
        if state == "pending":
            now = classify(lo, hi, k, inst.k_d)
            if now != "pending":
                state, decided = now, k
    return state, decided
