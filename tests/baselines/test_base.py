"""The Detector protocol, the BaselineBase template and the causal step iterator (WS06-T01).

FIXTURE-ONLY numbers (see conftest.py); every expected value below is computed by hand.
"""

from __future__ import annotations

import inspect
import math
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ralmon.attribution import AttributedCause, Detection
from ralmon.baselines import Detector
from ralmon.baselines.base import (
    BaselineBase,
    InvalidDetectionError,
    InvalidTimingError,
    LeakageError,
    NotFittedError,
    StepBatch,
    TimingConfig,
    evaluation_end_ms,
    iter_steps,
    rising_edges,
)
from ralmon.signals import EventKind, hours

from .conftest import (
    STEP_MS,
    RecordingBaseline,
    evidence_mapping,
    make_benchmark_day,
    make_care_plan,
    make_event,
    make_observed_day,
    make_sample,
)

ROOT = Path(__file__).resolve().parents[2]


def batches(day, timing, end_ms, **kwargs):  # type: ignore[no-untyped-def]
    return list(iter_steps(day, timing, end_ms, **kwargs))


def fitted(**kwargs):  # type: ignore[no-untyped-def]
    detector = RecordingBaseline(**kwargs)
    detector.fit([make_benchmark_day()], [make_benchmark_day(patient_id="p2")])
    return detector


# ---- BaselineBase -------------------------------------------------------------------------


def test_baseline_base_signatures_match_detector() -> None:
    for method in ("fit", "run"):
        expected = list(inspect.signature(getattr(Detector, method)).parameters)
        actual = list(inspect.signature(getattr(BaselineBase, method)).parameters)
        assert actual == expected
    assert list(inspect.signature(BaselineBase.fit).parameters) == [
        "self",
        "train_days",
        "calib_days",
    ]
    assert list(inspect.signature(BaselineBase.run).parameters) == [
        "self",
        "day",
        "plan",
        "evidence",
    ]


def test_run_before_fit_raises_not_fitted() -> None:
    detector = RecordingBaseline()
    with pytest.raises(NotFittedError):
        detector.run(make_observed_day(), make_care_plan(), None)


def test_failed_fit_leaves_the_detector_not_fitted() -> None:
    class Failing(RecordingBaseline):
        def _fit(self, train, calib):  # type: ignore[no-untyped-def]
            raise RuntimeError("boom")

    detector = fitted()
    failing = Failing()
    with pytest.raises(RuntimeError):
        failing.fit([], [])
    with pytest.raises(NotFittedError):
        failing.run(make_observed_day(), make_care_plan(), None)
    assert detector.run(make_observed_day(), make_care_plan(), None) == ()


def test_refit_replaces_state() -> None:
    detector = RecordingBaseline()
    first = [make_benchmark_day(patient_id="a")]
    second = [make_benchmark_day(patient_id="b"), make_benchmark_day(patient_id="c")]
    detector.fit(first, [])
    assert detector.state == (1, 0)
    detector.fit(second, first)
    assert len(detector.fit_calls) == 2
    assert detector.state == (2, 1)


def test_fit_rejects_days_that_are_not_benchmark_days() -> None:
    detector = RecordingBaseline()
    with pytest.raises(TypeError):
        detector.fit([make_observed_day()], [])  # type: ignore[list-item]


def test_run_rejects_latent_and_benchmark_days() -> None:
    detector = fitted()
    benchmark_day = make_benchmark_day()
    plan = make_care_plan()
    with pytest.raises(LeakageError):
        detector.run(benchmark_day, plan, None)  # type: ignore[arg-type]
    with pytest.raises(LeakageError):
        detector.run(benchmark_day.latent, plan, None)  # type: ignore[arg-type]
    assert detector.run(benchmark_day.observed, plan, None) == ()


def test_run_checks_leakage_before_fitted_state() -> None:
    with pytest.raises(LeakageError):
        RecordingBaseline().run(make_benchmark_day(), make_care_plan(), None)  # type: ignore[arg-type]


def test_evidence_is_not_forwarded_to_subclass() -> None:
    assert list(inspect.signature(RecordingBaseline._run).parameters) == [
        "self",
        "day",
        "plan",
    ]
    out = (Detection(5, None, 1.0),)
    detector = fitted(output=out)
    day, plan = make_observed_day(), make_care_plan()
    assert detector.run(day, plan, None) == detector.run(day, plan, evidence_mapping())
    assert detector.run(day, plan, evidence_mapping()) == out


def test_run_rejects_non_none_label() -> None:
    detector = fitted(output=[Detection(5, AttributedCause.C1_CLINICAL, 1.0)])
    with pytest.raises(InvalidDetectionError):
        detector.run(make_observed_day(), make_care_plan(), None)


def test_run_sorts_by_time_and_rejects_non_finite_score() -> None:
    unsorted = [
        Detection(5, None, 1.0),
        Detection(3, None, 2.0),
        Detection(5, None, 0.5),
    ]
    out = fitted(output=unsorted).run(make_observed_day(), make_care_plan(), None)
    assert [(d.t_ms, d.score) for d in out] == [(3, 2.0), (5, 1.0), (5, 0.5)]
    day, plan = make_observed_day(), make_care_plan()
    for bad in (
        Detection(1, None, math.nan),
        Detection(1, None, math.inf),
        Detection(1, None, -math.inf),
        Detection(-1, None, 1.0),
        Detection(1.5, None, 1.0),  # type: ignore[arg-type]
        Detection(True, None, 1.0),
        Detection(1, None, True),  # type: ignore[arg-type]
        Detection(1, None, "x"),  # type: ignore[arg-type]
    ):
        with pytest.raises(InvalidDetectionError):
            fitted(output=[Detection(0, None, 0.0), bad]).run(day, plan, None)


def test_run_rejects_items_that_are_not_detections() -> None:
    with pytest.raises(InvalidDetectionError):
        fitted(output=[(5, None, 1.0)]).run(  # type: ignore[list-item]
            make_observed_day(), make_care_plan(), None
        )


def test_run_returns_a_tuple_snapshot() -> None:
    detector = fitted(output=[Detection(1, None, 1.0)])
    out = detector.run(make_observed_day(), make_care_plan(), None)
    assert isinstance(out, tuple)


def test_base_module_never_names_the_latent_or_ground_truth_types() -> None:
    text = (ROOT / "src" / "ralmon" / "baselines" / "base.py").read_text("utf-8")
    assert "LatentDay" not in text
    assert "GroundTruthEvent" not in text


def test_baseline_base_is_a_detector() -> None:
    assert isinstance(RecordingBaseline(), Detector)


# ---- TimingConfig -------------------------------------------------------------------------


def test_timing_config_is_frozen_and_validated() -> None:
    timing = TimingConfig(STEP_MS, 30_000, 0)
    with pytest.raises(AttributeError):
        timing.step_ms = 1  # type: ignore[misc]
    for args in ((0, 0, 0), (-1, 0, 0), (STEP_MS, -1, 0), (STEP_MS, 0, -1)):
        with pytest.raises(InvalidTimingError):
            TimingConfig(*args)
    for args in ((1.5, 0, 0), (True, 0, 0), (STEP_MS, "0", 0)):
        with pytest.raises(InvalidTimingError):
            TimingConfig(*args)  # type: ignore[arg-type]


# ---- iter_steps ---------------------------------------------------------------------------


def test_iter_steps_hand_computed() -> None:
    a, b = make_sample(t_device_ms=0), make_sample(t_device_ms=45_000)
    out = batches(make_observed_day([a, b]), TimingConfig(60_000, 30_000, 0), 120_000)
    assert [x.t_ms for x in out] == [0, 60_000, 120_000]
    assert [x.samples for x in out] == [(), (a,), (b,)]
    assert all(x.events == () for x in out)
    assert isinstance(out[0], StepBatch)


def test_iter_steps_late_arrival_waits_for_receive_time() -> None:
    late = make_sample(t_device_ms=0, t_rx_ms=100_000)
    out = batches(make_observed_day([late]), TimingConfig(60_000, 0, 0), 180_000)
    assert [(x.t_ms, x.samples) for x in out] == [
        (0, ()),
        (60_000, ()),
        (120_000, (late,)),
        (180_000, ()),
    ]


def test_iter_steps_orders_batch_by_device_time_then_seq() -> None:
    first = make_sample(t_device_ms=10, t_rx_ms=50)
    second = make_sample(t_device_ms=20, t_rx_ms=30)
    day = make_observed_day([second, first])  # sorted by receive time
    out = batches(day, TimingConfig(60_000, 0, 0), 60_000)
    assert out[1].samples == (first, second)
    s2 = make_sample(t_device_ms=10, t_rx_ms=40, seq=2)
    s1 = make_sample(t_device_ms=10, t_rx_ms=41, seq=1)
    out = batches(make_observed_day([s2, s1]), TimingConfig(60_000, 0, 0), 60_000)
    assert out[1].samples == (s1, s2)
    e2 = make_event(EventKind.DISPENSE, 10, 40, seq=2)
    e1 = make_event(EventKind.DISPENSE, 10, 41, seq=1)
    out = batches(make_observed_day([], [e2, e1]), TimingConfig(60_000, 0, 0), 60_000)
    assert out[1].events == (e1, e2)


def test_iter_steps_event_kind_order_at_equal_device_time() -> None:
    dispense = make_event(EventKind.DISPENSE, 10, 10)
    measurement = make_event(EventKind.MEASUREMENT, 10, 11)
    out = batches(
        make_observed_day([], [dispense, measurement]),
        TimingConfig(60_000, 0, 0),
        60_000,
    )
    assert out[1].events == (measurement, dispense)


def test_iter_steps_batch_inputs_puts_samples_before_events_at_equal_time() -> None:
    sample = make_sample(t_device_ms=10, t_rx_ms=12)
    event = make_event(EventKind.DISPENSE, 10, 10)
    batch = batches(
        make_observed_day([sample], [event]), TimingConfig(60_000, 0, 0), 60_000
    )[1]
    assert batch.inputs() == (sample, event)


def test_iter_steps_grid_covers_end() -> None:
    day = make_observed_day()
    timing = TimingConfig(60_000, 0, 0)
    assert [x.t_ms for x in batches(day, timing, 180_000)] == [
        0,
        60_000,
        120_000,
        180_000,
    ]
    assert all(
        x.samples == () and x.events == () for x in batches(day, timing, 180_000)
    )
    assert [x.t_ms for x in batches(day, timing, 150_000)] == [
        0,
        60_000,
        120_000,
        180_000,
    ]
    assert [x.t_ms for x in batches(day, timing, 0)] == [0]
    with pytest.raises(InvalidTimingError):
        batches(day, TimingConfig(0, 0, 0), 60_000)
    with pytest.raises(InvalidTimingError):
        batches(day, TimingConfig(-60_000, 0, 0), 60_000)
    for bad in (-1, 1.5, True):
        with pytest.raises(InvalidTimingError):
            batches(day, timing, bad)  # type: ignore[arg-type]


def test_iter_steps_grid_starts_at_the_day_start_on_the_continuing_axis() -> None:
    day_ms = 86_400_000
    s = make_sample(t_device_ms=day_ms + 5_000)
    day = make_observed_day([s], day_index=1)
    out = batches(day, TimingConfig(60_000, 0, 0), day_ms + 120_000)
    assert [x.t_ms for x in out] == [day_ms, day_ms + 60_000, day_ms + 120_000]
    assert out[1].samples == (s,)
    explicit = batches(day, TimingConfig(60_000, 0, 0), 120_000, start_ms=60_000)
    assert [x.t_ms for x in explicit] == [60_000, 120_000]


def test_iter_steps_first_batch_holds_inputs_stamped_before_the_grid() -> None:
    early = make_sample(t_device_ms=5, t_rx_ms=5)
    out = batches(
        make_observed_day([early]), TimingConfig(60_000, 0, 0), 120_000, start_ms=60_000
    )
    assert out[0].samples == (early,)


def test_iter_steps_input_is_delivered_exactly_once() -> None:
    samples = [
        make_sample(t_device_ms=t, value=float(t)) for t in range(0, 200_000, 7_000)
    ]
    events = [make_event(EventKind.INTAKE, t, t) for t in range(1_000, 200_000, 33_000)]
    out = batches(
        make_observed_day(samples, events), TimingConfig(60_000, 30_000, 0), 240_000
    )
    assert sorted(s.value for x in out for s in x.samples) == [s.value for s in samples]
    assert sum(len(x.events) for x in out) == len(events)


@st.composite
def _days(draw):  # type: ignore[no-untyped-def]
    n = draw(st.integers(0, 8))
    items = []
    for i in range(n):
        dev = draw(st.integers(0, 300_000))
        rx = dev + draw(st.integers(0, 150_000))
        seq = draw(st.one_of(st.none(), st.integers(0, 3)))
        items.append((rx, i, dev, seq))
    items.sort()
    samples = [
        make_sample(t_device_ms=dev, t_rx_ms=rx, value=float(i), seq=seq)
        for rx, i, dev, seq in items
        if i % 2 == 0
    ]
    events = [
        make_event(EventKind.INTAKE, dev, rx, seq=seq)
        for rx, i, dev, seq in items
        if i % 2 == 1
    ]
    return samples, events


@given(
    _days(),
    st.integers(0, 300_000),
    st.sampled_from([0, 30_000, 60_000]),
    st.sampled_from([30_000, 60_000]),
)
def test_iter_steps_prefix_causality_property(days, horizon, delay, step) -> None:  # type: ignore[no-untyped-def]
    samples, events = days
    timing = TimingConfig(step, delay, 0)
    end = 480_000
    full = batches(make_observed_day(samples, events), timing, end)
    cut_samples = [s for s in samples if s.t_rx_ms <= horizon]
    cut_events = [e for e in events if e.t_rx_ms <= horizon]
    cut = batches(make_observed_day(cut_samples, cut_events), timing, end)
    assert [b for b in full if b.t_ms <= horizon] == [
        b for b in cut if b.t_ms <= horizon
    ]


# ---- rising_edges and evaluation_end_ms ----------------------------------------------------


def test_rising_edges_hand_computed() -> None:
    f, t = False, True
    assert rising_edges([f, t, t, f, t]) == [1, 4]
    assert rising_edges([t, t]) == [0]
    assert rising_edges([]) == []
    assert rising_edges([f, f]) == []
    assert rising_edges(x > 1 for x in (0, 2, 3, 0, 5)) == [1, 4]


def test_evaluation_end_ms_hand_computed() -> None:
    day = make_observed_day(
        [make_sample(t_device_ms=hours(1), t_rx_ms=hours(5))],
        [make_event(t_device_ms=hours(1), t_rx_ms=hours(2))],
    )
    plan = make_care_plan(schedule=[hours(1), hours(6)])
    assert evaluation_end_ms(day, plan, hours(1)) == hours(7)
    late_input = make_observed_day([make_sample(t_device_ms=0, t_rx_ms=hours(9))])
    assert evaluation_end_ms(late_input, plan, hours(1)) == hours(10)
    assert evaluation_end_ms(make_observed_day(), make_care_plan(), hours(1)) == hours(
        1
    )
    with pytest.raises(InvalidTimingError):
        evaluation_end_ms(day, plan, -1)


def test_evaluation_end_ms_never_precedes_the_day_start() -> None:
    day = make_observed_day(day_index=2)
    assert evaluation_end_ms(day, make_care_plan(), hours(1)) == hours(49)
