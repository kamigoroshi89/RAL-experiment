---
id: WS00-T08
title: "Obtain full text of the key reference papers needed by implementers (Lindemann et al. ICCPS 2023 first)"
workstream: WS00-admin
owner: human
status: ready
depends_on: []
critical_path: false
non_negotiable: false
estimate_pd: 0.25
sources: ["analisi §5.4 (B5)", "analisi §3.2", "analisi §10 (2)"]
interfaces: []
review_items: []
---
## Obiettivo

Give the implementing agents the full text of the papers whose algorithms they must apply and cannot reconstruct from the analysis. Agents have no network access (ADR-018), and B5 (WS06-T06, non-negotiable) is defined as the method of Lindemann, Qin, Deshmukh and Pappas, "Conformal prediction for STL runtime verification" (ICCPS 2023): without the paper the baseline would be reinvented from memory, which the plan forbids. Concrete output: PDFs under `data/raw/papers/` (gitignored, never committed) and the artefact `docs/plan/workstreams/WS00-admin/outputs/WS00-T08.md` listing them.

## Contesto

- `docs/source/analisi.md` §3.2 (conformal prediction applied to STL, the closest work) and §5.4 (B5 row).
- `docs/plan/workstreams/WS06-baselines/tasks/T06-b5-lindemann.md` (what the implementer needs from the paper).
- `docs/plan/03-decisions.md` ADR-018 (agents do not verify references from memory; no network).
- `docs/plan/01-conventions.md` section 1 (`data/raw/` is gitignored).

## File toccati

- `docs/plan/workstreams/WS00-admin/outputs/WS00-T08.md` (create)
- `data/raw/papers/` (create, not committed: the PDFs)

## Test

Verification checks:

1. The artefact lists at least the Lindemann et al. ICCPS 2023 paper. Every row has the fields `citation:` (as in analisi §3.2, with any uncertainty of the analysis kept), `file:` (path under `data/raw/papers/`), `obtained_from:` (publisher page, institutional access or author page) and `obtained_on:` (date).
2. Optional rows, obtained if the human can: the robustness-interval online monitoring paper of Deshmukh et al. (analisi §3.1), the adaptive conformal inference paper of Gibbs and Candès and the conformal beyond exchangeability paper of Barber et al. (analisi §3.2), and the neural predictive monitoring papers of Bortolussi, Cairoli and Paoletti (analisi §3.2).
3. Each file exists and opens as a PDF whose title matches the row (the human checks the title page; this is the verification of the citation details on the paper itself, and the `verified` flag of the bibliography entry (WS03) can be set from it).
4. No PDF is inside the git tree (`git status --short` shows nothing under `data/raw/`).

## Passi

1. Search the publisher, institutional or author page for the Lindemann et al. paper; save the PDF as `data/raw/papers/lindemann2023-conformal-stl.pdf`.
2. Save the optional papers of check 2 under `data/raw/papers/` with author-year file names.
3. Create `outputs/WS00-T08.md` with one row per paper and the fields of check 1.
4. Tell the owner of WS06-T06 and WS03-T02 that the files exist; set `status: done`.

## Done when

- `test -f docs/plan/workstreams/WS00-admin/outputs/WS00-T08.md` exits 0.
- `grep -c '^file: data/raw/papers/' docs/plan/workstreams/WS00-admin/outputs/WS00-T08.md` prints at least `1`, and `test -f data/raw/papers/lindemann2023-conformal-stl.pdf` exits 0.
- `git status --short data/raw` prints nothing.
