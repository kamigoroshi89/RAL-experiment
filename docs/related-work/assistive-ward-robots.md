# Related work note: assistive robots in wards (analisi 3.5)

Task WS03-T04. Bibliography fragment: `paper/refs/fragments/ws03-t04.bib` (rows 1 to 12 of the inventory; rows 13 to 22 are in `wearable-device-security.md`). Every entry has `verified = {false}` (ADR-018); nothing here is verified.

## Scope

Analisi section 3.5, "Robot assistivi in reparto": overviews of healthcare robotics, field studies with hospital logistics robots, robot-assisted care coordination, the use of a TIAGo-class robot in assistive settings, formal verification of care robots, and the standards for personal care robots and medical-device risk management. Twelve entries, transcribed as analisi recalls them (authors, year, venue as given; a dagger marks specific uncertainty on venue, year or author list). Nothing has been added from other sources: titles appear only where analisi quotes one or where the name is the only identity of the item. Analisi gives no year, edition or title for the three standards, so they carry only their name.

## Reference table

| Key | Authors as recalled | Year | Venue | Dagger | ref_status | Role in the text |
|---|---|---|---|---|---|---|
| `riek-healthcare-robotics` | Riek (title: Healthcare robotics) | 2017 | Communications of the ACM | no | recalled | overview |
| `yang-covid-robotics` | Yang and others | 2020 | Science Robotics | no | recalled | COVID-19 role of robotics |
| `kyrarini-healthcare-robots-survey` | Kyrarini and others | 2021 | Technologies | yes | recalled | survey |
| `ljungblad-hospital-logistics-robots` | Ljungblad and others | 2012 | CSCW | yes | recalled | field study with hospital logistics robots |
| `gombolay-care-coordination-conf` | Gombolay and others | 2016 | RSS | yes | recalled | care coordination (conference version) |
| `gombolay-care-coordination-ext` | Gombolay and others | - | IJRR | yes | recalled | care coordination (extended version) |
| `cosar-enrichme` | Coşar and others | 2020 | International Journal of Social Robotics | yes | recalled | TIAGo in assistive settings (ENRICHME) |
| `dixon-webster-care-robot-verification` | Dixon and Webster and others | 2014 | TAROS | yes | recalled | design-time verification of care robots |
| `webster-care-robot-verification-thms` | Webster and others | 2016 | IEEE Transactions on Human-Machine Systems | yes | recalled | design-time verification of care robots |
| `iso-13482` | ISO (title: ISO 13482) | - | - | no | partial | standard |
| `iso-14971` | ISO (title: ISO 14971) | - | - | no | partial | standard |
| `iec-62304` | IEC (title: IEC 62304) | - | - | no | partial | standard |

## What the reviewer expects

- Overviews: Riek, "Healthcare robotics" (Communications of the ACM, 2017); Yang and others on the role of robotics during COVID-19 (Science Robotics, 2020); Kyrarini and others, survey of robots in healthcare (dagger, Technologies, 2021).
- Field studies with hospital logistics robots: Ljungblad and others (dagger, CSCW, 2012).
- Robot-assisted care coordination: Gombolay and others (dagger, RSS 2016 and IJRR). Analisi names one dagger for both versions, so both entries carry it.
- TIAGo in assistive settings: the ENRICHME project, Coşar and others (dagger, International Journal of Social Robotics, 2020).
- Formal verification of care robots: Dixon, Webster and others (dagger, TAROS 2014); Webster and others (dagger, IEEE Transactions on Human-Machine Systems, 2016).
- Standards: ISO 13482, ISO 14971, IEC 62304. The simulated review (R3 weakness 5) found no reference to risk management (ISO 14971) or to standards for personal care robots (ISO 13482) in the workshop paper.
- Commercial ward robots: see the last section.

## Difference

Analisi: the literature concentrates on logistics, acceptance and design-time verification of the robot's behavior. This work proposes runtime monitoring of adherence to the care plan, with the robot as executor of tasks constrained by the specification and as a source of evidence.

Sentence for the fourth Related Work paragraph (covers 3.5 and 3.6 together, because analisi 7 merges them into one paragraph; at most 70 words; WS03-T05 may shorten it without dropping any element):

> Unlike work on logistics, acceptance and design-time verification of care robots, we monitor adherence to the care plan at runtime, with the robot both executing specification-constrained tasks and providing evidence; and unlike cryptographic protection or active sensor probing, we detect integrity or plausibility violations against declared attack classes using cross-modal invariants derived from the clinical specification and an embodied witness.

## Risk and handling in the text

Analisi rates the risk BASSO on novelty and ALTO on the question "why is a robot needed?" (analisi 10, third objection: "the robot is not necessary"). The text answers with the two facts of the method (ADR-003): the robot executes the measurement and witness obligations induced by the specification, and it is the only INTAKE witness (DISPENSE, the dispenser opening, is not INTAKE). The text makes no claim about a measured benefit of the robot here; that is ablation A4 (WS08-T04). The hazard and standards paragraph belongs to WS02-T05 and the Discussion; the related work may omit the three standards. Statements about the cited works are limited to what analisi says about them, since the entries are unverified. Validation is technical and pre-clinical, so no sentence about these works implies clinical validation of this one.

## Unresolved and for human verification

- Seven entries carry a dagger in analisi and need specific verification of venue, year or author list: `kyrarini-healthcare-robots-survey`, `ljungblad-hospital-logistics-robots`, `gombolay-care-coordination-conf`, `gombolay-care-coordination-ext`, `cosar-enrichme`, `dixon-webster-care-robot-verification`, `webster-care-robot-verification-thms` (rows 3 to 9).
- Gombolay pair: analisi lists RSS 2016 and IJRR without an IJRR year. WS03-T05 cites one of the two and records the choice in `citation-selection.md`; the human confirms the year of the extended version.
- Three `partial` standards (`iso-13482`, `iso-14971`, `iec-62304`, rows 10 to 12): analisi gives the name only, with no year, edition or title. The human supplies these if the standards are cited.
- Commercial ward robots such as Moxi: analisi states that it has no reliable peer-reviewed reference and asks the authors to check whether published studies exist. No entry was created, the item is not cited in the draft, and the human checks whether published studies exist (WS03-T06).
- Every entry lacks first names, full titles (except rows 1 and 10 to 12) and pages; the human adds them in WS03-T06.
