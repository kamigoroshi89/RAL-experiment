"""WS08-T09: the runner writes the keys of the probabilistic-attribution metrics (ADR-074), additive to ``metrics.json``.

ILLUSTRATIVE, UNVERIFIED, FIXTURE-ONLY. The runs use the hand-written mini benchmark (``tests/fixtures/eval``), a scripted
detector that carries ``Alert.p_kappa`` and a ``cause_set`` and offers the optional ``alert_inputs`` / ``likelihood_rule``
hooks, and arithmetic test values (T = 86_400_000 ms, H = one hour). Expected numbers are computed by hand in the
comments; none is a clinical value or a proposal.
"""

from __future__ import annotations

import dataclasses
import json
import math
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from ralmon.attribution import Alert, Detection
from ralmon.benchmark import LatentDay
from ralmon.eval import attribution_truth as T
from ralmon.eval.runner import (
    ConfigError,
    load_experiment,
    run_experiment,
    split_patients,
)
from tests.eval.helpers import C1, MINI, SMOKE, ms, write_config
from tests.eval.test_probabilistic_attribution import (
    count_vector,
    p_alert,
)
from tests.eval.test_runner import Scripted, hand_document, read_metrics, run_doc

NEW_KEYS = (
    "attribution_log_score",
    "attribution_brier",
    "attribution_calibration_curve",
    "attribution_sets",
    "attribution_equal_coverage",
    "pair_llr",
    "pair_direction_mcnemar",
)
H = 3_600_000
D = 86_400_000
SCALAR = {"value", "ci_lo", "ci_hi", "ci_cluster_lo", "ci_cluster_hi"}


class Probabilistic(Scripted):
    """A scripted detector with alerts that carry a posterior and the optional hooks of the scoring side."""

    def __init__(
        self,
        name: str,
        script: Mapping[tuple[str, int], Sequence[Detection]],
        inputs: Mapping[str, T.AlertInputs] | None = None,
        rule: Any = None,
    ) -> None:
        super().__init__(name, script)
        self.inputs = dict(inputs or {})
        self.likelihood_rule = rule
        self.calls: list[tuple[Any, ...]] = []

    def alert_inputs(self, patient_id: str, alert: Alert) -> T.AlertInputs | None:
        self.calls.append((patient_id, alert))
        return self.inputs.get(alert.xi.instance_key)


def factory(
    script: Mapping[tuple[str, int], Sequence[Detection]],
    inputs: Mapping[str, T.AlertInputs] | None = None,
    rule: Any = None,
    plain: Mapping[tuple[str, int], Sequence[Detection]] | None = None,
    created: list[Probabilistic] | None = None,
) -> Any:
    def build(name: str, env: Any, *, alpha: float | None = None) -> Scripted:
        if name.endswith("plain"):
            return Scripted(name, plain or {})
        detector = Probabilistic(name, script, inputs, rule)
        if created is not None:
            created.append(detector)
        return detector

    return build


def keyed(alert: Alert, key: str) -> Alert:
    return dataclasses.replace(
        alert, xi=dataclasses.replace(alert.xi, instance_key=key)
    )


# the hand case: p05 day 0 has a C1 range event at 14:00 (hypertensive_spike), day 1 a C3 injection_naive at 09:00 of that day
# (point event); p06 has no event. Alerts: p05 range 14:00:30 (C1 0.5, C2 0.3, C3 0.2; set hypertensive_spike,
# spontaneous_range), p05 sched at T + 09:00 (0.1, 0.1, 0.8; set injection_naive, replay), p06 range 12:00 (a false alarm).
SCRIPT: dict[tuple[str, int], list[Detection]] = {
    ("p05", 0): [
        keyed(
            p_alert(
                ms(14) + 30_000,
                "range",
                (0.5, 0.3, 0.2),
                cause_set=("hypertensive_spike", "spontaneous_range"),
            ),
            "r1",
        )
    ],
    ("p05", 1): [
        keyed(
            p_alert(
                D + ms(9),
                "sched",
                (0.1, 0.1, 0.8),
                cause_set=("injection_naive", "replay"),
            ),
            "s1",
        )
    ],
    ("p06", 0): [
        keyed(
            p_alert(
                ms(12),
                "range",
                (0.5, 0.3, 0.2),
                cause_set=("hypertensive_spike", "spontaneous_range"),
            ),
            "f1",
        )
    ],
}


def attribution_document(**options: Any) -> dict[str, Any]:
    doc = hand_document("ours-s1")
    doc["run_options"]["attribution"] = {
        "loose_after_ms": 60_000,
        **options,
    }  # TEST VALUE
    return doc


def run(
    tmp_path: Path, doc: Mapping[str, Any], fact: Any, out: str = "out"
) -> dict[str, Any]:
    return read_metrics(run_doc(tmp_path, doc, fact, out=out)[0])


# ---- the keys ---------------------------------------------------------------------------------------------------------


def test_the_new_keys_for_a_detector_with_p_kappa(tmp_path: Path) -> None:
    """p05's two alerts are caused by the C1 spike (RANGE) and the C3 injection_naive (SCHED); p06's alert has no event and is left
    out (counted). Log score: RANGE -ln 0.5 = 0.693147, SCHED -ln 0.8 = 0.223144; aggregate (equal weights, no RESP)
    0.458146. Brier: RANGE 0.25 + 0.09 + 0.04 = 0.38, SCHED 0.01 + 0.01 + 0.04 = 0.06. Sets: both cover the true subtype, size 2."""
    m = run(tmp_path, attribution_document(), factory(SCRIPT))
    assert set(NEW_KEYS) <= set(m)
    ls = m["attribution_log_score"]["ours-s1"]
    assert ls["primary_labelling"] == "tight"
    assert set(ls["labellings"]) == {"tight", "loose"}
    tight = ls["labellings"]["tight"]
    assert tight["templates"]["RANGE"]["n_alerts"] == 1
    assert tight["templates"]["RANGE"]["mean"]["value"] == pytest.approx(-math.log(0.5))
    assert tight["templates"]["SCHED"]["mean"]["value"] == pytest.approx(-math.log(0.8))
    assert set(tight["templates"]["RANGE"]["mean"]) >= SCALAR
    assert (
        tight["templates"]["HOLD"]["n_alerts"] == 0
        and tight["templates"]["HOLD"]["mean"] is None
    )
    assert tight["aggregate"]["mean"]["value"] == pytest.approx(
        (-math.log(0.5) - math.log(0.8)) / 2
    )
    assert tight["aggregate"]["weights"] == "equal"
    assert tight["aggregate"]["templates_averaged"] == ["RANGE", "SCHED"]
    assert "RESP" not in tight["templates"] and tight["resp"]["n_alerts"] == 0
    assert tight["excluded"]["no_compatible_event"] == 1
    br = m["attribution_brier"]["ours-s1"]["labellings"]["tight"]["templates"]
    assert br["RANGE"]["mean"]["value"] == pytest.approx(0.38)
    assert br["SCHED"]["mean"]["value"] == pytest.approx(0.06)
    sets = m["attribution_sets"]["ours-s1"]["labellings"]["tight"]
    assert sets["overall"]["n"] == 2 and sets["overall"]["coverage"] == 1.0
    assert sets["overall"]["mean_size"] == 2.0
    assert (
        sets["per_template"]["RANGE"]["n"] == 1 and sets["per_template"]["HOLD"] is None
    )
    assert sets["per_true_subtype"]["injection_naive"]["covered"] == 1
    assert sets["per_patient"]["n_patients"] == 1
    curve = m["attribution_calibration_curve"]["ours-s1"]["labellings"]["tight"][
        "templates"
    ]["RANGE"]
    assert curve["bins"] == 5  # ece_bins of the run options
    assert sum(b["n"] for b in curve["pooled"]) == 3  # three classes of one alert
    empty = [b for b in curve["pooled"] if b["n"] == 0]
    assert empty and all(
        b["mean_p"] is None and b["observed_rate"] is None for b in empty
    )


def test_both_labellings_are_in_every_table_and_the_metadata_says_why(
    tmp_path: Path,
) -> None:
    m = run(tmp_path, attribution_document(), factory(SCRIPT))
    for key in (
        "attribution_log_score",
        "attribution_brier",
        "attribution_calibration_curve",
        "attribution_sets",
    ):
        block = m[key]["ours-s1"]
        assert block["primary_labelling"] == "tight" and set(block["labellings"]) == {
            "tight",
            "loose",
        }
    meta = m["meta"]["attribution"]
    assert (
        meta["labelling"]["primary"] == "tight"
        and meta["labelling"]["reported_next_to_it"] == "loose"
    )
    assert "after seeing" in meta["labelling"]["choice"]
    assert meta["labelling"]["loose_after_ms"] == 60_000
    assert meta["effects"] == "fold" and "cascade" in meta["effects_note"]
    assert (
        meta["cell_scope"]["status"] == "not implemented"
        and meta["family"]["status"] == "not implemented"
    )
    assert "one designated alert per patient" in " ".join(
        meta["sets"]["assumptions"] + [meta["sets"]["exchangeability"]]
    )
    assert meta["score_definitions"]["brier"].startswith("sum over C1, C2, C3")
    assert "distribution-free" not in json.dumps(meta).replace(
        "distribution-free coverage is never", ""
    )


def test_loose_and_tight_differ_when_the_faulty_device_is_out_of_the_data_scope(
    tmp_path: Path,
) -> None:
    """The p02 ble_dropout (C2, 09:00-09:30) is logged on the ECG: under the loose labelling the COUNT alert at 09:10 is a C2 alert,
    under the tight one the ECG is in the data scope of no template and the alert has no cause."""
    bench = tmp_path / "bench"
    shutil.copytree(MINI, bench)
    path = bench / "truth" / "p02" / "0.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["injection_log"] = [
        {
            "cls": "C2",
            "subtype": "ble_dropout",
            "onset_ms": ms(9),
            "end_ms": ms(9, 30),
            "realised": True,
            "params": {},
            "details": {"target": "ecg", "templates": ["sched", "hold", "count"]},
            "truth_indices": [0],
            "explains_in_later_days": [],
        }
    ]
    path.write_text(json.dumps(doc), encoding="utf-8")
    script = {
        ("p02", 0): [
            keyed(
                p_alert(
                    ms(9, 10), "count", (0.2, 0.7, 0.1), cause_set=("ble_dropout",)
                ),
                "c1",
            )
        ]
    }
    d = attribution_document()
    d["benchmark_manifest"] = str(bench)
    m = run(tmp_path, d, factory(script))
    blocks = m["attribution_log_score"]["ours-s1"]["labellings"]
    assert blocks["loose"]["templates"]["COUNT"]["n_alerts"] == 1
    assert blocks["tight"]["templates"]["COUNT"]["n_alerts"] == 0
    assert blocks["tight"]["excluded"]["no_compatible_event"] == 1


def test_methods_without_p_kappa_are_null_in_the_file(tmp_path: Path) -> None:
    doc = attribution_document()
    doc["detectors"] = ["ours-s1", "ours-plain"]
    plain = {("p05", 0): [Detection(ms(14), C1, 1.0)]}
    m = run(tmp_path, doc, factory(SCRIPT, plain=plain))
    for key in NEW_KEYS:
        assert m[key]["ours-plain"] is None, key


def test_the_smoke_run_has_the_new_keys(tmp_path: Path) -> None:
    """B1 and B3 emit plain detections: every new key is null for them. The hierarchical ``ours`` has no p_kappa (scores, curves,
    equal coverage, pairs: null) but its alerts carry a kappa, which is scored as a set (``attribution_sets``) against the
    applicable subtypes of the likelihood table; the labelling needs ``loose_after_ms`` (a test value of the smoke config)."""
    config, options = load_experiment(SMOKE)
    folders = run_experiment(config, options, tmp_path / "o", git_rev=lambda: "rev0")
    m = read_metrics(folders[0])
    for key in NEW_KEYS:
        assert set(m[key]) == set(config.detectors), key
        for name in ("B1", "B3"):
            assert m[key][name] is None, (key, name)
        if key != "attribution_sets":
            assert m[key]["ours"] is None, key
    sets = m["attribution_sets"]["ours"]
    assert sets["primary_labelling"] == "tight" and set(sets["labellings"]) == {
        "tight",
        "loose",
    }
    loose = sets["labellings"]["loose"]
    assert loose is None or loose["set_source"] == "kappa_as_set"
    assert m["meta"]["attribution"]["status"] == "configured"
    assert m["meta"]["attribution"]["sets"]["applicable_table"].startswith(
        "configs/attribution_likelihood.yaml"
    )


def test_without_the_awaiting_value_the_blocks_say_so(tmp_path: Path) -> None:
    """No ``run_options.attribution``: ``loose_after_ms`` is an awaiting_human_value, so a detector with a posterior gets a status
    block naming what is missing, not a number."""
    doc = hand_document("ours-s1")
    doc["run_options"].pop(
        "attribution"
    )  # the smoke config of the fixtures carries a test value
    m = run(tmp_path, doc, factory(SCRIPT))
    block = m["attribution_log_score"]["ours-s1"]
    assert block["status"] == "awaiting_human_value"
    assert block["needs"] == ["run_options.attribution.loose_after_ms"]
    assert m["meta"]["attribution"]["status"] == "not configured"
    doc["run_options"][
        "attribution"
    ] = {}  # a section without the value: the value is awaiting
    again = run(tmp_path, doc, factory(SCRIPT), out="again")
    assert again["meta"]["attribution"]["status"] == "awaiting_human_value"
    assert again["attribution_log_score"]["ours-s1"]["status"] == "awaiting_human_value"


def test_zero_probability_is_null_with_a_reason_and_the_file_is_valid_json(
    tmp_path: Path,
) -> None:
    script = {
        ("p05", 0): [
            keyed(
                p_alert(
                    ms(14) + 30_000,
                    "range",
                    (0.0, 0.5, 0.5),
                    cause_set=("hypertensive_spike",),
                ),
                "r1",
            )
        ]
    }
    d = run_doc(tmp_path, attribution_document(), factory(script))[0]
    text = (d / "metrics.json").read_text(encoding="utf-8")
    assert "Infinity" not in text and "NaN" not in text
    m = json.loads(text)
    leaf = m["attribution_log_score"]["ours-s1"]["labellings"]["tight"]["templates"][
        "RANGE"
    ]
    assert leaf["n_alerts"] == 1 and leaf["n_zero_probability"] == 1
    assert leaf["mean"]["value"] is None and "zero probability" in leaf["reason"]


def test_the_scoring_hooks_receive_the_alert_and_no_truth(tmp_path: Path) -> None:
    created: list[Probabilistic] = []
    run(tmp_path, attribution_document(), factory(SCRIPT, created=created))
    detector = created[0]
    assert detector.calls, (
        "the runner asks the detector for the inputs of every labelled alert"
    )
    for patient_id, alert in detector.calls:
        assert isinstance(patient_id, str) and isinstance(alert, Alert)
    for day in detector.run_days:
        assert not isinstance(day, LatentDay)


# ---- equal coverage in the runner ---------------------------------------------------------------------------------------

#: one alert for each event of the mini benchmark, at an instant its event can cause (see the truth of the fixture)
EQ_EVENTS = {
    ("p01", 0): ("range", ms(14) + 30_000, "hypertensive_spike"),
    ("p02", 0): ("sched", ms(9, 10), "ble_dropout"),
    ("p02", 1): ("range", D + ms(15), "replay"),
    ("p03", 0): ("sched", ms(8, 30), "missed_measurement"),
    ("p04", 1): ("range", D + ms(11, 30), "stuck_at"),
    ("p05", 0): ("range", ms(14) + 30_000, "hypertensive_spike"),
    ("p05", 1): ("sched", D + ms(9), "injection_naive"),
}
NAMES = (
    "hypertensive_spike",
    "ble_dropout",
    "replay",
    "missed_measurement",
    "stuck_at",
    "injection_naive",
)


def eq_script() -> tuple[
    dict[tuple[str, int], list[Detection]], dict[str, T.AlertInputs]
]:
    script: dict[tuple[str, int], list[Detection]] = {}
    inputs: dict[str, T.AlertInputs] = {}
    for (patient, day), (tau, t, name) in EQ_EVENTS.items():
        key = f"{patient}-{day}"
        script[(patient, day)] = [
            keyed(p_alert(t, tau, (0.4, 0.3, 0.3), cause_set=(name,)), key)
        ]
        post = {n: (0.5 if n == name else 0.1) for n in NAMES}
        prior = {n: 1 / len(NAMES) for n in NAMES}
        inputs[key] = T.AlertInputs({"lik": post, "prior": prior}, {}, None)
    return script, inputs


def test_equal_coverage_runs_on_the_calibration_part_and_scores_the_test_part(
    tmp_path: Path,
) -> None:
    script, inputs = eq_script()
    doc = attribution_document(
        set_alphas=[0.5]
    )  # TEST VALUE: the calibration part is tiny
    doc["split"] = {"train": 0.34, "calibration": 0.33, "test": 0.33}
    m = run(tmp_path, doc, factory(script, inputs))
    split = split_patients(["p01", "p02", "p03", "p04", "p05", "p06"], doc["split"], 0)
    cal = sorted(p for p, v in split.items() if v == "calibration")
    test = sorted(p for p, v in split.items() if v == "test")
    n_cal = sum(1 for (p, _d) in EQ_EVENTS if p in cal)
    n_test = sum(1 for (p, _d) in EQ_EVENTS if p in test)
    eq = m["attribution_equal_coverage"]["ours-s1"]["labellings"]["tight"]
    assert (
        eq["population"] == "main"
        and eq["n_calibration"] == n_cal
        and eq["n_test"] == n_test
    )
    assert set(eq["methods"]) == {"lik", "prior"}
    cell = eq["methods"]["lik"]["alphas"]["0.5"]["marginal"]
    assert cell["n"] == n_test
    assert set(cell["per_template"]) <= {
        "RANGE",
        "SCHED",
        "HOLD",
        "COUNT",
        "RESP",
        "SYS",
        "INT",
    }
    assert m["meta"]["attribution"]["sets"]["calibration_patients"] == cal
    json.dumps(m, allow_nan=False)


def test_equal_coverage_without_alphas_says_so(tmp_path: Path) -> None:
    script, inputs = eq_script()
    m = run(tmp_path, attribution_document(), factory(script, inputs))
    block = m["attribution_equal_coverage"]["ours-s1"]
    assert block["status"] == "awaiting_human_value"
    assert block["needs"] == ["run_options.attribution.set_alphas"]


# ---- the pairs -------------------------------------------------------------------------------------------------------------


def pair_benchmark(tmp_path: Path, flag: bool = False) -> Path:
    """A copy of the mini benchmark whose pair01 members carry the per-pair flag ``indistinguishable_by_construction``."""
    bench = tmp_path / "bench"
    shutil.copytree(MINI, bench)
    for patient in ("p07", "p08"):
        path = bench / "truth" / patient / "0.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        cls, sub = (
            ("C1", "double_take") if patient == "p07" else ("C2", "dispenser_bounce")
        )
        doc["injection_log"] = [
            {
                "cls": cls,
                "subtype": sub,
                "onset_ms": ms(20),
                "end_ms": None,
                "realised": True,
                "params": {},
                "details": {
                    "target": "dispenser",
                    "templates": ["count", "hold", "resp", "int"],
                },
                "truth_indices": [0],
                "explains_in_later_days": [],
                "variant_id": "v01",
                "indistinguishable_by_construction": flag,
            }
        ]
        path.write_text(json.dumps(doc), encoding="utf-8")
    return bench


def pair_script() -> tuple[
    dict[tuple[str, int], list[Detection]], dict[str, T.AlertInputs]
]:
    ea, eb = count_vector(1.5, 20_000), count_vector(0.0, 5_000)
    script = {
        ("p07", 0): [
            keyed(
                p_alert(
                    ms(20) + 10_000,
                    "count",
                    (0.3, 0.4, 0.3),
                    cause_set=("double_take",),
                ),
                "pa",
            )
        ],
        ("p08", 0): [
            keyed(
                p_alert(
                    ms(20) + 10_000,
                    "count",
                    (0.3, 0.4, 0.3),
                    cause_set=("dispenser_bounce",),
                ),
                "pb",
            )
        ],
    }
    inputs = {
        "pa": T.AlertInputs({}, {}, ea),
        "pb": T.AlertInputs({}, {}, eb),
    }
    return script, inputs


def test_pairs_directions_and_mcnemar_in_the_runner(tmp_path: Path) -> None:
    """One distinguishable pair (double take / bounce at COUNT), evidence as in the library test: Lambda_A = +5.278, Lambda_B =
    -8.507, D = 13.785, both members in the right direction. A second detector sees the evidence swapped (wrong direction): the
    McNemar table of the first against the second has b = 1, c = 0, exact p = 1 (n = 1)."""
    from ralmon.attribution.likelihood import load_likelihood_table
    from tests.attribution.test_likelihood_rule import build_rule
    from tests.eval.test_probabilistic_attribution import REGISTRY

    rule = build_rule(
        REGISTRY,
        load_likelihood_table(
            Path(__file__).resolve().parents[2]
            / "configs"
            / "attribution_likelihood.yaml"
        ),
    )
    script, inputs = pair_script()
    swapped = {"pa": inputs["pb"], "pb": inputs["pa"]}
    bench = pair_benchmark(tmp_path)

    def build(name: str, env: Any, *, alpha: float | None = None) -> Scripted:
        return Probabilistic(
            name, script, swapped if name.endswith("s2") else inputs, rule
        )

    doc = attribution_document()
    doc["benchmark_manifest"] = str(bench)
    doc["detectors"] = ["ours-s1", "ours-s2"]
    doc["run_options"]["twins"] = "separate"
    m = run(tmp_path, doc, build)
    block = m["pair_llr"]["ours-s1"]
    assert block["strata"]["distinguishable"]["n_pairs"] == 1
    assert block["strata"]["distinguishable"]["n_both_right"] == 1
    assert block["strata"]["indistinguishable"]["n_pairs"] == 0
    assert "precision" not in json.dumps(block)
    only = block["pairs"][0]
    assert (
        only["pair_id"] == "pair01"
        and only["group"] == "double_take_vs_bounce"
        and only["template"] == "count"
    )
    assert only["lambda_a"] == pytest.approx(5.278, abs=2e-3) and only[
        "lambda_b"
    ] == pytest.approx(-8.507, abs=2e-3)
    assert only["d"] == pytest.approx(13.785, abs=4e-3)
    assert m["pair_llr"]["ours-s2"]["strata"]["distinguishable"]["n_both_right"] == 0
    mc = m["pair_direction_mcnemar"]["ours-s1"]["vs"]["ours-s2"]
    assert (
        (mc["b"], mc["c"], mc["n_discordant"]) == (1, 0, 1)
        and mc["p"] == 1.0
        and mc["n_pairs"] == 1
    )
    assert m["pair_direction_mcnemar"]["ours-s2"]["vs"]["ours-s1"]["c"] == 1
    assert m["meta"]["attribution"]["pairs"]["precision"] == "not computed on pairs"
    eq = m["attribution_equal_coverage"]["ours-s1"]
    assert eq["status"] == "awaiting_human_value"


def test_the_indistinguishable_stratum_has_d_exactly_zero(tmp_path: Path) -> None:
    from ralmon.attribution.likelihood import load_likelihood_table
    from tests.attribution.test_likelihood_rule import build_rule
    from tests.eval.test_probabilistic_attribution import REGISTRY

    rule = build_rule(
        REGISTRY,
        load_likelihood_table(
            Path(__file__).resolve().parents[2]
            / "configs"
            / "attribution_likelihood.yaml"
        ),
    )
    same = T.AlertInputs({}, {}, count_vector(0.0, 5_000))
    script, _ = pair_script()
    doc = attribution_document()
    doc["benchmark_manifest"] = str(pair_benchmark(tmp_path, flag=True))
    doc["run_options"]["twins"] = "separate"
    m = run(tmp_path, doc, factory(script, {"pa": same, "pb": same}, rule))
    ind = m["pair_llr"]["ours-s1"]["strata"]["indistinguishable"]
    assert ind["n_pairs"] == 1 and ind["n_d_exactly_zero"] == 1
    assert ind["abs_lambda"]["mean"] > 0.0


def test_pairs_need_the_twins_policy_separate(tmp_path: Path) -> None:
    from ralmon.attribution.likelihood import load_likelihood_table
    from tests.attribution.test_likelihood_rule import build_rule
    from tests.eval.test_probabilistic_attribution import REGISTRY

    rule = build_rule(
        REGISTRY,
        load_likelihood_table(
            Path(__file__).resolve().parents[2]
            / "configs"
            / "attribution_likelihood.yaml"
        ),
    )
    script, inputs = pair_script()
    m = run(tmp_path, attribution_document(), factory(script, inputs, rule))
    assert (
        m["pair_llr"]["ours-s1"]["status"]
        == "twins policy is 'exclude': the confounder pairs are not run"
    )
    assert m["pair_direction_mcnemar"]["ours-s1"] is None
    assert "twins policy" in m["meta"]["attribution"]["pairs"]["status"]


# ---- configuration ---------------------------------------------------------------------------------------------------------


def test_the_attribution_options_round_trip_and_are_validated(tmp_path: Path) -> None:
    doc = attribution_document(
        set_alphas=[0.1, 0.2],
        effects="include",
        pair_primary_templates={"double_take_vs_bounce": "count"},
    )
    path = write_config(tmp_path / "c.yaml", doc)
    config, options = load_experiment(path)
    assert options.attribution is not None
    assert options.attribution.loose_after_ms == 60_000
    assert options.attribution.set_alphas == (0.1, 0.2)
    assert options.attribution.effects == "include"
    assert options.attribution.pair_primary_templates == {
        "double_take_vs_bounce": "count"
    }
    from ralmon.eval.runner import dump_experiment

    again = tmp_path / "again.yaml"
    again.write_text(dump_experiment(config, options, base=tmp_path), encoding="utf-8")
    assert load_experiment(again)[1].attribution == options.attribution
    for bad in (
        {"loose_after_ms": -1},
        {"loose_after_ms": 1.5},
        {"set_alphas": [1.5]},
        {"set_alphas": [0.2, 0.2]},
        {"effects": "nonsense"},
        {"unknown_key": 1},
        {"pair_primary_templates": {"g": "nonsense"}},
    ):
        bad_doc = attribution_document(**bad)
        if "loose_after_ms" in bad:
            bad_doc["run_options"]["attribution"] = dict(bad)
        with pytest.raises(ConfigError):
            load_experiment(write_config(tmp_path / "bad.yaml", bad_doc))


# ---- writers and bookkeeping ---------------------------------------------------------------------------------------------


def test_the_writer_turns_a_level_into_a_string_and_keeps_infinity_out() -> None:
    """A level of the set calibration is a ``Fraction`` (a decimal string would hide it): the writer writes ``"1/11"``; ``inf``
    (the full-set threshold) is never written as a number, and a threshold written by the blocks is ``null`` with ``fallback``."""
    from fractions import Fraction

    from ralmon.conformal.sets import SetThreshold
    from ralmon.eval import attribution_sets as S
    from ralmon.eval.runner import _clean

    assert _clean({"alpha": Fraction(1, 11), "t": math.inf}) == {
        "alpha": "1/11",
        "t": None,
    }
    written = S.threshold_json(SetThreshold(math.inf, 2, True, "too few", "sched"))
    assert written == {
        "value": None,
        "n": 2,
        "fallback": True,
        "reason": "too few",
        "cell": "sched",
    }
    assert S.alpha_key(Fraction(2, 11)) == "2/11" and S.alpha_key(0.1) == "0.1"


def test_the_run_on_the_calibration_part_leaves_the_counters_of_the_detections(
    tmp_path: Path,
) -> None:
    """The detector is also run on the calibration patients to calibrate the sets; the counts of emitted detections of the test run
    must not change because of it."""
    script, inputs = eq_script()
    doc = attribution_document()
    doc["split"] = {"train": 0.34, "calibration": 0.33, "test": 0.33}
    without = run(tmp_path, doc, factory(script, inputs), out="without")
    doc["run_options"]["attribution"]["set_alphas"] = [0.5]
    with_cal = run(tmp_path, doc, factory(script, inputs), out="with")
    key = "detections"
    assert without["analysis"]["run"][key] == with_cal["analysis"]["run"][key]
    assert (
        with_cal["attribution_equal_coverage"]["ours-s1"]["labellings"]["tight"]
        is not None
    )


def test_the_rule_metadata_is_in_the_file(tmp_path: Path) -> None:
    """``meta.attribution.rules`` carries the sensitivity values the rule used and the version token of its posterior model."""
    from ralmon.attribution.likelihood import load_likelihood_table
    from tests.attribution.test_likelihood_rule import TEST_VALUES, build_rule
    from tests.eval.test_probabilistic_attribution import REGISTRY

    root = Path(__file__).resolve().parents[2]
    rule = build_rule(
        REGISTRY,
        load_likelihood_table(root / "configs" / "attribution_likelihood.yaml"),
    )
    m = run(tmp_path, attribution_document(), factory(SCRIPT, rule=rule))
    meta = m["meta"]["attribution"]["rules"]["ours-s1"]
    assert meta["model_version"] == rule.model_version
    assert set(meta["sensitivity_values"]) >= {
        "eps",
        "qc",
        "class_priors",
        "pi_designs",
    }
    assert meta["sensitivity_values"]["eps"]["value"] == TEST_VALUES["eps"]


# ---- fix round: the ambiguous class, mean_finite, role swap ----------------------------------------------------------------


def point_fault_benchmark(tmp_path: Path) -> Path:
    """The mini benchmark whose p02 day 0 holds a point ``manipulation_failure`` (C2, injected) at 08:00 and a natural C1
    ``spontaneous_resp`` window 08:05-08:10 (the scenario of the review)."""
    bench = tmp_path / "bench"
    shutil.copytree(MINI, bench)
    path = bench / "truth" / "p02" / "0.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["ground_truth"] = [
        {
            "cls": "C2",
            "subtype": "manipulation_failure",
            "onset_ms": ms(8),
            "end_ms": None,
            "injected": True,
            "template_id": None,
            "confounder_group": None,
        },
        {
            "cls": "C1",
            "subtype": "spontaneous_resp",
            "onset_ms": ms(8, 5),
            "end_ms": ms(8, 10),
            "injected": False,
            "template_id": "resp",
            "confounder_group": None,
        },
    ]
    doc["injection_log"] = [
        {
            "cls": "C2",
            "subtype": "manipulation_failure",
            "onset_ms": ms(8),
            "end_ms": None,
            "realised": True,
            "params": {},
            "details": {"target": "robot", "templates": ["sched", "resp", "hold"]},
            "truth_indices": [0],
            "explains_in_later_days": [],
        }
    ]
    path.write_text(json.dumps(doc), encoding="utf-8")
    return bench


def test_the_runner_reports_the_ambiguous_class_and_the_subtype_table(
    tmp_path: Path,
) -> None:
    script = {
        ("p02", 0): [
            keyed(
                p_alert(
                    ms(8, 10),
                    "resp",
                    (0.3, 0.4, 0.3),
                    cause_set=("manipulation_failure",),
                ),
                "r1",
            )
        ]
    }
    doc = attribution_document()
    doc["run_options"]["attribution"]["loose_after_ms"] = 24 * H  # TEST VALUE
    doc["benchmark_manifest"] = str(point_fault_benchmark(tmp_path))
    m = run(tmp_path, doc, factory(script))
    labs = m["attribution_log_score"]["ours-s1"]["labellings"]
    assert (
        labs["tight"]["resp"]["n_alerts"] == 0
        and labs["tight"]["excluded"]["ambiguous"] == 1
    )
    assert labs["loose"]["resp"]["n_alerts"] == 1
    block = m["attribution_labelling"]["ours-s1"]
    table = block["injected_subtype_table"]
    assert table["manipulation_failure"] == {"tight": 0, "ambiguous": 1, "loose": 1}
    assert table["replay"] == {
        "tight": 0,
        "ambiguous": 0,
        "loose": 0,
    }  # zeros are shown
    assert block["ambiguous"]["manipulation_failure"]["loose_labels"] == {
        "C2/manipulation_failure": 1
    }
    assert "manipulation_failure" in block["point_subtypes"]
    assert block["headline_for_point_subtypes"] == "loose"
    sets = m["attribution_sets"]["ours-s1"]["labellings"]
    assert (
        sets["tight"] is None
        or sets["tight"]["overall"]["n"] == 0
        or "manipulation_failure" not in sets["tight"]["per_true_subtype"]
    )
    meta = m["meta"]["attribution"]["labelling"]
    assert (
        "loose" in meta["point_c2_headline"]
        and "C1 and C3" in meta["loose_after_ms_scope"]
    )
    assert (
        m["attribution_labelling"]["B1"] is None
        if "B1" in m["attribution_labelling"]
        else True
    )


def test_mean_finite_next_to_a_null_log_score_mean(tmp_path: Path) -> None:
    script = {
        ("p05", 0): [
            keyed(
                p_alert(
                    ms(14) + 30_000,
                    "range",
                    (0.0, 0.5, 0.5),
                    cause_set=("hypertensive_spike",),
                ),
                "r1",
            ),
            keyed(
                p_alert(
                    ms(14) + 40_000,
                    "range",
                    (0.5, 0.3, 0.2),
                    cause_set=("hypertensive_spike",),
                ),
                "r2",
            ),
        ]
    }
    m = run(tmp_path, attribution_document(), factory(script))
    leaf = m["attribution_log_score"]["ours-s1"]["labellings"]["tight"]["templates"][
        "RANGE"
    ]
    assert (
        leaf["n_alerts"] == 2
        and leaf["n_zero_probability"] == 1
        and leaf["mean"]["value"] is None
    )
    assert leaf["mean_finite"]["value"] == pytest.approx(-math.log(0.5))


def test_the_role_swap_is_reported_next_to_the_equal_coverage(tmp_path: Path) -> None:
    script, inputs = eq_script()
    doc = attribution_document(set_alphas=[0.5])
    doc["split"] = {"train": 0.34, "calibration": 0.33, "test": 0.33}
    m = run(tmp_path, doc, factory(script, inputs))
    eq = m["attribution_equal_coverage"]["ours-s1"]["labellings"]["tight"]
    swap = eq["role_swap"]
    assert (
        swap["n_calibration"] == eq["n_test"] and swap["n_test"] == eq["n_calibration"]
    )
    assert "role" in swap["population"]
