"""Payload vocabulary of the observed event stream (WS04-T06).

``Event.payload`` is open in ``02-interfaces.md#trace-schema``. The keys that the evidence
derivation reads are fixed once, in the "Trace evidence conventions" table of
``docs/models/evidence-channels.md`` (WS02-T03): the names below are taken from it, not
invented here. Where this task needs a key that the table does not list (``kind`` of a
``SCHEDULE_TICK``), the key is owned by this module and no evidence field reads it.

Declared differences from the task text (WS04-T06 step 2 names an ``INTAKE`` key
``witness``): the conventions table says that the ``INTAKE`` event carries no payload ("the
event is the reading"), so none is declared, and the observed ``INTAKE`` event is witnessed
by construction (source ``robot``). The optional ``content_change`` of ``DISPENSE`` exists
in the vocabulary but the fault-free base does not emit it (a dispenser with content
sensing is a capability of the confounder variants of WS04-T09).

Later tasks add the keys they emit (``NODE_STATE``, ``DEVICE_ERROR``, the declined-task
outcome): they extend ``PAYLOAD_KEYS`` here, so a key can only enter a trace by being
declared. ``check_payload`` is the one conformity check.
"""

from __future__ import annotations

import math
import numbers
from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from ralmon.signals import EventKind

__all__ = [
    "ALL_PAYLOAD_KEYS",
    "KEY_CONTENT_CHANGE",
    "KEY_KIND",
    "KEY_OUTCOME",
    "KEY_PATIENT_ID",
    "KEY_TASK",
    "KINDS",
    "KIND_DOSE",
    "KIND_MEASUREMENT",
    "OUTCOMES",
    "OUTCOME_FAILED",
    "OUTCOME_LATE",
    "OUTCOME_SUCCESS",
    "OUTCOME_TIMEOUT",
    "PAYLOAD_KEYS",
    "SOURCE_CUFF",
    "SOURCE_DISPENSER",
    "SOURCE_ROBOT",
    "SOURCE_WARD",
    "TASKS",
    "TASK_MANIPULATE",
    "TASK_NAVIGATE",
    "TASK_WITNESS",
    "VocabularyError",
    "check_payload",
]

# Event sources (device or node identifiers).
SOURCE_CUFF: Final = "cuff"
SOURCE_DISPENSER: Final = "dispenser"
SOURCE_ROBOT: Final = "robot"
SOURCE_WARD: Final = "ward"  # the ward node that issues the care-plan ticks

# SCHEDULE_TICK: which care-plan step is due (owned by this module).
KEY_KIND: Final = "kind"
KIND_MEASUREMENT: Final = "measurement"
KIND_DOSE: Final = "dose"
KINDS: Final = (KIND_MEASUREMENT, KIND_DOSE)

# ROBOT_TASK (evidence-channels.md, Trace evidence conventions).
KEY_TASK: Final = "task"
TASK_NAVIGATE: Final = "navigate"
TASK_MANIPULATE: Final = "manipulate"
TASK_WITNESS: Final = "witness"
TASKS: Final = (TASK_NAVIGATE, TASK_MANIPULATE, TASK_WITNESS)
KEY_OUTCOME: Final = "outcome"
OUTCOME_SUCCESS: Final = "success"
OUTCOME_LATE: Final = "late"
OUTCOME_FAILED: Final = "failed"
OUTCOME_TIMEOUT: Final = "timeout"
OUTCOMES: Final = (OUTCOME_SUCCESS, OUTCOME_LATE, OUTCOME_FAILED, OUTCOME_TIMEOUT)
KEY_PATIENT_ID: Final = "patient_id"

# DISPENSE (evidence-channels.md, proposed by EC-GAP-1): after minus before, float.
KEY_CONTENT_CHANGE: Final = "content_change"

PAYLOAD_KEYS: Final[Mapping[EventKind, frozenset[str]]] = MappingProxyType(
    {
        EventKind.SCHEDULE_TICK: frozenset({KEY_KIND}),
        EventKind.MEASUREMENT: frozenset(),
        EventKind.DISPENSE: frozenset({KEY_CONTENT_CHANGE}),
        EventKind.INTAKE: frozenset(),
        EventKind.ROBOT_TASK: frozenset({KEY_TASK, KEY_OUTCOME, KEY_PATIENT_ID}),
    }
)
ALL_PAYLOAD_KEYS: Final[frozenset[str]] = frozenset().union(*PAYLOAD_KEYS.values())

_ENUMERATED: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {KEY_KIND: KINDS, KEY_TASK: TASKS, KEY_OUTCOME: OUTCOMES}
)


class VocabularyError(ValueError):
    """A payload carries a key or value that this vocabulary does not declare."""


def _check_value(key: str, value: object) -> None:
    if key in _ENUMERATED:
        if not isinstance(value, str) or value not in _ENUMERATED[key]:
            raise VocabularyError(
                f"payload {key!r} must be one of {_ENUMERATED[key]}, got {value!r}"
            )
    elif key == KEY_PATIENT_ID:
        if not isinstance(value, str) or not value.strip():
            raise VocabularyError(
                f"payload {key!r} must be a non-empty string, got {value!r}"
            )
    elif key == KEY_CONTENT_CHANGE:
        if isinstance(value, (bool, str)) or not isinstance(value, numbers.Real):
            raise VocabularyError(f"payload {key!r} must be a number, got {value!r}")
        try:
            finite = math.isfinite(float(value))
        except OverflowError:
            finite = False
        if not finite:
            raise VocabularyError(f"payload {key!r} must be finite, got {value!r}")


def check_payload(kind: object, payload: object) -> None:
    """Raise ``VocabularyError`` unless ``payload`` only uses keys and values declared for ``kind``."""
    if not isinstance(kind, EventKind):
        raise VocabularyError(f"kind must be an EventKind, got {kind!r}")
    if kind not in PAYLOAD_KEYS:
        raise VocabularyError(f"no payload is declared for events of kind {kind.value}")
    if not isinstance(payload, Mapping):
        raise VocabularyError(
            f"payload must be a mapping, got {type(payload).__name__}"
        )
    allowed = PAYLOAD_KEYS[kind]
    for key, value in payload.items():
        if not isinstance(key, str) or key not in allowed:
            raise VocabularyError(
                f"payload key {key!r} is not declared for {kind.value} events "
                f"(declared: {sorted(allowed)})"
            )
        _check_value(key, value)
