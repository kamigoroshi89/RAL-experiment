"""Fixture-only prior file builder for the benchmark tests (WS04-T02, reused by T03 to T13).

Every number below is FIXTURE-ONLY: chosen so that expected results can be computed by
hand, with no clinical meaning. A prior built here carries ``fixture_only: true`` and the
``fixture_only`` source type, so a ``LiteraturePriorSource`` refuses it unless the caller
passes ``allow_fixture_only=True``. Never describe these numbers as clinical.
"""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml

FIXTURE_REF = "FIXTURE-ONLY: arithmetic value, no source"

# Contract order of the 17 parameter rows (PatientParams, AdherenceParams, DeviceErrorModel).
_ROWS: tuple[dict[str, Any], ...] = (
    {
        "parameter": "baseline_sbp_mmhg",
        "unit": "mmHg",
        "dist": {"family": "uniform", "lo": 90.0, "hi": 110.0},
        "consumer_task": "WS04-T03",
    },
    {
        "parameter": "circadian_amplitude_mmhg",
        "unit": "mmHg",
        "value": 10.0,
        "consumer_task": "WS04-T03",
    },
    {
        "parameter": "ar_noise_sd_mmhg",
        "unit": "mmHg",
        "value": 2.0,
        "consumer_task": "WS04-T03",
    },
    {
        "parameter": "ar_noise_phi",
        "unit": "1",
        "value": 0.5,
        "reference_step_ms": 60_000,
        "consumer_task": "WS04-T03",
    },
    {
        "parameter": "emax_mmhg",
        "unit": "mmHg",
        "value": 20.0,
        "consumer_task": "WS04-T04",
    },
    {"parameter": "ec50", "unit": "1", "value": 1.0, "consumer_task": "WS04-T04"},
    {
        "parameter": "absorption_rate_per_h",
        "unit": "1/h",
        "value": 2.0,
        "consumer_task": "WS04-T04",
    },
    {
        "parameter": "elimination_rate_per_h",
        "unit": "1/h",
        "value": 0.5,
        "consumer_task": "WS04-T04",
    },
    {
        "parameter": "onset_delay_range_ms",
        "unit": "ms",
        "value": {"lower_ms": 3_600_000, "upper_ms": 7_200_000},
        "consumer_task": "WS04-T04",
    },
    {"parameter": "p_delay", "unit": "1", "value": 0.25, "consumer_task": "WS04-T05"},
    {
        "parameter": "p_omission",
        "unit": "1",
        "value": 0.125,
        "consumer_task": "WS04-T05",
    },
    {
        "parameter": "p_double_take",
        "unit": "1",
        "value": 0.0625,
        "consumer_task": "WS04-T05",
    },
    {
        "parameter": "mean_delay_ms",
        "unit": "ms",
        "value": 600_000,
        "consumer_task": "WS04-T05",
    },
    {
        "parameter": "cuff_error_sd_mmhg",
        "unit": "mmHg",
        "value": 4.0,
        "consumer_task": "WS04-T06",
    },
    {
        "parameter": "cuff_bias_mmhg",
        "unit": "mmHg",
        "value": 0.0,
        "consumer_task": "WS04-T06",
    },
    {
        "parameter": "dispenser_bounce_prob",
        "unit": "1",
        "value": 0.125,
        "consumer_task": "WS04-T07",
    },
    {
        "parameter": "ble_dropout_rate_per_h",
        "unit": "1/h",
        "value": 0.5,
        "consumer_task": "WS04-T07",
    },
)

FIXTURE_PARAMETERS: tuple[str, ...] = tuple(row["parameter"] for row in _ROWS)


def fixture_row(parameter: str) -> dict[str, Any]:
    """A complete, valid, fixture-only row (all schema keys present) for ``parameter``."""
    for base in _ROWS:
        if base["parameter"] == parameter:
            row: dict[str, Any] = {
                "parameter": parameter,
                "unit": base["unit"],
                "value": base.get("value"),
                "dist": base.get("dist"),
                "source_ref": FIXTURE_REF,
                "source_type": "fixture_only",
                "verified_by": None,
                "status": "filled",
                "consumer_task": base["consumer_task"],
                "rationale": "FIXTURE-ONLY arithmetic value",
                "note": "fixture row",
            }
            if "reference_step_ms" in base:
                row["reference_step_ms"] = base["reference_step_ms"]
            return row
    raise KeyError(parameter)


def unfilled_row(parameter: str) -> dict[str, Any]:
    """The awaiting_human_value form of a fixture row (value null, no source_ref)."""
    row = fixture_row(parameter)
    row.update(
        value=None,
        dist=None,
        source_ref=None,
        source_type=None,
        rationale=None,
        status="awaiting_human_value",
    )
    if "reference_step_ms" in row:
        row["reference_step_ms"] = None
    return row


def make_fixture_prior(
    tmp_path: Path,
    *,
    name: str = "fixture",
    fixture_only: bool = True,
    row_updates: Mapping[str, Mapping[str, Any]] | None = None,
    unfilled: Iterable[str] = (),
    drop: Iterable[str] = (),
    extra_rows: Iterable[Mapping[str, Any]] = (),
    top_level: Mapping[str, Any] | None = None,
    filename: str = "prior.yaml",
) -> Path:
    """Write a fixture-only prior YAML under ``tmp_path`` and return its path.

    ``row_updates`` maps a parameter name to keys that replace the fixture row's keys;
    ``unfilled`` turns the named rows into awaiting_human_value rows; ``drop`` removes
    rows; ``extra_rows`` are appended as given; ``top_level`` overrides or adds top-level
    keys. A key whose update value is the string ``"<DELETE>"`` is removed from the row.
    """
    rows = [fixture_row(p) for p in FIXTURE_PARAMETERS if p not in set(drop)]
    unfilled_set = set(unfilled)
    rows = [
        unfilled_row(r["parameter"]) if r["parameter"] in unfilled_set else r
        for r in rows
    ]
    for row in rows:
        for key, new in (row_updates or {}).get(row["parameter"], {}).items():
            if isinstance(new, str) and new == "<DELETE>":
                row.pop(key, None)
            else:
                row[key] = copy.deepcopy(new)
    rows.extend(copy.deepcopy(dict(r)) for r in extra_rows)
    document: dict[str, Any] = {
        "schema_version": "0.1.0",
        "name": name,
        "pathology": "hypertension",
        "fixture_only": fixture_only,
        "parameters": rows,
    }
    document.update(top_level or {})
    path = tmp_path / filename
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


@pytest.fixture
def fixture_prior_path(tmp_path: Path) -> Path:
    """A fully filled, fixture-only prior file under ``tmp_path``."""
    return make_fixture_prior(tmp_path)
