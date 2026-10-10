"""B1, static thresholds with simple schedule logic (WS06-T02).

FIXTURE-ONLY numbers. The band 110 to 140 mmHg, the hold threshold 100 mmHg and the dose limit 2 are the illustrative
numbers of analisi section 4.1 ("illustrative, unverified"); the schedule window of 30 minutes is chosen for these tests
only. None of them is a clinical value and none is a claim of clinical validation. The plans of the tests carry the
values in the ``param_values`` of the instances (the plan is the only source of B1's clinical knowledge); the fixture
registry ``stub_registry`` only answers when a plan leaves a name out. Timing: ``step_ms = 60_000``,
``reorder_delay_ms = 0`` and ``tail_ms = 1 h`` unless a test says otherwise. Every expected detection has
``label=None`` and ``score=1.0`` (B1 is binary). Expected times are computed by hand in the comment next to them.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import re
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ralmon.attribution import Detection
from ralmon.baselines import B1StaticThresholds, Detector
from ralmon.baselines.base import BaselineBase, NotFittedError, TimingConfig
from ralmon.benchmark import ObservedDay
from ralmon.monitor import PlanFeasibilityError
from ralmon.signals import MS_PER_HOUR, Event, EventKind, Sample
from ralmon.spec import CarePlan, TemplateId, TemplateInstance
from tests.baselines.conftest import (
    StubRegistry,
    evidence_mapping,
    make_benchmark_day,
    make_care_plan,
    make_event,
    make_instance,
    make_observed_day,
    make_sample,
)
from tests.baselines.test_b3_plain_stl import REGISTRY, _monitor_violations

ROOT = Path(__file__).resolve().parents[2]
B1_SOURCE = ROOT / "src" / "ralmon" / "baselines" / "b1_static_thresholds.py"
REGISTRY_YAML = ROOT / "configs" / "registry" / "hypertension.yaml"

STEP = 60_000
T_DAY = 24 * MS_PER_HOUR
WINDOW_MS = 1_800_000  # FIXTURE-ONLY: 30 min, for these tests only

BAND = {"bp_band_low": 110.0, "bp_band_high": 140.0}  # illustrative, unverified
HOLD = {"bp_hold_threshold": 100.0}  # illustrative, unverified
COUNT = {"dose_max_24h": 2.0}  # illustrative, unverified
SCHED = {"sched_window": float(WINDOW_MS)}  # FIXTURE-ONLY


def hours(h: float) -> int:
    return round(h * MS_PER_HOUR)


def b1_module() -> Any:
    """The module under test, imported at call time so that a missing module fails one test, not the collection."""
    return importlib.import_module("ralmon.baselines.b1_static_thresholds")


# ---- builders ---------------------------------------------------------------------------------------------------------


def bp(
    t_ms: int, value: float, rx: int | None = None, seq: int | None = None
) -> Sample:
    return make_sample("bp", t_ms, rx, value, seq)


def dispense(t_ms: int, rx: int | None = None, seq: int | None = None) -> Event:
    return make_event(EventKind.DISPENSE, t_ms, rx, seq=seq)


def measurement(t_ms: int, rx: int | None = None) -> Event:
    return make_event(EventKind.MEASUREMENT, t_ms, rx)


def day_of(
    samples: Iterable[Sample] = (),
    events: Iterable[Event] = (),
    *,
    day_index: int = 0,
) -> ObservedDay:
    return make_observed_day(tuple(samples), tuple(events), day_index=day_index)


def rec(template: TemplateId, params: dict[str, float]) -> TemplateInstance:
    """A parameter record: the instance of a template with ``anchor_ms`` None."""
    return make_instance(template, f"{template.value}-record", params)


def sched(anchor_ms: int, params: dict[str, float] | None = None) -> TemplateInstance:
    return make_instance(
        TemplateId.SCHED,
        f"sched@{anchor_ms}",
        SCHED if params is None else params,
        anchor_ms,
    )


def plan_of(*instances: TemplateInstance, schedule: Sequence[int] = ()) -> CarePlan:
    return make_care_plan(instances, schedule)


def full_plan(*anchors: int) -> CarePlan:
    """All four rules active; the SCHED anchors are listed in the schedule of the plan as well."""
    return plan_of(
        rec(TemplateId.RANGE, BAND),
        rec(TemplateId.HOLD, HOLD),
        rec(TemplateId.COUNT, COUNT),
        *(sched(a) for a in anchors),
        schedule=anchors,
    )


def make_b1(
    *,
    delay_ms: int = 0,
    tail_ms: int = hours(1),
    registry: Any = None,
    fit: bool = True,
) -> B1StaticThresholds:
    b1 = B1StaticThresholds(
        timing=TimingConfig(STEP, delay_ms, tail_ms), registry=registry
    )
    if fit:
        b1.fit([], [])
    return b1


def run(
    b1: B1StaticThresholds,
    day: ObservedDay,
    plan: CarePlan,
    evidence: Any = None,
) -> list[Detection]:
    return list(b1.run(day, plan, evidence))


def times(detections: Iterable[Detection]) -> list[int]:
    return [d.t_ms for d in detections]


def check_binary(detections: Iterable[Detection]) -> None:
    for d in detections:
        assert d.label is None and d.score == 1.0


# ---- 1, 2 R1: the band ------------------------------------------------------------------------------------------------


def test_b1_band_rule_hand_computed() -> None:
    """Test 1. 152 is above 140, 125 is inside, 105 is below 110: detections at 1 h and 3 h only."""
    day = day_of([bp(hours(1), 152.0), bp(hours(2), 125.0), bp(hours(3), 105.0)])
    out = run(make_b1(), day, plan_of(rec(TemplateId.RANGE, BAND)))
    assert times(out) == [3_600_000, 10_800_000]
    check_binary(out)


def test_b1_band_limits_are_inclusive() -> None:
    """Test 2. The band is closed: exactly 110 and exactly 140 are in band (the direction of the template)."""
    day = day_of([bp(hours(1), 110.0), bp(hours(2), 140.0)])
    assert run(make_b1(), day, plan_of(rec(TemplateId.RANGE, BAND))) == []
    just_out = day_of([bp(hours(1), 109.99), bp(hours(2), 140.01)])
    assert times(run(make_b1(), just_out, plan_of(rec(TemplateId.RANGE, BAND)))) == [
        hours(1),
        hours(2),
    ]


# ---- 3 R2: the hold rule ------------------------------------------------------------------------------------------------


def test_b1_hold_rule_uses_last_held_bp() -> None:
    """Test 3. BP 95 at 3.5 h then a dispense at 4 h: the band rule detects 95 at 12 600 000, the hold rule
    (95 < 100) the dispense at 14 400 000. A dispense with no pressure delivered before it gives no hold detection."""
    plan = plan_of(rec(TemplateId.RANGE, BAND), rec(TemplateId.HOLD, HOLD))
    day = day_of([bp(hours(3.5), 95.0)], [dispense(hours(4))])
    out = run(make_b1(), day, plan)
    assert times(out) == [12_600_000, 14_400_000]
    check_binary(out)
    assert run(make_b1(), day_of([], [dispense(hours(4))]), plan) == []


def test_b1_hold_threshold_is_strict_and_the_last_value_counts() -> None:
    """Exactly the threshold is not below it; a later in-range value replaces the earlier low one (only the last
    delivered pressure counts, there is no look-back window)."""
    plan = plan_of(rec(TemplateId.HOLD, HOLD))
    at_threshold = day_of([bp(hours(1), 100.0)], [dispense(hours(2))])
    assert run(make_b1(), at_threshold, plan) == []
    replaced = day_of([bp(hours(1), 90.0), bp(hours(2), 120.0)], [dispense(hours(3))])
    assert run(make_b1(), replaced, plan) == []
    low_last = day_of([bp(hours(1), 120.0), bp(hours(2), 90.0)], [dispense(hours(3))])
    assert times(run(make_b1(), low_last, plan)) == [hours(3)]


def test_b1_hold_pressure_with_the_device_time_of_the_dispense_is_the_pre_dose_value() -> (
    None
):
    """A pressure stamped like the dispense is delivered before it (``StepBatch.inputs``): the hold rule sees it."""
    plan = plan_of(rec(TemplateId.HOLD, HOLD))
    day = day_of([bp(hours(2), 90.0)], [dispense(hours(2))])
    assert times(run(make_b1(), day, plan)) == [hours(2)]


# ---- 4, 5, 6 R3: the scheduled measurement ------------------------------------------------------------------------------


def test_b1_schedule_rule_missed_measurement() -> None:
    """Test 4. SCHED anchored at 6 h with a 30 min window, nothing in [6 h, 6.5 h]: one detection at 23 400 000, the
    first step with ``t >= anchor + window``. Pressures outside the window (5.9 h, 6.6 h) do not count."""
    plan = plan_of(sched(hours(6)), schedule=[hours(6)])
    day = day_of([bp(hours(5.9), 125.0), bp(hours(6.6), 125.0)])
    out = run(make_b1(), day, plan)
    assert times(out) == [23_400_000]
    check_binary(out)
    # a pressure or a MEASUREMENT event inside the window satisfies the rule
    inside = day_of([bp(hours(6.25), 125.0)])
    assert run(make_b1(), inside, plan) == []
    event_inside = day_of([], [measurement(hours(6.25))])
    assert run(make_b1(), event_inside, plan) == []


def test_b1_schedule_rule_boundary() -> None:
    """Test 5. The window is closed: a pressure at exactly 23 400 000 satisfies it; at 23 400 001 it does not, and the
    detection is at 23 400 000. A MEASUREMENT event counts like a pressure sample."""
    plan = plan_of(sched(hours(6)), schedule=[hours(6)])
    assert run(make_b1(), day_of([bp(23_400_000, 125.0)]), plan) == []
    assert times(run(make_b1(), day_of([bp(23_400_001, 125.0)]), plan)) == [23_400_000]
    assert run(make_b1(), day_of([], [measurement(23_400_000)]), plan) == []
    assert times(run(make_b1(), day_of([], [measurement(23_400_001)]), plan)) == [
        23_400_000
    ]
    # the lower end of the window is closed too
    assert run(make_b1(), day_of([bp(hours(6), 125.0)]), plan) == []
    assert times(run(make_b1(), day_of([bp(hours(6) - 1, 125.0)]), plan)) == [
        23_400_000
    ]


def test_b1_schedule_rule_waits_for_reorder_delay() -> None:
    """Test 6. With ``reorder_delay_ms = 120 000`` the rule decides at the first step with ``t - D >= deadline``:
    23 520 000. A pressure at 23 400 000 is delivered at that very step, before the deadline is evaluated."""
    plan = plan_of(sched(hours(6)), schedule=[hours(6)])
    b1 = make_b1(delay_ms=120_000)
    assert times(run(b1, day_of([]), plan)) == [23_520_000]
    assert run(b1, day_of([bp(23_400_000, 125.0)]), plan) == []
    assert times(run(b1, day_of([bp(23_400_001, 125.0)]), plan)) == [23_520_000]


def test_b1_schedule_rule_each_instance_has_its_own_window() -> None:
    plan = plan_of(
        sched(hours(6), {"sched_window": 1_800_000.0}),
        sched(hours(9), {"sched_window": 3_600_000.0}),
        schedule=[hours(6), hours(9)],
    )
    day = day_of([bp(hours(6.2), 125.0)])
    # 6 h is covered; 9 h with a 1 h window is detected at 10 h
    assert times(run(make_b1(), day, plan)) == [hours(10)]


def test_b1_schedule_rule_decides_even_if_the_plan_schedule_is_shorter() -> None:
    """The deadline is evaluated whatever the tail of the timing and the ticks of ``plan.schedule``: B1 extends the
    run to its own last deadline (a plan whose instance is missing from its schedule must not silence B1)."""
    plan = plan_of(sched(hours(6)))  # empty schedule
    assert times(run(make_b1(tail_ms=0), day_of([]), plan)) == [23_400_000]


def test_b1_schedule_rule_ignores_an_anchor_outside_the_day() -> None:
    """Empty carry-over (ADR-061): an instance anchored in another day is not checked on this one."""
    other_day = plan_of(sched(T_DAY + hours(6)), schedule=[])
    assert run(make_b1(), day_of([]), other_day) == []
    this_day = plan_of(sched(T_DAY + hours(6)))
    assert times(run(make_b1(), day_of([], day_index=1), this_day)) == [
        T_DAY + 23_400_000
    ]


def test_b1_schedule_rule_detects_after_midnight_where_the_monitor_ends_pending() -> (
    None
):
    """OPEN DECISION (WS06-T04, midnight), pinned for B1. A tick at 23:30 with a 1 h window closes at 00:30 of the next
    day: B1 detects at that step (``T_DAY + 1 800 000``), it is not clipped at the closing step of the day."""
    plan = plan_of(sched(hours(23.5), {"sched_window": 3_600_000.0}))
    assert times(run(make_b1(tail_ms=0), day_of([]), plan)) == [T_DAY + 1_800_000]


def test_b1_schedule_rule_late_measurement_gets_no_credit() -> None:
    """A measurement stamped inside the window but received after its step was final is late and is dropped, as in
    the monitor: it does not satisfy the rule."""
    plan = plan_of(sched(hours(6)), schedule=[hours(6)])
    late = day_of([bp(hours(6.1), 125.0, rx=hours(6.4))])
    b1 = make_b1()
    assert times(run(b1, late, plan)) == [23_400_000]
    assert b1.run_stats is not None and b1.run_stats.late_inputs == 1


# ---- 7, 8 R4: the dose limit --------------------------------------------------------------------------------------------


def test_b1_dose_limit_rule_hand_computed() -> None:
    """Test 7. Limit 2, dispenses at 1 h, 2 h, 3 h, 4 h: the trailing count is 1, 2, 3, 4 and exceeds the limit at
    3 h (10 800 000) and 4 h (14 400 000)."""
    day = day_of([], [dispense(hours(h)) for h in (1, 2, 3, 4)])
    out = run(make_b1(), day, plan_of(rec(TemplateId.COUNT, COUNT)))
    assert times(out) == [10_800_000, 14_400_000]
    check_binary(out)


def test_b1_dose_window_is_left_open_24h() -> None:
    """Test 8. The window of a dispense at ``t`` is ``(t - 24 h, t]``."""
    plan = plan_of(rec(TemplateId.COUNT, COUNT))

    def detections(*at: int) -> list[int]:
        return times(run(make_b1(), day_of([], [dispense(t) for t in at]), plan))

    assert detections(0, hours(12), hours(25)) == []  # at 25 h: 12 h and 25 h
    assert (
        detections(0, hours(1), hours(24)) == []
    )  # at 24 h: the dose at 0 is outside, 1 h and 24 h count
    assert detections(0, hours(1), hours(2)) == [hours(2)]  # at 2 h: 0, 1 h and 2 h
    # at 24 h - 1 ms the dose at 0 still counts (3 doses); the alarm is raised at the delivery step, 24 h
    assert detections(0, hours(1), hours(24) - 1) == [hours(24)]


# ---- 9, 10 what the plan holds ------------------------------------------------------------------------------------------


def _rich_day() -> ObservedDay:
    """Out-of-band pressures, a low pressure before a dispense, three dispenses and no measurement near the tick."""
    return day_of(
        [bp(hours(1), 152.0), bp(hours(2), 95.0)],
        [dispense(hours(3)), dispense(hours(4)), dispense(hours(5))],
    )


def test_b1_rule_inactive_without_plan_instance() -> None:
    """Test 9. A rule runs only if the plan holds its instance; the plan is the only source of clinical knowledge."""
    day = _rich_day()
    anchors = (hours(8),)
    everything = full_plan(*anchors)
    base = run(make_b1(registry=StubRegistry()), day, everything)
    # R1 (152, 95), R2 (95 < 100 at 3 h, 4 h, 5 h), R3 (8 h + 30 min), R4 (3rd dispense at 5 h)
    assert times(base) == [
        hours(1),
        hours(2),
        hours(3),
        hours(4),
        hours(5),
        hours(5),
        23_400_000 + hours(2),
    ]
    for dropped, gone in (
        (TemplateId.RANGE, [hours(1), hours(2)]),
        (TemplateId.HOLD, [hours(3), hours(4), hours(5)]),
        (TemplateId.COUNT, [hours(5)]),
        (TemplateId.SCHED, [23_400_000 + hours(2)]),
    ):
        plan = plan_of(
            *(i for i in everything.instances if i.template is not dropped),
            schedule=anchors,
        )
        expected = list(base)
        for t in gone:
            expected.remove(next(d for d in expected if d.t_ms == t))
        got = run(make_b1(registry=StubRegistry()), day, plan)
        assert times(got) == times(expected), dropped
    assert run(make_b1(), day, plan_of(schedule=anchors)) == []


def test_b1_excludes_window_and_cross_signal_templates() -> None:
    """Test 10. RESP, SYS and INT instances change nothing: B1 has no response, cuff-health or presence logic."""
    day = day_of(
        [
            bp(hours(1), 152.0),
            bp(hours(2), 125.0),
            make_sample("cuff_health", hours(2), None, 0.0),
            make_sample("inflation_ms", hours(2), None, 1_000.0),
            make_sample("presence", hours(3), None, 0.0),
        ],
        [measurement(hours(2)), dispense(hours(3)), dispense(hours(4))],
    )
    without = full_plan(hours(8))
    extra = (
        rec(
            TemplateId.RESP,
            {"delta1": 3_600_000.0, "delta2": 7_200_000.0, "delta_resp": 7.5},
        ),
        rec(TemplateId.SYS, {"cuff_inflation_min": 15_000.0}),
        rec(TemplateId.INT, {"int_window": 300_000.0}),
        make_instance(TemplateId.INT, "int@3h", {"int_window": 300_000.0}, hours(3)),
    )
    with_extra = plan_of(*without.instances, *extra, schedule=without.schedule)
    a = run(make_b1(), day, without)
    b = run(make_b1(), day, with_extra)
    assert a == b and a  # the day has detections, and the extra instances change none


# ---- 11, 12, 13, 14 evidence, fit, reads, names ----------------------------------------------------------------------------


def test_b1_ignores_evidence_and_never_labels() -> None:
    """Test 11. Identical output with and without an ``EvidenceVector``; every label is None."""
    plan = full_plan(hours(8))
    b1 = make_b1()
    plain = run(b1, _rich_day(), plan)
    with_evidence = run(b1, _rich_day(), plan, evidence_mapping())
    assert plain == with_evidence and plain
    assert all(d.label is None for d in plain + with_evidence)
    check_binary(plain)


def test_b1_fit_reads_no_days() -> None:
    """Test 12. B1 has no fitted state: ``fit`` reads no day (not even the observed trace) and ``fit([], [])`` is valid."""
    b1 = make_b1(fit=False)
    with pytest.raises(NotFittedError):
        run(b1, day_of([]), full_plan())
    train = make_benchmark_day([bp(0, 125.0)], [], patient_id="t")
    calib = make_benchmark_day([bp(0, 130.0)], [], patient_id="c")
    b1.fit([train], [calib])
    assert b1.access_log.records == () and b1.access_log.denied == ()
    assert run(b1, day_of([bp(hours(1), 152.0)]), full_plan()) != []
    assert b1.access_log.records == () and b1.access_log.denied == ()
    fresh = make_b1()
    assert run(fresh, day_of([bp(hours(1), 152.0)]), full_plan()) != []


def test_b1_reads_only_declared_names(stub_registry: StubRegistry) -> None:
    """Test 13. The names read during ``run`` include the five role parameters and are a subset of the parameters of
    the RANGE, HOLD, SCHED and COUNT instances; no scale, priority, RESP, SYS or INT name is read."""
    range_params = {**BAND, "scale_range": 20.0, "priority_range": 2.0}
    hold_params = {**HOLD, "hold_lookback": 3_600_000.0, "scale_hold": 10.0}
    count_params = {**COUNT, "dose_min_day_end": 2.0, "scale_count": 1.0}
    sched_params = {**SCHED, "scale_sched": 1_800_000.0, "priority_sched": 3.0}
    resp_params = {"delta1": 3_600_000.0, "delta2": 7_200_000.0, "delta_resp": 7.5}
    sys_params = {"cuff_inflation_min": 15_000.0, "scale_sys": 15_000.0}
    int_params = {"int_window": 300_000.0, "priority_int": 3.0}
    plan = plan_of(
        rec(TemplateId.RANGE, range_params),
        rec(TemplateId.HOLD, hold_params),
        rec(TemplateId.COUNT, count_params),
        sched(hours(6), sched_params),
        rec(TemplateId.RESP, resp_params),
        rec(TemplateId.SYS, sys_params),
        rec(TemplateId.INT, int_params),
        schedule=[hours(6)],
    )
    b1 = make_b1(registry=stub_registry)
    assert run(b1, _rich_day(), plan)
    names = b1.read_log.all_names()
    roles = set(b1_module().ROLE_PARAMETERS.values())
    assert roles == {
        "bp_band_low",
        "bp_band_high",
        "bp_hold_threshold",
        "sched_window",
        "dose_max_24h",
    }
    assert roles <= names, roles - names
    allowed = (
        set(range_params) | set(hold_params) | set(count_params) | set(sched_params)
    )
    assert names <= allowed, names - allowed
    forbidden = (
        set(resp_params)
        | set(sys_params)
        | set(int_params)
        | {
            "scale_range",
            "priority_range",
            "scale_hold",
            "scale_count",
            "scale_sched",
            "priority_sched",
        }
    )
    assert not names & forbidden, names & forbidden
    assert not any(n.startswith("bounds:") for n in names)
    assert b1.access_log.records == () and b1.access_log.denied == ()


def test_b1_registry_is_read_only_for_a_name_the_plan_leaves_out(
    stub_registry: StubRegistry,
) -> None:
    """The proposed method fills an omitted name from the registry (ADR-047 (g)); so does B1, and logs it."""
    plan = plan_of(rec(TemplateId.RANGE, {}), rec(TemplateId.HOLD, HOLD))
    b1 = make_b1(registry=stub_registry)
    out = run(b1, day_of([bp(hours(1), 152.0), bp(hours(2), 125.0)]), plan)
    assert times(out) == [hours(1)]  # the band comes from the registry
    assert {"bp_band_low", "bp_band_high"} <= b1.read_log.registry_reads
    assert "bp_hold_threshold" not in b1.read_log.registry_reads  # the plan had it
    # a value in the plan wins over the registry
    narrow = plan_of(
        rec(TemplateId.RANGE, {"bp_band_low": 120.0, "bp_band_high": 130.0})
    )
    assert times(run(b1, day_of([bp(hours(1), 135.0)]), narrow)) == [hours(1)]


def test_b1_missing_parameter_without_registry_is_an_error_not_a_silent_rule() -> None:
    """A rule whose parameter the plan leaves out and no registry gives is a plan error that names the parameter;
    a baseline that silently switched the rule off would be a straw man."""
    b1 = make_b1()
    with pytest.raises(PlanFeasibilityError, match="bp_band_high"):
        run(
            b1,
            day_of([bp(hours(1), 152.0)]),
            plan_of(rec(TemplateId.RANGE, {"bp_band_low": 110.0})),
        )
    with pytest.raises(PlanFeasibilityError, match="sched_window"):
        run(b1, day_of([]), plan_of(sched(hours(6), {})))


def test_b1_plan_errors() -> None:
    b1 = make_b1()
    day = day_of([bp(hours(1), 152.0)])
    with pytest.raises(PlanFeasibilityError, match="more than one"):
        run(
            b1,
            day,
            plan_of(
                rec(TemplateId.RANGE, BAND), make_instance(TemplateId.RANGE, "r2", BAND)
            ),
        )
    with pytest.raises(PlanFeasibilityError, match="anchor"):
        run(b1, day, plan_of(make_instance(TemplateId.RANGE, "r@1", BAND, hours(1))))
    with pytest.raises(PlanFeasibilityError, match="band"):
        run(
            b1,
            day,
            plan_of(
                rec(TemplateId.RANGE, {"bp_band_low": 140.0, "bp_band_high": 110.0})
            ),
        )
    with pytest.raises(PlanFeasibilityError, match="window"):
        run(b1, day, plan_of(sched(hours(6), {"sched_window": -1.0})))
    with pytest.raises(PlanFeasibilityError, match="multiple"):
        run(b1, day, plan_of(sched(hours(6), {"sched_window": 90_000.0})))  # 1.5 steps
    with pytest.raises(PlanFeasibilityError, match="dose_max_24h"):
        run(b1, day, plan_of(rec(TemplateId.COUNT, {"dose_max_24h": float("nan")})))


def test_b1_parameter_names_exist_in_registry_yaml() -> None:
    """Test 14. Every registry entry name that the module references as a string exists, as a set entry, in
    ``configs/registry/hypertension.yaml`` (an ``unset`` name does not count)."""
    text = REGISTRY_YAML.read_text(encoding="utf-8")
    entries = set(re.findall(r"^  - name: ([a-z0-9_]+)\s*$", text, flags=re.MULTILINE))
    assert "bp_band_low" in entries
    module = b1_module()
    for role, name in module.ROLE_PARAMETERS.items():
        assert name in entries, (role, name)
    # every string constant of the source that looks like a registry name (lower case words joined by underscores)
    # is one of them: no name is spelt in the code without being a role
    tree = ast.parse(B1_SOURCE.read_text(encoding="utf-8"))
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    looks_like_a_name = re.compile(r"[a-z]+(_[a-z0-9]+)+")
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
            and looks_like_a_name.fullmatch(node.value)
        ):
            assert node.value in entries, node.value


# ---- 15, 16 properties ----------------------------------------------------------------------------------------------------


@settings(max_examples=60, deadline=None)
@given(
    bps=st.lists(
        st.tuples(st.integers(0, 40), st.integers(60, 200), st.integers(0, 3)),
        max_size=8,
    ),
    events=st.lists(
        st.tuples(
            st.sampled_from([EventKind.MEASUREMENT, EventKind.DISPENSE]),
            st.integers(0, 40),
            st.integers(0, 3),
        ),
        max_size=8,
    ),
    cut=st.integers(0, 50),
    delay_steps=st.integers(0, 2),
)
def test_b1_is_causal_property(
    bps: list[tuple[int, int, int]],
    events: list[tuple[EventKind, int, int]],
    cut: int,
    delay_steps: int,
) -> None:
    """Test 15. The detections with ``t_ms <= T`` are the same for the full day and for the day truncated to the
    inputs received by ``T`` (arrival delays of up to three steps; four rules active)."""
    samples = [bp(s * STEP, float(v), (s + d) * STEP) for s, v, d in bps]
    items = [make_event(k, s * STEP, (s + d) * STEP) for k, s, d in events]
    horizon = cut * STEP
    plan = plan_of(
        rec(TemplateId.RANGE, BAND),
        rec(TemplateId.HOLD, HOLD),
        rec(TemplateId.COUNT, COUNT),
        sched(5 * STEP, {"sched_window": 5.0 * STEP}),
        sched(20 * STEP, {"sched_window": 10.0 * STEP}),
        schedule=[5 * STEP, 20 * STEP],
    )
    b1 = make_b1(delay_ms=delay_steps * STEP, tail_ms=5 * STEP)
    full = [d for d in b1.run(day_of(samples, items), plan, None) if d.t_ms <= horizon]
    cut_day = day_of(
        [s for s in samples if s.t_rx_ms <= horizon],
        [e for e in items if e.t_rx_ms <= horizon],
    )
    truncated = [d for d in b1.run(cut_day, plan, None) if d.t_ms <= horizon]
    assert full == truncated


@settings(max_examples=60, deadline=None)
@given(
    values=st.lists(st.tuples(st.integers(0, 80), st.integers(110, 140)), max_size=10),
    meas=st.lists(st.integers(0, 80), max_size=5),
    delay_steps=st.integers(0, 2),
)
def test_b1_in_band_only_days_are_silent_property(
    values: list[tuple[int, int]], meas: list[int], delay_steps: int
) -> None:
    """Test 16. Pressures drawn inside the (closed) band, no dispenses and no SCHED instance give an empty result."""
    day = day_of(
        [bp(s * STEP, float(v)) for s, v in values],
        [measurement(s * STEP) for s in meas],
    )
    plan = plan_of(
        rec(TemplateId.RANGE, BAND),
        rec(TemplateId.HOLD, HOLD),
        rec(TemplateId.COUNT, COUNT),
    )
    assert run(make_b1(delay_ms=delay_steps * STEP), day, plan) == []


# ---- what the harness and the monitor do, pinned ------------------------------------------------------------------------------


def test_b1_drops_a_late_input_like_the_monitor() -> None:
    """An out-of-band pressure received after its step was final (``t_rx`` after ``ceil(t / T_s) * T_s + D``) is late
    and is dropped, and is counted; received on time it is detected."""
    plan = plan_of(rec(TemplateId.RANGE, BAND))
    b1 = make_b1()
    late = day_of([bp(hours(2), 152.0, rx=hours(2) + 10 * STEP)])
    assert run(b1, late, plan) == []
    assert b1.run_stats is not None and b1.run_stats.late_inputs == 1
    on_time = day_of([bp(hours(2), 152.0, rx=hours(2))])
    assert times(run(b1, on_time, plan)) == [hours(2)]
    assert b1.run_stats.late_inputs == 0
    # one step after its step was final is late, exactly at the watermark is on time (``ceil(t / T_s) * T_s + D``)
    one_step = day_of([bp(hours(2), 152.0, rx=hours(2) + STEP)])
    assert run(b1, one_step, plan) == []
    assert b1.run_stats.late_inputs == 1
    at_watermark = day_of([bp(hours(2) + 1, 152.0, rx=hours(2) + STEP)])
    assert times(run(b1, at_watermark, plan)) == [hours(2) + STEP]
    # received exactly at the watermark of its step with D = 2 steps: on time
    delayed = make_b1(delay_ms=2 * STEP)
    edge = day_of([bp(hours(2), 152.0, rx=hours(2) + 2 * STEP)])
    assert times(run(delayed, edge, plan)) == [hours(2) + 2 * STEP]


def test_b1_input_stamped_before_the_day_raises_no_alarm_but_is_state() -> None:
    """On day 1 a pressure stamped before the start of the day (received at its start) is not part of the day (empty
    carry-over, ADR-061): no band detection. It is a delivered value, so the hold rule sees it as the last pressure, and
    a dispense stamped before the day counts in the 24 h window of a later one."""
    t0 = T_DAY
    plan = plan_of(
        rec(TemplateId.RANGE, BAND),
        rec(TemplateId.HOLD, HOLD),
        rec(TemplateId.COUNT, COUNT),
    )
    early_bp = bp(t0 - 3 * STEP, 152.0, rx=t0)
    day = day_of([early_bp], [dispense(t0 + hours(1))], day_index=1)
    assert (
        run(make_b1(), day, plan) == []
    )  # 152 is above the band but not part of the day; hold 152 >= 100
    low = day_of(
        [bp(t0 - 3 * STEP, 90.0, rx=t0)], [dispense(t0 + hours(1))], day_index=1
    )
    assert times(run(make_b1(), low, plan)) == [t0 + hours(1)]  # the hold rule only
    doses = day_of(
        [],
        [dispense(t0 - STEP, rx=t0), dispense(t0 + hours(1)), dispense(t0 + hours(2))],
        day_index=1,
    )
    assert times(run(make_b1(), doses, plan)) == [
        t0 + hours(2)
    ]  # the dose before the day is counted, not alarmed


def test_b1_does_not_deduplicate_inputs() -> None:
    """KNOWN ASYMMETRY (asymmetry (b) of ``base.py``), pinned. The monitor deduplicates by (source, name, seq); the
    harness does not. A pressure delivered twice raises two alarms, and two doses each delivered twice are four doses,
    so B1 raises a dose alarm that the monitor does not."""
    plan = plan_of(rec(TemplateId.RANGE, BAND), rec(TemplateId.COUNT, COUNT))
    twice = day_of([bp(hours(1), 152.0, seq=7), bp(hours(1), 152.0, seq=7)])
    assert times(run(make_b1(), twice, plan)) == [hours(1), hours(1)]
    doses = day_of(
        [],
        [
            dispense(hours(1), seq=1),
            dispense(hours(1), seq=1),
            dispense(hours(2), seq=2),
            dispense(hours(2), seq=2),
        ],
    )
    # counts at the four deliveries: 1, 2, 3, 4; the limit is 2
    assert times(run(make_b1(), doses, plan)) == [hours(2), hours(2)]
    first, result = _monitor_violations(doses, make_care_plan(), 0, [TemplateId.COUNT])
    assert first == {} and result.stats.duplicate_count == 2


def test_b1_ignores_a_pressure_that_is_not_a_number() -> None:
    """A NaN is not a reading: no alarm, not the held pressure, no credit for a scheduled measurement."""
    plan = plan_of(
        rec(TemplateId.RANGE, BAND),
        rec(TemplateId.HOLD, HOLD),
        sched(hours(6)),
        schedule=[hours(6)],
    )
    b1 = make_b1()
    day = day_of(
        [bp(hours(2), 125.0), bp(hours(3), float("nan")), bp(hours(6.1), float("nan"))],
        [dispense(hours(4))],
    )
    assert times(run(b1, day, plan)) == [23_400_000]
    assert b1.run_stats is not None and b1.run_stats.non_finite_samples == 2


def test_b1_ignores_other_signals_and_event_kinds() -> None:
    plan = full_plan(hours(6))
    day = day_of(
        [
            make_sample("spo2", hours(1), None, 300.0),
            make_sample("hr", hours(6.1), None, 70.0),
        ],
        [
            make_event(EventKind.INTAKE, hours(2)),
            make_event(EventKind.INTAKE, hours(3)),
            make_event(EventKind.INTAKE, hours(4)),
            make_event(EventKind.MEASUREMENT_MISSED, hours(6.1)),
        ],
    )
    assert times(run(make_b1(), day, plan)) == [23_400_000]


# ---- the monitor and B1 agree on the threshold rules ------------------------------------------------------------------------


def _agreement_day() -> tuple[CarePlan, ObservedDay]:
    def m(h: int, mm: int = 0) -> int:
        return (60 * h + mm) * 60_000

    monitor_plan = make_care_plan(
        [
            make_instance(TemplateId.SCHED, "s8", {}, m(8)),
            make_instance(TemplateId.SCHED, "s14", {}, m(14)),
            make_instance(TemplateId.COUNT, "c-end", {}, T_DAY),
        ]
    )
    samples = [
        bp(m(8), 150.0),
        bp(m(9, 10), 95.0),
        bp(m(10), 130.0),
        bp(m(11, 30), 118.0),
        bp(m(14, 40), 125.0),
    ]
    events = [
        measurement(m(8)),
        dispense(m(8, 5)),
        measurement(m(9, 10)),
        dispense(m(9, 15)),
        dispense(m(10, 5)),
        measurement(m(10)),
        measurement(m(11, 30)),
        measurement(m(14, 40)),
    ]
    return monitor_plan, day_of(samples, events)


@pytest.mark.parametrize("delay_steps", [0, 2])
def test_b1_threshold_rules_agree_with_the_monitor(delay_steps: int) -> None:
    """On a hand-built day the first VIOLATED record of each RANGE, HOLD, COUNT and SCHED instance of ``run_offline``
    and the detections of B1 are at the same times (the monitor's step plus ``D``). The registry is the fixture
    registry F0: the plan holds empty parameter records and B1 reads the five values from it, as the monitor does."""
    monitor_plan, day = _agreement_day()
    first, _ = _monitor_violations(
        day,
        monitor_plan,
        delay_steps,
        (TemplateId.RANGE, TemplateId.HOLD, TemplateId.COUNT, TemplateId.SCHED),
    )
    # range@8:00 (150), range@9:10 (95), hold@9:15 (95), count@10:05 (3rd dose), sched@14:00 (nothing by 14:30)
    assert len(first) == 5, first
    b1_plan = make_care_plan(
        [
            *monitor_plan.instances,
            rec(TemplateId.RANGE, {}),
            rec(TemplateId.HOLD, {}),
            rec(TemplateId.COUNT, {}),
        ]
    )
    b1 = make_b1(delay_ms=delay_steps * STEP, tail_ms=hours(3), registry=REGISTRY)
    out = run(b1, day, b1_plan)
    assert sorted(times(out)) == sorted(t + delay_steps * STEP for t in first.values())
    check_binary(out)


def test_b1_blind_spots_against_the_monitor_are_pinned() -> None:
    """KNOWN DIFFERENCES, by the task text: two threshold-type violations that the monitor reports and B1 cannot see.
    (a) HOLD also needs a measurement in the look-back window before the dispense; B1 has no look-back window, so a
    dispense long after the last (in-range) pressure is silent. (b) COUNT also has the day-end obligation (a minimum
    number of doses); B1 knows only the upper limit. WS06-T07 lists them; they lower B1's recall on missed doses
    and on stale or missing measurements."""
    plan_monitor = make_care_plan([make_instance(TemplateId.COUNT, "c-end", {}, T_DAY)])
    plan_b1 = make_care_plan(
        [
            *plan_monitor.instances,
            rec(TemplateId.RANGE, {}),
            rec(TemplateId.HOLD, {}),
            rec(TemplateId.COUNT, {}),
        ]
    )
    # (a) a pressure of 125 at 0:00, a dispense at 12:00: no measurement in the look-back window
    stale = day_of([bp(0, 125.0)], [measurement(0), dispense(hours(12))])
    first, _ = _monitor_violations(stale, plan_monitor, 0, (TemplateId.HOLD,))
    assert list(first) and any(k.startswith("hold") for k in first)
    assert run(make_b1(registry=REGISTRY), stale, plan_b1) == []
    # (b) one dose in the day: the monitor reports the day-end count obligation, B1 is silent
    one_dose = day_of(
        [bp(hours(8), 125.0)], [measurement(hours(8)), dispense(hours(8.1))]
    )
    first, _ = _monitor_violations(one_dose, plan_monitor, 0, (TemplateId.COUNT,))
    assert "c-end" in first
    assert run(make_b1(registry=REGISTRY), one_dose, plan_b1) == []


def test_b1_cannot_see_response_cuff_and_integrity_violations() -> None:
    """KNOWN BLIND SPOT, by construction (analisi section 5.4), pinned like the INT and SYS hole of B3. Three violations
    that the monitor reports VIOLATED and that B1 cannot see, because it has no response, cuff-health or presence logic:
    SYS (the cuff reports itself unhealthy at a measurement), RESP (no response within the window after a dose) and INT (a
    dispense with the robot present and seeing no patient: explicit presence zeros). B1 is silent on all three even with
    every threshold rule active and an in-band pressure; the comparison with the proposed method on the integrity class
    (C3) and on the system class (C2) is not a comparison of equals, and WS08 must say so."""

    def m(h: int, mm: int = 0) -> int:
        return (60 * h + mm) * 60_000

    monitor_plan = make_care_plan()
    b1_plan = plan_of(
        rec(TemplateId.RANGE, {}),
        rec(TemplateId.HOLD, {}),
        rec(TemplateId.COUNT, {}),
        sched(m(8)),
        schedule=[m(8)],
    )
    cases = {
        TemplateId.SYS: day_of(
            [bp(m(8), 125.0), make_sample("cuff_health", m(8), None, 0.0)],
            [measurement(m(8))],
        ),
        TemplateId.RESP: day_of(
            [bp(m(7, 59), 130.0), bp(m(8), 125.0)], [dispense(m(8))]
        ),
        TemplateId.INT: day_of(
            [bp(m(7, 59), 125.0), bp(m(8), 125.0)]
            + [
                make_sample("presence", m(7, 50) + k * STEP, None, 0.0)
                for k in range(15)
            ],
            [measurement(m(8)), dispense(m(8))],
        ),
    }
    for template, day in cases.items():
        first, _ = _monitor_violations(day, monitor_plan, 0, [template])
        assert len(first) == 1, (template, first)
        assert run(make_b1(tail_ms=hours(4), registry=REGISTRY), day, b1_plan) == [], (
            template
        )


def test_b1_input_within_one_step_before_the_day_is_step_zero() -> None:
    """M1 (review). The monitor and the grid give a device time in ``(t0 - step, t0]`` the step 0 of the day
    (``ceil(t / T_s)``), so such an input IS part of the day; one stamped a whole step before or earlier is not. The
    boundary: ``t0 - step + 1`` raises the alarm (at the delivery step ``t0``), ``t0 - step`` does not."""
    t0 = T_DAY
    plan = plan_of(
        rec(TemplateId.RANGE, BAND),
        rec(TemplateId.HOLD, HOLD),
        rec(TemplateId.COUNT, COUNT),
    )
    for stamp, alarmed in ((t0 - STEP + 1, True), (t0 - STEP, False), (t0 - 1, True)):
        day = day_of([bp(stamp, 152.0, rx=t0)], [], day_index=1)
        assert times(run(make_b1(), day, plan)) == ([t0] if alarmed else []), stamp
    # the same step rule for a dispense (hold and dose limit) and for the pressure it is judged on
    low = day_of([bp(t0 - STEP + 1, 90.0, rx=t0)], [dispense(t0 + STEP)], day_index=1)
    assert times(run(make_b1(), low, plan)) == [t0, t0 + STEP]
    early_dose = day_of(
        [],
        [dispense(t0 - STEP + 1, rx=t0), dispense(t0 + STEP), dispense(t0 + 2 * STEP)],
        day_index=1,
    )
    assert times(run(make_b1(), early_dose, plan)) == [
        t0 + 2 * STEP
    ]  # 3 doses, none alarmed at step 0 (count 1)
    one_early = day_of(
        [], [dispense(t0 - STEP + 1, rx=t0), dispense(t0 + STEP)], day_index=1
    )
    strict = plan_of(rec(TemplateId.COUNT, {"dose_max_24h": 0.0}))
    assert times(run(make_b1(), one_early, strict)) == [t0, t0 + STEP]


def test_b1_dose_count_ignores_later_stamped_doses_that_arrived_first() -> None:
    """M2 (review). With a reorder delay that is not a multiple of the step, a dose stamped earlier can be delivered
    after a later-stamped one without being late. The window of the count at ``t`` is ``(t - 24 h, t]``: the dose that
    arrived first but is stamped later is not in it. Limit 1: the count at the second delivery is 1, no alarm. Dropping
    the upper bound of the window counts 2 and alarms."""
    t0 = T_DAY
    first = dispense(t0 - 30_000, rx=t0)  # delivered at t0 (delay 30 s)
    second = dispense(
        t0 - 40_000, rx=t0 + STEP
    )  # stamped earlier, delivered one step later, not late
    plan = plan_of(rec(TemplateId.COUNT, {"dose_max_24h": 1.0}))
    b1 = make_b1(delay_ms=30_000)
    assert run(b1, day_of([], [first, second], day_index=1), plan) == []
    assert b1.run_stats is not None and b1.run_stats.late_inputs == 0


def test_b1_schedule_anchor_at_the_next_days_first_step_is_not_checked() -> None:
    """M3 (review). An instance anchored at exactly ``t0 + 24 h`` belongs to the next day (empty carry-over); one at
    ``t0`` or one step before the end of the day is checked."""
    window = {"sched_window": 600_000.0}
    next_day = plan_of(sched(T_DAY, window))
    assert run(make_b1(), day_of([]), next_day) == []
    assert make_b1().run(day_of([]), next_day, None) == ()
    last_step = plan_of(sched(T_DAY - STEP, window))
    assert times(run(make_b1(), day_of([]), last_step)) == [T_DAY - STEP + 600_000]
    first_step = plan_of(sched(0, window))
    assert times(run(make_b1(), day_of([]), first_step)) == [600_000]
    on_day_1 = plan_of(sched(T_DAY, window))
    assert times(run(make_b1(), day_of([], day_index=1), on_day_1)) == [T_DAY + 600_000]


@pytest.mark.parametrize("step", [30_000, 60_000])
@pytest.mark.parametrize(
    "window",
    [
        0.0,
        -0.0,
        1.0,
        29_999.0,
        30_000.0,
        30_000.5,
        45_000.0,
        60_000.0,
        90_000.0,
        120_000.0,
    ]
    + [
        1_800_000.0,
        1_800_001.0,
        -30_000.0,
        -60_000.0,
        -1.0,
        float("nan"),
        float("inf"),
    ],
)
def test_b1_window_alignment_agrees_with_the_monitor(window: float, step: int) -> None:
    """M4 (review). B1 checks the alignment of the schedule window locally (``tests/test_layering.py`` forbids the
    import of ``ralmon.monitor.parameters`` from ``src``); this ties its accept and reject set to ``check_alignment``
    of the monitor, so that the copy cannot drift."""
    from ralmon.monitor.parameters import check_alignment

    try:
        check_alignment({"sched_window": window}, step, "reference")
        accepted = True
    except PlanFeasibilityError:
        accepted = False
    b1 = B1StaticThresholds(timing=TimingConfig(step, 0, 0))
    b1.fit([], [])
    plan = plan_of(sched(hours(6), {"sched_window": window}))
    try:
        run(b1, day_of([]), plan)
        b1_accepts = True
    except PlanFeasibilityError:
        b1_accepts = False
    assert b1_accepts == accepted, (window, step)


def test_b1_differences_in_what_counts_as_a_measurement_and_as_a_range_instance() -> (
    None
):
    """M5 and M6 (review), pinned against the monitor. (a) R3 gives credit for a bare pressure sample (no MEASUREMENT
    event): the monitor's SCHED does not, so it reports the miss and B1 does not (a sample-only outage). (b) A
    MEASUREMENT event one millisecond before the anchor counts for the monitor's grid (same step) but not for B1, whose
    window is ``[anchor, anchor + window]`` on device times; generator delays are non-negative, so this never occurs there.
    (c) R1 alarms per pressure sample while the monitor's RANGE is keyed per MEASUREMENT event: a sample with no event
    is an alarm for B1 and no instance for the monitor; two samples of one event are two alarms and one violation."""
    anchor = hours(6)
    monitor_plan = make_care_plan([make_instance(TemplateId.SCHED, "s6", {}, anchor)])
    b1_plan = plan_of(sched(anchor), rec(TemplateId.RANGE, BAND), schedule=[anchor])
    bare = day_of([bp(hours(6.1), 125.0)])
    first, _ = _monitor_violations(bare, monitor_plan, 0, [TemplateId.SCHED])
    assert first == {"s6": 23_400_000}
    assert run(make_b1(), bare, b1_plan) == []
    early = day_of([], [measurement(anchor - 1)])
    first, _ = _monitor_violations(early, monitor_plan, 0, [TemplateId.SCHED])
    assert first == {}
    assert times(run(make_b1(), early, b1_plan)) == [23_400_000]
    no_event = day_of([bp(hours(1), 152.0)])
    first, _ = _monitor_violations(no_event, make_care_plan(), 0, [TemplateId.RANGE])
    assert first == {}
    assert times(run(make_b1(), no_event, b1_plan)) == [hours(1), 23_400_000]
    two = day_of(
        [bp(hours(1), 152.0), bp(hours(1) + 5_000, 152.0)], [measurement(hours(1))]
    )
    first, _ = _monitor_violations(two, make_care_plan(), 0, [TemplateId.RANGE])
    assert len(first) == 1
    assert times(run(make_b1(), two, plan_of(rec(TemplateId.RANGE, BAND)))) == [
        hours(1),
        hours(1) + STEP,
    ]


# ---- stats, determinism, the class and its source ---------------------------------------------------------------------------


def test_b1_run_stats_report_the_active_rules() -> None:
    """``run_stats`` lets a caller see that B1 was not vacuous: which rules were active on the plan of the last run."""
    b1 = make_b1()
    assert b1.run_stats is None
    run(b1, day_of([bp(hours(1), 125.0)]), plan_of())
    assert b1.run_stats is not None and b1.run_stats.rules_active == ()
    run(b1, day_of([bp(hours(1), 125.0)]), full_plan(hours(6)))
    assert b1.run_stats.rules_active == ("R1", "R2", "R3", "R4")
    assert b1.run_stats.schedule_checks == 1
    run(b1, day_of([bp(hours(1), 125.0)]), plan_of(rec(TemplateId.HOLD, HOLD)))
    assert b1.run_stats.rules_active == ("R2",)
    b1.fit([], [])
    assert b1.run_stats is None  # a new fit forgets the last run


def test_b1_is_deterministic_and_leaves_the_plan_alone() -> None:
    plan = full_plan(hours(8))
    day = _rich_day()
    a = run(make_b1(), day, plan)
    b = run(make_b1(), day, plan)
    assert a == b and a
    assert all(isinstance(d, Detection) for d in a)
    assert [d.t_ms for d in a] == sorted(d.t_ms for d in a)


def test_b1_second_day_uses_the_axis_of_the_day() -> None:
    day = day_of([bp(T_DAY + hours(1), 152.0)], [], day_index=1)
    assert times(run(make_b1(), day, plan_of(rec(TemplateId.RANGE, BAND)))) == [
        T_DAY + hours(1)
    ]


def test_b1_signature_name_and_protocol() -> None:
    b1 = B1StaticThresholds(timing=TimingConfig(STEP, 0, 0))
    assert b1.name == "B1" and B1StaticThresholds.name == "B1"
    assert isinstance(b1, BaselineBase) and isinstance(b1, Detector)
    assert not hasattr(B1StaticThresholds, "__ralmon_stub_owner__")
    parameters = inspect.signature(B1StaticThresholds.__init__).parameters
    assert (
        "alpha" not in parameters
        and "threshold" not in parameters
        and "z_threshold" not in parameters
    )


def test_b1_docstring_states_what_b1_sees_and_does_not_see() -> None:
    """The class names its hyperparameter rule; the module states the rules, the five roles and the blind spots."""
    doc = inspect.getdoc(B1StaticThresholds) or ""
    assert "Hyperparameter selection" in doc and "no operating parameter" in doc
    module_doc = inspect.getdoc(b1_module()) or ""
    for phrase in (
        "R1",
        "R2",
        "R3",
        "R4",
        "RESP",
        "SYS",
        "INT",
        "day-end",
        "look-back",
        "attribution",
        "Hyperparameter selection",
    ):
        assert phrase in module_doc, phrase
    for name in b1_module().ROLE_PARAMETERS.values():
        assert name in module_doc, name


def test_b1_source_has_no_latent_types_and_no_clinical_constant() -> None:
    source = B1_SOURCE.read_text(encoding="utf-8")
    for token in (
        "LatentDay",
        "GroundTruthEvent",
        "Conformal",
        "Forecaster",
        "normalise",
        "rank_alerts",
    ):
        assert token not in source, token
    assert re.search(r"\b(110|140)\b", source) is None


def test_b1_exported_from_the_package() -> None:
    from ralmon import baselines

    assert baselines.B1StaticThresholds is B1StaticThresholds
    assert "B1StaticThresholds" in baselines.__all__
    from ralmon.baselines import _stubs

    assert not hasattr(_stubs, "B1StaticThresholds")


def test_b1_run_on_a_benchmark_day_is_refused() -> None:
    from ralmon.baselines.base import LeakageError

    b1 = make_b1()
    with pytest.raises(LeakageError):
        b1.run(make_benchmark_day([], []), full_plan(), None)  # type: ignore[arg-type]
