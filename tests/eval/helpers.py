"""Helpers of the WS08-T01 tests. ILLUSTRATIVE, UNVERIFIED, FIXTURE-ONLY: arithmetic test values, no clinical meaning."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from ralmon.attribution import Alert, AttributedCause, Detection, Explanation
from ralmon.benchmark import (
    BenchmarkDay,
    GroundTruthEvent,
    InjectedClass,
    LatentDay,
    ObservedDay,
)
from ralmon.monitor import VerdictState
from ralmon.spec import Rho, RhoKind, TemplateId

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "eval"
MINI = FIXTURES / "mini_benchmark"
SMOKE = FIXTURES / "smoke.yaml"
REGISTRY = FIXTURES / "registry.yaml"

T = 86_400_000
C1, C2, C3 = (
    AttributedCause.C1_CLINICAL,
    AttributedCause.C2_SYSTEM,
    AttributedCause.C3_INTEGRITY,
)
UND = AttributedCause.UNDETERMINED


def ms(h: int, m: int = 0) -> int:
    return (60 * h + m) * 60_000


def gt(
    cls: str,
    onset: int,
    end: int | None = None,
    subtype: str = "fx",
    template: str | None = None,
) -> GroundTruthEvent:
    return GroundTruthEvent(
        InjectedClass(cls), subtype, onset, end, cls != "C1", template, None
    )


def det(t: int, label: AttributedCause | None = None, score: float = 1.0) -> Detection:
    return Detection(t, label, score)


def alert(
    t: int,
    kappa: AttributedCause,
    *,
    key: str,
    verdict: VerdictState = VerdictState.VIOLATED,
    tau: TemplateId = TemplateId.RANGE,
) -> Alert:
    """A hand-built alert (the fields that the metrics read: t_ms, label, xi.instance_key, verdict)."""
    xi = Explanation(tau, key, "", {}, (), "")
    rho = (
        Rho(
            0.5,
            RhoKind.PREDICTED,
            "marginal over patient episodes under exchangeability",
            0.5,
            (),
        )
        if verdict is VerdictState.PREDICTED_VIOLATION
        else None
    )
    return Alert(t, kappa, 1.0, tau, kappa, -0.5, rho, xi, verdict, 1, (), None)


def benchmark_day(
    events: Sequence[GroundTruthEvent], patient: str = "p", index: int = 0
) -> BenchmarkDay:
    return BenchmarkDay(
        ObservedDay(patient, index, 0, (), (), "plan"),
        LatentDay(patient, index, 0, (), ()),
        tuple(events),
    )


def smoke_document() -> dict[str, Any]:
    """The smoke YAML as a dictionary with absolute paths (so that a copy can live in a temporary directory)."""
    doc = yaml.safe_load(SMOKE.read_text(encoding="utf-8"))
    doc["benchmark_manifest"] = str(MINI)
    doc["run_options"]["registry"] = str(REGISTRY)
    return doc  # type: ignore[no-any-return]


def write_config(path: Path, doc: Mapping[str, Any]) -> Path:
    path.write_text(yaml.safe_dump(dict(doc), sort_keys=True), encoding="utf-8")
    return path
