"""ralmon.baselines: public API (see 02-interfaces.md#package-public-api)."""

from __future__ import annotations

from ralmon.baselines._stubs import (
    B1StaticThresholds,
    B2AnomalyDetection,
    B4ConformalOnly,
)
from ralmon.baselines.b3_plain_stl import B3PlainSTL
from ralmon.baselines.b5_conformal_stl import B5ConformalSTL
from ralmon.baselines.base import Detector

__all__ = [
    "B1StaticThresholds",
    "B2AnomalyDetection",
    "B3PlainSTL",
    "B4ConformalOnly",
    "B5ConformalSTL",
    "Detector",
]
