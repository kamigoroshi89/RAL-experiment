"""Parameter registry: the dataclasses of 02-interfaces.md#parameter-registry and the loader.

``load_registry`` reads a registry file in the schema of docs/formal/03-parameter-registry.md
(``configs/registry/registry.schema.json``) with a strict, bounded, safe YAML reader and re-implements
the checks of that schema in code:

* every entry has the six fields of ``RegistryEntry``; an entry with no reviewer must say that it is
  unverified (ADR-020);
* durations (unit ``ms``) are integral and non-negative, scales are positive, priorities are integral
  ranks >= 1 with unit ``1``; window parameters are multiples of ``step_ms`` when it is given;
* a name can be an entry, a derived name (a sum of entries and ``step_ms``, evaluated by this
  module's own parser, never by ``eval``) or an unset name; asking for an unset name raises
  ``UnsetParameterError``, never a default;
* ``review_status`` must agree with the entries;
* a registry that contains FIXTURE-ONLY rows (ADR-027) is refused unless ``allow_fixture_only=True``.

This module is the only place where parameter values are read; no clinical value is written in code.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol

from ralmon.spec._text import show
from ralmon.spec._yaml import coerce_path, parse_yaml_bytes, read_limited_bytes

__all__ = [
    "FIXTURE_ONLY_MARKER",
    "LoadedRegistry",
    "ParameterRegistry",
    "PhysioBounds",
    "RegistryEntry",
    "RegistryError",
    "RegistryOverride",
    "UnsetParameterError",
    "as_duration_ms",
    "as_priority",
    "default_registry_path",
    "load_registry",
]

FIXTURE_ONLY_MARKER: Final = "FIXTURE-ONLY"
UNVERIFIED_SUFFIX: Final = "illustrative, unverified"
DERIVED_SOURCE_REF: Final = "docs/formal/03-parameter-registry.md section 3"
STEP_NAME: Final = "step_ms"
UNITS: Final = ("mmHg", "ms", "dose", "1")
SCALE_UNITS: Final = ("mmHg", "ms", "dose")
REVIEW_STATUSES: Final = ("unreviewed", "partially_reviewed", "reviewed")
# The ids of TemplateId (tests/spec checks that the two lists agree); this module cannot import
# ralmon.spec.templates, which imports it.
TEMPLATE_IDS: Final = ("range", "sched", "hold", "count", "resp", "sys", "int")
WINDOW_START: Final = "delta1"
WINDOW_END: Final = "delta2"
DEFAULT_REGISTRY_RELPATH: Final = ("configs", "registry", "hypertension.yaml")

_NAME_RE: Final = re.compile(r"[a-z][a-z0-9_]*")
_VERSION_RE: Final = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
_FORMULA_RE: Final = re.compile(r"[a-z][a-z0-9_]*( *\+ *[a-z][a-z0-9_]*)*")
_BOUND_LOWER_RE: Final = re.compile(r"bound_([a-z][a-z0-9_]*)_lower")

_TOP_REQUIRED: Final = (
    "registry_version",
    "pathology",
    "review_status",
    "window_parameters",
    "entries",
    "derived",
    "unset",
)
_TOP_OPTIONAL: Final = ("overrides",)
_ENTRY_KEYS: Final = ("name", "value", "unit", "rationale", "source_ref", "reviewed_by")
_DERIVED_KEYS: Final = ("name", "unit", "formula", "template")
_UNSET_KEYS: Final = ("parameter", "unit", "required_by", "note")
_OVERRIDE_KEYS: Final = (
    "name",
    "min",
    "max",
    "rationale",
    "source_ref",
    "reviewed_by",
)


# ---------------------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------------------


class RegistryError(Exception):
    """A registry file is malformed or inconsistent, or a name is not in the registry."""


class UnsetParameterError(RegistryError):
    """A parameter that is declared but has no value yet was asked for (ADR-020)."""


# ---------------------------------------------------------------------------------------
# Contract (02-interfaces.md#parameter-registry, version 0.1.0): copied verbatim
# ---------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RegistryEntry:
    name: str  # e.g. "bp_band_low", "delta1", "delta2", "scale_range"
    value: float
    unit: str  # "mmHg", "ms", "dose", "1" ...
    rationale: str  # drug or guideline anchoring, or "illustrative, unverified"
    source_ref: str
    reviewed_by: str | None  # clinician; None until reviewed


@dataclass(frozen=True, slots=True)
class PhysioBounds:
    signal: str
    lower: float
    upper: float  # used to complete unknown future values in robustness intervals (analisi §4.7 step 2)


class ParameterRegistry(Protocol):
    def get(self, name: str) -> RegistryEntry: ...
    def bounds(self, signal: str) -> PhysioBounds: ...
    def version(self) -> str: ...


# ---------------------------------------------------------------------------------------
# Additional value types
# ---------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RegistryOverride:
    """A clinician-approved range for a per-patient value (03 section 5.3)."""

    name: str
    min: float
    max: float
    rationale: str
    source_ref: str
    reviewed_by: str | None


@dataclass(frozen=True, slots=True)
class _Derived:
    name: str
    unit: str
    terms: tuple[str, ...]
    template: str


@dataclass(frozen=True, slots=True)
class _Unset:
    name: str
    unit: str
    required_by: tuple[str, ...]
    note: str


# ---------------------------------------------------------------------------------------
# Casts (docs/formal/03-parameter-registry.md section 2.6, CP10)
# ---------------------------------------------------------------------------------------


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _integral(value: object) -> int | None:
    """The integer value of a finite integral number, else ``None``."""
    if not _is_number(value):
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except OverflowError:
        return None
    if not math.isfinite(number) or not number.is_integer():
        return None
    return int(number)


def as_duration_ms(entry: RegistryEntry) -> int:
    """The value of an entry with unit ``ms`` as an integer number of milliseconds (``DurationMs``).

    Raises ``RegistryError`` if the entry is not a non-negative integral duration.
    """
    if not isinstance(entry, RegistryEntry):
        raise RegistryError(f"expected a RegistryEntry, got {show(entry)}")
    if entry.unit != "ms":
        raise RegistryError(
            f"{entry.name!r} has unit {entry.unit!r}, not 'ms': it is not a duration"
        )
    value = _integral(entry.value)
    if value is None or value < 0:
        raise RegistryError(
            f"{entry.name!r} is {show(entry.value)}, not a non-negative integral duration"
        )
    return value


def as_priority(entry: RegistryEntry) -> int:
    """The value of a ``priority_<id>`` entry as an integer rank >= 1 (1 is the highest priority).

    Raises ``RegistryError`` if the entry is not an integral rank with unit ``1``.
    """
    if not isinstance(entry, RegistryEntry):
        raise RegistryError(f"expected a RegistryEntry, got {show(entry)}")
    value = _integral(entry.value)
    if entry.unit != "1" or value is None or value < 1:
        raise RegistryError(
            f"{entry.name!r} is {show(entry.value)} {entry.unit!r}, not an integral rank >= 1"
        )
    return value


# ---------------------------------------------------------------------------------------
# The loaded registry
# ---------------------------------------------------------------------------------------


class LoadedRegistry:
    """A validated registry; implements ``ParameterRegistry``.

    Besides ``get``, ``bounds`` and ``version`` it offers ``is_declared``, ``is_set``,
    ``unset_names``, ``unverified_names`` and ``fixture_only_names`` (03 section 2.5). Build it with
    ``load_registry``.
    """

    def __init__(
        self,
        *,
        path: Path,
        sha256: str,
        version: str,
        pathology: str,
        review_status: str,
        window_parameters: tuple[str, ...],
        entries: Mapping[str, RegistryEntry],
        derived: Mapping[str, _Derived],
        unset: Mapping[str, _Unset],
        overrides: tuple[RegistryOverride, ...],
        fixture_names: tuple[str, ...],
        step_ms: int | None,
    ) -> None:
        self._path = path
        self._sha256 = sha256
        self._version = version
        self._pathology = pathology
        self._review_status = review_status
        self._windows = window_parameters
        self._entries = dict(entries)
        self._derived = dict(derived)
        self._unset = dict(unset)
        self._overrides = overrides
        self._fixture_names = fixture_names
        self._step_ms = step_ms

    # -- ParameterRegistry ------------------------------------------------------------

    def version(self) -> str:
        """The ``registry_version`` of the file (``MAJOR.MINOR.PATCH``)."""
        return self._version

    def get(self, name: str) -> RegistryEntry:
        """The entry ``name``: a stored entry, a computed derived entry, else an error.

        An unset name raises ``UnsetParameterError`` (never a default); an unknown name or a name
        that is not a ``str`` raises ``RegistryError``.
        """
        if not isinstance(name, str):
            raise RegistryError(f"a parameter name must be a str, got {show(name)}")
        entry = self._entries.get(name)
        if entry is not None:
            return entry
        derived = self._derived.get(name)
        if derived is not None:
            return self._compute(derived)
        unset = self._unset.get(name)
        if unset is not None:
            raise UnsetParameterError(_unset_message(unset))
        raise RegistryError(f"unknown parameter {name!r} in registry {self._version}")

    def bounds(self, signal: str) -> PhysioBounds:
        """The physiological bounds of ``signal``, composed from ``bound_<signal>_lower`` and
        ``bound_<signal>_upper`` (03 section 2.5 rule 5)."""
        if not isinstance(signal, str):
            raise RegistryError(f"a signal name must be a str, got {show(signal)}")
        lower_name, upper_name = f"bound_{signal}_lower", f"bound_{signal}_upper"
        if not (self.is_declared(lower_name) or self.is_declared(upper_name)):
            raise RegistryError(
                f"no bounds are declared for signal {signal!r} "
                f"(expected entries {lower_name!r} and {upper_name!r})"
            )
        lower = self._bound_side(lower_name, signal)
        upper = self._bound_side(upper_name, signal)
        return PhysioBounds(signal, lower.value, upper.value)

    def _bound_side(self, name: str, signal: str) -> RegistryEntry:
        entry = self._entries.get(name)
        if entry is not None:
            return entry
        unset = self._unset.get(name)
        if unset is not None:
            raise UnsetParameterError(_unset_message(unset))
        raise RegistryError(
            f"the bound {name!r} of signal {signal!r} is not an entry of the registry"
        )

    def _compute(self, derived: _Derived) -> RegistryEntry:
        total = 0.0
        unreviewed = False
        for term in derived.terms:
            if term == STEP_NAME:
                if self._step_ms is None:
                    raise RegistryError(
                        f"derived parameter {derived.name!r} needs step_ms: pass step_ms to load_registry"
                    )
                total += self._step_ms
                continue
            unset = self._unset.get(term)
            if unset is not None:
                raise UnsetParameterError(
                    f"derived parameter {derived.name!r} needs {term!r}, which is unset "
                    f"(required by {list(unset.required_by)})"
                )
            entry = self._entries[term]
            total += entry.value
            unreviewed = unreviewed or entry.reviewed_by is None
        rationale = "derived: " + " + ".join(derived.terms)
        if unreviewed:
            rationale += "; " + UNVERIFIED_SUFFIX
        return RegistryEntry(
            name=derived.name,
            value=float(total),
            unit=derived.unit,
            rationale=rationale,
            source_ref=DERIVED_SOURCE_REF,
            reviewed_by=None,
        )

    # -- extras (not in the protocol) -------------------------------------------------

    def is_declared(self, name: object) -> bool:
        """Whether ``name`` is an entry, a derived name or an unset name."""
        return isinstance(name, str) and (
            name in self._entries or name in self._derived or name in self._unset
        )

    def is_set(self, name: str) -> bool:
        """Whether ``name`` has a value: an entry, or a derived name all of whose terms are set.

        Raises ``RegistryError`` for a name that is not declared.
        """
        if not self.is_declared(name):
            raise RegistryError(
                f"unknown parameter {show(name)} in registry {self._version}"
            )
        if name in self._entries:
            return True
        derived = self._derived.get(name)
        if derived is not None:
            return all(
                term == STEP_NAME or term in self._entries for term in derived.terms
            )
        return False

    def unset_names(self) -> tuple[str, ...]:
        """The declared names that have no value, in file order."""
        return tuple(self._unset)

    def unverified_names(self) -> tuple[str, ...]:
        """The entries whose ``reviewed_by`` is ``None``, in file order (for the run manifest)."""
        return tuple(n for n, e in self._entries.items() if e.reviewed_by is None)

    def fixture_only_names(self) -> tuple[str, ...]:
        """The entries marked FIXTURE-ONLY (ADR-027), in file order."""
        return self._fixture_names

    def overrides(self) -> tuple[RegistryOverride, ...]:
        """The clinician-approved ranges for per-patient values (empty in version 0.x)."""
        return self._overrides

    @property
    def fixture_only(self) -> bool:
        """True if the file holds FIXTURE-ONLY rows: results obtained with it are not reportable."""
        return bool(self._fixture_names)

    @property
    def path(self) -> Path:
        return self._path

    @property
    def sha256(self) -> str:
        """SHA-256 (hex) of the bytes of the file, to tie a reported number to the exact file."""
        return self._sha256

    @property
    def step_ms(self) -> int | None:
        return self._step_ms

    @property
    def pathology(self) -> str:
        return self._pathology

    @property
    def review_status(self) -> str:
        return self._review_status

    @property
    def window_parameters(self) -> tuple[str, ...]:
        return self._windows


def _unset_message(unset: _Unset) -> str:
    return (
        f"parameter {unset.name!r} is declared but has no value yet "
        f"(required by {list(unset.required_by)}; {unset.note})"
    )


# ---------------------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------------------


def _repo_root() -> Path | None:
    """The directory that holds ``pyproject.toml``, searched upwards from this file."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    return None


def default_registry_path() -> Path:
    """``configs/registry/hypertension.yaml`` under the directory that holds ``pyproject.toml``."""
    root = _repo_root()
    if root is None:
        raise RegistryError(
            "cannot locate configs/registry/hypertension.yaml: no pyproject.toml above the "
            "ralmon package; pass the path of the registry file"
        )
    return root.joinpath(*DEFAULT_REGISTRY_RELPATH)


def load_registry(
    path: str | Path | None = None,
    *,
    step_ms: int | None = None,
    allow_fixture_only: bool = False,
) -> LoadedRegistry:
    """Load and validate a registry file.

    ``path`` is ``configs/registry/hypertension.yaml`` when ``None``. ``step_ms`` is the monitor step
    (``MonitorConfig.step_ms``); it is needed to evaluate derived names and enables the alignment
    check of the window parameters. A file with FIXTURE-ONLY rows (ADR-027) needs
    ``allow_fixture_only=True``. Every problem raises ``RegistryError``.
    """
    if not isinstance(allow_fixture_only, bool):
        raise RegistryError(
            f"allow_fixture_only must be a bool, got {show(allow_fixture_only)}"
        )
    if step_ms is not None and (
        isinstance(step_ms, bool) or not isinstance(step_ms, int) or step_ms <= 0
    ):
        raise RegistryError(
            f"step_ms must be a positive int or None, got {show(step_ms)}"
        )
    resolved = (
        default_registry_path()
        if path is None
        else coerce_path(path, RegistryError, "registry")
    )
    data = read_limited_bytes(resolved, RegistryError, "registry")
    document = parse_yaml_bytes(data, RegistryError, f"registry {resolved}")
    if not isinstance(document, Mapping):
        raise RegistryError(
            f"registry {resolved}: the file must hold a mapping at top level"
        )
    registry = _build(document, resolved, hashlib.sha256(data).hexdigest(), step_ms)
    if registry.fixture_only and not allow_fixture_only:
        raise RegistryError(
            f"registry {resolved} contains {FIXTURE_ONLY_MARKER} rows "
            f"{list(registry.fixture_only_names())}: arithmetic test numbers that must not be used "
            "for a reported result (ADR-027); pass allow_fixture_only=True only in tests"
        )
    return registry


def _check_keys(
    mapping: Mapping[object, object],
    required: Sequence[str],
    optional: Sequence[str],
    where: str,
) -> None:
    unknown = sorted(str(k) for k in mapping if k not in required and k not in optional)
    missing = [k for k in required if k not in mapping]
    if unknown or missing:
        raise RegistryError(
            f"{where}: unknown key(s) {unknown}, missing required key(s) {missing}"
        )


def _name(value: object, where: str) -> str:
    if not isinstance(value, str) or _NAME_RE.fullmatch(value) is None:
        raise RegistryError(
            f"{where}: a name must match [a-z][a-z0-9_]*, got {show(value)}"
        )
    if value == STEP_NAME:
        raise RegistryError(
            f"{where}: {STEP_NAME!r} is monitor configuration, not a registry name"
        )
    return value


def _text(value: object, field: str, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RegistryError(
            f"{where}: {field} must be a non-empty string, got {show(value)}"
        )
    return value


def _reviewer(value: object, where: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise RegistryError(
            f"{where}: reviewed_by must be a non-empty string or null, got {show(value)}"
        )
    return value


def _unit(value: object, where: str) -> str:
    if not isinstance(value, str) or value not in UNITS:
        raise RegistryError(
            f"{where}: unit must be one of {list(UNITS)}, got {show(value)}"
        )
    return value


def _finite_float(value: object, field: str, where: str) -> float:
    if not _is_number(value):
        raise RegistryError(
            f"{where}: {field} must be a finite number, got {show(value)}"
        )
    try:
        number = float(value)  # type: ignore[arg-type]
    except OverflowError as exc:
        raise RegistryError(
            f"{where}: {field} is outside the float range: {show(value)}"
        ) from exc
    if not math.isfinite(number):
        raise RegistryError(f"{where}: {field} must be finite, got {show(value)}")
    return number


def _list(document: Mapping[object, object], key: str) -> list[object]:
    value = document[key]
    if not isinstance(value, list):
        raise RegistryError(f"{key} must be a list, got {show(value)}")
    return value


def _mapping(value: object, where: str) -> Mapping[object, object]:
    if not isinstance(value, Mapping):
        raise RegistryError(f"{where} must be a mapping, got {show(value)}")
    return value


def _label(raw: Mapping[object, object], key: str, index: int, section: str) -> str:
    """``section[index] (name)`` for error messages."""
    name = raw.get(key)
    if isinstance(name, str) and _NAME_RE.fullmatch(name) is not None:
        return f"{section}[{index}] ({name})"
    return f"{section}[{index}]"


def _parse_entry(raw: object, index: int) -> RegistryEntry:
    mapping = _mapping(raw, f"entries[{index}]")
    where = _label(mapping, "name", index, "entries")
    _check_keys(mapping, _ENTRY_KEYS, (), where)
    name = _name(mapping["name"], where)
    unit = _unit(mapping["unit"], where)
    value = _finite_float(mapping["value"], "value", where)
    rationale = _text(mapping["rationale"], "rationale", where)
    source_ref = _text(mapping["source_ref"], "source_ref", where)
    reviewed_by = _reviewer(mapping["reviewed_by"], where)
    if reviewed_by is None and not rationale.endswith(UNVERIFIED_SUFFIX):
        raise RegistryError(
            f"{where}: an entry with reviewed_by null must have a rationale that ends with "
            f"'{UNVERIFIED_SUFFIX}' (ADR-020)"
        )
    _check_value_rules(name, unit, value, where)
    return RegistryEntry(name, value, unit, rationale, source_ref, reviewed_by)


def _check_value_rules(name: str, unit: str, value: float, where: str) -> None:
    """The cast rules of 03 section 2.6 and the checks of section 2.5 rule 10 that do not need the
    template table."""
    if unit == "ms" and (not value.is_integer() or value < 0):
        raise RegistryError(
            f"{where}: a duration (unit ms) must be a non-negative integer, got {value!r}"
        )
    for template in TEMPLATE_IDS:
        if name == f"scale_{template}":
            if unit not in SCALE_UNITS or not value > 0:
                raise RegistryError(
                    f"{where}: a scale must be positive with unit mmHg, ms or dose, "
                    f"got {value!r} {unit!r}"
                )
        elif name == f"priority_{template}" and (
            unit != "1" or not value.is_integer() or value < 1
        ):
            raise RegistryError(
                f"{where}: a priority must be an integral rank >= 1 with unit '1', "
                f"got {value!r} {unit!r}"
            )


def _parse_derived(raw: object, index: int) -> _Derived:
    mapping = _mapping(raw, f"derived[{index}]")
    where = _label(mapping, "name", index, "derived")
    _check_keys(mapping, _DERIVED_KEYS, (), where)
    name = _name(mapping["name"], where)
    unit = _unit(mapping["unit"], where)
    formula = mapping["formula"]
    if not isinstance(formula, str) or _FORMULA_RE.fullmatch(formula) is None:
        raise RegistryError(
            f"{where}: formula must be a sum of registry names and {STEP_NAME} "
            f"(term + term ...), got {show(formula)}"
        )
    template = mapping["template"]
    if not isinstance(template, str) or template not in TEMPLATE_IDS:
        raise RegistryError(
            f"{where}: template must be one of {list(TEMPLATE_IDS)}, got {show(template)}"
        )
    terms = tuple(term.strip() for term in formula.split("+"))
    return _Derived(name, unit, terms, template)


def _parse_unset(raw: object, index: int) -> _Unset:
    mapping = _mapping(raw, f"unset[{index}]")
    where = _label(mapping, "parameter", index, "unset")
    _check_keys(mapping, _UNSET_KEYS, (), where)
    name = _name(mapping["parameter"], where)
    unit = _unit(mapping["unit"], where)
    required = mapping["required_by"]
    if (
        not isinstance(required, list)
        or any(not isinstance(t, str) or t not in TEMPLATE_IDS for t in required)
        or len(set(required)) != len(required)
    ):
        raise RegistryError(
            f"{where}: required_by must be a list of distinct template ids "
            f"{list(TEMPLATE_IDS)}, got {show(required)}"
        )
    note = _text(mapping["note"], "note", where)
    return _Unset(name, unit, tuple(required), note)


def _parse_override(
    raw: object, index: int, entry_names: Mapping[str, RegistryEntry]
) -> RegistryOverride:
    where = f"overrides[{index}]"
    mapping = _mapping(raw, where)
    _check_keys(mapping, _OVERRIDE_KEYS, (), where)
    name = _name(mapping["name"], where)
    if name not in entry_names:
        raise RegistryError(f"{where}: {name!r} is not an entry of the registry")
    low = _finite_float(mapping["min"], "min", where)
    high = _finite_float(mapping["max"], "max", where)
    if low > high:
        raise RegistryError(f"{where}: min {low!r} is above max {high!r}")
    return RegistryOverride(
        name,
        low,
        high,
        _text(mapping["rationale"], "rationale", where),
        _text(mapping["source_ref"], "source_ref", where),
        _reviewer(mapping["reviewed_by"], where),
    )


def _check_unique_names(
    entries: Sequence[RegistryEntry],
    derived: Sequence[_Derived],
    unset: Sequence[_Unset],
) -> None:
    where_of: dict[str, str] = {}
    labelled = (
        [(e.name, "entries") for e in entries]
        + [(d.name, "derived") for d in derived]
        + [(u.name, "unset") for u in unset]
    )
    for name, section in labelled:
        if name in where_of:
            raise RegistryError(
                f"duplicate parameter name {name!r} (in {where_of[name]} and in {section})"
            )
        where_of[name] = section


def _check_derived_terms(
    derived: Sequence[_Derived],
    entries: Mapping[str, RegistryEntry],
    unset: Mapping[str, _Unset],
) -> None:
    for item in derived:
        where = f"derived ({item.name})"
        for term in item.terms:
            if term == STEP_NAME:
                if item.unit != "ms":
                    raise RegistryError(
                        f"{where}: {STEP_NAME} is a duration, but the unit is {item.unit!r}"
                    )
                continue
            if term in entries:
                if entries[term].unit != item.unit:
                    raise RegistryError(
                        f"{where}: term {term!r} has unit {entries[term].unit!r}, "
                        f"not {item.unit!r}"
                    )
            elif term in unset:
                if unset[term].unit != item.unit:
                    raise RegistryError(
                        f"{where}: term {term!r} has unit {unset[term].unit!r}, "
                        f"not {item.unit!r}"
                    )
            else:
                raise RegistryError(
                    f"{where}: term {term!r} is not an entry or an unset name"
                )


def _check_windows(
    windows: Sequence[str],
    entries: Mapping[str, RegistryEntry],
    unset: Mapping[str, _Unset],
    derived: Mapping[str, _Derived],
    step_ms: int | None,
) -> None:
    for name in windows:
        if name in entries:
            unit = entries[name].unit
        elif name in unset:
            unit = unset[name].unit
        elif name in derived:
            raise RegistryError(
                f"window_parameters: {name!r} is a derived name, not a window parameter"
            )
        else:
            raise RegistryError(
                f"window_parameters: {name!r} is neither an entry nor an unset name"
            )
        if unit != "ms":
            raise RegistryError(
                f"window_parameters: {name!r} has unit {unit!r}; a window is a duration in ms"
            )
    if step_ms is None:
        return
    for name in windows:
        entry = entries.get(name)
        if entry is not None and int(entry.value) % step_ms != 0:
            raise RegistryError(
                f"window parameter {name!r} = {entry.value!r} is not a multiple of "
                f"step_ms {step_ms}"
            )
    start, end = entries.get(WINDOW_START), entries.get(WINDOW_END)
    if start is not None and end is not None and end.value - start.value < 0:
        raise RegistryError(
            f"{WINDOW_END} - {WINDOW_START} must be a non-negative multiple of step_ms "
            f"{step_ms}, got {end.value - start.value!r}"
        )


def _check_bound_pairs(entries: Mapping[str, RegistryEntry]) -> None:
    for name, lower in entries.items():
        match = _BOUND_LOWER_RE.fullmatch(name)
        if match is None:
            continue
        upper = entries.get(f"bound_{match.group(1)}_upper")
        if upper is not None and not lower.value < upper.value:
            raise RegistryError(
                f"physiological bounds of signal {match.group(1)!r}: lower {lower.value!r} "
                f"must be below upper {upper.value!r}"
            )


def _check_review_status(
    status: str, entries: Sequence[RegistryEntry], unset: Mapping[str, _Unset]
) -> None:
    reviewed = [e.reviewed_by is not None for e in entries]
    if not any(reviewed):
        expected = "unreviewed"
    elif all(reviewed) and not unset:
        expected = "reviewed"
    else:
        expected = "partially_reviewed"
    if status != expected:
        raise RegistryError(
            f"review_status is {status!r} but the entries say {expected!r}"
        )


def _build(
    document: Mapping[object, object], path: Path, digest: str, step_ms: int | None
) -> LoadedRegistry:
    where = f"registry {path}"
    _check_keys(document, _TOP_REQUIRED, _TOP_OPTIONAL, where)
    version = document["registry_version"]
    if not isinstance(version, str) or _VERSION_RE.fullmatch(version) is None:
        raise RegistryError(
            f"registry_version must be a MAJOR.MINOR.PATCH string, got {show(version)}"
        )
    pathology = document["pathology"]
    if not isinstance(pathology, str) or not pathology.strip():
        raise RegistryError(
            f"pathology must be a non-empty string, got {show(pathology)}"
        )
    status = document["review_status"]
    if not isinstance(status, str) or status not in REVIEW_STATUSES:
        raise RegistryError(
            f"review_status must be one of {list(REVIEW_STATUSES)}, got {show(status)}"
        )
    windows_raw = _list(document, "window_parameters")
    windows = tuple(
        _name(w, f"window_parameters[{i}]") for i, w in enumerate(windows_raw)
    )
    repeated = sorted({w for w in windows if windows.count(w) > 1})
    if repeated:
        raise RegistryError(f"window_parameters must not repeat a name: {repeated}")
    entries = [_parse_entry(raw, i) for i, raw in enumerate(_list(document, "entries"))]
    derived = [
        _parse_derived(raw, i) for i, raw in enumerate(_list(document, "derived"))
    ]
    unset = [_parse_unset(raw, i) for i, raw in enumerate(_list(document, "unset"))]
    _check_unique_names(entries, derived, unset)
    entry_map = {e.name: e for e in entries}
    derived_map = {d.name: d for d in derived}
    unset_map = {u.name: u for u in unset}
    _check_derived_terms(derived, entry_map, unset_map)
    _check_windows(windows, entry_map, unset_map, derived_map, step_ms)
    _check_bound_pairs(entry_map)
    _check_review_status(status, entries, unset_map)
    overrides_raw = _list(document, "overrides") if "overrides" in document else []
    overrides = tuple(
        _parse_override(raw, i, entry_map) for i, raw in enumerate(overrides_raw)
    )
    fixture_names = tuple(
        e.name
        for e in entries
        if e.rationale.startswith(FIXTURE_ONLY_MARKER)
        or e.source_ref.startswith(FIXTURE_ONLY_MARKER)
    )
    return LoadedRegistry(
        path=path,
        sha256=digest,
        version=version,
        pathology=pathology,
        review_status=status,
        window_parameters=windows,
        entries=entry_map,
        derived=derived_map,
        unset=unset_map,
        overrides=overrides,
        fixture_names=fixture_names,
        step_ms=step_ms,
    )
