"""The bounded-text helpers and the named-error boundary of ``ralmon.spec`` (private module ``_text``)."""

from __future__ import annotations

from typing import Any

import pytest

from ralmon.spec import _text


def _raising(*args: object, **kwargs: object) -> Any:
    raise RuntimeError("hostile object")


class HostileRepr:
    __repr__ = _raising
    __str__ = _raising


class HostileException(Exception):
    __str__ = _raising


def test_show_is_the_repr_cut_to_a_short_text() -> None:
    assert _text.show("abc") == "'abc'"
    assert _text.show(None) == "None"
    long = _text.show("x" * 1_000_000)
    assert long.startswith("'xxx") and long.endswith("...")
    assert len(long) <= 70
    assert (
        _text.show(10**5000) == "<int>"
    )  # the repr of a huge integer raises; show does not


def test_show_never_raises() -> None:
    assert _text.show(HostileRepr()) == "<HostileRepr>"
    assert _text.show(_text).startswith("<module")


def test_show_path_keeps_a_real_path_whole_and_cuts_a_hostile_one() -> None:
    path = "/tmp/" + "d" * 200 + "/registry.yaml"
    assert _text.show_path(path) == path
    assert len(_text.show_path("p" * 1_000_000)) <= 410
    assert _text.show_path(HostileRepr()) == "<HostileRepr>"


def test_show_names_lists_a_bounded_number_of_cut_names() -> None:
    assert _text.show_names(["a", "b"]) == "['a', 'b']"
    assert _text.show_names([]) == "[]"
    many = _text.show_names([f"name_{i}" for i in range(1000)])
    assert "(+960 more)" in many and "'name_0'" in many and "'name_39'" in many
    assert "'name_40'" not in many
    assert len(_text.show_names(["n" * 1_000_000] * 3)) < 300

    def unreadable() -> Any:
        yield "first"
        raise RuntimeError("hostile iterator")

    assert "<unreadable>" in _text.show_names(unreadable())


def test_describe_names_the_type_and_cuts_the_message() -> None:
    assert _text.describe(ValueError("bad")) == "ValueError: bad"
    text = _text.describe(RuntimeError("m" * 1_000_000))
    assert text.startswith("RuntimeError: mmm") and len(text) < 340
    assert _text.describe(HostileException("x")) == "HostileException: <unprintable>"


def test_type_name_is_cut_and_never_raises() -> None:
    assert _text.type_name(3) == "int"
    assert len(_text.type_name(type("t" * 100_000, (), {})())) <= 70


class Named(Exception):
    pass


class NamedChild(Named):
    pass


def test_converting_turns_a_foreign_exception_into_the_named_error() -> None:
    @_text.converting(Named)
    def fails(x: int) -> int:
        """Docstring kept."""
        raise RuntimeError("inner message")

    with pytest.raises(
        Named, match=r"fails: unusable argument \(RuntimeError: inner message\)"
    ) as info:
        fails(1)
    assert isinstance(info.value.__cause__, RuntimeError)
    assert fails.__name__ == "fails" and fails.__doc__ == "Docstring kept."


def test_converting_lets_the_named_error_and_its_subclasses_through_unchanged() -> None:
    @_text.converting(Named)
    def raises_child() -> None:
        raise NamedChild("own message")

    with pytest.raises(NamedChild, match="^own message$") as info:
        raises_child()
    assert info.value.__cause__ is None

    @_text.converting(Named)
    def returns() -> int:
        return 7

    assert returns() == 7


def test_converting_does_not_swallow_base_exceptions() -> None:
    @_text.converting(Named)
    def interrupted() -> None:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        interrupted()
