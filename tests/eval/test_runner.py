"""Runner of WS08-T01 (tests 27 to 41, 47 to 49 of the task list, plus the guards and the scoring conventions).

ILLUSTRATIVE, UNVERIFIED, FIXTURE-ONLY. The runs use the hand-written mini benchmark of ``tests/fixtures/eval`` and, where
a number is asserted, a scripted detector whose detections are listed here; every expected value is derived by hand in
the comments (T = 86_400_000 ms; the truth of the fixture is in ``tests/fixtures/eval/build_mini_benchmark.py``).
"""

from __future__ import annotations

import copy
import json
import sys
import types
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml
from hypothesis import given
from hypothesis import strategies as st

from ralmon.attribution import Detection
from ralmon.benchmark import LatentDay, ObservedDay
from ralmon.eval import runner
from ralmon.eval.runner import (
    ConfigError,
    GuardError,
    HookResult,
    RunFacts,
    RunOptions,
    TruthAccessError,
    current_git_rev,
    evaluate_guards,
    load_experiment,
    main,
    run_experiment,
    split_patients,
)
from ralmon.monitor import VerdictState
from tests.eval.helpers import (
    C1,
    C2,
    C3,
    MINI,
    SMOKE,
    UND,
    T,
    det,
    ms,
    smoke_document,
    write_config,
)

METRICS = (
    "per_class_prf",
    "detection_delay_ms",
    "false_alarms_per_patient_day",
    "recall_vs_false_alarm_curve",
    "empirical_coverage",
    "mean_interval_width",
    "expected_calibration_error",
    "attribution_confusion",
    "accuracy_vs_coverage",
    "latency_percentiles",
    "severity_rank_agreement",
)
META_KEYS = {
    "experiment_id",
    "seed",
    "n_test_patients",
    "n_test_patient_days",
    "detectors",
    "match",
    "alpha",
    "alpha_grid",
    "prior_source",
    "coverage_qualifier",
    "bootstrap",
}
SCALAR_KEYS = {"value", "ci_lo", "ci_hi", "ci_cluster_lo", "ci_cluster_hi"}


# ---- scripted detectors ----------------------------------------------------------------------------------------------


class Scripted:
    """A detector whose output is a table keyed by (patient, day); it records what the runner hands it."""

    def __init__(
        self, name: str, script: Mapping[tuple[str, int], Sequence[Detection]]
    ) -> None:
        self.name = name
        self.script = dict(script)
        self.fit_args: list[tuple[list[Any], list[Any]]] = []
        self.run_days: list[Any] = []

    def fit(self, train_days: Sequence[Any], calib_days: Sequence[Any]) -> None:
        self.fit_args.append((list(train_days), list(calib_days)))

    def run(
        self, day: Any, plan: Any, evidence: Any, **kwargs: Any
    ) -> Sequence[Detection]:
        self.run_days.append(day)
        return list(self.script.get((day.patient_id, day.day_index), ()))


def factory_for(
    script: Mapping[tuple[str, int], Sequence[Detection]],
    created: list[Scripted] | None = None,
) -> Callable[..., Any]:
    def build(name: str, env: Any, *, alpha: float | None = None) -> Scripted:
        detector = Scripted(name, script)
        if created is not None:
            created.append(detector)
        return detector

    return build


# the hand case: all six virtual patients are test patients (fractions 0, 0, 1)
SCRIPT: dict[tuple[str, int], list[Detection]] = {
    ("p01", 0): [det(ms(14) + 30_000, C1)],  # the 14:00 range event, 30 s late
    ("p01", 1): [
        det(2 * T, C1)
    ],  # the closing step of the last scored day: the resp event of the tail day
    ("p02", 0): [det(ms(9), C3)],  # the ble_dropout (C2) event, labelled C3
    ("p03", 0): [
        det(ms(8, 30), C1),
        det(ms(8, 30) + 10_000, C1),
    ],  # the sched event (ref 08:30) and a duplicate
    ("p03", 1): [det(2 * T - 30_000, C1)],  # the day-end count (ref 2T), 30 s early
    ("p04", 1): [det(T + ms(11), C2)],  # the stuck_at event
    ("p05", 0): [
        det(ms(14), UND),
        det(ms(3), C1),
    ],  # the range event (abstained) and a false alarm at 03:00
    ("p06", 0): [det(ms(12), C2)],  # false alarm
    ("p06", 1): [
        det(T + ms(12), C1),
        det(2 * T + ms(10), C1),
    ],  # false alarm; one inside the unscored tail day
}


def hand_document(detector: str = "ours-s1", **overrides: Any) -> dict[str, Any]:
    doc = smoke_document()
    doc["detectors"] = [detector]
    doc["split"] = {"train": 0.0, "calibration": 0.0, "test": 1.0}
    doc["match"] = {"tolerance_ms": 60_000, "time_reference": "first_decidable"}
    doc["run_options"]["n_bootstrap"] = 100
    doc.update(overrides)
    return doc


def run_doc(
    tmp_path: Path,
    doc: Mapping[str, Any],
    factory: Callable[..., Any] | None,
    *,
    out: str = "out",
    git_rev: Callable[[], str] = lambda: "rev0",
) -> list[Path]:
    config, options = load_experiment(write_config(tmp_path / "cfg.yaml", doc))
    return run_experiment(
        config, options, tmp_path / out, git_rev=git_rev, detector_factory=factory
    )


def read_metrics(seed_dir: Path) -> dict[str, Any]:
    return json.loads((seed_dir / "metrics.json").read_text(encoding="utf-8"))  # type: ignore[no-any-return]


@pytest.fixture(scope="module")
def hand_run(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    tmp = tmp_path_factory.mktemp("hand")
    created: list[Scripted] = []
    dirs = run_doc(tmp, hand_document(), factory_for(SCRIPT, created))
    return {"dir": dirs[0], "metrics": read_metrics(dirs[0]), "detectors": created}


# 27
def test_split_sizes_largest_remainder() -> None:
    ids = [f"p{i}" for i in range(7)]
    sizes = Counter(
        split_patients(
            ids, {"train": 0.5, "calibration": 0.25, "test": 0.25}, 0
        ).values()
    )
    assert (sizes["train"], sizes["calibration"], sizes["test"]) == (
        3,
        2,
        2,
    )  # 3.5, 1.75, 1.75 -> 3, 2, 2
    ids = [f"p{i}" for i in range(10)]
    sizes = Counter(
        split_patients(ids, {"train": 0.6, "calibration": 0.2, "test": 0.2}, 0).values()
    )
    assert (sizes["train"], sizes["calibration"], sizes["test"]) == (6, 2, 2)


# 28
@given(
    n=st.integers(0, 40),
    a=st.integers(0, 100),
    b=st.integers(0, 100),
    seed=st.integers(0, 2**32),
)
def test_prop_split_is_patient_disjoint_and_complete(
    n: int, a: int, b: int, seed: int
) -> None:
    if a + b > 100:
        a, b = a % 51, b % 50
    fractions = {"train": a / 100, "calibration": b / 100, "test": (100 - a - b) / 100}
    ids = [f"p{i:03d}" for i in range(n)]
    split = split_patients(ids, fractions, seed)
    assert sorted(split) == sorted(
        ids
    )  # every id in exactly one split (a mapping has one value per key)
    assert set(split.values()) <= {"train", "calibration", "test"}


# 29
def test_split_same_seed_same_split_different_seed_differs_and_manifest_order_irrelevant() -> (
    None
):
    ids = [f"p{i:03d}" for i in range(30)]
    fr = {"train": 0.5, "calibration": 0.25, "test": 0.25}
    assert split_patients(ids, fr, 3) == split_patients(ids, fr, 3)
    assert split_patients(ids, fr, 3) != split_patients(ids, fr, 4)
    assert split_patients(list(reversed(ids)), fr, 3) == split_patients(ids, fr, 3)


# 30
def test_seed_streams_are_independent(tmp_path: Path) -> None:
    splits = []
    for n_boot in (50, 120):
        doc = hand_document()
        doc["split"] = {"train": 0.34, "calibration": 0.33, "test": 0.33}
        doc["run_options"]["n_bootstrap"] = n_boot
        d = run_doc(tmp_path, doc, factory_for({}), out=f"o{n_boot}")[0]
        splits.append(read_metrics(d)["analysis"]["run"]["split"])
    assert splits[0] == splits[1]


# 31
def test_load_experiment_roundtrip(tmp_path: Path) -> None:
    config, options = load_experiment(SMOKE)
    assert config.experiment_id == "smoke" and config.seeds == [0]
    assert (
        config.match.tolerance_ms == 60_000
        and config.match.time_reference == "first_decidable"
    )
    assert (
        config.monitor is not None
        and config.monitor.step_ms == 60_000
        and config.monitor.alpha == 0.5
    )
    assert (
        options.headline is False
        and options.alpha_grid == (0.5,)
        and options.ece_bins == 5
    )
    text = runner.dump_experiment(config, options)
    again_path = tmp_path / "again.yaml"
    again_path.write_text(text, encoding="utf-8")
    config2, options2 = load_experiment(again_path)
    assert (config2, options2) == (config, options)
    assert runner.dump_experiment(config2, options2) == text


# 32
@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(split={"train": 0.5, "calibration": 0.2, "test": 0.2}),
        lambda d: d.update(seeds=[0, 0]),
        lambda d: (d["run_options"].update(headline=True), d.update(seeds=[0, 1, 2])),
        lambda d: d.update(detectors=["B9"]),
        lambda d: d.update(
            match={"tolerance_ms": 60_000, "time_reference": "deadline"}
        ),
        lambda d: d["run_options"].pop("n_bootstrap"),
        lambda d: d.update(unknown_key=1),
        lambda d: d.update(alpha=1.5),
    ],
)
def test_load_experiment_rejects_invalid(
    tmp_path: Path, mutate: Callable[[dict[str, Any]], Any]
) -> None:
    doc = smoke_document()
    mutate(doc)
    with pytest.raises(ConfigError):
        load_experiment(write_config(tmp_path / "bad.yaml", doc))


def test_load_experiment_rejects_a_duplicate_yaml_key_and_a_missing_file(
    tmp_path: Path,
) -> None:
    bad = tmp_path / "dup.yaml"
    bad.write_text("experiment_id: a\nexperiment_id: b\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_experiment(bad)
    with pytest.raises(ConfigError):
        load_experiment(tmp_path / "missing.yaml")


# 33
def test_run_writes_three_files_per_seed(tmp_path: Path) -> None:
    doc = hand_document(seeds=[0, 1])
    dirs = run_doc(tmp_path, doc, factory_for(SCRIPT))
    assert [d.name for d in dirs] == ["0", "1"]
    for seed in (0, 1):
        folder = tmp_path / "out" / "smoke" / str(seed)
        assert sorted(p.name for p in folder.iterdir()) == [
            "config.yaml",
            "git_rev.txt",
            "metrics.json",
        ]


# 34
def test_git_rev_txt_content(tmp_path: Path) -> None:
    dirs = run_doc(
        tmp_path,
        hand_document(seeds=[3]),
        factory_for(SCRIPT),
        git_rev=lambda: "abc123",
    )
    assert (dirs[0] / "git_rev.txt").read_text(encoding="utf-8") == "abc123\n"
    recorded = yaml.safe_load((dirs[0] / "config.yaml").read_text(encoding="utf-8"))
    assert recorded["seeds"] == [3]
    assert recorded["experiment_id"] == "smoke"
    assert "run_options" in recorded


# 35
def test_metrics_json_top_level_keys(hand_run: dict[str, Any]) -> None:
    m = hand_run["metrics"]
    assert set(m) <= set(METRICS) | {"meta", "analysis", "per_template", "background"}
    assert set(METRICS) <= set(m)  # a metric that does not apply is null, never omitted
    assert META_KEYS <= set(m["meta"])
    assert m["meta"]["experiment_id"] == "smoke" and m["meta"]["seed"] == 0
    assert m["meta"]["n_test_patients"] == 6 and m["meta"]["n_test_patient_days"] == 12
    assert m["meta"]["detectors"] == ["ours-s1"]
    assert m["meta"]["match"] == {
        "tolerance_ms": 60_000,
        "time_reference": "first_decidable",
    }
    assert m["meta"]["alpha"] == 0.5 and m["meta"]["alpha_grid"] == [0.5]
    assert m["meta"]["prior_source"] == "fixture_prior"
    assert m["meta"]["coverage_qualifier"] == (
        "marginal over patient episodes under exchangeability; calibration unit: patient episode"
    )
    boot = m["meta"]["bootstrap"]
    assert {
        k: boot[k] for k in ("n_resamples", "level", "unit", "headline_interval")
    } == {
        "n_resamples": 100,
        "level": 0.95,
        "unit": "patient_day",
        "headline_interval": "cluster",
    }


# 36
def test_metrics_json_layout_metric_first(hand_run: dict[str, Any]) -> None:
    f1 = hand_run["metrics"]["per_class_prf"]["ours-s1"]["C1"]["f1"]
    assert set(f1) == SCALAR_KEYS
    # by hand (the module docstring of the scripted case): C1 TP 5, FA 3, FN 0: F1 = 2 * 5 / (2 * 5 + 3 + 0)
    assert f1["value"] == pytest.approx(10 / 13)
    assert f1["ci_lo"] <= f1["value"] <= f1["ci_hi"] or f1["ci_lo"] is None


# 37
def test_metrics_json_no_nan_and_sorted(tmp_path: Path) -> None:
    dirs = run_doc(
        tmp_path, hand_document(), factory_for({})
    )  # a detector that never detects: undefined ratios
    text = (dirs[0] / "metrics.json").read_text(encoding="utf-8")
    assert "NaN" not in text and "Infinity" not in text
    m = json.loads(text)
    assert (
        m["per_class_prf"]["ours-s1"]["C1"]["precision"]["value"] is None
    )  # TP_c + FA = 0: undefined, null
    assert text == json.dumps(m, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


# 38
def test_run_is_bit_reproducible(tmp_path: Path) -> None:
    a = run_doc(tmp_path, hand_document(), factory_for(SCRIPT), out="a")[0]
    b = run_doc(tmp_path, hand_document(), factory_for(SCRIPT), out="b")[0]
    assert (a / "metrics.json").read_bytes() == (b / "metrics.json").read_bytes()


# 39 and 40
def test_detector_receives_observed_day_only_and_fit_gets_no_test_patient(
    tmp_path: Path,
) -> None:
    created: list[Scripted] = []
    doc = hand_document()
    doc["split"] = {"train": 0.34, "calibration": 0.33, "test": 0.33}
    d = run_doc(tmp_path, doc, factory_for(SCRIPT, created))[0]
    spy = created[0]
    assert spy.run_days, "the detector was never run"
    for day in spy.run_days:
        assert type(day) is ObservedDay
        assert not isinstance(day, LatentDay) and not hasattr(day, "ground_truth")
    split = read_metrics(d)["analysis"]["run"]["split"]
    test_patients = set(split["test"])
    assert {day.patient_id for day in spy.run_days} == test_patients
    train, calib = spy.fit_args[0]
    seen = {x.observed.patient_id for x in train} | {
        x.observed.patient_id for x in calib
    }
    assert seen == set(split["train"]) | set(split["calibration"])
    assert seen.isdisjoint(test_patients)
    assert {x.observed.patient_id for x in train} == set(split["train"])
    for x in [
        *train,
        *calib,
    ]:  # the fit days show no latent trace and no ground truth at all
        with pytest.raises(TruthAccessError):
            _ = x.ground_truth
        with pytest.raises(TruthAccessError):
            _ = x.latent


# 41
def test_cli_smoke_exit_zero_and_missing_config_nonzero(tmp_path: Path) -> None:
    assert main(["--config", str(SMOKE), "--output", str(tmp_path / "o")]) == 0
    assert (tmp_path / "o" / "smoke" / "0" / "metrics.json").is_file()
    assert (
        main(
            ["--config", str(tmp_path / "nope.yaml"), "--output", str(tmp_path / "o2")]
        )
        != 0
    )


# 47
def test_current_git_rev_appends_dirty_suffix(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake(status_out: str) -> Callable[..., Any]:
        def run(cmd: list[str], **kwargs: Any) -> Any:
            calls.append(list(cmd))
            if "rev-parse" in cmd:
                return SimpleNamespace(returncode=0, stdout="abc123\n")
            return SimpleNamespace(returncode=0, stdout=status_out)

        return run

    monkeypatch.setattr(runner.subprocess, "run", fake(""))
    assert current_git_rev() == "abc123"
    monkeypatch.setattr(
        runner.subprocess, "run", fake(" M src/ralmon/eval/runner.py\n")
    )
    assert current_git_rev() == "abc123-dirty"

    def no_git(cmd: list[str], **kwargs: Any) -> Any:
        raise FileNotFoundError("git")

    monkeypatch.setattr(runner.subprocess, "run", no_git)
    assert current_git_rev() == "unknown"  # a missing git repository is not an error


# ---- the scored numbers of the hand case -----------------------------------------------------------------------------
# Truth (first_decidable reference, tolerance 60_000): C1 events: p01 range 14:00, p01 resp (closing step of the last
# day, ref 2T), p03 sched (ref 08:30), p03 count (ref 2T), p05 range 14:00 = 5; C2: p02 ble_dropout, p04 stuck_at = 2;
# C3: p02 replay, p05 injection_naive = 2. Matched: 5 C1, 2 C2, 0 C3 (7); missed: the two C3; duplicates: 1 (p03);
# false alarms: p05 03:00, p06 d0 12:00, p06 d1 12:00 = 3 (the detection at 2T + 10:00 is in the unscored tail day).


def test_hand_case_per_class_prf(hand_run: dict[str, Any]) -> None:
    prf = hand_run["metrics"]["per_class_prf"]["ours-s1"]
    value = lambda c, k: prf[c][k]["value"]
    assert value("C1", "precision") == pytest.approx(5 / 8)
    assert value("C1", "recall") == pytest.approx(1.0)
    assert value("C1", "f1") == pytest.approx(10 / 13)  # 2 * 5 / (2 * 5 + 3 + 0)
    assert value("C2", "precision") == pytest.approx(2 / 5)
    assert value("C2", "recall") == pytest.approx(1.0)
    assert value("C2", "f1") == pytest.approx(4 / 7)
    assert (
        value("C3", "precision") == 0.0
        and value("C3", "recall") == 0.0
        and value("C3", "f1") == 0.0
    )
    assert value("any", "precision") == pytest.approx(0.7)
    assert value("any", "recall") == pytest.approx(7 / 9)
    assert value("any", "f1") == pytest.approx(14 / 19)  # 2 * 7 / (2 * 7 + 3 + 2)


def test_hand_case_false_alarms_and_curve(hand_run: dict[str, Any]) -> None:
    fa = hand_run["metrics"]["false_alarms_per_patient_day"]["ours-s1"]
    assert fa["value"] == pytest.approx(3 / 12)
    assert fa["n_false_alarms"] == 3
    assert fa["duplicates_per_patient_day"] == pytest.approx(1 / 12)
    curve = hand_run["metrics"]["recall_vs_false_alarm_curve"]["ours-s1"]
    assert len(curve) == 1 and curve[0]["alpha"] == 0.5
    assert curve[0]["false_alarms_per_patient_day"] == pytest.approx(0.25)
    assert curve[0]["recall"] == pytest.approx(7 / 9)


def test_hand_case_delay(hand_run: dict[str, Any]) -> None:
    delay = hand_run["metrics"]["detection_delay_ms"]["ours-s1"]
    assert delay["n_matched"] == 7
    assert delay["values_ms"] == [-30_000.0, 0.0, 0.0, 0.0, 0.0, 0.0, 30_000.0]
    assert delay["mean"]["value"] == 0.0
    assert delay["fraction_early"]["value"] == pytest.approx(1 / 7)
    assert delay["p50"] == 0.0


def test_hand_case_attribution(hand_run: dict[str, Any]) -> None:
    att = hand_run["metrics"]["attribution_confusion"]["ours-s1"]
    # pairs (true -> label): C1->C1 x4 (p01 x2, p03 x2), C1->UNDETERMINED (p05), C2->C3 (p02), C2->C2 (p04)
    assert att["matrix"] == {
        "C1": {"C1": 4, "C2": 0, "C3": 0, "UNDETERMINED": 1},
        "C2": {"C1": 0, "C2": 1, "C3": 1, "UNDETERMINED": 0},
        "C3": {"C1": 0, "C2": 0, "C3": 0, "UNDETERMINED": 0},
    }
    assert att["abstention_rate"]["value"] == pytest.approx(1 / 7)
    assert att["accuracy_answered"]["value"] == pytest.approx(5 / 6)
    # C1: P 1, R 4/5 -> 8/9; C2: P 1, R 1/2 -> 2/3; C3: TP 0, FP 1 -> 0
    assert att["macro_f1"]["value"] == pytest.approx((8 / 9 + 2 / 3 + 0.0) / 3)
    acc = hand_run["metrics"]["accuracy_vs_coverage"]["ours-s1"]
    assert acc == [{"coverage": pytest.approx(6 / 7), "accuracy": pytest.approx(5 / 6)}]


def test_hand_case_not_applicable_metrics_are_null(hand_run: dict[str, Any]) -> None:
    m = hand_run["metrics"]
    for name in (
        "empirical_coverage",
        "mean_interval_width",
        "expected_calibration_error",
        "latency_percentiles",
    ):
        assert m[name]["ours-s1"] is None
    assert m["severity_rank_agreement"]["ours-s1"] is None


def test_hand_case_tail_day_is_not_scored_and_is_reported(
    hand_run: dict[str, Any],
) -> None:
    info = hand_run["metrics"]["analysis"]["run"]["detections"]["ours-s1"]
    assert info["n_dropped_in_unscored_tail"] == 1
    assert info["n_scored"] == 11  # 12 emitted, one in the tail day
    closing = hand_run["metrics"]["analysis"]["run"]["closing_step"]
    assert closing["n_events"] == 1 and closing["classes"] == ["C1"]
    assert hand_run["metrics"]["analysis"]["run"]["twins"]["policy"] == "exclude"


def test_twins_are_not_run_in_the_headline_population(hand_run: dict[str, Any]) -> None:
    run_days = {(d.patient_id, d.day_index) for d in hand_run["detectors"][0].run_days}
    assert {p for p, _ in run_days} == {"p01", "p02", "p03", "p04", "p05", "p06"}
    assert {i for _, i in run_days} == {0, 1}  # the tail day (index 2) is never run


def test_after_close_clip_drops_what_follows_the_closing_step(tmp_path: Path) -> None:
    script = {
        ("p06", 0): [det(T + ms(1), C1)]
    }  # emitted by the run of day 0, after its closing step
    kept = read_metrics(
        run_doc(tmp_path, hand_document(), factory_for(script), out="k")[0]
    )
    assert kept["false_alarms_per_patient_day"]["ours-s1"]["n_false_alarms"] == 1
    doc = hand_document()
    doc["run_options"]["after_close"] = "clip"
    clipped = read_metrics(run_doc(tmp_path, doc, factory_for(script), out="c")[0])
    assert clipped["false_alarms_per_patient_day"]["ours-s1"]["n_false_alarms"] == 0
    assert (
        clipped["analysis"]["run"]["detections"]["ours-s1"]["n_clipped_after_close"]
        == 1
    )


def test_baseline_time_shift_is_an_explicit_switch(tmp_path: Path) -> None:
    doc = hand_document(detector="B3")
    # B3 as a scripted stand-in: a baseline detection is emitted `reorder_delay_ms` after the decision (F20)
    doc["monitor"]["reorder_delay_ms"] = 60_000
    script = {
        ("p01", 0): [det(ms(14) + 100_000, None)]
    }  # 40 s past the 60 s tolerance, 100 s after the onset
    plain = read_metrics(run_doc(tmp_path, doc, factory_for(script), out="p")[0])
    assert plain["per_class_prf"]["B3"]["any"]["recall"]["value"] == 0.0
    doc["run_options"]["baseline_time"] = "subtract_reorder_delay"
    shifted = read_metrics(run_doc(tmp_path, doc, factory_for(script), out="s")[0])
    assert shifted["per_class_prf"]["B3"]["any"]["recall"]["value"] == pytest.approx(
        1 / 9
    )  # 40 s <= 60 s
    assert shifted["meta"]["latency_convention"] == "baseline_minus_reorder_delay"
    assert plain["meta"]["latency_convention"] == "as_emitted"


def test_twins_separate_policy_reports_them_apart(tmp_path: Path) -> None:
    created: list[Scripted] = []
    doc = hand_document()
    doc["run_options"]["twins"] = "separate"
    script = {**SCRIPT, ("p07", 0): [det(ms(20), C1)], ("p08", 0): [det(ms(20), C2)]}
    d = run_doc(tmp_path, doc, factory_for(script, created))[0]
    m = read_metrics(d)
    assert (
        m["meta"]["n_test_patients"] == 6
    )  # the headline counts stay the virtual patients'
    assert m["per_class_prf"]["ours-s1"]["any"]["recall"]["value"] == pytest.approx(
        7 / 9
    )
    twins = m["analysis"]["run"]["twins"]
    assert twins["policy"] == "separate" and twins["n_units"] == 2
    assert twins["detectors"]["ours-s1"]["per_class_prf"]["any"][
        "recall"
    ] == pytest.approx(1.0)


# ---- hooks (48, 49) --------------------------------------------------------------------------------------------------


@pytest.fixture
def hook_module(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[Callable[[Any], Any]], None]:
    def install(hook: Callable[[Any], Any]) -> None:
        module = types.ModuleType("ralmon.eval.analysis")
        module.hooks_for = lambda experiment_id: [hook]  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "ralmon.eval.analysis", module)

    return install


# 48
def test_hook_metric_contributions_merged_under_contract_names(
    tmp_path: Path, hook_module: Callable[[Callable[[Any], Any]], None]
) -> None:
    entry = [{"alpha": 0.5, "nominal": 0.5, "alert_level": 0.9, "band_level": 0.8}]
    hook_module(
        lambda ctx: HookResult(
            analysis={"k": 1},
            metrics={"empirical_coverage": {"ours": {"shift_x": entry}}},
        )
    )
    dirs = run_experiment(*load_experiment(SMOKE), tmp_path / "o", git_rev=lambda: "r")
    m = read_metrics(dirs[0])
    assert m["analysis"]["k"] == 1
    cov = m["empirical_coverage"]["ours"]
    assert cov["shift_x"] == entry
    assert isinstance(cov["in_distribution"], list) and len(cov["in_distribution"]) == 1
    assert set(cov["in_distribution"][0]) == {
        "alpha",
        "nominal",
        "alert_level",
        "band_level",
    }


# 49
def test_hook_metric_with_non_contract_name_rejected(
    tmp_path: Path, hook_module: Callable[[Callable[[Any], Any]], None]
) -> None:
    hook_module(
        lambda ctx: HookResult(analysis={}, metrics={"my_new_metric": {"ours": 1}})
    )
    with pytest.raises(ConfigError):
        run_doc(tmp_path, hand_document(), factory_for(SCRIPT))


def test_a_module_that_does_not_exist_is_skipped(tmp_path: Path) -> None:
    # none of ralmon.eval.analysis, ablations, embodied, shift, realdata exists in this task: the run goes through
    assert run_doc(tmp_path, hand_document(), factory_for(SCRIPT))


# ---- the guards ------------------------------------------------------------------------------------------------------


def facts(**kw: Any) -> RunFacts:
    base: dict[str, Any] = {
        "detectors": ("B1", "B3", "ours"),
        "benchmark_fixture_only": False,
        "registry_fixture_only": False,
        "step_ms": 60_000,
        "reorder_delay_ms": 120_000,
        "patients_without_tail_day": (),
        "b1_rules_active": ("R1", "R2", "R3", "R4"),
        "int_gate": {},
        "history": "none",
        "twins": "exclude",
        "n_seeds": 5,
        "has_device_profile": True,
        "timing_tail_ms": 90_000_000,
        "required_tail_ms": 90_000_000,
        "min_alpha": 0.05,
        "calibration_episodes": {"ours": 400},
    }
    base.update(kw)
    return RunFacts(**base)


def options(**kw: Any) -> RunOptions:
    cfg: dict[str, Any] = {
        "alpha_grid": (0.05,),
        "n_bootstrap": 10,
        "ci_level": 0.95,
        "ece_bins": 5,
        "headline": True,
    }
    cfg.update(kw)
    return RunOptions(**cfg)


def ids(entries: Sequence[Any]) -> set[str]:
    return {e.id for e in entries}


def test_guards_a_clean_headline_configuration_has_no_hard_failure() -> None:
    report = evaluate_guards(facts(detectors=("B1", "B2", "B4", "ours")), options())
    assert report.hard == ()
    # the standing flags: B1 is minimal, the closing-step truth is C1 only, the latency convention is open
    assert {"B1_MINIMAL", "CLOSING_STEP_C1_ONLY", "LATENCY_CONVENTION_OPEN"} <= ids(
        report.flags
    )


def test_guard_b1_vacuous_is_a_hard_failure_even_for_a_smoke_run() -> None:
    with pytest.raises(GuardError, match="B1_VACUOUS"):
        evaluate_guards(
            facts(b1_rules_active=("R3",)), options(headline=False)
        ).raise_if_failed()


@pytest.mark.parametrize(
    ("kw", "guard"),
    [
        ({"benchmark_fixture_only": True}, "FIXTURE_ONLY"),
        ({"registry_fixture_only": True}, "FIXTURE_ONLY"),
        ({"reorder_delay_ms": 90_000}, "REORDER_DELAY_NOT_A_MULTIPLE_OF_STEP"),
        ({"patients_without_tail_day": ("p01",)}, "TAIL_DAY_MISSING"),
        ({"int_gate": {"B3": 4}}, "INT_GATE"),
        ({"detectors": ("B3", "ours")}, "ADR063_INT_SYS_COMPARISON"),
        ({"detectors": ("B5", "ours")}, "ADR063_INT_SYS_COMPARISON"),
        ({"history": "ours"}, "HISTORY_ASYMMETRY"),
        ({"twins": "include"}, "TWINS_IN_HEADLINE"),
    ],
)
def test_headline_guards_are_hard_failures_in_a_headline_run_and_flags_otherwise(
    kw: dict[str, Any], guard: str
) -> None:
    hard = evaluate_guards(facts(**kw), options(headline=True))
    assert guard in ids(hard.hard)
    with pytest.raises(GuardError, match=guard):
        hard.raise_if_failed()
    soft = evaluate_guards(facts(**kw), options(headline=False))
    assert soft.hard == () and guard in ids(soft.flags)


@pytest.fixture
def accepted_adrs(monkeypatch: pytest.MonkeyPatch) -> None:
    """The decisions file as if ADR-063 and ADR-061 were accepted (they are still proposed in the repository)."""
    monkeypatch.setattr(
        runner,
        "adr_statuses",
        lambda path=None: {
            "ADR-063": "accepted (test)",
            "ADR-061": "accepted (test)",
            "ADR-066": "accepted (gab)",
            "ADR-062": "proposed [DA-CONFERMARE]",
        },
    )


def test_guards_a_decision_that_gab_accepted_lifts_its_guard(
    accepted_adrs: None,
) -> None:
    report = evaluate_guards(
        facts(detectors=("B3", "ours"), history="ours"),
        options(accepted_decisions=("ADR-063", "ADR-061")),
    )
    assert report.hard == ()


def test_guard_b5_stays_flagged_as_not_the_paper_comparison(
    accepted_adrs: None,
) -> None:
    flagged = evaluate_guards(
        facts(detectors=("B5", "ours")), options(accepted_decisions=("ADR-063",))
    )
    assert "B5_NOT_PAPER_COMPARISON" in ids(flagged.flags)


def test_the_smoke_run_checks_b1_and_records_the_guards(tmp_path: Path) -> None:
    config, opts = load_experiment(SMOKE)
    d = run_experiment(config, opts, tmp_path / "o", git_rev=lambda: "r")[0]
    guards = read_metrics(d)["meta"]["guards"]
    assert guards["headline"] is False
    assert guards["facts"]["b1_rules_active"] == ["R1", "R2", "R3", "R4"]
    assert guards["facts"]["benchmark_fixture_only"] is True
    assert "FIXTURE_ONLY" in {f["id"] for f in guards["flags"]}


def test_headline_run_on_a_fixture_only_benchmark_is_refused(tmp_path: Path) -> None:
    doc = hand_document(seeds=[0, 1, 2, 3, 4])
    doc["run_options"]["headline"] = True
    with pytest.raises(GuardError, match="FIXTURE_ONLY"):
        run_doc(tmp_path, doc, factory_for(SCRIPT))
    assert not (tmp_path / "out").exists() or not list(
        (tmp_path / "out").rglob("metrics.json")
    )


def test_a_changed_copy_of_the_config_does_not_change_the_loaded_one() -> None:
    config, options_ = load_experiment(SMOKE)
    snapshot = copy.deepcopy((config, options_))
    runner.dump_experiment(config, options_)
    assert (config, options_) == snapshot


# ---- the real pipeline on the mini benchmark -------------------------------------------------------------------------
# Seed 0 splits the six virtual patients as calibration p01, p04 and test p03, p06 (the first run of the split helper,
# pinned here; the test of the split itself is above). With the total level 0.9 and one test per day the per-test level is
# 0.9. By hand (the fixture days of tests/fixtures/eval/build_mini_benchmark.py):
# * the response template (RESP) of the dose at 08:05 is the one instance with a predictive path, persistence forecast of
#   the pressure: the forecast shows no fall, so sigma_hat = -1 (clipped) on every day;
# * p01 responds (125 to 115, sigma_true = 0.0), p04 does not (125 to 124, sigma_true = -0.45): the four calibration scores
#   R = sigma_true - sigma_hat are 1.0, 1.0, 0.55, 0.55; n = 4;
# * level 0.9: k = ceil(5 * 0.1) = 1, q = 0.55, so sigma_hat + q = -0.45 < 0 and every test episode is warned;
#   rho = m / (n + 1) with m = #{R_i < 1} = 2, so rho = 0.4 for all four predictions (p03 two days, p06 two days);
# * outcomes: p03 does not respond (violated, True), p06 responds (satisfied, False);
# * ECE with 5 bins: all four in the bin [0.4, 0.6): mean rho 0.4, observed rate 0.5, |0.4 - 0.5| = 0.1;
# * alert level 1 - P(emitted and sigma_true >= 0) = 1 - 2/4 = 0.5 (p06 has sigma_true = 0.0 >= 0), nominal 1 - 0.9 = 0.1;
#   band level P(sigma_true <= -1 + 0.55) = P(sigma_true <= -0.45) = 2/4 (p03 only).


def real_document(**options: Any) -> dict[str, Any]:
    doc = smoke_document()
    doc["detectors"] = ["ours"]
    doc["alpha"] = 0.9
    doc["monitor"]["alpha"] = 0.9
    doc["run_options"]["alpha_grid"] = [0.9]
    doc["run_options"]["n_bootstrap"] = 40
    doc["run_options"].update(options)
    return doc


@pytest.fixture(scope="module")
def real_run(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    tmp = tmp_path_factory.mktemp("real")
    d = run_doc(tmp, real_document(), None)[0]
    return read_metrics(d)


def test_real_pipeline_split_and_predictions(real_run: dict[str, Any]) -> None:
    run = real_run["analysis"]["run"]
    assert run["split"]["calibration"] == ["p01", "p04"] and run["split"]["test"] == [
        "p03",
        "p06",
    ]
    ours = run["ours"]["ours"]
    assert ours["predictive"] is True and ours["alpha_total"] == 0.9
    assert ours["n_calibration_episodes"] == 4 and ours["n_censored_calibration"] == 0
    assert ours["n_test_episodes"] == 4 and ours["n_tests_per_day"] == {"1": 4}


def test_real_pipeline_ece_and_reliability(real_run: dict[str, Any]) -> None:
    ece = real_run["expected_calibration_error"]["ours"]
    assert ece["value"] == pytest.approx(0.1)
    assert ece["n_predictions"] == 4 and ece["n_unresolved"] == 0 and ece["bins"] == 5
    bins = ece["reliability_bins"]
    assert [b["n"] for b in bins] == [0, 0, 4, 0, 0]
    assert bins[2]["mean_rho"] == pytest.approx(0.4) and bins[2][
        "observed_rate"
    ] == pytest.approx(0.5)
    assert bins[0]["mean_rho"] is None  # an empty bin is undefined, not zero
    assert set(ece) >= SCALAR_KEYS


def test_real_pipeline_coverage_in_distribution(real_run: dict[str, Any]) -> None:
    (entry,) = real_run["empirical_coverage"]["ours"]["in_distribution"]
    assert entry["alpha"] == 0.9
    assert entry["nominal"] == pytest.approx(0.1)
    assert entry["alert_level"] == pytest.approx(0.5)
    assert entry["band_level"] == pytest.approx(0.5)
    (width,) = real_run["mean_interval_width"]["ours"]["in_distribution"]
    assert (
        width["alpha"] == 0.9 and width["value"] is None
    )  # the two-sided band needs a level of at most 1/2


def test_real_pipeline_latency_and_detection(real_run: dict[str, Any]) -> None:
    # a decision on the grid with a reorder delay of 0 is emitted at the instant it is decidable: latency 0
    assert real_run["latency_percentiles"]["ours"] == {
        "p50": 0.0,
        "p95": 0.0,
        "p99": 0.0,
    }
    # the fixture truth holds 2 events of the two test patients (p03: a missed measurement that the observed day does not
    # show, a day-end count that it does): one is matched, by an alert whose cause the rule leaves undetermined
    assert real_run["per_class_prf"]["ours"]["C1"]["recall"]["value"] == pytest.approx(
        0.5
    )
    assert (
        real_run["analysis"]["run"]["recall_by_subtype"]["ours"]["C1/dose_omission"][
            "recall"
        ]
        == 1.0
    )


def test_real_pipeline_run_is_deterministic(tmp_path: Path) -> None:
    a = run_doc(tmp_path, real_document(), None, out="a")[0]
    b = run_doc(tmp_path, real_document(), None, out="b")[0]
    assert (a / "metrics.json").read_bytes() == (b / "metrics.json").read_bytes()


def test_the_registry_that_cannot_feed_the_attribution_is_refused_before_the_run(
    tmp_path: Path,
) -> None:
    doc = real_document()
    doc["run_options"]["registry"] = (
        None  # configs/registry/hypertension.yaml: lacks the evidence thresholds (OPF-6)
    )
    doc["run_options"]["allow_fixture_only"] = False
    real_version = yaml.safe_load(
        Path("configs/registry/hypertension.yaml").read_text(encoding="utf-8")
    )["registry_version"]
    doc["monitor"]["registry_version"] = str(real_version)
    with pytest.raises(ConfigError, match="attribution layer"):
        run_doc(tmp_path, doc, None)


def test_history_ours_changes_only_the_proposed_method_and_is_reported(
    tmp_path: Path,
) -> None:
    doc = real_document(history="ours")
    d = run_doc(tmp_path, doc, None)[0]
    m = read_metrics(d)
    assert m["analysis"]["run"]["policies"]["history"] == "ours"
    assert m["meta"]["guards"]["facts"]["history"] == "ours"


def test_calibration_days_without_injected_events(tmp_path: Path) -> None:
    doc = real_document(calibration_days="without_injected")
    m = read_metrics(run_doc(tmp_path, doc, None)[0])
    cal = m["analysis"]["run"]["calibration"]
    # seed 0 calibrates on p01 and p04; p04 day 1 holds the injected C2 event stuck_at: three days are left
    assert (
        cal["n_calibration_days"] == 4
        and cal["n_with_injected_event"] == 1
        and cal["n_used"] == 3
    )


def test_twins_include_adds_them_to_the_test_population(tmp_path: Path) -> None:
    doc = hand_document()
    doc["run_options"]["twins"] = "include"
    m = read_metrics(run_doc(tmp_path, doc, factory_for(SCRIPT))[0])
    assert m["meta"]["n_test_patients"] == 8 and m["meta"]["n_test_patient_days"] == 14
    assert "TWINS_IN_HEADLINE" in {f["id"] for f in m["meta"]["guards"]["flags"]}


def test_required_analysis_keys_are_checked(tmp_path: Path) -> None:
    doc = hand_document()
    doc["run_options"]["required_analysis"] = ["run.split", "b5_failure_found"]
    with pytest.raises(ConfigError, match="b5_failure_found"):
        run_doc(tmp_path, doc, factory_for(SCRIPT))
    doc["run_options"]["required_analysis"] = ["run.split", "run.closing_step.n_events"]
    assert run_doc(tmp_path, doc, factory_for(SCRIPT), out="ok")


def test_b1_vacuity_is_a_hard_failure_of_a_real_run(tmp_path: Path) -> None:
    """A plan without the RANGE, HOLD and COUNT parameter records makes B1 silent: the run is refused (F9)."""
    import shutil

    bench = tmp_path / "bench"
    shutil.copytree(MINI, bench)
    for plan_file in (bench / "plans").glob("*.json"):
        plan = json.loads(plan_file.read_text(encoding="utf-8"))
        plan["instances"] = [i for i in plan["instances"] if i["anchor_ms"] is not None]
        plan_file.write_text(json.dumps(plan), encoding="utf-8")
    doc = smoke_document()
    doc["benchmark_manifest"] = str(bench)
    doc["detectors"] = ["B1"]
    with pytest.raises(GuardError, match="B1_VACUOUS"):
        run_doc(tmp_path, doc, None)
    assert (
        not list((tmp_path / "out").rglob("metrics.json"))
        if (tmp_path / "out").exists()
        else True
    )


def test_device_profile_is_built_from_the_configuration() -> None:
    config, opts = load_experiment(SMOKE)
    params = {
        **opts.detector_params,
        "ours": {"device_profile": {"cuff": {"authenticates": True, "seq": True}}},
    }
    env = runner.make_environment(config, replace(opts, detector_params=params), 0)
    assert env.profile is not None
    assert env.profile.caps("cuff").authenticates is True  # type: ignore[attr-defined]
    assert env.profile.caps("robot").authenticates is False  # type: ignore[attr-defined]
    assert runner.make_environment(config, opts, 0).profile is None


def test_false_alarms_are_split_by_the_kind_of_detection(tmp_path: Path) -> None:
    """A predictive false alarm is visible apart from a measured one (the early warnings enter the false alarms when they
    lie outside the tolerance window of the event, E3)."""
    from tests.eval.helpers import alert

    script = {
        ("p06", 0): [
            alert(ms(5), UND, key="a", verdict=VerdictState.PREDICTED_VIOLATION),
            alert(ms(6), C1, key="b"),
            det(ms(7), None),
        ]
    }
    m = read_metrics(run_doc(tmp_path, hand_document(), factory_for(script))[0])
    kinds = m["analysis"]["run"]["false_alarms_by_kind"]["ours-s1"]
    assert kinds == {
        "predicted_violation": 1,
        "violated": 1,
        "unattributed_detection": 1,
    }
    assert m["false_alarms_per_patient_day"]["ours-s1"]["n_false_alarms"] == 3


@pytest.mark.parametrize(
    "name",
    ["ours", "ours-A1", "ours-A3-prio", "ours-A4-avail-0.5", "ours-A4-witness-only"],
)
def test_detector_names_of_the_ablation_variants_are_valid(name: str) -> None:
    assert runner.is_valid_detector_name(name)


@pytest.mark.parametrize(
    "name", ["", "ours-", "ours--A1", "oursA1", "B6", "b1", "ours A1", "../ours"]
)
def test_other_detector_names_are_not(name: str) -> None:
    assert not runner.is_valid_detector_name(name)


def test_a_registry_with_an_unset_priority_is_refused_before_the_run(
    tmp_path: Path,
) -> None:
    """The fixture registry with ``priority_sys`` turned into an unset row: a SYS alert would stop the run later."""
    text = REGISTRY_TEXT()
    start = text.index("  - name: priority_sys")
    end = text.index("  - name:", start + 1)
    unset_row = '  - {parameter: priority_sys, unit: "1", required_by: [sys], note: "unset for this test"}\n'
    changed = text[:start] + text[end:]
    changed = changed.replace("unset: []", "unset:\n" + unset_row)
    registry = tmp_path / "registry.yaml"
    registry.write_text(changed, encoding="utf-8")
    doc = real_document(registry=str(registry))
    with pytest.raises(ConfigError, match="priority_sys"):
        run_doc(tmp_path, doc, None)


def REGISTRY_TEXT() -> str:
    from tests.eval.helpers import REGISTRY

    return REGISTRY.read_text(encoding="utf-8")
