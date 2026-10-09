"""Reading the registry and checking per-patient values (shared by the monitor and the evaluator).

The registry is the single source of the numbers (ADR-020): this module reads them by name, never
supplies a default for an unset or unknown name (a missing value is a ``MonitorConfigError`` that names
it), and applies the minimal documented rule of ADR-047 (g), proposed: a value in a care plan that
differs from the registry value must lie in an approved range (``registry.overrides()``). The window
parameters must be non-negative integer multiples of ``T_s`` (docs/formal/01 section 3.6, check F1).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

from ralmon.monitor._text import as_number, describe, show
from ralmon.monitor.config import MonitorConfigError, PlanFeasibilityError
from ralmon.spec import RegistryError, Template, as_duration_ms

__all__ = [
    "WINDOW_PARAMS",
    "check_alignment",
    "check_registry",
    "layer_values",
    "optional_value",
    "read_bounds",
    "read_latency",
    "read_overrides",
    "read_value",
]

WINDOW_PARAMS: Final = (
    "sched_window",
    "hold_lookback",
    "int_window",
    "delta1",
    "delta2",
)


def check_registry(registry: object) -> None:
    for name in ("get", "bounds", "version"):
        if not callable(getattr(registry, name, None)):
            raise MonitorConfigError(
                f"registry must have a {name} method, got {show(registry)}"
            )


def read_value(registry: Any, name: str) -> float:
    """The value of a registry entry; an unset or unknown name is an error that names it."""
    try:
        entry = registry.get(name)
    except RegistryError as exc:
        raise MonitorConfigError(
            f"registry: parameter {name!r} cannot be read ({describe(exc)}); the monitor never "
            "substitutes a value for an unset or unknown name"
        ) from exc
    return as_number(
        getattr(entry, "value", None), f"registry value of {name}", MonitorConfigError
    )


def optional_value(registry: Any, name: str, *, low: float | None) -> float | None:
    """A registry value that switches a feature off when it is unset or absent (the caller says so)."""
    try:
        entry = registry.get(name)
    except RegistryError:
        return None
    value = as_number(
        getattr(entry, "value", None), f"registry value of {name}", MonitorConfigError
    )
    if low is not None and value < low:
        raise MonitorConfigError(
            f"registry: {name} must be at least {low}, got {value}"
        )
    return value


def read_latency(registry: Any, template: Template) -> int:
    """``max_latency_<id>`` in ms (a derived name: it needs the registry loaded with ``step_ms``)."""
    name = template.max_verdict_latency_param
    try:
        return as_duration_ms(registry.get(name))
    except RegistryError as exc:
        raise MonitorConfigError(
            f"registry: {name!r} cannot be read ({describe(exc)}); a derived name needs the registry "
            "loaded with step_ms"
        ) from exc


def read_bounds(registry: Any) -> tuple[float, float]:
    """The physiological bounds of ``bp`` (analisi §4.7 step 2): ``lower < upper``, both finite."""
    try:
        bounds = registry.bounds("bp")
    except RegistryError as exc:
        raise MonitorConfigError(
            f"registry: the physiological bounds of bp are unusable ({describe(exc)})"
        ) from exc
    lower = as_number(
        getattr(bounds, "lower", None), "bounds lower", MonitorConfigError
    )
    upper = as_number(
        getattr(bounds, "upper", None), "bounds upper", MonitorConfigError
    )
    if not lower < upper:
        raise MonitorConfigError(
            f"registry: the bounds of bp must satisfy lower < upper, got [{lower}, {upper}]"
        )
    return lower, upper


def read_overrides(registry: Any) -> list[tuple[str, float, float]]:
    """The approved ranges ``(name, min, max)`` of per-patient values; none if the registry has none."""
    getter = getattr(registry, "overrides", None)
    if not callable(getter):
        return []
    out = []
    for o in getter():
        out.append(
            (
                str(o.name),
                as_number(o.min, "override min", MonitorConfigError),
                as_number(o.max, "override max", MonitorConfigError),
            )
        )
    return out


def layer_values(
    template: Template,
    registry_values: Mapping[str, float],
    overrides: Sequence[tuple[str, float, float]],
    values: Mapping[str, float],
    where: str,
) -> dict[str, float]:
    """Check per-patient ``values`` of a template against the registry (ADR-047 (g), proposed)."""
    out: dict[str, float] = {}
    for name, value in values.items():
        if name not in template.params:
            raise PlanFeasibilityError(
                f"{where}: {name!r} is not a parameter of template {template.id.value} "
                f"{list(template.params)}"
            )
        reference = registry_values[name]
        if value != reference and not any(
            lo <= value <= hi for n, lo, hi in overrides if n == name
        ):
            raise PlanFeasibilityError(
                f"{where}: {name} = {value} differs from the registry value {reference} and lies in "
                "no approved range (registry overrides)"
            )
        out[name] = value
    return out


def check_alignment(params: Mapping[str, float], step_ms: int, where: str) -> None:
    """The window parameters are non-negative integer multiples of ``T_s`` (01 section 3.6, F1)."""
    for name in WINDOW_PARAMS:
        if name not in params:
            continue
        value = params[name]
        if not (
            value >= 0.0 and float(value).is_integer() and int(value) % step_ms == 0
        ):
            raise PlanFeasibilityError(
                f"{where}: window parameter {name} = {value} is not a non-negative multiple "
                f"of step_ms {step_ms}"
            )
    if (
        "delta1" in params
        and "delta2" in params
        and params["delta1"] > params["delta2"]
    ):
        raise PlanFeasibilityError(
            f"{where}: delta1 = {params['delta1']} must not exceed delta2 = {params['delta2']}"
        )
