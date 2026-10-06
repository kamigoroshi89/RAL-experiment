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

WS04-T07 adds the keys of the C2 injectors, all taken from the same table: ``NODE_STATE``
(``state``, ``commanded``), ``DEVICE_ERROR`` (``error_code``) and the empty payload of
``MEASUREMENT_MISSED``; ``ROBOT_TASK`` already has ``task``, ``outcome`` and ``patient_id`` and
the injectors use the outcomes ``late`` and ``failed``. A ``NODE_STATE`` event needs its
``state`` and a ``DEVICE_ERROR`` its ``error_code`` (the table: "required in every report",
"non-empty"). Later tasks add the keys they emit (the declined-task outcome, the gateway
verification outcome): they extend ``PAYLOAD_KEYS`` here, so a key can only enter a trace by
being declared. ``check_payload`` is the one conformity check.

WS04-T08 adds the gateway verification outcome of the conventions table (gap G-4 of
``docs/models/evidence-channels.md``, ADR-035, interim until it is confirmed): a ``DEVICE_ERROR``
event from the source ``gateway`` with ``verification`` (the value ``failed``) and ``subject``
(the identifier of the device whose message failed verification). A device error carries
``error_code`` or the two keys of the gateway, never both kinds. The schema has no event kind for
a gateway outcome, so the failed verification of one message is logged as this event (the policy
"flag" of ``docs/models/threat-model.md`` hypothesis H-GW: the message itself stays in the trace).
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
    "BLE_DEVICES",
    "KEY_COMMANDED",
    "KEY_CONTENT_CHANGE",
    "KEY_ERROR_CODE",
    "KEY_KIND",
    "KEY_OUTCOME",
    "KEY_PATIENT_ID",
    "KEY_STATE",
    "KEY_SUBJECT",
    "KEY_TASK",
    "KEY_VERIFICATION",
    "KINDS",
    "KIND_DOSE",
    "KIND_MEASUREMENT",
    "OUTCOMES",
    "OUTCOME_FAILED",
    "OUTCOME_LATE",
    "OUTCOME_SUCCESS",
    "OUTCOME_TIMEOUT",
    "PAYLOAD_KEYS",
    "REQUIRED_ALTERNATIVES",
    "SOURCE_CUFF",
    "SOURCE_DISPENSER",
    "SOURCE_ECG",
    "SOURCE_GATEWAY",
    "SOURCE_OXIMETER",
    "SOURCE_ROBOT",
    "SOURCE_WARD",
    "STATES",
    "STATE_ACTIVE",
    "STATE_FINALIZED",
    "STATE_INACTIVE",
    "STATE_LINK_DOWN",
    "STATE_UNCONFIGURED",
    "STATE_UNREACHABLE",
    "TASKS",
    "TASK_MANIPULATE",
    "TASK_NAVIGATE",
    "TASK_WITNESS",
    "VERIFICATIONS",
    "VERIFICATION_FAILED",
    "VocabularyError",
    "check_payload",
]

# Event sources (device or node identifiers).
SOURCE_CUFF: Final = "cuff"
SOURCE_DISPENSER: Final = "dispenser"
SOURCE_ROBOT: Final = "robot"
SOURCE_WARD: Final = "ward"  # the ward node that issues the care-plan ticks
SOURCE_ECG: Final = "ecg"  # the ECG device (heart rate); a BLE device
SOURCE_OXIMETER: Final = "oximeter"  # the pulse oximeter (SpO2); a BLE device
SOURCE_GATEWAY: Final = (
    "gateway"  # the ward gateway: it verifies messages (a node, not a device)
)
# The BLE devices whose messages the gateway receives; a message of one of them can be verified.
BLE_DEVICES: Final = (SOURCE_CUFF, SOURCE_DISPENSER, SOURCE_ECG, SOURCE_OXIMETER)

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

# NODE_STATE (evidence-channels.md, Trace evidence conventions and D-4).
KEY_STATE: Final = "state"
STATE_UNCONFIGURED: Final = "unconfigured"
STATE_INACTIVE: Final = "inactive"
STATE_ACTIVE: Final = "active"
STATE_FINALIZED: Final = "finalized"
STATE_LINK_DOWN: Final = "link_down"  # the gateway lost the BLE connection of a device
STATE_UNREACHABLE: Final = "unreachable"  # a liveliness lease lapsed
STATES: Final = (
    STATE_UNCONFIGURED,
    STATE_INACTIVE,
    STATE_ACTIVE,
    STATE_FINALIZED,
    STATE_LINK_DOWN,
    STATE_UNREACHABLE,
)
KEY_COMMANDED: Final = "commanded"  # bool: the transition was announced as deliberate

# DEVICE_ERROR: a device-defined label, never a clinical value.
KEY_ERROR_CODE: Final = "error_code"
_MAX_ERROR_CODE: Final = 256  # algorithmic: longest error label
# DEVICE_ERROR from the gateway: the verification of one message failed (evidence-channels.md,
# Trace evidence conventions: interim convention of gap G-4).
KEY_VERIFICATION: Final = "verification"
VERIFICATION_FAILED: Final = "failed"
VERIFICATIONS: Final = (VERIFICATION_FAILED,)
KEY_SUBJECT: Final = (
    "subject"  # the source identifier of the device whose message failed
)

PAYLOAD_KEYS: Final[Mapping[EventKind, frozenset[str]]] = MappingProxyType(
    {
        EventKind.SCHEDULE_TICK: frozenset({KEY_KIND}),
        EventKind.MEASUREMENT: frozenset(),
        EventKind.DISPENSE: frozenset({KEY_CONTENT_CHANGE}),
        EventKind.INTAKE: frozenset(),
        EventKind.ROBOT_TASK: frozenset({KEY_TASK, KEY_OUTCOME, KEY_PATIENT_ID}),
        EventKind.NODE_STATE: frozenset({KEY_STATE, KEY_COMMANDED}),
        EventKind.DEVICE_ERROR: frozenset(
            {KEY_ERROR_CODE, KEY_VERIFICATION, KEY_SUBJECT}
        ),
        EventKind.MEASUREMENT_MISSED: frozenset(),
    }
)
# What a payload of the kind must carry, only where the conventions table says so: a tuple of
# alternatives, and a payload needs every key of at least one of them (a later task that adds
# another way to report, for example the failed verification of the gateway, adds an
# alternative instead of loosening this).
REQUIRED_ALTERNATIVES: Final[Mapping[EventKind, tuple[frozenset[str], ...]]] = (
    MappingProxyType(
        {
            EventKind.NODE_STATE: (frozenset({KEY_STATE}),),
            EventKind.DEVICE_ERROR: (
                frozenset({KEY_ERROR_CODE}),
                frozenset({KEY_VERIFICATION, KEY_SUBJECT}),
            ),
        }
    )
)
ALL_PAYLOAD_KEYS: Final[frozenset[str]] = frozenset().union(*PAYLOAD_KEYS.values())

_ENUMERATED: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        KEY_KIND: KINDS,
        KEY_TASK: TASKS,
        KEY_OUTCOME: OUTCOMES,
        KEY_STATE: STATES,
        KEY_VERIFICATION: VERIFICATIONS,
    }
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
    elif key == KEY_COMMANDED:
        if not isinstance(value, bool):
            raise VocabularyError(f"payload {key!r} must be a bool, got {value!r}")
    elif key in (KEY_ERROR_CODE, KEY_SUBJECT):
        if (
            not isinstance(value, str)
            or not value.strip()
            or len(value) > _MAX_ERROR_CODE
        ):
            raise VocabularyError(
                f"payload {key!r} must be a non-empty string of at most "
                f"{_MAX_ERROR_CODE} characters, got {value!r}"
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
    try:
        items = list(payload.items())
    except Exception as exc:  # a mapping whose methods misbehave
        raise VocabularyError(f"payload cannot be read: {type(exc).__name__}") from exc
    for key, value in items:
        if not isinstance(key, str) or key not in allowed:
            raise VocabularyError(
                f"payload key {key!r} is not declared for {kind.value} events "
                f"(declared: {sorted(allowed)})"
            )
        _check_value(key, value)
    keys = {key for key, _ in items}
    alternatives = REQUIRED_ALTERNATIVES.get(kind)
    if alternatives is not None and not any(
        alternative <= keys for alternative in alternatives
    ):
        raise VocabularyError(
            f"payload of a {kind.value} event needs "
            + " or ".join(str(sorted(a)) for a in alternatives)
        )
    if (
        kind is EventKind.DEVICE_ERROR
        and KEY_ERROR_CODE in keys
        and (KEY_VERIFICATION in keys or KEY_SUBJECT in keys)
    ):
        raise VocabularyError(
            "a device error carries an error code or a failed verification, not both"
        )
