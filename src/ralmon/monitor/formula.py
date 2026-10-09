"""The grammar of ``Template.formula_past_time`` and the paths of its sub-formulas.

The parser reads the EBNF of docs/formal/02-templates.md section 1.2 into a tree. The monitor does not
evaluate the tree; it implements the closed forms of docs/formal/05 section 2.3 (Lemma 10), which are
the unrolling of the interval recursion of section 2.2 for the bodies of the seven strings. The tree
binds the two: a template library whose strings do not parse to exactly the reference strings below is
refused (``check_library_formulas``), and the child indices of the tree give ``subformula_path`` its
syntax.

Path syntax: ``<template id>/<element>/...``. An element is a child index counted from the root of the
parsed string (``historically`` and ``once`` have one child, ``not`` one, a binary operator two in
the order of the text), or, at the first position of a COUNT path, one of the labels ``limit`` and
``day_end`` for the two conjuncts. The last element may be the guard marker of the template.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from ralmon.monitor._text import show
from ralmon.monitor.config import MonitorConfigError, MonitorInputError
from ralmon.spec import Template, TemplateId

__all__ = [
    "GUARD_OF",
    "REFERENCE_FORMULAS",
    "Formula",
    "Node",
    "PathTable",
    "build_path_table",
    "check_library_formulas",
    "parse_formula",
    "resolve_subformula_path",
]

# algorithmic: the longest formula text and the deepest nesting the parser accepts, so that a hostile
# string cannot exhaust the stack or the memory
MAX_FORMULA_CHARS: Final[int] = 10_000
MAX_FORMULA_DEPTH: Final[int] = 96

# The seven strings of docs/formal/02-templates.md section 3.1: the formulas for which the closed
# forms of docs/formal/05 section 2.3 are the unrolled interval recursion.
REFERENCE_FORMULAS: Final[dict[TemplateId, str]] = {
    TemplateId.RANGE: "historically(meas -> (bp >= bp_band_low and bp <= bp_band_high))",
    TemplateId.SCHED: (
        "historically(once[sched_window, sched_window + step_ms] sched_tick -> "
        "once[0, sched_window] (meas and age >= 0))"
    ),
    TemplateId.HOLD: (
        "historically(dispense -> (once[0, hold_lookback] meas and bp >= bp_hold_threshold))"
    ),
    TemplateId.COUNT: (
        "historically(dispense -> dose_count <= dose_max_24h) and "
        "historically(day_end -> dose_count >= dose_min_day_end)"
    ),
    TemplateId.RESP: (
        "historically(once[delta2, delta2 + step_ms] dispense -> "
        "once[0, delta2 - delta1] (meas and bp_drop >= delta_resp))"
    ),
    TemplateId.SYS: (
        "historically(meas -> (cuff_health == 1 and inflation_ms >= cuff_inflation_min))"
    ),
    TemplateId.INT: (
        "historically(dispense -> once[0, inf] ((presence or intake or auth) and age <= int_window))"
    ),
}

# docs/formal/02-templates.md section 2.1: the marker of the guard whose failure makes the value -inf
GUARD_OF: Final[dict[TemplateId, str | None]] = {
    TemplateId.RANGE: None,
    TemplateId.SCHED: "no_measurement_after_tick",
    TemplateId.HOLD: "no_recent_measurement",
    TemplateId.COUNT: None,
    TemplateId.RESP: "obligation_unmet",
    TemplateId.SYS: "cuff_unhealthy",
    TemplateId.INT: "no_witness",
}

# the sub-formulas whose path a record can carry, by role: the text of the node in the reference string
_ROLE_TEXT: Final[dict[TemplateId, dict[str, str]]] = {
    TemplateId.RANGE: {"lower": "bp >= bp_band_low", "upper": "bp <= bp_band_high"},
    TemplateId.SCHED: {"guard": "meas", "margin": "age >= 0"},
    TemplateId.HOLD: {
        "guard": "once[0, hold_lookback] meas",
        "margin": "bp >= bp_hold_threshold",
    },
    TemplateId.COUNT: {
        "limit": "dose_count <= dose_max_24h",
        "day_end": "dose_count >= dose_min_day_end",
    },
    TemplateId.RESP: {"guard": "meas", "margin": "bp_drop >= delta_resp"},
    TemplateId.SYS: {
        "guard": "cuff_health == 1",
        "margin": "inflation_ms >= cuff_inflation_min",
    },
    TemplateId.INT: {
        "guard": "(presence or intake) or auth",
        "margin": "age <= int_window",
    },
}
_COUNT_LABELS: Final[tuple[str, str]] = ("limit", "day_end")

_TOKEN: Final = re.compile(
    r"\s*(?:(->|>=|<=|==)|([a-z][a-z0-9_]*)|(\d+)|([()\[\],+\-]))"
)
_BINARY: Final = frozenset({"and", "or", "imp", "since"})

Term = tuple[str | int, ...]
Expr = tuple[tuple[int, Term], ...]


@dataclass(frozen=True, slots=True)
class Node:
    """A node of a parsed formula. ``op`` is hist, once, since, not, and, or, imp, cmp or ind."""

    op: str
    kids: tuple[Node, ...] = ()
    lo: Expr | str | None = (
        None  # interval of a temporal operator: an expression or "inf"
    )
    hi: Expr | str | None = None
    cmp: str | None = None
    left: Expr | None = None
    right: Expr | None = None
    name: str | None = None  # the signal of an indicator atom


def _render_term(term: Term) -> str:
    return "age" if term[0] == "age" else str(term[1])


def _render_expr(expr: Expr | str) -> str:
    if isinstance(expr, str):
        return expr
    out = ""
    for index, (sign, term) in enumerate(expr):
        text = _render_term(term)
        out += text if index == 0 else (" + " if sign > 0 else " - ") + text
    return out


def render(node: Node) -> str:
    """The canonical text of a node: binary operands that are not atoms are parenthesised."""
    op = node.op
    if op == "ind":
        return str(node.name)
    if op == "cmp":
        assert node.left is not None and node.right is not None
        return f"{_render_expr(node.left)} {node.cmp} {_render_expr(node.right)}"

    def wrap(child: Node) -> str:
        text = render(child)
        return text if child.op in ("ind", "cmp") else f"({text})"

    if op == "not":
        return f"not {wrap(node.kids[0])}"
    if op in ("hist", "once"):
        name = "historically" if op == "hist" else "once"
        return f"{name}[{_render_expr(node.lo or '0')}, {_render_expr(node.hi or 'inf')}] {wrap(node.kids[0])}"
    word = {"and": "and", "or": "or", "imp": "->"}.get(op)
    if word is not None:
        return f"{wrap(node.kids[0])} {word} {wrap(node.kids[1])}"
    if op == "since":
        return (
            f"{wrap(node.kids[0])} since[{_render_expr(node.lo or '0')}, "
            f"{_render_expr(node.hi or 'inf')}] {wrap(node.kids[1])}"
        )
    raise MonitorConfigError(
        f"unknown operator {op!r}"
    )  # pragma: no cover - the parser makes no other


class _Parser:
    def __init__(self, text: str) -> None:
        self.tokens = self._tokenize(text)
        self.index = 0
        self.depth = 0

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        out: list[str] = []
        position = 0
        length = len(text.rstrip())
        while position < length:
            match = _TOKEN.match(text, position)
            if match is None or match.end() == position:
                raise MonitorConfigError(
                    f"formula: unexpected text at position {position}"
                )
            out.append(match.group(match.lastindex or 0).strip())
            position = match.end()
        return out

    def peek(self) -> str | None:
        return self.tokens[self.index] if self.index < len(self.tokens) else None

    def take(self, expected: str | None = None) -> str:
        token = self.peek()
        if token is None or (expected is not None and token != expected):
            raise MonitorConfigError(
                f"formula: expected {expected or 'more text'}, got {token!r}"
            )
        self.index += 1
        return token

    def enter(self) -> None:
        self.depth += 1
        if self.depth > MAX_FORMULA_DEPTH:
            raise MonitorConfigError(
                f"formula: nesting deeper than {MAX_FORMULA_DEPTH}"
            )

    def leave(self) -> None:
        self.depth -= 1

    # formula = implication ; implication = disjunction [ "->" implication ] ;
    def formula(self) -> Node:
        self.enter()
        left = self.disjunction()
        if self.peek() == "->":
            self.take()
            left = Node("imp", (left, self.formula()))
        self.leave()
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
            self.take()
            lo: Expr | str = ((1, ("num", 0)),)
            hi: Expr | str = "inf"
            if self.peek() == "[":
                lo, hi = self.interval()
            return Node("since", (node, self.unary()), lo=lo, hi=hi)
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
        self.enter()
        token = self.peek()
        node: Node
        if token == "not":
            self.take()
            node = Node("not", (self.unary(),))
        elif token == "historically":
            self.take()
            lo: Expr | str = ((1, ("num", 0)),)
            hi: Expr | str = "inf"
            if self.peek() == "[":
                lo, hi = self.interval()
            node = Node("hist", (self.unary(),), lo=lo, hi=hi)
        elif token == "once":
            self.take()
            lo, hi = self.interval()
            node = Node("once", (self.unary(),), lo=lo, hi=hi)
        elif token == "(":
            self.take()
            node = self.formula()
            self.take(")")
        else:
            node = self.atom()
        self.leave()
        return node

    def atom(self) -> Node:
        left = self.expr()
        if self.peek() in (">=", "<=", "=="):
            comparison = self.take()
            return Node("cmp", cmp=comparison, left=left, right=self.expr())
        if len(left) == 1 and left[0][0] == 1 and left[0][1][0] == "name":
            return Node("ind", name=str(left[0][1][1]))
        raise MonitorConfigError(
            "formula: an atom without a comparison must be a signal"
        )

    def expr(self) -> Expr:
        terms = [(1, self.term())]
        while self.peek() in ("+", "-"):
            sign = 1 if self.take() == "+" else -1
            terms.append((sign, self.term()))
        return tuple(terms)

    def term(self) -> Term:
        token = self.take()
        if token == "age":
            return ("age",)
        if token.isdigit():
            return ("num", int(token))
        if re.fullmatch(r"[a-z][a-z0-9_]*", token) and token not in (
            "not",
            "and",
            "or",
            "since",
            "historically",
            "once",
            "inf",
        ):
            return ("name", token)
        raise MonitorConfigError(
            f"formula: unexpected {token!r} where a term is expected"
        )


@dataclass(frozen=True, slots=True)
class Formula:
    """A parsed formula; equality is structural, so whitespace is not structure."""

    root: Node

    @property
    def text(self) -> str:
        return render(self.root)

    def node_at(self, indices: Sequence[int]) -> Node:
        node = self.root
        for index in indices:
            if not 0 <= index < len(node.kids):
                raise MonitorInputError(
                    f"path: node {render(node)!r} has no child {index}"
                )
            node = node.kids[index]
        return node

    def find(self, text: str) -> tuple[int, ...]:
        """The indices of the first node, in preorder, whose canonical text is ``text``."""
        found = _find(self.root, text, ())
        if found is None:
            raise MonitorConfigError(
                f"formula: no sub-formula {text!r} in {self.text!r}"
            )
        return found


def _find(node: Node, text: str, path: tuple[int, ...]) -> tuple[int, ...] | None:
    if render(node) == text:
        return path
    for index, child in enumerate(node.kids):
        found = _find(child, text, (*path, index))
        if found is not None:
            return found
    return None


def parse_formula(text: object) -> Formula:
    """Parse a template string; anything outside the grammar raises ``MonitorConfigError``."""
    if not isinstance(text, str):
        raise MonitorConfigError(f"a formula must be a str, got {show(text)}")
    if len(text) > MAX_FORMULA_CHARS:
        raise MonitorConfigError(f"formula: longer than {MAX_FORMULA_CHARS} characters")
    parser = _Parser(text)
    if not parser.tokens:
        raise MonitorConfigError("formula: empty")
    node = parser.formula()
    if parser.peek() is not None:
        raise MonitorConfigError(
            f"formula: unexpected {parser.peek()!r} after the formula"
        )
    return Formula(node)


def check_library_formulas(templates: Sequence[Template]) -> None:
    """Refuse a library whose string differs (structurally) from the reference string of its id."""
    for template in templates:
        reference = parse_formula(REFERENCE_FORMULAS[template.id])
        got = parse_formula(template.formula_past_time)
        if got != reference:
            raise MonitorConfigError(
                f"template {template.id.value}: formula_past_time {template.formula_past_time!r} differs "
                f"from the formula {reference.text!r} that the closed forms of docs/formal/05 "
                "section 2.3 implement"
            )


@dataclass(frozen=True, slots=True)
class PathTable:
    """The child indices of the roles of one template, from the reference string."""

    template: TemplateId
    roles: dict[str, tuple[int, ...]]

    def path(self, role: str, marker: str | None = None) -> str:
        indices = self.roles[role]
        elements = [self.template.value]
        if self.template is TemplateId.COUNT:
            elements.append(_COUNT_LABELS[indices[0]])
            elements.extend(str(i) for i in indices[1:])
        else:
            elements.extend(str(i) for i in indices)
        if marker is not None:
            elements.append(marker)
        return "/".join(elements)


def build_path_table(template_id: TemplateId) -> PathTable:
    formula = parse_formula(REFERENCE_FORMULAS[template_id])
    return PathTable(
        template_id,
        {role: formula.find(text) for role, text in _ROLE_TEXT[template_id].items()},
    )


def resolve_subformula_path(template: Template, path: object) -> str:
    """The canonical text of the sub-formula that ``path`` names in the string of ``template``.

    The last element may be the guard marker of the template (it names a failed guard and does not
    change what the path resolves to). Raises ``MonitorInputError`` for a path that does not resolve.
    """
    if not isinstance(path, str) or not path:
        raise MonitorInputError(f"a path must be a non-empty str, got {show(path)}")
    elements = path.split("/")
    if elements[0] != template.id.value:
        raise MonitorInputError(
            f"path {show(path)} does not start with the template id {template.id.value!r}"
        )
    formula = parse_formula(template.formula_past_time)
    marker = GUARD_OF.get(template.id)
    indices: list[int] = []
    for position, element in enumerate(elements[1:], start=1):
        if element.isdigit() and element.isascii():
            indices.append(int(element))
        elif (
            template.id is TemplateId.COUNT
            and position == 1
            and element in _COUNT_LABELS
        ):
            indices.append(_COUNT_LABELS.index(element))
        elif position == len(elements) - 1 and marker is not None and element == marker:
            break
        else:
            raise MonitorInputError(
                f"path {show(path)}: unknown element {show(element)}"
            )
    return render(formula.node_at(indices))
