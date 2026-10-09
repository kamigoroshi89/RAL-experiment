"""SignalId, EventKind, Sample, Event and the ObservedTrace Protocol (WS05-T02).

The contract text of docs/plan/02-interfaces.md is parsed so that the enumerations cannot
drift from it.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest

from ralmon.signals import (
    DerivedSignal,
    Event,
    EventKind,
    ObservedTrace,
    Sample,
    SignalId,
    default_derived_signals,
    event_to_sample,
    hold_last,
    hours,
    impulses_on_grid,
    minutes,
)

INTERFACES = Path(__file__).resolve().parents[2] / "docs" / "plan" / "02-interfaces.md"


def _contract_members(class_name: str) -> list[tuple[str, str]]:
    """Members (NAME, value) of ``class <class_name>(...)`` in the contract, in order."""
    text = INTERFACES.read_text(encoding="utf-8")
    match = re.search(
        rf"^class {class_name}\(.*?\):\n((?:    .*\n|\n)+)", text, re.MULTILINE
    )
    assert match is not None, f"class {class_name} not found in the contract"
    return re.findall(r'^    ([A-Z0-9_]+) = "([^"]+)"', match.group(1), re.MULTILINE)


def test_signal_id_values_match_contract() -> None:
    expected = [
        ("BP", "bp"),
        ("MEAS", "meas"),
        ("DISPENSE", "dispense"),
        ("INTAKE", "intake"),
        ("SCHED_TICK", "sched_tick"),
        ("DOSE_COUNT", "dose_count"),
        ("MEAS_COUNT", "meas_count"),
        ("BP_PRE", "bp_pre"),
        ("BP_DROP", "bp_drop"),
        ("CUFF_HEALTH", "cuff_health"),
        ("INFLATION_MS", "inflation_ms"),
        ("PRESENCE", "presence"),
        ("AUTH", "auth"),
        ("DAY_END", "day_end"),
        ("HR_ECG", "hr_ecg"),
        ("HR_PULSE", "hr_pulse"),
        ("SPO2", "spo2"),
    ]
    assert len(expected) == 17
    assert [(m.name, m.value) for m in SignalId] == expected
    assert _contract_members("SignalId") == expected
    assert issubclass(SignalId, str)
    assert SignalId("bp") is SignalId.BP
    assert SignalId.BP == "bp"


def test_event_kind_values_match_contract() -> None:
    expected = [
        ("MEASUREMENT", "measurement"),
        ("MEASUREMENT_MISSED", "measurement_missed"),
        ("DISPENSE", "dispense"),
        ("INTAKE", "intake"),
        ("SCHEDULE_TICK", "schedule_tick"),
        ("NODE_STATE", "node_state"),
        ("ROBOT_TASK", "robot_task"),
        ("DEVICE_ERROR", "device_error"),
        ("VERIFICATION", "verification"),
    ]
    assert len(expected) == 9
    assert [(m.name, m.value) for m in EventKind] == expected
    assert _contract_members("EventKind") == expected


def test_sample_and_event_are_frozen_and_slotted() -> None:
    sample = Sample("bp", 1, 2, 3.0, None, None)
    event = Event(EventKind.DISPENSE, 1, 2, "dispenser", {}, None)
    with pytest.raises(dataclasses.FrozenInstanceError):
        sample.value = 4.0  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        event.kind = EventKind.INTAKE  # type: ignore[misc]
    assert not hasattr(sample, "__dict__")
    assert not hasattr(event, "__dict__")
    assert [f.name for f in dataclasses.fields(Sample)] == [
        "signal",
        "t_device_ms",
        "t_rx_ms",
        "value",
        "seq",
        "quality",
    ]
    assert [f.name for f in dataclasses.fields(Event)] == [
        "kind",
        "t_device_ms",
        "t_rx_ms",
        "source",
        "payload",
        "seq",
    ]


def test_sample_signal_field_accepts_a_signal_id_value() -> None:
    sample = Sample(SignalId.BP.value, 0, 0, 120.0, None, None)
    assert SignalId(sample.signal) is SignalId.BP


@dataclass(frozen=True, slots=True)
class _StructuralDay:
    patient_id: str
    day_index: int
    seed: int
    samples: Sequence[Sample]
    events: Sequence[Event]
    care_plan_id: str


@dataclass(frozen=True, slots=True)
class _DayWithoutCarePlan:
    patient_id: str
    day_index: int
    seed: int
    samples: Sequence[Sample]
    events: Sequence[Event]


def test_observed_trace_accepts_structural_day() -> None:
    day = _StructuralDay("p0", 0, 0, [], [], "cp0")
    assert isinstance(day, ObservedTrace)
    assert not isinstance(_DayWithoutCarePlan("p0", 0, 0, [], []), ObservedTrace)
    assert not isinstance(object(), ObservedTrace)


def test_real_signals_names_are_not_placeholders() -> None:
    names = (
        SignalId,
        DerivedSignal,
        ObservedTrace,
        hold_last,
        minutes,
        hours,
        default_derived_signals,
        event_to_sample,
        impulses_on_grid,
    )
    for obj in names:
        assert not hasattr(obj, "__ralmon_stub_owner__"), obj
