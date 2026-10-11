"""Fixtures of the attribution tests (WS05-T07): the worked cases, the test registry and builders.

* ``worked_cases.json`` is the copy of the worked cases W-01 to W-15 of ``docs/models/attribution-rule.md``
  made by ``build_worked_cases.py`` (each case keeps the id of the document). Float and string readings are
  given by their relation to a registry threshold; ``build_vector`` resolves them with the FIXTURE-ONLY
  thresholds of ``registry_attribution.yaml``.
* ``registry_attribution.yaml`` is the F0 fixture registry plus the parameters that the evidence and rule
  documents request from the registry and that the real registry does not carry (all FIXTURE-ONLY).

Nothing here is a clinical value.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

from ralmon.monitor import RobustnessInterval, VerdictRecord, VerdictState
from ralmon.spec import LoadedRegistry, Rho, RhoKind, TemplateId, load_registry

HERE = Path(__file__).resolve().parent
REGISTRY_PATH = HERE / "registry_attribution.yaml"
CASES_PATH = HERE / "worked_cases.json"

STEP_MS = 60_000
DAY_MS = 86_400_000

#: The twenty-four fields of the EvidenceVector 0.2.0 in contract order (``docs/plan/02-interfaces.md#evidencevector``).
CONTRACT_PATHS: tuple[str, ...] = (
    "provenance.violated_template",
    "provenance.template_kind",
    "system.node_lifecycle",
    "system.diagnostics_ok",
    "system.liveliness_ok",
    "system.qos_deadline_missed",
    "system.ble_link_quality",
    "system.battery_low",
    "system.nav_task_failed",
    "system.manip_task_failed",
    "system.seq_gap",
    "signal_quality.ecg_sqi",
    "signal_quality.ppg_sqi",
    "signal_quality.cuff_error_code",
    "signal_quality.cuff_value_repeated",
    "cross_device.pulse_vs_ecg_hr_diff",
    "witness.robot_present",
    "witness.identity_confirmed",
    "witness.intake_observed",
    "crypto_temporal.authenticated",
    "crypto_temporal.seq_repeat",
    "crypto_temporal.timestamp_implausible",
    "dispenser.interval_since_previous_ms",
    "dispenser.content_change",
)
NON_PROVENANCE_PATHS: tuple[str, ...] = CONTRACT_PATHS[2:]

KIND_OF = {
    "range": "CARE_PLAN",
    "sched": "CARE_PLAN",
    "hold": "CARE_PLAN",
    "count": "CARE_PLAN",
    "resp": "CARE_PLAN",
    "sys": "SYSTEM",
    "int": "INTEGRITY",
}


def load_fixture_registry() -> LoadedRegistry:
    return load_registry(REGISTRY_PATH, step_ms=STEP_MS, allow_fixture_only=True)


@lru_cache(maxsize=1)
def _cases() -> tuple[dict[str, Any], ...]:
    return tuple(json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"])


def worked_cases() -> list[dict[str, Any]]:
    return [dict(case) for case in _cases()]


def worked_case(case_id: str) -> dict[str, Any]:
    for case in _cases():
        if case["id"] == case_id:
            return dict(case)
    raise KeyError(case_id)


def case_ids() -> list[str]:
    return [case["id"] for case in _cases()]


def resolve_value(value: Any, registry: LoadedRegistry) -> Any:
    """A value cell of a worked case: literal, or a relation to a registry threshold."""
    if not isinstance(value, dict) or "rel" not in value:
        return value
    threshold = registry.get(value["param"]).value
    rel = value["rel"]
    if rel == "at_or_above":
        return threshold  # the boundary itself is a denied reading
    if rel == "within":
        return threshold
    if rel == "below":
        return threshold / 2.0
    if rel == "above":
        return threshold * 2.0
    if rel == "between_floor_and_one":
        return (threshold + 1.0) / 2.0
    raise ValueError(f"unknown relation {rel!r}")


def build_vector(case: Mapping[str, Any], registry: LoadedRegistry) -> Any:
    """The EvidenceVector of a worked case: the listed fields, every other field None."""
    from ralmon.attribution import (
        CrossDeviceEvidence,
        CryptoTemporalEvidence,
        DispenserEvidence,
        EmbodiedWitnessEvidence,
        EvidenceVector,
        ProvenanceEvidence,
        SignalQualityEvidence,
        SystemHealthEvidence,
    )
    from ralmon.spec import TemplateKind

    fields = {
        path: resolve_value(value, registry) for path, value in case["fields"].items()
    }

    def part(group: str, names: tuple[str, ...]) -> dict[str, Any]:
        return {name: fields.get(f"{group}.{name}") for name in names}

    system = part(
        "system",
        (
            "node_lifecycle",
            "diagnostics_ok",
            "liveliness_ok",
            "qos_deadline_missed",
            "ble_link_quality",
            "battery_low",
            "nav_task_failed",
            "manip_task_failed",
            "seq_gap",
        ),
    )
    return EvidenceVector(
        provenance=ProvenanceEvidence(
            violated_template=TemplateId(case["template"]),
            template_kind=TemplateKind[KIND_OF[case["template"]]],
        ),
        system=SystemHealthEvidence(**system),
        signal_quality=SignalQualityEvidence(
            **part(
                "signal_quality",
                ("ecg_sqi", "ppg_sqi", "cuff_error_code", "cuff_value_repeated"),
            )
        ),
        cross_device=CrossDeviceEvidence(
            **part("cross_device", ("pulse_vs_ecg_hr_diff",))
        ),
        witness=EmbodiedWitnessEvidence(
            **part(
                "witness", ("robot_present", "identity_confirmed", "intake_observed")
            )
        ),
        crypto_temporal=CryptoTemporalEvidence(
            **part(
                "crypto_temporal",
                ("authenticated", "seq_repeat", "timestamp_implausible"),
            )
        ),
        dispenser=DispenserEvidence(
            **part("dispenser", ("interval_since_previous_ms", "content_change"))
        ),
    )


def vector(template: str, fields: Mapping[str, Any], registry: LoadedRegistry) -> Any:
    """An EvidenceVector with the listed fields (a worked-case style mapping), every other field None."""
    return build_vector({"template": template, "fields": dict(fields)}, registry)


def registry_variant(
    tmp_path: Path,
    *,
    drop: tuple[str, ...] = (),
    override: Mapping[str, float] | None = None,
) -> LoadedRegistry:
    """The test registry without some entries and/or with other values (a copy written under ``tmp_path``)."""
    import yaml

    document = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    entries = [e for e in document["entries"] if e["name"] not in drop]
    for entry in entries:
        if override and entry["name"] in override:
            entry["value"] = float(override[entry["name"]])
    document["entries"] = entries
    target = tmp_path / "registry_variant.yaml"
    target.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return load_registry(target, step_ms=STEP_MS, allow_fixture_only=True)


def hms(hh: int, mm: int, ss: int = 0) -> int:
    """``hh:mm:ss`` of a fixture day as milliseconds (ADR-017)."""
    return ((60 * hh + mm) * 60 + ss) * 1000


def measured_rho(value: float = 0.9772) -> Rho:
    return Rho(
        value=value,
        kind=RhoKind.MEASURED,
        guarantee="FIXTURE-ONLY guarantee text of a measured confidence",
        alpha=None,
        assumptions=("FIXTURE-ONLY assumption",),
    )


def deterministic_rho() -> Rho:
    return Rho(
        value=1.0,
        kind=RhoKind.DETERMINISTIC,
        guarantee="FIXTURE-ONLY guarantee text of a deterministic confidence",
        alpha=None,
        assumptions=("FIXTURE-ONLY assumption",),
    )


def predicted_rho(value: float = 0.9, alpha: float = 0.2) -> Rho:
    return Rho(
        value=value,
        kind=RhoKind.PREDICTED,
        guarantee="marginal over patient episodes under exchangeability",
        alpha=alpha,
        assumptions=("exchangeability of patient episodes",),
    )


def rho_variants() -> tuple[Rho, Rho, Rho]:
    """A measured, a deterministic and a predicted confidence (FIXTURE-ONLY strings)."""
    return (measured_rho(), deterministic_rho(), predicted_rho())


def make_record(
    template: str | TemplateId = "range",
    *,
    key: str | None = None,
    state: VerdictState = VerdictState.VIOLATED,
    decided_at_ms: int | None = None,
    t_eval_ms: int | None = None,
    hi: float = -12.0,
    lo: float | None = None,
    sigma_norm: tuple[float, float] | None = None,
    rho: Rho | None = None,
    pending_until_ms: int | None = None,
    guard_failed: str | None = None,
    subformula_path: str | None = None,
    predicted_sigma_norm: float | None = None,
) -> VerdictRecord:
    """A VerdictRecord of the observed monitor with fixture numbers (the F0 scale of ``range`` is 20)."""
    tid = TemplateId(template)
    decided = decided_at_ms if decided_at_ms is not None else hms(9, 5)
    if state is VerdictState.PREDICTED_VIOLATION:
        decided_final: int | None = None
        evaluated = t_eval_ms if t_eval_ms is not None else decided
    else:
        decided_final = decided
        evaluated = t_eval_ms if t_eval_ms is not None else decided
    lower = hi if lo is None else lo
    norm = (
        sigma_norm
        if sigma_norm is not None
        else (max(-1.0, lower / 20.0), max(-1.0, hi / 20.0))
    )
    return VerdictRecord(
        instance_key=key if key is not None else f"{tid.value}@{decided}",
        template=tid,
        t_eval_ms=evaluated,
        state=state,
        sigma_interval=RobustnessInterval(lo=lower, hi=hi),
        sigma_norm_interval=norm,
        rho=rho if rho is not None else measured_rho(),
        decided_at_ms=decided_final,
        pending_until_ms=pending_until_ms,
        guard_failed=guard_failed,
        subformula_path=subformula_path,
        predicted_sigma_norm=predicted_sigma_norm,
    )
