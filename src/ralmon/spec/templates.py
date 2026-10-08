"""The template contract (02-interfaces.md#template) and the loader of the template library.

``load_templates`` reads ``configs/templates/hypertension.yaml``, the machine-readable form of the
seven-row table of docs/formal/02-templates.md section 3.1, and checks it against the grammar of
section 1.2 of that document and against a parameter registry:

* exactly one ``Template`` per ``TemplateId``; the kind follows the decomposition
  phi = phi_CP and phi_SYS and phi_INT (SYS is phi_sys, INT is phi_int, the others phi_cp);
* ``scale_param``, ``priority_param`` and ``max_verdict_latency_param`` are ``scale_<id>``,
  ``priority_<id>`` and ``max_latency_<id>`` (WS01-T02 check 3);
* ``signals`` are ``SignalId`` values and ``signals`` and ``params`` are exactly the names that the
  string mentions (``age`` is an instance term and ``step_ms`` monitor configuration: neither is listed);
* every name resolves in the registry (an unset name is declared, so it resolves: the structure of a
  template does not depend on the value), a set scale has the unit of the template margin and a set
  priority is a rank.

No value is read here: the clinical values stay in the registry.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Final, TypeVar

from ralmon.signals import SignalId
from ralmon.spec import registry as _registry
from ralmon.spec._text import show
from ralmon.spec._yaml import coerce_path, parse_yaml_bytes, read_limited_bytes
from ralmon.spec.registry import (
    ParameterRegistry,
    RegistryEntry,
    RegistryError,
    UnsetParameterError,
    as_priority,
    load_registry,
)

__all__ = [
    "RobustnessUnit",
    "Template",
    "TemplateId",
    "TemplateKind",
    "TemplateLibraryError",
    "default_templates_path",
    "load_templates",
]

DEFAULT_TEMPLATES_RELPATH: Final = ("configs", "templates", "hypertension.yaml")
_E = TypeVar("_E", bound=Enum)


class TemplateLibraryError(Exception):
    """The template library file is malformed or inconsistent with the grammar or the registry."""


# ---------------------------------------------------------------------------------------
# Contract (02-interfaces.md#template, version 0.1.0): copied verbatim
# ---------------------------------------------------------------------------------------


class TemplateKind(str, Enum):
    CARE_PLAN = "phi_cp"
    SYSTEM = "phi_sys"
    INTEGRITY = "phi_int"


class TemplateId(str, Enum):
    RANGE = "range"  # measured pressure inside the prescribed band
    SCHED = "sched"  # a measurement occurs in the window after a schedule tick
    HOLD = "hold"  # do not dispense if pressure is below the hold threshold
    COUNT = "count"  # dose count limit and day-end count obligation
    RESP = "resp"  # dose-response: pressure decrease relative to pre-dose reference in [Delta1, Delta2]
    SYS = "sys"  # measurement valid only if cuff node healthy and inflation acceptable
    INT = (
        "int"  # a dispense is backed by robot-observed presence or authenticated event
    )


class RobustnessUnit(str, Enum):
    MMHG = "mmHg"
    MS = "ms"  # time robustness
    DOSE = "dose"
    DIMENSIONLESS = "1"


@dataclass(frozen=True, slots=True)
class Template:
    id: TemplateId
    kind: TemplateKind
    formula_past_time: (
        str  # past-time STL string, syntax fixed by WS01-T02 (RTAMT-compatible)
    )
    signals: Sequence[str]  # SignalId values used (see #signals)
    params: Sequence[str]  # registry entry names it needs
    unit: RobustnessUnit
    scale_param: str  # registry entry name holding s_pi
    priority_param: str  # registry entry name holding the clinician-assigned priority
    max_verdict_latency_param: str  # registry entry: bound on time to a definitive verdict (Delta2 or W plus T_s)
    creates_robot_obligation: bool  # True for RESP and SCHED (analisi §4.1 item 4)


# ---------------------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------------------

_TOP_KEYS: Final = ("library_version", "pathology", "templates")
_ROW_KEYS: Final = (
    "id",
    "kind",
    "formula_past_time",
    "signals",
    "params",
    "unit",
    "scale_param",
    "priority_param",
    "max_verdict_latency_param",
    "creates_robot_obligation",
    "source",
)
_KIND_OF_ID: Final[Mapping[TemplateId, TemplateKind]] = {
    TemplateId.RANGE: TemplateKind.CARE_PLAN,
    TemplateId.SCHED: TemplateKind.CARE_PLAN,
    TemplateId.HOLD: TemplateKind.CARE_PLAN,
    TemplateId.COUNT: TemplateKind.CARE_PLAN,
    TemplateId.RESP: TemplateKind.CARE_PLAN,
    TemplateId.SYS: TemplateKind.SYSTEM,
    TemplateId.INT: TemplateKind.INTEGRITY,
}
# Words of the grammar of docs/formal/02-templates.md section 1.2 that are neither a signal nor a
# registry name: the operators, `inf`, the instance term `age` and the monitor step.
_GRAMMAR_WORDS: Final = frozenset(
    {"historically", "once", "since", "not", "and", "or", "inf", "age", "step_ms"}
)
_FORMULA_CHARS: Final = re.compile(r"[a-z0-9_ ()\[\],<>=+\-]+")
_WORD: Final = re.compile(r"[a-z][a-z0-9_]*")
_NAME: Final = re.compile(r"[a-z][a-z0-9_]*")
_VERSION: Final = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
_SIGNAL_VALUES: Final = frozenset(member.value for member in SignalId)


def default_templates_path() -> Path:
    """``configs/templates/hypertension.yaml`` under the directory that holds ``pyproject.toml``."""
    root = _registry._repo_root()
    if root is None:
        raise TemplateLibraryError(
            "cannot locate configs/templates/hypertension.yaml: no pyproject.toml above the "
            "ralmon package; pass the path of the template file"
        )
    return root.joinpath(*DEFAULT_TEMPLATES_RELPATH)


def load_templates(
    path: str | Path | None = None,
    registry: ParameterRegistry | None = None,
) -> tuple[Template, ...]:
    """Load the template library: one ``Template`` per ``TemplateId``, in the order of the enum.

    ``path`` is ``configs/templates/hypertension.yaml`` when ``None``; ``registry`` is the registry
    the names must resolve in (``load_registry()`` when ``None``). Every problem raises
    ``TemplateLibraryError``.
    """
    resolved = (
        default_templates_path()
        if path is None
        else coerce_path(path, TemplateLibraryError, "template library")
    )
    if registry is None:
        try:
            registry = load_registry()
        except RegistryError as exc:
            raise TemplateLibraryError(
                f"default registry cannot be loaded: {exc}"
            ) from exc
    elif not all(
        callable(getattr(registry, method, None))
        for method in ("get", "bounds", "version")
    ):
        raise TemplateLibraryError(
            "registry must be a ParameterRegistry (an object with get, bounds and "
            f"version), got {show(registry)}"
        )
    data = read_limited_bytes(resolved, TemplateLibraryError, "template library")
    document = parse_yaml_bytes(
        data, TemplateLibraryError, f"template library {resolved}"
    )
    where = f"template library {resolved}"
    if not isinstance(document, Mapping):
        raise TemplateLibraryError(
            f"{where}: the file must hold a mapping at top level"
        )
    unknown = sorted(str(k) for k in document if k not in _TOP_KEYS)
    missing = [k for k in _TOP_KEYS if k not in document]
    if unknown or missing:
        raise TemplateLibraryError(
            f"{where}: unknown key(s) {unknown}, missing required key(s) {missing}"
        )
    version = document["library_version"]
    if not isinstance(version, str) or _VERSION.fullmatch(version) is None:
        raise TemplateLibraryError(
            f"{where}: library_version must be a MAJOR.MINOR.PATCH string, got {show(version)}"
        )
    pathology = document["pathology"]
    if not isinstance(pathology, str) or not pathology.strip():
        raise TemplateLibraryError(f"{where}: pathology must be a non-empty string")
    rows = document["templates"]
    if not isinstance(rows, list):
        raise TemplateLibraryError(
            f"{where}: templates must be a list, got {show(rows)}"
        )
    parsed = [_parse_row(row, index) for index, row in enumerate(rows)]
    by_id: dict[TemplateId, Template] = {}
    for template in parsed:
        if template.id in by_id:
            raise TemplateLibraryError(
                f"{where}: templates: the id {template.id.value!r} appears twice"
            )
        by_id[template.id] = template
    absent = [i.value for i in TemplateId if i not in by_id]
    if absent:
        raise TemplateLibraryError(f"{where}: templates: missing ids {absent}")
    library = tuple(by_id[template_id] for template_id in TemplateId)
    for template in library:
        _check_against_registry(template, registry)
    return library


def _enum_member(enum_class: type[_E], value: object, field: str, where: str) -> _E:
    if isinstance(value, str):
        try:
            return enum_class(value)
        except ValueError:
            pass
    allowed = [m.value for m in enum_class]
    raise TemplateLibraryError(
        f"{where}: {field} must be one of {allowed}, got {show(value)}"
    )


def _names(value: object, field: str, where: str) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(n, str) or _NAME.fullmatch(n) is None for n in value)
    ):
        raise TemplateLibraryError(
            f"{where}: {field} must be a non-empty list of names, got {show(value)}"
        )
    if len(set(value)) != len(value):
        raise TemplateLibraryError(f"{where}: {field} repeats a name: {show(value)}")
    return tuple(value)


def _parse_row(raw: object, index: int) -> Template:
    where = f"templates[{index}]"
    if not isinstance(raw, Mapping):
        raise TemplateLibraryError(f"{where} must be a mapping, got {show(raw)}")
    ident = raw.get("id")
    if isinstance(ident, str) and _NAME.fullmatch(ident) is not None:
        where = f"{where} ({ident})"
    unknown = sorted(str(k) for k in raw if k not in _ROW_KEYS)
    missing = [k for k in _ROW_KEYS if k not in raw]
    if unknown or missing:
        raise TemplateLibraryError(
            f"{where}: unknown key(s) {unknown}, missing required field(s) {missing}"
        )
    template_id = _enum_member(TemplateId, raw["id"], "id", where)
    kind = _enum_member(TemplateKind, raw["kind"], "kind", where)
    unit = _enum_member(RobustnessUnit, raw["unit"], "unit", where)
    if kind is not _KIND_OF_ID[template_id]:
        raise TemplateLibraryError(
            f"{where}: kind {kind.value!r} contradicts the decomposition "
            f"(the kind of {template_id.value!r} is {_KIND_OF_ID[template_id].value!r})"
        )
    formula = raw["formula_past_time"]
    if (
        not isinstance(formula, str)
        or not formula.strip()
        or _FORMULA_CHARS.fullmatch(formula) is None
    ):
        raise TemplateLibraryError(
            f"{where}: formula_past_time must be a non-empty string of the grammar of "
            f"docs/formal/02-templates.md section 1.2, got {show(formula)}"
        )
    signals = _names(raw["signals"], "signals", where)
    params = _names(raw["params"], "params", where)
    unknown_signals = [s for s in signals if s not in _SIGNAL_VALUES]
    if unknown_signals:
        raise TemplateLibraryError(
            f"{where}: signals {unknown_signals} are not SignalId values"
        )
    _check_formula_names(formula, signals, params, where)
    for field, prefix in (
        ("scale_param", "scale"),
        ("priority_param", "priority"),
        ("max_verdict_latency_param", "max_latency"),
    ):
        expected = f"{prefix}_{template_id.value}"
        if raw[field] != expected:
            raise TemplateLibraryError(
                f"{where}: {field} must be {expected!r}, got {show(raw[field])}"
            )
    obligation = raw["creates_robot_obligation"]
    if not isinstance(obligation, bool):
        raise TemplateLibraryError(
            f"{where}: creates_robot_obligation must be true or false, got {show(obligation)}"
        )
    source = raw["source"]
    if not isinstance(source, str) or not source.strip():
        raise TemplateLibraryError(
            f"{where}: source (the locator) must be a non-empty string"
        )
    return Template(
        id=template_id,
        kind=kind,
        formula_past_time=formula,
        signals=signals,
        params=params,
        unit=unit,
        scale_param=str(raw["scale_param"]),
        priority_param=str(raw["priority_param"]),
        max_verdict_latency_param=str(raw["max_verdict_latency_param"]),
        creates_robot_obligation=obligation,
    )


def _check_formula_names(
    formula: str, signals: Sequence[str], params: Sequence[str], where: str
) -> None:
    """``signals`` and ``params`` are exactly the names that the string mentions."""
    words = set(_WORD.findall(formula)) - _GRAMMAR_WORDS
    used_signals = {w for w in words if w in _SIGNAL_VALUES}
    used_params = words - used_signals
    if set(signals) != used_signals:
        raise TemplateLibraryError(
            f"{where}: signals {sorted(signals)} differ from the signals of the string "
            f"{sorted(used_signals)}"
        )
    if set(params) != used_params:
        raise TemplateLibraryError(
            f"{where}: params {sorted(params)} differ from the registry names of the string "
            f"{sorted(used_params)}"
        )


def _resolve(
    registry: ParameterRegistry, name: str, where: str
) -> tuple[bool, RegistryEntry | None]:
    """(declared, entry): the entry is ``None`` for a declared name that has no value to read."""
    is_declared = getattr(registry, "is_declared", None)
    try:
        entry = registry.get(name)
    except UnsetParameterError:
        return True, None
    except RegistryError:
        if callable(is_declared) and is_declared(name):
            return True, None  # for instance a derived name when step_ms was not given
        return False, None
    except Exception as exc:
        raise TemplateLibraryError(
            f"{where}: the registry failed on {name!r}: {exc}"
        ) from exc
    if not isinstance(entry, RegistryEntry):
        raise TemplateLibraryError(
            f"{where}: the registry returned {show(entry)} for {name!r}, not a RegistryEntry"
        )
    return True, entry


def _check_against_registry(template: Template, registry: ParameterRegistry) -> None:
    where = f"template {template.id.value!r}"
    for name in (
        *template.params,
        template.scale_param,
        template.priority_param,
        template.max_verdict_latency_param,
    ):
        declared, _entry = _resolve(registry, name, where)
        if not declared:
            raise TemplateLibraryError(
                f"{where}: {name!r} is not declared in the registry"
            )
    _declared, scale = _resolve(registry, template.scale_param, where)
    if scale is not None:
        if scale.unit != template.unit.value:
            raise TemplateLibraryError(
                f"{where}: scale_param {template.scale_param!r} has unit {scale.unit!r}, "
                f"the margin of the template is {template.unit.value!r}"
            )
        if not scale.value > 0:
            raise TemplateLibraryError(
                f"{where}: scale_param {template.scale_param!r} must be positive, "
                f"got {scale.value!r}"
            )
    _declared, priority = _resolve(registry, template.priority_param, where)
    if priority is not None:
        try:
            as_priority(priority)
        except RegistryError as exc:
            raise TemplateLibraryError(f"{where}: {exc}") from exc
