"""B3, the pathway templates with raw robustness on measured values and no uncertainty (WS06-T04).

FIXTURE-ONLY numbers. The band 110 to 140 mmHg (fixture registry F0) is the illustrative band of analisi section 4.1
("illustrative, unverified"); the scripted robustness values are chosen for these tests only; none is a clinical
value and none is a claim of clinical validation. ``step_ms`` is 60 000 and ``reorder_delay_ms`` is 0 unless a test
says otherwise. Expected values are computed by hand in the comment next to them.

A "scripted evaluator" is a stub ``RawRobustnessEvaluator`` that returns a fixed list of raw robustness values, one
per step of the day, and records what it was given; the real evaluator is the point evaluator of ``ralmon.monitor``
(ADR-013, outcome C: RTAMT cannot host the templates).

Reconciliations with the task text (also in the Notes of the task file): the instances of a day are created as the
monitor creates them (RANGE and SYS at MEASUREMENT events, HOLD, COUNT, RESP and INT at DISPENSE events, SCHED and
the day-end COUNT from the plan), so "a plan with three instances" of test 8 is a day with a measurement and a
dispense; the detection time of a step is the time at which the step is final (``t_eval + D``).
"""

from __future__ import annotations

import functools
import inspect
import math
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import ralmon.spec
from ralmon.attribution import Detection
from ralmon.baselines import B3PlainSTL, Detector
from ralmon.baselines.base import BaselineBase, NotFittedError, TimingConfig
from ralmon.benchmark import ObservedDay
from ralmon.signals import Event, EventKind, Sample
from ralmon.spec import (
    CarePlan,
    RobustnessUnit,
    Template,
    TemplateId,
    TemplateInstance,
    load_templates,
)
from tests.baselines.conftest import make_care_plan, make_instance
from tests.baselines.test_b5_conformal_stl import bench, evt, observed, smp
from tests.monitor.helpers import load_f0

ROOT = Path(__file__).resolve().parents[2]
B3_SOURCE = ROOT / "src" / "ralmon" / "baselines" / "b3_plain_stl.py"
RAW_SOURCE = ROOT / "src" / "ralmon" / "baselines" / "raw_robustness.py"

STEP = 60_000
T_DAY = 86_400_000
TAIL = 10 * STEP
TIMING = TimingConfig(STEP, 0, TAIL)

REGISTRY = load_f0()
LIBRARY = {t.id: t for t in load_templates(registry=REGISTRY)}


def templ(*ids: TemplateId) -> tuple[Template, ...]:
    return tuple(LIBRARY[i] for i in ids)


# ---- stubs -----------------------------------------------------------------------------------------------------------


class Scripted:
    """A ``RawRobustnessEvaluator`` that returns ``script[k]`` at step ``k`` (``None`` beyond the list)."""

    def __init__(self, unit: RobustnessUnit, script: Sequence[float | None]) -> None:
        self.unit = unit
        self.script = list(script)
        self.resets = 0
        self.instances: list[TemplateInstance] = []
        self.seen: list[tuple[int, dict[str, float | None]]] = []

    def reset(self, instance: TemplateInstance) -> None:
        self.resets += 1
        self.instances.append(instance)

    def step(self, t_ms: int, values: Mapping[str, float | None]) -> float | None:
        self.seen.append((t_ms, dict(values)))
        k = t_ms // STEP
        return self.script[k] if k < len(self.script) else None


class Factory:
    """The ``evaluator_factory`` of B3 with one script per template; it records what it created."""

    def __init__(self, scripts: Mapping[TemplateId, Sequence[float | None]]) -> None:
        self.scripts = scripts
        self.created: list[tuple[TemplateId, str | None, Scripted]] = []

    def __call__(
        self,
        template: Template,
        registry: Any,
        step_ms: int,
        anchor_kind: str | None,
    ) -> Scripted:
        evaluator = Scripted(template.unit, self.scripts.get(template.id, []))
        self.created.append((template.id, anchor_kind, evaluator))
        return evaluator

    def of(self, tid: TemplateId) -> list[Scripted]:
        return [e for t, _, e in self.created if t is tid]


def from_step(first: int, value: float, n: int = 40) -> list[float | None]:
    """``None`` before step ``first``, ``value`` from it on."""
    return [None] * first + [value] * n


def make_b3(
    templates: Sequence[Template],
    factory: Callable[..., Any] | None = None,
    *,
    timing: TimingConfig = TIMING,
    **kwargs: Any,
) -> B3PlainSTL:
    b3 = B3PlainSTL(
        templates,
        REGISTRY,
        timing=timing,
        **({} if factory is None else {"evaluator_factory": factory}),
        **kwargs,
    )
    b3.fit([], [])
    return b3


def run(
    b3: B3PlainSTL, day: ObservedDay, plan: CarePlan | None = None, evidence: Any = None
) -> list[Detection]:
    return list(b3.run(day, make_care_plan() if plan is None else plan, evidence))


def pairs(detections: Sequence[Detection]) -> list[tuple[int, float]]:
    return [(d.t_ms, d.score) for d in detections]


def measurement_day(step: int = 0) -> ObservedDay:
    return observed([], [evt(EventKind.MEASUREMENT, step)])


# ---- 4, 5 the detection rule ---------------------------------------------------------------------------------------


def test_b3_rising_edge_of_negative_robustness() -> None:
    """Test 4. Values ``[5, 3, -2, -4, 1, -1]`` at steps 0..5: negative at steps 2, 3, 5; the rising edges are steps
    2 (minus the value is 2) and 5 (the value 1); step 3 continues the violation of step 2 and is not a detection."""
    factory = Factory({TemplateId.RANGE: [5, 3, -2, -4, 1, -1]})
    out = run(make_b3(templ(TemplateId.RANGE), factory), measurement_day())
    assert pairs(out) == [(120_000, 2.0), (300_000, 1.0)]
    assert all(d.label is None for d in out)


def test_b3_zero_robustness_is_not_a_violation() -> None:
    """Test 5. ``VIOLATED iff hi < 0`` (02-interfaces.md#verdict): a robustness of exactly 0 is not a detection."""
    factory = Factory({TemplateId.RANGE: [5, 0.0, 3, 0.0, -0.0]})
    assert run(make_b3(templ(TemplateId.RANGE), factory), measurement_day()) == []


def test_b3_none_is_not_a_violation_and_minus_infinity_has_a_finite_score() -> None:
    """``None`` (no value yet) is no detection. A failed Boolean guard is minus infinity: the score is the largest
    finite number (the harness refuses an infinite score; the rule of B5)."""
    factory = Factory(
        {TemplateId.RANGE: [None, None, -math.inf, -math.inf, 4.0, -math.inf]}
    )
    out = run(make_b3(templ(TemplateId.RANGE), factory), measurement_day())
    assert pairs(out) == [(120_000, sys.float_info.max), (300_000, sys.float_info.max)]


# ---- 6, 7 raw scores, no cross-unit ordering -------------------------------------------------------------------


def _patch_scaling(monkeypatch: pytest.MonkeyPatch) -> int:
    def boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("normalisation or ranking was used by B3")

    originals = (ralmon.spec.normalise, ralmon.spec.rank_alerts)
    patched = 0
    for module in list(sys.modules.values()):
        if not getattr(module, "__name__", "").startswith("ralmon."):
            continue
        for name, original in zip(("normalise", "rank_alerts"), originals, strict=True):
            if getattr(module, name, None) is original:
                monkeypatch.setattr(module, name, boom)
                patched += 1
    return patched


def test_b3_score_is_raw_not_normalised(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test 6. RANGE returns -12 mmHg and COUNT returns -1 dose at the same step: the scores are 12.0 and 1.0, not
    the 0.6 that a scale of 20 mmHg would give for the first. ``normalise`` and ``rank_alerts`` fail if called, in
    every module that holds them."""
    assert _patch_scaling(monkeypatch) >= 3
    factory = Factory(
        {
            TemplateId.RANGE: from_step(2, -12.0),
            TemplateId.COUNT: from_step(2, -1.0),
        }
    )
    day = observed([], [evt(EventKind.MEASUREMENT, 2), evt(EventKind.DISPENSE, 2)])
    out = run(make_b3(templ(TemplateId.RANGE, TemplateId.COUNT), factory), day)
    assert sorted(pairs(out)) == [(2 * STEP, 1.0), (2 * STEP, 12.0)]


def test_b3_two_instances_same_step_both_kept() -> None:
    """Test 7. Two instances violated at one step give two detections with the same ``t_ms``, in the order of their
    ``instance_key`` (``range@...`` before ``sys@...``): a deterministic tie-break, not an order by score (the
    larger score, 5.0, comes second) and not an order across units."""
    factory = Factory(
        {TemplateId.RANGE: from_step(3, -1.0), TemplateId.SYS: from_step(3, -5.0)}
    )
    day = observed([], [evt(EventKind.MEASUREMENT, 3)])
    out = run(make_b3(templ(TemplateId.SYS, TemplateId.RANGE), factory), day)
    assert pairs(out) == [(3 * STEP, 1.0), (3 * STEP, 5.0)]
    # the same inputs give the same order whatever the order of the templates
    again = run(make_b3(templ(TemplateId.RANGE, TemplateId.SYS), factory), day)
    assert pairs(again) == pairs(out)


# ---- 8, 9, 10, 11 what the evaluators are given --------------------------------------------------------------------


def test_b3_evaluates_every_instance_of_the_plan() -> None:
    """Test 8. A measurement creates RANGE and SYS, a dispense creates INT (the instances of the monitor): three
    evaluators are created and reset, including SYS and INT, with the anchor kind of the point evaluator; a static
    SCHED of the plan and the day-end COUNT are created at step 0."""
    factory = Factory({})
    day = observed([], [evt(EventKind.MEASUREMENT, 2), evt(EventKind.DISPENSE, 5)])
    plan = make_care_plan(
        [
            make_instance(TemplateId.SCHED, "s@3", {}, 3 * STEP),
            make_instance(TemplateId.COUNT, "c-end", {}, T_DAY),
        ]
    )
    templates = templ(
        TemplateId.RANGE,
        TemplateId.SYS,
        TemplateId.INT,
        TemplateId.SCHED,
        TemplateId.COUNT,
    )
    run(make_b3(templates, factory), day, plan)
    kinds = {(t, kind, e.resets) for t, kind, e in factory.created}
    assert kinds == {
        (TemplateId.RANGE, "measurement", 1),
        (TemplateId.SYS, "measurement", 1),
        (TemplateId.INT, "dispense", 1),
        (TemplateId.SCHED, "sched_tick", 1),
        (TemplateId.COUNT, "day_end", 1),
    }
    (int_instance,) = factory.of(TemplateId.INT)[0].instances
    assert (int_instance.anchor_ms, int_instance.instance_key) == (
        5 * STEP,
        "int@300000",
    )
    # the instances created at a step were stepped from step 0 on (the point evaluator needs consecutive steps)
    assert [t for t, _ in factory.of(TemplateId.INT)[0].seen[:3]] == [
        0,
        STEP,
        2 * STEP,
    ]


def test_b3_templates_not_given_are_not_instantiated_and_records_are_passed() -> None:
    """A template that is not in the library given to B3 creates nothing. A parameter record of the plan
    (``anchor_ms`` None) is the ``param_values`` of the instances that the events create."""
    factory = Factory({})
    day = observed([], [evt(EventKind.MEASUREMENT, 2), evt(EventKind.DISPENSE, 5)])
    plan = make_care_plan(
        [make_instance(TemplateId.RANGE, "range-record", {"bp_band_high": 140.0})]
    )
    run(make_b3(templ(TemplateId.RANGE), factory), day, plan)
    assert [t for t, _, _ in factory.created] == [TemplateId.RANGE]
    (instance,) = factory.of(TemplateId.RANGE)[0].instances
    assert dict(instance.param_values) == {"bp_band_high": 140.0}


def test_b3_uses_measured_values_only() -> None:
    """Test 9. No forecaster or calibrator in the constructor. A BP sample of 152 at step 3 is in ``values["bp"]``
    at step 3 and every later step until the next BP sample (140 at step 7); before it the key is absent; no key
    that is not a signal of the trace (no forecast, no predicted value) ever appears."""
    names = set(inspect.signature(B3PlainSTL.__init__).parameters)
    assert not {n for n in names if re.search("forecast|calibrat|alpha|conformal", n)}
    factory = Factory({})
    day = observed(
        [smp("bp", 3, 152.0), smp("bp", 7, 140.0)], [evt(EventKind.MEASUREMENT, 0)]
    )
    run(make_b3(templ(TemplateId.RANGE), factory), day)
    (evaluator,) = factory.of(TemplateId.RANGE)
    by_step = {t // STEP: values for t, values in evaluator.seen}
    assert all("bp" not in by_step[k] for k in range(3))
    assert all(by_step[k]["bp"] == 152.0 for k in range(3, 7))
    assert all(by_step[k]["bp"] == 140.0 for k in range(7, 11))
    allowed = {
        "bp",
        "cuff_health",
        "inflation_ms",
        "presence",
        "meas",
        "dispense",
        "intake",
        "sched_tick",
        "auth",
        "dose_count",
        "bp_pre",
        "bp_drop",
    }
    assert set().union(*(v.keys() for v in by_step.values())) <= allowed


def test_b3_impulses_last_one_step() -> None:
    """Test 10. A DISPENSE delivered at step 4 is ``dispense == 1.0`` at step 4 and ``0.0`` at the next; a
    measurement likewise; the counter ``dose_count`` is the derived signal of the monitor."""
    factory = Factory({})
    day = observed([], [evt(EventKind.DISPENSE, 4), evt(EventKind.MEASUREMENT, 4)])
    run(make_b3(templ(TemplateId.INT, TemplateId.RANGE), factory), day)
    for tid in (TemplateId.INT, TemplateId.RANGE):
        values = {t // STEP: v for t, v in factory.of(tid)[0].seen}
        assert [values[k]["dispense"] for k in (3, 4, 5, 6)] == [0.0, 1.0, 0.0, 0.0]
        assert [values[k]["meas"] for k in (3, 4, 5)] == [0.0, 1.0, 0.0]
    count = Factory({})
    run(make_b3(templ(TemplateId.COUNT), count), day)
    values = {t // STEP: v for t, v in count.of(TemplateId.COUNT)[0].seen}
    assert values[3].get("dose_count", 0.0) == 0.0 and values[4]["dose_count"] == 1.0
    assert values[8]["dose_count"] == 1.0


def test_b3_detection_time_after_reorder_delay() -> None:
    """Test 11. A BP sample of 152 at 3 600 000 with ``reorder_delay_ms = 120 000`` is final at 3 720 000: that is
    the time of the detection (RANGE margin ``140 - 152`` = -12 mmHg, minus the value is 12), and the evaluator sees
    the sample at its device step 3 600 000 and not before."""
    steps = 3_600_000 // STEP
    delay = 120_000
    timing = TimingConfig(STEP, delay, 5 * STEP)
    day = observed([smp("bp", steps, 152.0)], [evt(EventKind.MEASUREMENT, steps)])
    b3 = make_b3(templ(TemplateId.RANGE), None, timing=timing)
    out = run(b3, day)
    assert pairs(out) == [(3_720_000, pytest.approx(12.0))]
    # the same day with the scripted evaluator shows when the sample reaches it
    factory = Factory({})
    run(make_b3(templ(TemplateId.RANGE), factory, timing=timing), day)
    (evaluator,) = factory.of(TemplateId.RANGE)
    first = min(t for t, v in evaluator.seen if v.get("bp") == 152.0)
    assert first == 3_600_000


def test_b3_second_day_uses_the_axis_of_the_day() -> None:
    """Day 1: the evaluator axis starts at 0 at the start of the day, the instance key and the detection time are on
    the continuing axis of the patient."""
    t0 = T_DAY
    event = Event(EventKind.MEASUREMENT, t0 + 2 * STEP, t0 + 2 * STEP, "dev", {}, None)
    sample = Sample("bp", t0 + 2 * STEP, t0 + 2 * STEP, 152.0, None, None)
    day = ObservedDay("p1", 1, 0, (sample,), (event,), "plan-1")
    factory = Factory({})
    out = run(make_b3(templ(TemplateId.RANGE), None), day)
    assert pairs(out) == [(t0 + 2 * STEP, pytest.approx(12.0))]
    run(make_b3(templ(TemplateId.RANGE), factory), day)
    (instance,) = factory.of(TemplateId.RANGE)[0].instances
    assert instance.anchor_ms == 2 * STEP
    assert instance.instance_key == f"range@{t0 + 2 * STEP}"


# ---- 12 knowledge: the parameters and nothing else -----------------------------------------------------------------


def test_b3_reads_all_template_params_but_no_scale_or_priority() -> None:
    """Test 12. With the logged registry and plan, every name in ``Template.params`` of the instantiated templates is
    read, and no ``scale_param``, ``priority_param`` or ``max_verdict_latency_param`` name is."""
    every = tuple(LIBRARY.values())
    b3 = make_b3(every)
    day = observed(
        [smp("bp", 0, 125.0), smp("bp", 5, 152.0), smp("bp", 8, 100.0)],
        [
            evt(EventKind.MEASUREMENT, 5),
            evt(EventKind.DISPENSE, 8),
            evt(EventKind.MEASUREMENT, 8),
        ],
    )
    plan = make_care_plan(
        [
            make_instance(TemplateId.SCHED, "sched@5", {}, 5 * STEP),
            make_instance(TemplateId.COUNT, "count-end", {}, T_DAY),
            make_instance(TemplateId.RANGE, "range-record", {}),
        ]
    )
    assert run(b3, day, plan)
    names = b3.read_log.all_names()
    wanted = {p for t in every for p in t.params}
    assert wanted <= names, wanted - names
    forbidden = (
        {t.scale_param for t in every}
        | {t.priority_param for t in every}
        | {t.max_verdict_latency_param for t in every}
    )
    assert not (names & forbidden), names & forbidden
    assert names <= wanted | {"bounds:bp"}, names - wanted
    # nothing of the days is read by fit, and nothing is refused
    assert b3.access_log.records == () and b3.access_log.denied == ()


def test_b3_fit_reads_no_day() -> None:
    """B3 has no operating parameter and nothing to fit: ``fit`` touches no day, whatever it is given."""
    b3 = B3PlainSTL(templ(TemplateId.RANGE), REGISTRY, timing=TIMING)
    train = bench(observed([smp("bp", 0, 120.0)], [], patient="t"))
    calib = bench(observed([smp("bp", 0, 125.0)], [], patient="c"))
    b3.fit([train], [calib])
    assert b3.access_log.records == () and b3.access_log.denied == ()
    assert b3.is_fitted


# ---- 13 evidence, labels -------------------------------------------------------------------------------------------


def test_b3_ignores_evidence_and_never_labels() -> None:
    """Test 13. The output is identical with and without an ``EvidenceVector`` and every label is ``None``."""
    factory = Factory({TemplateId.RANGE: [5, 3, -2, -4, 1, -1]})
    b3 = make_b3(templ(TemplateId.RANGE), factory)
    day = measurement_day()
    plain = run(b3, day)
    with_evidence = run(b3, day, None, {"range@0": object()})
    assert plain == with_evidence and plain
    assert all(d.label is None for d in plain + with_evidence)


# ---- 14 causality --------------------------------------------------------------------------------------------------


@functools.lru_cache(maxsize=3)
def real_b3(delay_steps: int) -> B3PlainSTL:
    every = templ(
        TemplateId.RANGE,
        TemplateId.SYS,
        TemplateId.HOLD,
        TemplateId.COUNT,
        TemplateId.RESP,
        TemplateId.INT,
    )
    b3 = B3PlainSTL(
        every, REGISTRY, timing=TimingConfig(STEP, delay_steps * STEP, 60 * STEP)
    )
    b3.fit([], [])
    return b3


@settings(max_examples=60, deadline=None)
@given(
    bp=st.lists(
        st.tuples(st.integers(0, 30), st.integers(60, 200), st.integers(0, 3)),
        min_size=1,
        max_size=6,
    ),
    cuff=st.lists(
        st.tuples(st.integers(0, 30), st.sampled_from([0, 1]), st.integers(0, 3)),
        max_size=3,
    ),
    events=st.lists(
        st.tuples(
            st.sampled_from(
                [EventKind.MEASUREMENT, EventKind.DISPENSE, EventKind.INTAKE]
            ),
            st.integers(0, 30),
            st.integers(0, 3),
        ),
        min_size=1,
        max_size=6,
    ),
    cut=st.integers(0, 40),
    delay_steps=st.integers(0, 2),
)
def test_b3_is_causal_property(
    bp: list[tuple[int, int, int]],
    cuff: list[tuple[int, int, int]],
    events: list[tuple[EventKind, int, int]],
    cut: int,
    delay_steps: int,
) -> None:
    """Test 14. The detections with ``t_ms <= T`` are the same for the full day and for the day cut to the inputs
    received by ``T`` (real evaluator, six templates, arrival delays of up to three steps)."""
    samples = [smp("bp", s, v, s + d) for s, v, d in bp]
    samples += [smp("cuff_health", s, v, s + d) for s, v, d in cuff]
    items = [evt(k, s, s + d) for k, s, d in events]
    full = observed(samples, items)
    horizon = cut * STEP
    truncated = observed(
        [s for s in samples if s.t_rx_ms <= horizon],
        [e for e in items if e.t_rx_ms <= horizon],
    )
    b3 = real_b3(delay_steps)
    plan = make_care_plan()
    a = [d for d in b3.run(full, plan, None) if d.t_ms <= horizon]
    b = [d for d in b3.run(truncated, plan, None) if d.t_ms <= horizon]
    assert a == b


def test_b3_is_deterministic() -> None:
    day = observed(
        [smp("bp", 0, 125.0), smp("bp", 5, 152.0)],
        [evt(EventKind.MEASUREMENT, 5), evt(EventKind.DISPENSE, 8)],
    )
    outputs = [tuple(real_b3(0).run(day, make_care_plan(), None)) for _ in range(2)]
    other = B3PlainSTL(templ(*LIBRARY), REGISTRY, timing=TIMING)
    other.fit([], [])
    outputs.append(tuple(other.run(day, make_care_plan(), None)))
    assert outputs[0] == outputs[1]
    assert outputs[2] and all(isinstance(d, Detection) for d in outputs[2])


# ---- 15 the real evaluator, hand derivation ------------------------------------------------------------------------


def test_b3_range_template_matches_hand_derivation() -> None:
    """Test 15 (integration, real evaluator). RANGE with the test-local band 110 to 140 mmHg (illustrative,
    unverified) and measurements of 125, 152 and 105 mmHg at steps 3, 6 and 9.

    Derivation from ``formula_past_time = historically(meas -> (bp >= bp_band_low and bp <= bp_band_high))``. The
    trigger ``meas`` is true by construction inside an instance (docs/formal/02-templates.md section 2.1, item 4),
    so the instance reduces to its margin atom at the anchor step: ``min(bp - 110, 140 - bp)`` = ``min(15, 15)`` =
    15 for 125, ``min(42, -12)`` = -12 for 152, ``min(-5, 35)`` = -5 for 105. The measurement indicator contributes
    ``+inf`` at the steps where it is 1 and a failed guard only where an instance had no measurement, which the
    anchor step excludes. Violation is strictly negative: 152 and 105 are detected at their steps (360 000 and
    540 000 ms) with the scores 12 and 5; 125 is not.
    """
    day = observed(
        [smp("bp", 3, 125.0), smp("bp", 6, 152.0), smp("bp", 9, 105.0)],
        [
            evt(EventKind.MEASUREMENT, 3),
            evt(EventKind.MEASUREMENT, 6),
            evt(EventKind.MEASUREMENT, 9),
        ],
    )
    out = run(make_b3(templ(TemplateId.RANGE)), day)
    assert [(d.t_ms, d.score) for d in out] == [
        (360_000, pytest.approx(12.0)),
        (540_000, pytest.approx(5.0)),
    ]
    assert all(d.label is None for d in out)


# ---- the monitor and B3 agree on the measured decisions ----------------------------------------------------------------


def _all_template_day() -> tuple[CarePlan, ObservedDay]:
    def m(h: int, mm: int = 0) -> int:
        return 60 * h + mm

    plan = make_care_plan(
        [
            make_instance(TemplateId.SCHED, "s8", {}, m(8) * STEP),
            make_instance(TemplateId.SCHED, "s14", {}, m(14) * STEP),
            make_instance(TemplateId.COUNT, "c-end", {}, T_DAY),
        ]
    )
    samples = [
        smp("bp", m(8), 150.0),
        smp("cuff_health", m(8), 0.0),
        smp("inflation_ms", m(8), 40000.0),
        smp("bp", m(9, 10), 95.0),
        smp("cuff_health", m(9, 10), 1.0),
        smp("bp", m(10), 130.0),
        smp("bp", m(11, 30), 118.0),
        smp("presence", m(8, 3), 1.0),
        smp("bp", m(14, 40), 125.0),
        smp("cuff_health", m(14, 40), 1.0),
        smp("inflation_ms", m(14, 40), 40000.0),
    ]
    events = [
        evt(EventKind.MEASUREMENT, m(8)),
        evt(EventKind.DISPENSE, m(8, 5)),
        evt(EventKind.INTAKE, m(8, 6)),
        evt(EventKind.MEASUREMENT, m(9, 10)),
        evt(EventKind.DISPENSE, m(9, 15)),
        evt(EventKind.DISPENSE, m(10, 5)),
        evt(EventKind.MEASUREMENT, m(10)),
        evt(EventKind.MEASUREMENT, m(11, 30)),
        evt(EventKind.MEASUREMENT, m(14, 40)),
    ]
    return plan, observed(samples, events)


def _monitor_violations(
    day: ObservedDay, plan: CarePlan, delay_steps: int, tids: Sequence[TemplateId]
) -> tuple[dict[str, int], Any]:
    """The first VIOLATED record of each instance of ``run_offline_detailed`` (time of the step) and the result."""
    from ralmon.monitor import run_offline_detailed
    from tests.monitor.helpers import make_config

    result = run_offline_detailed(
        day,
        plan,
        make_config(REGISTRY, d_ms=delay_steps * STEP),
        None,
        None,
        registry=REGISTRY,
        templates=templ(*tids),
    )
    first: dict[str, int] = {}
    for r in result.records:
        if r.state.value == "violated" and r.instance_key not in first:
            first[r.instance_key] = r.t_eval_ms
    return first, result


@pytest.mark.parametrize("delay_steps", [0, 2])
def test_b3_decisions_agree_with_the_monitor(delay_steps: int) -> None:
    """The first violated record of each instance of ``run_offline`` and the detection of B3 are at the same device
    step for all seven templates (hand-built day, fixture registry); a step is final ``D`` later, so the detection
    time is the record time plus ``D``. This checks the signal construction and the instance creation."""
    plan, day = _all_template_day()
    first, _ = _monitor_violations(day, plan, delay_steps, tuple(LIBRARY))
    assert len(first) == 7  # range, sys, range, hold, count, resp, sched
    expected = sorted(t + delay_steps * STEP for t in first.values())
    b3 = B3PlainSTL(
        tuple(LIBRARY.values()),
        REGISTRY,
        timing=TimingConfig(STEP, delay_steps * STEP, 25 * 60 * STEP),
    )
    b3.fit([], [])
    out = run(b3, day, plan)
    assert [d.t_ms for d in out] == expected
    assert all(d.label is None and math.isfinite(d.score) for d in out)


def _report(step: int, colocated: bool) -> Event:
    t = step * STEP
    return Event(
        EventKind.NODE_STATE,
        t,
        t,
        "robot",
        {"state": "active", "colocated": colocated},
        None,
    )


def _visit_day(with_reports: bool) -> ObservedDay:
    """One robot visit 07:00 to 07:10 with a presence sample at 07:00, a dispense at 08:00 with the robot away."""
    events = [evt(EventKind.DISPENSE, 8 * 60)]
    if with_reports:
        events += [_report(7 * 60, True), _report(7 * 60 + 10, False)]
    return observed([smp("presence", 7 * 60, 1.0)], events)


@pytest.mark.parametrize("delay_steps", [0, 2])
def test_b3_presence_follows_the_colocation_reports_like_the_monitor(
    delay_steps: int,
) -> None:
    """ADR-054 (b). The dispense at 08:00 finds the robot away. With the reports (arrival 07:00, departure 07:10) the
    channel is down at 08:00: INT is not decided (not violated) and the gate is 0. Without any report the level of the
    07:00 sample is held, 60 minutes old against a window of 5: the witness is too old, INT is violated by graded
    lateness, and the gate counts the sample. B3 and the monitor give the same answer in both cases."""
    plan = make_care_plan()
    for with_reports in (True, False):
        day = _visit_day(with_reports)
        first, result = _monitor_violations(day, plan, delay_steps, [TemplateId.INT])
        b3 = B3PlainSTL(
            templ(TemplateId.INT),
            REGISTRY,
            timing=TimingConfig(STEP, delay_steps * STEP, 3 * 60 * STEP),
        )
        b3.fit([], [])
        out = run(b3, day, plan)
        assert [d.t_ms for d in out] == sorted(
            t + delay_steps * STEP for t in first.values()
        ), with_reports
        stats = b3.run_stats
        assert stats is not None
        gate = result.stats.presence_samples_without_availability_marks
        assert stats.presence_samples_without_availability_marks == gate
        assert gate == (0 if with_reports else 1)
        assert b3.int_gate_passed is with_reports
        assert bool(out) is (not with_reports)
        assert stats.availability_reports == (2 if with_reports else 0)


def test_b3_run_stats_before_any_run_and_after_a_second_day() -> None:
    b3 = B3PlainSTL(templ(TemplateId.INT), REGISTRY, timing=TIMING)
    assert b3.run_stats is None
    b3.fit([], [])
    run(b3, _visit_day(False))
    assert b3.run_stats is not None
    assert b3.run_stats.presence_samples_without_availability_marks == 1
    run(b3, _visit_day(True))  # the counters belong to the last run only
    assert b3.run_stats.presence_samples_without_availability_marks == 0


# ---- the class, its source and its documentation ------------------------------------------------------------------------


def test_b3_signature_name_and_protocol() -> None:
    b3 = B3PlainSTL(templ(TemplateId.RANGE), REGISTRY, timing=TIMING)
    assert b3.name == "B3" and B3PlainSTL.name == "B3"
    assert isinstance(b3, BaselineBase) and isinstance(b3, Detector)
    assert not hasattr(B3PlainSTL, "__ralmon_stub_owner__")
    with pytest.raises(NotFittedError):
        run(b3, measurement_day())


def test_b3_constructor_validation() -> None:
    with pytest.raises(ValueError, match="at least one"):
        B3PlainSTL((), REGISTRY, timing=TIMING)
    with pytest.raises(ValueError, match="twice"):
        B3PlainSTL(templ(TemplateId.RANGE, TemplateId.RANGE), REGISTRY, timing=TIMING)
    with pytest.raises(ValueError, match="divide the day"):
        B3PlainSTL(
            templ(TemplateId.RANGE), REGISTRY, timing=TimingConfig(7 * STEP, 0, 0)
        )


def test_b3_docstring_states_what_b3_is_not_and_the_hyperparameter_rule() -> None:
    doc = inspect.getdoc(B3PlainSTL) or ""
    assert "Hyperparameter selection" in doc
    for phrase in ("normalis", "ranking", "interval", "verdict", "uncertainty"):
        assert phrase in doc, phrase
    parameters = inspect.signature(B3PlainSTL.__init__).parameters
    assert "alpha" not in parameters and "threshold" not in parameters


def test_b3_source_has_no_latent_scaling_or_conformal_tokens() -> None:
    """The Done-when grep: neither module names the latent trace, the ground truth, the normalisation, the ranking,
    the scale and priority parameters, a conformal calibrator or a forecaster; no clinical constant."""
    tokens = (
        "normalise",
        "rank_alerts",
        "scale_param",
        "priority_param",
        "Conformal",
        "Forecaster",
        "LatentDay",
        "GroundTruthEvent",
    )
    for path in (B3_SOURCE, RAW_SOURCE):
        source = path.read_text(encoding="utf-8")
        for token in tokens:
            assert token not in source, (path.name, token)
        assert re.search(r"\b(110|140)\b", source) is None, path.name


def test_b3_exported_from_the_package() -> None:
    from ralmon import baselines

    assert baselines.B3PlainSTL is B3PlainSTL
    assert "B3PlainSTL" in baselines.__all__
