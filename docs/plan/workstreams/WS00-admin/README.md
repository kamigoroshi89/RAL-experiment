# WS00-admin: Admin and human decisions

## Objective

Settle the administrative, scope and access questions that no agent can settle and that the rest of the plan depends on. WS00 holds ten human tasks: verify the call for papers (CFP); take the three scope decisions of analisi §9 item 0.2 and confirm or overturn the ADRs left in status `proposed`; recruit a clinician (and if possible a runtime-verification or STL collaborator); start PhysioNet credentialing; check TIAGo and ROS 2 simulation availability and decide ADR-011; check ethics rules; obtain the clinician review of the parameter registry (the M1 gate); and three hand-offs added at reconciliation because agents have no network access and cannot verify values: full text of key papers (T08), download of open datasets (T09), verification of the literature-prior provenance table (T10). Every task ends in a written artefact under `outputs/`, so an agent can check that the human step happened and read its result. Total estimate: 9.25 person-days (analisi §9 phase 0, plus the two tasks derived from analisi §5.3, §5.7 and §4.2).

## Inputs

- `docs/source/analisi.md`: §9 phase 0 (rows 0.1, 0.2, 0.3, 0.6, 0.7), §5.1 to §5.3, §5.7, §4.2, §3.6, §4.9, §7, §10; reviewer findings in `docs/source/review.md` (R3 weaknesses 2 to 4, R2 weakness 7).
- `docs/plan/03-decisions.md`: ADR-001 to ADR-003 (to be confirmed), ADR-005 (PriorSource, credentialing), ADR-011 to ADR-017 (status `proposed`, to be confirmed or overturned), ADR-020 (unverified clinical parameters).
- `docs/plan/02-interfaces.md`: `#priorsource`, `#ros-2-interfaces`, `#parameter-registry`.
- `docs/plan/00-master-plan.md`: milestones M0 and M1, critical path, cut order (section 7).
- From other workstreams: the parameter registry and the template table (WS01-T02, WS01-T03), consumed by WS00-T07.

## Outputs

One artefact per task in `docs/plan/workstreams/WS00-admin/outputs/`, named by task id. The folder is created by the human who executes the first task; plan authors do not create it.

| Artefact | Task | Consumed by |
|---|---|---|
| `outputs/WS00-T01.md` | CFP facts | WS00-T02, WS12-T01, WS12-T02, WS12-T03, WS12-T08 |
| `outputs/WS00-T02.md` and updated status lines in `docs/plan/03-decisions.md` | scope decisions, ADR 012 to 017 outcome | WS01-T01, WS12-T01, WS00-T03, WS00-T06 |
| `outputs/WS00-T03.md` | clinician and collaborator | WS00-T07, WS11-T01, WS00-T06 |
| `outputs/WS00-T04.md` | credentialing status | WS04-T13, WS08-T06 |
| `outputs/WS00-T05.md` and ADR-011 outcome in `docs/plan/03-decisions.md` | TIAGo and simulation availability | WS07-T01, WS10-T01 |
| `outputs/WS00-T06.md` | ethics requirements and lead times | WS10-T01, WS11-T01 |
| `outputs/WS00-T07.md` and `reviewed_by` fields in the registry YAML | clinician review | M1 gate, WS04-T02, WS05-T03, WS06-T02 |
| `outputs/WS00-T08.md` and `data/raw/papers/` | full text of key papers | WS06-T06, WS03-T02 |
| `outputs/WS00-T09.md` and `data/raw/<dataset>/` | open datasets and licences | WS04-T06, WS13-T04 |
| `outputs/WS00-T10.md` and `verified_by` fields in the prior YAML | verified literature priors | WS12-T06, WS13-T04 |

Artefact convention (all ten files):

1. The first two lines are `completed_by: <name>` and `completed_on: <YYYY-MM-DD>`.
2. Every required field is an H2 heading with the exact name given in the task; the body is never empty.
3. A value read from a document carries a `Source:` line (document, section, address, date consulted). A value the source does not give is written as `not stated in <source>` together with the date the question was sent and, when it arrives, the answer. Values are never copied from analisi as if they were facts about the CFP, the robot or a dataset.
4. No personal contact details are stored in the repository: names, roles and institutions only.

## Dependencies

- Upstream, inside WS00: WS00-T02 needs T01; T03 and T06 need T02; T07 needs T03. T01, T04 and T05 have no dependency and start on day one (`00-master-plan.md` section 6).
- Upstream, other workstreams: WS00-T07 needs WS01-T03 (registry design and `configs/registry/hypertension.yaml`).
- Downstream: WS01-T01 (needs T02); WS12-T01 (needs T02); WS12-T02 (needs T01); WS07-T01 (needs T05); WS04-T13 (needs T04, and therefore credentialing actually granted); WS10-T01 (needs T06); WS11-T01 (needs T03 and T06).
- Milestones: M0 needs T01 and T02 (plus WS12 title and abstract); M1 needs the clinician review of T07 in addition to WS01.
- Contract anchors: `02-interfaces.md#priorsource` (T04), `02-interfaces.md#ros-2-interfaces` (T05), `02-interfaces.md#parameter-registry` (T07). No task in WS00 edits a contract; a change forced by a human decision goes through an ADR (`01-conventions.md` section 6).

## Acceptance criteria

1. `test -f docs/plan/workstreams/WS00-admin/outputs/WS00-T0N.md` exits 0 for N = 1 to 10, and each file contains every H2 field named in its task (each task's Done when gives the `grep -c` count).
2. From the repository root, `grep -cE '^## ADR-01[1-7] .*\[DA-' docs/plan/03-decisions.md` prints 0: every ADR from 011 to 017 has been confirmed or superseded by a human.
3. `outputs/WS00-T02.md` records ADR-001, ADR-002 and ADR-003 with the decision, the decision-makers and the date.
4. `outputs/WS00-T04.md` shows an `access_status:` of `granted` or `refused` for MIMIC-IV and for eICU, with `refused` accompanied by its consequence for WS08 (ADR-005).
5. `outputs/WS00-T05.md` names the ROS 2 distribution and Gazebo generation that WS07 will use, and ADR-011 in `03-decisions.md` is accepted or superseded.
6. `outputs/WS00-T07.md` covers every entry of the registry; entries without `reviewed_by` are listed and will be reported as unverified (ADR-020).
7. No file in this folder contains the tokens forbidden by `AUTHORING-BRIEF.md`.

## Source sections

- analisi §9 phase 0, rows 0.1, 0.2, 0.3, 0.6, 0.7 (roadmap).
- analisi §7 (page budget in the worst case), §8.3 and §8.4 (title and abstract for the commitment letter).
- analisi §3.6, §4.5, §4.9 item 1, §10 (scope decisions: C3, threat model, distributed architecture, pre-clinical validation).
- analisi §5.1 (public sources, credentialing), §5.2 (simulation, TIAGo packages, onboard computer), §5.3 (lab with volunteers), §5.7 (vignette study).
- analisi §4.2 (scales and priorities), §2 R3 weaknesses 3 and 4 (drug anchoring, taxonomy).

## Tasks

| id | title | owner | status | depends_on |
|---|---|---|---|---|
| WS00-T01 | Verify CFP: deadlines, page limit, prior-publication policy, commitment letter content | human | ready | - |
| WS00-T02 | Scope decisions: one pathology, C3 as integrity violations, distributed architecture | human | blocked | WS00-T01 |
| WS00-T03 | Recruit a clinician and, if possible, an RV/STL collaborator | human | blocked | WS00-T02 |
| WS00-T04 | Start PhysioNet credentialing for MIMIC-IV and eICU | human | ready | - |
| WS00-T05 | Check real TIAGo or TIAGo Pro availability and ROS 2 simulation packages | human | ready | - |
| WS00-T06 | Check ethics rules for lab volunteers and the vignette study | human | blocked | WS00-T02 |
| WS00-T07 | Clinician review of parameter registry, taxonomy and priorities (M1 gate) | human | blocked | WS00-T03, WS01-T03, WS01-T04, WS01-T05, WS02-T04 |
| WS00-T08 | Obtain full text of the key reference papers needed by implementers (Lindemann et al. ICCPS 2023 first) | human | ready | - |
| WS00-T09 | Download the open datasets into data/raw/ and record their licences (VitalDB, MIT-BIH noise stress test, BIDMC, CinC 2015) | human | ready | - |
| WS00-T10 | Verify the literature-prior provenance table produced by WS04-T02 | human | blocked | WS04-T02 |
