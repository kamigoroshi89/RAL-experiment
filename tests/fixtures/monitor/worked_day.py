"""The worked patient-day of WS01-T08 as an end-to-end input (WS05-T08, test 19), and the row 15:00 day (test 20).

FIXTURE-ONLY. The observed day is the one of ``docs/formal/09-worked-patient-day.md`` (copy
``golden_patient_day.yaml``); the registry is the attribution fixture registry (the F0 table plus the seven
FIXTURE-ONLY names that the real registry lacks, open point OPF-6 of ``docs/formal/08-consistency-review.md``),
because the attribution package refuses the real registry; nothing here is a clinical value.

The golden day gives the evidence readings instead of deriving them (hypothesis H-W15: its observed day has
no ``NODE_STATE``, liveliness, heartbeat, ``hr_ecg`` or ``hr_pulse`` input). So that the extractor can derive
them, this module ADDS inputs to the observed day and declares a device profile; the added inputs are listed
in ``evidence_inputs`` and do not change a single verdict record (checked by the tests):

* ``NODE_STATE`` reports of the cuff, the dispenser and the robot at 00:00 (all active, diagnostics ok);
* the robot co-location reports that reproduce the golden availability of the robot channels: departure at
  00:00, arrival at 06:58, departure at 07:05 (ADR-054 (b), WS05-T11);
* the cuff process killed at 08:56 (``unreachable``) and restarted at 11:20 (W-11);
* ``hr_pulse`` and ``hr_ecg`` samples around the measurements of 12:24 and 20:32 (a coherent pair, W-01);
* a failed verification of the cuff message of 20:32 (the informed replay, W-08).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ralmon.attribution import (
    Alert,
    RuleAttributor,
    extract_evidence,
)
from ralmon.attribution.extract import DeviceCapabilities, DeviceProfile
from ralmon.conformal import CalibrationEpisode, SplitConformal
from ralmon.monitor import MonitorConfig, VerdictRecord, run_offline
from ralmon.signals import Event, EventKind, Sample
from ralmon.spec import (
    CarePlan,
    TemplateId,
    TemplateInstance,
    load_templates,
)
from tests.fixtures.attribution import hms, load_fixture_registry
from tests.fixtures.attribution.trace import CUFF_ALL

from .predictive import StubForecaster

GOLDEN = Path(__file__).resolve().parent / "golden_patient_day.yaml"
STEP = 60_000
H12 = 12 * 3_600_000


@dataclass(frozen=True)
class Day:
    """A structural ``ObservedTrace`` (no dependency on the benchmark generator)."""

    samples: Sequence[Sample]
    events: Sequence[Event]
    patient_id: str = "PD-1-patient"
    day_index: int = 0
    seed: int = 0
    care_plan_id: str = "PD-1-plan"


@dataclass
class World:
    registry: Any
    templates: Any
    profile: DeviceProfile


def golden() -> dict[str, Any]:
    return dict(yaml.safe_load(GOLDEN.read_text(encoding="utf-8")))


def world() -> World:
    registry = load_fixture_registry()
    templates = load_templates(registry=registry)
    profile = DeviceProfile(
        {
            # a data-stream deadline of 12 h: the cuff speaks four times a day, so the deadline never lapses
            "cuff": DeviceCapabilities(**{**CUFF_ALL, "deadline_ms": H12}),
            "dispenser": DeviceCapabilities(status_reports=True, supervised=True),
            "robot": DeviceCapabilities(status_reports=True, supervised=True),
        }
    )
    return World(registry, templates, profile)


def node_state(t: int, source: str, state: str, **payload: Any) -> Event:
    return Event(EventKind.NODE_STATE, t, t, source, {"state": state, **payload}, None)


def golden_inputs(doc: dict[str, Any]) -> tuple[list[Sample], list[Event]]:
    observed = doc["observed_day"]
    samples = [
        Sample(
            s["signal"],
            s["t_device_ms"],
            s["t_rx_ms"],
            float(s["value"]),
            s.get("seq"),
            s.get("quality"),
        )
        for s in observed["samples"]
    ]
    events = [
        Event(
            EventKind(e["kind"]),
            e["t_device_ms"],
            e["t_rx_ms"],
            e["source"],
            dict(e.get("payload") or {}),
            e.get("seq"),
        )
        for e in observed["events"]
    ]
    return samples, events


def evidence_inputs() -> tuple[list[Sample], list[Event]]:
    """The inputs added to the golden observed day so that the extractor derives the readings of H-W6."""
    events = [
        node_state(0, "cuff", "active", diagnostics="ok"),
        node_state(0, "dispenser", "active", diagnostics="ok"),
        node_state(0, "robot", "active", colocated=False),
        node_state(hms(6, 58), "robot", "active", colocated=True),
        node_state(hms(7, 5), "robot", "active", colocated=False),
        node_state(hms(8, 56), "cuff", "unreachable"),
        node_state(hms(11, 20), "cuff", "active", diagnostics="ok"),
        Event(
            EventKind.VERIFICATION,
            hms(20, 32),
            hms(20, 32),
            "gateway",
            {"verification": "failed", "subject": "cuff"},
            None,
        ),
    ]
    samples: list[Sample] = []
    for t, seq in ((hms(12, 24), 102), (hms(20, 32), 103)):
        samples.append(Sample("hr_pulse", t, t, 72.0, seq, None))
        samples.append(Sample("hr_ecg", t - STEP, t - STEP, 70.0, None, 0.9))
    return samples, events


def worked_day(*, with_evidence: bool = True) -> Day:
    doc = golden()
    samples, events = golden_inputs(doc)
    if with_evidence:
        more_samples, more_events = evidence_inputs()
        samples += more_samples
        events += more_events
    return Day(tuple(samples), tuple(events))


def worked_plan(registry: Any) -> CarePlan:
    doc = golden()["plan"]
    return CarePlan(
        doc["care_plan_id"],
        doc["pathway_template_id"],
        doc["patient_id"],
        registry.version(),
        tuple(
            TemplateInstance(
                TemplateId(item["template"]),
                item["instance_key"],
                {},
                item["anchor_ms"],
            )
            for item in doc["static_instances"]
        ),
        tuple(item["t_ms"] for item in doc["schedule"]),
        doc["plan_version"],
        None,
    )


def worked_calibrator(version: str) -> SplitConformal:
    """The calibrator fixture C-1 of ``conformal.yaml`` (nine scores, ``sigma_hat = 0`` episodes)."""
    scores = golden()["calibrator"]["scores_sorted"]
    episodes = [
        CalibrationEpisode(f"c1-{i}", 0, TemplateId.SCHED, 0.0, float(score))
        for i, score in enumerate(scores)
    ]
    calibrator = SplitConformal()
    calibrator.fit(episodes, 0.2, model_version=version)
    return calibrator


def worked_forecaster() -> StubForecaster:
    """The stub of the golden day (H-W13): an arrival only for the tick of 12:00 (12:40, 10 minutes late).

    The ticks of 06:50, 20:30 and 22:30 are answered with the arrival that the day then shows (2, 2 and 5
    minutes after the tick); the tick of 09:00 has no basis (the cuff is down: no arrival is forecast).
    """
    arrivals = {
        hms(6, 50): hms(6, 52),
        hms(9, 0): None,
        hms(12, 0): hms(12, 40),
        hms(20, 30): hms(20, 32),
        hms(22, 30): hms(22, 35),
    }
    return StubForecaster(arrival=arrivals, version="v1")


def pipeline(
    day: Any,
    plan: CarePlan,
    config: MonitorConfig,
    calibrator: Any,
    forecaster: Any,
    w: World,
) -> tuple[tuple[VerdictRecord, ...], list[Alert]]:
    """``run_offline``, ``extract_evidence``, ``RuleAttributor.attribute_all``: the chain of the end-to-end tests."""
    records = tuple(
        run_offline(
            day,
            plan,
            config,
            calibrator,
            forecaster,
            registry=w.registry,
            templates=w.templates,
        )
    )
    evidence = extract_evidence(
        day,
        records,
        w.registry,
        step_ms=config.step_ms,
        reorder_delay_ms=config.reorder_delay_ms,
        profile=w.profile,
        plan=plan,
    )
    attributor = RuleAttributor(w.registry, w.templates, plan=plan)
    return records, attributor.attribute_all(records, evidence)


# ---------------------------------------------------------------------------------------------
# the row 15:00 day (analisi section 4.6)
# ---------------------------------------------------------------------------------------------

ROW_TICKS = (hms(12, 30), hms(15, 0))
ROW_DISPENSE = hms(13, 0)


def row_1500_day() -> Day:
    """A day built from row 15:00 of analisi section 4.6: a missed measurement and its consequence.

    The robot fails to navigate at 14:55 and the node goes inactive by command at 14:56 (a deliberate
    transition, not a crash). The measurement of the tick of 15:00 never happens (the SCHED instance is
    violated at 15:30) and the response window of the 13:00 dose, [14:00, 16:00], closes without a
    measurement (the RESP instance is violated at 16:00). The day-end count of five measurements of analisi
    section 4.6 is not a template of the library (CP2, ADR-045 (d)); the later violation that the missed
    measurement causes is the response obligation, which the cascade table CT-1 folds under the root.
    """
    samples = [
        Sample("bp", hms(12, 32), hms(12, 32), 130.0, 1, None),
        Sample("cuff_health", hms(12, 32), hms(12, 32), 1.0, 1, None),
        Sample("inflation_ms", hms(12, 32), hms(12, 32), 45_000.0, 1, None),
        Sample("auth", ROW_DISPENSE, ROW_DISPENSE, 1.0, 2, None),
    ]
    events = [
        node_state(0, "cuff", "active", diagnostics="ok"),
        node_state(0, "dispenser", "active", diagnostics="ok"),
        node_state(0, "robot", "active", colocated=False),
        Event(EventKind.MEASUREMENT, hms(12, 32), hms(12, 32), "cuff", {}, 1),
        Event(EventKind.DISPENSE, ROW_DISPENSE, ROW_DISPENSE, "dispenser", {}, 2),
        Event(
            EventKind.ROBOT_TASK,
            hms(14, 55),
            hms(14, 55),
            "robot",
            {"task": "navigate", "outcome": "failed", "patient_id": "p-row"},
            None,
        ),
        node_state(hms(14, 56), "robot", "inactive", commanded=True),
    ]
    return Day(
        tuple(samples), tuple(events), patient_id="p-row", care_plan_id="plan-row"
    )


def row_1500_plan(registry: Any) -> CarePlan:
    return CarePlan(
        "plan-row",
        "hypertension-fixture",
        "p-row",
        registry.version(),
        tuple(
            TemplateInstance(TemplateId.SCHED, f"sched@{t}", {}, t) for t in ROW_TICKS
        ),
        (ROW_TICKS[0], ROW_DISPENSE, ROW_TICKS[1]),
        1,
        None,
    )
