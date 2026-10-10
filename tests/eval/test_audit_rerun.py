"""The fairness audit re-run on the detectors that ``build_detector`` builds (WS06-T07 conclusion, review round 1).

ILLUSTRATIVE, UNVERIFIED, FIXTURE-ONLY: the days are the mini benchmark of ``tests/fixtures/eval`` and the registry is
the fixture registry. The audit as delivered certifies the fixture configuration of ``tests/baselines/conftest.py``; this
test runs the same machinery (``ralmon.baselines.audit.run_audit``) on B1 to B5 as the runner configures them (one timing
equal to the ``MonitorConfig``, the same forecaster class, the same ``plan_for_day``) with days whose latent trace and
ground truth raise on access, and on the proposed method wired the same way. It lives outside ``src/`` because
``ralmon.eval`` may not import ``ralmon.baselines.audit`` (``tests/test_layering.py``).
"""

from __future__ import annotations

from typing import Any

import pytest

from ralmon.baselines.audit import AuditDays, ProposedMethod, run_audit
from ralmon.benchmark import open_benchmark
from ralmon.conformal import SplitConformal
from ralmon.eval.runner import (
    _ObservedOnlyDay,
    build_detector,
    load_experiment,
    make_environment,
)
from ralmon.monitor import PersistenceForecaster
from tests.eval.helpers import SMOKE, smoke_document, write_config

BASELINES = ("B1", "B2", "B3", "B4", "B5")


@pytest.fixture(scope="module")
def audit() -> Any:
    import tempfile
    from pathlib import Path

    doc = smoke_document()
    doc["detectors"] = list(BASELINES)
    doc["run_options"]["detector_params"] = {
        **doc["run_options"]["detector_params"],
        # FIXTURE-ONLY operating parameters of B2 (test values, not tuned)
        "B2": {"z_threshold": 3.0, "score_quantile": 0.9, "feature_step_ms": 3_600_000},
    }
    with tempfile.TemporaryDirectory() as tmp:
        config, options = load_experiment(write_config(Path(tmp) / "c.yaml", doc))
    env = make_environment(config, options, 0)
    reader = open_benchmark(config.benchmark_manifest, view="observed")
    train = [
        _ObservedOnlyDay(reader.observed(p, d)) for p in ("p01", "p02") for d in (0, 1)
    ]
    calib = [
        _ObservedOnlyDay(reader.observed(p, d)) for p in ("p03", "p04") for d in (0, 1)
    ]
    day = reader.observed("p05", 0)
    plan = env.plan_for_day(day)
    detectors = [build_detector(n, env, alpha=0.5) for n in BASELINES]
    assert env.monitor is not None
    proposed = ProposedMethod(
        env.monitor,
        env.templates,
        PersistenceForecaster(env.monitor.step_ms),
        env.plan_for_day,
        SplitConformal,
    )
    report = run_audit(
        detectors,
        AuditDays(train, calib, day),
        plan,
        env.registry,
        templates=env.templates,
        proposed=proposed,
    )
    return report, detectors


def test_audit_finds_no_problem_in_the_detectors_the_runner_builds(audit: Any) -> None:
    report, _ = audit
    assert report.problems == ()


def test_the_detectors_share_one_timing_equal_to_the_monitor_configuration(
    audit: Any,
) -> None:
    _, detectors = audit
    config, _ = load_experiment(SMOKE)
    assert config.monitor is not None
    timings = {(d.timing.step_ms, d.timing.reorder_delay_ms) for d in detectors}
    assert timings == {(config.monitor.step_ms, config.monitor.reorder_delay_ms)}
    assert len({d.timing.tail_ms for d in detectors}) == 1


def test_no_baseline_reads_a_latent_trace_or_a_ground_truth(audit: Any) -> None:
    report, _ = audit
    for name, trace in report.traces.items():
        assert "latent" not in trace.all_fields, name
        assert "ground_truth" not in trace.all_fields, name
        assert trace.by_exception == 0 and trace.denied == 0, name


def test_the_baselines_are_fitted_on_the_training_days_only(audit: Any) -> None:
    _, detectors = audit
    for detector in detectors:
        assert detector.access_policy.calib_latent is False


def test_the_audit_covered_every_detector_and_the_proposed_method(audit: Any) -> None:
    report, detectors = audit
    assert set(report.traces) == {d.name for d in detectors} | {"ours"}
    assert len(detectors) == len(BASELINES)
    for name, trace in report.traces.items():
        assert trace.n_detections >= 0
        assert "observed" in trace.all_fields or trace.timing is not None, name
