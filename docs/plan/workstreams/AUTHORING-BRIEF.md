# Authoring brief for workstream documents

Used in bootstrap phase F6 (one subagent per workstream). Also the reference for anyone adding a task later.

## Inputs to read (in this order)

1. `docs/plan/01-conventions.md` (layout, style, testing, git, binding glossary).
2. `docs/plan/02-interfaces.md` (contracts). Read the full text of every contract your tasks cite, and skim the ownership table.
3. `docs/plan/03-decisions.md` (ADRs; respect them).
4. `docs/plan/workstreams/INDEX.md`: **your workstream's table is binding** (task ids, slugs, titles, owners, `depends_on`, `critical_path`, `non_negotiable`, `estimate_pd`, `sources`, `interfaces`, `review_items`). Do not add, remove, rename or renumber tasks. Do not change dependencies.
5. `docs/source/analisi.md`: read the sections named in the `sources` column, plus the roadmap rows of §9 for your workstream. Use `grep -n '^## \|^### ' docs/source/analisi.md` to find them. `docs/source/review.md` holds the reviewer findings behind `review_items`.

`docs/source/` is read-only. Precedence: sources, then `PROMPT.md`, then your own inference.

## Deliverables (only inside `docs/plan/workstreams/<WSxx-slug>/`)

- `README.md` with these sections, in this order: `## Objective`, `## Inputs`, `## Outputs`, `## Dependencies` (other workstreams and contract anchors), `## Acceptance criteria` (verifiable), `## Source sections` (analisi references), `## Tasks` (table: id, title, owner, status, depends_on).
- One file per INDEX row: `tasks/<Txx>-<slug>.md`, for example `tasks/T01-scaffolding.md`.

## Task file format

Frontmatter (exact keys; YAML; values from the INDEX row):

```markdown
---
id: WS05-T01
title: Scaffolding of src/ralmon and toolchain
workstream: WS05-monitor
owner: agent            # agent | human
status: ready           # ready if depends_on is empty, otherwise blocked
depends_on: []          # list of task ids exactly as in INDEX
critical_path: true
non_negotiable: false
estimate_pd: 0.5
sources: ["analisi §9 (5)", "analisi §8.1"]     # at least one, taken from INDEX and refined
interfaces: ["02-interfaces.md#package-public-api"]   # only anchors that exist in 02-interfaces.md
review_items: []       # finding ids from INDEX
---
## Obiettivo
## Contesto
## File toccati
## Test
## Passi
## Done when
```

Keep these six section headings exactly as written (they are the plan's template). Write the content in English.

- **Obiettivo**: two to four sentences, including the concrete output.
- **Contesto**: at most five links (paths or `02-interfaces.md#anchor` or `docs/source/analisi.md` section names) to read first.
- **File toccati**: at most six paths (a directory counts as one path when it holds tightly coupled generated or fixture files). Mark each `create` or `modify`. Code goes under `src/ralmon/<package>/` and `tests/<package>/` as in `01-conventions.md`; nothing is written to `src/` during bootstrap, you only describe it.
- **Test** (code tasks): the pytest test names, with a one-line assertion each, written **before** the steps. Include at least one failing-first test per behaviour, fixtures with hand-computed expected values, and property tests where `01-conventions.md` calls for them. **Test** (documents, human and hardware tasks): a numbered list of *verification checks* that a reviewer can run or inspect (for example "every template in the table has a unit, a scale parameter and a priority parameter").
- **Passi**: numbered, small, concrete steps in TDD order (test, watch it fail, implement, refactor, commit). For document tasks, steps that produce each part of the document.
- **Done when**: a command or inspectable artefact. Code: `pytest tests/<pkg> -q`, `ruff check src tests`, `mypy src/ralmon` with expected exit code 0. Documents: `grep`/`test -f` style checks or a named file with named required headings. Human tasks: a named artefact file with named fields (see below).

Size: a task is about one working day of an agent and touches at most six paths. `estimate_pd` is fixed in INDEX (human person-days from analisi §9); if you believe a task cannot be done within the file limit, say so in your final report instead of splitting it.

## Rules

1. **No invention.** Do not invent numbers, PK/PD or clinical parameters, drug names, citations, dataset schemas, tool APIs or package versions. Where a value is unknown, the task states which earlier task or human establishes it, and from which source. Illustrative values in analisi §4.1 stay labelled "illustrative, unverified" (ADR-020).
2. **Cite sources.** Every task names the analisi sections it derives from and, where relevant, the reviewer findings it closes.
3. **Use the contracts.** Refer to types and names exactly as in `02-interfaces.md`. If a contract seems wrong or incomplete, do not edit it; describe the issue in your final report.
4. **Glossary.** Use the binding terms of `01-conventions.md` section 7 (tier/module/node, forecaster, conformal calibrator, pathway template and patient care plan, DISPENSE and INTAKE, alert and violation and attributed cause, robustness reserved to STL).
5. **Forbidden tokens**: the four placeholder markers listed in section F9 of `PROMPT.md` (an unfinished-work marker, a to-be-decided marker, a triple question mark and the classic dummy-text word) must not appear in any plan file; `tools/check_plan.py` enforces this. (`[DA-CONFERMARE]` is allowed only in `03-decisions.md`.)
6. **Non-negotiable** tasks (`non_negotiable: yes`) must say so in their Obiettivo and must not be described as optional or cuttable.
7. **Human tasks** (`owner: human`): Done when names an artefact under `docs/plan/workstreams/<WSxx-slug>/outputs/<task-id>.md` with the required fields listed in the task, so an agent can check it exists and is complete. Do not put outputs there yourself.
8. **Optional tasks** say "OPTIONAL" in the Obiettivo and cite the cut order (`00-master-plan.md` section 7) where it applies.
9. **Blocked tasks** state in Contesto what unblocks them.
10. **Git and network:** do not run git commands and do not use the network. Do not create files outside your workstream folder. Do not write to `src/`.
11. Task text must be self-contained enough for an agent that starts with only `CLAUDE.md`, the task file and its linked contracts.

## Final report (max 150 words)

List: files written; any contract or INDEX inconsistency you found (with the exact anchor or id); any task you believe cannot meet the file limit; any dependency you think is missing.
