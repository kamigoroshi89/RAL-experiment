---
id: WS03-T06
title: Human verification of every reference marked unverified
workstream: WS03-related-work
owner: human
status: ready
depends_on: ["WS03-T05"]
critical_path: true
non_negotiable: false
estimate_pd: 1
sources: ["analisi §3 (note)", "analisi §3.2", "analisi §10 (2)"]
interfaces: []
review_items: []
---
## Obiettivo

A human checks on DBLP, Google Scholar or the publisher page every reference that the Related Work draft cites, completes and corrects its `.bib` entry, and only then sets `verified = {true}` (ADR-018, analisi §3 note). The human also checks against the paper text that the difference sentences describe the cited works correctly, above all Lindemann et al., ICCPS 2023, and decides the fate of the unresolved items. The artefact is `docs/plan/workstreams/WS03-related-work/outputs/WS03-T06.md`; after this task `python3 tools/check_bib.py --src docs/related-work/related-work-draft.tex` must exit 0, which unblocks WS12-T06.

## Contesto

- Unblocked when WS03-T05 is `done`: `docs/related-work/citation-selection.md` exists (cited keys, verification priority, conditional citations) and `paper/refs/references.bib` holds 85 unverified entries. Start from section "Handover to T06" of that file.
- `paper/refs/references.bib` and the entry schema in `docs/plan/workstreams/WS03-related-work/README.md` (fields `verified`, `uncertain`, `ref_status`, `verified_by`, `verified_on`, `verified_via`, `verify_notes`).
- `docs/related-work/related-work-draft.tex` (the four paragraphs and their difference sentences) and `docs/related-work/conformal-predictive-monitoring.md` (the Lindemann sentence and its traceability table).
- `docs/source/analisi.md` §3 note ("all to be verified on DBLP or Google Scholar before citing"; daggers mark uncertain venue, year or authors) and `docs/plan/03-decisions.md` ADR-018.

## File toccati

1. `paper/refs/references.bib` (modify: completed and corrected entries, `verified` flags)
2. `docs/related-work/related-work-draft.tex` (modify: only where a citation is dropped or a characterization is corrected)
3. `docs/plan/workstreams/WS03-related-work/outputs/WS03-T06.md` (create, by the human; the required fields are listed below)

## Test

Verification checks that a reviewer or an agent can run once the human declares the task finished.

1. The artefact exists: `test -f docs/plan/workstreams/WS03-related-work/outputs/WS03-T06.md`.
2. It contains the header lines `verifier:`, `date:` (form `YYYY-MM-DD`), `sources_used:`, `bib_file:`, `draft_file:`, `cited_keys_total:`, `cited_keys_verified:`, `check_bib_exit_code:`, `uncited_entries_verified:`, `uncited_entries_left_unverified:`, and the sections `## Corrections`, `## Confirmed without change`, `## Dropped citations`, `## Unresolved items`, `## Characterisation check`, `## Later citations` (`grep -c` of each name is at least 1).
3. `cited_keys_total` equals `cited_keys_verified`, and equals the `cited=` value printed by `python3 tools/check_bib.py --src docs/related-work/related-work-draft.tex` run after the citations listed under `## Dropped citations` were removed.
4. `python3 tools/check_bib.py --src docs/related-work/related-work-draft.tex` exits 0 (no `UNVERIFIED`, `MISSING` or `INCOMPLETE` line). If `paper/` already contains `.tex` files that cite keys, `python3 tools/check_bib.py` (default source `paper`) exits 0 as well.
5. `python3 tools/check_bib.py --schema` exits 0 (structure intact, no `INCOMPLETE` for any entry with `verified = {true}`).
6. Every cited key that was `uncertain = {true}` before this task appears either in `## Corrections` or in `## Confirmed without change`; every cited key that was `ref_status = {partial}` has all fields required for `verified = {true}` (`author`, `title`, `year`, a venue field), which check 5 enforces.
7. `## Characterisation check` has one row for each of the four paragraphs and a row for Lindemann et al. (key `lindemann-conformal-stl`) that states the statement checked (dense predicted trajectories; no attribution; how conformal prediction enters), the section of the paper where it was confirmed or refuted, and the result (`agrees` or `edited`).
8. `## Unresolved items` has one row each for Moxi (commercial ward robots), SCIFF (specific work), Breach and S-TaLiRo (tool references), and for every cited `partial` entry, each with a disposition (`entry completed and verified`, `not cited`, or `citation dropped`).
9. No key listed under `## Dropped citations` still occurs in the draft: `grep -c '<key>' docs/related-work/related-work-draft.tex` prints 0 for each.

## Passi

1. Open `docs/related-work/citation-selection.md`. Take the cited keys in the order of "Handover to T06": first those with `uncertain = {true}`, then `partial`, then the rest.
2. For each key, find the publication on DBLP or Google Scholar using the recorded authors, venue and `topic` (the agent left out first names, full titles and pages on purpose). For a conference and extended version pair, confirm that the cited version is the one intended.
3. Compare authors, year and venue with the source. Correct the entry and complete it: full author names, full title, `booktitle` or `journal` in full, year, optionally volume, pages, DOI. Keep the key unchanged. Change the entry type if the venue requires it.
4. Set `verified = {true}`, `verified_by`, `verified_on` (`YYYY-MM-DD`) and `verified_via`. If the dagger doubt is resolved, set `uncertain = {false}`. Record every changed field in `verify_notes` and in the `## Corrections` table (key, field, recorded value, verified value, reason).
5. If a work cannot be found, or differs materially from the recorded data or the topic, leave `verified = {false}`, remove its `\cite` from the draft, adapt the sentence (or ask for a rewrite of that paragraph), and list the key under `## Dropped citations` with the reason and the edit.
6. Characterisation check. Read the abstract and introduction of each work whose behavior is characterized in a difference sentence, at least: Lindemann et al., ICCPS 2023 (the sentence says the contrast is to conformal STL runtime verification on dense predicted trajectories, against sparse event-driven samples; confirm this, and that the work has neither a measured-versus-predicted verdict separation nor cause attribution); Asbru (temporal conditions monitorable at execution time, paragraph 3); the design-time verification works cited in paragraph 4. Edit the draft wherever the text says more than the source supports. Record each check.
7. Unresolved items. Moxi: look for peer-reviewed studies of commercial ward robots; if one exists, add an entry with all fields and `verified = {true}` and decide whether to cite it, otherwise record `not cited`. SCIFF: pick the specific work of the Chesani, Mello, Montali line if you want to cite it (add the entry with key `chesani-sciff-conformance`), otherwise record `not cited`. Breach and S-TaLiRo: locate the reference for each tool and complete the entries, otherwise drop the two `\cite` commands and keep the tool names in the text. Cited `partial` standards (for example FHIR): complete year, edition or URL.
8. Uncited entries: verify as many as time allows and count them; the others stay `verified = {false}` and uncited. Do not delete them, later sections may cite them.
9. Run the commands of checks 4 and 5 and paste their output into the artefact under `## Later citations`, with one line stating that any key cited later by other sections (WS12) must be verified before WS12-T08, and that `python3 tools/check_bib.py` is the gate.
10. Write `docs/plan/workstreams/WS03-related-work/outputs/WS03-T06.md` with the header lines and sections of check 2, set `status: done` in this file and commit with message `WS03-T06: verify cited references`.

## Done when

- `docs/plan/workstreams/WS03-related-work/outputs/WS03-T06.md` exists with the fields `verifier`, `date`, `sources_used`, `bib_file`, `draft_file`, `cited_keys_total`, `cited_keys_verified` (equal to the total), `check_bib_exit_code` (value 0), `uncited_entries_verified`, `uncited_entries_left_unverified`, and the sections `## Corrections`, `## Confirmed without change`, `## Dropped citations`, `## Unresolved items`, `## Characterisation check`, `## Later citations`.
- `python3 tools/check_bib.py --src docs/related-work/related-work-draft.tex` exits 0.
