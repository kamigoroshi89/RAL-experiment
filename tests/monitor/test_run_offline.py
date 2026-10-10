"""``run_offline`` and the isolation of the monitor (WS05-T04 tests 27 to 29).

``run_offline`` pushes every input with ``t_rx_ms <= t_k + D`` and then calls ``advance(t_k + D)`` for
each grid step of the day, ``k = 0..K`` (WS05 README D5). The keyword-only ``registry``, ``templates``
and ``verifier`` are additive to the contract signature (pending acceptance of ADR-047 and ADR-048).
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import random
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

import ralmon.monitor as m
from ralmon.spec import HmacSha256PlanVerifier, PlanIntegrityError

from . import helpers
from .helpers import (
    SRC_MONITOR,
    STEP,
    T_DAY,
    Inputs,
    LocalDay,
    by_key,
    golden_patient_day,
    hhmm,
    load_f0,
    load_lib,
    make_config,
    make_plan,
)
from .scenarios import SETTINGS, Scenario, scenarios

REG = load_f0()
LIB = load_lib(REG)
K = T_DAY // STEP


def day_of(inputs: Inputs, **kwargs: Any) -> LocalDay:
    return LocalDay(tuple(inputs.samples), tuple(inputs.events), **kwargs)


def manual(day: LocalDay, plan: Any, config: Any) -> tuple[Any, ...]:
    """The documented cadence, written out by hand against the public methods."""
    mon = m.StreamingMonitor(config, REG, LIB)
    mon.load(plan)
    items = Inputs(list(day.samples), list(day.events)).merged()
    pointer, out = 0, []
    for k in range(K + 1):
        t = k * STEP + config.reorder_delay_ms
        while pointer < len(items) and items[pointer][0] <= t:
            obj = items[pointer][4]
            (mon.push_sample if items[pointer][3] == "sample" else mon.push_event)(obj)
            pointer += 1
        out += list(mon.advance(t))
    return tuple(out)


# ---------------------------------------------------------------------------------------------
# test 27
# ---------------------------------------------------------------------------------------------


def test_run_offline_equals_manual_stream_feed_on_the_worked_day() -> None:
    golden = golden_patient_day()
    inputs = helpers.Inputs(
        helpers.samples_of(golden["observed_day"]),
        helpers.events_of(golden["observed_day"]),
    )
    static = [
        (i["template"], i["instance_key"], i["anchor_ms"])
        for i in golden["plan"]["static_instances"]
    ]
    from ralmon.spec import CarePlan, TemplateId, TemplateInstance

    plan = CarePlan(
        "PD-1-plan",
        "hypertension-fixture",
        "PD-1-patient",
        REG.version(),
        tuple(TemplateInstance(TemplateId(t), k, {}, a) for t, k, a in static),
        (),
        1,
        None,
    )
    for d_ms in (0, 30_000):
        config = make_config(REG, d_ms=d_ms)
        want = manual(day_of(inputs), plan, config)
        got = m.run_offline(
            day_of(inputs), plan, config, None, None, registry=REG, templates=LIB
        )
        assert tuple(got) == want
        assert len(want) > 1000  # SCHED refinement records included
        assert got[-1].t_eval_ms <= T_DAY


@SETTINGS
@given(scenarios(), st.integers(0, 2**32 - 1), st.sampled_from([0, 30_000]))
def test_run_offline_equals_manual_stream_feed_with_transport_delays(
    scn: Scenario, seed: int, d_ms: int
) -> None:
    rng = random.Random(seed)
    inputs = scn.to_inputs()
    delayed = Inputs()
    for s in (
        inputs.samples
    ):  # some inputs are late (delay beyond D): they must be excluded identically
        delayed.samples.append(
            dataclasses.replace(
                s, t_rx_ms=s.t_device_ms + rng.choice([0, 0, 5_000, 90_000])
            )
        )
    for e in inputs.events:
        delayed.events.append(
            dataclasses.replace(
                e, t_rx_ms=e.t_device_ms + rng.choice([0, 0, 5_000, 90_000])
            )
        )
    plan = make_plan(REG, sched=scn.ticks, day_end=scn.day_end_anchors())
    config = make_config(REG, d_ms=d_ms)
    want = manual(day_of(delayed), plan, config)
    got = m.run_offline(
        day_of(delayed), plan, config, None, None, registry=REG, templates=LIB
    )
    assert tuple(got) == want


def test_run_offline_advances_at_t_k_plus_d_after_pushing_what_has_arrived() -> None:
    """V-LATE-1 and V-LATE-2 through ``run_offline``: the watermark decides, the day is one slice."""
    tick = hhmm(9, 0)
    for rx, state in (
        (34_240_000, m.VerdictState.VIOLATED),
        (34_210_000, m.VerdictState.SATISFIED),
    ):
        inputs = Inputs()
        inputs.events.append(helpers.evt("schedule_tick", tick, source="care_plan"))
        inputs.events.append(
            helpers.evt("measurement", 34_190_000, rx=rx, source="cuff")
        )
        plan = make_plan(REG, sched=(tick,))
        records = m.run_offline(
            day_of(inputs),
            plan,
            make_config(REG, d_ms=30_000),
            None,
            None,
            registry=REG,
            templates=LIB,
        )
        rec = helpers.at_step(records, f"sched@{tick}", 34_200_000)
        assert rec.state is state
        assert rec.decided_at_ms == 34_200_000


def test_run_offline_covers_the_closing_step_and_leaves_open_instances_pending() -> (
    None
):
    """CP7: the response window of a 21:02 dispense ends after 24:00; the instance is PENDING at K."""
    inputs = Inputs()
    inputs.events.append(helpers.evt("measurement", hhmm(20, 32), source="cuff"))
    inputs.samples.append(helpers.smp("bp", hhmm(20, 32), 152.0))
    inputs.events.append(helpers.evt("dispense", hhmm(21, 2), source="dispenser"))
    plan = make_plan(REG, day_end=(T_DAY,))
    records = m.run_offline(
        day_of(inputs), plan, make_config(REG), None, None, registry=REG, templates=LIB
    )
    resp = by_key(records)[f"resp@{hhmm(21, 2)}"]
    assert resp[-1].t_eval_ms == T_DAY and resp[-1].state is m.VerdictState.PENDING
    assert resp[-1].pending_until_ms == T_DAY + 120_000
    assert resp[-1].decided_at_ms is None


def test_run_offline_is_deterministic_and_returns_a_sequence_of_records() -> None:
    inputs = Inputs()
    inputs.events.append(helpers.evt("dispense", hhmm(7, 0), source="dispenser"))
    plan = make_plan(REG)
    config = make_config(REG)
    a = m.run_offline(
        day_of(inputs), plan, config, None, None, registry=REG, templates=LIB
    )
    b = m.run_offline(
        day_of(inputs), plan, config, None, None, registry=REG, templates=LIB
    )
    assert a == b and len(a) > 0
    assert all(isinstance(r, m.VerdictRecord) for r in a)


# ---------------------------------------------------------------------------------------------
# test 28: default registry and templates, explicit overrides
# ---------------------------------------------------------------------------------------------


def test_run_offline_default_registry_and_templates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ralmon.monitor import offline

    calls: dict[str, list[Any]] = {"registry": [], "templates": []}

    def fake_registry(*args: Any, **kwargs: Any) -> Any:
        calls["registry"].append((args, kwargs))
        return REG

    def fake_templates(*args: Any, **kwargs: Any) -> Any:
        calls["templates"].append((args, kwargs))
        return LIB

    monkeypatch.setattr(offline, "load_registry", fake_registry)
    monkeypatch.setattr(offline, "load_templates", fake_templates)
    config = make_config(REG)
    plan = make_plan(REG)
    m.run_offline(day_of(Inputs()), plan, config, None, None)
    assert calls["registry"] == [
        ((), {"step_ms": STEP})
    ]  # the registry is built from the config step
    assert len(calls["templates"]) == 1 and calls["templates"][0][1] == {
        "registry": REG
    }
    # explicit arguments override the defaults: nothing is loaded
    calls["registry"].clear()
    calls["templates"].clear()
    m.run_offline(
        day_of(Inputs()), plan, config, None, None, registry=REG, templates=LIB
    )
    assert calls == {"registry": [], "templates": []}
    # a registry given but no templates: the templates are read against that registry
    m.run_offline(day_of(Inputs()), plan, config, None, None, registry=REG)
    assert calls["registry"] == [] and calls["templates"][0][1] == {"registry": REG}


def test_run_offline_verifier_override() -> None:
    verifier = HmacSha256PlanVerifier(b"another-test-key")
    plan = make_plan(REG, sched=(hhmm(9, 0),))
    signed = dataclasses.replace(plan, signature=verifier.sign(plan))
    config = make_config(REG)
    m.run_offline(
        day_of(Inputs()),
        signed,
        config,
        None,
        None,
        registry=REG,
        templates=LIB,
        verifier=verifier,
    )
    with pytest.raises(PlanIntegrityError):
        m.run_offline(
            day_of(Inputs()), signed, config, None, None, registry=REG, templates=LIB
        )


def test_run_offline_signature() -> None:
    sig = inspect.signature(m.run_offline)
    params = list(sig.parameters.values())
    assert [p.name for p in params[:5]] == [
        "day",
        "plan",
        "config",
        "calibrator",
        "forecaster",
    ]
    extra = {p.name: p for p in params[5:]}
    assert set(extra) == {"registry", "templates", "verifier", "history"}
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in extra.values())
    assert all(p.default is None for n, p in extra.items() if n != "history")
    assert extra["history"].default == ()  # ADR-046, WS05-T10


def test_run_offline_with_the_real_defaults_loads_and_runs() -> None:
    """The real registry and the real library, no value pinned: a plan pins the registry version."""
    from ralmon.spec import load_registry

    real = load_registry(step_ms=STEP)
    config = make_config(real)
    plan = make_plan(real)
    records = m.run_offline(day_of(Inputs()), plan, config, None, None)
    assert (
        tuple(records) == ()
    )  # no instance in a day without input and without static instances


# ---------------------------------------------------------------------------------------------
# test 29 and the isolation of the monitor: no ground truth, no look-ahead into other packages
# ---------------------------------------------------------------------------------------------

FORBIDDEN_NAMES = ("LatentDay", "GroundTruthEvent", "BenchmarkDay")


def test_monitor_sources_do_not_reference_ground_truth() -> None:
    files = sorted(SRC_MONITOR.rglob("*.py"))
    assert len(files) >= 8  # the scan covers the real modules
    for path in files:
        text = path.read_text(encoding="utf-8")
        for name in FORBIDDEN_NAMES:
            assert name not in text, f"{path.name} mentions {name}"


def test_monitor_imports_only_signals_and_spec_of_the_package() -> None:
    allowed = {"signals", "spec"}
    seen: set[str] = set()
    for path in sorted(SRC_MONITOR.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            targets: list[str] = []
            if isinstance(node, ast.Import):
                targets = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                targets = [node.module]
            for target in targets:
                parts = target.split(".")
                if (
                    parts[0] == "ralmon"
                    and len(parts) > 1
                    and parts[1] not in {"monitor", "_stub"}
                ):
                    seen.add(parts[1])
                    assert parts[1] in allowed, f"{path.name} imports {target}"
                    assert len(parts) == 2, (
                        f"{path.name} imports {target} (package roots only)"
                    )
    assert seen == allowed


def test_run_offline_never_reads_the_latent_or_the_truth_of_a_day() -> None:
    class Guarded(LocalDay):
        @property
        def latent(self) -> Any:  # a BenchmarkDay-like carrier must never be read
            raise AssertionError("the monitor read the latent trace")

        @property
        def ground_truth(self) -> Any:
            raise AssertionError("the monitor read the ground truth")

    inputs = Inputs()
    inputs.events.append(helpers.evt("dispense", hhmm(7, 0), source="dispenser"))
    day = Guarded(tuple(inputs.samples), tuple(inputs.events))
    records = m.run_offline(
        day, make_plan(REG), make_config(REG), None, None, registry=REG, templates=LIB
    )
    assert len(records) > 0
