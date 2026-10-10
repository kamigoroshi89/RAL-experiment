"""Predictive mode of the monitor (WS05-T08 tests 1 to 15).

FIXTURE-ONLY numbers: the F0 registry (``step_ms = 60000``, ``sched_window = scale_sched = 1800000``,
``delta1 = 3600000``, ``delta2 = 10800000``, ``scale_resp = 20``, ``delta_resp = 10``) and the nine scores of
the WS05-T06 fixture ``R = [-0.2, -0.1, 0.0, 0.1, 0.1, 0.2, 0.3, 0.4, 0.6]``. The forecasters are stubs that
return fixed paths. Time labels convert as ``t_ms = (60 * hh + mm) * 60000``.

Reading of test 3 recorded in the Notes of WS05-T08: a PREDICTED_VIOLATION state is sticky (docs/formal/05
section 4, T5), so the instance keeps emitting records in that state until its definitive record; "at most one
PREDICTED_VIOLATION record" is read as one prediction and one transition, that is one run of the state that
starts at the activation step, and the sequences of states are compared with consecutive repeats collapsed.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Sequence
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

import ralmon.monitor as m
from ralmon.conformal import BonferroniAllocation
from ralmon.monitor import (
    InsufficientHistoryError,
    MonitorConfigError,
    StaleCalibratorError,
    VerdictState,
)
from ralmon.spec import RhoKind
from tests.fixtures.monitor.predictive import (
    R_SCORES,
    SpyCalibrator,
    StubForecaster,
    calibrator,
    hhmm,
    plan,
)

from .helpers import (
    Inputs,
    LocalDay,
    drive,
    evt,
    load_f0,
    load_lib,
    make_config,
    smp,
)

REG = load_f0()
LIB = load_lib(REG)
STEP = 60_000
PENDING = VerdictState.PENDING
PREDICTED = VerdictState.PREDICTED_VIOLATION
VIOLATED = VerdictState.VIOLATED
SATISFIED = VerdictState.SATISFIED
DEFINITIVE = (VIOLATED, SATISFIED)

TICK = hhmm(9)  # 32_400_000
DEADLINE = hhmm(9, 30)


def monitor(
    *,
    sched: Sequence[int] = (),
    schedule: Sequence[int] = (),
    forecaster: Any = None,
    cal: Any = None,
    alpha: float | None = 0.2,
    variant: str = "likely",
    d_ms: int = 0,
    predictive: bool = True,
) -> Any:
    config = make_config(
        REG, d_ms=d_ms, predictive=predictive, alpha=alpha, variant=variant
    )
    mon = m.StreamingMonitor(config, REG, LIB, calibrator=cal, forecaster=forecaster)
    mon.load(plan(REG, sched=sched, schedule=schedule))
    return mon


def measurement(
    inputs: Inputs, t: int, bp: float = 130.0, seq: int | None = None
) -> None:
    """One cuff message: the measurement event and its three samples (a healthy cuff)."""
    inputs.events.append(evt("measurement", t, source="cuff", seq=seq))
    inputs.samples.append(smp("bp", t, bp, seq=seq))
    inputs.samples.append(smp("cuff_health", t, 1.0, seq=seq))
    inputs.samples.append(smp("inflation_ms", t, 45_000.0, seq=seq))


def run(mon: Any, inputs: Inputs, until: int = hhmm(10), *, d_ms: int = 0) -> list[Any]:
    return drive(mon, inputs, until // STEP, d_ms=d_ms)


def of(records: Sequence[Any], key: str) -> list[Any]:
    return [r for r in records if r.instance_key == key]


def collapsed(records: Sequence[Any], key: str) -> list[VerdictState]:
    """The states of an instance with consecutive repeats collapsed."""
    return [k for k, _ in itertools.groupby(r.state for r in of(records, key))]


def definitive(records: Sequence[Any]) -> dict[str, list[Any]]:
    out: dict[str, list[Any]] = {}
    for r in records:
        if r.state in DEFINITIVE:
            out.setdefault(r.instance_key, []).append(r)
    return out


def late_arrival_forecaster(arrival: int = hhmm(9, 52)) -> StubForecaster:
    return StubForecaster(arrival=arrival)


# ---------------------------------------------------------------------------------------------
# test 1
# ---------------------------------------------------------------------------------------------


def test_predictive_false_matches_measured_only_run() -> None:
    inputs = Inputs()
    measurement(inputs, hhmm(9, 51))
    measurement(inputs, hhmm(12, 20))
    forecaster = late_arrival_forecaster()
    plain = monitor(sched=[TICK, hhmm(12)], predictive=False)
    spied = monitor(
        sched=[TICK, hhmm(12)],
        forecaster=forecaster,
        cal=calibrator(),
        predictive=False,
    )
    want = run(plain, inputs, hhmm(13))
    got = run(spied, inputs, hhmm(13))
    assert got == want
    assert not [r for r in got if r.state is PREDICTED]
    assert forecaster.calls == []  # ablation A2: the forecaster is never called
    assert spied.stats().predictions_made == 0


# ---------------------------------------------------------------------------------------------
# test 2
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("missing", ["calibrator", "forecaster", "alpha"])
def test_predictive_true_requires_calibrator_forecaster_and_alpha(missing: str) -> None:
    config = make_config(
        REG, predictive=True, alpha=None if missing == "alpha" else 0.2
    )
    cal = None if missing == "calibrator" else calibrator()
    forecaster = None if missing == "forecaster" else late_arrival_forecaster()
    with pytest.raises(MonitorConfigError):
        m.StreamingMonitor(config, REG, LIB, calibrator=cal, forecaster=forecaster)
    with pytest.raises(MonitorConfigError):
        m.run_offline(
            LocalDay((), ()),
            plan(REG),
            config,
            cal,
            forecaster,
            registry=REG,
            templates=LIB,
        )


def test_predictive_true_with_all_parts_is_accepted() -> None:
    mon = monitor(sched=[TICK], forecaster=late_arrival_forecaster(), cal=calibrator())
    assert mon.stats().n_tests == 1


# ---------------------------------------------------------------------------------------------
# test 3
# ---------------------------------------------------------------------------------------------


def test_prediction_only_while_pending_and_once_per_instance() -> None:
    inputs = Inputs()
    measurement(inputs, hhmm(9, 51))
    forecaster = late_arrival_forecaster()
    mon = monitor(sched=[TICK], forecaster=forecaster, cal=calibrator())
    records = run(mon, inputs, hhmm(10))
    key = f"sched@{TICK}"
    mine = of(records, key)
    # one prediction (one call of the forecaster) for the instance, at its activation step
    assert len(forecaster.calls) == 1
    assert forecaster.calls[0].t_ms == TICK
    # the activation step emits PENDING first and PREDICTED_VIOLATION second, with the same t_eval_ms
    assert [(r.state, r.t_eval_ms) for r in mine[:2]] == [
        (PENDING, TICK),
        (PREDICTED, TICK),
    ]
    # one run of the sticky state, which begins at the activation step; none after a definitive record
    runs = [(k, len(list(g))) for k, g in itertools.groupby(r.state for r in mine)]
    assert [k for k, _ in runs] == [PENDING, PREDICTED, VIOLATED]
    assert runs[0][1] == 1
    first_definitive = next(i for i, r in enumerate(mine) if r.state in DEFINITIVE)
    assert all(r.state not in (PENDING, PREDICTED) for r in mine[first_definitive:])
    assert mine[first_definitive].decided_at_ms == DEADLINE
    # the sequence of states follows the allowed transitions of #verdict
    allowed = {(PENDING, PREDICTED), (PREDICTED, VIOLATED)}
    seq = collapsed(records, key)
    assert all(pair in allowed for pair in itertools.pairwise(seq))


def test_an_instance_decided_at_its_activation_step_is_not_predicted() -> None:
    inputs = Inputs()
    measurement(inputs, TICK)  # the measurement lands on the step of the tick
    forecaster = late_arrival_forecaster()
    mon = monitor(sched=[TICK], forecaster=forecaster, cal=calibrator())
    records = run(mon, inputs, hhmm(10))
    assert forecaster.calls == []
    assert PREDICTED not in collapsed(records, f"sched@{TICK}")
    assert dict(mon.stats().prediction_skips) == {"decided_at_activation": 1}


# ---------------------------------------------------------------------------------------------
# test 4 (Hypothesis)
# ---------------------------------------------------------------------------------------------

EXTREME = st.sampled_from(
    [
        0.0,
        1.0,
        -1.0,
        0.5,
        1e300,
        -1e300,
        1e15,
        -1e15,
        math.inf,
        -math.inf,
        math.nan,
        145.0,
        30.0,
    ]
)


@settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    base=st.lists(EXTREME, min_size=1, max_size=6),
    exact=st.booleans(),
    t_meas=st.sampled_from([None, hhmm(9, 5), hhmm(9, 40), hhmm(12, 5), hhmm(13, 5)]),
    arrival_kind=st.booleans(),
)
def test_forecast_never_produces_definitive_verdict(
    base: list[float], exact: bool, t_meas: int | None, arrival_kind: bool
) -> None:
    inputs = Inputs()
    inputs.samples.append(smp("bp", hhmm(6, 50), 150.0))
    inputs.events.append(evt("dispense", hhmm(7), source="dispenser", seq=1))
    inputs.samples.append(smp("auth", hhmm(7), 1.0, seq=1))
    if t_meas is not None:
        measurement(inputs, t_meas)

    def raw(signal: str, t_ms: int, horizon_ms: int, n: int) -> list[float]:
        cycle = itertools.cycle(base)
        length = n if exact else n + 1
        return [next(cycle) for _ in range(length)]

    kwargs: dict[str, Any] = {"raw": raw, "signals": frozenset({"meas", "bp"})}
    if arrival_kind:
        kwargs["arrival"] = hhmm(12, 50)
    sched = [TICK, hhmm(12)]
    schedule = [TICK, hhmm(12), hhmm(7)]
    until = hhmm(14)
    predictive = monitor(
        sched=sched,
        schedule=schedule,
        forecaster=StubForecaster(**kwargs),
        cal=calibrator(),
        alpha=0.9,
    )
    measured = monitor(sched=sched, schedule=schedule, predictive=False)
    got = run(predictive, inputs, until)
    want = run(measured, inputs, until)
    assert definitive(got) == definitive(want)
    # outside the prediction the two runs agree on everything but the state and rho of the PENDING steps
    assert len({r.instance_key for r in got}) == len({r.instance_key for r in want})
    for key in {r.instance_key for r in want}:
        first_got = [r for r in of(got, key) if r.state in DEFINITIVE][:1]
        first_want = [r for r in of(want, key) if r.state in DEFINITIVE][:1]
        assert [(r.state, r.decided_at_ms) for r in first_got] == [
            (r.state, r.decided_at_ms) for r in first_want
        ]


# ---------------------------------------------------------------------------------------------
# tests 5, 6, 15
# ---------------------------------------------------------------------------------------------


def test_scheduled_arrival_predicted_late_then_violated() -> None:
    inputs = Inputs()
    measurement(inputs, hhmm(9, 51))  # G-SCHED-3: 21 minutes after the deadline
    spy = SpyCalibrator(calibrator())
    mon = monitor(sched=[TICK], forecaster=late_arrival_forecaster(), cal=spy)
    records = run(mon, inputs, hhmm(10))
    key = f"sched@{TICK}"
    assert collapsed(records, key) == [PENDING, PREDICTED, VIOLATED]
    assert spy.sigma_hats == [pytest.approx(-1_320_000 / 1_800_000)]
    assert spy.sigma_hats[0] == pytest.approx(-0.7333, abs=1e-4)
    # one instance in the plan: the whole alpha is the level of the test, q_{0.8} = 0.4
    assert spy.levels == [pytest.approx(0.2)]
    predicted = next(r for r in of(records, key) if r.state is PREDICTED)
    assert predicted.rho is not None
    assert predicted.rho.value == pytest.approx(0.9)  # alpha_star = (0 + 1) / 10
    assert predicted.rho.kind is RhoKind.PREDICTED
    assert predicted.predicted_sigma_norm == pytest.approx(-0.3333, abs=1e-4)
    # the definitive record is at the deadline, from the measured prefix, whatever the forecast said
    verdict = next(r for r in of(records, key) if r.state is VIOLATED)
    assert verdict.decided_at_ms == DEADLINE
    assert verdict.rho is not None and verdict.rho.kind is RhoKind.DETERMINISTIC
    assert verdict.predicted_sigma_norm is None


def test_predicted_then_satisfied_is_a_false_predictive_alarm() -> None:
    inputs = Inputs()
    measurement(inputs, hhmm(9, 20))
    mon = monitor(sched=[TICK], forecaster=late_arrival_forecaster(), cal=calibrator())
    records = run(mon, inputs, hhmm(10))
    key = f"sched@{TICK}"
    assert collapsed(records, key) == [PENDING, PREDICTED, SATISFIED]
    final = next(r for r in of(records, key) if r.state is SATISFIED)
    assert final.rho is None  # T7: the predicted rho is dropped
    assert final.decided_at_ms == hhmm(9, 20)
    assert final.predicted_sigma_norm is None


def test_predicted_record_fields() -> None:
    mon = monitor(sched=[TICK], forecaster=late_arrival_forecaster(), cal=calibrator())
    records = run(mon, Inputs(), hhmm(9, 5))
    key = f"sched@{TICK}"
    pending, predicted = of(records, key)[:2]
    assert pending.state is PENDING and predicted.state is PREDICTED
    assert predicted.rho is not None
    assert predicted.rho.kind is RhoKind.PREDICTED
    assert predicted.rho.alpha == pytest.approx(0.2)  # the per-test level (one test)
    assert (
        predicted.rho.guarantee
        == "marginal over patient episodes under exchangeability"
    )
    # sigma_hat + q = -0.7333 + 0.4 clipped to [-1, 1]
    assert predicted.predicted_sigma_norm == pytest.approx(-1_320_000 / 1_800_000 + 0.4)
    # ADR-008: the raw interval remains the measured one
    for field in (
        "sigma_interval",
        "sigma_norm_interval",
        "pending_until_ms",
        "t_eval_ms",
    ):
        assert getattr(predicted, field) == getattr(pending, field)
    assert predicted.decided_at_ms is None
    assert predicted.guard_failed is None
    # the sticky state keeps the fields on the following steps
    later = of(records, key)[2]
    assert later.state is PREDICTED and later.rho == predicted.rho
    assert later.predicted_sigma_norm == predicted.predicted_sigma_norm


def test_predicted_sigma_norm_is_clipped_to_the_unit_interval() -> None:
    # a very late arrival: sigma_hat = -1 (clipped), q = 0.4: the bound is -0.6
    forecaster = StubForecaster(arrival=hhmm(12))
    mon = monitor(sched=[TICK], forecaster=forecaster, cal=calibrator())
    records = run(mon, Inputs(), hhmm(9, 5))
    predicted = next(r for r in records if r.state is PREDICTED)
    assert predicted.predicted_sigma_norm == pytest.approx(-0.6)
    # a score set whose quantile is large keeps the bound inside [-1, 1]
    wide = calibrator(scores=(-5.0, -4.0, -3.0, -2.0, -1.0, 0.0, 0.0, 0.0, 0.0))
    mon2 = monitor(sched=[TICK], forecaster=StubForecaster(arrival=hhmm(12)), cal=wide)
    rec2 = next(r for r in run(mon2, Inputs(), hhmm(9, 5)) if r.state is PREDICTED)
    assert -1.0 <= rec2.predicted_sigma_norm <= 0.0  # type: ignore[operator]


# ---------------------------------------------------------------------------------------------
# test 7
# ---------------------------------------------------------------------------------------------


def test_variant_switch_changes_emission() -> None:
    # sigma_hat = 0.3 (arrival 09:21): the upper quantile 0.4 and the lower quantile -0.1 both keep it
    for variant in ("likely", "possible"):
        mon = monitor(
            sched=[TICK],
            forecaster=StubForecaster(arrival=hhmm(9, 21)),
            cal=calibrator(),
            variant=variant,
        )
        records = run(mon, Inputs(), hhmm(9, 5))
        assert not [r for r in records if r.state is PREDICTED], variant
    # sigma_hat = 0.0 (arrival at the deadline): "likely" 0.0 + 0.4 >= 0 stays silent, "possible" emits with
    # the lower quantile q^lo_{0.2} = -0.1 (ADR-030; the symmetric reading 0.3 - 0.4 < 0 is not used)
    emitted = {}
    for variant in ("likely", "possible"):
        mon = monitor(
            sched=[TICK],
            forecaster=StubForecaster(arrival=DEADLINE),
            cal=calibrator(),
            variant=variant,
        )
        records = run(mon, Inputs(), hhmm(9, 5))
        emitted[variant] = [r for r in records if r.state is PREDICTED]
    assert emitted["likely"] == []
    assert emitted["possible"]
    first = emitted["possible"][0]
    # the bound that decided: sigma_hat + q^lo = 0.0 - 0.1
    assert first.predicted_sigma_norm == pytest.approx(-0.1)
    assert first.rho is not None and first.rho.value == pytest.approx(
        0.2
    )  # m = 2 scores below 0


def test_a_possible_alert_with_an_infinite_lower_quantile_is_counted_as_uninformative() -> (
    None
):
    # alpha 0.05 with nine scores: j = floor(10 * 0.05) = 0, the lower quantile is -inf and every instance emits
    mon = monitor(
        sched=[TICK],
        forecaster=StubForecaster(arrival=hhmm(9, 21)),
        cal=calibrator(),
        variant="possible",
        alpha=0.05,
    )
    records = run(mon, Inputs(), hhmm(9, 5))
    predicted = next(r for r in records if r.state is PREDICTED)
    assert predicted.rho is not None and predicted.rho.value == 0.0
    assert predicted.predicted_sigma_norm == -1.0
    assert mon.stats().predictions_uninformative == 1


def test_a_level_below_one_over_n_plus_one_silences_the_early_warning_and_says_so() -> (
    None
):
    # likely: alpha 0.05 gives an infinite quantile with nine scores; nothing is emitted, and it is counted
    mon = monitor(
        sched=[TICK],
        forecaster=late_arrival_forecaster(),
        cal=calibrator(),
        alpha=0.05,
    )
    records = run(mon, Inputs(), hhmm(9, 5))
    assert not [r for r in records if r.state is PREDICTED]
    stats = mon.stats()
    assert stats.predictions_made == 1 and stats.predictions_emitted == 0


# ---------------------------------------------------------------------------------------------
# test 8
# ---------------------------------------------------------------------------------------------


def two_sched_one_resp_inputs() -> Inputs:
    inputs = Inputs()
    inputs.samples.append(smp("bp", hhmm(6, 50), 150.0))
    inputs.events.append(evt("dispense", hhmm(10), source="dispenser", seq=7))
    inputs.samples.append(smp("auth", hhmm(10), 1.0, seq=7))
    return inputs


def test_alpha_is_allocated_over_pending_tests_of_the_patient_day() -> None:
    sched = [TICK, hhmm(12)]
    schedule = [
        TICK,
        hhmm(12),
        hhmm(10),
    ]  # the third tick is a dispense tick (no SCHED instance)
    forecaster = StubForecaster(
        arrival=lambda t: t + 3_120_000,  # 52 minutes after each tick
        bp=160.0,  # a rise instead of a drop: sigma_hat = -1 (clipped)
        signals=frozenset({"meas", "bp"}),
    )
    spy = SpyCalibrator(calibrator())
    mon = monitor(
        sched=sched, schedule=schedule, forecaster=forecaster, cal=spy, alpha=0.3
    )
    records = run(mon, two_sched_one_resp_inputs(), hhmm(13))
    stats = mon.stats()
    assert stats.n_tests == 3
    assert stats.per_test_alpha == pytest.approx(
        float(BonferroniAllocation().per_test(0.3, 3))
    )
    assert stats.per_test_alpha == pytest.approx(0.1)
    predicted = [r for r in records if r.state is PREDICTED]
    assert {r.instance_key.split("@")[0] for r in predicted} == {"sched", "resp"}
    assert predicted and all(
        r.rho is not None and r.rho.alpha == pytest.approx(0.1) for r in predicted
    )
    # the exact level reaches the calibrator, not the float image
    from fractions import Fraction

    assert spy.levels and all(level == Fraction(1, 10) for level in spy.levels)


def test_instances_without_a_predictive_path_are_not_counted() -> None:
    sched = [TICK, hhmm(12)]
    schedule = [TICK, hhmm(12), hhmm(10)]
    only_meas = StubForecaster(arrival=lambda t: t + 3_120_000)
    mon = monitor(
        sched=sched,
        schedule=schedule,
        forecaster=only_meas,
        cal=calibrator(),
        alpha=0.3,
    )
    assert mon.stats().n_tests == 2  # the response instance has no forecast coverage
    only_bp = StubForecaster(bp=160.0, signals=frozenset({"bp"}))
    mon2 = monitor(
        sched=sched, schedule=schedule, forecaster=only_bp, cal=calibrator(), alpha=0.3
    )
    assert mon2.stats().n_tests == 1  # the two SCHED instances have none


def test_n_tests_is_the_largest_number_of_tests_of_one_day() -> None:
    day2 = 86_400_000
    sched = [TICK, hhmm(12), TICK + day2]
    mon = monitor(
        sched=sched,
        forecaster=StubForecaster(arrival=lambda t: t + 3_120_000),
        cal=calibrator(),
        alpha=0.4,
    )
    assert (
        mon.stats().n_tests == 2
    )  # day 0 has two ticks, day 1 one: the union bound is per patient-day
    assert mon.stats().per_test_alpha == pytest.approx(0.2)


# ---------------------------------------------------------------------------------------------
# test 9
# ---------------------------------------------------------------------------------------------


def test_no_forecast_coverage_means_no_predictive_path() -> None:
    forecaster = StubForecaster(arrival=lambda t: t + 3_120_000)  # supports only meas
    mon = monitor(
        schedule=[hhmm(7)], forecaster=forecaster, cal=calibrator(), alpha=0.3
    )
    inputs = Inputs()
    inputs.samples.append(smp("bp", hhmm(6, 50), 150.0))
    inputs.events.append(evt("dispense", hhmm(7), source="dispenser", seq=3))
    inputs.samples.append(smp("auth", hhmm(7), 1.0, seq=3))
    records = run(mon, inputs, hhmm(8))
    assert any(r.template.value == "resp" for r in records)
    assert not [r for r in records if r.state is PREDICTED]
    assert forecaster.calls == []
    stats = mon.stats()
    assert stats.n_tests == 0
    assert dict(stats.prediction_skips) == {"no_forecast_coverage": 1}


def test_a_dispense_beyond_the_plan_has_no_slot_and_says_so() -> None:
    forecaster = StubForecaster(bp=160.0, signals=frozenset({"bp"}))
    mon = monitor(schedule=[], forecaster=forecaster, cal=calibrator(), alpha=0.3)
    inputs = Inputs()
    inputs.samples.append(smp("bp", hhmm(6, 50), 150.0))
    inputs.events.append(evt("dispense", hhmm(7), source="dispenser", seq=3))
    inputs.samples.append(smp("auth", hhmm(7), 1.0, seq=3))
    records = run(mon, inputs, hhmm(8))
    assert not [r for r in records if r.state is PREDICTED]
    assert forecaster.calls == []
    assert dict(mon.stats().prediction_skips) == {"resp_beyond_plan": 1}


# ---------------------------------------------------------------------------------------------
# tests 10 and 11
# ---------------------------------------------------------------------------------------------


def resp_scenario(
    bp_forecast: Any = None,
) -> tuple[Any, SpyCalibrator, StubForecaster, Inputs]:
    tick_meas = hhmm(8, 30)
    dispense = hhmm(7)
    forecaster = StubForecaster(
        arrival=lambda t: t + 120_000,
        bp=bp_forecast
        if bp_forecast is not None
        else (lambda at: 145.0 if at == tick_meas else 80.0),
        signals=frozenset({"meas", "bp"}),
    )
    spy = SpyCalibrator(calibrator())
    mon = monitor(
        sched=[tick_meas],
        schedule=[tick_meas, dispense],
        forecaster=forecaster,
        cal=spy,
        alpha=0.4,
    )
    inputs = Inputs()
    inputs.samples.append(smp("bp", hhmm(6, 50), 150.0))
    inputs.events.append(evt("dispense", dispense, source="dispenser", seq=5))
    inputs.samples.append(smp("auth", dispense, 1.0, seq=5))
    return mon, spy, forecaster, inputs


def test_resp_completes_bp_by_forecast_at_scheduled_ticks() -> None:
    mon, spy, forecaster, inputs = resp_scenario()
    run(mon, inputs, hhmm(7, 5))
    # the plan schedules a measurement at 08:30 inside [07:00 + 1 h, 07:00 + 3 h]; the stub bp at that
    # tick is 145 and 80 elsewhere: sigma_hat = (150 - 145 - 10) / 20 (G-RESP-2: -5 mmHg, -0.25)
    assert spy.sigma_hats == [pytest.approx(-0.25)]
    assert [c.signal for c in forecaster.calls] == ["bp"]


def test_horizon_is_time_to_deadline_extended_by_scale_for_time_templates() -> None:
    mon, _spy, forecaster, inputs = resp_scenario()
    run(mon, inputs, hhmm(8, 31))
    by_signal = {c.signal: c for c in forecaster.calls}
    # resp: the unit is mmHg, the horizon is the time to the deadline (delta2 = 10800000)
    assert by_signal["bp"].horizon_ms == 10_800_000
    assert by_signal["bp"].t_ms == hhmm(7)
    # sched: the time to the deadline (1800000) plus the scale of the template (1800000)
    assert by_signal["meas"].horizon_ms == 1_800_000 + 1_800_000
    assert by_signal["meas"].t_ms == hhmm(8, 30)


# ---------------------------------------------------------------------------------------------
# test 12
# ---------------------------------------------------------------------------------------------


def test_prediction_uses_only_released_history() -> None:
    d_ms = 120_000
    forecaster = StubForecaster(arrival=hhmm(9, 52), signals=frozenset({"meas", "bp"}))
    mon = monitor(sched=[TICK], forecaster=forecaster, cal=calibrator(), d_ms=d_ms)
    inputs = Inputs()
    for t in (hhmm(8, 58), TICK, hhmm(9, 1), hhmm(9, 2)):
        inputs.samples.append(smp("bp", t, 130.0 + (t - TICK) / STEP))
    run(mon, inputs, hhmm(9, 4), d_ms=d_ms)
    assert len(forecaster.calls) == 1
    call = forecaster.calls[0]
    advance_time = (
        call.t_ms + d_ms
    )  # the time of the advance() call that finalised the step
    times = [s.t_device_ms for s in call.history]
    assert times == [hhmm(8, 58), TICK]
    assert all(t <= advance_time - d_ms for t in times)
    # the samples of 09:01 and 09:02 were buffered but not released at the step of the tick
    assert hhmm(9, 1) not in times


def test_history_holds_robot_state_samples_for_the_deadline_forecaster() -> None:
    forecaster = StubForecaster(arrival=hhmm(9, 52))
    mon = monitor(sched=[TICK], forecaster=forecaster, cal=calibrator())
    inputs = Inputs()
    inputs.samples.append(smp("nav_eta_ms", hhmm(8, 59), 240_000.0))
    inputs.samples.append(smp("task_queue_ms", hhmm(8, 59), 600_000.0))
    run(mon, inputs, hhmm(9, 5))
    names = sorted(s.signal for s in forecaster.calls[0].history)
    assert names == ["nav_eta_ms", "task_queue_ms"]


# ---------------------------------------------------------------------------------------------
# test 13
# ---------------------------------------------------------------------------------------------


def test_insufficient_history_means_no_prediction() -> None:
    inputs = Inputs()
    measurement(inputs, hhmm(9, 51))
    stub = StubForecaster(
        arrival=hhmm(9, 52), raises=InsufficientHistoryError("no state")
    )
    mon = monitor(sched=[TICK], forecaster=stub, cal=calibrator())
    plain = monitor(sched=[TICK], predictive=False)
    got = run(mon, inputs, hhmm(10))
    want = run(plain, inputs, hhmm(10))
    assert got == want  # unchanged verdicts
    assert dict(mon.stats().prediction_skips) == {"insufficient_history": 1}
    assert mon.stats().predictions_made == 0


def test_any_other_forecaster_error_propagates() -> None:
    boom = RuntimeError("the model is broken")
    mon = monitor(
        sched=[TICK],
        forecaster=StubForecaster(arrival=hhmm(9, 52), raises=boom),
        cal=calibrator(),
    )
    with pytest.raises(m.MonitorInputError) as info:
        run(mon, Inputs(), hhmm(9, 5))
    assert (
        info.value.__cause__ is boom
    )  # named at the boundary, the original is chained


# ---------------------------------------------------------------------------------------------
# test 14
# ---------------------------------------------------------------------------------------------


def test_stale_calibrator_is_refused() -> None:
    forecaster = StubForecaster(arrival=hhmm(9, 52), version="v2")
    stale = calibrator(version="v1")
    config = make_config(REG, predictive=True, alpha=0.2)
    with pytest.raises(StaleCalibratorError):
        m.StreamingMonitor(config, REG, LIB, calibrator=stale, forecaster=forecaster)
    # after a refit on the new model it is accepted
    fresh = calibrator(version="v2")
    mon = m.StreamingMonitor(config, REG, LIB, calibrator=fresh, forecaster=forecaster)
    mon.load(plan(REG, sched=[TICK]))
    mon.advance(TICK)
    # a forecaster refit that changes its version: the next advance raises
    forecaster.refit("v3")
    with pytest.raises(StaleCalibratorError):
        mon.advance(TICK + STEP)
    # a calibrator calibrated for no particular model is refused (analisi section 2, R2 weakness 6)
    with pytest.raises(StaleCalibratorError):
        m.StreamingMonitor(
            config,
            REG,
            LIB,
            calibrator=calibrator(version=None),
            forecaster=StubForecaster(),
        )


def test_refitting_the_calibrator_on_the_new_model_lifts_the_refusal() -> None:
    forecaster = StubForecaster(arrival=hhmm(9, 52), version="v1")
    cal = calibrator(version="v1")
    mon = monitor(sched=[TICK], forecaster=forecaster, cal=cal)
    mon.advance(TICK - STEP)
    forecaster.refit("v2")
    with pytest.raises(StaleCalibratorError):
        mon.advance(TICK)
    from ralmon.conformal import CalibrationEpisode
    from ralmon.spec import TemplateId

    cal.fit(
        [CalibrationEpisode("c", 0, TemplateId.SCHED, 0.0, r) for r in R_SCORES],
        0.2,
        model_version="v2",
    )
    mon.advance(TICK)  # accepted again; the failed call changed no state


def test_stale_calibrator_error_is_not_a_config_or_input_error() -> None:
    assert issubclass(StaleCalibratorError, Exception)
    assert not hasattr(StaleCalibratorError, "__ralmon_stub_owner__")


# ---------------------------------------------------------------------------------------------
# the measured verdict decides, whatever the forecast said
# ---------------------------------------------------------------------------------------------


def test_predicted_violated_replaces_the_predicted_rho_by_the_measured_one() -> None:
    mon = monitor(sched=[TICK], forecaster=late_arrival_forecaster(), cal=calibrator())
    records = run(mon, Inputs(), hhmm(9, 40))
    key = f"sched@{TICK}"
    assert collapsed(records, key) == [PENDING, PREDICTED, VIOLATED]
    violated = next(r for r in of(records, key) if r.state is VIOLATED)
    assert violated.rho is not None and violated.rho.kind is RhoKind.DETERMINISTIC
    assert violated.guard_failed == "no_measurement_after_tick"


def test_predictive_mode_does_not_mention_ground_truth() -> None:
    from pathlib import Path

    text = (Path(m.__file__).parent / "predictive.py").read_text(encoding="utf-8")
    for name in ("LatentDay", "GroundTruthEvent", "BenchmarkDay"):
        assert name not in text


# ---------------------------------------------------------------------------------------------
# robustness of the step (added after the implementation: the cases the hypothesis test does not pin)
# ---------------------------------------------------------------------------------------------


def test_a_path_that_is_not_the_one_asked_for_is_skipped_and_counted() -> None:
    for raw in (
        lambda signal, t, h, n: [0.0] * (n + 3),  # wrong length
        lambda signal, t, h, n: [math.nan] * n,  # not finite
        lambda signal, t, h, n: [math.inf] + [0.0] * (n - 1),
    ):
        mon = monitor(
            sched=[TICK], forecaster=StubForecaster(raw=raw), cal=calibrator()
        )
        records = run(mon, Inputs(), hhmm(9, 5))
        assert not [r for r in records if r.state is PREDICTED]
        assert dict(mon.stats().prediction_skips) == {"invalid_forecast": 1}


def test_a_forecaster_that_answers_another_signal_is_skipped() -> None:
    from ralmon.monitor import Forecast

    class Wrong(StubForecaster):
        def predict(
            self, history: Any, t_ms: int, horizon_ms: int, *, signal: Any = None
        ) -> Any:
            return Forecast("bp", t_ms, horizon_ms, [0.0] * (horizon_ms // STEP))

    mon = monitor(sched=[TICK], forecaster=Wrong(), cal=calibrator())
    run(mon, Inputs(), hhmm(9, 5))
    assert dict(mon.stats().prediction_skips) == {"invalid_forecast": 1}


def test_a_forecaster_without_the_signal_keyword_is_called_with_the_contract_arguments() -> (
    None
):
    class Plain:
        name = "plain"
        model_version = "v1"
        supported_signals = frozenset({"meas"})

        def __init__(self) -> None:
            self.calls: list[tuple[int, int]] = []

        def fit(self, train_days: Any) -> None: ...

        def predict(self, history: Any, t_ms: int, horizon_ms: int) -> Any:
            self.calls.append((t_ms, horizon_ms))
            mean = [0.0] * (horizon_ms // STEP)
            mean[51] = 1.0  # 09:52
            return m.Forecast("meas", t_ms, horizon_ms, mean)

    forecaster = Plain()
    mon = monitor(sched=[TICK], forecaster=forecaster, cal=calibrator())
    records = run(mon, Inputs(), hhmm(9, 5))
    assert forecaster.calls == [(TICK, 3_600_000)]
    assert [r for r in records if r.state is PREDICTED]


def test_an_open_pre_dose_pressure_gives_no_completed_value() -> None:
    forecaster = StubForecaster(bp=145.0, signals=frozenset({"bp"}))
    mon = monitor(
        sched=[hhmm(8, 30)],
        schedule=[hhmm(8, 30), hhmm(7)],
        forecaster=forecaster,
        cal=calibrator(),
    )
    inputs = Inputs()  # no pressure before the dose: bp_pre is undefined (stale-open)
    inputs.events.append(evt("dispense", hhmm(7), source="dispenser", seq=5))
    inputs.samples.append(smp("auth", hhmm(7), 1.0, seq=5))
    records = run(mon, inputs, hhmm(7, 5))
    assert not [r for r in records if r.state is PREDICTED]
    assert dict(mon.stats().prediction_skips) == {"undefined_completion": 1}


def test_a_new_version_of_the_plan_recomputes_the_tests_and_keeps_the_slots_used() -> (
    None
):
    forecaster = StubForecaster(arrival=lambda t: t + 3_120_000)
    mon = monitor(sched=[TICK], forecaster=forecaster, cal=calibrator(), alpha=0.4)
    assert mon.stats().n_tests == 1
    import dataclasses

    bigger = dataclasses.replace(plan(REG, sched=[TICK, hhmm(12)]), plan_version=2)
    mon.load(bigger)
    assert mon.stats().n_tests == 2
    assert mon.stats().per_test_alpha == pytest.approx(0.2)


def test_the_recording_mode_needs_a_forecaster_and_no_calibrator() -> None:
    mon = m.StreamingMonitor(make_config(REG), REG, LIB)
    with pytest.raises(MonitorConfigError):
        mon._enable_recording(lambda point: None)
    mon2 = m.StreamingMonitor(
        make_config(REG), REG, LIB, forecaster=late_arrival_forecaster()
    )
    seen: list[Any] = []
    mon2._enable_recording(seen.append)
    mon2.load(plan(REG, sched=[TICK]))
    run(mon2, Inputs(), hhmm(9, 5))
    assert len(seen) == 1 and seen[0].sigma_hat == pytest.approx(-1_320_000 / 1_800_000)
    with pytest.raises(MonitorConfigError):
        mon2._enable_recording(seen.append)  # after the plan
