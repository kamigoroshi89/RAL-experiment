"""The hand-written mini benchmark of WS08-T01 (tests/fixtures/eval/mini_benchmark/).

ILLUSTRATIVE, UNVERIFIED, FIXTURE-ONLY. Six virtual patients (p01 to p06) with two scored days each and one unscored
tail day each (ADR-066), plus one confounder pair (p07, p08: single-day twins). Every number is arithmetic chosen so that
the metrics of the tests can be computed by hand; nothing is a clinical value and nothing is a result.

The observed days are not produced by a generator: they are written here, day by day, with the same shape as a built
benchmark (``days/``, ``truth/``, ``plans/``, ``manifest.json``). The ground truth is written by hand too (it is not
the output of the labeller), and the tests that need exact numbers use a scripted detector whose detections are listed
in the test, so that no expected value depends on the monitor.

Regeneration (from the repository root; the committed files change only through this command and the diff is reviewed):

    python -m tests.fixtures.eval.build_mini_benchmark

Truth of the fixture (T = 86_400_000 ms, ``ms(h, m)`` the clock time of the day):

=======  ===========================================================================================================
patient  events (class, subtype, onset, end)
=======  ===========================================================================================================
p01      d0: C1 hypertensive_spike range 14:00. tail: C1 drug_nonresponse resp 21:00 of d1 to 2T (the closing step
         of the last scored day), C1 hypertensive_spike range 10:00 of the tail day (never scored)
p02      d0: C2 ble_dropout 09:00 to 09:30. d1: C3 replay 15:00
p03      d0: C1 missed_measurement sched 08:00 to 08:30. d1: C1 dose_omission count, day-end, onset = end = 2T
p04      d1: C2 stuck_at 11:00 to 12:00
p05      d0: C1 hypertensive_spike range 14:00. d1: C3 injection_naive 09:00
p06      none (a control patient)
p07      d0: C1 double_take count 20:00 (group double_take_vs_bounce, member A of pair p07/p08)
p08      d0: C2 dispenser_bounce 20:00 (group double_take_vs_bounce, member B)
=======  ===========================================================================================================
"""

from __future__ import annotations

import shutil
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ralmon.benchmark import GroundTruthEvent, InjectedClass, LatentDay, ObservedDay
from ralmon.benchmark.builder import write_care_plan
from ralmon.benchmark.trace import (
    Manifest,
    file_sha256,
    observed_relpath,
    truth_relpath,
    write_manifest,
    write_observed_day,
    write_truth,
)
from ralmon.signals import Event, EventKind, Sample
from ralmon.spec import CarePlan, TemplateInstance, load_registry
from ralmon.spec.templates import TemplateId

HERE = Path(__file__).resolve().parent
OUT = HERE / "mini_benchmark"
REGISTRY_PATH = HERE / "registry.yaml"

STEP_MS = 60_000
T = 86_400_000
N_SCORED = 2

C1, C2, C3 = InjectedClass.C1, InjectedClass.C2, InjectedClass.C3


def ms(h: int, m: int = 0) -> int:
    return (60 * h + m) * STEP_MS


# (patient, split, role, extra manifest keys)
PATIENTS: tuple[tuple[str, str, str, Mapping[str, Any]], ...] = (
    ("p01", "train", "patient", {}),
    ("p02", "train", "patient", {}),
    ("p03", "calibration", "patient", {}),
    ("p04", "calibration", "patient", {}),
    ("p05", "test", "patient", {}),
    ("p06", "test", "patient", {}),
    (
        "p07",
        "test",
        "confounder_pair",
        {
            "pair": "pair01",
            "member": "A",
            "group": "double_take_vs_bounce",
            "variant_id": "v01",
            "mechanism": "c1_double_take",
        },
    ),
    (
        "p08",
        "test",
        "confounder_pair",
        {
            "pair": "pair01",
            "member": "B",
            "group": "double_take_vs_bounce",
            "variant_id": "v01",
            "mechanism": "c2_bounce",
        },
    ),
)


def _gt(
    cls: InjectedClass,
    subtype: str,
    onset: int,
    end: int | None = None,
    *,
    template: str | None = None,
    injected: bool | None = None,
    group: str | None = None,
) -> GroundTruthEvent:
    inj = cls is not C1 if injected is None else injected
    return GroundTruthEvent(cls, subtype, onset, end, inj, template, group)


# (patient, day_index) -> events of that file (the tail day has index N_SCORED, twins have one scored day)
TRUTH: dict[tuple[str, int], tuple[GroundTruthEvent, ...]] = {
    ("p01", 0): (_gt(C1, "hypertensive_spike", ms(14), template="range"),),
    ("p01", 2): (
        _gt(
            C1,
            "drug_nonresponse",
            T + ms(21),
            2 * T,
            template="resp",
            injected=True,
        ),
        _gt(C1, "hypertensive_spike", 2 * T + ms(10), template="range"),
    ),
    ("p02", 0): (_gt(C2, "ble_dropout", ms(9), ms(9, 30)),),
    ("p02", 1): (_gt(C3, "replay", T + ms(15)),),
    ("p03", 0): (_gt(C1, "missed_measurement", ms(8), ms(8, 30), template="sched"),),
    ("p03", 1): (
        _gt(C1, "dose_omission", 2 * T, 2 * T, template="count", injected=True),
    ),
    ("p04", 1): (_gt(C2, "stuck_at", T + ms(11), T + ms(12)),),
    ("p05", 0): (_gt(C1, "hypertensive_spike", ms(14), template="range"),),
    ("p05", 1): (_gt(C3, "injection_naive", T + ms(9)),),
    (
        "p07",
        0,
    ): (
        _gt(
            C1,
            "double_take",
            ms(20),
            template="count",
            injected=True,
            group="double_take_vs_bounce",
        ),
    ),
    ("p08", 0): (_gt(C2, "dispenser_bounce", ms(20), group="double_take_vs_bounce"),),
}

# observed anomalies: the 14:00 pressure of the patients whose day carries the C1 spike of the truth
SPIKE_DAYS: frozenset[tuple[str, int]] = frozenset({("p01", 0), ("p05", 0)})


def n_scored(patient: str) -> int:
    role = next(p[2] for p in PATIENTS if p[0] == patient)
    return 1 if role == "confounder_pair" else N_SCORED


def _sample(signal: str, t: int, value: float) -> Sample:
    return Sample(signal, t, t, float(value), None, None)


def _event(
    kind: EventKind,
    t: int,
    source: str = "dev",
    payload: Mapping[str, float | int | str | bool] | None = None,
) -> Event:
    return Event(kind, t, t, source, dict(payload or {}), None)


def observed_day(patient: str, day: int, *, plan_id: str) -> ObservedDay:
    """A routine day: two measurements, one dose with its witness and its response, a heart rate and a saturation."""
    o = day * T
    spike = (patient, day) in SPIKE_DAYS
    samples: list[Sample] = [
        _sample("bp", o + ms(8), 125.0),
        _sample("cuff_health", o + ms(8), 1.0),
        _sample("inflation_ms", o + ms(8), 40_000.0),
        _sample("presence", o + ms(8, 3), 1.0),
        _sample("bp", o + ms(10), 115.0),
        _sample("bp", o + ms(14), 165.0 if spike else 122.0),
        _sample("cuff_health", o + ms(14), 1.0),
        _sample("inflation_ms", o + ms(14), 40_000.0),
    ]
    for k in range(48):
        samples.append(_sample("hr_ecg", o + 30 * k * STEP_MS, 70.0 + (k % 5)))
        samples.append(_sample("spo2", o + 30 * k * STEP_MS, 96.0 + (k % 3)))
    events: list[Event] = [
        _event(EventKind.MEASUREMENT, o + ms(8)),
        _event(
            EventKind.NODE_STATE,
            o + ms(8, 3),
            "robot",
            {"state": "active", "colocated": True},
        ),
        _event(EventKind.DISPENSE, o + ms(8, 5)),
        _event(EventKind.INTAKE, o + ms(8, 6)),
        _event(EventKind.MEASUREMENT, o + ms(10)),
        _event(EventKind.MEASUREMENT, o + ms(14)),
    ]
    samples.sort(key=lambda s: (s.t_rx_ms, s.signal))
    events.sort(key=lambda e: (e.t_rx_ms, e.kind.value))
    return ObservedDay(patient, day, 0, tuple(samples), tuple(events), plan_id)


def latent_day(patient: str, day: int) -> LatentDay:
    o = day * T
    spike = (patient, day) in SPIKE_DAYS
    samples = (
        _sample("bp", o + ms(8), 125.0),
        _sample("bp", o + ms(10), 115.0),
        _sample("bp", o + ms(14), 165.0 if spike else 122.0),
    )
    return LatentDay(patient, day, 0, samples, ())


def care_plan(patient: str, n_days: int, registry: Any) -> CarePlan:
    """The plan of the whole record: scored days and tail day on the continuing axis."""

    def value(name: str) -> float:
        return float(registry.get(name).value)

    records: dict[str, tuple[str, ...]] = {
        "range": ("bp_band_low", "bp_band_high"),
        "hold": ("bp_hold_threshold", "hold_lookback"),
        "count": ("dose_max_24h", "dose_min_day_end"),
        "resp": ("delta1", "delta2", "delta_resp"),
        "sys": ("cuff_inflation_min",),
        "int": ("int_window",),
    }
    instances: list[TemplateInstance] = []
    for name, params in records.items():
        instances.append(
            TemplateInstance(
                TemplateId(name),
                f"record-{name}",
                {p: value(p) for p in params},
                None,
            )
        )
    schedule: list[int] = []
    window = value("sched_window")
    for d in range(n_days + 1):  # the tail day included
        for tick in (ms(8), ms(14)):
            instances.append(
                TemplateInstance(
                    TemplateId.SCHED,
                    f"sched@{d * T + tick}",
                    {"sched_window": window},
                    d * T + tick,
                )
            )
            schedule.append(d * T + tick)
        instances.append(
            TemplateInstance(
                TemplateId.COUNT,
                f"count-day-end@{(d + 1) * T}",
                {p: value(p) for p in records["count"]},
                (d + 1) * T,
            )
        )
        schedule.append(d * T + ms(8, 5))
    return CarePlan(
        f"plan-{patient}",
        "pathway-fixture",
        patient,
        registry.version(),
        tuple(instances),
        tuple(sorted(set(schedule))),
        1,
        None,
    )


def build(root: Path = OUT) -> Manifest:
    """Write the mini benchmark into ``root`` (emptied first) and return its manifest."""
    registry = load_registry(REGISTRY_PATH, step_ms=STEP_MS, allow_fixture_only=True)
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    files: dict[str, str] = {}
    patients: dict[str, dict[str, Any]] = {}
    counts: dict[str, int] = {}

    def record(relative: str) -> None:
        files[relative] = file_sha256(root / relative)

    for pid, split, role, extra in PATIENTS:
        n = n_scored(pid)
        plan = care_plan(pid, n, registry)
        write_care_plan(root, plan)
        record(f"plans/{plan.care_plan_id}.json")
        for d in range(n + 1):  # the scored days, then the tail day
            write_observed_day(root, observed_day(pid, d, plan_id=plan.care_plan_id))
            events = TRUTH.get((pid, d), ())
            write_truth(root, latent_day(pid, d), events, [], [])
            record(observed_relpath(pid, d))
            record(truth_relpath(pid, d))
            if role == "patient" and d < n:
                for e in events:
                    key = f"{e.cls.value}/{e.subtype}"
                    counts[key] = counts.get(key, 0) + 1
        entry: dict[str, Any] = {
            "split": split,
            "cohort": "fx",
            "role": role,
            "n_scored_days": n,
            "tail_day_index": n,
            "care_plan_id": plan.care_plan_id,
            "patient_index": int(pid[1:]),
        }
        entry.update(extra)
        patients[pid] = entry
    manifest = Manifest(
        benchmark_version="mini-0",
        generator_git_rev="fixture-rev",
        generation_seed=0,
        prior_source_name="fixture_prior",
        prior_provenance=[
            {
                "name": "fx_param",
                "source_ref": "FIXTURE-ONLY: arithmetic value, no source",
                "verified_by": None,
            }
        ],
        fixture_only=True,
        n_unfilled=0,
        n_unverified=1,
        patients=patients,
        files=dict(sorted(files.items())),
        event_counts=dict(sorted(counts.items())),
        settings={
            "tail_day": True,
            "n_scored_days": N_SCORED,
            "n_patients": 6,
            "n_patient_days": 12,
            "n_twin_patients": 2,
            "n_twin_patient_days": 2,
            "monitor": {"step_ms": STEP_MS, "reorder_delay_ms": 0},
            "registry_version": registry.version(),
            "registry_fixture_only": True,
            "split_fractions": {"train": 0.34, "calibration": 0.33, "test": 0.33},
            "note": "ILLUSTRATIVE, UNVERIFIED: hand-written fixture of WS08-T01",
        },
    )
    write_manifest(root, manifest)
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    manifest = build()
    print(
        f"wrote {OUT} ({len(manifest.files)} files, {len(manifest.patients)} patients)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
