# 00 Master plan

Everything here derives from `docs/source/analisi.md` (cited as "analisi §x"). Effort is in person-weeks (pw) unless stated. Numbers not present in the analysis are not given.

## 1. Goal

Turn the IJCAI-ECAI 2026 workshop paper into a submission-ready IEEE RA-L paper (6 pages, references possibly included: analisi §7) with:

1. a complete formal specification (past-time STL templates, normalised severity, three-valued online semantics, operational definitions of ρ and κ, Proposition 1);
2. an explicit fault model, threat model and diagnosability matrix;
3. a semi-synthetic benchmark with latent ground truth and public-data-derived parameters;
4. baselines B1-B5 and ablations A1-A7, with B5 and A4 mandatory;
5. a ROS 2 implementation evaluated in simulation on a TIAGo-class robot, and (strongly recommended) a mock-ward lab demo;
6. an open-source, anonymisable release.

The claim to defend (analisi §3.7): the *combination*, verified experimentally, of (i) STL templates from care plans over sparse mixed signals with clinically normalised severity, (ii) three-valued verdicts that formally separate measured evidence from conformal prediction, (iii) an attribution layer using embodiment as an evidence channel, whose contribution is measured. Validation is technical and pre-clinical; no real patients (analisi §5).

## 2. Workstreams and effort

Effort per workstream is taken from analisi §9. WS00 rows come from the phase-0 table.

| WS | Content (§9 item) | Effort | Depends on (§9) |
|---|---|---|---|
| WS00 | Admin and human decisions: CFP check (0.1), scope decisions (0.2), clinician and RV collaborator (0.3), PhysioNet credentialing (0.6), TIAGo availability (0.7); plus hand-offs added at reconciliation (ADR-023): ethics rules check, clinician review of the registry, reference PDFs, open datasets, provenance verification | 0.1: 0.5 d; 0.2: 2-3 d; 0.6: 1 d + wait; 0.7: 1 d; 0.3: contacts; hand-offs: 0.5-1 d each (not in analisi §9) | 0.2 after 0.1 |
| WS01 | Formalization: problem formulation, templates, normalisation, ρ, three-valued semantics, Proposition 1 (1) | 3-4 pw | 0.2 |
| WS02 | Threat model, fault model, diagnosability matrix, attribution rule with abstention (2) | 1-2 pw | WS01 |
| WS03 | Related work and verified references (3) | 1.5 pw | parallel |
| WS04 | Benchmark generator (4) | 4-6 pw | 0.6, WS01 |
| WS05 | Monitor, conformal calibrator, attribution as `ralmon` core plus ROS 2 nodes (5) | 4-5 pw | WS01, WS02 |
| WS06 | Baselines B1-B5 (6) | 2-3 pw | WS04 |
| WS07 | ROS 2 and Gazebo simulation with TIAGo, robot faults, latency, deadline predictive monitoring (7) | 3-4 pw | WS05 |
| WS08 | Main experiments, ablations A1-A6, shift test, unlabeled real-data run (8) | 3 pw | WS04, WS05, WS06 |
| WS09 | Figures 1-3 and Tables I-III (9) | 1.5 pw | WS08 |
| WS10 | Real-robot lab demo (10) | 3 pw | WS07 |
| WS11 | Clinician vignette study (11) | 3 pw plus ethics lead time | WS05, 0.3 |
| WS12 | Writing, internal devil's-advocate review, title (0.4) and abstract (0.5) (12) | 2-3 pw | all |
| WS13 | Open-source repository (13) | 1 pw | WS05, WS04 |

The plan's task estimates add up to about 201 person-days (about 40 pw) including the optional second pathology; the total of analisi §9 is about 33-42 pw, feasible for 3-4 people in 3-4 months (roughly 14-16 weeks for the full submission) if WS04, WS05 and WS07 run in parallel.

## 3. Milestones

| Id | Milestone | Gate (verifiable) |
|---|---|---|
| M0 | Commitment letter ready (analisi §9, weeks 1-2) | WS00-T01, T02 done; title and abstract without numbers written (WS12) |
| M1 | Formalization frozen | WS01 done (the freeze WS01-T08 follows the clinician review WS00-T07 of registry, normalisation, verdict semantics and taxonomy); contract amendments decided by ADR (ADR-021); `02-interfaces.md` versions agreed |
| M2 | Core running offline | WS04 generator produces traces with latent ground truth; WS05 monitor emits verdicts and alerts on them; unit and property tests green |
| M3 | Baselines and main results | WS06 B1-B5 run on the same traces; WS08 main table and A1-A4 produced |
| M4 | Robot evidence | WS07 latency and robot-fault results; WS10 lab demo (or fallback video, see cut order) |
| M5 | Submission | WS09 figures and tables final; WS12 paper compiled and reviewed with analisi as checklist; WS13 repository anonymised |

## 4. Critical path and parallelism

Dependencies follow analisi §9 literally.

- Root: WS00-T01 (CFP) → WS00-T02 (scope) → WS01.
- Chain A (benchmark): WS01 → WS04 → WS06 → WS08 → WS09 → WS12. WS04 also needs PhysioNet credentialing (WS00-T04), which has an external wait, so it starts on day one.
- Chain B (monitor): WS01 → WS02 → WS05 → WS08 (and → WS07 → WS10).
- WS03 (related work) and the paper skeleton in WS12 run in parallel from the start.
- WS04, WS05 and WS07 must run concurrently (analisi §9). This is only possible because `02-interfaces.md` freezes the contracts early: WS04 and WS05 code against the trace schema, template and alert types while WS01 finishes the prose.
- WS08 is the merge point: it needs WS04, WS05 and WS06 complete.
- WS10 and WS11 are tails: they improve the paper but do not block WS08.

Tasks on the critical path carry `critical_path: true`. Agents choose them first (see `CLAUDE.md`).

## 5. Not to be cut

Analisi §9: "Non tagliate B5, A4 né la formalizzazione."

- **WS01, all tasks** (formalization).
- **B5**: the conformal STL predictive-monitoring baseline after Lindemann et al. 2023 (indispensable to defend novelty, analisi §5.4 and §10).
- **A4**: ablation removing the embodied channel (answers "why a robot?", analisi §5.6).
- Also indispensable per analisi §5.8: threat/fault model with diagnosability matrix, semi-synthetic benchmark with latent ground truth, baselines B1-B5, ablations A1-A4, ROS 2 simulation with latency and robot faults.

These are marked `non_negotiable: true` in task frontmatter (B5, A4, WS01). The remaining indispensable items are protected by dependencies and by the review traceability.

## 6. Order of attack

1. Day 1, in parallel: WS00-T01 (CFP), WS00-T04 (start PhysioNet credentialing), WS00-T05 (TIAGo and simulation packages), WS03 start.
2. WS00-T02 scope decisions (one main pathology, C3 reduced to integrity violations with threat model, distributed architecture), then WS00-T03 contact clinician.
3. WS01 first tasks freeze the template table and normalisation; then WS02.
4. WS05-T01 scaffolding as soon as contracts are frozen; WS04 and WS05 proceed in parallel against the contracts.
5. WS06 after WS04 traces exist; WS07 after the WS05 core; WS08 when WS04, WS05 and WS06 are done.
6. WS09 figures, WS10 lab demo, WS11 vignettes; WS12 throughout, final pass last; WS13 at the end.

## 7. Cut order if time is short

Analisi §9: cut in this order: (1) WS11 vignette study; (2) WS10 lab demo, replaced by a simulation video, accepting that it weakens the robotics fit; (3) the second pathology (optional task in WS04). The list in section 5 is never cut.

## 8. Risks tracked by the plan

The three residual objections of analisi §10 plus the fourth about C3 are each mapped to workstreams in `04-review-traceability.md`: circular semi-synthetic evaluation (WS04, WS08), incremental conformal-STL application (WS03, WS06 B5, WS01 Proposition 1), and "robot not needed" (WS05, WS07, WS08 A4, WS10).
