"""Random scenarios for the property tests of ``ralmon.monitor`` (WS05-T04).

A ``Scenario`` is a small accepted trace (device times in whole seconds, pressures in half units, so
that every sum and difference is exact in IEEE 754) that converts to the inputs of a
``StreamingMonitor`` and to the ``Trace`` of the independent oracle. Fixture arithmetic only.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from hypothesis import strategies as st

from tests.fixtures.monitor import oracle

from .helpers import (
    BP_LOWER,
    BP_UPPER,
    F0_PATH,
    STEP,
    T_DAY,
    Inputs,
    evt,
    mark_unavailable,
    smp,
)


@dataclass(frozen=True)
class Meas:
    t: int
    bp: float
    health: float = 1.0
    inflation: float = 45_000.0
    drop_bp: bool = False
    drop_health: bool = False
    drop_inflation: bool = False


@dataclass(frozen=True)
class Scenario:
    meas: tuple[Meas, ...] = ()
    dispenses: tuple[int, ...] = ()
    standalone_bp: tuple[tuple[int, float], ...] = ()
    presence: tuple[tuple[int, float], ...] = ()
    intakes: tuple[int, ...] = ()
    auths: tuple[int, ...] = ()
    ticks: tuple[int, ...] = ()
    day_end: bool = False
    unavailable_presence: tuple[tuple[int, int], ...] = ()
    unavailable_intake: tuple[tuple[int, int], ...] = ()

    # -- conversions --------------------------------------------------------------------------

    def to_inputs(self) -> Inputs:
        inputs = Inputs()
        for m in self.meas:
            inputs.events.append(evt("measurement", m.t, source="cuff"))
            if not m.drop_bp:
                inputs.samples.append(smp("bp", m.t, m.bp))
            if not m.drop_health:
                inputs.samples.append(smp("cuff_health", m.t, m.health))
            if not m.drop_inflation:
                inputs.samples.append(smp("inflation_ms", m.t, m.inflation))
        for t, v in self.standalone_bp:
            inputs.samples.append(smp("bp", t, v))
        for t in self.dispenses:
            inputs.events.append(evt("dispense", t, source="dispenser"))
        for t in self.auths:
            inputs.samples.append(smp("auth", t, 1.0))
        for t, v in self.presence:
            inputs.samples.append(smp("presence", t, v))
        for t in self.intakes:
            inputs.events.append(evt("intake", t, source="robot"))
        for t in self.ticks:
            inputs.events.append(evt("schedule_tick", t, source="care_plan"))
        for a, b in self.unavailable_presence:
            mark_unavailable(inputs, "presence", a * STEP, b * STEP)
        for a, b in self.unavailable_intake:
            mark_unavailable(inputs, "intake", a * STEP, b * STEP)
        return inputs

    def day_end_anchors(self) -> tuple[int, ...]:
        return (T_DAY,) if self.day_end else ()

    def to_trace(self) -> oracle.Trace:
        samples: list[tuple[str, int, float]] = []
        for s in self.to_inputs().samples:
            samples.append((s.signal, s.t_device_ms, s.value))
        events = [(e.kind.value, e.t_device_ms) for e in self.to_inputs().events]
        unavailable: dict[str, list[tuple[int, int]]] = {}
        if self.unavailable_presence:
            unavailable["presence"] = list(self.unavailable_presence)
        if self.unavailable_intake:
            unavailable["intake"] = list(self.unavailable_intake)
        return oracle.Trace(STEP, samples, events, unavailable)

    def truncated(self, cut_step: int) -> Scenario:
        """The inputs visible at steps <= ``cut_step`` (device time at most ``cut_step * STEP``)."""
        limit = cut_step * STEP
        return Scenario(
            meas=tuple(m for m in self.meas if m.t <= limit),
            dispenses=tuple(t for t in self.dispenses if t <= limit),
            standalone_bp=tuple(x for x in self.standalone_bp if x[0] <= limit),
            presence=tuple(x for x in self.presence if x[0] <= limit),
            intakes=tuple(t for t in self.intakes if t <= limit),
            auths=tuple(t for t in self.auths if t <= limit),
            ticks=self.ticks,
            day_end=self.day_end,
            unavailable_presence=self.unavailable_presence,
            unavailable_intake=self.unavailable_intake,
        )

    def last_step(self) -> int:
        times = [m.t for m in self.meas] + list(self.dispenses) + list(self.intakes)
        times += list(self.auths) + [t for t, _ in self.standalone_bp]
        times += [t for t, _ in self.presence]
        return max((t + STEP - 1) // STEP for t in times) if times else 0

    def with_future(self, extra: Scenario) -> Scenario:
        """This scenario plus the inputs of ``extra`` (used to complete the future)."""
        return Scenario(
            meas=self.meas + extra.meas,
            dispenses=self.dispenses + extra.dispenses,
            standalone_bp=self.standalone_bp + extra.standalone_bp,
            presence=self.presence + extra.presence,
            intakes=self.intakes + extra.intakes,
            auths=self.auths + extra.auths,
            ticks=self.ticks,
            day_end=self.day_end,
            unavailable_presence=self.unavailable_presence,
            unavailable_intake=self.unavailable_intake,
        )


# -- oracle adapters -----------------------------------------------------------------------------


def oracle_params(path: Any = F0_PATH, step_ms: int = STEP) -> oracle.Params:
    """The F0 numbers read straight from the YAML file (no ralmon import)."""
    doc = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    values: dict[str, float] = {}
    for entry in doc["entries"]:
        values[entry["name"]] = float(entry["value"])
    return oracle.Params(
        values, values["bound_bp_lower"], values["bound_bp_upper"], step_ms
    )


def oracle_formulas(lib: Any) -> Mapping[str, str]:
    return {t.id.value: t.formula_past_time for t in lib}


# -- strategies ----------------------------------------------------------------------------------

N_SECONDS = 330 * 60  # the scenario inputs lie in the first 5.5 hours (330 steps)


def _times(max_size: int) -> st.SearchStrategy[tuple[int, ...]]:
    return st.lists(
        st.integers(0, N_SECONDS), min_size=0, max_size=max_size, unique=True
    ).map(lambda xs: tuple(sorted(x * 1000 for x in xs)))


def half_units(low: float, high: float) -> st.SearchStrategy[float]:
    return st.integers(int(low * 2), int(high * 2)).map(lambda x: x / 2)


@st.composite
def scenarios(
    draw: st.DrawFn,
    *,
    in_domain: bool = True,
    max_meas: int = 4,
    with_drops: bool = True,
    with_unavailability: bool = True,
    with_day_end: bool = True,
) -> Scenario:
    low, high = (BP_LOWER, BP_UPPER) if in_domain else (30.0, 280.0)
    m_times = draw(_times(max_meas))
    meas = []
    for t in m_times:
        drops = (
            draw(st.tuples(st.booleans(), st.booleans(), st.booleans()))
            if with_drops
            else (False,) * 3
        )
        meas.append(
            Meas(
                t,
                draw(half_units(low, high)),
                draw(st.sampled_from([1.0, 1.0, 1.0, 0.0])),
                draw(st.sampled_from([45_000.0, 45_000.0, 9_000.0, 30_000.0])),
                # a dropped sample is rare: the stale-open positions are exercised, not dominant
                drop_bp=drops[0] and draw(st.booleans()),
                drop_health=drops[1] and draw(st.booleans()),
                drop_inflation=drops[2] and draw(st.booleans()),
            )
        )
    taken = {m.t for m in meas}
    standalone = tuple(
        (t, draw(half_units(low, high))) for t in draw(_times(2)) if t not in taken
    )
    dispenses = draw(_times(3))
    auths = tuple(t for t in draw(_times(2)))
    presence_t = draw(_times(4))
    presence = tuple((t, draw(st.sampled_from([0.0, 1.0]))) for t in presence_t)
    intakes = draw(_times(2))
    ticks = draw(st.lists(st.integers(0, N_SECONDS // 2), max_size=2, unique=True))
    unav_p: tuple[tuple[int, int], ...] = ()
    unav_i: tuple[tuple[int, int], ...] = ()
    if with_unavailability:
        unav_p = tuple(
            draw(
                st.lists(
                    st.tuples(st.integers(0, 320), st.integers(0, 30)).map(
                        lambda ab: (ab[0], ab[0] + ab[1])
                    ),
                    max_size=2,
                )
            )
        )
        unav_i = tuple(
            draw(
                st.lists(
                    st.tuples(st.integers(0, 320), st.integers(0, 30)).map(
                        lambda ab: (ab[0], ab[0] + ab[1])
                    ),
                    max_size=1,
                )
            )
        )
    return Scenario(
        meas=tuple(meas),
        dispenses=dispenses,
        standalone_bp=standalone,
        presence=presence,
        intakes=intakes,
        auths=auths,
        ticks=tuple(sorted(t * 1000 for t in ticks)),
        day_end=draw(st.booleans()) if with_day_end else False,
        unavailable_presence=_non_overlapping(unav_p),
        unavailable_intake=_non_overlapping(unav_i),
    )


def _non_overlapping(
    ranges: tuple[tuple[int, int], ...],
) -> tuple[tuple[int, int], ...]:
    """Disjoint, sorted ranges (the golden masks are disjoint; overlap would be a second input)."""
    out: list[tuple[int, int]] = []
    for a, b in sorted(ranges):
        if out and a <= out[-1][1] + 1:
            continue
        out.append((a, b))
    return tuple(out)


@st.composite
def futures(draw: st.DrawFn, after_step: int) -> Scenario:
    """Inputs with device time after ``after_step``: a completion inside the bounds (05 section 2.1)."""
    start = (after_step + 1) * STEP
    span = 200 * 60  # seconds
    secs = st.integers(start // 1000 + 1, start // 1000 + span)

    m_t = draw(st.lists(secs, max_size=3, unique=True))
    meas = tuple(
        Meas(
            t * 1000,
            draw(half_units(BP_LOWER, BP_UPPER)),
            draw(st.sampled_from([1.0, 0.0])),
            draw(st.sampled_from([45_000.0, 9_000.0])),
        )
        for t in sorted(m_t)
    )
    used = {m.t for m in meas}
    disp = tuple(
        sorted({t * 1000 for t in draw(st.lists(secs, max_size=2, unique=True))} - used)
    )
    presence = tuple(
        (t * 1000, draw(st.sampled_from([0.0, 1.0])))
        for t in sorted(draw(st.lists(secs, max_size=2, unique=True)))
    )
    return Scenario(meas=meas, dispenses=disp, presence=presence)
