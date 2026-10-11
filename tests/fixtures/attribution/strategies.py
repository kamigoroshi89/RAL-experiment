"""Hypothesis strategies shared by the cascade and invariant tests of WS05-T07."""

from __future__ import annotations

from typing import Any

from hypothesis import strategies as st

from ralmon.monitor import VerdictState
from tests.fixtures.attribution import make_record, rho_variants

THREE = {"cuff": "active", "dispenser": "active", "robot": "active"}
CLEAN = {
    "system.node_lifecycle": THREE,
    "system.diagnostics_ok": True,
    "system.liveliness_ok": True,
    "system.qos_deadline_missed": False,
    "system.ble_link_quality": 1.0,
    "system.nav_task_failed": False,
    "system.manip_task_failed": False,
    "signal_quality.cuff_error_code": "",
    "cross_device.pulse_vs_ecg_hr_diff": 2.0,
    "crypto_temporal.authenticated": True,
    "system.seq_gap": False,
    "crypto_temporal.seq_repeat": False,
    "crypto_temporal.timestamp_implausible": False,
}
EVIDENCE_KINDS = {
    "lapse": {"system.node_lifecycle": THREE, "system.liveliness_ok": False},
    "forged": {
        "system.node_lifecycle": THREE,
        "system.liveliness_ok": False,
        "crypto_temporal.authenticated": False,
    },
    "empty": {},
    "clean": CLEAN,
}
STEP = 60_000


@st.composite
def cascade_sets(draw: Any) -> list[tuple[Any, str]]:
    """Random violated/predicted records of sched, resp and hold with an evidence kind each."""
    n = draw(st.integers(1, 7))
    out: list[tuple[Any, str]] = []
    for i in range(n):
        template = draw(st.sampled_from(["sched", "resp", "hold"]))
        decided = draw(st.integers(0, 1440)) * STEP
        state = draw(
            st.sampled_from(
                [VerdictState.VIOLATED] * 4 + [VerdictState.PREDICTED_VIOLATION]
            )
        )
        guard = None
        if template == "resp":
            guard = draw(st.sampled_from(["obligation_unmet", None]))
        elif template == "hold":
            guard = draw(st.sampled_from(["no_recent_measurement", None]))
        hi = (
            float("-inf")
            if guard is not None
            else -60_000.0
            if template == "sched"
            else -5.0
        )
        record = make_record(
            template,
            key=f"{template}@{i}",
            state=state,
            decided_at_ms=decided,
            hi=hi,
            lo=float("-inf") if template != "sched" else -1_800_000.0,
            sigma_norm=(-1.0, -0.0333 if template == "sched" else -0.25),
            guard_failed=guard,
            predicted_sigma_norm=-0.3
            if state is VerdictState.PREDICTED_VIOLATION
            else None,
            rho=rho_variants()[2]
            if state is VerdictState.PREDICTED_VIOLATION
            else None,
        )
        out.append((record, draw(st.sampled_from(sorted(EVIDENCE_KINDS)))))
    return out
