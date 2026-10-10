"""SignalId: the nineteen signals of the Signals contract (02-interfaces.md#signals).

The members and their order follow the contract and docs/formal/01-signals-sampling.md
section 2.1. The last two, ``nav_eta_ms`` and ``task_queue_ms``, are the robot-state signals added
by WS05-T05 (ADR-057): the input of the deadline forecaster, not signals of any template. ``Sample.signal`` carries one of these values as a plain string.
"""

from __future__ import annotations

from enum import Enum


class SignalId(str, Enum):
    BP = "bp"  # last measured systolic pressure, piecewise-constant
    MEAS = "meas"  # measurement indicator (impulse)
    DISPENSE = "dispense"  # dispenser opened (impulse)
    INTAKE = "intake"  # intake verified by the robot (impulse)
    SCHED_TICK = "sched_tick"  # care-plan step due (impulse)
    DOSE_COUNT = "dose_count"  # derived: dispenses in the trailing 24 h
    MEAS_COUNT = "meas_count"  # derived: measurements in the current day
    BP_PRE = "bp_pre"  # derived: pre-dose reference pressure
    BP_DROP = "bp_drop"  # derived: bp_pre minus bp
    CUFF_HEALTH = "cuff_health"  # 1.0 healthy
    INFLATION_MS = "inflation_ms"  # cuff inflation duration
    PRESENCE = "presence"  # robot-observed presence of the patient
    AUTH = "auth"  # authenticated dispense event
    DAY_END = "day_end"  # end-of-day marker for count obligations
    HR_ECG = "hr_ecg"
    HR_PULSE = "hr_pulse"  # pulse rate reported by the cuff
    SPO2 = "spo2"
    NAV_ETA = "nav_eta_ms"  # remaining navigation time to the patient room, published by the robot task layer (integer ms)
    TASK_QUEUE = "task_queue_ms"  # summed estimated duration of the tasks queued ahead of the care-delivery task (integer ms)
