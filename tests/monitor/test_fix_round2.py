"""Fix round 2 (WS05-T04): the time axis of a day, and gaps found by the second review's mutants.

The first part pins what ``run_offline`` does with ``day_index``: the benchmark writes the days of a
patient on a continuing axis (``day_index * T_day + clock time``, WS04-T06), so day ``d`` is run from the
step ``d * K``. The second part adds the tests for four mutants that survived the review.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

import ralmon.monitor as m
from ralmon.spec import HmacSha256PlanVerifier, PlanIntegrityError, TemplateId

from .helpers import (
    K_DAY,
    STEP,
    T_DAY,
    LocalDay,
    evt,
    final,
    hhmm,
    load_f0,
    load_lib,
    make_config,
    make_monitor,
    make_plan,
    smp,
)
from .test_inputs import Hostile

REG = load_f0()
LIB = load_lib(REG)
CFG = make_config(REG)


def run(day: Any, plan: Any) -> Any:
    return m.run_offline_detailed(
        day, plan, CFG, None, None, registry=REG, templates=LIB
    )


# ---------------------------------------------------------------------------------------------
# MINOR 4: day_index
# ---------------------------------------------------------------------------------------------


def day_one(offset: int) -> LocalDay:
    t = offset + hhmm(7, 0)
    return LocalDay(
        [smp("bp", t, 150.0)], [evt("measurement", t, source="cuff")], day_index=1
    )


def test_a_day_on_the_continuing_axis_is_run_from_its_own_first_step() -> None:
    base = T_DAY
    plan = make_plan(REG, sched=[hhmm(9, 0), base + hhmm(9, 0)])
    result = run(day_one(base), plan)
    keys = {r.instance_key for r in result.records}
    assert f"range@{base + hhmm(7, 0)}" in keys
    assert f"sched@{base + hhmm(9, 0)}" in keys
    assert f"sched@{hhmm(9, 0)}" not in keys  # the tick of day 0 belongs to another run
    assert result.stats.plan_instances_before_start == 1
    assert result.stats.accepted_count == 2 and result.rejected_inputs == ()
    assert min(r.t_eval_ms for r in result.records) >= base
    assert max(r.t_eval_ms for r in result.records) <= base + T_DAY
    assert result.stats.steps_finalised == 2 * K_DAY + 1  # the axis, counted from 0


def test_a_day_on_the_per_day_axis_with_a_day_index_is_reported_not_swallowed() -> None:
    result = run(day_one(0), make_plan(REG, sched=[T_DAY + hhmm(9, 0)]))
    assert result.stats.accepted_count == 0
    assert result.stats.after_finalisation_count == 2
    assert [r.reason for r in result.rejected_inputs] == ["finalised", "finalised"]


def test_day_zero_is_unchanged() -> None:
    day = LocalDay([smp("bp", hhmm(7, 0), 150.0)], [evt("measurement", hhmm(7, 0))])
    result = run(day, make_plan(REG, sched=[hhmm(9, 0)]))
    assert result.stats.plan_instances_before_start == 0
    assert (
        result.stats.accepted_count == 2 and result.stats.steps_finalised == K_DAY + 1
    )
    assert {r.instance_key for r in result.records} >= {f"range@{hhmm(7, 0)}"}


@pytest.mark.parametrize(
    "day_index",
    [-1, True, 1.5, None, "1", 10**9, 2**70, Hostile()],
    ids=["negative", "bool", "float", "none", "str", "too-large", "huge", "hostile"],
)
def test_a_bad_day_index_is_a_named_error(day_index: Any) -> None:
    day = dataclasses.replace(day_one(0), day_index=0)
    object.__setattr__(day, "day_index", day_index)
    for fn in (m.run_offline, m.run_offline_detailed):
        with pytest.raises(m.MonitorInputError, match="day_index"):
            fn(day, make_plan(REG), CFG, None, None, registry=REG, templates=LIB)


def test_an_instance_before_the_run_is_skipped_and_one_in_its_finalised_past_is_refused() -> (
    None
):
    """Inside a run the rule of the finalised past is unchanged."""
    mon = m.StreamingMonitor(CFG, REG, LIB)
    mon._start_at(3 * K_DAY)  # type: ignore[attr-defined]
    mon.load(
        make_plan(REG, sched=[hhmm(9, 0), 3 * T_DAY + hhmm(9, 0)])
    )  # day 0 skipped
    assert mon.stats().plan_instances_before_start == 1
    mon.advance(3 * T_DAY + 10 * STEP)
    with pytest.raises(m.PlanFeasibilityError, match="finalised"):
        mon.load(make_plan(REG, sched=[3 * T_DAY + 10 * STEP], plan_version=2))


def test_the_start_can_only_be_set_before_anything_was_finalised() -> None:
    mon = m.StreamingMonitor(CFG, REG, LIB)
    mon.advance(STEP)
    with pytest.raises(m.MonitorInputError):
        mon._start_at(K_DAY)  # type: ignore[attr-defined]
    loaded = make_monitor()  # a plan is already loaded
    with pytest.raises(m.MonitorInputError):
        loaded._start_at(K_DAY)  # type: ignore[attr-defined]
    fresh = m.StreamingMonitor(CFG, REG, LIB)
    for bad in (-1, True, 1.5, 10**30):
        with pytest.raises(m.MonitorInputError):
            fresh._start_at(bad)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------------------------
# MINOR 5: four survivors of the second review
# ---------------------------------------------------------------------------------------------


def test_anchors_applied_after_the_plan_is_loaded_are_not_counted_and_create_instances() -> (
    None
):
    """A20: the counter is about the moment an anchor is applied, not the moment it was pushed."""
    mon = m.StreamingMonitor(CFG, REG, LIB)
    mon.push_event(evt("measurement", STEP))  # pushed before the plan, applied after it
    mon.push_event(evt("dispense", 2 * STEP))
    mon.load(make_plan(REG))
    records = mon.advance(3 * STEP)
    assert mon.stats().anchors_without_plan == 0
    assert {r.template.value for r in records} >= {
        "range",
        "sys",
        "hold",
        "count",
        "resp",
        "int",
    }


def test_every_anchor_of_a_step_before_the_plan_is_counted_once() -> None:
    mon = m.StreamingMonitor(CFG, REG, LIB)
    for t in (STEP, 2 * STEP, 3 * STEP):
        mon.push_event(evt("measurement", t, source="cuff"))
    mon.push_event(evt("dispense", 3 * STEP))
    mon.advance(4 * STEP)
    assert mon.stats().anchors_without_plan == 4


def test_a_template_whose_formula_does_not_parse_is_a_config_error_in_the_resolver() -> (
    None
):
    """F15: the resolver passes the library error through; it is not a bad path."""
    broken = dataclasses.replace(
        next(t for t in LIB if t.id is TemplateId.SYS), formula_past_time="(("
    )
    for fn in (m.resolve_subformula_path, m.resolve_subformula_paths):
        with pytest.raises(m.MonitorConfigError):
            fn(broken, "sys/0;sys/1")


def test_a_signed_plan_runs_offline_with_the_verifier_and_not_without() -> None:
    """O04: the verifier reaches the monitor through run_offline_detailed."""
    verifier = HmacSha256PlanVerifier(b"test-key-of-fix-round-2")
    plan = make_plan(REG)
    signed = dataclasses.replace(plan, signature=verifier.sign(plan))
    day = LocalDay([], [])
    result = m.run_offline_detailed(
        day, signed, CFG, None, None, registry=REG, templates=LIB, verifier=verifier
    )
    assert result.stats.steps_finalised == K_DAY + 1
    with pytest.raises(
        PlanIntegrityError
    ):  # signed, no verifier: never accepted silently
        m.run_offline_detailed(
            day, signed, CFG, None, None, registry=REG, templates=LIB
        )
    tampered = dataclasses.replace(signed, patient_id="someone-else")
    with pytest.raises(PlanIntegrityError):
        m.run_offline_detailed(
            day,
            tampered,
            CFG,
            None,
            None,
            registry=REG,
            templates=LIB,
            verifier=verifier,
        )
    other = HmacSha256PlanVerifier(b"another-key")
    with pytest.raises(PlanIntegrityError):
        m.run_offline_detailed(
            day, signed, CFG, None, None, registry=REG, templates=LIB, verifier=other
        )


def test_a_dynamic_key_that_clashes_with_a_static_key_gets_a_suffix() -> None:
    """X09: a dispense at exactly 24:00 against the day-end COUNT keyed count@86400000."""
    mon = make_monitor(day_end=[T_DAY])
    mon.push_event(evt("dispense", T_DAY))
    records = mon.advance(T_DAY)
    keys = sorted({r.instance_key for r in records if r.template is TemplateId.COUNT})
    assert keys == [f"count@{T_DAY}", f"count@{T_DAY}#2"]
    day_end = final(records, f"count@{T_DAY}")
    limit = final(records, f"count@{T_DAY}#2")
    dose_max, dose_min = (
        REG.get("dose_max_24h").value,
        REG.get("dose_min_day_end").value,
    )
    assert day_end.sigma_interval.lo == day_end.sigma_interval.hi == 1 - dose_min
    assert limit.sigma_interval.lo == limit.sigma_interval.hi == dose_max - 1


# ---------------------------------------------------------------------------------------------
# the start step and the reorder buffer: gaps found by the mutation run of this round
# ---------------------------------------------------------------------------------------------


def test_the_start_step_can_be_set_only_once_and_not_after_an_advance_without_a_step() -> (
    None
):
    mon = m.StreamingMonitor(CFG, REG, LIB)
    mon._start_at(K_DAY)  # type: ignore[attr-defined]
    with pytest.raises(m.MonitorInputError, match="before the first advance"):
        mon._start_at(2 * K_DAY)  # type: ignore[attr-defined]  # k_f is no longer -1
    delayed = m.StreamingMonitor(make_config(REG, d_ms=STEP), REG, LIB)
    assert (
        delayed.advance(0) == ()
    )  # t - D < 0: no step is finalised, but advance was called
    with pytest.raises(m.MonitorInputError, match="before the first advance"):
        delayed._start_at(5)  # type: ignore[attr-defined]


def entry(**changes: Any) -> Any:
    from ralmon.monitor.reorder import BufferedInput

    fields: dict[str, Any] = {
        "t_device_ms": 10,
        "t_rx_ms": 10,
        "kind": "sample",
        "item": "x",
        "seq": None,
        "data": None,
        "order": 0,
    }
    fields.update(changes)
    return BufferedInput(**fields)


@pytest.mark.parametrize(
    ("changes", "fragment"),
    [
        ({"kind": "other"}, "unknown kind"),
        ({"kind": None}, "unknown kind"),
        ({"t_device_ms": True}, "t_device_ms"),
        ({"t_device_ms": 1.5}, "t_device_ms"),
        ({"t_device_ms": "10"}, "t_device_ms"),
        ({"t_rx_ms": None}, "t_rx_ms"),
        ({"order": 0.5}, "order"),
        ({"order": False}, "order"),
        ({"seq": 1.5}, "seq"),
        ({"seq": True}, "seq"),
        ({"seq": "1"}, "seq"),
    ],
)
def test_a_malformed_buffer_entry_is_refused_before_the_heap_is_touched(
    changes: dict[str, Any], fragment: str
) -> None:
    from ralmon.monitor.reorder import ReorderBuffer

    buffer = ReorderBuffer(10)
    with pytest.raises(m.MonitorInputError, match=fragment):
        buffer.push(entry(**changes))
    assert len(buffer) == 0
    assert buffer.push(entry()) is True and len(buffer) == 1  # still usable


def test_a_buffer_entry_that_is_not_a_buffer_entry_is_refused() -> None:
    from ralmon.monitor.reorder import ReorderBuffer

    buffer = ReorderBuffer(10)
    for bad in (None, 5, "entry", object(), (10, 10, "sample", "x", None)):
        with pytest.raises(m.MonitorInputError, match="BufferedInput"):
            buffer.push(bad)  # type: ignore[arg-type]
    assert len(buffer) == 0


def test_a_buffer_entry_whose_attributes_raise_is_a_named_error() -> None:
    from ralmon.monitor.reorder import BufferedInput, ReorderBuffer

    class Raising(BufferedInput):
        @property  # type: ignore[misc]
        def kind(self) -> str:
            raise RuntimeError("hostile kind")

    buffer = ReorderBuffer(10)
    bad = object.__new__(Raising)
    for name, value in (
        ("t_device_ms", 10),
        ("t_rx_ms", 10),
        ("seq", None),
        ("order", 0),
    ):
        object.__setattr__(bad, name, value)
    with pytest.raises(m.MonitorInputError, match="unusable argument"):
        buffer.push(bad)
    assert len(buffer) == 0
