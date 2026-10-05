"""Adherence Markov model: true DISPENSE and INTAKE events of the latent day (WS04-T05).

Adherence is a **declared assumption** (analisi section 5.1): no public smart-dispenser dataset
is known, so the dosing behaviour is a Markov chain over per-dose outcomes whose parameters
come from ``AdherenceParams`` (a prior source; ``verified_by`` says whether a human checked
them). Nothing here is a clinical value or a source-backed estimate.

States, in this fixed order (``AdherenceState``): ``ON_TIME`` (0), ``DELAYED`` (1), ``OMITTED``
(2), ``DOUBLE_TAKE`` (3). One state is drawn per **slot**, the scheduled dose of one day. The
slot of a dose is the half-open interval from its tick to the next dose tick, or to the day end
for the last dose of the day (``Schedule.slot_lengths_ms``).

* ``ON_TIME``: one DISPENSE at the tick.
* ``DELAYED``: one DISPENSE at ``tick + d``, ``1 <= d <= L - 1`` (``L`` the slot length), so the
  dose is distinguishable from an on-time one and never leaves its slot. ``d - 1`` is the floor
  of an exponential of mean ``mean_delay_ms`` truncated at ``L - 1`` ms, drawn by inverse CDF
  (the family is a declared assumption).
* ``OMITTED``: nothing.
* ``DOUBLE_TAKE``: one DISPENSE at the tick and a second at ``tick + double_take_gap_ms``.

**DISPENSE is not INTAKE** (ADR-004). Each DISPENSE is an event of the dispenser (source
``dispenser``). Each DISPENSE is followed by a true INTAKE ``intake_lag_ms`` later (source
``patient``): this is the patient's act, in the **latent** day. It is not what the monitor sees:
the observed trace holds an INTAKE only if the robot witnessed it, a mapping owned by the
measurement process (WS04-T06). Declared simplification: the model has no dispensed-but-not-taken
case, so the counts of DISPENSE and INTAKE are equal; a dispense without intake would need a
further parameter the contract does not carry.

Transition law. ``transition_matrix`` (4 by 4, rows sum to 1) gives ``P(next | previous)``. The
default has four identical rows ``[1 - p_delay - p_omission - p_double_take, p_delay,
p_omission, p_double_take]`` (the memoryless special case that the contract's ``AdherenceParams``
can express). Persistence of omissions (clusters of missed doses) needs a parameter that
``AdherenceParams`` does not carry (ADR-038, gap G7): the class accepts the matrix so that a
later contract version supplies it without changing the generator. The first state of a
patient is drawn from ``initial_distribution`` (default: the marginals, which is the stationary
law of the default chain; for a custom matrix the caller chooses it, for instance the stationary
law). The chain is carried across days and never resets at midnight: ``simulate`` returns
``final_state`` and accepts it back as ``state``.

Random numbers. ``simulate`` takes the generator from the caller (the named stream
``adherence_stream``, purpose ``StreamPurpose.ADHERENCE``, one stream per patient) and consumes
exactly two uniform numbers per slot in slot order, whatever the outcome: one for the state and
one for the delay (unused unless the state is ``DELAYED``). A run of ``n`` days equals runs of
fewer days on the same generator with the state carried; adding or removing another component
does not change these numbers (streams share nothing).

Time. All times are integer milliseconds on the continuing axis ``day * T_day + clock time``.
Event order: ``(t_device_ms, kind rank, slot order)`` with DISPENSE before INTAKE at equal times
(a zero lag gives a DISPENSE and its INTAKE at one instant; an INTAKE can meet the next slot's
DISPENSE). An event may fall after the end of its slot's day (an intake of a late dose); it keeps
its place on the continuing axis and its slot keeps the day of the dose. ``t_rx_ms ==
t_device_ms`` and ``seq`` is ``None`` (latent events have no transport).
"""

from __future__ import annotations

import math
import numbers
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import IntEnum
from operator import itemgetter
from pathlib import Path
from types import MappingProxyType
from typing import Final, TypeGuard

import numpy as np

from ralmon.benchmark.latent import T_DAY_MS
from ralmon.benchmark.priors import AdherenceParams
from ralmon.benchmark.rng import StreamPurpose, stream
from ralmon.benchmark.schedule import Schedule, load_filled_rows
from ralmon.signals import DurationMs, Event, EventKind, TimeMs

__all__ = [
    "DOUBLE_TAKE_GAP_ROW",
    "INTAKE_LAG_ROW",
    "MAX_SLOTS",
    "TRANSITION_TOLERANCE",
    "AdherenceConfig",
    "AdherenceConfigError",
    "AdherenceModel",
    "AdherenceResult",
    "AdherenceState",
    "BehaviourEntry",
    "adherence_stream",
    "load_adherence_config",
    "sample_delay_ms",
    "truncated_exponential",
]

INTAKE_LAG_ROW: Final = "intake_lag_ms"
DOUBLE_TAKE_GAP_ROW: Final = "double_take_gap_ms"
_N_STATES: Final = 4  # algorithmic: the four outcome states of the model
# Largest number of slots one call may build (each slot makes up to four events).
MAX_SLOTS: Final[int] = 100_000  # algorithmic: memory guard of the generator
# Tolerance on a probability sum or a stochastic row (float rounding of the inputs).
TRANSITION_TOLERANCE: Final[float] = 1e-9  # algorithmic: float tolerance of row sums
_INT64_MAX: Final = int(np.iinfo(np.int64).max)
_NO_PAYLOAD: Final[Mapping[str, float | int | str | bool]] = MappingProxyType({})
_DISPENSER: Final = "dispenser"  # Event.source of a DISPENSE
_PATIENT: Final = "patient"  # Event.source of a true INTAKE


class AdherenceConfigError(ValueError):
    """A parameter, matrix, schedule or horizon of the adherence model is invalid."""


class AdherenceState(IntEnum):
    """Outcome of one scheduled dose. The integer values are the fixed state order."""

    ON_TIME = 0
    DELAYED = 1
    OMITTED = 2
    DOUBLE_TAKE = 3  # algorithmic: frozen state order


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _is_integer(x: object) -> TypeGuard[numbers.Integral]:
    return not isinstance(x, (bool, np.bool_)) and isinstance(x, numbers.Integral)


def _int(name: str, x: object, *, minimum: int) -> int:
    if not _is_integer(x):
        raise AdherenceConfigError(f"{name} must be an integer, got {x!r}")
    value = int(x)
    if value < minimum:
        raise AdherenceConfigError(f"{name} must be >= {minimum}, got {value}")
    return value


def _real(name: str, x: object) -> float:
    if isinstance(x, (bool, np.bool_)) or not isinstance(x, numbers.Real):
        raise AdherenceConfigError(f"{name} must be a finite number, got {x!r}")
    value = float(x)
    if not math.isfinite(value):
        raise AdherenceConfigError(f"{name} must be a finite number, got {x!r}")
    return value


def _probability(name: str, x: object) -> float:
    value = _real(name, x)
    if not 0.0 <= value <= 1.0:
        raise AdherenceConfigError(f"{name} must lie in [0, 1], got {value}")
    return value


def _distribution(name: str, x: object) -> tuple[float, ...]:
    """A length-4 vector of probabilities summing to 1 within the tolerance."""
    if isinstance(x, np.ndarray):
        x = x.tolist()
    if isinstance(x, (str, bytes)) or not isinstance(x, Sequence):
        raise AdherenceConfigError(
            f"{name} must be a sequence of 4 probabilities, got {x!r}"
        )
    if len(x) != _N_STATES:
        raise AdherenceConfigError(f"{name} needs {_N_STATES} entries, got {len(x)}")
    values = tuple(_probability(f"{name}[{k}]", v) for k, v in enumerate(x))
    if abs(sum(values) - 1.0) > TRANSITION_TOLERANCE:
        raise AdherenceConfigError(f"{name} must sum to 1, got {sum(values)}")
    return values


def _matrix(x: object) -> tuple[tuple[float, ...], ...]:
    if isinstance(x, np.ndarray):
        x = x.tolist()
    if isinstance(x, (str, bytes)) or not isinstance(x, Sequence):
        raise AdherenceConfigError(
            f"transition_matrix must be a 4 by 4 matrix, got {x!r}"
        )
    if len(x) != _N_STATES:
        raise AdherenceConfigError(
            f"transition_matrix needs {_N_STATES} rows, got {len(x)}"
        )
    return tuple(
        _distribution(f"transition_matrix row {i}", row) for i, row in enumerate(x)
    )


# ---------------------------------------------------------------------------
# Delay law
# ---------------------------------------------------------------------------


def truncated_exponential(mean: float, upper: float, u: float) -> float:
    """Inverse CDF of an exponential of mean ``mean`` truncated to ``[0, upper]``.

    ``x = -mean * ln(1 - u * (1 - exp(-upper / mean)))`` for ``u`` in ``[0, 1)``; ``u = 0``
    gives 0 and ``u -> 1`` gives ``upper``. Its mean is ``mean - upper * q / (1 - q)`` with
    ``q = exp(-upper / mean)``.
    """
    mean_value = _real("mean", mean)
    upper_value = _real("upper", upper)
    uniform = _real("u", u)
    if mean_value <= 0.0 or upper_value <= 0.0:
        raise AdherenceConfigError(
            f"mean and upper must be > 0, got {mean_value} and {upper_value}"
        )
    if not 0.0 <= uniform < 1.0:
        raise AdherenceConfigError(f"u must lie in [0, 1), got {uniform}")
    mass = -math.expm1(
        -upper_value / mean_value
    )  # 1 - exp(-upper / mean), without cancellation
    x = -mean_value * math.log1p(-uniform * mass)
    return min(max(x, 0.0), upper_value)


def sample_delay_ms(
    mean_delay_ms: DurationMs, slot_length_ms: DurationMs, u: float
) -> DurationMs:
    """Delay of a late dose in whole ms, in ``[1, slot_length_ms - 1]``.

    ``1 + floor(x)`` with ``x`` a ``truncated_exponential(mean_delay_ms, slot_length_ms - 1,
    u)`` draw, so a delayed dose is at least 1 ms late and strictly before the end of its slot.
    A slot shorter than 2 ms has no admissible delay.
    """
    mean = _int("mean_delay_ms", mean_delay_ms, minimum=1)
    slot = _int("slot_length_ms", slot_length_ms, minimum=2)
    longest = slot - 1
    x = truncated_exponential(float(mean), float(longest), u)
    return 1 + min(int(x), longest - 1)


# ---------------------------------------------------------------------------
# Configuration, results
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AdherenceConfig:
    """Timing of the events of one dose, from the design rows (no contract field for them).

    ``intake_lag_ms >= 0`` is the time from a DISPENSE to its INTAKE; ``double_take_gap_ms >= 1``
    is the time between the two DISPENSE events of a double take, and must exceed the intake lag
    (the first pill is taken before the dispenser is opened again). The gap must also be shorter
    than every slot (checked by ``AdherenceModel.simulate`` against the schedule).
    """

    intake_lag_ms: DurationMs
    double_take_gap_ms: DurationMs

    def __post_init__(self) -> None:
        lag = _int(INTAKE_LAG_ROW, self.intake_lag_ms, minimum=0)
        gap = _int(DOUBLE_TAKE_GAP_ROW, self.double_take_gap_ms, minimum=1)
        if lag >= gap:
            raise AdherenceConfigError(
                f"{INTAKE_LAG_ROW} ({lag}) must be shorter than {DOUBLE_TAKE_GAP_ROW} ({gap})"
            )
        object.__setattr__(self, "intake_lag_ms", lag)
        object.__setattr__(self, "double_take_gap_ms", gap)


def load_adherence_config(path: str | Path) -> AdherenceConfig:
    """Read ``intake_lag_ms`` and ``double_take_gap_ms`` from ``generator_design.yaml``.

    Raises ``UnfilledParameterError`` for a row that is still ``awaiting_human_value`` (no agent
    chooses these values: the only qualitative constraint is analisi section 4.5 rows 6 and 7,
    a double take clearly separated from a sub-second sensor bounce), ``PriorConfigError`` for a
    missing row, and ``AdherenceConfigError`` for a value that is not valid.
    """
    values = load_filled_rows(path, (INTAKE_LAG_ROW, DOUBLE_TAKE_GAP_ROW))
    return AdherenceConfig(
        intake_lag_ms=values[INTAKE_LAG_ROW],
        double_take_gap_ms=values[DOUBLE_TAKE_GAP_ROW],
    )


@dataclass(frozen=True, slots=True)
class BehaviourEntry:
    """One slot of the behaviour log (the sidecar of the truth file).

    ``slot_tick_ms`` is the tick of the dose on the continuing axis; ``day_index`` the day of
    the dose; ``dispense_times_ms`` the times of its DISPENSE events (empty if omitted).
    """

    slot_tick_ms: TimeMs
    day_index: int
    state: AdherenceState
    dispense_times_ms: tuple[TimeMs, ...]

    def to_json(self) -> dict[str, int | str | list[int]]:
        return {
            "slot_tick_ms": self.slot_tick_ms,
            "day_index": self.day_index,
            "state": self.state.name,
            "dispense_times_ms": list(self.dispense_times_ms),
        }


@dataclass(frozen=True, slots=True)
class AdherenceResult:
    """Latent events (sorted, DISPENSE before INTAKE at equal times), the log and the chain end.

    ``final_state`` is the state of the last slot, or the ``state`` passed in when the schedule
    has no dose (``None`` if there was none).
    """

    events: tuple[Event, ...]
    behaviour_log: tuple[BehaviourEntry, ...]
    final_state: AdherenceState | None


def adherence_stream(seed: int, patient_index: int) -> np.random.Generator:
    """The named stream of the adherence model: one per patient, purpose ``ADHERENCE``."""
    return stream(seed, patient_index, None, StreamPurpose.ADHERENCE)


# ---------------------------------------------------------------------------
# The model
# ---------------------------------------------------------------------------


def _cumulative(row: tuple[float, ...]) -> tuple[tuple[float, ...], int]:
    total = 0.0
    cumulative = []
    for p in row:
        total += p
        cumulative.append(total)
    last_positive = max(k for k, p in enumerate(row) if p > 0.0)
    return tuple(cumulative), last_positive


def _draw_state(row: tuple[tuple[float, ...], int], u: float) -> AdherenceState:
    """Inverse CDF with a strict comparison: a state of probability 0 is never drawn."""
    cumulative, last_positive = row
    for k, bound in enumerate(cumulative):
        if u < bound:
            return AdherenceState(k)
    return AdherenceState(last_positive)  # rounding left the last bound below u


def _as_state(x: object) -> AdherenceState | None:
    if x is None:
        return None
    if isinstance(x, AdherenceState):
        return x
    raise AdherenceConfigError(f"state must be an AdherenceState or None, got {x!r}")


class AdherenceModel:
    """Markov model of per-dose adherence (see the module docstring).

    ``params`` supplies the marginals (default matrix and initial law) and ``mean_delay_ms``;
    ``config`` the intake lag and double-take gap. Raises ``AdherenceConfigError`` for a
    probability outside [0, 1], marginals whose sum exceeds 1, a matrix or initial law that is
    not stochastic, or a ``mean_delay_ms`` below 1 ms when a delayed dose can occur.
    """

    def __init__(
        self,
        params: AdherenceParams,
        config: AdherenceConfig,
        *,
        transition_matrix: Sequence[Sequence[float]] | None = None,
        initial_distribution: Sequence[float] | None = None,
    ) -> None:
        p_delay = _probability("p_delay", params.p_delay)
        p_omission = _probability("p_omission", params.p_omission)
        p_double = _probability("p_double_take", params.p_double_take)
        total = p_delay + p_omission + p_double
        if total > 1.0 + TRANSITION_TOLERANCE:
            raise AdherenceConfigError(
                f"p_delay + p_omission + p_double_take = {total} exceeds 1"
            )
        marginals = (max(0.0, 1.0 - total), p_delay, p_omission, p_double)
        self._mean_delay_ms = _int("mean_delay_ms", params.mean_delay_ms, minimum=0)
        if not isinstance(config, AdherenceConfig):
            raise AdherenceConfigError(
                f"config must be an AdherenceConfig, got {config!r}"
            )
        self.config: AdherenceConfig = config
        self._matrix = (
            (marginals,) * _N_STATES
            if transition_matrix is None
            else _matrix(transition_matrix)
        )
        self._initial = (
            marginals
            if initial_distribution is None
            else _distribution("initial_distribution", initial_distribution)
        )
        delayed = AdherenceState.DELAYED
        can_delay = self._initial[delayed] > 0.0 or any(
            row[delayed] > 0.0 for row in self._matrix
        )
        if can_delay and self._mean_delay_ms < 1:
            raise AdherenceConfigError(
                "mean_delay_ms must be >= 1 when a delayed dose can occur, "
                f"got {self._mean_delay_ms}"
            )
        self._row_laws = tuple(_cumulative(row) for row in self._matrix)
        self._initial_law = _cumulative(self._initial)

    @property
    def transition_matrix(self) -> tuple[tuple[float, ...], ...]:
        """``P(next | previous)``, rows and columns in the ``AdherenceState`` order."""
        return self._matrix

    @property
    def initial_distribution(self) -> tuple[float, ...]:
        """Law of the state of the first slot of a patient."""
        return self._initial

    def simulate(
        self,
        schedule: Schedule,
        n_days: int,
        rng: np.random.Generator,
        *,
        start_day: int = 0,
        state: AdherenceState | None = None,
    ) -> AdherenceResult:
        """Events and behaviour log of ``n_days`` days from ``start_day`` on.

        ``state`` is the chain state to continue from (``final_state`` of the previous run);
        ``None`` starts the chain from ``initial_distribution``. Consumes ``2 * n_slots``
        uniform numbers from ``rng`` (none when the schedule has no dose). Raises
        ``AdherenceConfigError`` for an invalid argument, a double-take gap that is not shorter
        than every slot, more than ``MAX_SLOTS`` slots, or a time axis beyond int64.
        """
        if not isinstance(schedule, Schedule):
            raise AdherenceConfigError(f"schedule must be a Schedule, got {schedule!r}")
        days = _int("n_days", n_days, minimum=1)
        first_day = _int("start_day", start_day, minimum=0)
        if not isinstance(rng, np.random.Generator):
            raise AdherenceConfigError(
                "rng must be a numpy.random.Generator (see adherence_stream)"
            )
        carried = _as_state(state)
        lengths = schedule.slot_lengths_ms()
        ticks = schedule.dose_ticks_ms
        gap, lag = self.config.double_take_gap_ms, self.config.intake_lag_ms
        if lengths and gap >= min(lengths):
            raise AdherenceConfigError(
                f"double_take_gap_ms ({gap}) must be shorter than every slot; "
                f"the shortest slot is {min(lengths)} ms"
            )
        n_slots = days * len(ticks)
        if n_slots > MAX_SLOTS:
            raise AdherenceConfigError(
                f"{n_slots} slots exceed MAX_SLOTS = {MAX_SLOTS}; use fewer days"
            )
        if (first_day + days) * T_DAY_MS + lag > _INT64_MAX:
            raise AdherenceConfigError(
                "the time axis would leave the int64 range of milliseconds"
            )
        if n_slots == 0:
            return AdherenceResult((), (), carried)

        uniforms = rng.random(2 * n_slots).tolist()
        stamped: list[tuple[int, int, int, Event]] = []
        log: list[BehaviourEntry] = []
        previous = carried
        slot = 0
        for day in range(first_day, first_day + days):
            for tick_clock, length in zip(ticks, lengths, strict=True):
                u_state, u_delay = uniforms[2 * slot], uniforms[2 * slot + 1]
                law = (
                    self._initial_law if previous is None else self._row_laws[previous]
                )
                current = _draw_state(law, u_state)
                tick = day * T_DAY_MS + tick_clock
                dispenses: tuple[TimeMs, ...]
                if current is AdherenceState.ON_TIME:
                    dispenses = (tick,)
                elif current is AdherenceState.DELAYED:
                    dispenses = (
                        tick + sample_delay_ms(self._mean_delay_ms, length, u_delay),
                    )
                elif current is AdherenceState.DOUBLE_TAKE:
                    dispenses = (tick, tick + gap)
                else:
                    dispenses = ()
                for t in dispenses:
                    stamped.append(
                        (t, 0, slot, _event(EventKind.DISPENSE, t, _DISPENSER))
                    )
                    stamped.append(
                        (t + lag, 1, slot, _event(EventKind.INTAKE, t + lag, _PATIENT))
                    )
                log.append(BehaviourEntry(tick, day, current, dispenses))
                previous = current
                slot += 1
        stamped.sort(key=itemgetter(0, 1, 2))
        return AdherenceResult(
            events=tuple(item[-1] for item in stamped),
            behaviour_log=tuple(log),
            final_state=previous,
        )


def _event(kind: EventKind, t_ms: TimeMs, source: str) -> Event:
    return Event(
        kind=kind,
        t_device_ms=t_ms,
        t_rx_ms=t_ms,
        source=source,
        payload=_NO_PAYLOAD,
        seq=None,
    )
