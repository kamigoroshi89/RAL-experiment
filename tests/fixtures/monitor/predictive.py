"""Fixtures of the predictive tests of WS05-T08: the calibrator fixture, stub forecasters and plan builders.

FIXTURE-ONLY. Every number is fixture arithmetic on the F0 fixture registry (``step_ms = 60000``,
``sched_window = scale_sched = 1800000``, ``delta1 = 3600000``, ``delta2 = 10800000``,
``scale_resp = 20``, ``delta_resp = 10``) and on the nine scores of the WS05-T06 fixture; nothing here is a
clinical statement and nothing is clinically validated. Time labels convert as
``t_ms = (60 * hh + mm) * 60000``.

The stub forecasters return fixed paths: they read nothing but the arguments they are given, hold no
random generator and no clock, and record every call so that a test can see the horizon, the history
and the target signal that the monitor passed.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ralmon.conformal import CalibrationEpisode, SplitConformal
from ralmon.monitor import Forecast, InsufficientHistoryError
from ralmon.signals import Sample
from ralmon.spec import CarePlan, TemplateId, TemplateInstance

STEP = 60_000
T_DAY = 86_400_000

#: The nine residual scores of the WS05-T06 fixture, ``R = sigma_true - sigma_hat`` (FIXTURE-ONLY).
R_SCORES: tuple[float, ...] = (-0.2, -0.1, 0.0, 0.1, 0.1, 0.2, 0.3, 0.4, 0.6)


def hhmm(hh: int, mm: int = 0, day: int = 0) -> int:
    """``hh:mm`` of day ``day`` on the continuing axis, as integer milliseconds (ADR-017)."""
    return day * T_DAY + (60 * hh + mm) * 60_000


def calibrator(
    version: str | None = "v1",
    scores: Sequence[float] = R_SCORES,
    alpha: float = 0.2,
) -> SplitConformal:
    """A ``SplitConformal`` fitted on episodes whose scores are ``scores`` (``sigma_hat = 0``)."""
    episodes = [
        CalibrationEpisode(f"cal-{i}", 0, TemplateId.SCHED, 0.0, float(score))
        for i, score in enumerate(scores)
    ]
    fitted = SplitConformal()
    fitted.fit(episodes, alpha, model_version=version)
    return fitted


@dataclass(frozen=True)
class Call:
    """One call of a stub forecaster."""

    signal: str | None
    t_ms: int
    horizon_ms: int
    history: tuple[Sample, ...]


@dataclass
class StubForecaster:
    """A forecaster that returns fixed paths and records its calls.

    * ``arrival``: the predicted arrival of the measurement (signal ``meas``) as an absolute time in ms, a
      mapping from the issue time ``t_ms`` to such a time, or a callable of ``t_ms``; ``None`` (or a missing
      key) raises ``InsufficientHistoryError`` (the forecaster has no basis for the arrival).
    * ``bp``: the predicted blood pressure (signal ``bp``): a number, or a callable of the absolute time.
    * ``raw``: replaces every path by ``raw(signal, t_ms, horizon_ms, n)`` (extreme paths of a property test).
    * ``raises``: an exception that ``predict`` raises instead of answering.
    """

    arrival: int | Mapping[int, int | None] | Callable[[int], int | None] | None = None
    bp: float | Callable[[int], float] | None = None
    signals: frozenset[str] = frozenset({"meas"})
    version: str = "v1"
    raw: Callable[[str, int, int, int], list[float]] | None = None
    raises: BaseException | None = None
    step_ms: int = STEP
    name: str = "stub"
    calls: list[Call] = field(default_factory=list)

    @property
    def model_version(self) -> str:
        return self.version

    @property
    def supported_signals(self) -> frozenset[str]:
        return self.signals

    def fit(self, train_days: Sequence[Any]) -> None:
        """Nothing is learned."""

    def refit(self, version: str) -> None:
        """A refit that changes the model version."""
        self.version = version

    def _arrival_at(self, t_ms: int) -> int | None:
        spec = self.arrival
        if spec is None:
            return None
        if isinstance(spec, int):
            return spec
        if callable(spec):
            return spec(t_ms)
        return spec.get(t_ms)

    def predict(
        self,
        history: Sequence[Sample],
        t_ms: int,
        horizon_ms: int,
        *,
        signal: str | None = None,
    ) -> Forecast:
        self.calls.append(Call(signal, t_ms, horizon_ms, tuple(history)))
        if self.raises is not None:
            raise self.raises
        target = signal if signal is not None else next(iter(sorted(self.signals)))
        n = horizon_ms // self.step_ms
        if self.raw is not None:
            return Forecast(
                target, t_ms, horizon_ms, self.raw(target, t_ms, horizon_ms, n)
            )
        mean = [0.0] * n
        if target == "meas":
            arrival = self._arrival_at(t_ms)
            if arrival is None:
                raise InsufficientHistoryError(
                    "the stub has no arrival for this instant"
                )
            index = max(1, -(-(arrival - t_ms) // self.step_ms)) - 1
            if index < n:
                mean[index] = 1.0
        elif target == "bp":
            spec = self.bp
            if spec is None:
                raise InsufficientHistoryError("the stub has no pressure")
            for k in range(n):
                at = t_ms + (k + 1) * self.step_ms
                mean[k] = float(spec(at)) if callable(spec) else float(spec)
        return Forecast(target, t_ms, horizon_ms, mean)


class SpyCalibrator:
    """A ``SplitConformal`` that records the ``sigma_hat`` and the level of every ``predict`` call."""

    def __init__(self, inner: SplitConformal) -> None:
        self._inner = inner
        self.sigma_hats: list[float] = []
        self.levels: list[Any] = []
        self.variants: list[str] = []

    @property
    def mode(self) -> str:
        return self._inner.mode

    @property
    def calibrated_for(self) -> str | None:
        return self._inner.calibrated_for

    @calibrated_for.setter
    def calibrated_for(self, value: str | None) -> None:
        self._inner.calibrated_for = value

    def fit(
        self, episodes: Any, alpha: Any, *, model_version: str | None = None
    ) -> None:
        self._inner.fit(episodes, alpha, model_version=model_version)

    def quantile(self, alpha: Any) -> float:
        return self._inner.quantile(alpha)

    def quantile_lower(self, alpha: Any) -> float:
        return self._inner.quantile_lower(alpha)

    def predict(self, sigma_hat: float, alpha: Any, *, variant: Any = "likely") -> Any:
        self.sigma_hats.append(sigma_hat)
        self.levels.append(alpha)
        self.variants.append(variant)
        return self._inner.predict(sigma_hat, alpha, variant=variant)

    def update(self, sigma_hat: float, sigma_true: float) -> None:
        self._inner.update(sigma_hat, sigma_true)


def plan(
    registry: Any,
    *,
    sched: Iterable[int] = (),
    schedule: Iterable[int] = (),
    day_end: Iterable[int] = (),
    care_plan_id: str = "plan-1",
    patient_id: str = "p-1",
) -> CarePlan:
    """A plan with a static SCHED instance at each ``sched`` tick and a plain schedule of ticks.

    ``schedule`` lists the ticks of the plan (measurement ticks and dispense ticks, ``CarePlan.schedule``
    has no kind); the measurement ticks are the anchors of the SCHED instances, the others are dispense
    ticks (ADR-060).
    """
    instances: list[TemplateInstance] = [
        TemplateInstance(TemplateId.SCHED, f"sched@{a}", {}, a) for a in sched
    ]
    instances += [
        TemplateInstance(TemplateId.COUNT, f"count@{a}", {}, a) for a in day_end
    ]
    return CarePlan(
        care_plan_id=care_plan_id,
        pathway_template_id="hypertension-fixture",
        patient_id=patient_id,
        registry_version=registry.version(),
        instances=tuple(instances),
        schedule=tuple(schedule),
        plan_version=1,
        signature=None,
    )
