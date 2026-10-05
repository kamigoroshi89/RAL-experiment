"""Adherence Markov model, schedule and its derivation rule (WS04-T05).

Every number below is arithmetic and FIXTURE-ONLY (probabilities 0.2, 0.1, 0.1, mean delay 1 h,
dose times 08:00 and 20:00, intake lag 5 s, double-take gap 2 min, ...): none is a clinical
value and none enters a prior file used by the builder. The adherence parameters themselves
are a declared assumption (analisi section 5.1). Horizons are short: the longest run builds
20 000 slots (about 40 000 events), no test builds a per-millisecond grid.

Statistical tolerances are derived, never hard thresholds: a binomial frequency uses
``4 * sqrt(p (1 - p) / n)``; a mean of draws uses ``4 * sd / sqrt(n)`` with the analytic ``sd``;
a mean run length uses the geometric variance. The seeds are fixed, so each run is
deterministic; the width is chosen so that a correct model would pass at any seed with a
probability above 0.9999 per comparison.

Tie rule under test (stated in ``ralmon.benchmark.adherence``): events are sorted by
``(t_device_ms, kind rank, slot order)`` with DISPENSE before INTAKE at equal times.
"""

from __future__ import annotations

import ast
import dataclasses
import math
from collections.abc import Sequence
from fractions import Fraction
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

from ralmon.benchmark import AdherenceParams, LatentDay, LiteraturePriorSource
from ralmon.benchmark import adherence as adherence_module
from ralmon.benchmark import schedule as schedule_module
from ralmon.benchmark.adherence import (
    MAX_SLOTS,
    AdherenceConfig,
    AdherenceConfigError,
    AdherenceModel,
    AdherenceResult,
    AdherenceState,
    BehaviourEntry,
    adherence_stream,
    load_adherence_config,
    sample_delay_ms,
    truncated_exponential,
)
from ralmon.benchmark.latent import T_DAY_MS
from ralmon.benchmark.priors import (
    SOURCE_TYPES,
    PriorConfigError,
    UnfilledParameterError,
    load_design_file,
)
from ralmon.benchmark.rng import StreamPurpose, stream
from ralmon.benchmark.schedule import (
    Schedule,
    ScheduleError,
    ScheduleInfeasibleError,
    ScheduleProblem,
    check_schedule_consistency,
    derive_schedule,
    load_schedule,
)
from ralmon.benchmark.trace import read_truth, write_truth
from ralmon.signals import Event, EventKind

from .conftest import make_fixture_prior

ROOT = Path(__file__).resolve().parents[2]
DESIGN_FILE = ROOT / "configs" / "benchmark" / "generator_design.yaml"
CARE_PLAN_FILE = ROOT / "configs" / "benchmark" / "care_plans.yaml"
TABLE = ROOT / "docs" / "benchmark" / "parameter-provenance.md"

SEC = 1_000
MIN = 60_000
HOUR = 3_600_000
DAY = 86_400_000

LAG = 5 * SEC  # FIXTURE-ONLY
GAP = 2 * MIN  # FIXTURE-ONLY
CFG = AdherenceConfig(intake_lag_ms=LAG, double_take_gap_ms=GAP)
TWO_DOSES = Schedule(dose_ticks_ms=(8 * HOUR, 20 * HOUR), measurement_ticks_ms=())
ON_TIME, DELAYED, OMITTED, DOUBLE_TAKE = (
    AdherenceState.ON_TIME,
    AdherenceState.DELAYED,
    AdherenceState.OMITTED,
    AdherenceState.DOUBLE_TAKE,
)
STATES = (ON_TIME, DELAYED, OMITTED, DOUBLE_TAKE)


def params(
    p_delay: float = 0.0,
    p_omission: float = 0.0,
    p_double_take: float = 0.0,
    mean_delay_ms: int = HOUR,
) -> AdherenceParams:
    return AdherenceParams(p_delay, p_omission, p_double_take, mean_delay_ms)


def run(
    p: AdherenceParams,
    *,
    schedule: Schedule = TWO_DOSES,
    n_days: int = 1,
    seed: int = 0,
    patient: int = 0,
    config: AdherenceConfig = CFG,
    matrix: Sequence[Sequence[float]] | None = None,
    initial: Sequence[float] | None = None,
    **kwargs: Any,
) -> AdherenceResult:
    model = AdherenceModel(
        p, config, transition_matrix=matrix, initial_distribution=initial
    )
    return model.simulate(schedule, n_days, adherence_stream(seed, patient), **kwargs)


def kinds(events: Sequence[Event], kind: EventKind) -> list[int]:
    return [e.t_device_ms for e in events if e.kind is kind]


def tie_key(e: Event) -> tuple[int, int]:
    return (e.t_device_ms, 0 if e.kind is EventKind.DISPENSE else 1)


def state_sequence(result: AdherenceResult) -> list[AdherenceState]:
    return [entry.state for entry in result.behaviour_log]


def binomial_tolerance(p: float, n: int) -> float:
    return 4.0 * math.sqrt(p * (1.0 - p) / n)


# ---------------------------------------------------------------------------
# 1 to 3. Transition matrix
# ---------------------------------------------------------------------------


def test_default_transition_rows_equal_marginals() -> None:
    model = AdherenceModel(params(0.2, 0.1, 0.1), CFG)
    matrix = model.transition_matrix
    assert len(matrix) == 4 and all(len(row) == 4 for row in matrix)
    for row in matrix:
        assert row == pytest.approx([0.6, 0.2, 0.1, 0.1], abs=1e-12)
    assert model.initial_distribution == pytest.approx([0.6, 0.2, 0.1, 0.1], abs=1e-12)
    assert tuple(s.value for s in STATES) == (0, 1, 2, 3)  # the fixed state order
    assert [s.name for s in STATES] == ["ON_TIME", "DELAYED", "OMITTED", "DOUBLE_TAKE"]


def test_the_matrix_is_immutable_data() -> None:
    model = AdherenceModel(params(0.2, 0.1, 0.1), CFG)
    assert isinstance(model.transition_matrix, tuple)
    assert all(isinstance(row, tuple) for row in model.transition_matrix)
    assert isinstance(model.initial_distribution, tuple)


def test_marginals_above_one_rejected() -> None:
    with pytest.raises(AdherenceConfigError, match="exceeds 1"):
        AdherenceModel(params(0.5, 0.4, 0.3), CFG)


def test_marginals_sum_boundary() -> None:
    # sum exactly 1: the on-time probability is 0 (not slightly negative)
    model = AdherenceModel(params(0.5, 0.25, 0.25), CFG)
    assert model.transition_matrix[0] == (0.0, 0.5, 0.25, 0.25)
    with pytest.raises(AdherenceConfigError):
        AdherenceModel(params(0.5, 0.25, 0.25 + 1e-6), CFG)
    # all mass on one state is a valid memoryless chain
    AdherenceModel(params(1.0, 0.0, 0.0), CFG)
    AdherenceModel(params(0.0, 1.0, 0.0), CFG)
    AdherenceModel(params(0.0, 0.0, 1.0), CFG)


@pytest.mark.parametrize("bad", [-0.1, 1.1, float("nan"), float("inf"), True, "0.1"])
def test_each_marginal_must_be_a_probability(bad: object) -> None:
    for position in range(3):
        values: list[Any] = [0.1, 0.1, 0.1]
        values[position] = bad
        with pytest.raises(AdherenceConfigError):
            AdherenceModel(AdherenceParams(*values, HOUR), CFG)


@pytest.mark.parametrize("bad", [-1, 1.5, True, None, "3"])
def test_mean_delay_must_be_a_non_negative_integer(bad: object) -> None:
    with pytest.raises(AdherenceConfigError, match="mean_delay_ms"):
        AdherenceModel(AdherenceParams(0.0, 0.0, 0.0, bad), CFG)  # type: ignore[arg-type]


def test_mean_delay_zero_is_refused_only_when_a_delay_can_occur() -> None:
    AdherenceModel(params(0.0, 0.1, 0.1, mean_delay_ms=0), CFG)  # no delayed state
    with pytest.raises(AdherenceConfigError, match="mean_delay_ms"):
        AdherenceModel(params(0.1, 0.0, 0.0, mean_delay_ms=0), CFG)
    # reachable through a custom matrix or initial law as well
    matrix = [[1.0, 0.0, 0.0, 0.0]] * 3 + [[0.0, 1.0, 0.0, 0.0]]
    with pytest.raises(AdherenceConfigError, match="mean_delay_ms"):
        AdherenceModel(params(mean_delay_ms=0), CFG, transition_matrix=matrix)
    with pytest.raises(AdherenceConfigError, match="mean_delay_ms"):
        AdherenceModel(
            params(mean_delay_ms=0), CFG, initial_distribution=(0.0, 1.0, 0.0, 0.0)
        )


STICKY = (
    (0.6, 0.2, 0.1, 0.1),
    (0.4, 0.4, 0.2, 0.0),
    (0.2, 0.1, 0.6, 0.1),
    (0.5, 0.1, 0.1, 0.3),
)  # FIXTURE-ONLY: irreducible, with one structural zero


def test_custom_transition_matrix_accepted_and_kept() -> None:
    model = AdherenceModel(params(0.1, 0.1, 0.1), CFG, transition_matrix=STICKY)
    assert model.transition_matrix == STICKY
    # rows are accepted when they sum to 1 within a tiny float tolerance
    near = [[0.25 + 1e-12] * 4] * 4
    AdherenceModel(params(), CFG, transition_matrix=near)


@pytest.mark.parametrize(
    "matrix",
    [
        [[0.25] * 4] * 3,  # 3 rows
        [[0.25] * 3] * 4,  # 3 columns
        [[0.25] * 4, [0.25] * 4, [0.25] * 4, [0.25] * 5],  # ragged
        [[0.25] * 4] * 5,  # 5 rows
        [[0.25] * 4, [0.25] * 4, [0.25] * 4, [0.9, 0.0, 0.0, 0.0]],  # row sum 0.9
        [[0.25] * 4, [0.25] * 4, [0.25] * 4, [0.5, 0.5, 0.5, 0.0]],  # row sum 1.5
        [[0.25] * 4, [0.25] * 4, [0.25] * 4, [1.25, -0.25, 0.0, 0.0]],  # negative
        [[0.25] * 4, [0.25] * 4, [0.25] * 4, [float("nan"), 0.0, 0.0, 1.0]],
        [[0.25] * 4, [0.25] * 4, [0.25] * 4, [0.0, 0.0, 0.0, 0.0]],  # empty row
        [[0.25] * 4, [0.25] * 4, [0.25] * 4, [0.25, 0.25, 0.25, "x"]],
        [[0.25] * 4, [0.25] * 4, [0.25] * 4, [0.25] * 3 + [True]],
        "not a matrix",
        [0.25] * 4,
    ],
)
def test_custom_transition_matrix_validated(matrix: object) -> None:
    with pytest.raises(AdherenceConfigError):
        AdherenceModel(params(), CFG, transition_matrix=matrix)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "initial",
    [
        (0.5, 0.5, 0.5, 0.0),
        (0.25, 0.25, 0.25),
        (0.25,) * 5,
        (-0.25, 0.5, 0.5, 0.25),
        (float("nan"), 0.0, 0.0, 1.0),
        "abcd",
    ],
)
def test_initial_distribution_validated(initial: object) -> None:
    with pytest.raises(AdherenceConfigError):
        AdherenceModel(params(), CFG, initial_distribution=initial)  # type: ignore[arg-type]


stochastic_rows = st.lists(
    st.integers(min_value=0, max_value=3), min_size=4, max_size=4
).filter(lambda weights: sum(weights) > 0)


@settings(max_examples=60, deadline=None, derandomize=True)
@given(
    st.lists(stochastic_rows, min_size=4, max_size=4),
    st.integers(min_value=0, max_value=10_000),
)
def test_simulated_sequence_only_visits_positive_probability_transitions(
    weights: list[list[int]], seed: int
) -> None:
    matrix = [[w / sum(row) for w in row] for row in weights]
    model = AdherenceModel(params(mean_delay_ms=HOUR), CFG, transition_matrix=matrix)
    schedule = Schedule(
        dose_ticks_ms=(8 * HOUR, 14 * HOUR, 20 * HOUR), measurement_ticks_ms=()
    )
    result = model.simulate(schedule, 7, adherence_stream(seed, 0))
    states = state_sequence(result)
    assert len(states) == 21
    assert model.initial_distribution[states[0]] > 0.0
    for previous, current in pairwise(states):
        assert matrix[previous][current] > 0.0


# ---------------------------------------------------------------------------
# 4 to 7. Events of one chain
# ---------------------------------------------------------------------------


def test_perfect_adherence_when_all_probabilities_zero() -> None:
    result = run(params(), n_days=3)
    assert set(state_sequence(result)) == {ON_TIME}
    assert len(state_sequence(result)) == 6
    dispenses = kinds(result.events, EventKind.DISPENSE)
    assert dispenses == [d * DAY + t for d in range(3) for t in (8 * HOUR, 20 * HOUR)]
    assert len(dispenses) == len(state_sequence(result))
    assert result.final_state is ON_TIME


def test_a_dose_time_that_is_not_on_any_grid_is_kept_to_the_millisecond() -> None:
    odd = 25_200_001  # FIXTURE-ONLY: 07:00:00.001, off every grid step
    schedule = Schedule(dose_ticks_ms=(odd,), measurement_ticks_ms=())
    result = run(params(), schedule=schedule, n_days=2)
    assert kinds(result.events, EventKind.DISPENSE) == [odd, DAY + odd]
    assert kinds(result.events, EventKind.INTAKE) == [odd + LAG, DAY + odd + LAG]


def test_omission_probability_one_yields_no_events() -> None:
    result = run(params(p_omission=1.0), n_days=4)
    assert result.events == ()
    assert set(state_sequence(result)) == {OMITTED}
    assert len(result.behaviour_log) == 8
    assert all(entry.dispense_times_ms == () for entry in result.behaviour_log)


def test_double_take_second_dispense_after_gap() -> None:
    schedule = Schedule(dose_ticks_ms=(8 * HOUR,), measurement_ticks_ms=())
    result = run(params(p_double_take=1.0), schedule=schedule)
    t = 8 * HOUR
    assert [(e.kind, e.t_device_ms) for e in result.events] == [
        (EventKind.DISPENSE, t),
        (EventKind.INTAKE, t + 5_000),
        (EventKind.DISPENSE, t + 120_000),
        (EventKind.INTAKE, t + 125_000),
    ]
    assert result.behaviour_log[0].dispense_times_ms == (t, t + 120_000)


def test_delayed_state_probability_one_delays_every_dose_within_its_slot() -> None:
    result = run(params(p_delay=1.0, mean_delay_ms=HOUR), n_days=200)
    log = result.behaviour_log
    assert set(state_sequence(result)) == {DELAYED}
    tick_of = {8 * HOUR: 12 * HOUR, 20 * HOUR: 4 * HOUR}  # slot lengths
    for entry in log:
        (when,) = entry.dispense_times_ms
        clock = entry.slot_tick_ms - entry.day_index * DAY
        assert entry.slot_tick_ms + 1 <= when <= entry.slot_tick_ms + tick_of[clock] - 1
    # a delayed dose is distinguishable from an on-time one: the delay is at least 1 ms
    assert min(e.dispense_times_ms[0] - e.slot_tick_ms for e in log) >= 1


def test_delay_is_bounded_by_the_next_tick_and_by_the_day_end() -> None:
    # A huge mean makes the truncation matter: delays reach the last part of every slot.
    result = run(params(p_delay=1.0, mean_delay_ms=10_000 * HOUR), n_days=300)
    first = [e for e in result.behaviour_log if e.slot_tick_ms % DAY == 8 * HOUR]
    last = [e for e in result.behaviour_log if e.slot_tick_ms % DAY == 20 * HOUR]
    for entry in first:
        assert entry.dispense_times_ms[0] <= entry.slot_tick_ms + 12 * HOUR - 1
    for entry in last:
        # the last slot of a day ends at the day end, not at the first tick of the next day
        day_end = (entry.day_index + 1) * DAY
        assert entry.dispense_times_ms[0] <= day_end - 1
    # the bound is approached (nearly uniform delays on [1, L - 1]), so the test has teeth
    assert max(e.dispense_times_ms[0] - e.slot_tick_ms for e in first) > 11 * HOUR
    assert max(e.dispense_times_ms[0] - e.slot_tick_ms for e in last) > 3 * HOUR


# ---------------------------------------------------------------------------
# 8. Delay law
# ---------------------------------------------------------------------------


def truncated_moments(mean: float, upper: float) -> tuple[float, float]:
    """Mean and sd of an exponential of mean ``mean`` truncated at ``upper`` (closed form)."""
    q = math.exp(-upper / mean)
    first = mean - upper * q / (1.0 - q)
    second = 2.0 * mean**2 - (upper**2 + 2.0 * mean * upper) * q / (1.0 - q)
    return first, math.sqrt(second - first**2)


def test_truncated_exponential_delay_mean() -> None:
    # mean 1 h truncated at 3 h: 1 - 3 exp(-3) / (1 - exp(-3)) = 0.842813 h
    analytic, sd = truncated_moments(1.0, 3.0)
    assert analytic == pytest.approx(0.842813, abs=1e-6)
    n = 50_000
    u = stream(0, 0, None, StreamPurpose.ADHERENCE).random(n)
    draws = [truncated_exponential(HOUR, 3 * HOUR, float(x)) / HOUR for x in u]
    assert abs(sum(draws) / n - analytic) < 4.0 * sd / math.sqrt(n)
    assert all(0.0 <= d <= 3.0 for d in draws)


def test_truncated_exponential_inverse_cdf_properties() -> None:
    mean, upper = float(HOUR), float(3 * HOUR)
    assert truncated_exponential(mean, upper, 0.0) == 0.0
    top = math.nextafter(1.0, 0.0)
    assert 0.0 <= truncated_exponential(mean, upper, top) <= upper
    grid = [truncated_exponential(mean, upper, k / 100) for k in range(100)]
    assert grid == sorted(grid)
    # CDF at the median of u: F(x) = (1 - exp(-x/mean)) / (1 - exp(-upper/mean))
    x = truncated_exponential(mean, upper, 0.5)
    cdf = (1.0 - math.exp(-x / mean)) / (1.0 - math.exp(-upper / mean))
    assert cdf == pytest.approx(0.5, abs=1e-12)
    with pytest.raises(AdherenceConfigError):
        truncated_exponential(mean, upper, 1.0)
    with pytest.raises(AdherenceConfigError):
        truncated_exponential(mean, upper, -0.1)
    with pytest.raises(AdherenceConfigError):
        truncated_exponential(0.0, upper, 0.5)
    with pytest.raises(AdherenceConfigError):
        truncated_exponential(mean, 0.0, 0.5)


def test_integer_delay_boundaries_and_mean() -> None:
    top = math.nextafter(1.0, 0.0)
    assert sample_delay_ms(HOUR, 2, 0.0) == 1
    assert sample_delay_ms(HOUR, 2, top) == 1  # slot of 2 ms: the only admissible delay
    assert sample_delay_ms(HOUR, 100, 0.0) == 1
    assert 1 <= sample_delay_ms(HOUR, 100, top) <= 99
    assert sample_delay_ms(10**12, 100, top) == 99  # truncation active: the maximum
    for bad in (1, 0, -5):
        with pytest.raises(AdherenceConfigError):
            sample_delay_ms(HOUR, bad, 0.5)
    with pytest.raises(AdherenceConfigError):
        sample_delay_ms(0, 100, 0.5)
    # mean of integer delays: truncated mean plus a discretisation shift in (0, 1] ms
    slot = 3 * HOUR + 1
    analytic, sd = truncated_moments(float(HOUR), float(slot - 1))
    n = 50_000
    u = stream(0, 0, None, StreamPurpose.ADHERENCE).random(n)
    delays = [sample_delay_ms(HOUR, slot, float(x)) for x in u]
    assert all(1 <= d <= slot - 1 for d in delays)
    assert abs(sum(delays) / n - analytic) < 4.0 * sd / math.sqrt(n) + 1.0


# ---------------------------------------------------------------------------
# 9 to 11. The chain itself
# ---------------------------------------------------------------------------


def test_empirical_state_frequencies_match_marginals() -> None:
    marginals = {ON_TIME: 0.6, DELAYED: 0.2, OMITTED: 0.1, DOUBLE_TAKE: 0.1}
    result = run(params(0.2, 0.1, 0.1), n_days=10_000, seed=0)
    states = state_sequence(result)
    assert len(states) == 20_000
    for state, p in marginals.items():
        freq = states.count(state) / len(states)
        assert abs(freq - p) < binomial_tolerance(p, len(states)), state.name


def test_memoryless_chain_has_the_marginals_as_every_transition_row() -> None:
    states = state_sequence(run(params(0.2, 0.1, 0.1), n_days=10_000, seed=1))
    marginals = [0.6, 0.2, 0.1, 0.1]
    for i in STATES:
        successors = [b for a, b in pairwise(states) if a is i]
        for j in STATES:
            freq = successors.count(j) / len(successors)
            assert abs(freq - marginals[j]) < binomial_tolerance(
                marginals[j], len(successors)
            )


def stationary(matrix: Sequence[Sequence[float]]) -> np.ndarray:
    p = np.asarray(matrix, dtype=float)
    a = np.vstack([p.T - np.eye(4), np.ones(4)])
    b = np.array([0.0, 0.0, 0.0, 0.0, 1.0])
    return np.linalg.lstsq(a, b, rcond=None)[0]


def test_custom_chain_transition_frequencies_match_the_matrix() -> None:
    pi = stationary(STICKY)
    assert np.allclose(
        pi @ np.asarray(STICKY), pi
    )  # the helper really solves pi P = pi
    result = run(
        params(mean_delay_ms=HOUR), matrix=STICKY, initial=tuple(pi), n_days=7_000
    )
    states = state_sequence(result)
    assert len(states) == 14_000
    for i in STATES:
        successors = [b for a, b in pairwise(states) if a is i]
        for j in STATES:
            p = STICKY[i][j]
            freq = successors.count(j) / len(successors)
            if p == 0.0:
                assert freq == 0.0  # a structural zero is never visited
            else:
                assert abs(freq - p) < binomial_tolerance(p, len(successors))


def test_custom_chain_run_lengths_are_geometric() -> None:
    pi = stationary(STICKY)
    result = run(
        params(mean_delay_ms=HOUR), matrix=STICKY, initial=tuple(pi), n_days=7_000
    )
    states = state_sequence(result)
    runs: list[tuple[AdherenceState, int]] = []
    for s in states:
        if runs and runs[-1][0] is s:
            runs[-1] = (s, runs[-1][1] + 1)
        else:
            runs.append((s, 1))
    runs.pop()  # the last run is cut by the horizon
    for i in STATES:
        lengths = [n for s, n in runs if s is i]
        stay = STICKY[i][i]
        mean = 1.0 / (1.0 - stay)
        sd = math.sqrt(stay) / (1.0 - stay)  # geometric on {1, 2, ...}
        observed = sum(lengths) / len(lengths)
        assert abs(observed - mean) < 4.0 * sd / math.sqrt(len(lengths)), i.name


def test_stationary_start_gives_the_stationary_law_at_every_slot() -> None:
    # 4000 independent chains (one stream per patient): the state at slot k is iid with law
    # pi P^k = pi when the first state is drawn from pi.
    pi = stationary(STICKY)
    schedule = Schedule(
        dose_ticks_ms=tuple(k * HOUR for k in range(1, 7)), measurement_ticks_ms=()
    )
    model = AdherenceModel(
        params(mean_delay_ms=HOUR),
        CFG,
        transition_matrix=STICKY,
        initial_distribution=tuple(pi),
    )
    n = 4_000
    sequences = [
        state_sequence(model.simulate(schedule, 1, adherence_stream(0, patient)))
        for patient in range(n)
    ]
    for slot in (0, 5):
        for j in STATES:
            freq = sum(1 for seq in sequences if seq[slot] is j) / n
            assert abs(freq - pi[j]) < binomial_tolerance(float(pi[j]), n), (slot, j)


def test_a_point_mass_initial_law_and_one_step_from_it() -> None:
    schedule = Schedule(dose_ticks_ms=(8 * HOUR, 20 * HOUR), measurement_ticks_ms=())
    delta = (0.0, 0.0, 1.0, 0.0)  # starts omitted
    model = AdherenceModel(
        params(mean_delay_ms=HOUR),
        CFG,
        transition_matrix=STICKY,
        initial_distribution=delta,
    )
    n = 6_000
    second = []
    for patient in range(n):
        seq = state_sequence(model.simulate(schedule, 1, adherence_stream(2, patient)))
        assert seq[0] is OMITTED
        second.append(seq[1])
    for j in STATES:
        p = STICKY[OMITTED][j]
        freq = second.count(j) / n
        assert abs(freq - p) < binomial_tolerance(p, n) if p else freq == 0.0


@pytest.mark.parametrize("absorbing", [OMITTED, DOUBLE_TAKE, ON_TIME])
def test_absorbing_row_is_markov(absorbing: AdherenceState) -> None:
    rows = [list(r) for r in ((0.5, 0.2, 0.2, 0.1),) * 4]
    rows[absorbing] = [1.0 if k == absorbing else 0.0 for k in range(4)]
    result = run(params(0.2, 0.1, 0.1), matrix=rows, n_days=100, seed=3)
    states = state_sequence(result)
    first = states.index(absorbing)
    assert first < len(states) - 1  # the absorbing state is reached with room to spare
    assert set(states[first:]) == {absorbing}


def test_absorbing_start_stays_forever() -> None:
    rows = [[0.0, 0.0, 1.0, 0.0]] * 4
    result = run(params(), matrix=rows, initial=(0.0, 0.0, 1.0, 0.0), n_days=50)
    assert set(state_sequence(result)) == {OMITTED}
    assert result.events == ()


def test_chain_state_carries_across_days() -> None:
    # a cycle ON_TIME -> DELAYED -> OMITTED -> DOUBLE_TAKE -> ON_TIME with probability 0.9; the
    # first state of a patient is ON_TIME (marginals of zero probabilities), so a chain that
    # restarted every midnight would begin each day with ON_TIME
    cycle = [
        [0.1, 0.9, 0.0, 0.0],
        [0.0, 0.1, 0.9, 0.0],
        [0.0, 0.0, 0.1, 0.9],
        [0.9, 0.0, 0.0, 0.1],
    ]
    p = params(mean_delay_ms=HOUR)
    model = AdherenceModel(p, CFG, transition_matrix=cycle)
    whole = model.simulate(TWO_DOSES, 7, adherence_stream(4, 0))

    rng = adherence_stream(4, 0)
    pieces: list[AdherenceResult] = []
    state: AdherenceState | None = None
    for day in range(7):
        piece = model.simulate(TWO_DOSES, 1, rng, start_day=day, state=state)
        state = piece.final_state
        pieces.append(piece)
    assert state_sequence(whole) == [
        s for piece in pieces for s in state_sequence(piece)
    ]
    merged = sorted((e for piece in pieces for e in piece.events), key=tie_key)
    assert list(whole.events) == merged
    assert list(whole.behaviour_log) == [
        x for piece in pieces for x in piece.behaviour_log
    ]
    assert whole.final_state is pieces[-1].final_state
    # the chain does not reset at midnight: restarting each day from the initial law differs
    rng = adherence_stream(4, 0)
    restarted = [
        s
        for day in range(7)
        for s in state_sequence(model.simulate(TWO_DOSES, 1, rng, start_day=day))
    ]
    assert restarted != state_sequence(whole)
    first_of_day = state_sequence(whole)[2::2]
    assert any(s is not ON_TIME for s in first_of_day)  # the carry shows at midnight
    assert set(restarted[0::2]) == {ON_TIME}


def test_one_run_of_many_days_equals_runs_of_one_and_of_several_days() -> None:
    p = params(0.2, 0.1, 0.1)
    model = AdherenceModel(p, CFG)
    whole = model.simulate(TWO_DOSES, 6, adherence_stream(5, 1))
    rng = adherence_stream(5, 1)
    first = model.simulate(TWO_DOSES, 2, rng)
    second = model.simulate(TWO_DOSES, 4, rng, start_day=2, state=first.final_state)
    assert state_sequence(whole) == state_sequence(first) + state_sequence(second)
    assert list(whole.events) == sorted([*first.events, *second.events], key=tie_key)


def test_the_generator_is_consumed_two_draws_per_slot_whatever_the_outcome() -> None:
    for p in (params(), params(p_omission=1.0), params(0.2, 0.1, 0.1), params(1.0)):
        rng = adherence_stream(6, 0)
        AdherenceModel(p, CFG).simulate(TWO_DOSES, 5, rng)
        reference = adherence_stream(6, 0)
        reference.random(2 * 10)
        assert rng.random() == reference.random()


# ---------------------------------------------------------------------------
# 12 to 14. DISPENSE is not INTAKE; ordering; the behaviour log
# ---------------------------------------------------------------------------


def test_dispense_and_intake_are_distinct_kinds() -> None:
    result = run(params(0.2, 0.1, 0.2), n_days=200, seed=7)
    dispenses = kinds(result.events, EventKind.DISPENSE)
    intakes = kinds(result.events, EventKind.INTAKE)
    assert dispenses and intakes
    assert {e.kind for e in result.events} == {EventKind.DISPENSE, EventKind.INTAKE}
    # each INTAKE follows its DISPENSE by the lag; the model has no dispensed-but-not-taken
    # case (declared simplification), so the counts are equal and the shifted times match
    assert len(dispenses) == len(intakes)
    assert sorted(t + LAG for t in dispenses) == sorted(intakes)
    n_double = sum(1 for e in result.behaviour_log if e.state is DOUBLE_TAKE)
    n_omitted = sum(1 for e in result.behaviour_log if e.state is OMITTED)
    assert n_double > 0 and n_omitted > 0
    assert len(dispenses) == len(result.behaviour_log) - n_omitted + n_double
    # no INTAKE exists without a DISPENSE: an omitted slot has neither
    for entry in result.behaviour_log:
        if entry.state is OMITTED:
            assert entry.dispense_times_ms == ()


def test_latent_events_sorted_and_times_equal() -> None:
    result = run(params(0.2, 0.1, 0.2), n_days=100, seed=8)
    times = [e.t_device_ms for e in result.events]
    assert times == sorted(times)
    for e in result.events:
        assert e.t_rx_ms == e.t_device_ms
        assert e.seq is None
        assert type(e.t_device_ms) is int and type(e.t_rx_ms) is int
        assert dict(e.payload) == {}
        expected = "dispenser" if e.kind is EventKind.DISPENSE else "patient"
        assert e.source == expected
    assert isinstance(result.events, tuple)


def test_equal_times_put_dispense_before_intake() -> None:
    # Zero intake lag: a DISPENSE and its INTAKE share a time; the DISPENSE comes first.
    zero_lag = AdherenceConfig(intake_lag_ms=0, double_take_gap_ms=GAP)
    result = run(params(), config=zero_lag, n_days=2)
    assert [(e.kind, e.t_device_ms) for e in result.events[:2]] == [
        (EventKind.DISPENSE, 8 * HOUR),
        (EventKind.INTAKE, 8 * HOUR),
    ]
    # An INTAKE of one slot can also meet the next slot's DISPENSE: slots of 3 ms, lag 1 ms,
    # gap 2 ms; the first slot is always DELAYED and the second ON_TIME.
    tight = Schedule(dose_ticks_ms=(1_000, 1_003), measurement_ticks_ms=())
    config = AdherenceConfig(intake_lag_ms=1, double_take_gap_ms=2)
    alternate = [[0.0, 1.0, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0]] + [
        [1.0, 0.0, 0.0, 0.0]
    ] * 2
    result = run(
        params(mean_delay_ms=1),
        schedule=tight,
        config=config,
        matrix=alternate,
        initial=(0.0, 1.0, 0.0, 0.0),
        n_days=60,
    )
    by_time: dict[int, list[EventKind]] = {}
    for e in result.events:
        by_time.setdefault(e.t_device_ms, []).append(e.kind)
    shared = [kinds_at for kinds_at in by_time.values() if len(kinds_at) > 1]
    assert shared, "the test needs at least one shared time to have teeth"
    for kinds_at in shared:
        assert kinds_at == [EventKind.DISPENSE, EventKind.INTAKE]
    order = [(e.t_device_ms, e.kind is EventKind.INTAKE) for e in result.events]
    assert order == sorted(order)


def test_behaviour_log_matches_events() -> None:
    result = run(params(0.2, 0.1, 0.2), n_days=50, seed=9)
    log = result.behaviour_log
    assert len(log) == 100  # one entry per slot
    for index, entry in enumerate(log):
        assert isinstance(entry, BehaviourEntry)
        assert entry.day_index == index // 2
        clock = (8 * HOUR, 20 * HOUR)[index % 2]
        assert entry.slot_tick_ms == entry.day_index * DAY + clock
        assert isinstance(entry.state, AdherenceState)
    flat = sorted(t for entry in log for t in entry.dispense_times_ms)
    assert flat == sorted(kinds(result.events, EventKind.DISPENSE))
    assert sum(flat) == sum(kinds(result.events, EventKind.DISPENSE))
    shapes = {
        ON_TIME: lambda e: e.dispense_times_ms == (e.slot_tick_ms,),
        DELAYED: lambda e: (
            len(e.dispense_times_ms) == 1 and e.dispense_times_ms[0] > e.slot_tick_ms
        ),
        OMITTED: lambda e: e.dispense_times_ms == (),
        DOUBLE_TAKE: lambda e: (
            e.dispense_times_ms == (e.slot_tick_ms, e.slot_tick_ms + GAP)
        ),
    }
    for entry in log:
        assert shapes[entry.state](entry), entry


def test_behaviour_entry_json_form() -> None:
    entry = BehaviourEntry(
        slot_tick_ms=DAY + 8 * HOUR,
        day_index=1,
        state=DOUBLE_TAKE,
        dispense_times_ms=(DAY + 8 * HOUR, DAY + 8 * HOUR + GAP),
    )
    assert entry.to_json() == {
        "slot_tick_ms": DAY + 8 * HOUR,
        "day_index": 1,
        "state": "DOUBLE_TAKE",
        "dispense_times_ms": [DAY + 8 * HOUR, DAY + 8 * HOUR + GAP],
    }


# ---------------------------------------------------------------------------
# 15. Streams
# ---------------------------------------------------------------------------


def test_adherence_stream_is_the_named_patient_stream() -> None:
    a = adherence_stream(3, 2).random(4).tolist()
    b = stream(3, 2, None, StreamPurpose.ADHERENCE).random(4).tolist()
    assert a == b
    assert adherence_stream(3, 3).random(4).tolist() != a
    assert adherence_stream(4, 2).random(4).tolist() != a


def test_adherence_stream_independent_of_other_streams() -> None:
    p = params(0.2, 0.1, 0.2)
    expected = run(p, n_days=30, seed=10, patient=4)
    # consume every other purpose of the same patient first, in a different order
    for purpose in (
        StreamPurpose.MEASUREMENT,
        StreamPurpose.INJECTION_C1,
        StreamPurpose.INJECTION_C2,
        StreamPurpose.INJECTION_C3,
        StreamPurpose.LATENT_AR,
        StreamPurpose.PATIENT,
    ):
        stream(10, 4, None, purpose).random(1_000)
        stream(10, 4, 3, purpose).random(10)
    again = run(p, n_days=30, seed=10, patient=4)
    assert again == expected
    assert run(p, n_days=30, seed=10, patient=5) != expected


def test_the_output_is_deterministic_for_a_fixed_seed() -> None:
    p = params(0.2, 0.1, 0.2)
    assert run(p, n_days=20, seed=11) == run(p, n_days=20, seed=11)
    assert run(p, n_days=20, seed=11) != run(p, n_days=20, seed=12)


# ---------------------------------------------------------------------------
# 16. Configuration of the double take
# ---------------------------------------------------------------------------


def test_double_take_gap_must_fit_between_slots() -> None:
    slot = (
        4 * HOUR
    )  # the slots of TWO_DOSES are 12 h and 4 h (to the day end): 4 h decides
    fits = AdherenceConfig(intake_lag_ms=LAG, double_take_gap_ms=slot - 1)
    result = run(params(p_double_take=1.0), config=fits)
    assert kinds(result.events, EventKind.DISPENSE) == [
        8 * HOUR,
        8 * HOUR + slot - 1,
        20 * HOUR,
        DAY - 1,
    ]  # the second dispense of a slot stays before the next tick and before the day end
    equal = AdherenceConfig(intake_lag_ms=LAG, double_take_gap_ms=slot)
    with pytest.raises(AdherenceConfigError, match="shorter"):
        run(params(p_double_take=1.0), config=equal)
    # also when the double take cannot happen: a gap that does not fit is a configuration error
    with pytest.raises(AdherenceConfigError, match="shorter"):
        run(params(), config=equal)


def test_the_shortest_slot_decides_including_the_last_slot_of_the_day() -> None:
    # ticks 08:00 and 23:00: the second slot ends at the day end and is 1 h long
    schedule = Schedule(dose_ticks_ms=(8 * HOUR, 23 * HOUR), measurement_ticks_ms=())
    run(
        params(),
        schedule=schedule,
        config=dataclasses.replace(CFG, double_take_gap_ms=HOUR - 1),
    )
    with pytest.raises(AdherenceConfigError):
        run(
            params(),
            schedule=schedule,
            config=dataclasses.replace(CFG, double_take_gap_ms=HOUR),
        )
    # a single dose: its slot is the whole rest of the day
    last = Schedule(dose_ticks_ms=(DAY - 1_000,), measurement_ticks_ms=())
    with pytest.raises(AdherenceConfigError):
        run(params(), schedule=last, config=CFG)
    ok = run(params(p_double_take=1.0), schedule=last, config=AdherenceConfig(0, 999))
    assert (
        max(kinds(ok.events, EventKind.DISPENSE)) == DAY - 1
    )  # last millisecond of the day


@pytest.mark.parametrize(
    ("lag", "gap"),
    [
        (-1, 10),
        (0, 0),
        (0, -1),
        (10, 10),
        (11, 10),
        (1.5, 10),
        (0, 10.0),
        (True, 10),
        (0, None),
    ],
)
def test_config_validation(lag: object, gap: object) -> None:
    with pytest.raises(AdherenceConfigError):
        AdherenceConfig(intake_lag_ms=lag, double_take_gap_ms=gap)  # type: ignore[arg-type]


def test_config_boundaries() -> None:
    AdherenceConfig(intake_lag_ms=0, double_take_gap_ms=1)
    AdherenceConfig(intake_lag_ms=np.int64(9), double_take_gap_ms=np.int64(10))


# ---------------------------------------------------------------------------
# Horizons, empty days, guards
# ---------------------------------------------------------------------------


def test_a_day_with_no_scheduled_dose_has_no_slot_and_no_event() -> None:
    empty = Schedule(dose_ticks_ms=(), measurement_ticks_ms=())
    result = run(params(0.2, 0.1, 0.1), schedule=empty, n_days=5)
    assert result.events == () and result.behaviour_log == ()
    assert result.final_state is None
    carried = run(params(0.2, 0.1, 0.1), schedule=empty, n_days=5, state=DELAYED)
    assert (
        carried.final_state is DELAYED
    )  # nothing happened: the state is carried through
    # the generator is not consumed when there is nothing to draw
    rng = adherence_stream(0, 0)
    AdherenceModel(params(0.2, 0.1, 0.1), CFG).simulate(empty, 3, rng)
    assert rng.random() == adherence_stream(0, 0).random()


def test_one_dose_per_day_and_two_doses_per_day() -> None:
    one = Schedule(dose_ticks_ms=(8 * HOUR,), measurement_ticks_ms=())
    assert len(run(params(), schedule=one, n_days=3).behaviour_log) == 3
    assert len(run(params(), n_days=3).behaviour_log) == 6
    result = run(params(), n_days=1)
    assert [e.kind for e in result.events] == [EventKind.DISPENSE, EventKind.INTAKE] * 2


def test_an_event_exactly_at_a_day_boundary_stays_on_the_continuing_axis() -> None:
    # A slot of 3 ms at the end of the day, lag 1 ms, gap 2 ms. A delayed dose of 2 ms is
    # dispensed at 23:59:59.999 and its intake falls exactly at 24:00 = step 0 of the next day;
    # the slot (and its behaviour entry) still belong to the dose's day.
    schedule = Schedule(dose_ticks_ms=(DAY - 3,), measurement_ticks_ms=())
    config = AdherenceConfig(intake_lag_ms=1, double_take_gap_ms=2)
    result = run(
        params(p_delay=1.0, mean_delay_ms=1),
        schedule=schedule,
        config=config,
        n_days=40,
    )
    boundary = [
        e
        for e in result.events
        if e.kind is EventKind.INTAKE and e.t_device_ms % DAY == 0
    ]
    assert boundary, "the test needs a delay of 2 ms to have teeth"
    assert len(boundary) < 40  # a delay of 1 ms ends before the boundary
    by_day = {entry.day_index: entry for entry in result.behaviour_log}
    for e in boundary:
        day = e.t_device_ms // DAY - 1
        assert by_day[day].dispense_times_ms == (e.t_device_ms - 1,)
        assert e in result.events
    for entry in result.behaviour_log:
        (when,) = entry.dispense_times_ms
        assert when // DAY == entry.day_index  # a dispense never leaves its own day
        assert entry.slot_tick_ms < when < (entry.day_index + 1) * DAY
    times = [e.t_device_ms for e in result.events]
    assert times == sorted(times)
    # an on-time intake cannot cross midnight: lag < gap < slot, so tick + lag < day end
    on_time = run(params(), schedule=schedule, config=config, n_days=3)
    assert kinds(on_time.events, EventKind.INTAKE) == [
        DAY - 2,
        2 * DAY - 2,
        3 * DAY - 2,
    ]
    # a dose exactly at 00:00 is allowed (tick 0)
    midnight = Schedule(dose_ticks_ms=(0,), measurement_ticks_ms=())
    assert kinds(
        run(params(), schedule=midnight, n_days=2).events, EventKind.DISPENSE
    ) == [0, DAY]


def test_a_one_millisecond_slot_cannot_hold_a_double_take_gap() -> None:
    # slot of 1 ms (a dose at 23:59:59.999): the gap must be >= 1 ms and < 1 ms: refused
    last = Schedule(dose_ticks_ms=(DAY - 1,), measurement_ticks_ms=())
    with pytest.raises(AdherenceConfigError, match="shorter"):
        run(params(), schedule=last, config=AdherenceConfig(0, 1))


def test_start_day_places_events_on_the_continuing_axis() -> None:
    result = run(params(), n_days=2, start_day=3)
    assert kinds(result.events, EventKind.DISPENSE)[0] == 3 * DAY + 8 * HOUR
    assert [x.day_index for x in result.behaviour_log] == [3, 3, 4, 4]


def test_a_time_axis_beyond_int64_is_refused() -> None:
    far = (2**63 - 1) // DAY
    with pytest.raises(AdherenceConfigError):
        run(params(), n_days=2, start_day=far)
    run(params(), n_days=1, start_day=far - 1)  # still inside the axis


def test_slot_guard_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(adherence_module, "MAX_SLOTS", 6)
    assert len(run(params(), n_days=3).behaviour_log) == 6  # exactly at the limit
    with pytest.raises(AdherenceConfigError, match="MAX_SLOTS"):
        run(params(), n_days=4)
    assert MAX_SLOTS >= 14  # a 200-patient, 7-day benchmark needs 14 slots per patient


@pytest.mark.parametrize("bad", [0, -1, 1.0, True, None, "1"])
def test_n_days_must_be_a_positive_integer(bad: object) -> None:
    with pytest.raises(AdherenceConfigError, match="n_days"):
        AdherenceModel(params(), CFG).simulate(TWO_DOSES, bad, adherence_stream(0, 0))  # type: ignore[arg-type]


def test_inputs_are_checked() -> None:
    model = AdherenceModel(params(), CFG)
    with pytest.raises(AdherenceConfigError, match="start_day"):
        model.simulate(TWO_DOSES, 1, adherence_stream(0, 0), start_day=-1)
    with pytest.raises(AdherenceConfigError, match="Generator"):
        model.simulate(TWO_DOSES, 1, 0)  # type: ignore[arg-type]
    with pytest.raises(AdherenceConfigError, match="Schedule"):
        model.simulate([8 * HOUR], 1, adherence_stream(0, 0))  # type: ignore[arg-type]
    with pytest.raises(AdherenceConfigError, match="state"):
        model.simulate(TWO_DOSES, 1, adherence_stream(0, 0), state=7)  # type: ignore[arg-type]
    assert (
        len(
            model.simulate(TWO_DOSES, np.int64(2), adherence_stream(0, 0)).behaviour_log
        )
        == 4
    )


def test_zero_probability_states_are_never_visited() -> None:
    result = run(params(0.3, 0.0, 0.0), n_days=5_000, seed=13)
    seen = set(state_sequence(result))
    assert seen == {ON_TIME, DELAYED}
    result = run(params(0.0, 0.0, 0.5), n_days=5_000, seed=13)
    assert set(state_sequence(result)) == {ON_TIME, DOUBLE_TAKE}


def test_probability_one_states_are_the_only_state_visited() -> None:
    for state, p in (
        (DELAYED, params(p_delay=1.0)),
        (OMITTED, params(p_omission=1.0)),
        (DOUBLE_TAKE, params(p_double_take=1.0)),
    ):
        assert set(state_sequence(run(p, n_days=500, seed=14))) == {state}


# ---------------------------------------------------------------------------
# Boundaries of the inverse-CDF draw (a generator that returns one constant)
# ---------------------------------------------------------------------------


class ConstantUniform(np.random.Generator):
    """A ``Generator`` whose ``random`` returns one fixed value (to hit the draw boundaries)."""

    def __init__(self, value: float) -> None:
        super().__init__(np.random.PCG64(0))
        self.value = value

    def random(self, size: Any = None, *args: Any, **kwargs: Any) -> Any:  # type: ignore[override]
        return np.full(size, self.value)


TOP = math.nextafter(1.0, 0.0)  # the largest value of Generator.random()


def first_state(
    row: Sequence[float], u: float, *, initial: bool = False
) -> AdherenceState:
    one_slot = Schedule(dose_ticks_ms=(8 * HOUR,), measurement_ticks_ms=())
    matrix = [row] * 4
    model = AdherenceModel(
        params(mean_delay_ms=HOUR),
        CFG,
        transition_matrix=matrix,
        initial_distribution=row if initial else (1.0, 0.0, 0.0, 0.0),
    )
    start = None if initial else ON_TIME
    result = model.simulate(one_slot, 1, ConstantUniform(u), state=start)
    return result.behaviour_log[0].state


@pytest.mark.parametrize("initial", [False, True])
def test_a_state_of_probability_zero_is_never_drawn_at_the_ends_of_u(
    initial: bool,
) -> None:
    for u in (0.0, 0.25, 0.5, 0.75, TOP):
        assert first_state((0.0, 0.0, 1.0, 0.0), u, initial=initial) is OMITTED
        assert first_state((1.0, 0.0, 0.0, 0.0), u, initial=initial) is ON_TIME
        assert first_state((0.0, 0.0, 0.0, 1.0), u, initial=initial) is DOUBLE_TAKE
        assert first_state((0.0, 1.0, 0.0, 0.0), u, initial=initial) is DELAYED
    row = (0.5, 0.0, 0.5, 0.0)  # structural zero in the middle
    assert first_state(row, 0.0, initial=initial) is ON_TIME
    assert first_state(row, math.nextafter(0.5, 0.0), initial=initial) is ON_TIME
    assert first_state(row, 0.5, initial=initial) is OMITTED  # u < 0.5 is strict
    assert first_state(row, TOP, initial=initial) is OMITTED


def test_a_row_that_sums_to_one_only_within_tolerance_never_falls_off_the_end() -> None:
    # sum is 1 - 1e-12: u above the last cumulative bound falls to the last state of
    # positive probability, not to a state of probability 0
    row = (0.5, 0.5 - 1e-12, 0.0, 0.0)
    assert first_state(row, TOP) is DELAYED
    assert first_state(row, 0.5) is DELAYED
    assert first_state(row, math.nextafter(0.5, 0.0)) is ON_TIME


def test_constant_uniform_hits_the_delay_ends_through_the_model() -> None:
    one_slot = Schedule(dose_ticks_ms=(8 * HOUR,), measurement_ticks_ms=())
    model = AdherenceModel(params(p_delay=1.0, mean_delay_ms=HOUR), CFG)
    low = model.simulate(one_slot, 1, ConstantUniform(0.0))
    assert low.behaviour_log[0].dispense_times_ms == (
        8 * HOUR + 1,
    )  # delay at its minimum
    high = model.simulate(one_slot, 1, ConstantUniform(TOP))
    (when,) = high.behaviour_log[0].dispense_times_ms
    assert when <= DAY - 1  # slot to the day end: 16 h, the delay stays inside it
    huge = AdherenceModel(params(p_delay=1.0, mean_delay_ms=10**12), CFG)
    top = huge.simulate(one_slot, 1, ConstantUniform(TOP))
    assert top.behaviour_log[0].dispense_times_ms == (DAY - 1,)  # delay at its maximum


# ---------------------------------------------------------------------------
# The events are valid latent trace data
# ---------------------------------------------------------------------------


def test_events_and_behaviour_log_round_trip_through_the_truth_file(
    tmp_path: Path,
) -> None:
    result = run(params(0.2, 0.1, 0.2), n_days=1, seed=15)
    latent = LatentDay("p0000", 0, 15, (), result.events)
    log = [entry.to_json() for entry in result.behaviour_log]
    write_truth(tmp_path, latent, (), behaviour_log=log)
    record = read_truth(tmp_path, "p0000", 0)
    assert tuple(record.latent.events) == result.events
    assert record.behaviour_log == log


# ---------------------------------------------------------------------------
# From a prior file (fixture-only values)
# ---------------------------------------------------------------------------


def test_parameters_from_a_fixture_prior_source(tmp_path: Path) -> None:
    prior = LiteraturePriorSource(make_fixture_prior(tmp_path), allow_fixture_only=True)
    p = prior.adherence()
    model = AdherenceModel(p, CFG)
    assert model.transition_matrix[0] == pytest.approx(
        [1.0 - 0.25 - 0.125 - 0.0625, 0.25, 0.125, 0.0625]
    )
    result = model.simulate(TWO_DOSES, 3, adherence_stream(0, 0))
    assert len(result.behaviour_log) == 6


# ---------------------------------------------------------------------------
# 17 and 18. Schedule derivation and consistency
# ---------------------------------------------------------------------------

HOLD, D1, D2, SW = (
    HOUR,
    HOUR,
    3 * HOUR,
    30 * MIN,
)  # FIXTURE-ONLY: the F0 shape of the windows


def clock(h: int, m: int = 0, s: int = 0) -> int:
    return h * HOUR + m * MIN + s * SEC


def test_schedule_derivation_hand_case() -> None:
    schedule = derive_schedule((clock(8), clock(20)), 5, HOLD, D1, D2, SW)
    assert schedule.dose_ticks_ms == (clock(8), clock(20))
    assert schedule.measurement_ticks_ms == (
        clock(7, 15),
        clock(9, 45),
        clock(14, 30),
        clock(19, 15),
        clock(21, 45),
    )
    # the building blocks of the rule
    assert clock(8) - clock(7, 15) == 45 * MIN  # midpoint of [a - 1 h, a - 30 min)
    assert (
        clock(9, 45) - clock(8) == 105 * MIN
    )  # midpoint of [a + 1 h, a + 3 h - 30 min]
    assert isinstance(schedule, Schedule)
    assert dataclasses.is_dataclass(schedule)
    with pytest.raises(dataclasses.FrozenInstanceError):
        schedule.dose_ticks_ms = ()  # type: ignore[misc]


def test_derivation_with_only_the_required_ticks_and_with_more_extras() -> None:
    four = derive_schedule((clock(8), clock(20)), 4, HOLD, D1, D2, SW)
    assert four.measurement_ticks_ms == (
        clock(7, 15),
        clock(9, 45),
        clock(19, 15),
        clock(21, 45),
    )
    six = derive_schedule((clock(8), clock(20)), 6, HOLD, D1, D2, SW)
    # gaps after five ticks: 2.5 h, 4.75 h, 4.75 h, 2.5 h; the earliest of the tie is split
    assert six.measurement_ticks_ms == (
        clock(7, 15),
        clock(9, 45),
        clock(12, 7, 30),
        clock(14, 30),
        clock(19, 15),
        clock(21, 45),
    )
    zero = derive_schedule((), 0, HOLD, D1, D2, SW)
    assert zero.dose_ticks_ms == () and zero.measurement_ticks_ms == ()


def test_derivation_rounds_an_odd_midpoint_down_inside_the_window() -> None:
    a, hold, sw = (
        clock(8),
        3_000_001,
        1_000_000,
    )  # window [a - 3 000 001, a - 1 000 000)
    schedule = derive_schedule((a,), 2, hold, D1, D2, sw)
    assert schedule.measurement_ticks_ms[0] == a - 2_000_001  # floor of a - 2 000 000.5
    assert a - hold <= schedule.measurement_ticks_ms[0] < a - sw
    # the closed post window [a + D1, a + D2 - sw] with an odd sum rounds down too
    post = schedule.measurement_ticks_ms[1]
    assert a + D1 <= post <= a + D2 - sw


@pytest.mark.parametrize(
    ("doses", "n", "match"),
    [
        ((clock(8), clock(20)), 3, "TOO_FEW"),  # each dose needs a pre and a post tick
        ((), 1, "NO_ANCHOR"),  # extra ticks need ticks to sit between
        ((clock(0, 30),), 2, "OUTSIDE_DAY"),  # the pre-dose window leaves the day
        ((clock(23, 30),), 2, "OUTSIDE_DAY"),  # the post-dose window leaves the day
        (
            (clock(8), clock(10, 30)),
            4,
            "COINCID",
        ),  # pre tick of dose 2 = post tick of dose 1
    ],
)
def test_derivation_refuses_what_it_cannot_realise(
    doses: tuple[int, ...], n: int, match: str
) -> None:
    with pytest.raises(ScheduleInfeasibleError, match=match) as info:
        derive_schedule(doses, n, HOLD, D1, D2, SW)
    assert info.value.problems


def test_derivation_needs_room_between_ticks_for_an_extra() -> None:
    # hold 2 ms, delta1 = delta2 = 0, sched_window 0: the pre tick is a - 1 and the post tick is a,
    # one millisecond apart, so no integer time lies strictly between them
    ticks = derive_schedule((clock(8),), 2, 2, 0, 0, 0).measurement_ticks_ms
    assert ticks == (clock(8) - 1, clock(8))
    with pytest.raises(ScheduleInfeasibleError, match="NO_ROOM"):
        derive_schedule((clock(8),), 3, 2, 0, 0, 0)


@pytest.mark.parametrize(
    "bad",
    [
        {"dose_times_ms": (clock(9), clock(8))},
        {"dose_times_ms": (clock(8), clock(8))},
        {"dose_times_ms": (-1,)},
        {"dose_times_ms": (DAY,)},
        {"dose_times_ms": (1.5,)},
        {"dose_times_ms": (True,)},
        {"n_measurements": -1},
        {"n_measurements": 2.0},
        {"hold_lookback_ms": -1},
        {"delta1_ms": -1},
        {"delta2_ms": D1 - 1},
        {"sched_window_ms": -1},
        {"sched_window_ms": None},
    ],
)
def test_derivation_validates_its_arguments(bad: dict[str, Any]) -> None:
    arguments: dict[str, Any] = {
        "dose_times_ms": (clock(8),),
        "n_measurements": 2,
        "hold_lookback_ms": HOLD,
        "delta1_ms": D1,
        "delta2_ms": D2,
        "sched_window_ms": SW,
        **bad,
    }
    with pytest.raises(ScheduleError):
        derive_schedule(**arguments)


def test_schedule_validation() -> None:
    Schedule(dose_ticks_ms=(0, DAY - 1), measurement_ticks_ms=(0, DAY - 1))
    for doses, meas in (
        ((5, 5), ()),
        ((6, 5), ()),
        ((), (7, 7)),
        ((), (DAY,)),
        ((DAY,), ()),
        ((-1,), ()),
        ((1.0,), ()),  # type: ignore[arg-type]
        ((), (True,)),
    ):
        with pytest.raises(ScheduleError):
            Schedule(dose_ticks_ms=doses, measurement_ticks_ms=meas)
    assert TWO_DOSES.slot_lengths_ms() == (12 * HOUR, 4 * HOUR)
    one = Schedule(dose_ticks_ms=(clock(7),), measurement_ticks_ms=())
    assert one.slot_lengths_ms() == (DAY - clock(7),)
    assert Schedule(dose_ticks_ms=(), measurement_ticks_ms=()).slot_lengths_ms() == ()
    assert Schedule(
        dose_ticks_ms=(0, 1), measurement_ticks_ms=()
    ).slot_lengths_ms() == (
        1,
        DAY - 1,
    )


def test_schedule_consistency_flags_infeasible_window() -> None:
    schedule = derive_schedule((clock(8), clock(20)), 5, HOLD, D1, D2, SW)
    assert check_schedule_consistency(schedule, HOLD, D1, D2, SW) == ()
    # with sched_window equal to hold_lookback no pre-dose tick can leave slack
    with pytest.raises(ScheduleInfeasibleError) as info:
        derive_schedule((clock(8), clock(20)), 5, HOLD, D1, D2, HOLD)
    derived = info.value.problems
    assert [p.check for p in derived] == ["SLACK_HOLD", "SLACK_HOLD"]
    assert [p.dose_tick_ms for p in derived] == [clock(8), clock(20)]
    assert "08:00:00.000" in str(info.value) and "20:00:00.000" in str(info.value)
    # the same problem is returned for a hand-written schedule (ticks of the hand case)
    found = check_schedule_consistency(schedule, HOLD, D1, D2, HOLD)
    assert [(p.check, p.dose_tick_ms) for p in found] == [
        ("SLACK_HOLD", clock(8)),
        ("SLACK_HOLD", clock(20)),
    ]
    assert all(isinstance(p, ScheduleProblem) and p.message for p in found)


def test_derivation_names_a_post_dose_window_that_cannot_hold_the_slack() -> None:
    with pytest.raises(ScheduleInfeasibleError) as info:
        derive_schedule((clock(8),), 2, HOLD, D1, D1 + SW - 1, SW)
    assert [p.check for p in info.value.problems] == ["SLACK_RESP"]
    # the boundary: a window of exactly sched_window holds one tick
    schedule = derive_schedule((clock(8),), 2, HOLD, D1, D1 + SW, SW)
    assert schedule.measurement_ticks_ms[1] == clock(8) + D1  # [a + D1, a + D1]
    assert check_schedule_consistency(schedule, HOLD, D1, D1 + SW, SW) == ()
    # and for the pre-dose window: hold = sched + 1 ms leaves one admissible tick
    schedule = derive_schedule((clock(8),), 2, SW + 1, D1, D2, SW)
    assert schedule.measurement_ticks_ms[0] == clock(8) - SW - 1
    assert check_schedule_consistency(schedule, SW + 1, D1, D2, SW) == ()


def make_plan(dose: int, ticks: tuple[int, ...]) -> Schedule:
    return Schedule(dose_ticks_ms=(dose,), measurement_ticks_ms=ticks)


def checks(plan: Schedule, sw: int = SW) -> list[str]:
    return [p.check for p in check_schedule_consistency(plan, HOLD, D1, D2, sw)]


def test_consistency_boundaries_of_the_hold_window() -> None:
    a = clock(8)
    post = a + 2 * HOUR  # a good post-dose tick, so only HOLD is under test
    assert (
        checks(make_plan(a, (a - HOLD, post))) == []
    )  # first instant of [a - hold, a)
    assert checks(make_plan(a, (a - SW - 1, post))) == []  # last tick with slack
    assert checks(make_plan(a, (a - SW, post))) == [
        "SLACK_HOLD"
    ]  # t + sched == a: no slack
    assert checks(make_plan(a, (a - 1, post))) == ["SLACK_HOLD"]
    assert checks(make_plan(a, (a, post))) == ["F2_HOLD"]  # the window is half open
    assert checks(make_plan(a, (a - HOLD - 1, post))) == ["F2_HOLD"]
    assert checks(make_plan(a, (post,))) == ["F2_HOLD"]
    assert checks(make_plan(a, ())) == ["F2_HOLD", "F3_RESP"]
    # one tick with slack is enough even if another does not leave it
    assert checks(make_plan(a, (a - HOLD, a - 1, post))) == []


def test_consistency_boundaries_of_the_response_window() -> None:
    a = clock(8)
    pre = a - HOLD
    assert checks(make_plan(a, (pre, a + D1))) == []  # first instant of the window
    assert checks(make_plan(a, (pre, a + D2 - SW))) == []  # last tick with slack
    assert checks(make_plan(a, (pre, a + D2 - SW + 1))) == ["SLACK_RESP"]
    assert checks(make_plan(a, (pre, a + D2))) == ["SLACK_RESP"]  # inside, but no slack
    assert checks(make_plan(a, (pre, a + D2 + 1))) == ["F3_RESP"]
    assert checks(make_plan(a, (pre, a + D1 - 1))) == ["F3_RESP"]
    # a zero sched_window needs no slack: the closed end is admissible
    assert checks(make_plan(a, (pre, a + D2)), sw=0) == []


def test_consistency_reports_every_dose_in_dose_order() -> None:
    schedule = Schedule(
        dose_ticks_ms=(clock(8), clock(20)), measurement_ticks_ms=(clock(21, 45),)
    )
    problems = check_schedule_consistency(schedule, HOLD, D1, D2, SW)
    assert [(p.check, p.dose_tick_ms) for p in problems] == [
        ("F2_HOLD", clock(8)),
        ("F3_RESP", clock(8)),
        ("F2_HOLD", clock(20)),
    ]
    assert all("08:00" in p.message or "20:00" in p.message for p in problems)


@settings(max_examples=80, deadline=None, derandomize=True)
@given(
    st.lists(
        st.integers(min_value=0, max_value=23 * 60), min_size=0, max_size=3, unique=True
    ),
    st.integers(min_value=0, max_value=4),
    st.integers(min_value=1, max_value=180),
    st.integers(min_value=0, max_value=180),
    st.integers(min_value=0, max_value=240),
    st.integers(min_value=0, max_value=90),
)
def test_a_derived_schedule_passes_its_own_consistency_check(
    dose_minutes: list[int], extra: int, hold_m: int, d1_m: int, width_m: int, sw_m: int
) -> None:
    doses = tuple(sorted(m * MIN for m in dose_minutes))
    hold, d1, d2, sw = hold_m * MIN, d1_m * MIN, (d1_m + width_m) * MIN, sw_m * MIN
    n = 2 * len(doses) + extra
    try:
        schedule = derive_schedule(doses, n, hold, d1, d2, sw)
    except ScheduleInfeasibleError as error:
        assert error.problems
        return
    assert len(schedule.measurement_ticks_ms) == n
    assert list(schedule.measurement_ticks_ms) == sorted(
        set(schedule.measurement_ticks_ms)
    )
    assert all(0 <= t < DAY for t in schedule.measurement_ticks_ms)
    assert check_schedule_consistency(schedule, hold, d1, d2, sw) == ()


# ---------------------------------------------------------------------------
# Config files
# ---------------------------------------------------------------------------

LAG_ROW, GAP_ROW = "intake_lag_ms", "double_take_gap_ms"
DOSES_ROW, N_MEAS_ROW = "dose_times_clock_ms", "n_measurements_per_day"
FIXTURE_NOTE = "FIXTURE-ONLY arithmetic of the test, not a source"


def rows_of(path: Path) -> dict[str, Any]:
    return {r.parameter: r for r in load_design_file(path).rows}


def edited_copy(
    source: Path, tmp_path: Path, updates: dict[str, dict[str, Any]]
) -> Path:
    document = yaml.safe_load(source.read_text(encoding="utf-8"))
    for row in document["parameters"]:
        row.update(updates.get(row["parameter"], {}))
    path = tmp_path / source.name
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def unfilled(**keep: Any) -> dict[str, Any]:
    return {
        "value": None,
        "dist": None,
        "status": "awaiting_human_value",
        "rationale": None,
        "verified_by": None,
        **keep,
    }


def filled(value: Any) -> dict[str, Any]:
    return {
        "value": value,
        "status": "filled",
        "source_ref": FIXTURE_NOTE,
        "rationale": "FIXTURE-ONLY: exercises the filled state of the row",
        "verified_by": None,
    }


def test_design_rows_have_provenance() -> None:
    """Invariants of the committed files that hold whether or not a human has filled them."""
    design = rows_of(DESIGN_FILE)
    plans = rows_of(CARE_PLAN_FILE)
    expected = {
        LAG_ROW: (design, "ms", "WS04-T05"),
        GAP_ROW: (design, "ms", "WS04-T05"),
        DOSES_ROW: (plans, "ms", "WS04-T05"),
        N_MEAS_ROW: (plans, "1", "WS04-T05"),
    }
    for name, (rows, unit, task) in expected.items():
        row = rows[name]
        assert row.unit == unit and row.consumer_task == task
        assert row.source_type in SOURCE_TYPES and row.source_type != "fixture_only"
        assert row.source_ref and row.source_ref.strip(), name
        if row.filled:
            assert row.rationale and row.rationale.strip(), name
        else:
            assert row.value is None
    # the note of the gap row records the only qualitative constraint (analisi 4.5 rows 6, 7)
    note = " ".join(design[GAP_ROW].note.split()).lower()
    assert "4.5" in note and "bounce" in note and "sub-second" in note
    # nothing a clinician has to confirm is hidden in a generator module: the table lists it
    table = TABLE.read_text(encoding="utf-8")
    for name in expected:
        assert f"| {name} |" in table


def test_adherence_config_unfilled_state_on_a_copy(tmp_path: Path) -> None:
    path = edited_copy(
        DESIGN_FILE, tmp_path, {LAG_ROW: unfilled(), GAP_ROW: unfilled()}
    )
    with pytest.raises(UnfilledParameterError, match="intake_lag_ms"):
        load_adherence_config(path)
    with pytest.raises(UnfilledParameterError, match="double_take_gap_ms"):
        load_adherence_config(path)
    only_lag = edited_copy(
        DESIGN_FILE, tmp_path, {LAG_ROW: filled(LAG), GAP_ROW: unfilled()}
    )
    with pytest.raises(UnfilledParameterError, match="double_take_gap_ms") as info:
        load_adherence_config(only_lag)
    assert "intake_lag_ms" not in str(info.value)


def test_adherence_config_filled_state_on_a_copy(tmp_path: Path) -> None:
    path = edited_copy(
        DESIGN_FILE, tmp_path, {LAG_ROW: filled(LAG), GAP_ROW: filled(GAP)}
    )
    config = load_adherence_config(path)
    assert config == CFG
    assert isinstance(config.intake_lag_ms, int)
    # a filled value that is not an integer, or breaks the constraints, is refused
    bad = edited_copy(
        DESIGN_FILE, tmp_path, {LAG_ROW: filled(1.5), GAP_ROW: filled(GAP)}
    )
    with pytest.raises(AdherenceConfigError, match="intake_lag_ms"):
        load_adherence_config(bad)
    bad = edited_copy(
        DESIGN_FILE, tmp_path, {LAG_ROW: filled(GAP), GAP_ROW: filled(GAP)}
    )
    with pytest.raises(AdherenceConfigError, match="shorter"):
        load_adherence_config(bad)


def test_adherence_config_needs_its_rows(tmp_path: Path) -> None:
    document = yaml.safe_load(DESIGN_FILE.read_text(encoding="utf-8"))
    document["parameters"] = [
        r for r in document["parameters"] if r["parameter"] != GAP_ROW
    ]
    path = tmp_path / "generator_design.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    with pytest.raises(PriorConfigError, match="double_take_gap_ms"):
        load_adherence_config(path)
    with pytest.raises(PriorConfigError):
        load_adherence_config(tmp_path / "missing.yaml")


def test_load_schedule_filled_state_on_a_copy(tmp_path: Path) -> None:
    path = edited_copy(
        CARE_PLAN_FILE,
        tmp_path,
        {DOSES_ROW: filled([clock(8), clock(20)]), N_MEAS_ROW: filled(5)},
    )
    loaded = load_schedule(
        path, hold_lookback_ms=HOLD, delta1_ms=D1, delta2_ms=D2, sched_window_ms=SW
    )
    assert loaded == derive_schedule((clock(8), clock(20)), 5, HOLD, D1, D2, SW)
    assert check_schedule_consistency(loaded, HOLD, D1, D2, SW) == ()
    # windows that cannot hold the plan are reported with the dose, not hidden
    with pytest.raises(ScheduleInfeasibleError, match="08:00:00.000"):
        load_schedule(
            path,
            hold_lookback_ms=HOLD,
            delta1_ms=D1,
            delta2_ms=D2,
            sched_window_ms=HOLD,
        )


def test_load_schedule_unfilled_state_and_bad_values_on_copies(tmp_path: Path) -> None:
    windows = {
        "hold_lookback_ms": HOLD,
        "delta1_ms": D1,
        "delta2_ms": D2,
        "sched_window_ms": SW,
    }
    path = edited_copy(
        CARE_PLAN_FILE, tmp_path, {DOSES_ROW: unfilled(), N_MEAS_ROW: unfilled()}
    )
    with pytest.raises(UnfilledParameterError, match="dose_times_clock_ms"):
        load_schedule(path, **windows)
    for doses, n in (
        ("08:00", 5),  # not numbers
        (clock(8), 5),  # a scalar, not a list
        ([clock(8), 1.5], 5),
        ([clock(8)], 2.5),
        ([clock(20), clock(8)], 4),  # not increasing
    ):
        bad = edited_copy(
            CARE_PLAN_FILE, tmp_path, {DOSES_ROW: filled(doses), N_MEAS_ROW: filled(n)}
        )
        with pytest.raises((ScheduleError, PriorConfigError)):
            load_schedule(bad, **windows)


def test_committed_care_plan_rows_load_in_the_design_loader() -> None:
    plans = rows_of(CARE_PLAN_FILE)
    assert set(plans) >= {DOSES_ROW, N_MEAS_ROW}
    if plans[DOSES_ROW].filled:
        value = plans[DOSES_ROW].value
        assert isinstance(value, list) and all(isinstance(v, int) for v in value)
        assert value == sorted(set(value)) and all(0 <= v < DAY for v in value)
    if plans[N_MEAS_ROW].filled:
        assert isinstance(plans[N_MEAS_ROW].value, int) and plans[N_MEAS_ROW].value >= 0


# ---------------------------------------------------------------------------
# Hygiene of the new modules
# ---------------------------------------------------------------------------


def _imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.add(node.module or "")
    return found


def test_schedule_module_never_imports_the_registry_or_monitor() -> None:
    names = _imports(Path(schedule_module.__file__))
    assert not any(n.startswith(("ralmon.spec", "ralmon.monitor")) for n in names)
    names = _imports(Path(adherence_module.__file__))
    assert not any(n.startswith(("ralmon.spec", "ralmon.monitor")) for n in names)


def test_names_outside_the_contract_are_not_exported_from_the_package_root() -> None:
    import ralmon.benchmark as root

    for name in ("AdherenceModel", "Schedule", "derive_schedule", "AdherenceState"):
        assert name not in root.__all__
        assert not hasattr(root, name)


def test_the_time_axis_constant_is_the_day() -> None:
    assert T_DAY_MS == DAY


# ---------------------------------------------------------------------------
# Fix round 1 (review): defined errors for numbers that overflow a float
# ---------------------------------------------------------------------------

TOO_BIG: list[Any] = [
    10**400,
    -(10**400),
    2**1024,
    Fraction(10**400),
]  # float() overflows
NOT_FINITE: list[Any] = [float("inf"), float("-inf"), float("nan")]


def ident(value: object) -> str:
    return f"{type(value).__name__}-{str(value)[:12]}"


@pytest.mark.parametrize("bad", TOO_BIG + NOT_FINITE, ids=ident)
def test_probabilities_that_overflow_or_are_not_finite_name_their_field(
    bad: Any,
) -> None:
    for position, name in enumerate(("p_delay", "p_omission", "p_double_take")):
        values: list[Any] = [0.1, 0.1, 0.1]
        values[position] = bad
        with pytest.raises(AdherenceConfigError, match=name):
            AdherenceModel(AdherenceParams(*values, HOUR), CFG)


@pytest.mark.parametrize("bad", TOO_BIG + NOT_FINITE, ids=ident)
def test_matrix_and_initial_law_entries_that_overflow_name_their_field(
    bad: Any,
) -> None:
    for row in range(4):
        matrix = [list(r) for r in STICKY]
        matrix[row][0] = bad
        with pytest.raises(AdherenceConfigError, match=f"transition_matrix row {row}"):
            AdherenceModel(params(0.2, 0.1, 0.1), CFG, transition_matrix=matrix)
    with pytest.raises(AdherenceConfigError, match="initial_distribution"):
        AdherenceModel(
            params(0.2, 0.1, 0.1), CFG, initial_distribution=[bad, 0.0, 0.0, 1.0]
        )


@pytest.mark.parametrize("bad", [10**400, 2**1024, 2**1024 - 1, 10**309], ids=ident)
def test_a_mean_delay_that_is_not_a_float_is_refused_by_name(bad: int) -> None:
    with pytest.raises(AdherenceConfigError, match="mean_delay_ms"):
        AdherenceModel(AdherenceParams(0.0, 0.0, 0.0, bad), CFG)
    with pytest.raises(AdherenceConfigError, match="mean_delay_ms"):
        AdherenceModel(AdherenceParams(0.1, 0.0, 0.0, bad), CFG)


@pytest.mark.parametrize("bad", TOO_BIG + NOT_FINITE, ids=ident)
def test_delay_law_arguments_that_overflow_name_their_argument(bad: Any) -> None:
    mean, upper, u = float(HOUR), float(3 * HOUR), 0.5
    with pytest.raises(AdherenceConfigError, match="mean"):
        truncated_exponential(bad, upper, u)
    with pytest.raises(AdherenceConfigError, match="upper"):
        truncated_exponential(mean, bad, u)
    with pytest.raises(AdherenceConfigError, match="u"):
        truncated_exponential(mean, upper, bad)
    if isinstance(bad, int):  # the integer entry point
        with pytest.raises(AdherenceConfigError, match="mean_delay_ms"):
            sample_delay_ms(bad, HOUR, 0.5)
        with pytest.raises(AdherenceConfigError, match="slot_length_ms"):
            sample_delay_ms(HOUR, bad, 0.5)
    with pytest.raises(AdherenceConfigError, match="u"):
        sample_delay_ms(HOUR, HOUR, bad)


@pytest.mark.parametrize("bad", [10**400, 2**1024], ids=ident)
def test_the_largest_integers_a_float_cannot_hold_are_refused_by_the_delay_law(
    bad: int,
) -> None:
    for slot in (bad, bad + 1, 2**1024 - 1):
        with pytest.raises(AdherenceConfigError, match="slot_length_ms"):
            sample_delay_ms(1, slot, TOP)
    with pytest.raises(AdherenceConfigError, match="mean_delay_ms"):
        sample_delay_ms(2**1024 - 1, 2, 0.5)


@pytest.mark.parametrize(
    ("mean", "upper", "u"),
    [
        (1e308, 1e308, 0.5),
        (1.7e308, 1.79e308, TOP),
        (5e-324, 1e308, 0.5),
        (1e-308, 1e-308, TOP),
        (1e308, 5e-324, 0.5),
        (5e-324, 5e-324, TOP),
        (1e-320, 1e308, TOP),
        (1e308, 1e308, 0.0),
    ],
)
def test_extreme_finite_floats_give_a_defined_result_in_range(
    mean: float, upper: float, u: float
) -> None:
    x = truncated_exponential(mean, upper, u)
    assert math.isfinite(x)
    assert 0.0 <= x <= upper


@pytest.mark.parametrize(
    ("mean", "slot"),
    [(10**300, 10**300), (1, 10**300), (10**308, 10**308), (1, 2**1023), (2**1023, 2)],
)
def test_huge_representable_integers_give_a_delay_inside_the_slot(
    mean: int, slot: int
) -> None:
    for u in (0.0, 0.5, TOP):
        assert 1 <= sample_delay_ms(mean, slot, u) <= slot - 1


@pytest.mark.parametrize("big", [10**400, 2**1024], ids=ident)
def test_huge_integer_arguments_of_the_simulation_are_defined_errors(big: int) -> None:
    model = AdherenceModel(params(0.2, 0.1, 0.1), CFG)
    for kwargs in ({"n_days": big}, {"n_days": 1, "start_day": big}):
        with pytest.raises(AdherenceConfigError):
            model.simulate(
                TWO_DOSES, kwargs.pop("n_days"), adherence_stream(0, 0), **kwargs
            )
    empty = Schedule(dose_ticks_ms=(), measurement_ticks_ms=())
    with pytest.raises(AdherenceConfigError, match="int64"):
        model.simulate(
            empty, big, adherence_stream(0, 0)
        )  # no slot: axis still checked
    for lag, gap in ((big, big + 1), (1, big), (big, big + 1)):
        huge = AdherenceModel(
            params(0.2, 0.1, 0.1),
            AdherenceConfig(intake_lag_ms=lag, double_take_gap_ms=gap),
        )
        with pytest.raises(AdherenceConfigError):
            huge.simulate(TWO_DOSES, 1, adherence_stream(0, 0))
    for bad in (-big, -1):
        with pytest.raises(AdherenceConfigError):
            AdherenceConfig(intake_lag_ms=bad, double_take_gap_ms=5)
        with pytest.raises(AdherenceConfigError):
            AdherenceConfig(intake_lag_ms=0, double_take_gap_ms=bad)


@pytest.mark.parametrize(
    "bad", [None, 0.5, "params", object(), (0.1, 0.1, 0.1, HOUR)], ids=ident
)
def test_a_model_without_adherence_params_is_a_defined_error(bad: object) -> None:
    with pytest.raises(AdherenceConfigError, match="params"):
        AdherenceModel(bad, CFG)  # type: ignore[arg-type]


@pytest.mark.parametrize("big", [10**400, -(10**400), 2**1024], ids=ident)
def test_schedule_arguments_that_overflow_give_a_schedule_error(big: int) -> None:
    base: dict[str, Any] = {
        "dose_times_ms": (clock(8),),
        "n_measurements": 2,
        "hold_lookback_ms": HOLD,
        "delta1_ms": D1,
        "delta2_ms": D2,
        "sched_window_ms": SW,
    }
    for name in base:
        arguments = {**base, name: (big,) if name == "dose_times_ms" else big}
        with pytest.raises(ScheduleError):
            derive_schedule(**arguments)
    windows = ("hold_lookback_ms", "delta1_ms", "delta2_ms", "sched_window_ms")
    schedule = derive_schedule((clock(8),), 2, HOLD, D1, D2, SW)
    for name in windows:
        arguments = {k: base[k] for k in windows} | {name: big}
        try:
            check_schedule_consistency(schedule, **arguments)
        except ScheduleError:
            pass  # a defined error is as good as a defined list of problems
    with pytest.raises(ScheduleError):
        Schedule(dose_ticks_ms=(big,), measurement_ticks_ms=())


# ---------------------------------------------------------------------------
# Fix round 1 (review): the number of measurements is bounded before any work
# ---------------------------------------------------------------------------


def test_the_measurement_bound_is_a_named_constant_below_the_day_positions() -> None:
    assert isinstance(schedule_module.MAX_MEASUREMENTS, int)
    assert 2 <= schedule_module.MAX_MEASUREMENTS < T_DAY_MS


@pytest.mark.parametrize("n", [10**9, 10**400, 2**1024, T_DAY_MS + 1])
def test_a_huge_measurement_count_is_refused_before_any_work(n: int) -> None:
    # no timing: the refusal comes from a comparison, so a loop over ``n`` would not return
    with pytest.raises(ScheduleError, match="TOO_MANY_MEASUREMENTS"):
        derive_schedule((clock(8),), n, HOLD, D1, D2, SW)
    with pytest.raises(ScheduleError, match="TOO_MANY_MEASUREMENTS"):
        derive_schedule((), n, HOLD, D1, D2, SW)


def test_the_measurement_bound_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(schedule_module, "MAX_MEASUREMENTS", 9)
    ticks = derive_schedule((clock(8),), 9, HOLD, D1, D2, SW).measurement_ticks_ms
    assert len(ticks) == 9  # exactly at the bound
    with pytest.raises(ScheduleError, match="TOO_MANY_MEASUREMENTS"):
        derive_schedule((clock(8),), 10, HOLD, D1, D2, SW)


def test_more_ticks_than_distinct_positions_in_the_day_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # even with the bound lifted, a day holds T_DAY distinct integer-ms ticks at most
    monkeypatch.setattr(schedule_module, "MAX_MEASUREMENTS", 10**12)
    with pytest.raises(ScheduleError, match="NO_POSITIONS"):
        derive_schedule((clock(8),), T_DAY_MS + 1, HOLD, D1, D2, SW)
    with pytest.raises(ScheduleError, match="NO_POSITIONS"):
        derive_schedule((clock(8),), 10**11, HOLD, D1, D2, SW)


def test_a_count_in_the_realistic_range_is_still_derived() -> None:
    ticks = derive_schedule(
        (clock(8), clock(20)), 3_000, HOLD, D1, D2, SW
    ).measurement_ticks_ms
    assert len(ticks) == 3_000 and list(ticks) == sorted(set(ticks))
    assert all(0 <= t < T_DAY_MS for t in ticks)
    # the largest admissible count works in negligible time (sub-quadratic placement)
    top = schedule_module.MAX_MEASUREMENTS
    many = derive_schedule((clock(8), clock(20)), top, HOLD, D1, D2, SW)
    assert len(many.measurement_ticks_ms) == top


def reference_extras(
    ticks: Sequence[int], extras: int
) -> tuple[int, ...] | ScheduleInfeasibleError:
    """The straightforward O(n^2) placement: split the earliest of the widest gaps."""
    out = list(ticks)
    for _ in range(extras):
        if len(out) < 2:
            return ScheduleInfeasibleError(
                [ScheduleProblem("NO_ANCHOR", None, "no anchor")]
            )
        widths = [b - a for a, b in pairwise(out)]
        i = widths.index(max(widths))
        if out[i + 1] - out[i] < 2:
            return ScheduleInfeasibleError(
                [ScheduleProblem("NO_ROOM", None, "no room")]
            )
        out.insert(i + 1, (out[i] + out[i + 1]) // 2)
    return tuple(out)


def test_extras_placement_equals_the_quadratic_reference_on_random_plans() -> None:
    rng = np.random.default_rng(20261005)
    compared = rooms = 0
    for case in range(400):
        n_doses = int(rng.integers(0, 5))
        if case % 2:  # coarse windows: room for many extras
            lo = HOUR
            hold, d1, d2, sw = (
                int(rng.integers(HOUR, 2 * HOUR)),
                int(rng.integers(0, HOUR)),
                0,
                int(rng.integers(0, 20 * MIN)),
            )
            d2 = d1 + int(rng.integers(MIN, 2 * HOUR))
        else:  # millisecond windows: the NO_ROOM boundary is reached
            lo = 10
            hold, d1, d2, sw = (
                int(rng.integers(0, 12)),
                int(rng.integers(0, 6)),
                0,
                int(rng.integers(0, 4)),
            )
            d2 = d1 + int(rng.integers(0, 8))
        doses = sorted({int(x) for x in rng.integers(lo, DAY - 3 * HOUR, size=n_doses)})
        try:
            base = derive_schedule(doses, 2 * len(doses), hold, d1, d2, sw)
        except ScheduleError:
            continue
        extras = int(rng.integers(0, 40))
        expected = reference_extras(base.measurement_ticks_ms, extras)
        compared += 1
        try:
            got = derive_schedule(
                doses, 2 * len(doses) + extras, hold, d1, d2, sw
            ).measurement_ticks_ms
        except ScheduleInfeasibleError as error:
            assert isinstance(expected, ScheduleInfeasibleError), (case, error)
            assert [p.check for p in error.problems] == [
                p.check for p in expected.problems
            ]
            rooms += 1
        else:
            assert got == expected, case
    assert compared > 100 and rooms > 5  # the comparison has both outcomes


# ---------------------------------------------------------------------------
# Fix round 1 (review): rounding of the post window, exact reasons of two refusals
# ---------------------------------------------------------------------------


def test_the_post_dose_midpoint_of_an_odd_width_window_rounds_down() -> None:
    a = clock(8)
    d2 = 3 * HOUR + 1  # window [a + 1 h, a + 3 h + 1 ms - 30 min]: low + high is odd
    schedule = derive_schedule((a,), 2, HOLD, D1, d2, SW)
    low, high = a + D1, a + d2 - SW
    assert (low + high) % 2 == 1
    assert (
        schedule.measurement_ticks_ms[1] == (low + high) // 2
    )  # not (low + high + 1) // 2
    assert schedule.measurement_ticks_ms[1] == a + 6_300_000


def test_a_tick_exactly_at_midnight_is_outside_the_day_with_its_own_reason() -> None:
    a = DAY - HOUR  # post tick = a + 1 h = 24:00 exactly
    with pytest.raises(ScheduleInfeasibleError) as info:
        derive_schedule((a,), 2, HOUR, HOUR, HOUR, 0)
    assert [p.check for p in info.value.problems] == ["TICK_OUTSIDE_DAY"]
    assert info.value.problems[0].dose_tick_ms == a
    ok = derive_schedule((a - 1,), 2, HOUR, HOUR, HOUR, 0)  # post tick 23:59:59.999
    assert ok.measurement_ticks_ms[-1] == DAY - 1
    first = derive_schedule((HOUR,), 2, HOUR, 0, 0, 0).measurement_ticks_ms[0]
    assert first == HOUR // 2  # a pre tick strictly inside the day
    with pytest.raises(ScheduleInfeasibleError) as info:
        derive_schedule((HOUR // 4,), 2, HOUR, 0, 0, 0)  # pre tick at -15 min
    assert [p.check for p in info.value.problems] == ["TICK_OUTSIDE_DAY"]
    assert (
        derive_schedule((1,), 2, 2, 0, 0, 0).measurement_ticks_ms[0] == 0
    )  # tick 0 is inside
    with pytest.raises(ScheduleInfeasibleError) as info:
        derive_schedule((0,), 2, 2, 0, 0, 0)  # pre tick at -1
    assert [p.check for p in info.value.problems] == ["TICK_OUTSIDE_DAY"]


def test_delta2_below_delta1_is_refused_with_its_own_message() -> None:
    for call in (
        lambda d2: derive_schedule((clock(8),), 2, HOLD, D1, d2, 0),
        lambda d2: check_schedule_consistency(TWO_DOSES, HOLD, D1, d2, 0),
    ):
        with pytest.raises(ScheduleError, match="delta2_ms .* below delta1_ms") as info:
            call(D1 - 1)
        assert not isinstance(info.value, ScheduleInfeasibleError)
    # equal windows are a point window: accepted, with the post tick at delta1
    point = derive_schedule((clock(8),), 2, HOLD, D1, D1, 0)
    assert point.measurement_ticks_ms[1] == clock(8) + D1


# ---------------------------------------------------------------------------
# Fix round 1 (review): a double take can cross midnight too; delay uniform; clamp
# ---------------------------------------------------------------------------


def test_the_intake_of_a_double_take_can_cross_midnight_and_keeps_its_slot_day() -> (
    None
):
    # last slot of the day is 10 min, gap 8 min, lag 5 min: the second dispense is at
    # 23:58 and its intake at 00:03 of the next day (3 min past midnight)
    schedule = Schedule(dose_ticks_ms=(DAY - 10 * MIN,), measurement_ticks_ms=())
    config = AdherenceConfig(intake_lag_ms=5 * MIN, double_take_gap_ms=8 * MIN)
    result = run(params(p_double_take=1.0), schedule=schedule, config=config, n_days=2)
    first, second = result.behaviour_log
    assert first.day_index == 0 and second.day_index == 1
    assert first.dispense_times_ms == (DAY - 10 * MIN, DAY - 2 * MIN)
    assert [(e.kind, e.t_device_ms) for e in result.events[:4]] == [
        (EventKind.DISPENSE, DAY - 10 * MIN),
        (EventKind.INTAKE, DAY - 5 * MIN),
        (EventKind.DISPENSE, DAY - 2 * MIN),
        (EventKind.INTAKE, DAY + 3 * MIN),  # past midnight, on the continuing axis
    ]
    crossing = result.events[3]
    assert (
        crossing.t_device_ms // DAY == first.day_index + 1
    )  # the event is in day 1 ...
    assert (
        first.dispense_times_ms[-1] // DAY == first.day_index
    )  # ... its dispense in day 0
    # no dispense ever leaves its slot's day, whatever the state
    for entry in result.behaviour_log:
        assert all(t // DAY == entry.day_index for t in entry.dispense_times_ms)
    times = [e.t_device_ms for e in result.events]
    assert times == sorted(times)


def test_simulated_delays_are_drawn_from_the_delay_uniform_not_the_state_uniform() -> (
    None
):
    # All four states present. Replaying the stream pairs (state, delay) uniform by uniform,
    # every delayed dose must be sample_delay_ms of ITS delay uniform.
    one = Schedule(dose_ticks_ms=(8 * HOUR,), measurement_ticks_ms=())
    n = 6_000
    p = params(0.25, 0.25, 0.25, mean_delay_ms=HOUR)
    result = run(p, schedule=one, n_days=n, seed=21)
    assert set(state_sequence(result)) == set(STATES)
    uniforms = adherence_stream(21, 0).random(2 * n)
    (length,) = one.slot_lengths_ms()
    delays = []
    for k, entry in enumerate(result.behaviour_log):
        if entry.state is DELAYED:
            expected = sample_delay_ms(HOUR, length, float(uniforms[2 * k + 1]))
            assert entry.dispense_times_ms == (entry.slot_tick_ms + expected,)
            delays.append(expected)
    # the state uniform of a delayed slot lies in [0.25, 0.5): reusing it would bias the delays
    # low; the delay law has its analytic truncated mean (plus the 1 ms discretisation shift)
    analytic, sd = truncated_moments(float(HOUR), float(length - 1))
    assert len(delays) > 1_000
    assert (
        abs(sum(delays) / len(delays) - analytic)
        < 4.0 * sd / math.sqrt(len(delays)) + 1.0
    )
    # and the uniforms really differ from the state ones on those slots
    state_u = [
        float(uniforms[2 * k])
        for k, e in enumerate(result.behaviour_log)
        if e.state is DELAYED
    ]
    reused = [sample_delay_ms(HOUR, length, u) for u in state_u]
    assert reused != delays
    assert sum(reused) / len(reused) < sum(delays) / len(delays) - 4.0 * sd / math.sqrt(
        len(delays)
    )


def test_the_delay_never_reaches_the_end_of_a_slot_for_a_uniform_next_to_one() -> None:
    # truncated_exponential reaches ``upper`` exactly for u just below 1, so int(x) would equal
    # the slot length minus one and the dose would leave its slot: the clamp keeps it inside
    assert truncated_exponential(100.0, 5.0, TOP) == 5.0
    assert sample_delay_ms(100, 6, TOP) <= 5
    assert sample_delay_ms(100, 6, TOP) == 5


@settings(max_examples=200, deadline=None)
@given(
    slot=st.sampled_from([2, 3, 4, 6, 7, 100, 1_001, 3_600_000]),
    mean=st.sampled_from([1, 3, 100, 10**6, 10**12]),
    steps=st.integers(min_value=0, max_value=64),
)
def test_the_delay_stays_inside_the_slot_near_one(
    slot: int, mean: int, steps: int
) -> None:
    u = 1.0
    for _ in range(steps + 1):
        u = math.nextafter(u, 0.0)  # TOP, then 63 doubles below it
    assert 1 <= sample_delay_ms(mean, slot, u) <= slot - 1


def test_the_module_text_names_both_ways_an_intake_crosses_midnight() -> None:
    doc = " ".join((adherence_module.__doc__ or "").split())
    assert "double take" in doc.split("INTAKE may fall after the end")[1][:400]
    assert "an intake of a late dose" not in doc
