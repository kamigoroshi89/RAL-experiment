"""Specification tests for the attribution likelihood table (WS02-T06, ADR-074).

The tests read ``configs/attribution_likelihood.yaml`` and ``docs/models/attribution-likelihood.md`` and check them against the
documents they are derived from (the relevance map of ``attribution-rule.md``, the vocabularies of the fault model, the threat
model and the benchmark, the contract text of ``02-interfaces.md``). There is no production code here: the posterior is
implemented by WS05-T12. ``reference_posterior`` below is a TEST-LOCAL transcription of the pseudo-code of the specification,
used only to check hand-computed examples; it is not importable from ``ralmon``.

Numbers used here (eps, qc, ...) are values of the SENSITIVITY GRID of the specification, not proposals.
"""

from __future__ import annotations

import dataclasses
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
    return float(eval(form, {"__builtins__": {}}, {**par, "max": max}))  # noqa: S307 - trusted config under test


def applicable(cfg: Mapping[str, Any], template: str) -> list[Mapping[str, Any]]:
    return [c for c in cfg["components"] if template in c["templates"]]


def reference_posterior(
    cfg: Mapping[str, Any],
    template: str,
    readings: Mapping[str, str | None],
    par: Mapping[str, float],
    prior: Mapping[str, float] | None = None,
    mask: frozenset[str] = frozenset(),
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
        for field in reads:
            reading = readings.get(field)
            if reading is None or field in mask:
                continue  # unavailable: factor 1
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
    for path, value in walk_numbers(cfg):
        if value in (0, 1):
            continue
        assert any(p in ("sensitivity_range", "designs") for p in path), (path, value)


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
    assert len(cfg["cells"]) > 100
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
    names = [m.group(1) for m in re.finditer(r"^    (\w+):", block, flags=re.M)]
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
