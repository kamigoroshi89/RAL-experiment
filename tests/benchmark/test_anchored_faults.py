"""Cuff faults anchored to the readings of the day (WS04-T16, ADR-070 (a), (b), (d)).

FIXTURE-ONLY where it builds anything: the fixture prior and registry F0 of ``test_builder``, hand-built
observed days (``test_inject_c2.fixture_stream``) and arithmetic values. The committed
``configs/benchmark/injections.yaml`` and the real registry 0.2.1 are only read: the readings of the default
day are derived from them, never typed here. None of the numbers is a clinical value.

What is under test
------------------
* the rule of ADR-070 (a): the first covered reading is drawn uniformly among the ``n - k + 1`` feasible ones, the
  onset uniformly on the grid in (previous reading, first covered reading], the end uniformly on the grid in
  (last covered reading, next reading] (up to the day end after the last one); exact enumeration, not sampling;
* the real injectors realise every anchored window of ``cuff_detached`` and ``cuff_silent_bias`` on a fault-free
  day, and ``stuck_at`` freezes the last reading of the previous evening (``InjectionContext.previous_day``);
  the first scored day of a patient is excluded from the draw of ``stuck_at`` and the manifest says so;
* the truth records the EFFECTIVE number of readings (after the robot stage) next to the drawn one;
* the nine duration rows are in readings (1, 2, 3); the loader refuses ms for these three subtypes only;
* determinism, and the committed observability table of ``docs/benchmark/builder.md`` is the generator's output.
"""

from __future__ import annotations

import dataclasses
import itertools
import re
import subprocess
import sys
from bisect import bisect_left
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
import yaml

from ralmon.benchmark.anchoring import (
    ANCHORED_SUBTYPES,
    anchored_choices,
    draw_anchored_window,
    observability_table,
)
from ralmon.benchmark.builder import (
    BenchmarkConfigError,
    BuildContext,
    load_config,
    open_benchmark,
)
from ralmon.benchmark.injection import (
    InjectionContext,
    InjectionDesignError,
    apply_observation_injections,
    ground_truth_events,
    load_injection_design,
    record_to_ground_truth,
)
from ralmon.benchmark.latent import T_DAY_MS
from ralmon.benchmark.priors import LiteraturePriorSource
from ralmon.benchmark.schedule import load_filled_rows, load_schedule
from ralmon.spec.registry import load_registry

from .test_builder import (
    CARE_PLANS,
    GENERATOR_DESIGN,
    INJECTIONS_FILE,
    ROOT,
    build,
    config_document,
    make_prior,
    write_config,
    write_injections,
)
from .test_inject_c2 import (
    bias,
    detached,
    fixture_stream,
    manip,
    nav,
    run,
    stuck,
)

DAY = T_DAY_MS
HOUR = 3_600_000
MIN = 60_000
STEP = MIN
REGISTRY = ROOT / "configs" / "registry" / "hypertension.yaml"
BUILDER_DOC = ROOT / "docs" / "benchmark" / "builder.md"
TABLE_SCRIPT = ROOT / "tools" / "anchored_observability_table.py"

# The enumeration of the research file (docs/benchmark/evidence/group1-design-options.md, section 1) on the
# default day: per k, the number of onsets and of ends for each feasible first reading.
EXPECTED_SHAPES = {
    1: [(376, 120), (120, 360), (360, 360), (360, 120), (120, 105)],
    2: [(376, 360), (120, 360), (360, 120), (360, 105)],
    3: [(376, 360), (120, 120), (360, 105)],
}


def default_ticks() -> tuple[int, ...]:
    """The measurement ticks of the committed schedule under the real registry 0.2.1 (read, not typed)."""
    registry = load_registry(REGISTRY, step_ms=STEP)
    windows = {
        f"{name}_ms": int(registry.get(name).value)
        for name in ("hold_lookback", "delta1", "delta2", "sched_window")
    }
    return tuple(load_schedule(CARE_PLANS, **windows).measurement_ticks_ms)


def default_readings() -> list[int]:
    """The reading instants of a fault-free default day: tick plus the nominal inflation, no jitter."""
    rows = load_filled_rows(GENERATOR_DESIGN, ("inflation_ms_nominal",))
    inflation = int(rows["inflation_ms_nominal"])
    return [t + inflation for t in default_ticks()]


def design_ks() -> tuple[int, ...]:
    """The numbers of readings of the duration rows of the three subtypes (read from the design)."""
    design = load_injection_design(INJECTIONS_FILE, section="c2")
    values = {
        int(level.value)
        for subtype in ANCHORED_SUBTYPES
        for level in design[subtype].duration.levels
    }
    return tuple(sorted(values))


def covered(readings: Sequence[int], onset: int, end: int) -> int:
    """Independent count of the readings in the window ``[onset, end)``."""
    return bisect_left(readings, end) - bisect_left(readings, onset)


# ---------------------------------------------------------------------------------------------------
# 1. The rule, by exact enumeration
# ---------------------------------------------------------------------------------------------------


def test_the_default_day_has_five_readings_at_the_documented_instants() -> None:
    readings = default_readings()
    assert len(readings) == 5
    assert [r // MIN for r in readings] == [
        6 * 60 + 15,
        8 * 60 + 15,
        14 * 60 + 15,
        20 * 60 + 15,
        22 * 60 + 15,
    ]
    assert all(r % MIN == 30_000 for r in readings)


@pytest.mark.parametrize("k", [1, 2, 3])
def test_a_window_covers_exactly_k_readings(k: int) -> None:
    readings = default_readings()
    choices = anchored_choices(
        readings, k, step_ms=STEP, day_start_ms=0, day_end_ms=DAY
    )
    assert len(choices) == len(readings) - k + 1 == {1: 5, 2: 4, 3: 3}[k]
    assert [c.first for c in choices] == list(range(len(choices)))
    assert [(len(c.onsets), len(c.ends)) for c in choices] == EXPECTED_SHAPES[k]
    pairs = 0
    for choice in choices:
        for onset, end in itertools.product(choice.onsets, choice.ends):
            pairs += 1
            assert onset % STEP == 0 and end % STEP == 0  # on the grid
            assert (
                0 <= onset < end <= DAY
            )  # inside the day, ends before (or at) the day end
            assert covered(readings, onset, end) == k, (choice.first, onset, end)
            # the covered readings are exactly the ones the choice names
            assert bisect_left(readings, onset) == choice.first
    assert pairs == sum(a * b for a, b in EXPECTED_SHAPES[k])


def test_the_rule_with_fewer_readings_than_k_has_no_choice() -> None:
    readings = default_readings()
    assert (
        anchored_choices(readings[:2], 3, step_ms=STEP, day_start_ms=0, day_end_ms=DAY)
        == ()
    )
    assert anchored_choices([], 1, step_ms=STEP, day_start_ms=0, day_end_ms=DAY) == ()
    two = anchored_choices(
        readings[:2], 2, step_ms=STEP, day_start_ms=0, day_end_ms=DAY
    )
    assert len(two) == 1 and two[0].first == 0


def test_the_rule_on_a_later_day_and_with_readings_off_the_grid() -> None:
    day = 3
    start, end = day * DAY, (day + 1) * DAY
    readings = [start + 7 * HOUR + 17, start + 9 * HOUR + 59_999, start + 15 * HOUR]
    for k in (1, 2, 3):
        for choice in anchored_choices(
            readings, k, step_ms=STEP, day_start_ms=start, day_end_ms=end
        ):
            for onset, stop in itertools.product(choice.onsets, choice.ends):
                assert (onset - start) % STEP == 0 and (stop - start) % STEP == 0
                assert start <= onset < stop <= end
                assert covered(readings, onset, stop) == k


def test_two_readings_in_one_grid_cell_cannot_be_isolated() -> None:
    readings = [10 * HOUR + 5_000, 10 * HOUR + 20_000, 12 * HOUR]
    choices = anchored_choices(
        readings, 1, step_ms=STEP, day_start_ms=0, day_end_ms=DAY
    )
    # no grid instant lies in (10:00:05, 10:00:20]: a window can neither end between the two readings
    # (reading 0 alone) nor start between them (reading 1 alone), so only the third reading is a choice
    assert [c.first for c in choices] == [2]
    for choice in choices:
        for onset, end in itertools.product(choice.onsets, choice.ends):
            assert covered(readings, onset, end) == 1


def test_the_draw_covers_every_first_reading_and_stays_inside_the_choice() -> None:
    readings = default_readings()
    choices = anchored_choices(
        readings, 2, step_ms=STEP, day_start_ms=0, day_end_ms=DAY
    )
    firsts: Counter[int] = Counter()
    for seed in range(400):
        onset, end, first = draw_anchored_window(np.random.default_rng(seed), choices)
        firsts[first] += 1
        choice = choices[first]
        assert onset in choice.onsets and end in choice.ends
        assert covered(readings, onset, end) == 2
    assert set(firsts) == {0, 1, 2, 3}
    assert (
        min(firsts.values()) > 60
    )  # uniform over the four choices (100 expected), not over (onset, end) pairs


# ---------------------------------------------------------------------------------------------------
# 2. The real injectors realise every anchored window of cuff_detached and cuff_silent_bias
# ---------------------------------------------------------------------------------------------------


def sample_pairs(choices: Sequence[Any], seed: int) -> list[tuple[int, int, int]]:
    """The four corners of every choice and 20 seeded random pairs: ``(first, onset, end)``."""
    rng = np.random.default_rng(seed)
    out: list[tuple[int, int, int]] = []
    for choice in choices:
        corners = itertools.product(
            (choice.onsets[0], choice.onsets[-1]), (choice.ends[0], choice.ends[-1])
        )
        out += [(choice.first, o, e) for o, e in corners]
        for _ in range(20):
            out.append(
                (
                    choice.first,
                    choice.onsets[int(rng.integers(0, len(choice.onsets)))],
                    choice.ends[int(rng.integers(0, len(choice.ends)))],
                )
            )
    return out


@pytest.mark.parametrize("k", [1, 2, 3])
def test_realised_share_is_one_for_detached_and_bias(k: int) -> None:
    ticks = default_ticks()
    readings = default_readings()
    base = fixture_stream(ticks)
    assert sorted(s.t_device_ms for s in base.samples if s.signal == "bp") == readings
    choices = anchored_choices(
        readings, k, step_ms=STEP, day_start_ms=0, day_end_ms=DAY
    )
    pairs = sample_pairs(choices, seed=k)
    assert len(pairs) >= 24 * len(choices)
    for first, onset, end in pairs:
        for make in (detached, lambda o, d: bias(o, d, 8.0)):
            [record] = run([make(onset, end - onset)], stream_=base).records
            assert record.realised, (record.spec.subtype, first, onset, end)
            assert record.details["n_readings_covered"] == k
    # the planner of the builder produces such windows: every cuff_detached and cuff_silent_bias it draws on a
    # fault-free day is realised (a 40 patient x 6 day seeded loop through plan_observation)
    context = planner_context(rates=(0.0, 3.0, 0.0))
    cohort = context.cohorts["main"]
    latent: Any = SimpleNamespace(latent=SimpleNamespace(events=[]))
    seen: Counter[str] = Counter()
    for patient_index in range(40):
        for day in range(6):
            stream_ = fixture_stream(ticks, day_index=day)
            specs = context.plan_observation(
                cohort, patient_index, day, latent, stream_, Counter()
            )
            for spec in specs:
                if spec.subtype not in ("cuff_detached", "cuff_silent_bias"):
                    continue
                [record] = apply_observation_injections(
                    stream_,
                    [spec],
                    InjectionContext(patient_index, task_deadline_offset_ms=MIN),
                ).records
                seen[spec.subtype] += 1
                assert record.realised, spec
                assert 1 <= record.details["n_readings_covered"] <= 3
    assert seen["cuff_detached"] > 20 and seen["cuff_silent_bias"] > 20


# ---------------------------------------------------------------------------------------------------
# 3. stuck_at: the previous evening, and the first scored day is excluded
# ---------------------------------------------------------------------------------------------------

PREVIOUS_VALUES = [131.0, 126.0, 138.0, 129.0, 143.0]
TODAY_VALUES = [120.0, 121.0, 122.0, 123.0, 124.0]


def two_days() -> tuple[Any, Any]:
    ticks = default_ticks()
    previous = fixture_stream(ticks, PREVIOUS_VALUES, day_index=0)
    today = fixture_stream(ticks, TODAY_VALUES, day_index=1)
    return previous, today


def bp_values(result: Any) -> list[float]:
    return [s.value for s in result.stream.samples if s.signal == "bp"]


def test_stuck_at_uses_the_previous_evening() -> None:
    previous, today = two_days()
    readings = default_readings()
    onset = (
        DAY + 2 * HOUR
    )  # before the first reading of the day: nothing earlier in the day's stream
    window = stuck(
        onset, 5 * HOUR
    )  # 02:00 to 07:00: covers the reading at 06:15:30 only
    assert covered([DAY + r for r in readings], onset, onset + 5 * HOUR) == 1
    # day 1 with its previous day: the frozen value is the last reading of the previous evening
    out = run([window], stream_=today, previous_day=previous)
    [record] = out.records
    assert record.realised and record.n_changed == 1
    assert record.details["frozen_value"] == PREVIOUS_VALUES[-1]
    assert record.details["frozen_from"] == "previous_day"
    assert record.details["n_readings_covered"] == 1
    assert bp_values(out)[0] == PREVIOUS_VALUES[-1]
    assert bp_values(out)[1:] == TODAY_VALUES[1:]
    # without a previous day (the first scored day) there is nothing to freeze: unrealised, as before
    bare = fixture_stream(default_ticks(), TODAY_VALUES, day_index=0)
    [record] = run([stuck(2 * HOUR, 5 * HOUR)], stream_=bare).records
    assert not record.realised
    assert record.details["reason"] == "no earlier reading to freeze"
    assert record.details["n_readings_covered"] == 1
    # an earlier reading of the same day wins over the previous evening
    later = stuck(
        DAY + 9 * HOUR, 7 * HOUR
    )  # first covered reading 14:15:30, earlier one 08:15:30
    [record] = run([later], stream_=today, previous_day=previous).records
    assert record.details["frozen_value"] == TODAY_VALUES[1]
    assert record.details["frozen_from"] == "same_day"
    # a previous day with no reading leaves nothing to freeze
    empty = fixture_stream(default_ticks(), PREVIOUS_VALUES, day_index=0)
    no_bp = dataclasses.replace(
        empty, samples=tuple(s for s in empty.samples if s.signal != "bp")
    )
    [record] = run([window], stream_=today, previous_day=no_bp).records
    assert not record.realised
    assert record.details["reason"] == "no earlier reading to freeze"


def planner_context(
    rates: tuple[float, float, float] = (0.0, 3.0, 0.0),
) -> BuildContext:
    tmp = _scratch()
    prior_path = make_prior(tmp)
    doc = config_document(
        tmp, prior=prior_path, pairs=0, variants=[], n_patients=1, n_days=1, rates=rates
    )
    config = load_config(write_config(tmp, doc))
    prior = LiteraturePriorSource(prior_path, strict=False, allow_fixture_only=True)
    return BuildContext.create(config, prior, allow_fixture_only=True)


_SCRATCH: list[Path] = []


def _scratch() -> Path:
    import tempfile

    path = Path(tempfile.mkdtemp(prefix="anchored-faults-"))
    _SCRATCH.append(path)
    return path


@pytest.fixture(scope="module", autouse=True)
def _cleanup_scratch():  # type: ignore[no-untyped-def]
    yield
    import shutil

    for path in _SCRATCH:
        shutil.rmtree(path, ignore_errors=True)
    _SCRATCH.clear()


def test_the_planner_never_draws_stuck_at_on_the_first_day_and_realises_it_afterwards() -> (
    None
):
    context = planner_context()
    cohort = context.cohorts["main"]
    ticks = default_ticks()
    latent: Any = SimpleNamespace(latent=SimpleNamespace(events=[]))
    first_day_skipped = 0
    by_day: Counter[int] = Counter()
    realised: Counter[int] = Counter()
    for patient_index in range(60):
        for day in range(7):
            skipped: Counter[str] = Counter()
            stream_ = fixture_stream(ticks, day_index=day, seed=patient_index)
            specs = context.plan_observation(
                cohort, patient_index, day, latent, stream_, skipped
            )
            if day == 0:
                assert all(s.subtype != "stuck_at" for s in specs)
                first_day_skipped += skipped["c2/stuck_at/first_day"]
            previous = (
                fixture_stream(ticks, day_index=day - 1, seed=patient_index)
                if day > 0
                else None
            )
            for spec in specs:
                if spec.subtype != "stuck_at":
                    continue
                by_day[day] += 1
                [record] = apply_observation_injections(
                    stream_,
                    [spec],
                    InjectionContext(
                        patient_index,
                        task_deadline_offset_ms=MIN,
                        previous_day=previous,
                    ),
                ).records
                realised[day] += int(record.realised)
    assert (
        first_day_skipped > 0
    )  # the draws that fell on day 0 are counted, not silently lost
    assert 0 not in by_day
    assert set(by_day) == {1, 2, 3, 4, 5, 6}
    assert sum(by_day.values()) > 40
    # the realised share is 1 on days 1 to 6: every anchored window holds a reading and has a value to freeze
    # (a reading equal to the frozen value would not count as changed: the fixture values differ by construction)
    assert realised == by_day


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Any]:
    tmp = tmp_path_factory.mktemp("anchored_build")
    return build(
        tmp,
        "bench",
        pairs=0,
        variants=[],
        n_patients=6,
        n_days=3,
        rates=(0.0, 3.0, 0.0),
    )


def test_the_manifest_records_the_day_zero_exclusion_and_the_unit(
    built: tuple[Path, Any],
) -> None:
    _, manifest = built
    block = manifest.settings["anchored_cuff_faults"]
    assert block["subtypes"] == sorted(ANCHORED_SUBTYPES)
    assert block["duration_unit"] == "readings"
    assert block["stuck_at_excluded_day_indices"] == [0]
    out, _ = built
    reader = open_benchmark(out)
    for patient in reader.patient_ids(role="patient"):
        entries = reader.truth(patient, 0).injection_log
        assert all(e["subtype"] != "stuck_at" for e in entries)


# ---------------------------------------------------------------------------------------------------
# 4. The effective k, after the robot stage
# ---------------------------------------------------------------------------------------------------


LEDGER = (
    "n_readings_drawn",
    "n_readings_lost_robot",
    "n_readings_gained_robot",
    "n_readings_lost_device",
    "n_readings_covered",
)


def ledger(record: Any) -> tuple[int, int, int, int, int]:
    """``(drawn, lost to the robot stage, gained from it, lost to an earlier device fault, covered)``."""
    values = tuple(record.details[key] for key in LEDGER)
    drawn, lost_robot, gained, lost_device, got = values
    assert got == drawn - lost_robot + gained - lost_device  # the ledger balances
    return values  # type: ignore[return-value]


def only(out: Any, subtype: str) -> Any:
    [record] = [r for r in out.records if r.spec.subtype == subtype]
    return record


def test_effective_k_after_the_robot_stage() -> None:
    ticks = default_ticks()
    readings = default_readings()
    base = fixture_stream(ticks)
    # a window of k = 2 readings (08:15:30 and 14:15:30); the robot fails the manipulation of the 14:15 visit
    onset, end = 8 * HOUR, 15 * HOUR
    assert covered(readings, onset, end) == 2
    cases = {
        "cuff_detached": detached(onset, end - onset),
        "cuff_silent_bias": bias(onset, end - onset, 8.0),
        "stuck_at": stuck(onset, end - onset),
    }
    for subtype, window in cases.items():
        out = run([manip(ticks[2]), window], stream_=base)
        record = only(out, subtype)
        assert ledger(record) == (2, 1, 0, 0, 1), subtype
        assert record.realised, subtype
    # a delayed visit can also bring a reading INTO the window: drawn 1, covered 2
    narrow = (8 * HOUR, 9 * HOUR)  # holds the 08:15:30 reading only
    assert covered(readings, *narrow) == 1
    for subtype, make in (
        ("cuff_detached", detached),
        ("cuff_silent_bias", lambda o, d: bias(o, d, 8.0)),
        ("stuck_at", stuck),
    ):
        out = run(
            [nav(ticks[0], 110 * MIN, kind="measurement"), make(narrow[0], HOUR)],
            stream_=base,
            task_deadline_offset_ms=30 * MIN,
        )
        assert ledger(only(out, subtype)) == (1, 0, 1, 0, 2), subtype
    # a record of another subtype carries no ledger
    [other] = run([manip(ticks[1])], stream_=base).records
    assert not set(LEDGER) & set(other.details)


def test_the_robot_loss_is_split_into_removed_and_moved_out() -> None:
    ticks = default_ticks()
    base = fixture_stream(ticks)
    window = (8 * HOUR, 9 * HOUR)  # the 08:15:30 reading only
    removed = only(
        run([manip(ticks[1]), detached(window[0], HOUR)], stream_=base),
        "cuff_detached",
    )
    assert removed.details["n_readings_lost_robot"] == 1
    assert removed.details["n_readings_removed_robot"] == 1
    moved = only(
        run(
            [nav(ticks[1], 110 * MIN, kind="measurement"), detached(window[0], HOUR)],
            stream_=base,
            task_deadline_offset_ms=30 * MIN,
        ),
        "cuff_detached",
    )
    assert (
        moved.details["n_readings_lost_robot"] == 1
    )  # moved to 10:05, out of the window
    assert moved.details["n_readings_removed_robot"] == 0
    assert moved.details["n_readings_covered"] == 0 and not moved.realised


def test_a_reading_moved_inside_the_window_is_neither_lost_nor_gained() -> None:
    ticks = default_ticks()
    base = fixture_stream(ticks)
    onset, end = 8 * HOUR, 15 * HOUR  # readings 08:15:30 and 14:15:30
    # the 08:15 visit arrives 30 minutes late: the reading moves to 08:45:30, still inside the window
    out = run(
        [nav(ticks[1], 30 * MIN, kind="measurement"), detached(onset, end - onset)],
        stream_=base,
        task_deadline_offset_ms=60 * MIN,
    )
    assert ledger(only(out, "cuff_detached")) == (2, 0, 0, 0, 2)


def test_a_device_fault_before_the_bias_is_counted_apart_from_the_robot_stage() -> None:
    ticks = default_ticks()
    base = fixture_stream(ticks)
    onset, end = 8 * HOUR, 15 * HOUR  # readings 08:15:30 and 14:15:30
    out = run(
        [detached(7 * HOUR, 2 * HOUR), bias(onset, end - onset, 8.0)], stream_=base
    )
    assert ledger(only(out, "cuff_silent_bias")) == (2, 0, 0, 1, 1)
    assert ledger(only(out, "cuff_detached")) == (1, 0, 0, 0, 1)
    # both causes at once: the robot fails 14:15 and the detached window removes 08:15
    out = run(
        [manip(ticks[2]), detached(7 * HOUR, 2 * HOUR), stuck(onset, end - onset)],
        stream_=base,
    )
    assert ledger(only(out, "stuck_at")) == (2, 1, 0, 1, 0)
    assert not only(out, "stuck_at").realised  # nothing left in the window: unrealised


def test_a_direct_call_has_nothing_lost() -> None:
    base = fixture_stream(default_ticks())
    out = run([bias(8 * HOUR, 7 * HOUR, 8.0)], stream_=base)
    assert ledger(only(out, "cuff_silent_bias")) == (2, 0, 0, 0, 2)


def test_covered_counts_the_bp_readings_for_the_three_subtypes() -> None:
    """``cuff_detached`` counts ``bp`` samples like the others; ``n_attempts`` counts MEASUREMENT events."""
    ticks = default_ticks()
    base = fixture_stream(ticks)
    onset, end = 8 * HOUR, 15 * HOUR
    for subtype, window in (
        ("cuff_detached", detached(onset, end - onset)),
        ("cuff_silent_bias", bias(onset, end - onset, 8.0)),
        ("stuck_at", stuck(onset, end - onset)),
    ):
        record = only(run([window], stream_=base), subtype)
        assert record.details["n_readings_covered"] == 2
    record = only(run([detached(onset, end - onset)], stream_=base), "cuff_detached")
    assert record.details["n_attempts"] == 2
    # a MEASUREMENT event whose bp sample is missing is an attempt but not a reading
    lone = dataclasses.replace(
        base,
        samples=tuple(
            s
            for s in base.samples
            if not (s.signal == "bp" and s.t_device_ms == default_readings()[1])
        ),
    )
    record = only(run([detached(onset, end - onset)], stream_=lone), "cuff_detached")
    assert record.details["n_attempts"] == 2
    assert record.details["n_readings_covered"] == 1


def test_a_fault_that_covers_no_reading_is_unrealised_and_is_no_positive() -> None:
    ticks = default_ticks()
    base = fixture_stream(ticks)
    onset, end = (
        8 * HOUR,
        9 * HOUR,
    )  # the 08:15:30 reading only; the robot fails that visit
    for subtype, window in (
        ("cuff_detached", detached(onset, end - onset)),
        ("cuff_silent_bias", bias(onset, end - onset, 8.0)),
        ("stuck_at", stuck(onset, end - onset)),
    ):
        out = run([manip(ticks[1]), window], stream_=base)
        record = only(out, subtype)
        assert record.details["n_readings_covered"] == 0, subtype
        assert not record.realised and record.n_changed == 0, subtype
        assert record_to_ground_truth(record) is None, subtype
        assert ground_truth_events(out.records) == [
            e for e in ground_truth_events(out.records) if e.subtype != subtype
        ]


def zero_covered_build(tmp_path: Path) -> tuple[Path, Any]:
    return build(
        tmp_path,
        "zero",
        pairs=0,
        variants=[],
        n_patients=10,
        n_days=4,
        rates=(0.0, 4.0, 0.0),
    )


def test_unrealised_cuff_faults_are_no_positive_anywhere_and_are_counted(
    tmp_path: Path,
) -> None:
    out, manifest = zero_covered_build(tmp_path)
    reader = open_benchmark(out)
    zero: Counter[str] = Counter()
    for patient in reader.patient_ids(role="patient"):
        for day in range(manifest.settings["n_scored_days"]):
            truth = reader.truth(patient, day)
            positives = Counter(
                (e.subtype, e.onset_ms, e.end_ms)
                for e in truth.ground_truth
                if e.injected
            )
            for entry in truth.injection_log:
                if entry["subtype"] not in ANCHORED_SUBTYPES:
                    continue
                key = (entry["subtype"], entry["onset_ms"], entry["end_ms"])
                if entry["details"]["n_readings_covered"] == 0:
                    zero[f"c2/{entry['subtype']}/covered_zero"] += 1
                    assert entry["realised"] is False
                    assert entry["truth_indices"] == []
                    assert positives[key] == 0
                else:
                    assert (positives[key] > 0) == bool(entry["realised"])
    assert sum(zero.values()) > 0  # the build is large enough to contain some
    assert dict(sorted(zero.items())) == manifest.settings["plan_unrealised"]


def test_manifest_tallies_the_ledger_by_drawn_k(tmp_path: Path) -> None:
    out, manifest = zero_covered_build(tmp_path)
    block = manifest.settings["anchored_cuff_faults"]["by_drawn_k"]
    reader = open_benchmark(out)
    expected: dict[str, dict[str, Counter[str]]] = {}
    for patient in reader.patient_ids(role="patient"):
        for day in range(manifest.settings["n_scored_days"]):
            for entry in reader.truth(patient, day).injection_log:
                if entry["subtype"] not in ANCHORED_SUBTYPES:
                    continue
                d = entry["details"]
                cell = expected.setdefault(entry["subtype"], {}).setdefault(
                    str(d["n_readings_drawn"]), Counter()
                )
                cell["draws"] += 1
                cell["readings_drawn"] += d["n_readings_drawn"]
                cell["lost_robot"] += d["n_readings_lost_robot"]
                cell["removed_robot"] += d["n_readings_removed_robot"]
                cell["gained_robot"] += d["n_readings_gained_robot"]
                cell["lost_device"] += d["n_readings_lost_device"]
                cell["covered_differs"] += int(
                    d["n_readings_covered"] != d["n_readings_drawn"]
                )
                cell["covered_zero"] += int(d["n_readings_covered"] == 0)
    assert block == {
        s: {k: dict(sorted(c.items())) for k, c in sorted(per.items())}
        for s, per in sorted(expected.items())
    }
    assert sum(c["draws"] for per in expected.values() for c in per.values()) > 20


def test_day_zero_wording_is_drawn_and_not_placed() -> None:
    document = yaml.safe_load(INJECTIONS_FILE.read_text(encoding="utf-8"))
    for row in document["parameters"]:
        if row["parameter"].startswith("stuck_at_duration_"):
            text = " ".join(str(row["rationale"]).split())
            assert "drawn and not placed" in text
            assert "excluded from the draw" not in text
    doc = " ".join(BUILDER_DOC.read_text(encoding="utf-8").split())
    assert "drawn and not placed" in doc
    assert "excluded from the draw" not in doc
    assert (
        "5/6" in doc and "6/7" in doc
    )  # the day-0 C2 rate and the planned count of stuck_at
    source = (ROOT / "src" / "ralmon" / "benchmark" / "builder.py").read_text(
        encoding="utf-8"
    )
    assert "excluded from the draw" not in source


def test_the_documents_state_that_the_truth_interval_does_not_shrink() -> None:
    doc = " ".join(BUILDER_DOC.read_text(encoding="utf-8").split())
    assert "does not shrink with the effective k" in doc
    t12 = (
        ROOT
        / "docs"
        / "plan"
        / "workstreams"
        / "WS04-benchmark"
        / "tasks"
        / "T12-benchmark-validation.md"
    ).read_text(encoding="utf-8")
    assert "does not shrink with the effective k" in " ".join(t12.split())


def test_the_table_script_runs_with_plain_python3_or_fails_clearly() -> None:
    result = subprocess.run(
        ["python3", str(TABLE_SCRIPT), "--check"],
        capture_output=True, text=True, cwd="/", check=False,
    )  # fmt: skip
    assert "Traceback" not in result.stderr, result.stderr
    assert result.returncode in (0, 2), result.stderr
    if result.returncode == 2:
        assert "cannot" in result.stderr


def test_a_design_without_a_reading_duration_is_a_configuration_error(
    tmp_path: Path,
) -> None:
    context = planner_context()
    entry = context.design.c2["stuck_at"]
    broken = dataclasses.replace(entry, duration=None)
    context.design = dataclasses.replace(  # type: ignore[misc]
        context.design, c2={**context.design.c2, "stuck_at": broken}
    )
    with pytest.raises(BenchmarkConfigError, match="stuck_at"):
        context._check_reading_rows()


def cuff_entries(out: Path) -> list[tuple[str, int, dict[str, Any]]]:
    reader = open_benchmark(out)
    entries: list[tuple[str, int, dict[str, Any]]] = []
    for patient in reader.patient_ids(role="patient"):
        for day in range(reader.manifest.settings["n_scored_days"]):
            for entry in reader.truth(patient, day).injection_log:
                if entry["subtype"] in ANCHORED_SUBTYPES:
                    entries.append((patient, day, entry))
    return entries


def test_the_truth_log_and_the_manifest_carry_the_effective_k(
    built: tuple[Path, Any],
) -> None:
    out, manifest = built
    entries = cuff_entries(out)
    assert len(entries) > 10
    tally: dict[str, Counter[str]] = {}
    for _, _, entry in entries:
        details = entry["details"]
        drawn, got = details["n_readings_drawn"], details["n_readings_covered"]
        assert isinstance(drawn, int) and isinstance(got, int)
        assert 1 <= drawn <= 3 and got >= 0
        if entry["subtype"] != "stuck_at":
            assert entry["realised"] == (got > 0)  # the truth follows the effective k
        tally.setdefault(entry["subtype"], Counter())[f"{drawn}->{got}"] += 1
    block = manifest.settings["anchored_cuff_faults"]["readings_drawn_to_covered"]
    assert {k: dict(sorted(v.items())) for k, v in tally.items()} == block
    realised = manifest.settings["anchored_cuff_faults"]["realised"]
    for subtype in ANCHORED_SUBTYPES:
        mine = [e for _, _, e in entries if e["subtype"] == subtype]
        assert realised.get(subtype, {"realised": 0, "placed": 0}) == {
            "realised": sum(1 for e in mine if e["realised"]),
            "placed": len(mine),
        }


# ---------------------------------------------------------------------------------------------------
# 5. The duration rows are in readings
# ---------------------------------------------------------------------------------------------------


def committed_design() -> dict[str, Any]:
    return load_injection_design(INJECTIONS_FILE, section="c2")


@pytest.mark.parametrize("subtype", sorted(ANCHORED_SUBTYPES))
def test_duration_rows_are_in_readings(subtype: str) -> None:
    entry = committed_design()[subtype]
    assert entry.duration is not None
    assert entry.duration.unit == "readings" and entry.duration.key == "n_readings"
    levels = entry.duration.levels
    assert [lv.level for lv in levels] == ["short", "medium", "long"]
    assert [lv.name for lv in levels] == [
        f"{subtype}_duration_{n}" for n in ("short", "medium", "long")
    ]
    assert [lv.value for lv in levels] == [1.0, 2.0, 3.0]
    assert all(lv.unit == "readings" and lv.filled for lv in levels)
    assert all(lv.source_type == "design_choice" for lv in levels)
    n_readings = len(default_ticks())
    assert all(1 <= lv.value <= n_readings for lv in levels)
    # the other duration blocks of the same file are still in ms
    for other in ("ble_dropout", "ecg_noise"):
        block = committed_design()[other].duration
        assert block is not None and block.unit == "ms"
        assert all(lv.unit == "ms" for lv in block.levels)


def test_the_nine_rows_carry_the_provenance_adr_070_asks_for() -> None:
    document = yaml.safe_load(INJECTIONS_FILE.read_text(encoding="utf-8"))
    rows = {r["parameter"]: r for r in document["parameters"]}
    for subtype in ANCHORED_SUBTYPES:
        for level, value in (("short", 1), ("medium", 2), ("long", 3)):
            row = rows[f"{subtype}_duration_{level}"]
            assert row["unit"] == "readings" and row["value"] == value
            assert type(row["value"]) is int
            assert row["status"] == "filled" and row["source_type"] == "design_choice"
            assert row["verified_by"] is None
            assert "proposal accepted by gab 2026-10-10, not reviewed" in " ".join(
                str(row["rationale"]).split()
            )
            assert "ADR-070 (a)" in " ".join(str(row["source_ref"]).split())


def mutated(tmp_path: Path, mutate: Callable[[dict[str, Any]], None]) -> Path:
    document = yaml.safe_load(INJECTIONS_FILE.read_text(encoding="utf-8"))
    mutate(document)
    path = tmp_path / "injections.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def set_row(document: dict[str, Any], name: str, **fields: Any) -> None:
    [row] = [r for r in document["parameters"] if r["parameter"] == name]
    row.update(fields)


def test_a_duration_in_ms_is_refused_for_the_three_subtypes_with_a_named_error(
    tmp_path: Path,
) -> None:
    def block_in_ms(document: dict[str, Any]) -> None:
        document["injections"]["c2"]["cuff_detached"]["duration"]["unit"] = "ms"

    def row_in_ms(document: dict[str, Any]) -> None:
        set_row(document, "stuck_at_duration_short", unit="ms", value=60_000)

    for edit in (block_in_ms, row_in_ms):
        with pytest.raises(InjectionDesignError, match="readings"):
            load_injection_design(mutated(tmp_path, edit), section="c2")


def test_the_other_subtypes_still_require_ms(tmp_path: Path) -> None:
    def readings_for_ble(document: dict[str, Any]) -> None:
        document["injections"]["c2"]["ble_dropout"]["duration"]["unit"] = "readings"

    with pytest.raises(InjectionDesignError, match="ms"):
        load_injection_design(mutated(tmp_path, readings_for_ble), section="c2")


@pytest.mark.parametrize(
    ("fields", "match"),
    [
        ({"cuff_silent_bias_duration_short": 1.5}, "integer"),
        ({"cuff_silent_bias_duration_short": 0}, "at least 1"),
        (
            {"cuff_silent_bias_duration_short": 3, "cuff_silent_bias_duration_long": 1},
            "ordered",
        ),
        ({"cuff_silent_bias_duration_medium": 1}, "ordered"),
    ],
)
def test_reading_counts_must_be_integers_of_at_least_one_and_ordered(
    tmp_path: Path, fields: dict[str, float], match: str
) -> None:
    def edit(document: dict[str, Any]) -> None:
        for name, value in fields.items():
            set_row(document, name, value=value)

    with pytest.raises(InjectionDesignError, match=match):
        load_injection_design(mutated(tmp_path, edit), section="c2")


def test_a_count_above_the_readings_of_the_day_is_a_configuration_error(
    tmp_path: Path,
) -> None:
    n_readings = len(default_ticks())

    def too_long(document: dict[str, Any]) -> None:
        set_row(document, "stuck_at_duration_long", value=n_readings + 1)

    doc = config_document(tmp_path, pairs=0, variants=[], n_patients=1, n_days=1)
    path = write_injections(tmp_path, mutate=too_long)
    doc["paths"]["injections"] = str(path)
    config = load_config(write_config(tmp_path, doc))
    prior = LiteraturePriorSource(
        Path(doc["cohorts"][0]["prior"]), strict=False, allow_fixture_only=True
    )
    with pytest.raises(BenchmarkConfigError, match="readings"):
        BuildContext.create(config, prior, allow_fixture_only=True)


# ---------------------------------------------------------------------------------------------------
# 6. Determinism, and a change of k changes only the affected injection
# ---------------------------------------------------------------------------------------------------


def test_the_plan_is_deterministic(tmp_path: Path) -> None:
    kwargs: dict[str, Any] = {
        "pairs": 0,
        "variants": [],
        "n_patients": 3,
        "n_days": 2,
        "rates": (0.0, 3.0, 0.0),
    }
    a, manifest_a = build(tmp_path, "a", **kwargs)
    b, manifest_b = build(tmp_path, "b", **kwargs)
    assert manifest_a.files == manifest_b.files
    assert (a / "manifest.json").read_bytes() == (b / "manifest.json").read_bytes()
    files = sorted(p.relative_to(a) for p in a.rglob("*.json"))
    assert files and all((a / f).read_bytes() == (b / f).read_bytes() for f in files)
    # another generation seed draws another plan
    _, other = build(tmp_path, "c", seed=12, **kwargs)
    assert other.files != manifest_a.files


def test_a_change_of_the_drawn_k_changes_only_the_affected_injection(
    tmp_path: Path,
) -> None:
    ticks = default_ticks()
    readings = default_readings()

    def context_with(long_value: int, name: str) -> BuildContext:
        folder = tmp_path / name
        folder.mkdir()
        prior_path = make_prior(folder)
        doc = config_document(
            folder, prior=prior_path, pairs=0, variants=[], n_patients=1, n_days=1,
            rates=(0.0, 3.0, 0.0),
        )  # fmt: skip

        def edit(document: dict[str, Any]) -> None:
            set_row(document, "cuff_detached_duration_long", value=long_value)

        doc["paths"]["injections"] = str(
            write_injections(folder, rates=(0.0, 3.0, 0.0), mutate=edit)
        )
        config = load_config(write_config(folder, doc))
        prior = LiteraturePriorSource(prior_path, strict=False, allow_fixture_only=True)
        return BuildContext.create(config, prior, allow_fixture_only=True)

    original, changed = context_with(3, "a"), context_with(4, "b")
    latent: Any = SimpleNamespace(latent=SimpleNamespace(events=[]))
    differing = 0
    for patient_index in range(30):
        for day in range(6):
            stream_ = fixture_stream(ticks, day_index=day)
            plans = []
            for context in (original, changed):
                plans.append(
                    context.plan_observation(
                        context.cohorts["main"],
                        patient_index,
                        day,
                        latent,
                        stream_,
                        Counter(),
                    )
                )
            before, after = plans
            # every injection that is not a cuff_detached window of level long is the same spec
            keep = [
                s
                for s in before
                if not (s.subtype == "cuff_detached" and s.level == "long")
            ]
            same_subtypes = [s for s in after if s.subtype != "cuff_detached"]
            assert [s for s in keep if s.subtype != "cuff_detached"] == same_subtypes
            longs_before = [
                s for s in before if s.subtype == "cuff_detached" and s.level == "long"
            ]
            longs_after = [
                s for s in after if s.subtype == "cuff_detached" and s.level == "long"
            ]
            for spec in longs_before:
                assert (
                    covered(
                        [DAY * day + r for r in readings],
                        spec.onset_ms,
                        spec.onset_ms + (spec.duration_ms or 0),
                    )
                    == 3
                )
            for spec in longs_after:
                assert (
                    covered(
                        [DAY * day + r for r in readings],
                        spec.onset_ms,
                        spec.onset_ms + (spec.duration_ms or 0),
                    )
                    == 4
                )
            differing += len(longs_before)
    assert differing > 5  # the comparison is not vacuous


# ---------------------------------------------------------------------------------------------------
# 7. The observability table of docs/benchmark/builder.md is the generator's output
# ---------------------------------------------------------------------------------------------------

BEGIN = "<!-- observability-table:begin"
END = "<!-- observability-table:end -->"


def committed_table() -> str:
    text = BUILDER_DOC.read_text(encoding="utf-8")
    match = re.search(
        re.escape(BEGIN) + r"[^\n]*\n(.*?)" + re.escape(END), text, re.DOTALL
    )
    assert match, "docs/benchmark/builder.md has no observability table block"
    return match.group(1).strip("\n")


def test_observability_table_matches_the_generator() -> None:
    generated = observability_table(
        default_readings(),
        step_ms=STEP,
        ks=design_ks(),
        day_start_ms=0,
        day_end_ms=DAY,
    )
    assert committed_table() == generated.strip("\n")


def test_the_generated_table_states_the_exact_distribution() -> None:
    readings = default_readings()
    table = observability_table(
        readings, step_ms=STEP, ks=design_ks(), day_start_ms=0, day_end_ms=DAY
    )
    rows = [line for line in table.splitlines() if re.match(r"\| [123] \|", line)]
    assert len(rows) == 3
    for k, row in zip((1, 2, 3), rows, strict=True):
        cells = [c.strip() for c in row.strip("|").split("|")]
        assert cells[0] == str(k)
        assert (
            cells[1] == f"{k}: 1"
        )  # probability 1: every window covers exactly k readings
        assert cells[2] == str(len(readings) - k + 1)
        shapes = ", ".join(f"{a}x{b}" for a, b in EXPECTED_SHAPES[k])
        assert cells[3] == shapes
    # the readings and the number of pairs behind it are stated, so a reader can recompute
    assert "06:15:30" in table and "22:15:30" in table


def test_the_generator_script_checks_the_committed_table() -> None:
    result = subprocess.run(
        [sys.executable, str(TABLE_SCRIPT), "--check"],
        capture_output=True, text=True, cwd=ROOT, check=False,
    )  # fmt: skip
    assert result.returncode == 0, result.stdout + result.stderr
    stale = subprocess.run(
        [sys.executable, str(TABLE_SCRIPT), "--check", "--doc", "/nonexistent.md"],
        capture_output=True, text=True, cwd=ROOT, check=False,
    )  # fmt: skip
    assert stale.returncode != 0


def test_anchored_subtypes_are_exactly_the_three_of_adr_070() -> None:
    assert set(ANCHORED_SUBTYPES) == {"cuff_detached", "cuff_silent_bias", "stuck_at"}
    assert list(ANCHORED_SUBTYPES) == sorted(ANCHORED_SUBTYPES)
