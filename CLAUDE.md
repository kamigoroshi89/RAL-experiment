# CLAUDE.md: RAL experiment

Entry point for every Claude Code agent working in this repository. Read this file first, then only the documents your task links.

## Project

We are extending the IJCAI-ECAI 2026 workshop paper "Clinical Pathways as Safety Specifications for Physical AI in Hospital Wards" (Franchini, Mallardi, De Carolis, Lanubile; University of Bari) into a full **IEEE RA-L** submission (6 pages). The workshop paper is a position paper; the extension builds the technical content:

- a complete formal specification: past-time Signal Temporal Logic templates derived from care plans, clinically normalised robustness, three-valued online monitoring, conformal calibration (rho, Proposition 1);
- a fault model, threat model and diagnosability matrix, and an attribution layer with abstention;
- a semi-synthetic benchmark with latent ground truth, baselines B1-B5, ablations A1-A7;
- a ROS 2 implementation evaluated in simulation, plus a lab demo on a TIAGo-class robot;
- an open-source release.

Validation is **technical and pre-clinical**: no real patients. Never write claims that imply clinical validation.

## Where things are

| What | Path |
|---|---|
| Sources of truth (read-only) | `docs/source/analisi.md` (analysis, roadmap §9), `docs/source/review.md` (reviewer findings) |
| Original workshop paper | `Clinical_Pathways_Physical_AI_IJCAI-ECAI_2026.pdf` |
| Design spec of this plan | `docs/superpowers/specs/2026-09-29-ral-dev-plan-design.md` |
| Master plan (goal, milestones, critical path, effort, what not to cut) | `docs/plan/00-master-plan.md` |
| Conventions (layout, style, testing, git, **glossary**) | `docs/plan/01-conventions.md` |
| Interface contracts (Python signatures) | `docs/plan/02-interfaces.md` |
| Decisions (ADR log; entries tagged `[DA-CONFERMARE]` await human confirmation) | `docs/plan/03-decisions.md` |
| Reviewer finding to task map | `docs/plan/04-review-traceability.md` |
| Workstreams and tasks | `docs/plan/workstreams/WSxx-<slug>/README.md` and `tasks/Txx-<slug>.md` |
| Task index (binding skeleton) | `docs/plan/workstreams/INDEX.md` |
| Plan verifier | `python3 tools/check_plan.py` |
| Core library (created by WS05-T01) | `src/ralmon/` |

Workstreams: WS00 admin (humans), WS01 formalization, WS02 threat-fault-model, WS03 related-work, WS04 benchmark, WS05 monitor, WS06 baselines, WS07 ros2-sim, WS08 experiments, WS09 figures, WS10 lab-demo, WS11 vignettes, WS12 paper, WS13 release.

## Glossary (short; full binding table in `docs/plan/01-conventions.md` section 7)

- **tier** (architecture level), **module** (component of the Runtime Safety Monitor, RSM), **node** (ROS 2 process).
- **forecaster**, **conformal calibrator**, **back-end (off the safety-critical path)**.
- **pathway template** instantiated into a **patient care plan** (never "Clinical Pathway" for one patient's prescription).
- **DISPENSE** (dispenser opened) is not **INTAKE** (verified by the robot).
- **alert** = output tuple ⟨τ, κ, σ̃, ρ, ξ⟩; **violation** = violated sub-formula; **attributed cause** = κ ∈ C1, C2, C3, UNDETERMINED. C3 means *integrity violation*.
- **robustness** is reserved for STL semantics. σ̃ is normalised robustness.
- Verdict states: PENDING, PREDICTED-VIOLATION, VIOLATED, SATISFIED.
- **latent trace** (noise-free, used only for ground truth) versus **observed trace** (what monitors see).

## How to choose a task

1. List candidates: `grep -lE '^status: ready' docs/plan/workstreams/*/tasks/*.md`, keep those with `owner: agent`.
2. Prefer tasks with `critical_path: true`; then those with `non_negotiable: true`; then the smallest `estimate_pd`.
3. Confirm every id in `depends_on` has `status: done` (the verifier enforces that `ready` implies this).
4. Do not take `owner: human` tasks. If your work needs a human output, check the artefact named in that task's "Done when" (under `docs/plan/workstreams/WS00-admin/outputs/` and similar); if it is missing, stop and record a blocking note in the task file instead of guessing.
5. Set `status: in_progress`, create branch `<task-id-lowercase>-<slug>` (for example `ws05-t01-scaffolding`), and read only the task file and its linked contracts.

## Working rules

- **TDD.** Write the tests listed in the task's "Test" section first, watch them fail, then implement. Use `superpowers:test-driven-development`. Fixed seeds, no wall-clock, no network in tests.
- **Contracts are frozen.** Do not change a signature in `02-interfaces.md` or the meaning of a field without an ADR in `03-decisions.md`; bump the contract version in the same commit and update the tasks that cite it.
- **No invented numbers.** Clinical parameters, PK/PD values, thresholds and citations come from the parameter registry, `PriorSource` provenance and the verified bibliography. Values from analisi §4.1 are illustrative and unverified. Unverified references (bib flag) cannot be cited.
- **Ground truth discipline.** Monitors and baselines never read `LatentDay` or `GroundTruthEvent` at inference.
- **Honest reporting.** Report undetectable cases (diagnosability matrix), where forecasting fails, and where B5 fails. Use the claim wording of analisi §4.8; avoid "ensures", "intrinsic explainability", "orthogonal", "distribution-free coverage" without qualification.
- **Do not cut:** WS01 (formalization), B5 (Lindemann et al. 2023 baseline) and ablation A4 (embodied channel). See `00-master-plan.md` sections 5 and 7.
- **Data.** Never commit `data/raw/` or `outputs/`. PhysioNet data is under a data use agreement: no redistribution.
- **Git.** One task per branch, commit messages `<TASK-ID>: <summary>`, merge locally after "Done when" passes. Never push or add remotes without explicit human approval (WS13 governs publishing).
- **Done means verified.** Run the "Done when" commands, read their output, then (`superpowers:verification-before-completion`) set `status: done` in the task file, set newly unblocked dependents from `blocked` to `ready`, add a note to `docs/plan/PROGRESS.md` if a milestone (M0-M5) closes, and run `python3 tools/check_plan.py`.
- **Task too big or wrong?** Do not silently change scope. Record the problem in the task file under a "Notes" heading and, if a decision is needed, add a proposed ADR to `03-decisions.md`.
- Docs and code in English. Talk to the user in the language they use.

## Commands

- Plan consistency: `python3 tools/check_plan.py` (standard library only; must exit 0 before any commit that touches `docs/plan/`).
- After WS05-T01: `pytest -q`, `ruff check src tests`, `ruff format --check src tests`, `mypy src/ralmon`.
- ROS 2 (from WS07): Jazzy and Gazebo Harmonic unless ADR-011 is superseded.

## Milestones (details in the master plan)

M0 commitment letter · M1 formalization frozen · M2 core running offline · M3 baselines and main results · M4 robot evidence · M5 submission.

## Status

Bootstrap of the plan is tracked in `docs/plan/PROGRESS.md`. Completion of the bootstrap is signalled by `docs/plan/.PLAN_COMPLETE`. After that, task status in the task files is the source of truth for project progress.
