"""The enumeration check of ``docs/models/attribution-rule.md`` (WS05-T13 test 11), recomputed by a test.

A vectorised implementation of the decision table, written from the predicates of the document and not from
``HierarchicalRule``, enumerates every combination of the reading classes of the fields each template reads. It is
checked three ways: against the table printed in the document (the numbers are parsed from it), against
``HierarchicalRule.decide`` on seeded random combinations (the whole space for ``count``), and against the 0.1.0 table
on every combination of the old space through the mapping of the single sequence field to the pair of 0.2.0.
"""

from __future__ import annotations

import itertools
import random
import re
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from tests.fixtures.attribution import load_fixture_registry, make_record, vector

ROOT = Path(__file__).resolve().parents[2]
DOC = (ROOT / "docs" / "models" / "attribution-rule.md").read_text(encoding="utf-8")

CP = ["LIFE", "DIAG", "LIVE", "QOS", "BLE"]
READS: dict[str, list[str]] = {
    "range": [*CP, "CUFF", "DIFF", "ECG", "PPG", "AUTH", "GAP", "SEQ", "TIME"],
    "sched": [*CP, "NAV", "MANIP", "CUFF", "AUTH", "GAP", "SEQ", "TIME"],
    "hold": [*CP, "NAV", "MANIP", "CUFF", "DIFF", "ECG", "PPG", "AUTH", "GAP", "SEQ", "TIME"],
    "count": [*CP, "AUTH", "GAP", "SEQ", "TIME"],
    "resp": [
        *CP, "NAV", "MANIP", "CUFF", "DIFF", "ECG", "PPG", "IDENT", "INTAKE",
        "AUTH", "GAP", "SEQ", "TIME",
    ],
    "sys": [*CP, "CUFF", "DIFF", "ECG", "PPG", "AUTH", "GAP", "SEQ", "TIME"],
    "int": [*CP, "NAV", "MANIP", "AUTH", "GAP", "SEQ", "TIME"],
}  # fmt: skip
QUAL = {"range", "hold", "resp", "sys"}
TASKS = {"sched", "hold", "resp", "int"}
CUFF_CODE = {"range", "sched", "hold", "resp", "sys"}
EX_EXTRA = {
    "range": ["CUFF", "DIFF"],
    "sched": ["NAV", "MANIP", "CUFF"],
    "hold": ["NAV", "MANIP", "CUFF", "DIFF"],
    "resp": ["NAV", "MANIP", "CUFF", "DIFF"],
}
# class codes. Ordinary fields: A asserted 0, D denied 1, U unavailable 2. LIFE: A 0, D 1, U 2, K 3 (deliberate).
# BLE: A 0 (degraded), F 1 (complete), G 2 (a value missing, not degraded), U 3.


def n_classes(field: str) -> int:
    return 4 if field in ("LIFE", "BLE") else 3


def reads(template: str, old: bool) -> list[str]:
    return [f for f in READS[template] if not (old and f == "GAP")]


def table(template: str, x: dict[str, Any], old: bool) -> Any:
    """The row (1 to 8) of every combination in ``x`` (a code array per field read)."""
    n = len(next(iter(x.values())))
    zeros = np.zeros(n, bool)
    ones = np.ones(n, bool)

    def asserted(f: str) -> Any:
        return x[f] == 0 if f in x else zeros

    def denied(f: str) -> Any:
        if f not in x:
            return zeros
        return (x[f] == 1) | (x[f] == 2) if f == "BLE" else x[f] == 1

    def unavailable(f: str) -> Any:
        if f not in x:
            return ones
        return x[f] == 3 if f == "BLE" else x[f] == 2

    ble_f, ble_g, ble_a, ble_u = (
        x["BLE"] == 1,
        x["BLE"] == 2,
        x["BLE"] == 0,
        x["BLE"] == 3,
    )
    gap = zeros if old else asserted("GAP")
    ie1 = asserted("AUTH")
    ie2 = asserted("SEQ") & ble_f
    qualified = template in QUAL
    ie3 = asserted("DIFF") & denied("ECG") & denied("PPG") if qualified else zeros
    se = (
        asserted("LIFE") | asserted("DIAG") | asserted("LIVE") | asserted("QOS") | ble_a
    )
    if template in TASKS:
        se = se | asserted("NAV") | asserted("MANIP")
    if template in CUFF_CODE:
        se = se | asserted("CUFF")
    if qualified:
        se = se | (asserted("DIFF") & (asserted("ECG") | asserted("PPG")))
    ex = zeros
    if template in EX_EXTRA:
        req = (
            (x["LIFE"] == 1) & denied("DIAG") & denied("LIVE") & denied("QOS") & ble_f
            & denied("SEQ") & denied("TIME")
        )  # fmt: skip
        if not old:
            req = req & denied("GAP")
        for f in EX_EXTRA[template]:
            req = req & denied(f)
        if template == "resp":
            backing = denied("AUTH") | (
                unavailable("AUTH") & denied("IDENT") & denied("INTAKE")
            )
        else:
            backing = ones
        ex = req & backing
    rs = (x["LIFE"] == 3) | ble_g | asserted("TIME")
    if not old:
        rs = rs | (ble_f & gap)
    if template == "resp":
        backed = denied("IDENT") & denied("INTAKE")
        rs = rs | (
            unavailable("AUTH") & ~backed & (asserted("IDENT") | asserted("INTAKE"))
        )
    am1 = (
        asserted("DIFF")
        & ~asserted("ECG")
        & ~asserted("PPG")
        & ~(denied("ECG") & denied("PPG"))
        if qualified
        else zeros
    )
    am2 = (asserted("SEQ") | gap) & ble_u
    row = np.full(n, 8, np.int8)
    if template in ("sys", "int"):
        row[~(am1 | am2)] = 7
    row[rs] = 6
    row[ex] = 5
    row[se] = 4
    row[ie3] = 3
    row[ie2] = 2
    row[ie1] = 1
    return row


def enumerate_template(template: str, old: bool = False) -> tuple[int, int, list[int]]:
    """(fields read, combinations, combinations per row 1 to 8)."""
    fields = reads(template, old)
    sizes = [n_classes(f) for f in fields]
    tail, k = 1, 0
    for s in reversed(sizes):
        if tail * s > 4_000_000:
            break
        tail *= s
        k += 1
    head, rest = fields[: len(fields) - k], fields[len(fields) - k :]
    remainder = np.arange(tail)
    tail_codes: dict[str, Any] = {}
    for f in reversed(rest):
        tail_codes[f] = (remainder % n_classes(f)).astype(np.int8)
        remainder = remainder // n_classes(f)
    counts = np.zeros(9, np.int64)
    for combo in itertools.product(*[range(n_classes(f)) for f in head]):
        x = {f: np.full(tail, c, np.int8) for f, c in zip(head, combo, strict=True)}
        x.update(tail_codes)
        counts += np.bincount(table(template, x, old), minlength=9)
    total = int(np.prod(sizes))
    assert int(counts.sum()) == total
    return len(fields), total, [int(c) for c in counts[1:]]


def doc_table() -> dict[str, list[int]]:
    """The rows of the enumeration table of the document: fields read, combinations, rows 1 to 8, outcomes."""
    section = DOC.split("**Enumeration check.**", 1)[1].split(
        "**Combinations the extractor", 1
    )[0]
    out: dict[str, list[int]] = {}
    for line in section.splitlines():
        m = re.match(r"^\| `([a-z]+)` \|(.*)\|\s*$", line)
        if m is None:
            continue
        cells = [c.strip() for c in m.group(2).split("|")]
        out[m.group(1)] = [0 if c == "n/a" else int(c.replace(",", "")) for c in cells]
    return out


TEMPLATES = list(READS)


@pytest.mark.parametrize("template", TEMPLATES)
def test_enumeration_table_of_the_document_is_recomputed(template: str) -> None:
    n_fields, total, rows = enumerate_template(template)
    printed = doc_table()[template]
    assert printed[0] == n_fields
    assert printed[1] == total
    assert printed[2:10] == rows
    c3, c2, c1 = sum(rows[:3]), rows[3], rows[4]
    assert printed[10:13] == [c3, c2, c1]
    assert printed[13] == sum(rows[5:])


def test_new_combination_count_and_c1_reachability() -> None:
    totals = {t: enumerate_template(t)[1] for t in TEMPLATES}
    assert sum(totals.values()) == 262_055_088
    assert sum(enumerate_template(t, old=True)[1] for t in TEMPLATES) == 87_351_696
    assert "262,055,088 combinations in all" in DOC
    # C1 exists only for range, sched, hold and resp, in the same number of combinations as in 0.1.0
    c1 = {t: enumerate_template(t)[2][4] for t in TEMPLATES}
    assert c1 == {
        "range": 18,
        "sched": 2,
        "hold": 18,
        "count": 0,
        "resp": 90,
        "sys": 0,
        "int": 0,
    }
    assert c1 == {t: enumerate_template(t, old=True)[2][4] for t in TEMPLATES}


def test_the_old_table_is_reproduced_by_the_single_field_mode() -> None:
    """The implementation reproduces the numbers of the 0.1.0 version of the section (kept in the git history)."""
    expected = {
        "range": [314_928, 52_488, 21_384, 507_600, 18, 34_944, 0, 13_422],
        "resp": [
            25_509_168,
            4_251_528,
            1_732_104,
            43_292_880,
            90,
            1_392_384,
            0,
            349_350,
        ],
        "sys": [314_928, 52_488, 21_384, 507_600, 0, 34_944, 9_216, 4_224],
        "int": [34_992, 5_832, 0, 59_544, 0, 3_328, 1_024, 256],
    }
    for template, rows in expected.items():
        assert enumerate_template(template, old=True)[2] == rows


@pytest.mark.parametrize("template", TEMPLATES)
def test_the_new_table_equals_the_old_table_through_the_mapping(template: str) -> None:
    """Old ``True`` with a complete ratio is a repeat, with a ratio below one a gap, with an unavailable ratio a repeat
    whose gap is unavailable; old ``False`` and ``None`` map to both fields False and both ``None``."""
    fields = reads(template, old=True)
    sizes = [n_classes(f) for f in fields]
    tail, k = 1, 0
    for s in reversed(sizes):
        if tail * s > 2_000_000:
            break
        tail *= s
        k += 1
    head, rest = fields[: len(fields) - k], fields[len(fields) - k :]
    remainder = np.arange(tail)
    tail_codes: dict[str, Any] = {}
    for f in reversed(rest):
        tail_codes[f] = (remainder % n_classes(f)).astype(np.int8)
        remainder = remainder // n_classes(f)
    differences = 0
    for combo in itertools.product(*[range(n_classes(f)) for f in head]):
        x = {f: np.full(tail, c, np.int8) for f, c in zip(head, combo, strict=True)}
        x.update(tail_codes)
        seq, ble = x["SEQ"], x["BLE"]
        new = dict(x)
        new["SEQ"] = np.where(
            seq == 0, np.where(ble == 1, 0, np.where(ble == 3, 0, 1)), seq
        ).astype(np.int8)
        new["GAP"] = np.where(
            seq == 0, np.where(ble == 1, 1, np.where(ble == 3, 2, 0)), seq
        ).astype(np.int8)
        differences += int(
            (table(template, x, old=True) != table(template, new, old=False)).sum()
        )
    assert differences == 0


# ---- the implementation of the rule against the vectorised table ------------------------------------------

PATH = {
    "LIFE": "system.node_lifecycle", "DIAG": "system.diagnostics_ok", "LIVE": "system.liveliness_ok",
    "QOS": "system.qos_deadline_missed", "BLE": "system.ble_link_quality", "NAV": "system.nav_task_failed",
    "MANIP": "system.manip_task_failed", "GAP": "system.seq_gap", "CUFF": "signal_quality.cuff_error_code",
    "ECG": "signal_quality.ecg_sqi", "PPG": "signal_quality.ppg_sqi",
    "DIFF": "cross_device.pulse_vs_ecg_hr_diff", "IDENT": "witness.identity_confirmed",
    "INTAKE": "witness.intake_observed", "AUTH": "crypto_temporal.authenticated",
    "SEQ": "crypto_temporal.seq_repeat", "TIME": "crypto_temporal.timestamp_implausible",
}  # fmt: skip
ADVERSE_FALSE = {"DIAG", "LIVE", "IDENT", "INTAKE", "AUTH"}


def reading(f: str, code: int, registry: Any) -> Any:
    def threshold(name: str) -> float:
        return float(registry.get(name).value)

    if f == "LIFE":
        return {
            0: {"cuff": "inactive"},
            1: {"cuff": "active"},
            2: None,
            3: {"cuff": "inactive+commanded"},
        }[code]
    if f == "BLE":
        floor = threshold("ble_link_quality_floor")
        return {0: floor / 2, 1: 1.0, 2: (floor + 1) / 2, 3: None}[code]
    if code == 2:
        return None
    if f in ("ECG", "PPG"):
        floor = threshold("ecg_sqi_floor" if f == "ECG" else "ppg_sqi_floor")
        return floor / 2 if code == 0 else floor
    if f == "DIFF":
        tolerance = threshold("hr_coherence_tolerance")
        return tolerance * 2 if code == 0 else tolerance
    if f == "CUFF":
        return "E1" if code == 0 else ""
    if f in ADVERSE_FALSE:
        return code != 0
    return code == 0


@pytest.mark.parametrize("template", TEMPLATES)
def test_hierarchical_rule_agrees_with_the_vectorised_table(template: str) -> None:
    from ralmon.attribution import HierarchicalRule

    registry = load_fixture_registry()
    rule = HierarchicalRule(registry)
    fields = reads(template, old=False)
    sizes = [n_classes(f) for f in fields]
    total = int(np.prod(sizes))
    rnd = random.Random(20261011)
    if total <= 40_000:
        space = itertools.product(*[range(s) for s in sizes])
    else:
        space = (tuple(rnd.randrange(s) for s in sizes) for _ in range(3_000))
    for combo in space:
        codes = dict(zip(fields, combo, strict=True))
        x = {f: np.array([c], np.int8) for f, c in codes.items()}
        want = int(table(template, x, old=False)[0])
        values = {PATH[f]: reading(f, c, registry) for f, c in codes.items()}
        got = rule.decide(
            make_record(template),
            vector(
                template, {k: v for k, v in values.items() if v is not None}, registry
            ),
        )
        assert got.row == want, (template, codes)
