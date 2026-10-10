"""The natural-language text of ``Explanation.text`` (WS05-T07 tests 21 to 27).

The wording is specification-level traceability (docs/formal/07-alert-tuple-mapping.md section 3.4), generated from
the fields of the alert, never typed per case. The expected fragments are fixed strings of the renderer; the numbers
are fixture arithmetic (F0), not clinical values.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from ralmon.monitor import VerdictState
from ralmon.spec import TemplateId, load_templates
from tests.fixtures.attribution import (
    case_ids,
    hms,
    load_fixture_registry,
    make_record,
    measured_rho,
    predicted_rho,
    vector,
    worked_case,
)

FORBIDDEN = (
    "PILL",
    "subsystem",
    "tampering",
    "ensures",
    "intrinsic explainab",
    "orthogonal",
    "edge cloud",
    "distribution-free",
)


@pytest.fixture(scope="module")
def registry():  # type: ignore[no-untyped-def]
    return load_fixture_registry()


@pytest.fixture(scope="module")
def attributor(registry):  # type: ignore[no-untyped-def]
    from ralmon.attribution import RuleAttributor

    return RuleAttributor(registry, load_templates(registry=registry))


def alert_of(
    attributor: Any, registry: Any, case_id: str, record: Any = None, **kwargs: Any
) -> Any:
    case = worked_case(case_id)
    record = (
        record
        if record is not None
        else make_record(case["template"], key=f"{case['template']}@1")
    )
    evidence = {record.instance_key: vector(case["template"], case["fields"], registry)}
    (alert,) = attributor.attribute_all([record], evidence)
    return alert


def range_alert(attributor: Any, registry: Any) -> Any:
    record = make_record(
        "range",
        key="range@32700000",
        decided_at_ms=hms(9, 5),
        hi=-12.0,
        sigma_norm=(-0.6, -0.6),
        rho=measured_rho(0.9772),
    )
    return alert_of(attributor, registry, "W-01", record)


# ---- test 21 ------------------------------------------------------------------------------------


def test_rendering_contains_traceability_fields(attributor, registry) -> None:  # type: ignore[no-untyped-def]
    alert = range_alert(attributor, registry)
    text = alert.xi.text
    assert "the measured blood pressure inside the prescribed band" in text
    assert "violated (definitive)" in text
    assert "bp_band_low 110 mmHg" in text and "bp_band_high 140 mmHg" in text
    assert (
        "-12 mmHg" in text
        and "-0.60" in text
        and "scale of 20 mmHg (unreviewed)" in text
    )
    assert "Confidence: 0.98" in text and "kind: measured" in text
    assert alert.rho.guarantee in text
    assert "Attributed cause: clinical or adherence deviation" in text
    for path in alert.xi.evidence_used:
        assert f"({path})" in text
    assert next(iter(alert.xi.evidence_used)) == "system.node_lifecycle"
    assert "09:05" in text and "range@32700000" in text
    # an unreviewed registry value is labelled as such (ADR-020)
    assert text.count("unreviewed") >= 2


def test_rendering_of_a_scheduled_measurement_reports_the_certified_bound(
    attributor, registry
) -> None:  # type: ignore[no-untyped-def]
    """A violated SCHED alert at its deadline reports the certified bound and not an incurred delay (requirement 8)."""
    record = make_record(
        "sched",
        key="sched@32400000",
        decided_at_ms=hms(9, 30),
        hi=-60_000.0,
        lo=-1_800_000.0,
        sigma_norm=(-1.0, -0.0333),
        guard_failed="no_measurement_after_tick",
    )
    alert = alert_of(attributor, registry, "W-11", record)
    text = alert.xi.text
    assert "was not taken by the deadline" in text
    assert "late by at least one monitor step" in text
    assert "is late by" not in text
    assert "sched_window 30 minutes" in text
    assert "(system.liveliness_ok)" in text
    assert "system or embodiment failure" in text
    final = dataclasses.replace(
        record,
        sigma_interval=dataclasses.replace(record.sigma_interval, hi=float("-inf")),
    )
    text = alert_of(attributor, registry, "W-11", final).xi.text
    assert "maximum of the scale" in text


# ---- test 22 ------------------------------------------------------------------------------------


def test_rendering_is_deterministic_and_locale_free(
    attributor, registry, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    from ralmon.attribution.alert import alert_from_record
    from ralmon.attribution.render import render_text
    from ralmon.attribution.rule import HierarchicalRule

    first = range_alert(attributor, registry)
    monkeypatch.setenv("LC_ALL", "tr_TR.UTF-8")
    monkeypatch.setenv("LANG", "de_DE.UTF-8")
    monkeypatch.setenv("TZ", "Pacific/Kiritimati")
    second = range_alert(attributor, registry)
    assert first.xi.text == second.xi.text
    assert first == second

    # no dependence on the iteration order of the parameter mapping
    templates = {t.id: t for t in load_templates(registry=registry)}
    record = make_record(
        "range",
        key="range@32700000",
        decided_at_ms=hms(9, 5),
        hi=-12.0,
        sigma_norm=(-0.6, -0.6),
    )
    decision = HierarchicalRule(registry).decide(
        record, vector("range", worked_case("W-01")["fields"], registry)
    )
    forward = {"bp_band_low": 110.0, "bp_band_high": 140.0}
    backward = dict(reversed(list(forward.items())))
    a = alert_from_record(
        record, decision, templates[TemplateId.RANGE], registry, param_values=forward
    )
    b = alert_from_record(
        record, decision, templates[TemplateId.RANGE], registry, param_values=backward
    )
    assert a.xi.text == b.xi.text

    # the text is regenerated from the alert, its record, the decision and the template (TR-4)
    assert (
        render_text(a, record, decision, templates[TemplateId.RANGE], registry)
        == a.xi.text
    )


# ---- test 23 ------------------------------------------------------------------------------------


@pytest.mark.parametrize("case_id", case_ids())
def test_rendering_never_uses_forbidden_terms(
    case_id: str, attributor, registry
) -> None:  # type: ignore[no-untyped-def]
    case = worked_case(case_id)
    record = make_record(case["template"], key=f"{case['template']}@1")
    alert = alert_of(attributor, registry, case_id, record)
    lowered = alert.xi.text.lower()
    for term in FORBIDDEN:
        assert term.lower() not in lowered, (case_id, term)
    assert alert.xi.text == alert.xi.text.strip() and alert.xi.text
    assert "\n" not in alert.xi.text


def test_forbidden_terms_in_predicted_and_cascade_texts(attributor, registry) -> None:  # type: ignore[no-untyped-def]
    texts = [
        predicted_alert(attributor, registry, "possible").xi.text,
        predicted_alert(attributor, registry, "likely").xi.text,
    ]
    texts.append(predicted_alert(attributor, registry, None).xi.text)
    for text in texts:
        for term in FORBIDDEN:
            assert term.lower() not in text.lower()


# ---- test 24 ------------------------------------------------------------------------------------

CAUSE_WORDS = (
    "clinical or adherence deviation",
    "system or embodiment failure",
    "integrity or plausibility violation",
)


def test_undetermined_rendering_names_the_missing_channels(
    attributor, registry
) -> None:  # type: ignore[no-untyped-def]
    # insufficient: the channels needed to exclude the other causes were not available (W-02-A4)
    alert = alert_of(attributor, registry, "W-02-A4")
    text = alert.xi.text
    assert "Attributed cause: not determined" in text
    assert "insufficient evidence" in text
    for path in (
        "system.nav_task_failed",
        "system.manip_task_failed",
        "witness.identity_confirmed",
        "witness.intake_observed",
        "crypto_temporal.authenticated",
    ):
        assert path in text, path
    assert not any(
        words in text for words in CAUSE_WORDS
    )  # an abstention names no class
    assert list(alert.xi.evidence_used) == []

    # conflict: asserted evidence that no rule accepts (W-05-deliberate: a deliberate transition is not a failure)
    text = alert_of(attributor, registry, "W-05-deliberate").xi.text
    assert "Attributed cause: not determined" in text
    assert "conflicting evidence" in text
    assert "(system.node_lifecycle)" in text
    assert "deliberate transition is not a failure" in text

    # provenance only: a system or integrity constraint with nothing asserted outside provenance (W-14)
    text = alert_of(attributor, registry, "W-14").xi.text
    assert "Attributed cause: not determined" in text
    assert "no other channel corroborates a cause" in text

    # count: the dispenser content evidence has no field in this contract version (W-06)
    text = alert_of(attributor, registry, "W-06").xi.text
    assert "no field in this contract version" in text


# ---- test 25 ------------------------------------------------------------------------------------


def predicted_alert(attributor: Any, registry: Any, variant: str | None) -> Any:
    from ralmon.attribution import RuleAttributor

    own = RuleAttributor(registry, load_templates(registry=registry), variant=variant)
    record = make_record(
        "sched",
        key="sched@32400000",
        state=VerdictState.PREDICTED_VIOLATION,
        t_eval_ms=hms(9, 10),
        hi=0.0,
        lo=-1_800_000.0,
        sigma_norm=(-1.0, 0.1),
        rho=predicted_rho(),
        predicted_sigma_norm=-0.2433,
    )
    (alert,) = own.attribute_all([record], {})
    return alert


def test_predicted_rendering_says_early_warning(attributor, registry) -> None:  # type: ignore[no-untyped-def]
    alert = predicted_alert(attributor, registry, "possible")
    text = alert.xi.text
    assert "early warning" in text
    assert "not a definitive verdict" in text
    assert "marginal over patient episodes under exchangeability" in text
    assert "not the probability that the violation will occur" in text
    assert "possible-violation early warning" in text
    assert "pessimistic end of the range" in text
    assert "Attributed cause: not determined" in text
    assert "violated (definitive)" not in text
    assert "-0.24" in text
    likely = predicted_alert(attributor, registry, "likely").xi.text
    assert "likely-violation early warning" in likely
    assert "at least this severe" in likely and "pessimistic" not in likely


# ---- test 26 ------------------------------------------------------------------------------------


def test_dispense_and_intake_are_not_conflated(attributor, registry) -> None:  # type: ignore[no-untyped-def]
    integrity = alert_of(attributor, registry, "W-09").xi.text  # int: provenance only
    assert "dispense" in integrity.lower()
    assert "intake" not in integrity.lower()
    witness = alert_of(
        attributor, registry, "W-02"
    ).xi.text  # resp: backed by the robot witness
    assert "intake observed by the robot (witness.intake_observed)" in witness
    assert "dispense" in witness.lower()
    assert "dose was taken" not in witness.lower()
    for case_id in case_ids():
        text = alert_of(attributor, registry, case_id).xi.text.lower()
        assert "taken because the dispenser opened" not in text


# ---- test 27 ------------------------------------------------------------------------------------


def test_explanation_fields(attributor, registry) -> None:  # type: ignore[no-untyped-def]
    record = make_record(
        "range",
        key="range@32700000",
        decided_at_ms=hms(9, 5),
        hi=-12.0,
        sigma_norm=(-0.6, -0.6),
        subformula_path="range/0/1",
    )
    alert = alert_of(attributor, registry, "W-01", record)
    xi = alert.xi
    assert xi.template is TemplateId.RANGE == alert.tau
    assert xi.instance_key == "range@32700000"
    assert xi.subformula_path == "range/0/1"
    assert dict(xi.param_values) == {"bp_band_low": 110.0, "bp_band_high": 140.0}
    assert list(xi.evidence_used) == worked_case("W-01")["decisive"]
    assert isinstance(xi.text, str) and xi.text
    # a record without a path has no source for the field
    bare = alert_of(attributor, registry, "W-01", make_record("range", key="range@2"))
    assert bare.xi.subformula_path == ""
    # a predicted alert has no decisive evidence
    assert list(predicted_alert(attributor, registry, None).xi.evidence_used) == []


def test_violated_sub_formula_is_named_when_the_path_resolves(
    attributor, registry
) -> None:  # type: ignore[no-untyped-def]
    """Hand-over (3) of WS05-T04: the text of the violated sub-formula comes from the path of the record."""
    sched = make_record(
        "sched",
        key="sched@32400000",
        decided_at_ms=hms(9, 30),
        hi=float("-inf"),
        lo=float("-inf"),
        sigma_norm=(-1.0, -1.0),
        guard_failed="no_measurement_after_tick",
        subformula_path="sched/0/1",
    )
    text = alert_of(attributor, registry, "W-11", sched).xi.text
    assert "Violated sub-formula: once[0, sched_window] (meas and age >= 0)." in text
    assert "(failed guard: no_measurement_after_tick)" in text
    # a path that does not resolve loses the sentence and not the alert
    broken = dataclasses.replace(sched, subformula_path="sched/9/9/9")
    other = alert_of(attributor, registry, "W-11", broken)
    assert "Violated sub-formula" not in other.xi.text
    assert other.xi.subformula_path == "sched/9/9/9"
