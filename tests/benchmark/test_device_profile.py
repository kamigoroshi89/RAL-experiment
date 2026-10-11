"""Device profile of the generator: cuff resolution, driver diagnostics, dispenser interval (WS04-T18, ADR-074).

FIXTURE-ONLY. Every number below is arithmetic of the test: the lease and the period of the driver are TEST VALUES
(the real ones are ``awaiting_human_value`` rows of ``configs/benchmark/generator_design.yaml``), the cuff error SD
of the repeat-rate test is a test value and the fixture streams are hand-written. None is a device specification
or a clinical value.

What is under test (``ralmon.benchmark.device_profile``, ``measurement.assign_dispense_intervals``,
``injection.finalize_observed`` and ``InjectionContext.device_profile``, ``builder`` and its ``device_profile`` section)

* the cuff readings (``bp`` and the ``hr_pulse`` of the cuff) are rounded at the device boundary, AFTER the
  injectors, to a device-profile resolution (default 1 mmHg / 1 bpm); the latent day and the ground truth never are;
* the driver ``NODE_STATE`` ``diagnostics`` reports under the liveness contract of ``docs/models/evidence-channels.md``
  (an idle on-demand device is ``ok``, never ``stale``; a session whose publisher stops is ``stale`` after the lease);
  two named profiles; a lease or period that is unset fails loudly;
* the ``DISPENSE`` payload ``interval_since_previous_ms`` and the sign of ``content_change`` (ADR-040 (2));
* the robot ``NODE_STATE`` ``colocated`` reports of the builder (ADR-040 (3)).
"""

from __future__ import annotations

import dataclasses
import json
import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from ralmon.attribution.extract import DeviceCapabilities
from ralmon.benchmark import vocab
from ralmon.benchmark.builder import (
    generate_benchmark,
    load_config,
    open_benchmark,
)
from ralmon.benchmark.device_profile import (
    ACTIVITY_MODES,
    DEFAULT_CUFF_RESOLUTION_MMHG,
    DEFAULT_PULSE_RESOLUTION_BPM,
    MODE_CONTINUOUS,
    MODE_ON_DEMAND,
    PROFILE_WITH_DIAGNOSTICS,
    PROFILE_WITHOUT_DIAGNOSTICS,
    DeviceProfileError,
    DriverDiagnostics,
    GeneratorDeviceProfile,
    Session,
    UnsetDriverParameterError,
    driver_reports,
)
from ralmon.benchmark.injection import (
    InjectionSpec,
    finalize_observed,
)
from ralmon.benchmark.latent import T_DAY_MS
from ralmon.benchmark.measurement import (
    ObservedStream,
    assign_dispense_intervals,
)
from ralmon.benchmark.priors import (
    DeviceErrorModel,
    LiteraturePriorSource,
    UnfilledParameterError,
)
from ralmon.benchmark.schedule import Schedule
from ralmon.benchmark.trace import InjectedClass
from ralmon.signals import Event, EventKind

from .test_builder import (
    GENERATOR_DESIGN,
    GIT_REV,
    config_document,
    make_prior,
    write_config,
)
from .test_builder import build as build_benchmark
from .test_inject_c2 import (
    DOSE_TICKS,
    HOUR,
    MIN,
    bias,
    ble,
    bounce,
    fixture_stream,
    manip,
    run,
    stuck,
)
from .test_measurement import build as build_base
from .test_measurement import latent_day

DAY = T_DAY_MS
PERIOD = HOUR  # TEST VALUE: the real driver period is awaiting_human_value
LEASE = 10 * MIN  # TEST VALUE: the real lease is awaiting_human_value
C3 = InjectedClass.C3


def diagnostics_profile(
    *, period: int = PERIOD, lease: int = LEASE, **kwargs: Any
) -> GeneratorDeviceProfile:
    return GeneratorDeviceProfile.with_diagnostics(
        period_ms=period, stale_lease_ms=lease, **kwargs
    )


def reports_of(events: Sequence[Event], source: str) -> list[tuple[int, str]]:
    """``(t, level)`` of the ``diagnostics`` reports of a node, in time order."""
    return [
        (e.t_device_ms, str(e.payload[vocab.KEY_DIAGNOSTICS]))
        for e in events
        if e.kind is EventKind.NODE_STATE
        and e.source == source
        and vocab.KEY_DIAGNOSTICS in e.payload
    ]


def fractional_stream(day_index: int = 0) -> ObservedStream:
    """The hand-written fixture day with non-integer cuff readings and pulse rates."""
    stream = fixture_stream(bps=[128.4, 131.6, 127.5, 133.2], day_index=day_index)
    samples = tuple(
        dataclasses.replace(s, value=s.value + 0.37) if s.signal == "hr_pulse" else s
        for s in stream.samples
    )
    return dataclasses.replace(stream, samples=samples)


# ---------------------------------------------------------------------------
# 1. and 10. Rounding at the device boundary
# ---------------------------------------------------------------------------


def test_cuff_readings_are_multiples_of_the_resolution() -> None:
    stream = fractional_stream()
    assert any(s.value != round(s.value) for s in stream.samples if s.signal == "bp")
    # the default: 1 mmHg and 1 bpm (gab, ADR-074 amendment 2)
    assert DEFAULT_CUFF_RESOLUTION_MMHG == 1.0 and DEFAULT_PULSE_RESOLUTION_BPM == 1.0
    assert GeneratorDeviceProfile().cuff_resolution_mmhg == 1.0
    assert GeneratorDeviceProfile().pulse_resolution_bpm == 1.0
    day = finalize_observed(stream, device_profile=GeneratorDeviceProfile())
    bp = [s.value for s in day.samples if s.signal == "bp"]
    pulse = [s.value for s in day.samples if s.signal == "hr_pulse"]
    assert bp == [128.0, 132.0, 128.0, 133.0]  # round half to even at 127.5
    assert all(v == round(v) for v in (*bp, *pulse))
    # a resolution of 5 gives multiples of 5; the pulse has its own resolution
    coarse = finalize_observed(
        stream,
        device_profile=GeneratorDeviceProfile(
            cuff_resolution_mmhg=5.0, pulse_resolution_bpm=2.0
        ),
    )
    assert [s.value for s in coarse.samples if s.signal == "bp"] == [
        130.0,
        130.0,
        130.0,
        135.0,
    ]  # fmt: skip  (127.5 / 5 = 25.5 rounds half to even, to 26)
    assert all(s.value % 5 == 0 for s in coarse.samples if s.signal == "bp")
    assert all(s.value % 2 == 0 for s in coarse.samples if s.signal == "hr_pulse")
    # nothing else is touched: other signals, times, sequence numbers, qualities and events
    other = [s for s in stream.samples if s.signal not in ("bp", "hr_pulse")]
    kept = [s for s in coarse.samples if s.signal not in ("bp", "hr_pulse")]
    assert other == kept
    assert coarse.events == tuple(stream.events)
    # no profile: the values are as the injectors left them (the device boundary is not modelled)
    assert finalize_observed(stream).samples == tuple(stream.samples)
    # a resolution of None means no rounding (the behaviour before WS04-T18, a counterfactual)
    free = GeneratorDeviceProfile(cuff_resolution_mmhg=None, pulse_resolution_bpm=None)
    assert finalize_observed(stream, device_profile=free).samples == tuple(
        stream.samples
    )


@pytest.mark.parametrize("bad", [0, 0.0, -1.0, math.nan, math.inf, True, "1"])
def test_a_resolution_must_be_positive_and_finite(bad: Any) -> None:
    with pytest.raises(DeviceProfileError):
        GeneratorDeviceProfile(cuff_resolution_mmhg=bad)
    with pytest.raises(DeviceProfileError):
        GeneratorDeviceProfile(pulse_resolution_bpm=bad)


def test_rounding_is_after_the_injectors_so_a_frozen_value_stays_frozen() -> None:
    """A silent bias is added before the display rounds it; a frozen window is exactly identical after rounding."""
    stream = fractional_stream()
    biased = run([bias(9 * HOUR, 4 * HOUR, 2.3)], stream_=stream)
    unrounded = [s.value for s in biased.stream.samples if s.signal == "bp"]
    shown = finalize_observed(biased.stream, device_profile=GeneratorDeviceProfile())
    assert [s.value for s in shown.samples if s.signal == "bp"] == [
        float(round(v)) for v in unrounded
    ]
    frozen = run([stuck(9 * HOUR, 6 * HOUR)], stream_=stream)
    values = [s.value for s in frozen.stream.samples if s.signal == "bp"]
    assert len(set(values[1:])) == 1  # the injector froze the unrounded reading
    day = finalize_observed(frozen.stream, device_profile=GeneratorDeviceProfile())
    shown_bp = [s.value for s in day.samples if s.signal == "bp"]
    assert len(set(shown_bp[1:])) == 1 and shown_bp[1] == float(round(values[1]))


def test_fault_free_repeat_rate_matches_the_rounding_formula() -> None:
    """Natural repeat rate of rounded readings: E[max(0, 1 - |delta| / r)] on the unrounded differences.

    FIXTURE-ONLY cuff error SD of 8 mmHg (a test value) on a flat latent pressure; the readings of 600 seeded
    fault-free days are drawn by ``build_observed_base``, shown unrounded and rounded to 1 mmHg.
    """
    schedule = Schedule(
        dose_ticks_ms=(),
        measurement_ticks_ms=(
            6 * HOUR,
            8 * HOUR,
            12 * HOUR,
            16 * HOUR,
            20 * HOUR,
            22 * HOUR,
        ),
    )
    errors = DeviceErrorModel(8.0, 0.0, 0.0, 0.0)
    resolution = 1.0
    profile = GeneratorDeviceProfile(cuff_resolution_mmhg=resolution)
    repeats = 0
    pairs = 0
    expected = 0.0
    variance = 0.0
    unrounded_repeats = 0
    for d in range(600):
        stream = build_base(
            latent_day(130.0, day_index=0, seed=0),
            schedule,
            errors=errors,
            seed=0,
            patient_index=d,
        )
        raw = [s.value for s in stream.samples if s.signal == "bp"]
        shown = [
            s.value
            for s in finalize_observed(stream, device_profile=profile).samples
            if s.signal == "bp"
        ]
        assert len(raw) == len(shown) == 6
        for a, b, x, y in zip(raw, raw[1:], shown, shown[1:], strict=False):
            p = max(0.0, 1.0 - abs(b - a) / resolution)
            expected += p
            variance += p * (1.0 - p)
            repeats += x == y
            unrounded_repeats += a == b
            pairs += 1
    assert pairs == 600 * 5
    assert (
        unrounded_repeats == 0
    )  # without rounding the natural repeat probability is exactly 0
    assert expected > 20  # the check is not vacuous
    assert abs(repeats - expected) <= 4.0 * math.sqrt(variance), (repeats, expected)


@pytest.fixture(scope="module")
def rounding_builds(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, Path, Any, Any]:
    """The same small benchmark twice: cuff resolution 1 mmHg / 1 bpm (the default) and no rounding."""
    tmp = tmp_path_factory.mktemp("rounding")
    prior = make_prior(tmp)
    rounded_doc = config_document(tmp, prior=prior, n_patients=4, n_days=2, variants=[])
    free_doc = json.loads(json.dumps(rounded_doc))
    free_doc["device_profile"]["cuff_resolution_mmhg"] = None
    free_doc["device_profile"]["pulse_resolution_bpm"] = None
    rounded_dir, rounded = build_benchmark(
        tmp, "rounded", document=rounded_doc, prior_path=prior
    )
    free_dir, free = build_benchmark(tmp, "free", document=free_doc, prior_path=prior)
    return rounded_dir, free_dir, rounded, free


def test_rounding_does_not_change_ground_truth(
    rounding_builds: tuple[Path, Path, Any, Any],
) -> None:
    rounded_dir, free_dir, rounded, free = rounding_builds
    # the latent days, the ground truth, the injection log and the latent baseline are byte-identical
    n_truth = 0
    for sub in ("truth", "generator", "plans"):
        for path in sorted((rounded_dir / sub).rglob("*.json")):
            twin = free_dir / path.relative_to(rounded_dir)
            assert path.read_bytes() == twin.read_bytes(), path
            n_truth += 1
    assert n_truth > 12
    # the observed readings are the rounded ones, everything else is identical
    changed = 0
    for path in sorted((rounded_dir / "days").rglob("*.json")):
        shown = json.loads(path.read_text("utf-8"))
        raw = json.loads((free_dir / path.relative_to(rounded_dir)).read_text("utf-8"))
        assert shown["events"] == raw["events"]
        assert len(shown["samples"]) == len(raw["samples"])
        for a, b in zip(shown["samples"], raw["samples"], strict=True):
            if b["signal"] in ("bp", "hr_pulse"):
                assert a["value"] == float(round(b["value"]))
                assert {k: v for k, v in a.items() if k != "value"} == {
                    k: v for k, v in b.items() if k != "value"
                }
                changed += a["value"] != b["value"]
            else:
                assert a == b
    assert changed > 0
    # the manifest records the resolution that the extractor must be given
    profile = rounded.settings["device_profile"]
    assert profile["cuff_resolution_mmhg"] == 1.0
    assert profile["pulse_resolution_bpm"] == 1.0
    assert free.settings["device_profile"]["cuff_resolution_mmhg"] is None
    capabilities = DeviceCapabilities(cuff_resolution=profile["cuff_resolution_mmhg"])
    assert capabilities.cuff_resolution == DEFAULT_CUFF_RESOLUTION_MMHG
    # no reading of the shown day is a fraction
    for path in sorted((rounded_dir / "days").rglob("*.json")):
        for s in json.loads(path.read_text("utf-8"))["samples"]:
            if s["signal"] in ("bp", "hr_pulse"):
                assert s["value"] == round(s["value"])


# ---------------------------------------------------------------------------
# 3. to 6. Driver diagnostics under the liveness contract
# ---------------------------------------------------------------------------


def test_profile_names_and_modes_are_declared() -> None:
    assert PROFILE_WITH_DIAGNOSTICS == "driver_with_diagnostics"
    assert PROFILE_WITHOUT_DIAGNOSTICS == "without_diagnostics"
    assert GeneratorDeviceProfile().diagnostics_profile == PROFILE_WITHOUT_DIAGNOSTICS
    assert diagnostics_profile().diagnostics_profile == PROFILE_WITH_DIAGNOSTICS
    # evidence-channels.md, liveness contract item 2
    assert ACTIVITY_MODES[vocab.SOURCE_CUFF] == MODE_ON_DEMAND
    assert ACTIVITY_MODES[vocab.SOURCE_DISPENSER] == MODE_ON_DEMAND
    assert ACTIVITY_MODES[vocab.SOURCE_ECG] == MODE_CONTINUOUS
    assert ACTIVITY_MODES[vocab.SOURCE_OXIMETER] == MODE_CONTINUOUS


def test_idle_cuff_never_reports_stale_over_24h() -> None:
    # the pure rule: an on-demand device with no open session, however long the day
    events = driver_reports(
        vocab.SOURCE_CUFF,
        MODE_ON_DEMAND,
        period_ms=PERIOD,
        stale_lease_ms=LEASE,
        day_start_ms=0,
        day_end_ms=DAY,
        sessions=(),
        message_times=(),
    )
    levels = reports_of(events, vocab.SOURCE_CUFF)
    assert [t for t, _ in levels] == [
        k * PERIOD for k in range(24)
    ]  # ok at start, then each period
    assert {level for _, level in levels} == {"ok"}
    # the same over a built day: five readings, an idle cuff between them (a lease above the inflation time)
    out = run([], stream_=fixture_stream(), device_profile=diagnostics_profile())
    for device in (vocab.SOURCE_CUFF, vocab.SOURCE_DISPENSER):
        levels = reports_of(out.stream.events, device)
        assert len(levels) == 24
        assert {level for _, level in levels} == {"ok"}
        assert levels[0] == (0, "ok")
    # the nodes that the profile does not name report nothing
    assert reports_of(out.stream.events, vocab.SOURCE_ECG) == []
    assert reports_of(out.stream.events, vocab.SOURCE_ROBOT) == []


def test_open_session_with_stopped_publisher_goes_stale_after_the_lease() -> None:
    t0 = 10 * HOUR
    stopped = driver_reports(
        vocab.SOURCE_CUFF,
        MODE_ON_DEMAND,
        period_ms=10 * MIN,
        stale_lease_ms=LEASE,
        day_start_ms=0,
        day_end_ms=DAY,
        sessions=(Session(t0, None),),
        message_times=(),
    )
    levels = dict(reports_of(stopped, vocab.SOURCE_CUFF))
    assert (
        levels[t0] == "ok"
    )  # the session has just opened: silent for less than the lease
    assert (
        levels[t0 + LEASE] == "ok"
    )  # silent for exactly the lease is not yet stale (MORE than the lease)
    assert levels[t0 + LEASE + 10 * MIN] == "stale"
    assert (
        levels[t0 - 10 * MIN] == "ok" and levels[0] == "ok"
    )  # idle before the session
    assert levels[DAY - 10 * MIN] == "stale"  # nobody closed the session
    # a restored session: ok again from the restoration, and a transition report is there
    restored = driver_reports(
        vocab.SOURCE_CUFF,
        MODE_ON_DEMAND,
        period_ms=HOUR,
        stale_lease_ms=LEASE,
        day_start_ms=0,
        day_end_ms=DAY,
        sessions=(Session(t0, t0 + 40 * MIN),),
        message_times=(),
    )
    seq = reports_of(restored, vocab.SOURCE_CUFF)
    assert (t0 + LEASE + 1, "stale") in seq and (
        t0 + 40 * MIN,
        "ok",
    ) in seq  # a report at the first ms beyond the lease
    assert [level for t, level in seq if t > t0 + 40 * MIN] == ["ok"] * 13
    # the strict lease: silent for exactly the lease is not stale yet
    edge = dict(
        reports_of(
            driver_reports(
                vocab.SOURCE_CUFF,
                MODE_ON_DEMAND,
                period_ms=MIN,
                stale_lease_ms=LEASE,
                day_start_ms=0,
                day_end_ms=DAY,
                sessions=(Session(HOUR, None),),
                message_times=(),
            ),
            vocab.SOURCE_CUFF,
        )
    )
    assert edge[HOUR + LEASE] == "ok" and edge[HOUR + LEASE + MIN] == "stale"


def test_a_continuous_device_is_stale_when_silent_beyond_the_lease() -> None:
    times = tuple(range(0, 4 * HOUR, MIN)) + tuple(
        range(5 * HOUR, DAY, MIN)
    )  # silent from 04:00 to 05:00
    events = driver_reports(
        vocab.SOURCE_ECG,
        MODE_CONTINUOUS,
        period_ms=30 * MIN,
        stale_lease_ms=LEASE,
        day_start_ms=0,
        day_end_ms=DAY,
        sessions=(),
        message_times=times,
    )
    levels = dict(reports_of(events, vocab.SOURCE_ECG))
    assert levels[3 * HOUR + 30 * MIN] == "ok"
    assert levels[4 * HOUR + 30 * MIN] == "stale"  # silent for 30 min > the lease
    assert levels[5 * HOUR + 30 * MIN] == "ok"
    assert (
        levels[4 * HOUR - MIN + LEASE + 1] == "stale"
    )  # a transition report at the first ms beyond the lease
    assert levels[5 * HOUR] == "ok"  # and one at the recovery


def test_dropout_over_a_reading_makes_the_cuff_stale_and_an_idle_dropout_does_not() -> (
    None
):
    # fixture readings at 08:00:30, 10:00:30, ...: the cuff session opens at the arrival, 30 s before the reading
    profile = diagnostics_profile(period=10 * MIN)
    lost = run(
        [ble(9 * HOUR + 59 * MIN, 31 * MIN, "cuff")],
        stream_=fixture_stream(),
        device_profile=profile,
    )
    cuff = reports_of(lost.stream.events, vocab.SOURCE_CUFF)
    start = 10 * HOUR  # the session opens at 10:00:00
    window_end = 9 * HOUR + 59 * MIN + 31 * MIN
    assert (
        start + LEASE + 1,
        "stale",
    ) in cuff  # stale at the first ms beyond the lease
    assert (
        start + 2 * LEASE,
        "stale",
    ) in cuff  # and at the periodic report inside the outage
    stale_times = [t for t, level in cuff if level == "stale"]
    assert min(stale_times) == start + LEASE + 1 and max(stale_times) < window_end
    assert (
        window_end,
        "ok",
    ) in cuff  # restored when the gateway reports the link active
    assert {level for t, level in cuff if t >= window_end} == {"ok"}
    assert {level for t, level in cuff if t <= start + LEASE} == {"ok"}
    # the dispenser, the other device, stays ok
    assert {
        level for _, level in reports_of(lost.stream.events, vocab.SOURCE_DISPENSER)
    } == {"ok"}
    # a dropout of the idle cuff between two readings loses nothing and is no report of the driver about the sensor
    idle = run(
        [ble(5 * HOUR, 2 * HOUR, "cuff")],
        stream_=fixture_stream(),
        device_profile=profile,
    )
    assert {
        level for _, level in reports_of(idle.stream.events, vocab.SOURCE_CUFF)
    } == {"ok"}
    assert not any(
        e.kind is EventKind.NODE_STATE and e.payload.get("state") == "link_down"
        for e in idle.stream.events
    )  # nothing was lost, so the gateway reported nothing


def test_a_refused_or_failed_measurement_opens_no_session() -> None:
    """A patient who refuses, or a manipulation that fails, sends no message: no session, no stale (C1 stays C1)."""
    out = run(
        [manip(10 * HOUR)],
        stream_=fixture_stream(),
        device_profile=diagnostics_profile(period=10 * MIN),
    )
    assert {level for _, level in reports_of(out.stream.events, vocab.SOURCE_CUFF)} == {
        "ok"
    }


def test_profile_without_diagnostics_emits_no_diagnostics_report() -> None:
    for profile in (None, GeneratorDeviceProfile()):
        out = run(
            [ble(10 * HOUR, HOUR, "cuff")],
            stream_=fixture_stream(),
            device_profile=profile,
        )
        assert not any(vocab.KEY_DIAGNOSTICS in e.payload for e in out.stream.events)
    # the day is the same as without a profile, apart from the interval of the dispenser
    plain = run([], stream_=fixture_stream())
    withp = run([], stream_=fixture_stream(), device_profile=GeneratorDeviceProfile())
    strip = lambda s: [
        dataclasses.replace(
            e, payload={k: v for k, v in e.payload.items() if k != vocab.KEY_INTERVAL}
        )
        for e in s.stream.events
    ]
    assert strip(plain) == strip(withp) and plain.stream.samples == withp.stream.samples


def test_unset_lease_with_diagnostics_profile_fails_loudly() -> None:
    # the library: no default for the lease or the period (a named error, not a silent skip)
    with pytest.raises(UnsetDriverParameterError, match="stale_lease_ms"):
        GeneratorDeviceProfile.with_diagnostics(period_ms=PERIOD, stale_lease_ms=None)
    with pytest.raises(UnsetDriverParameterError, match="period_ms"):
        GeneratorDeviceProfile.with_diagnostics(period_ms=None, stale_lease_ms=LEASE)
    with pytest.raises(UnsetDriverParameterError):
        DriverDiagnostics(period_ms=None, stale_lease_ms=None)  # type: ignore[arg-type]
    assert issubclass(UnsetDriverParameterError, DeviceProfileError)
    for bad in (0, -1, 1.5, True):
        with pytest.raises(DeviceProfileError):
            DriverDiagnostics(period_ms=bad, stale_lease_ms=LEASE)  # type: ignore[arg-type]
        with pytest.raises(DeviceProfileError):
            DriverDiagnostics(period_ms=PERIOD, stale_lease_ms=bad)  # type: ignore[arg-type]
    with pytest.raises(DeviceProfileError):
        diagnostics_profile(devices=(vocab.SOURCE_ROBOT,))


def test_the_builder_refuses_the_diagnostics_profile_while_the_rows_are_awaiting(
    tmp_path: Path,
) -> None:
    unset = ("driver_period_ms", "driver_stale_lease_ms")
    doc = config_document(
        tmp_path, n_patients=1, n_days=1, variants=[], leave_unset=unset,
        device_profile={"diagnostics_profile": PROFILE_WITH_DIAGNOSTICS},
    )  # fmt: skip
    config = load_config(write_config(tmp_path, doc))
    prior = LiteraturePriorSource(
        Path(doc["cohorts"][0]["prior"]), strict=False, allow_fixture_only=True
    )
    with pytest.raises(UnfilledParameterError) as info:
        generate_benchmark(
            config,
            prior,
            tmp_path / "refused",
            allow_fixture_only=True,
            git_rev=GIT_REV,
        )
    assert "driver_stale_lease_ms" in str(info.value) and "driver_period_ms" in str(
        info.value
    )
    assert not (tmp_path / "refused").exists()
    # the same rows left awaiting do not stop the build of the profile without diagnostics
    plain = config_document(
        tmp_path, n_patients=1, n_days=1, variants=[], leave_unset=unset
    )
    out, manifest = build_benchmark(tmp_path, "plain", document=plain)
    assert (
        manifest.settings["device_profile"]["diagnostics_profile"]
        == PROFILE_WITHOUT_DIAGNOSTICS
    )
    assert manifest.settings["device_profile"]["driver"] is None
    assert (out / "manifest.json").is_file()


def test_the_committed_design_file_holds_the_two_rows_as_awaiting() -> None:
    from ralmon.benchmark.priors import load_design_file

    rows = {r.parameter: r for r in load_design_file(GENERATOR_DESIGN).rows}
    for name in ("driver_period_ms", "driver_stale_lease_ms"):
        assert rows[name].status == "awaiting_human_value" and rows[name].value is None
        assert rows[name].unit == "ms" and rows[name].consumer_task == "WS04-T18"


def test_a_built_benchmark_with_the_diagnostics_profile_records_it_and_reports_ok_and_stale(
    tmp_path: Path,
) -> None:
    doc = config_document(
        tmp_path, n_patients=3, n_days=2, variants=["nominal_content_robot"],
        device_profile={"diagnostics_profile": PROFILE_WITH_DIAGNOSTICS},
    )  # fmt: skip
    out, manifest = build_benchmark(tmp_path, document=doc)
    entry = manifest.settings["device_profile"]
    assert entry["diagnostics_profile"] == "driver_with_diagnostics"
    assert entry["driver"]["devices"] == ["cuff", "dispenser"]
    assert (
        entry["driver"]["period_ms"] == HOUR
        and entry["driver"]["stale_lease_ms"] == 10 * MIN
    )  # test values
    assert entry["driver"]["activity_modes"] == {
        "cuff": "on_demand",
        "dispenser": "on_demand",
    }
    reader = open_benchmark(out)
    seen: dict[str, set[str]] = {"cuff": set(), "dispenser": set()}
    for patient in reader.patients:
        for d in (*reader.days(patient), reader.tail_day(patient)):
            day = reader.observed(patient, d)
            for device in seen:
                reports = reports_of(day.events, device)
                assert (
                    reports and reports[0][0] == d * DAY
                )  # ok at the start of every day
                assert reports[0][1] == "ok"
                seen[device] |= {level for _, level in reports}
            for e in day.events:
                vocab.check_payload(e.kind, e.payload)
    assert seen["cuff"] <= {"ok", "stale"} and "ok" in seen["cuff"]


def test_the_driver_reports_do_not_change_the_verdicts_of_the_monitor(
    tmp_path: Path,
) -> None:
    """The monitor reads no non-robot NODE_STATE: the verdicts of a day equal those of the day without the reports."""
    from ralmon.monitor import MonitorConfig, run_offline_detailed

    from .test_builder import F0, STEP_MS, TEMPLATES

    doc = config_document(
        tmp_path,
        n_patients=2,
        n_days=2,
        variants=[],
        device_profile={"diagnostics_profile": PROFILE_WITH_DIAGNOSTICS},
    )
    out, _ = build_benchmark(tmp_path, document=doc)
    reader = open_benchmark(out)
    cfg = MonitorConfig(STEP_MS, 0, False, None, "likely", F0.version())
    n = 0
    for patient in reader.patients:
        plan = reader.care_plan(reader.observed(patient, 0).care_plan_id)
        for d in reader.days(patient):
            day = reader.observed(patient, d)
            bare = dataclasses.replace(
                day,
                events=tuple(
                    e for e in day.events if vocab.KEY_DIAGNOSTICS not in e.payload
                ),
            )
            assert len(bare.events) < len(day.events)
            history = [reader.observed(patient, k) for k in range(d)]
            args = (plan, cfg, None, None)
            kwargs: dict[str, Any] = {
                "registry": F0,
                "templates": TEMPLATES,
                "history": history,
            }
            with_reports = run_offline_detailed(day, *args, **kwargs)
            without = run_offline_detailed(bare, *args, **kwargs)
            assert with_reports.records == without.records
            n += 1
    assert n == 4


# ---------------------------------------------------------------------------
# 7. and 8. The dispenser payload
# ---------------------------------------------------------------------------


def with_content(stream: ObservedStream, change: float = 1.0) -> ObservedStream:
    """The fixture day with a dispenser that senses its content (a release is +1)."""
    events = tuple(
        dataclasses.replace(e, payload={vocab.KEY_CONTENT_CHANGE: change})
        if e.kind is EventKind.DISPENSE
        else e
        for e in stream.events
    )
    return dataclasses.replace(stream, events=events)


def dispenses(events: Sequence[Event]) -> list[Event]:
    return sorted(
        (e for e in events if e.kind is EventKind.DISPENSE and e.source == "dispenser"),
        key=lambda e: e.t_device_ms,
    )


def test_dispense_payload_has_interval_and_signed_content_change() -> None:
    out = run(
        [], stream_=with_content(fixture_stream()),
        device_profile=GeneratorDeviceProfile(), dispenser_content_sensing=True,
    )  # fmt: skip
    first, second = dispenses(out.stream.events)
    assert first.t_device_ms == DOSE_TICKS[0] and second.t_device_ms == DOSE_TICKS[1]
    assert (
        vocab.KEY_INTERVAL not in first.payload
    )  # the first opening of a stream has no previous opening
    interval = second.payload[vocab.KEY_INTERVAL]
    assert type(interval) is int and interval == DOSE_TICKS[1] - DOSE_TICKS[0] >= 0
    # content_change is before minus after: a release is positive
    assert (
        first.payload[vocab.KEY_CONTENT_CHANGE]
        == second.payload[vocab.KEY_CONTENT_CHANGE]
        == 1.0
    )
    # each opening has its own sequence number (a re-sent copy with the same seq is skipped by the extractor)
    assert first.seq is not None and second.seq is not None and first.seq != second.seq
    # the payload is a declared one and the day is a valid observed day
    for e in (first, second):
        vocab.check_payload(e.kind, e.payload)
    day = finalize_observed(out.stream, device_profile=GeneratorDeviceProfile())
    assert [e.payload for e in dispenses(day.events)] == [first.payload, second.payload]


def test_the_first_opening_of_a_day_has_no_interval_across_midnight() -> None:
    day1 = run(
        [],
        stream_=fractional_stream(day_index=1),
        device_profile=GeneratorDeviceProfile(),
    )
    opens = dispenses(day1.stream.events)
    assert opens[0].t_device_ms >= DAY
    assert vocab.KEY_INTERVAL not in opens[0].payload
    assert vocab.KEY_INTERVAL in opens[1].payload


def test_the_interval_is_reported_by_the_device_not_derived_from_what_arrived() -> None:
    """A dropout loses an opening but not the interval of the next one, which is measured from the lost opening."""
    out = run(
        [ble(DOSE_TICKS[0] - MIN, 2 * MIN, "dispenser")], stream_=fixture_stream(),
        device_profile=GeneratorDeviceProfile(),
    )  # fmt: skip
    [kept] = dispenses(out.stream.events)
    assert kept.t_device_ms == DOSE_TICKS[1]
    assert kept.payload[vocab.KEY_INTERVAL] == DOSE_TICKS[1] - DOSE_TICKS[0]


def test_no_interval_without_the_capability_or_without_a_profile() -> None:
    for profile in (None, GeneratorDeviceProfile(dispenser_reports_interval=False)):
        out = run([], stream_=fixture_stream(), device_profile=profile)
        assert not any(
            vocab.KEY_INTERVAL in e.payload for e in dispenses(out.stream.events)
        )


def test_assign_dispense_intervals_is_idempotent_and_keeps_other_payload_keys() -> None:
    stream = with_content(fixture_stream())
    once = assign_dispense_intervals(stream)
    twice = assign_dispense_intervals(once)
    assert once.events == twice.events
    assert [e.payload[vocab.KEY_CONTENT_CHANGE] for e in dispenses(once.events)] == [
        1.0,
        1.0,
    ]
    assert [e for e in once.events if e.kind is not EventKind.DISPENSE] == [
        e for e in stream.events if e.kind is not EventKind.DISPENSE
    ]


def test_bounce_has_content_change_zero_and_release_positive() -> None:
    gap = 500  # FIXTURE-ONLY
    out = run(
        [bounce(DOSE_TICKS[0], gap)], stream_=with_content(fixture_stream()),
        device_profile=GeneratorDeviceProfile(), dispenser_content_sensing=True,
    )  # fmt: skip
    real, extra, later = dispenses(out.stream.events)
    assert (real.t_device_ms, extra.t_device_ms) == (DOSE_TICKS[0], DOSE_TICKS[0] + gap)
    assert real.payload[vocab.KEY_CONTENT_CHANGE] == 1.0  # a release is positive
    assert extra.payload[vocab.KEY_CONTENT_CHANGE] == 0.0  # a bounce releases nothing
    assert (
        extra.payload[vocab.KEY_INTERVAL] == gap
    )  # the sub-second interval since the real opening
    assert vocab.KEY_INTERVAL not in real.payload
    assert later.payload[vocab.KEY_CONTENT_CHANGE] == 1.0
    assert later.payload[vocab.KEY_INTERVAL] == DOSE_TICKS[1] - (DOSE_TICKS[0] + gap)
    assert len({real.seq, extra.seq, later.seq}) == 3  # each opening has its own seq


def forgery(level: str, onset: int) -> Any:
    return InjectionSpec(C3, "dispense_forgery", onset, level=level)


def test_a_forged_dispense_reports_the_interval_the_stream_gives() -> None:
    """Naive: whatever the real stream gives. The informed one copies the bounce timing by where it is placed."""
    gap = 500  # FIXTURE-ONLY
    base = with_content(fixture_stream())
    bounced = run(
        [bounce(DOSE_TICKS[0], gap)], stream_=base, device_profile=GeneratorDeviceProfile(),
        dispenser_content_sensing=True,
    )  # fmt: skip
    for level in ("naive", "informed"):
        # a forger placed one bounce gap after a real opening reads like the bounce member of a pair
        forged = run(
            [forgery(level, DOSE_TICKS[0] + gap)], stream_=base, device_profile=GeneratorDeviceProfile(),
        )  # fmt: skip
        opens = dispenses(forged.stream.events)
        extra = [e for e in opens if e.t_device_ms == DOSE_TICKS[0] + gap]
        assert len(extra) == 1
        assert extra[0].payload[vocab.KEY_INTERVAL] == gap
        # the genuine device did not see the forgery: its next opening is measured from the real opening
        later = [e for e in opens if e.t_device_ms == DOSE_TICKS[1]]
        assert later[0].payload[vocab.KEY_INTERVAL] == DOSE_TICKS[1] - DOSE_TICKS[0]
        if (
            level == "informed"
        ):  # the informed forger continues the counter; the naive one repeats a number
            assert len({e.seq for e in opens}) == len(opens)
    assert len(dispenses(bounced.stream.events)) == 3
    # a forged dispense before every real one has no previous opening: no interval
    early = run(
        [forgery("naive", HOUR)], stream_=base, device_profile=GeneratorDeviceProfile()
    )
    first = dispenses(early.stream.events)[0]
    assert first.t_device_ms == HOUR and vocab.KEY_INTERVAL not in first.payload
    # without the capability nothing is added
    quiet = run([forgery("naive", HOUR)], stream_=base)
    assert not any(
        vocab.KEY_INTERVAL in e.payload for e in dispenses(quiet.stream.events)
    )


def test_interval_payload_is_a_declared_integer_key() -> None:
    assert vocab.KEY_INTERVAL == "interval_since_previous_ms"
    assert vocab.KEY_DIAGNOSTICS == "diagnostics"
    assert vocab.DIAGNOSTICS_VALUES == ("ok", "warn", "error", "stale")
    vocab.check_payload(
        EventKind.DISPENSE, {"interval_since_previous_ms": 500, "content_change": 0.0}
    )
    vocab.check_payload(EventKind.DISPENSE, {"interval_since_previous_ms": 0})
    for bad in (-1, 1.5, True, "500", float("nan")):
        with pytest.raises(vocab.VocabularyError):
            vocab.check_payload(EventKind.DISPENSE, {"interval_since_previous_ms": bad})
    vocab.check_payload(
        EventKind.NODE_STATE, {"state": "active", "diagnostics": "stale"}
    )
    for bad in ("fine", 1, None, True):
        with pytest.raises(vocab.VocabularyError):
            vocab.check_payload(
                EventKind.NODE_STATE, {"state": "active", "diagnostics": bad}
            )


# ---------------------------------------------------------------------------
# 9. The robot reports of the builder (ADR-040 (3))
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def robot_pairs(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Any]:
    tmp = tmp_path_factory.mktemp("colocated")
    doc = config_document(
        tmp, n_patients=3, n_days=2, pairs=1,
        variants=["nominal_content_robot", "nominal_content_norobot"],
    )  # fmt: skip
    return build_benchmark(tmp, document=doc)


def test_colocated_events_follow_the_robot_visits(
    robot_pairs: tuple[Path, Any],
) -> None:
    out, manifest = robot_pairs
    reader = open_benchmark(out)
    dwell = 10 * MIN  # the FIXTURE-ONLY robot_dwell_ms of test_builder.GENERATOR_VALUES
    n_robot = n_norobot = 0
    for patient, entry in manifest.patients.items():
        norobot = entry.get("variant_id") == "nominal_content_norobot"
        for d in (*reader.days(patient), reader.tail_day(patient)):
            day = reader.observed(patient, d)
            reports = [
                e for e in day.events
                if e.kind is EventKind.NODE_STATE and e.payload.get("colocated") is not None
            ]  # fmt: skip
            if norobot:
                # a variant without the robot: no report, no presence, no robot event at all
                assert reports == []
                assert not [s for s in day.samples if s.signal == "presence"]
                n_norobot += 1
                continue
            log = reader.truth(patient, d).injection_log or []
            if any(r["subtype"] in ("nav_delay", "manipulation_failure") for r in log):
                continue  # a robot-stage fault moves the task events away from the arrivals
            arrivals = sorted(
                e.t_device_ms for e in day.events
                if e.kind is EventKind.ROBOT_TASK and e.payload.get("task") == "navigate"
            )  # fmt: skip
            assert arrivals, (patient, d)
            true_at = sorted(
                e.t_device_ms for e in reports if e.payload["colocated"] is True
            )
            false_at = sorted(
                e.t_device_ms for e in reports if e.payload["colocated"] is False
            )
            assert true_at == arrivals  # True at the arrival of every visit
            # False where no other visit keeps the robot in the room: the departure of the last visit of a run
            expected_false: list[int] = []
            end: int | None = None
            for a in arrivals:
                if end is not None and a > end:
                    expected_false.append(end)
                    end = None
                end = a + dwell if end is None else max(end, a + dwell)
            if end is not None:
                expected_false.append(end)
            assert false_at == expected_false
            for e in reports:
                assert e.source == "robot" and e.payload["state"] == "active"
                assert type(e.payload["colocated"]) is bool
            n_robot += 1
    assert n_robot >= 4 and n_norobot >= 2
