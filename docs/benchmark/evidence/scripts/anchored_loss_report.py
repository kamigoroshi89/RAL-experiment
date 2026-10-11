"""Tally table of the readings an anchored cuff fault loses, by cause, with Wilson intervals and the closed-form expectation.

WS04-T16, item 2 of the fix round. Input: one or more JSON files written by `anchored_loss_build.py` (a FIXTURE build;
no clinical meaning). Output: markdown on stdout. Needs the project venv (it reads the FIXTURE schedule of registry F0).

    PYTHONPATH=src .venv/bin/python docs/benchmark/evidence/scripts/anchored_loss_report.py /tmp/diag_400_03.json

Closed-form expectation (the "earlier estimate" assumptions made explicit). Per day the plan draws N ~ Poisson(rate) C2
injections; each is one of the six drawn subtypes with probability 1/6 and a robot fault takes a tick uniformly among the
n measurement ticks plus the dose ticks (n_ticks = n + 2 on the default schedule; the dose ticks are in `n_dose_ticks`).
  * robot, removal: a reading is removed by a `manipulation_failure` with probability p = (rate/6) / n_ticks per reading per
    day (the ADR-070 estimate: 0.7% at rate 0.3). Robot, displacement: a `nav_delay` hits the tick with the same probability p
    and moves the reading forward by the delay (the FIXTURE levels are 0.5, 1, 2 sched_windows of registry F0: 15, 30, 60 min); it
    leaves the window only if it is the last covered reading and the delayed instant passes the window end, which is uniform
    over the gap after it (computed exactly from the rule). The ADR estimate counted the removal only.
  * device: a bias or stuck window loses a reading if a `cuff_detached` window of the same day covers it. The detached windows
    of a day are Poisson with mean rate/6; a detached window covers reading r with probability c(r), averaged over its k'
    (uniform on the levels) and its first reading (uniform among the n - k' + 1). So the reading is lost with probability
    1 - exp(-(rate/6) c(r)). The earlier 0.7-4% estimate counted the robot only: it assumed the windows interact only with
    the robot faults. Anchoring puts every cuff window on the same n readings, which makes them interact with each other.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from ralmon.benchmark.anchoring import anchored_choices
from ralmon.benchmark.schedule import load_schedule
from ralmon.spec.registry import load_registry

ROOT = Path(__file__).resolve().parents[4]
FIXTURE_INFLATION_MS = 30_000  # FIXTURE-ONLY: GENERATOR_VALUES["inflation_ms_nominal"] of tests/benchmark/test_builder.py
FIXTURE_DELAYS_MS = (900_000, 1_800_000, 3_600_000)  # FIXTURE-ONLY: 0.5, 1, 2 x the F0 sched_window of 30 min
DAY_MS = 86_400_000
STEP_MS = 60_000


def fixture_readings() -> list[int]:
    registry = load_registry(ROOT / "tests/fixtures/spec/registry_f0.yaml", step_ms=STEP_MS, allow_fixture_only=True)
    windows = {f"{n}_ms": int(registry.get(n).value) for n in ("hold_lookback", "delta1", "delta2", "sched_window")}
    schedule = load_schedule(ROOT / "configs/benchmark/care_plans.yaml", **windows)
    return [t + FIXTURE_INFLATION_MS for t in schedule.measurement_ticks_ms]


def nav_out_per_window(readings: list[int], k: int) -> float:
    """Expected readings a nav_delay at each tick of the window moves out of it, per unit of tick probability."""
    choices = anchored_choices(readings, k, step_ms=STEP_MS, day_start_ms=0, day_end_ms=DAY_MS)
    total = 0.0
    for c in choices:
        last = readings[c.first + k - 1]
        for delta in FIXTURE_DELAYS_MS:
            out = sum(1 for e in c.ends if e <= last + delta) / len(c.ends)
            total += out / (len(choices) * len(FIXTURE_DELAYS_MS))
    return total


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def fmt(k: int, n: int) -> str:
    low, high = wilson(k, n)
    return f"{k}/{n} = {100 * k / n if n else 0:.1f}% [{100 * low:.1f}, {100 * high:.1f}]"


def coverage(n: int, ks: list[int]) -> list[float]:
    """c(r): probability that a detached window (k' uniform on ks, first reading uniform) covers reading r."""
    out = [0.0] * n
    for k in ks:
        choices = n - k + 1
        for first in range(choices):
            for r in range(first, first + k):
                out[r] += 1.0 / (len(ks) * choices)
    return out


def expected_device_loss(n: int, rate: float, k: int, ks: list[int]) -> tuple[float, float]:
    """(expected readings lost to a detached window, P(at least one lost)) for a window of k readings."""
    c = coverage(n, ks)
    lam = rate / 6.0
    lost = 0.0
    keep_all = 0.0
    choices = n - k + 1
    for first in range(choices):
        window = range(first, first + k)
        lost += sum(1 - math.exp(-lam * c[r]) for r in window) / choices
        keep_all += math.exp(-lam * sum(c[r] for r in window)) / choices  # independence across readings
    return lost, 1 - keep_all


def report(path: Path) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    rate, n = data["c2_rate"], data["n_measurement_ticks"]
    n_ticks = n + 2  # measurement ticks plus the two dose ticks of the default schedule
    block = data["anchored_cuff_faults"]["by_drawn_k"]
    ks = sorted({int(k) for per in block.values() for k in per})
    p_manip = rate / 6.0 / n_ticks
    readings = fixture_readings()
    out = [
        f"### {data['n_patients']} patients x 7 days, C2 rate {rate} ({data['n_patient_days']} patient-days)",
        "",
        f"Robot, closed form per reading per day: `manipulation_failure` removes {100 * p_manip:.2f}%; "
        f"`nav_delay` moves out {', '.join(f'k={k}: {100 * p_manip * nav_out_per_window(readings, k) / k:.2f}%' for k in ks)}. "
        f"Detached coverage per reading c(r) = "
        f"{', '.join(f'{x:.3f}' for x in coverage(n, ks))}.",
        "",
        "| subtype | drawn k | draws | readings drawn | removed by robot (per reading) | moved out by robot (per reading) | lost device (per reading) | "
        "gained robot | covered != drawn (per draw) | covered 0 | device loss per reading, closed form | P(differs) device, closed form |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for subtype in sorted(block):
        total = dict.fromkeys(("draws", "readings_drawn", "lost_robot", "removed_robot", "lost_device", "gained_robot", "covered_differs", "covered_zero"), 0)
        rows = []
        for k_text in sorted(block[subtype]):
            cell = block[subtype][k_text]
            for key in total:
                total[key] += cell.get(key, 0)
            rows.append((k_text, cell))
        rows.append(("all", total))
        for k_text, cell in rows:
            g = lambda key: cell.get(key, 0)  # noqa: E731
            if k_text == "all" or subtype == "cuff_detached":
                lost_cf, differs_cf = ("-", "-") if subtype == "cuff_detached" else ("", "")
            else:
                lost, differs = expected_device_loss(n, rate, int(k_text), ks)
                lost_cf, differs_cf = f"{100 * lost / int(k_text):.1f}%", f"{100 * differs:.1f}%"
            if k_text == "all" and subtype != "cuff_detached":
                weights = {int(k): block[subtype][k]["draws"] for k in block[subtype]}
                tot = sum(weights.values())
                ev = [expected_device_loss(n, rate, k, ks) for k in weights]
                lost_cf = f"{100 * sum(w * e[0] for w, e in zip(weights.values(), ev, strict=True)) / sum(w * k for k, w in weights.items()):.1f}%"
                differs_cf = f"{100 * sum(w * e[1] for w, e in zip(weights.values(), ev, strict=True)) / tot:.1f}%"
            out.append(
                f"| {subtype} | {k_text} | {g('draws')} | {g('readings_drawn')} | {fmt(g('removed_robot'), g('readings_drawn'))} "
                f"| {fmt(g('lost_robot') - g('removed_robot'), g('readings_drawn'))} "
                f"| {fmt(g('lost_device'), g('readings_drawn'))} | {g('gained_robot')} "
                f"| {fmt(g('covered_differs'), g('draws'))} | {g('covered_zero')} | {lost_cf} | {differs_cf} |"
            )
    out.append("")
    out.append(f"plan_skipped (cuff): { {k: v for k, v in data['plan_skipped'].items() if 'cuff' in k or 'stuck' in k} }; plan_unrealised: {data['plan_unrealised']}")
    return "\n".join(out)


def main(argv: list[str]) -> int:
    for name in argv[1:]:
        print(report(Path(name)))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
