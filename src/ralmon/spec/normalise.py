# ruff: noqa: TRY004  (the contract: every invalid argument is a ValueError, never a TypeError)
"""Normalised robustness and the lexicographic order of alerts (02-interfaces.md#template).

``normalise`` is ``sigma_tilde = clip(sigma_raw / scale, -1.0, 1.0)`` with the conventions of
docs/formal/04-normalisation-ranking.md section 2: ``+-inf`` maps to ``+-1.0`` (a failed guard is minus
infinity), a NaN or a scale that is not positive and finite raises ``ValueError``, and a ``bool`` is not
a number. ``rank_alerts`` sorts alerts by ``K0 = (priority, sigma_norm, t_ms, instance_key)``, all
ascending, with priority 1 the highest (ADR-028, accepted); it is typed structurally, so this package
never imports ``ralmon.attribution``.
"""

from __future__ import annotations

import math
import numbers
from collections.abc import Sequence
from fractions import Fraction
from typing import Protocol, TypeVar

from ralmon.spec._text import converting, show

__all__ = ["normalise", "rank_alerts"]


# --- normalise ----------------------------------------------------------------------------


def _real(value: object, name: str) -> int | float:
    """``value`` as an exact ``int`` or a ``float``; a bool, a non-number or an unrepresentable
    number raises ``ValueError``."""
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a real number, a bool is not a number")
    if isinstance(value, numbers.Integral):
        return int(value)
    if isinstance(value, numbers.Real):
        try:
            return float(value)
        except (OverflowError, ValueError, TypeError) as exc:
            raise ValueError(
                f"{name} is not representable as a float: {show(value)}"
            ) from exc
    raise ValueError(f"{name} must be a real number, got {show(value)}")


def _clip_exact(sigma: float, scale: float) -> float:
    """The clipped quotient computed in exact arithmetic (a quotient of integers beyond the float
    range); only used when the plain division overflows."""
    quotient = Fraction(sigma) / Fraction(scale)
    if quotient >= 1:
        return 1.0
    if quotient <= -1:
        return -1.0
    return float(quotient)


@converting(ValueError)
def normalise(sigma_raw: float, scale: float) -> float:
    """sigma_tilde = clip(sigma_raw / scale, -1.0, 1.0). scale > 0.

    ``+inf`` and ``-inf`` map to ``+1.0`` and ``-1.0``. Raises ``ValueError`` if ``scale`` is not a
    positive finite number, if ``sigma_raw`` is NaN, or if either argument is not a real number (a
    ``bool`` is not). The result is always a Python ``float``.
    """
    divisor = _real(scale, "scale")
    if (isinstance(divisor, float) and not math.isfinite(divisor)) or not divisor > 0:
        raise ValueError(f"scale must be a positive finite number, got {show(scale)}")
    sigma = _real(sigma_raw, "sigma_raw")
    if isinstance(sigma, float):
        if math.isnan(sigma):
            raise ValueError("sigma_raw must not be NaN")
        if math.isinf(sigma):
            return 1.0 if sigma > 0 else -1.0
    try:
        ratio = sigma / divisor
    except OverflowError:
        return _clip_exact(sigma, divisor)
    return max(-1.0, min(1.0, ratio))


# --- rank_alerts --------------------------------------------------------------------------


class _HasInstanceKey(Protocol):
    @property
    def instance_key(self) -> str: ...


class _RankableFlat(Protocol):
    """The four fields K0 reads, flat: priority, sigma_norm, t_ms and instance_key."""

    @property
    def priority(self) -> int: ...

    @property
    def sigma_norm(self) -> float: ...

    @property
    def t_ms(self) -> int: ...

    @property
    def instance_key(self) -> str: ...


class _RankableAlert(Protocol):
    """The shape of ``Alert`` (#alert): the instance key is ``xi.instance_key``."""

    @property
    def priority(self) -> int: ...

    @property
    def sigma_norm(self) -> float: ...

    @property
    def t_ms(self) -> int: ...

    @property
    def xi(self) -> _HasInstanceKey: ...


A = TypeVar("A", bound="_RankableFlat | _RankableAlert")

_MISSING = object()


def _read(alert: object, name: str, where: str) -> object:
    try:
        return getattr(alert, name, _MISSING)
    except Exception as exc:  # a property that raises
        raise ValueError(f"{where}: reading {name} failed: {exc}") from exc


def _integer(value: object, name: str, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, numbers.Integral):
        raise ValueError(f"{where}: {name} must be an integer, got {show(value)}")
    return int(value)


def _sort_key(alert: object, index: int) -> tuple[int, int | float, int, str]:
    where = f"alerts[{index}]"
    priority = _integer(_read(alert, "priority", where), "priority", where)
    if priority < 1:
        raise ValueError(
            f"{where}: priority must be an integer >= 1, got {show(priority)}"
        )
    severity = _read(alert, "sigma_norm", where)
    if isinstance(severity, bool) or not isinstance(severity, numbers.Real):
        raise ValueError(
            f"{where}: sigma_norm must be a real number, got {show(severity)}"
        )
    try:
        sigma = severity if isinstance(severity, (int, float)) else float(severity)
    except (OverflowError, ValueError, TypeError) as exc:
        raise ValueError(
            f"{where}: sigma_norm is not representable as a float: {show(severity)}"
        ) from exc
    if isinstance(sigma, float) and math.isnan(sigma):
        raise ValueError(f"{where}: sigma_norm must not be NaN")
    t_ms = _integer(_read(alert, "t_ms", where), "t_ms", where)
    xi = _read(alert, "xi", where)
    holder = alert if xi is _MISSING or xi is None else xi
    key = _read(holder, "instance_key", where)
    if not isinstance(key, str):
        raise ValueError(f"{where}: instance_key must be a str, got {show(key)}")
    return (priority, sigma, t_ms, key)


@converting(ValueError)
def rank_alerts(alerts: Sequence[A]) -> list[A]:
    """Lexicographic order: template priority first (clinician-assigned), then sigma_tilde ascending within a priority.

    The order key is ``K0 = (priority, sigma_norm, t_ms, instance_key)``, every component ascending
    (ADR-028): priority 1 is the highest, the most negative ``sigma_norm`` comes first inside a
    priority, then the earlier ``t_ms``, then the instance key by code point, as a whole string.
    The sort is stable, so alerts with equal keys keep their input order. The input is not modified;
    a new list is returned.

    The instance key is ``alert.xi.instance_key`` (the shape of ``Alert``). A flat
    ``alert.instance_key`` is a fallback for an object that has no ``xi`` (or whose ``xi`` is
    ``None``), such as a test double. If both exist, ``xi.instance_key`` wins and the flat attribute is
    not consulted, even when ``xi`` has no valid key (that is an error, not a fall back).

    Raises ``ValueError`` for an input that is not a sequence, a priority that is not an integer >= 1,
    a NaN or non-number ``sigma_norm``, a non-integer ``t_ms`` or a non-str key, and for any other
    failure caused by a hostile element (the original exception type is kept in the message).
    """
    if isinstance(alerts, (str, bytes, bytearray)) or not isinstance(alerts, Sequence):
        raise ValueError(f"alerts must be a sequence of alerts, got {show(alerts)}")
    keyed = [(_sort_key(alert, index), alert) for index, alert in enumerate(alerts)]
    keyed.sort(key=lambda pair: pair[0])
    return [alert for _key, alert in keyed]
