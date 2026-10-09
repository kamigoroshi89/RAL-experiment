"""The reorder buffer and the lateness rule (docs/formal/01 sections 4.2 and 4.3, 05 section 6.1).

Lateness is decided from the two clocks of an input alone (requirement R-late of 05 section 6.1): an
input with device time ``t_dev`` and receive time ``t_rx`` is late iff ``t_rx`` is after the watermark
``t_{k_up(t_dev)} + D`` of the step that first shows it, ``k_up(t) = ceil(t / T_s)`` (the ceiling
rule); an arrival exactly at the watermark is on time. The decision does not depend on when
``advance`` is called. The buffer releases accepted inputs in device-time order once their step is
finalised.

Order inside the buffer. Primary key the device time. Ties: an availability mark, then a sample
(a pressure sample with the device time of a dispense is the pre-dose value, modelling choice M5),
then an event; among events the kind (a measurement before a dispense: the usual order is measure
then dispense, M5), so that the order of the records of one step does not depend on the order of
arrival; among inputs of one kind the sequence number when present, else the receive time, else the
order of arrival. The buffer is bounded (``capacity`` inputs): ``push`` returns ``False``
when it is full and the caller reports the input; nothing is dropped silently.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from typing import Final

__all__ = ["BufferedInput", "ReorderBuffer", "is_late", "step_of", "watermark_ms"]

_KIND_RANK: Final = {"avail": 0, "sample": 1, "event": 2}


def step_of(t_ms: int, step_ms: int) -> int:
    """The step that first shows an input with device time ``t_ms``: the ceiling rule ``ceil(t / T_s)``."""
    return (t_ms + step_ms - 1) // step_ms


def watermark_ms(t_device_ms: int, step_ms: int, delay_ms: int) -> int:
    """The monitor time ``t_{k_up(t_dev)} + D`` at which the step of an input is finalised."""
    return step_of(t_device_ms, step_ms) * step_ms + delay_ms


def is_late(t_device_ms: int, t_rx_ms: int, step_ms: int, delay_ms: int) -> bool:
    """Whether an input arrived after its watermark; an arrival exactly at the watermark is on time."""
    return t_rx_ms > watermark_ms(t_device_ms, step_ms, delay_ms)


@dataclass(frozen=True, slots=True)
class BufferedInput:
    t_device_ms: int
    t_rx_ms: int
    kind: str  # "avail", "sample" or "event"
    item: object  # the object the caller pushed (returned unchanged in a report)
    seq: int | None
    data: object = None  # the validated payload that the monitor applies at release
    order: int = 0  # tie-break among events of one device time (the monitor passes the kind rank)


class ReorderBuffer:
    """A min-heap of accepted inputs keyed by device time; ``O(log b)`` per push and per release."""

    __slots__ = ("_arrival", "_capacity", "_heap")

    def __init__(self, capacity: int) -> None:
        self._capacity = capacity
        self._heap: list[tuple[int, int, int, int, int, int, BufferedInput]] = []
        self._arrival = 0

    def __len__(self) -> int:
        return len(self._heap)

    def push(self, entry: BufferedInput) -> bool:
        """Buffer ``entry``; ``False`` (and nothing buffered) when the buffer is full."""
        if len(self._heap) >= self._capacity:
            return False
        has_seq = entry.seq is not None
        secondary = entry.seq if entry.seq is not None else entry.t_rx_ms
        key = (
            entry.t_device_ms,
            _KIND_RANK[entry.kind],
            entry.order,
            0 if has_seq else 1,
            secondary,
            self._arrival,
            entry,
        )
        self._arrival += 1
        heapq.heappush(self._heap, key)
        return True

    def release(self, watermark_ms: int) -> list[BufferedInput]:
        """Remove and return the inputs with device time at most ``watermark_ms``, in order."""
        out: list[BufferedInput] = []
        heap = self._heap
        while heap and heap[0][0] <= watermark_ms:
            out.append(heapq.heappop(heap)[-1])
        return out
