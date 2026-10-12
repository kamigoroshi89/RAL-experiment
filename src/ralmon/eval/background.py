"""Footprints of the injections and the patient-time WITHOUT injections (ADR-071 (b), WS08-T08).

ADR-071 (b): false alarms are measured on the windows without injections, "outside every injection window and outside its
causal consequences", because no day of the benchmark is clean (the natural events are truth, a noise alarm is a false
alarm). This module is the geometry of that rule; the counts are in ``ralmon.eval.metrics``. Every function is pure and
reads no clock, no environment and no file. It reads TRUTH (the injection log of the truth sidecar): it is evaluation code,
never a detector input.

The footprint of an injection record (``injection_log`` entry of ``docs/benchmark/builder.md``):

* C2 and C3: the window ``[onset_ms, end_ms]`` of the record (a point or per-tick fault: the instant). The window is read
  on the RECEIVE axis (``axis = "t_rx"``), which is the axis of every detection. For a replay this is the only valid
  reading: the replayed copies keep an old ``t_device`` (the previous day) and arrive in the window (``docs/benchmark/
  evidence/nonadditivity.md``, section 3: the footprint of a replay is measured on ``t_rx``).
* C1: the same window plus a finite physiological TAIL, a parameter of the experiment (``run_options.background.
  c1_footprint_tail_ms``). A pharmacokinetic effect decays without ever reaching zero (non-response and double take: 9.3
  mmHg on day 0, 1.8e-5 mmHg on day 7, nonadditivity.md), so some finite horizon must be stated; it is not a clinical value
  and the repository has no basis for one, so the value is an ``awaiting_human_value`` of the configuration.
* Every record: the spans of the ground-truth events that the record explains (``truth_indices`` of its own day and
  ``explains_in_later_days``), because an event of a later day (the day-end COUNT after a double take) is a causal
  consequence of the record.
* Unrealised records (``realised`` false: the injector changed nothing) have no footprint.

A margin (``margin_ms``) widens every footprint on both sides: a detection within the matching tolerance of an injection
belongs to the injection, whether it was matched, was a duplicate or fell just outside.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from ralmon.benchmark import GroundTruthEvent

__all__ = [
    "DAY_MS",
    "Footprint",
    "PatientBackground",
    "patient_footprints",
    "record_footprint",
    "subtype_key",
]

DAY_MS: Final[int] = (
    86_400_000  # algorithmic: 24 h, the day of the continuing axis (ADR-053 (h))
)
_CLASSES: Final[tuple[str, ...]] = ("C1", "C2", "C3")


@dataclass(frozen=True, slots=True)
class Footprint:
    """A closed interval ``[start_ms, end_ms]`` of the patient's continuing axis on which an injection acts.

    ``axis`` is always ``"t_rx"`` (module docstring)."""

    subtype: str
    cls: str
    start_ms: int
    end_ms: int
    axis: str = "t_rx"

    def __post_init__(self) -> None:
        if self.end_ms < self.start_ms:
            raise ValueError(
                f"footprint of {self.subtype!r} ends ({self.end_ms}) before it starts ({self.start_ms})"
            )


def subtype_key(footprint: Footprint) -> str:
    """The key of an injected subtype in the outputs: ``<class>/<subtype>`` (the key of ``event_counts``)."""
    return f"{footprint.cls}/{footprint.subtype}"


def _need_int(value: object, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{what} must be an integer, got {value!r}")
    return value


def _span(
    events: Mapping[int, Sequence[GroundTruthEvent]], day: int, index: int
) -> tuple[int, int]:
    try:
        event = events[day][index]
    except (KeyError, IndexError) as exc:
        raise ValueError(
            f"the injection log names event {index} of day {day}, which the truth does not have"
        ) from exc
    return event.onset_ms, event.end_ms if event.end_ms is not None else event.onset_ms


def record_footprint(
    entry: Mapping[str, Any],
    *,
    day_index: int,
    truth_by_day: Mapping[int, Sequence[GroundTruthEvent]],
    c1_tail_ms: int,
) -> tuple[Footprint, ...]:
    """The footprint of one ``injection_log`` entry of day ``day_index`` (module docstring): the window (plus the tail for a
    C1 record) and the spans of the events that the record explains; ``()`` for a record that changed nothing."""
    if not entry.get("realised", True):
        return ()
    cls, subtype = entry["cls"], entry["subtype"]
    if cls not in _CLASSES:
        raise ValueError(
            f"the class of an injection record must be C1, C2 or C3, got {cls!r}"
        )
    c1_tail_ms = _need_int(c1_tail_ms, "c1_tail_ms")
    if c1_tail_ms < 0:
        raise ValueError("c1_tail_ms must not be negative")
    onset = _need_int(entry["onset_ms"], "onset_ms")
    raw_end = entry.get("end_ms")
    end = onset if raw_end is None else _need_int(raw_end, "end_ms")
    if cls == "C1":
        end += c1_tail_ms
    spans = [(onset, end)]
    for index in entry.get("truth_indices", ()):
        spans.append(_span(truth_by_day, day_index, _need_int(index, "truth_indices")))
    for item in entry.get("explains_in_later_days", ()):
        spans.append(
            _span(
                truth_by_day,
                _need_int(item["day_index"], "day_index"),
                _need_int(item["truth_index"], "truth_index"),
            )
        )
    return tuple(Footprint(subtype, cls, a, b) for a, b in spans)


def patient_footprints(
    logs_by_day: Mapping[int, Sequence[Mapping[str, Any]]],
    truth_by_day: Mapping[int, Sequence[GroundTruthEvent]],
    *,
    c1_tail_ms: int,
) -> tuple[Footprint, ...]:
    """The footprints of all the records of a patient (``logs_by_day``: day index to the ``injection_log`` of that day)."""
    out: list[Footprint] = []
    for day in sorted(logs_by_day):
        for entry in logs_by_day[day]:
            out.extend(
                record_footprint(
                    entry,
                    day_index=day,
                    truth_by_day=truth_by_day,
                    c1_tail_ms=c1_tail_ms,
                )
            )
    return tuple(out)


def _merge(intervals: Sequence[tuple[int, int]]) -> tuple[tuple[int, int], ...]:
    merged: list[tuple[int, int]] = []
    for a, b in sorted(intervals):
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return tuple(merged)


class PatientBackground:
    """The injected time of one patient on a record of ``n_days`` scored days, and so the time WITHOUT injections.

    Every footprint is widened by ``margin_ms`` on both sides and clipped to ``[0, n_days * day_ms]`` (the scored axis).
    ``outside(t)`` says that an instant is in no footprint; ``exposure_ms()`` is, per day, the time outside every footprint;
    ``window_ms(key)`` and ``inside(t, key)`` give the time and the instants inside the footprints of one injected
    subtype (``subtype_key``).
    """

    def __init__(
        self,
        footprints: Sequence[Footprint],
        n_days: int,
        *,
        margin_ms: int = 0,
        day_ms: int = DAY_MS,
    ) -> None:
        n_days = _need_int(n_days, "n_days")
        margin_ms = _need_int(margin_ms, "margin_ms")
        if n_days < 0 or margin_ms < 0 or day_ms < 1:
            raise ValueError(
                "n_days and margin_ms must not be negative and day_ms must be positive"
            )
        self.footprints = tuple(footprints)
        self.n_days = n_days
        self.margin_ms = margin_ms
        self.day_ms = day_ms
        axis_end = n_days * day_ms
        by_key: dict[str, list[tuple[int, int]]] = {}
        for fp in self.footprints:
            lo, hi = (
                max(0, fp.start_ms - margin_ms),
                min(axis_end, fp.end_ms + margin_ms),
            )
            if lo <= hi:
                by_key.setdefault(subtype_key(fp), []).append((lo, hi))
        self._all = _merge([x for xs in by_key.values() for x in xs])
        self._by_key = {k: _merge(v) for k, v in by_key.items()}
        self._key_starts = {k: [a for a, _ in v] for k, v in self._by_key.items()}
        self._starts = [a for a, _ in self._all]
        self._covered = self._per_day(self._all)

    def _per_day(self, merged: Sequence[tuple[int, int]]) -> tuple[int, ...]:
        covered = [0] * self.n_days
        for a, b in merged:
            for d in range(
                a // self.day_ms, min(self.n_days - 1, b // self.day_ms) + 1
            ):
                lo, hi = max(a, d * self.day_ms), min(b, (d + 1) * self.day_ms)
                if hi > lo:
                    covered[d] += hi - lo
        return tuple(covered)

    @property
    def keys(self) -> tuple[str, ...]:
        """The injected subtypes with a footprint on the scored axis, sorted."""
        return tuple(sorted(self._by_key))

    def outside(self, t_ms: int) -> bool:
        """True when ``t_ms`` is in no footprint (the closed intervals of the module docstring)."""
        i = bisect_right(self._starts, t_ms) - 1
        return not (i >= 0 and t_ms <= self._all[i][1])

    def inside(self, t_ms: int, key: str) -> bool:
        """True when ``t_ms`` is in a footprint of the subtype ``key``."""
        merged = self._by_key.get(key, ())
        i = bisect_right(self._key_starts.get(key, []), t_ms) - 1
        return i >= 0 and t_ms <= merged[i][1]

    def exposure_ms(self) -> tuple[int, ...]:
        """Per scored day, the time (ms) outside every footprint."""
        return tuple(self.day_ms - c for c in self._covered)

    def window_ms(self, key: str) -> tuple[int, ...]:
        """Per scored day, the time (ms) inside the footprints of the subtype ``key`` (zeros for an unknown key)."""
        return self._per_day(self._by_key.get(key, ()))
