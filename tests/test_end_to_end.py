"""End to end: an observed trace to attributed alerts (WS05-T08 tests 19 to 22).

The chain is ``run_offline`` (the predictive monitor), ``extract_evidence`` and ``RuleAttributor.attribute_all``.
FIXTURE-ONLY: the attribution fixture registry (the F0 table plus the seven names that the real registry lacks,
open point OPF-6; the attribution package refuses the real registry, so a test that attributes cannot use it),
the calibrator fixture C-1 of ``conformal.yaml`` and the stub forecaster of the golden day. Nothing is a
clinical value and nothing is clinically validated. Time labels convert as ``t_ms = (60 * hh + mm) * 60000``.

Deviations from the golden day, all stated here and in the Notes of WS05-T08:

* The golden day warns once, at the designated instant 12:10 (20 minutes before the deadline, hypothesis H-W11);
  the monitor of this task predicts once, at activation (ADR-060, WS05 decision D6), so the warning of
  ``sched@43200000`` is issued at 12:00. The test compares the template, the cause, the severity, the kind and
  the value of rho, the explanation template and the instance key, as the task asks; ``t_ms`` is not compared.
* The golden day uses the per-test level 0.2 (calibrator C-1, ``q = 0.09``). The five SCHED tests of the day
  need ``alpha_total = 1.0`` for that level (hypothesis H-W14: a vacuous bound, and ``MonitorConfig.alpha`` must
  lie in (0, 1)), so the run uses ``alpha = 0.5``, the per-test level 0.1 and ``q = 0.15``: the severity of the
  predicted alert is ``sigma_hat + 0.15`` and not ``sigma_hat + 0.09``, ``Rho.alpha`` is 0.1 and not 0.2, and
  ``rho`` is 0.9 either way (all nine scores are below ``-sigma_hat``). The golden arithmetic at the level 0.2 is
  checked on the calibrator alone.
"""

from __future__ import annotations

from typing import Any

import pytest

from ralmon.attribution import AttributedCause, Detection, EvidenceExtractor
from ralmon.monitor import MonitorConfig, VerdictState
from ralmon.spec import RhoKind, TemplateId
from tests.fixtures.attribution import hms
from tests.fixtures.monitor.predictive import StubForecaster, calibrator
from tests.fixtures.monitor.worked_day import (
    golden,
    pipeline,
    row_1500_day,
    row_1500_plan,
    worked_calibrator,
    worked_day,
    worked_forecaster,
    worked_plan,
    world,
)

PENDING = VerdictState.PENDING
PREDICTED = VerdictState.PREDICTED_VIOLATION
VIOLATED = VerdictState.VIOLATED
SATISFIED = VerdictState.SATISFIED

W = world()
DOC = golden()
SIGMA_HAT = -600_000 / 1_800_000
Q_AT_PER_TEST_LEVEL = (
    0.15  # C-1 at the per-test level 0.1: the 9th smallest of nine scores
)


def config(*, predictive: bool = True, alpha: float | None = 0.5) -> MonitorConfig:
    return MonitorConfig(
        60_000,
        0,
        predictive,
        alpha if predictive else None,
        "likely",
        W.registry.version(),
    )


def run_worked(**kwargs: Any) -> Any:
    return pipeline(
        worked_day(),
        worked_plan(W.registry),
        config(**kwargs),
        worked_calibrator("v1"),
        worked_forecaster(),
        W,
    )


@pytest.fixture(scope="module")
def result() -> Any:
    return run_worked()


# ---------------------------------------------------------------------------------------------
# test 19
# ---------------------------------------------------------------------------------------------


def expected_alerts() -> dict[str, dict[str, Any]]:
    return {a["instance_key"]: a["expected"] for a in DOC["alerts"]}


def test_the_worked_day_has_six_alerts_in_the_golden_file() -> None:
    assert len(expected_alerts()) == 6


def test_worked_patient_day_end_to_end(result: Any) -> None:
    _records, alerts = result
    want = expected_alerts()
    # the current set: the five alerts that are open at the end of the day; the false predictive alarm
    # sched@43200000 (closed at 12:24 by its SATISFIED record) is not in it
    assert {a.xi.instance_key for a in alerts} == set(want) - {"sched@43200000"}
    by_key = {a.xi.instance_key: a for a in alerts}
    for key, expected in want.items():
        if key == "sched@43200000":
            continue
        alert = by_key[key]
        assert alert.tau.value == expected["tau"], key
        assert alert.kappa.value == expected["kappa"], key
        assert alert.label == alert.kappa
        assert alert.sigma_norm == pytest.approx(expected["sigma_norm"], abs=1e-9), key
        assert alert.rho is not None, key
        assert alert.rho.kind.value == expected["rho"]["kind"], key
        assert alert.rho.value == pytest.approx(expected["rho"]["value"], abs=1e-9), key
        assert alert.rho.guarantee == expected["rho"]["guarantee"], key
        assert alert.xi.template == expected["xi"]["template"], key
        assert alert.xi.instance_key == expected["xi"]["instance_key"]
        assert alert.verdict.value == expected["verdict"], key
        assert alert.priority == expected["priority"], key
        assert sorted(alert.root_cause_of) == sorted(expected["root_cause_of"]), key
        assert alert.caused_by == expected["caused_by"], key
        assert alert.t_ms == expected["t_ms"], key
        assert alert.score == pytest.approx(expected["score"], abs=1e-9), key


def test_the_false_predictive_alarm_is_issued_by_the_incremental_attributor_and_then_closed() -> (
    None
):
    """A3: the incremental ``update`` issues the predicted alert and closes it when the instance ends SATISFIED."""
    from ralmon.attribution import RuleAttributor, extract_evidence

    records, _ = run_worked()
    plan = worked_plan(W.registry)
    day = worked_day()
    evidence = extract_evidence(
        day,
        records,
        W.registry,
        step_ms=60_000,
        reorder_delay_ms=0,
        profile=W.profile,
        plan=plan,
    )
    key = "sched@43200000"
    before_close = [r for r in records if r.t_eval_ms < hms(12, 24)]
    attributor = RuleAttributor(W.registry, W.templates, plan=plan)
    issued = attributor.update(before_close, evidence)
    predicted = next(a for a in issued if a.xi.instance_key == key)
    expected = expected_alerts()[key]
    assert predicted.tau.value == expected["tau"] == "sched"
    assert predicted.kappa is AttributedCause.UNDETERMINED
    assert predicted.label is AttributedCause.UNDETERMINED
    assert predicted.verdict is PREDICTED
    assert predicted.rho is not None
    assert predicted.rho.kind is RhoKind.PREDICTED
    assert predicted.rho.value == pytest.approx(expected["rho"]["value"])  # 0.9
    assert predicted.rho.guarantee == expected["rho"]["guarantee"]
    assert predicted.priority == expected["priority"] == 3
    assert not predicted.xi.evidence_used
    # the issue instant is the activation of the instance (12:00), not the designated instant 12:10
    assert predicted.t_ms == hms(12, 0)
    assert predicted.sigma_norm == pytest.approx(SIGMA_HAT + Q_AT_PER_TEST_LEVEL)
    assert predicted.rho.alpha == pytest.approx(0.1)
    attributor.update(records, evidence)
    assert key in attributor.closed_predictions  # a false predictive alarm


def test_the_golden_arithmetic_of_the_predicted_alert_at_the_level_of_the_golden_day() -> (
    None
):
    cal = worked_calibrator("v1")
    assert cal.quantile(0.2) == pytest.approx(0.09)
    verdict = cal.predict(SIGMA_HAT, 0.2)
    assert verdict.emitted and verdict.rho is not None
    assert verdict.rho.value == pytest.approx(0.9) and verdict.rho.alpha == 0.2
    assert SIGMA_HAT + cal.quantile(0.2) == pytest.approx(
        -0.2433, abs=1e-4
    )  # PD-ALT-03


def test_the_monitor_reproduces_the_definitive_records_of_the_worked_day(
    result: Any,
) -> None:
    records, _ = result
    want: dict[str, tuple[str, int]] = {}
    for g in DOC["records"]:
        e = g["expected"]
        if e["state"] in ("violated", "satisfied"):
            want[g["instance_key"]] = (e["state"], e["decided_at_ms"])
    got: dict[str, tuple[str, int]] = {}
    for r in records:
        if r.state in (VIOLATED, SATISFIED) and r.instance_key not in got:
            assert r.decided_at_ms is not None
            got[r.instance_key] = (r.state.value, r.decided_at_ms)
    assert got == want
    # only the warning of the golden day is predicted, and it is closed by the measurement of 12:24
    predicted = {r.instance_key for r in records if r.state is PREDICTED}
    assert predicted == {"sched@43200000"}
    first = next(r for r in records if r.state is PREDICTED)
    assert first.t_eval_ms == hms(12, 0)
    assert first.rho is not None and first.rho.value == pytest.approx(0.9)


# ---------------------------------------------------------------------------------------------
# test 20
# ---------------------------------------------------------------------------------------------


def test_cascade_row_15_00_pipeline() -> None:
    plan = row_1500_plan(W.registry)
    forecaster = StubForecaster(
        arrival={hms(12, 30): hms(12, 32), hms(15, 0): hms(15, 45)}, version="v1"
    )
    records, alerts = pipeline(
        row_1500_day(),
        plan,
        config(alpha=0.4),
        calibrator("v1"),
        forecaster,
        W,
    )
    root_key = f"sched@{hms(15, 0)}"
    effect_key = f"resp@{hms(13, 0)}"
    first = {r.instance_key: r for r in records if r.state is VIOLATED}
    assert first[root_key].decided_at_ms == hms(15, 30)
    assert first[effect_key].decided_at_ms == hms(16, 0)
    assert first[effect_key].guard_failed == "obligation_unmet"
    # the warning at activation (15:45 is later than the deadline 15:30) is superseded by the violation
    assert any(r.state is PREDICTED and r.instance_key == root_key for r in records)
    assert {a.xi.instance_key for a in alerts} == {root_key, effect_key}
    top_level = [a for a in alerts if a.caused_by is None]
    folded = [a for a in alerts if a.caused_by is not None]
    assert len(top_level) == 1 and len(folded) == 1
    root, effect = top_level[0], folded[0]
    assert root.xi.instance_key == root_key
    assert root.kappa is AttributedCause.C2_SYSTEM  # the robot failed to navigate
    assert root.verdict is VIOLATED
    assert effect.xi.instance_key == effect_key
    assert effect.caused_by == root_key
    assert effect.kappa is AttributedCause.C2_SYSTEM
    assert tuple(root.root_cause_of) == (effect_key,)
    assert effect.tau is TemplateId.RESP


# ---------------------------------------------------------------------------------------------
# test 21
# ---------------------------------------------------------------------------------------------


def test_alerts_are_valid_detections(result: Any) -> None:
    records, alerts = result
    assert alerts
    for alert in alerts:
        assert isinstance(alert, Detection)
        own = [r for r in records if r.instance_key == alert.xi.instance_key]
        first_violated = next((r for r in own if r.state is VIOLATED), None)
        if first_violated is not None:
            assert alert.t_ms == first_violated.decided_at_ms
        else:
            first_predicted = next(r for r in own if r.state is PREDICTED)
            assert alert.t_ms == first_predicted.t_eval_ms
        assert alert.label is alert.kappa
        assert alert.score == pytest.approx(-alert.sigma_norm)
        assert alert.score >= 0.0


# ---------------------------------------------------------------------------------------------
# test 22
# ---------------------------------------------------------------------------------------------


def test_run_offline_is_deterministic() -> None:
    first_records, first_alerts = run_worked()
    second_records, second_alerts = run_worked()
    assert first_records == second_records
    assert tuple(first_alerts) == tuple(second_alerts)
    assert [a.xi.instance_key for a in first_alerts] == [
        a.xi.instance_key for a in second_alerts
    ]


def test_an_unreadable_registry_is_not_used_by_the_pipeline() -> None:
    """The chain needs the fixture registry: the real one lacks the seven names of OPF-6 (one error lists them)."""
    from ralmon.spec import RegistryError, load_registry

    real = load_registry(step_ms=60_000)
    with pytest.raises(RegistryError):
        EvidenceExtractor(real, step_ms=60_000, reorder_delay_ms=0)
