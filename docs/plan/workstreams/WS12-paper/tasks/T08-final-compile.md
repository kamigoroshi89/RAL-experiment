---
id: WS12-T08
title: Final compile, page fit, index terms, anonymisation check
workstream: WS12-paper
owner: human
status: blocked
depends_on: ["WS12-T07", "WS13-T03"]
critical_path: true
non_negotiable: false
estimate_pd: 1
sources: ["analisi §7", "analisi §8.2", "analisi §9 (13)"]
interfaces: []
review_items: []
---
## Obiettivo

Produce the final PDF of the paper: clean compile with all placeholders resolved, page count within the CFP limit (worst case, references included, analisi §7), Index Terms taken from the RA-L controlled list (analisi §8.2 lists candidates to verify), and the anonymisation check performed together with the anonymised release snapshot of WS13-T03.

Concrete output: `paper/build/main.pdf`, `paper/front/index-terms.tex`, `paper/FINAL-CHECK.md`, final page-fit edits, and the M5 note in `docs/plan/PROGRESS.md` when the other M5 conditions hold.

## Contesto

Blocked until WS12-T07 (reviewed paper) and WS13-T03 (anonymised snapshot and its record) are `done`.

- `docs/source/analisi.md` §7 (worst-case page planning, optional floats) and §8.2 (Index Terms candidates: Robot Safety; Formal Methods in Robotics and Automation; Medical Robots and Systems; Human-Centered Robotics).
- `docs/plan/workstreams/WS00-admin/outputs/WS00-T01.md` (`## Page limit`, `## Review mode and format`: anonymisation rules, template, PDF requirements, Index Terms list if attached; `## Author and title changes`).
- `docs/plan/workstreams/WS13-release/README.md` (Outputs: `tools/check_anonymity.py`, `outputs/anonymised-release-report.md`, `docs/anonymised-release.md`, the hosting ADR and the anonymised link).
- `paper/PAGE_BUDGET.md` (limit, measured sizes, ledger of leftovers).
- `docs/plan/03-decisions.md` ADR-018 (only verified references are cited).

## File toccati

- `paper/main.tex` (modify: final options, anonymity default)
- `paper/front/index-terms.tex` (create)
- `paper/sections/` (modify: page-fit edits only)
- `paper/FINAL-CHECK.md` (create)
- `paper/PAGE_BUDGET.md` (modify: final measured sizes)
- `docs/plan/PROGRESS.md` (modify: M5 note if WS09 final, WS13-T03 and this task are done)

## Test

Documents task: verification checks.

1. A clean build succeeds: `make -C paper clean pdf FINAL=1 ANON=1` exits 0 (use `ANON=0` only if the CFP record states that the submission is not anonymous). If the record does not state the review mode, `ANON=1` is used and the open question is recorded in `FINAL-CHECK.md`.
2. `python tools/check_paper.py pages --pdf paper/build/main.pdf --limit <N>` exits 0, where N is the limit in `paper/PAGE_BUDGET.md`. If the CFP record says references are outside the limit, the page count is reported both with and without references and the worst case is still the one that must pass, unless the record explicitly relaxes it.
3. `paper/build/main.log` has no undefined reference or citation; each overfull box is listed in `FINAL-CHECK.md` with a decision.
4. If the CFP record requires embedded fonts (or a PDF check service), `pdffonts paper/build/main.pdf` shows `yes` in the `emb` column for every font, and the record says which requirement applied.
5. `python tools/check_paper.py all --strict` exits 0 (tokens, terms, claims, numerals, no placeholder, required markers, structure); `make -C paper check-numbers` exits 0; `python3 tools/check_bib.py` exits 0, so every cited key is `verified` (ADR-018).
6. Index Terms: every term in `paper/front/index-terms.tex` occurs in the controlled list of the RA-L template or CFP (path recorded in `FINAL-CHECK.md`). Each of the four candidates of analisi §8.2 has a row: present in the list or not, and the replacement by the closest controlled term when not. The number of terms follows the template instruction. If no controlled list is available in the repository, the Index Terms step is marked blocked in `FINAL-CHECK.md`, the file `index-terms.tex` holds the four candidates labelled as unverified, and the task is not set to `done` until a human supplies the list.
7. Anonymisation, when `ANON=1`: the PDF text (`pdftotext paper/build/main.pdf outputs/anonymity/paper-text/main.txt`) and a copy of the paper sources without `authors.tex` and `build/` (in `outputs/anonymity/paper-src/`) both pass `python tools/check_anonymity.py <dir> --terms outputs/anonymity/terms.txt --allowlist tools/anonymise_allowlist.txt` (exit 0; the terms file is the human-reviewed list of WS13-T03, and `outputs/anonymised-release-report.md` states `terms reviewed by human: yes`, otherwise this check is reported as not conclusive); the `pdfinfo` Author field is empty; no acknowledgements or funding lines; figures and captions carry no institution logo, host name or lab name (if Fig. 4 is included, its sidecar fields `exif_stripped`, `logos_or_names_visible` and `inspected_by` are confirmed by a human, and its effective resolution satisfies the rule `MIN_PHOTO_DPI` of WS09-T06 confirmed against the IEEE author guidelines or the CFP record); the workshop paper and any other self-citation follow the CFP policy for anonymous submissions (third person or anonymised entry).
8. Consistency with WS13-T03: every statement that something is released (implementation, benchmark generator) is backed by an item in the snapshot (`outputs/anonymised-release-report.md`, `docs/benchmark/`), and the paper says the artefact is anonymised for review. The anonymised link is the one the human obtained in the hosting step of `docs/anonymised-release.md` (WS13 records the hosting options and no choice until the human names one); it is inserted as a footnote in Section V-A and its wording does not identify the authors (H5 of WS13-T03). If the human has not yet provided a link, the paper announces the release without a link, the item is written under `Open items`, and the task is not set to `done` until the human provides the link or decides that no link is given during review.
9. Commitment-letter consistency: the final title equals the title of `paper/front/title.tex` chosen in WS12-T01, or the change is allowed by the CFP record and recorded as a human decision; the final abstract differs from `abstract-commitment.txt` only by the added numbers and by documented fallback wording; any difference in named dataset, robot or deployment is explained in `FINAL-CHECK.md`.
10. Author block: equals the authors of the CFP-compliant submission as recorded by `## Author and title changes` of WS00-T01 and `## Authorship and acknowledgement` of `WS00-T03.md` (a clinician or collaborator may have been added); nothing else is inferred.
11. The required statements are still in place after the page-fit edits: `% req:preclinical` in the abstract, Section I and Section VI, exactly one `% req:workshop-diff`, one `% req:why-embodiment`.
12. `paper/FINAL-CHECK.md` has exactly these `##` headings: `Build`, `Page fit`, `Lint and numbers`, `References`, `Index Terms`, `Anonymisation`, `Commitment-letter consistency`, `Open items`.

## Passi

1. Preconditions: WS12-T07 and WS13-T03 are `done`, the review checklist has no non-negotiable `open` row, and the anonymised snapshot record exists. Read the CFP record for page limit, references policy, review mode and PDF requirements. If something is missing, stop and write a blocking note.
2. Clean build: `make -C paper clean pdf FINAL=1 ANON=1`. Measure the page count and write the `Build` section (commands, date, git revision).
3. Page fit. If the count exceeds the limit, apply this ladder one step at a time, recompiling and recording pages before and after in `Page fit`; stop as soon as the paper fits: (a) drop the optional Fig. 4 of V-E; (b) drop the ten-line algorithm of IV-C and keep its description in prose; (c) show either Fig. 3 or Table III in V-D, not both (analisi §7 offers either); (d) reduce the compact diagnosability matrix of IV-D to the rows that are not distinguishable plus one row per class (merging it into Table III, which analisi §7 allows, needs a WS09-T05 change and a human decision, so it is not done here); (e) shrink Fig. 1 to single-column width with the ROS 2 placement folded into it; (f) tighten prose in V-A/B and V-C toward their budgets of 0.50 and 0.60 page and trim references in the order of `## Trim order` of `docs/related-work/citation-selection.md`, never removing Lindemann et al. 2023 or the Bortolussi and Cairoli line. Never cut: Table I, the formal definitions, Proposition 1, the B5 rows and its failure result, the A4 result, the diagnosability rows that are not distinguishable, the pre-clinical statement, the workshop-difference sentence, Section VI, the hazard and fallback paragraph. If the ladder is exhausted and the paper still exceeds the limit, stop and escalate to the human with the measured excess: the options are a scope decision or a CFP question about extra pages, not a silent cut.
4. Index Terms: locate the controlled list (the path in the CFP record, or a file the human placed under `paper/template/`), check the four candidates, write `paper/front/index-terms.tex` and the `Index Terms` section of `FINAL-CHECK.md`. Follow check 6 when no list exists.
5. References: run `python3 tools/check_bib.py` and record the result and the final reference count in `References`.
6. Anonymisation: insert the anonymised link as a footnote in Section V-A if the human provided one (check 8); run the checks 7 and 8 with the WS13-T03 report and `docs/anonymised-release.md` open; write `Anonymisation` with the commands and their outputs. Fix leaks in `paper/main.tex`, the `authors.tex` handling or the sections; add a `term => replacement` rule to the WS13 terms file only through WS13, never here.
7. Commitment-letter consistency and author block: checks 9 and 10; write the section.
8. Re-run all checks after the last edit, including the markers of check 11. Update `PAGE_BUDGET.md` with the final measured sizes.
9. Write `Open items` (empty if none). Set `status: done`. If WS09 final artefacts, WS13-T03 and this task are `done`, add the M5 line to `docs/plan/PROGRESS.md` (WS09 figures and tables final, paper compiled and reviewed, repository anonymised). Commit `WS12-T08: final compile, page fit, index terms, anonymisation`.

## Done when

```
make -C paper clean && make -C paper pdf FINAL=1 ANON=1                       # exit 0 (ANON=0 only if the CFP record allows)
python tools/check_paper.py all --strict                                       # exit 0
python tools/check_paper.py pages --pdf paper/build/main.pdf --limit <N>       # exit 0, N from paper/PAGE_BUDGET.md
make -C paper check-numbers                                                    # exit 0
python3 tools/check_bib.py                                                     # exit 0
test -f paper/front/index-terms.tex && test -f paper/FINAL-CHECK.md
grep -c '^## ' paper/FINAL-CHECK.md                                            # prints 8
pdfinfo paper/build/main.pdf | grep -E '^Author'                               # empty value when ANON=1
```

When ANON=1, `python tools/check_anonymity.py outputs/anonymity/paper-text --terms outputs/anonymity/terms.txt --allowlist tools/anonymise_allowlist.txt` and the same command on `outputs/anonymity/paper-src` (sources without `authors.tex`) exit 0. `paper/FINAL-CHECK.md` records the Index Terms verified against a named controlled list.

### Scope change (2026-10-05)

The human removed paper writing from the agent's scope (ADR-037): this task is now `owner: human`. The agent does not write, edit or compile any text under `paper/`. Existing blocking notes of this file are moot.
