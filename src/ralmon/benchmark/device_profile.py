"""Device profile of the generator: cuff resolution, driver diagnostics, dispenser interval (WS04-T18, ADR-074).

A benchmark is observed through devices. This module holds the declared configuration of those devices that the
fault models do not cover, and the three behaviours that follow from it:

Cuff resolution (``cuff_resolution_mmhg``, ``pulse_resolution_bpm``). A real display shows integers; the generator
draws floats. The readings ``bp`` and the ``hr_pulse`` that the cuff reports are rounded to a multiple of the
resolution at the device boundary, that is in the final observed stream, AFTER the injectors have run (so that a
silent bias is added, and a frozen value repeated, before the display rounds it: a frozen window stays exactly
identical). The default is 1 mmHg and 1 bpm (decision of gab, ADR-074 amendment 2: a property of this generator, not
the resolution of a real cuff, which is not in the repository). ``None`` means no rounding (the behaviour before
WS04-T18, a counterfactual). The latent day and the ground truth are never rounded. The value is the one that the run
gives the extractor as ``DeviceCapabilities.cuff_resolution``: the manifest records it (``settings.device_profile``).

Driver diagnostics (``DriverDiagnostics``; the two named profiles). ``without_diagnostics`` (the default) emits no
``diagnostics`` report. ``driver_with_diagnostics`` emits ``NODE_STATE`` reports whose payload ``diagnostics`` is
``ok`` or ``stale``, produced under the liveness contract of ``docs/models/evidence-channels.md`` ("Bridge node:
liveness contract for ``diagnostics = stale``"), for each device named by the profile:

* ``ok`` at the start of the day and at every driver period, for each device; ``stale`` replaces it while the
  device is stale; a report also marks each transition (the first millisecond beyond the lease, and the recovery);
* an ON-DEMAND device (``cuff``, ``dispenser``) is stale only with an OPEN SESSION that has sent no message for more
  than ``stale_lease_ms``; an idle one (no open session) is ``ok`` and never stale. The generator derives a session
  from the stream the device SENT (before the link stage): the session of a cuff reading opens when the measurement
  starts (the reading instant minus its inflation time) and closes when the reading arrives; that of a dispenser
  opening opens and closes at its instant. A message lost on the link leaves its session open until the link is
  reported active again or the device delivers another message; a refused or failed measurement sends nothing and
  opens no session. Nothing is derived from an injection record or the ground truth;
* a CONTINUOUS device (``ecg``, ``oximeter``) is stale while it has been silent for more than the lease.

``warn`` and ``error`` are not produced: they come from the status the device itself reports, and the fault model
attributes no fault to ``system.diagnostics_ok`` (fault-model OP-4). The lease and the driver period have NO
default: a profile with diagnostics built without them raises ``UnsetDriverParameterError``.

Dispenser interval (``dispenser_reports_interval``, default True). The dispenser reports the interval since its
previous opening in the payload of each ``DISPENSE``: see ``measurement.assign_dispense_intervals``.

Resource bounds: at most ``MAX_DRIVER_REPORTS_PER_DAY`` periodic reports per device and day. Every public function
raises ``DeviceProfileError`` for an invalid argument and nothing else.
"""

from __future__ import annotations

import math
import numbers
from bisect import bisect_right
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Any, Final

from ralmon.benchmark import vocab
from ralmon.benchmark.latent import T_DAY_MS
from ralmon.signals import Event, EventKind, Sample, SignalId

__all__ = [
    "ACTIVITY_MODES",
    "DEFAULT_CUFF_RESOLUTION_MMHG",
    "DEFAULT_DRIVER_DEVICES",
    "DEFAULT_PULSE_RESOLUTION_BPM",
    "DIAGNOSTICS_PROFILES",
    "MAX_DRIVER_REPORTS_PER_DAY",
    "MODE_CONTINUOUS",
    "MODE_ON_DEMAND",
    "PROFILE_WITHOUT_DIAGNOSTICS",
    "PROFILE_WITH_DIAGNOSTICS",
    "DeviceProfileError",
    "DriverDiagnostics",
    "GeneratorDeviceProfile",
    "MessageView",
    "Session",
    "UnsetDriverParameterError",
    "driver_inputs",
    "driver_reports",
    "message_view",
    "round_cuff_samples",
    "round_to_resolution",
    "stale_intervals",
]

PROFILE_WITH_DIAGNOSTICS: Final = "driver_with_diagnostics"
PROFILE_WITHOUT_DIAGNOSTICS: Final = "without_diagnostics"
DIAGNOSTICS_PROFILES: Final = (PROFILE_WITHOUT_DIAGNOSTICS, PROFILE_WITH_DIAGNOSTICS)

# The one new default of WS04-T18 (gab, ADR-074 amendment 2): the display resolution of the generator's cuff.
DEFAULT_CUFF_RESOLUTION_MMHG: Final = 1.0
DEFAULT_PULSE_RESOLUTION_BPM: Final = 1.0

# Activity mode of each BLE device (evidence-channels.md, liveness contract item 2): a device streams for as long as
# it is connected (continuous) or connects and acts only when used (on demand).
MODE_CONTINUOUS: Final = "continuous"
MODE_ON_DEMAND: Final = "on_demand"
_MODES: Final = (MODE_CONTINUOUS, MODE_ON_DEMAND)
ACTIVITY_MODES: Final[Mapping[str, str]] = MappingProxyType(
    {
        vocab.SOURCE_CUFF: MODE_ON_DEMAND,
        vocab.SOURCE_DISPENSER: MODE_ON_DEMAND,
        vocab.SOURCE_ECG: MODE_CONTINUOUS,
        vocab.SOURCE_OXIMETER: MODE_CONTINUOUS,
    }
)
# The devices whose driver the evidence fields read (the data scope of the templates: cuff and dispenser).
DEFAULT_DRIVER_DEVICES: Final = (vocab.SOURCE_CUFF, vocab.SOURCE_DISPENSER)

MAX_DRIVER_REPORTS_PER_DAY: Final[int] = (
    100_000  # algorithmic: periodic reports of one device in a day
)

_BP: Final = SignalId.BP.value
_PULSE: Final = SignalId.HR_PULSE.value
_INFLATION: Final = SignalId.INFLATION_MS.value
# Which signals and event kinds are the messages of a device (a Sample has no source field).
_DATA_SIGNALS: Final[Mapping[str, frozenset[str]]] = MappingProxyType(
    {
        vocab.SOURCE_CUFF: frozenset(
            {
                SignalId.BP.value,
                SignalId.INFLATION_MS.value,
                SignalId.CUFF_HEALTH.value,
                SignalId.HR_PULSE.value,
            }
        ),
        vocab.SOURCE_DISPENSER: frozenset({SignalId.AUTH.value}),
        vocab.SOURCE_ECG: frozenset({SignalId.HR_ECG.value}),
        vocab.SOURCE_OXIMETER: frozenset({SignalId.SPO2.value}),
    }
)
_DATA_EVENTS: Final[Mapping[str, frozenset[EventKind]]] = MappingProxyType(
    {
        vocab.SOURCE_CUFF: frozenset(
            {
                EventKind.MEASUREMENT,
                EventKind.MEASUREMENT_MISSED,
                EventKind.DEVICE_ERROR,
            }
        ),
        vocab.SOURCE_DISPENSER: frozenset({EventKind.DISPENSE}),
        vocab.SOURCE_ECG: frozenset(),
        vocab.SOURCE_OXIMETER: frozenset(),
    }
)


class DeviceProfileError(ValueError):
    """A device-profile argument is invalid."""


class UnsetDriverParameterError(DeviceProfileError):
    """The profile 'driver_with_diagnostics' was asked for without a value for its lease or its period.

    Both are device-profile parameters with NO default (rows ``driver_period_ms`` and ``driver_stale_lease_ms`` of
    ``generator_design.yaml``, ``awaiting_human_value``): the run fails instead of inventing one.
    """


def _is_integer(x: object) -> bool:
    return not isinstance(x, bool) and isinstance(x, numbers.Integral)


def _resolution(name: str, x: object) -> float | None:
    if x is None:
        return None
    if isinstance(x, bool) or not isinstance(x, numbers.Real):
        raise DeviceProfileError(f"{name} must be a positive finite number or None")
    value = float(x)
    if not math.isfinite(value) or value <= 0.0:
        raise DeviceProfileError(f"{name} must be a positive finite number or None")
    return value


# ---------------------------------------------------------------------------
# The profile
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DriverDiagnostics:
    """The parameters of the profile 'driver_with_diagnostics' (no default for the first two).

    ``period_ms``: the period of the driver's reports; ``stale_lease_ms``: the silence beyond which an expected
    publisher is stale. Both are integers of at least 1 ms and at most one day; a missing value raises
    ``UnsetDriverParameterError``. ``devices``: the nodes whose driver reports (default: the cuff and the dispenser).
    """

    period_ms: int
    stale_lease_ms: int
    devices: tuple[str, ...] = DEFAULT_DRIVER_DEVICES

    def __post_init__(self) -> None:
        unset = [
            f"driver_{name}"
            for name, value in (
                ("period_ms", self.period_ms),
                ("stale_lease_ms", self.stale_lease_ms),
            )
            if value is None
        ]
        if unset:
            raise UnsetDriverParameterError(
                f"the profile {PROFILE_WITH_DIAGNOSTICS!r} needs {' and '.join(unset)}, which have no default "
                "(awaiting_human_value in generator_design.yaml): a human supplies them"
            )
        for name, value in (
            ("period_ms", self.period_ms),
            ("stale_lease_ms", self.stale_lease_ms),
        ):
            if not _is_integer(value) or not 1 <= int(value) <= T_DAY_MS:
                raise DeviceProfileError(
                    f"{name} must be an integer number of ms in [1, {T_DAY_MS}]"
                )
            object.__setattr__(self, name, int(value))
        devices = (
            tuple(self.devices)
            if isinstance(self.devices, Iterable) and not isinstance(self.devices, str)
            else ()
        )
        if (
            not devices
            or len(set(devices)) != len(devices)
            or any(d not in ACTIVITY_MODES for d in devices)
        ):
            raise DeviceProfileError(
                f"devices must be a non-empty list of distinct nodes among {list(ACTIVITY_MODES)}"
            )
        if -(-T_DAY_MS // self.period_ms) > MAX_DRIVER_REPORTS_PER_DAY:
            raise DeviceProfileError(
                f"a period of {self.period_ms} ms gives more than {MAX_DRIVER_REPORTS_PER_DAY} reports a day"
            )
        object.__setattr__(self, "devices", devices)

    @property
    def activity_modes(self) -> dict[str, str]:
        return {d: ACTIVITY_MODES[d] for d in self.devices}

    def manifest_entry(self) -> dict[str, Any]:
        return {
            "period_ms": self.period_ms,
            "stale_lease_ms": self.stale_lease_ms,
            "devices": list(self.devices),
            "activity_modes": self.activity_modes,
        }


@dataclass(frozen=True, slots=True)
class GeneratorDeviceProfile:
    """The declared device profile of a run (module docstring).

    ``cuff_resolution_mmhg`` and ``pulse_resolution_bpm``: the display resolutions (default 1 and 1; ``None``: no
    rounding). ``dispenser_reports_interval``: the dispenser reports ``interval_since_previous_ms``. ``driver``:
    ``None`` is the profile 'without_diagnostics', a ``DriverDiagnostics`` the profile 'driver_with_diagnostics'.
    """

    cuff_resolution_mmhg: float | None = DEFAULT_CUFF_RESOLUTION_MMHG
    pulse_resolution_bpm: float | None = DEFAULT_PULSE_RESOLUTION_BPM
    dispenser_reports_interval: bool = True
    driver: DriverDiagnostics | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "cuff_resolution_mmhg",
            _resolution("cuff_resolution_mmhg", self.cuff_resolution_mmhg),
        )
        object.__setattr__(
            self,
            "pulse_resolution_bpm",
            _resolution("pulse_resolution_bpm", self.pulse_resolution_bpm),
        )
        if not isinstance(self.dispenser_reports_interval, bool):
            raise DeviceProfileError("dispenser_reports_interval must be a bool")
        if self.driver is not None and not isinstance(self.driver, DriverDiagnostics):
            raise DeviceProfileError("driver must be a DriverDiagnostics or None")

    @classmethod
    def with_diagnostics(
        cls,
        *,
        period_ms: int | None,
        stale_lease_ms: int | None,
        devices: Sequence[str] = DEFAULT_DRIVER_DEVICES,
        **kwargs: Any,
    ) -> GeneratorDeviceProfile:
        """The profile 'driver_with_diagnostics'; an unset period or lease raises ``UnsetDriverParameterError``."""
        driver = DriverDiagnostics(
            period_ms=period_ms,  # type: ignore[arg-type]
            stale_lease_ms=stale_lease_ms,  # type: ignore[arg-type]
            devices=tuple(devices),
        )
        return cls(driver=driver, **kwargs)

    @property
    def diagnostics_profile(self) -> str:
        return (
            PROFILE_WITHOUT_DIAGNOSTICS
            if self.driver is None
            else PROFILE_WITH_DIAGNOSTICS
        )

    def manifest_entry(self) -> dict[str, Any]:
        """The part of ``settings.device_profile`` that this profile owns (JSON-native)."""
        return {
            "cuff_resolution_mmhg": self.cuff_resolution_mmhg,
            "pulse_resolution_bpm": self.pulse_resolution_bpm,
            "dispenser_reports_interval": self.dispenser_reports_interval,
            "diagnostics_profile": self.diagnostics_profile,
            "driver": None if self.driver is None else self.driver.manifest_entry(),
        }


# ---------------------------------------------------------------------------
# Rounding at the device boundary
# ---------------------------------------------------------------------------


def round_to_resolution(value: float, resolution: float) -> float:
    """``value`` rounded to the nearest multiple of ``resolution`` (ties to even, as ``round``)."""
    return round(value / resolution) * resolution


def round_cuff_samples(
    samples: Iterable[Sample], profile: GeneratorDeviceProfile
) -> tuple[Sample, ...]:
    """The samples with the cuff readings (``bp`` and the cuff's ``hr_pulse``) at the profile's resolution.

    Only the value of those two signals changes; times, ``seq`` and ``quality`` and every other signal are kept.
    """
    cuff, pulse = profile.cuff_resolution_mmhg, profile.pulse_resolution_bpm
    out: list[Sample] = []
    for s in samples:
        if s.signal == _BP and cuff is not None:
            s = replace(s, value=round_to_resolution(s.value, cuff))
        elif s.signal == _PULSE and pulse is not None:
            s = replace(s, value=round_to_resolution(s.value, pulse))
        out.append(s)
    return tuple(out)


# ---------------------------------------------------------------------------
# Driver diagnostics
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Session:
    """A session of an on-demand device: open at ``open_ms``, closed at ``close_ms`` (``None``: still open)."""

    open_ms: int
    close_ms: int | None = None


def _merge(intervals: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for a, b in sorted(intervals):
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged


def stale_intervals(
    mode: str,
    stale_lease_ms: int,
    day_start_ms: int,
    day_end_ms: int,
    *,
    sessions: Sequence[Session] = (),
    message_times: Sequence[int] = (),
) -> list[tuple[int, int]]:
    """The half-open intervals ``[first stale ms, recovery)`` of a device inside the day, merged.

    A device is stale once it has been silent for MORE than the lease, so the first stale millisecond is
    ``silence start + lease + 1``. On demand: the silence starts when a session opens and ends when it closes (an
    idle device has no silence to report). Continuous: the silence is the gap between two messages, from the start
    of the day to the first message and from the last one to the end of the day.
    """
    if mode not in _MODES:
        raise DeviceProfileError(f"mode must be one of {_MODES}")
    found: list[tuple[int, int]] = []
    if mode == MODE_ON_DEMAND:
        for s in sessions:
            b = day_end_ms if s.close_ms is None else min(s.close_ms, day_end_ms)
            a = max(s.open_ms + stale_lease_ms + 1, day_start_ms)
            if a < b:
                found.append((a, b))
    else:
        times = sorted({t for t in message_times if day_start_ms <= t < day_end_ms})
        previous = day_start_ms
        for t in (*times, day_end_ms):
            if t - previous > stale_lease_ms:
                found.append((previous + stale_lease_ms + 1, t))
            previous = t
    return _merge(found)


def driver_reports(
    source: str,
    mode: str,
    *,
    period_ms: int,
    stale_lease_ms: int,
    day_start_ms: int,
    day_end_ms: int,
    sessions: Sequence[Session] = (),
    message_times: Sequence[int] = (),
) -> tuple[Event, ...]:
    """The ``NODE_STATE`` ``diagnostics`` reports of one device's driver for one day (module docstring).

    ``ok`` at ``day_start_ms`` and at every ``period_ms`` after it (strictly before ``day_end_ms``), ``stale`` at the
    periodic instants that fall inside a stale interval, and one report at the first stale millisecond and one at the
    recovery of each stale interval. ``state`` is ``active`` in every report (the driver is alive); ``t_rx_ms`` is
    ``t_device_ms`` (the driver is a ward-side node: no transport delay) and ``seq`` is ``None``.
    """
    if source not in ACTIVITY_MODES:
        raise DeviceProfileError(f"source must be one of {list(ACTIVITY_MODES)}")
    if not (_is_integer(period_ms) and 1 <= period_ms <= T_DAY_MS):
        raise DeviceProfileError(
            "period_ms must be an integer number of ms in [1, one day]"
        )
    if not (_is_integer(stale_lease_ms) and stale_lease_ms >= 1):
        raise DeviceProfileError("stale_lease_ms must be an integer of at least 1")
    if not (
        _is_integer(day_start_ms)
        and _is_integer(day_end_ms)
        and day_end_ms > day_start_ms
    ):
        raise DeviceProfileError("the day must be a non-empty integer interval")
    if -(-(day_end_ms - day_start_ms) // period_ms) > MAX_DRIVER_REPORTS_PER_DAY:
        raise DeviceProfileError("the period gives too many reports in a day")
    intervals = stale_intervals(
        mode, stale_lease_ms, day_start_ms, day_end_ms,
        sessions=sessions, message_times=message_times,
    )  # fmt: skip
    times = set(range(day_start_ms, day_end_ms, period_ms))
    for a, b in intervals:
        times.add(a)
        if b < day_end_ms:
            times.add(b)
    starts = [a for a, _ in intervals]

    def is_stale(t: int) -> bool:
        i = bisect_right(starts, t) - 1
        return i >= 0 and t < intervals[i][1]

    return tuple(
        Event(
            EventKind.NODE_STATE,
            t,
            t,
            source,
            {
                vocab.KEY_STATE: vocab.STATE_ACTIVE,
                vocab.KEY_DIAGNOSTICS: "stale" if is_stale(t) else "ok",
            },
            None,
        )
        for t in sorted(times)
    )


@dataclass(frozen=True, slots=True)
class MessageView:
    """The messages of one device in a stream: ``{instant: setup time}`` (ms before the message that its session opened).

    The setup time of a cuff message is its ``inflation_ms`` (the measurement starts that long before the reading);
    that of every other message is 0.
    """

    device: str
    setups: Mapping[int, int] = field(default_factory=dict)


def message_view(
    device: str, samples: Iterable[Sample], events: Iterable[Event]
) -> MessageView:
    """The messages that ``device`` has in a stream: its data samples and its data events, by instant."""
    if device not in ACTIVITY_MODES:
        raise DeviceProfileError(f"device must be one of {list(ACTIVITY_MODES)}")
    signals, kinds = _DATA_SIGNALS[device], _DATA_EVENTS[device]
    setups: dict[int, int] = {}
    for s in samples:
        if s.signal in signals:
            t = s.t_device_ms
            setups.setdefault(t, 0)
            if device == vocab.SOURCE_CUFF and s.signal == _INFLATION and s.value > 0:
                setups[t] = max(setups[t], round(s.value))
    for e in events:
        if e.source == device and e.kind in kinds:
            setups.setdefault(e.t_device_ms, 0)
    return MessageView(device, setups)


def driver_inputs(
    sent: MessageView, delivered: MessageView, events: Iterable[Event]
) -> tuple[list[Session], list[int]]:
    """The sessions and the delivered message instants of a device, from what it sent and what the link delivered.

    ``events`` are the events of the stream after the link stage: a ``NODE_STATE`` ``active`` report of the device
    (the gateway reporting the link restored, or the device back from a deactivation) restores a lost session.
    """
    device = sent.device
    if delivered.device != device:
        raise DeviceProfileError("the two views must be of the same device")
    arrivals = sorted(delivered.setups)
    restores = sorted(
        e.t_device_ms
        for e in events
        if e.kind is EventKind.NODE_STATE
        and e.source == device
        and e.payload.get(vocab.KEY_STATE) == vocab.STATE_ACTIVE
        and vocab.KEY_DIAGNOSTICS not in e.payload
    )
    sessions: list[Session] = []
    for t, setup in sorted(sent.setups.items()):
        opened = t - setup
        if t in delivered.setups:
            sessions.append(Session(opened, t))
            continue
        closes = []
        i = bisect_right(arrivals, t)
        if i < len(arrivals):
            closes.append(arrivals[i])
        j = bisect_right(restores, t - 1)
        if j < len(restores):
            closes.append(restores[j])
        sessions.append(Session(opened, min(closes) if closes else None))
    return sessions, arrivals
