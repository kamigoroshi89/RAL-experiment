"""The hierarchical attribution rule (``AttributionRule``, ``HierarchicalRule``).

Specification: docs/models/attribution-rule.md (WS02-T04), which this module implements without adding to it. The
rule is a total function of the template and the reading classes of the eighteen non-provenance fields of the
``EvidenceVector``; it reads nothing else (invariant I1: neither rho, nor the interval, nor the verdict state, nor a
time of the record). The hierarchy of ADR-010 and of the four steps of ``#attribution``, as eight rows of the decision
table (section Decision table), tried in order:

1. ``crypto_temporal.authenticated`` asserted (IE-1) gives C3;
2. a repeated sequence value with a complete delivery ratio (IE-2) gives C3;
3. a cross-device incoherence with both signal-quality fields denied (IE-3) gives C3;
4. any system evidence (SE-1 to SE-9) gives C2;
5. the exclusion set of the template available and denied gives C1 (``range``, ``sched``, ``hold``, ``resp``);
6. evidence that no rule accepts (RS-1 to RS-4) gives UNDETERMINED, reason ``conflict``;
7. a system or integrity template with nothing asserted outside provenance gives UNDETERMINED, reason
   ``provenance_only``;
8. otherwise UNDETERMINED, reason ``insufficient``.

``None`` is never a negative reading: a predicate that needs a denied reading is not satisfied by ``None``. A reading
that is out of its domain (a delivery ratio outside the closed unit interval, a NaN, a negative cross-device
difference, a value of the wrong type) is a defect of the extractor and is read as unavailable and logged (AD-18),
never raised: the alert path does not raise on evidence. The four thresholds are read from the registry at
construction and have no default (H-1): ``hr_coherence_tolerance``, ``ecg_sqi_floor``, ``ppg_sqi_floor`` and
``ble_link_quality_floor`` (which must not exceed 1.0, H-2).

``decide`` returns the decision record <kappa, row, reason, decisive fields, unavailable fields> (OP-AR-15); the
``AttributionRule`` Protocol of the contract has only ``attribute``.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from typing import Final, Protocol

from ralmon.attribution.alert import AttributedCause
from ralmon.attribution.evidence import (
    EVIDENCE_PATHS,
    NON_PROVENANCE_PATHS,
    EvidenceVector,
    get_evidence,
    template_kind_of,
)
from ralmon.monitor import VerdictRecord
from ralmon.spec import ParameterRegistry, RegistryError, TemplateId, TemplateKind

__all__ = [
    "AbstentionReason",
    "AttributionRule",
    "Decision",
    "HierarchicalRule",
    "predicted_decision",
]

log = logging.getLogger(__name__)

#: The rows of the decision table in precedence order (section Decision table); a row is identified by its number.
ROWS: Final = (
    "authentication failed",
    "repeated sequence value",
    "cross-device incoherence",
    "system evidence",
    "exclusion set satisfied",
    "evidence that no rule accepts",
    "provenance only",
    "insufficient evidence",
)
ROW_INSUFFICIENT: Final = len(ROWS)


class AttributionRule(Protocol):
    def attribute(
        self, violated: VerdictRecord, evidence: EvidenceVector
    ) -> AttributedCause: ...


class AbstentionReason(str, Enum):
    """The three reasons of an UNDETERMINED result (section Abstention): rows 8, 6 and 7."""

    INSUFFICIENT = "insufficient"
    CONFLICT = "conflict"
    PROVENANCE_ONLY = "provenance_only"


@dataclass(frozen=True, slots=True)
class Decision:
    """The decision record of the table: the attributed cause, the row that decided and why.

    ``evidence_used`` lists the decisive fields in precedence order (AD-17); ``missing`` lists, for an
    UNDETERMINED result of reason ``insufficient``, the fields of the exclusion set (or of the qualifier) that were
    unavailable, in contract order.
    """

    kappa: AttributedCause
    row: int | None  # 1 to 8; None for a predicted alert (the rule is not evaluated)
    reason: AbstentionReason | None
    evidence_used: tuple[str, ...]
    missing: tuple[str, ...]


def predicted_decision() -> Decision:
    """Kappa of a PREDICTED_VIOLATION alert: UNDETERMINED by definition, the rule is not evaluated (CP13)."""
    return Decision(AttributedCause.UNDETERMINED, None, None, (), ())


# ---- reading classes -----------------------------------------------------------------------------------------
# A asserted, D denied, U unavailable; K a deliberate transition (lifecycle); F a complete delivery ratio and G a
# ratio below one but not below the floor (link quality).
A: Final = "A"
D: Final = "D"
U: Final = "U"
K: Final = "K"
F: Final = "F"
G: Final = "G"

LIFE: Final = "system.node_lifecycle"
DIAG: Final = "system.diagnostics_ok"
LIVE: Final = "system.liveliness_ok"
QOS: Final = "system.qos_deadline_missed"
BLE: Final = "system.ble_link_quality"
NAV: Final = "system.nav_task_failed"
MANIP: Final = "system.manip_task_failed"
ECG: Final = "signal_quality.ecg_sqi"
PPG: Final = "signal_quality.ppg_sqi"
CUFF: Final = "signal_quality.cuff_error_code"
DIFF: Final = "cross_device.pulse_vs_ecg_hr_diff"
IDENT: Final = "witness.identity_confirmed"
INTAKE: Final = "witness.intake_observed"
AUTH: Final = "crypto_temporal.authenticated"
SEQ: Final = "crypto_temporal.seq_gap_or_replay"
TIME: Final = "crypto_temporal.timestamp_implausible"

_CP = (LIFE, DIAG, LIVE, QOS, BLE)  # the five fields every template reads
_REST = (AUTH, SEQ, TIME)

# Relevance map (section Relevance map): the fields that the table reads for each template. A field outside the set
# is context or "-" and is read as unavailable whatever the vector holds.
_READS: Final[dict[TemplateId, frozenset[str]]] = {
    TemplateId.RANGE: frozenset({*_CP, CUFF, DIFF, ECG, PPG, *_REST}),
    TemplateId.SCHED: frozenset({*_CP, NAV, MANIP, CUFF, *_REST}),
    TemplateId.HOLD: frozenset({*_CP, NAV, MANIP, CUFF, DIFF, ECG, PPG, *_REST}),
    TemplateId.COUNT: frozenset({*_CP, *_REST}),
    TemplateId.RESP: frozenset(
        {*_CP, NAV, MANIP, CUFF, DIFF, ECG, PPG, IDENT, INTAKE, *_REST}
    ),
    TemplateId.SYS: frozenset({*_CP, CUFF, DIFF, ECG, PPG, *_REST}),
    TemplateId.INT: frozenset({*_CP, NAV, MANIP, *_REST}),
}
# The exclusion set EX(t) of C1 (section C1 exclusion conditions): the cuff-path conditions EX-CP plus, per template,
# the readings that must be available and denied. ``authenticated`` and the backing of ``resp`` are handled apart.
_EX_CP: Final = (LIFE, DIAG, LIVE, QOS, BLE, SEQ, TIME)
_EX: Final[dict[TemplateId, tuple[str, ...]]] = {
    TemplateId.RANGE: (*_EX_CP, CUFF, DIFF),
    TemplateId.SCHED: (*_EX_CP, NAV, MANIP, CUFF),
    TemplateId.HOLD: (*_EX_CP, NAV, MANIP, CUFF, DIFF),
    TemplateId.RESP: (*_EX_CP, NAV, MANIP, CUFF, DIFF),
}
_ORDER: Final[dict[str, int]] = {p: i for i, p in enumerate(EVIDENCE_PATHS)}
_QUALIFIED = (
    TemplateId.RANGE,
    TemplateId.HOLD,
    TemplateId.RESP,
    TemplateId.SYS,
)  # IE-3, SE-9, AM-1
_TASKS = (
    TemplateId.SCHED,
    TemplateId.HOLD,
    TemplateId.RESP,
    TemplateId.INT,
)  # SE-6, SE-7
_CUFF_CODE = (
    TemplateId.RANGE,
    TemplateId.SCHED,
    TemplateId.HOLD,
    TemplateId.RESP,
    TemplateId.SYS,
)  # SE-8


def _ordered(paths: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted(set(paths), key=_ORDER.__getitem__))


def _is_real(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


class HierarchicalRule:
    """The default rule of ``#attribution`` (analisi 4.5): integrity, system, coherent channels, abstention."""

    def __init__(self, registry: ParameterRegistry) -> None:
        def threshold(name: str) -> float:
            value = float(registry.get(name).value)
            if not math.isfinite(value):
                raise RegistryError(f"{name} must be finite, got {value!r}")
            return value

        self.hr_coherence_tolerance = threshold("hr_coherence_tolerance")
        self.ecg_sqi_floor = threshold("ecg_sqi_floor")
        self.ppg_sqi_floor = threshold("ppg_sqi_floor")
        self.ble_link_quality_floor = threshold("ble_link_quality_floor")
        if not 0.0 <= self.ble_link_quality_floor <= 1.0:
            raise RegistryError(
                "ble_link_quality_floor must lie in [0, 1], a delivery ratio floor above 1.0 is "
                f"meaningless (H-2), got {self.ble_link_quality_floor!r}"
            )

    # ---- the Protocol -------------------------------------------------------------------------------------

    def attribute(
        self, violated: VerdictRecord, evidence: EvidenceVector
    ) -> AttributedCause:
        return self.decide(violated, evidence).kappa

    # ---- readings -----------------------------------------------------------------------------------------

    def _readings(
        self, evidence: EvidenceVector, template: TemplateId
    ) -> dict[str, str]:
        reads = _READS[template]
        invalid: list[str] = []
        out: dict[str, str] = {}
        for path in NON_PROVENANCE_PATHS:
            if path not in reads:
                out[path] = U
                continue
            value = get_evidence(evidence, path)
            code, bad = self._classify(path, value)
            out[path] = code
            if bad:
                invalid.append(path)
        if invalid:
            log.warning(
                "attribution: out-of-domain readings read as unavailable: %s",
                ", ".join(invalid),
            )
        return out

    def _classify(self, path: str, value: object) -> tuple[str, bool]:
        """The reading class of one field and whether the value was out of domain (read as U)."""
        if value is None:
            return U, False
        if path == LIFE:
            if not isinstance(value, dict) and not hasattr(value, "values"):
                return U, True
            entries = list(value.values())
            if not entries:
                return U, False  # an empty mapping is None (H-3)
            if not all(isinstance(e, str) for e in entries):
                return U, True
            adverse = [
                e for e in entries if e != "active" and not e.endswith("+commanded")
            ]
            if adverse:
                return A, False
            if any(e.endswith("+commanded") for e in entries):
                return K, False
            return D, False
        if path == BLE:
            if not _is_real(value) or not math.isfinite(float(value)):  # type: ignore[arg-type]
                return U, True
            ratio = float(value)  # type: ignore[arg-type]
            if ratio < 0.0 or ratio > 1.0:
                return U, True
            if ratio < self.ble_link_quality_floor:
                return A, False
            return (F, False) if ratio == 1.0 else (G, False)
        if path in (ECG, PPG):
            if not _is_real(value) or math.isnan(float(value)):  # type: ignore[arg-type]
                return U, True
            floor = self.ecg_sqi_floor if path == ECG else self.ppg_sqi_floor
            return (A if float(value) < floor else D), False  # type: ignore[arg-type]
        if path == CUFF:
            if not isinstance(value, str):
                return U, True
            return (A if value else D), False
        if path == DIFF:
            if not _is_real(value) or math.isnan(float(value)) or float(value) < 0.0:  # type: ignore[arg-type]
                return U, True
            return (A if float(value) > self.hr_coherence_tolerance else D), False  # type: ignore[arg-type]
        if not isinstance(value, bool):
            return U, True
        adverse_false = path in (DIAG, LIVE, IDENT, INTAKE, AUTH)
        asserted = (value is False) if adverse_false else (value is True)
        return (A if asserted else D), False

    # ---- the decision table -------------------------------------------------------------------------------

    def decide(self, violated: VerdictRecord, evidence: EvidenceVector) -> Decision:
        """Apply the decision table to the vector (``violated`` is not read: invariant I1)."""
        template = evidence.provenance.violated_template
        kind = evidence.provenance.template_kind
        if (
            not isinstance(template, TemplateId)
            or not isinstance(kind, TemplateKind)
            or template_kind_of(template) is not kind
        ):
            log.warning(
                "attribution: provenance.template_kind %r does not match provenance.violated_template %r; "
                "the evidence is not evaluated",
                kind,
                template,
            )
            return Decision(
                AttributedCause.UNDETERMINED,
                ROW_INSUFFICIENT,
                AbstentionReason.INSUFFICIENT,
                (),
                (),
            )
        r = self._readings(evidence, template)

        # --- integrity evidence (rows 1 to 3)
        ie1 = r[AUTH] == A
        ie2 = r[SEQ] == A and r[BLE] == F
        ie3 = template in _QUALIFIED and r[DIFF] == A and r[ECG] == D and r[PPG] == D
        ie2_fields = (BLE, SEQ) if ie2 else ()
        ie3_fields = (ECG, PPG, DIFF) if ie3 else ()
        if ie1:
            return self._definite(
                AttributedCause.C3_INTEGRITY, 1, (AUTH, *ie2_fields, *ie3_fields)
            )
        if ie2:
            return self._definite(
                AttributedCause.C3_INTEGRITY, 2, (*ie2_fields, *ie3_fields)
            )
        if ie3:
            return self._definite(AttributedCause.C3_INTEGRITY, 3, ie3_fields)

        # --- system evidence (row 4), in the order SE-1 to SE-9
        se: list[str] = []
        for path in (LIFE, DIAG, LIVE, QOS, BLE):
            if r[path] == A:
                se.append(path)
        if template in _TASKS:
            se.extend(p for p in (NAV, MANIP) if r[p] == A)
        if template in _CUFF_CODE and r[CUFF] == A:
            se.append(CUFF)
        if template in _QUALIFIED and r[DIFF] == A and (r[ECG] == A or r[PPG] == A):
            se.extend(p for p in (ECG, PPG) if r[p] == A)
            se.append(DIFF)
        if se:
            return self._definite(AttributedCause.C2_SYSTEM, 4, se)

        # --- C1 by exclusion (row 5)
        if template in _EX:
            required = _EX[template]
            denied_ok = all(
                r[p] == (F if p == BLE else D) for p in required
            )  # BLE must be complete
            backing: tuple[str, ...] | None = ()
            if template is TemplateId.RESP:
                if r[AUTH] == D:
                    backing = (AUTH,)
                elif r[AUTH] == U and r[IDENT] == D and r[INTAKE] == D:
                    backing = (IDENT, INTAKE)
                else:
                    backing = None
            elif r[AUTH] == D:
                backing = (AUTH,)
            if denied_ok and backing is not None:
                return self._definite(
                    AttributedCause.C1_CLINICAL, 5, (*required, *backing)
                )

        # --- evidence that no rule accepts (row 6)
        rs: list[str] = []
        if r[LIFE] == K:
            rs.append(LIFE)
        if r[BLE] == G:
            rs.append(BLE)
            if r[SEQ] == A:
                rs.append(SEQ)
        if r[TIME] == A:
            rs.append(TIME)
        if template is TemplateId.RESP and r[AUTH] == U:
            backed = r[IDENT] == D and r[INTAKE] == D
            if not backed:
                rs.extend(p for p in (IDENT, INTAKE) if r[p] == A)
        if rs:
            return Decision(
                AttributedCause.UNDETERMINED,
                6,
                AbstentionReason.CONFLICT,
                _ordered(rs),
                (),
            )

        # --- abstention without evidence (rows 7 and 8)
        am1 = (
            template in _QUALIFIED
            and r[DIFF] == A
            and r[ECG] != A
            and r[PPG] != A
            and not (r[ECG] == D and r[PPG] == D)
        )
        am2 = r[SEQ] == A and r[BLE] == U
        if kind in (TemplateKind.SYSTEM, TemplateKind.INTEGRITY) and not (am1 or am2):
            return Decision(
                AttributedCause.UNDETERMINED,
                7,
                AbstentionReason.PROVENANCE_ONLY,
                (),
                (),
            )
        return Decision(
            AttributedCause.UNDETERMINED,
            ROW_INSUFFICIENT,
            AbstentionReason.INSUFFICIENT,
            (),
            self._missing(template, r, am1, am2),
        )

    @staticmethod
    def _definite(kappa: AttributedCause, row: int, fields: Iterable[str]) -> Decision:
        paths = tuple(fields)
        # rows 1 to 3 list their fields in the order of the table; rows 4 and 5 in contract order (a sorted list)
        if row >= 4:
            paths = _ordered(paths)
        return Decision(kappa, row, None, paths, ())

    @staticmethod
    def _missing(
        template: TemplateId, r: dict[str, str], am1: bool, am2: bool
    ) -> tuple[str, ...]:
        """The unavailable fields that stop the exclusion (or resolve an ambiguity), in contract order."""
        missing: set[str] = set()
        if template in _EX:
            missing.update(p for p in _EX[template] if r[p] == U)
            if (
                template is TemplateId.RESP
                and r[AUTH] == U
                and not (r[IDENT] == D and r[INTAKE] == D)
            ):
                missing.update(p for p in (IDENT, INTAKE, AUTH) if r[p] == U)
        if am1:
            missing.update(p for p in (ECG, PPG) if r[p] == U)
        if am2:
            missing.add(BLE)
        return _ordered(missing)
