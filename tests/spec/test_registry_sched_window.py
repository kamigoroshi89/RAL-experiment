"""Registry 0.2.1 (ADR-068): ``sched_window`` is 30 min, so that a care-plan schedule can be derived.

With registry 0.2.0 the real values ``hold_lookback = sched_window = 3600000`` ms left no admissible
pre-dose tick (``[a - hold_lookback, a - sched_window)`` is empty), and nothing noticed it because every
schedule test used a fixture registry. These tests read the REAL registry file as the repo loads it
(``load_registry``) and the REAL care-plan design rows through the repo's own functions, and pin the
nature of the new ``sched_window`` row (a declared design choice without literature source, unreviewed).
The loader check (``hold_lookback`` must be longer than ``sched_window``) is tested on the F0 fixture
document with a modified value.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ralmon.benchmark.schedule import (
    CARE_PLAN_RELPATH,
    DOSES_ROW,
    N_MEASUREMENTS_ROW,
    check_schedule_consistency,
    derive_schedule,
    load_filled_rows,
    load_schedule,
)
from ralmon.spec import load_registry
from ralmon.spec.registry import LoadedRegistry, RegistryError

from .helpers import (
    REAL_REGISTRY_PATH,
    ROOT,
    STEP_MS,
    entry_of,
    f0_doc,
    make_unset,
    write_yaml,
)

HOUR_MS = 3_600_000


def real_registry() -> LoadedRegistry:
    return load_registry(step_ms=STEP_MS)


def windows(registry: LoadedRegistry) -> dict[str, int]:
    """The four windows exactly as the benchmark builder reads them from the registry."""
    return {
        "hold_lookback_ms": int(registry.get("hold_lookback").value),
        "delta1_ms": int(registry.get("delta1").value),
        "delta2_ms": int(registry.get("delta2").value),
        "sched_window_ms": int(registry.get("sched_window").value),
    }


def load_doc(tmp_path: Path, doc: dict[str, Any], **kwargs: Any) -> LoadedRegistry:
    kwargs.setdefault("allow_fixture_only", True)
    return load_registry(write_yaml(tmp_path, doc), **kwargs)


# --- the real registry gives a feasible schedule ---------------------------------------


def test_the_real_registry_gives_a_feasible_schedule_for_the_default_care_plan() -> (
    None
):
    registry = real_registry()
    w = windows(registry)
    rows = load_filled_rows(ROOT / CARE_PLAN_RELPATH, (DOSES_ROW, N_MEASUREMENTS_ROW))
    doses, n_measurements = rows[DOSES_ROW], rows[N_MEASUREMENTS_ROW]
    assert isinstance(doses, list) and doses and isinstance(n_measurements, int)

    schedule = derive_schedule(doses, n_measurements, **w)

    assert len(schedule.measurement_ticks_ms) == n_measurements
    assert list(schedule.dose_ticks_ms) == doses
    assert check_schedule_consistency(schedule, **w) == ()
    # the repo's own file reader gives the same schedule
    assert load_schedule(ROOT / CARE_PLAN_RELPATH, **w) == schedule


def test_the_real_registry_leaves_room_for_a_pre_dose_tick() -> None:
    w = windows(real_registry())
    assert w["hold_lookback_ms"] > w["sched_window_ms"]
    # HOLD is the safety rule and keeps its 60 min look-back (ADR-068)
    assert w["hold_lookback_ms"] == HOUR_MS


# --- the loading path refuses a registry that cannot hold a schedule ---------------------


@pytest.mark.parametrize("sched_window", [3_600_000.0, 5_400_000.0])
def test_a_registry_whose_hold_lookback_is_not_longer_than_sched_window_is_refused(
    tmp_path: Path, sched_window: float
) -> None:
    doc = f0_doc()
    assert entry_of(doc, "hold_lookback")["value"] == 3_600_000.0
    entry_of(doc, "sched_window")["value"] = sched_window
    with pytest.raises(RegistryError) as info:
        load_doc(tmp_path, doc, step_ms=STEP_MS)
    message = str(info.value)
    assert "hold_lookback" in message and "sched_window" in message
    assert "longer than" in message and "schedule" in message


def test_the_window_check_does_not_need_step_ms(tmp_path: Path) -> None:
    doc = f0_doc()
    entry_of(doc, "sched_window")["value"] = 3_600_000.0
    with pytest.raises(RegistryError, match=r"hold_lookback.*sched_window"):
        load_doc(tmp_path, doc)


def test_a_hold_lookback_one_step_longer_than_sched_window_is_accepted(
    tmp_path: Path,
) -> None:
    doc = f0_doc()
    entry_of(doc, "sched_window")["value"] = 3_600_000.0 - STEP_MS
    registry = load_doc(tmp_path, doc, step_ms=STEP_MS)
    assert registry.get("sched_window").value == 3_600_000.0 - STEP_MS


def test_the_window_check_is_skipped_while_one_of_the_two_names_is_unset(
    tmp_path: Path,
) -> None:
    doc = f0_doc()
    make_unset(doc, "sched_window", ("sched",))
    registry = load_doc(tmp_path, doc, step_ms=STEP_MS)
    assert not registry.is_set("sched_window")


# --- version 0.2.1 and the nature of the new row ------------------------------------------


def test_the_real_registry_is_version_0_2_1() -> None:
    assert real_registry().version() == "0.2.1"
    assert 'registry_version: "0.2.1"' in REAL_REGISTRY_PATH.read_text(encoding="utf-8")


def test_sched_window_is_a_declared_design_choice_of_30_minutes_without_a_reviewer() -> (
    None
):
    entry = real_registry().get("sched_window")
    assert entry.value == 1_800_000.0 and entry.unit == "ms"
    assert entry.reviewed_by is None
    assert entry.rationale.startswith("design choice")
    assert "ADR-068" in entry.rationale and "2026-10-10" in entry.rationale
    assert "not literature" in entry.rationale
    assert entry.rationale.endswith("illustrative, unverified")
    assert "ADR-068" in entry.source_ref
    # the ISMP rationale of 0.2.0 is kept as the history of the old value, not as the support of the new one
    assert "ISMP" in entry.rationale and "0.2.0" in entry.rationale
    assert not entry.rationale.startswith("literature-anchored")
    # the whole registry stays unreviewed
    assert real_registry().review_status == "unreviewed"


def test_the_derived_sched_latency_follows_the_new_window() -> None:
    registry = real_registry()
    assert registry.get("max_latency_sched").value == 1_800_000.0 + STEP_MS
