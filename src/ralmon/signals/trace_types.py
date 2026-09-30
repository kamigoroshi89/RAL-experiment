"""Sample, Event and EventKind (02-interfaces.md#trace-schema): the single definition.

Created by WS04-T01 because WS05-T02 was not done; WS05-T02 imports these names and
does not redefine them. ``signal`` holds a ``SignalId`` value (see the Signals contract).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from ralmon.signals.units import TimeMs


class EventKind(str, Enum):
    MEASUREMENT = (
        "measurement"  # a blood-pressure measurement was attempted and produced a value
    )
    MEASUREMENT_MISSED = (
        "measurement_missed"  # observed only if the device reports a failed attempt
    )
    DISPENSE = "dispense"  # dispenser opened / pill released (does NOT prove intake)
    INTAKE = "intake"  # intake verified by the robot witness
    SCHEDULE_TICK = "schedule_tick"  # a care-plan step becomes due
    NODE_STATE = (
        "node_state"  # lifecycle or liveliness change of a device or robot node
    )
    ROBOT_TASK = "robot_task"  # navigation or manipulation task outcome
    DEVICE_ERROR = "device_error"  # error code from a device (e.g. cuff)


@dataclass(frozen=True, slots=True)
class Sample:
    signal: str  # a SignalId value (see #signals)
    t_device_ms: TimeMs
    t_rx_ms: TimeMs  # equals t_device_ms in offline traces without transport delay
    value: float  # continuous value; for indicators 1.0
    seq: int | None  # device sequence number (None if the device provides none)
    quality: float | None  # signal quality index in [0, 1], None if unavailable


@dataclass(frozen=True, slots=True)
class Event:
    kind: EventKind
    t_device_ms: TimeMs
    t_rx_ms: TimeMs
    source: str  # device or node identifier
    payload: Mapping[str, float | int | str | bool]
    seq: int | None
