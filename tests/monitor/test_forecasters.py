"""Forecaster contract, persistence reference and autoregressive forecaster (WS05-T05).

All series are fixture-only arithmetic, not clinical values. Step ``T_s = 60_000`` ms. Time labels
convert with ``t_ms = (60 * hh + mm) * 60000``. The names under test are read from
``ralmon.monitor`` at call time, so that the file can be collected before the implementation exists.
"""

from __future__ import annotations

import hashlib
import inspect
import math
import re
import time
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import ralmon.monitor as m
from ralmon.signals import Event, EventKind, Sample

from .helpers import LocalDay, hhmm, smp

STEP = 60_000  # FIXTURE-ONLY


def mins(hh: int, mm: int = 0) -> int:
    return hhmm(hh, mm)


def dense_day(signal: str, values: list[float], t0: int = 0) -> LocalDay:
    """One sample of ``signal`` on every grid step from ``t0`` (FIXTURE-ONLY)."""
    return LocalDay(
        samples=[smp(signal, t0 + k * STEP, v) for k, v in enumerate(values)],
        events=[],
    )


def varied_day(signal: str = "hr_ecg", n: int = 40) -> LocalDay:
    """A non-degenerate dense series (FIXTURE-ONLY arithmetic: 60 + (7k mod 11))."""
    return dense_day(signal, [60.0 + float((7 * k) % 11) for k in range(n)])


def line_day() -> LocalDay:
    """x[k+1] = 0.5 * x[k] + 10 from x[0] = 40, ten values (FIXTURE-ONLY)."""
    values = [40.0]
    for _ in range(9):
        values.append(0.5 * values[-1] + 10.0)
    return dense_day("hr_ecg", values)


def make_ar(order: int = 1) -> Any:
    return m.AutoRegressiveForecaster(STEP, order)


# -- contract of Forecast and of the protocol ------------------------------------------------------


def test_forecast_index_convention_and_length() -> None:
    f = m.PersistenceForecaster(STEP)
    history = [smp("hr_ecg", mins(8), 70.0)]
    t = mins(9)
    assert t == 32_400_000
    out = f.predict(history, t, 300_000)
    assert out.t_from_ms == 32_400_000
    assert out.horizon_ms == 300_000
    assert len(out.mean) == 5
    assert len(f.predict(history, t, 330_000).mean) == 5  # floor
    assert len(f.predict(history, t, 0).mean) == 0
    doc = m.Forecast.__doc__ or ""
    assert "t_from_ms + (k + 1) * step_ms" in doc
    assert "mean[k]" in doc


def test_the_protocol_names_model_version_and_supported_signals() -> None:
    hints = inspect.get_annotations(m.Forecaster)
    assert "name" in hints
    for member in ("model_version", "supported_signals"):
        assert hasattr(m.Forecaster, member), member
    for cls, args in (
        (m.PersistenceForecaster, (STEP,)),
        (m.AutoRegressiveForecaster, (STEP, 1)),
        (m.DeadlineForecaster, (STEP,)),
    ):
        obj = cls(*args)
        assert isinstance(obj.name, str) and obj.name
        assert isinstance(obj.model_version, str)
        assert isinstance(obj.supported_signals, frozenset)
        assert obj.supported_signals
        assert callable(obj.fit) and callable(obj.predict)


def test_named_errors_are_distinct_exceptions() -> None:
    for name in (
        "ForecasterNotFittedError",
        "InsufficientHistoryError",
        "UnsupportedSignalError",
    ):
        assert issubclass(getattr(m, name), Exception)
        assert name in m.__all__
    assert not issubclass(m.InsufficientHistoryError, m.ForecasterNotFittedError)


def test_persistence_repeats_last_value() -> None:
    f = m.PersistenceForecaster(STEP)
    history = [smp("hr_ecg", mins(8), 70.0), smp("hr_ecg", mins(8, 58), 72.0)]
    out = f.predict(history, mins(9), 180_000)
    assert out.signal == "hr_ecg"
    assert list(out.mean) == [72.0, 72.0, 72.0]


def test_persistence_takes_the_latest_by_device_time_whatever_the_order() -> None:
    f = m.PersistenceForecaster(STEP)
    history = [smp("spo2", mins(8, 58), 96.0), smp("spo2", mins(8), 99.0)]
    assert list(f.predict(history, mins(9), 120_000).mean) == [96.0, 96.0]


def test_persistence_with_an_explicit_signal_among_several() -> None:
    f = m.PersistenceForecaster(STEP)
    history = [smp("spo2", mins(8), 97.0), smp("hr_ecg", mins(8, 30), 70.0)]
    assert list(f.predict(history, mins(9), 60_000, signal="spo2").mean) == [97.0]
    with pytest.raises(ValueError):
        f.predict(history, mins(9), 60_000)  # two supported signals, none requested


@settings(max_examples=60, deadline=None)
@given(
    extra=st.lists(
        st.tuples(
            st.sampled_from(["hr_ecg", "hr_pulse", "spo2", "bp", "nav_eta_ms"]),
            st.integers(min_value=1, max_value=10**7),
            st.floats(min_value=0.0, max_value=300.0, allow_nan=False),
        ),
        max_size=12,
    )
)
def test_forecasters_use_only_history_up_to_t(
    extra: list[tuple[str, int, float]],
) -> None:
    t = mins(9)
    base = [smp("hr_ecg", mins(8, 30) + k * STEP, 60.0 + (k % 5)) for k in range(30)]
    base += [smp("nav_eta_ms", mins(9), 600_000.0), smp("task_queue_ms", mins(9), 0.0)]
    future = [smp(s, t + dt, v) for s, dt, v in extra if s != "meas"]
    train = [varied_day("hr_ecg", 60)]
    ar = make_ar(2)
    ar.fit(train)
    deadline = m.DeadlineForecaster(STEP)
    deadline.fit([_deadline_training_day()])
    persistence = m.PersistenceForecaster(STEP)
    only_hr = [s for s in base if s.signal == "hr_ecg"]
    future_hr = [s for s in future if s.signal == "hr_ecg"]
    for forecaster, hist, extra_hist in (
        (persistence, only_hr, future_hr),
        (ar, only_hr, future_hr),
        (deadline, base, future),
    ):
        a = forecaster.predict(hist, t, 600_000)
        b = forecaster.predict(hist + extra_hist, t, 600_000)
        c = forecaster.predict(extra_hist + hist, t, 600_000)
        assert a == b == c


def _deadline_training_day() -> LocalDay:
    return LocalDay(
        samples=[
            smp("nav_eta_ms", mins(9) - STEP, 1_500_000.0),
            smp("task_queue_ms", mins(9) - STEP, 600_000.0),
        ],
        events=[
            Event(EventKind.SCHEDULE_TICK, mins(9), mins(9), "plan", {}, None),
            Event(EventKind.MEASUREMENT, mins(9, 35), mins(9, 35), "cuff", {}, None),
        ],
    )


def test_predict_before_fit_raises() -> None:
    history = [smp("hr_ecg", mins(8), 70.0)]
    with pytest.raises(m.ForecasterNotFittedError):
        make_ar().predict(history, mins(9), 180_000)
    robot = [smp("nav_eta_ms", mins(9), 1.0), smp("task_queue_ms", mins(9), 1.0)]
    with pytest.raises(m.ForecasterNotFittedError):
        m.DeadlineForecaster(STEP).predict(robot, mins(9), 180_000)
    # persistence needs no fit
    assert (
        len(m.PersistenceForecaster(STEP).predict(history, mins(9), 180_000).mean) == 3
    )


def test_insufficient_history_and_unsupported_signal_raise_specific_errors() -> None:
    ar = make_ar(2)
    ar.fit([varied_day("hr_ecg", 40)])
    one = [smp("hr_ecg", mins(8), 70.0)]
    with pytest.raises(m.InsufficientHistoryError):
        ar.predict(one, mins(9), 180_000)
    with pytest.raises(m.InsufficientHistoryError):
        ar.predict([], mins(9), 180_000)
    with pytest.raises(m.InsufficientHistoryError):
        m.PersistenceForecaster(STEP).predict([], mins(9), 180_000)
    # samples only after t do not count
    with pytest.raises(m.InsufficientHistoryError):
        m.PersistenceForecaster(STEP).predict(
            [smp("hr_ecg", mins(9, 1), 70.0)], mins(9), 60_000
        )
    for forecaster in (m.PersistenceForecaster(STEP), ar):
        assert "dispense" not in forecaster.supported_signals
        with pytest.raises(m.UnsupportedSignalError):
            forecaster.predict(one, mins(9), 60_000, signal="dispense")
        with pytest.raises(m.UnsupportedSignalError):
            forecaster.predict([smp("dispense", mins(8), 1.0)], mins(9), 60_000)


def test_fit_is_deterministic_and_seedless() -> None:
    days = [varied_day("hr_ecg", 40), varied_day("spo2", 30)]
    a, b = make_ar(2), make_ar(2)
    a.fit(days)
    b.fit(days)
    for signal in ("hr_ecg", "spo2"):
        assert a.intercept(signal) == b.intercept(signal)
        assert a.coefficients(signal) == b.coefficients(signal)
    assert a.model_version == b.model_version
    forbidden = re.compile(r"rng|seed|random|generator", re.IGNORECASE)
    for cls in (
        m.PersistenceForecaster,
        m.AutoRegressiveForecaster,
        m.DeadlineForecaster,
    ):
        params = inspect.signature(cls.__init__).parameters
        assert not [p for p in params if forbidden.search(p)], cls.__name__
        assert not [
            p for p in inspect.signature(cls.fit).parameters if forbidden.search(p)
        ]


def test_model_version_is_content_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_clock() -> float:
        raise AssertionError("the clock must not be read")

    for clock in ("time", "monotonic", "perf_counter", "time_ns"):
        monkeypatch.setattr(time, clock, no_clock)
    a, b, c = make_ar(1), make_ar(1), make_ar(1)
    a.fit([varied_day("hr_ecg", 40)])
    b.fit([varied_day("hr_ecg", 40)])
    c.fit([dense_day("hr_ecg", [50.0 + float((3 * k) % 7) for k in range(40)])])
    assert re.fullmatch(r"[0-9a-f]{64}", a.model_version)
    assert a.model_version == b.model_version
    assert a.model_version != c.model_version
    a.fit([varied_day("hr_ecg", 40)])  # refitting the same data
    assert a.model_version == b.model_version
    assert a.model_version != make_ar(1).model_version  # unfitted differs from fitted
    assert m.PersistenceForecaster(STEP).model_version == (
        m.PersistenceForecaster(STEP).model_version
    )
    assert m.PersistenceForecaster(STEP).model_version
    # the digest does not depend on object identity: sha256 of text, 64 hex digits
    assert len(hashlib.sha256(b"x").hexdigest()) == len(a.model_version)


# -- autoregressive forecaster -----------------------------------------------------------------


def test_ar1_recovers_noise_free_coefficients() -> None:
    ar = make_ar(1)
    ar.fit([line_day()])
    assert ar.intercept("hr_ecg") == pytest.approx(10.0, abs=1e-9)
    assert list(ar.coefficients("hr_ecg")) == pytest.approx([0.5], abs=1e-9)


def test_ar1_multistep_matches_closed_form() -> None:
    ar = make_ar(1)
    ar.fit([line_day()])
    history = [smp("hr_ecg", mins(9), 40.0)]
    out = ar.predict(history, mins(9), 180_000)
    assert out.signal == "hr_ecg"
    assert out.t_from_ms == mins(9)
    assert list(out.mean) == pytest.approx([30.0, 25.0, 22.5], abs=1e-9)


def test_ar2_uses_two_lags_most_recent_first() -> None:
    # x[k+1] = 0.5 x[k] + 0.25 x[k-1] + 8 on a short series (FIXTURE-ONLY arithmetic)
    values = [10.0, 30.0]
    for _ in range(12):
        values.append(0.5 * values[-1] + 0.25 * values[-2] + 8.0)
    ar = make_ar(2)
    ar.fit([dense_day("hr_ecg", values)])
    assert ar.intercept("hr_ecg") == pytest.approx(8.0, abs=1e-6)
    assert list(ar.coefficients("hr_ecg")) == pytest.approx([0.5, 0.25], abs=1e-6)
    history = [smp("hr_ecg", mins(8, 59), 30.0), smp("hr_ecg", mins(9), 40.0)]
    out = ar.predict(history, mins(9), 120_000)
    first = 0.5 * 40.0 + 0.25 * 30.0 + 8.0
    second = 0.5 * first + 0.25 * 40.0 + 8.0
    assert list(out.mean) == pytest.approx([first, second], abs=1e-6)


def test_order_is_an_explicit_argument() -> None:
    with pytest.raises(TypeError):
        m.AutoRegressiveForecaster()  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        m.AutoRegressiveForecaster(STEP)  # type: ignore[call-arg]
    with pytest.raises(ValueError):
        m.AutoRegressiveForecaster(STEP, 0)
    with pytest.raises(ValueError):
        m.AutoRegressiveForecaster(0, 1)
    with pytest.raises(ValueError):
        m.PersistenceForecaster(-1)
    with pytest.raises(ValueError):
        m.DeadlineForecaster(0)


def test_training_series_is_the_hold_last_grid() -> None:
    from ralmon.monitor.forecasters import _training_series

    day = LocalDay(
        samples=[smp("bp", mins(6), 150.0), smp("bp", mins(9), 140.0)], events=[]
    )
    series = _training_series(day, "bp", STEP, t_end_ms=mins(9, 1))
    assert len(series) == 182
    assert list(series) == [150.0] * 180 + [140.0] * 2
    # without an explicit end the series stops at the grid point of the last sample
    assert list(_training_series(day, "bp", STEP)) == [150.0] * 180 + [140.0]
    assert list(_training_series(day, "spo2", STEP)) == []


def test_training_series_applies_the_ceiling_rule_to_off_grid_samples() -> None:
    from ralmon.monitor.forecasters import _training_series

    day = LocalDay(
        samples=[smp("hr_ecg", 90_000, 5.0), smp("hr_ecg", 150_000, 7.0)], events=[]
    )
    # first grid point at or after 90_000 is 120_000, the sample is visible there;
    # 150_000 becomes visible at 180_000
    assert list(_training_series(day, "hr_ecg", STEP)) == [5.0, 7.0]


def test_bp_path_exists_and_expectation_is_documented() -> None:
    days = [
        LocalDay(
            samples=[
                smp("bp", mins(6), 150.0),
                smp("bp", mins(9), 140.0),
                smp("bp", mins(13), 135.0),
                smp("bp", mins(18), 145.0),
                smp("bp", mins(22), 138.0),
            ],
            events=[],
        )
        for _ in range(3)
    ]
    ar = make_ar(1)
    ar.fit(days)
    out = ar.predict([smp("bp", mins(22), 138.0)], mins(22), 600_000)
    assert out.signal == "bp"
    assert len(out.mean) == 10
    doc = (m.AutoRegressiveForecaster.__doc__ or "").lower()
    assert "uninformative" in doc
    assert "no accuracy claim" in doc
    assert "r2-w5" in doc


def test_ar_fit_with_no_training_row_is_refused_not_defaulted() -> None:
    with pytest.raises(ValueError):
        make_ar(1).fit([])
    ar = make_ar(1)
    ar.fit([varied_day("hr_ecg", 20)])
    with pytest.raises(m.ForecasterNotFittedError):  # no model for spo2
        ar.predict([smp("spo2", mins(8), 97.0)], mins(9), 60_000)


def test_ar_fit_does_not_mix_days_into_one_series() -> None:
    # two days that each hold a constant: pairs across the day boundary would add a jump
    day_a = dense_day("hr_ecg", [10.0] * 6)
    day_b = dense_day("hr_ecg", [90.0] * 6)
    ar = make_ar(1)
    ar.fit([day_a, day_b])
    # (10, 10) and (90, 90) lie on x' = x; a pair across the boundary (10 -> 90) would bend the fit
    assert ar.intercept("hr_ecg") == pytest.approx(0.0, abs=1e-6)
    assert list(ar.coefficients("hr_ecg")) == pytest.approx([1.0], abs=1e-9)
    pairs_per_day = 5
    assert ar.n_training_rows("hr_ecg") == 2 * pairs_per_day


def test_fit_never_reads_latent_or_ground_truth() -> None:
    class Spy:
        patient_id = "p"
        day_index = 0
        seed = 0
        care_plan_id = "c"
        events: tuple[Event, ...] = ()

        def __init__(self) -> None:
            self.samples = [smp("hr_ecg", k * STEP, 60.0 + k % 4) for k in range(20)]

        def __getattr__(self, name: str) -> Any:
            raise AssertionError(f"forbidden attribute {name}")

    ar = make_ar(1)
    ar.fit([Spy()])
    assert ar.model_version


def test_no_anomaly_scoring_in_forecaster_api() -> None:
    forbidden = ("score", "residual", "anomaly")
    for cls in (
        m.PersistenceForecaster,
        m.AutoRegressiveForecaster,
        m.DeadlineForecaster,
    ):
        public = [n for n in dir(cls) if not n.startswith("_")]
        assert public
        assert not [n for n in public if any(f in n.lower() for f in forbidden)], (
            cls.__name__
        )


def test_samples_with_nan_or_infinite_values_are_refused() -> None:
    f = m.PersistenceForecaster(STEP)
    with pytest.raises(ValueError):
        f.predict([Sample("hr_ecg", 0, 0, float("nan"), None, None)], mins(1), 60_000)


def test_a_path_that_overflows_is_refused_not_returned() -> None:
    # x[k+1] = 2 x[k] (FIXTURE-ONLY): from 1e300 the iterated path passes the float range
    ar = make_ar(1)
    ar.fit([dense_day("hr_ecg", [2.0**k for k in range(21)])])
    assert ar.coefficients("hr_ecg")[0] == pytest.approx(2.0, rel=1e-6)
    history = [smp("hr_ecg", mins(9), 1e300)]
    assert all(
        math.isfinite(v) for v in ar.predict(history, mins(9), 120_000).mean
    )  # a short path is fine
    with pytest.raises(ValueError):
        ar.predict(history, mins(9), 100 * STEP)
