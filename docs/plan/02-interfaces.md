# 02 Interfaces

Shared contracts between workstreams. Sources: analisi §4 (technical design), §5 (evaluation), §6 (contributions). Every contract below has a version, an owning workstream, its consumers and its sources. **A contract changes only through an ADR** (`01-conventions.md` section 6).

## How to read

- Python signatures are the normative form. They use `dataclass(frozen=True, slots=True)` and `typing.Protocol`; they are shown inside markdown and are copied verbatim into `src/ralmon/` by the owning task.
- Contracts are the H2 headings after the `# Contracts` line below. A task cites a contract in its `interfaces` frontmatter as `02-interfaces.md#<anchor>`, where the anchor is the lower-case, hyphenated heading (for example `## EvidenceVector` becomes `#evidencevector`).
- Numeric clinical values never appear here. They come from the parameter registry (see `#parameter-registry`). The formulas of analisi §4.1 are illustrative.
- `None` in a field always means "channel unavailable or not applicable", never "negative".
- Common imports assumed by all blocks: `from __future__ import annotations`, `from dataclasses import dataclass`, `from enum import Enum`, `from typing import Mapping, Protocol, Sequence, Literal`.

## Ownership summary

| Contract | Owner | Main consumers |
|---|---|---|
| Time and units | WS05 | all |
| Trace schema | WS04 | WS05, WS06, WS07, WS08, WS10 |
| PriorSource | WS04 | WS04, WS08, WS11 |
| Parameter registry | WS01 | WS04, WS05, WS06, WS11 |
| Template | WS01 | WS05, WS06, WS09, WS11 |
| Signals | WS05 | WS01, WS04, WS06, WS07 |
| Verdict | WS01 | WS05, WS08, WS09 |
| Forecaster | WS05 | WS05, WS07, WS08 |
| Conformal calibrator | WS05 | WS06, WS08 |
| Monitor | WS05 | WS06, WS07, WS08 |
| Alert | WS01 | WS02, WS05, WS06, WS08, WS09, WS11 |
| EvidenceVector | WS02 | WS04, WS05, WS07, WS10 |
| Attribution | WS02 | WS05, WS08 |
| Detector | WS06 | WS08 |
| Metrics | WS08 | WS06, WS09 |
| Experiment config and outputs | WS08 | WS09, WS12, WS13 |
| ROS 2 interfaces | WS07 | WS05, WS10 |
| Package public API | WS05 | all |

# Contracts

## Time and units

Version 0.1.1 (ADR-046, ADR-053 (h): the continuing axis). Owner WS05. Consumers: all. Sources: analisi §4.1 (sampling semantics), §4.9 item 2 (time semantics).

```python
TimeMs = int      # milliseconds on the continuing axis of the patient: the day with index d starts at d * 86,400,000 (ADR-017, ADR-053 (h)); never negative; a verdict or alert time can exceed the end of its day
DurationMs = int

MS_PER_SECOND: int = 1_000
MS_PER_MINUTE: int = 60_000
MS_PER_HOUR: int = 3_600_000

def minutes(x: float) -> DurationMs: ...
def hours(x: float) -> DurationMs: ...
```

Rules:

1. The monitor evaluates at discrete steps of period `T_s` (a `DurationMs` chosen in the monitor configuration and reported in the paper). Sparse measurements are held piecewise-constant between samples; events are one-sample impulses (analisi §4.1 items 2 and 5).
2. Point events with an exact window `O[W,W]` are evaluated as `O[W, W+T_s]` (analisi §4.1 item 5).
3. Two clocks exist per sample: `t_device_ms` (device timestamp) and `t_rx_ms` (receive time). Verdict latency is measured against `t_device_ms` after reordering with a bounded reorder buffer (maximum delay declared in the monitor configuration).
4. Normalised robustness is dimensionless; raw robustness carries the unit declared in the template (`RobustnessUnit`).
5. The days of one patient are written on one continuing axis, `day_index * T_day + clock time` (WS04-T06); day 0 is the per-day axis. `run_offline` runs the day `day_index` from the step `day_index * K` on that axis and replays the earlier days of `history` first (ADR-046). An input stamped before the first step of the run is reported as finalised, not swallowed.

## Trace schema

Version 0.2.0 (ADR-035: the member `EventKind.VERIFICATION` and the evidence conventions; 0.1.1 was ADR-046, text on times beyond the day). Owner WS04. Consumers: WS05, WS06, WS07, WS08, WS10. Sources: analisi §5.1 (trace generator, ground truth), §4.1 (signals), §4.5 (evidence).

A patient-day is represented twice: the **latent trace** (noise-free, fault-free, attack-free) used only to compute ground truth, and the **observed trace** that the monitor and every baseline see.

```python
class EventKind(str, Enum):
    MEASUREMENT = "measurement"        # a blood-pressure measurement was attempted and produced a value
    MEASUREMENT_MISSED = "measurement_missed"  # observed only if the device reports a failed attempt
    DISPENSE = "dispense"              # dispenser opened / pill released (does NOT prove intake)
    INTAKE = "intake"                  # intake verified by the robot witness
    SCHEDULE_TICK = "schedule_tick"    # a care-plan step becomes due
    NODE_STATE = "node_state"          # lifecycle or liveliness change of a device or robot node
    ROBOT_TASK = "robot_task"          # navigation or manipulation task outcome
    DEVICE_ERROR = "device_error"      # error code from a device (e.g. cuff)
    VERIFICATION = "verification"      # a message failed the gateway verification (ADR-035); payload verification, subject

@dataclass(frozen=True, slots=True)
class Sample:
    signal: str                 # a SignalId value (see #signals)
    t_device_ms: TimeMs
    t_rx_ms: TimeMs             # equals t_device_ms in offline traces without transport delay
    value: float                # continuous value; for indicators 1.0
    seq: int | None             # device sequence number (None if the device provides none)
    quality: float | None       # signal quality index in [0, 1], None if unavailable

@dataclass(frozen=True, slots=True)
class Event:
    kind: EventKind
    t_device_ms: TimeMs
    t_rx_ms: TimeMs
    source: str                 # device or node identifier
    payload: Mapping[str, float | int | str | bool]
    seq: int | None

class InjectedClass(str, Enum):
    C1 = "C1"                   # physiological / adherence deviation
    C2 = "C2"                   # system or embodiment failure
    C3 = "C3"                   # integrity violation

@dataclass(frozen=True, slots=True)
class GroundTruthEvent:
    cls: InjectedClass
    subtype: str                # e.g. "hypertensive_spike", "silent_bias", "replay" (open vocabulary, listed in WS04 README)
    onset_ms: TimeMs
    end_ms: TimeMs | None       # None for point events
    injected: bool              # False for C1 events that arise from the latent trace itself
    template_id: str | None     # violated template for C1; None otherwise
    confounder_group: str | None  # e.g. "double_take_vs_bounce"; used to score abstention (analisi §5.1 item 4)

@dataclass(frozen=True, slots=True)
class ObservedDay:
    patient_id: str
    day_index: int
    seed: int
    samples: Sequence[Sample]   # sorted by t_rx_ms
    events: Sequence[Event]     # sorted by t_rx_ms
    care_plan_id: str

@dataclass(frozen=True, slots=True)
class LatentDay:
    patient_id: str
    day_index: int
    seed: int
    samples: Sequence[Sample]   # latent physiology and true intake, no corruption
    events: Sequence[Event]

@dataclass(frozen=True, slots=True)
class BenchmarkDay:
    observed: ObservedDay
    latent: LatentDay
    ground_truth: Sequence[GroundTruthEvent]
```

Rules:

1. **Ground truth definition** (analisi §5.1): a true C1 is a violation of φ_CP evaluated on the *latent* trace. True C2 and C3 are the injected events. The monitor never receives `LatentDay` or `ground_truth`.
2. Every split is by patient: `patient_id` belongs to exactly one of train, calibration or test (analisi §5.1, §4.4).
3. Files on disk: one directory per benchmark version, `days/<patient_id>/<day_index>.json` (or Parquet, chosen by WS04-T01 and recorded as an ADR), plus a `manifest.json` with generator git revision, seeds and prior source provenance.
4. The times of `samples` and `events` of an `ObservedDay` are on the continuing axis of the patient (`#time-and-units`). The time of a verdict or of an alert can exceed the end of the day for an instance anchored in it and decided after it (a RESP window across midnight); with a `history` an instance anchored in an earlier day can be decided in this day, and its onset then lies before the first step of the day (ADR-046). A `GroundTruthEvent` belongs to the day in which the monitor decides it.
5. **Evidence conventions** (ADR-035). The table "Trace evidence conventions" of `docs/models/evidence-channels.md` is binding for the `payload` keys of `NODE_STATE`, `ROBOT_TASK`, `DEVICE_ERROR`, `VERIFICATION` and `DISPENSE`; a key enters a trace only if the table declares it. A message that fails the gateway verification stays in the trace (policy "flag") and the gateway logs a `VERIFICATION` event (`source` the gateway, `payload` `verification` = `failed` and `subject` = the device); a `DEVICE_ERROR` is a fault report of a device and carries only `error_code`.
6. **`auth`** (ADR-035). The gateway delivers an `auth` Sample only for a dispense message whose verification passed, and a source that cannot verify does not emit `auth`, so an injector without keys cannot satisfy INT through it.
7. **Robot-channel availability** (ADR-035, ADR-054). The availability of `presence` and `intake` is derived from the robot `NODE_STATE` events (`state`, `colocated`); no field is added to `ObservedDay`.

## PriorSource

Version 0.1.0. Owner WS04. Consumers: WS04, WS08, WS11. Sources: analisi §5.1 (public sources, generator), §9 item 0.6 (credentialing delay).

The only way the benchmark obtains parameters of the latent patient, the PK/PD response, the device error model and the adherence model. `LiteraturePriorSource` is the first implementation; `MimicPriorSource` is added when PhysioNet access exists (ADR-005) without changing any consumer.

```python
@dataclass(frozen=True, slots=True)
class ParamProvenance:
    name: str
    source_ref: str            # citation or dataset table; mandatory, agents must not invent values
    verified_by: str | None    # human who verified the value (None = unverified, must be reported)

@dataclass(frozen=True, slots=True)
class PatientParams:
    patient_id: str
    baseline_sbp_mmhg: float
    circadian_amplitude_mmhg: float
    ar_noise_sd_mmhg: float
    ar_noise_phi: float
    emax_mmhg: float           # maximal drug effect (Emax model)
    ec50: float
    absorption_rate_per_h: float
    elimination_rate_per_h: float
    onset_delay_range_ms: tuple[DurationMs, DurationMs]   # informs Delta1, Delta2 (analisi §5.1)

@dataclass(frozen=True, slots=True)
class AdherenceParams:
    p_delay: float
    p_omission: float
    p_double_take: float
    mean_delay_ms: DurationMs
    # Markov state model of adherence; declared as an assumption (analisi §5.1: no public smart-dispenser dataset known)

@dataclass(frozen=True, slots=True)
class DeviceErrorModel:
    cuff_error_sd_mmhg: float  # from device validation protocols (analisi §5.1; the exact source is verified by a human)
    cuff_bias_mmhg: float
    dispenser_bounce_prob: float
    ble_dropout_rate_per_h: float

class PriorSource(Protocol):
    name: str
    def sample_patient(self, rng: "np.random.Generator", patient_index: int) -> PatientParams: ...
    def adherence(self) -> AdherenceParams: ...
    def device_errors(self) -> DeviceErrorModel: ...
    def provenance(self) -> Sequence[ParamProvenance]: ...
```

Rules: every numeric field must have a `ParamProvenance` entry; a value with no `source_ref` makes the constructor of the implementation fail. `LiteraturePriorSource` values that are not verified by a human are flagged in the benchmark manifest and in the paper limitations.

## Parameter registry

Version 0.1.0. Owner WS01. Consumers: WS04, WS05, WS06, WS11. Sources: analisi §4.1 (illustrative values), §4.2 (scales s_π), §5.7, §2 R3 weakness 3 (anchoring in drug and guideline).

Single source for clinical parameters of the templates: band limits, hold threshold, Δ1, Δ2, δ, schedule window W, dose limits, physiological bounds for robustness intervals, per-template scale s_π and priority. Values live in a versioned YAML file `configs/registry/hypertension.yaml` (created by WS01) and are reviewed by the clinician (WS00-T03).

```python
@dataclass(frozen=True, slots=True)
class RegistryEntry:
    name: str                  # e.g. "bp_band_low", "delta1", "delta2", "scale_range"
    value: float
    unit: str                  # "mmHg", "ms", "dose", "1" ...
    rationale: str             # drug or guideline anchoring, or "illustrative, unverified"
    source_ref: str
    reviewed_by: str | None    # clinician; None until reviewed

@dataclass(frozen=True, slots=True)
class PhysioBounds:
    signal: str
    lower: float
    upper: float               # used to complete unknown future values in robustness intervals (analisi §4.7 step 2)

class ParameterRegistry(Protocol):
    def get(self, name: str) -> RegistryEntry: ...
    def bounds(self, signal: str) -> PhysioBounds: ...
    def version(self) -> str: ...
```

Rule: no numeric clinical constant appears in `src/ralmon` outside the registry loader. Illustrative values from analisi §4.1 may be loaded only if `rationale` states "illustrative, unverified".

## Template

Version 0.1.0. Owner WS01. Consumers: WS05, WS06, WS09, WS11. Sources: analisi §4.1 (templates and decomposition), §4.2 (normalisation, priority), §4.7 (online semantics), §6 (contributions).

A pathway template is a parametric past-time STL formula with the metadata needed for normalisation and reporting. It is instantiated for a patient into a `TemplateInstance` inside a `CarePlan`. The decomposition is φ = φ_CP ∧ φ_SYS ∧ φ_INT.

```python
class TemplateKind(str, Enum):
    CARE_PLAN = "phi_cp"
    SYSTEM = "phi_sys"
    INTEGRITY = "phi_int"

class TemplateId(str, Enum):
    RANGE = "range"      # measured pressure inside the prescribed band
    SCHED = "sched"      # a measurement occurs in the window after a schedule tick
    HOLD = "hold"        # do not dispense if pressure is below the hold threshold
    COUNT = "count"      # dose count limit and day-end count obligation
    RESP = "resp"        # dose-response: pressure decrease relative to pre-dose reference in [Delta1, Delta2]
    SYS = "sys"          # measurement valid only if cuff node healthy and inflation acceptable
    INT = "int"          # a dispense is backed by robot-observed presence or authenticated event

class RobustnessUnit(str, Enum):
    MMHG = "mmHg"
    MS = "ms"            # time robustness
    DOSE = "dose"
    DIMENSIONLESS = "1"

@dataclass(frozen=True, slots=True)
class Template:
    id: TemplateId
    kind: TemplateKind
    formula_past_time: str          # past-time STL string, syntax fixed by WS01-T02 (RTAMT-compatible)
    signals: Sequence[str]          # SignalId values used (see #signals)
    params: Sequence[str]           # registry entry names it needs
    unit: RobustnessUnit
    scale_param: str                # registry entry name holding s_pi
    priority_param: str             # registry entry name holding the clinician-assigned priority
    max_verdict_latency_param: str  # registry entry: bound on time to a definitive verdict (Delta2 or W plus T_s)
    creates_robot_obligation: bool  # True for RESP and SCHED (analisi §4.1 item 4)

@dataclass(frozen=True, slots=True)
class TemplateInstance:
    template: TemplateId
    instance_key: str               # unique within a care plan, e.g. "resp@2026-01-01T07:00"
    param_values: Mapping[str, float]
    anchor_ms: TimeMs | None        # schedule tick that anchors the instance, if any

@dataclass(frozen=True, slots=True)
class CarePlan:
    care_plan_id: str
    pathway_template_id: str        # institutional pathway template it instantiates
    patient_id: str
    registry_version: str
    instances: Sequence[TemplateInstance]
    schedule: Sequence[TimeMs]      # measurement and dispense ticks
    plan_version: int
    signature: str | None           # integrity signature of the distributed plan (analisi §2 R1 weakness 9, §4.9 item 7)
```

Normalised robustness (analisi §4.2), owned by WS01 and implemented in `ralmon.spec`:

```python
def normalise(sigma_raw: float, scale: float) -> float:
    """sigma_tilde = clip(sigma_raw / scale, -1.0, 1.0). scale > 0."""

def rank_alerts(alerts: Sequence["Alert"]) -> list["Alert"]:
    """Lexicographic order: template priority first (clinician-assigned), then sigma_tilde ascending within a priority."""
```

Rules: the conjunction of templates is never a `min` over raw values in different units; only normalised values are compared (analisi §4.2). Counters are derived signals, not "outside STL" (analisi §4.1 item 2). Normalisation by the width of a conformal interval is forbidden (analisi §4.2, last paragraph).

## Signals

Version 0.2.0 (ADR-057: the two robot-state signals). Owner WS05. Consumers: WS01, WS04, WS06, WS07. Sources: analisi §4.1 (signals list and derived signals), §4.5 (evidence channels), §4.3 (forecast from task queue and navigation state).

```python
class SignalId(str, Enum):
    BP = "bp"                     # last measured systolic pressure, piecewise-constant
    MEAS = "meas"                 # measurement indicator (impulse)
    DISPENSE = "dispense"         # dispenser opened (impulse)
    INTAKE = "intake"             # intake verified by the robot (impulse)
    SCHED_TICK = "sched_tick"     # care-plan step due (impulse)
    DOSE_COUNT = "dose_count"     # derived: dispenses in the trailing 24 h
    MEAS_COUNT = "meas_count"     # derived: measurements in the current day
    BP_PRE = "bp_pre"             # derived: pre-dose reference pressure
    BP_DROP = "bp_drop"           # derived: bp_pre minus bp
    CUFF_HEALTH = "cuff_health"   # 1.0 healthy
    INFLATION_MS = "inflation_ms" # cuff inflation duration
    PRESENCE = "presence"         # robot-observed presence of the patient
    AUTH = "auth"                 # authenticated dispense event
    DAY_END = "day_end"           # end-of-day marker for count obligations
    HR_ECG = "hr_ecg"
    HR_PULSE = "hr_pulse"         # pulse rate reported by the cuff
    SPO2 = "spo2"
    NAV_ETA = "nav_eta_ms"        # remaining navigation time to the patient room, published by the robot task layer (integer ms)
    TASK_QUEUE = "task_queue_ms"  # summed estimated duration of the tasks queued ahead of the care-delivery task (integer ms)

class DerivedSignal(Protocol):
    output: SignalId
    inputs: Sequence[SignalId]
    def update(self, sample: Sample) -> Sample | None: ...   # streaming, causal, O(1) per sample

def hold_last(samples: Sequence[Sample], t_grid_ms: Sequence[TimeMs]) -> Sequence[float]:
    """Piecewise-constant interpolation on the monitor grid (analisi §4.1 item 2)."""
```

Rule: derived signals are causal and streaming. `NAV_ETA` and `TASK_QUEUE` are inputs of the deadline forecaster (`#forecaster`) and of no template; the robot task layer (WS07-T04) publishes them as `Sample`s. The `PRESENCE` and `INTAKE` signals exist only while the robot is co-located; their absence is reported through the `EvidenceVector`, not as a value of zero.

## Verdict

Version 0.1.0. Owner WS01. Consumers: WS05, WS08, WS09. Sources: analisi §4.7 (three-valued semantics, state diagram), §4.3 (separation of measured and predicted), §4.4 (definition of ρ).

```python
class VerdictState(str, Enum):
    PENDING = "pending"
    PREDICTED_VIOLATION = "predicted_violation"   # early warning, never definitive
    VIOLATED = "violated"                         # definitive, from measured prefix only
    SATISFIED = "satisfied"                       # definitive, from measured prefix only

@dataclass(frozen=True, slots=True)
class RobustnessInterval:
    lo: float                 # raw robustness lower bound (native unit)
    hi: float                 # raw robustness upper bound; unknown future values replaced by physiological bounds

class RhoKind(str, Enum):
    MEASURED = "measured"           # P(sigma_true < 0 | measurement) under a device error model
    PREDICTED = "predicted"         # conformal, 1 - alpha_star
    DETERMINISTIC = "deterministic" # event-log predicate, rho = 1

@dataclass(frozen=True, slots=True)
class Rho:
    value: float              # in [0, 1]
    kind: RhoKind
    guarantee: str            # exact statement, e.g. "marginal over patient episodes under exchangeability"
    alpha: float | None       # nominal level for PREDICTED
    assumptions: Sequence[str]

@dataclass(frozen=True, slots=True)
class VerdictRecord:
    instance_key: str
    template: TemplateId
    t_eval_ms: TimeMs
    state: VerdictState
    sigma_interval: RobustnessInterval    # raw, native unit
    sigma_norm_interval: tuple[float, float]  # clipped normalised interval
    rho: Rho | None
    decided_at_ms: TimeMs | None          # when the definitive verdict became decidable; None while PENDING
    pending_until_ms: TimeMs | None       # deadline after which the verdict is definitive (anchor + Delta2 or W)
```

Semantics (analisi §4.7):

1. VIOLATED iff `sigma_interval.hi < 0`; SATISFIED iff `sigma_interval.lo > 0`; otherwise PENDING.
2. PREDICTED_VIOLATION is emitted only while PENDING, when the conformal completion satisfies `sigma_hat + q_{1-alpha} < 0` ("likely") or `sigma_hat - q < 0` ("possible"); which one is used is a monitor option with a clinical justification (analisi §4.4).
3. A definitive verdict is computed only from the measured prefix. The forecast never produces VIOLATED or SATISFIED (analisi §4.3).
4. Maximum latency of a definitive verdict is a property of the template (`max_verdict_latency_param`) and is reported.

Allowed transitions: PENDING → PREDICTED_VIOLATION → VIOLATED; PENDING → VIOLATED; PENDING → SATISFIED; PREDICTED_VIOLATION → SATISFIED (the warning is then counted as a false predictive alarm).

## Forecaster

Version 0.2.0 (ADR-057: `model_version`, `supported_signals`, the index convention, the concrete classes). Owner WS05. Consumers: WS05, WS07, WS08. Sources: analisi §4.3 (candidates for prediction), §2 R2 weakness 5, §10 objection 3.

```python
@dataclass(frozen=True, slots=True)
class Forecast:
    signal: str
    t_from_ms: TimeMs
    horizon_ms: DurationMs
    mean: Sequence[float]        # point path on the monitor grid

class Forecaster(Protocol):
    name: str
    model_version: str                     # read-only; changes whenever the fitted parameters change
    supported_signals: frozenset[str]      # read-only; the Forecast.signal values it can produce
    def fit(self, train_days: Sequence[ObservedDay]) -> None: ...
    def predict(self, history: Sequence[Sample], t_ms: TimeMs, horizon_ms: DurationMs) -> Forecast: ...
```

Index convention of `Forecast.mean`: `t_from_ms == t_ms`, `len(mean) == horizon_ms // step_ms`, and `mean[k]` predicts the value at `t_from_ms + (k + 1) * step_ms`. For the impulse signal `meas` an entry is 1.0 at the first grid step at or after the predicted instant and 0.0 elsewhere. The concrete classes (`PersistenceForecaster(step_ms)`, `AutoRegressiveForecaster(step_ms, order)`, `DeadlineForecaster(step_ms)`) add a keyword-only `signal: str | None = None` to `predict`; with `None` the target is the single supported signal present in `history`. They raise `ForecasterNotFittedError`, `InsufficientHistoryError` or `UnsupportedSignalError` and never return a silent default.

Targets in scope (analisi §4.3): continuous signals (heart rate, SpO₂) and robot care-delivery deadlines (the forecast that the robot will arrive late to a scheduled window, from task queue and navigation state). Blood pressure with about five measurements per day is expected to give intervals too wide to be useful; WS08 reports this honestly as a finding. Model class is chosen by WS05-T05 and recorded as an ADR (ADR-057).

## Conformal calibrator

Version 0.2.0 (ADR-058: `calibrated_for`, `model_version`, `quantile_lower`, the `variant` argument of `predict`, levels as exact fractions, the accessors of the adaptive mode; 0.1.0 was the first text). Owner WS05. Consumers: WS06, WS08. Sources: analisi §4.4 (ρ definitions, Proposition 1, caveats), §3.2, §5.6 (A1, A6), §2 R2 weaknesses 3, 4, 6; `docs/formal/06-rho-proposition1.md`.

```python
@dataclass(frozen=True, slots=True)
class CalibrationEpisode:
    patient_id: str
    day_index: int
    template: TemplateId
    sigma_hat: float          # predicted normalised robustness
    sigma_true: float         # normalised robustness of the completed trace (latent or measured)

Level = float | Fraction     # a float is read as its decimal literal (Fraction(repr(alpha))); a Fraction is exact

class AlphaAllocation(Protocol):
    def per_test(self, alpha_total: float, n_tests: int) -> float: ...   # controls alarms per patient-day (analisi §4.4)

class ConformalCalibrator(Protocol):
    mode: Literal["split", "adaptive"]                                # read-only
    calibrated_for: str | None                                        # model version of the last fit; None: no particular model
    def fit(self, episodes: Sequence[CalibrationEpisode], alpha: Level, *, model_version: str | None = None) -> None: ...
    def quantile(self, alpha: Level) -> float: ...                    # one-sided q_{1-alpha} of R = sigma_true - sigma_hat
    def quantile_lower(self, alpha: Level) -> float: ...              # q^lo_alpha, for the variant "possible" (ADR-030)
    def predict(self, sigma_hat: float, alpha: Level, *, variant: Literal["likely", "possible"] = "likely") -> "PredictedViolation": ...
    def update(self, sigma_hat: float, sigma_true: float) -> None: ... # adaptive mode only; no-op in split mode

@dataclass(frozen=True, slots=True)
class PredictedViolation:
    emitted: bool
    rho: Rho | None           # RhoKind.PREDICTED with alpha_star = inf{alpha : sigma_hat + q_{1-alpha} < 0}; None when not emitted
    variant: Literal["likely", "possible"]
```

Rules (analisi §4.4):

1. Calibration unit is the **patient episode**, never the time step. Split by patient.
2. Coverage is marginal over the population, not conditional on the patient; this is stated wherever coverage is reported.
3. Nonconformity score is one-sided, `R = sigma_true - sigma_hat`; Proposition 1 (WS01) states `P(alert emitted and sigma >= 0) <= alpha` under exchangeability across episodes.
4. Every model update pushed from the back-end triggers recalibration on held-out episodes (`fit` is called again); the monitor refuses to use a calibrator older than the model version (analisi §2 R2 weakness 6). The version token is `calibrated_for`: `fit(..., model_version=v)` sets it to `v`, a `fit` without `model_version` sets it to `None` (calibrated for no particular model), and the monitor compares it with `Forecaster.model_version` and refuses `None` in predictive mode.

Additions of 0.2.0 (ADR-058):

5. **Ranks** are computed in integer arithmetic from the level as an exact fraction: `k = ceil((n + 1)(1 - alpha))` for `quantile` (`+inf` if `k > n`) and `j = floor((n + 1) alpha)` for `quantile_lower` (`-inf` if `j < 1`). A float level is read through its shortest round-trip decimal; an allocated level (`alpha_total / n_tests`) is passed as a `Fraction`, which `BonferroniAllocation.per_test_exact(alpha_total, n_tests)` returns (`per_test` is its float image). `alpha` outside `(0, 1)` raises `ValueError`; the split calibrator is level-agnostic (the `alpha` of `fit` is only validated).
6. **Variants.** `variant="likely"` emits iff `sigma_hat + quantile(alpha) < 0` (Proposition 1, false alarms). `variant="possible"` emits iff `sigma_hat + quantile_lower(alpha) < 0` (Proposition 1b, missed violations), not the symmetric form `sigma_hat - q < 0`, which carries the miss bound only for scores symmetric about zero (ADR-030). In both variants `Rho.value = m / (n + 1)` with `m` the number of calibration scores `R_i` with `sigma_hat + R_i < 0`, so `1 - Rho.value = alpha_star = (m' + 1) / (n + 1)` with `m' = n - m`; `Rho.alpha` is the level used and `Rho.guarantee` is `"marginal over patient episodes under exchangeability"` for the split mode.
7. **Not emitted.** `PredictedViolation.rho` is `None` when `emitted` is false (including a quantile of `+inf`: a level below `1 / (n + 1)` never emits, which is reported, not hidden). `quantile`, `quantile_lower` and `predict` raise `RuntimeError` before the first `fit`; `fit` raises `ValueError` for no episodes and for a non-finite `sigma`.
8. **Adaptive mode** (`AdaptiveConformal(gamma, window=None)`, `gamma` required): `fit(episodes, alpha)` sets the target level and `alpha_t = alpha`; `update` moves `alpha_t` by `alpha_t + gamma (alpha - err_t)` (`err_t = 1` when the new score exceeds the quantile at `alpha_t`) and adds the score; accessors `alpha_t` (unclipped) and `n_scores`; `fork()` returns a copy at the state right after `fit` (per-patient adaptation without leakage); `quantile`, `quantile_lower` and `predict` raise `ValueError` for a level other than the one of `fit`. `alpha_t <= 0` gives `quantile = +inf`, `alpha_t >= 1` gives `-inf`. `Rho.guarantee` is empirical (ablation A6), with no finite-sample claim. The recursion is that of the adaptive conformal inference literature, `[ref-needed: WS03]`, unverified until the human reference check (ADR-018).

## Monitor

Version 0.3.0 (ADR-060: the meaning of `alpha`, the prediction rule, `StaleCalibratorError`, `build_calibration_episodes`; 0.2.0 was ADR-053 and ADR-046). Owner WS05. Consumers: WS06, WS07, WS08. Sources: analisi §4.7 (online monitoring), §4.1 (samples), §4.9 items 1 and 2.

```python
@dataclass(frozen=True, slots=True)
class MonitorConfig:
    step_ms: DurationMs                 # T_s
    reorder_delay_ms: DurationMs        # maximum reorder buffer delay
    predictive: bool                    # emit PREDICTED_VIOLATION
    alpha: float | None                 # the TOTAL level of a patient-day, split over the tests of the plan (ADR-060); required if predictive
    variant: Literal["likely", "possible"]
    registry_version: str

class Monitor(Protocol):
    def load(self, plan: CarePlan) -> None: ...                       # verifies plan signature if present
    def push_sample(self, sample: Sample) -> None: ...
    def push_event(self, event: Event) -> None: ...
    def advance(self, t_ms: TimeMs) -> Sequence[VerdictRecord]: ...  # causal: uses only inputs with t_device_ms <= t_ms - reorder_delay_ms
    def verdict_latency_bound_ms(self, template: TemplateId) -> DurationMs: ...

def run_offline(day: ObservedDay, plan: CarePlan, config: MonitorConfig, calibrator: ConformalCalibrator | None,
                forecaster: Forecaster | None, *, registry: ParameterRegistry | None = None,
                templates: Sequence[Template] | None = None, verifier: PlanVerifier | None = None,
                history: Sequence[ObservedDay] = ()) -> Sequence[VerdictRecord]: ...
```

Rules: `advance` is causal (no look-ahead); processing cost per sample is O(number of active template instances) and the bound is reported. The monitor separates verdicts from attribution: it emits `VerdictRecord`s; the `Attribution` step turns violated records into alerts.

Rules of 0.2.0 (ADR-053, ADR-046). (1) `registry` defaults to `load_registry(step_ms=config.step_ms)`, `templates` to `load_templates(registry=registry)`; a signed plan without a `verifier` raises `PlanIntegrityError`; a caller that passes the five positional arguments keeps working. (2) `history` holds the accepted observed days that precede `day` for the same patient, in order of day index, on the continuing axis (`#time-and-units`); they are replayed first and the verdicts of the steps before the first step of `day` are not returned. The history needed is `H = max(T_day, largest window parameter)`. With an empty `history` the run starts with empty state: a counter over 24 h can only under-count, so a VIOLATED verdict stays sound and a SATISFIED one can be wrong. (3) `StreamingMonitor` offers, outside the `Monitor` protocol, `push_availability(signal, available, t_device_ms, t_rx_ms)` (the availability of the robot channels `presence` and `intake`, ordered with the inputs and late by the same rule), `late_inputs()`, `rejected_inputs()`, `stats()` and `close()`; `run_offline_detailed(...)` takes the same arguments as `run_offline` and returns an `OfflineResult` (the records plus those diagnostics). (4) `make_point_evaluator(template, instance, registry, step_ms, *, anchor_kind=None) -> PointEvaluator` is the entry point of the baselines B3 and B5; `PointEvaluator.step(t_ms, values) -> float | None` returns the raw robustness at the decision step and `None` before it (ADR-053 (c) has the details).

Rules of 0.3.0 (ADR-060). (5) **Predictive mode.** `predictive=True` requires `alpha`, a calibrator and a forecaster (`MonitorConfigError` at construction) and a calibrator calibrated for `forecaster.model_version` (`StaleCalibratorError` at construction and on every `advance`; `calibrated_for is None` is refused). With `predictive=False` both are ignored and the records are those of the measured-only monitor (ablation A2). (6) **Prediction rule.** An instance that has a predictive path (a SCHED instance of the plan if the forecaster supports `meas`, a RESP instance created at a scheduled dispense if it supports `bp`) gets exactly one prediction, at its activation step, and only if its record there is PENDING. If the calibrator emits, the step emits the PENDING record and then a PREDICTED_VIOLATION record with the same `t_eval_ms`; the state is sticky until the measured prefix decides it, the interval fields are those of the measured prefix, `rho` is `PREDICTED` with `Rho.alpha` the per-test level, `predicted_sigma_norm = clip(sigma_hat + q, -1, 1)` and `decided_at_ms` is `None`. The forecast never produces VIOLATED or SATISFIED. (7) **Allocation.** The per-test level is `alpha / n_tests` (exact fraction, `BonferroniAllocation`), `n_tests` being the largest number of tests of one calendar day of the loaded plan; `stats()` reports `n_tests`, `per_test_alpha`, the predictions made, emitted and uninformative, and the reason of every skipped prediction. (8) **Horizon.** The time to the deadline of the instance, plus the scale of the template when its unit is milliseconds. (9) `build_calibration_episodes(days: Sequence[ObservedTrace], plans: Sequence[CarePlan], config: MonitorConfig, forecaster: Forecaster, *, registry=None, templates=None) -> tuple[list[CalibrationEpisode], int]` returns the calibration episodes of the observed days, on the same code path as the monitor, and the number of tested instances whose value is undefined on the day (`n_censored`). `sigma_true` is the observed completion; no latent day can be passed. (10) `StreamingMonitor.push_sample` also accepts the robot-state signals `nav_eta_ms` and `task_queue_ms` (kept for the forecaster, read by no template).

## Alert

Version 0.1.1 (ADR-059: `Alert.rho` may be `None`). Owner WS01. Consumers: WS02, WS05, WS06, WS08, WS09, WS11. Sources: analisi §4.2 (σ̃), §4.4 (ρ), §4.5 (κ), §4.8 (traceability wording), §4.9 item 3 (cascades).

The output tuple ⟨τ, κ, σ̃, ρ, ξ⟩ with explicit semantics per field.

```python
class AttributedCause(str, Enum):
    C1_CLINICAL = "C1"       # clinical or adherence deviation
    C2_SYSTEM = "C2"         # system or embodiment failure
    C3_INTEGRITY = "C3"      # integrity or plausibility violation
    UNDETERMINED = "UNDETERMINED"

@dataclass(frozen=True, slots=True)
class Explanation:
    """xi: specification-level traceability (not 'intrinsic explainability')."""
    template: TemplateId
    instance_key: str
    subformula_path: str              # path to the violated sub-formula
    param_values: Mapping[str, float] # clinical parameters used
    evidence_used: Sequence[str]      # EvidenceVector fields that decided kappa
    text: str                         # natural-language rendering for nursing staff

@dataclass(frozen=True, slots=True)
class Detection:
    """Minimal output shared by every detector, including baselines B1-B4."""
    t_ms: TimeMs
    label: AttributedCause | None     # None for detectors that do not attribute
    score: float                      # detector-specific; higher = more anomalous, only for ROC-style curves

@dataclass(frozen=True, slots=True)
class Alert(Detection):
    tau: TemplateId                   # violated template (constraint)
    kappa: AttributedCause            # attributed cause; UNDETERMINED is a valid output
    sigma_norm: float                 # normalised robustness in [-1, 0) for a violation
    rho: Rho | None                   # confidence with declared kind and guarantee; None when the record has no confidence (ADR-059)
    xi: Explanation
    verdict: VerdictState             # VIOLATED or PREDICTED_VIOLATION
    priority: int                     # clinician-assigned template priority
    root_cause_of: Sequence[str]      # instance keys of downstream violations explained by this alert (cascades)
    caused_by: str | None             # instance key of the upstream alert when this one is a cascade effect
```

Semantics:

- σ̃ answers "how badly is the prescribed care violated" in clinical scale units; ρ answers "how confidently can the violation be claimed", with its `kind` telling which guarantee applies. They are complementary, not orthogonal (analisi §4.8).
- κ is produced by the attribution layer, never by the sub-formula alone (analisi §4.5). A value of `UNDETERMINED` is not an error.
- `rho` is `None` exactly when the `VerdictRecord` has no confidence (the monitor has no error model for a MEASURED value). A violated verdict is always reported, so the alert is still issued; consumers of `Alert.rho` (calibration, ECE, ranking by confidence) filter `None` and never read it as 0 (ADR-059).
- A cascade effect (for example a counter violation caused by a C2 missed measurement) carries `caused_by` and is not shown as a separate top-level alert (analisi §4.9 item 3).
- Ordering of alerts uses `rank_alerts` from `#template`.

## EvidenceVector

Version 0.1.0. Owner WS02. Consumers: WS04, WS05, WS07, WS10. Sources: analisi §4.5 (six evidence groups), §4.9 item 5.

```python
@dataclass(frozen=True, slots=True)
class ProvenanceEvidence:
    violated_template: TemplateId
    template_kind: TemplateKind            # which of phi_cp, phi_sys, phi_int is violated

@dataclass(frozen=True, slots=True)
class SystemHealthEvidence:
    node_lifecycle: Mapping[str, str] | None    # ROS 2 lifecycle state per node
    diagnostics_ok: bool | None
    liveliness_ok: bool | None
    qos_deadline_missed: bool | None
    ble_link_quality: float | None
    battery_low: bool | None
    nav_task_failed: bool | None
    manip_task_failed: bool | None

@dataclass(frozen=True, slots=True)
class SignalQualityEvidence:
    ecg_sqi: float | None
    ppg_sqi: float | None
    cuff_error_code: str | None

@dataclass(frozen=True, slots=True)
class CrossDeviceEvidence:
    pulse_vs_ecg_hr_diff: float | None     # cuff pulse rate versus ECG heart rate at the same instant

@dataclass(frozen=True, slots=True)
class EmbodiedWitnessEvidence:
    robot_present: bool | None             # None if the robot was not co-located
    identity_confirmed: bool | None
    intake_observed: bool | None

@dataclass(frozen=True, slots=True)
class CryptoTemporalEvidence:
    authenticated: bool | None
    seq_gap_or_replay: bool | None
    timestamp_implausible: bool | None

@dataclass(frozen=True, slots=True)
class EvidenceVector:
    provenance: ProvenanceEvidence
    system: SystemHealthEvidence
    signal_quality: SignalQualityEvidence
    cross_device: CrossDeviceEvidence
    witness: EmbodiedWitnessEvidence
    crypto_temporal: CryptoTemporalEvidence
```

Rule: `None` (channel unavailable) is never converted to a negative observation. This is what makes the embodied-channel ablation A4 meaningful: with the channel removed, all `witness` fields and robot-derived `system` fields become `None`.

## Attribution

Version 0.1.0. Owner WS02. Consumers: WS05, WS08. Sources: analisi §4.5 (hierarchical rule, abstention, diagnosability matrix), §3.6, §4.9 item 3, §5.5, §5.6 (A4).

```python
class AttributionRule(Protocol):
    def attribute(self, violated: VerdictRecord, evidence: EvidenceVector) -> AttributedCause: ...

class Attributor(Protocol):
    def attribute_all(self, violated: Sequence[VerdictRecord], evidence: Mapping[str, EvidenceVector]) -> Sequence[Alert]: ...
    # propagates root causes over cascades (analisi §4.9 item 3)
```

The default rule is hierarchical and auditable (analisi §4.5):

1. Integrity evidence present → `C3_INTEGRITY`.
2. Otherwise system evidence present → `C2_SYSTEM`.
3. Otherwise a violation with coherent channels → `C1_CLINICAL`.
4. Otherwise (conflicting or insufficient evidence) → `UNDETERMINED`.

The diagnosability matrix of analisi §4.5 is encoded as a machine-readable table (`configs/diagnosability.yaml`, owned by WS02) and used both to design tests and to declare which event types are distinguishable with which channels. A probabilistic variant producing `p_kappa` is optional.

## Detector

Version 0.1.0. Owner WS06. Consumers: WS08. Sources: analisi §5.4 (B1-B5), §5.6 (ablations), §5.5 (metrics).

Common interface so that every method, including the proposed one and its ablations, is evaluated by identical code.

```python
class Detector(Protocol):
    name: str                  # "B1".."B5", "ours", "ours-A1" ...
    def fit(self, train_days: Sequence[BenchmarkDay], calib_days: Sequence[BenchmarkDay]) -> None: ...
    def run(self, day: ObservedDay, plan: CarePlan, evidence: Mapping[str, EvidenceVector] | None) -> Sequence[Detection]: ...
```

Rules: baselines receive the same clinical knowledge as the proposed method (bands and schedules for B1 and B3; analisi §10 objection 1). B5 is the conformal STL predictive-monitoring method of Lindemann et al. 2023 applied to the same templates. Detectors never see `LatentDay` or `GroundTruthEvent`; `fit` may use ground truth from training days only.

## Metrics

Version 0.1.0. Owner WS08. Consumers: WS06, WS09. Sources: analisi §5.5, §5.6, §10.

```python
@dataclass(frozen=True, slots=True)
class MatchConfig:
    tolerance_ms: DurationMs            # matching window between detection and ground-truth event; declared in the paper
    time_reference: Literal["onset", "first_decidable"]

def match_events(gt: Sequence[GroundTruthEvent], det: Sequence[Detection], cfg: MatchConfig) -> "Matching": ...
def per_class_prf(matching: "Matching") -> Mapping[str, Mapping[str, float]]: ...     # precision, recall, F1 per C1, C2, C3
def detection_delay_ms(matching: "Matching", days: Sequence[BenchmarkDay]) -> Sequence[float]: ...  # relative to first decidable instant; negative = early warning
def false_alarms_per_patient_day(matching: "Matching", n_patient_days: int) -> float: ...
def recall_vs_false_alarm_curve(runs: Sequence["Matching"], alphas: Sequence[float]) -> Sequence[tuple[float, float]]: ...
def empirical_coverage(pred: Sequence[PredictedViolation], truth_sigma: Sequence[float], alpha: float) -> float: ...
def mean_interval_width(intervals: Sequence[tuple[float, float]]) -> float: ...
def expected_calibration_error(rho: Sequence[float], outcome: Sequence[bool], bins: int) -> float: ...
def attribution_confusion(matching: "Matching") -> Mapping[tuple[str, str], int]: ...   # includes UNDETERMINED
def accuracy_vs_coverage(matching: "Matching") -> Sequence[tuple[float, float]]: ...
def latency_percentiles(latencies_ms: Sequence[float]) -> Mapping[str, float]: ...       # p50, p95, p99
def severity_rank_agreement(auto: Sequence[float], clinician: Sequence[float]) -> float: ... # Kendall tau or Spearman
```

Rules: bootstrap confidence intervals over patient-days; at least 5 seeds (analisi §5.1); coverage is reported both in distribution and under shift (calibrate on one cohort, test on the other).

## Experiment config and outputs

Version 0.1.0. Owner WS08. Consumers: WS09, WS12, WS13. Sources: analisi §5.1 (scale), §5.5, §5.6, §5.8.

```python
@dataclass(frozen=True, slots=True)
class ExperimentConfig:
    experiment_id: str          # e.g. "main", "A1", "A6", "shift", "unlabeled-real"
    benchmark_manifest: str     # path of the benchmark version
    detectors: Sequence[str]    # names in the Detector contract
    seeds: Sequence[int]        # at least five for headline results
    split: Mapping[str, float]  # train, calibration, test fractions, by patient
    match: MatchConfig
    alpha: float | None
    monitor: MonitorConfig | None
```

Outputs: `outputs/<experiment_id>/<seed>/{config.yaml, metrics.json, git_rev.txt}`. `metrics.json` keys are the metric names of `#metrics`. Tables and figures are generated only from these files.

## ROS 2 interfaces

Version 0.1.0. Owner WS07. Consumers: WS05, WS10. Sources: analisi §4.9 item 1 (distributed architecture), §4.5 (system health evidence), §5.2 (simulation), §2 R3 weakness 2.

Logic lives in `ralmon`; ROS 2 packages under `ros2/` are thin. Placement follows ADR-003: a **ward node** (fixed BLE gateway plus RSM for the continuous φ_CP monitoring) supervises the robot with a heartbeat; the **robot** runs the embodied specifications (task deadlines, witness) and provides evidence; if the robot is unavailable the fallback escalates to the nurse.

Topics (names are stable; message fields map one to one to the Python types above):

| Topic | Message content | Producer | Consumer |
|---|---|---|---|
| `/ralmon/samples` | `Sample` | device nodes, gateway | RSM |
| `/ralmon/events` | `Event` | device nodes, robot | RSM |
| `/ralmon/robot_evidence` | witness and system fields of `EvidenceVector` | robot | ward node |
| `/ralmon/verdicts` | `VerdictRecord` | RSM | attribution |
| `/ralmon/alerts` | `Alert` | attribution | event manager, nurse interface |
| `/ralmon/heartbeat` | node id, sequence number, t_ms | robot, ward node | watchdogs |
| `/ralmon/care_plan` | `CarePlan` (signed) | back-end | RSM (read-only) |

QoS: liveliness and deadline QoS on `/ralmon/heartbeat` and `/ralmon/samples`; the loss of a heartbeat is a C2 evidence source (`SystemHealthEvidence.liveliness_ok`). A deliberate lifecycle transition is not a crash; crash detection uses liveliness and heartbeat (analisi §4.6, row 15:00).

## Package public API

Version 0.2.2. Owner WS05. Consumers: all. Sources: analisi §9 item 5, `01-conventions.md` section 1. History: 0.1.1 (ADR-021, editorial additions of missing public names); 0.2.0 (ADR-024, API reconciliation: names that the contracts of WS05-T02 to WS05-T08 use; no signature changes); 0.2.1 (ADR-053 (d), the named errors, report types and extra entry points of `ralmon.monitor`); 0.2.2 (ADR-057, the three forecasters and their three errors in `ralmon.monitor`).

Consumers import only these names, from the package root.

| Package | Public names |
|---|---|
| `ralmon.signals` | `SignalId`, `Sample`, `Event`, `EventKind`, `DerivedSignal`, `hold_last`, `minutes`, `hours`, `TimeMs`, `DurationMs`, `MS_PER_SECOND`, `MS_PER_MINUTE`, `MS_PER_HOUR`, `ObservedTrace`, `default_derived_signals`, `event_to_sample`, `impulses_on_grid` |
| `ralmon.spec` | `Template`, `TemplateId`, `TemplateKind`, `TemplateInstance`, `CarePlan`, `RobustnessUnit`, `ParameterRegistry`, `RegistryEntry`, `PhysioBounds`, `normalise`, `rank_alerts`, `load_registry`, `load_templates`, `Rho`, `RhoKind`, `PlanVerifier`, `HmacSha256PlanVerifier`, `PlanIntegrityError`, `verify_plan` |
| `ralmon.monitor` | `Monitor`, `MonitorConfig`, `VerdictRecord`, `VerdictState`, `RobustnessInterval`, `Rho`, `RhoKind`, `run_offline`, `Forecaster`, `Forecast`, `StreamingMonitor`, `PointEvaluator`, `make_point_evaluator`, `MonitorConfigError`, `PlanVersionError`, `PlanFeasibilityError`, `MonitorInputError`, `MonitorInvariantError`, `MonitorStats`, `RejectedInput`, `ChannelAvailability`, `OfflineResult`, `run_offline_detailed`, `resolve_subformula_path`, `resolve_subformula_paths`, `PersistenceForecaster`, `AutoRegressiveForecaster`, `DeadlineForecaster`, `ForecasterNotFittedError`, `InsufficientHistoryError`, `UnsupportedSignalError`, `build_calibration_episodes`, `StaleCalibratorError` |
| `ralmon.conformal` | `ConformalCalibrator`, `CalibrationEpisode`, `PredictedViolation`, `AlphaAllocation`, `SplitConformal`, `AdaptiveConformal`, `BonferroniAllocation` |
| `ralmon.attribution` | `EvidenceVector` (and its parts), `AttributionRule`, `Attributor`, `AttributedCause`, `Alert`, `Explanation`, `Detection`, `HierarchicalRule`, `RuleAttributor`, `EvidenceExtractor`, `extract_evidence` |
| `ralmon.benchmark` | `PriorSource`, `LiteraturePriorSource`, `PatientParams`, `AdherenceParams`, `DeviceErrorModel`, `ParamProvenance`, `BenchmarkDay`, `ObservedDay`, `LatentDay`, `GroundTruthEvent`, `InjectedClass`, `generate_benchmark`, `load_benchmark` |
| `ralmon.baselines` | `Detector`, `B1StaticThresholds`, `B2AnomalyDetection`, `B3PlainSTL`, `B4ConformalOnly`, `B5ConformalSTL` |
| `ralmon.eval` | `MatchConfig`, `match_events`, `per_class_prf`, `detection_delay_ms`, `false_alarms_per_patient_day`, `empirical_coverage`, `expected_calibration_error`, `attribution_confusion`, `latency_percentiles`, `Matching`, `mean_interval_width`, `recall_vs_false_alarm_curve`, `accuracy_vs_coverage`, `severity_rank_agreement`, `OursDetector`, `ExperimentConfig`, `run_experiment` |

Ownership note: trace-schema dataclasses are defined in `ralmon.benchmark` (owner WS04) but `Sample` and `Event` are re-exported from `ralmon.signals` because the monitor consumes them without depending on the generator. The single definition lives in `ralmon.signals`; `ralmon.benchmark` imports it. ADR-024 widens the allowed dependencies of `benchmark` to `signals`, `spec` and `monitor` (package roots only).

Note (ADR-021): `OursDetector` is the adapter of the proposed method to the Detector contract; it is owned by WS08-T01 and exported from `ralmon.eval`. `Forecaster` and `Forecast` are defined by the Forecaster contract and exported from `ralmon.monitor`.

Note (ADR-024): `Rho` and `RhoKind` are defined once in `ralmon.spec` and re-exported by `ralmon.monitor`, so that `conformal` (which needs `Rho`) and `monitor` (which uses `conformal`) do not form a cycle. Monitor inputs are annotated with the structural `ObservedTrace` Protocol of `ralmon.signals`; `ObservedDay` satisfies it, so no caller signature changes. `rank_alerts` is typed structurally on `priority` and `sigma_norm`. Until its owner task is `done`, a public name is a placeholder that carries `__ralmon_stub_owner__` and fails loudly when used.
