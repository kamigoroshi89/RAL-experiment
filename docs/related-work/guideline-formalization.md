# Related work note: guideline and pathway formalization (analisi 3.4)

Task WS03-T03. Bibliography fragment: `paper/refs/fragments/ws03-t03.bib` (rows 13 to 31 of the inventory). Every entry has `verified = {false}` (ADR-018); nothing here is verified.

## Scope

Analisi section 3.4, "Formalization of clinical guidelines and clinical pathways": computer-interpretable guideline formalisms, temporal abstraction, model checking of guidelines, declarative and online process monitoring, process mining and conformance checking in healthcare, BPMN for pathways, and healthcare standards. Nineteen entries, transcribed as analisi recalls them (a dagger marks specific uncertainty). Nothing has been added from other sources. One item, the SCIFF line of work, has no identified specific work and has no entry (see the unresolved section).

## Reference table

| Key | Authors as recalled | Year | Venue | Dagger | ref_status | Role in the text |
|---|---|---|---|---|---|---|
| `peleg-comparing-guideline-models` | Peleg and others | 2003 | JAMIA | no | recalled | model comparison |
| `ohno-machado-glif` | Ohno-Machado and others | 1998 | JAMIA | no | recalled | formalism (GLIF) |
| `fox-proforma` | Fox and Johns and Rahmanzadeh | 1998 | AI in Medicine | no | recalled | formalism (PROforma) |
| `shahar-miksch-johnson-asbru` | Shahar and Miksch and Johnson | 1998 | AI in Medicine | no | recalled | formalism (Asbru, Asgaard project) |
| `terenziani-glare` | Terenziani and others | 2001 | AI in Medicine | yes | recalled | formalism (GLARE) |
| `shahar-temporal-abstraction` | Shahar | 1997 | Artificial Intelligence | no | recalled | temporal abstraction |
| `tenteije-protocure` | ten Teije and others | 2006 | AI in Medicine | yes | recalled | model checking (Protocure) |
| `bottrighi-guideline-verification` | Bottrighi and others | 2010 | AI in Medicine | yes | recalled | model checking |
| `maggi-declare-monitoring` | Maggi and Montali and Westergaard and van der Aalst | 2011 | BPM | yes | recalled | declarative monitoring |
| `mans-process-mining-healthcare` | Mans and van der Aalst and Vanwersch | 2015 | series SpringerBriefs | no | recalled | process mining |
| `rojas-process-mining-healthcare` | Rojas and others | 2016 | Journal of Biomedical Informatics | no | recalled | process mining |
| `munoz-gama-process-mining-healthcare` | Munoz-Gama and others | 2022 | Journal of Biomedical Informatics | no | recalled | process mining |
| `carmona-conformance-checking` | Carmona and others | 2018 | publisher Springer | no | recalled | conformance checking |
| `burattin-online-conformance` | Burattin and others | 2018 | BPM | yes | recalled | online conformance checking |
| `braun-bpmn4cp` | Braun and others | 2014 | - | yes | recalled | BPMN for pathways |
| `hl7-fhir-plandefinition` | HL7 (title: FHIR PlanDefinition and CarePlan) | - | - | no | partial | standard |
| `hl7-cql` | - (title: Clinical Quality Language) | - | - | no | partial | standard |
| `arden-syntax` | - (title: Arden Syntax) | - | - | no | partial | standard |
| `openehr-gdl` | - (title: openEHR GDL) | - | - | no | partial | standard |

## What the reviewer expects

- Comparison of formalisms: Peleg and others, "Comparing computer-interpretable guideline models" (JAMIA, 2003).
- Formalisms: GLIF, Ohno-Machado and others (JAMIA, 1998); PROforma, Fox, Johns and Rahmanzadeh (AI in Medicine, 1998); Asbru, in the Asgaard project of Shahar, Miksch and Johnson (AI in Medicine, 1998); GLARE, Terenziani and others (dagger, AI in Medicine, 2001).
- Temporal abstraction: Shahar, knowledge-based temporal abstraction (Artificial Intelligence, 1997).
- Model checking of guidelines: the Protocure project, ten Teije and others (dagger, AI in Medicine, 2006); Bottrighi and others (dagger, AI in Medicine, 2010).
- Declarative monitoring with finite-trace semantics (Declare): Maggi, Montali, Westergaard and van der Aalst (dagger, BPM 2011).
- Guideline conformance with SCIFF: the line of work of Chesani, Mello, Montali and others (dagger; analisi asks to verify the specific work). No entry exists.
- Process mining in healthcare: Mans, van der Aalst and Vanwersch (SpringerBriefs, 2015); Rojas and others (Journal of Biomedical Informatics, 2016); Munoz-Gama and others (Journal of Biomedical Informatics, 2022).
- Conformance checking: Carmona and others (Springer, 2018); online conformance checking, Burattin and others (dagger, BPM 2018).
- BPMN for pathways: BPMN4CP, Braun and others (dagger, 2014).
- Standards: HL7 FHIR PlanDefinition and CarePlan, Clinical Quality Language, Arden Syntax, openEHR GDL.

Analisi adds that showing, even partially, a mapping from a standard representation (FHIR PlanDefinition or BPMN) to the pathway templates is a strong and cheap point. That mapping sketch is WS01-T07; this note does not describe it.

## Difference

Analisi: these approaches work on discrete events of the clinical record, often offline, for decision support or retrospective conformance. This work operates on continuous signals, with quantitative robustness, online, on an embodied agent.

Sentence for the third Related Work paragraph (identical to the one in `medical-cps-monitoring.md`):

> Unlike these works, which monitor a single device, controller or physiological property, or which reason offline over discrete events of the clinical record for decision support and retrospective conformance, we monitor adherence to a care process that spans several devices, the patient and an assistive robot, online, on continuous signals with quantitative robustness, and we attribute a cause to each alert.

Asbru already expresses intentions and temporal conditions that can be monitored during execution. The paper does not claim that treating guidelines as monitorable specifications is new.

## Risk and handling in the text

Analisi rates the risk ALTO on contribution 1. Asbru already expresses intentions and temporal conditions that can be monitored during execution, and online monitoring of clinical process constraints with temporal logics exists. The text says so, and repositions the contribution as quantitative, signal-level monitoring executed by a physical agent. "Reinterpret clinical pathways as runtime safety specifications" is not presented as a new idea.

Terminology: a Clinical Pathway is institutional and population-level. The objects of this paper are the "pathway template" and the "patient care plan" (glossary in `01-conventions.md`, section 7).

Hook: if WS01-T07 has produced a FHIR or BPMN mapping sketch when WS03-T05 runs, one clause may point to it; otherwise nothing is claimed.

## Unresolved and for human verification

- Six entries carry a dagger in analisi and need specific verification: `terenziani-glare`, `tenteije-protocure`, `bottrighi-guideline-verification`, `maggi-declare-monitoring`, `burattin-online-conformance`, `braun-bpmn4cp` (rows 17, 19, 20, 21, 26, 27).
- Four standards are `partial`: `hl7-fhir-plandefinition`, `hl7-cql`, `arden-syntax`, `openehr-gdl` (rows 28 to 31). Analisi gives no author, year or edition; the human decides which edition or specification document to cite, if any.
- SCIFF: analisi marks the line of work of Chesani, Mello, Montali and others with a dagger and says to verify the specific work. No specific work is identified, so there is no bibliography entry, the item is not cited in the draft, and it is handed to WS03-T06. If the human chooses a specific work, the entry key to use is `chesani-sciff-conformance`.
- Every entry lacks first names, full titles (except rows 13 and 28 to 31), pages and DOIs; the human adds them in WS03-T06.
