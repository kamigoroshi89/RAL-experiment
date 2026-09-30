---
id: WS00-T06
title: "Check ethics rules for lab volunteers and the vignette study"
workstream: WS00-admin
owner: human
status: ready
depends_on: ["WS00-T02"]
critical_path: false
non_negotiable: false
estimate_pd: 0.5
sources: ["analisi §5.3", "analisi §5.7", "analisi §9 (11)"]
interfaces: []
review_items: []
---
## Obiettivo

Find out, from the ethics committee or the responsible office of each institution involved, which rules apply to two activities of the plan: the lab demo with human volunteers (analisi §5.3: healthy volunteers with non-invasive devices, or a mannequin with emulated signals) and the online vignette study with 8 to 15 nurses or physicians (analisi §5.7: whether ethical approval or an exemption is needed). Concrete output: `docs/plan/workstreams/WS00-admin/outputs/WS00-T06.md` with the requirement, the documents and the lead time for each activity, so that WS10-T01 and WS11-T01 can plan around them and the schedule can decide early whether the activity goes ahead. Analisi §9 item 11 counts the ethics lead time on top of the 3 person-weeks of the vignette study, and the cut order puts the vignette study first (`00-master-plan.md` section 7).

## Contesto

- `docs/source/analisi.md` §5.3 (real robot in the lab, human volunteers, mannequin alternative) and §5.7 (vignette study format, measures, "verificate se serve approvazione etica o se basta un'esenzione").
- `docs/source/analisi.md` §9 rows 10 and 11 (lab demo effort; vignette study "3 pw più tempi etici").
- `docs/plan/00-master-plan.md` sections 3 (M4), 4 (WS10 and WS11 are tails) and 7 (cut order).
- `docs/plan/workstreams/WS00-admin/outputs/WS00-T02.md` (scope), `outputs/WS00-T01.md` (deadline) and `outputs/WS00-T03.md` (clinician and partner hospital; the committee of the partner hospital may be the relevant one).
- The rules and forms of the ethics committee of each institution, which the human obtains.

Blocked until WS00-T02 is done: the scope decisions fix which studies remain in the plan, so `outputs/WS00-T02.md` must exist first.

## File toccati

- `docs/plan/workstreams/WS00-admin/outputs/WS00-T06.md` (create)

## Test

Verification checks:

1. The artefact starts with `completed_by:` and `completed_on:` lines and contains the six H2 fields of Done when, each non-empty and each with a `Source:` line (rule, form or message from the committee, with its date) or `not stated in <source>` with the date the question was sent.
2. `## Institutions and bodies` names each institution involved (the authors' institution, the partner hospital if any) and the committee or office that decides for it, by name of the body and role of the contact.
3. `## Lab demo with volunteers` states for the volunteer variant (healthy volunteers, non-invasive devices) one of: approval required, exemption available, or not required, with the document that says so, the documents to submit and the lead time.
4. `## Lab demo mannequin variant` states whether the mannequin with emulated signals removes the need for approval, according to whom, and what the lab safety review (WS10-T01) still has to cover.
5. `## Vignette study` states for the online within-subject study with 8 to 15 nurses or physicians: approval or exemption, which committee decides, the documents required (protocol, information sheet, consent form, recruitment text, or as the committee lists them), and the lead time.
6. `## Data protection for study data` records what data the study would collect, whether responses can be anonymous, where they are stored, for how long, and the rules the committee or the institution states for handling them.
7. `## Decision and schedule` states for each activity: go ahead, go ahead with the lighter variant, or drop. It gives the latest date to submit the application, computed backwards from the full-submission deadline in `outputs/WS00-T01.md` using the committee's lead time plus the durations that the decision-makers assume for the study run and its analysis (WS10-T05, or WS11-T05 and WS11-T06), each duration labelled as a planning assumption, and it states the consequence of missing that date using the cut order (`00-master-plan.md` section 7: vignette study first, lab demo replaced by a simulation video second).
8. Every committee lead time is a value given by the committee or office, not an estimate by the author of the artefact; where none was given the field says so.

## Passi

1. Read `outputs/WS00-T02.md` and `outputs/WS00-T03.md` to see which activities are in scope and which institution the clinician belongs to.
2. Identify the ethics committee or responsible office of each institution and ask them the questions of checks 3 to 6 in writing, describing the two activities as in analisi §5.3 and §5.7. Fill `## Institutions and bodies` and record the date of each question.
3. Fill `## Lab demo with volunteers` and `## Lab demo mannequin variant` from the answers. Ask explicitly whether a mannequin with emulated signals needs no approval, since analisi §5.3 says it avoids the problem but does not say who decides.
4. Fill `## Vignette study` and `## Data protection for study data` from the answers, including the documents the committee requires.
5. Compute the latest application date for each activity from the deadline in `outputs/WS00-T01.md` and the lead times in the artefact; fill `## Decision and schedule` and ask the decision-makers of WS00-T02 to confirm go, lighter variant or drop.
6. Set `status: done` in this task file and tell the owners of WS10-T01 and WS11-T01 that the requirements are recorded.

## Done when

From the repository root:

- `test -f docs/plan/workstreams/WS00-admin/outputs/WS00-T06.md` exits 0.
- `grep -cE '^## (Institutions and bodies|Lab demo with volunteers|Lab demo mannequin variant|Vignette study|Data protection for study data|Decision and schedule)$' docs/plan/workstreams/WS00-admin/outputs/WS00-T06.md` prints `6`.
- `grep -c '^completed_by: .\+' docs/plan/workstreams/WS00-admin/outputs/WS00-T06.md` prints `1`.
- Inspection: checks 3, 5 and 7 hold, and every lead time carries its `Source:` line.
