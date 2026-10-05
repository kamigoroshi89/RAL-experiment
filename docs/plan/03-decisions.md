# 03 Decisions (ADR log)

Format per entry: context, decision, alternatives, consequences, status. Status values: `accepted` (from the sources or from an explicit user answer), `proposed` (chosen autonomously; tag `[DA-CONFERMARE]` means a human must confirm or overturn it). A contract in `02-interfaces.md` changes only through an ADR added here.

Index: ADR-001 scope; 002 C3 as integrity; 003 distributed architecture; 004 DISPENSE vs INTAKE; 005 PriorSource; 006 multi-file plan layout; 007 past-time formulation; 008 three-valued verdicts; 009 normalisation; 010 attribution rule; 011 ROS 2 distribution; 012 source files; 013 RTAMT; 014 workstream placement of §9 items; 015 run location of the loop script; 016 Python toolchain; 017 time unit; 018 reference verification; 019 optional second pathology; 020 unverified clinical parameters; 021 contract-gap register; 022 layout and package-dependency amendments; 023 dependency reconciliation and extra WS00 tasks; 024 package public API reconciliation; 025 trace file format and benchmark layout.

---

## ADR-001 Scope: one main pathology, pre-clinical technical validation

- **Context.** The analysis recommends one main pathology and a pre-clinical technical validation without real patients (analisi §5, §9 item 0.2). The workshop paper uses hypertension as its running example.
- **Decision.** The main pathology is hypertension (antihypertensive dosing with blood-pressure response). Validation is semi-synthetic plus ROS 2 simulation plus an optional mock-ward demo. No real patients. This is stated in the abstract, introduction and limitations (analisi §10 objection 1).
- **Alternatives.** Two pathologies from the start (diabetes with the simglucose simulator is the analysis' optional second case, §5.8); a clinical pilot (out of reach and out of scope).
- **Consequences.** WS04 targets hypertension only; the second pathology is an optional task (ADR-019). Human confirmation of scope is task WS00-T02.
- **Status.** accepted (analisi §9 item 0.2).

## ADR-002 C3 reduced to integrity violations with a threat model

- **Context.** "Adversarial tampering" is not identifiable from low confidence, and an informed attacker injecting plausible, cross-modally consistent data is undetectable by construction (analisi §3.6, §4.5, §4.8, §10 item 4).
- **Decision.** Class C3 is renamed and claimed as "integrity or plausibility violations" against declared attack classes (BLE injection and replay without keys, physical access to the dispenser, perception spoofing). Out of scope: compromised robot, RSM or specification. The diagnosability matrix reports the undetectable cases as a result.
- **Alternatives.** Keep "tampering" and claim general adversarial detection (rejected: not defensible).
- **Consequences.** WS02 owns the threat model and matrix; WS04 injects C3 at two attacker-knowledge levels (naive and informed); WS08 reports the non-detectable rows.
- **Status.** accepted (analisi §3.6, §9 item 0.2).

## ADR-003 Distributed architecture: ward node plus robot

- **Context.** An RSM only on the robot is a single point of failure, loses BLE streams when the robot leaves the room, and cannot serve N patients (analisi §2 R3 weakness 2, §4.9 item 1).
- **Decision.** A fixed ward node (BLE gateway plus RSM for continuous φ_CP monitoring) supervises the robot with a heartbeat. The robot runs the embodied specifications (task deadlines, presence and intake witness) and provides evidence. If the robot is unavailable, the fallback escalates to the nurse. The auditability claim is kept ("single auditable verification path") with a watchdog added.
- **Alternatives.** Robot-only RSM (rejected: R3 fatal); ward-only RSM (rejected: robot loses its role and A4 has nothing to measure).
- **Consequences.** Contract `#ros-2-interfaces` encodes placement. The robot's contribution stays central because it executes the obligations induced by the specification (φ_resp, φ_sched) and is the only witness channel.
- **Status.** accepted (analisi §4.9 item 1, §9 item 0.2).

## ADR-004 DISPENSE is distinct from INTAKE

- **Context.** A dispenser opening does not prove intake (analisi §4.9 item 5, §8.1).
- **Decision.** Two signals: `DISPENSE` (device) and `INTAKE` (verified by the robot). The witness channel is the only source of `INTAKE`.
- **Alternatives.** Treat opening as intake (rejected: hides the main adherence weakness).
- **Consequences.** Templates use dispense for hold and count, and intake for response evidence where present. The double-take versus bounce confounder depends on dispenser content sensing (analisi §4.5 matrix).
- **Status.** accepted.

## ADR-005 PriorSource interface with a literature implementation first

- **Context.** MIMIC-IV and eICU access requires PhysioNet credentialing (course, data use agreement) and can take days to weeks; it is on the critical path (analisi §5.1, §9 item 0.6). The user's answer at bootstrap: access not yet started.
- **Decision.** All benchmark parameters flow through `PriorSource`. `LiteraturePriorSource` uses values from published literature with mandatory `source_ref` per parameter. `MimicPriorSource` (and an eICU variant for the shift test) is added when access exists. Public-access data (VitalDB, MIT-BIH noise stress test database, BIDMC, PhysioNet/CinC 2015) can be used immediately for noise and artefact modelling.
- **Alternatives.** Wait for MIMIC before starting WS04 (rejected: blocks the critical path); invent parameters (rejected: forbidden by PROMPT precedence).
- **Consequences.** Results produced before MIMIC access are labelled "literature priors"; WS08 repeats key experiments with MIMIC priors once available. Human owner: WS00-T04.
- **Status.** accepted.

## ADR-006 Multi-file plan layout (option A)

- **Context.** ~14 workstreams and ~33-42 pw (analisi §9) exceed what one agent can hold in context; roadmap items 4, 5 and 7 must run in parallel.
- **Decision.** Workstream folders with README and small task files; contracts frozen in `02-interfaces.md`; ADR log here; traceability in `04`.
- **Alternatives.** B: plan per paper section; C: single file. See `docs/superpowers/specs/2026-09-29-ral-dev-plan-design.md` section 3.
- **Consequences.** A verifier (`tools/check_plan.py`) keeps ids, dependencies and references consistent.
- **Status.** accepted.

## ADR-007 Past-time formulation and derived signals for counters

- **Context.** Future operators block immediate verdicts; counters "outside STL" break uniform σ and ξ (analisi §4.1, §4.7, §2 R1 weaknesses 5 and 6).
- **Decision.** Constraints are written in past-time STL (once, historically) so each obligation is evaluated at its deadline with a bounded latency. Counters are derived signals with atomic predicates (robustness `limit - count`). "Pressure decrease" uses a derived pre-dose signal `bp_pre`; the freeze operator (STL*) is cited as an alternative but not implemented. Point-event windows use `O[W, W+T_s]`.
- **Alternatives.** Future-time STL with bounded eventually plus look-ahead buffering; STL* freeze.
- **Consequences.** WS01 documents the equivalence to the future-time form (ablation A7). Time robustness is used for timing constraints.
- **Status.** accepted (analisi §4.1).

## ADR-008 Three-valued verdicts; conformal prediction only in PENDING

- **Context.** The workshop text contradicts itself on whether conformal envelopes or measured values ground the verdict (analisi §4.3).
- **Decision.** Definitive verdicts come only from the measured prefix with robustness intervals (unknown future replaced by physiological bounds). Conformal prediction acts only in the PENDING state and produces early warning. Definition of ρ by verdict type as in analisi §4.4. The predictive component targets continuous signals and robot care-delivery deadlines rather than five-a-day blood pressure.
- **Alternatives.** Conformal envelope on measured values (rejected: suppresses true positives near thresholds); pure anomaly detection (rejected: what the paper moves away from).
- **Consequences.** Proposition 1 (WS01) gives the one-sided guarantee; A1 and A2 ablations test the components.
- **Status.** accepted (analisi §4.3, §4.4, §4.7).

## ADR-009 Normalised robustness and lexicographic ranking

- **Context.** Robustness in mmHg, ms and doses cannot be combined by `min` (analisi §4.2).
- **Decision.** Per-predicate normalisation `clip(sigma / s_pi, -1, 1)` with clinician-fixed scales; ranking lexicographic by clinician priority then σ̃; never normalise by conformal interval width. AGM robustness and weighted STL are cited as alternatives; ordinal NEWS2-style bands as another.
- **Alternatives.** As listed.
- **Consequences.** Scales and priorities live in the parameter registry; ablation A3 measures the effect; optional clinician-ranking agreement study in WS11.
- **Status.** accepted.

## ADR-010 Attribution: hierarchical rules with abstention

- **Context.** κ has no producing module and C2/C3 identifiability is undefined (analisi §4.5).
- **Decision.** Start with the hierarchical auditable rule (integrity → C3, else system → C2, else coherent clinical → C1, else UNDETERMINED). Six evidence groups form the `EvidenceVector`. Cascades propagate a root cause. A Bayesian variant is optional.
- **Alternatives.** Probabilistic network first (rejected: harder to audit, needs benchmark-fit probabilities).
- **Consequences.** UNDETERMINED is a valid, scored output; the diagnosability matrix is a machine-readable artefact; A4 removes the witness channel.
- **Status.** accepted.

## ADR-011 ROS 2 distribution [DA-CONFERMARE]

- **Context.** The analysis says "Humble or Jazzy, depending on available TIAGo packages" and asks to verify whether a TIAGo Pro model exists for ROS 2 (analisi §5.2). At bootstrap the user chose Jazzy with Gazebo Harmonic.
- **Decision.** Target ROS 2 Jazzy with Gazebo Harmonic. If WS00-T05 finds that the needed TIAGo or hospital-world packages exist only for Humble or Gazebo Classic, this ADR is superseded by one selecting Humble. The `ralmon` core is unaffected because it is ROS-independent.
- **Alternatives.** Humble; ROS-native from the start.
- **Consequences.** WS07 begins with a package availability check.
- **Status.** proposed [DA-CONFERMARE] (confirmation pending WS00-T05).

## ADR-012 Source files in `docs/source/` [DA-CONFERMARE]

- **Context.** PROMPT.md expects `docs/source/analisi.md` and `docs/source/review.md`. The repository held `analisi_RAL_clinical_pathways.md` (which contains the reviewer simulation in its §2) and the workshop PDF. No separate review file existed. The prompt says a missing source leads to a blocked state, but also forbids questions and asks for the most conservative choice.
- **Decision.** `docs/source/analisi.md` is a byte-identical copy of the original; `docs/source/review.md` is a verbatim extract of lines 32-153 of the original (its §2: R1, R2, R3, AE meta-review), with a short header. Originals are left in the repository root, not moved. Files in `docs/source/` are read-only. The header of `review.md` states that it is an extract. Finding ids used for traceability are defined in `04-review-traceability.md`.
- **Alternatives.** Write `BLOCKED.md` and stop (rejected: the required content exists verbatim in the analysis; stopping would lose no information but block all progress).
- **Consequences.** If a separate authoritative review document exists, replace `review.md` and rerun the verifier.
- **Status.** proposed [DA-CONFERMARE].

## ADR-013 RTAMT as reference STL tool [DA-CONFERMARE]

- **Context.** The analysis lists RTAMT, Breach and S-TaLiRo and says "RTAMT o custom" for the monitor (analisi §3.1, §9 item 5, B3 uses RTAMT).
- **Decision.** Original proposal: RTAMT is the reference implementation wrapped behind `ralmon.spec` and `ralmon.monitor`; a custom monitor may replace it if RTAMT cannot express robustness intervals or sparse sampling. Updated by WS05-T02 after the spike: the evaluator is custom and RTAMT is not a dependency of the monitor (outcome C, see below).
- **Alternatives.** Custom monitor from the start; Breach or S-TaLiRo (MATLAB dependence); outcome B (custom evaluator, RTAMT kept as test oracle and as the engine of baseline B3), not adopted for the reasons in the record.
- **Consequences.** The spike result is recorded in `docs/plan/workstreams/WS05-monitor/rtamt-spike.md`. `ralmon.spec` and `ralmon.monitor` do not import RTAMT; no `rtamt` extra is added to `pyproject.toml`; WS06-T04 builds baseline B3 on `make_point_evaluator` and the paper says that its point-robustness evaluator is the project's own (the wording "same templates with RTAMT" of analisi §5.4 is not used).
- **Status.** proposed [DA-CONFERMARE].

Spike result (WS05-T02, closes the spike of ADR-013): outcome C. Tested RTAMT 0.4.10 on Python 3.12.8 (host throwaway venv) and 3.12.15 (`ralmon-dev` container, same report); on Python 3.14.4, the Python of the repository, `import rtamt` fails (`No module named 'typing.io'`). Q1 FAIL (4 of 7 templates translate mechanically and equal the goldens; `sched` and `int` contain `age`, `sys` uses an equality atom that RTAMT evaluates as `-abs(a - b)`), Q2 PASS, Q3 NOT-SUPPORTED (`update` returns a point value; the endpoint rule is unsound for `range`, `count` and `sys`), Q4 FAIL (no guard rule, no unknown value), Q5 FAIL (8 of 10 time-margin goldens only with hand rewrites), Q6 PASS (operator updates linear in the instances, but each timed `once` or `historically` scans its window at every step). Outcome C is forced by the Q1 failure (rule of WS05-T02 check 9). Entry point that WS06-T04 must call for raw robustness: `make_point_evaluator` of `ralmon.monitor`, created by WS05-T04. Evidence and the reasons for not adopting outcome B: `docs/plan/workstreams/WS05-monitor/rtamt-spike.md`. This remains `[DA-CONFERMARE]` until a human confirms it.

## ADR-014 Placement of §9 items in workstreams [DA-CONFERMARE]

- **Context.** PROMPT.md lists WS00 as human-only tasks and workstreams WS01-WS13; roadmap §9 has phase-0 items 0.1-0.7 and items 1-13. Prompt and §9 agree on 14 workstreams (WS00-WS13, with WS06 baselines and WS12 paper). Two items do not fit a human-only WS00.
- **Decision.** Phase-0 items 0.4 (title) and 0.5 (abstract without numbers) are agent-doable and are placed in WS12 as tasks (owner agent), not in WS00. Item 0.7 also covers verifying the TIAGo simulation packages. WS00 holds 0.1, 0.2, 0.3, 0.6, 0.7 (human). The ROS 2 node realisation of §9 item 5 is delivered in WS05 (thin wrappers), while WS07 owns the simulation environment, robot faults and latency measurement.
- **Alternatives.** Put 0.4 and 0.5 in WS00 as human tasks.
- **Consequences.** M0 (commitment letter) depends on WS00 and two WS12 tasks.
- **Status.** proposed [DA-CONFERMARE].

## ADR-015 Run location of the loop script [DA-CONFERMARE]

- **Context.** `prompt/run-plan.sh` starts with `cd "$(dirname "$0")"`, which sets the working directory to `prompt/`, while PROMPT.md and the design assume the repository root (`docs/`, `tools/`, `CLAUDE.md`).
- **Decision.** This bootstrap ran with the repository root as working directory. To use the script unchanged it must be copied or symlinked to the repository root, together with `PROMPT.md` and `.claude/settings.json`. `prompt/` is committed as delivered.
- **Alternatives.** Edit the script (rejected: not asked; part of user-provided input).
- **Consequences.** None for the plan content.
- **Status.** proposed [DA-CONFERMARE].

## ADR-016 Python toolchain [DA-CONFERMARE]

- **Context.** The sources fix neither Python version nor tools.
- **Decision.** Python 3.11+, pytest, Hypothesis for property tests, ruff (format and lint), mypy strict on `src/ralmon`, `numpy` random Generators with explicit seeds.
- **Alternatives.** unittest; black and flake8; pyright.
- **Consequences.** WS05-T01 creates `pyproject.toml` with these settings.
- **Status.** proposed [DA-CONFERMARE].

## ADR-017 Time unit: integer milliseconds [DA-CONFERMARE]

- **Context.** Sparse, irregular sampling, event impulses and windows in minutes and hours need one unit (analisi §4.1 item 2).
- **Decision.** Integer milliseconds since trace start; conversion helpers in `ralmon.signals`.
- **Alternatives.** Float seconds (accumulates drift and equality problems); datetime objects.
- **Consequences.** Contracts use `TimeMs` and `DurationMs`.
- **Status.** proposed [DA-CONFERMARE].

## ADR-018 Reference verification is a human step

- **Context.** The analysis marks many references with a dagger (unverified venue, year or authors) and states all must be checked on DBLP or Google Scholar before citation (analisi §3).
- **Decision.** WS03 agents assemble bibliography entries with a `verified` flag defaulting to false. A human sets it after checking. The paper build (WS12) fails if a cited entry is unverified. No network access is assumed for agents.
- **Alternatives.** Agents verify from memory (rejected).
- **Consequences.** A human review task exists in WS03 (WS03-T06). Citations added later by WS12 are checked in WS12-T07 (claim audit) and must go through the same verification before the paper build; WS00-T08 supplies full texts of the key papers so that details can be checked on the paper itself.
- **Status.** accepted (analisi §3 note).

## ADR-019 Second pathology is optional and last

- **Context.** The analysis lists a second pathology (diabetes with the UVA/Padova simulator, simglucose) as optional and the third item to cut (analisi §5.8, §9).
- **Decision.** One optional task in WS04, `ready` only after M3, and excluded from the critical path.
- **Alternatives.** Include from the start.
- **Consequences.** None if cut.
- **Status.** accepted.

## ADR-020 Clinical parameter values are unverified until reviewed

- **Context.** Values in analisi §4.1 are explicitly illustrative; onset and peak times vary by hours across antihypertensive drugs (analisi §2 R3 weakness 3).
- **Decision.** The parameter registry starts empty of clinical claims: any value carries `rationale` and `reviewed_by`; values with no review are reported in the paper as unverified. No agent assigns a drug or guideline anchor from memory; WS01 defines the procedure and WS00-T07 performs the clinical review (WS00-T03 recruits the clinician).
- **Alternatives.** Pick a specific drug and guideline now (rejected: invention risk).
- **Consequences.** M1 requires the clinician's review of the registry.
- **Status.** accepted.

## ADR-021 Contract-gap register: amendments are decided at M1 [DA-CONFERMARE]

- **Context.** During phase F6 the fourteen workstream authors, reading `02-interfaces.md` against analisi, reported gaps and ambiguities. None was edited during authoring, because contracts change only through an ADR. The reports concern:
  - `Template`, `Verdict`, `Alert`: the unit of mixed-atom templates (HOLD, RESP, SYS), the treatment of sigma = 0, the range of `sigma_norm` and the direction of `priority`, the "possible" variant needing a lower quantile, whether `creates_robot_obligation` also holds for INT, a measurement-count template, `VerdictRecord` without a sub-formula path or predicted severity, `Detection` without a template field, the attributed cause of predicted alerts;
  - `EvidenceVector`: no field for dispenser content or dispense interval (needed for the double-take versus bounce rows of analisi §4.5), `seq_gap_or_replay` mixing message loss (C2) and replay (C3), no clock-health field, undefined key of the evidence mapping, and no owner for building an `EvidenceVector` from an observed day and a verdict record;
  - `Trace schema`: impulse signals are events only, no carry-over across midnight, no benchmark reader;
  - `PriorSource`: `PatientParams`, `AdherenceParams` and `DeviceErrorModel` lack fields the generator needs;
  - `Conformal calibrator`: no model-version token for the recalibration rule, `CalibrationEpisode` tied to `TemplateId` and normalised sigma while B4 and B5 work on other residuals, `sigma_true` wording versus the rule that detectors fit on training ground truth only;
  - `Metrics` and `Experiment config`: `Matching` undefined, no first-decidable instant in `GroundTruthEvent`, no alpha grid, bootstrap settings or shift conditions, macro-F1 and abstention rate without a function;
  - `Signals`: no robot ETA or task-queue signal for deadline forecasting; `Time and units`: no time-compression rule for the lab demo;
  - `Package public API`: names used elsewhere but missing (`TimeMs`, `DurationMs`, `Forecaster`, `Forecast`, concrete monitor and attributor, `Matching`, four metrics functions, a benchmark reader, a factory for the proposed detector "ours").
- **Decision.** (a) The public-API omissions are editorial and are added now (contract `Package public API` moves to 0.1.1); the semantic gaps are not edited during bootstrap. (b) Each semantic gap is resolved by the owning task through a proposed ADR, and all are consolidated at the M1 freeze: WS01-T08 resolves the template, verdict and alert points (its README lists them as CP1 to CP13), WS02-T03 the evidence points, WS04-T02 the prior and trace points, WS05-T01, T04, T06 the monitor, calibrator and cycle points, WS08-T01 the metrics and experiment points, WS07-T03 and WS10-T04 the time-compression rule. (c) No implementation task that consumes a gap may start before the ADR of the owning task is `accepted`; the owning tasks precede consumers in `depends_on` (see ADR-023).
- **Alternatives.** Edit `02-interfaces.md` now (rejected: guesses would bypass the owning workstreams and the clinician review); ignore (rejected: agents would diverge).
- **Consequences.** Contract versions bump at M1. Agents reading a contract before M1 must also read this ADR and the "contract points" section of the owning README.
- **Status.** proposed [DA-CONFERMARE].

## ADR-022 Layout and package-dependency amendments [DA-CONFERMARE]

- **Context.** Authors of WS02, WS03, WS04, WS05, WS09, WS10, WS11 and WS13 needed places for documents, configs, tool tests and lab code that `01-conventions.md` did not list, and WS04 needs `spec` and `monitor` for ground-truth labelling.
- **Decision.** `01-conventions.md` section 1 now lists `configs/`, `docs/formal|models|related-work|benchmark`, `paper/refs|figures|tables`, `tools/check_bib.py`, `tools/figures/`, `hardware/lab_demo/`, `tests/tools|study|hardware`. `benchmark` may import `spec` and `monitor` only in the labeller, validation and prior-registry loader modules; the generator itself depends on `signals` only. `tools/check_plan.py` keeps its rule 8 (no file in `src/`) for the bootstrap; WS05-T01 relaxes it to "no file in `src/` outside the scaffold" once the scaffold exists (its task text carries the change).
- **Alternatives.** Force all such items into existing folders (rejected: hides ownership).
- **Consequences.** Layout is a convention, not a contract, but the dependency exception is recorded here so that an import-linter rule can encode it.
- **Status.** proposed [DA-CONFERMARE].

## ADR-023 Dependency reconciliation and extra WS00 tasks [DA-CONFERMARE]

- **Context.** The F6 authors reported missing dependency edges between workstreams and human hand-offs with no owner. The index skeleton was regenerated and all task files patched consistently.
- **Decision.** Edges added: WS00-T07 after WS01-T04, WS01-T05, WS02-T04; WS01-T08 after WS00-T07 (M1 requires the clinician review); WS05-T02 after WS01-T01, WS01-T02; WS05-T08 after WS01-T08; WS04-T06 after WS05-T02, WS00-T09; WS04-T07 and WS04-T08 after WS02-T03; WS06-T01 after WS05-T03, WS05-T07; WS06-T02 after WS05-T02; WS06-T04 after WS05-T04; WS06-T05 after WS05-T05; WS06-T06 after WS05-T04, WS05-T05, WS00-T08; WS07-T04 after WS05-T05; WS07-T06 after WS05-T05, WS08-T01, WS04-T11; WS07-T07 after WS08-T01; WS09-T02 after WS09-T01; WS09-T04 after WS09-T01, WS05-T03; WS09-T05 after WS08-T04; WS10-T01 after WS02-T05; WS10-T04 after WS10-T03; WS10-T06 after WS08-T01; WS11-T02 after WS06-T02, WS06-T03; WS12-T03 and WS12-T04 after WS00-T07; WS12-T05 after WS07-T07, WS10-T06; WS13-T02 after WS09-T02, WS09-T03, WS09-T04; WS13-T03 after WS13-T04, WS00-T01; WS13-T04 after WS13-T01. New human tasks: WS00-T08 (full texts of key papers, needed by WS06-T06), WS00-T09 (download of open datasets, needed by WS04-T06), WS00-T10 (verification of the literature-prior provenance table, non-blocking). Not added on purpose: WS12-T01 does not wait for PhysioNet credentialing (the commitment-letter abstract must not depend on an external wait; it is worded so that it holds with or without MIMIC); WS12 does not depend on the optional vignette study.
- **Alternatives.** Leave the edges to the executing agents (rejected: parallel agents would start on missing inputs).
- **Consequences.** The critical chain now includes the clinician review WS00-T07 before the M1 freeze. WS10-T06 (analysis or fallback video) precedes the experiments section, so the section can be written whether the lab demo is completed or cut. Total estimate is 200.75 person-days.
- **Status.** proposed [DA-CONFERMARE].

## ADR-024 Package public API reconciliation (0.1.1 to 0.2.0) [DA-CONFERMARE]

- **Context.** The Package public API table (0.1.1) is the list that the tests of WS05-T01 parse, but the contracts of WS05-T02 to WS05-T08 use names it does not list. `TimeMs` and `DurationMs` are used in every contract but are exported without the three time constants; `Forecaster` and `Forecast` have no owner package beyond the table entry; no concrete `Monitor` or `Attributor` is public although the ROS 2 wrappers and WS08 need one; `Rho` is defined in `#verdict` (monitor) but `PredictedViolation` (conformal) needs it while `monitor` uses `conformal`, which would create a cycle; `run_offline` takes `ObservedDay`, defined in `benchmark`, while WS04-T10 needs `monitor`; `rank_alerts` names `Alert`, which lives above `spec`.
- **Decision.** Add to the table: `signals` gets `MS_PER_SECOND`, `MS_PER_MINUTE`, `MS_PER_HOUR`, `ObservedTrace`, `default_derived_signals`, `event_to_sample`, `impulses_on_grid`; `spec` gets `Rho`, `RhoKind`, `PlanVerifier`, `HmacSha256PlanVerifier`, `PlanIntegrityError`, `verify_plan`; `monitor` gets `StreamingMonitor`, `PointEvaluator`, `make_point_evaluator`, `MonitorConfigError`, `PlanVersionError`, `build_calibration_episodes`, `StaleCalibratorError`; `conformal` gets `BonferroniAllocation`; `attribution` gets `RuleAttributor`, `EvidenceExtractor`, `extract_evidence`. `Rho` and `RhoKind` are defined once in `ralmon.spec` and re-exported from `ralmon.monitor`. The structural `ObservedTrace` Protocol is added to `ralmon.signals` and monitor inputs are annotated with it (`ObservedDay` satisfies it; the contract signature is unchanged for callers). `rank_alerts` is typed by a structural Protocol on `priority` and `sigma_norm`. `01-conventions.md` section 1 is to be amended so that `benchmark` may import the public APIs of `spec` and `monitor` (package roots only); this widens ADR-022, which limited that exception to the labeller, validation and prior-registry loader modules, and the layering test of WS05-T01 encodes the wider package-level rule. The package graph is `signals` < `spec` < `conformal` < `monitor` < `attribution`, with `benchmark` above `monitor` and `baselines` and `eval` on top. No signature of any contract changes here. Package public API moves from 0.1.1 to 0.2.0.
- **Alternatives.** Move the day dataclasses to `signals` (rejected: splits the trace schema owned by WS04); import `benchmark` from `monitor` (rejected: creates a cycle with WS04-T10).
- **Consequences.** Affected tasks: WS05-T02 to WS05-T08, WS04-T02, WS04-T10, WS06-T03 to WS06-T06, WS08-T01, WS05-T09. The name `load_benchmark` (in the table since ADR-021) has no owner in the readiness map of the WS05 README; WS05-T01 assigns its placeholder to WS04-T11 (benchmark builder), to be confirmed by WS04. `01-conventions.md` section 1 still carries the ADR-022 wording until this ADR is confirmed.
- **Status.** proposed [DA-CONFERMARE].

## ADR-025 Trace file format and benchmark directory layout [DA-CONFERMARE]

- **Context.** Contract `02-interfaces.md#trace-schema` rule 3 leaves the file format (JSON or Parquet) to WS04-T01 and requires it to be recorded as an ADR. The bit-for-bit reproducibility rule of `01-conventions.md` section 3 needs byte-identical output for equal input, and the ground-truth discipline needs a detector run that never reads the truth.
- **Decision.** Canonical JSON (`ralmon.benchmark.trace`): sorted keys, two-space indent, final newline, floats written with `repr`, non-finite numbers rejected, no timestamp or host field. Layout of one benchmark directory: `manifest.json` (generator git revision, generation seed, prior source name and provenance, `fixture_only`, `n_unfilled`, `n_unverified`, patients with split and cohort, sha256 of every listed file, event counts, settings); `days/<patient_id>/<day_index>.json` holding `ObservedDay` only; `truth/<patient_id>/<day_index>.json` holding the `LatentDay`, the ground-truth events and the sidecars. Observed files and truth files live in different directories, a refinement of contract rule 3 that keeps `truth/` out of every detector run; an observed file has exactly the keys `patient_id`, `day_index`, `seed`, `samples`, `events`, `care_plan_id`, and the writer refuses a payload key that contains `latent` or `ground_truth`. The truth file has the keys `latent` and `ground_truth` and the optional JSON-native sidecars `injection_log` and `behaviour_log`, which the contract's `GroundTruthEvent` has no fields for (WS08 reads them for per-magnitude and per-level results); they are stored as given after a JSON-native check. The manifest is strict: a missing or unknown top-level key is an error, so no wall-clock field can appear, and a patient listed in two splits is a `SplitLeakError` (contract rule 2). `Sample`, `Event` and `EventKind` have a single definition in `ralmon/signals/trace_types.py` (created by WS04-T01 because WS05-T02 was not done; WS05-T02 imports and does not redefine them). Plans go to `plans/<care_plan_id>.json` (owner WS04-T11, not part of this decision).
- **Alternatives.** Parquet (rejected for now: needs an extra dependency and its byte-level output is not guaranteed identical across writer versions; reconsider only if a measured size or speed problem appears at 1400 patient-days); one file per day holding observed and truth together (rejected: a detector run would have to open a file that contains the truth); JSON Lines (rejected: no gain at this scale, weaker canonical form).
- **Consequences.** WS04-T02 to WS04-T12, WS06, WS07-T03 and WS08-T01 read and write through `ralmon.benchmark.trace`. Sequences read back are tuples, so compare with tuples. Extra manifest information goes into `settings` or a patient entry (for example `role`, `pair`), never into a new top-level key without a follow-up ADR. No contract signature changes; the trace-schema contract version is unchanged.
- **Status.** proposed [DA-CONFERMARE].

## ADR-026 INT witness obligation: static backward window or dynamic forward window [DA-CONFERMARE]

- **Context.** WS01-T02 (`docs/formal/02-templates.md` section 5.3 and open point TG-8) found that the INT template looks back from the dispense, `historically(dispense -> once[0, int_window](presence or intake or auth))`, so an obligation created at the DISPENSE arrives after its own window has closed. WS01-T02 therefore defines the INT robot obligation as static, derived from the schedule's dispense ticks, with the backward window `[a - int_window, a]`. WS07-T04 (`test_witness_obligation_from_int_instance`: a DISPENSE at 2_000_000 gives the window [2_000_000, 2_010_000]) and WS04-T10 (step 3: instances created "at each DISPENSE, RESP and INT") assume a dynamic obligation created at each DISPENSE with a forward window. WS05-T04 test 5 expects an early SATISFIED (`decided_at_ms` 32_700_000), whereas WS01-T01 section 3.7 and WS01-T02 section 1.5 decide at the anchor's decision step `k_d`.
- **Decision.** Proposed: keep the static backward form as the reference semantics of the template library (it is the one the 26 golden cases fix), and align WS07-T04 and WS04-T10 to it after confirmation. The early-decision question of WS05-T04 test 5 is settled by WS01-T05 (three-valued semantics), not here.
- **Alternatives.** A dynamic forward witness obligation after each DISPENSE (a second witness formula with its own golden cases and a change to the obligation record of CP9); both forms together.
- **Consequences.** Until confirmed, WS07-T04 and WS04-T10 stay `blocked` and carry a note. No signature of `02-interfaces.md` changes in this ADR; adopting the alternative would need CP9.
- **Status.** proposed [DA-CONFERMARE].

## ADR-027 Fixture registry for runs before the clinician review [DA-CONFERMARE]

- **Context.** WS01-T03 (`docs/formal/03-parameter-registry.md`, section 7 open point OP-11) seeds `configs/registry/hypertension.yaml` with the 17 illustrative values that analisi gives and leaves 17 names `unset` (among them `sched_window`, `delta_resp`, `cuff_inflation_min`, the scales `scale_hold`, `scale_resp`, `scale_sys`, `scale_int`, the priorities `priority_count`, `priority_resp`, `priority_sys`, `priority_int`, and `cuff_error_sd`) until the clinician review WS00-T07, which comes after the formalization freeze. Tasks that run before that review need a value for those names: WS05-T03 (test 15 copies fixture F0 into the WS01-T03 schema), WS06-T01 (test 21, stub registry) and WS06-T02 (step 2: "if a role has no entry, stop and report it"), WS04 (README working names) and any benchmark run. No task owns the creation of a fixture registry, and the number of registry rows the review sheet holds (34: entries plus unset names) differs from what WS00-T07 test 3 expects (the number of entries, 17).
- **Decision.** Proposed: a separate file `configs/registry/fixture.yaml` holding the fixture F0 rows, every entry marked FIXTURE-ONLY, `reviewed_by: null`, rationale ending "illustrative, unverified", loaded only through an explicit `allow_fixture_only` option and never used for a reported result; created by WS05-T03 (owner of the registry loader), not by WS01. `hypertension.yaml` stays the single source of clinical parameters and keeps its `unset` names until WS00-T07.
- **Alternatives.** Seed the unset names in `hypertension.yaml` with the F0 numbers (rejected: puts fixture values in the clinical registry, against ADR-020); let each task carry its own stub registry (rejected: duplicates values and hides the dependency).
- **Consequences.** WS06-T01, WS06-T02, WS01-T08 and WS00-T07 carry a note and stay `blocked` until this ADR is decided; WS00-T07 test 3 and test 4 should count the review-sheet rows as entries plus `unset` names, and bounds once. No signature of `02-interfaces.md` changes in this ADR.
- **Status.** proposed [DA-CONFERMARE].

## ADR-028 Order key of `rank_alerts`: tie-break and predicted versus violated [DA-CONFERMARE]

- **Context.** WS01-T04 (`docs/formal/04-normalisation-ranking.md`, open points OP-3, OP-6, OP-15 and OP-16) makes the lexicographic order of `rank_alerts` total and deterministic with the key `K0 = (priority, sigma_tilde, t_ms, instance_key)`, where the contract docstring names only `(priority, sigma_norm)`. It also defines a variant `K1` that places VIOLATED alerts before PREDICTED_VIOLATION alerts inside a priority. WS05-T03 test 7 ("equal `(priority, sigma_norm)` keep input order") and test 9 ("a local dataclass with only those two fields is accepted") conflict with `K0`, which needs `t_ms` and `xi.instance_key`; ADR-024 types `rank_alerts` on `priority` and `sigma_norm` only, and `Alert` carries no patient identifier although `instance_key` is unique only within a care plan.
- **Decision.** Proposed: adopt `K0` as the reference order (a tie-break that makes the output independent of the input order, refining the docstring without contradicting it), leave `K1` (VIOLATED first) as an open alternative to be settled by WS01-T05 (three-valued semantics), and extend the structural Protocol of ADR-024 with `t_ms` and `instance_key` (and the patient identifier of the care plan where alerts of several patients are ranked together).
- **Alternatives.** Keep the docstring order and a stable sort (output depends on input order, so two runs can differ; rejected); adopt `K1` now (needs the WS01-T05 decision on how a predicted alert is graded).
- **Consequences.** WS05-T03 tests 7 and 9 are adapted after confirmation (they stay `blocked` and carry a note); the severity questions of OP-14 (upper end of the interval for a VIOLATED alert) and OP-15 (`predicted_sigma_norm`) are settled by WS01-T05, T06 and T07, not here. No signature of `02-interfaces.md` changes in this ADR beyond the Protocol of ADR-024.
- **Status.** proposed [DA-CONFERMARE].

## ADR-029 Extensions of the verdict contract adopted by the three-valued semantics [DA-CONFERMARE]

- **Context.** WS01-T05 (`docs/formal/05-three-valued-semantics.md`, section 11 and open points CP3, CP6, CP7, CP12, OP-T05-6 and OP-T05-12 to OP-T05-21) states the contract `#verdict` word for word and adopts, meanwhile, the following extensions that the contract text does not contain: (CP3) a tie rule, so that a closed instance with `lo = hi = 0` is SATISFIED, while the residual case `lo = 0 < hi` stays PENDING (a sound refinement `lo >= 0` is recorded but not adopted); (CP6) an instance whose decision window holds a stale-open position stays PENDING with a marker `undecidable: <reason>:<signal>`, with an optional `undecidable` (and `guard_failed`) field proposed for `VerdictRecord`; (CP7) a warm-up prefix counts as a known prefix (hypothesis H-hist) and instances open at the end of the trace are PENDING or decided early by the rule of Lemma 12b when `k_d > K`; (CP12) infinite interval endpoints with a serialisation rule; per-step records and refinement records for the graded lateness of SCHED; the lateness rule `t_rx > t_{k_up(t_dev)} + D` independent of the `advance` calls.
- **Decision.** Proposed: adopt these extensions as the reference semantics of the verdict layer, to be ratified (or amended) by WS01-T08 at the formalization freeze, and add the optional fields to `VerdictRecord` only then, with the contract version bump.
- **Alternatives.** Keep the contract wording and reject the extensions (the golden cases V-INT-3, V-LATE-2 and the 12b examples would then have no rule); adopt the sound refinement `lo >= 0` instead of the tie rule.
- **Consequences.** WS05-T04 (steps 1, 4 and 8, tests 5, 10, 11), WS05-T07 (`update` returns only new or changed alerts), WS05-T08 (prediction once at activation versus per-step instants), WS04-T10 (`pending_until_ms` on every record) and WS09-T03 (a RESP fixture VIOLATED before the deadline) carry a note and stay `blocked` until this ADR and the severity questions OP-14 and OP-15 (WS01-T06, WS01-T07) are decided. No signature of `02-interfaces.md` changes in this ADR.
- **Status.** proposed [DA-CONFERMARE].

## ADR-030 Conformal quantiles: lower quantile for the "possible" variant and exact rank rule [DA-CONFERMARE]

- **Context.** WS01-T06 (`docs/formal/06-rho-proposition1.md`, open points CP4 and section 10) found two tensions with the contract `#conformal-calibrator` and `#verdict`. (1) Contract rule 2 of `#verdict` and analisi §4.4 write the "possible" variant with the symmetric form `sigma_hat - q_{1-alpha} < 0`, which is valid only if the score law is symmetric (sufficient, not necessary); the bound that holds for any exchangeable score law is Proposition 1b with the lower quantile `q^lo_alpha`, `P(sigma_tilde < 0 and sigma_hat + q^lo_alpha >= 0) <= alpha`. (2) The quantile ranks `k = ceil((n+1)(1-alpha))` (upper) and `floor((n+1) alpha)` (lower) are wrong in floating point: the product `(n+1)*(1-alpha)` gives 577 wrong upper and 49 wrong lower ranks over 98,901 pairs (n from 1 to 999, alpha from 0.01 to 0.99), exact arithmetic on the binary value of the float alpha is wrong in 1,280 pairs each way, and the integer rule on the decimal literal (`Fraction(repr(alpha))`) is wrong in none. A level computed in floats (for example the Bonferroni allocation `alpha_total / n_tests`) can still have a 16 to 17 digit repr and a wrong rank (358 of 231,884 pairs, always conservative); it must be computed as `Fraction(repr(alpha_total)) / n_tests` and passed as a fraction.
- **Decision.** Proposed: adopt Proposition 1b (lower quantile `q^lo_alpha`) as the definition of the "possible" variant, with a `quantile_lower` method (or the existing `quantile` on episodes with `sigma_hat` and `sigma_true` swapped); take alpha as the decimal literal and compute ranks with integer or `Fraction` arithmetic; pass allocated levels as fractions. The "likely" variant and its guarantee string are unchanged.
- **Alternatives.** Keep the symmetric form and state symmetry as a hypothesis of the guarantee string (valid only under symmetry; the document shows a 41-of-152 exact-cell failure for an asymmetric law); round the product with `ceil(round(x, 9))` (0 wrong ranks on the two-decimal grid, untested on allocated levels).
- **Consequences.** WS05-T06 (test 2 float-boundary remark: `10 * (1 - 0.3)` is exactly 7.0 and the boundary level is 0.7, so `quantile(0.7)` on its fixture is 0.0; step 3 rounding; test 8 symmetric reading, `sigma_hat = 0.3` is not emitted by the lower-quantile form) and WS05-T08 (test 7) carry a note and stay `blocked`; WS01-T08 records the contract amendment at the freeze. No signature of `02-interfaces.md` changes in this ADR beyond the added method.
- **Status.** proposed [DA-CONFERMARE].

## ADR-031 Containerised development environment [DA-CONFERMARE]

- **Context.** The human asked on 2026-10-04 to dockerise the environment and allowed installing what is needed. Until then every task ran on the host (Python 3.14.4 in a `.venv`, ruff 0.16.9, mypy 2.3.1) with no pinned versions (ADR-016); ROS 2 and Gazebo, needed by WS07 and WS10, are not installed on the host and the agents have no sudo.
- **Decision.** Proposed: `docker/Dockerfile.dev` (Python 3.12, the dependencies of `pyproject.toml`, `types-PyYAML`), `docker/Dockerfile.ros2` (ROS 2 Jazzy base, `ros_gz_sim`, `ros_gz_bridge`, CycloneDDS; no TIAGo packages) and `docker-compose.yml` with the services `dev`, `test`, `lint`, `plan`, `bib` and the profile `ros2`. The repository is mounted at `/work` and the containers run as the host user. The suite, `ruff`, `mypy`, `tools/check_plan.py` and `tools/check_bib.py` give the same results in the container as on the host (175 tests). `pyproject.toml` and the contracts do not change; versions stay unpinned and the resolved ones are recorded in `docker/README.md`.
- **Alternatives.** Keep the host `.venv` only (no ROS 2 without sudo); a devcontainer (ties the setup to an editor); pin every dependency now (ADR-016 defers pins).
- **Consequences.** ADR-011 (ROS 2 distribution and Gazebo generation) stays `[DA-CONFERMARE]`: the image follows the default of `CLAUDE.md` (Jazzy and Harmonic) and must be rebuilt if ADR-011 is superseded. WS07-T01 still needs the record of WS00-T05 (TIAGo availability and package versions) and keeps its blocking note; the image only removes the missing-ROS part of that block. LaTeX is not in the image (the excerpts of the WS01 documents were compiled on the host).
- **Status.** proposed [DA-CONFERMARE].

## ADR-032 EvidenceVector: a dispenser evidence group (content change and dispense interval) [DA-CONFERMARE]

- **Context.** `docs/models/evidence-channels.md` (WS02-T03, gap EC-GAP-1, task gap G-1) and `docs/models/fault-model.md` (FM-GAP-DISP) found that no field of `02-interfaces.md#evidencevector` carries the interval between dispenser openings or a change of dispenser content, although rows 6 (patient double take) and 7 (dispenser sensor bounce) of the diagnosability matrix of analisi §4.5 and the confounder `double_take_vs_bounce` of §5.1 depend on them. ADR-021 lists the same gap; it is decided at M1. WS10-T03 builds a dispenser that reports both facts and WS04-T06 plans an optional `content_change` payload key.
- **Decision.** Proposed: add a group `dispenser: DispenserEvidence` to `EvidenceVector`, with `interval_since_previous_ms: int | None` (interval since the previous opening of the dispenser) and `content_change: float | None` (content after minus before, in the unit the dispenser declares), both `None` when the dispenser reports no interval or has no content sensing, never a negative reading. The values come from the `DISPENSE` payload keys `interval_since_previous_ms` and `content_change`; the channel identifier is `CH-DISP`; the registry name `dispense_bounce_interval_ms` is the threshold under which two openings are a bounce (the analisi nominal "below one second" is illustrative, unverified). Old version: `#evidencevector` 0.1.0 (twenty fields in six groups). New version: 0.2.0, bumped once at M1 together with ADR-033 and ADR-034, with the group appended last and a default of `None` for both fields so that existing constructors keep working. Affected tasks: WS02-T04, WS02-T05, WS04-T05, WS04-T07, WS05-T07, WS07-T03, WS10-T03. Migration (`01-conventions.md` section 6): the A4 mask lists the two fields as unchanged; WS05-T07 test 1 counts twenty-two fields; WS04 payload keys move from provisional to the conventions table of `evidence-channels.md`; no consumer is changed before the ADR is accepted.
- **Alternatives.** Extend `CrossDeviceEvidence` with the two fields (rejected: they come from one device, not a comparison of two); keep the gap as a declared limit (rows 6 and 7 then read not distinguishable without content sensing, which the analisi says is distinguishable).
- **Consequences.** Until the ADR is accepted, WS05-T07 does not implement the group and WS02-T05 writes the two rows with the proposed evidence in slash notation; the rows 6 and 7 stay conditional on `CH-DISP`. No signature of `02-interfaces.md` changes in this entry; amendments are decided at M1 (ADR-021) and the entry does not touch ADR-026 to ADR-031.
- **Status.** proposed [DA-CONFERMARE].

## ADR-033 EvidenceVector: key of the evidence mapping, scope of the scalar system fields, meaning of `battery_low` and `robot_present` [DA-CONFERMARE]

- **Context.** `docs/models/evidence-channels.md` (EC-GAP-2, EC-GAP-7, decisions D-1, D-2, D-10) found that `02-interfaces.md#attribution` and `#detector` use `Mapping[str, EvidenceVector]` without saying what the key is; that `system.liveliness_ok`, `system.qos_deadline_missed`, `system.diagnostics_ok` and `system.battery_low` are scalars that do not say which node they refer to (FM-GAP-LIVE); and that `witness.robot_present` is named as if it meant the robot is present while the contract comment makes it `None` when the robot is not co-located (so it can only be the patient presence the robot observed). ADR-021 lists the key as a gap; it is decided at M1.
- **Decision.** Proposed, as a statement of meaning with no signature change: (1) the key of the mapping is `VerdictRecord.instance_key` of the violated record, the mapping is per care plan (`TemplateInstance.instance_key` is unique within a care plan only), and a caller with several plans builds one mapping per plan or prefixes the key with `<care_plan_id>/`; (2) a scalar `system` field aggregates over the scope of the instance (table in `evidence-channels.md`: per template, the BLE device roles and the robot node where the template creates a robot obligation, reads a visit measurement, or (`int`) reads the robot's witness channels `presence` and `intake`), is asserted when one component asserts, denied only when every capable component is denied, and `None` otherwise; (3) `system.battery_low` is the state of the robot battery; (4) `witness.robot_present` is the presence of the patient as observed by the robot (`SignalId.PRESENCE`), the name being kept. Old version: `#evidencevector` 0.1.0. New version: 0.1.1 if adopted alone (text only), or part of 0.2.0 with ADR-032 and ADR-034. Affected tasks: WS02-T04, WS05-T07, WS05-T09, WS08-T04. Migration: WS05-T07 builds the mapping by `instance_key` and takes the scope table as extractor configuration; no data changes.
- **Alternatives.** Per-node mappings for the four scalar fields (`Mapping[str, bool | None]`): more expressive, and the robot entry of each mapping could then be removed after the fact, but that is the removal of a key and not a pure path mask (a path addresses a field, not an entry of a mapping); it changes four types and is a version bump with a migration of every consumer; a tuple key `(care_plan_id, instance_key)`: not a `str` as the contract types it; a global reading over every node: lets a fault on an unrelated node turn a clinical violation into C2.
- **Consequences.** A device battery fault has no field and is read as a `ble_dropout` or `process_kill` of the device (declared limit); a deployment in which the cuff measures on its own schedule edits the scope table (hypothesis H-VISIT). The per-node alternative can be taken at M1 without changing the scope table. No signature of `02-interfaces.md` changes in this entry (ADR-021, amendments decided at M1; ADR-026 to ADR-031 are not touched).
- **Status.** proposed [DA-CONFERMARE].

## ADR-034 EvidenceVector: split of `crypto_temporal.seq_gap_or_replay` [DA-CONFERMARE]

- **Context.** `docs/models/evidence-channels.md` (EC-GAP-3, decision D-3), `docs/models/fault-model.md` (FM-GAP-SEQ) and `docs/models/threat-model.md` (TM-GAP-SEQ) found that the one Boolean `crypto_temporal.seq_gap_or_replay` is True for a message loss (a C2 symptom of `ble_dropout` and `message_drop`) and for a replay (a C3 symptom). Under ADR-010 integrity evidence is read first, so a link loss can become C3. Interim, with no contract change: the field is True for a repeat or a gap and `system.ble_link_quality` (the delivery ratio over the distinct sequence values) is 1.0 exactly when no value is missing, so a True field with a ratio of 1.0 is a repeat without a gap; a True field with a lower ratio contains a gap and does not exclude a repeat (a replay together with a loss is not told from a loss).
- **Decision.** Proposed: replace the field by two, `crypto_temporal/seq_repeat` (a received `(name, seq)` repeats an accepted one: integrity evidence) and `system/seq_gap` (a sequence value is missing at the cut-off: system evidence), written in slash notation because neither name exists in the contract, each `bool | None` with the `None` conditions of the single field today. Old version: `#evidencevector` 0.1.0. New version: 0.2.0 (shared with ADR-032 and ADR-033). Affected tasks: WS02-T04, WS02-T05, WS04-T07, WS04-T08, WS05-T07, WS07-T05. Migration: the A4 mask lists both as unchanged; WS04-T07 `EVIDENCE_SIGNATURES` and WS07-T05 `EXPECTED_EVIDENCE` rename the path in the rows of `ble_dropout`, `message_drop`, `replay` and `dispense_forgery`; WS02-T04 drops the explained-away rule for the sequence gap (the case W-15 becomes a reading of `system/seq_gap`).
- **Alternatives.** Keep the Boolean with the interim reading (no change, the replay with a loss stays ambiguous); set the field only for a repeat and report a gap through the delivery ratio and the deadline only (hides losses shorter than a declared deadline); add one field (`seq_repeat`) and keep the old one as the gap (a rename with less migration but a field name that still says "or replay").
- **Consequences.** The pair of fields closes the false-C3 hazard of a pure loss. Until the ADR is accepted, WS05-T07 implements the single field with the rule of D-3. No signature of `02-interfaces.md` changes in this entry; amendments are decided at M1 (ADR-021); ADR-026 to ADR-031 are not touched.
- **Status.** proposed [DA-CONFERMARE].

## ADR-035 Trace schema: evidence conventions for `Event.payload`, the gateway verification outcome, `auth` Samples and the availability of the robot channels [DA-CONFERMARE]

- **Context.** `02-interfaces.md#trace-schema` leaves `Event.payload` open and has no member for a per-message verification outcome (`docs/models/threat-model.md` TM-GAP-AUTH, `docs/models/evidence-channels.md` EC-GAP-4); WS04-T06, WS04-T07, WS04-T08, WS07-T03 and WS07-T04 each declare payload keys provisionally. The meaning of `SignalId.AUTH` against the verification outcome is not stated, so a keyless injector can write an `auth` Sample in a deployment without verification and INT reads it as a witness (first MINOR of the WS02-T02 review, EC-GAP-9). The availability of the robot channels `presence` and `intake` is a mask in the monitor (T01 section 2.5, CG-6) but is not carried by an `ObservedDay` (EC-GAP-10).
- **Decision.** Proposed: (1) the table "Trace evidence conventions" of `docs/models/evidence-channels.md` is binding for the payload keys of `NODE_STATE` (`state`, `commanded`, `diagnostics`, `battery_low`, `deadline_missed`, `colocated`), `ROBOT_TASK` (`task`, `outcome`, `patient_id`, `obligation_id`, `identity_confirmed`), `DEVICE_ERROR` (`error_code`, `verification`, `subject`) and `DISPENSE` (`interval_since_previous_ms`, `content_change`, with ADR-032); (2) the gateway verification failure is an `Event` of the new kind `EventKind/VERIFICATION` with `source` the gateway and the payload keys `verification` (the value `failed`) and `subject`; until the member exists the same keys travel on a `DEVICE_ERROR` event whose source is the gateway; (3) the gateway does not deliver as an `auth` Sample a message that failed verification, and a source that cannot verify does not emit `auth` (alternative reading to be confirmed: `auth` is a user-authentication token of the dispenser and needs its own verification outcome); (4) the availability of the robot channels is derived from the robot `NODE_STATE` events (`state`, `colocated`), with the run starting not co-located; no field is added to `ObservedDay`. Old version: `#trace-schema` 0.1.0. New version: 0.2.0 if the enum member is accepted, otherwise 0.1.1 (text only). Affected tasks: WS04-T01, WS04-T06, WS04-T07, WS04-T08, WS05-T02, WS05-T09, WS07-T03, WS07-T04, WS08-T04. Migration: `vocab.py` of WS04 takes its keys from the table; `EventKind` gains the member `VERIFICATION` and the trace reader accepts it; WS07 nodes publish the robot status as `NODE_STATE` events.
- **Alternatives.** Leave the keys to each producer (rejected: the extractor needs one set); put the verification flag on every `Sample` and `Event` (a field on two dataclasses and a migration of every trace); carry the availability mask as intervals in `ObservedDay` (a new field and a new reader rule, with the golden cases already giving it as an input).
- **Consequences.** The derivation of `crypto_temporal.authenticated` rests on the gateway logging every failure (the policy "flag" of TM H-GW). Until the ADR is accepted, WS04-T08 and WS07-T03 use the interim keys and mark them provisional. No signature of `02-interfaces.md` changes in this entry until it is accepted; amendments are decided at M1 (ADR-021); ADR-026 to ADR-031 are not touched (the INT form is not affected, and the verdict marker of ADR-029 reads the same availability mask).
- **Status.** proposed [DA-CONFERMARE].

## ADR-036 Device capability profile [DA-CONFERMARE]

- **Context.** `docs/models/evidence-channels.md` (EC-GAP-8, decision D-8) derives a field as `None` when the capability it needs is not declared: the device authenticates, provides `seq`, reports a signal quality, error codes or diagnostics, declares a deadline, has independent clocks, and (robot) reports task outcomes, battery, perception and identity check. No contract object carries these capabilities, and inferring them from the trace would turn an absence into a negative reading.
- **Decision.** Proposed: a device profile is a run-level mapping from a source identifier to its role and capabilities (the names of the section Device capabilities used of `evidence-channels.md`, plus the run parameters `liveliness_lease_ms` and `qos_deadline_ms`, the latter null for an event-driven device). For the benchmark it is stored in the `settings` of `manifest.json` (ADR-025: extra run information goes into `settings`); for the ROS 2 simulation it is a parameter file of WS07-T03; `EvidenceExtractor` receives it as a constructor argument. No contract type changes. Old version: none (a convention, not a contract). New version: none. Affected tasks: WS04-T11, WS05-T07, WS07-T03, WS07-T04, WS10-T02. Migration: the benchmark builder writes the profile; the extractor refuses a source with no profile entry instead of assuming a capability.
- **Alternatives.** Infer capabilities from the observed trace (an absence read as "the device does not report", a negative); assume every capability (false for the benchmark devices); add the profile to `CarePlan` (it is not a plan property).
- **Consequences.** The benchmark manifest gains a profile section inside `settings`, with no new top-level key. No signature of `02-interfaces.md` changes in this entry; amendments are decided at M1 (ADR-021); ADR-026 to ADR-031 are not touched.
- **Status.** proposed [DA-CONFERMARE].

## ADR-037 Paper writing is out of the agent's scope
- **Context.** On 2026-10-05 the human instructed: the agent must not write anything of the paper and must concentrate on development. The plan had assigned to the agent the writing of the paper (WS12: title and abstract, skeleton, introduction, methods, experiments, discussion, review, final compile) and the generation of figures and tables for it (WS09). The formalization tasks of WS01 and WS02 also asked for "paper excerpt" sections, and WS03 produced a Related Work draft before this decision.
- **Decision.** The writing of the paper is the human's. WS12-T01 to WS12-T08 become `owner: human` (task files and `workstreams/INDEX.md`); the agent loop never takes them and `CLAUDE.md` says so. In the tasks that remain, a required "Paper excerpt" section keeps its heading and carries one line, "Not written: paper text is outside the agent's scope (ADR-037)", so that the structural checks of the task still hold; the technical content of the task is unchanged. Documents already merged are not rewritten (WS01-T01 to WS01-T06 excerpts, the WS03 related-work notes and draft stay as inputs for the human). The agent still produces technical artefacts that the paper will use (formal documents, golden files, code, experiment outputs, the open-source release WS13).
- **Not decided here.** WS09 (figures and tables of the paper): the scripts that generate them from experiment outputs are code, the figures and LaTeX tables are paper artefacts, and WS13-T02 (reproduction scripts) depends on WS09. To be settled when WS08 produces results.
- **Alternatives.** Keep WS12 on the agent with human review (rejected by the instruction); cut WS12 from the plan (rejected: the paper is the deliverable, only its author changes).
- **Consequences.** Milestone M5 (submission) is now a human milestone for its paper part; the effort of WS12 (13 person-days) moves from the agent to the human; the 25 related-work keys remain unverified until the human completes WS03-T06 (human). No contract and no signature change.
- **Status.** accepted (explicit user instruction, 2026-10-05).
