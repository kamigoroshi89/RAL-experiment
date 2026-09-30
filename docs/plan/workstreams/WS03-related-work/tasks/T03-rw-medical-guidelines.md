---
id: WS03-T03
title: "Related work: medical CPS monitoring and guideline formalization"
workstream: WS03-related-work
owner: agent
status: done
depends_on: []
critical_path: false
non_negotiable: false
estimate_pd: 1.5
sources: ["analisi §3.3", "analisi §3.4", "analisi §8.1 (Clinical Pathway terminology)"]
interfaces: []
review_items: ["AE-3"]
---
## Obiettivo

Transcribe the reference lists of analisi §3.3 (specification-based monitoring in medicine, alarm fatigue, early warning scores) and §3.4 (formalization of clinical guidelines and pathways, process mining, standards) into a bibliography fragment of 31 entries, all `verified = {false}` (ADR-018), and into two notes that give the difference of this work to each strand. The notes carry the difference sentence for the third Related Work paragraph and record that treating guidelines as monitorable specifications is not claimed as new (analisi §3.4, risk "ALTO on contribution 1"). One item without a reliable reference (the specific SCIFF work) stays unresolved and gets no entry.

## Contesto

- `docs/plan/workstreams/WS03-related-work/README.md` (entry schema, key naming, expected counts).
- `docs/source/analisi.md` §3.3 and §3.4 (lists and "Differenza" paragraphs), §3 note on daggers.
- `docs/source/review.md` meta-review item 3 and R3 weakness 6 (alarm load and alarm fatigue).
- `docs/plan/01-conventions.md` section 7 ("Clinical Pathway" is institutional and population-level; use "pathway template" and "patient care plan" for this work's own objects).
- `docs/plan/workstreams/INDEX.md`, row WS01-T07 (FHIR and BPMN mapping sketch, a possible hook for the paragraph).

## File toccati

1. `paper/refs/fragments/ws03-t03.bib` (create)
2. `docs/related-work/medical-cps-monitoring.md` (create)
3. `docs/related-work/guideline-formalization.md` (create)

## Test

Verification checks (paths relative to the repository root).

1. Files exist: `test -f paper/refs/fragments/ws03-t03.bib && test -f docs/related-work/medical-cps-monitoring.md && test -f docs/related-work/guideline-formalization.md`.
2. Entry count and unique keys: `grep -c '^@' paper/refs/fragments/ws03-t03.bib` prints 31; `grep -o '^@[a-z]*{[^,]*' paper/refs/fragments/ws03-t03.bib | sort | uniq -d` prints nothing.
3. Nothing verified: `grep -c 'verified *= *{false}'` prints 31 and `grep -c 'verified *= *{true}'` prints 0 on the fragment.
4. Mandatory custom fields on every entry:
   ```
   for f in verified uncertain ref_status analisi task topic; do grep -c "^ *$f *=" paper/refs/fragments/ws03-t03.bib; done
   ```
   prints six lines, each 31.
5. Transcription fidelity: `grep -c 'uncertain *= *{true}'` prints 12; `grep -c 'ref_status *= *{partial}'` prints 4; `grep -c '^ *title *='` prints 7.
6. Dagger keys are exactly the twelve of the table:
   ```
   awk '/^@/{k=$0} /uncertain *= *\{true\}/{print k}' paper/refs/fragments/ws03-t03.bib | sed 's/^@[a-z]*{//; s/,$//' | LC_ALL=C sort
   ```
   prints, in this order: `arney-closed-loop-devices`, `bottrighi-guideline-verification`, `braun-bpmn4cp`, `bufo-icu-ventilation-stl`, `burattin-online-conformance`, `cameron-artificial-pancreas`, `jiang-pajic-mangharam-cardiac`, `kim-pca-pump`, `maggi-declare-monitoring`, `nickovic-shape-expressions`, `tenteije-protocure`, `terenziani-glare`.
7. Note tables match the fragment: ``grep -c '^| `' docs/related-work/medical-cps-monitoring.md`` prints 12 and the same command on `guideline-formalization.md` prints 19 (no other table row in a note starts with a backtick); the union of the keys of the two tables equals the set of keys of the fragment.
8. Each note has exactly six second-level headings: `## Scope`, `## Reference table`, `## What the reviewer expects`, `## Difference`, `## Risk and handling in the text`, `## Unresolved and for human verification` (`grep -c '^## '` prints 6).
9. No entry for unresolved items: `grep -i -c -E 'sciff|chesani|moxi' paper/refs/fragments/ws03-t03.bib` prints 0, while `guideline-formalization.md` mentions SCIFF in its unresolved section and states that no specific work is identified.
10. The `## Difference` section of `guideline-formalization.md` contains, case-insensitively, `Asbru`, `offline`, `discrete events`, `continuous signals`, `online` and `quantitative robustness`, and states that the paper does not claim that treating guidelines as monitorable specifications is new. The `## Difference` section of `medical-cps-monitoring.md` contains `single`, `several devices`, `patient`, `robot` and `cause`.
11. Glossary check on both notes: `grep -n -i -E 'sub[s]ystem|embodied A[I]|smart-medic[a]l' docs/related-work/medical-cps-monitoring.md docs/related-work/guideline-formalization.md` prints nothing.
12. If `tools/check_bib.py` exists (WS03-T01 merged): `python3 tools/check_bib.py --schema --bib paper/refs/fragments/ws03-t03.bib` exits 0 and prints `entries=31`.
13. Forbidden tokens: `grep -n -E 'T[O]DO|T[B]D|[?]{3}|lor[e]m'` on the three files prints nothing.

## Passi

Inventory (binding; transcribed from analisi, nothing added). Columns as in WS03-T02: `type` (inp, art, bk `@book`, misc); `author` is the exact `author` field; `-` means omitted; `title` only where analisi quotes a title or where the name is the only identity of the item; `†` is `uncertain = {true}`; `status` is `ref_status`; `analisi` is `{3.3}` or `{3.4}` as the section of the note. Corporate authors use double braces.

Analisi §3.3 (note `medical-cps-monitoring.md`, 12 rows):

| # | key | type | author | year | venue | title | † | status | topic |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `lee-sokolsky-medical-cps` | art | Lee and Sokolsky and others | 2012 | Proceedings of the IEEE | Challenges and research directions in medical cyber-physical systems | no | recalled | medical CPS overview |
| 2 | `arney-closed-loop-devices` | inp | Arney and others | 2010 | ICCPS | - | yes | recalled | closed-loop medical device systems |
| 3 | `kim-pca-pump` | inp | Kim and others | 2011 | EMSOFT | - | yes | recalled | generic PCA infusion pump |
| 4 | `jiang-pajic-mangharam-cardiac` | art | Jiang and Pajic and Mangharam | 2012 | Proceedings of the IEEE | - | yes | recalled | pacemaker and cardiac models |
| 5 | `cameron-artificial-pancreas` | inp | Cameron and Fainekos and Maahs and Sankaranarayanan | 2015 | RV | - | yes | recalled | artificial pancreas and runtime safety |
| 6 | `bufo-icu-ventilation-stl` | inp | Bufo and Bartocci and Bortolussi and others | 2014 | ISoLA | - | yes | recalled | STL for assisted ventilation in intensive care |
| 7 | `nickovic-shape-expressions` | inp | Ni{\v c}kovi{\'c} and others | 2019 | RV | - | yes | recalled | shape expressions with ECG examples |
| 8 | `clifford-cinc-2015` | inp | Clifford and others | 2015 | CinC | - | no | recalled | PhysioNet and Computing in Cardiology Challenge 2015 on false arrhythmia alarms in intensive care |
| 9 | `sendelbach-funk-alarm-fatigue` | art | Sendelbach and Funk | 2013 | AACN Advanced Critical Care | - | no | recalled | alarm fatigue |
| 10 | `drew-alarm-fatigue` | art | Drew and others | 2014 | PLoS ONE | - | no | recalled | alarm fatigue |
| 11 | `rcp-news2` | misc | {{Royal College of Physicians}} | 2017 | - | NEWS2 | no | recalled | early warning score; source of the ordinal-band alternative of ADR-009 |
| 12 | `wong-sepsis-external-validation` | art | Wong and others | 2021 | JAMA Internal Medicine | - | no | recalled | external validation of a proprietary sepsis prediction model; motivates the specification-based approach |

Analisi §3.4 (note `guideline-formalization.md`, 19 rows):

| # | key | type | author | year | venue | title | † | status | topic |
|---|---|---|---|---|---|---|---|---|---|
| 13 | `peleg-comparing-guideline-models` | art | Peleg and others | 2003 | JAMIA | Comparing computer-interpretable guideline models | no | recalled | comparison of guideline formalisms |
| 14 | `ohno-machado-glif` | art | Ohno-Machado and others | 1998 | JAMIA | - | no | recalled | GLIF |
| 15 | `fox-proforma` | art | Fox and Johns and Rahmanzadeh | 1998 | AI in Medicine | - | no | recalled | PROforma |
| 16 | `shahar-miksch-johnson-asbru` | art | Shahar and Miksch and Johnson | 1998 | AI in Medicine | - | no | recalled | Asbru, in the Asgaard project |
| 17 | `terenziani-glare` | art | Terenziani and others | 2001 | AI in Medicine | - | yes | recalled | GLARE |
| 18 | `shahar-temporal-abstraction` | art | Shahar | 1997 | Artificial Intelligence | - | no | recalled | knowledge-based temporal abstraction |
| 19 | `tenteije-protocure` | art | ten Teije and others | 2006 | AI in Medicine | - | yes | recalled | Protocure project, model checking of guidelines |
| 20 | `bottrighi-guideline-verification` | art | Bottrighi and others | 2010 | AI in Medicine | - | yes | recalled | model checking of guidelines |
| 21 | `maggi-declare-monitoring` | inp | Maggi and Montali and Westergaard and van der Aalst | 2011 | BPM | - | yes | recalled | declarative monitoring with finite-trace semantics (Declare) |
| 22 | `mans-process-mining-healthcare` | bk | Mans and van der Aalst and Vanwersch | 2015 | series SpringerBriefs | - | no | recalled | process mining in healthcare |
| 23 | `rojas-process-mining-healthcare` | art | Rojas and others | 2016 | Journal of Biomedical Informatics | - | no | recalled | process mining in healthcare |
| 24 | `munoz-gama-process-mining-healthcare` | art | Munoz-Gama and others | 2022 | Journal of Biomedical Informatics | - | no | recalled | process mining in healthcare |
| 25 | `carmona-conformance-checking` | bk | Carmona and others | 2018 | publisher Springer | - | no | recalled | conformance checking |
| 26 | `burattin-online-conformance` | inp | Burattin and others | 2018 | BPM | - | yes | recalled | online conformance checking |
| 27 | `braun-bpmn4cp` | misc | Braun and others | 2014 | - | - | yes | recalled | BPMN4CP, BPMN for clinical pathways |
| 28 | `hl7-fhir-plandefinition` | misc | {{HL7}} | - | - | FHIR PlanDefinition and CarePlan | no | partial | standard, target of the mapping sketch of WS01-T07 |
| 29 | `hl7-cql` | misc | - | - | - | Clinical Quality Language | no | partial | standard |
| 30 | `arden-syntax` | misc | - | - | - | Arden Syntax | no | partial | standard |
| 31 | `openehr-gdl` | misc | - | - | - | openEHR GDL | no | partial | standard |

Not an entry: the SCIFF line of work of Chesani, Mello, Montali et al. (analisi §3.4 marks it with a dagger and says "verify the specific work"). It has no identified work, so it is listed under "Unresolved" in the note, is not cited in the draft, and is handed to T06 (the human may add an entry with key `chesani-sciff-conformance` if a specific work is chosen).

Steps.

1. Create `paper/refs/fragments/ws03-t03.bib` with a two-line comment header (task id, "merged into references.bib by WS03-T05").
2. Write one entry per inventory row, in table order, with exactly the fields of the row plus `verified = {false}`, `uncertain`, `ref_status`, `analisi`, `task = {WS03-T03}`, `topic` (schema in the README). Run checks 2 to 6 and fix.
3. Create `docs/related-work/medical-cps-monitoring.md` with the six headings of check 8.
   - `## Scope`: analisi §3.3.
   - `## Reference table`: rows 1 to 12, columns key, authors as recalled, year, venue, dagger, ref_status, role in the text (medical CPS overview, closed-loop devices, infusion pump, cardiac, artificial pancreas, STL in intensive care, shape expressions, false-alarm challenge, alarm fatigue, early warning score, motivation against opaque ML deterioration models). Each row starts with the key in backticks.
   - `## What the reviewer expects`: English summary of the analisi bullets; add that Wong et al. is "useful to motivate the specification-based approach" and that the alarm-fatigue and false-alarm entries support the metric "false alarms per patient-day" (analisi §5.5) and R3 weakness 6.
   - `## Difference`: the analisi statement (those works monitor a device, a controller or a single physiological property; this work monitors adherence to a care process involving several devices, the patient and a robotic agent, and attributes a cause to each alert), then the paragraph-3 sentence (see step 5).
   - `## Risk and handling in the text`: analisi rates the risk "MEDIO": specification-based monitoring in medicine is not new, the novelty lies in the scale of the process and in attribution; the text must not claim priority for medical STL monitoring. Use "alert" for the output and do not call a device fault a "violation" (glossary).
   - `## Unresolved and for human verification`: the six daggered entries (rows 2 to 7) and the ambiguity of which of rows 5 to 7 to cite (one or two are enough for paragraph 3).
4. Create `docs/related-work/guideline-formalization.md` with the same six headings.
   - `## Scope`: analisi §3.4.
   - `## Reference table`: rows 13 to 31 in the same format (roles: model comparison, formalism, temporal abstraction, model checking, declarative monitoring, process mining, conformance checking, online conformance, BPMN for pathways, standard).
   - `## What the reviewer expects`: the analisi bullets, including the standards list and the remark that a partial mapping from FHIR PlanDefinition or BPMN to the templates is a strong and cheap point (the sketch is WS01-T07; state that the note does not describe it).
   - `## Difference`: analisi statement (these approaches work on discrete events of the clinical record, often offline, for decision support or retrospective conformance; this work works on continuous signals, with quantitative robustness, online, on an embodied agent), the sentence of step 5, and an explicit line that names Asbru and states that the paper does not claim that treating guidelines as monitorable specifications is new.
   - `## Risk and handling in the text`: risk "ALTO on contribution 1": Asbru already expresses intentions and temporal conditions that can be monitored during execution, and online monitoring of clinical process constraints with temporal logics exists; the text says so and repositions the contribution as quantitative, signal-level monitoring executed by a physical agent. Terminology: a Clinical Pathway is institutional and population-level; this paper's objects are the "pathway template" and the "patient care plan" (glossary). Hook: if WS01-T07 has produced a FHIR or BPMN mapping sketch when WS03-T05 runs, one clause may point to it; otherwise nothing is claimed.
   - `## Unresolved and for human verification`: the six daggered entries (rows 17, 19, 20, 21, 26, 27), the four `partial` standards (rows 28 to 31, no author, year or edition in analisi), and the SCIFF item.
5. In the `## Difference` section of both notes write the same paragraph-3 sentence (it covers §3.3 and §3.4 together because analisi §7 merges them into one paragraph; at most 70 words; WS03-T05 may shorten it without dropping any element). Wording:

   > Unlike these works, which monitor a single device, controller or physiological property, or which reason offline over discrete events of the clinical record for decision support and retrospective conformance, we monitor adherence to a care process that spans several devices, the patient and an assistive robot, online, on continuous signals with quantitative robustness, and we attribute a cause to each alert.

6. Run every check under "Test" and fix. Commit with message `WS03-T03: assemble medical CPS and guideline related-work notes and bib fragment`; set `status: done` in this file.

## Done when

- The thirteen checks under "Test" pass; the completion note pastes the output of checks 2 to 7 and 12 (if the tool exists).
- `grep -c '^@' paper/refs/fragments/ws03-t03.bib` prints 31 and `grep -c 'verified *= *{true}' paper/refs/fragments/ws03-t03.bib` prints 0.
- `grep -c 'Asbru' docs/related-work/guideline-formalization.md` prints a number greater than 0 and the file states that no novelty is claimed for guidelines as monitorable specifications.

## Notes

- Red state before implementation: check 1 exited 1 (files absent) and check 12 exited 2 (fragment absent).
- The fragment header comment avoids the literal string of the `verified` field, so that check 3 counts exactly the 31 entries.
- Table columns of the notes show the exact `author` string without LaTeX accents (Ničković); a row without author shows its title in the author column.
- `status` left at `in_progress` on purpose: the orchestrator reviews and closes the task.

### Post-task review

- Produced: `paper/refs/fragments/ws03-t03.bib` (31 entries, all `verified = {false}`, no DOI, URL, pages or invented field), `docs/related-work/medical-cps-monitoring.md` and `docs/related-work/guideline-formalization.md` (six `##` headings each, shared paragraph-3 difference sentence of 61 words, explicit statement that guidelines as monitorable specifications are not claimed as new, Asbru named, SCIFF without an entry). Orchestrator re-ran the "Done when" commands, `check_bib.py --schema` (exit 0, `entries=31`), the full suite (175 tests) and `check_plan` (exit 0). Independent review: PASS; provenance of all 31 entries compared field by field with analisi §3.3 and §3.4, all clean.
- Deviations from the task text: none in scope. The artefacts were generated by a throwaway script in `/tmp` that is not committed.
- Dependents: WS03-T05 stays `blocked` (waits on WS03-T02 and T04). It expects the two T03 notes, the paragraph-3 sentence and the keys `shahar-miksch-johnson-asbru` and `wong-sepsis-external-validation`, all present. No dependent assumption is broken.
- Open MINOR: (1) SCIFF is mentioned in `guideline-formalization.md` Scope (line 7) and "What the reviewer expects" (line 40) as well as in the Unresolved section; acceptable, stricter than required; (2) line 56 states the Asbru capability as fact although the reference is unverified; T05 should write "per analisi" as done at line 60; (3) the fixed sentence ends "we attribute a cause to each alert", while ADR-010 allows abstention (UNDETERMINED); T05 or WS12 may want "attribute a cause, or abstain, for each alert".
- Risks: 12 entries are flagged `uncertain` and 4 standards are `partial` (no author, year or venue); none may be cited until a human verifies them (WS00-T08 provides the PDFs). Entry types (`@book`, `@misc`, `@inproceedings`) are inferences the human may change in WS03-T06.
