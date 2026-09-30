"""Placeholder decorators (decision D1 of WS05): a placeholder never fakes behaviour.

This is the only module of ``ralmon`` that may raise the unfinished-work error. A
decorated name imports, carries ``__ralmon_stub_owner__`` and fails loudly when used.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import NoReturn, TypeVar

STUB_OWNER_ATTR = "__ralmon_stub_owner__"

_T = TypeVar("_T", bound=type)


def stub_class(owner: str) -> Callable[[_T], _T]:
    """Mark an empty class as a placeholder owned by task ``owner``; instantiation fails."""

    def decorate(cls: _T) -> _T:
        def _refuse(_cls: type, *args: object, **kwargs: object) -> NoReturn:
            raise NotImplementedError(
                f"{cls.__name__} is a placeholder owned by {owner}"
            )

        for attr, value in (
            ("__new__", staticmethod(_refuse)),
            (STUB_OWNER_ATTR, owner),
        ):
            setattr(cls, attr, value)
        return cls

    return decorate


def stub_function(
    owner: str,
) -> Callable[[Callable[..., NoReturn]], Callable[..., NoReturn]]:
    """Mark a function as a placeholder owned by task ``owner``; calling it fails."""

    def decorate(func: Callable[..., NoReturn]) -> Callable[..., NoReturn]:
        def _refuse(*args: object, **kwargs: object) -> NoReturn:
            raise NotImplementedError(
                f"{func.__name__} is a placeholder owned by {owner}"
            )

        _refuse.__name__ = func.__name__
        _refuse.__qualname__ = func.__qualname__
        _refuse.__doc__ = func.__doc__
        setattr(_refuse, STUB_OWNER_ATTR, owner)
        return _refuse

    return decorate
