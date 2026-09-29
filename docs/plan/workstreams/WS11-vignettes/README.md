# WS11-vignettes: Clinician vignette study

OPTIONAL workstream, and the first item in the cut order of `docs/plan/00-master-plan.md` section 7 (analisi §9: cut item 11 first, then the lab demo, then the second pathology). No task of another workstream depends on it. WS08 and WS12 must be able to finish, and the paper must be able to stand, without it.

## Objective

Run the qualitative check with clinicians that analisi §5.7 describes: an online, within-subject vignette study with 8 to 15 nurses or physicians of a partner hospital. The same event is shown in three conditions: a threshold alarm, an anomaly score, and an RSM alert rendered in natural language (violated template, severity, confidence, attributed cause). Five measures are taken: action correctness against a key defined by an expert, decision time, perceived interpretability (Likert), trust with a validated scale (Jian et al. 2000, marked unverified in analisi §5.7 and verified by a human in WS11-T03), and behaviour when severity (σ̃) and confidence (ρ) diverge, the question the workshop paper raises in its §IV. A ranking block, included by default, asks participants to order a set of alerts by urgency so that the agreement with `rank_alerts` can be computed (analisi §5.5, ADR-009; `severity_rank_agreement` of `#metrics`).

The study answers the part of reviewer concern R3-W6 (analisi §2 R3 weakness 6) that needs users: whether a nurse can understand and act on the natural-language rendering of an alert, which is also the evidence that analisi §4.8 asks for behind the wording "specification-level traceability". It does not measure alarm fatigue. The expected alert load per shift (R3 question 5) comes from the false alarms per patient-day of WS04-T12 and WS08. Who receives an alert, through which channel and with which escalation is a design statement (ADR-003, WS01-T07); the vignettes only place the participant in that workflow and check the escalation choices. The write-up (WS11-T06) states this split explicitly.

The study is technical and pre-clinical: synthetic vignettes generated from the benchmark, no real patients, no clinical claim (analisi §5). With 8 to 15 participants every analysis is exploratory and is reported as such.

If this workstream is cut, the paper drops every statement about how clinicians read the alerts and keeps the natural-language rendering as a demonstration only. WS12-T06 then lists "no user study" among the limitations, and R3-W6 stays covered only by WS05-T07 (rendering), WS01-T07 (FHIR and BPMN mapping sketch) and WS08 (alert load).

## Inputs

- `docs/source/analisi.md` §5.7 (format, conditions, measures), §2 R3 weakness 6 and question 5, §4.8, §4.5, §4.4, §4.2, §5.5, §5.8, §9 item 11.
- The workshop paper `Clinical_Pathways_Physical_AI_IJCAI-ECAI_2026.pdf`, §IV: clinicians' interpretation of RSM outputs "especially when severity and confidence diverge".
- Contracts: `02-interfaces.md#alert`, `#trace-schema`, `#metrics` (the ones listed in INDEX), plus `#template` (`rank_alerts`, template names), `#parameter-registry` (band limits shown in the threshold alarm, scales), `#priorsource` (through the benchmark), which the ownership table of `02-interfaces.md` lists WS11 as consumer of.
- `docs/plan/03-decisions.md`: ADR-003 (alerts reach the nurse; fallback escalates to the nurse), ADR-004 (DISPENSE is not INTAKE), ADR-009 (ranking), ADR-018 and ADR-020 (unverified references and parameters are reported as such).
- Human inputs: `docs/plan/workstreams/WS00-admin/outputs/WS00-T03.md` (clinician and partner hospital access), `outputs/WS00-T06.md` (ethics outcome and lead time for the vignette study).
- Code inputs (packages built by other workstreams): the benchmark builder (WS04-T11), the attribution package with natural-language rendering (WS05-T07), the baselines B1 and B2 (WS06-T02, WS06-T03).

## Outputs

| Path | Produced by | Content |
|---|---|---|
| `study/design.md` | WS11-T01 | Research questions, conditions, event families, measures, counterbalancing, analysis plan, threats to validity, R3-W6 coverage |
| `study/protocol.yaml` | WS11-T01 (trust items and `verified_by` filled by WS11-T03) | Machine-readable protocol, instruments, response schema, analysis parameters |
| `study/ethics-dossier.md` | WS11-T01 | Material for the ethics approval or exemption; consent text section read by WS11-T04 |
| `study/build_vignettes.py`, `study/vignettes/`, `tests/study/` | WS11-T02 | Vignette families in three renderings, ranking set, manifest, pilot pack |
| `study/answer-key-draft.yaml` | WS11-T02 | Draft key with action catalogue, status `draft` |
| `study/answer-key.yaml` | WS11-T03 | Key validated by the clinician, status `validated` |
| `docs/plan/workstreams/WS11-vignettes/outputs/WS11-T03.md` | WS11-T03 (human) | Validation and pilot record |
| `study/schedule.py`, `study/responses.py`, `study/build_app.py`, `study/app/` | WS11-T04 | Counterbalancing schedule, response validator, static web app |
| `docs/plan/workstreams/WS11-vignettes/outputs/WS11-T05.md` | WS11-T05 (human) | Recruitment and run record |
| `data/raw/vignette-responses/` | WS11-T05 (human) | One exported response file per participant; gitignored, never committed |
| `study/analysis.py`, `study/writeup.template.md`, `study/writeup.md`, `outputs/vignettes/` | WS11-T06 | Analysis, write-up with generated tables, `metrics.json` |

Nothing is written to `src/`. Humans create the two `outputs/` artefacts under this workstream folder; agents do not.

## Dependencies

Other workstreams (from INDEX):

- WS00-T03 (clinician collaborator and partner hospital access) and WS00-T06 (ethics rules and lead time): read by WS11-T01. The ethics lead time is external and long. The ethics dossier (WS11-T01) is written early so that the application can be lodged in parallel with WS11-T02 to WS11-T04; WS11-T05 does not start before the outcome is recorded.
- WS01-T07 (alert tuple, traceability wording, FHIR and BPMN mapping sketch): fixes what the RSM condition shows and how the workflow is described.
- WS05-T07 (attribution package, natural-language rendering) and WS04-T11 (benchmark builder): read by WS11-T02.
- Not captured in `depends_on` and stated as a precondition in WS11-T02: the baselines B1 and B2 from WS06-T02 and WS06-T03 provide the threshold alarm and anomaly score renderings. WS11-T06 optionally compares with the ordering used for ablation A3 (WS08-T03) if that task defines it.
- Consumers: WS12 (a subsection of Section V and the limitations if the study is run) and WS13 (the anonymised snapshot must not contain participant data or institution names; `data/raw/` is gitignored, `study/ethics-dossier.md` and the write-up carry no institution names).

Contract anchors: `02-interfaces.md#alert` (T01, T02), `#trace-schema` (T02), `#metrics` (T06: `severity_rank_agreement`).

## Acceptance criteria

1. `python3 tools/check_plan.py` passes for this folder: the six task files exist, and their frontmatter matches the WS11 table of `docs/plan/workstreams/INDEX.md`.
2. `grep -l OPTIONAL docs/plan/workstreams/WS11-vignettes/README.md docs/plan/workstreams/WS11-vignettes/tasks/*.md` lists seven files.
3. The protocol is fixed before data collection: `study/design.md` and `study/protocol.yaml` exist before `outputs/WS11-T05.md` is created, and every later deviation appears in the `Deviation log` field of that artefact.
4. Each of the five measures of analisi §5.7 (M1 action correctness, M2 decision time, M3 perceived interpretability, M4 trust, M5 behaviour when severity and confidence diverge) has an instrument in `study/protocol.yaml` and an analysis in `study/analysis.py`.
5. Every event family is rendered in all three conditions from the same benchmark event, the RSM rendering is the text produced by the attribution package (`Explanation.text`), and no condition contains information of another (tests of WS11-T02).
6. No answer key, ground-truth label or latent value reaches the participant-facing files (tests of WS11-T02 and WS11-T04).
7. The trust scale items in `study/protocol.yaml` were transcribed from the original publication and verified by a named human (`trust_scale.verified_by` is not null); until then the app build fails.
8. The ethics status recorded in `outputs/WS11-T03.md` and `outputs/WS11-T05.md` matches `outputs/WS00-T06.md` (approval, exemption or not required), and no participant, including pilot participants, took part before that status was recorded.
9. `completed_count` in `outputs/WS11-T05.md` is between 8 and 15, or the write-up labels the study a descriptive pilot and states the shortfall.
10. Every number in `study/writeup.md` is generated by `study/analysis.py` from `data/raw/vignette-responses/`; `pytest tests/study -q` and `ruff check study tests` exit 0.
11. No personal data is committed: `data/raw/` stays gitignored, the generated `study/writeup.md` holds aggregates only, and neither the write-up nor the ethics dossier names the hospital, the committee or a person.
12. The write-up states which parts of R3-W6 the study covers, which parts other workstreams cover, and uses the wording of analisi §4.8 (specification-level traceability, complementary, cause-based taxonomy). It claims no clinical efficacy.

## Source sections

- analisi §5.7 (vignette study), §5.8 (status: optional, high value for R3), §9 item 11 and cut order.
- analisi §2 R3 weakness 6 (alert workflow, alarm fatigue, natural-language rendering with user verification) and R3 question 5.
- analisi §4.8 (traceability wording, "complementary"), §4.5 (diagnosability matrix, cascades, abstention: source of the event families), §4.4 (ρ), §4.2 (σ̃, lexicographic ranking), §4.9 items 3 and 4 (cascades, clinician in the loop), §5.1 item 4 (confounders), §5.5 (optional rank agreement).
- Workshop paper §IV (severity and confidence diverge).

## Tasks

| id | title | owner | status | depends_on |
|---|---|---|---|---|
| WS11-T01 | Vignette study design and measures | agent | blocked | WS00-T03, WS00-T06, WS01-T07 |
| WS11-T02 | Vignette generation, natural-language alerts, answer key draft | agent | blocked | WS11-T01, WS05-T07, WS04-T11, WS06-T02, WS06-T03 |
| WS11-T03 | Clinician answer-key validation and pilot | human | blocked | WS11-T02 |
| WS11-T04 | Online study implementation | agent | blocked | WS11-T03 |
| WS11-T05 | Recruitment and study run (8-15 participants) | human | blocked | WS11-T04 |
| WS11-T06 | Study analysis and write-up | agent | blocked | WS11-T05 |
