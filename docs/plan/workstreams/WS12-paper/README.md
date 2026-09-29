# WS12-paper: Paper

## Objective

Turn the results and formalization of the other workstreams into the IEEE RA-L paper (6 pages, planned in the worst case with references included, analisi §7) as LaTeX sources in `paper/`, from the title and the number-free abstract for the commitment letter (milestone M0) to the compiled, reviewed, page-fitted and anonymisation-checked PDF (milestone M5).

The paper is a **pre-clinical technical validation**: semi-synthetic benchmark, ROS 2 simulation and (optional) mock-ward demo, no real patients (ADR-001). The paper must:

- state the pre-clinical technical nature in the abstract, in the introduction and in the limitations (analisi §10, objection 1), with the sentence recorded by WS00-T02 under `## ADR-001 scope`;
- contain exactly one sentence that states the difference from the IJCAI-ECAI workshop paper (analisi §7, row I);
- use the claim wording of analisi §4.8 and the binding glossary of `docs/plan/01-conventions.md` section 7;
- take every number from `outputs/` through scripts (`01-conventions.md` section 9), never typed by hand.

Effort: 13.0 person-days (analisi §9 item 12 "Scrittura, review interna in ruolo avvocato del diavolo", plus items 0.4 title and 0.5 abstract, placed here by ADR-014). Task T01 is on the M0 critical path; T04, T05, T06, T07 and T08 are on the M5 critical path.

## Inputs

- `docs/source/analisi.md`: §4 (technical content to write down), §4.8 (claim rewording table, used as claim audit), §5 (experiments to report), §6 (revised contributions with bracketed values), §7 (6-page structure, page budget, cut list, key figures), §8 (terminology, three title options, 182-word abstract, Index Terms candidates), §9 (0.4, 0.5, 12), §10 (residual objections and their prevention text).
- `docs/source/review.md`: the reviewer findings, used as the checklist of T07.
- `Clinical_Pathways_Physical_AI_IJCAI-ECAI_2026.pdf` (repository root): the workshop text to compress and rewrite (sections I, II-A, II-B a-d, III, IV).
- `docs/plan/01-conventions.md` (glossary, section 9), `docs/plan/02-interfaces.md` (contracts `#template`, `#alert`, `#metrics`), `docs/plan/03-decisions.md` (ADR-001, 002, 003, 004, 005, 008, 018, 020), `docs/plan/04-review-traceability.md` (authoritative list of finding ids).
- Human records under `docs/plan/workstreams/WS00-admin/outputs/`: `WS00-T01.md` (sections `## Page limit`, `## Prior publication policy`, `## Workshop proceedings archival status`, `## Commitment letter content`, `## Author and title changes`, `## Review mode and format`), `WS00-T02.md` (sections `## ADR-001 scope`, `## ADR-002 C3 integrity`, `## ADR-003 distributed architecture`), `WS00-T03.md` (`## Authorship and acknowledgement`), `WS00-T04.md` (`access_status` per dataset), `WS00-T05.md` (robot availability, ADR-011 decision), `WS00-T07.md` (clinician review: `## Unreviewed entries`, `## Drug and guideline anchoring`, `## M1 sign-off`).
- Upstream outputs, located through the `## Outputs` section of each upstream README: `docs/formal/` (WS01), `docs/models/` and `configs/diagnosability.yaml` (WS02), `paper/refs/references.bib`, `tools/check_bib.py` and `docs/related-work/` (WS03), `outputs/<experiment_id>/<seed>/` and `experiments/results.lock.json` (WS08), `paper/figures/`, `paper/tables/` (WS09), `outputs/ws07-latency/` (WS07), `outputs/WS10-T05.md`, `outputs/lab-summary/` and `hardware/lab_demo/claims.md` (WS10), `tools/check_anonymity.py` and the anonymised snapshot record (WS13).

## Outputs

All under `paper/` unless stated. Nothing here is written during bootstrap; the tasks create these files.

### Paper directory layout and owning tasks

```
paper/
├── main.tex                      T02 (template class and options from the CFP record); T08 (final)
├── Makefile                      T02: targets pdf, check, numbers, check-numbers, clean; switches FINAL=1, ANON=1
├── authors.tex                   T02 (author block, hidden when ANON=1); T08 (re-check)
├── PAGE_BUDGET.md                T02: limit, budget, front matter and geometry, number-macro ledger, cut ledger, overage; updated by T03-T08
├── REVIEW-CHECKLIST.md           T07: internal audit record, not part of the submission
├── FINAL-CHECK.md                T08: record of the final checks
├── front/
│   ├── title.tex                 T01
│   ├── abstract.tex              T01 (bracketed result placeholders); T06 (numbers as macros)
│   ├── abstract-commitment.txt   T01 (plain text, no numbers)
│   ├── title-abstract-decision.md T01
│   └── index-terms.tex           T08
├── sections/
│   ├── 01-introduction.tex       T03
│   ├── 02-related-work.tex       T06 (from docs/related-work/related-work-draft.tex of WS03-T05)
│   ├── 03-formulation.tex        T04
│   ├── 04-method.tex             T04
│   ├── 05-experiments.tex        T05
│   ├── 06-discussion.tex         T06
│   └── 07-conclusion.tex         T06
├── refs/references.bib           WS03 (created, filled and verified there); WS12 only cites
├── figures/, tables/             WS09, generated, never edited here; tables/*_macros.tex define macros
├── generated/numbers.tex         T05 (generated by tools/paper_numbers.py from outputs/)
└── build/                        gitignored
tools/check_paper.py              T02 (lint: forbidden tokens, glossary terms, claim phrases, numerals, placeholders, required markers, pages, structure)
tools/paper_numbers.py            T05 (outputs/ and manifest to LaTeX macros, built on tools/figures of WS09-T01)
tests/tools/                      tests of the two scripts (WS03-T01 also puts its tests here; keep file names distinct)
```

WS09 generates the figures (`fig1_architecture.pdf`, `fig2_patient_day.pdf`, `fig3_recall_coverage.pdf`, optional `fig4_lab.pdf`) and the tabulars (`table1_templates.tex`, `table2_main.tex`, `table3_ablations.tex`) and their macro files. WS09 supplies floats and macros, never captions: the paper wraps each tabular in `table` or `table*` and writes every caption and label. Captions quote facts (Fig. 2 patient id, day, seed, alpha, variant; Fig. 1 module count; table notes) through macros exported from the sidecar `.data.json` files and the WS09 macro files, never typed. `main.tex` shows a labelled empty box while a WS09 file is absent.

### Page budget (analisi §7, worst case, references included)

The budget of each row includes the floats listed in the same row (analisi §7 assigns them per row). Title, abstract, Index Terms and author block are not in the analisi table; T02 measures their space and records it in `paper/PAGE_BUDGET.md`, and any resulting overage is settled by the page-fit ladder of T08.

| Section | Label | Budget (pages) | Floats in the row | Written by |
|---|---|---|---|---|
| I. Introduction | `sec:intro` | 0.60 | Fig. 1, single column | T03 |
| II. Related Work | `sec:related` | 0.45 | none | T06 (draft from WS03-T05) |
| III. Problem Formulation | `sec:formulation` | 0.50 | none | T04 |
| IV-A. Specification templates | `sec:templates` | 0.50 | Table I | T04 |
| IV-B. Severity and confidence | `sec:severity` | 0.30 | none | T04 |
| IV-C. Three-valued predictive monitoring | `sec:monitoring` | 0.45 | algorithm in 10 lines (optional) | T04 |
| IV-D. Attribution | `sec:attribution` | 0.30 | compact diagnosability matrix | T04 |
| IV-E. ROS 2 realization | `sec:ros2` | 0.15 | folded into Fig. 1 | T04 |
| V-A/B. Setup | `sec:setup` | 0.50 | none | T05 |
| V-C. Results | `sec:results` | 0.60 | Table II, Fig. 2 | T05 |
| V-D. Ablations and shift | `sec:ablations` | 0.35 | Fig. 3 (two panels) or Table III | T05 |
| V-E. Robot deployment | `sec:robot` | 0.25 | Fig. 4, small, optional | T05 |
| VI. Discussion and Limitations | `sec:discussion` | 0.30 | none | T06 |
| VII. Conclusion | `sec:conclusion` | 0.10 | none | T06 |
| References | `bibliography` | 0.60 | 30 to 35 entries | WS03, checked by T06 |
| Total | | 5.95 | | |

Analisi §7 lets the compact diagnosability matrix of IV-D merge into Table III. WS09 generates Table III as the ablation table only, so a merge needs a WS09-T05 change decided by a human; by default the matrix stays inline in IV-D. WS09 generates both Fig. 3 and Table III; which of them enters V-D is decided at T05 from measured size and, if needed, by ladder step (c) of T08. Whichever is dropped, the A1 to A7 outcomes and the A4 numbers are still reported (in the other float or through macros in the text).

### Binding number macros

Every number in prose, abstract, contributions and captions is a LaTeX macro. WS09 already emits part of them; `tools/paper_numbers.py` (T05) emits the rest into `paper/generated/numbers.tex`. `main.tex` inputs the WS09 macro files and `numbers.tex` first and then gives each macro of this table a fallback `\providecommand{\Name}{\ph{label}}`, where `\ph` prints a bold bracketed label in draft builds and aborts the build when `FINAL=1`. Names use letters only (LaTeX rule, as in WS09-T01 `fmt.macro`) and are binding, so that T01 to T08 agree.

| Macro | Analisi placeholder | Meaning | Source of truth | Emitted by |
|---|---|---|---|---|
| `\NTemplates` | [K] | size of the frozen template library | `paper/tables/table1_macros.tex` | WS09-T04 |
| `\NCarePlanTemplates` | | number of phi_CP templates | `paper/tables/table1_macros.tex` | WS09-T04 |
| `\NSeeds`, `\AlphaMain`, `\NTestPatientDays` | | seeds, main alpha, test patient-days | `paper/tables/table2_macros.tex` | WS09-T05 |
| `\NPatientDays` | [N] | patient-days of the benchmark | manifest named by `benchmark_manifest` in `outputs/main/<seed>/config.yaml`: day files under `days/` | T05 |
| `\NInjectedEvents` | [E] | injected events | same manifest, sum of `event_counts` | T05 |
| `\NUnverifiedParams` | | benchmark parameters without clinician review (ADR-020) | same manifest, `n_unverified` | T05 |
| `\NConstraintsCovered`, `\NConstraintsTotal` | [M], [M'] | constraints of the clinician-reviewed pathway covered by templates, and total | only if a machine-readable count exists (registry or WS01 output); otherwise T03 deletes the clause (analisi §6: placeholders are filled or eliminated) and the ledger marks both rows `removed` | T05 |
| `\ResRecall` | [X] | headline recall of the proposed method, pooled class `any`, unless T05 records another choice | `outputs/main/<seed>/metrics.json`, `per_class_prf.ours.any.recall`, seed aggregate of the WS09 aggregator | T05 |
| `\ResFalseAlarms` | [Y] | false alarms per patient-day of the proposed method | same file, `false_alarms_per_patient_day.ours` | T05 |
| `\ResCoverageGap` | [Z] | largest gap in percentage points between empirical and nominal level over the alpha grid, in distribution, with the level (`alert_level` or `band_level`) named in the text | same file, `empirical_coverage.ours.in_distribution` | T05 |
| `\ResLatencyMs` | [W] | on-board latency in ms, percentile named in Section V-E | `outputs/ws07-latency/<seed>/metrics.json` (WS07-T07) | T05 |

The analisi placeholder [two] (care pathways) has no macro: the text follows the scope recorded in `WS00-T02.md` (one main pathology, hypertension, ADR-001) and mentions a second pathology only if the optional WS04-T14 was done. Any further macro is added to the ledger in `paper/PAGE_BUDGET.md` in the same commit that first uses it.

### Cut-and-compress ledger (analisi §7, "Cosa tagliare o comprimere")

| # | Workshop text | Action | Task |
|---|---|---|---|
| 1 | §II-A narrative of the subsystems and pull/push dataflow | from about 0.6 page to about 0.15 page plus the figure | T03 (Fig. 1 slot), T04 (IV-E) |
| 2 | §II-B.b tutorial on the operators always and eventually | delete; replace with formal definitions | T04 |
| 3 | old Table I and §III-B | delete; the hypertension scenario stays in 3 to 4 lines in V-A; Fig. 2 replaces the table | T05 (V-A), WS09-T03 |
| 4 | §III-A prose of the taxonomy | fold into short definitions in Section III | T04 |
| 5 | §IV paragraph "Three aspects connect this work to the trustworthy-AI agenda" | delete (rhetoric) | T06 |
| 6 | §IV future work | delete what became a contribution; keep the real limits in Section VI | T06 |
| 7 | Conclusion | from one paragraph to three lines | T06 |
| 8 | repeated sentences ("whether prescribed care is delivered safely" at least four times; anomaly detection versus specification-based contrast in introduction, §IV and conclusion) | keep once, in the introduction | T03 keeps it, T06 sweeps the rest |

### Required statements (checked by `tools/check_paper.py required`)

| Marker (LaTeX comment on the sentence) | Where | Count |
|---|---|---|
| `% req:preclinical` | `front/abstract.tex`, `sections/01-introduction.tex`, `sections/06-discussion.tex` | at least 1 per file |
| `% req:workshop-diff` | `sections/01-introduction.tex` | exactly 1 |
| `% req:why-embodiment` | `sections/01-introduction.tex` | exactly 1 |

## Dependencies

Other workstreams (from INDEX `depends_on`):

- WS00-T01 (CFP verification) gates T02; WS00-T02 (scope decisions) gates T01.
- WS01-T08 (formalization freeze) gates T03 and T04; WS02-T05 (diagnosability matrix and hazard paragraph) gates T04.
- WS08-T07 (result freeze) and WS09-T05 (Table II, Table III, Fig. 3) gate T05.
- WS03-T06 (human verification of references) gates T06; the paper build fails on an unverified cited entry (ADR-018), checked with `python3 tools/check_bib.py`.
- WS13-T03 (anonymised release snapshot and `tools/check_anonymity.py`) gates T08.

Contract anchors: `02-interfaces.md#template` and `#alert` (T04), `#metrics` (T05). WS12 is also a listed consumer of `02-interfaces.md#experiment-config-and-outputs` (ownership table); T05 reads the `outputs/` layout defined there.

Upstream outputs that tasks read but INDEX does not list as `depends_on`. Each task checks that the artefact exists and, if it does not, stops and records a blocking note in the task file instead of guessing:

- T05 Section V-E needs the latency results of WS07-T07 (`outputs/ws07-latency/`) and the lab outcome of WS10-T05 (`outputs/WS10-T05.md`, `outcome` completed, partial or cut) with `outputs/lab-summary/metrics.json` or the simulation-video fallback of WS10-T06.
- T06 Section VI repeats the declared assumptions of the simulation (WS07 README) and the limits in `hardware/lab_demo/claims.md` (WS10-T06).
- T03 and T04 may write "clinician-reviewed" only if `WS00-T07.md` exists and its `## M1 sign-off` records the review; otherwise parameters are reported as unverified (ADR-020). Drugs and guidelines are named only as anchored in its `## Drug and guideline anchoring`.
- T01 may name MIMIC-IV only if `WS00-T04.md` records `access_status: granted` for it, and TIAGo or a lab deployment only if `WS00-T05.md` (and, for the deployment, the WS10 plan) confirm; otherwise it uses the generic wording (analisi §8.4, last sentence).
- T04 Section IV-C describes the forecaster at contract level (`02-interfaces.md#forecaster`); the model class is chosen by WS05-T05 (ADR) and is inserted by T06.
- T05 states the prior source and the number of unverified parameters from the benchmark manifest and `meta.prior_source` of `metrics.json`; results with literature priors are labelled so (ADR-005).

## Acceptance criteria

Each item is checkable by command or by inspecting a named file.

1. `make -C paper pdf FINAL=1 ANON=1` exits 0 (`ANON=0` only if the CFP record allows a non-anonymous submission), and `pdfinfo paper/build/main.pdf` reports a page count not above the limit recorded in `paper/PAGE_BUDGET.md` (from the CFP record, references included unless the record says otherwise).
2. `python tools/check_paper.py all --strict` exits 0: no forbidden tokens, no glossary "do not use" terms outside the allow-marked lines, no claim phrase of analisi §4.8 outside the allow-marked lines, no hand-typed numeral in prose, no `\ph` and no bare bracketed placeholder, all required markers present.
3. `make -C paper check-numbers` exits 0: `paper/generated/numbers.tex` equals a fresh regeneration from `outputs/`, and every macro of the ledger is defined.
4. `paper/front/title.tex` equals one of the three titles of analisi §8.3; `paper/front/abstract-commitment.txt` has no numeric result and states pre-clinical technical validation.
5. The abstract, Section I and Section VI each carry `% req:preclinical`; Section I carries exactly one `% req:workshop-diff`.
6. `paper/REVIEW-CHECKLIST.md` has one row for every finding id in `docs/plan/04-review-traceability.md`, one row for each of the ten claims of analisi §4.8 and for the four residual objections of analisi §10, and no row with status `open` without an owner; no non-negotiable finding (WS01, B5, A4) is `open`.
7. `python3 tools/check_bib.py` exits 0 (every cited key is `verified`).
8. `paper/FINAL-CHECK.md` records the Index Terms checked against the controlled list and the anonymisation check (`tools/check_anonymity.py` on the paper source and on the PDF text).
9. `python3 tools/check_plan.py` exits 0 after the task files' status updates.

## Source sections

- analisi §2 (reviewer simulation R1, R2, R3, AE; `docs/source/review.md`)
- analisi §3.7 (defensible novelty claim, for the contributions and Related Work)
- analisi §4 (4.1 to 4.9; 4.8 is the claim audit table)
- analisi §5 (experiments to report; 5.8 what is indispensable)
- analisi §6 (revised contributions)
- analisi §7 (6-page structure, budget, cut list, key figures)
- analisi §8 (8.1 terminology, 8.2 clarity and Index Terms, 8.3 titles, 8.4 abstract)
- analisi §9 (0.4, 0.5, 12; cut order)
- analisi §10 (residual objections 1 to 3 plus the C3 objection)

## Tasks

| id | title | owner | status | depends_on |
|---|---|---|---|---|
| WS12-T01 | Title selection and abstract without numbers (commitment letter) | agent | blocked | WS00-T02 |
| WS12-T02 | Paper skeleton with page budget | agent | blocked | WS00-T01 |
| WS12-T03 | Introduction and contributions rewrite | agent | blocked | WS01-T08, WS12-T02, WS00-T07 |
| WS12-T04 | Sections III and IV (formulation and methods) | agent | blocked | WS01-T08, WS02-T05, WS12-T02, WS00-T07 |
| WS12-T05 | Section V experiments and results | agent | blocked | WS09-T05, WS08-T07, WS07-T07, WS10-T06 |
| WS12-T06 | Discussion, limitations, conclusion, related work insertion and terminology sweep | agent | blocked | WS12-T05, WS03-T06, WS12-T03, WS12-T04 |
| WS12-T07 | Internal devil's-advocate review and claim audit | agent | blocked | WS12-T06 |
| WS12-T08 | Final compile, page fit, index terms, anonymisation check | agent | blocked | WS12-T07, WS13-T03 |
