# Related work note: security of wearable medical devices (analisi 3.6)

Task WS03-T04. Bibliography fragment: `paper/refs/fragments/ws03-t04.bib` (rows 13 to 22 of the inventory; rows 1 to 12 are in `assistive-ward-robots.md`). Every entry has `verified = {false}` (ADR-018); nothing here is verified.

## Scope

Analisi section 3.6, "Sicurezza e tampering di dispositivi medici indossabili": attacks on medical devices, surveys, vulnerabilities of Bluetooth Low Energy (BLE) stacks, detection based on physical or physiological invariants, diagnosability of discrete-event systems (the basis of the diagnosability matrix, WS02-T05), and regulatory guidance. Ten entries, transcribed as analisi recalls them (authors, year, venue as given; a dagger marks specific uncertainty on venue, year or author list). Nothing has been added from other sources: titles appear only where analisi quotes one. Analisi gives no title for the FDA guidance beyond its description.

## Reference table

| Key | Authors as recalled | Year | Venue | Dagger | ref_status | Role in the text |
|---|---|---|---|---|---|---|
| `halperin-pacemaker-icd` | Halperin and others | 2008 | IEEE S&P | no | recalled | attacks on devices (pacemaker and ICD) |
| `li-insulin-pump` | Li and Raghunathan and Raghunathan (title: Hijacking an insulin pump) | 2011 | Healthcom | yes | recalled | attacks on devices (insulin pump) |
| `rushanan-sok-implantable` | Rushanan and others | 2014 | IEEE S&P | no | recalled | survey (SoK, implantable devices and body area networks) |
| `camara-medical-device-security-survey` | Camara and Peris-Lopez and Tapiador | 2015 | JBI | yes | recalled | survey |
| `garbelini-sweyntooth` | Garbelini and others | 2020 | USENIX ATC | yes | recalled | BLE vulnerabilities (SweynTooth) |
| `rostami-heart-to-heart` | Rostami and Juels and Koushanfar | 2013 | CCS | yes | recalled | physical or physiological invariants (Heart-to-Heart) |
| `choi-control-invariants` | Choi and others | 2018 | CCS | yes | recalled | control invariants for robotic vehicles |
| `shoukry-pycra` | Shoukry and others | 2015 | CCS | yes | recalled | physical invariants (PyCRA) |
| `sampath-diagnosability` | Sampath and others (title: Diagnosability of discrete-event systems) | 1995 | IEEE TAC | no | recalled | diagnosability |
| `fda-premarket-cybersecurity` | FDA | 2023 | - | no | recalled | regulation |

## What the reviewer expects

- Attacks on devices: Halperin and others on pacemakers and ICDs (IEEE S&P, 2008); Li, Raghunathan and Raghunathan, "Hijacking an insulin pump" (dagger, Healthcom, 2011).
- Surveys: Rushanan and others, SoK on implantable devices and body area networks (IEEE S&P, 2014); Camara, Peris-Lopez and Tapiador (dagger, JBI, 2015).
- BLE vulnerabilities: SweynTooth, Garbelini and others (dagger, USENIX ATC, 2020).
- Detection with physical or physiological invariants: Rostami, Juels and Koushanfar, Heart-to-Heart (dagger, CCS, 2013); Choi and others, control invariants for robotic vehicles (dagger, CCS, 2018); Shoukry and others, PyCRA (dagger, CCS, 2015).
- Diagnosability: Sampath and others, "Diagnosability of discrete-event systems" (IEEE TAC, 1995).
- Regulation: FDA guidance on the cybersecurity of medical devices in premarket submissions (2023).

## Difference

Analisi: this work uses invariants derived from the clinical specification (cross-modal) and an embodied witness, instead of cryptography or active probing of the sensor.

Sentence for the fourth Related Work paragraph (covers 3.5 and 3.6 together, because analisi 7 merges them into one paragraph; at most 70 words; WS03-T05 may shorten it without dropping any element):

> Unlike work on logistics, acceptance and design-time verification of care robots, we monitor adherence to the care plan at runtime, with the robot both executing specification-constrained tasks and providing evidence; and unlike cryptographic protection or active sensor probing, we detect integrity or plausibility violations against declared attack classes using cross-modal invariants derived from the clinical specification and an embodied witness.

Scoping line (ADR-002): the claim is limited to integrity or plausibility violations against declared attack classes, namely BLE injection and replay without keys, physical access to the dispenser, and perception spoofing. A compromised robot, monitor or specification is excluded. An informed attacker who injects physiologically plausible, cross-modally consistent data is undetectable by construction; those cases are reported as a result in the diagnosability matrix (WS02-T05), not as a side note. Attribution class C3 means integrity violation in this sense.

## Risk and handling in the text

Analisi rates the risk ALTO: without a threat model, a security reviewer objects that an informed attacker can inject physiologically plausible, cross-modally consistent data that is undetectable by construction (analisi 10, fourth objection). The text must not claim detection of tampering in general, nor of all integrity attacks. It states the declared attack classes and the excluded ones, reports the undetectable cases as a result in the diagnosability matrix (WS02-T05), and names them as a limit in the Discussion (WS12). Statements about the cited works are limited to what analisi says about them, since the entries are unverified. Validation is technical and pre-clinical, so no sentence about these works implies clinical validation of this one.

## Unresolved and for human verification

- Six entries carry a dagger in analisi and need specific verification of venue, year or author list: `li-insulin-pump`, `camara-medical-device-security-survey`, `garbelini-sweyntooth`, `rostami-heart-to-heart`, `choi-control-invariants`, `shoukry-pycra` (rows 14, 16 to 20).
- FDA guidance (`fda-premarket-cybersecurity`, row 22): analisi gives the organisation and the year 2023 and describes the subject, but no title. The human supplies the title and the document identity if it is cited.
- Every entry lacks first names, full titles (except rows 14 and 21) and pages; the human adds them in WS03-T06.
