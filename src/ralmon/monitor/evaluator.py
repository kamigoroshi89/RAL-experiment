"""The point evaluator: raw robustness of one template instance on a grid (ADR-013, outcome C).

``make_point_evaluator`` is the entry point of the baselines that need the raw robustness of a
template without the interval layer, the verdict states or the forecaster: B3 (plain STL) and B5 (WS06).
The spike of WS05-T02 found that RTAMT cannot host the templates (the term ``age``, the equality atom,
the unavailable channel), so the evaluator is the project's own and shares the closed forms of the
monitor: at a step where the decision window is closed and no position of it is open the interval of
the instance is a point and its value is the robustness of docs/formal/02 section 1.5.

``step(t_ms, values)`` takes the values of one grid step, from step 0 on, consecutively:

* a held signal (``bp``, ``cuff_health``, ``inflation_ms``, ``presence``) is its held value; a missing
  key or ``NaN`` is undefined (an open position, 01 section 3.5); ``None`` for ``presence`` and
  ``intake`` is an unavailable channel, never a zero;
* an impulse (``meas``, ``dispense``, ``intake``, ``auth``) is its multiplicity at the step; a missing
  key is no event;
* the derived signals ``dose_count`` (a missing key is read as 0, a counter) and ``bp_pre`` (the
  pre-dose value captured at the anchor step; when it is missing the held ``bp`` of that step is used).

It returns ``None`` until the instance is closed and defined, then the value in ``Template.unit``
(``-inf`` for a failed guard, with ``guard_failed`` naming it); SCHED keeps grading the lateness of
the first measurement after its deadline. The ``day_end`` COUNT obligation counts the ``dispense``
multiplicities of the steps of its day.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any, Final, Protocol

from ralmon.monitor._text import as_int, as_number, converting, show
from ralmon.monitor.config import (
    T_DAY_MS,
    MonitorConfigError,
    MonitorInputError,
    MonitorInvariantError,
)
from ralmon.monitor.formula import (
    REFERENCE_FORMULAS,
    build_path_table,
    parse_formula,
    resolve_subformula_path,
    resolve_subformula_paths,
)
from ralmon.monitor.instances import (
    CountEndInstance,
    CountLimitInstance,
    EngineContext,
    HoldInstance,
    Instance,
    IntInstance,
    RangeInstance,
    RespInstance,
    SchedInstance,
    StepView,
    SysInstance,
    WitnessTracker,
)
from ralmon.monitor.parameters import (
    check_alignment,
    check_registry,
    layer_values,
    read_bounds,
    read_overrides,
    read_value,
)
from ralmon.signals import TimeMs
from ralmon.spec import RobustnessUnit, Template, TemplateId, TemplateInstance

__all__ = [
    "PointEvaluator",
    "make_point_evaluator",
    "parse_formula",
    "resolve_subformula_path",
    "resolve_subformula_paths",
]

_NAN: Final = math.nan
# the anchoring events of the templates (docs/formal/02 section 3.2)
_ANCHOR_KINDS: Final[dict[TemplateId, tuple[str, ...]]] = {
    TemplateId.RANGE: ("measurement",),
    TemplateId.SYS: ("measurement",),
    TemplateId.HOLD: ("dispense",),
    TemplateId.RESP: ("dispense",),
    TemplateId.INT: ("dispense",),
    TemplateId.SCHED: ("sched_tick",),
    TemplateId.COUNT: ("dispense", "day_end"),
}


class PointEvaluator(Protocol):
    """One template instance stepped on the grid: ``step`` returns its raw robustness or ``None``."""

    @property
    def unit(self) -> RobustnessUnit: ...

    @property
    def guard_failed(self) -> str | None: ...

    def step(
        self, t_ms: TimeMs, values: Mapping[str, float | None]
    ) -> float | None: ...


def _cell(value: object, name: str) -> float | None:
    """A value of the step: ``None`` (unavailable), a real number or ``NaN`` (undefined); never ``inf``."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MonitorInputError(
            f"values[{name!r}] must be a number or None, got {show(value)}"
        )
    number = float(value)
    if math.isinf(number):
        raise MonitorInputError(
            f"values[{name!r}] must be finite or NaN, got {show(value)}"
        )
    return number


def _held(row: Mapping[str, float | None], name: str) -> float:
    value = row.get(name)
    return _NAN if value is None else value


def _count(row: Mapping[str, float | None], name: str) -> float:
    value = row.get(name)
    return 0.0 if value is None or math.isnan(value) else value


class _Evaluator:
    """The state of one point evaluator: the shared summaries and the instance once it exists."""

    def __init__(
        self,
        template: Template,
        anchor_ms: int,
        kind: str,
        params: Mapping[str, float],
        ctx: EngineContext,
        first_step: int = 0,
    ) -> None:
        self._template = template
        self._ctx = ctx
        self._params = params
        self._kind = kind
        self._step = ctx.step_ms
        self._k_day = T_DAY_MS // ctx.step_ms
        self._k_a = -(-anchor_ms // ctx.step_ms)
        self._witness = WitnessTracker()
        self._view = StepView(self._witness)
        self._next = first_step
        self._last_meas = -1
        self._instance: Instance | None = None
        self._value: float | None = None
        self._frozen = False
        self._anchor_ms = anchor_ms
        # the step at which the instance is created: the anchor step, or the start of the day (day end)
        self._create_at = self._k_a - self._k_day if kind == "day_end" else self._k_a

    @property
    def unit(self) -> RobustnessUnit:
        return self._template.unit

    @property
    def guard_failed(self) -> str | None:
        """The guard that makes the current value minus infinity; ``None`` once the value is finite."""
        if self._instance is None or self._value != -math.inf:
            return None
        return self._instance.closed_guard

    def _make(self, row: Mapping[str, float | None]) -> Instance:
        tid, ctx, key = (
            self._template.id,
            self._ctx,
            f"{self._template.id.value}@{self._anchor_ms}",
        )
        k_a, anchor, params = self._k_a, self._anchor_ms, self._params
        if tid is TemplateId.RANGE:
            return RangeInstance(ctx, self._template, key, 0, anchor, k_a, params)
        if tid is TemplateId.SYS:
            return SysInstance(ctx, self._template, key, 0, anchor, k_a, params)
        if tid is TemplateId.HOLD:
            return HoldInstance(ctx, self._template, key, 0, anchor, k_a, params)
        if tid is TemplateId.INT:
            return IntInstance(ctx, self._template, key, 0, anchor, k_a, params)
        if tid is TemplateId.RESP:
            pre = row.get("bp_pre")
            return RespInstance(
                ctx,
                self._template,
                key,
                0,
                anchor,
                k_a,
                params,
                _held(row, "bp") if pre is None else pre,
            )
        if tid is TemplateId.SCHED:
            close = ((max(k_a, 1) - 1) // self._k_day + 1) * self._k_day
            return SchedInstance(
                ctx, self._template, key, 0, anchor, k_a, params, close
            )
        if self._kind == "day_end":
            return CountEndInstance(
                ctx, self._template, key, 0, anchor, k_a, params, k_a - self._k_day, 0
            )
        return CountLimitInstance(ctx, self._template, key, 0, anchor, k_a, params)

    @converting(MonitorInputError, MonitorInvariantError)
    def step(self, t_ms: object, values: object) -> float | None:
        t = as_int(t_ms, "t_ms", MonitorInputError)
        if t != self._next * self._step:
            raise MonitorInputError(
                f"the next step is {self._next} (t_ms {self._next * self._step}); steps are consecutive "
                f"from step 0, got t_ms {t}"
            )
        if not isinstance(values, Mapping):
            raise MonitorInputError(f"values must be a mapping, got {show(values)}")
        row: dict[str, float | None] = {}
        for name, value in values.items():
            if not isinstance(name, str):
                raise MonitorInputError(f"values keys must be str, got {show(name)}")
            row[name] = _cell(value, name)
        k = self._next
        view = self._view
        view.k = k
        view.bp = _held(row, "bp")
        view.cuff_health = _held(row, "cuff_health")
        view.inflation = _held(row, "inflation_ms")
        view.meas_now = _count(row, "meas") > 0
        if view.meas_now:
            self._last_meas = k
        view.last_meas_step = self._last_meas
        view.dose_count = _count(row, "dose_count")
        presence_off = "presence" in row and row["presence"] is None
        intake_off = "intake" in row and row["intake"] is None
        self._witness.update(
            k,
            presence_off,
            _NAN if presence_off else _held(row, "presence"),
            intake_off,
            not intake_off and _count(row, "intake") > 0,
            _count(row, "auth") > 0,
        )
        if self._instance is None and k == self._create_at:
            self._instance = self._make(row)
        instance = self._instance
        if instance is not None and not self._frozen:
            if isinstance(instance, CountEndInstance) and k > instance.act:
                instance.count += int(_count(row, "dispense"))
            lo, hi = instance.evaluate(k, view)
            if k >= instance.k_d:
                self._value = (
                    lo if isinstance(instance, SchedInstance) or lo == hi else None
                )
                if not isinstance(instance, SchedInstance) or k >= instance.horizon:
                    self._frozen = True
        self._next += 1
        return self._value


def _evaluator_from(
    template: Template,
    anchor_ms: int,
    kind: str,
    params: Mapping[str, float],
    ctx: EngineContext,
    first_step: int,
) -> PointEvaluator:
    """A point evaluator that starts at grid step ``first_step`` (package-private; used by the predictive step).

    The parameters were validated when the plan was loaded and ``ctx`` is the one of the monitor, so nothing is
    read from a registry here. ``first_step`` must be the creation step of the instance (the step of its anchor
    for SCHED and RESP): no earlier step is needed by those two templates, and starting there makes a prediction
    cost the length of its window and not the position of the instant on the continuing axis of the patient.
    """
    return _Evaluator(template, anchor_ms, kind, params, ctx, first_step)


@converting(MonitorConfigError)
def make_point_evaluator(
    template: Template,
    instance: TemplateInstance,
    registry: Any,
    step_ms: int,
    *,
    anchor_kind: str | None = None,
) -> PointEvaluator:
    """A ``PointEvaluator`` for one instance of ``template`` anchored at ``instance.anchor_ms``.

    ``registry`` gives the parameters (``instance.param_values`` may replace a value inside an approved
    range, ADR-047 (g)) and the physiological bounds; ``step_ms`` must be the step of the registry.
    ``anchor_kind`` is ``measurement`` (RANGE, SYS), ``dispense`` (HOLD, RESP, INT, COUNT limit),
    ``sched_tick`` (SCHED) or ``day_end`` (COUNT day-end obligation); it defaults to the anchor of the
    template. Raises ``MonitorConfigError`` for an argument that cannot be used.

    The caller builds ``values`` (docs/formal/01 sections 3 and 5): the level of ``presence`` that it
    passes is the level of the current co-location episode, that is absent (undefined) from the step at
    which the channel returns until the first new sample, and ``None`` while the channel is unavailable
    (ADR-054, proposed). The evaluator cannot tell a held level from a new sample, so it does not clear a
    stale one: a baseline that holds a presence level across an outage disagrees with the monitor.
    """
    if not isinstance(template, Template):
        raise MonitorConfigError(f"template must be a Template, got {show(template)}")
    if not isinstance(instance, TemplateInstance):
        raise MonitorConfigError(
            f"instance must be a TemplateInstance, got {show(instance)}"
        )
    if instance.template is not template.id:
        raise MonitorConfigError(
            f"instance of template {show(instance.template)} given with the template {template.id.value}"
        )
    check_registry(registry)
    step = as_int(step_ms, "step_ms", MonitorConfigError, low=1, high=T_DAY_MS)
    if T_DAY_MS % step != 0:
        raise MonitorConfigError(f"step_ms {step} must divide the day of {T_DAY_MS} ms")
    registry_step = getattr(registry, "step_ms", None)
    if registry_step is not None and registry_step != step:
        raise MonitorConfigError(
            f"step_ms {step} differs from the step_ms of the registry {show(registry_step)}"
        )
    if parse_formula(template.formula_past_time) != parse_formula(
        REFERENCE_FORMULAS[template.id]
    ):
        raise MonitorConfigError(
            f"template {template.id.value}: formula_past_time differs from the formula that the closed forms implement"
        )
    allowed = _ANCHOR_KINDS[template.id]
    if anchor_kind is None:
        kind = allowed[0]
    elif isinstance(anchor_kind, str) and anchor_kind in allowed:
        kind = anchor_kind
    else:
        raise MonitorConfigError(
            f"anchor_kind for template {template.id.value} must be one of {list(allowed)}, got {show(anchor_kind)}"
        )
    anchor = instance.anchor_ms
    if anchor is None:
        raise MonitorConfigError(
            "instance.anchor_ms is required: the anchor of the instance"
        )
    anchor = as_int(anchor, "instance.anchor_ms", MonitorConfigError)
    if kind == "day_end" and (anchor < T_DAY_MS or anchor % T_DAY_MS != 0):
        raise MonitorConfigError(
            f"a day-end anchor must be a closing step of a day (a positive multiple of {T_DAY_MS} ms), got {anchor}"
        )
    defaults = {n: read_value(registry, n) for n in template.params}
    if not isinstance(instance.param_values, Mapping):
        raise MonitorConfigError(
            f"instance.param_values must be a mapping, got {show(instance.param_values)}"
        )
    own = layer_values(
        template,
        defaults,
        read_overrides(registry),
        {
            str(n): as_number(v, f"param_values[{n!r}]", MonitorConfigError)
            for n, v in instance.param_values.items()
        },
        f"instance {instance.instance_key!r}",
    )
    params = {**defaults, **own}
    check_alignment(params, step, f"instance {instance.instance_key!r}")
    lower, upper = read_bounds(registry)
    ctx = EngineContext(
        step, lower, upper, None, {}, {template.id: build_path_table(template.id)}
    )
    return _Evaluator(template, anchor, kind, params, ctx)
