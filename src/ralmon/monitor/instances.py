"""The template instances: closed-form intervals, the verdict rule and the records.

The monitor is per instance, not per formula (docs/formal/01 section 3.7, 02 section 1.5, 05 section
6.2): one instance per anchor event (a measurement, a dispense), per schedule tick of the plan and
for the day-end count. Each instance keeps O(1) state and, at every finalised step, computes its
robustness interval ``[lo, hi]`` by the closed form of docs/formal/05 section 2.3 (Lemma 10), which is
the unrolling of the interval recursion of section 2.2 for the body of its template, then applies the
verdict rule and emits one record.

Why closed forms and not a sliding-window evaluator (open point OP-T05-21): the body of an instance
is evaluated at a fixed closing step, so its windows are anchored and nothing leaves them before the
instance retires; a running extremum is exact, and the cost per node is O(1) per step without a
monotone queue (05 section 6.4). The queue is the right tool for the whole-formula form, which this
monitor does not implement (review rule R1 of 08 section 5.3).

Verdict rule (05 sections 3.4 and 6.2), applied only to an instance that is PENDING, so a definitive
state is never re-evaluated:

    VIOLATED   iff hi < 0
    SATISFIED  iff lo > 0, or (k >= k_d and lo == hi == 0)       (tie rule, CP3)
    PENDING    otherwise

``k_d`` is the decision step. Everything is integer milliseconds and steps; floats appear only in the
robustness values, computed in the order of docs/formal/02 (05 section 2.6 (b)).
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final

from ralmon.monitor.config import MonitorInvariantError
from ralmon.monitor.formula import GUARD_OF, PathTable
from ralmon.monitor.measured_rho import (
    bounds_rho,
    deterministic_rho,
    difference_rho,
    lower_limit_rho,
    range_band_rho,
)
from ralmon.monitor.verdict import RobustnessInterval, VerdictRecord, VerdictState
from ralmon.spec import Rho, Template, TemplateId, normalise

__all__ = [
    "CountEndInstance",
    "CountLimitInstance",
    "EngineContext",
    "HoldInstance",
    "Instance",
    "IntInstance",
    "RangeInstance",
    "RespInstance",
    "SchedInstance",
    "StepView",
    "SysInstance",
    "WitnessTracker",
    "format_marker",
]

INF: Final = math.inf
_NAN: Final = math.nan

# the entries of the marker of an undecidable instance, in the order of docs/formal/05 section 3.5
_MARKER_ORDER: Final[tuple[str, ...]] = (
    "channel_unavailable:presence",
    "channel_unavailable:intake",
    "value_undefined:presence",
    "value_undefined:bp_pre",
    "value_undefined:bp",
    "value_undefined:cuff_health",
    "value_undefined:inflation_ms",
)
_CHANNEL_UNAVAILABLE_PRESENCE: Final = "channel_unavailable:presence"
_CHANNEL_UNAVAILABLE_INTAKE: Final = "channel_unavailable:intake"
_VALUE_UNDEFINED_PRESENCE: Final = "value_undefined:presence"


def format_marker(entries: Sequence[str]) -> str | None:
    """``undecidable: <reason>:<signal>`` with the entries in the canonical order, joined by commas."""
    if not entries:
        return None
    ordered = sorted(set(entries), key=_MARKER_ORDER.index)
    return "undecidable: " + ",".join(ordered)


@dataclass(slots=True)
class EngineContext:
    """What every instance of one monitor shares: the step, the bounds, the error model, the tables."""

    step_ms: int
    bound_lower: float
    bound_upper: float
    error_sd: float | None
    scales: Mapping[TemplateId, float]
    paths: Mapping[TemplateId, PathTable]
    rho_unavailable: int = field(default=0)


class WitnessTracker:
    """O(1) summary of the witness of INT (05 section 2.3, table of Lemma 10).

    ``last_det`` is the last step with a determined witness (``auth`` seen, ``presence`` determined to
    1, ``intake`` seen on an available channel); ``last_poss`` the last step with a possible one (a
    determined witness or an open ``presence`` or ``intake`` position); ``last_open`` the last step at
    which each kind of open position occurred (for the marker of 05 section 3.5).

    The ``presence`` level that ``update`` receives is the level of the current co-location episode: the
    caller (``StreamingMonitor``) clears it at a step where the channel is unavailable (ADR-054). The
    tracker itself holds no level.
    """

    __slots__ = ("last_det", "last_open", "last_poss")

    def __init__(self) -> None:
        self.last_det = -1
        self.last_poss = -1
        self.last_open: dict[str, int] = {}

    def update(
        self,
        k: int,
        presence_unavailable: bool,
        presence_level: float,
        intake_unavailable: bool,
        intake_seen: bool,
        auth_seen: bool,
    ) -> None:
        determined = auth_seen
        possible = auth_seen
        if presence_unavailable:
            possible = True
            self.last_open[_CHANNEL_UNAVAILABLE_PRESENCE] = k
        elif math.isnan(presence_level):
            possible = True
            self.last_open[_VALUE_UNDEFINED_PRESENCE] = k
        elif presence_level == 1.0:
            determined = True
        if intake_unavailable:
            possible = True
            self.last_open[_CHANNEL_UNAVAILABLE_INTAKE] = k
        elif intake_seen:
            determined = True
        if determined:
            self.last_det = k
            possible = True
        if possible:
            self.last_poss = k


class StepView:
    """The summaries of the finalised step ``k`` that the instances read (mutable, reused)."""

    __slots__ = (
        "bp",
        "cuff_health",
        "dose_count",
        "inflation",
        "k",
        "last_meas_step",
        "meas_now",
        "witness",
    )

    def __init__(self, witness: WitnessTracker) -> None:
        self.k = 0
        self.bp = _NAN
        self.cuff_health = _NAN
        self.inflation = _NAN
        self.meas_now = False
        self.last_meas_step = -1
        self.dose_count = 0.0
        self.witness = witness


Part = tuple[str, float, float]  # (role, lo, hi) of a sub-formula of the body


def _rank(
    parts: Sequence[Part],
    state: VerdictState,
    guard_role: str | None,
    guard_name: str | None,
) -> list[tuple[str, str | None]]:
    """The decisive sub-formula first, then (VIOLATED only) the others that are violated, by value."""
    if state is VerdictState.VIOLATED:
        order = sorted(range(len(parts)), key=lambda i: (parts[i][2], i))
        chosen = [order[0], *(i for i in order[1:] if parts[i][2] < 0.0)]
    else:
        chosen = [min(range(len(parts)), key=lambda i: (parts[i][1], i))]
    out: list[tuple[str, str | None]] = []
    for i in chosen:
        role, _lo, hi = parts[i]
        failed = state is VerdictState.VIOLATED and role == guard_role and hi == -INF
        out.append((role, guard_name if failed else None))
    return out


class Instance(ABC):
    """The shared part of an instance: the state machine, the record and the retirement rule."""

    __slots__ = (
        "_closed_done",
        "act",
        "anchor_ms",
        "closed_guard",
        "ctx",
        "decided_at_ms",
        "decided_step",
        "guard_failed",
        "horizon",
        "k_a",
        "k_d",
        "key",
        "params",
        "path",
        "pending_until_ms",
        "refines",
        "rho",
        "scale",
        "seq",
        "state",
        "template",
    )

    def __init__(
        self,
        ctx: EngineContext,
        template: Template,
        key: str,
        seq: int,
        anchor_ms: int,
        k_a: int,
        k_d: int,
        horizon: int,
        act: int,
        params: Mapping[str, float],
    ) -> None:
        self.ctx = ctx
        self.template = template
        self.key = key
        self.seq = seq
        self.anchor_ms = anchor_ms
        self.k_a = k_a
        self.k_d = k_d
        self.horizon = horizon
        self.act = act
        self.params = params
        self.scale = ctx.scales.get(template.id, 1.0)
        self.pending_until_ms = k_d * ctx.step_ms
        self.state = VerdictState.PENDING
        self.decided_step: int | None = None
        self.decided_at_ms: int | None = None
        self.rho: Rho | None = None
        self.guard_failed: str | None = None
        self.path: str | None = None
        self.closed_guard: str | None = None
        self._closed_done = False
        self.refines = False  # only SCHED keeps emitting records after its decision

    # -- provided by the template ------------------------------------------------------------

    @abstractmethod
    def interval(self, k: int, v: StepView) -> tuple[float, float]:
        """The robustness interval at step ``k`` (closed form of 05 section 2.3); may update the state."""

    @abstractmethod
    def decisive(self, state: VerdictState) -> list[tuple[str, str | None]]:
        """(role, guard marker or None) of the sub-formulas to name in the path, decisive first."""

    def guard_at_close(self, k: int, v: StepView) -> str | None:
        """The guard whose failure makes the decision-step value minus infinity, if it failed."""
        return None

    def markers(self, k: int, v: StepView) -> list[str]:
        """The stale-open positions of the decision window (05 section 3.5)."""
        return []

    def rho_violation(self, k: int) -> Rho | None:
        """The rho of a VIOLATED record at the deciding step ``k`` (06 section 2.3)."""
        return deterministic_rho()

    # -- the common part -----------------------------------------------------------------------

    def evaluate(self, k: int, v: StepView) -> tuple[float, float]:
        """The interval at step ``k``; also the guard of the decision step the first time ``k >= k_d``."""
        lo, hi = self.interval(k, v)
        if math.isnan(lo) or math.isnan(hi) or lo > hi:
            raise MonitorInvariantError(
                f"{self.key}: invalid interval [{lo}, {hi}] at step {k} (NaN or lo > hi)"
            )
        if k >= self.k_d and not self._closed_done:
            self._closed_done = True
            self.closed_guard = self.guard_at_close(k, v)
        return lo, hi

    def step(self, k: int, v: StepView) -> VerdictRecord:
        lo, hi = self.evaluate(k, v)
        if self.state is VerdictState.PENDING:
            if hi < 0.0:
                self._decide(VerdictState.VIOLATED, k)
            elif lo > 0.0 or (k >= self.k_d and lo == 0.0 and hi == 0.0):
                self._decide(VerdictState.SATISFIED, k)
        marker = None
        if self.state is VerdictState.PENDING and k >= self.k_d:
            marker = format_marker(self.markers(k, v))
        scale = self.scale
        return VerdictRecord(
            instance_key=self.key,
            template=self.template.id,
            t_eval_ms=k * self.ctx.step_ms,
            state=self.state,
            sigma_interval=RobustnessInterval(lo, hi),
            sigma_norm_interval=(normalise(lo, scale), normalise(hi, scale)),
            rho=self.rho,
            decided_at_ms=self.decided_at_ms,
            pending_until_ms=self.pending_until_ms,
            undecidable=marker,
            guard_failed=self.guard_failed,
            subformula_path=self.path,
            predicted_sigma_norm=None,
        )

    def _decide(self, state: VerdictState, k: int) -> None:
        self.state = state
        self.decided_step = k
        self.decided_at_ms = k * self.ctx.step_ms
        table = self.ctx.paths[self.template.id]
        self.path = ";".join(
            table.path(role, marker) for role, marker in self.decisive(state)
        )
        if state is VerdictState.VIOLATED:
            if k >= self.k_d:
                self.guard_failed = self.closed_guard
            self.rho = self.rho_violation(k)

    def finished(self, k: int) -> bool:
        """Whether the record of step ``k`` is the last one (05 section 6.5)."""
        if self.state is VerdictState.PENDING:
            return k >= self.horizon
        if self.refines:
            return k >= max(self.decided_step or 0, self.horizon)
        return True

    def _no_model(self) -> None:
        """No error model: a MEASURED rho cannot be given and no number is invented."""
        self.ctx.rho_unavailable += 1


def _steps(params: Mapping[str, float], name: str, step_ms: int) -> int:
    """A window parameter in steps; the alignment was checked when the plan was loaded."""
    return int(params[name]) // step_ms


class RangeInstance(Instance):
    """RANGE: ``min(bp - bp_band_low, bp_band_high - bp)`` at the measurement step (B = 0)."""

    __slots__ = ("_p",)

    def __init__(
        self,
        ctx: EngineContext,
        template: Template,
        key: str,
        seq: int,
        anchor_ms: int,
        k_a: int,
        params: Mapping[str, float],
    ) -> None:
        super().__init__(ctx, template, key, seq, anchor_ms, k_a, k_a, k_a, k_a, params)
        self._p = _NAN

    def _parts(self) -> list[Part]:
        low, high = self.params["bp_band_low"], self.params["bp_band_high"]
        p = self._p
        if math.isnan(p):
            bl, bu = self.ctx.bound_lower, self.ctx.bound_upper
            return [("lower", bl - low, bu - low), ("upper", high - bu, high - bl)]
        return [("lower", p - low, p - low), ("upper", high - p, high - p)]

    def interval(self, k: int, v: StepView) -> tuple[float, float]:
        self._p = v.bp
        (_, lo_l, hi_l), (_, lo_u, hi_u) = self._parts()
        return min(lo_l, lo_u), min(hi_l, hi_u)

    def markers(self, k: int, v: StepView) -> list[str]:
        return ["value_undefined:bp"] if math.isnan(self._p) else []

    def decisive(self, state: VerdictState) -> list[tuple[str, str | None]]:
        return _rank(self._parts(), state, None, None)

    def rho_violation(self, k: int) -> Rho | None:
        sd = self.ctx.error_sd
        if sd is None or math.isnan(self._p):
            self._no_model()
            return None
        return range_band_rho(
            self._p, self.params["bp_band_low"], self.params["bp_band_high"], sd
        )


class SysInstance(Instance):
    """SYS: ``cuff_health == 1`` and ``inflation_ms >= cuff_inflation_min`` at the measurement step."""

    __slots__ = ("_ch", "_infl")

    def __init__(
        self,
        ctx: EngineContext,
        template: Template,
        key: str,
        seq: int,
        anchor_ms: int,
        k_a: int,
        params: Mapping[str, float],
    ) -> None:
        super().__init__(ctx, template, key, seq, anchor_ms, k_a, k_a, k_a, k_a, params)
        self._ch = _NAN
        self._infl = _NAN

    def _parts(self) -> list[Part]:
        ch, infl = self._ch, self._infl
        minimum = self.params["cuff_inflation_min"]
        if math.isnan(ch):
            guard = ("guard", -INF, INF)
        elif ch == 1.0:
            guard = ("guard", INF, INF)
        else:
            guard = ("guard", -INF, -INF)
        if math.isnan(infl):
            margin = ("margin", 0.0 - minimum, INF)
        else:
            margin = ("margin", infl - minimum, infl - minimum)
        return [guard, margin]

    def interval(self, k: int, v: StepView) -> tuple[float, float]:
        self._ch = v.cuff_health
        self._infl = v.inflation
        (_, g_lo, g_hi), (_, m_lo, m_hi) = self._parts()
        return min(g_lo, m_lo), min(g_hi, m_hi)

    def guard_at_close(self, k: int, v: StepView) -> str | None:
        if not math.isnan(self._ch) and self._ch != 1.0:
            return GUARD_OF[TemplateId.SYS]
        return None

    def markers(self, k: int, v: StepView) -> list[str]:
        out = []
        if math.isnan(self._ch):
            out.append("value_undefined:cuff_health")
        if math.isnan(self._infl):
            out.append("value_undefined:inflation_ms")
        return out

    def decisive(self, state: VerdictState) -> list[tuple[str, str | None]]:
        return _rank(self._parts(), state, "guard", GUARD_OF[TemplateId.SYS])


class HoldInstance(Instance):
    """HOLD (refined form): a measurement in the look-back window and ``bp >= bp_hold_threshold``."""

    __slots__ = ("_guard_ok", "_lookback", "_p")

    def __init__(
        self,
        ctx: EngineContext,
        template: Template,
        key: str,
        seq: int,
        anchor_ms: int,
        k_a: int,
        params: Mapping[str, float],
    ) -> None:
        super().__init__(ctx, template, key, seq, anchor_ms, k_a, k_a, k_a, k_a, params)
        self._lookback = _steps(params, "hold_lookback", ctx.step_ms)
        self._guard_ok = False
        self._p = _NAN

    def _margin(self) -> tuple[float, float]:
        threshold = self.params["bp_hold_threshold"]
        p = self._p
        if math.isnan(p):
            return self.ctx.bound_lower - threshold, self.ctx.bound_upper - threshold
        return p - threshold, p - threshold

    def interval(self, k: int, v: StepView) -> tuple[float, float]:
        self._p = v.bp
        self._guard_ok = (
            v.last_meas_step >= 0 and v.last_meas_step >= self.k_a - self._lookback
        )
        if not self._guard_ok:
            return -INF, -INF
        return self._margin()

    def guard_at_close(self, k: int, v: StepView) -> str | None:
        return None if self._guard_ok else GUARD_OF[TemplateId.HOLD]

    def markers(self, k: int, v: StepView) -> list[str]:
        return ["value_undefined:bp"] if self._guard_ok and math.isnan(self._p) else []

    def decisive(self, state: VerdictState) -> list[tuple[str, str | None]]:
        m_lo, m_hi = self._margin()
        guard: Part = ("guard", INF, INF) if self._guard_ok else ("guard", -INF, -INF)
        return _rank(
            [guard, ("margin", m_lo, m_hi)], state, "guard", GUARD_OF[TemplateId.HOLD]
        )

    def rho_violation(self, k: int) -> Rho | None:
        if not self._guard_ok:
            return deterministic_rho()
        sd = self.ctx.error_sd
        if sd is None or math.isnan(self._p):
            self._no_model()
            return None
        return lower_limit_rho(self._p, self.params["bp_hold_threshold"], sd)


class CountLimitInstance(Instance):
    """COUNT, limit: ``dose_count <= dose_max_24h`` at the dispense step (B = 0)."""

    __slots__ = ()

    def __init__(
        self,
        ctx: EngineContext,
        template: Template,
        key: str,
        seq: int,
        anchor_ms: int,
        k_a: int,
        params: Mapping[str, float],
    ) -> None:
        super().__init__(ctx, template, key, seq, anchor_ms, k_a, k_a, k_a, k_a, params)

    def interval(self, k: int, v: StepView) -> tuple[float, float]:
        x = self.params["dose_max_24h"] - v.dose_count
        return x, x

    def decisive(self, state: VerdictState) -> list[tuple[str, str | None]]:
        return [("limit", None)]


class CountEndInstance(Instance):
    """COUNT, day end: ``dose_count >= dose_min_day_end`` at the closing step of the day (B = 0).

    Active from the start of its day (``act``); ``count`` is the number of accepted dispenses of the
    steps ``act + 1 .. k`` (05 section 2.3: the determined ones add to both ends, the open ones add
    ``[0, +inf)``). Early SATISFIED as soon as the count exceeds the minimum (Lemma 12).
    """

    __slots__ = ("count",)

    def __init__(
        self,
        ctx: EngineContext,
        template: Template,
        key: str,
        seq: int,
        anchor_ms: int,
        k_a: int,
        params: Mapping[str, float],
        act: int,
        count: int,
    ) -> None:
        super().__init__(ctx, template, key, seq, anchor_ms, k_a, k_a, k_a, act, params)
        self.count = count

    def interval(self, k: int, v: StepView) -> tuple[float, float]:
        lo = float(self.count) - self.params["dose_min_day_end"]
        return lo, (INF if k < self.k_d else lo)

    def decisive(self, state: VerdictState) -> list[tuple[str, str | None]]:
        return [("day_end", None)]


class SchedInstance(Instance):
    """SCHED: a measurement in ``[k_a, k_d]``; the margin is the slack to the deadline (graded).

    ``horizon`` is the closing step ``H`` of the graded body, ``max(k_d, min(k_next, K))``: the instance
    keeps emitting records, with the same state, until ``H`` (05 sections 2.3 and 6.5, TG-4).
    """

    __slots__ = ("j0",)

    def __init__(
        self,
        ctx: EngineContext,
        template: Template,
        key: str,
        seq: int,
        anchor_ms: int,
        k_a: int,
        params: Mapping[str, float],
        horizon_next: int,
    ) -> None:
        k_d = k_a + _steps(params, "sched_window", ctx.step_ms)
        super().__init__(
            ctx,
            template,
            key,
            seq,
            anchor_ms,
            k_a,
            k_d,
            max(k_d, horizon_next),
            k_a,
            params,
        )
        self.j0: int | None = None
        self.refines = True

    def interval(self, k: int, v: StepView) -> tuple[float, float]:
        if self.j0 is None and v.meas_now:
            self.j0 = k
        if self.j0 is not None:
            x = float((self.k_d - self.j0) * self.ctx.step_ms)
            return x, x
        hi = float((self.k_d - k - 1) * self.ctx.step_ms) if k < self.horizon else -INF
        return -INF, hi

    def guard_at_close(self, k: int, v: StepView) -> str | None:
        return GUARD_OF[TemplateId.SCHED] if self.j0 is None else None

    def decisive(self, state: VerdictState) -> list[tuple[str, str | None]]:
        if state is VerdictState.VIOLATED:
            return [("guard", GUARD_OF[TemplateId.SCHED])]
        return [("margin", None)]


class RespInstance(Instance):
    """RESP: a measurement in ``[k_a + delta1, k_d]`` whose drop from the pre-dose value is ``delta_resp``.

    ``pre`` is the pre-dose pressure captured at the dispense (01 section 5.3), NaN when no pressure
    precedes the dose (stale-open: the bounds of the registry stand in for it). ``m_lo`` and ``m_hi``
    are the running maxima of the margin over the accepted measurements of the window.
    """

    __slots__ = (
        "m_hi",
        "m_lo",
        "n_meas",
        "open_bp",
        "pre",
        "responses",
        "window_start",
    )

    def __init__(
        self,
        ctx: EngineContext,
        template: Template,
        key: str,
        seq: int,
        anchor_ms: int,
        k_a: int,
        params: Mapping[str, float],
        pre: float,
    ) -> None:
        k_d = k_a + _steps(params, "delta2", ctx.step_ms)
        super().__init__(ctx, template, key, seq, anchor_ms, k_a, k_d, k_d, k_a, params)
        self.pre = pre
        self.window_start = k_a + _steps(params, "delta1", ctx.step_ms)
        self.m_lo = -INF
        self.m_hi = -INF
        self.n_meas = 0
        self.open_bp = False
        self.responses: list[float] = []

    def interval(self, k: int, v: StepView) -> tuple[float, float]:
        delta = self.params["delta_resp"]
        bl, bu = self.ctx.bound_lower, self.ctx.bound_upper
        q_lo, q_hi = (bl, bu) if math.isnan(self.pre) else (self.pre, self.pre)
        if v.meas_now and self.window_start <= k <= self.k_d:
            self.n_meas += 1
            bp = v.bp
            if math.isnan(bp):
                self.open_bp = True
                c_lo = (q_lo - bu) - delta
                c_hi = (q_hi - bl) - delta
            else:
                self.responses.append(bp)
                c_lo = (q_lo - bp) - delta
                c_hi = (q_hi - bp) - delta
            self.m_lo = max(self.m_lo, c_lo)
            self.m_hi = max(self.m_hi, c_hi)
        hi = self.m_hi if k >= self.k_d else max(self.m_hi, (q_hi - bl) - delta)
        return self.m_lo, hi

    def guard_at_close(self, k: int, v: StepView) -> str | None:
        return GUARD_OF[TemplateId.RESP] if self.n_meas == 0 else None

    def markers(self, k: int, v: StepView) -> list[str]:
        out = []
        if math.isnan(self.pre):
            out.append("value_undefined:bp_pre")
        if self.open_bp:
            out.append("value_undefined:bp")
        return out

    def decisive(self, state: VerdictState) -> list[tuple[str, str | None]]:
        closed = (
            self.decided_step if self.decided_step is not None else self.k_d
        ) >= self.k_d
        if state is VerdictState.VIOLATED and closed and self.n_meas == 0:
            return [("guard", GUARD_OF[TemplateId.RESP])]
        return [("margin", None)]

    def rho_violation(self, k: int) -> Rho | None:
        if k >= self.k_d and self.n_meas == 0:
            return (
                deterministic_rho()
            )  # obligation_unmet: the absence of an event in the window
        sd = self.ctx.error_sd
        delta = self.params["delta_resp"]
        if sd is None or math.isnan(self.pre):
            self._no_model()
            return None
        if (
            k < self.k_d
        ):  # decided at the anchor step by the bounds (06 section 3.2 item 5)
            return bounds_rho(self.pre, self.ctx.bound_lower, delta, sd)
        if self.open_bp:
            self._no_model()
            return None
        return difference_rho(self.pre, self.responses, delta, sd)


class IntInstance(Instance):
    """INT: a witness (``presence``, ``intake`` or ``auth``) at or before the dispense, graded by age."""

    __slots__ = ("_hi", "_window")

    def __init__(
        self,
        ctx: EngineContext,
        template: Template,
        key: str,
        seq: int,
        anchor_ms: int,
        k_a: int,
        params: Mapping[str, float],
    ) -> None:
        super().__init__(ctx, template, key, seq, anchor_ms, k_a, k_a, k_a, k_a, params)
        self._window = _steps(params, "int_window", ctx.step_ms)
        self._hi = -INF

    def interval(self, k: int, v: StepView) -> tuple[float, float]:
        window_ms = int(self.params["int_window"])
        w = v.witness
        step = self.ctx.step_ms
        lo = float(window_ms - (k - w.last_det) * step) if w.last_det >= 0 else -INF
        hi = float(window_ms - (k - w.last_poss) * step) if w.last_poss >= 0 else -INF
        self._hi = hi
        return lo, hi

    def guard_at_close(self, k: int, v: StepView) -> str | None:
        return GUARD_OF[TemplateId.INT] if self._hi == -INF else None

    def markers(self, k: int, v: StepView) -> list[str]:
        first = k - self._window
        return [entry for entry, last in v.witness.last_open.items() if last >= first]

    def decisive(self, state: VerdictState) -> list[tuple[str, str | None]]:
        if state is VerdictState.VIOLATED and self._hi == -INF:
            return [("guard", GUARD_OF[TemplateId.INT])]
        return [("margin", None)]
