"""Care-plan schedule of the benchmark generator and its derivation rule (WS04-T05).

A ``Schedule`` holds, for one patient-day, the **dose ticks** (device clock time of each
scheduled dose) and the **measurement ticks**, both as integer milliseconds since the start of
the day, strictly increasing and inside ``[0, T_day)``. The same schedule applies to every day.

Derivation rule (``derive_schedule``). For each dose tick ``a`` the plan needs a measurement
before it (the HOLD obligation, plan feasibility check F2) and one after it (the RESP
obligation, check F3) of ``docs/formal/02-templates.md`` section 5.4. With the windows of the
parameter registry (working names ``hold_lookback``, ``delta1``, ``delta2``, ``sched_window``)
passed as arguments (this module never imports ``ralmon.spec``; the builder, WS04-T11, reads
the registry):

* the **pre-dose tick** is the midpoint of ``[a - hold_lookback, a - sched_window)``;
* the **post-dose tick** is the midpoint of ``[a + delta1, a + delta2 - sched_window]``;
* every remaining measurement is the midpoint of the largest gap between two consecutive ticks
  (the earliest gap on ties), one at a time.

A midpoint is ``(low + high) // 2`` (rounded down), which lies inside the window. A tick placed
at least ``sched_window`` before the end of its window leaves **slack**: a robot that arrives as
late as the schedule window allows still measures inside the window, so a fault-free day cannot
violate HOLD or RESP by construction of the plan. ``check_schedule_consistency`` verifies F2 and
F3 plus that slack for a given schedule (any schedule, derived or hand-written).

Declared limits: the ticks of one day must lie inside that day (a window that reaches into the
neighbouring day is refused, ``OUTSIDE_DAY``); the extra ticks need at least one dose to sit
between (``NO_ANCHOR``); checks F1 (alignment to the grid step), F4 (robot visits), F5 (dose
counts) and F6 (registry names) need data this module does not have and are not run here.

The care-plan design rows (dose times of day, number of measurements) live in
``configs/benchmark/care_plans.yaml`` and are read through ``load_design_file``.
"""

from __future__ import annotations

import numbers
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any, Final, TypeGuard

import numpy as np

from ralmon.benchmark.latent import T_DAY_MS
from ralmon.benchmark.priors import (
    PriorConfigError,
    UnfilledParameterError,
    load_design_file,
)
from ralmon.signals import MS_PER_HOUR, MS_PER_MINUTE, MS_PER_SECOND, DurationMs, TimeMs

__all__ = [
    "CARE_PLAN_RELPATH",
    "DOSES_ROW",
    "N_MEASUREMENTS_ROW",
    "Schedule",
    "ScheduleError",
    "ScheduleInfeasibleError",
    "ScheduleProblem",
    "check_schedule_consistency",
    "clock_label",
    "derive_schedule",
    "load_filled_rows",
    "load_schedule",
]

CARE_PLAN_RELPATH: Final = "configs/benchmark/care_plans.yaml"
DOSES_ROW: Final = "dose_times_clock_ms"
N_MEASUREMENTS_ROW: Final = "n_measurements_per_day"

# Problem codes of ScheduleProblem.check.
F2_HOLD: Final = "F2_HOLD"  # no tick in [a - hold_lookback, a)
F3_RESP: Final = "F3_RESP"  # no tick in [a + delta1, a + delta2]
SLACK_HOLD: Final = (
    "SLACK_HOLD"  # no tick in the pre window leaves sched_window of slack
)
SLACK_RESP: Final = (
    "SLACK_RESP"  # no tick in the post window leaves sched_window of slack
)
TOO_FEW: Final = "TOO_FEW_MEASUREMENTS"
NO_ANCHOR: Final = "NO_ANCHOR"
OUTSIDE_DAY: Final = "TICK_OUTSIDE_DAY"
COINCIDES: Final = "TICK_COINCIDES"
NO_ROOM: Final = "NO_ROOM"


class ScheduleError(ValueError):
    """A schedule, a window or a configuration row is invalid."""


@dataclass(frozen=True, slots=True)
class ScheduleProblem:
    """One failed check: its code, the dose it concerns (``None`` if none) and a message."""

    check: str
    dose_tick_ms: TimeMs | None
    message: str


class ScheduleInfeasibleError(ScheduleError):
    """The windows cannot be realised for the doses; ``problems`` lists each one."""

    def __init__(self, problems: Sequence[ScheduleProblem]) -> None:
        self.problems: tuple[ScheduleProblem, ...] = tuple(problems)
        super().__init__("; ".join(f"{p.check}: {p.message}" for p in self.problems))


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _is_integer(x: object) -> TypeGuard[numbers.Integral]:
    return not isinstance(x, (bool, np.bool_)) and isinstance(x, numbers.Integral)


def _int(name: str, x: object, *, minimum: int) -> int:
    if not _is_integer(x):
        raise ScheduleError(f"{name} must be an integer, got {x!r}")
    value = int(x)
    if value < minimum:
        raise ScheduleError(f"{name} must be >= {minimum}, got {value}")
    return value


def _ticks(name: str, ticks: object) -> tuple[int, ...]:
    if isinstance(ticks, (str, bytes)) or not isinstance(ticks, Sequence):
        raise ScheduleError(f"{name} must be a sequence of integers, got {ticks!r}")
    values = tuple(_int(f"{name}[{i}]", t, minimum=0) for i, t in enumerate(ticks))
    for i, value in enumerate(values):
        if value >= T_DAY_MS:
            raise ScheduleError(
                f"{name}[{i}] = {value} is not inside the day [0, {T_DAY_MS})"
            )
    for before, after in pairwise(values):
        if after <= before:
            raise ScheduleError(f"{name} must be strictly increasing, got {values}")
    return values


def clock_label(t_ms: TimeMs) -> str:
    """``hh:mm:ss.mmm`` of a time of day in ms (for messages); times past 24 h keep counting."""
    hours, rest = divmod(int(t_ms), MS_PER_HOUR)
    minutes, rest = divmod(rest, MS_PER_MINUTE)
    seconds, millis = divmod(rest, MS_PER_SECOND)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


@dataclass(frozen=True, slots=True)
class Schedule:
    """Dose ticks and measurement ticks of one day (ms since the start of the day).

    Both are strictly increasing integers in ``[0, T_day)``; the empty tuple is a valid
    schedule (a day with no scheduled dose).
    """

    dose_ticks_ms: tuple[TimeMs, ...]
    measurement_ticks_ms: tuple[TimeMs, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "dose_ticks_ms", _ticks("dose_ticks_ms", self.dose_ticks_ms)
        )
        object.__setattr__(
            self,
            "measurement_ticks_ms",
            _ticks("measurement_ticks_ms", self.measurement_ticks_ms),
        )

    def slot_lengths_ms(self) -> tuple[DurationMs, ...]:
        """Length of the slot of each dose: to the next dose tick, or to the day end.

        The last slot of a day ends at the day end (``T_day``), not at the first tick of the
        next day, so that everything a slot produces starts inside its own day.
        """
        ends = (*self.dose_ticks_ms[1:], T_DAY_MS)
        return tuple(
            end - start for start, end in zip(self.dose_ticks_ms, ends, strict=False)
        )


# ---------------------------------------------------------------------------
# Windows and checks
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Windows:
    hold_lookback_ms: DurationMs
    delta1_ms: DurationMs
    delta2_ms: DurationMs
    sched_window_ms: DurationMs


def _windows(
    hold_lookback_ms: object,
    delta1_ms: object,
    delta2_ms: object,
    sched_window_ms: object,
) -> _Windows:
    hold = _int("hold_lookback_ms", hold_lookback_ms, minimum=0)
    d1 = _int("delta1_ms", delta1_ms, minimum=0)
    d2 = _int("delta2_ms", delta2_ms, minimum=0)
    sched = _int("sched_window_ms", sched_window_ms, minimum=0)
    if d2 < d1:
        raise ScheduleError(f"delta2_ms ({d2}) must not be below delta1_ms ({d1})")
    return _Windows(hold, d1, d2, sched)


def _problem(check: str, dose: TimeMs | None, message: str) -> ScheduleProblem:
    where = "" if dose is None else f"dose at {dose} ms ({clock_label(dose)}): "
    return ScheduleProblem(check, dose, where + message)


def check_schedule_consistency(
    schedule: Schedule,
    hold_lookback_ms: DurationMs,
    delta1_ms: DurationMs,
    delta2_ms: DurationMs,
    sched_window_ms: DurationMs,
) -> tuple[ScheduleProblem, ...]:
    """Plan feasibility checks F2 and F3 plus the slack requirement, per dose in dose order.

    For each dose tick ``a``: ``F2_HOLD`` if no measurement tick lies in
    ``[a - hold_lookback, a)``, else ``SLACK_HOLD`` if no such tick ``t`` has
    ``t + sched_window < a``; ``F3_RESP`` if none lies in ``[a + delta1, a + delta2]``, else
    ``SLACK_RESP`` if none has ``t + sched_window <= a + delta2``. Returns an empty tuple when
    the schedule passes.
    """
    w = _windows(hold_lookback_ms, delta1_ms, delta2_ms, sched_window_ms)
    ticks = schedule.measurement_ticks_ms
    problems: list[ScheduleProblem] = []
    for a in schedule.dose_ticks_ms:
        before = [t for t in ticks if a - w.hold_lookback_ms <= t < a]
        if not before:
            problems.append(
                _problem(
                    F2_HOLD,
                    a,
                    f"no measurement tick in [a - {w.hold_lookback_ms} ms, a)",
                )
            )
        elif not any(t + w.sched_window_ms < a for t in before):
            problems.append(
                _problem(
                    SLACK_HOLD,
                    a,
                    f"no pre-dose tick leaves sched_window ({w.sched_window_ms} ms) "
                    "of slack before the dose",
                )
            )
        after = [t for t in ticks if a + w.delta1_ms <= t <= a + w.delta2_ms]
        if not after:
            problems.append(
                _problem(
                    F3_RESP,
                    a,
                    f"no measurement tick in [a + {w.delta1_ms} ms, a + {w.delta2_ms} ms]",
                )
            )
        elif not any(t + w.sched_window_ms <= a + w.delta2_ms for t in after):
            problems.append(
                _problem(
                    SLACK_RESP,
                    a,
                    f"no post-dose tick leaves sched_window ({w.sched_window_ms} ms) "
                    "of slack before the end of the response window",
                )
            )
    return tuple(problems)


def derive_schedule(
    dose_times_ms: Sequence[TimeMs],
    n_measurements: int,
    hold_lookback_ms: DurationMs,
    delta1_ms: DurationMs,
    delta2_ms: DurationMs,
    sched_window_ms: DurationMs,
) -> Schedule:
    """The schedule of the module docstring; raises ``ScheduleInfeasibleError`` if none exists.

    ``dose_times_ms`` are strictly increasing times of day; ``n_measurements`` is the total
    number of measurement ticks and must be at least two per dose (one pre and one post tick).
    """
    doses = _ticks("dose_times_ms", dose_times_ms)
    total = _int("n_measurements", n_measurements, minimum=0)
    w = _windows(hold_lookback_ms, delta1_ms, delta2_ms, sched_window_ms)

    problems: list[ScheduleProblem] = []
    required: list[tuple[TimeMs, TimeMs]] = []  # (tick, dose it serves)
    for a in doses:
        pre_low, pre_high = a - w.hold_lookback_ms, a - w.sched_window_ms
        if pre_high <= pre_low:  # the window [a - hold, a - sched) is empty
            problems.append(
                _problem(
                    SLACK_HOLD,
                    a,
                    f"hold_lookback ({w.hold_lookback_ms} ms) is not longer than "
                    f"sched_window ({w.sched_window_ms} ms): no pre-dose tick can leave slack",
                )
            )
        else:
            required.append(((pre_low + pre_high) // 2, a))
        post_low, post_high = a + w.delta1_ms, a + w.delta2_ms - w.sched_window_ms
        if post_high < post_low:  # the window [a + delta1, a + delta2 - sched] is empty
            problems.append(
                _problem(
                    SLACK_RESP,
                    a,
                    f"delta2 - delta1 ({w.delta2_ms - w.delta1_ms} ms) is shorter than "
                    f"sched_window ({w.sched_window_ms} ms): no post-dose tick can leave slack",
                )
            )
        else:
            required.append(((post_low + post_high) // 2, a))
    for tick, dose in required:
        if not 0 <= tick < T_DAY_MS:
            problems.append(
                _problem(
                    OUTSIDE_DAY,
                    dose,
                    f"its tick at {tick} ms lies outside the day [0, {T_DAY_MS})",
                )
            )
    if problems:
        raise ScheduleInfeasibleError(problems)

    if total < len(required):
        raise ScheduleInfeasibleError(
            [
                _problem(
                    TOO_FEW,
                    None,
                    f"{total} measurement(s) cannot cover {len(doses)} dose(s): "
                    f"each dose needs a pre-dose and a post-dose tick ({len(required)})",
                )
            ]
        )
    seen: dict[TimeMs, TimeMs] = {}
    for tick, dose in required:
        if tick in seen:
            raise ScheduleInfeasibleError(
                [
                    _problem(
                        COINCIDES,
                        dose,
                        f"its tick at {tick} ms coincides with the tick of the dose at "
                        f"{seen[tick]} ms ({clock_label(seen[tick])})",
                    )
                ]
            )
        seen[tick] = dose

    ticks = sorted(seen)
    for _ in range(total - len(required)):
        if len(ticks) < 2:
            raise ScheduleInfeasibleError(
                [
                    _problem(
                        NO_ANCHOR,
                        None,
                        "an extra measurement needs at least two ticks to sit between; "
                        "the plan has no dose",
                    )
                ]
            )
        widths = [after - before for before, after in pairwise(ticks)]
        widest = widths.index(max(widths))  # the earliest gap on ties
        low, high = ticks[widest], ticks[widest + 1]
        if high - low < 2:  # a midpoint strictly between two integers needs a gap of 2
            raise ScheduleInfeasibleError(
                [
                    _problem(
                        NO_ROOM,
                        None,
                        f"the largest gap between ticks ({high - low} ms) leaves no "
                        "integer time strictly between its ends",
                    )
                ]
            )
        ticks.insert(widest + 1, (low + high) // 2)
    return Schedule(dose_ticks_ms=doses, measurement_ticks_ms=tuple(ticks))


# ---------------------------------------------------------------------------
# The care-plan design file
# ---------------------------------------------------------------------------


def load_filled_rows(path: str | Path, names: Sequence[str]) -> dict[str, Any]:
    """The values of rows ``names`` of a design config, each of which must be filled.

    Raises ``PriorConfigError`` for a missing row or file, and ``UnfilledParameterError``
    (naming only the unfilled rows) when a row is still ``awaiting_human_value``.
    """
    parsed = load_design_file(path)
    rows = {r.parameter: r for r in parsed.rows}
    missing = [n for n in names if n not in rows]
    if missing:
        raise PriorConfigError(f"{parsed.path}: missing row(s) {missing}")
    unfilled = [n for n in names if not rows[n].filled]
    if unfilled:
        raise UnfilledParameterError(
            f"parameter(s) {', '.join(unfilled)} are awaiting_human_value: a human "
            f"supplies the value and its source_ref in {parsed.path}"
        )
    return {n: rows[n].value for n in names}


def load_schedule(
    path: str | Path,
    *,
    hold_lookback_ms: DurationMs,
    delta1_ms: DurationMs,
    delta2_ms: DurationMs,
    sched_window_ms: DurationMs,
) -> Schedule:
    """Read the dose times and the measurement count from a care-plan file and derive the schedule.

    The windows come from the caller (the registry values read by the builder). Raises
    ``UnfilledParameterError`` for an unfilled row, ``ScheduleError`` for a value that is not
    a list of integer times or an integer count, and ``ScheduleInfeasibleError`` when the
    windows cannot hold the plan.
    """
    values = load_filled_rows(path, (DOSES_ROW, N_MEASUREMENTS_ROW))
    doses = values[DOSES_ROW]
    if not isinstance(doses, list):
        raise ScheduleError(
            f"{DOSES_ROW} must be a list of times of day, got {doses!r}"
        )
    return derive_schedule(
        doses,
        values[N_MEASUREMENTS_ROW],
        hold_lookback_ms,
        delta1_ms,
        delta2_ms,
        sched_window_ms,
    )
