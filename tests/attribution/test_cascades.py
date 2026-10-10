"""Cascades and incremental use (WS05-T07 tests 14 to 20).

The case W-11 of ``attribution-rule.md`` (the row 15:00 of analisi 4.6 with the templates of the library): a missed
measurement (a violated ``sched`` with the cuff lapse as system evidence, root C2) and the downstream violations that
the missing measurement causes. Times are the F0 fixture numbers of the document.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from itertools import pairwise
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ralmon.monitor import VerdictState
from ralmon.spec import rank_alerts
from tests.fixtures.attribution import (
    hms,
    load_fixture_registry,
    make_record,
    predicted_rho,
    vector,
    worked_case,
)
from tests.fixtures.attribution.strategies import EVIDENCE_KINDS, cascade_sets

INF = float("inf")


@pytest.fixture(scope="module")
def registry():  # type: ignore[no-untyped-def]
    return load_fixture_registry()


@pytest.fixture
def attributor(registry):  # type: ignore[no-untyped-def]
    from ralmon.attribution import RuleAttributor
    from ralmon.spec import load_templates

    return RuleAttributor(registry, load_templates(registry=registry))


def root_record() -> Any:
    return make_record(
        "sched",
        key="sched@09:00",
        decided_at_ms=hms(9, 30),
        hi=-60_000.0,
        lo=-1_800_000.0,
        sigma_norm=(-1.0, -0.0333),
        guard_failed="no_measurement_after_tick",
    )


def guard_record(template: str, key: str, hh: int, mm: int, guard: str) -> Any:
    return make_record(
        template,
        key=key,
        decided_at_ms=hms(hh, mm),
        hi=-INF,
        lo=-INF,
        sigma_norm=(-1.0, -1.0),
        guard_failed=guard,
    )


def margin_record(template: str, key: str, hh: int, mm: int) -> Any:
    return make_record(
        template,
        key=key,
        decided_at_ms=hms(hh, mm),
        hi=-4.0,
        lo=-8.0,
        sigma_norm=(-0.4, -0.2),
    )


def evidence_for(registry: Any, case_id: str) -> Any:
    case = worked_case(case_id)
    return vector(case["template"], case["fields"], registry)


def w11(registry: Any) -> tuple[list[Any], dict[str, Any]]:
    records = [
        root_record(),
        guard_record("resp", "resp@07:00", 10, 0, "obligation_unmet"),
        guard_record("hold", "hold@09:45", 9, 45, "no_recent_measurement"),
        margin_record("resp", "resp@07:30", 10, 30),
    ]
    evidence = {
        "sched@09:00": evidence_for(registry, "W-11"),
        "resp@07:00": evidence_for(registry, "W-11-resp"),
        "hold@09:45": evidence_for(registry, "W-11-hold"),
        "resp@07:30": evidence_for(registry, "W-11-resp"),
    }
    return records, evidence


def by_key(alerts: Sequence[Any]) -> dict[str, Any]:
    return {a.xi.instance_key: a for a in alerts}


# ---- test 14 -----------------------------------------------------------------------------------


def test_cascade_row_15_00_of_analisi(attributor, registry) -> None:  # type: ignore[no-untyped-def]
    records, evidence = w11(registry)
    alerts = by_key(attributor.attribute_all(records, evidence))
    root = alerts["sched@09:00"]
    assert root.kappa.value == "C2"
    assert root.caused_by is None
    assert list(root.root_cause_of) == [
        "hold@09:45",
        "resp@07:00",
    ]  # the sorted keys of its effects
    for key in ("resp@07:00", "hold@09:45"):
        effect = alerts[key]
        assert effect.caused_by == "sched@09:00"
        assert effect.kappa.value == "C2"  # the attributed cause of its root
        assert (
            list(effect.xi.evidence_used)
            == list(root.xi.evidence_used)
            == ["system.liveliness_ok"]
        )
        assert list(effect.root_cause_of) == []
        assert (
            "sched@09:00" in effect.xi.text
        )  # an effect says that it follows from the root and names it
    # the effects keep their own severity, confidence, priority and time
    assert alerts["resp@07:00"].sigma_norm == -1.0
    assert alerts["resp@07:00"].t_ms == hms(10, 0)
    assert alerts["hold@09:45"].t_ms == hms(9, 45)
    assert alerts["resp@07:00"].priority == int(registry.get("priority_resp").value)
    # a root says how many further violations it accounts for
    assert "2 further violations" in root.xi.text


def test_w11_independent_evidence_and_variants(attributor, registry) -> None:  # type: ignore[no-untyped-def]
    records, evidence = w11(registry)
    alerts = by_key(attributor.attribute_all(records, evidence))
    # resp@07:30 has a valid measurement in its window and fails on the margin: not folded, own kappa
    margin = alerts["resp@07:30"]
    assert margin.caused_by is None and margin.kappa.value == "C2"
    assert "resp@07:30" not in alerts["sched@09:00"].root_cause_of

    # W-11-c3: resp@07:00 also has a failed verification: its own result C3 differs from the root's C2
    evidence["resp@07:00"] = evidence_for(registry, "W-11-c3")
    alerts = by_key(attributor.attribute_all(records, evidence))
    assert alerts["resp@07:00"].caused_by is None
    assert alerts["resp@07:00"].kappa.value == "C3"
    assert list(alerts["sched@09:00"].root_cause_of) == ["hold@09:45"]

    # W-11-deliberate: a commanded deactivation gives the root UNDETERMINED: it seeds nothing
    evidence = {
        "sched@09:00": evidence_for(registry, "W-11-deliberate"),
        "resp@07:00": evidence_for(registry, "W-11-deliberate"),
        "hold@09:45": evidence_for(registry, "W-11-hold"),
    }
    alerts = by_key(attributor.attribute_all(records[:3], evidence))
    assert alerts["sched@09:00"].kappa.value == "UNDETERMINED"
    assert list(alerts["sched@09:00"].root_cause_of) == []
    assert alerts["resp@07:00"].caused_by is None
    assert alerts["hold@09:45"].caused_by is None
    assert alerts["hold@09:45"].kappa.value == "C2"  # its own result is kept


def test_w11_late_root_does_not_fold(attributor, registry) -> None:  # type: ignore[no-untyped-def]
    """The hold dispensed at 09:15 is decided before the root (09:30): it stays top-level (rule 2 and 7)."""
    early = guard_record("hold", "hold@09:15", 9, 15, "no_recent_measurement")
    evidence = {
        "sched@09:00": evidence_for(registry, "W-11"),
        "hold@09:15": evidence_for(registry, "W-11-late-root"),
    }
    alerts = by_key(attributor.attribute_all([root_record(), early], evidence))
    assert alerts["hold@09:15"].caused_by is None
    assert alerts["hold@09:15"].kappa.value == "UNDETERMINED"
    assert list(alerts["sched@09:00"].root_cause_of) == []
    assert (
        "further" not in alerts["sched@09:00"].xi.text
    )  # no count sentence while no effect is linked
    # decided at the same time as the root: not folded either
    same = guard_record("hold", "hold@09:30", 9, 30, "no_recent_measurement")
    alerts = by_key(
        attributor.attribute_all(
            [root_record(), same],
            {
                "sched@09:00": evidence_for(registry, "W-11"),
                "hold@09:30": evidence_for(registry, "W-11-hold"),
            },
        )
    )
    assert alerts["hold@09:30"].caused_by is None


def test_w11_predicted_effect_takes_no_part(attributor, registry) -> None:  # type: ignore[no-untyped-def]
    predicted = make_record(
        "resp",
        key="resp@07:00",
        state=VerdictState.PREDICTED_VIOLATION,
        t_eval_ms=hms(9, 50),
        hi=0.0,
        sigma_norm=(-1.0, 0.1),
        rho=predicted_rho(),
        predicted_sigma_norm=-0.3,
    )
    alerts = by_key(
        attributor.attribute_all(
            [root_record(), predicted],
            {
                "sched@09:00": evidence_for(registry, "W-11"),
                "resp@07:00": evidence_for(registry, "W-11-resp"),
            },
        )
    )
    assert alerts["resp@07:00"].kappa.value == "UNDETERMINED"
    assert alerts["resp@07:00"].verdict is VerdictState.PREDICTED_VIOLATION
    assert alerts["resp@07:00"].caused_by is None
    assert list(alerts["sched@09:00"].root_cause_of) == []


# ---- test 15 -----------------------------------------------------------------------------------


def test_independent_evidence_prevents_folding(attributor, registry) -> None:  # type: ignore[no-untyped-def]
    """A response violated on its margin, or with a different definite cause, stays top-level."""
    root = root_record()
    root_ev = evidence_for(registry, "W-11")
    effect_margin = margin_record("resp", "resp@07:00", 10, 0)
    alerts = by_key(
        attributor.attribute_all(
            [root, effect_margin], {"sched@09:00": root_ev, "resp@07:00": root_ev}
        )
    )
    assert alerts["resp@07:00"].caused_by is None
    assert alerts["sched@09:00"].root_cause_of == ()
    # the same record without a guard marker and with a finite upper end is a margin violation
    guard = guard_record("resp", "resp@07:00", 10, 0, "obligation_unmet")
    alerts = by_key(
        attributor.attribute_all(
            [root, guard], {"sched@09:00": root_ev, "resp@07:00": root_ev}
        )
    )
    assert alerts["resp@07:00"].caused_by == "sched@09:00"
    # an effect whose own result is UNDETERMINED is folded and takes the root's cause
    alerts = by_key(attributor.attribute_all([root, guard], {"sched@09:00": root_ev}))
    assert alerts["resp@07:00"].caused_by == "sched@09:00"
    assert alerts["resp@07:00"].kappa.value == "C2"


def test_root_selection_takes_the_earliest_eligible_root(attributor, registry) -> None:  # type: ignore[no-untyped-def]
    first = dataclasses.replace(root_record(), instance_key="sched@09:00")
    second = dataclasses.replace(
        root_record(),
        instance_key="sched@09:10",
        decided_at_ms=hms(9, 40),
        t_eval_ms=hms(9, 40),
    )
    effect = guard_record("hold", "hold@09:45", 9, 45, "no_recent_measurement")
    ev = evidence_for(registry, "W-11")
    evidence = {
        "sched@09:00": ev,
        "sched@09:10": ev,
        "hold@09:45": evidence_for(registry, "W-11-hold"),
    }
    alerts = by_key(attributor.attribute_all([second, effect, first], evidence))
    assert alerts["hold@09:45"].caused_by == "sched@09:00"
    assert (
        list(alerts["sched@09:10"].root_cause_of) == []
    )  # the other eligible root does not list it


# ---- test 16 and 17 ----------------------------------------------------------------------------


def test_effects_are_returned_but_filterable(attributor, registry) -> None:  # type: ignore[no-untyped-def]
    records, evidence = w11(registry)
    alerts = list(attributor.attribute_all(records, evidence))
    assert len(alerts) == 4  # roots and effects
    top = [a for a in alerts if a.caused_by is None]
    assert sorted(a.xi.instance_key for a in top) == ["resp@07:30", "sched@09:00"]


def test_alerts_come_out_in_rank_order(attributor, registry) -> None:  # type: ignore[no-untyped-def]
    records, evidence = w11(registry)
    alerts = list(attributor.attribute_all(records, evidence))
    assert alerts == rank_alerts(alerts)
    assert alerts == list(attributor.attribute_all(list(reversed(records)), evidence))


# ---- test 18 -----------------------------------------------------------------------------------


def test_update_returns_only_new_or_changed_alerts(attributor, registry) -> None:  # type: ignore[no-untyped-def]
    root = root_record()
    effect = guard_record("hold", "hold@09:45", 9, 45, "no_recent_measurement")
    ev_root = {"sched@09:00": evidence_for(registry, "W-11")}
    ev_effect = {"hold@09:45": evidence_for(registry, "W-11-hold")}

    first = list(attributor.update([root], ev_root))
    assert [a.xi.instance_key for a in first] == ["sched@09:00"]
    assert list(first[0].root_cause_of) == []

    second = list(attributor.update([effect], ev_effect))
    assert [a.xi.instance_key for a in second] == ["hold@09:45", "sched@09:00"]
    new_effect, reissued = second
    assert new_effect.caused_by == "sched@09:00" and new_effect.kappa.value == "C2"
    assert list(reissued.root_cause_of) == ["hold@09:45"]
    # the re-issue of the root changes only root_cause_of and the sentence derived from it
    restated = dataclasses.replace(
        first[0],
        root_cause_of=reissued.root_cause_of,
        xi=dataclasses.replace(first[0].xi, text=reissued.xi.text),
    )
    assert restated == reissued
    assert reissued.xi.text != first[0].xi.text

    assert (
        list(attributor.update([effect], ev_effect)) == []
    )  # an identical call changes nothing
    assert list(attributor.update([root, effect], {**ev_root, **ev_effect})) == []
    # evidence that arrives later does not change an alert already issued
    assert (
        list(
            attributor.update(
                [root], {"sched@09:00": evidence_for(registry, "W-11-c3")}
            )
        )
        == []
    )


# ---- test 19 -----------------------------------------------------------------------------------


@settings(max_examples=80, deadline=None)
@given(items=cascade_sets(), data=st.data())
def test_update_equals_attribute_all_for_any_batching(items, data, registry) -> None:  # type: ignore[no-untyped-def]
    from ralmon.attribution import RuleAttributor
    from ralmon.spec import load_templates

    attributor = RuleAttributor(registry, load_templates(registry=registry))

    def when(item: tuple[Any, str]) -> tuple[int, str]:
        record = item[0]
        return (
            record.decided_at_ms
            if record.decided_at_ms is not None
            else record.t_eval_ms,
            record.instance_key,
        )

    ordered = sorted(items, key=when)
    cuts = sorted(
        data.draw(st.lists(st.integers(0, len(ordered)), max_size=4)),
    )
    bounds = [0, *cuts, len(ordered)]
    batches = [ordered[a:b] for a, b in pairwise(bounds) if b > a]

    def evidence_of(batch: Sequence[tuple[Any, str]]) -> Mapping[str, Any]:
        return {
            r.instance_key: vector(r.template.value, EVIDENCE_KINDS[kind], registry)
            for r, kind in batch
        }

    final: dict[str, Any] = {}
    for batch in batches:
        for alert in attributor.update([r for r, _ in batch], evidence_of(batch)):
            final[alert.xi.instance_key] = alert
    expected = by_key(
        attributor.attribute_all([r for r, _ in ordered], evidence_of(ordered))
    )
    assert final == expected


# ---- test 20 -----------------------------------------------------------------------------------


def _predicted(key: str = "sched@09:00") -> Any:
    return make_record(
        "sched",
        key=key,
        state=VerdictState.PREDICTED_VIOLATION,
        t_eval_ms=hms(9, 10),
        hi=0.0,
        lo=-1_800_000.0,
        sigma_norm=(-1.0, 0.1),
        rho=predicted_rho(),
        predicted_sigma_norm=-0.2433,
    )


def test_predicted_alert_is_replaced_not_duplicated(attributor, registry) -> None:  # type: ignore[no-untyped-def]
    evidence = {"sched@09:00": evidence_for(registry, "W-11")}
    # CP13: the kappa of a predicted alert is UNDETERMINED by definition, the rule is not evaluated
    first = list(attributor.update([_predicted()], evidence))
    assert len(first) == 1
    predicted = first[0]
    assert predicted.verdict is VerdictState.PREDICTED_VIOLATION
    assert (
        predicted.kappa.value == "UNDETERMINED"
        and predicted.label.value == "UNDETERMINED"
    )
    assert list(predicted.xi.evidence_used) == []
    assert predicted.t_ms == hms(9, 10)
    assert predicted.sigma_norm == pytest.approx(-0.2433)

    second = list(attributor.update([root_record()], evidence))
    assert len(second) == 1  # one alert for the key
    assert second[0].xi.instance_key == "sched@09:00"
    assert second[0].verdict is VerdictState.VIOLATED
    assert second[0].kappa.value == "C2"
    assert [
        a.verdict for a in attributor.history if a.xi.instance_key == "sched@09:00"
    ] == [
        VerdictState.PREDICTED_VIOLATION,
        VerdictState.VIOLATED,
    ]


def test_predicted_alert_closed_by_satisfied_stays_in_history(attributor) -> None:  # type: ignore[no-untyped-def]
    assert len(list(attributor.update([_predicted("sched@10:00")], {}))) == 1
    satisfied = make_record(
        "sched",
        key="sched@10:00",
        state=VerdictState.SATISFIED,
        decided_at_ms=hms(10, 20),
        hi=60_000.0,
        lo=60_000.0,
        sigma_norm=(0.03, 0.03),
    )
    assert list(attributor.update([satisfied], {})) == []  # no new alert
    assert [a.verdict for a in attributor.history] == [VerdictState.PREDICTED_VIOLATION]
    assert "sched@10:00" in attributor.closed_predictions
    # the stateless view: a closed prediction is not in the current set
    assert (
        list(attributor.attribute_all([_predicted("sched@10:00"), satisfied], {})) == []
    )


def test_attribute_all_returns_the_violated_alert_of_a_key_only(
    attributor, registry
) -> None:  # type: ignore[no-untyped-def]
    evidence = {"sched@09:00": evidence_for(registry, "W-11")}
    both = list(attributor.attribute_all([_predicted(), root_record()], evidence))
    assert len(both) == 1 and both[0].verdict is VerdictState.VIOLATED
    only = list(attributor.attribute_all([_predicted()], evidence))
    assert len(only) == 1 and only[0].verdict is VerdictState.PREDICTED_VIOLATION
    # a PENDING record makes no alert
    pending = make_record(
        "sched", key="sched@11:00", state=VerdictState.PENDING, hi=60_000.0, lo=-5.0
    )
    assert list(attributor.attribute_all([pending], {})) == []
