# Citation selection for the Related Work draft

Task WS03-T05. Draft: `docs/related-work/related-work-draft.tex`. Bibliography: `paper/refs/references.bib` (85 entries after the merge of the fragments of WS03-T02, T03 and T04, all `verified = {false}`, ADR-018). Every cited key below is still unverified: none may appear in the submission until a human verifies it (WS03-T06, WS00-T08). The draft lives under `docs/related-work/`, not under `paper/`, so that the WS12 build gate (`check_bib.py`, default scan of `paper/`) is not affected until WS12-T06 inserts it.

## Budget

- Related Work: four paragraphs of about 0.45 page in total (analisi section 7). About 1000 words fit a two-column RA-L page (assumption, unverified), so 0.45 page is about 450 to 500 words. The cap used here is 500 words outside comments and citation commands; the draft has 494 (225 of them are the four difference sentences).
- The whole paper carries 30 to 35 references (analisi section 7). Working allocation for this section: at most 25 distinct keys, split as P1 at most 8, P2 at most 7, P3 at most 6, P4 at most 4. The draft cites exactly 8, 7, 6 and 4 (25 in total, no key is shared between paragraphs).
- WS12-T02 fixes the real budget and WS12-T08 confirms it by compiling; the trim order below lets the draft shrink without rework.
- Selection rules: the must-cite keys first, then for every other role the entry that serves it best, preferring `uncertain = {false}` over `{true}` and `ref_status = {recalled}` over `{partial}`. Exceptions where a daggered or partial entry is cited: `bortolussi-neural-predictive-monitoring-conf`, `cairoli-conformal-quantitative-monitoring` (the Bortolussi and Cairoli line, analisi section 10 objection 2), `huang-rosrv` (RV for ROS, R1-W10; both RV-for-ROS works carry a dagger), `zhao-robust-conformal-stl` (distribution shift; only entry for that role), `dixon-webster-care-robot-verification` and `rostami-heart-to-heart` (no entry without a dagger for design-time verification of care robots or for physical or physiological invariants), `breach-tool`, `staliro-tool` and `hl7-fhir-plandefinition` (only entries for their role; partial).
- Choice between versions: Deshmukh, conference version (RV 2015) cited, the extended version not, because the two carry the same role and neither has a dagger; Bortolussi, conference version cited because the extended entry has no year in analisi; Gombolay pair not cited (the care-coordination role is not used in the draft).

## Cited keys

| Key | Paragraph | Role | `uncertain` | `ref_status` | Conditional |
|---|---|---|---|---|---|
| `fainekos-pappas-robustness` | P1 | robust semantics (must-cite) | false | recalled | no |
| `donze-maler-robust` | P1 | robust semantics and time robustness (must-cite) | false | recalled | no |
| `deshmukh-online-monitoring-conf` | P1 | online monitoring with robustness intervals on partial traces | false | recalled | no |
| `bauer-leucker-schallhart-three-valued` | P1 | three-valued semantics | false | recalled | no |
| `nickovic-yamaguchi-rtamt` | P1 | tool (RTAMT) (must-cite) | false | recalled | no |
| `breach-tool` | P1 | tool (Breach) (must-cite) | false | partial | yes |
| `staliro-tool` | P1 | tool (S-TaLiRo) (must-cite) | false | partial | yes |
| `huang-rosrv` | P1 | RV in ROS (ROSRV); R1-W10 | true | recalled | no |
| `lindemann-conformal-stl` | P2 | closest work; baseline B5 (must-cite) | false | recalled | no |
| `bortolussi-neural-predictive-monitoring-conf` | P2 | predictive monitoring (conference version) | true | recalled | no |
| `cairoli-conformal-quantitative-monitoring` | P2 | conformal quantitative predictive monitoring of STL requirements (must-cite) | true | recalled | no |
| `zhao-robust-conformal-stl` | P2 | distribution shift | true | recalled | no |
| `lindemann-safe-planning` | P2 | conformal prediction in robotics, RA-L (must-cite) | false | recalled | no |
| `gibbs-candes-adaptive-conformal` | P2 | non-exchangeability (adaptive conformal inference) | false | recalled | no |
| `barber-beyond-exchangeability` | P2 | non-exchangeability | false | recalled | no |
| `lee-sokolsky-medical-cps` | P3 | medical CPS overview | false | recalled | no |
| `wong-sepsis-external-validation` | P3 | motivation against opaque ML deterioration models (must-cite) | false | recalled | no |
| `sendelbach-funk-alarm-fatigue` | P3 | alarm fatigue | false | recalled | no |
| `shahar-miksch-johnson-asbru` | P3 | formalism (Asbru) (must-cite) | false | recalled | no |
| `munoz-gama-process-mining-healthcare` | P3 | process mining in healthcare | false | recalled | no |
| `hl7-fhir-plandefinition` | P3 | standard (FHIR PlanDefinition and CarePlan) | false | partial | no |
| `riek-healthcare-robotics` | P4 | healthcare robotics overview | false | recalled | no |
| `dixon-webster-care-robot-verification` | P4 | design-time verification of care robots | true | recalled | no |
| `halperin-pacemaker-icd` | P4 | attacks on devices (pacemaker and ICD) | false | recalled | no |
| `rostami-heart-to-heart` | P4 | physical or physiological invariants (Heart-to-Heart) | true | recalled | no |

Notes on the table:

- `breach-tool` and `staliro-tool` are conditional: their entries are `partial` and analisi gives no citation data. If the human cannot complete them in WS03-T06, drop the two `\cite` commands and keep the tool names in the text.
- The paragraph column is the paragraph of the first citation in the draft; `donze-maler-robust` is cited twice in P1 and `lindemann-conformal-stl` twice in P2 (body and difference sentence). Distinct keys: 25.
- Unresolved items (commercial ward robots such as Moxi; the specific SCIFF work) have no entry and are not cited or named in the draft.

## Not cited

All other entries stay in `references.bib` for later sections of the paper (Discussion, Problem Formulation, method).

- Unchosen version of a conf and ext pair: `bortolussi-neural-predictive-monitoring-ext` (the conference entry has a year; the extended one has none in analisi), `deshmukh-online-monitoring-ext` (same role as the conference version, one version is enough), `gombolay-care-coordination-conf` and `gombolay-care-coordination-ext` (role not used in the draft; both carry a dagger).
- Second RV-for-ROS work: `ferrando-rosmonitoring` (dagger; one of the two is enough for R1-W10).
- STL background kept for the method sections: `maler-nickovic-stl`, `donze-ferrere-maler-monitoring`, `bartocci-spec-monitoring-survey`, `leucker-schallhart-rv-survey`, `luckcuck-formal-robotics-survey`, `desai-soter`, `sha-simplex`, `mehdipour-agm-robustness`, `mehdipour-weighted-stl`, `brim-stl-star`, `rodionova-time-robustness` (normalization and freeze alternatives belong to WS01: ADR-007, ADR-009).
- Conformal time series and PID: `stankeviciute-conformal-time-series`, `xu-xie-enbpi`, `angelopoulos-conformal-pid` (P2 is at its cap of 7).
- Medical CPS and devices, kept for the Discussion and the benchmark: `arney-closed-loop-devices`, `kim-pca-pump`, `jiang-pajic-mangharam-cardiac`, `cameron-artificial-pancreas`, `bufo-icu-ventilation-stl`, `nickovic-shape-expressions` (all daggered; P3 is at its cap of 6), `clifford-cinc-2015`, `drew-alarm-fatigue` (second alarm-fatigue entry), `rcp-news2` (source of the ordinal-band alternative, ADR-009).
- Guideline formalization: `peleg-comparing-guideline-models`, `ohno-machado-glif`, `fox-proforma`, `terenziani-glare`, `shahar-temporal-abstraction`, `tenteije-protocure`, `bottrighi-guideline-verification`, `maggi-declare-monitoring`, `mans-process-mining-healthcare`, `rojas-process-mining-healthcare`, `carmona-conformance-checking`, `burattin-online-conformance`, `braun-bpmn4cp`, `hl7-cql`, `arden-syntax`, `openehr-gdl`.
- Robots and security: `yang-covid-robotics`, `kyrarini-healthcare-robots-survey`, `ljungblad-hospital-logistics-robots`, `cosar-enrichme`, `webster-care-robot-verification-thms`, `li-insulin-pump`, `rushanan-sok-implantable`, `camara-medical-device-security-survey`, `garbelini-sweyntooth`, `choi-control-invariants`, `shoukry-pycra`, `sampath-diagnosability` (basis of the diagnosability matrix, WS02-T05).
- Standards and guidance left to the hazard paragraph (WS02-T05, Discussion): `iso-13482`, `iso-14971`, `iec-62304`, `fda-premarket-cybersecurity`.
- Unresolved, no entry and not named in the draft: Moxi and other commercial ward robots; the specific SCIFF work.
- No FHIR or BPMN mapping clause: WS01-T07 has not produced its mapping sketch (status `blocked` when this task ran), so the draft claims nothing about it.

## Trim order

If WS12-T08 shows that the section exceeds 0.45 page, drop the following first, lowest priority first (delete the clause and its `\cite`, keep the difference sentences). Must-cite keys are never dropped, and neither are the conf entry of Bortolussi, `deshmukh-online-monitoring-conf` and `huang-rosrv`, which satisfy the R1-W10 and analisi requirements.

1. `munoz-gama-process-mining-healthcare` (process-mining clause)
2. `sendelbach-funk-alarm-fatigue` (alarm-fatigue clause)
3. `lee-sokolsky-medical-cps` (medical CPS opening sentence)
4. `barber-beyond-exchangeability`
5. `gibbs-candes-adaptive-conformal` (when 4 and 5 go, keep the sentence about the calibration unit and the adaptive variant, which are needed for the coverage statement)
6. `rostami-heart-to-heart`
7. `halperin-pacemaker-icd`
8. `riek-healthcare-robotics`
9. `bauer-leucker-schallhart-three-valued`
10. `zhao-robust-conformal-stl`

## Handover to T06

Verify in this order. All 25 keys are `verified = {false}`; the human checks each on DBLP, Google Scholar or the publisher page, completes first names, full titles, venue, pages and DOI, and only then sets `verified = {true}` (ADR-018).

1. `uncertain = {true}` (dagger in analisi; venue, year or author list): `bortolussi-neural-predictive-monitoring-conf`, `cairoli-conformal-quantitative-monitoring`, `dixon-webster-care-robot-verification`, `huang-rosrv`, `rostami-heart-to-heart`, `zhao-robust-conformal-stl`.
2. `ref_status = {partial}` (analisi gives no citation data): `breach-tool`, `staliro-tool` (conditional: if not completed, drop their two `\cite` commands), `hl7-fhir-plandefinition` (the human decides which specification document and edition to cite).
3. The rest (`recalled`, no dagger): `fainekos-pappas-robustness`, `donze-maler-robust`, `deshmukh-online-monitoring-conf`, `bauer-leucker-schallhart-three-valued`, `nickovic-yamaguchi-rtamt`, `lindemann-conformal-stl`, `lindemann-safe-planning`, `gibbs-candes-adaptive-conformal`, `barber-beyond-exchangeability`, `lee-sokolsky-medical-cps`, `wong-sepsis-external-validation`, `sendelbach-funk-alarm-fatigue`, `shahar-miksch-johnson-asbru`, `munoz-gama-process-mining-healthcare`, `riek-healthcare-robotics`, `halperin-pacemaker-icd`.

Statements in the draft about cited works that the human must check against the paper text (they rest on analisi, which recalls the works from memory):

- Lindemann et al. (`lindemann-conformal-stl`), difference sentence of P2, mandatory check: "dense predicted trajectories" is the wording of WS03-T02 built on analisi section 3.2, which says only "traiettorie dense"; the word "predicted" is not in analisi. It has not been checked against the paper. Correct the sentence if the paper differs. The three other elements of that sentence describe this work (they are not statements about Lindemann et al.), but the contrast is only valid if the paper indeed lacks them; analisi section 5.4 lists sparse sampling, mixed units and no attribution as points where B5 fails, to be confirmed by WS06-T06.
- Asbru (`shahar-miksch-johnson-asbru`), P3: "express intentions and temporal conditions that can be monitored during execution" is taken from analisi section 3.4 (risk paragraph), not from the paper.
- Process mining (`munoz-gama-process-mining-healthcare`), P3: "works on recorded events of the clinical record" is the characterization of analisi section 3.4 for that family of works; it is not checked against this paper.
- The other descriptions are limited to the `topic` field of the entry or the role column of the notes (overview, attacks on pacemakers and ICDs, physical or physiological invariants, distribution shift, non-exchangeability, design-time verification of care robots, RV in ROS, three-valued semantics, tools). Tool-specific remarks (for example the MATLAB dependence of Breach and S-TaLiRo, which rests on ADR-013 still marked `[DA-CONFERMARE]`) are deliberately not in the draft.
- P3 states that FHIR PlanDefinition and CarePlan is the standard representation the paper targets. That is a statement about this work, not about the standard; it must stay consistent with WS01-T07 when that task closes.
