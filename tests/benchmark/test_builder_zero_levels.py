"""A magnitude level that resolves to exactly zero is not drawn by the injection plan (FIX-DB).

FIXTURE-ONLY where it builds anything: the fixture prior of ``conftest.make_fixture_prior`` and design rows
filled with arithmetic values (``test_builder.write_injections``). The committed
``configs/benchmark/injections.yaml`` and ``configs/priors/literature_hypertension.yaml`` are read as the
builder reads them; their awaiting rows are filled only in a copy under ``tmp_path``.

The defect (observability analysis of Group 1, 2026-10-10): the magnitude block of ``cuff_silent_bias`` has the
levels ``low``, ``medium``, ``high`` and ``device_bias``. ``device_bias`` is the multiplier 1.0 of the prior
``cuff_bias_mmhg``, which is 0.0 mmHg, so the injected shift was zero and the real injector never realised the
injection, in one draw out of four. The level keeps its definition (the device's own bias); the planner does not
draw a level whose resolved magnitude is exactly zero, and the manifest records the exclusion.
"""

from __future__ import annotations

import dataclasses
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from ralmon.benchmark.builder import BuildContext, load_config
from ralmon.benchmark.injection import (
    InjectionContext,
    SubtypeDesign,
    apply_observation_injections,
    load_injection_design,
    resolve_magnitude,
)
from ralmon.benchmark.latent import T_DAY_MS
from ralmon.benchmark.priors import DeviceErrorModel, LiteraturePriorSource

from .test_builder import (
    INJECTIONS_FILE,
    config_document,
    make_prior,
    write_config,
    write_injections,
)
from .test_inject_c2 import fixture_stream

ROOT = Path(__file__).resolve().parents[2]
REAL_PRIOR = ROOT / "configs" / "priors" / "literature_hypertension.yaml"
SUBTYPE = "cuff_silent_bias"


def _references(errors: DeviceErrorModel) -> dict[str, float]:
    return {
        "cuff_error_sd_mmhg": errors.cuff_error_sd_mmhg,
        "cuff_bias_mmhg": errors.cuff_bias_mmhg,
    }


def _silent_bias(tmp_path: Path) -> SubtypeDesign:
    """The real ``injections.yaml`` with its awaiting rows filled by FIXTURE-ONLY values in a copy."""
    return load_injection_design(write_injections(tmp_path), section="c2")[SUBTYPE]


def _real_errors() -> DeviceErrorModel:
    prior = LiteraturePriorSource(REAL_PRIOR, strict=False, allow_fixture_only=True)
    return prior.device_errors()


def test_the_real_prior_has_a_zero_device_bias_and_the_real_design_keeps_the_level() -> (
    None
):
    """The premise of the defect, read from the committed files, and the definition that stays."""
    assert _real_errors().cuff_bias_mmhg == 0.0
    document = load_injection_design(INJECTIONS_FILE, section="c2")[SUBTYPE]
    assert document.magnitude is not None
    names = [lv.level for lv in document.magnitude.levels]
    assert names == ["low", "medium", "high", "device_bias"]


def test_every_drawable_level_of_cuff_silent_bias_resolves_to_a_nonzero_shift(
    tmp_path: Path,
) -> None:
    from ralmon.benchmark.builder import drawable_magnitude_levels

    entry = _silent_bias(tmp_path)
    assert entry.magnitude is not None
    errors = _real_errors()
    drawable, excluded = drawable_magnitude_levels(entry.magnitude, errors)
    assert [lv.level for lv in drawable] == ["low", "medium", "high"]
    assert excluded == ("device_bias",)
    references = _references(errors)
    for level in drawable:
        assert level.reference is not None
        shift = resolve_magnitude(level, references[level.reference], level.reference)
        assert shift != 0.0, level.level


def test_device_bias_is_drawable_again_when_the_prior_bias_is_not_zero(
    tmp_path: Path,
) -> None:
    from ralmon.benchmark.builder import drawable_magnitude_levels

    entry = _silent_bias(tmp_path)
    assert entry.magnitude is not None
    errors = dataclasses.replace(_real_errors(), cuff_bias_mmhg=2.5)
    drawable, excluded = drawable_magnitude_levels(entry.magnitude, errors)
    assert [lv.level for lv in drawable] == ["low", "medium", "high", "device_bias"]
    assert excluded == ()
    level = drawable[-1]
    assert level.reference == "cuff_bias_mmhg"
    assert resolve_magnitude(level, 2.5, "cuff_bias_mmhg") == level.value * 2.5


def test_the_exclusion_does_not_touch_blocks_without_a_zero_level(
    tmp_path: Path,
) -> None:
    from ralmon.benchmark.builder import drawable_magnitude_levels

    design = load_injection_design(write_injections(tmp_path), section="c2")
    errors = _real_errors()
    for subtype in ("ecg_noise", "dispenser_bounce"):
        block = design[subtype].magnitude
        assert block is not None
        drawable, excluded = drawable_magnitude_levels(block, errors)
        assert drawable == tuple(block.levels)
        assert excluded == ()


def _context(tmp_path: Path, **kwargs: Any) -> BuildContext:
    prior_path = make_prior(tmp_path)
    doc = config_document(
        tmp_path,
        prior=prior_path,
        pairs=0,
        variants=[],
        n_patients=1,
        n_days=1,
        rates=(0.0, 3.0, 0.0),
        **kwargs,
    )
    config = load_config(write_config(tmp_path, doc))
    prior = LiteraturePriorSource(prior_path, strict=False, allow_fixture_only=True)
    return BuildContext.create(config, prior, allow_fixture_only=True)


def test_the_context_lists_the_excluded_zero_levels_per_cohort(tmp_path: Path) -> None:
    context = _context(tmp_path)
    assert context.cohorts["main"].errors.cuff_bias_mmhg == 0.0
    assert context.excluded_zero_levels() == {"main": {SUBTYPE: ["device_bias"]}}


def test_the_manifest_records_the_excluded_zero_levels(tmp_path: Path) -> None:
    from .test_builder import build

    _, manifest = build(tmp_path, "bench", pairs=0, variants=[], n_patients=1, n_days=1)
    assert manifest.settings["excluded_zero_levels"] == {
        "main": {SUBTYPE: ["device_bias"]}
    }


def test_no_planned_silent_bias_is_lost_for_lack_of_a_shift(tmp_path: Path) -> None:
    """Seeded loop through the planner and the real injector.

    Every planned ``cuff_silent_bias`` carries a non-zero shift and is never unrealised for that reason; one
    that is unrealised found no ``bp`` reading in its window (expected, not part of this fix). No planned
    injection is labelled ``device_bias`` while the prior bias is zero.
    """
    context = _context(tmp_path)
    cohort = context.cohorts["main"]
    latent: Any = SimpleNamespace(latent=SimpleNamespace(events=[]))
    outcomes: Counter[str] = Counter()
    levels: Counter[str] = Counter()
    for patient_index in range(40):
        for day in range(6):
            stream = fixture_stream(day_index=day)
            specs = context.plan_observation(
                cohort, patient_index, day, latent, stream, Counter()
            )
            readings = [s.t_device_ms for s in stream.samples if s.signal == "bp"]
            for spec in specs:
                if spec.subtype != SUBTYPE:
                    continue
                assert spec.duration_ms is not None
                levels[str(spec.level)] += 1
                assert spec.magnitude is not None and spec.magnitude != 0.0
                result = apply_observation_injections(
                    stream,
                    [spec],
                    InjectionContext(patient_index, task_deadline_offset_ms=600_000),
                )
                record = result.records[0]
                inside = any(
                    spec.onset_ms <= t < spec.onset_ms + spec.duration_ms
                    for t in readings
                )
                if record.realised:
                    outcomes["realised"] += 1
                elif not inside:
                    outcomes["no_reading_in_window"] += 1
                else:
                    outcomes["zero_shift_or_other"] += 1
                assert 0 <= spec.onset_ms - day * T_DAY_MS < T_DAY_MS
    assert sum(outcomes.values()) > 100  # the loop is large enough to mean something
    assert outcomes["zero_shift_or_other"] == 0, dict(outcomes)
    assert "device_bias" not in levels, dict(levels)
    assert set(levels) <= {"low", "medium", "high"}
    assert set(levels) == {"low", "medium", "high"}


def test_the_plan_is_a_pure_function_of_the_seed(tmp_path: Path) -> None:
    """Two plans of the same patient-day are identical (the exclusion adds no hidden state)."""
    context = _context(tmp_path)
    cohort = context.cohorts["main"]
    latent: Any = SimpleNamespace(latent=SimpleNamespace(events=[]))
    stream = fixture_stream(day_index=1)
    first = context.plan_observation(cohort, 3, 1, latent, stream, Counter())
    second = context.plan_observation(cohort, 3, 1, latent, stream, Counter())
    assert first == second
