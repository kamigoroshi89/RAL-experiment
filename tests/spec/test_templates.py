"""Template library loader (02-interfaces.md#template, docs/formal/02-templates.md section 3).

Tests 20 to 22 of WS05-T03 plus the structural checks of the loader. The expectations (kinds, units,
robot-obligation flags, parameter lists) come from ``tests/fixtures/spec/template_table.yaml``, a
transcription of the table of the document with its locator, which ``test_fixture_consistency.py``
compares with the markdown itself.
"""

from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

import pytest

from ralmon.signals import SignalId
from ralmon.spec import (
    RobustnessUnit,
    Template,
    TemplateId,
    TemplateKind,
    load_registry,
    load_templates,
)
from ralmon.spec.registry import LoadedRegistry, RegistryError
from ralmon.spec.templates import TemplateLibraryError

from .helpers import (
    F0_PATH,
    TEMPLATE_TABLE_PATH,
    TEMPLATES_PATH,
    drop_entry,
    entry_of,
    f0_doc,
    make_unset,
    read_yaml,
    write_yaml,
)

TABLE = read_yaml(TEMPLATE_TABLE_PATH)["rows"]
KIND_OF_NAME = {
    "CARE_PLAN": TemplateKind.CARE_PLAN,
    "SYSTEM": TemplateKind.SYSTEM,
    "INTEGRITY": TemplateKind.INTEGRITY,
}
UNIT_OF_NAME = {
    "MMHG": RobustnessUnit.MMHG,
    "MS": RobustnessUnit.MS,
    "DOSE": RobustnessUnit.DOSE,
    "DIMENSIONLESS": RobustnessUnit.DIMENSIONLESS,
}


def library_doc() -> dict[str, Any]:
    doc = read_yaml(TEMPLATES_PATH)
    assert isinstance(doc, dict)
    return copy.deepcopy(doc)


def row_of(doc: dict[str, Any], template_id: str) -> dict[str, Any]:
    for row in doc["templates"]:
        if row["id"] == template_id:
            return row  # type: ignore[no-any-return]
    raise KeyError(template_id)


def write_library(tmp_path: Path, doc: Any, name: str = "templates.yaml") -> Path:
    return write_yaml(tmp_path, doc, name)


# --- test 20 -----------------------------------------------------------------------------


def test_templates_cover_seven_ids_with_contract_kinds(f0_templates: Any) -> None:
    assert len(f0_templates) == 7
    assert [t.id for t in f0_templates] == list(
        TemplateId
    )  # one each, in the order of the enum
    assert len({t.id for t in f0_templates}) == 7
    by_id = {t.id: t for t in f0_templates}
    for care_plan in ("RANGE", "SCHED", "HOLD", "COUNT", "RESP"):
        assert by_id[TemplateId[care_plan]].kind is TemplateKind.CARE_PLAN
    assert by_id[TemplateId.SYS].kind is TemplateKind.SYSTEM
    assert by_id[TemplateId.INT].kind is TemplateKind.INTEGRITY
    for row in (
        TABLE
    ):  # the robot-obligation flag of the section-3 table (True for SCHED, RESP, INT)
        assert (
            by_id[TemplateId[row["id"]]].creates_robot_obligation
            is row["creates_robot_obligation"]
        )
    assert {t.id.name for t in f0_templates if t.creates_robot_obligation} == {
        "SCHED",
        "RESP",
        "INT",
    }


def test_the_loaded_library_equals_the_transcribed_table(f0_templates: Any) -> None:
    by_id = {t.id: t for t in f0_templates}
    for row in TABLE:
        template = by_id[TemplateId[row["id"]]]
        assert template == Template(
            id=TemplateId[row["id"]],
            kind=KIND_OF_NAME[row["kind"]],
            formula_past_time=row["formula_past_time"],
            signals=tuple(row["signals"]),
            params=tuple(row["params"]),
            unit=UNIT_OF_NAME[row["unit"]],
            scale_param=row["scale_param"],
            priority_param=row["priority_param"],
            max_verdict_latency_param=row["max_verdict_latency_param"],
            creates_robot_obligation=row["creates_robot_obligation"],
        )
        assert isinstance(template.signals, tuple) and isinstance(
            template.params, tuple
        )
        assert row["locator"].startswith("docs/formal/02-templates.md")


def test_templates_are_frozen_hashable_values(f0_templates: Any) -> None:
    template = f0_templates[0]
    with pytest.raises(AttributeError):
        template.formula_past_time = "x"
    assert hash(template) == hash(f0_templates[0])
    assert {t.id for t in f0_templates} == set(TemplateId)


def test_loading_twice_gives_equal_libraries(f0_registry: LoadedRegistry) -> None:
    assert load_templates(registry=f0_registry) == load_templates(registry=f0_registry)
    assert load_templates(TEMPLATES_PATH, f0_registry) == load_templates(
        registry=f0_registry
    )


# --- test 21 -----------------------------------------------------------------------------


def test_template_names_follow_pattern_and_resolve(
    f0_templates: Any, f0_registry: LoadedRegistry
) -> None:
    for template in f0_templates:
        ident = template.id.value
        assert template.scale_param == f"scale_{ident}"
        assert template.priority_param == f"priority_{ident}"
        assert template.max_verdict_latency_param == f"max_latency_{ident}"
        for name in (
            *template.params,
            template.scale_param,
            template.priority_param,
            template.max_verdict_latency_param,
        ):
            assert f0_registry.is_declared(name), (ident, name)
            assert f0_registry.get(name).value is not None  # F0 sets every name


def test_an_unknown_parameter_name_raises_template_library_error(
    tmp_path: Path, f0_registry: LoadedRegistry
) -> None:
    doc = library_doc()
    row_of(doc, "range")["params"].append("no_such_name")
    with pytest.raises(
        TemplateLibraryError, match=r"range.*no_such_name|no_such_name.*range"
    ):
        load_templates(write_library(tmp_path, doc), f0_registry)


@pytest.mark.parametrize(
    "field", ["scale_param", "priority_param", "max_verdict_latency_param"]
)
def test_the_three_metadata_names_must_follow_the_pattern(
    tmp_path: Path, f0_registry: LoadedRegistry, field: str
) -> None:
    doc = library_doc()
    row_of(doc, "hold")[field] = row_of(doc, "range")[
        field
    ]  # a declared name, the wrong template's
    with pytest.raises(TemplateLibraryError, match=field):
        load_templates(write_library(tmp_path, doc), f0_registry)


@pytest.mark.parametrize(
    "field", ["scale_param", "priority_param", "max_verdict_latency_param"]
)
def test_the_three_metadata_names_must_resolve_in_the_registry(
    tmp_path: Path, f0_registry: LoadedRegistry, field: str
) -> None:
    registry_doc = f0_doc()
    row = next(t for t in TABLE if t["id"] == "RANGE")
    target = row[field]
    if field == "max_verdict_latency_param":
        registry_doc["derived"] = [
            d for d in registry_doc["derived"] if d["name"] != target
        ]
    else:
        drop_entry(registry_doc, target)
    registry = load_registry(
        write_yaml(tmp_path, registry_doc, "r.yaml"), allow_fixture_only=True
    )
    with pytest.raises(TemplateLibraryError, match=target):
        load_templates(registry=registry)


def test_names_declared_unset_still_resolve(tmp_path: Path) -> None:
    """03 section 2.5 rule 4: the structure of a template does not depend on the value."""
    doc = f0_doc()
    make_unset(doc, "scale_hold", ("hold",))
    make_unset(doc, "priority_int", ("int",))
    make_unset(doc, "cuff_inflation_min", ("sys",))
    registry = load_registry(write_yaml(tmp_path, doc), allow_fixture_only=True)
    templates = load_templates(registry=registry)
    assert len(templates) == 7


def test_the_real_registry_resolves_every_template() -> None:
    """Done when: ``load_templates(registry=load_registry())`` has seven templates (the real file has
    unset names; the structure resolves all the same)."""
    registry = load_registry()
    assert len(load_templates(registry=registry)) == 7
    assert len(load_templates()) == 7  # registry=None reads the default registry


def test_a_registry_without_is_declared_is_asked_through_get(
    f0_registry: LoadedRegistry,
) -> None:
    class BareRegistry:
        """Only the three methods of the ParameterRegistry protocol."""

        def get(self, name: str) -> Any:
            return f0_registry.get(name)

        def bounds(self, signal: str) -> Any:
            return f0_registry.bounds(signal)

        def version(self) -> str:
            return f0_registry.version()

    assert len(load_templates(registry=BareRegistry())) == 7  # type: ignore[arg-type]


def test_a_bare_registry_that_lacks_a_name_is_refused(
    f0_registry: LoadedRegistry,
) -> None:
    class Missing:
        def get(self, name: str) -> Any:
            if name == "bp_band_low":
                raise RegistryError("unknown")
            return f0_registry.get(name)

        def bounds(self, signal: str) -> Any:
            return f0_registry.bounds(signal)

        def version(self) -> str:
            return "0"

    with pytest.raises(TemplateLibraryError, match="bp_band_low"):
        load_templates(registry=Missing())  # type: ignore[arg-type]


# --- test 22 -----------------------------------------------------------------------------


def test_template_signals_are_signal_ids(f0_templates: Any) -> None:
    valid = {s.value for s in SignalId}
    for template in f0_templates:
        assert template.signals, template.id
        assert set(template.signals) <= valid
        assert len(set(template.signals)) == len(template.signals)
    by_id = {t.id: t for t in f0_templates}
    assert by_id[TemplateId.RESP].signals == ("dispense", "meas", "bp_drop")
    assert "age" not in {
        s for t in f0_templates for s in t.signals
    }  # an instance term, not a signal


@pytest.mark.parametrize("bad", ["not_a_signal", "BP", "bp ", "", None, 5, ["bp"]])
def test_a_fixture_row_with_an_unknown_signal_raises(
    tmp_path: Path, f0_registry: LoadedRegistry, bad: Any
) -> None:
    doc = library_doc()
    row_of(doc, "range")["signals"].append(bad)
    with pytest.raises(TemplateLibraryError, match=r"range.*(SignalId|list of names)"):
        load_templates(write_library(tmp_path, doc), f0_registry)


def test_signals_and_params_must_match_the_formula(
    tmp_path: Path, f0_registry: LoadedRegistry
) -> None:
    """The metadata is the list of names the string mentions (02-templates.md section 3.1 notes)."""
    for field, name in (("signals", "dispense"), ("params", "int_window")):
        doc = library_doc()
        row_of(doc, "range")[field].append(name)  # declared, but not in the string
        with pytest.raises(TemplateLibraryError, match=name):
            load_templates(write_library(tmp_path, doc), f0_registry)
    for field in ("signals", "params"):
        doc = library_doc()
        row_of(doc, "range")[field].pop()  # in the string, missing from the metadata
        with pytest.raises(TemplateLibraryError, match="range"):
            load_templates(write_library(tmp_path, doc), f0_registry)
    doc = library_doc()
    row_of(doc, "range")["params"].append("bp_band_low")  # duplicate
    with pytest.raises(TemplateLibraryError, match="bp_band_low"):
        load_templates(write_library(tmp_path, doc), f0_registry)


def test_the_formula_may_use_only_the_grammar_vocabulary(
    tmp_path: Path, f0_registry: LoadedRegistry
) -> None:
    for formula in (
        "historically(meas -> (bp >= bp_band_low and bp <= bp_band_high)) and mystery",
        "historically(meas -> (bp >= bp_band_low and bp <= bp_band_high)); x",
        "historically(meas -> (bp >= bp_band_low and bp <= bp_band_high))\n",
        "historically(meas -> (bp >= bp_band_low and bp <= BP_BAND_HIGH))",
        "historically(meas -> __import__('os'))",
        "",
        "   ",
    ):
        doc = library_doc()
        row_of(doc, "range")["formula_past_time"] = formula
        with pytest.raises(TemplateLibraryError, match="range"):
            load_templates(write_library(tmp_path, doc), f0_registry)


# --- structure ---------------------------------------------------------------------------


def test_kinds_follow_the_decomposition_of_the_specification(
    tmp_path: Path, f0_registry: LoadedRegistry
) -> None:
    """phi = phi_CP and phi_SYS and phi_INT: SYS is phi_sys, INT is phi_int, the rest phi_cp."""
    for ident, wrong in (
        ("sys", "phi_cp"),
        ("int", "phi_cp"),
        ("range", "phi_sys"),
        ("hold", "phi_int"),
        ("resp", "phi_cp_typo"),
        ("range", None),
        ("range", 5),
    ):
        doc = library_doc()
        row_of(doc, ident)["kind"] = wrong
        with pytest.raises(TemplateLibraryError, match=ident):
            load_templates(write_library(tmp_path, doc), f0_registry)


def test_every_template_id_appears_exactly_once(
    tmp_path: Path, f0_registry: LoadedRegistry
) -> None:
    doc = library_doc()
    doc["templates"].pop()  # int missing
    with pytest.raises(TemplateLibraryError, match="int"):
        load_templates(write_library(tmp_path, doc), f0_registry)
    doc = library_doc()
    doc["templates"].append(copy.deepcopy(doc["templates"][0]))
    with pytest.raises(TemplateLibraryError, match="range"):
        load_templates(write_library(tmp_path, doc), f0_registry)
    doc = library_doc()
    doc["templates"][0]["id"] = "bogus"
    with pytest.raises(TemplateLibraryError, match="bogus"):
        load_templates(write_library(tmp_path, doc), f0_registry)
    doc = library_doc()
    doc[
        "templates"
    ].reverse()  # file order does not matter; the library is in enum order
    templates = load_templates(write_library(tmp_path, doc), f0_registry)
    assert [t.id for t in templates] == list(TemplateId)


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("unit", "kg"),
        ("unit", None),
        ("unit", "MMHG"),
        ("creates_robot_obligation", "yes please"),
        ("creates_robot_obligation", 1),
        ("creates_robot_obligation", None),
        ("formula_past_time", 5),
        ("formula_past_time", None),
        ("signals", "meas"),
        ("signals", None),
        ("signals", []),
        ("params", "bp_band_low"),
        ("params", None),
        ("params", [None]),
        ("params", []),
        ("scale_param", None),
        ("scale_param", 5),
        ("source", ""),
        ("source", None),
        ("extra_field", 1),
    ],
)
def test_malformed_rows_raise_template_library_error(
    tmp_path: Path, f0_registry: LoadedRegistry, field: str, bad: Any
) -> None:
    doc = library_doc()
    row_of(doc, "range")[field] = bad
    with pytest.raises(TemplateLibraryError):
        load_templates(write_library(tmp_path, doc), f0_registry)


@pytest.mark.parametrize(
    "field",
    [
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
    ],
)
def test_every_row_field_is_required(
    tmp_path: Path, f0_registry: LoadedRegistry, field: str
) -> None:
    doc = library_doc()
    del doc["templates"][0][field]
    with pytest.raises(TemplateLibraryError, match=field):
        load_templates(write_library(tmp_path, doc), f0_registry)


@pytest.mark.parametrize("key", ["library_version", "pathology", "templates"])
def test_top_level_keys_are_required_and_strict(
    tmp_path: Path, f0_registry: LoadedRegistry, key: str
) -> None:
    doc = library_doc()
    del doc[key]
    with pytest.raises(TemplateLibraryError, match=key):
        load_templates(write_library(tmp_path, doc), f0_registry)
    doc = library_doc()
    doc["surprise"] = 1
    with pytest.raises(TemplateLibraryError, match="surprise"):
        load_templates(write_library(tmp_path, doc), f0_registry)


@pytest.mark.parametrize("bad", [None, "text", 5, {"a": 1}, [], [None], ["text"], [[]]])
def test_templates_must_be_a_list_of_mappings(
    tmp_path: Path, f0_registry: LoadedRegistry, bad: Any
) -> None:
    doc = library_doc()
    doc["templates"] = bad
    with pytest.raises(TemplateLibraryError, match="templates"):
        load_templates(write_library(tmp_path, doc), f0_registry)


# --- registry cross-checks (03 section 2.5 rule 10) -------------------------------------------


@pytest.mark.parametrize(
    ("name", "unit"),
    [
        ("scale_range", "ms"),  # RANGE margin is mmHg
        ("scale_sched", "mmHg"),  # SCHED margin is ms
        ("scale_count", "mmHg"),  # COUNT margin is dose
        ("scale_hold", "dose"),
        ("scale_int", "mmHg"),
    ],
)
def test_a_scale_must_have_the_unit_of_its_template(
    tmp_path: Path, name: str, unit: str
) -> None:
    doc = f0_doc()
    entry_of(doc, name)["unit"] = unit
    registry = load_registry(write_yaml(tmp_path, doc), allow_fixture_only=True)
    with pytest.raises(TemplateLibraryError, match=name):
        load_templates(registry=registry)


def test_an_unset_scale_is_not_unit_checked(tmp_path: Path) -> None:
    doc = f0_doc()
    make_unset(doc, "scale_range", ("range",))
    registry = load_registry(write_yaml(tmp_path, doc), allow_fixture_only=True)
    assert len(load_templates(registry=registry)) == 7


def test_templates_follow_the_registry_it_is_given_not_the_default(
    tmp_path: Path, f0_registry: LoadedRegistry
) -> None:
    doc = f0_doc()
    drop_entry(doc, "bp_band_high")
    other = load_registry(write_yaml(tmp_path, doc), allow_fixture_only=True)
    with pytest.raises(TemplateLibraryError, match="bp_band_high"):
        load_templates(registry=other)
    assert len(load_templates(registry=f0_registry)) == 7


# --- robust inputs -----------------------------------------------------------------------


@pytest.mark.parametrize("bad", [5, b"x.yaml", ["a"], {"a": 1}, object(), True])
def test_a_path_of_the_wrong_type_raises_template_library_error(
    bad: Any, f0_registry: LoadedRegistry
) -> None:
    with pytest.raises(TemplateLibraryError):
        load_templates(bad, f0_registry)


@pytest.mark.parametrize("bad", [5, "text", ["a"], {"a": 1}, object(), True, b"x"])
def test_a_registry_of_the_wrong_type_raises_template_library_error(bad: Any) -> None:
    with pytest.raises(TemplateLibraryError, match="must be a ParameterRegistry"):
        load_templates(registry=bad)


@pytest.mark.parametrize(
    "bad", [None, "", "1", "1.0", "1.0.0.0", "v1.0.0", "01.0.0", 1, 1.0, ["1.0.0"]]
)
def test_library_version_must_be_a_semantic_version_string(
    tmp_path: Path, f0_registry: LoadedRegistry, bad: Any
) -> None:
    doc = library_doc()
    doc["library_version"] = bad
    with pytest.raises(TemplateLibraryError, match="library_version"):
        load_templates(write_library(tmp_path, doc), f0_registry)


@pytest.mark.parametrize("bad", [None, "", "  ", 5, ["x"]])
def test_library_pathology_must_be_a_non_empty_string(
    tmp_path: Path, f0_registry: LoadedRegistry, bad: Any
) -> None:
    doc = library_doc()
    doc["pathology"] = bad
    with pytest.raises(TemplateLibraryError, match="pathology"):
        load_templates(write_library(tmp_path, doc), f0_registry)


def test_missing_directory_and_unreadable_template_files(
    tmp_path: Path, f0_registry: LoadedRegistry
) -> None:
    with pytest.raises(TemplateLibraryError, match="nothing-here.yaml"):
        load_templates(tmp_path / "nothing-here.yaml", f0_registry)
    with pytest.raises(TemplateLibraryError):
        load_templates(tmp_path, f0_registry)
    binary = tmp_path / "bin.yaml"
    binary.write_bytes(b"\xff\xfe\x00bad")
    with pytest.raises(TemplateLibraryError):
        load_templates(binary, f0_registry)
    with pytest.raises(TemplateLibraryError):
        load_templates(str(tmp_path / "a\x00b.yaml"), f0_registry)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "null\n",
        "- a\n",
        "a: [unclosed\n",
        "a: &x 1\nb: *x\n",
        "a: !!python/object/apply:os.system ['echo']\n",
        "library_version: 1\nlibrary_version: 2\n",
        "a: 1\n---\nb: 2\n",
        "a: " + "[" * 100_000 + "\n",
    ],
    ids=lambda t: repr(t[:30]),
)
def test_hostile_yaml_raises_template_library_error(
    tmp_path: Path, f0_registry: LoadedRegistry, text: str
) -> None:
    path = tmp_path / "t.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(TemplateLibraryError):
        load_templates(path, f0_registry)


def test_the_library_file_has_no_duplicate_keys_or_aliases() -> None:
    text = TEMPLATES_PATH.read_text(encoding="utf-8")
    assert re.search(r"^\s*[&*]", text, flags=re.MULTILINE) is None
    assert read_yaml(TEMPLATES_PATH)["library_version"]


def test_the_default_library_path_is_next_to_the_registry_configs() -> None:
    from ralmon.spec import templates as templates_module

    assert templates_module.default_templates_path() == TEMPLATES_PATH
    assert F0_PATH.is_file()


class _Delegating:
    """A bare ParameterRegistry (get, bounds, version) over the F0 registry with chosen answers."""

    def __init__(self, base: LoadedRegistry, answers: dict[str, Any]) -> None:
        self._base = base
        self._answers = answers

    def get(self, name: str) -> Any:
        if name in self._answers:
            answer = self._answers[name]
            if isinstance(answer, Exception):
                raise answer
            return answer
        return self._base.get(name)

    def bounds(self, signal: str) -> Any:
        return self._base.bounds(signal)

    def version(self) -> str:
        return self._base.version()


def _entry(name: str, value: float, unit: str) -> Any:
    from ralmon.spec import RegistryEntry

    return RegistryEntry(name, value, unit, "r; illustrative, unverified", "s", None)


def test_a_registry_that_returns_something_else_than_an_entry_is_refused(
    f0_registry: LoadedRegistry,
) -> None:
    registry = _Delegating(f0_registry, {"bp_band_low": "not an entry"})
    with pytest.raises(TemplateLibraryError, match="RegistryEntry"):
        load_templates(registry=registry)  # type: ignore[arg-type]


def test_a_registry_that_fails_unexpectedly_is_reported_as_template_library_error(
    f0_registry: LoadedRegistry,
) -> None:
    registry = _Delegating(f0_registry, {"bp_band_low": RuntimeError("boom")})
    with pytest.raises(TemplateLibraryError, match="boom"):
        load_templates(registry=registry)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("answers", "message"),
    [
        ({"scale_range": _entry("scale_range", 0.0, "mmHg")}, "positive"),
        ({"scale_range": _entry("scale_range", -1.0, "mmHg")}, "positive"),
        ({"scale_range": _entry("scale_range", 20.0, "ms")}, "unit"),
        ({"priority_range": _entry("priority_range", 0.0, "1")}, "rank"),
        ({"priority_range": _entry("priority_range", 1.5, "1")}, "rank"),
        ({"priority_range": _entry("priority_range", 2.0, "ms")}, "rank"),
    ],
)
def test_the_loader_checks_scale_and_priority_of_a_registry_that_does_not(
    f0_registry: LoadedRegistry, answers: dict[str, Any], message: str
) -> None:
    """A registry other than ``LoadedRegistry`` may not have enforced the rules: the loader does."""
    with pytest.raises(TemplateLibraryError, match=message):
        load_templates(registry=_Delegating(f0_registry, answers))  # type: ignore[arg-type]
    good = {"priority_range": _entry("priority_range", 2.0, "1")}
    assert len(load_templates(registry=_Delegating(f0_registry, good))) == 7  # type: ignore[arg-type]
