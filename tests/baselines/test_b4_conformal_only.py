"""B4, conformal anomaly detection without a specification (WS06-T05).

FIXTURE-ONLY numbers. Every signal value, every quantile and every level below is arithmetic chosen so that the
expected result can be computed by hand in the comment next to it. Heart rates of 60 or 70 and the out-of-band level
of 200 are not clinical values and nothing here is a claim of clinical validation. ``step_ms`` is 60 000 and
``reorder_delay_ms`` is 0 unless a test says otherwise.

Residual definition (the one of WS06-T03, with the index convention of WS05-T05): the residual of a delivered sample
of signal ``s`` at device time ``t`` is ``value - forecast``, where the forecast is issued at the device time
``t_prev`` of the previous delivered sample of ``s`` with horizon ``t - t_prev`` and read from the path at index
``(t - t_prev) // step_ms - 1``. The first sample of a signal has no residual. The persistence stub below repeats the
last value, so the residual of the stub is the difference of two consecutive values.

Hand derivation of the quantile used with the real calibrator (``SplitConformal``): with ``n`` scores and level
``alpha`` the threshold is the ``k``-th smallest score, ``k = ceil((n + 1)(1 - alpha))``, and ``+inf`` if ``k > n``.
Example: ``n = 4``, ``alpha = 0.25``: ``(n + 1)(1 - alpha) = 3.75``, ``k = 4``.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import math
import re
import sys
from collections.abc import Callable, Iterable, Sequence
from fractions import Fraction
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ralmon.attribution import Detection
from ralmon.baselines import B4ConformalOnly, Detector
from ralmon.baselines.access import LeakageError, Split
from ralmon.baselines.base import BaselineBase, NotFittedError, TimingConfig
from ralmon.benchmark import BenchmarkDay, ObservedDay
from ralmon.conformal import (
    BonferroniAllocation,
    CalibrationEpisode,
    SplitConformal,
)
from ralmon.monitor import (
    AutoRegressiveForecaster,
    Forecast,
    InsufficientHistoryError,
    PersistenceForecaster,
    StaleCalibratorError,
)
from ralmon.signals import EventKind, Sample
from ralmon.spec import TemplateId
from tests.baselines.conftest import (
    evidence_mapping,
    make_benchmark_day,
    make_care_plan,
    make_event,
    make_instance,
    make_observed_day,
)

ROOT = Path(__file__).resolve().parents[2]
B4_SOURCE = ROOT / "src" / "ralmon" / "baselines" / "b4_conformal_only.py"

STEP = 60_000
STEPS_PER_DAY = 1440
T_DAY = 86_400_000
TIMING = TimingConfig(STEP, 0, 0)
SUPPORTED = frozenset({"bp", "hr_ecg", "hr_pulse", "spo2"})
ALPHA = 0.2  # FIXTURE-ONLY level, the operating parameter of the tests


def b4_module() -> Any:
    """The module under test, imported at call time so that a missing module fails one test, not the collection."""
    return importlib.import_module("ralmon.baselines.b4_conformal_only")


# ---- doubles ---------------------------------------------------------------------------------------------------------


class StubForecaster:
    """Persistence, as the task prescribes: the forecast is the last value of the requested signal in ``history``."""

    name = "stub-persistence"
    supported_signals = SUPPORTED

    def __init__(self, version: str = "stub-1", step_ms: int = STEP) -> None:
        self.version = version
        self.step_ms = step_ms
        self.fit_calls: list[tuple[Any, ...]] = []
        self.predict_calls: list[tuple[tuple[Sample, ...], int, int, str | None]] = []

    @property
    def model_version(self) -> str:
        return self.version

    def fit(self, train_days: Sequence[Any]) -> None:
        self.fit_calls.append(tuple(train_days))

    def predict(
        self,
        history: Sequence[Sample],
        t_ms: int,
        horizon_ms: int,
        *,
        signal: str | None = None,
    ) -> Forecast:
        self.predict_calls.append((tuple(history), t_ms, horizon_ms, signal))
        mine = [s for s in history if s.signal == signal and s.t_device_ms <= t_ms]
        if not mine:
            raise InsufficientHistoryError("no sample")
        last = max(mine, key=lambda s: s.t_device_ms).value
        assert signal is not None
        return Forecast(
            signal, t_ms, horizon_ms, (last,) * (horizon_ms // self.step_ms)
        )


class RampForecaster(StubForecaster):
    """A path whose entry ``k`` is ``100 + k``: the value read from it tells which index B4 used."""

    def predict(
        self,
        history: Sequence[Sample],
        t_ms: int,
        horizon_ms: int,
        *,
        signal: str | None = None,
    ) -> Forecast:
        self.predict_calls.append((tuple(history), t_ms, horizon_ms, signal))
        assert signal is not None
        return Forecast(
            signal,
            t_ms,
            horizon_ms,
            tuple(100.0 + k for k in range(horizon_ms // self.step_ms)),
        )


class StubCalibrator:
    """A ``ConformalCalibrator`` that returns a preset ``q`` and records every call and every episode."""

    mode = "split"

    def __init__(self, q: float) -> None:
        self.q = q
        self.calibrated_for: str | None = None
        self.fits: list[tuple[tuple[CalibrationEpisode, ...], Any, str | None]] = []
        self.quantile_calls: list[Any] = []
        self.touched: list[str] = []

    def fit(
        self,
        episodes: Sequence[CalibrationEpisode],
        alpha: Any,
        *,
        model_version: str | None = None,
    ) -> None:
        self.fits.append((tuple(episodes), alpha, model_version))
        self.calibrated_for = model_version

    def quantile(self, alpha: Any) -> float:
        self.quantile_calls.append(alpha)
        return self.q

    def __getattr__(
        self, name: str
    ) -> Any:  # only reached for a name the stub does not define
        self.touched.append(name)
        raise AttributeError(name)


class Factory:
    """A calibrator factory that hands out stub calibrators with the given quantiles, in call order."""

    def __init__(self, quantiles: Iterable[float]) -> None:
        self._quantiles = list(quantiles)
        self.made: list[StubCalibrator] = []

    def __call__(self) -> StubCalibrator:
        calibrator = StubCalibrator(self._quantiles[len(self.made)])
        self.made.append(calibrator)
        return calibrator


class StubAllocation:
    """``per_test(a, n) = a / n``, the allocation stub of the task."""

    def __init__(self) -> None:
        self.calls: list[tuple[float, int]] = []

    def per_test(self, alpha_total: float, n_tests: int) -> float:
        self.calls.append((alpha_total, n_tests))
        return alpha_total / n_tests


# ---- builders --------------------------------------------------------------------------------------------------------


def smp(
    signal: str, step: int, value: float, rx_step: int | None = None, day: int = 0
) -> Sample:
    """A sample at grid step ``step`` of day ``day`` (device time on the continuing axis of the patient)."""
    device = (day * STEPS_PER_DAY + step) * STEP
    rx = device if rx_step is None else (day * STEPS_PER_DAY + rx_step) * STEP
    return Sample(signal, device, rx, float(value), None, None)


def series(
    signal: str,
    values: Sequence[float],
    *,
    first: int = 10,
    every: int = 10,
    day: int = 0,
) -> list[Sample]:
    """Samples of one signal at steps ``first``, ``first + every``, ..."""
    return [smp(signal, first + i * every, v, day=day) for i, v in enumerate(values)]


def observed(
    samples: Sequence[Sample],
    *,
    patient: str = "p1",
    day: int = 0,
    events: Sequence[Any] = (),
) -> ObservedDay:
    return make_observed_day(samples, events, patient_id=patient, day_index=day)


def bench(
    values: Sequence[float],
    *,
    signal: str = "hr_ecg",
    patient: str = "c1",
    day: int = 0,
) -> BenchmarkDay:
    samples = series(signal, values, day=day)
    return make_benchmark_day(samples, patient_id=patient, day_index=day)


def hr(values: Sequence[float], *, day: int = 0, patient: str = "p1") -> ObservedDay:
    return observed(series("hr_ecg", values, day=day), patient=patient, day=day)


PLAN = make_care_plan()


def make_b4(
    *,
    forecaster: Any = None,
    factory: Callable[[], Any] | None = None,
    alpha: Any = ALPHA,
    signals: Sequence[str] | None = ("hr_ecg",),
    timing: TimingConfig = TIMING,
    **kwargs: Any,
) -> Any:
    return B4ConformalOnly(
        StubForecaster() if forecaster is None else forecaster,
        Factory([5.0] * 16) if factory is None else factory,
        alpha=alpha,
        signals=signals,
        timing=timing,
        **kwargs,
    )


def fitted(
    quantile: float = 5.0,
    calib: Sequence[BenchmarkDay] | None = None,
    train: Sequence[BenchmarkDay] = (),
    **kwargs: Any,
) -> Any:
    """A B4 on one signal with a stub calibrator of preset quantile ``quantile``, fitted on one calibration day."""
    b4 = make_b4(factory=Factory([quantile]), **kwargs)
    b4.fit(train, [bench([60, 61])] if calib is None else calib)
    return b4


def real_b4(
    calib_values: Sequence[Sequence[float]],
    alpha: float,
    *,
    signals: Sequence[str] = ("hr_ecg",),
    timing: TimingConfig = TIMING,
    **kwargs: Any,
) -> Any:
    """B4 with the real ``SplitConformal``; every calibration day carries each signal with the same values."""
    days = []
    for i, values in enumerate(calib_values):
        samples = [s for sig in signals for s in series(sig, values, day=0)]
        days.append(make_benchmark_day(samples, patient_id=f"c{i}", day_index=0))
    b4 = make_b4(
        factory=SplitConformal, alpha=alpha, signals=signals, timing=timing, **kwargs
    )
    b4.fit([], days)
    return b4


def times(detections: Iterable[Detection]) -> list[int]:
    return [d.t_ms for d in detections]


def at(step: int, day: int = 0) -> int:
    return (day * STEPS_PER_DAY + step) * STEP


# ---- the 16 tests of the task ----------------------------------------------------------------------------------------


def test_b4_interval_alarm_hand_computed() -> None:
    # q = 5. Samples at steps 10, 20, 30, 40 with values 60, 62, 70, 50: residuals 62-60 = 2, 70-62 = 8, 50-70 = -20.
    # Magnitudes 2, 8, 20: 2 <= 5 no alarm; 8 > 5 alarm at the delivery step of the 70 sample (step 30), score
    # 8 / 5 = 1.6; 20 > 5 alarm at step 40, score 20 / 5 = 4.0.
    b4 = fitted(5.0)
    out = b4.run(hr([60, 62, 70, 50]), PLAN, None)
    assert times(out) == [at(30), at(40)]
    assert [d.score for d in out] == pytest.approx([1.6, 4.0])
    assert all(d.label is None for d in out)


def test_b4_boundary_is_inside_interval() -> None:
    # |65 - 60| = 5.0 = q: the interval is closed, no detection. 5.5 is outside; so is -5.5.
    b4 = fitted(5.0)
    assert b4.run(hr([60, 65]), PLAN, None) == ()
    assert b4.run(hr([60, 55]), PLAN, None) == ()
    assert times(b4.run(hr([60, 65.5]), PLAN, None)) == [at(20)]
    assert times(b4.run(hr([60, 54.5]), PLAN, None)) == [at(20)]


def test_b4_first_sample_has_no_forecast() -> None:
    # a single sample has no previous sample to issue a forecast at: no residual, whatever the threshold
    b4 = fitted(0.0)
    assert b4.run(hr([500]), PLAN, None) == ()
    assert b4.run(observed([]), PLAN, None) == ()


def test_b4_day_max_episodes_hand_computed() -> None:
    # day 1 of patient a: 60, 62, 70 -> residual magnitudes 2, 8 -> one episode with sigma_true 8.0.
    # day 2 (day_index 1) of patient b: 60, 61, 61 -> magnitudes 1, 0 -> one episode with sigma_true 1.0.
    forecaster = StubForecaster("stub-7")
    factory = Factory([5.0])
    b4 = make_b4(
        forecaster=forecaster, factory=factory
    )  # unit="day_max" is the default
    b4.fit(
        [],
        [
            bench([60, 62, 70], patient="a", day=0),
            bench([60, 61, 61], patient="b", day=1),
        ],
    )
    (calibrator,) = factory.made
    ((episodes, alpha, version),) = calibrator.fits
    assert [(e.patient_id, e.day_index) for e in episodes] == [("a", 0), ("b", 1)]
    assert [e.sigma_hat for e in episodes] == [0.0, 0.0]
    assert [e.sigma_true for e in episodes] == [8.0, 1.0]
    assert alpha == ALPHA
    assert version == "stub-7"  # calibrated_for must equal the forecaster model_version
    assert calibrator.calibrated_for == "stub-7"


def test_b4_sample_unit_episodes_hand_computed() -> None:
    # unit="sample" is the classical time-step conformal anomaly detection (it does not follow rule 1 of the
    # contract); the same two days give one episode per residual, in time order: 2, 8, 1, 0.
    factory = Factory([5.0])
    b4 = make_b4(factory=factory, unit="sample")
    b4.fit(
        [],
        [
            bench([60, 62, 70], patient="a", day=0),
            bench([60, 61, 61], patient="b", day=1),
        ],
    )
    ((episodes, _, _),) = factory.made[0].fits
    assert [e.sigma_true for e in episodes] == [2.0, 8.0, 1.0, 0.0]
    assert [(e.patient_id, e.day_index) for e in episodes] == [
        ("a", 0),
        ("a", 0),
        ("b", 1),
        ("b", 1),
    ]
    assert [e.sigma_hat for e in episodes] == [0.0] * 4
    assert "classical" in (b4_module().__doc__ or "") + (B4ConformalOnly.__doc__ or "")


def test_b4_alpha_allocation_hand_computed() -> None:
    # four monitored signals, alpha = 0.2, per_test(a, n) = a / n: every calibrator is fitted with 0.2 / 4 = 0.05
    signals = ("bp", "hr_ecg", "hr_pulse", "spo2")
    samples = [s for sig in signals for s in series(sig, [60, 61])]
    day = make_benchmark_day(samples, patient_id="c1")
    allocation = StubAllocation()
    factory = Factory([1.0] * 4)
    b4 = make_b4(factory=factory, signals=signals, allocation=allocation)
    b4.fit([], [day])
    assert len(factory.made) == 4
    assert all(c.fits[0][1] == 0.05 for c in factory.made)
    assert allocation.calls == [(ALPHA, 4)]
    b4.run(observed(samples), PLAN, None)
    assert all(
        c.quantile_calls and set(c.quantile_calls) == {0.05} for c in factory.made
    )
    # without an allocation each calibrator gets the level itself
    factory2 = Factory([1.0] * 4)
    plain = make_b4(factory=factory2, signals=signals)
    plain.fit([], [day])
    assert all(c.fits[0][1] == ALPHA for c in factory2.made)


def test_b4_one_calibrator_per_signal() -> None:
    # the factory is called once per monitored signal, in the order of ``signals`` (units are never pooled);
    # q = 5 for hr_ecg and q = 1 for spo2: a change of 3 alarms on spo2 only
    samples = series("hr_ecg", [60, 61]) + series("spo2", [95, 96])
    day = make_benchmark_day(samples, patient_id="c1")
    factory = Factory([5.0, 1.0])
    b4 = make_b4(factory=factory, signals=("hr_ecg", "spo2"))
    b4.fit([], [day])
    assert len(factory.made) == 2
    ecg = series("hr_ecg", [60, 63]) + series("spo2", [95, 98])
    out = b4.run(observed(ecg), PLAN, None)
    assert times(out) == [at(20)]
    assert out[0].score == pytest.approx(3.0)  # the spo2 sample: 3 / 1
    # each calibrator was fitted with the episodes of its own signal only
    assert [e.sigma_true for e in factory.made[0].fits[0][0]] == [1.0]
    assert [e.sigma_true for e in factory.made[1].fits[0][0]] == [1.0]
    assert factory.made[0].quantile_calls and factory.made[1].quantile_calls


def test_b4_uses_only_public_calibrator_api() -> None:
    # B4 touches ``fit`` and ``quantile`` and the protocol attribute ``calibrated_for``, nothing else
    factory = Factory([5.0])
    b4 = make_b4(factory=factory)
    b4.fit([], [bench([60, 62, 70])])
    b4.run(hr([60, 70]), PLAN, None)
    (calibrator,) = factory.made
    assert calibrator.touched == []
    assert len(calibrator.fits) == 1
    assert calibrator.quantile_calls  # the quantile was asked for


def test_b4_placeholder_template_does_not_change_quantile() -> None:
    # SplitConformal pools the episodes whatever their template: the placeholder carries no meaning
    module = b4_module()
    assert isinstance(module.PLACEHOLDER_TEMPLATE, TemplateId)
    magnitudes = [1.0, 2.0, 3.0, 4.0]
    by_template = {}
    for template in TemplateId:
        calibrator = SplitConformal()
        calibrator.fit(
            [
                CalibrationEpisode(f"p{i}", 0, template, 0.0, m)
                for i, m in enumerate(magnitudes)
            ],
            0.25,
        )
        by_template[template] = calibrator.quantile(0.25)
    assert set(by_template.values()) == {4.0}


def test_b4_real_split_conformal_matches_definition() -> None:
    # four calibration days with residual magnitudes 1, 2, 3, 4 and alpha = 0.25: k = ceil(5 * 0.75) = 4, the
    # 4th smallest magnitude, q = 4.0. A residual of 4.5 alarms (score 4.5 / 4 = 1.125) and 4.0 does not.
    days = [[60, 61], [60, 62], [60, 63], [60, 64]]
    b4 = real_b4(days, 0.25)
    out = b4.run(hr([60, 64.5]), PLAN, None)
    assert times(out) == [at(20)]
    assert out[0].score == pytest.approx(1.125)
    assert b4.run(hr([60, 64.0]), PLAN, None) == ()
    # alpha = 0.5: k = ceil(5 * 0.5) = 3, q = 3.0; 3.5 alarms, 3.0 does not
    half = real_b4(days, 0.5)
    assert times(half.run(hr([60, 63.5]), PLAN, None)) == [at(20)]
    assert half.run(hr([60, 63.0]), PLAN, None) == ()
    # alpha = 0.1 < 1 / (n + 1): k = ceil(5 * 0.9) = 5 > 4, the quantile is +inf, nothing is ever emitted
    tiny = real_b4(days, 0.1)
    assert tiny.run(hr([60, 1000]), PLAN, None) == ()


@settings(max_examples=60, deadline=None)
@given(
    calib=st.lists(
        st.lists(st.integers(40, 160), min_size=2, max_size=6), min_size=1, max_size=8
    ),
    test=st.lists(st.integers(40, 160), min_size=2, max_size=10),
    alphas=st.lists(
        st.sampled_from([0.05, 0.1, 0.2, 0.25, 0.3, 0.5, 0.7]),
        min_size=2,
        max_size=2,
        unique=True,
    ),
    unit=st.sampled_from(["day_max", "sample"]),
)
def test_b4_smaller_alpha_gives_subset_property(
    calib: list[list[int]], test: list[int], alphas: list[float], unit: str
) -> None:
    low, high = sorted(alphas)
    day = hr([float(v) for v in test])
    found = {}
    for alpha in (low, high):
        b4 = real_b4([[float(v) for v in d] for d in calib], alpha, unit=unit)
        found[alpha] = set(times(b4.run(day, PLAN, None)))
    assert found[low] <= found[high]  # wider interval, fewer alarms


def test_b4_invariant_to_plan_parameters() -> None:
    # B4 has no clinical specification and no schedule: no entry of the plan can change its output
    b4 = fitted(5.0)
    day = hr([60, 70, 50, 52])
    plan_a = make_care_plan(
        [
            make_instance(
                TemplateId.RANGE, "r", {"bp_band_low": 110.0, "bp_band_high": 140.0}
            ),
            make_instance(TemplateId.HOLD, "h", {"bp_hold_threshold": 100.0}),
            make_instance(TemplateId.COUNT, "c", {"dose_max_24h": 2.0}),
            make_instance(
                TemplateId.SCHED, "s", {"sched_window": 1_800_000.0}, 3_600_000
            ),
        ],
        schedule=[3_600_000, 7_200_000],
    )
    plan_b = make_care_plan(
        [
            make_instance(
                TemplateId.RANGE, "r", {"bp_band_low": 10.0, "bp_band_high": 20.0}
            ),
            make_instance(TemplateId.HOLD, "h", {"bp_hold_threshold": 5.0}),
            make_instance(TemplateId.COUNT, "c", {"dose_max_24h": 99.0}),
            make_instance(TemplateId.SCHED, "s", {"sched_window": 60_000.0}, 60_000),
        ],
        schedule=[],
    )
    base = b4.run(day, PLAN, None)
    assert base  # a non-trivial output
    assert b4.run(day, plan_a, None) == base
    assert b4.run(day, plan_b, None) == base
    assert b4.read_log.registry_reads == frozenset()
    assert b4.read_log.param_reads == {}
    assert b4.read_log.all_names() == frozenset()


def test_b4_does_not_depend_on_the_tail_of_the_timing() -> None:
    # the run ends at the last step that delivers an input; neither plan.schedule nor tail_ms moves a detection
    day = hr([60, 70])
    short = fitted(5.0, timing=TimingConfig(STEP, 0, 0))
    long = fitted(5.0, timing=TimingConfig(STEP, 0, 6 * 3_600_000))
    assert short.run(day, PLAN, None) == long.run(day, PLAN, None)
    assert times(short.run(day, PLAN, None)) == [at(20)]


def test_b4_calibration_reads_observed_only() -> None:
    # the default AccessPolicy: observed reads of both splits; no ground truth, no latent trace, nothing denied
    train = [bench([60, 61, 62], patient="t1"), bench([61, 62], patient="t2")]
    calib = [bench([60, 61], patient="c1"), bench([60, 62], patient="c2")]
    b4 = fitted(5.0, calib=calib, train=train)
    log = b4.access_log
    assert log.fields() == frozenset({"observed"})
    assert log.fields(Split.CALIB) == frozenset({"observed"})
    assert log.denied == ()
    b4.run(hr([60, 70]), PLAN, None)
    assert log.fields() == frozenset({"observed"}) and log.denied == ()


def test_b4_ignores_evidence_and_never_labels() -> None:
    b4 = fitted(5.0)
    day = hr([60, 70, 50])
    without = b4.run(day, PLAN, None)
    with_evidence = b4.run(day, PLAN, evidence_mapping())
    assert without == with_evidence and len(without) == 2
    assert all(d.label is None and math.isfinite(d.score) for d in with_evidence)


@settings(max_examples=60, deadline=None)
@given(
    steps=st.lists(st.integers(0, 120), min_size=2, max_size=12, unique=True),
    values=st.lists(st.integers(40, 160), min_size=12, max_size=12),
    delays=st.lists(st.integers(0, 3), min_size=12, max_size=12),
    reorder=st.sampled_from([0, 2]),
    cut=st.integers(0, 130),
)
def test_b4_is_causal_property(
    steps: list[int], values: list[int], delays: list[int], reorder: int, cut: int
) -> None:
    timing = TimingConfig(STEP, reorder * STEP, 0)
    b4 = real_b4([[60, 62, 70], [60, 61], [60, 66, 62]], 0.3, timing=timing)
    samples = [
        smp("hr_ecg", s, values[i], rx_step=s + delays[i])
        for i, s in enumerate(sorted(steps))
    ]
    horizon = cut * STEP
    full = b4.run(observed(samples), PLAN, None)
    truncated = b4.run(
        observed([s for s in samples if s.t_rx_ms <= horizon]), PLAN, None
    )
    assert [d for d in full if d.t_ms <= horizon] == [
        d for d in truncated if d.t_ms <= horizon
    ]


def test_b4_deterministic() -> None:
    day = hr([60, 70, 50, 55, 90])
    calib = [bench([60, 62, 70], patient="a"), bench([60, 61, 61], patient="b")]
    first = real_b4([[60, 62, 70], [60, 61, 61]], 0.3)
    second = real_b4([[60, 62, 70], [60, 61, 61]], 0.3)
    assert (
        first.run(day, PLAN, None)
        == second.run(day, PLAN, None)
        == first.run(day, PLAN, None)
    )
    b4 = make_b4(factory=SplitConformal, alpha=0.3)
    b4.fit([], calib)
    again = make_b4(factory=SplitConformal, alpha=0.3)
    again.fit([], calib)
    assert b4.run(day, PLAN, None) == again.run(day, PLAN, None)


# ---- the residual: index, horizon, causality, stream anomalies -------------------------------------------------------


def test_b4_residual_reads_the_path_at_the_documented_index() -> None:
    # samples at steps 10 and 13: gap 3 steps, horizon 180 000, path of 3 entries 100, 101, 102 for the grid times
    # t_prev + 1, 2, 3 steps. The sample at t_prev + 3 steps is predicted by entry (t - t_from) // step - 1 = 2, that
    # is 102: the residual of the value 110 is 8 (and not 10 or 9, which the other indices would give).
    forecaster = RampForecaster()
    b4 = make_b4(forecaster=forecaster, factory=Factory([7.0]))
    b4.fit([], [bench([60, 61])])
    forecaster.predict_calls.clear()
    day = observed([smp("hr_ecg", 10, 100.0), smp("hr_ecg", 13, 110.0)])
    out = b4.run(day, PLAN, None)
    assert [(c[1], c[2], c[3]) for c in forecaster.predict_calls] == [
        (at(10), 3 * STEP, "hr_ecg")
    ]
    assert times(out) == [at(13)]
    assert out[0].score == pytest.approx(8.0 / 7.0)
    residuals = b4.residuals
    assert [r.residual for r in residuals] == [8.0] and [
        r.forecast for r in residuals
    ] == [102.0]


def test_b4_forecaster_gets_the_signal_keyword_and_only_delivered_samples() -> None:
    forecaster = StubForecaster()
    b4 = make_b4(forecaster=forecaster, factory=Factory([5.0]))
    b4.fit([], [bench([60, 61])])
    forecaster.predict_calls.clear()
    samples = [smp("hr_ecg", 10, 60), smp("hr_ecg", 20, 62), smp("hr_ecg", 30, 70)]
    b4.run(observed(samples), PLAN, None)
    assert [c[3] for c in forecaster.predict_calls] == ["hr_ecg", "hr_ecg"]
    for history, t_prev, _, _ in forecaster.predict_calls:
        assert all(
            s.t_device_ms <= t_prev for s in history
        )  # nothing from the future of the issue time
    assert [len(c[0]) for c in forecaster.predict_calls] == [1, 2]


def test_b4_forecaster_is_fitted_on_observed_train_days_only() -> None:
    forecaster = StubForecaster()
    train = [bench([60, 200], patient="t1")]
    calib = [bench([60, 61], patient="c1")]
    b4 = make_b4(forecaster=forecaster, factory=Factory([5.0]))
    b4.fit(train, calib)
    (call,) = forecaster.fit_calls
    assert len(call) == 1 and all(isinstance(d, ObservedDay) for d in call)
    assert call[0].patient_id == "t1"


def test_b4_calibration_uses_calibration_days_only() -> None:
    # a train day with a residual of 140 must not enter the episodes
    factory = Factory([5.0])
    b4 = make_b4(factory=factory)
    b4.fit([bench([60, 200], patient="t1")], [bench([60, 62], patient="c1")])
    assert [e.sigma_true for e in factory.made[0].fits[0][0]] == [2.0]


def test_b4_sub_step_gap_and_insufficient_history_give_no_residual() -> None:
    # two samples 30 s apart: the path of horizon 30 s is empty, there is no forecast to compare with
    b4 = fitted(0.0)
    close = Sample("hr_ecg", 10 * STEP, 10 * STEP, 60.0, None, None)
    closer = Sample("hr_ecg", 10 * STEP + 30_000, 10 * STEP + 30_000, 500.0, None, None)
    assert b4.run(observed([close, closer]), PLAN, None) == ()
    assert b4.run_stats.no_forecast == 1

    # a forecaster that cannot define the forecast (history too short) skips the residual and counts it
    class Short(StubForecaster):
        armed = False

        def predict(
            self,
            history: Sequence[Sample],
            t_ms: int,
            horizon_ms: int,
            *,
            signal: str | None = None,
        ) -> Forecast:
            if self.armed:
                raise InsufficientHistoryError("too short")
            return super().predict(history, t_ms, horizon_ms, signal=signal)

    short = Short()
    skipping = fitted(0.0, forecaster=short)
    short.armed = True
    assert skipping.run(hr([60, 500]), PLAN, None) == ()
    assert skipping.run_stats.no_forecast == 1


def test_b4_a_late_input_is_dropped_like_the_monitor_does() -> None:
    # step 20 sample stamped at step 20 but received at step 22 is final-late: dropped and counted, never used as
    # the previous sample; the 62 -> 70 pair is then 60 -> 70 with the gap of 2 steps
    b4 = fitted(5.0)
    samples = [
        smp("hr_ecg", 10, 60),
        smp("hr_ecg", 20, 200, rx_step=22),
        smp("hr_ecg", 30, 70),
    ]
    out = b4.run(observed(samples), PLAN, None)
    assert times(out) == [at(30)]  # |70 - 60| = 10 > 5
    assert b4.run_stats.late_inputs == 1
    # received one step after the step where it is final (stamped 20, received 21): late, the exact boundary
    just_late = [smp("hr_ecg", 10, 60), smp("hr_ecg", 20, 200, rx_step=21)]
    assert b4.run(observed(just_late), PLAN, None) == ()
    assert b4.run_stats.late_inputs == 1
    # received exactly at the step where it is final: delivered, not late
    on_time = [smp("hr_ecg", 10, 60), smp("hr_ecg", 20, 200, rx_step=20)]
    assert times(b4.run(observed(on_time), PLAN, None)) == [at(20)]
    assert b4.run_stats.late_inputs == 0


def test_b4_lateness_rule_includes_the_reorder_delay() -> None:
    # reorder delay of 2 steps: a sample stamped at step 20 is final at step 22 (watermark 20 + 2). Received at 22 it is
    # delivered; received at 23 it is late (the rule of the monitor, ceil(t_dev / T_s) * T_s + D).
    timing = TimingConfig(STEP, 2 * STEP, 0)
    b4 = fitted(5.0, timing=timing)
    on_time = [smp("hr_ecg", 10, 60), smp("hr_ecg", 20, 90, rx_step=22)]
    assert times(b4.run(observed(on_time), PLAN, None)) == [at(22)]
    assert b4.run_stats.late_inputs == 0
    late = [smp("hr_ecg", 10, 60), smp("hr_ecg", 20, 90, rx_step=23)]
    assert b4.run(observed(late), PLAN, None) == ()
    assert b4.run_stats.late_inputs == 1


def test_b4_does_not_deduplicate_inputs_but_a_duplicate_has_no_residual() -> None:
    # the harness does not deduplicate (asymmetry (b) of base.py). A sample delivered twice is delivered twice, but the
    # second copy has gap 0 to its predecessor and so no residual: no second alarm (B1 would raise one).
    b4 = fitted(5.0)
    spike = smp("hr_ecg", 20, 90)
    samples = [smp("hr_ecg", 10, 60), spike, spike]
    out = b4.run(observed(samples), PLAN, None)
    assert times(out) == [at(20)]
    assert b4.run_stats.not_newer == 1


def test_b4_non_finite_sample_is_not_a_reading() -> None:
    b4 = fitted(5.0)
    samples = [
        smp("hr_ecg", 10, 60),
        smp("hr_ecg", 20, math.nan),
        smp("hr_ecg", 30, 61),
    ]
    assert b4.run(observed(samples), PLAN, None) == ()
    assert b4.run_stats.non_finite_samples == 1
    assert [r.residual for r in b4.residuals] == [1.0]


def test_b4_input_before_the_day_is_a_delivered_value_but_raises_no_alarm() -> None:
    # day 1 starts at t0 = 1440 steps. A device time in (t0 - step, t0] is step 0 of the day (as in the monitor and in
    # B1); one a whole step or more before it is not part of the day: it can be the previous sample of the next one,
    # but it raises no detection and no calibration residual.
    b4 = fitted(5.0)
    t0 = T_DAY
    first = Sample("hr_ecg", t0 - 3 * STEP, t0, 60.0, None, None)
    later = Sample("hr_ecg", 5 * STEP + t0, 5 * STEP + t0, 60.0, None, None)
    # within a step before the day: in the day, residual 90 - 60 = 30 > 5, detected at the first step; then -30 at step 5
    inside = Sample("hr_ecg", t0 - STEP + 1, t0, 90.0, None, None)
    assert times(b4.run(observed([first, inside, later], day=1), PLAN, None)) == [
        at(0, 1),
        at(5, 1),
    ]
    # a whole step before the day: not part of it, no alarm for it; the sample of step 5 still alarms
    outside = Sample("hr_ecg", t0 - STEP, t0, 90.0, None, None)
    assert times(b4.run(observed([first, outside, later], day=1), PLAN, None)) == [
        at(5, 1)
    ]
    assert len(b4.residuals) == 1


def test_b4_detection_after_midnight_is_not_clipped() -> None:
    # reorder delay of 2 steps: the sample stamped at step 1439 of day 0 is delivered at step 1441, in the next day;
    # the detection time is the delivery step (t_eval + D), not clipped at the closing step of the day
    timing = TimingConfig(STEP, 2 * STEP, 0)
    b4 = fitted(5.0, timing=timing)
    samples = [smp("hr_ecg", 1400, 60), smp("hr_ecg", 1439, 90)]
    out = b4.run(observed(samples), PLAN, None)
    assert times(out) == [at(1441)]
    assert out[0].t_ms > T_DAY


def test_b4_score_is_finite_when_the_quantile_is_zero_and_zero_when_it_is_infinite() -> (
    None
):
    # all calibration residuals zero: q = 0, any change alarms and the ratio is infinite; the harness refuses an
    # infinite score, so it is the largest finite float (the rule of B5)
    zero = fitted(0.0)
    (alarm,) = zero.run(hr([60, 61]), PLAN, None)
    assert alarm.score == sys.float_info.max
    # q = +inf (level below 1 / (n + 1)): never an alarm
    wide = fitted(math.inf)
    assert wide.run(hr([60, 1e9]), PLAN, None) == ()
    # a negative or NaN quantile is a bug of the calibrator and is refused
    for bad in (-1.0, math.nan):
        broken = fitted(bad)
        with pytest.raises(ValueError, match="quantile"):
            broken.run(hr([60, 70]), PLAN, None)


def test_b4_malformed_forecast_is_refused() -> None:
    class Wrong(StubForecaster):
        armed = False

        def predict(
            self,
            history: Sequence[Sample],
            t_ms: int,
            horizon_ms: int,
            *,
            signal: str | None = None,
        ) -> Forecast:
            if not self.armed:
                return super().predict(history, t_ms, horizon_ms, signal=signal)
            return Forecast("spo2", t_ms, horizon_ms, (1.0,) * (horizon_ms // STEP))

    wrong = Wrong()
    b4 = fitted(5.0, forecaster=wrong)
    wrong.armed = True
    with pytest.raises(ValueError, match="forecast"):
        b4.run(hr([60, 70]), PLAN, None)


def test_b4_stale_calibrator_is_refused() -> None:
    forecaster = StubForecaster("v1")
    b4 = fitted(5.0, forecaster=forecaster)
    assert b4.run(hr([60, 70]), PLAN, None)
    forecaster.version = "v2"  # the model changed after the calibration
    with pytest.raises(StaleCalibratorError):
        b4.run(hr([60, 70]), PLAN, None)


# ---- constructor, state and harness ----------------------------------------------------------------------------------


def test_b4_is_a_detector_named_b4() -> None:
    b4 = make_b4()
    assert isinstance(b4, BaselineBase) and isinstance(b4, Detector)
    assert b4.name == "B4"
    assert "Hyperparameter selection" in (B4ConformalOnly.__doc__ or "")


def test_b4_run_before_fit_and_on_a_benchmark_day() -> None:
    b4 = make_b4()
    with pytest.raises(NotFittedError):
        b4.run(hr([60, 70]), PLAN, None)
    b4.fit([], [bench([60, 61])])
    with pytest.raises(LeakageError):
        b4.run(bench([60, 70]), PLAN, None)


def test_b4_alpha_has_no_default_and_is_validated() -> None:
    parameters = inspect.signature(B4ConformalOnly.__init__).parameters
    assert parameters["alpha"].default is inspect.Parameter.empty
    assert parameters["alpha"].kind is inspect.Parameter.KEYWORD_ONLY
    for bad in (0.0, 1.0, -0.1, 1.5, True, "0.2", None, math.nan):
        with pytest.raises(ValueError, match="alpha"):
            make_b4(alpha=bad)
    assert make_b4(alpha=Fraction(1, 20)).name == "B4"


def test_b4_unit_and_signals_are_validated() -> None:
    with pytest.raises(ValueError, match="unit"):
        make_b4(unit="week")
    with pytest.raises(ValueError, match="signal"):
        make_b4(signals=("not_a_signal",))
    with pytest.raises(ValueError, match="signal"):
        make_b4(signals=())
    with pytest.raises(ValueError, match="signal"):
        make_b4(signals=("hr_ecg", "hr_ecg"))
    # the default signals are bp, hr_ecg, hr_pulse and spo2, restricted to what the forecaster supports
    default = B4ConformalOnly(
        StubForecaster(), Factory([1.0] * 4), alpha=ALPHA, timing=TIMING
    )
    assert default.signals == ("bp", "hr_ecg", "hr_pulse", "spo2")
    narrow = StubForecaster()
    narrow.supported_signals = frozenset({"hr_ecg", "spo2"})
    restricted = B4ConformalOnly(narrow, Factory([1.0] * 4), alpha=ALPHA, timing=TIMING)
    assert restricted.signals == ("hr_ecg", "spo2")
    with pytest.raises(ValueError, match="support"):
        B4ConformalOnly(
            narrow, Factory([1.0]), alpha=ALPHA, signals=("bp",), timing=TIMING
        )


def test_b4_signal_without_calibration_episodes_is_silent_and_reported() -> None:
    # no calibration residual for spo2 (one sample only): that calibrator is not fitted and B4 is silent on spo2
    samples = series("hr_ecg", [60, 61]) + series("spo2", [95])
    factory = Factory([5.0, 1.0])
    b4 = make_b4(factory=factory, signals=("hr_ecg", "spo2"))
    b4.fit([], [make_benchmark_day(samples, patient_id="c1")])
    assert factory.made[1].fits == []
    out = b4.run(
        observed(series("hr_ecg", [60, 61]) + series("spo2", [95, 200])), PLAN, None
    )
    assert out == ()
    assert b4.run_stats.uncalibrated_signals == ("spo2",)


def test_b4_second_fit_replaces_the_state() -> None:
    factory = Factory([5.0, 50.0])
    b4 = make_b4(factory=factory)
    b4.fit([], [bench([60, 61])])
    assert b4.run(hr([60, 70]), PLAN, None)
    b4.fit([], [bench([60, 61])])
    assert b4.run(hr([60, 70]), PLAN, None) == ()  # the new calibrator has q = 50


def test_b4_exposes_calibration_episodes_and_residuals() -> None:
    b4 = fitted(5.0, calib=[bench([60, 62, 70]), bench([60, 61, 61], patient="c2")])
    assert b4.n_calibration_episodes == {"hr_ecg": 2}
    assert [e.sigma_true for e in b4.calibration_episodes] == [8.0, 1.0]
    b4.run(hr([60, 62, 70]), PLAN, None)
    rows = b4.residuals
    assert [(r.signal, r.residual, r.quantile, r.alarm) for r in rows] == [
        ("hr_ecg", 2.0, 5.0, False),
        ("hr_ecg", 8.0, 5.0, True),
    ]


def test_b4_real_forecasters_agree_with_the_stub_and_the_autoregression_runs() -> None:
    day = hr([60, 62, 70, 50])
    calib = [bench([60, 62, 70]), bench([60, 61, 61], patient="c2")]
    stub = make_b4(factory=SplitConformal, alpha=0.4)
    stub.fit([], calib)
    real = make_b4(
        forecaster=PersistenceForecaster(STEP), factory=SplitConformal, alpha=0.4
    )
    real.fit([], calib)
    assert real.run(day, PLAN, None) == stub.run(day, PLAN, None)
    # an autoregression of order 2 needs two samples: the first residual of a day is skipped and counted
    rng = np.random.default_rng(0)
    train = [
        make_benchmark_day(
            [
                smp("hr_ecg", i, 60.0 + float(v))
                for i, v in enumerate(np.cumsum(rng.normal(size=40)))
            ],
            patient_id=f"t{k}",
        )
        for k in range(3)
    ]
    calib_ar = [
        make_benchmark_day(
            [
                smp("hr_ecg", i, 60.0 + float(v))
                for i, v in enumerate(np.cumsum(rng.normal(size=40)))
            ],
            patient_id=f"a{k}",
        )
        for k in range(6)
    ]
    ar = B4ConformalOnly(
        AutoRegressiveForecaster(STEP, 2),
        SplitConformal,
        alpha=0.3,
        signals=("hr_ecg",),
        timing=TIMING,
    )
    ar.fit(train, calib_ar)
    test_day = observed(
        [
            smp("hr_ecg", i, 60.0 + float(v))
            for i, v in enumerate(np.cumsum(rng.normal(size=40)))
        ]
    )
    ar.run(test_day, PLAN, None)
    assert ar.run_stats.no_forecast == 1
    assert len(ar.residuals) == 38


def test_b4_allocated_level_is_the_exact_fraction() -> None:
    # alpha = 0.05 over 3 signals: per_test_exact = 1/60 (a Fraction). With n = 59 calibration days the rank is
    # k = ceil(60 * (1 - 1/60)) = 59, the largest magnitude; the float 0.05 / 3 would give +inf (WS05-T06 hand-over)
    signals = ("hr_ecg", "hr_pulse", "spo2")
    magnitudes = list(range(1, 60))
    b4 = real_b4(
        [[60, 60 + m] for m in magnitudes],
        0.05,
        signals=signals,
        allocation=BonferroniAllocation(),
    )
    spike = [s for sig in signals for s in series(sig, [60, 119.5])]
    quiet = [s for sig in signals for s in series(sig, [60, 119.0])]
    assert len(b4.run(observed(spike), PLAN, None)) == 3  # 59.5 > 59 on each signal
    assert b4.run(observed(quiet), PLAN, None) == ()  # 59.0 is inside
    # the same through the calibrator-recording stub: the level passed is a Fraction equal to 1/60
    factory = Factory([1.0] * 3)
    stubbed = make_b4(
        factory=factory, signals=signals, alpha=0.05, allocation=BonferroniAllocation()
    )
    stubbed.fit(
        [], [make_benchmark_day([s for sig in signals for s in series(sig, [60, 61])])]
    )
    assert all(
        isinstance(c.fits[0][1], Fraction) and c.fits[0][1] == Fraction(1, 60)
        for c in factory.made
    )


# ---- what B4 cannot see, by construction (pinned, not hidden) --------------------------------------------------------


def test_b4_blind_spot_a_constant_level_is_never_an_anomaly() -> None:
    # B4 sees changes, not levels. A value held at 200 all day (far outside any band) has residual 0 at every sample.
    # A slow climb in steps below q reaches the same level with no alarm either. The proposed method and B1 see a
    # level against the band of the care plan; B4 has no band by definition.
    b4 = fitted(5.0)
    assert b4.run(hr([200] * 8), PLAN, None) == ()
    assert (
        b4.run(hr([60 + 4 * k for k in range(30)]), PLAN, None) == ()
    )  # reaches 176 in steps of 4 <= 5
    # the first reading of the day cannot alarm, however extreme
    assert b4.run(hr([1e6]), PLAN, None) == ()


def test_b4_blind_spot_events_obligations_and_absences() -> None:
    # No sample is a change, and no event is read: a dispense, a missed measurement, a robot task or a whole day without
    # measurements cannot be detected (event-driven obligations, dispenses, counts, schedules).
    b4 = fitted(0.0)
    events = [
        make_event(kind, at(10 + i), payload=payload)
        for i, (kind, payload) in enumerate(
            [
                (EventKind.DISPENSE, {}),
                (EventKind.DISPENSE, {}),
                (EventKind.DISPENSE, {}),
                (EventKind.MEASUREMENT, {}),
            ]
        )
    ]
    assert b4.run(observed([], events=events), PLAN, None) == ()
    # a gap of hours with unchanged values between two readings is silent for any q >= 0
    gap = [smp("hr_ecg", 10, 60), smp("hr_ecg", 700, 60)]
    assert b4.run(observed(gap), PLAN, None) == ()


def test_b4_alarms_on_any_large_change_in_either_direction_whatever_its_clinical_meaning() -> (
    None
):
    # symmetric and unit-blind: a large drop alarms exactly as a large rise does, with no notion of a band or of what
    # direction is clinically worrying (the other side of the blind spot above: false alarms by construction)
    b4 = fitted(5.0)
    up = b4.run(hr([60, 75]), PLAN, None)
    down = b4.run(hr([75, 60]), PLAN, None)
    assert times(up) == times(down) == [at(20)]
    assert up[0].score == down[0].score


# ---- source hygiene --------------------------------------------------------------------------------------------------


def test_b4_source_has_no_specification_ground_truth_or_clinical_constants() -> None:
    source = B4_SOURCE.read_text(encoding="utf-8")
    for token in (
        "normalise",
        "rank_alerts",
        "load_templates",
        "param_values",
        "LatentDay",
        "GroundTruthEvent",
    ):
        assert token not in source
    assert not re.search(r"\b(110|140)\b", source)
    tree = ast.parse(source)
    names = {
        a.name
        for n in ast.walk(tree)
        if isinstance(n, ast.ImportFrom) and n.module == "ralmon.spec"
        for a in n.names
    }
    assert names <= {"CarePlan", "TemplateId"}
