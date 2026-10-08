"""Helpers shared by the modules of ``ralmon.spec``: bounded text for error messages, and the boundary
that turns a foreign exception into the named error of a module.

Every externally supplied string that enters an error message goes through ``show``, ``show_path`` or
``show_names``, so a megabyte of hostile text cannot become a megabyte of log line, and a hostile
object whose ``repr`` raises cannot break the message.
"""

from __future__ import annotations

import functools
from collections.abc import Callable, Iterable
from typing import ParamSpec, TypeVar

# algorithmic: longest ``repr`` quoted in an error message, so that a hostile 1 MiB value cannot
# flood a log line
_MAX_SHOWN: int = 60
# algorithmic: longest path quoted in full (a path of the operating system is at most 4096 characters)
_MAX_PATH_SHOWN: int = 400
# algorithmic: longest text of a foreign exception quoted when it is converted to a named error
MAX_REASON: int = 300
# algorithmic: most names listed in one message
_MAX_LISTED: int = 40

_P = ParamSpec("_P")
_R = TypeVar("_R")


def clip(text: str, limit: int = _MAX_SHOWN) -> str:
    """``text`` cut to ``limit`` characters, with an ellipsis if it was cut."""
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def show(value: object) -> str:
    """A short ``repr`` of ``value`` that never raises."""
    try:
        text = repr(value)
        return clip(text)
    except Exception:  # noqa: BLE001 - a repr that raises must not hide the real error
        return f"<{type_name(value)}>"


def show_path(path: object) -> str:
    """A path as text, in full up to the length of a path of the operating system."""
    try:
        return clip(str(path), _MAX_PATH_SHOWN)
    except Exception:  # noqa: BLE001 - a hostile path object must not hide the real error
        return f"<{type_name(path)}>"


def show_names(names: Iterable[object]) -> str:
    """A bracketed list of at most ``_MAX_LISTED`` names, each cut, with the count of the rest."""
    listed: list[str] = []
    extra = 0
    try:
        for name in names:
            if len(listed) < _MAX_LISTED:
                listed.append(show(name))
            else:
                extra += 1
    except Exception:  # noqa: BLE001 - a hostile iterable must not hide the real error
        listed.append("<unreadable>")
    tail = f", ... (+{extra} more)" if extra else ""
    return "[" + ", ".join(listed) + tail + "]"


def type_name(value: object) -> str:
    """The name of the type of ``value``, cut; never raises."""
    try:
        return clip(type(value).__name__)
    except Exception:  # noqa: BLE001 - last resort
        return "object"


def describe(exc: BaseException) -> str:
    """``TypeName: message`` of an exception, with the message cut; never raises."""
    try:
        message = clip(str(exc), MAX_REASON)
    except Exception:  # noqa: BLE001 - an exception whose __str__ raises
        message = "<unprintable>"
    return f"{type_name(exc)}: {message}"


def converting(
    error: type[Exception],
) -> Callable[[Callable[_P, _R]], Callable[_P, _R]]:
    """Decorator for a public entry point: ``error`` is the only exception that escapes.

    A foreign exception (a hostile argument whose ``__repr__``, ``__eq__``, ``__hash__``, ``__iter__``
    or attributes raise, for instance) is re-raised as ``error`` with the original exception type and
    a cut message in the text, and chained as the cause.
    """

    def decorate(func: Callable[_P, _R]) -> Callable[_P, _R]:
        @functools.wraps(func)
        def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            try:
                return func(*args, **kwargs)
            except error:
                raise
            except Exception as exc:
                raise error(
                    f"{func.__qualname__}: unusable argument ({describe(exc)})"
                ) from exc

        return wrapper

    return decorate
