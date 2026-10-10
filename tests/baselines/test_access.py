"""Guarded day views, the access and read logs, the audited registry and the logged plan (WS06-T01).

FIXTURE-ONLY numbers (see conftest.py).
"""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import pytest
import yaml

from ralmon.baselines.access import (
    AccessLog,
    AccessPolicy,
    AuditedRegistry,
    GuardedDay,
    LeakageError,
    LoggedMapping,
    ReadLog,
    Split,
    logged_plan,
)
from ralmon.benchmark import ObservedDay
from ralmon.spec.templates import TemplateId

from .conftest import (
    RecordingBaseline,
    StubRegistry,
    make_benchmark_day,
    make_care_plan,
    make_ground_truth,
    make_instance,
)

ROOT = Path(__file__).resolve().parents[2]


def guard(
    split: Split, *, policy: AccessPolicy | None = None, log: AccessLog | None = None
):  # type: ignore[no-untyped-def]
    log = AccessLog() if log is None else log
    day = make_benchmark_day()
    return day, log, GuardedDay(day, split, log, policy or AccessPolicy())


# ---- GuardedDay and AccessLog ---------------------------------------------------------------


def test_fit_passes_guarded_days_with_split_labels() -> None:
    detector = RecordingBaseline()
    train = [make_benchmark_day(patient_id="a"), make_benchmark_day(patient_id="b")]
    calib = [make_benchmark_day(patient_id="c")]
    detector.fit(train, calib)
    ((seen_train, seen_calib),) = detector.fit_calls
    assert all(isinstance(d, GuardedDay) for d in seen_train + seen_calib)
    assert [d.split for d in seen_train] == [Split.TRAIN, Split.TRAIN]
    assert [d.split for d in seen_calib] == [Split.CALIB]
    assert [d.patient_id for d in seen_train] == ["a", "b"]
    assert seen_calib[0].day_index == 0


def test_observed_always_allowed_and_logged() -> None:
    for split in (Split.TRAIN, Split.CALIB):
        day, log, guarded = guard(split)
        assert isinstance(guarded.observed, ObservedDay)
        assert guarded.observed is day.observed
        assert [(r.split, r.field) for r in log.records] == [(split, "observed")]
        assert log.records[0].patient_id == "p1"
        assert log.records[0].day_index == 0
        assert log.fields(split) == frozenset({"observed"})


def test_ground_truth_train_only() -> None:
    day, log, train = guard(Split.TRAIN)
    assert train.ground_truth == make_ground_truth()
    assert [(r.split, r.field) for r in log.records] == [(Split.TRAIN, "ground_truth")]
    _, calib_log, calib = guard(Split.CALIB)
    with pytest.raises(LeakageError):
        calib.ground_truth
    assert calib_log.records == ()
    assert [(d.split, d.field) for d in calib_log.denied] == [
        (Split.CALIB, "ground_truth")
    ]


def test_ground_truth_is_denied_on_calibration_even_with_the_latent_exception() -> None:
    _, _, calib = guard(Split.CALIB, policy=AccessPolicy(calib_latent=True))
    with pytest.raises(LeakageError):
        calib.ground_truth


def test_latent_denied_on_calibration_by_default() -> None:
    day, log, calib = guard(Split.CALIB)
    assert AccessPolicy().calib_latent is False
    with pytest.raises(LeakageError):
        calib.latent
    assert log.records == ()
    day, log, calib = guard(Split.CALIB, policy=AccessPolicy(calib_latent=True))
    assert calib.latent is day.latent
    (record,) = log.records
    assert (record.split, record.field) == (Split.CALIB, "latent")
    assert record.by_exception is True
    assert log.reads(field="latent", split=Split.CALIB) == (record,)


def test_latent_on_a_train_day_is_allowed_and_not_an_exception() -> None:
    day, log, train = guard(Split.TRAIN)
    assert train.latent is day.latent
    (record,) = log.records
    assert record.by_exception is False


def test_access_log_queries_and_clear() -> None:
    log = AccessLog()
    _, _, train = guard(Split.TRAIN, log=log)
    _, _, calib = guard(Split.CALIB, log=log)
    train.observed
    train.ground_truth
    calib.observed
    assert log.fields(Split.TRAIN) == frozenset({"observed", "ground_truth"})
    assert log.fields(Split.CALIB) == frozenset({"observed"})
    assert log.fields() == frozenset({"observed", "ground_truth"})
    assert len(log) == 3
    assert len(log.reads(field="observed")) == 2
    log.clear()
    assert len(log) == 0 and log.denied == ()


def test_guarded_day_does_not_expose_the_underlying_day() -> None:
    _, _, guarded = guard(Split.CALIB)
    public = {n for n in dir(guarded) if not n.startswith("_")}
    assert public == {
        "observed",
        "ground_truth",
        "latent",
        "split",
        "patient_id",
        "day_index",
    }
    assert "latent_s" not in repr(guarded)


def test_policy_is_frozen() -> None:
    assert [f.name for f in fields(AccessPolicy)] == ["calib_latent"]
    with pytest.raises(AttributeError):
        AccessPolicy().calib_latent = True  # type: ignore[misc]


def test_harness_applies_the_policy_and_shares_the_log() -> None:
    log = AccessLog()
    detector = RecordingBaseline(
        access_log=log, access_policy=AccessPolicy(calib_latent=True)
    )
    detector.fit([], [make_benchmark_day()])
    assert detector.access_log is log
    ((_, calib),) = detector.fit_calls
    assert calib[0].latent is not None
    assert log.reads(field="latent")[0].by_exception is True
    default = RecordingBaseline()
    default.fit([], [make_benchmark_day()])
    with pytest.raises(LeakageError):
        default.fit_calls[0][1][0].latent


# ---- ReadLog, AuditedRegistry, LoggedMapping, logged_plan --------------------------------------


def test_audited_registry_logs_reads(stub_registry: StubRegistry) -> None:
    audited = AuditedRegistry(stub_registry)
    entry = audited.get("bp_band_low")
    assert entry.value == 110.0
    bounds = audited.bounds("bp")
    assert (bounds.lower, bounds.upper) == (50.0, 250.0)
    assert audited.log.registry_reads == frozenset({"bp_band_low", "bounds:bp"})
    assert "bp_band_high" not in audited.log.registry_reads
    assert audited.version() == "0.0.0"
    assert audited.log.registry_reads == frozenset({"bp_band_low", "bounds:bp"})


def test_audited_registry_shares_a_given_log_and_logs_failed_reads(
    stub_registry: StubRegistry,
) -> None:
    log = ReadLog()
    audited = AuditedRegistry(stub_registry, log)
    with pytest.raises(KeyError):
        audited.get("nope")
    assert audited.log is log
    assert log.registry_reads == frozenset({"nope"})


def test_logged_plan_records_param_reads() -> None:
    inst = make_instance(TemplateId.RANGE, "range@0", {"a": 1.0, "b": 2.0}, 5)
    plan = make_care_plan([inst], schedule=[1, 2, 3])
    log = ReadLog()
    wrapped = logged_plan(plan, log)
    assert wrapped.instances[0].param_values["a"] == 1.0
    assert log.param_reads == {"range@0": frozenset({"a"})}
    assert wrapped.instances[0].param_values.get("a") == 1.0
    assert "b" not in log.param_reads["range@0"]
    # nothing but param_values changed
    assert wrapped.schedule == plan.schedule
    assert wrapped.care_plan_id == plan.care_plan_id
    assert wrapped.signature == plan.signature
    assert wrapped.instances[0].template == inst.template
    assert wrapped.instances[0].instance_key == inst.instance_key
    assert wrapped.instances[0].anchor_ms == inst.anchor_ms
    assert dict(wrapped.instances[0].param_values) == {"a": 1.0, "b": 2.0}
    assert plan.instances[0].param_values == {"a": 1.0, "b": 2.0}  # original untouched


def test_logged_mapping_logs_per_instance_key_and_only_found_names() -> None:
    log = ReadLog()
    first = LoggedMapping({"a": 1.0, "b": 2.0}, log, "k1")
    second = LoggedMapping({"a": 3.0}, log, "k2")
    assert len(first) == 2 and sorted(first) == ["a", "b"]
    assert log.param_reads == {}
    with pytest.raises(KeyError):
        first["zzz"]
    assert log.param_reads == {}
    second["a"]
    assert log.param_reads == {"k2": frozenset({"a"})}
    assert dict(first.items()) == {"a": 1.0, "b": 2.0}
    assert log.param_reads["k1"] == frozenset({"a", "b"})


def test_read_log_clear_and_all_names() -> None:
    log = ReadLog()
    log.record_registry("x")
    log.record_param("k", "a")
    assert log.all_names() == frozenset({"x", "a"})
    log.clear()
    assert log.registry_reads == frozenset() and log.param_reads == {}


def test_the_harness_passes_the_logged_plan_to_the_subclass() -> None:
    seen = []

    class Reader(RecordingBaseline):
        def _run(self, day, plan):  # type: ignore[no-untyped-def]
            seen.append(plan.instances[0].param_values["a"])
            return ()

    inst = make_instance(TemplateId.RANGE, "range@0", {"a": 1.0, "b": 2.0})
    detector = Reader()
    detector.fit([], [])
    detector.run(make_benchmark_day().observed, make_care_plan([inst]), None)
    assert seen == [1.0]
    assert detector.read_log.param_reads == {"range@0": frozenset({"a"})}


def test_stub_registry_names_exist_in_yaml(stub_registry: StubRegistry) -> None:
    for relpath in ("hypertension.yaml", "fixture.yaml"):
        doc = yaml.safe_load(
            (ROOT / "configs" / "registry" / relpath).read_text("utf-8")
        )
        entry_names = {row["name"] for row in doc["entries"]}
        assert stub_registry.names() <= entry_names, relpath
