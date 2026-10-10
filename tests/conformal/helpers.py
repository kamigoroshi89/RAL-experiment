"""Shared fixtures of the conformal tests (WS05-T06). All numbers are FIXTURE-ONLY.

The names under test are read from ``ralmon.conformal`` at call time, so that the files collect
before the implementation exists.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

import ralmon.conformal as c
from ralmon.spec import TemplateId

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "tests" / "fixtures" / "conformal" / "golden_conformal.yaml"

# FIXTURE-ONLY: hand-computed calibration scores of the task text (n = 9).
FIXTURE_SCORES = [-0.2, -0.1, 0.0, 0.1, 0.1, 0.2, 0.3, 0.4, 0.6]


def episode(i: int, sigma_hat: float, sigma_true: float) -> Any:
    return c.CalibrationEpisode(
        patient_id=f"p{i:05d}",
        day_index=0,
        template=TemplateId.RANGE,
        sigma_hat=sigma_hat,
        sigma_true=sigma_true,
    )


def episodes_from_scores(scores: Sequence[float], sigma_hat: float = 0.0) -> list[Any]:
    """Episodes with the given ``sigma_hat`` and ``sigma_true = sigma_hat + R``.

    With ``sigma_hat = 0.0`` the value ``sigma_true`` is exactly the score, so hand values
    survive floating point.
    """
    return [episode(i, sigma_hat, sigma_hat + r) for i, r in enumerate(scores)]


def split_on(scores: Sequence[float], alpha: float = 0.2) -> Any:
    cal = c.SplitConformal()
    cal.fit(episodes_from_scores(scores), alpha)
    return cal


def load_golden() -> dict[str, dict[str, Any]]:
    data = yaml.safe_load(GOLDEN.read_text(encoding="utf-8"))
    return {case["id"]: case for case in data["cases"]}
