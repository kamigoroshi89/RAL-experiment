"""First layer of the latent patient: systolic pressure without drug or measurement (WS04-T03).

Model (analisi §5.1 item 1; a declared simplification, see below)::

    sbp(t_k) = baseline + A * cos(2 pi (t_k - t_peak) / T_day) + x_k

* ``baseline`` is ``PatientParams.baseline_sbp_mmhg`` (mmHg).
* The circadian component is a single harmonic of period ``T_day`` (24 h) over the **clock
  time of day**, so it repeats exactly every day on the continuing time axis. ``t_peak`` is
  ``circadian_peak_clock_ms``, the clock time of its maximum: a parameter that the prior
  contract has no field for (row of ``configs/benchmark/generator_design.yaml``, filled by a
  human). The nocturnal dip is the minimum of the harmonic, half a day after ``t_peak``; it
  is nocturnal when the human-supplied ``t_peak`` falls in the daytime, which this module
  does not choose or check.
* **Amplitude convention.** ``A = PatientParams.circadian_amplitude_mmhg`` is HALF the
  peak-to-trough difference: the curve runs from ``baseline - A`` to ``baseline + A`` and the
  peak-to-trough difference is ``2 A``. A source that reports a peak-to-trough dip must be
  halved by the human transcribing it.
* ``x`` is an AR(1) noise, ``x_k = phi_s x_{k-1} + s_e z_k``, ``z_k`` i.i.d. standard normal,
  with stationary standard deviation ``ar_noise_sd_mmhg``. ``phi_s`` is the coefficient
  ``ar_noise_phi`` rescaled from the sampling step at which it was estimated
  (``ar_reference_step_ms``) to the grid step: ``phi_s = phi ** (step / reference_step)``,
  the autocorrelation of the same continuous-time process. The innovation SD is
  ``s_e = sd * sqrt(1 - phi_s ** 2)``, so the stationary SD does not depend on the step.
* **Initialisation.** A run that starts a patient (no carried state) draws ``x_0`` from the
  stationary law ``N(0, sd ** 2)``: there is no burn-in and no transient. A run that continues
  a previous one is given ``ar_state_mmhg``, the last value of that run, and starts from
  ``phi_s * state + s_e * z``; nothing resets at midnight.

Random numbers. The function consumes exactly one standard normal per grid point, in order,
whatever the parameters (a zero SD still consumes them): ``n_days`` days in one call and the
same days in several consecutive calls on one generator, with the AR state carried, give the
same numbers. The generator comes from ``ralmon.benchmark.rng.stream`` with the purpose
``LATENT_AR``; nothing here touches global random state or the clock.

Grid. Time is integer milliseconds on the continuing axis ``t_k = start_day * T_day + k * T_s``
(``docs/formal/01-signals-sampling.md``, section 3.1), ``k = 0 .. n_days * T_day / T_s - 1``.
The grid is half-open: the 24:00 instant of the last day is the step 0 of the next day and is
not emitted twice. ``T_s`` must divide ``T_day``. The grid size is checked against
``MAX_GRID_POINTS`` before any array is allocated, so a per-millisecond day (86 400 000
points) is refused, not built.

Values are never clipped: whether a value lies outside the physiological bounds is reported by
the validation report (WS04-T12), not hidden here. Not here: drug response (WS04-T04),
measurement (WS04-T06). A single harmonic is a declared simplification: dipper and non-dipper
patterns would need further literature parameters.
"""

from __future__ import annotations

import math
import numbers
from dataclasses import dataclass
from typing import Final, TypeGuard

import numpy as np
import numpy.typing as npt

from ralmon.benchmark.priors import PatientParams
from ralmon.signals import MS_PER_HOUR, DurationMs

__all__ = [
    "MAX_GRID_POINTS",
    "T_DAY_MS",
    "LatentModelError",
    "LatentPressure",
    "circadian",
    "innovation_sd",
    "rescale_ar1_phi",
    "simulate_baseline_sbp",
]

T_DAY_MS: Final[DurationMs] = 24 * MS_PER_HOUR  # algorithmic: a patient-day is 24 h
# Largest number of grid points one call may build (each of four float or int arrays: 8 MB).
MAX_GRID_POINTS: Final[int] = 1_000_000  # algorithmic: memory guard of the generator
_INT64_MAX: Final = int(np.iinfo(np.int64).max)


class LatentModelError(ValueError):
    """A parameter, step or horizon of the latent model is invalid."""


@dataclass(frozen=True, slots=True)
class LatentPressure:
    """The latent systolic pressure on an integer-millisecond grid (arrays are read-only).

    ``sbp_mmhg == (baseline + circadian_mmhg) + ar_noise_mmhg`` exactly, in that order.
    """

    t_ms: npt.NDArray[np.int64]
    circadian_mmhg: npt.NDArray[np.float64]
    ar_noise_mmhg: npt.NDArray[np.float64]
    sbp_mmhg: npt.NDArray[np.float64]

    @property
    def ar_state_mmhg(self) -> float:
        """The last AR value: pass it as ``ar_state_mmhg`` to continue the run."""
        return float(self.ar_noise_mmhg[-1])


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _is_integer(x: object) -> TypeGuard[numbers.Integral]:
    return not isinstance(x, (bool, np.bool_)) and isinstance(x, numbers.Integral)


def _int(name: str, x: object, *, minimum: int) -> int:
    if not _is_integer(x):
        raise LatentModelError(f"{name} must be an integer, got {x!r}")
    value = int(x)
    if value < minimum:
        raise LatentModelError(f"{name} must be >= {minimum}, got {value}")
    return value


def _finite(name: str, x: object) -> float:
    if isinstance(x, (bool, np.bool_)) or not isinstance(x, numbers.Real):
        raise LatentModelError(f"{name} must be a finite number, got {x!r}")
    value = float(x)
    if not math.isfinite(value):
        raise LatentModelError(f"{name} must be a finite number, got {x!r}")
    return value


def _non_negative(name: str, x: object) -> float:
    value = _finite(name, x)
    if value < 0.0:
        raise LatentModelError(f"{name} must be >= 0, got {value}")
    return value


def _stationary_phi(phi: object) -> float:
    value = _finite("ar_noise_phi", phi)
    if not abs(value) < 1.0:
        raise LatentModelError(
            f"ar_noise_phi must lie strictly inside (-1, 1) for a stationary AR(1), got {value}"
        )
    return value


def _peak_clock(peak_clock_ms: object) -> int:
    if not _is_integer(peak_clock_ms):
        raise LatentModelError(
            f"circadian_peak_clock_ms must be an integer, got {peak_clock_ms!r}"
        )
    value = int(peak_clock_ms)
    if not 0 <= value < T_DAY_MS:
        raise LatentModelError(
            f"circadian_peak_clock_ms is a clock time of day in [0, {T_DAY_MS}), got {value}"
        )
    return value


# ---------------------------------------------------------------------------
# Closed forms
# ---------------------------------------------------------------------------


def innovation_sd(ar_noise_sd_mmhg: float, phi: float) -> float:
    """SD of the AR(1) innovation that gives stationary SD ``ar_noise_sd_mmhg``.

    ``sd * sqrt(1 - phi ** 2)``; for ``sd = 8`` and ``phi = 0.6`` it is ``6.4``.
    """
    sd = _non_negative("ar_noise_sd_mmhg", ar_noise_sd_mmhg)
    coefficient = _stationary_phi(phi)
    return sd * math.sqrt((1.0 - coefficient) * (1.0 + coefficient))


def rescale_ar1_phi(phi: float, ref_step_ms: DurationMs, step_ms: DurationMs) -> float:
    """The AR(1) coefficient at ``step_ms`` of a process estimated at ``ref_step_ms``.

    ``phi ** (step_ms / ref_step_ms)``: the same continuous-time process (exponentially
    decaying autocorrelation) sampled at another step. A negative coefficient has a real value
    only when ``step_ms`` is an integer multiple of ``ref_step_ms`` (a subsampling, ``phi ** n``);
    any other ratio raises ``LatentModelError``. A result that rounds to 1.0 is refused.
    """
    coefficient = _stationary_phi(phi)
    ref = _int("ref_step_ms", ref_step_ms, minimum=1)
    step = _int("step_ms", step_ms, minimum=1)
    if coefficient == 0.0:
        return 0.0
    if coefficient > 0.0:
        rescaled = float(coefficient ** (step / ref))
    elif step % ref == 0:
        rescaled = float(coefficient ** (step // ref))
    else:
        raise LatentModelError(
            f"a negative ar_noise_phi ({coefficient}) has no real value at step {step} ms "
            f"from reference step {ref} ms: the ratio is not an integer"
        )
    if not abs(rescaled) < 1.0:
        raise LatentModelError(
            f"the rescaled coefficient {rescaled} is not strictly inside (-1, 1)"
        )
    return rescaled


def circadian(
    t_ms: npt.ArrayLike, amplitude_mmhg: float, peak_clock_ms: DurationMs
) -> npt.NDArray[np.float64]:
    """``A * cos(2 pi (t - t_peak) / T_day)`` in mmHg, for integer times ``t_ms``.

    ``amplitude_mmhg`` is half the peak-to-trough difference (module docstring). The phase is
    reduced with integer arithmetic, so the result is exactly periodic with period ``T_day``
    and exact for every int64 time, including the ends of the axis (a negative time is read as
    clock time modulo a day).
    """
    amplitude = _non_negative("circadian_amplitude_mmhg", amplitude_mmhg)
    peak = _peak_clock(peak_clock_ms)
    times = np.asarray(t_ms)
    if times.dtype.kind not in "iu" or not np.can_cast(times.dtype, np.int64, "safe"):
        raise LatentModelError(
            f"t_ms must be an array of integers (int64 range), got dtype {times.dtype}"
        )
    # (t - peak) mod T == ((t mod T) - peak) mod T. Reducing t first keeps every operand in
    # (-T, T): no int64 wrap-around at the ends of the axis (t - peak can leave the range).
    phase = ((times.astype(np.int64) % T_DAY_MS) - peak) % T_DAY_MS
    angle = phase.astype(np.float64) * (math.tau / T_DAY_MS)
    return np.asarray(amplitude * np.cos(angle), dtype=np.float64)


# ---------------------------------------------------------------------------
# The simulation
# ---------------------------------------------------------------------------


def _grid_points(step_ms: int, n_days: int) -> int:
    if T_DAY_MS % step_ms != 0:
        raise LatentModelError(
            f"latent_step_ms {step_ms} does not divide the day ({T_DAY_MS} ms); "
            "a step larger than a day cannot divide it either"
        )
    points = n_days * (T_DAY_MS // step_ms)  # Python ints: no overflow, no allocation
    if points > MAX_GRID_POINTS:
        raise LatentModelError(
            f"the grid of {points} points ({n_days} day(s) at {step_ms} ms) exceeds "
            f"MAX_GRID_POINTS = {MAX_GRID_POINTS}; use a coarser step or fewer days"
        )
    return points


def _read_only(array: npt.NDArray[np.generic]) -> None:
    array.setflags(write=False)


def simulate_baseline_sbp(
    params: PatientParams,
    latent_step_ms: DurationMs,
    n_days: int,
    circadian_peak_clock_ms: DurationMs,
    ar_reference_step_ms: DurationMs,
    rng: np.random.Generator,
    *,
    start_day: int = 0,
    ar_state_mmhg: float | None = None,
) -> LatentPressure:
    """Latent systolic pressure of ``n_days`` days from ``start_day`` on (module docstring).

    ``ar_reference_step_ms`` is the sampling step at which ``params.ar_noise_phi`` holds, read
    by the caller through ``LiteraturePriorSource.reference_step_ms("ar_noise_phi")``.
    ``ar_state_mmhg`` continues a previous run (its ``ar_state_mmhg`` property); ``None``
    starts the AR noise from its stationary law. Consumes ``n_points`` standard normals from
    ``rng``. Raises ``LatentModelError`` for an invalid parameter, a step that does not divide
    the day, or a grid larger than ``MAX_GRID_POINTS``.
    """
    baseline = _finite("baseline_sbp_mmhg", params.baseline_sbp_mmhg)
    if baseline <= 0.0:
        raise LatentModelError(f"baseline_sbp_mmhg must be > 0, got {baseline}")
    amplitude = _non_negative(
        "circadian_amplitude_mmhg", params.circadian_amplitude_mmhg
    )
    sd = _non_negative("ar_noise_sd_mmhg", params.ar_noise_sd_mmhg)
    step = _int("latent_step_ms", latent_step_ms, minimum=1)
    days = _int("n_days", n_days, minimum=1)
    first_day = _int("start_day", start_day, minimum=0)
    peak = _peak_clock(circadian_peak_clock_ms)
    ref_step = _int("ar_reference_step_ms", ar_reference_step_ms, minimum=1)
    if not isinstance(rng, np.random.Generator):
        raise LatentModelError("rng must be a numpy.random.Generator (see rng.stream)")
    state = None if ar_state_mmhg is None else _finite("ar_state_mmhg", ar_state_mmhg)
    phi = rescale_ar1_phi(params.ar_noise_phi, ref_step, step)
    shock_sd = innovation_sd(sd, phi)
    points = _grid_points(step, days)
    if (first_day + days) * T_DAY_MS > _INT64_MAX:
        raise LatentModelError(
            "the time axis would leave the int64 range of milliseconds"
        )

    t_ms: npt.NDArray[np.int64] = (
        np.arange(points, dtype=np.int64) * step + first_day * T_DAY_MS
    )
    circ = circadian(t_ms, amplitude, peak)
    draws = rng.standard_normal(points).tolist()
    noise = np.empty(points, dtype=np.float64)
    if state is None:
        previous = sd * draws[0]  # the stationary law: no burn-in
        noise[0] = previous
        begin = 1
    else:
        previous = state
        begin = 0
    for k in range(begin, points):
        previous = phi * previous + shock_sd * draws[k]
        noise[k] = previous
    sbp = (baseline + circ) + noise
    for array in (t_ms, circ, noise, sbp):
        _read_only(array)
    return LatentPressure(
        t_ms=t_ms, circadian_mmhg=circ, ar_noise_mmhg=noise, sbp_mmhg=sbp
    )
