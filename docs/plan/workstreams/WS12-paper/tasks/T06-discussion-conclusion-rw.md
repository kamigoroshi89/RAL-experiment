---
id: WS12-T06
title: Discussion, limitations, conclusion, related work insertion and terminology sweep
workstream: WS12-paper
owner: human
status: blocked
depends_on: ["WS12-T05", "WS03-T06", "WS12-T03", "WS12-T04"]
critical_path: true
non_negotiable: false
estimate_pd: 1.5
sources: ["analisi §7", "analisi §8.1", "analisi §8.2", "analisi §10", "analisi §3.7"]
interfaces: []
review_items: ["R3-W7"]
---
## Obiettivo

Complete the text of the paper: write Section VI (Discussion and Limitations, budget 0.30 page) and Section VII (Conclusion, three lines, 0.10 page); insert Section II (Related Work, budget 0.45 page) from the WS03-T05 draft using only references verified by WS03-T06; fill the abstract's result placeholders with the number macros; resolve the leftover placeholders of T03 and T04; and run the paper-wide terminology and wording sweep (analisi §8.1 and §8.2, cut ledger items 5 to 8).

Closes R3-W7 (the minor imprecisions: the dispenser is not worn, the 24-hour cuff is an ambulatory blood-pressure monitoring device, ambient sensors must appear consistently in text and Fig. 1, "middleware-agnostic" contradicts the use of ROS 2 lifecycle states). Concrete output: `02-related-work.tex`, `06-discussion.tex`, `07-conclusion.tex`, a filled `abstract.tex`, and edits across the other sections.

## Contesto

Blocked until WS12-T05 (Section V and `numbers.tex`), WS03-T06 (references verified), WS12-T03 and WS12-T04 are `done`.

- `docs/source/analisi.md` §7 (rows II, VI, VII and the cut list), §8.1 and §8.2 (terminology and clarity), §10 (objections 1 to 3 and the C3 objection, prevention text).
- `docs/related-work/related-work-draft.tex` and `docs/related-work/citation-selection.md` (WS03-T05: the four-paragraph draft with markers `%P1` to `%P4` and `%DIFF`, the cited keys and the `## Trim order`); the human record `docs/plan/workstreams/WS03-related-work/outputs/WS03-T06.md`.
- `docs/models/diagnosability-hazards.md` (WS02-T05: hazards and standards paragraph, marked as draft for WS12-T04 and WS12-T06).
- `docs/source/review.md` (R3 weakness 7).
- `paper/front/title-abstract-decision.md` (fallback wording, word limit).

## File toccati

- `paper/sections/` (modify: create `02-related-work.tex`, `06-discussion.tex`, `07-conclusion.tex`; edit `01-introduction.tex`, `03-formulation.tex`, `04-method.tex`, `05-experiments.tex` only for the sweep and for leftover placeholders)
- `paper/front/abstract.tex` (modify)
- `paper/PAGE_BUDGET.md` (modify: measured sizes of the whole paper, ledger closed, cut ledger items 5 to 8 closed)

## Test

Documents task: verification checks. Run them first (most fail), then after drafting.

1. `paper/sections/06-discussion.tex` carries `% req:preclinical` on a sentence stating that the evaluation is a pre-clinical technical validation on semi-synthetic data and simulation without real patients.
2. Section VI covers, in this priority order: (a) silent faults that produce plausible values remain indistinguishable from clinical deviations, with the measured rate as a macro (analisi §4.8, row 2); (b) the informed attacker is invisible by construction and is reported in the diagnosability matrix as a result (fourth objection of analisi §10); (c) semi-synthetic data, the released generator that makes circularity inspectable, the prior source, and the status of the unlabeled real-data run; (d) absence of clinical validation and, if WS11 was not run, the absence of a clinician study; (e) hazards, standards and fallback: safety actions are hazards with a clinician in the loop, risk management and personal-care-robot standards as named in the WS02 paragraph, robot-introduced risks (collisions, infection control, camera privacy, presence is not identity), fallback to the nurse when the robot is unavailable; (f) assumptions: exchangeability, marginal coverage, one pathology (or the second one if WS04-T14 was done); (g) the declared assumptions of the simulation, which the WS07 README requires to be repeated in the limitations (witness perception is a stub with configured error rates, the manipulation step is abstract and no manipulation fault is simulated, no battery model, non-preemptive earliest-deadline-first scheduling of obligations, the cuff replay is not quantised to the BLE format and lacks diastolic and mean pressure), the validity threat of timeline compression, and the limits stated in `hardware/lab_demo/claims.md` if the lab demo was run.
3. Section VI does not contain the paragraph "Three aspects connect this work to the trustworthy-AI agenda" and contains no future-work list of items that became contributions (cut ledger items 5 and 6).
4. Section VII has at most three sentences, fits 0.10 page, restates the contribution and the main measured finding through macros, and carries no repetition of the anomaly-score contrast.
5. Section II has four paragraphs (STL runtime monitoring and RV in robotics; conformal and predictive monitoring; guideline formalization and medical CPS; assistive robots in wards and wearable-device security), corresponding to `%P1` to `%P4` of the WS03 draft, each ending with the sentence that states the difference from this paper (`%DIFF`), and fits 0.45 page. The 500-word and 25-key caps of the draft are working estimates; the compiled size decides.
6. The second paragraph cites Lindemann et al. 2023 and the Bortolussi and Cairoli line and states the difference precisely: sparse, event-driven sampling; formal separation of measured and predicted verdicts; severity normalised over mixed units; attribution with abstention (analisi §10 objection 2). The text says B5 is that method as a baseline.
7. Every cited key is `verified` (`python3 tools/check_bib.py` exits 0); no `\ph{cite: ...}` remains; the total number of references is between 30 and 35 (analisi §7) or the deviation is recorded in the ledger for the page-fit decision of WS12-T08 (which uses the `## Trim order` of `citation-selection.md`).
8. `paper/front/abstract.tex` has no bare bracket; the placeholders are replaced by `\NPatientDays`, `\ResRecall`, `\ResFalseAlarms`, `\ResCoverageGap` and `\ResLatencyMs`; each number is the same macro that Section V uses; the fallback wording of the decision record is applied when the lab demo was cut or MIMIC-IV was not used; the word count is not above the CFP limit; `% req:preclinical` is still present.
9. `\ph{forecaster-model}` in Section IV-C is replaced from the ADR of WS05-T05; no `\ph` remains anywhere: `python tools/check_paper.py placeholders paper/front paper/sections --strict` exits 0.
10. Terminology sweep (analisi §8.1). Each row is checked by `python tools/check_paper.py terms` plus reading each occurrence:

| Do not use | Use |
|---|---|
| "subsystem" for tiers, modules or processes | tier (sensing, robot, back-end), module (RSM components), node (ROS 2 processes) |
| "edge cloud", "cloud subsystem", "edge" unqualified | back-end (off the safety-critical path) or ward server; on-path and off-path defined once |
| multivariate time-series learner, temporal prediction subsystem, Time-Series Learner | forecaster |
| calibrated uncertainty subsystem, uncertainty subsystem, conformal subsystem, Conformal Uncertainty | conformal calibrator |
| "Clinical Pathway" for one patient's prescription | pathway template, instantiated into a patient care plan |
| "Physical AI", "embodied medical AI", "embodied AI", "clinical robotic architecture" | "Physical AI" only in title and framing; otherwise assistive robot, monitoring architecture |
| "robust" for noise tolerance | "robustness" reserved to STL semantics; "noise tolerance" otherwise |
| PILL, "dispenser open", "intake" used interchangeably | DISPENSE (dispenser opening) and INTAKE (verified by the robot) |
| "violation" for C2 and C3 events | alert (output), violation (violated sub-formula), attributed cause (kappa) |
| smart-medical devices | smart medical devices |

11. Clarity items of analisi §8.2 and the cut ledger: the words "natural", "practical pay-off" and "conceptual core" are absent as emphasis; phi_HW and phi_DOSE do not occur (they are the SYS constraint and the count template); "missed deadlines on safety-critical topics" is either explained or absent; the sentence "operational states are observable to the RSM and used to disambiguate sensor faults from clinical events" is replaced by the concrete mechanism of Section IV-D; `grep -rho 'delivered safely' paper/sections | wc -l` prints at most 1 (cut ledger item 8); RSM is expanded once at first use; American spelling is uniform (as in analisi §6 and §8.4).
12. R3-W7 checks: the dispenser is not described as worn; the 24-hour cuff is called an ambulatory blood-pressure monitoring device; ambient sensors are either present in Fig. 1 and the text or absent from both; "middleware-agnostic" does not occur.
13. The whole paper compiled with `make -C paper pdf` is measured against the budget; any excess over the page limit is written in the ledger with the sections that exceed their budget, for the ladder of WS12-T08. No non-negotiable content is cut to fit (formalization, B5 result, A4 result, diagnosability rows, the pre-clinical statement).

## Passi

1. Preconditions: `docs/related-work/related-work-draft.tex` and the WS03-T06 record of verified references exist; `paper/generated/numbers.tex` exists (WS12-T05). If not, stop and write a blocking note.
2. Run the checks above and note the failures before drafting.
3. Insert Section II: take the four paragraphs of `docs/related-work/related-work-draft.tex` (body only, no `\section`) and compress to 0.45 page keeping the four difference sentences; keep the difference sentence of the second paragraph as in check 6. Keys come only from the verified bibliography.
4. Write Section VI in the priority order of check 2, taking the hazard and standards paragraph of `docs/models/diagnosability-hazards.md` in three or four sentences, and the simulation assumptions and lab limits of check 2(g) from the WS07 README and `hardware/lab_demo/claims.md` in one or two sentences. If VI exceeds 0.30 page, compress Section V-A/B by the excess instead of dropping an item of check 2, and record it.
5. Write Section VII in at most three sentences.
6. Fill `abstract.tex` from the macros; align the wording of each quantity with the definition in Sections V-C and V-E (the aggregation of recall, the percentile of latency, the setting of the coverage gap). Apply the fallback wording where needed.
7. Resolve `\ph{forecaster-model}` and every `\ph{cite: ...}` from the ledger.
8. Run the sweep: `python tools/check_paper.py terms claims tokens numerals paper/front paper/sections`; then read every occurrence of "violation", "robust", "intake", "edge" and "Physical AI" in `paper/` and fix by the table of check 10. Fix the R3-W7 items.
9. Compile, measure the whole paper, update `PAGE_BUDGET.md` (sizes, ledger, cut ledger items 5 to 8), and run all checks.
10. Set `status: done`; set WS12-T07 to `ready`. Commit `WS12-T06: complete text, related work and terminology sweep`.

## Done when

```
python tools/check_paper.py all --strict                 # exit 0
make -C paper pdf FINAL=1                                # exit 0 (no placeholder left)
make -C paper check-numbers                              # exit 0
python3 tools/check_bib.py                               # exit 0
grep -rho 'delivered safely' paper/sections | wc -l     # prints 0 or 1
```

`paper/PAGE_BUDGET.md` records the measured whole-paper page count and any excess over the page limit.

### Scope change (2026-10-05)

The human removed paper writing from the agent's scope (ADR-037): this task is now `owner: human`. The agent does not write, edit or compile any text under `paper/`. Existing blocking notes of this file are moot.
