"""Copy the worked cases W-01 to W-15 of docs/models/attribution-rule.md into worked_cases.json.

Run from the repository root: ``python tests/fixtures/attribution/build_worked_cases.py``. The output is
committed; the tests read the JSON and never the markdown. The script is the audit trail of the copy:
every case keeps the id of the document, and a variant is the base case with the listed fields replaced
(``None`` removes the field), as the document defines it (section Worked cases, convention 3).

Float and string readings are kept symbolic (``{"rel": "at_or_above", "param": "ecg_sqi_floor"}``): the
document gives them by their relation to a registry threshold and no clinical value, so the test builds the
number from the (FIXTURE-ONLY) threshold of its registry.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "docs" / "models" / "attribution-rule.md"
TARGET = Path(__file__).with_name("worked_cases.json")

GROUPS = (
    "provenance",
    "system",
    "signal_quality",
    "cross_device",
    "witness",
    "crypto_temporal",
)
_GROUP_ALT = "|".join(GROUPS)
PATH = re.compile(rf"`((?:{_GROUP_ALT})\.[a-z_0-9]+)`")
START = re.compile(rf"\(`(?:{_GROUP_ALT})\.[a-z_0-9]+`")


def cells(line: str) -> list[str]:
    parts = line.strip().strip("|").split("|")
    return [p.strip() for p in parts]


def parse_value(text: str) -> Any:
    """A value cell of the document as JSON-friendly data (symbolic for threshold relations)."""
    text = text.strip()
    if text in ("None", "`None`"):
        return None
    if text in ("`True`", "True"):
        return True
    if text in ("`False`", "False"):
        return False
    m = re.match(r"^`(\{.*\})`$", text)
    if m:
        return json.loads(m.group(1))
    m = re.match(r'^`""(?: \(empty string\))?`$', text) or re.match(
        r'^`"" \(empty string\)`$', text
    )
    if m or text.startswith('`"" ('):
        return ""
    m = re.match(r'^`?"([A-Z0-9]+)"(?: \(device label\))?`?$', text)
    if m:
        return m.group(1)
    m = re.match(r"^`(-?\d+(?:\.\d+)?)`$", text)
    if m:
        return float(m.group(1))
    if text.startswith("below 1.0, at or above"):
        param = re.search(r"`([a-z_]+)`", text)
        assert param is not None
        return {"rel": "between_floor_and_one", "param": param.group(1)}
    m = re.match(r"^(at or above|within|below|above) `([a-z_]+)`$", text)
    if m:
        rel = {
            "at or above": "at_or_above",
            "within": "within",
            "below": "below",
            "above": "above",
        }[m.group(1)]
        return {"rel": rel, "param": m.group(2)}
    raise ValueError(f"cannot parse value {text!r}")


def balanced(text: str, start: int) -> str:
    """The content of the parenthesis group that opens at ``start`` (text[start] == '(')."""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return text[start + 1 : i]
    raise ValueError("unbalanced parenthesis")


def parse_assignments(change: str) -> dict[str, Any]:
    starts = [m.start() for m in START.finditer(change)]
    if not starts:
        return {}
    content = balanced(change, starts[-1])
    out: dict[str, Any] = {}
    for part in content.split(";"):
        part = part.strip()
        m = PATH.match(part)
        assert m is not None, part
        out[m.group(1)] = parse_value(part[m.end() :].strip())
    return out


def decisive(text: str) -> list[str]:
    if text.startswith("none"):
        return []
    return PATH.findall(text)


def reason_of(text: str) -> str | None:
    text = text.strip()
    if text.startswith("not applicable"):
        return None
    return text.replace("-", "_").lower()


def kappa_of(text: str) -> str:
    return text.strip()


def parse_section(lines: list[str]) -> dict[str, Any]:
    """Base case of a section: item table + field table."""
    item: dict[str, str] = {}
    fields: dict[str, Any] = {}
    mode = None
    for line in lines:
        if line.startswith("| item |"):
            mode = "item"
            continue
        if line.startswith("| field |"):
            mode = "field"
            continue
        if line.startswith("|---"):
            continue
        if not line.startswith("|"):
            mode = None if mode else mode
            continue
        c = cells(line)
        if mode == "item":
            item[c[0].strip("`")] = c[1]
        elif mode == "field":
            fields[PATH.match(c[0]).group(1)] = parse_value(c[1])  # type: ignore[union-attr]
    return {"item": item, "fields": fields}


def case_from(
    case_id: str, parsed: dict[str, Any], variant_of: str | None = None
) -> dict[str, Any]:
    item = parsed["item"]
    template = item["provenance.violated_template"].strip("`")
    kind_text = item["provenance.template_kind"]
    kind = re.match(r"(phi_[a-z]+)", kind_text).group(1)  # type: ignore[union-attr]
    return {
        "id": case_id,
        "variant_of": variant_of,
        "template": template,
        "kind": kind,
        "kappa": kappa_of(item["expected κ"]),
        "decisive": decisive(item["decisive fields, precedence order"]),
        "reason": reason_of(item["reason (UNDETERMINED only)"]),
        "row": int(item["table row"]),
        "fields": parsed["fields"],
    }


def w11_rule_cases() -> list[dict[str, Any]]:
    """The rule part of W-11 (the cascade case of the document, section Worked cases).

    The table of W-11 gives, per instance, the fields that are not None and the kappa of the rule on its own
    evidence; the cascade part (links, issue order) is encoded in tests/attribution/test_cascades.py.
    """
    three = {"cuff": "active", "dispenser": "active", "robot": "active"}
    lapse = {"system.liveliness_ok": False}

    def case(
        cid: str,
        template: str,
        fields: dict[str, Any],
        kappa: str,
        decisive: list[str],
        reason: str | None,
        row: int,
    ) -> dict[str, Any]:
        kind = {"sys": "phi_sys", "int": "phi_int"}.get(template, "phi_cp")
        return {
            "id": cid,
            "variant_of": "W-11" if cid != "W-11" else None,
            "template": template,
            "kind": kind,
            "kappa": kappa,
            "decisive": decisive,
            "reason": reason,
            "row": row,
            "fields": fields,
        }

    return [
        case(
            "W-11",
            "sched",
            {"system.node_lifecycle": {"cuff": "active", "robot": "active"}, **lapse},
            "C2",
            ["system.liveliness_ok"],
            None,
            4,
        ),
        case(
            "W-11-resp",
            "resp",
            {"system.node_lifecycle": three, **lapse},
            "C2",
            ["system.liveliness_ok"],
            None,
            4,
        ),
        case(
            "W-11-hold",
            "hold",
            {"system.node_lifecycle": three, **lapse},
            "C2",
            ["system.liveliness_ok"],
            None,
            4,
        ),
        case(
            "W-11-late-root",
            "hold",
            {"system.node_lifecycle": three, "system.liveliness_ok": True},
            "UNDETERMINED",
            [],
            "insufficient",
            8,
        ),
        case(
            "W-11-deliberate",
            "sched",
            {
                "system.node_lifecycle": {
                    "cuff": "inactive+commanded",
                    "robot": "active",
                }
            },
            "UNDETERMINED",
            ["system.node_lifecycle"],
            "conflict",
            6,
        ),
        case(
            "W-11-c3",
            "resp",
            {
                "system.node_lifecycle": three,
                **lapse,
                "crypto_temporal.authenticated": False,
            },
            "C3",
            ["crypto_temporal.authenticated"],
            None,
            1,
        ),
    ]


def main() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    block = text.split("## Worked cases", 1)[1].split("**Hand derivations**", 1)[0]
    sections = re.split(r"\n### (W-\d\d)\n", "\n" + block)
    cases: list[dict[str, Any]] = []
    for i in range(1, len(sections), 2):
        wid = sections[i]
        body = sections[i + 1].splitlines()
        if wid == "W-11":
            continue
        if wid == "W-12":
            for line in body:
                if line.startswith("| `") and "TemplateKind" in line:
                    c = cells(line)
                    tid = c[0].strip("`")
                    kind = re.match(r"(phi_[a-z]+)", c[1]).group(1)  # type: ignore[union-attr]
                    reason = reason_of(c[4])
                    cases.append(
                        {
                            "id": f"W-12-{tid}",
                            "variant_of": None,
                            "template": tid,
                            "kind": kind,
                            "kappa": "UNDETERMINED",
                            "decisive": [],
                            "reason": reason,
                            "row": int(c[5]),
                            "fields": {},
                        }
                    )
            continue
        # split the section on "Variant W-xx-yyy:" paragraphs (own item and field tables)
        chunks: list[tuple[str, list[str]]] = [(wid, [])]
        for line in body:
            m = re.match(r"^Variant (W-\d\d-[\w-]+):", line)
            if m:
                chunks.append((m.group(1), []))
                continue
            chunks[-1][1].append(line)
        for cid, lines in chunks:
            parsed = parse_section(lines)
            case = case_from(cid, parsed, None if cid == wid else wid)
            cases.append(case)
            # variant table rows of this chunk
            in_variants = False
            for line in lines:
                if line.startswith("| variant |"):
                    in_variants = True
                    continue
                if line.startswith("|---"):
                    continue
                if in_variants and line.startswith("|"):
                    c = cells(line)
                    vid = c[0]
                    change = c[1]
                    fields = dict(case["fields"])
                    for path, value in parse_assignments(change).items():
                        fields[path] = value
                    kappa = kappa_of(c[2])
                    cases.append(
                        {
                            "id": vid,
                            "variant_of": cid,
                            "template": case["template"],
                            "kind": case["kind"],
                            "kappa": kappa,
                            "decisive": decisive(c[3]),
                            "reason": reason_of(c[4]),
                            "row": int(c[5]),
                            "fields": fields,
                        }
                    )
                elif in_variants:
                    in_variants = False
    cases.extend(w11_rule_cases())
    # drop None-valued fields (None removes the field)
    for case in cases:
        case["fields"] = {k: v for k, v in case["fields"].items() if v is not None}
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids)), "duplicate case id"
    document = {
        "source": "docs/models/attribution-rule.md, section Worked cases (W-11, the cascade case, is in test_cascades.py)",
        "cases": cases,
    }
    TARGET.write_text(
        json.dumps(document, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"{len(cases)} cases written to {TARGET}")


if __name__ == "__main__":
    main()
