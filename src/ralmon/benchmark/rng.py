"""Named random streams of the benchmark generator (WS04-T03).

Every step of the generator draws from its own stream, identified by the key
``(seed, patient_index, day_index or None, purpose, sub_index)``. A stream is a
``numpy.random.Generator`` built from ``numpy.random.SeedSequence`` with

* ``entropy`` = the root seed;
* ``spawn_key`` = ``(patient_index, day_code, purpose, sub_index)``, where ``day_code`` is
  ``0`` for ``None`` (a patient-level stream) and ``day_index + 1`` otherwise, so that
  ``None`` is distinct from every day index.

Properties, each tested in ``tests/benchmark/test_latent.py``:

* the same key gives the same numbers, in any call order and in any process (the derivation
  uses integers only: no ``hash()``, no string, no platform-dependent value);
* different keys give independent streams (``SeedSequence`` mixes the whole key);
* creating, using or dropping a stream never changes the numbers of another stream: a stream
  is a pure function of its key, with no shared state, so adding an injection later cannot
  shift the draws of the latent trace, the adherence model or the measurement process;
* no use of the global ``numpy`` or ``random`` state, and no wall clock.

``SeedSequence`` turns each ``spawn_key`` entry into 32-bit words and concatenates them, so a
value of 2**32 or more could alias two different keys. Every entry is therefore limited to
``[0, 2**32)`` and the seed to ``[0, 2**64)``; a key outside its range is refused with
``StreamKeyError`` rather than reduced. The integer ids of ``StreamPurpose`` are frozen: a
change would change every benchmark.
"""

from __future__ import annotations

import numbers
from enum import IntEnum
from typing import Final

import numpy as np

__all__ = [
    "StreamKeyError",
    "StreamPurpose",
    "stream",
    "stream_seed_sequence",
]

_WORD_BITS: Final = 32  # algorithmic: SeedSequence mixes 32-bit words
_SEED_BITS: Final = 64  # algorithmic: width of the root seed written in the manifest
_WORD_LIMIT: Final = 1 << _WORD_BITS
_SEED_LIMIT: Final = 1 << _SEED_BITS
_NO_DAY_CODE: Final = 0  # the reserved day code of a stream that belongs to no day


class StreamKeyError(ValueError):
    """A stream key is not an integer of the admissible range, or the purpose is wrong."""


class StreamPurpose(IntEnum):
    """What a stream is used for. The integer values are frozen (never reuse or renumber)."""

    PATIENT = 1  # algorithmic: frozen stream id
    LATENT_AR = 2  # algorithmic: frozen stream id
    ADHERENCE = 3  # algorithmic: frozen stream id
    MEASUREMENT = 4  # algorithmic: frozen stream id
    SEGMENTS = 5  # algorithmic: frozen stream id
    JITTER = 6  # algorithmic: frozen stream id
    INJECTION_PLAN = 7  # algorithmic: frozen stream id
    INJECTION_C1 = 8  # algorithmic: frozen stream id
    INJECTION_C2 = 9  # algorithmic: frozen stream id
    INJECTION_C3 = 10  # algorithmic: frozen stream id
    SPLIT = 11  # algorithmic: frozen stream id
    CONFOUNDER = 12  # algorithmic: frozen stream id


def _integer(name: str, value: object, limit: int) -> int:
    """``value`` as a Python int in ``[0, limit)``; bools and non-integers are refused."""
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, numbers.Integral):
        raise StreamKeyError(f"{name} must be an integer, got {value!r}")
    number = int(value)
    if not 0 <= number < limit:
        raise StreamKeyError(f"{name} must lie in [0, {limit}), got {number}")
    return number


def stream_seed_sequence(
    seed: int,
    patient_index: int,
    day_index: int | None,
    purpose: StreamPurpose,
    sub_index: int = 0,
) -> np.random.SeedSequence:
    """The ``SeedSequence`` of a stream key (exposed so the derivation can be pinned)."""
    root = _integer("seed", seed, _SEED_LIMIT)
    patient = _integer("patient_index", patient_index, _WORD_LIMIT)
    if day_index is None:
        day_code = _NO_DAY_CODE
    else:
        day_code = _integer("day_index", day_index, _WORD_LIMIT - 1) + 1
    if not isinstance(purpose, StreamPurpose):
        raise StreamKeyError(f"purpose must be a StreamPurpose member, got {purpose!r}")
    sub = _integer("sub_index", sub_index, _WORD_LIMIT)
    return np.random.SeedSequence(
        entropy=root, spawn_key=(patient, day_code, int(purpose), sub)
    )


def stream(
    seed: int,
    patient_index: int,
    day_index: int | None,
    purpose: StreamPurpose,
    sub_index: int = 0,
) -> np.random.Generator:
    """A fresh, independent generator for the key; the same key always gives the same numbers.

    ``day_index`` is ``None`` for a stream of the patient (not of one day). ``sub_index``
    separates several streams of one purpose (for example one per dose or per injection).
    Integral numpy integers are accepted; booleans, floats and strings are refused.
    """
    return np.random.default_rng(
        stream_seed_sequence(seed, patient_index, day_index, purpose, sub_index)
    )
