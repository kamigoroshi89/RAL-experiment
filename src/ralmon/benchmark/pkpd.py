"""Drug response of the latent patient and its onset window (WS04-T04).

Model (analisi §5.1 item 1; a declared simplification): one-compartment oral absorption, an
Emax effect on the concentration, and linear superposition over the true intakes::

    C(tau)   = ka / (ka - ke) * (exp(-ke tau) - exp(-ka tau))        tau = t - t_intake >= 0
    C_total  = sum_i C(t - t_i)
    effect   = Emax * sum_i s_i C(t - t_i) / (EC50 + C_total)

* **Dose convention.** The concentration is per unit dose (``D / V = 1``): ``C`` is a
  dimensionless fraction of the dose, with ``C(0) = 0`` and a peak of at most 1. ``ec50`` is
  in the same normalised units; a literature EC50 in physical units is converted to these
  units by the human in the ``rationale`` of its provenance row. ``ka`` and ``ke`` are rates
  per hour, ``tau`` is in hours, every time at the interfaces is integer milliseconds
  (ADR-017).
* **Sign convention (ADR-038, gap G6, fixed here).** ``effect`` is a pressure DECREASE in
  mmHg, a magnitude ``>= 0``, and the composition is ``sbp = baseline - effect``
  (``compose_latent_sbp``). ``Emax >= 0``; a negative Emax is an error, not an increase.
* **Per-intake scales** ``s_i >= 0`` (default 1) scale the Emax of intake ``i``: the share of
  the effect produced by that intake is ``Emax * s_i C_i / (EC50 + C_total)``. The shares of
  all intakes add up to the unscaled effect when every ``s_i`` is 1, and ``s_i = 0`` is a
  non-response to that intake whose drug still occupies the saturation term (used by the C1
  non-response injection of WS04-T09). A scale above 1 lets the effect exceed ``Emax``; the
  caller owns that choice.
* **Ground truth discipline.** This module belongs to the latent generator. It takes TRUE
  intake times only (``intake_times_from_events`` keeps ``INTAKE`` events and drops
  ``DISPENSE``: a dispenser opened without an intake has no effect). It never reads
  ``LatentDay``, ``GroundTruthEvent`` or any observed trace, and no monitor or baseline may
  call it at inference time.

The onset window of a patient is the set of integer milliseconds after a single intake at
which the modelled effect is at least ``delta_mmhg``. The effect curve of one intake is
unimodal (``C`` is unimodal and ``E`` is increasing in ``C``), so the set is an interval
``[lo, hi]`` or empty. ``derive_onset_window`` returns it in integer milliseconds rounded
INWARD: ``effect(lo) >= delta``, ``effect(hi) >= delta``, and ``effect(lo - 1) < delta``,
``effect(hi + 1) < delta`` hold exactly, as evaluated by ``OneCompartmentEmax`` itself. It is
``None`` when no integer millisecond reaches ``delta`` (a non-responder by construction).
The search is an integer bisection on that predicate on each side of the peak, so it needs
no float tolerance and is deterministic.

Numerics. ``ka == ke`` is a removable singularity: for a relative rate difference at most
``RATE_LIMIT_TOLERANCE`` the limit form ``ka tau exp(-ke tau)`` with its first-order
correction is used; elsewhere the Bateman function is evaluated as
``(ka / d) * (1 - exp(-d tau)) * exp(-m tau)`` with ``d = |ka - ke|``, ``m = min(ka, ke)``
and ``expm1``, which has no cancellation for either ordering of the rates and cannot
overflow. A ``tau`` so large that ``exp(-m tau)`` underflows gives exactly 0. Every factor is
nonnegative, so a concentration is never negative and no clamp is needed.

Resource bounds: at most ``MAX_INTAKES`` intakes, ``MAX_GRID_LEN`` grid points and
``MAX_EVALUATIONS`` intake-by-point evaluations per call, checked from the lengths before
any array is built. Every public function raises ``PkpdModelError`` (and nothing else) for an
invalid argument; the committed configuration files are never read here: parameters are
arguments (``PkpdParams`` or a ``PatientParams`` from a ``PriorSource``).
"""

from __future__ import annotations

import math
import numbers
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Protocol, TypeGuard, runtime_checkable

import numpy as np
import numpy.typing as npt

from ralmon.benchmark.latent import MAX_GRID_POINTS, LatentPressure
from ralmon.benchmark.priors import PatientParams
from ralmon.signals import MS_PER_HOUR, Event, EventKind, TimeMs

__all__ = [
    "MAX_EVALUATIONS",
    "MAX_GRID_LEN",
    "MAX_INTAKES",
    "RATE_LIMIT_TOLERANCE",
    "OneCompartmentEmax",
    "PkpdModelError",
    "PkpdParams",
    "ResponseModel",
    "apply_drug_response",
    "bateman_concentration",
    "compose_latent_sbp",
    "derive_onset_window",
    "effect_concentration",
    "emax_effect_mmhg",
    "intake_times_from_events",
    "t_max_hours",
    "window_overlap",
]

# Largest number of intakes of one call (a week has a few dozen).
MAX_INTAKES: Final[int] = 10_000  # algorithmic: resource guard of the generator
# Largest grid of one call: the latent grid limit (a per-millisecond day is refused).
MAX_GRID_LEN: Final[int] = MAX_GRID_POINTS
# Largest number of (intake, grid point) evaluations of one call (about a second of numpy).
MAX_EVALUATIONS: Final[int] = 20_000_000  # algorithmic: time guard of the generator
# Relative difference |ka - ke| / max(ka, ke) up to which the ka == ke limit form is used.
RATE_LIMIT_TOLERANCE: Final[float] = 1e-12  # algorithmic: removable-singularity guard
# Relative rate difference below which log1p is used for the peak time (no cancellation).
_LOG1P_RANGE: Final[float] = 0.5  # algorithmic: switch between log1p and log difference
_INT64_MAX: Final = int(np.iinfo(np.int64).max)
_SHOWN_CHARS: Final = 16  # algorithmic: characters kept at each end in a message


class PkpdModelError(ValueError):
    """An argument of the PK/PD model is invalid, or a result would not be representable."""


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _shown(x: object) -> str:
    """``repr`` of a value, cut short so that a huge integer does not flood a message."""
    text = repr(x)
    if len(text) <= 2 * _SHOWN_CHARS:
        return text
    return f"{text[:_SHOWN_CHARS]}...{text[-_SHOWN_CHARS:]} ({len(text)} chars)"


def _is_integer(x: object) -> TypeGuard[numbers.Integral]:
    return not isinstance(x, (bool, np.bool_)) and isinstance(x, numbers.Integral)


def _real(name: str, x: object) -> float:
    if isinstance(x, (bool, np.bool_)) or not isinstance(x, numbers.Real):
        raise PkpdModelError(f"{name} must be a finite number, got {_shown(x)}")
    try:
        value = float(x)
    except (OverflowError, ValueError, TypeError) as error:
        # an integer or fraction beyond the float range: ``float`` raises OverflowError
        raise PkpdModelError(
            f"{name} must be a finite number representable as a float, got {_shown(x)}"
        ) from error
    if not math.isfinite(value):
        raise PkpdModelError(f"{name} must be a finite number, got {_shown(x)}")
    return value


def _positive(name: str, x: object) -> float:
    value = _real(name, x)
    if not value > 0.0:
        raise PkpdModelError(f"{name} must be > 0, got {value}")
    return value


def _non_negative(name: str, x: object) -> float:
    value = _real(name, x)
    if value < 0.0:
        raise PkpdModelError(f"{name} must be >= 0, got {value}")
    return value


def _time_ms(name: str, x: object) -> int:
    """A time or duration: an integer number of ms in ``[0, int64 max]``."""
    if not _is_integer(x):
        raise PkpdModelError(f"{name} must be an integer number of ms, got {_shown(x)}")
    value = int(x)
    if not 0 <= value <= _INT64_MAX:
        raise PkpdModelError(
            f"{name} must lie in [0, {_INT64_MAX}] ms, got {_shown(value)}"
        )
    return value


def _length(name: str, x: object, maximum: int) -> int:
    """Length of a sequence or 1-D array, checked before anything is built from it."""
    if isinstance(x, np.ndarray):
        if x.ndim != 1:
            raise PkpdModelError(f"{name} must be one-dimensional, got ndim {x.ndim}")
        size = int(x.shape[0])
    elif isinstance(x, (str, bytes)) or not isinstance(x, Sequence):
        raise PkpdModelError(f"{name} must be a sequence, got {_shown(x)}")
    else:
        size = len(x)
    if size > maximum:
        raise PkpdModelError(f"{name} has {size} entries, the limit is {maximum}")
    return size


def _int_array(
    name: str, x: object, *, strictly_increasing: bool
) -> npt.NDArray[np.int64]:
    """Integer ms times of a sequence or array (length already checked) as int64."""
    if isinstance(x, np.ndarray):
        if x.dtype.kind not in "iu" or not np.can_cast(x.dtype, np.int64, "safe"):
            raise PkpdModelError(
                f"{name} must be an array of integers (int64 range), got dtype {x.dtype}"
            )
        array = x.astype(np.int64)
        if array.size and int(array.min()) < 0:
            raise PkpdModelError(f"{name} must be >= 0 ms, got {int(array.min())}")
    else:
        assert isinstance(x, Sequence)
        values = [_time_ms(f"{name}[{k}]", v) for k, v in enumerate(x)]
        array = np.array(values, dtype=np.int64)
    if strictly_increasing and array.size > 1 and not bool(np.all(np.diff(array) > 0)):
        raise PkpdModelError(
            f"{name} must be strictly increasing (sorted, no duplicate)"
        )
    return array


def _scales(x: object, n_intakes: int) -> tuple[float, ...] | None:
    if x is None:
        return None
    if isinstance(x, np.ndarray):
        if x.ndim != 1 or x.dtype.kind not in "fiu":
            raise PkpdModelError(
                f"intake_scales must be a 1-D array of numbers, got dtype {x.dtype} "
                f"and shape {x.shape}"
            )
        items: Sequence[object] = x.tolist()
    elif isinstance(x, (str, bytes)) or not isinstance(x, Sequence):
        raise PkpdModelError(f"intake_scales must be a sequence, got {_shown(x)}")
    else:
        items = x
    if len(items) != n_intakes:
        raise PkpdModelError(
            f"intake_scales has {len(items)} entries for {n_intakes} intake(s)"
        )
    return tuple(_non_negative(f"intake_scales[{k}]", v) for k, v in enumerate(items))


# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PkpdParams:
    """The four PK/PD parameters of a patient, validated at construction.

    ``emax_mmhg >= 0`` (a pressure decrease), ``ec50 > 0`` (unit-dose-normalised
    concentration), ``absorption_rate_per_h > 0`` and ``elimination_rate_per_h > 0``.
    """

    emax_mmhg: float
    ec50: float
    absorption_rate_per_h: float
    elimination_rate_per_h: float

    def __post_init__(self) -> None:
        for name, value in (
            ("emax_mmhg", _non_negative("emax_mmhg", self.emax_mmhg)),
            ("ec50", _positive("ec50", self.ec50)),
            (
                "absorption_rate_per_h",
                _positive("absorption_rate_per_h", self.absorption_rate_per_h),
            ),
            (
                "elimination_rate_per_h",
                _positive("elimination_rate_per_h", self.elimination_rate_per_h),
            ),
        ):
            object.__setattr__(self, name, value)

    @classmethod
    def from_patient(cls, patient: PatientParams) -> PkpdParams:
        """The PK/PD fields of a ``PatientParams`` (from a ``PriorSource``)."""
        if not isinstance(patient, PatientParams):
            raise PkpdModelError(f"expected a PatientParams, got {_shown(patient)}")
        return cls(
            emax_mmhg=patient.emax_mmhg,
            ec50=patient.ec50,
            absorption_rate_per_h=patient.absorption_rate_per_h,
            elimination_rate_per_h=patient.elimination_rate_per_h,
        )


def _params(params: object) -> PkpdParams:
    if isinstance(params, PkpdParams):
        return params
    if isinstance(params, PatientParams):
        return PkpdParams.from_patient(params)
    raise PkpdModelError(
        f"params must be a PkpdParams or a PatientParams, got {_shown(params)}"
    )


# ---------------------------------------------------------------------------
# Closed forms
# ---------------------------------------------------------------------------


def _bateman_array(
    ka: float, ke: float, tau_h: npt.NDArray[np.float64]
) -> npt.NDArray[np.float64]:
    """Unit-dose Bateman concentration at the times ``tau_h`` (hours; ``<= 0`` gives 0)."""
    out = np.zeros_like(tau_h)
    with np.errstate(all="ignore"):
        slowest = min(ka, ke)
        gap = abs(ka - ke)
        tau = np.where(tau_h > 0.0, tau_h, 0.0)
        decay = np.exp(
            -slowest * tau
        )  # underflows to 0; an overflowing product gives exp(-inf)
        live = decay > 0.0  # elsewhere the concentration is below the smallest float
        t, e = tau[live], decay[live]
        x = gap * t
        if gap <= RATE_LIMIT_TOLERANCE * max(ka, ke):
            out[live] = ka * t * e * (1.0 - x / 2)
        else:
            out[live] = (ka / gap) * (-np.expm1(-x)) * e
    return out


def bateman_concentration(
    absorption_rate_per_h: float, elimination_rate_per_h: float, tau_h: float
) -> float:
    """Unit-dose concentration ``ka / (ka - ke) * (exp(-ke tau) - exp(-ka tau))`` at ``tau_h``.

    ``tau_h`` in hours since the intake; ``tau_h <= 0`` gives 0 (nothing before the intake).
    For ``ka = 2``, ``ke = 1``: ``C(1 h) = 0.465088316`` and ``C(ln 2 h) = 0.5``. The limit
    ``ka == ke`` (``ka tau exp(-ke tau)``) is handled without division by zero; a ``tau``
    large enough to underflow gives exactly 0.
    """
    ka = _positive("absorption_rate_per_h", absorption_rate_per_h)
    ke = _positive("elimination_rate_per_h", elimination_rate_per_h)
    tau = _real("tau_h", tau_h)
    return float(_bateman_array(ka, ke, np.array([tau], dtype=np.float64))[0])


def _t_max(ka: float, ke: float) -> float:
    gap = ka - ke
    if abs(gap) <= RATE_LIMIT_TOLERANCE * max(ka, ke):
        return (1.0 / ke) * (1.0 - (gap / ke) / 2)
    if abs(gap) < _LOG1P_RANGE * ke:
        return math.log1p(gap / ke) / gap
    return (math.log(ka) - math.log(ke)) / gap


def t_max_hours(absorption_rate_per_h: float, elimination_rate_per_h: float) -> float:
    """Time of the concentration peak, ``ln(ka / ke) / (ka - ke)`` hours (``1 / ke`` if equal).

    For ``ka = 2``, ``ke = 1`` it is ``ln 2 = 0.693147`` h. Symmetric in ``ka`` and ``ke``.
    """
    ka = _positive("absorption_rate_per_h", absorption_rate_per_h)
    ke = _positive("elimination_rate_per_h", elimination_rate_per_h)
    value = _t_max(ka, ke)
    if not math.isfinite(value):
        raise PkpdModelError(f"the peak time of ka {ka}, ke {ke} is not representable")
    return value


def emax_effect_mmhg(params: PkpdParams | PatientParams, concentration: float) -> float:
    """``Emax * C / (EC50 + C)`` for a concentration ``C >= 0`` (unit-dose normalised).

    For ``Emax = 20``, ``EC50 = 0.25``: ``E(0) = 0``, ``E(0.25) = 10``, ``E(0.5) = 13.3333``.
    """
    p = _params(params)
    c = _non_negative("concentration", concentration)
    return p.emax_mmhg * c / (p.ec50 + c)


# ---------------------------------------------------------------------------
# The response
# ---------------------------------------------------------------------------


def _inputs(
    intake_times_ms: object, t_grid_ms: object, intake_scales: object
) -> tuple[npt.NDArray[np.int64], npt.NDArray[np.int64], tuple[float, ...] | None]:
    """Validate sizes first (from lengths only), then build the arrays."""
    n_intakes = _length("intake_times_ms", intake_times_ms, MAX_INTAKES)
    n_grid = _length("t_grid_ms", t_grid_ms, MAX_GRID_LEN)
    if n_grid == 0:
        raise PkpdModelError("t_grid_ms must not be empty")
    if n_intakes * n_grid > MAX_EVALUATIONS:
        raise PkpdModelError(
            f"{n_intakes} intake(s) on {n_grid} grid point(s) exceed MAX_EVALUATIONS = "
            f"{MAX_EVALUATIONS}"
        )
    scales = _scales(intake_scales, n_intakes)
    intakes = _int_array("intake_times_ms", intake_times_ms, strictly_increasing=False)
    grid = _int_array("t_grid_ms", t_grid_ms, strictly_increasing=True)
    return intakes, grid, scales


def _superpose(
    p: PkpdParams,
    intakes: npt.NDArray[np.int64],
    grid: npt.NDArray[np.int64],
    scales: tuple[float, ...] | None,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Total concentration and scale-weighted concentration on the grid."""
    total = np.zeros(grid.shape, dtype=np.float64)
    weighted = np.zeros(grid.shape, dtype=np.float64)
    with np.errstate(all="ignore"):
        for k, t_intake in enumerate(intakes.tolist()):
            # both operands lie in [0, int64 max]: the difference cannot wrap around
            tau_h = (grid - np.int64(t_intake)).astype(np.float64) / MS_PER_HOUR
            c = _bateman_array(p.absorption_rate_per_h, p.elimination_rate_per_h, tau_h)
            total += c
            weighted += c * (1.0 if scales is None else scales[k])
    return total, weighted


def _effect(
    p: PkpdParams,
    intakes: npt.NDArray[np.int64],
    grid: npt.NDArray[np.int64],
    scales: tuple[float, ...] | None,
) -> npt.NDArray[np.float64]:
    total, weighted = _superpose(p, intakes, grid, scales)
    with np.errstate(all="ignore"):
        effect = p.emax_mmhg * weighted / (p.ec50 + total)
    if not bool(np.all(np.isfinite(effect))):
        raise PkpdModelError(
            "the effect is not representable (intake_scales or Emax too large)"
        )
    return effect


def effect_concentration(
    params: PkpdParams | PatientParams,
    intake_times_ms: Sequence[TimeMs],
    t_grid_ms: Sequence[TimeMs],
) -> tuple[float, ...]:
    """Total unit-dose concentration ``sum_i C(t - t_i)`` on the grid (before the Emax map).

    ``intake_times_ms`` need not be sorted and may repeat (a double intake doubles ``C``);
    ``t_grid_ms`` is strictly increasing and non-empty; all times are integer ms ``>= 0``.
    """
    p = _params(params)
    intakes, grid, _ = _inputs(intake_times_ms, t_grid_ms, None)
    return tuple(_superpose(p, intakes, grid, None)[0].tolist())


@runtime_checkable
class ResponseModel(Protocol):
    """A drug-response engine: the pressure decrease (mmHg, ``>= 0``) on a time grid.

    A different engine (for example an adapter to a physiology simulator) replaces
    ``OneCompartmentEmax`` by implementing this method; callers do not change.
    """

    def effect_mmhg(
        self,
        params: PkpdParams | PatientParams,
        intake_times_ms: Sequence[TimeMs],
        t_grid_ms: Sequence[TimeMs],
        intake_scales: Sequence[float] | None = None,
    ) -> Sequence[float]: ...


class OneCompartmentEmax:
    """One-compartment oral absorption, Emax effect, linear superposition (module docstring)."""

    __slots__ = ()

    def effect_mmhg(
        self,
        params: PkpdParams | PatientParams,
        intake_times_ms: Sequence[TimeMs],
        t_grid_ms: Sequence[TimeMs],
        intake_scales: Sequence[float] | None = None,
    ) -> tuple[float, ...]:
        """Pressure decrease in mmHg on ``t_grid_ms`` caused by the TRUE intakes.

        ``intake_scales[i] >= 0`` scales the Emax of intake ``i`` (the order of
        ``intake_times_ms``, sorted or not); ``None`` means all 1. No intake gives an effect
        of exactly 0 everywhere.
        """
        p = _params(params)
        intakes, grid, scales = _inputs(intake_times_ms, t_grid_ms, intake_scales)
        return tuple(_effect(p, intakes, grid, scales).tolist())


def intake_times_from_events(events: Sequence[Event]) -> tuple[TimeMs, ...]:
    """Times of the ``INTAKE`` events (latent, true); ``DISPENSE`` and the rest are ignored."""
    _length("events", events, MAX_GRID_LEN)
    times: list[int] = []
    for k, event in enumerate(events):
        if not isinstance(event, Event):
            raise PkpdModelError(f"events[{k}] must be an Event, got {_shown(event)}")
        if event.kind == EventKind.INTAKE:
            times.append(_time_ms(f"events[{k}].t_device_ms", event.t_device_ms))
    return tuple(times)


# ---------------------------------------------------------------------------
# Composition with the latent pressure
# ---------------------------------------------------------------------------


def _vector(name: str, x: object) -> npt.NDArray[np.float64]:
    size = _length(name, x, MAX_GRID_LEN)
    if size == 0:
        raise PkpdModelError(f"{name} must not be empty")
    if isinstance(x, np.ndarray):
        if x.dtype.kind not in "fiu":
            raise PkpdModelError(
                f"{name} must be an array of numbers, got dtype {x.dtype}"
            )
        items: Sequence[object] = x.tolist()
    else:
        assert isinstance(x, Sequence)
        items = x
    return np.array(
        [_real(f"{name}[{k}]", v) for k, v in enumerate(items)], dtype=np.float64
    )


def compose_latent_sbp(
    baseline: Sequence[float] | npt.NDArray[np.float64],
    effect: Sequence[float] | npt.NDArray[np.float64],
) -> npt.NDArray[np.float64]:
    """``baseline - effect`` (mmHg), a new read-only float array.

    ``effect >= 0`` is a decrease (module docstring); the result is not clipped. With an
    effect of exactly 0 the baseline is returned bit for bit.
    """
    base = _vector("baseline", baseline)
    drop = _vector("effect", effect)
    if base.shape != drop.shape:
        raise PkpdModelError(f"baseline has {base.size} points, effect has {drop.size}")
    if float(drop.min()) < 0.0:
        raise PkpdModelError("effect must be >= 0 (a pressure decrease)")
    with np.errstate(all="ignore"):
        out = base - drop
    if not bool(np.all(np.isfinite(out))):
        raise PkpdModelError("the composed pressure is not representable")
    out.setflags(write=False)
    return out


def apply_drug_response(
    model: ResponseModel,
    params: PkpdParams | PatientParams,
    baseline: LatentPressure,
    intake_times_ms: Sequence[TimeMs],
    intake_scales: Sequence[float] | None = None,
) -> npt.NDArray[np.float64]:
    """Latent pressure with the drug: ``baseline.sbp_mmhg - model.effect_mmhg(...)``.

    The effect is evaluated on ``baseline.t_ms`` for the TRUE intakes given; any
    ``ResponseModel`` can be passed. The result has the length of the baseline grid.
    """
    if not isinstance(baseline, LatentPressure):
        raise PkpdModelError(
            f"baseline must be a LatentPressure, got {_shown(baseline)}"
        )
    if not callable(getattr(model, "effect_mmhg", None)):
        raise PkpdModelError(
            f"model must have an effect_mmhg method, got {_shown(model)}"
        )
    _params(params)
    effect = model.effect_mmhg(
        params, intake_times_ms, baseline.t_ms.tolist(), intake_scales=intake_scales
    )
    return compose_latent_sbp(baseline.sbp_mmhg, effect)


# ---------------------------------------------------------------------------
# Onset window
# ---------------------------------------------------------------------------


def derive_onset_window(
    params: PkpdParams | PatientParams, delta_mmhg: float
) -> tuple[TimeMs, TimeMs] | None:
    """Integer-ms window ``[lo, hi]`` after one intake where the effect is ``>= delta_mmhg``.

    Rounded inward (module docstring): the effect at ``lo`` and ``hi`` is ``>= delta``, one
    ms outside it is ``< delta``. ``None`` if no integer millisecond reaches ``delta`` (the
    peak effect is below it: a non-responder by construction). ``delta_mmhg`` has no default
    and must be ``> 0``: it is the registry's decrease threshold. Raises ``PkpdModelError``
    if the peak or the end of the window lies beyond the int64 range of milliseconds.
    """
    p = _params(params)
    delta = _positive("delta_mmhg", delta_mmhg)
    peak_ms = _t_max(p.absorption_rate_per_h, p.elimination_rate_per_h) * MS_PER_HOUR
    if not peak_ms < _INT64_MAX:
        raise PkpdModelError(
            f"the effect peaks at {peak_ms} ms, beyond the int64 range of milliseconds"
        )
    origin = np.zeros(1, dtype=np.int64)

    def effect_at(t_ms: int) -> float:
        grid = np.array([t_ms], dtype=np.int64)
        return float(_effect(p, origin, grid, None)[0])

    below = math.floor(peak_ms)
    best = below if effect_at(below) >= effect_at(below + 1) else below + 1
    if effect_at(best) < delta:
        return None
    # rising side: effect(0) = 0 < delta <= effect(best); integer bisection
    rise_false, rise_true = 0, best
    while rise_true - rise_false > 1:
        mid = (rise_false + rise_true) // 2
        if effect_at(mid) >= delta:
            rise_true = mid
        else:
            rise_false = mid
    # falling side: double the step until the effect is below delta, then bisect
    fall_true, step = best, 1
    while True:
        probe = min(best + step, _INT64_MAX)
        if effect_at(probe) < delta:
            fall_false = probe
            break
        if probe == _INT64_MAX:
            raise PkpdModelError(
                "the onset window extends beyond the int64 range of ms"
            )
        fall_true, step = probe, step * 2
    while fall_false - fall_true > 1:
        mid = (fall_true + fall_false) // 2
        if effect_at(mid) >= delta:
            fall_true = mid
        else:
            fall_false = mid
    return rise_true, fall_true


def window_overlap(
    window: tuple[TimeMs, TimeMs], delta1_ms: TimeMs, delta2_ms: TimeMs
) -> tuple[TimeMs, TimeMs] | None:
    """Intersection of the onset window with the registry window ``[delta1, delta2]``.

    All intervals are closed, in integer ms: touching at one instant is an overlap (a
    one-instant window), one ms apart is none (``None``).
    """
    if isinstance(window, (str, bytes)) or not isinstance(window, (tuple, list)):
        raise PkpdModelError(f"window must be a (lo, hi) pair, got {_shown(window)}")
    if len(window) != 2:
        raise PkpdModelError(f"window must have 2 entries, got {len(window)}")
    lo = _time_ms("window[0]", window[0])
    hi = _time_ms("window[1]", window[1])
    if lo > hi:
        raise PkpdModelError(f"window lower end {lo} exceeds its upper end {hi}")
    d1 = _time_ms("delta1_ms", delta1_ms)
    d2 = _time_ms("delta2_ms", delta2_ms)
    if d1 > d2:
        raise PkpdModelError(f"delta1_ms {d1} exceeds delta2_ms {d2}")
    start, end = max(lo, d1), min(hi, d2)
    return (start, end) if start <= end else None
