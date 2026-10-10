"""``run_offline``: a patient-day through a ``StreamingMonitor`` (02-interfaces.md#monitor).

The cadence is the one of WS05 README D5 and of docs/formal/05 section 9.3 item 4: for each grid step
``t_k = k * T_s``, ``k = 0..K`` (``K = T_day / T_s``), push every input with ``t_rx_ms <= t_k + D``
that has not been pushed, then call ``advance(t_k + D)``. With ``D > 0`` this is what makes the
late-sample policy of docs/formal/01 section 4.3 hold: an input received after the watermark of its
step arrives after the step has been finalised and is reported late, never applied.

Keyword-only ``registry``, ``templates`` and ``verifier`` are part of the contract (ADR-053, accepted):
``MonitorConfig`` carries only a registry version string, so without them the registry would have to be
found by the function itself. When ``registry`` is ``None`` it is
``load_registry(step_ms=config.step_ms)`` (the real registry, never a fixture); when ``templates`` is
``None`` it is ``load_templates(registry=registry)``.

The keyword-only ``history`` (ADR-046, accepted) holds the observed days of the same patient that precede
``day``, in increasing order of day index, on the continuing axis (``day_index * T_day + clock time``).
They are replayed first, from the first step of the first history day to the closing step of ``day``,
with the same cadence, so the state that crosses midnight (the trailing 24 h dose counter, the held
pressure and the measurement look-back, the instances whose window ends after the closing step of their
day) carries into the day. The records of the steps before the first step of ``day`` are not returned
(they were emitted by the run of the day that owns them), and neither is the day-end COUNT obligation
that closes the previous day at that first step (docs/formal/01 section 5.5, item 1): it belongs to the
run of its own day. A record of any other instance at the first step of ``day`` is returned, whatever
the day of its anchor; the closing step of a day is also the first step of the next one, so a consumer
that wants each instance decided once keys its records by ``(instance_key, t_eval_ms)``. With an empty
``history`` the run starts with empty state, exactly as before: a counter over 24 h can only under-count
(docs/formal/01 section 5.5, item 5), and nothing is dropped.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from itertools import islice
from typing import Any

from ralmon.conformal import CalibrationEpisode, ConformalCalibrator
from ralmon.monitor._text import MAX_TIME_MS, as_int, converting, show
from ralmon.monitor.config import (
    T_DAY_MS,
    MonitorConfig,
    MonitorConfigError,
    MonitorInputError,
    MonitorInvariantError,
    check_config,
)
from ralmon.monitor.core import MonitorStats, RejectedInput, StreamingMonitor
from ralmon.monitor.forecast import Forecaster
from ralmon.monitor.predictive import (
    PredictionPoint,
    StaleCalibratorError,
    _observed_sigma_true,
)
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

__all__ = [
    "OfflineResult",
    "build_calibration_episodes",
    "run_offline",
    "run_offline_detailed",
]

# algorithmic: the most days a ``history`` may span before ``day`` (from its first day to ``day``). The
# history needed is H = max(T_day, largest window parameter) (docs/formal/01 section 5.5, item 4), which
# is one day for the registry; the cost of a run grows with the days replayed, so a caller that holds a
# longer record of the patient passes only its last days
MAX_HISTORY_DAYS: int = 14


@dataclass(frozen=True, slots=True)
class OfflineResult:
    """What ``run_offline_detailed`` returns: the records of ``run_offline`` and the diagnostics of the run.

    ``late_inputs`` are the inputs excluded as late, ``rejected_inputs`` every input that was not used
    (late, finalised, duplicate, future-stamped, over capacity; the last ``REPORT_CAPACITY`` of them),
    ``stats`` the counters of the monitor at the end of the day. Not part of the contract of
    ``run_offline``, which returns the records only (ADR-053).
    """

    records: tuple[VerdictRecord, ...]
    late_inputs: tuple[RejectedInput, ...]
    rejected_inputs: tuple[RejectedInput, ...]
    stats: MonitorStats


@converting(
    MonitorInputError,
    MonitorConfigError,
    PlanIntegrityError,
    MonitorInvariantError,
    StaleCalibratorError,
)
def run_offline(
    day: ObservedTrace,
    plan: CarePlan,
    config: MonitorConfig,
    calibrator: ConformalCalibrator | None,
    forecaster: Forecaster | None,
    *,
    registry: Any | None = None,
    templates: Any | None = None,
    verifier: PlanVerifier | None = None,
    history: Sequence[ObservedTrace] = (),
) -> Sequence[VerdictRecord]:
    """The measured verdicts of one patient-day: every record of every step of the day in step order.

    The steps are ``day_index * K .. (day_index + 1) * K`` on the continuing axis of the patient (``K =
    T_day / T_s``); with a ``history`` the earlier days are replayed first and their records are not
    returned (module docstring). Raises ``MonitorInputError`` for a history of another patient, with a
    day index not smaller than the one of ``day`` or not increasing, longer than ``MAX_HISTORY_DAYS``, or
    with an item that is not an observed day.

    With ``config.predictive`` the run is predictive (ADR-060): ``calibrator`` and ``forecaster`` are required,
    ``config.alpha`` is the total level of the patient-day and the calibrator must be calibrated for
    ``forecaster.model_version`` (``StaleCalibratorError`` otherwise). Without it both are accepted and never
    called, and the records are those of the measured-only monitor (ablation A2).
    ``registry``, ``templates``, ``verifier`` and ``history`` are the keyword-only arguments of the
    contract (ADR-053, ADR-046; see the module docstring). The late and rejected inputs and the counters of the run are not reachable from here: use
    ``run_offline_detailed``.
    """
    return _run(
        day,
        plan,
        config,
        calibrator,
        forecaster,
        registry,
        templates,
        verifier,
        history,
    ).records


@converting(
    MonitorInputError,
    MonitorConfigError,
    PlanIntegrityError,
    MonitorInvariantError,
    StaleCalibratorError,
)
def run_offline_detailed(
    day: ObservedTrace,
    plan: CarePlan,
    config: MonitorConfig,
    calibrator: ConformalCalibrator | None,
    forecaster: Forecaster | None,
    *,
    registry: Any | None = None,
    templates: Any | None = None,
    verifier: PlanVerifier | None = None,
    history: Sequence[ObservedTrace] = (),
) -> OfflineResult:
    """``run_offline`` with the diagnostics of the run: the same records, plus the inputs that were not
    used and the counters of the monitor (``OfflineResult``). Same arguments, same errors."""
    return _run(
        day,
        plan,
        config,
        calibrator,
        forecaster,
        registry,
        templates,
        verifier,
        history,
    )


def _defaults(cfg: MonitorConfig, registry: Any | None, templates: Any | None) -> Any:
    """The registry and the template library of a run: the arguments, else the defaults of ADR-053."""
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
    return registry, templates


def _run(
    day: ObservedTrace,
    plan: CarePlan,
    config: MonitorConfig,
    calibrator: ConformalCalibrator | None,
    forecaster: Forecaster | None,
    registry: Any | None,
    templates: Any | None,
    verifier: PlanVerifier | None,
    history: Sequence[ObservedTrace],
    recorder: Callable[[PredictionPoint], None] | None = None,
) -> OfflineResult:
    cfg = check_config(config)
    if not isinstance(day, ObservedTrace):
        raise MonitorInputError(
            f"day must be an observed day (samples, events, ...), got {show(day)}"
        )
    samples = _items(day.samples, Sample, "day.samples")
    events = _items(day.events, Event, "day.events")
    k_day = T_DAY_MS // cfg.step_ms
    day_index = as_int(
        day.day_index,
        "day_index",
        MonitorInputError,
        low=0,
        high=MAX_TIME_MS // T_DAY_MS - 1,
    )
    earlier = _read_history(history, day, day_index)
    first_step = day_index * k_day  # the first step of the day that is returned
    run_from = (
        earlier[0][0] if earlier else day_index
    ) * k_day  # the first step that is run
    registry, templates = _defaults(cfg, registry, templates)
    monitor = StreamingMonitor(
        cfg,
        registry,
        templates,
        calibrator=calibrator,
        forecaster=forecaster,
        verifier=verifier,
    )
    monitor._start_at(run_from)  # the days of a patient lie on one continuing axis
    if recorder is not None:
        monitor._enable_recording(
            recorder
        )  # calibration: the predictive step records, it does not emit
    monitor.load(plan)
    # the day-end obligation that closes the previous day sits at this day's first step: that day's own
    # run decided it. Only a run that replays a history knows the previous day; without one it stays
    # (the present behaviour of a day that follows another with no history)
    closed_before = (
        monitor._day_end_keys_closing_at(first_step) if earlier else frozenset()
    )
    # inputs in the order of arrival; at one receive time samples come before events (a pressure with
    # the device time of a dispense is pre-dose, M5), then the order of the day
    # the replayed days come first in the running index, which orders inputs received at one time
    all_samples = [x for _d, ss, _es in earlier for x in ss] + samples
    all_events = [x for _d, _ss, es in earlier for x in es] + events
    arrivals: list[tuple[int, int, int, Sample | Event]] = [
        (x.t_rx_ms, 0, i, x) for i, x in enumerate(all_samples)
    ] + [(x.t_rx_ms, 1, i, x) for i, x in enumerate(all_events)]
    arrivals.sort(key=lambda a: a[:3])
    records: list[VerdictRecord] = []
    pointer = 0
    for k in range(run_from, first_step + k_day + 1):
        t = k * cfg.step_ms + cfg.reorder_delay_ms
        while pointer < len(arrivals) and arrivals[pointer][0] <= t:
            item = arrivals[pointer][3]
            if isinstance(item, Sample):
                monitor.push_sample(item)
            else:
                monitor.push_event(item)
            pointer += 1
        produced = monitor.advance(t)
        if k < first_step:
            continue  # emitted by the run of the day that owns the step
        if k == first_step and closed_before:
            produced = tuple(r for r in produced if r.instance_key not in closed_before)
        records.extend(produced)
    monitor.close()
    return OfflineResult(
        tuple(records),
        monitor.late_inputs(),
        monitor.rejected_inputs(),
        monitor.stats(),
    )


def _items(value: object, kind: type, what: str) -> list[Any]:
    """The elements of ``samples`` or ``events`` of a day as a list of ``kind`` with integer receive times;
    ``what`` names them in a message."""
    try:
        items: list[Any] = list(value)  # type: ignore[call-overload]
    except TypeError as exc:
        raise MonitorInputError(
            f"{what} must be a sequence, got {show(value)}"
        ) from exc
    for x in items:
        if not isinstance(x, kind):
            raise MonitorInputError(
                f"{what} must hold {kind.__name__} objects, got {show(x)}"
            )
        as_int(getattr(x, "t_rx_ms", None), "t_rx_ms", MonitorInputError)
    return items


def _read_history(
    history: object, day: ObservedTrace, day_index: int
) -> list[tuple[int, list[Sample], list[Event]]]:
    """The validated earlier days as ``(day_index, samples, events)``, in order; ``[]`` for no history.

    Read through a bounded iterator, so that an endless iterable cannot hang the call. Each item must be
    an observed day of the patient of ``day`` with a day index larger than the previous item's and
    smaller than ``day_index``, the whole history within ``MAX_HISTORY_DAYS`` days of ``day``.
    """
    try:
        items = list(islice(iter(history), MAX_HISTORY_DAYS + 1))  # type: ignore[call-overload]
    except TypeError as exc:
        raise MonitorInputError(
            f"history must be a sequence of observed days, got {show(history)}"
        ) from exc
    if len(items) > MAX_HISTORY_DAYS:
        raise MonitorInputError(
            f"history holds more than {MAX_HISTORY_DAYS} days, the most a run replays"
        )
    earlier: list[tuple[int, list[Sample], list[Event]]] = []
    for n, item in enumerate(items):
        if not isinstance(item, ObservedTrace):
            raise MonitorInputError(
                f"history[{n}] must be an observed day (samples, events, ...), got {show(item)}"
            )
        index = as_int(
            item.day_index,
            f"history[{n}].day_index",
            MonitorInputError,
            low=0,
            high=MAX_TIME_MS // T_DAY_MS - 1,
        )
        if item.patient_id != day.patient_id:
            raise MonitorInputError(
                f"history[{n}] belongs to patient {show(item.patient_id)}, the day to "
                f"{show(day.patient_id)}"
            )
        if index >= day_index:
            raise MonitorInputError(
                f"history[{n}].day_index {index} must be smaller than the day index {day_index}"
            )
        if earlier and index <= earlier[-1][0]:
            raise MonitorInputError(
                f"history day indices must increase, got {index} after {earlier[-1][0]}"
            )
        earlier.append(
            (
                index,
                _items(item.samples, Sample, f"history[{n}].samples"),
                _items(item.events, Event, f"history[{n}].events"),
            )
        )
    if earlier and day_index - earlier[0][0] > MAX_HISTORY_DAYS:
        raise MonitorInputError(
            f"history starts {day_index - earlier[0][0]} days before the day, "
            f"more than the {MAX_HISTORY_DAYS} a run replays"
        )
    return earlier


@converting(
    MonitorInputError,
    MonitorConfigError,
    PlanIntegrityError,
    MonitorInvariantError,
)
def build_calibration_episodes(
    days: Sequence[ObservedTrace],
    plans: Sequence[CarePlan],
    config: MonitorConfig,
    forecaster: Forecaster,
    *,
    registry: Any | None = None,
    templates: Any | None = None,
) -> tuple[list[CalibrationEpisode], int]:
    """The calibration episodes of the observed days: ``(episodes, n_censored)`` (ADR-060).

    ``plans[i]`` is the care plan of ``days[i]`` (a patient with several days repeats the plan). Each day is
    run through the same ``StreamingMonitor`` code path as a deployment, with the predictive step recording
    in place of the calibrator: the ``sigma_hat`` of an episode is the normalised robustness of the instance
    on the trace completed by the forecaster at the activation step, clipped into the interval of its record,
    exactly the value the monitor passes to the calibrator. An episode exists for each instance that has a
    predictive path and is PENDING at its activation step (the calibration set is the set of tested instances,
    docs/formal/06 section 4.2 item 4), and ``sigma_true`` is the normalised robustness of the instance on the
    complete observed day computed with the point evaluator (the accepted observed inputs only: a late
    measurement counts as lateness, as in G-SCHED-3, and the trace is never replaced by a latent one; this
    function has no parameter that could carry a latent day, and the monitor never receives one).

    An instance whose value is not defined on the day (its window closes after the last step of the day, or an
    open position keeps it undefined) makes no episode and is counted in ``n_censored``; so are not the
    instances without a predictive path or whose forecaster had no basis, which are not episodes of any test.
    The episodes are returned in day order, then in activation order. ``config.predictive``, ``alpha`` and the
    variant are not used (the level is the business of the calibrator that will be fitted on the episodes, and
    ``fit(..., model_version=forecaster.model_version)`` ties it to the model). The reorder delay is that of
    ``config``; nothing is read from the days but their samples and events.
    """
    cfg = check_config(config)
    day_list = _sequence(days, "days")
    plan_list = _sequence(plans, "plans")
    if len(day_list) != len(plan_list):
        raise MonitorInputError(
            f"plans must hold one care plan per day: {len(plan_list)} plans for {len(day_list)} days"
        )
    registry, templates = _defaults(cfg, registry, templates)
    k_day = T_DAY_MS // cfg.step_ms
    episodes: list[CalibrationEpisode] = []
    censored = 0
    for n, (day, plan) in enumerate(zip(day_list, plan_list, strict=True)):
        points: list[PredictionPoint] = []
        _run(
            day,
            plan,
            replace(cfg, predictive=False),
            None,
            forecaster,
            registry,
            templates,
            None,
            (),
            recorder=points.append,
        )
        samples = _items(day.samples, Sample, f"days[{n}].samples")
        events = _items(day.events, Event, f"days[{n}].events")
        last_step = (day.day_index + 1) * k_day
        for point in points:
            sigma_true = _observed_sigma_true(
                point,
                samples,
                events,
                reorder_delay_ms=cfg.reorder_delay_ms,
                last_step=last_step,
            )
            if sigma_true is None:
                censored += 1
                continue
            episodes.append(
                CalibrationEpisode(
                    day.patient_id,
                    day.day_index,
                    point.template.id,
                    point.sigma_hat,
                    sigma_true,
                )
            )
    return episodes, censored


def _sequence(value: object, what: str) -> list[Any]:
    """``value`` as a list (a list or a tuple), else ``MonitorInputError``."""
    if not isinstance(value, (list, tuple)):
        raise MonitorInputError(f"{what} must be a list or a tuple, got {show(value)}")
    return list(value)
