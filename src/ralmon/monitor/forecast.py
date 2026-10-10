"""``Forecast`` and ``Forecaster`` (02-interfaces.md#forecaster): the contract types only.

The contract types live here; the three concrete forecasters are in ``forecasters.py`` (WS05-T05) and
the predictive mode is WS05-T08. ``Forecaster.fit`` is annotated with the structural ``ObservedTrace``
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
    """A point path on the monitor grid (index convention, read by WS05-T08 and WS06-T03).

    A forecast issued at ``t_ms`` has ``t_from_ms == t_ms`` and
    ``len(mean) == horizon_ms // step_ms`` (floor). ``mean[k]`` predicts the value at the grid time
    ``t_from_ms + (k + 1) * step_ms``: the first entry is one step after the issue time and the
    value at ``t_from_ms`` itself is the last observation, not part of the path. For the impulse
    signal ``meas`` an entry is 1.0 at the first grid step at or after the predicted instant (the
    ceiling rule of docs/formal/01-signals-sampling.md section 3.3) and 0.0 elsewhere. To read the
    path at a later instant ``t`` use index ``(t - t_from_ms) // step_ms - 1``.
    """

    signal: str
    t_from_ms: TimeMs
    horizon_ms: DurationMs
    mean: Sequence[float]  # point path on the monitor grid


class Forecaster(Protocol):
    """What the monitor and the baselines call; the classes of ``forecasters.py`` implement it.

    ``model_version`` is a token that changes whenever the fitted parameters change; a conformal
    calibrator records the token it was calibrated for (``calibrated_for``) and the monitor refuses
    a calibrator older than the model (WS05 decision D10). ``supported_signals`` are the
    ``Forecast.signal`` values the forecaster can produce. The concrete classes also accept a
    keyword-only ``signal`` on ``predict`` to name the target; a caller that uses only the three
    contract arguments gets the single supported signal present in ``history``.
    """

    name: str

    @property
    def model_version(self) -> str: ...

    @property
    def supported_signals(self) -> frozenset[str]: ...

    def fit(self, train_days: Sequence[ObservedTrace]) -> None: ...

    def predict(
        self, history: Sequence[Sample], t_ms: TimeMs, horizon_ms: DurationMs
    ) -> Forecast: ...
