"""Loading a care plan, configuration and registry checks (WS05-T04 tests 25 and 26 and WS05-T03 hand-over).

Checks that ``Monitor.load`` makes: signature (ADR-051), exact registry version, ``plan_version`` never
decreasing per ``care_plan_id``, the feasibility of the plan (alignment of the window parameters, the
approved range of an overridden value, known names, anchors). The registry is the F0 fixture (ADR-027)
except in the tests that say otherwise; the real registry (0.2.0) is only loaded and run, no value of
it is pinned.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

import ralmon.monitor as m
from ralmon.spec import (
    CarePlan,
    HmacSha256PlanVerifier,
    PlanIntegrityError,
    TemplateId,
    TemplateInstance,
    load_registry,
    load_templates,
)

from .helpers import (
    STEP,
    T_DAY,
    Inputs,
    SpyRegistry,
    at_step,
    by_key,
    drive,
    entry_row,
    evt,
    hhmm,
    load_f0,
    load_lib,
    make_config,
    make_plan,
    override_row,
    registry_variant,
    smp,
)

REG = load_f0()
LIB = load_lib(REG)
TICK = hhmm(9, 0)
KEY = b"test-key-of-the-monitor-tests"


def monitor(
    registry: Any = REG, lib: Any = LIB, config: Any = None, **kwargs: Any
) -> Any:
    return m.StreamingMonitor(
        make_config(registry) if config is None else config, registry, lib, **kwargs
    )


# ---------------------------------------------------------------------------------------------
# test 25: signature, registry version and monotonic plan_version
# ---------------------------------------------------------------------------------------------


def test_load_verifies_signature_and_monotonic_plan_version() -> None:
    verifier = HmacSha256PlanVerifier(KEY)
    plan = make_plan(REG, sched=(TICK,), plan_version=2)
    signed = dataclasses.replace(plan, signature=verifier.sign(plan))
    mon = monitor(verifier=verifier)
    mon.load(signed)  # the signature verifies
    tampered = dataclasses.replace(
        signed, patient_id="someone-else"
    )  # content changed, old signature
    with pytest.raises(PlanIntegrityError):
        mon.load(tampered)
    older = dataclasses.replace(plan, plan_version=1)
    older_signed = dataclasses.replace(older, signature=verifier.sign(older))
    with pytest.raises(m.PlanVersionError):
        mon.load(older_signed)  # a valid but older plan of the same care_plan_id
    other_registry = dataclasses.replace(plan, registry_version="9.9.9")
    with pytest.raises(PlanIntegrityError):
        monitor(verifier=verifier).load(
            dataclasses.replace(other_registry, signature=verifier.sign(other_registry))
        )


def test_plan_version_may_stay_or_rise_and_is_tracked_per_care_plan() -> None:
    mon = monitor()
    mon.load(make_plan(REG, plan_version=3))
    mon.load(
        make_plan(REG, plan_version=3)
    )  # non-decreasing: the same version is accepted
    mon.load(make_plan(REG, plan_version=4))
    with pytest.raises(m.PlanVersionError):
        mon.load(make_plan(REG, plan_version=3))
    mon.load(
        make_plan(REG, plan_version=1, care_plan_id="another-plan")
    )  # another plan, its own counter
    with pytest.raises(m.PlanVersionError):
        mon.load(make_plan(REG, plan_version=0, care_plan_id="another-plan"))
    with pytest.raises(m.PlanVersionError):
        mon.load(make_plan(REG, plan_version=3))  # the first plan is still at version 4


def test_a_forged_plan_is_refused_before_its_version_is_looked_at() -> None:
    verifier = HmacSha256PlanVerifier(KEY)
    mon = monitor(verifier=verifier)
    plan = make_plan(REG, plan_version=5)
    mon.load(dataclasses.replace(plan, signature=verifier.sign(plan)))
    forged = dataclasses.replace(plan, plan_version=1, signature="0" * 64)
    with pytest.raises(PlanIntegrityError):
        mon.load(forged)


def test_a_failed_load_changes_nothing() -> None:
    mon = monitor()
    mon.load(make_plan(REG, sched=(TICK,), plan_version=2))
    with pytest.raises(m.PlanVersionError):
        mon.load(make_plan(REG, sched=(hhmm(10, 0),), plan_version=1))
    records = drive(mon, Inputs(), 545)
    assert {r.instance_key for r in records} == {f"sched@{TICK}"}


def test_signed_plan_without_verifier_and_unsigned_plan_when_required() -> None:
    verifier = HmacSha256PlanVerifier(KEY)
    plan = make_plan(REG)
    signed = dataclasses.replace(plan, signature=verifier.sign(plan))
    with pytest.raises(PlanIntegrityError):
        monitor().load(signed)  # never accepted unchecked
    with pytest.raises(PlanIntegrityError):
        monitor(require_signature=True).load(plan)  # a ward deployment (ADR-051)
    monitor(require_signature=False).load(plan)
    monitor().load(plan)  # unsigned plans are allowed unless a signature is required


def test_the_plan_registry_version_must_equal_the_loaded_registry() -> None:
    mon = monitor()
    with pytest.raises(PlanIntegrityError):
        mon.load(dataclasses.replace(make_plan(REG), registry_version="0.0.1"))


# ---------------------------------------------------------------------------------------------
# test 26 and the validity of the configuration (CG-12)
# ---------------------------------------------------------------------------------------------


def test_config_rejects_predictive_until_ws05_t08() -> None:
    config = make_config(REG, predictive=True, alpha=0.2)
    with pytest.raises(m.MonitorConfigError, match="added by WS05-T08"):
        monitor(config=config)


def test_monitor_config_is_a_plain_dataclass_with_the_contract_fields() -> None:
    assert [f.name for f in dataclasses.fields(m.MonitorConfig)] == [
        "step_ms",
        "reorder_delay_ms",
        "predictive",
        "alpha",
        "variant",
        "registry_version",
    ]
    c = make_config(REG)
    with pytest.raises(dataclasses.FrozenInstanceError):
        c.step_ms = 1  # type: ignore[misc]
    # it validates nothing: the monitor does (CG-12)
    m.MonitorConfig(
        step_ms=-1,
        reorder_delay_ms=-1,
        predictive=False,
        alpha=None,
        variant="likely",
        registry_version="",
    )


@pytest.mark.parametrize(
    "change",
    [
        {"step_ms": 0},
        {"step_ms": -STEP},
        {"step_ms": 70_000},  # does not divide T_day (M2)
        {"step_ms": True},
        {"step_ms": 60_000.0},
        {"step_ms": None},
        {"step_ms": "60000"},
        {"step_ms": 10**400},
        {"reorder_delay_ms": -1},
        {"reorder_delay_ms": True},
        {"reorder_delay_ms": 1.5},
        {"reorder_delay_ms": None},
        {"reorder_delay_ms": 10**400},
        {"predictive": "yes"},
        {"predictive": None},
        {"variant": "maybe"},
        {"variant": None},
        {"alpha": 0.0},
        {"alpha": 1.0},
        {"alpha": -0.1},
        {"alpha": float("nan")},
        {"alpha": float("inf")},
        {"alpha": "0.1"},
        {"alpha": True},
        {"registry_version": 1},
        {"registry_version": None},
        {"registry_version": "9.9.9"},  # not the loaded registry
    ],
    ids=lambda c: "-".join(f"{k}={v!r}" for k, v in c.items())[:60],
)
def test_the_configuration_is_validated(change: dict[str, Any]) -> None:
    config = dataclasses.replace(make_config(REG), **change)
    with pytest.raises(m.MonitorConfigError):
        monitor(config=config)


def test_a_valid_alpha_and_variant_are_accepted_when_not_predictive() -> None:
    for variant in ("likely", "possible"):
        monitor(
            config=dataclasses.replace(make_config(REG, variant=variant), alpha=0.2)
        )


def test_the_config_step_must_equal_the_registry_step(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    half = registry_variant(tmp_path_factory.mktemp("half"), step_ms=30_000)
    assert half.step_ms == 30_000
    config = dataclasses.replace(make_config(REG), registry_version=half.version())
    with pytest.raises(m.MonitorConfigError, match="step_ms"):
        monitor(registry=half, lib=load_lib(half), config=config)


def test_a_registry_without_a_step_cannot_give_the_derived_latency_names(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    bare = registry_variant(tmp_path_factory.mktemp("bare"), step_ms=None)
    with pytest.raises(m.MonitorConfigError, match="step_ms"):
        monitor(registry=bare, lib=LIB, config=make_config(bare))


@pytest.mark.parametrize("bad", [None, "registry", object(), 3])
def test_the_registry_must_be_a_registry(bad: Any) -> None:
    with pytest.raises(m.MonitorConfigError):
        monitor(registry=bad)


def test_the_bounds_must_be_a_proper_interval() -> None:
    from ralmon.spec import PhysioBounds

    class Inverted(SpyRegistry):
        def bounds(self, signal: str) -> Any:
            return PhysioBounds(signal, 260.0, 40.0)

    with pytest.raises(m.MonitorConfigError, match="bounds"):
        monitor(registry=Inverted(REG))
    for lower, upper in ((float("nan"), 250.0), (50.0, float("inf")), (250.0, 250.0)):

        class Odd(SpyRegistry):
            def bounds(self, signal: str, lo: float = lower, up: float = upper) -> Any:
                return PhysioBounds(signal, lo, up)

        with pytest.raises(m.MonitorConfigError, match="bounds"):
            monitor(registry=Odd(REG))


# ---------------------------------------------------------------------------------------------
# the template library: the closed forms are valid for exactly the strings of the library
# ---------------------------------------------------------------------------------------------


def test_a_template_whose_formula_differs_from_the_implemented_one_is_refused() -> None:
    changed = tuple(
        dataclasses.replace(
            t, formula_past_time=t.formula_past_time.replace("<=", ">=")
        )
        if t.id is TemplateId.COUNT
        else t
        for t in LIB
    )
    with pytest.raises(m.MonitorConfigError, match="count"):
        monitor(lib=changed)


def test_whitespace_and_redundant_parentheses_do_not_change_the_formula() -> None:
    spaced = tuple(
        dataclasses.replace(
            t, formula_past_time="  " + t.formula_past_time.replace(" ", "   ") + " "
        )
        for t in LIB
    )
    monitor(lib=spaced)


@pytest.mark.parametrize(
    "what", ["duplicate", "missing", "not a template", "none", "string"]
)
def test_the_template_library_is_checked(what: str) -> None:
    lib: Any
    if what == "duplicate":
        lib = (*LIB, LIB[0])
    elif what == "missing":
        lib = tuple(t for t in LIB if t.id is not TemplateId.SYS)
    elif what == "not a template":
        lib = (*LIB, object())
    elif what == "none":
        lib = None
    else:
        lib = "templates"
    if what == "missing":
        mon = monitor(lib=lib)  # a library without SYS simply has no SYS instance
        mon.load(make_plan(REG))
        inputs = Inputs()
        inputs.events.append(evt("measurement", hhmm(9, 0), source="cuff"))
        inputs.samples.append(smp("bp", hhmm(9, 0), 125.0))
        assert not any(
            r.instance_key.startswith("sys@") for r in drive(mon, inputs, 541)
        )
        return
    with pytest.raises(m.MonitorConfigError):
        monitor(lib=lib)


def test_template_ids_select_the_templates_that_run() -> None:
    mon = monitor(template_ids=[TemplateId.SCHED, TemplateId.RANGE])
    mon.load(make_plan(REG, sched=(TICK,)))
    inputs = Inputs()
    inputs.events.append(evt("measurement", hhmm(9, 5), source="cuff"))
    inputs.events.append(evt("dispense", hhmm(9, 6), source="dispenser"))
    inputs.samples.append(smp("bp", hhmm(9, 5), 130.0))
    records = drive(mon, inputs, 547)
    kinds = {r.template for r in records}
    assert kinds == {TemplateId.SCHED, TemplateId.RANGE}
    assert mon.verdict_latency_bound_ms(TemplateId.SCHED) == 1_860_000
    # a plan instance of a template that does not run is not instantiated
    mon2 = monitor(template_ids=[TemplateId.RANGE])
    mon2.load(make_plan(REG, sched=(TICK,)))
    assert drive(mon2, Inputs(), 545) == []


@pytest.mark.parametrize(
    "bad", [[], ["sched"], [TemplateId.SCHED, "x"], 5, "sched", [None]]
)
def test_template_ids_are_checked(bad: Any) -> None:
    with pytest.raises(m.MonitorConfigError):
        monitor(template_ids=bad)


# ---------------------------------------------------------------------------------------------
# registry names: never a silent substitute for an unset value
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "sched_window",
        "scale_resp",
        "max_latency_int",
        "delta_resp",
        "cuff_inflation_min",
    ],
)
def test_a_needed_unset_name_is_a_named_error_naming_the_parameter(name: str) -> None:
    spy = SpyRegistry(REG, unset=(name,))
    with pytest.raises(m.MonitorConfigError, match=name):
        monitor(registry=spy)


def test_the_real_registry_loads_and_runs_without_reading_its_unset_names() -> None:
    """Registry 0.2.0 has three unset names; the monitor needs none of them and substitutes nothing."""
    real = load_registry(step_ms=STEP)
    unset = real.unset_names()
    assert (
        unset
    )  # priority_sys, priority_int, bound_dose_count_upper at the time of writing
    spy = SpyRegistry(real, unset=unset)
    lib = load_templates(registry=real)
    mon = m.StreamingMonitor(make_config(real), spy, lib)
    mon.load(make_plan(real, sched=(TICK,)))
    inputs = Inputs()
    inputs.samples.append(smp("bp", hhmm(6, 55), 150.0))
    inputs.events.append(evt("measurement", hhmm(6, 55), source="cuff"))
    inputs.events.append(evt("dispense", hhmm(7, 0), source="dispenser"))
    records = drive(mon, inputs, 430)
    assert records
    assert not set(spy.read) & set(unset)
    for r in records:
        assert r.sigma_interval.lo <= r.sigma_interval.hi
        assert -1.0 <= r.sigma_norm_interval[0] <= r.sigma_norm_interval[1] <= 1.0


# ---------------------------------------------------------------------------------------------
# approved ranges of per-patient values (ADR-047 (g), proposed: the minimal documented check)
# ---------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ranged(tmp_path_factory: pytest.TempPathFactory) -> Any:
    return registry_variant(
        tmp_path_factory.mktemp("ranged"),
        overrides=[
            override_row("bp_hold_threshold", 80.0, 100.0),
            override_row("sched_window", 1_000_000.0, 3_000_000.0),
            override_row("delta1", 0.0, 20_000_000.0),
            override_row("delta2", 0.0, 20_000_000.0),
        ],
    )


def plan_with(registry: Any, *instances: TemplateInstance) -> CarePlan:
    return make_plan(registry, records=instances)


def test_a_value_equal_to_the_registry_needs_no_override() -> None:
    mon = monitor()
    mon.load(
        plan_with(
            REG,
            TemplateInstance(
                TemplateId.HOLD, "hold-params", {"bp_hold_threshold": 100.0}, None
            ),
        )
    )


def test_a_value_that_differs_needs_an_approved_range(ranged: Any) -> None:
    record = TemplateInstance(
        TemplateId.HOLD, "hold-params", {"bp_hold_threshold": 90.0}, None
    )
    with pytest.raises(m.PlanFeasibilityError, match="bp_hold_threshold"):
        monitor().load(plan_with(REG, record))  # F0 has no override
    mon = monitor(registry=ranged, lib=load_lib(ranged), config=make_config(ranged))
    mon.load(plan_with(ranged, record))
    for outside in (79.9, 100.1):
        with pytest.raises(m.PlanFeasibilityError, match="bp_hold_threshold"):
            monitor(
                registry=ranged, lib=load_lib(ranged), config=make_config(ranged)
            ).load(
                plan_with(
                    ranged,
                    TemplateInstance(
                        TemplateId.HOLD, "p", {"bp_hold_threshold": outside}, None
                    ),
                )
            )


def test_the_value_of_the_plan_is_the_one_the_instance_uses(ranged: Any) -> None:
    """G-HOLD-2: 94 mmHg against the threshold; the plan lowers the threshold to 90."""
    inputs = Inputs()
    inputs.events.append(evt("measurement", hhmm(6, 50), source="cuff"))
    inputs.samples.append(smp("bp", hhmm(6, 50), 94.0))
    inputs.events.append(evt("dispense", hhmm(7, 0), source="dispenser"))
    results = {}
    for threshold in (100.0, 90.0):
        plan = plan_with(
            ranged,
            TemplateInstance(
                TemplateId.HOLD, "hold-params", {"bp_hold_threshold": threshold}, None
            ),
        )
        mon = monitor(registry=ranged, lib=load_lib(ranged), config=make_config(ranged))
        mon.load(plan)
        rec = at_step(drive(mon, inputs, 420), f"hold@{hhmm(7, 0)}", hhmm(7, 0))
        results[threshold] = (rec.state, rec.sigma_interval.lo)
    assert results[100.0] == (m.VerdictState.VIOLATED, -6.0)
    assert results[90.0] == (m.VerdictState.SATISFIED, 4.0)


def test_a_static_instance_may_carry_its_own_window(ranged: Any) -> None:
    """sched_window of 32 steps: the decision step moves by two steps."""
    own = TemplateInstance(
        TemplateId.SCHED, f"sched@{TICK}", {"sched_window": 1_920_000.0}, TICK
    )
    mon = monitor(registry=ranged, lib=load_lib(ranged), config=make_config(ranged))
    mon.load(plan_with(ranged, own))
    records = drive(mon, Inputs(), 575)
    mine = by_key(records)[f"sched@{TICK}"]
    assert all(r.pending_until_ms == TICK + 1_920_000 for r in mine)
    deciding = next(r for r in mine if r.state is m.VerdictState.VIOLATED)
    assert deciding.decided_at_ms == TICK + 1_920_000


@pytest.mark.parametrize(
    ("instance", "match"),
    [
        (
            TemplateInstance(
                TemplateId.SCHED, "a", {"sched_window": 1_950_000.0}, TICK
            ),
            "sched_window",
        ),  # 32.5 steps
        (
            TemplateInstance(
                TemplateId.SCHED, "a", {"sched_window": 5_000_000.0}, TICK
            ),
            "sched_window",
        ),  # outside
        (
            TemplateInstance(TemplateId.SCHED, "a", {"no_such_name": 1.0}, TICK),
            "no_such_name",
        ),
        (
            TemplateInstance(TemplateId.SCHED, "a", {"dose_max_24h": 1.0}, TICK),
            "dose_max_24h",
        ),  # not a SCHED name
        (
            TemplateInstance(
                TemplateId.SCHED, "a", {"sched_window": float("nan")}, TICK
            ),
            "sched_window",
        ),
        (
            TemplateInstance(
                TemplateId.SCHED, "a", {"sched_window": float("inf")}, TICK
            ),
            "sched_window",
        ),
        (
            TemplateInstance(
                TemplateId.RESP,
                "r",
                {"delta1": 10_800_000.0, "delta2": 3_600_000.0},
                None,
            ),
            "delta1",
        ),
        (
            TemplateInstance(TemplateId.RESP, "r", {"delta1": 3_630_000.0}, None),
            "delta1",
        ),  # unaligned
    ],
)
def test_an_infeasible_plan_is_rejected_naming_the_parameter(
    ranged: Any, instance: TemplateInstance, match: str
) -> None:
    mon = monitor(registry=ranged, lib=load_lib(ranged), config=make_config(ranged))
    with pytest.raises(m.PlanFeasibilityError, match=match):
        mon.load(plan_with(ranged, instance))


def test_the_alignment_error_names_the_parameter_and_the_step(ranged: Any) -> None:
    mon = monitor(registry=ranged, lib=load_lib(ranged), config=make_config(ranged))
    unaligned = TemplateInstance(
        TemplateId.SCHED, "a", {"sched_window": 1_950_000.0}, TICK
    )
    with pytest.raises(m.PlanFeasibilityError) as info:
        mon.load(plan_with(ranged, unaligned))
    assert "sched_window" in str(info.value) and str(STEP) in str(info.value)


@pytest.mark.parametrize(
    "instance",
    [
        TemplateInstance(
            TemplateId.RANGE, "x", {}, TICK
        ),  # a dynamic template has no static anchor
        TemplateInstance(TemplateId.RESP, "x", {}, TICK),
        TemplateInstance(TemplateId.COUNT, "x", {}, TICK),  # not a day-end marker
        TemplateInstance(TemplateId.COUNT, "x", {}, 0),
        TemplateInstance(TemplateId.SCHED, "x", {}, -1),
        TemplateInstance(TemplateId.SCHED, "x", {}, True),  # type: ignore[arg-type]
        TemplateInstance(TemplateId.SCHED, "x", {}, 1.5),  # type: ignore[arg-type]
        TemplateInstance(TemplateId.SCHED, "x", {}, 10**400),
        TemplateInstance(TemplateId.SCHED, "", {}, TICK),
    ],
)
def test_static_instances_are_sched_ticks_and_day_end_markers_only(
    instance: TemplateInstance,
) -> None:
    with pytest.raises((m.PlanFeasibilityError, PlanIntegrityError)):
        monitor().load(plan_with(REG, instance))


def test_instance_keys_are_unique_and_a_template_has_one_parameter_record() -> None:
    a = TemplateInstance(TemplateId.SCHED, "dup", {}, TICK)
    b = TemplateInstance(TemplateId.SCHED, "dup", {}, hhmm(10, 0))
    with pytest.raises(m.PlanFeasibilityError, match="dup"):
        monitor().load(plan_with(REG, a, b))
    two = (
        TemplateInstance(TemplateId.HOLD, "p1", {}, None),
        TemplateInstance(TemplateId.HOLD, "p2", {}, None),
    )
    with pytest.raises(m.PlanFeasibilityError, match="hold"):
        monitor().load(plan_with(REG, *two))


def test_day_end_instance_anchor_is_a_multiple_of_the_day() -> None:
    monitor().load(
        plan_with(REG, TemplateInstance(TemplateId.COUNT, f"count@{T_DAY}", {}, T_DAY))
    )
    monitor().load(
        plan_with(
            REG, TemplateInstance(TemplateId.COUNT, f"count@{2 * T_DAY}", {}, 2 * T_DAY)
        )
    )


def test_reloading_the_same_plan_does_not_duplicate_its_instances() -> None:
    mon = monitor()
    plan = make_plan(REG, sched=(TICK,))
    mon.load(plan)
    mon.load(plan)
    records = drive(mon, Inputs(), 545)
    assert len(by_key(records)[f"sched@{TICK}"]) == 6  # steps 540 to 545, once each


def test_a_new_version_may_add_future_ticks_but_not_past_ones() -> None:
    mon = monitor()
    mon.load(make_plan(REG, sched=(TICK,), plan_version=1))
    mon.advance(550 * STEP)
    mon.load(
        make_plan(REG, sched=(TICK, hhmm(12, 0)), plan_version=2)
    )  # 12:00 is still ahead
    with pytest.raises(m.PlanFeasibilityError, match="finalised"):
        mon.load(
            make_plan(REG, sched=(TICK, hhmm(9, 5)), plan_version=3)
        )  # 09:05 has been finalised
    records = drive(mon, Inputs(), 725, first_step=551)
    assert f"sched@{hhmm(12, 0)}" in {r.instance_key for r in records}


def test_the_day_end_instance_loaded_mid_day_counts_the_dispenses_already_seen() -> (
    None
):
    mon = monitor()
    mon.load(make_plan(REG))
    inputs = Inputs()
    for t in (hhmm(7, 0), hhmm(8, 0)):
        inputs.events.append(evt("dispense", t, source="dispenser"))
    drive(mon, inputs, 600)
    mon.load(make_plan(REG, day_end=(T_DAY,), plan_version=2))
    records = drive(mon, Inputs(), 601, first_step=601)
    rec = by_key(records)[f"count@{T_DAY}"][0]
    assert (rec.sigma_interval.lo, rec.sigma_interval.hi) == (
        0.0,
        float("inf"),
    )  # 2 dispenses - minimum 2


def test_entries_added_by_a_variant_are_visible_to_the_loader(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    extra = registry_variant(
        tmp_path_factory.mktemp("extra"),
        add_entries=[entry_row("clock_skew_max_ms", 500.0)],
    )
    assert extra.get("clock_skew_max_ms").value == 500.0
