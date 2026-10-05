"""PriorSource contract and ``LiteraturePriorSource`` (02-interfaces.md#priorsource).

Every parameter of the latent patient, the PK/PD response, the adherence model and the
device error model reaches the benchmark through a ``PriorSource`` (ADR-005). The first
implementation reads ``configs/priors/literature_hypertension.yaml``: one row per
contract field, each with a unit, a value or a distribution, a ``source_ref``, a
``source_type``, a ``verified_by`` and a ``status``. The module never chooses a number:

* a row with a value and no ``source_ref`` makes the constructor fail
  (``MissingProvenanceError``);
* a row that no human has filled stays ``awaiting_human_value`` and is refused on use
  (``UnfilledParameterError``);
* a prior made of arithmetic test numbers is marked ``fixture_only`` and is refused unless
  the caller passes ``allow_fixture_only=True`` (``FixtureOnlyPriorError``).

``python -m ralmon.benchmark.priors --write-table | --check-table`` renders the
parameter-provenance table ``docs/benchmark/parameter-provenance.md`` that a human
verifies (H1 of the WS04 README). Time is integer milliseconds (ADR-017); randomness comes
only from the ``numpy.random.Generator`` the caller passes in.
"""

from __future__ import annotations

import argparse
import json
import math
import numbers
import re
import statistics
import sys
from collections.abc import Hashable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Protocol

import numpy as np
import yaml

from ralmon.signals import DurationMs

__all__ = [
    "BEGIN_MARKER",
    "DIST_FAMILIES",
    "END_MARKER",
    "SOURCE_TYPES",
    "STATUSES",
    "AdherenceParams",
    "DeviceErrorModel",
    "Distribution",
    "FixtureOnlyPriorError",
    "LiteraturePriorSource",
    "MissingProvenanceError",
    "ParamProvenance",
    "ParameterFile",
    "ParameterRow",
    "PatientParams",
    "PriorConfigError",
    "PriorError",
    "PriorSource",
    "UnfilledParameterError",
    "collect_parameter_files",
    "load_design_file",
    "load_prior_file",
    "main",
    "parse_distribution",
    "render_provenance_table",
]

PRIOR_FILE_VERSION: Final = "0.1.0"
PRIORS_RELPATH: Final = "configs/priors/literature_hypertension.yaml"
# Sibling configs of the generator; read when present (each owned by a later task).
DESIGN_RELPATHS: Final = (
    "configs/benchmark/generator_design.yaml",
    "configs/benchmark/care_plans.yaml",
    "configs/benchmark/injections.yaml",
)
TABLE_RELPATH: Final = "docs/benchmark/parameter-provenance.md"
BEGIN_MARKER: Final = "<!-- BEGIN GENERATED -->"
END_MARKER: Final = "<!-- END GENERATED -->"

SOURCE_TYPES: Final = (
    "published_literature",
    "standard",
    "public_dataset",
    "design_choice",
    "declared_assumption",
    "illustrative_unverified",
    "fixture_only",
)
STATUSES: Final = ("filled", "awaiting_human_value")
STATUS_FILLED: Final = "filled"
STATUS_AWAITING: Final = "awaiting_human_value"
SOURCE_FIXTURE: Final = "fixture_only"
FIXTURE_PREFIX: Final = "FIXTURE-ONLY"
FIXTURE_NAME_SUFFIX: Final = "-FIXTURE-ONLY"

# Parameters of each distribution family, in the order they are written and rendered.
DIST_FAMILIES: Final[Mapping[str, tuple[str, ...]]] = {
    "constant": ("value",),
    "uniform": ("lo", "hi"),
    "normal": ("mean", "sd"),
    "lognormal": ("log_mean", "log_sd"),
}

_ROW_KEYS: Final = (
    "parameter",
    "unit",
    "value",
    "dist",
    "source_ref",
    "source_type",
    "verified_by",
    "status",
    "consumer_task",
    "rationale",
    "note",
)
_OPTIONAL_ROW_KEYS: Final = ("reference_step_ms",)
_TOP_KEYS: Final = frozenset(
    {"schema_version", "name", "pathology", "fixture_only", "parameters"}
)
_REFERENCE_STEP_REQUIRED: Final = frozenset({"ar_noise_phi"})
_NAME_RE: Final = re.compile(r"[a-z][a-z0-9_]*")
_TASK_RE: Final = re.compile(r"WS\d\d-T\d\d")
_UNFILLED_REF: Final = STATUS_AWAITING  # provenance text of a row with no source yet
_ONSET_KEYS: Final = ("lower_ms", "upper_ms")


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class PriorError(Exception):
    """Base class of the errors of this module."""


class PriorConfigError(PriorError):
    """A prior file is malformed, inconsistent or outside the parameter domain."""


class MissingProvenanceError(PriorError):
    """A value is present without a source_ref, source_type or rationale."""


class UnfilledParameterError(PriorError):
    """A parameter that no human has filled was used (or strict loading was asked)."""


class FixtureOnlyPriorError(PriorError):
    """A fixture-only prior was loaded without ``allow_fixture_only=True``."""


# ---------------------------------------------------------------------------
# Contract (02-interfaces.md#priorsource, version 0.1.0): copied verbatim
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ParamProvenance:
    name: str
    source_ref: (
        str  # citation or dataset table; mandatory, agents must not invent values
    )
    verified_by: (
        str | None
    )  # human who verified the value (None = unverified, must be reported)


@dataclass(frozen=True, slots=True)
class PatientParams:
    patient_id: str
    baseline_sbp_mmhg: float
    circadian_amplitude_mmhg: (
        float  # HALF the peak-to-trough difference (baseline +- A)
    )
    ar_noise_sd_mmhg: float
    ar_noise_phi: float
    emax_mmhg: float  # maximal drug effect (Emax model)
    ec50: float
    absorption_rate_per_h: float
    elimination_rate_per_h: float
    onset_delay_range_ms: tuple[DurationMs, DurationMs]  # informs Delta1, Delta2


@dataclass(frozen=True, slots=True)
class AdherenceParams:
    p_delay: float
    p_omission: float
    p_double_take: float
    mean_delay_ms: DurationMs
    # Markov state model of adherence; declared as an assumption (analisi §5.1)


@dataclass(frozen=True, slots=True)
class DeviceErrorModel:
    cuff_error_sd_mmhg: (
        float  # from device validation protocols; the source is verified by a human
    )
    cuff_bias_mmhg: float
    dispenser_bounce_prob: float
    ble_dropout_rate_per_h: float


class PriorSource(Protocol):
    name: str

    def sample_patient(
        self, rng: np.random.Generator, patient_index: int
    ) -> PatientParams: ...

    def adherence(self) -> AdherenceParams: ...

    def device_errors(self) -> DeviceErrorModel: ...

    def provenance(self) -> Sequence[ParamProvenance]: ...


# ---------------------------------------------------------------------------
# Field specifications (names, units and domains; no clinical value is stored here)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Domain:
    """Interval of admissible values; an open end excludes its bound."""

    lo: float
    lo_open: bool
    hi: float
    hi_open: bool

    def contains_support(
        self, lo: float, lo_open: bool, hi: float, hi_open: bool
    ) -> bool:
        lower = lo > self.lo or (lo == self.lo and (lo_open or not self.lo_open))
        upper = hi < self.hi or (hi == self.hi and (hi_open or not self.hi_open))
        return lower and upper

    def contains(self, x: float) -> bool:
        return self.contains_support(x, False, x, False)

    def describe(self) -> str:
        left = "(" if self.lo_open else "["
        right = ")" if self.hi_open else "]"
        return f"{left}{self.lo}, {self.hi}{right}"


_REAL = _Domain(-math.inf, True, math.inf, True)
_POSITIVE = _Domain(0.0, True, math.inf, True)
_NONNEG = _Domain(0.0, False, math.inf, True)
_UNIT_INTERVAL = _Domain(0.0, False, 1.0, False)
_STATIONARY = _Domain(-1.0, True, 1.0, True)  # algorithmic: |phi| < 1 for AR(1)

_FLOAT: Final = "float"
_MS_INT: Final = "ms_int"
_RANGE: Final = "range"
_PATIENT: Final = "patient"
_ADHERENCE: Final = "adherence"
_DEVICE: Final = "device"


@dataclass(frozen=True, slots=True)
class _FieldSpec:
    parameter: str
    owner: str  # contract dataclass
    group: str
    unit: str
    kind: str
    domain: _Domain
    allows_dist: bool

    @property
    def field(self) -> str:
        return f"{self.owner}.{self.parameter}"


def _spec(
    parameter: str,
    owner: str,
    group: str,
    unit: str,
    domain: _Domain,
    *,
    kind: str = _FLOAT,
    dist: bool = False,
) -> _FieldSpec:
    return _FieldSpec(parameter, owner, group, unit, kind, domain, dist)


_PP: Final = "PatientParams"
_AP: Final = "AdherenceParams"
_DM: Final = "DeviceErrorModel"
# Contract order. ec50 has no unit in the contract: it is read as a concentration
# normalised to the unit dose (dimensionless), a gap recorded in ADR-038.
_SPECS: Final[tuple[_FieldSpec, ...]] = (
    _spec("baseline_sbp_mmhg", _PP, _PATIENT, "mmHg", _POSITIVE, dist=True),
    _spec("circadian_amplitude_mmhg", _PP, _PATIENT, "mmHg", _NONNEG, dist=True),
    _spec("ar_noise_sd_mmhg", _PP, _PATIENT, "mmHg", _NONNEG, dist=True),
    _spec("ar_noise_phi", _PP, _PATIENT, "1", _STATIONARY, dist=True),
    _spec("emax_mmhg", _PP, _PATIENT, "mmHg", _REAL, dist=True),
    _spec("ec50", _PP, _PATIENT, "1", _POSITIVE, dist=True),
    _spec("absorption_rate_per_h", _PP, _PATIENT, "1/h", _POSITIVE, dist=True),
    _spec("elimination_rate_per_h", _PP, _PATIENT, "1/h", _POSITIVE, dist=True),
    _spec("onset_delay_range_ms", _PP, _PATIENT, "ms", _NONNEG, kind=_RANGE),
    _spec("p_delay", _AP, _ADHERENCE, "1", _UNIT_INTERVAL),
    _spec("p_omission", _AP, _ADHERENCE, "1", _UNIT_INTERVAL),
    _spec("p_double_take", _AP, _ADHERENCE, "1", _UNIT_INTERVAL),
    _spec("mean_delay_ms", _AP, _ADHERENCE, "ms", _NONNEG, kind=_MS_INT),
    _spec("cuff_error_sd_mmhg", _DM, _DEVICE, "mmHg", _NONNEG),
    _spec("cuff_bias_mmhg", _DM, _DEVICE, "mmHg", _REAL),
    _spec("dispenser_bounce_prob", _DM, _DEVICE, "1", _UNIT_INTERVAL),
    _spec("ble_dropout_rate_per_h", _DM, _DEVICE, "1/h", _NONNEG),
)
_SPEC_BY_NAME: Final = {s.parameter: s for s in _SPECS}
_PROBABILITY_SUM: Final = ("p_delay", "p_omission", "p_double_take")


# ---------------------------------------------------------------------------
# Distributions
# ---------------------------------------------------------------------------

_STD_NORMAL: Final = statistics.NormalDist()
_P_MIN: Final = math.nextafter(0.0, 1.0)
_P_MAX: Final = math.nextafter(1.0, 0.0)
_U_MAX: Final = math.nextafter(1.0, 0.0)  # the largest value of Generator.random()


@dataclass(frozen=True, slots=True)
class Distribution:
    """A validated, optionally truncated distribution; sampling is by inverse CDF.

    Every draw consumes exactly one uniform number, whatever the family, so the stream of
    a seeded generator does not depend on which family a row uses.
    """

    family: str
    params: tuple[tuple[str, float], ...]
    trunc_lo: float | None
    trunc_hi: float | None
    support_lo: float
    support_lo_open: bool
    support_hi: float
    support_hi_open: bool
    degenerate: bool  # one point of positive mass: constant, or a zero spread
    _p_lo: float
    _p_hi: float

    def param(self, name: str) -> float:
        return dict(self.params)[name]

    def ppf(self, u: float) -> float:
        """Quantile for ``u`` in [0, 1); the result always lies inside the truncation."""
        if self.degenerate:
            return self.support_lo
        if self.family == "uniform":
            x = self.support_lo + u * (self.support_hi - self.support_lo)
        else:
            p = min(max(self._p_lo + u * (self._p_hi - self._p_lo), _P_MIN), _P_MAX)
            z = _STD_NORMAL.inv_cdf(p)
            if self.family == "normal":
                x = self.param("mean") + self.param("sd") * z
            else:
                x = _exp(self.param("log_mean") + self.param("log_sd") * z)
        return min(max(x, self.support_lo), self.support_hi)

    def check_sampling_range(self, parameter: str) -> None:
        """Refuse a distribution whose quantile range is not a finite set of floats.

        ``ppf`` is monotone, so its two edge values bound every draw: both must be finite
        and must not sit on an open end of the support (a lognormal underflowing to
        ``0.0`` would be a draw outside the strictly positive support the loader checked).
        """
        for u in (0.0, _U_MAX):
            x = self.ppf(u)
            if not math.isfinite(x):
                raise PriorConfigError(
                    f"{parameter}: {self.describe()} draws a non-finite value "
                    f"({x}) at u = {u}; its parameters are out of the float range"
                )
        low, high = self.ppf(0.0), self.ppf(_U_MAX)
        if (self.support_lo_open and low <= self.support_lo) or (
            self.support_hi_open and high >= self.support_hi
        ):
            raise PriorConfigError(
                f"{parameter}: {self.describe()} cannot be represented as floats inside "
                f"its support over the quantile range used for sampling "
                f"(draws {low} to {high})"
            )

    def describe(self) -> str:
        inner = ", ".join(f"{k}={v!r}" for k, v in self.params)
        text = f"{self.family}({inner})"
        if self.trunc_lo is not None or self.trunc_hi is not None:
            bounds = []
            if self.trunc_lo is not None:
                bounds.append(f"lo={self.trunc_lo!r}")
            if self.trunc_hi is not None:
                bounds.append(f"hi={self.trunc_hi!r}")
            text += f" truncate[{', '.join(bounds)}]"
        return text


def _exp(x: float) -> float:
    """``math.exp`` that returns ``inf`` on overflow (the caller refuses a non-finite draw)."""
    try:
        return math.exp(x)
    except OverflowError:
        return math.inf


def _is_number(x: object) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _finite(where: str, what: str, x: object) -> float:
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        raise PriorConfigError(f"{where}: {what} must be a finite number, got {x!r}")
    return float(x)


def _integral(where: str, what: str, x: object) -> int:
    value = _finite(where, what, x)
    if not value.is_integer():
        raise PriorConfigError(f"{where}: {what} must be an integer, got {x!r}")
    return int(value)


def _phi(z: float) -> float:
    if z == -math.inf:
        return 0.0
    if z == math.inf:
        return 1.0
    return _STD_NORMAL.cdf(z)


def parse_distribution(parameter: str, raw: object) -> Distribution:
    """Validate a ``dist`` mapping; raise ``PriorConfigError`` naming ``parameter``."""
    if not isinstance(raw, Mapping):
        raise PriorConfigError(f"{parameter}: dist must be a mapping, got {raw!r}")
    family = raw.get("family")
    if not isinstance(family, str) or family not in DIST_FAMILIES:
        raise PriorConfigError(
            f"{parameter}: distribution family {family!r} is not in the allow-list "
            f"{sorted(DIST_FAMILIES)}"
        )
    names = DIST_FAMILIES[family]
    unknown = sorted(str(k) for k in raw if k not in {"family", "truncate", *names})
    if unknown:
        raise PriorConfigError(
            f"{parameter}: unknown key(s) {unknown} for family {family!r}"
        )
    missing = [n for n in names if n not in raw]
    if missing:
        raise PriorConfigError(f"{parameter}: family {family!r} needs {missing}")
    values = {n: _finite(parameter, n, raw[n]) for n in names}
    trunc_lo, trunc_hi = _parse_truncation(parameter, raw)
    return _build(parameter, family, values, trunc_lo, trunc_hi)


def _parse_truncation(
    parameter: str, raw: Mapping[str, object]
) -> tuple[float | None, float | None]:
    if "truncate" not in raw:
        return None, None
    spec = raw["truncate"]
    if not isinstance(spec, Mapping) or not spec:
        raise PriorConfigError(
            f"{parameter}: truncate must be a non-empty mapping with lo and/or hi"
        )
    extra = sorted(str(k) for k in spec if k not in {"lo", "hi"})
    if extra:
        raise PriorConfigError(f"{parameter}: unknown truncate key(s) {extra}")
    lo = _finite(parameter, "truncate.lo", spec["lo"]) if "lo" in spec else None
    hi = _finite(parameter, "truncate.hi", spec["hi"]) if "hi" in spec else None
    if lo is not None and hi is not None and not lo < hi:
        raise PriorConfigError(
            f"{parameter}: truncate needs lo < hi, got {lo} and {hi}"
        )
    return lo, hi


def _build(
    parameter: str,
    family: str,
    values: dict[str, float],
    trunc_lo: float | None,
    trunc_hi: float | None,
) -> Distribution:
    names = DIST_FAMILIES[family]
    params = tuple((n, values[n]) for n in names)
    t_lo = -math.inf if trunc_lo is None else trunc_lo
    t_hi = math.inf if trunc_hi is None else trunc_hi

    def point(x: float) -> Distribution:
        if not t_lo <= x <= t_hi:
            raise PriorConfigError(
                f"{parameter}: the point {x} lies outside the truncation [{t_lo}, {t_hi}]"
            )
        return Distribution(
            family, params, trunc_lo, trunc_hi, x, False, x, False, True, 0.0, 1.0
        )

    if family == "constant":
        return point(values["value"])
    if family == "uniform":
        lo, hi = values["lo"], values["hi"]
        if not lo < hi:
            raise PriorConfigError(
                f"{parameter}: uniform needs lo < hi, got {lo}, {hi}"
            )
        eff_lo, eff_hi = max(lo, t_lo), min(hi, t_hi)
        if not eff_lo < eff_hi:
            raise PriorConfigError(
                f"{parameter}: the truncation leaves no positive-length interval of "
                f"uniform({lo}, {hi})"
            )
        return Distribution(
            family,
            params,
            trunc_lo,
            trunc_hi,
            eff_lo,
            False,
            eff_hi,
            False,
            False,
            0.0,
            1.0,
        )
    spread = values["sd"] if family == "normal" else values["log_sd"]
    centre = values["mean"] if family == "normal" else values["log_mean"]
    if spread < 0.0:
        raise PriorConfigError(f"{parameter}: the spread of {family} must be >= 0")
    if family == "normal":
        sup_lo, lo_open = t_lo, trunc_lo is None
        sup_hi, hi_open = t_hi, trunc_hi is None
        if spread == 0.0:
            return point(centre)
        z_lo = (t_lo - centre) / spread if trunc_lo is not None else -math.inf
        z_hi = (t_hi - centre) / spread if trunc_hi is not None else math.inf
    else:
        if trunc_hi is not None and trunc_hi <= 0.0:
            raise PriorConfigError(
                f"{parameter}: lognormal has support (0, inf); truncate.hi {trunc_hi} "
                "leaves nothing"
            )
        positive_lo = trunc_lo is not None and trunc_lo > 0.0
        sup_lo, lo_open = (t_lo if positive_lo else 0.0), not positive_lo
        sup_hi, hi_open = t_hi, trunc_hi is None
        if spread == 0.0:
            mode = _exp(centre)
            if not 0.0 < mode < math.inf:
                raise PriorConfigError(
                    f"{parameter}: exp({centre}) of this lognormal is not a finite "
                    "strictly positive float"
                )
            return point(mode)
        z_lo = (math.log(t_lo) - centre) / spread if positive_lo else -math.inf
        z_hi = (math.log(t_hi) - centre) / spread if trunc_hi is not None else math.inf
    p_lo, p_hi = _phi(z_lo), _phi(z_hi)
    if not p_lo < p_hi:
        raise PriorConfigError(
            f"{parameter}: the truncation of {family} carries a negligible probability mass"
        )
    dist = Distribution(
        family,
        params,
        trunc_lo,
        trunc_hi,
        sup_lo,
        lo_open,
        sup_hi,
        hi_open,
        False,
        p_lo,
        p_hi,
    )
    dist.check_sampling_range(parameter)
    return dist


# ---------------------------------------------------------------------------
# Rows and files
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ParameterRow:
    """One validated row of a parameter file (the same schema in every file)."""

    parameter: str
    unit: str
    value: (
        Any  # None, a number, a {lower_ms, upper_ms} mapping, or numbers (design rows)
    )
    distribution: Distribution | None
    source_ref: str | None
    source_type: str | None
    verified_by: str | None
    status: str
    consumer_task: str
    rationale: str | None
    note: str
    reference_step_ms: int | None
    declares_reference_step: bool

    @property
    def filled(self) -> bool:
        return self.status == STATUS_FILLED

    @property
    def field(self) -> str | None:
        spec = _SPEC_BY_NAME.get(self.parameter)
        return None if spec is None else spec.field


@dataclass(frozen=True, slots=True)
class ParameterFile:
    path: Path
    name: str  # with the fixture suffix when fixture_only
    fixture_only: bool
    rows: tuple[ParameterRow, ...]


class _UniqueKeyLoader(yaml.SafeLoader):
    """Safe loader that refuses a repeated key instead of keeping the last one."""

    def construct_mapping(
        self, node: yaml.MappingNode, deep: bool = False
    ) -> dict[Hashable, Any]:
        seen: set[Hashable] = set()
        for key_node, _value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if isinstance(key, Hashable):
                if key in seen:
                    raise PriorConfigError(f"duplicate key {key!r} in the YAML mapping")
                seen.add(key)
        return super().construct_mapping(node, deep=deep)


def _read_yaml(path: Path) -> object:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PriorConfigError(f"cannot read {path}: {exc}") from exc
    try:
        return yaml.load(text, Loader=_UniqueKeyLoader)
    except yaml.YAMLError as exc:
        raise PriorConfigError(f"{path}: invalid YAML: {exc}") from exc
    except PriorConfigError as exc:
        raise PriorConfigError(f"{path}: {exc}") from exc


def _optional_str(where: str, key: str, x: object) -> str | None:
    if x is None or isinstance(x, str):
        return x
    raise PriorConfigError(f"{where}: {key} must be a string or null, got {x!r}")


def _numeric_structure(where: str, x: object) -> Any:
    """Finite numbers, or lists and mappings of them (rows of the design configs)."""
    if _is_number(x):
        return _finite(where, "value", x) if isinstance(x, float) else x
    if isinstance(x, list):
        return [_numeric_structure(where, item) for item in x]
    if isinstance(x, Mapping) and all(isinstance(k, str) for k in x):
        return {k: _numeric_structure(where, v) for k, v in x.items()}
    raise PriorConfigError(f"{where}: value must be numeric, got {x!r}")


def _parse_value(where: str, spec: _FieldSpec | None, raw: object) -> Any:
    if spec is None:
        return _numeric_structure(where, raw)
    if spec.kind == _RANGE:
        if not isinstance(raw, Mapping) or set(raw) != set(_ONSET_KEYS):
            raise PriorConfigError(
                f"{where}: value must be a mapping with exactly {list(_ONSET_KEYS)}"
            )
        lower, upper = (_integral(where, k, raw[k]) for k in _ONSET_KEYS)
        if not (spec.domain.contains(lower) and lower <= upper):
            raise PriorConfigError(
                f"{where}: needs {spec.domain.describe()} and lower_ms <= upper_ms, "
                f"got {lower} and {upper}"
            )
        return {"lower_ms": lower, "upper_ms": upper}
    number = _finite(where, "value", raw)
    if spec.kind == _MS_INT:
        number = float(_integral(where, "value", raw))
    if not spec.domain.contains(number):
        raise PriorConfigError(
            f"{where}: value {number} is outside the domain {spec.domain.describe()}"
        )
    return int(number) if spec.kind == _MS_INT else number


def _parse_row(
    raw: object, index: int, *, fixture_file: bool, contract: bool
) -> ParameterRow:
    if not isinstance(raw, Mapping):
        raise PriorConfigError(f"row {index}: a parameter row must be a mapping")
    name = raw.get("parameter")
    if not isinstance(name, str) or _NAME_RE.fullmatch(name) is None:
        raise PriorConfigError(
            f"row {index}: parameter must match [a-z][a-z0-9_]*, got {name!r}"
        )
    where = f"row {name!r}"
    unknown = sorted(str(k) for k in raw if k not in (*_ROW_KEYS, *_OPTIONAL_ROW_KEYS))
    if unknown:
        raise PriorConfigError(f"{where}: unknown key(s) {unknown}")
    missing = [k for k in _ROW_KEYS if k not in raw]
    if name in _REFERENCE_STEP_REQUIRED and "reference_step_ms" not in raw:
        missing.append("reference_step_ms")
    if missing:
        raise PriorConfigError(
            f"{where}: missing key(s) {missing} (write null explicitly)"
        )

    unit = raw["unit"]
    if not isinstance(unit, str) or not unit.strip():
        raise PriorConfigError(
            f"{where}: unit must be a non-empty string, got {unit!r}"
        )
    task = raw["consumer_task"]
    if not isinstance(task, str) or _TASK_RE.fullmatch(task) is None:
        raise PriorConfigError(
            f"{where}: consumer_task must look like WS04-T03, got {task!r}"
        )
    status = raw["status"]
    if status not in STATUSES:
        raise PriorConfigError(
            f"{where}: status must be one of {list(STATUSES)}, got {status!r}"
        )
    note = raw["note"]
    if not isinstance(note, str):
        raise PriorConfigError(f"{where}: note must be a string, got {note!r}")
    source_ref = _optional_str(where, "source_ref", raw["source_ref"])
    source_type = _optional_str(where, "source_type", raw["source_type"])
    rationale = _optional_str(where, "rationale", raw["rationale"])
    verified_by = _optional_str(where, "verified_by", raw["verified_by"])
    if source_type is not None and source_type not in SOURCE_TYPES:
        raise PriorConfigError(
            f"{where}: source_type must be one of {list(SOURCE_TYPES)}, got {source_type!r}"
        )
    if verified_by is not None and not verified_by.strip():
        raise PriorConfigError(
            f"{where}: verified_by must be a name or null, not blank"
        )

    has_value = raw["value"] is not None
    has_dist = raw["dist"] is not None
    if (has_value or has_dist) and not (source_ref and source_ref.strip()):
        raise MissingProvenanceError(f"{name}: a value without a source_ref")
    if (has_value or has_dist) and source_type is None:
        raise MissingProvenanceError(f"{name}: a value without a source_type")
    if (has_value or has_dist) and not (rationale and rationale.strip()):
        raise MissingProvenanceError(f"{name}: a value without a rationale")
    if has_value and has_dist:
        raise PriorConfigError(f"{where}: give value or dist, not both")
    if status == STATUS_FILLED and not (has_value or has_dist):
        raise PriorConfigError(f"{where}: status filled needs a value or a dist")
    if status == STATUS_AWAITING and (has_value or has_dist):
        raise PriorConfigError(
            f"{where}: status awaiting_human_value needs value and dist null"
        )
    if status == STATUS_AWAITING and verified_by is not None:
        raise PriorConfigError(f"{where}: an unfilled row cannot be verified")
    _check_fixture_consistency(where, fixture_file, source_ref, source_type, status)

    spec = _SPEC_BY_NAME.get(name) if contract else None
    if spec is not None and unit != spec.unit:
        raise PriorConfigError(f"{where}: unit must be {spec.unit!r}, got {unit!r}")
    value: Any = None
    distribution: Distribution | None = None
    if has_value:
        value = _parse_value(where, spec, raw["value"])
    if has_dist:
        if spec is not None and not spec.allows_dist:
            raise PriorConfigError(
                f"{where}: this field takes a value, not a distribution"
            )
        distribution = parse_distribution(name, raw["dist"])
        if spec is not None:
            _check_support(name, distribution, spec.domain)

    step: int | None = None
    declares = "reference_step_ms" in raw
    if declares and raw["reference_step_ms"] is not None:
        step = _integral(where, "reference_step_ms", raw["reference_step_ms"])
        if step <= 0:
            raise PriorConfigError(
                f"{where}: reference_step_ms must be > 0, got {step}"
            )
    if name in _REFERENCE_STEP_REQUIRED and status == STATUS_FILLED and step is None:
        raise PriorConfigError(
            f"{where}: a filled row needs reference_step_ms (the coefficient is meaningless "
            "without its sampling step)"
        )
    return ParameterRow(
        name, unit, value, distribution, source_ref, source_type, verified_by,
        status, task, rationale, note, step, declares,
    )  # fmt: skip


def _check_fixture_consistency(
    where: str,
    fixture_file: bool,
    source_ref: str | None,
    source_type: str | None,
    status: str,
) -> None:
    if fixture_file:
        if source_type not in (None, SOURCE_FIXTURE):
            raise PriorConfigError(
                f"{where}: a fixture_only file may only use source_type fixture_only"
            )
        if source_ref is not None and not source_ref.startswith(FIXTURE_PREFIX):
            raise PriorConfigError(
                f"{where}: in a fixture_only file source_ref must start with {FIXTURE_PREFIX}"
            )
        if status == STATUS_FILLED and source_type != SOURCE_FIXTURE:
            raise PriorConfigError(
                f"{where}: a filled row of a fixture_only file needs source_type fixture_only"
            )
    elif source_type == SOURCE_FIXTURE:
        raise PriorConfigError(
            f"{where}: source_type fixture_only is only allowed in a file with fixture_only: true"
        )


def _check_support(name: str, dist: Distribution, domain: _Domain) -> None:
    if not domain.contains_support(
        dist.support_lo, dist.support_lo_open, dist.support_hi, dist.support_hi_open
    ):
        raise PriorConfigError(
            f"{name}: the support of {dist.describe()} is not inside the domain "
            f"{domain.describe()}; truncate it"
        )


def _check_probability_sum(rows: Sequence[ParameterRow]) -> None:
    by_name = {r.parameter: r for r in rows}
    filled = [
        by_name[n].value for n in _PROBABILITY_SUM if n in by_name and by_name[n].filled
    ]
    if math.fsum(filled) > 1.0:
        raise PriorConfigError(
            f"{' + '.join(_PROBABILITY_SUM)} must not exceed 1, got {math.fsum(filled)}"
        )


def _rows_of(
    document: Mapping[str, object], path: Path, *, fixture_file: bool, contract: bool
) -> tuple[ParameterRow, ...]:
    raw_rows = document["parameters"]
    if not isinstance(raw_rows, list):
        raise PriorConfigError(f"{path}: parameters must be a list of rows")
    rows = tuple(
        _parse_row(raw, i, fixture_file=fixture_file, contract=contract)
        for i, raw in enumerate(raw_rows)
    )
    seen: set[str] = set()
    for row in rows:
        if row.parameter in seen:
            raise PriorConfigError(f"{path}: duplicate row {row.parameter!r}")
        seen.add(row.parameter)
    return rows


def load_prior_file(path: str | Path) -> ParameterFile:
    """Load and validate a prior file: exactly the 17 contract rows, strict top level."""
    path = Path(path)
    document = _read_yaml(path)
    if not isinstance(document, Mapping):
        raise PriorConfigError(f"{path}: the file must hold a mapping at top level")
    extra = sorted(str(k) for k in document if k not in _TOP_KEYS)
    absent = sorted(_TOP_KEYS - set(document))
    if extra or absent:
        raise PriorConfigError(
            f"{path}: unknown top-level key(s) {extra}, missing {absent}"
        )
    if document["schema_version"] != PRIOR_FILE_VERSION:
        raise PriorConfigError(f"{path}: schema_version must be {PRIOR_FILE_VERSION!r}")
    name, pathology, fixture = (
        document["name"],
        document["pathology"],
        document["fixture_only"],
    )
    if not isinstance(name, str) or not name.strip():
        raise PriorConfigError(f"{path}: name must be a non-empty string")
    if not isinstance(pathology, str) or not pathology.strip():
        raise PriorConfigError(f"{path}: pathology must be a non-empty string")
    if not isinstance(fixture, bool):
        raise PriorConfigError(
            f"{path}: fixture_only must be true or false, got {fixture!r}"
        )
    rows = _rows_of(document, path, fixture_file=fixture, contract=True)
    present = {r.parameter for r in rows}
    for row in rows:
        if row.parameter not in _SPEC_BY_NAME:
            raise PriorConfigError(
                f"{path}: row {row.parameter!r} is not a PriorSource contract field; "
                "put it in configs/benchmark/generator_design.yaml"
            )
    absent_fields = [s.parameter for s in _SPECS if s.parameter not in present]
    if absent_fields:
        raise PriorConfigError(
            f"{path}: missing row(s) for contract field(s) {absent_fields}"
        )
    _check_probability_sum(rows)
    if fixture and not name.endswith(FIXTURE_NAME_SUFFIX):
        name += FIXTURE_NAME_SUFFIX
    return ParameterFile(path, name, fixture, rows)


def load_design_file(path: str | Path) -> ParameterFile:
    """Load the rows of a sibling config (same row schema, other keys ignored).

    A file without a ``parameters`` list contributes no rows. The keys owned by the task
    that wrote the file are not validated here.
    """
    path = Path(path)
    document = _read_yaml(path)
    if not isinstance(document, Mapping):
        raise PriorConfigError(f"{path}: the file must hold a mapping at top level")
    if "parameters" not in document:
        return ParameterFile(path, path.stem, False, ())
    rows = _rows_of(document, path, fixture_file=False, contract=False)
    return ParameterFile(path, path.stem, False, rows)


# ---------------------------------------------------------------------------
# LiteraturePriorSource
# ---------------------------------------------------------------------------


def _names_in(group: str) -> tuple[str, ...]:
    return tuple(s.parameter for s in _SPECS if s.group == group)


class LiteraturePriorSource:
    """The ``PriorSource`` that reads ``configs/priors/literature_hypertension.yaml``.

    ``strict=True`` (default) refuses a file with an unfilled row at construction;
    ``strict=False`` loads it so that ``unfilled_names()`` can be reported, and the
    unfilled parameters are then refused on use. A fixture-only file needs
    ``allow_fixture_only=True``. Every draw of a distribution row consumes one uniform
    number from the generator; a row with a plain value consumes none.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        strict: bool = True,
        allow_fixture_only: bool = False,
    ) -> None:
        parsed = load_prior_file(path)
        if parsed.fixture_only and not allow_fixture_only:
            raise FixtureOnlyPriorError(
                f"{parsed.path} is a fixture-only prior (arithmetic test numbers, no source); "
                "pass allow_fixture_only=True only in tests"
            )
        self.name: str = parsed.name
        self.fixture_only: bool = parsed.fixture_only
        self.path: Path = parsed.path
        self._rows: dict[str, ParameterRow] = {r.parameter: r for r in parsed.rows}
        unfilled = self.unfilled_names()
        if strict and unfilled:
            raise UnfilledParameterError(_unfilled_message(unfilled))

    # -- reporting ----------------------------------------------------------------

    def unfilled_names(self) -> tuple[str, ...]:
        """Sorted names of the rows still ``awaiting_human_value``."""
        return tuple(sorted(n for n, r in self._rows.items() if not r.filled))

    def unverified_names(self) -> tuple[str, ...]:
        """Sorted names of filled rows without ``verified_by`` (unfilled rows are not listed)."""
        return tuple(
            sorted(
                n for n, r in self._rows.items() if r.filled and r.verified_by is None
            )
        )

    def provenance(self) -> tuple[ParamProvenance, ...]:
        """One entry per numeric contract field, in contract order."""
        entries = []
        for spec in _SPECS:
            row = self._rows[spec.parameter]
            ref = row.source_ref if row.source_ref else _UNFILLED_REF
            entries.append(ParamProvenance(spec.parameter, ref, row.verified_by))
        return tuple(entries)

    def reference_step_ms(self, name: str) -> DurationMs:
        """Sampling step (ms) at which the row ``name`` was estimated."""
        row = self._rows.get(name)
        if row is None:
            raise PriorConfigError(f"unknown parameter {name!r}")
        if not row.declares_reference_step:
            raise PriorConfigError(f"{name}: this row has no reference step")
        if row.reference_step_ms is None:
            raise UnfilledParameterError(_unfilled_message((name,)))
        return row.reference_step_ms

    # -- the PriorSource contract -------------------------------------------------

    def sample_patient(
        self, rng: np.random.Generator, patient_index: int
    ) -> PatientParams:
        if (
            isinstance(patient_index, (bool, np.bool_))
            or not isinstance(patient_index, numbers.Integral)
            or patient_index < 0
        ):
            raise ValueError(
                f"patient_index must be a non-negative integer, got {patient_index!r}"
            )
        patient_index = int(patient_index)
        self._require_filled(_PATIENT)
        # Keyword arguments are evaluated left to right: the draws follow contract order.
        return PatientParams(
            patient_id=f"p{patient_index:04d}",
            baseline_sbp_mmhg=self._draw("baseline_sbp_mmhg", rng),
            circadian_amplitude_mmhg=self._draw("circadian_amplitude_mmhg", rng),
            ar_noise_sd_mmhg=self._draw("ar_noise_sd_mmhg", rng),
            ar_noise_phi=self._draw("ar_noise_phi", rng),
            emax_mmhg=self._draw("emax_mmhg", rng),
            ec50=self._draw("ec50", rng),
            absorption_rate_per_h=self._draw("absorption_rate_per_h", rng),
            elimination_rate_per_h=self._draw("elimination_rate_per_h", rng),
            onset_delay_range_ms=self._onset_range(),
        )

    def adherence(self) -> AdherenceParams:
        self._require_filled(_ADHERENCE)
        return AdherenceParams(
            p_delay=self._scalar("p_delay"),
            p_omission=self._scalar("p_omission"),
            p_double_take=self._scalar("p_double_take"),
            mean_delay_ms=int(self._rows["mean_delay_ms"].value),
        )

    def device_errors(self) -> DeviceErrorModel:
        self._require_filled(_DEVICE)
        return DeviceErrorModel(
            cuff_error_sd_mmhg=self._scalar("cuff_error_sd_mmhg"),
            cuff_bias_mmhg=self._scalar("cuff_bias_mmhg"),
            dispenser_bounce_prob=self._scalar("dispenser_bounce_prob"),
            ble_dropout_rate_per_h=self._scalar("ble_dropout_rate_per_h"),
        )

    # -- internals ----------------------------------------------------------------

    def _require_filled(self, group: str) -> None:
        missing = sorted(n for n in _names_in(group) if not self._rows[n].filled)
        if missing:
            raise UnfilledParameterError(_unfilled_message(tuple(missing)))

    def _scalar(self, name: str) -> float:
        return float(self._rows[name].value)

    def _draw(self, name: str, rng: np.random.Generator) -> float:
        row = self._rows[name]
        if row.distribution is not None:
            return row.distribution.ppf(float(rng.random()))
        return float(row.value)

    def _onset_range(self) -> tuple[DurationMs, DurationMs]:
        value = self._rows["onset_delay_range_ms"].value
        return (int(value["lower_ms"]), int(value["upper_ms"]))


def _unfilled_message(names: Sequence[str]) -> str:
    return (
        f"parameter(s) {', '.join(names)} are awaiting_human_value: a human supplies the "
        "value and its source_ref in configs/priors/literature_hypertension.yaml"
    )


# ---------------------------------------------------------------------------
# Provenance table
# ---------------------------------------------------------------------------

_TABLE_COLUMNS: Final = (
    "parameter",
    "field",
    "unit",
    "value or distribution",
    "source_ref",
    "source_type",
    "verified_by",
    "status",
    "consumer task",
    "note",
)


def _cell(text: str | None) -> str:
    if text is None or not text.strip():
        return "-"
    return " ".join(text.split()).replace("|", "\\|")


def _value_cell(row: ParameterRow) -> str:
    if row.distribution is not None:
        return _cell(row.distribution.describe())
    if row.value is None:
        return "-"
    return _cell(json.dumps(row.value, sort_keys=True))


def _note_cell(row: ParameterRow) -> str:
    text = row.note.strip()
    if row.rationale and row.rationale.strip():
        text = f"{text} Rationale: {row.rationale.strip()}".strip()
    return _cell(text)


def _check_unique(files: Sequence[ParameterFile]) -> None:
    owner: dict[str, Path] = {}
    for parsed in files:
        for row in parsed.rows:
            if row.parameter in owner:
                raise PriorConfigError(
                    f"parameter {row.parameter!r} appears in {owner[row.parameter]} and {parsed.path}"
                )
            owner[row.parameter] = parsed.path


def render_provenance_table(
    files: Sequence[ParameterFile], *, root: Path | None = None
) -> str:
    """Render the generated region (summary lines and one table), ending with a newline."""
    _check_unique(files)
    rows = [row for parsed in files for row in parsed.rows]
    filled = sum(1 for r in rows if r.filled)
    unverified = sum(1 for r in rows if r.filled and r.verified_by is None)
    verified = sum(1 for r in rows if r.verified_by is not None)
    fixture = sum(1 for r in rows if r.source_type == SOURCE_FIXTURE)

    def shown(path: Path) -> str:
        if root is not None:
            try:
                return path.relative_to(root).as_posix()
            except ValueError:
                pass
        return path.as_posix()

    lines = [
        "- Source files: " + ", ".join(f"`{shown(f.path)}`" for f in files),
        f"- Parameter rows: {len(rows)}",
        f"- Rows by status: filled: {filled}, {STATUS_AWAITING}: {len(rows) - filled}",
        f"- Rows verified by a human (verified_by set): {verified} of {len(rows)}",
        f"- Filled rows still without verified_by (unfilled rows are not counted): {unverified}",
        f"- Fixture-only rows: {fixture}",
        "",
        "| " + " | ".join(_TABLE_COLUMNS) + " |",
        "|" + "---|" * len(_TABLE_COLUMNS),
    ]
    for row in rows:
        cells = (
            _cell(row.parameter),
            _cell(row.field),
            _cell(row.unit),
            _value_cell(row),
            _cell(row.source_ref),
            _cell(row.source_type),
            _cell(row.verified_by),
            _cell(row.status),
            _cell(row.consumer_task),
            _note_cell(row),
        )
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def collect_parameter_files(root: Path) -> list[ParameterFile]:
    """The prior file, then each sibling config that exists, validated and unique."""
    files = [load_prior_file(root / PRIORS_RELPATH)]
    for relpath in DESIGN_RELPATHS:
        candidate = root / relpath
        if candidate.is_file():
            files.append(load_design_file(candidate))
    _check_unique(files)
    return files


def _split_table(text: str) -> tuple[str, str, str]:
    lines = text.splitlines(keepends=True)
    begins = [i for i, line in enumerate(lines) if line.rstrip("\r\n") == BEGIN_MARKER]
    ends = [i for i, line in enumerate(lines) if line.rstrip("\r\n") == END_MARKER]
    if len(begins) != 1 or len(ends) != 1 or begins[0] >= ends[0]:
        raise PriorConfigError(
            f"the table needs exactly one {BEGIN_MARKER} line followed by one {END_MARKER} line"
        )
    begin, end = begins[0], ends[0]
    return (
        "".join(lines[: begin + 1]),
        "".join(lines[begin + 1 : end]),
        "".join(lines[end:]),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Exit code 0 ok, 1 table stale (--check-table), 2 error."""
    parser = argparse.ArgumentParser(
        prog="python -m ralmon.benchmark.priors",
        description="Render or check the parameter-provenance table.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--write-table", action="store_true", help="rewrite the generated region"
    )
    mode.add_argument(
        "--check-table", action="store_true", help="fail if the region is stale"
    )
    parser.add_argument(
        "--root", type=Path, default=None, help="repository root (default: cwd)"
    )
    args = parser.parse_args(argv)
    root: Path = args.root if args.root is not None else Path.cwd()
    table_path = root / TABLE_RELPATH
    try:
        files = collect_parameter_files(root)
        rendered = render_provenance_table(files, root=root)
        head, region, tail = _split_table(table_path.read_bytes().decode("utf-8"))
        if args.write_table:
            table_path.write_bytes((head + rendered + tail).encode("utf-8"))
            return 0
    except (PriorError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if region == rendered:
        return 0
    print(
        f"error: {TABLE_RELPATH} is stale; run `python -m ralmon.benchmark.priors --write-table`",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
