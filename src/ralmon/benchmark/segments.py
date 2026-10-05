"""Segment library: clean heart-rate, SpO2 and ECG-noise segments from public data (WS04-T06).

The benchmark takes heart rate and SpO2 from real, clean segments and the noise of the ECG
path from real electrode and motion noise (analisi section 5.1). Raw PhysioNet or VitalDB
records are never read here and never committed (``data/raw/`` is gitignored): a human with
the data runs the extraction of ``docs/benchmark/public-sources.md`` and obtains a **segment
root** directory with an ``index.json`` and one JSON file per segment. This module defines
that format and reads it.

Index (``index.json``)::

    {"schema_version": "0.1.0", "segments": [ <entry>, ... ]}

An entry has exactly the keys ``segment_id`` (unique), ``dataset``, ``record_id``, ``kind``
(``hr_clean``, ``spo2_clean`` or ``hr_error_ecg_noise``), ``sample_period_ms`` (integer
milliseconds), ``n_samples``, ``unit``, ``path`` (relative to the segment root), ``sha256``
(64 lowercase hex digits of the segment file) and ``licence``. The provenance fields
(``dataset``, ``record_id``, ``licence``, ``sha256``) are mandatory: an entry without one is
refused. All entries of one kind share one ``sample_period_ms``.

Segment file: ``{"values": [numbers], "quality": [numbers in [0, 1]]}``; ``quality`` is
optional, same length as ``values``, and ``len(values)`` equals ``n_samples``. Values are
finite JSON numbers (``NaN`` and ``Infinity`` are refused).

Safety. Every file is untrusted: the index and each segment file have a size limit
(``MAX_INDEX_BYTES``, ``MAX_SEGMENT_FILE_BYTES``), the number of entries
(``MAX_SEGMENTS``) and of samples (``MAX_SEGMENT_SAMPLES``, ``MAX_TOTAL_SAMPLES``) are
bounded, a path must be relative, without ``..``, ``.``, empty or backslash components, and
its resolved location (symbolic links followed) must lie under the segment root. The sha256
of every file is verified when the library is built and again when the file is read for a
draw. Every failure is a ``SegmentIndexError``; a request that cannot be served is a
``SegmentUnavailableError``; nothing else escapes (no ``OSError``, ``JSONDecodeError``,
``OverflowError``, ``KeyError``).

Draw. ``SegmentLibrary.draw(kind, n_samples, rng)`` returns ``n_samples`` consecutive
samples. It prefers one segment that is long enough, chosen uniformly among those, starting
at a uniformly drawn offset; when no segment is long enough, whole segments are chosen
uniformly with replacement and joined from their start, the last one cut, and every join is
counted (``join_count``). The generator always consumes the same number of draws for the
first choice (two), so a branch of the selection never shifts the stream of a later use.

``SegmentLibrary.from_memory`` builds a library from inline arrays for **tests only**
(fixture values, no files, dataset ``inline-fixture``); the benchmark builder uses files.
"""

from __future__ import annotations

import hashlib
import json
import math
import numbers
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Final, TypeGuard

import numpy as np

__all__ = [
    "KIND_HR_CLEAN",
    "KIND_HR_ERROR_ECG_NOISE",
    "KIND_SPO2_CLEAN",
    "MAX_DRAW_SAMPLES",
    "MAX_INDEX_BYTES",
    "MAX_SAMPLE_PERIOD_MS",
    "MAX_SEGMENTS",
    "MAX_SEGMENT_FILE_BYTES",
    "MAX_SEGMENT_SAMPLES",
    "MAX_TOTAL_SAMPLES",
    "SCHEMA_VERSION",
    "SEGMENT_KINDS",
    "InlineSegment",
    "SegmentDraw",
    "SegmentEntry",
    "SegmentError",
    "SegmentIndex",
    "SegmentIndexError",
    "SegmentLibrary",
    "SegmentUnavailableError",
]

SCHEMA_VERSION: Final = "0.1.0"
KIND_HR_CLEAN: Final = "hr_clean"
KIND_SPO2_CLEAN: Final = "spo2_clean"
KIND_HR_ERROR_ECG_NOISE: Final = "hr_error_ecg_noise"
SEGMENT_KINDS: Final = (KIND_HR_CLEAN, KIND_SPO2_CLEAN, KIND_HR_ERROR_ECG_NOISE)

# Resource guards (a human-produced file is untrusted input).
_MIB: Final = 1024 * 1024  # algorithmic: one mebibyte
MAX_INDEX_BYTES: Final[int] = 4 * _MIB  # algorithmic: size limit of index.json
MAX_SEGMENT_FILE_BYTES: Final[int] = 8 * _MIB  # algorithmic: segment file size
MAX_SEGMENTS: Final[int] = 10_000  # algorithmic: number of index entries
MAX_SEGMENT_SAMPLES: Final[int] = 500_000  # algorithmic: samples of one segment
MAX_TOTAL_SAMPLES: Final[int] = 10_000_000  # algorithmic: samples of the whole index
MAX_DRAW_SAMPLES: Final[int] = MAX_SEGMENT_SAMPLES
MAX_SAMPLE_PERIOD_MS: Final[int] = (
    86_400_000  # algorithmic: a sample spans at most a day
)
_MAX_TEXT: Final = 256  # algorithmic: longest identifier or label
_CACHE_SEGMENTS: Final = 8  # algorithmic: parsed segment files kept in memory
_DRAW_RANGE: Final = 1 << 32  # algorithmic: range of the integer draws of a selection
_SHA256_RE: Final = re.compile(r"[0-9a-f]{64}")
_ENTRY_KEYS: Final = (
    "segment_id",
    "dataset",
    "record_id",
    "kind",
    "sample_period_ms",
    "n_samples",
    "unit",
    "path",
    "sha256",
    "licence",
)
_NO_SOURCE: Final = "none"


class SegmentError(ValueError):
    """Base class of the errors of this module."""


class SegmentIndexError(SegmentError):
    """The index, a segment file, a path or the library root is invalid or untrusted."""


class SegmentUnavailableError(SegmentError):
    """A request cannot be served: unknown kind, no segment of the kind, bad count or rng."""


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _is_integer(x: object) -> TypeGuard[numbers.Integral]:
    return not isinstance(x, (bool, np.bool_)) and isinstance(x, numbers.Integral)


def _text(name: str, x: object) -> str:
    if not isinstance(x, str) or not x.strip() or len(x) > _MAX_TEXT:
        raise SegmentIndexError(
            f"{name} must be a non-empty string of at most {_MAX_TEXT} characters"
        )
    return x


def _positive_int(name: str, x: object, limit: int) -> int:
    if not _is_integer(x):
        raise SegmentIndexError(f"{name} must be an integer")
    value = int(x)
    if not 1 <= value <= limit:
        raise SegmentIndexError(f"{name} must lie in [1, {limit}]")
    return value


def _relative_path(path: object) -> str:
    """A portable relative path: no absolute form, no ``..``, ``.``, empty or backslash part."""
    text = _text("path", path)
    if "\0" in text or "\\" in text or text.startswith("/") or text.endswith("/"):
        raise SegmentIndexError(f"path {text!r} is not a plain relative path")
    parts = text.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise SegmentIndexError(f"path {text!r} has an empty, '.' or '..' component")
    if (
        re.match(r"^[A-Za-z]:", parts[0]) is not None
        or PurePosixPath(text).is_absolute()
    ):
        raise SegmentIndexError(f"path {text!r} is absolute")
    return text


def _finite(name: str, x: object) -> float:
    if isinstance(x, (bool, np.bool_)) or not isinstance(x, numbers.Real):
        raise SegmentIndexError(f"{name} must be a finite number")
    try:
        value = float(x)
    except OverflowError as exc:
        raise SegmentIndexError(f"{name} is too large for a float") from exc
    if not math.isfinite(value):
        raise SegmentIndexError(f"{name} must be a finite number")
    return value


def _reject_constant(token: str) -> Any:
    raise SegmentIndexError(f"JSON constant {token} is not allowed")


def _parse_json(data: bytes, what: str) -> Any:
    try:
        return json.loads(data.decode("utf-8"), parse_constant=_reject_constant)
    except SegmentIndexError:
        raise
    except (
        ValueError,
        RecursionError,
    ) as exc:  # JSONDecodeError and UnicodeDecodeError
        raise SegmentIndexError(
            f"{what} is not valid JSON: {type(exc).__name__}"
        ) from exc


def _read_bounded(path: Path, limit: int, what: str) -> bytes:
    """Bytes of a regular file of at most ``limit`` bytes; any OS-level problem is refused."""
    try:
        regular = path.is_file()
        size = path.stat().st_size if regular else 0
        if regular and size <= limit:
            with path.open("rb") as handle:
                data = handle.read(limit + 1)
        else:
            data = b""
    except OSError as exc:
        raise SegmentIndexError(f"{what} cannot be read: {type(exc).__name__}") from exc
    except ValueError as exc:  # embedded NUL in a path
        raise SegmentIndexError(f"{what} is not a valid path") from exc
    if not regular:
        raise SegmentIndexError(f"{what} is not a regular file")
    if size > limit or len(data) > limit:
        raise SegmentIndexError(f"{what} is larger than {limit} bytes")
    return data


def _as_path(name: str, value: object) -> Path:
    if not isinstance(value, (str, os.PathLike)) or isinstance(value, bytes):
        raise SegmentIndexError(f"{name} must be a path, got {type(value).__name__}")
    text = os.fspath(value)
    if not isinstance(text, str) or "\0" in text or not text:
        raise SegmentIndexError(f"{name} is not a valid path")
    return Path(text)


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SegmentEntry:
    """One validated index entry (see the module docstring for the fields)."""

    segment_id: str
    dataset: str
    record_id: str
    kind: str
    sample_period_ms: int
    n_samples: int
    unit: str
    path: str
    sha256: str
    licence: str

    def __post_init__(self) -> None:
        _text("segment_id", self.segment_id)
        _text("dataset", self.dataset)
        _text("record_id", self.record_id)
        _text("unit", self.unit)
        _text("licence", self.licence)
        if not isinstance(self.kind, str) or self.kind not in SEGMENT_KINDS:
            raise SegmentIndexError(f"kind must be one of {SEGMENT_KINDS}")
        object.__setattr__(
            self,
            "sample_period_ms",
            _positive_int(
                "sample_period_ms", self.sample_period_ms, MAX_SAMPLE_PERIOD_MS
            ),
        )
        object.__setattr__(
            self,
            "n_samples",
            _positive_int("n_samples", self.n_samples, MAX_SEGMENT_SAMPLES),
        )
        object.__setattr__(self, "path", _relative_path(self.path))
        if (
            not isinstance(self.sha256, str)
            or _SHA256_RE.fullmatch(self.sha256) is None
        ):
            raise SegmentIndexError("sha256 must be 64 lowercase hexadecimal digits")

    def to_json(self) -> dict[str, str | int]:
        return {key: getattr(self, key) for key in _ENTRY_KEYS}


@dataclass(frozen=True, slots=True)
class SegmentIndex:
    """The validated entries of an index: unique ids, one sample period per kind."""

    entries: tuple[SegmentEntry, ...]

    def __post_init__(self) -> None:
        if isinstance(self.entries, (str, bytes)) or not isinstance(
            self.entries, Sequence
        ):
            raise SegmentIndexError("entries must be a sequence of SegmentEntry")
        entries = tuple(self.entries)
        if len(entries) > MAX_SEGMENTS:
            raise SegmentIndexError(f"an index holds at most {MAX_SEGMENTS} entries")
        if not all(isinstance(e, SegmentEntry) for e in entries):
            raise SegmentIndexError("every entry must be a SegmentEntry")
        ids = [e.segment_id for e in entries]
        if len(set(ids)) != len(ids):
            raise SegmentIndexError("segment_id values must be unique")
        periods: dict[str, int] = {}
        total = 0
        for e in entries:
            if periods.setdefault(e.kind, e.sample_period_ms) != e.sample_period_ms:
                raise SegmentIndexError(
                    f"segments of kind {e.kind} have different sample_period_ms"
                )
            total += e.n_samples
        if total > MAX_TOTAL_SAMPLES:
            raise SegmentIndexError(
                f"an index holds at most {MAX_TOTAL_SAMPLES} samples"
            )
        object.__setattr__(self, "entries", entries)

    @classmethod
    def from_mapping(cls, document: object) -> SegmentIndex:
        """Validate a parsed ``index.json``."""
        if not isinstance(document, Mapping):
            raise SegmentIndexError("the index must be a JSON object")
        if set(document) != {"schema_version", "segments"}:
            raise SegmentIndexError(
                "the index needs exactly schema_version and segments"
            )
        if document["schema_version"] != SCHEMA_VERSION:
            raise SegmentIndexError(f"schema_version must be {SCHEMA_VERSION!r}")
        raw = document["segments"]
        if not isinstance(raw, list):
            raise SegmentIndexError("segments must be a list")
        if len(raw) > MAX_SEGMENTS:
            raise SegmentIndexError(f"an index holds at most {MAX_SEGMENTS} entries")
        entries = []
        for position, item in enumerate(raw):
            if not isinstance(item, Mapping) or set(item) != set(_ENTRY_KEYS):
                raise SegmentIndexError(
                    f"entry {position} must be an object with exactly the keys {list(_ENTRY_KEYS)}"
                )
            entries.append(SegmentEntry(**{key: item[key] for key in _ENTRY_KEYS}))
        return cls(tuple(entries))

    @classmethod
    def from_file(cls, path: object) -> SegmentIndex:
        """Read and validate an ``index.json`` (bounded size, JSON constants refused)."""
        target = _as_path("index path", path)
        data = _read_bounded(target, MAX_INDEX_BYTES, "the index file")
        return cls.from_mapping(_parse_json(data, "the index file"))

    def digest(self) -> str:
        """sha256 of the canonical JSON of the entries (recorded in the manifest)."""
        body = json.dumps(
            [e.to_json() for e in self.entries], sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(body.encode("utf-8")).hexdigest()

    def kinds(self) -> frozenset[str]:
        return frozenset(e.kind for e in self.entries)


# ---------------------------------------------------------------------------
# Library
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class InlineSegment:
    """A fixture segment for ``SegmentLibrary.from_memory`` (tests only)."""

    segment_id: str
    kind: str
    values: Sequence[float]
    sample_period_ms: int
    unit: str
    quality: Sequence[float] | None = None


@dataclass(frozen=True, slots=True)
class SegmentDraw:
    """The result of a draw: ids of the segments used, values, optional quality, joins."""

    kind: str
    segment_ids: tuple[str, ...]
    values: tuple[float, ...]
    quality: tuple[float, ...] | None
    join_count: int
    sample_period_ms: int
    unit: str


@dataclass(frozen=True, slots=True)
class _Loaded:
    values: tuple[float, ...]
    quality: tuple[float, ...] | None


def _file_bytes(values: Sequence[float], quality: Sequence[float] | None) -> bytes:
    body: dict[str, list[float]] = {"values": list(values)}
    if quality is not None:
        body["quality"] = list(quality)
    return json.dumps(body, sort_keys=True).encode("utf-8")


def _numbers(name: str, raw: object, expected: int | None) -> tuple[float, ...]:
    if not isinstance(raw, list):
        raise SegmentIndexError(f"{name} must be a list of numbers")
    if expected is not None and len(raw) != expected:
        raise SegmentIndexError(
            f"{name} has {len(raw)} samples, the index says {expected}"
        )
    return tuple(_finite(f"{name}[{i}]", v) for i, v in enumerate(raw))


def _parse_segment(data: bytes, entry: SegmentEntry) -> _Loaded:
    document = _parse_json(data, f"segment {entry.segment_id}")
    if not isinstance(document, dict) or not {"values"} <= set(document) <= {
        "values",
        "quality",
    }:
        raise SegmentIndexError(
            f"segment {entry.segment_id}: the file needs 'values' and may have 'quality'"
        )
    values = _numbers("values", document["values"], entry.n_samples)
    quality = None
    if "quality" in document:
        quality = _numbers("quality", document["quality"], entry.n_samples)
        if any(not 0.0 <= q <= 1.0 for q in quality):
            raise SegmentIndexError(
                f"segment {entry.segment_id}: quality must lie in [0, 1]"
            )
    return _Loaded(values, quality)


class SegmentLibrary:
    """Segments under a root directory, verified, with deterministic draws.

    The constructor checks that the root is a directory, that every entry's path stays under
    it (symbolic links followed), that each file is a regular file within the size limit and
    that its sha256 equals the index. Parsed files are cached (at most ``_CACHE_SEGMENTS``).
    """

    def __init__(self, root: object, index: object) -> None:
        if not isinstance(index, SegmentIndex):
            raise SegmentIndexError("index must be a SegmentIndex")
        self._root: Path | None = None
        self._memory: dict[str, _Loaded] = {}
        self._cache: dict[str, _Loaded] = {}
        self._index = index
        resolved_root = self._check_root(root)
        self._root = resolved_root
        for entry in index.entries:
            data = _read_bounded(
                self._resolve(entry),
                MAX_SEGMENT_FILE_BYTES,
                f"segment {entry.segment_id}",
            )
            if hashlib.sha256(data).hexdigest() != entry.sha256:
                raise SegmentIndexError(
                    f"segment {entry.segment_id}: sha256 differs from the index"
                )

    @staticmethod
    def _check_root(root: object) -> Path:
        path = _as_path("root", root)
        try:
            resolved = path.resolve(strict=True)
            is_directory = resolved.is_dir()
        except (OSError, RuntimeError, ValueError) as exc:
            raise SegmentIndexError(
                f"the segment root cannot be used: {type(exc).__name__}"
            ) from exc
        if not is_directory:
            raise SegmentIndexError("the segment root is not a directory")
        return resolved

    def _resolve(self, entry: SegmentEntry) -> Path:
        assert self._root is not None
        try:
            target = (self._root / entry.path).resolve(strict=False)
            inside = target.is_relative_to(self._root)
        except (OSError, RuntimeError, ValueError) as exc:
            raise SegmentIndexError(
                f"segment {entry.segment_id}: path cannot be resolved ({type(exc).__name__})"
            ) from exc
        if not inside:
            raise SegmentIndexError(
                f"segment {entry.segment_id}: path leaves the segment root"
            )
        return target

    @classmethod
    def from_memory(cls, segments: Sequence[InlineSegment]) -> SegmentLibrary:
        """A library of inline fixture segments (tests only; no file is read)."""
        if isinstance(segments, (str, bytes)) or not isinstance(segments, Sequence):
            raise SegmentIndexError("segments must be a sequence of InlineSegment")
        entries = []
        memory: dict[str, _Loaded] = {}
        for item in segments:
            if not isinstance(item, InlineSegment):
                raise SegmentIndexError("every segment must be an InlineSegment")
            n = (
                len(item.values)
                if isinstance(item.values, (Sequence, np.ndarray))
                else 0
            )
            if not 1 <= n <= MAX_SEGMENT_SAMPLES:
                raise SegmentIndexError(
                    f"inline segment {item.segment_id!r} has no valid values"
                )
            values = tuple(_finite("values", v) for v in item.values)
            quality = None
            if item.quality is not None:
                quality = tuple(_finite("quality", q) for q in item.quality)
                if len(quality) != len(values) or any(
                    not 0.0 <= q <= 1.0 for q in quality
                ):
                    raise SegmentIndexError(
                        "quality must match values and lie in [0, 1]"
                    )
            sha = hashlib.sha256(_file_bytes(values, quality)).hexdigest()
            entry = SegmentEntry(
                segment_id=item.segment_id,
                dataset="inline-fixture",
                record_id=item.segment_id,
                kind=item.kind,
                sample_period_ms=item.sample_period_ms,
                n_samples=len(values),
                unit=item.unit,
                path=f"inline/{item.segment_id}.json"
                if isinstance(item.segment_id, str)
                else "inline/invalid.json",
                sha256=sha,
                licence="fixture-only",
            )
            entries.append(entry)
            memory[entry.segment_id] = _Loaded(values, quality)
        library = object.__new__(cls)
        library._root = None
        library._index = SegmentIndex(tuple(entries))
        library._memory = memory
        library._cache = {}
        return library

    # -- queries ------------------------------------------------------------------

    @property
    def index(self) -> SegmentIndex:
        return self._index

    @property
    def root(self) -> Path | None:
        return self._root

    @property
    def descriptor(self) -> str:
        """``none`` for an empty library, else ``index:`` plus the digest of the entries."""
        if not self._index.entries:
            return _NO_SOURCE
        return "index:" + self._index.digest()

    def has_kind(self, kind: object) -> bool:
        return isinstance(kind, str) and kind in self._index.kinds()

    def sample_period_ms(self, kind: object) -> int:
        """The sample period shared by the segments of ``kind``."""
        return self._select(kind)[0].sample_period_ms

    def _select(self, kind: object) -> tuple[SegmentEntry, ...]:
        if not isinstance(kind, str) or kind not in SEGMENT_KINDS:
            raise SegmentUnavailableError(
                f"kind must be one of {SEGMENT_KINDS}, got {kind!r}"
            )
        chosen = tuple(
            sorted(
                (e for e in self._index.entries if e.kind == kind),
                key=lambda e: e.segment_id,
            )
        )
        if not chosen:
            raise SegmentUnavailableError(
                f"the library has no segment of kind {kind!r}"
            )
        return chosen

    # -- loading and drawing ------------------------------------------------------

    def _load(self, entry: SegmentEntry) -> _Loaded:
        if entry.segment_id in self._memory:
            return self._memory[entry.segment_id]
        cached = self._cache.get(entry.segment_id)
        if cached is not None:
            return cached
        data = _read_bounded(
            self._resolve(entry), MAX_SEGMENT_FILE_BYTES, f"segment {entry.segment_id}"
        )
        if hashlib.sha256(data).hexdigest() != entry.sha256:
            raise SegmentIndexError(
                f"segment {entry.segment_id}: sha256 differs from the index"
            )
        loaded = _parse_segment(data, entry)
        if len(self._cache) >= _CACHE_SEGMENTS:
            self._cache.pop(next(iter(self._cache)))
        self._cache[entry.segment_id] = loaded
        return loaded

    def draw(self, kind: object, n_samples: object, rng: object) -> SegmentDraw:
        """``n_samples`` consecutive samples of ``kind`` (module docstring, section Draw)."""
        if not _is_integer(n_samples):
            raise SegmentUnavailableError("n_samples must be an integer")
        count = int(n_samples)
        if not 1 <= count <= MAX_DRAW_SAMPLES:
            raise SegmentUnavailableError(
                f"n_samples must lie in [1, {MAX_DRAW_SAMPLES}]"
            )
        if not isinstance(rng, np.random.Generator):
            raise SegmentUnavailableError(
                "rng must be a numpy.random.Generator (see rng.stream)"
            )
        candidates = self._select(kind)
        first, offset_draw = (int(x) for x in rng.integers(0, _DRAW_RANGE, size=2))
        long_enough = [e for e in candidates if e.n_samples >= count]
        period, unit = candidates[0].sample_period_ms, candidates[0].unit
        if long_enough:
            entry = long_enough[first % len(long_enough)]
            loaded = self._load(entry)
            start = offset_draw % (entry.n_samples - count + 1)
            quality = (
                None
                if loaded.quality is None
                else loaded.quality[start : start + count]
            )
            return SegmentDraw(
                str(kind),
                (entry.segment_id,),
                loaded.values[start : start + count],
                quality,
                0,
                period,
                unit,
            )
        ids: list[str] = []
        values: list[float] = []
        qualities: list[float] = []
        has_quality = True
        pick = first
        while len(values) < count:
            entry = candidates[pick % len(candidates)]
            loaded = self._load(entry)
            take = min(entry.n_samples, count - len(values))
            ids.append(entry.segment_id)
            values.extend(loaded.values[:take])
            if loaded.quality is None:
                has_quality = False
            else:
                qualities.extend(loaded.quality[:take])
            pick = int(rng.integers(0, _DRAW_RANGE))
        return SegmentDraw(
            str(kind),
            tuple(ids),
            tuple(values),
            tuple(qualities) if has_quality else None,
            len(ids) - 1,
            period,
            unit,
        )
