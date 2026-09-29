# RAL experiment: development plan design

Date: 2026-09-29. Status: approved (option A, see PROMPT.md "Design approvato").

## 1. Purpose

Turn the workshop paper "Clinical Pathways as Safety Specifications for Physical AI in Hospital Wards" (IJCAI-ECAI 2026 workshop, Franchini, Mallardi, De Carolis, Lanubile) into a full IEEE RA-L submission (6 pages), following the analysis in `docs/source/analisi.md`. The analysis concludes that the workshop paper is a position paper, and that the extension must build almost all technical content: a formal specification, a three-valued online monitor with conformal calibration, an attribution layer, a semi-synthetic benchmark, baselines B1-B5, ROS 2 simulation and (recommended) a mock-ward demo.

This document defines how that work is organised so that several Claude Code agents can execute it in parallel without diverging. It does not contain code. Code scaffolding is task `WS05-T01`, executed later by an agent.

## 2. Sources of truth

| Source | Path | Use |
|---|---|---|
| Analysis (roadmap §9, terminology §8.1, metrics §5, contributions §6, paper layout §7) | `docs/source/analisi.md` | Everything numeric or structural in the plan derives from here |
| Reviewer findings (R1, R2, R3, AE meta-review) | `docs/source/review.md` (verbatim extract of analisi §2) | Traceability target (`04-review-traceability.md`) |
| Workshop paper | `Clinical_Pathways_Physical_AI_IJCAI-ECAI_2026.pdf` (repo root) | Baseline text to be rewritten |

Precedence: sources > PROMPT.md > agent inference. Nothing in the plan may invent PK/PD parameters, numbers, sections, findings or workstreams. Where a value is unknown, the plan says which task must establish it from which source.

## 3. Approach and rationale

Three organisations were considered.

- **A. Workstreams with shared interface contracts (chosen).** Each roadmap §9 item becomes a workstream folder with a README and small tasks. Interfaces between modules (trace schema, STL templates, alert tuple, evidence vector, prior source) are frozen in one document before any code is written. Chosen because §9 explicitly plans parallel work (items 4, 5 and 7) and because contracts are what lets independent agents integrate.
- **B. Plan organised by paper sections.** Closer to the final artefact, but it mixes code and writing and makes tasks hard to assign to a single agent. Rejected.
- **C. Single plan file.** Simple, but with 14 workstreams and about 33-42 person-weeks (analisi §9) it exceeds what one agent can hold in context. Rejected.

## 4. Repository layout

```
RAL experiment/
├── CLAUDE.md                      entry point for every agent
├── tools/check_plan.py            plan verifier (only code allowed before WS05-T01)
├── docs/
│   ├── source/                    read-only sources of truth
│   ├── superpowers/specs/         this file
│   └── plan/
│       ├── PROGRESS.md            bootstrap checklist F0-F9
│       ├── 00-master-plan.md      goal, milestones, critical path, effort, do-not-cut list
│       ├── 01-conventions.md      repo layout, style, testing, git, glossary
│       ├── 02-interfaces.md       versioned contracts (Python signatures inside markdown)
│       ├── 03-decisions.md        ADRs, including autonomous choices tagged [DA-CONFERMARE]
│       ├── 04-review-traceability.md   every reviewer finding mapped to a task
│       └── workstreams/WSxx-<slug>/README.md + tasks/Txx-<slug>.md
└── src/ralmon/                    created by WS05-T01, NOT during bootstrap
```

## 5. Workstreams

The set matches roadmap §9 exactly (phase 0 plus items 1-13). Phase-0 items become WS00 (human tasks); items 1-13 become WS01-WS13 in order.

| WS | Slug | §9 item | Owner type |
|---|---|---|---|
| WS00 | admin | 0.1, 0.2, 0.3, 0.6, 0.7 | human |
| WS01 | formalization | 1 | agent |
| WS02 | threat-fault-model | 2 | agent |
| WS03 | related-work | 3 | agent (human verifies references) |
| WS04 | benchmark | 4 | agent |
| WS05 | monitor | 5 | agent |
| WS06 | baselines | 6 | agent |
| WS07 | ros2-sim | 7 | agent |
| WS08 | experiments | 8 | agent |
| WS09 | figures | 9 | agent |
| WS10 | lab-demo | 10 | mixed (physical parts human) |
| WS11 | vignettes | 11 | mixed (recruitment and ethics human) |
| WS12 | paper | 12 (plus 0.4 title, 0.5 abstract) | agent |
| WS13 | release | 13 | agent |

Core packages under `src/ralmon/` (created by WS05-T01): `signals`, `spec`, `monitor`, `conformal`, `attribution`, `benchmark`, `baselines`, `eval`.

## 6. Data access

Parameters of the latent patient and PK/PD model enter through a `PriorSource` interface. The first implementation is `LiteraturePriorSource`; `MimicPriorSource` is added when PhysioNet credentialing (WS00) completes, without changing any consumer. Analisi §5.1 states that credentialing is on the critical path, so it starts first.

## 7. Non-negotiable guarantees

1. Every task cites the analysis sections it derives from (`sources` frontmatter).
2. Every reviewer finding is traced to at least one task (`04-review-traceability.md`).
3. B5 (conformal STL baseline after Lindemann et al. 2023), ablation A4 (embodied channel) and all WS01 tasks carry `non_negotiable: true` and never appear in a cut list (analisi §9, §5.8).

## 8. Verification

`python3 tools/check_plan.py` (standard library only) checks: workstream folders have README and tasks; task frontmatter is complete; `depends_on` resolves and is acyclic; every reviewer finding is traced; every contract is used and every cited anchor exists; non-negotiable flags; no placeholder tokens; nothing in `src/`.

## 9. Out of scope for the bootstrap run

Writing anything under `src/`, running experiments, downloading data, contacting third parties. Git operations are local only.
