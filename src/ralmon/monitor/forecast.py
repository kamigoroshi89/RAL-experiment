"""``Forecast`` and ``Forecaster`` (02-interfaces.md#forecaster): the contract types only.

This task contains no forecaster and no conformal code: the predictive mode is WS05-T08 and the
forecasters are WS05-T05. ``Forecaster.fit`` is annotated with the structural ``ObservedTrace``
Protocol of ``ralmon.signals`` instead of ``ObservedDay`` (ADR-024: ``monitor`` never imports
``benchmark``; ``ObservedDay`` satisfies the Protocol).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from ralmon.signals import DurationMs, ObservedTrace, Sample, TimeMs

__all__ = ["Forecast", "Forecaster"]


@dataclass(frozen=True, slots=True)
class Forecast:
    signal: str
    t_from_ms: TimeMs
    horizon_ms: DurationMs
    mean: Sequence[float]  # point path on the monitor grid


class Forecaster(Protocol):
    name: str

    def fit(self, train_days: Sequence[ObservedTrace]) -> None: ...

    def predict(
        self, history: Sequence[Sample], t_ms: TimeMs, horizon_ms: DurationMs
    ) -> Forecast: ...
