"""Specification tests for the attribution likelihood table (WS02-T06, ADR-074).

The tests read ``configs/attribution_likelihood.yaml`` and ``docs/models/attribution-likelihood.md`` and check them against the
documents they are derived from (the relevance map of ``attribution-rule.md``, the vocabularies of the fault model, the threat
model and the benchmark, the contract text of ``02-interfaces.md``). There is no production code here: the posterior is
implemented by WS05-T12. ``reference_posterior`` below is a TEST-LOCAL transcription of the pseudo-code of the specification,
used only to check hand-computed examples; it is not importable from ``ralmon``.

Numbers used here (eps, qc, ...) are values of the SENSITIVITY GRID of the specification, not proposals.
"""

from __future__ import annotations

import collections
import copy
import dataclasses
import itertools
import math
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "configs" / "attribution_likelihood.yaml"
DOC_PATH = ROOT / "docs" / "models" / "attribution-likelihood.md"
RULE_DOC = ROOT / "docs" / "models" / "attribution-rule.md"
FAULT_DOC = ROOT / "docs" / "models" / "fault-model.md"
THREAT_DOC = ROOT / "docs" / "models" / "threat-model.md"
CONTRACT = ROOT / "docs" / "plan" / "02-interfaces.md"

TEMPLATES = ("range", "sched", "hold", "count", "resp", "sys", "int")
CLASSES = ("C1", "C2", "C3")
AWAITING = "awaiting_human_value"
SOURCE_TYPES = {
    "fault_model_row",
    "threat_model_row",
    "device_specification",
    "literature",
    "design_choice",
}
NEEDS = {"gab", "literature", "device_specification", "none"}
#: grid values of the sensitivity design (research report, section 6); NOT proposals
GRID = {
    "eps": 0.01,
    "qc": 0.5,
    "q_stale": 0.5,
    "rep_nat": 0.0197,
    "delta": 0.0,
}
DISPENSER_FIELDS = (
    "dispenser.interval_since_previous_ms",
    "dispenser.content_change",
)
DISPENSER_TEMPLATES = ("hold", "count", "resp", "int")
CUFF_REPEAT = "signal_quality.cuff_value_repeated"
CUFF_TEMPLATES = ("range", "sched", "hold", "resp", "sys")
CONTEXT_FIELDS = {
    "system.battery_low",
    "witness.robot_present",
}


@pytest.fixture(scope="module")
def cfg() -> dict[str, Any]:
    assert CONFIG_PATH.exists(), "configs/attribution_likelihood.yaml is missing"
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def doc() -> str:
    assert DOC_PATH.exists(), "docs/models/attribution-likelihood.md is missing"
    return DOC_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------------------------


def relevance_map() -> dict[str, set[str]]:
    """Fields read per template, parsed from the table of ``attribution-rule.md`` (E, s, b, q, r; not ctx, not -)."""
    text = RULE_DOC.read_text(encoding="utf-8")
    start = text.index("### Relevance map")
    lines = text[start:].splitlines()
    rows = [ln for ln in lines if ln.startswith("| `")]
    out: dict[str, set[str]] = {t: set() for t in TEMPLATES}
    for ln in rows:
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cells) != 8:
            continue
        field = cells[0].strip("`")
        if field.startswith("provenance."):
            continue
        for template, mark in zip(TEMPLATES, cells[1:], strict=True):
            if mark in {"E", "s", "b", "q", "r"}:
                out[template].add(field)
    return out


def components_by_id(cfg: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {c["id"]: c for c in cfg["components"]}


def cell_index(cfg: Mapping[str, Any]) -> dict[tuple[str, str], Mapping[str, Any]]:
    return {(c["component"], c["field"]): c for c in cfg["cells"]}


def p_asserted(
    cfg: Mapping[str, Any], comp_id: str, field: str, par: Mapping[str, float]
) -> float:
    cell = cell_index(cfg).get((comp_id, field))
    token = cell["token"] if cell else cfg["default_cell"]["token"]
    form = cfg["cell_tokens"][token]["form"]
    return float(eval(form, {"__builtins__": {}}, {**par, "max": max}))


def applicable(cfg: Mapping[str, Any], template: str) -> list[Mapping[str, Any]]:
    return [c for c in cfg["components"] if template in c["templates"]]


def _mode_weight(expr: str, par: Mapping[str, float]) -> float:
    return float(eval(expr, {"__builtins__": {}}, dict(par)))


def joint_prob(
    cfg: Mapping[str, Any],
    group: str,
    comp_id: str,
    readings: Mapping[str, str | None],
    par: Mapping[str, float],
) -> float:
    """P(joint reading of the available members of a grouped cell | component); None members are summed over.

    Formula of the specification: P(j) = sum over modes m of weight(m) * [(1-eps) 1(j=m) + eps/(K-1) 1(j!=m)] for a component
    with modes (K = number of joint classes); a component without modes is, in the cross-device group, the product of its marginals
    and, in the ble_seq_gap group, the single mode ``clean``.
    """
    spec = cfg["grouped_cells"][group]
    fields = spec["fields"]
    eps = par["eps"]
    k_classes = spec["K"]
    modes = spec["modes"].get(comp_id)
    total = 0.0
    for combo in itertools.product("AD", repeat=len(fields)):
        if any(
            readings.get(f) is not None and readings[f] != c
            for f, c in zip(fields, combo, strict=True)
        ):
            continue
        if group == "ble_seq_gap":
            joint = spec["joint_class_map"][",".join(combo)]
            mode_weights = (
                {m: _mode_weight(w, par) for m, w in modes.items()}
                if modes
                else {m: _mode_weight(w, par) for m, w in spec["default_mode"].items()}
            )
            total += sum(
                w * ((1 - eps) if joint == m else eps / (k_classes - 1))
                for m, w in mode_weights.items()
            )
        elif modes:
            joint = ",".join(combo)
            mode_weights = {m: _mode_weight(w, par) for m, w in modes.items()}
            total += sum(
                w * ((1 - eps) if joint == m else eps / (k_classes - 1))
                for m, w in mode_weights.items()
            )
        else:
            prod = 1.0
            for f, c in zip(fields, combo, strict=True):
                pa = p_asserted(cfg, comp_id, f, par)
                prod *= pa if c == "A" else 1 - pa
            total += prod
    return total


def reference_posterior(
    cfg: Mapping[str, Any],
    template: str,
    readings: Mapping[str, str | None],
    par: Mapping[str, float],
    prior: Mapping[str, float] | None = None,
    mask: frozenset[str] = frozenset(),
    grouped_off: bool = False,
) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
    """(component, subtype, class) posteriors; pseudo-code of the specification, design ``uniform`` (weight 1 per component)."""
    prior = prior or {c: 1 / 3 for c in CLASSES}
    comps = applicable(cfg, template)
    support = {c["class"] for c in comps}
    z = sum(prior[c] for c in support)
    reads = cfg["templates"][template]["reads"]
    log_post: dict[str, float] = {}
    for comp in comps:
        n_class = sum(1 for c in comps if c["class"] == comp["class"])
        lp = math.log(prior[comp["class"]] / z) + math.log(1 / n_class)
        pair = cfg["grouped_cells"]["ble_seq_gap"]["fields"]
        if (
            cfg["grouped_cells"]["ble_seq_gap"]["reference_mode"] == "grouped"
            and not grouped_off
        ):
            avail = {f: (None if f in mask else readings.get(f)) for f in pair}
            if any(v is not None for v in avail.values()):
                lp += math.log(joint_prob(cfg, "ble_seq_gap", comp["id"], avail, par))
        for field in reads:
            reading = readings.get(field)
            if reading is None or field in mask:
                continue  # unavailable: factor 1
            if (
                field in pair
                and not grouped_off
                and cfg["grouped_cells"]["ble_seq_gap"]["reference_mode"] == "grouped"
            ):
                continue  # the pair is ONE joint cell in the reference
            pa = p_asserted(cfg, comp["id"], field, par)
            lp += math.log(pa if reading == "A" else 1 - pa)
        log_post[comp["id"]] = lp
    m = max(log_post.values())
    ex = {k: math.exp(v - m) for k, v in log_post.items()}
    zz = sum(ex.values())
    comp_post = {k: v / zz for k, v in ex.items()}
    by_id = components_by_id(cfg)
    sub: dict[str, float] = {}
    cls = {c: 0.0 for c in CLASSES}
    for k, v in comp_post.items():
        sub[by_id[k]["subtype"]] = sub.get(by_id[k]["subtype"], 0.0) + v
        cls[by_id[k]["class"]] += v
    return comp_post, sub, cls


def walk_numbers(node: Any, path: tuple[str, ...] = ()):
    if isinstance(node, bool):
        return
    if isinstance(node, (int, float)):
        yield path, node
    elif isinstance(node, Mapping):
        for k, v in node.items():
            yield from walk_numbers(v, (*path, str(k)))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk_numbers(v, (*path, str(i)))


def number_is_allowed(path: tuple[str, ...]) -> bool:
    """A number may stand only inside a declared sensitivity range or design, at an exact place of the file."""
    if (
        len(path) >= 3
        and path[0] in {"parameters", "cells", "grouped_cells"}
        and path[2] == "sensitivity_range"
    ):
        return True
    if len(path) >= 3 and path[0] == "sensitivity_design" and path[2] == "range":
        return True
    if len(path) == 3 and path[0] == "grouped_cells" and path[2] == "K":
        return True  # number of joint classes, an integer, not a probability
    return (
        len(path) >= 2
        and path[0] in {"class_priors", "pi_designs"}
        and path[1] in {"designs", "sensitivity_range"}
    )


def numbers_outside_the_whitelist(
    config: Mapping[str, Any],
) -> list[tuple[tuple[str, ...], float]]:
    return [
        (p, v)
        for p, v in walk_numbers(config)
        if v not in (0, 1) and not number_is_allowed(p)
    ]


def contract_section(name: str) -> str:
    text = CONTRACT.read_text(encoding="utf-8")
    start = text.index(f"\n## {name}\n")
    end = text.find("\n## ", start + 4)
    return text[start : end if end != -1 else None]


# ---------------------------------------------------------------------------------------------
# The seven tests of the task
# ---------------------------------------------------------------------------------------------


def test_every_read_field_has_a_cell_for_every_cause(cfg: dict[str, Any]) -> None:
    rel = relevance_map()
    for template in TEMPLATES:
        reads = cfg["templates"][template]["reads"]
        assert set(rel[template]) <= set(reads), template
        impossible = set(cfg["templates"][template]["impossible_classes"])
        for cause in CLASSES:
            comps = [c for c in applicable(cfg, template) if c["class"] == cause]
            if not comps:
                assert cause in impossible, (template, cause)
                continue
            assert cause not in impossible, (template, cause)
            for field in reads:
                mix_a = mix_d = 0.0
                for comp in comps:
                    pa = p_asserted(cfg, comp["id"], field, GRID)
                    assert 0.0 <= pa <= 1.0, (comp["id"], field)
                    mix_a += pa / len(comps)
                    mix_d += (1.0 - pa) / len(comps)
                assert mix_a + mix_d == pytest.approx(1.0), (template, cause, field)
    # C1 has no catalogued cause at sys and int; C2 and C3 exist everywhere
    assert set(cfg["templates"]["sys"]["impossible_classes"]) == {"C1"}
    assert set(cfg["templates"]["int"]["impossible_classes"]) == {"C1"}
    for template in ("range", "sched", "hold", "count", "resp"):
        assert cfg["templates"][template]["impossible_classes"] == []


def test_structural_cells_use_eps_and_no_literal_probability(
    cfg: dict[str, Any],
) -> None:
    allowed_a = {"eps", "1-eps", AWAITING}
    assert cfg["default_cell"]["A"] == "eps"
    for cell in cfg["cells"]:
        assert cell["A"] in allowed_a, cell
        if cell["A"] == AWAITING:
            assert cell.get("form"), cell
            assert cell["status"] == AWAITING, cell
        else:
            assert cell["status"] == "structural", cell
    forms = {t["form"] for t in cfg["cell_tokens"].values()}
    assert "eps" in forms and "1-eps" in forms
    # no bare probability anywhere outside a sensitivity range or a declared sensitivity design
    assert numbers_outside_the_whitelist(cfg) == []
    # the whitelist is positional: a number under a key that is not a declared range cannot pass as one
    tampered = copy.deepcopy(cfg)
    tampered["templates"]["range"]["sensitivity_range"] = 0.3
    tampered["parameters"][0]["note"] = 0.2
    assert len(numbers_outside_the_whitelist(tampered)) == 2


def test_silent_faults_do_not_zero_diagnostics_ok(cfg: dict[str, Any]) -> None:
    field = "system.diagnostics_ok"
    silent = ("cuff_silent_bias", "stuck_at", "dispenser_bounce")
    profile = cfg["diagnostics_profiles"]["driver_with_diagnostics"]
    assert profile["reads_diagnostics_ok"] is True
    for sid in silent:
        for comp in cfg["components"]:
            if comp["subtype"] == sid:
                # a silent fault raises no diagnostics field: P(ok) = 1 - eps, P(stale) = eps
                assert (comp["id"], field) not in cell_index(cfg), sid
                pa = p_asserted(cfg, comp["id"], field, GRID)
                assert 1.0 - pa > GRID["eps"]
    for template in TEMPLATES:
        c2 = [c for c in applicable(cfg, template) if c["class"] == "C2"]
        p_ok = sum(1 - p_asserted(cfg, c["id"], field, GRID) for c in c2) / len(c2)
        assert p_ok > GRID["eps"], template
    # the loud stale path is conditional (a dropout shorter than the lease leaves ok), never by construction
    stale = cell_index(cfg)[("ble_dropout", field)]
    assert stale["token"] == "S"
    assert stale["A"] == AWAITING


def test_unavailable_contributes_one(cfg: dict[str, Any], doc: str) -> None:
    unavailable = cfg["unavailable"]
    assert unavailable["reading_class"] == "U"
    assert unavailable["factor"] == 1
    assert "has no cell" in unavailable["rule"] or "no cell" in unavailable["rule"]
    assert "factor 1" in doc
    template = "count"
    comp_post_full, _, _ = reference_posterior(
        cfg,
        template,
        {"crypto_temporal.authenticated": "A", "system.diagnostics_ok": None},
        GRID,
    )
    comp_post_drop, _, _ = reference_posterior(
        cfg, template, {"crypto_temporal.authenticated": "A"}, GRID
    )
    assert comp_post_full == pytest.approx(comp_post_drop)
    # masking a field is the same as reading it None
    comp_post_mask, _, _ = reference_posterior(
        cfg,
        template,
        {"crypto_temporal.authenticated": "A", "system.diagnostics_ok": "A"},
        GRID,
        mask=frozenset({"system.diagnostics_ok"}),
    )
    assert comp_post_mask == pytest.approx(comp_post_drop)


def test_every_cell_names_its_source_and_status(cfg: dict[str, Any]) -> None:
    rows: list[Mapping[str, Any]] = [
        *cfg["cells"],
        cfg["default_cell"],
        *cfg["parameters"],
        cfg["class_priors"],
        cfg["pi_designs"],
        *cfg["grouped_cells"].values(),
    ]
    assert len(cfg["cells"]) == 86
    by_status = collections.Counter(c["status"] for c in cfg["cells"])
    assert by_status == {"structural": 19, AWAITING: 67}
    by_token = collections.Counter(c["token"] for c in cfg["cells"])
    assert by_token == {"R": 19, "C": 29, "Cn": 2, "S": 4, "V": 2, "N": 30}
    for row in rows:
        assert row["source_type"] in SOURCE_TYPES, row
        assert row.get("source_ref"), row
        assert row["status"] in {"structural", AWAITING, "reference"}, row
        assert row["verified_by"] is None, row
        assert row["needs"] in NEEDS, row
        if row["source_type"] == "literature":
            assert row.get("bib_key"), row
    # every cell names an existing component and field
    comps = components_by_id(cfg)
    all_fields = set().union(*(set(t["reads"]) for t in cfg["templates"].values()))
    for cell in cfg["cells"]:
        assert cell["component"] in comps, cell
        assert cell["field"] in all_fields | CONTEXT_FIELDS, cell
        assert cell["token"] in cfg["cell_tokens"], cell


def test_contract_versions_bumped() -> None:
    alert = contract_section("Alert")
    assert re.search(r"Version 0\.3\.0", alert), "#alert must read 0.3.0"
    assert "ADR-074" in alert and "amendment 1" in alert
    block = alert[alert.index("class Alert(Detection)") :]
    block = block[: block.index("```")]
    names = [m.group(1) for m in re.finditer(r"^    (\w+):", block, flags=re.MULTILINE)]
    assert names[-2:] == ["p_kappa", "cause_set"]
    assert re.search(r"cause_set: Sequence\[str\] \| None = None", block)
    attribution = contract_section("Attribution")
    assert re.search(r"Version 0\.3\.0", attribution), "#attribution must read 0.3.0"
    assert "ADR-074" in attribution
    assert "posterior_subtypes" in attribution
    # the protocol keeps posterior (0.2.0) and gains posterior_subtypes
    assert "def posterior(" in attribution and "def posterior_subtypes(" in attribution


def test_alert_dataclass_has_cause_set_last_and_optional() -> None:
    from ralmon.attribution import Alert

    fields = dataclasses.fields(Alert)
    assert [f.name for f in fields][-2:] == ["p_kappa", "cause_set"]
    assert fields[-1].default is None


def test_sensitivity_design_is_listed(cfg: dict[str, Any], doc: str) -> None:
    assert "## Sensitivity design" in doc
    wanted = {
        "eps",
        "class_priors",
        "pi_designs",
        "cumulative_level",
        "tau",
        "grouped_variant",
        "qc",
        "q_stale",
        "rep_nat",
        "delta",
        "dispense_bounce_interval_ms",
    }
    listed = {d["name"] for d in cfg["sensitivity_design"]}
    assert wanted <= listed
    for dim in cfg["sensitivity_design"]:
        assert dim["name"] in doc, dim["name"]
        assert dim["range"], dim
    for row in cfg["parameters"]:
        assert row["name"] in doc, row["name"]
        for value in row["sensitivity_range"]:
            assert f"{value:g}" in doc, (row["name"], value)
    for design in cfg["class_priors"]["designs"]:
        assert design in doc
    for design in cfg["pi_designs"]["designs"]:
        assert design in doc
    for variant in cfg["grouped_cells"]:
        assert variant in doc


# ---------------------------------------------------------------------------------------------
# Further checks asked for by the task
# ---------------------------------------------------------------------------------------------


def test_masks_per_template(cfg: dict[str, Any]) -> None:
    rel = relevance_map()
    for template in TEMPLATES:
        expected = set(rel[template])
        if template in DISPENSER_TEMPLATES:
            expected |= set(DISPENSER_FIELDS)
        if template in CUFF_TEMPLATES:
            expected.add(CUFF_REPEAT)
        reads = cfg["templates"][template]["reads"]
        assert set(reads) == expected, template
        assert len(reads) == len(set(reads))
        assert not (set(reads) & CONTEXT_FIELDS), template
    scope = cfg["masks"]["data_scope"]
    assert set(scope["dispenser"]["fields"]) == set(DISPENSER_FIELDS)
    assert set(scope["dispenser"]["read_for"]) == set(DISPENSER_TEMPLATES)
    assert set(scope["cuff_value_repeated"]["read_for"]) == set(CUFF_TEMPLATES)
    # the cuff-repeat cell is None-aware (profile resolution, previous reading, window)
    assert len(scope["cuff_value_repeated"]["unavailable_when"]) >= 3
    # a masked field is not read: the dispenser fields are not in the reads of the other templates
    for template in set(TEMPLATES) - set(DISPENSER_TEMPLATES):
        assert not set(DISPENSER_FIELDS) & set(cfg["templates"][template]["reads"])
    for template in set(TEMPLATES) - set(CUFF_TEMPLATES):
        assert CUFF_REPEAT not in cfg["templates"][template]["reads"]


def test_a4_mask_removes_witness_and_robot_task_cells(cfg: dict[str, Any]) -> None:
    a4 = cfg["masks"]["a4"]
    assert set(a4["cells_removed"]) == {
        "witness.identity_confirmed",
        "witness.intake_observed",
        "system.nav_task_failed",
        "system.manip_task_failed",
    }
    assert set(a4["cells_kept"]) >= {
        "system.node_lifecycle",
        "system.seq_gap",
        "crypto_temporal.authenticated",
    }
    # removing the witness cells equals reading them None
    readings = {"witness.intake_observed": "A", "crypto_temporal.authenticated": "A"}
    masked = reference_posterior(
        cfg, "resp", readings, GRID, mask=frozenset(a4["cells_removed"])
    )
    dropped = reference_posterior(
        cfg, "resp", {"crypto_temporal.authenticated": "A"}, GRID
    )
    assert masked[0] == pytest.approx(dropped[0])


def _bullets(path: Path, heading: str) -> list[str]:
    text = path.read_text(encoding="utf-8")
    start = text.index(heading)
    out: list[str] = []
    for line in text[start:].splitlines()[1:]:
        if line.startswith("- "):
            out.append(line[2:].strip())
        elif out and not line.strip():
            break
    return out


def test_subtype_catalogue_equals_the_union_of_the_vocabularies(
    cfg: dict[str, Any],
) -> None:
    from ralmon.benchmark import inject_c1, inject_c2, inject_c3, labelling

    by_class: dict[str, set[str]] = {c: set() for c in CLASSES}
    for sub in cfg["subtypes"]:
        by_class[sub["class"]].add(sub["name"])
    assert len({s["name"] for s in cfg["subtypes"]}) == len(cfg["subtypes"])

    c2_doc = set(_bullets(FAULT_DOC, "## Subtype vocabulary"))
    c3_doc = set(_bullets(THREAT_DOC, "## Subtype vocabulary"))
    assert len(c2_doc) == 17 and len(c3_doc) == 7
    assert by_class["C2"] == c2_doc == set(inject_c2.C2_SUBTYPES) | c2_doc
    assert by_class["C3"] == c3_doc
    assert (
        set(inject_c3.C3_SUBTYPES) | set(inject_c3.NOT_INJECTED_IN_V1) <= by_class["C3"]
    )
    assert set(inject_c2.C2_SUBTYPES) <= by_class["C2"]
    # C1: the injected subtypes, the two natural labels of the labeller and one spontaneous label per C1-capable template
    expected_c1 = set(inject_c1.C1_SUBTYPES) | {
        labelling.SUBTYPE_DOUBLE_TAKE,
        labelling.SUBTYPE_DOSE_OMISSION,
        *(
            labelling.SPONTANEOUS_PREFIX + t
            for t in ("range", "sched", "hold", "count", "resp")
        ),
    }
    assert by_class["C1"] == expected_c1
    # every component belongs to a subtype of its own class, every subtype has a component
    subtypes = {s["name"]: s for s in cfg["subtypes"]}
    used: set[str] = set()
    for comp in cfg["components"]:
        assert comp["subtype"] in subtypes, comp
        assert comp["class"] == subtypes[comp["subtype"]]["class"], comp
        assert set(comp["templates"]) <= set(TEMPLATES), comp
        used.add(comp["subtype"])
    assert used == set(subtypes)
    # a subtype that the fault model says violates nothing is kept in the catalogue and applicable nowhere
    for name in ("ecg_noise", "out_of_order"):
        assert [
            c for c in cfg["components"] if c["subtype"] == name and c["templates"]
        ] == []
    # the research label
    c1 = [s for s in cfg["subtypes"] if s["class"] == "C1"]
    assert all("in_benchmark_v1" in s for s in c1)


def test_grouped_cells_exist(cfg: dict[str, Any]) -> None:
    grouped = cfg["grouped_cells"]
    assert set(grouped) >= {"ble_seq_gap", "cross_device_signal_quality"}
    assert set(grouped["ble_seq_gap"]["fields"]) == {
        "system.ble_link_quality",
        "system.seq_gap",
    }
    assert set(grouped["cross_device_signal_quality"]["fields"]) == {
        "cross_device.pulse_vs_ecg_hr_diff",
        "signal_quality.ecg_sqi",
        "signal_quality.ppg_sqi",
    }
    assert len(grouped["ble_seq_gap"]["joint_classes"]) == 4
    for g in grouped.values():
        assert g["sensitivity_range"]
        assert g["status"] == AWAITING
    comps = components_by_id(cfg)
    for g in grouped.values():
        for comp_id in g["modes"]:
            assert comp_id in comps, comp_id


def test_both_diagnostics_profiles_have_cells(cfg: dict[str, Any]) -> None:
    profiles = cfg["diagnostics_profiles"]
    assert set(profiles) == {"driver_with_diagnostics", "without_diagnostics"}
    with_diag = profiles["driver_with_diagnostics"]
    without = profiles["without_diagnostics"]
    assert with_diag["reads_diagnostics_ok"] is True
    assert without["reads_diagnostics_ok"] is False
    assert without["factor"] == 1
    stale = [c for c in cfg["cells"] if c["field"] == "system.diagnostics_ok"]
    assert {c["component"] for c in stale} == set(with_diag["stale_components"])
    assert {"ble_dropout"} <= set(with_diag["stale_components"])
    for cell in stale:
        assert cell["token"] == "S" and cell["condition"] == "STALE"
    # the liveness contract and the lease/period rows that the profile needs
    assert "liveness" in with_diag["contract"].lower()
    assert set(with_diag["requires_rows"]) == {
        "driver_stale_lease_ms",
        "driver_period_ms",
    }
    # a C1 event never causes a stale report
    for comp in cfg["components"]:
        if comp["class"] == "C1":
            assert (comp["id"], "system.diagnostics_ok") not in cell_index(cfg)


def test_every_awaiting_row_has_a_sensitivity_range(cfg: dict[str, Any]) -> None:
    rows: list[Mapping[str, Any]] = [
        r
        for r in [
            *cfg["cells"],
            *cfg["parameters"],
            cfg["class_priors"],
            cfg["pi_designs"],
            *cfg["grouped_cells"].values(),
        ]
        if r["status"] == AWAITING
    ]
    assert len(rows) > 20
    for row in rows:
        assert row["sensitivity_range"], row
        assert row["sensitivity_label"] == "sensitivity, not a proposal", row
        assert row["value"] is None, row
    # the parameters of the model that gab must decide are all awaiting rows
    names = {r["name"] for r in cfg["parameters"] if r["status"] == AWAITING}
    assert {
        "eps",
        "qc",
        "q_stale",
        "rep_nat",
        "delta",
        "tau",
        "cumulative_level",
        "dispense_bounce_interval_ms",
    } <= names


def test_class_posterior_is_the_sum_of_subtype_posteriors(cfg: dict[str, Any]) -> None:
    # Hand-computed example at ``count``: only crypto_temporal.authenticated is read and it is asserted.
    eps = GRID["eps"]
    readings = {"crypto_temporal.authenticated": "A"}
    comp_post, sub_post, p_kappa = reference_posterior(cfg, "count", readings, GRID)
    comps = applicable(cfg, "count")
    n = {c: sum(1 for x in comps if x["class"] == c) for c in CLASSES}
    assert n == {
        "C1": 3,
        "C2": 5,
        "C3": 3,
    }  # double_take, dose_omission, spontaneous_count; 5 C2 faults; 3 C3 components
    raised = {"dispense_forgery_naive", "dispense_forgery_informed"}
    weights = {}
    for comp in comps:
        pa = (1 - eps) if comp["id"] in raised else eps
        weights[comp["id"]] = (1 / 3) * (1 / n[comp["class"]]) * pa
    z = sum(weights.values())
    for key, w in weights.items():
        assert comp_post[key] == pytest.approx(w / z)
    expected_c3 = (
        sum(w for k, w in weights.items() if components_by_id(cfg)[k]["class"] == "C3")
        / z
    )
    assert p_kappa["C3"] == pytest.approx(expected_c3)
    assert p_kappa["C3"] == pytest.approx(0.970732, abs=1e-6)
    assert p_kappa["C1"] == pytest.approx(p_kappa["C2"])
    assert sum(p_kappa.values()) == pytest.approx(1.0)
    # the class posterior is the sum of the subtype posteriors; the subtype posterior merges the knowledge levels
    by_sub_class = {s["name"]: s["class"] for s in cfg["subtypes"]}
    for cause in CLASSES:
        assert p_kappa[cause] == pytest.approx(
            sum(p for s, p in sub_post.items() if by_sub_class[s] == cause)
        )
    assert sub_post["dispense_forgery"] == pytest.approx(
        comp_post["dispense_forgery_naive"] + comp_post["dispense_forgery_informed"]
    )
    # the threshold gives the label
    assert max(p_kappa, key=lambda c: p_kappa[c]) == "C3"


def test_documents_state_the_decisions_of_the_task(doc: str) -> None:
    required = [
        "p(s | e, t)",
        "p_kappa",
        "factor 1",
        "ASSUMPTION",
        "naive Bayes",
        "UNDETERMINED",
        "TIGHT",
        "ADR-074 amendment 2",
        "looser",
        "rep_nat",
        "delta",
        "driver_with_diagnostics",
        "without_diagnostics",
        "liveness",
        "A4",
        "posterior_subtypes",
        "cause_set",
        "log likelihood ratio",
        "exactly 1",
        "awaiting_human_value",
        "system.seq_gap",
        "system.ble_link_quality",
        "cross_device",
        "cuff_value_repeated",
        "pre-clinical",
    ]
    for needle in required:
        assert needle in doc, needle
    assert "distribution-free coverage" not in doc
    assert "ensures" not in doc


def test_attribution_rule_points_to_the_table() -> None:
    text = RULE_DOC.read_text(encoding="utf-8")
    assert "attribution-likelihood.md" in text
    assert "ours-hier" in text


def _log_lik(
    cfg: dict[str, Any], comp_id: str, template: str, readings: Mapping[str, str | None]
) -> float:
    total = 0.0
    for field in cfg["templates"][template]["reads"]:
        reading = readings.get(field)
        if reading is None:
            continue
        pa = p_asserted(cfg, comp_id, field, GRID)
        total += math.log(pa if reading == "A" else 1 - pa)
    return total


def test_c1_against_silent_faults_at_range_has_ratio_exactly_one(
    cfg: dict[str, Any],
) -> None:
    # Known failure mode of the research (section 7.2): where nothing is raised the likelihood ratio is exactly 1.
    reads = cfg["templates"]["range"]["reads"]
    for silent in ("cuff_silent_bias",):
        for readings in (
            {},
            {reads[0]: "D", reads[1]: "D"},
            dict.fromkeys(reads, "D"),
            {**dict.fromkeys(reads, "D"), "signal_quality.cuff_value_repeated": "A"},
        ):
            lam = _log_lik(cfg, "spontaneous_range", "range", readings) - _log_lik(
                cfg, silent, "range", readings
            )
            assert lam == pytest.approx(0.0, abs=1e-12)
    # stuck_at differs from C1 only through the repeated-value channel
    all_denied = dict.fromkeys(reads, "D")
    assert _log_lik(cfg, "stuck_at", "range", all_denied) < _log_lik(
        cfg, "spontaneous_range", "range", all_denied
    )
    repeated = {**all_denied, "signal_quality.cuff_value_repeated": "A"}
    assert _log_lik(cfg, "stuck_at", "range", repeated) > _log_lik(
        cfg, "spontaneous_range", "range", repeated
    )
    # identical streams give identical log likelihoods for any two subtypes: D = 0 by construction of the pair quantity
    assert _log_lik(cfg, "stuck_at", "range", repeated) == _log_lik(
        cfg, "stuck_at", "range", dict(repeated)
    )


def test_every_component_with_a_ble_or_gap_cell_has_a_joint_mode(
    cfg: dict[str, Any],
) -> None:
    modes = set(cfg["grouped_cells"]["ble_seq_gap"]["modes"])
    for cell in cfg["cells"]:
        if (
            cell["field"] in cfg["grouped_cells"]["ble_seq_gap"]["fields"]
            and cell["token"] != "R"
        ):
            assert cell["component"] in modes, cell
    # ble_dropout raises the link quality by construction and is also in the modes
    assert "ble_dropout" in modes


def test_the_spec_lists_the_tight_labelling_and_the_two_diagnostics_profiles_as_sensitivity(
    cfg: dict[str, Any],
) -> None:
    names = {d["name"]: d for d in cfg["sensitivity_design"]}
    assert set(names["labelling"]["range"]) == {"tight", "loose"}
    assert set(names["diagnostics_profile"]["range"]) == {
        "driver_with_diagnostics",
        "without_diagnostics",
    }


# ---------------------------------------------------------------------------------------------
# Fix round after the independent review
# ---------------------------------------------------------------------------------------------


def doc_section(doc: str, heading: str) -> str:
    start = doc.index(f"\n## {heading}")
    end = doc.find("\n## ", start + 4)
    return doc[start : end if end != -1 else None]


def test_ble_seq_gap_is_the_reference_grouped_cell(
    cfg: dict[str, Any], doc: str
) -> None:
    # B1: ADR-074 amendment 3 and ADR-075: seq_gap and ble_link_quality are ONE grouped cell in the reference
    grouped = cfg["grouped_cells"]
    assert grouped["ble_seq_gap"]["reference_mode"] == "grouped"
    assert grouped["cross_device_signal_quality"]["reference_mode"] == "independent"
    assert set(grouped["ble_seq_gap"]["fields"]) == {
        "system.ble_link_quality",
        "system.seq_gap",
    }
    design = {d["name"]: d for d in cfg["sensitivity_design"]}
    assert design["grouped_variant"]["reference"] == "reference"
    assert {"reference", "fully_independent", "reference_plus_cross_device"} <= set(
        design["grouped_variant"]["range"]
    )
    assert "REFERENCE" in doc_section(
        doc, "Grouped cells (the reference pair and the sensitivity variants)"
    )
    assert "fully independent" in doc
    model = doc_section(doc, "The model")
    assert "off by default" not in doc
    assert "the independent product is the reference" not in doc
    assert "ONE joint cell" in model
    # the reference posterior multiplies the joint term for the pair, not the two marginals
    readings = {"system.ble_link_quality": "A", "system.seq_gap": "A"}
    grouped_post = reference_posterior(cfg, "hold", readings, GRID)[0]
    independent_post = reference_posterior(
        cfg, "hold", readings, GRID, grouped_off=True
    )[0]
    assert grouped_post["ble_dropout"] != pytest.approx(independent_post["ble_dropout"])
    # the hand-over of WS05-T12 no longer says that the grouped pair is off by default
    t12 = (
        ROOT / "docs/plan/workstreams/WS05-monitor/tasks/T12-likelihood-attributor.md"
    ).read_text(encoding="utf-8")
    handover = t12[t12.index("Hand-over from WS02-T06") :]
    assert "off by default" not in handover
    assert "ble_seq_gap" in handover and "reference" in handover


def _parse_reads_table(doc: str) -> tuple[list[str], dict[str, set[str]]]:
    section = doc_section(doc, "Fields read per template, and the masks")
    lines = [ln for ln in section.splitlines() if ln.startswith("|")]
    header = [c.strip() for c in lines[0].strip().strip("|").split("|")]
    separator = [c.strip() for c in lines[1].strip().strip("|").split("|")]
    assert all(set(c) <= {"-", ":"} and c for c in separator), separator
    reads: dict[str, set[str]] = {t: set() for t in header[1:]}
    for ln in lines[2:]:
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        assert len(cells) == len(header), ln
        for template, mark in zip(header[1:], cells[1:], strict=True):
            if mark == "read":
                reads[template].add(cells[0].strip("`"))
    return header, reads


def test_reads_table_of_the_document_matches_the_yaml(
    cfg: dict[str, Any], doc: str
) -> None:
    header, reads = _parse_reads_table(doc)
    assert header == ["field", *TEMPLATES]
    for template in TEMPLATES:
        assert reads[template] == set(cfg["templates"][template]["reads"]), template


@pytest.mark.parametrize("group", ["ble_seq_gap", "cross_device_signal_quality"])
def test_every_grouped_joint_sums_to_one_for_every_availability_pattern(
    cfg: dict[str, Any], group: str
) -> None:
    spec = cfg["grouped_cells"][group]
    assert spec["K"] == 2 ** len(spec["fields"]) or group == "ble_seq_gap"
    assert "eps/(K-1)" in spec["joint_formula"].replace(" ", "")
    assert spec["none_rule"]
    comps = [c["id"] for c in cfg["components"]]
    for eps, qc in itertools.product((0.001, 0.01, 0.1), (0.25, 0.5, 0.75)):
        par = {**GRID, "eps": eps, "qc": qc}
        for comp in comps:
            full = {f: None for f in spec["fields"]}
            # no member available: the factor is 1
            assert joint_prob(cfg, group, comp, full, par) == pytest.approx(1.0), (
                group,
                comp,
            )
            # for every subset of available members, the probabilities of their joint readings sum to 1
            for avail in itertools.product((False, True), repeat=len(spec["fields"])):
                members = [f for f, a in zip(spec["fields"], avail, strict=True) if a]
                total = 0.0
                for values in itertools.product("AD", repeat=len(members)):
                    readings = {f: None for f in spec["fields"]}
                    readings.update(dict(zip(members, values, strict=True)))
                    total += joint_prob(cfg, group, comp, readings, par)
                assert total == pytest.approx(1.0), (group, comp, members, eps, qc)


def test_grouped_modes_are_distributions_and_cross_device_has_a_none_rule(
    cfg: dict[str, Any],
) -> None:
    for group, spec in cfg["grouped_cells"].items():
        for comp, modes in spec["modes"].items():
            assert sum(_mode_weight(w, GRID) for w in modes.values()) == pytest.approx(
                1.0
            ), (group, comp)
    xdev = cfg["grouped_cells"]["cross_device_signal_quality"]
    assert "summed over" in xdev["none_rule"] or "marginalis" in xdev["none_rule"]
    # None member of the cross-device group: the joint of the others is the marginal (summing over the unavailable one)
    par = {**GRID}
    for comp in ("ecg_noise", "replay_informed", "ble_dropout"):
        fields = xdev["fields"]
        a = joint_prob(
            cfg,
            "cross_device_signal_quality",
            comp,
            {fields[0]: "A", fields[1]: "A", fields[2]: None},
            par,
        )
        b = sum(
            joint_prob(
                cfg,
                "cross_device_signal_quality",
                comp,
                {fields[0]: "A", fields[1]: "A", fields[2]: v},
                par,
            )
            for v in "AD"
        )
        assert a == pytest.approx(b)


def test_timestamp_cells_beyond_the_bound_are_conditional(
    cfg: dict[str, Any], doc: str
) -> None:
    # I3: 'beyond the bound only' (fault-model.md, threat-model.md, TX-8 (a)) is not a structural 1 - eps
    field = "crypto_temporal.timestamp_implausible"
    for comp in ("clock_skew", "out_of_order", "timestamp_manipulation"):
        cell = cell_index(cfg)[(comp, field)]
        assert cell["token"] != "R", comp
        assert cell["status"] == AWAITING and cell["sensitivity_range"], comp
        assert cell["condition"] == "BOUND", comp
    section = doc_section(
        doc, "Known failure modes (from the research, stated plainly)"
    )
    assert "beyond the bound" in section
    for name in ("clock_skew", "timestamp_manipulation", "out_of_order"):
        assert name in section
    assert "outside benchmark v1" in section
    subtypes = {s["name"]: s for s in cfg["subtypes"]}
    for name in ("clock_skew", "timestamp_manipulation", "out_of_order"):
        assert subtypes[name]["in_benchmark_v1"] is False


def test_body_states_adr_075_the_interval_chain_and_the_sessions(doc: str) -> None:
    # I4 (a)
    assert "ADR-075" in doc and "DA-CONFERMARE" in doc
    assert "is not a C2 predicate" in doc
    # I4 (b)
    assert "ADR-074 amendment 4" in doc
    assert "coherent on the interval chain" in doc
    assert "7 of 16" in doc
    assert "naive forger is not coherent" in doc
    # I4 (c)
    assert "sessions" in doc
    assert "in practice a `ble_dropout` signal" in doc


def test_pair_quantity_names_the_within_subtype_weights(doc: str) -> None:
    section = doc_section(doc, "The pair quantity")
    assert "within-subtype" in section
    assert "pi design in force" in section
    assert "uniform over components" in section
    assert "reference design" in section and "awaiting" in section


def test_dead_awaiting_cells_are_exactly_the_documented_ones(
    cfg: dict[str, Any], doc: str
) -> None:
    reads_of: dict[str, set[str]] = {}
    for comp in cfg["components"]:
        reads_of[comp["id"]] = (
            set().union(*(set(cfg["templates"][t]["reads"]) for t in comp["templates"]))
            if comp["templates"]
            else set()
        )
    dead = {
        (c["component"], c["field"])
        for c in cfg["cells"]
        if c["field"] not in reads_of[c["component"]]
    }
    assert dead == {
        ("presence_spoof_naive", "witness.identity_confirmed"),
        ("out_of_order", "crypto_temporal.timestamp_implausible"),
        ("ecg_noise", "cross_device.pulse_vs_ecg_hr_diff"),
        ("ecg_noise", "signal_quality.ecg_sqi"),
    }
    section = doc_section(
        doc, "Known failure modes (from the research, stated plainly)"
    )
    assert "presence_spoof" in section and "dead" in section
    assert "message_drop" in section
    assert "replay" in section and "seq_gap" in section and "H-SUPP" in section


def test_status_table_counts_are_the_recounted_ones(
    cfg: dict[str, Any], doc: str
) -> None:
    section = doc_section(doc, "Status of the numbers, in one table")
    counts = collections.Counter(c["token"] for c in cfg["cells"])
    conditional = counts["C"] + counts["Cn"] + counts["S"] + counts["V"]
    assert f"{conditional} conditional cells" in section
    assert f"{counts['N']} natural-repeat cells" in section
    assert f"{counts['R']} structural" in section


def test_catalogue_wording_counts_double_take_once(doc: str) -> None:
    section = doc_section(doc, "The subtype catalogue")
    assert "double_take` is both" in section
