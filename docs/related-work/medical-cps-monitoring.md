# Related work note: medical CPS monitoring (analisi 3.3)

Task WS03-T03. Bibliography fragment: `paper/refs/fragments/ws03-t03.bib` (rows 1 to 12 of the inventory). Every entry has `verified = {false}` (ADR-018); nothing here is verified.

## Scope

Analisi section 3.3, "Specification-based monitoring in medicine": medical cyber-physical systems, monitoring of medical devices with temporal logics, false alarms and alarm fatigue, early warning scores, and the limits of opaque machine-learning deterioration models. Twelve entries, transcribed as analisi recalls them (authors, year, venue as given; a dagger marks specific uncertainty on venue, year or author list). Nothing has been added from other sources: titles appear only where analisi quotes one or where the name is the only identity of the item.

## Reference table

| Key | Authors as recalled | Year | Venue | Dagger | ref_status | Role in the text |
|---|---|---|---|---|---|---|
| `lee-sokolsky-medical-cps` | Lee and Sokolsky and others | 2012 | Proceedings of the IEEE | no | recalled | medical CPS overview |
| `arney-closed-loop-devices` | Arney and others | 2010 | ICCPS | yes | recalled | closed-loop devices |
| `kim-pca-pump` | Kim and others | 2011 | EMSOFT | yes | recalled | infusion pump |
| `jiang-pajic-mangharam-cardiac` | Jiang and Pajic and Mangharam | 2012 | Proceedings of the IEEE | yes | recalled | cardiac |
| `cameron-artificial-pancreas` | Cameron and Fainekos and Maahs and Sankaranarayanan | 2015 | RV | yes | recalled | artificial pancreas |
| `bufo-icu-ventilation-stl` | Bufo and Bartocci and Bortolussi and others | 2014 | ISoLA | yes | recalled | STL in intensive care |
| `nickovic-shape-expressions` | Ničković and others | 2019 | RV | yes | recalled | shape expressions |
| `clifford-cinc-2015` | Clifford and others | 2015 | CinC | no | recalled | false-alarm challenge |
| `sendelbach-funk-alarm-fatigue` | Sendelbach and Funk | 2013 | AACN Advanced Critical Care | no | recalled | alarm fatigue |
| `drew-alarm-fatigue` | Drew and others | 2014 | PLoS ONE | no | recalled | alarm fatigue |
| `rcp-news2` | Royal College of Physicians (title: NEWS2) | 2017 | - | no | recalled | early warning score |
| `wong-sepsis-external-validation` | Wong and others | 2021 | JAMA Internal Medicine | no | recalled | motivation against opaque ML deterioration models |

## What the reviewer expects

- Medical CPS: Lee, Sokolsky and others, "Challenges and research directions in medical cyber-physical systems" (Proceedings of the IEEE, 2012); Arney and others on closed-loop medical device systems (dagger, ICCPS 2010).
- Generic PCA infusion pump: Kim and others (dagger, EMSOFT 2011).
- Pacemaker and cardiac models: Jiang, Pajic and Mangharam (dagger, Proceedings of the IEEE, 2012).
- Artificial pancreas and runtime safety: Cameron, Fainekos, Maahs and Sankaranarayanan (dagger, RV 2015).
- STL for assisted ventilation in intensive care: Bufo, Bartocci, Bortolussi and others (dagger, ISoLA 2014).
- Shape expressions with ECG examples: Ničković and others (dagger, RV 2019).
- False alarms: PhysioNet/Computing in Cardiology Challenge 2015 on false arrhythmia alarms in intensive care (Clifford and others, CinC 2015).
- Alarm fatigue: Sendelbach and Funk (AACN Advanced Critical Care, 2013); Drew and others (PLoS ONE, 2014).
- Early warning score: NEWS2 (Royal College of Physicians, 2017). It is the source of the ordinal-band alternative of ADR-009.
- Limits of machine-learning deterioration models: Wong and others, external validation of a proprietary sepsis prediction model (JAMA Internal Medicine, 2021). Analisi calls it "useful to motivate the specification-based approach".

The alarm-fatigue and false-alarm entries (rows 8 to 10) also support the metric "false alarms per patient-day" (analisi 5.5) and answer R3 weakness 6 of the simulated review (alarm load and alarm fatigue).

## Difference

Analisi: those works monitor a device, a controller or a single physiological property. This work monitors adherence to a care process that involves several devices, the patient and a robotic agent, and attributes a cause to each alert.

Sentence for the third Related Work paragraph (covers 3.3 and 3.4 together, because analisi 7 merges them; WS03-T05 may shorten it without dropping any element):

> Unlike these works, which monitor a single device, controller or physiological property, or which reason offline over discrete events of the clinical record for decision support and retrospective conformance, we monitor adherence to a care process that spans several devices, the patient and an assistive robot, online, on continuous signals with quantitative robustness, and we attribute a cause to each alert.

## Risk and handling in the text

Analisi rates the risk MEDIO: specification-based monitoring in medicine is not new. The novelty lies in the scale of the process and in attribution. The text must not claim priority for medical STL monitoring. It uses "alert" for the output of the monitor and does not call a device fault a "violation" (glossary: a violation is a violated sub-formula). Validation is technical and pre-clinical, so no sentence about these works implies clinical validation of this one.

## Unresolved and for human verification

- Six entries carry a dagger in analisi and need specific verification of venue, year or author list: `arney-closed-loop-devices`, `kim-pca-pump`, `jiang-pajic-mangharam-cardiac`, `cameron-artificial-pancreas`, `bufo-icu-ventilation-stl`, `nickovic-shape-expressions` (rows 2 to 7).
- Ambiguity for WS03-T05: which of rows 5 to 7 to cite. One or two are enough for paragraph 3; the choice is recorded in `citation-selection.md`.
- Every entry lacks first names, full titles (except rows 1 and 11), pages and DOIs; the human adds them in WS03-T06.
