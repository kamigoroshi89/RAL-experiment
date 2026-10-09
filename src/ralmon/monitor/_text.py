"""Helpers shared by the modules of ``ralmon.monitor``: bounded text for error messages, the validated
conversion of externally supplied numbers, and the boundary that turns a foreign exception into the
named error of a call.

Every externally supplied object that enters an error message goes through ``show`` or ``type_name``,
so a megabyte of hostile text cannot become a megabyte of log line and an object whose ``repr``
raises cannot break the message. ``as_int`` and ``as_number`` are the only places where a time, a
sequence number or a value is read from an argument.
"""

from __future__ import annotations

import functools
import math
import numbers
import operator
from collections.abc import Callable
from typing import ParamSpec, TypeVar

# algorithmic: longest ``repr`` quoted in an error message, so that a hostile 1 MiB value cannot flood a
# log line
_MAX_SHOWN: int = 60
# algorithmic: longest text of a foreign exception quoted when it is converted to a named error
MAX_REASON: int = 300
# algorithmic: the largest time in milliseconds the monitor accepts (2**53: exact in a float, about 285
# thousand years), so that no arithmetic on a time can overflow a float or exhaust memory
MAX_TIME_MS: int = 2**53
# algorithmic: the largest magnitude of a sample value (about 1e15), so that sums and differences of
# values stay exact enough and finite
MAX_ABS_VALUE: float = 1e15
# algorithmic: the range of a sequence number (signed 64 bit, as in the plan serialisation)
MAX_SEQ: int = 2**63 - 1

_P = ParamSpec("_P")
_R = TypeVar("_R")


def clip(text: str, limit: int = _MAX_SHOWN) -> str:
    """``text`` cut to ``limit`` characters, with an ellipsis if it was cut."""
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def type_name(value: object) -> str:
    """The name of the type of ``value``, cut; never raises."""
    try:
        return clip(type(value).__name__)
    except Exception:  # noqa: BLE001 - last resort
        return "object"


def show(value: object) -> str:
    """A short ``repr`` of ``value`` that never raises."""
    try:
        return clip(repr(value))
    except Exception:  # noqa: BLE001 - a repr that raises must not hide the real error
        return f"<{type_name(value)}>"


def describe(exc: BaseException) -> str:
    """``TypeName: message`` of an exception, with the message cut; never raises."""
    try:
        message = clip(str(exc), MAX_REASON)
    except Exception:  # noqa: BLE001 - an exception whose __str__ raises
        message = "<unprintable>"
    return f"{type_name(exc)}: {message}"


def converting(
    error: type[Exception], *passthrough: type[Exception]
) -> Callable[[Callable[_P, _R]], Callable[_P, _R]]:
    """Decorator for a public entry point: ``error`` and ``passthrough`` are the only exceptions that escape.

    A foreign exception (a hostile argument whose ``__repr__``, ``__eq__``, ``__hash__``, ``__iter__`` or
    attributes raise, for instance) is re-raised as ``error`` with the original exception type and a cut
    message in the text, and chained as the cause.
    """
    allowed = (error, *passthrough)

    def decorate(func: Callable[_P, _R]) -> Callable[_P, _R]:
        @functools.wraps(func)
        def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            try:
                return func(*args, **kwargs)
            except allowed:
                raise
            except Exception as exc:
                raise error(
                    f"{func.__qualname__}: unusable argument ({describe(exc)})"
                ) from exc

        return wrapper

    return decorate


def as_int(
    value: object,
    what: str,
    error: type[Exception],
    *,
    low: int | None = 0,
    high: int | None = MAX_TIME_MS,
) -> int:
    """``value`` as a plain ``int`` in ``[low, high]``; a ``bool``, a float or a text raises ``error``."""
    if isinstance(value, bool) or not isinstance(value, numbers.Integral):
        raise error(f"{what} must be an integer, got {show(value)}")
    number = operator.index(value)
    if (low is not None and number < low) or (high is not None and number > high):
        raise error(f"{what} must be in [{low}, {high}], got {show(number)}")
    return number


def as_number(
    value: object, what: str, error: type[Exception], *, bound: float = MAX_ABS_VALUE
) -> float:
    """``value`` as a finite ``float`` of magnitude at most ``bound``; a ``bool`` or a text raises ``error``."""
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise error(f"{what} must be a real number, got {show(value)}")
    try:
        number = float(value)
    except (OverflowError, ValueError, TypeError) as exc:
        raise error(f"{what} is not representable as a float: {show(value)}") from exc
    if not math.isfinite(number) or abs(number) > bound:
        raise error(
            f"{what} must be finite and at most {bound:g} in magnitude, got {show(value)}"
        )
    return number
