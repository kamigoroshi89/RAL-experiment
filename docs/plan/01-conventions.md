# 01 Conventions

Binding for every agent. Sources: analisi §8.1 (glossary), §5 (evaluation), §4 (technical design), §9 (roadmap). Choices not fixed by the sources are recorded as ADRs in `03-decisions.md` (tag `[DA-CONFERMARE]`).

## 1. Repository layout

```
RAL experiment/
├── CLAUDE.md
├── pyproject.toml                 (WS05-T01)
├── src/ralmon/                    core library, ROS-independent (WS05-T01 creates it)
│   ├── signals/                   signal abstraction, derived signals (bp_pre, c_d)
│   ├── spec/                      past-time STL templates, normalised robustness, priorities
│   ├── monitor/                   robustness intervals, three-valued verdicts, alert generation
│   ├── conformal/                 split and adaptive conformal calibration, rho
│   ├── attribution/               hierarchical rules with UNDETERMINED
│   ├── benchmark/                 PriorSource, latent patient, PK/PD, measurement process, injection, ground truth
│   ├── baselines/                 B1-B5
│   └── eval/                      metrics of analisi §5.5
├── tests/                         mirrors src/ralmon (tests/spec/test_*.py ...)
├── ros2/                          thin ROS 2 packages (wrappers only, no logic): ralmon_ros, ralmon_sim
├── experiments/                   configs and run scripts for WS08 (one YAML per experiment)
├── hardware/                      lab demo material (WS10)
├── study/                         vignette study material (WS11)
├── paper/                         LaTeX sources (WS12)
├── data/raw/                      never committed (gitignored)
├── outputs/                       never committed (gitignored)
├── tools/                         repo tooling (tools/check_plan.py)
└── docs/                          source/, superpowers/specs/, plan/
```

Rules:

- `src/ralmon` never imports ROS 2 (`rclpy`, `rclcpp`). ROS 2 packages under `ros2/` import `ralmon` and contain no monitoring logic. This keeps the core testable with plain `pytest`.
- Package dependency direction: `signals` ← `spec` ← `monitor` ← `attribution`; `conformal` used by `monitor`; `benchmark` depends only on `signals` and the trace schema; `baselines` and `eval` depend on the public API of the others. No cycles. Consumers import only from a package's `__init__` (its public API as defined in `02-interfaces.md`).
- Docs and code comments in English. Identifiers in English.

## 2. Python style

- Python 3.11 or newer (ADR-016). Type hints on all public functions; `mypy --strict` clean on `src/ralmon`.
- Formatting and lint: `ruff format` and `ruff check` with the default rule set plus `I` (isort) and `B` (bugbear).
- Data containers: `@dataclass(frozen=True, slots=True)` or `typing.Protocol` for interfaces, as shown in `02-interfaces.md`. No mutable module-level state.
- Time: all timestamps are integer milliseconds since the start of the patient-day trace unless a contract says otherwise (ADR-017). Durations are integer milliseconds. Never mix minutes and milliseconds in one API; conversion helpers live in `ralmon.signals`.
- Randomness: always via `numpy.random.Generator` created from an explicit integer seed passed as an argument. No global `np.random.seed`, no unseeded generators.
- Monitoring library: RTAMT is the reference STL tool (analisi §3.1, §9 item 5 "RTAMT o custom"). Wrap it behind `ralmon.spec`/`ralmon.monitor` so that a custom implementation can replace it. See ADR-013.
- Errors: raise specific exceptions defined per package; never swallow exceptions in the monitor path.

## 3. Testing (TDD)

- Every code task fills its "Test" section before its "Passi" section. The executing agent writes the failing tests first, then the implementation (`superpowers:test-driven-development`).
- `pytest` only; tests live under `tests/` mirroring the package tree; test names are those listed in the task.
- Deterministic by construction: fixed seeds (default seed 0 in fixtures, explicit seeds listed in experiment configs), no wall-clock, no network, no reliance on dict ordering of external data.
- Fixtures: small hand-written traces under `tests/fixtures/` (each a few dozen samples) with expected verdicts written by hand from the formulas of `02-interfaces.md`. Golden files are regenerated only through a documented script and reviewed in the diff.
- Property tests (Hypothesis, ADR-016) for monotonicity of normalised robustness, causality of the past-time monitor, and conformal coverage on synthetic exchangeable data.
- A task is done only when its "Done when" command exits 0 and the output is shown in the task's completion note.
- Experiments (WS08) are also tests of reproducibility: the same config and seed must reproduce the same table bit for bit on the same machine.

## 4. Git workflow

- One branch per task, named after the task id in lower case: `ws05-t01-scaffolding`. Branch from `main`.
- Commit message convention: `<TASK-ID>: <imperative summary>`; examples: `WS05-T01: scaffold ralmon package`, `WS01-T03: add normalised robustness definition`. Bootstrap commits use `plan(Fx): <summary>`.
- Small commits inside the branch; the last commit of a task updates the task's `status` to `done` and adds a note to `docs/plan/PROGRESS.md` when the task closes a milestone.
- Merge to `main` locally after "Done when" passes. No history rewriting on `main`.
- Never modify `docs/source/`. Never edit a contract in `02-interfaces.md` without an ADR (see section 6).
- Only local git operations are allowed in the bootstrap run. Remote operations are governed later by WS13.

## 5. Task lifecycle and frontmatter

Task file location: `docs/plan/workstreams/WSxx-<slug>/tasks/Txx-<slug>.md`. Frontmatter keys are fixed:

`id`, `title`, `workstream`, `owner` (`agent` or `human`), `status` (`ready`, `blocked`, `in_progress`, `done`), `depends_on` (list of task ids), `critical_path` (bool), `non_negotiable` (bool), `estimate_pd` (person-days), `sources` (list of analisi references), `interfaces` (list of `02-interfaces.md#anchor`), `review_items` (list of finding ids from `04-review-traceability.md`).

Status rules: `ready` only if all `depends_on` are `done`; otherwise `blocked`. An agent sets `in_progress` when it starts and `done` when "Done when" passes.

## 6. Contract changes

A contract in `02-interfaces.md` changes only through an ADR in `03-decisions.md` that states the old version, the new version, the affected tasks and the migration. The contract's version number is bumped in the same commit. Consumers list their contract dependencies in `interfaces` so the affected tasks can be found by grep.

## 7. Binding glossary (analisi §8.1)

Use exactly these terms in code, docs and paper text.

| Use | Do not use | Note |
|---|---|---|
| **tier** for architectural levels (sensing, robot, back-end) | subsystem | |
| **module** for components of the Runtime Safety Monitor (RSM) | subsystem, stage | |
| **node** for ROS 2 processes | | |
| **back-end (off the safety-critical path)** or **ward server** | edge cloud, cloud subsystem, "edge" without qualification | Define **on-path** vs **off-path** once, then reuse |
| **forecaster** | multivariate time-series learner, temporal prediction subsystem, Time-Series Learner | |
| **conformal calibrator** | calibrated uncertainty subsystem, uncertainty subsystem, conformal subsystem, Conformal Uncertainty | |
| **pathway template**, instantiated into a **patient care plan** | "Clinical Pathway" for one patient's prescription | A Clinical Pathway is institutional and population-level |
| **Physical AI** only in the title and framing; elsewhere **assistive robot** and **monitoring architecture** | embodied medical AI, embodied AI, clinical robotic architecture | |
| **robustness** reserved to STL semantics | "robust" for noise tolerance | Use "noise tolerance" for the latter |
| **DISPENSE** (dispenser opening) and **INTAKE** (verified by the robot) | PILL, "dispenser open", "intake" interchangeably | Opening does not prove intake |
| **alert** for the output; **violation** for a violated sub-formula; **attributed cause** for κ | "violation" for C2 and C3 | A device fault is not a violation of the care plan |
| **smart medical devices** | smart-medical devices | Spelling |

Additional binding vocabulary from the analysis:

- Alert tuple: ⟨τ, κ, σ̃, ρ, ξ⟩ where σ̃ is the clinically normalised robustness (analisi §4.2). "σ" without tilde means raw robustness.
- Classes: C1 clinical deviation, C2 system or embodiment failure, C3 integrity violation (reduced from "adversarial tampering", analisi §3.6, §9 item 0.2), plus **UNDETERMINED** (analisi §4.5).
- Verdict states: **PENDING**, **PREDICTED-VIOLATION**, **VIOLATED**, **SATISFIED** (analisi §4.7).
- Specification decomposition: φ = φ_CP ∧ φ_SYS ∧ φ_INT (analisi §4.1); "φ_CP" only for care-plan constraints.
- Claims wording: use the reformulations of analisi §4.8 ("specification-level traceability", "complementary", "cause-based taxonomy"). Do not write "ensures", "intrinsic explainability", "orthogonal axes", "distribution-free coverage" without the qualifiers listed there.
- Ground-truth vocabulary: **latent trace** (noise-free, fault-free, attack-free) versus **observed trace** (what the monitor sees) (analisi §5.1).
- Alert-class names in metrics: report per class C1, C2, C3, and abstention rate.

## 8. Numerics and units

- Robustness is reported in native units only inside `spec` internals. Everything outside `spec` uses normalised robustness σ̃ ∈ [-1, 1] with per-template scale s_π (analisi §4.2). The scale table is a contract (see `02-interfaces.md#template`).
- Clinical parameter values (bands, Δ1, Δ2, δ, scales, priorities) come only from the parameter registry defined in WS01 and reviewed by the clinician. Agents must not hard-code numeric clinical values elsewhere; the examples in analisi §4.1 are illustrative and are marked as such.

## 9. Documentation of results

Each experiment run writes to `outputs/<experiment-id>/<seed>/` a `config.yaml` copy, a `metrics.json` and a `git_rev.txt`. Tables and figures are regenerated from these files only (WS09). Numbers in the paper come from `outputs/` through scripts, never typed by hand.
