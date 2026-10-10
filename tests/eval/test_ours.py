"""``OursDetector`` and ``PipelineComponents`` of WS08-T01 (tests 42 to 46 of the task list).

ILLUSTRATIVE, UNVERIFIED, FIXTURE-ONLY: the registry is the fixture registry of ``tests/fixtures/eval`` (the F0 table plus
the seven names that the real registry lacks), the days are hand-built or are the mini benchmark of the same directory.
Nothing is a clinical value and nothing is clinically validated.
"""

from __future__ import annotations

import dataclasses
import sys
import types
from collections.abc import Callable
from typing import Any

import pytest

from ralmon.attribution import AttributedCause
from ralmon.benchmark import BenchmarkDay, LatentDay, ObservedDay, open_benchmark
from ralmon.conformal import CalibrationEpisode, SplitConformal
from ralmon.eval import OursDetector, build_detector
from ralmon.eval.ours import PipelineComponents
from ralmon.eval.runner import (
    ConfigError,
    DetectorEnvironment,
    load_experiment,
    make_environment,
)
from ralmon.monitor import (
    MonitorConfig,
    PersistenceForecaster,
    VerdictState,
    build_calibration_episodes,
    run_offline,
)
from ralmon.signals import Event, EventKind, Sample
from ralmon.spec import (
    CarePlan,
    TemplateId,
    TemplateInstance,
    load_registry,
    load_templates,
    rank_alerts,
)
from tests.eval.helpers import MINI, REGISTRY, SMOKE, T, ms

STEP = 60_000


@pytest.fixture(scope="module")
def registry() -> Any:
    return load_registry(REGISTRY, step_ms=STEP, allow_fixture_only=True)


@pytest.fixture(scope="module")
def templates(registry: Any) -> Any:
    return load_templates(registry=registry)


def config(
    registry: Any, *, predictive: bool = False, alpha: float | None = None
) -> MonitorConfig:
    return MonitorConfig(STEP, 0, predictive, alpha, "likely", registry.version())


def range_plan(registry: Any) -> CarePlan:
    params = {"bp_band_low": 110.0, "bp_band_high": 140.0}
    return CarePlan(
        "plan-1",
        "pathway-fixture",
        "px",
        registry.version(),
        (TemplateInstance(TemplateId.RANGE, "record-range", params, None),),
        (),
        1,
        None,
    )


def out_of_band_day() -> ObservedDay:
    """One measurement at 10:00 with a pressure of 165 (above the band), a coherent cuff, nothing else."""
    t = ms(10)
    samples = (
        Sample("bp", t, t, 165.0, None, None),
        Sample("cuff_health", t, t, 1.0, None, None),
        Sample("inflation_ms", t, t, 40_000.0, None, None),
    )
    events = (Event(EventKind.MEASUREMENT, t, t, "dev", {}, None),)
    return ObservedDay("px", 0, 0, samples, events, "plan-1")


def make_ours(registry: Any, templates: Any, **kw: Any) -> OursDetector:
    cfg = kw.pop("config", None) or config(registry)
    components = kw.pop("components", PipelineComponents(use_forecaster=False))
    return OursDetector(cfg, registry, templates, components=components, **kw)


# 42
def test_ours_emits_c1_alert_for_out_of_band_measurement(
    registry: Any, templates: Any
) -> None:
    ours = make_ours(registry, templates)
    ours.fit([], [])
    alerts = ours.run(out_of_band_day(), range_plan(registry), None)
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.tau == TemplateId.RANGE  # type: ignore[attr-defined]
    assert alert.kappa == AttributedCause.C1_CLINICAL  # type: ignore[attr-defined]
    assert alert.verdict == VerdictState.VIOLATED  # type: ignore[attr-defined]
    assert alert.label == AttributedCause.C1_CLINICAL
    assert alert.t_ms == ms(
        10
    )  # decided at the measurement (ADR-041: t_ms is decided_at_ms)


# 43
def test_ours_name_and_default_components(registry: Any, templates: Any) -> None:
    assert make_ours(registry, templates).name == "ours"
    c = PipelineComponents()
    assert c.verdict_runner is run_offline
    assert c.calibrator_factory is SplitConformal
    assert c.use_forecaster is True
    sentinel_plan = range_plan(registry)
    assert c.plan_transform(sentinel_plan) is sentinel_plan  # identity
    evidence = {"k": object()}
    assert c.evidence_transform(evidence, 0) is evidence  # identity
    ours = make_ours(registry, templates, components=c, config=config(registry))
    day = out_of_band_day()
    first = ours.run(day, range_plan(registry), None)
    assert [a.xi.instance_key for a in c.rank(first, {})] == [
        a.xi.instance_key for a in rank_alerts(first)
    ]


# 44
def test_pipeline_components_frozen() -> None:
    c = PipelineComponents()
    with pytest.raises(dataclasses.FrozenInstanceError):
        c.use_forecaster = False  # type: ignore[misc]


# 45
def test_resolve_variant_delegates_to_modules(
    registry: Any, templates: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_, options = load_experiment(SMOKE)
    env = make_environment(config_, options, 0)
    assert isinstance(env, DetectorEnvironment)
    variant = PipelineComponents(use_forecaster=False)
    seen: list[str] = []

    def stub(answer: PipelineComponents | None) -> types.ModuleType:
        module = types.ModuleType("stub")

        def variant_components(name: str) -> PipelineComponents | None:
            seen.append(name)
            return answer if name == "ours-XYZ" else None

        module.variant_components = variant_components  # type: ignore[attr-defined]
        return module

    monkeypatch.setitem(sys.modules, "ralmon.eval.ablations", stub(None))
    monkeypatch.setitem(sys.modules, "ralmon.eval.embodied", stub(variant))
    detector = build_detector("ours-XYZ", env)
    assert isinstance(detector, OursDetector) and detector.name == "ours-XYZ"
    assert detector.components is variant
    assert (
        seen.count("ours-XYZ") == 2
    )  # the first module answered None, the second answered
    with pytest.raises(ConfigError):
        build_detector("ours-UNKNOWN", env)
    with pytest.raises(ConfigError):
        build_detector("B9", env)


class SpyCalibrator(SplitConformal):
    """A split calibrator that says it is adaptive, forks to itself and logs every call in order."""

    mode = "adaptive"  # type: ignore[assignment]

    def __init__(self, log: list[tuple[str, Any]]) -> None:
        super().__init__()
        self.log = log

    def fork(self) -> SpyCalibrator:
        return self

    def predict(self, sigma_hat: float, alpha: Any, *, variant: Any = "likely") -> Any:
        self.log.append(("predict", sigma_hat))
        return super().predict(sigma_hat, alpha, variant=variant)

    def update(self, sigma_hat: float, sigma_true: float) -> None:
        self.log.append(("update", (sigma_hat, sigma_true)))


def mini_days(split: str) -> tuple[Any, ...]:
    full = open_benchmark(MINI)
    out = []
    for pid in full.patient_ids(split=split, role="patient"):
        for d in full.days(pid):
            out.append(full.observed(pid, d))
    return tuple(out)


# 46
def test_ours_updates_calibrator_after_episode_completion(
    registry: Any, templates: Any
) -> None:
    log: list[tuple[str, Any]] = []
    cfg = config(registry, predictive=True, alpha=0.5)
    forecaster = PersistenceForecaster(STEP)
    reader = open_benchmark(MINI, view="observed")

    def plan_for_day(day: ObservedDay) -> CarePlan:
        return reader.care_plan(day.care_plan_id)

    ours = OursDetector(
        cfg,
        registry,
        templates,
        components=PipelineComponents(calibrator_factory=lambda: SpyCalibrator(log)),
        forecaster_factory=lambda: forecaster,
        plan_for_day=plan_for_day,
    )
    full = open_benchmark(MINI)
    train = [full.benchmark_day(p, d) for p in ("p01", "p02") for d in (0, 1)]
    calib = [full.benchmark_day(p, d) for p in ("p03", "p04") for d in (0, 1)]
    ours.fit(train, calib)
    log.clear()  # the fit does not predict or update
    day = reader.observed("p05", 0)
    ours.run(day, plan_for_day(day), None)
    # oracle: the episodes of the day on the same code path as the monitor (WS05-T08 rule 9)
    episodes, _ = build_calibration_episodes(
        [day],
        [plan_for_day(day)],
        cfg,
        forecaster,
        registry=registry,
        templates=templates,
    )
    assert len(episodes) >= 1
    updates = [entry for kind, entry in log if kind == "update"]
    assert updates == [
        (e.sigma_hat, e.sigma_true) for e in episodes
    ]  # once per completed episode
    kinds = [kind for kind, _ in log]
    assert "predict" in kinds
    first_update = kinds.index("update")
    assert (
        "predict" not in kinds[first_update:]
    )  # no update before the day, hence its deadlines, is complete


def test_ours_predictive_run_has_the_alpha_bookkeeping(
    registry: Any, templates: Any
) -> None:
    """``Alert.rho.alpha`` is the per-test level alpha_total / n_tests (ADR-060): the run exposes both."""
    cfg = config(registry, predictive=True, alpha=0.5)
    reader = open_benchmark(MINI, view="observed")
    ours = OursDetector(
        cfg,
        registry,
        templates,
        forecaster_factory=lambda: PersistenceForecaster(STEP),
        plan_for_day=lambda d: reader.care_plan(d.care_plan_id),
    )
    full = open_benchmark(MINI)
    ours.fit(
        [full.benchmark_day(p, d) for p in ("p01", "p02") for d in (0, 1)],
        [full.benchmark_day(p, d) for p in ("p03", "p04") for d in (0, 1)],
    )
    assert ours.n_calibration_episodes > 0
    day = reader.observed("p05", 0)
    ours.run(day, reader.care_plan(day.care_plan_id), None)
    details = ours.last_run
    assert details is not None
    assert details.alpha_total == 0.5 and details.n_tests >= 1
    assert details.per_test_alpha == pytest.approx(0.5 / details.n_tests)
    assert (
        details.presence_samples_without_availability_marks == 0
    )  # the gate of ADR-054 on a built day
    for a in details.alerts:
        if a.verdict is VerdictState.PREDICTED_VIOLATION:
            assert a.rho is not None and a.rho.alpha == pytest.approx(
                details.per_test_alpha
            )


def test_ours_refuses_a_stale_calibrator_by_construction(
    registry: Any, templates: Any
) -> None:
    """The calibrator is fitted with ``model_version=forecaster.model_version`` (else ``StaleCalibratorError``)."""
    cfg = config(registry, predictive=True, alpha=0.5)
    reader = open_benchmark(MINI, view="observed")
    forecaster = PersistenceForecaster(STEP)
    ours = OursDetector(
        cfg,
        registry,
        templates,
        forecaster_factory=lambda: forecaster,
        plan_for_day=lambda d: reader.care_plan(d.care_plan_id),
    )
    full = open_benchmark(MINI)
    ours.fit([], [full.benchmark_day(p, d) for p in ("p03", "p04") for d in (0, 1)])
    assert ours.calibrator is not None
    assert ours.calibrator.calibrated_for == forecaster.model_version


def test_ours_never_reads_the_latent_trace_or_the_truth(
    registry: Any, templates: Any
) -> None:
    class Poisoned(BenchmarkDay):
        def __init__(self, observed: ObservedDay) -> None:
            object.__setattr__(self, "observed", observed)

        @property  # type: ignore[override]
        def latent(self) -> LatentDay:
            raise AssertionError("the latent trace was read")

        @property  # type: ignore[override]
        def ground_truth(self) -> Any:
            raise AssertionError("the ground truth was read")

    cfg = config(registry, predictive=True, alpha=0.5)
    reader = open_benchmark(MINI, view="observed")
    ours = OursDetector(
        cfg,
        registry,
        templates,
        forecaster_factory=lambda: PersistenceForecaster(STEP),
        plan_for_day=lambda d: reader.care_plan(d.care_plan_id),
    )
    days = [
        Poisoned(reader.observed(p, d))
        for p in ("p01", "p02", "p03", "p04")
        for d in (0, 1)
    ]
    ours.fit(days[:4], days[4:])  # raises AssertionError if anything is read
    with pytest.raises(TypeError):
        ours.run(
            days[0], reader.care_plan("plan-p01"), None
        )  # a benchmark day is refused: an observed day only


def test_ours_with_history_keeps_the_history_out_of_the_alerts(
    registry: Any, templates: Any
) -> None:
    ours = make_ours(registry, templates)
    ours.fit([], [])
    t = T + ms(10)
    day2 = ObservedDay(
        "px",
        1,
        0,
        (
            Sample("bp", t, t, 165.0, None, None),
            Sample("cuff_health", t, t, 1.0, None, None),
        ),
        (Event(EventKind.MEASUREMENT, t, t, "dev", {}, None),),
        "plan-1",
    )
    plan = range_plan(registry)
    alone = ours.run(day2, plan, None)
    with_history = ours.run(day2, plan, None, history=[out_of_band_day()])
    # the out-of-band measurement of day 0 was decided in day 0: replayed, not reported for day 1
    assert [a.t_ms for a in alone] == [t]
    assert [a.t_ms for a in with_history] == [t]


def test_the_evidence_transform_sees_the_extracted_evidence_once_per_run(
    registry: Any, templates: Any
) -> None:
    calls: list[tuple[dict[str, Any], int]] = []

    def transform(evidence: Any, seed: int) -> Any:
        calls.append((dict(evidence), seed))
        return evidence

    ours = make_ours(
        registry,
        templates,
        components=PipelineComponents(
            use_forecaster=False, evidence_transform=transform
        ),
        seed=7,
    )
    ours.fit([], [])
    ours.run(out_of_band_day(), range_plan(registry), None)
    assert len(calls) == 1
    evidence, seed = calls[0]
    assert (
        seed == 7 and len(evidence) == 1
    )  # one violated instance: one evidence vector, keyed by instance key
