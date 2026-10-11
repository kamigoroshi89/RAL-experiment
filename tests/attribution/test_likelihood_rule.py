"""The likelihood attributor (WS05-T12, ADR-074; specification ``docs/models/attribution-likelihood.md``).

NUMBERS HERE ARE TEST VALUES. ``TEST_VALUES`` takes one value of the sensitivity grid of the specification for each parameter
so that a rule can be built; none is a proposal, none is a clinical or device value, and the production code has no default
for any of them (``test_awaiting_value_fails_loudly``). The hand-computed examples are written with explicit arithmetic and
do not read the YAML; ``reference_posterior`` of ``test_likelihood_spec`` (the test-local transcription of the pseudo-code of
the specification) is the cross-check of the sweep.
"""

from __future__ import annotations

import ast
import dataclasses
import itertools
import math
import random
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from ralmon.attribution import AttributedCause, RuleAttributor
from ralmon.monitor import VerdictState
from ralmon.spec import TemplateId, load_templates
from tests.attribution.test_likelihood_spec import (
    CONFIG_PATH,
    CUFF_REPEAT,
    CUFF_TEMPLATES,
    DISPENSER_FIELDS,
    DISPENSER_TEMPLATES,
    reference_posterior,
    relevance_map,
)
from tests.fixtures.attribution import (
    hms,
    load_fixture_registry,
    make_record,
    predicted_rho,
    vector,
    worked_case,
)

ROOT = Path(__file__).resolve().parents[2]
LIKELIHOOD_PY = ROOT / "src" / "ralmon" / "attribution" / "likelihood.py"

#: TEST VALUES: grid values of the sensitivity design of the specification, not proposals.
TEST_VALUES: dict[str, Any] = {
    "eps": 0.01,
    "qc": 0.5,
    "q_stale": 0.5,
    "rep_nat": 0.0197,
    "delta": 0.0,
    "dispense_bounce_interval_ms": 10_000,
    "tau": 0.67,
    "cumulative_level": 0.9,
    "class_priors": "uniform",
    "pi_designs": "uniform",
}
PARAMS = {k: v for k, v in TEST_VALUES.items() if isinstance(v, (int, float))}
TEMPLATES = ("range", "sched", "hold", "count", "resp", "sys", "int")
CLASSES = ("C1", "C2", "C3")
WITNESS = ("witness.identity_confirmed", "witness.intake_observed")
A4_REMOVED = (
    "witness.identity_confirmed",
    "witness.intake_observed",
    "system.nav_task_failed",
    "system.manip_task_failed",
)
DIAG = "system.diagnostics_ok"
BLE = "system.ble_link_quality"
GAP = "system.seq_gap"
AUTH = "crypto_temporal.authenticated"

#: (value that reads A, value that reads D) of each field against the FIXTURE-ONLY thresholds of the test registry
#: (ecg and ppg floor 0.5, link floor 0.9, coherence tolerance 10) and ``dispense_bounce_interval_ms = 10000``.
AD: dict[str, tuple[Any, Any]] = {
    "system.node_lifecycle": ({"cuff": "unreachable"}, {"cuff": "active"}),
    "system.diagnostics_ok": (False, True),
    "system.liveliness_ok": (False, True),
    "system.qos_deadline_missed": (True, False),
    "system.ble_link_quality": (0.5, 1.0),
    "system.nav_task_failed": (True, False),
    "system.manip_task_failed": (True, False),
    "system.seq_gap": (True, False),
    "signal_quality.ecg_sqi": (0.1, 0.9),
    "signal_quality.ppg_sqi": (0.1, 0.9),
    "signal_quality.cuff_error_code": ("E1", ""),
    "signal_quality.cuff_value_repeated": (True, False),
    "cross_device.pulse_vs_ecg_hr_diff": (30.0, 1.0),
    "witness.identity_confirmed": (False, True),
    "witness.intake_observed": (False, True),
    "crypto_temporal.authenticated": (False, True),
    "crypto_temporal.seq_repeat": (True, False),
    "crypto_temporal.timestamp_implausible": (True, False),
    "dispenser.interval_since_previous_ms": (5_000, 20_000),
    "dispenser.content_change": (0.0, 1.5),
}


@pytest.fixture(scope="module")
def registry():  # type: ignore[no-untyped-def]
    return load_fixture_registry()


@pytest.fixture(scope="module")
def table():  # type: ignore[no-untyped-def]
    from ralmon.attribution.likelihood import load_likelihood_table

    return load_likelihood_table(CONFIG_PATH)


def build_rule(registry: Any, table: Any, **kwargs: Any) -> Any:
    from ralmon.attribution.likelihood import LikelihoodRule

    options: dict[str, Any] = {
        "sensitivity_values": dict(TEST_VALUES),
        "diagnostics_profile": "driver_with_diagnostics",
    }
    options.update(kwargs)
    return LikelihoodRule(registry, table, **options)


@pytest.fixture(scope="module")
def rule(registry, table):  # type: ignore[no-untyped-def]
    return build_rule(registry, table)


def classes_to_vector(
    template: str, classes: Mapping[str, str | None], registry: Any
) -> Any:
    """An EvidenceVector whose fields read ``A`` or ``D`` as listed; every other field is None."""
    fields = {
        path: AD[path][0 if c == "A" else 1]
        for path, c in classes.items()
        if c is not None
    }
    return vector(template, fields, registry)


def post(rule: Any, template: str, classes: Mapping[str, str | None], reg: Any) -> Any:
    evidence = classes_to_vector(template, classes, reg)
    return rule.posterior_subtypes(make_record(template), evidence)


# ---- test 1: the cells, by hand ------------------------------------------------------------------------------


def test_posterior_sums_to_one_and_respects_the_cells(registry, rule) -> None:  # type: ignore[no-untyped-def]
    # Hand-computed, no YAML read: template ``count``; authenticated asserted (A), seq_repeat denied, timestamp denied.
    # Components of ``count``: C1 double_take, dose_omission, spontaneous_count (3); C2 dispenser_bounce, ble_dropout,
    # message_drop, process_kill, uncommanded_lifecycle_transition (5); C3 dispense_forgery naive and informed and
    # dispenser_physical_tamper (3). Class prior 1/3, pi uniform inside the class.
    eps, qc = PARAMS["eps"], PARAMS["qc"]
    structural_d = 1 - eps
    like = {
        "dispense_forgery_naive": (1 - eps)
        * (1 - (eps + (1 - 2 * eps) * qc))
        * structural_d,
        "dispense_forgery_informed": (1 - eps) * structural_d * structural_d,
    }
    default = eps * structural_d * structural_d
    weight: dict[str, float] = {}
    for sub in ("double_take", "dose_omission", "spontaneous_count"):
        weight[sub] = (1 / 3) * (1 / 3) * default
    for sub in (
        "dispenser_bounce",
        "ble_dropout",
        "message_drop",
        "process_kill",
        "uncommanded_lifecycle_transition",
    ):
        weight[sub] = (1 / 3) * (1 / 5) * default
    weight["dispenser_physical_tamper"] = (1 / 3) * (1 / 3) * default
    for comp, value in like.items():
        weight[comp] = (1 / 3) * (1 / 3) * value
    z = sum(weight.values())
    expected = {k: v / z for k, v in weight.items()}
    expected["dispense_forgery"] = expected.pop(
        "dispense_forgery_naive"
    ) + expected.pop("dispense_forgery_informed")
    evidence = vector(
        "count",
        {
            AUTH: False,
            "crypto_temporal.seq_repeat": False,
            "crypto_temporal.timestamp_implausible": False,
        },
        registry,
    )
    sub = rule.posterior_subtypes(make_record("count"), evidence)
    assert sum(sub.values()) == pytest.approx(1.0, abs=1e-12)
    assert set(sub) == set(expected)
    for name, value in expected.items():
        assert sub[name] == pytest.approx(value, rel=1e-9), name
    cls = rule.posterior(make_record("count"), evidence)
    assert set(cls) == set(AttributedCause) - {AttributedCause.UNDETERMINED}
    assert sum(cls.values()) == pytest.approx(1.0, abs=1e-12)
    assert cls[AttributedCause.C3_INTEGRITY] == pytest.approx(
        expected["dispense_forgery"] + expected["dispenser_physical_tamper"],
        rel=1e-9,
    )


def test_spec_example_only_authenticated_asserted_gives_0_970732(
    registry, rule
) -> None:  # type: ignore[no-untyped-def]
    # the hand example of the specification (count, eps 0.01, uniform): only ``authenticated`` is read, and asserted
    evidence = vector("count", {AUTH: False}, registry)
    cls = rule.posterior(make_record("count"), evidence)
    assert cls[AttributedCause.C3_INTEGRITY] == pytest.approx(0.970732, abs=1e-6)
    assert cls[AttributedCause.C1_CLINICAL] == pytest.approx(
        cls[AttributedCause.C2_SYSTEM]
    )


# ---- test 2: None is factor one -------------------------------------------------------------------------------


def test_none_reading_is_factor_one(registry, rule) -> None:  # type: ignore[no-untyped-def]
    full = {
        "system.liveliness_ok": "A",
        "signal_quality.cuff_error_code": "D",
        "crypto_temporal.authenticated": "D",
    }
    for dropped in full:
        kept = {k: v for k, v in full.items() if k != dropped}
        with_none = post(rule, "range", {**kept, dropped: None}, registry)
        without = post(rule, "range", kept, registry)
        assert dict(with_none) == dict(without)
    # an empty evidence vector gives the prior (restricted to the applicable classes, uniform pi)
    empty = post(rule, "range", {}, registry)
    cls_prior = rule.posterior(
        make_record("range"), classes_to_vector("range", {}, registry)
    )
    for c in CLASSES:
        assert cls_prior[AttributedCause(c)] == pytest.approx(1 / 3)
    assert sum(empty.values()) == pytest.approx(1.0)


def test_group_pair_with_both_members_none_is_factor_one(registry, rule) -> None:  # type: ignore[no-untyped-def]
    base = post(rule, "hold", {"crypto_temporal.authenticated": "D"}, registry)
    again = post(
        rule,
        "hold",
        {"crypto_temporal.authenticated": "D", BLE: None, GAP: None},
        registry,
    )
    assert dict(base) == dict(again)


# ---- test 3: diagnostics ok does not exclude silent faults ---------------------------------------------------


def test_diagnostics_ok_does_not_exclude_silent_faults(registry, rule) -> None:  # type: ignore[no-untyped-def]
    eps = PARAMS["eps"]
    sub = post(
        rule, "range", {DIAG: "D"}, registry
    )  # diagnostics ok = a denied reading
    cls = rule.posterior(
        make_record("range"), classes_to_vector("range", {DIAG: "D"}, registry)
    )
    assert (
        cls[AttributedCause.C2_SYSTEM] > eps
    )  # eps-scaled floor: P(D | C2 mixture) stays above eps
    assert cls[AttributedCause.C1_CLINICAL] < 1.0 - eps
    for silent in ("stuck_at", "cuff_silent_bias"):
        assert sub[silent] > eps / 10


# ---- test 4: prior free ratio ---------------------------------------------------------------------------------


def test_prior_free_ratio(registry, table) -> None:  # type: ignore[no-untyped-def]
    evidence = classes_to_vector(
        "range",
        {"signal_quality.cuff_error_code": "D", "system.liveliness_ok": "D"},
        registry,
    )
    lam = {}
    for prior, design in itertools.product(
        ("uniform", "c1_heavy", "c3_heavy"), ("uniform", "quiet_rare", "quiet_common")
    ):
        values = {**TEST_VALUES, "class_priors": prior, "pi_designs": design}
        rule = build_rule(registry, table, sensitivity_values=values)
        lam[(prior, design)] = rule.log_likelihood_ratio(
            "hypertensive_spike", "cuff_silent_bias", evidence
        )
    assert (
        len(set(lam.values())) == 1
    )  # neither the class prior nor the weights between subtypes enter


def test_pair_statistic_is_zero_on_identical_evidence(registry, rule) -> None:  # type: ignore[no-untyped-def]
    evidence = classes_to_vector(
        "hold",
        {BLE: "D", GAP: "A", "signal_quality.cuff_value_repeated": "D"},
        registry,
    )
    lam_a = rule.log_likelihood_ratio("dispenser_bounce", "dispense_forgery", evidence)
    assert lam_a != 0.0  # Lambda itself is the lean of the catalogue
    d = rule.pair_statistic("dispenser_bounce", "dispense_forgery", evidence, evidence)
    assert d == 0.0
    other = classes_to_vector("hold", {AUTH: "A"}, registry)
    assert (
        rule.pair_statistic("dispenser_bounce", "dispense_forgery", evidence, other)
        != 0.0
    )


def test_subtype_log_likelihood_mixes_the_levels(registry, table) -> None:  # type: ignore[no-untyped-def]
    # replay has two components (naive, informed); P(e | replay) is the weighted mixture, weights of the pi design
    evidence = classes_to_vector("sched", {"crypto_temporal.seq_repeat": "A"}, registry)
    rule = build_rule(registry, table)
    eps = PARAMS["eps"]
    naive = (
        1 - eps
    )  # replay_naive raises seq_repeat by construction; the informed level has the structural zero
    informed = eps
    assert rule.subtype_log_likelihood("replay", evidence) == pytest.approx(
        math.log(0.5 * naive + 0.5 * informed)
    )
    heavy = build_rule(
        registry,
        table,
        sensitivity_values={**TEST_VALUES, "pi_designs": "quiet_common"},
    )
    # quiet_common weighs replay_informed 4, replay_naive 1
    assert heavy.subtype_log_likelihood("replay", evidence) == pytest.approx(
        math.log(0.2 * naive + 0.8 * informed)
    )
    with pytest.raises(KeyError):
        rule.subtype_log_likelihood("not_a_subtype", evidence)


# ---- test 5: determinism ---------------------------------------------------------------------------------------


def test_identical_evidence_gives_identical_posterior_for_two_instances(
    registry, table
) -> None:  # type: ignore[no-untyped-def]
    classes = {"system.liveliness_ok": "A", "crypto_temporal.seq_repeat": "D"}
    one = build_rule(registry, table)
    two = build_rule(registry, table)
    evidence = classes_to_vector("hold", classes, registry)
    first = one.posterior_subtypes(make_record("hold", key="hold@1"), evidence)
    second = one.posterior_subtypes(
        make_record("hold", key="hold@2", hi=-3.0), evidence
    )
    third = two.posterior_subtypes(make_record("hold", key="hold@1"), evidence)
    assert dict(first) == dict(second) == dict(third)
    assert list(first) == list(second)  # also the order of the keys


# ---- test 6: the threshold -----------------------------------------------------------------------------------


def test_threshold_gives_undetermined(registry, table) -> None:  # type: ignore[no-untyped-def]
    evidence = classes_to_vector("count", {AUTH: "A"}, registry)  # p(C3) = 0.9707
    low = build_rule(registry, table, sensitivity_values={**TEST_VALUES, "tau": 0.9})
    high = build_rule(registry, table, sensitivity_values={**TEST_VALUES, "tau": 0.99})
    record = make_record("count")
    assert low.attribute(record, evidence) is AttributedCause.C3_INTEGRITY
    assert high.attribute(record, evidence) is AttributedCause.UNDETERMINED
    assert high.posterior(record, evidence) == low.posterior(record, evidence)
    decision = high.decide(record, evidence)
    assert decision.kappa is AttributedCause.UNDETERMINED
    assert decision.p_kappa is not None
    assert decision.p_kappa[AttributedCause.C3_INTEGRITY] == pytest.approx(
        0.970732, abs=1e-6
    )
    assert decision.abstention_threshold == 0.99
    # through the attributor: kappa UNDETERMINED, p_kappa still filled
    attributor = RuleAttributor(registry, load_templates(registry=registry), rule=high)
    (alert,) = attributor.attribute_all([record], {record.instance_key: evidence})
    assert alert.kappa is AttributedCause.UNDETERMINED
    assert alert.p_kappa is not None
    assert alert.p_kappa[AttributedCause.C3_INTEGRITY] == pytest.approx(
        0.970732, abs=1e-6
    )


def test_tie_at_the_maximum_is_undetermined(registry, table) -> None:  # type: ignore[no-untyped-def]
    # tau below every posterior, so that only the tie can make the label abstain
    rule = build_rule(registry, table, sensitivity_values={**TEST_VALUES, "tau": 0.3})
    # no field read: the three classes tie at 1/3
    assert (
        rule.attribute(make_record("count"), classes_to_vector("count", {}, registry))
        is AttributedCause.UNDETERMINED
    )
    # two classes tie at sys when nothing is read (C1 impossible, C2 = C3 = 1/2)
    assert (
        rule.attribute(make_record("sys"), classes_to_vector("sys", {}, registry))
        is AttributedCause.UNDETERMINED
    )
    # a clear maximum above tau is a label
    evidence = classes_to_vector("count", {AUTH: "A"}, registry)
    assert (
        rule.attribute(make_record("count"), evidence) is AttributedCause.C3_INTEGRITY
    )


def test_kappa_is_the_argmax_class_above_the_threshold(registry, rule) -> None:  # type: ignore[no-untyped-def]
    record = make_record("sched")
    system = classes_to_vector(
        "sched", {"system.liveliness_ok": "A", "system.node_lifecycle": "A"}, registry
    )
    assert rule.attribute(record, system) is AttributedCause.C2_SYSTEM
    integrity = classes_to_vector("sched", {AUTH: "A"}, registry)
    assert rule.attribute(record, integrity) is AttributedCause.C3_INTEGRITY


# ---- test 7: only the relevance map -----------------------------------------------------------------------------


def expected_reads(template: str) -> set[str]:
    reads = set(relevance_map()[template])
    if template in DISPENSER_TEMPLATES:
        reads |= set(DISPENSER_FIELDS)
    if template in CUFF_TEMPLATES:
        reads.add(CUFF_REPEAT)
    return reads


@pytest.mark.parametrize("template", TEMPLATES)
def test_reads_only_the_relevance_map_fields(template, registry, rule) -> None:  # type: ignore[no-untyped-def]
    reads = set(rule.read_fields(template))
    assert reads == expected_reads(template)
    # masks by data scope
    for field in DISPENSER_FIELDS:
        assert (field in reads) == (template in DISPENSER_TEMPLATES)
    assert (CUFF_REPEAT in reads) == (template in CUFF_TEMPLATES)
    assert {f for f in reads if f.startswith("witness.")} == (
        set(WITNESS) if template == "resp" else set()
    )
    # a field outside the map cannot change the result
    outside = [f for f in AD if f not in reads]
    base_classes = {
        "system.liveliness_ok": "D",
        "crypto_temporal.seq_repeat": "D",
        "crypto_temporal.authenticated": "D",
    }
    base = rule.posterior_subtypes(
        make_record(template), classes_to_vector(template, base_classes, registry)
    )
    for field in outside:
        for k in ("A", "D"):
            changed = rule.posterior_subtypes(
                make_record(template),
                classes_to_vector(template, {**base_classes, field: k}, registry),
            )
            assert dict(changed) == dict(base), (template, field, k)
    # battery_low and robot_present are context for every template
    ctx = vector(
        template,
        {
            "system.battery_low": True,
            "witness.robot_present": True,
            **{f: AD[f][0] for f in base_classes},
        },
        registry,
    )
    again = rule.posterior_subtypes(make_record(template), ctx)
    assert dict(again) != {} and set(again) == set(base)


def _moved(a: Mapping[str, float], b: Mapping[str, float]) -> bool:
    """The posteriors differ by more than rounding (a factor common to all components moves the last bit)."""
    return any(abs(a[k] - b[k]) > 1e-9 for k in a)


@pytest.mark.parametrize("template", TEMPLATES)
def test_dispenser_and_cuff_masks_hold_even_if_the_extractor_fills_them(
    template, registry, rule
) -> None:  # type: ignore[no-untyped-def]
    no_extra = classes_to_vector(template, {AUTH: "D"}, registry)
    extra = classes_to_vector(
        template,
        {
            AUTH: "D",
            "dispenser.interval_since_previous_ms": "A",
            "dispenser.content_change": "A",
            CUFF_REPEAT: "A",
        },
        registry,
    )
    a = rule.posterior_subtypes(make_record(template), no_extra)
    b = rule.posterior_subtypes(make_record(template), extra)
    # where the cuff repeat is read but every component has the same natural cell (sched, sys) it cannot move the
    # posterior; stuck_at raises it at range, hold and resp
    moves = template in DISPENSER_TEMPLATES or template in ("range", "hold", "resp")
    assert _moved(a, b) == moves
    only_dispenser = classes_to_vector(
        template, {AUTH: "D", "dispenser.content_change": "A"}, registry
    )
    c = rule.posterior_subtypes(make_record(template), only_dispenser)
    assert _moved(c, a) == (template in DISPENSER_TEMPLATES)
    only_cuff = classes_to_vector(template, {AUTH: "D", CUFF_REPEAT: "A"}, registry)
    d = rule.posterior_subtypes(make_record(template), only_cuff)
    assert _moved(d, a) == (template in ("range", "hold", "resp"))
    assert template in CUFF_TEMPLATES or dict(d) == dict(a)  # not read: exactly equal


def test_i1_nothing_but_the_template_and_the_evidence_is_read(registry, rule) -> None:  # type: ignore[no-untyped-def]
    evidence = classes_to_vector("range", {"system.liveliness_ok": "A"}, registry)
    base = rule.decide(make_record("range"), evidence)
    other = rule.decide(
        make_record(
            "range",
            key="range@other",
            hi=-0.5,
            lo=-9.0,
            decided_at_ms=hms(23, 59),
            rho=predicted_rho(),
            state=VerdictState.VIOLATED,
        ),
        evidence,
    )
    assert base == other


# ---- test 8: the hierarchical rule is unchanged ---------------------------------------------------------------


def test_hierarchical_rule_unchanged(registry) -> None:  # type: ignore[no-untyped-def]
    from ralmon.attribution import HierarchicalRule

    rule = HierarchicalRule(registry)
    case = worked_case("W-01")
    evidence = vector(case["template"], case["fields"], registry)
    record = make_record(case["template"])
    assert rule.posterior(record, evidence) is None
    assert rule.posterior_subtypes(record, evidence) is None
    attributor = RuleAttributor(registry, load_templates(registry=registry))
    (alert,) = attributor.attribute_all([record], {record.instance_key: evidence})
    assert alert.p_kappa is None and alert.cause_set is None
    assert alert.kappa.value == case["kappa"]


# ---- test 9: the A4 mask ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("template", TEMPLATES)
def test_a4_mask_removes_witness_likelihoods(template, registry, table) -> None:  # type: ignore[no-untyped-def]
    a4 = build_rule(registry, table, a4=True)
    plain = build_rule(registry, table)
    observed = {
        "system.liveliness_ok": "A",
        "crypto_temporal.authenticated": "D",
        "witness.identity_confirmed": "A",
        "witness.intake_observed": "A",
        "system.nav_task_failed": "A",
        "system.manip_task_failed": "D",
    }
    masked = {k: (None if k in A4_REMOVED else v) for k, v in observed.items()}
    with_cells = a4.posterior_subtypes(
        make_record(template), classes_to_vector(template, observed, registry)
    )
    table_without = plain.posterior_subtypes(
        make_record(template), classes_to_vector(template, masked, registry)
    )
    assert dict(with_cells) == dict(table_without)
    assert set(a4.read_fields(template)) == set(plain.read_fields(template)) - set(
        A4_REMOVED
    )
    # the applicable set does not change under A4
    assert a4.applicable_subtypes(template) == plain.applicable_subtypes(template)
    # the four aggregate system fields keep their cells
    assert {
        "system.node_lifecycle",
        DIAG,
        "system.liveliness_ok",
        "system.qos_deadline_missed",
    } <= set(a4.read_fields(template))


# ---- test 10: awaiting values ------------------------------------------------------------------------------------


def test_awaiting_value_fails_loudly(registry, table) -> None:  # type: ignore[no-untyped-def]
    from ralmon.attribution.likelihood import (
        AwaitingValueError,
        LikelihoodConfigError,
        LikelihoodRule,
    )

    with pytest.raises(AwaitingValueError) as excinfo:
        LikelihoodRule(
            registry,
            table,
            sensitivity_values={},
            diagnostics_profile="driver_with_diagnostics",
        )
    assert issubclass(AwaitingValueError, LikelihoodConfigError)
    for name in TEST_VALUES:
        assert name in str(excinfo.value)
    assert set(excinfo.value.names) == set(TEST_VALUES)
    for name in TEST_VALUES:
        partial = {k: v for k, v in TEST_VALUES.items() if k != name}
        with pytest.raises(AwaitingValueError) as one:
            LikelihoodRule(
                registry,
                table,
                sensitivity_values=partial,
                diagnostics_profile="driver_with_diagnostics",
            )
        assert one.value.names == (name,)
        assert name in str(one.value)


def test_sensitivity_values_are_recorded_and_labelled(registry, table, rule) -> None:  # type: ignore[no-untyped-def]
    meta = rule.metadata
    recorded = meta["sensitivity_values"]
    for name, value in TEST_VALUES.items():
        assert recorded[name]["value"] == value
        assert "sensitivity" in recorded[name]["label"]
        assert "not a proposal" in recorded[name]["label"]
    assert meta["diagnostics_profile"] == "driver_with_diagnostics"
    assert meta["grouped_variant"] == "reference"
    assert meta["a4"] is False
    assert meta["model_version"] == rule.model_version
    assert meta["config_sha256"] and len(meta["config_sha256"]) == 64
    assert meta["sensitivity_values"]["class_priors"]["value"] == "uniform"
    # JSON-serialisable, so that it can be written next to the output
    import json

    json.dumps(meta)
    # the token changes with every option that changes the posterior, and not otherwise
    same = build_rule(registry, table)
    assert same.model_version == rule.model_version
    for changed in (
        build_rule(registry, table, sensitivity_values={**TEST_VALUES, "eps": 0.05}),
        build_rule(registry, table, a4=True),
        build_rule(registry, table, grouped_variant="fully_independent"),
        build_rule(registry, table, diagnostics_profile="without_diagnostics"),
        build_rule(
            registry,
            table,
            sensitivity_values={**TEST_VALUES, "class_priors": "c3_rare"},
        ),
    ):
        assert changed.model_version != rule.model_version
    tau_only = build_rule(
        registry, table, sensitivity_values={**TEST_VALUES, "tau": 0.5}
    )
    assert (
        tau_only.model_version == rule.model_version
    )  # tau and the level change the label and the set, not p(s | e)


def test_bad_sensitivity_values_are_refused(registry, table) -> None:  # type: ignore[no-untyped-def]
    from ralmon.attribution.likelihood import LikelihoodConfigError

    bad: list[dict[str, Any]] = [
        {**TEST_VALUES, "not_a_parameter": 1.0},
        {**TEST_VALUES, "eps": 0.0},
        {**TEST_VALUES, "eps": 0.5},
        {**TEST_VALUES, "qc": 1.5},
        {**TEST_VALUES, "tau": float("nan")},
        {**TEST_VALUES, "rep_nat": 1.0},
        {**TEST_VALUES, "dispense_bounce_interval_ms": -1},
        {**TEST_VALUES, "cumulative_level": 1.0},
        {**TEST_VALUES, "class_priors": "no_such_design"},
        {**TEST_VALUES, "pi_designs": 3},
        {**TEST_VALUES, "eps": True},
    ]
    for values in bad:
        with pytest.raises(LikelihoodConfigError):
            build_rule(registry, table, sensitivity_values=values)
    with pytest.raises(LikelihoodConfigError):
        build_rule(registry, table, diagnostics_profile="no_such_profile")
    with pytest.raises(LikelihoodConfigError):
        build_rule(registry, table, grouped_variant="no_such_variant")
    with pytest.raises(TypeError):  # the profile is required: no hidden default
        from ralmon.attribution.likelihood import LikelihoodRule

        LikelihoodRule(registry, table, sensitivity_values=dict(TEST_VALUES))  # type: ignore[call-arg]


def test_a_parameter_that_no_live_cell_uses_is_not_required(registry, table) -> None:  # type: ignore[no-untyped-def]
    from ralmon.attribution.likelihood import AwaitingValueError

    values = {k: v for k, v in TEST_VALUES.items() if k != "q_stale"}
    build_rule(
        registry,
        table,
        sensitivity_values=values,
        diagnostics_profile="without_diagnostics",
    )
    with pytest.raises(AwaitingValueError) as excinfo:
        build_rule(registry, table, sensitivity_values=values)
    assert excinfo.value.names == ("q_stale",)
    # a value supplied for a parameter that is not needed is accepted and not recorded as used
    extra = build_rule(
        registry,
        table,
        sensitivity_values=TEST_VALUES,
        diagnostics_profile="without_diagnostics",
    )
    assert "q_stale" not in extra.metadata["sensitivity_values"]
    # the diversion share is only needed where the witness cell is read
    no_delta = {k: v for k, v in TEST_VALUES.items() if k != "delta"}
    build_rule(registry, table, sensitivity_values=no_delta, a4=True)


def test_the_cumulative_level_is_needed_only_if_the_rule_makes_the_set(
    registry, table
) -> None:  # type: ignore[no-untyped-def]
    from ralmon.attribution.likelihood import AwaitingValueError

    values = {k: v for k, v in TEST_VALUES.items() if k != "cumulative_level"}
    with pytest.raises(AwaitingValueError):
        build_rule(registry, table, sensitivity_values=values)
    rule = build_rule(
        registry, table, sensitivity_values=values, needs_cumulative_level=False
    )
    evidence = classes_to_vector("count", {AUTH: "A"}, registry)
    decision = rule.decide(make_record("count"), evidence)
    assert decision.cause_set is None
    with pytest.raises(ValueError, match="cumulative"):
        RuleAttributor(registry, load_templates(registry=registry), rule=rule)


# ---- the subtype posterior ---------------------------------------------------------------------------------------


def test_class_posterior_is_the_sum_of_subtype_posteriors(
    registry, table, rule
) -> None:  # type: ignore[no-untyped-def]
    cls_of = {s["name"]: s["class"] for s in table.raw["subtypes"]}
    rng = random.Random(20261012)
    for _ in range(40):
        template = rng.choice(TEMPLATES)
        classes = {f: rng.choice([None, "A", "D"]) for f in AD}
        evidence = classes_to_vector(template, classes, registry)
        sub = rule.posterior_subtypes(make_record(template), evidence)
        cls = rule.posterior(make_record(template), evidence)
        assert sum(sub.values()) == pytest.approx(1.0, abs=1e-9)
        for c in CLASSES:
            total = math.fsum(p for s, p in sub.items() if cls_of[s] == c)
            assert cls[AttributedCause(c)] == pytest.approx(total, abs=1e-12)


@pytest.mark.parametrize("template", TEMPLATES)
def test_subtypes_are_the_ones_applicable_at_the_template(
    template, registry, table, rule
) -> None:  # type: ignore[no-untyped-def]
    expected = {
        c["subtype"] for c in table.raw["components"] if template in c["templates"]
    }
    applicable = rule.applicable_subtypes(template)
    assert set(applicable) == expected
    assert list(applicable) == sorted(applicable)
    sub = rule.posterior_subtypes(
        make_record(template), classes_to_vector(template, {}, registry)
    )
    assert set(sub) == expected
    assert not {"ecg_noise", "out_of_order"} & set(sub)  # applicable nowhere
    cls = rule.posterior(
        make_record(template), classes_to_vector(template, {}, registry)
    )
    impossible = table.raw["templates"][template]["impossible_classes"]
    for c in impossible:
        assert cls[AttributedCause(c)] == 0.0


def test_set_is_full_set_when_evidence_is_empty(registry, rule) -> None:  # type: ignore[no-untyped-def]
    # nothing read: the subtype posterior is flat inside the classes; the cumulative set reaches the level only with
    # most of the applicable subtypes, and the label abstains
    attributor = RuleAttributor(registry, load_templates(registry=registry), rule=rule)
    record = make_record("count")
    (alert,) = attributor.attribute_all([record], {})
    assert alert.kappa is AttributedCause.UNDETERMINED
    applicable = rule.applicable_subtypes("count")
    assert alert.cause_set is not None
    assert set(alert.cause_set) <= set(applicable)
    posterior = rule.posterior_subtypes(
        record, classes_to_vector("count", {}, registry)
    )
    # with the level at 1.0 the set would be the full set; the declared level is below that
    assert (
        len(alert.cause_set) >= math.ceil(rule.cumulative_level * len(applicable)) - 1
    )
    assert "not determined" in alert.xi.text
    for name in applicable:
        assert (
            name in alert.xi.text
        )  # UNDETERMINED is the full set of the applicable subtypes
    assert posterior


def test_prior_weights_inside_class_are_explicit_parameters(registry, table) -> None:  # type: ignore[no-untyped-def]
    evidence = classes_to_vector("range", {}, registry)
    record = make_record("range")
    uniform = build_rule(registry, table).posterior_subtypes(record, evidence)
    rare = build_rule(
        registry, table, sensitivity_values={**TEST_VALUES, "pi_designs": "quiet_rare"}
    ).posterior_subtypes(record, evidence)
    common = build_rule(
        registry,
        table,
        sensitivity_values={**TEST_VALUES, "pi_designs": "quiet_common"},
    ).posterior_subtypes(record, evidence)
    # range, C2: stuck_at and cuff_silent_bias are quiet, message_drop is not
    assert rare["stuck_at"] < uniform["stuck_at"] < common["stuck_at"]
    # inside one class the ratio of two weights is the ratio of the weights of the design (4 to 1 at quiet_common)
    # with the same likelihood: both read nothing, so the ratio of posteriors is the ratio of weights
    assert common["stuck_at"] / common["message_drop"] == pytest.approx(
        4.0 * uniform["stuck_at"] / uniform["message_drop"]
    )
    assert rare["stuck_at"] / rare["message_drop"] == pytest.approx(
        0.25 * uniform["stuck_at"] / uniform["message_drop"]
    )
    # the class posterior is the prior (flat evidence) and does not move with the within-class weights
    for design in (rare, common):
        assert sum(design.values()) == pytest.approx(1.0)


def test_class_priors_restricted_to_applicable_classes(registry, table) -> None:  # type: ignore[no-untyped-def]
    heavy = build_rule(
        registry, table, sensitivity_values={**TEST_VALUES, "class_priors": "c3_heavy"}
    )
    empty_sys = classes_to_vector("sys", {}, registry)
    cls = heavy.posterior(make_record("sys"), empty_sys)
    # C1 is impossible at sys; the C2 and C3 priors 0.2 and 0.6 are renormalised to 0.25 and 0.75
    assert cls[AttributedCause.C1_CLINICAL] == 0.0
    assert cls[AttributedCause.C2_SYSTEM] == pytest.approx(0.25)
    assert cls[AttributedCause.C3_INTEGRITY] == pytest.approx(0.75)


# ---- cross-check against the transcription of the specification ----------------------------------------------


def _random_classes(rng: random.Random) -> dict[str, str | None]:
    weights = (0.45, 0.3, 0.25)
    return {f: rng.choices([None, "A", "D"], weights)[0] for f in AD}


@pytest.mark.parametrize(
    ("options", "mask_extra", "grouped_off"),
    [
        ({}, frozenset(), False),
        ({"a4": True}, frozenset(A4_REMOVED), False),
        ({"grouped_variant": "fully_independent"}, frozenset(), True),
        ({"diagnostics_profile": "without_diagnostics"}, frozenset({DIAG}), False),
    ],
    ids=["reference", "a4", "fully_independent", "without_diagnostics"],
)
def test_matches_the_transcription_of_the_specification(
    options, mask_extra, grouped_off, registry, table
) -> None:  # type: ignore[no-untyped-def]
    rule = build_rule(registry, table, **options)
    rng = random.Random(20261012)
    for _ in range(120):
        template = rng.choice(TEMPLATES)
        classes = _random_classes(rng)
        evidence = classes_to_vector(template, classes, registry)
        readings = {f: c for f, c in classes.items()}
        _comp, sub, cls = reference_posterior(
            table.raw,
            template,
            readings,
            PARAMS,
            mask=mask_extra,
            grouped_off=grouped_off,
        )
        got_sub = rule.posterior_subtypes(make_record(template), evidence)
        got_cls = rule.posterior(make_record(template), evidence)
        assert set(got_sub) == set(sub)
        for name, value in sub.items():
            assert got_sub[name] == pytest.approx(value, abs=1e-9, rel=1e-9), (
                template,
                name,
            )
        for c in CLASSES:
            assert got_cls[AttributedCause(c)] == pytest.approx(
                cls[c], abs=1e-9, rel=1e-9
            )


# ---- grouped cells ---------------------------------------------------------------------------------------------------


def test_grouped_cell_normalisation_for_every_component_and_pattern(
    table, rule
) -> None:  # type: ignore[no-untyped-def]
    for comp in table.raw["components"]:
        for group in ("ble_seq_gap", "cross_device_signal_quality"):
            fields = table.raw["grouped_cells"][group]["fields"]
            # all members available: the K joint classes sum to 1
            total = 0.0
            for combo in itertools.product("AD", repeat=len(fields)):
                total += rule.joint_probability(
                    group, comp["id"], dict(zip(fields, combo, strict=True))
                )
            assert total == pytest.approx(1.0, abs=1e-12), (comp["id"], group)
            # a pattern with unavailable members: the marginal sums to 1 over the available ones
            for hidden in range(len(fields)):
                keep = [f for i, f in enumerate(fields) if i != hidden]
                marginal = 0.0
                for combo in itertools.product("AD", repeat=len(keep)):
                    readings: dict[str, str | None] = dict(
                        zip(keep, combo, strict=True)
                    )
                    readings[fields[hidden]] = None
                    marginal += rule.joint_probability(group, comp["id"], readings)
                assert marginal == pytest.approx(1.0, abs=1e-12), (
                    comp["id"],
                    group,
                    hidden,
                )
            nothing = dict.fromkeys(fields)
            assert rule.joint_probability(group, comp["id"], nothing) == pytest.approx(
                1.0
            )


def test_grouped_cell_formula_for_ble_dropout(rule) -> None:  # type: ignore[no-untyped-def]
    eps, qc = PARAMS["eps"], PARAMS["qc"]
    # modes of ble_dropout: gap_degraded (A, A) with qc, degraded (A, D) with 1 - qc; K = 4
    leak = eps / 3
    both = qc * (1 - eps) + (1 - qc) * leak
    assert rule.joint_probability(
        "ble_seq_gap", "ble_dropout", {BLE: "A", GAP: "A"}
    ) == pytest.approx(both)
    only_ble = (1 - qc) * (1 - eps) + qc * leak
    assert rule.joint_probability(
        "ble_seq_gap", "ble_dropout", {BLE: "A", GAP: "D"}
    ) == pytest.approx(only_ble)
    # None member: summed over
    assert rule.joint_probability(
        "ble_seq_gap", "ble_dropout", {BLE: "A", GAP: None}
    ) == pytest.approx(both + only_ble)
    # a component without modes has the single mode clean
    assert rule.joint_probability(
        "ble_seq_gap", "stuck_at", {BLE: "D", GAP: "D"}
    ) == pytest.approx(1 - eps)


def test_grouped_reference_differs_from_the_independent_product(
    registry, table
) -> None:  # type: ignore[no-untyped-def]
    grouped = build_rule(registry, table)
    independent = build_rule(registry, table, grouped_variant="fully_independent")
    evidence = classes_to_vector("hold", {BLE: "A", GAP: "A"}, registry)
    record = make_record("hold")
    g = grouped.posterior_subtypes(record, evidence)
    i = independent.posterior_subtypes(record, evidence)
    assert dict(g) != dict(i)
    assert grouped.metadata["grouped_variant"] == "reference"
    assert independent.metadata["grouped_variant"] == "fully_independent"


def test_cross_device_variant_adds_the_common_cause(registry, table) -> None:  # type: ignore[no-untyped-def]
    ref = build_rule(registry, table)
    cross = build_rule(registry, table, grouped_variant="reference_plus_cross_device")
    assert "ecg_noise" not in ref.applicable_subtypes("range")
    for template in ("range", "hold", "resp", "sys"):
        assert "ecg_noise" in cross.applicable_subtypes(template)
    for template in ("sched", "count", "int"):
        assert "ecg_noise" not in cross.applicable_subtypes(template)
    evidence = classes_to_vector(
        "range",
        {
            "cross_device.pulse_vs_ecg_hr_diff": "A",
            "signal_quality.ecg_sqi": "A",
            "signal_quality.ppg_sqi": "D",
        },
        registry,
    )
    sub = cross.posterior_subtypes(make_record("range"), evidence)
    assert sum(sub.values()) == pytest.approx(1.0)
    assert sub["ecg_noise"] > max(sub[s] for s in ("hypertensive_spike", "stuck_at"))


# ---- diagnostics profiles ----------------------------------------------------------------------------------------------


def test_without_diagnostics_does_not_read_the_field(registry, table) -> None:  # type: ignore[no-untyped-def]
    without = build_rule(registry, table, diagnostics_profile="without_diagnostics")
    assert DIAG not in without.read_fields("range")
    with_diag = classes_to_vector("range", {DIAG: "A"}, registry)
    none_diag = classes_to_vector("range", {}, registry)
    record = make_record("range")
    assert dict(without.posterior_subtypes(record, with_diag)) == dict(
        without.posterior_subtypes(record, none_diag)
    )
    driver = build_rule(registry, table)
    assert DIAG in driver.read_fields("range")
    assert dict(driver.posterior_subtypes(record, with_diag)) != dict(
        driver.posterior_subtypes(record, none_diag)
    )
    assert without.metadata["diagnostics_profile"] == "without_diagnostics"


def test_driver_stale_is_a_conditional_cell(registry, table) -> None:  # type: ignore[no-untyped-def]
    # stale (A) is raised by ble_dropout with q_stale, never near 1; C1 has the structural zero
    rule = build_rule(registry, table)
    sub = post(rule, "hold", {DIAG: "A"}, registry)
    assert sub["ble_dropout"] > sub["spontaneous_hold"]
    eps, q = PARAMS["eps"], PARAMS["q_stale"]
    ratio = sub["ble_dropout"] / sub["spontaneous_hold"]
    comps = [c for c in rule.table.components if "hold" in c.templates]
    n_c1 = sum(1 for c in comps if c.cls == "C1")
    n_c2 = sum(1 for c in comps if c.cls == "C2")
    # the likelihood ratio of the stale cell, times the ratio of the within-class weights (uniform)
    assert ratio == pytest.approx(
        (eps + (1 - 2 * eps) * q) / eps * n_c1 / n_c2, rel=1e-9
    )


# ---- reading classes of the added fields ---------------------------------------------------------------------------------


def test_reading_classes_of_the_added_fields(registry, table) -> None:  # type: ignore[no-untyped-def]
    rule = build_rule(registry, table)
    record = make_record("count")

    def p(fields: dict[str, Any]) -> dict[str, float]:
        return dict(rule.posterior_subtypes(record, vector("count", fields, registry)))

    nothing = p({})
    bounce = "dispenser.interval_since_previous_ms"
    assert p({bounce: 10_000}) == p({bounce: 0})  # at or below the threshold: A
    assert p({bounce: 10_001}) != p({bounce: 10_000})  # above: D
    assert p({bounce: 10_001}) == p({bounce: 10_000_000})
    assert p({bounce: None}) == nothing
    content = "dispenser.content_change"
    assert p({content: 0.0}) != p({content: 1.5})
    assert p({content: 0}) == p({content: 0.0})
    assert p({content: 1.5}) == p({content: 7.0})
    assert p({content: None}) == nothing
    # out of domain: read as unavailable, never raised
    assert p({bounce: -5}) == nothing
    assert p({content: float("nan")}) == nothing
    assert p({bounce: True}) == nothing
    # a bounce is the structural pattern of dispenser_bounce: both fields asserted put it on top at count
    both = p({bounce: 5_000, content: 0.0})
    assert max(both, key=both.__getitem__) == "dispenser_bounce"


# ---- decision record, kappa, decisive fields ------------------------------------------------------------------------------


def test_decision_record_contributions_and_decisive_fields(registry, rule) -> None:  # type: ignore[no-untyped-def]
    evidence = vector(
        "count",
        {
            AUTH: False,
            "crypto_temporal.seq_repeat": False,
            "system.liveliness_ok": True,
        },
        registry,
    )
    record = make_record("count")
    decision = rule.decide(record, evidence)
    assert decision.kappa is AttributedCause.C3_INTEGRITY
    assert decision.row is None and decision.reason is None
    assert decision.p_kappa == rule.posterior(record, evidence)
    assert decision.posterior_subtypes == rule.posterior_subtypes(record, evidence)
    assert decision.evidence_used[0] == AUTH  # the asserted authentication decides
    assert set(decision.evidence_used) <= {
        AUTH,
        "crypto_temporal.seq_repeat",
        "system.liveliness_ok",
    }
    # contributions: component id -> field -> log P(reading class | component), exactly additive
    contributions = decision.contributions
    assert contributions is not None
    eps = PARAMS["eps"]
    assert contributions["dispense_forgery_informed"][AUTH] == pytest.approx(
        math.log(1 - eps)
    )
    assert contributions["double_take"][AUTH] == pytest.approx(math.log(eps))
    assert set(contributions["double_take"]) == {
        AUTH,
        "crypto_temporal.seq_repeat",
        "system.liveliness_ok",
    }
    # the readings of the decisive fields are carried for the text
    values = dict(decision.readings)
    assert values[AUTH] is False
    class_contrib = decision.class_contributions
    assert class_contrib is not None
    assert set(class_contrib) == {"C1", "C2", "C3"}


def test_decisive_fields_of_a_clinical_attribution_are_the_channels_that_favour_it(
    registry, table
) -> None:  # type: ignore[no-untyped-def]
    rule = build_rule(registry, table, sensitivity_values={**TEST_VALUES, "tau": 0.5})
    read = {
        "system.liveliness_ok": "D",
        "system.node_lifecycle": "D",
        AUTH: "D",
        "signal_quality.cuff_error_code": "D",
        BLE: "D",
    }
    evidence = classes_to_vector("range", read, registry)
    decision = rule.decide(make_record("range"), evidence)
    assert decision.kappa is AttributedCause.C1_CLINICAL
    assert (
        decision.evidence_used
    )  # not empty: the denied channels pull towards C1 against the C2 mixture
    assert set(decision.evidence_used) <= set(read) | {GAP}
    assert "system.liveliness_ok" in decision.evidence_used
    assert len(decision.evidence_used) == len(set(decision.evidence_used))
    assert {p for p, _v in decision.readings} == set(decision.evidence_used)


def test_the_decision_of_a_provenance_mismatch_abstains_without_raising(
    registry, rule
) -> None:  # type: ignore[no-untyped-def]
    evidence = vector("count", {AUTH: False}, registry)
    broken = dataclasses.replace(
        evidence,
        provenance=dataclasses.replace(
            evidence.provenance,
            template_kind=vector("sys", {}, registry).provenance.template_kind,
        ),
    )
    decision = rule.decide(make_record("count"), broken)
    assert decision.kappa is AttributedCause.UNDETERMINED
    assert decision.p_kappa is None
    with pytest.raises(ValueError):
        rule.posterior(make_record("count"), broken)


# ---- the attributor -------------------------------------------------------------------------------------------------------------


def attributor_for(registry: Any, rule: Any, **kwargs: Any) -> Any:
    return RuleAttributor(
        registry, load_templates(registry=registry), rule=rule, **kwargs
    )


def test_alert_carries_p_kappa_set_and_evidence_used(registry, rule) -> None:  # type: ignore[no-untyped-def]
    from ralmon.conformal.sets import cumulative_level_set

    evidence = vector("count", {AUTH: False}, registry)
    record = make_record("count")
    (alert,) = attributor_for(registry, rule).attribute_all(
        [record], {record.instance_key: evidence}
    )
    assert alert.kappa is AttributedCause.C3_INTEGRITY
    assert alert.label is alert.kappa
    assert alert.p_kappa is not None
    assert alert.p_kappa == rule.posterior(record, evidence)
    assert math.fsum(alert.p_kappa.values()) == pytest.approx(1.0)
    posterior = rule.posterior_subtypes(record, evidence)
    assert alert.cause_set == cumulative_level_set(posterior, PARAMS_LEVEL)
    assert list(alert.cause_set) == sorted(
        alert.cause_set, key=lambda s: (-posterior[s], s)
    )
    assert list(alert.xi.evidence_used) == [AUTH]
    assert alert.verdict is VerdictState.VIOLATED


PARAMS_LEVEL = TEST_VALUES["cumulative_level"]


def test_text_states_probabilities_and_decisive_fields(registry, rule) -> None:  # type: ignore[no-untyped-def]
    evidence = vector("count", {AUTH: False}, registry)
    record = make_record("count")
    (alert,) = attributor_for(registry, rule).attribute_all(
        [record], {record.instance_key: evidence}
    )
    text = alert.xi.text
    assert "Attributed cause: integrity or plausibility violation" in text
    assert "0.97" in text  # p(C3)
    assert "C1 0.01" in text and "C2 0.01" in text and "C3 0.97" in text
    assert "message authentication failed (crypto_temporal.authenticated)" in text
    for name in alert.cause_set:
        assert name in text
    assert "tau" in text or "threshold" in text
    for banned in (
        "ensures",
        "intrinsic explainab",
        "orthogonal",
        "distribution-free",
        "proves",
    ):
        assert banned not in text


def test_text_of_an_abstention_names_the_full_applicable_set(registry, table) -> None:  # type: ignore[no-untyped-def]
    rule = build_rule(registry, table, sensitivity_values={**TEST_VALUES, "tau": 0.99})
    evidence = vector("count", {AUTH: False}, registry)
    record = make_record("count")
    (alert,) = attributor_for(registry, rule).attribute_all(
        [record], {record.instance_key: evidence}
    )
    assert alert.kappa is AttributedCause.UNDETERMINED
    text = alert.xi.text
    assert "Attributed cause: not determined" in text
    assert "0.99" in text and "0.97" in text
    for name in rule.applicable_subtypes("count"):
        assert name in text
    assert alert.cause_set is not None


def test_predicted_violation_is_undetermined_without_posterior(registry, rule) -> None:  # type: ignore[no-untyped-def]
    record = make_record(
        "range",
        state=VerdictState.PREDICTED_VIOLATION,
        rho=predicted_rho(),
        predicted_sigma_norm=-0.3,
    )
    evidence = vector("range", {"system.liveliness_ok": False}, registry)
    (alert,) = attributor_for(registry, rule).attribute_all(
        [record], {record.instance_key: evidence}
    )
    assert alert.verdict is VerdictState.PREDICTED_VIOLATION
    assert alert.kappa is AttributedCause.UNDETERMINED  # CP13: by definition
    assert alert.p_kappa is None and alert.cause_set is None
    assert list(alert.xi.evidence_used) == []


def test_injected_set_selector_replaces_the_cumulative_set(registry, rule) -> None:  # type: ignore[no-untyped-def]
    calls: list[tuple[str, str, tuple[str, ...]]] = []

    def selector(
        posteriors: Mapping[str, float], template: TemplateId, instance_key: str
    ) -> tuple[str, ...]:
        calls.append((template.value, instance_key, tuple(sorted(posteriors))))
        top = max(posteriors, key=lambda s: (posteriors[s], s))
        return (top,)

    evidence = vector("count", {AUTH: False}, registry)
    record = make_record("count", key="count@1")
    (alert,) = attributor_for(registry, rule, set_selector=selector).attribute_all(
        [record], {"count@1": evidence}
    )
    assert alert.cause_set is not None and len(alert.cause_set) == 1
    assert calls == [
        ("count", "count@1", tuple(sorted(rule.applicable_subtypes("count"))))
    ]
    # a rule that makes no cumulative set, with a selector: accepted
    # a selector that returns nothing or a subtype outside the posterior: refused
    for bad in ((), ("not_a_subtype",)):
        with pytest.raises(ValueError):
            attributor_for(
                registry, rule, set_selector=lambda p, t, k, bad=bad: bad
            ).attribute_all(  # type: ignore[misc]
                [record], {"count@1": evidence}
            )


def test_selector_lets_the_rule_skip_the_cumulative_level(registry, table) -> None:  # type: ignore[no-untyped-def]
    values = {k: v for k, v in TEST_VALUES.items() if k != "cumulative_level"}
    rule = build_rule(
        registry, table, sensitivity_values=values, needs_cumulative_level=False
    )
    evidence = vector("count", {AUTH: False}, registry)
    record = make_record("count", key="count@1")
    attributor = attributor_for(registry, rule, set_selector=lambda p, t, k: (min(p),))
    (alert,) = attributor.attribute_all([record], {"count@1": evidence})
    assert alert.cause_set == (min(rule.applicable_subtypes("count")),)


def test_cascade_effect_carries_the_p_kappa_of_its_root(registry, rule) -> None:  # type: ignore[no-untyped-def]
    from tests.attribution.test_cascades import (
        evidence_for,
        guard_record,
        root_record,
    )

    root_evidence = evidence_for(registry, "W-11")
    effect_evidence = evidence_for(registry, "W-11-resp")
    records = [
        root_record(),
        guard_record("resp", "resp@07:00", 10, 0, "obligation_unmet"),
    ]
    alerts = {
        a.xi.instance_key: a
        for a in attributor_for(registry, rule).attribute_all(
            records, {"sched@09:00": root_evidence, "resp@07:00": effect_evidence}
        )
    }
    root, effect = alerts["sched@09:00"], alerts["resp@07:00"]
    assert root.kappa is AttributedCause.C2_SYSTEM
    assert effect.caused_by == "sched@09:00"
    assert effect.kappa is root.kappa
    assert effect.p_kappa == root.p_kappa and effect.p_kappa is not None
    assert effect.cause_set == root.cause_set


def test_update_equals_attribute_all_with_the_likelihood_rule(registry, rule) -> None:  # type: ignore[no-untyped-def]
    evidence = vector("count", {AUTH: False}, registry)
    record = make_record("count", key="count@1")
    one = attributor_for(registry, rule)
    two = attributor_for(registry, rule)
    assert two.update([record], {"count@1": evidence}) == one.attribute_all(
        [record], {"count@1": evidence}
    )


# ---- guards ----------------------------------------------------------------------------------------------------------------------


def test_no_ground_truth_and_no_forbidden_import_in_the_module() -> None:
    tree = ast.parse(LIKELIHOOD_PY.read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
    joined = " ".join(imported)
    for banned in (
        "benchmark",
        "LatentDay",
        "GroundTruthEvent",
        "conformal",
        "ralmon.eval",
        "baselines",
    ):
        assert banned not in joined, banned
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
        n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
    }
    assert not names & {
        "LatentDay",
        "GroundTruthEvent",
        "rho",
        "sigma_interval",
        "sigma_norm_interval",
        "state",
        "decided_at_ms",
        "t_eval_ms",
    }


def test_cumulative_set_agrees_with_the_conformal_module(registry, rule) -> None:  # type: ignore[no-untyped-def]
    from ralmon.conformal.sets import cumulative_level_set

    rng = random.Random(7)
    for _ in range(30):
        template = rng.choice(TEMPLATES)
        evidence = classes_to_vector(template, _random_classes(rng), registry)
        posterior = rule.posterior_subtypes(make_record(template), evidence)
        for level in (0.8, 0.9, 0.95):
            local = rule.cumulative_set(posterior, level=level)
            assert local == cumulative_level_set(posterior, level)


def test_table_loader_validates_the_file(tmp_path: Path) -> None:
    from ralmon.attribution.likelihood import (
        LikelihoodConfigError,
        load_likelihood_table,
    )

    text = CONFIG_PATH.read_text(encoding="utf-8")
    broken = tmp_path / "broken.yaml"
    broken.write_text(text.replace("token: N", "token: Q", 1), encoding="utf-8")
    with pytest.raises(LikelihoodConfigError):
        load_likelihood_table(broken)
    with pytest.raises(LikelihoodConfigError):
        load_likelihood_table(tmp_path / "missing.yaml")
    table = load_likelihood_table(CONFIG_PATH)
    assert table.sha256 and len(table.sha256) == 64
    assert table.schema_version == "0.1.0"
