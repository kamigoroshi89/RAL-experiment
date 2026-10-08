"""``rank_alerts`` (02-interfaces.md#template, ADR-028, docs/formal/04-normalisation-ranking.md section 4).

Order key ``K0 = (priority, sigma_norm, t_ms, instance_key)``, ascending, priority 1 first, stable.
Tests 6 to 9 of WS05-T03 with tests 7 and 9 adapted to ADR-028 (the tie-break and the structural
Protocol that also reads ``t_ms`` and ``instance_key``), the golden cases RK-1 to RK-6 and the properties
P-R1 to P-R6.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ralmon.spec import normalise, rank_alerts

from .helpers import GOLDEN_RANKING_COPY, read_yaml

RANKING = read_yaml(GOLDEN_RANKING_COPY)
RK_CASES = [case for case in RANKING if case["id"].startswith("RK-")]


@dataclass(frozen=True)
class FlatAlert:
    """The four fields K0 reads, flat (the shape of the golden file)."""

    priority: int
    sigma_norm: float
    t_ms: int
    instance_key: str
    tag: str = ""  # not read by rank_alerts: tells apart alerts with equal keys


@dataclass(frozen=True)
class _Xi:
    instance_key: str


@dataclass(frozen=True)
class NestedAlert:
    """The shape of ``Alert`` of #alert: the instance key is ``xi.instance_key``."""

    priority: int
    sigma_norm: float
    t_ms: int
    xi: _Xi
    tag: str = ""


def keys(alerts: Sequence[Any]) -> list[str]:
    return [a.instance_key for a in alerts]


# --- test 6 ------------------------------------------------------------------------------


def test_rank_alerts_priority_then_sigma_ascending() -> None:
    sched = FlatAlert(3, -0.9, 0, "sched")
    range_b = FlatAlert(2, -0.2, 0, "range@-0.2")
    hold = FlatAlert(1, -0.3, 0, "hold")
    range_a = FlatAlert(2, -0.6, 0, "range@-0.6")
    ordered = rank_alerts([sched, range_b, hold, range_a])
    assert ordered == [hold, range_a, range_b, sched]
    # the most negative sigma is last only because its priority is the lowest
    assert min(a.sigma_norm for a in ordered) == ordered[-1].sigma_norm


def test_rank_alerts_returns_a_new_list_and_leaves_the_input_alone() -> None:
    original = [FlatAlert(2, -0.1, 5, "b"), FlatAlert(1, -0.1, 5, "a")]
    snapshot = list(original)
    ordered = rank_alerts(original)
    assert original == snapshot
    assert ordered is not original
    assert isinstance(ordered, list)
    assert rank_alerts(tuple(original)) == ordered
    assert rank_alerts([]) == []
    assert rank_alerts(()) == []


# --- test 7, adapted to ADR-028 ----------------------------------------------------------


def test_rank_alerts_breaks_ties_by_time_then_instance_key() -> None:
    """Equal ``(priority, sigma_norm)``: ``t_ms`` ascending, then ``instance_key`` (RK-3 shapes)."""
    later_but_smaller_key = FlatAlert(2, -0.6, 100, "a")
    earlier = FlatAlert(2, -0.6, 50, "b")
    assert rank_alerts([later_but_smaller_key, earlier]) == [
        earlier,
        later_but_smaller_key,
    ]
    b = FlatAlert(2, -0.6, 100, "b")
    a = FlatAlert(2, -0.6, 100, "a")
    assert rank_alerts([b, a]) == [a, b]
    assert rank_alerts([a, b]) == [a, b]


def test_rank_alerts_is_stable_on_equal_keys() -> None:
    """Only a full tie (all four key components) keeps the input order."""
    first = FlatAlert(2, -0.6, 100, "k", tag="first")
    second = FlatAlert(2, -0.6, 100, "k", tag="second")
    third = FlatAlert(2, -0.6, 100, "k", tag="third")
    assert [a.tag for a in rank_alerts([first, second, third])] == [
        "first",
        "second",
        "third",
    ]
    assert [a.tag for a in rank_alerts([third, first, second])] == [
        "third",
        "first",
        "second",
    ]


def test_rank_alerts_treats_negative_zero_as_zero() -> None:
    plus = FlatAlert(1, 0.0, 10, "z", tag="plus")
    minus = FlatAlert(1, -0.0, 10, "z", tag="minus")
    assert [a.tag for a in rank_alerts([plus, minus])] == ["plus", "minus"]
    assert [a.tag for a in rank_alerts([minus, plus])] == ["minus", "plus"]


# --- test 9, adapted to ADR-028 ----------------------------------------------------------


def test_rank_alerts_accepts_any_object_with_the_four_read_fields() -> None:
    """Structural typing: a local class with exactly ``priority``, ``sigma_norm``, ``t_ms`` and
    ``instance_key`` is accepted, and so is the shape of ``Alert`` (``xi.instance_key``); the module never
    imports ``ralmon.attribution``."""

    @dataclass(frozen=True)
    class Local:
        priority: int
        sigma_norm: float
        t_ms: int
        instance_key: str

    flat = rank_alerts([Local(2, -0.1, 1, "x"), Local(1, -0.1, 1, "y")])
    assert [a.instance_key for a in flat] == ["y", "x"]
    nested = rank_alerts(
        [
            NestedAlert(2, -0.1, 1, _Xi("x")),
            NestedAlert(1, -0.1, 1, _Xi("y")),
        ]
    )
    assert [a.xi.instance_key for a in nested] == ["y", "x"]
    namespace = rank_alerts(
        [
            SimpleNamespace(priority=2, sigma_norm=-0.1, t_ms=1, instance_key="x"),
            SimpleNamespace(priority=1, sigma_norm=-0.1, t_ms=1, instance_key="y"),
        ]
    )
    assert [a.instance_key for a in namespace] == ["y", "x"]


def test_rank_alerts_reads_xi_instance_key_first() -> None:
    both = SimpleNamespace(
        priority=1,
        sigma_norm=-0.1,
        t_ms=1,
        instance_key="flat-z",
        xi=SimpleNamespace(instance_key="nested-a"),
    )
    other = SimpleNamespace(
        priority=1,
        sigma_norm=-0.1,
        t_ms=1,
        instance_key="flat-a",
        xi=SimpleNamespace(instance_key="nested-z"),
    )
    assert rank_alerts([other, both]) == [both, other]  # nested keys decide: a < z


def test_rank_alerts_does_not_read_other_fields() -> None:
    """Nothing but the four fields is read: no kappa, no rho, no verdict (K0, not K1)."""
    plain = SimpleNamespace(priority=1, sigma_norm=-0.1, t_ms=1, instance_key="a")
    with_extras = SimpleNamespace(
        priority=1,
        sigma_norm=-0.2,
        t_ms=2,
        instance_key="b",
        kappa=object(),
        rho=object(),
        verdict="predicted_violation",
    )
    assert rank_alerts([plain, with_extras]) == [with_extras, plain]


# --- golden cases RK-1 to RK-6 -----------------------------------------------------------


def alert_from(raw: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(**raw)


def instance_keys(alerts: Sequence[SimpleNamespace]) -> list[str]:
    return [a.instance_key for a in alerts]


@pytest.mark.parametrize("case", RK_CASES, ids=[c["id"] for c in RK_CASES])
def test_rank_alerts_matches_ranking_golden(case: dict[str, Any]) -> None:
    inputs, expected = case["inputs"], case["expected"]
    assert inputs["call"] == "rank_alerts"
    cid = case["id"]
    if cid == "RK-1":
        assert (
            instance_keys(rank_alerts([alert_from(a) for a in inputs["alerts"]]))
            == expected["order"]
        )
    elif cid == "RK-2":
        main = rank_alerts([alert_from(a) for a in inputs["alerts"]])
        swapped = rank_alerts([alert_from(a) for a in inputs["alerts_swapped_times"]])
        assert instance_keys(main) == expected["order"]
        assert instance_keys(swapped) == expected["order_swapped_times"]
    elif cid == "RK-3":
        for name in ("call_1", "call_2"):
            ranked = rank_alerts([alert_from(a) for a in inputs[name]])
            assert instance_keys(ranked) == expected[name]
    elif cid == "RK-4":
        alerts = [alert_from(a) for a in inputs["alerts"]]
        assert instance_keys(rank_alerts(alerts)) == expected["lexicographic"]
        for (
            a
        ) in alerts:  # the stored sigma_norm is normalise(raw, scale) of the same case
            assert normalise(a.raw, a.scale) == a.sigma_norm
    elif cid == "RK-5":
        ranked = instance_keys(rank_alerts([alert_from(a) for a in inputs["alerts"]]))
        # K0 is implemented (ADR-028 accepted); K1 (ADR-050) is only proposed
        assert ranked == expected["literal_contract"]
        assert ranked != expected["recommended_extension"]
    elif cid == "RK-6":
        ranked = instance_keys(rank_alerts([alert_from(a) for a in inputs["alerts"]]))
        assert ranked == expected["order"]
        assert ranked != expected["forbidden_order"]
    else:  # a new case in the golden file must get its own check
        pytest.fail(f"unhandled golden ranking case {cid}")


def test_every_golden_ranking_case_is_collected() -> None:
    assert [c["id"] for c in RK_CASES] == [f"RK-{i}" for i in range(1, 7)]


# --- properties P-R1 to P-R6 -------------------------------------------------------------

ALERT = st.builds(
    FlatAlert,
    priority=st.integers(min_value=1, max_value=4),
    sigma_norm=st.sampled_from([-1.0, -0.5, -0.0, 0.0, 0.25, 1.0]),
    t_ms=st.integers(min_value=-2, max_value=3),
    instance_key=st.sampled_from(["a", "b", "c"]),
    tag=st.text(alphabet="xyz", max_size=2),
)
ALERTS = st.lists(ALERT, max_size=12)


def key_of(a: FlatAlert) -> tuple[int, float, int, str]:
    return (a.priority, a.sigma_norm, a.t_ms, a.instance_key)


@settings(max_examples=150)
@given(alerts=ALERTS)
def test_rank_alerts_permutation_and_lexicographic_property(
    alerts: list[FlatAlert],
) -> None:
    out = rank_alerts(alerts)
    assert sorted(out, key=lambda a: (key_of(a), a.tag)) == sorted(
        alerts, key=lambda a: (key_of(a), a.tag)
    )  # P-R1: a permutation
    assert len(out) == len(alerts)
    for i in range(len(out)):
        for j in range(i + 1, len(out)):
            assert out[i].priority <= out[j].priority  # P-R2: priority first
            if out[i].priority == out[j].priority:
                assert out[i].sigma_norm <= out[j].sigma_norm  # P-R3
            assert key_of(out[i]) <= key_of(out[j])


@settings(max_examples=150)
@given(alerts=ALERTS, seed=st.integers(min_value=0, max_value=1000))
def test_rank_alerts_is_independent_of_input_order_when_keys_are_distinct(
    alerts: list[FlatAlert], seed: int
) -> None:
    distinct = list({key_of(a): a for a in alerts}.values())  # P-R4
    shuffled = list(distinct)
    random.Random(seed).shuffle(shuffled)
    assert rank_alerts(shuffled) == rank_alerts(distinct)


@settings(max_examples=150)
@given(alerts=ALERTS)
def test_rank_alerts_is_idempotent_and_stable(alerts: list[FlatAlert]) -> None:
    once = rank_alerts(alerts)
    assert rank_alerts(once) == once  # P-R5
    for key in {key_of(a) for a in alerts}:  # P-R6: equal keys keep input order
        assert [a.tag for a in once if key_of(a) == key] == [
            a.tag for a in alerts if key_of(a) == key
        ]


@settings(max_examples=100)
@given(alerts=ALERTS)
def test_rank_alerts_equals_a_sort_by_the_documented_key(
    alerts: list[FlatAlert],
) -> None:
    assert rank_alerts(alerts) == sorted(alerts, key=key_of)


@settings(max_examples=100)
@given(alerts=ALERTS)
def test_rank_alerts_nested_and_flat_shapes_agree(alerts: list[FlatAlert]) -> None:
    nested = [
        NestedAlert(a.priority, a.sigma_norm, a.t_ms, _Xi(a.instance_key), a.tag)
        for a in alerts
    ]
    flat_order = [(a.instance_key, a.tag) for a in rank_alerts(alerts)]
    nested_order = [(a.xi.instance_key, a.tag) for a in rank_alerts(nested)]
    assert flat_order == nested_order


# --- tie-break direction, one component at a time ----------------------------------------


@pytest.mark.parametrize(
    ("better", "worse"),
    [
        (
            FlatAlert(1, 0.9, 9, "z"),
            FlatAlert(2, -0.9, 0, "a"),
        ),  # priority beats severity
        (FlatAlert(2, -0.9, 9, "z"), FlatAlert(2, -0.1, 0, "a")),  # severity beats time
        (FlatAlert(2, -0.5, 1, "z"), FlatAlert(2, -0.5, 2, "a")),  # time beats key
        (FlatAlert(2, -0.5, 1, "a"), FlatAlert(2, -0.5, 1, "b")),  # key ascending
        (
            FlatAlert(2, -0.5, -7, "b"),
            FlatAlert(2, -0.5, 7, "a"),
        ),  # negative times sort first
    ],
)
def test_each_key_component_decides_in_the_documented_direction(
    better: FlatAlert, worse: FlatAlert
) -> None:
    assert rank_alerts([worse, better]) == [better, worse]
    assert rank_alerts([better, worse]) == [better, worse]


def test_large_and_numpy_numbers_are_ordered_exactly() -> None:
    huge = 10**400
    items = [
        FlatAlert(huge, -0.1, huge, "k"),
        FlatAlert(huge - 1, -0.1, huge, "k"),
        FlatAlert(huge - 1, -0.1, huge - 1, "k"),
    ]
    assert rank_alerts(items) == [items[2], items[1], items[0]]
    numpy_items = [
        SimpleNamespace(
            priority=np.int64(2),
            sigma_norm=np.float64(-0.1),
            t_ms=np.int64(5),
            instance_key="a",
        ),
        SimpleNamespace(
            priority=np.int32(1),
            sigma_norm=np.float32(0.5),
            t_ms=np.int64(9),
            instance_key="b",
        ),
    ]
    assert rank_alerts(numpy_items) == [numpy_items[1], numpy_items[0]]
    inf_items = [FlatAlert(1, math.inf, 0, "a"), FlatAlert(1, -math.inf, 0, "b")]
    assert rank_alerts(inf_items) == [inf_items[1], inf_items[0]]


# --- robust inputs: ValueError, never TypeError or AttributeError --------------------------

GOOD = {"priority": 1, "sigma_norm": -0.5, "t_ms": 10, "instance_key": "k"}


def with_field(**changes: Any) -> SimpleNamespace:
    return SimpleNamespace(**{**GOOD, **changes})


BAD_ALERTS: list[tuple[str, Any]] = [
    ("priority zero", with_field(priority=0)),
    ("priority negative", with_field(priority=-1)),
    ("priority float", with_field(priority=2.0)),
    ("priority bool", with_field(priority=True)),
    ("priority str", with_field(priority="1")),
    ("priority None", with_field(priority=None)),
    ("priority nan", with_field(priority=math.nan)),
    ("sigma nan", with_field(sigma_norm=math.nan)),
    ("sigma numpy nan", with_field(sigma_norm=np.float64("nan"))),
    ("sigma str", with_field(sigma_norm="-0.5")),
    ("sigma None", with_field(sigma_norm=None)),
    ("sigma bool", with_field(sigma_norm=False)),
    ("sigma complex", with_field(sigma_norm=1j)),
    ("t_ms float", with_field(t_ms=1.5)),
    ("t_ms bool", with_field(t_ms=True)),
    ("t_ms None", with_field(t_ms=None)),
    ("t_ms str", with_field(t_ms="10")),
    ("key int", with_field(instance_key=5)),
    ("key None", with_field(instance_key=None)),
    ("key bytes", with_field(instance_key=b"k")),
    ("no priority", SimpleNamespace(sigma_norm=-0.5, t_ms=10, instance_key="k")),
    ("no sigma_norm", SimpleNamespace(priority=1, t_ms=10, instance_key="k")),
    ("no t_ms", SimpleNamespace(priority=1, sigma_norm=-0.5, instance_key="k")),
    ("no key at all", SimpleNamespace(priority=1, sigma_norm=-0.5, t_ms=10)),
    ("xi None and no flat key", with_field(instance_key=None, xi=None)),
    (
        "xi without key",
        SimpleNamespace(priority=1, sigma_norm=-0.5, t_ms=10, xi=object()),
    ),
    ("xi key int", SimpleNamespace(priority=1, sigma_norm=-0.5, t_ms=10, xi=_Xi(5))),
    ("a dict", dict(GOOD)),
    ("a tuple", (1, -0.5, 10, "k")),
    ("None", None),
    ("an int", 5),
    ("a string", "alert"),
]


@pytest.mark.parametrize(("label", "bad"), BAD_ALERTS, ids=[b[0] for b in BAD_ALERTS])
def test_rank_alerts_rejects_an_invalid_alert_with_value_error(
    label: str, bad: Any
) -> None:
    with pytest.raises(ValueError, match=r"alerts\[1\]"):
        rank_alerts([with_field(), bad])


@pytest.mark.parametrize(
    "bad",
    [None, 5, 5.0, "abc", b"abc", {"a": 1}, {1, 2}, object(), (x for x in [])],
    ids=["None", "int", "float", "str", "bytes", "dict", "set", "object", "generator"],
)
def test_rank_alerts_rejects_a_non_sequence_with_value_error(bad: Any) -> None:
    with pytest.raises(ValueError, match="must be a sequence of alerts"):
        rank_alerts(bad)


def test_rank_alerts_validates_before_sorting() -> None:
    """One invalid alert anywhere raises, even if the sort would never compare it."""
    with pytest.raises(ValueError, match=r"alerts\[2\]"):
        rank_alerts(
            [
                with_field(priority=1),
                with_field(priority=2),
                with_field(sigma_norm=math.nan),
            ]
        )


def test_rank_alerts_infinite_severity_is_accepted_but_not_nan() -> None:
    assert len(rank_alerts([with_field(sigma_norm=math.inf)])) == 1
    with pytest.raises(ValueError, match="NaN"):
        rank_alerts([with_field(sigma_norm=math.nan)])
