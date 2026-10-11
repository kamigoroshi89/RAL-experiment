"""Builders for the extractor tests of WS05-T07: trace items, the device profile and records.

Every number is fixture arithmetic (the F0 registry and the FIXTURE-ONLY rows of ``registry_attribution.yaml``); the
values of the samples carry no clinical meaning. Times are the ``hh:mm:ss`` labels of EX-1 to EX-12 of
``docs/models/evidence-channels.md`` as integer milliseconds.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ralmon.signals import Event, EventKind, Sample, SignalId
from ralmon.spec import LoadedRegistry
from tests.fixtures.attribution import STEP_MS, hms, make_record


@dataclass(frozen=True)
class Day:
    """A structural ``ObservedTrace`` (patient-day) without the generator."""

    samples: Sequence[Sample] = ()
    events: Sequence[Event] = ()
    patient_id: str = "p1"
    day_index: int = 0
    seed: int = 0
    care_plan_id: str = "plan-1"


@dataclass
class Inputs:
    samples: list[Sample] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)

    def day(self) -> Day:
        return Day(
            samples=sorted(self.samples, key=lambda s: (s.t_rx_ms, s.t_device_ms)),
            events=sorted(self.events, key=lambda e: (e.t_rx_ms, e.t_device_ms)),
        )


def sample(
    signal: SignalId | str,
    t: int,
    *,
    rx: int | None = None,
    value: float = 1.0,
    seq: int | None = None,
    quality: float | None = None,
) -> Sample:
    name = signal.value if isinstance(signal, SignalId) else signal
    return Sample(name, t, t if rx is None else rx, value, seq, quality)


def event(
    kind: EventKind,
    t: int,
    source: str,
    *,
    rx: int | None = None,
    seq: int | None = None,
    **payload: float | str | bool,
) -> Event:
    return Event(kind, t, t if rx is None else rx, source, payload, seq)


def node_state(
    t: int,
    source: str,
    state: str,
    *,
    commanded: bool | None = None,
    **extra: float | str | bool,
) -> Event:
    payload: dict[str, float | int | str | bool] = {"state": state, **extra}
    if commanded is not None:
        payload["commanded"] = commanded
    return Event(EventKind.NODE_STATE, t, t, source, payload, None)


def robot_state(
    t: int, state: str = "active", *, colocated: bool, **extra: float | str | bool
) -> Event:
    return node_state(t, "robot", state, colocated=colocated, **extra)


def robot_task(
    t: int, task: str, outcome: str, *, patient: str | None = "p1", **extra: Any
) -> Event:
    payload: dict[str, float | int | str | bool] = {
        "task": task,
        "outcome": outcome,
        **extra,
    }
    if patient is not None:
        payload["patient_id"] = patient
    return Event(EventKind.ROBOT_TASK, t, t, "robot", payload, None)


def verification_failed(t: int, subject: str) -> Event:
    return Event(
        EventKind.VERIFICATION,
        t,
        t,
        "gateway",
        {"verification": "failed", "subject": subject},
        None,
    )


def device_error(t: int, code: str, source: str = "cuff") -> Event:
    return Event(EventKind.DEVICE_ERROR, t, t, source, {"error_code": code}, None)


def cuff_frame(t: int, seq: int | None = None, *, rx: int | None = None) -> Sample:
    """One message of the cuff: a ``bp`` Sample (FIXTURE-ONLY value, no clinical meaning)."""
    return sample(SignalId.BP, t, rx=rx, value=100.0, seq=seq)


@dataclass(frozen=True)
class ProfileSpec:
    """A device profile as plain data; ``to_profile`` builds the ``DeviceProfile`` when a test needs it."""

    nodes: Mapping[str, Mapping[str, Any]]


def profile(**nodes: Mapping[str, Any]) -> ProfileSpec:
    return ProfileSpec(nodes)


def to_profile(spec: ProfileSpec) -> Any:
    from ralmon.attribution.extract import DeviceCapabilities, DeviceProfile

    return DeviceProfile(
        {name: DeviceCapabilities(**caps) for name, caps in spec.nodes.items()}
    )


CUFF_ALL = {
    "status_reports": True,
    "supervised": True,
    "diagnostics": True,
    "seq": True,
    "two_clocks": True,
    "authenticates": True,
    "error_codes": True,
}


def full_profile() -> ProfileSpec:
    """The cuff capable of everything; the dispenser and the robot report status and are supervised."""
    return profile(
        cuff=CUFF_ALL,
        dispenser={"status_reports": True, "supervised": True},
        robot={"status_reports": True, "supervised": True, "battery": True},
    )


def hold_record(at: int = hms(21, 0)) -> Any:
    """A VIOLATED ``hold`` at the dispense ``at`` (decided at the dispense step)."""
    return make_record(
        "hold", key=f"hold@{at}", decided_at_ms=at, hi=-5.0, sigma_norm=(-0.25, -0.25)
    )


def int_record(at: int = hms(21, 0)) -> Any:
    return make_record(
        "int", key=f"int@{at}", decided_at_ms=at, hi=-1.0, sigma_norm=(-1.0, -1.0)
    )


def range_record(at: int = hms(21, 0)) -> Any:
    return make_record(
        "range", key=f"range@{at}", decided_at_ms=at, hi=-5.0, sigma_norm=(-0.25, -0.25)
    )


def extractor(
    registry: LoadedRegistry,
    prof: Any = None,
    *,
    reorder_delay_ms: int = 0,
    **kwargs: Any,
) -> Any:
    from ralmon.attribution import EvidenceExtractor

    return EvidenceExtractor(
        registry,
        step_ms=STEP_MS,
        reorder_delay_ms=reorder_delay_ms,
        profile=to_profile(prof if prof is not None else full_profile()),
        **kwargs,
    )


def feed(ex: Any, inputs: Inputs) -> Any:
    for s in sorted(inputs.samples, key=lambda s: s.t_rx_ms):
        ex.observe_sample(s)
    for e in sorted(inputs.events, key=lambda e: e.t_rx_ms):
        ex.observe_event(e)
    return ex


def evidence_dict(vec: Any) -> dict[str, Any]:
    """The twenty-four fields of an EvidenceVector as ``{group.field: value}``."""
    import dataclasses

    out: dict[str, Any] = {}
    for group in dataclasses.fields(vec):
        part = getattr(vec, group.name)
        for leaf in dataclasses.fields(part):
            out[f"{group.name}.{leaf.name}"] = getattr(part, leaf.name)
    return out
