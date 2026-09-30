---
id: WS03-T02
title: "Related work: STL runtime monitoring, RV in robotics, conformal and predictive monitoring"
workstream: WS03-related-work
owner: agent
status: in_progress
depends_on: []
critical_path: false
non_negotiable: false
estimate_pd: 2
sources: ["analisi §3.1", "analisi §3.2", "analisi §10 (2)", "analisi §5.4 (B5)", "analisi §2 R1 weakness 10"]
interfaces: []
review_items: ["R1-W10", "AE-3"]
---
## Obiettivo

Transcribe the reference lists of analisi §3.1 (STL runtime monitoring and RV in robotics) and §3.2 (conformal and predictive monitoring) into a bibliography fragment of 32 entries, all `verified = {false}` (ADR-018), and into two notes that give the difference of this work to each strand. The conformal note must contain the precise difference sentence with respect to Lindemann et al., ICCPS 2023 (sparse event-driven sampling, formal separation of measured and predicted verdict, normalized severity over mixed units, attribution with abstention; analisi §3.2, §10 objection 2). The STL note must also close reviewer finding R1-W10 (tools, complexity, RV for ROS).

## Contesto

- `docs/plan/workstreams/WS03-related-work/README.md` (entry schema, key naming, expected counts).
- `docs/source/analisi.md` §3.1 and §3.2 (the reference lists and the "Differenza" paragraphs), plus §3 note on daggers.
- `docs/source/analisi.md` §10 objection 2 and §5.4 (B5, "where it fails"); `docs/source/review.md` R1 weakness 10 and meta-review item 3.
- `docs/plan/03-decisions.md` ADR-008 (three-valued verdicts, conformal prediction only in PENDING), ADR-009 (normalisation), ADR-010 (attribution with abstention), ADR-007 and ADR-013 (alternatives named in §3.1).
- `docs/plan/01-conventions.md` section 7 (glossary).

## File toccati

1. `paper/refs/fragments/ws03-t02.bib` (create)
2. `docs/related-work/stl-rv-robotics.md` (create)
3. `docs/related-work/conformal-predictive-monitoring.md` (create)

## Test

Verification checks (a reviewer can run each; paths relative to the repository root).

1. Files exist: `test -f paper/refs/fragments/ws03-t02.bib && test -f docs/related-work/stl-rv-robotics.md && test -f docs/related-work/conformal-predictive-monitoring.md`.
2. Entry count and unique keys: `grep -c '^@' paper/refs/fragments/ws03-t02.bib` prints 32; `grep -o '^@[a-z]*{[^,]*' paper/refs/fragments/ws03-t02.bib | sort | uniq -d` prints nothing.
3. Nothing verified: `grep -c 'verified *= *{false}' paper/refs/fragments/ws03-t02.bib` prints 32 and `grep -c 'verified *= *{true}'` prints 0.
4. Mandatory custom fields on every entry:
   ```
   for f in verified uncertain ref_status analisi task topic; do grep -c "^ *$f *=" paper/refs/fragments/ws03-t02.bib; done
   ```
   prints six lines, each 32.
5. Transcription fidelity: `grep -c 'uncertain *= *{true}'` prints 10; `grep -c 'ref_status *= *{partial}'` prints 3; `grep -c '^ *title *='` prints 7 (no title is added beyond the table below).
6. Dagger keys are exactly the ten of the table:
   ```
   awk '/^@/{k=$0} /uncertain *= *\{true\}/{print k}' paper/refs/fragments/ws03-t02.bib | sed 's/^@[a-z]*{//; s/,$//' | LC_ALL=C sort
   ```
   prints, in this order: `bortolussi-neural-predictive-monitoring-conf`, `bortolussi-neural-predictive-monitoring-ext`, `brim-stl-star`, `cairoli-conformal-quantitative-monitoring`, `ferrando-rosmonitoring`, `huang-rosrv`, `mehdipour-agm-robustness`, `mehdipour-weighted-stl`, `rodionova-time-robustness`, `zhao-robust-conformal-stl`.
7. Note tables match the fragment: ``grep -c '^| `' docs/related-work/stl-rv-robotics.md`` prints 21 and the same command on `conformal-predictive-monitoring.md` prints 11 (no other table row in a note starts with a backtick); the set of keys in the two tables equals the set of keys in the fragment (`diff` of the two sorted key lists is empty).
8. Each note has exactly six second-level headings: `grep -c '^## ' <note>` prints 6, and they are `## Scope`, `## Reference table`, `## What the reviewer expects`, `## Difference`, `## Risk and handling in the text`, `## Unresolved and for human verification`.
9. Lindemann difference sentence: extract the section (`awk '/^## Difference/{f=1;next}/^## /{f=0}f' docs/related-work/conformal-predictive-monitoring.md`); it contains, case-insensitively, `sparse`, `event-driven`, `PENDING`, `measured`, `normali[sz]ed`, `mixed units`, `abstain` and the key `lindemann-conformal-stl`.
10. R1-W10 coverage: `docs/related-work/stl-rv-robotics.md` contains `RTAMT`, `Breach`, `S-TaLiRo`, `ROSRV`, `ROSMonitoring` and `complexity`; the complexity remark says that no complexity bound is stated in the related work and points to WS05-T04 (per-sample complexity, analisi §4.7).
11. If `tools/check_bib.py` exists (WS03-T01 merged): `python3 tools/check_bib.py --schema --bib paper/refs/fragments/ws03-t02.bib` exits 0 and prints `entries=32`.
12. Forbidden tokens: `grep -n -E 'T[O]DO|T[B]D|[?]{3}|lor[e]m'` on the three files prints nothing.

## Passi

Inventory (binding; transcribed from analisi, nothing added). Columns: `type` (inp `@inproceedings`, art `@article`, inc `@incollection`, misc `@misc`); `author` is the exact `author` field (surnames only); `-` means the field is omitted; `title` only where analisi quotes a title or where the name is the only identity of the item; `†` is `uncertain = {true}`; `status` is `ref_status`. The `analisi` field is `{3.1}` or `{3.2}` as the section of the note, except rows 1, 20 and 21.

Analisi §3.1 (note `stl-rv-robotics.md`, 21 rows):

| # | key | type | author | year | venue | title | † | status | topic |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `maler-nickovic-stl` | misc | Maler and Ni{\v c}kovi{\'c} | 2004 | - | - | no | recalled | original STL definition with Boolean semantics; `analisi = {2 (R1 weakness 2)}` |
| 2 | `fainekos-pappas-robustness` | art | Fainekos and Pappas | 2009 | Theoretical Computer Science | - | no | recalled | robust semantics of temporal logic |
| 3 | `donze-maler-robust` | inp | Donz{\'e} and Maler | 2010 | FORMATS | - | no | recalled | robust semantics; time robustness also appears here |
| 4 | `donze-ferrere-maler-monitoring` | inp | Donz{\'e} and Ferr{\`e}re and Maler | 2013 | CAV | - | no | recalled | monitoring algorithms |
| 5 | `deshmukh-online-monitoring-conf` | inp | Deshmukh and others | 2015 | RV | - | no | recalled | online monitoring with robustness intervals on partial traces (conference version) |
| 6 | `deshmukh-online-monitoring-ext` | art | Deshmukh and others | 2017 | Formal Methods in System Design | - | no | recalled | extended version of the RV 2015 work |
| 7 | `bartocci-spec-monitoring-survey` | inc | Bartocci and others | 2018 | booktitle Lectures on Runtime Verification, series LNCS, volume 10457 | Specification-based monitoring of cyber-physical systems | no | recalled | survey |
| 8 | `leucker-schallhart-rv-survey` | art | Leucker and Schallhart | 2009 | JLAP | - | no | recalled | survey |
| 9 | `bauer-leucker-schallhart-three-valued` | art | Bauer and Leucker and Schallhart | 2011 | ACM TOSEM | - | no | recalled | three-valued semantics |
| 10 | `nickovic-yamaguchi-rtamt` | inp | Ni{\v c}kovi{\'c} and Yamaguchi | 2020 | ATVA | - | no | recalled | RTAMT tool |
| 11 | `huang-rosrv` | inp | Huang and others | 2014 | SIMPAR | - | yes | recalled | ROSRV, runtime verification for ROS |
| 12 | `ferrando-rosmonitoring` | inp | Ferrando and others | 2020 | TAROS | - | yes | recalled | ROSMonitoring, runtime verification for ROS |
| 13 | `luckcuck-formal-robotics-survey` | art | Luckcuck and others | 2019 | ACM Computing Surveys | - | no | recalled | survey of formal verification in robotics |
| 14 | `desai-soter` | inp | Desai and others | 2019 | DSN | - | no | recalled | SOTER, runtime assurance |
| 15 | `sha-simplex` | misc | Sha | 2001 | - | - | no | recalled | Simplex architecture |
| 16 | `mehdipour-agm-robustness` | inp | Mehdipour and Vasile and Belta | 2019 | CDC | - | yes | recalled | AGM robustness (normalisation alternative, ADR-009) |
| 17 | `mehdipour-weighted-stl` | misc | Mehdipour and Vasile and Belta | - | - | - | yes | partial | weighted STL, same authors as row 16; year and venue not given in analisi |
| 18 | `brim-stl-star` | art | Brim and others | 2014 | Information and Computation | - | yes | recalled | STL* freeze operator (alternative to derived signals, ADR-007) |
| 19 | `rodionova-time-robustness` | inp | Rodionova and others | 2021 | CDC | - | yes | recalled | time robustness for control |
| 20 | `breach-tool` | misc | - | - | - | Breach | no | partial | STL tool named in R1 weakness 10 and ADR-013; no citation data in analisi; `analisi = {2 (R1 weakness 10)}` |
| 21 | `staliro-tool` | misc | - | - | - | S-TaLiRo | no | partial | STL tool named in R1 weakness 10 and ADR-013; no citation data in analisi; `analisi = {2 (R1 weakness 10)}` |

Analisi §3.2 (note `conformal-predictive-monitoring.md`, 11 rows):

| # | key | type | author | year | venue | title | † | status | topic |
|---|---|---|---|---|---|---|---|---|---|
| 22 | `lindemann-conformal-stl` | inp | Lindemann and Qin and Deshmukh and Pappas | 2023 | ICCPS | Conformal prediction for {STL} runtime verification | no | recalled | closest work; baseline B5 (WS06-T06) |
| 23 | `bortolussi-neural-predictive-monitoring-conf` | inp | Bortolussi and Cairoli and Paoletti and others | 2019 | RV | Neural predictive monitoring | yes | recalled | predictive monitoring (conference version) |
| 24 | `bortolussi-neural-predictive-monitoring-ext` | art | Bortolussi and Cairoli and Paoletti and others | - | STTT | - | yes | recalled | extended version of row 23 |
| 25 | `cairoli-conformal-quantitative-monitoring` | inp | Cairoli and Paoletti and Bortolussi | 2023 | HSCC | - | yes | recalled | conformal quantitative predictive monitoring of STL requirements |
| 26 | `zhao-robust-conformal-stl` | inp | Zhao and Hoxha and Fainekos and Deshmukh and Lindemann | 2024 | ICCPS | - | yes | recalled | robust conformal prediction for STL runtime verification under distribution shift |
| 27 | `lindemann-safe-planning` | art | Lindemann and others | 2023 | IEEE RA-L | Safe planning in dynamic environments using conformal prediction | no | recalled | conformal prediction in robotics; must be cited because it appeared in RA-L |
| 28 | `stankeviciute-conformal-time-series` | inp | Stankeviciute and Alaa and van der Schaar | 2021 | NeurIPS | - | no | recalled | conformal prediction for time series |
| 29 | `xu-xie-enbpi` | inp | Xu and Xie | 2021 | ICML | - | no | recalled | EnbPI, conformal prediction for time series |
| 30 | `gibbs-candes-adaptive-conformal` | inp | Gibbs and Cand{\`e}s | 2021 | NeurIPS | - | no | recalled | adaptive conformal inference under non-exchangeability |
| 31 | `barber-beyond-exchangeability` | art | Barber and Cand{\`e}s and Ramdas and Tibshirani | 2023 | Annals of Statistics | Conformal prediction beyond exchangeability | no | recalled | non-exchangeability |
| 32 | `angelopoulos-conformal-pid` | inp | Angelopoulos and Cand{\`e}s and Tibshirani | 2023 | NeurIPS | - | no | recalled | conformal PID control |

Steps.

1. Create `paper/refs/fragments/ws03-t02.bib` with a two-line comment header (task id, "merged into references.bib by WS03-T05").
2. Write one entry per inventory row, in table order, with exactly the fields of the row plus `verified = {false}`, `uncertain`, `ref_status`, `analisi`, `task = {WS03-T02}`, `topic` (schema in the README). Use the accents shown in the table. Run checks 2 to 6 and fix.
3. Create `docs/related-work/stl-rv-robotics.md` with the six headings of check 8.
   - `## Scope`: analisi §3.1, the three extra items (Maler and Nickovic, Breach, S-TaLiRo) and why they are there (R1 weakness 2 and 10).
   - `## Reference table`: one row per row 1 to 21 with columns key, authors as recalled, year, venue, dagger, ref_status, role in the text (from the topic column; use words such as "robust semantics", "algorithm", "online monitoring", "survey", "three-valued", "tool", "RV in ROS", "formal verification", "runtime assurance", "normalisation alternative", "freeze alternative", "time robustness"). Each row starts with the key in backticks so that check 7 counts it.
   - `## What the reviewer expects`: English summary of the analisi bullets, grouped by role, with the daggers kept.
   - `## Difference`: the three things analisi says the contribution can be (specification class from care plans over sparse, irregular, mixed continuous and event signals; severity normalized with clinical scales; coupling of the clinical specification with the robot's tasks), then one sentence of at most 70 words for paragraph 1 that opens with "Our contribution is not the monitoring algorithm" and lists the three things, using glossary terms ("care plan", "assistive robot").
   - `## Risk and handling in the text`: analisi rates the risk "ALTO" if the claim stays "we use robust STL for runtime safety"; the text must never present the monitoring algorithm as the contribution. R1-W10: name RTAMT, Breach and S-TaLiRo as tools (Breach and S-TaLiRo have no reference in analisi, so their `.bib` entries are `partial` and T06 must complete them or T05's citations of them are dropped); cite at least one RV-for-ROS work (ROSRV or ROSMonitoring, both daggered); complexity: analisi asks for complexity per sample (§4.7) but §3.1 gives no reference for it; the related work states no complexity bound, and the statement belongs to WS05-T04 and WS01-T05.
   - `## Unresolved and for human verification`: the six daggered entries of §3.1, the `partial` entries (rows 17, 20, 21), the two-version pair Deshmukh (which one to cite is decided in T05), and Sha (no venue in analisi).
4. Create `docs/related-work/conformal-predictive-monitoring.md` with the same six headings.
   - `## Scope`: analisi §3.2, closest-work status of Lindemann et al., link to B5.
   - `## Reference table`: rows 22 to 32 in the same format.
   - `## What the reviewer expects`: the analisi bullets (closest work; predictive monitoring; distribution shift; conformal in robotics, to be cited because it is in RA-L; time series; non-exchangeability), and the analisi warning that the workshop abstract sentence "combines temporal prediction, uncertainty-aware reasoning, and constraint-based verification" describes almost exactly Lindemann et al. 2023.
   - `## Difference`: (a) the four analisi §3.2 candidates (sparse event-driven sampling; explicit separation of measured and predictive verdict; calibration per patient episode with an adaptive variant for the single patient; integration with cause attribution); (b) the four elements prescribed by analisi §10 objection 2, which are the ones used in the sentence below (the §3.2 item on per-episode calibration with an adaptive variant is kept for the preceding sentences of paragraph 2, where Gibbs and Candes and Barber et al. are cited; normalized severity is added by §10); (c) the traceability table, one row per element with the plan artefact that realizes it (sparse event-driven sampling: WS01-T01 sampling semantics; formal separation: WS01-T05 and WS01-T06, ADR-008; normalized severity over mixed units: WS01-T04, ADR-009; attribution with abstention: WS02-T04, ADR-010) and the place where it is tested against the closest work (B5, WS06-T06; analisi §5.4: sparse sampling, mixed units, no attribution); (d) the binding sentence:

   > Unlike conformal STL runtime verification on dense predicted trajectories \cite{lindemann-conformal-stl}, our monitor works on sparse, event-driven samples; it separates formally the verdict on measured data from the predictive verdict, confining conformal prediction to the PENDING state; it ranks alerts by a clinically normalized severity over mixed units; and it attributes each alert to a cause, or abstains (UNDETERMINED).

   The sentence may be shortened by WS03-T05 but must keep the four elements, the key `lindemann-conformal-stl`, and the hedge that the characterization "dense predicted trajectories" comes from analisi §3.2 and is checked against the paper by the human in T06.
   - `## Risk and handling in the text`: analisi rates this "MOLTO ALTO" (a reject for lack of novelty becomes likely if Lindemann et al. is neither cited nor used as a baseline). Handling: cite it explicitly, cite the Bortolussi and Cairoli line, use it as B5, and present Proposition 1 as small but new in the three-valued setting without inflating it (analisi §10 objection 2). Make no priority or novelty claim ("first", "novel") and do not use the unqualified coverage phrase that analisi §4.8 replaces; coverage is marginal and needs exchangeability across patient episodes. Describe the Bortolussi and Cairoli works only by the topic recorded in the table.
   - `## Unresolved and for human verification`: the four daggered entries (rows 23 to 26), the Bortolussi pair (which version to cite), and the mandatory T06 check that the description of Lindemann et al. in the sentence matches the paper.
5. Run every check under "Test" and fix. Commit with message `WS03-T02: assemble STL and conformal related-work notes and bib fragment`; set `status: done` in this file.

## Done when

- The twelve checks under "Test" pass; the completion note pastes the output of checks 2 to 7 and 11 (if the tool exists).
- `grep -c '^@' paper/refs/fragments/ws03-t02.bib` prints 32 and `grep -c 'verified *= *{true}' paper/refs/fragments/ws03-t02.bib` prints 0.
- `docs/related-work/conformal-predictive-monitoring.md` contains the sentence of step 4(d) (or a shortened one that passes check 9).

## Notes

Completion note (WS03-T02, worker run on branch `ws03-t02-rw-stl-conformal`; status left `in_progress` for the orchestrator after review).

Red state: before the artefacts existed, check 1 exited 1 and checks 2 to 11 failed with "No such file or directory" (no red commit, none prescribed).

Inventory versus analisi: all 32 rows were compared with analisi 3.1, 3.2 and 2 (R1 weaknesses 2 and 10). Every author, year and venue matches analisi; no unsupported row. Points worth a look: rows 1, 20 and 21 come from the reviewer text (`analisi = {2 (...)}`), as the task prescribes; the accents in `Ni{\v c}kovi{\'c}` for row 1 follow the task table (analisi writes "Nickovic" in R1 weakness 2 and "Ni{\v c}kovi{\'c}" in 3.1); row 24 has no year because analisi gives none; the dagger of the Bortolussi line covers both versions (README rule). Counts: daggers 6 (3.1) + 4 (3.2) = 10, partial 3, titles 7.

Real output of the checks (script kept outside the repository, `/tmp/t02_checks.sh`, run from the repository root):

```
== check1
exit=0
== check2
32
dups-above (none expected)
== check3
32
0
== check4
32
32
32
32
32
32
== check5
10
3
7
== check6
bortolussi-neural-predictive-monitoring-conf
bortolussi-neural-predictive-monitoring-ext
brim-stl-star
cairoli-conformal-quantitative-monitoring
ferrando-rosmonitoring
huang-rosrv
mehdipour-agm-robustness
mehdipour-weighted-stl
rodionova-time-robustness
zhao-robust-conformal-stl
== check7
21
11
keysets equal
== check8
6
## Scope
## Reference table
## What the reviewer expects
## Difference
## Risk and handling in the text
## Unresolved and for human verification
6
## Scope
## Reference table
## What the reviewer expects
## Difference
## Risk and handling in the text
## Unresolved and for human verification
== check9
sparse: 4
event-driven: 4
PENDING: 2
measured: 4
normali[sz]ed: 3
mixed units: 3
abstain: 1
lindemann-conformal-stl: 2
== check10
RTAMT: 5
Breach: 4
S-TaLiRo: 4
ROSRV: 3
ROSMonitoring: 3
complexity: 2
WS05-T04: 1
== check11
entries=32 cited=0 unverified=0 missing=0 incomplete=0 duplicate=0 invalid=0 status=OK
exit=0
== check12
grep exit=1 (1 = nothing found)
```

Full suite and plan checks:

```
pytest -q                     -> 175 passed in 0.87s (exit 0)
python3 tools/check_plan.py   -> check_plan: OK (103 tasks, 18 contracts, 31 findings) (exit 0)
python3 tools/check_bib.py --schema --bib paper/refs/fragments/ws03-t02.bib --bib paper/refs/fragments/ws03-t03.bib --bib paper/refs/fragments/ws03-t04.bib
                              -> entries=85 ... duplicate=0 invalid=0 status=OK (exit 0; no key clash across fragments)
```
