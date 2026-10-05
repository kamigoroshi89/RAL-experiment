---
id: WS12-T01
title: Title selection and abstract without numbers (commitment letter)
workstream: WS12-paper
owner: human
status: ready
depends_on: ["WS00-T02"]
critical_path: true
non_negotiable: false
estimate_pd: 0.5
sources: ["analisi §8.3", "analisi §8.4", "analisi §9 (0.4, 0.5)", "analisi §8.2", "analisi §10 (1)"]
interfaces: []
review_items: []
---
## Obiettivo

Choose the paper title among the three options of analisi §8.3 (the analysis recommends option 1) and write the abstract without numbers, plus the commitment-letter variant of analisi §8.4, so that milestone M0 has its paper-side text. This task is on the M0 critical path (commitment letter due in weeks 1 and 2 of the roadmap).

Concrete output: `paper/front/title.tex`, `paper/front/abstract.tex` (full abstract with bracketed result placeholders, filled later by WS12-T06), `paper/front/abstract-commitment.txt` (plain text, no numbers), and the decision record `paper/front/title-abstract-decision.md`. The abstract states the pre-clinical technical validation and makes no claim of assisting nursing staff in real-world wards.

## Contesto

Blocked until WS00-T02 is `done`, that is, until `docs/plan/workstreams/WS00-admin/outputs/WS00-T02.md` exists (WS00-T01, the CFP record, is done transitively). Read first:

- `docs/source/analisi.md` §8.3 (three titles), §8.4 (182-word abstract and the commitment-letter variant), §8.2 (what is wrong with the workshop abstract).
- `docs/source/analisi.md` §9 rows 0.4 and 0.5, and §10 objection 1 (the pre-clinical statement must be in the abstract).
- `docs/plan/workstreams/WS00-admin/outputs/WS00-T01.md` (sections `## Commitment letter content` with any abstract length limit, `## Author and title changes`, `## Prior publication policy`) and `WS00-T02.md` (sections `## ADR-001 scope` with the exact pre-clinical sentence, `## ADR-002 C3 integrity` with the name of class C3, `## ADR-003 distributed architecture`).
- `docs/plan/01-conventions.md` section 7 (binding glossary).
- `docs/plan/03-decisions.md` ADR-001, ADR-002, ADR-003, ADR-005, ADR-014.

## File toccati

- `paper/front/title.tex` (create)
- `paper/front/abstract.tex` (create)
- `paper/front/abstract-commitment.txt` (create)
- `paper/front/title-abstract-decision.md` (create)
- `docs/plan/PROGRESS.md` (modify: note for M0 once WS00-T01 and WS00-T02 are also done)

## Test

Documents task: verification checks a reviewer can run or inspect. Write them into the decision record as a checklist before drafting.

1. `paper/front/title.tex` defines exactly one `\papertitle`, character-identical to one of the three titles of analisi §8.3.
2. The title contains no term of the "Do not use" column of `01-conventions.md` section 7; "Physical AI" appears only if option 3 is chosen (the glossary allows it in the title).
3. The decision record has exactly these seven `##` headings: `Title options`, `Choice`, `Abstract edits`, `Named entities check`, `Word count`, `Commitment letter checklist`, `Fallback wording`.
4. `Title options` lists all three titles verbatim. `Choice` names one, states the title-change policy taken from `## Author and title changes` of the WS00-T01 record (changes allowed, or title frozen at the letter), and states that the choice was checked against the WS00-T02 scope decisions.
5. `abstract-commitment.txt` has no numeric result: `grep -oE '[0-9]+' paper/front/abstract-commitment.txt | sort -u` prints nothing or only `2` (from "ROS 2"), and the file contains no square bracket.
6. `abstract.tex` contains the bracketed placeholders `[N]`, `[X]`, `[Y]`, `[Z]`, `[W]` for the result quantities and no other bracketed text.
7. Both abstracts contain "Signal Temporal Logic", "conformal prediction" and a statement that the evaluation is a pre-clinical technical validation without real patients (ADR-001); the statement is the sentence recorded under `## ADR-001 scope` of the WS00-T02 record, shortened only if the word limit requires it. `abstract.tex` carries the marker `% req:preclinical` on that sentence.
8. Neither abstract contains "real-world", "ensures", "assist nursing staff", "intrinsic", "orthogonal" or "distribution-free" (analisi §4.8 and §8.2).
9. The list of baselines names the conformal STL baseline (B5) besides threshold, anomaly-detection, plain-STL and conformal-only baselines. Reason recorded: analisi §8.4 lists four, while §6, §5.4 and §10 objection 2 require B5 to be visible.
10. The architecture clause matches `## ADR-003 distributed architecture` of the WS00-T02 record (a ward node plus a mobile manipulator), not "ROS 2 nodes on a mobile manipulator" only. Class C3 is named as the WS00-T02 record names it (an integrity violation, not "tampering").
11. `Named entities check` has one row per named dataset, robot, middleware or deployment (MIMIC-IV, TIAGo, ROS 2, mock-ward deployment). Each row is either backed by a record (`WS00-T04.md` with `access_status: granted` for MIMIC-IV; `WS00-T05.md` sections `## Real robot availability` and `## TIAGo Pro simulation model` for the robot; the lab plan for the deployment) or the abstract uses the generic wording ("public clinical data", "a mobile manipulator") and the named form sits in `Fallback wording`.
12. `Word count` shows the source count (182 words for analisi §8.4), the delta of each edit, the final count of `abstract-commitment.txt` (`wc -w`), and the abstract limit taken from `## Commitment letter content` of the WS00-T01 record (and, for the submission abstract, `## Review mode and format`); the final count is not above the limit.
13. `Commitment letter checklist` has one row per element listed in `## Commitment letter content` of the WS00-T01 record. Elements outside title and abstract are labelled "owner: human, outside WS12".

## Passi

1. Read the WS00-T01 and WS00-T02 records and extract: abstract word limit and format, whether the title may change after the letter, prior-publication policy, scope decisions (main pathology, the name of class C3, distributed architecture, the exact pre-clinical sentence). Also read, if they exist, `WS00-T04.md` and `WS00-T05.md` for the named-entities check. If a needed item of the first two records is missing, stop and write a blocking note in this task file; do not guess.
2. Create `paper/front/title-abstract-decision.md` with the seven headings and paste the checks of the Test section at the end of the record as a `### Verification ticks` subsection (a third-level heading, so the count of `##` headings stays seven); every check is unticked.
3. Title: compare the three options against the glossary and against the scope records. Option 1 keeps continuity with the workshop title and adds method and platform; option 2 names the method and is the most technical; option 3 is the shortest and matches the special issue title but says least about the method (analisi §8.3). Prefer option 1 unless a record contradicts it. If the title is frozen at the letter, prefer the option that does not name a method detail that may still change. Write `Title options` and `Choice`, then `paper/front/title.tex` with `\newcommand{\papertitle}{...}`.
4. Abstract base: copy the text of analisi §8.4 into `abstract.tex` and apply only these edits, each logged in `Abstract edits` with reason and source: (a) architecture clause aligned to ADR-003; (b) B5 added to the baseline list; (c) one sentence stating that the evaluation is a pre-clinical technical validation without real patients, taken from `## ADR-001 scope` of the WS00-T02 record (analisi §10 objection 1), marked `% req:preclinical`; (d) named entities replaced by generic wording where the check of step 6 is not confirmed; (e) nothing else. Keep "Signal Temporal Logic" and "conformal prediction" (their absence was a defect of the workshop abstract, analisi §8.2).
5. Commitment variant: from `abstract.tex` remove `[N]` and replace the last sentence with the one given in analisi §8.4 ("We report per-class detection, false alarms per patient-day, empirical coverage, and on-board latency."). Save as plain text in `abstract-commitment.txt`, one paragraph, no LaTeX commands.
6. Fill `Named entities check` and `Fallback wording`. Fallback wording holds the replacement clauses to use if the lab demo is cut (cut order item 2 in `00-master-plan.md` section 7: simulation only) or if MIMIC-IV access is not obtained (results labelled "literature priors", ADR-005). WS12-T06 and WS12-T08 apply them when needed.
7. Fill `Word count` and `Commitment letter checklist` from the WS00-T01 record. If the count exceeds the limit, shorten by removing enumerations, not by removing the pre-clinical sentence or the STL and conformal terms.
8. Run every check of the Test section and tick it in the record.
9. Set `status: done` in this file. If WS00-T01 and WS00-T02 are done, add a line to `docs/plan/PROGRESS.md` stating that the paper-side artefacts of M0 exist. Commit `WS12-T01: select title and write number-free abstract`.

## Done when

```
test -f paper/front/title.tex && test -f paper/front/abstract.tex && test -f paper/front/abstract-commitment.txt && test -f paper/front/title-abstract-decision.md
grep -c '^## ' paper/front/title-abstract-decision.md            # prints 7
grep -oE '[0-9]+' paper/front/abstract-commitment.txt | sort -u   # prints nothing or only 2
grep -qi 'pre-clinical' paper/front/abstract-commitment.txt && grep -q 'req:preclinical' paper/front/abstract.tex
wc -w paper/front/abstract-commitment.txt                         # not above the limit written in the decision record
```

All commands exit 0 (the third prints only the allowed output). If `tools/check_paper.py` already exists (WS12-T02 done), `python tools/check_paper.py tokens terms claims paper/front` also exits 0.

## Notes

### Blocking note (orchestrator, 2026-10-02)

Selected by the loop on 2026-10-02 and SKIPPED (the status stays `ready` because `tools/check_plan.py` rejects `blocked` when every dependency is `done`; the loop skips tasks that carry an unresolved blocking note). The task takes its facts from `docs/plan/workstreams/WS00-admin/outputs/WS00-T01.md` (sections `## Commitment letter content` with the abstract length limit, `## Author and title changes`, `## Prior publication policy`) and `WS00-T02.md` (`## ADR-001 scope` with the exact pre-clinical sentence, `## ADR-002 C3 integrity`, `## ADR-003 distributed architecture`). WS00-T01 and WS00-T02 were marked `done` by the human, but neither artefact exists in the repository (`docs/plan/workstreams/WS00-admin/outputs/` is absent), and the decision record of this task must state the title-change policy and the length limit taken from them. Inventing them is not allowed (CLAUDE.md, working rules). Set the status back to `ready` once both artefacts exist.

### Scope change (2026-10-05)

The human removed paper writing from the agent's scope (ADR-037): this task is now `owner: human`. The agent does not write, edit or compile any text under `paper/`. Existing blocking notes of this file are moot.
