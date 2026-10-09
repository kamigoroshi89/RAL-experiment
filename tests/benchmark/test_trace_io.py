"""Trace schema, canonical JSON io and manifest (WS04-T01).

All numbers below are arithmetic and fixture-only: they are not clinical values.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ralmon import benchmark, signals
from ralmon.benchmark import trace
from ralmon.benchmark.trace import (
    BenchmarkDay,
    GroundTruthEvent,
    InjectedClass,
    LatentDay,
    Manifest,
    ManifestError,
    ObservedDay,
    SplitLeakError,
    TraceOrderError,
    TraceTypeError,
    read_benchmark_day,
    read_manifest,
    read_observed_day,
    read_truth,
    validate_day,
    verify_manifest,
    write_manifest,
    write_observed_day,
    write_truth,
)
from ralmon.signals import Event, EventKind, Sample

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "benchmark"
STUB_ATTR = "__ralmon_stub_owner__"


# ---------------------------------------------------------------------------
# Fixture objects (the byte-level golden files are checked by test 5)
# ---------------------------------------------------------------------------


def fixture_day() -> ObservedDay:
    """12 samples and 6 events; every value is fixture-only."""
    rows = [
        ("fx_a", 0, 0, 0.1, 0, 1.0),
        ("fx_b", 59_500, 60_000, 0.25, None, None),
        ("fx_a", 120_000, 120_000, 1.0, 1, 0.5),
        ("fx_b", 179_500, 180_000, 2.5, None, 0.75),
        ("fx_a", 240_000, 240_000, 3.0, 2, None),
        ("fx_b", 299_500, 300_000, 0.5, None, 1.0),
        ("fx_a", 360_000, 360_000, 1e-07, 3, 0.25),
        ("fx_b", 419_500, 420_000, 100.0, None, None),
        ("fx_a", 480_000, 480_000, 7.75, 4, 0.9),
        ("fx_b", 539_500, 540_000, 0.3, None, None),
        ("fx_a", 600_000, 600_000, 12345.678, 5, 1.0),
        ("fx_b", 659_500, 660_000, 2.0, None, 0.0),
    ]
    samples = tuple(Sample(*row) for row in rows)
    events = (
        Event(
            EventKind.MEASUREMENT,
            59_000,
            60_000,
            "fx_cuff",
            {"n_attempts": 1, "ok": True},
            0,
        ),
        Event(EventKind.DISPENSE, 120_000, 120_000, "fx_dispenser", {}, None),
        Event(
            EventKind.INTAKE,
            180_000,
            180_000,
            "fx_robot",
            {"confidence": 0.75, "count": 2, "verified": True, "witness": "fx_cam"},
            1,
        ),
        Event(
            EventKind.SCHEDULE_TICK,
            300_000,
            300_000,
            "fx_schedule",
            {"step": "fx_step_1"},
            None,
        ),
        Event(
            EventKind.ROBOT_TASK, 420_000, 420_000, "fx_robot", {"success": False}, 2
        ),
        Event(EventKind.DEVICE_ERROR, 480_000, 480_000, "fx_cuff", {"code": 3}, None),
    )
    return ObservedDay("p001", 0, 7, samples, events, "plan-fixture")


def fixture_latent() -> LatentDay:
    samples = (
        Sample("fx_a", 0, 0, 0.5, None, None),
        Sample("fx_a", 60_000, 60_000, 0.75, None, None),
    )
    events = (Event(EventKind.INTAKE, 30_000, 30_000, "fx_latent_src", {}, None),)
    return LatentDay("p001", 0, 7, samples, events)


def fixture_ground_truth() -> tuple[GroundTruthEvent, ...]:
    return (
        GroundTruthEvent(
            InjectedClass.C1, "fx_spike", 60_000, None, False, "fx_range", None
        ),
        GroundTruthEvent(
            InjectedClass.C2, "fx_dropout", 120_000, 180_000, True, None, "fx_group"
        ),
    )


FIXTURE_INJECTION_LOG = [{"level": "fx", "magnitude": 1.5, "subtype": "fx_dropout"}]
FIXTURE_BEHAVIOUR_LOG = [{"dose": 0, "outcome": "fx_on_time"}]


def fixture_benchmark_day() -> BenchmarkDay:
    return BenchmarkDay(fixture_day(), fixture_latent(), fixture_ground_truth())


def write_fixture_benchmark(root: Path) -> None:
    write_observed_day(root, fixture_day())
    write_truth(
        root,
        fixture_latent(),
        fixture_ground_truth(),
        injection_log=FIXTURE_INJECTION_LOG,
        behaviour_log=FIXTURE_BEHAVIOUR_LOG,
    )


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fixture_manifest(files: dict[str, str]) -> Manifest:
    return Manifest(
        benchmark_version="fx-0",
        generator_git_rev="fixture-rev",
        generation_seed=0,
        prior_source_name="fixture_prior",
        prior_provenance=(
            {"name": "fx_param", "source_ref": "fixture-only", "verified_by": None},
        ),
        fixture_only=True,
        n_unfilled=0,
        n_unverified=1,
        patients={
            "p001": {"split": "train", "cohort": "fx"},
            "p002": {"split": "calibration", "cohort": "fx"},
            "p003": {
                "split": "test",
                "cohort": "fx_shift",
                "role": "fx_role",
                "pair": "p001",
            },
        },
        files=files,
        event_counts={"C1/fx_spike": 1, "C2/fx_dropout": 1},
        settings={"days_per_patient": 1, "note": "fixture-only"},
    )


def build_fixture_tree(root: Path) -> Manifest:
    """Write the observed and truth files plus a manifest listing both."""
    write_fixture_benchmark(root)
    files = {
        rel: sha256_hex((root / rel).read_bytes())
        for rel in ("days/p001/0.json", "truth/p001/0.json")
    }
    manifest = fixture_manifest(files)
    write_manifest(root, manifest)
    return manifest


def regenerate_fixtures() -> None:
    """Rewrite the golden files (command documented in the fixtures README)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        build_fixture_tree(root)
        FIXTURES.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(
            root / "days/p001/0.json", FIXTURES / "observed_day_minimal.json"
        )
        shutil.copyfile(root / "truth/p001/0.json", FIXTURES / "truth_minimal.json")
        shutil.copyfile(root / "manifest.json", FIXTURES / "manifest_minimal.json")


# ---------------------------------------------------------------------------
# 1, 2: single definition and contract fields
# ---------------------------------------------------------------------------


def test_sample_and_event_have_single_definition() -> None:
    assert trace.Sample is signals.Sample
    assert trace.Event is signals.Event
    assert trace.EventKind is signals.EventKind
    for name in ("Sample", "Event", "EventKind"):
        assert not hasattr(getattr(signals, name), STUB_ATTR)
    for name in (
        "ObservedDay",
        "LatentDay",
        "BenchmarkDay",
        "GroundTruthEvent",
        "InjectedClass",
    ):
        assert name in benchmark.__all__
        obj = getattr(benchmark, name)
        assert obj is getattr(trace, name)
        assert not hasattr(obj, STUB_ATTR)


def fields_of(cls: type) -> list[str]:
    return [f.name for f in dataclasses.fields(cls)]


def test_dataclass_fields_match_contract() -> None:
    assert fields_of(GroundTruthEvent) == [
        "cls",
        "subtype",
        "onset_ms",
        "end_ms",
        "injected",
        "template_id",
        "confounder_group",
    ]
    assert fields_of(ObservedDay) == [
        "patient_id",
        "day_index",
        "seed",
        "samples",
        "events",
        "care_plan_id",
    ]
    assert fields_of(LatentDay) == [
        "patient_id",
        "day_index",
        "seed",
        "samples",
        "events",
    ]
    assert fields_of(BenchmarkDay) == ["observed", "latent", "ground_truth"]
    assert fields_of(Sample) == [
        "signal",
        "t_device_ms",
        "t_rx_ms",
        "value",
        "seq",
        "quality",
    ]
    assert fields_of(Event) == [
        "kind",
        "t_device_ms",
        "t_rx_ms",
        "source",
        "payload",
        "seq",
    ]
    assert [m.value for m in InjectedClass] == ["C1", "C2", "C3"]
    assert [m.name for m in EventKind] == [
        "MEASUREMENT",
        "MEASUREMENT_MISSED",
        "DISPENSE",
        "INTAKE",
        "SCHEDULE_TICK",
        "NODE_STATE",
        "ROBOT_TASK",
        "DEVICE_ERROR",
        "VERIFICATION",
    ]


# ---------------------------------------------------------------------------
# 3, 4, 5: round trip, canonical form, golden files
# ---------------------------------------------------------------------------


def test_observed_day_roundtrip_bit_exact(tmp_path: Path) -> None:
    day = fixture_day()
    assert len(day.samples) == 12
    assert len(day.events) == 6
    path = write_observed_day(tmp_path, day)
    first = path.read_bytes()
    back = read_observed_day(tmp_path, "p001", 0)
    assert back == day
    write_observed_day(tmp_path, back)
    assert path.read_bytes() == first


def test_serialisation_is_canonical(tmp_path: Path) -> None:
    day = ObservedDay(
        "p001",
        3,
        1,
        (Sample("fx_b", 1, 2, 0.1, None, None), Sample("fx_a", 3, 3, 1e-07, 1, 0.5)),
        (),
        "plan-fixture",
    )
    path = write_observed_day(tmp_path, day)
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    assert text.endswith("}\n")
    assert not text.endswith("\n\n")
    expected = json.dumps(json.loads(text), sort_keys=True, indent=2) + "\n"
    assert text == expected
    assert '  "care_plan_id": "plan-fixture",\n' in text
    assert "0.1" in text and "1e-07" in text
    assert repr(0.1) == "0.1"
    assert list(json.loads(text)) == sorted(json.loads(text))
    for forbidden in ("time", "host", "date", "created"):
        assert forbidden not in "".join(json.loads(text).keys())
    assert read_observed_day(tmp_path, "p001", 3).samples[0].value == 0.1
    write_observed_day(tmp_path, day)
    assert path.read_bytes() == raw


def test_fixture_bytes_equal_writer_output(tmp_path: Path) -> None:
    build_fixture_tree(tmp_path)
    pairs = {
        "observed_day_minimal.json": "days/p001/0.json",
        "truth_minimal.json": "truth/p001/0.json",
        "manifest_minimal.json": "manifest.json",
    }
    for fixture_name, rel in pairs.items():
        golden = (FIXTURES / fixture_name).read_bytes()
        assert golden == (tmp_path / rel).read_bytes(), fixture_name


# ---------------------------------------------------------------------------
# 6 to 10: validation
# ---------------------------------------------------------------------------


def make_day(
    samples: tuple[Sample, ...], events: tuple[Event, ...] = ()
) -> ObservedDay:
    return ObservedDay("p001", 0, 0, samples, events, "plan-fixture")


def test_samples_must_be_sorted_by_t_rx(tmp_path: Path) -> None:
    ok = (Sample("fx_a", 0, 5, 1.0, None, None), Sample("fx_a", 0, 5, 2.0, None, None))
    validate_day(make_day(ok))
    bad = (Sample("fx_a", 0, 6, 1.0, None, None), Sample("fx_a", 0, 5, 2.0, None, None))
    with pytest.raises(TraceOrderError):
        validate_day(make_day(bad))
    ev = Event(EventKind.DISPENSE, 0, 9, "fx_d", {}, None)
    ev_early = Event(EventKind.DISPENSE, 0, 8, "fx_d", {}, None)
    with pytest.raises(TraceOrderError):
        validate_day(make_day((), (ev, ev_early)))
    with pytest.raises(TraceOrderError):
        write_observed_day(tmp_path, make_day(bad))
    assert not (tmp_path / "days").exists()


def test_negative_t_device_allowed_negative_t_rx_rejected() -> None:
    stale = Sample("fx_a", -5_000, 0, 1.0, None, None)
    validate_day(make_day((stale,)))
    with pytest.raises(TraceTypeError):
        validate_day(make_day((Sample("fx_a", 0, -1, 1.0, None, None),)))
    with pytest.raises(TraceTypeError):
        validate_day(
            make_day((), (Event(EventKind.DISPENSE, 0, -1, "fx_d", {}, None),))
        )
    validate_day(make_day((), (Event(EventKind.DISPENSE, -7, 0, "fx_d", {}, None),)))


def test_time_values_must_be_integer_ms(tmp_path: Path) -> None:
    for bad in (1.5, 2.0, True):
        with pytest.raises(TraceTypeError):
            validate_day(make_day((Sample("fx_a", bad, 0, 1.0, None, None),)))  # type: ignore[arg-type]
        with pytest.raises(TraceTypeError):
            validate_day(make_day((Sample("fx_a", 0, bad, 1.0, None, None),)))  # type: ignore[arg-type]
        with pytest.raises(TraceTypeError):
            validate_day(
                make_day((), (Event(EventKind.DISPENSE, bad, 0, "d", {}, None),))  # type: ignore[arg-type]
            )
        with pytest.raises(TraceTypeError):
            write_truth(
                tmp_path,
                fixture_latent(),
                (
                    GroundTruthEvent(
                        InjectedClass.C1, "fx", bad, None, False, None, None
                    ),
                ),  # type: ignore[arg-type]
            )
        with pytest.raises(TraceTypeError):
            write_truth(
                tmp_path,
                fixture_latent(),
                (GroundTruthEvent(InjectedClass.C1, "fx", 0, bad, False, None, None),),  # type: ignore[arg-type]
            )
    assert not (tmp_path / "truth").exists()


def test_non_finite_values_rejected() -> None:
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(TraceTypeError):
            validate_day(make_day((Sample("fx_a", 0, 0, bad, None, None),)))
        with pytest.raises(TraceTypeError):
            validate_day(make_day((Sample("fx_a", 0, 0, 1.0, None, bad),)))
        with pytest.raises(TraceTypeError):
            validate_day(
                make_day((), (Event(EventKind.DISPENSE, 0, 0, "d", {"x": bad}, None),))
            )


def test_payload_types_preserved(tmp_path: Path) -> None:
    payload = {"b": True, "i": 1, "f": 1.0, "s": "1", "z": False, "zero": 0}
    day = make_day((), (Event(EventKind.INTAKE, 0, 0, "fx_r", payload, None),))
    write_observed_day(tmp_path, day)
    back = read_observed_day(tmp_path, "p001", 0).events[0].payload
    assert back == payload
    for key, value in payload.items():
        assert type(back[key]) is type(value), key


# ---------------------------------------------------------------------------
# 11 to 13: observed versus truth files
# ---------------------------------------------------------------------------


def all_keys(obj: object) -> list[str]:
    if isinstance(obj, dict):
        found = list(obj)
        for value in obj.values():
            found.extend(all_keys(value))
        return found
    if isinstance(obj, list):
        return [k for item in obj for k in all_keys(item)]
    return []


def test_observed_file_has_no_latent_or_truth_keys(tmp_path: Path) -> None:
    write_fixture_benchmark(tmp_path)
    obj = json.loads((tmp_path / "days/p001/0.json").read_text(encoding="utf-8"))
    assert set(obj) == {
        "patient_id",
        "day_index",
        "seed",
        "samples",
        "events",
        "care_plan_id",
    }
    for key in all_keys(obj):
        assert "latent" not in key
        assert "ground_truth" not in key
    leaky = make_day(
        (), (Event(EventKind.DISPENSE, 0, 0, "d", {"latent_flag": True}, None),)
    )
    with pytest.raises(TraceTypeError):
        write_observed_day(tmp_path / "other", leaky)


def test_truth_file_holds_latent_ground_truth_and_sidecars(tmp_path: Path) -> None:
    write_fixture_benchmark(tmp_path)
    obj = json.loads((tmp_path / "truth/p001/0.json").read_text(encoding="utf-8"))
    assert set(obj) == {"latent", "ground_truth", "injection_log", "behaviour_log"}
    record = read_truth(tmp_path, "p001", 0)
    assert record.latent == fixture_latent()
    assert tuple(record.ground_truth) == fixture_ground_truth()
    assert record.injection_log == FIXTURE_INJECTION_LOG
    assert record.behaviour_log == FIXTURE_BEHAVIOUR_LOG
    assert read_benchmark_day(tmp_path, "p001", 0) == fixture_benchmark_day()

    write_truth(tmp_path, fixture_latent(), fixture_ground_truth())
    bare = json.loads((tmp_path / "truth/p001/0.json").read_text(encoding="utf-8"))
    assert set(bare) == {"latent", "ground_truth"}
    assert read_truth(tmp_path, "p001", 0).injection_log is None

    with pytest.raises(TraceTypeError):
        write_truth(
            tmp_path,
            fixture_latent(),
            fixture_ground_truth(),
            injection_log={"x": float("nan")},
        )
    with pytest.raises(TraceTypeError):
        write_truth(
            tmp_path,
            fixture_latent(),
            fixture_ground_truth(),
            behaviour_log=[object()],  # type: ignore[list-item]
        )


def test_read_observed_day_needs_no_truth_directory(tmp_path: Path) -> None:
    write_fixture_benchmark(tmp_path)
    shutil.rmtree(tmp_path / "truth")
    assert read_observed_day(tmp_path, "p001", 0) == fixture_day()


# ---------------------------------------------------------------------------
# 14 to 16: manifest
# ---------------------------------------------------------------------------

MANIFEST_KEYS = {
    "benchmark_version",
    "generator_git_rev",
    "generation_seed",
    "prior_source_name",
    "prior_provenance",
    "fixture_only",
    "n_unfilled",
    "n_unverified",
    "patients",
    "files",
    "event_counts",
    "settings",
}


def test_manifest_required_fields(tmp_path: Path) -> None:
    manifest = build_fixture_tree(tmp_path)
    assert {f.name for f in dataclasses.fields(Manifest)} == MANIFEST_KEYS
    path = tmp_path / "manifest.json"
    obj = json.loads(path.read_text(encoding="utf-8"))
    assert set(obj) == MANIFEST_KEYS
    assert sorted(obj["prior_provenance"][0]) == ["name", "source_ref", "verified_by"]
    assert obj["patients"]["p003"]["role"] == "fx_role"
    assert "C1/fx_spike" in obj["event_counts"]
    assert read_manifest(tmp_path) == manifest
    for key in MANIFEST_KEYS:
        broken = {k: v for k, v in obj.items() if k != key}
        path.write_text(json.dumps(broken), encoding="utf-8")
        with pytest.raises(ManifestError, match=key):
            read_manifest(tmp_path)
    with_clock = {**obj, "created_at": "2026-01-01"}
    path.write_text(json.dumps(with_clock), encoding="utf-8")
    with pytest.raises(ManifestError):
        read_manifest(tmp_path)
    bad_patient = {**obj, "patients": {"p001": {"cohort": "fx"}}}
    path.write_text(json.dumps(bad_patient), encoding="utf-8")
    with pytest.raises(ManifestError):
        read_manifest(tmp_path)


def test_split_membership_is_by_patient(tmp_path: Path) -> None:
    build_fixture_tree(tmp_path)
    path = tmp_path / "manifest.json"
    text = path.read_text(encoding="utf-8")
    duplicate = text.replace(
        '"p002": {',
        '"p001": {\n      "cohort": "fx",\n      "split": "test"\n    },\n    "p002": {',
    )
    assert duplicate != text
    path.write_text(duplicate, encoding="utf-8")
    with pytest.raises(SplitLeakError):
        read_manifest(tmp_path)

    two_splits = fixture_manifest({})
    leaky = dataclasses.replace(
        two_splits,
        patients={"p001": {"split": ["train", "test"], "cohort": "fx"}},
    )
    with pytest.raises(SplitLeakError):
        write_manifest(tmp_path / "leaky", leaky)
    unknown = dataclasses.replace(
        two_splits, patients={"p001": {"split": "holdout", "cohort": "fx"}}
    )
    with pytest.raises(ManifestError):
        write_manifest(tmp_path / "unknown", unknown)


def test_verify_detects_tampered_or_missing_file(tmp_path: Path) -> None:
    build_fixture_tree(tmp_path)
    verify_manifest(tmp_path)

    target = tmp_path / "days/p001/0.json"
    original = target.read_bytes()
    flipped = bytearray(original)
    flipped[10] ^= 0x01
    target.write_bytes(bytes(flipped))
    with pytest.raises(ManifestError, match=r"days/p001/0\.json"):
        verify_manifest(tmp_path)

    target.unlink()
    with pytest.raises(ManifestError, match=r"days/p001/0\.json"):
        verify_manifest(tmp_path)

    target.write_bytes(original)
    verify_manifest(tmp_path)
    (tmp_path / "truth/p001/0.json").unlink()
    with pytest.raises(ManifestError, match=r"truth/p001/0\.json"):
        verify_manifest(tmp_path)


# ---------------------------------------------------------------------------
# 17: property test
# ---------------------------------------------------------------------------

finite = st.floats(allow_nan=False, allow_infinity=False)
times = st.integers(min_value=-(2**40), max_value=2**40)
rx_times = st.integers(min_value=0, max_value=2**40)
payload_values = st.one_of(
    st.booleans(), st.integers(-(2**63), 2**63), finite, st.text(max_size=8)
)
payloads = st.dictionaries(
    st.text(max_size=8).filter(lambda k: "latent" not in k and "ground_truth" not in k),
    payload_values,
    max_size=4,
)


@st.composite
def random_days(draw: st.DrawFn) -> ObservedDay:
    sample_rx = sorted(draw(st.lists(rx_times, max_size=8)))
    samples = tuple(
        Sample(
            draw(st.text(min_size=1, max_size=6)),
            draw(times),
            rx,
            draw(finite),
            draw(st.none() | st.integers(0, 2**31)),
            draw(st.none() | st.floats(0.0, 1.0)),
        )
        for rx in sample_rx
    )
    event_rx = sorted(draw(st.lists(rx_times, max_size=6)))
    events = tuple(
        Event(
            draw(st.sampled_from(list(EventKind))),
            draw(times),
            rx,
            draw(st.text(max_size=6)),
            draw(payloads),
            draw(st.none() | st.integers(0, 2**31)),
        )
        for rx in event_rx
    )
    return ObservedDay(
        "p001",
        draw(st.integers(0, 50)),
        draw(st.integers(0, 2**32)),
        samples,
        events,
        draw(st.text(max_size=6)),
    )


@settings(max_examples=60, deadline=None)
@given(day=random_days())
def test_roundtrip_property_random_days(day: ObservedDay) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        path = write_observed_day(root, day)
        first = path.read_bytes()
        back = read_observed_day(root, day.patient_id, day.day_index)
        assert back == day
        write_observed_day(root, back)
        assert path.read_bytes() == first
