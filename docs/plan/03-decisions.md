# 03 Decisions (ADR log)

Format per entry: context, decision, alternatives, consequences, status. Status values: `accepted` (from the sources or from an explicit user answer), `proposed` (chosen autonomously; tag `[DA-CONFERMARE]` means a human must confirm or overturn it). A contract in `02-interfaces.md` changes only through an ADR added here.

Index: ADR-001 scope; 002 C3 as integrity; 003 distributed architecture; 004 DISPENSE vs INTAKE; 005 PriorSource; 006 multi-file plan layout; 007 past-time formulation; 008 three-valued verdicts; 009 normalisation; 010 attribution rule; 011 ROS 2 distribution; 012 source files; 013 RTAMT; 014 workstream placement of §9 items; 015 run location of the loop script; 016 Python toolchain; 017 time unit; 018 reference verification; 019 optional second pathology; 020 unverified clinical parameters; 021 contract-gap register; 022 layout and package-dependency amendments; 023 dependency reconciliation and extra WS00 tasks.

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
- **Decision.** RTAMT is the reference implementation wrapped behind `ralmon.spec` and `ralmon.monitor`; a custom monitor may replace it if RTAMT cannot express robustness intervals or sparse sampling. WS05-T02 decides after a spike and updates this ADR. Installation of packages is not part of the bootstrap run.
- **Alternatives.** Custom monitor from the start; Breach or S-TaLiRo (MATLAB dependence).
- **Consequences.** The spike result is recorded in WS05.
- **Status.** proposed [DA-CONFERMARE].

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
