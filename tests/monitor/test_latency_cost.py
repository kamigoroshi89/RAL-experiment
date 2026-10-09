"""Cost and state of ``StreamingMonitor`` (WS05-T04 tests 23 and 24) and the reported costs.

``stats().node_updates`` counts constant-time units of work, not seconds (no wall clock): one per
instance evaluation, one per step summary, one per released input. ``stats().retained_samples``
counts the inputs the monitor keeps: the reorder buffer and the dispense queue of the trailing 24 h.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

import ralmon.monitor as m

from .helpers import (
    K_DAY,
    STEP,
    Inputs,
    drive,
    evt,
    hhmm,
    load_f0,
    load_lib,
    make_monitor,
    override_row,
    registry_variant,
    smp,
)

REG = load_f0()
LIB = load_lib(REG)
TICK = hhmm(9, 0)


LONG_WINDOW = 72_000_000.0  # 1200 steps: the instances below stay active for the whole measurement


@pytest.fixture(scope="module")
def long_registry(tmp_path_factory: pytest.TempPathFactory) -> Any:
    return registry_variant(
        tmp_path_factory.mktemp("long"),
        overrides=[override_row("sched_window", 1_800_000.0, LONG_WINDOW)],
    )


def many_sched(registry: Any, count: int) -> Any:
    """``count`` identical SCHED instances: ticks 1 ms apart, all visible at step 541, each active for
    1200 steps (their own ``sched_window``)."""
    from ralmon.spec import CarePlan, TemplateId, TemplateInstance

    instances = tuple(
        TemplateInstance(
            TemplateId.SCHED,
            f"sched@{TICK + 1 + i}",
            {"sched_window": LONG_WINDOW},
            TICK + 1 + i,
        )
        for i in range(count)
    )
    plan = CarePlan(
        "plan-1", "pathway", "p-1", registry.version(), instances, (), 1, None
    )
    return make_monitor(registry, plan=plan)


def per_sample_cost(registry: Any, instances: int, steps: int) -> float:
    """Node updates per ingested sample over ``steps`` steps with one sample per step."""
    mon = many_sched(registry, instances)
    first = 545
    mon.advance(first * STEP)
    before = mon.stats().node_updates
    assert mon.stats().active_instances == instances
    for k in range(first + 1, first + 1 + steps):
        mon.push_sample(smp("bp", k * STEP, 120.0))
        mon.advance(k * STEP)
    assert (
        mon.stats().active_instances == instances
    )  # still active: the trace did not shorten the work
    return (mon.stats().node_updates - before) / steps


def test_node_updates_per_sample_are_linear_in_active_instances(
    long_registry: Any,
) -> None:
    cost = {
        (a, n): per_sample_cost(long_registry, a, n)
        for a in (1, 10, 100)
        for n in (10, 800)
    }
    for a in (1, 10, 100):
        # independent of the trace length: 10 steps and 800 steps cost the same per sample
        assert cost[(a, 10)] == pytest.approx(cost[(a, 800)]), a
    # at most linear in the number of instances
    assert cost[(10, 10)] <= 10 * cost[(1, 10)]
    assert cost[(100, 10)] <= 100 * cost[(1, 10)]
    assert (
        cost[(10, 10)] > cost[(1, 10)]
    )  # it does grow with the instances: one update each per step
    assert cost[(100, 10)] - cost[(10, 10)] == pytest.approx(
        90.0
    )  # exactly one node update per instance per step


def test_a_quiet_step_costs_one_node_update_per_active_instance_whatever_the_window() -> (
    None
):
    """RESP has a 180-step window and SCHED a 30-step one: the cost per step does not depend on them."""
    mon = make_monitor(REG)
    mon.advance(100 * STEP)
    base_before = mon.stats().node_updates
    mon.advance(101 * STEP)
    baseline = mon.stats().node_updates - base_before  # a step with no active instance
    inputs = Inputs()
    inputs.events.append(evt("dispense", hhmm(7, 0), source="dispenser"))
    inputs.samples.append(smp("bp", hhmm(6, 55), 150.0))
    mon2 = make_monitor(REG, sched=(hhmm(6, 0),))
    drive(mon2, inputs, 430)
    active = mon2.stats().active_instances
    assert (
        active >= 2
    )  # the RESP instance (window 180 steps) and the static SCHED one are active
    before = mon2.stats().node_updates
    mon2.advance(431 * STEP)
    assert mon2.stats().node_updates - before == baseline + active


def test_node_updates_do_not_depend_on_the_length_of_the_history() -> None:
    def cost_of_one_step(history_steps: int) -> int:
        mon = make_monitor(REG, sched=(hhmm(0, 1),))
        for k in range(history_steps):
            mon.push_sample(smp("bp", k * STEP, 120.0))
            mon.advance(k * STEP)
        before = mon.stats().node_updates
        mon.push_sample(smp("bp", history_steps * STEP, 120.0))
        mon.advance(history_steps * STEP)
        return mon.stats().node_updates - before

    assert cost_of_one_step(20) == cost_of_one_step(1200)


# ---------------------------------------------------------------------------------------------
# test 24: retained state is bounded by the windows
# ---------------------------------------------------------------------------------------------


def test_retained_state_is_bounded_by_windows() -> None:
    capacity = 64
    mon = make_monitor(REG, buffer_capacity=capacity)
    bound = K_DAY + capacity  # largest window: the 24 h of dose_count, plus the buffer
    peaks: list[int] = []
    inputs = Inputs()
    for k in range(3 * K_DAY):
        inputs.samples.append(smp("bp", k * STEP, 120.0 + (k % 7)))
        if k % 10 == 0:
            inputs.events.append(evt("dispense", k * STEP + 5_000, source="dispenser"))
    items = inputs.merged()
    pointer = 0
    for k in range(3 * K_DAY):
        t = k * STEP
        while pointer < len(items) and items[pointer][0] <= t:
            obj = items[pointer][4]
            (mon.push_sample if items[pointer][3] == "sample" else mon.push_event)(obj)
            pointer += 1
        mon.advance(t)
        peaks.append(mon.stats().retained_samples)
    assert max(peaks) <= bound
    # nothing proportional to the trace length is kept: the third day retains no more than the second
    assert max(peaks[2 * K_DAY :]) <= max(peaks[K_DAY : 2 * K_DAY]) + 1
    stats = mon.stats()
    assert stats.retained_samples <= bound and stats.buffered_inputs <= capacity
    assert (
        stats.active_instances < 400
    )  # instances retire when decided or at their horizon


def test_the_duplicate_keys_are_pruned_with_the_window() -> None:
    mon = make_monitor(REG)
    for k in range(3 * K_DAY):
        mon.push_sample(smp("bp", k * STEP, 120.0, seq=k))
        mon.advance(k * STEP)
    assert mon.stats().retained_dedup_keys <= K_DAY + 1
    assert mon.stats().duplicate_count == 0


# ---------------------------------------------------------------------------------------------
# what is reported
# ---------------------------------------------------------------------------------------------


def test_class_docstring_states_the_reported_costs_and_the_latency_bound() -> None:
    doc = m.StreamingMonitor.__doc__ or ""
    assert "O(" in doc and "latency" in doc.lower()
    assert "O(log b)" in doc  # ingestion into a buffer of b inputs
    assert (
        "O(A)" in doc and "amortised" in doc.lower()
    )  # evaluation per grid step for A active instances
    assert "O(largest window in steps + b)" in doc  # state
    for template in ("RANGE", "SCHED", "HOLD", "COUNT", "RESP", "SYS", "INT"):
        assert template in doc, template  # the latency bound is stated per template


def test_stats_fields() -> None:
    stats = make_monitor(REG).stats()
    names = {f.name for f in dataclasses.fields(stats)}
    assert names >= {
        "node_updates",
        "retained_samples",
        "retained_dedup_keys",
        "buffered_inputs",
        "active_instances",
        "steps_finalised",
        "records_emitted",
        "accepted_count",
        "released_count",
        "late_count",
        "future_stamped_count",
        "duplicate_count",
        "overflow_count",
        "after_finalisation_count",
        "ignored_events",
        "out_of_domain_samples",
        "rho_unavailable",
        "future_stamp_check",
    }
    assert (
        stats.node_updates == 0
        and stats.retained_samples == 0
        and stats.late_count == 0
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        stats.node_updates = 5  # type: ignore[misc]


def test_stats_count_what_the_run_did() -> None:
    inputs = Inputs()
    inputs.events.append(evt("dispense", hhmm(7, 0), source="dispenser"))
    inputs.samples.append(smp("bp", hhmm(6, 55), 150.0))
    mon = make_monitor(REG)
    records = drive(mon, inputs, 425)
    stats = mon.stats()
    assert stats.steps_finalised == 426
    assert stats.records_emitted == len(records)
    assert stats.accepted_count == 2 and stats.released_count == 2
    assert stats.active_instances >= 1  # the RESP instance is waiting for its window
