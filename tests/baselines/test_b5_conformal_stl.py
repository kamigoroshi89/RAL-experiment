"""B5, conformal STL predictive monitoring after Lindemann et al. (WS06-T06): behaviour and decision rule.

FIXTURE-ONLY numbers. The band limit 140 mmHg, the scale 20 mmHg and the dose limit are the illustrative
numbers of analisi section 4.1 ("illustrative, unverified") and the deadlines of the stub evaluator are chosen
for these tests only; none is a clinical value and none is a claim of clinical validation. ``step_ms`` is
60 000 and ``reorder_delay_ms`` is 0. Every expected value is computed by hand in the comment next to it.

Hand derivation of the quantile used throughout (equation (4), Theorem 1, p. 8 of the preprint arXiv:2211.01539v2,
and ``SplitConformal``): with ``n`` scores and level ``alpha`` the constant is the ``k``-th smallest score,
``k = ceil((n + 1)(1 - alpha))``. Example: ``n = 10``, ``alpha = 0.2``: ``(n + 1)(1 - alpha) = 8.8``, ``k = 9``.

Helpers defined here are imported by ``test_b5_failure_modes.py``.
"""

from __future__ import annotations

import functools
import inspect
import math
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import ralmon.monitor.predictive
import ralmon.spec
from ralmon.attribution import Detection
from ralmon.baselines import B5ConformalSTL, Detector
from ralmon.baselines.access import AccessPolicy, LeakageError
from ralmon.baselines.b5_conformal_stl import (
    Evaluation,
    aggregate_raw,
)
from ralmon.baselines.base import BaselineBase, NotFittedError, TimingConfig, iter_steps
from ralmon.baselines.raw_robustness import (
    LoggingRegistry,
    SignalGrid,
    make_evaluator,
)
from ralmon.benchmark import BenchmarkDay, ObservedDay
from ralmon.conformal import CalibrationEpisode, SplitConformal
from ralmon.monitor import PersistenceForecaster, StaleCalibratorError
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
from tests.monitor.helpers import load_f0

ROOT = Path(__file__).resolve().parents[2]
NOTES = ROOT / "docs" / "plan" / "workstreams" / "WS06-baselines" / "notes"
B5_SOURCE = ROOT / "src" / "ralmon" / "baselines" / "b5_conformal_stl.py"

STEP = 60_000
T_DAY = 86_400_000
LIMIT = 140.0  # illustrative upper band, unverified (analisi 4.1)
ACT = 10  # activation step of the dispense in the stub fixtures
LENGTH = 5  # steps from the activation to the deadline of the stub evaluator
TIMING = TimingConfig(STEP, 0, 0)

_REGISTRY = load_f0()
_LIBRARY = {t.id: t for t in load_templates(registry=_REGISTRY)}


def templ(*ids: TemplateId) -> tuple[Template, ...]:
    return tuple(_LIBRARY[i] for i in ids)


# ---- days -----------------------------------------------------------------------------------------


def smp(signal: str, step: int, value: float, rx_step: int | None = None) -> Sample:
    rx = step if rx_step is None else rx_step
    return Sample(signal, step * STEP, rx * STEP, float(value), None, None)


def evt(
    kind: EventKind,
    step: int,
    rx_step: int | None = None,
    source: str = "dev",
    payload: Mapping[str, float | int | str | bool] | None = None,
) -> Event:
    rx = step if rx_step is None else rx_step
    return Event(kind, step * STEP, rx * STEP, source, dict(payload or {}), None)


def observed(
    samples: Sequence[Sample],
    events: Sequence[Event] = (),
    *,
    patient: str = "p1",
    day_index: int = 0,
) -> ObservedDay:
    return ObservedDay(
        patient,
        day_index,
        0,
        tuple(sorted(samples, key=lambda s: s.t_rx_ms)),
        tuple(sorted(events, key=lambda e: e.t_rx_ms)),
        "plan-1",
    )


def bench(day: ObservedDay) -> BenchmarkDay:
    from tests.baselines.conftest import make_benchmark_day

    return make_benchmark_day(
        day.samples,
        day.events,
        patient_id=day.patient_id,
        day_index=day.day_index,
    )


def dispense_day(
    bp_act: float,
    bp_deadline: float,
    *,
    patient: str = "p1",
    act: int = ACT,
    length: int = LENGTH,
    bp0: float | None = None,
) -> ObservedDay:
    """A day with one dispense at step ``act`` and the blood pressure ``bp_act`` held from step 0.

    ``bp_deadline`` is the sample delivered at the deadline step ``act + length``. With the persistence forecaster
    and the threshold stub, ``rho_hat = LIMIT - bp_act`` and ``rho_true = LIMIT - bp_deadline``.
    """
    return observed(
        [smp("bp", 0, bp_act if bp0 is None else bp0), smp("bp", act, bp_act)]
        + [smp("bp", act + length, bp_deadline)],
        [evt(EventKind.DISPENSE, act)],
        patient=patient,
    )


def calibration_days(
    residuals: Sequence[float], *, prefix: str = "c"
) -> list[BenchmarkDay]:
    """Days whose episodes have the scores ``R = rho_true - rho_hat = bp_act - bp_deadline`` = ``residuals``."""
    base = 100.0
    return [
        bench(dispense_day(base, base - r, patient=f"{prefix}{i}"))
        for i, r in enumerate(residuals)
    ]


def train_days() -> list[BenchmarkDay]:
    return [bench(observed([smp("bp", 0, 100.0)], patient="train"))]


# ---- stubs -----------------------------------------------------------------------------------------


class ThresholdEvaluator:
    """``limit - bp`` at the deadline step ``anchor_step + length``; ``None`` before it (FIXTURE-ONLY)."""

    def __init__(
        self, unit: RobustnessUnit, limit: float = LIMIT, length: int = LENGTH
    ) -> None:
        self.unit = unit
        self._limit = limit
        self._length = length
        self._anchor: int | None = None
        self.resets = 0

    def reset(self, instance: TemplateInstance) -> None:
        self.resets += 1
        assert instance.anchor_ms is not None
        self._anchor = -(-instance.anchor_ms // STEP)

    def step(self, t_ms: int, values: Mapping[str, float | None]) -> float | None:
        assert self._anchor is not None
        if t_ms // STEP < self._anchor + self._length:
            return None
        bp = values.get("bp")
        return None if bp is None else self._limit - bp


class ScriptedEvaluator:
    """Returns ``value`` from the anchor step on, ``None`` before it."""

    def __init__(self, unit: RobustnessUnit, value: float) -> None:
        self.unit = unit
        self._value = value
        self._anchor: int | None = None

    def reset(self, instance: TemplateInstance) -> None:
        assert instance.anchor_ms is not None
        self._anchor = -(-instance.anchor_ms // STEP)

    def step(self, t_ms: int, values: Mapping[str, float | None]) -> float | None:
        assert self._anchor is not None
        return self._value if t_ms // STEP >= self._anchor else None


class NeverEvaluator:
    """Never decides: the instance stays open for ever."""

    def __init__(self, unit: RobustnessUnit) -> None:
        self.unit = unit

    def reset(self, instance: TemplateInstance) -> None:
        pass

    def step(self, t_ms: int, values: Mapping[str, float | None]) -> float | None:
        return None


Factory = Callable[[Template, Any, int, str | None], Any]


def threshold_factory(
    limit: float = LIMIT,
    length: int = LENGTH,
    created: list[ThresholdEvaluator] | None = None,
) -> Factory:
    """RESP gets the threshold stub, every other template never decides."""

    def make(
        template: Template, registry: Any, step_ms: int, anchor_kind: str | None
    ) -> Any:
        if template.id is TemplateId.RESP:
            ev = ThresholdEvaluator(template.unit, limit, length)
            if created is not None:
                created.append(ev)
            return ev
        return NeverEvaluator(template.unit)

    return make


@dataclass
class FixedCalibrator:
    """A calibrator with a fixed quantile ``q``: emits iff ``sigma_hat + q < 0`` (the protocol, no learning)."""

    q: float
    calibrated_for: str | None = None
    mode: str = "split"
    fits: list[Any] = field(default_factory=list)

    def fit(
        self,
        episodes: Sequence[CalibrationEpisode],
        alpha: Any,
        *,
        model_version: str | None = None,
    ) -> None:
        self.fits.append(tuple(episodes))
        self.calibrated_for = model_version

    def quantile(self, alpha: Any) -> float:
        return self.q

    def quantile_lower(self, alpha: Any) -> float:
        return -math.inf

    def predict(self, sigma_hat: float, alpha: Any, *, variant: str = "likely") -> Any:
        from ralmon.conformal import PredictedViolation

        return PredictedViolation(sigma_hat + self.q < 0, None, "likely")  # type: ignore[arg-type]

    def update(self, sigma_hat: float, sigma_true: float) -> None:
        pass


def make_b5(
    *,
    aggregation: str = "conjunction",
    alpha: Any = 0.2,
    templates: Sequence[Template] | None = None,
    evaluator_factory: Factory | None = None,
    calibrator_factory: Callable[[], Any] = SplitConformal,
    forecaster: Any = None,
    plan_for_day: Callable[[ObservedDay], CarePlan] | None = None,
    timing: TimingConfig = TIMING,
    registry: Any = None,
    **kwargs: Any,
) -> B5ConformalSTL:
    return B5ConformalSTL(
        templates if templates is not None else templ(TemplateId.RESP),
        _REGISTRY if registry is None else registry,
        PersistenceForecaster(STEP) if forecaster is None else forecaster,
        calibrator_factory,
        alpha=alpha,
        aggregation=aggregation,  # type: ignore[arg-type]
        timing=timing,
        plan_for_day=(lambda day: make_care_plan())
        if plan_for_day is None
        else plan_for_day,
        evaluator_factory=threshold_factory()
        if evaluator_factory is None
        else evaluator_factory,
        **kwargs,
    )


# the ten residuals of the worked example: n = 10, alpha = 0.2, k = ceil(11 * 0.8) = 9, q = 6
WORKED_RESIDUALS = (-3.0, -1.0, 0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0)


def fitted_worked(**kwargs: Any) -> B5ConformalSTL:
    b5 = make_b5(**kwargs)
    b5.fit(train_days(), calibration_days(WORKED_RESIDUALS))
    return b5


def run(b5: B5ConformalSTL, day: ObservedDay, plan: CarePlan | None = None) -> Any:
    return b5.run(day, make_care_plan() if plan is None else plan, None)


def pairs(detections: Sequence[Detection]) -> list[tuple[int, float]]:
    return [(d.t_ms, d.score) for d in detections]


# ---- 1. the deviation note -------------------------------------------------------------------------


def _sections(text: str) -> dict[str, str]:
    parts = re.split(r"^## (.+)$", text, flags=re.MULTILINE)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}


def test_deviation_note_has_required_sections() -> None:
    text = (NOTES / "B5-deviations.md").read_text(encoding="utf-8")
    sections = _sections(text)
    for heading in (
        "Published method as read",
        "Mapping to the pathway templates",
        "Deviations",
    ):
        assert heading in sections, heading
    bullets = [
        line
        for line in sections["Published method as read"].splitlines()
        if line.startswith("- ")
    ]
    assert len(bullets) >= 10
    for bullet in bullets:
        assert "locator:" in bullet, bullet
    rows = [
        [c.strip() for c in line.strip().strip("|").split("|")]
        for line in sections["Deviations"].splitlines()
        if line.startswith("|")
    ]
    header = [c.lower() for c in rows[0]]
    for column in (
        "aspect",
        "paper",
        "this implementation",
        "reason",
        "effect on b5 strength",
    ):
        assert column in header, column
    body = [r for r in rows[2:] if len(r) == len(header)]
    assert len(body) >= 1
    assert all(all(cell for cell in row) for row in body)


# ---- 2. signature, name, labels --------------------------------------------------------------------


def test_b5_signature_name_and_labels() -> None:
    assert BaselineBase in B5ConformalSTL.__mro__
    assert isinstance(fitted_worked(), Detector)
    expected = inspect.signature(Detector.run)
    actual = inspect.signature(B5ConformalSTL.run)
    assert list(actual.parameters)[:4] == list(expected.parameters)[:4]
    assert list(inspect.signature(B5ConformalSTL.fit).parameters) == list(
        inspect.signature(Detector.fit).parameters
    )
    assert make_b5().name == "B5"
    assert make_b5(aggregation="per_template").name == "B5-per-template"
    b5 = fitted_worked()
    out = run(b5, dispense_day(150.0, 142.0))
    assert out and all(d.label is None for d in out)
    assert all(isinstance(d, Detection) and math.isfinite(d.score) for d in out)


def test_b5_operating_parameter_and_docstring() -> None:
    parameters = inspect.signature(B5ConformalSTL.__init__).parameters
    assert parameters["alpha"].default is inspect.Parameter.empty
    assert "Hyperparameter selection" in (B5ConformalSTL.__doc__ or "")
    with pytest.raises(ValueError):
        make_b5(aggregation="sum")
    for bad in (0.0, 1.0, -0.1, True, "0.1"):
        with pytest.raises(ValueError):
            make_b5(alpha=bad)


def test_b5_run_requires_fit_and_an_observed_day() -> None:
    b5 = make_b5()
    with pytest.raises(NotFittedError):
        run(b5, dispense_day(150.0, 142.0))
    b5.fit(train_days(), calibration_days(WORKED_RESIDUALS))
    with pytest.raises(LeakageError):
        b5.run(bench(dispense_day(150.0, 142.0)), make_care_plan(), None)  # type: ignore[arg-type]


# ---- 3. evidence is ignored ------------------------------------------------------------------------


def test_b5_ignores_evidence() -> None:
    b5 = fitted_worked()
    day = dispense_day(150.0, 142.0)
    plan = make_care_plan()
    bare = b5.run(day, plan, None)
    with_evidence = b5.run(day, plan, {"k": object()})  # type: ignore[dict-item]
    assert tuple(bare) == tuple(with_evidence)
    assert len(bare) >= 1


# ---- 4. no latent trace and no ground truth ---------------------------------------------------------


class PoisonedDay(BenchmarkDay):
    """A benchmark day whose latent trace and ground truth raise on any access."""

    def __init__(self, observed_day: ObservedDay) -> None:
        object.__setattr__(self, "observed", observed_day)

    @property  # type: ignore[override]
    def latent(self) -> Any:
        raise AssertionError("the latent trace was read")

    @property  # type: ignore[override]
    def ground_truth(self) -> Any:
        raise AssertionError("the ground truth was read")


def test_b5_never_touches_latent_or_ground_truth() -> None:
    calib = [
        PoisonedDay(dispense_day(100.0, 100.0 - r, patient=f"c{i}"))
        for i, r in enumerate(WORKED_RESIDUALS)
    ]
    train = [PoisonedDay(observed([smp("bp", 0, 100.0)], patient="train"))]
    b5 = make_b5()
    b5.fit(train, calib)  # AssertionError if anything but ``observed`` is read
    out = run(b5, dispense_day(150.0, 142.0))
    assert out
    assert b5.access_log.denied == ()
    assert b5.access_log.fields() == frozenset({"observed"})
    # even the exception of the shared policy is not used: B5 reads no latent trace when it is allowed either
    allowed = make_b5(access_policy=AccessPolicy(calib_latent=True))
    allowed.fit(train, calib)
    assert allowed.access_log.fields() == frozenset({"observed"})


# ---- 5. the decision rule, worked example -----------------------------------------------------------


@pytest.mark.parametrize(
    ("bp_act", "expected"),
    [
        # rho_hat = 140 - bp_act; alert iff rho_hat + 6 < 0 (Theorem 1 applied to the negated formula, p. 8, p. 24)
        (150.0, [(ACT * STEP, 4.0)]),  # -10 + 6 = -4 < 0: alert, score 4
        (147.0, [(ACT * STEP, 1.0)]),  # -7 + 6 = -1 < 0: alert, score 1
        (146.0, []),  # boundary: -6 + 6 = 0, not strictly negative: no alert
        (145.0, []),  # -5 + 6 = 1
        (100.0, []),  # +40
    ],
)
def test_b5_decision_rule_worked_example(
    bp_act: float, expected: list[tuple[int, float]]
) -> None:
    """Locator: Section 3.2, Theorem 1, equation (4), p. 8 of arXiv:2211.01539v2; the paper has no numeric example.

    Hand instance. Calibration scores ``R_i = rho_true - rho_hat`` = (-3, -1, 0, 1, 2, 3, 4, 5, 6, 8), ``n = 10``,
    ``alpha = 0.2``: ``k = ceil(11 * 0.8) = 9``, ``C = 6``. The paper certifies satisfaction when ``rho_hat > C`` with
    ``R = rho_hat - rho_true``; for the alert about violation the same theorem is applied to the negated formula,
    whose robustness is minus ``rho`` (Appendix A, p. 24), so ``R = rho_true - rho_hat`` and the alert is
    emitted iff ``rho_hat + C < 0``. With the persistence forecaster and ``rho = 140 - bp`` the day below has
    ``rho_hat = 140 - bp_act`` and, since the pressure returns to 100 at the deadline, a satisfied measured verdict.
    """
    b5 = fitted_worked()
    assert b5.n_calibration_episodes == len(WORKED_RESIDUALS)
    out = run(b5, dispense_day(bp_act, 100.0))
    assert pairs(out) == expected
    # the stub calibrator confirms the constant of the hand derivation
    check = SplitConformal()
    check.fit(
        [CalibrationEpisode("p", 0, TemplateId.RESP, 0.0, r) for r in WORKED_RESIDUALS],
        0.2,
    )
    assert check.quantile(0.2) == 6.0


def test_b5_prediction_records_expose_sigma_hat_and_quantile() -> None:
    b5 = fitted_worked()
    run(b5, dispense_day(150.0, 100.0))
    (record,) = b5.predictions
    assert record.template is TemplateId.RESP
    assert record.t_ms == ACT * STEP
    assert record.sigma_hat == -10.0
    assert record.quantile == 6.0
    assert record.emitted is True
    assert record.sigma_true == 40.0  # measured at the deadline: 140 - 100


def test_b5_predicted_alerts_are_nested_in_alpha_but_detections_are_not() -> None:
    """A smaller ``alpha`` gives a larger constant and fewer predicted alerts (nested), but the measured verdict at the
    deadline then supplies the detection that the prediction no longer does, so the detection sets are not nested.

    Hand derivation, scores as in the worked example (``n = 10``): ``alpha = 0.2``: ``k = 9``, ``C = 6``; ``alpha = 0.1``:
    ``k = 10``, ``C = 8``; ``alpha = 0.05``: ``k = 11 > 10``, ``C = inf``. Day: pressure 150 throughout, ``rho = -10``.
    """
    deadline = (ACT + LENGTH) * STEP
    seen = {}
    for alpha, constant in ((0.2, 6.0), (0.1, 8.0), (0.05, math.inf)):
        b5 = make_b5(alpha=alpha)
        b5.fit(train_days(), calibration_days(WORKED_RESIDUALS))
        out = run(b5, dispense_day(150.0, 150.0))
        (record,) = b5.predictions
        assert record.quantile == constant
        seen[alpha] = (record.emitted, pairs(out))
    assert seen[0.2] == (True, [(ACT * STEP, 4.0)])  # -10 + 6
    assert seen[0.1] == (True, [(ACT * STEP, 2.0)])  # -10 + 8
    assert seen[0.05] == (
        False,
        [(deadline, 10.0)],
    )  # only the measured verdict is left


# ---- 6. only the public calibrator API -------------------------------------------------------------


class SpyCalibrator:
    """Records every public attribute that B5 touches; a member outside the protocol raises."""

    PROTOCOL = frozenset(
        {
            "mode",
            "calibrated_for",
            "fit",
            "quantile",
            "quantile_lower",
            "predict",
            "update",
        }
    )

    def __init__(self) -> None:
        object.__setattr__(self, "_inner", FixedCalibrator(2.0))
        object.__setattr__(self, "touched", [])

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_") or name == "touched":
            raise AttributeError(name)
        self.touched.append(name)
        if name not in self.PROTOCOL:
            raise AttributeError(f"{name} is not a member of ConformalCalibrator")
        return getattr(self._inner, name)

    def __setattr__(self, name: str, value: Any) -> None:
        self.touched.append(name)
        setattr(self._inner, name, value)


def test_b5_uses_calibrator_public_api_only() -> None:
    spy_holder: list[SpyCalibrator] = []

    def factory() -> SpyCalibrator:
        spy = SpyCalibrator()
        spy_holder.append(spy)
        return spy

    b5 = make_b5(calibrator_factory=factory)
    calib = calibration_days(WORKED_RESIDUALS)
    b5.fit(train_days(), calib)
    run(b5, dispense_day(150.0, 100.0))
    (spy,) = spy_holder
    assert set(spy.touched) <= SpyCalibrator.PROTOCOL
    assert "fit" in spy.touched and "predict" in spy.touched
    (episodes,) = spy._inner.fits
    # episodes come from the observed calibration days only: their patients and days, nothing of the training day
    assert {e.patient_id for e in episodes} == {
        f"c{i}" for i in range(len(WORKED_RESIDUALS))
    }
    assert all(e.template is TemplateId.RESP for e in episodes)
    assert sorted(e.sigma_true - e.sigma_hat for e in episodes) == sorted(
        WORKED_RESIDUALS
    )
    assert spy._inner.calibrated_for == "persistence-1"


def test_b5_refuses_a_calibrator_older_than_the_forecaster() -> None:
    class Moving(PersistenceForecaster):
        version = "persistence-1"

        @property
        def model_version(self) -> str:
            return self.version

    forecaster = Moving(STEP)
    b5 = make_b5(forecaster=forecaster)
    b5.fit(train_days(), calibration_days(WORKED_RESIDUALS))
    forecaster.version = "persistence-2"
    with pytest.raises(StaleCalibratorError):
        run(b5, dispense_day(150.0, 100.0))


# ---- 7. raw robustness is never scaled ----------------------------------------------------------------


def test_b5_raw_robustness_never_normalised(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("normalisation or ranking was used by B5")

    for module in (ralmon.spec, ralmon.monitor.predictive):
        monkeypatch.setattr(module, "normalise", boom, raising=False)
    monkeypatch.setattr(ralmon.spec, "rank_alerts", boom, raising=False)

    # the real evaluator on every template: the read log holds no scale or priority name
    registry = _REGISTRY
    every = tuple(_LIBRARY.values())
    b5 = make_b5(templates=every, evaluator_factory=make_evaluator, registry=registry)
    day = observed(
        [smp("bp", 0, 125.0), smp("bp", 5, 152.0), smp("bp", 8, 100.0)],
        [
            evt(EventKind.MEASUREMENT, 5),
            evt(EventKind.DISPENSE, 8),
            evt(EventKind.MEASUREMENT, 8),
        ],
    )
    b5.fit([bench(day)], [bench(day)])
    plan = make_care_plan(
        [
            make_instance(TemplateId.SCHED, "sched@5", {}, 5 * STEP),
            make_instance(TemplateId.RANGE, "range-record", {}),
        ]
    )
    out = b5.run(day, plan, None)
    assert out
    names = b5.read_log.all_names()
    assert not any(n.startswith(("scale_", "priority_")) for n in names), names
    known = {p for t in every for p in t.params} | {"bounds:bp"}
    assert names <= known, names - known
    forbidden = {t.scale_param for t in every} | {t.priority_param for t in every}
    assert not (names & forbidden)


# ---- 8. conjunction is the minimum of the raw instance values ----------------------------------------


def _evals() -> list[Evaluation]:
    return [
        Evaluation("range@1", TemplateId.RANGE, -12.0, "measured"),  # mmHg
        Evaluation("sys@1", TemplateId.SYS, 3.0, "measured"),  # time robustness, ms
        Evaluation("count@1", TemplateId.COUNT, -1.0, "measured"),  # dose
    ]


def test_b5_conjunction_is_min_of_raw_instance_robustness() -> None:
    (group,) = aggregate_raw(_evals(), "conjunction")
    assert group.value == -12.0  # min of the raw values in three different units
    assert group.members == ("range@1", "sys@1", "count@1")
    assert group.template is TemplateId.RANGE
    separate = aggregate_raw(_evals(), "per_template")
    assert [g.value for g in separate] == [-12.0, 3.0, -1.0]
    assert [g.members for g in separate] == [("range@1",), ("sys@1",), ("count@1",)]
    with pytest.raises(ValueError):
        aggregate_raw(_evals(), "mean")  # type: ignore[arg-type]
    assert aggregate_raw([], "conjunction") == []


def _decided_at_dispense(values: Mapping[TemplateId, float]) -> Factory:
    def make(
        template: Template, registry: Any, step_ms: int, anchor_kind: str | None
    ) -> Any:
        return ScriptedEvaluator(template.unit, values[template.id])

    return make


def test_b5_aggregation_in_the_pipeline() -> None:
    values = {
        TemplateId.HOLD: -12.0,  # mmHg
        TemplateId.INT: 3.0,  # ms
        TemplateId.COUNT: -1.0,  # dose
    }
    day = observed([smp("bp", 0, 100.0)], [evt(EventKind.DISPENSE, 2)])
    templates = templ(TemplateId.HOLD, TemplateId.COUNT, TemplateId.INT)
    factory = _decided_at_dispense(values)
    conj = make_b5(templates=templates, evaluator_factory=factory)
    conj.fit(train_days(), [])
    assert pairs(run(conj, day)) == [(2 * STEP, 12.0)]  # one detection, minimum -12
    per = make_b5(
        aggregation="per_template", templates=templates, evaluator_factory=factory
    )
    per.fit(train_days(), [])
    # instance keys count@... < hold@...: deterministic order, no ordering of scores across units
    assert pairs(run(per, day)) == [(2 * STEP, 1.0), (2 * STEP, 12.0)]


# ---- 9. calibrators: one for the conjunction, one per template ------------------------------------------


def test_b5_per_template_variant_calibrates_each_template_separately() -> None:
    every = tuple(_LIBRARY.values())
    for aggregation, name, expected in (
        ("conjunction", "B5", 1),
        ("per_template", "B5-per-template", len(every)),
    ):
        made: list[SplitConformal] = []

        def factory(made: list[SplitConformal] = made) -> SplitConformal:
            made.append(SplitConformal())
            return made[-1]

        b5 = make_b5(
            aggregation=aggregation, templates=every, calibrator_factory=factory
        )
        assert b5.name == name
        b5.fit(train_days(), calibration_days(WORKED_RESIDUALS))
        assert len(made) == expected
        fitted = [c for c in made if c.calibrated_for is not None]
        assert len(fitted) == 1  # only RESP has a predictive part and so episodes
        assert fitted[0].n_scores == len(WORKED_RESIDUALS)
        made.clear()
        b5.fit(
            train_days(), calibration_days(WORKED_RESIDUALS)
        )  # a refit replaces the state
        assert len(made) == expected


# ---- 10. after the deadline only the measured prefix is left ------------------------------------------------


@pytest.mark.parametrize(
    ("bp_deadline", "violated"),
    [
        (142.0, True),
        (140.0, False),
        (130.0, False),
    ],  # rho = -2, 0 (not a violation), +10
)
def test_b5_reduces_to_measured_prefix_at_deadline(
    bp_deadline: float, violated: bool
) -> None:
    deadline = (ACT + LENGTH) * STEP
    never = make_b5(calibrator_factory=lambda: FixedCalibrator(math.inf))
    never.fit(train_days(), calibration_days(WORKED_RESIDUALS))
    out = pairs(run(never, dispense_day(100.0, bp_deadline)))
    # no prediction can fire (q = +inf): the decision is the sign of the measured raw robustness at the deadline
    assert out == (
        [(deadline, bp_deadline - 140.0)] if violated else []
    )  # score is minus the raw value
    always = make_b5(calibrator_factory=lambda: FixedCalibrator(-1e9))
    always.fit(train_days(), calibration_days(WORKED_RESIDUALS))
    got = pairs(run(always, dispense_day(100.0, bp_deadline)))
    # the prediction fires at the activation step; the measured verdict at the deadline adds no second detection
    assert [t for t, _ in got] == [ACT * STEP]


def test_b5_prediction_then_satisfied_measurement_gives_one_detection() -> None:
    # predicted at the activation with q = -1e9 (always), measured satisfied (+10): the flag falls, no detection later
    always = make_b5(calibrator_factory=lambda: FixedCalibrator(-1e9))
    always.fit(train_days(), calibration_days(WORKED_RESIDUALS))
    assert [t for t, _ in pairs(run(always, dispense_day(100.0, 130.0)))] == [
        ACT * STEP
    ]


# ---- 11. causality -------------------------------------------------------------------------------------------


@functools.lru_cache(maxsize=1)
def fixed_b5() -> B5ConformalSTL:
    return fitted_worked(timing=TimingConfig(STEP, 0, 60 * STEP))


@settings(max_examples=60, deadline=None)
@given(
    sample_specs=st.lists(
        st.tuples(st.integers(0, 25), st.integers(100, 160), st.integers(0, 3)),
        min_size=1,
        max_size=6,
    ),
    dispenses=st.lists(st.integers(1, 20), min_size=1, max_size=2, unique=True),
    cut=st.integers(0, 40),
)
def test_b5_is_causal_property(
    sample_specs: list[tuple[int, int, int]], dispenses: list[int], cut: int
) -> None:
    samples = [smp("bp", s, v, s + d) for s, v, d in sample_specs]
    events = [evt(EventKind.DISPENSE, s) for s in dispenses]
    full = observed(samples, events)
    horizon = cut * STEP
    truncated = observed(
        [s for s in samples if s.t_rx_ms <= horizon],
        [e for e in events if e.t_rx_ms <= horizon],
    )
    b5 = fixed_b5()
    a = [d for d in b5.run(full, make_care_plan(), None) if d.t_ms <= horizon]
    b = [d for d in b5.run(truncated, make_care_plan(), None) if d.t_ms <= horizon]
    assert a == b


# ---- 12. determinism ----------------------------------------------------------------------------------------


def test_b5_deterministic() -> None:
    day = dispense_day(150.0, 142.0)
    outputs = []
    for _ in range(2):
        b5 = fitted_worked()
        outputs.append(tuple(run(b5, day)))
        b5.fit(
            train_days(), calibration_days(WORKED_RESIDUALS)
        )  # a second fit on the same days
        outputs.append(tuple(run(b5, day)))
    assert outputs[0] == outputs[1] == outputs[2] == outputs[3]


# ---- 13. control: dense, exchangeable days -------------------------------------------------------------------


def _walk_day(
    rng: np.random.Generator, patient: str, start: float, n: int
) -> ObservedDay:
    """A dense Gaussian random walk: one bp value per step 0..n, a dispense at ``ACT_DENSE``."""
    values = start + np.cumsum(np.concatenate([[0.0], rng.normal(0.0, 1.0, n)]))
    samples = [smp("bp", k, float(v)) for k, v in enumerate(values)]
    return observed(samples, [evt(EventKind.DISPENSE, ACT_DENSE)], patient=patient)


ACT_DENSE = 20
LEN_DENSE = 20


def test_b5_control_dense_exchangeable_days() -> None:
    """The paper's setting: dense, exchangeable trajectories (Assumption 1, p. 4); the error event is the one of
    ``#conformal-calibrator`` rule 3: detection emitted and the true robustness is not negative.

    200 calibration and 2000 test days, ``numpy.random.default_rng(0)``, a Gaussian random walk from a common start
    3 mmHg above the limit (so that a good part of the test days is alerted), persistence forecaster, the threshold
    stub with a deadline 20 steps after the dose. The score of an episode is ``R = x_20 - x_40`` (the change over the
    deadline window), which is exchangeable across days. The rate of the error event must stay at or below
    ``alpha + 3 sqrt(alpha (1 - alpha) / 2000)``; the bound is the one of the task and is loose on this population
    (many days are not alerted), which the note on the control states.
    """
    rng = np.random.default_rng(0)
    start = LIMIT + 3.0
    n_steps = ACT_DENSE + LEN_DENSE
    calib = [bench(_walk_day(rng, f"c{i}", start, n_steps)) for i in range(200)]
    tests = [_walk_day(rng, f"t{i}", start, n_steps) for i in range(2000)]
    alpha = 0.1
    b5 = make_b5(alpha=alpha, evaluator_factory=threshold_factory(length=LEN_DENSE))
    b5.fit(train_days(), calib)
    assert b5.n_calibration_episodes == 200
    errors = alerts = 0
    for day in tests:
        detections = run(b5, day)
        predicted = [d for d in detections if d.t_ms == ACT_DENSE * STEP]
        rho_true = LIMIT - day.samples[n_steps].value
        alerts += bool(predicted)
        errors += bool(predicted) and rho_true >= 0.0
    bound = alpha + 3.0 * math.sqrt(alpha * (1.0 - alpha) / 2000)
    assert errors / 2000 <= bound
    assert (
        alerts / 2000 >= 0.05
    )  # not vacuous: the predictive part does fire on this population


# ---- the raw robustness adapter and the signal grid (module shared with WS06-T04) -------------------------


def test_adapter_reports_template_unit_and_resets_independently() -> None:
    for tid in (TemplateId.RANGE, TemplateId.SCHED, TemplateId.COUNT):
        template = _LIBRARY[tid]
        evaluator = make_evaluator(template, _REGISTRY, STEP)
        assert evaluator.unit is template.unit
    range_template = _LIBRARY[TemplateId.RANGE]
    evaluator = make_evaluator(range_template, _REGISTRY, STEP, "measurement")
    instance = TemplateInstance(TemplateId.RANGE, "r", {}, 2 * STEP)
    evaluator.reset(instance)
    values = [
        evaluator.step(k * STEP, {"bp": 125.0, "meas": 1.0 if k == 2 else 0.0})
        for k in range(3)
    ]
    assert (
        values[:2] == [None, None] and values[2] == 15.0
    )  # min(125 - 110, 140 - 125) at the anchor step
    evaluator.reset(instance)  # forgets the history: step 0 is accepted again
    assert evaluator.step(0, {"bp": 152.0}) is None
    other = make_evaluator(range_template, _REGISTRY, STEP, "measurement")
    other.reset(TemplateInstance(TemplateId.RANGE, "r2", {}, 0))
    assert (
        other.step(0, {"bp": 152.0, "meas": 1.0}) == -12.0
    )  # independent of the first evaluator


def test_logging_registry_forwards_and_logs() -> None:
    from ralmon.baselines.access import ReadLog

    log = ReadLog()
    wrapped = LoggingRegistry(_REGISTRY, log)
    assert wrapped.get("bp_band_low").value == 110.0
    assert wrapped.bounds("bp").lower == 50.0
    assert wrapped.version() == _REGISTRY.version()
    assert callable(wrapped.overrides)
    assert log.registry_reads == {"bp_band_low", "bounds:bp"}


def test_signal_grid_builds_held_values_impulses_and_derived_signals() -> None:
    grid = SignalGrid(STEP)
    day = observed(
        [smp("bp", 2, 125.0), smp("cuff_health", 2, 1.0)],
        [evt(EventKind.MEASUREMENT, 2), evt(EventKind.DISPENSE, 3)],
    )
    rows = {}
    for batch in iter_steps(day, TimingConfig(STEP, 0, 0), 5 * STEP):
        step = grid.apply(batch)
        rows[step.k] = step
    assert (
        "bp" not in rows[0].values and "bp" not in rows[1].values
    )  # undefined before the first sample
    assert rows[2].values["bp"] == 125.0 and rows[5].values["bp"] == 125.0  # held
    assert (
        rows[2].values["meas"] == 1.0 and rows[3].values["meas"] == 0.0
    )  # an impulse lasts one step
    assert rows[3].values["dispense"] == 1.0 and rows[4].values["dispense"] == 0.0
    assert rows[3].values["dose_count"] == 1.0 and rows[5].values["dose_count"] == 1.0
    assert (
        rows[3].values["bp_pre"] == 125.0
    )  # the value before the dose, captured at the dispense
    assert rows[2].measurements == (2 * STEP,) and rows[3].dispenses == (3 * STEP,)
    assert rows[3].measurements == ()


def test_signal_grid_origin_shifts_the_axis_to_the_day() -> None:
    grid = SignalGrid(STEP, origin_ms=T_DAY)
    day = ObservedDay(
        "p1",
        1,
        0,
        (Sample("bp", T_DAY, T_DAY, 125.0, None, None),),
        (
            Event(
                EventKind.DISPENSE, T_DAY + 3 * STEP, T_DAY + 3 * STEP, "dev", {}, None
            ),
        ),
        "plan-1",
    )
    # the harness grid of day 1 starts at 24 h; the evaluator axis starts at 0
    steps = [grid.apply(b) for b in iter_steps(day, TIMING, T_DAY + 4 * STEP)]
    assert [s.k for s in steps] == [0, 1, 2, 3, 4]
    assert steps[3].dispenses == (3 * STEP,)
    assert steps[0].values["bp"] == 125.0


# ---- the real evaluator, hand derivation (integration) --------------------------------------------------------


def test_b5_range_template_with_the_real_evaluator() -> None:
    """RANGE with the test-local band 110 to 140 mmHg: margin ``min(v - 110, 140 - v)`` = 15, -12, -5 for 125, 152, 105."""
    b5 = make_b5(
        templates=templ(TemplateId.RANGE),
        evaluator_factory=make_evaluator,
        alpha=0.2,
    )
    day = observed(
        [smp("bp", 3, 125.0), smp("bp", 6, 152.0), smp("bp", 9, 105.0)],
        [
            evt(EventKind.MEASUREMENT, 3),
            evt(EventKind.MEASUREMENT, 6),
            evt(EventKind.MEASUREMENT, 9),
        ],
    )
    b5.fit(train_days(), [bench(day)])
    out = run(b5, day)
    assert [(d.t_ms, pytest.approx(d.score)) for d in out] == [
        (6 * STEP, pytest.approx(12.0)),
        (9 * STEP, pytest.approx(5.0)),
    ]
    assert all(d.label is None for d in out)


def test_b5_resp_prediction_with_the_real_evaluator_uses_the_plan_ticks() -> None:
    """RESP needs a measurement in ``[delta1, delta2]`` after the dose with a drop of at least ``delta_resp`` (10 mmHg
    in the fixture registry); the plan supplies the measurement tick.

    Hand derivation. Dose at step ACT with the pre-dose pressure 150; one tick inside the window. Persistence predicts
    150 at the tick: drop 0, margin ``rho_hat = 0 - 10 = -10``. A calibration day with an actual drop ``d`` has
    ``rho_true = d - 10``, so the score is ``R = d``. Drops 0..8: ``n = 9``, ``alpha = 0.2``, ``k = ceil(10 * 0.8) = 8``,
    ``C = 7``; ``-10 + 7 = -3 < 0``: alert at the activation step with score 3, and the measured verdict at the
    deadline (``rho = -10``) adds no second detection.
    """
    resp = templ(TemplateId.RESP)
    delta1 = int(_REGISTRY.get("delta1").value) // STEP
    delta2 = int(_REGISTRY.get("delta2").value) // STEP
    tick = ACT + delta1 + 5  # a SCHED anchor inside the response window
    assert ACT + delta1 <= tick <= ACT + delta2
    plan = make_care_plan(
        [make_instance(TemplateId.SCHED, f"sched@{tick}", {}, tick * STEP)]
    )
    pre = 150.0

    def day_with(drop: float, patient: str) -> ObservedDay:
        return observed(
            [smp("bp", 0, pre), smp("bp", tick, pre - drop)],
            [evt(EventKind.DISPENSE, ACT), evt(EventKind.MEASUREMENT, tick)],
            patient=patient,
        )

    b5 = make_b5(
        templates=resp,
        evaluator_factory=make_evaluator,
        alpha=0.2,
        plan_for_day=lambda day: plan,
        timing=TimingConfig(
            STEP, 0, (delta2 + 5) * STEP
        ),  # long enough for the window to close
    )
    b5.fit(train_days(), [bench(day_with(d, f"c{i}")) for i, d in enumerate(range(9))])
    assert b5.n_calibration_episodes == 9 and b5.n_censored == 0
    out = b5.run(day_with(0.0, "t"), plan, None)
    (record,) = b5.predictions
    assert (record.sigma_hat, record.quantile, record.emitted) == (-10.0, 7.0, True)
    assert pairs(out) == [(ACT * STEP, 3.0)]


def test_b5_measured_decisions_agree_with_the_monitor() -> None:
    """Without a prediction B5 is the measured verdict of the templates: the first violated record of each instance of
    ``run_offline`` and the detection of B5 are at the same step, for all seven templates (hand-built day, fixture
    registry). This checks the signal construction and the instance creation that B5 repeats from the monitor."""
    from ralmon.monitor import run_offline
    from tests.monitor.helpers import make_config

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
    day = observed(samples, events)
    records = run_offline(
        day,
        plan,
        make_config(_REGISTRY),
        None,
        None,
        registry=_REGISTRY,
        templates=tuple(_LIBRARY.values()),
    )
    first: dict[str, int] = {}
    for r in records:
        if r.state.value == "violated" and r.instance_key not in first:
            first[r.instance_key] = r.t_eval_ms
    expected = sorted(first.values())
    assert len(expected) == 7  # range, sys, range, hold, count, resp, sched
    long_tail = TimingConfig(STEP, 0, 25 * 60 * STEP)
    for aggregation, times in (
        ("per_template", expected),
        ("conjunction", sorted(set(expected))),
    ):
        b5 = make_b5(
            templates=tuple(_LIBRARY.values()),
            evaluator_factory=make_evaluator,
            aggregation=aggregation,
            plan_for_day=lambda d: plan,
            timing=long_tail,
        )
        b5.fit(train_days(), [])
        out = b5.run(day, plan, None)
        assert [d.t_ms for d in out] == times, aggregation
        assert all(d.label is None and math.isfinite(d.score) for d in out)


# ---- the source of B5 ---------------------------------------------------------------------------------------------------


def test_b5_source_has_no_latent_or_scaling_tokens() -> None:
    source = B5_SOURCE.read_text(encoding="utf-8")
    for token in (
        "LatentDay",
        "GroundTruthEvent",
        "normalise",
        "rank_alerts",
        "scale_param",
        "priority_param",
    ):
        assert token not in source, token
    assert re.search(r"\b(110|140)\b", source) is None
    assert "locator" in source.lower() or "Section" in source


def test_b5_exported_from_the_package() -> None:
    from ralmon import baselines

    assert baselines.B5ConformalSTL is B5ConformalSTL
    assert not hasattr(B5ConformalSTL, "__ralmon_stub_owner__")
