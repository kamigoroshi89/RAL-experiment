"""``build_calibration_episodes`` (WS05-T08 tests 16 to 18).

FIXTURE-ONLY numbers on the F0 fixture registry (``step_ms = 60000``, ``sched_window = scale_sched =
1800000``). Time labels convert as ``t_ms = (60 * hh + mm) * 60000``; a day of index ``d`` lies on the
continuing axis at ``d * 86400000``.
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

import ralmon.monitor as m
from ralmon.conformal import CalibrationEpisode
from ralmon.spec import TemplateId
from tests.fixtures.monitor.predictive import (
    SpyCalibrator,
    StubForecaster,
    calibrator,
    hhmm,
    plan,
)

from .helpers import Inputs, LocalDay, evt, load_f0, load_lib, make_config, smp

REG = load_f0()
LIB = load_lib(REG)
STEP = 60_000
SCALE = 1_800_000.0


def measurement(
    inputs: Inputs, t: int, *, rx: int | None = None, bp: float = 130.0
) -> None:
    inputs.events.append(evt("measurement", t, rx=rx, source="cuff"))
    inputs.samples.append(smp("bp", t, bp, rx=rx))
    inputs.samples.append(smp("cuff_health", t, 1.0, rx=rx))
    inputs.samples.append(smp("inflation_ms", t, 45_000.0, rx=rx))


def day_of(inputs: Inputs, patient: str, index: int) -> LocalDay:
    return LocalDay(
        tuple(inputs.samples),
        tuple(inputs.events),
        patient_id=patient,
        day_index=index,
    )


def build(days: list[Any], plans: list[Any], forecaster: Any, **kwargs: Any) -> Any:
    config = make_config(REG, predictive=False)
    return m.build_calibration_episodes(
        days, plans, config, forecaster, registry=REG, templates=LIB, **kwargs
    )


# ---------------------------------------------------------------------------------------------
# test 16
# ---------------------------------------------------------------------------------------------


def hand_case() -> tuple[list[Any], list[Any], StubForecaster]:
    a, b = Inputs(), Inputs()
    measurement(a, hhmm(9, 51))
    measurement(b, hhmm(9, 25, 1))
    days = [day_of(a, "pA", 0), day_of(b, "pB", 1)]
    plans = [
        plan(REG, sched=[hhmm(9)], patient_id="pA"),
        plan(REG, sched=[hhmm(9, 0, 1)], patient_id="pB"),
    ]
    forecaster = StubForecaster(
        arrival={hhmm(9): hhmm(9, 52), hhmm(9, 0, 1): hhmm(9, 21, 1)}
    )
    return days, plans, forecaster


def test_build_calibration_episodes_hand_case() -> None:
    days, plans, forecaster = hand_case()
    episodes, n_censored = build(days, plans, forecaster)
    assert n_censored == 0
    assert [(e.patient_id, e.day_index, e.template) for e in episodes] == [
        ("pA", 0, TemplateId.SCHED),
        ("pB", 1, TemplateId.SCHED),
    ]
    assert all(isinstance(e, CalibrationEpisode) for e in episodes)
    # day A: predicted arrival 09:52, measurement 09:51 (G-SCHED-3: -21 minutes, -0.7)
    assert episodes[0].sigma_hat == pytest.approx(-1_320_000 / SCALE)
    assert episodes[0].sigma_hat == pytest.approx(-0.7333, abs=1e-4)
    assert episodes[0].sigma_true == pytest.approx(-1_260_000 / SCALE)
    assert episodes[0].sigma_true == pytest.approx(-0.7)
    # day B: predicted arrival 09:21 (+0.3), measurement 09:25 (+300000 ms, 0.1667)
    assert episodes[1].sigma_hat == pytest.approx(540_000 / SCALE)
    assert episodes[1].sigma_hat == pytest.approx(0.3)
    assert episodes[1].sigma_true == pytest.approx(300_000 / SCALE)
    assert episodes[1].sigma_true == pytest.approx(0.1667, abs=1e-4)


def test_the_episodes_fit_a_calibrator_of_the_model_they_were_made_with() -> None:
    days, plans, forecaster = hand_case()
    episodes, _ = build(days, plans, forecaster)
    cal = calibrator(version=None)
    cal.fit(episodes, 0.5, model_version=forecaster.model_version)
    assert cal.calibrated_for == forecaster.model_version
    assert cal.n_scores == 2


# ---------------------------------------------------------------------------------------------
# test 17
# ---------------------------------------------------------------------------------------------


def test_episodes_use_measured_completion_only_and_skip_censored() -> None:
    inputs = Inputs()
    measurement(inputs, hhmm(9, 20))
    # the second instance closes after the end of the day (23:50 + 30 min): censored, never invented
    plans = [plan(REG, sched=[hhmm(9), hhmm(23, 50)])]
    forecaster = StubForecaster(arrival=lambda t: t + 600_000)
    episodes, n_censored = build([day_of(inputs, "p", 0)], plans, forecaster)
    assert n_censored == 1
    assert len(episodes) == 1
    assert episodes[0].sigma_true == pytest.approx((hhmm(9, 30) - hhmm(9, 20)) / SCALE)


def test_a_late_measurement_is_not_part_of_the_completed_day() -> None:
    inputs = Inputs()
    # device time 09:20, received at 09:40: after the watermark of its step, the monitor excludes it
    measurement(inputs, hhmm(9, 20), rx=hhmm(9, 40))
    episodes, n_censored = build(
        [day_of(inputs, "p", 0)],
        [plan(REG, sched=[hhmm(9)])],
        StubForecaster(arrival=hhmm(9, 10)),
    )
    assert n_censored == 0
    assert (
        episodes[0].sigma_true == -1.0
    )  # no accepted measurement: the guard fails, minus infinity
    assert episodes[0].sigma_hat > 0.0


def test_the_function_has_no_parameter_that_could_carry_a_latent_day() -> None:
    parameters = list(inspect.signature(m.build_calibration_episodes).parameters)
    assert parameters == [
        "days",
        "plans",
        "config",
        "forecaster",
        "registry",
        "templates",
    ]


def test_a_day_with_a_latent_trace_never_has_it_read() -> None:
    class Guarded(LocalDay):
        @property
        def latent(self) -> Any:
            raise AssertionError("the latent trace was read")

        @property
        def ground_truth(self) -> Any:
            raise AssertionError("the ground truth was read")

    inputs = Inputs()
    measurement(inputs, hhmm(9, 20))
    day = Guarded(tuple(inputs.samples), tuple(inputs.events))
    episodes, _ = build(
        [day], [plan(REG, sched=[hhmm(9)])], StubForecaster(arrival=hhmm(9, 40))
    )
    assert len(episodes) == 1


def test_arguments_are_checked() -> None:
    days, plans, forecaster = hand_case()
    with pytest.raises(m.MonitorInputError):
        build(days, plans[:1], forecaster)
    with pytest.raises(m.MonitorInputError):
        build("not days", plans, forecaster)  # type: ignore[arg-type]
    assert build([], [], forecaster) == ([], 0)


def test_an_instance_decided_at_activation_or_without_a_forecast_makes_no_episode() -> (
    None
):
    inputs = Inputs()
    measurement(inputs, hhmm(9))  # lands on the step of the tick: decided at once
    episodes, n_censored = build(
        [day_of(inputs, "p", 0)],
        [plan(REG, sched=[hhmm(9), hhmm(12)])],
        StubForecaster(
            arrival={hhmm(9): hhmm(9, 40)}
        ),  # no arrival for the 12:00 tick: no basis
    )
    assert episodes == [] and n_censored == 0


def test_resp_episode_uses_the_pre_dose_pressure_and_the_scheduled_measurement() -> (
    None
):
    inputs = Inputs()
    inputs.samples.append(smp("bp", hhmm(6, 50), 150.0))
    inputs.events.append(evt("dispense", hhmm(7), source="dispenser", seq=4))
    inputs.samples.append(smp("auth", hhmm(7), 1.0, seq=4))
    measurement(inputs, hhmm(8, 30), bp=138.0)
    forecaster = StubForecaster(
        arrival=lambda t: t + 60_000,
        bp=145.0,
        signals=frozenset({"meas", "bp"}),
    )
    episodes, n_censored = build(
        [day_of(inputs, "p", 0)],
        [plan(REG, sched=[hhmm(8, 30)], schedule=[hhmm(8, 30), hhmm(7)])],
        forecaster,
    )
    resp = [e for e in episodes if e.template is TemplateId.RESP]
    assert len(resp) == 1 and n_censored == 0
    assert resp[0].sigma_hat == pytest.approx((150 - 145 - 10) / 20)  # forecast 145
    assert resp[0].sigma_true == pytest.approx((150 - 138 - 10) / 20)  # measured 138


# ---------------------------------------------------------------------------------------------
# test 18 (Hypothesis)
# ---------------------------------------------------------------------------------------------


@settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    ticks=st.lists(
        st.integers(min_value=10, max_value=21 * 60),
        min_size=1,
        max_size=3,
        unique=True,
    ),
    offsets=st.lists(st.integers(min_value=-5, max_value=90), min_size=3, max_size=3),
    measured=st.lists(
        st.one_of(st.none(), st.integers(min_value=0, max_value=100)),
        min_size=3,
        max_size=3,
    ),
)
def test_calibration_and_deployment_share_the_code_path(
    ticks: list[int], offsets: list[int], measured: list[int | None]
) -> None:
    ticks = sorted(t * 60_000 for t in ticks)
    # keep the ticks one window apart so that each instance has its own horizon
    kept: list[int] = []
    for t in ticks:
        if not kept or t - kept[-1] >= 2 * 1_800_000:
            kept.append(t)
    arrivals = {t: t + 60_000 * offsets[i] for i, t in enumerate(kept)}
    inputs = Inputs()
    for i, t in enumerate(kept):
        if measured[i] is not None:
            measurement(inputs, t + 60_000 * measured[i])
    day = day_of(inputs, "p", 0)
    schedule_plan = plan(REG, sched=kept)
    forecaster = StubForecaster(arrival=lambda t: arrivals.get(t))
    episodes, _ = build([day], [schedule_plan], forecaster)

    spy = SpyCalibrator(calibrator())
    config = make_config(REG, predictive=True, alpha=0.5)
    m.run_offline(
        day, schedule_plan, config, spy, forecaster, registry=REG, templates=LIB
    )
    assert [
        e.sigma_hat for e in episodes if e.template is TemplateId.SCHED
    ] == spy.sigma_hats
