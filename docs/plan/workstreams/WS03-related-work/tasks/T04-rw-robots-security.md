---
id: WS03-T04
title: "Related work: assistive ward robots and wearable-device security"
workstream: WS03-related-work
owner: agent
status: ready
depends_on: []
critical_path: false
non_negotiable: false
estimate_pd: 1.5
sources: ["analisi §3.5", "analisi §3.6", "analisi §10 (3)", "analisi §10 (fourth objection, C3)"]
interfaces: []
review_items: ["AE-3"]
---
## Obiettivo

Transcribe the reference lists of analisi §3.5 (assistive robots in wards, standards) and §3.6 (security and tampering of wearable medical devices, diagnosability, regulation) into a bibliography fragment of 22 entries, all `verified = {false}` (ADR-018), and into two notes that give the difference of this work to each strand. The notes carry the difference sentence for the fourth Related Work paragraph, scope the C3 claim to "integrity or plausibility violations against declared attack classes" (ADR-002), and record that commercial ward robots such as Moxi have no reliable reference in analisi (no entry, no citation).

## Contesto

- `docs/plan/workstreams/WS03-related-work/README.md` (entry schema, key naming, expected counts).
- `docs/source/analisi.md` §3.5 and §3.6 (lists and "Differenza" paragraphs), §3 note on daggers.
- `docs/source/analisi.md` §10, third objection ("the robot is not necessary") and the fourth objection (C3, "an informed attacker is invisible").
- `docs/plan/03-decisions.md` ADR-002 (C3 reduced to integrity violations with a threat model) and ADR-003 (ward node plus robot; the robot executes the obligations induced by the specification and is the witness channel).
- `docs/source/review.md` R3 weakness 5 (risk management and standards for care robots) and meta-review item 3.

## File toccati

1. `paper/refs/fragments/ws03-t04.bib` (create)
2. `docs/related-work/assistive-ward-robots.md` (create)
3. `docs/related-work/wearable-device-security.md` (create)

## Test

Verification checks (paths relative to the repository root).

1. Files exist: `test -f paper/refs/fragments/ws03-t04.bib && test -f docs/related-work/assistive-ward-robots.md && test -f docs/related-work/wearable-device-security.md`.
2. Entry count and unique keys: `grep -c '^@' paper/refs/fragments/ws03-t04.bib` prints 22; `grep -o '^@[a-z]*{[^,]*' paper/refs/fragments/ws03-t04.bib | sort | uniq -d` prints nothing.
3. Nothing verified: `grep -c 'verified *= *{false}'` prints 22 and `grep -c 'verified *= *{true}'` prints 0 on the fragment.
4. Mandatory custom fields on every entry:
   ```
   for f in verified uncertain ref_status analisi task topic; do grep -c "^ *$f *=" paper/refs/fragments/ws03-t04.bib; done
   ```
   prints six lines, each 22.
5. Transcription fidelity: `grep -c 'uncertain *= *{true}'` prints 13; `grep -c 'ref_status *= *{partial}'` prints 3; `grep -c '^ *title *='` prints 6.
6. Dagger keys are exactly the thirteen of the table:
   ```
   awk '/^@/{k=$0} /uncertain *= *\{true\}/{print k}' paper/refs/fragments/ws03-t04.bib | sed 's/^@[a-z]*{//; s/,$//' | LC_ALL=C sort
   ```
   prints, in this order: `camara-medical-device-security-survey`, `choi-control-invariants`, `cosar-enrichme`, `dixon-webster-care-robot-verification`, `garbelini-sweyntooth`, `gombolay-care-coordination-conf`, `gombolay-care-coordination-ext`, `kyrarini-healthcare-robots-survey`, `li-insulin-pump`, `ljungblad-hospital-logistics-robots`, `rostami-heart-to-heart`, `shoukry-pycra`, `webster-care-robot-verification-thms`.
7. Note tables match the fragment: ``grep -c '^| `' docs/related-work/assistive-ward-robots.md`` prints 12 and the same command on `wearable-device-security.md` prints 10 (no other table row in a note starts with a backtick); the union of the keys of the two tables equals the set of keys of the fragment.
8. Each note has exactly six second-level headings: `## Scope`, `## Reference table`, `## What the reviewer expects`, `## Difference`, `## Risk and handling in the text`, `## Unresolved and for human verification` (`grep -c '^## '` prints 6).
9. No entry for unresolved items: `grep -i -c 'moxi' paper/refs/fragments/ws03-t04.bib` prints 0; `assistive-ward-robots.md` mentions Moxi only in its unresolved section, with the statement that analisi has no reliable peer-reviewed reference and the human checks whether published studies exist.
10. The `## Difference` section of `assistive-ward-robots.md` contains, case-insensitively, `logistics`, `acceptance`, `design-time`, `runtime`, `evidence` and `robot`. The `## Difference` section of `wearable-device-security.md` contains `invariants`, `cross-modal`, `witness`, `cryptograph`, `probing`, `integrity`, `attack classes` and `informed attacker`, and does not contain `adversarial` or `tampering` (`grep -i -c -E 'adversarial|tampering'` on that section prints 0).
11. Glossary check on both notes: `grep -n -i -E 'sub[s]ystem|embodied A[I]|smart-medic[a]l|edge clo[u]d' docs/related-work/assistive-ward-robots.md docs/related-work/wearable-device-security.md` prints nothing.
12. If `tools/check_bib.py` exists (WS03-T01 merged): `python3 tools/check_bib.py --schema --bib paper/refs/fragments/ws03-t04.bib` exits 0 and prints `entries=22`.
13. Forbidden tokens: `grep -n -E 'T[O]DO|T[B]D|[?]{3}|lor[e]m'` on the three files prints nothing.

## Passi

Inventory (binding; transcribed from analisi, nothing added). Columns as in WS03-T02: `type` (inp, art, misc); `author` is the exact `author` field; `-` means omitted; `title` only where analisi quotes a title or where the name is the only identity of the item; `†` is `uncertain = {true}`; `status` is `ref_status`; `analisi` is `{3.5}` or `{3.6}` as the section of the note. Corporate authors use double braces; the ampersand in a venue is written `{\&}`.

Analisi §3.5 (note `assistive-ward-robots.md`, 12 rows):

| # | key | type | author | year | venue | title | † | status | topic |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `riek-healthcare-robotics` | art | Riek | 2017 | Communications of the ACM | Healthcare robotics | no | recalled | overview |
| 2 | `yang-covid-robotics` | art | Yang and others | 2020 | Science Robotics | - | no | recalled | role of robotics during COVID-19 |
| 3 | `kyrarini-healthcare-robots-survey` | art | Kyrarini and others | 2021 | Technologies | - | yes | recalled | survey of robots in healthcare |
| 4 | `ljungblad-hospital-logistics-robots` | inp | Ljungblad and others | 2012 | CSCW | - | yes | recalled | field studies with hospital logistics robots |
| 5 | `gombolay-care-coordination-conf` | inp | Gombolay and others | 2016 | RSS | - | yes | recalled | robot-assisted care coordination (conference version) |
| 6 | `gombolay-care-coordination-ext` | art | Gombolay and others | - | IJRR | - | yes | recalled | extended version of row 5 |
| 7 | `cosar-enrichme` | art | Co{\c s}ar and others | 2020 | International Journal of Social Robotics | - | yes | recalled | ENRICHME project, TIAGo in assistive settings |
| 8 | `dixon-webster-care-robot-verification` | inp | Dixon and Webster and others | 2014 | TAROS | - | yes | recalled | formal verification of care robots |
| 9 | `webster-care-robot-verification-thms` | art | Webster and others | 2016 | IEEE Transactions on Human-Machine Systems | - | yes | recalled | formal verification of care robots |
| 10 | `iso-13482` | misc | {{ISO}} | - | - | ISO 13482 | no | partial | standard for personal care robots (R3 weakness 5) |
| 11 | `iso-14971` | misc | {{ISO}} | - | - | ISO 14971 | no | partial | risk management (R3 weakness 5) |
| 12 | `iec-62304` | misc | {{IEC}} | - | - | IEC 62304 | no | partial | standard named in analisi §3.5, no description in analisi |

Analisi §3.6 (note `wearable-device-security.md`, 10 rows):

| # | key | type | author | year | venue | title | † | status | topic |
|---|---|---|---|---|---|---|---|---|---|
| 13 | `halperin-pacemaker-icd` | inp | Halperin and others | 2008 | IEEE S{\&}P | - | no | recalled | attacks on pacemakers and ICDs |
| 14 | `li-insulin-pump` | inp | Li and Raghunathan and Raghunathan | 2011 | Healthcom | Hijacking an insulin pump | yes | recalled | attack on an insulin pump |
| 15 | `rushanan-sok-implantable` | inp | Rushanan and others | 2014 | IEEE S{\&}P | - | no | recalled | SoK on implantable devices and body area networks |
| 16 | `camara-medical-device-security-survey` | art | Camara and Peris-Lopez and Tapiador | 2015 | JBI | - | yes | recalled | survey |
| 17 | `garbelini-sweyntooth` | inp | Garbelini and others | 2020 | USENIX ATC | - | yes | recalled | SweynTooth, BLE vulnerabilities |
| 18 | `rostami-heart-to-heart` | inp | Rostami and Juels and Koushanfar | 2013 | CCS | - | yes | recalled | Heart-to-Heart, detection with physical or physiological invariants |
| 19 | `choi-control-invariants` | inp | Choi and others | 2018 | CCS | - | yes | recalled | control invariants for robotic vehicles |
| 20 | `shoukry-pycra` | inp | Shoukry and others | 2015 | CCS | - | yes | recalled | PyCRA, detection with physical invariants |
| 21 | `sampath-diagnosability` | art | Sampath and others | 1995 | IEEE TAC | Diagnosability of discrete-event systems | no | recalled | diagnosability, basis of the diagnosability matrix (WS02-T05) |
| 22 | `fda-premarket-cybersecurity` | misc | {{FDA}} | 2023 | - | - | no | recalled | guidance on cybersecurity of medical devices in premarket submissions |

Not an entry: commercial ward robots such as Moxi. Analisi says it has no reliable peer-reviewed reference and asks the authors to check whether published studies exist. The item is listed under "Unresolved" in the note, is not named or cited in the draft, and is handed to T06.

Steps.

1. Create `paper/refs/fragments/ws03-t04.bib` with a two-line comment header (task id, "merged into references.bib by WS03-T05").
2. Write one entry per inventory row, in table order, with exactly the fields of the row plus `verified = {false}`, `uncertain`, `ref_status`, `analisi`, `task = {WS03-T04}`, `topic` (schema in the README). Run checks 2 to 6 and fix.
3. Create `docs/related-work/assistive-ward-robots.md` with the six headings of check 8.
   - `## Scope`: analisi §3.5.
   - `## Reference table`: rows 1 to 12, columns key, authors as recalled, year, venue, dagger, ref_status, role in the text (overview, COVID-19 role, survey, field study, care coordination, TIAGo in assistive settings, design-time verification of care robots, standard). Each row starts with the key in backticks.
   - `## What the reviewer expects`: English summary of the analisi bullets, including the standards ISO 13482, ISO 14971 and IEC 62304 (R3 weakness 5 found none of them in the workshop paper).
   - `## Difference`: analisi statement (the literature concentrates on logistics, acceptance and design-time verification of robot behavior; this work proposes runtime monitoring of adherence to the care plan, with the robot as executor of tasks constrained by the specification and as a source of evidence), then the sentence of step 5.
   - `## Risk and handling in the text`: analisi rates the risk "BASSO" on novelty and "ALTO" on the question "why is a robot needed?" (§10 third objection). The text answers with the two facts of the method (ADR-003): the robot executes the measurement and witness obligations induced by the specification, and it is the only INTAKE witness. It makes no claim about measured benefit here (that is ablation A4, WS08-T04). The hazard and standards paragraph belongs to WS02-T05 and the Discussion; the related work may omit the three standards.
   - `## Unresolved and for human verification`: the seven daggered entries (rows 3 to 9), the Gombolay pair (which version to cite), the three `partial` standards (no year, edition or title beyond the name), and Moxi.
4. Create `docs/related-work/wearable-device-security.md` with the same six headings.
   - `## Scope`: analisi §3.6.
   - `## Reference table`: rows 13 to 22 in the same format (roles: attacks on devices, survey, BLE vulnerabilities, physical or physiological invariants, control invariants, diagnosability, regulation).
   - `## What the reviewer expects`: the analisi bullets.
   - `## Difference`: analisi statement (this work uses invariants derived from the clinical specification, cross-modal, and an embodied witness instead of cryptography or active probing of the sensor), the sentence of step 5, and the scoping line: the claim is limited to integrity or plausibility violations against declared attack classes (BLE injection and replay without keys, physical access to the dispenser, perception spoofing; compromised robot, monitor or specification excluded, ADR-002).
   - `## Risk and handling in the text`: analisi rates the risk "ALTO": without a threat model, a security reviewer objects that an informed attacker can inject physiologically plausible, cross-modally consistent data that is undetectable by construction. The text must not claim detection of tampering in general; the undetectable cases are reported as a result in the diagnosability matrix (WS02-T05) and named as a limit in the Discussion (WS12).
   - `## Unresolved and for human verification`: the six daggered entries (rows 14, 16 to 20) and the FDA guidance (analisi gives organisation and year, no title).
5. In the `## Difference` section of the two notes write the sentence for paragraph 4 (it covers §3.5 and §3.6 together because analisi §7 merges them into one paragraph; at most 70 words; WS03-T05 may shorten it without dropping any element). Wording:

   > Unlike work on logistics, acceptance and design-time verification of care robots, we monitor adherence to the care plan at runtime, with the robot both executing specification-constrained tasks and providing evidence; and unlike cryptographic protection or active sensor probing, we detect integrity or plausibility violations against declared attack classes using cross-modal invariants derived from the clinical specification and an embodied witness.

   Put the phrase "informed attacker" in the scoping line of the wearable note so that check 10 finds it.
6. Run every check under "Test" and fix. Commit with message `WS03-T04: assemble assistive-robot and device-security related-work notes and bib fragment`; set `status: done` in this file.

## Done when

- The thirteen checks under "Test" pass; the completion note pastes the output of checks 2 to 7 and 12 (if the tool exists).
- `grep -c '^@' paper/refs/fragments/ws03-t04.bib` prints 22 and `grep -c 'verified *= *{true}' paper/refs/fragments/ws03-t04.bib` prints 0.
- `docs/related-work/wearable-device-security.md` states the scope line of step 4 and `docs/related-work/assistive-ward-robots.md` lists Moxi as unresolved without any entry in the fragment.
