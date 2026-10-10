"""Robot-deadline forecaster (WS05-T05): an impulse of ``meas`` at the predicted arrival.

Fixture-only arithmetic. Step 60_000 ms. Time labels convert with ``t_ms = (60 * hh + mm) * 60000``.
"""

from __future__ import annotations

from typing import Any

import pytest

import ralmon.monitor as m
from ralmon.signals import Event, EventKind

from .helpers import LocalDay, smp
from .helpers import hhmm as _hhmm

STEP = 60_000  # FIXTURE-ONLY


def hhmm(hh: int, mm: int = 0) -> int:
    return _hhmm(hh, mm)


def tick(t: int) -> Event:
    return Event(EventKind.SCHEDULE_TICK, t, t, "plan", {}, None)


def meas(t: int) -> Event:
    return Event(EventKind.MEASUREMENT, t, t, "cuff", {}, None)


def robot(t: int, eta: float, queue: float) -> list[Any]:
    return [smp("nav_eta_ms", t, eta), smp("task_queue_ms", t, queue)]


def state_at_nine() -> list[Any]:
    """Latest samples at 09:00: ETA 25 min and queue 10 min (FIXTURE-ONLY)."""
    return robot(hhmm(9), 1_500_000.0, 600_000.0)


def day_one() -> LocalDay:
    # tick 09:00, state just before it, first meas 09:37: residual +120_000
    return LocalDay(
        samples=robot(hhmm(9) - STEP, 1_500_000.0, 600_000.0),
        events=[tick(hhmm(9)), meas(hhmm(9, 37))],
    )


def day_two() -> LocalDay:
    # tick 21:00, ETA 300_000, queue 0, first meas 21:04: residual -60_000
    return LocalDay(
        samples=robot(hhmm(21) - STEP, 300_000.0, 0.0),
        events=[tick(hhmm(21)), meas(hhmm(21, 4))],
    )


def day_censored() -> LocalDay:
    # a tick with no later meas that day
    return LocalDay(
        samples=robot(hhmm(22) - STEP, 100_000.0, 0.0), events=[tick(hhmm(22))]
    )


def zero_bias() -> Any:
    f = m.DeadlineForecaster(STEP)
    day = LocalDay(
        samples=robot(hhmm(9), 1_500_000.0, 600_000.0),
        events=[tick(hhmm(9)), meas(hhmm(9, 35))],
    )
    f.fit([day])
    assert f.bias_ms == 0.0
    return f


def learned() -> Any:
    f = m.DeadlineForecaster(STEP)
    f.fit([day_one(), day_two(), day_censored()])
    return f


def test_deadline_forecast_places_impulse_at_predicted_arrival() -> None:
    out = zero_bias().predict(state_at_nine(), hhmm(9), 2_400_000)
    assert out.signal == "meas"
    assert out.t_from_ms == hhmm(9)
    assert len(out.mean) == 40
    assert out.mean[34] == 1.0  # grid time t + 35 * step = 09:35
    assert [i for i, v in enumerate(out.mean) if v != 0.0] == [34]
    assert hhmm(9, 35) == 34_500_000


def test_deadline_forecast_all_zero_beyond_horizon() -> None:
    out = zero_bias().predict(state_at_nine(), hhmm(9), 1_800_000)
    assert len(out.mean) == 30
    assert all(v == 0.0 for v in out.mean)


def test_deadline_fit_learns_mean_signed_bias_and_counts_censoring() -> None:
    f = learned()
    assert f.bias_ms == 30_000.0
    assert f.n_train_episodes == 2
    assert f.n_censored == 1


def test_deadline_forecast_uses_learned_bias() -> None:
    out = learned().predict(state_at_nine(), hhmm(9), 2_400_000)
    assert len(out.mean) == 40
    # predicted arrival 09:35:30 = 34_530_000; the first grid step at or after it is t + 36 * step
    assert out.mean[35] == 1.0  # ceiling rule
    assert [i for i, v in enumerate(out.mean) if v != 0.0] == [35]


def test_deadline_state_without_robot_signals_raises() -> None:
    f = learned()
    with pytest.raises(m.InsufficientHistoryError):
        f.predict([], hhmm(9), 600_000)
    with pytest.raises(m.InsufficientHistoryError):
        f.predict([smp("nav_eta_ms", hhmm(9), 1.0)], hhmm(9), 600_000)
    with pytest.raises(m.InsufficientHistoryError):
        f.predict([smp("task_queue_ms", hhmm(9), 1.0)], hhmm(9), 600_000)
    # a state published after t does not exist yet
    late = robot(hhmm(9, 1), 1.0, 1.0)
    with pytest.raises(m.InsufficientHistoryError):
        f.predict(late, hhmm(9), 600_000)


def test_the_latest_robot_state_at_or_before_t_is_used() -> None:
    f = zero_bias()
    history = robot(hhmm(8, 50), 9_000_000.0, 9_000_000.0) + state_at_nine()
    out = f.predict(history, hhmm(9), 2_400_000)
    assert out.mean[34] == 1.0


def test_arrival_not_after_t_is_placed_at_the_first_step() -> None:
    f = zero_bias()
    out = f.predict(robot(hhmm(9), 0.0, 0.0), hhmm(9), 180_000)
    assert list(out.mean) == [1.0, 0.0, 0.0]


def test_negative_bias_that_passes_the_clock_does_not_leave_the_grid() -> None:
    f = m.DeadlineForecaster(STEP)
    day = LocalDay(
        samples=robot(hhmm(9), 600_000.0, 0.0),
        events=[tick(hhmm(9)), meas(hhmm(9, 1))],  # residual -540_000
    )
    f.fit([day])
    out = f.predict(robot(hhmm(9), 60_000.0, 0.0), hhmm(9), 120_000)
    assert list(out.mean) == [1.0, 0.0]


def test_negative_or_non_finite_robot_state_is_refused() -> None:
    f = zero_bias()
    for eta, queue in ((-1.0, 0.0), (0.0, -1.0), (float("nan"), 0.0)):
        with pytest.raises(ValueError):
            f.predict(robot(hhmm(9), eta, queue), hhmm(9), 600_000)


def test_ticks_and_measurements_may_come_as_samples_without_double_counting() -> None:
    day = LocalDay(
        samples=[
            *robot(hhmm(9) - STEP, 1_500_000.0, 600_000.0),
            smp("sched_tick", hhmm(9), 1.0),
            smp("meas", hhmm(9, 37), 1.0),
        ],
        events=[tick(hhmm(9)), meas(hhmm(9, 37))],
    )
    f = m.DeadlineForecaster(STEP)
    f.fit([day])
    assert f.n_train_episodes == 1
    assert f.bias_ms == 120_000.0


def test_tick_without_robot_state_is_counted_and_not_trained_on() -> None:
    bare = LocalDay(samples=[], events=[tick(hhmm(9)), meas(hhmm(9, 40))])
    f = m.DeadlineForecaster(STEP)
    f.fit([day_one(), bare])
    assert f.n_train_episodes == 1
    assert f.n_no_robot_state == 1
    assert f.n_censored == 0
    assert f.bias_ms == 120_000.0


def test_fit_with_no_usable_episode_is_refused_not_defaulted() -> None:
    f = m.DeadlineForecaster(STEP)
    with pytest.raises(ValueError):
        f.fit([day_censored()])
    with pytest.raises(ValueError):
        f.fit([])


def test_fit_is_deterministic_and_version_follows_the_bias() -> None:
    a, b = learned(), learned()
    assert a.model_version == b.model_version
    assert a.model_version != zero_bias().model_version
    assert a.supported_signals == frozenset({"meas"})


def test_other_signal_is_unsupported() -> None:
    f = zero_bias()
    with pytest.raises(m.UnsupportedSignalError):
        f.predict(state_at_nine(), hhmm(9), 600_000, signal="bp")
    out = f.predict(state_at_nine(), hhmm(9), 600_000, signal="meas")
    assert out.signal == "meas"


def test_a_delay_that_overflows_is_refused_with_a_named_error() -> None:
    f = zero_bias()
    # both finite, but their sum is not representable: no bare OverflowError
    with pytest.raises(ValueError):
        f.predict(robot(hhmm(9), 1e308, 1e308), hhmm(9), 600_000)
    for eta, queue in (
        (float("inf"), 0.0),
        (0.0, float("inf")),
        (float("nan"), float("nan")),
    ):
        with pytest.raises(ValueError):
            f.predict(robot(hhmm(9), eta, queue), hhmm(9), 600_000)


def test_a_huge_but_finite_delay_gives_an_all_zero_path() -> None:
    out = zero_bias().predict(robot(hhmm(9), 1e300, 0.0), hhmm(9), 600_000)
    assert list(out.mean) == [0.0] * 10
