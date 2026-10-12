"""WS08-T09: metrics for probabilistic attribution (ADR-074): log score, Brier, calibration curves, sets, equal coverage, pairs.

ILLUSTRATIVE, UNVERIFIED, FIXTURE-ONLY. Every number is an arithmetic test value written here before the run; the expected
values are computed by hand in the comments. ``TEST_VALUES`` of ``tests/attribution/test_likelihood_rule.py`` take one value of
the sensitivity grid for each parameter of the likelihood rule so that a rule can be built: none is a proposal, none is a
clinical value, and the production code has no default for any of them. T = 86_400_000 ms, H = one hour.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from ralmon.attribution import Alert, AttributedCause
from ralmon.benchmark import GroundTruthEvent, InjectedClass
from ralmon.conformal.sets import PatientLeakError
from ralmon.eval import attribution_sets as S
from ralmon.eval import attribution_truth as T
from ralmon.eval import metrics as M
from ralmon.eval import pairs as P
from ralmon.monitor import VerdictState
from ralmon.spec import TemplateId
from tests.attribution.test_likelihood_rule import TEST_VALUES, build_rule
from tests.eval.helpers import C1, C2, C3, alert
from tests.fixtures.attribution import load_fixture_registry, make_record, vector

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "ralmon"
HOUR = 3_600_000
AFTER = 60_000  # TEST VALUE for the post-window allowance of the loose labelling (no source, not a proposal)


# ---- builders ---------------------------------------------------------------------------------------------------------


def p_alert(
    t: int,
    tau: str,
    p: Sequence[float] | None,
    *,
    key: str = "k",
    cause_set: Sequence[str] | None = None,
    caused_by: str | None = None,
    verdict: VerdictState = VerdictState.VIOLATED,
    kappa: AttributedCause = C1,
) -> Alert:
    """An Alert of template ``tau`` with the posterior ``p`` over (C1, C2, C3) and an optional subtype set."""
    base = alert(t, kappa, key=key, verdict=verdict, tau=TemplateId(tau))
    mapping = None if p is None else {C1: p[0], C2: p[1], C3: p[2]}
    return dataclasses.replace(
        base, p_kappa=mapping, cause_set=cause_set, caused_by=caused_by
    )


def labelled(
    tau: str,
    p: Sequence[float] | None,
    true_class: str,
    *,
    subtype: str = "x",
    patient: str = "p1",
    t: int = 0,
    cause_set: Sequence[str] | None = None,
    kappa: AttributedCause = C1,
    inputs: T.AlertInputs | None = None,
) -> T.LabelledAlert:
    return T.LabelledAlert(
        patient,
        p_alert(t, tau, p, cause_set=cause_set, kappa=kappa),
        tau,
        true_class,
        subtype,
        0,
        True,
        1,
        inputs,
    )


def event(
    cls: str,
    subtype: str,
    onset: int,
    end: int | None = None,
    template: str | None = None,
    injected: bool | None = None,
    group: str | None = None,
) -> GroundTruthEvent:
    c = InjectedClass(cls)
    return GroundTruthEvent(
        c,
        subtype,
        onset,
        end,
        c is not InjectedClass.C1 if injected is None else injected,
        template,
        group,
    )


# ---- 1, 2: log score, Brier, per template, equal-weight aggregate without RESP --------------------------------------------

THREE = [
    labelled("range", (0.5, 0.3, 0.2), "C1"),
    labelled("range", (0.2, 0.7, 0.1), "C2"),
    labelled("range", (0.1, 0.1, 0.8), "C3"),
]


def test_log_score_and_brier_hand_values() -> None:
    """Three alerts at RANGE. Log score = mean of -ln p(true class): (-ln 0.5 - ln 0.7 - ln 0.8) / 3 = (0.693147 + 0.356675 +
    0.223144) / 3 = 0.424322. Brier = mean of the sum over C1, C2, C3 of (p_c - y_c)^2: alert 1 (0.5-1)^2 + 0.3^2 + 0.2^2 =
    0.38; alert 2 0.2^2 + (0.7-1)^2 + 0.1^2 = 0.14; alert 3 0.1^2 + 0.1^2 + (0.8-1)^2 = 0.06; mean 0.58 / 3 = 0.193333."""
    ls = M.attribution_log_score(THREE)
    br = M.attribution_brier(THREE)
    assert ls is not None and br is not None
    assert ls["RANGE"] == pytest.approx(
        (-math.log(0.5) - math.log(0.7) - math.log(0.8)) / 3, abs=1e-12
    )
    assert ls["RANGE"] == pytest.approx(0.424322, abs=1e-6)
    assert br["RANGE"] == pytest.approx(0.58 / 3, abs=1e-12)
    assert ls["AGGREGATE"] == pytest.approx(ls["RANGE"], abs=1e-12)  # one template
    assert set(ls) == {*M.TEMPLATES, "AGGREGATE"}
    assert (
        ls["SCHED"] is None
    )  # a template without a scored alert is undefined, never 0


def test_per_template_and_equal_weight_aggregate_without_resp() -> None:
    """RANGE (the three alerts above) 0.424322; SCHED one alert p = (0.9, 0.05, 0.05), true C1: -ln 0.9 = 0.105361; RESP one
    alert p = (0.25, 0.25, 0.5), true C1: -ln 0.25 = 1.386294. The aggregate is the plain mean of the templates that have an
    alert, RESP apart (ADR-072): (0.424322 + 0.105361) / 2 = 0.264841, NOT the mean of three (0.638659) and NOT the mean over
    the five alerts."""
    items = [
        *THREE,
        labelled("sched", (0.9, 0.05, 0.05), "C1"),
        labelled("resp", (0.25, 0.25, 0.5), "C1"),
    ]
    ls = M.attribution_log_score(items)
    assert ls is not None
    assert ls["SCHED"] == pytest.approx(-math.log(0.9), abs=1e-12)
    assert ls["RESP"] == pytest.approx(-math.log(0.25), abs=1e-12)
    assert ls["AGGREGATE"] == pytest.approx((0.424322 + 0.105361) / 2, abs=1e-6)
    assert ls["AGGREGATE"] != pytest.approx(
        (0.424322 + 0.105361 + 1.386294) / 3, abs=1e-3
    )
    summary = M.attribution_score_summary(items)
    assert summary is not None
    assert summary.templates_averaged == ("RANGE", "SCHED")
    assert (
        summary.n["RANGE"] == 3 and summary.n["SCHED"] == 1 and summary.n["RESP"] == 1
    )
    assert summary.aggregate_excluded == ("RESP",)


def test_a_zero_probability_for_the_true_class_is_infinite_and_counted() -> None:
    """-ln 0 is +inf; the library returns inf and counts it, the file writer turns it into null with a reason."""
    items = [labelled("range", (0.0, 0.5, 0.5), "C1")]
    ls = M.attribution_log_score(items)
    assert ls is not None and math.isinf(ls["RANGE"])  # type: ignore[arg-type]
    summary = M.attribution_score_summary(items)
    assert summary is not None and summary.n_zero_probability["RANGE"] == 1
    br = M.attribution_brier(items)
    assert br is not None and br["RANGE"] == pytest.approx(1.0 + 0.25 + 0.25)


# ---- 3: calibration curve ---------------------------------------------------------------------------------------------


def test_calibration_curve_counts_per_bin() -> None:
    """Two alerts at RANGE with p = (0.6, 0.3, 0.1), true C1 and true C2. One-vs-rest pairs (p_c, y_c): alert 1 (0.6, 1),
    (0.3, 0), (0.1, 0); alert 2 (0.6, 0), (0.3, 1), (0.1, 0). Four equal-width bins: [0, .25): 0.1, 0.1 -> n 2, mean 0.1,
    observed 0; [.25, .5): 0.3, 0.3 -> n 2, mean 0.3, observed 0.5; [.5, .75): 0.6, 0.6 -> n 2, mean 0.6, observed 0.5;
    [.75, 1]: empty. An empty bin is reported with count 0 and an undefined mean and frequency (nan), NOT with accuracy 0."""
    items = [
        labelled("range", (0.6, 0.3, 0.1), "C1"),
        labelled("range", (0.6, 0.3, 0.1), "C2"),
    ]
    curve = M.attribution_calibration_curve(items, 4)
    assert curve is not None
    bins = curve["RANGE"]
    assert [b[2] for b in bins] == [2, 2, 2, 0]
    assert bins[0][0] == pytest.approx(0.1) and bins[0][1] == pytest.approx(0.0)
    assert bins[1][0] == pytest.approx(0.3) and bins[1][1] == pytest.approx(0.5)
    assert bins[2][0] == pytest.approx(0.6) and bins[2][1] == pytest.approx(0.5)
    assert math.isnan(bins[3][0]) and math.isnan(bins[3][1])  # empty: not 0
    assert curve["SCHED"] == []  # no alert at SCHED: no curve


def test_calibration_detail_has_per_class_and_top_label_curves() -> None:
    """Top label: the class with the largest p_kappa is the predicted one; both alerts above predict C1 with confidence 0.6,
    right for the first and wrong for the second: bin [.5, .75): n 2, mean 0.6, observed 0.5; ECE = |0.6 - 0.5| = 0.1. Per
    class C1: points (0.6, 1), (0.6, 0): bin [.5, .75) n 2 observed 0.5."""
    items = [
        labelled("range", (0.6, 0.3, 0.1), "C1"),
        labelled("range", (0.6, 0.3, 0.1), "C2"),
    ]
    detail = M.attribution_calibration_detail(items, 4)
    assert detail is not None
    top = detail["RANGE"]["top_label"]
    assert [b.n for b in top] == [0, 0, 2, 0]
    assert top[2].observed_rate == pytest.approx(0.5)
    assert detail["RANGE"]["ece_top_label"] == pytest.approx(0.1, abs=1e-12)
    c1 = detail["RANGE"]["per_class"]["C1"]
    assert [b.n for b in c1] == [0, 0, 2, 0] and c1[2].observed_rate == 0.5


# ---- 8: methods without p_kappa are null ------------------------------------------------------------------------------


def test_methods_without_p_kappa_are_null() -> None:
    plain = [labelled("range", None, "C1", kappa=C2)]
    assert M.attribution_log_score(plain) is None
    assert M.attribution_brier(plain) is None
    assert M.attribution_calibration_curve(plain, 4) is None
    assert M.attribution_score_summary(plain) is None
    assert M.attribution_log_score([]) is None
    # a mixture scores the alerts that have a posterior and counts the others
    mixed = [*THREE, labelled("range", None, "C1")]
    summary = M.attribution_score_summary(mixed)
    assert summary is not None and summary.n_without_p_kappa == 1
    assert summary.n["RANGE"] == 3


# ---- the labelling: tight and loose -----------------------------------------------------------------------------------


def _label(
    gt: Sequence[GroundTruthEvent],
    det: Sequence[Alert],
    contexts: Sequence[T.EventContext] | None,
    labelling: str,
    **kw: Any,
) -> T.LabelResult:
    return T.label_alerts(
        gt,
        det,
        contexts,
        labelling=labelling,
        loose_after_ms=kw.pop("loose_after_ms", AFTER),
        patient_id=kw.pop("patient_id", "p1"),
        **kw,
    )


def test_tight_labelling_needs_the_faulty_device_in_the_data_scope_and_an_active_window() -> (
    None
):
    """A ble_dropout (C2) on the ECG during [10:00, 11:00] and a COUNT alert decided at 10:30: the ECG is in the data scope of
    no template (COUNT: the dispenser), so under the TIGHT labelling the dropout is not the cause (the alert has no cause and is
    left out, counted); under the LOOSE labelling a dropout anywhere in the window counts and the alert is C2. The same
    dropout on the dispenser is the cause under both. A HOLD alert decided at 11:00 + 30 s, after the window has closed, is
    caused by the dispenser dropout only under the loose labelling (post-window allowance 60 s)."""
    ecg = event("C2", "ble_dropout", 10 * HOUR, 11 * HOUR)
    ctx_ecg = [T.EventContext(("sched", "resp", "hold", "count"), "ecg")]
    count_alert = p_alert(10 * HOUR + 30 * 60_000, "count", (0.2, 0.7, 0.1))
    loose = _label([ecg], [count_alert], ctx_ecg, "loose")
    tight = _label([ecg], [count_alert], ctx_ecg, "tight")
    assert [x.true_class for x in loose.labelled] == ["C2"]
    assert loose.labelled[0].true_subtype == "ble_dropout"
    assert tight.labelled == ()
    assert tight.excluded["no_compatible_event"] == 1
    dispenser = [T.EventContext(("sched", "resp", "hold", "count"), "dispenser")]
    assert [
        x.true_class for x in _label([ecg], [count_alert], dispenser, "tight").labelled
    ] == ["C2"]
    late = p_alert(11 * HOUR + 30_000, "hold", (0.2, 0.7, 0.1))
    assert [
        x.true_class for x in _label([ecg], [late], dispenser, "loose").labelled
    ] == ["C2"]
    assert _label([ecg], [late], dispenser, "tight").labelled == ()
    # the cuff is in the data scope of HOLD and the dispenser too; the cuff is not in the scope of COUNT
    cuff = [T.EventContext(("sched", "resp", "hold", "count"), "cuff")]
    assert _label([ecg], [count_alert], cuff, "tight").labelled == ()
    hold_alert = p_alert(10 * HOUR + 1, "hold", (0.2, 0.7, 0.1))
    assert len(_label([ecg], [hold_alert], cuff, "tight").labelled) == 1


def test_the_template_must_be_one_the_event_can_violate() -> None:
    """A stuck_at (templates range, hold, resp) cannot cause a SCHED alert whatever the time (both labellings)."""
    stuck = event("C2", "stuck_at", 0, HOUR)
    ctx = [T.EventContext(("range", "hold", "resp"), "cuff")]
    sched = p_alert(30 * 60_000, "sched", (0.2, 0.7, 0.1))
    assert _label([stuck], [sched], ctx, "loose").labelled == ()
    assert _label([stuck], [sched], ctx, "tight").labelled == ()
    rng = p_alert(30 * 60_000, "range", (0.2, 0.7, 0.1))
    assert len(_label([stuck], [rng], ctx, "tight").labelled) == 1


def test_c1_events_use_their_template_and_first_decidable_instant() -> None:
    """A C1 event of a windowed obligation (SCHED, end_ms the deadline) is decidable at the deadline: an alert at the deadline
    or within the allowance after it is caused by it; one before it is not (both labellings)."""
    sched = event("C1", "measurement_refusal", 8 * HOUR, 9 * HOUR, "sched")
    ok = p_alert(9 * HOUR + 30_000, "sched", (0.9, 0.05, 0.05))
    early = p_alert(8 * HOUR + 30_000, "sched", (0.9, 0.05, 0.05))
    wrong = p_alert(9 * HOUR, "range", (0.9, 0.05, 0.05))
    for lab in ("tight", "loose"):
        assert len(_label([sched], [ok], None, lab).labelled) == 1
        assert _label([sched], [early], None, lab).labelled == ()
        assert _label([sched], [wrong], None, lab).labelled == ()
    got = _label([sched], [ok], None, "tight").labelled[0]
    assert (got.true_class, got.true_subtype, got.template) == (
        "C1",
        "measurement_refusal",
        "sched",
    )


def test_ambiguous_alerts_prefer_injected_events_and_are_otherwise_dropped() -> None:
    """Two compatible events of two classes: if exactly one class is injected it is the cause (the C2 here); if the classes
    cannot be told apart by that rule the alert is dropped and counted as ambiguous."""
    c1 = event("C1", "spontaneous_range", 0, None, "range", injected=False)
    c2 = event("C2", "stuck_at", 0, HOUR)
    ctx = [
        T.EventContext(None, None),
        T.EventContext(("range", "hold", "resp"), "cuff"),
    ]
    a = p_alert(30_000, "range", (0.4, 0.4, 0.2))
    res = _label([c1, c2], [a], ctx, "loose")
    assert [x.true_class for x in res.labelled] == ["C2"] and res.labelled[
        0
    ].n_compatible == 2
    c1i = event("C1", "hypertensive_spike", 0, None, "range", injected=True)
    res2 = _label([c1i, c2], [a], [T.EventContext(None, None), ctx[1]], "loose")
    assert res2.labelled == () and res2.excluded["ambiguous"] == 1


def test_predicted_violations_and_cascade_effects_are_folded_by_default() -> None:
    """A PREDICTED_VIOLATION has no p_kappa and is no cause to score; a cascade effect carries the ROOT's posterior and set, so it is
    folded (left out, counted) unless the policy says include, and the policy is recorded."""
    sched = event("C1", "measurement_refusal", 8 * HOUR, 9 * HOUR, "sched")
    root = p_alert(9 * HOUR, "sched", (0.9, 0.05, 0.05), key="r")
    effect = p_alert(
        9 * HOUR + 10_000, "sched", (0.9, 0.05, 0.05), key="e", caused_by="r"
    )
    predicted = p_alert(
        9 * HOUR - 5_000,
        "sched",
        None,
        key="q",
        verdict=VerdictState.PREDICTED_VIOLATION,
    )
    res = _label([sched], [root, effect, predicted], None, "tight")
    assert len(res.labelled) == 1 and res.labelled[0].alert is root
    assert (
        res.excluded["cascade_effect"] == 1 and res.excluded["predicted_violation"] == 1
    )
    inc = _label([sched], [root, effect], None, "tight", effects="include")
    assert len(inc.labelled) == 2
    with pytest.raises(ValueError, match="effects"):
        _label([sched], [root], None, "tight", effects="nonsense")
    with pytest.raises(ValueError, match="labelling"):
        _label([sched], [root], None, "strict")


def test_the_event_contexts_are_read_from_the_injection_log() -> None:
    """``day_contexts`` aligns one context per ground-truth event of a day: the templates and the target of the linked
    injection-log entry (``truth_indices``), the static table for a C3 subtype, the template of a C1 event; an event no entry
    links gets an unconstrained context."""
    gt = [
        event("C1", "hypertensive_spike", 0, None, "range"),
        event("C2", "ble_dropout", HOUR, 2 * HOUR),
        event("C3", "replay", 3 * HOUR),
        event("C2", "stuck_at", 4 * HOUR, 5 * HOUR),
    ]
    log = [
        {
            "cls": "C2",
            "subtype": "ble_dropout",
            "truth_indices": [1],
            "details": {"target": "oximeter", "templates": ["sched", "hold"]},
        }
    ]
    ctx = T.day_contexts(gt, log)
    assert len(ctx) == 4
    assert ctx[0] == T.EventContext(("range",), None)
    assert ctx[1] == T.EventContext(("sched", "hold"), "oximeter")
    assert ctx[2].templates == T.C3_EVENT_TEMPLATES["replay"] and ctx[2].target is None
    assert ctx[3] == T.EventContext(None, None)


def test_static_tables_agree_with_the_extractor_and_the_labeller() -> None:
    from ralmon.attribution import extract
    from ralmon.eval.metrics import first_decidable_ms

    assert {k.value: v for k, v in extract._DATA_SCOPE.items()} == dict(T.DATA_SCOPE)
    for ev in (
        event("C1", "x", 5, 9, "resp"),
        event("C1", "x", 5, None, "range"),
        event("C2", "x", 5, 9),
    ):
        assert T._first_decidable(ev) == first_decidable_ms(ev)


def test_both_labellings_are_reported() -> None:
    """``both_labellings`` labels the same alerts twice, TIGHT first (primary) and LOOSE next to it, and says that the choice of
    the tight labelling was made after seeing the result (ADR-074 amendment 2)."""
    ecg = event("C2", "ble_dropout", 10 * HOUR, 11 * HOUR)
    a = p_alert(10 * HOUR + 1, "count", (0.2, 0.7, 0.1))
    out = T.both_labellings(
        [ecg],
        [a],
        [T.EventContext(("count",), "ecg")],
        loose_after_ms=AFTER,
        patient_id="p1",
    )
    assert list(out) == ["tight", "loose"]
    assert out["tight"].labelled == () and len(out["loose"].labelled) == 1
    assert "after seeing" in T.LABELLING_STATEMENT
    assert "tight" in T.LABELLING_STATEMENT and "loose" in T.LABELLING_STATEMENT


# ---- 9: ground-truth discipline ---------------------------------------------------------------------------------------


def _imports_of(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names.append(node.module or "")
            names.extend(a.name for a in node.names)
        elif isinstance(node, ast.Import):
            names.extend(a.name for a in node.names)
    return names


def test_no_ground_truth_in_the_attributor() -> None:
    """The metric code reads the truth (it is the scoring side); the attributor, the rule and the set builder cannot: none of
    them imports the evaluation package or names the truth types, and what a detector hands to the scoring side
    (``AlertInputs``) has no truth field."""
    for rel in (
        "attribution/likelihood.py",
        "attribution/attributor.py",
        "attribution/rule.py",
        "conformal/sets.py",
    ):
        path = SRC / rel
        joined = " ".join(_imports_of(path))
        assert "ralmon.eval" not in joined, rel
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
            n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
        }
        assert not names & {"LatentDay", "GroundTruthEvent", "LabelledAlert"}, rel
    fields = {f.name for f in dataclasses.fields(T.AlertInputs)}
    assert not any(
        "true" in f or "truth" in f or "label" in f or "ground" in f for f in fields
    )
    # the scoring side is the one that takes the truth
    assert "gt" in inspect.signature(T.label_alerts).parameters
    for fn in (
        M.attribution_log_score,
        M.attribution_brier,
        M.attribution_calibration_curve,
    ):
        assert "latent" not in " ".join(inspect.signature(fn).parameters)
    # the detector side: OursDetector.run takes an observed day only
    from ralmon.eval.ours import OursDetector

    assert list(inspect.signature(OursDetector.run).parameters)[:4] == [
        "self",
        "day",
        "plan",
        "evidence",
    ]


# ---- 4, 5, 6: the pair quantity ---------------------------------------------------------------------------------------

REGISTRY = load_fixture_registry()
EPS, QC = TEST_VALUES["eps"], TEST_VALUES["qc"]
CONTENT = "dispenser.content_change"
INTERVAL = "dispenser.interval_since_previous_ms"


def count_vector(content: float | None, interval: float | None) -> Any:
    fields: dict[str, Any] = {}
    if content is not None:
        fields[CONTENT] = content
    if interval is not None:
        fields[INTERVAL] = interval
    return vector("count", fields, REGISTRY)


@pytest.fixture(scope="module")
def table():  # type: ignore[no-untyped-def]
    from ralmon.attribution.likelihood import load_likelihood_table

    return load_likelihood_table(ROOT / "configs" / "attribution_likelihood.yaml")


@pytest.fixture(scope="module")
def rule(table):  # type: ignore[no-untyped-def]
    return build_rule(REGISTRY, table)


def member(
    pair: str,
    name: str,
    evidence: Any,
    *,
    sub_a: str = "double_take",
    sub_b: str = "dispenser_bounce",
    indistinguishable: bool = False,
    group: str = "double_take_vs_bounce",
) -> P.PairMember:
    return P.PairMember(
        pair_id=pair,
        member=name,
        group=group,
        variant_id="v",
        indistinguishable=indistinguishable,
        subtype_a=sub_a,
        subtype_b=sub_b,
        template="count",
        evidence=evidence,
        alert=p_alert(0, "count", (0.3, 0.4, 0.3)),
    )


def test_pair_llr_between_subtypes(rule) -> None:  # type: ignore[no-untyped-def]
    """Lambda is taken between the two SPECIFIC subtypes of the pair, not between classes. Template COUNT, only
    ``dispenser.content_change`` read and asserted (value 0.0, a bounce: nothing left the dispenser). Cells: dispenser_bounce
    raises it by construction, P(A) = 1 - eps = 0.99; double_take has the structural zero, P(A) = eps = 0.01. Lambda(bounce,
    double_take) = ln(0.99 / 0.01) = 4.595120; the reverse is its negative. Other fields None: factor 1."""
    ev = count_vector(0.0, None)
    m = member("pr", "B", ev, sub_a="dispenser_bounce", sub_b="double_take")
    lam = P.pair_llr([m], rule)
    assert lam[0] == pytest.approx(math.log((1 - EPS) / EPS), abs=1e-12)
    rev = P.pair_llr(
        [member("pr", "B", ev, sub_a="double_take", sub_b="dispenser_bounce")], rule
    )
    assert rev[0] == pytest.approx(-lam[0], abs=1e-12)
    # a member without evidence has no Lambda (nan), it is not 0
    none = P.pair_llr([dataclasses.replace(m, evidence=None)], rule)
    assert math.isnan(none[0])


def test_llr_is_prior_free() -> None:
    """Changing the class priors and the between-subtype weights changes the posterior but not Lambda (ADR-074 decision 3)."""
    from ralmon.attribution.likelihood import load_likelihood_table

    table = load_likelihood_table(ROOT / "configs" / "attribution_likelihood.yaml")
    ev = count_vector(0.0, 5_000)
    base = build_rule(REGISTRY, table)
    other = build_rule(
        REGISTRY,
        table,
        sensitivity_values={
            **TEST_VALUES,
            "class_priors": "c3_heavy",
            "pi_designs": "quiet_rare",
        },
    )
    rec = make_record("count")
    assert base.posterior_subtypes(rec, ev) != pytest.approx(
        other.posterior_subtypes(rec, ev)
    )
    a = P.pair_llr([member("p", "A", ev)], base)[0]
    b = P.pair_llr([member("p", "A", ev)], other)[0]
    assert a == b  # exactly: the same cells, no prior


def test_identical_streams_give_zero_llr(rule) -> None:  # type: ignore[no-untyped-def]
    """Indistinguishable stratum: both members have the same evidence at the common template, so D = Lambda_A - Lambda_B is
    exactly 0, while Lambda itself is not 0 (the lean of the catalogue and the cells)."""
    ev = count_vector(0.0, 5_000)
    a, b = (
        member("p", "A", ev, indistinguishable=True),
        member("p", "B", ev, indistinguishable=True),
    )
    res = P.pair_result(a, b, rule)
    assert res.d == 0.0
    assert res.lambda_a == res.lambda_b != 0.0
    assert res.d_zero and not res.d_positive
    assert res.indistinguishable


def test_direction_and_pair_statistic(rule) -> None:  # type: ignore[no-untyped-def]
    """Double take (A, subtype double_take) against bounce (B, dispenser_bounce), COUNT. Member A: content_change 1.5 (a release, read D) and
    interval 20 000 ms (above the 10 000 ms test threshold, D). P(e_A | double_take) = (1 - eps)^2 = 0.9801 (both structural
    zeros, D has 1 - eps); P(e_A | bounce) = eps * (1 - (eps + (1 - 2 eps) qc)) = 0.01 * 0.5 = 0.005. Lambda_A =
    ln(0.9801 / 0.005) = 5.278 > 0: right. Member B: content_change 0.0 (A) and interval 5 000 (A): P(e_B | double_take) = eps^2
    = 1e-4; P(e_B | bounce) = (1 - eps)(eps + (1 - 2 eps) qc) = 0.99 * 0.5 = 0.495; Lambda_B = ln(1e-4 / 0.495) = -8.507 < 0:
    right. D = Lambda_A - Lambda_B = 13.785 > 0; both members point the right way."""
    ea, eb = count_vector(1.5, 20_000), count_vector(0.0, 5_000)
    res = P.pair_result(member("p", "A", ea), member("p", "B", eb), rule)
    q = EPS + (1 - 2 * EPS) * QC
    assert res.lambda_a == pytest.approx(
        math.log((1 - EPS) ** 2 / (EPS * (1 - q))), abs=1e-9
    )
    assert res.lambda_b == pytest.approx(
        math.log(EPS * EPS / ((1 - EPS) * q)), abs=1e-9
    )
    assert res.d == pytest.approx(res.lambda_a - res.lambda_b, abs=1e-12)
    assert res.d == pytest.approx(5.278 + 8.507, abs=2e-3)
    assert res.a_right and res.b_right and res.both_right and res.d_positive
    assert not res.d_zero
    # the reverse evidence is the wrong direction for both members
    bad = P.pair_result(member("p", "A", eb), member("p", "B", ea), rule)
    assert not bad.a_right and not bad.b_right and not bad.both_right and bad.d < 0
    # one member right: not both right
    half = P.pair_result(member("p", "A", ea), member("p", "B", ea), rule)
    assert half.a_right and not half.b_right and not half.both_right


def test_pair_strata_summaries(rule) -> None:  # type: ignore[no-untyped-def]
    """Indistinguishable stratum: the distance of Lambda from 0 (|Lambda|) and D = 0 exactly. Distinguishable stratum: the
    direction. NO precision on pairs."""
    same = count_vector(0.0, 5_000)
    ea, eb = count_vector(1.5, 20_000), count_vector(0.0, 5_000)
    pairs = [
        (
            member("i1", "A", same, indistinguishable=True),
            member("i1", "B", same, indistinguishable=True),
        ),
        (
            member("i2", "A", ea, indistinguishable=True),
            member("i2", "B", ea, indistinguishable=True),
        ),
        (member("d1", "A", ea), member("d1", "B", eb)),
        (member("d2", "A", eb), member("d2", "B", ea)),
        (member("d3", "A", ea), member("d3", "B", eb)),
    ]
    results = [P.pair_result(a, b, rule) for a, b in pairs]
    out = P.summarize_strata(results, level=0.95)
    ind, dist = out["indistinguishable"], out["distinguishable"]
    assert ind["n_pairs"] == 2 and ind["n_d_exactly_zero"] == 2
    assert ind["abs_lambda"]["n"] == 4  # both members of both pairs
    lam = [
        abs(results[0].lambda_a),
        abs(results[0].lambda_b),
        abs(results[1].lambda_a),
        abs(results[1].lambda_b),
    ]
    assert ind["abs_lambda"]["mean"] == pytest.approx(sum(lam) / 4)
    assert ind["abs_lambda"]["min"] == pytest.approx(min(lam))
    assert (
        dist["n_pairs"] == 3 and dist["n_both_right"] == 2 and dist["n_d_positive"] == 2
    )
    assert dist["both_right_rate"] == pytest.approx(2 / 3)
    assert dist["both_right_wilson"][0] < 2 / 3 < dist["both_right_wilson"][1]
    assert (
        dist["n_members"] == 6 and dist["n_member_right"] == 4
    )  # d1 and d3 both members, d2 none
    for stratum in (ind, dist):
        assert "precision" not in stratum and "f1" not in stratum


# ---- 7: McNemar -------------------------------------------------------------------------------------------------------


def test_mcnemar_exact_on_discordant_pairs() -> None:
    """x right and y wrong on b = 5 pairs, the reverse on c = 1, both right on 3, both wrong on 2. n = b + c = 6; the two-sided
    exact p is min(1, 2 * P(X <= min(b, c) = 1)) with X ~ Binomial(6, 1/2): (1 + 6) / 64 = 0.109375, twice 0.21875. With b = 8, c = 2:
    n = 10, P(X <= 2) = (1 + 10 + 45) / 1024 = 0.0546875, twice 0.109375. No discordant pair: p = 1."""
    x = [True] * 5 + [False] + [True] * 3 + [False] * 2
    y = [False] * 5 + [True] + [True] * 3 + [False] * 2
    r = P.pair_direction_mcnemar(x, y)
    assert (r["b"], r["c"], r["n_discordant"]) == (5, 1, 6)
    assert r["p"] == pytest.approx(0.21875, abs=1e-12)
    r2 = P.pair_direction_mcnemar([True] * 8 + [False] * 2, [False] * 8 + [True] * 2)
    assert (r2["b"], r2["c"]) == (8, 2)
    assert r2["p"] == pytest.approx(0.109375, abs=1e-12)
    r0 = P.pair_direction_mcnemar([True, False], [True, False])
    assert r0["b"] == r0["c"] == 0 and r0["p"] == 1.0
    assert P.pair_direction_mcnemar([True] * 6, [False] * 6)["p"] == pytest.approx(
        2 / 64
    )
    with pytest.raises(ValueError, match="length"):
        P.pair_direction_mcnemar([True], [True, False])


def test_directions_are_aligned_by_pair_id(rule) -> None:  # type: ignore[no-untyped-def]
    ea, eb = count_vector(1.5, 20_000), count_vector(0.0, 5_000)
    right = P.pair_result(member("d1", "A", ea), member("d1", "B", eb), rule)
    wrong = P.pair_result(member("d2", "A", eb), member("d2", "B", ea), rule)
    other = P.pair_result(member("d3", "A", ea), member("d3", "B", eb), rule)
    x, y, ids = P.align_directions(
        [right, wrong], [dataclasses.replace(wrong, pair_id="d1"), other]
    )
    assert ids == ["d1"] and x == [True] and y == [False]


# ---- sets: coverage and size ------------------------------------------------------------------------------------------


def test_set_coverage_and_size_hand_values() -> None:
    """Four alerts with their own sets (``Alert.cause_set``). RANGE: {a, b} true a (covered, size 2); {a} true b (not covered,
    size 1); SCHED: {c, d, e} true d (covered, size 3); COUNT: {a, b, c, d} true z (not covered, size 4). Overall coverage 2/4,
    mean size 10/4 = 2.5. Per template RANGE 1/2 at size 1.5, SCHED 1/1 at 3, COUNT 0/1 at 4. Per true class: C1 (RANGE, RANGE)
    1/2; C2 (SCHED) 1/1; C3 (COUNT) 0/1. Per true subtype: a 1/1, b 0/1, d 1/1, z 0/1."""
    items = [
        labelled(
            "range",
            (0.5, 0.3, 0.2),
            "C1",
            subtype="a",
            patient="p1",
            cause_set=("a", "b"),
        ),
        labelled(
            "range", (0.5, 0.3, 0.2), "C1", subtype="b", patient="p2", cause_set=("a",)
        ),
        labelled(
            "sched",
            (0.5, 0.3, 0.2),
            "C2",
            subtype="d",
            patient="p1",
            cause_set=("c", "d", "e"),
        ),
        labelled(
            "count",
            (0.5, 0.3, 0.2),
            "C3",
            subtype="z",
            patient="p3",
            cause_set=("a", "b", "c", "d"),
        ),
    ]
    out = S.set_metrics(items, n_resamples=100, level=0.95, seed=0)
    assert out is not None
    g = out["overall"]
    assert (g["n"], g["covered"]) == (4, 2)
    assert g["coverage"] == pytest.approx(0.5) and g["mean_size"] == pytest.approx(2.5)
    assert g["size_counts"] == {"1": 1, "2": 1, "3": 1, "4": 1}
    pt = out["per_template"]
    assert pt["RANGE"]["coverage"] == pytest.approx(0.5) and pt["RANGE"][
        "mean_size"
    ] == pytest.approx(1.5)
    assert pt["SCHED"]["coverage"] == 1.0 and pt["COUNT"]["coverage"] == 0.0
    assert pt["HOLD"] is None  # no alert: undefined, not 0
    pc = out["per_true_class"]
    assert (
        pc["C1"]["coverage"] == pytest.approx(0.5)
        and pc["C2"]["coverage"] == 1.0
        and pc["C3"]["coverage"] == 0.0
    )
    ps = out["per_true_subtype"]
    assert (
        ps["a"]["coverage"] == 1.0 and ps["b"]["coverage"] == 0.0 and ps["z"]["n"] == 1
    )
    assert out["set_source"] == "alert.cause_set"
    lo, hi = out["overall"]["wilson"]
    assert 0.0 < lo < 0.5 < hi < 1.0


def test_a_method_without_sets_is_null_and_the_hierarchical_kappa_is_a_set() -> None:
    """``ours-hier`` has no cause_set: its kappa is scored as a set (kappa C2 -> every subtype of C2 applicable at the template;
    UNDETERMINED -> every applicable subtype). Without the applicable table there is no set and the metric is null."""
    applicable = {
        "range": {
            "C1": ("hypertensive_spike", "spontaneous_range"),
            "C2": ("stuck_at", "cuff_silent_bias"),
            "C3": ("replay",),
        }
    }
    assert S.kappa_as_set("C2", applicable["range"]) == ("stuck_at", "cuff_silent_bias")
    assert S.kappa_as_set("UNDETERMINED", applicable["range"]) == (
        "hypertensive_spike",
        "spontaneous_range",
        "stuck_at",
        "cuff_silent_bias",
        "replay",
    )
    hier = [
        labelled("range", None, "C2", subtype="stuck_at", kappa=C2),
        labelled(
            "range",
            None,
            "C1",
            subtype="hypertensive_spike",
            kappa=AttributedCause.UNDETERMINED,
        ),
        labelled("range", None, "C1", subtype="hypertensive_spike", kappa=C2),
    ]
    out = S.set_metrics(
        hier, applicable=applicable, n_resamples=100, level=0.95, seed=0
    )
    assert out is not None and out["set_source"] == "kappa_as_set"
    assert out["overall"]["covered"] == 2 and out["overall"][
        "mean_size"
    ] == pytest.approx((2 + 5 + 2) / 3)
    assert S.set_metrics(hier, n_resamples=100, level=0.95, seed=0) is None
    assert S.set_metrics([], n_resamples=100, level=0.95, seed=0) is None


def test_coverage_per_patient_cluster_bootstrap() -> None:
    """Patient P1: 4 alerts, 4 covered; P2: 4 alerts, 0 covered; P3: 2 alerts, 2 covered. Pooled coverage 6/10; per-patient
    coverages 1.0, 0.0, 1.0 (median 1.0). The cluster bootstrap resamples PATIENTS: the interval is deterministic for a seed, lies in
    [0, 1], contains the pooled coverage, and is wider than the Wilson interval over alerts would be (the alerts of a patient are
    correlated). With all alerts covered the interval is [1, 1]."""
    items: list[T.LabelledAlert] = []
    for patient, n, covered in (("P1", 4, 4), ("P2", 4, 0), ("P3", 2, 2)):
        for i in range(n):
            items.append(
                labelled(
                    "range",
                    (0.5, 0.3, 0.2),
                    "C1",
                    subtype="a",
                    patient=patient,
                    cause_set=("a",) if i < covered else ("b",),
                )
            )
    out = S.set_metrics(items, n_resamples=200, level=0.9, seed=3)
    assert out is not None
    pp = out["per_patient"]
    assert pp["n_patients"] == 3
    assert pp["coverage_by_patient"] == {"P1": 1.0, "P2": 0.0, "P3": 1.0}
    assert pp["median_coverage"] == 1.0
    boot = out["cluster_bootstrap"]
    assert (
        boot["unit"] == "patient"
        and boot["n_resamples"] == 200
        and boot["level"] == 0.9
    )
    lo, hi = boot["coverage"]
    assert 0.0 <= lo <= 0.6 <= hi <= 1.0
    wlo, whi = out["overall"]["wilson"]
    assert (hi - lo) > (whi - wlo)
    again = S.set_metrics(items, n_resamples=200, level=0.9, seed=3)
    assert again is not None and again["cluster_bootstrap"] == boot
    all_in = [
        dataclasses.replace(i, alert=dataclasses.replace(i.alert, cause_set=("a",)))
        for i in items
    ]
    full = S.set_metrics(all_in, n_resamples=200, level=0.9, seed=3)
    assert full is not None and full["cluster_bootstrap"]["coverage"] == [1.0, 1.0]
    one = S.set_metrics(items[:4], n_resamples=200, level=0.9, seed=3)
    assert one is not None and one["cluster_bootstrap"]["coverage"] == [
        None,
        None,
    ]  # one patient: no interval


# ---- equal coverage ---------------------------------------------------------------------------------------------------

POST_LIK = {"a": 0.6, "b": 0.3, "c": 0.1}
POST_PRIOR = {"a": 0.5, "b": 0.25, "c": 0.25}
POST_SCHED = {"a": 0.6, "b": 0.4}


def item(
    patient: str,
    template: str,
    truth: str,
    post: Mapping[str, float],
    prior: Mapping[str, float],
    fixed: tuple[str, ...] | None = None,
) -> T.LabelledAlert:
    fixed_sets = {} if fixed is None else {"hier": fixed}
    return labelled(
        template,
        (0.5, 0.3, 0.2),
        "C1",
        subtype=truth,
        patient=patient,
        inputs=T.AlertInputs({"lik": post, "prior": prior}, fixed_sets, None),
    )


def calibration_part() -> list[T.LabelledAlert]:
    """Nine alerts at RANGE (truths a x6, b x2, c x1) and two at SCHED (truth a)."""
    truths = ["a"] * 6 + ["b"] * 2 + ["c"]
    out = [
        item(f"c{i + 1}", "range", t, POST_LIK, POST_PRIOR, ("a", "b"))
        for i, t in enumerate(truths)
    ]
    out += [
        item(f"s{i + 1}", "sched", "a", POST_SCHED, POST_SCHED, ("a", "b"))
        for i in range(2)
    ]
    return out


def make_test_part() -> list[T.LabelledAlert]:
    truths = ["a", "b", "c", "a"]
    out = [
        item(f"t{i + 1}", "range", t, POST_LIK, POST_PRIOR, ("a", "b"))
        for i, t in enumerate(truths)
    ]
    out.append(item("t5", "sched", "b", POST_SCHED, POST_SCHED, ("a", "b")))
    return out


def run_equal(**kw: Any) -> dict[str, Any]:
    args: dict[str, Any] = {
        "methods": ("lik", "prior"),
        "alphas": (0.2,),
        "model_version": "m1",
        "population": "main",
    }
    args.update(kw)
    return S.equal_coverage(calibration_part(), make_test_part(), **args)


def test_equal_coverage_comparison_hand_values() -> None:
    """Calibration scores 1 - p(true): method ``lik`` (posterior a .6, b .3, c .1): a -> 0.4 (x6), b -> 0.7 (x2), c -> 0.9, and
    SCHED (a .6, b .4) -> 0.4 (x2). Marginal alpha 0.2 pools n = 11, k = ceil(12 * 0.8) = 10, the 10th smallest of
    [0.4 x8, 0.7, 0.7, 0.9] is 0.7: the set is every subtype with 1 - p <= 0.7, {a, b} (c has 0.9). Test (truths a, b, c, a at
    RANGE, b at SCHED): RANGE sets {a, b} cover a, b, a but not c; SCHED {a, b} (scores 0.4, 0.6) covers b: coverage 4/5, mean
    size 2. The ``prior`` method (a .5, b .25, c .25; scores a 0.5 x6, b 0.75 x2, c 0.75; SCHED a .6, b .4: 0.4 x2) has threshold
    the 10th smallest of [0.4 x2, 0.5 x6, 0.75 x3] = 0.75: sets of size 3 at RANGE and {a, b} at SCHED, coverage 5/5, mean
    size (3 x 4 + 2) / 5 = 2.8."""
    out = run_equal()
    lik = out["methods"]["lik"]["alphas"]["0.2"]["marginal"]
    assert (lik["n"], lik["covered"]) == (5, 4)
    assert lik["coverage"] == pytest.approx(0.8) and lik["mean_size"] == pytest.approx(
        2.0
    )
    assert lik["per_template"]["RANGE"]["coverage"] == pytest.approx(0.75)
    assert lik["per_template"]["SCHED"]["coverage"] == 1.0
    prior = out["methods"]["prior"]["alphas"]["0.2"]["marginal"]
    assert prior["coverage"] == 1.0 and prior["mean_size"] == pytest.approx(2.8)
    # at the same alpha the likelihood sets are smaller than the prior-only sets
    assert lik["mean_size"] < prior["mean_size"]
    assert (
        out["population"] == "main"
        and out["n_calibration"] == 11
        and out["n_test"] == 5
    )
    thr = out["methods"]["lik"]["alphas"]["0.2"]["marginal"]["threshold"]
    assert (
        thr["value"] == pytest.approx(0.7)
        and thr["fallback"] is False
        and thr["n"] == 11
    )


def test_the_hierarchical_kappa_set_is_compared_at_its_own_coverage() -> None:
    """The hierarchical rule's kappa has no threshold to tune: its fixed set ({a, b} for every alert here) has coverage 10/11 on
    the calibration part (truths a x8, b x2 are in; c is not) and 4/5 on the test part, mean size 2. The calibrated methods are
    then compared at alpha = 1 - 10/11 = 1/11 (a Fraction, exact): k = ceil(12 * 10/11) = 11, the largest calibration score
    (0.9 for ``lik``, 0.75 for ``prior``), so both give sets of size 3 at RANGE and {a, b} at SCHED: coverage 5/5, mean size
    (3 x 4 + 2) / 5 = 2.8."""
    out = run_equal()
    fixed = out["fixed"]["hier"]
    assert fixed["calibration"]["covered"] == 10 and fixed["calibration"]["n"] == 11
    assert fixed["test"]["covered"] == 4 and fixed["test"][
        "mean_size"
    ] == pytest.approx(2.0)
    assert fixed["alpha_at_calibration_coverage"] == "1/11"
    at = fixed["methods_at_alpha"]["lik"]["marginal"]
    assert (
        at["n"] == 5 and at["coverage"] == 1.0 and at["mean_size"] == pytest.approx(2.8)
    )
    assert fixed["methods_at_alpha"]["prior"]["marginal"]["mean_size"] == pytest.approx(
        2.8
    )


def test_mondrian_reports_the_fallback_and_top1_fill_per_template() -> None:
    """Mondrian per template at alpha 0.2: RANGE has 9 calibration alerts (finite threshold 0.7), SCHED only 2, below the 4 that a
    finite rank needs at this level: the full set of the applicable subtypes, flagged as a fallback with its reason, so the
    threshold is written null with ``fallback`` true (inf is not valid JSON)."""
    out = run_equal(modes=("marginal", "mondrian"))
    m = out["methods"]["lik"]["alphas"]["0.2"]["mondrian"]
    assert m["per_template"]["SCHED"]["n_full_set_fallback"] == 1
    assert m["per_template"]["SCHED"]["full_set_fallback_share"] == 1.0
    assert m["per_template"]["RANGE"]["full_set_fallback_share"] == 0.0
    thr = m["thresholds"]
    assert thr["SCHED"]["value"] is None and thr["SCHED"]["fallback"] is True
    assert "calibration alerts" in thr["SCHED"]["reason"]
    assert thr["RANGE"]["value"] == pytest.approx(0.7) and thr["RANGE"]["n"] == 9
    assert m["n_full_set_fallback"] == 1
    import json

    json.dumps(out, allow_nan=False)  # valid JSON: no inf, no Fraction


def test_top1_fill_is_counted_per_template() -> None:
    """Nine calibration alerts, posterior a .9 / b .1, truth a: every score is 1 - 0.9 and the threshold is that score. A test
    alert with posterior a .3 / b .7 has scores 0.7 and 0.3, both above it: the pure rule gives an empty set, the calibrator adds
    the most probable subtype (b) and flags it: top1_fill share 1 at RANGE, coverage 0 (truth a)."""
    cal = [
        item(f"c{i}", "range", "a", {"a": 0.9, "b": 0.1}, {"a": 0.9, "b": 0.1})
        for i in range(9)
    ]
    test = [item("t1", "range", "a", {"a": 0.3, "b": 0.7}, {"a": 0.3, "b": 0.7})]
    out = S.equal_coverage(
        cal,
        test,
        methods=("lik",),
        alphas=(0.2,),
        model_version="m1",
        population="main",
    )
    cell = out["methods"]["lik"]["alphas"]["0.2"]["marginal"]
    assert cell["per_template"]["RANGE"]["n_top1_fill"] == 1
    assert cell["per_template"]["RANGE"]["top1_fill_share"] == 1.0
    assert cell["covered"] == 0 and cell["mean_size"] == 1.0
    assert cell["n_top1_fill"] == 1


def test_calibration_and_test_patients_must_be_disjoint() -> None:
    cal = calibration_part()
    test = make_test_part()
    test[0] = dataclasses.replace(test[0], patient_id="c1")
    with pytest.raises(PatientLeakError):
        S.equal_coverage(
            cal,
            test,
            methods=("lik",),
            alphas=(0.2,),
            model_version="m1",
            population="main",
        )


def test_a_true_subtype_outside_the_applicable_set_is_counted() -> None:
    """The ground truth can name a subtype that is not a key of the posterior (not applicable at the template): the score is 1,
    the set never contains it, and the count is reported (``n_true_not_applicable``)."""
    cal = [
        item(f"c{i}", "range", "zz" if i == 0 else "a", POST_LIK, POST_PRIOR)
        for i in range(9)
    ]
    test = [item("t1", "range", "zz", POST_LIK, POST_PRIOR)]
    out = S.equal_coverage(
        cal,
        test,
        methods=("lik",),
        alphas=(0.2,),
        model_version="m1",
        population="main",
    )
    assert out["n_calibration_true_not_applicable"] == 1
    assert out["n_test_true_not_applicable"] == 1


# ---- the pairs get a separate calibration -----------------------------------------------------------------------------


def test_pair_calibration_is_separate() -> None:
    """The pair population has its own SubtypeSetCalibrator instance (population ``pairs``), fitted on the calibration part of the
    pairs; the main-population instance evaluated on the same pair test alerts is the transfer, reported next to it. Main
    calibration: posterior a .6 / b .3 / c .1, truth a x6, b x2, c x1 (scores 0.4 x6, 0.7 x2, 0.9: threshold 0.7 at
    alpha 0.2). Pairs calibration: ten alerts with truth c (score 0.9 each; k = ceil(11 * 0.8) = 9): threshold 0.9, so the pair sets are {a, b, c}
    and they cover the pair test alerts (truth c) while the transferred sets {a, b} do not."""
    main_cal = [
        item(f"c{i + 1}", "range", t, POST_LIK, POST_PRIOR)
        for i, t in enumerate(["a"] * 6 + ["b"] * 2 + ["c"])
    ]
    pair_cal = [item(f"pc{i}", "range", "c", POST_LIK, POST_PRIOR) for i in range(10)]
    pair_test = [item(f"pt{i}", "range", "c", POST_LIK, POST_PRIOR) for i in range(4)]
    out = S.pair_set_calibration(
        main_cal,
        pair_cal,
        pair_test,
        methods=("lik",),
        alphas=(0.2,),
        model_version="m1",
    )
    sep, tr = out["separate"], out["transfer_from_main"]
    assert sep["population"] == "pairs" and tr["population"] == "main"
    s = sep["methods"]["lik"]["alphas"]["0.2"]["marginal"]
    t = tr["methods"]["lik"]["alphas"]["0.2"]["marginal"]
    assert s["threshold"]["value"] == pytest.approx(0.9) and t["threshold"][
        "value"
    ] == pytest.approx(0.7)
    assert s["coverage"] == 1.0 and t["coverage"] == 0.0
    assert s["mean_size"] == 3.0 and t["mean_size"] == 2.0
    assert sep["n_calibration"] == 10 and tr["n_calibration"] == 9
    assert "why" in out and "prevalence" in out["why"]


# ---- the statements of the metadata ----------------------------------------------------------------------------------


def test_the_metadata_statements_are_qualified() -> None:
    """The exchangeability statement is marginal, exact only for one alert per patient and approximate otherwise; the phrase
    'distribution-free coverage' never appears without its qualification; the guard strings are copied from the set builder."""
    from ralmon.conformal.sets import (
        ASSUMPTIONS_SETS,
        GUARANTEE_SETS,
        GUARANTEE_SETS_MONDRIAN,
    )

    meta = S.sets_metadata()
    text = " ".join(str(v) for v in meta.values()).lower()
    assert (
        "marginal" in text
        and "one designated alert per patient" in text
        and "approximate" in text
    )
    assert "distribution-free" not in text.replace("never claimed", "")
    assert meta["guarantee_marginal"] == GUARANTEE_SETS
    assert meta["guarantee_mondrian"] == GUARANTEE_SETS_MONDRIAN
    assert tuple(meta["assumptions"]) == tuple(ASSUMPTIONS_SETS)
    assert "top1_fill" in meta and "full_set_fallback" in meta
    assert meta["cell_scope"]["status"] == "not implemented"
    assert meta["family"]["status"] == "not implemented"
    assert (
        "decided after" in meta["labelling"]["choice"]
        or "after seeing" in meta["labelling"]["choice"]
    )
    assert (
        meta["labelling"]["primary"] == "tight"
        and meta["labelling"]["reported_next_to_it"] == "loose"
    )


# ---- matching of the pair members ---------------------------------------------------------------------------------------


def test_pair_members_are_matched_by_template_and_onset() -> None:
    """Member A (double take, a C1 event of COUNT at 20:00) can only be matched to a COUNT alert decided at or after 20:00; member B
    (bounce at 20:00, templates count, hold, resp, int) to an alert of any of those. The common template is COUNT, the only one
    both can violate: A's earliest alert there is 20:00:10 (the 19:00 one is before the onset), B's is 20:00:20 (its HOLD alert at
    20:00:05 is on another template). A member without an injected event of the group has no match; a presence_spoof is a co-event
    and is not the mechanism."""
    group = "double_take_vs_bounce"
    ev_a = [
        event("C1", "double_take", 20 * HOUR, None, "count", injected=True, group=group)
    ]
    ev_b = [
        event(
            "C2", "dispenser_bounce", 20 * HOUR, None, None, injected=True, group=group
        ),
        event(
            "C3", "presence_spoof", 20 * HOUR, None, None, injected=True, group=group
        ),
    ]
    ctx_b = [
        T.EventContext(("count", "hold", "resp", "int"), "dispenser"),
        T.EventContext(("int",), None),
    ]
    alerts_a = [
        p_alert(19 * HOUR, "count", (0.3, 0.4, 0.3), key="early"),
        p_alert(20 * HOUR + 10_000, "count", (0.3, 0.4, 0.3), key="a1"),
        p_alert(20 * HOUR + 5_000, "resp", (0.3, 0.4, 0.3), key="wrong-template"),
    ]
    alerts_b = [
        p_alert(20 * HOUR + 20_000, "count", (0.3, 0.4, 0.3), key="b2"),
        p_alert(20 * HOUR + 5_000, "hold", (0.3, 0.4, 0.3), key="b1"),
    ]
    ma = P.match_member(ev_a, None, alerts_a, group=group)
    mb = P.match_member(ev_b, ctx_b, alerts_b, group=group)
    assert ma is not None and mb is not None
    assert ma.event.subtype == "double_take" and mb.event.subtype == "dispenser_bounce"
    assert [a.xi.instance_key for a in ma.candidates] == ["a1"]
    assert [a.xi.instance_key for a in mb.candidates] == [
        "b1",
        "b2",
    ]  # by decision time
    got = P.common_match(ma, mb)
    assert got is not None
    template, left, right = got
    assert (template, left.xi.instance_key, right.xi.instance_key) == (
        "count",
        "a1",
        "b2",
    )
    assert P.match_member([], None, alerts_a, group=group) is None
    assert P.match_member(ev_a, None, alerts_a, group="another_group") is None
    only_hold = P.match_member(ev_b, ctx_b, [alerts_b[1]], group=group)
    assert (
        only_hold is not None and P.common_match(ma, only_hold) is None
    )  # no common alert: no pair
    # the primary template of the group goes first when several templates are shared
    wide = P.MemberMatch(
        ma.event,
        0,
        ("count", "hold"),
        (alerts_a[1], p_alert(20 * HOUR + 30_000, "hold", None, key="a2")),
    )
    both = P.common_match(wide, mb, primary="hold")
    assert both is not None and both[0] == "hold"


# ---- the inputs a detector hands to the scoring side ------------------------------------------------------------------------


def test_alert_inputs_from_the_rule_give_the_posterior_the_prior_and_the_kappa_set(
    rule,
) -> None:  # type: ignore[no-untyped-def]
    """``lik`` is the rule's posterior; ``prior`` the same rule on an evidence vector with every field unavailable (factor 1), so it is
    ``prior_t(class) * pi``: at COUNT with the uniform designs the C1 components (3) share 1/3, the C2 (5) 1/3 and the C3 (3
    components, two of them the levels of ``dispense_forgery``) 1/3 (`dispense_forgery` has two components, so 2/9 of the C3 mass).
    The hierarchical kappa C2 as a set is every C2 subtype applicable at COUNT; UNDETERMINED every applicable subtype."""
    ev = count_vector(0.0, 5_000)
    rec = make_record("count")
    got = S.alert_inputs_from_rule(rule, rec, ev, hierarchical_kappa="C2")
    assert got.posteriors["lik"] == pytest.approx(
        dict(rule.posterior_subtypes(rec, ev))
    )
    prior = got.posteriors["prior"]
    assert sum(prior.values()) == pytest.approx(1.0)
    assert prior["double_take"] == pytest.approx(1 / 9)
    assert prior["dispenser_bounce"] == pytest.approx(1 / 15)
    assert prior["dispense_forgery"] == pytest.approx(2 / 9)
    assert prior["dispenser_physical_tamper"] == pytest.approx(1 / 9)
    assert got.fixed_sets["hier"] == (
        "ble_dropout",
        "dispenser_bounce",
        "message_drop",
        "process_kill",
        "uncommanded_lifecycle_transition",
    )
    assert got.evidence is ev
    und = S.alert_inputs_from_rule(rule, rec, ev, hierarchical_kappa="UNDETERMINED")
    assert set(und.fixed_sets["hier"]) == set(prior)
    assert S.alert_inputs_from_rule(rule, rec, ev).fixed_sets == {}


def test_wilson_interval_hand_value() -> None:
    """k = 5 of n = 10 at 0.95: centre 0.5, half width z sqrt(0.025 + z^2 / 400) / (1 + z^2 / 10) = 0.2634, so [0.2366, 0.7634]."""
    lo, hi = S.wilson_interval(5, 10, 0.95)
    assert lo == pytest.approx(0.2366, abs=2e-4) and hi == pytest.approx(
        0.7634, abs=2e-4
    )
    assert all(math.isnan(x) for x in S.wilson_interval(0, 0, 0.95))
    assert S.wilson_interval(0, 5, 0.95)[0] == pytest.approx(0.0, abs=1e-12)
    assert S.wilson_interval(5, 5, 0.95)[1] == pytest.approx(1.0, abs=1e-12)


def test_the_static_c3_table_agrees_with_the_likelihood_catalogue(table) -> None:  # type: ignore[no-untyped-def]
    """The templates a C3 subtype can change (the injection log of a C3 record lists none) are those of the components of the
    likelihood table, over the knowledge levels of the subtype."""
    by_subtype: dict[str, set[str]] = {}
    for component in table.components:
        if component.cls == "C3":
            by_subtype.setdefault(component.subtype, set()).update(component.templates)
    assert {k: set(v) for k, v in T.C3_EVENT_TEMPLATES.items()} == by_subtype


def test_scores_on_a_real_alert_of_the_likelihood_rule(rule) -> None:  # type: ignore[no-untyped-def]
    """End to end with the real attributor: a COUNT alert of ``RuleAttributor(rule=LikelihoodRule)`` carries ``p_kappa`` (keys are
    ``AttributedCause``) and a cumulative-level ``cause_set``; its log score against a C2 cause is ``-ln p_kappa[C2]``, and a
    double take (C1) event at the alert's instant makes the C1 posterior the one that is scored."""
    from ralmon.attribution import RuleAttributor
    from ralmon.spec import load_templates

    record = make_record("count", decided_at_ms=20 * HOUR + 5_000)
    evidence = count_vector(0.0, 5_000)
    attributor = RuleAttributor(REGISTRY, load_templates(registry=REGISTRY), rule=rule)
    (real,) = attributor.attribute_all([record], {record.instance_key: evidence})
    assert real.p_kappa is not None and real.cause_set is not None
    bounce = event("C2", "ble_dropout", 20 * HOUR, 21 * HOUR, None, injected=True)
    res = _label(
        [bounce],
        [real],
        [T.EventContext(("count",), "dispenser")],
        "tight",
        patient_id="p",
    )
    assert [x.true_class for x in res.labelled] == ["C2"]
    ls = M.attribution_log_score(res.labelled)
    assert ls is not None
    assert ls["COUNT"] == pytest.approx(-math.log(real.p_kappa[C2]), abs=1e-12)
    double_take = event("C1", "double_take", 20 * HOUR, None, "count", injected=True)
    c1 = _label([double_take], [real], None, "tight", patient_id="p")
    ls1 = M.attribution_log_score(c1.labelled)
    assert ls1 is not None and ls1["COUNT"] == pytest.approx(
        -math.log(real.p_kappa[C1]), abs=1e-12
    )
    br = M.attribution_brier(c1.labelled)
    expected = sum(
        (real.p_kappa[c] - (1.0 if c is C1 else 0.0)) ** 2 for c in (C1, C2, C3)
    )
    assert br is not None and br["COUNT"] == pytest.approx(expected, abs=1e-12)
    sets = S.set_metrics(c1.labelled, n_resamples=100, level=0.95, seed=0)
    assert sets is not None and sets["overall"]["n"] == 1


def test_a_point_c2_event_is_the_tight_cause_only_at_its_own_instant() -> None:
    """A C2 event with no window (``end_ms`` None: the extra opening of a ``dispenser_bounce``) is active only at its onset: under the
    TIGHT labelling an alert decided later (the COUNT alert of a bounce is decided at the next dose step) is not caused by it, under the
    LOOSE one it is, within the allowance. This is the reading of the ADR ('decided while the event window is active') and of the
    research prototype, which kept only 3 bounce alerts under the tight labelling; the consequence is reported in the Notes."""
    bounce = event("C2", "dispenser_bounce", 20 * HOUR, None, None)
    ctx = [T.EventContext(("count", "hold", "resp", "int"), "dispenser")]
    at = p_alert(20 * HOUR, "count", (0.2, 0.7, 0.1))
    later = p_alert(20 * HOUR + 30_000, "count", (0.2, 0.7, 0.1))
    assert len(_label([bounce], [at], ctx, "tight").labelled) == 1
    assert _label([bounce], [later], ctx, "tight").labelled == ()
    assert len(_label([bounce], [later], ctx, "loose").labelled) == 1
