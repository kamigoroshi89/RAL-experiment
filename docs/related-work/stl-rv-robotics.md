# Related work note: STL runtime monitoring and runtime verification in robotics (analisi 3.1)

Task WS03-T02. Bibliography fragment: `paper/refs/fragments/ws03-t02.bib` (rows 1 to 21 of the inventory; rows 22 to 32 are in `conformal-predictive-monitoring.md`). Every entry has `verified = {false}` (ADR-018); nothing here is verified.

## Scope

Analisi section 3.1, "Runtime monitoring STL per robotica e CPS": robust STL semantics, monitoring algorithms, online monitoring on partial traces, surveys, three-valued semantics, tools, runtime verification (RV) for ROS, formal verification in robotics, runtime assurance, normalisation and weighting of robustness, the freeze operator, and time robustness. Eighteen entries come from that section, transcribed as analisi recalls them (authors, year, venue as given; a dagger marks specific uncertainty on venue, year or author list).

Three items are added beyond the list of section 3.1, each because analisi names it elsewhere:

- Maler and Nickovic (2004), the original STL definition with Boolean semantics. Analisi section 2, R1 weakness 2, says it is the only STL reference of the workshop paper, which lacks the works that introduce quantitative robustness (rows 2 and 3).
- Breach and S-TaLiRo, the two STL tools named in R1 weakness 10 ("Nessun tool (RTAMT, Breach, S-TaLiRo), nessuna complessita, nessun cenno a RV per ROS") and in ADR-013. Analisi gives no citation data for them, so their entries are `partial` and carry only the tool name as title.

Nothing else has been added from other sources: titles appear only where analisi quotes one or where the name is the only identity of the item.

## Reference table

| Key | Authors as recalled | Year | Venue | Dagger | ref_status | Role in the text |
|---|---|---|---|---|---|---|
| `maler-nickovic-stl` | Maler and Nickovic | 2004 | not given | no | recalled | original STL definition, Boolean semantics |
| `fainekos-pappas-robustness` | Fainekos and Pappas | 2009 | Theoretical Computer Science | no | recalled | robust semantics |
| `donze-maler-robust` | Donze and Maler | 2010 | FORMATS | no | recalled | robust semantics; time robustness also appears here |
| `donze-ferrere-maler-monitoring` | Donze, Ferrere and Maler | 2013 | CAV | no | recalled | monitoring algorithm |
| `deshmukh-online-monitoring-conf` | Deshmukh and others | 2015 | RV | no | recalled | online monitoring with robustness intervals on partial traces (conference version) |
| `deshmukh-online-monitoring-ext` | Deshmukh and others | 2017 | Formal Methods in System Design | no | recalled | online monitoring, extended version of the RV 2015 work |
| `bartocci-spec-monitoring-survey` | Bartocci and others | 2018 | Lectures on Runtime Verification, LNCS 10457 | no | recalled | survey |
| `leucker-schallhart-rv-survey` | Leucker and Schallhart | 2009 | JLAP | no | recalled | survey |
| `bauer-leucker-schallhart-three-valued` | Bauer, Leucker and Schallhart | 2011 | ACM TOSEM | no | recalled | three-valued semantics |
| `nickovic-yamaguchi-rtamt` | Nickovic and Yamaguchi | 2020 | ATVA | no | recalled | tool (RTAMT) |
| `huang-rosrv` | Huang and others | 2014 | SIMPAR | yes | recalled | RV in ROS (ROSRV) |
| `ferrando-rosmonitoring` | Ferrando and others | 2020 | TAROS | yes | recalled | RV in ROS (ROSMonitoring) |
| `luckcuck-formal-robotics-survey` | Luckcuck and others | 2019 | ACM Computing Surveys | no | recalled | formal verification in robotics, survey |
| `desai-soter` | Desai and others | 2019 | DSN | no | recalled | runtime assurance (SOTER) |
| `sha-simplex` | Sha | 2001 | not given | no | recalled | runtime assurance (Simplex architecture) |
| `mehdipour-agm-robustness` | Mehdipour, Vasile and Belta | 2019 | CDC | yes | recalled | normalisation alternative (AGM robustness, ADR-009) |
| `mehdipour-weighted-stl` | Mehdipour, Vasile and Belta | not given | not given | yes | partial | normalisation alternative (weighted STL); same authors as AGM robustness |
| `brim-stl-star` | Brim and others | 2014 | Information and Computation | yes | recalled | freeze alternative (STL*, ADR-007) |
| `rodionova-time-robustness` | Rodionova and others | 2021 | CDC | yes | recalled | time robustness for control |
| `breach-tool` | not given | not given | not given | no | partial | tool (Breach), named in R1 weakness 10 |
| `staliro-tool` | not given | not given | not given | no | partial | tool (S-TaLiRo), named in R1 weakness 10 |

## What the reviewer expects

Grouped by role, as analisi section 3.1 lists them (daggers kept).

- Robust semantics: Fainekos and Pappas (Theoretical Computer Science, 2009); Donze and Maler (FORMATS 2010), where time robustness also appears. Original STL definition with Boolean semantics: Maler and Nickovic (2004), from R1 weakness 2.
- Monitoring algorithms: Donze, Ferrere and Maler (CAV 2013).
- Online monitoring with robustness intervals on partial traces: Deshmukh and others (RV 2015; extended version in Formal Methods in System Design, 2017).
- Surveys: Bartocci and others, "Specification-based monitoring of cyber-physical systems" (Lectures on Runtime Verification, LNCS 10457, 2018); Leucker and Schallhart (JLAP 2009).
- Three-valued semantics: Bauer, Leucker and Schallhart (ACM TOSEM 2011).
- Tools: RTAMT, Nickovic and Yamaguchi (ATVA 2020). Breach and S-TaLiRo are named in R1 weakness 10 without citation data.
- RV in ROS: ROSRV by Huang and others (dagger, SIMPAR 2014); ROSMonitoring by Ferrando and others (dagger, TAROS 2020).
- Formal verification in robotics: survey by Luckcuck and others (ACM Computing Surveys 2019).
- Runtime assurance: SOTER, Desai and others (DSN 2019); Simplex architecture (Sha, 2001; analisi gives no venue).
- Normalisation and weighting: AGM robustness by Mehdipour, Vasile and Belta (dagger, CDC 2019); weighted STL (dagger, same authors; analisi gives no year or venue).
- Freeze operator: STL* by Brim and others (dagger, Information and Computation 2014).
- Time robustness for control: Rodionova and others (dagger, CDC 2021).

## Difference

Analisi: the contribution cannot be the monitoring algorithm, which exists. It can be three things:

1. the class of specifications (templates derived from care plans) over clinical signals that are sparse, irregular, and a mix of continuous values and events;
2. a severity normalized with clinical scales;
3. the coupling between the clinical specification and the tasks of the robot.

Sentence for the first Related Work paragraph (WS03-T05 may shorten it without dropping any of the three elements):

> Our contribution is not the monitoring algorithm: it is a class of specifications derived from patient care plans over sparse, irregular, mixed continuous and event signals, a severity normalized with clinical scales, and the coupling of the clinical specification with the tasks of the assistive robot.

## Risk and handling in the text

Analisi rates the risk ALTO if the claim stays "we use robust STL for runtime safety": a formal-methods reviewer would dismiss it as an application of RTAMT. The text must never present the monitoring algorithm as the contribution. Handling for reviewer finding R1-W10 (tools, complexity, RV for ROS):

- Tools: name RTAMT, Breach and S-TaLiRo. RTAMT has a recalled reference (row 10). Breach and S-TaLiRo have no reference in analisi, so their `.bib` entries are `partial`; WS03-T06 must complete them, otherwise WS03-T05 drops the citations of them and the text names the tools without a citation. ADR-013 records RTAMT as the reference tool, with Breach and S-TaLiRo as alternatives with a MATLAB dependence.
- RV for ROS: cite at least one of ROSRV or ROSMonitoring; both carry a dagger and need verification before they are cited.
- Complexity: analisi asks for the complexity per sample (section 4.7), but section 3.1 gives no reference for it. The related work states no complexity bound. The statement belongs to WS05-T04 (per-sample complexity and latency bounds of the monitor core) and WS01-T05 (three-valued semantics with latency bounds); the related work does not anticipate it.
- Wording: robustness is used only for STL semantics; the text does not call a device fault a violation. Validation is technical and pre-clinical, so no sentence about these works implies clinical validation of this one.

## Unresolved and for human verification

- Six entries of section 3.1 carry a dagger in analisi and need specific verification of venue, year or author list: `huang-rosrv`, `ferrando-rosmonitoring`, `mehdipour-agm-robustness`, `mehdipour-weighted-stl`, `brim-stl-star`, `rodionova-time-robustness` (rows 11, 12, 16 to 19).
- Three entries are `partial`: `mehdipour-weighted-stl` (year and venue not given in analisi), `breach-tool` and `staliro-tool` (no citation data). WS03-T06 completes them or WS03-T05 does not cite them.
- Two versions of the Deshmukh work exist (rows 5 and 6): which one to cite is decided in WS03-T05 and recorded in `citation-selection.md`.
- Sha (row 15): analisi gives author and year but no venue.
- Every entry lacks first names, full titles (except row 7 and the tool names), pages and DOIs; the human adds them in WS03-T06.
