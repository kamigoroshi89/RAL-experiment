"""PriorSource contract, LiteraturePriorSource and the provenance table (WS04-T02).

All numbers below are arithmetic and fixture-only (see conftest.py): none is a clinical value.
"""

from __future__ import annotations

import ast
import dataclasses
import math
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st
from ralmon.benchmark.priors import (
    DIST_FAMILIES,
    FixtureOnlyPriorError,
    MissingProvenanceError,
    PriorConfigError,
    PriorError,
    UnfilledParameterError,
    load_prior_file,
    main,
    render_provenance_table,
)

from ralmon import benchmark
from ralmon.benchmark import (
    AdherenceParams,
    DeviceErrorModel,
    LiteraturePriorSource,
    ParamProvenance,
    PatientParams,
    PriorSource,
)

from .conftest import (
    FIXTURE_PARAMETERS,
    FIXTURE_REF,
    fixture_row,
    make_fixture_prior,
    unfilled_row,
)

ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "src"
BENCHMARK_SRC = SRC / "ralmon" / "benchmark"
STUB_ATTR = "__ralmon_stub_owner__"

CONTRACT_PATIENT_FIELDS = (
    "patient_id",
    "baseline_sbp_mmhg",
    "circadian_amplitude_mmhg",
    "ar_noise_sd_mmhg",
    "ar_noise_phi",
    "emax_mmhg",
    "ec50",
    "absorption_rate_per_h",
    "elimination_rate_per_h",
    "onset_delay_range_ms",
)
CONTRACT_ADHERENCE_FIELDS = ("p_delay", "p_omission", "p_double_take", "mean_delay_ms")
CONTRACT_DEVICE_FIELDS = (
    "cuff_error_sd_mmhg",
    "cuff_bias_mmhg",
    "dispenser_bounce_prob",
    "ble_dropout_rate_per_h",
)
CONTRACT_NUMERIC_NAMES = (
    CONTRACT_PATIENT_FIELDS[1:] + CONTRACT_ADHERENCE_FIELDS + CONTRACT_DEVICE_FIELDS
)
TABLE_COLUMNS = (
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


def prior(
    tmp_path: Path, *, strict: bool = True, **kwargs: Any
) -> LiteraturePriorSource:
    """A fixture-only source (the explicit flag is passed) built from make_fixture_prior."""
    path = make_fixture_prior(tmp_path, **kwargs)
    return LiteraturePriorSource(path, strict=strict, allow_fixture_only=True)


def fresh(tmp_path: Path, name: str) -> Path:
    """A new empty sub-directory, so one test can build several prior files."""
    sub = tmp_path / name
    sub.mkdir()
    return sub


def assert_config_error(
    tmp_path: Path, match: str | None = None, **kwargs: Any
) -> None:
    path = make_fixture_prior(tmp_path, **kwargs)
    with pytest.raises(PriorConfigError, match=match):
        LiteraturePriorSource(path, strict=False, allow_fixture_only=True)


# ---------------------------------------------------------------------------
# 1. Contract shapes
# ---------------------------------------------------------------------------


def test_dataclass_shapes_match_contract() -> None:
    expected = {
        ParamProvenance: ("name", "source_ref", "verified_by"),
        PatientParams: CONTRACT_PATIENT_FIELDS,
        AdherenceParams: CONTRACT_ADHERENCE_FIELDS,
        DeviceErrorModel: CONTRACT_DEVICE_FIELDS,
    }
    for cls, names in expected.items():
        assert tuple(f.name for f in dataclasses.fields(cls)) == names
        assert cls.__dataclass_params__.frozen is True  # type: ignore[attr-defined]
        assert hasattr(cls, "__slots__")
    for member in ("sample_patient", "adherence", "device_errors", "provenance"):
        assert callable(getattr(PriorSource, member))
    assert "name" in PriorSource.__annotations__
    # The public names are the real ones, not placeholders (WS05-T01 stubs removed).
    for cls in (
        PriorSource,
        LiteraturePriorSource,
        PatientParams,
        AdherenceParams,
        DeviceErrorModel,
        ParamProvenance,
    ):
        assert not hasattr(cls, STUB_ATTR)
    # The placeholder of another owner is untouched.
    assert getattr(benchmark.generate_benchmark, STUB_ATTR) == "WS04-T11"


def test_frozen_dataclasses_reject_assignment() -> None:
    p = ParamProvenance(name="x", source_ref="FIXTURE-ONLY", verified_by=None)
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.name = "y"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 2. Mandatory provenance
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_ref", ["", "   ", None])
@pytest.mark.parametrize("name", ["ec50", "baseline_sbp_mmhg", "p_delay"])
def test_missing_source_ref_fails_constructor(
    tmp_path: Path, name: str, bad_ref: str | None
) -> None:
    path = make_fixture_prior(tmp_path, row_updates={name: {"source_ref": bad_ref}})
    with pytest.raises(MissingProvenanceError, match=name):
        LiteraturePriorSource(path, strict=False, allow_fixture_only=True)


def test_missing_provenance_is_checked_even_when_status_says_awaiting(
    tmp_path: Path,
) -> None:
    updates = {"ec50": {"source_ref": "", "status": "awaiting_human_value"}}
    path = make_fixture_prior(tmp_path, row_updates=updates)
    with pytest.raises(MissingProvenanceError, match="ec50"):
        LiteraturePriorSource(path, strict=False, allow_fixture_only=True)


@pytest.mark.parametrize("key", ["source_type", "rationale"])
def test_filled_row_needs_source_type_and_rationale(tmp_path: Path, key: str) -> None:
    path = make_fixture_prior(tmp_path, row_updates={"ec50": {key: None}})
    with pytest.raises(MissingProvenanceError, match="ec50"):
        LiteraturePriorSource(path, strict=False, allow_fixture_only=True)


def test_missing_provenance_error_is_distinct_from_config_error() -> None:
    assert issubclass(MissingProvenanceError, PriorError)
    assert not issubclass(MissingProvenanceError, PriorConfigError)
    assert not issubclass(UnfilledParameterError, PriorConfigError)
    assert not issubclass(FixtureOnlyPriorError, PriorConfigError)


# ---------------------------------------------------------------------------
# 3. Provenance covers every numeric field
# ---------------------------------------------------------------------------


def test_every_contract_field_has_provenance_entry(tmp_path: Path) -> None:
    numeric = tuple(
        f.name
        for cls in (PatientParams, AdherenceParams, DeviceErrorModel)
        for f in dataclasses.fields(cls)
        if f.name != "patient_id"
    )
    assert numeric == CONTRACT_NUMERIC_NAMES
    source = prior(tmp_path)
    entries = source.provenance()
    assert all(isinstance(e, ParamProvenance) for e in entries)
    assert [e.name for e in entries] == list(numeric)  # one each, contract order
    assert all(e.source_ref.startswith("FIXTURE-ONLY") for e in entries)
    again = prior(fresh(tmp_path, "second"))
    assert source.provenance() == again.provenance()


def test_provenance_order_does_not_follow_file_order(tmp_path: Path) -> None:
    path = make_fixture_prior(tmp_path)
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    document["parameters"].reverse()
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    source = LiteraturePriorSource(path, allow_fixture_only=True)
    assert [e.name for e in source.provenance()] == list(CONTRACT_NUMERIC_NAMES)


def test_provenance_of_unfilled_row_never_invents_a_source(tmp_path: Path) -> None:
    source = prior(tmp_path, strict=False, unfilled=["ec50"])
    entry = {e.name: e for e in source.provenance()}["ec50"]
    assert entry.source_ref == "awaiting_human_value"
    assert entry.verified_by is None


# ---------------------------------------------------------------------------
# 4. Unfilled parameters
# ---------------------------------------------------------------------------


def test_unfilled_parameter_raises_on_use(tmp_path: Path) -> None:
    source = prior(tmp_path, strict=False, unfilled=["ec50", "emax_mmhg", "p_delay"])
    assert source.unfilled_names() == ("ec50", "emax_mmhg", "p_delay")
    with pytest.raises(UnfilledParameterError) as info:
        source.sample_patient(np.random.default_rng(0), 0)
    assert "ec50" in str(info.value) and "emax_mmhg" in str(info.value)
    assert "p_delay" not in str(info.value)  # not needed by a patient draw
    with pytest.raises(UnfilledParameterError, match="p_delay"):
        source.adherence()
    source.device_errors()  # every device row is filled: no error


def test_unfilled_rows_of_another_group_do_not_block_a_use(tmp_path: Path) -> None:
    source = prior(tmp_path, strict=False, unfilled=["cuff_bias_mmhg"])
    source.sample_patient(np.random.default_rng(0), 3)
    source.adherence()
    with pytest.raises(UnfilledParameterError, match="cuff_bias_mmhg"):
        source.device_errors()


def test_strict_true_raises_at_construction(tmp_path: Path) -> None:
    path = make_fixture_prior(tmp_path, unfilled=["ec50", "p_delay"])
    with pytest.raises(UnfilledParameterError) as info:
        LiteraturePriorSource(path, strict=True, allow_fixture_only=True)
    assert "ec50" in str(info.value) and "p_delay" in str(info.value)
    # strict is the default
    with pytest.raises(UnfilledParameterError):
        LiteraturePriorSource(path, allow_fixture_only=True)
    # nothing unfilled: strict passes and nothing is listed
    assert prior(fresh(tmp_path, "ok")).unfilled_names() == ()


def test_null_versus_missing_value_keys(tmp_path: Path) -> None:
    for key in ("value", "dist", "source_ref", "source_type", "verified_by", "note"):
        assert_config_error(
            fresh(tmp_path, key), match="ec50", row_updates={"ec50": {key: "<DELETE>"}}
        )


def test_status_must_agree_with_value(tmp_path: Path) -> None:
    sub = fresh(tmp_path, "a")
    assert_config_error(sub, match="ec50", row_updates={"ec50": {"value": None}})
    sub = fresh(tmp_path, "b")
    updates = {"ec50": {"status": "awaiting_human_value"}}
    assert_config_error(sub, match="ec50", row_updates=updates)
    sub = fresh(tmp_path, "c")
    unfilled = {"ec50": {"verified_by": "someone"}}
    assert_config_error(sub, match="ec50", unfilled=["ec50"], row_updates=unfilled)
    sub = fresh(tmp_path, "d")
    assert_config_error(sub, match="ec50", row_updates={"ec50": {"status": "done"}})


def test_zero_is_a_value_not_a_missing_value(tmp_path: Path) -> None:
    source = prior(tmp_path, row_updates={"cuff_bias_mmhg": {"value": 0.0}})
    assert source.device_errors().cuff_bias_mmhg == 0.0
    assert source.unfilled_names() == ()


# ---------------------------------------------------------------------------
# 5. Verification state
# ---------------------------------------------------------------------------


def test_unverified_names_reported(tmp_path: Path) -> None:
    verified = {name: {"verified_by": "H. Reviewer"} for name in FIXTURE_PARAMETERS}
    for name in ("p_omission", "baseline_sbp_mmhg"):
        verified[name] = {"verified_by": None}
    source = prior(tmp_path, row_updates=verified)
    assert source.unverified_names() == ("baseline_sbp_mmhg", "p_omission")
    assert {e.name for e in source.provenance() if e.verified_by is None} == {
        "baseline_sbp_mmhg",
        "p_omission",
    }
    sub = fresh(tmp_path, "all")
    everything = {name: {"verified_by": "H. Reviewer"} for name in FIXTURE_PARAMETERS}
    assert prior(sub, row_updates=everything).unverified_names() == ()


def test_unfilled_rows_are_unfilled_not_unverified(tmp_path: Path) -> None:
    source = prior(tmp_path, strict=False, unfilled=["ec50"])
    assert "ec50" in source.unfilled_names()
    assert "ec50" not in source.unverified_names()


@pytest.mark.parametrize("verified_by", ["", "  ", 3, True])
def test_verified_by_must_be_none_or_a_name(tmp_path: Path, verified_by: Any) -> None:
    assert_config_error(
        tmp_path, match="ec50", row_updates={"ec50": {"verified_by": verified_by}}
    )


# ---------------------------------------------------------------------------
# 6. Fixture-only priors
# ---------------------------------------------------------------------------


def test_fixture_only_prior_rejected_by_default(tmp_path: Path) -> None:
    path = make_fixture_prior(tmp_path)
    with pytest.raises(FixtureOnlyPriorError):
        LiteraturePriorSource(path)
    with pytest.raises(FixtureOnlyPriorError):
        LiteraturePriorSource(path, allow_fixture_only=False)
    source = LiteraturePriorSource(path, allow_fixture_only=True)
    assert source.name.endswith("-FIXTURE-ONLY")
    assert source.fixture_only is True
    assert all(e.source_ref.startswith("FIXTURE-ONLY") for e in source.provenance())


def test_fixture_suffix_is_not_doubled(tmp_path: Path) -> None:
    source = prior(tmp_path, name="x-FIXTURE-ONLY")
    assert source.name == "x-FIXTURE-ONLY"


def test_fixture_only_rows_cannot_hide_in_a_real_prior(tmp_path: Path) -> None:
    sub = fresh(tmp_path, "a")
    path = make_fixture_prior(sub, fixture_only=False)  # rows still say fixture_only
    with pytest.raises(PriorConfigError, match="fixture_only"):
        LiteraturePriorSource(path, allow_fixture_only=True)
    sub = fresh(tmp_path, "b")
    # a fixture file whose row cites a real-looking source: refused
    assert_config_error(
        sub, match="ec50", row_updates={"ec50": {"source_ref": "a real citation"}}
    )
    sub = fresh(tmp_path, "c")
    assert_config_error(
        sub, match="ec50", row_updates={"ec50": {"source_type": "standard"}}
    )


def test_real_prior_flag_does_not_need_the_fixture_switch(tmp_path: Path) -> None:
    updates = {
        name: {"source_ref": "a named source", "source_type": "design_choice"}
        for name in FIXTURE_PARAMETERS
    }
    path = make_fixture_prior(tmp_path, fixture_only=False, row_updates=updates)
    source = LiteraturePriorSource(path)
    assert source.fixture_only is False
    assert not source.name.endswith("-FIXTURE-ONLY")


@pytest.mark.parametrize("flag", ["yes", 1, None])
def test_fixture_only_flag_must_be_boolean(tmp_path: Path, flag: Any) -> None:
    assert_config_error(tmp_path, top_level={"fixture_only": flag})


# ---------------------------------------------------------------------------
# 7. Sampling is deterministic
# ---------------------------------------------------------------------------


def test_sample_patient_deterministic_given_generator(tmp_path: Path) -> None:
    source = prior(tmp_path)
    a = source.sample_patient(np.random.default_rng(7), 12)
    b = source.sample_patient(np.random.default_rng(7), 12)
    c = source.sample_patient(np.random.default_rng(8), 12)
    assert a == b
    assert a.baseline_sbp_mmhg != c.baseline_sbp_mmhg
    assert a.patient_id == "p0012" == c.patient_id
    assert isinstance(a.onset_delay_range_ms, tuple)
    assert all(isinstance(x, int) for x in a.onset_delay_range_ms)


def test_patient_id_is_a_pure_function_of_the_index(tmp_path: Path) -> None:
    source = prior(tmp_path)
    ids = [
        source.sample_patient(np.random.default_rng(i), i).patient_id
        for i in (0, 7, 199)
    ]
    assert ids == ["p0000", "p0007", "p0199"]
    assert source.sample_patient(np.random.default_rng(1), 12345).patient_id == "p12345"
    for bad in (-1, True, 1.5):
        with pytest.raises(ValueError, match="patient_index"):
            source.sample_patient(np.random.default_rng(0), bad)  # type: ignore[arg-type]


def test_constant_rows_consume_no_randomness_and_each_dist_row_one_draw(
    tmp_path: Path,
) -> None:
    source = prior(tmp_path)  # one dist row (uniform baseline), the others constant
    rng = np.random.default_rng(3)
    patient = source.sample_patient(rng, 0)
    reference = np.random.default_rng(3)
    u = reference.random()
    assert rng.random() == reference.random()  # exactly one uniform was consumed
    assert patient.baseline_sbp_mmhg == pytest.approx(90.0 + u * (110.0 - 90.0))
    assert patient.circadian_amplitude_mmhg == 10.0
    assert patient.onset_delay_range_ms == (3_600_000, 7_200_000)


def test_adherence_and_device_errors_return_the_file_values(tmp_path: Path) -> None:
    source = prior(tmp_path)
    assert source.adherence() == AdherenceParams(0.25, 0.125, 0.0625, 600_000)
    assert source.device_errors() == DeviceErrorModel(4.0, 0.0, 0.125, 0.5)


# ---------------------------------------------------------------------------
# 8. Truncation
# ---------------------------------------------------------------------------

_TRUNCATED_FAMILIES: dict[str, Callable[[float, float], dict[str, Any]]] = {
    "constant": lambda lo, hi: {
        "family": "constant",
        "value": (lo + hi) / 2.0,
        "truncate": {"lo": lo, "hi": hi},
    },
    "uniform": lambda lo, hi: {
        "family": "uniform",
        "lo": lo - 1.0,
        "hi": hi + 1.0,
        "truncate": {"lo": lo, "hi": hi},
    },
    "normal": lambda lo, hi: {
        "family": "normal",
        "mean": (lo + hi) / 2.0,
        "sd": 5.0,
        "truncate": {"lo": lo, "hi": hi},
    },
    "lognormal": lambda lo, hi: {
        "family": "lognormal",
        "log_mean": math.log((lo + hi) / 2.0),
        "log_sd": 1.0,
        "truncate": {"lo": lo, "hi": hi},
    },
}


@pytest.mark.parametrize("family", sorted(_TRUNCATED_FAMILIES))
def test_sample_patient_respects_truncation(tmp_path: Path, family: str) -> None:
    lo, hi = 95.0, 100.0
    dist = _TRUNCATED_FAMILIES[family](lo, hi)
    source = prior(tmp_path, row_updates={"baseline_sbp_mmhg": {"dist": dist}})
    rng = np.random.default_rng(0)
    draws = [source.sample_patient(rng, i).baseline_sbp_mmhg for i in range(1000)]
    assert all(lo <= x <= hi for x in draws)
    if family != "constant":
        assert len(set(draws)) > 900


@settings(max_examples=25, deadline=None)
@given(
    family=st.sampled_from(sorted(_TRUNCATED_FAMILIES)),
    lo=st.floats(min_value=1.0, max_value=200.0),
    width=st.floats(min_value=0.01, max_value=100.0),
    seed=st.integers(min_value=0, max_value=1000),
)
def test_truncation_holds_for_random_bounds(
    family: str, lo: float, width: float, seed: int
) -> None:
    hi = lo + width
    dist = _TRUNCATED_FAMILIES[family](lo, hi)
    with tempfile.TemporaryDirectory() as tmp:
        source = prior(Path(tmp), row_updates={"baseline_sbp_mmhg": {"dist": dist}})
        rng = np.random.default_rng(seed)
        for i in range(40):
            assert lo <= source.sample_patient(rng, i).baseline_sbp_mmhg <= hi


@pytest.mark.parametrize(
    ("dist", "why"),
    [
        (
            {
                "family": "uniform",
                "lo": 90.0,
                "hi": 110.0,
                "truncate": {"lo": 100.0, "hi": 100.0},
            },
            "equal bounds",
        ),
        (
            {
                "family": "uniform",
                "lo": 90.0,
                "hi": 110.0,
                "truncate": {"lo": 105.0, "hi": 100.0},
            },
            "inverted bounds",
        ),
        (
            {
                "family": "uniform",
                "lo": 90.0,
                "hi": 110.0,
                "truncate": {"lo": 120.0, "hi": 130.0},
            },
            "no overlap",
        ),
        (
            {"family": "uniform", "lo": 90.0, "hi": 110.0, "truncate": {"lo": 110.0}},
            "touching only",
        ),
        (
            {"family": "constant", "value": 100.0, "truncate": {"lo": 101.0}},
            "constant outside",
        ),
        (
            {
                "family": "normal",
                "mean": 100.0,
                "sd": 1.0,
                "truncate": {"lo": 1000.0, "hi": 1001.0},
            },
            "no mass",
        ),
        (
            {"family": "normal", "mean": 100.0, "sd": 1.0, "truncate": {}},
            "empty truncate",
        ),
        (
            {
                "family": "normal",
                "mean": 100.0,
                "sd": 1.0,
                "truncate": {"lo": 95.0, "hi": 99.0, "mid": 1.0},
            },
            "unknown key",
        ),
        (
            {"family": "normal", "mean": 100.0, "sd": 1.0, "truncate": [95.0, 99.0]},
            "not a mapping",
        ),
        (
            {
                "family": "lognormal",
                "log_mean": 0.0,
                "log_sd": 1.0,
                "truncate": {"hi": 0.0},
            },
            "below support",
        ),
    ],
)
def test_bad_truncation_is_rejected(
    tmp_path: Path, dist: dict[str, Any], why: str
) -> None:
    assert_config_error(tmp_path, row_updates={"baseline_sbp_mmhg": {"dist": dist}})


def test_truncation_with_one_bound_only(tmp_path: Path) -> None:
    dist = {"family": "normal", "mean": 100.0, "sd": 10.0, "truncate": {"lo": 95.0}}
    source = prior(tmp_path, row_updates={"baseline_sbp_mmhg": {"dist": dist}})
    rng = np.random.default_rng(1)
    assert all(
        source.sample_patient(rng, i).baseline_sbp_mmhg >= 95.0 for i in range(200)
    )


def test_zero_sd_normal_is_a_constant(tmp_path: Path) -> None:
    dist = {"family": "normal", "mean": 100.0, "sd": 0.0}
    source = prior(tmp_path, row_updates={"baseline_sbp_mmhg": {"dist": dist}})
    assert source.sample_patient(np.random.default_rng(0), 0).baseline_sbp_mmhg == 100.0


# ---------------------------------------------------------------------------
# 9. Distribution families and domains
# ---------------------------------------------------------------------------


def test_distribution_family_allow_list(tmp_path: Path) -> None:
    assert set(DIST_FAMILIES) == {"constant", "uniform", "normal", "lognormal"}
    good = [
        {"family": "constant", "value": 100.0},
        {"family": "uniform", "lo": 90.0, "hi": 110.0},
        {"family": "normal", "mean": 100.0, "sd": 5.0, "truncate": {"lo": 80.0}},
        {"family": "lognormal", "log_mean": 4.0, "log_sd": 0.25},
    ]
    for i, dist in enumerate(good):
        sub = fresh(tmp_path, f"good{i}")
        source = prior(sub, row_updates={"baseline_sbp_mmhg": {"dist": dist}})
        assert (
            source.sample_patient(np.random.default_rng(0), 0).baseline_sbp_mmhg > 0.0
        )
    for i, family in enumerate(["beta", "exponential", "Normal", "", None, 3]):
        sub = fresh(tmp_path, f"bad{i}")
        dist = {"family": family, "mean": 100.0, "sd": 5.0}
        assert_config_error(
            sub, match="family", row_updates={"baseline_sbp_mmhg": {"dist": dist}}
        )


@pytest.mark.parametrize(
    "dist",
    [
        {"family": "uniform", "lo": 110.0, "hi": 90.0},
        {"family": "uniform", "lo": 100.0, "hi": 100.0},
        {"family": "normal", "mean": 100.0, "sd": -1.0},
        {"family": "lognormal", "log_mean": 4.0, "log_sd": -0.5},
        {"family": "uniform", "lo": 90.0},
        {"family": "uniform", "lo": 90.0, "hi": 110.0, "sd": 1.0},
        {"family": "normal", "mean": "100", "sd": 1.0},
        {"family": "normal", "mean": True, "sd": 1.0},
        {"family": "normal", "mean": float("nan"), "sd": 1.0},
        {"family": "uniform", "lo": 90.0, "hi": float("inf")},
        {"mean": 100.0, "sd": 1.0},
        "normal",
        [1, 2],
    ],
)
def test_distribution_parameters_are_validated(tmp_path: Path, dist: Any) -> None:
    assert_config_error(tmp_path, row_updates={"baseline_sbp_mmhg": {"dist": dist}})


def test_value_and_dist_together_are_rejected(tmp_path: Path) -> None:
    both = {"value": 100.0, "dist": {"family": "constant", "value": 100.0}}
    assert_config_error(
        tmp_path, match="baseline_sbp_mmhg", row_updates={"baseline_sbp_mmhg": both}
    )


def test_dist_is_allowed_only_for_patient_rows(tmp_path: Path) -> None:
    dist = {"family": "constant", "value": 0.25}
    assert_config_error(
        tmp_path,
        match="p_delay",
        row_updates={"p_delay": {"value": None, "dist": dist}},
    )


@pytest.mark.parametrize(
    ("name", "dist"),
    [
        # an untruncated normal can leave the physical domain of the field
        ("baseline_sbp_mmhg", {"family": "normal", "mean": 100.0, "sd": 5.0}),
        ("ar_noise_sd_mmhg", {"family": "uniform", "lo": -1.0, "hi": 1.0}),
        ("ec50", {"family": "uniform", "lo": 0.0, "hi": 1.0}),  # EC50 must be > 0
        ("ar_noise_phi", {"family": "uniform", "lo": -0.5, "hi": 1.0}),
        ("ar_noise_phi", {"family": "uniform", "lo": -1.0, "hi": 0.5}),
        ("ar_noise_phi", {"family": "normal", "mean": 0.0, "sd": 0.25}),
    ],
)
def test_distribution_support_must_lie_in_the_field_domain(
    tmp_path: Path, name: str, dist: dict[str, Any]
) -> None:
    assert_config_error(
        tmp_path, match=name, row_updates={name: {"dist": dist, "value": None}}
    )


def test_support_inside_the_domain_is_accepted(tmp_path: Path) -> None:
    updates = {
        "ar_noise_phi": {
            "dist": {"family": "uniform", "lo": -0.5, "hi": 0.5},
            "value": None,
        },
        "ec50": {
            "dist": {"family": "lognormal", "log_mean": 0.0, "log_sd": 0.5},
            "value": None,
        },
        "ar_noise_sd_mmhg": {
            "dist": {"family": "uniform", "lo": 0.0, "hi": 1.0},
            "value": None,
        },
    }
    source = prior(tmp_path, row_updates=updates)
    p = source.sample_patient(np.random.default_rng(0), 0)
    assert (
        -0.5 <= p.ar_noise_phi <= 0.5
        and p.ec50 > 0.0
        and 0.0 <= p.ar_noise_sd_mmhg <= 1.0
    )


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("baseline_sbp_mmhg", 0.0),
        ("circadian_amplitude_mmhg", -1.0),
        ("ar_noise_sd_mmhg", -0.5),
        ("ar_noise_phi", 1.0),
        ("ar_noise_phi", -1.0),
        ("ec50", 0.0),
        ("absorption_rate_per_h", 0.0),
        ("elimination_rate_per_h", -2.0),
        ("cuff_error_sd_mmhg", -1.0),
        ("ble_dropout_rate_per_h", -0.5),
        ("mean_delay_ms", -1),
        ("mean_delay_ms", 1.5),
        ("emax_mmhg", float("nan")),
        ("emax_mmhg", float("inf")),
        ("emax_mmhg", "20"),
        ("emax_mmhg", True),
    ],
)
def test_scalar_domains_are_validated(tmp_path: Path, name: str, value: Any) -> None:
    assert_config_error(tmp_path, match=name, row_updates={name: {"value": value}})


def test_domain_boundaries_that_are_allowed(tmp_path: Path) -> None:
    updates = {
        "circadian_amplitude_mmhg": {"value": 0.0},
        "ar_noise_sd_mmhg": {"value": 0.0},
        "ar_noise_phi": {"value": 0.0},
        "cuff_error_sd_mmhg": {"value": 0.0},
        "cuff_bias_mmhg": {"value": -2.0},
        "mean_delay_ms": {"value": 0},
        "ble_dropout_rate_per_h": {"value": 0.0},
        "emax_mmhg": {"value": -20.0},
    }
    source = prior(tmp_path, row_updates=updates)
    assert source.adherence().mean_delay_ms == 0
    assert source.device_errors().cuff_bias_mmhg == -2.0


@pytest.mark.parametrize(
    "onset",
    [
        {"lower_ms": 7_200_000, "upper_ms": 3_600_000},
        {"lower_ms": -1, "upper_ms": 5},
        {"lower_ms": 1.5, "upper_ms": 5},
        {"lower_ms": 1},
        {"lower_ms": 1, "upper_ms": 2, "mid_ms": 1},
        [1, 2],
        3_600_000,
    ],
)
def test_onset_delay_range_is_validated(tmp_path: Path, onset: Any) -> None:
    assert_config_error(
        tmp_path,
        match="onset_delay_range_ms",
        row_updates={"onset_delay_range_ms": {"value": onset}},
    )


def test_onset_delay_range_boundaries(tmp_path: Path) -> None:
    equal = {"onset_delay_range_ms": {"value": {"lower_ms": 0, "upper_ms": 0}}}
    source = prior(tmp_path, row_updates=equal)
    assert source.sample_patient(np.random.default_rng(0), 0).onset_delay_range_ms == (
        0,
        0,
    )
    dist = {"family": "constant", "value": 1.0}
    assert_config_error(
        fresh(tmp_path, "x"),
        match="onset_delay_range_ms",
        row_updates={"onset_delay_range_ms": {"value": None, "dist": dist}},
    )


@pytest.mark.parametrize(
    ("name", "wrong_unit"),
    [
        ("baseline_sbp_mmhg", "kPa"),
        ("ar_noise_phi", "mmHg"),
        ("p_delay", "%"),
        ("mean_delay_ms", "min"),
        ("absorption_rate_per_h", "1/min"),
        ("ble_dropout_rate_per_h", "1/s"),
        ("cuff_error_sd_mmhg", ""),
        ("ec50", None),
    ],
)
def test_unit_mismatch_is_rejected(tmp_path: Path, name: str, wrong_unit: Any) -> None:
    assert_config_error(tmp_path, match=name, row_updates={name: {"unit": wrong_unit}})


def test_unit_is_checked_on_unfilled_rows_too(tmp_path: Path) -> None:
    assert_config_error(
        tmp_path,
        match="p_delay",
        unfilled=["p_delay"],
        row_updates={"p_delay": {"unit": "%"}},
    )


# ---------------------------------------------------------------------------
# 10. Probabilities
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name", ["p_delay", "p_omission", "p_double_take", "dispenser_bounce_prob"]
)
@pytest.mark.parametrize("value", [-0.0625, 1.0625, 2.0, float("nan")])
def test_probability_fields_validated(tmp_path: Path, name: str, value: float) -> None:
    assert_config_error(tmp_path, match=name, row_updates={name: {"value": value}})


@pytest.mark.parametrize(
    "name", ["p_delay", "p_omission", "p_double_take", "dispenser_bounce_prob"]
)
@pytest.mark.parametrize("value", [0.0, 1.0])
def test_probability_boundaries_zero_and_one_are_allowed(
    tmp_path: Path, name: str, value: float
) -> None:
    updates = {n: {"value": 0.0} for n in ("p_delay", "p_omission", "p_double_take")}
    updates[name] = {"value": value}
    source = prior(tmp_path, row_updates=updates)
    assert source.unfilled_names() == ()


def test_adherence_probabilities_may_sum_to_exactly_one_but_not_more(
    tmp_path: Path,
) -> None:
    def updates(a: float, b: float, c: float) -> dict[str, dict[str, Any]]:
        return {
            "p_delay": {"value": a},
            "p_omission": {"value": b},
            "p_double_take": {"value": c},
        }

    source = prior(tmp_path, row_updates=updates(0.5, 0.25, 0.25))
    assert source.adherence().p_delay == 0.5
    sub = fresh(tmp_path, "over")
    assert_config_error(sub, match="p_delay", row_updates=updates(0.5, 0.25, 0.3125))
    sub = fresh(tmp_path, "partial")
    # one row unfilled: the filled ones already exceed 1, so the file is still refused
    partial = updates(0.75, 0.5, 0.0)
    assert_config_error(
        sub, match="p_delay", unfilled=["p_double_take"], row_updates=partial
    )


# ---------------------------------------------------------------------------
# 11. Autoregressive reference step
# ---------------------------------------------------------------------------


def test_ar_reference_step_required(tmp_path: Path) -> None:
    source = prior(tmp_path)
    assert source.reference_step_ms("ar_noise_phi") == 60_000
    bad_updates: list[dict[str, Any]] = [
        {"reference_step_ms": "<DELETE>"},
        {"reference_step_ms": None},
        {"reference_step_ms": 0},
        {"reference_step_ms": -60_000},
        {"reference_step_ms": 1.5},
        {"reference_step_ms": 60_000.0 + 0.5},
        {"reference_step_ms": True},
        {"reference_step_ms": "60000"},
    ]
    for i, update in enumerate(bad_updates):
        sub = fresh(tmp_path, f"bad{i}")
        assert_config_error(
            sub, match="ar_noise_phi", row_updates={"ar_noise_phi": update}
        )


def test_reference_step_may_be_null_only_while_the_row_is_unfilled(
    tmp_path: Path,
) -> None:
    source = prior(tmp_path, strict=False, unfilled=["ar_noise_phi"])
    with pytest.raises(UnfilledParameterError, match="ar_noise_phi"):
        source.reference_step_ms("ar_noise_phi")
    sub = fresh(tmp_path, "missing")
    # the key itself must exist even on an unfilled row (null versus missing)
    assert_config_error(
        sub,
        match="ar_noise_phi",
        unfilled=["ar_noise_phi"],
        row_updates={"ar_noise_phi": {"reference_step_ms": "<DELETE>"}},
    )


def test_reference_step_of_another_parameter_is_an_error(tmp_path: Path) -> None:
    source = prior(tmp_path)
    with pytest.raises(PriorConfigError, match="ec50"):
        source.reference_step_ms("ec50")
    with pytest.raises(PriorConfigError, match="nonsense"):
        source.reference_step_ms("nonsense")


# ---------------------------------------------------------------------------
# File structure
# ---------------------------------------------------------------------------


def test_structural_errors_are_config_errors(tmp_path: Path) -> None:
    names = ("dup", "unknown", "missing", "rowkey", "top", "task", "stype")
    sub = {name: fresh(tmp_path, name) for name in names}
    # duplicate row
    assert_config_error(sub["dup"], match="ec50", extra_rows=[fixture_row("ec50")])
    # a row that is not a contract field belongs to generator_design.yaml
    assert_config_error(
        sub["unknown"],
        match="circadian_phase",
        extra_rows=[{**fixture_row("ec50"), "parameter": "circadian_phase"}],
    )
    # a contract field without a row
    assert_config_error(sub["missing"], match="ec50", drop=["ec50"])
    # an unknown key in a row
    assert_config_error(
        sub["rowkey"], match="colour", row_updates={"ec50": {"colour": "red"}}
    )
    # an unknown top-level key
    assert_config_error(sub["top"], match="extra", top_level={"extra": 1})
    assert_config_error(
        sub["task"], match="ec50", row_updates={"ec50": {"consumer_task": "T04"}}
    )
    assert_config_error(
        sub["stype"], match="ec50", row_updates={"ec50": {"source_type": "hearsay"}}
    )


@pytest.mark.parametrize(
    "content",
    ["", "   \n", "# only a comment\n", "[]\n", "- a\n", "42\n", "parameters: []\n"],
)
def test_empty_or_malformed_file_is_rejected(tmp_path: Path, content: str) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(PriorConfigError):
        LiteraturePriorSource(path, strict=False, allow_fixture_only=True)


def test_yaml_syntax_error_and_duplicate_keys_are_config_errors(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("a: [unclosed\n", encoding="utf-8")
    with pytest.raises(PriorConfigError):
        LiteraturePriorSource(path, strict=False, allow_fixture_only=True)
    good = make_fixture_prior(tmp_path)
    text = good.read_text(encoding="utf-8").replace(
        "fixture_only: true", "fixture_only: true\nfixture_only: false", 1
    )
    dup = tmp_path / "dup.yaml"
    dup.write_text(text, encoding="utf-8")
    with pytest.raises(PriorConfigError, match="duplicate"):
        LiteraturePriorSource(dup, strict=False, allow_fixture_only=True)


def test_missing_file_is_a_config_error(tmp_path: Path) -> None:
    with pytest.raises(PriorConfigError, match="nope.yaml"):
        LiteraturePriorSource(tmp_path / "nope.yaml")


def test_parameters_must_be_a_list_of_mappings(tmp_path: Path) -> None:
    assert_config_error(tmp_path, top_level={"parameters": {"ec50": {}}})
    sub = fresh(tmp_path, "b")
    assert_config_error(sub, top_level={"parameters": ["ec50"]})


# ---------------------------------------------------------------------------
# 12. Provenance table
# ---------------------------------------------------------------------------

HEADER = (
    "# Parameter provenance (test copy)\n\nHand-written text that must survive.\n\n"
)
FOOTER = "\nHand-written trailer.\n"


def make_root(tmp_path: Path, *, prior_kwargs: dict[str, Any] | None = None) -> Path:
    """A repository-shaped tree with a fixture prior and a table with markers."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    root = tmp_path / "repo"
    (root / "configs" / "priors").mkdir(parents=True)
    (root / "docs" / "benchmark").mkdir(parents=True)
    source = make_fixture_prior(tmp_path, **(prior_kwargs or {}), filename="src.yaml")
    (root / "configs" / "priors" / "literature_hypertension.yaml").write_text(
        source.read_text(encoding="utf-8"), encoding="utf-8"
    )
    table = HEADER + "<!-- BEGIN GENERATED -->\n<!-- END GENERATED -->\n" + FOOTER
    (root / "docs" / "benchmark" / "parameter-provenance.md").write_text(
        table, encoding="utf-8"
    )
    return root


def table_path(root: Path) -> Path:
    return root / "docs" / "benchmark" / "parameter-provenance.md"


def prior_path(root: Path) -> Path:
    return root / "configs" / "priors" / "literature_hypertension.yaml"


def table_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("| ")]


def split_cells(line: str) -> list[str]:
    return [c.strip() for c in re.split(r"(?<!\\)\|", line.strip())[1:-1]]


def test_provenance_table_is_deterministic_and_complete(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    parsed = load_prior_file(prior_path(root))
    first = render_provenance_table([parsed], root=root)
    assert first == render_provenance_table([parsed], root=root)
    lines = table_lines(first)
    assert tuple(split_cells(lines[0])) == TABLE_COLUMNS
    assert len(lines) == 1 + len(CONTRACT_NUMERIC_NAMES)  # header plus one row each
    names = [split_cells(line)[0] for line in lines[1:]]
    assert names == list(CONTRACT_NUMERIC_NAMES)
    ec50 = split_cells(lines[1 + CONTRACT_NUMERIC_NAMES.index("ec50")])
    assert ec50[1] == "PatientParams.ec50"
    assert ec50[2] == "1" and ec50[4] == FIXTURE_REF and ec50[5] == "fixture_only"
    assert ec50[7] == "filled" and ec50[8] == "WS04-T04"
    assert first.endswith("\n")


def test_table_shows_unfilled_rows_honestly(tmp_path: Path) -> None:
    root = make_root(tmp_path, prior_kwargs={"unfilled": ["ec50", "p_delay"]})
    text = render_provenance_table([load_prior_file(prior_path(root))], root=root)
    rows = {split_cells(line)[0]: split_cells(line) for line in table_lines(text)[1:]}
    assert rows["ec50"][3] == "-" and rows["ec50"][7] == "awaiting_human_value"
    assert rows["ec50"][4] == "-" and rows["ec50"][6] == "-"
    assert "awaiting_human_value: 2" in text
    assert "filled: 15" in text


def test_table_cells_escape_pipes_and_newlines(tmp_path: Path) -> None:
    note = "a | b\nsecond line"
    root = make_root(tmp_path, prior_kwargs={"row_updates": {"ec50": {"note": note}}})
    text = render_provenance_table([load_prior_file(prior_path(root))], root=root)
    line = next(line for line in table_lines(text) if line.startswith("| ec50 "))
    assert len(split_cells(line)) == len(TABLE_COLUMNS)
    assert "a \\| b second line" in line


def test_table_notes_carry_the_rationale(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    text = render_provenance_table([load_prior_file(prior_path(root))], root=root)
    line = next(line for line in table_lines(text) if line.startswith("| ec50 "))
    assert "FIXTURE-ONLY arithmetic value" in line


def test_write_and_check_table_round_trip(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = make_root(tmp_path)
    assert main(["--root", str(root), "--check-table"]) == 1  # empty region is stale
    assert main(["--root", str(root), "--write-table"]) == 0
    first = table_path(root).read_bytes()
    assert main(["--root", str(root), "--check-table"]) == 0
    assert main(["--root", str(root), "--write-table"]) == 0
    assert table_path(root).read_bytes() == first  # regeneration is byte-identical
    text = first.decode("utf-8")
    assert text.startswith(HEADER) and text.endswith(
        FOOTER
    )  # hand-written text untouched
    assert len(table_lines(text)) == 1 + len(CONTRACT_NUMERIC_NAMES)
    capsys.readouterr()


def test_check_table_fails_when_the_yaml_changed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = make_root(tmp_path)
    assert main(["--root", str(root), "--write-table"]) == 0
    assert main(["--root", str(root), "--check-table"]) == 0
    document = yaml.safe_load(prior_path(root).read_text(encoding="utf-8"))
    for row in document["parameters"]:
        if row["parameter"] == "ec50":
            row["value"] = 3.0
    prior_path(root).write_text(
        yaml.safe_dump(document, sort_keys=False), encoding="utf-8"
    )
    capsys.readouterr()
    assert main(["--root", str(root), "--check-table"]) == 1
    assert "stale" in capsys.readouterr().err
    assert main(["--root", str(root), "--write-table"]) == 0
    assert main(["--root", str(root), "--check-table"]) == 0


def test_check_table_fails_when_the_table_was_edited_by_hand(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    assert main(["--root", str(root), "--write-table"]) == 0
    text = table_path(root).read_text(encoding="utf-8")
    table_path(root).write_text(
        text.replace("| filled |", "| awaiting_human_value |", 1), encoding="utf-8"
    )
    assert main(["--root", str(root), "--check-table"]) == 1
    # a hand edit outside the generated region is not a staleness
    table_path(root).write_text(
        text.replace("Hand-written trailer.", "Edited trailer."), encoding="utf-8"
    )
    assert main(["--root", str(root), "--check-table"]) == 0


@pytest.mark.parametrize(
    "table_text",
    [
        "no markers\n",
        "<!-- BEGIN GENERATED -->\n",
        "<!-- END GENERATED -->\n<!-- BEGIN GENERATED -->\n",
        "<!-- BEGIN GENERATED -->\n<!-- END GENERATED -->\n<!-- BEGIN GENERATED -->\n<!-- END GENERATED -->\n",
    ],
)
def test_table_markers_are_required_exactly_once_in_order(
    tmp_path: Path, table_text: str
) -> None:
    root = make_root(tmp_path)
    table_path(root).write_text(table_text, encoding="utf-8")
    for flag in ("--write-table", "--check-table"):
        assert main(["--root", str(root), flag]) == 2
    assert table_path(root).read_text(encoding="utf-8") == table_text  # never rewritten


def test_missing_table_or_prior_is_an_error_not_a_creation(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    table_path(root).unlink()
    assert main(["--root", str(root), "--write-table"]) == 2
    assert not table_path(root).exists()
    root2 = make_root(tmp_path / "two")
    prior_path(root2).unlink()
    assert main(["--root", str(root2), "--check-table"]) == 2


def test_an_invalid_prior_file_makes_the_table_command_fail(tmp_path: Path) -> None:
    root = make_root(
        tmp_path, prior_kwargs={"row_updates": {"ec50": {"source_ref": ""}}}
    )
    assert main(["--root", str(root), "--write-table"]) == 2


def test_exactly_one_mode_is_required() -> None:
    with pytest.raises(SystemExit):
        main([])
    with pytest.raises(SystemExit):
        main(["--write-table", "--check-table"])


def test_sibling_design_configs_are_rendered_when_present(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    (root / "configs" / "benchmark").mkdir(parents=True)
    design = {
        "parameters": [
            {
                **unfilled_row("ec50"),
                "parameter": "circadian_phase_h",
                "unit": "h",
                "source_type": "design_choice",
                "consumer_task": "WS04-T03",
                "note": "gap parameter",
            }
        ],
        "grid_step_ms": 60_000,  # keys owned by the sibling task are not validated here
    }
    (root / "configs" / "benchmark" / "generator_design.yaml").write_text(
        yaml.safe_dump(design, sort_keys=False), encoding="utf-8"
    )
    (root / "configs" / "benchmark" / "care_plans.yaml").write_text(
        "plans: []\n", encoding="utf-8"
    )  # no rows: contributes nothing
    assert main(["--root", str(root), "--write-table"]) == 0
    lines = table_lines(table_path(root).read_text(encoding="utf-8"))
    assert len(lines) == 1 + len(CONTRACT_NUMERIC_NAMES) + 1
    extra = split_cells(lines[-1])
    assert extra[0] == "circadian_phase_h" and extra[1] == "-"  # no contract field
    assert main(["--root", str(root), "--check-table"]) == 0


def test_sibling_rows_are_validated_with_the_same_schema(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    (root / "configs" / "benchmark").mkdir(parents=True)
    bad = {
        "parameters": [{**fixture_row("ec50"), "parameter": "x_gap", "source_ref": ""}]
    }
    (root / "configs" / "benchmark" / "generator_design.yaml").write_text(
        yaml.safe_dump(bad, sort_keys=False), encoding="utf-8"
    )
    assert main(["--root", str(root), "--write-table"]) == 2


def test_duplicate_parameter_across_files_is_rejected(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    (root / "configs" / "benchmark").mkdir(parents=True)
    dup = {"parameters": [{**unfilled_row("ec50")}]}
    (root / "configs" / "benchmark" / "injections.yaml").write_text(
        yaml.safe_dump(dup, sort_keys=False), encoding="utf-8"
    )
    assert main(["--root", str(root), "--write-table"]) == 2


# ---------------------------------------------------------------------------
# 13. The committed files
# ---------------------------------------------------------------------------

COMMITTED_PRIOR = ROOT / "configs" / "priors" / "literature_hypertension.yaml"
COMMITTED_TABLE = ROOT / "docs" / "benchmark" / "parameter-provenance.md"


def test_committed_provenance_table_is_current() -> None:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        filter(None, [str(SRC), env.get("PYTHONPATH", "")])
    )
    result = subprocess.run(
        [sys.executable, "-m", "ralmon.benchmark.priors", "--check-table"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert main(["--root", str(ROOT), "--check-table"]) == 0


def test_committed_prior_has_one_row_per_contract_field() -> None:
    parsed = load_prior_file(COMMITTED_PRIOR)
    assert parsed.fixture_only is False
    assert [row.parameter for row in parsed.rows] == list(CONTRACT_NUMERIC_NAMES)
    source = LiteraturePriorSource(COMMITTED_PRIOR, strict=False)
    assert set(source.unfilled_names()) | {
        r.parameter for r in parsed.rows if r.status == "filled"
    } == set(CONTRACT_NUMERIC_NAMES)
    assert "-FIXTURE-ONLY" not in source.name
    assert all(row.source_type != "fixture_only" for row in parsed.rows)
    # a filled row always has a source_ref (the loader enforces it; stated here for the reader)
    assert all(row.source_ref for row in parsed.rows if row.status == "filled")
    # a strict load of a prior with unfilled rows refuses to run
    if source.unfilled_names():
        with pytest.raises(UnfilledParameterError):
            LiteraturePriorSource(COMMITTED_PRIOR)


def test_committed_prior_carries_the_standing_notes() -> None:
    rows = {r.parameter: r for r in load_prior_file(COMMITTED_PRIOR).rows}
    for name in ("cuff_error_sd_mmhg", "cuff_bias_mmhg"):
        row = rows[name]
        assert row.source_ref is not None and "ISO 81060-2" in row.source_ref
        assert "acceptance limits" in row.note and "conservative" in row.note
        assert "edition" in row.note and "clause" in row.note
    for name in CONTRACT_ADHERENCE_FIELDS:
        assert rows[name].source_type == "declared_assumption"
        assert rows[name].source_ref is not None and "analisi" in rows[name].source_ref
    for name in (
        "emax_mmhg",
        "ec50",
        "absorption_rate_per_h",
        "elimination_rate_per_h",
        "onset_delay_range_ms",
    ):
        assert (
            "registry" in rows[name].note
        )  # the drug anchor is the registry's, not ours
        assert rows[name].consumer_task == "WS04-T04"
    assert rows["ar_noise_phi"].reference_step_ms is None  # awaiting the human


def test_committed_table_counts_match_the_prior() -> None:
    text = COMMITTED_TABLE.read_text(encoding="utf-8")
    assert len(table_lines(text)) >= 18
    parsed = load_prior_file(COMMITTED_PRIOR)
    filled = sum(1 for r in parsed.rows if r.status == "filled")
    assert f"filled: {filled}" in text
    assert "Fixture-only rows: 0" in text


# ---------------------------------------------------------------------------
# 14. No parameter literals in the generator modules
# ---------------------------------------------------------------------------

ALLOWED_FLOATS = (0.0, 1.0)
ALLOWED_INTS = (0, 1, 2, -1)
ALGORITHMIC = re.compile(r"#\s*algorithmic:\s*\S[^#]*$")
# Constants owned by an earlier, merged task that cannot be annotated within this task's
# file list. Each entry must still be needed (see test_literal_exemptions_are_not_stale).
EXEMPT_LITERALS: dict[tuple[str, int | float], str] = {
    ("trace.py", 64): "length of a sha256 hex digest (WS04-T01, algorithmic)",
}


def _literal_value(node: ast.AST) -> int | float | None:
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        inner = _literal_value(node.operand)
        if inner is None:
            return None
        return -inner if isinstance(node.op, ast.USub) else inner
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    ):
        return node.value
    return None


def parameter_literals(source: str) -> list[tuple[int, int | float]]:
    """Numeric literals of ``source`` that are neither allowed nor annotated."""
    lines = source.splitlines()
    tree = ast.parse(source)
    operands = {id(n.operand) for n in ast.walk(tree) if isinstance(n, ast.UnaryOp)}
    found = []
    for node in ast.walk(tree):
        value = None if id(node) in operands else _literal_value(node)
        if value is None:
            continue
        if isinstance(value, float):
            allowed = value in ALLOWED_FLOATS or value == 0.0  # 0.0 and -0.0
        else:
            allowed = value in ALLOWED_INTS
        if allowed or ALGORITHMIC.search(lines[node.lineno - 1]):
            continue
        found.append((node.lineno, value))
    return found


def test_literal_scanner_flags_and_allows_the_right_numbers() -> None:
    assert parameter_literals("x = 0.0 + 1.0 + 0 + 1 + 2 + -1 + -0.0\n") == []
    assert [
        v for _, v in parameter_literals("x = 0.5\ny = 3\nz = -2\nw = -1.0\nv = 2.0\n")
    ] == [0.5, 3, -2, -1.0, 2.0]
    assert parameter_literals("x = 0.5  # algorithmic: tolerance of the loop\n") == []
    assert [v for _, v in parameter_literals("x = 0.5  # algorithmic:\n")] == [0.5]
    assert [v for _, v in parameter_literals("x = 0.5  # algorithmic\n")] == [0.5]
    assert [
        v for _, v in parameter_literals("x = 0.5  # fine: algorithmic: why\ny = 0.5\n")
    ] == [0.5]
    assert [
        v for _, v in parameter_literals("x = True\ny = 'a'\nz = f'{1:04d}'\n")
    ] == []
    assert [
        v
        for _, v in parameter_literals(
            "x = (\n    0.5\n)  # algorithmic: not on the literal line\n"
        )
    ] == [0.5]


def _benchmark_modules() -> list[Path]:
    return sorted(BENCHMARK_SRC.glob("*.py"))


def test_no_parameter_literals_in_generator_modules() -> None:
    offenders = []
    for path in _benchmark_modules():
        for lineno, value in parameter_literals(path.read_text(encoding="utf-8")):
            if (path.name, value) in EXEMPT_LITERALS:
                continue
            offenders.append(f"{path.name}:{lineno}: {value!r}")
    assert offenders == [], (
        "numbers must come from YAML, or carry '# algorithmic: <reason>'"
    )


def test_literal_exemptions_are_not_stale() -> None:
    for name, value in EXEMPT_LITERALS:
        source = (BENCHMARK_SRC / name).read_text(encoding="utf-8")
        values = [v for _, v in parameter_literals(source)]
        assert value in values, (
            f"{name} no longer has the literal {value}: drop the exemption"
        )


def test_the_literal_scan_covers_every_benchmark_module() -> None:
    names = {p.name for p in _benchmark_modules()}
    assert {"priors.py", "trace.py", "__init__.py", "_stubs.py"} <= names


def _registry_values() -> set[float]:
    document = yaml.safe_load(
        (ROOT / "configs" / "registry" / "hypertension.yaml").read_text(
            encoding="utf-8"
        )
    )
    values = {float(entry["value"]) for entry in document["entries"]}
    return {v for v in values if abs(v) > 3.0}


# Unit-conversion constants of the time helpers, not clinical parameters.
CLINICAL_LITERAL_EXEMPT: dict[tuple[str, float], str] = {
    ("signals/units.py", 3_600_000.0): "MS_PER_HOUR",
}
REGISTRY_LOADER_MODULES = {"spec/registry.py"}


def _numeric_constants(path: Path) -> list[tuple[int, float]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = []
    for node in ast.walk(tree):
        value = _literal_value(node)
        if value is not None and not isinstance(node, ast.UnaryOp):
            out.append((node.lineno, float(value)))
    return out


def test_no_clinical_registry_value_appears_in_src_outside_the_loader() -> None:
    clinical = _registry_values()
    assert {
        110.0,
        140.0,
        100.0,
        50.0,
        250.0,
    } <= clinical  # the illustrative band values
    offenders = []
    for path in sorted((SRC / "ralmon").rglob("*.py")):
        rel = path.relative_to(SRC / "ralmon").as_posix()
        if rel in REGISTRY_LOADER_MODULES:
            continue
        for lineno, value in _numeric_constants(path):
            if value in clinical and (rel, value) not in CLINICAL_LITERAL_EXEMPT:
                offenders.append(f"{rel}:{lineno}: {value}")
    assert offenders == [], "clinical values live in the registry or a prior file only"


def test_clinical_exemptions_are_not_stale() -> None:
    for rel, value in CLINICAL_LITERAL_EXEMPT:
        values = [v for _, v in _numeric_constants(SRC / "ralmon" / rel)]
        assert value in values


# ---------------------------------------------------------------------------
# 15. The protocol is swappable
# ---------------------------------------------------------------------------


class _StubPrior:
    name = "stub-prior"

    def sample_patient(
        self, rng: np.random.Generator, patient_index: int
    ) -> PatientParams:
        return PatientParams("p", 1.0, 1.0, 1.0, 0.5, 1.0, 1.0, 1.0, 1.0, (0, 1))

    def adherence(self) -> AdherenceParams:
        return AdherenceParams(0.0, 0.0, 0.0, 0)

    def device_errors(self) -> DeviceErrorModel:
        return DeviceErrorModel(0.0, 0.0, 0.0, 0.0)

    def provenance(self) -> Sequence[ParamProvenance]:
        return ()


def _describe(source: PriorSource) -> tuple[str, str]:
    patient = source.sample_patient(np.random.default_rng(0), 0)
    return source.name, patient.patient_id


def test_protocol_swappable(tmp_path: Path) -> None:
    assert _describe(_StubPrior()) == ("stub-prior", "p")
    literature = prior(tmp_path)
    assert _describe(literature) == (literature.name, "p0000")
