---
id: WS12-T03
title: Introduction and contributions rewrite
workstream: WS12-paper
owner: agent
status: blocked
depends_on: ["WS01-T08", "WS12-T02", "WS00-T07"]
critical_path: false
non_negotiable: false
estimate_pd: 1.5
sources: ["analisi §6", "analisi §7", "analisi §10 (3)", "analisi §10 (1)", "analisi §8.1"]
interfaces: []
review_items: ["R3-W3"]
---
## Obiettivo

Write Section I of the paper (budget 0.60 page, including the single-column Fig. 1 slot) in `paper/sections/01-introduction.tex`: problem, gap (anomaly score against prescribed care, and the "why embodiment" answer), the four revised contributions of analisi §6 with every bracketed value resolved to a number macro or removed, the statement of pre-clinical technical validation, and exactly one sentence stating the difference from the workshop paper.

Closes review item R3-W3 (clinical terminology: a Clinical Pathway is institutional and population-level, a single patient's prescription is a patient care plan; parameters must be anchored or declared unverified). Concrete output: the section file, plus updated ledger and measured size in `paper/PAGE_BUDGET.md`.

## Contesto

Blocked until WS01-T08 (formalization freeze, which fixes the template library and the definitions the contributions cite) and WS12-T02 (skeleton, macros, lint) are `done`.

- `docs/source/analisi.md` §6 (contributions with brackets), §7 row I and the cut list, §10 objections 1 and 3 (prevention text for the introduction).
- `docs/plan/workstreams/WS12-paper/README.md` (binding number macros, cut ledger, required markers).
- `docs/formal/README.md` (WS01-T08: index of the frozen formalization; the template library and the freeze note).
- `docs/plan/workstreams/WS00-admin/outputs/WS00-T02.md` (`## ADR-001 scope`, `## ADR-003 distributed architecture`: the recorded pre-clinical sentence and the sentence on what the robot adds) and `WS00-T01.md` (`## Prior publication policy`, `## Workshop proceedings archival status`).
- `Clinical_Pathways_Physical_AI_IJCAI-ECAI_2026.pdf` (workshop introduction to compress).

## File toccati

- `paper/sections/01-introduction.tex` (modify)
- `paper/PAGE_BUDGET.md` (modify: measured size of Section I, ledger status of each macro used)

## Test

Documents task: verification checks.

1. Section I fits `0.60` page within 0.10 (measure with the method recorded by WS12-T02) and contains the Fig. 1 slot with label (if WS09-T02 has not produced the figure yet, the slot stays a labelled empty box and the size is re-measured by WS12-T06).
2. The list of contributions has exactly four items, matching the four bullets of analisi §6 (pathway-grounded specification; uncertainty-aware three-valued monitoring; evidence-based attribution with embodied witnessing; implementation and evaluation). No bracketed placeholder remains: `python tools/check_paper.py placeholders paper/sections/01-introduction.tex` reports no bare bracketed placeholder and no `\ph` other than the `\ph{cite: ...}` entries of check 10. The number macros of the README table are written as macros in the source and print as placeholders in draft PDFs until WS12-T05 generates their values.
3. Each analisi §6 placeholder is resolved as in the README ledger: [K] to `\NTemplates`, [N] to `\NPatientDays`, [E] to `\NInjectedEvents`; "cover [M] of [M']" to `\NConstraintsCovered` and `\NConstraintsTotal` only if a machine-readable count exists, otherwise the clause is deleted and the ledger row marked `removed`; [two] pathways has no macro and follows the scope of `WS00-T02.md` (one main pathology, a second only if the optional WS04-T14 was done). "Clinician-reviewed" appears only if `docs/plan/workstreams/WS00-admin/outputs/WS00-T07.md` exists and its `## M1 sign-off` records the review; otherwise the text says the parameters are unverified (ADR-020). The clause in contribution 4 about a TIAGo robot and a mock-ward deployment matches the named-entities and fallback decisions of `paper/front/title-abstract-decision.md` and the `outcome` of `WS10-T05.md` when that record exists.
4. `% req:preclinical` marks one sentence stating that the evaluation is a pre-clinical technical validation on a semi-synthetic benchmark and simulation, without real patients; it follows the sentence recorded under `## ADR-001 scope` of `WS00-T02.md` and agrees with the abstract.
5. `% req:workshop-diff` marks exactly one sentence that (i) cites the workshop paper, (ii) says what the present paper adds (formal specification, monitor with conformal calibration, attribution layer, benchmark and evaluation), (iii) describes the workshop paper's status as recorded in `## Workshop proceedings archival status` of the WS00-T01 record, and satisfies `## Prior publication policy` if that section requires a statement of differences, without asserting an archival status the record does not confirm. The citation form of the workshop paper follows the anonymisation rule (WS12-T08 re-checks it).
6. `% req:why-embodiment` marks exactly one sentence answering "why embodiment": the robot executes the measurement and witness obligations that the specification induces (analisi §4.1 item 4, §10 objection 3), and is the only witness channel for INTAKE (ADR-004), while a fixed ward node keeps continuous monitoring so the robot is not a single point of failure (ADR-003). It follows the sentence recorded under `## ADR-003 distributed architecture` of `WS00-T02.md`.
7. The contrast between anomaly scores and specification-based monitoring, and the phrase "delivered safely", occur in this section at most once each; the rest of the paper does not repeat them (cut ledger item 8).
8. Terminology: `python tools/check_paper.py terms paper/sections/01-introduction.tex` exits 0; "tier", "module", "node" used as in the glossary; "on-path" and "off-path" defined exactly once here, at their first use (Fig. 1 needs them); "pathway template" and "patient care plan" used, and "Clinical Pathway" never names one patient's prescription; "Physical AI" at most once, in the framing sentence.
9. `python tools/check_paper.py claims paper/sections/01-introduction.tex` exits 0 (no "ensures", "intrinsic explainability", "orthogonal", "distribution-free", "beyond static edge-based", "real-world hospital wards").
10. Every citation key is present in `paper/refs/references.bib` with the `verified` flag set (`python3 tools/check_bib.py` exits 0). A statement that needs a reference whose entry is not verified is cited with `\ph{cite: <topic>}` instead, and listed in the ledger for WS12-T06.
11. No numeric clinical value is written in the section (`grep -nE 'mmHg|mg' paper/sections/01-introduction.tex` prints nothing), and no drug or guideline is named unless `WS00-T07.md` records its anchoring under `## Drug and guideline anchoring` (ADR-020).
12. The caption of Fig. 1 is written here (WS09 supplies the figure, not the caption); it defines "on-path" and "off-path" (the sidecar field `onpath_definition` of `paper/figures/fig1_architecture.data.json` is a proposal, the wording is owned here), names the humans shown, and, if it states the number of pipeline modules, uses a macro exported from the sidecar field `pipeline_modules` (added to the ledger).

## Passi

1. Read the inputs of Contesto. From the workshop introduction keep the problem statement and the reason anomaly scores are limited; list what is cut (cut ledger items 1, 5 and 8).
2. Run the checks above on the skeleton and note which fail: the marker, contribution-count and terminology checks fail on the empty section.
3. Resolve the analisi §6 brackets with the README ledger. Check `WS00-T07.md`, the WS01-T08 output and the benchmark manifest location (WS04-T11) for the source of each value; where no countable source exists, delete the clause. Record each decision in the ledger of `paper/PAGE_BUDGET.md` (`macro`, `status: pending generation` or `clause removed`).
4. Read the frozen formalization index and the recorded sentences of `WS00-T02.md`; then outline six paragraphs: (i) problem and setting, without claims of real-world ward benefit; (ii) gap, the only place for the anomaly-score contrast, three event classes not separated (clinical deviation, system or embodiment failure, integrity violation); (iii) idea: pathway templates instantiated into patient care plans as runtime safety specifications, tiers (sensing, robot, back-end), the definition of on-path and off-path, Fig. 1 with its caption; (iv) why embodiment, one sentence; (v) the four contributions as an itemised list; (vi) scope statement, then the difference sentence. An optional roadmap sentence only if it fits the budget.
5. Draft the section. Use the wording of analisi §4.8 for any claim ("specification-level traceability", "complementary", "cause-based taxonomy", "is designed to").
6. Compile with `make -C paper pdf`, measure, and trim to `0.60` page, dropping the roadmap sentence first and never dropping a required marker or a contribution.
7. Run the checks of the Test section and fix findings.
8. Update `PAGE_BUDGET.md` (measured size, ledger). Set `status: done`; set WS12-T06 to `ready` only if its other dependencies are done. Commit `WS12-T03: rewrite introduction and contributions`.

## Done when

```
python tools/check_paper.py terms claims tokens numerals paper/sections/01-introduction.tex   # exit 0
python tools/check_paper.py required paper/sections/01-introduction.tex            # exit 0 (checks only the files given)
grep -c 'req:workshop-diff' paper/sections/01-introduction.tex                        # prints 1
grep -c 'req:why-embodiment' paper/sections/01-introduction.tex                       # prints 1
make -C paper pdf                                                                     # exit 0
```

`paper/PAGE_BUDGET.md` shows Section I measured within `0.60 +/- 0.10` page and every macro used in Section I listed in the ledger.
