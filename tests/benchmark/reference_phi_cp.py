"""Independent reference evaluator of the five phi_CP templates on plain lists (WS04-T10).

Purpose. The ground-truth labeller of ``ralmon.benchmark.labelling`` computes the C1 truth by running the
WS05 monitor on an ideal observation of the latent day. A defect of the monitor would then define its own
truth. This module is the guard: it evaluates the same five templates (RANGE, SCHED, HOLD, COUNT, RESP) a
second time, from the formulas of ``docs/formal/02-templates.md`` (sections 3 and 4) and the semantics of
``docs/formal/05-three-valued-semantics.md`` (sections 2.3, 3.3, 3.4 and Lemma 12b), on plain Python lists
and a dense grid, with no import of ``ralmon`` at all (checked by an AST test). It shares no code with the
monitor, the labeller or the spec package; the only things it may take from the repository are the fixture
registry values, parsed here as plain numbers with YAML (``Params.from_registry_file``).

FIXTURE-ONLY. Every number the tests give it is fixture arithmetic (registry F0, ``step_ms = 60000``); none is
a clinical statement.

Semantics implemented (one instance per anchor, evaluated at its decision step; T01 section 3.7)
-----------------------------------------------------------------------------------------------
Grid: step ``k`` is the time ``origin + k * step``; an item with device time ``t`` is visible at the step
``ceil((t - origin) / step)`` (the ceiling rule). Items visible before step 0 or after step ``K`` are not part
of the run (the monitor starts at the first step of the day and the closing step is ``K = T_day / step``).
``bp`` is held: its value at a step is the value of the latest sample visible at or before the step (the
last sample of a bin wins). ``dose_count`` at step ``k`` counts the dispenses visible in ``(k - K, k]``; the
dispenses of the day count the steps ``1 .. K``.

* RANGE (one instance per measurement event at step ``k``): ``sigma = min(bp_k - low, high - bp_k)``;
  violated iff ``sigma < 0``; decided at ``k``; anchor ``origin + k * step``.
* HOLD (one per dispense at step ``k``): the guard holds iff a measurement event is visible in
  ``[k - lookback, k]``; ``sigma = bp_k - threshold`` (``-inf`` when the guard fails); violated iff
  ``sigma < 0``; decided at ``k``.
* COUNT limit (one per dispense at step ``k``): ``sigma = max - dose_count_k``; violated iff ``sigma < 0``.
* COUNT day end (one, at ``K``): ``sigma = dispenses_of_the_day - minimum``; violated iff ``sigma < 0``;
  anchor ``origin + K * step``.
* SCHED (one per tick of the plan, visible at ``k_a``, decided at ``k_d = k_a + window``): satisfied iff a
  measurement event is visible in ``[k_a, k_d]``, else violated at ``k_d``; an instance with ``k_d > K`` is
  open at the end of the day (it can only be satisfied early) and is never a violation here.
* RESP (one per dispense at step ``k_a``, decided at ``k_d = k_a + delta2``): ``pre`` is the value of the
  latest ``bp`` sample with device time not after the dispense (a sample of the same instant counts as
  before it, M5); with ``pre`` defined and ``pre - bound_lower - delta_resp < 0`` no pressure of the domain
  can give the response and the instance is violated at ``k_a`` (the early decision by the bounds, Lemma 12);
  otherwise an instance with ``k_d > K`` is open; otherwise the measurement events visible in
  ``[k_a + delta1, k_d]`` decide: none is a failed guard (violated), and with ``pre`` undefined and some
  measurement the instance stays undecided; else ``max(pre - bp_j) - delta_resp < 0`` is a violation.

What it returns for a violated instance is ``Violation(template, anchor_ms, end_ms, decided_at_ms)``:
the anchor of the labeller's convention (the decision instant for RANGE, HOLD and COUNT limit; the tick for
SCHED; the dispense step for RESP; the closing step for the day-end count) and ``end_ms`` the deadline for
the windowed obligations, ``None`` otherwise.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

DAY_MS = 86_400_000  # T_day: a definition, not a parameter
NAN = math.nan


@dataclass(frozen=True)
class Params:
    """The registry names the five templates use, as plain numbers (milliseconds, mmHg, doses)."""

    band_low: float
    band_high: float
    hold_threshold: float
    hold_lookback_ms: int
    dose_max_24h: int
    dose_min_day_end: int
    delta1_ms: int
    delta2_ms: int
    delta_resp: float
    sched_window_ms: int
    bound_bp_lower: float

    @staticmethod
    def from_registry_file(path: Path) -> Params:
        """Read the values from a registry YAML file (the fixture registry F0), as plain numbers."""
        document: Any = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        values = {entry["name"]: entry["value"] for entry in document["entries"]}
        return Params(
            band_low=float(values["bp_band_low"]),
            band_high=float(values["bp_band_high"]),
            hold_threshold=float(values["bp_hold_threshold"]),
            hold_lookback_ms=int(values["hold_lookback"]),
            dose_max_24h=int(values["dose_max_24h"]),
            dose_min_day_end=int(values["dose_min_day_end"]),
            delta1_ms=int(values["delta1"]),
            delta2_ms=int(values["delta2"]),
            delta_resp=float(values["delta_resp"]),
            sched_window_ms=int(values["sched_window"]),
            bound_bp_lower=float(values["bound_bp_lower"]),
        )


@dataclass(frozen=True, order=True)
class Violation:
    template: str
    anchor_ms: int
    end_ms: int | None
    decided_at_ms: int


def _ceil_div(a: int, b: int) -> int:
    return -((-a) // b)


def evaluate(
    params: Params,
    *,
    step_ms: int,
    origin_ms: int,
    measurements: Sequence[int],
    bp_samples: Sequence[tuple[int, float]],
    dispenses: Sequence[int],
    sched_ticks: Sequence[int],
    count_end: bool,
) -> list[Violation]:
    """The violated instances of the five templates for one day (module docstring).

    ``origin_ms`` is the start of the day on the continuing axis (``day_index * T_day``); the day lasts
    ``K = T_day / step_ms`` steps. ``measurements`` are the device times of the MEASUREMENT events,
    ``bp_samples`` the ``(device time, value)`` pairs of the ``bp`` signal, ``dispenses`` the device times of
    the DISPENSE events, ``sched_ticks`` the anchors of the SCHED instances of the plan and ``count_end``
    whether the plan carries the day-end obligation.
    """
    if DAY_MS % step_ms != 0:
        raise ValueError("the step must divide the day")
    k_end = DAY_MS // step_ms

    def step_of(t: int) -> int:
        return _ceil_div(t - origin_ms, step_ms)

    def in_run(k: int) -> bool:
        return 0 <= k <= k_end

    # --- the grid -------------------------------------------------------------------------------
    samples = sorted(
        ((t, i, v) for i, (t, v) in enumerate(bp_samples) if in_run(step_of(t))),
        key=lambda x: (x[0], x[1]),
    )
    held = [NAN] * (k_end + 1)
    last = NAN
    pointer = 0
    for k in range(k_end + 1):
        while pointer < len(samples) and step_of(samples[pointer][0]) <= k:
            last = samples[pointer][2]
            pointer += 1
        held[k] = last

    meas_steps = sorted(k for k in (step_of(t) for t in measurements) if in_run(k))
    disp = sorted(t for t in dispenses if in_run(step_of(t)))
    disp_steps = [step_of(t) for t in disp]

    def dose_count(k: int) -> int:
        return sum(1 for s in disp_steps if k - k_end < s <= k)

    def meas_between(lo: int, hi: int) -> list[int]:
        return [m for m in meas_steps if lo <= m <= hi]

    found: list[Violation] = []

    def at(k: int) -> int:
        return origin_ms + k * step_ms

    # --- RANGE ----------------------------------------------------------------------------------
    for k in meas_steps:
        v = held[k]
        if math.isnan(v):
            continue
        if min(v - params.band_low, params.band_high - v) < 0:
            found.append(Violation("range", at(k), None, at(k)))

    # --- HOLD and COUNT limit -------------------------------------------------------------------
    lookback = params.hold_lookback_ms // step_ms
    for k in disp_steps:
        guard = bool(meas_between(k - lookback, k))
        v = held[k]
        if not guard or (not math.isnan(v) and v - params.hold_threshold < 0):
            found.append(Violation("hold", at(k), None, at(k)))
        if params.dose_max_24h - dose_count(k) < 0:
            found.append(Violation("count", at(k), None, at(k)))

    # --- COUNT day end --------------------------------------------------------------------------
    if count_end:
        today = sum(1 for s in disp_steps if 1 <= s <= k_end)
        if today - params.dose_min_day_end < 0:
            found.append(Violation("count", at(k_end), at(k_end), at(k_end)))

    # --- SCHED ----------------------------------------------------------------------------------
    window = params.sched_window_ms // step_ms
    for tick in sched_ticks:
        k_a = step_of(tick)
        if k_a < 0:
            continue  # an instance of an earlier day is not part of the run
        k_d = k_a + window
        if k_d > k_end:
            continue  # open at the end of the day: at most satisfied early, never violated here
        if not meas_between(k_a, k_d):
            found.append(Violation("sched", tick, at(k_d), at(k_d)))

    # --- RESP -----------------------------------------------------------------------------------
    d1 = params.delta1_ms // step_ms
    d2 = params.delta2_ms // step_ms
    for t_d, k_a in zip(disp, disp_steps, strict=True):
        k_d = k_a + d2
        before = [(t, i, v) for (t, i, v) in samples if t <= t_d]
        pre = before[-1][2] if before else NAN
        if not math.isnan(pre) and pre - params.bound_bp_lower - params.delta_resp < 0:
            found.append(Violation("resp", at(k_a), at(k_d), at(k_a)))
            continue
        if k_d > k_end:
            continue
        window_meas = meas_between(k_a + d1, k_d)
        if not window_meas:
            found.append(Violation("resp", at(k_a), at(k_d), at(k_d)))
            continue
        if math.isnan(pre):
            continue
        best = max((pre - held[m]) - params.delta_resp for m in window_meas)
        if best < 0:
            found.append(Violation("resp", at(k_a), at(k_d), at(k_d)))

    return sorted(found)
