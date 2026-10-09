"""``rho`` of a VIOLATED record (docs/formal/06 sections 2.2, 2.3 and 3.2).

The kind follows the deciding sub-formula: a margin on a measured pressure is MEASURED
(``P(sigma_true < 0 | measurement)`` under a Gaussian error of standard deviation ``cuff_error_sd`` read
from the registry), every predicate over the event log or the timestamps is DETERMINISTIC. PENDING and
SATISFIED records carry no rho; the PREDICTED kind is WS05-T08. The expected numbers are recomputed
here from ``math.erf`` and a separate quadrature; the strings are the exact ones of section 2.2.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

import ralmon.monitor as m

from .helpers import (
    Inputs,
    SpyRegistry,
    by_key,
    drive,
    evt,
    hhmm,
    load_f0,
    make_monitor,
    registry_variant,
    smp,
)

REG = load_f0()
S = 6.0  # cuff_error_sd of F0 (FIXTURE-ONLY)

MEASURED_GUARANTEE = "conditional on the adequacy of the declared device error model"
MEASURED_ASSUMPTIONS = [
    "measured value equals the true value plus an independent Gaussian error with standard deviation cuff_error_sd",
    "zero bias after correction (a silent bias is not seen by rho)",
    "flat prior on the true value",
    "errors of distinct measurements are independent",
]
DET_GUARANTEE = "conditional on the integrity of the event log"
DET_ASSUMPTIONS = [
    "the predicate is evaluated on the accepted event log or timestamps without error",
    "authenticity of the events is attributed by kappa and is not covered by rho",
]


def phi(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def measure(
    inputs: Inputs,
    t: int,
    bp: float,
    *,
    health: float = 1.0,
    inflation: float = 45_000.0,
) -> None:
    inputs.events.append(evt("measurement", t, source="cuff"))
    inputs.samples.append(smp("bp", t, bp))
    inputs.samples.append(smp("cuff_health", t, health))
    inputs.samples.append(smp("inflation_ms", t, inflation))


def last(records: list[Any], key: str) -> Any:
    return by_key(records)[key][-1]


def run(inputs: Inputs, until: int, registry: Any = REG, **kwargs: Any) -> list[Any]:
    return drive(make_monitor(registry, **kwargs), inputs, until // 60_000)


def check(rec: Any, kind: m.RhoKind, value: float) -> None:
    assert rec.rho is not None and rec.rho.kind is kind
    assert rec.rho.value == pytest.approx(value, abs=1e-12)
    assert rec.rho.alpha is None
    if kind is m.RhoKind.MEASURED:
        assert (
            rec.rho.guarantee == MEASURED_GUARANTEE
            and list(rec.rho.assumptions) == MEASURED_ASSUMPTIONS
        )
    else:
        assert rec.rho.value == 1.0
        assert (
            rec.rho.guarantee == DET_GUARANTEE
            and list(rec.rho.assumptions) == DET_ASSUMPTIONS
        )


# -- MEASURED ---------------------------------------------------------------------------------------


def test_range_upper_limit_is_a_normal_cdf_of_the_distance_in_standard_deviations() -> (
    None
):
    inputs = Inputs()
    measure(inputs, hhmm(9, 0), 152.0)
    rec = last(run(inputs, hhmm(9, 0)), f"range@{hhmm(9, 0)}")
    check(rec, m.RhoKind.MEASURED, phi((110 - 152) / S) + phi((152 - 140) / S))
    assert rec.rho.value == pytest.approx(
        0.97724986805, abs=1e-9
    )  # Phi(2) of the worked day


def test_range_band_adds_the_two_disjoint_regions() -> None:
    inputs = Inputs()
    measure(inputs, hhmm(9, 0), 104.0)
    rec = last(run(inputs, hhmm(9, 0)), f"range@{hhmm(9, 0)}")
    check(rec, m.RhoKind.MEASURED, phi((110 - 104) / S) + phi((104 - 140) / S))
    assert rec.rho.value == pytest.approx(0.8413447461 + 0.0000000010, abs=1e-9)


def test_hold_margin_is_the_lower_limit_formula_and_its_guard_is_deterministic() -> (
    None
):
    inputs = Inputs()
    measure(inputs, hhmm(6, 50), 94.0)
    inputs.events.append(evt("dispense", hhmm(7, 0), source="dispenser"))
    rec = last(run(inputs, hhmm(7, 0)), f"hold@{hhmm(7, 0)}")
    check(rec, m.RhoKind.MEASURED, phi((100 - 94) / S))
    old = Inputs()
    measure(old, hhmm(5, 30), 80.0)
    old.events.append(evt("dispense", hhmm(7, 0), source="dispenser"))
    guard = last(run(old, hhmm(7, 0)), f"hold@{hhmm(7, 0)}")
    check(guard, m.RhoKind.DETERMINISTIC, 1.0)


def resp_inputs(pre: float, responses: list[tuple[int, float]]) -> Inputs:
    inputs = Inputs()
    measure(inputs, hhmm(6, 55), pre)
    inputs.events.append(evt("dispense", hhmm(7, 0), source="dispenser"))
    for t, bp in responses:
        measure(inputs, t, bp)
    return inputs


def test_resp_one_measurement_is_the_difference_of_two_measurements() -> None:
    rec = last(
        run(resp_inputs(150.0, [(hhmm(8, 30), 145.0)]), hhmm(10, 0)),
        f"resp@{hhmm(7, 0)}",
    )
    check(rec, m.RhoKind.MEASURED, 0.7221551048586027)  # V-RESP-4: Phi(5 / (6 sqrt 2))
    assert rec.rho.value == pytest.approx(phi(5 / (S * math.sqrt(2))), abs=1e-15)
    rec2 = last(
        run(resp_inputs(138.0, [(hhmm(8, 30), 152.0)]), hhmm(10, 0)),
        f"resp@{hhmm(7, 0)}",
    )
    check(rec2, m.RhoKind.MEASURED, phi(24 / (S * math.sqrt(2))))
    assert rec2.rho.value == pytest.approx(0.997661, abs=1e-6)


def quadrature(pre: float, responses: list[float], delta: float = 10.0) -> float:
    """Item 4 of section 3.2 by a separate trapezoid rule on [-9, 9] with 40,000 intervals."""
    n, lo, hi = 40_000, -9.0, 9.0
    h = (hi - lo) / n
    total = 0.0
    for i in range(n + 1):
        z = lo + i * h
        term = math.exp(-0.5 * z * z) / math.sqrt(2 * math.pi)
        for x in responses:
            term *= phi((x + delta - pre) / S - z)
        total += term * (0.5 if i in (0, n) else 1.0)
    return total * h


@pytest.mark.parametrize(
    "responses", [[145.0, 143.0], [145.0, 141.0, 144.0], [150.0, 141.0]]
)
def test_resp_several_measurements_share_the_pre_dose_error(
    responses: list[float],
) -> None:
    pre = 150.0
    inputs = resp_inputs(
        pre, [(hhmm(8, 30 + 10 * i), x) for i, x in enumerate(responses)]
    )
    rec = last(run(inputs, hhmm(10, 0)), f"resp@{hhmm(7, 0)}")
    assert rec.state is m.VerdictState.VIOLATED  # every drop is below the required 10
    check(rec, m.RhoKind.MEASURED, quadrature(pre, responses))
    assert rec.rho.value == pytest.approx(quadrature(pre, responses), abs=1e-8)
    single_values = math.prod(
        phi((x + 10 - pre) / (S * math.sqrt(2))) for x in responses
    )
    assert (
        abs(rec.rho.value - single_values) > 1e-4
    )  # the drops are correlated: not a product


def test_resp_early_violation_by_the_bounds_is_measured() -> None:
    inputs = Inputs()
    measure(inputs, hhmm(6, 45), 55.0)
    inputs.events.append(evt("dispense", hhmm(7, 0), source="dispenser"))
    rec = last(run(inputs, hhmm(7, 0)), f"resp@{hhmm(7, 0)}")
    check(rec, m.RhoKind.MEASURED, phi((50 + 10 - 55) / S))


def test_the_error_model_comes_from_the_registry(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    other = registry_variant(
        tmp_path_factory.mktemp("sd"), values={"cuff_error_sd": 3.0}
    )
    inputs = Inputs()
    measure(inputs, hhmm(9, 0), 152.0)
    rec = last(run(inputs, hhmm(9, 0), other), f"range@{hhmm(9, 0)}")
    assert rec.rho is not None and rec.rho.value == pytest.approx(
        phi((110 - 152) / 3.0) + phi((152 - 140) / 3.0)
    )


def test_without_an_error_model_a_measured_rho_is_absent_and_counted_not_invented() -> (
    None
):
    spy = SpyRegistry(REG, unset=("cuff_error_sd",))
    mon = make_monitor(spy)
    inputs = Inputs()
    measure(inputs, hhmm(9, 0), 152.0)
    inputs.events.append(evt("dispense", hhmm(21, 0), source="dispenser"))
    records = drive(mon, inputs, hhmm(21, 0) // 60_000)
    assert last(records, f"range@{hhmm(9, 0)}").state is m.VerdictState.VIOLATED
    assert last(records, f"range@{hhmm(9, 0)}").rho is None
    assert mon.stats().rho_unavailable == 1
    # a deterministic rho needs no model
    spy2 = SpyRegistry(REG, unset=("cuff_error_sd",))
    d = Inputs()
    for t in (hhmm(7, 0), hhmm(21, 0), hhmm(21, 2)):
        d.events.append(evt("dispense", t, source="dispenser"))
    rec = last(
        drive(make_monitor(spy2), d, hhmm(21, 2) // 60_000), f"count@{hhmm(21, 2)}"
    )
    check(rec, m.RhoKind.DETERMINISTIC, 1.0)


# -- DETERMINISTIC and None --------------------------------------------------------------------------


def test_event_log_predicates_are_deterministic() -> None:
    sched = Inputs()
    recs = run(sched, hhmm(9, 31), sched=(hhmm(9, 0),))
    check(last(recs, f"sched@{hhmm(9, 0)}"), m.RhoKind.DETERMINISTIC, 1.0)
    resp = Inputs()
    measure(resp, hhmm(6, 55), 150.0)
    resp.events.append(evt("dispense", hhmm(7, 0), source="dispenser"))
    check(
        last(run(resp, hhmm(10, 0)), f"resp@{hhmm(7, 0)}"), m.RhoKind.DETERMINISTIC, 1.0
    )  # obligation_unmet
    sys_ = Inputs()
    measure(sys_, hhmm(9, 0), 130.0, health=0.0)
    check(
        last(run(sys_, hhmm(9, 0)), f"sys@{hhmm(9, 0)}"), m.RhoKind.DETERMINISTIC, 1.0
    )
    sys2 = Inputs()
    measure(
        sys2, hhmm(9, 0), 130.0, inflation=9_000.0
    )  # a device-reported duration: no error model
    check(
        last(run(sys2, hhmm(9, 0)), f"sys@{hhmm(9, 0)}"), m.RhoKind.DETERMINISTIC, 1.0
    )
    witness = Inputs()
    witness.samples.append(smp("presence", 0, 0.0))
    witness.events.append(evt("dispense", hhmm(7, 0), source="dispenser"))
    check(
        last(run(witness, hhmm(7, 0)), f"int@{hhmm(7, 0)}"),
        m.RhoKind.DETERMINISTIC,
        1.0,
    )
    day_end = Inputs()
    day_end.events.append(evt("dispense", hhmm(7, 0), source="dispenser"))
    check(
        last(run(day_end, 86_400_000, day_end=(86_400_000,)), "count@86400000"),
        m.RhoKind.DETERMINISTIC,
        1.0,
    )


def test_pending_and_satisfied_records_carry_no_rho() -> None:
    inputs = Inputs()
    measure(inputs, hhmm(9, 0), 125.0)
    inputs.events.append(evt("dispense", hhmm(9, 1), source="dispenser"))
    for r in run(inputs, hhmm(9, 30), sched=(hhmm(9, 0),)):
        if r.state is not m.VerdictState.VIOLATED:
            assert r.rho is None, (r.instance_key, r.state)
