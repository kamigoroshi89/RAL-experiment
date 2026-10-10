"""Fairness audit of the baselines B1 to B5 (WS06-T07; analisi section 10 objection 1, "whoever writes the
specification wins").

What is audited. That every baseline receives the clinical knowledge of the proposed method that its definition allows
(bands and schedules for B1, all seven templates for B3 and B5), sees the same inputs at the same time, never reads a
latent trace or ground truth at inference, and is fitted and calibrated only on data that the proposed method may also
use. The tests run the five baselines and the monitor of the proposed method on the same poisoned days and the same
test day and assert on the logs; the knowledge matrix of the audit note is regenerated from the same run.

FIXTURE-ONLY numbers. Parameter values are the rows of the fixture registry F0 (illustrative, unverified, ADR-027);
the operating parameters are test values; none is a clinical value and none is a claim of clinical validation.

What the audit does not prove (``access.py``): the guards are a defence against accidents plus an audit log, not a
sandbox; the logs are as complete as the code paths that use the wrappers. The audit shows what well-behaved baselines
read, not that no baseline could read more.

Reconciliations with the task text, each recorded in the audit note: the knowledge set K also holds the names that the
monitor itself reads (physiological bounds, two global parameters), because the monitor reads them; tests 11, 12 and 15
hold in the documented-difference form that the hand-overs of WS06-T01 and WS06-T06 describe.
"""

from __future__ import annotations

import inspect
import math
import re
import sys
from pathlib import Path
from typing import Any

import pytest

import ralmon.baselines as baselines_package
from ralmon.baselines import (
    B1StaticThresholds,
    B2AnomalyDetection,
    B3PlainSTL,
    B4ConformalOnly,
    B5ConformalSTL,
    Detector,
)
from ralmon.baselines.access import AccessPolicy, LeakageError, Split
from ralmon.baselines.audit import (
    AuditDays,
    AuditError,
    assert_b1_not_vacuous,
    knowledge_set,
    render_markdown,
    render_probe_table,
    run_audit,
)
from ralmon.baselines.b1_static_thresholds import ROLE_PARAMETERS
from ralmon.baselines.base import BaselineBase, TimingConfig
from ralmon.benchmark import BenchmarkDay, ObservedDay
from ralmon.monitor import (
    PersistenceForecaster,
    build_calibration_episodes,
    run_offline_detailed,
)
from ralmon.spec import Template, TemplateId
from tests.baselines.conftest import (
    ACT_STEP,
    AUDIT_ALPHA,
    AUDIT_DELAY_MS,
    AUDIT_STEP_MS,
    AUDIT_TAIL_MS,
    AUDIT_TIMING,
    CALIB_DROPS,
    T_DAY_MS,
    Audit,
    AuditSetup,
    build_audit,
    build_audit_setup,
    evidence_mapping,
    make_benchmark_day,
    make_care_plan,
    make_full_plan,
    poisoned_days,
    response_day,
)
from tests.monitor.helpers import make_config

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "ralmon"
NOTE = (
    ROOT
    / "docs"
    / "plan"
    / "workstreams"
    / "WS06-baselines"
    / "notes"
    / "fairness-audit.md"
)
NAMES = ("B1", "B2", "B3", "B4", "B5")
STEP = AUDIT_STEP_MS


@pytest.fixture(scope="module")
def audit() -> Audit:
    """One audit run (fit on poisoned days, run on the test day, the monitor of the proposed method, the probes)."""
    return build_audit()


def _scale_priority_latency(templates: tuple[Template, ...]) -> frozenset[str]:
    names: set[str] = set()
    for t in templates:
        names.update((t.scale_param, t.priority_param, t.max_verdict_latency_param))
    return frozenset(names)


# ---- 1, 2 names and shared timing ------------------------------------------------------------------------------------


def test_baselines_exported_and_named(all_baselines: dict[str, BaselineBase]) -> None:
    """Test 1. The package exports ``Detector`` and the five classes; the names are B1 to B5 (a documented suffix such
    as ``B2-residual`` or ``B5-per-template`` is a variant, not used by the fixture)."""
    for exported in (
        "Detector",
        "B1StaticThresholds",
        "B2AnomalyDetection",
        "B3PlainSTL",
        "B4ConformalOnly",
        "B5ConformalSTL",
    ):
        assert exported in baselines_package.__all__
        assert hasattr(baselines_package, exported)
    classes = {
        "B1": B1StaticThresholds,
        "B2": B2AnomalyDetection,
        "B3": B3PlainSTL,
        "B4": B4ConformalOnly,
        "B5": B5ConformalSTL,
    }
    assert tuple(all_baselines) == NAMES
    for name, detector in all_baselines.items():
        assert detector.name == name
        assert isinstance(detector, classes[name])
        assert isinstance(detector, Detector)
        assert isinstance(detector, BaselineBase)
    # the suffixes that exist are documented variants of a base name
    assert B2AnomalyDetection.__doc__ is not None
    for variant, base in (("B2-residual", "B2"), ("B5-per-template", "B5")):
        assert variant.split("-")[0] == base


def test_shared_timing_configuration(
    all_baselines: dict[str, BaselineBase], audit: Audit
) -> None:
    """Test 2. All five carry the same ``step_ms``, ``reorder_delay_ms`` and ``tail_ms``, and the first two equal the
    ``MonitorConfig`` of the proposed method of the same experiment."""
    config = audit.proposed.config
    assert (config.step_ms, config.reorder_delay_ms) == (AUDIT_STEP_MS, AUDIT_DELAY_MS)
    timings = {name: det.timing for name, det in all_baselines.items()}
    assert set(timings.values()) == {AUDIT_TIMING}
    for timing in timings.values():
        assert timing.step_ms == config.step_ms
        assert timing.reorder_delay_ms == config.reorder_delay_ms
        assert timing.tail_ms == AUDIT_TAIL_MS
    # the delay is a multiple of the step: the lateness rule of the grid then equals the monitor's (open decision
    # for gab otherwise, Notes of WS06-T05); the audit says so when it is not
    assert audit.report.problems == ()


def test_audit_flags_a_delay_that_is_not_a_multiple_of_the_step(
    audit: Audit,
) -> None:
    """Open decision (D not a multiple of the step): the audit reports the configuration as a problem."""
    odd = B1StaticThresholds(
        timing=TimingConfig(STEP, 30_000, AUDIT_TAIL_MS), registry=audit.setup.registry
    )
    report = run_audit(
        [odd],
        audit.days,
        audit.plan,
        audit.setup.registry,
        templates=audit.setup.templates,
    )
    assert any("multiple" in problem for problem in report.problems)


# ---- 3, 4 no latent, no ground truth, no labels --------------------------------------------------------------------


def test_no_latent_or_ground_truth_at_inference(
    all_baselines: dict[str, BaselineBase],
    poisoned_benchmark_days: tuple[list[BenchmarkDay], list[BenchmarkDay]],
    full_plan: Any,
) -> None:
    """Test 3. With days whose latent trace and ground truth raise on any access: ``fit`` then ``run`` on the observed
    day succeeds, the access log has no ``latent`` read on either split and no ``ground_truth`` read on a calibration
    day, and ``run`` refuses a benchmark day and a latent day."""
    train, calib = poisoned_benchmark_days
    real = make_benchmark_day()
    for name, det in all_baselines.items():
        det.fit(train, calib)
        out = det.run(train[0].observed, full_plan, None)
        assert out is not None, name
        log = det.access_log
        assert log.reads(field="latent") == (), name
        assert log.reads(field="ground_truth", split=Split.CALIB) == (), name
        assert log.denied == (), name
        assert log.fields() == frozenset({"observed"}) or log.fields() == frozenset(), (
            name,
            log.fields(),
        )
        with pytest.raises(LeakageError):
            det.run(real, full_plan, None)  # type: ignore[arg-type]
        with pytest.raises(LeakageError):
            det.run(real.latent, full_plan, None)  # type: ignore[arg-type]


def test_evidence_and_labels(audit: Audit) -> None:
    """Test 4. The output is identical with ``evidence=None`` and with a populated mapping; every label is ``None``;
    every score is finite; and the runs are not vacuous (every baseline detects something on the test day)."""
    for name, det in audit.setup.detectors.items():
        bare = tuple(det.run(audit.days.test, audit.plan, None))
        with_evidence = tuple(det.run(audit.days.test, audit.plan, evidence_mapping()))
        assert bare == with_evidence, name
        assert len(bare) >= 1, name
        assert all(d.label is None for d in bare), name
        assert all(math.isfinite(d.score) for d in bare), name
        trace = audit.report.traces[name]
        assert trace.evidence_invariant and trace.signature_invariant, name


# ---- 5 to 9 the knowledge each baseline receives -----------------------------------------------------------------


def test_knowledge_is_subset_of_proposed_method(audit: Audit) -> None:
    """Test 5. The names read through the logged plan and the audited registry (in ``fit`` and in ``run``) are a
    subset of K. K is the union of ``params``, ``scale_param``, ``priority_param`` and ``max_verdict_latency_param``
    over the loaded templates (the text of the task) together with the names that the monitor of the proposed method
    reads on the same day: the physiological bounds of ``bp`` and two global parameters. The extras are exactly the
    documented ones (finding F2 of the audit note)."""
    report = audit.report
    k_task = knowledge_set(audit.setup.templates)
    assert report.knowledge_task == k_task
    ours = report.traces["ours"]
    extras = (ours.fit_reads | ours.run_reads) - k_task
    assert extras == {"bounds:bp", "clock_skew_max_ms", "cuff_error_sd"}
    assert report.knowledge == k_task | extras
    for name in NAMES:
        trace = report.traces[name]
        assert trace.fit_reads <= report.knowledge, (name, trace.fit_reads - k_task)
        assert trace.run_reads <= report.knowledge, (name, trace.run_reads - k_task)
    # the two extras are knowledge of the proposed method only: no baseline reads them
    for name in NAMES:
        trace = report.traces[name]
        assert not (
            {"clock_skew_max_ms", "cuff_error_sd"} & (trace.fit_reads | trace.run_reads)
        )


def test_b1_receives_bands_and_schedules(audit: Audit) -> None:
    """Test 6. B1's read set holds the band, hold, schedule-window and dose-limit parameters that its docstring
    declares; the minimal rule set is all that it reads; and B1 is not vacuous on the audit plan (hard check)."""
    b1 = audit.setup.detectors["B1"]
    assert isinstance(b1, B1StaticThresholds)
    declared = set(ROLE_PARAMETERS.values())
    module_doc = sys.modules[B1StaticThresholds.__module__].__doc__ or ""
    for role, name in ROLE_PARAMETERS.items():
        assert name in module_doc, (role, name)
    reads = audit.report.traces["B1"].run_reads
    assert reads == declared
    assert declared <= audit.report.knowledge
    assert audit.report.traces["B1"].fit_reads == frozenset()
    # four rules are active on the plan that carries the RANGE, HOLD and COUNT records and a SCHED instance
    b1.run(audit.days.test, audit.plan, None)
    assert b1.run_stats is not None
    assert b1.run_stats.rules_active == ("R1", "R2", "R3", "R4")
    assert_b1_not_vacuous(b1)


def test_b1_vacuity_is_a_hard_failure(audit: Audit) -> None:
    """Open decision (vacuity of B1): on a plan without parameter records only the schedule rule is active (the shape of
    the monitor's own plan helper), and the gate that WS08 calls fails loudly instead of letting a straw man run."""
    b1 = audit.setup.detectors["B1"]
    assert isinstance(b1, B1StaticThresholds)
    bare = make_care_plan(
        [i for i in audit.plan.instances if i.template is TemplateId.SCHED]
    )
    b1.run(audit.days.test, bare, None)
    assert b1.run_stats is not None
    assert b1.run_stats.rules_active == ("R3",)
    with pytest.raises(AuditError, match="R3"):
        assert_b1_not_vacuous(b1)
    b1.run(audit.days.test, audit.plan, None)  # restore the stats of the audit plan
    assert_b1_not_vacuous(b1)


def test_b3_receives_all_templates_without_normalisation(audit: Audit) -> None:
    """Test 7. B3's read set holds every ``Template.params`` name of the instantiated templates (all seven are
    instantiated on the test day) and no ``scale``, ``priority`` or verdict-latency name; the only name besides the
    template parameters is the physiological bound of ``bp``."""
    templates = audit.setup.templates
    b3 = audit.setup.detectors["B3"]
    assert isinstance(b3, B3PlainSTL)
    assert b3.run_stats is not None and b3.run_stats.instances >= 7
    params = {p for t in templates for p in t.params}
    reads = audit.report.traces["B3"].run_reads
    assert params <= reads
    assert not reads & _scale_priority_latency(templates)
    assert reads - params == {"bounds:bp"}
    assert not any(n.startswith(("scale_", "priority_", "max_latency_")) for n in reads)


def test_b5_knowledge_equals_b3_knowledge(audit: Audit) -> None:
    """Test 8. Same templates, raw robustness: B5 reads what B3 reads (in ``run``), and what B5 reads while it
    calibrates on the plans of the calibration days is inside that set."""
    b3, b5 = audit.report.traces["B3"], audit.report.traces["B5"]
    assert b5.run_reads == b3.run_reads
    assert b5.fit_reads <= b3.run_reads
    assert b3.fit_reads == frozenset()


def test_b2_and_b4_read_no_clinical_thresholds(audit: Audit) -> None:
    """Test 9. B2 and B4 read no name through the registry or the plan values, in ``fit`` or in ``run``; B2 uses
    ``plan.schedule`` only (the forest's schedule features) and B4 does not touch the plan at all."""
    for name in ("B2", "B4"):
        trace = audit.report.traces[name]
        assert trace.fit_reads == frozenset() and trace.run_reads == frozenset(), name
        assert audit.setup.detectors[name].read_log.all_names() == frozenset(), name
    assert audit.report.traces["B2"].schedule_accessed is True
    assert audit.report.traces["B4"].schedule_accessed is False


# ---- 10 the calibration target ----------------------------------------------------------------------------------


def test_calibration_target_is_shared(audit: Audit) -> None:
    """Test 10. Which ``sigma_true`` does the proposed method calibrate on? The OBSERVED completion
    (``build_calibration_episodes`` takes observed days and has no parameter that could carry a latent day; its
    ``sigma_true`` is the point evaluator on the accepted observed inputs), not the latent trace. Hence the finding F1
    of the plan (calibration on the latent trace) does not arise: B4 and B5 are NOT given
    ``AccessPolicy(calib_latent=True)``, and none of them reads a latent trace on a calibration day.

    The poisoned calibration days raise if anything but ``observed`` is read, and the three calibration targets are
    shown to be the same quantity: for the response template the score is the drop of the day, in mmHg for B5, in
    units of the response scale for the proposed method, and the largest residual of the day for B4."""
    # no baseline reads a latent trace on a calibration day, and nobody uses the exception of the policy
    for name in NAMES:
        det = audit.setup.detectors[name]
        assert det.access_policy.calib_latent is False, name
        assert det.access_log.reads(field="latent") == (), name
        assert not any(r.by_exception for r in det.access_log.records), name
    # the construction of the proposed method: observed days only
    parameters = inspect.signature(build_calibration_episodes).parameters
    assert list(parameters)[:4] == ["days", "plans", "config", "forecaster"]
    assert not any("latent" in p or "truth" in p for p in parameters)
    sources = (SRC / "monitor" / "offline.py").read_text(encoding="utf-8") + (
        SRC / "monitor" / "predictive.py"
    ).read_text(encoding="utf-8")
    body = sources.split("def _observed_sigma_true", 1)[1].split("\ndef ", 1)[0]
    assert "latent" not in body.lower().replace("never replaced by a latent", "")
    for token in ("LatentDay", "GroundTruthEvent", ".latent", ".ground_truth"):
        assert token not in sources, token
    with pytest.raises(Exception):  # noqa: B017 - a benchmark day is not an observed trace
        build_calibration_episodes(
            audit.days.calib[:1],  # type: ignore[arg-type]
            [audit.setup.plan_for_day(audit.days.calib[0].observed)],
            audit.proposed.config,
            PersistenceForecaster(AUDIT_STEP_MS),
            registry=audit.setup.registry,
            templates=audit.setup.templates,
        )
    # the three targets, from the poisoned days (a read of the latent trace would have raised)
    scale = float(audit.setup.registry.get("scale_resp").value)
    b5 = audit.setup.detectors["B5"]
    assert isinstance(b5, B5ConformalSTL)
    assert sorted(e.sigma_true - e.sigma_hat for e in b5.calibration_episodes) == (
        pytest.approx(sorted(float(d) for d in CALIB_DROPS))
    )
    episodes, censored = build_calibration_episodes(
        [d.observed for d in audit.days.calib],
        [audit.setup.plan_for_day(d.observed) for d in audit.days.calib],
        audit.proposed.config,
        PersistenceForecaster(AUDIT_STEP_MS),
        registry=audit.setup.registry,
        templates=audit.setup.templates,
    )
    assert censored == 0
    assert sorted(e.sigma_true - e.sigma_hat for e in episodes) == pytest.approx(
        sorted(d / scale for d in CALIB_DROPS)
    )
    b4 = audit.setup.detectors["B4"]
    assert isinstance(b4, B4ConformalOnly)
    assert sorted(
        e.sigma_true for e in b4.calibration_episodes if e.sigma_true > 0
    ) == pytest.approx(sorted(float(d) for d in CALIB_DROPS if d > 0))


# ---- 11 the residual of B2 and B4 -------------------------------------------------------------------------------


def test_residual_definitions_agree(audit: Audit) -> None:
    """Test 11. On the test day with the persistence stub, the residual series of B2 and of B4 are equal (signal,
    delivery step, device time, value, forecast, residual). The index rule is that of B4 (hand-over of WS05-T05), not
    the ``floor`` form of the task text."""
    b2, b4 = audit.setup.detectors["B2"], audit.setup.detectors["B4"]
    assert isinstance(b2, B2AnomalyDetection) and isinstance(b4, B4ConformalOnly)
    b2.run(audit.days.test, audit.plan, None)
    b4.run(audit.days.test, audit.plan, None)

    def key(r: Any) -> tuple[Any, ...]:
        return (r.signal, r.t_ms, r.t_device_ms, r.value, r.forecast, r.residual)

    series2 = [key(r) for r in b2.residuals]
    series4 = [key(r) for r in b4.residuals]
    assert series2 == series4
    assert len(series2) > 90
    assert {r[0] for r in series2} == {"bp", "hr_ecg", "spo2"}


# ---- 12 detection times against the monitor ---------------------------------------------------------------------


def _first_violated(
    day: ObservedDay, plan: Any, audit: Audit, templates: Any = None
) -> dict[str, int]:
    config = make_config(audit.setup.registry, d_ms=AUDIT_DELAY_MS)
    result = run_offline_detailed(
        day,
        plan,
        config,
        None,
        None,
        registry=audit.setup.registry,
        templates=audit.setup.templates if templates is None else templates,
    )
    first: dict[str, int] = {}
    for record in result.records:
        if record.state.value == "violated" and record.instance_key not in first:
            first[record.instance_key] = record.t_eval_ms
    return first


def test_b3_detection_time_equals_monitor_violation_time(audit: Audit) -> None:
    """Test 12, in the documented-difference form (hand-over of WS06-T01). The grid time of a baseline is a monitor
    time: a step ``t`` sees device times up to ``t - D``, whereas ``run_offline`` calls ``advance(k * T_s + D)``. So the
    B3 detection time is ``t_eval_ms + D`` of the first VIOLATED record, and equals it for ``D = 0``.

    The one-violation day (a pressure of 152 mmHg, out of the band) is checked for B1, B3 and B5; the day with a
    violation of each template is checked for B3 and B5, where the relation holds for six templates and for INT it does
    not (ADR-063, a separate test)."""
    registry = audit.setup.registry
    plan = make_full_plan(registry, sched_steps=(), day_end=False, ticks=())
    day = _single_violation_day()
    first = _first_violated(day, plan, audit)
    assert list(first) == ["range@6000000"]
    (t_eval,) = first.values()
    assert t_eval == 100 * STEP
    for name in ("B1", "B3", "B5"):
        out = audit.setup.detectors[name].run(day, plan, None)
        assert [d.t_ms for d in out] == [t_eval + AUDIT_DELAY_MS], name
    # D = 0: the relation is equality
    zero = TimingConfig(STEP, 0, AUDIT_TAIL_MS)
    b3 = B3PlainSTL(audit.setup.templates, registry, timing=zero)
    b3.fit([], [])
    config = make_config(registry, d_ms=0)
    result = run_offline_detailed(
        day,
        plan,
        config,
        None,
        None,
        registry=registry,
        templates=audit.setup.templates,
    )
    (zero_eval,) = [r.t_eval_ms for r in result.records if r.state.value == "violated"]
    assert [d.t_ms for d in b3.run(day, plan, None)] == [zero_eval]
    # the day with a violation of the templates (INT has none here): the relation holds for every one of them
    full_day = audit.days.test
    first_all = _first_violated(full_day, audit.plan, audit)
    expected = sorted(t + AUDIT_DELAY_MS for t in first_all.values())
    assert len(expected) == 7
    for name in ("B3", "B5"):
        out = audit.setup.detectors[name].run(full_day, audit.plan, None)
        got = sorted({d.t_ms for d in out})
        # B5 merges the instances of one step in a conjunction and adds the predicted alert: compare as sets of times
        if name == "B3":
            assert [d.t_ms for d in out] == expected
        else:
            assert set(expected) <= set(got), set(expected) - set(got)


def _single_violation_day() -> ObservedDay:
    from ralmon.signals import Event, EventKind, Sample
    from tests.baselines.conftest import make_observed_day

    return make_observed_day(
        [Sample("bp", 100 * STEP, 100 * STEP, 152.0, None, None)],
        [Event(EventKind.MEASUREMENT, 100 * STEP, 100 * STEP, "dev", {}, None)],
    )


def test_known_difference_int_violation_is_silent_in_b3_and_b5(audit: Audit) -> None:
    """ADR-063 (open decision for gab), pinned. The robot is co-located from step 470 and sees nobody; a dispense at
    step 480 has no witness. The monitor reports INT VIOLATED, B3 and B5 are silent (the point evaluator has no value
    for an interval whose upper bound is negative). No C3/INT comparison with B3 or B5 until ADR-063 is decided."""
    result = next(
        r for r in audit.probe_results if r.probe.label.startswith("integrity")
    )
    assert result.extra["ours"] >= 1
    assert result.extra["B3"] == 0
    assert result.extra["B5"] == 0


# ---- 13, 14 hyperparameter selection and operating parameters ---------------------------------------------------


@pytest.mark.parametrize(
    "cls",
    [
        B1StaticThresholds,
        B2AnomalyDetection,
        B3PlainSTL,
        B4ConformalOnly,
        B5ConformalSTL,
    ],
)
def test_hyperparameter_selection_documented(cls: type) -> None:
    assert "Hyperparameter selection" in (cls.__doc__ or "")


@pytest.mark.parametrize(
    ("cls", "names"),
    [
        (B2AnomalyDetection, ("z_threshold", "score_quantile")),
        (B4ConformalOnly, ("alpha",)),
        (B5ConformalSTL, ("alpha",)),
    ],
)
def test_operating_parameters_have_no_numeric_defaults(
    cls: type, names: tuple[str, ...]
) -> None:
    parameters = inspect.signature(cls.__init__).parameters
    for name in names:
        default = parameters[name].default
        assert default is inspect.Parameter.empty or default is None, (cls, name)
        assert not isinstance(default, (int, float)), (cls, name)
    for cls_other in (B1StaticThresholds, B3PlainSTL):
        other = inspect.signature(cls_other.__init__).parameters
        assert not {"alpha", "z_threshold", "score_quantile"} & set(other)


# ---- 15 monotone in alpha ---------------------------------------------------------------------------------------


def test_conformal_baselines_monotone_in_alpha() -> None:
    """Test 15. B4: the alarms at ``alpha = 0.05`` are a subset of those at ``0.2``. B5: the detections are NOT nested
    (hand-over of WS06-T06: a smaller level removes the predicted alert, and the measured verdict at the deadline
    supplies the detection, so its time moves from the activation step to the deadline step); the predicted alerts
    (``B5ConformalSTL.predictions``) are nested, and the shift is asserted.

    Hand derivation. The 19 calibration days have drops 0, 0, 1, 1, ..., 8, 8, 10. B4 (day maximum of the residual
    magnitude): ``alpha = 0.2`` gives ``k = ceil(20 * 0.8) = 16`` and the sixteenth smallest is 7; ``alpha = 0.05``
    gives ``k = 19`` and the constant is 10. B5 (response template, score ``R`` = drop): the same constants 7 and 10.
    The test day has a drop of 8.5 mmHg: B4 alarms at 7 and not at 10; B5 has ``rho_hat = 0 - 10 = -10`` (persistence
    predicts no drop and the response parameter is 10 mmHg), so it alerts iff ``-10 + C < 0`` iff ``C < 10``: at 7 and
    not at 10."""
    train, calib = poisoned_days()
    day = response_day(8.5, "test")
    sets: dict[float, dict[str, Any]] = {}
    for alpha in (0.05, AUDIT_ALPHA):
        setup = build_audit_setup(alpha=alpha)
        plan = setup.plan_for_day(day)
        found: dict[str, Any] = {}
        for name in ("B4", "B5"):
            det = setup.detectors[name]
            det.fit(train, calib)
            found[name] = det
            found[name + "-out"] = tuple(det.run(day, plan, None))
        sets[alpha] = found
    low, high = sets[0.05], sets[AUDIT_ALPHA]
    b4_low = {d.t_ms for d in low["B4-out"]}
    b4_high = {d.t_ms for d in high["B4-out"]}
    assert b4_low <= b4_high
    assert b4_low == set() and len(b4_high) == 1  # a non-trivial inclusion
    emitted = {
        alpha: {(p.keys, p.t_ms) for p in sets[alpha]["B5"].predictions if p.emitted}
        for alpha in (0.05, AUDIT_ALPHA)
    }
    assert emitted[0.05] <= emitted[AUDIT_ALPHA]
    assert emitted[0.05] == set() and len(emitted[AUDIT_ALPHA]) == 1
    quantiles = {
        alpha: [p.quantile for p in sets[alpha]["B5"].predictions] for alpha in sets
    }
    assert quantiles == {0.05: [10.0], AUDIT_ALPHA: [7.0]}
    # the documented shift: without the predicted alert the response template is decided at its deadline
    activation = (ACT_STEP + 2) * STEP  # dose step plus the reorder delay of two steps
    deadline = (
        ACT_STEP + 180 + 2
    ) * STEP  # the response window of the fixture registry is 180 steps
    at_activation = {
        alpha: sorted(d.score for d in sets[alpha]["B5-out"] if d.t_ms == activation)
        for alpha in sets
    }
    assert len(at_activation[AUDIT_ALPHA]) == len(at_activation[0.05]) + 1
    assert 3.0 in at_activation[AUDIT_ALPHA]  # the predicted alert: -(-10 + 7)
    times_high = {d.t_ms for d in high["B5-out"]}
    times_low = {d.t_ms for d in low["B5-out"]}
    assert times_low - times_high == {deadline}
    assert not times_high - times_low


# ---- 16 sources --------------------------------------------------------------------------------------------------


def test_baseline_sources_do_not_touch_latent_types() -> None:
    files = sorted((SRC / "baselines").glob("b[1-5]_*.py")) + [
        SRC / "baselines" / "raw_robustness.py"
    ]
    assert len(files) == 7  # b1, b2, b2_features, b3, b4, b5, raw_robustness
    for path in files:
        text = path.read_text(encoding="utf-8")
        for token in ("LatentDay", "GroundTruthEvent"):
            assert token not in text, (path.name, token)
    # base.py does not name them either; only access.py does (its guards)
    assert "LatentDay" not in (SRC / "baselines" / "base.py").read_text(
        encoding="utf-8"
    )


# ---- the audit catches a baseline that cheats ------------------------------------------------------------------------


class _B3ReadsAScale(B3PlainSTL):
    """A mutant of B3 that reads a normalisation name, which the baseline is defined without."""

    def _run(self, day: ObservedDay, plan: Any) -> Any:
        self._registry.get("scale_range")
        return super()._run(day, plan)


class _B4ReadsLatent(B4ConformalOnly):
    """A mutant of B4 that reads the latent trace of the calibration days (the policy allows it)."""

    def _fit(self, train: Any, calib: Any) -> None:
        for guarded in calib:
            _ = guarded.latent
        super()._fit(train, calib)


def test_audit_flags_a_baseline_that_reads_a_scale_name(audit: Audit) -> None:
    mutant = _B3ReadsAScale(
        audit.setup.templates, audit.setup.registry, timing=AUDIT_TIMING
    )
    report = run_audit(
        [mutant],
        audit.days,
        audit.plan,
        audit.setup.registry,
        templates=audit.setup.templates,
    )
    assert "scale_range" in report.traces["B3"].run_reads
    assert any("scale" in problem for problem in report.problems)


def test_audit_flags_a_baseline_that_reads_latent_data(audit: Audit) -> None:
    """With ``calib_latent`` the guard allows the read and the log marks it; the audit reports it. On the poisoned days
    the read itself raises, so a cheat that the log missed would still fail the run."""
    mutant = _B4ReadsLatent(
        PersistenceForecaster(AUDIT_STEP_MS),
        alpha=AUDIT_ALPHA,
        timing=AUDIT_TIMING,
        access_policy=AccessPolicy(calib_latent=True),
    )
    with pytest.raises(AssertionError, match="latent trace was read"):
        run_audit(
            [mutant],
            audit.days,
            audit.plan,
            audit.setup.registry,
            templates=audit.setup.templates,
        )
    clean = [
        make_benchmark_day(
            d.observed.samples, d.observed.events, patient_id=d.observed.patient_id
        )
        for d in audit.days.calib
    ]
    report = run_audit(
        [mutant],
        AuditDays(audit.days.train, clean, audit.days.test),
        audit.plan,
        audit.setup.registry,
        templates=audit.setup.templates,
    )
    assert any("latent" in problem for problem in report.problems)
    assert any("calib_latent" in problem for problem in report.problems)


# ---- the audit report -------------------------------------------------------------------------------------------


def test_audit_report_has_no_problems(audit: Audit) -> None:
    """Every claim of the matrix that a log can contradict is consistent with the logs: no by-design cell was read, no
    calibration day gave more than its observed trace, the forecasters were fitted on the training days only."""
    assert audit.report.problems == ()
    for name in NAMES:
        trace = audit.report.traces[name]
        assert trace.calib_fields <= {"observed"}, name
        assert trace.train_fields <= {"observed"}, name
        assert trace.denied == 0, name
    assert audit.report.traces["ours"].calib_fields == frozenset({"observed"})


def test_matrix_cells_come_from_the_logs(audit: Audit) -> None:
    """Spot checks of cells that a reader will look at: B1 is minimal (it does not read the look-back or the day-end
    minimum), B3 and B5 read no scale, B2 and B4 have no registry, nobody reads latent data."""
    cells = {row.item: row.cells for row in audit.report.rows}
    assert cells["hold threshold and look-back (HOLD)"]["B1"] == "partly read"
    assert cells["dose limit and day-end minimum (COUNT)"]["B1"] == "partly read"
    assert cells["response parameters (RESP)"]["B1"] == "not read"
    for item in ("scale", "priority", "verdict-latency bound"):
        assert cells[item]["B3"] == "not read"
        assert cells[item]["B5"] == "not read"
        assert cells[item]["ours (K)"] == "read"
    assert cells["band (RANGE)"]["B2"] == "by design"
    assert cells["band (RANGE)"]["B4"] == "by design"
    assert cells["latent trace (any day)"] == dict.fromkeys(
        (*NAMES, "ours (K)"), "not read"
    )
    assert cells["forecaster (fitted on training days)"]["B3"] == "by design"
    assert cells["forecaster (fitted on training days)"]["B4"] == "read"
    assert cells["EvidenceVector"]["B1"] == "not read"
    assert cells["plan signature check"]["B5"] == "not read"


def test_run_has_no_history_input() -> None:
    """ADR-061 (proposed): ``Detector.run`` has no ``history`` input, so the baselines run one day at a time with empty
    state, whereas the proposed method can be given ``history`` by ``run_offline`` (ADR-046)."""
    for cls in (
        B1StaticThresholds,
        B2AnomalyDetection,
        B3PlainSTL,
        B4ConformalOnly,
        B5ConformalSTL,
    ):
        assert "history" not in inspect.signature(cls.run).parameters
    assert "history" in inspect.signature(run_offline_detailed).parameters


def test_probes_measure_the_documented_asymmetries(audit: Audit) -> None:
    """The extra detections that each perturbation adds, per detector (the size of the asymmetry on the audit fixtures,
    not a statistic). Directions asserted are those that the hand-overs describe."""
    by_label = {r.probe.label: r for r in audit.probe_results}
    dup = by_label["duplicate deliveries"]
    assert dup.extra["ours"] == 0  # the monitor deduplicates
    assert dup.extra["B1"] >= 1 and dup.extra["B3"] >= 1 and dup.extra["B5"] >= 1
    assert dup.extra["B4"] == 0  # a duplicate has no residual
    late = by_label["late input"]
    assert late.extra["ours"] == 0
    for name in ("B1", "B3", "B4", "B5"):
        assert late.extra[name] == 0, (
            name
        )  # the grid rule drops it, as the monitor does
    future = by_label["future-stamped input"]
    assert future.extra["ours"] == 0  # the monitor rejects a future stamp
    assert future.extra["B1"] >= 1 and future.extra["B3"] >= 1
    midnight = by_label["deadline after midnight"]
    assert midnight.extra_after_close["ours"] == 0
    assert (
        midnight.extra_after_close["B3"] >= 1 and midnight.extra_after_close["B5"] >= 1
    )
    assert midnight.extra_after_close["B4"] == 0
    state = by_label["state across midnight (two doses the evening before)"]
    assert state.extra["ours"] >= 1  # with the day before as history
    assert state.extra["B1"] == state.extra["B3"] == state.extra["B5"] == 0
    assert (
        state.extra_without_history["ours"] == 0
    )  # without it the proposed method is blind too


# ---- 17, 18 the audit note --------------------------------------------------------------------------------------

_HEADINGS = (
    "Scope and method",
    "Knowledge matrix",
    "Checks",
    "Documented asymmetries",
    "Findings",
    "Conclusion for WS08-T02",
)
_TESTS_OF_THE_TASK = (
    "test_baselines_exported_and_named",
    "test_shared_timing_configuration",
    "test_no_latent_or_ground_truth_at_inference",
    "test_evidence_and_labels",
    "test_knowledge_is_subset_of_proposed_method",
    "test_b1_receives_bands_and_schedules",
    "test_b3_receives_all_templates_without_normalisation",
    "test_b5_knowledge_equals_b3_knowledge",
    "test_b2_and_b4_read_no_clinical_thresholds",
    "test_calibration_target_is_shared",
    "test_residual_definitions_agree",
    "test_b3_detection_time_equals_monitor_violation_time",
    "test_hyperparameter_selection_documented",
    "test_operating_parameters_have_no_numeric_defaults",
    "test_conformal_baselines_monotone_in_alpha",
    "test_baseline_sources_do_not_touch_latent_types",
    "test_audit_note_complete",
    "test_knowledge_matrix_is_generated",
)


def _sections(text: str) -> dict[str, str]:
    parts = re.split(r"^## (.+)$", text, flags=re.MULTILINE)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}


def _between(text: str, name: str) -> str:
    start, end = f"<!-- {name}:start -->", f"<!-- {name}:end -->"
    assert text.count(start) == 1 and text.count(end) == 1, name
    return text.split(start, 1)[1].split(end, 1)[0].strip()


def test_audit_note_complete() -> None:
    text = NOTE.read_text(encoding="utf-8")
    sections = _sections(text)
    for heading in _HEADINGS:
        assert heading in sections, heading
    # every finding line is classified; none is left open (the intent of the Done-when line)
    findings = [
        line for line in sections["Findings"].splitlines() if line.startswith("- F")
    ]
    assert len(findings) >= 8
    for line in findings:
        assert re.match(r"^- F[0-9]+ \[(closed|accepted|escalated)\]: ", line), line
    assert not re.search(r"^- F[0-9]+ \[open\]", text, flags=re.MULTILINE)
    joined = "\n".join(findings)
    for topic in (
        "calibration target",
        "template field",
        "PLACEHOLDER_TEMPLATE",
        "Forecaster",
        "ADR-063",
        "ADR-061",
        "ADR-062",
        "D2",
    ):
        assert topic in joined, topic
    # the checks table names every test of the task
    for name in _TESTS_OF_THE_TASK:
        assert name in sections["Checks"], name
    # the conclusion states the conditions under which each comparison is legitimate
    conclusion = sections["Conclusion for WS08-T02"]
    for topic in (
        "rules_active",
        "ADR-063",
        "D2",
        "operating point",
        "one day at a time",
        "step_ms",
        "reorder_delay_ms",
        "tail_ms",
    ):
        assert topic in conclusion, topic
    # what the audit does not prove
    assert "not a sandbox" in sections["Scope and method"]


def test_knowledge_matrix_is_generated(audit: Audit) -> None:
    """Test 18. The text between the markers equals ``render_markdown`` of a fresh audit run; the probe table is
    generated the same way. (Regenerate with ``render_audit_blocks`` of ``tests/baselines/conftest.py``.)"""
    text = NOTE.read_text(encoding="utf-8")
    assert _between(text, "matrix") == render_markdown(audit.report).strip()
    assert _between(text, "probes") == render_probe_table(audit.probe_results).strip()
    # determinism: a second run of the audit gives the same matrix
    again = build_audit()
    assert render_markdown(again.report) == render_markdown(audit.report)


def test_audit_setup_fixture_is_consistent(audit_setup: AuditSetup) -> None:
    assert tuple(audit_setup.detectors) == NAMES
    assert set(audit_setup.probes) == {"B2", "B4", "B5"}
    assert T_DAY_MS == 86_400_000
