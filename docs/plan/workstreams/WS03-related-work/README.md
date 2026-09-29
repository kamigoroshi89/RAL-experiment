# WS03-related-work: Related work and bibliography

## Objective

Deliver, in parallel with the technical workstreams, three things that together position the paper against the literature (analisi §3, meta-review item 3 = AE-3):

1. A bibliography `paper/refs/references.bib` in which every entry carries an explicit `verified` field (default `false`, ADR-018), plus a small stdlib-only tool `tools/check_bib.py` that fails when a cited entry is unverified.
2. Six short notes under `docs/related-work/` that transcribe the reference lists of analisi §3.1 to §3.6 with their uncertainty markers and record, per strand, what the paper does differently.
3. The Related Work draft `docs/related-work/related-work-draft.tex`: four dense paragraphs (about 0.45 page, analisi §7), each closed by a difference sentence, including the precise difference to Lindemann et al., ICCPS 2023 (analisi §3.2, §10 objection 2). This is the highest novelty risk of the paper (analisi §3.2, "MOLTO ALTO"); the workstream mitigates it in text, while the experimental answer is baseline B5 (WS06-T06, non-negotiable).

A human then verifies every reference that the draft cites (WS03-T06). No task of this workstream is `non_negotiable`; only T06 is on the critical path, because WS12-T06 depends on it.

Hard rules for this workstream:

- Agents have no network access and must not invent references (ADR-018, brief rule 1). Every author, year, venue and title written into a `.bib` entry comes from analisi §3.1 to §3.6 (or from analisi §2 R1 weakness 10 for the tool names Breach and S-TaLiRo). Anything else (first names, full titles, pages, DOIs, URLs, editions) is left out and is added by the human in T06.
- Agents never set `verified = {true}`. Only the human does, after checking the entry on DBLP, Google Scholar or the publisher page (analisi §3 note).
- Where analisi says that no reliable reference exists (commercial ward robots such as Moxi; the specific SCIFF work), no `.bib` entry is created. The item is listed as unresolved in the relevant note, is not cited in the draft, and is handed to T06.
- The draft describes cited works only as far as analisi describes them. Any statement about what a cited work does that goes beyond analisi is a claim the human checks against the paper text in T06.
- Paper text follows the spelling of analisi §6 and §8.4 (American: "normalized"); repository documents use the spelling of `01-conventions.md`. Checks in this workstream accept both.

## Inputs

- `docs/source/analisi.md`: §3 note on references, §3.1 to §3.7, §7 (Related Work row: four paragraphs, 0.45 page; References row: 30 to 35 entries), §9 item 3, §10 objection 2 and the fourth objection (C3), §4.8 (claim wording), §2 R1 weakness 10 (tools, complexity, RV for ROS).
- `docs/source/review.md`: R1 weakness 10 and meta-review item 3 (the findings behind `review_items`).
- `docs/plan/03-decisions.md`: ADR-018 (verification is a human step); ADR-002 (C3 as integrity or plausibility violations), ADR-008 (three-valued verdicts, conformal prediction only in PENDING), ADR-009 (normalisation), ADR-010 (attribution with abstention), used to keep the difference sentences consistent with the method.
- `docs/plan/01-conventions.md` section 7 (binding glossary) and sections 2 and 3 (Python style and tests, for the tool in T01).
- `docs/plan/workstreams/AUTHORING-BRIEF.md` (task format).

## Outputs

| Path | Produced by | Content |
|---|---|---|
| `tools/check_bib.py` | T01 | Stdlib-only gate: exit 1 if a cited entry is unverified, missing, incomplete, duplicated or malformed |
| `tests/tools/test_check_bib.py`, `tests/tools/fixtures/` | T01 | Tests and hand-written fixtures for the tool |
| `docs/related-work/bib-conventions.md` | T01 | Entry schema, key naming, verification workflow, tool usage (copied from this README) |
| `paper/refs/references.bib` | T01 creates (header only), T05 fills, T06 verifies | The single bibliography of the paper |
| `paper/refs/fragments/ws03-t02.bib`, `ws03-t03.bib`, `ws03-t04.bib` | T02, T03, T04 | Per-task entries; merged into `references.bib` by T05, then removed |
| `docs/related-work/stl-rv-robotics.md`, `conformal-predictive-monitoring.md` | T02 | Notes for analisi §3.1 and §3.2 |
| `docs/related-work/medical-cps-monitoring.md`, `guideline-formalization.md` | T03 | Notes for analisi §3.3 and §3.4 |
| `docs/related-work/assistive-ward-robots.md`, `wearable-device-security.md` | T04 | Notes for analisi §3.5 and §3.6 |
| `docs/related-work/related-work-draft.tex`, `docs/related-work/citation-selection.md` | T05 | The four-paragraph draft (body only, no `\section`) and the record of which keys are cited and why |
| `docs/plan/workstreams/WS03-related-work/outputs/WS03-T06.md` | T06 (human) | Verification record |

### Fragment-then-merge flow

T02, T03 and T04 have no dependencies, so they may run concurrently, on separate branches, and before T01 is merged. To avoid add/add conflicts each of them writes only its own files (notes and one fragment under `paper/refs/fragments/`). T01 creates `paper/refs/references.bib` (header comment, zero entries). T05, which depends on all four, merges the fragments into `references.bib` in the order T02, T03, T04, removes the fragments, and writes the draft. Every bibliography key is defined by exactly one task (the one whose analisi section lists it); other tasks cite it by key.

### Bibliography entry schema

Binding for T01 to T05. T01 copies this section into `docs/related-work/bib-conventions.md`.

| Field | Required | Value | Set by |
|---|---|---|---|
| `verified` | yes | `{false}` or `{true}`; absent counts as false for the tool | agents: `{false}`; human (T06): `{true}` |
| `uncertain` | yes | `{true}` if analisi marks the item with a dagger, else `{false}`. If the dagger covers a conference and an extended version (Bortolussi; Gombolay), both entries are `{true}` | agent; human may set `{false}` after confirming |
| `ref_status` | yes | `{recalled}`: analisi gives an author or organisation and at least one of year and venue. `{partial}`: otherwise (only a name, a number, or authors without year and venue) | agent |
| `analisi` | yes | analisi section, for example `{3.2}`; for items taken from the reviewer text `{2 (R1 weakness 10)}` | agent |
| `task` | yes | producing task, for example `{WS03-T02}` | agent |
| `topic` | yes | one-line English description of what the work is and why analisi cites it; never printed by bibliography styles | agent |
| `author` | at least one of `author`, `title` | Surnames only, as in analisi, joined by `and`; `and others` for "et al."; corporate author in double braces, for example `{{Royal College of Physicians}}`. Non-ASCII letters as LaTeX accents (`Donz{\'e}`, `Ni{\v c}kovi{\'c}`, `Co{\c s}ar`) | agent; human completes first names |
| `title` | only if analisi quotes a title, or the only identity of the item is a name written in analisi (tools without a paper, standards) | as written in analisi | agent; human completes |
| `year` | only if analisi gives it | four digits | agent |
| venue field | only if analisi gives it | `booktitle` (conference), `journal` (article), `booktitle` plus `series` plus `volume` (book chapter), `series` or `publisher` (book); abbreviations kept as in analisi (`ICCPS`, `CAV`) | agent; human expands |
| `verified_by`, `verified_on`, `verified_via` | when `verified = {true}` | name; ISO date `YYYY-MM-DD`; source consulted (DBLP, Google Scholar, publisher page) | human |
| `verify_notes` | optional | corrections made | human |

Entry types: `@inproceedings` for a conference, `@article` for a journal, `@incollection` for a book chapter, `@book` for a book or a SpringerBriefs volume, `@misc` when the venue is not given, and for standards, guidance and tools. The human may change the type during T06.

Nothing is added that analisi does not state. A field that analisi does not give is omitted, not filled from memory.

### Key naming

`<first-author-surname>-<short-topic>`, lower case ASCII, hyphens, no year and no venue (T06 may correct both, so keys never encode them). Where analisi names a conference version and an extended version of one work, two entries are created with suffixes `-conf` and `-ext`; T05 cites one of them and records the choice.

### Reference inventory (expected counts after T02, T03, T04)

| Fragment | Entries | `uncertain = {true}` | `ref_status = {partial}` | Entries with `title` |
|---|---|---|---|---|
| `ws03-t02.bib` (analisi §3.1, §3.2, plus Maler and Nickovic, Breach, S-TaLiRo) | 32 | 10 | 3 | 7 |
| `ws03-t03.bib` (analisi §3.3, §3.4) | 31 | 12 | 4 | 7 |
| `ws03-t04.bib` (analisi §3.5, §3.6) | 22 | 13 | 3 | 6 |
| `references.bib` after T05 | 85 | 35 | 10 | 20 |

Unresolved, no entry: commercial ward robots such as Moxi (analisi §3.5), the specific SCIFF work of Chesani, Mello, Montali et al. (analisi §3.4).

## Dependencies

- Upstream workstreams: none. WS03 runs in parallel from day one (00-master-plan section 4, order of attack step 1).
- Inside the workstream: T05 needs T01 to T04; T06 needs T05 (INDEX, unchanged).
- Downstream consumers (soft, no dependency edge is added):
  - WS06-T06 (baseline B5, Lindemann et al. 2023) may reuse the note `conformal-predictive-monitoring.md` for the description of the closest work.
  - WS12-T02 fixes the page budget and the bibliography path used by the paper skeleton (`paper/refs/references.bib`); WS12-T03 (introduction) may reuse the Lindemann difference sentence; WS12-T06 inserts the draft into the paper and needs T06 done (INDEX); WS12-T08 should run `python3 tools/check_bib.py` as the build gate of ADR-018.
  - WS01-T07 (FHIR and BPMN mapping sketch): if it exists when T05 runs, the paragraph on guideline formalization may add one clause pointing to it (analisi §3.4 suggests a partial mapping is a cheap and strong point); if it does not exist, nothing is claimed.
  - WS02-T02 (threat model): the wording of the C3 scope in the last paragraph follows ADR-002 and is aligned with the threat model at WS12 time.
- Contract anchors: none. The INDEX `interfaces` column is `-` for every WS03 row. Verdict-state names used in difference sentences (PENDING, VIOLATED, UNDETERMINED) follow `01-conventions.md` section 7.

## Acceptance criteria

1. `python3 -m pytest tests/tools -q` exits 0; `python3 tools/check_bib.py --schema` exits 0 on the repository bibliography (T01, and again after T05).
2. After T05, `paper/refs/references.bib` holds exactly 85 entries, 35 with `uncertain = {true}`, 10 with `ref_status = {partial}`, 20 with a `title`, every entry has `verified = {false}`, and there are no duplicate keys (`check_bib.py --schema` exits 0).
3. The six notes exist and each has the headings `## Scope`, `## Reference table`, `## What the reviewer expects`, `## Difference`, `## Risk and handling in the text`, `## Unresolved and for human verification`; the reference-table rows of a note equal the entries of its section in the fragment.
4. `docs/related-work/related-work-draft.tex` has exactly four paragraphs (markers `%P1` to `%P4`), each ending with a difference sentence (marker `%DIFF`), at most 500 words of text outside comments and citation commands (working estimate for 0.45 page, confirmed by WS12-T08), at most 25 distinct cited keys, and no `\cite` of an unresolved item.
5. The second difference sentence names Lindemann et al. (key `lindemann-conformal-stl`) and contains all four required elements: sparse event-driven sampling, formal separation of measured and predicted verdict, normalized severity over mixed units, attribution with abstention.
6. After T06: `python3 tools/check_bib.py --src docs/related-work/related-work-draft.tex` exits 0, and `docs/plan/workstreams/WS03-related-work/outputs/WS03-T06.md` exists with all fields listed in the T06 task.
7. `grep -rn -E 'T[O]DO|T[B]D|[?]{3}|lor[e]m' docs/plan/workstreams/WS03-related-work` finds nothing.

## Source sections

- analisi §3 (note on references and daggers), §3.1, §3.2, §3.3, §3.4, §3.5, §3.6, §3.7 (defensible novelty claim).
- analisi §7 (Related Work: four paragraphs, 0.45 page, each closed by a difference sentence; References: 30 to 35 entries).
- analisi §9 item 3 (Related work with verification of all references, 1.5 pw, parallel).
- analisi §10 objection 2 (incremental application of conformal STL; citation of Lindemann et al. 2023 and of the Bortolussi and Cairoli line with a precise difference sentence) and the fourth objection (C3).
- analisi §2 R1 weakness 10 and meta-review item 3 (docs/source/review.md).
- analisi §4.8 (claim wording), §8.1 (glossary).

## Tasks

| id | title | owner | status | depends_on |
|---|---|---|---|---|
| WS03-T01 | Bibliography infrastructure with verified flag and check tool | agent | ready | - |
| WS03-T02 | Related work: STL runtime monitoring, RV in robotics, conformal and predictive monitoring | agent | ready | - |
| WS03-T03 | Related work: medical CPS monitoring and guideline formalization | agent | ready | - |
| WS03-T04 | Related work: assistive ward robots and wearable-device security | agent | ready | - |
| WS03-T05 | Related Work section draft (four paragraphs with difference sentences) | agent | blocked | WS03-T01, WS03-T02, WS03-T03, WS03-T04 |
| WS03-T06 | Human verification of every reference marked unverified | human | blocked | WS03-T05 |
