"""Parameter registry loader (02-interfaces.md#parameter-registry, docs/formal/03-parameter-registry.md).

Tests 10 to 18 of WS05-T03 and the loader rules of section 2.5/2.6 of the formal document. Hand values use
the F0 fixture (``tests/fixtures/spec/registry_f0.yaml``), never the real registry file, whose values a
human may change (the real file is only checked to load, test 18).
"""

from __future__ import annotations

import builtins
import hashlib
from pathlib import Path
from typing import Any

import pytest

from ralmon.spec import PhysioBounds, RegistryEntry, load_registry
from ralmon.spec import registry as registry_module
from ralmon.spec.registry import (
    FIXTURE_ONLY_MARKER,
    LoadedRegistry,
    RegistryError,
    UnsetParameterError,
    as_duration_ms,
    as_priority,
)

from .helpers import (
    F0_PATH,
    FIXTURE_REGISTRY_PATH,
    REAL_REGISTRY_PATH,
    ROOT,
    STEP_MS,
    drop_entry,
    entry_of,
    f0_doc,
    make_unset,
    read_yaml,
    unfixture,
    write_yaml,
)


def load_doc(tmp_path: Path, doc: dict[str, Any], **kwargs: Any) -> LoadedRegistry:
    kwargs.setdefault("allow_fixture_only", True)
    return load_registry(write_yaml(tmp_path, doc), **kwargs)


# --- test 10 -----------------------------------------------------------------------------


def test_registry_f0_entries(f0_registry: LoadedRegistry) -> None:
    low = f0_registry.get("bp_band_low")
    assert isinstance(low, RegistryEntry)
    assert low.value == 110.0
    assert low.unit == "mmHg"
    assert low.reviewed_by is None
    assert "illustrative, unverified" in low.rationale
    assert f0_registry.get("delta1").value == 3_600_000
    assert f0_registry.get("delta2").value == 10_800_000
    assert f0_registry.get("priority_hold").unit == "1"
    assert f0_registry.get("scale_sched").unit == "ms"


def test_registry_entries_are_the_frozen_contract_dataclass(
    f0_registry: LoadedRegistry,
) -> None:
    entry = f0_registry.get("scale_range")
    assert entry == RegistryEntry(
        name="scale_range",
        value=20.0,
        unit="mmHg",
        rationale=entry.rationale,
        source_ref=entry.source_ref,
        reviewed_by=None,
    )
    assert type(entry.value) is float
    with pytest.raises(AttributeError):
        entry.value = 1.0  # type: ignore[misc]
    assert f0_registry.get("scale_range") == entry


# --- test 11 -----------------------------------------------------------------------------


def test_registry_unknown_name_raises_registry_error(
    f0_registry: LoadedRegistry,
) -> None:
    with pytest.raises(RegistryError, match="no_such_name"):
        f0_registry.get("no_such_name")
    assert not issubclass(RegistryError, UnsetParameterError)
    try:
        f0_registry.get("no_such_name")
    except UnsetParameterError:  # pragma: no cover - would be a wrong subclass
        pytest.fail("an unknown name is not an unset name")
    except RegistryError:
        pass


@pytest.mark.parametrize(
    "bad", [None, 1, 1.5, True, [], ["bp_band_low"], {}, b"bp_band_low", "", " "]
)
def test_registry_get_with_a_non_name_raises_registry_error(
    f0_registry: LoadedRegistry, bad: Any
) -> None:
    with pytest.raises(RegistryError):
        f0_registry.get(bad)


# --- test 12 -----------------------------------------------------------------------------


def test_registry_bounds(f0_registry: LoadedRegistry) -> None:
    bounds = f0_registry.bounds("bp")
    assert bounds == PhysioBounds(signal="bp", lower=50.0, upper=250.0)
    assert isinstance(bounds, PhysioBounds)


def test_registry_bounds_compose_names_with_underscores(tmp_path: Path) -> None:
    """``inflation_ms`` contains an underscore: the prefix and suffix are removed, not split on it."""
    doc = f0_doc()
    for side, value in (("lower", 0.0), ("upper", 180000.0)):
        doc["entries"].append(
            {
                "name": f"bound_inflation_ms_{side}",
                "value": value,
                "unit": "ms",
                "rationale": "FIXTURE-ONLY test row; illustrative, unverified",
                "source_ref": "test",
                "reviewed_by": None,
            }
        )
    registry = load_doc(tmp_path, doc)
    assert registry.bounds("inflation_ms") == PhysioBounds(
        "inflation_ms", 0.0, 180000.0
    )


def test_registry_bounds_unset_partner_raises_unset_parameter_error(
    tmp_path: Path,
) -> None:
    doc = f0_doc()
    make_unset(doc, "bound_bp_upper", ("range",))
    registry = load_doc(tmp_path, doc)
    with pytest.raises(UnsetParameterError, match="bound_bp_upper"):
        registry.bounds("bp")


@pytest.mark.parametrize("signal", ["nope", "", "bp ", "BP"])
def test_registry_bounds_of_an_undeclared_signal_raises_registry_error(
    f0_registry: LoadedRegistry, signal: str
) -> None:
    with pytest.raises(RegistryError, match="no bounds are declared"):
        f0_registry.bounds(signal)


@pytest.mark.parametrize("signal", [None, 5, ["bp"], b"bp", {}])
def test_registry_bounds_of_a_non_name_raises_registry_error(
    f0_registry: LoadedRegistry, signal: Any
) -> None:
    with pytest.raises(RegistryError, match="signal name must be a str"):
        f0_registry.bounds(signal)


def test_registry_bounds_with_one_side_missing_raises_registry_error(
    tmp_path: Path,
) -> None:
    doc = f0_doc()
    drop_entry(doc, "bound_bp_upper")
    registry = load_doc(tmp_path, doc)
    with pytest.raises(RegistryError, match="bound_bp_upper"):
        registry.bounds("bp")


# --- test 13 -----------------------------------------------------------------------------


@pytest.mark.parametrize("field", ["rationale", "source_ref"])
@pytest.mark.parametrize("value", ["", "   ", "\n\t", None, 5, ["x"], True])
def test_registry_rejects_entry_without_rationale_or_source_ref(
    tmp_path: Path, field: str, value: Any
) -> None:
    doc = f0_doc()
    entry_of(doc, "bp_band_high")[field] = value
    with pytest.raises(RegistryError, match="bp_band_high") as info:
        load_doc(tmp_path, doc)
    assert field in str(info.value)


def test_registry_rejects_entry_with_a_missing_field(tmp_path: Path) -> None:
    for field in ("name", "value", "unit", "rationale", "source_ref", "reviewed_by"):
        doc = f0_doc()
        del entry_of(doc, "bp_band_high")[field]
        with pytest.raises(
            RegistryError, match=field if field != "name" else "entries"
        ):
            load_doc(tmp_path, doc)


def test_registry_rejects_an_unreviewed_entry_that_does_not_say_it_is_unverified(
    tmp_path: Path,
) -> None:
    """ADR-020 made mechanical: ``reviewed_by`` null needs a rationale that ends with the string."""
    doc = f0_doc()
    entry_of(doc, "bp_band_high")["rationale"] = "guideline target"
    with pytest.raises(RegistryError, match="bp_band_high.*illustrative, unverified"):
        load_doc(tmp_path, doc)
    entry_of(doc, "bp_band_high")["rationale"] = "illustrative, unverified; extra"
    with pytest.raises(RegistryError, match="bp_band_high"):
        load_doc(tmp_path, doc)
    entry_of(doc, "bp_band_high")["rationale"] = "Illustrative, Unverified"
    with pytest.raises(RegistryError, match="bp_band_high"):
        load_doc(tmp_path, doc)


def test_registry_accepts_a_reviewed_entry_with_any_rationale(tmp_path: Path) -> None:
    doc = f0_doc()
    entry = entry_of(doc, "bp_band_high")
    entry["rationale"] = "guideline target for the drug class"
    entry["reviewed_by"] = "clinician-01"
    doc["review_status"] = "partially_reviewed"
    registry = load_doc(tmp_path, doc)
    assert registry.get("bp_band_high").reviewed_by == "clinician-01"
    assert "bp_band_high" not in registry.unverified_names()
    assert "bp_band_low" in registry.unverified_names()


# --- test 14 -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("lower", "upper"), [(250.0, 50.0), (50.0, 50.0), (0.0, -1.0), (1e9, 1e9)]
)
def test_registry_rejects_inverted_bounds(
    tmp_path: Path, lower: float, upper: float
) -> None:
    doc = f0_doc()
    entry_of(doc, "bound_bp_lower")["value"] = lower
    entry_of(doc, "bound_bp_upper")["value"] = upper
    with pytest.raises(RegistryError, match="bp"):
        load_doc(tmp_path, doc)


# --- test 15 -----------------------------------------------------------------------------

WINDOW_NAMES = ("sched_window", "hold_lookback", "int_window", "delta1", "delta2")


def test_registry_window_entries_are_multiples_of_step(tmp_path: Path) -> None:
    doc = f0_doc()
    entry_of(doc, "sched_window")["value"] = 1_800_000.0
    assert (
        load_doc(tmp_path, doc, step_ms=60_000).get("sched_window").value == 1_800_000
    )
    entry_of(doc, "sched_window")["value"] = 90_500.0
    with pytest.raises(RegistryError, match=r"sched_window.*60000|60000.*sched_window"):
        load_doc(tmp_path, doc, step_ms=60_000)


@pytest.mark.parametrize("name", WINDOW_NAMES)
def test_every_window_parameter_is_checked(tmp_path: Path, name: str) -> None:
    doc = f0_doc()
    entry_of(doc, name)["value"] = entry_of(doc, name)["value"] + 1000.0
    with pytest.raises(RegistryError, match=name):
        load_doc(tmp_path, doc, step_ms=60_000)
    assert load_doc(tmp_path, doc).get(name).value % 60_000 == 1000  # no step: no check
    assert (
        load_doc(tmp_path, doc, step_ms=1000).get(name) is not None
    )  # a compatible step


def test_thresholds_that_are_not_windows_are_not_aligned(tmp_path: Path) -> None:
    """``cuff_inflation_min`` (an inflation duration) and the scales are in ms but are not window edges."""
    doc = f0_doc()
    entry_of(doc, "cuff_inflation_min")["value"] = 90_500.0
    entry_of(doc, "scale_sys")["value"] = 77_777.0
    registry = load_doc(tmp_path, doc, step_ms=60_000)
    assert registry.get("cuff_inflation_min").value == 90_500


def test_window_width_delta2_minus_delta1_must_not_be_negative(tmp_path: Path) -> None:
    doc = f0_doc()
    entry_of(doc, "delta1")["value"] = 10_800_000.0
    entry_of(doc, "delta2")["value"] = 3_600_000.0
    with pytest.raises(RegistryError, match="delta2"):
        load_doc(tmp_path, doc, step_ms=60_000)
    entry_of(doc, "delta2")["value"] = 10_800_000.0  # a zero width is non-negative
    assert load_doc(tmp_path, doc, step_ms=60_000).get("delta2").value == 10_800_000


def test_window_parameter_names_must_be_declared_and_in_ms(tmp_path: Path) -> None:
    doc = f0_doc()
    doc["window_parameters"].append("no_such_window")
    with pytest.raises(RegistryError, match="no_such_window"):
        load_doc(tmp_path, doc)
    doc = f0_doc()
    doc["window_parameters"].append("bp_band_low")  # an mmHg threshold is not a window
    with pytest.raises(RegistryError, match="bp_band_low"):
        load_doc(tmp_path, doc)
    doc = f0_doc()
    doc["window_parameters"].append(
        "max_latency_range"
    )  # a derived name is not a window parameter
    with pytest.raises(RegistryError, match=r"max_latency_range.*derived name"):
        load_doc(tmp_path, doc)


def test_an_unset_window_parameter_is_accepted_and_checked_when_set(
    tmp_path: Path,
) -> None:
    doc = f0_doc()
    make_unset(doc, "sched_window", ("sched",))
    registry = load_doc(tmp_path, doc, step_ms=60_000)
    assert registry.is_declared("sched_window") and not registry.is_set("sched_window")
    with pytest.raises(UnsetParameterError, match="sched_window"):
        registry.get("sched_window")


@pytest.mark.parametrize(
    "step", [0, -1, -60_000, True, False, 1.5, 60000.0, "60000", [60000], b"1"]
)
def test_step_ms_must_be_a_positive_int(tmp_path: Path, step: Any) -> None:
    with pytest.raises(RegistryError, match="step_ms"):
        load_registry(F0_PATH, step_ms=step, allow_fixture_only=True)


def test_step_ms_may_be_huge_or_absent(tmp_path: Path) -> None:
    assert load_registry(F0_PATH, allow_fixture_only=True).step_ms is None
    registry = load_registry(F0_PATH, step_ms=1, allow_fixture_only=True)
    assert registry.step_ms == 1
    assert registry.get("max_latency_range").value == 1


# --- test 16 -----------------------------------------------------------------------------


def test_registry_derived_latency_entries(f0_registry: LoadedRegistry) -> None:
    resp = f0_registry.get("max_latency_resp")
    assert resp.value == 10_860_000  # delta2 + step_ms
    assert (
        f0_registry.get("max_latency_sched").value == 1_860_000
    )  # sched_window + step_ms
    for name in ("range", "hold", "count", "sys", "int"):
        assert f0_registry.get(f"max_latency_{name}").value == 60_000  # step_ms
    assert resp.unit == "ms"
    assert resp.reviewed_by is None
    assert resp.name == "max_latency_resp"
    assert type(resp.value) is float


def test_derived_entries_carry_a_derivation_rationale_and_the_document_source(
    f0_registry: LoadedRegistry,
) -> None:
    resp = f0_registry.get("max_latency_resp")
    assert resp.rationale.startswith("derived: delta2 + step_ms")
    assert resp.rationale.endswith("illustrative, unverified")  # delta2 is unreviewed
    assert resp.source_ref == "docs/formal/03-parameter-registry.md section 3"
    assert f0_registry.get("max_latency_range").rationale.startswith("derived: step_ms")


def test_a_derived_value_of_reviewed_inputs_is_not_called_unverified(
    tmp_path: Path,
) -> None:
    doc = f0_doc()
    for item in doc["entries"]:
        item["reviewed_by"] = "clinician-01"
    doc["review_status"] = "reviewed"
    registry = load_doc(tmp_path, doc, step_ms=60_000)
    rationale = registry.get("max_latency_resp").rationale
    assert rationale == "derived: delta2 + step_ms"
    assert (
        registry.get("max_latency_resp").reviewed_by is None
    )  # a derived value is never reviewed
    assert registry.unverified_names() == ()


def test_derived_names_need_step_ms_only_when_the_formula_uses_it(
    tmp_path: Path,
) -> None:
    registry = load_registry(F0_PATH, allow_fixture_only=True)  # no step_ms
    with pytest.raises(RegistryError, match="step_ms"):
        registry.get("max_latency_resp")
    assert registry.is_declared("max_latency_resp")
    doc = f0_doc()
    doc["derived"].append(
        {
            "name": "two_windows",
            "unit": "ms",
            "formula": "delta1 + delta2",
            "template": "resp",
        }
    )
    no_step = load_doc(tmp_path, doc)
    assert no_step.get("two_windows").value == 3_600_000 + 10_800_000


def test_derived_with_an_unset_term_raises_naming_both(tmp_path: Path) -> None:
    doc = f0_doc()
    make_unset(doc, "sched_window", ("sched",))
    registry = load_doc(tmp_path, doc, step_ms=60_000)
    with pytest.raises(UnsetParameterError) as info:
        registry.get("max_latency_sched")
    assert "max_latency_sched" in str(info.value)
    assert "sched_window" in str(info.value)
    assert registry.get("max_latency_range").value == 60_000  # the others still resolve
    assert registry.is_set("max_latency_range") and not registry.is_set(
        "max_latency_sched"
    )


def test_the_derivation_grammar_is_a_sum_and_never_eval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("eval or exec was called")

    monkeypatch.setattr(builtins, "eval", forbidden)
    monkeypatch.setattr(builtins, "exec", forbidden)
    doc = f0_doc()
    doc["derived"].append(
        {
            "name": "triple",
            "unit": "ms",
            "formula": "delta1+delta2 +  step_ms",
            "template": "resp",
        }
    )
    registry = load_doc(tmp_path, doc, step_ms=60_000)
    assert registry.get("triple").value == 3_600_000 + 10_800_000 + 60_000
    assert registry.get("max_latency_resp").value == 10_860_000


@pytest.mark.parametrize(
    "formula",
    [
        "",
        " ",
        "delta2 - step_ms",
        "delta2 * 2",
        "delta2 / step_ms",
        "(delta2)",
        "delta2 +",
        "+ delta2",
        "delta2 + + step_ms",
        "delta2 step_ms",
        "2 + step_ms",
        "delta2 + 60000",
        "__import__('os').getcwd()",
        "delta2.real",
        "delta2; step_ms",
        "Delta2",
        "no_such_term + step_ms",
        "max_latency_range + step_ms",  # a derived name is not a term
        "bp_band_low + step_ms",  # unit mismatch: mmHg + ms
        "delta2 +\nstep_ms",
        "delta2 + step_ms\n",
        None,
        5,
        ["delta2"],
    ],
)
def test_invalid_derivation_formulas_are_rejected_at_load(
    tmp_path: Path, formula: Any
) -> None:
    doc = f0_doc()
    doc["derived"][4]["formula"] = formula
    with pytest.raises(RegistryError, match="max_latency_resp"):
        load_doc(tmp_path, doc, step_ms=60_000)


def test_a_derived_unit_must_be_ms_summable(tmp_path: Path) -> None:
    doc = f0_doc()
    doc["derived"][4]["unit"] = "mmHg"
    with pytest.raises(RegistryError, match="max_latency_resp"):
        load_doc(tmp_path, doc, step_ms=60_000)
    doc = (
        f0_doc()
    )  # step_ms is a duration: a formula that is just step_ms cannot be in mmHg
    doc["derived"][0]["unit"] = "mmHg"
    with pytest.raises(
        RegistryError, match=r"max_latency_range.*step_ms.*duration|step_ms"
    ):
        load_doc(tmp_path, doc, step_ms=60_000)


# --- test 17 -----------------------------------------------------------------------------


def test_registry_version_declared(f0_registry: LoadedRegistry, tmp_path: Path) -> None:
    assert f0_registry.version() == read_yaml(F0_PATH)["registry_version"]
    assert isinstance(f0_registry.version(), str)
    doc = f0_doc()
    doc["registry_version"] = "12.0.345"
    assert load_doc(tmp_path, doc).version() == "12.0.345"
    del doc["registry_version"]
    with pytest.raises(RegistryError, match="registry_version"):
        load_doc(tmp_path, doc)


@pytest.mark.parametrize(
    "version",
    [
        None,
        "",
        "1",
        "1.0",
        "1.0.0.0",
        "v1.0.0",
        "1.0.0-rc1",
        "01.0.0",
        "1.0.0\n",
        " 1.0.0",
        1,
        1.0,
        [1],
        True,
    ],
)
def test_registry_version_must_be_a_semantic_version_string(
    tmp_path: Path, version: Any
) -> None:
    doc = f0_doc()
    doc["registry_version"] = version
    with pytest.raises(RegistryError, match="registry_version"):
        load_doc(tmp_path, doc)


# --- test 18 -----------------------------------------------------------------------------


def test_real_registry_file_loads() -> None:
    """``load_registry()`` reads configs/registry/hypertension.yaml; the test asserts that the file loads
    and that nothing is dropped, not any value (a human may change the values)."""
    registry = load_registry()
    assert registry.path == REAL_REGISTRY_PATH
    raw = read_yaml(REAL_REGISTRY_PATH)
    assert registry.version() == raw["registry_version"]
    assert registry.pathology == raw["pathology"]
    assert registry.review_status == raw["review_status"]
    for item in raw["entries"]:
        entry = registry.get(item["name"])
        assert entry.reviewed_by == item["reviewed_by"]
        assert entry.unit == item["unit"]
    unreviewed = [i["name"] for i in raw["entries"] if i["reviewed_by"] is None]
    assert (
        list(registry.unverified_names()) == unreviewed
    )  # unreviewed entries are kept
    assert [e["parameter"] for e in raw["unset"]] == list(registry.unset_names())
    assert registry.fixture_only is False


def test_real_registry_exposes_unset_names_honestly() -> None:
    registry = load_registry()
    for name in registry.unset_names():
        assert registry.is_declared(name)
        assert not registry.is_set(name)
        with pytest.raises(UnsetParameterError, match=name):
            registry.get(name)


def test_the_default_registry_path_is_resolved_from_the_directory_with_pyproject(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert (ROOT / "pyproject.toml").is_file()
    assert registry_module.default_registry_path() == REAL_REGISTRY_PATH
    monkeypatch.setattr(registry_module, "_repo_root", lambda: tmp_path)
    with pytest.raises(RegistryError) as info:
        load_registry()
    assert str(tmp_path / "configs" / "registry" / "hypertension.yaml") in str(
        info.value
    )
    monkeypatch.setattr(registry_module, "_repo_root", lambda: None)
    with pytest.raises(RegistryError, match="pyproject.toml"):
        load_registry()


# --- fixture registry gate (ADR-027) -----------------------------------------------------


def test_a_registry_with_fixture_only_rows_needs_the_flag_and_names_the_rows() -> None:
    with pytest.raises(RegistryError) as info:
        load_registry(F0_PATH)
    message = str(info.value)
    assert FIXTURE_ONLY_MARKER in message
    for name in ("sched_window", "delta_resp", "scale_hold", "cuff_error_sd"):
        assert name in message
    assert "allow_fixture_only" in message
    with pytest.raises(RegistryError):
        load_registry(F0_PATH, allow_fixture_only=False)
    registry = load_registry(F0_PATH, allow_fixture_only=True)
    assert registry.fixture_only is True
    assert len(registry.fixture_only_names()) == 29
    assert "sched_window" in registry.fixture_only_names()


@pytest.mark.parametrize("flag", [None, 1, "yes", 0, [], "True"])
def test_the_fixture_flag_must_be_a_bool(flag: Any) -> None:
    with pytest.raises(RegistryError, match="allow_fixture_only"):
        load_registry(F0_PATH, allow_fixture_only=flag)


def test_fixture_marking_is_by_the_rationale_prefix_or_the_source_prefix(
    tmp_path: Path,
) -> None:
    doc = unfixture(f0_doc())
    plain = load_doc(tmp_path, doc, allow_fixture_only=False)
    assert plain.fixture_only is False and plain.fixture_only_names() == ()
    entry_of(doc, "bp_band_low")["rationale"] = (
        FIXTURE_ONLY_MARKER + " row; illustrative, unverified"
    )
    with pytest.raises(RegistryError, match="bp_band_low"):
        load_doc(tmp_path, doc, allow_fixture_only=False)
    doc = unfixture(f0_doc())
    entry_of(doc, "bp_band_low")["source_ref"] = FIXTURE_ONLY_MARKER + " source"
    with pytest.raises(RegistryError, match="bp_band_low"):
        load_doc(tmp_path, doc, allow_fixture_only=False)
    doc = unfixture(f0_doc())
    entry_of(doc, "bp_band_low")["rationale"] = (
        "a note about FIXTURE-ONLY rows; illustrative, unverified"
    )
    assert load_doc(tmp_path, doc, allow_fixture_only=False).fixture_only is False


def test_the_registry_fixture_in_configs_loads_only_with_the_flag() -> None:
    with pytest.raises(RegistryError):
        load_registry(FIXTURE_REGISTRY_PATH)
    registry = load_registry(
        FIXTURE_REGISTRY_PATH, step_ms=STEP_MS, allow_fixture_only=True
    )
    assert registry.get("delta2").value == 10_800_000
    assert registry.bounds("bp") == PhysioBounds("bp", 50.0, 250.0)
    assert registry.fixture_only


def test_the_real_registry_has_no_fixture_row() -> None:
    assert load_registry(REAL_REGISTRY_PATH).fixture_only_names() == ()
    text = REAL_REGISTRY_PATH.read_text(encoding="utf-8")
    assert 'rationale: "FIXTURE-ONLY' not in text


# --- other loader rules -------------------------------------------------------------------


def test_entry_names_are_unique_across_entries_derived_and_unset(
    tmp_path: Path,
) -> None:
    doc = f0_doc()
    doc["entries"].append(dict(entry_of(doc, "bp_band_low")))
    with pytest.raises(RegistryError, match="bp_band_low"):
        load_doc(tmp_path, doc)
    doc = f0_doc()
    doc["unset"].append(
        {"parameter": "bp_band_low", "unit": "mmHg", "required_by": [], "note": "n"}
    )
    with pytest.raises(RegistryError, match="bp_band_low"):
        load_doc(tmp_path, doc)
    doc = f0_doc()
    doc["derived"].append(dict(doc["derived"][0]))
    with pytest.raises(RegistryError, match="max_latency_range"):
        load_doc(tmp_path, doc)
    doc = f0_doc()
    doc["derived"].append(
        {
            "name": "bp_band_low",
            "unit": "mmHg",
            "formula": "step_ms",
            "template": "range",
        }
    )
    with pytest.raises(RegistryError, match="bp_band_low"):
        load_doc(tmp_path, doc)
    doc = f0_doc()
    doc["entries"][0]["name"] = (
        "step_ms"  # a monitor-configuration name is not a registry name
    )
    with pytest.raises(RegistryError, match="step_ms"):
        load_doc(tmp_path, doc)


@pytest.mark.parametrize(
    ("name", "field", "value"),
    [
        ("scale_range", "value", 0.0),
        ("scale_range", "value", -20.0),
        ("scale_sched", "value", 0.0),
        ("scale_count", "value", -1.0),
        (
            "scale_range",
            "unit",
            "1",
        ),  # a scale is in mmHg, ms or dose, never a bare rank
        ("scale_sched", "unit", "1"),
        ("priority_hold", "value", 0.0),
        ("priority_hold", "value", -1.0),
        ("priority_hold", "value", 1.5),
        ("priority_range", "unit", "ms"),
        ("priority_range", "unit", "dose"),
    ],
)
def test_scale_and_priority_rules(
    tmp_path: Path, name: str, field: str, value: Any
) -> None:
    """03 section 2.5 rule 10 and section 2.6: scales are positive and carry a margin unit, priorities are
    integral ranks >= 1 with unit 1. That a scale has the unit of its own template is checked with the
    template table (test_templates.py)."""
    doc = f0_doc()
    entry_of(doc, name)[field] = value
    with pytest.raises(RegistryError, match=name):
        load_doc(tmp_path, doc)


def test_scale_and_priority_rules_accept_the_boundary_values(tmp_path: Path) -> None:
    doc = f0_doc()
    entry_of(doc, "priority_hold")["value"] = 1.0
    entry_of(doc, "scale_range")["value"] = 1e-300
    registry = load_doc(tmp_path, doc)
    assert as_priority(registry.get("priority_hold")) == 1
    assert registry.get("scale_range").value == 1e-300


@pytest.mark.parametrize(
    ("value", "valid"),
    [
        (60000.0, True),
        (0.0, True),
        (1.5, False),
        (-1.0, False),
        (-60000.0, False),
        (1e300, True),
    ],
)
def test_durations_are_non_negative_integral_milliseconds(
    tmp_path: Path, value: float, valid: bool
) -> None:
    doc = f0_doc()
    entry_of(doc, "cuff_inflation_min")["value"] = value
    if valid:
        assert load_doc(tmp_path, doc).get("cuff_inflation_min").value == value
    else:
        with pytest.raises(RegistryError, match="cuff_inflation_min"):
            load_doc(tmp_path, doc)


def test_pressures_and_doses_may_be_fractional_or_negative(tmp_path: Path) -> None:
    doc = f0_doc()
    entry_of(doc, "bp_band_low")["value"] = -2.5
    entry_of(doc, "dose_max_24h")["value"] = 0.5
    registry = load_doc(tmp_path, doc)
    assert registry.get("bp_band_low").value == -2.5
    assert registry.get("dose_max_24h").value == 0.5


@pytest.mark.parametrize(
    ("status", "reviewers", "unset", "ok"),
    [
        ("unreviewed", "none", False, True),
        ("unreviewed", "some", False, False),
        ("unreviewed", "all", False, False),
        ("partially_reviewed", "none", False, False),
        ("partially_reviewed", "some", False, True),
        ("partially_reviewed", "all", True, True),
        ("partially_reviewed", "all", False, False),
        ("reviewed", "all", False, True),
        ("reviewed", "all", True, False),
        ("reviewed", "some", False, False),
        ("reviewed", "none", False, False),
    ],
)
def test_review_status_must_agree_with_the_entries(
    tmp_path: Path, status: str, reviewers: str, unset: bool, ok: bool
) -> None:
    doc = f0_doc()
    if unset:
        make_unset(doc, "sched_window", ("sched",))
        doc["window_parameters"].remove("sched_window")
    for index, item in enumerate(doc["entries"]):
        marked = reviewers == "all" or (reviewers == "some" and index == 0)
        item["reviewed_by"] = "clinician-01" if marked else None
        if marked:
            item["rationale"] = "anchored"
    doc["review_status"] = status
    if ok:
        assert load_doc(tmp_path, doc).review_status == status
    else:
        with pytest.raises(RegistryError, match="review_status"):
            load_doc(tmp_path, doc)


def test_unreviewed_entries_are_accepted_and_reported_never_dropped(
    f0_registry: LoadedRegistry,
) -> None:
    names = f0_registry.unverified_names()
    assert len(names) == 29
    assert names[0] == "bp_band_low"  # the order of the file
    assert all(f0_registry.get(n).reviewed_by is None for n in names)


def test_unset_names_are_declared_but_have_no_value(tmp_path: Path) -> None:
    doc = f0_doc()
    make_unset(doc, "scale_hold", ("hold", "resp"))
    make_unset(doc, "priority_int", ("int",))
    registry = load_doc(tmp_path, doc)
    assert registry.unset_names() == ("scale_hold", "priority_int")
    assert registry.is_declared("scale_hold") and not registry.is_set("scale_hold")
    assert registry.is_set("scale_range")
    with pytest.raises(UnsetParameterError) as info:
        registry.get("scale_hold")
    assert isinstance(info.value, RegistryError)
    assert "scale_hold" in str(info.value)  # the name
    assert "'hold', 'resp'" in str(info.value)  # and the templates that need it
    with pytest.raises(RegistryError, match="no_such_name"):
        registry.is_set("no_such_name")
    assert registry.is_declared("no_such_name") is False
    assert registry.is_declared(None) is False  # type: ignore[arg-type]
    assert "scale_hold" not in registry.unverified_names()


def test_unset_never_returns_a_default(tmp_path: Path) -> None:
    doc = f0_doc()
    make_unset(doc, "scale_hold", ("hold",))
    registry = load_doc(tmp_path, doc)
    for call in (registry.get, registry.is_set):
        try:
            result = call("scale_hold")
        except UnsetParameterError:
            continue
        except RegistryError:  # is_set is a predicate: False is also honest
            continue
        assert result is False  # pragma: no cover


def test_overrides_are_parsed_and_validated(tmp_path: Path) -> None:
    doc = f0_doc()
    doc["overrides"] = [
        {
            "name": "bp_band_low",
            "min": 100.0,
            "max": 115.0,
            "rationale": "approved range",
            "source_ref": "review log",
            "reviewed_by": None,
        }
    ]
    registry = load_doc(tmp_path, doc)
    (override,) = registry.overrides()
    assert (override.name, override.min, override.max) == ("bp_band_low", 100.0, 115.0)
    for bad in (
        {"name": "no_such_name"},
        {"min": 120.0},  # min above max
        {"max": float("nan")},
        {"rationale": ""},
        {"extra": 1},
    ):
        broken = f0_doc()
        broken["overrides"] = [{**doc["overrides"][0], **bad}]
        with pytest.raises(RegistryError, match="overrides"):
            load_doc(tmp_path, broken)
    no_key = f0_doc()
    del no_key["overrides"]
    assert load_doc(tmp_path, no_key).overrides() == ()


def test_the_file_digest_is_the_sha256_of_the_bytes(
    f0_registry: LoadedRegistry,
) -> None:
    assert f0_registry.sha256 == hashlib.sha256(F0_PATH.read_bytes()).hexdigest()
    assert f0_registry.path == F0_PATH


def test_window_parameters_are_exposed(f0_registry: LoadedRegistry) -> None:
    assert f0_registry.window_parameters == WINDOW_NAMES


# --- casts (CP10) ------------------------------------------------------------------------


def test_as_duration_ms_casts_integral_durations(f0_registry: LoadedRegistry) -> None:
    value = as_duration_ms(f0_registry.get("delta2"))
    assert value == 10_800_000 and type(value) is int
    derived = as_duration_ms(f0_registry.get("max_latency_resp"))
    assert derived == 10_860_000 and type(derived) is int
    assert as_priority(f0_registry.get("priority_range")) == 2
    assert type(as_priority(f0_registry.get("priority_range"))) is int


def test_casts_refuse_what_is_not_a_duration_or_a_rank(
    f0_registry: LoadedRegistry,
) -> None:
    with pytest.raises(RegistryError, match="bp_band_low"):
        as_duration_ms(f0_registry.get("bp_band_low"))  # mmHg
    with pytest.raises(RegistryError):
        as_duration_ms(RegistryEntry("d", 1.5, "ms", "r", "s", None))
    with pytest.raises(RegistryError):
        as_duration_ms(RegistryEntry("d", float("nan"), "ms", "r", "s", None))
    with pytest.raises(RegistryError):
        as_duration_ms(RegistryEntry("d", -1.0, "ms", "r", "s", None))
    with pytest.raises(RegistryError):
        as_duration_ms("delta2")  # type: ignore[arg-type]
    with pytest.raises(RegistryError, match="scale_range"):
        as_priority(f0_registry.get("scale_range"))
    with pytest.raises(RegistryError):
        as_priority(RegistryEntry("p", 0.0, "1", "r", "s", None))
    with pytest.raises(RegistryError):
        as_priority(RegistryEntry("p", 1.5, "1", "r", "s", None))
    with pytest.raises(RegistryError):
        as_priority(None)  # type: ignore[arg-type]
