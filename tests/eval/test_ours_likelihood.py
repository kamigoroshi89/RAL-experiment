"""WS08-T10: ``OursDetector`` with the likelihood attributor (ADR-074): alert_inputs, calibrated sets, ours-hier, A4, device profile.

ILLUSTRATIVE, UNVERIFIED, FIXTURE-ONLY. The registry is the fixture registry of ``tests/fixtures/eval``, the days are hand-built or are
the mini benchmark of the same directory, and every sensitivity value is ``TEST_VALUES`` of ``tests/attribution/test_likelihood_rule.py``:
one point of the sensitivity grid for each awaiting row, labelled "sensitivity, not a proposal", none a clinical or device value. No
expected number here is a result; the sets of the calibrated-selector tests are computed from the posterior of the same alert.
"""

from __future__ import annotations

import ast
import dataclasses
import json
import math
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import ralmon.eval.ours as ours_module
from ralmon.attribution import AwaitingValueError
from ralmon.benchmark import BenchmarkDay, ObservedDay, open_benchmark
from ralmon.benchmark.device_profile import GeneratorDeviceProfile
from ralmon.conformal.sets import (
    PatientLeakError,
    StaleSetCalibratorError,
    SubtypeCalibrationAlert,
    SubtypeSetCalibrator,
    cumulative_level_set,
)
from ralmon.eval import build_detector
from ralmon.eval.ours import LikelihoodSpec, OursDetector, PipelineComponents
from ralmon.eval.runner import (
    ConfigError,
    _ObservedOnlyDay,
    load_experiment,
    make_environment,
    run_experiment,
    split_patients,
)
from ralmon.monitor import VerdictState
from ralmon.signals import Sample
from ralmon.spec import load_registry, load_templates
from tests.attribution.test_likelihood_rule import A4_REMOVED, TEST_VALUES
from tests.eval.helpers import FIXTURES, MINI, REGISTRY, ms
from tests.eval.test_ours import (
    STEP,
    config,
    device_profile,
    make_ours,
    out_of_band_day,
    range_plan,
)

ROOT = Path(__file__).resolve().parents[2]
TABLE = ROOT / "configs" / "attribution_likelihood.yaml"
LIKELIHOOD = FIXTURES / "likelihood.yaml"
SMOKE_LIKELIHOOD = ROOT / "experiments" / "smoke-likelihood.yaml"
SENSITIVITY = "sensitivity, not a proposal"

NEW_KEYS = (
    "attribution_log_score",
    "attribution_brier",
    "attribution_sets",
    "attribution_equal_coverage",
    "pair_llr",
    "pair_direction_mcnemar",
)


@pytest.fixture(scope="module")
def registry() -> Any:
    return load_registry(REGISTRY, step_ms=STEP, allow_fixture_only=True)


@pytest.fixture(scope="module")
def templates(registry: Any) -> Any:
    return load_templates(registry=registry)


def spec(**kw: Any) -> LikelihoodSpec:
    """The likelihood wiring of the tests: TEST sensitivity values, the profile of the worked day (with diagnostics)."""
    base: dict[str, Any] = {
        "table_path": TABLE,
        "sensitivity_values": dict(TEST_VALUES),
        "diagnostics_profile": "driver_with_diagnostics",
        "set_alpha": 0.5,
    }
    base.update(kw)
    return LikelihoodSpec(**base)


def make_lik(registry: Any, templates: Any, **kw: Any) -> OursDetector:
    likelihood = kw.pop("likelihood", None) or spec()
    return make_ours(registry, templates, likelihood=likelihood, **kw)


def violated_alerts(alerts: Any) -> list[Any]:
    return [a for a in alerts if a.verdict is VerdictState.VIOLATED]


def calibration_alerts(
    posterior: dict[str, float],
    true_subtype: str,
    *,
    n: int = 4,
    prefix: str = "c",
    template: str = "range",
) -> list[SubtypeCalibrationAlert]:
    return [
        SubtypeCalibrationAlert(f"{prefix}{i}", template, posterior, true_subtype)
        for i in range(n)
    ]


def top_of(posterior: dict[str, float]) -> str:
    return max(sorted(posterior), key=lambda k: posterior[k])


# ---- the mini benchmark, fitted --------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def mini() -> SimpleNamespace:
    cfg, options = load_experiment(LIKELIHOOD)
    reader = open_benchmark(cfg.benchmark_manifest, view="observed")
    env = make_environment(cfg, options, 0, manifest=reader.manifest)
    ids = list(reader.patient_ids(role="patient"))
    split = split_patients(ids, cfg.split, 0)

    def days(part: str) -> list[BenchmarkDay]:
        return [
            _ObservedOnlyDay(reader.observed(p, d))
            for p, s in sorted(split.items())
            if s == part
            for d in reader.days(p)
        ]

    detectors: dict[str, Any] = {}
    for name in ("ours", "ours-hier"):
        detector = build_detector(name, env, alpha=0.5)
        detector.fit(days("train"), days("calibration"))
        detectors[name] = detector
    everyone = [*ids, *reader.patient_ids(role="confounder_pair")]
    return SimpleNamespace(
        config=cfg,
        options=options,
        reader=reader,
        env=env,
        detectors=detectors,
        patients=everyone,
    )


def run_all(mini: SimpleNamespace, name: str) -> list[Any]:
    detector = mini.detectors[name]
    out: list[Any] = []
    for patient in mini.patients:
        for d in mini.reader.days(patient):
            day = mini.reader.observed(patient, d)
            out.extend(detector.run(day, mini.env.plan_for_day(day), None))
    return out


# 1
def test_ours_emits_p_kappa_and_cause_set(registry: Any, templates: Any) -> None:
    ours = make_lik(registry, templates)
    ours.fit([], [])
    day = out_of_band_day()
    alerts = ours.run(day, range_plan(registry), None)
    violated = violated_alerts(alerts)
    assert len(violated) == 1
    alert = violated[0]
    assert alert.p_kappa is not None
    assert math.isclose(sum(alert.p_kappa.values()), 1.0, abs_tol=1e-9)
    posterior = ours.alert_inputs(day.patient_id, alert).posteriors["lik"]
    assert alert.cause_set and set(alert.cause_set) <= set(posterior)
    hier = make_ours(registry, templates)  # no likelihood block: ours-hier
    hier.fit([], [])
    (plain,) = violated_alerts(hier.run(day, range_plan(registry), None))
    assert plain.p_kappa is None and plain.cause_set is None
    assert hier.likelihood_rule is None and hier.alert_inputs is None


def test_ours_emits_p_kappa_and_cause_set_on_the_mini_benchmark(
    mini: SimpleNamespace,
) -> None:
    lik = violated_alerts(run_all(mini, "ours"))
    assert lik, "the mini benchmark has VIOLATED alerts"
    for alert in lik:
        assert alert.p_kappa is not None
        assert math.isclose(sum(alert.p_kappa.values()), 1.0, abs_tol=1e-9)
        assert alert.cause_set
    hier = violated_alerts(run_all(mini, "ours-hier"))
    assert len(hier) == len(lik)  # the same violations, another rule
    assert all(a.p_kappa is None and a.cause_set is None for a in hier)
    assert mini.detectors["ours-hier"].likelihood_rule is None
    assert mini.detectors["ours"].likelihood_rule is not None


# 2
def test_awaiting_value_fails_loudly_without_sensitivity_values(
    registry: Any, templates: Any, mini: SimpleNamespace
) -> None:
    for name in TEST_VALUES:
        partial = {k: v for k, v in TEST_VALUES.items() if k != name}
        with pytest.raises(AwaitingValueError) as excinfo:
            make_lik(registry, templates, likelihood=spec(sensitivity_values=partial))
        assert name in excinfo.value.names
    with pytest.raises(AwaitingValueError):
        make_lik(registry, templates, likelihood=spec(sensitivity_values={}))
    # through the runner: a ConfigError that names the missing values; no key at all is refused too
    ours_params = dict(mini.env.params["ours"])
    likelihood = dict(ours_params["likelihood"])
    for values, needle in (
        ({k: v for k, v in TEST_VALUES.items() if k != "eps"}, "eps"),
        (None, "sensitivity_values"),
    ):
        broken = {k: v for k, v in likelihood.items() if k != "sensitivity_values"}
        if values is not None:
            broken["sensitivity_values"] = values
        env = dataclasses.replace(
            mini.env,
            params={**mini.env.params, "ours": {**ours_params, "likelihood": broken}},
        )
        with pytest.raises(ConfigError, match=needle):
            build_detector("ours", env, alpha=0.5)
    # the rows of the file stay awaiting: the rule counts them and the run only substitutes labelled sensitivity values
    rule = mini.detectors["ours"].likelihood_rule
    assert rule.metadata["awaiting_cells"] > 0


# 3
def test_sensitivity_values_are_recorded_in_the_metadata(
    registry: Any, templates: Any, e2e: SimpleNamespace
) -> None:
    ours = make_lik(registry, templates)
    recorded = ours.likelihood_rule.metadata["sensitivity_values"]
    assert recorded["eps"] == {"value": 0.01, "label": SENSITIVITY}
    assert recorded["class_priors"]["value"] == "uniform"
    # the selector's own declared level (it is not in the posterior model) is recorded with the same label
    selector = ours.set_selector_metadata()
    assert selector["fallback_level"] == {"value": 0.9, "label": SENSITIVITY}
    assert selector["set_alpha"] == "0.5"
    # the run writes them next to the metrics, for the likelihood detector only
    rules = e2e.metrics["meta"]["attribution"]["rules"]
    assert set(rules) == {"ours"}
    assert rules["ours"]["sensitivity_values"]["eps"]["label"] == SENSITIVITY
    sets = e2e.metrics["meta"]["attribution"]["set_selector"]
    assert set(sets) == {"ours"}
    assert sets["ours"]["fallback_level"]["label"] == SENSITIVITY
    json.dumps(sets)  # inf thresholds are written as null with a flag, alpha as a string


# 4
def test_set_selector_uses_the_fitted_calibrator_and_refuses_a_stale_model_version(
    registry: Any, templates: Any
) -> None:
    ours = make_lik(registry, templates)
    ours.fit([], [])
    day, plan = out_of_band_day(), range_plan(registry)
    (before,) = violated_alerts(ours.run(day, plan, None))
    posterior = dict(ours.alert_inputs(day.patient_id, before).posteriors["lik"])
    # before a calibrator is fitted the set is the cumulative-level set with the declared level
    assert before.cause_set == cumulative_level_set(posterior, 0.9)
    token = ours.likelihood_rule.model_version
    top = top_of(posterior)
    calibrator = ours.fit_set_calibrator(
        calibration_alerts(posterior, top), test_patient_ids=[day.patient_id]
    )
    assert calibrator.calibrated_for == token and calibrator.population == "main"
    assert ours.set_calibrator("main") is calibrator
    (after,) = violated_alerts(ours.run(day, plan, None))
    expected = calibrator.predict_set(
        posterior, "range", 0.5, patient_id=day.patient_id, model_version=token
    )
    assert after.cause_set == expected.subtypes
    assert after.cause_set != before.cause_set
    assert len(after.cause_set) < len(before.cause_set)
    # a calibrator fitted for another model version is refused, and the installed one stays
    stale = SubtypeSetCalibrator("marginal", population="main")
    stale.fit(calibration_alerts(posterior, top), model_version="another-token")
    with pytest.raises(StaleSetCalibratorError):
        ours.install_set_calibrator(stale)
    unversioned = SubtypeSetCalibrator("marginal", population="main")
    unversioned.fit(calibration_alerts(posterior, top))
    with pytest.raises(StaleSetCalibratorError):
        ours.install_set_calibrator(unversioned)
    assert ours.set_calibrator("main") is calibrator
    # a calibration patient among the test patients is refused (the split is by patient)
    with pytest.raises(PatientLeakError):
        ours.fit_set_calibrator(
            calibration_alerts(posterior, top), test_patient_ids=["c0"]
        )
    # the run on a calibration patient is refused by the set builder itself
    leaked = make_lik(registry, templates)
    leaked.fit([], [])
    leaked.fit_set_calibrator(
        calibration_alerts(posterior, top, prefix="px"), test_patient_ids=["zz"]
    )
    with pytest.raises(PatientLeakError):
        leaked.run(day, plan, None)
    # the metadata counts the sets issued and copies the guarantee as it is
    meta = ours.set_selector_metadata()
    main = meta["populations"]["main"]
    assert main["model_version"] == token and main["n_calibration"] == 4
    assert main["guarantee"] == expected.guarantee
    assert tuple(main["assumptions"]) == expected.assumptions
    assert meta["sets_issued"]["main"]["range"]["n"] >= 1
    json.dumps(meta)
    # fit() starts again: no calibrator survives a new fit
    ours.fit([], [])
    assert ours.set_calibrator("main") is None


# 5
def test_pairs_use_a_separate_calibrator(registry: Any, templates: Any) -> None:
    ours = make_lik(registry, templates)
    ours.fit([], [])
    day, plan = out_of_band_day(), range_plan(registry)
    (alert,) = violated_alerts(ours.run(day, plan, None))
    posterior = dict(ours.alert_inputs(day.patient_id, alert).posteriors["lik"])
    token = ours.likelihood_rule.model_version
    main = ours.fit_set_calibrator(
        calibration_alerts(posterior, top_of(posterior)),
        test_patient_ids=[day.patient_id],
    )
    # the pair population has other prevalences: here its calibration alerts sit on an improbable subtype
    pairs = ours.fit_set_calibrator(
        calibration_alerts(posterior, "replay", prefix="q"),
        test_patient_ids=[day.patient_id],
        population="pairs",
    )
    assert pairs is not main and pairs.population == "pairs" and main.population == "main"
    (as_main,) = violated_alerts(ours.run(day, plan, None))
    with ours.using_population("pairs"):
        (as_pair,) = violated_alerts(ours.run(day, plan, None))
    assert as_main.cause_set == main.predict_set(
        posterior, "range", 0.5, patient_id=day.patient_id, model_version=token
    ).subtypes
    assert as_pair.cause_set == pairs.predict_set(
        posterior, "range", 0.5, patient_id=day.patient_id, model_version=token
    ).subtypes
    assert set(as_main.cause_set) < set(as_pair.cause_set)
    # outside the context the main calibrator is back
    (again,) = violated_alerts(ours.run(day, plan, None))
    assert again.cause_set == as_main.cause_set
    # without a calibrator of its own the pairs never borrow the main one: the cumulative-level set, flagged
    alone = make_lik(registry, templates)
    alone.fit([], [])
    alone.fit_set_calibrator(
        calibration_alerts(posterior, top_of(posterior)),
        test_patient_ids=[day.patient_id],
    )
    with alone.using_population("pairs"):
        (borrowed,) = violated_alerts(alone.run(day, plan, None))
    assert borrowed.cause_set == cumulative_level_set(posterior, 0.9)
    issued = alone.set_selector_metadata()["sets_issued"]
    assert issued["pairs"]["range"]["cumulative_fallback"] == 1
    with pytest.raises(ValueError, match="population"):
        with alone.using_population("main2"):
            pass


# 6
def test_a4_variant_removes_witness_cells_and_robot_system_fields(
    registry: Any, templates: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    a4 = make_lik(registry, templates, a4=True)
    plain = make_lik(registry, templates)
    rule_a4, rule = a4.likelihood_rule, plain.likelihood_rule
    assert rule_a4.a4 is True and rule.a4 is False
    assert rule_a4.model_version != rule.model_version
    for template in ("range", "sched", "hold", "count", "resp", "int"):
        removed = set(rule.read_fields(template)) - set(rule_a4.read_fields(template))
        assert removed <= set(A4_REMOVED)
    assert any(
        set(rule.read_fields(t)) - set(rule_a4.read_fields(t)) for t in ("resp", "int")
    )
    assert all(
        not set(rule_a4.read_fields(t)) & set(A4_REMOVED)
        for t in ("range", "sched", "hold", "count", "resp", "int")
    )
    # delta (the diversion share of the witness cell) is not needed under A4
    without_delta = {k: v for k, v in TEST_VALUES.items() if k != "delta"}
    make_lik(
        registry, templates, likelihood=spec(sensitivity_values=without_delta), a4=True
    )
    # the extractor is asked to leave the robot out: the witness and the robot system fields are None, the aggregates recomputed
    seen: list[bool] = []
    real = ours_module.extract_evidence

    def spy(*args: Any, **kwargs: Any) -> Any:
        seen.append(bool(kwargs.get("exclude_robot", False)))
        return real(*args, **kwargs)

    monkeypatch.setattr(ours_module, "extract_evidence", spy)
    for detector in (a4, plain):
        detector.fit([], [])
        detector.run(out_of_band_day(), range_plan(registry), None)
    assert seen == [True, False]
    assert a4.name == "ours" and a4.is_a4 and not plain.is_a4
    for vector in a4.last_run.evidence.values():
        assert vector.witness.robot_present is None
        assert vector.witness.identity_confirmed is None
        assert vector.witness.intake_observed is None
        assert vector.system.nav_task_failed is None
        assert vector.system.manip_task_failed is None
        assert vector.system.battery_low is None
    # the runner builds it by name: the likelihood rule with A4 and the robot excluded
    cfg, options = load_experiment(LIKELIHOOD)
    env = make_environment(cfg, options, 0)
    built = build_detector("ours-A4", env, alpha=0.5)
    assert built.name == "ours-A4" and built.is_a4 and built.likelihood_rule.a4


# 7
@pytest.fixture(scope="module")
def e2e(tmp_path_factory: pytest.TempPathFactory) -> SimpleNamespace:
    tmp = tmp_path_factory.mktemp("likelihood")
    cfg, options = load_experiment(LIKELIHOOD)
    folders = []
    for name in ("run1", "run2"):
        folders.extend(
            run_experiment(cfg, options, tmp / name, git_rev=lambda: "rev0")
        )
    metrics = json.loads((folders[0] / "metrics.json").read_text(encoding="utf-8"))
    return SimpleNamespace(folders=folders, metrics=metrics)


def test_end_to_end_run_writes_the_new_metric_keys(e2e: SimpleNamespace) -> None:
    metrics = e2e.metrics
    for key in NEW_KEYS:
        assert key in metrics
        block = metrics[key]["ours"]
        assert block is not None, key
        assert "status" not in block or block["status"] == "ok", (key, block)
        assert metrics[key]["B3"] is None, key
    # ours-hier has no posterior: the scores and the pair quantities are null, its kappa is scored as a set
    for key in (
        "attribution_log_score",
        "attribution_brier",
        "attribution_equal_coverage",
        "pair_llr",
        "pair_direction_mcnemar",
    ):
        assert metrics[key]["ours-hier"] is None, key
    assert metrics["attribution_sets"]["ours-hier"] is not None
    # the equal-coverage comparison holds the hierarchical rule's kappa as a fixed set next to the likelihood posterior
    labelling = metrics["attribution_equal_coverage"]["ours"]["labellings"]["tight"]
    assert labelling is not None
    methods = json.dumps(labelling)
    assert '"hier"' in methods and '"lik"' in methods and '"prior"' in methods
    # the alert sets of the likelihood detector were calibrated before the test run (patient-level split of the builder)
    sets = metrics["meta"]["attribution"]["set_selector"]["ours"]
    assert sets["populations"]["main"]["n_calibration"] >= 1
    assert sets["populations"]["main"]["model_version"] == (
        metrics["meta"]["attribution"]["rules"]["ours"]["model_version"]
    )
    assert "ours-hier" not in metrics["meta"]["attribution"]["set_selector"]
    # JSON discipline: no inf or nan anywhere (strict parse)
    text = (e2e.folders[0] / "metrics.json").read_text(encoding="utf-8")
    json.loads(
        text,
        parse_constant=lambda c: (_ for _ in ()).throw(ValueError(f"{c} in metrics")),
    )


# 8
def test_byte_identical_metrics_across_two_runs(e2e: SimpleNamespace) -> None:
    first, second = (f / "metrics.json" for f in e2e.folders)
    assert first.read_bytes() == second.read_bytes()


# 9
def with_device_profile(tmp_path: Path, **section: Any) -> Path:
    """A copy of the mini benchmark whose manifest records a device profile (the generator's ``manifest_entry``)."""
    target = tmp_path / "bench"
    shutil.copytree(MINI, target)
    path = target / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    entry = GeneratorDeviceProfile(
        cuff_resolution_mmhg=section.pop("cuff_resolution_mmhg", 1.0)
    ).manifest_entry()
    entry.update(section)
    manifest["settings"]["device_profile"] = entry
    path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    return target


def repeated_cuff_day() -> ObservedDay:
    """The out-of-band day with an earlier cuff reading of the same value: two equal consecutive readings."""
    day = out_of_band_day()
    earlier = ms(12, 0)
    extra = Sample("bp", earlier, earlier, 152.0, 101, None)
    return dataclasses.replace(day, samples=(extra, *day.samples))


@pytest.mark.parametrize("resolution", [1.0, None])
def test_device_profile_reaches_the_extractor(
    tmp_path: Path, registry: Any, templates: Any, resolution: float | None
) -> None:
    bench = with_device_profile(tmp_path, cuff_resolution_mmhg=resolution)
    cfg, options = load_experiment(LIKELIHOOD)
    cfg = dataclasses.replace(cfg, benchmark_manifest=str(bench))
    manifest = open_benchmark(bench, view="observed").manifest
    env = make_environment(cfg, options, 0, manifest=manifest)
    cuff = env.profile.caps("cuff")
    assert cuff.cuff_resolution == resolution  # the manifest's value, None when the benchmark is not rounded
    assert env.profile.caps("dispenser").content_sensing is False
    ours = OursDetector(
        config(env.registry),
        env.registry,
        env.templates,
        components=PipelineComponents(use_forecaster=False),
        profile=env.profile,
        likelihood=spec(diagnostics_profile="without_diagnostics"),
    )
    ours.fit([], [])
    ours.run(repeated_cuff_day(), range_plan(env.registry), None)
    vectors = list(ours.last_run.evidence.values())
    assert vectors
    for vector in vectors:
        repeated = vector.signal_quality.cuff_value_repeated
        assert repeated is (True if resolution is not None else None)


def test_manifest_diagnostics_profile_must_agree_with_the_run(
    tmp_path: Path,
) -> None:
    bench = with_device_profile(tmp_path, diagnostics_profile="driver_with_diagnostics")
    cfg, options = load_experiment(LIKELIHOOD)  # declares without_diagnostics
    cfg = dataclasses.replace(cfg, benchmark_manifest=str(bench))
    manifest = open_benchmark(bench, view="observed").manifest
    env = make_environment(cfg, options, 0, manifest=manifest)
    with pytest.raises(ConfigError, match="diagnostics_profile"):
        build_detector("ours", env, alpha=0.5)


# 10
def test_no_ground_truth_reaches_the_detector(
    registry: Any, templates: Any, mini: SimpleNamespace
) -> None:
    class Sealed(BenchmarkDay):
        def __init__(self, observed: ObservedDay) -> None:
            object.__setattr__(self, "observed", observed)

        @property
        def latent(self) -> Any:  # type: ignore[override]
            raise AssertionError("the detector read the latent trace")

        @property
        def ground_truth(self) -> Any:  # type: ignore[override]
            raise AssertionError("the detector read the ground truth")

    ours = make_lik(registry, templates)
    ours.fit([Sealed(out_of_band_day())], [Sealed(out_of_band_day(1))])
    day = out_of_band_day()
    (alert,) = violated_alerts(ours.run(day, range_plan(registry), None))
    inputs = ours.alert_inputs(day.patient_id, alert)
    assert set(inputs.posteriors) == {"lik", "prior"} and set(inputs.fixed_sets) == {
        "hier"
    }
    with pytest.raises(TypeError):
        ours.run(Sealed(day), range_plan(registry), None)  # type: ignore[arg-type]
    # the source never touches the truth members or their types (the existing guard of the runner stays: see test_runner)
    tree = ast.parse(Path(ours_module.__file__).read_text(encoding="utf-8"))
    touched = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    } | {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert not touched & {"latent", "ground_truth", "LatentDay", "GroundTruthEvent"}
    # the hook of a detector that is built by the runner returns inputs without truth too
    for alert in violated_alerts(run_all(mini, "ours")):
        got = mini.detectors["ours"].alert_inputs("p05", alert)
        assert got is None or isinstance(got.fixed_sets, dict)


# ---- the smoke configuration of experiments/ ---------------------------------------------------------------------------


def test_experiments_smoke_config_labels_its_values_as_tests() -> None:
    text = SMOKE_LIKELIHOOD.read_text(encoding="utf-8")
    cfg, options = load_experiment(SMOKE_LIKELIHOOD)
    assert options.headline is False
    assert options.twins == "separate"
    assert options.attribution is not None
    assert options.attribution.loose_after_ms is not None
    assert options.attribution.set_alphas
    assert options.attribution.pair_primary_templates
    assert "TEST VALUE" in text and "never a headline" in text
    assert {"ours", "ours-hier"} <= set(cfg.detectors)
    ours = options.detector_params["ours"]["likelihood"]
    assert set(TEST_VALUES) <= set(ours["sensitivity_values"])
