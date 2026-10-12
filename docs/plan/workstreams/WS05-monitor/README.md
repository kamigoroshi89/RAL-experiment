# WS05-monitor: Monitor, conformal calibrator, attribution, ROS 2 wrappers

## Objective

Build the ROS-independent core library `ralmon` that turns a patient care plan and a stream of samples and events into three-valued verdicts, predicted violations with a conformal guarantee, and attributed alerts, and put thin ROS 2 wrappers around it. The workstream creates the package skeleton and toolchain (T01), the signals layer and the RTAMT spike that decides ADR-013 (T02), the `spec` package (T03), the monitor core (T04), the forecaster (T05), the conformal calibrator (T06), the attribution package (T07), the predictive integration and `run_offline` (T08) and the ROS 2 wrappers of the ward-node and robot placement (T09). Definitive verdicts come from the measured prefix only; the forecaster and the conformal calibrator act only while a verdict is PENDING (ADR-008).

Vocabulary used in every task: a **tier** is an architectural level, a **module** is a component of the runtime safety monitor (RSM), a **node** is a ROS 2 process. **On-path** means between a sample and its alert (gateway, RSM, attribution, event manager), **off-path** means the back-end (ward server) that distributes signed care plans and model updates and is not required to produce an alert. The forecaster predicts, the conformal calibrator calibrates; robustness is reserved to STL semantics; DISPENSE (dispenser opening) is never INTAKE (verified by the robot).

Out of scope here: the benchmark generator (WS04), the baselines (WS06), the metrics and the runner (WS08), the simulation environment, robot task layer and fault injection (WS07), and any clinical parameter value (registry, WS01 and WS00-T07).

## Inputs

- Contracts owned here: `02-interfaces.md#time-and-units`, `#signals`, `#forecaster`, `#conformal-calibrator`, `#monitor`, `#package-public-api`. Contracts read: `#template`, `#parameter-registry`, `#verdict`, `#alert`, `#evidencevector`, `#attribution`, `#detector`, `#trace-schema`, `#ros-2-interfaces`. A contract changes only through an ADR (`01-conventions.md` section 6); the changes this workstream proposes are listed under Outputs.
- ADRs: ADR-003 (ward node plus robot), ADR-004 (DISPENSE versus INTAKE), ADR-007 (past-time formulation), ADR-008 (three-valued verdicts, conformal only in PENDING), ADR-009 (normalisation), ADR-010 (hierarchical attribution), ADR-011 (ROS 2 distribution), ADR-013 (RTAMT), ADR-016 (toolchain), ADR-017 (integer milliseconds), ADR-020 (unverified clinical parameters).
- WS01 artefacts: `docs/formal/01-signals-sampling.md`, `02-templates.md`, `03-parameter-registry.md`, `04-normalisation-ranking.md`, `05-three-valued-semantics.md`, `06-rho-proposition1.md`, `07-alert-tuple-mapping.md`, `09-worked-patient-day.md`; golden files `docs/formal/golden/{templates,ranking,verdicts,conformal}.yaml` (fixture registry F0, `step_ms = 60000`; each case has `hand_calculation`); `configs/registry/hypertension.yaml` and `registry.schema.json`. Tests copy golden cases into `tests/fixtures/<package>/` with their `id` and `source`.
- WS02 artefacts: `docs/models/evidence-channels.md`, `docs/models/attribution-rule.md` (invariants I1 to I6, worked cases W-01 to W-15), `configs/diagnosability.yaml`.
- WS07-T01 artefacts for T09: `ros2/` workspace, `ros2/ralmon_sim/config/package_availability.yaml`.
- Analisi sections and reviewer findings listed under Source sections. Clinical-looking numbers in tests are "illustrative, unverified" (analisi §4.1, §4.2, §4.6, §4.7) or fixture-only; no agent invents a clinical, PK/PD, package-version or citation value.

## Outputs

| Task | Deliverable | Main consumers |
|---|---|---|
| T01 | `pyproject.toml`, `src/ralmon/` with the eight packages, `tests/` tree, placeholders for every public name, the API reconciliation ADR | every workstream |
| T02 | `ralmon.signals`, `tools/rtamt_spike.py`, `rtamt-spike.md`, ADR-013 decision | WS04-T01, WS06-T02, T04 to T09 |
| T03 | `ralmon.spec` (registry and template loaders, `normalise`, `rank_alerts`, `Rho`, plan integrity) | WS04-T02, WS06-T04, T06, WS09-T04 |
| T04 | `StreamingMonitor`, measured `run_offline`, `make_point_evaluator`, `Forecast` and `Forecaster` types | WS04-T10, WS06-T04, WS06-T06, WS08-T01 |
| T05 | three forecasters, model ADR, robot-state signals | WS06-T03, WS07-T04, WS07-T06, WS08 |
| T06 | `SplitConformal`, `AdaptiveConformal`, `BonferroniAllocation` | WS06-T05, WS06-T06, WS07-T06, WS08-T05 |
| T07 | `ralmon.attribution` with renderer and `EvidenceExtractor` | WS06-T01, WS08-T01, WS08-T04, WS11-T02 |
| T08 | predictive mode, `build_calibration_episodes`, end-to-end tests | WS08-T01, WS13-T01 |
| T09 | `ros2/ralmon_ros` (messages, converters, five nodes, ward and robot launch files) | WS07-T03, WS07-T04, WS10 |

### Module layout (guidance; each owner task creates its modules)

| Package | Modules | Task |
|---|---|---|
| `signals` | `units.py`, `ids.py`, `samples.py`, `derived.py` | T01 (`units.py` constants), T02 |
| `spec` | `registry.py`, `templates.py`, `plan.py`, `normalise.py`, `rho.py`, `integrity.py` | T03 |
| `monitor` | `verdict.py`, `config.py`, `reorder.py`, `evaluator.py`, `core.py`, `offline.py`, `forecast.py`, `forecasters.py`, `predictive.py` | T04, T05, T08 |
| `conformal` | `scores.py`, `split.py`, `adaptive.py`, `allocation.py` | T06 |
| `attribution` | `evidence.py`, `alert.py`, `rule.py`, `attributor.py`, `render.py`, `extract.py` | T07 |
| `benchmark`, `baselines`, `eval` | placeholders in `_stubs.py` only | WS04, WS06, WS08 |

Readiness map: until its owner task is `done`, a public name is a placeholder (`__ralmon_stub_owner__`), and a consumer that needs the real type stays blocked. Owners: `signals` T02 (five constants are real from T01); `spec` T03; `monitor` T04, except `build_calibration_episodes` and `StaleCalibratorError` T08; `conformal` T06; `attribution` T07; `benchmark` WS04-T01, T02, T11; `baselines` WS06-T01 to T06; `eval` WS08-T01. Forecaster classes and robot-state signals exist from T05.

### Design decisions fixed by this workstream

1. **D1 Placeholder policy (T01).** A placeholder exists only so that a name imports; it never returns a value. Function placeholders raise `NotImplementedError` naming the owner task; class placeholders cannot be instantiated; both carry `__ralmon_stub_owner__`. Behaviour tests arrive with the owner task.
2. **D2 Layering (T01).** `Rho` and `RhoKind` are defined once in `ralmon.spec` and re-exported by `ralmon.monitor` (otherwise `conformal` and `monitor` import each other); monitor inputs are annotated with the structural `ObservedTrace` Protocol of `ralmon.signals` (`ObservedDay` satisfies it) so `monitor` never imports `benchmark`; `rank_alerts` is typed structurally on `priority` and `sigma_norm`; `benchmark` may import the public APIs of `spec` and `monitor`.
3. **D3 Evaluator (T02, T04).** Robustness intervals on prefixes need custom code; T02 decides whether RTAMT is the point-robustness engine (outcome A), an oracle and the engine of baseline B3 (B), or unusable (C). The entry point for baselines is `make_point_evaluator`.
4. **D4 Late inputs (T04).** An input at or below the released watermark is excluded, listed by `late_inputs()`, and never retracts an emitted verdict (WS01-T01 section 4).
5. **D5 Driver cadence (T04, T08).** `run_offline` pushes every input with `t_rx_ms <= t_k + D` and then calls `advance(t_k + D)` for each grid step `t_k`, where `D` is the reorder delay.
6. **D6 One predictive test per pending instance (T06, T08).** Prediction happens once, at activation, so that the calibration unit is the patient episode and a fixed lead makes episodes exchangeable. `MonitorConfig.alpha` is the total alpha of a patient-day, split by Bonferroni over the instances that have a predictive path.
7. **D7 Alert fields (T07).** `t_ms` is `decided_at_ms` (else `t_eval_ms`); `label` is the attributed cause; `score` is minus the normalised severity; `sigma_norm` is the upper end of `sigma_norm_interval` for definitive records and `predicted_sigma_norm` for predicted ones; `priority` comes from the registry. WS01-T07 wins where it differs (CP5).
8. **D8 Plan integrity (T03, T04).** HMAC-SHA256 over canonical bytes is the placeholder scheme behind the `PlanVerifier` interface; unsigned plans are allowed unless required; the registry version must match; a lower `plan_version` is refused.
9. **D9 Wrappers (T09).** "No logic" is checked by AST rules: no arithmetic and no comparison except `is` in callbacks, one call per loop item, allowed imports only, `ralmon` package roots only. Middleware events become contract `Event`s of kind `NODE_STATE` and flow through the same `EvidenceExtractor` as offline traces.
10. **D10 Model version tokens (T05, T06, T08).** `Forecaster.model_version` and `ConformalCalibrator.calibrated_for` let the monitor refuse a calibrator older than the model (R2-W6).

### Contract changes proposed (each through an ADR with a version bump)

Package public API 0.2.0 (T01: names the tasks need, no signature change); `#verdict` and `#monitor` (T04: `subformula_path`, `predicted_sigma_norm`, keyword-only arguments of `run_offline`; T08: meaning of `alpha`); `#signals` (T05: two robot-state signals); `#forecaster` (T05: `model_version`, `supported_signals`); `#conformal-calibrator` (T06: `calibrated_for`, `model_version` argument of `fit`).

## Dependencies

- Declared upstream: WS01-T03 and T04 (T03), WS01-T05 (T04), WS01-T06 (T06), WS02-T04 and T05 (T07), WS07-T01 (T09). Transitive: WS01-T02 through WS01-T03; WS02-T03 through WS02-T04.
- Undeclared edges to report to the plan lead: T02 needs WS01-T01 (signals document) and, for the spike, WS01-T02; T08 needs WS01-T08 (`09-worked-patient-day.md`) for its golden test; T09 reads WS02-T03 and WS02-T04 through T07. Consumers' undeclared edges: WS04-T01 needs `Sample`, `Event`, `EventKind` (real from T02; WS04-T01 creates `signals/trace_types.py` if T02 is not done); WS06-T01 needs `Detection` (T07); WS06-T02 needs `SignalId` and `EventKind` (T02); WS06-T03 and WS06-T05 need the forecaster class (T05); WS06-T04 needs `make_point_evaluator` (T04); WS07-T04 and WS07-T06 need the robot-state signals (T05).
- Downstream: WS04-T01 (T01), WS04-T10 (T04), WS06-T01 to T06, WS07-T03 and T04 (T09), WS07-T06 (T06), WS08-T01 (T08), WS11-T02 (T07), WS13-T01 (T08).
- Contract anchors: owns `#time-and-units`, `#signals`, `#forecaster`, `#conformal-calibrator`, `#monitor`, `#package-public-api`; reads the others listed under Inputs.

## Acceptance criteria

From the repository root, inside `.venv`; ROS 2 commands in the workspace of WS07-T01.

1. `pytest tests -q` exits 0; `ruff check src tests`, `ruff format --check src tests` and `mypy src/ralmon` exit 0.
2. No name owned by WS05 is a placeholder: `python -c "from ralmon import signals, spec, monitor, conformal, attribution; bad = [f'{m.__name__}.{n}' for m in (signals, spec, monitor, conformal, attribution) for n in m.__all__ if getattr(getattr(m, n), '__ralmon_stub_owner__', '').startswith('WS05')]; print(bad); raise SystemExit(1 if bad else 0)"` prints `[]`.
3. Layering: `pytest tests/test_layering.py -q` exits 0 (allowed edges, package roots only, no cycle, no ROS import in `src/ralmon`).
4. Golden cases of WS01 are reproduced: `pytest tests -q -k golden` runs the case ids of `templates.yaml`, `ranking.yaml`, `verdicts.yaml`, `conformal.yaml` (every parametrised test id carries the golden case id), and `pytest tests/test_end_to_end.py -q` runs the worked patient-day without a skip.
5. ADR-013 records the spike outcome: `grep -n "Spike result" docs/plan/03-decisions.md` prints a line and `test -f docs/plan/workstreams/WS05-monitor/rtamt-spike.md` succeeds.
6. Causality, soundness and coverage properties pass: `pytest tests/monitor tests/conformal -q -k "causal or interval or coverage"` exits 0.
7. Latency and cost are reported: `python -c "import ralmon.monitor as m; d = m.StreamingMonitor.__doc__ or ''; assert 'O(' in d and 'latency' in d.lower()"` exits 0, and `verdict_latency_bound_ms` is tested per template.
8. The forecaster ADR states the honest expectation: `grep -n "uninformative" docs/plan/03-decisions.md` prints the blood-pressure sentence.
9. No clinical constant in code: `pytest tests/spec -q -k clinical_constants` exits 0.
10. ROS 2 wrappers: `pytest ros2/ralmon_ros/test -q -m "not ros"` exits 0; in the workspace `pytest ros2/ralmon_ros/test -q -m ros -rs` exits 0 with no skip; `! grep -rnE "from ralmon\.[a-z_]+\.[a-z_]+" ros2/ralmon_ros` succeeds.
11. Contract versions are bumped and consistent: `python tools/check_plan.py` exits 0.
12. Plan documents of this workstream contain no placeholder tokens: `! grep -rnE 'T[O]DO|T[B]D|[?][?][?]|lore[m]' docs/plan/workstreams/WS05-monitor`.

## Source sections

- analisi §3.1 (RTAMT and other tools, R1-W10), §3.2 (conformal prediction, adaptive conformal inference, non-exchangeability; citation details are verified by a human, ADR-018).
- analisi §4.1 (signals, derived signals, templates, sampling aspects), §4.2 (normalisation, ranking), §4.3 (predictor versus measured verdicts, forecasting targets), §4.4 (definition of rho, one-sided score, allocation of alpha), §4.5 (evidence groups, hierarchical rule, matrix), §4.6 (row 15:00: cascade, crash versus deliberate transition), §4.7 (online monitoring: past-time, intervals, predictive completion, complexity), §4.8 (claim wording), §4.9 items 1, 2, 3 and 7 (architecture, time, cascades, plan governance).
- analisi §5.4 (B3 with RTAMT), §5.6 (A1, A4, A6, A7), §8.1 (glossary), §9 item 5 (monitor as ROS 2 nodes, RTAMT or custom), §10 objection 3 (why a robot).
- `docs/source/review.md`: R1 weaknesses 6, 7, 9, 10; R2 weaknesses 1, 3, 4, 5, 6, 8; R3 weaknesses 2 and 6; AE problem 4.

## Tasks

| id | title | owner | status | depends_on |
|---|---|---|---|---|
| WS05-T01 | Scaffolding of src/ralmon and toolchain | agent | ready | none |
| WS05-T02 | Signals and derived signals; RTAMT spike (ADR-013) | agent | blocked | WS05-T01, WS01-T01, WS01-T02 |
| WS05-T03 | spec package: registry and template loaders, normalisation, ranking, plan signature check | agent | blocked | WS05-T02, WS01-T03, WS01-T04 |
| WS05-T04 | Monitor core: past-time evaluation, robustness intervals, verdicts, reorder buffer, latency bounds | agent | blocked | WS05-T03, WS01-T05 |
| WS05-T05 | Forecaster for continuous signals and robot deadlines | agent | blocked | WS05-T04 |
| WS05-T06 | Split and adaptive conformal calibrator, rho, alpha allocation, recalibration rule | agent | blocked | WS05-T04, WS01-T06 |
| WS05-T07 | Attribution package: hierarchical rule, cascades, Attributor, natural-language rendering | agent | blocked | WS05-T04, WS02-T04, WS02-T05 |
| WS05-T08 | Predictive integration and run_offline end to end | agent | blocked | WS05-T05, WS05-T06, WS05-T07, WS01-T08 |
| WS05-T09 | ROS 2 wrapper packages: RSM, attribution, event manager, watchdog, heartbeat, ward-node placement | agent | blocked | WS05-T08, WS07-T01 |
| WS05-T10 | Monitor history input: run_offline replays the earlier days of the patient (ADR-046) | agent | ready | WS05-T04 |
| WS05-T11 | Robot-channel availability from NODE_STATE colocated reports (ADR-054 (b)) | agent | blocked | WS05-T10 |
| WS05-T12 | Likelihood attributor: posterior over C1, C2, C3 and Alert.p_kappa (ADR-074) | agent | done | WS02-T06, WS05-T07, WS05-T13, WS05-T14 |
| WS05-T13 | EvidenceVector 0.2.0: dispenser group, seq_repeat / seq_gap, cuff_value_repeated, ADR-033 and ADR-040 conventions | agent | done | WS05-T07 |
| WS05-T14 | Conformal calibration of attribution sets (patient-level split, Mondrian per template) | agent | done | WS05-T06, WS02-T06 |

Total estimate: 25.5 person-days (analisi §9 item 5: 4 to 5 person-weeks; WS05-T10 added by ADR-046, 2 pd; WS05-T11 added by ADR-054, 1.5 pd).
