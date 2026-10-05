"""Named random streams and the first layer of the latent patient (WS04-T03).

Every number below is arithmetic and FIXTURE-ONLY (baseline 130, amplitude 10, SD 8,
phi 0.6, ...): none is a clinical value and none enters a prior file used by the builder.
Horizons are short: the largest array built in this file has 200 000 points (1.6 MB), and no
test builds a per-millisecond grid of a day (86 400 000 points).
"""

from __future__ import annotations

import ast
import dataclasses
import math
import os
import random
import subprocess
import sys
import tracemalloc
from pathlib import Path

import numpy as np
import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

from ralmon.benchmark import LiteraturePriorSource, PatientParams
from ralmon.benchmark import latent as latent_module
from ralmon.benchmark.latent import (
    MAX_GRID_POINTS,
    T_DAY_MS,
    LatentModelError,
    LatentPressure,
    circadian,
    innovation_sd,
    rescale_ar1_phi,
    simulate_baseline_sbp,
)
from ralmon.benchmark.priors import UnfilledParameterError, load_design_file
from ralmon.benchmark.rng import (
    StreamKeyError,
    StreamPurpose,
    stream,
    stream_seed_sequence,
)

from .conftest import make_fixture_prior

ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_SRC = ROOT / "src" / "ralmon" / "benchmark"
DESIGN_FILE = ROOT / "configs" / "benchmark" / "generator_design.yaml"
TABLE = ROOT / "docs" / "benchmark" / "parameter-provenance.md"

HOUR = 3_600_000
DAY = 86_400_000
PEAK_NOON = 12 * HOUR  # fixture: the circadian peak at 12:00 (hand arithmetic only)

BASE, AMP, SD, PHI = 130.0, 10.0, 8.0, 0.6  # FIXTURE-ONLY


def make_params(**changes: float) -> PatientParams:
    """A patient made of fixture arithmetic; ``changes`` overrides a field."""
    base = PatientParams(
        patient_id="p0000",
        baseline_sbp_mmhg=BASE,
        circadian_amplitude_mmhg=AMP,
        ar_noise_sd_mmhg=SD,
        ar_noise_phi=PHI,
        emax_mmhg=20.0,
        ec50=1.0,
        absorption_rate_per_h=2.0,
        elimination_rate_per_h=0.5,
        onset_delay_range_ms=(3_600_000, 7_200_000),
    )
    return dataclasses.replace(base, **changes)


def simulate(
    params: PatientParams | None = None,
    *,
    step: int = 900_000,
    n_days: int = 1,
    peak: int = PEAK_NOON,
    ref_step: int | None = None,
    seed: int = 0,
    sub_index: int = 0,
    **kwargs: object,
) -> LatentPressure:
    rng = stream(seed, 0, None, StreamPurpose.LATENT_AR, sub_index)
    return simulate_baseline_sbp(
        params if params is not None else make_params(),
        step,
        n_days,
        peak,
        step if ref_step is None else ref_step,
        rng,
        **kwargs,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# Named random streams (rng.py)
# ---------------------------------------------------------------------------

# Hand-copied table: changing one value silently would change every benchmark.
FROZEN_PURPOSE_IDS = {
    "PATIENT": 1,
    "LATENT_AR": 2,
    "ADHERENCE": 3,
    "MEASUREMENT": 4,
    "SEGMENTS": 5,
    "JITTER": 6,
    "INJECTION_PLAN": 7,
    "INJECTION_C1": 8,
    "INJECTION_C2": 9,
    "INJECTION_C3": 10,
    "SPLIT": 11,
    "CONFOUNDER": 12,
}


def first_draws(
    seed: int = 0,
    patient: int = 3,
    day: int | None = None,
    purpose: StreamPurpose = StreamPurpose.LATENT_AR,
    sub: int = 0,
    n: int = 5,
) -> list[float]:
    return stream(seed, patient, day, purpose, sub).standard_normal(n).tolist()


def test_stream_same_keys_same_numbers() -> None:
    first = stream(0, 3, None, StreamPurpose.LATENT_AR).standard_normal(5)
    other = stream(0, 3, None, StreamPurpose.ADHERENCE).standard_normal(5)  # call order
    second = stream(0, 3, None, StreamPurpose.LATENT_AR).standard_normal(5)
    assert first.tolist() == second.tolist()
    assert first.tolist() != other.tolist()
    # The values themselves are pinned: a change of the derivation is a change of every
    # benchmark. Computed with numpy.random.SeedSequence(entropy=0, spawn_key=(3, 0, 2, 0)).
    assert first_draws(0, 3, None, StreamPurpose.LATENT_AR)[:3] == [
        -0.9207973564386018,
        -0.16202891795970387,
        -0.6115747205301761,
    ]


def test_stream_purposes_are_independent() -> None:
    a_alone = first_draws(purpose=StreamPurpose.LATENT_AR)
    gen_b = stream(0, 3, None, StreamPurpose.MEASUREMENT)
    b_draws = gen_b.standard_normal(5).tolist()
    a_after_b = first_draws(purpose=StreamPurpose.LATENT_AR)
    assert a_alone == a_after_b
    assert a_alone != b_draws
    # Both orders: B drawn before A, and A drawn before B, give the same two sequences.
    gen_a = stream(0, 3, None, StreamPurpose.LATENT_AR)
    gen_b2 = stream(0, 3, None, StreamPurpose.MEASUREMENT)
    a_first = gen_a.standard_normal(5).tolist()
    b_second = gen_b2.standard_normal(5).tolist()
    assert (a_first, b_second) == (a_alone, b_draws)
    # Independent in the statistical sense too: no linear dependence on 4000 draws.
    xs = stream(0, 3, None, StreamPurpose.LATENT_AR).standard_normal(4000)
    ys = stream(0, 3, None, StreamPurpose.MEASUREMENT).standard_normal(4000)
    r = float(np.corrcoef(xs, ys)[0, 1])
    assert abs(r) < 4.0 / math.sqrt(4000)  # four standard errors of a null correlation


def test_stream_purpose_ids_are_frozen() -> None:
    assert {m.name: int(m.value) for m in StreamPurpose} == FROZEN_PURPOSE_IDS
    assert len({int(m.value) for m in StreamPurpose}) == len(StreamPurpose) == 12


def test_stream_derivation_matches_a_literal_spawn_key() -> None:
    # entropy is the seed; spawn_key is (patient, day code, purpose, sub index); the day
    # code is 0 for None and day + 1 otherwise.
    ss = stream_seed_sequence(7, 3, 2, StreamPurpose.LATENT_AR, 5)
    assert ss.entropy == 7
    assert tuple(ss.spawn_key) == (3, 3, 2, 5)
    # Pinned output of numpy.random.SeedSequence(entropy=7, spawn_key=(3, 3, 2, 5)).
    assert ss.generate_state(4).tolist() == [
        1131869446,
        829711048,
        3148046875,
        4215335841,
    ]
    none_day = stream_seed_sequence(7, 3, None, StreamPurpose.LATENT_AR, 5)
    assert tuple(none_day.spawn_key) == (3, 0, 2, 5)


def test_stream_none_day_is_distinct_from_every_day_index() -> None:
    draws = {
        day: tuple(first_draws(day=day)) for day in (None, 0, 1, 2, 365, 2**32 - 2)
    }
    assert len(set(draws.values())) == len(draws)


def test_stream_every_key_changes_the_stream() -> None:
    base = first_draws(seed=1, patient=2, day=3, purpose=StreamPurpose.JITTER, sub=4)
    variants = [
        first_draws(seed=2, patient=2, day=3, purpose=StreamPurpose.JITTER, sub=4),
        first_draws(seed=1, patient=5, day=3, purpose=StreamPurpose.JITTER, sub=4),
        first_draws(seed=1, patient=2, day=4, purpose=StreamPurpose.JITTER, sub=4),
        first_draws(seed=1, patient=2, day=3, purpose=StreamPurpose.SPLIT, sub=4),
        first_draws(seed=1, patient=2, day=3, purpose=StreamPurpose.JITTER, sub=5),
    ]
    assert all(v != base for v in variants)
    assert len({tuple(v) for v in [base, *variants]}) == 6


def test_stream_key_positions_do_not_alias() -> None:
    # (patient 1, day 2) and (patient 2, day 1) must not be the same stream.
    assert first_draws(patient=1, day=2) != first_draws(patient=2, day=1)
    assert first_draws(patient=0, day=0, sub=1) != first_draws(patient=0, day=1, sub=0)


def test_adding_or_removing_a_stream_never_changes_another() -> None:
    def component_a(with_b: bool) -> np.ndarray:
        if with_b:
            b = stream(11, 4, 2, StreamPurpose.MEASUREMENT)
            b.standard_normal(1000)
            c = stream(11, 4, 2, StreamPurpose.INJECTION_C2)
            c.random(77)
        a = stream(11, 4, 2, StreamPurpose.LATENT_AR)
        return a.standard_normal(50)

    assert np.array_equal(component_a(False), component_a(True))
    # At the level of the latent model: bit-identical with and without other streams.
    plain = simulate(seed=11).sbp_mmhg
    stream(11, 0, None, StreamPurpose.ADHERENCE).standard_normal(500)
    stream(11, 0, None, StreamPurpose.MEASUREMENT).standard_normal(500)
    stream(11, 0, None, StreamPurpose.INJECTION_PLAN).random(500)
    assert np.array_equal(plain, simulate(seed=11).sbp_mmhg)


def test_stream_seed_boundaries() -> None:
    assert first_draws(seed=0) != first_draws(seed=1)
    top = 2**64 - 1
    assert len(first_draws(seed=top)) == 5
    assert first_draws(seed=top) != first_draws(seed=top - 1)
    with pytest.raises(StreamKeyError):
        stream(2**64, 0, None, StreamPurpose.PATIENT)
    with pytest.raises(StreamKeyError):
        stream(-1, 0, None, StreamPurpose.PATIENT)  # a negative seed is refused


@pytest.mark.parametrize("bad", [True, np.True_, 1.0, "0", np.float64(2.0), 1 + 0j])
def test_stream_refuses_non_integer_keys(bad: object) -> None:
    purpose = StreamPurpose.PATIENT
    with pytest.raises(StreamKeyError):
        stream(bad, 0, None, purpose)  # type: ignore[arg-type]
    with pytest.raises(StreamKeyError):
        stream(0, bad, None, purpose)  # type: ignore[arg-type]
    with pytest.raises(StreamKeyError):
        stream(0, 0, bad, purpose)  # type: ignore[arg-type]
    with pytest.raises(StreamKeyError):
        stream(0, 0, None, purpose, bad)  # type: ignore[arg-type]


def test_stream_accepts_numpy_integers_like_python_ints() -> None:
    assert (
        first_draws(seed=3, patient=4)
        == stream(np.int64(3), np.int32(4), None, StreamPurpose.LATENT_AR, np.uint8(0))
        .standard_normal(5)
        .tolist()
    )


def test_stream_key_ranges() -> None:
    top = 2**32 - 1
    assert len(first_draws(patient=top)) == 5
    assert len(first_draws(sub=top)) == 5
    assert len(first_draws(day=top - 1)) == 5
    for kwargs in (
        {"patient": top + 1},
        {"patient": -1},
        {"day": top},
        {"day": -1},
        {"sub": top + 1},
        {"sub": -1},
    ):
        with pytest.raises(StreamKeyError):
            first_draws(**kwargs)


@pytest.mark.parametrize("bad", [2, "LATENT_AR", None, 0, 13, 1.0, True])
def test_stream_purpose_must_be_a_member(bad: object) -> None:
    with pytest.raises(StreamKeyError):
        stream(0, 0, None, bad, 0)  # type: ignore[arg-type]


def test_stream_spawn_key_words_are_32_bit() -> None:
    ss = stream_seed_sequence(
        0, 2**32 - 1, 2**32 - 2, StreamPurpose.CONFOUNDER, 2**32 - 1
    )
    assert len(ss.spawn_key) == 4
    assert all(0 <= w < 2**32 for w in ss.spawn_key)


def test_stream_does_not_touch_global_random_state() -> None:
    np_state = np.random.get_state()
    py_state = random.getstate()
    stream(0, 0, None, StreamPurpose.PATIENT).standard_normal(10)
    simulate()
    after = np.random.get_state()
    assert after[0] == np_state[0]
    assert np.array_equal(after[1], np_state[1])
    assert after[2:] == np_state[2:]
    assert random.getstate() == py_state


def test_stream_returns_independent_generators() -> None:
    g1 = stream(0, 0, None, StreamPurpose.PATIENT)
    g2 = stream(0, 0, None, StreamPurpose.PATIENT)
    assert isinstance(g1, np.random.Generator) and g1 is not g2
    g1.standard_normal(100)
    assert g2.standard_normal(3).tolist() == first_draws(
        0, 0, None, StreamPurpose.PATIENT, 0, 3
    )


def test_stream_is_stable_across_processes_and_hash_seeds() -> None:
    code = (
        "from ralmon.benchmark.rng import StreamPurpose, stream\n"
        "print(stream(5, 6, 7, StreamPurpose.INJECTION_C3, 8).standard_normal(3).tolist())"
    )
    outputs = []
    for hash_seed in ("1", "2"):
        env = {**os.environ, "PYTHONHASHSEED": hash_seed}
        done = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            env=env,
            check=True,
        )
        outputs.append(done.stdout.strip())
    assert outputs[0] == outputs[1]
    assert outputs[0] == str(first_draws(5, 6, 7, StreamPurpose.INJECTION_C3, 8, 3))


# ---------------------------------------------------------------------------
# Circadian component
# ---------------------------------------------------------------------------


def test_circadian_hand_values() -> None:
    t = np.array([12 * HOUR, 0, 6 * HOUR, 18 * HOUR], dtype=np.int64)
    value = BASE + circadian(t, AMP, PEAK_NOON)
    assert value[0] == pytest.approx(BASE + AMP, abs=1e-9)  # 12:00, the peak
    assert value[1] == pytest.approx(BASE - AMP, abs=1e-9)  # 00:00, the trough
    assert value[2] == pytest.approx(BASE, abs=1e-9)  # 06:00
    assert value[3] == pytest.approx(BASE, abs=1e-9)  # 18:00
    grid = np.arange(0, DAY, 900_000, dtype=np.int64)  # 96 points of one period
    assert float(np.mean(BASE + circadian(grid, AMP, PEAK_NOON))) == pytest.approx(
        BASE, abs=1e-9
    )


def test_circadian_amplitude_is_half_the_peak_to_trough_difference() -> None:
    grid = np.arange(0, DAY, 900_000, dtype=np.int64)
    values = circadian(grid, AMP, PEAK_NOON)
    assert float(values.max() - values.min()) == pytest.approx(2.0 * AMP, abs=1e-9)
    assert float(values.max()) == pytest.approx(AMP, abs=1e-9)
    assert float(values.min()) == pytest.approx(-AMP, abs=1e-9)


def test_circadian_peak_clock_moves_the_whole_curve() -> None:
    peak = 15 * HOUR + 1_800_000  # fixture: 15:30
    t = np.array([peak, peak + 12 * HOUR - DAY, peak + 6 * HOUR - DAY], dtype=np.int64)
    values = circadian(t, AMP, peak)
    assert values[0] == pytest.approx(AMP, abs=1e-9)
    assert t[1] == 3 * HOUR + 1_800_000  # 03:30, the nocturnal trough
    assert values[1] == pytest.approx(-AMP, abs=1e-9)
    assert values[2] == pytest.approx(0.0, abs=1e-9)
    assert circadian(np.array([0]), AMP, 0)[0] == pytest.approx(AMP, abs=1e-9)


def test_circadian_is_periodic_on_the_integer_axis() -> None:
    t = np.arange(0, DAY, 7 * HOUR + 123, dtype=np.int64)
    base = circadian(t, AMP, 5 * HOUR)
    for k in (1, 2, 40):
        assert np.array_equal(base, circadian(t + k * DAY, AMP, 5 * HOUR))
    assert circadian(np.array([-12 * HOUR]), AMP, 0)[0] == pytest.approx(-AMP, abs=1e-9)


def test_circadian_zero_amplitude_and_empty_grid() -> None:
    t = np.arange(0, DAY, HOUR, dtype=np.int64)
    assert np.array_equal(circadian(t, 0.0, PEAK_NOON), np.zeros(len(t)))
    assert circadian(np.array([], dtype=np.int64), AMP, 0).shape == (0,)


@pytest.mark.parametrize("peak", [-1, DAY, 2 * DAY, 1.5, True, "0", None])
def test_circadian_peak_clock_must_be_a_time_of_day(peak: object) -> None:
    with pytest.raises(LatentModelError):
        circadian(np.array([0]), AMP, peak)  # type: ignore[arg-type]


def test_circadian_peak_clock_boundaries() -> None:
    assert circadian(np.array([0]), AMP, 0)[0] == pytest.approx(AMP)
    assert circadian(np.array([DAY - 1]), AMP, DAY - 1)[0] == pytest.approx(AMP)


@pytest.mark.parametrize("amp", [-1.0, math.nan, math.inf])
def test_circadian_amplitude_must_be_finite_and_non_negative(amp: float) -> None:
    with pytest.raises(LatentModelError):
        circadian(np.array([0]), amp, 0)


def test_circadian_times_must_be_integers() -> None:
    with pytest.raises(LatentModelError):
        circadian(np.array([0.0, 1.0]), AMP, 0)


# ---------------------------------------------------------------------------
# Closed forms
# ---------------------------------------------------------------------------


def test_ar_innovation_sd_closed_form() -> None:
    assert innovation_sd(8.0, 0.6) == pytest.approx(
        6.4, abs=1e-12
    )  # 8 * sqrt(1 - 0.36)
    assert innovation_sd(8.0, -0.6) == pytest.approx(6.4, abs=1e-12)
    assert innovation_sd(8.0, 0.0) == 8.0
    assert innovation_sd(0.0, 0.6) == 0.0
    near = innovation_sd(8.0, 1.0 - 1e-12)
    assert 0.0 < near < 1e-2


@pytest.mark.parametrize(
    ("sd", "phi"),
    [
        (-1.0, 0.5),
        (math.nan, 0.5),
        (math.inf, 0.5),
        (1.0, 1.0),
        (1.0, -1.0),
        (1.0, math.nan),
    ],
)
def test_ar_innovation_sd_rejects_invalid(sd: float, phi: float) -> None:
    with pytest.raises(LatentModelError):
        innovation_sd(sd, phi)


def test_rescale_ar1_phi() -> None:
    assert rescale_ar1_phi(0.5, ref_step_ms=2, step_ms=1) == pytest.approx(
        0.7071067811865476, abs=1e-15
    )
    assert rescale_ar1_phi(0.5, ref_step_ms=1, step_ms=1) == 0.5
    assert rescale_ar1_phi(0.5, ref_step_ms=1, step_ms=2) == pytest.approx(
        0.25, abs=1e-15
    )


def test_rescale_ar1_phi_boundaries() -> None:
    assert rescale_ar1_phi(0.0, 1, 3) == 0.0
    assert rescale_ar1_phi(0.0, 3, 1) == 0.0
    # Negative phi: only an integer multiple of the reference step has a real value.
    assert rescale_ar1_phi(-0.5, 1, 1) == -0.5
    assert rescale_ar1_phi(-0.5, 1, 2) == pytest.approx(0.25, abs=1e-15)
    assert rescale_ar1_phi(-0.5, 1, 3) == pytest.approx(-0.125, abs=1e-15)
    for ref, step in ((2, 1), (3, 2), (2, 3)):
        with pytest.raises(LatentModelError):
            rescale_ar1_phi(-0.5, ref, step)
    near = rescale_ar1_phi(1.0 - 1e-9, 1, 2)
    assert 0.0 < near < 1.0
    assert abs(rescale_ar1_phi(-(1.0 - 1e-9), 1, 1)) < 1.0


@pytest.mark.parametrize("phi", [1.0, -1.0, 2.0, math.nan, math.inf])
def test_rescale_ar1_phi_rejects_non_stationary(phi: float) -> None:
    with pytest.raises(LatentModelError):
        rescale_ar1_phi(phi, 1, 1)


@pytest.mark.parametrize("ref", [0, -1, 1.5, True, "1"])
def test_rescale_ar1_phi_rejects_bad_steps(ref: object) -> None:
    with pytest.raises(LatentModelError):
        rescale_ar1_phi(0.5, ref, 1)  # type: ignore[arg-type]
    with pytest.raises(LatentModelError):
        rescale_ar1_phi(0.5, 1, ref)  # type: ignore[arg-type]


@given(
    phi=st.floats(min_value=0.0, max_value=0.999, allow_nan=False),
    a=st.integers(min_value=1, max_value=10),
    b=st.integers(min_value=1, max_value=10),
    c=st.integers(min_value=1, max_value=10),
)
@settings(max_examples=60, deadline=None)
def test_rescale_ar1_phi_composes(phi: float, a: int, b: int, c: int) -> None:
    # Rescaling a -> b and then b -> c equals rescaling a -> c (same continuous process).
    direct = rescale_ar1_phi(phi, a, c)
    via = rescale_ar1_phi(rescale_ar1_phi(phi, a, b), b, c)
    assert via == pytest.approx(direct, abs=1e-9)
    assert 0.0 <= direct < 1.0


# ---------------------------------------------------------------------------
# The simulated trace
# ---------------------------------------------------------------------------


def test_no_noise_trace_equals_baseline_plus_circadian() -> None:
    result = simulate(make_params(ar_noise_sd_mmhg=0.0))
    expected = BASE + circadian(result.t_ms, AMP, PEAK_NOON)
    assert np.array_equal(result.sbp_mmhg, expected)  # exactly, not approximately
    assert np.array_equal(result.ar_noise_mmhg, np.zeros(96))


def test_trace_is_baseline_plus_circadian_plus_noise_in_this_order() -> None:
    result = simulate(seed=4)
    rebuilt = (BASE + result.circadian_mmhg) + result.ar_noise_mmhg
    assert np.array_equal(result.sbp_mmhg, rebuilt)
    assert np.array_equal(result.circadian_mmhg, circadian(result.t_ms, AMP, PEAK_NOON))


def test_zero_amplitude_trace_is_baseline_plus_noise() -> None:
    result = simulate(make_params(circadian_amplitude_mmhg=0.0), seed=5)
    assert np.array_equal(result.circadian_mmhg, np.zeros(96))
    assert np.array_equal(result.sbp_mmhg, BASE + result.ar_noise_mmhg)


def test_zero_noise_and_zero_amplitude_is_the_constant_baseline() -> None:
    result = simulate(make_params(circadian_amplitude_mmhg=0.0, ar_noise_sd_mmhg=0.0))
    assert np.array_equal(result.sbp_mmhg, np.full(96, BASE))


def test_determinism_for_a_fixed_seed() -> None:
    one, two = simulate(seed=9), simulate(seed=9)
    assert np.array_equal(one.sbp_mmhg, two.sbp_mmhg)
    assert not np.array_equal(one.sbp_mmhg, simulate(seed=10).sbp_mmhg)


def test_the_generator_is_consumed_one_draw_per_grid_point() -> None:
    # A caller can rely on this: n points use exactly n standard normals, whatever the
    # parameters (a zero noise SD still consumes them), so an extra component added later
    # on the same stream never shifts these.
    for params in (make_params(), make_params(ar_noise_sd_mmhg=0.0)):
        used = stream(1, 1, None, StreamPurpose.LATENT_AR)
        simulate_baseline_sbp(params, 900_000, 1, PEAK_NOON, 900_000, used)
        control = stream(1, 1, None, StreamPurpose.LATENT_AR)
        control.standard_normal(96)
        assert used.random() == control.random()


def test_ar_state_continues_across_midnight() -> None:
    whole = simulate(n_days=2, seed=5)
    rng = stream(5, 0, None, StreamPurpose.LATENT_AR)
    day1 = simulate_baseline_sbp(make_params(), 900_000, 1, PEAK_NOON, 900_000, rng)
    day2 = simulate_baseline_sbp(
        make_params(),
        900_000,
        1,
        PEAK_NOON,
        900_000,
        rng,
        start_day=1,
        ar_state_mmhg=float(day1.ar_noise_mmhg[-1]),
    )
    for name in ("t_ms", "circadian_mmhg", "ar_noise_mmhg", "sbp_mmhg"):
        joined = np.concatenate([getattr(day1, name), getattr(day2, name)])
        assert np.array_equal(joined, getattr(whole, name)), name
    assert day2.t_ms[0] == DAY  # the continuing axis: no reset of time at midnight


def test_without_a_carried_state_the_day_restarts_from_its_stationary_law() -> None:
    rng = stream(5, 0, None, StreamPurpose.LATENT_AR)
    simulate_baseline_sbp(make_params(), 900_000, 1, PEAK_NOON, 900_000, rng)
    cold = simulate_baseline_sbp(
        make_params(), 900_000, 1, PEAK_NOON, 900_000, rng, start_day=1
    )
    whole = simulate(n_days=2, seed=5)
    assert not np.array_equal(cold.ar_noise_mmhg, whole.ar_noise_mmhg[96:])


def test_start_day_shifts_the_axis_and_keeps_the_clock_phase() -> None:
    d0 = simulate(make_params(ar_noise_sd_mmhg=0.0))
    d3 = simulate(make_params(ar_noise_sd_mmhg=0.0), start_day=3)
    assert np.array_equal(d3.t_ms, d0.t_ms + 3 * DAY)
    assert np.array_equal(d3.sbp_mmhg, d0.sbp_mmhg)  # the circadian phase is clock time


def test_grid_is_integer_ms_and_step_divides_day() -> None:
    result = simulate(step=900_000)
    assert result.t_ms.dtype == np.int64
    assert len(result.t_ms) == len(result.sbp_mmhg) == 96
    assert result.t_ms[:3].tolist() == [0, 900_000, 1_800_000]
    assert result.t_ms[-1] == DAY - 900_000  # half-open: 24:00 is the next day's step 0
    assert np.all(np.diff(result.t_ms) == 900_000)
    assert result.sbp_mmhg.dtype == np.float64


@pytest.mark.parametrize("step", [7, 1_000_000, 86_400_001, 2 * DAY, 3 * DAY])
def test_a_step_that_does_not_divide_the_day_is_refused(step: int) -> None:
    with pytest.raises(LatentModelError):
        simulate(step=step)


def test_horizon_of_one_point_and_step_equal_to_the_day() -> None:
    result = simulate(step=DAY)
    assert result.t_ms.tolist() == [0]
    assert result.sbp_mmhg.shape == (1,)
    assert math.isfinite(float(result.sbp_mmhg[0]))
    two = simulate(step=DAY, n_days=2)
    assert two.t_ms.tolist() == [0, DAY]


def test_step_larger_than_the_horizon_is_refused_not_truncated() -> None:
    with pytest.raises(LatentModelError):
        simulate(step=2 * DAY, n_days=1)


def _divisors_of_the_day_with_few_points() -> list[int]:
    # K = DAY / step points per day, for the K <= 2000 that divide the day.
    return [DAY // k for k in range(1, 2001) if DAY % k == 0]


@given(
    step=st.sampled_from(_divisors_of_the_day_with_few_points()),
    n_days=st.integers(min_value=1, max_value=3),
)
@settings(max_examples=40, deadline=None)
def test_grid_length_and_order_property(step: int, n_days: int) -> None:
    result = simulate(step=step, n_days=n_days)
    assert len(result.t_ms) == n_days * DAY // step
    assert len(result.sbp_mmhg) == len(result.t_ms)
    assert result.t_ms[0] == 0
    assert np.all(np.diff(result.t_ms) > 0)
    assert np.all(result.t_ms % step == 0)
    assert result.t_ms[-1] == n_days * DAY - step


@pytest.mark.parametrize("bad", [0, -900_000, 1.5, True, "900000", None])
def test_step_must_be_a_positive_integer(bad: object) -> None:
    with pytest.raises(LatentModelError):
        simulate(step=bad)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [0, -1, 1.5, True, None])
def test_n_days_must_be_a_positive_integer(bad: object) -> None:
    with pytest.raises(LatentModelError):
        simulate(n_days=bad)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [-1, 1.5, True])
def test_start_day_must_be_a_non_negative_integer(bad: object) -> None:
    with pytest.raises(LatentModelError):
        simulate(start_day=bad)


def test_numpy_integers_are_accepted_for_step_and_days() -> None:
    a = simulate(step=900_000, n_days=2)
    b = simulate(step=np.int64(900_000), n_days=np.int64(2))  # type: ignore[arg-type]
    assert np.array_equal(a.sbp_mmhg, b.sbp_mmhg)


def test_generated_arrays_are_bounded_for_a_stated_horizon() -> None:
    # Stated bound: one day at a 15-minute step is 96 points, 768 bytes per array.
    result = simulate(step=900_000)
    for array in (
        result.t_ms,
        result.circadian_mmhg,
        result.ar_noise_mmhg,
        result.sbp_mmhg,
    ):
        assert array.size == 96
        assert array.nbytes <= 96 * 8
    # A per-millisecond day (86 400 000 points, 691 MB per array) is refused before any
    # allocation: the grid size is checked first, and the guard sits well below a day of
    # milliseconds.
    assert MAX_GRID_POINTS < DAY
    tracemalloc.start()
    try:
        with pytest.raises(LatentModelError, match="grid"):
            simulate(step=1)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 1_000_000  # bytes: nothing near a grid was allocated


def test_the_grid_size_guard_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(latent_module, "MAX_GRID_POINTS", 96)
    assert len(simulate(step=900_000).t_ms) == 96  # exactly at the bound: allowed
    with pytest.raises(LatentModelError, match="grid"):
        simulate(step=900_000, n_days=2)  # 192 points: refused
    monkeypatch.setattr(latent_module, "MAX_GRID_POINTS", 95)
    with pytest.raises(LatentModelError, match="grid"):
        simulate(step=900_000)


def test_the_grid_size_guard_cannot_be_dodged_with_many_days() -> None:
    with pytest.raises(LatentModelError, match="grid"):
        simulate(step=900_000, n_days=10**9)  # 9.6e10 points


# -- invalid parameters --------------------------------------------------------


@pytest.mark.parametrize(
    "phi", [1.0, -1.0, 1.0001, -1.5, 2.0, math.nan, math.inf, -math.inf]
)
def test_invalid_ar_parameters_rejected(phi: float) -> None:
    with pytest.raises(LatentModelError):
        simulate(make_params(ar_noise_phi=phi))


@pytest.mark.parametrize("sd", [-0.1, -1.0, math.nan, math.inf])
def test_invalid_ar_sd_rejected(sd: float) -> None:
    with pytest.raises(LatentModelError):
        simulate(make_params(ar_noise_sd_mmhg=sd))


@pytest.mark.parametrize("baseline", [0.0, -1.0, -130.0, math.nan, math.inf])
def test_baseline_must_be_positive_and_finite(baseline: float) -> None:
    # The prior domain of baseline_sbp_mmhg is strictly positive; the generator mirrors it.
    with pytest.raises(LatentModelError):
        simulate(make_params(baseline_sbp_mmhg=baseline))


@pytest.mark.parametrize("amp", [-0.1, math.nan, math.inf])
def test_amplitude_must_be_non_negative_and_finite(amp: float) -> None:
    with pytest.raises(LatentModelError):
        simulate(make_params(circadian_amplitude_mmhg=amp))


@pytest.mark.parametrize("bad", [math.nan, math.inf, "0"])
def test_carried_ar_state_must_be_finite(bad: object) -> None:
    with pytest.raises(LatentModelError):
        simulate(ar_state_mmhg=bad)


@pytest.mark.parametrize("ref", [0, -1, 1.5, True])
def test_reference_step_must_be_a_positive_integer(ref: object) -> None:
    with pytest.raises(LatentModelError):
        simulate(ref_step=ref)  # type: ignore[arg-type]


def test_a_negative_phi_with_a_non_integer_step_ratio_is_refused() -> None:
    with pytest.raises(LatentModelError):
        simulate(make_params(ar_noise_phi=-0.5), step=900_000, ref_step=1_800_000)


def test_the_rng_must_be_a_generator() -> None:
    with pytest.raises(LatentModelError):
        simulate_baseline_sbp(make_params(), 900_000, 1, 0, 900_000, 0)  # type: ignore[arg-type]
    with pytest.raises(LatentModelError):
        simulate_baseline_sbp(
            make_params(),
            900_000,
            1,
            0,
            900_000,
            np.random.RandomState(0),  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("phi", [0.0, 1.0 - 1e-9, -(1.0 - 1e-9), 1e-300])
def test_phi_at_zero_and_near_the_bounds_gives_finite_values(phi: float) -> None:
    result = simulate(make_params(ar_noise_phi=phi), seed=2)
    assert np.all(np.isfinite(result.sbp_mmhg))
    assert np.all(np.isfinite(result.ar_noise_mmhg))


def test_phi_zero_is_white_noise_with_the_stationary_sd() -> None:
    z = stream(0, 0, None, StreamPurpose.LATENT_AR).standard_normal(96)
    result = simulate(make_params(ar_noise_phi=0.0), seed=0)
    assert np.array_equal(result.ar_noise_mmhg, SD * z)


def test_first_point_is_the_stationary_draw_and_the_recursion_follows() -> None:
    z = stream(0, 0, None, StreamPurpose.LATENT_AR).standard_normal(4)
    x = simulate(make_params(), seed=0).ar_noise_mmhg
    s = innovation_sd(SD, PHI)
    assert x[0] == pytest.approx(SD * z[0], abs=1e-12)
    assert x[1] == pytest.approx(PHI * x[0] + s * z[1], abs=1e-12)
    assert x[2] == pytest.approx(PHI * x[1] + s * z[2], abs=1e-12)
    assert x[3] == pytest.approx(PHI * x[2] + s * z[3], abs=1e-12)


def test_values_finite_and_not_clipped() -> None:
    # A small baseline with a large noise SD drives the trace below zero: nothing clips it.
    params = make_params(baseline_sbp_mmhg=1.0, ar_noise_sd_mmhg=50.0)
    result = simulate(params, seed=3, n_days=2)
    assert np.all(np.isfinite(result.sbp_mmhg))
    assert float(result.sbp_mmhg.min()) < 0.0
    assert np.array_equal(
        result.sbp_mmhg, (1.0 + result.circadian_mmhg) + result.ar_noise_mmhg
    )


def test_result_arrays_are_read_only() -> None:
    result = simulate()
    for array in (
        result.t_ms,
        result.circadian_mmhg,
        result.ar_noise_mmhg,
        result.sbp_mmhg,
    ):
        with pytest.raises(ValueError, match="read-only"):
            array[0] = 0


def test_latent_trace_unchanged_by_other_streams() -> None:
    plain = simulate(seed=21, n_days=2)
    for purpose in (
        StreamPurpose.ADHERENCE,
        StreamPurpose.MEASUREMENT,
        StreamPurpose.INJECTION_PLAN,
        StreamPurpose.INJECTION_C1,
        StreamPurpose.INJECTION_C2,
        StreamPurpose.INJECTION_C3,
    ):
        for patient in (0, 1):
            stream(21, patient, None, purpose).standard_normal(10_000)
    with_others = simulate(seed=21, n_days=2)
    assert np.array_equal(plain.sbp_mmhg, with_others.sbp_mmhg)
    assert np.array_equal(plain.ar_noise_mmhg, with_others.ar_noise_mmhg)


# -- statistics, seeded Monte Carlo with tolerances in standard errors ----------

N_LONG = 200_000
LONG_STEP = DAY // 200  # 432 000 ms, 200 points per day
LONG_DAYS = N_LONG // 200


@pytest.mark.parametrize(
    ("phi", "ref_factor"),
    [(0.6, 1), (0.6, 2), (-0.6, 1), (0.0, 1), (0.95, 1)],
)
def test_ar_stationary_variance_and_lag1_autocorrelation(
    phi: float, ref_factor: int
) -> None:
    # ref_factor 2: the coefficient is given at twice the generator step and rescaled.
    params = make_params(
        baseline_sbp_mmhg=BASE,
        circadian_amplitude_mmhg=0.0,
        ar_noise_phi=phi,
    )
    result = simulate(
        params,
        step=LONG_STEP,
        n_days=LONG_DAYS,
        ref_step=LONG_STEP * ref_factor,
        seed=0,
    )
    x = result.sbp_mmhg - BASE
    assert len(x) == N_LONG
    phi_step = rescale_ar1_phi(phi, LONG_STEP * ref_factor, LONG_STEP)
    # Asymptotic standard errors of a Gaussian AR(1) sample (variance about the known zero
    # mean; lag-1 autocorrelation, Bartlett): se(var) = sd^2 sqrt(2 (1 + phi^2) / (1 - phi^2) / N),
    # se(r1) = sqrt((1 - phi^2) / N).
    se_var = SD**2 * math.sqrt(2.0 * (1.0 + phi_step**2) / (1.0 - phi_step**2) / N_LONG)
    se_r1 = math.sqrt((1.0 - phi_step**2) / N_LONG)
    variance = float(np.mean(x * x))
    r1 = float(np.sum(x[:-1] * x[1:]) / np.sum(x * x))
    assert abs(variance - SD**2) < 4.0 * se_var
    assert abs(r1 - phi_step) < 4.0 * se_r1


def test_ar_ensemble_starts_in_the_stationary_law() -> None:
    n = 2000
    step = 6 * HOUR
    first = np.empty((n, 6))
    for i in range(n):
        r = simulate(
            make_params(circadian_amplitude_mmhg=0.0),
            step=step,
            n_days=2,
            sub_index=i,
        )
        first[i] = r.sbp_mmhg[:6] - BASE
    se_var = SD**2 * math.sqrt(2.0 / n)
    se_mean = SD / math.sqrt(n)
    for k in range(6):  # no transient: every early point has the stationary variance
        assert abs(float(np.mean(first[:, k]))) < 4.0 * se_mean
        assert abs(float(np.mean(first[:, k] ** 2)) - SD**2) < 4.0 * se_var
    # and the lag-1 covariance of the very first pair is phi * sd^2
    cov = float(np.mean(first[:, 0] * first[:, 1]))
    phi_step = rescale_ar1_phi(PHI, step, step)
    se_cov = SD**2 * math.sqrt((1.0 + phi_step**2) / n)
    assert abs(cov - phi_step * SD**2) < 4.0 * se_cov


def test_circadian_ensemble_mean_and_minimum_position() -> None:
    n = 400
    runs = np.stack(
        [simulate(step=HOUR, sub_index=i, seed=1).sbp_mmhg for i in range(n)]
    )
    t = np.arange(0, DAY, HOUR, dtype=np.int64)
    expected = BASE + circadian(t, AMP, PEAK_NOON)
    se = SD / math.sqrt(n)  # independent runs, stationary marginal SD
    mean = runs.mean(axis=0)
    assert np.all(np.abs(mean - expected) < 4.0 * se)
    # the trough is at 00:00 (peak 12:00 plus half a day) and the peak at 12:00
    assert abs(float(mean[0]) - (BASE - AMP)) < 4.0 * se
    assert abs(float(mean[12]) - (BASE + AMP)) < 4.0 * se
    assert float(mean[12] - mean[0]) > 2.0 * AMP - 8.0 * se


def test_values_move_with_the_circadian_phase_not_the_day_index() -> None:
    quiet = make_params(ar_noise_sd_mmhg=0.0)
    two = simulate(quiet, n_days=2, step=HOUR)
    assert np.array_equal(two.sbp_mmhg[:24], two.sbp_mmhg[24:])


# -- integration with the prior and the design file ------------------------------


def test_latent_pressure_from_a_fixture_prior(tmp_path: Path) -> None:
    prior = LiteraturePriorSource(make_fixture_prior(tmp_path), allow_fixture_only=True)
    patient = prior.sample_patient(stream(0, 7, None, StreamPurpose.PATIENT), 7)
    ref = prior.reference_step_ms("ar_noise_phi")
    assert ref == 60_000  # fixture-only reference step
    rng = stream(0, 7, None, StreamPurpose.LATENT_AR)
    result = simulate_baseline_sbp(patient, 900_000, 1, PEAK_NOON, ref, rng)
    assert len(result.t_ms) == 96 and np.all(np.isfinite(result.sbp_mmhg))
    again = simulate_baseline_sbp(
        patient, 900_000, 1, PEAK_NOON, ref, stream(0, 7, None, StreamPurpose.LATENT_AR)
    )
    assert np.array_equal(result.sbp_mmhg, again.sbp_mmhg)
    # the patient draw consumed the PATIENT stream only
    assert 90.0 <= patient.baseline_sbp_mmhg <= 110.0  # the fixture uniform(90, 110)


def test_unfilled_reference_step_is_refused_by_the_prior(tmp_path: Path) -> None:
    prior = LiteraturePriorSource(
        make_fixture_prior(tmp_path, unfilled=["ar_noise_phi"]),
        strict=False,
        allow_fixture_only=True,
    )
    with pytest.raises(UnfilledParameterError):
        prior.reference_step_ms("ar_noise_phi")


def test_design_file_holds_the_circadian_peak_row_awaiting_a_human() -> None:
    rows = {r.parameter: r for r in load_design_file(DESIGN_FILE).rows}
    row = rows["circadian_peak_clock_ms"]
    assert row.value is None and row.distribution is None
    assert row.status == "awaiting_human_value"
    assert row.verified_by is None and row.source_ref is None
    assert row.source_type == "published_literature"
    assert row.unit == "ms"
    assert row.consumer_task == "WS04-T03"
    note = " ".join(row.note.split()).lower()
    # The amplitude convention is stated in the row a human transcribes a source into.
    assert "half" in note and "peak-to-trough" in note
    assert "cos" in note and "circadian_amplitude_mmhg" in note
    # No agent chose a number: nothing but null values in this file.
    document = yaml.safe_load(DESIGN_FILE.read_text(encoding="utf-8"))
    assert all(r["value"] is None and r["dist"] is None for r in document["parameters"])


def test_provenance_table_lists_the_circadian_peak_row() -> None:
    assert "circadian_peak_clock_ms" in TABLE.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Randomness discipline of the benchmark package (AST scan)
# ---------------------------------------------------------------------------

ALLOWED_NUMPY_RANDOM = {
    "Generator",
    "SeedSequence",
    "default_rng",
    "PCG64",
    "BitGenerator",
}
WALL_CLOCK_MODULES = {"time", "datetime"}


def _attribute_chain(node: ast.AST) -> list[str] | None:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return parts[::-1]
    return None


def randomness_violations(source: str) -> list[str]:
    """Unseeded or global randomness, and wall-clock imports, found in ``source``."""
    problems: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root == "random" or root in WALL_CLOCK_MODULES:
                    problems.append(f"{node.lineno}: import {alias.name}")
                if alias.name == "numpy.random":
                    problems.append(f"{node.lineno}: import numpy.random")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.split(".")[0] in {"random", *WALL_CLOCK_MODULES}:
                problems.append(f"{node.lineno}: from {module} import ...")
            if module == "numpy.random":
                for alias in node.names:
                    if alias.name not in ALLOWED_NUMPY_RANDOM:
                        problems.append(
                            f"{node.lineno}: from numpy.random import {alias.name}"
                        )
            if module == "numpy" and any(a.name == "random" for a in node.names):
                problems.append(f"{node.lineno}: from numpy import random")
        elif isinstance(node, ast.Attribute):
            chain = _attribute_chain(node)
            if (
                chain
                and len(chain) >= 3
                and chain[0] in {"np", "numpy"}
                and chain[1] == "random"
                and chain[2] not in ALLOWED_NUMPY_RANDOM
                and len(chain) == 3
            ):
                problems.append(f"{node.lineno}: {'.'.join(chain)}")
        elif isinstance(node, ast.Call):
            func = node.func
            name = (
                func.attr
                if isinstance(func, ast.Attribute)
                else getattr(func, "id", "")
            )
            if name == "default_rng":
                no_args = not node.args and not node.keywords
                none_arg = len(node.args) == 1 and (
                    isinstance(node.args[0], ast.Constant)
                    and node.args[0].value is None
                )
                if no_args or none_arg:
                    problems.append(f"{node.lineno}: default_rng() without a seed")
    return problems


def test_randomness_scanner_flags_and_allows_the_right_code() -> None:
    assert (
        randomness_violations("import numpy as np\ng = np.random.default_rng(3)\n")
        == []
    )
    assert (
        randomness_violations("import numpy as np\ns = np.random.SeedSequence(3)\n")
        == []
    )
    assert randomness_violations("rng.random()\nrng.normal()\n") == []
    for bad in (
        "import numpy as np\nnp.random.seed(0)\n",
        "import numpy as np\nnp.random.normal()\n",
        "import numpy as np\nnp.random.rand(3)\n",
        "import numpy\nnumpy.random.random()\n",
        "import numpy as np\nnp.random.default_rng()\n",
        "import numpy as np\nnp.random.default_rng(None)\n",
        "from numpy.random import default_rng\ndefault_rng()\n",
        "from numpy.random import normal\n",
        "from numpy import random\n",
        "import numpy.random as npr\n",
        "import random\n",
        "from random import choice\n",
        "import time\n",
        "from datetime import datetime\n",
    ):
        assert randomness_violations(bad), bad


def test_no_unseeded_randomness_in_benchmark_package() -> None:
    offenders = []
    for path in sorted(BENCHMARK_SRC.rglob("*.py")):
        for problem in randomness_violations(path.read_text(encoding="utf-8")):
            offenders.append(f"{path.name}:{problem}")
    assert offenders == []
    assert {p.name for p in BENCHMARK_SRC.glob("*.py")} >= {"rng.py", "latent.py"}


def test_t_day_is_24_hours_in_ms() -> None:
    assert T_DAY_MS == DAY == 24 * HOUR


def test_rescale_that_rounds_to_one_is_refused() -> None:
    # (1 - 2^-53) ** (1 / 10^9) is 1.0 in floating point: not a stationary coefficient.
    with pytest.raises(LatentModelError):
        rescale_ar1_phi(1.0 - 2.0**-53, 10**9, 1)


def test_ar_state_property_continues_a_run() -> None:
    first = simulate(seed=8)
    assert first.ar_state_mmhg == float(first.ar_noise_mmhg[-1])
    rng = stream(8, 0, None, StreamPurpose.LATENT_AR)
    a = simulate_baseline_sbp(make_params(), 900_000, 1, PEAK_NOON, 900_000, rng)
    b = simulate_baseline_sbp(
        make_params(),
        900_000,
        1,
        PEAK_NOON,
        900_000,
        rng,
        start_day=1,
        ar_state_mmhg=a.ar_state_mmhg,
    )
    assert np.array_equal(
        np.concatenate([a.sbp_mmhg, b.sbp_mmhg]), simulate(seed=8, n_days=2).sbp_mmhg
    )
