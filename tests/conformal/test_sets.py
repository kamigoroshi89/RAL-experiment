"""Conformal calibration of the subtype sets of the attribution (WS05-T14, ADR-074 amendments 1 to 3).

Tests 1 to 8 of the task, plus the cumulative-level set, the validation of posteriors, the degenerate
inputs and the determinism. All numbers are FIXTURE-ONLY (dyadic probabilities, so the hand values are
exact in doubles). The names under test are read from ``ralmon.conformal.sets`` at call time, so that
the file collects before the implementation exists. Fixed seeds, no clock, no network.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import math
import random
from collections.abc import Mapping, Sequence
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SETS_PY = ROOT / "src" / "ralmon" / "conformal" / "sets.py"


def sets() -> Any:
    return importlib.import_module("ralmon.conformal.sets")


def example(
    patient: str,
    template: str,
    p_true: float,
    *,
    true: str = "a",
    other: str = "b",
) -> Any:
    """A calibration alert whose true subtype has posterior ``p_true`` (two applicable subtypes)."""
    return sets().SubtypeCalibrationAlert(
        patient_id=patient,
        template=template,
        posteriors={true: p_true, other: 1.0 - p_true},
        true_subtype=true,
    )


# FIXTURE-ONLY: p(true) of nine calibration alerts; the scores 1 - p, sorted ascending, are
# 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875, 0.9375, 0.96875 (all exact in doubles).
P_TRUE = [0.875, 0.75, 0.625, 0.5, 0.375, 0.25, 0.125, 0.0625, 0.03125]
SCORES = sorted(1.0 - p for p in P_TRUE)


def nine(template: str = "range") -> list[Any]:
    return [example(f"c{i}", template, p) for i, p in enumerate(P_TRUE)]


def marginal() -> Any:
    return sets().SubtypeSetCalibrator("marginal", population="main")


def mondrian(**kw: Any) -> Any:
    return sets().SubtypeSetCalibrator("mondrian", population="main", **kw)


# --- 1. the quantile -----------------------------------------------------------------------------------------


def test_quantile_with_finite_sample_correction() -> None:
    cal = marginal()
    cal.fit(nine(), model_version="m1")
    # n = 9, k = ceil(10 (1 - alpha)): alpha 0.5 -> 5, 0.3 -> 7, 0.2 -> 8, 0.1 -> 9
    assert cal.threshold("range", 0.5).value == SCORES[4] == 0.625
    assert cal.threshold("range", 0.3).value == SCORES[6] == 0.875
    assert cal.threshold("range", 0.2).value == SCORES[7] == 0.9375
    assert cal.threshold("range", 0.1).value == SCORES[8] == 0.96875
    # alpha 0.05 -> k = 10 > n: the full set, threshold +inf, and the object says so
    t = cal.threshold("range", 0.05)
    assert t.value == math.inf
    assert t.fallback is True
    assert t.n == 9
    assert cal.threshold("range", 0.1).fallback is False


def test_quantile_rank_is_exact_at_a_float_boundary_level() -> None:
    """``10 * (1 - 0.7)`` is 3.0000000000000004 in doubles: a float product gives rank 4, the exact rank is 3."""
    cal = marginal()
    cal.fit(nine(), model_version="m1")
    assert cal.threshold("range", 0.7).value == SCORES[2] == 0.375
    assert cal.threshold("range", Fraction(7, 10)).value == 0.375
    assert cal.threshold("range", Fraction(1, 5)).value == SCORES[7]


def test_alpha_is_validated_like_the_other_calibrators() -> None:
    cal = marginal()
    cal.fit(nine(), model_version="m1")
    for bad in (0.0, 1.0, -0.1, 1.5, math.nan, math.inf, True, "0.1", 1):
        with pytest.raises(ValueError, match="alpha"):
            cal.threshold("range", bad)


def test_alpha_extremes_give_the_smallest_score_or_the_full_set() -> None:
    cal = marginal()
    cal.fit(nine(), model_version="m1")
    assert cal.threshold("range", 0.999).value == SCORES[0]  # k = 1
    assert cal.threshold("range", 0.0001).value == math.inf  # rank above n
    assert cal.threshold("range", 0.0001).fallback is True


def test_threshold_is_monotone_in_alpha() -> None:
    cal = marginal()
    cal.fit(nine(), model_version="m1")
    values = [cal.threshold("range", a).value for a in (0.9, 0.5, 0.3, 0.2, 0.1, 0.05)]
    assert values == sorted(values)


def test_fit_refuses_an_empty_calibration_set() -> None:
    with pytest.raises(ValueError, match="at least one"):
        marginal().fit([], model_version="m1")


def test_unfitted_calibrator_refuses_to_predict() -> None:
    with pytest.raises(RuntimeError, match="fit"):
        marginal().threshold("range", 0.1)


def test_score_of_a_subtype_missing_from_the_posterior_is_one() -> None:
    """A true subtype that cannot violate the template has p = 0, score 1 (hand-over of WS02-T06)."""
    s = sets()
    assert s.nonconformity_score({"a": 0.75, "b": 0.25}, "a") == 0.25
    assert s.nonconformity_score({"a": 0.75, "b": 0.25}, "zzz") == 1.0
    assert s.nonconformity_score({"a": 1.0, "b": 0.0}, "b") == 1.0


# --- 2. the set below the threshold ----------------------------------------------------------------------------

POST = {"a": 0.5, "b": 0.25, "c": 0.125, "d": 0.125}  # scores 0.5, 0.75, 0.875, 0.875


def test_set_contains_subtypes_below_threshold() -> None:
    prediction_set = sets().prediction_set
    assert prediction_set(POST, 0.5) == (
        "a",
    )  # score at most the threshold: equality is inside
    assert prediction_set(POST, 0.75) == ("a", "b")
    assert prediction_set(POST, 0.8) == ("a", "b")
    assert prediction_set(POST, 0.875) == ("a", "b", "c", "d")  # ties ordered by name
    assert prediction_set(POST, math.inf) == ("a", "b", "c", "d")  # the full set
    assert prediction_set(POST, 0.4) == ()  # the pure rule can give an empty set


def test_set_is_ordered_by_decreasing_posterior_then_name() -> None:
    prediction_set = sets().prediction_set
    shuffled = {"d": 0.125, "b": 0.25, "c": 0.125, "a": 0.5}
    assert prediction_set(shuffled, math.inf) == ("a", "b", "c", "d")


def test_the_calibrated_set_uses_the_calibration_threshold() -> None:
    cal = marginal()
    cal.fit(nine(), model_version="m1")
    out = cal.predict_set(POST, "range", 0.3, patient_id="t1", model_version="m1")
    # alpha 0.3 -> threshold 0.875 -> all four
    assert out.subtypes == ("a", "b", "c", "d")
    assert out.threshold == 0.875
    assert out.full_set_fallback is False
    out = cal.predict_set(POST, "range", 0.5, patient_id="t1", model_version="m1")
    assert out.threshold == 0.625
    assert out.subtypes == ("a",)  # scores 0.5 and 0.75; only 0.5 is at most 0.625


def test_a_pure_empty_set_is_filled_with_the_most_probable_subtype() -> None:
    """``Alert.cause_set`` is never empty (02-interfaces.md#alert); adding the top subtype can only raise coverage."""
    cal = marginal()
    cal.fit(nine(), model_version="m1")
    flat = {"a": 0.5, "b": 0.5}
    # threshold at alpha 0.999 is 0.125: both scores 0.5 exceed it
    out = cal.predict_set(flat, "range", 0.999, patient_id="t1", model_version="m1")
    assert out.subtypes == ("a",)  # tie by name
    assert out.top1_fill is True
    filled = cal.predict_set(POST, "range", 0.3, patient_id="t1", model_version="m1")
    assert filled.top1_fill is False


# --- 3. Mondrian cells -----------------------------------------------------------------------------------------


def mixed() -> list[Any]:
    """Template ``range``: nine alerts; template ``hold``: two alerts; template ``sched``: none."""
    out = [example(f"r{i}", "range", p) for i, p in enumerate(P_TRUE)]
    out += [example("h0", "hold", 0.875), example("h1", "hold", 0.75)]
    return out


def test_mondrian_cell_with_few_members_falls_back_to_full_set() -> None:
    cal = mondrian()
    cal.fit(mixed(), model_version="m1")
    ok = cal.threshold("range", 0.2)
    assert (ok.value, ok.n, ok.fallback) == (SCORES[7], 9, False)
    few = cal.threshold("hold", 0.2)  # n = 2, k = ceil(3 * 0.8) = 3 > 2
    assert few.value == math.inf
    assert few.fallback is True
    assert few.n == 2
    assert "hold" in few.reason
    out = cal.predict_set(POST, "hold", 0.2, patient_id="t1", model_version="m1")
    assert out.subtypes == (
        "a",
        "b",
        "c",
        "d",
    )  # every applicable subtype (the keys of the posterior)
    assert out.full_set_fallback is True
    assert out.fallback_reason == few.reason
    assert out.cell == "hold"


def test_mondrian_unseen_template_falls_back_to_full_set() -> None:
    cal = mondrian()
    cal.fit(mixed(), model_version="m1")
    t = cal.threshold("sched", 0.2)
    assert (t.value, t.n, t.fallback) == (math.inf, 0, True)
    out = cal.predict_set(POST, "sched", 0.2, patient_id="t1", model_version="m1")
    assert out.full_set_fallback is True


def test_mondrian_min_cell_size_can_force_the_fallback() -> None:
    cal = mondrian(min_cell_size=10)
    cal.fit(mixed(), model_version="m1")
    forced = cal.threshold("range", 0.5)  # n = 9 < 10: the rank alone would be finite
    assert forced.fallback is True
    assert forced.value == math.inf
    assert "10" in forced.reason
    with pytest.raises(ValueError, match="min_cell_size"):
        mondrian(min_cell_size=0)


def test_mondrian_uses_one_threshold_per_template() -> None:
    cal = mondrian()
    items = [example(f"r{i}", "range", p) for i, p in enumerate(P_TRUE)]
    items += [
        example(f"h{i}", "hold", p) for i, p in enumerate(P_TRUE[:4])
    ]  # scores .125 .25 .375 .5
    cal.fit(items, model_version="m1")
    assert cal.threshold("range", 0.5).value == 0.625
    assert cal.threshold("hold", 0.5).value == 0.375  # n = 4, k = ceil(5 * 0.5) = 3
    assert cal.cell_sizes() == {"hold": 4, "range": 9}


def test_marginal_pools_the_templates() -> None:
    cal = marginal()
    cal.fit(mixed(), model_version="m1")
    assert cal.threshold("hold", 0.2).n == 11
    assert (
        cal.threshold("sched", 0.2).n == 11
    )  # the template is not a cell of the marginal variant


def test_template_ids_and_plain_strings_name_the_same_cell() -> None:
    from ralmon.spec import TemplateId

    cal = mondrian()
    cal.fit(nine("range"), model_version="m1")
    assert (
        cal.threshold(TemplateId.RANGE, 0.5).value == cal.threshold("range", 0.5).value
    )


# --- 4. patient-wise separation ----------------------------------------------------------------------------


def test_calibration_and_test_patients_are_disjoint() -> None:
    s = sets()
    cal = marginal()
    with pytest.raises(s.PatientLeakError, match="c3"):
        cal.fit(nine(), model_version="m1", test_patient_ids=["t1", "c3"])
    cal.fit(nine(), model_version="m1", test_patient_ids=["t1", "t2"])
    assert cal.calibration_patients == frozenset(f"c{i}" for i in range(9))
    cal.require_disjoint(["t1", "t2"])
    with pytest.raises(s.PatientLeakError, match="c0"):
        cal.require_disjoint(["t1", "c0"])


def test_predicting_for_a_calibration_patient_is_refused() -> None:
    s = sets()
    cal = marginal()
    cal.fit(nine(), model_version="m1")
    with pytest.raises(s.PatientLeakError, match="c4"):
        cal.predict_set(POST, "range", 0.3, patient_id="c4", model_version="m1")
    cal.predict_set(POST, "range", 0.3, patient_id="t9", model_version="m1")


def test_patient_ids_are_mandatory_and_non_empty() -> None:
    cal = marginal()
    cal.fit(nine(), model_version="m1")
    with pytest.raises(TypeError):
        cal.predict_set(POST, "range", 0.3, model_version="m1")  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="patient"):
        cal.predict_set(POST, "range", 0.3, patient_id="", model_version="m1")
    with pytest.raises(ValueError, match="patient"):
        sets().SubtypeCalibrationAlert(
            patient_id="", template="range", posteriors=POST, true_subtype="a"
        )


# --- 5. a separate calibrator for the pairs ---------------------------------------------------------------------


def test_separate_calibrator_for_pairs_is_a_separate_instance() -> None:
    s = sets()
    main = s.SubtypeSetCalibrator("mondrian", population="main")
    pairs = s.SubtypeSetCalibrator("marginal", population="pairs")
    assert main is not pairs
    main.fit(nine(), model_version="m1")
    with pytest.raises(RuntimeError, match="fit"):
        pairs.threshold("range", 0.5)  # fitting one instance leaves the other unfitted
    pair_items = [example(f"q{i}", "range", 0.5 + 0.0625 * i) for i in range(8)]
    pairs.fit(pair_items, model_version="m1")
    assert pairs.population == "pairs" and main.population == "main"
    assert pairs.n_calibration == 8 and main.n_calibration == 9
    assert pairs.threshold("range", 0.5).value != main.threshold("range", 0.5).value
    assert main.calibration_patients.isdisjoint(pairs.calibration_patients)
    # refitting the pairs instance does not move the main thresholds
    before = main.threshold("range", 0.5)
    pairs.fit(pair_items[:4], model_version="m2")
    assert main.threshold("range", 0.5) == before
    assert main.calibrated_for == "m1" and pairs.calibrated_for == "m2"


def test_population_label_is_required_and_non_empty() -> None:
    s = sets()
    with pytest.raises(TypeError):
        s.SubtypeSetCalibrator("marginal")
    with pytest.raises(ValueError, match="population"):
        s.SubtypeSetCalibrator("marginal", population="")
    with pytest.raises(ValueError, match="mode"):
        s.SubtypeSetCalibrator("global", population="main")


def test_the_predicted_set_names_its_population_and_guarantee() -> None:
    s = sets()
    cal = s.SubtypeSetCalibrator("marginal", population="pairs")
    cal.fit(nine(), model_version="m1")
    out = cal.predict_set(POST, "range", 0.3, patient_id="t1", model_version="m1")
    assert out.population == "pairs"
    assert out.mode == "marginal"
    assert out.guarantee == s.GUARANTEE_SETS
    assert "marginal" in s.GUARANTEE_SETS and "exchangeab" in s.GUARANTEE_SETS
    joined = " ".join(out.assumptions)
    assert "patient" in joined and "correlated" in joined
    assert "distribution-free" not in s.GUARANTEE_SETS


# --- 6. coverage on exchangeable synthetic scores ------------------------------------------------------------


def synthetic_alert(rng: random.Random, patient: str) -> Any:
    """An iid draw: random posterior over four subtypes, a true subtype drawn from a FIXED other law.

    The model is miscalibrated on purpose (the truth is drawn from the squared posterior): the
    conformal statement needs exchangeability, not a correct model.
    """
    names = ("s1", "s2", "s3", "s4")
    raw = [rng.random() ** 3 + 1e-6 for _ in names]
    total = sum(raw)
    post = {n: r / total for n, r in zip(names, raw, strict=True)}
    weights = [p * p for p in post.values()]
    true = rng.choices(names, weights=weights)[0]
    return sets().SubtypeCalibrationAlert(
        patient_id=patient, template="range", posteriors=post, true_subtype=true
    )


@pytest.mark.parametrize("alpha", [0.2, 0.1])
def test_coverage_on_exchangeable_synthetic_scores(alpha: float) -> None:
    rng = random.Random(20261012)
    reps, n_cal, n_test = 80, 300, 300
    covered = pure = total = 0
    for r in range(reps):
        cal = marginal()
        cal.fit(
            [synthetic_alert(rng, f"c{r}-{i}") for i in range(n_cal)],
            model_version="syn",
        )
        for i in range(n_test):
            alert = synthetic_alert(rng, f"t{r}-{i}")
            out = cal.predict_set(
                alert.posteriors,
                "range",
                alpha,
                patient_id=alert.patient_id,
                model_version="syn",
            )
            covered += alert.true_subtype in out.subtypes
            pure += alert.true_subtype in sets().prediction_set(
                alert.posteriors, out.threshold
            )
            total += 1
    rate = pure / total  # the pure rule: the conformal statement
    assert covered >= pure  # the fill of an empty set can only raise the coverage
    # coverage is in [1 - alpha, 1 - alpha + 1/(n+1)] on average (continuous scores); the standard error of the pooled rate over the replications is se
    se = math.sqrt(alpha * (1 - alpha) * (1 / n_cal + 1 / n_test) / reps)
    assert 1 - alpha - 4 * se <= rate <= 1 - alpha + 1 / (n_cal + 1) + 4 * se
    assert se < 0.005


# --- 7. the model-version token ------------------------------------------------------------------------------


def test_calibrator_refuses_a_model_version_mismatch() -> None:
    s = sets()
    cal = marginal()
    assert cal.calibrated_for is None
    cal.fit(nine(), model_version="v1")
    assert cal.calibrated_for == "v1"
    cal.predict_set(POST, "range", 0.3, patient_id="t1", model_version="v1")
    with pytest.raises(s.StaleSetCalibratorError, match="v2"):
        cal.predict_set(POST, "range", 0.3, patient_id="t1", model_version="v2")
    with pytest.raises(s.StaleSetCalibratorError):
        cal.check_fresh("v2")
    cal.check_fresh("v1")
    cal.fit(nine(), model_version="v2")  # refit on the current model
    assert cal.calibrated_for == "v2"
    cal.predict_set(POST, "range", 0.3, patient_id="t1", model_version="v2")


def test_calibrator_fitted_for_no_model_refuses_every_prediction() -> None:
    s = sets()
    cal = marginal()
    cal.fit(nine())
    assert cal.calibrated_for is None
    with pytest.raises(s.StaleSetCalibratorError):
        cal.predict_set(POST, "range", 0.3, patient_id="t1", model_version="v1")


# --- 8. ground-truth discipline -------------------------------------------------------------------------------


def _parameter_names(fn: Any) -> list[str]:
    return list(inspect.signature(fn).parameters)


def test_no_ground_truth_import_in_the_set_builder() -> None:
    s = sets()
    tree = ast.parse(SETS_PY.read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
    joined = " ".join(imported)
    for banned in ("benchmark", "LatentDay", "GroundTruthEvent", "attribution"):
        assert banned not in joined
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
        n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
    }
    assert not names & {"LatentDay", "GroundTruthEvent"}
    # the builders take posteriors and a threshold or a level, never a truth
    for fn in (
        s.prediction_set,
        s.cumulative_level_set,
        s.SubtypeSetCalibrator.predict_set,
        s.SubtypeSetCalibrator.threshold,
    ):
        for name in _parameter_names(fn):
            assert "true" not in name and "truth" not in name and "label" not in name
    assert _parameter_names(s.prediction_set) == ["posteriors", "threshold"]
    # the calibration side takes the truth, as the field of the calibration alert
    fields = {f for f in s.SubtypeCalibrationAlert.__dataclass_fields__}
    assert "true_subtype" in fields
    assert "true_subtype" in inspect.signature(s.nonconformity_score).parameters


def test_the_set_builder_cannot_receive_a_truth() -> None:
    s = sets()
    with pytest.raises(TypeError):
        s.prediction_set(POST, 0.8, true_subtype="a")
    cal = marginal()
    cal.fit(nine(), model_version="m1")
    with pytest.raises(TypeError):
        cal.predict_set(
            POST,
            "range",
            0.3,
            patient_id="t1",
            model_version="m1",
            true_subtype="a",  # type: ignore[call-arg]
        )


# --- the cumulative-level set (non-conformal alternative, ADR-074 amendment 1) -------------------------------


def test_cumulative_level_set_hand_cases() -> None:
    f = sets().cumulative_level_set
    assert f(POST, 0.4) == ("a",)
    assert f(POST, 0.5) == ("a",)  # cumulative 0.5 reaches the level 0.5 exactly
    assert f(POST, 0.75) == ("a", "b")  # exactly 0.75
    assert f(POST, 0.8) == ("a", "b", "c")
    assert f(POST, 0.9) == ("a", "b", "c", "d")
    assert f(POST, Fraction(3, 4)) == ("a", "b")


def test_cumulative_level_set_breaks_ties_by_subtype_name() -> None:
    f = sets().cumulative_level_set
    tied = {"z": 0.5, "a": 0.25, "m": 0.25}
    assert f(tied, 0.5) == ("z",)
    even = {"z": 0.25, "a": 0.25, "m": 0.25, "b": 0.25}
    assert f(even, 0.5) == ("a", "b")  # the two smallest names
    assert f(even, 0.6) == ("a", "b", "m")


def test_cumulative_level_set_reads_probabilities_and_level_as_decimal_literals() -> (
    None
):
    """0.7 + 0.2 is 0.8999999999999999 in doubles; read as decimals the two reach the level 0.9 exactly."""
    f = sets().cumulative_level_set
    post = {"c": 0.7, "b": 0.2, "a": 0.1}
    assert f(post, 0.7) == ("c",)
    assert f(post, 0.9) == ("c", "b")
    assert f(post, Fraction(9, 10)) == ("c", "b")
    assert f(post, 0.91) == ("c", "b", "a")


def test_cumulative_level_set_is_independent_of_mapping_order_and_never_empty() -> None:
    f = sets().cumulative_level_set
    a = {"a": 0.5, "b": 0.25, "c": 0.125, "d": 0.125}
    b = dict(reversed(list(a.items())))
    assert f(a, 0.9) == f(b, 0.9)
    assert len(f({"only": 1.0}, 0.01)) == 1
    for level in (0.01, 0.5, 0.99):
        assert len(f(a, level)) >= 1


def test_cumulative_level_has_no_default_and_is_validated() -> None:
    f = sets().cumulative_level_set
    assert "level" in _parameter_names(f)
    assert inspect.signature(f).parameters["level"].default is inspect.Parameter.empty
    for bad in (0.0, 1.0, -1.0, 2.0, math.nan, True, "0.9"):
        with pytest.raises(ValueError, match="level"):
            f(POST, bad)


# --- posteriors: validation -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {"a": 0.5, "b": 0.4},  # sums to 0.9
        {"a": 0.5, "b": 0.6},  # sums to 1.1
        {"a": -0.25, "b": 1.25},
        {"a": math.nan, "b": 1.0},
        {"a": math.inf, "b": 0.0},
        {"a": 1.5, "b": -0.5},
    ],
)
def test_posteriors_that_are_not_a_distribution_are_refused(
    bad: Mapping[str, float],
) -> None:
    s = sets()
    with pytest.raises(s.PosteriorError):
        s.prediction_set(bad, 0.5)
    with pytest.raises(s.PosteriorError):
        s.cumulative_level_set(bad, 0.5)
    with pytest.raises(s.PosteriorError):
        s.nonconformity_score(bad, "a")


def test_posteriors_summing_to_one_within_rounding_are_accepted() -> None:
    s = sets()
    third = 1.0 / 3.0
    post = {"a": third, "b": third, "c": third}  # sums to 1 within 1e-16
    assert s.prediction_set(post, math.inf) == ("a", "b", "c")
    assert issubclass(s.PosteriorError, ValueError)


def test_a_bad_calibration_posterior_names_the_patient() -> None:
    s = sets()
    bad = s.SubtypeCalibrationAlert(
        patient_id="p-bad",
        template="range",
        posteriors={"a": 0.5, "b": 0.1},
        true_subtype="a",
    )
    with pytest.raises(s.PosteriorError, match="p-bad"):
        marginal().fit([bad], model_version="m1")


# --- determinism ----------------------------------------------------------------------------------------------


def test_the_calibration_is_independent_of_the_order_of_the_examples() -> None:
    items = mixed()
    shuffled = items[:]
    random.Random(7).shuffle(shuffled)
    a, b = mondrian(), mondrian()
    a.fit(items, model_version="m1")
    b.fit(shuffled, model_version="m1")
    for template in ("range", "hold", "sched"):
        for alpha in (0.5, 0.2, 0.05):
            assert a.threshold(template, alpha) == b.threshold(template, alpha)
    out_a = a.predict_set(POST, "range", 0.2, patient_id="t1", model_version="m1")
    out_b = b.predict_set(POST, "range", 0.2, patient_id="t1", model_version="m1")
    assert out_a == out_b


def test_the_public_types_are_immutable_values() -> None:
    cal = marginal()
    cal.fit(nine(), model_version="m1")
    out = cal.predict_set(POST, "range", 0.3, patient_id="t1", model_version="m1")
    with pytest.raises(AttributeError):
        out.subtypes = ("x",)  # type: ignore[misc]
    assert isinstance(out.subtypes, tuple)
    sequence: Sequence[str] = out.subtypes
    assert all(isinstance(x, str) for x in sequence)
