"""Integrity of a distributed care plan (analisi §4.9 item 7, review item R1-W9).

``canonical_plan_bytes`` is the deterministic byte form of a ``CarePlan``: a JSON object with the
sorted keys of every field except ``signature`` (so a field added later is signed without a change of
this definition), compact separators, UTF-8; integers are written as integers (64-bit signed range),
parameter values as floats, non-finite numbers are refused, sequences keep their order.

``HmacSha256PlanVerifier`` signs and verifies with HMAC-SHA256 over those bytes (standard library,
``hmac.compare_digest``, lowercase hex digest). ``verify_plan`` is the load-time check: signature,
registry version, and whether a signature is required. The scheme is ADR-051 (proposed): a shared
key means that whoever can verify can also sign, so it covers accidental corruption and
modification by a party without the key, not a compromised specification, and it cannot see a
replay of an old plan at an equal ``plan_version`` (docs/formal/07-alert-tuple-mapping.md OP-T07-12).
The monotonic ``plan_version`` rule belongs to the monitor that loads the plan (WS05-T04).
"""

from __future__ import annotations

import dataclasses
import hashlib
import hmac
import json
import math
import numbers
from collections.abc import Callable, Mapping
from enum import Enum
from typing import Final, Protocol

from ralmon.spec._text import show
from ralmon.spec.plan import CarePlan, TemplateInstance

__all__ = [
    "HmacSha256PlanVerifier",
    "PlanIntegrityError",
    "PlanVerifier",
    "canonical_plan_bytes",
    "verify_plan",
]

# algorithmic: the range of a signed 64-bit integer, so that the back-end need not be Python
_INT_MAX: Final = 9_223_372_036_854_775_807
_INT_MIN: Final = -_INT_MAX - 1
_HEX_DIGITS: Final = frozenset("0123456789abcdef")
_SIGNATURE_LENGTH: Final = hashlib.sha256().digest_size * 2


class PlanIntegrityError(Exception):
    """A care plan cannot be serialised, its signature or version does not verify, or the verifier
    is unusable."""


class PlanVerifier(Protocol):
    def verify(self, payload: bytes, signature: str) -> bool: ...


# ---------------------------------------------------------------------------------------
# Canonical bytes
# ---------------------------------------------------------------------------------------


def _text(value: object, where: str) -> str:
    if isinstance(value, Enum):
        value = value.value
    if not isinstance(value, str):
        raise PlanIntegrityError(f"{where}: expected a str, got {show(value)}")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise PlanIntegrityError(
            f"{where}: the text cannot be encoded as UTF-8: {exc}"
        ) from exc
    return value[:]


def _integer(value: object, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, numbers.Integral):
        raise PlanIntegrityError(f"{where}: expected an integer, got {show(value)}")
    number = int(value)
    if not _INT_MIN <= number <= _INT_MAX:
        raise PlanIntegrityError(
            f"{where}: the integer is outside the signed 64-bit range"
        )
    return number


def _optional_integer(value: object, where: str) -> int | None:
    return None if value is None else _integer(value, where)


def _finite_float(value: object, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise PlanIntegrityError(f"{where}: expected a number, got {show(value)}")
    try:
        number = float(value)
    except (OverflowError, ValueError, TypeError) as exc:
        raise PlanIntegrityError(
            f"{where}: the number is outside the float range"
        ) from exc
    if not math.isfinite(number):
        raise PlanIntegrityError(f"{where}: a non-finite number cannot be signed")
    return number


def _params(value: object, where: str) -> dict[str, float]:
    if not isinstance(value, Mapping):
        raise PlanIntegrityError(f"{where}: expected a mapping, got {show(value)}")
    out: dict[str, float] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise PlanIntegrityError(f"{where}: keys must be str, got {show(key)}")
        out[_text(key, f"{where} key")] = _finite_float(item, f"{where}[{show(key)}]")
    return out


def _sequence(value: object, where: str) -> list[object]:
    if not isinstance(value, (list, tuple)):
        raise PlanIntegrityError(
            f"{where}: expected a list or a tuple, got {show(value)}"
        )
    return list(value)


def _ticks(value: object, where: str) -> list[int]:
    return [
        _integer(tick, f"{where}[{i}]")
        for i, tick in enumerate(_sequence(value, where))
    ]


def _generic(value: object, where: str) -> object:
    """Encoding of a field that has no dedicated rule (a field added to the dataclass later)."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise PlanIntegrityError(f"{where}: a bool is not a plan value")
    if isinstance(value, (str, Enum)):
        return _text(value, where)
    if isinstance(value, numbers.Integral):
        return _integer(value, where)
    if isinstance(value, numbers.Real):
        return _finite_float(value, where)
    if isinstance(value, Mapping):
        return {
            _text(k, where): _generic(v, f"{where}[{show(k)}]")
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_generic(v, f"{where}[{i}]") for i, v in enumerate(value)]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            f.name: _generic(getattr(value, f.name), f"{where}.{f.name}")
            for f in dataclasses.fields(value)
        }
    raise PlanIntegrityError(f"{where}: unsupported type {type(value).__name__}")


_INSTANCE_FIELDS: Final[Mapping[str, Callable[[object, str], object]]] = {
    "template": _text,
    "instance_key": _text,
    "param_values": _params,
    "anchor_ms": _optional_integer,
}


def _instance(value: object, where: str) -> dict[str, object]:
    if not isinstance(value, TemplateInstance):
        raise PlanIntegrityError(
            f"{where}: expected a TemplateInstance, got {show(value)}"
        )
    out: dict[str, object] = {}
    for field in dataclasses.fields(TemplateInstance):
        encode = _INSTANCE_FIELDS.get(field.name, _generic)
        out[field.name] = encode(getattr(value, field.name), f"{where}.{field.name}")
    return out


def _instances(value: object, where: str) -> list[dict[str, object]]:
    return [
        _instance(item, f"{where}[{i}]")
        for i, item in enumerate(_sequence(value, where))
    ]


_PLAN_FIELDS: Final[Mapping[str, Callable[[object, str], object]]] = {
    "care_plan_id": _text,
    "pathway_template_id": _text,
    "patient_id": _text,
    "registry_version": _text,
    "instances": _instances,
    "schedule": _ticks,
    "plan_version": _integer,
}


def canonical_plan_bytes(plan: CarePlan) -> bytes:
    """The canonical bytes of ``plan``: every field except ``signature``, sorted keys, compact
    separators, UTF-8. Raises ``PlanIntegrityError`` for a value that cannot be signed."""
    if not isinstance(plan, CarePlan):
        raise PlanIntegrityError(f"expected a CarePlan, got {show(plan)}")
    body: dict[str, object] = {}
    for field in dataclasses.fields(CarePlan):
        if field.name == "signature":
            continue
        encode = _PLAN_FIELDS.get(field.name, _generic)
        body[field.name] = encode(getattr(plan, field.name), f"plan.{field.name}")
    try:
        text = json.dumps(
            body,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        return text.encode("utf-8")
    except (ValueError, TypeError, OverflowError, RecursionError) as exc:
        raise PlanIntegrityError(f"the plan cannot be serialised: {exc}") from exc


# ---------------------------------------------------------------------------------------
# HMAC-SHA256
# ---------------------------------------------------------------------------------------


class HmacSha256PlanVerifier:
    """Signs and verifies care plans with HMAC-SHA256 over ``canonical_plan_bytes``.

    The signature is the lowercase hex digest. The key is shared: whoever can verify can also sign
    (ADR-051). An empty key, or a key that is not ``bytes`` or ``bytearray``, raises
    ``PlanIntegrityError``.
    """

    __slots__ = ("_key",)

    def __init__(self, key: bytes) -> None:
        if not isinstance(key, (bytes, bytearray)) or not key:
            raise PlanIntegrityError(
                f"the HMAC key must be non-empty bytes, got {type(key).__name__}"
            )
        self._key = bytes(key)

    def __repr__(self) -> str:
        return "HmacSha256PlanVerifier()"

    def _digest(self, payload: bytes) -> str:
        return hmac.new(self._key, payload, hashlib.sha256).hexdigest()

    def sign(self, plan: CarePlan) -> str:
        """The hex digest of HMAC-SHA256 over the canonical bytes of ``plan``."""
        return self._digest(canonical_plan_bytes(plan))

    def verify(self, payload: bytes, signature: str) -> bool:
        """Whether ``signature`` is the lowercase hex HMAC-SHA256 of ``payload`` (constant-time
        comparison). A malformed signature is not valid; a ``payload`` that is not bytes raises."""
        if not isinstance(payload, (bytes, bytearray)):
            raise PlanIntegrityError(
                f"the payload must be bytes, got {type(payload).__name__}"
            )
        if (
            not isinstance(signature, str)
            or len(signature) != _SIGNATURE_LENGTH
            or not _HEX_DIGITS.issuperset(signature)
        ):
            return False
        expected = self._digest(bytes(payload))
        return hmac.compare_digest(expected.encode("ascii"), signature.encode("ascii"))


# ---------------------------------------------------------------------------------------
# Load-time check
# ---------------------------------------------------------------------------------------


def verify_plan(
    plan: CarePlan,
    verifier: PlanVerifier | None,
    *,
    registry_version: str | None = None,
    require_signature: bool = False,
) -> None:
    """Check a distributed plan; return ``None`` or raise ``PlanIntegrityError``.

    * ``registry_version``, if given, must equal ``plan.registry_version`` exactly (no range);
    * an unsigned plan (``signature is None``) is accepted unless ``require_signature`` is true;
    * a signed plan needs a ``verifier`` (never accepted silently) and its signature must verify
      over ``canonical_plan_bytes(plan)``.

    The rule that ``plan_version`` never decreases is enforced by the monitor, not here.
    """
    if not isinstance(require_signature, bool):
        raise PlanIntegrityError(
            f"require_signature must be a bool, got {show(require_signature)}"
        )
    if not isinstance(plan, CarePlan):
        raise PlanIntegrityError(f"expected a CarePlan, got {show(plan)}")
    if registry_version is not None:
        if not isinstance(registry_version, str):
            raise PlanIntegrityError(
                f"registry_version must be a str, got {show(registry_version)}"
            )
        if plan.registry_version != registry_version:
            raise PlanIntegrityError(
                f"the plan pins registry_version {show(plan.registry_version)} but the loaded "
                f"registry is {show(registry_version)}"
            )
    signature = plan.signature
    if signature is None:
        if require_signature:
            raise PlanIntegrityError("the plan is unsigned but a signature is required")
        return
    if not isinstance(signature, str):
        raise PlanIntegrityError(f"the signature must be a str, got {show(signature)}")
    if verifier is None:
        raise PlanIntegrityError(
            "the plan is signed but no verifier is configured: a signed plan is never "
            "accepted unchecked"
        )
    if not callable(getattr(verifier, "verify", None)):
        raise PlanIntegrityError(f"the verifier has no verify method: {show(verifier)}")
    payload = canonical_plan_bytes(plan)
    try:
        valid = verifier.verify(payload, signature)
    except PlanIntegrityError:
        raise
    except Exception as exc:
        raise PlanIntegrityError(f"the verifier failed: {exc}") from exc
    if valid is not True:
        raise PlanIntegrityError("the plan signature does not verify")
