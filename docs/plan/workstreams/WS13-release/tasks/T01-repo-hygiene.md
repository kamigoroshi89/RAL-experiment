---
id: WS13-T01
title: "Repository hygiene: README, install docs, license decision"
workstream: WS13-release
owner: agent
status: blocked
depends_on: ["WS05-T08", "WS04-T11"]
critical_path: false
non_negotiable: false
estimate_pd: 1.5
sources: ["analisi §9 (13)", "analisi §6"]
interfaces: ["02-interfaces.md#package-public-api"]
review_items: []
---
## Obiettivo

Make the repository readable, installable and runnable by a stranger, and settle the licence question without deciding it silently. Concrete output: a root `README.md` (scope, install, quickstart, public API, layout, documentation index), `docs/install.md` with a dependency and licence inventory, a `LICENSE` file, licence metadata in `pyproject.toml` and in the `ros2/` packages, and a new ADR that states the licence options and constraints and records a provisional proposal with status `proposed` and the confirmation tag used by ADR-011 to ADR-017. The licence is a human decision: the agent proposes, the human confirms or overturns. Nothing is published; pushing to any remote requires explicit human approval.

## Contesto

- `docs/plan/01-conventions.md` sections 1 (layout), 4 (git: local operations only, remote operations reserved to WS13), 7 (glossary) and 8 (no clinical numeric values outside the registry).
- `docs/plan/02-interfaces.md#package-public-api` (the table of public names that the README reproduces).
- `docs/plan/03-decisions.md`: ADR format, ADR-001 (scope), ADR-005 (literature priors, credentialed data), ADR-011 (ROS 2 distribution), ADR-016 (toolchain), ADR-020 (unverified clinical parameters).
- `docs/source/analisi.md` §9 item 13, §6 (the release is an "open-source ROS 2 implementation and a semi-synthetic benchmark") and §10 objection 1.
- Completion notes of WS05-T08 (`run_offline` end to end) and WS04-T11 (benchmark builder CLI), and `docs/plan/workstreams/WS00-admin/outputs/WS00-T04.md` section `## Data handling constraints` if it exists (what the data use agreements allow).

Blocked until WS05-T08 and WS04-T11 are `done`: the quickstart needs the offline monitor and the builder. Unblocked means both completion notes exist and their commands run.

## File toccati

- `README.md` (create)
- `docs/install.md` (create)
- `LICENSE` (create)
- `pyproject.toml` (modify: licence metadata and readme fields only)
- `ros2/` (modify: the `<license>` element of each `package.xml` and the `license` argument of each `setup.py`, only if the packages exist when the task runs)
- `docs/plan/03-decisions.md` (modify: append the licence ADR and update the index line)

## Test

Verification checks (a reviewer can run or inspect each one; the agent runs them all and shows the output in the completion note):

1. `test -f README.md && test -f LICENSE && test -f docs/install.md` exits 0.
2. `README.md` contains the H2 headings `## Scope and status`, `## Installation`, `## Quickstart`, `## Public API`, `## Repository layout`, `## Documentation`, `## Licence`, in this order (`grep -n '^## ' README.md`).
3. Each of the four phrases `semi-synthetic`, `pre-clinical`, `no real patients` and `not a medical device` occurs at least once in `README.md` (`grep -ci '<phrase>' README.md` prints a number of 1 or more for each; ADR-001: pre-clinical technical validation, no real patients, semi-synthetic benchmark).
4. Claims wording (analisi §4.8, `01-conventions.md` section 7): `grep -niE 'ensures|intrinsic explainab|orthogonal|distribution-free' README.md docs/install.md` prints nothing.
5. Glossary: `grep -niE 'subsystem|edge cloud|embodied ai' README.md docs/install.md` prints nothing, and `README.md` distinguishes DISPENSE from INTAKE if it mentions either.
6. No clinical value outside the registry (ADR-020): `grep -nE '[0-9] ?mmHg' README.md docs/install.md` prints nothing.
7. Public API table: for each row of `02-interfaces.md#package-public-api`, the README row lists the same names, and `python -c "import importlib; m = importlib.import_module('ralmon.<package>'); [getattr(m, n) for n in ('<name>', ...)]"` exits 0 for every package (run for all eight packages; write the loop in a shell here-document, do not commit it).
8. Layout: every directory that the README layout block names exists (`test -d`), and every non-hidden top-level directory that is tracked by git and not gitignored appears in the block.
9. Quickstart: in a fresh virtual environment, each command of `## Quickstart` exits 0, in the documented order, from a clean checkout of the current commit; the commands are copied from the `--help` output of the builder CLI and from the WS05-T08 completion note, never written from memory. If the machine has no network for dependency installation, the completion note says so and the offline steps are still run.
10. Install docs: every version number or version constraint written in `docs/install.md` occurs in `pyproject.toml` (or its lock file); the Python requirement equals `requires-python` of `pyproject.toml` (ADR-016); the ROS 2 section names the distribution as stated in ADR-011 at the time of writing and says that the core, the tests, the benchmark and the experiments do not need ROS 2.
11. Dependency inventory: `docs/install.md` has a section `## Dependencies and licences` with one row per dependency declared in `pyproject.toml` (runtime, optional and development groups) and one row per non-Python dependency named in ADR-011 or in the `ros2/` packages; columns: name, declared constraint, licence, source of the licence statement, compatible with the proposed licence (yes, no, or needs human). A licence cell is read from installed package metadata (`importlib.metadata`) or is the word `unverified`; no licence is filled from memory.
12. Licence ADR: `grep -nE '^## ADR-[0-9]+ .*[Ll]icen[cs]e' docs/plan/03-decisions.md` prints exactly one heading; the ADR carries the same confirmation tag as the headings of ADR-011 to ADR-017, has a Status line beginning `proposed`, an options table (code, generated data, documentation), the constraints C1 to C5 of Passi step 5, alternatives, and a consequences list naming every file to change if the human overturns the proposal; the index line at the top of `03-decisions.md` mentions the new ADR.
13. Consistency: the SPDX identifier written in the ADR equals the `license` field of `pyproject.toml`; the first non-blank line of `LICENSE` names the same licence; if `ros2/` exists, `grep -h '<license>' ros2/*/package.xml | sort -u` prints one line with the same identifier; if `ros2/` does not exist yet, the completion note says so and WS13-T03 re-checks it.
14. The text of `LICENSE` was taken from a file, not typed: the ADR names its source (for example `/usr/share/common-licenses/` on the machine, the `LICENSE` file of an installed package, or a text supplied by the human).
15. Every documentation file under `docs/`, other than `docs/plan`, `docs/source`, `docs/superpowers` and `docs/anonymised-release.md` (maintainer document of WS13-T03, not part of the release), is linked from `## Documentation` in the README (`for f in $(git ls-files docs | grep -vE '^docs/(plan|source|superpowers)/|^docs/anonymised-release.md$'); do grep -q "$f" README.md || echo "missing: $f"; done` prints nothing).
16. `git remote -v` printed at the start and at the end of the task is identical; the completion note contains no command that writes to a remote.

## Passi

1. Create the branch `ws13-t01-repo-hygiene` from `main` and record `git remote -v`. Do not run any command that writes to a remote: pushing to any remote requires explicit human approval, which this task does not have; if a step seems to need it, stop and report.
2. Collect facts before writing: read the completion notes of WS05-T08 and WS04-T11, run `python -m pip --version`, read `pyproject.toml` (dependencies, extras, `requires-python`), list the top-level directories with `ls` and `git ls-files | cut -d/ -f1 | sort -u`, and run the builder CLI with `--help`.
3. Write the README skeleton with the seven headings of check 2 (the checks above are the tests of this document task; run them after each part). `## Scope and status`: what the project is (a monitoring architecture for assistive robots that checks care-plan constraints written as past-time STL templates and attributes each alert to C1, C2, C3 or UNDETERMINED), the pre-clinical technical validation on a semi-synthetic benchmark, no real patients, not a medical device and not for clinical use, and that clinical parameter values are unverified unless the registry shows a `reviewed_by` (ADR-020). Use only claim wording allowed by analisi §4.8.
4. Write `## Public API` by copying the table of `02-interfaces.md#package-public-api`; write `## Repository layout` from what exists now (not from the planned tree of `01-conventions.md`), adding a note for directories excluded from the release (`data/raw/`, `outputs/`); write `## Installation` as a pointer to `docs/install.md` with the two shortest commands.
5. Write the licence ADR (next free number: run `grep -n '^## ADR-' docs/plan/03-decisions.md | tail -3`; at bootstrap the next number is ADR-021, but other workstreams may have added ADRs). Format as the other ADRs: context, decision, alternatives, consequences, status. Content:
   - Options for the code (`src/ralmon`, `ros2/`, `tools/`): MIT (keep copyright and licence notice; no express patent grant); BSD-3-Clause (as MIT plus a non-endorsement clause); Apache-2.0 (notice, statement of changes, express patent grant, NOTICE mechanism); GPL-3.0-or-later or AGPL-3.0-or-later (copyleft: derivative works are distributed under the same terms; AGPL extends this to network use). Options for the generated benchmark data and sample days: CC BY 4.0 (attribution), CC0 1.0 (no conditions), or the same licence as the code. Options for documentation and paper-derived text: CC BY 4.0 or the code licence. The descriptions are orientation, not legal advice.
   - Constraints, each answered in the ADR: C1 compatibility with every dependency licence in the inventory of `docs/install.md` (a dependency that imposes terms on the combined work excludes some options); C2 the licence chosen does not govern anything derived from credentialed data: MIMIC-IV and eICU are used under a data use agreement, so the release contains no record and no value derived from them unless the human confirms, from WS00-T04 `## Data handling constraints`, that the agreement allows it, and until then only `LiteraturePriorSource` parameters (ADR-005) are released; C3 institution or funder policy, which the plan does not establish (write `not established by the plan; the human states it` and leave the field for the human); C4 analisi §6 promises an "open-source" implementation, so the code licence must be one that the Open Source Initiative approves; C5 the copyright line names holders, which the anonymised snapshot replaces (WS13-T03).
   - Provisional proposal: the option that satisfies C1 to C5 and imposes the fewest conditions on reusers, with a reason of one or two sentences and the statement that it is the agent's recommendation and not a decision. If the inventory shows a dependency that forces terms, propose the compatible option and say why. List the alternatives that also satisfy the constraints.
   - Consequences: the files to change if the human overturns the proposal (`LICENSE`, `pyproject.toml`, `ros2/*/package.xml`, `ros2/*/setup.py`, the `## Licence` section of `README.md`, the `## Distribution and licence` section of `docs/benchmark/datasheet.md` from WS13-T04, the copyright line handled by WS13-T03), and the human actions: confirm the ADR, state the institution or funder policy, verify the dependency licences marked `unverified`.
   - Status: `proposed`, with the confirmation tag. Update the index line at the top of `03-decisions.md`.
6. Create `LICENSE` from a file (see check 14) according to the proposal, with a copyright line that carries the year and the holder that the human states; if no holder is known to the plan, write the line `Copyright (c) <year> The authors` and record in the completion note that the human must state the holder. Set `license` (SPDX expression) and `readme` in `pyproject.toml`; leave every other field untouched. If `ros2/` exists, set the `<license>` element of each `package.xml` and the `license` argument of each `setup.py`.
7. Write `docs/install.md`: requirements (Python from `requires-python`), install of the core with the extras defined by WS05-T01 (copy the exact commands from `pyproject.toml` and the WS05-T01 note), how to run the tests (`pytest`, `ruff check src tests`, `mypy src/ralmon`), the optional ROS 2 section (distribution and simulator as in ADR-011, marked as needed only for `ros2/` and the simulation), and `## Dependencies and licences` (check 11).
8. Write `## Quickstart` in the README: generate a small benchmark with the builder CLI (copy the invocation from `--help`, with a small scale and an explicit seed), then run the offline monitor on one generated day through the public API (`run_offline`), then run the unit tests. Run every command in a fresh virtual environment (check 9). Add `## Documentation` (links to `docs/install.md` and every other user-facing document that exists) and `## Licence` (one sentence naming the licence and pointing to `LICENSE`).
9. Run checks 1 to 16 and fix failures. Commit on the branch with messages of the form `WS13-T01: <summary>`; the last commit sets `status: done` in this task file. Merge to `main` locally. Do not push (pushing to any remote requires explicit human approval).
10. Write the completion note: check output, the licence proposal, and the list of human actions (confirm or overturn the licence ADR; state institution or funder policy; verify dependency licences marked `unverified`; state the copyright holder).

## Done when

From the repository root:

- `test -f README.md && test -f LICENSE && test -f docs/install.md` exits 0.
- `grep -c '^## ' README.md` prints at least 7 and the seven headings of check 2 appear in order.
- `grep -nE '^## ADR-[0-9]+ .*[Ll]icen[cs]e' docs/plan/03-decisions.md` prints one line, and the Status line of that ADR begins with `proposed`.
- `grep -n 'license' pyproject.toml` shows the SPDX identifier written in the ADR.
- `pytest tests -q` exits 0 (no regression from the metadata change).
- The completion note shows the output of checks 1 to 16, `git remote -v` before and after (identical), and the list of human confirmations still open.
