"""The evidence extractor (WS05-T07 tests 28 to 36 and the rows of the derivation table of evidence-channels.md).

The fixture day is the one of the worked checks EX-1 to EX-12 of ``docs/models/evidence-channels.md`` (step 60000,
F0 registry, hold look-back 3600000, INT window 300000); the FIXTURE-ONLY parameters of the test registry are an
evidence margin of 600000, a grace of 0, a held-ECG age of 600000 and a skew bound of 1000. Every expected value is
the documented value of the check named in the case id.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ralmon.signals import EventKind, SignalId
from ralmon.spec import RegistryError, TemplateId, TemplateKind
from tests.fixtures.attribution import (
    STEP_MS,
    hms,
    load_fixture_registry,
    make_record,
    registry_variant,
)
from tests.fixtures.attribution.trace import (
    CUFF_ALL,
    Inputs,
    cuff_frame,
    device_error,
    event,
    evidence_dict,
    extractor,
    feed,
    full_profile,
    hold_record,
    int_record,
    node_state,
    profile,
    range_record,
    robot_state,
    robot_task,
    sample,
    to_profile,
    verification_failed,
)

NO_NODES: dict[str, dict[str, Any]] = {}


@pytest.fixture(scope="module")
def registry():  # type: ignore[no-untyped-def]
    return load_fixture_registry()


@dataclass
class Case:
    id: str
    record: Any
    inputs: Inputs
    expected: Mapping[str, Any]
    prof: Any = None
    reorder_delay_ms: int = 0
    kwargs: dict[str, Any] = field(default_factory=dict)


def at(hh: int, mm: int, ss: int = 0) -> int:
    return hms(hh, mm, ss)


def I(*items: Any) -> Inputs:
    out = Inputs()
    for item in items:
        if hasattr(item, "signal"):
            out.samples.append(item)
        else:
            out.events.append(item)
    return out


CUFF_ONLY = profile(cuff=CUFF_ALL)
CUFF_DEADLINE = profile(cuff={**CUFF_ALL, "deadline_ms": 600_000})
INT_ROBOT = profile(
    dispenser={"status_reports": True, "supervised": True},
    robot={"status_reports": True, "supervised": True, "battery": True},
)
THREE_ACTIVE = {"cuff": "active", "dispenser": "active", "robot": "active"}


def lifecycle(**overrides: str) -> dict[str, str]:
    return {**THREE_ACTIVE, **overrides}


def cases() -> list[Case]:
    hold = hold_record
    out: list[Case] = []

    # ---- provenance -----------------------------------------------------------------------------
    out += [
        Case(
            "provenance.violated_template[EX copy of the record]",
            hold(),
            I(),
            {"provenance.violated_template": TemplateId.HOLD},
        ),
        Case(
            "provenance.template_kind[hold is phi_cp]",
            hold(),
            I(),
            {"provenance.template_kind": TemplateKind.CARE_PLAN},
        ),
        Case(
            "provenance.template_kind[sys is phi_sys]",
            make_record("sys", key="sys@75600000", decided_at_ms=at(21, 0)),
            I(),
            {"provenance.template_kind": TemplateKind.SYSTEM},
        ),
        Case(
            "provenance.template_kind[int is phi_int]",
            int_record(),
            I(),
            {"provenance.template_kind": TemplateKind.INTEGRITY},
        ),
    ]

    # ---- system.node_lifecycle (EX-4) -----------------------------------------------------------
    def life(
        name: str, events: list[Any], expected: dict[str, str], live: bool = True
    ) -> Case:
        return Case(
            f"system.node_lifecycle[EX-4 {name}]",
            hold(),
            I(node_state(0, "cuff", "active"), *events),
            {"system.node_lifecycle": expected, "system.liveliness_ok": live},
        )

    out += [
        life(
            "uncommanded deactivation 20:10",
            [node_state(at(20, 10), "cuff", "inactive", commanded=False)],
            lifecycle(cuff="inactive"),
        ),
        life(
            "commanded deactivation 20:10",
            [node_state(at(20, 10), "cuff", "inactive", commanded=True)],
            lifecycle(cuff="inactive+commanded"),
        ),
        life(
            "deactivation 19:00 still in force",
            [node_state(at(19, 0), "cuff", "inactive")],
            lifecycle(cuff="inactive"),
        ),
        life(
            "deactivation 20:10 undone 20:20",
            [
                node_state(at(20, 10), "cuff", "inactive"),
                node_state(at(20, 20), "cuff", "active"),
            ],
            lifecycle(cuff="inactive"),
        ),
        life(
            "deactivation 18:10 undone 18:20",
            [
                node_state(at(18, 10), "cuff", "inactive"),
                node_state(at(18, 20), "cuff", "active"),
            ],
            lifecycle(cuff="active"),
        ),
        life(
            "unreachable 20:15",
            [node_state(at(20, 15), "cuff", "unreachable")],
            lifecycle(cuff="unreachable"),
            live=False,
        ),
        life(
            "link_down 20:15",
            [node_state(at(20, 15), "cuff", "link_down")],
            lifecycle(cuff="link_down"),
        ),
        life(
            "uncommanded 20:10 then commanded 20:20",
            [
                node_state(at(20, 10), "cuff", "inactive", commanded=False),
                node_state(at(20, 20), "cuff", "inactive", commanded=True),
            ],
            lifecycle(cuff="inactive"),
        ),
        life(
            "commanded 20:10 then uncommanded 20:20",
            [
                node_state(at(20, 10), "cuff", "inactive", commanded=True),
                node_state(at(20, 20), "cuff", "inactive", commanded=False),
            ],
            lifecycle(cuff="inactive"),
        ),
        life(
            "commanded 20:10 undone 20:20",
            [
                node_state(at(20, 10), "cuff", "inactive", commanded=True),
                node_state(at(20, 20), "cuff", "active"),
            ],
            lifecycle(cuff="inactive+commanded"),
        ),
        Case(
            "system.node_lifecycle[no node reports status: None]",
            hold(),
            I(),
            {"system.node_lifecycle": None},
            prof=profile(cuff={"seq": True}),
        ),
        Case(
            "system.node_lifecycle[a node that never reports reads active (H-INIT)]",
            hold(),
            I(),
            {"system.node_lifecycle": THREE_ACTIVE},
        ),
    ]

    # ---- diagnostics, liveliness, deadline ---------------------------------------------------------
    diag = profile(cuff={"status_reports": True, "diagnostics": True})
    out += [
        Case(
            "system.diagnostics_ok[every capable node reported ok: True]",
            hold(),
            I(node_state(at(19, 0), "cuff", "active", diagnostics="ok")),
            {"system.diagnostics_ok": True},
            prof=diag,
        ),
        Case(
            "system.diagnostics_ok[an error report in the window: False]",
            hold(),
            I(
                node_state(at(19, 0), "cuff", "active", diagnostics="ok"),
                node_state(at(20, 20), "cuff", "active", diagnostics="error"),
            ),
            {"system.diagnostics_ok": False},
            prof=diag,
        ),
        Case(
            "system.diagnostics_ok[stale report: False]",
            hold(),
            I(node_state(at(20, 20), "cuff", "active", diagnostics="stale")),
            {"system.diagnostics_ok": False},
            prof=diag,
        ),
        Case(
            "system.diagnostics_ok[a capable node with no report: None]",
            hold(),
            I(),
            {"system.diagnostics_ok": None},
            prof=diag,
        ),
        Case(
            "system.diagnostics_ok[an ok report of an inactive node is not an ok reading: None]",
            hold(),
            I(
                node_state(at(19, 0), "cuff", "active", diagnostics="ok"),
                node_state(at(20, 10), "cuff", "inactive"),
            ),
            {"system.diagnostics_ok": None},
            prof=diag,
        ),
        Case(
            "system.diagnostics_ok[no node declares diagnostics: None]",
            hold(),
            I(node_state(at(19, 0), "cuff", "active", diagnostics="ok")),
            {"system.diagnostics_ok": None},
            prof=profile(cuff={"status_reports": True}),
        ),
        Case(
            "system.liveliness_ok[no lapse of a supervised node: True]",
            hold(),
            I(),
            {"system.liveliness_ok": True},
        ),
        Case(
            "system.liveliness_ok[a lapse in force at the window start: False]",
            hold(),
            I(node_state(at(19, 0), "dispenser", "unreachable")),
            {"system.liveliness_ok": False},
        ),
        Case(
            "system.liveliness_ok[no supervised node: None]",
            hold(),
            I(),
            {"system.liveliness_ok": None},
            prof=profile(cuff={"status_reports": True}),
        ),
    ]
    arrivals_ok = [cuff_frame(at(20, m)) for m in range(0, 65, 5)]
    arrivals_gap = [
        cuff_frame(at(20, m)) for m in (0, 5, 10, 30, 35, 40, 45, 50, 55)
    ] + [cuff_frame(at(21, 0))]
    out += [
        Case(
            "system.qos_deadline_missed[EX-6 nominal arrivals every 300000: False]",
            hold(),
            I(*arrivals_ok),
            {"system.qos_deadline_missed": False},
            prof=CUFF_DEADLINE,
        ),
        Case(
            "system.qos_deadline_missed[EX-6 three consecutive messages lost: True]",
            hold(),
            I(*arrivals_gap),
            {"system.qos_deadline_missed": True},
            prof=CUFF_DEADLINE,
        ),
        Case(
            "system.qos_deadline_missed[EX-6 one message lost, gap equal to the deadline: False]",
            hold(),
            I(
                *[
                    cuff_frame(at(20, m))
                    for m in (0, 5, 15, 20, 25, 30, 35, 40, 45, 50, 55)
                ],
                cuff_frame(at(21, 0)),
            ),
            {"system.qos_deadline_missed": False},
            prof=CUFF_DEADLINE,
        ),
        Case(
            "system.qos_deadline_missed[a heartbeat deadline report of the robot: True]",
            hold(),
            I(robot_state(at(20, 40), colocated=False, deadline_missed=True)),
            {"system.qos_deadline_missed": True},
            prof=profile(robot={"status_reports": True, "deadline_ms": 1000}),
        ),
        Case(
            "system.qos_deadline_missed[no declared deadline: None]",
            hold(),
            I(*arrivals_gap),
            {"system.qos_deadline_missed": None},
        ),
    ]

    # ---- sequence and time evidence (EX-1) --------------------------------------------------------
    d120 = 120_000
    frames = [
        (at(20, 10, 20), 1),
        (at(20, 11, 10), 2),
        (at(20, 12, 5), 3),
        (at(20, 13, 0), 4),
    ]

    def seq_inputs(skip: tuple[int, ...] = (), extra: tuple[Any, ...] = ()) -> Inputs:
        return I(*[cuff_frame(t, s) for t, s in frames if s not in skip], *extra)

    out += [
        Case(
            "system.ble_link_quality[EX-1 (a) in order: 1.0]",
            hold(),
            seq_inputs(),
            {
                "system.ble_link_quality": 1.0,
                "system.seq_gap": False,
                "crypto_temporal.seq_repeat": False,
                "crypto_temporal.timestamp_implausible": False,
            },
            prof=CUFF_ONLY,
            reorder_delay_ms=d120,
        ),
        Case(
            "system.ble_link_quality[EX-1 (b) seq 2 before seq 1 within the bound: 1.0]",
            hold(),
            I(
                cuff_frame(frames[0][0], 1, rx=at(20, 11, 30)),
                cuff_frame(frames[1][0], 2, rx=at(20, 11, 20)),
                cuff_frame(frames[2][0], 3),
                cuff_frame(frames[3][0], 4),
            ),
            {
                "system.ble_link_quality": 1.0,
                "system.seq_gap": False,
                "crypto_temporal.seq_repeat": False,
                "crypto_temporal.timestamp_implausible": False,
            },
            prof=CUFF_ONLY,
            reorder_delay_ms=d120,
        ),
        Case(
            "system.ble_link_quality[EX-1 (c) seq 2 lost: 0.75]",
            hold(),
            seq_inputs(skip=(2,)),
            {
                "system.ble_link_quality": 0.75,
                "system.seq_gap": True,
                "crypto_temporal.seq_repeat": False,
            },
            prof=CUFF_ONLY,
            reorder_delay_ms=d120,
        ),
        Case(
            "crypto_temporal.timestamp_implausible[EX-1 (d) seq 2 after its watermark before the cut-off: True, no gap]",
            hold(),
            I(
                cuff_frame(frames[0][0], 1),
                cuff_frame(frames[1][0], 2, rx=at(20, 15, 0)),
                cuff_frame(frames[2][0], 3),
                cuff_frame(frames[3][0], 4),
            ),
            {
                "crypto_temporal.timestamp_implausible": True,
                "system.seq_gap": False,
                "crypto_temporal.seq_repeat": False,
                "system.ble_link_quality": 1.0,
            },
            prof=CUFF_ONLY,
            reorder_delay_ms=d120,
        ),
        Case(
            "system.seq_gap[EX-1 (e) seq 2 after the cut-off: a gap, nothing counted late]",
            hold(),
            I(
                cuff_frame(frames[0][0], 1),
                cuff_frame(frames[1][0], 2, rx=at(21, 30, 0)),
                cuff_frame(frames[2][0], 3),
                cuff_frame(frames[3][0], 4),
            ),
            {
                "system.seq_gap": True,
                "crypto_temporal.seq_repeat": False,
                "system.ble_link_quality": 0.75,
                "crypto_temporal.timestamp_implausible": False,
            },
            prof=CUFF_ONLY,
            reorder_delay_ms=d120,
        ),
        Case(
            "crypto_temporal.seq_repeat[EX-1 (f) a copy of seq 2 on time: a repeat without gap]",
            hold(),
            seq_inputs(extra=(cuff_frame(at(20, 11, 30), 2),)),
            {
                "crypto_temporal.seq_repeat": True,
                "system.seq_gap": False,
                "system.ble_link_quality": 1.0,
            },
            prof=CUFF_ONLY,
            reorder_delay_ms=d120,
        ),
        Case(
            "crypto_temporal.seq_repeat[EX-1 (g) seq 2 lost and a copy of seq 3: repeat and gap]",
            hold(),
            seq_inputs(skip=(2,), extra=(cuff_frame(at(20, 12, 30), 3),)),
            {
                "crypto_temporal.seq_repeat": True,
                "system.seq_gap": True,
                "system.ble_link_quality": 0.75,
            },
            prof=CUFF_ONLY,
            reorder_delay_ms=d120,
        ),
        Case(
            "system.seq_gap[EX-1 (l) a trailing loss is not seen: ratio 1.0]",
            hold(),
            seq_inputs(skip=(4,)),
            {
                "system.seq_gap": False,
                "crypto_temporal.seq_repeat": False,
                "system.ble_link_quality": 1.0,
            },
            prof=CUFF_ONLY,
            reorder_delay_ms=d120,
        ),
        Case(
            "system.seq_gap[EX-1 (m) a forged number that jumps ahead: gap, ratio 0.12]",
            hold(),
            I(
                *[cuff_frame(at(20, 0) + 600_000 * (i - 1), i) for i in range(1, 6)],
                cuff_frame(at(20, 41), 50),
            ),
            {
                "system.seq_gap": True,
                "crypto_temporal.seq_repeat": False,
                "system.ble_link_quality": pytest.approx(0.12, abs=0.005),
            },
            prof=CUFF_ONLY,
            reorder_delay_ms=d120,
        ),
        Case(
            "system.seq_gap[EX-3 (f) a silent capable cuff: None, the dispenser cannot deny]",
            hold(),
            I(sample(SignalId.DISPENSE, at(20, 50), seq=1)),
            {
                "system.seq_gap": None,
                "crypto_temporal.seq_repeat": None,
                "crypto_temporal.timestamp_implausible": None,
                "crypto_temporal.authenticated": None,
                "system.ble_link_quality": None,
            },
            prof=profile(
                cuff=CUFF_ALL,
                dispenser={"seq": True, "two_clocks": True, "authenticates": True},
            ),
        ),
        Case(
            "system.seq_gap[no device provides seq: None]",
            hold(),
            seq_inputs(),
            {
                "system.seq_gap": None,
                "crypto_temporal.seq_repeat": None,
                "system.ble_link_quality": None,
            },
            prof=profile(cuff={"two_clocks": True}),
            reorder_delay_ms=d120,
        ),
        Case(
            "crypto_temporal.timestamp_implausible[a future-stamped message: True]",
            hold(),
            I(
                cuff_frame(at(20, 30, 10), 1, rx=at(20, 30, 0)),
                cuff_frame(at(20, 31), 2),
            ),
            {"crypto_temporal.timestamp_implausible": True},
            prof=CUFF_ONLY,
        ),
        Case(
            "crypto_temporal.timestamp_implausible[no independent clocks never denies: None]",
            hold(),
            seq_inputs(),
            {"crypto_temporal.timestamp_implausible": None},
            prof=profile(cuff={"seq": True}),
            reorder_delay_ms=d120,
        ),
        Case(
            "crypto_temporal.timestamp_implausible[no independent clocks still asserts a late message: True]",
            hold(),
            I(
                cuff_frame(frames[0][0], 1),
                cuff_frame(frames[1][0], 2, rx=at(20, 15, 0)),
            ),
            {"crypto_temporal.timestamp_implausible": True},
            prof=profile(cuff={"seq": True}),
            reorder_delay_ms=d120,
        ),
    ]

    # ---- authentication -----------------------------------------------------------------------
    out += [
        Case(
            "crypto_temporal.authenticated[a failed verification logged in the window: False]",
            hold(),
            I(cuff_frame(at(20, 30), 1), verification_failed(at(20, 40), "cuff")),
            {"crypto_temporal.authenticated": False},
            prof=CUFF_ONLY,
        ),
        Case(
            "crypto_temporal.authenticated[an authenticating device with a message and no failure: True]",
            hold(),
            I(cuff_frame(at(20, 30), 1)),
            {"crypto_temporal.authenticated": True},
            prof=CUFF_ONLY,
        ),
        Case(
            "crypto_temporal.authenticated[an authenticating device with no message: None]",
            hold(),
            I(),
            {"crypto_temporal.authenticated": None},
            prof=CUFF_ONLY,
        ),
        Case(
            "crypto_temporal.authenticated[no device authenticates (unauthenticated deployment): None]",
            hold(),
            I(cuff_frame(at(20, 30), 1)),
            {"crypto_temporal.authenticated": None},
            prof=profile(cuff={"seq": True}),
        ),
    ]

    # ---- robot task outcomes and battery ---------------------------------------------------------
    for task, path in (
        ("navigate", "system.nav_task_failed"),
        ("manipulate", "system.manip_task_failed"),
    ):
        out += [
            Case(
                f"{path}[a failed outcome: True]",
                hold(),
                I(robot_task(at(20, 45), task, "failed")),
                {path: True},
            ),
            Case(
                f"{path}[a timeout: True]",
                hold(),
                I(robot_task(at(20, 45), task, "timeout")),
                {path: True},
            ),
            Case(
                f"{path}[EX-11 (b) an overrun report stamped at the deadline: True]",
                hold(),
                I(robot_task(at(21, 0), task, "late")),
                {path: True},
            ),
            Case(
                f"{path}[EX-11 (a) a late outcome stamped at completion, after the decision time: None]",
                hold(),
                I(robot_task(at(21, 22), task, "late")),
                {path: None},
            ),
            Case(
                f"{path}[success outcomes only: False]",
                hold(),
                I(
                    robot_task(at(20, 20), task, "success"),
                    robot_task(at(20, 40), task, "success"),
                ),
                {path: False},
            ),
            Case(f"{path}[no outcome: None]", hold(), I(), {path: None}),
            Case(
                f"{path}[the outcome of another patient is not read: None]",
                hold(),
                I(robot_task(at(20, 45), task, "failed", patient="p2")),
                {path: None},
                kwargs={"patient_id": "p1"},
            ),
            Case(
                f"{path}[not in the scope of a range violation: None]",
                range_record(),
                I(robot_task(at(20, 55), task, "failed")),
                {path: None},
            ),
        ]
    out += [
        Case(
            "system.battery_low[a low-battery report in the window: True]",
            hold(),
            I(robot_state(at(20, 40), colocated=False, battery_low=True)),
            {"system.battery_low": True},
        ),
        Case(
            "system.battery_low[every report False and the robot active: False]",
            hold(),
            I(robot_state(at(20, 40), colocated=False, battery_low=False)),
            {"system.battery_low": False},
        ),
        Case(
            "system.battery_low[no report: None]",
            hold(),
            I(),
            {"system.battery_low": None},
        ),
        Case(
            "system.battery_low[False reports but a stale status entry: None]",
            hold(),
            I(
                robot_state(at(20, 40), colocated=False, battery_low=False),
                node_state(at(20, 50), "robot", "unreachable"),
            ),
            {"system.battery_low": None},
        ),
    ]

    # ---- signal quality, error code, cross-device (EX-3) ------------------------------------------
    out += [
        Case(
            "signal_quality.ecg_sqi[the lowest quality of the window]",
            hold(),
            I(
                sample(SignalId.HR_ECG, at(20, 0), value=70.0, quality=0.9),
                sample(SignalId.HR_ECG, at(20, 10), value=70.0, quality=0.6),
                sample(SignalId.HR_ECG, at(20, 20), value=70.0),
            ),
            {"signal_quality.ecg_sqi": 0.6},
        ),
        Case(
            "signal_quality.ecg_sqi[no sample carries a quality: None]",
            hold(),
            I(sample(SignalId.HR_ECG, at(20, 10), value=70.0)),
            {"signal_quality.ecg_sqi": None},
        ),
        Case(
            "signal_quality.ppg_sqi[SPO2 qualities (D-13): the lowest]",
            hold(),
            I(
                sample(SignalId.SPO2, at(20, 5), value=95.0, quality=0.7),
                sample(SignalId.SPO2, at(20, 35), value=95.0, quality=0.4),
            ),
            {"signal_quality.ppg_sqi": 0.4},
        ),
        Case(
            "signal_quality.cuff_error_code[EX-3 (a) no code, cuff frames in the window: empty string]",
            hold(),
            I(cuff_frame(at(20, 0), 1), cuff_frame(at(20, 30), 2)),
            {"signal_quality.cuff_error_code": ""},
            prof=CUFF_ONLY,
        ),
        Case(
            "signal_quality.cuff_error_code[EX-3 (b) a DEVICE_ERROR with code E1]",
            hold(),
            I(
                cuff_frame(at(20, 0), 1),
                cuff_frame(at(20, 30), 2),
                device_error(at(20, 40), "E1"),
            ),
            {"signal_quality.cuff_error_code": "E1"},
            prof=CUFF_ONLY,
        ),
        Case(
            "signal_quality.cuff_error_code[EX-3 (c) the cuff silent in the window: None]",
            hold(),
            I(),
            {"signal_quality.cuff_error_code": None},
            prof=CUFF_ONLY,
        ),
        Case(
            "signal_quality.cuff_error_code[EX-3 (d) a cuff without error codes: None]",
            hold(),
            I(cuff_frame(at(20, 0), 1), cuff_frame(at(20, 30), 2)),
            {"signal_quality.cuff_error_code": None},
            prof=profile(cuff={"seq": True}),
        ),
        Case(
            "cross_device.pulse_vs_ecg_hr_diff[EX-3 (e) a pulse of 90 against an ECG rate of 72: 18.0]",
            hold(),
            I(
                sample(SignalId.HR_ECG, at(20, 20), value=72.0),
                sample(SignalId.HR_PULSE, at(20, 30), value=90.0),
            ),
            {"cross_device.pulse_vs_ecg_hr_diff": 18.0},
        ),
        Case(
            "cross_device.pulse_vs_ecg_hr_diff[the held ECG value is too old: None]",
            hold(),
            I(
                sample(SignalId.HR_ECG, at(20, 0), value=72.0),
                sample(SignalId.HR_PULSE, at(20, 30), value=90.0),
            ),
            {"cross_device.pulse_vs_ecg_hr_diff": None},
        ),
        Case(
            "cross_device.pulse_vs_ecg_hr_diff[the maximum over the pulse samples]",
            hold(),
            I(
                sample(SignalId.HR_ECG, at(20, 20), value=72.0),
                sample(SignalId.HR_PULSE, at(20, 25), value=75.0),
                sample(SignalId.HR_PULSE, at(20, 30), value=90.0),
                sample(SignalId.HR_PULSE, at(20, 35), value=70.0),
            ),
            {"cross_device.pulse_vs_ecg_hr_diff": 18.0},
        ),
    ]

    # ---- witness fields (EX-5) ----------------------------------------------------------------------
    def wit(
        name: str,
        items: list[Any],
        present: bool | None,
        intake: bool | None,
        **extra: Any,
    ) -> Case:
        return Case(
            f"witness[EX-5 {name}]",
            int_record(),
            I(*items),
            {
                "witness.robot_present": present,
                "witness.intake_observed": intake,
                **extra,
            },
            prof=INT_ROBOT,
        )

    here = robot_state(at(20, 50), colocated=True)
    pres = lambda t, v: sample(SignalId.PRESENCE, t, value=v)
    out += [
        wit(
            "(a) presence 1 at 20:50 and 0 at 20:58",
            [here, pres(at(20, 50), 1.0), pres(at(20, 58), 0.0)],
            True,
            False,
        ),
        wit("(b) presence 0 held", [here, pres(at(20, 50), 0.0)], False, False),
        wit(
            "(c) an INTAKE event at 20:58 with presence 0",
            [here, pres(at(20, 50), 0.0), event(EventKind.INTAKE, at(20, 58), "robot")],
            False,
            True,
        ),
        wit(
            "(d) the robot arrives at 20:58 and sees the patient: coverage broken",
            [robot_state(at(20, 58), colocated=True), pres(at(20, 58), 1.0)],
            True,
            None,
        ),
        wit(
            "(e) unreachable at 20:57 after presence 1 at 20:56",
            [
                robot_state(at(20, 50), colocated=True),
                pres(at(20, 56), 1.0),
                node_state(at(20, 57), "robot", "unreachable"),
            ],
            True,
            None,
        ),
        wit(
            "(f) unreachable at 20:57 with presence 0 only",
            [
                robot_state(at(20, 50), colocated=True),
                pres(at(20, 56), 0.0),
                node_state(at(20, 57), "robot", "unreachable"),
            ],
            None,
            None,
        ),
        wit(
            "(g) co-located with no presence sample: level undefined",
            [here],
            None,
            False,
        ),
        wit("(h) never co-located", [], None, None),
        wit(
            "(i) a failed manipulation at 20:56 with presence 1",
            [
                here,
                pres(at(20, 50), 1.0),
                robot_task(at(20, 56), "manipulate", "failed"),
            ],
            True,
            None,
        ),
        wit(
            "(j) the same with an INTAKE event",
            [
                here,
                pres(at(20, 50), 1.0),
                robot_task(at(20, 56), "manipulate", "failed"),
                event(EventKind.INTAKE, at(20, 58), "robot"),
            ],
            True,
            True,
        ),
        wit(
            "(m) the level of the morning visit is not carried across the outage (ADR-054 episode rule)",
            [
                robot_state(at(6, 0), colocated=True),
                pres(at(6, 0), 0.0),
                robot_state(at(6, 10), colocated=False),
                robot_state(at(20, 50), colocated=True),
            ],
            None,
            False,
        ),
        wit(
            "(m) the same with presence 0 at 20:52",
            [
                robot_state(at(6, 0), colocated=True),
                pres(at(6, 0), 0.0),
                robot_state(at(6, 10), colocated=False),
                robot_state(at(20, 50), colocated=True),
                pres(at(20, 52), 0.0),
            ],
            False,
            False,
        ),
        wit(
            "(k) a failed identity check with presence 1",
            [
                here,
                pres(at(20, 50), 1.0),
                robot_task(at(20, 56), "witness", "success", identity_confirmed=False),
            ],
            True,
            False,
            **{"witness.identity_confirmed": False},
        ),
        wit(
            "(l) the same with presence 0: no identity reading",
            [
                here,
                pres(at(20, 50), 0.0),
                robot_task(at(20, 56), "witness", "success", identity_confirmed=False),
            ],
            False,
            False,
            **{"witness.identity_confirmed": None},
        ),
        wit(
            "(n) a confirmed identity with presence 1",
            [
                here,
                pres(at(20, 50), 1.0),
                robot_task(at(20, 56), "witness", "success", identity_confirmed=True),
            ],
            True,
            False,
            **{"witness.identity_confirmed": True},
        ),
        Case(
            "witness[a violation of range has no robot in its scope: every witness field None]",
            range_record(),
            I(here, pres(at(20, 50), 1.0)),
            {
                "witness.robot_present": None,
                "witness.identity_confirmed": None,
                "witness.intake_observed": None,
            },
            prof=INT_ROBOT,
        ),
    ]

    # ---- the fields of #evidencevector 0.2.0 (ADR-032, ADR-040, ADR-074 amendment 3) -------------------
    resolved = profile(
        cuff={**CUFF_ALL, "cuff_resolution": 1.0},
        dispenser={"content_sensing": True},
    )

    def bp(t: int, value: float) -> Any:
        return sample(SignalId.BP, t, value=value)

    def dispense(t: int, **payload: float | str | bool) -> Any:
        return event(EventKind.DISPENSE, t, "dispenser", **payload)

    out += [
        Case(
            "signal_quality.cuff_value_repeated[two equal readings of the cuff: True]",
            hold(),
            I(bp(at(20, 10), 120.0), bp(at(20, 40), 120.0)),
            {"signal_quality.cuff_value_repeated": True},
            prof=resolved,
        ),
        Case(
            "signal_quality.cuff_value_repeated[two different readings: False]",
            hold(),
            I(bp(at(20, 10), 120.0), bp(at(20, 40), 119.0)),
            {"signal_quality.cuff_value_repeated": False},
            prof=resolved,
        ),
        Case(
            "signal_quality.cuff_value_repeated[a first reading has no previous one: None]",
            hold(),
            I(bp(at(20, 40), 120.0)),
            {"signal_quality.cuff_value_repeated": None},
            prof=resolved,
        ),
        Case(
            "signal_quality.cuff_value_repeated[the profile declares no resolution: None]",
            hold(),
            I(bp(at(20, 10), 120.0), bp(at(20, 40), 120.0)),
            {"signal_quality.cuff_value_repeated": None},
            prof=CUFF_ONLY,
        ),
        Case(
            "dispenser[a release: a long interval and a positive content change (ADR-040 (2))]",
            hold(),
            I(
                dispense(
                    at(20, 50),
                    interval_since_previous_ms=43_200_000,
                    content_change=1.0,
                )
            ),
            {
                "dispenser.interval_since_previous_ms": 43_200_000,
                "dispenser.content_change": 1.0,
            },
            prof=resolved,
        ),
        Case(
            "dispenser[a bounce: a short interval and a zero content change]",
            hold(),
            I(
                dispense(
                    at(20, 50), interval_since_previous_ms=4_000, content_change=0.0
                )
            ),
            {
                "dispenser.interval_since_previous_ms": 4_000,
                "dispenser.content_change": 0.0,
            },
            prof=resolved,
        ),
        Case(
            "dispenser[an opening that reports neither key: None, None]",
            hold(),
            I(dispense(at(20, 50))),
            {
                "dispenser.interval_since_previous_ms": None,
                "dispenser.content_change": None,
            },
            prof=resolved,
        ),
    ]
    return out


ALL_CASES = cases()


def run(case: Case, registry: Any) -> dict[str, Any]:
    prof = case.prof if case.prof is not None else full_profile()
    ex = extractor(
        registry, prof, reorder_delay_ms=case.reorder_delay_ms, **case.kwargs
    )
    feed(ex, case.inputs)
    return evidence_dict(ex.evidence_for(case.record))


# ---- test 30: the derivation table, one fixture per documented row -----------------------------------


@pytest.mark.parametrize("case", ALL_CASES, ids=[c.id for c in ALL_CASES])
def test_extractor_derivation_table(case: Case, registry) -> None:  # type: ignore[no-untyped-def]
    values = run(case, registry)
    for path, expected in case.expected.items():
        assert values[path] == expected, (path, values[path])


def test_every_field_of_the_derivation_table_has_a_fixture() -> None:
    from tests.fixtures.attribution import CONTRACT_PATHS

    covered = {path for case in ALL_CASES for path in case.expected}
    assert covered >= set(CONTRACT_PATHS)


# ---- test 28 -----------------------------------------------------------------------------------


def test_extractor_channel_unavailable_is_none_not_false(registry) -> None:  # type: ignore[no-untyped-def]
    ex = extractor(
        registry, CUFF_ONLY
    )  # a capability-poor profile and no inputs at all
    values = evidence_dict(ex.evidence_for(hold_record()))
    for path in (
        "system.nav_task_failed",
        "system.manip_task_failed",
        "system.battery_low",
        "signal_quality.ecg_sqi",
        "signal_quality.ppg_sqi",
        "signal_quality.cuff_error_code",
        "cross_device.pulse_vs_ecg_hr_diff",
        "witness.robot_present",
        "witness.identity_confirmed",
        "witness.intake_observed",
        "crypto_temporal.authenticated",
        "system.seq_gap",
        "crypto_temporal.seq_repeat",
        "signal_quality.cuff_value_repeated",
        "dispenser.interval_since_previous_ms",
        "dispenser.content_change",
        "crypto_temporal.timestamp_implausible",
        "system.ble_link_quality",
        "system.qos_deadline_missed",
    ):
        assert values[path] is None, path
    # no profile: no capability is assumed, so nothing is read as a negative
    bare = extractor(registry, profile(), reorder_delay_ms=0)
    values = evidence_dict(bare.evidence_for(hold_record()))
    assert [
        p for p, v in values.items() if v is not None and not p.startswith("provenance")
    ] == []
    # a declared "denied" reading uses the representation of the Conventions: the empty string
    ex = extractor(registry, CUFF_ONLY)
    feed(ex, I(cuff_frame(at(20, 30), 1)))
    assert ex.evidence_for(hold_record()).signal_quality.cuff_error_code == ""


# ---- test 29 -----------------------------------------------------------------------------------


def test_extractor_witness_none_without_robot(registry) -> None:  # type: ignore[no-untyped-def]
    only_presence = I(sample(SignalId.PRESENCE, at(20, 56), value=1.0))
    ex = feed(extractor(registry, INT_ROBOT), only_presence)
    vec = ex.evidence_for(int_record())
    assert (
        vec.witness.robot_present,
        vec.witness.identity_confirmed,
        vec.witness.intake_observed,
    ) == (None, None, None)
    # EC-OP-7: with the robot status saying co-located, a presence sample and no intake inside the window
    withdrawn = I(
        robot_state(at(20, 50), colocated=True),
        sample(SignalId.PRESENCE, at(20, 56), value=1.0),
    )
    vec = feed(extractor(registry, INT_ROBOT), withdrawn).evidence_for(int_record())
    assert (
        vec.witness.robot_present is True and vec.witness.intake_observed is False
    )  # asserted absence
    assert vec.witness.identity_confirmed is None


# ---- test 31 -----------------------------------------------------------------------------------


def test_extractor_sequence_gap_explained_by_link_fault(registry) -> None:  # type: ignore[no-untyped-def]
    """D-3: the extractor sets the field for a gap and the integrity reading is the rule's (worked case W-15)."""
    from ralmon.attribution import HierarchicalRule

    rule = HierarchicalRule(registry)
    cuff = profile(cuff=CUFF_ALL)
    base = [
        cuff_frame(at(20, 10, 20), 1),
        cuff_frame(at(20, 12, 5), 3),
        cuff_frame(at(20, 13, 0), 4),
    ]
    link = I(*base, node_state(at(20, 11, 0), "cuff", "link_down"))
    vec = feed(extractor(registry, cuff, reorder_delay_ms=120_000), link).evidence_for(
        hold_record()
    )
    assert vec.system.seq_gap is True  # the field is set by the gap ...
    assert vec.crypto_temporal.seq_repeat is False  # ... and the integrity field is not
    assert vec.system.ble_link_quality is not None and vec.system.ble_link_quality < 1.0
    assert vec.system.node_lifecycle == {"cuff": "link_down"}
    decision = rule.decide(hold_record(), vec)
    assert (
        decision.kappa.value != "C3"
    )  # ... and it is not integrity evidence (W-15, W-15-alone)
    # a repeated value with a complete delivery ratio is integrity evidence
    repeat = I(
        *[
            cuff_frame(*pair)
            for pair in ((at(20, 10, 20), 1), (at(20, 11, 10), 2), (at(20, 12, 5), 3))
        ],
        cuff_frame(at(20, 11, 30), 2),
    )
    vec = feed(
        extractor(registry, cuff, reorder_delay_ms=120_000), repeat
    ).evidence_for(hold_record())
    assert rule.decide(hold_record(), vec).kappa.value == "C3"


# ---- test 32 -----------------------------------------------------------------------------------

BASE_INPUTS = I(
    cuff_frame(at(20, 10, 20), 1),
    cuff_frame(at(20, 12, 5), 3),
    node_state(0, "cuff", "active"),
    node_state(at(20, 40), "cuff", "link_down"),
    robot_state(at(20, 50), colocated=True),
    sample(SignalId.PRESENCE, at(20, 51), value=1.0),
    robot_task(at(20, 45), "navigate", "success"),
    sample(SignalId.HR_ECG, at(20, 20), value=70.0, quality=0.9),
)
CUTOFF_D = 120_000
CUTOFF = at(21, 0) + CUTOFF_D


@st.composite
def late_inputs(draw: Any) -> Inputs:
    out = Inputs()
    for _ in range(draw(st.integers(1, 6))):
        rx = CUTOFF + draw(st.integers(1, 6 * 3_600_000))
        t = draw(st.integers(max(0, rx - 8 * 3_600_000), rx))
        kind = draw(
            st.sampled_from(
                ["cuff", "state", "task", "verify", "presence", "error", "ecg"]
            )
        )
        if kind == "cuff":
            out.samples.append(cuff_frame(t, draw(st.integers(1, 9)), rx=rx))
        elif kind == "state":
            out.events.append(
                replace(
                    node_state(
                        t,
                        draw(st.sampled_from(["cuff", "robot"])),
                        draw(st.sampled_from(["inactive", "unreachable", "active"])),
                    ),
                    t_rx_ms=rx,
                )
            )
        elif kind == "task":
            out.events.append(
                replace(
                    robot_task(
                        t, draw(st.sampled_from(["navigate", "manipulate"])), "failed"
                    ),
                    t_rx_ms=rx,
                )
            )
        elif kind == "verify":
            out.events.append(replace(verification_failed(t, "cuff"), t_rx_ms=rx))
        elif kind == "presence":
            out.samples.append(sample(SignalId.PRESENCE, t, rx=rx, value=0.0))
        elif kind == "error":
            out.events.append(replace(device_error(t, "E9"), t_rx_ms=rx))
        else:
            out.samples.append(
                sample(SignalId.HR_ECG, t, rx=rx, value=70.0, quality=0.1)
            )
    return out


@settings(max_examples=60, deadline=None)
@given(extra=late_inputs())
def test_extractor_is_causal_property(extra: Inputs) -> None:
    registry = load_fixture_registry()
    prof = full_profile()
    record = hold_record()
    base = feed(
        extractor(registry, prof, reorder_delay_ms=CUTOFF_D), BASE_INPUTS
    ).evidence_for(record)
    both = Inputs(
        BASE_INPUTS.samples + extra.samples, BASE_INPUTS.events + extra.events
    )
    ex = feed(extractor(registry, prof, reorder_delay_ms=CUTOFF_D), both)
    ex.observe_robot_evidence(
        CUTOFF + 1, base.witness, base.system
    )  # a robot message after the cut-off
    assert ex.evidence_for(record) == base


# ---- test 33 -----------------------------------------------------------------------------------


def test_offline_equals_streaming(registry) -> None:  # type: ignore[no-untyped-def]
    from ralmon.attribution import extract_evidence

    prof = full_profile()
    inputs = Inputs(
        BASE_INPUTS.samples
        + [
            cuff_frame(at(21, 20), 5),
            cuff_frame(at(22, 10), 6),
            sample(SignalId.PRESENCE, at(22, 5), value=1.0),
        ],
        BASE_INPUTS.events
        + [
            node_state(at(21, 30), "cuff", "inactive"),
            robot_state(at(22, 0), colocated=True),
        ],
    )
    records = [hold_record(at(21, 0)), int_record(at(22, 10)), range_record(at(21, 30))]
    day = inputs.day()
    offline = extract_evidence(
        day,
        records,
        registry,
        step_ms=STEP_MS,
        reorder_delay_ms=CUTOFF_D,
        profile=to_profile(prof),
    )
    assert set(offline) == {r.instance_key for r in records}

    ex = extractor(registry, prof, reorder_delay_ms=CUTOFF_D, patient_id=day.patient_id)
    pending_samples = list(day.samples)
    pending_events = list(day.events)
    streaming = {}
    for record in sorted(records, key=lambda r: r.decided_at_ms):
        cutoff = record.decided_at_ms + CUTOFF_D
        for s in [s for s in pending_samples if s.t_rx_ms <= cutoff]:
            ex.observe_sample(s)
            pending_samples.remove(s)
        for e in [e for e in pending_events if e.t_rx_ms <= cutoff]:
            ex.observe_event(e)
            pending_events.remove(e)
        streaming[record.instance_key] = ex.evidence_for(record)
    assert streaming == offline


def test_extract_evidence_prefers_the_violated_record_of_a_key(registry) -> None:  # type: ignore[no-untyped-def]
    from ralmon.attribution import extract_evidence
    from ralmon.monitor import VerdictState

    predicted = make_record(
        "hold",
        key="hold@75600000",
        state=VerdictState.PREDICTED_VIOLATION,
        t_eval_ms=at(20, 30),
        hi=0.0,
        sigma_norm=(-1.0, 0.1),
        predicted_sigma_norm=-0.2,
    )
    violated = hold_record()
    day = I(node_state(at(20, 40), "cuff", "inactive")).day()
    out = extract_evidence(
        day,
        [predicted, violated],
        registry,
        step_ms=STEP_MS,
        reorder_delay_ms=0,
        profile=to_profile(full_profile()),
    )
    assert list(out) == ["hold@75600000"]
    assert out["hold@75600000"].system.node_lifecycle == lifecycle(
        cuff="inactive"
    )  # the cut-off of the violated record


# ---- test 34 -----------------------------------------------------------------------------------

EXTRACTOR_PARAMETERS = (
    "evidence_margin_ms",
    "evidence_grace_ms",
    "hr_coherence_max_age_ms",
    "clock_skew_max_ms",
)


@pytest.mark.parametrize("name", EXTRACTOR_PARAMETERS)
def test_extractor_requires_registry_parameters(name: str, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from ralmon.attribution import EvidenceExtractor

    with pytest.raises(RegistryError):
        EvidenceExtractor(
            registry_variant(tmp_path, drop=(name,)),
            step_ms=STEP_MS,
            reorder_delay_ms=0,
        )
    # the real registry carries only clock_skew_max_ms: there is no default value for the others
    from ralmon.spec import load_registry

    with pytest.raises(RegistryError):
        EvidenceExtractor(
            load_registry(step_ms=STEP_MS), step_ms=STEP_MS, reorder_delay_ms=0
        )


def test_extractor_does_not_require_the_rule_thresholds(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """EC-OP-13: the floors and the tolerance are read by the rule, the extractor needs only its own names."""
    from ralmon.attribution import EvidenceExtractor

    dropped = (
        "hr_coherence_tolerance",
        "ecg_sqi_floor",
        "ppg_sqi_floor",
        "ble_link_quality_floor",
    )
    EvidenceExtractor(
        registry_variant(tmp_path, drop=dropped), step_ms=STEP_MS, reorder_delay_ms=0
    )


# ---- test 35 -----------------------------------------------------------------------------------


def snapshot_parts(**kwargs: Any) -> tuple[Any, Any]:
    from ralmon.attribution import EmbodiedWitnessEvidence, SystemHealthEvidence

    witness = EmbodiedWitnessEvidence(
        robot_present=kwargs.get("robot_present"),
        identity_confirmed=kwargs.get("identity_confirmed"),
        intake_observed=kwargs.get("intake_observed"),
    )
    system = SystemHealthEvidence(
        node_lifecycle=kwargs.get("node_lifecycle"),
        diagnostics_ok=kwargs.get("diagnostics_ok"),
        liveliness_ok=kwargs.get("liveliness_ok"),
        qos_deadline_missed=kwargs.get("qos_deadline_missed"),
        ble_link_quality=None,
        battery_low=kwargs.get("battery_low"),
        nav_task_failed=kwargs.get("nav_task_failed"),
        manip_task_failed=kwargs.get("manip_task_failed"),
        seq_gap=None,  # ward-side (BLE devices only): the robot does not publish it
    )
    return witness, system


def test_extractor_merges_robot_evidence(registry) -> None:  # type: ignore[no-untyped-def]
    record = int_record()
    ex = extractor(registry, INT_ROBOT)
    before = ex.evidence_for(record)
    assert (
        before.witness.robot_present is None and before.system.nav_task_failed is None
    )  # before any message

    witness, system = snapshot_parts(
        robot_present=True,
        identity_confirmed=True,
        intake_observed=False,
        nav_task_failed=False,
        manip_task_failed=False,
        battery_low=False,
        liveliness_ok=True,
    )
    ex.observe_robot_evidence(at(20, 58), witness, system)
    vec = ex.evidence_for(record)
    assert (
        vec.witness.robot_present,
        vec.witness.identity_confirmed,
        vec.witness.intake_observed,
    ) == (True, True, False)
    assert (
        vec.system.nav_task_failed,
        vec.system.manip_task_failed,
        vec.system.battery_low,
    ) == (False, False, False)
    assert (
        vec.system.liveliness_ok is True
    )  # merged with the ward side, which also reads True
    # a record whose cut-off is before the message does not see it
    early = int_record(at(20, 57))
    assert (
        extractor_fed(registry, witness, system, at(20, 58))
        .evidence_for(early)
        .witness.robot_present
        is None
    )
    # the merge by the placement rules: an adverse reading of either side stands
    ward_lapse = I(node_state(at(20, 56), "dispenser", "unreachable"))
    ex2 = feed(extractor(registry, INT_ROBOT), ward_lapse)
    ex2.observe_robot_evidence(at(20, 58), witness, system)
    assert ex2.evidence_for(record).system.liveliness_ok is False
    robot_lapse_witness, robot_lapse_system = snapshot_parts(liveliness_ok=False)
    ex3 = extractor(registry, INT_ROBOT)
    ex3.observe_robot_evidence(at(20, 58), robot_lapse_witness, robot_lapse_system)
    assert ex3.evidence_for(record).system.liveliness_ok is False
    # what the trace can express wins for the witness fields; the snapshot fills what the trace leaves unavailable
    ex4 = feed(
        extractor(registry, INT_ROBOT),
        I(
            robot_state(at(20, 50), colocated=True),
            sample(SignalId.PRESENCE, at(20, 51), value=0.0),
        ),
    )
    ex4.observe_robot_evidence(at(20, 58), witness, system)
    assert ex4.evidence_for(record).witness.robot_present is False
    # robot-derived fields stay None for a template without the robot
    assert ex.evidence_for(range_record()).witness.robot_present is None
    assert ex.evidence_for(range_record()).system.nav_task_failed is None


def extractor_fed(registry: Any, witness: Any, system: Any, t_ms: int) -> Any:
    ex = extractor(registry, INT_ROBOT)
    ex.observe_robot_evidence(t_ms, witness, system)
    return ex


def test_robot_evidence_outside_the_window_is_not_used(registry) -> None:  # type: ignore[no-untyped-def]
    """A snapshot older than the evidence window of the record (a stale robot message) is not evidence for it."""
    witness, system = snapshot_parts(robot_present=True)
    ex = extractor(registry, INT_ROBOT)
    ex.observe_robot_evidence(at(8, 0), witness, system)
    assert ex.evidence_for(int_record()).witness.robot_present is None


# ---- test 36 -----------------------------------------------------------------------------------


def test_robot_unavailable_makes_robot_fields_none(registry) -> None:  # type: ignore[no-untyped-def]
    """Placement S4. The facts asserted earlier in the window stay (EC-OP-4, note 3 of Field semantics)."""
    items = [
        robot_state(at(20, 50), colocated=True, battery_low=False),
        node_state(at(20, 56), "robot", "unreachable"),
    ]
    vec = feed(extractor(registry, INT_ROBOT), I(*items)).evidence_for(int_record())
    assert vec.system.liveliness_ok is False
    assert vec.system.node_lifecycle == {"dispenser": "active", "robot": "unreachable"}
    for path, value in evidence_dict(vec).items():
        if path.startswith("witness.") or path in (
            "system.battery_low",
            "system.nav_task_failed",
            "system.manip_task_failed",
        ):
            assert value is None, path
    # an outcome event or a True presence seen before the outage is a fact and stays
    items += [
        robot_task(at(20, 54), "manipulate", "failed"),
        sample(SignalId.PRESENCE, at(20, 55), value=1.0),
    ]
    vec = feed(extractor(registry, INT_ROBOT), I(*items)).evidence_for(int_record())
    assert vec.system.manip_task_failed is True
    assert vec.witness.robot_present is True
    assert vec.witness.intake_observed is None


def test_robot_excluded_extractor_for_ablation_a4(registry) -> None:  # type: ignore[no-untyped-def]
    """EC-OP-20: the extractor with the robot sources excluded (the full A4)."""
    items = I(
        robot_state(at(20, 50), colocated=True),
        sample(SignalId.PRESENCE, at(20, 51), value=1.0),
        robot_task(at(20, 55), "navigate", "failed"),
        node_state(at(20, 56), "robot", "unreachable"),
        node_state(at(20, 40), "dispenser", "inactive"),
    )
    full = feed(extractor(registry, INT_ROBOT), items).evidence_for(int_record())
    assert full.system.liveliness_ok is False and full.witness.robot_present is True
    witness, system = snapshot_parts(
        robot_present=True, nav_task_failed=True, liveliness_ok=False
    )
    ex = feed(extractor(registry, INT_ROBOT, exclude_robot=True), items)
    ex.observe_robot_evidence(at(20, 58), witness, system)
    vec = ex.evidence_for(int_record())
    assert vec.witness == type(vec.witness)(None, None, None)
    assert vec.system.nav_task_failed is None and vec.system.battery_low is None
    assert vec.system.liveliness_ok is True  # recomputed over the device nodes
    assert vec.system.node_lifecycle == {"dispenser": "inactive"}
    # the ward-side fields are unchanged
    assert (
        vec.crypto_temporal == full.crypto_temporal
        and vec.signal_quality == full.signal_quality
    )


def test_extractor_uses_the_anchor_of_a_plan_instance(registry) -> None:  # type: ignore[no-untyped-def]
    """A plan instance key is free text: the anchor then comes from the call or the plan (EC D-1)."""
    ex = feed(
        extractor(registry, full_profile()),
        I(node_state(at(20, 10), "cuff", "inactive")),
    )
    record = make_record(
        "hold",
        key="hold@2026-01-01T21:00",
        decided_at_ms=at(21, 0),
        hi=-5.0,
        sigma_norm=(-0.25, -0.25),
    )
    assert ex.evidence_for(
        record, anchor_ms=at(21, 0)
    ).system.node_lifecycle == lifecycle(cuff="inactive")
    # without an anchor the decision time of a record decided at its anchor step is used
    assert ex.evidence_for(record).system.node_lifecycle == lifecycle(cuff="inactive")


_ = (Callable,)  # keep the typing import used by the table helpers


# ---- agreement with the monitor on the witness fields (EX-9, ADR-054 episode rule) --------------------------


def _agreement_scenario(
    first: bool,
    reports: list[tuple[int, bool]],
    presence: list[tuple[int, float]],
    intakes: list[int],
    dispense: int,
) -> tuple[Inputs, Any]:
    """The same robot trace for the monitor and for the extractor (state active, ``colocated`` reports)."""
    from tests.monitor.helpers import Inputs as MonitorInputs
    from tests.monitor.helpers import evt, smp

    shared = Inputs()
    shared.events.append(robot_state(0, colocated=first))
    shared.events.extend(robot_state(t, colocated=flag) for t, flag in reports)
    shared.samples.extend(sample(SignalId.PRESENCE, t, value=v) for t, v in presence)
    mon_in = MonitorInputs()
    mon_in.events.append(evt("dispense", dispense, source="dispenser"))
    mon_in.events.extend(replace(e, t_rx_ms=e.t_device_ms) for e in shared.events)
    mon_in.events.extend(evt("intake", t, source="robot") for t in intakes)
    mon_in.samples.extend(smp("presence", t, v) for t, v in presence)
    shared.events.extend(event(EventKind.INTAKE, t, "robot") for t in intakes)
    return shared, mon_in


@settings(max_examples=150, deadline=None)
@given(
    first=st.booleans(),
    flips=st.lists(
        st.tuples(st.integers(6 * 60, 21 * 60 - 1), st.booleans()), max_size=4
    ),
    samples=st.lists(
        st.tuples(st.integers(6 * 60, 21 * 60 - 1), st.sampled_from([0.0, 1.0])),
        max_size=4,
    ),
    intake_minute=st.one_of(st.none(), st.integers(20 * 60 + 55, 21 * 60)),
)
def test_extractor_agrees_with_the_monitor_on_the_witness(
    first: bool,
    flips: list[tuple[int, bool]],
    samples: list[tuple[int, float]],
    intake_minute: int | None,
) -> None:
    """EX-9 invariants I1 to I4 for the pair (monitor verdict of INT, extractor witness fields).

    Differences of WS05-T11 that the generator avoids: the first report is at 00:00 (H-INIT), and the robot state is
    always ``active`` (the monitor reads only ``colocated``).
    """
    from tests.monitor.helpers import drive, final, make_monitor

    registry = load_fixture_registry()
    dispense = at(21, 0)
    reports = sorted((m * 60_000, flag) for m, flag in flips)
    presence = sorted((m * 60_000, value) for m, value in samples)
    intakes = [] if intake_minute is None else [intake_minute * 60_000]
    shared, mon_in = _agreement_scenario(first, reports, presence, intakes, dispense)
    mon = make_monitor()
    records = drive(mon, mon_in, 21 * 60 + 1)
    verdict = final(records, f"int@{dispense}")
    vec = feed(extractor(registry, INT_ROBOT), shared).evidence_for(
        int_record(dispense)
    )
    present, intake = vec.witness.robot_present, vec.witness.intake_observed
    marker = verdict.undecidable or ""
    if verdict.state.value == "violated":
        assert present is False and intake in (False, None)  # I1
    if present is False and intake is False:
        assert verdict.state.value == "violated"  # I2 (no auth sample in the trace)
    if verdict.state.value == "pending" and "channel_unavailable" in marker:
        assert present is not False and intake is not False  # I3
    if verdict.state.value == "pending" and "value_undefined:presence" in marker:
        assert present is not False  # I4


# ---- a forged sequence number must not cost memory proportional to its size (review blocker 1) ----------------


@pytest.mark.parametrize("forged", [4_000_000_000, 10**12])
def test_forged_sequence_number_is_counted_not_materialised(
    forged: int, registry
) -> None:  # type: ignore[no-untyped-def]
    """A naive forger that jumps far ahead (EX-1 (m)) gives the ratio by arithmetic: 3 values present in the span."""
    items = I(
        cuff_frame(at(20, 10), 1),
        cuff_frame(at(20, 20), 2),
        cuff_frame(at(20, 41), forged),
    )
    vec = feed(
        extractor(registry, CUFF_ONLY, reorder_delay_ms=120_000), items
    ).evidence_for(hold_record())
    assert vec.system.ble_link_quality == pytest.approx(3 / forged)
    assert vec.system.seq_gap is True
    assert vec.crypto_temporal.seq_repeat is False


@pytest.mark.parametrize(
    ("seqs", "ratio", "flag"),
    [
        ((1, 2, 3, 4), 1.0, False),
        ((1, 2, 4), 0.75, True),
        ((1, 2, 3, 6), 4 / 6, True),
        (
            (5, 6, 7),
            1.0,
            False,
        ),  # the base is the smallest value of the window minus one
        ((7, 9), 2 / 3, True),
    ],
)
def test_small_range_sequence_results_are_unchanged(
    seqs, ratio, flag, registry
) -> None:  # type: ignore[no-untyped-def]
    items = I(*[cuff_frame(at(20, 10) + 60_000 * i, s) for i, s in enumerate(seqs)])
    vec = feed(
        extractor(registry, CUFF_ONLY, reorder_delay_ms=120_000), items
    ).evidence_for(hold_record())
    assert vec.system.ble_link_quality == pytest.approx(ratio)
    assert vec.system.seq_gap is flag
    assert vec.crypto_temporal.seq_repeat is False


# ---- review minors --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_quality_and_pulse_values_are_skipped_in_any_order(
    bad: float, registry
) -> None:  # type: ignore[no-untyped-def]
    """A non-finite value is a defect of the source, not a reading: min and max must not depend on arrival order."""
    import itertools

    ppg = [
        sample(SignalId.SPO2, at(20, 5), value=95.0, quality=bad),
        sample(SignalId.SPO2, at(20, 35), value=95.0, quality=0.2),
    ]
    pulses = [
        sample(SignalId.HR_ECG, at(20, 20), value=72.0),
        sample(SignalId.HR_PULSE, at(20, 25), value=bad),
        sample(SignalId.HR_PULSE, at(20, 30), value=90.0),
    ]
    seen = set()
    for perm in itertools.permutations(ppg + pulses):
        ex = extractor(registry)
        for s in perm:
            ex.observe_sample(s)
        vec = ex.evidence_for(hold_record())
        seen.add((vec.signal_quality.ppg_sqi, vec.cross_device.pulse_vs_ecg_hr_diff))
    assert seen == {(0.2, 18.0)}


def test_an_anchor_after_the_decision_time_gives_no_witness_reading(registry) -> None:  # type: ignore[no-untyped-def]
    """An empty witness window is no data, not a denial: robot_present and intake_observed stay None."""
    items = I(
        robot_state(at(20, 50), colocated=True),
        sample(SignalId.PRESENCE, at(20, 51), value=0.0),
    )
    ex = feed(extractor(registry, INT_ROBOT), items)
    assert (
        ex.evidence_for(int_record()).witness.robot_present is False
    )  # a normal window reads the level
    vec = ex.evidence_for(
        int_record(), anchor_ms=at(21, 30)
    )  # anchor after the decision time
    assert (
        vec.witness.robot_present,
        vec.witness.identity_confirmed,
        vec.witness.intake_observed,
    ) == (None, None, None)


def test_missing_registry_names_are_reported_in_one_message(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from ralmon.attribution import EvidenceExtractor, HierarchicalRule
    from ralmon.spec import load_registry

    real = load_registry(step_ms=STEP_MS)
    with pytest.raises(RegistryError) as info:
        EvidenceExtractor(real, step_ms=STEP_MS, reorder_delay_ms=0)
    message = str(info.value)
    for name in ("evidence_margin_ms", "evidence_grace_ms", "hr_coherence_max_age_ms"):
        assert name in message
    assert "clock_skew_max_ms" not in message  # it exists
    assert "OPF-6" in message and "docs/formal/08-consistency-review.md" in message
    assert "hypertension.yaml" in message
    with pytest.raises(RegistryError) as info:
        HierarchicalRule(real)
    message = str(info.value)
    for name in (
        "hr_coherence_tolerance",
        "ecg_sqi_floor",
        "ppg_sqi_floor",
        "ble_link_quality_floor",
    ):
        assert name in message
    assert "OPF-6" in message
