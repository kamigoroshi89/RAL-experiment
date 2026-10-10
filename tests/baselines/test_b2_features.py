"""B2 feature extractor (WS06-T03), tests 1 to 4 of the task and the pins that follow from its definition.

FIXTURE-ONLY numbers. Pressures of 150 and the times of day below are arithmetic chosen so that the expected row can
be computed by hand in the comment next to it. Nothing here is a clinical value. ``step_ms`` is 60 000 and
``reorder_delay_ms`` is 0 unless a test says otherwise.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ralmon.baselines.base import StepBatch, TimingConfig, iter_steps
from ralmon.signals import MS_PER_HOUR, EventKind, Sample
from tests.baselines.conftest import make_event, make_observed_day, make_sample

ROOT = Path(__file__).resolve().parents[2]
FEATURES_SOURCE = ROOT / "src" / "ralmon" / "baselines" / "b2_features.py"

STEP = 60_000
H = MS_PER_HOUR
T_DAY = 24 * H
TIMING = TimingConfig(STEP, 0, 0)


def features() -> Any:
    """The module under test, imported at call time so that a missing module fails one test, not the collection."""
    return importlib.import_module("ralmon.baselines.b2_features")


def rows_at(
    samples: Sequence[Sample],
    events: Sequence[Any],
    schedule: Sequence[int],
    end_ms: int,
    *,
    signals: Sequence[str] = ("bp",),
    timing: TimingConfig = TIMING,
) -> list[tuple[int, dict[str, float | None]]]:
    """The feature row at every grid step up to ``end_ms``, through the shared step iterator."""
    day = make_observed_day(samples, events)
    extractor = features().FeatureExtractor(signals, schedule)
    out = []
    for batch in iter_steps(day, timing, end_ms):
        out.append((batch.t_ms, extractor.push(batch)))
    return out


def test_features_hand_computed() -> None:
    # BP 150 at 1 h, DISPENSE at 2 h, schedule [3 h]. At t = 2.5 h:
    #   last_bp = 150; age_bp_ms = 2.5 h - 1 h = 1.5 h = 5 400 000; dose_count_24h = 1 (the dispense at 2 h is in
    #   (t - 24 h, t]); since_last_dispense_ms = 0.5 h = 1 800 000; to_next_tick_ms = 3 h - 2.5 h = 1 800 000;
    #   since_last_tick_ms is undefined (no tick yet); time of day = 2.5 h = 9 000 000.
    samples = [make_sample("bp", H, value=150.0)]
    events = [make_event(EventKind.DISPENSE, 2 * H)]
    rows = rows_at(samples, events, [3 * H], 5 * H // 2)
    t, row = rows[-1]
    assert t == 5 * H // 2
    assert row == {
        "last_bp": 150.0,
        "age_bp_ms": 5_400_000,
        "dose_count_24h": 1,
        "since_last_dispense_ms": 1_800_000,
        "to_next_tick_ms": 1_800_000,
        "since_last_tick_ms": None,
        "time_of_day_ms": 9_000_000,
    }
    assert tuple(row) == features().feature_names(("bp",))


def test_features_undefined_before_first_input() -> None:
    # At t = 0 nothing has been delivered: the last value, its age and the time since the last dispense are None.
    # A count is always defined (0), the schedule is known in advance, and the time of day needs no input.
    rows = rows_at([], [], [3 * H], 0)
    assert rows[0][1] == {
        "last_bp": None,
        "age_bp_ms": None,
        "dose_count_24h": 0,
        "since_last_dispense_ms": None,
        "to_next_tick_ms": 3 * H,
        "since_last_tick_ms": None,
        "time_of_day_ms": 0,
    }


def test_features_after_the_last_scheduled_tick() -> None:
    # Schedule [3 h]. At t = 3 h the tick is "last" (since 0), and there is no next one.
    rows = dict(rows_at([], [], [3 * H], 4 * H))
    at_tick = rows[3 * H]
    assert at_tick["since_last_tick_ms"] == 0
    assert at_tick["to_next_tick_ms"] is None
    after = rows[4 * H]
    assert after["since_last_tick_ms"] == H
    assert after["to_next_tick_ms"] is None
    # one step before the tick the next tick is one step away and no tick is behind
    before = rows[3 * H - STEP]
    assert before["to_next_tick_ms"] == STEP
    assert before["since_last_tick_ms"] is None


def test_features_schedule_is_sorted_and_may_be_empty() -> None:
    rows = dict(rows_at([], [], [6 * H, 3 * H], 7 * H))
    assert rows[4 * H]["to_next_tick_ms"] == 2 * H
    assert rows[4 * H]["since_last_tick_ms"] == H
    assert rows[7 * H]["since_last_tick_ms"] == H
    empty = dict(rows_at([], [], [], H))
    assert empty[H]["to_next_tick_ms"] is None
    assert empty[H]["since_last_tick_ms"] is None


def test_features_dose_count_window_is_open_on_the_left() -> None:
    # (t - 24 h, t]: a dose at device time 0 is counted at t = 24 h - 1 step and not at t = 24 h; one at t counts.
    events = [make_event(EventKind.DISPENSE, 0), make_event(EventKind.DISPENSE, T_DAY)]
    rows = dict(rows_at([], events, [], T_DAY))
    assert rows[T_DAY - STEP]["dose_count_24h"] == 1
    assert (
        rows[T_DAY]["dose_count_24h"] == 1
    )  # the dose at 0 left the window, the dose at 24 h entered it
    assert rows[T_DAY]["since_last_dispense_ms"] == 0


def test_features_only_dispense_events_count_as_doses() -> None:
    events = [
        make_event(EventKind.MEASUREMENT, H),
        make_event(EventKind.INTAKE, H),
        make_event(EventKind.SCHEDULE_TICK, H),
    ]
    rows = dict(rows_at([], events, [], 2 * H))
    assert rows[2 * H]["dose_count_24h"] == 0
    assert rows[2 * H]["since_last_dispense_ms"] is None


def test_features_last_value_is_the_newest_by_device_time() -> None:
    # The newer device time wins even if it was delivered first; a sample with an equal device time keeps the first.
    samples = [
        make_sample("bp", 2 * H, t_rx_ms=2 * H, value=120.0),
        make_sample("bp", H, t_rx_ms=2 * H + STEP, value=999.0),  # older, arrives later
        make_sample(
            "bp", 2 * H, t_rx_ms=2 * H + 2 * STEP, value=555.0
        ),  # same device time
    ]
    rows = dict(rows_at(samples, [], [], 2 * H + 3 * STEP))
    row = rows[2 * H + 3 * STEP]
    assert row["last_bp"] == 120.0
    assert row["age_bp_ms"] == 3 * STEP


def test_features_non_finite_value_is_not_a_reading() -> None:
    samples = [
        make_sample("bp", H, value=150.0),
        make_sample("bp", 2 * H, value=float("nan")),
    ]
    rows = dict(rows_at(samples, [], [], 3 * H))
    assert rows[3 * H]["last_bp"] == 150.0
    assert rows[3 * H]["age_bp_ms"] == 2 * H


def test_features_ignore_signals_that_are_not_monitored() -> None:
    samples = [make_sample("spo2", H, value=97.0)]
    rows = dict(rows_at(samples, [], [], 2 * H, signals=("bp",)))
    assert rows[2 * H]["last_bp"] is None
    assert "last_spo2" not in rows[2 * H]


def test_features_one_pair_of_columns_per_monitored_signal() -> None:
    samples = [make_sample("hr_ecg", H, value=61.0), make_sample("spo2", H, value=97.0)]
    rows = dict(rows_at(samples, [], [], 2 * H, signals=("hr_ecg", "spo2")))
    row = rows[2 * H]
    assert row["last_hr_ecg"] == 61.0
    assert row["last_spo2"] == 97.0
    assert row["age_hr_ecg_ms"] == H
    assert tuple(row) == features().feature_names(("hr_ecg", "spo2"))


def test_feature_names_listed_for_the_default_signals() -> None:
    module = features()
    names = module.FEATURE_NAMES
    assert names == module.feature_names(module.DEFAULT_SIGNALS)
    assert names[-5:] == (
        "dose_count_24h",
        "since_last_dispense_ms",
        "to_next_tick_ms",
        "since_last_tick_ms",
        "time_of_day_ms",
    )
    assert len(set(names)) == len(names)
    doc = module.__doc__ or ""
    for name in names:
        assert name in doc, (
            f"FEATURE_NAMES entry {name!r} is not in the module docstring"
        )


def test_features_time_of_day_wraps_on_the_continuing_axis() -> None:
    extractor = features().FeatureExtractor(("bp",), [])
    row = extractor.push(StepBatch(T_DAY + 90 * STEP, (), ()))
    assert row["time_of_day_ms"] == 90 * STEP


def test_features_reject_time_going_backwards_and_bad_schedules() -> None:
    module = features()
    extractor = module.FeatureExtractor(("bp",), [])
    extractor.push(StepBatch(10 * STEP, (), ()))
    with pytest.raises(ValueError, match="backwards"):
        extractor.push(StepBatch(9 * STEP, (), ()))
    with pytest.raises(ValueError):
        module.FeatureExtractor(("bp",), [-1])
    with pytest.raises(ValueError):
        module.FeatureExtractor(("bp",), [1.5])
    with pytest.raises(ValueError):
        module.FeatureExtractor((), [])
    with pytest.raises(ValueError):
        module.FeatureExtractor(("bp", "bp"), [])


# ---- test 3: causality (Hypothesis) ----------------------------------------------------------------------------------


@st.composite
def _inputs(draw: Any) -> tuple[list[Sample], list[Any], int]:
    n_steps = 40
    samples = []
    for _ in range(draw(st.integers(0, 8))):
        device = draw(st.integers(0, n_steps)) * STEP + draw(st.sampled_from([0, 17]))
        delay = draw(st.integers(0, 3)) * STEP
        samples.append(
            make_sample(
                draw(st.sampled_from(["bp", "spo2"])),
                device,
                device + delay,
                float(draw(st.integers(40, 200))),
            )
        )
    events = []
    for _ in range(draw(st.integers(0, 5))):
        device = draw(st.integers(0, n_steps)) * STEP
        delay = draw(st.integers(0, 3)) * STEP
        events.append(
            make_event(
                draw(st.sampled_from([EventKind.DISPENSE, EventKind.MEASUREMENT])),
                device,
                device + delay,
            )
        )
    cut = draw(st.integers(0, n_steps + 3)) * STEP
    return samples, events, cut


@settings(max_examples=60, deadline=None)
@given(_inputs(), st.sampled_from([0, 2 * STEP]), st.lists(st.integers(0, 45 * STEP)))
def test_features_are_causal_property(
    data: tuple[list[Sample], list[Any], int], delay: int, schedule: list[int]
) -> None:
    samples, events, cut = data
    timing = TimingConfig(STEP, delay, 0)
    end = 45 * STEP
    full = rows_at(
        samples, events, schedule, end, signals=("bp", "spo2"), timing=timing
    )
    kept_samples = [s for s in samples if s.t_rx_ms <= cut]
    kept_events = [e for e in events if e.t_rx_ms <= cut]
    prefix = rows_at(
        kept_samples,
        kept_events,
        schedule,
        end,
        signals=("bp", "spo2"),
        timing=timing,
    )
    # the row at t uses inputs received by t only: dropping everything received after `cut` leaves every row up to
    # `cut` as it was
    assert [r for r in full if r[0] <= cut] == [r for r in prefix if r[0] <= cut]


# ---- test 4: only observed inputs and the schedule -------------------------------------------------------------------


def test_features_use_only_observed_inputs_and_schedule() -> None:
    module = features()
    init = inspect.signature(module.FeatureExtractor.__init__)
    assert list(init.parameters) == ["self", "signals", "schedule"]
    push = inspect.signature(module.FeatureExtractor.push)
    assert list(push.parameters) == ["self", "batch"]
    source = FEATURES_SOURCE.read_text(encoding="utf-8")
    for forbidden in (
        "param_values",
        "registry",
        "LatentDay",
        "GroundTruthEvent",
        "ground_truth",
        "latent",
        "normalise",
        "rank_alerts",
        "load_templates",
    ):
        assert forbidden not in source, forbidden


def test_features_module_imports_no_clinical_specification() -> None:
    tree = ast.parse(FEATURES_SOURCE.read_text(encoding="utf-8"))
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert not any(m.startswith("ralmon.spec") for m in imported), imported
    assert not any(m.startswith("ralmon.benchmark") for m in imported), imported
