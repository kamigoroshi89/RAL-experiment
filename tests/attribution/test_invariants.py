"""The invariants I1 to I5 of attribution-rule.md as property tests, and I6 on random cascades (tests 5 to 10)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ralmon.monitor import VerdictState
from ralmon.spec import TemplateId
from tests.fixtures.attribution import (
    NON_PROVENANCE_PATHS,
    load_fixture_registry,
    make_record,
    rho_variants,
    vector,
)
from tests.fixtures.attribution.strategies import EVIDENCE_KINDS, cascade_sets

TEMPLATES = [t.value for t in TemplateId]
ROBOT_SCOPE = {"sched", "hold", "resp", "int"}

# ---- strategies over the reading classes of the fields (values relate to the FIXTURE-ONLY thresholds) --

NODES = {
    "range": ["cuff"],
    "sys": ["cuff"],
    "sched": ["cuff", "robot"],
    "hold": ["cuff", "dispenser", "robot"],
    "resp": ["cuff", "dispenser", "robot"],
    "count": ["dispenser"],
    "int": ["dispenser", "robot"],
}
STATES = [
    "active",
    "active",
    "active",
    "inactive",
    "inactive+commanded",
    "unreachable",
    "link_down",
]
FIELD_VALUES: dict[str, Any] = {
    "system.diagnostics_ok": st.sampled_from([None, True, True, False]),
    "system.liveliness_ok": st.sampled_from([None, True, True, False]),
    "system.qos_deadline_missed": st.sampled_from([None, False, False, True]),
    "system.ble_link_quality": st.sampled_from([None, 1.0, 1.0, 0.95, 0.45]),
    "system.battery_low": st.sampled_from([None, True, False]),
    "system.nav_task_failed": st.sampled_from([None, False, False, True]),
    "system.manip_task_failed": st.sampled_from([None, False, False, True]),
    "signal_quality.ecg_sqi": st.sampled_from([None, 0.75, 0.75, 0.25]),
    "signal_quality.ppg_sqi": st.sampled_from([None, 0.75, 0.75, 0.25]),
    "signal_quality.cuff_error_code": st.sampled_from([None, "", "", "E1"]),
    "cross_device.pulse_vs_ecg_hr_diff": st.sampled_from([None, 2.0, 2.0, 20.0]),
    "witness.robot_present": st.sampled_from([None, True, False]),
    "witness.identity_confirmed": st.sampled_from([None, True, False]),
    "witness.intake_observed": st.sampled_from([None, True, False]),
    "crypto_temporal.authenticated": st.sampled_from([None, None, True, False]),
    "crypto_temporal.seq_gap_or_replay": st.sampled_from([None, False, False, True]),
    "crypto_temporal.timestamp_implausible": st.sampled_from(
        [None, False, False, True]
    ),
}


@st.composite
def fields_for(draw: Any, template: str) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    nodes = NODES[template]
    lifecycle = draw(
        st.one_of(
            st.none(),
            st.just({}),
            st.fixed_dictionaries({n: st.sampled_from(STATES) for n in nodes}),
        )
    )
    if lifecycle is not None:
        fields["system.node_lifecycle"] = lifecycle
    for path, strategy in FIELD_VALUES.items():
        value = draw(strategy)
        if value is not None:
            fields[path] = value
    return fields


@st.composite
def cases(draw: Any) -> tuple[str, dict[str, Any]]:
    template = draw(st.sampled_from(TEMPLATES))
    return template, draw(fields_for(template))


@pytest.fixture(scope="module")
def registry():  # type: ignore[no-untyped-def]
    return load_fixture_registry()


@pytest.fixture(scope="module")
def rule(registry):  # type: ignore[no-untyped-def]
    from ralmon.attribution import HierarchicalRule

    return HierarchicalRule(registry)


def _decide(rule: Any, registry: Any, template: str, fields: Mapping[str, Any]) -> Any:
    return rule.decide(make_record(template), vector(template, fields, registry))


# ---- test 5: I1 purity ----------------------------------------------------------------------


@settings(max_examples=120, deadline=None)
@given(
    case=cases(),
    state=st.sampled_from(list(VerdictState)),
    t_eval=st.integers(0, 10**9),
    decided=st.integers(0, 10**9),
    hi=st.floats(-1e6, 1e6),
    with_rho=st.booleans(),
)
def test_invariant_i1_purity(
    case, state, t_eval, decided, hi, with_rho, registry_and_rule
) -> None:  # type: ignore[no-untyped-def]
    registry, rule = registry_and_rule
    template, fields = case
    evidence = vector(template, fields, registry)
    reference = rule.decide(make_record(template), evidence)
    other = make_record(
        template,
        state=state,
        t_eval_ms=t_eval,
        decided_at_ms=decided,
        hi=hi,
        lo=hi - 1.0,
        sigma_norm=(-1.0, 0.0),
        rho=rho_variants()[0] if with_rho else None,
        pending_until_ms=decided + 5,
    )
    assert rule.decide(other, evidence) == reference
    assert rule.attribute(other, evidence) is reference.kappa


@pytest.fixture(scope="module")
def registry_and_rule(registry, rule):  # type: ignore[no-untyped-def]
    return registry, rule


# ---- test 6: I2 precedence ------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(case=cases())
def test_invariant_i2_precedence(case, registry_and_rule) -> None:  # type: ignore[no-untyped-def]
    registry, rule = registry_and_rule
    template, fields = case
    ie1 = fields.get("crypto_temporal.authenticated") is False
    ie2 = (
        fields.get("crypto_temporal.seq_gap_or_replay") is True
        and fields.get("system.ble_link_quality") == 1.0
    )
    ie3 = (
        template in {"range", "hold", "resp", "sys"}
        and fields.get("cross_device.pulse_vs_ecg_hr_diff") == 20.0
        and fields.get("signal_quality.ecg_sqi") == 0.75
        and fields.get("signal_quality.ppg_sqi") == 0.75
    )
    decision = _decide(rule, registry, template, fields)
    if ie1 or ie2 or ie3:
        assert decision.kappa.value == "C3"
        assert decision.row in (1, 2, 3)
    else:
        assert decision.kappa.value != "C3"


# ---- test 7: I3 provenance is never sufficient ----------------------------------------------


@pytest.mark.parametrize("template", TEMPLATES)
def test_invariant_i3_provenance_is_never_sufficient(
    template: str, registry_and_rule
) -> None:  # type: ignore[no-untyped-def]
    registry, rule = registry_and_rule
    assert len(NON_PROVENANCE_PATHS) == 18
    decision = _decide(rule, registry, template, {})
    assert decision.kappa.value == "UNDETERMINED"
    expected = "provenance_only" if template in {"sys", "int"} else "insufficient"
    assert decision.reason is not None and decision.reason.value == expected
    assert decision.evidence_used == ()


# ---- test 8: I4 no certainty from missing data ----------------------------------------------


def _without(fields: Mapping[str, Any], path: str) -> dict[str, Any]:
    return {k: v for k, v in fields.items() if k != path}


@settings(max_examples=150, deadline=None)
@given(case=cases())
def test_invariant_i4_no_certainty_from_missing_data(case, registry_and_rule) -> None:  # type: ignore[no-untyped-def]
    registry, rule = registry_and_rule
    template, fields = case
    before = _decide(rule, registry, template, fields).kappa.value
    for path in NON_PROVENANCE_PATHS:
        after = _decide(rule, registry, template, _without(fields, path)).kappa.value
        if before == "UNDETERMINED":
            assert after == "UNDETERMINED", (path, fields)
        if before != "C1" and path != "crypto_temporal.authenticated":
            assert after != "C1", (path, fields)


def test_invariant_i4_exception_is_the_unauthenticated_deployment(
    registry_and_rule,
) -> None:  # type: ignore[no-untyped-def]
    """AD-8: masking a failed verification can give C1 (W-08, W-10-A), the one exception of I4(b)."""
    from tests.fixtures.attribution import worked_case

    registry, rule = registry_and_rule
    for case_id in ("W-08", "W-10-A"):
        case = worked_case(case_id)
        assert (
            _decide(rule, registry, case["template"], case["fields"]).kappa.value
            == "C3"
        )
        masked = _without(case["fields"], "crypto_temporal.authenticated")
        assert _decide(rule, registry, case["template"], masked).kappa.value == "C1"


# ---- test 9: I5 locality and the A4 mask ----------------------------------------------------

EX_CP = (
    "system.node_lifecycle",
    "system.diagnostics_ok",
    "system.liveliness_ok",
    "system.qos_deadline_missed",
    "system.ble_link_quality",
    "crypto_temporal.seq_gap_or_replay",
    "crypto_temporal.timestamp_implausible",
)
ROBOT_OUTCOMES = ("system.nav_task_failed", "system.manip_task_failed")
EXCLUSION_SET = {
    "range": (
        *EX_CP,
        "signal_quality.cuff_error_code",
        "cross_device.pulse_vs_ecg_hr_diff",
        "crypto_temporal.authenticated",
    ),
    "sched": (
        *EX_CP,
        *ROBOT_OUTCOMES,
        "signal_quality.cuff_error_code",
        "crypto_temporal.authenticated",
    ),
    "hold": (
        *EX_CP,
        *ROBOT_OUTCOMES,
        "signal_quality.cuff_error_code",
        "cross_device.pulse_vs_ecg_hr_diff",
        "crypto_temporal.authenticated",
    ),
    "resp": (
        *EX_CP,
        *ROBOT_OUTCOMES,
        "signal_quality.cuff_error_code",
        "cross_device.pulse_vs_ecg_hr_diff",
        "crypto_temporal.authenticated",
        "witness.identity_confirmed",
        "witness.intake_observed",
    ),
    "count": (),
    "sys": (),
    "int": (),
}
#: ``EMBODIED_MASK_ALL`` of evidence-channels.md (class None of the A4 mask): six paths.
A4_PATH_MASK = (
    "witness.robot_present",
    "witness.identity_confirmed",
    "witness.intake_observed",
    "system.nav_task_failed",
    "system.manip_task_failed",
    "system.battery_low",
)


@settings(max_examples=150, deadline=None)
@given(case=cases())
def test_invariant_i5_locality(case, registry_and_rule) -> None:  # type: ignore[no-untyped-def]
    registry, rule = registry_and_rule
    template, fields = case
    decision = _decide(rule, registry, template, fields)
    keep = set(decision.evidence_used) | set(EXCLUSION_SET[template])
    for path in NON_PROVENANCE_PATHS:
        if path in keep:
            continue
        masked = _decide(rule, registry, template, _without(fields, path))
        assert masked.kappa == decision.kappa, (path, fields)


@settings(max_examples=150, deadline=None)
@given(case=cases())
def test_invariant_i5_a4_mask_changes_only_the_listed_fields(
    case, registry_and_rule
) -> None:  # type: ignore[no-untyped-def]
    registry, rule = registry_and_rule
    template, fields = case
    before = _decide(rule, registry, template, fields).kappa.value
    masked_fields = {k: v for k, v in fields.items() if k not in A4_PATH_MASK}
    # the mask touches exactly the six paths of the table
    assert set(fields) - set(masked_fields) <= set(A4_PATH_MASK)
    after = _decide(rule, registry, template, masked_fields).kappa.value
    if template in {"range", "count", "sys"}:
        assert after == before  # no field of the mask is read
    elif before == "C3":
        assert after == "C3"
    elif before == "C2":
        assert after in {"C2", "UNDETERMINED"}
    elif before == "C1":
        assert after == "UNDETERMINED"
    else:
        assert after == "UNDETERMINED"


# ---- test 10: I6 cascade consistency on random sets ------------------------------------------


def _alerts(attributor: Any, registry: Any, items: list[tuple[Any, str]]) -> list[Any]:
    records = [r for r, _ in items]
    evidence = {
        r.instance_key: vector(r.template.value, EVIDENCE_KINDS[kind], registry)
        for r, kind in items
    }
    return list(attributor.attribute_all(records, evidence))


@pytest.fixture(scope="module")
def attributor(registry):  # type: ignore[no-untyped-def]
    from ralmon.attribution import RuleAttributor
    from ralmon.spec import load_templates

    return RuleAttributor(registry, load_templates(registry=registry))


@settings(max_examples=150, deadline=None)
@given(items=cascade_sets(), rnd=st.randoms(use_true_random=False))
def test_invariant_i6_cascade_consistency(items, rnd, registry, attributor) -> None:  # type: ignore[no-untyped-def]
    alerts = _alerts(attributor, registry, items)
    by_key = {a.xi.instance_key: a for a in alerts}
    decided = {
        r.instance_key: r.decided_at_ms
        for r, _ in items
        if r.state is VerdictState.VIOLATED
    }
    assert len(by_key) == len(alerts)
    for alert in alerts:
        if alert.caused_by is not None:
            root = by_key[alert.caused_by]
            assert alert.xi.instance_key in root.root_cause_of  # mutual inverses
            assert (
                alert.kappa == root.kappa
            )  # an effect never has another kappa than its root
            assert root.caused_by is None  # depth one: acyclic
            assert not alert.root_cause_of
            assert (
                alert.verdict is VerdictState.VIOLATED
                and root.verdict is VerdictState.VIOLATED
            )
            assert decided[root.xi.instance_key] < decided[alert.xi.instance_key]
            assert root.tau is TemplateId.SCHED
            assert alert.tau in {TemplateId.RESP, TemplateId.HOLD}
        for key in alert.root_cause_of:
            assert by_key[key].caused_by == alert.xi.instance_key
        if alert.verdict is VerdictState.PREDICTED_VIOLATION:
            assert alert.caused_by is None and not alert.root_cause_of
    # the output does not depend on the order of the input
    shuffled = list(items)
    rnd.shuffle(shuffled)
    assert _alerts(attributor, registry, shuffled) == alerts
