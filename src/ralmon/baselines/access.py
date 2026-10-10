"""Access guards and read logs of the baseline harness (WS06-T01; analisi section 10 objection 1).

Two things must be true by construction and auditable by logs: a baseline never sees the latent trace or the
ground truth when it runs, and it knows no more of the clinical specification than the proposed method.

Fitting. ``BaselineBase.fit`` wraps every ``BenchmarkDay`` it receives in a ``GuardedDay`` and hands only
those to ``_fit``. The wrapper offers three properties and enforces the contract of ``#detector``
(ground truth from training days only):

==============  ===========================  ===========================================
property        training day                 calibration day
==============  ===========================  ===========================================
``observed``    allowed                      allowed
``ground_truth``  allowed                    ``LeakageError`` always
``latent``      allowed                      ``LeakageError`` unless ``AccessPolicy.calib_latent``
==============  ===========================  ===========================================

Every allowed read is appended to an ``AccessLog`` (split, patient, day, field); a read that is allowed only
by the ``calib_latent`` exception is marked ``by_exception``; a refused read is kept apart in
``AccessLog.denied`` so that "no latent read on a calibration day" can be asserted on ``records``. The
``calib_latent`` exception exists only so that a baseline can be given the same calibration target as the
proposed method if WS05-T06 fixes the latent trace as that target (WS06-T05, T07).

Running. ``run`` receives an ``ObservedDay``, which has no latent or ground-truth member. What the baseline
reads of the clinical specification is logged by two wrappers that record names into a ``ReadLog``:
``AuditedRegistry`` (``get(name)`` logs ``name``, ``bounds(signal)`` logs ``bounds:<signal>``) and
``logged_plan`` (a copy of the care plan whose ``TemplateInstance.param_values`` log every lookup per
instance key). Only ``param_values`` is wrapped: ``CarePlan.schedule``, the anchors and the template ids are
not logged, because every method receives them and the knowledge audit (WS06-T07) treats the schedule as
shared. A failed lookup of a registry name is logged too (the baseline asked for it); a failed lookup of a
plan parameter is not (nothing was read).

This is the only module of the baseline package that names the latent and ground-truth types.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import Enum

from ralmon.benchmark import BenchmarkDay, GroundTruthEvent, LatentDay, ObservedDay
from ralmon.spec import CarePlan, ParameterRegistry, PhysioBounds, RegistryEntry

__all__ = [
    "AccessLog",
    "AccessPolicy",
    "AccessRecord",
    "AuditedRegistry",
    "GuardedDay",
    "LeakageError",
    "LoggedMapping",
    "ReadLog",
    "Split",
    "logged_plan",
]


class LeakageError(Exception):
    """A detector tried to read what it must not see (latent trace, ground truth, a non-observed day)."""


class Split(str, Enum):
    TRAIN = "train"
    CALIB = "calib"


@dataclass(frozen=True, slots=True)
class AccessPolicy:
    """What a guarded calibration day may show beyond the observed trace.

    ``calib_latent=False`` (the default): nothing. ``True``: the latent trace of a calibration day may be
    read, and the log marks the read. Ground truth is never readable on a calibration day.
    """

    calib_latent: bool = False


@dataclass(frozen=True, slots=True)
class AccessRecord:
    split: Split
    patient_id: str
    day_index: int
    field: str  # "observed", "ground_truth" or "latent"
    by_exception: bool = False  # allowed only by AccessPolicy.calib_latent


class AccessLog:
    """The reads of guarded days: allowed ones in ``records``, refused attempts in ``denied``."""

    __slots__ = ("_denied", "_records")

    def __init__(self) -> None:
        self._records: list[AccessRecord] = []
        self._denied: list[AccessRecord] = []

    @property
    def records(self) -> tuple[AccessRecord, ...]:
        return tuple(self._records)

    @property
    def denied(self) -> tuple[AccessRecord, ...]:
        return tuple(self._denied)

    def record(self, entry: AccessRecord) -> None:
        self._records.append(entry)

    def record_denied(self, entry: AccessRecord) -> None:
        self._denied.append(entry)

    def reads(
        self, *, field: str | None = None, split: Split | None = None
    ) -> tuple[AccessRecord, ...]:
        """The allowed reads, optionally of one field and/or one split."""
        return tuple(
            r
            for r in self._records
            if (field is None or r.field == field)
            and (split is None or r.split == split)
        )

    def fields(self, split: Split | None = None) -> frozenset[str]:
        """The names of the fields read (of one split, or of all)."""
        return frozenset(r.field for r in self.reads(split=split))

    def clear(self) -> None:
        self._records.clear()
        self._denied.clear()

    def __len__(self) -> int:
        return len(self._records)


class GuardedDay:
    """A benchmark day seen through the access rules of the module docstring.

    Only the properties below and the identifying metadata (``split``, ``patient_id``, ``day_index``) are
    public; the wrapped day is private.
    """

    __slots__ = ("_day", "_log", "_policy", "_split")

    def __init__(
        self,
        day: BenchmarkDay,
        split: Split,
        log: AccessLog,
        policy: AccessPolicy | None = None,
    ) -> None:
        self._day = day
        self._split = split
        self._log = log
        self._policy = AccessPolicy() if policy is None else policy

    @property
    def split(self) -> Split:
        return self._split

    @property
    def patient_id(self) -> str:
        return self._day.observed.patient_id

    @property
    def day_index(self) -> int:
        return self._day.observed.day_index

    def _entry(self, name: str, by_exception: bool = False) -> AccessRecord:
        return AccessRecord(
            self._split, self.patient_id, self.day_index, name, by_exception
        )

    def _deny(self, name: str, why: str) -> LeakageError:
        self._log.record_denied(self._entry(name))
        return LeakageError(
            f"{name} of a {self._split.value} day is not readable: {why}"
        )

    @property
    def observed(self) -> ObservedDay:
        self._log.record(self._entry("observed"))
        return self._day.observed

    @property
    def ground_truth(self) -> Sequence[GroundTruthEvent]:
        if self._split is not Split.TRAIN:
            raise self._deny(
                "ground_truth", "ground truth is for training days only (#detector)"
            )
        self._log.record(self._entry("ground_truth"))
        return self._day.ground_truth

    @property
    def latent(self) -> LatentDay:
        exception = self._split is Split.CALIB
        if exception and not self._policy.calib_latent:
            raise self._deny(
                "latent",
                "the default AccessPolicy denies latent traces on calibration days",
            )
        self._log.record(self._entry("latent", by_exception=exception))
        return self._day.latent

    def __repr__(self) -> str:
        return (
            f"GuardedDay(split={self._split.value!r}, patient_id={self.patient_id!r}, "
            f"day_index={self.day_index})"
        )


class ReadLog:
    """Names read from the registry and parameter names read per plan instance."""

    __slots__ = ("_params", "_registry")

    def __init__(self) -> None:
        self._registry: set[str] = set()
        self._params: dict[str, set[str]] = {}

    def record_registry(self, name: str) -> None:
        self._registry.add(name)

    def record_param(self, instance_key: str, name: str) -> None:
        self._params.setdefault(instance_key, set()).add(name)

    @property
    def registry_reads(self) -> frozenset[str]:
        return frozenset(self._registry)

    @property
    def param_reads(self) -> dict[str, frozenset[str]]:
        return {key: frozenset(names) for key, names in self._params.items()}

    def all_names(self) -> frozenset[str]:
        """Every registry name and every plan parameter name read, without the instance keys."""
        names = set(self._registry)
        for read in self._params.values():
            names |= read
        return frozenset(names)

    def clear(self) -> None:
        self._registry.clear()
        self._params.clear()


class AuditedRegistry:
    """A ``ParameterRegistry`` that logs the names it is asked for and delegates to another registry."""

    def __init__(self, inner: ParameterRegistry, log: ReadLog | None = None) -> None:
        self._inner = inner
        self.log = ReadLog() if log is None else log

    def get(self, name: str) -> RegistryEntry:
        self.log.record_registry(name)
        return self._inner.get(name)

    def bounds(self, signal: str) -> PhysioBounds:
        self.log.record_registry(f"bounds:{signal}")
        return self._inner.bounds(signal)

    def version(self) -> str:
        return self._inner.version()


class LoggedMapping(Mapping[str, float]):
    """A read-only view of a parameter mapping that logs each successful ``__getitem__``.

    ``items()``, ``values()``, ``get()`` and ``in`` go through ``__getitem__`` and so log what they touch;
    ``len()`` and iteration over the keys do not.
    """

    __slots__ = ("_inner", "_key", "_log")

    def __init__(
        self, inner: Mapping[str, float], log: ReadLog, instance_key: str
    ) -> None:
        self._inner = inner
        self._log = log
        self._key = instance_key

    def __getitem__(self, name: str) -> float:
        value = self._inner[name]
        self._log.record_param(self._key, name)
        return value

    def __iter__(self) -> Iterator[str]:
        return iter(self._inner)

    def __len__(self) -> int:
        return len(self._inner)

    def __repr__(self) -> str:
        return (
            f"LoggedMapping(instance_key={self._key!r}, names={sorted(self._inner)!r})"
        )


def logged_plan(plan: CarePlan, log: ReadLog) -> CarePlan:
    """A copy of ``plan`` whose instances log every parameter read; no other field changes."""
    return replace(
        plan,
        instances=tuple(
            replace(
                instance,
                param_values=LoggedMapping(
                    instance.param_values, log, instance.instance_key
                ),
            )
            for instance in plan.instances
        ),
    )
