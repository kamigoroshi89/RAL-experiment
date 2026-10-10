"""Hand-written fixtures of the baseline harness tests (WS06-T01).

FIXTURE-ONLY. Every number is arithmetic chosen so that results can be computed by hand: band 110 to 140
mmHg, hold threshold 100 mmHg and dose limit 2 are the illustrative numbers of analisi section 4.1
("illustrative, unverified"), and the 30 min window is chosen for these tests only. None of it is a clinical
value. Signal names in the harness tests are opaque strings: the harness never looks at what a signal means.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from ralmon.attribution import Detection, EvidenceVector
from ralmon.baselines.base import BaselineBase, TimingConfig
from ralmon.benchmark import (
    BenchmarkDay,
    GroundTruthEvent,
    InjectedClass,
    LatentDay,
    ObservedDay,
)
from ralmon.signals import Event, EventKind, Sample
from ralmon.spec import CarePlan, PhysioBounds, RegistryEntry, TemplateInstance
from ralmon.spec.templates import TemplateId

STEP_MS = 60_000


def make_sample(
    signal: str = "s",
    t_device_ms: int = 0,
    t_rx_ms: int | None = None,
    value: float = 1.0,
    seq: int | None = None,
    quality: float | None = None,
) -> Sample:
    rx = t_device_ms if t_rx_ms is None else t_rx_ms
    return Sample(signal, t_device_ms, rx, value, seq, quality)


def make_event(
    kind: EventKind = EventKind.MEASUREMENT,
    t_device_ms: int = 0,
    t_rx_ms: int | None = None,
    source: str = "dev",
    payload: Mapping[str, float | int | str | bool] | None = None,
    seq: int | None = None,
) -> Event:
    rx = t_device_ms if t_rx_ms is None else t_rx_ms
    return Event(kind, t_device_ms, rx, source, dict(payload or {}), seq)


def make_observed_day(
    samples: Sequence[Sample] = (),
    events: Sequence[Event] = (),
    *,
    patient_id: str = "p1",
    day_index: int = 0,
    seed: int = 0,
    care_plan_id: str = "plan-1",
) -> ObservedDay:
    return ObservedDay(
        patient_id, day_index, seed, tuple(samples), tuple(events), care_plan_id
    )


def make_ground_truth() -> tuple[GroundTruthEvent, ...]:
    return (
        GroundTruthEvent(
            InjectedClass.C1, "fixture_event", 1_000, None, True, "range", None
        ),
    )


def make_benchmark_day(
    samples: Sequence[Sample] = (),
    events: Sequence[Event] = (),
    *,
    patient_id: str = "p1",
    day_index: int = 0,
    ground_truth: Sequence[GroundTruthEvent] | None = None,
) -> BenchmarkDay:
    observed = make_observed_day(
        samples, events, patient_id=patient_id, day_index=day_index
    )
    latent = LatentDay(
        patient_id, day_index, 0, (make_sample("latent_s", 0, 0, 9.0),), ()
    )
    truth = make_ground_truth() if ground_truth is None else tuple(ground_truth)
    return BenchmarkDay(observed, latent, truth)


def make_care_plan(
    instances: Sequence[TemplateInstance] = (),
    schedule: Sequence[int] = (),
    *,
    patient_id: str = "p1",
) -> CarePlan:
    return CarePlan(
        "plan-1",
        "pathway-1",
        patient_id,
        "0.0.0",
        tuple(instances),
        tuple(schedule),
        1,
        None,
    )


def make_instance(
    template: TemplateId,
    instance_key: str,
    params: Mapping[str, float],
    anchor_ms: int | None = None,
) -> TemplateInstance:
    return TemplateInstance(template, instance_key, dict(params), anchor_ms)


class StubRegistry:
    """A test-local ``ParameterRegistry``; names are entry names of the registry files (test 21)."""

    ENTRIES: Mapping[str, float] = {
        "bp_band_low": 110.0,  # illustrative, unverified (analisi 4.1)
        "bp_band_high": 140.0,  # illustrative, unverified (analisi 4.1)
        "bp_hold_threshold": 100.0,  # illustrative, unverified (analisi 4.1)
        "dose_max_24h": 2.0,  # illustrative, unverified (analisi 4.1)
        "delta2": 30 * 60_000.0,  # window chosen for these tests only
    }
    BOUNDS: Mapping[str, tuple[str, str]] = {"bp": ("bound_bp_lower", "bound_bp_upper")}
    BOUND_VALUES: Mapping[str, float] = {
        "bound_bp_lower": 50.0,
        "bound_bp_upper": 250.0,
    }

    def get(self, name: str) -> RegistryEntry:
        if name not in self.ENTRIES:
            raise KeyError(name)
        return RegistryEntry(
            name,
            self.ENTRIES[name],
            "1",
            "illustrative, unverified",
            "FIXTURE-ONLY: tests/baselines/conftest.py",
            None,
        )

    def bounds(self, signal: str) -> PhysioBounds:
        low, high = self.BOUNDS[signal]
        return PhysioBounds(signal, self.BOUND_VALUES[low], self.BOUND_VALUES[high])

    def version(self) -> str:
        return "0.0.0"

    def names(self) -> frozenset[str]:
        """Every registry name this stub can answer (entries and the two bound entries)."""
        names = set(self.ENTRIES)
        for low, high in self.BOUNDS.values():
            names.update((low, high))
        return frozenset(names)


@pytest.fixture
def stub_registry() -> StubRegistry:
    return StubRegistry()


class RecordingBaseline(BaselineBase):
    """A minimal subclass: records its `_fit` calls and emits what the test tells it to."""

    name = "STUB"

    def __init__(
        self,
        timing: TimingConfig | None = None,
        *,
        output: Sequence[Detection] = (),
        **kwargs: Any,
    ) -> None:
        super().__init__(timing or TimingConfig(STEP_MS, 0, 0), **kwargs)
        self.output = tuple(output)
        self.fit_calls: list[tuple[tuple[Any, ...], tuple[Any, ...]]] = []
        self.state: Any = None

    def _fit(self, train: Any, calib: Any) -> None:
        self.fit_calls.append((tuple(train), tuple(calib)))
        self.state = (len(train), len(calib))

    def _run(self, day: ObservedDay, plan: CarePlan) -> Sequence[Detection]:
        return self.output


def evidence_mapping() -> Mapping[str, EvidenceVector]:
    """A non-empty mapping standing for evidence; the harness must drop it unread."""
    return {"k": object()}  # type: ignore[dict-item]
