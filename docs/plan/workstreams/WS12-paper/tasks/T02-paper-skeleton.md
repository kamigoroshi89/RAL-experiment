---
id: WS12-T02
title: Paper skeleton with page budget
workstream: WS12-paper
owner: agent
status: blocked
depends_on: ["WS00-T01"]
critical_path: false
non_negotiable: false
estimate_pd: 1
sources: ["analisi §7", "analisi §8.1", "analisi §4.8", "analisi §10 (1)"]
interfaces: []
review_items: []
---
## Obiettivo

Create the paper skeleton in `paper/`: the RA-L template named in the CFP record, one file per section of the analisi §7 structure with headings, labels and per-section page budget, a placeholder mechanism for values not yet known, a build (`make -C paper pdf`), the include slots for the WS09 figures, tables and macro files, and a stdlib-only lint `tools/check_paper.py` that every later WS12 task runs. After this task, T03 to T06 only fill section files and never touch the structure.

Concrete output: a compiling skeleton PDF, `paper/PAGE_BUDGET.md` (budget, measured front-matter space, number-macro ledger, cut ledger), and the lint with passing tests.

## Contesto

Blocked until WS00-T01 is `done`, that is, until `docs/plan/workstreams/WS00-admin/outputs/WS00-T01.md` exists with the CFP facts (template, page limit, references policy, review mode).

- `docs/source/analisi.md` §7 (budget table, figures, cut list) and §8.1 (terminology table).
- `docs/plan/workstreams/WS12-paper/README.md` (layout, page budget, binding number macros, required markers).
- `docs/plan/01-conventions.md` sections 7 (glossary, claims wording) and 9 (numbers only from `outputs/`).
- `docs/plan/03-decisions.md` ADR-018 (cited entries must be verified).
- `docs/plan/workstreams/WS00-admin/outputs/WS00-T01.md` (sections `## Page limit`, `## Review mode and format`, `## Commitment letter content`).

## File toccati

- `paper/` (create; the skeleton files `main.tex`, `Makefile`, `authors.tex`, `PAGE_BUDGET.md`, `sections/01-introduction.tex` to `sections/07-conclusion.tex`)
- `tools/check_paper.py` (create)
- `tests/tools/test_check_paper.py` (create)
- `.gitignore` (modify: add `paper/build/`)

## Test

Two parts. Part A, pytest tests of `tools/check_paper.py`, written first with fixtures built in `tmp_path` from short hand-written strings. Part B, verification checks of the skeleton.

Part A (each test fails first because the module does not exist):

- `test_tokens_flags_forbidden_markers`: a line containing one of the four forbidden tokens of `AUTHORING-BRIEF.md` rule 5 yields a finding with file and line number; a clean line yields none.
- `test_terms_flags_glossary_violations`: one line per "Do not use" term of `01-conventions.md` section 7 and analisi §8.1 (subsystem, edge cloud, multivariate time-series learner, Time-Series Learner, uncertainty subsystem, Conformal Uncertainty, embodied AI, embodied medical AI, clinical robotic architecture, smart-medical, PILL) yields one finding each; lines with tier, module, node, forecaster, conformal calibrator yield none.
- `test_terms_physical_ai_only_in_framing_files`: "Physical AI" in `front/title.tex` and `sections/01-introduction.tex` is accepted; in `sections/04-method.tex` it is flagged.
- `test_lint_ok_marker_suppresses_finding`: a flagged line that ends with `% lint-ok: quoted from the workshop text` yields no finding; the same line without the marker does.
- `test_claims_flags_section_4_8_phrases`: "ensures", "intrinsic explainability", "orthogonal", "distribution-free", "beyond static edge-based", "real-world hospital wards" are flagged; "specification-level traceability", "complementary", "is designed to" are not.
- `test_numerals_flags_hand_typed_numbers`: in prose, "a recall of 0.87", "5 seeds" and "30 min" are flagged; `\ResRecall`, "B5", "A4", "ROS 2", "Section~IV-C", "Fig.~1", `\ref{...}` and `\cite{...}` arguments, and any digit inside math mode (`$...$`, `\[...\]`, equation environments) are not; a flagged line with `% lint-ok: <reason>` is exempt.
- `test_placeholders_counts_ph_and_bare_brackets`: `\ph{N}` and a bare `[X]` are counted; a citation `[1]` and an interval `[0,W]` are not.
- `test_required_markers_report_missing`: with the layout of the README table, a missing `% req:preclinical` in `sections/06-discussion.tex` fails; two `% req:workshop-diff` in the introduction fail; exactly one passes; when file paths are given as arguments only those files are checked.
- `test_pages_parses_pdfinfo_output`: the text `Pages:           6` with limit 6 passes, `Pages:           7` with limit 6 fails.
- `test_cli_accepts_several_checks_and_paths`: the call `check_paper.py terms claims tokens <file>` runs the three checks on the file, returns 1 if any check finds something and 0 otherwise; `all` with no path runs `tokens`, `terms`, `claims`, `numerals`, `placeholders`, `required` and `structure` over `paper/front` and `paper/sections` (not `pages`, which needs a PDF and is called explicitly).
- `test_structure_requires_all_section_files_and_budget_sum`: a directory lacking `05-experiments.tex` fails; a budget table whose rows sum above the limit fails; the table of the README (sum 5.95) with limit 6 passes.

Part B (skeleton, verification checks):

1. `make -C paper pdf` exits 0 and produces `paper/build/main.pdf`.
2. `make -C paper pdf FINAL=1` exits non-zero while any `\ph` remains (expected on the skeleton, and the reason for the switch).
3. `main.tex` uses the class and options named in the CFP record and `\input`s the seven section files in order; each section file has the `\section` or `\subsection` headings and the labels of the README table and a comment `% budget: <pages> pages (analisi §7)`.
4. `PAGE_BUDGET.md` has these `##` headings: `Page limit`, `Page budget`, `Front matter and geometry`, `Number macros`, `Cut ledger`, `Overage`. The budget table equals the README table row by row. `Front matter and geometry` records the measured front-matter space, the values of `\columnwidth`, `\textwidth` and `\textheight` of the template in points and inches, whether they agree with the 3.5 in and 7.16 in assumed by WS09 (`WS09 README`, "IEEE geometry"), and the budget of each row in column-inches (budget times two columns times the column height), so that WS09-T02 and WS09-T03 can confirm their provisional maximum float heights against it.
5. Every macro of the README table "Binding number macros" has a `\providecommand{\Name}{\ph{label}}` line in `main.tex`, placed after the `\IfFileExists` inputs of `tables/table1_macros`, `tables/table2_macros` and `generated/numbers`, so that a defined macro is never redefined.
6. Float slots exist for Fig. 1 (`figures/fig1_architecture.pdf`), Fig. 2 (`figures/fig2_patient_day.pdf`), Table I (`tables/table1_templates.tex`), Table II (`tables/table2_main.tex`), Table III (`tables/table3_ablations.tex`), Fig. 3 (`figures/fig3_recall_coverage.pdf`) and optional Fig. 4 (`figures/fig4_lab.pdf`). Each slot wraps the WS09 file in `figure`, `figure*`, `table` or `table*` with a caption and label of its own (WS09 supplies tabulars and figures, not captions) and shows a labelled empty box while the WS09 file is absent.
7. `authors.tex` is included only when `ANON=1` is not set.
8. `PAGE_BUDGET.md` states, in `Page budget`, that the choice between Fig. 3 and Table III in V-D is open until WS12-T05 (WS09 generates both; analisi §7 offers either), with the rule: decide from the measured height against the 0.35 page budget, and report the A1 to A7 outcomes and the A4 numbers in either case.

## Passi

1. Read the CFP record: template class and options (`## Review mode and format`), page limit and whether references count (`## Page limit`), review mode, abstract limit (`## Commitment letter content`). Check the class locally (`kpsewhich <class>.cls`, `command -v latexmk pdflatex pdfinfo`). Agents have no network: if the class is not installed and not under `paper/template/`, stop, write a blocking note asking the human to place the official RA-L package, and do not substitute another class.
2. Write `tests/tools/test_check_paper.py` from Part A; run `pytest tests/tools/test_check_paper.py -q`; confirm all tests fail.
3. Implement `tools/check_paper.py` with the standard library only and subcommands `tokens`, `terms`, `claims`, `numerals`, `placeholders`, `required`, `pages`, `structure`, `all`. `numerals` enforces `01-conventions.md` section 9 heuristically: any digit sequence in prose that is not in the allowed patterns of the test above is a finding, so every number must be a macro from `paper/generated/numbers.tex` or come from a WS09-generated float. Several checks and paths can be given in one call (`check_paper.py terms claims tokens <paths>`). Findings print as `path:line: rule: text`; exit code 1 when any finding exists, 0 otherwise. A line ending with `% lint-ok: <reason>` is exempt. `placeholders` counts `\ph{...}` and bare bracketed capital letters such as `[N]` or `[M']`; with `--strict` any count above zero fails. The term list comes from `01-conventions.md` section 7 and analisi §8.1; the claim list from analisi §4.8. Run the tests until green.
4. Create `paper/main.tex`: class and options from the CFP record; `\input{front/title}` and `\input{front/abstract}` guarded by `\IfFileExists` with a `\ph` fallback; `\ph` defined as bold bracketed text, redefined to raise an error when `\finalbuild` is set (`make ... FINAL=1`); guarded `\IfFileExists` inputs of `tables/table1_macros`, `tables/table2_macros` and `generated/numbers` (in this order), then the `\providecommand` fallbacks of the number macros; the author block from `authors.tex` unless `ANON=1`; PDF metadata author field empty when `ANON=1`; the float slots; the bibliography `paper/refs/references.bib` created by WS03-T01 (the path WS03 fixes for the paper skeleton) with the bibliography style named by the template.
5. Create the seven section files with headings, labels and budget comments. Do not add the `% req:` markers: they must appear only together with the real sentences they mark, so that `check_paper.py required` fails on the skeleton and passes only when the statements exist.
6. Create `paper/Makefile` with targets `pdf` (latexmk, output in `paper/build`), `check` (`python ../tools/check_paper.py all` and, from the repository root and only if the file exists, `python3 tools/check_bib.py`, the gate of ADR-018), `numbers` (`python ../tools/paper_numbers.py`, which WS12-T05 creates), `check-numbers` (same script with `--check`), `clean`; variables `FINAL` and `ANON`. Append `paper/build/` to `.gitignore`.
7. Build. Measure the space taken by title, abstract, Index Terms and author block (front matter is not in the analisi §7 table) and write it under `Front matter and geometry`; use `paper/front/abstract.tex` and `title.tex` from WS12-T01 if they exist, otherwise a filler paragraph as long as the abstract limit of the CFP record. Emit position marks per section start to measure section extents if reliable within 0.15 page; otherwise record only the start page of each section and say so. If budget plus front matter exceeds the page limit, write the excess under `Overage` and do not rescale the budgets; the page-fit ladder of WS12-T08 settles it. Flag the excess in the completion note.
8. Write `PAGE_BUDGET.md` with the six headings (geometry, column-inch budgets and the V-D rule of check 8 under the headings named there); the `Page limit` line states the limit and whether references are included, copied from the CFP record. The worst case (references included) stays in force until WS12-T08 decides otherwise.
9. Run Part B checks and `python tools/check_paper.py structure`. Commit `WS12-T02: add paper skeleton, budget and lint`.

## Done when

```
pytest tests/tools/test_check_paper.py -q          # exit 0
ruff check tools tests/tools                        # exit 0 (if ruff is not installed yet: python -m py_compile tools/check_paper.py)
make -C paper pdf                                   # exit 0, paper/build/main.pdf exists
python tools/check_paper.py structure               # exit 0
make -C paper pdf FINAL=1                           # exit non-zero (placeholders present), by design
```

`paper/PAGE_BUDGET.md` exists with the six headings listed in Part B check 4, and, if WS03-T01 is done, `python3 tools/check_bib.py` runs (it may report no citation yet).
