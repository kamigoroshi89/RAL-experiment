"""The raw-robustness adapter and the signal grid shared by B3 and B5 (WS06-T04; the module was created by WS06-T06).

FIXTURE-ONLY numbers: the band 110 to 140 mmHg is the illustrative band of analisi section 4.1 ("illustrative,
unverified"; the fixture registry ``registry_f0.yaml`` carries it), ``step_ms`` is 60 000 and every expected value
is computed by hand in the comment next to it. None is a clinical value.

``tests/baselines/test_b5_conformal_stl.py`` already tests the unit and the independent reset of the adapter and
the held values, the impulses, the origin and the reorder delay of ``SignalGrid`` (written by WS06-T06); this file
extends rather than repeats those: every template, the parameter rules of the adapter (the task text of WS06-T04
asks for an error on a missing name, the point evaluator fills it from the registry, ADR-047 (g): the test pins the
reconciled rule), and the availability of the robot channels from the ``NODE_STATE colocated`` reports (ADR-054 (b),
accepted 2026-10-09), which the monitor applies and which the grid must apply too, so that a baseline does not hold
the level of ``presence`` across an outage.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import pytest

from ralmon.baselines.base import TimingConfig, iter_steps
from ralmon.baselines.raw_robustness import (
    GridStep,
    RawRobustnessEvaluator,
    SignalGrid,
    TemplateRawEvaluator,
    make_evaluator,
)
from ralmon.monitor import PlanFeasibilityError
from ralmon.signals import Event, EventKind, Sample
from ralmon.spec import TemplateId, TemplateInstance, load_templates
from tests.monitor.helpers import load_f0

STEP = 60_000
REGISTRY = load_f0()
LIBRARY = {t.id: t for t in load_templates(registry=REGISTRY)}


def smp(signal: str, step: int, value: float, rx_step: int | None = None) -> Sample:
    rx = step if rx_step is None else rx_step
    return Sample(signal, step * STEP, rx * STEP, float(value), None, None)


def report(
    step: int,
    colocated: Any,
    *,
    source: str = "robot",
    state: bool = True,
) -> Event:
    payload: dict[str, Any] = {"state": "active"} if state else {}
    if colocated is not None:
        payload["colocated"] = colocated
    return Event(EventKind.NODE_STATE, step * STEP, step * STEP, source, payload, None)


def dispense(step: int) -> Event:
    return Event(EventKind.DISPENSE, step * STEP, step * STEP, "dev", {}, None)


def grid_steps(
    samples: Sequence[Sample],
    events: Sequence[Event],
    last_step: int,
    *,
    delay_steps: int = 0,
) -> tuple[SignalGrid, dict[int, GridStep]]:
    """Run the harness iterator and the grid over a hand-built day (day 0, no carry-over)."""
    from ralmon.benchmark import ObservedDay

    day = ObservedDay(
        "p1",
        0,
        0,
        tuple(sorted(samples, key=lambda s: s.t_rx_ms)),
        tuple(sorted(events, key=lambda e: e.t_rx_ms)),
        "plan-1",
    )
    grid = SignalGrid(STEP, delay_ms=delay_steps * STEP)
    steps: dict[int, GridStep] = {}
    timing = TimingConfig(STEP, delay_steps * STEP, 0)
    for batch in iter_steps(day, timing, (last_step + delay_steps) * STEP):
        for step in grid.apply(batch):
            steps[step.k] = step
    return grid, steps


# ---- the adapter ---------------------------------------------------------------------------------------------------


def test_adapter_reports_template_unit() -> None:
    """Test 1: the real adapter of every template of the library reports ``Template.unit`` and is a protocol member."""
    assert len(LIBRARY) == 7
    for tid, template in LIBRARY.items():
        evaluator = make_evaluator(template, REGISTRY, STEP)
        assert evaluator.unit is template.unit, tid
        assert isinstance(evaluator, RawRobustnessEvaluator)
        assert isinstance(evaluator, TemplateRawEvaluator)


def test_adapter_step_before_reset_is_an_error() -> None:
    evaluator = make_evaluator(LIBRARY[TemplateId.RANGE], REGISTRY, STEP)
    with pytest.raises(RuntimeError, match="reset"):
        evaluator.step(0, {})


def test_adapter_done_marks_a_final_value_except_for_sched() -> None:
    """``done`` is true once an instance other than SCHED has a value (the point evaluator freezes it); SCHED keeps
    grading the lateness of the first measurement, so it is never done; ``reset`` clears it."""
    range_eval = make_evaluator(
        LIBRARY[TemplateId.RANGE], REGISTRY, STEP, "measurement"
    )
    range_eval.reset(TemplateInstance(TemplateId.RANGE, "r", {}, STEP))
    assert range_eval.done is False
    assert range_eval.step(0, {"bp": 125.0}) is None and range_eval.done is False
    assert range_eval.step(STEP, {"bp": 125.0, "meas": 1.0}) == 15.0
    assert range_eval.done is True
    range_eval.reset(TemplateInstance(TemplateId.RANGE, "r", {}, STEP))
    assert range_eval.done is False
    sched = make_evaluator(LIBRARY[TemplateId.SCHED], REGISTRY, STEP, "sched_tick")
    sched.reset(TemplateInstance(TemplateId.SCHED, "s", {}, 0))
    value = None
    for k in range(400):
        value = sched.step(
            k * STEP,
            {"meas": 1.0 if k == 1 else 0.0, "sched_tick": 1.0 if k == 0 else 0.0},
        )
        assert sched.done is False
    assert value is not None


def test_adapter_reset_gives_independent_state() -> None:
    """Test 2: two instances of one template stepped with different values do not influence each other; ``reset``
    forgets the history.

    RANGE, band 110 to 140: the margin of 125 is ``min(125 - 110, 140 - 125)`` = 15, of 152 it is ``min(42, -12)``
    = -12, of 105 it is ``min(-5, 35)`` = -5.
    """
    template = LIBRARY[TemplateId.RANGE]
    first = make_evaluator(template, REGISTRY, STEP, "measurement")
    second = make_evaluator(template, REGISTRY, STEP, "measurement")
    first.reset(TemplateInstance(TemplateId.RANGE, "a", {}, 0))
    second.reset(TemplateInstance(TemplateId.RANGE, "b", {}, STEP))
    assert first.step(0, {"bp": 125.0, "meas": 1.0}) == 15.0
    assert second.step(0, {"bp": 152.0}) is None  # its anchor is step 1
    assert second.step(STEP, {"bp": 152.0, "meas": 1.0}) == -12.0
    assert (
        first.step(STEP, {"bp": 105.0}) == 15.0
    )  # decided at its anchor, the value stays
    first.reset(TemplateInstance(TemplateId.RANGE, "a", {}, 0))  # forgets the history
    assert first.step(0, {"bp": 105.0, "meas": 1.0}) == -5.0
    assert (
        second.step(2 * STEP, {"bp": 152.0}) == -12.0
    )  # the other evaluator is untouched


def test_adapter_rejects_unknown_param_and_fills_omitted_names_from_the_registry() -> (
    None
):
    """Test 3, reconciled with the point evaluator. A parameter name that is not in ``Template.params`` is an error
    (never ignored); a name that the instance omits is read from the registry (ADR-047 (g)), so it is not an error;
    a value that differs from the registry and lies in no approved range is an error."""
    template = LIBRARY[TemplateId.RANGE]
    assert set(template.params) == {"bp_band_low", "bp_band_high"}
    evaluator = make_evaluator(template, REGISTRY, STEP, "measurement")
    with pytest.raises(PlanFeasibilityError, match="no_such_param"):
        evaluator.reset(
            TemplateInstance(TemplateId.RANGE, "r", {"no_such_param": 1.0}, 0)
        )
    # nothing omitted: band 110 to 140 from the registry, so the margin of 125 is 15
    evaluator.reset(TemplateInstance(TemplateId.RANGE, "r", {}, 0))
    assert evaluator.step(0, {"bp": 125.0, "meas": 1.0}) == 15.0
    # the value of the registry written in the instance is the same instance
    evaluator.reset(TemplateInstance(TemplateId.RANGE, "r", {"bp_band_high": 140.0}, 0))
    assert evaluator.step(0, {"bp": 125.0, "meas": 1.0}) == 15.0
    # a value that differs from the registry and has no approved range
    assert not list(REGISTRY.overrides())
    with pytest.raises(PlanFeasibilityError, match="bp_band_high"):
        evaluator.reset(
            TemplateInstance(TemplateId.RANGE, "r", {"bp_band_high": 150.0}, 0)
        )


# ---- the grid: availability of the robot channels (ADR-054 (b)) --------------------------------------------------


def _episode_day() -> tuple[list[Sample], list[Event]]:
    """Arrival at step 2, a sample at step 3, departure at 6, a sample while down at 7, return at 9, a sample at 11."""
    samples = [
        smp("presence", 3, 1.0),
        smp("presence", 7, 1.0),
        smp("presence", 11, 1.0),
    ]
    events = [
        report(2, True),
        report(6, False),
        report(9, True),
        dispense(5),
        dispense(10),
    ]
    return samples, events


def test_grid_presence_belongs_to_one_colocation_episode() -> None:
    """The level of ``presence`` is the one of the current episode: undefined (no key) from the arrival until its
    first sample, ``None`` while the channel is down, undefined again from the return until a new sample. A sample
    that arrives while the channel is down is not held after the return. ``intake`` is ``None`` while down and the
    multiplicity (``0.0``) otherwise."""
    samples, events = _episode_day()
    grid, steps = grid_steps(samples, events, 13)
    presence = {k: s.values.get("presence", "absent") for k, s in steps.items()}
    assert (
        presence[0] == presence[1] == presence[2] == "absent"
    )  # arrival: no sample yet
    assert presence[3] == presence[4] == presence[5] == 1.0
    assert presence[6] is None and presence[7] is None and presence[8] is None  # down
    assert (
        presence[9] == "absent" and presence[10] == "absent"
    )  # returned, no new sample
    assert presence[11] == presence[12] == presence[13] == 1.0
    intake = {k: s.values["intake"] for k, s in steps.items()}
    assert intake[0] == intake[5] == intake[9] == intake[13] == 0.0
    assert intake[6] is None and intake[7] is None and intake[8] is None
    assert grid.availability_reports == 3
    assert (
        grid.presence_samples_without_availability_marks == 0
    )  # the first mark precedes every sample


def test_grid_without_reports_holds_the_level_and_counts_the_samples_for_the_gate() -> (
    None
):
    """A trace with no ``colocated`` report: the level is held for the rest of the day (the documented hazard of
    ADR-054) and the gate counts the presence samples used."""
    samples, _ = _episode_day()
    grid, steps = grid_steps(samples, [dispense(5)], 13)
    assert "presence" not in steps[2].values
    assert steps[3].values["presence"] == steps[8].values["presence"] == 1.0
    assert steps[13].values["presence"] == 1.0
    assert steps[8].values["intake"] == 0.0
    assert grid.availability_reports == 0
    assert grid.presence_samples_without_availability_marks == 3


def test_grid_first_report_clears_a_level_held_from_before_it() -> None:
    """H-INIT as the monitor reads it: when the first mark of the run is a report, a level held from before it
    belongs to no episode that a report opened, and the sample used before it stays counted by the gate."""
    grid, steps = grid_steps([smp("presence", 1, 1.0)], [report(4, True)], 8)
    assert steps[1].values["presence"] == steps[3].values["presence"] == 1.0
    assert "presence" not in steps[4].values and "presence" not in steps[8].values
    assert grid.presence_samples_without_availability_marks == 1


def test_grid_a_report_goes_before_a_sample_of_the_same_device_time() -> None:
    """An availability mark is ordered before a sample of the same device time (reorder buffer of the monitor): the
    sample stamped with the time of the arrival report belongs to the new episode, the one stamped with the time of
    the departure report does not."""
    _, steps = grid_steps(
        [smp("presence", 2, 1.0), smp("presence", 5, 1.0)],
        [report(2, True), report(5, False)],
        7,
    )
    assert steps[2].values["presence"] == 1.0 and steps[4].values["presence"] == 1.0
    assert steps[5].values["presence"] is None


@pytest.mark.parametrize(
    "ignored",
    [
        report(3, True, source="dev"),  # not the robot
        report(3, 1),  # not a bool
        report(3, "true"),
        report(3, None),  # no colocated key
        Event(
            EventKind.NODE_STATE, 3 * STEP, 3 * STEP, "robot", {"state": "idle"}, None
        ),
    ],
)
def test_grid_ignores_a_node_state_that_is_not_a_robot_report(ignored: Event) -> None:
    grid, steps = grid_steps([smp("presence", 1, 1.0)], [ignored], 6)
    assert steps[3].values["presence"] == steps[6].values["presence"] == 1.0
    assert steps[3].values["intake"] == 0.0
    assert grid.availability_reports == 0


def test_grid_with_a_reorder_delay_applies_reports_on_the_device_time_grid() -> None:
    """With ``D = 2`` steps the step of a departure report is final at its device time plus ``D``, as for any input."""
    _, steps = grid_steps(
        [smp("presence", 1, 1.0)], [report(4, True), report(6, False)], 8, delay_steps=2
    )
    assert (
        "presence" not in steps[4].values
    )  # the first report clears the level of step 1
    assert steps[6].values["presence"] is None and steps[6].values["intake"] is None


def test_grid_values_never_contain_an_infinite_number() -> None:
    samples, events = _episode_day()
    _, steps = grid_steps(samples, events, 13)
    for step in steps.values():
        for name, value in step.values.items():
            assert value is None or not math.isinf(value), name
