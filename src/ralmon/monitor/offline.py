"""``run_offline``: a patient-day through a ``StreamingMonitor`` (02-interfaces.md#monitor).

The cadence is the one of WS05 README D5 and of docs/formal/05 section 9.3 item 4: for each grid step
``t_k = k * T_s``, ``k = 0..K`` (``K = T_day / T_s``), push every input with ``t_rx_ms <= t_k + D``
that has not been pushed, then call ``advance(t_k + D)``. With ``D > 0`` this is what makes the
late-sample policy of docs/formal/01 section 4.3 hold: an input received after the watermark of its
step arrives after the step has been finalised and is reported late, never applied.

Keyword-only ``registry``, ``templates`` and ``verifier`` are AHEAD OF THE CONTRACT signature until
ADR-047 and ADR-048 are accepted: ``MonitorConfig`` carries only a registry version string, so without
them the registry would have to be found by the function itself. When ``registry`` is ``None`` it is
``load_registry(step_ms=config.step_ms)`` (the real registry, never a fixture); when ``templates`` is
``None`` it is ``load_templates(registry=registry)``. There is no ``history`` argument (ADR-046 is
proposed): a day starts with empty state, so a counter that depends on the previous day can only
under-count (docs/formal/01 section 5.5, item 5).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ralmon.monitor._text import as_int, converting, show
from ralmon.monitor.config import (
    T_DAY_MS,
    MonitorConfig,
    MonitorConfigError,
    MonitorInputError,
    MonitorInvariantError,
    check_config,
)
from ralmon.monitor.core import StreamingMonitor
from ralmon.monitor.verdict import VerdictRecord
from ralmon.signals import Event, ObservedTrace, Sample
from ralmon.spec import (
    CarePlan,
    PlanIntegrityError,
    PlanVerifier,
    RegistryError,
    TemplateLibraryError,
    load_registry,
    load_templates,
)

__all__ = ["run_offline"]


@converting(
    MonitorInputError, MonitorConfigError, PlanIntegrityError, MonitorInvariantError
)
def run_offline(
    day: ObservedTrace,
    plan: CarePlan,
    config: MonitorConfig,
    calibrator: object | None,
    forecaster: object | None,
    *,
    registry: Any | None = None,
    templates: Any | None = None,
    verifier: PlanVerifier | None = None,
) -> Sequence[VerdictRecord]:
    """The measured verdicts of one patient-day: every record of every step ``0..K`` in step order.

    ``calibrator`` and ``forecaster`` are accepted for the contract signature and are not used: the
    predictive mode is WS05-T08 (``config.predictive`` is refused until then). ``registry``,
    ``templates`` and ``verifier`` are keyword-only additions, ahead of the contract signature until
    ADR-047 and ADR-048 are accepted (see the module docstring).
    """
    cfg = check_config(config)
    if not isinstance(day, ObservedTrace):
        raise MonitorInputError(
            f"day must be an observed day (samples, events, ...), got {show(day)}"
        )
    samples = _items(day.samples, Sample, "samples")
    events = _items(day.events, Event, "events")
    if registry is None:
        try:
            registry = load_registry(step_ms=cfg.step_ms)
        except RegistryError as exc:
            raise MonitorConfigError(
                f"the default registry cannot be loaded: {exc}"
            ) from exc
    if templates is None:
        try:
            templates = load_templates(registry=registry)
        except TemplateLibraryError as exc:
            raise MonitorConfigError(
                f"the default template library cannot be loaded: {exc}"
            ) from exc
    monitor = StreamingMonitor(
        cfg,
        registry,
        templates,
        calibrator=calibrator,
        forecaster=forecaster,
        verifier=verifier,
    )
    monitor.load(plan)
    # inputs in the order of arrival; at one receive time samples come before events (a pressure with
    # the device time of a dispense is pre-dose, M5), then the order of the day
    arrivals: list[tuple[int, int, int, Sample | Event]] = [
        (x.t_rx_ms, 0, i, x) for i, x in enumerate(samples)
    ] + [(x.t_rx_ms, 1, i, x) for i, x in enumerate(events)]
    arrivals.sort(key=lambda a: a[:3])
    records: list[VerdictRecord] = []
    pointer = 0
    for k in range(T_DAY_MS // cfg.step_ms + 1):
        t = k * cfg.step_ms + cfg.reorder_delay_ms
        while pointer < len(arrivals) and arrivals[pointer][0] <= t:
            item = arrivals[pointer][3]
            if isinstance(item, Sample):
                monitor.push_sample(item)
            else:
                monitor.push_event(item)
            pointer += 1
        records.extend(monitor.advance(t))
    monitor.close()
    return tuple(records)


def _items(value: object, kind: type, what: str) -> list[Any]:
    """The elements of ``day.samples`` or ``day.events`` as a list of ``kind`` with integer receive times."""
    try:
        items: list[Any] = list(value)  # type: ignore[call-overload]
    except TypeError as exc:
        raise MonitorInputError(
            f"day.{what} must be a sequence, got {show(value)}"
        ) from exc
    for x in items:
        if not isinstance(x, kind):
            raise MonitorInputError(
                f"day.{what} must hold {kind.__name__} objects, got {show(x)}"
            )
        as_int(getattr(x, "t_rx_ms", None), "t_rx_ms", MonitorInputError)
    return items
