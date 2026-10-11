"""The likelihood attributor (``LikelihoodRule``, ``load_likelihood_table``): ADR-074, WS05-T12.

Specification: ``docs/models/attribution-likelihood.md`` (WS02-T06), which this module implements without adding to
it, and the machine-readable table ``configs/attribution_likelihood.yaml``. For a violated instance of template ``t``
with the evidence vector ``e`` the rule computes, over the COMPONENTS (a subtype at a knowledge level) that can violate
``t``::

    p(s | e, t)  proportional to  prior_t(class(s)) * pi(s | class(s), t) * product over f in R_t of P(class_f | s)

* ``posterior_subtypes`` returns the posterior merged to SUBTYPES, over the subtypes applicable at the template only
  (it sums to 1); ``posterior`` is its sum by class (``Alert.p_kappa``, keys C1, C2, C3); ``kappa`` is the class with the
  largest ``p_kappa`` if that value is at least ``tau``, otherwise ``UNDETERMINED`` (a tie at the maximum is also
  ``UNDETERMINED``; ``UNDETERMINED`` is not a key of ``p_kappa``).
* ``R_t`` is the set of fields the YAML lists for the template (the relevance map of ``attribution-rule.md`` plus the
  data-scope masks of the specification: the dispenser group for ``hold``, ``count``, ``resp`` and ``int``,
  ``signal_quality.cuff_value_repeated`` for ``range``, ``sched``, ``hold``, ``resp`` and ``sys``), minus the fields of
  the run options: the profile ``without_diagnostics`` removes ``system.diagnostics_ok``; the mask A4 removes the four
  witness and robot-task fields of ``masks.a4.cells_removed``. The rule reads nothing else (invariant I1: neither rho,
  nor the interval, nor the verdict state, nor a time of the record, nor a ground truth; ``violated`` is not read, the
  template is the one of the provenance of the vector). A field that is ``None``, out of its domain or of the class K
  contributes the factor 1.
* The pair (``system.ble_link_quality``, ``system.seq_gap``) is ONE joint cell in the reference
  (``grouped_variant="reference"``); ``"fully_independent"`` multiplies the two marginals,
  ``"reference_plus_cross_device"`` also groups the cross-device fields with the common cause ``ecg_noise``.

NO NUMBER IS DEFAULTED HERE. Every parameter (``eps``, ``qc``, ``q_stale``, ``rep_nat``, ``delta``,
``dispense_bounce_interval_ms``, ``tau``, ``cumulative_level``) and the two designs (``class_priors``, ``pi_designs``) is
a row ``awaiting_human_value`` of the file. The rule is built with ``sensitivity_values``, a mapping name -> value; each
value is recorded in ``metadata`` with the label of the file ("sensitivity, not a proposal"). A name that a live cell
needs and that is not supplied makes construction raise ``AwaitingValueError``. A parameter that no cell read in the run
uses (``q_stale`` without the driver diagnostics, ``delta`` under A4) is not required.

The decision record (``Decision`` of ``rule.py``) carries ``p_kappa``, the subtype posterior, the set, the log
likelihood contributions per component and per class, and the decisive fields (``evidence_used``): the fields whose
reading favours the leading class against the rest (single-field log likelihood ratio of the pi-weighted class mixture
against the mixture of the other classes weighted by their posterior mass, larger than numerical zero), most favourable
first. They are traceability of the table,
not an explanation of the cause. The set is the cumulative-level set unless the attributor injects a selector (the
conformal set of WS05-T14, which this package may not import, see ``tests/test_layering.py``).

The prior-free pair quantity of ADR-074 decision 3 is ``log_likelihood_ratio`` and ``pair_statistic``.
"""

from __future__ import annotations

import ast
import hashlib
import json
import logging
import math
import operator
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from itertools import product
from pathlib import Path
from typing import Any, Final, TypeGuard

import yaml

from ralmon.attribution.alert import AttributedCause
from ralmon.attribution.evidence import (
    NON_PROVENANCE_PATHS,
    EvidenceVector,
    get_evidence,
    template_kind_of,
)
from ralmon.attribution.rule import AbstentionReason, Decision, HierarchicalRule
from ralmon.monitor import VerdictRecord
from ralmon.spec import ParameterRegistry, TemplateId, TemplateKind

__all__ = [
    "AwaitingValueError",
    "Component",
    "LikelihoodConfigError",
    "LikelihoodInputError",
    "LikelihoodRule",
    "LikelihoodTable",
    "load_likelihood_table",
]

log = logging.getLogger(__name__)

AWAITING: Final = "awaiting_human_value"
SUPPORTED_SCHEMA: Final = ("0.1.0",)
CLASS_ORDER: Final = ("C1", "C2", "C3")
_CAUSE: Final = {
    "C1": AttributedCause.C1_CLINICAL,
    "C2": AttributedCause.C2_SYSTEM,
    "C3": AttributedCause.C3_INTEGRITY,
}
DIAG_PATH: Final = "system.diagnostics_ok"
INTERVAL_PATH: Final = "dispenser.interval_since_previous_ms"
CONTENT_PATH: Final = "dispenser.content_change"
THRESHOLD_PARAM: Final = "dispense_bounce_interval_ms"
#: numerical zero of the comparisons of two sums of logarithms (a tie of two class posteriors; a field that favours no
#: class). Not a modelling value.
NUMERICAL_ZERO: Final = 1e-12
_ORDER: Final = {p: i for i, p in enumerate(NON_PROVENANCE_PATHS)}
_DESIGN_NAMES: Final = ("class_priors", "pi_designs")
_TOP_KEYS: Final = (
    "schema_version",
    "parameters",
    "class_priors",
    "pi_designs",
    "templates",
    "masks",
    "subtypes",
    "components",
    "cell_tokens",
    "default_cell",
    "cells",
    "grouped_cells",
    "diagnostics_profiles",
    "sensitivity_design",
)
# the numerical domain each parameter must lie in for the logarithms to exist; structural, not a value
_DOMAIN: Final[dict[str, tuple[float, float, bool, bool]]] = {
    # name: (low, high, low_included, high_included)
    "eps": (0.0, 0.5, False, False),
    "qc": (0.0, 1.0, True, True),
    "q_stale": (0.0, 1.0, True, True),
    "rep_nat": (0.0, 1.0, True, False),
    "delta": (0.0, 1.0, True, True),
    "tau": (0.0, 1.0, False, True),
    "cumulative_level": (0.0, 1.0, False, False),
    THRESHOLD_PARAM: (0.0, math.inf, True, False),
}


class LikelihoodConfigError(ValueError):
    """The table file or the run options are invalid (a named configuration error, never a silent default)."""


class AwaitingValueError(LikelihoodConfigError):
    """Rows ``awaiting_human_value`` that the run reads have no value in ``sensitivity_values``."""

    def __init__(self, names: Sequence[str], message: str) -> None:
        super().__init__(message)
        self.names: tuple[str, ...] = tuple(names)


class LikelihoodInputError(ValueError):
    """The evidence cannot be evaluated (provenance inconsistent)."""


# ---- safe arithmetic of the forms of the file ----------------------------------------------------------------------------
_BINARY = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
_FUNCTIONS = {"max": max, "min": min}


def _compile(text: object, where: str) -> ast.expr:
    """The expression of a cell form or a mode weight: numbers, names, ``+ - * /``, ``max`` and ``min`` only."""
    if isinstance(text, bool) or not isinstance(text, (str, int, float)):
        raise LikelihoodConfigError(f"{where}: not an expression: {text!r}")
    try:
        tree = ast.parse(str(text).strip(), mode="eval")
    except SyntaxError:
        raise LikelihoodConfigError(f"{where}: cannot parse {text!r}") from None
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if (
                not isinstance(node.func, ast.Name)
                or node.func.id not in _FUNCTIONS
                or node.keywords
            ):
                raise LikelihoodConfigError(f"{where}: call not allowed in {text!r}")
        elif isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                raise LikelihoodConfigError(
                    f"{where}: constant not allowed in {text!r}"
                )
        elif isinstance(node, ast.BinOp):
            if type(node.op) not in _BINARY:
                raise LikelihoodConfigError(
                    f"{where}: operator not allowed in {text!r}"
                )
        elif isinstance(node, ast.UnaryOp):
            if not isinstance(node.op, (ast.USub, ast.UAdd)):
                raise LikelihoodConfigError(
                    f"{where}: operator not allowed in {text!r}"
                )
        elif not isinstance(
            node,
            (
                ast.Expression,
                ast.Name,
                ast.Load,
                ast.Add,
                ast.Sub,
                ast.Mult,
                ast.Div,
                ast.USub,
                ast.UAdd,
            ),
        ):
            raise LikelihoodConfigError(f"{where}: syntax not allowed in {text!r}")
    return tree.body


def _names(tree: ast.expr) -> set[str]:
    called = {id(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    return {
        n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and id(n) not in called
    }


def _evaluate(node: ast.expr, env: Mapping[str, float], where: str) -> float:
    if isinstance(node, ast.Constant) and _real(node.value):
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id not in env:
            raise AwaitingValueError(
                (node.id,),
                f"{where}: the parameter {node.id!r} has no value in this run",
            )
        return env[node.id]
    if isinstance(node, ast.UnaryOp):
        inner = _evaluate(node.operand, env, where)
        return -inner if isinstance(node.op, ast.USub) else inner
    if isinstance(node, ast.BinOp):
        return float(
            _BINARY[type(node.op)](
                _evaluate(node.left, env, where), _evaluate(node.right, env, where)
            )
        )
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        args = [_evaluate(a, env, where) for a in node.args]
        return float(_FUNCTIONS[node.func.id](*args))
    raise LikelihoodConfigError(f"{where}: unsupported expression")  # pragma: no cover


def _fraction_or_float(value: object, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise LikelihoodConfigError(f"{where}: not a number: {value!r}")
    try:
        number = float(Fraction(str(value)))
    except (ValueError, ZeroDivisionError):
        raise LikelihoodConfigError(f"{where}: not a number: {value!r}") from None
    if not math.isfinite(number):
        raise LikelihoodConfigError(f"{where}: not finite: {value!r}")
    return number


# ---- the table ----------------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Component:
    """A subtype at a knowledge level (``replay``, ``dispense_forgery`` and ``presence_spoof`` have two)."""

    id: str
    subtype: str
    level: str | None
    cls: str
    templates: frozenset[str]


def _need(mapping: Mapping[str, Any], key: str, where: str) -> Any:
    if not isinstance(mapping, Mapping) or key not in mapping:
        raise LikelihoodConfigError(f"{where}: missing key {key!r}")
    return mapping[key]


class LikelihoodTable:
    """``configs/attribution_likelihood.yaml``, loaded and checked for structure (no number is chosen here)."""

    def __init__(self, raw: Mapping[str, Any], sha256: str, path: Path | None) -> None:
        self.raw: Mapping[str, Any] = raw
        self.sha256 = sha256
        self.path = path
        for key in _TOP_KEYS:
            _need(raw, key, "the likelihood table")
        self.schema_version = str(raw["schema_version"])
        if self.schema_version not in SUPPORTED_SCHEMA:
            raise LikelihoodConfigError(
                f"unsupported schema_version {self.schema_version!r} (supported: {', '.join(SUPPORTED_SCHEMA)})"
            )
        self.parameters: dict[str, Mapping[str, Any]] = {}
        for row in raw["parameters"]:
            name = _need(row, "name", "a parameter row")
            if name in self.parameters:
                raise LikelihoodConfigError(f"duplicate parameter {name!r}")
            for key in ("status", "value", "sensitivity_label"):
                _need(row, key, f"parameter {name}")
            self.parameters[name] = row
        for name in _DOMAIN:
            if name not in self.parameters:
                raise LikelihoodConfigError(f"the table has no parameter row {name!r}")
        self.templates: dict[str, Mapping[str, Any]] = dict(raw["templates"])
        valid_templates = {t.value for t in TemplateId}
        if set(self.templates) != valid_templates:
            raise LikelihoodConfigError(
                f"templates must be exactly {sorted(valid_templates)}, got {sorted(self.templates)}"
            )
        for tid, spec in self.templates.items():
            for field in _need(spec, "reads", f"template {tid}"):
                if field not in NON_PROVENANCE_PATHS:
                    raise LikelihoodConfigError(
                        f"template {tid}: {field!r} is not a field of the evidence vector"
                    )
            for cls in _need(spec, "impossible_classes", f"template {tid}"):
                if cls not in CLASS_ORDER:
                    raise LikelihoodConfigError(
                        f"template {tid}: unknown class {cls!r}"
                    )
        self.subtype_class: dict[str, str] = {}
        self.subtype_in_benchmark: dict[str, bool] = {}
        for sub in raw["subtypes"]:
            name = _need(sub, "name", "a subtype row")
            cls = _need(sub, "class", f"subtype {name}")
            if cls not in CLASS_ORDER:
                raise LikelihoodConfigError(f"subtype {name}: unknown class {cls!r}")
            self.subtype_class[name] = cls
            self.subtype_in_benchmark[name] = bool(sub.get("in_benchmark_v1", False))
        components: list[Component] = []
        seen: set[str] = set()
        for row in raw["components"]:
            cid = _need(row, "id", "a component row")
            if cid in seen:
                raise LikelihoodConfigError(f"duplicate component {cid!r}")
            seen.add(cid)
            subtype = _need(row, "subtype", f"component {cid}")
            if self.subtype_class.get(subtype) != row.get("class"):
                raise LikelihoodConfigError(
                    f"component {cid}: subtype {subtype!r} is unknown or of another class"
                )
            tpl = frozenset(_need(row, "templates", f"component {cid}"))
            if not tpl <= valid_templates:
                raise LikelihoodConfigError(
                    f"component {cid}: unknown templates {sorted(tpl - valid_templates)}"
                )
            components.append(
                Component(cid, subtype, row.get("level"), row["class"], tpl)
            )
        self.components: tuple[Component, ...] = tuple(components)
        self.component_ids = frozenset(seen)
        # tokens
        self.tokens: dict[str, tuple[ast.expr, str]] = {}
        for tname, spec in raw["cell_tokens"].items():
            tree = _compile(_need(spec, "form", f"token {tname}"), f"token {tname}")
            param = _need(spec, "param", f"token {tname}")
            if not _names(tree) <= set(self.parameters):
                raise LikelihoodConfigError(
                    f"token {tname}: names a parameter the table does not have"
                )
            self.tokens[tname] = (tree, param)
        default_token = _need(raw["default_cell"], "token", "default_cell")
        if default_token not in self.tokens:
            raise LikelihoodConfigError(
                f"default_cell: unknown token {default_token!r}"
            )
        self.default_token: str = default_token
        # cells
        self.cell_token: dict[tuple[str, str], str] = {}
        for cell in raw["cells"]:
            comp = _need(cell, "component", "a cell")
            field = _need(cell, "field", "a cell")
            token = _need(cell, "token", f"cell {comp}/{field}")
            if comp not in self.component_ids:
                raise LikelihoodConfigError(f"cell: unknown component {comp!r}")
            if field not in NON_PROVENANCE_PATHS:
                raise LikelihoodConfigError(f"cell {comp}: unknown field {field!r}")
            if token not in self.tokens:
                raise LikelihoodConfigError(
                    f"cell {comp}/{field}: unknown token {token!r}"
                )
            if (comp, field) in self.cell_token:
                raise LikelihoodConfigError(f"duplicate cell {comp}/{field}")
            self.cell_token[(comp, field)] = token
        # groups
        self.groups: dict[str, Mapping[str, Any]] = dict(raw["grouped_cells"])
        self.group_modes: dict[str, dict[str, list[tuple[str, ast.expr]]]] = {}
        self.group_default: dict[str, list[tuple[str, ast.expr]] | None] = {}
        for gname, spec in self.groups.items():
            fields = list(_need(spec, "fields", f"group {gname}"))
            if not all(f in NON_PROVENANCE_PATHS for f in fields):
                raise LikelihoodConfigError(f"group {gname}: unknown field")
            if int(_need(spec, "K", f"group {gname}")) != 2 ** len(fields):
                raise LikelihoodConfigError(f"group {gname}: K must be 2 ** members")
            templates = spec.get("templates")
            if (
                templates != "all"
                and not set(templates if templates is not None else ())
                <= valid_templates
            ):
                raise LikelihoodConfigError(f"group {gname}: unknown templates")
            cmap = spec.get("joint_class_map")
            inverse = {v: k for k, v in cmap.items()} if cmap else None
            if cmap and set(cmap) != {
                ",".join(c) for c in product("AD", repeat=len(fields))
            }:
                raise LikelihoodConfigError(
                    f"group {gname}: joint_class_map is incomplete"
                )
            self.group_modes[gname] = {}
            for cid, modes in _need(spec, "modes", f"group {gname}").items():
                if cid not in self.component_ids:
                    raise LikelihoodConfigError(
                        f"group {gname}: unknown component {cid!r}"
                    )
                self.group_modes[gname][cid] = self._parse_modes(
                    modes, len(fields), inverse, f"group {gname}/{cid}"
                )
            default = spec.get("default_mode")
            self.group_default[gname] = (
                self._parse_modes(
                    default, len(fields), inverse, f"group {gname}/default_mode"
                )
                if isinstance(default, Mapping)
                else None
            )
        # designs
        self.class_designs: dict[str, dict[str, float]] = {}
        for dname, design in _need(
            raw["class_priors"], "designs", "class_priors"
        ).items():
            values = {
                c: _fraction_or_float(
                    _need(design, c, f"class prior {dname}"), f"class prior {dname}/{c}"
                )
                for c in CLASS_ORDER
            }
            if any(v <= 0 for v in values.values()):
                raise LikelihoodConfigError(
                    f"class prior {dname}: every class needs a positive weight"
                )
            self.class_designs[dname] = values
        groups = _need(raw["pi_designs"], "groups", "pi_designs")
        self.pi_groups: dict[str, frozenset[str]] = {
            g: frozenset(m) for g, m in groups.items()
        }
        for gname, members in self.pi_groups.items():
            if not members <= self.component_ids:
                raise LikelihoodConfigError(f"pi group {gname}: unknown component")
        self.pi_designs: dict[str, tuple[float, dict[str, float]]] = {}
        for dname, design in _need(raw["pi_designs"], "designs", "pi_designs").items():
            default_w = _fraction_or_float(
                _need(design, "default", f"pi design {dname}"), f"pi design {dname}"
            )
            weights = {
                g: _fraction_or_float(w, f"pi design {dname}/{g}")
                for g, w in _need(design, "weights", f"pi design {dname}").items()
            }
            if (
                default_w <= 0
                or any(w <= 0 for w in weights.values())
                or set(weights) - set(self.pi_groups)
            ):
                raise LikelihoodConfigError(
                    f"pi design {dname}: weights must be positive over known groups"
                )
            self.pi_designs[dname] = (default_w, weights)
        self.diagnostics_profiles: dict[str, Mapping[str, Any]] = dict(
            raw["diagnostics_profiles"]
        )
        for pname, spec in self.diagnostics_profiles.items():
            _need(spec, "reads_diagnostics_ok", f"profile {pname}")
        design = {d["name"]: d for d in raw["sensitivity_design"]}
        variant = design.get("grouped_variant")
        if variant is None or "reference" not in variant:
            raise LikelihoodConfigError(
                "sensitivity_design has no grouped_variant with a reference"
            )
        self.grouped_variants: tuple[str, ...] = tuple(variant["range"])
        self.grouped_variant_reference: str = variant["reference"]
        # masks
        masks = raw["masks"]
        self.data_scope: list[tuple[tuple[str, ...], frozenset[str]]] = []
        for entry in _need(masks, "data_scope", "masks").values():
            scoped = tuple(entry.get("fields") or [entry["field"]])
            if not all(f in NON_PROVENANCE_PATHS for f in scoped):
                raise LikelihoodConfigError("masks.data_scope: unknown field")
            self.data_scope.append((scoped, frozenset(entry["read_for"])))
        self.a4_removed: tuple[str, ...] = tuple(
            _need(_need(masks, "a4", "masks"), "cells_removed", "masks.a4")
        )
        if not all(f in NON_PROVENANCE_PATHS for f in self.a4_removed):
            raise LikelihoodConfigError("masks.a4: unknown field")

    @staticmethod
    def _parse_modes(
        modes: Mapping[str, Any],
        members: int,
        inverse: Mapping[str, str] | None,
        where: str,
    ) -> list[tuple[str, ast.expr]]:
        """The modes of a grouped cell: (joint class as "A,D,...", compiled weight)."""
        valid = {",".join(c) for c in product("AD", repeat=members)}
        out: list[tuple[str, ast.expr]] = []
        for key, weight in modes.items():
            combo = inverse[key] if inverse is not None and key in inverse else key
            if combo not in valid:
                raise LikelihoodConfigError(f"{where}: unknown joint class {key!r}")
            out.append((combo, _compile(weight, f"{where}/{key}")))
        return out


def load_likelihood_table(path: str | Path) -> LikelihoodTable:
    """Load and check ``configs/attribution_likelihood.yaml`` (a path is required: there is no default location)."""
    target = Path(path)
    try:
        data = target.read_bytes()
    except OSError as error:
        raise LikelihoodConfigError(
            f"cannot read {target}: {error.strerror or error}"
        ) from None
    try:
        raw = yaml.safe_load(data.decode("utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError) as error:
        raise LikelihoodConfigError(f"cannot parse {target}: {error}") from None
    if not isinstance(raw, dict):
        raise LikelihoodConfigError(f"{target}: the top level must be a mapping")
    return LikelihoodTable(raw, hashlib.sha256(data).hexdigest(), target)


# ---- the rule -----------------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Plan:
    """What is fixed for a template once the options are known."""

    reads: tuple[str, ...]
    components: tuple[Component, ...]
    classes: tuple[str, ...]
    log_weight: Mapping[
        str, float
    ]  # log(prior_t(class)) + log(pi(component | class, t))
    pi: Mapping[str, float]
    groups: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Evaluation:
    template: TemplateId
    plan: _Plan
    terms: Mapping[str, Mapping[str, float]]  # component -> field key -> log P
    components: Mapping[str, float]  # component -> posterior
    subtypes: Mapping[str, float]
    classes: Mapping[AttributedCause, float]
    readings: Mapping[str, str | None]


def _group_key(fields: Iterable[str]) -> str:
    return "+".join(fields)


def _logsumexp(values: Sequence[float], weights: Sequence[float]) -> float:
    """log of sum(weights * exp(values)), stable; ``-inf`` if every term vanishes."""
    top = max(values)
    if top == -math.inf:
        return -math.inf
    return top + math.log(
        math.fsum(w * math.exp(v - top) for v, w in zip(values, weights, strict=True))
    )


def _real(value: object) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


class LikelihoodRule:
    """The likelihood attributor: ``posterior``, ``posterior_subtypes``, ``decide`` and the pair quantities."""

    def __init__(
        self,
        registry: ParameterRegistry,
        table: LikelihoodTable,
        *,
        sensitivity_values: Mapping[str, object],
        diagnostics_profile: str,
        grouped_variant: str | None = None,
        a4: bool = False,
        needs_cumulative_level: bool = True,
    ) -> None:
        """Build the rule.

        ``sensitivity_values`` maps the name of each row ``awaiting_human_value`` that the run reads to a value (a number;
        for ``class_priors`` and ``pi_designs`` the name of a declared design); each is recorded in ``metadata`` as a
        sensitivity value. ``diagnostics_profile`` (``driver_with_diagnostics`` or ``without_diagnostics``) is the device
        profile of the run and has no default. ``grouped_variant`` defaults to the reference declared in the file.
        ``a4`` removes the cells of the embodied channel. ``needs_cumulative_level=False`` is for a run whose
        ``Alert.cause_set`` comes from an injected selector (the conformal set): ``cumulative_level`` is then neither
        required nor used.
        """
        self.table = table
        if diagnostics_profile not in table.diagnostics_profiles:
            raise LikelihoodConfigError(
                f"unknown diagnostics_profile {diagnostics_profile!r}; the table has "
                f"{', '.join(sorted(table.diagnostics_profiles))}"
            )
        variant = (
            grouped_variant
            if grouped_variant is not None
            else table.grouped_variant_reference
        )
        if variant not in table.grouped_variants:
            raise LikelihoodConfigError(
                f"unknown grouped_variant {variant!r}; the table has {', '.join(table.grouped_variants)}"
            )
        self.diagnostics_profile = diagnostics_profile
        self.grouped_variant = variant
        self.a4 = bool(a4)
        self.needs_cumulative_level = bool(needs_cumulative_level)
        self._classifier = HierarchicalRule(
            registry
        )  # the thresholds of the reading classes (registry, no default)
        self._active_groups: tuple[str, ...] = {
            "reference": ("ble_seq_gap",),
            "fully_independent": (),
            "reference_plus_cross_device": (
                "ble_seq_gap",
                "cross_device_signal_quality",
            ),
        }.get(variant, ())
        self._reads = self._effective_reads()
        live = {f for fields in self._reads.values() for f in fields}
        self._resolve(dict(sensitivity_values), live)
        self._pa_cache: dict[tuple[str, str], float] = {}
        self._group_cache: dict[tuple[str, str], list[tuple[str, float]]] = {}
        self._check_groups()
        self._plans = {t: self._plan(t) for t in self._reads}
        self.model_version = self._version()
        self.metadata: Mapping[str, Any] = self._metadata()

    # ---- options -------------------------------------------------------------------------------------------------------

    def _effective_reads(self) -> dict[str, tuple[str, ...]]:
        """The fields read per template: the file, the data-scope masks, the profile and A4."""
        table = self.table
        drop: set[str] = set()
        if not table.diagnostics_profiles[self.diagnostics_profile][
            "reads_diagnostics_ok"
        ]:
            drop.add(DIAG_PATH)
        if self.a4:
            drop.update(table.a4_removed)
        out: dict[str, tuple[str, ...]] = {}
        for tid, spec in table.templates.items():
            reads = set(spec["reads"]) - drop
            for fields, read_for in table.data_scope:
                if tid not in read_for:
                    reads -= set(fields)
            out[tid] = tuple(sorted(reads, key=_ORDER.__getitem__))
        return out

    def _needed(self, live: set[str]) -> list[str]:
        """The names the run needs: every parameter some live cell or mode uses, the thresholds and the designs."""
        table = self.table
        needed = {"eps"}
        for (_comp, field), token in table.cell_token.items():
            if field in live:
                needed.add(table.tokens[token][1])
        needed.add(table.tokens[table.default_token][1])
        for gname in self._active_groups:
            for modes in table.group_modes[gname].values():
                for _combo, tree in modes:
                    needed |= _names(tree)
            default = table.group_default[gname]
            for _combo, tree in default or ():
                needed |= _names(tree)
        if live & {INTERVAL_PATH}:
            needed.add(THRESHOLD_PARAM)
        needed |= {"tau", *_DESIGN_NAMES}
        if self.needs_cumulative_level:
            needed.add("cumulative_level")
        return [n for n in [*table.parameters, *_DESIGN_NAMES] if n in needed]

    def _resolve(self, supplied: dict[str, object], live: set[str]) -> None:
        table = self.table
        known = {*table.parameters, *_DESIGN_NAMES}
        unknown = sorted(set(supplied) - known)
        if unknown:
            raise LikelihoodConfigError(
                f"sensitivity_values names no row of the table: {', '.join(unknown)}"
            )
        needed = self._needed(live)
        values: dict[str, float] = {}
        designs: dict[str, str] = {}
        recorded: dict[str, dict[str, Any]] = {}
        missing: list[str] = []
        for name in needed:
            row = table.parameters.get(name) or table.raw[name]
            fixed = row.get("status") != AWAITING and row.get("value") is not None
            if name in supplied and fixed:
                raise LikelihoodConfigError(
                    f"{name!r} is not awaiting a value (the file gives {row['value']!r}); it cannot be overridden"
                )
            if fixed:
                value: object = row["value"]
                label = None
            elif name in supplied:
                value = supplied[name]
                label = row.get("sensitivity_label") or "sensitivity, not a proposal"
            else:
                missing.append(name)
                continue
            if name in _DESIGN_NAMES:
                declared = (
                    table.class_designs if name == "class_priors" else table.pi_designs
                )
                if not isinstance(value, str) or value not in declared:
                    raise LikelihoodConfigError(
                        f"{name}: {value!r} is not a declared design ({', '.join(sorted(declared))})"
                    )
                designs[name] = value
                if label is not None:
                    recorded[name] = {
                        "value": value,
                        "label": label,
                        "design_status": table.raw[name]["designs"][value].get(
                            "status"
                        ),
                    }
            else:
                values[name] = self._number(name, value)
                if label is not None:
                    recorded[name] = {"value": value, "label": label}
        if missing:
            raise AwaitingValueError(
                missing,
                "rows awaiting_human_value that this run reads have no value in sensitivity_values: "
                + ", ".join(missing)
                + " (configs/attribution_likelihood.yaml; a value is a sensitivity value, never a default)",
            )
        self._values = values
        self._designs = designs
        self._recorded = recorded
        self.tau: float = values["tau"]
        self.cumulative_level: float | None = values.get("cumulative_level")
        self._class_prior = table.class_designs[designs["class_priors"]]
        self._pi_default, self._pi_weights = table.pi_designs[designs["pi_designs"]]

    @staticmethod
    def _number(name: str, value: object) -> float:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise LikelihoodConfigError(
                f"{name}: must be a finite number, got {value!r}"
            )
        low, high, low_in, high_in = _DOMAIN[name]
        number = float(value)
        if not (
            (number > low or (low_in and number == low))
            and (number < high or (high_in and number == high))
        ):
            raise LikelihoodConfigError(
                f"{name}: {value!r} is outside the domain where the logarithms exist "
                f"{'[' if low_in else '('}{low}, {high}{']' if high_in else ')'}"
            )
        return number

    # ---- cells ---------------------------------------------------------------------------------------------------------

    @property
    def parameters(self) -> Mapping[str, float]:
        """The numeric parameters this run uses (name -> value)."""
        return dict(self._values)

    def _env(self) -> Mapping[str, float]:
        return self._values

    def _pa(self, component: str, field: str) -> float:
        """P(field is asserted | component): the cell of the file, or the default cell (structural zero)."""
        key = (component, field)
        if key not in self._pa_cache:
            token = self.table.cell_token.get(key, self.table.default_token)
            tree, _param = self.table.tokens[token]
            where = f"cell {component}/{field} (token {token})"
            value = _evaluate(tree, self._env(), where)
            if not 0.0 < value < 1.0:
                raise LikelihoodConfigError(
                    f"{where}: P(A) = {value!r} is not strictly between 0 and 1"
                )
            self._pa_cache[key] = value
        return self._pa_cache[key]

    def _modes(self, group: str, component: str) -> list[tuple[str, float]] | None:
        key = (group, component)
        if key not in self._group_cache:
            table = self.table
            spec = table.group_modes[group].get(component)
            if spec is None:
                spec = table.group_default[group]
            if spec is None:
                return None
            where = f"group {group}/{component}"
            resolved = [
                (combo, _evaluate(tree, self._env(), where)) for combo, tree in spec
            ]
            if (
                any(w < 0 for _c, w in resolved)
                or abs(math.fsum(w for _c, w in resolved) - 1.0) > 1e-9
            ):
                raise LikelihoodConfigError(
                    f"{where}: the weights of the modes must be >= 0 and sum to 1"
                )
            self._group_cache[key] = resolved
        return self._group_cache[key]

    def _check_groups(self) -> None:
        for group in self._active_groups:
            for comp in self.table.components:
                self._modes(group, comp.id)

    def joint_probability(
        self, group: str, component: str, readings: Mapping[str, str | None]
    ) -> float:
        """P(joint reading of the available members of a grouped cell | component); an unavailable member is summed over.

        ``readings`` maps the members to ``"A"``, ``"D"`` or ``None``. A component with modes: the sum over its modes
        ``m`` of ``weight(m) * [(1 - eps) 1(j = m) + eps / (K - 1) 1(j != m)]``; the group ``ble_seq_gap`` gives a
        component without modes the single mode ``clean``; a component without modes in the cross-device group is the
        product of its marginals. With every member ``None`` the result is 1.
        """
        spec = self.table.groups[group]
        fields = list(spec["fields"])
        k_classes = int(spec["K"])
        eps = self._values["eps"]
        modes = self._modes(group, component)
        total = 0.0
        for combo in product("AD", repeat=len(fields)):
            if any(
                readings.get(f) is not None and readings[f] != c
                for f, c in zip(fields, combo, strict=True)
            ):
                continue
            if modes is None:
                p = 1.0
                for f, c in zip(fields, combo, strict=True):
                    pa = self._pa(component, f)
                    p *= pa if c == "A" else 1.0 - pa
                total += p
            else:
                joint = ",".join(combo)
                total += math.fsum(
                    w * ((1.0 - eps) if joint == m else eps / (k_classes - 1))
                    for m, w in modes
                )
        return total

    # ---- plans ---------------------------------------------------------------------------------------------------------

    def _weight(self, component: Component) -> float:
        for group, weight in self._pi_weights.items():
            if component.id in self.table.pi_groups[group]:
                return weight
        return self._pi_default

    def _group_applies(self, group: str, template: str) -> bool:
        spec = self.table.groups[group]
        templates = spec["templates"]
        return (templates == "all" or template in templates) and any(
            f in self._reads[template] for f in spec["fields"]
        )

    def _applicable(self, template: str) -> tuple[Component, ...]:
        extra: str | None = None
        if "cross_device_signal_quality" in self._active_groups:
            cause = (
                self.table.groups["cross_device_signal_quality"].get("common_cause")
                or {}
            )
            if self._group_applies("cross_device_signal_quality", template):
                extra = cause.get("component")
        return tuple(
            c for c in self.table.components if template in c.templates or c.id == extra
        )

    def _plan(self, template: str) -> _Plan:
        comps = self._applicable(template)
        if not comps:  # pragma: no cover - the table has components at every template
            raise LikelihoodConfigError(f"no component can violate {template}")
        classes = tuple(c for c in CLASS_ORDER if any(x.cls == c for x in comps))
        total_prior = math.fsum(self._class_prior[c] for c in classes)
        log_weight: dict[str, float] = {}
        pi: dict[str, float] = {}
        for comp in comps:
            same = [x for x in comps if x.cls == comp.cls]
            share = self._weight(comp) / math.fsum(self._weight(x) for x in same)
            pi[comp.id] = share
            log_weight[comp.id] = math.log(
                self._class_prior[comp.cls] / total_prior
            ) + math.log(share)
        groups = tuple(
            g for g in self._active_groups if self._group_applies(g, template)
        )
        return _Plan(self._reads[template], comps, classes, log_weight, pi, groups)

    def read_fields(self, template: str | TemplateId) -> tuple[str, ...]:
        """The fields the rule reads for a template, in contract order (the relevance map, the masks, the options)."""
        return self._plans[TemplateId(template).value].reads

    def applicable_subtypes(self, template: str | TemplateId) -> tuple[str, ...]:
        """The subtypes that can violate the template, sorted by name: the keys of ``posterior_subtypes``."""
        plan = self._plans[TemplateId(template).value]
        return tuple(sorted({c.subtype for c in plan.components}))

    @property
    def needs_set_selector(self) -> bool:
        """True when the rule makes no cumulative-level set, so the attributor must be given a selector."""
        return not self.needs_cumulative_level

    # ---- readings ------------------------------------------------------------------------------------------------------

    def _reading(self, path: str, value: object, invalid: list[str]) -> str | None:
        """``"A"``, ``"D"`` or ``None`` (unavailable, out of domain or of class K)."""
        if value is None:
            return None
        if path == INTERVAL_PATH:
            if (
                not _real(value)
                or not math.isfinite(float(value))
                or float(value) < 0.0
            ):
                invalid.append(path)
                return None
            return "A" if float(value) <= self._values[THRESHOLD_PARAM] else "D"
        if path == CONTENT_PATH:
            if not _real(value) or not math.isfinite(float(value)):
                invalid.append(path)
                return None
            return "A" if float(value) == 0.0 else "D"
        code, bad = self._classifier.reading_class(path, value)
        if bad:
            invalid.append(path)
        if code == "A":
            return "A"
        if code in ("D", "F", "G"):
            return "D"
        return None

    def _classes(self, plan: _Plan, evidence: EvidenceVector) -> dict[str, str | None]:
        invalid: list[str] = []
        out = {
            f: self._reading(f, get_evidence(evidence, f), invalid) for f in plan.reads
        }
        if invalid:
            log.warning(
                "attribution: out-of-domain readings read as unavailable: %s",
                ", ".join(invalid),
            )
        return out

    def _terms(
        self, plan: _Plan, component: Component, classes: Mapping[str, str | None]
    ) -> dict[str, float]:
        """log P(reading class | component) per field key; a grouped cell is one entry; an unavailable field has none."""
        grouped = {f for g in plan.groups for f in self.table.groups[g]["fields"]}
        out: dict[str, float] = {}
        for field in plan.reads:
            if field in grouped or classes[field] is None:
                continue
            pa = self._pa(component.id, field)
            out[field] = math.log(pa) if classes[field] == "A" else math.log1p(-pa)
        for group in plan.groups:
            members = list(self.table.groups[group]["fields"])
            readings = {f: classes.get(f) for f in members}
            if all(v is None for v in readings.values()):
                continue
            out[_group_key(members)] = math.log(
                self.joint_probability(group, component.id, readings)
            )
        return dict(sorted(out.items(), key=lambda kv: _ORDER[kv[0].split("+", 1)[0]]))

    # ---- evaluation ----------------------------------------------------------------------------------------------------

    def _template_of(self, evidence: EvidenceVector) -> TemplateId:
        template = evidence.provenance.violated_template
        kind = evidence.provenance.template_kind
        if (
            not isinstance(template, TemplateId)
            or not isinstance(kind, TemplateKind)
            or template_kind_of(template) is not kind
        ):
            raise LikelihoodInputError(
                f"provenance.template_kind {kind!r} does not match provenance.violated_template {template!r}"
            )
        return template

    def _evaluate(self, evidence: EvidenceVector) -> _Evaluation:
        template = self._template_of(evidence)
        plan = self._plans[template.value]
        classes = self._classes(plan, evidence)
        terms = {c.id: self._terms(plan, c, classes) for c in plan.components}
        logp = {
            c.id: plan.log_weight[c.id] + math.fsum(terms[c.id].values())
            for c in plan.components
        }
        top = max(logp.values())
        weights = {k: math.exp(v - top) for k, v in logp.items()}
        norm = math.fsum(weights.values())
        post = {k: w / norm for k, w in weights.items()}
        by_subtype: dict[str, list[float]] = {}
        for comp in plan.components:
            by_subtype.setdefault(comp.subtype, []).append(post[comp.id])
        subtypes = {s: math.fsum(by_subtype[s]) for s in sorted(by_subtype)}
        scale = math.fsum(subtypes.values())
        subtypes = {s: p / scale for s, p in subtypes.items()}
        cls = {
            _CAUSE[c]: math.fsum(
                p for s, p in subtypes.items() if self.table.subtype_class[s] == c
            )
            for c in CLASS_ORDER
        }
        return _Evaluation(template, plan, terms, post, subtypes, cls, classes)

    def posterior_subtypes(
        self, violated: VerdictRecord, evidence: EvidenceVector
    ) -> Mapping[str, float]:
        """p(subtype | e, t) over the subtypes applicable at the template; sums to 1. ``violated`` is not read (I1)."""
        return dict(self._evaluate(evidence).subtypes)

    def posterior(
        self, violated: VerdictRecord, evidence: EvidenceVector
    ) -> Mapping[AttributedCause, float]:
        """p(class | e, t), keys C1, C2, C3 (0 for a class with no component at the template); sums to 1."""
        return dict(self._evaluate(evidence).classes)

    def attribute(
        self, violated: VerdictRecord, evidence: EvidenceVector
    ) -> AttributedCause:
        return self.decide(violated, evidence).kappa

    def label(self, p_kappa: Mapping[AttributedCause, float]) -> AttributedCause:
        """The class with the largest posterior if it reaches ``tau``; ``UNDETERMINED`` below it and on a tie."""
        ranked = sorted(p_kappa.items(), key=lambda kv: -kv[1])
        best_class, best = ranked[0]
        if best < self.tau:
            return AttributedCause.UNDETERMINED
        if len(ranked) > 1 and abs(ranked[1][1] - best) <= NUMERICAL_ZERO:
            return AttributedCause.UNDETERMINED
        return best_class

    def cumulative_set(
        self, posteriors: Mapping[str, float], level: float | None = None
    ) -> tuple[str, ...]:
        """The most probable subtypes (ties by name) until their cumulative probability reaches the level.

        The same rule as ``ralmon.conformal.sets.cumulative_level_set``, exact on the decimal literals of the
        probabilities (that module cannot be imported here; a test compares the two).
        """
        chosen_level = level if level is not None else self.cumulative_level
        if chosen_level is None:
            raise AwaitingValueError(
                ("cumulative_level",),
                "this rule was built without cumulative_level (needs_cumulative_level=False): no cumulative set",
            )
        if isinstance(chosen_level, bool) or not 0.0 < float(chosen_level) < 1.0:
            raise LikelihoodConfigError(
                f"level must lie in (0, 1), got {chosen_level!r}"
            )
        target = Fraction(repr(float(chosen_level)))
        chosen: list[str] = []
        cumulative = Fraction(0)
        for name, p in sorted(posteriors.items(), key=lambda kv: (-kv[1], kv[0])):
            chosen.append(name)
            cumulative += Fraction(repr(float(p)))
            if cumulative >= target:
                break
        return tuple(chosen)

    # ---- the decision record -------------------------------------------------------------------------------------------

    def decide(self, violated: VerdictRecord, evidence: EvidenceVector) -> Decision:
        """The decision record: kappa, the class and subtype posteriors, the set, the contributions, the decisive fields.

        A vector whose provenance is inconsistent is a defect of the extractor: it is logged and the decision is
        ``UNDETERMINED`` without a posterior (the alert path does not raise on evidence); ``posterior`` raises.
        """
        try:
            ev = self._evaluate(evidence)
        except LikelihoodInputError as error:
            log.warning("attribution: %s; the evidence is not evaluated", error)
            return Decision(
                AttributedCause.UNDETERMINED,
                None,
                AbstentionReason.INSUFFICIENT,
                (),
                (),
            )
        kappa = self.label(ev.classes)
        class_terms = self._class_terms(ev)
        decisive = self._decisive(ev, class_terms)
        readings = tuple(
            (path, self._plain(get_evidence(evidence, path))) for path in decisive
        )
        cause_set = (
            self.cumulative_set(ev.subtypes)
            if self.cumulative_level is not None
            else None
        )
        return Decision(
            kappa,
            None,
            None,
            decisive,
            (),
            readings,
            p_kappa=dict(ev.classes),
            posterior_subtypes=dict(ev.subtypes),
            cause_set=cause_set,
            contributions={k: dict(v) for k, v in ev.terms.items()},
            class_contributions=class_terms,
            abstention_threshold=self.tau,
        )

    @staticmethod
    def _plain(value: object) -> object:
        if isinstance(value, dict):
            return tuple(sorted((str(k), str(v)) for k, v in value.items()))
        return value

    @staticmethod
    def _class_terms(ev: _Evaluation) -> dict[str, dict[str, float]]:
        """class -> field key -> log of the pi-weighted mixture, over the components of the class, of P(reading | s)."""
        keys: list[str] = []
        for terms in ev.terms.values():
            for key in terms:
                if key not in keys:
                    keys.append(key)
        out: dict[str, dict[str, float]] = {}
        for cls in ev.plan.classes:
            comps = [c for c in ev.plan.components if c.cls == cls]
            weights = [ev.plan.pi[c.id] for c in comps]
            out[cls] = {
                key: _logsumexp([ev.terms[c.id][key] for c in comps], weights)
                for key in keys
            }
        return out

    @staticmethod
    def _decisive(
        ev: _Evaluation, class_terms: Mapping[str, Mapping[str, float]]
    ) -> tuple[str, ...]:
        """The fields whose reading favours the leading class against the rest, best first.

        The margin of a field is the single-field log likelihood ratio of the leading class against the mixture of
        the other applicable classes, weighted by their posterior mass; a field is decisive if the margin exceeds
        numerical zero. It is traceability of the table (which readings pulled towards the class), not a causal claim.
        """
        order = {c: i for i, c in enumerate(CLASS_ORDER)}
        leading = max(ev.plan.classes, key=lambda c: (ev.classes[_CAUSE[c]], -order[c]))
        others = [c for c in ev.plan.classes if c != leading]
        mass = [ev.classes[_CAUSE[c]] for c in others]
        if not others or math.fsum(mass) <= 0.0:
            return ()
        scored: list[tuple[float, int, str]] = []
        for key, lead in class_terms[leading].items():
            rest = _logsumexp([class_terms[o][key] for o in others], mass) - math.log(
                math.fsum(mass)
            )
            margin = lead - rest
            if margin > NUMERICAL_ZERO:
                for path in key.split("+"):
                    if path in ev.readings and ev.readings[path] is not None:
                        scored.append((-margin, _ORDER[path], path))
        return tuple(path for _m, _o, path in sorted(scored))

    # ---- the pair quantity -----------------------------------------------------------------------------------------------

    def subtype_log_likelihood(self, subtype: str, evidence: EvidenceVector) -> float:
        """log P(e | subtype) at the template of the evidence: the pi-weighted mixture over the levels of the subtype.

        The weights are the within-subtype weights of the pi design in force; the subtype need not be applicable at
        the template (a pair compares its two actual causes). ``KeyError`` for a name that is not in the catalogue.
        """
        comps = [c for c in self.table.components if c.subtype == subtype]
        if not comps:
            raise KeyError(subtype)
        template = self._template_of(evidence)
        plan = self._plans[template.value]
        classes = self._classes(plan, evidence)
        weights = [self._weight(c) for c in comps]
        total = math.fsum(weights)
        values = [math.fsum(self._terms(plan, c, classes).values()) for c in comps]
        return _logsumexp(values, [w / total for w in weights])

    def log_likelihood_ratio(
        self, subtype_a: str, subtype_b: str, evidence: EvidenceVector
    ) -> float:
        """Lambda = log P(e | subtype_a) - log P(e | subtype_b): prior-free (no class prior, no weight between subtypes)."""
        return self.subtype_log_likelihood(
            subtype_a, evidence
        ) - self.subtype_log_likelihood(subtype_b, evidence)

    def pair_statistic(
        self,
        subtype_a: str,
        subtype_b: str,
        evidence_a: EvidenceVector,
        evidence_b: EvidenceVector,
    ) -> float:
        """D = Lambda_A - Lambda_B for the alerts of the two members of a pair at their common template.

        Identical evidence gives exactly 0; Lambda itself is the lean of the catalogue and is not 0.
        """
        return self.log_likelihood_ratio(
            subtype_a, subtype_b, evidence_a
        ) - self.log_likelihood_ratio(subtype_a, subtype_b, evidence_b)

    # ---- version and metadata --------------------------------------------------------------------------------------------

    def _thresholds(self) -> dict[str, float]:
        c = self._classifier
        return {
            "hr_coherence_tolerance": c.hr_coherence_tolerance,
            "ecg_sqi_floor": c.ecg_sqi_floor,
            "ppg_sqi_floor": c.ppg_sqi_floor,
            "ble_link_quality_floor": c.ble_link_quality_floor,
        }

    def _version(self) -> str:
        """A token of the posterior model: the file and every option that changes p(s | e, t).

        ``tau`` and ``cumulative_level`` change the label and the set, not the posterior, so they are not in it.
        Use it as the ``model_version`` of ``SubtypeSetCalibrator.fit`` and ``predict_set``.
        """
        payload = {
            "config_sha256": self.table.sha256,
            "values": {
                k: v
                for k, v in sorted(self._values.items())
                if k not in ("tau", "cumulative_level")
            },
            "designs": dict(sorted(self._designs.items())),
            "grouped_variant": self.grouped_variant,
            "diagnostics_profile": self.diagnostics_profile,
            "a4": self.a4,
            "thresholds": self._thresholds(),
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return f"ralmon-likelihood-{digest[:16]}"

    def _metadata(self) -> dict[str, Any]:
        table = self.table
        return {
            "model": "likelihood table of ADR-074 (docs/models/attribution-likelihood.md)",
            "model_version": self.model_version,
            "config_path": str(table.path) if table.path is not None else None,
            "config_sha256": table.sha256,
            "schema_version": table.schema_version,
            "sensitivity_values": {k: dict(v) for k, v in self._recorded.items()},
            "grouped_variant": self.grouped_variant,
            "diagnostics_profile": self.diagnostics_profile,
            "a4": self.a4,
            "needs_cumulative_level": self.needs_cumulative_level,
            "thresholds_of_the_reading_classes": self._thresholds(),
            "awaiting_cells": sum(
                1 for cell in table.raw["cells"] if cell.get("status") == AWAITING
            ),
            "awaiting_groups": sorted(
                g for g, spec in table.groups.items() if spec.get("status") == AWAITING
            ),
            "note": "every sensitivity value is a sensitivity, not a proposal; no value of the table is verified (verified_by is null)",
        }
