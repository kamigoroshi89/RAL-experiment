"""Where B5 fails on this problem (WS06-T06; analisi section 5.4 B5 and section 10 objection 2).

FIXTURE-ONLY numbers: the band 110 to 140 mmHg, the scale 20 mmHg, one dose and the residuals below are
illustrative and unverified (analisi sections 4.1 to 4.3); they demonstrate mechanisms and are not clinical claims.
Coverage statements read "marginal over patient episodes under exchangeability". ``step_ms`` is 60 000 and
``reorder_delay_ms`` is 0. The tests do not tune B5 to fail: every B5 setting is the one of the control in
``test_b5_conformal_stl.py``; only the data change.

The micro-scenarios are two-layered. The first layer uses the real ``SplitConformal`` with hand-written episodes
(the mechanism). The second runs ``B5ConformalSTL`` itself on days built to give the same residuals (the effect on
the detections of the baseline).
"""

from __future__ import annotations

import dataclasses
import math
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from ralmon.attribution import Detection
from ralmon.baselines.base import TimingConfig
from ralmon.baselines.raw_robustness import make_evaluator
from ralmon.conformal import CalibrationEpisode, SplitConformal
from ralmon.signals import EventKind
from ralmon.spec import (
    RobustnessUnit,
    Template,
    TemplateId,
    TemplateInstance,
    normalise,
)
from tests.baselines.conftest import make_care_plan, make_instance
from tests.baselines.test_b5_conformal_stl import (
    ACT,
    LENGTH,
    LIMIT,
    STEP,
    Evaluation,
    FixedCalibrator,
    aggregate_raw,
    bench,
    calibration_days,
    dispense_day,
    evt,
    make_b5,
    observed,
    pairs,
    run,
    smp,
    templ,
    threshold_factory,
    train_days,
)

NOTES = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "plan"
    / "workstreams"
    / "WS06-baselines"
    / "notes"
)

SPARSE_RESIDUALS = (
    -50.0,
    -20.0,
    20.0,
    50.0,
) * 5  # five copies each, mmHg (test-local spread)
DENSE_RESIDUALS = (-5.0, -2.0, 2.0, 5.0) * 5


def episodes(
    residuals: tuple[float, ...],
    template: TemplateId = TemplateId.RESP,
    sigma_hat: float = 0.0,
) -> list[CalibrationEpisode]:
    return [
        CalibrationEpisode(f"p{i}", 0, template, sigma_hat, sigma_hat + r)
        for i, r in enumerate(residuals)
    ]


# ---- 14. sparse sampling: the calibrated region never leaves the safe region ---------------------------------


def test_failure_sparse_sampling_region_never_exits_safe_region() -> None:
    """With about five pressure measurements a day the gap between samples is hours and the forecast residuals are wide
    (analisi 4.3); the one-sided conformal constant is then as large as the whole excursion that matters.

    Hand derivation: ``n = 20``, ``alpha = 0.1``: ``k = ceil(21 * 0.9) = 19``. Sorted, the scores are five of -50,
    five of -20, five of +20, five of +50, so the 19th is +50 (``q = 50``); dense residuals (-5, -2, 2, 5) give
    ``q = 5``. A predicted pressure ``bp`` has ``sigma_hat = 140 - bp`` against the band limit.
    """
    sparse = SplitConformal()
    sparse.fit(episodes(SPARSE_RESIDUALS), 0.1)
    assert sparse.quantile(0.1) == 50.0
    for bp in range(140, 191):  # sigma_hat from 0 down to -50: sigma_hat + 50 >= 0
        assert not sparse.predict(LIMIT - bp, 0.1).emitted, bp
    dense = SplitConformal()
    dense.fit(episodes(DENSE_RESIDUALS), 0.1)
    assert dense.quantile(0.1) == 5.0
    assert dense.predict(LIMIT - 150.0, 0.1).emitted  # -10 + 5 < 0

    # The same effect on the detections of B5: a dose at step ACT, the pressure stays at 150 and breaches the limit.
    deadline = (ACT + LENGTH) * STEP
    day = dispense_day(150.0, 150.0)
    sparse_b5 = make_b5(alpha=0.1)
    sparse_b5.fit(train_days(), calibration_days(SPARSE_RESIDUALS))
    # nothing at the activation step: the first detection is the measured one at the deadline (B3-like)
    assert pairs(run(sparse_b5, day)) == [(deadline, 10.0)]
    (record,) = sparse_b5.predictions
    assert (record.sigma_hat, record.quantile, record.emitted) == (-10.0, 50.0, False)
    dense_b5 = make_b5(alpha=0.1)
    dense_b5.fit(train_days(), calibration_days(DENSE_RESIDUALS))
    # -10 + 5 < 0: alert at the activation step, LENGTH steps before the measured verdict; score -(-10 + 5) = 5
    assert pairs(run(dense_b5, day)) == [(ACT * STEP, 5.0)]
    assert (ACT * STEP) < deadline


def _gap_day(rng: np.random.Generator, patient: str, gap: int, length: int) -> Any:
    """A random walk observed every ``gap`` steps; the dose falls between samples and the deadline is measured."""
    offset = int(rng.integers(0, gap)) if gap > 1 else 0
    act = 3 * gap + 1 + offset
    n = act + length
    walk = LIMIT + 3.0 + np.cumsum(np.concatenate([[0.0], rng.normal(0.0, 1.0, n)]))
    samples = [
        smp("bp", k, float(walk[k])) for k in range(n + 1) if k % gap == 0 and k <= act
    ]
    samples.append(smp("bp", n, float(walk[n])))  # the measurement at the deadline
    return observed(samples, [evt(EventKind.DISPENSE, act)], patient=patient)


def test_failure_sparse_sampling_quantile_grows_with_the_gap() -> None:
    """A random walk observed every ``gap`` steps: the residual of the held value against the next measurement widens
    with the time since the last sample, so the calibrated constant grows with the gap. ``default_rng(0)``. The
    alert rates are not compared: the walk also drifts further from its start, which changes the population."""
    quantiles: dict[int, float] = {}
    length = 20
    for gap in (1, 40, 160):
        rng = np.random.default_rng(0)
        calib = [bench(_gap_day(rng, f"c{i}", gap, length)) for i in range(300)]
        b5 = make_b5(alpha=0.1, evaluator_factory=threshold_factory(length=length))
        b5.fit(train_days(), calib)
        run(b5, _gap_day(rng, "t", gap, length))
        (record,) = b5.predictions
        assert record.quantile is not None
        quantiles[gap] = record.quantile
    assert quantiles[1] < quantiles[40] < quantiles[160]


def test_failure_small_calibration_set_never_emits() -> None:
    """``n = 10``, ``alpha = 0.05``: ``k = ceil(11 * 0.95) = 11 > n``, so the constant is infinite and nothing is
    predicted, however wide the excursion. Reported by the counters, not hidden (B5-deviations D19)."""
    b5 = make_b5(alpha=0.05)
    b5.fit(
        train_days(),
        calibration_days((-3.0, -1.0, 0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0)),
    )
    out = run(b5, dispense_day(250.0, 250.0))  # rho_hat = -110
    (record,) = b5.predictions
    assert record.quantile == math.inf and record.emitted is False
    assert [t for t, _ in pairs(out)] == [
        (ACT + LENGTH) * STEP
    ]  # measured verdict at the deadline only


# ---- 15. events and counters have no predictive part -----------------------------------------------------


class LateEvaluator:
    """Open until ``decide_step``, then ``value`` (FIXTURE-ONLY)."""

    def __init__(self, unit: RobustnessUnit, decide_step: int, value: float) -> None:
        self.unit = unit
        self._decide = decide_step
        self._value = value

    def reset(self, instance: TemplateInstance) -> None:
        pass

    def step(self, t_ms: int, values: Mapping[str, float | None]) -> float | None:
        return self._value if t_ms // STEP >= self._decide else None


class CountingForecaster:
    name = "counting"
    model_version = "counting-1"
    supported_signals = frozenset({"bp", "meas"})

    def __init__(self) -> None:
        self.calls = 0

    def fit(self, train_days: Any) -> None:
        pass

    def predict(
        self, history: Any, t_ms: int, horizon_ms: int, *, signal: str | None = None
    ) -> Any:
        self.calls += 1
        raise AssertionError("B5 asked the forecaster for an event template")


def test_failure_sparse_sampling_no_predictive_part_for_event_templates() -> None:
    """COUNT, SCHED and INT are events and counters: the trajectory model of the paper (real-valued states, Section 2,
    p. 4) has no event predictor, so B5 has no prediction for them and decides only on the measured prefix."""
    decide = 8
    templates = templ(TemplateId.SCHED, TemplateId.COUNT, TemplateId.INT)

    def factory(
        template: Template, registry: Any, step_ms: int, anchor_kind: str | None
    ) -> Any:
        return LateEvaluator(template.unit, decide, -5.0)

    forecaster = CountingForecaster()
    b5 = make_b5(
        aggregation="per_template",
        templates=templates,
        forecaster=forecaster,
        evaluator_factory=factory,
        calibrator_factory=lambda: FixedCalibrator(
            -1e9
        ),  # would alert at any prediction
        timing=TimingConfig(STEP, 0, 10 * STEP),  # the run reaches the decision step
    )
    b5.fit(train_days(), [])
    plan = make_care_plan([make_instance(TemplateId.SCHED, "sched@3", {}, 3 * STEP)])
    day = observed([smp("bp", 0, 100.0)], [evt(EventKind.DISPENSE, 2)])
    out = b5.run(day, plan, None)
    assert forecaster.calls == 0
    assert b5.predictions == ()
    assert len(out) == 3 and {d.t_ms for d in out} == {
        decide * STEP
    }  # nothing before the decision step
    assert all(d.score == 5.0 and d.label is None for d in out)


# ---- 16 and 17. mixed units ------------------------------------------------------------------------------------


def test_failure_mixed_units_raw_min_masks_dose_violation() -> None:
    """Twenty conjunction episodes in mmHg-sized units: ``sigma_hat = 10`` and ``sigma_true`` alternating 18 and 2
    (residuals +8 and -8). ``n = 20``, ``alpha = 0.1``: ``k = 19``, ``q = 8``. A dose over the limit has raw
    robustness -1: ``-1 + 8 > 0``, no alert. Calibrated for the dose template in its own units (scale 1, residuals
    +0.5 and -0.5, ``q = 0.5``), ``normalise(-1, 1) = -1`` and ``-1 + 0.5 < 0``: alert."""
    pooled = SplitConformal()
    pooled.fit(
        [
            CalibrationEpisode(
                f"p{i}", 0, TemplateId.RESP, 10.0, 18.0 if i % 2 == 0 else 2.0
            )
            for i in range(20)
        ],
        0.1,
    )
    assert pooled.quantile(0.1) == 8.0
    assert not pooled.predict(-1.0, 0.1).emitted

    own = SplitConformal()
    own.fit(
        [
            CalibrationEpisode(
                f"p{i}", 0, TemplateId.COUNT, 0.5, 1.0 if i % 2 == 0 else 0.0
            )
            for i in range(20)
        ],
        0.1,
    )
    assert own.quantile(0.1) == 0.5
    sigma = normalise(-1.0, 1.0)
    assert sigma == -1.0
    assert own.predict(sigma, 0.1).emitted

    # The pooled calibrator of the variant "B5" sees only the templates with a predictive part, that is RESP: the
    # pipeline cannot reproduce the masking of the predicted decision until a second template has a path. What the
    # pipeline does show is the effect of the minimum on the measured decision (next test).


def test_failure_mixed_units_raw_min_misranks_severity() -> None:
    evaluations = [
        Evaluation(
            "count@1", TemplateId.COUNT, -1.0, "measured"
        ),  # one dose over the limit
        Evaluation(
            "range@1", TemplateId.RANGE, -12.0, "measured"
        ),  # 12 mmHg outside the band
    ]
    (group,) = aggregate_raw(evaluations, "conjunction")
    assert (
        group.value == -12.0 and group.template is TemplateId.RANGE
    )  # the raw minimum is the range instance
    scales = {
        TemplateId.RANGE: 20.0,
        TemplateId.COUNT: 1.0,
    }  # 20 mmHg, 1 dose (illustrative)
    scaled = {e.template: normalise(e.value, scales[e.template]) for e in evaluations}
    assert scaled == {TemplateId.RANGE: pytest.approx(-0.6), TemplateId.COUNT: -1.0}
    assert (
        min(scaled, key=lambda t: scaled[t]) is TemplateId.COUNT
    )  # with a scale the minimum is the count instance

    # on the detections: one detection scored 12 for the conjunction; the dose violation, the more severe one once the
    # units are scaled, has no detection of its own
    values = {TemplateId.HOLD: -12.0, TemplateId.COUNT: -1.0}

    def factory(
        template: Template, registry: Any, step_ms: int, anchor_kind: str | None
    ) -> Any:
        return LateEvaluator(template.unit, 2, values[template.id])

    day = observed([smp("bp", 0, 100.0)], [evt(EventKind.DISPENSE, 2)])
    for aggregation, expected in (
        ("conjunction", [(2 * STEP, 12.0)]),
        ("per_template", [(2 * STEP, 1.0), (2 * STEP, 12.0)]),
    ):
        b5 = make_b5(
            aggregation=aggregation,
            templates=templ(TemplateId.HOLD, TemplateId.COUNT),
            evaluator_factory=factory,
        )
        b5.fit(train_days(), [])
        assert pairs(run(b5, day)) == expected


# ---- 18. no attribution ----------------------------------------------------------------------------------------


def _bp152_day(faulty: bool) -> Any:
    samples = [smp("bp", 5, 152.0)]
    events = [evt(EventKind.MEASUREMENT, 5)]
    if faulty:
        samples.append(smp("cuff_health", 5, 0.0))
        events.append(
            evt(EventKind.DEVICE_ERROR, 5, source="cuff", payload={"code": 7})
        )
    return observed(samples, events)


def test_failure_no_attribution_same_range_detection_for_c1_and_c2_days() -> None:
    assert {f.name for f in dataclasses.fields(Detection)} == {"t_ms", "label", "score"}
    clean, faulty = _bp152_day(False), _bp152_day(True)
    b5 = make_b5(
        templates=templ(TemplateId.RANGE),
        evaluator_factory=make_evaluator,
        alpha=0.2,
    )
    b5.fit(train_days(), [bench(clean)])
    plan = make_care_plan()
    out_clean = b5.run(clean, plan, None)
    out_faulty = b5.run(faulty, plan, {"cuff": object()})  # type: ignore[dict-item]
    # RANGE margin min(152 - 110, 140 - 152) = -12 at the measurement step in both days
    assert [(d.t_ms, d.score, d.label) for d in out_clean] == [(5 * STEP, 12.0, None)]
    assert [(d.t_ms, d.score, d.label) for d in out_faulty] == [(5 * STEP, 12.0, None)]
    assert (
        out_clean == out_faulty
    )  # the same detection for a true excursion and for a faulty cuff

    # with the system template as well the faulty cuff changes the score or adds a detection, but nothing says why
    largest = (
        sys.float_info.max
    )  # a failed Boolean guard has robustness -inf: the score saturates (D20)
    for aggregation, expected_clean, expected_faulty in (
        ("conjunction", [(5 * STEP, 12.0)], [(5 * STEP, largest)]),
        (
            "per_template",
            [(5 * STEP, 12.0)],
            [(5 * STEP, 12.0), (5 * STEP, largest)],
        ),
    ):
        both = make_b5(
            aggregation=aggregation,
            templates=templ(TemplateId.RANGE, TemplateId.SYS),
            evaluator_factory=make_evaluator,
            alpha=0.2,
        )
        both.fit(train_days(), [bench(clean)])
        got_clean, got_faulty = (
            both.run(clean, plan, None),
            both.run(faulty, plan, None),
        )
        assert pairs(got_clean) == expected_clean
        assert pairs(got_faulty) == expected_faulty
        assert all(d.label is None for d in (*got_clean, *got_faulty))


# ---- 19. the analysis note ---------------------------------------------------------------------------------------


def test_failure_analysis_note_lists_all_modes() -> None:
    text = (NOTES / "B5-failure-analysis.md").read_text(encoding="utf-8")
    parts = re.split(r"^## (.+)$", text, flags=re.MULTILINE)
    sections = {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}
    for heading in (
        "Setup and reproduction",
        "Sparse sampling",
        "Mixed units",
        "No attribution",
        "Other differences that are not failures",
        "Control: where B5 works",
        "Benchmark-scale evidence",
        "Wording for the paper",
    ):
        assert heading in sections, heading
    order = [h for h in sections]
    assert order == [
        "Setup and reproduction",
        "Sparse sampling",
        "Mixed units",
        "No attribution",
        "Other differences that are not failures",
        "Control: where B5 works",
        "Benchmark-scale evidence",
        "Wording for the paper",
    ]
    own_tests = set(
        re.findall(
            r"^def (test_\w+)",
            Path(__file__).read_text(encoding="utf-8"),
            flags=re.MULTILINE,
        )
    )
    for heading in ("Sparse sampling", "Mixed units", "No attribution"):
        cited = set(re.findall(r"test_\w+", sections[heading]))
        assert cited & own_tests, heading
    assert (
        "test_b5_control_dense_exchangeable_days" in sections["Control: where B5 works"]
    )
