"""The seeded experiment runner of WS08 (``02-interfaces.md#experiment-config-and-outputs``).

``run_experiment(config, options, output_root)`` writes ``output_root/<experiment_id>/<seed>/{config.yaml, metrics.json,
git_rev.txt}`` for every seed. ``metrics.json`` has the layout of the README of WS08 (metric first, then the detector;
a metric that does not apply to a detector is ``null``), is written with sorted keys, two-space indent and a final newline,
holds no ``NaN`` and no wall-clock quantity, and is byte-identical for the same configuration and seed on one machine (E8).

What a seed does (E1, E2). It re-draws the split of the virtual patients (``split_patients``, largest remainder, by
patient) and every random choice of a model (the seed of a detector, the bootstrap); the benchmark is the one named by the
configuration. The detectors are built by ``build_detector``, fitted on the training and calibration days and run, one
day at a time, on the observed days of the test patients. Ground truth is read by the scoring code only.

Ground-truth discipline. The runner holds two readers of the benchmark: the observed-only view (``view="observed"``) from
which every detector gets its days and care plans, and the full view, used only to read the truth for scoring and the
manifest. The days handed to ``fit`` are benchmark days whose latent trace and ground truth raise ``TruthAccessError`` on any
access (stricter than the ``Detector`` contract, which would allow the truth of a training day: no detector of WS06 or WS08
uses it). ``run`` gets an ``ObservedDay``. The test days are never given to ``fit``.

Scoring conventions (ADR-064, ADR-066; they refine E3, which says "per patient-day").
* The unit of MATCHING is the record of one patient: the events of all its scored days on the continuing axis plus the
  closing-step truth of the unscored tail day, against all the detections of its runs. A tolerance window may therefore
  cross midnight, which resolves the ownership at the shared step without a special case: a detection at the closing step
  of day d-1 is matched against the truth of day d (and against the day-end COUNT of day d-1, which stays with that day,
  ADR-064 (c)), whichever the tolerance reaches.
* The unit of COUNTING and of the bootstrap is the patient-day: a pair and a missed event belong to the day whose file holds
  the event (the closing-step events to the last scored day), a duplicate and a false alarm to the day that contains
  the instant of the detection (the shared step ``d * T_day`` belongs to day d, and the final closing step to the last
  scored day, which holds the closing-step truth). A duplicate or false alarm after the first step of the tail day is in
  no scored day: it is dropped and counted (``analysis.run.detections.<det>.n_dropped_in_unscored_tail``). The tail day
  is in no day count; the detectors are never run on it.
* ``after_close = "keep"`` keeps what a run emits after its closing step (a baseline runs on for ``tail_ms``); ``"clip"`` drops it
  (F11); either way the count is reported.
* The closing-step truth is C1 only (ADR-066, builder.md): a C2 or C3 event that starts at the first instant of the tail
  day is not part of it, and the limit is reported (``analysis.run.closing_step``).

Guards (``evaluate_guards``). Each condition of the fairness audit that decides whether a comparison is legitimate is a
guard with an id. Always a HARD failure (``GuardError``, nothing is written for the seed): ``B1_VACUOUS`` (B1 ran with fewer
rules than R1 to R4 on some plan). A HARD failure in a ``headline`` run and a FLAG in the metadata otherwise:
``FIXTURE_ONLY`` (a fixture-only benchmark or registry), ``REORDER_DELAY_NOT_A_MULTIPLE_OF_STEP`` (F10),
``TAIL_DAY_MISSING`` (ADR-066), ``INT_GATE`` (``presence_samples_without_availability_marks`` positive, ADR-054, F21),
``ADR063_INT_SYS_COMPARISON`` (B3 or B5 next to the proposed method, ADR-063, F7), ``HISTORY_ASYMMETRY`` (history only for
the proposed method, ADR-061, F12) and ``TWINS_IN_HEADLINE``, ``INT_GATE_UNKNOWN`` (the verdict runner reports no counters), ``TIMING_TAIL_TOO_SHORT`` (the tail
of the baselines is shorter than RESP delta2 plus the reorder delay and the day-end COUNT convention),
``ALPHA_BELOW_CALIBRATION_RESOLUTION`` (min alpha below 1 / (n + 1), E6) and ``NO_DEVICE_PROFILE``. A decision that gab accepted is named in
``run_options.accepted_decisions`` and lifts its guard only if it is an ADR of ``docs/plan/03-decisions.md`` whose Status
starts with ``accepted`` (the table ``GUARD_DECISIONS``: ADR-063, ADR-061); D2, F19 and F20 have no ADR yet and cannot be
named. Flags only: ``B1_MINIMAL`` (F8),
``B5_NOT_PAPER_COMPARISON`` (D2, F6), ``CLOSING_STEP_C1_ONLY``, ``LATENCY_CONVENTION_OPEN`` (F20), ``CONTAMINATION_POLICY_OPEN``
(F19), ``SCORES_NOT_RANKED`` (F13: no AUROC or AP is computed for B1 or B4) and ``B2_IFOREST_NOT_STRONGEST`` (F14). All of
them are in ``meta.guards``.

Before the run the registry is checked against what the proposed method needs (the evidence thresholds of the attribution
layer and a priority, a scale and a latency bound for every template): a registry that lacks them is refused with a
``ConfigError`` naming the rows, because a run that reaches such an alert would stop hours later.

Extension points. Modules ``ralmon.eval.ablations``, ``embodied``, ``shift`` and ``realdata`` may expose
``variant_components(name) -> PipelineComponents | None``; ``analysis``, ``ablations``, ``embodied``, ``shift`` and
``realdata`` may expose ``hooks_for(experiment_id)``, a list of functions ``RunContext -> HookResult`` whose ``analysis`` is
merged under ``analysis`` and whose ``metrics`` (contract metric names only) is merged into the metric-first layout.
A module that does not exist is skipped.
"""

from __future__ import annotations

import argparse
import importlib
import json
import math
import os
import re
import subprocess
import sys
import typing
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from fractions import Fraction
from pathlib import Path
from types import ModuleType
from typing import Any, Final

import numpy as np
import yaml

from ralmon.attribution import Alert, Detection, RuleAttributor, extract_evidence
from ralmon.baselines import (
    B1StaticThresholds,
    B2AnomalyDetection,
    B3PlainSTL,
    B4ConformalOnly,
    B5ConformalSTL,
)
from ralmon.benchmark import (
    BenchmarkDay,
    GroundTruthEvent,
    ObservedDay,
    open_benchmark,
)
from ralmon.benchmark import split_patients as _builder_split_patients
from ralmon.conformal import BonferroniAllocation, SplitConformal
from ralmon.eval.metrics import (
    CLASSES,
    LABEL_COLUMNS,
    STREAM_BOOTSTRAP,
    MatchConfig,
    Matching,
    bin_index,
    bootstrap_weights,
    ci_with_report,
    empirical_coverage,
    expected_calibration_error,
    latency_percentiles,
    match_events,
    min_bootstrap_resamples,
    per_class_prf,
    reliability_bins,
    residual_coverage,
    table_abstention_rate,
    table_accuracy_answered,
    table_delay_mean,
    table_early_fraction,
    table_fa_per_day,
    table_macro_f1,
    table_prf,
)
from ralmon.eval.ours import (
    CompositeForecaster,
    OursDetector,
    PipelineComponents,
)
from ralmon.monitor import (
    AutoRegressiveForecaster,
    DeadlineForecaster,
    Forecaster,
    MonitorConfig,
    PersistenceForecaster,
    StreamingMonitor,
    VerdictState,
)
from ralmon.signals import MS_PER_HOUR
from ralmon.spec import CarePlan, RegistryError, load_registry, load_templates

__all__ = [
    "ConfigError",
    "DetectorEnvironment",
    "ExperimentConfig",
    "Guard",
    "GuardError",
    "GuardReport",
    "HookResult",
    "RunContext",
    "RunFacts",
    "RunOptions",
    "TruthAccessError",
    "build_detector",
    "current_git_rev",
    "dump_experiment",
    "evaluate_guards",
    "load_experiment",
    "main",
    "make_environment",
    "run_experiment",
    "split_patients",
]

T_DAY_MS: Final[int] = (
    86_400_000  # algorithmic: 24 h, the day of the continuing axis (ADR-053 (h))
)
#: The most earlier days a run of the monitor replays (``ralmon.monitor.offline.MAX_HISTORY_DAYS``, not exported by the
#: package root; ``tests/eval/test_review_minors.py`` checks that the two are equal).
MAX_HISTORY_DAYS: Final[int] = 14
COVERAGE_QUALIFIER: Final[str] = (
    "marginal over patient episodes under exchangeability; calibration unit: patient episode"
)
METRIC_NAMES: Final[tuple[str, ...]] = (
    "per_class_prf",
    "detection_delay_ms",
    "false_alarms_per_patient_day",
    "recall_vs_false_alarm_curve",
    "empirical_coverage",
    "mean_interval_width",
    "expected_calibration_error",
    "attribution_confusion",
    "accuracy_vs_coverage",
    "latency_percentiles",
    "severity_rank_agreement",
)
BASELINE_NAMES: Final[tuple[str, ...]] = (
    "B1",
    "B2",
    "B2-residual",
    "B2-iforest",
    "B3",
    "B4",
    "B5",
    "B5-per-template",
    "B5-bonferroni",
)
_ALPHA_BASELINES: Final[frozenset[str]] = frozenset(
    {"B4", "B5", "B5-per-template", "B5-bonferroni"}
)
_OURS_NAME: Final = re.compile(r"ours(-[A-Za-z0-9_.]+)*")
_EXPERIMENT_ID: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
_EXTENSIONS: Final[tuple[str, ...]] = (
    "ralmon.eval.ablations",
    "ralmon.eval.embodied",
    "ralmon.eval.shift",
    "ralmon.eval.realdata",
)
_HOOK_MODULES: Final[tuple[str, ...]] = ("ralmon.eval.analysis", *_EXTENSIONS)
_MAX_CONFIG_BYTES: Final[int] = (
    1_048_576  # algorithmic: a configuration file is a few kilobytes
)
_MIN_HEADLINE_SEEDS: Final[int] = 5  # analisi 5.1: at least five seeds
_B1_RULES: Final[tuple[str, ...]] = ("R1", "R2", "R3", "R4")
_SPLITS: Final[tuple[str, ...]] = ("train", "calibration", "test")

_HISTORY_MODES: Final = ("none", "ours")
_AFTER_CLOSE: Final = ("keep", "clip")
_TWINS: Final = ("exclude", "separate", "include")
_BASELINE_TIME: Final = ("as_emitted", "subtract_reorder_delay")
_CALIB_DAYS: Final = ("all", "without_injected")


class ConfigError(ValueError):
    """The configuration, the benchmark or a hook is not usable (never a silent default)."""


class GuardError(ConfigError):
    """A guard of the fairness audit failed hard: the run is refused (module docstring)."""


class TruthAccessError(RuntimeError):
    """A detector tried to read the latent trace or the ground truth of a day it was given."""


def baseline_has_alpha(name: str) -> bool:
    """Whether a detector name takes the level ``alpha`` (the conformal methods)."""
    return name in _ALPHA_BASELINES or _OURS_NAME.fullmatch(name) is not None


def is_valid_detector_name(name: str) -> bool:
    return name in BASELINE_NAMES or _OURS_NAME.fullmatch(name) is not None


# ---- configuration ---------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ExperimentConfig:
    """Verbatim from ``02-interfaces.md#experiment-config-and-outputs`` (version 0.1.0)."""

    experiment_id: str  # e.g. "main", "A1", "A6", "shift", "unlabeled-real"
    benchmark_manifest: str  # path of the benchmark version
    detectors: Sequence[str]  # names in the Detector contract
    seeds: Sequence[int]  # at least five for headline results
    split: Mapping[str, float]  # train, calibration, test fractions, by patient
    match: MatchConfig
    alpha: float | None
    monitor: MonitorConfig | None


@dataclass(frozen=True, slots=True)
class RunOptions:
    """The companion of ``ExperimentConfig`` (the contract has no field for these), parsed from ``run_options``.

    Required in the YAML, no default (E9: written before the first run on the test split, each with its reason in the
    header comment of the file): ``alpha_grid``, ``n_bootstrap``, ``ci_level``, ``ece_bins``. The switches below the line
    have a conservative default and are reported in ``meta``; none of them resolves an open decision of the project.

    * ``headline``: a result that goes in the paper; the headline guards are hard failures (module docstring).
    * ``required_analysis``: dotted keys that ``analysis`` must hold at the end of the run.
    * ``extra``: free-form values for the hooks of WS08-T02 to T07.
    * ``history``: ``none`` (every detector one day at a time with empty state, ADR-061 open) or ``ours`` (the proposed
      method gets the earlier days of the patient: asymmetric, a headline guard).
    * ``after_close``: ``keep`` or ``clip`` the detections after the closing step of a run (F11).
    * ``twins``: ``exclude`` (the confounder pairs are not run), ``separate`` (run and reported apart) or ``include`` (run
      with the test patients: a headline guard).
    * ``baseline_time``: ``as_emitted`` or ``subtract_reorder_delay`` (F20: the baselines report ``t_eval_ms + D``).
    * ``calibration_days``: ``all`` or ``without_injected`` (F19: drop the calibration days with an injected event).
    * ``registry`` / ``allow_fixture_only``: the registry file (None: ``configs/registry/hypertension.yaml``) and the
      permission to load a fixture-only one.
    * ``accepted_decisions``: ADR ids that are accepted in ``docs/plan/03-decisions.md`` (checked); the table ``GUARD_DECISIONS``
      says which guard each lifts.
    * ``detector_params``: operating parameters of the detectors (``timing_tail_ms``, ``forecaster``, ``B2``, ``B4``, ``B5``,
      ``B5-bonferroni``, ``ours``); none has a default.
    """

    alpha_grid: tuple[float, ...]
    n_bootstrap: int
    ci_level: float
    ece_bins: int
    headline: bool = False
    required_analysis: tuple[str, ...] = ()
    extra: Mapping[str, Any] = field(default_factory=dict)
    history: str = "none"
    after_close: str = "keep"
    twins: str = "exclude"
    baseline_time: str = "as_emitted"
    calibration_days: str = "all"
    registry: str | None = None
    allow_fixture_only: bool = False
    accepted_decisions: tuple[str, ...] = ()
    detector_params: Mapping[str, Any] = field(default_factory=dict)


def _read_yaml(path: Path) -> Any:
    class Strict(yaml.SafeLoader):
        def compose_node(self, parent: Any, index: Any) -> Any:
            event = self.peek_event()  # type: ignore[no-untyped-call]
            if getattr(event, "anchor", None) is not None:
                raise ConfigError(f"{path}: anchors and aliases are not allowed")
            return super().compose_node(parent, index)

        def construct_mapping(self, node: Any, deep: bool = False) -> Any:
            seen: set[Any] = set()
            for key_node, _ in node.value:
                if key_node.tag == "tag:yaml.org,2002:merge":
                    raise ConfigError(f"{path}: merge keys are not allowed")
                key = self.construct_object(key_node, deep=deep)
                if key in seen:
                    raise ConfigError(f"{path}: duplicate key {key!r}")
                seen.add(key)
            return super().construct_mapping(node, deep=deep)

    try:
        if not path.is_file():
            raise ConfigError(f"{path}: not a file")
        data = path.read_bytes()
        if len(data) > _MAX_CONFIG_BYTES:
            raise ConfigError(f"{path}: larger than {_MAX_CONFIG_BYTES} bytes")
        return yaml.load(data, Loader=Strict)  # SafeLoader subclass
    except ConfigError:
        raise
    except (OSError, yaml.YAMLError, UnicodeDecodeError, RecursionError) as exc:
        raise ConfigError(f"{path}: cannot be read as YAML: {exc}") from exc


def _is_int(x: object) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _is_number(x: object) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _need(cond: bool, message: str) -> None:
    if not cond:
        raise ConfigError(message)


def _keys(
    doc: Mapping[str, Any], required: Sequence[str], optional: Sequence[str], what: str
) -> None:
    _need(isinstance(doc, Mapping), f"{what} must be a mapping")
    missing = [k for k in required if k not in doc]
    unknown = sorted(set(doc) - set(required) - set(optional))
    _need(not missing, f"{what}: missing keys {missing}")
    _need(not unknown, f"{what}: unknown keys {unknown}")


def _level(value: object, what: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ConfigError(f"{what} must be a number in (0, 1)")
    if not 0.0 < float(value) < 1.0:
        raise ConfigError(f"{what} must be a number in (0, 1)")
    return float(value)


def load_experiment(path: str | Path) -> tuple[ExperimentConfig, RunOptions]:
    """Read and validate an experiment YAML: ``(ExperimentConfig, RunOptions)``.

    Relative paths (``benchmark_manifest``, ``run_options.registry``) are resolved against the directory of the file and
    stored absolute, so that the ``config.yaml`` copied to an output directory loads again. Raises ``ConfigError``.
    """
    file = Path(path)
    doc = _read_yaml(file)
    base = file.resolve().parent
    _keys(
        doc,
        (
            "experiment_id",
            "benchmark_manifest",
            "detectors",
            "seeds",
            "split",
            "match",
            "run_options",
        ),
        ("alpha", "monitor"),
        str(file),
    )
    experiment_id = doc["experiment_id"]
    _need(
        isinstance(experiment_id, str)
        and _EXPERIMENT_ID.fullmatch(experiment_id) is not None,
        "experiment_id must be a name of letters, digits, '_', '-' and '.' (it names a directory)",
    )
    manifest = doc["benchmark_manifest"]
    _need(
        isinstance(manifest, str) and manifest != "",
        "benchmark_manifest must be a path",
    )
    manifest_path = _resolve_path(base, manifest)
    detectors = doc["detectors"]
    _need(
        isinstance(detectors, list)
        and len(detectors) > 0
        and all(isinstance(d, str) for d in detectors),
        "detectors must be a non-empty list of names",
    )
    _need(len(set(detectors)) == len(detectors), "detectors must not repeat")
    for name in detectors:
        _need(is_valid_detector_name(name), f"unknown detector {name!r}")
    seeds = doc["seeds"]
    _need(
        isinstance(seeds, list)
        and len(seeds) > 0
        and all(_is_int(s) and s >= 0 for s in seeds),
        "seeds must be a non-empty list of non-negative integers",
    )
    _need(len(set(seeds)) == len(seeds), "seeds must not repeat")
    split = doc["split"]
    _keys(split, _SPLITS, (), "split")
    _need(
        all(_is_number(v) and v >= 0 for v in split.values()),
        "split fractions must be non-negative numbers",
    )
    _need(
        sum(Fraction(str(split[k])) for k in _SPLITS) == 1,
        f"split fractions must sum to 1, got {[split[k] for k in _SPLITS]}",
    )
    match = doc["match"]
    _keys(match, ("tolerance_ms", "time_reference"), (), "match")
    try:
        match_config = MatchConfig(match["tolerance_ms"], match["time_reference"])
    except ValueError as exc:
        raise ConfigError(f"match: {exc}") from exc
    alpha = doc.get("alpha")
    if alpha is not None:
        alpha = _level(alpha, "alpha")
    monitor_doc = doc.get("monitor")
    monitor: MonitorConfig | None = None
    if monitor_doc is not None:
        _keys(
            monitor_doc,
            (
                "step_ms",
                "reorder_delay_ms",
                "predictive",
                "alpha",
                "variant",
                "registry_version",
            ),
            (),
            "monitor",
        )
        _need(
            _is_int(monitor_doc["step_ms"]) and monitor_doc["step_ms"] > 0,
            "monitor.step_ms must be a positive integer",
        )
        _need(
            _is_int(monitor_doc["reorder_delay_ms"])
            and monitor_doc["reorder_delay_ms"] >= 0,
            "monitor.reorder_delay_ms must be a non-negative integer",
        )
        _need(
            isinstance(monitor_doc["predictive"], bool),
            "monitor.predictive must be a bool",
        )
        _need(
            monitor_doc["variant"] in ("likely", "possible"),
            "monitor.variant must be 'likely' or 'possible'",
        )
        _need(
            isinstance(monitor_doc["registry_version"], str),
            "monitor.registry_version must be a string",
        )
        m_alpha = monitor_doc["alpha"]
        if m_alpha is not None:
            m_alpha = _level(m_alpha, "monitor.alpha")
        _need(
            not monitor_doc["predictive"] or m_alpha is not None,
            "a predictive monitor needs monitor.alpha",
        )
        _need(
            m_alpha is None or alpha is None or m_alpha == alpha,
            "monitor.alpha is the total level of a patient-day and must equal the experiment alpha",
        )
        monitor = MonitorConfig(
            monitor_doc["step_ms"],
            monitor_doc["reorder_delay_ms"],
            monitor_doc["predictive"],
            m_alpha,
            monitor_doc["variant"],
            monitor_doc["registry_version"],
        )
    options = _parse_options(doc["run_options"], base)
    _need(
        not options.headline or len(seeds) >= _MIN_HEADLINE_SEEDS,
        f"a headline experiment needs at least {_MIN_HEADLINE_SEEDS} seeds, got {len(seeds)}",
    )
    needs_alpha = [d for d in detectors if baseline_has_alpha(d)]
    if needs_alpha:
        _need(alpha is not None, f"{needs_alpha} take a level: set alpha")
        _need(
            alpha in options.alpha_grid, "alpha must be one of run_options.alpha_grid"
        )
        _need(monitor is not None, f"{needs_alpha} need a monitor configuration")
    config = ExperimentConfig(
        experiment_id,
        manifest_path,
        list(detectors),
        list(seeds),
        {k: split[k] for k in _SPLITS},
        match_config,
        alpha,
        monitor,
    )
    return config, options


def _parse_options(doc: Any, base: Path) -> RunOptions:
    optional = (
        "headline",
        "required_analysis",
        "extra",
        "history",
        "after_close",
        "twins",
        "baseline_time",
        "calibration_days",
        "registry",
        "allow_fixture_only",
        "accepted_decisions",
        "detector_params",
    )
    _keys(
        doc,
        ("alpha_grid", "n_bootstrap", "ci_level", "ece_bins"),
        optional,
        "run_options",
    )
    grid = doc["alpha_grid"]
    _need(
        isinstance(grid, list) and len(grid) > 0,
        "run_options.alpha_grid must be a non-empty list",
    )
    levels = tuple(sorted({_level(a, "alpha_grid entry") for a in grid}))
    _need(len(levels) == len(grid), "run_options.alpha_grid must not repeat")
    _need(
        _is_int(doc["n_bootstrap"]) and doc["n_bootstrap"] >= 1,
        "run_options.n_bootstrap must be a positive integer",
    )
    ci_level = _level(doc["ci_level"], "run_options.ci_level")
    least = min_bootstrap_resamples(ci_level)
    _need(
        doc["n_bootstrap"] >= least,
        f"run_options.n_bootstrap {doc['n_bootstrap']} is below {least}, the fewest resamples for a "
        f"{ci_level} percentile interval (one replicate in each tail)",
    )
    _need(
        _is_int(doc["ece_bins"]) and doc["ece_bins"] >= 1,
        "run_options.ece_bins must be a positive integer",
    )
    headline = doc.get("headline", False)
    _need(isinstance(headline, bool), "run_options.headline must be a bool")
    required = doc.get("required_analysis", [])
    _need(
        isinstance(required, list) and all(isinstance(r, str) for r in required),
        "required_analysis must be a list of keys",
    )
    extra = doc.get("extra", {})
    _need(isinstance(extra, Mapping), "run_options.extra must be a mapping")

    def choice(key: str, allowed: Sequence[str]) -> str:
        value = doc.get(key, allowed[0])
        _need(
            value in allowed,
            f"run_options.{key} must be one of {list(allowed)}, got {value!r}",
        )
        return str(value)

    registry = doc.get("registry")
    _need(
        registry is None or isinstance(registry, str),
        "run_options.registry must be a path",
    )
    allow = doc.get("allow_fixture_only", False)
    _need(isinstance(allow, bool), "run_options.allow_fixture_only must be a bool")
    accepted = doc.get("accepted_decisions", [])
    _need(
        isinstance(accepted, list) and all(isinstance(a, str) for a in accepted),
        "accepted_decisions must be a list of ids",
    )
    validate_accepted_decisions(accepted)
    params = doc.get("detector_params", {})
    _need(isinstance(params, Mapping), "run_options.detector_params must be a mapping")
    return RunOptions(
        alpha_grid=levels,
        n_bootstrap=doc["n_bootstrap"],
        ci_level=ci_level,
        ece_bins=doc["ece_bins"],
        headline=headline,
        required_analysis=tuple(required),
        extra=dict(extra),
        history=choice("history", _HISTORY_MODES),
        after_close=choice("after_close", _AFTER_CLOSE),
        twins=choice("twins", _TWINS),
        baseline_time=choice("baseline_time", _BASELINE_TIME),
        calibration_days=choice("calibration_days", _CALIB_DAYS),
        registry=None if registry is None else _resolve_path(base, registry),
        allow_fixture_only=allow,
        accepted_decisions=tuple(accepted),
        detector_params=dict(params),
    )


def _resolve_path(base: Path, value: str) -> str:
    """A path of a configuration file: absolute as it is; relative against the directory of the file when it exists
    there, else against the repository root (where ``dump_experiment`` writes the paths inside the repository)."""
    path = Path(value)
    if path.is_absolute():
        return str(path.resolve())
    here = (base / path).resolve()
    if here.exists():
        return str(here)
    root = _repo_root()
    if root is not None and (root / path).exists():
        return str((root / path).resolve())
    return str(here)


def _portable(value: str, base: Path | None) -> str:
    """A path as written to an output: relative to the repository root when inside it, else relative to ``base`` (the
    directory of the file that holds it) when given, else as it is. No user name and no absolute path of the machine
    reaches ``config.yaml`` for a benchmark and a registry of the repository."""
    path = Path(value)
    if not path.is_absolute():
        return value
    root = _repo_root()
    if root is not None:
        try:
            return path.resolve().relative_to(root).as_posix()
        except ValueError:
            pass
    if base is not None:
        return Path(os.path.relpath(path, base)).as_posix()
    return value


def dump_experiment(
    config: ExperimentConfig, options: RunOptions, *, base: Path | None = None
) -> str:
    """The resolved configuration as YAML (sorted keys): ``load_experiment`` of the dump gives equal objects.

    Paths are written by ``_portable``; ``base`` is the directory of the file the text will be written to."""
    monitor = None
    if config.monitor is not None:
        m = config.monitor
        monitor = {
            "step_ms": m.step_ms,
            "reorder_delay_ms": m.reorder_delay_ms,
            "predictive": m.predictive,
            "alpha": m.alpha,
            "variant": m.variant,
            "registry_version": m.registry_version,
        }
    run_options: dict[str, Any] = {
        "alpha_grid": list(options.alpha_grid),
        "n_bootstrap": options.n_bootstrap,
        "ci_level": options.ci_level,
        "ece_bins": options.ece_bins,
        "headline": options.headline,
        "required_analysis": list(options.required_analysis),
        "extra": dict(options.extra),
        "history": options.history,
        "after_close": options.after_close,
        "twins": options.twins,
        "baseline_time": options.baseline_time,
        "calibration_days": options.calibration_days,
        "registry": None
        if options.registry is None
        else _portable(options.registry, base),
        "allow_fixture_only": options.allow_fixture_only,
        "accepted_decisions": list(options.accepted_decisions),
        "detector_params": dict(options.detector_params),
    }
    document = {
        "experiment_id": config.experiment_id,
        "benchmark_manifest": _portable(config.benchmark_manifest, base),
        "detectors": list(config.detectors),
        "seeds": list(config.seeds),
        "split": dict(config.split),
        "match": {
            "tolerance_ms": config.match.tolerance_ms,
            "time_reference": config.match.time_reference,
        },
        "alpha": config.alpha,
        "monitor": monitor,
        "run_options": run_options,
    }
    return yaml.safe_dump(document, sort_keys=True, default_flow_style=False)


def split_patients(
    ids: Sequence[str], fractions: Mapping[str, float], seed: int
) -> dict[str, str]:
    """Assign every patient id to exactly one of train, calibration, test (the split is by patient).

    The sizes follow the largest-remainder rule on the exact decimal fractions, the ids are sorted and then permuted by
    the split stream of the seed (the helper of the builder, ``ralmon.benchmark.split_patients``), so the result is a
    function of the set of ids, the fractions and the seed, not of the order of ``ids``. ``ConfigError`` for an invalid
    argument.
    """
    try:
        return dict(_builder_split_patients(ids, fractions, seed))
    except ValueError as exc:
        raise ConfigError(f"split: {exc}") from exc


# ---- guards ----------------------------------------------------------------------------------------------------------


# ---- decisions that lift a guard -----------------------------------------------------------------------------------------

DECISIONS_RELPATH: Final = "docs/plan/03-decisions.md"
_ADR_ID: Final = re.compile(r"ADR-\d{3}")
_ADR_HEADING: Final = re.compile(r"##\s+(ADR-\d+)\b")
_ADR_STATUS: Final = re.compile(r"-\s+\*\*Status\.\*\*\s*(.*)")
#: The one table that says which accepted decision lifts which guard. ``None``: the decision has no ADR yet (D2 and F6
#: for the B5 of the paper, F19 for the calibration days, F20 for the latency convention), so the flag cannot be lifted
#: until an ADR is recorded, accepted and named here.
GUARD_DECISIONS: Final[Mapping[str, str | None]] = {
    "ADR063_INT_SYS_COMPARISON": "ADR-063",
    "HISTORY_ASYMMETRY": "ADR-061",
    "B5_NOT_PAPER_COMPARISON": None,
    "CONTAMINATION_POLICY_OPEN": None,
    "LATENCY_CONVENTION_OPEN": None,
}


def _repo_root() -> Path | None:
    """The repository root (the directory that holds ``docs/plan/03-decisions.md``), None for an installed package."""
    root = Path(__file__).resolve().parents[3]
    return root if (root / DECISIONS_RELPATH).is_file() else None


def adr_statuses(path: Path | None = None) -> dict[str, str]:
    """``{"ADR-063": "proposed [DA-CONFERMARE] ...", ...}`` from the decisions file (the text after ``**Status.**`` of
    each ``## ADR-NNN`` section, empty when the section has none). ``ConfigError`` when the file cannot be found."""
    target = path
    if target is None:
        root = _repo_root()
        target = None if root is None else root / DECISIONS_RELPATH
    if target is None or not target.is_file():
        raise ConfigError(
            f"cannot check run_options.accepted_decisions: the decisions file {DECISIONS_RELPATH} was not found "
            f"(looked at {target})"
        )
    statuses: dict[str, str] = {}
    current: str | None = None
    for line in target.read_text(encoding="utf-8").splitlines():
        heading = _ADR_HEADING.match(line)
        if heading:
            current = heading.group(1)
            statuses[current] = ""
            continue
        status = _ADR_STATUS.match(line)
        if status and current is not None and statuses[current] == "":
            statuses[current] = status.group(1).strip()
    return statuses


def validate_accepted_decisions(names: Sequence[str]) -> frozenset[str]:
    """The names of ``run_options.accepted_decisions`` that are accepted ADRs of the decisions file.

    A name must be an ADR id (``ADR-063``) whose section exists in ``docs/plan/03-decisions.md`` and whose Status line
    starts with ``accepted``; anything else (a malformed or unknown id, a decision that is not an ADR such as ``D2``,
    ``F19`` or ``F20``, an ADR that is still proposed) is a ``ConfigError``.
    """
    if not names:
        return frozenset()
    statuses = adr_statuses()
    for name in names:
        if _ADR_ID.fullmatch(name) is None or name not in statuses:
            raise ConfigError(
                f"accepted_decisions: {name!r} is not an ADR of {DECISIONS_RELPATH}: "
                "record the decision as an accepted ADR first"
            )
        if not statuses[name].startswith("accepted"):
            raise ConfigError(
                f"accepted_decisions: {name} is not accepted (Status: {statuses[name][:60]!r}): "
                "record the decision as an accepted ADR first"
            )
    return frozenset(names)


def _lifted(guard_id: str, accepted: frozenset[str]) -> bool:
    decision = GUARD_DECISIONS[guard_id]
    return decision is not None and decision in accepted


def required_tail_ms(delta2_ms: int, reorder_delay_ms: int) -> int:
    """The shortest ``TimingConfig.tail_ms`` of the audit Conclusion for WS08-T02: the longest window (RESP ``delta2``) plus
    the reorder delay, and long enough for the run to reach the day-end COUNT (the audit uses the day and one hour)."""
    return max(delta2_ms + reorder_delay_ms, T_DAY_MS + MS_PER_HOUR)


@dataclass(frozen=True, slots=True)
class Guard:
    id: str
    message: str


@dataclass(frozen=True, slots=True)
class RunFacts:
    """What the guards look at (module docstring); the first ones are known before the run, the others after it."""

    detectors: tuple[str, ...]
    benchmark_fixture_only: bool
    registry_fixture_only: bool
    step_ms: int
    reorder_delay_ms: int
    patients_without_tail_day: tuple[str, ...] = ()
    b1_rules_active: tuple[str, ...] | None = None
    int_gate: Mapping[str, int] = field(default_factory=dict)
    history: str = "none"
    twins: str = "exclude"
    n_seeds: int = 0
    has_device_profile: bool = False
    timing_tail_ms: int | None = None
    required_tail_ms: int | None = None
    int_gate_unknown: tuple[str, ...] = ()
    min_alpha: float | None = None
    calibration_episodes: Mapping[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class GuardReport:
    hard: tuple[Guard, ...]
    flags: tuple[Guard, ...]

    def raise_if_failed(self) -> None:
        if self.hard:
            raise GuardError("; ".join(f"{g.id}: {g.message}" for g in self.hard))


def evaluate_guards(facts: RunFacts, options: RunOptions) -> GuardReport:
    """The guards of the fairness audit for a run (module docstring): which fail hard and which are flags."""
    hard: list[Guard] = []
    flags: list[Guard] = []
    accepted = validate_accepted_decisions(options.accepted_decisions)
    names = facts.detectors
    baselines = [n for n in names if not n.startswith("ours")]
    has_ours = any(n.startswith("ours") for n in names)

    def conditional(guard_id: str, message: str) -> None:
        (hard if options.headline else flags).append(Guard(guard_id, message))

    if (
        "B1" in names
        and facts.b1_rules_active is not None
        and facts.b1_rules_active != _B1_RULES
    ):
        hard.append(
            Guard(
                "B1_VACUOUS",
                f"B1 ran with the rules {list(facts.b1_rules_active)} instead of {list(_B1_RULES)}: "
                "a plan without the RANGE, HOLD and COUNT parameter records makes B1 a straw man (F9)",
            )
        )
    if facts.benchmark_fixture_only or facts.registry_fixture_only:
        conditional(
            "FIXTURE_ONLY",
            "the benchmark or the registry is fixture-only (ADR-027): no number of this run is a result",
        )
    if baselines and facts.reorder_delay_ms % facts.step_ms != 0:
        conditional(
            "REORDER_DELAY_NOT_A_MULTIPLE_OF_STEP",
            "the lateness rule of the baselines diverges from the monitor's (F10)",
        )
    if facts.patients_without_tail_day:
        conditional(
            "TAIL_DAY_MISSING",
            f"{len(facts.patients_without_tail_day)} patients have no tail day: the closing step of their last day has no owner (ADR-066)",
        )
    positive = {k: v for k, v in facts.int_gate.items() if v > 0}
    if positive:
        conditional(
            "INT_GATE",
            f"presence_samples_without_availability_marks is positive for {sorted(positive)}: "
            "INT-based results are not evidence (ADR-054, F21)",
        )
    if (
        has_ours
        and any(n.startswith(("B3", "B5")) for n in names)
        and not _lifted("ADR063_INT_SYS_COMPARISON", accepted)
    ):
        conditional(
            "ADR063_INT_SYS_COMPARISON",
            "B3 and B5 are silent on INT and SYS violations that the monitor reports: no C3/INT or SYS comparison "
            "between the proposed method and B3 or B5 (ADR-063, F7)",
        )
    if (
        facts.history != "none"
        and baselines
        and not _lifted("HISTORY_ASYMMETRY", accepted)
    ):
        conditional(
            "HISTORY_ASYMMETRY",
            "only the proposed method gets the earlier days of the patient while the baselines run one day at a time (ADR-061, F12)",
        )
    if facts.twins == "include":
        conditional(
            "TWINS_IN_HEADLINE",
            "the confounder twins are a different population (single-day pairs): decide before counting them in a headline (ADR-067)",
        )
    if facts.int_gate_unknown:
        conditional(
            "INT_GATE_UNKNOWN",
            f"the verdict runner of {sorted(facts.int_gate_unknown)} reports no counters, so the INT gate of ADR-054 "
            "is unknown, not passed",
        )
    if (
        baselines
        and facts.timing_tail_ms is not None
        and facts.required_tail_ms is not None
        and facts.timing_tail_ms < facts.required_tail_ms
    ):
        conditional(
            "TIMING_TAIL_TOO_SHORT",
            f"timing_tail_ms {facts.timing_tail_ms} is shorter than {facts.required_tail_ms} (RESP delta2 plus the "
            "reorder delay, and the day-end COUNT convention of the audit): the baselines stop before their deadlines",
        )
    too_few = {
        n: k
        for n, k in facts.calibration_episodes.items()
        if facts.min_alpha is not None
        and Fraction(repr(float(facts.min_alpha))) < Fraction(1, k + 1)
    }
    if too_few:
        conditional(
            "ALPHA_BELOW_CALIBRATION_RESOLUTION",
            f"the smallest alpha {facts.min_alpha} is below 1 / (n + 1) for the calibration sets {too_few}: the "
            "finite-sample quantile is infinite, nothing is emitted and the coverage is vacuous (E6)",
        )
    if has_ours and not facts.has_device_profile:
        conditional(
            "NO_DEVICE_PROFILE",
            "no device capability profile is declared (run_options.detector_params.ours.device_profile): every "
            "capability is absent and the attribution answers UNDETERMINED; the profile of the benchmark devices is an "
            "open decision",
        )
    if "B1" in names:
        flags.append(
            Guard(
                "B1_MINIMAL",
                "B1 is the minimal threshold baseline, per class only; no RESP, SYS or INT rule (F8)",
            )
        )
    if any(n.startswith("B5") for n in names) and not _lifted(
        "B5_NOT_PAPER_COMPARISON", accepted
    ):
        flags.append(
            Guard(
                "B5_NOT_PAPER_COMPARISON",
                "B5 as configured predicts RESP only: not the B5 comparison of the paper until D2 is decided (F6, F25)",
            )
        )
    flags.append(
        Guard(
            "CLOSING_STEP_C1_ONLY",
            "the closing-step truth of the last scored day holds C1 events only; a C2 or C3 event starting at the first "
            "instant of the tail day is not scored (builder.md, open decision)",
        )
    )
    if baselines and not _lifted("LATENCY_CONVENTION_OPEN", accepted):
        flags.append(
            Guard(
                "LATENCY_CONVENTION_OPEN",
                "the baselines report t_eval + D and the monitor t_eval: a delay comparison needs a decided time convention (F20)",
            )
        )
    if not _lifted("CONTAMINATION_POLICY_OPEN", accepted):
        flags.append(
            Guard(
                "CONTAMINATION_POLICY_OPEN",
                "the calibration days may hold injected events and the conformal methods are not affected equally (F19)",
            )
        )
    if any(n in ("B1", "B4") for n in names):
        flags.append(
            Guard(
                "SCORES_NOT_RANKED",
                "B1 and B4 are operating points: no AUROC or AP is computed for them (F13)",
            )
        )
    if "B2-iforest" in names or "B2" in names:
        flags.append(
            Guard(
                "B2_IFOREST_NOT_STRONGEST",
                "the joint Isolation Forest of B2 is not claimed to be the strongest anomaly-detection competitor (F14)",
            )
        )
    return GuardReport(tuple(hard), tuple(flags))


# ---- detectors -------------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DetectorEnvironment:
    """Everything a detector is built from (shared by all the detectors of a seed)."""

    config: ExperimentConfig
    options: RunOptions
    seed: int
    registry: Any
    templates: tuple[Any, ...]
    monitor: MonitorConfig | None
    plan_for_day: Callable[[ObservedDay], CarePlan]
    timing: Any | None
    profile: object | None
    params: Mapping[str, Any]


def _hint(function: Any, name: str) -> Any:
    hints = typing.get_type_hints(function)
    return hints[name]


def _timing_class() -> Any:
    """``TimingConfig`` of the baseline harness, through the annotation of B1 (it is not exported by the package root)."""
    return _hint(B1StaticThresholds.__init__, "timing")


def _build_profile(spec: Mapping[str, Any] | None) -> object | None:
    """A ``DeviceProfile`` from ``{node: {capability: value}}`` (None for no declaration: every capability absent).

    The classes are found through the annotations of ``extract_evidence``: the package root does not export them.
    """
    if not spec:
        return None
    try:
        profile_cls = next(
            a
            for a in typing.get_args(_hint(extract_evidence, "profile"))
            if a is not type(None)
        )
        caps_cls = typing.get_args(_hint(profile_cls, "nodes"))[1]
        profile: object = profile_cls(
            {node: caps_cls(**dict(caps)) for node, caps in spec.items()}
        )
        return profile
    except (KeyError, IndexError, StopIteration, TypeError) as exc:
        raise ConfigError(
            f"detector_params.device_profile is not usable: {exc}"
        ) from exc


def _params(env: DetectorEnvironment, name: str) -> Mapping[str, Any]:
    value = env.params.get(name, {})
    _need(isinstance(value, Mapping), f"detector_params.{name} must be a mapping")
    return value  # type: ignore[no-any-return]


def make_environment(
    config: ExperimentConfig,
    options: RunOptions,
    seed: int,
    *,
    plan_for_day: Callable[[ObservedDay], CarePlan] | None = None,
) -> DetectorEnvironment:
    """The registry, the templates, the shared timing and the plan lookup of a seed."""
    monitor = config.monitor
    registry_path = options.registry
    try:
        registry = load_registry(
            registry_path,
            step_ms=None if monitor is None else monitor.step_ms,
            allow_fixture_only=options.allow_fixture_only,
        )
        templates = tuple(load_templates(registry=registry))
    except Exception as exc:  # RegistryError, TemplateLibraryError: reported as a configuration problem
        raise ConfigError(f"registry: {exc}") from exc
    if monitor is not None and monitor.registry_version != registry.version():
        raise ConfigError(
            f"monitor.registry_version {monitor.registry_version!r} differs from the registry version {registry.version()!r}"
        )
    if plan_for_day is None:
        reader = open_benchmark(config.benchmark_manifest, view="observed")
        cache: dict[str, CarePlan] = {}

        def lookup(day: ObservedDay) -> CarePlan:
            if day.care_plan_id not in cache:
                cache[day.care_plan_id] = reader.care_plan(day.care_plan_id)
            return cache[day.care_plan_id]

        plan_for_day = lookup
    params = options.detector_params
    timing = None
    if monitor is not None and "timing_tail_ms" in params:
        tail = params["timing_tail_ms"]
        _need(
            _is_int(tail) and tail >= 0,
            "detector_params.timing_tail_ms must be a non-negative integer",
        )
        timing = _timing_class()(monitor.step_ms, monitor.reorder_delay_ms, tail)
    profile_spec = _params_dict(params, "ours").get("device_profile")
    return DetectorEnvironment(
        config,
        options,
        seed,
        registry,
        templates,
        monitor,
        plan_for_day,
        timing,
        _build_profile(profile_spec),
        params,
    )


def _params_dict(params: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = params.get(key, {})
    return value if isinstance(value, Mapping) else {}


def _forecaster_factory(
    env: DetectorEnvironment, *, with_deadline: bool
) -> Callable[[], Forecaster]:
    spec = _params_dict(env.params, "forecaster")
    _need(
        bool(spec) and "continuous" in spec,
        "detector_params.forecaster.continuous is required (persistence or autoregressive)",
    )
    assert env.monitor is not None
    step = env.monitor.step_ms
    kind = spec["continuous"]
    _need(
        kind in ("persistence", "autoregressive"),
        f"unknown continuous forecaster {kind!r}",
    )
    if kind == "autoregressive":
        _need(
            _is_int(spec.get("order")),
            "detector_params.forecaster.order is required for autoregressive",
        )
    deadline = bool(spec.get("deadline", False))

    def make() -> Forecaster:
        continuous: Forecaster = (
            PersistenceForecaster(step)
            if kind == "persistence"
            else AutoRegressiveForecaster(step, spec["order"])
        )
        if with_deadline and deadline:
            return CompositeForecaster([DeadlineForecaster(step), continuous])
        return continuous

    return make


def _extension(name: str) -> ModuleType | None:
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:
        if exc.name == name:
            return None
        raise


def _resolve_variant(name: str) -> PipelineComponents | None:
    for module_name in _EXTENSIONS:
        module = _extension(module_name)
        resolver = (
            getattr(module, "variant_components", None) if module is not None else None
        )
        if callable(resolver):
            components = resolver(name)
            if components is not None:
                if not isinstance(components, PipelineComponents):
                    raise ConfigError(
                        f"{module_name}.variant_components({name!r}) did not return PipelineComponents"
                    )
                return components
    return None


def build_detector(
    name: str, env: DetectorEnvironment, *, alpha: float | None = None
) -> Any:
    """The detector called ``name`` (``B1`` to ``B5``, ``ours``, ``ours-*``), built from the shared environment.

    ``alpha`` is the total level of the conformal methods (B4, B5, the proposed method), one instance per operating
    point. The baselines get one ``TimingConfig`` equal to the ``MonitorConfig`` of the proposed method, the same
    forecaster class (fitted on the same training days), the same ``plan_for_day`` and the default access policy
    (fairness audit, conventions of WS08). ``ConfigError`` for an unknown name or a missing operating parameter.
    """
    if name in BASELINE_NAMES:
        return _build_baseline(name, env, alpha)
    if _OURS_NAME.fullmatch(name) is None:
        raise ConfigError(f"unknown detector {name!r}")
    _need(env.monitor is not None, "ours needs a monitor configuration")
    assert env.monitor is not None
    components = PipelineComponents() if name == "ours" else _resolve_variant(name)
    if components is None:
        raise ConfigError(f"no extension module knows the detector variant {name!r}")
    monitor = env.monitor if alpha is None else replace(env.monitor, alpha=alpha)
    spec = _params_dict(env.params, "ours")
    predictive = components.use_forecaster and monitor.predictive
    return OursDetector(
        monitor,
        env.registry,
        env.templates,
        name=name,
        components=components,
        forecaster_factory=_forecaster_factory(env, with_deadline=True)
        if predictive
        else None,
        plan_for_day=env.plan_for_day,
        profile=env.profile,
        seed=env.seed,
        collect_episodes=bool(spec.get("collect_episodes", True)),
    )


def _build_baseline(name: str, env: DetectorEnvironment, alpha: float | None) -> Any:
    _need(
        env.timing is not None,
        "the baselines need detector_params.timing_tail_ms (and a monitor configuration)",
    )
    timing: Any = env.timing
    if name == "B1":
        return B1StaticThresholds(timing=timing, registry=env.registry)
    if name == "B3":
        return B3PlainSTL(env.templates, env.registry, timing=timing)
    if name.startswith("B2"):
        spec = _params_dict(env.params, "B2")
        mode = {"B2": "both", "B2-residual": "residual", "B2-iforest": "iforest"}[name]
        # a parameter that the mode does not use is refused by the baseline, so only the used ones are passed
        needed = {
            "residual": ("z_threshold",),
            "iforest": ("score_quantile",),
            "both": ("z_threshold", "score_quantile"),
        }[mode]
        for key in needed:
            _need(
                key in spec,
                f"detector_params.B2.{key} is required (no default, none tuned on the test split)",
            )
        kwargs: dict[str, Any] = {
            "mode": mode,
            "seed": env.seed,
            "timing": timing,
            **{key: spec[key] for key in needed},
        }
        if mode != "iforest":
            kwargs["signals"] = spec.get("signals")
        if mode != "residual":
            _need(
                "feature_step_ms" in spec,
                "detector_params.B2.feature_step_ms is required for the forest modes",
            )
            kwargs["feature_step_ms"] = spec["feature_step_ms"]
            kwargs["plan_for_day"] = env.plan_for_day
        forecaster = (
            None
            if mode == "iforest"
            else _forecaster_factory(env, with_deadline=False)()
        )
        return B2AnomalyDetection(forecaster, **kwargs)
    _need(alpha is not None, f"{name} needs a level alpha")
    assert alpha is not None
    forecaster = _forecaster_factory(env, with_deadline=False)()
    if name == "B4":
        spec = _params_dict(env.params, "B4")
        return B4ConformalOnly(
            forecaster,
            SplitConformal,
            alpha=alpha,
            unit=spec.get("unit", "day_max"),
            signals=spec.get("signals"),
            timing=timing,
        )
    spec = _params_dict(env.params, name)
    level: float | Fraction = alpha
    if name == "B5-bonferroni":
        _need(
            _is_int(spec.get("n_tests")) and spec["n_tests"] >= 1,
            "detector_params.B5-bonferroni.n_tests is required",
        )
        level = BonferroniAllocation().per_test_exact(alpha, spec["n_tests"])
    built = B5ConformalSTL(
        env.templates,
        env.registry,
        forecaster,
        SplitConformal,
        alpha=level,
        aggregation="per_template" if name == "B5-per-template" else "conjunction",
        timing=timing,
        plan_for_day=env.plan_for_day,
    )
    built.name = (
        name  # the variant at the allocated level is a B5 run under its own name
    )
    return built


# ---- hooks -----------------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class HookResult:
    """What an analysis hook returns: free-form ``analysis`` and ``metrics`` limited to the contract metric names."""

    analysis: Mapping[str, Any] = field(default_factory=dict)
    metrics: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RunContext:
    """What a hook receives for one seed (all read-only): the configuration, the split, the fitted main detectors, their
    outputs (detections per patient and day) and matchings, the per-day tables, the bootstrap generator and the two
    readers (the full one is for scoring code only)."""

    config: ExperimentConfig
    options: RunOptions
    seed: int
    split: Mapping[str, tuple[str, ...]]
    detectors: Mapping[str, Any]
    outputs: Mapping[str, Mapping[str, Sequence[Detection]]]
    matchings: Mapping[str, Matching]
    tables: Mapping[str, np.ndarray]
    units: Sequence[tuple[str, int]]
    rng: np.random.Generator
    environment: DetectorEnvironment
    reader_observed: Any
    reader_full: Any


def _collect_hooks(experiment_id: str) -> list[Callable[[RunContext], HookResult]]:
    hooks: list[Callable[[RunContext], HookResult]] = []
    for module_name in _HOOK_MODULES:
        module = _extension(module_name)
        provider = getattr(module, "hooks_for", None) if module is not None else None
        if callable(provider):
            hooks.extend(provider(experiment_id))
    return hooks


def _merge(target: dict[str, Any], source: Mapping[str, Any], path: str) -> None:
    for key, value in source.items():
        here = f"{path}.{key}" if path else str(key)
        if key not in target or target[key] is None:
            target[key] = value
        elif isinstance(target[key], dict) and isinstance(value, Mapping):
            _merge(target[key], value, here)
        elif target[key] != value:
            raise ConfigError(
                f"a hook contributes {here!r}, which the runner or another hook already wrote"
            )


# ---- git revision ----------------------------------------------------------------------------------------------------


def current_git_rev() -> str:
    """``git rev-parse HEAD``, with ``-dirty`` when a tracked file differs from the commit; ``unknown`` without a repository."""
    cwd = Path(__file__).resolve().parent
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            cwd=cwd,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    revision = head.stdout.strip() if head.returncode == 0 else ""
    if not revision:
        return "unknown"
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            capture_output=True,
            text=True,
            check=False,
            cwd=cwd,
        )
    except (OSError, subprocess.SubprocessError):
        return revision
    return (
        f"{revision}-dirty"
        if status.returncode == 0 and status.stdout.strip()
        else revision
    )


# ---- fit days --------------------------------------------------------------------------------------------------------


class _ObservedOnlyDay(BenchmarkDay):
    """A benchmark day whose latent trace and ground truth raise on access: what ``fit`` is given."""

    def __init__(self, observed: ObservedDay) -> None:
        object.__setattr__(self, "observed", observed)

    @property
    def latent(self) -> Any:
        raise TruthAccessError("the latent trace of a day given to a detector was read")

    @property
    def ground_truth(self) -> Any:
        raise TruthAccessError("the ground truth of a day given to a detector was read")

    def __repr__(self) -> str:
        return f"_ObservedOnlyDay({self.observed.patient_id!r}, day {self.observed.day_index})"

    def __eq__(self, other: object) -> bool:
        return self is other

    def __hash__(self) -> int:
        return id(self)


# ---- scoring ---------------------------------------------------------------------------------------------------------


@dataclass(slots=True)
class _Instance:
    name: str
    alpha: float | None
    detector: Any
    main: bool
    detections: dict[str, list[Detection]] = field(default_factory=dict)
    runs: dict[tuple[str, int], Any] = field(
        default_factory=dict
    )  # (patient, day) -> OursRunDetails
    stats: Counter[str] = field(default_factory=Counter)
    b1_rules: list[tuple[str, ...]] = field(default_factory=list)
    n_clipped: int = 0


@dataclass(slots=True)
class _Scored:
    matching: Matching
    table: np.ndarray
    n_dropped_tail: int
    false_alarm_kinds: Counter[str]


def _unit_of_detection(t_ms: int, last_day: int, tail_start: int) -> int:
    """The scored day that owns an instant, -1 for the unscored tail (module docstring)."""
    if t_ms > tail_start:
        return -1
    return min(max(t_ms, 0) // T_DAY_MS, last_day)


def _score_patient(
    events: Sequence[tuple[GroundTruthEvent, int]],
    detections: Sequence[Detection],
    n_days: int,
    match: MatchConfig,
) -> _Scored:
    last_day = n_days - 1
    tail_start = n_days * T_DAY_MS
    matching = match_events([e for e, _ in events], detections, match, n_days=n_days)
    det_days = [_unit_of_detection(d.t_ms, last_day, tail_start) for d in matching.det]
    # a matched detection counts through its event; a duplicate or a false alarm in the unscored tail is dropped
    table = matching.table([day for _, day in events], det_days, n_days)
    dropped = sum(
        1
        for i in (*matching.false_alarm_index, *matching.duplicate_index)
        if det_days[i] < 0
    )
    kinds: Counter[str] = Counter()
    for i in matching.false_alarm_index:
        if det_days[i] < 0:
            continue
        item = matching.det[i]
        if not isinstance(item, Alert):
            kinds["unattributed_detection"] += 1
        elif item.verdict is VerdictState.PREDICTED_VIOLATION:
            kinds["predicted_violation"] += 1
        else:
            kinds["violated"] += 1
    return _Scored(matching, table, dropped, kinds)


# ---- the run ---------------------------------------------------------------------------------------------------------


def _clean(value: Any) -> Any:
    """JSON-ready: numpy scalars to Python, NaN and infinities to None, mappings with string keys."""
    if isinstance(value, Mapping):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, np.ndarray):
        return [_clean(v) for v in value.tolist()]
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        number = float(value)
        return number if math.isfinite(number) else None
    if value is None or isinstance(value, str):
        return value
    raise TypeError(f"cannot write {type(value).__name__} to metrics.json")


def _num(x: float) -> float | None:
    return float(x) if math.isfinite(x) else None


@dataclass(slots=True)
class _Weights:
    """The bootstrap replicates of a seed: patient-days (``days``) and patients (``patients``, None when there is a single
    patient and the cluster bootstrap has nothing to resample). ``nan`` collects, per labelled interval, the number of
    replicates in which the statistic was undefined (they are left out of the interval, never silently)."""

    days: np.ndarray
    patients: np.ndarray | None
    level: float
    nan: dict[str, dict[str, int]] = field(default_factory=dict)

    def scalar(
        self,
        table: np.ndarray,
        stat: Callable[[np.ndarray], float],
        label: str = "",
    ) -> dict[str, Any]:
        total = table.sum(axis=0)
        lo, hi, n_day = ci_with_report(table, stat, self.days, self.level)
        n_cluster = 0
        if self.patients is None:
            clo = chi = math.nan
        else:
            clo, chi, n_cluster = ci_with_report(table, stat, self.patients, self.level)
        if label and (n_day or n_cluster):
            self.nan[label] = {"day": n_day, "cluster": n_cluster}
        return {
            "value": _num(stat(total)),
            "ci_lo": _num(lo),
            "ci_hi": _num(hi),
            "ci_cluster_lo": _num(clo),
            "ci_cluster_hi": _num(chi),
        }


def _percentiles(values: Sequence[float], qs: Sequence[float]) -> list[float | None]:
    if not values:
        return [None for _ in qs]
    return [
        float(x) for x in np.percentile(np.asarray(values, dtype=np.float64), list(qs))
    ]


def _prf_stat(cls: str, key: str) -> Callable[[np.ndarray], float]:
    def stat(row: np.ndarray) -> float:
        return table_prf(row)[cls][key]

    return stat


def _ece_stat(bins: int) -> Callable[[np.ndarray], float]:
    def stat(row: np.ndarray) -> float:
        n = row[0::3]
        total = float(n.sum())
        if total <= 0:
            return math.nan
        used = n > 0
        gap = np.abs(row[1::3][used] / n[used] - row[2::3][used] / n[used])
        return float((n[used] / total * gap).sum())

    return stat


def _ece_table(
    per_unit: Sequence[Sequence[tuple[float, bool]]], bins: int
) -> np.ndarray:
    table = np.zeros((len(per_unit), 3 * bins), dtype=np.float64)
    for u, items in enumerate(per_unit):
        for rho, hit in items:
            b = bin_index(rho, bins)
            table[u, 3 * b] += 1
            table[u, 3 * b + 1] += rho
            table[u, 3 * b + 2] += 1.0 if hit else 0.0
    return table


def _coverage_blocks(
    detector: OursDetector,
    episodes: Sequence[tuple[Any, int]],
    alphas: Sequence[float],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]] | None:
    """The in-distribution coverage and mean interval width of the split calibrator over the test episodes.

    For each total level the per-test level of a day is ``alpha / n_tests`` (ADR-060), computed in exact arithmetic;
    episodes of one level are scored together, and the levels are pooled by the number of episodes. ``alert_level`` is the
    empirical form of Proposition 1 (``1 - P(alert emitted and sigma_true >= 0)``), ``nominal`` the pooled ``1 - level``
    it is compared with, ``band_level`` the share of episodes with ``sigma_true <= sigma_hat + q``. The width is that of the
    two-sided band ``[sigma_hat + q^lo, sigma_hat + q]`` clipped to [-1, 1], which exists for a per-test level of at
    most one half (above it the two quantiles cross): the value is then ``None``.
    """
    calibrator = detector.calibrator
    if calibrator is None or calibrator.mode != "split" or not episodes:
        return None
    variant = detector.config.variant
    allocation = BonferroniAllocation()
    coverage: list[dict[str, Any]] = []
    widths: list[dict[str, Any]] = []
    lower = getattr(calibrator, "quantile_lower", None)
    notes: dict[str, Any] = {"n_episodes": len(episodes), "per_alpha": []}
    for alpha in alphas:
        groups: dict[Fraction, list[Any]] = {}
        for episode, n_tests in episodes:
            if n_tests >= 1:
                groups.setdefault(allocation.per_test_exact(alpha, n_tests), []).append(
                    episode
                )
        total = sum(len(g) for g in groups.values())
        if not total:
            continue
        alert = band = nominal = 0.0
        two_sided = True
        intervals: list[tuple[float, float]] = []
        levels: list[float] = []
        for level, group in sorted(groups.items()):
            preds = [
                calibrator.predict(e.sigma_hat, level, variant=variant) for e in group
            ]
            truth = [e.sigma_true for e in group]
            q = calibrator.quantile(level)
            weight = len(group) / total
            alert += weight * empirical_coverage(preds, truth, float(level))
            band += weight * residual_coverage([e.sigma_hat for e in group], truth, q)
            nominal += weight * (1.0 - float(level))
            if level > Fraction(1, 2) or not callable(lower):
                two_sided = (
                    False  # the lower and the upper quantile cross above one half
                )
            else:
                low = lower(level)
                intervals.extend(
                    (max(-1.0, e.sigma_hat + low), min(1.0, e.sigma_hat + q))
                    for e in group
                )
            levels.append(float(level))
        coverage.append(
            {
                "alpha": alpha,
                "nominal": nominal,
                "alert_level": alert,
                "band_level": band,
            }
        )
        widths.append(
            {
                "alpha": alpha,
                "value": (
                    sum(hi - lo for lo, hi in intervals) / len(intervals)
                    if two_sided and len(intervals) == total
                    else None
                ),
            }
        )
        notes["per_alpha"].append(
            {
                "alpha": alpha,
                "per_test_levels": sorted(set(levels)),
                "n_episodes": total,
            }
        )
    if not coverage:
        return None
    return coverage, widths, notes


def _subtype_recall(matching: Matching) -> dict[str, Any]:
    out: dict[str, dict[str, int]] = {}
    matched = {p.gt_index for p in matching.pairs}
    for i, event in enumerate(matching.gt):
        key = f"{event.cls.value}/{event.subtype}"
        entry = out.setdefault(key, {"n_events": 0, "n_matched": 0})
        entry["n_events"] += 1
        entry["n_matched"] += 1 if i in matched else 0
    return {
        k: {**v, "recall": v["n_matched"] / v["n_events"]}
        for k, v in sorted(out.items())
    }


def _preflight_registry(env: DetectorEnvironment, names: Sequence[str]) -> None:
    """Fail before the run, not in the middle of it, when the registry cannot feed the proposed method.

    The attribution layer needs the evidence thresholds of ``docs/models`` (open point OPF-6: the registry 0.2.0 lacks some
    of them; the error names those still missing) and a priority for every template whose violation can become an alert (``priority_sys`` and ``priority_int``
    are unset in 0.2.0): a run that reaches such an alert would stop with an error after hours of computation.
    """
    if not any(n.startswith("ours") for n in names):
        return
    try:
        RuleAttributor(env.registry, env.templates)
    except Exception as exc:  # RegistryError: a name the rule or the extractor requests
        raise ConfigError(
            f"the registry cannot feed the attribution layer of the proposed method: {exc}"
        ) from exc
    unset = getattr(env.registry, "unset_names", None)
    if callable(unset):
        needed = {
            n
            for t in env.templates
            for n in (t.priority_param, t.scale_param, t.max_verdict_latency_param)
        }
        missing = sorted(needed & set(unset()))
        if missing:
            raise ConfigError(
                f"the registry has unset rows that the proposed method needs: {missing}"
            )


def _validate_plans(env: DetectorEnvironment, plans: Mapping[str, CarePlan]) -> None:
    """F26: a plan the monitor refuses is not run by any method."""
    if env.monitor is None:
        return
    config = replace(env.monitor, predictive=False, alpha=None)
    for plan_id, plan in sorted(plans.items()):
        try:
            StreamingMonitor(config, env.registry, env.templates).load(plan)
        except Exception as exc:
            raise ConfigError(
                f"the monitor refuses the care plan {plan_id!r}: {exc}"
            ) from exc


def _plan_cache(
    reader: Any, ids: Sequence[str]
) -> tuple[Callable[[ObservedDay], CarePlan], dict[str, CarePlan]]:
    plans: dict[str, CarePlan] = {}

    def lookup(day: ObservedDay) -> CarePlan:
        if day.care_plan_id not in plans:
            plans[day.care_plan_id] = reader.care_plan(day.care_plan_id)
        return plans[day.care_plan_id]

    return lookup, plans


def _truth_events(
    reader_full: Any, patient: str
) -> tuple[list[tuple[GroundTruthEvent, int]], int]:
    """The events of a patient with the day of their file, then the closing-step events with the last scored day."""
    days = reader_full.days(patient)
    events: list[tuple[GroundTruthEvent, int]] = []
    try:
        for d in days:
            events.extend((e, d) for e in reader_full.truth(patient, d).ground_truth)
        closing = reader_full.closing_step_truth(patient)
    except Exception as exc:
        raise ConfigError(f"truth of patient {patient!r}: {exc}") from exc
    events.extend((e, days[-1]) for e in closing)
    return events, len(closing)


def _at_shared_step(item: Detection) -> bool:
    """A detection at the closing step of a day, which is also the first step of the next one (ADR-064)."""
    return item.t_ms > 0 and item.t_ms % T_DAY_MS == 0


def _shared_key(item: Detection) -> tuple[Any, ...]:
    """What makes two detections at a shared step the same: the instance and the instant for an alert, the instant,
    the label and the score for another detection."""
    if isinstance(item, Alert):
        return ("alert", item.xi.instance_key, item.t_ms)
    return ("detection", item.t_ms, item.label, item.score)


def _run_patient(
    inst: _Instance,
    patient: str,
    days: Sequence[ObservedDay],
    env: DetectorEnvironment,
    options: RunOptions,
) -> list[Detection]:
    """Run one instance over the scored days of a patient, one day at a time (module docstring)."""
    out: list[Detection] = []
    detector = inst.detector
    is_ours = isinstance(detector, OursDetector)
    baseline = not inst.name.startswith("ours")
    shift = (
        env.monitor.reorder_delay_ms
        if baseline
        and options.baseline_time == "subtract_reorder_delay"
        and env.monitor
        else 0
    )
    previous_shared: set[tuple[Any, ...]] = set()
    for d, obs in enumerate(days):
        plan = env.plan_for_day(obs)
        kwargs: dict[str, Any] = {}
        if options.history == "ours" and is_ours and d > 0:
            kwargs["history"] = list(days[max(0, d - MAX_HISTORY_DAYS) : d])
        emitted = detector.run(obs, plan, None, **kwargs)
        inst.stats["n_emitted"] += len(emitted)
        shared = {_shared_key(x) for x in emitted if _at_shared_step(x)}
        inst.stats["n_at_shared_step"] += sum(1 for x in emitted if _at_shared_step(x))
        inst.stats["n_repeating_previous_day"] += sum(
            1
            for x in emitted
            if _at_shared_step(x) and _shared_key(x) in previous_shared
        )
        previous_shared = shared
        for item in emitted:
            if shift:
                item = replace(item, t_ms=max(0, item.t_ms - shift))
            if (
                options.after_close == "clip"
                and item.t_ms > (obs.day_index + 1) * T_DAY_MS
            ):
                inst.n_clipped += 1
                continue
            out.append(item)
        if isinstance(detector, OursDetector):
            run = detector.last_run
            if run is not None:
                inst.runs[(patient, d)] = run
                gate = run.presence_samples_without_availability_marks
                if gate is None:
                    inst.stats["int_gate_unknown"] += 1
                else:
                    inst.stats["int_gate"] += gate
        else:
            stats = getattr(detector, "run_stats", None)
            rules = getattr(stats, "rules_active", None)
            if rules is not None:
                inst.b1_rules.append(tuple(rules))
            gate = getattr(stats, "presence_samples_without_availability_marks", None)
            if gate is not None:
                inst.stats["int_gate"] += int(gate)
    return out


def _fit_all(
    config: ExperimentConfig,
    options: RunOptions,
    env: DetectorEnvironment,
    factory: Callable[..., Any],
    train: Sequence[BenchmarkDay],
    calib: Sequence[BenchmarkDay],
) -> list[_Instance]:
    instances: list[_Instance] = []
    for name in config.detectors:
        if not baseline_has_alpha(name):
            detector = factory(name, env, alpha=None)
            detector.fit(list(train), list(calib))
            instances.append(_Instance(name, None, detector, True))
            continue
        base: Any = None
        for alpha in options.alpha_grid:
            if base is not None and hasattr(base, "at_alpha"):
                detector = base.at_alpha(alpha)
            else:
                detector = factory(name, env, alpha=alpha)
                detector.fit(list(train), list(calib))
                if base is None:
                    base = detector
            instances.append(_Instance(name, alpha, detector, alpha == config.alpha))
    return instances


def _scalar_block_attr(
    matching: Matching, table: np.ndarray, weights: _Weights
) -> tuple[dict[str, Any] | None, list[dict[str, Any]] | None]:
    if matching.attributes is not True:
        return None, None
    total = table.sum(axis=0)
    cells = {
        t: {p: round(float(total[_col(f"conf_{t}_{p}")])) for p in LABEL_COLUMNS}
        for t in CLASSES
    }
    block = {
        "matrix": cells,
        "macro_f1": weights.scalar(table, table_macro_f1),
        "abstention_rate": weights.scalar(table, table_abstention_rate),
        "accuracy_answered": weights.scalar(table, table_accuracy_answered),
        "n_unresolved": round(float(total[_col("unresolved")])),
    }
    points = accuracy_vs_coverage_from_table(total)
    return block, points


def _col(name: str) -> int:
    from ralmon.eval.metrics import COLUMNS

    return COLUMNS.index(name)


def accuracy_vs_coverage_from_table(total: np.ndarray) -> list[dict[str, Any]]:
    from ralmon.eval.metrics import table_coverage_answered

    return [
        {
            "coverage": _num(table_coverage_answered(total)),
            "accuracy": _num(table_accuracy_answered(total)),
        }
    ]


def _write_seed(
    root: Path,
    config: ExperimentConfig,
    options: RunOptions,
    seed: int,
    rev: str,
    document: Mapping[str, Any],
) -> Path:
    folder = root / config.experiment_id / str(seed)
    folder.mkdir(parents=True, exist_ok=True)
    text = json.dumps(
        _clean(document), sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False
    )
    (folder / "metrics.json").write_text(text + "\n", encoding="utf-8")
    (folder / "config.yaml").write_text(
        dump_experiment(replace(config, seeds=[seed]), options, base=folder),
        encoding="utf-8",
    )
    (folder / "git_rev.txt").write_text(rev + "\n", encoding="utf-8")
    return folder


def _tail_of(options: RunOptions) -> int | None:
    tail = options.detector_params.get("timing_tail_ms")
    return tail if isinstance(tail, int) and not isinstance(tail, bool) else None


def _required_tail(
    env: DetectorEnvironment, monitor: MonitorConfig | None
) -> int | None:
    """``required_tail_ms`` for the registry of the run (RESP ``delta2``; 0 when the registry has none)."""
    if monitor is None:
        return None
    try:
        delta2 = int(float(env.registry.get("delta2").value))
    except (
        RegistryError,
        ValueError,
        TypeError,
    ):  # a registry without the row: the day-end convention decides
        delta2 = 0
    return required_tail_ms(delta2, monitor.reorder_delay_ms)


def run_experiment(
    config: ExperimentConfig,
    options: RunOptions,
    output_root: str | Path,
    *,
    git_rev: Callable[[], str] = current_git_rev,
    detector_factory: Callable[..., Any] | None = None,
) -> list[Path]:
    """Run every seed of an experiment and write ``output_root/<experiment_id>/<seed>/`` (module docstring).

    ``detector_factory(name, env, *, alpha=None)`` replaces ``build_detector`` (tests and special experiments). Returns the
    seed directories in the order of ``config.seeds``. Nothing is written for a seed whose guards fail hard.
    """
    factory = detector_factory if detector_factory is not None else build_detector
    try:
        reader_obs = open_benchmark(config.benchmark_manifest, view="observed")
        reader_full = open_benchmark(config.benchmark_manifest)
        manifest = reader_full.manifest
    except Exception as exc:
        raise ConfigError(f"benchmark {config.benchmark_manifest!r}: {exc}") from exc
    revision = git_rev()
    ids = list(reader_full.patient_ids(role="patient"))
    _need(bool(ids), "the benchmark has no virtual patient")
    twin_ids = (
        list(reader_full.patient_ids(role="confounder_pair"))
        if options.twins != "exclude"
        else []
    )
    lookup, plans = _plan_cache(reader_obs, ids)
    first_env = make_environment(config, options, config.seeds[0], plan_for_day=lookup)
    without_tail = tuple(
        p for p in (*ids, *twin_ids) if reader_full.tail_day(p) is None
    )
    monitor = config.monitor
    static = RunFacts(
        detectors=tuple(config.detectors),
        benchmark_fixture_only=bool(manifest.fixture_only),
        registry_fixture_only=bool(getattr(first_env.registry, "fixture_only", False)),
        step_ms=monitor.step_ms if monitor else 1,
        reorder_delay_ms=monitor.reorder_delay_ms if monitor else 0,
        patients_without_tail_day=without_tail,
        history=options.history,
        twins=options.twins,
        n_seeds=len(config.seeds),
        has_device_profile=first_env.profile is not None,
        timing_tail_ms=_tail_of(options),
        required_tail_ms=_required_tail(first_env, monitor),
        min_alpha=(
            min(options.alpha_grid)
            if any(baseline_has_alpha(n) for n in config.detectors)
            else None
        ),
    )
    evaluate_guards(static, options).raise_if_failed()
    folders: list[Path] = []
    for seed in config.seeds:
        document = _run_seed(
            config,
            options,
            seed,
            factory,
            reader_obs,
            reader_full,
            manifest,
            ids,
            twin_ids,
            lookup,
            plans,
            static,
        )
        folders.append(
            _write_seed(Path(output_root), config, options, seed, revision, document)
        )
    return folders


def _run_seed(
    config: ExperimentConfig,
    options: RunOptions,
    seed: int,
    factory: Callable[..., Any],
    reader_obs: Any,
    reader_full: Any,
    manifest: Any,
    ids: Sequence[str],
    twin_ids: Sequence[str],
    lookup: Callable[[ObservedDay], CarePlan],
    plans: dict[str, CarePlan],
    static: RunFacts,
) -> dict[str, Any]:
    env = make_environment(config, options, seed, plan_for_day=lookup)
    split = split_patients(ids, config.split, seed)
    by_split = {
        s: tuple(sorted(p for p, v in split.items() if v == s)) for s in _SPLITS
    }
    test_patients = list(by_split["test"])
    if options.twins == "include":
        test_patients = sorted([*test_patients, *twin_ids])
    _need(bool(test_patients), "the test split is empty: no patient to score")
    # evaluation-side reading of the calibration days (never given to a detector): the contamination of F19
    calib_pairs = [(p, d) for p in by_split["calibration"] for d in reader_obs.days(p)]
    injected = {
        (p, d)
        for p, d in calib_pairs
        if any(e.injected for e in reader_full.truth(p, d).ground_truth)
    }
    drop = injected if options.calibration_days == "without_injected" else set()
    train_days: list[BenchmarkDay] = [
        _ObservedOnlyDay(reader_obs.observed(p, d))
        for p in by_split["train"]
        for d in reader_obs.days(p)
    ]
    calib_days: list[BenchmarkDay] = [
        _ObservedOnlyDay(reader_obs.observed(p, d))
        for p, d in calib_pairs
        if (p, d) not in drop
    ]
    for p in (*by_split["train"], *by_split["calibration"], *test_patients, *twin_ids):
        for d in reader_obs.days(p):
            lookup(reader_obs.observed(p, d))
    _preflight_registry(env, config.detectors)
    _validate_plans(env, plans)
    instances = _fit_all(config, options, env, factory, train_days, calib_days)
    test_days = {
        p: [reader_obs.observed(p, d) for d in reader_obs.days(p)]
        for p in test_patients
    }
    units = [(p, d) for p in test_patients for d in range(len(test_days[p]))]
    for inst in instances:
        for p in test_patients:
            inst.detections[p] = _run_patient(inst, p, test_days[p], env, options)
    # dynamic guards
    b1 = next((i for i in instances if i.name == "B1"), None)
    b1_rules: tuple[str, ...] | None = None
    if b1 is not None and b1.b1_rules:
        b1_rules = next((r for r in b1.b1_rules if r != _B1_RULES), _B1_RULES)
    gates = {
        i.name: int(i.stats["int_gate"])
        for i in instances
        if i.main and i.stats["int_gate"]
    }
    unknown = tuple(i.name for i in instances if i.main and i.stats["int_gate_unknown"])
    episodes_n = {
        i.name: int(i.detector.n_calibration_episodes)
        for i in instances
        if i.main and hasattr(i.detector, "n_calibration_episodes")
    }
    facts = replace(
        static,
        b1_rules_active=b1_rules,
        int_gate=gates,
        int_gate_unknown=unknown,
        calibration_episodes=episodes_n,
    )
    report = evaluate_guards(facts, options)
    report.raise_if_failed()

    truth = {p: _truth_events(reader_full, p) for p in test_patients}
    n_closing = sum(c for _, c in truth.values())
    patients_of_units = [p for p, _ in units]
    n_clusters = len(set(patients_of_units))
    weights = _Weights(
        bootstrap_weights(len(units), options.n_bootstrap, seed),
        bootstrap_weights(
            len(units), options.n_bootstrap, seed, clusters=patients_of_units
        )
        if n_clusters >= 2
        else None,
        options.ci_level,
    )
    metrics: dict[str, dict[str, Any]] = {name: {} for name in METRIC_NAMES}
    detections_info: dict[str, Any] = {}
    fa_kinds: dict[str, Any] = {}
    shared_steps: dict[str, Any] = {}
    subtype: dict[str, Any] = {}
    ours_info: dict[str, Any] = {}
    outputs: dict[str, Mapping[str, Sequence[Detection]]] = {}
    matchings: dict[str, Matching] = {}
    tables: dict[str, np.ndarray] = {}
    mains: dict[str, Any] = {}
    curves: dict[str, list[dict[str, Any]]] = {}
    for inst in instances:
        scored = {
            p: _score_patient(
                truth[p][0], inst.detections[p], len(test_days[p]), config.match
            )
            for p in test_patients
        }
        matching = Matching.concat([scored[p].matching for p in test_patients])
        table = np.vstack([scored[p].table for p in test_patients])
        total = table.sum(axis=0)
        prf = table_prf(total)
        curves.setdefault(inst.name, []).append(
            {
                "alpha": inst.alpha,
                "false_alarms_per_patient_day": _num(table_fa_per_day(total)),
                "recall": _num(prf["any"]["recall"]),
            }
        )
        if not inst.main:
            continue
        name = inst.name
        mains[name] = inst.detector
        outputs[name] = inst.detections
        matchings[name] = matching
        tables[name] = table
        dropped = sum(s.n_dropped_tail for s in scored.values())
        emitted = int(inst.stats["n_emitted"])
        shared_steps[name] = {
            "n_at_shared_step": int(inst.stats["n_at_shared_step"]),
            "n_repeating_previous_day": int(inst.stats["n_repeating_previous_day"]),
        }
        kinds: Counter[str] = Counter()
        for scored_patient in scored.values():
            kinds.update(scored_patient.false_alarm_kinds)
        fa_kinds[name] = dict(sorted(kinds.items()))
        detections_info[name] = {
            "n_emitted": emitted,
            "n_clipped_after_close": inst.n_clipped,
            "n_dropped_in_unscored_tail": dropped,
            "n_scored": emitted - inst.n_clipped - dropped,
        }
        metrics["per_class_prf"][name] = {
            c: {
                k: weights.scalar(
                    table, _prf_stat(c, k), f"per_class_prf.{name}.{c}.{k}"
                )
                for k in ("precision", "recall", "f1")
            }
            for c in (*CLASSES, "any")
        }
        delays = sorted(p.delay_ms for p in matching.pairs)
        p05, p25, p50, p75, p95 = _percentiles(delays, (5, 25, 50, 75, 95))
        metrics["detection_delay_ms"][name] = {
            "n_matched": len(delays),
            "values_ms": delays,
            "p05": p05,
            "p25": p25,
            "p50": p50,
            "p75": p75,
            "p95": p95,
            "mean": weights.scalar(
                table, table_delay_mean, f"detection_delay_ms.{name}.mean"
            ),
            "fraction_early": weights.scalar(
                table, table_early_fraction, f"detection_delay_ms.{name}.fraction_early"
            ),
        }
        fa = weights.scalar(
            table, table_fa_per_day, f"false_alarms_per_patient_day.{name}"
        )
        fa["n_false_alarms"] = round(float(total[_col("false_alarms")]))
        fa["duplicates_per_patient_day"] = _num(
            float(total[_col("duplicates")]) / float(total[_col("days")])
        )
        metrics["false_alarms_per_patient_day"][name] = fa
        block, points = _scalar_block_attr(matching, table, weights)
        metrics["attribution_confusion"][name] = block
        metrics["accuracy_vs_coverage"][name] = points
        subtype[name] = _subtype_recall(matching)
        if isinstance(inst.detector, OursDetector):
            ours_info[name] = _ours_block(inst, units, weights, metrics, options)
        # not applicable to a detector without an entry above
    for name in config.detectors:
        for metric in METRIC_NAMES:
            metrics[metric].setdefault(name, None)
        metrics["recall_vs_false_alarm_curve"][name] = sorted(
            curves[name], key=lambda e: (e["alpha"] is None, e["alpha"] or 0.0)
        )
    context_split = {k: v for k, v in by_split.items()}
    twins_info = _twins_block(
        config, options, env, reader_full, reader_obs, twin_ids, mains
    )
    analysis: dict[str, Any] = {
        "run": {
            "split": {k: list(v) for k, v in context_split.items()},
            "detections": detections_info,
            "false_alarms_by_kind": fa_kinds,
            "closing_step": {
                "n_events": n_closing,
                "classes": ["C1"],
                "n_patients_without_tail_day": len(static.patients_without_tail_day),
            },
            "twins": twins_info,
            "calibration": {
                "policy": options.calibration_days,
                "n_calibration_days": len(calib_pairs),
                "n_with_injected_event": len(injected),
                "n_used": len(calib_days),
            },
            "policies": {
                "history": options.history,
                "after_close": options.after_close,
                "baseline_time": options.baseline_time,
                "twins": options.twins,
                "calibration_days": options.calibration_days,
            },
            "recall_by_subtype": subtype,
            "shared_step_detections": shared_steps,
            "bootstrap": {
                "n_replicates": options.n_bootstrap,
                "n_units": len(units),
                "n_clusters": n_clusters,
                "degenerate_days": len(units) < 2,
                "degenerate_clusters": n_clusters < 2,
                "nan_replicates": weights.nan,
            },
            "ours": ours_info,
            "int_gate": gates,
        }
    }
    document: dict[str, Any] = dict(metrics)
    document["analysis"] = analysis
    document["meta"] = _meta(
        config, options, seed, manifest, env, test_patients, units, report, facts
    )
    _run_hooks(
        document,
        RunContext(
            config,
            options,
            seed,
            {k: tuple(v) for k, v in by_split.items()},
            mains,
            outputs,
            matchings,
            tables,
            units,
            np.random.default_rng([seed, STREAM_BOOTSTRAP]),
            env,
            reader_obs,
            reader_full,
        ),
    )
    for key in options.required_analysis:
        node: Any = analysis
        for part in key.split("."):
            node = node.get(part) if isinstance(node, Mapping) else None
        _need(
            node is not None,
            f"run_options.required_analysis: analysis.{key} is missing",
        )
    return document


def _meta(
    config: ExperimentConfig,
    options: RunOptions,
    seed: int,
    manifest: Any,
    env: DetectorEnvironment,
    test_patients: Sequence[str],
    units: Sequence[tuple[str, int]],
    report: GuardReport,
    facts: RunFacts,
) -> dict[str, Any]:
    return {
        "experiment_id": config.experiment_id,
        "seed": seed,
        "n_test_patients": len(test_patients),
        "n_test_patient_days": len(units),
        "detectors": list(config.detectors),
        "match": {
            "tolerance_ms": config.match.tolerance_ms,
            "time_reference": config.match.time_reference,
        },
        "alpha": config.alpha,
        "alpha_grid": list(options.alpha_grid),
        "prior_source": manifest.prior_source_name,
        "coverage_qualifier": COVERAGE_QUALIFIER,
        "bootstrap": {
            "n_resamples": options.n_bootstrap,
            "level": options.ci_level,
            "unit": "patient_day",
            "headline_interval": "cluster",
            "day_level_interval": (
                "ci_lo and ci_hi resample patient-days and are reported for reference only: the days of a patient are "
                "correlated, so that interval is anti-conservative; the headline interval is ci_cluster_lo and "
                "ci_cluster_hi (patients resampled)"
            ),
        },
        "interval_width_note": (
            "mean_interval_width is the width of the two-sided band [sigma_hat + q_lo, sigma_hat + q] of the split "
            "calibrator, which has the per-test level alpha' in each tail: its coverage is 1 - 2 alpha', not the "
            "nominal 1 - alpha' that empirical_coverage.nominal prints next to it; it is null where alpha' > 1/2"
        ),
        "headline": options.headline,
        "benchmark_version": manifest.benchmark_version,
        "generator_git_rev": manifest.generator_git_rev,
        "registry_version": env.registry.version(),
        "latency_convention": (
            "baseline_minus_reorder_delay"
            if options.baseline_time == "subtract_reorder_delay"
            else "as_emitted"
        ),
        "guards": {
            "headline": options.headline,
            "hard": [{"id": g.id, "message": g.message} for g in report.hard],
            "flags": [{"id": g.id, "message": g.message} for g in report.flags],
            "accepted_decisions": list(options.accepted_decisions),
            "facts": {
                "detectors": list(facts.detectors),
                "benchmark_fixture_only": facts.benchmark_fixture_only,
                "registry_fixture_only": facts.registry_fixture_only,
                "step_ms": facts.step_ms,
                "reorder_delay_ms": facts.reorder_delay_ms,
                "patients_without_tail_day": list(facts.patients_without_tail_day),
                "b1_rules_active": None
                if facts.b1_rules_active is None
                else list(facts.b1_rules_active),
                "int_gate": dict(facts.int_gate),
                "history": facts.history,
                "twins": facts.twins,
                "n_seeds": facts.n_seeds,
                "has_device_profile": facts.has_device_profile,
                "timing_tail_ms": facts.timing_tail_ms,
                "required_tail_ms": facts.required_tail_ms,
                "int_gate_unknown": list(facts.int_gate_unknown),
                "min_alpha": facts.min_alpha,
                "calibration_episodes": dict(facts.calibration_episodes),
            },
        },
    }


def _ours_block(
    inst: _Instance,
    units: Sequence[tuple[str, int]],
    weights: _Weights,
    metrics: dict[str, dict[str, Any]],
    options: RunOptions,
) -> dict[str, Any]:
    """Coverage, width, calibration of rho and latency of the proposed method (and bookkeeping for the analysis)."""
    detector = inst.detector
    name = inst.name
    runs = [inst.runs.get(unit) for unit in units]
    done = [r for r in runs if r is not None]
    latencies = [x for r in done for x in r.latencies_ms]
    if latencies:
        p = latency_percentiles(latencies)
        metrics["latency_percentiles"][name] = {
            "p50": p["p50"],
            "p95": p["p95"],
            "p99": p["p99"],
        }
    per_unit = [
        [
            (o.rho, bool(o.outcome))
            for o in (r.predictions if r else ())
            if o.rho is not None and o.outcome is not None
        ]
        for r in runs
    ]
    n_pred = sum(len(u) for u in per_unit)
    n_unresolved = sum(
        1
        for r in done
        for o in r.predictions
        if o.rho is not None and o.outcome is None
    )
    if n_pred:
        bins = options.ece_bins
        table = _ece_table(per_unit, bins)
        flat_rho = [x for u in per_unit for x, _ in u]
        flat_hit = [h for u in per_unit for _, h in u]
        block = weights.scalar(table, _ece_stat(bins))
        block["value"] = _num(expected_calibration_error(flat_rho, flat_hit, bins))
        block["bins"] = bins
        block["n_predictions"] = n_pred
        block["n_unresolved"] = n_unresolved
        block["reliability_bins"] = [
            {
                "lo": b.lo,
                "hi": b.hi,
                "n": b.n,
                "mean_rho": _num(b.mean_rho),
                "observed_rate": _num(b.observed_rate),
            }
            for b in reliability_bins(flat_rho, flat_hit, bins)
        ]
        metrics["expected_calibration_error"][name] = block
    episodes = [(e, r.n_tests) for r in done for e in r.episodes]
    blocks = (
        _coverage_blocks(detector, episodes, options.alpha_grid)
        if detector.is_predictive
        else None
    )
    if blocks is not None:
        coverage, widths, notes = blocks
        metrics["empirical_coverage"][name] = {"in_distribution": coverage}
        metrics["mean_interval_width"][name] = {"in_distribution": widths}
    else:
        notes = {}
    skips: Counter[str] = Counter()
    rejected: Counter[str] = Counter()
    n_tests: Counter[int] = Counter()
    for r in done:
        for reason, count in r.prediction_skips:
            skips[reason] += count
        for item in r.rejected_inputs:
            rejected[item.reason] += 1
        n_tests[r.n_tests] += 1
    return {
        "predictive": detector.is_predictive,
        "alpha_total": detector.config.alpha if detector.is_predictive else None,
        "n_calibration_episodes": detector.n_calibration_episodes,
        "n_censored_calibration": detector.n_censored_calibration,
        "n_test_episodes": len(episodes),
        "n_censored_test": sum(r.n_censored for r in done),
        "n_tests_per_day": {str(k): v for k, v in sorted(n_tests.items())},
        "prediction_skips": dict(sorted(skips.items())),
        "rejected_inputs": dict(sorted(rejected.items())),
        "coverage": notes,
        "calibration_history": "empty: build_calibration_episodes has no history input",
    }


def _twins_block(
    config: ExperimentConfig,
    options: RunOptions,
    env: DetectorEnvironment,
    reader_full: Any,
    reader_obs: Any,
    twin_ids: Sequence[str],
    mains: Mapping[str, Any],
) -> dict[str, Any]:
    if options.twins == "exclude":
        return {"policy": "exclude"}
    if options.twins == "include":
        return {"policy": "include", "n_units": len(twin_ids)}
    info: dict[str, Any] = {}
    days_by = {
        p: [reader_obs.observed(p, d) for d in reader_obs.days(p)] for p in twin_ids
    }
    truth = {p: _truth_events(reader_full, p) for p in twin_ids}
    for name, detector in sorted(mains.items()):
        inst = _Instance(name, None, detector, True)
        parts = []
        for p in twin_ids:
            dets = _run_patient(inst, p, days_by[p], env, options)
            parts.append(
                _score_patient(
                    truth[p][0], dets, len(days_by[p]), config.match
                ).matching
            )
        if not parts:
            continue
        prf = per_class_prf(Matching.concat(parts))
        info[name] = {
            "per_class_prf": {
                c: {k: _num(v) for k, v in vals.items()} for c, vals in prf.items()
            },
            "n_patient_days": sum(len(d) for d in days_by.values()),
        }
    return {"policy": "separate", "n_units": len(twin_ids), "detectors": info}


def _run_hooks(document: dict[str, Any], context: RunContext) -> None:
    for hook in _collect_hooks(context.config.experiment_id):
        result = hook(context)
        if not isinstance(result, HookResult):
            raise ConfigError("an analysis hook must return a HookResult")
        unknown = sorted(set(result.metrics) - set(METRIC_NAMES))
        if unknown:
            raise ConfigError(
                f"a hook contributes metrics {unknown}, which are not contract metric names: {list(METRIC_NAMES)}"
            )
        _merge(document["analysis"], result.analysis, "analysis")
        for metric, value in result.metrics.items():
            if document[metric] is None:
                document[metric] = {}
            _merge(document[metric], value, metric)


# ---- command line ----------------------------------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    """``python -m ralmon.eval.runner --config FILE --output DIR``: 0 done, 2 configuration or guard error."""
    parser = argparse.ArgumentParser(
        prog="python -m ralmon.eval.runner",
        description=__doc__.split("\n")[0] if __doc__ else None,
    )
    parser.add_argument(
        "--config",
        required=True,
        help="experiment YAML (see tests/fixtures/eval/smoke.yaml)",
    )
    parser.add_argument(
        "--output", required=True, help="root of outputs/<experiment_id>/<seed>/"
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        config, options = load_experiment(args.config)
        folders = run_experiment(config, options, args.output)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for folder in folders:
        print(folder)
    return 0


if __name__ == "__main__":
    sys.exit(main())
