"""Benchmark builder, reader and care-plan files (WS04-T11): the composition module of ``ralmon.benchmark``.

``generate_benchmark`` assembles the generator steps of WS04-T02 to WS04-T10 and WS04-T15 into one benchmark
version: ``manifest.json``, ``days/`` (observed days only), ``truth/`` (latent days, ground truth and the sidecars),
``plans/`` (care plans), and ``generator/`` (the latent baseline pressure that a validation needs). Like
``labelling.py`` and ``validation.py`` it is one of the modules that may import ``ralmon.spec`` and
``ralmon.monitor`` (README issue I1).

Per virtual patient, in this order (``BuildContext.build_patient``):

1. the patient is drawn from the prior (stream ``PATIENT``); the schedule comes from the registry windows
   (``load_schedule``), the same for every patient of the version;
2. the injection plan: the C1 specs of the whole record are drawn from the rate of ``injections.yaml`` (stream
   ``INJECTION_PLAN``) and their relative magnitudes are resolved with the registry or the patient (``scale_range``,
   the distance from the baseline to ``bp_hold_threshold``); the C2 and C3 specs of a day are drawn once the latent
   day exists, because their onsets are ticks, dispenses and robot visits;
3. the latent days (``assemble_latent_days``, one call per day, ``end_state`` chained);
4. the observed base (``build_observed_base``), the declined-task events of the refusals, the C2 and C3 injectors
   (``apply_observation_injections``, ``previous_day`` and the sequence counters chained), ``finalize_observed``;
5. the robot ``NODE_STATE`` reports with ``colocated`` (ADR-054 (b), ADR-035): one arrival report (true) per visit,
   including the first of the day, at the instant of the arrival, and one departure report (false) where no other
   visit keeps the robot in the room; source ``robot``, ``payload.state`` ``active``;
6. the ground truth (``label_latent_day_detailed`` with the earlier days as history, ADR-046 and ADR-064) and the
   sidecars: one ``injection_log`` entry per record of the day with ``record_index``, ``truth_indices`` and
   ``explains_in_later_days`` (the events of later days that the record explains, ADR-064: an event of day d can be
   explained by a record of day d-1 and is then in no ``truth_indices`` of day d).

The care plan covers the whole record of the patient (a SCHED instance for every measurement tick of every day, the
day-end COUNT of every day, and one parameter record each for RANGE, HOLD and COUNT with ``anchor_ms`` None so
that the baseline B1 is not vacuous). The tail day (ADR-066): every patient has ``n_days + 1`` days; the last one is
generated with the same machinery, labelled with the history of the scored days, and marked in the manifest; only
the events it decides at its first step are the truth of the closing step of the last scored day
(``BenchmarkReader.closing_step_truth``). It is in no split count or day total.

Confounder twin patients (``BuildContext.build_pairs``): two single-day patients per pair, made with
``build_confounder_pair``/``realise_scenario`` (the paired design), plus their tail day. A pair is a unit of the
split: both members are in the same split.

Determinism. All randomness is a named stream of ``ralmon.benchmark.rng`` keyed by the generation seed, the patient
index, the day and a purpose; files are canonical JSON; the manifest has no clock, host or user field. Two builds
of one configuration and one generation seed give the same bytes.

Numbers. Nothing here is a clinical or device value. The scale, the split fractions, the monitor step, the
generation seed, the injection rates and the number of confounder pairs are rows of ``default.yaml`` and
``injections.yaml`` (design choices awaiting H3, with their reasons); the levels of durations and magnitudes are rows of
``injections.yaml``; the priors come through ``PriorSource``.
"""

from __future__ import annotations

import dataclasses
import json
import math
import platform
import re
import shutil
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any, Final, cast

import numpy as np
import yaml

from ralmon.benchmark import vocab
from ralmon.benchmark.adherence import (
    AdherenceModel,
    load_adherence_config,
)
from ralmon.benchmark.anchoring import (
    ANCHORED_SUBTYPES,
    READINGS_UNIT,
    anchored_choices,
    annotate_reading_counts,
    draw_anchored_window,
    stream_readings,
)
from ralmon.benchmark.confounders import (
    GROUPS,
    PairBase,
    RealisedScenario,
    Variant,
    build_confounder_pair,
    confounder_log,
    evaluate_pair,
    load_confounder_design,
    realise_scenario,
)
from ralmon.benchmark.inject_c1 import (
    C1_SUBTYPES,
    C1InjectionError,
    c1_spec,
    c1_spec_from_level,
    hold_distance_mmhg,
    load_c1_design,
    observe_refusals,
)
from ralmon.benchmark.inject_c2 import plan_dispenser_bounces
from ralmon.benchmark.injection import (
    InjectionContext,
    InjectionError,
    InjectionRecord,
    InjectionSpec,
    LevelRow,
    QuantityDesign,
    SubtypeDesign,
    apply_observation_injections,
    finalize_observed,
    load_injection_design,
    resolve_magnitude,
    stable_index,
)
from ralmon.benchmark.labelling import MODES, HistoryDay, label_latent_day_detailed
from ralmon.benchmark.latent import MAX_GRID_POINTS, T_DAY_MS
from ralmon.benchmark.latent_day import (
    AssemblyConfig,
    ForcedSlot,
    LatentResult,
    assemble_latent_days,
)
from ralmon.benchmark.measurement import (
    ArrivalJitterModel,
    EmpiricalJitter,
    MeasurementDesign,
    NoJitter,
    ObservedStream,
    RobotVisit,
    build_observed_base,
    jitter_descriptor,
    load_measurement_design,
)
from ralmon.benchmark.pkpd import OneCompartmentEmax
from ralmon.benchmark.priors import (
    DeviceErrorModel,
    FixtureOnlyPriorError,
    ParameterRow,
    PatientParams,
    PriorConfigError,
    PriorSource,
    UnfilledParameterError,
    load_design_file,
)
from ralmon.benchmark.rng import StreamPurpose, stream
from ralmon.benchmark.schedule import (
    Schedule,
    ScheduleError,
    check_schedule_consistency,
    load_filled_rows,
    load_schedule,
)
from ralmon.benchmark.segments import SegmentError, SegmentIndex, SegmentLibrary
from ralmon.benchmark.trace import (
    MANIFEST_NAME,
    SPLITS,
    BenchmarkDay,
    GroundTruthEvent,
    InjectedClass,
    JsonValue,
    Manifest,
    ManifestError,
    ObservedDay,
    TraceError,
    TruthRecord,
    file_sha256,
    read_manifest,
    read_observed_day,
    read_truth,
    verify_manifest,
    write_manifest,
    write_observed_day,
    write_truth,
)
from ralmon.monitor import MonitorConfig
from ralmon.signals import MS_PER_HOUR, Event, EventKind
from ralmon.spec import (
    CarePlan,
    RegistryError,
    TemplateId,
    TemplateInstance,
    load_registry,
    load_templates,
)

__all__ = [
    "BenchmarkConfig",
    "BenchmarkConfigError",
    "BenchmarkReader",
    "BuildContext",
    "BuiltDay",
    "BuiltPatient",
    "CohortSpec",
    "ObservedViewError",
    "PatientInjections",
    "TruthUnavailableError",
    "generate_benchmark",
    "load_benchmark",
    "load_config",
    "open_benchmark",
    "read_care_plan",
    "split_patients",
    "verify_benchmark",
    "write_care_plan",
]

GENERATOR_DIR: Final = "generator"
PLANS_DIR: Final = "plans"
SCHEMA_VERSION: Final = "0.1.0"
ROLE_PATIENT: Final = "patient"
ROLE_PAIR: Final = "confounder_pair"
UNKNOWN_REV: Final = "unknown"
_SEED_BITS: Final = 64  # algorithmic: width of the root seed
SEED_LIMIT: Final = 1 << _SEED_BITS
_ID_PATTERN: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
_REQUIRED_ROWS: Final = (
    "n_patients",
    "n_days",
    "generation_seed",
    "split_fractions",
    "monitor_step_ms",
    "monitor_reorder_delay_ms",
)
_CONFIG_KEYS: Final = frozenset(
    {
        "schema_version",
        "benchmark_version",
        "pathway_template_id",
        "paths",
        "cohorts",
        "labelling",
        "device_profile",
        "allow_no_segments",
        "confounders",
        "parameters",
    }
)
_PATH_KEYS: Final = (
    "registry",
    "generator_design",
    "care_plans",
    "injections",
    "segments",
)
_RECORD_PARAMS: Final = (  # the parameter records of the plan (anchor None): what B1 reads (WS06-T02, F-B1-3)
    (TemplateId.RANGE, "record-range", ("bp_band_low", "bp_band_high")),
    (TemplateId.HOLD, "record-hold", ("bp_hold_threshold", "hold_lookback")),
    (TemplateId.COUNT, "record-count", ("dose_max_24h", "dose_min_day_end")),
)
_WINDOW_NAMES: Final = (
    "hold_lookback",
    "delta1",
    "delta2",
    "sched_window",
    "int_window",
)
# The three attacks on the cuff stream share one overlap group (inject_c3): their windows must not overlap.
_CUFF_ATTACKS: Final = ("replay", "injection_naive", "injection_informed")
_C2_DRIVEN: Final = (  # the C2 subtypes that the class rate draws (the other two follow the prior rates)
    "cuff_detached",
    "cuff_silent_bias",
    "ecg_noise",
    "manipulation_failure",
    "nav_delay",
    "stuck_at",
)


def _magnitude_references(errors: DeviceErrorModel) -> dict[str, float]:
    """The prior quantities a relative magnitude level may be a multiple of, for one cohort."""
    return {
        "cuff_error_sd_mmhg": errors.cuff_error_sd_mmhg,
        "cuff_bias_mmhg": errors.cuff_bias_mmhg,
    }


def drawable_magnitude_levels(
    block: QuantityDesign, errors: DeviceErrorModel
) -> tuple[tuple[LevelRow, ...], tuple[str, ...]]:
    """``(drawable levels, excluded level names)`` of a magnitude block for the device errors of one cohort.

    A level whose resolved magnitude is exactly zero is not drawn: an injection with no effect is never
    realised (the level ``device_bias`` of ``cuff_silent_bias`` is the multiplier 1.0 of ``cuff_bias_mmhg``,
    which is 0.0 mmHg for an accurate device), and keeping it in the uniform draw wastes that share of the
    injections. The level keeps its definition: with a non-zero prior bias it is drawn again. The resolution
    is the one the planner applies (``resolve_magnitude``); a level still awaiting a value is kept, and the
    planner refuses it where it draws it.
    """
    references = _magnitude_references(errors)
    drawable: list[LevelRow] = []
    excluded: list[str] = []
    for level in block.levels:
        if level.value is None:
            magnitude: float | None = None
        elif level.reference is None:
            magnitude = float(level.value)
        else:
            magnitude = resolve_magnitude(
                level, references[level.reference], level.reference
            )
        if magnitude == 0.0:
            excluded.append(level.level)
        else:
            drawable.append(level)
    if not drawable:
        raise BenchmarkConfigError(
            f"every level of the magnitude block {block.key!r} resolves to zero: nothing can be injected"
        )
    return tuple(drawable), tuple(excluded)


_C3_ORDER: Final = (
    "dispense_forgery",
    "injection_informed",
    "injection_naive",
    "presence_spoof",
    "replay",
)
_ATTACKER_LEVELS: Final = ("naive", "informed")


class BenchmarkConfigError(ValueError):
    """The configuration of a build is missing, malformed or inconsistent (CLI exit code 2)."""


class TruthUnavailableError(TraceError):
    """A truth file was asked for and the benchmark directory has none (observed-only copy)."""


# ---------------------------------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------------------------------


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _int_row(name: str, value: object, lo: int, hi: int | None = None) -> int:
    if not _is_int(value):
        raise BenchmarkConfigError(f"row {name!r} must be an integer, got {value!r}")
    assert isinstance(value, int)
    if value < lo or (hi is not None and value > hi):
        raise BenchmarkConfigError(f"row {name!r} must be at least {lo}, got {value}")
    return value


def _dump(obj: object) -> bytes:
    """Canonical JSON, as ``ralmon.benchmark.trace`` writes it."""
    return (json.dumps(obj, sort_keys=True, indent=2, allow_nan=False) + "\n").encode(
        "utf-8"
    )


def _write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_dump(obj))


def _safe_id(what: str, value: object) -> str:
    if not isinstance(value, str) or _ID_PATTERN.fullmatch(value) is None:
        raise BenchmarkConfigError(f"{what} is not a usable identifier: {value!r}")
    return value


def _hours_per_day() -> float:
    return T_DAY_MS / MS_PER_HOUR


# ---------------------------------------------------------------------------------------------------
# Split by patient
# ---------------------------------------------------------------------------------------------------


def _fractions(fractions: object) -> dict[str, Fraction]:
    """The split fractions as exact decimals: exactly the three splits, each at least 0, summing to 1."""
    if not isinstance(fractions, Mapping) or set(fractions) != set(SPLITS):
        raise BenchmarkConfigError(
            f"the split fractions must be a mapping with exactly the keys {list(SPLITS)}"
        )
    exact: dict[str, Fraction] = {}
    for name in SPLITS:
        value = fractions[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise BenchmarkConfigError(f"split fraction {name!r} must be a number")
        if not math.isfinite(value) or value < 0:
            raise BenchmarkConfigError(
                f"split fraction {name!r} must be finite and not negative"
            )
        exact[name] = Fraction(str(value))
    if sum(exact.values()) != 1:
        raise BenchmarkConfigError(
            f"the split fractions must sum to 1, got {[str(fractions[n]) for n in SPLITS]}"
        )
    return exact


def _split_sizes(n: int, exact: Mapping[str, Fraction]) -> dict[str, int]:
    """Largest-remainder sizes; ties are broken by the order train, calibration, test."""
    quotas = {name: n * exact[name] for name in SPLITS}
    sizes = {name: math.floor(quotas[name]) for name in SPLITS}
    leftover = n - sum(sizes.values())
    by_remainder = sorted(
        range(len(SPLITS)), key=lambda i: (-(quotas[SPLITS[i]] - sizes[SPLITS[i]]), i)
    )
    for i in by_remainder[:leftover]:
        sizes[SPLITS[i]] += 1
    return sizes


def split_patients(
    ids: Iterable[str], fractions: Mapping[str, float], seed: int
) -> Mapping[str, str]:
    """Assign every id to exactly one of ``train``, ``calibration``, ``test`` (the split is by patient).

    The sizes follow the largest-remainder rule on the exact decimal fractions (7 patients and 0.5, 0.25, 0.25 give
    3, 2, 2). The ids are sorted first and then permuted with the stream ``(seed, 0, None, SPLIT)``, so the result is
    a function of the set of ids, the fractions and the seed, not of the order of ``ids``. Raises
    ``BenchmarkConfigError`` for fractions that do not sum to 1, an unknown split name or a repeated id.
    """
    exact = _fractions(fractions)
    ordered = sorted(ids)
    if len(set(ordered)) != len(ordered):
        raise BenchmarkConfigError(
            "an id is listed twice: a patient has one split only"
        )
    if not _is_int(seed) or not 0 <= seed < SEED_LIMIT:
        raise BenchmarkConfigError("the split seed must be an integer in [0, 2**64)")
    sizes = _split_sizes(len(ordered), exact)
    order = stream(seed, 0, None, StreamPurpose.SPLIT).permutation(len(ordered))
    result: dict[str, str] = {}
    position = 0
    for name in SPLITS:
        for index in order[position : position + sizes[name]]:
            result[ordered[int(index)]] = name
        position += sizes[name]
    return {pid: result[pid] for pid in ordered}


# ---------------------------------------------------------------------------------------------------
# The configuration
# ---------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CohortSpec:
    """One cohort: its id, the prior file it is drawn from (None: the prior is passed in) and its size."""

    id: str
    prior: Path | None
    n_patients: int


@dataclass(frozen=True, slots=True)
class BenchmarkConfig:
    """A parsed ``default.yaml``-shaped configuration; every number comes from a row (no default exists)."""

    path: Path | None
    benchmark_version: str
    pathway_template_id: str
    generation_seed: int
    n_patients: int
    n_days: int
    cohorts: tuple[CohortSpec, ...]
    split_fractions: Mapping[str, float]
    monitor_step_ms: int
    monitor_reorder_delay_ms: int
    labelling_mode: str
    registry_path: Path
    generator_design_path: Path
    care_plans_path: Path
    injections_path: Path
    segments_path: Path
    arrival_jitter_path: Path | None
    dispenser_content_sensing: bool
    authenticating_devices: tuple[str, ...]
    allow_no_segments: bool
    confounder_variants: tuple[str, ...] | None
    rows: tuple[ParameterRow, ...] = field(default=(), repr=False)

    @property
    def latent_step_ms(self) -> int:
        """The grid of the latent pressure is the step of the monitor configuration (one grid for both)."""
        return self.monitor_step_ms

    @property
    def total_patients(self) -> int:
        return sum(c.n_patients for c in self.cohorts)

    def with_overrides(
        self,
        *,
        n_patients: int | None = None,
        n_days: int | None = None,
        generation_seed: int | None = None,
        prior: Path | None = None,
    ) -> BenchmarkConfig:
        """A copy with the command-line overrides applied (``--n-patients`` needs a single cohort)."""
        cohorts = self.cohorts
        if n_patients is not None:
            if len(cohorts) != 1:
                raise BenchmarkConfigError("--n-patients needs exactly one cohort")
            cohorts = (
                dataclasses.replace(
                    cohorts[0], n_patients=_int_row("n_patients", n_patients, 1)
                ),
            )
        if prior is not None:
            if len(cohorts) != 1:
                raise BenchmarkConfigError("--prior needs exactly one cohort")
            cohorts = (dataclasses.replace(cohorts[0], prior=Path(prior)),)
        return dataclasses.replace(
            self,
            n_patients=n_patients if n_patients is not None else self.n_patients,
            n_days=_int_row("n_days", n_days, 1) if n_days is not None else self.n_days,
            generation_seed=(
                _int_row("generation_seed", generation_seed, 0, SEED_LIMIT - 1)
                if generation_seed is not None
                else self.generation_seed
            ),
            cohorts=cohorts,
        )


def _resolve(base: Path, value: object, what: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise BenchmarkConfigError(f"{what} must be a path string, got {value!r}")
    path = Path(value)
    return path if path.is_absolute() else (base / path).resolve()


def load_config(path: str | Path) -> BenchmarkConfig:
    """Read a build configuration. Relative paths are relative to the directory of the file.

    Raises ``BenchmarkConfigError`` for a missing file, a malformed document, a missing or invalid row, and
    ``UnfilledParameterError`` for a required row that is still ``awaiting_human_value``: the builder has no default
    for the scale, the seed, the split fractions or the monitor step.
    """
    target = Path(path)
    try:
        document = yaml.safe_load(target.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError, UnicodeDecodeError) as exc:
        raise BenchmarkConfigError(
            f"cannot read the configuration {target}: {exc}"
        ) from exc
    if not isinstance(document, Mapping):
        raise BenchmarkConfigError(
            f"{target}: the file must hold a mapping at top level"
        )
    missing = sorted(_CONFIG_KEYS - set(document))
    unknown = sorted(str(k) for k in set(document) - _CONFIG_KEYS)
    if missing or unknown:
        raise BenchmarkConfigError(
            f"{target}: missing keys {missing}, unknown keys {unknown}"
        )
    if document["schema_version"] != SCHEMA_VERSION:
        raise BenchmarkConfigError(
            f"{target}: schema_version must be {SCHEMA_VERSION!r}"
        )
    try:
        parsed = load_design_file(target)
    except PriorConfigError as exc:
        raise BenchmarkConfigError(str(exc)) from exc
    rows = {r.parameter: r for r in parsed.rows}
    for name in _REQUIRED_ROWS:
        row = rows.get(name)
        if row is None:
            raise BenchmarkConfigError(
                f"{target}: the row {name!r} is missing and the builder has no default for it"
            )
        if not row.filled:
            raise UnfilledParameterError(
                f"parameter {name} is awaiting_human_value in {target}: a human supplies the value"
            )
    n_patients = _int_row("n_patients", rows["n_patients"].value, 1)
    n_days = _int_row("n_days", rows["n_days"].value, 1)
    seed = _int_row("generation_seed", rows["generation_seed"].value, 0, SEED_LIMIT - 1)
    step = _int_row("monitor_step_ms", rows["monitor_step_ms"].value, 1, T_DAY_MS)
    if T_DAY_MS % step != 0 or T_DAY_MS // step > MAX_GRID_POINTS:
        raise BenchmarkConfigError(
            "monitor_step_ms must divide the day and give a latent grid of at most "
            f"{MAX_GRID_POINTS} points"
        )
    reorder = _int_row(
        "monitor_reorder_delay_ms", rows["monitor_reorder_delay_ms"].value, 0, T_DAY_MS
    )
    fractions = rows["split_fractions"].value
    _fractions(fractions)
    base = target.resolve().parent
    paths = document["paths"]
    if not isinstance(paths, Mapping) or not set(_PATH_KEYS) <= set(paths) <= {
        *_PATH_KEYS,
        "arrival_jitter",
    }:
        raise BenchmarkConfigError(
            f"{target}: paths needs {list(_PATH_KEYS)} and optionally arrival_jitter"
        )
    jitter = paths.get("arrival_jitter")
    cohorts_raw = document["cohorts"]
    if not isinstance(cohorts_raw, list) or not cohorts_raw:
        raise BenchmarkConfigError(f"{target}: cohorts must be a non-empty list")
    cohorts: list[CohortSpec] = []
    for entry in cohorts_raw:
        if not isinstance(entry, Mapping) or not {"id"} <= set(entry) <= {
            "id",
            "prior",
            "n_patients",
        }:
            raise BenchmarkConfigError(
                f"{target}: a cohort needs id and optionally prior and n_patients"
            )
        cohort_id = _safe_id("a cohort id", entry["id"])
        prior = entry.get("prior")
        size = (
            n_patients
            if entry.get("n_patients") is None
            else _int_row("n_patients", entry["n_patients"], 1)
        )
        cohorts.append(
            CohortSpec(
                cohort_id,
                None if prior is None else _resolve(base, prior, "a cohort prior"),
                size,
            )
        )
    if len({c.id for c in cohorts}) != len(cohorts):
        raise BenchmarkConfigError(f"{target}: a cohort id is listed twice")
    labelling = document["labelling"]
    if (
        not isinstance(labelling, Mapping)
        or set(labelling) != {"mode"}
        or labelling["mode"] not in MODES
    ):
        raise BenchmarkConfigError(
            f"{target}: labelling needs exactly mode, one of {list(MODES)}"
        )
    profile = document["device_profile"]
    if not isinstance(profile, Mapping) or set(profile) != {
        "dispenser_content_sensing",
        "authenticating_devices",
    }:
        raise BenchmarkConfigError(
            f"{target}: device_profile needs dispenser_content_sensing and authenticating_devices"
        )
    sensing, devices = (
        profile["dispenser_content_sensing"],
        profile["authenticating_devices"],
    )
    if (
        not isinstance(sensing, bool)
        or not isinstance(devices, list)
        or not all(isinstance(d, str) and d in vocab.BLE_DEVICES for d in devices)
    ):
        raise BenchmarkConfigError(
            f"{target}: dispenser_content_sensing is a bool, authenticating_devices a list of {list(vocab.BLE_DEVICES)}"
        )
    if not isinstance(document["allow_no_segments"], bool):
        raise BenchmarkConfigError(f"{target}: allow_no_segments must be a bool")
    confounders = document["confounders"]
    if not isinstance(confounders, Mapping) or set(confounders) != {"variants"}:
        raise BenchmarkConfigError(
            f"{target}: confounders needs exactly variants (a list or null)"
        )
    variants = confounders["variants"]
    if variants is not None and (
        not isinstance(variants, list) or not all(isinstance(v, str) for v in variants)
    ):
        raise BenchmarkConfigError(
            f"{target}: confounders.variants must be null or a list of ids"
        )
    for key in ("benchmark_version", "pathway_template_id"):
        _safe_id(key, document[key])
    return BenchmarkConfig(
        path=target,
        benchmark_version=document["benchmark_version"],
        pathway_template_id=document["pathway_template_id"],
        generation_seed=seed,
        n_patients=n_patients,
        n_days=n_days,
        cohorts=tuple(cohorts),
        split_fractions=dict(fractions),
        monitor_step_ms=step,
        monitor_reorder_delay_ms=reorder,
        labelling_mode=labelling["mode"],
        registry_path=_resolve(base, paths["registry"], "paths.registry"),
        generator_design_path=_resolve(
            base, paths["generator_design"], "paths.generator_design"
        ),
        care_plans_path=_resolve(base, paths["care_plans"], "paths.care_plans"),
        injections_path=_resolve(base, paths["injections"], "paths.injections"),
        segments_path=_resolve(base, paths["segments"], "paths.segments"),
        arrival_jitter_path=None
        if jitter is None
        else _resolve(base, jitter, "paths.arrival_jitter"),
        dispenser_content_sensing=sensing,
        authenticating_devices=tuple(devices),
        allow_no_segments=document["allow_no_segments"],
        confounder_variants=None if variants is None else tuple(variants),
        rows=parsed.rows,
    )


# ---------------------------------------------------------------------------------------------------
# Care-plan files
# ---------------------------------------------------------------------------------------------------


def _plan_relpath(care_plan_id: str) -> str:
    return f"{PLANS_DIR}/{_safe_id('care_plan_id', care_plan_id)}.json"


def _plan_to_json(plan: CarePlan) -> dict[str, JsonValue]:
    instances: list[JsonValue] = []
    for item in plan.instances:
        instances.append(
            {
                "template": item.template.value,
                "instance_key": item.instance_key,
                "param_values": {k: float(v) for k, v in item.param_values.items()},
                "anchor_ms": item.anchor_ms,
            }
        )
    return {
        "care_plan_id": plan.care_plan_id,
        "pathway_template_id": plan.pathway_template_id,
        "patient_id": plan.patient_id,
        "registry_version": plan.registry_version,
        "plan_version": plan.plan_version,
        "signature": plan.signature,
        "schedule": [int(t) for t in plan.schedule],
        "instances": instances,
    }


def write_care_plan(root: Path, plan: CarePlan) -> Path:
    """Write ``plans/<care_plan_id>.json`` (canonical JSON) and return the path."""
    path = root / _plan_relpath(plan.care_plan_id)
    _write_json(path, _plan_to_json(plan))
    return path


def read_care_plan(root: Path, care_plan_id: str) -> CarePlan:
    """The ``CarePlan`` of ``plans/<care_plan_id>.json``. ``KeyError`` if there is no such plan."""
    path = root / _plan_relpath(care_plan_id)
    if not path.is_file():
        raise KeyError(f"no care plan {care_plan_id!r} in {root}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        instances = tuple(
            TemplateInstance(
                TemplateId(item["template"]),
                item["instance_key"],
                {k: float(v) for k, v in item["param_values"].items()},
                item["anchor_ms"],
            )
            for item in document["instances"]
        )
        return CarePlan(
            document["care_plan_id"],
            document["pathway_template_id"],
            document["patient_id"],
            document["registry_version"],
            instances,
            tuple(document["schedule"]),
            document["plan_version"],
            document["signature"],
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise TraceError(f"{path} is not a care plan file: {exc}") from exc


# ---------------------------------------------------------------------------------------------------
# What a build produces in memory
# ---------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PatientInjections:
    """A hand-written injection plan for one patient (tests and reproductions); it replaces the random plan.

    ``c1`` is the C1 spec list of the whole record, ``forced_slots`` the scenario controls of the adherence chain,
    ``c2`` and ``c3`` map a day index to the observation-side specs of that day.
    """

    c1: tuple[InjectionSpec, ...] = ()
    forced_slots: tuple[ForcedSlot, ...] = ()
    c2: Mapping[int, tuple[InjectionSpec, ...]] = field(default_factory=dict)
    c3: Mapping[int, tuple[InjectionSpec, ...]] = field(default_factory=dict)


@dataclass(slots=True)
class BuiltDay:
    """One generated day: the observed file content, the truth file content and the baseline sidecar."""

    observed: ObservedDay
    truth: TruthRecord
    baseline_sbp_mmhg: tuple[float, ...]
    tail: bool


@dataclass(slots=True)
class BuiltPatient:
    """A generated patient: its days (the last one is the tail day), its care plan and the manifest extras."""

    patient_id: str
    patient_index: int
    cohort: str
    role: str
    params: PatientParams
    plan: CarePlan
    days: tuple[BuiltDay, ...]
    n_scored_days: int
    extra: dict[str, JsonValue] = field(default_factory=dict)
    disabled_subtypes: frozenset[str] = frozenset()
    skipped: Counter[str] = field(default_factory=Counter)


# ---------------------------------------------------------------------------------------------------
# The build context: everything loaded once
# ---------------------------------------------------------------------------------------------------


@dataclass(slots=True)
class _Cohort:
    id: str
    prior: PriorSource
    adherence: AdherenceModel
    assembly: AssemblyConfig
    errors: DeviceErrorModel


@dataclass(frozen=True, slots=True)
class _Design:
    """The injection design: the sections of ``injections.yaml`` and the rows of the plan."""

    c1: Mapping[str, SubtypeDesign]
    c2: Mapping[str, SubtypeDesign]
    c3: Mapping[str, SubtypeDesign]
    rate_c1: float
    rate_c2: float
    rate_c3: float
    pairs_per_variant: int
    hr_bounds_bpm: tuple[float, float]
    nominal_bounce_gap_ms: int
    variants: Mapping[str, tuple[Variant, ...]]


def _row_value(rows: Mapping[str, ParameterRow], name: str) -> Any:
    row = rows.get(name)
    if row is None:
        raise BenchmarkConfigError(f"the design row {name!r} is missing")
    if not row.filled:
        raise UnfilledParameterError(f"parameter {name} is awaiting_human_value")
    return row.value


def _prior_flags(prior: PriorSource) -> tuple[bool, tuple[str, ...], int]:
    """``(fixture_only, unfilled names, number of unverified rows)`` of a prior.

    These accessors exist on ``LiteraturePriorSource`` only, not on the ``PriorSource`` protocol (ADR-038 G10):
    a prior without them is read through ``provenance()`` (every row without ``verified_by`` is unverified).
    """
    fixture = bool(getattr(prior, "fixture_only", False))
    unfilled = getattr(prior, "unfilled_names", None)
    names = tuple(unfilled()) if callable(unfilled) else ()
    unverified = getattr(prior, "unverified_names", None)
    if callable(unverified):
        count = len(tuple(unverified()))
    else:
        count = sum(1 for p in prior.provenance() if p.verified_by is None)
    return fixture, names, count


class BuildContext:
    """Everything a build needs, loaded once: the registry, the designs, the models and the named streams.

    ``BuildContext.create`` refuses a prior or design with unfilled rows (``UnfilledParameterError``) and a
    fixture-only input without ``allow_fixture_only`` (``FixtureOnlyPriorError``, ``RegistryError``).
    """

    def __init__(self) -> None:  # use create()
        raise TypeError("use BuildContext.create")

    config: BenchmarkConfig
    allow_fixture_only: bool

    @classmethod
    def create(
        cls,
        config: BenchmarkConfig | str | Path,
        prior: PriorSource | Mapping[str, PriorSource] | None = None,
        *,
        allow_fixture_only: bool = False,
    ) -> BuildContext:
        self = object.__new__(cls)
        self._init(config, prior, allow_fixture_only)
        return self

    def _init(
        self,
        config: BenchmarkConfig | str | Path,
        prior: PriorSource | Mapping[str, PriorSource] | None,
        allow_fixture_only: bool,
    ) -> None:
        if not isinstance(config, BenchmarkConfig):
            config = load_config(config)
        if not isinstance(allow_fixture_only, bool):
            raise BenchmarkConfigError("allow_fixture_only must be a bool")
        self.config = config
        self.allow_fixture_only = allow_fixture_only
        priors = self._normalise_priors(prior)
        # provenance of the priors first: fixture-only, then unfilled rows (both name what is wrong)
        self.fixture_only = False
        n_unverified_prior = 0
        unfilled: list[str] = []
        for cohort in config.cohorts:
            fixture, names, unverified = _prior_flags(priors[cohort.id])
            if fixture and not allow_fixture_only:
                raise FixtureOnlyPriorError(
                    f"the prior of cohort {cohort.id!r} is fixture-only (arithmetic test numbers, no source); "
                    "pass allow_fixture_only=True only in tests"
                )
            self.fixture_only = self.fixture_only or fixture
            unfilled += [
                f"{cohort.id}:{n}" if len(config.cohorts) > 1 else n for n in names
            ]
            n_unverified_prior += unverified
        if unfilled:
            raise UnfilledParameterError(
                f"parameter(s) {', '.join(sorted(unfilled))} of the prior are awaiting_human_value: "
                "a human supplies the value and its source_ref"
            )
        # the design files: unfilled rows refuse the build, fixture rows need the flag
        design_rows: list[ParameterRow] = list(config.rows)
        for path in (
            config.generator_design_path,
            config.care_plans_path,
            config.injections_path,
        ):
            try:
                design_rows += list(load_design_file(path).rows)
            except PriorConfigError as exc:
                raise BenchmarkConfigError(str(exc)) from exc
        awaiting = [r.parameter for r in design_rows if not r.filled]
        if awaiting:
            raise UnfilledParameterError(
                f"design parameter(s) {', '.join(sorted(awaiting))} are awaiting_human_value: "
                "a human supplies the value and its source_ref"
            )
        design_fixture = [
            r.parameter
            for r in design_rows
            if (r.source_ref or "").startswith("FIXTURE-ONLY")
        ]
        if design_fixture and not allow_fixture_only:
            raise FixtureOnlyPriorError(
                f"design row(s) {', '.join(sorted(design_fixture))} are fixture-only: pass allow_fixture_only=True only in tests"
            )
        self.fixture_only = self.fixture_only or bool(design_fixture)
        self.n_unverified_prior = n_unverified_prior
        self.n_unverified_design = sum(1 for r in design_rows if r.verified_by is None)
        self.design_sha256 = {
            "care_plans": file_sha256(config.care_plans_path),
            "generator_design": file_sha256(config.generator_design_path),
            "injections": file_sha256(config.injections_path),
        }
        if config.path is not None:
            self.design_sha256["config"] = file_sha256(config.path)
        self.prior_sha256: dict[str, str] = {}
        for spec in config.cohorts:
            prior_path = getattr(priors[spec.id], "path", None)
            if isinstance(prior_path, Path) and prior_path.is_file():
                self.prior_sha256[spec.id] = file_sha256(prior_path)
        try:
            self.registry = load_registry(
                config.registry_path,
                step_ms=config.monitor_step_ms,
                allow_fixture_only=allow_fixture_only,
            )
            self.templates = load_templates(registry=self.registry)
        except RegistryError as exc:
            # a registry with FIXTURE-ONLY rows is a provenance problem (ADR-027), anything else a configuration one
            if "FIXTURE-ONLY" in str(exc):
                raise FixtureOnlyPriorError(str(exc)) from exc
            raise BenchmarkConfigError(f"the registry cannot be used: {exc}") from exc
        self.fixture_only = self.fixture_only or bool(self.registry.fixture_only)
        windows = self._windows()
        try:
            self.schedule: Schedule = load_schedule(config.care_plans_path, **windows)
        except ScheduleError as exc:
            raise BenchmarkConfigError(
                f"the care-plan schedule is not feasible: {exc}"
            ) from exc
        problems = check_schedule_consistency(self.schedule, **windows)
        if problems:
            raise BenchmarkConfigError(
                "the schedule is not consistent with the registry windows: "
                + "; ".join(f"{p.check}: {p.message}" for p in problems)
            )
        self.monitor_config = MonitorConfig(
            config.monitor_step_ms,
            config.monitor_reorder_delay_ms,
            False,
            None,
            "likely",
            self.registry.version(),
        )
        self.mode = config.labelling_mode
        self.history_days = self._history_days()
        inflation_min = int(self.registry.get("cuff_inflation_min").value)
        self.measurement: MeasurementDesign = load_measurement_design(
            config.generator_design_path, inflation_min_ms=inflation_min
        )
        adherence_config = load_adherence_config(config.generator_design_path)
        peak = load_filled_rows(
            config.generator_design_path, ("circadian_peak_clock_ms",)
        )["circadian_peak_clock_ms"]
        self.cohorts: dict[str, _Cohort] = {}
        for spec in config.cohorts:
            cohort_prior = priors[spec.id]
            reference = getattr(cohort_prior, "reference_step_ms", None)
            if not callable(reference):
                raise BenchmarkConfigError(
                    "the prior must offer reference_step_ms(name) (the sampling step of ar_noise_phi)"
                )
            model = AdherenceModel(cohort_prior.adherence(), adherence_config)
            self.cohorts[spec.id] = _Cohort(
                spec.id,
                cohort_prior,
                model,
                AssemblyConfig(
                    latent_step_ms=config.latent_step_ms,
                    circadian_peak_clock_ms=int(peak),
                    ar_reference_step_ms=int(reference("ar_noise_phi")),
                    adherence=model,
                    vitals=self.measurement,
                    allow_no_segments=config.allow_no_segments,
                ),
                cohort_prior.device_errors(),
            )
        try:
            self.library = SegmentLibrary(
                config.segments_path,
                SegmentIndex.from_file(config.segments_path / "index.json"),
            )
        except SegmentError as exc:
            raise BenchmarkConfigError(
                f"the segment library cannot be used: {exc}"
            ) from exc
        self.jitter: ArrivalJitterModel = (
            NoJitter()
            if config.arrival_jitter_path is None
            else EmpiricalJitter(config.arrival_jitter_path)
        )
        self.response_model = OneCompartmentEmax()
        self.design = self._load_design()
        self._check_reading_rows()
        self.excluded_zero_levels()  # refuses a magnitude block with no drawable level, before any draw
        self.sched_window_ms = windows["sched_window_ms"]
        bounds = self.registry.bounds("bp")
        self.bp_bounds = (float(bounds.lower), float(bounds.upper))
        self.hold_threshold = float(self.registry.get("bp_hold_threshold").value)
        self.scale_range = float(self.registry.get("scale_range").value)
        self.record_values = {
            template: {name: float(self.registry.get(name).value) for name in names}
            for template, _, names in _RECORD_PARAMS
        }

    # -- loading ---------------------------------------------------------------------------------

    def _normalise_priors(
        self, prior: PriorSource | Mapping[str, PriorSource] | None
    ) -> dict[str, PriorSource]:
        from ralmon.benchmark.priors import LiteraturePriorSource

        config = self.config
        ids = [c.id for c in config.cohorts]
        if prior is None:
            out: dict[str, PriorSource] = {}
            for spec in config.cohorts:
                if spec.prior is None:
                    raise BenchmarkConfigError(
                        f"cohort {spec.id!r} names no prior file and none was passed"
                    )
                out[spec.id] = LiteraturePriorSource(
                    spec.prior, strict=False, allow_fixture_only=self.allow_fixture_only
                )
            return out
        if isinstance(prior, Mapping):
            if set(prior) != set(ids):
                raise BenchmarkConfigError(
                    f"the priors must be given for exactly the cohorts {ids}"
                )
            return dict(prior)
        if len(ids) != 1:
            raise BenchmarkConfigError(
                f"one prior was given for {len(ids)} cohorts: pass a mapping"
            )
        return {ids[0]: prior}

    def _windows(self) -> dict[str, int]:
        get = self.registry.get
        return {
            "hold_lookback_ms": int(get("hold_lookback").value),
            "delta1_ms": int(get("delta1").value),
            "delta2_ms": int(get("delta2").value),
            "sched_window_ms": int(get("sched_window").value),
        }

    def _history_days(self) -> int:
        """Days of history for the labeller: H = max(T_day, largest window parameter), at least one day."""
        longest = T_DAY_MS
        for name in _WINDOW_NAMES:
            try:
                longest = max(longest, int(self.registry.get(name).value))
            except (RegistryError, KeyError):
                continue
        return max(1, -(-longest // T_DAY_MS))

    def _check_reading_rows(self) -> None:
        """A duration in readings cannot exceed the readings of the day (the schedule's measurement ticks)."""
        n_readings = len(self.schedule.measurement_ticks_ms)
        for subtype in ANCHORED_SUBTYPES:
            entry = self.design.c2[subtype]
            assert entry.duration is not None and entry.duration.unit == READINGS_UNIT
            for level in entry.duration.levels:
                if level.value is not None and level.value > n_readings:
                    raise BenchmarkConfigError(
                        f"row {level.name!r} asks for {level.value:g} consecutive readings but the schedule "
                        f"has {n_readings} readings a day: a window of {subtype} cannot cover more"
                    )

    def excluded_zero_levels(self) -> dict[str, dict[str, list[str]]]:
        """Per cohort and C2 subtype, the magnitude levels the plan does not draw because they resolve to zero."""
        out: dict[str, dict[str, list[str]]] = {}
        for cohort_id, cohort in self.cohorts.items():
            per_subtype: dict[str, list[str]] = {}
            for subtype in _C2_DRIVEN:
                entry = self.design.c2[subtype]
                if entry.duration is None or entry.magnitude is None:
                    continue
                _, excluded = drawable_magnitude_levels(entry.magnitude, cohort.errors)
                if excluded:
                    per_subtype[subtype] = list(excluded)
            out[cohort_id] = per_subtype
        return out

    def _load_design(self) -> _Design:
        config = self.config
        path = config.injections_path
        try:
            c1 = load_c1_design(path)
            c2 = load_injection_design(path, section="c2")
            c3 = load_injection_design(path, section="c3")
            variants = load_confounder_design(path)
        except InjectionError as exc:
            raise BenchmarkConfigError(
                f"the injection design cannot be used: {exc}"
            ) from exc
        rows = {r.parameter: r for r in load_design_file(path).rows}
        lower = float(_row_value(rows, "injection_naive_pulse_lower_bpm"))
        upper = float(_row_value(rows, "injection_naive_pulse_upper_bpm"))
        bounce = c2["dispenser_bounce"].magnitude
        assert bounce is not None
        nominal = next(lv for lv in bounce.levels if lv.level == "nominal")
        if nominal.value is None:
            raise UnfilledParameterError(
                f"parameter {nominal.name} is awaiting_human_value"
            )
        selected = config.confounder_variants
        if selected is not None:
            known = {v.variant_id for group in variants.values() for v in group}
            if not set(selected) <= known:
                raise BenchmarkConfigError(
                    f"unknown confounder variants {sorted(set(selected) - known)}"
                )
        return _Design(
            c1=c1,
            c2=c2,
            c3=c3,
            rate_c1=float(_row_value(rows, "injection_rate_c1")),
            rate_c2=float(_row_value(rows, "injection_rate_c2")),
            rate_c3=float(_row_value(rows, "injection_rate_c3")),
            pairs_per_variant=_int_row(
                "confounder_pairs_per_variant",
                _row_value(rows, "confounder_pairs_per_variant"),
                0,
            ),
            hr_bounds_bpm=(lower, upper),
            nominal_bounce_gap_ms=int(nominal.value),
            variants=variants,
        )

    # -- patients --------------------------------------------------------------------------------

    @property
    def n_total_days(self) -> int:
        """Generated days per virtual patient: the scored days and the tail day (ADR-066)."""
        return self.config.n_days + 1

    def patient_units(self) -> list[tuple[str, int, str]]:
        """``(patient_id, patient_index, cohort_id)`` of every virtual patient, in build order."""
        units: list[tuple[str, int, str]] = []
        index = 0
        for spec in self.config.cohorts:
            for _ in range(spec.n_patients):
                units.append((self._label(index, spec.id), index, spec.id))
                index += 1
        return units

    def _numbers(self) -> list[int]:
        """The id numbers of all patients, virtual and twin, in one permutation drawn from the seed.

        An id carries no role: a twin has the shape of a virtual patient (``p0042``), twin ids are not larger than
        virtual ones, and member A is the lower number of its pair in about half of the pairs. The mapping from an id
        to its role is in the manifest and the truth side only.
        """
        cached: list[int] | None = getattr(self, "_number_cache", None)
        if cached is None:
            total = self.config.total_patients + 2 * len(self.pair_units())
            order = stream(
                self.config.generation_seed, 0, None, StreamPurpose.PATIENT, 1
            ).permutation(total)
            cached = [int(x) for x in order]
            self._number_cache = cached
        return cached

    def _label(self, slot: int, cohort_id: str) -> str:
        label = f"p{self._numbers()[slot]:04d}"
        return f"{cohort_id}-{label}" if len(self.config.cohorts) > 1 else label

    def planned_ids(self) -> tuple[list[str], list[tuple[str, str]]]:
        """The patient ids of the build: the virtual patients, and the ``(A, B)`` ids of every pair."""
        virtual = [pid for pid, _, _ in self.patient_units()]
        first = self.config.cohorts[0].id
        base = self.config.total_patients
        members = [
            (self._label(base + 2 * k, first), self._label(base + 2 * k + 1, first))
            for k in range(len(self.pair_units()))
        ]
        return virtual, members

    def draw_patient(
        self, patient_index: int, cohort: str | None = None
    ) -> PatientParams:
        """The patient of ``patient_index`` from the prior of its cohort (stream ``PATIENT``)."""
        cohort_id = cohort if cohort is not None else self.config.cohorts[0].id
        rng = stream(
            self.config.generation_seed, patient_index, None, StreamPurpose.PATIENT
        )
        params = self.cohorts[cohort_id].prior.sample_patient(rng, patient_index)
        return dataclasses.replace(
            params, patient_id=self._label(patient_index, cohort_id)
        )

    def make_plan(self, patient_id: str, n_days: int) -> CarePlan:
        """The care plan of the whole record: SCHED per tick, day-end COUNT per day, and the B1 records."""
        instances: list[TemplateInstance] = [
            TemplateInstance(template, key, dict(self.record_values[template]), None)
            for template, key, _ in _RECORD_PARAMS
        ]
        ticks: list[int] = []
        for day in range(n_days):
            base = day * T_DAY_MS
            for tick in self.schedule.measurement_ticks_ms:
                instances.append(
                    TemplateInstance(
                        TemplateId.SCHED, f"sched@{base + tick}", {}, base + tick
                    )
                )
            instances.append(
                TemplateInstance(
                    TemplateId.COUNT, f"count@{base + T_DAY_MS}", {}, base + T_DAY_MS
                )
            )
            ticks += [
                base + t
                for t in (
                    *self.schedule.dose_ticks_ms,
                    *self.schedule.measurement_ticks_ms,
                )
            ]
        return CarePlan(
            f"plan-{patient_id}",
            self.config.pathway_template_id,
            patient_id,
            self.registry.version(),
            tuple(instances),
            tuple(sorted(ticks)),
            1,
            None,
        )

    # -- the injection plan ----------------------------------------------------------------------

    def _plan_rng(
        self, patient_index: int, day: int | None, *parts: str | int
    ) -> np.random.Generator:
        return stream(
            self.config.generation_seed,
            patient_index,
            day,
            StreamPurpose.INJECTION_PLAN,
            stable_index("plan", *parts),
        )

    def _pick(self, rng: np.random.Generator, items: Sequence[Any]) -> Any:
        return items[int(rng.integers(0, len(items)))]

    def _window(
        self, rng: np.random.Generator, day: int, levels: Sequence[LevelRow]
    ) -> tuple[int, int, LevelRow] | None:
        """``(onset, duration, level)`` of a window inside the day, on the latent grid; None if none fits."""
        level = self._pick(rng, levels)
        assert level.value is not None
        duration = round(level.value)
        step = self.config.latent_step_ms
        if duration < 1 or duration > T_DAY_MS:
            return None
        positions = (T_DAY_MS - duration) // step + 1
        onset = day * T_DAY_MS + step * int(rng.integers(0, positions))
        return onset, duration, level

    def _anchored_window(
        self,
        rng: np.random.Generator,
        day: int,
        levels: Sequence[LevelRow],
        readings: Sequence[int],
    ) -> tuple[int, int, LevelRow] | None:
        """``(onset, duration, level)`` of a window of ``k`` consecutive readings of the day (ADR-070 (a)).

        The level of the duration block gives ``k`` (rows in the unit ``readings``). None when the day has
        fewer than ``k`` readings (a C1 refusal removed some) or no grid instant fits.
        """
        level = self._pick(rng, levels)
        assert level.value is not None
        choices = anchored_choices(
            readings,
            int(level.value),
            step_ms=self.config.latent_step_ms,
            day_start_ms=day * T_DAY_MS,
            day_end_ms=(day + 1) * T_DAY_MS,
        )
        if not choices:
            return None
        onset, end, _ = draw_anchored_window(rng, choices)
        return onset, end - onset, level

    def plan_c1(
        self,
        patient: PatientParams,
        patient_index: int,
        n_days: int,
        skipped: Counter[str],
    ) -> tuple[InjectionSpec, ...]:
        """The C1 specs of the whole record (the same list goes to every day's latent assembly)."""
        design = self.design
        specs: list[InjectionSpec] = []
        taken: dict[str, list[tuple[int, int]]] = {}
        seen_points: set[tuple[str, int]] = set()
        order = sorted(C1_SUBTYPES)
        for day in range(n_days):
            count = int(
                self._plan_rng(patient_index, day, "c1", "count").poisson(
                    design.rate_c1
                )
            )
            for k in range(count):
                rng = self._plan_rng(patient_index, day, "c1", k)
                subtype = self._pick(rng, order)
                try:
                    spec = self._c1_spec(subtype, rng, day, patient)
                except C1InjectionError:
                    skipped[f"c1/{subtype}/no_reference"] += 1
                    continue
                if spec is None:
                    skipped[f"c1/{subtype}/no_position"] += 1
                    continue
                if spec.duration_ms is not None:
                    span = (spec.onset_ms, spec.onset_ms + spec.duration_ms)
                    if any(
                        span[0] < b and a < span[1] for a, b in taken.get(subtype, [])
                    ):
                        skipped[f"c1/{subtype}/overlap"] += 1
                        continue
                    taken.setdefault(subtype, []).append(span)
                else:
                    if (subtype, spec.onset_ms) in seen_points:
                        skipped[f"c1/{subtype}/same_tick"] += 1
                        continue
                    seen_points.add((subtype, spec.onset_ms))
                specs.append(spec)
        return tuple(specs)

    def _c1_spec(
        self, subtype: str, rng: np.random.Generator, day: int, patient: PatientParams
    ) -> InjectionSpec | None:
        entry = self.design.c1[subtype]
        if (
            entry.duration is None
        ):  # a tick of the schedule: refusal (measurement) or double take (dose)
            ticks = (
                self.schedule.measurement_ticks_ms
                if subtype == "measurement_refusal"
                else self.schedule.dose_ticks_ms
            )
            if not ticks:
                return None
            return c1_spec(subtype, day * T_DAY_MS + int(self._pick(rng, ticks)))
        drawn = self._window(rng, day, entry.duration.levels)
        assert entry.magnitude is not None
        if drawn is None:
            return None
        onset, duration, _ = drawn
        magnitude = self._pick(rng, entry.magnitude.levels)
        reference: float | None = None
        if magnitude.reference == "scale_range":
            reference = self.scale_range
        elif magnitude.reference == "baseline_to_hold_distance":
            reference = hold_distance_mmhg(
                patient.baseline_sbp_mmhg, self.hold_threshold
            )
        return c1_spec_from_level(
            subtype, onset, magnitude, reference, duration_ms=duration
        )

    def plan_observation(
        self,
        cohort: _Cohort,
        patient_index: int,
        day: int,
        latent: LatentResult,
        stream_: ObservedStream,
        skipped: Counter[str],
    ) -> tuple[InjectionSpec, ...]:
        """The C2 and C3 specs of one day, drawn once the latent day and the base stream exist."""
        specs: list[InjectionSpec] = []
        windows: dict[tuple[str, str], list[tuple[int, int]]] = {}

        def add_window(spec: InjectionSpec, group: str, target: str) -> bool:
            assert spec.duration_ms is not None
            span = (spec.onset_ms, spec.onset_ms + spec.duration_ms)
            if any(
                span[0] < b and a < span[1] for a, b in windows.get((group, target), [])
            ):
                skipped[f"{spec.cls.value.lower()}/{spec.subtype}/overlap"] += 1
                return False
            windows.setdefault((group, target), []).append(span)
            specs.append(spec)
            return True

        design = self.design
        errors = cohort.errors
        # ble_dropout: the rate per device-hour of the prior, one stream of windows per device
        entry = design.c2["ble_dropout"]
        assert entry.duration is not None
        for device in vocab.BLE_DEVICES:
            mean = errors.ble_dropout_rate_per_h * _hours_per_day()
            rng = self._plan_rng(patient_index, day, "ble_dropout", device)
            for _ in range(int(rng.poisson(mean))):
                drawn = self._window(rng, day, entry.duration.levels)
                if drawn is None:
                    continue
                onset, duration, level = drawn
                add_window(
                    InjectionSpec(
                        InjectedClass.C2, "ble_dropout", onset, duration,
                        params={"target": device}, level=level.level,
                    ),
                    "ble_dropout", device,
                )  # fmt: skip
        # dispenser_bounce: one draw per true dispense with the probability of the prior
        dispenses = sorted(
            e.t_device_ms for e in latent.latent.events if e.kind is EventKind.DISPENSE
        )
        specs += plan_dispenser_bounces(
            dispenses, errors.dispenser_bounce_prob, design.nominal_bounce_gap_ms,
            seed=self.config.generation_seed, patient_index=patient_index, day_index=day,
        )  # fmt: skip
        robot_used: set[tuple[str, int]] = set()
        day_start, day_end = day * T_DAY_MS, (day + 1) * T_DAY_MS
        readings = [t for t in stream_readings(stream_) if day_start <= t < day_end]
        # the class rates
        for cls_name, rate, subtypes, section in (
            ("c2", design.rate_c2, _C2_DRIVEN, design.c2),
            ("c3", design.rate_c3, _C3_ORDER, design.c3),
        ):
            count = int(
                self._plan_rng(patient_index, day, cls_name, "count").poisson(rate)
            )
            for k in range(count):
                rng = self._plan_rng(patient_index, day, cls_name, k)
                subtype = self._pick(rng, subtypes)
                if cls_name == "c2" and subtype == "stuck_at" and day == 0:
                    # the first scored day has no previous evening whose last reading a stuck cuff could
                    # repeat (ADR-070 (d)): excluded from the draw, counted, not left to be unrealised
                    skipped["c2/stuck_at/first_day"] += 1
                    continue
                if cls_name == "c2":
                    spec = self._c2_spec(
                        subtype,
                        rng,
                        day,
                        section[subtype],
                        cohort,
                        robot_used,
                        readings,
                    )
                else:
                    spec = self._c3_spec(subtype, rng, day, section[subtype], stream_)
                if spec is None:
                    if subtype == "replay" and day == 0:
                        reason = "first_day"
                    elif subtype in ANCHORED_SUBTYPES and cls_name == "c2":
                        reason = "too_few_readings"
                    else:
                        reason = "no_position"
                    skipped[f"{cls_name}/{subtype}/{reason}"] += 1
                    continue
                if spec.duration_ms is not None:
                    group = (
                        "cuff_attacks"
                        if spec.subtype in _CUFF_ATTACKS
                        else spec.subtype
                    )
                    target = str(
                        spec.params.get(
                            "target",
                            "cuff" if group == "cuff_attacks" else spec.subtype,
                        )
                    )
                    if not add_window(spec, group, target):
                        continue
                else:
                    if any(
                        s.subtype == spec.subtype
                        and s.onset_ms == spec.onset_ms
                        and s.params == spec.params
                        for s in specs
                    ):
                        skipped[f"{cls_name}/{subtype}/same_instant"] += 1
                        continue
                    specs.append(spec)
        return tuple(specs)

    def _c2_spec(
        self,
        subtype: str,
        rng: np.random.Generator,
        day: int,
        entry: SubtypeDesign,
        cohort: _Cohort,
        robot_used: set[tuple[str, int]],
        readings: Sequence[int] = (),
    ) -> InjectionSpec | None:
        if entry.duration is not None:
            if subtype in ANCHORED_SUBTYPES:
                drawn = self._anchored_window(rng, day, entry.duration.levels, readings)
            else:
                drawn = self._window(rng, day, entry.duration.levels)
            if drawn is None:
                return None
            onset, duration, level = drawn
            magnitude: float | None = None
            unit: str | None = None
            label = level.level
            if entry.magnitude is not None:
                drawable, _ = drawable_magnitude_levels(entry.magnitude, cohort.errors)
                mag_level = self._pick(rng, drawable)
                assert mag_level.value is not None
                unit = entry.magnitude.unit
                if mag_level.reference is None:
                    magnitude = float(mag_level.value)
                else:
                    reference = _magnitude_references(cohort.errors)[
                        mag_level.reference
                    ]
                    magnitude = resolve_magnitude(
                        mag_level, reference, mag_level.reference
                    )
                    if (
                        mag_level.level != "device_bias"
                        and int(rng.integers(0, 2)) == 1
                    ):
                        magnitude = -magnitude  # the sign is drawn fairly
                label = mag_level.level
            return InjectionSpec(
                InjectedClass.C2, subtype, onset, duration, magnitude, unit, {}, label
            )
        # a per-tick robot fault: one tick of the day, a tick is used by one robot fault at most
        ticks = [
            (vocab.KIND_MEASUREMENT, t) for t in self.schedule.measurement_ticks_ms
        ]
        ticks += [(vocab.KIND_DOSE, t) for t in self.schedule.dose_ticks_ms]
        ticks = [kt for kt in ticks if (kt[0], kt[1]) not in robot_used]
        if not ticks:
            return None
        kind, tick = self._pick(rng, ticks)
        robot_used.add((kind, tick))
        params = {"target": vocab.SOURCE_ROBOT, "kind": kind}
        if subtype == "manipulation_failure":
            return InjectionSpec(
                InjectedClass.C2, subtype, day * T_DAY_MS + tick, params=params
            )
        assert entry.magnitude is not None
        level = self._pick(rng, entry.magnitude.levels)
        assert level.reference is not None
        delay = resolve_magnitude(level, float(self.sched_window_ms), level.reference)
        return InjectionSpec(
            InjectedClass.C2,
            subtype,
            day * T_DAY_MS + tick,
            None,
            delay,
            "ms",
            params,
            level.level,
        )

    def _c3_spec(
        self,
        subtype: str,
        rng: np.random.Generator,
        day: int,
        entry: SubtypeDesign,
        stream_: ObservedStream,
    ) -> InjectionSpec | None:
        step = self.config.latent_step_ms
        if subtype in _CUFF_ATTACKS:
            if subtype == "replay" and day == 0:
                return None  # a replay needs the cuff messages of the day before
            assert entry.duration is not None
            drawn = self._window(rng, day, entry.duration.levels)
            if drawn is None:
                return None
            onset, duration, _ = drawn
            attacker = (
                self._pick(rng, _ATTACKER_LEVELS) if subtype == "replay" else None
            )
            return InjectionSpec(
                InjectedClass.C3, subtype, onset, duration, level=attacker, params={}
            )  # the duration level is not an attacker level; the label is the attacker
        attacker = self._pick(rng, _ATTACKER_LEVELS)
        if subtype == "dispense_forgery":
            if attacker == "informed" and self.schedule.dose_ticks_ms:
                onset = day * T_DAY_MS + int(
                    self._pick(rng, self.schedule.dose_ticks_ms)
                )
            else:
                onset = day * T_DAY_MS + step * int(rng.integers(0, T_DAY_MS // step))
            return InjectionSpec(InjectedClass.C3, subtype, onset, level=attacker)
        # presence_spoof: an instant inside a robot visit
        if not stream_.visits:
            return None
        visit = self._pick(rng, stream_.visits)
        instant = visit.arrival_ms + int(
            rng.integers(0, visit.departure_ms - visit.arrival_ms + 1)
        )
        return InjectionSpec(
            InjectedClass.C3, subtype, instant, level=attacker,
            params={"spoof_intake": attacker == "informed"},
        )  # fmt: skip

    # -- one day of observation ------------------------------------------------------------------

    def _reports(self, visits: Sequence[RobotVisit]) -> list[Event]:
        """The robot ``NODE_STATE`` reports of a day: true at every arrival, false where the robot leaves."""
        events: list[Event] = []
        ordered = sorted(visits, key=lambda v: (v.arrival_ms, v.departure_ms))
        for visit in ordered:
            events.append(_report(visit.arrival_ms, True))
        end: int | None = None
        for visit in ordered:
            if end is not None and visit.arrival_ms > end:
                events.append(_report(end, False))
                end = None
            end = visit.departure_ms if end is None else max(end, visit.departure_ms)
        if end is not None:
            events.append(_report(end, False))
        return sorted(events, key=lambda e: e.t_rx_ms)

    def _with_reports(
        self, day: ObservedDay, visits: Sequence[RobotVisit]
    ) -> ObservedDay:
        reports = self._reports(visits)
        for event in reports:
            vocab.check_payload(event.kind, event.payload)
        merged = sorted([*day.events, *reports], key=lambda e: e.t_rx_ms)
        return dataclasses.replace(day, events=tuple(merged))

    def _observe_day(
        self,
        cohort: _Cohort,
        params: PatientParams,
        patient_index: int,
        care_plan_id: str,
        day: int,
        latent: LatentResult,
        specs: tuple[InjectionSpec, ...] | None,
        previous: ObservedStream | None,
        counters: tuple[int, int],
        *,
        content_sensing: bool,
        robot_present: bool = True,
        task_outcomes: bool = True,
        authenticating: tuple[str, ...] = (),
        skipped: Counter[str],
    ) -> tuple[
        ObservedDay, ObservedStream, tuple[InjectionRecord, ...], tuple[str, ...]
    ]:
        base = build_observed_base(
            latent.latent, self.schedule, care_plan_id, cohort.errors, self.measurement, self.jitter,
            self.library, self.config.generation_seed, patient_index,
            allow_no_segments=self.config.allow_no_segments,
            skip_measurement_ticks_ms=latent.refused_ticks_ms,
            dispenser_content_sensing=content_sensing,
        )  # fmt: skip
        stream_ = observe_refusals(base, latent.c1_records)
        if specs is None:
            specs = self.plan_observation(
                cohort, patient_index, day, latent, stream_, skipped
            )
        context = InjectionContext(
            patient_index,
            library=self.library,
            latent=latent.latent,
            task_deadline_offset_ms=self.sched_window_ms,
            dispenser_content_sensing=content_sensing,
            cuff_start=counters[0],
            dispenser_start=counters[1],
            previous_day=previous,
            bp_bounds_mmhg=self.bp_bounds,
            hr_bounds_bpm=self.design.hr_bounds_bpm,
            authenticating_devices=authenticating,
        )
        result = apply_observation_injections(stream_, specs, context)
        observed = finalize_observed(result.stream)
        observed = _withhold(observed, robot_present, task_outcomes)
        if robot_present:
            observed = self._with_reports(observed, result.stream.visits)
        # the readings the plan drew next to the ones the injector found after the robot stage (ADR-070 (b))
        records = annotate_reading_counts(result.records, stream_)
        return observed, result.stream, records, result.disabled_subtypes

    # -- patients --------------------------------------------------------------------------------

    def _label_and_collect(
        self,
        plan: CarePlan,
        days: Sequence[tuple[ObservedDay, LatentResult, tuple[InjectionRecord, ...]]],
        n_scored: int,
    ) -> list[BuiltDay]:
        """Label every day with the earlier days as history and write the sidecars (module docstring, step 6)."""
        built: list[BuiltDay] = []
        entries: list[list[dict[str, Any]]] = []
        for d, (observed, latent, records) in enumerate(days):
            history = [
                HistoryDay(days[k][1].latent, days[k][2], days[k][1].behaviour_log)
                for k in range(max(0, d - self.history_days), d)
            ]
            first_history = max(0, d - self.history_days)
            labelled = label_latent_day_detailed(
                latent.latent, plan, records, latent.behaviour_log, None, self.monitor_config, None,
                self.mode, registry=self.registry, templates=self.templates, history=history,
            )  # fmt: skip
            log = confounder_log(list(records))
            links: dict[int, list[int]] = {}
            for position, index in enumerate(labelled.record_index):
                if index is not None:
                    links.setdefault(index, []).append(position)
            day_entries: list[dict[str, Any]] = []
            for index, entry in enumerate(log):
                full = dict(entry)
                full["record_index"] = index
                full["truth_indices"] = links.get(index, [])
                full["explains_in_later_days"] = []
                day_entries.append(full)
            entries.append(day_entries)
            for position, link in enumerate(labelled.history_record_index):
                if link is not None:
                    earlier, record = link
                    entries[first_history + earlier][record][
                        "explains_in_later_days"
                    ].append({"day_index": observed.day_index, "truth_index": position})
            behaviour: list[JsonValue] = [
                cast(JsonValue, dict(b.to_json())) for b in latent.behaviour_log
            ]
            built.append(
                BuiltDay(
                    observed,
                    TruthRecord(latent.latent, labelled.events, day_entries, behaviour),  # type: ignore[arg-type]
                    tuple(float(x) for x in latent.baseline_sbp_mmhg),
                    d >= n_scored,
                )
            )
        return built

    def build_patient(
        self,
        params: PatientParams,
        patient_index: int,
        scripted: PatientInjections | None = None,
        *,
        cohort: str | None = None,
    ) -> BuiltPatient:
        """Generate one virtual patient: ``n_days`` scored days and the tail day (module docstring)."""
        cohort_id = cohort if cohort is not None else self.config.cohorts[0].id
        models = self.cohorts[cohort_id]
        n_total = self.n_total_days
        plan = self.make_plan(params.patient_id, n_total)
        skipped: Counter[str] = Counter()
        if scripted is None:
            c1 = self.plan_c1(params, patient_index, n_total, skipped)
            forced: tuple[ForcedSlot, ...] = ()
        else:
            c1, forced = scripted.c1, scripted.forced_slots
        latents: list[LatentResult] = []
        rows: list[tuple[ObservedDay, LatentResult, tuple[InjectionRecord, ...]]] = []
        disabled: set[str] = set()
        state = None
        previous: ObservedStream | None = None
        counters = (1, 1)
        for day in range(n_total):
            [latent] = assemble_latent_days(
                params, self.schedule, 1, list(c1), self.response_model, self.library,
                self.config.generation_seed, patient_index, config=models.assembly,
                start_day=day, state=state,
                forced_slots=[s for s in forced if s.day_index == day],
            )  # fmt: skip
            state = latent.end_state
            latents.append(latent)
            specs = None
            if scripted is not None:
                specs = (*scripted.c2.get(day, ()), *scripted.c3.get(day, ()))
            observed, stream_, records, off = self._observe_day(
                models, params, patient_index, plan.care_plan_id, day, latent, specs, previous, counters,
                content_sensing=self.config.dispenser_content_sensing,
                authenticating=self.config.authenticating_devices, skipped=skipped,
            )  # fmt: skip
            disabled.update(off)
            previous = stream_
            counters = _next_counters(stream_)
            rows.append((observed, latent, (*latent.c1_records, *records)))
        days = self._label_and_collect(plan, rows, self.config.n_days)
        return BuiltPatient(
            params.patient_id, patient_index, cohort_id, ROLE_PATIENT, params, plan, tuple(days),
            self.config.n_days, {}, frozenset(disabled), skipped,
        )  # fmt: skip

    # -- confounder pairs ------------------------------------------------------------------------

    def pair_units(self) -> list[tuple[str, str, Variant, int]]:
        """``(pair_id, group, variant, ordinal)`` of every pair, in build order."""
        out: list[tuple[str, str, Variant, int]] = []
        first = self.config.cohorts[0].id
        prefix = f"{first}-" if len(self.config.cohorts) > 1 else ""
        selected = self.config.confounder_variants
        count = 0
        for group in GROUPS:
            for variant in self.design.variants[group]:
                if selected is not None and variant.variant_id not in selected:
                    continue
                for k in range(self.design.pairs_per_variant):
                    out.append((f"{prefix}pair-{count:04d}", group, variant, k))
                    count += 1
        return out

    def pair_base(
        self, params: PatientParams, patient_index: int, ordinal: int
    ) -> PairBase:
        """The base of a pair member: the arguments the paired design shares (one dose and tick per ordinal)."""
        cohort = self.cohorts[self.config.cohorts[0].id]
        n_doses, n_ticks = (
            len(self.schedule.dose_ticks_ms),
            len(self.schedule.measurement_ticks_ms),
        )
        return PairBase(
            params, self.schedule, cohort.assembly, self.response_model, cohort.errors,
            self.measurement, self.jitter, self.library, f"plan-{params.patient_id}",
            self.config.generation_seed, patient_index,
            dose_index=ordinal % n_doses if n_doses else 0,
            measurement_index=ordinal % n_ticks if n_ticks else 0,
            nominal_bounce_gap_ms=self.design.nominal_bounce_gap_ms,
            task_deadline_offset_ms=self.sched_window_ms,
        )  # fmt: skip

    def build_pairs(
        self, first_index: int | None = None
    ) -> list[tuple[BuiltPatient, BuiltPatient]]:
        """All confounder twin pairs (``build_pair`` for every unit of ``pair_units``)."""
        start = self.config.total_patients if first_index is None else first_index
        return [
            self.build_pair(pair_id, group, variant, start + number, ordinal)
            for number, (pair_id, group, variant, ordinal) in enumerate(
                self.pair_units()
            )
        ]

    def build_pair(
        self,
        pair_id: str,
        group: str,
        variant: Variant,
        patient_index: int,
        ordinal: int,
    ) -> tuple[BuiltPatient, BuiltPatient]:
        """Two single-day twin patients that share everything but the mechanism, and their tail days."""
        cohort = self.cohorts[self.config.cohorts[0].id]
        shared = cohort.prior.sample_patient(
            stream(
                self.config.generation_seed, patient_index, None, StreamPurpose.PATIENT
            ),
            patient_index,
        )
        number = patient_index - self.config.total_patients
        ids = dict(zip(("A", "B"), self.planned_ids()[1][number], strict=True))

        def base_for(member: str) -> PairBase:
            return self.pair_base(
                dataclasses.replace(shared, patient_id=ids[member]),
                patient_index,
                ordinal,
            )

        flag = evaluate_pair(
            group, variant, base_for("A")
        ).indistinguishable_by_construction
        built: list[BuiltPatient] = []
        for member in ("A", "B"):
            base = base_for(member)
            scenarios = dict(
                zip(
                    ("A", "B"), build_confounder_pair(group, variant, base), strict=True
                )
            )
            scenario = scenarios[member]
            realised = realise_scenario(scenario, base)
            records = tuple(
                dataclasses.replace(
                    r,
                    details={
                        **r.details,
                        "variant_id": variant.variant_id,
                        "indistinguishable_by_construction": flag,
                    },
                )
                for r in realised.records
            )
            built.append(
                self._finish_pair_member(
                    base, realised, records, member, pair_id, group, variant
                )
            )
        return built[0], built[1]

    def _finish_pair_member(
        self,
        base: PairBase,
        realised: RealisedScenario,
        records: tuple[InjectionRecord, ...],
        member: str,
        pair_id: str,
        group: str,
        variant: Variant,
    ) -> BuiltPatient:
        scenario = realised.scenario
        params = base.patient
        cohort_id = self.config.cohorts[0].id
        models = self.cohorts[cohort_id]
        plan = self.make_plan(params.patient_id, 2)
        skipped: Counter[str] = Counter()
        day0 = realised.observed
        if scenario.robot_present:
            day0 = self._with_reports(day0, realised.stream.visits)
        [tail] = assemble_latent_days(
            params, self.schedule, 1, list(scenario.c1_specs), self.response_model, self.library,
            self.config.generation_seed, base.patient_index, config=models.assembly, start_day=1,
            state=realised.latent.end_state,
        )  # fmt: skip
        counters = _next_counters(realised.stream)
        observed_tail, _, tail_records, _ = self._observe_day(
            models, params, base.patient_index, plan.care_plan_id, 1, tail, (), realised.stream, counters,
            content_sensing=scenario.content_sensing, robot_present=scenario.robot_present,
            task_outcomes=scenario.task_outcomes, authenticating=scenario.authenticating_devices,
            skipped=skipped,
        )  # fmt: skip
        rows = [
            (day0, realised.latent, records),
            (observed_tail, tail, (*tail.c1_records, *tail_records)),
        ]
        days = self._label_and_collect(plan, rows, 1)
        extra: dict[str, JsonValue] = {
            "role": ROLE_PAIR, "pair": pair_id, "member": member, "group": group,
            "variant_id": variant.variant_id, "mechanism": scenario.mechanism,
        }  # fmt: skip
        return BuiltPatient(
            params.patient_id, base.patient_index, cohort_id, ROLE_PAIR, params, plan, tuple(days), 1,
            extra, frozenset(), skipped,
        )  # fmt: skip

    # -- writing ---------------------------------------------------------------------------------

    def write(
        self,
        out_dir: str | Path,
        patients: Sequence[BuiltPatient],
        pairs: Sequence[tuple[BuiltPatient, BuiltPatient]],
        *,
        git_rev: str | None = None,
    ) -> Manifest:
        """Write already built patients and pairs, split them by patient, and write the manifest."""
        writer = _Writer(self, Path(out_dir))
        try:
            units = {p.patient_id: (p,) for p in patients}
            units.update({a.extra["pair"]: (a, b) for a, b in pairs})  # type: ignore[misc]
            split = split_patients(
                units, self.config.split_fractions, self.config.generation_seed
            )
            for unit_id, members in units.items():
                for built in members:
                    writer.add(built, split[unit_id])
            return writer.finish(git_rev)
        except BaseException:
            writer.abort()
            raise

    def generate(self, out_dir: str | Path, *, git_rev: str | None = None) -> Manifest:
        """Build and write every patient and pair, one unit at a time (the memory of one patient)."""
        writer = _Writer(self, Path(out_dir))
        try:
            singles = self.patient_units()
            pairs = self.pair_units()
            first_pair_index = self.config.total_patients
            ids = [p for p, _, _ in singles] + [pair_id for pair_id, _, _, _ in pairs]
            split = split_patients(
                ids, self.config.split_fractions, self.config.generation_seed
            )
            for patient_id, index, cohort_id in singles:
                params = self.draw_patient(index, cohort_id)
                writer.add(
                    self.build_patient(params, index, None, cohort=cohort_id),
                    split[patient_id],
                )
            for number, (pair_id, group, variant, ordinal) in enumerate(pairs):
                for built in self.build_pair(
                    pair_id, group, variant, first_pair_index + number, ordinal
                ):
                    writer.add(built, split[pair_id])
            return writer.finish(git_rev)
        except BaseException:
            writer.abort()
            raise


def _next_counters(stream_: ObservedStream) -> tuple[int, int]:
    """The first cuff and dispenser sequence numbers of the next day (the ``next_*`` of the day's settings)."""
    cuff, dispenser = (
        stream_.settings["next_cuff_seq"],
        stream_.settings["next_dispenser_seq"],
    )
    if not isinstance(cuff, int) or not isinstance(dispenser, int):
        raise BenchmarkConfigError("the stream settings carry no sequence counters")
    return cuff, dispenser


def _report(t: int, colocated: bool) -> Event:
    return Event(
        EventKind.NODE_STATE,
        t,
        t,
        vocab.SOURCE_ROBOT,
        {vocab.KEY_STATE: vocab.STATE_ACTIVE, vocab.KEY_COLOCATED: colocated},
        None,
    )


def _withhold(
    day: ObservedDay, robot_present: bool, task_outcomes: bool
) -> ObservedDay:
    """A variant without a robot has no robot sample and no robot event; one without outcomes has no task event."""
    if robot_present and task_outcomes:
        return day
    samples = day.samples
    events = day.events
    if not robot_present:
        samples = tuple(s for s in samples if s.signal != "presence")
        events = tuple(e for e in events if e.source != vocab.SOURCE_ROBOT)
    if not task_outcomes:
        events = tuple(e for e in events if e.kind is not EventKind.ROBOT_TASK)
    return dataclasses.replace(day, samples=tuple(samples), events=tuple(events))


# ---------------------------------------------------------------------------------------------------
# The writer
# ---------------------------------------------------------------------------------------------------


class _Writer:
    """Writes the files of the built patients and collects what the manifest needs."""

    def __init__(self, context: BuildContext, root: Path) -> None:
        self.context = context
        self.root = root
        if root.exists() and (not root.is_dir() or any(root.iterdir())):
            raise BenchmarkConfigError(f"{root} exists and is not an empty directory")
        self.created = not root.exists()
        root.mkdir(parents=True, exist_ok=True)
        self.files: dict[str, str] = {}
        self.patients: dict[str, dict[str, JsonValue]] = {}
        # headline counts are the virtual patients'; the confounder twins are counted apart
        self.counts: dict[bool, Counter[str]] = {False: Counter(), True: Counter()}
        self.tail_counts: dict[bool, Counter[str]] = {False: Counter(), True: Counter()}
        self.closing_counts: dict[bool, Counter[str]] = {
            False: Counter(),
            True: Counter(),
        }
        self.n_patients: dict[bool, int] = {False: 0, True: 0}
        self.n_days: dict[bool, int] = {False: 0, True: 0}
        self.disabled: set[str] = set()
        self.skipped: Counter[str] = Counter()
        self.cuff_readings: dict[str, Counter[str]] = {}
        self.cuff_realised: dict[str, Counter[str]] = {}

    def abort(self) -> None:
        """Remove what this build wrote: the directory if it created it, else only its contents."""
        if self.created:
            shutil.rmtree(self.root, ignore_errors=True)
            return
        for child in self.root.iterdir():
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)

    def _record(self, relative: str) -> None:
        self.files[relative] = file_sha256(self.root / relative)

    def add(self, built: BuiltPatient, split: str) -> None:
        context = self.context
        if built.patient_id in self.patients:
            raise BenchmarkConfigError(f"patient {built.patient_id!r} is built twice")
        write_care_plan(self.root, built.plan)
        self._record(_plan_relpath(built.plan.care_plan_id))
        for day in built.days:
            write_observed_day(self.root, day.observed)
            truth = day.truth
            write_truth(
                self.root,
                truth.latent,
                truth.ground_truth,
                truth.injection_log,
                truth.behaviour_log,
            )
            index = day.observed.day_index
            baseline = {
                "patient_id": built.patient_id,
                "day_index": index,
                "seed": day.observed.seed,
                "latent_step_ms": context.config.latent_step_ms,
                "baseline_sbp_mmhg": list(day.baseline_sbp_mmhg),
            }
            relative = f"{GENERATOR_DIR}/{built.patient_id}/{index}.json"
            _write_json(self.root / relative, baseline)
            for rel in (
                f"days/{built.patient_id}/{index}.json",
                f"truth/{built.patient_id}/{index}.json",
                relative,
            ):
                self._record(rel)
            twin = built.role == ROLE_PAIR
            if not twin and not day.tail:
                self._count_cuff_faults(truth.injection_log)
            counts = self.tail_counts[twin] if day.tail else self.counts[twin]
            start = index * T_DAY_MS
            for event in truth.ground_truth:
                counts[f"{event.cls.value}/{event.subtype}"] += 1
                decided = event.end_ms if event.end_ms is not None else event.onset_ms
                if (
                    day.tail and event.cls is InjectedClass.C1 and decided == start
                ):  # the closing step of the last scored day (ADR-066)
                    self.closing_counts[twin][f"{event.cls.value}/{event.subtype}"] += 1
        self.n_patients[built.role == ROLE_PAIR] += 1
        self.n_days[built.role == ROLE_PAIR] += built.n_scored_days
        self.disabled |= built.disabled_subtypes
        self.skipped.update(built.skipped)
        entry: dict[str, JsonValue] = {
            "split": split,
            "cohort": built.cohort,
            "role": built.role,
            "n_scored_days": built.n_scored_days,
            "tail_day_index": built.n_scored_days,
            "care_plan_id": built.plan.care_plan_id,
            "patient_index": built.patient_index,
        }
        entry.update(built.extra)
        self.patients[built.patient_id] = entry

    def _count_cuff_faults(self, log: Any) -> None:
        """Tally the anchored cuff faults of a scored day of a virtual patient: drawn -> covered, and realised."""
        for entry in log:
            subtype = entry["subtype"]
            if subtype not in ANCHORED_SUBTYPES:
                continue
            details = entry["details"]
            key = f"{details['n_readings_drawn']}->{details['n_readings_covered']}"
            self.cuff_readings.setdefault(subtype, Counter())[key] += 1
            self.cuff_realised.setdefault(subtype, Counter())["placed"] += 1
            if entry["realised"]:
                self.cuff_realised[subtype]["realised"] += 1

    def finish(self, git_rev: str | None) -> Manifest:
        context = self.context
        config = context.config
        provenance: list[Mapping[str, str | None]] = []
        multi = len(config.cohorts) > 1
        names: list[str] = []
        fixture_only = context.fixture_only
        for spec in config.cohorts:
            prior = context.cohorts[spec.id].prior
            names.append(prior.name)
            for p in prior.provenance():
                provenance.append(
                    {
                        "name": f"{spec.id}:{p.name}" if multi else p.name,
                        "source_ref": p.source_ref,
                        "verified_by": p.verified_by,
                    }
                )
        settings: dict[str, JsonValue] = {
            "benchmark_version": config.benchmark_version,
            "latent_measurement_mode": context.mode,
            "latent_step_ms": config.latent_step_ms,
            "monitor": {
                "step_ms": config.monitor_step_ms,
                "reorder_delay_ms": config.monitor_reorder_delay_ms,
            },
            "jitter_source": jitter_descriptor(context.jitter),
            "segment_source": context.library.descriptor,
            "disabled_subtypes": cast(JsonValue, sorted(self.disabled)),
            "numpy_version": np.__version__,
            "python_version": platform.python_version(),
            "n_scored_days": config.n_days,
            "tail_day": True,
            "n_patients": self.n_patients[False],
            "n_patient_days": self.n_days[False],
            "n_twin_patients": self.n_patients[True],
            "n_twin_patient_days": self.n_days[True],
            "tail_event_counts": dict(sorted(self.tail_counts[False].items())),
            "closing_step_event_counts": dict(
                sorted(self.closing_counts[False].items())
            ),
            "twin_event_counts": dict(sorted(self.counts[True].items())),
            "twin_tail_event_counts": dict(sorted(self.tail_counts[True].items())),
            "twin_closing_step_event_counts": dict(
                sorted(self.closing_counts[True].items())
            ),
            "total_event_counts": dict(
                sorted((self.counts[False] + self.counts[True]).items())
            ),
            "cohorts": [c.id for c in config.cohorts],
            "split_fractions": {k: float(v) for k, v in config.split_fractions.items()},
            "registry_version": context.registry.version(),
            "registry_sha256": context.registry.sha256,
            "registry_fixture_only": bool(context.registry.fixture_only),
            "device_profile": {
                "dispenser_content_sensing": config.dispenser_content_sensing,
                "authenticating_devices": list(config.authenticating_devices),
            },
            "design_sha256": dict(context.design_sha256),
            "prior_sha256": dict(context.prior_sha256),
            "history_days": context.history_days,
            "pathway_template_id": config.pathway_template_id,
            "injection_rates": {
                "c1": context.design.rate_c1,
                "c2": context.design.rate_c2,
                "c3": context.design.rate_c3,
            },
            "confounder_pairs_per_variant": context.design.pairs_per_variant,
            "excluded_zero_levels": {
                cohort_id: {k: list(v) for k, v in per_subtype.items()}
                for cohort_id, per_subtype in context.excluded_zero_levels().items()
            },
            "plan_skipped": dict(sorted(self.skipped.items())),
            "anchored_cuff_faults": {
                "subtypes": list(ANCHORED_SUBTYPES),
                "duration_unit": READINGS_UNIT,
                "stuck_at_excluded_day_indices": [0],
                "readings_drawn_to_covered": {
                    s: dict(sorted(c.items()))
                    for s, c in sorted(self.cuff_readings.items())
                },
                "realised": {
                    s: {"placed": c["placed"], "realised": c["realised"]}
                    for s, c in sorted(self.cuff_realised.items())
                },
            },
            "n_unverified_prior": context.n_unverified_prior,
            "n_unverified_design": context.n_unverified_design,
            "schedule": {
                "dose_ticks_ms": list(context.schedule.dose_ticks_ms),
                "measurement_ticks_ms": list(context.schedule.measurement_ticks_ms),
            },
        }
        manifest = Manifest(
            benchmark_version=config.benchmark_version,
            generator_git_rev=git_rev if git_rev is not None else UNKNOWN_REV,
            generation_seed=config.generation_seed,
            prior_source_name="+".join(names),
            prior_provenance=tuple(provenance),
            fixture_only=fixture_only,
            n_unfilled=0,
            n_unverified=context.n_unverified_prior + context.n_unverified_design,
            patients=dict(sorted(self.patients.items())),
            files=dict(sorted(self.files.items())),
            event_counts=dict(sorted(self.counts[False].items())),
            settings=settings,
        )
        write_manifest(self.root, manifest)
        return manifest


# ---------------------------------------------------------------------------------------------------
# generate_benchmark
# ---------------------------------------------------------------------------------------------------


def generate_benchmark(
    config: BenchmarkConfig | str | Path,
    prior: PriorSource | Mapping[str, PriorSource] | None,
    out_dir: str | Path,
    allow_fixture_only: bool = False,
    git_rev: str | None = None,
) -> Manifest:
    """Build a benchmark version into ``out_dir`` (new or empty) and return its manifest.

    ``config`` is a ``BenchmarkConfig`` or the path of one; ``prior`` the ``PriorSource`` of the single cohort, a
    mapping from cohort id to prior, or None to load the priors named in the configuration. ``git_rev`` is the
    revision of the generator (the CLI reads it from git; a library call passes it in, and None records
    ``"unknown"``): the build reads neither the clock nor the environment. A fixture-only prior, registry or design
    needs ``allow_fixture_only=True`` (``FixtureOnlyPriorError``; the manifest then has ``fixture_only`` true); an
    unfilled prior or design row refuses the build (``UnfilledParameterError`` naming the rows).
    """
    context = BuildContext.create(config, prior, allow_fixture_only=allow_fixture_only)
    return context.generate(out_dir, git_rev=git_rev)


# ---------------------------------------------------------------------------------------------------
# The reader
# ---------------------------------------------------------------------------------------------------


class ObservedViewError(TraceError):
    """The observed-only view of a benchmark was asked for truth, latent or generator state."""


VIEW_FULL: Final = "full"
VIEW_OBSERVED: Final = "observed"
VIEWS: Final = (VIEW_FULL, VIEW_OBSERVED)


class BenchmarkReader:
    """Read access to one benchmark directory, as WS06, WS07, WS08 and WS13 use it.

    Two views. ``view="full"`` (evaluation code) offers everything. ``view="observed"`` (inference-time code: the
    monitor, the baselines, anything that fits or runs a detector) offers ONLY the observed days, the care plans, the
    day lists and the split (``patients`` maps an id to ``split`` and ``cohort``); ``truth``, ``benchmark_day``,
    ``closing_step_truth``, ``baseline_sbp``, ``manifest``, ``root`` and the role filters raise ``ObservedViewError``,
    so that such code cannot reach the ground truth, the latent trace, the generator sidecar or the role of a patient.

    ``days(patient)`` lists the SCORED days; the tail day (ADR-066) is ``tail_day(patient)`` and is in no count; its
    C1 events decided at its first step are ``closing_step_truth``. The twin patients (``role: confounder_pair``) are
    counted apart from the virtual patients: ``n_patient_days`` defaults to the virtual ones.
    """

    def __init__(self, root: Path, manifest: Manifest, view: str = VIEW_FULL) -> None:
        if view not in VIEWS:
            raise BenchmarkConfigError(
                f"view must be one of {list(VIEWS)}, got {view!r}"
            )
        self._root = root
        self._manifest = manifest
        self.view = view

    def _full_only(self, what: str) -> None:
        if self.view != VIEW_FULL:
            raise ObservedViewError(
                f"{what} is not available in the observed-only view"
            )

    @property
    def root(self) -> Path:
        self._full_only("root")
        return self._root

    @property
    def manifest(self) -> Manifest:
        self._full_only("the manifest")
        return self._manifest

    @property
    def patients(self) -> Mapping[str, Mapping[str, JsonValue]]:
        entries = self._manifest.patients
        if self.view == VIEW_FULL:
            return entries
        return {
            pid: {"split": e["split"], "cohort": e["cohort"]}
            for pid, e in entries.items()
        }

    def patient_ids(
        self,
        *,
        split: str | None = None,
        role: str | None = None,
        cohort: str | None = None,
    ) -> tuple[str, ...]:
        if role is not None:
            self._full_only("a filter by role")
        return tuple(
            sorted(
                pid
                for pid, entry in self._manifest.patients.items()
                if (split is None or entry["split"] == split)
                and (role is None or entry["role"] == role)
                and (cohort is None or entry["cohort"] == cohort)
            )
        )

    def _entry(self, patient_id: str) -> Mapping[str, JsonValue]:
        try:
            return self._manifest.patients[patient_id]
        except KeyError:
            raise KeyError(f"no patient {patient_id!r} in the benchmark") from None

    def n_patient_days(self, role: str | None = ROLE_PATIENT) -> int:
        """Scored patient-days of the patients of ``role`` (default the virtual patients; None: all, twins included)."""
        self._full_only("the day totals by role")
        total = 0
        for entry in self._manifest.patients.values():
            n = entry["n_scored_days"]
            assert isinstance(n, int)
            if role is None or entry["role"] == role:
                total += n
        return total

    def days(self, patient_id: str) -> tuple[int, ...]:
        """The scored days of a patient (the tail day is not one of them)."""
        n = self._entry(patient_id)["n_scored_days"]
        assert isinstance(n, int)
        return tuple(range(n))

    def tail_day(self, patient_id: str) -> int | None:
        """The index of the unscored tail day, None if the patient has none."""
        index = self._entry(patient_id).get("tail_day_index")
        return index if isinstance(index, int) else None

    def _check_day(self, patient_id: str, day_index: int) -> None:
        if day_index not in (*self.days(patient_id), self.tail_day(patient_id)):
            raise KeyError(f"patient {patient_id!r} has no day {day_index}")

    def observed(self, patient_id: str, day_index: int) -> ObservedDay:
        self._check_day(patient_id, day_index)
        return read_observed_day(self._root, patient_id, day_index)

    def truth(self, patient_id: str, day_index: int) -> TruthRecord:
        self._full_only("the truth")
        self._check_day(patient_id, day_index)
        if not (self._root / "truth").is_dir():
            raise TruthUnavailableError(f"{self._root} has no truth directory")
        return read_truth(self._root, patient_id, day_index)

    def benchmark_day(self, patient_id: str, day_index: int) -> BenchmarkDay:
        self._full_only("the benchmark day")
        truth = self.truth(patient_id, day_index)
        return BenchmarkDay(
            self.observed(patient_id, day_index), truth.latent, truth.ground_truth
        )

    def closing_step_truth(self, patient_id: str) -> tuple[GroundTruthEvent, ...]:
        """The C1 events of the tail day decided at its first step: the truth of the closing step of the last scored day.

        A C1 event is decided at ``end_ms`` (a windowed obligation) or at ``onset_ms`` (a point event); the first step
        of the tail day is the instant ``tail_day * T_day``. The C2 and C3 events of the tail day are injected events of
        that day, not decisions of the monitor at the shared step, so they are never part of it (a C2 or C3 event that
        starts exactly at that instant is therefore not scored on the last scored day: an open decision, builder.md).
        """
        self._full_only("the closing-step truth")
        tail = self.tail_day(patient_id)
        if tail is None:
            return ()
        start = tail * T_DAY_MS
        return tuple(
            e
            for e in self.truth(patient_id, tail).ground_truth
            if e.cls is InjectedClass.C1
            and (e.end_ms if e.end_ms is not None else e.onset_ms) == start
        )

    def baseline_sbp(self, patient_id: str, day_index: int) -> tuple[float, ...]:
        """The latent baseline pressure of a day before the drug and the pulses (generator sidecar, full view only).

        It is generator state: without the truth directory (an observed-only copy) it is refused too.
        """
        self._full_only("the latent baseline")
        self._check_day(patient_id, day_index)
        path = self._root / GENERATOR_DIR / patient_id / f"{day_index}.json"
        if not (self._root / "truth").is_dir() or not path.is_file():
            raise TruthUnavailableError(f"the generator sidecar {path} is unavailable")
        document = json.loads(path.read_text(encoding="utf-8"))
        return tuple(float(x) for x in document["baseline_sbp_mmhg"])

    def care_plan(self, care_plan_id: str) -> CarePlan:
        """The plan that an ``ObservedDay.care_plan_id`` names (``KeyError`` if it is unknown)."""
        return read_care_plan(self._root, care_plan_id)


def open_benchmark(
    manifest_path: str | Path, verify: bool = False, view: str = VIEW_FULL
) -> BenchmarkReader:
    """Open a benchmark directory (or its ``manifest.json``); ``verify=True`` checks every file first.

    ``view="observed"`` gives the view that a detector or the monitor must be handed (``BenchmarkReader``).
    """
    path = Path(manifest_path)
    root = path.parent if path.name == "manifest.json" else path
    if verify:
        verify_benchmark(root)
    return BenchmarkReader(root, read_manifest(root), view)


def load_benchmark(
    manifest_path: str | Path, verify: bool = False, view: str = VIEW_FULL
) -> BenchmarkReader:
    """The name of the contract table (``#package-public-api``): the same as ``open_benchmark``."""
    return open_benchmark(manifest_path, verify, view)


# The injection vocabulary that no observed file may contain: the fields of an injection record, the names of the
# subtypes of the three classes and of the confounder groups, the natural-subtype prefix and the template ids. A
# string of an observed file (a key or a value) equal to one of them, or starting with the prefix, is a leak.
_LEAK_PARTS: Final = (
    "latent",
    "ground_truth",
    "injection",
    "spontaneous_",
    "confounder",
)
_RECORD_FIELDS: Final = (
    "injected", "record_index", "truth_indices", "explains_in_later_days", "realised", "n_changed",
    "evidence_paths", "confounder_group", "indistinguishable_by_construction", "variant_id", "template_id",
    "expected_undetectable", "onset_ms", "end_ms", "duration_ms", "magnitude", "magnitude_unit",
)  # fmt: skip


def _leak_words() -> frozenset[str]:
    from ralmon.benchmark.confounders import GROUPS as groups
    from ralmon.benchmark.injection import registered_subtypes

    words = {*_RECORD_FIELDS, *groups, *C1_SUBTYPES, "dose_omission"}
    words |= {t.value for t in TemplateId}
    for cls in (InjectedClass.C2, InjectedClass.C3):
        words |= set(registered_subtypes(cls))
    return frozenset(words)


def _strings(node: object) -> Iterable[str]:
    if isinstance(node, str):
        yield node
    elif isinstance(node, Mapping):
        for key, value in node.items():
            yield str(key)
            yield from _strings(value)
    elif isinstance(node, (list, tuple)):
        for item in node:
            yield from _strings(item)


def _check_observed_file(root: Path, relative: str, words: frozenset[str]) -> None:
    """Parse an observed file strictly (unknown keys, bad types and undeclared payload keys are errors) and scan it."""
    _, pid, name = relative.split("/")
    try:
        day = read_observed_day(root, pid, int(name.removesuffix(".json")))
        for event in day.events:
            vocab.check_payload(event.kind, event.payload)
        document = json.loads((root / relative).read_text(encoding="utf-8"))
    except (TraceError, vocab.VocabularyError, ValueError, OSError) as exc:
        raise TraceError(f"{relative}: not a clean observed day: {exc}") from exc
    for text in _strings(document):
        if text in words or any(part in text for part in _LEAK_PARTS):
            raise TraceError(
                f"{relative}: an observed file names {text!r}, which belongs to the truth side"
            )


def verify_benchmark(root: str | Path) -> int:
    """Check a benchmark directory: hashes, no unlisted file, strict observed days, no leaked vocabulary.

    Raises ``ManifestError`` naming the first file that is missing, unlisted or differs, ``TraceError`` for an
    observed file that does not parse as an ``ObservedDay`` (an unknown key, an undeclared payload key) or that names
    latent data, ground truth or the injection vocabulary (record fields, subtype names, template ids). Every observed
    file is parsed, so the check costs a read of the whole ``days/`` tree. Returns the number of files verified.
    """
    path = Path(root)
    verify_manifest(path)
    manifest = read_manifest(path)
    on_disk = {
        p.relative_to(path).as_posix() for p in path.rglob("*") if p.is_file()
    } - {MANIFEST_NAME}
    unlisted = sorted(on_disk - set(manifest.files))
    if unlisted:
        raise ManifestError(f"file not listed in the manifest: {unlisted[0]}")
    words = _leak_words()
    for relative in sorted(manifest.files):
        if relative.startswith("days/"):
            _check_observed_file(path, relative, words)
    for pid, entry in manifest.patients.items():
        tail = entry["tail_day_index"]
        if f"days/{pid}/{tail}.json" not in manifest.files:
            raise ManifestError(
                f"patient {pid}: the tail day is not listed in the manifest"
            )
    return len(manifest.files)
