"""``#evidencevector`` 0.2.0 (WS05-T13, ADR-074 amendment 3): the contract, the extractor, the rule and the documents.

The expected values are derived by hand from the contract text and from the worked checks of
``docs/models/evidence-channels.md``; the old verdicts of the worked cases are frozen here as literals (the values of
the 0.1.0 fixture), so that the regression does not depend on the regenerated fixture it checks.
"""

from __future__ import annotations

import ast
import dataclasses
import itertools
import math
import re
from pathlib import Path
from typing import Any

import pytest

from ralmon.signals import EventKind, SignalId
from tests.attribution.test_types import contract_classes
from tests.fixtures.attribution import (
    CONTRACT_PATHS,
    NON_PROVENANCE_PATHS,
    build_vector,
    case_ids,
    load_fixture_registry,
    make_record,
    worked_case,
)
from tests.fixtures.attribution.trace import (
    CUFF_ALL,
    Inputs,
    cuff_frame,
    event,
    evidence_dict,
    extractor,
    feed,
    hold_record,
    profile,
    robot_state,
    robot_task,
    sample,
)

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = (ROOT / "docs" / "plan" / "02-interfaces.md").read_text(encoding="utf-8")
EVIDENCE_CHANNELS = ROOT / "docs" / "models" / "evidence-channels.md"
FAULT_MODEL = ROOT / "docs" / "models" / "fault-model.md"

#: The group order and the fields of the contract 0.2.0 (the dispenser group is appended last).
EXPECTED_GROUPS: dict[str, tuple[str, ...]] = {
    "provenance": ("violated_template", "template_kind"),
    "system": (
        "node_lifecycle",
        "diagnostics_ok",
        "liveliness_ok",
        "qos_deadline_missed",
        "ble_link_quality",
        "battery_low",
        "nav_task_failed",
        "manip_task_failed",
        "seq_gap",
    ),
    "signal_quality": ("ecg_sqi", "ppg_sqi", "cuff_error_code", "cuff_value_repeated"),
    "cross_device": ("pulse_vs_ecg_hr_diff",),
    "witness": ("robot_present", "identity_confirmed", "intake_observed"),
    "crypto_temporal": ("authenticated", "seq_repeat", "timestamp_implausible"),
    "dispenser": ("interval_since_previous_ms", "content_change"),
}

#: Verdicts of the worked cases of the 0.1.0 table (kappa, row, reason): frozen literals.
OLD_VERDICTS: dict[str, tuple[str, int, str | None]] = {
    "W-01": ("C1", 5, None),
    "W-02": ("C1", 5, None),
    "W-02-A4": ("UNDETERMINED", 8, "insufficient"),
    "W-02-auth": ("C1", 5, None),
    "W-02-nowit": ("UNDETERMINED", 8, "insufficient"),
    "W-02-witness-only": ("UNDETERMINED", 8, "insufficient"),
    "W-02-auth-witness": ("C1", 5, None),
    "W-02-auth-A4": ("UNDETERMINED", 8, "insufficient"),
    "W-03": ("C2", 4, None),
    "W-03-sched": ("C2", 4, None),
    "W-04": ("C1", 5, None),
    "W-05": ("C2", 4, None),
    "W-05-A4": ("UNDETERMINED", 8, "insufficient"),
    "W-05-live": ("C2", 4, None),
    "W-05-live-A4": ("UNDETERMINED", 8, "insufficient"),
    "W-05-silent": ("UNDETERMINED", 8, "insufficient"),
    "W-05-silent-040": ("UNDETERMINED", 8, "insufficient"),
    "W-05-late-traffic": ("C1", 5, None),
    "W-05-deliberate": ("UNDETERMINED", 6, "conflict"),
    "W-06": ("UNDETERMINED", 8, "insufficient"),
    "W-07": ("UNDETERMINED", 8, "insufficient"),
    "W-08": ("C3", 1, None),
    "W-08-U": ("C3", 2, None),
    "W-08-U-noseq": ("UNDETERMINED", 6, "conflict"),
    "W-09": ("UNDETERMINED", 7, "provenance_only"),
    "W-09-A4": ("UNDETERMINED", 7, "provenance_only"),
    "W-09-A": ("C3", 1, None),
    "W-09-lag": ("C2", 4, None),
    "W-09-lag-late": ("UNDETERMINED", 7, "provenance_only"),
    "W-09-jump": ("C2", 4, None),
    "W-09-resp": ("UNDETERMINED", 6, "conflict"),
    "W-10": ("C1", 5, None),
    "W-10-A": ("C3", 1, None),
    "W-12-range": ("UNDETERMINED", 8, "insufficient"),
    "W-12-sched": ("UNDETERMINED", 8, "insufficient"),
    "W-12-hold": ("UNDETERMINED", 8, "insufficient"),
    "W-12-count": ("UNDETERMINED", 8, "insufficient"),
    "W-12-resp": ("UNDETERMINED", 8, "insufficient"),
    "W-12-sys": ("UNDETERMINED", 7, "provenance_only"),
    "W-12-int": ("UNDETERMINED", 7, "provenance_only"),
    "W-13": ("C2", 4, None),
    "W-13-C3": ("C3", 3, None),
    "W-13-U": ("UNDETERMINED", 8, "insufficient"),
    "W-14": ("UNDETERMINED", 7, "provenance_only"),
    "W-14-code": ("C2", 4, None),
    "W-15": ("C2", 4, None),
    "W-15-alone": ("UNDETERMINED", 6, "conflict"),
    "W-15-repeat": ("C3", 2, None),
    "W-15-jump": ("C2", 4, None),
    "W-11": ("C2", 4, None),
    "W-11-resp": ("C2", 4, None),
    "W-11-hold": ("C2", 4, None),
    "W-11-late-root": ("UNDETERMINED", 8, "insufficient"),
    "W-11-deliberate": ("UNDETERMINED", 6, "conflict"),
    "W-11-c3": ("C3", 1, None),
}


@pytest.fixture(scope="module")
def registry():  # type: ignore[no-untyped-def]
    return load_fixture_registry()


@pytest.fixture(scope="module")
def rule(registry):  # type: ignore[no-untyped-def]
    from ralmon.attribution import HierarchicalRule

    return HierarchicalRule(registry)


def at(hh: int, mm: int, ss: int = 0) -> int:
    return ((60 * hh + mm) * 60 + ss) * 1000


def I(*items: Any) -> Inputs:
    out = Inputs()
    for item in items:
        if hasattr(item, "signal"):
            out.samples.append(item)
        else:
            out.events.append(item)
    return out


CUFF_ONLY = profile(cuff=CUFF_ALL)


# ---- 1, 2: the contract ----------------------------------------------------------------------------------


def test_evidence_vector_fields_match_contract_0_2_0() -> None:
    from ralmon import attribution
    from ralmon.attribution.evidence import EVIDENCE_PATHS
    from ralmon.attribution.evidence import NON_PROVENANCE_PATHS as NP

    classes = contract_classes("EvidenceVector")
    assert "Version 0.2.0" in CONTRACT.split("## EvidenceVector\n", 1)[1][:200]
    top = classes["EvidenceVector"]
    assert tuple(top) == tuple(
        EXPECTED_GROUPS
    )  # seven groups, the dispenser group last
    assert top[-1] == "dispenser"
    group_class = {
        "provenance": "ProvenanceEvidence",
        "system": "SystemHealthEvidence",
        "signal_quality": "SignalQualityEvidence",
        "cross_device": "CrossDeviceEvidence",
        "witness": "EmbodiedWitnessEvidence",
        "crypto_temporal": "CryptoTemporalEvidence",
        "dispenser": "DispenserEvidence",
    }
    for group, names in EXPECTED_GROUPS.items():
        assert classes[group_class[group]] == list(names), group
        cls = getattr(attribution, group_class[group])
        assert [f.name for f in dataclasses.fields(cls)] == list(names), group
        assert cls.__dataclass_params__.frozen and hasattr(cls, "__slots__")
    paths = tuple(f"{g}.{n}" for g, names in EXPECTED_GROUPS.items() for n in names)
    assert len(paths) == 24
    assert EVIDENCE_PATHS == CONTRACT_PATHS == paths
    assert len(NP) == len(NON_PROVENANCE_PATHS) == 22
    # the new type annotations
    annotations = {
        "system.seq_gap": "bool | None",
        "signal_quality.cuff_value_repeated": "bool | None",
        "crypto_temporal.seq_repeat": "bool | None",
        "dispenser.interval_since_previous_ms": "int | None",
        "dispenser.content_change": "float | None",
    }
    block = re.search(
        r"```python\n(.*?)```", CONTRACT.split("## EvidenceVector\n", 1)[1], re.DOTALL
    )
    assert block is not None
    declared: dict[str, str] = {}
    for node in ast.parse(block.group(1)).body:
        if isinstance(node, ast.ClassDef):
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign) and isinstance(
                    stmt.target, ast.Name
                ):
                    group = (
                        next(g for g, c in group_class.items() if c == node.name)
                        if node.name in group_class.values()
                        else None
                    )
                    if group is not None:
                        declared[f"{group}.{stmt.target.id}"] = ast.unparse(
                            stmt.annotation
                        )
    for path, text in annotations.items():
        assert declared[path] == text, path


def test_dispenser_group_defaults_so_that_old_constructors_keep_working() -> None:
    from ralmon.attribution import DispenserEvidence, EvidenceVector
    from ralmon.attribution.evidence import empty_evidence
    from ralmon.spec import TemplateId

    assert DispenserEvidence() == DispenserEvidence(None, None)
    full = empty_evidence(TemplateId.RANGE)
    six = EvidenceVector(
        provenance=full.provenance,
        system=full.system,
        signal_quality=full.signal_quality,
        cross_device=full.cross_device,
        witness=full.witness,
        crypto_temporal=full.crypto_temporal,
    )  # ADR-032: the group is appended last with a default of None
    assert six.dispenser == DispenserEvidence(None, None) == full.dispenser


def test_old_sequence_field_is_gone_and_split_fields_exist() -> None:
    from ralmon.attribution import CryptoTemporalEvidence, SystemHealthEvidence
    from ralmon.attribution.evidence import EVIDENCE_PATHS

    assert "crypto_temporal.seq_gap_or_replay" not in EVIDENCE_PATHS
    names = {f.name for f in dataclasses.fields(CryptoTemporalEvidence)}
    assert "seq_gap_or_replay" not in names and "seq_repeat" in names
    assert "seq_gap" in {f.name for f in dataclasses.fields(SystemHealthEvidence)}
    block = re.search(
        r"```python\n(.*?)```", CONTRACT.split("## EvidenceVector\n", 1)[1], re.DOTALL
    )
    assert block is not None and "seq_gap_or_replay" not in block.group(1)


# ---- 3: sequence evidence from the trace -----------------------------------------------------------------

D120 = 120_000
FRAMES = [
    (at(20, 10, 20), 1),
    (at(20, 11, 10), 2),
    (at(20, 12, 5), 3),
    (at(20, 13, 0), 4),
]


def seq_inputs(skip: tuple[int, ...] = (), extra: tuple[Any, ...] = ()) -> Inputs:
    return I(*[cuff_frame(t, s) for t, s in FRAMES if s not in skip], *extra)


def seq_vector(registry: Any, inputs: Inputs, prof: Any = CUFF_ONLY) -> Any:
    ex = feed(extractor(registry, prof, reorder_delay_ms=D120), inputs)
    return ex.evidence_for(hold_record())


@pytest.mark.parametrize(
    ("inputs", "repeat", "gap", "ratio"),
    [
        (seq_inputs(), False, False, 1.0),
        (seq_inputs(extra=(cuff_frame(at(20, 11, 30), 2),)), True, False, 1.0),
        (seq_inputs(skip=(2,)), False, True, 0.75),
        (
            seq_inputs(skip=(2,), extra=(cuff_frame(at(20, 12, 30), 3),)),
            True,
            True,
            0.75,
        ),
        (
            seq_inputs(skip=(4,)),
            False,
            False,
            1.0,
        ),  # a trailing loss is not seen (EX-1 (l))
    ],
    ids=[
        "clean",
        "repeat-without-gap",
        "gap-without-repeat",
        "repeat-and-gap",
        "trailing-loss",
    ],
)
def test_extractor_seq_repeat_and_gap_from_the_trace(
    inputs: Inputs, repeat: bool, gap: bool, ratio: float, registry
) -> None:  # type: ignore[no-untyped-def]
    vec = seq_vector(registry, inputs)
    assert vec.crypto_temporal.seq_repeat is repeat
    assert vec.system.seq_gap is gap
    assert vec.system.ble_link_quality == pytest.approx(ratio)


def test_extractor_seq_none_conditions_carry_over(registry) -> None:  # type: ignore[no-untyped-def]
    # no device provides seq: both None, as the old field was
    vec = seq_vector(registry, seq_inputs(), profile(cuff={"two_clocks": True}))
    assert vec.crypto_temporal.seq_repeat is None and vec.system.seq_gap is None
    # a capable but silent cuff: the dispenser cannot deny (EX-3 (f))
    silent = I(sample(SignalId.DISPENSE, at(20, 50), seq=1))
    prof = profile(cuff=CUFF_ALL, dispenser={"seq": True})
    vec = seq_vector(registry, silent, prof)
    assert vec.crypto_temporal.seq_repeat is None and vec.system.seq_gap is None
    # no input at all and no profile
    vec = extractor(registry, profile()).evidence_for(hold_record())
    assert vec.crypto_temporal.seq_repeat is None and vec.system.seq_gap is None


def test_extractor_seq_gap_is_a_system_field_and_repeat_an_integrity_field(
    registry,
) -> None:  # type: ignore[no-untyped-def]
    """A pure loss (ble_dropout, message_drop) must not set the integrity field (ADR-034)."""
    vec = seq_vector(registry, seq_inputs(skip=(2, 3)))
    assert vec.system.seq_gap is True
    assert vec.crypto_temporal.seq_repeat is False


# ---- 4: the dispenser group from the DISPENSE payload ----------------------------------------------------

CONTENT = profile(cuff=CUFF_ALL, dispenser={"content_sensing": True})
NO_CONTENT = profile(cuff=CUFF_ALL, dispenser={})


def dispense(t: int, *, rx: int | None = None, **payload: float | str | bool) -> Any:
    return event(EventKind.DISPENSE, t, "dispenser", rx=rx, seq=None, **payload)


def dispenser_values(vec: Any) -> tuple[Any, Any]:
    return vec.dispenser.interval_since_previous_ms, vec.dispenser.content_change


def test_extractor_dispenser_group_from_dispense_payload(registry) -> None:  # type: ignore[no-untyped-def]
    release = I(
        dispense(at(20, 50), interval_since_previous_ms=43_200_000, content_change=1.0)
    )
    vec = feed(extractor(registry, CONTENT), release).evidence_for(hold_record())
    interval, content = dispenser_values(vec)
    assert interval == 43_200_000 and isinstance(interval, int)
    assert (
        content == 1.0 and content > 0.0
    )  # ADR-040 (2): a release is positive (before minus after)
    # a bounce: the latest opening of the window, a short interval and a zero content change
    bounce = I(
        dispense(at(20, 50), interval_since_previous_ms=43_200_000, content_change=1.0),
        dispense(at(20, 50, 4), interval_since_previous_ms=4_000, content_change=0.0),
    )
    vec = feed(extractor(registry, CONTENT), bounce).evidence_for(hold_record())
    assert dispenser_values(vec) == (4_000, 0.0)


def test_extractor_dispenser_none_when_absent(registry) -> None:  # type: ignore[no-untyped-def]
    # no opening in the window
    vec = extractor(registry, CONTENT).evidence_for(hold_record())
    assert dispenser_values(vec) == (None, None)
    # an opening whose payload carries no key (first opening of a stream: no previous opening)
    vec = feed(extractor(registry, CONTENT), I(dispense(at(20, 50)))).evidence_for(
        hold_record()
    )
    assert dispenser_values(vec) == (None, None)
    # content sensing not declared: the content change is None, the interval is still read
    only_interval = I(
        dispense(at(20, 50), interval_since_previous_ms=9_000, content_change=1.0)
    )
    vec = feed(extractor(registry, NO_CONTENT), only_interval).evidence_for(
        hold_record()
    )
    assert dispenser_values(vec) == (9_000, None)


@pytest.mark.parametrize(
    "payload",
    [
        {"interval_since_previous_ms": -1, "content_change": float("nan")},
        {"interval_since_previous_ms": True, "content_change": True},
        {"interval_since_previous_ms": 1.5, "content_change": "1"},
        {"interval_since_previous_ms": float("inf"), "content_change": float("inf")},
    ],
)
def test_extractor_dispenser_never_reports_a_negative_or_malformed_reading(
    payload: dict[str, Any], registry
) -> None:  # type: ignore[no-untyped-def]
    vec = feed(
        extractor(registry, CONTENT), I(dispense(at(20, 50), **payload))
    ).evidence_for(hold_record())
    interval, content = dispenser_values(vec)
    assert interval is None
    assert content is None or math.isfinite(content)


def test_extractor_dispenser_reads_only_what_was_received_by_the_cutoff(
    registry,
) -> None:  # type: ignore[no-untyped-def]
    late = I(
        dispense(at(20, 50), interval_since_previous_ms=8_000, content_change=1.0),
        dispense(
            at(20, 55),
            rx=at(23, 0),
            interval_since_previous_ms=2_000,
            content_change=0.0,
        ),  # arrives after the cut-off: not used
        dispense(
            at(18, 0), interval_since_previous_ms=7_000, content_change=1.0
        ),  # before the window: not used
    )
    vec = feed(extractor(registry, CONTENT), late).evidence_for(hold_record())
    assert dispenser_values(vec) == (8_000, 1.0)


def test_extractor_dispense_still_counts_as_a_dispense_sample(registry) -> None:  # type: ignore[no-untyped-def]
    """Keeping the payload does not stop the event from being an impulse sample (sequence evidence)."""
    items = I(
        dispense(at(20, 50), interval_since_previous_ms=8_000, content_change=1.0),
        cuff_frame(at(20, 51), 1),
    )
    prof = profile(cuff=CUFF_ALL, dispenser={"content_sensing": True, "seq": True})
    vec = feed(extractor(registry, prof), items).evidence_for(hold_record())
    assert dispenser_values(vec) == (8_000, 1.0)


# ---- 5: cuff_value_repeated ----------------------------------------------------------------------------

RESOLVED = profile(cuff={**CUFF_ALL, "cuff_resolution": 1.0})


def bp(t: int, value: float, **kw: Any) -> Any:
    return sample(SignalId.BP, t, value=value, **kw)


def test_extractor_cuff_value_repeated(registry) -> None:  # type: ignore[no-untyped-def]
    def value(items: Inputs, prof: Any = RESOLVED) -> Any:
        return (
            feed(extractor(registry, prof), items)
            .evidence_for(hold_record())
            .signal_quality.cuff_value_repeated
        )

    assert value(I(bp(at(20, 10), 120.0), bp(at(20, 40), 120.0))) is True
    assert value(I(bp(at(20, 10), 120.0), bp(at(20, 40), 121.0))) is False
    assert value(I(bp(at(20, 40), 120.0))) is None  # no previous reading
    assert value(I()) is None
    # the profile declares no resolution: the equality of two readings says nothing, no default is assumed
    assert value(I(bp(at(20, 10), 120.0), bp(at(20, 40), 120.0)), CUFF_ONLY) is None
    # the latest two readings in device-time order: 20:20 and 20:40 are equal, 20:10 is not the previous one
    assert (
        value(I(bp(at(20, 10), 118.0), bp(at(20, 20), 120.0), bp(at(20, 40), 120.0)))
        is True
    )
    assert (
        value(I(bp(at(20, 10), 120.0), bp(at(20, 20), 118.0), bp(at(20, 40), 120.0)))
        is False
    )  # equal to the reading before the previous one only
    # a previous reading of the day before counts (the stream is the cuff's, not the day's)
    assert value(I(bp(at(20, 10) - 86_400_000, 120.0), bp(at(20, 40), 120.0))) is True


def test_extractor_cuff_value_repeated_ignores_readings_after_the_decision(
    registry,
) -> None:  # type: ignore[no-untyped-def]
    items = I(bp(at(20, 10), 120.0), bp(at(20, 40), 119.0), bp(at(21, 30), 119.0))
    vec = feed(extractor(registry, RESOLVED), items).evidence_for(hold_record())
    assert (
        vec.signal_quality.cuff_value_repeated is False
    )  # the 21:30 reading is after the hold at 21:00


def test_cuff_resolution_is_a_capability_not_a_default() -> None:
    from ralmon.attribution.extract import DeviceCapabilities

    assert DeviceCapabilities().cuff_resolution is None
    assert DeviceCapabilities().content_sensing is False
    assert DeviceCapabilities(cuff_resolution=1.0).cuff_resolution == 1.0
    for bad in (0.0, -1.0, float("nan"), float("inf")):
        with pytest.raises(ValueError, match="cuff_resolution"):
            DeviceCapabilities(cuff_resolution=bad)


# ---- 6: the hierarchical rule on the old cases --------------------------------------------------------


def test_worked_cases_cover_the_frozen_old_verdicts() -> None:
    assert set(OLD_VERDICTS) == set(case_ids())


@pytest.mark.parametrize("case_id", sorted(OLD_VERDICTS))
def test_hierarchical_rule_unchanged_on_the_old_cases(
    case_id: str, registry, rule
) -> None:  # type: ignore[no-untyped-def]
    case = worked_case(case_id)
    decision = rule.decide(make_record(case["template"]), build_vector(case, registry))
    kappa, row, reason = OLD_VERDICTS[case_id]
    assert decision.kappa.value == kappa, case_id
    assert decision.row == row, case_id
    assert (decision.reason.value if decision.reason else None) == reason, case_id
    # the old field is not read by any case any more
    assert "crypto_temporal.seq_gap_or_replay" not in case["fields"], case_id
    assert "crypto_temporal.seq_gap_or_replay" not in decision.evidence_used


def test_sequence_cases_use_the_split_fields(registry, rule) -> None:  # type: ignore[no-untyped-def]
    """Re-derivations (attribution-rule.md, worked cases W-08-U, W-09-jump, W-15*): repeat or gap, never both fields."""
    repeat = ("W-08-U", "W-15-repeat")
    gap = ("W-09-jump", "W-15", "W-15-alone", "W-15-jump")
    for case_id in repeat:
        fields = worked_case(case_id)["fields"]
        assert fields["crypto_temporal.seq_repeat"] is True
        assert fields["system.seq_gap"] is False
        assert fields["system.ble_link_quality"] == 1.0
    for case_id in gap:
        fields = worked_case(case_id)["fields"]
        assert fields["system.seq_gap"] is True
        assert fields["crypto_temporal.seq_repeat"] is False
    alone = rule.decide(
        make_record("hold"), build_vector(worked_case("W-15-alone"), registry)
    )
    assert alone.kappa.value == "UNDETERMINED" and alone.reason.value == "conflict"  # type: ignore[union-attr]
    assert alone.evidence_used == ("system.ble_link_quality", "system.seq_gap")
    repeated = rule.decide(
        make_record("range"), build_vector(worked_case("W-15-repeat"), registry)
    )
    assert repeated.evidence_used == (
        "system.ble_link_quality",
        "crypto_temporal.seq_repeat",
    )


def test_a_gap_is_not_integrity_evidence_and_a_loss_with_a_complete_ratio_is_a_conflict(
    registry, rule
) -> None:  # type: ignore[no-untyped-def]
    from tests.fixtures.attribution import vector

    clean = {
        "system.node_lifecycle": {"cuff": "active"},
        "system.diagnostics_ok": True,
        "system.liveliness_ok": True,
        "system.qos_deadline_missed": False,
        "system.ble_link_quality": 1.0,
        "signal_quality.ecg_sqi": 0.9,
        "signal_quality.ppg_sqi": 0.9,
        "signal_quality.cuff_error_code": "",
        "cross_device.pulse_vs_ecg_hr_diff": 2.0,
        "system.seq_gap": False,
        "crypto_temporal.seq_repeat": False,
        "crypto_temporal.timestamp_implausible": False,
    }
    record = make_record("range")
    assert rule.decide(record, vector("range", clean, registry)).kappa.value == "C1"
    # the two fields contradict each other (a gap with a complete delivery ratio): an extractor defect, a conflict
    gap_full = rule.decide(
        record, vector("range", {**clean, "system.seq_gap": True}, registry)
    )
    assert gap_full.kappa.value == "UNDETERMINED" and gap_full.row == 6
    # the repeat with a complete ratio is integrity evidence
    rep = rule.decide(
        record, vector("range", {**clean, "crypto_temporal.seq_repeat": True}, registry)
    )
    assert rep.kappa.value == "C3" and rep.row == 2
    # a gap or a repeat with an unavailable ratio is ambiguous (AM-2)
    for field in ("system.seq_gap", "crypto_temporal.seq_repeat"):
        ambiguous = rule.decide(
            record,
            vector(
                "range",
                {**clean, field: True, "system.ble_link_quality": None},
                registry,
            ),
        )
        assert ambiguous.kappa.value == "UNDETERMINED" and ambiguous.row == 8, field
    # C1 needs both fields denied: None on either blocks it (I4)
    for field in ("system.seq_gap", "crypto_temporal.seq_repeat"):
        masked = {k: v for k, v in clean.items() if k != field}
        assert (
            rule.decide(record, vector("range", masked, registry)).kappa.value
            == "UNDETERMINED"
        )


# ---- 7: the new fields are context -----------------------------------------------------------------------

CONTEXT_PATHS = (
    "signal_quality.cuff_value_repeated",
    "dispenser.interval_since_previous_ms",
    "dispenser.content_change",
)
CONTEXT_VALUES: dict[str, tuple[Any, ...]] = {
    "signal_quality.cuff_value_repeated": (None, True, False),
    "dispenser.interval_since_previous_ms": (None, 0, 4_000, 43_200_000),
    "dispenser.content_change": (None, 0.0, 1.0, -1.0),
}


@pytest.mark.parametrize("case_id", sorted(OLD_VERDICTS))
def test_new_fields_are_context_for_the_hierarchical_rule(
    case_id: str, registry, rule
) -> None:  # type: ignore[no-untyped-def]
    case = worked_case(case_id)
    record = make_record(case["template"])
    reference = rule.decide(record, build_vector(case, registry))
    for values in itertools.product(*(CONTEXT_VALUES[p] for p in CONTEXT_PATHS)):
        fields = {**case["fields"], **dict(zip(CONTEXT_PATHS, values, strict=True))}
        decision = rule.decide(
            record, build_vector({**case, "fields": fields}, registry)
        )
        assert decision.kappa is reference.kappa
        assert decision.row == reference.row
        assert decision.reason == reference.reason
        assert decision.evidence_used == reference.evidence_used
        assert decision.missing == reference.missing


# ---- 8: the A4 mask ---------------------------------------------------------------------------------------


def a4_table() -> dict[str, str]:
    text = EVIDENCE_CHANNELS.read_text(encoding="utf-8")
    section = text.split("## Ablation A4 mask", 1)[1].split(
        "\n**Constants for WS08-T04.**", 1
    )[0]
    table: dict[str, str] = {}
    for line in section.splitlines():
        m = re.match(
            r"^\|\s*`([a-z_]+\.[a-z_]+)`\s*\|\s*(None|recompute|unchanged)\s*\|", line
        )
        if m:
            table[m.group(1)] = m.group(2)
    return table


def test_a4_mask_counts() -> None:
    table = a4_table()
    assert tuple(table) == CONTRACT_PATHS  # one row per field, in contract order
    counts = {
        k: sum(1 for v in table.values() if v == k)
        for k in ("None", "recompute", "unchanged")
    }
    assert counts == {"None": 6, "recompute": 4, "unchanged": 14}
    for path in (
        "system.seq_gap",
        "signal_quality.cuff_value_repeated",
        "crypto_temporal.seq_repeat",
        "dispenser.interval_since_previous_ms",
        "dispenser.content_change",
    ):
        assert table[path] == "unchanged", path
    text = EVIDENCE_CHANNELS.read_text(encoding="utf-8")
    assert "unchanged** (fourteen fields" in text
    # the contract sentence agrees with the mask (ADR-049 (n)): six wholly robot-derived fields become None,
    # the four aggregates are recomputed over the device nodes
    rule = CONTRACT.split("## EvidenceVector\n", 1)[1].split("## Attribution", 1)[0]
    assert (
        "all `witness` fields and robot-derived `system` fields become `None`."
        not in rule
    )
    assert "six" in rule and "recomputed" in rule


def test_new_fields_do_not_depend_on_the_robot(registry) -> None:  # type: ignore[no-untyped-def]
    """A4 by extraction: the run with the robot excluded gives the same new fields as the full run."""
    prof = profile(
        cuff={**CUFF_ALL, "cuff_resolution": 1.0},
        dispenser={"content_sensing": True, "seq": True},
        robot={"status_reports": True, "supervised": True},
    )
    items = I(
        *[cuff_frame(t, s) for t, s in FRAMES if s != 2],
        bp(at(20, 10), 120.0),
        bp(at(20, 40), 120.0),
        dispense(at(20, 50), interval_since_previous_ms=8_000, content_change=1.0),
        robot_state(at(20, 0), colocated=True),
        robot_task(at(20, 30), "manipulate", "success"),
    )
    full = evidence_dict(
        feed(extractor(registry, prof, reorder_delay_ms=D120), items).evidence_for(
            hold_record()
        )
    )
    cut = evidence_dict(
        feed(
            extractor(registry, prof, reorder_delay_ms=D120, exclude_robot=True), items
        ).evidence_for(hold_record())
    )
    for path in (
        "system.seq_gap",
        "signal_quality.cuff_value_repeated",
        "crypto_temporal.seq_repeat",
        "dispenser.interval_since_previous_ms",
        "dispenser.content_change",
    ):
        assert cut[path] == full[path], path
    assert (
        full["system.seq_gap"] is True
        and full["signal_quality.cuff_value_repeated"] is True
    )


# ---- 9: declined (ADR-040 (1)) ---------------------------------------------------------------------------


def test_declined_does_not_set_manip_task_failed(registry) -> None:  # type: ignore[no-untyped-def]
    prof = profile(cuff=CUFF_ALL, robot={"status_reports": True})
    declined = I(robot_task(at(20, 30), "manipulate", "declined"))
    vec = feed(extractor(registry, prof), declined).evidence_for(hold_record())
    assert (
        vec.system.manip_task_failed is False
    )  # the robot reported and did not fail (ADR-040 (1))
    mixed = I(
        robot_task(at(20, 30), "manipulate", "declined"),
        robot_task(at(20, 40), "manipulate", "failed"),
    )
    vec = feed(extractor(registry, prof), mixed).evidence_for(hold_record())
    assert vec.system.manip_task_failed is True
    after_success = I(
        robot_task(at(20, 30), "manipulate", "success"),
        robot_task(at(20, 40), "manipulate", "declined"),
    )
    vec = feed(extractor(registry, prof), after_success).evidence_for(hold_record())
    assert vec.system.manip_task_failed is False
    # a declined step is not a failed visit for the witness fields either
    vec = feed(extractor(registry, prof), declined).evidence_for(hold_record())
    assert vec.system.nav_task_failed is None


# ---- 10: the contract and the fault-model signature tables --------------------------------------------


def test_contract_and_fault_model_signature_tables_agree() -> None:
    contract_fields = set(CONTRACT_PATHS)
    text = FAULT_MODEL.read_text(encoding="utf-8")
    cited = set(
        re.findall(
            r"`((?:system|signal_quality|cross_device|witness|crypto_temporal|dispenser)\.[a-z_]+)`",
            text,
        )
    )
    assert cited <= contract_fields, cited - contract_fields
    assert "seq_gap_or_replay" not in text.replace(
        "(was `crypto_temporal.seq_gap_or_replay`", ""
    )
    # the coverage paragraph names each of the 22 non-provenance fields (raised, made None, or not raised)
    coverage = text.split("Coverage of the twenty-two fields.", 1)[1].split("\n## ", 1)[
        0
    ]
    for path in NON_PROVENANCE_PATHS:
        assert f"`{path}`" in coverage, path
    assert "Not raised by any fault of this catalogue:" in coverage


def test_evidence_signatures_use_the_split_fields() -> None:
    from ralmon.benchmark.inject_c2 import EVIDENCE_SIGNATURES
    from ralmon.benchmark.inject_c3 import attack_signature

    assert "system.seq_gap" in EVIDENCE_SIGNATURES["ble_dropout"]
    assert "crypto_temporal.seq_repeat" not in EVIDENCE_SIGNATURES["ble_dropout"]
    for subtype, signature in EVIDENCE_SIGNATURES.items():
        assert "crypto_temporal.seq_gap_or_replay" not in signature, subtype
        assert set(signature) <= set(CONTRACT_PATHS), subtype
    from ralmon.benchmark.inject_c3 import INFORMED, NAIVE

    assert "crypto_temporal.seq_repeat" in attack_signature("replay", NAIVE, False)
    assert "crypto_temporal.seq_repeat" in attack_signature(
        "dispense_forgery", NAIVE, False
    )
    assert "crypto_temporal.seq_repeat" not in attack_signature(
        "replay", INFORMED, False
    )
