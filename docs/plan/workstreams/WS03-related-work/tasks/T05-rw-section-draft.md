---
id: WS03-T05
title: Related Work section draft (four paragraphs with difference sentences)
workstream: WS03-related-work
owner: agent
status: blocked
depends_on: ["WS03-T01", "WS03-T02", "WS03-T03", "WS03-T04"]
critical_path: false
non_negotiable: false
estimate_pd: 1
sources: ["analisi §3.7", "analisi §7", "analisi §4.8", "analisi §10 (2)"]
interfaces: []
review_items: ["AE-3"]
---
## Obiettivo

Merge the three bibliography fragments into `paper/refs/references.bib` (85 entries, all `verified = {false}`) and write the Related Work draft `docs/related-work/related-work-draft.tex`: four dense paragraphs of about 0.45 page in total (analisi §7), one per strand, each closed by a difference sentence, with the precise difference to Lindemann et al., ICCPS 2023 in the second. Also write `docs/related-work/citation-selection.md`, the record of which keys are cited, in which paragraph, with which risk flags, so that the human can verify them in WS03-T06.

## Contesto

- Blocked until WS03-T01 (tool `tools/check_bib.py` and header-only `paper/refs/references.bib`), WS03-T02, T03 and T04 (fragments `paper/refs/fragments/ws03-t0{2,3,4}.bib` and the six notes) are `done`. Start by checking that all of them exist.
- `docs/related-work/*.md` (the six notes of T02 to T04: reference tables, difference sentences, risk handling) and `docs/plan/workstreams/WS03-related-work/README.md` (schema, caps, spelling rule).
- `docs/source/analisi.md` §3.7 (defensible novelty claim) and §7 (Related Work row: four paragraphs, 0.45 page, each closed by a difference sentence; References row: 30 to 35 entries in the whole paper).
- `docs/source/analisi.md` §4.8 (claim wording) and `docs/plan/01-conventions.md` section 7 (binding glossary).
- `docs/plan/03-decisions.md` ADR-018 (agents assemble entries with `verified = {false}`; a human verifies).

## File toccati

1. `paper/refs/references.bib` (modify)
2. `paper/refs/fragments/` (modify: the three fragments are merged, then the directory is removed so that `references.bib` is the single source)
3. `docs/related-work/related-work-draft.tex` (create)
4. `docs/related-work/citation-selection.md` (create)

## Test

Verification checks (paths relative to the repository root). The word and key caps are working estimates: about 1000 words fit a two-column RA-L page (assumption, unverified), so 0.45 page is about 450 to 500 words; the whole paper carries 30 to 35 references (analisi §7). WS12-T02 fixes the real budget and WS12-T08 confirms it by compiling; the selection note keeps a trim order so that the draft can shrink without rework.

1. Preconditions: `test -f tools/check_bib.py`, the three fragments and the six notes exist. If not, stop: the task is still blocked.
2. Merge: `grep -c '^@' paper/refs/references.bib` prints 85; `python3 tools/check_bib.py --schema` exits 0 and prints `entries=85 ... duplicate=0 invalid=0 status=OK`; `grep -c 'verified *= *{false}'` prints 85 and `grep -c 'verified *= *{true}'` prints 0; `grep -c 'uncertain *= *{true}'` prints 35; `grep -c 'ref_status *= *{partial}'` prints 10; `grep -c '^ *title *='` prints 20; `test ! -e paper/refs/fragments` succeeds.
3. Structure of the draft: `grep -c '^%P[1-4]$' docs/related-work/related-work-draft.tex` prints 4 and `grep -c '^%DIFF$'` prints 4; `grep -n '^%P[1-4]$\|^%DIFF$'` lists them in the order `%P1 %DIFF %P2 %DIFF %P3 %DIFF %P4 %DIFF`; the file contains no `\section` command.
4. Topics in analisi §7 order: P1 STL runtime monitoring and RV in robotics; P2 conformal and predictive monitoring; P3 guideline formalization and medical CPS; P4 robots in healthcare and device security. The marker line carries no text; the topic is stated in the first sentence of each paragraph.
5. Length: `grep -v '^%' docs/related-work/related-work-draft.tex | sed -E 's/\\cite[a-z]*(\[[^]]*\])*\{[^}]*\}//g' | wc -w` prints a number at most 500.
6. Citations resolve: `python3 tools/check_bib.py --src docs/related-work/related-work-draft.tex` prints a summary with `missing=0` and `cited=N` where N is at most 25 (working allocation: P1 at most 8, P2 at most 7, P3 at most 6, P4 at most 4). The exit code is 1 at this stage, because every cited entry is still unverified; record it in the completion note, this is the expected state until WS03-T06.
7. Must-cite keys (each required by analisi) appear in the draft:
   ```
   for k in lindemann-conformal-stl lindemann-safe-planning cairoli-conformal-quantitative-monitoring nickovic-yamaguchi-rtamt breach-tool staliro-tool fainekos-pappas-robustness donze-maler-robust shahar-miksch-johnson-asbru wong-sepsis-external-validation; do echo "$k $(grep -c "$k" docs/related-work/related-work-draft.tex)"; done
   ```
   prints a count of at least 1 for every key. In addition at least one of `bortolussi-neural-predictive-monitoring-conf` or `-ext`, at least one of `huang-rosrv` or `ferrando-rosmonitoring` (R1-W10: RV for ROS) and at least one of `deshmukh-online-monitoring-conf` or `-ext` appear. At most one version of each conf and ext pair (Deshmukh, Bortolussi, Gombolay) is cited.
8. Unresolved items are not cited or named: `grep -i -c -E 'moxi|sciff|chesani' docs/related-work/related-work-draft.tex` prints 0.
9. Difference sentences: `awk '/^%DIFF$/{f=1;next} /^$/{f=0} f' docs/related-work/related-work-draft.tex` prints four sentences, one per paragraph, each at most 70 words (`awk '/^%DIFF$/{f=1;n++;next} /^$/{f=0} f{w[n]+=NF} END{for(i=1;i<=n;i++) print i, w[i]}' docs/related-work/related-work-draft.tex` prints four counts, none above 70). The second contains, case-insensitively, `lindemann-conformal-stl`, `sparse`, `event-driven`, `PENDING`, `measured`, `normali[sz]ed`, `mixed units` and `abstain`. The first contains `algorithm` and `care plan`; the third contains `offline`, `discrete events`, `online`, `robustness` and `cause`; the fourth contains `runtime`, `evidence`, `cross-modal`, `integrity` and `attack classes`.
10. Claim wording and glossary: `grep -n -i -E 'ensure[s]|intrinsic explainab|orthogona[l]|distribution-fre[e]|first to|we are the first|\bnovel\b|sub[s]ystem|edge clo[u]d|embodied A[I]|Physical A[I]|smart-medic[a]l' docs/related-work/related-work-draft.tex` prints nothing (the word "novelty" in the clause that disclaims novelty for guidelines as monitorable specifications is allowed). Inspection: "robust" or "robustness" appears only for STL semantics or inside the name of a cited work; "violation" is not used for a device fault; the outputs are called "alerts".
11. Description fidelity (inspection): for five cited keys chosen by the reviewer, the property that the draft attributes to the work appears in that key's `topic` field or in the role column of its note table; nothing is stated about a cited work that is not in the notes.
12. Selection note: `docs/related-work/citation-selection.md` has exactly the headings `## Budget`, `## Cited keys`, `## Not cited`, `## Trim order`, `## Handover to T06` (`grep -c '^## '` prints 5); the table under "Cited keys" has one row per distinct cited key (rows start with the key in backticks; the row count equals `N` of check 6) with columns key, paragraph, role, `uncertain`, `ref_status`, conditional (yes for `breach-tool` and `staliro-tool`).
13. Regression: `python3 -m pytest tests/tools -q` still exits 0 (test 22 of WS03-T01 now runs on real entries).
14. Forbidden tokens: `grep -n -E 'T[O]DO|T[B]D|[?]{3}|lor[e]m'` on the draft and the selection note prints nothing.

## Passi

1. Run check 1. Run `python3 tools/check_bib.py --schema --bib paper/refs/fragments/ws03-t02.bib` (and t03, t04); each exits 0 with entries 32, 31, 22.
2. Merge: append the three fragments to `paper/refs/references.bib` below its header, in the order T02, T03, T04, each preceded by a banner comment naming the task. Run `python3 tools/check_bib.py --schema`; fix any duplicate key by keeping the entry of the task whose analisi section lists it (README, "Key naming") and turning the other into a citation by key. Remove `paper/refs/fragments/` (its content stays in git history). Run check 2.
3. Choose the cited set and write `citation-selection.md`. Rules, in order:
   - the must-cite keys of check 7;
   - for every other role (for example three-valued semantics, survey, adaptive conformal inference, non-exchangeability, medical STL monitoring, alarm fatigue, healthcare-robotics overview, design-time verification of care robots, attacks on devices, physical-invariant detection, standards) pick the entry that serves it best, preferring `uncertain = {false}` over `{true}` and `ref_status = {recalled}` over `{partial}`; a daggered or partial entry is chosen only when no other entry serves the role or when analisi names it as required (the Bortolussi and Cairoli line, §10 objection 2; the RV-for-ROS works, R1-W10);
   - never cite the unresolved items (Moxi, SCIFF);
   - obey the working allocation: P1 at most 8, P2 at most 7, P3 at most 6, P4 at most 4 distinct keys; the three standards ISO 13482, ISO 14971 and IEC 62304 and the FDA guidance are left to the hazard paragraph (WS02-T05, Discussion) unless a clause fits;
   - Breach and S-TaLiRo are cited but flagged conditional: their entries are `partial` and have no citation data in analisi; if the human cannot complete them in T06, the two `\cite` commands are dropped and the tool names stay in the text.
   Fill `## Budget` (caps and their derivation as stated under "Test"), `## Cited keys` (table of check 12), `## Not cited` (all other entries stay in `references.bib` for later sections; list the unchosen version of each conf and ext pair with the reason, and the unresolved items), `## Trim order` (numbered list of cited keys to drop first if WS12-T08 shows the section exceeds 0.45 page, lowest priority first, never a must-cite key) and `## Handover to T06` (cited keys grouped by verification priority: first `uncertain = {true}`, then `partial`, then the rest).
4. Write the draft in `docs/related-work/related-work-draft.tex`. Header: two comment lines (task id; "body only, WS12-T06 inserts it under the Related Work section; all citations unverified until WS03-T06"). Each paragraph is: marker line `%P<n>`, the paragraph text, marker line `%DIFF`, the difference sentence (no blank line between the text and the marker, so LaTeX sees one paragraph), blank line. Use `\cite{key1,key2}` (natbib-compatible), `$\tilde{\sigma}$` for normalized robustness when needed, American spelling as in analisi §6. Content per paragraph:
   - P1 (from `stl-rv-robotics.md`): robust semantics and time robustness, monitoring algorithms and online monitoring on partial traces, three-valued semantics, tools (RTAMT, Breach, S-TaLiRo), runtime verification for ROS. R1-W10: state no complexity bound. Difference sentence: the P1 sentence of the note, opening with "Our contribution is not the monitoring algorithm".
   - P2 (from `conformal-predictive-monitoring.md`): the closest work and the Bortolussi and Cairoli predictive-monitoring line described only by their recorded topics, robust conformal prediction under distribution shift, conformal prediction in robotics (RA-L), conformal prediction beyond exchangeability and adaptive variants, with a clause that the adaptive variant is evaluated under shift in this work. Difference sentence: the binding Lindemann sentence of T02 (shortened at most to 70 words, all four elements kept).
   - P3 (from the two notes of T03): medical CPS and specification-based monitoring in medicine, motivation from the limits of opaque deterioration models and from alarm fatigue, guideline formalisms with Asbru named as already monitorable at execution time, process mining and conformance, FHIR as target standard. One clause states that the paper does not claim novelty for treating guidelines as monitorable specifications. If WS01-T07 has produced its FHIR or BPMN mapping sketch, add one clause pointing to it; otherwise omit. Difference sentence: the paragraph-3 sentence of the T03 notes.
   - P4 (from the two notes of T04): healthcare robotics overview, design-time verification of care robots, attacks on medical devices, detection with physical or physiological invariants. The C3 scope is stated as integrity or plausibility violations against declared attack classes (ADR-002). Difference sentence: the paragraph-4 sentence of the T04 notes.
5. Trim: run checks 5 and 6; cut lowest-value clauses (not the difference sentences) until both pass. Update the selection note to match the final cited keys.
6. Claims and glossary pass: run checks 8, 10 and 11; rewrite any sentence that describes a cited work beyond what the notes record. Use "care plan" and "patient care plan" for this work's objects and "Clinical Pathway" only for the institutional concept.
7. Run every check, save the outputs of checks 2, 5, 6 and 9 in the completion note, commit with message `WS03-T05: merge bibliography and draft Related Work section`, and set `status: done` in this file. WS03-T06 is unblocked.

## Done when

- `python3 tools/check_bib.py --schema` exits 0 and prints `entries=85`.
- `python3 tools/check_bib.py --src docs/related-work/related-work-draft.tex` prints `missing=0` and `cited=N` with N at most 25 (exit code 1 is expected: cited entries are unverified until WS03-T06).
- `grep -v '^%' docs/related-work/related-work-draft.tex | sed -E 's/\\cite[a-z]*(\[[^]]*\])*\{[^}]*\}//g' | wc -w` prints at most 500; `grep -c '^%DIFF$' docs/related-work/related-work-draft.tex` prints 4.
- `python3 -m pytest tests/tools -q` exits 0 and `test -f docs/related-work/citation-selection.md` succeeds.
