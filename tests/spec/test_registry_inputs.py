"""Hostile and malformed inputs of ``load_registry``: only ``RegistryError`` comes out.

Table-driven: bad paths, bad bytes, YAML constructs that must be refused (duplicate keys, anchors and
aliases, python tags, multiple documents, deep nesting), bad shapes and bad values of every field.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from ralmon.spec import _yaml as yaml_io
from ralmon.spec import load_registry
from ralmon.spec import registry as registry_module
from ralmon.spec.registry import RegistryError

from .helpers import F0_PATH, dump_yaml, entry_of, f0_doc, write_yaml


def load_text(tmp_path: Path, text: str | bytes, name: str = "registry.yaml") -> Any:
    path = tmp_path / name
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text, encoding="utf-8")
    return load_registry(path, allow_fixture_only=True)


F0_TEXT = F0_PATH.read_text(encoding="utf-8")


# --- paths -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [5, 5.5, b"registry.yaml", ["a"], {"a": 1}, object(), True, False],
    ids=["int", "float", "bytes", "list", "dict", "object", "True", "False"],
)
def test_a_path_of_the_wrong_type_raises_registry_error(bad: Any) -> None:
    with pytest.raises(RegistryError):
        load_registry(bad)


def test_an_os_pathlike_with_a_bytes_path_raises_registry_error() -> None:
    class BytesPath:
        def __fspath__(self) -> bytes:
            return b"/tmp/x"

    class BrokenPath:
        def __fspath__(self) -> str:
            raise OSError("broken")

    with pytest.raises(RegistryError):
        load_registry(BytesPath())  # type: ignore[arg-type]
    with pytest.raises(RegistryError):
        load_registry(BrokenPath())  # type: ignore[arg-type]


def test_a_missing_file_names_its_path(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.yaml"
    with pytest.raises(RegistryError, match="does-not-exist.yaml"):
        load_registry(missing)
    with pytest.raises(RegistryError, match="does-not-exist.yaml"):
        load_registry(str(missing))


def test_a_directory_is_not_a_registry(tmp_path: Path) -> None:
    with pytest.raises(RegistryError):
        load_registry(tmp_path)


def test_an_embedded_nul_or_surrogate_in_the_path_raises_registry_error(
    tmp_path: Path,
) -> None:
    with pytest.raises(RegistryError):
        load_registry(str(tmp_path / "a\x00b.yaml"))
    with pytest.raises(RegistryError):
        load_registry(str(tmp_path / "a\udc80b.yaml"))
    with pytest.raises(RegistryError):
        load_registry("x" * 5000)  # ENAMETOOLONG


@pytest.mark.skipif(
    not hasattr(os, "geteuid") or os.geteuid() == 0,
    reason="file permissions do not stop root",
)
def test_an_unreadable_file_raises_registry_error(tmp_path: Path) -> None:
    path = tmp_path / "locked.yaml"
    path.write_text(F0_TEXT, encoding="utf-8")
    path.chmod(0)
    try:
        with pytest.raises(RegistryError, match="locked.yaml"):
            load_registry(path, allow_fixture_only=True)
    finally:
        path.chmod(0o600)


def test_a_file_that_is_not_utf8_raises_registry_error(tmp_path: Path) -> None:
    for payload in (
        b"\xff\xfe\x00\x00",
        b"registry_version: \xc3\x28\n",
        F0_TEXT.encode("utf-16"),
    ):
        with pytest.raises(RegistryError):
            load_text(tmp_path, payload)


def test_a_file_over_the_size_limit_is_refused_without_parsing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    limit = yaml_io.MAX_FILE_BYTES
    assert limit == 1_048_576  # 1 MiB: the real files are a few kilobytes
    big = tmp_path / "big.yaml"
    big.write_text(F0_TEXT + "#" * limit, encoding="utf-8")
    with pytest.raises(RegistryError, match="big.yaml") as info:
        load_registry(big, allow_fixture_only=True)
    assert str(limit) in str(info.value)
    exact = tmp_path / "exact.yaml"
    exact.write_text(
        F0_TEXT + "#" * (limit - len(F0_TEXT.encode("utf-8")) - 1) + "\n",
        encoding="utf-8",
    )
    assert exact.stat().st_size == limit
    assert load_registry(exact, allow_fixture_only=True).version() == "0.0.0"
    monkeypatch.setattr(yaml_io, "MAX_FILE_BYTES", 100)
    with pytest.raises(RegistryError):
        load_registry(F0_PATH, allow_fixture_only=True)


# --- YAML constructs ---------------------------------------------------------------------

TOP_LEVEL_KEYS = (
    "registry_version",
    "pathology",
    "review_status",
    "window_parameters",
    "entries",
    "derived",
    "unset",
)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   \n\n",
        "# only a comment\n",
        "---\n",
        "null\n",
        "42\n",
        "just a string\n",
        "- a\n- b\n",
        "[]\n",
        "{}\n",
        "key: [unclosed\n",
        "a: b: c\n",
        "\tregistry_version: '1.0.0'\n",
        "registry_version: '1.0.0'\n---\nregistry_version: '2.0.0'\n",  # two documents
        "registry_version: 1\nregistry_version: 2\n",  # duplicate top-level key
        "a: &x 1\nb: *x\n",  # alias
        "a: &x 1\n",  # anchor
        "base: &b {name: x}\nd:\n  <<: *b\n",  # merge key through an alias
        "a: !!python/object/apply:os.system ['echo hi']\n",
        "a: !!python/name:os.system\n",
        "a: !!python/object:collections.OrderedDict {}\n",
        "a: !!binary aGVsbG8=\n",
        "a: !!set {x, y}\n",
        "? [a, b]\n: 1\n",  # unhashable key
        "a: 2001-13-45\n",  # impossible date
        "a: \x00\n",
        "a: \x07\n",
        "a: " + "[" * 100_000 + "\n",  # nesting deeper than the parser stack
        "a: " + "{a: " * 50_000 + "1" + "}" * 50_000 + "\n",
        "a: !unknown tag\n",
        "%YAML 9.9\n---\na: 1\n",
    ],
    ids=lambda t: repr(t[:30]),
)
def test_hostile_yaml_raises_registry_error(tmp_path: Path, text: str) -> None:
    with pytest.raises(RegistryError):
        load_text(tmp_path, text)


def test_the_billion_laughs_bomb_is_refused_before_it_is_expanded(
    tmp_path: Path,
) -> None:
    lines = ['a: &a ["lol","lol","lol","lol","lol","lol","lol","lol","lol"]']
    previous = "a"
    for level in "bcdefghi":
        lines.append(
            f"{level}: &{level} [" + ",".join(f"*{previous}" for _ in range(9)) + "]"
        )
        previous = level
    with pytest.raises(RegistryError, match=r"anchor|alias"):
        load_text(tmp_path, "\n".join(lines) + "\n")


def test_duplicate_keys_are_refused_at_every_level(tmp_path: Path) -> None:
    text = F0_TEXT.replace(
        "    unit: mmHg\n    rationale",
        "    unit: mmHg\n    unit: ms\n    rationale",
        1,
    )
    assert text != F0_TEXT
    with pytest.raises(RegistryError, match="duplicate"):
        load_text(tmp_path, text)
    flow = F0_TEXT.replace(
        "{name: max_latency_range, unit: ms,",
        "{name: max_latency_range, name: other, unit: ms,",
        1,
    )
    assert flow != F0_TEXT
    with pytest.raises(RegistryError, match="duplicate"):
        load_text(tmp_path, flow)


def test_a_bom_and_crlf_line_endings_are_accepted(tmp_path: Path) -> None:
    registry = load_text(tmp_path, "\ufeff" + F0_TEXT.replace("\n", "\r\n"))
    assert registry.version() == "0.0.0"


def test_yaml_error_text_never_leaks_as_a_raw_exception(tmp_path: Path) -> None:
    import yaml

    with pytest.raises(RegistryError) as info:
        load_text(tmp_path, "a: [")
    assert not isinstance(info.value, yaml.YAMLError)
    assert str(info.value)


# --- shapes ------------------------------------------------------------------------------


@pytest.mark.parametrize("key", TOP_LEVEL_KEYS)
def test_every_required_top_level_key_is_required(tmp_path: Path, key: str) -> None:
    doc = f0_doc()
    del doc[key]
    with pytest.raises(RegistryError, match=key):
        load_registry(write_yaml(tmp_path, doc), allow_fixture_only=True)


def test_unknown_top_level_and_entry_keys_are_refused(tmp_path: Path) -> None:
    doc = f0_doc()
    doc["surprise"] = 1
    with pytest.raises(RegistryError, match="surprise"):
        load_registry(write_yaml(tmp_path, doc), allow_fixture_only=True)
    doc = f0_doc()
    entry_of(doc, "bp_band_low")["fixture_only"] = True
    with pytest.raises(RegistryError, match="fixture_only"):
        load_registry(write_yaml(tmp_path, doc), allow_fixture_only=True)
    doc = f0_doc()
    doc["derived"][0]["extra"] = 1
    with pytest.raises(RegistryError, match="extra"):
        load_registry(write_yaml(tmp_path, doc), allow_fixture_only=True)
    doc = f0_doc()
    doc["unset"] = [
        {
            "parameter": "scale_hold",
            "unit": "mmHg",
            "required_by": [],
            "note": "n",
            "x": 1,
        }
    ]
    with pytest.raises(RegistryError, match="unset"):
        load_registry(write_yaml(tmp_path, doc), allow_fixture_only=True)


@pytest.mark.parametrize(
    "key", ["window_parameters", "entries", "derived", "unset", "overrides"]
)
@pytest.mark.parametrize("bad", [None, "text", 5, {"a": 1}, True])
def test_list_valued_keys_must_be_lists(tmp_path: Path, key: str, bad: Any) -> None:
    doc = f0_doc()
    doc[key] = bad
    with pytest.raises(RegistryError, match=key):
        load_registry(write_yaml(tmp_path, doc), allow_fixture_only=True)


@pytest.mark.parametrize("key", ["entries", "derived", "unset", "overrides"])
@pytest.mark.parametrize("bad", [None, "text", 5, ["a"], True])
def test_list_elements_must_be_mappings(tmp_path: Path, key: str, bad: Any) -> None:
    doc = f0_doc()
    doc[key] = [bad]
    with pytest.raises(RegistryError, match=key):
        load_registry(write_yaml(tmp_path, doc), allow_fixture_only=True)


@pytest.mark.parametrize(
    "bad",
    [
        None,
        "",
        5,
        ["a"],
        "Upper",
        "has space",
        "1abc",
        "a-b",
        "ünï",
        "a" * 10_000 + "!",
    ],
)
def test_pathology_and_window_names_must_be_valid(tmp_path: Path, bad: Any) -> None:
    doc = f0_doc()
    doc["window_parameters"] = [bad]
    with pytest.raises(RegistryError, match="window_parameters"):
        load_registry(write_yaml(tmp_path, doc), allow_fixture_only=True)


@pytest.mark.parametrize("bad", [None, "", "  ", 5, ["a"], {"a": 1}])
def test_pathology_must_be_a_non_empty_string(tmp_path: Path, bad: Any) -> None:
    doc = f0_doc()
    doc["pathology"] = bad
    with pytest.raises(RegistryError, match="pathology"):
        load_registry(write_yaml(tmp_path, doc), allow_fixture_only=True)


@pytest.mark.parametrize(
    "bad", [None, "", "Unreviewed", "reviewed ", "done", 5, ["reviewed"], True]
)
def test_review_status_must_be_one_of_the_three_values(
    tmp_path: Path, bad: Any
) -> None:
    doc = f0_doc()
    doc["review_status"] = bad
    with pytest.raises(RegistryError, match="review_status"):
        load_registry(write_yaml(tmp_path, doc), allow_fixture_only=True)


def test_window_parameters_must_be_unique(tmp_path: Path) -> None:
    doc = f0_doc()
    doc["window_parameters"].append("delta1")
    with pytest.raises(RegistryError, match="delta1"):
        load_registry(write_yaml(tmp_path, doc), allow_fixture_only=True)


# --- field values ------------------------------------------------------------------------

BAD_NAMES = [
    None,
    "",
    5,
    ["a"],
    "Upper",
    "has space",
    "1abc",
    "a-b",
    "bp\n",
    "bpé",
    "_x",
    "x" * 3 + "\n",
]
BAD_VALUES: list[Any] = [
    None,
    True,
    False,
    "110",
    "",
    [110],
    {"v": 110},
    float("nan"),
    float("inf"),
    float("-inf"),
    10**400,
    -(10**400),
]
BAD_UNITS = [None, "", 1, "kg", "MMHG", "mmhg", "mmHg ", "ms\n", ["ms"], True]
BAD_REVIEWERS = [5, "", "   ", ["a"], {"a": 1}, True]


@pytest.mark.parametrize("bad", BAD_NAMES, ids=lambda v: repr(v)[:20])
def test_entry_names_must_match_the_pattern_exactly(tmp_path: Path, bad: Any) -> None:
    doc = f0_doc()
    entry_of(doc, "bp_band_low")["name"] = bad
    with pytest.raises(RegistryError):
        load_registry(write_yaml(tmp_path, doc), allow_fixture_only=True)


@pytest.mark.parametrize("bad", BAD_VALUES, ids=lambda v: repr(v)[:20])
def test_entry_values_must_be_finite_numbers(tmp_path: Path, bad: Any) -> None:
    doc = f0_doc()
    entry_of(doc, "bp_band_low")["value"] = bad
    with pytest.raises(RegistryError, match="bp_band_low"):
        load_registry(write_yaml(tmp_path, doc), allow_fixture_only=True)


def test_an_integer_value_is_accepted_and_stored_as_a_float(tmp_path: Path) -> None:
    doc = f0_doc()
    entry_of(doc, "bp_band_low")["value"] = 110
    value = (
        load_registry(write_yaml(tmp_path, doc), allow_fixture_only=True)
        .get("bp_band_low")
        .value
    )
    assert value == 110.0 and type(value) is float


@pytest.mark.parametrize("bad", BAD_UNITS, ids=lambda v: repr(v)[:20])
def test_entry_units_must_be_one_of_the_four(tmp_path: Path, bad: Any) -> None:
    doc = f0_doc()
    entry_of(doc, "bp_band_low")["unit"] = bad
    with pytest.raises(RegistryError, match="bp_band_low"):
        load_registry(write_yaml(tmp_path, doc), allow_fixture_only=True)


def test_the_unit_one_must_be_the_string_one(tmp_path: Path) -> None:
    """``unit: 1`` is an integer in YAML; the schema wants the string ``"1"``."""
    text = F0_TEXT.replace('unit: "1"', "unit: 1")
    assert text != F0_TEXT
    with pytest.raises(RegistryError, match="unit"):
        load_text(tmp_path, text)


@pytest.mark.parametrize("bad", BAD_REVIEWERS, ids=lambda v: repr(v)[:20])
def test_reviewed_by_must_be_a_non_empty_string_or_null(
    tmp_path: Path, bad: Any
) -> None:
    doc = f0_doc()
    entry_of(doc, "bp_band_low")["reviewed_by"] = bad
    with pytest.raises(RegistryError, match="bp_band_low"):
        load_registry(write_yaml(tmp_path, doc), allow_fixture_only=True)


@pytest.mark.parametrize(
    "unset_element",
    [
        {
            "parameter": "scale_hold",
            "unit": "mmHg",
            "required_by": ["nope"],
            "note": "n",
        },
        {"parameter": "scale_hold", "unit": "mmHg", "required_by": "hold", "note": "n"},
        {
            "parameter": "scale_hold",
            "unit": "mmHg",
            "required_by": ["hold", "hold"],
            "note": "n",
        },
        {"parameter": "scale_hold", "unit": "kg", "required_by": [], "note": "n"},
        {"parameter": "scale_hold", "unit": "mmHg", "required_by": [], "note": ""},
        {"parameter": "scale_hold", "unit": "mmHg", "required_by": [], "note": None},
        {"parameter": "Scale", "unit": "mmHg", "required_by": [], "note": "n"},
        {"parameter": None, "unit": "mmHg", "required_by": [], "note": "n"},
        {"unit": "mmHg", "required_by": [], "note": "n"},
        {"parameter": "scale_hold", "unit": "mmHg", "required_by": [5], "note": "n"},
    ],
    ids=lambda v: repr(v)[-40:],
)
def test_unset_elements_are_validated(
    tmp_path: Path, unset_element: dict[str, Any]
) -> None:
    doc = f0_doc()
    doc["entries"] = [e for e in doc["entries"] if e["name"] != "scale_hold"]
    doc["unset"] = [unset_element]
    with pytest.raises(RegistryError, match="unset"):
        load_registry(write_yaml(tmp_path, doc), allow_fixture_only=True)


@pytest.mark.parametrize(
    "change",
    [
        {"template": "nope"},
        {"template": None},
        {"unit": "kg"},
        {"name": "Max"},
        {"name": None},
        {"formula": "delta2 + unknown_name"},
    ],
    ids=lambda v: repr(v)[:40],
)
def test_derived_elements_are_validated(tmp_path: Path, change: dict[str, Any]) -> None:
    doc = f0_doc()
    doc["derived"][4].update(change)
    with pytest.raises(RegistryError, match="derived"):
        load_registry(
            write_yaml(tmp_path, doc), step_ms=60_000, allow_fixture_only=True
        )


def test_a_huge_but_valid_registry_loads_in_bounded_time(tmp_path: Path) -> None:
    doc = f0_doc()
    for index in range(2000):
        doc["entries"].append(
            {
                "name": f"extra_{index}",
                "value": float(index),
                "unit": "dose",
                "rationale": "FIXTURE-ONLY row; illustrative, unverified",
                "source_ref": "test",
                "reviewed_by": None,
            }
        )
    registry = load_registry(write_yaml(tmp_path, doc), allow_fixture_only=True)
    assert registry.get("extra_1999").value == 1999.0
    assert len(dump_yaml(doc)) < yaml_io.MAX_FILE_BYTES


def test_the_loader_module_has_the_documented_constants() -> None:
    assert registry_module.FIXTURE_ONLY_MARKER == "FIXTURE-ONLY"
    assert yaml_io.MAX_FILE_BYTES == 1_048_576


def test_the_file_is_read_with_a_bounded_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """The size limit is enforced while reading, not after: a huge or endless file is never slurped."""
    calls: list[int] = []

    def read(size: int = -1) -> bytes:
        calls.append(size)
        return F0_TEXT.encode("utf-8")

    @contextlib.contextmanager
    def fake_open(*args: object, **kwargs: object) -> Iterator[SimpleNamespace]:
        yield SimpleNamespace(read=read)

    monkeypatch.setattr(yaml_io, "open", fake_open, raising=False)
    assert load_registry(F0_PATH, allow_fixture_only=True).version() == "0.0.0"
    assert calls == [yaml_io.MAX_FILE_BYTES + 1]


def test_invalid_utf8_anywhere_in_the_file_is_refused_not_replaced(
    tmp_path: Path,
) -> None:
    """Even in a comment: a lossy decode would let a corrupted file load."""
    payload = F0_TEXT.encode("utf-8") + b"\n# corrupted \xff\xfe bytes\n"
    with pytest.raises(RegistryError, match="UTF-8"):
        load_text(tmp_path, payload)


def test_an_inline_merge_key_is_refused(tmp_path: Path) -> None:
    """``<<`` merges without an alias; it could override a checked key silently."""
    text = F0_TEXT + "\n<<: {pathology: injected}\n"
    with pytest.raises(RegistryError, match="merge keys are not allowed"):
        load_text(tmp_path, text)


def test_python_tags_are_never_constructed(tmp_path: Path) -> None:
    """Only the safe loader: a ``!!python/object/apply`` tag must not run anything."""
    marker = tmp_path / "pwned"
    text = F0_TEXT.replace(
        'registry_version: "0.0.0"',
        f'registry_version: !!python/object/apply:os.mkdir ["{marker}"]',
        1,
    )
    assert text != F0_TEXT
    with pytest.raises(RegistryError):
        load_text(tmp_path, text)
    assert not marker.exists()
