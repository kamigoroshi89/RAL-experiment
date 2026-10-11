"""Benchmark builder, reader and CLI (WS04-T11).

FIXTURE-ONLY. Every build below uses the fixture-only prior of ``conftest.make_fixture_prior``, the fixture
registry F0 (``tests/fixtures/spec/registry_f0.yaml``, ADR-027), design files whose awaiting rows are filled with
arithmetic values and inline-sized segments written under ``tmp_path``. None of the numbers is a clinical value,
a device specification or a statement about a patient; the builds are small (4 patients of 2 days, two or four
confounder pairs) and the committed ``configs/benchmark/*.yaml`` files are only read, never relied on being filled.

What is under test (``ralmon.benchmark.builder``, ``python -m ralmon.benchmark``)
------------------------------------------------------------------------------
* ``generate_benchmark``: per patient, in this order, the patient, the schedule from the registry windows, the
  injection plan, the latent days (T09), the labels (T10 with history, ADR-046 and ADR-064), the observed base
  (T06), the C2 and C3 injectors (T07, T08), the robot ``NODE_STATE colocated`` reports (ADR-054), the care plan
  (RANGE, HOLD and COUNT parameter records for B1) and one unscored TAIL day (ADR-066);
* ``split_patients`` (largest remainder, deterministic shuffle by patient), the reader (``open_benchmark``,
  ``BenchmarkReader``), the care-plan loader and the CLI ``build``, ``verify``, ``validate``;
* determinism (same bytes), provenance (fixture-only flag, unfilled rows), no wall clock in the manifest.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from ralmon.benchmark import vocab
from ralmon.benchmark.adherence import AdherenceState
from ralmon.benchmark.builder import (
    BenchmarkConfigError,
    BenchmarkReader,
    BuildContext,
    ObservedViewError,
    PatientInjections,
    TruthUnavailableError,
    generate_benchmark,
    load_config,
    open_benchmark,
    split_patients,
    verify_benchmark,
)
from ralmon.benchmark.confounders import evaluate_pair
from ralmon.benchmark.inject_c1 import C1_SUBTYPES, c1_spec
from ralmon.benchmark.injection import registered_subtypes
from ralmon.benchmark.latent import T_DAY_MS
from ralmon.benchmark.latent_day import ForcedSlot
from ralmon.benchmark.priors import (
    FixtureOnlyPriorError,
    LiteraturePriorSource,
    UnfilledParameterError,
    load_design_file,
)
from ralmon.benchmark.schedule import check_schedule_consistency, load_schedule
from ralmon.benchmark.trace import (
    InjectedClass,
    ManifestError,
    TraceError,
    read_manifest,
    write_manifest,
)
from ralmon.monitor import MonitorConfig, run_offline_detailed
from ralmon.signals import Event, EventKind
from ralmon.spec import CarePlan, TemplateId, load_registry, load_templates

from .conftest import make_fixture_prior

ROOT = Path(__file__).resolve().parents[2]
CONFIGS = ROOT / "configs" / "benchmark"
DEFAULT_CONFIG = CONFIGS / "default.yaml"
INJECTIONS_FILE = CONFIGS / "injections.yaml"
GENERATOR_DESIGN = CONFIGS / "generator_design.yaml"
CARE_PLANS = CONFIGS / "care_plans.yaml"
F0_PATH = ROOT / "tests" / "fixtures" / "spec" / "registry_f0.yaml"

MIN = 60_000
HOUR = 3_600_000
DAY = T_DAY_MS
STEP_MS = MIN
GIT_REV = "fixture"
GENERATION_SEED = 11

F0 = load_registry(F0_PATH, step_ms=STEP_MS, allow_fixture_only=True)
TEMPLATES = load_templates(registry=F0)
WINDOWS = {
    "hold_lookback_ms": int(F0.get("hold_lookback").value),
    "delta1_ms": int(F0.get("delta1").value),
    "delta2_ms": int(F0.get("delta2").value),
    "sched_window_ms": int(F0.get("sched_window").value),
}
SCHEDULE = load_schedule(CARE_PLANS, **WINDOWS)

# ---------------------------------------------------------------------------------------------------
# Fixture files (FIXTURE-ONLY values, written under tmp_path)
# ---------------------------------------------------------------------------------------------------

GENERATOR_VALUES: dict[str, Any] = {  # FIXTURE-ONLY arithmetic
    "circadian_peak_clock_ms": 14 * HOUR,
    "intake_lag_ms": 5_000,
    "double_take_gap_ms": 2 * MIN,
    "inflation_ms_nominal": 30_000,
    "inflation_ms_sd": 2_000,
    "pulse_error_sd_bpm": 2.0,
    "robot_dwell_ms": 10 * MIN,
    "vitals_period_ms": MIN,
    "driver_period_ms": HOUR,  # TEST VALUE of WS04-T18: the real driver period is awaiting_human_value
    "driver_stale_lease_ms": 10
    * MIN,  # TEST VALUE of WS04-T18: the real lease is awaiting_human_value
}
DURATIONS = {"short": 10 * MIN, "medium": 30 * MIN, "long": HOUR}  # FIXTURE-ONLY
MULTIPLES = {  # FIXTURE-ONLY multiples of a reference quantity, spanning it
    "below": 0.5, "near": 1.0, "above": 2.0, "low": 0.5, "medium": 1.0, "high": 2.0,
}  # fmt: skip
FIXTURE_REF = "FIXTURE-ONLY: arithmetic value, no source"


def _fixture_value(row: Mapping[str, Any]) -> float:
    name, unit = row["parameter"], row["unit"]
    level = name.rsplit("_", 1)[-1]
    if "_duration_" in name:
        return DURATIONS[level]
    if name.startswith("dispenser_bounce_magnitude"):
        return {"nominal": 500, "stress_low": 5_000, "stress_high": 20_000}[
            name.removeprefix("dispenser_bounce_magnitude_")
        ]
    if name.startswith("cuff_silent_bias_magnitude"):
        return {"low": 1.0, "medium": 2.0, "high": 3.0}.get(level, 1.0)
    if name.endswith("_bpm"):
        return 40.0 if "lower" in name else 180.0
    if name.startswith("drug_nonresponse_magnitude"):
        return {"complete": 0.0, "partial": 0.5, "mild": 0.9}[level]
    if name.startswith("ecg_noise_magnitude"):
        return {"low": 1.0, "medium": 2.0, "high": 3.0}[level]
    if unit.startswith("x "):
        return MULTIPLES[level]
    raise AssertionError(f"no fixture value for {name}")


def write_injections(
    tmp_path: Path,
    *,
    rates: tuple[float, float, float] = (1.0, 1.0, 1.0),
    pairs: int = 1,
    mutate: Callable[[dict[str, Any]], None] | None = None,
    name: str = "injections.yaml",
) -> Path:
    """The committed injections.yaml with every awaiting row filled with a FIXTURE-ONLY value."""
    document = yaml.safe_load(INJECTIONS_FILE.read_text(encoding="utf-8"))
    values = {
        "injection_rate_c1": rates[0],
        "injection_rate_c2": rates[1],
        "injection_rate_c3": rates[2],
        "confounder_pairs_per_variant": pairs,
    }
    for row in document["parameters"]:
        if row["parameter"] in values:
            row.update(value=values[row["parameter"]], status="filled")
        elif row["status"] == "awaiting_human_value":
            row.update(
                value=_fixture_value(row),
                status="filled",
                source_ref=FIXTURE_REF,
                rationale="FIXTURE-ONLY: arithmetic",
                verified_by=None,
            )
    if mutate is not None:
        mutate(document)
    path = tmp_path / name
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def write_generator_design(
    tmp_path: Path,
    *,
    fill: bool = True,
    leave_unset: Sequence[str] = (),
    overrides: Mapping[str, Any] | None = None,
) -> Path:
    """The committed design file with every awaiting row filled by a FIXTURE-ONLY value, except ``leave_unset``."""
    document = yaml.safe_load(GENERATOR_DESIGN.read_text(encoding="utf-8"))
    for row in document["parameters"]:
        if row["parameter"] in leave_unset:
            continue
        if fill and row["status"] == "awaiting_human_value":
            row.update(
                value=GENERATOR_VALUES[row["parameter"]],
                status="filled",
                source_ref=FIXTURE_REF,
                rationale="FIXTURE-ONLY: arithmetic",
                verified_by=None,
            )
    for row in document["parameters"]:
        if (
            overrides and row["parameter"] in overrides
        ):  # a TEST VALUE replaces the fixture one
            row.update(
                value=overrides[row["parameter"]],
                status="filled",
                source_ref=FIXTURE_REF,
                rationale="FIXTURE-ONLY: arithmetic",
                verified_by=None,
            )
    path = tmp_path / "generator_design.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def write_segments(tmp_path: Path) -> Path:
    """A segment root with one clean heart-rate and one clean SpO2 segment of a day (FIXTURE-ONLY)."""
    root = tmp_path / "segments"
    root.mkdir(exist_ok=True)
    entries = []
    for kind, base, spread, unit in (
        ("hr_clean", 70.0, 30, "bpm"),
        ("spo2_clean", 95.0, 4, "%"),
    ):
        values = [base + i % spread for i in range(DAY // MIN)]
        data = json.dumps({"values": values}, sort_keys=True).encode("utf-8")
        (root / f"{kind}.json").write_bytes(data)
        entries.append(
            {
                "segment_id": f"{kind}-1",
                "dataset": "inline-fixture",
                "record_id": f"{kind}-1",
                "kind": kind,
                "sample_period_ms": MIN,
                "n_samples": len(values),
                "unit": unit,
                "path": f"{kind}.json",
                "sha256": hashlib.sha256(data).hexdigest(),
                "licence": "fixture-only",
            }
        )
    (root / "index.json").write_text(
        json.dumps({"schema_version": "0.1.0", "segments": entries}), encoding="utf-8"
    )
    return root


def make_prior(tmp_path: Path, *, name: str = "prior.yaml", **kwargs: Any) -> Path:
    """A fixture-only prior with baselines above the hold threshold of F0 and a low dropout rate."""
    updates = {
        "baseline_sbp_mmhg": {"dist": {"family": "uniform", "lo": 105.0, "hi": 125.0}},
        "ble_dropout_rate_per_h": {"value": 0.05},
    }
    updates.update(kwargs.pop("row_updates", {}))
    return make_fixture_prior(tmp_path, filename=name, row_updates=updates, **kwargs)


def config_document(
    tmp_path: Path,
    *,
    prior: Path | None = None,
    n_patients: int = 4,
    n_days: int = 2,
    pairs: int = 1,
    variants: list[str] | None = None,
    rates: tuple[float, float, float] = (1.0, 1.0, 1.0),
    split: Mapping[str, float] | None = None,
    device_profile: Mapping[str, Any] | None = None,
    leave_unset: Sequence[str] = (),
    design_overrides: Mapping[str, Any] | None = None,
    registry: Path | None = None,
) -> dict[str, Any]:
    prior_path = prior if prior is not None else make_prior(tmp_path)
    return {
        "schema_version": "0.1.0",
        "benchmark_version": "fixture-0",
        "pathway_template_id": "hypertension-fixture",
        "paths": {
            "registry": str(registry if registry is not None else F0_PATH),
            "generator_design": str(
                write_generator_design(
                    tmp_path, leave_unset=leave_unset, overrides=design_overrides
                )
            ),
            "care_plans": str(CARE_PLANS),
            "injections": str(write_injections(tmp_path, rates=rates, pairs=pairs)),
            "segments": str(write_segments(tmp_path)),
            "arrival_jitter": None,
        },
        "cohorts": [{"id": "main", "prior": str(prior_path)}],
        "labelling": {"mode": "scheduled"},
        "device_profile": {
            "dispenser_content_sensing": False,
            "authenticating_devices": [],
            **(device_profile or {}),
        },
        "allow_no_segments": False,
        "confounders": {"variants": variants},
        "parameters": [
            _row("n_patients", n_patients, "1"),
            _row("n_days", n_days, "1"),
            _row("generation_seed", GENERATION_SEED, "1"),
            _row(
                "split_fractions",
                dict(split or {"train": 0.5, "calibration": 0.25, "test": 0.25}),
                "1",
            ),
            _row("monitor_step_ms", STEP_MS, "ms"),
            _row("monitor_reorder_delay_ms", 0, "ms"),
        ],
    }


def _row(name: str, value: Any, unit: str) -> dict[str, Any]:
    return {
        "parameter": name,
        "unit": unit,
        "value": value,
        "dist": None,
        "source_ref": FIXTURE_REF,
        "source_type": "design_choice",
        "verified_by": None,
        "status": "filled",
        "consumer_task": "WS04-T11",
        "rationale": "FIXTURE-ONLY: arithmetic",
        "note": "fixture row",
    }


def write_config(
    tmp_path: Path, document: Mapping[str, Any] | None = None, **kwargs: Any
) -> Path:
    doc = document if document is not None else config_document(tmp_path, **kwargs)
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(dict(doc), sort_keys=False), encoding="utf-8")
    return path


def drop_row(document: dict[str, Any], name: str) -> dict[str, Any]:
    out = copy.deepcopy(document)
    out["parameters"] = [r for r in out["parameters"] if r["parameter"] != name]
    return out


def set_row(document: dict[str, Any], name: str, value: Any) -> dict[str, Any]:
    out = copy.deepcopy(document)
    for row in out["parameters"]:
        if row["parameter"] == name:
            row["value"] = value
    return out


def run_cli(*args: str | Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "ralmon.benchmark", *map(str, args)],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )


def build(
    tmp_path: Path,
    out_name: str = "bench",
    *,
    seed: int | None = None,
    document: Mapping[str, Any] | None = None,
    prior_path: Path | None = None,
    **kwargs: Any,
) -> tuple[Path, Any]:
    """Build in-process; returns (directory, manifest)."""
    doc = (
        dict(document)
        if document is not None
        else config_document(tmp_path, prior=prior_path, **kwargs)
    )
    if seed is not None:
        doc = set_row(doc, "generation_seed", seed)
    config = load_config(write_config(tmp_path, doc))
    prior = LiteraturePriorSource(
        Path(doc["cohorts"][0]["prior"]), strict=False, allow_fixture_only=True
    )
    out = tmp_path / out_name
    manifest = generate_benchmark(
        config, prior, out, allow_fixture_only=True, git_rev=GIT_REV
    )
    return out, manifest


@pytest.fixture(scope="module")
def small(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Any, Path]:
    """4 patients x 2 days + 2 confounder pairs (one variant each of two groups), built once."""
    tmp = tmp_path_factory.mktemp("small_benchmark")
    variants = ["nominal_content_robot", "outcome_reported"]
    doc = config_document(tmp, variants=variants)
    out, manifest = build(tmp, document=doc)
    return out, manifest, tmp


def files_of(root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def patients_with(manifest: Any, role: str) -> list[str]:
    return sorted(p for p, e in manifest.patients.items() if e["role"] == role)


# ---------------------------------------------------------------------------------------------------
# 1. The CLI end to end
# ---------------------------------------------------------------------------------------------------


def test_build_small_benchmark_end_to_end(tmp_path: Path) -> None:
    config = write_config(
        tmp_path, variants=[], pairs=0
    )  # 4 patients x 2 days, no pair
    out = tmp_path / "cli_bench"
    built = run_cli(
        "build", "--config", config, "--out", out,
        "--allow-fixture-only", "--git-rev", GIT_REV,
    )  # fmt: skip
    print(built.stdout, built.stderr)
    assert built.returncode == 0, built.stderr
    # 4 patients x (2 scored days + 1 tail day): observed and truth files, one plan per patient, one manifest
    observed = sorted((out / "days").rglob("*.json"))
    truth = sorted((out / "truth").rglob("*.json"))
    assert len(observed) == len(truth) == 4 * 3
    assert len(list((out / "plans").glob("*.json"))) == 4
    assert (out / "manifest.json").is_file()
    manifest = read_manifest(out)
    assert len(manifest.patients) == 4
    assert manifest.generator_git_rev == GIT_REV and manifest.fixture_only is True
    verified = run_cli("verify", out)
    print(verified.stdout, verified.stderr)
    assert verified.returncode == 0, verified.stderr
    # the scored days are 4 x 2; the tail days are marked and not counted
    reader = open_benchmark(out)
    assert sum(len(reader.days(p)) for p in reader.patients) == 8
    assert sum(1 for p in reader.patients if reader.tail_day(p) is not None) == 4


def test_cli_validate_placeholder_exits_2() -> None:
    result = run_cli("validate", "somewhere")
    assert result.returncode == 2
    assert "WS04-T12" in result.stdout + result.stderr


# ---------------------------------------------------------------------------------------------------
# 2. Determinism
# ---------------------------------------------------------------------------------------------------


def test_same_config_and_seed_reproduce_bytes(
    small: tuple[Path, Any, Path], tmp_path: Path
) -> None:
    """The same configuration FILE and seed: the manifest hashes the configuration, so a copy elsewhere differs."""
    out, _, tmp = small
    prior = LiteraturePriorSource(
        tmp / "prior.yaml", strict=False, allow_fixture_only=True
    )
    again = tmp_path / "again"
    generate_benchmark(
        load_config(tmp / "config.yaml"),
        prior,
        again,
        allow_fixture_only=True,
        git_rev=GIT_REV,
    )
    first, second = files_of(out), files_of(again)
    assert sorted(first) == sorted(second)
    for rel in first:
        assert first[rel] == second[rel], rel
    assert (out / "manifest.json").read_bytes() == (
        again / "manifest.json"
    ).read_bytes()


def test_different_generation_seeds_differ(
    small: tuple[Path, Any, Path], tmp_path: Path
) -> None:
    out, manifest, _ = small
    other, other_manifest = build(
        tmp_path,
        "other",
        seed=GENERATION_SEED + 1,
        variants=["nominal_content_robot", "outcome_reported"],
    )
    assert sorted(manifest.patients) == sorted(
        other_manifest.patients
    )  # the id scheme is the same
    assert other_manifest.generation_seed == GENERATION_SEED + 1
    changed = [
        rel
        for rel in sorted(manifest.files)
        if rel.startswith("days/")
        and rel
        in other_manifest.files  # the ids are permuted by the seed: a twin may swap places with a virtual id
        and (out / rel).read_bytes() != (other / rel).read_bytes()
    ]
    assert changed, "another generation seed must change the day files"


# ---------------------------------------------------------------------------------------------------
# 3. Splits by patient
# ---------------------------------------------------------------------------------------------------


def test_split_is_by_patient_no_leak(small: tuple[Path, Any, Path]) -> None:
    out, manifest, _ = small
    reader = open_benchmark(out)
    assert set(manifest.patients) == set(reader.patients)
    splits = {p: e["split"] for p, e in manifest.patients.items()}
    assert set(splits.values()) <= {"train", "calibration", "test"}
    # every patient is in exactly one split and the union is complete (a mapping cannot hold a patient twice;
    # the day files of a patient exist under that patient only)
    on_disk = {p.name for p in (out / "days").iterdir()}
    assert on_disk == set(splits)
    # the two members of a confounder pair share the split
    pairs: dict[str, set[str]] = {}
    for entry in manifest.patients.values():
        if entry["role"] == "confounder_pair":
            pairs.setdefault(entry["pair"], set()).add(entry["split"])
    assert pairs and all(len(s) == 1 for s in pairs.values())
    assert (
        read_manifest(out).patients == manifest.patients
    )  # the contract rule 2 check ran on read


def test_split_patients_largest_remainder() -> None:
    ids = [f"p{i}" for i in range(7)]
    fractions = {"train": 0.5, "calibration": 0.25, "test": 0.25}
    split = split_patients(ids, fractions, 0)
    assert Counter(split.values()) == {"train": 3, "calibration": 2, "test": 2}
    ten = split_patients(
        [f"q{i}" for i in range(10)], {"train": 0.5, "calibration": 0.2, "test": 0.3}, 0
    )
    assert Counter(ten.values()) == {"train": 5, "calibration": 2, "test": 3}
    for bad in (
        {"train": 0.5, "calibration": 0.25, "test": 0.5},
        {"train": 0.5, "calibration": 0.25},
        {"train": 0.5, "calibration": 0.25, "test": 0.25, "extra": 0.0},
        {"train": -0.5, "calibration": 1.0, "test": 0.5},
    ):
        with pytest.raises(BenchmarkConfigError):
            split_patients(ids, bad, 0)
    with pytest.raises(BenchmarkConfigError):
        split_patients(["a", "a"], fractions, 0)


def test_split_helper_same_seed_same_split_different_seed_differs() -> None:
    ids = [f"p{i:02d}" for i in range(40)]
    fractions = {"train": 0.5, "calibration": 0.25, "test": 0.25}
    first = split_patients(ids, fractions, 3)
    assert dict(first) == dict(split_patients(ids, fractions, 3))
    assert dict(first) == dict(
        split_patients(list(reversed(ids)), fractions, 3)
    )  # input order is irrelevant
    assert dict(first) != dict(split_patients(ids, fractions, 4))
    assert set(first) == set(ids)


# ---------------------------------------------------------------------------------------------------
# 4. The configuration
# ---------------------------------------------------------------------------------------------------


def test_default_scale_is_200_patients_7_days() -> None:
    config = load_config(DEFAULT_CONFIG)
    assert config.n_patients == 200 and config.n_days == 7
    assert config.n_patients * config.n_days == 1400  # analisi 5.1: 1400 patient-days
    assert set(config.split_fractions) == {"train", "calibration", "test"}
    assert config.monitor_step_ms == config.latent_step_ms


def test_config_requires_split_and_monitor_step(tmp_path: Path) -> None:
    doc = config_document(tmp_path)
    load_config(write_config(tmp_path, doc))
    for name in ("split_fractions", "monitor_step_ms"):
        with pytest.raises(BenchmarkConfigError, match=name):
            load_config(write_config(tmp_path, drop_row(doc, name)))
    # a value that is not a monitor step of the day is refused too
    with pytest.raises(BenchmarkConfigError):
        load_config(
            write_config(tmp_path, set_row(doc, "monitor_step_ms", 7 * MIN + 1))
        )
    # a malformed file is a configuration error
    bad = tmp_path / "bad.yaml"
    bad.write_text("- not a mapping\n", encoding="utf-8")
    with pytest.raises(BenchmarkConfigError):
        load_config(bad)
    with pytest.raises(BenchmarkConfigError):
        load_config(tmp_path / "absent.yaml")


def test_default_config_rows_have_source_refs() -> None:
    document = yaml.safe_load(DEFAULT_CONFIG.read_text(encoding="utf-8"))
    rows = document["parameters"]
    assert {"n_patients", "n_days", "split_fractions", "monitor_step_ms"} <= {
        r["parameter"] for r in rows
    }
    injections = yaml.safe_load(INJECTIONS_FILE.read_text(encoding="utf-8"))[
        "parameters"
    ]
    mine = [r for r in injections if r["consumer_task"] == "WS04-T11"]
    assert {r["parameter"] for r in mine} >= {
        "injection_rate_c1", "injection_rate_c2", "injection_rate_c3", "confounder_pairs_per_variant",
    }  # fmt: skip
    for row in [*rows, *mine]:
        assert row["source_type"] in (
            "design_choice",
            "declared_assumption",
            "illustrative_unverified",
        ), row["parameter"]
        assert isinstance(row["source_ref"], str) and row["source_ref"].strip(), row[
            "parameter"
        ]
        assert isinstance(row["rationale"], str) and row["rationale"].strip(), row[
            "parameter"
        ]
        if row["source_type"] == "design_choice":
            assert row["verified_by"] is None  # a human confirms it (H3)
    # the rows reach the provenance table through the same loader as the other design files
    names = {r.parameter for r in load_design_file(DEFAULT_CONFIG).rows}
    assert {"n_patients", "n_days", "split_fractions"} <= names


# ---------------------------------------------------------------------------------------------------
# 5. Provenance
# ---------------------------------------------------------------------------------------------------


def test_fixture_only_prior_needs_flag_and_marks_manifest(tmp_path: Path) -> None:
    doc = config_document(tmp_path, pairs=0, variants=[], n_patients=2, n_days=1)
    config = load_config(write_config(tmp_path, doc))
    prior = LiteraturePriorSource(
        Path(doc["cohorts"][0]["prior"]), strict=False, allow_fixture_only=True
    )
    assert prior.fixture_only
    with pytest.raises(FixtureOnlyPriorError):
        generate_benchmark(
            config,
            prior,
            tmp_path / "refused",
            allow_fixture_only=False,
            git_rev=GIT_REV,
        )
    assert not (tmp_path / "refused").exists() or not any(
        (tmp_path / "refused").iterdir()
    )
    manifest = generate_benchmark(
        config, prior, tmp_path / "flagged", allow_fixture_only=True, git_rev=GIT_REV
    )
    assert manifest.fixture_only is True
    assert read_manifest(tmp_path / "flagged").fixture_only is True


def test_unfilled_prior_refuses_build(tmp_path: Path) -> None:
    names = ("mean_delay_ms", "cuff_bias_mmhg")
    path = make_prior(tmp_path, name="unfilled.yaml", unfilled=names)
    doc = config_document(
        tmp_path, prior=path, pairs=0, variants=[], n_patients=2, n_days=1
    )
    config = load_config(write_config(tmp_path, doc))
    prior = LiteraturePriorSource(path, strict=False, allow_fixture_only=True)
    with pytest.raises(UnfilledParameterError) as excinfo:
        generate_benchmark(
            config, prior, tmp_path / "x", allow_fixture_only=True, git_rev=GIT_REV
        )
    for name in names:
        assert name in str(excinfo.value)
    # an unfilled design row is refused too, and named
    committed = dict(doc)
    committed["paths"] = {**doc["paths"], "injections": str(INJECTIONS_FILE)}
    config = load_config(write_config(tmp_path, committed))
    good = LiteraturePriorSource(
        make_prior(tmp_path, name="good.yaml"), strict=False, allow_fixture_only=True
    )
    with pytest.raises(UnfilledParameterError, match="duration"):
        generate_benchmark(
            config, good, tmp_path / "y", allow_fixture_only=True, git_rev=GIT_REV
        )
    # and a successful build reports zero unfilled and the unverified count
    _, manifest = build(tmp_path, "ok", pairs=0, variants=[], n_patients=2, n_days=1)
    assert manifest.n_unfilled == 0
    assert (
        manifest.n_unverified > 0
    )  # nothing of the fixture prior is verified by a human
    assert isinstance(manifest.n_unverified, int)


def test_manifest_records_revision_provenance_and_settings(
    small: tuple[Path, Any, Path],
) -> None:
    out, manifest, tmp = small
    prior = LiteraturePriorSource(
        tmp / "prior.yaml", strict=False, allow_fixture_only=True
    )
    assert manifest.generator_git_rev == GIT_REV
    assert manifest.generation_seed == GENERATION_SEED
    assert [dict(r) for r in manifest.prior_provenance] == [
        {"name": p.name, "source_ref": p.source_ref, "verified_by": p.verified_by}
        for p in prior.provenance()
    ]
    settings = manifest.settings
    for key in (
        "latent_measurement_mode", "jitter_source", "segment_source", "disabled_subtypes",
        "latent_step_ms", "numpy_version", "python_version",
    ):  # fmt: skip
        assert key in settings, key
    assert settings["latent_measurement_mode"] == "scheduled"
    assert settings["latent_step_ms"] == STEP_MS
    assert settings["jitter_source"] == "none"
    assert settings["numpy_version"] == np.__version__
    assert isinstance(settings["disabled_subtypes"], list)
    assert settings["n_scored_days"] == 2 and settings["tail_day"] is True
    assert settings["registry_version"] == F0.version()
    assert settings[
        "device_profile"
    ] == {  # WS04-T18: the device profile is recorded whole
        "dispenser_content_sensing": False,
        "authenticating_devices": [],
        "cuff_resolution_mmhg": 1.0,
        "pulse_resolution_bpm": 1.0,
        "dispenser_reports_interval": True,
        "diagnostics_profile": "without_diagnostics",
        "driver": None,
    }
    assert read_manifest(out) == manifest or read_manifest(out).files == manifest.files


def test_manifest_has_no_wallclock_fields(small: tuple[Path, Any, Path]) -> None:
    out, _, _ = small
    text = (out / "manifest.json").read_text(encoding="utf-8")
    document = json.loads(text)

    def keys(node: Any) -> list[str]:
        if isinstance(node, dict):
            return [str(k) for k in node] + [k for v in node.values() for k in keys(v)]
        if isinstance(node, list):
            return [k for v in node for k in keys(v)]
        return []

    banned = re.compile(
        r"time|date|host|user|clock|stamp|created|elapsed", re.IGNORECASE
    )
    patient_ids = set(document["patients"])
    offending = [k for k in keys(document) if banned.search(k) and k not in patient_ids]
    assert offending == [], offending
    # no value that looks like a date, a time of day with a zone or a host name
    assert not re.search(r"\b20\d\d-\d\d-\d\d", text)
    assert not re.search(r"\d\d:\d\d:\d\d", text)
    assert not re.search(r"(?i)\bhostname\b|\blocalhost\b", text)


# ---------------------------------------------------------------------------------------------------
# 6. Verify and the reader
# ---------------------------------------------------------------------------------------------------


def test_verify_detects_tampered_file(
    small: tuple[Path, Any, Path], tmp_path: Path
) -> None:
    out, manifest, _ = small
    verify_benchmark(out)  # the untouched build verifies
    copy_root = tmp_path / "copy"
    for rel, data in files_of(out).items():
        target = copy_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    victim = min(r for r in manifest.files if r.startswith("days/"))
    raw = bytearray((copy_root / victim).read_bytes())
    raw[len(raw) // 2] ^= 0x01
    (copy_root / victim).write_bytes(bytes(raw))
    with pytest.raises(ManifestError, match=re.escape(victim)):
        verify_benchmark(copy_root)
    result = run_cli("verify", copy_root)
    assert result.returncode != 0 and victim in result.stdout + result.stderr
    with pytest.raises(ManifestError, match=re.escape(victim)):
        open_benchmark(copy_root, verify=True)


def test_observed_loading_needs_no_truth_directory(
    small: tuple[Path, Any, Path], tmp_path: Path
) -> None:
    out, _, _ = small
    copy_root = tmp_path / "no_truth"
    for rel, data in files_of(out).items():
        if rel.startswith("truth/"):
            continue
        target = copy_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    reader = open_benchmark(copy_root)
    assert isinstance(reader, BenchmarkReader)
    seen = 0
    for patient in reader.patients:
        for day in reader.days(patient):
            observed = reader.observed(patient, day)
            assert (observed.patient_id, observed.day_index) == (patient, day)
            with pytest.raises(TruthUnavailableError):
                reader.truth(patient, day)
            seen += 1
        assert (
            reader.tail_day(patient) is not None
        )  # the tail day is listed, never counted
    assert seen == sum(len(reader.days(p)) for p in reader.patients) > 0
    with pytest.raises(ManifestError):
        open_benchmark(copy_root, verify=True)  # the manifest lists the truth files


def test_observed_files_carry_no_latent_or_truth_key(
    small: tuple[Path, Any, Path],
) -> None:
    out, _, _ = small
    for path in sorted((out / "days").rglob("*.json")):
        text = path.read_text(encoding="utf-8")
        assert "latent" not in text and "ground_truth" not in text, path
        document = json.loads(text)
        assert set(document) == {
            "patient_id",
            "day_index",
            "seed",
            "samples",
            "events",
            "care_plan_id",
        }


def test_out_dir_must_be_new_or_empty(
    small: tuple[Path, Any, Path], tmp_path: Path
) -> None:
    out, _, _ = small
    doc = config_document(tmp_path, pairs=0, variants=[], n_patients=1, n_days=1)
    config = load_config(write_config(tmp_path, doc))
    prior = LiteraturePriorSource(
        Path(doc["cohorts"][0]["prior"]), strict=False, allow_fixture_only=True
    )
    with pytest.raises(BenchmarkConfigError):
        generate_benchmark(config, prior, out, allow_fixture_only=True, git_rev=GIT_REV)


# ---------------------------------------------------------------------------------------------------
# 7. Care plans
# ---------------------------------------------------------------------------------------------------


def test_care_plan_resolves_from_observed_day(small: tuple[Path, Any, Path]) -> None:
    out, manifest, _ = small
    reader = open_benchmark(out)
    n_total = 3  # two scored days and the tail day
    ticks = sorted(
        d * DAY + t
        for d in range(n_total)
        for t in (*SCHEDULE.dose_ticks_ms, *SCHEDULE.measurement_ticks_ms)
    )
    patient = patients_with(manifest, "patient")[0]
    for day_index in reader.days(patient):
        observed = reader.observed(patient, day_index)
        plan = reader.care_plan(observed.care_plan_id)
        assert isinstance(plan, CarePlan)
        assert plan.care_plan_id == observed.care_plan_id and plan.patient_id == patient
        assert plan.registry_version == F0.version()
        assert (
            list(plan.schedule) == ticks
        )  # single source: the schedule the generator used, on the continuing axis
        sched = sorted(
            i.anchor_ms for i in plan.instances if i.template is TemplateId.SCHED
        )
        assert sched == sorted(
            d * DAY + t for d in range(n_total) for t in SCHEDULE.measurement_ticks_ms
        )
        ends = sorted(
            i.anchor_ms
            for i in plan.instances
            if i.template is TemplateId.COUNT and i.anchor_ms is not None
        )
        assert ends == [
            (d + 1) * DAY for d in range(n_total)
        ]  # the plan covers the whole record, tail included
    with pytest.raises(KeyError):
        reader.care_plan("no-such-plan")


def test_care_plan_carries_parameter_records_for_b1(
    small: tuple[Path, Any, Path],
) -> None:
    out, manifest, _ = small
    reader = open_benchmark(out)
    for patient in patients_with(manifest, "patient"):
        plan = reader.care_plan(reader.observed(patient, 0).care_plan_id)
        records = {
            i.template: i for i in plan.instances if i.anchor_ms is None
        }  # a parameter record has no anchor
        assert {TemplateId.RANGE, TemplateId.HOLD, TemplateId.COUNT} <= set(records)
        assert records[TemplateId.RANGE].param_values == {
            "bp_band_low": float(F0.get("bp_band_low").value),
            "bp_band_high": float(F0.get("bp_band_high").value),
        }
        assert set(records[TemplateId.HOLD].param_values) == {
            "bp_hold_threshold",
            "hold_lookback",
        }
        assert set(records[TemplateId.COUNT].param_values) == {
            "dose_max_24h",
            "dose_min_day_end",
        }
        # at most one record per template (the monitor refuses more)
        recorded = [i.template for i in plan.instances if i.anchor_ms is None]
        assert len(recorded) == len(set(recorded))
    from ralmon.baselines import B1StaticThresholds
    from ralmon.baselines.base import TimingConfig

    plan = reader.care_plan(
        reader.observed(patients_with(manifest, "patient")[0], 0).care_plan_id
    )
    b1 = B1StaticThresholds(timing=TimingConfig(STEP_MS, 0, HOUR), registry=F0)
    b1.fit([], [])
    b1.run(reader.observed(plan.patient_id, 0), plan, None)
    assert b1.run_stats is not None
    assert b1.run_stats.rules_active == ("R1", "R2", "R3", "R4")


def test_care_plan_schedule_consistent_with_registry_windows(
    small: tuple[Path, Any, Path],
) -> None:
    out, manifest, _ = small
    reader = open_benchmark(out)
    for patient in manifest.patients:
        plan = reader.care_plan(reader.observed(patient, 0).care_plan_id)
        by_day = Counter(t // DAY for t in plan.schedule)
        assert by_day[0] == len(SCHEDULE.dose_ticks_ms) + len(
            SCHEDULE.measurement_ticks_ms
        )
        measurement = tuple(
            sorted(
                i.anchor_ms % DAY
                for i in plan.instances
                if i.template is TemplateId.SCHED and i.anchor_ms < DAY
            )
        )
        doses = tuple(sorted({t for t in plan.schedule if t < DAY} - set(measurement)))
        schedule = dataclasses.replace(
            SCHEDULE, dose_ticks_ms=doses, measurement_ticks_ms=measurement
        )
        assert schedule == SCHEDULE
        assert check_schedule_consistency(schedule, **WINDOWS) == ()


# ---------------------------------------------------------------------------------------------------
# 8. Counts, pairs, cohorts
# ---------------------------------------------------------------------------------------------------


def _count_events(
    reader: BenchmarkReader,
    patients: Sequence[str],
    *,
    tail: bool = False,
    closing: bool = False,
) -> dict[str, int]:
    counted: Counter[str] = Counter()
    for patient in patients:
        if closing:
            events: Sequence[Any] = reader.closing_step_truth(patient)
        elif tail:
            tail_day = reader.tail_day(patient)
            assert tail_day is not None
            events = reader.truth(patient, tail_day).ground_truth
        else:  # scored days only: the tail day is not counted
            events = [
                e
                for d in reader.days(patient)
                for e in reader.truth(patient, d).ground_truth
            ]
        for event in events:
            counted[f"{event.cls.value}/{event.subtype}"] += 1
    return dict(sorted(counted.items()))


def test_event_counts_in_manifest_match_truth_files(
    small: tuple[Path, Any, Path],
) -> None:
    """Headline counts are the virtual patients'; the twins are counted apart (never silently mixed)."""
    out, manifest, _ = small
    reader = open_benchmark(out)
    virtual = reader.patient_ids(role="patient")
    twins = reader.patient_ids(role="confounder_pair")
    assert len(virtual) == 4 and len(twins) == 4
    counted = _count_events(reader, virtual)
    assert counted == dict(manifest.event_counts)
    assert sum(counted.values()) > 0
    assert "C1" in {key.split("/")[0] for key in counted}
    assert _count_events(reader, twins) == dict(manifest.settings["twin_event_counts"])
    total: Counter[str] = Counter(manifest.event_counts)
    total.update(manifest.settings["twin_event_counts"])
    assert dict(sorted(total.items())) == dict(manifest.settings["total_event_counts"])
    # the tail days, and the events they decide at their first step (the closing-step truth of the last scored days)
    tail = _count_events(reader, virtual, tail=True)
    assert tail == dict(manifest.settings["tail_event_counts"])
    closing = _count_events(reader, virtual, closing=True)
    assert closing == dict(manifest.settings["closing_step_event_counts"])
    assert sum(closing.values()) <= sum(tail.values())
    assert _count_events(reader, twins, tail=True) == dict(
        manifest.settings["twin_tail_event_counts"]
    )
    assert _count_events(reader, twins, closing=True) == dict(
        manifest.settings["twin_closing_step_event_counts"]
    )


def test_pair_patients_share_base_and_split(small: tuple[Path, Any, Path]) -> None:
    out, manifest, _ = small
    pairs: dict[str, list[str]] = {}
    for patient, entry in manifest.patients.items():
        if entry["role"] == "confounder_pair":
            pairs.setdefault(entry["pair"], []).append(patient)
    assert len(pairs) == 2
    reader = open_benchmark(out)
    for _pair_id, members in sorted(pairs.items()):
        assert len(members) == 2
        a, b = sorted(members, key=lambda p: manifest.patients[p]["member"])
        entry_a, entry_b = manifest.patients[a], manifest.patients[b]
        assert (entry_a["member"], entry_b["member"]) == ("A", "B")
        assert (
            entry_a["split"] == entry_b["split"]
            and entry_a["cohort"] == entry_b["cohort"]
        )
        assert (
            entry_a["group"] == entry_b["group"]
            and entry_a["variant_id"] == entry_b["variant_id"]
        )
        # the latent baseline (the sidecar before the drug and the pulses) is the same
        assert reader.baseline_sbp(a, 0) == reader.baseline_sbp(b, 0)
        # different mechanisms: the record sets differ
        mechanisms = []
        for patient in (a, b):
            log = reader.truth(patient, 0).injection_log
            assert isinstance(log, list)
            mechanisms.append(sorted((e["cls"], e["subtype"]) for e in log))
        assert mechanisms[0] != mechanisms[1]
        # both members have a scored day 0 and a tail day, whatever their group
        for patient in (a, b):
            assert reader.days(patient) == (0,) and reader.tail_day(patient) == 1


def test_pair_members_have_equal_patient_params(tmp_path: Path) -> None:
    doc = config_document(
        tmp_path, pairs=1, variants=["nominal_content_robot"], n_patients=1, n_days=1
    )
    config = load_config(write_config(tmp_path, doc))
    prior = LiteraturePriorSource(
        Path(doc["cohorts"][0]["prior"]), strict=False, allow_fixture_only=True
    )
    context = BuildContext.create(config, prior, allow_fixture_only=True)
    pairs = context.build_pairs()
    assert len(pairs) == 1
    member_a, member_b = pairs[0]
    pa = dataclasses.replace(member_a.params, patient_id="same")
    pb = dataclasses.replace(member_b.params, patient_id="same")
    assert pa == pb and member_a.params.patient_id != member_b.params.patient_id
    assert member_a.patient_index == member_b.patient_index
    assert member_a.extra["role"] == member_b.extra["role"] == "confounder_pair"
    assert member_a.extra["pair"] == member_b.extra["pair"]
    # the computed flag, not the YAML expectation, is in the records
    flags = {
        e["indistinguishable_by_construction"]
        for built in (member_a, member_b)
        for e in built.days[0].truth.injection_log  # type: ignore[union-attr]
    }
    assert len(flags) == 1 and flags <= {True, False}


def test_cohort_option_builds_two_cohorts(tmp_path: Path) -> None:
    prior_a = make_prior(tmp_path, name="a.yaml")
    prior_b = make_prior(
        tmp_path,
        name="b.yaml",
        row_updates={
            "baseline_sbp_mmhg": {
                "dist": {"family": "uniform", "lo": 120.0, "hi": 140.0}
            }
        },
    )
    doc = config_document(
        tmp_path, prior=prior_a, pairs=0, variants=[], n_patients=2, n_days=1
    )
    doc["cohorts"] = [
        {"id": "alpha", "prior": str(prior_a), "n_patients": 2},
        {"id": "beta", "prior": str(prior_b), "n_patients": 3},
    ]
    config = load_config(write_config(tmp_path, doc))
    priors = {
        "alpha": LiteraturePriorSource(prior_a, strict=False, allow_fixture_only=True),
        "beta": LiteraturePriorSource(prior_b, strict=False, allow_fixture_only=True),
    }
    out = tmp_path / "two_cohorts"
    manifest = generate_benchmark(
        config, priors, out, allow_fixture_only=True, git_rev=GIT_REV
    )
    assert len(manifest.patients) == 5
    by_cohort = Counter(e["cohort"] for e in manifest.patients.values())
    assert by_cohort == {"alpha": 2, "beta": 3}
    for patient, entry in manifest.patients.items():
        assert patient.startswith(entry["cohort"] + "-"), patient
    reader = open_benchmark(out)
    assert sorted(reader.patient_ids(cohort="beta")) == sorted(
        p for p in manifest.patients if p.startswith("beta-")
    )
    assert manifest.settings["cohorts"] == ["alpha", "beta"]
    names = {r["name"] for r in manifest.prior_provenance}
    assert any(n.startswith("alpha:") for n in names) and any(
        n.startswith("beta:") for n in names
    )
    verify_benchmark(out)


# ---------------------------------------------------------------------------------------------------
# 9. The robot NODE_STATE reports (ADR-054, ADR-035)
# ---------------------------------------------------------------------------------------------------


def test_colocated_is_a_declared_payload_key() -> None:
    assert vocab.KEY_COLOCATED == "colocated"
    assert "colocated" in vocab.PAYLOAD_KEYS[EventKind.NODE_STATE]
    vocab.check_payload(EventKind.NODE_STATE, {"state": "active", "colocated": True})
    with pytest.raises(vocab.VocabularyError):
        vocab.check_payload(EventKind.NODE_STATE, {"state": "active", "colocated": 1})
    with pytest.raises(vocab.VocabularyError):
        vocab.check_payload(
            EventKind.NODE_STATE, {"state": "active", "colocated": "yes"}
        )
    assert "colocated" in vocab.__all__ or "KEY_COLOCATED" in vocab.__all__


def robot_reports(events: Sequence[Event]) -> list[Event]:
    return [
        e
        for e in events
        if e.kind is EventKind.NODE_STATE and e.payload.get("colocated") is not None
    ]


def test_every_robot_visit_has_an_arrival_report_and_the_gate_is_zero(
    small: tuple[Path, Any, Path],
) -> None:
    out, manifest, _ = small
    reader = open_benchmark(out)
    registry_plan_cfg = MonitorConfig(STEP_MS, 0, False, None, "likely", F0.version())
    checked_days = 0
    for patient in patients_with(manifest, "patient"):
        plan = reader.care_plan(reader.observed(patient, 0).care_plan_id)
        for day_index in reader.days(patient):
            day = reader.observed(patient, day_index)
            reports = robot_reports(day.events)
            presence = sorted(
                s.t_device_ms for s in day.samples if s.signal == "presence"
            )
            for event in reports:
                assert event.source == vocab.SOURCE_ROBOT == "robot"
                assert event.payload["state"] == "active"
                assert type(event.payload["colocated"]) is bool  # a real bool, not 0/1
                vocab.check_payload(event.kind, event.payload)
                assert event.t_rx_ms == event.t_device_ms and event.seq is None
            arrivals = [
                e.t_device_ms for e in reports if e.payload["colocated"] is True
            ]
            departures = [
                e.t_device_ms for e in reports if e.payload["colocated"] is False
            ]
            # one arrival report per presence sample, at or before it (including the first one of the day)
            assert presence, "the fixture schedule makes robot visits"
            for t in presence:
                assert any(a <= t for a in arrivals), (patient, day_index, t)
            assert min(arrivals) <= min(presence)
            assert len(departures) >= 1 and all(
                any(a < d for a in arrivals) for d in departures
            )
            history = [reader.observed(patient, k) for k in range(day_index)]
            result = run_offline_detailed(
                day, plan, registry_plan_cfg, None, None, registry=F0, templates=TEMPLATES, history=history,
            )  # fmt: skip
            assert result.stats.presence_samples_without_availability_marks == 0
            assert result.stats.colocated_reports_ignored == 0
            assert result.stats.availability_reports >= len(reports) > 0
            checked_days += 1
    assert checked_days == 8


# ---------------------------------------------------------------------------------------------------
# 10. The sidecars
# ---------------------------------------------------------------------------------------------------


def test_truth_sidecars_have_one_entry_per_record_and_the_baseline(
    small: tuple[Path, Any, Path],
) -> None:
    out, manifest, _ = small
    reader = open_benchmark(out)
    for patient in reader.patients:
        for day in (*reader.days(patient), reader.tail_day(patient)):
            assert day is not None
            truth = reader.truth(patient, day)
            log = truth.injection_log
            assert isinstance(log, list)
            for index, entry in enumerate(log):
                assert entry["record_index"] == index
                assert set(entry["truth_indices"]) <= set(
                    range(len(truth.ground_truth))
                )
                assert isinstance(entry["explains_in_later_days"], list)
            assert isinstance(truth.behaviour_log, list)
            baseline = reader.baseline_sbp(patient, day)
            assert len(baseline) == DAY // STEP_MS
            assert all(isinstance(x, float) for x in baseline)
    first = patients_with(manifest, "patient")[0]
    assert reader.baseline_sbp(first, 0) != reader.baseline_sbp(first, 1)


# ---------------------------------------------------------------------------------------------------
# 11. The tail day (ADR-066)
# ---------------------------------------------------------------------------------------------------


def test_manifest_marks_exactly_one_tail_day_per_patient(
    small: tuple[Path, Any, Path],
) -> None:
    out, manifest, _ = small
    reader = open_benchmark(out)
    n_scored = manifest.settings["n_scored_days"]
    assert n_scored == 2 and manifest.settings["tail_day"] is True
    for patient, entry in manifest.patients.items():
        scored = 2 if entry["role"] == "patient" else 1
        assert entry["n_scored_days"] == scored
        assert (
            entry["tail_day_index"] == scored
        )  # one tail day, right after the scored days
        assert reader.days(patient) == tuple(range(scored))
        assert reader.tail_day(patient) == scored
        files = sorted(
            int(Path(rel).stem)
            for rel in manifest.files
            if rel.startswith(f"days/{patient}/")
        )
        assert files == list(
            range(scored + 1)
        )  # the tail day is generated and listed in `files`
        assert f"days/{patient}/{scored}.json" in manifest.files
        assert f"truth/{patient}/{scored}.json" in manifest.files
    # the tail day is in no split count and in no day total of the manifest
    split_counts = Counter(e["split"] for e in manifest.patients.values())
    assert sum(split_counts.values()) == len(manifest.patients)
    total_days = sum(e["n_scored_days"] for e in manifest.patients.values())
    assert (
        total_days == 4 * 2 + 4 * 1
    )  # four patients of two days, four pair members of one
    # headline day totals are the virtual patients' (4 x 2); the twin days are a separate field, the sum is explicit
    assert manifest.settings["n_patient_days"] == 4 * 2
    assert manifest.settings["n_twin_patient_days"] == 4 * 1
    assert (
        reader.n_patient_days() == 8 and reader.n_patient_days(role=None) == total_days
    )
    assert reader.n_patient_days(role="confounder_pair") == 4
    assert sum(len(reader.days(p)) for p in reader.patients) == total_days


def _scripted_context(tmp_path: Path) -> tuple[BuildContext, Any]:
    """A prior with a flat latent pressure (no circadian component, no noise): a response is the drug's alone."""
    prior_path = make_prior(
        tmp_path,
        row_updates={
            "circadian_amplitude_mmhg": {"value": 0.0},
            "ar_noise_sd_mmhg": {"value": 0.0},
            "baseline_sbp_mmhg": {
                "dist": {"family": "uniform", "lo": 120.0, "hi": 125.0}
            },
            "p_delay": {"value": 0.0},
            "p_omission": {"value": 0.0},
            "p_double_take": {"value": 0.0},
        },
    )
    doc = config_document(
        tmp_path,
        prior=prior_path,
        pairs=0,
        variants=[],
        n_patients=1,
        n_days=2,
        rates=(0.0, 0.0, 0.0),
    )
    config = load_config(write_config(tmp_path, doc))
    prior = LiteraturePriorSource(prior_path, strict=False, allow_fixture_only=True)
    return BuildContext.create(config, prior, allow_fixture_only=True), prior


def test_the_closing_step_of_the_last_scored_day_is_owned_by_the_tail_day(
    tmp_path: Path,
) -> None:
    """The example of docs/benchmark/ground-truth.md: a dose at 21:00 whose RESP window closes at 24:00.

    The dose of the last scored day (day 1) is taken on time and does nothing (a complete non-response over
    the day), so the RESP instance is violated at the closing step, which is the first step of the tail day
    (ADR-064 (b), ADR-066): it is an event of the tail day with the deadline 48:00 as its end, it is in no
    truth of the last scored day, and the reader gives it as the closing-step truth of the patient.
    """
    context, _ = _scripted_context(tmp_path)
    dose_21 = SCHEDULE.dose_ticks_ms[-1]
    assert dose_21 == 21 * HOUR
    last = 1
    nonresponse = c1_spec(
        "drug_nonresponse",
        last * DAY + 20 * HOUR,
        duration_ms=3 * HOUR,
        magnitude=0.0,
        level="complete",
    )  # the window covers the true intake of the 21:00 dose
    scripted = PatientInjections(
        c1=(nonresponse,),
        forced_slots=(
            ForcedSlot(last, len(SCHEDULE.dose_ticks_ms) - 1, AdherenceState.ON_TIME),
        ),
    )
    patient = context.draw_patient(0)
    built = context.build_patient(patient, 0, scripted)
    deadline = (last + 1) * DAY
    scored, tail = built.days[last], built.days[last + 1]
    assert built.n_scored_days == 2 and built.days[-1].tail and not scored.tail
    dose_onset = last * DAY + dose_21
    resp_last = [
        e
        for e in scored.truth.ground_truth
        if e.template_id == "resp" and e.onset_ms == dose_onset
    ]
    assert resp_last == [], (
        "by ADR-064 (b) the closing step of the last scored day is not its own"
    )
    resp_tail = [
        e
        for e in tail.truth.ground_truth
        if e.template_id == "resp" and e.onset_ms == dose_onset
    ]
    owned = [e for e in resp_tail if e.end_ms == deadline]
    assert len(owned) == 1, resp_tail
    event = owned[0]
    assert (
        event.onset_ms == last * DAY + dose_21
        and event.injected is True
        and event.subtype == "drug_nonresponse"
    )
    # the sidecar link: the record of day 1 explains an event of the tail day, which is in no truth_indices of its own day
    log = scored.truth.injection_log
    assert isinstance(log, list) and len(log) == 1
    index = tail.truth.ground_truth.index(event)
    assert log[0]["explains_in_later_days"] == [
        {"day_index": last + 1, "truth_index": index}
    ]
    assert all(index not in e["truth_indices"] for e in tail.truth.injection_log)  # type: ignore[union-attr]
    # and the same through the written benchmark: the reader's closing-step truth is the first-step truth of the tail
    out = tmp_path / "scripted"
    context.write(out, [built], [], git_rev=GIT_REV)
    reader = open_benchmark(out)
    closing = reader.closing_step_truth(built.patient_id)
    assert [e for e in closing if e.template_id == "resp"] == [event]
    assert all(
        (e.end_ms if e.end_ms is not None else e.onset_ms) == deadline for e in closing
    )
    assert (
        reader.days(built.patient_id) == (0, 1)
        and reader.tail_day(built.patient_id) == 2
    )


def test_the_tail_day_is_labelled_with_the_history_of_the_scored_days(
    tmp_path: Path,
) -> None:
    """Without the history the closing-step event would not exist on the tail day: it needs the dose of day 1."""
    context, _ = _scripted_context(tmp_path)
    scripted = PatientInjections(
        c1=(
            c1_spec(
                "drug_nonresponse",
                1 * DAY + 20 * HOUR,
                duration_ms=3 * HOUR,
                magnitude=0.0,
                level="complete",
            ),
        ),
        forced_slots=(ForcedSlot(1, 1, AdherenceState.ON_TIME),),
    )
    built = context.build_patient(context.draw_patient(0), 0, scripted)
    tail = built.days[-1]
    assert any(
        e.template_id == "resp" and e.onset_ms < tail.observed.day_index * DAY
        for e in tail.truth.ground_truth
    )


# ---------------------------------------------------------------------------------------------------
# 12. The CLI
# ---------------------------------------------------------------------------------------------------


def test_cli_help_and_exit_codes(tmp_path: Path) -> None:
    helped = run_cli("--help")
    assert helped.returncode == 0
    for command in ("build", "verify", "validate"):
        assert command in helped.stdout
    for command in ("build", "verify"):
        assert run_cli(command, "--help").returncode == 0
    out = tmp_path / "out"
    # a bad configuration exits 2
    bad = tmp_path / "bad.yaml"
    bad.write_text("not: a benchmark config\n", encoding="utf-8")
    assert (
        run_cli(
            "build",
            "--config",
            bad,
            "--out",
            out,
            "--allow-fixture-only",
            "--git-rev",
            GIT_REV,
        ).returncode
        == 2
    )
    assert (
        run_cli("build", "--config", tmp_path / "absent.yaml", "--out", out).returncode
        == 2
    )
    # a provenance error exits 3: a fixture-only prior without the flag, an unfilled prior
    config = write_config(tmp_path, pairs=0, variants=[], n_patients=1, n_days=1)
    refused = run_cli("build", "--config", config, "--out", out, "--git-rev", GIT_REV)
    assert refused.returncode == 3, refused.stderr
    unfilled = make_prior(tmp_path, name="unfilled.yaml", unfilled=("mean_delay_ms",))
    refused = run_cli(
        "build",
        "--config",
        config,
        "--out",
        out,
        "--prior",
        unfilled,
        "--allow-fixture-only",
        "--git-rev",
        GIT_REV,
    )
    assert refused.returncode == 3 and "mean_delay_ms" in refused.stderr
    # the flags --n-patients, --n-days and --seed apply
    ok = run_cli(
        "build", "--config", config, "--out", tmp_path / "flags", "--allow-fixture-only",
        "--git-rev", GIT_REV, "--n-patients", "2", "--n-days", "1", "--seed", "5",
    )  # fmt: skip
    assert ok.returncode == 0, ok.stderr
    manifest = read_manifest(tmp_path / "flags")
    assert len(manifest.patients) == 2 and manifest.generation_seed == 5
    assert all(e["n_scored_days"] == 1 for e in manifest.patients.values())


def test_public_api_exports() -> None:
    from ralmon import benchmark
    from ralmon.benchmark import (
        BenchmarkReader as reader_class,
    )
    from ralmon.benchmark import (
        generate_benchmark as generate,
    )
    from ralmon.benchmark import (
        load_benchmark,
    )
    from ralmon.benchmark import (
        open_benchmark as opener,
    )
    from ralmon.benchmark import (
        split_patients as splitter,
    )

    assert (
        generate is generate_benchmark
        and opener is open_benchmark
        and splitter is split_patients
    )
    assert reader_class is BenchmarkReader
    assert not hasattr(benchmark.generate_benchmark, "__ralmon_stub_owner__")
    assert not hasattr(load_benchmark, "__ralmon_stub_owner__")
    assert callable(load_benchmark)


# ---------------------------------------------------------------------------------------------------
# 13. Review round 1: opaque twin ids, a strict verify, the observed-only view, counts, failures
# ---------------------------------------------------------------------------------------------------

MECHANISM_NAMES = sorted(
    {
        *C1_SUBTYPES,
        *registered_subtypes(InjectedClass.C2),
        *registered_subtypes(InjectedClass.C3),
    }
    | {
        "double_take_vs_bounce",
        "nonresponse_vs_falsified_dispense",
        "refusal_vs_robot_missed",
    }
)
ID_SHAPE = re.compile(r"p\d{4}")


def test_twin_ids_carry_no_role_and_have_the_shape_of_a_virtual_id(
    small: tuple[Path, Any, Path],
) -> None:
    """The label of a twin (A or B, a pair, a mechanism) lives in the manifest and the truth side only."""
    out, manifest, _ = small
    for patient, entry in manifest.patients.items():
        assert ID_SHAPE.fullmatch(patient), patient  # twins and virtual patients alike
        assert entry["care_plan_id"] == f"plan-{patient}"
    banned = re.compile(r"pair|confounder|member|-A\b|-B\b|twin", re.IGNORECASE)
    names = [p.name for p in (out / "days").rglob("*")]
    names += [p.name for p in (out / "plans").rglob("*")]
    for name in names:
        assert banned.search(name) is None, name
    for path in [
        *sorted((out / "days").rglob("*.json")),
        *sorted((out / "plans").glob("*.json")),
    ]:
        text = path.read_text(encoding="utf-8")
        assert banned.search(text) is None, path
        for mechanism in MECHANISM_NAMES:
            assert f'"{mechanism}"' not in text, (path, mechanism)
    # the only places that name the role: the manifest and the truth side
    twin = next(
        p for p, e in manifest.patients.items() if e["role"] == "confounder_pair"
    )
    assert manifest.patients[twin]["pair"].startswith("pair-")
    assert manifest.patients[twin]["member"] in ("A", "B")


def test_twin_ids_are_interleaved_and_the_assignment_is_drawn_from_the_seed(
    tmp_path: Path,
) -> None:
    doc = config_document(tmp_path, n_patients=5, n_days=1, pairs=2, variants=None)
    config = load_config(write_config(tmp_path, doc))
    prior = LiteraturePriorSource(
        Path(doc["cohorts"][0]["prior"]), strict=False, allow_fixture_only=True
    )
    context = BuildContext.create(config, prior, allow_fixture_only=True)
    virtual, members = context.planned_ids()
    assert len(virtual) == 5 and len(members) == 38  # 19 variants x 2 pairs
    everything = [*virtual, *(i for pair in members for i in pair)]
    assert len(set(everything)) == len(everything) and all(
        ID_SHAPE.fullmatch(i) for i in everything
    )
    numbers = lambda ids: sorted(int(i[1:]) for i in ids)
    twin_numbers = numbers(i for pair in members for i in pair)
    assert (
        numbers(virtual)[-1] > twin_numbers[0]
    )  # a twin id is not recognisable by being larger
    first_is_smaller = {int(a[1:]) < int(b[1:]) for a, b in members}
    assert first_is_smaller == {
        True,
        False,
    }  # member A is the lower id in some pairs and the higher in others
    # a different seed assigns differently; the same seed assigns the same
    other = BuildContext.create(
        load_config(
            write_config(tmp_path, set_row(doc, "generation_seed", GENERATION_SEED + 1))
        ),
        prior,
        allow_fixture_only=True,
    )
    assert other.planned_ids() != context.planned_ids()
    assert BuildContext.create(
        config, prior, allow_fixture_only=True
    ).planned_ids() == (virtual, members)


def _copy_tree(source: Path, target: Path) -> Path:
    for rel, data in files_of(source).items():
        destination = target / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    return target


def _refresh_manifest(root: Path) -> None:
    """Recompute the sha256 of the files the manifest lists (a tamperer who also fixes the manifest)."""
    manifest = read_manifest(root)
    files = {
        rel: hashlib.sha256((root / rel).read_bytes()).hexdigest()
        for rel in manifest.files
    }
    write_manifest(root, dataclasses.replace(manifest, files=files))


def _tamper(root: Path, manifest: Any, mutate: Callable[[dict[str, Any]], None]) -> str:
    patient = patients_with(manifest, "patient")[0]
    relative = f"days/{patient}/0.json"
    document = json.loads((root / relative).read_text(encoding="utf-8"))
    mutate(document)
    (root / relative).write_text(
        json.dumps(document, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    _refresh_manifest(root)
    return relative


def _with_payload(document: dict[str, Any]) -> dict[str, Any]:
    return next(e for e in document["events"] if e["payload"])


@pytest.mark.parametrize(
    "case",
    [
        "unknown_top_key",
        "unknown_payload_key",
        "subtype_as_value",
        "template_as_key",
        "injected_flag",
    ],
)
def test_verify_rejects_an_observed_file_with_the_injection_vocabulary(
    small: tuple[Path, Any, Path], tmp_path: Path, case: str
) -> None:
    """The reviewer's mutants: the manifest hash is fixed after the edit, so only the content checks can catch it."""
    out, manifest, _ = small
    root = _copy_tree(out, tmp_path / case)
    verify_benchmark(root)

    def mutate(document: dict[str, Any]) -> None:
        if case == "unknown_top_key":
            document["injection_log"] = []
        elif case == "unknown_payload_key":
            _with_payload(document)["payload"]["record_index"] = 3
        elif case == "subtype_as_value":
            document["events"][0]["source"] = "cuff_detached"
        elif case == "template_as_key":
            _with_payload(document)["payload"]["resp"] = "x"
        else:
            document["samples"][0]["injected"] = True

    relative = _tamper(root, manifest, mutate)
    with pytest.raises(TraceError):
        verify_benchmark(root)
    result = run_cli("verify", root)
    assert result.returncode == 1 and relative in result.stdout + result.stderr


def test_verify_rejects_a_file_that_the_manifest_does_not_list(
    small: tuple[Path, Any, Path], tmp_path: Path
) -> None:
    out, manifest, _ = small
    root = _copy_tree(out, tmp_path / "stray")
    patient = patients_with(manifest, "patient")[0]
    stray = root / "days" / patient / "99.json"
    stray.write_text('{"injected": true}\n', encoding="utf-8")
    with pytest.raises(ManifestError, match="99.json"):
        verify_benchmark(root)
    assert run_cli("verify", root).returncode == 1
    stray.unlink()
    (root / "notes.txt").write_text("not part of the benchmark", encoding="utf-8")
    with pytest.raises(ManifestError, match="notes.txt"):
        verify_benchmark(root)


def test_the_indistinguishable_flag_is_the_computed_one(tmp_path: Path) -> None:
    """Pinned to ``evaluate_pair`` on a pair where it is False and one where it is True (not the same for both members only)."""
    for variant_id, expected in (
        ("nominal_content_robot", False),
        ("stress_nocontent_norobot", True),
    ):
        sub = tmp_path / variant_id
        sub.mkdir()
        doc = config_document(
            sub, pairs=1, variants=[variant_id], n_patients=1, n_days=1
        )
        config = load_config(write_config(sub, doc))
        prior = LiteraturePriorSource(
            Path(doc["cohorts"][0]["prior"]), strict=False, allow_fixture_only=True
        )
        context = BuildContext.create(config, prior, allow_fixture_only=True)
        [(_pair_id, group, variant, ordinal)] = context.pair_units()
        assert variant.variant_id == variant_id
        ((first, second),) = context.build_pairs()
        member = first if first.extra["member"] == "A" else second
        base = context.pair_base(member.params, member.patient_index, ordinal)
        computed = evaluate_pair(group, variant, base).indistinguishable_by_construction
        assert computed is expected  # the fixture run has no arrival jitter
        for built in (first, second):
            flags = {
                e["indistinguishable_by_construction"]
                for e in built.days[0].truth.injection_log
            }  # type: ignore[union-attr]
            assert flags == {expected}, (variant_id, built.extra["member"])


def test_the_observed_only_view_cannot_reach_generator_state(
    small: tuple[Path, Any, Path], tmp_path: Path
) -> None:
    out, manifest, _ = small
    full = open_benchmark(out)
    with pytest.raises(BenchmarkConfigError):
        open_benchmark(out, view="everything")  # type: ignore[arg-type]
    reader = open_benchmark(out, view="observed")
    patient = patients_with(manifest, "patient")[0]
    assert reader.view == "observed" and full.view == "full"
    # what it offers: observed days, care plans, the split, the day lists
    day = reader.observed(patient, 0)
    assert day == full.observed(patient, 0)
    assert reader.care_plan(day.care_plan_id) == full.care_plan(day.care_plan_id)
    assert reader.days(patient) == full.days(patient) and reader.tail_day(
        patient
    ) == full.tail_day(patient)
    assert reader.patient_ids(split="test") == full.patient_ids(split="test")
    assert dict(reader.patients[patient]) == {
        "split": manifest.patients[patient]["split"],
        "cohort": "main",
    }
    for twin in patients_with(manifest, "confounder_pair"):
        assert set(reader.patients[twin]) == {
            "split",
            "cohort",
        }  # no role, pair, member or mechanism
    # what it refuses, by name
    for call in (
        lambda: reader.truth(patient, 0),
        lambda: reader.benchmark_day(patient, 0),
        lambda: reader.closing_step_truth(patient),
        lambda: reader.baseline_sbp(patient, 0),
        lambda: reader.manifest,
        lambda: reader.root,
        lambda: reader.patient_ids(role="patient"),
        lambda: reader.patient_ids(role="confounder_pair"),
        lambda: reader.n_patient_days(),
    ):
        with pytest.raises(ObservedViewError):
            call()
    assert issubclass(ObservedViewError, TraceError)
    # an observed-only copy (no truth, no generator) works in that view; the full view refuses the generator sidecar too
    copy_root = tmp_path / "observed_only"
    for rel, data in files_of(out).items():
        if rel.startswith(("truth/", "generator/")):
            continue
        target = copy_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    assert open_benchmark(copy_root, view="observed").observed(patient, 0) == day
    with pytest.raises(TruthUnavailableError):
        open_benchmark(copy_root).baseline_sbp(patient, 0)
    # even with the generator directory present, once the truth directory is gone the full view gives nothing
    partial = tmp_path / "no_truth_dir"
    for rel, data in files_of(out).items():
        if rel.startswith("truth/"):
            continue
        target = partial / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    with pytest.raises(TruthUnavailableError):
        open_benchmark(partial).baseline_sbp(patient, 0)


def test_headline_counts_are_the_virtual_patients_and_the_twins_are_apart(
    small: tuple[Path, Any, Path], tmp_path: Path
) -> None:
    out, manifest, _ = small
    s = manifest.settings
    assert (
        s["n_patient_days"] == 8
        and s["n_twin_patient_days"] == 4
        and s["n_twin_patients"] == 4
    )
    assert s["n_patients"] == 4
    result = run_cli("verify", out)
    assert result.returncode == 0
    config = write_config(
        tmp_path, variants=["nominal_content_robot"], pairs=1, n_patients=2, n_days=2
    )
    built = run_cli(
        "build",
        "--config",
        config,
        "--out",
        tmp_path / "counts",
        "--allow-fixture-only",
        "--git-rev",
        GIT_REV,
    )
    assert built.returncode == 0, built.stderr
    # 2 virtual patients x 2 days = 4 patient-days, the 2 twin days are a separate figure
    assert "virtual patients 2, scored patient-days 4" in built.stdout
    assert "twin patients 2, scored twin days 2" in built.stdout
    assert "events on scored days of the virtual patients" in built.stdout
    assert "events of the twins" in built.stdout


def test_the_manifest_hashes_the_configuration_and_the_priors(
    small: tuple[Path, Any, Path],
) -> None:
    _, manifest, tmp = small
    hashes = manifest.settings["design_sha256"]
    assert (
        hashes["config"]
        == hashlib.sha256((tmp / "config.yaml").read_bytes()).hexdigest()
    )
    for name, path in (
        ("care_plans", CARE_PLANS),
        ("generator_design", tmp / "generator_design.yaml"),
        ("injections", tmp / "injections.yaml"),
    ):
        assert hashes[name] == hashlib.sha256(path.read_bytes()).hexdigest(), name
    assert manifest.settings["prior_sha256"] == {
        "main": hashlib.sha256((tmp / "prior.yaml").read_bytes()).hexdigest()
    }


def test_a_failed_build_removes_what_it_created_and_nothing_else(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    doc = config_document(tmp_path, pairs=0, variants=[], n_patients=3, n_days=1)
    config = load_config(write_config(tmp_path, doc))
    prior = LiteraturePriorSource(
        Path(doc["cohorts"][0]["prior"]), strict=False, allow_fixture_only=True
    )
    original = BuildContext.build_patient
    calls: list[int] = []

    def failing(self: BuildContext, *args: Any, **kwargs: Any) -> Any:
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("the build fails after the first patient was written")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(BuildContext, "build_patient", failing)
    created = tmp_path / "created"
    with pytest.raises(RuntimeError):
        generate_benchmark(
            config, prior, created, allow_fixture_only=True, git_rev=GIT_REV
        )
    assert not created.exists()  # the directory this build created is gone
    calls.clear()
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(RuntimeError):
        generate_benchmark(
            config, prior, empty, allow_fixture_only=True, git_rev=GIT_REV
        )
    assert (
        empty.is_dir() and list(empty.iterdir()) == []
    )  # a pre-existing directory stays, emptied of what was written
    busy = tmp_path / "busy"
    busy.mkdir()
    (busy / "keep.txt").write_text("mine", encoding="utf-8")
    calls.clear()
    with pytest.raises(BenchmarkConfigError):
        generate_benchmark(
            config, prior, busy, allow_fixture_only=True, git_rev=GIT_REV
        )
    assert (busy / "keep.txt").read_text(encoding="utf-8") == "mine" and len(
        list(busy.iterdir())
    ) == 1
    # and the next build into the removed directory works
    monkeypatch.setattr(BuildContext, "build_patient", original)
    generate_benchmark(config, prior, created, allow_fixture_only=True, git_rev=GIT_REV)
    verify_benchmark(created)


def test_the_revision_is_dirty_for_tracked_changes_and_for_untracked_sources(
    tmp_path: Path,
) -> None:
    from ralmon.benchmark.__main__ import git_revision

    def git(*args: str) -> None:
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )

    git("init", "-q")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "one")
    clean = git_revision(tmp_path)
    assert re.fullmatch(r"[0-9a-f]{40}", clean)
    (tmp_path / "scratch.txt").write_text("unrelated", encoding="utf-8")
    assert (
        git_revision(tmp_path) == clean
    )  # an untracked file outside src and configs is not a generator change
    (tmp_path / "src" / "b.py").write_text("y = 2\n", encoding="utf-8")
    assert git_revision(tmp_path) == clean + "-dirty"  # an untracked source file is
    (tmp_path / "src" / "b.py").unlink()
    (tmp_path / "src" / "a.py").write_text("x = 2\n", encoding="utf-8")
    assert git_revision(tmp_path) == clean + "-dirty"


def test_the_split_rationale_states_targets_not_counts() -> None:
    document = yaml.safe_load(DEFAULT_CONFIG.read_text(encoding="utf-8"))
    row = next(r for r in document["parameters"] if r["parameter"] == "split_fractions")
    text = row["rationale"] + " " + row["note"]
    assert "TARGETS" in text and "pair" in text
    assert (
        "varies with the generation seed" in text
    )  # the counts per split are not guaranteed
    assert "open decision for gab" in text
