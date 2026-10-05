---
id: WS12-T07
title: Internal devil's-advocate review and claim audit
workstream: WS12-paper
owner: human
status: blocked
depends_on: ["WS12-T06"]
critical_path: true
non_negotiable: false
estimate_pd: 2
sources: ["analisi §2", "analisi §4.8", "analisi §10", "analisi §9 (12)"]
interfaces: []
review_items: []
---
## Obiettivo

Review the complete compiled paper as a hostile RA-L panel would, using `docs/source/review.md` (R1, R2, R3 and the Associate Editor meta-review) as the checklist (analisi §9 item 12), and audit every claim against the rewording table of analisi §4.8. Record the result in `paper/REVIEW-CHECKLIST.md`, fix every text-only defect within the page budget, and escalate every defect that needs new experiments or upstream work to a named human or workstream.

Concrete output: `paper/REVIEW-CHECKLIST.md` with one row per finding id, per reviewer question, per editor requirement, per claim of §4.8 and per prevention item of the three residual objections plus the C3 objection of analisi §10; a fix log; and the corrected paper sources.

## Contesto

Blocked until WS12-T06 is `done` (all text present, no placeholder left, lint clean).

- `docs/source/review.md` (findings and reviewer questions; the checklist).
- `docs/plan/04-review-traceability.md` (authoritative list of finding ids and the task that closes each).
- `docs/source/analisi.md` §4.8 (ten claims and their reformulations) and §4.6 (the internal inconsistencies of the workshop table that must not reappear).
- `docs/source/analisi.md` §10 (objections 1 to 3 and the C3 objection with their prevention text).
- `paper/build/main.pdf` built with `make -C paper pdf FINAL=1`.

## File toccati

- `paper/REVIEW-CHECKLIST.md` (create)
- `paper/sections/` (modify: text fixes only)
- `paper/front/abstract.tex` (modify: only if the audit requires it)
- `paper/PAGE_BUDGET.md` (modify: measured sizes after the fixes)

## Test

Documents task: verification checks on the checklist and on the paper.

1. The ids in the first column of the `Findings` table equal the finding ids of `docs/plan/04-review-traceability.md` (the command in Done when prints nothing). The expected set, from `docs/source/review.md`, is R1-W1 to R1-W10, R2-W1 to R2-W9, R3-W1 to R3-W7 and AE-1 to AE-5; if `04-review-traceability.md` differs, it is authoritative.
2. Every row has a status in {`closed`, `mitigated`, `open`}. `closed` and `mitigated` rows give a location (section label and line in `paper/sections/` or `paper/front/`) and a quotation of at most 25 words that `grep -rF` finds in the sources. `mitigated` means the weakness is declared as a limitation in the paper and the location is in Section VI. `open` rows name an owner (a human, or a WS id and task) and the proposed action.
3. The `Reviewer questions` table has 15 rows (five per reviewer), each with the location of the answer in the paper.
4. The `Editor requirements` table has one row per requirement of the meta-review list (formal specification with online semantics; operational definitions of normalised robustness, rho and kappa; explicit fault and attack model; quantitative evaluation against reasonable baselines including the closest method; evidence that embodiment contributes measurably), each mapped to its section and table or figure.
5. The `Claim audit` table has ten rows, one per row of analisi §4.8. For each: the original claim pattern is absent (`python tools/check_paper.py claims paper/front paper/sections` exits 0), and the reformulation or an equivalent qualified statement is present with its location. Row 5 (embodiment as a safety asset) points to the A4 numbers; row 2 (faulty sensor) points to the measured silent-fault rate; row 6 (single auditable path) points to the watchdog and fallback in IV-E; row 9 (assist nursing staff in real-world hospital wards) is absent from the abstract.
6. The `Residual objections` table has 16 rows: objection 1 (six prevention items: ground truth on the latent trace; baselines with the same clinical knowledge; alert load on unlabeled real data; parameters from public data reviewed by a clinician; pre-clinical validation stated in abstract, introduction and limitations; generator released), objection 2 (three items: Lindemann et al. 2023 and the Bortolussi and Cairoli line cited with a difference sentence; B5 included with at least one result where it fails; Proposition 1 presented as small but new in the three-valued setting), objection 3 (six items: robot part of the specification through the obligations of the response and integrity constraints; A4 with numbers; predictive monitoring of care-delivery deadlines; on-board latency and lab demo; hazard, standards and fallback paragraph; the introduction sentence on why embodiment), and the C3 objection (one item: undetectable cases reported in the diagnosability matrix as a result). Each row has a location or, for items that depend on work not done (for example the unlabeled real-data run or the lab demo), an `open` or `mitigated` status with owner.
7. An `Internal consistency` table checks that the paper does not reproduce the workshop table defects of analisi §4.6: no verdict displayed before its window closes (a pending obligation is PENDING, not SATISFIED); every robustness value has a stated unit or is normalised; a deliberate lifecycle transition is not called a crash and crash detection uses liveliness and heartbeat; a cascade effect is attributed to its root cause and not shown as a second top-level alert; rho of an event-log predicate is 1 and authenticity belongs to kappa; C3 is not identified by low confidence. Each row has a location and a pass status.
8. A `Devil's advocate pass` section has at least three objections per role (R1, R2, R3, editor), each written against the compiled paper as it stands, each with either the location of the answer, a logged fix, or an `open` owner.
9. Consistency of numbers: `python tools/check_paper.py numerals paper/front paper/sections` exits 0 and `make -C paper check-numbers` exits 0; the abstract, Sections I, V, VI and VII use the same macro for the same quantity.
10. Every contribution of Section I has a section that defines it and a table or figure that evaluates it, and every table and figure is referenced in the text.
11. After the fixes: `python tools/check_paper.py all --strict` exits 0, `python3 tools/check_bib.py` exits 0, and the page count is not above the limit of `paper/PAGE_BUDGET.md`.
12. No row of a finding whose closing task is non-negotiable (WS01 tasks, B5 in WS06-T06, A4 in WS08-T04, as listed in `04-review-traceability.md`) is `open`.

## Passi

1. Build the paper with `make -C paper pdf FINAL=1` and read the PDF end to end, cold, before opening the checklist.
2. Create `paper/REVIEW-CHECKLIST.md` with the headings `Findings`, `Reviewer questions`, `Editor requirements`, `Claim audit`, `Residual objections`, `Internal consistency`, `Devil's advocate pass`, `Fix log`, `Open items for human`. Fill the first column of each table from the sources (ids from `04-review-traceability.md`, questions from `review.md`, claims from analisi §4.8, prevention items from analisi §10). All statuses start as `open`.
3. Fill `Findings`, `Reviewer questions`, `Editor requirements`, `Residual objections` and `Internal consistency` by locating the evidence in the compiled paper. Judge the paper, not the intention: a finding is `closed` only if a reader of the PDF alone finds the answer.
4. Run the claim audit: `python tools/check_paper.py claims paper/front paper/sections`, then read each row of §4.8 against the text.
5. Devil's advocate pass: take the roles of R1 (runtime verification and formal methods), R2 (machine learning and uncertainty quantification), R3 (healthcare robotics and clinical HRI) and the editor in turn, and write the strongest surviving objections against this version of the paper. The optional plugin skill `academic-paper:paper-review` may generate extra reviewer personas; its output is a source of candidate objections only, each one is verified against the PDF before it enters the checklist, and it does not replace the checklist.
6. Fix every defect that is fixable in text: edit the sections, log before and after in `Fix log` with the location, recompile, rerun the lint, check the page count. Do not add claims that the results do not support; if a finding needs a new experiment, a new figure or an upstream change, leave it `open` with the owner.
7. Fill `Open items for human`. If any non-negotiable finding is `open`, stop, write a blocking note in this file and do not set the task to `done`.
8. Update `PAGE_BUDGET.md`, set `status: done`, set WS12-T08 to `ready` if WS13-T03 is also done. Commit `WS12-T07: devil's-advocate review and claim audit`.

## Done when

```
test -f paper/REVIEW-CHECKLIST.md
diff <(grep -oE '\b(R[123]-W[0-9]+|AE-[0-9]+)\b' docs/plan/04-review-traceability.md | sort -u) \
     <(grep -oE '^\| (R[123]-W[0-9]+|AE-[0-9]+) ' paper/REVIEW-CHECKLIST.md | tr -d '| ' | sort -u)     # prints nothing
python tools/check_paper.py all --strict                                                                   # exit 0
python3 tools/check_bib.py                                                                                 # exit 0
make -C paper check-numbers                                                                                # exit 0
make -C paper pdf FINAL=1                                                                                  # exit 0
```

`paper/REVIEW-CHECKLIST.md` has the nine headings of step 2, no empty status cell, and every `open` row has an owner and an action.

### Scope change (2026-10-05)

The human removed paper writing from the agent's scope (ADR-037): this task is now `owner: human`. The agent does not write, edit or compile any text under `paper/`. Existing blocking notes of this file are moot.
