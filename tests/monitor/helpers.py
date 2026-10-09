"""Shared helpers of the tests of ``ralmon.monitor`` (WS05-T04).

Fixture registry F0 and ``step_ms = 60000`` are fixture arithmetic (FIXTURE-ONLY, ADR-027); nothing
here is a clinical statement. Time labels convert as ``t_ms = (60 * hh + mm) * 60000``. The module
imports names of the code under test only through ``ralmon.monitor`` attributes read at call time,
so that the test files can be collected while the implementation is missing.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ralmon.signals import Event, EventKind, Sample

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "monitor"
F0_PATH = ROOT / "tests" / "fixtures" / "spec" / "registry_f0.yaml"
GOLDEN_SOURCES = ROOT / "docs" / "formal" / "golden"
SRC_MONITOR = ROOT / "src" / "ralmon" / "monitor"
INTERFACES = ROOT / "docs" / "plan" / "02-interfaces.md"

STEP = 60_000  # step_ms of the fixture (fixture arithmetic)
T_DAY = 86_400_000
K_DAY = T_DAY // STEP
BP_LOWER = 50.0  # bound_bp_lower of F0 (illustrative, unverified)
BP_UPPER = 250.0  # bound_bp_upper of F0 (illustrative, unverified)


def hhmm(hh: int, mm: int, ss: int = 0, ms: int = 0) -> int:
    return ((60 * hh + mm) * 60 + ss) * 1000 + ms


def close(a: float, b: float, rel: float = 1e-12) -> bool:
    """Equality of two raw or normalised values: infinities must be equal, finite ones close."""
    if math.isinf(a) or math.isinf(b):
        return a == b
    return abs(a - b) <= rel * max(1.0, abs(b))


# -- registry, templates, configuration --------------------------------------------------------


def load_f0(step_ms: int = STEP, path: Path = F0_PATH) -> Any:
    from ralmon.spec import load_registry

    return load_registry(path, step_ms=step_ms, allow_fixture_only=True)


def load_lib(registry: Any) -> Any:
    from ralmon.spec import load_templates

    return load_templates(registry=registry)


def make_config(
    registry: Any,
    *,
    d_ms: int = 0,
    step_ms: int = STEP,
    predictive: bool = False,
    alpha: float | None = None,
    variant: str = "likely",
) -> Any:
    import ralmon.monitor as m

    return m.MonitorConfig(
        step_ms=step_ms,
        reorder_delay_ms=d_ms,
        predictive=predictive,
        alpha=alpha,
        variant=variant,  # type: ignore[arg-type]
        registry_version=registry.version(),
    )


def make_plan(
    registry: Any,
    *,
    sched: Iterable[int] = (),
    day_end: Iterable[int] = (),
    records: Sequence[Any] = (),
    plan_version: int = 1,
    care_plan_id: str = "plan-1",
    signature: str | None = None,
    patient_id: str = "p-1",
) -> Any:
    """A plan with static SCHED instances at ``sched`` and day-end COUNT instances at ``day_end``."""
    from ralmon.spec import CarePlan, TemplateId, TemplateInstance

    instances: list[Any] = [
        TemplateInstance(TemplateId.SCHED, f"sched@{a}", {}, a) for a in sched
    ]
    instances += [
        TemplateInstance(TemplateId.COUNT, f"count@{a}", {}, a) for a in day_end
    ]
    instances += list(records)
    return CarePlan(
        care_plan_id=care_plan_id,
        pathway_template_id="hypertension-fixture",
        patient_id=patient_id,
        registry_version=registry.version(),
        instances=tuple(instances),
        schedule=(),
        plan_version=plan_version,
        signature=signature,
    )


def make_monitor(
    registry: Any | None = None,
    *,
    d_ms: int = 0,
    plan: Any | None = None,
    sched: Iterable[int] = (),
    day_end: Iterable[int] = (),
    **kwargs: Any,
) -> Any:
    """A StreamingMonitor on the F0 registry with the plan loaded."""
    import ralmon.monitor as m

    registry = load_f0() if registry is None else registry
    config = make_config(registry, d_ms=d_ms)
    mon = m.StreamingMonitor(config, registry, load_lib(registry), **kwargs)
    if plan is None:
        plan = make_plan(registry, sched=sched, day_end=day_end)
    mon.load(plan)
    return mon


# -- inputs --------------------------------------------------------------------------------------


def smp(
    signal: str,
    t: int,
    value: float = 1.0,
    *,
    rx: int | None = None,
    seq: int | None = None,
) -> Sample:
    return Sample(signal, t, t if rx is None else rx, float(value), seq, None)


def evt(
    kind: str,
    t: int,
    *,
    rx: int | None = None,
    source: str = "dev",
    seq: int | None = None,
) -> Event:
    return Event(EventKind(kind), t, t if rx is None else rx, source, {}, seq)


@dataclass
class Inputs:
    samples: list[Sample] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    # (signal, available, t_device_ms, t_rx_ms)
    avail: list[tuple[str, bool, int, int]] = field(default_factory=list)

    def merged(self) -> list[tuple[int, int, int, str, Any]]:
        """Items sorted by receive time, then samples, events, availability, then file order."""
        items: list[tuple[int, int, int, str, Any]] = []
        for i, s in enumerate(self.samples):
            items.append((s.t_rx_ms, 0, i, "sample", s))
        for i, e in enumerate(self.events):
            items.append((e.t_rx_ms, 1, i, "event", e))
        for i, a in enumerate(self.avail):
            items.append((a[3], 2, i, "avail", a))
        items.sort(key=lambda it: it[:3])
        return items


def mark_unavailable(inputs: Inputs, signal: str, from_ms: int, to_ms: int) -> None:
    """The golden ``channels_unavailable`` entry as two availability inputs (steps inclusive)."""
    inputs.avail.append((signal, False, from_ms, from_ms))
    inputs.avail.append((signal, True, to_ms + 1, to_ms + 1))


def drive(
    mon: Any,
    inputs: Inputs,
    last_step: int,
    *,
    d_ms: int = 0,
    first_step: int = 0,
    step_ms: int = STEP,
) -> list[Any]:
    """The cadence of ``run_offline`` (WS05 README D5): push what has arrived, then ``advance``."""
    items = inputs.merged()
    pointer = 0
    records: list[Any] = []
    for k in range(first_step, last_step + 1):
        t = k * step_ms + d_ms
        while pointer < len(items) and items[pointer][0] <= t:
            _rx, _rank, _i, kind, obj = items[pointer]
            if kind == "sample":
                mon.push_sample(obj)
            elif kind == "event":
                mon.push_event(obj)
            else:
                from ralmon.signals import SignalId

                mon.push_availability(SignalId(obj[0]), obj[1], obj[2], obj[3])
            pointer += 1
        records.extend(mon.advance(t))
    return records


def by_key(records: Iterable[Any]) -> dict[str, list[Any]]:
    out: dict[str, list[Any]] = {}
    for r in records:
        out.setdefault(r.instance_key, []).append(r)
    return out


def at_step(records: Iterable[Any], key: str, t_eval_ms: int) -> Any:
    found = [r for r in records if r.instance_key == key and r.t_eval_ms == t_eval_ms]
    assert len(found) == 1, f"{key} at {t_eval_ms}: {len(found)} records"
    return found[0]


def final(records: Iterable[Any], key: str) -> Any:
    found = [r for r in records if r.instance_key == key]
    assert found, f"no record for {key}"
    return found[-1]


def first_definitive(records: Iterable[Any], key: str) -> Any | None:
    for r in records:
        if r.instance_key == key and r.state.value in ("violated", "satisfied"):
            return r
    return None


# -- a local ObservedTrace ----------------------------------------------------------------------


@dataclass(frozen=True)
class LocalDay:
    """Structural day (the ``ObservedTrace`` Protocol); no dependency on WS04."""

    samples: Sequence[Sample]
    events: Sequence[Event]
    patient_id: str = "p-1"
    day_index: int = 0
    seed: int = 0
    care_plan_id: str = "plan-1"


# -- golden files ---------------------------------------------------------------------------------


def read_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def golden_templates() -> list[dict[str, Any]]:
    return list(read_yaml(FIXTURES / "golden_templates.yaml")["cases"])


def golden_verdicts() -> list[dict[str, Any]]:
    return list(read_yaml(FIXTURES / "golden_verdicts.yaml"))


def golden_patient_day() -> dict[str, Any]:
    return dict(read_yaml(FIXTURES / "golden_patient_day.yaml"))


def samples_of(case_inputs: Mapping[str, Any]) -> list[Sample]:
    return [
        Sample(
            s["signal"],
            s["t_device_ms"],
            s["t_rx_ms"],
            float(s["value"]),
            s.get("seq"),
            s.get("quality"),
        )
        for s in case_inputs.get("samples", [])
    ]


def events_of(case_inputs: Mapping[str, Any]) -> list[Event]:
    return [
        Event(
            EventKind(e["kind"]),
            e["t_device_ms"],
            e["t_rx_ms"],
            e["source"],
            dict(e.get("payload") or {}),
            e.get("seq"),
        )
        for e in case_inputs.get("events", [])
    ]


def inputs_of(case_inputs: Mapping[str, Any]) -> Inputs:
    """Samples, events and ``channels_unavailable`` of a golden case (1 step = 1 grid step)."""
    inputs = Inputs(samples_of(case_inputs), events_of(case_inputs))
    for c in case_inputs.get("channels_unavailable") or []:
        if isinstance(
            c, str
        ):  # templates.yaml: the channel is unavailable for the whole day
            mark_unavailable(inputs, c, 0, T_DAY)
        else:
            mark_unavailable(inputs, c["signal"], c["from_ms"], c["to_ms"])
    return inputs


def expect_interval(
    rec: Any, raw: Sequence[float], norm: Sequence[float], label: str
) -> None:
    assert close(rec.sigma_interval.lo, float(raw[0])), (
        label,
        "lo",
        rec.sigma_interval,
    )
    assert close(rec.sigma_interval.hi, float(raw[1])), (
        label,
        "hi",
        rec.sigma_interval,
    )
    assert close(rec.sigma_norm_interval[0], float(norm[0])), (
        label,
        "norm lo",
        rec.sigma_norm_interval,
    )
    assert close(rec.sigma_norm_interval[1], float(norm[1])), (
        label,
        "norm hi",
        rec.sigma_norm_interval,
    )


def expect_record(rec: Any, expected: Mapping[str, Any], label: str) -> None:
    """Compare the fields that the golden ``expected`` block carries (05 section 9.3 item 5)."""
    assert rec.state.value == expected["state"], (label, rec.state)
    assert rec.t_eval_ms == expected["t_eval_ms"], (label, rec.t_eval_ms)
    expect_interval(
        rec, expected["sigma_interval"], expected["sigma_norm_interval"], label
    )
    assert rec.decided_at_ms == expected["decided_at_ms"], (label, rec.decided_at_ms)
    assert rec.pending_until_ms == expected["pending_until_ms"], (
        label,
        rec.pending_until_ms,
    )
    assert rec.guard_failed == expected.get("guard_failed"), (label, rec.guard_failed)
    assert rec.undecidable == expected.get("marker"), (label, rec.undecidable)
    # the tie annotation is a property of the interval and the state, not a field of the record
    is_tie = (
        rec.state.value == "satisfied"
        and rec.sigma_interval.lo == 0
        and rec.sigma_interval.hi == 0
    )
    assert is_tie == bool(expected.get("tie_rule", False)), (label, "tie_rule")
    want = expected.get("rho")
    if want is None:
        assert rec.rho is None, (label, rec.rho)
    else:
        assert rec.rho is not None, label
        assert rec.rho.kind.value == want["kind"], (label, rec.rho)
        assert abs(rec.rho.value - float(want["value"])) <= 1e-9, (label, rec.rho)
        assert rec.rho.alpha == want.get("alpha"), (label, rec.rho)
        if "guarantee" in want:
            assert rec.rho.guarantee == want["guarantee"], (label, rec.rho)
            assert list(rec.rho.assumptions) == list(want["assumptions"]), (
                label,
                rec.rho,
            )


# -- grid values for the point evaluator (what a baseline builds from ralmon.signals) ------------


def step_values(inputs: Inputs, last_step: int) -> list[dict[str, float | None]]:
    """The ``values`` argument of ``PointEvaluator.step`` for steps 0..``last_step``.

    Built the way a baseline builds it from the public helpers of ``ralmon.signals``: ``hold_last``
    for the held signals, ``impulses_on_grid`` (from step 0, never a sub-grid) for the impulses,
    the derived signals fed in device-time order with a clock sample at every step. A held signal
    that is undefined is absent; ``None`` marks a robot channel that is unavailable.
    """
    from ralmon.signals import (
        SignalId,
        default_derived_signals,
        event_to_sample,
        hold_last,
        impulses_on_grid,
    )

    grid = [k * STEP for k in range(last_step + 1)]
    held_ids = ("bp", "cuff_health", "inflation_ms", "presence")
    held = {
        sig: hold_last(
            sorted(
                (s for s in inputs.samples if s.signal == sig),
                key=lambda s: s.t_device_ms,
            ),
            grid,
        )
        for sig in held_ids
    }
    impulses = {
        sig: impulses_on_grid(
            [
                e
                for e in map(event_to_sample, inputs.events)
                if e is not None and e.signal == sig
            ],
            grid,
            count=True,
        )
        for sig in ("meas", "dispense", "intake", "sched_tick")
    }
    impulses["auth"] = impulses_on_grid(
        [s for s in inputs.samples if s.signal == "auth"], grid, count=True
    )
    # robot-channel availability: the last input with step <= k wins
    avail_changes: dict[str, list[tuple[int, bool]]] = {}
    for sig, on, t, _rx in sorted(inputs.avail, key=lambda a: a[2]):
        avail_changes.setdefault(sig, []).append(((t + STEP - 1) // STEP, on))

    def available(sig: str, k: int) -> bool:
        state = True
        for step, on in avail_changes.get(sig, ()):
            if step <= k:
                state = on
        return state

    derived = list(default_derived_signals())
    stream = sorted(
        [s for s in inputs.samples if s.signal != "auth"]
        + [x for x in map(event_to_sample, inputs.events) if x is not None],
        key=lambda s: (s.t_device_ms, 0 if s.signal == "bp" else 1),
    )
    last_out: dict[str, float] = {}
    pointer = 0
    out: list[dict[str, float | None]] = []
    for k, t in enumerate(grid):
        while pointer < len(stream) and stream[pointer].t_device_ms <= t:
            for d in derived:
                produced = d.update(stream[pointer])
                if produced is not None:
                    last_out[produced.signal] = produced.value
            pointer += 1
        for d in derived:  # the clock sample of the step (hand-over of WS05-T02)
            produced = d.update(Sample(SignalId.SPO2.value, t, t, 0.0, None, None))
            if produced is not None:
                last_out[produced.signal] = produced.value
        values: dict[str, float | None] = {}
        for sig in held_ids:
            v = held[sig][k]
            if sig == "presence" and not available("presence", k):
                values[sig] = None
            elif not math.isnan(v):
                values[sig] = v
        for sig, arr in impulses.items():
            values[sig] = (
                None if sig == "intake" and not available("intake", k) else arr[k]
            )
        for name, v in last_out.items():
            values[name] = v
        out.append(values)
    return out


# -- registry variants (a throwaway copy of F0 with some rows changed) --------------------------


def registry_variant(
    directory: Path,
    *,
    values: Mapping[str, float] | None = None,
    add_entries: Sequence[Mapping[str, Any]] = (),
    overrides: Sequence[Mapping[str, Any]] = (),
    step_ms: int | None = STEP,
) -> Any:
    """Load a copy of the F0 registry with ``values`` replaced, ``add_entries`` appended and
    ``overrides`` added. The copy lives in ``directory`` (a temporary directory); the real registry
    file is never touched."""
    from ralmon.spec import load_registry

    doc = yaml.safe_load(F0_PATH.read_text(encoding="utf-8"))
    for entry in doc["entries"]:
        if values and entry["name"] in values:
            entry["value"] = values[entry["name"]]
    doc["entries"].extend(dict(e) for e in add_entries)
    if overrides:
        doc["overrides"] = [dict(o) for o in overrides]
    path = directory / "registry.yaml"
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return load_registry(path, step_ms=step_ms, allow_fixture_only=True)


def entry_row(name: str, value: float, unit: str = "ms") -> dict[str, Any]:
    return {
        "name": name,
        "value": value,
        "unit": unit,
        "rationale": "FIXTURE-ONLY (test row); illustrative, unverified",
        "source_ref": "test",
        "reviewed_by": None,
    }


def override_row(name: str, low: float, high: float) -> dict[str, Any]:
    return {
        "name": name,
        "min": low,
        "max": high,
        "rationale": "approved range of a test",
        "source_ref": "test",
        "reviewed_by": None,
    }


def _unset_error() -> Any:
    from ralmon.spec import UnsetParameterError

    return UnsetParameterError


class SpyRegistry:
    """Delegates to a registry, records every name read and can declare names unset."""

    def __init__(self, inner: Any, unset: tuple[str, ...] = ()) -> None:
        self.inner = inner
        self.unset = unset
        self.read: list[str] = []
        self.step_ms = inner.step_ms

    def get(self, name: str) -> Any:
        self.read.append(name)
        if name in self.unset:
            raise _unset_error()(f"parameter {name!r} is declared but has no value yet")
        return self.inner.get(name)

    def bounds(self, signal: str) -> Any:
        return self.inner.bounds(signal)

    def version(self) -> str:
        return self.inner.version()

    def overrides(self) -> Any:
        return self.inner.overrides()
