"""Deliberate confounders: matched pairs of C1, C2 and C3 mechanisms (WS04-T09).

Analisi section 5.1 item 4 asks for confounders on purpose: cases in which the attribution layer
must abstain or use the witness. A pair has two members, A and B, that share everything but the
labelled mechanism (the paired design): the same patient, latent baseline, schedule, seed, cuff
noise draws and natural adherence draws; only the mechanism differs.

Groups (``GROUPS``; the matrix rows are those of analisi section 4.5):

``double_take_vs_bounce`` (rows 6 and 7)
    A: C1 ``double_take`` (the patient opens the dispenser twice, a forced slot); B: C2
    ``dispenser_bounce`` (the sensor reports an extra opening, the patient took one dose).
    Separated by the dispense interval (a sub-second bounce against the double-take gap), by the
    content change of the second dispense (1 against 0, only if the dispenser senses its content,
    gap G-1 of ``evidence-channels.md``) and by the witness (the second INTAKE, only if a robot is
    co-located).
``nonresponse_vs_falsified_dispense`` (rows 2 and 9)
    A: C1 ``drug_nonresponse`` (scale 0, the patient took the dose and it did nothing); B: C3
    ``dispense_forgery`` (the patient took nothing, an attacker forged the dispense; the informed
    level adds a ``presence_spoof`` with a spoofed intake). The latent days differ: a dose against
    none. Separated by the witness (naive attacker: no INTAKE), by the sequence number of the forged
    dispense (a naive forger leaves a repeat or a gap) and by the gateway verification (a device
    that authenticates). The informed attacker without authentication gives the same observed
    streams as the real non-response, with or without the robot (threat model, TM-OP-5).
``refusal_vs_robot_missed`` (added by this plan from R3-W4 of ``docs/source/review.md``, not one of
    the two groups named in analisi section 5.1)
    A: C1 ``measurement_refusal`` (the patient declines, robot task outcome ``declined``); B: C2
    ``manipulation_failure`` at the same tick (the robot fails the step, outcome ``failed``). Both
    lack the measurement. Separated by the outcome of the robot task, nothing else.

Variants. A ``Variant`` fixes which discriminating channels are **withheld** (the capability is
not in the deployment): ``content_change`` (the dispenser does not sense its content), ``witness``
(no robot is co-located: no INTAKE event and no presence sample; with ``robot_task_outcome``, the
robot channel of ablation A4), ``robot_task_outcome`` (the robot reports no task outcome) and
``verification`` (no device authenticates). The other knobs are the gap of the bounce (``nominal``
or the double-take gap) and the attacker level. The committed grid is the section ``confounders``
of ``configs/benchmark/injections.yaml`` (design choices awaiting confirmation, H3); nothing here
reads it except ``load_confounder_design``.

A variant without a robot (``witness`` withheld) is a deployment with no robot in the room: for the
groups 1 and 2 the injectors read the stream without its robot visits, so a forged dispense reads the
witness as None and its record carries no ``witness.*`` evidence path, and its ``expected_undetectable``
tag agrees with the flag computed below. Group 3 injects its fault at a robot visit, so its
``robot_absent`` variant withholds what the robot reports, not the robot. The visits stay in the
generator-side ``stream`` (they are the base shared by the pair).

``indistinguishable_by_construction``. It is computed, not asserted: ``compare_observed`` compares
the OBSERVED days of the two members, field by field, over the declared discriminating fields
(``DISCRIMINATORS``) minus the withheld ones, plus everything else that the observed day holds
(``other``); the pair is indistinguishable by construction when no field differs. The latent
days are never read: this module compares what a monitor would see. Presence is a level held over
the robot visit (``docs/models/evidence-channels.md``): an extra 1.0 sample inside a visit adds no
information and is not a difference; a sample outside every visit is. The pressure samples are
ignored for the double-take pair, where the physiological response differs by construction (two
doses against one: reported as ``pressure_response_differs``, not hidden). Each record of both
members is tagged with ``variant_id`` and ``indistinguishable_by_construction`` (in its details and
in the log entry).

Ground truth. The C2 and C3 members of a pair are injected events and become ground-truth events
through ``injection.ground_truth_events`` (with the group); the C1 members never do: their truth is
computed by the labeller on the latent trace (WS04-T10). The latent values never reach an observed
day.

Resource bounds: at most ``MAX_VARIANTS`` variants in a design file; every public function raises
``ConfounderError`` (a subclass of ``InjectionError``) or another ``InjectionError`` and nothing else.
"""

from __future__ import annotations

import dataclasses
import numbers
import os
from collections.abc import Hashable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, TypeGuard, TypeVar

import numpy as np

from ralmon.benchmark import vocab
from ralmon.benchmark.adherence import AdherenceState
from ralmon.benchmark.device_profile import GeneratorDeviceProfile
from ralmon.benchmark.inject_c1 import c1_spec, observe_refusals
from ralmon.benchmark.injection import (
    InjectionContext,
    InjectionDesignError,
    InjectionError,
    InjectionRecord,
    InjectionSpec,
    apply_observation_injections,
    finalize_observed,
    ground_truth_events,
    injection_log,
    load_design_mapping,
)
from ralmon.benchmark.latent import T_DAY_MS
from ralmon.benchmark.latent_day import (
    AssemblyConfig,
    ForcedSlot,
    LatentResult,
    assemble_latent_days,
)
from ralmon.benchmark.measurement import (
    ArrivalJitterModel,
    MeasurementDesign,
    ObservedStream,
    RobotVisit,
    build_observed_base,
)
from ralmon.benchmark.pkpd import ResponseModel
from ralmon.benchmark.priors import SOURCE_TYPES, DeviceErrorModel, PatientParams
from ralmon.benchmark.schedule import Schedule
from ralmon.benchmark.segments import SegmentLibrary
from ralmon.benchmark.trace import GroundTruthEvent, InjectedClass, ObservedDay
from ralmon.signals import Event, EventKind, Sample

__all__ = [
    "DISCRIMINATORS",
    "GROUPS",
    "GROUP_DOUBLE_TAKE_VS_BOUNCE",
    "GROUP_NONRESPONSE_VS_FORGERY",
    "GROUP_REFUSAL_VS_ROBOT_MISSED",
    "MAX_VARIANTS",
    "WITHHOLDABLE",
    "ConfounderError",
    "PairBase",
    "PairEvaluation",
    "RealisedScenario",
    "Scenario",
    "Variant",
    "build_confounder_pair",
    "compare_observed",
    "confounder_log",
    "evaluate_pair",
    "load_confounder_design",
    "realise_scenario",
]

GROUP_DOUBLE_TAKE_VS_BOUNCE: Final = "double_take_vs_bounce"
GROUP_NONRESPONSE_VS_FORGERY: Final = "nonresponse_vs_falsified_dispense"
GROUP_REFUSAL_VS_ROBOT_MISSED: Final = "refusal_vs_robot_missed"  # added from R3-W4
GROUPS: Final = (
    GROUP_DOUBLE_TAKE_VS_BOUNCE,
    GROUP_NONRESPONSE_VS_FORGERY,
    GROUP_REFUSAL_VS_ROBOT_MISSED,
)

FIELD_CONTENT: Final = "content_change"
FIELD_WITNESS: Final = (
    "witness"  # INTAKE events and presence samples (embodied witness channel)
)
FIELD_OUTCOME: Final = "robot_task_outcome"
FIELD_INTERVAL: Final = "dispense_interval"
FIELD_SEQ: Final = "dispense_seq"
FIELD_VERIFICATION: Final = "verification"  # failed gateway verifications
FIELD_OTHER: Final = "other"  # everything else the observed day holds
DISCRIMINATORS: Final = (
    FIELD_CONTENT,
    FIELD_WITNESS,
    FIELD_OUTCOME,
    FIELD_INTERVAL,
    FIELD_SEQ,
    FIELD_VERIFICATION,
)
WITHHOLDABLE: Final = (FIELD_CONTENT, FIELD_WITNESS, FIELD_OUTCOME, FIELD_VERIFICATION)

GAP_NOMINAL: Final = "nominal"
GAP_DOUBLE_TAKE: Final = "double_take_gap"
_GAPS: Final = (GAP_NOMINAL, GAP_DOUBLE_TAKE)
_ATTACKERS: Final = ("naive", "informed")
COMPLETE_NONRESPONSE_SCALE: Final = (
    0.0  # by definition: the whole drug effect of the intake is removed
)
DISPENSER_DEVICE: Final = vocab.SOURCE_DISPENSER

_SEED_LIMIT: Final = 1 << 64  # algorithmic: the root seed of rng.stream is below 2**64
_WORD_LIMIT: Final = 1 << 32  # algorithmic: a stream key entry is below 2**32
MAX_VARIANTS: Final[int] = 1_000  # algorithmic: variants of a design file
_MAX_TEXT: Final = 256  # algorithmic: longest identifier or label
_MAX_PROSE: Final = 2_000  # algorithmic: longest rationale or source reference
_MAX_WALK: Final = 100_000  # algorithmic: nodes walked in a design section
_MAX_ITEMS: Final = (
    256  # algorithmic: entries of a short list (withheld channels, devices, specs)
)
_MEMBER_KEYS: Final = ("class", "subtype")
_VARIANT_KEYS: Final = frozenset(
    {
        "bounce_gap",
        "attacker",
        "withheld",
        "expected_indistinguishable",
        "source_type",
        "source_ref",
        "rationale",
    }
)
_GROUP_KEYS: Final = frozenset({"members", "matrix_rows", "added_by", "variants"})


class ConfounderError(InjectionError):
    """A variant, a pair base, a scenario or a design file of the confounder pairs is invalid."""


@dataclass(frozen=True, slots=True)
class _GroupInfo:
    member_a: tuple[InjectedClass, str]
    member_b: tuple[InjectedClass, str]
    # the latent pressure of the members may differ by construction (two doses against one, or a dose
    # whose drug still occupies the saturation term of a later dose against no dose)
    pressure_differs: bool


_GROUP_INFO: Final[Mapping[str, _GroupInfo]] = {
    GROUP_DOUBLE_TAKE_VS_BOUNCE: _GroupInfo(
        (InjectedClass.C1, "double_take"), (InjectedClass.C2, "dispenser_bounce"), True
    ),
    GROUP_NONRESPONSE_VS_FORGERY: _GroupInfo(
        (InjectedClass.C1, "drug_nonresponse"),
        (InjectedClass.C3, "dispense_forgery"),
        True,
    ),
    GROUP_REFUSAL_VS_ROBOT_MISSED: _GroupInfo(
        (InjectedClass.C1, "measurement_refusal"),
        (InjectedClass.C2, "manipulation_failure"),
        False,
    ),
}


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _is_integer(x: object) -> TypeGuard[numbers.Integral]:
    return not isinstance(x, (bool, np.bool_)) and isinstance(x, numbers.Integral)


def _int(name: str, x: object, lo: int, hi: int) -> int:
    if not _is_integer(x):
        raise ConfounderError(f"{name} must be an integer")
    try:
        value = int(x)
    except Exception as exc:  # a number type whose conversion misbehaves
        raise ConfounderError(f"{name} is not an integer") from exc
    if not lo <= value <= hi:
        raise ConfounderError(f"{name} must lie in [{lo}, {hi}]")
    return value


_T = TypeVar("_T")


def _plain(x: _T) -> _T:
    """A ``str`` subclass copied to an exact ``str`` (anything else is returned as it is).

    A subclass may override its hash, equality, truth value, length or repr and raise from them
    (review F5); the copy is what the validation reads and what is stored, so none of those is ever
    called.
    """
    return str.__str__(x) if isinstance(x, str) else x  # type: ignore[return-value]


def _text(name: str, x: object) -> str:
    if not isinstance(x, str):
        raise ConfounderError(
            f"{name} must be a non-empty string of at most {_MAX_TEXT} characters"
        )
    plain = str.__str__(x)
    if not plain.strip() or len(plain) > _MAX_TEXT:
        raise ConfounderError(
            f"{name} must be a non-empty string of at most {_MAX_TEXT} characters"
        )
    return plain


def _prose(name: str, x: object) -> str:
    if not isinstance(x, str):
        raise ConfounderError(
            f"{name} must be a non-empty string of at most {_MAX_PROSE} characters"
        )
    plain = str.__str__(x)
    if not plain.strip() or len(plain) > _MAX_PROSE:
        raise ConfounderError(
            f"{name} must be a non-empty string of at most {_MAX_PROSE} characters"
        )
    return plain


def _bool(name: str, x: object) -> bool:
    if not isinstance(x, bool):
        raise ConfounderError(f"{name} must be a bool")
    return x


def _choice(name: str, x: object, allowed: Sequence[str]) -> str:
    """``x`` as an exact ``str`` that is one of ``allowed`` (a plain copy: see ``_plain``)."""
    if not isinstance(x, str):
        raise ConfounderError(f"{name} must be one of {tuple(allowed)}")
    plain = str.__str__(x)
    if plain not in allowed:
        raise ConfounderError(f"{name} must be one of {tuple(allowed)}")
    return plain


def _optional_choice(name: str, x: object, allowed: Sequence[str]) -> str | None:
    return None if x is None else _choice(name, x, allowed)


def _unreadable(what: str, exc: Exception) -> ConfounderError:
    """The named error for an argument or a foreign object that misbehaves when it is read."""
    return ConfounderError(f"{what} cannot be read: {type(exc).__name__}")


def _sequence(name: str, items: object, limit: int) -> tuple[Any, ...]:
    """A list or tuple of at most ``limit`` items (never a string, a generator or a mapping)."""
    if isinstance(items, (str, bytes)) or not isinstance(items, (list, tuple)):
        raise ConfounderError(f"{name} must be a list or a tuple")
    try:
        if len(items) > limit:
            raise ConfounderError(f"{name} has more than {limit} entries")
        return tuple(items)
    except ConfounderError:
        raise
    except Exception as exc:  # a list or tuple subclass whose methods misbehave
        raise _unreadable(name, exc) from exc


def _group(group: object) -> str:
    return _choice("group", group, GROUPS)


# ---------------------------------------------------------------------------
# Variants
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Variant:
    """One cell of the variant grid of a group (see the module docstring).

    ``withheld`` lists the discriminating channels that the deployment of the variant does not
    have (a subset of ``WITHHOLDABLE``; ``witness`` needs ``robot_task_outcome`` too: a robot that
    is not co-located reports no task). ``bounce_gap`` (group 1) is ``nominal`` or
    ``double_take_gap``; ``attacker`` (group 2) is ``naive`` or ``informed``; group 3 has neither.
    ``expected_indistinguishable`` is the design intent, checked against the computation by the
    tests; ``source_type``, ``source_ref`` and ``rationale`` are the provenance of the variant
    (an agent-proposed design choice, confirmed by H3).
    """

    group: str
    variant_id: str
    withheld: tuple[str, ...] = ()
    bounce_gap: str | None = None
    attacker: str | None = None
    expected_indistinguishable: bool = False
    source_type: str = "design_choice"
    source_ref: str = ""
    rationale: str = ""

    def __post_init__(self) -> None:
        group = _group(self.group)
        object.__setattr__(self, "group", group)
        object.__setattr__(self, "variant_id", _text("variant_id", self.variant_id))
        withheld = tuple(
            _choice("a withheld channel", item, WITHHOLDABLE)
            for item in _sequence("withheld", self.withheld, _MAX_ITEMS)
        )
        if len(set(withheld)) != len(withheld):
            raise ConfounderError("withheld lists a channel twice")
        if FIELD_WITNESS in withheld and FIELD_OUTCOME not in withheld:
            raise ConfounderError(
                "a robot that is not co-located reports no task: withhold witness and "
                "robot_task_outcome together"
            )
        object.__setattr__(self, "withheld", withheld)
        gap = _optional_choice("bounce_gap", self.bounce_gap, _GAPS)
        attacker = _optional_choice("attacker", self.attacker, _ATTACKERS)
        if group == GROUP_DOUBLE_TAKE_VS_BOUNCE:
            if gap is None or attacker is not None:
                raise ConfounderError(
                    f"group 1 takes bounce_gap in {_GAPS} and no attacker"
                )
        elif group == GROUP_NONRESPONSE_VS_FORGERY:
            if attacker is None or gap is not None:
                raise ConfounderError(
                    f"group 2 takes attacker in {_ATTACKERS} and no bounce_gap"
                )
        elif gap is not None or attacker is not None:
            raise ConfounderError("group 3 has no bounce_gap and no attacker")
        object.__setattr__(self, "bounce_gap", gap)
        object.__setattr__(self, "attacker", attacker)
        _bool("expected_indistinguishable", self.expected_indistinguishable)
        object.__setattr__(
            self, "source_type", _choice("source_type", self.source_type, SOURCE_TYPES)
        )
        object.__setattr__(self, "source_ref", _prose("source_ref", self.source_ref))
        object.__setattr__(self, "rationale", _prose("rationale", self.rationale))

    @property
    def content_sensing(self) -> bool:
        """The dispenser senses its content: a knob of the double-take pair only (group 1)."""
        return (
            self.group == GROUP_DOUBLE_TAKE_VS_BOUNCE
            and FIELD_CONTENT not in self.withheld
        )

    @property
    def robot_present(self) -> bool:
        return FIELD_WITNESS not in self.withheld

    @property
    def task_outcomes(self) -> bool:
        return FIELD_OUTCOME not in self.withheld

    @property
    def authenticating(self) -> bool:
        return (
            self.group == GROUP_NONRESPONSE_VS_FORGERY
            and FIELD_VERIFICATION not in self.withheld
        )


# ---------------------------------------------------------------------------
# Design file
# ---------------------------------------------------------------------------


def _has_number(node: object) -> bool:
    """Whether a design section holds a number (booleans and strings are fine); aliases are walked once."""
    seen: set[int] = set()
    stack: list[object] = [node]
    walked = 0
    while stack:
        item = stack.pop()
        walked += 1
        if walked > _MAX_WALK:
            raise InjectionDesignError("confounders: the section is too large")
        if isinstance(item, bool):
            continue
        if isinstance(item, (int, float)):
            return True
        if isinstance(item, (Mapping, list, tuple)):
            if id(item) in seen:
                continue
            seen.add(id(item))
            if isinstance(item, Mapping):
                stack.extend(item.keys())
                stack.extend(item.values())
            else:
                stack.extend(item)
    return False


def _design_text(where: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > _MAX_TEXT:
        raise InjectionDesignError(f"{where} must be a non-empty string")
    return value


def load_confounder_design(
    path: str | os.PathLike[str],
) -> Mapping[str, tuple[Variant, ...]]:
    """The variant grid of ``configs/benchmark/injections.yaml`` (top-level section ``confounders``).

    ``confounders.groups`` has exactly the three groups; each has ``members`` (``A`` and ``B`` with
    their ``class`` and ``subtype``: they must be those of ``GROUPS``), ``matrix_rows``,
    ``added_by`` and ``variants``, a mapping from a variant id to its fields (``bounce_gap`` or
    ``attacker``, ``withheld``, ``expected_indistinguishable``, ``source_type``, ``source_ref``,
    ``rationale``). The section holds no number (numbers are rows of ``parameters:``). Raises
    ``InjectionError`` for an invalid file.
    """
    try:
        section = load_design_mapping(_plain(path), "confounders")
    except InjectionError:
        raise
    except MemoryError:
        raise
    except Exception as exc:  # a path object that misbehaves
        raise InjectionDesignError(
            f"the design file cannot be read: {type(exc).__name__}"
        ) from exc
    if _has_number(section):
        raise InjectionDesignError(
            "confounders holds a number: numbers are rows of parameters:"
        )
    groups = section.get("groups")
    if not isinstance(groups, Mapping) or set(groups) != set(GROUPS):
        raise InjectionDesignError(
            f"confounders.groups must list exactly {list(GROUPS)}"
        )
    design: dict[str, tuple[Variant, ...]] = {}
    total = 0
    for group in GROUPS:
        entry = groups[group]
        where = f"confounders.groups.{group}"
        if not isinstance(entry, Mapping) or set(entry) != _GROUP_KEYS:
            raise InjectionDesignError(
                f"{where} must have exactly {sorted(_GROUP_KEYS)}"
            )
        _design_text(f"{where}.added_by", entry["added_by"])
        rows = entry["matrix_rows"]
        if not isinstance(rows, list) or not all(
            isinstance(r, str) and r.strip() for r in rows
        ):
            raise InjectionDesignError(f"{where}.matrix_rows must be a list of strings")
        members = entry["members"]
        info = _GROUP_INFO[group]
        expected = {"A": info.member_a, "B": info.member_b}
        if not isinstance(members, Mapping) or set(members) != set(expected):
            raise InjectionDesignError(f"{where}.members must be A and B")
        for name, (cls, subtype) in expected.items():
            member = members[name]
            if not isinstance(member, Mapping) or dict(member) != {
                "class": cls.value,
                "subtype": subtype,
            }:
                raise InjectionDesignError(
                    f"{where}.members.{name} must be class {cls.value} subtype {subtype}"
                )
        raw_variants = entry["variants"]
        if not isinstance(raw_variants, Mapping) or not raw_variants:
            raise InjectionDesignError(f"{where}.variants must be a non-empty mapping")
        variants: list[Variant] = []
        for variant_id, raw in raw_variants.items():
            total += 1
            if total > MAX_VARIANTS:
                raise InjectionDesignError(f"more than {MAX_VARIANTS} variants")
            vwhere = f"{where}.variants.{variant_id}"
            _design_text(vwhere, variant_id)
            if not isinstance(raw, Mapping) or set(raw) - _VARIANT_KEYS:
                raise InjectionDesignError(f"{vwhere} has unknown or missing fields")
            withheld = raw.get("withheld", [])
            if not isinstance(withheld, list):
                raise InjectionDesignError(f"{vwhere}.withheld must be a list")
            try:
                variants.append(
                    Variant(
                        group=group,
                        variant_id=str(variant_id),
                        withheld=tuple(withheld),
                        bounce_gap=raw.get("bounce_gap"),
                        attacker=raw.get("attacker"),
                        expected_indistinguishable=raw.get(
                            "expected_indistinguishable"
                        ),  # type: ignore[arg-type]
                        source_type=raw.get("source_type"),  # type: ignore[arg-type]
                        source_ref=raw.get("source_ref"),  # type: ignore[arg-type]
                        rationale=raw.get("rationale"),  # type: ignore[arg-type]
                    )
                )
            except ConfounderError as exc:
                raise InjectionDesignError(f"{vwhere}: {exc}") from exc
        design[group] = tuple(variants)
    return design


# ---------------------------------------------------------------------------
# The base of a pair and the scenarios
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PairBase:
    """Everything the two members share: the base day and seed.

    The arguments of ``assemble_latent_days`` (patient, schedule, ``config``, response model,
    library, seed, patient index) and of ``build_observed_base`` (care plan, device errors, design,
    jitter). A pair is one day, day 0. ``dose_index`` picks the dose that carries the dispenser
    mechanisms (groups 1 and 2) and ``measurement_index`` the measurement tick of group 3.
    ``nominal_bounce_gap_ms`` is the resolved nominal gap of the bounce (the design row
    ``dispenser_bounce_magnitude_nominal``; required by the nominal variants, shorter than the
    double-take gap) and ``task_deadline_offset_ms`` the registry ``sched_window`` that the C2
    robot faults need. ``device_profile`` (WS04-T18) is the declared device profile of the run (the cuff
    resolution at the device boundary, the dispenser interval, the driver diagnostics); ``None``: as before.
    """

    patient: PatientParams
    schedule: Schedule
    config: AssemblyConfig
    response_model: ResponseModel
    device_errors: DeviceErrorModel
    design: MeasurementDesign
    jitter: ArrivalJitterModel
    library: SegmentLibrary
    care_plan_id: str
    seed: int
    patient_index: int
    dose_index: int = 0
    measurement_index: int = 0
    nominal_bounce_gap_ms: int | None = None
    task_deadline_offset_ms: int | None = None
    device_profile: GeneratorDeviceProfile | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.patient, PatientParams):
            raise ConfounderError("patient must be a PatientParams")
        if not isinstance(self.schedule, Schedule):
            raise ConfounderError("schedule must be a Schedule")
        if not isinstance(self.config, AssemblyConfig):
            raise ConfounderError("config must be an AssemblyConfig")
        if not callable(getattr(self.response_model, "effect_mmhg", None)):
            raise ConfounderError("response_model must have an effect_mmhg method")
        if not isinstance(self.device_errors, DeviceErrorModel):
            raise ConfounderError("device_errors must be a DeviceErrorModel")
        if not isinstance(self.design, MeasurementDesign):
            raise ConfounderError("design must be a MeasurementDesign")
        if not callable(getattr(self.jitter, "delay_ms", None)) or not isinstance(
            getattr(self.jitter, "descriptor", None), str
        ):
            raise ConfounderError("jitter must have a delay_ms method and a descriptor")
        if not isinstance(self.library, SegmentLibrary):
            raise ConfounderError("library must be a SegmentLibrary")
        object.__setattr__(
            self, "care_plan_id", _text("care_plan_id", self.care_plan_id)
        )
        _int("seed", self.seed, 0, _SEED_LIMIT - 1)
        _int("patient_index", self.patient_index, 0, _WORD_LIMIT - 1)
        _int("dose_index", self.dose_index, 0, T_DAY_MS)
        _int("measurement_index", self.measurement_index, 0, T_DAY_MS)
        if self.nominal_bounce_gap_ms is not None:
            _int("nominal_bounce_gap_ms", self.nominal_bounce_gap_ms, 1, T_DAY_MS)
        if self.task_deadline_offset_ms is not None:
            _int("task_deadline_offset_ms", self.task_deadline_offset_ms, 1, T_DAY_MS)
        if self.device_profile is not None and not isinstance(
            self.device_profile, GeneratorDeviceProfile
        ):
            raise ConfounderError(
                "device_profile must be a GeneratorDeviceProfile or None"
            )


@dataclass(frozen=True, slots=True)
class Scenario:
    """One member of a pair: its specs and the capabilities of the variant.

    ``c1_specs`` change the latent day, ``c2_specs`` and ``c3_specs`` the observed stream;
    ``forced_slots`` are the adherence controls that keep the base of the pair identical
    (scenario controls, not injections: they have no record). ``content_sensing``, ``robot_present``
    and ``task_outcomes`` are the capabilities that the variant keeps (a withheld channel is
    absent from the released day) and ``authenticating_devices`` the devices whose messages are
    verified. The scenario is validated when it is built (``ConfounderError``, review F5): the group,
    the member (``A`` or ``B``) with its mechanism and class, the class and group of every spec,
    the forced slots, the flags (``bool``) and the withheld channels; lists become tuples and a
    ``str`` subclass an exact ``str``.
    """

    group: str
    variant_id: str
    member: str
    mechanism: str
    mechanism_class: InjectedClass
    c1_specs: tuple[InjectionSpec, ...]
    c2_specs: tuple[InjectionSpec, ...]
    c3_specs: tuple[InjectionSpec, ...]
    forced_slots: tuple[ForcedSlot, ...]
    content_sensing: bool
    robot_present: bool
    task_outcomes: bool
    authenticating_devices: tuple[str, ...]
    withheld: tuple[str, ...]

    def __post_init__(self) -> None:
        group = _group(self.group)
        object.__setattr__(self, "group", group)
        object.__setattr__(self, "variant_id", _text("variant_id", self.variant_id))
        member = _choice("member", self.member, ("A", "B"))
        object.__setattr__(self, "member", member)
        info = _GROUP_INFO[group]
        cls, mechanism = info.member_a if member == "A" else info.member_b
        if _text("mechanism", self.mechanism) != mechanism or (
            self.mechanism_class is not cls
        ):
            raise ConfounderError(
                f"member {member} of {group} is the {cls.value} mechanism {mechanism!r}"
            )
        object.__setattr__(self, "mechanism", mechanism)
        for name, spec_cls in (
            ("c1_specs", InjectedClass.C1),
            ("c2_specs", InjectedClass.C2),
            ("c3_specs", InjectedClass.C3),
        ):
            specs = _sequence(name, getattr(self, name), _MAX_ITEMS)
            for spec in specs:
                if not isinstance(spec, InjectionSpec) or spec.cls is not spec_cls:
                    raise ConfounderError(f"{name} holds {spec_cls.value} specs only")
                if (
                    spec.confounder_group is None
                    or _plain(spec.confounder_group) != group
                ):
                    raise ConfounderError(
                        f"every spec of {name} carries the group {group!r}"
                    )
            object.__setattr__(self, name, specs)
        slots = _sequence("forced_slots", self.forced_slots, _MAX_ITEMS)
        if not all(isinstance(slot, ForcedSlot) for slot in slots):
            raise ConfounderError("every forced slot must be a ForcedSlot")
        object.__setattr__(self, "forced_slots", slots)
        for flag in ("content_sensing", "robot_present", "task_outcomes"):
            _bool(flag, getattr(self, flag))
        devices = tuple(
            _text("an authenticating device", device)
            for device in _sequence(
                "authenticating_devices", self.authenticating_devices, _MAX_ITEMS
            )
        )
        object.__setattr__(self, "authenticating_devices", devices)
        withheld = tuple(
            _choice("a withheld channel", item, WITHHOLDABLE)
            for item in _sequence("withheld", self.withheld, _MAX_ITEMS)
        )
        if len(set(withheld)) != len(withheld):
            raise ConfounderError("withheld lists a channel twice")
        object.__setattr__(self, "withheld", withheld)


def _spec(
    cls: InjectedClass, subtype: str, onset_ms: int, **kwargs: Any
) -> InjectionSpec:
    try:
        return InjectionSpec(cls, subtype, onset_ms, **kwargs)
    except InjectionError as exc:
        raise ConfounderError(str(exc)) from exc


def _checked_base(base: object) -> PairBase:
    if not isinstance(base, PairBase):
        raise ConfounderError("base_context must be a PairBase")
    return base


def _checked_variant(group: str, variant: object) -> Variant:
    if not isinstance(variant, Variant):
        raise ConfounderError("variant must be a Variant")
    if variant.group != group:
        raise ConfounderError(
            f"the variant is of group {variant.group!r}, not {group!r}"
        )
    return variant


def build_confounder_pair(
    group: str, variant: Variant, base_context: PairBase
) -> tuple[Scenario, Scenario]:
    """The two scenarios of a pair: member A (the C1 mechanism) and member B (C2 or C3).

    The members share ``base_context`` (the base day and seed). Raises ``ConfounderError`` for an
    unknown group, a variant of another group, a dose or measurement index the schedule does not
    have, or a nominal bounce gap that is missing or not shorter than the double-take gap.
    """
    name = _group(group)
    var = _checked_variant(name, variant)
    base = _checked_base(base_context)
    info = _GROUP_INFO[name]
    schedule = base.schedule
    auth = (DISPENSER_DEVICE,) if var.authenticating else ()
    common: dict[str, Any] = {
        "group": name,
        "variant_id": var.variant_id,
        "content_sensing": var.content_sensing,
        "robot_present": var.robot_present,
        "task_outcomes": var.task_outcomes,
        "authenticating_devices": auth,
        "withheld": var.withheld,
    }
    empty: tuple[InjectionSpec, ...] = ()
    if name == GROUP_REFUSAL_VS_ROBOT_MISSED:
        if base.measurement_index >= len(schedule.measurement_ticks_ms):
            raise ConfounderError("the schedule has no such measurement tick")
        tick = schedule.measurement_ticks_ms[base.measurement_index]
        try:
            refusal = c1_spec("measurement_refusal", tick, confounder_group=name)
        except InjectionError as exc:
            raise ConfounderError(str(exc)) from exc
        failure = _spec(
            InjectedClass.C2,
            "manipulation_failure",
            tick,
            params={"target": vocab.SOURCE_ROBOT, "kind": vocab.KIND_MEASUREMENT},
            confounder_group=name,
        )
        a = Scenario(member="A", mechanism=info.member_a[1], mechanism_class=info.member_a[0],
                     c1_specs=(refusal,), c2_specs=empty, c3_specs=empty, forced_slots=(), **common)  # fmt: skip
        b = Scenario(member="B", mechanism=info.member_b[1], mechanism_class=info.member_b[0],
                     c1_specs=empty, c2_specs=(failure,), c3_specs=empty, forced_slots=(), **common)  # fmt: skip
        return a, b

    if base.dose_index >= len(schedule.dose_ticks_ms):
        raise ConfounderError("the schedule has no such dose")
    tick = schedule.dose_ticks_ms[base.dose_index]
    model = base.config.adherence
    if name == GROUP_DOUBLE_TAKE_VS_BOUNCE:
        double_take_gap = model.config.double_take_gap_ms
        if var.bounce_gap == GAP_NOMINAL:
            gap = base.nominal_bounce_gap_ms
            if gap is None:
                raise ConfounderError("a nominal variant needs nominal_bounce_gap_ms")
            if gap >= double_take_gap:
                raise ConfounderError(
                    "the nominal bounce gap must be shorter than the double-take gap"
                )
        else:
            gap = double_take_gap
        try:
            double = c1_spec("double_take", tick, confounder_group=name)
        except InjectionError as exc:
            raise ConfounderError(str(exc)) from exc
        bounce = _spec(
            InjectedClass.C2,
            "dispenser_bounce",
            tick,
            magnitude=float(gap),
            magnitude_unit="ms",
            params={"target": DISPENSER_DEVICE},
            level=var.bounce_gap,
            confounder_group=name,
        )
        slot = ForcedSlot(0, base.dose_index, AdherenceState.ON_TIME)
        a = Scenario(member="A", mechanism=info.member_a[1], mechanism_class=info.member_a[0],
                     c1_specs=(double,), c2_specs=empty, c3_specs=empty, forced_slots=(), **common)  # fmt: skip
        b = Scenario(member="B", mechanism=info.member_b[1], mechanism_class=info.member_b[0],
                     c1_specs=empty, c2_specs=(bounce,), c3_specs=empty, forced_slots=(slot,), **common)  # fmt: skip
        return a, b

    # group 2: the dose is taken and does nothing (A), or never taken and forged (B)
    lag = model.config.intake_lag_ms
    length = schedule.slot_lengths_ms()[base.dose_index]
    try:
        nonresponse = c1_spec(
            "drug_nonresponse",
            tick,
            duration_ms=length,
            magnitude=COMPLETE_NONRESPONSE_SCALE,
            level="complete",
            confounder_group=name,
        )
    except InjectionError as exc:
        raise ConfounderError(str(exc)) from exc
    assert var.attacker is not None  # Variant required it for this group
    forgery = _spec(
        InjectedClass.C3,
        "dispense_forgery",
        tick,
        level=var.attacker,
        confounder_group=name,
    )
    c3: tuple[InjectionSpec, ...] = (forgery,)
    if var.attacker == "informed" and var.robot_present:
        spoof = _spec(
            InjectedClass.C3,
            "presence_spoof",
            tick + lag,  # at the instant the genuine intake would have been seen
            params={"spoof_intake": True},
            level="informed",
            confounder_group=name,
        )
        c3 = (spoof, forgery)
    a = Scenario(member="A", mechanism=info.member_a[1], mechanism_class=info.member_a[0],
                 c1_specs=(nonresponse,), c2_specs=empty, c3_specs=empty,
                 forced_slots=(ForcedSlot(0, base.dose_index, AdherenceState.ON_TIME),), **common)  # fmt: skip
    b = Scenario(member="B", mechanism=info.member_b[1], mechanism_class=info.member_b[0],
                 c1_specs=empty, c2_specs=empty, c3_specs=c3,
                 forced_slots=(ForcedSlot(0, base.dose_index, AdherenceState.OMITTED),), **common)  # fmt: skip
    return a, b


# ---------------------------------------------------------------------------
# Realising a scenario
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RealisedScenario:
    """A scenario assembled and observed.

    ``latent`` is the assembled latent day (generator side), ``stream`` the observed stream with
    its generator-side records (it carries latent values and is never written to a file),
    ``observed`` the released ``ObservedDay`` (withheld channels removed), ``records`` every
    injection record of the member (C1, C2, C3) tagged with the variant and the flag, ``log`` their
    sidecar entries and ``ground_truth`` the events of the C2 and C3 records (the C1 truth is the
    labeller's). The ``stream`` keeps the robot visits of the base even when the variant has no robot:
    only the injectors are shown none (module docstring).
    """

    scenario: Scenario
    latent: LatentResult
    stream: ObservedStream
    observed: ObservedDay
    records: tuple[InjectionRecord, ...]
    log: list[dict[str, Any]]
    ground_truth: tuple[GroundTruthEvent, ...]


def _withhold(day: ObservedDay, scenario: Scenario) -> ObservedDay:
    """The released day: the channels the variant does not have are removed (nothing is added)."""
    samples: Sequence[Sample] = day.samples
    events: Sequence[Event] = day.events
    if not scenario.robot_present:
        samples = [s for s in samples if s.signal != "presence"]
        events = [e for e in events if e.source != vocab.SOURCE_ROBOT]
    if not scenario.task_outcomes:
        events = [e for e in events if e.kind is not EventKind.ROBOT_TASK]
    return dataclasses.replace(day, samples=tuple(samples), events=tuple(events))


def realise_scenario(scenario: Scenario, base_context: PairBase) -> RealisedScenario:
    """Assemble the latent day of a scenario and observe it (the pipeline of the README).

    The latent day (``assemble_latent_days``: the C1 specs and the forced slots), the fault-free
    observed base (``build_observed_base``: the refused ticks are skipped, the dispenser senses
    its content if the variant says so), the declined-task events of the refusals, the C2 and C3
    injections (``apply_observation_injections``), the released day (withheld channels removed).
    Nothing is read from the other member. Raises ``InjectionError`` subclasses only.
    """
    if not isinstance(scenario, Scenario):
        raise ConfounderError("scenario must be a Scenario")
    base = _checked_base(base_context)
    try:
        return _realise(scenario, base)
    except InjectionError:
        raise
    except MemoryError:
        raise
    except Exception as exc:
        # the errors of the measurement and segment modules, or an argument
        # of another module (a device error model, a patient) that misbehaves when it is read
        raise ConfounderError(f"{type(exc).__name__}: {exc}") from exc


def _realise(scenario: Scenario, base: PairBase) -> RealisedScenario:
    [latent] = assemble_latent_days(
        base.patient,
        base.schedule,
        1,
        list(scenario.c1_specs),
        base.response_model,
        base.library,
        base.seed,
        base.patient_index,
        config=base.config,
        forced_slots=scenario.forced_slots,
    )
    observed_base = build_observed_base(
        latent.latent,
        base.schedule,
        base.care_plan_id,
        base.device_errors,
        base.design,
        base.jitter,
        base.library,
        base.seed,
        base.patient_index,
        allow_no_segments=base.config.allow_no_segments,
        skip_measurement_ticks_ms=latent.refused_ticks_ms,
        dispenser_content_sensing=scenario.content_sensing,
    )
    stream = observe_refusals(observed_base, latent.c1_records)
    context = InjectionContext(
        base.patient_index,
        library=base.library,
        latent=latent.latent,
        task_deadline_offset_ms=base.task_deadline_offset_ms,
        dispenser_content_sensing=scenario.content_sensing,
        authenticating_devices=scenario.authenticating_devices,
        device_profile=base.device_profile,
    )
    # A deployment without a robot has no robot in the room: the injectors read the stream without
    # its visits, so a forged dispense reads the witness as None (never a negative) and its record
    # carries no witness path (review F2). Group 3 injects a fault at a robot visit (its
    # ``robot_absent`` variant withholds what the robot reports, not the robot), so it keeps them.
    # The visits are restored afterwards: they are the base of the pair, shared by both members.
    hide_visits = (
        not scenario.robot_present and scenario.group != GROUP_REFUSAL_VS_ROBOT_MISSED
    )
    seen = dataclasses.replace(stream, visits=()) if hide_visits else stream
    result = apply_observation_injections(
        seen, [*scenario.c2_specs, *scenario.c3_specs], context
    )
    if hide_visits:
        result = dataclasses.replace(
            result, stream=dataclasses.replace(result.stream, visits=stream.visits)
        )
    released = _withhold(
        finalize_observed(result.stream, base.device_profile), scenario
    )
    records = (*latent.c1_records, *result.records)
    return RealisedScenario(
        scenario=scenario,
        latent=latent,
        stream=result.stream,
        observed=released,
        records=records,
        log=confounder_log(records),
        ground_truth=tuple(
            ground_truth_events(list(result.records))
        ),  # the C2 and C3 events only
    )


# ---------------------------------------------------------------------------
# Comparing observed days
# ---------------------------------------------------------------------------


def _by_repr(items: Sequence[Hashable]) -> tuple[Hashable, ...]:
    return tuple(sorted(items, key=repr))


def _payload(event: Event) -> tuple[tuple[str, Any], ...]:
    return tuple(sorted(event.payload.items(), key=lambda kv: kv[0]))


def _is_gateway_error(event: Event) -> bool:
    return event.kind is EventKind.VERIFICATION and event.source == vocab.SOURCE_GATEWAY


def _views(
    day: ObservedDay, visits: Sequence[RobotVisit], ignore_pressure: bool
) -> dict[str, Hashable]:
    dispenses = [e for e in day.events if e.kind is EventKind.DISPENSE]
    presence = [s for s in day.samples if s.signal == "presence"]
    intakes = [e for e in day.events if e.kind is EventKind.INTAKE]
    tasks = [e for e in day.events if e.kind is EventKind.ROBOT_TASK]
    failures = [e for e in day.events if _is_gateway_error(e)]
    in_visit = [
        any(v.arrival_ms <= s.t_device_ms <= v.departure_ms for s in presence)
        for v in visits
    ]
    off_visit = [
        (s.t_device_ms, s.value)
        for s in presence
        if not any(v.arrival_ms <= s.t_device_ms <= v.departure_ms for v in visits)
    ]
    ordered = sorted(dispenses, key=lambda e: (e.t_device_ms, e.t_rx_ms))
    rest_samples = [
        (s.signal, s.t_device_ms, s.t_rx_ms, s.value, s.seq, s.quality)
        for s in day.samples
        if s.signal != "presence" and not (ignore_pressure and s.signal == "bp")
    ]
    rest_events = [
        (e.kind.value, e.t_device_ms, e.t_rx_ms, e.source, _payload(e), e.seq)
        for e in day.events
        if e.kind not in (EventKind.DISPENSE, EventKind.INTAKE, EventKind.ROBOT_TASK)
        and not _is_gateway_error(e)
    ]
    return {
        FIELD_CONTENT: _by_repr(
            [
                (e.t_device_ms, e.payload[vocab.KEY_CONTENT_CHANGE])
                for e in dispenses
                if vocab.KEY_CONTENT_CHANGE in e.payload
            ]
        ),
        FIELD_WITNESS: (
            _by_repr([(e.t_device_ms, e.t_rx_ms, e.source, e.seq) for e in intakes]),
            tuple(in_visit),
            _by_repr(off_visit),
        ),
        FIELD_OUTCOME: _by_repr(
            [(e.t_device_ms, e.source, _payload(e)) for e in tasks]
        ),
        FIELD_INTERVAL: _by_repr(
            [
                (e.t_device_ms, e.t_rx_ms, e.source, e.payload.get(vocab.KEY_INTERVAL))
                for e in dispenses
            ]
        ),
        FIELD_SEQ: tuple(e.seq for e in ordered),
        FIELD_VERIFICATION: _by_repr(
            [(e.t_device_ms, e.t_rx_ms, _payload(e)) for e in failures]
        ),
        FIELD_OTHER: (_by_repr(rest_samples), _by_repr(rest_events)),
    }


def compare_observed(
    a: ObservedDay,
    b: ObservedDay,
    visits: Sequence[RobotVisit],
    masked: Sequence[str],
    *,
    ignore_pressure: bool = False,
) -> tuple[str, ...]:
    """The discriminating fields in which two observed days differ (empty: indistinguishable).

    Each of ``DISCRIMINATORS`` is compared as the observer sees it (``content_change`` of the
    dispenses, the INTAKE events and the presence level over each robot visit, the robot task
    outcomes, the dispense times, their sequence numbers, the failed gateway verifications); the
    ``masked`` ones (the channels the variant withholds) are left out; ``other`` is added when
    anything else in the days differs (the pressure samples are left out with ``ignore_pressure``).
    The order of items at one instant is not a difference. Only observed days and the robot visits
    are read. The result is in the order of ``DISCRIMINATORS``, ``other`` last.
    """
    for name, day in (("a", a), ("b", b)):
        if not isinstance(day, ObservedDay):
            raise ConfounderError(f"{name} must be an ObservedDay")
    seen = _sequence("visits", visits, _MAX_WALK)
    if not all(isinstance(v, RobotVisit) for v in seen):
        raise ConfounderError("every visit must be a RobotVisit")
    hidden = tuple(
        _choice("a masked field", field, DISCRIMINATORS)
        for field in _sequence("masked", masked, _MAX_ITEMS)
    )
    ignore = _bool("ignore_pressure", ignore_pressure)
    try:
        first, second = _views(a, seen, ignore), _views(b, seen, ignore)
        different = [
            f for f in DISCRIMINATORS if f not in hidden and first[f] != second[f]
        ]
        if first[FIELD_OTHER] != second[FIELD_OTHER]:
            different.append(FIELD_OTHER)
    except Exception as exc:
        # a day or a visit of another module whose fields misbehave
        raise _unreadable("an observed day or a visit", exc) from exc
    return tuple(different)


# ---------------------------------------------------------------------------
# Log and evaluation
# ---------------------------------------------------------------------------

_TAG_KEYS: Final = ("variant_id", "indistinguishable_by_construction")


def confounder_log(records: Sequence[InjectionRecord]) -> list[dict[str, Any]]:
    """The injection-log entries of the records, with the pair tags promoted to the top level.

    ``injection.injection_log`` entries plus, for a record tagged by ``evaluate_pair``,
    ``variant_id`` and ``indistinguishable_by_construction`` (also kept in ``details``).
    """
    checked = _sequence("records", records, _MAX_WALK)
    try:
        entries = injection_log(list(checked))
        for entry, record in zip(entries, checked, strict=True):
            for key in _TAG_KEYS:
                if key in record.details:
                    entry[key] = record.details[key]
    except InjectionError as exc:
        raise ConfounderError(str(exc)) from exc
    except Exception as exc:  # a record of another module whose fields misbehave
        raise _unreadable("a record", exc) from exc
    return entries


def _tag(
    records: Sequence[InjectionRecord], variant_id: str, flag: bool
) -> tuple[InjectionRecord, ...]:
    return tuple(
        dataclasses.replace(
            r,
            details={
                **r.details,
                "variant_id": variant_id,
                "indistinguishable_by_construction": flag,
            },
        )
        for r in records
    )


@dataclass(frozen=True, slots=True)
class PairEvaluation:
    """A pair realised and compared.

    ``separated_by`` are the discriminating fields in which the observed days differ (the withheld
    ones excluded); ``indistinguishable_by_construction`` is True exactly when it is empty.
    ``pressure_response_differs`` says whether the released pressure samples differ (they do for
    the double-take pair: two doses against one); for that group the comparison ignores them.
    Both members' records carry ``variant_id`` and the flag.
    """

    group: str
    variant: Variant
    a: RealisedScenario
    b: RealisedScenario
    separated_by: tuple[str, ...]
    indistinguishable_by_construction: bool
    pressure_response_differs: bool


def evaluate_pair(
    group: str, variant: Variant, base_context: PairBase
) -> PairEvaluation:
    """Build, realise and compare the pair of a variant (the whole of this module in one call)."""
    name = _group(group)
    var = _checked_variant(name, variant)
    base = _checked_base(base_context)
    first, second = build_confounder_pair(name, var, base)
    a, b = realise_scenario(first, base), realise_scenario(second, base)
    if a.stream.visits != b.stream.visits:
        raise ConfounderError(
            "the members do not share their robot visits (the base differs)"
        )
    ignore = _GROUP_INFO[name].pressure_differs
    separated = compare_observed(
        a.observed, b.observed, a.stream.visits, var.withheld, ignore_pressure=ignore
    )
    flag = not separated

    def bp(day: ObservedDay) -> list[tuple[int, float]]:
        return [(s.t_device_ms, s.value) for s in day.samples if s.signal == "bp"]

    tagged: list[RealisedScenario] = []
    for member in (a, b):
        records = _tag(member.records, var.variant_id, flag)
        tagged.append(
            dataclasses.replace(member, records=records, log=confounder_log(records))
        )
    return PairEvaluation(
        group=name,
        variant=var,
        a=tagged[0],
        b=tagged[1],
        separated_by=separated,
        indistinguishable_by_construction=flag,
        pressure_response_differs=bp(a.observed) != bp(b.observed),
    )
