"""B2, anomaly detection without a specification (WS06-T03): forecast-residual z-score and Isolation Forest.

FIXTURE-ONLY numbers. Every signal value, every threshold and every score below is arithmetic chosen so that the
expected result can be computed by hand in the comment next to it. Heart rates of 60 or 72 and the out-of-band level of
200 are not clinical values and nothing here is a claim of clinical validation. ``step_ms`` is 60 000 and
``reorder_delay_ms`` is 0 unless a test says otherwise.

Residual definition (the one of WS06-T03 and WS06-T05, with the index convention of WS05-T05): the residual of a
delivered sample of signal ``s`` at device time ``t`` is ``value - forecast``, where the forecast is issued at the
device time ``t_prev`` of the previous delivered sample of ``s`` with horizon ``t - t_prev`` and read from the path at
index ``(t - t_prev) // step_ms - 1``. The first sample of a signal has no residual. The persistence stub below repeats
the last value, so the residual of the stub is the difference of two consecutive values.
"""

from __future__ import annotations

import functools
import importlib
import inspect
import math
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ralmon.attribution import Detection
from ralmon.baselines import B2AnomalyDetection, B4ConformalOnly, Detector
from ralmon.baselines.access import LeakageError
from ralmon.baselines.base import BaselineBase, NotFittedError, TimingConfig
from ralmon.benchmark import BenchmarkDay, ObservedDay
from ralmon.conformal import SplitConformal
from ralmon.monitor import Forecast, InsufficientHistoryError, StaleCalibratorError
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
B2_SOURCE = ROOT / "src" / "ralmon" / "baselines" / "b2_anomaly_detection.py"
B2_FEATURES_SOURCE = ROOT / "src" / "ralmon" / "baselines" / "b2_features.py"

STEP = 60_000
STEPS_PER_DAY = 1440
T_DAY = 86_400_000
H = 3_600_000
TIMING = TimingConfig(STEP, 0, 0)
SUPPORTED = frozenset({"bp", "hr_ecg", "hr_pulse", "spo2"})
FEATURE_STEP_4 = 6 * H  # 4 rows a day
FEATURE_STEP_5 = T_DAY // 5  # 5 rows a day: 17 280 000 ms = 288 steps


def b2_module() -> Any:
    """The module under test, imported at call time so that a missing module fails one test, not the collection."""
    return importlib.import_module("ralmon.baselines.b2_anomaly_detection")


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
    """A path whose entry ``k`` is ``100 + k``: the value read from it tells which index B2 used."""

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


class RefusingForecaster(StubForecaster):
    """Raises ``InsufficientHistoryError`` for every call."""

    def predict(self, *args: Any, **kwargs: Any) -> Forecast:
        raise InsufficientHistoryError("never enough")


class StubScorer:
    """An anomaly scorer that returns preset scores, one list per ``score`` call, in call order."""

    def __init__(self, outputs: Sequence[Sequence[float]], seed: int = -1) -> None:
        self.outputs = [list(o) for o in outputs]
        self.seed = seed
        self.fit_rows: list[np.ndarray[Any, Any]] = []
        self.score_rows: list[np.ndarray[Any, Any]] = []

    def fit(self, rows: np.ndarray[Any, Any]) -> None:
        self.fit_rows.append(np.array(rows, copy=True))

    def score(self, rows: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
        self.score_rows.append(np.array(rows, copy=True))
        out = self.outputs.pop(0)
        assert len(out) == len(rows), (len(out), len(rows))
        return np.asarray(out, dtype=float)


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
    first: int = 60,
    every: int = 60,
    day: int = 0,
) -> list[Sample]:
    """Samples of one signal at steps ``first``, ``first + every``, ... (default: one a fixture hour)."""
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
    events: Sequence[Any] = (),
    first: int = 60,
    every: int = 60,
) -> BenchmarkDay:
    samples = series(signal, values, first=first, every=every, day=day)
    return make_benchmark_day(samples, events, patient_id=patient, day_index=day)


def hr(values: Sequence[float], *, day: int = 0, patient: str = "p1") -> ObservedDay:
    return observed(series("hr_ecg", values, day=day), patient=patient, day=day)


PLAN = make_care_plan()
PLAN_SCHEDULE = make_care_plan(schedule=[6 * H, 12 * H, 18 * H])


def plan_for_day(day: ObservedDay) -> Any:
    return PLAN_SCHEDULE


def make_b2(
    *,
    forecaster: Any = None,
    mode: str = "residual",
    z_threshold: float | None = 3.0,
    score_quantile: float | None = None,
    seed: int = 0,
    signals: Sequence[str] | None = ("hr_ecg",),
    timing: TimingConfig = TIMING,
    **kwargs: Any,
) -> Any:
    if mode != "residual" and "plan_for_day" not in kwargs:
        kwargs["plan_for_day"] = plan_for_day
    return B2AnomalyDetection(
        StubForecaster() if forecaster is None else forecaster,
        mode=mode,
        z_threshold=z_threshold,
        score_quantile=score_quantile,
        seed=seed,
        signals=signals,
        timing=timing,
        **kwargs,
    )


CALIB_3 = [
    60,
    63,
    60,
    63,
    60,
]  # residuals +3, -3, +3, -3: mean 0, population standard deviation 3


def residual_b2(
    z_threshold: float | None = 3.0,
    calib: Sequence[BenchmarkDay] | None = None,
    train: Sequence[BenchmarkDay] = (),
    **kwargs: Any,
) -> Any:
    """B2 in residual mode on ``hr_ecg``, fitted on one calibration day whose residuals are +3, -3, +3, -3."""
    b2 = make_b2(z_threshold=z_threshold, **kwargs)
    b2.fit(train, [bench(CALIB_3)] if calib is None else calib)
    return b2


def times(detections: Sequence[Detection]) -> list[int]:
    return [d.t_ms for d in detections]


def at(step: int, day: int = 0) -> int:
    return (day * STEPS_PER_DAY + step) * STEP


# ---- the 17 tests of the task ----------------------------------------------------------------------------------------


def test_b2_residual_zscore_hand_computed() -> None:
    # Calibration HR at 1 h to 5 h = 60, 63, 60, 63, 60: residuals +3, -3, +3, -3, mean 0, population standard
    # deviation sqrt((9 * 4) / 4) = 3. Test day HR 60, 60, 72 (steps 60, 120, 180): residuals 0 and +12. z = (12 - 0)
    # / 3 = 4.0 > 3.0: one detection at the delivery step of the 72 sample (step 180), score 4.0 / 3.0.
    b2 = residual_b2(3.0)
    scale = b2.residual_scales["hr_ecg"]
    assert (scale.mean, scale.std, scale.n) == (0.0, 3.0, 4)
    out = b2.run(hr([60, 60, 72]), PLAN, None)
    assert times(out) == [at(180)]
    assert out[0].score == 4.0 / 3.0
    assert out[0].label is None


def test_b2_zscore_threshold_strict_and_two_sided() -> None:
    b2 = residual_b2(3.0)
    # +9: z = 3.0 exactly, not above the threshold: no detection
    assert b2.run(hr([60, 69]), PLAN, None) == ()
    # -9 likewise
    assert b2.run(hr([60, 51]), PLAN, None) == ()
    # +12 and -12 give the same score 4.0 / 3.0
    up = b2.run(hr([60, 72]), PLAN, None)
    down = b2.run(hr([60, 48]), PLAN, None)
    assert times(up) == times(down) == [at(120)]
    assert up[0].score == down[0].score == 4.0 / 3.0


def test_b2_zscore_uses_the_calibration_mean() -> None:
    # Calibration 60, 64, 68, 72: residuals +4, +4, +4 would have std 0; use 60, 64, 62, 66: +4, -2, +4: mean 2,
    # population std sqrt(((2)^2 + (-4)^2 + (2)^2) / 3) = sqrt(8). A residual +2 is the mean: z = 0.
    b2 = residual_b2(1.0, calib=[bench([60, 64, 62, 66])])
    scale = b2.residual_scales["hr_ecg"]
    assert scale.mean == pytest.approx(2.0)
    assert scale.std == pytest.approx(math.sqrt(8.0))
    assert b2.run(hr([60, 62]), PLAN, None) == ()
    out = b2.run(hr([60, 70]), PLAN, None)  # (10 - 2) / sqrt(8)
    assert out[0].score == pytest.approx(8.0 / math.sqrt(8.0) / 1.0)


def test_b2_first_sample_has_no_residual() -> None:
    b2 = residual_b2(3.0)
    assert b2.run(hr([200]), PLAN, None) == ()
    assert b2.residuals == ()
    assert b2.run_stats.residuals == 0


def test_b2_residual_scale_from_calibration_days_only() -> None:
    forecaster = StubForecaster()
    b2 = make_b2(forecaster=forecaster)
    calib_a = [bench(CALIB_3, patient="ca")]
    train_1 = [bench([10, 90, 10, 90], patient="t1")]
    train_2 = [bench([1, 2, 3, 4, 5], patient="t2")]
    b2.fit(train_1, calib_a)
    first = dict(b2.residual_scales)
    b2.fit(train_2, calib_a)
    assert (
        dict(b2.residual_scales) == first
    )  # a different training set does not move the scale
    assert len(forecaster.fit_calls) == 2  # the forecaster did see the training days
    assert forecaster.fit_calls[0] != forecaster.fit_calls[1]
    b2.fit(train_2, [bench([60, 66, 60, 66], patient="cb")])
    assert dict(b2.residual_scales) != first  # a different calibration set does
    assert b2.residual_scales["hr_ecg"].std == pytest.approx(6.0)
    # only the observed trace is read, on both splits, and nothing is refused
    assert b2.access_log.fields() == frozenset({"observed"})
    assert b2.access_log.denied == ()


def test_b2_quantile_threshold_hand_computed() -> None:
    # Scores [1, 2, 3, 4] with score_quantile 0.75: numpy.quantile, linear interpolation, position
    # 0.75 * (4 - 1) = 2.25 between the third and the fourth: 3 + 0.25 * (4 - 3) = 3.25.
    scorer = StubScorer([[1, 2, 3, 4]])
    b2 = make_b2(
        mode="iforest",
        z_threshold=None,
        score_quantile=0.75,
        feature_step_ms=FEATURE_STEP_4,
        scorer_factory=lambda seed: scorer,
    )
    b2.fit([bench([])], [bench([])])
    assert b2.iforest_threshold == 3.25
    assert b2.iforest_threshold == float(np.quantile([1, 2, 3, 4], 0.75))


def _real_scorer(seed: int = 0) -> Any:
    return b2_module().IsolationForestScorer(seed)


def test_b2_iforest_scores_outlier_above_inlier() -> None:
    rng = np.random.default_rng(0)
    centre = np.array([50.0, 120.0, 3.0])
    rows = centre + rng.normal(0.0, 1.0, size=(200, 3))
    scorer = _real_scorer(0)
    scorer.fit(rows)
    far = centre + np.array([25.0, -30.0, 15.0])
    scores = scorer.score(np.vstack([centre, far]))
    assert scores[1] > scores[0]
    assert scores.shape == (2,)
    assert np.all(np.isfinite(scores))


def test_b2_iforest_one_detection_per_rising_edge() -> None:
    # Calibration scores [0.5] * 5 give the threshold 0.5. Run scores [0.1, 0.9, 0.95, 0.2, 0.8]: the condition
    # score > 0.5 holds at rows 1, 2 and 4; it turns true at rows 1 and 4. One detection each, with the score of the
    # row at the edge divided by the threshold: 0.9 / 0.5 = 1.8 and 0.8 / 0.5 = 1.6 (not the 0.95 of row 2).
    scorer = StubScorer([[0.5] * 5, [0.1, 0.9, 0.95, 0.2, 0.8]])
    b2 = make_b2(
        mode="iforest",
        z_threshold=None,
        score_quantile=0.5,
        feature_step_ms=FEATURE_STEP_5,
        scorer_factory=lambda seed: scorer,
    )
    b2.fit([bench([])], [bench([])])
    assert b2.iforest_threshold == 0.5
    out = b2.run(observed([]), PLAN, None)
    assert times(out) == [FEATURE_STEP_5, 4 * FEATURE_STEP_5]
    assert [d.score for d in out] == [1.8, 1.6]
    assert all(d.label is None for d in out)
    rows = b2.iforest_rows
    assert [r.t_ms for r in rows] == [k * FEATURE_STEP_5 for k in range(5)]
    assert [r.alarm for r in rows] == [False, True, True, False, True]


def _real_days(n: int, *, seed: int, first_patient: int = 0) -> list[BenchmarkDay]:
    """Days of one HR channel and one dispense, with values drawn from a seeded generator."""
    rng = np.random.default_rng(seed)
    days = []
    for i in range(n):
        values = [float(v) for v in rng.integers(55, 75, size=6)]
        dispense_step = int(rng.integers(300, 900))
        days.append(
            bench(
                values,
                patient=f"r{first_patient + i}",
                first=100,
                every=120,
                events=[make_event(EventKind.DISPENSE, dispense_step * STEP)],
            )
        )
    return days


def test_b2_deterministic_given_seed() -> None:
    train, calib = _real_days(3, seed=1), _real_days(3, seed=2, first_patient=10)
    test_day = observed(
        series("hr_ecg", [60, 62, 120, 61, 63], first=100, every=120),
        events=[make_event(EventKind.DISPENSE, 500 * STEP)],
    )
    outputs = []
    for _ in range(2):
        b2 = make_b2(
            mode="both",
            z_threshold=1.0,
            score_quantile=0.5,
            seed=7,
            feature_step_ms=10 * STEP,
        )
        b2.fit(train, calib)
        outputs.append(tuple(b2.run(test_day, PLAN_SCHEDULE, None)))
    assert outputs[0] == outputs[1]
    assert outputs[0], (
        "the fixture must produce detections, or the test compares two empty lists"
    )
    with pytest.raises(TypeError):
        B2AnomalyDetection(  # type: ignore[call-arg]
            StubForecaster(), mode="residual", z_threshold=3.0, timing=TIMING
        )


def test_b2_seed_reaches_the_estimator() -> None:
    seen: list[int] = []

    def factory(seed: int) -> StubScorer:
        seen.append(seed)
        return StubScorer([[0.5] * 4])

    b2 = make_b2(
        mode="iforest",
        z_threshold=None,
        score_quantile=0.5,
        seed=1234,
        feature_step_ms=FEATURE_STEP_4,
        scorer_factory=factory,
    )
    b2.fit([bench([])], [bench([])])
    assert seen == [1234]
    # the default scorer is seeded through the estimator's random-state argument
    scorer = b2_module().IsolationForestScorer(99)
    assert scorer.seed == 99


def test_b2_modes_and_names() -> None:
    cases = {"residual": "B2-residual", "iforest": "B2-iforest", "both": "B2"}
    for mode, name in cases.items():
        b2 = make_b2(
            mode=mode,
            z_threshold=3.0 if mode != "iforest" else None,
            score_quantile=0.5 if mode != "residual" else None,
            feature_step_ms=FEATURE_STEP_4,
        )
        assert b2.name == name
    with pytest.raises(ValueError, match="mode"):
        make_b2(mode="nonsense")


def test_b2_both_is_the_time_sorted_union() -> None:
    # Residual detection at step 120 (the +12 jump after the calibration scale 3) and the Isolation Forest rising
    # edges at rows 1 and 4 (of 5 rows a day). The union holds all three, sorted by time.
    scorer = StubScorer([[0.5] * 5, [0.1, 0.9, 0.95, 0.2, 0.8]])
    b2 = make_b2(
        mode="both",
        z_threshold=3.0,
        score_quantile=0.5,
        feature_step_ms=FEATURE_STEP_5,
        scorer_factory=lambda seed: scorer,
    )
    b2.fit([bench([])], [bench(CALIB_3)])
    day = hr([60, 72])
    out = b2.run(day, PLAN, None)
    assert times(out) == [at(120), FEATURE_STEP_5, 4 * FEATURE_STEP_5]
    assert len(out) == 3
    assert out[0].score == 4.0 / 3.0
    assert [d.score for d in out[1:]] == [1.8, 1.6]


def test_b2_operating_parameters_have_no_numeric_defaults() -> None:
    parameters = inspect.signature(B2AnomalyDetection.__init__).parameters
    assert parameters["z_threshold"].default is None
    assert parameters["score_quantile"].default is None
    assert parameters["seed"].default is inspect.Parameter.empty
    assert parameters["seed"].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters["timing"].default is inspect.Parameter.empty
    assert "Hyperparameter selection" in (B2AnomalyDetection.__doc__ or "")
    with pytest.raises(ValueError, match="z_threshold"):
        make_b2(mode="residual", z_threshold=None, score_quantile=None)
    with pytest.raises(ValueError, match="z_threshold"):
        make_b2(mode="both", z_threshold=None, score_quantile=0.5)
    with pytest.raises(ValueError, match="score_quantile"):
        make_b2(mode="iforest", z_threshold=None, score_quantile=None)
    with pytest.raises(ValueError, match="score_quantile"):
        make_b2(mode="both", z_threshold=3.0, score_quantile=None)
    # a parameter that the mode does not use is refused, not silently ignored
    with pytest.raises(ValueError, match="score_quantile"):
        make_b2(mode="residual", z_threshold=3.0, score_quantile=0.5)
    with pytest.raises(ValueError, match="z_threshold"):
        make_b2(mode="iforest", z_threshold=3.0, score_quantile=0.5)


@pytest.mark.parametrize("bad", [0.0, -1.0, math.inf, math.nan, True, "3", 0])
def test_b2_z_threshold_must_be_a_positive_finite_number(bad: Any) -> None:
    with pytest.raises(ValueError, match="z_threshold"):
        make_b2(z_threshold=bad)


@pytest.mark.parametrize("bad", [-0.1, 1.1, math.nan, True, "0.5"])
def test_b2_score_quantile_must_lie_in_the_unit_interval(bad: Any) -> None:
    with pytest.raises(ValueError, match="score_quantile"):
        make_b2(mode="iforest", z_threshold=None, score_quantile=bad)


def test_b2_ignores_evidence_and_never_labels() -> None:
    b2 = make_b2(
        mode="both",
        z_threshold=1.0,
        score_quantile=0.5,
        feature_step_ms=10 * STEP,
    )
    b2.fit(_real_days(2, seed=3), _real_days(2, seed=4, first_patient=5))
    day = observed(
        series("hr_ecg", [60, 120, 61, 130], first=100, every=120),
        events=[make_event(EventKind.DISPENSE, 400 * STEP)],
    )
    plain = tuple(b2.run(day, PLAN_SCHEDULE, None))
    with_evidence = tuple(b2.run(day, PLAN_SCHEDULE, evidence_mapping()))
    assert plain == with_evidence
    assert plain
    assert all(d.label is None for d in plain)


def test_b2_reads_no_ground_truth_latent_or_clinical_thresholds() -> None:
    plan = make_care_plan(
        [], schedule=[6 * H, 12 * H]
    )  # a plan with instances is covered below
    b2 = make_b2(
        mode="both", z_threshold=3.0, score_quantile=0.5, feature_step_ms=FEATURE_STEP_4
    )
    b2.fit(_real_days(2, seed=5), _real_days(2, seed=6, first_patient=5))
    assert b2.access_log.reads(field="ground_truth") == ()
    assert b2.access_log.reads(field="latent") == ()
    assert b2.access_log.fields() == frozenset({"observed"})
    assert b2.access_log.denied == ()
    b2.run(hr([60, 61, 99]), plan, None)
    assert b2.read_log.all_names() == frozenset()
    assert b2.read_log.registry_reads == frozenset()
    assert b2.read_log.param_reads == {}


def test_b2_never_reads_the_parameters_of_a_plan_instance() -> None:
    plan = make_care_plan(
        [make_instance(TemplateId.RANGE, "r", {"bp_band_low": 110.0}, None)],
        schedule=[6 * H],
    )
    b2 = make_b2(
        mode="both", z_threshold=3.0, score_quantile=0.5, feature_step_ms=FEATURE_STEP_4
    )
    b2.fit(_real_days(1, seed=5), _real_days(1, seed=6, first_patient=5))
    b2.run(hr([60, 99]), plan, None)
    assert b2.read_log.param_reads == {}
    assert b2.read_log.all_names() == frozenset()


# ---- test 17: causality (Hypothesis) ---------------------------------------------------------------------------------


@functools.cache
def _causal_b2() -> Any:
    b2 = make_b2(
        mode="both", z_threshold=0.5, score_quantile=0.5, feature_step_ms=10 * STEP
    )
    b2.fit(_real_days(3, seed=11), _real_days(3, seed=12, first_patient=10))
    return b2


@st.composite
def _day_inputs(draw: Any) -> tuple[list[Sample], list[Any], int]:
    samples = []
    for _ in range(draw(st.integers(0, 10))):
        step = draw(st.integers(0, 90))
        rx = step + draw(st.integers(0, 2))
        samples.append(smp("hr_ecg", step, draw(st.integers(40, 140)), rx))
    events = []
    for _ in range(draw(st.integers(0, 4))):
        step = draw(st.integers(0, 90))
        events.append(
            make_event(
                EventKind.DISPENSE, step * STEP, (step + draw(st.integers(0, 2))) * STEP
            )
        )
    cut = draw(st.integers(0, 100)) * STEP
    return samples, events, cut


@settings(max_examples=40, deadline=None)
@given(_day_inputs())
def test_b2_is_causal_property(data: tuple[list[Sample], list[Any], int]) -> None:
    samples, events, cut = data
    b2 = _causal_b2()
    full = b2.run(observed(samples, events=events), PLAN_SCHEDULE, None)
    kept_samples = [s for s in samples if s.t_rx_ms <= cut]
    kept_events = [e for e in events if e.t_rx_ms <= cut]
    truncated = b2.run(observed(kept_samples, events=kept_events), PLAN_SCHEDULE, None)
    assert [d for d in full if d.t_ms <= cut] == [d for d in truncated if d.t_ms <= cut]


def test_b2_causality_fixture_produces_detections() -> None:
    # guards the property above against vacuity: the fixture does raise detections of both kinds
    b2 = _causal_b2()
    day = observed(
        series("hr_ecg", [60, 130, 61, 62], first=10, every=10),
        events=[make_event(EventKind.DISPENSE, 25 * STEP)],
    )
    out = b2.run(day, PLAN_SCHEDULE, None)
    assert b2.run_stats.residuals == 3
    assert any(r.alarm for r in b2.residuals)
    assert any(r.alarm for r in b2.iforest_rows)
    assert len(out) >= 2


# ---- the residual rule shared with B4 --------------------------------------------------------------------------------


def test_b2_reads_the_path_at_index_gap_over_step_minus_one() -> None:
    # Ramp path: entry k is 100 + k. Samples at steps 10 and 13: gap 3 steps, index 2, forecast 102. The sample
    # value 105 gives residual 3. (The floor((t - t_from) / step) form of the task text would read entry 3 = 103.)
    b2 = make_b2(forecaster=RampForecaster(), z_threshold=1.0)
    b2.fit([], [bench([100, 100, 100], first=10, every=3)])
    b2.run(observed([smp("hr_ecg", 10, 100), smp("hr_ecg", 13, 105)]), PLAN, None)
    (row,) = b2.residuals
    assert (row.forecast, row.residual) == (102.0, 3.0)
    assert row.t_ms == at(13)
    assert row.t_device_ms == at(13)


def test_b2_asks_for_the_signal_and_passes_that_signals_history() -> None:
    forecaster = StubForecaster()
    b2 = make_b2(forecaster=forecaster, signals=("hr_ecg", "spo2"), z_threshold=1.0)
    day = observed(
        [
            smp("hr_ecg", 10, 60),
            smp("spo2", 12, 97),
            smp("hr_ecg", 20, 62),
            smp("spo2", 22, 96),
            smp("bp", 23, 150),
        ]
    )
    b2.fit([], [bench([], signal="hr_ecg")])
    forecaster.predict_calls.clear()
    b2.run(day, PLAN, None)
    assert [c[3] for c in forecaster.predict_calls] == ["hr_ecg", "spo2"]
    for history, _t_prev, gap, signal in forecaster.predict_calls:
        assert {s.signal for s in history} == {signal}
        assert gap == 10 * STEP
    assert forecaster.predict_calls[0][1] == at(10)
    assert forecaster.predict_calls[1][1] == at(12)


def test_b2_insufficient_history_skips_the_residual() -> None:
    b2 = make_b2(forecaster=RefusingForecaster(), z_threshold=1.0)
    b2.fit([], [bench([60, 63, 60])])
    assert (
        b2.residual_scales == {}
    )  # no calibration residual: the signal is uncalibrated
    out = b2.run(hr([60, 99, 60]), PLAN, None)
    assert out == ()
    assert b2.run_stats.no_forecast == 2
    assert b2.run_stats.residuals == 0
    assert b2.run_stats.uncalibrated_signals == ("hr_ecg",)


def test_b2_gap_shorter_than_a_step_has_no_residual() -> None:
    b2 = residual_b2(3.0)
    near = Sample("hr_ecg", at(10) + 30_000, at(10) + 30_000, 90.0, None, None)
    out = b2.run(observed([smp("hr_ecg", 10, 60), near]), PLAN, None)
    assert out == ()
    assert b2.run_stats.no_forecast == 1
    assert b2.run_stats.residuals == 0


def test_b2_duplicate_has_no_residual_and_does_not_replace_the_previous_sample() -> (
    None
):
    b2 = residual_b2(3.0)
    day = observed(
        [
            smp("hr_ecg", 10, 60),
            smp("hr_ecg", 10, 90),  # same device time: not newer
            smp("hr_ecg", 20, 61),
        ]
    )
    assert (
        b2.run(day, PLAN, None) == ()
    )  # 61 - 60 = 1, z = 0.33; the 90 was not the previous sample
    assert b2.run_stats.not_newer == 1
    assert [r.residual for r in b2.residuals] == [1.0]


def test_b2_late_input_is_dropped_and_counted_like_the_monitor_does() -> None:
    b2 = residual_b2(3.0)
    # D = 0: a sample received after its step (rx step 21 for device step 20) is final-late and dropped
    day = observed([smp("hr_ecg", 10, 60), smp("hr_ecg", 20, 99, rx_step=21)])
    assert b2.run(day, PLAN, None) == ()
    assert b2.run_stats.late_inputs == 1
    on_time = observed([smp("hr_ecg", 10, 60), smp("hr_ecg", 20, 99, rx_step=20)])
    assert times(b2.run(on_time, PLAN, None)) == [at(20)]
    assert b2.run_stats.late_inputs == 0


def test_b2_reorder_delay_moves_the_lateness_boundary() -> None:
    timing = TimingConfig(STEP, 2 * STEP, 0)
    b2 = residual_b2(3.0, timing=timing)
    # D = 2 steps: delivered at device + 2 steps; received within 2 steps is on time, 3 steps is late
    on_time = observed([smp("hr_ecg", 10, 60), smp("hr_ecg", 20, 99, rx_step=22)])
    out = b2.run(on_time, PLAN, None)
    assert times(out) == [at(22)]  # detection time is the delivery step: t_eval + D
    late = observed([smp("hr_ecg", 10, 60), smp("hr_ecg", 20, 99, rx_step=23)])
    assert b2.run(late, PLAN, None) == ()
    assert b2.run_stats.late_inputs == 1


def test_b2_non_finite_value_is_not_a_reading() -> None:
    b2 = residual_b2(3.0)
    day = observed(
        [smp("hr_ecg", 10, 60), smp("hr_ecg", 20, float("nan")), smp("hr_ecg", 30, 61)]
    )
    assert b2.run(day, PLAN, None) == ()
    assert b2.run_stats.non_finite_samples == 1
    assert [r.residual for r in b2.residuals] == [1.0]


def test_b2_pre_day_samples_are_values_but_not_detections() -> None:
    b2 = residual_b2(3.0)
    # a sample stamped a whole step or more before day 1 is a delivered value (the previous sample of the next one)
    # but yields no detection; the next sample's residual is computed against it
    day1 = observed(
        [smp("hr_ecg", -5, 60, rx_step=0, day=1), smp("hr_ecg", 30, 99, day=1)],
        day=1,
    )
    out = b2.run(day1, PLAN, None)
    assert times(out) == [at(30, 1)]
    only_pre = observed(
        [
            smp("hr_ecg", -10, 60, rx_step=0, day=1),
            smp("hr_ecg", -5, 99, rx_step=0, day=1),
        ],
        day=1,
    )
    assert b2.run(only_pre, PLAN, None) == ()


def test_b2_zero_scale_makes_any_deviation_an_alarm_with_a_finite_score() -> None:
    # calibration residuals all equal (+2): population std 0, mean 2. A residual of 2 is exactly the mean (z = 0);
    # any other residual is infinitely many deviations away and gets the largest finite score.
    b2 = residual_b2(3.0, calib=[bench([60, 62, 64, 66])])
    assert b2.residual_scales["hr_ecg"].std == 0.0
    assert b2.run(hr([60, 62]), PLAN, None) == ()
    out = b2.run(hr([60, 63]), PLAN, None)
    assert times(out) == [at(120)]
    assert math.isfinite(out[0].score) and out[0].score > 1e300


def test_b2_signal_with_fewer_than_two_calibration_residuals_is_silent() -> None:
    b2 = residual_b2(
        3.0, calib=[bench([60, 63])]
    )  # one residual: no spread to estimate
    assert b2.residual_scales == {}
    assert b2.run(hr([60, 200]), PLAN, None) == ()
    assert b2.run_stats.uncalibrated_signals == ("hr_ecg",)


def test_b2_stale_scale_is_refused_after_the_forecaster_changes() -> None:
    forecaster = StubForecaster("v1")
    b2 = residual_b2(3.0, forecaster=forecaster)
    forecaster.version = "v2"
    with pytest.raises(StaleCalibratorError):
        b2.run(hr([60, 72]), PLAN, None)
    b2.fit([], [bench(CALIB_3)])
    assert times(b2.run(hr([60, 72]), PLAN, None)) == [at(120)]


def test_b2_residuals_equal_those_of_b4() -> None:
    # WS06-T07 test 11 in miniature: the residual series of B2 and B4 on one day, one persistence stub
    day = observed(
        [
            smp("hr_ecg", 10, 60),
            smp("hr_ecg", 20, 63),
            smp("hr_ecg", 20, 99),
            smp("hr_ecg", 25, 70),
            Sample("hr_ecg", at(25) + 20_000, at(25) + 20_000, 80.0, None, None),
            smp("spo2", 15, 97),
            smp("spo2", 30, 95),
        ]
    )
    assert _residual_keys_b2(day, TIMING) == _residual_keys_b4(day, TIMING)
    assert len(_residual_keys_b2(day, TIMING)) == 3  # hr 3 and 7, spo2 -2


def _residual_keys_b2(day: ObservedDay, timing: TimingConfig) -> list[Any]:
    b2 = make_b2(signals=("hr_ecg", "spo2"), timing=timing, z_threshold=1.0)
    b2.fit([], [bench([60, 62, 61], signal="hr_ecg", patient="k")])
    b2.run(day, PLAN, None)
    return [
        (r.signal, r.t_ms, r.t_device_ms, r.value, r.forecast, r.residual)
        for r in b2.residuals
    ]


def _residual_keys_b4(day: ObservedDay, timing: TimingConfig) -> list[Any]:
    b4 = B4ConformalOnly(
        StubForecaster(),
        SplitConformal,
        alpha=0.2,
        signals=("hr_ecg", "spo2"),
        timing=timing,
    )
    b4.fit([], [bench([60, 62, 61], signal="hr_ecg", patient="k")])
    b4.run(day, PLAN, None)
    return [
        (r.signal, r.t_ms, r.t_device_ms, r.value, r.forecast, r.residual)
        for r in b4.residuals
    ]


@st.composite
def _residual_days(draw: Any) -> ObservedDay:
    samples = []
    for _ in range(draw(st.integers(0, 14))):
        step = draw(st.integers(0, 120))
        jitter = draw(st.sampled_from([0, 0, 0, 30_000]))
        device = step * STEP + jitter
        rx = device + draw(st.sampled_from([0, 0, STEP, 2 * STEP, 3 * STEP]))
        samples.append(
            Sample(
                draw(st.sampled_from(["hr_ecg", "spo2", "bp"])),
                device,
                rx,
                float(draw(st.integers(40, 120))),
                None,
                None,
            )
        )
    return observed(samples)


@settings(max_examples=60, deadline=None)
@given(_residual_days(), st.sampled_from([0, 2 * STEP]))
def test_b2_residual_series_equals_b4_property(day: ObservedDay, delay: int) -> None:
    timing = TimingConfig(STEP, delay, 0)
    assert _residual_keys_b2(day, timing) == _residual_keys_b4(day, timing)


# ---- blind spots, pinned by construction (the B1, B3 and B4 lesson) --------------------------------------------------


def test_b2_residual_blind_spot_a_constant_level_is_never_an_anomaly() -> None:
    # A value held at 200 has residual 0: the z-score sees changes, not levels. Nor does a drift in small steps.
    b2 = residual_b2(3.0)
    held = hr([200, 200, 200, 200])
    assert b2.run(held, PLAN, None) == ()
    drift = hr([60, 62, 64, 66, 68, 70, 72, 74, 76, 78, 80, 82, 84, 86, 88, 90])
    assert b2.run(drift, PLAN, None) == ()  # each step +2, z = 2 / 3 < 3


def test_b2_residual_blind_spot_absence_and_events() -> None:
    # No samples, an hours-long gap with the same value, and dispenses: no residual detection
    b2 = residual_b2(3.0)
    assert b2.run(observed([]), PLAN, None) == ()
    gap = observed([smp("hr_ecg", 10, 60), smp("hr_ecg", 900, 60)])
    assert b2.run(gap, PLAN, None) == ()
    events = [make_event(EventKind.DISPENSE, k * STEP) for k in (10, 11, 12, 13)]
    assert b2.run(observed([], events=events), PLAN, None) == ()


def test_b2_residual_alarms_on_any_large_change_whatever_its_clinical_meaning() -> None:
    # a wanted drop alarms like a rise: false alarms by construction
    b2 = residual_b2(3.0)
    assert len(b2.run(hr([90, 60]), PLAN, None)) == 1


def test_b2_residual_mode_is_independent_of_the_plan_and_of_the_tail() -> None:
    day = hr([60, 60, 72])
    base = residual_b2(3.0)
    out = base.run(day, PLAN, None)
    other = residual_b2(3.0, timing=TimingConfig(STEP, 0, 10 * H))
    assert tuple(other.run(day, PLAN_SCHEDULE, None)) == tuple(out)
    assert other.read_log.all_names() == frozenset()


def test_b2_iforest_blind_spot_it_learns_what_is_frequent_not_what_is_allowed() -> None:
    # The forest is unsupervised and has no band. A population whose values sit at 200 (out of any clinical range)
    # makes 200 ordinary, and a value of 120 that a clinician would accept scores as MORE anomalous. This is the
    # reason B2 is not "equal clinical knowledge": it measures unusualness, not safety.
    rng = np.random.default_rng(0)
    days = []
    for i in range(12):
        values = [float(v) for v in rng.integers(190, 211, size=8)]
        days.append(bench(values, signal="bp", patient=f"h{i}", first=30, every=60))
    b2 = make_b2(
        mode="iforest",
        z_threshold=None,
        score_quantile=0.99,
        signals=("bp",),
        feature_step_ms=15 * STEP,
        seed=3,
    )
    b2.fit(days[:6], days[6:])
    usual = observed(series("bp", [200.0] * 8, first=30, every=60))
    unusual = observed(series("bp", [120.0] * 8, first=30, every=60))
    b2.run(usual, PLAN_SCHEDULE, None)
    usual_scores = [r.score for r in b2.iforest_rows if r.t_ms >= at(480)]
    b2.run(unusual, PLAN_SCHEDULE, None)
    unusual_scores = [r.score for r in b2.iforest_rows if r.t_ms >= at(480)]
    assert np.mean(unusual_scores) > np.mean(usual_scores)


def test_b2_iforest_cannot_name_a_cause() -> None:
    b2 = residual_b2(3.0)
    out = b2.run(hr([60, 72]), PLAN, None)
    assert [d.label for d in out] == [None]


# ---- the isolation-forest features through the detector --------------------------------------------------------------


def test_b2_imputes_undefined_features_with_the_train_day_means() -> None:
    # Train day: BP 100 at 5 h and 200 at 11 h, rows at 0, 6, 12, 18 h: last_bp is None, 100, 200, 200. The mean of the
    # defined values is (100 + 200 + 200) / 3. The calibration day has other values and must not move the mean.
    scorer = StubScorer([[1, 2, 3, 4]])
    b2 = make_b2(
        mode="iforest",
        z_threshold=None,
        score_quantile=0.5,
        signals=("bp",),
        feature_step_ms=FEATURE_STEP_4,
        scorer_factory=lambda seed: scorer,
    )
    train = bench([100, 200], signal="bp", first=300, every=360)
    calib = bench([10, 20], signal="bp", first=300, every=360, patient="cc")
    b2.fit([train], [calib])
    (fit_rows,) = scorer.fit_rows
    names = b2_module().feature_names(("bp",))
    col = names.index("last_bp")
    assert fit_rows.shape == (4, len(names))
    assert fit_rows[:, col] == pytest.approx([500 / 3, 100.0, 200.0, 200.0])
    (calib_rows,) = scorer.score_rows
    assert calib_rows[0, col] == pytest.approx(
        500 / 3
    )  # imputed with the train mean, not the calibration mean
    assert not np.isnan(fit_rows).any() and not np.isnan(calib_rows).any()


def test_b2_iforest_rows_cover_the_day_and_do_not_depend_on_the_tail() -> None:
    results = []
    for tail in (0, 10 * H):
        scorer = StubScorer([[0.5] * 4, [0.1, 0.9, 0.2, 0.3]])
        b2 = make_b2(
            mode="iforest",
            z_threshold=None,
            score_quantile=0.5,
            feature_step_ms=FEATURE_STEP_4,
            timing=TimingConfig(STEP, 0, tail),
            scorer_factory=lambda seed, s=scorer: s,
        )
        b2.fit([bench([])], [bench([])])
        results.append(tuple(b2.run(observed([]), PLAN, None)))
    assert results[0] == results[1]
    assert times(results[0]) == [FEATURE_STEP_4]


def test_b2_iforest_requires_a_plan_source_for_the_schedule_features() -> None:
    with pytest.raises(ValueError, match="plan_for_day"):
        B2AnomalyDetection(
            StubForecaster(),
            mode="iforest",
            score_quantile=0.5,
            seed=0,
            timing=TIMING,
        )
    # the residual mode needs no plan at all
    make_b2(mode="residual")


def test_b2_iforest_without_training_rows_or_calibration_rows() -> None:
    scorer = StubScorer([])
    b2 = make_b2(
        mode="iforest",
        z_threshold=None,
        score_quantile=0.5,
        feature_step_ms=FEATURE_STEP_4,
        scorer_factory=lambda seed: scorer,
    )
    with pytest.raises(ValueError, match="training"):
        b2.fit([], [bench([])])
    assert not b2.is_fitted
    # no calibration day: the threshold is undefined and the forest stays silent, which the stats say
    scorer2 = StubScorer([[0.1, 0.9, 0.2, 0.3]])
    b2 = make_b2(
        mode="iforest",
        z_threshold=None,
        score_quantile=0.5,
        feature_step_ms=FEATURE_STEP_4,
        scorer_factory=lambda seed: scorer2,
    )
    b2.fit([bench([])], [])
    assert b2.iforest_threshold is None
    assert b2.run(observed([]), PLAN, None) == ()
    assert b2.run_stats.iforest_calibrated is False


@pytest.mark.parametrize("bad", [0, -60_000, 90_000, 60_001, True, 1.5])
def test_b2_feature_step_must_be_a_positive_multiple_of_the_step(bad: Any) -> None:
    with pytest.raises(ValueError, match="feature_step_ms"):
        make_b2(
            mode="iforest",
            z_threshold=None,
            score_quantile=0.5,
            feature_step_ms=bad,
        )


def test_b2_feature_step_defaults_to_the_monitor_step() -> None:
    b2 = make_b2(mode="iforest", z_threshold=None, score_quantile=0.5)
    assert b2.feature_step_ms == STEP


# ---- harness conventions ---------------------------------------------------------------------------------------------


def test_b2_is_a_detector_and_a_baseline() -> None:
    b2 = make_b2()
    assert isinstance(b2, Detector)
    assert isinstance(b2, BaselineBase)


def test_b2_refuses_to_run_before_fit_and_on_a_non_observed_day() -> None:
    b2 = make_b2()
    with pytest.raises(NotFittedError):
        b2.run(hr([60, 72]), PLAN, None)
    b2.fit([], [bench(CALIB_3)])
    with pytest.raises(LeakageError):
        b2.run(bench([60, 72]), PLAN, None)


def test_b2_default_signals_are_the_continuous_in_scope_channels() -> None:
    b2 = B2AnomalyDetection(
        StubForecaster(), mode="residual", z_threshold=3.0, seed=0, timing=TIMING
    )
    assert b2.signals == ("bp", "hr_ecg", "hr_pulse", "spo2")
    with pytest.raises(ValueError, match="not supported"):
        make_b2(signals=("nonsense",))
    with pytest.raises(ValueError, match="twice"):
        make_b2(signals=("hr_ecg", "hr_ecg"))


def test_b2_scores_of_alarms_exceed_one() -> None:
    b2 = residual_b2(3.0)
    out = b2.run(hr([60, 72, 60, 48, 200]), PLAN, None)
    assert out and all(d.score > 1.0 for d in out)


# ---- sources and dependency ------------------------------------------------------------------------------------------


def test_b2_sources_name_no_latent_type_no_normalisation_and_no_clinical_constant() -> (
    None
):
    for path in (B2_SOURCE, B2_FEATURES_SOURCE):
        text = path.read_text(encoding="utf-8")
        for token in (
            "LatentDay",
            "GroundTruthEvent",
            "normalise",
            "rank_alerts",
            "load_templates",
            "param_values",
            ".ground_truth",
            ".latent",
        ):
            assert token not in text, (path.name, token)
        assert not re.search(r"\b(110|140)\b", text), path.name


def test_scikit_learn_is_a_declared_dependency() -> None:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    dependencies = text.split("dependencies = [", 1)[1].split("]", 1)[0]
    assert "scikit-learn" in dependencies


def test_b2_default_scorer_is_the_library_isolation_forest() -> None:
    scorer = _real_scorer(5)
    rng = np.random.default_rng(1)
    scorer.fit(rng.normal(size=(60, 2)))
    inner = scorer.estimator
    from sklearn.ensemble import IsolationForest

    assert isinstance(inner, IsolationForest)
    assert inner.random_state == 5
    # estimator settings other than the seed are the library defaults (hyperparameter selection, step 5 of the task)
    defaults = IsolationForest()
    assert inner.n_estimators == defaults.n_estimators
    assert inner.max_samples == defaults.max_samples
    assert inner.contamination == defaults.contamination


def test_b2_scorer_and_plan_sources_default_to_none() -> None:
    parameters = inspect.signature(B2AnomalyDetection.__init__).parameters
    assert parameters["scorer_factory"].default is None
    assert parameters["plan_for_day"].default is None
    assert parameters["feature_step_ms"].default is None
    assert parameters["signals"].default is None
