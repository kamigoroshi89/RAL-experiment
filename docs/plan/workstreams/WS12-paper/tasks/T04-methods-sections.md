---
id: WS12-T04
title: Sections III and IV (formulation and methods)
workstream: WS12-paper
owner: agent
status: blocked
depends_on: ["WS01-T08", "WS02-T05", "WS12-T02", "WS00-T07"]
critical_path: true
non_negotiable: false
estimate_pd: 3
sources: ["analisi §4", "analisi §7", "analisi §8.1", "analisi §4.8"]
interfaces: ["02-interfaces.md#template", "02-interfaces.md#alert"]
review_items: ["R2-W8", "R2-W9", "AE-5"]
---
## Obiettivo

Write Section III (Problem Formulation, budget 0.50 page) and Section IV (subsections A to E, budgets 0.50, 0.30, 0.45, 0.30, 0.15 page) in `paper/sections/03-formulation.tex` and `paper/sections/04-method.tex`, from the frozen formalization (WS01-T08), the fault and threat model and diagnosability matrix (WS02), and the contracts `#template` and `#alert`.

Closes R2-W8 (the forecaster must not read as residual-based anomaly detection, which is what baseline B2 is), R2-W9 (no unsupported claim that the forecaster gives "robust evaluation under noise"; "robustness" is reserved to STL, "noise tolerance" is used only if measured) and AE-5 (no internal inconsistency in units, verdict timing, measured versus conformal, or C3 identifiability). Concrete output: the two section files, Table I and Fig. 1 included from WS09, updated `paper/PAGE_BUDGET.md`.

## Contesto

Blocked until WS01-T08, WS02-T05 and WS12-T02 are `done`.

- `docs/source/analisi.md` §4 (4.1 to 4.9) for the content and §7 rows III and IV-A to IV-E for budgets and floats.
- `docs/plan/02-interfaces.md#template` (Template, TemplateInstance, CarePlan, `normalise`, `rank_alerts`).
- `docs/plan/02-interfaces.md#alert` (tuple, `Explanation`, cascade fields).
- `docs/formal/README.md` and files `01-signals-sampling.md`, `02-templates.md`, `04-normalisation-ranking.md`, `05-three-valued-semantics.md`, `06-rho-proposition1.md`, `07-alert-tuple-mapping.md` (WS01; the README of WS01 maps them to Sections III, IV-A, IV-B and IV-C).
- `docs/models/fault-model.md`, `threat-model.md`, `evidence-channels.md`, `attribution-rule.md`, `diagnosability-hazards.md` and `configs/diagnosability.yaml` (WS02).

## File toccati

- `paper/sections/03-formulation.tex` (modify)
- `paper/sections/04-method.tex` (modify)
- `paper/PAGE_BUDGET.md` (modify: measured size per subsection, ledger, cut ledger items 2 and 4 closed)

## Test

Documents task: verification checks. Run them before drafting (they fail on the empty skeleton) and after.

1. Table I slot: every template of the frozen library appears with formula, unit (`RobustnessUnit`), scale `s_pi` and priority, and the row count equals `\NTemplates` (macro of `paper/tables/table1_macros.tex`). The tabular comes from WS09-T04 and is wrapped here in `table` or `table*` with the caption and label written here; the section never retypes it. If WS09-T04 has not produced the file when this task runs (it is not a dependency of this task), the slot stays a labelled empty box and this check is re-run by WS12-T06.
2. Notation: the alert tuple is written as the tuple of tau, kappa, sigma-tilde, rho, xi with tilde on the normalised robustness; sigma without tilde means raw robustness, and appears only where raw robustness is meant.
3. The decomposition phi = phi_CP and phi_SYS and phi_INT is stated in Section III and "phi_CP" is used only for care-plan constraints (`01-conventions.md` section 7).
4. Verdicts: the text states VIOLATED iff the upper bound of the robustness interval is below 0, SATISFIED iff the lower bound is above 0, otherwise PENDING; PREDICTED-VIOLATION exists only inside PENDING; conformal prediction acts only in PENDING and never produces a definitive verdict (`#verdict` semantics 1 to 3). `grep -n 'conformal' paper/sections/04-method.tex` shows no sentence that gives conformal prediction a role on measured values.
5. The maximum latency of a definitive verdict is stated as a property of each template (delta 2, or the window W plus the monitor period) and the reorder-buffer delay is included; no example or figure caption shows a verdict earlier than the window closes (analisi §4.6, the impossible 21:02 verdict of the workshop table must not reappear).
6. Proposition 1 is stated with the quantifiers of the WS01-T06 output, the proof takes at most four lines, and the text names the three caveats: calibration unit is the patient episode, coverage is marginal over the population (not per patient), alpha is allocated over the tests of a patient-day. The phrase "distribution-free coverage" is absent.
7. The table of rho has three rows (measured violation, predicted violation, deterministic predicate) each with its guarantee (conditional on the device error model; marginal under exchangeability across episodes; conditional on log integrity). Authenticity is stated to belong to kappa, not to rho.
8. Severity and confidence are called "complementary" (never "orthogonal"); ranking is lexicographic by clinician priority then normalised robustness; normalisation by the width of a conformal interval is explicitly excluded.
9. The forecaster paragraph states what it predicts (continuous signals and robot care-delivery deadlines, per `#forecaster`), that definitive verdicts do not depend on it, and that blood pressure with a few measurements per day is not its target. It does not describe residual-based anomaly scoring. The model class is written only if an ADR of WS05-T05 exists; otherwise the slot `\ph{forecaster-model}` is left for WS12-T06 and listed in the ledger.
10. Attribution: the six evidence groups of `EvidenceVector`; the hierarchical rule (integrity, then system, then coherent clinical, then UNDETERMINED); cascades propagate a root cause; the clinician-in-the-loop principle and the limit of robot autonomy to stop, retry and call; the compact diagnosability matrix is transcribed from `configs/diagnosability.yaml` (qualitative entries only, no measured number, each row of the paper table matches a row of the file) and includes the rows that are not distinguishable by construction (silent cuff bias, informed attacker), stated as results. Measured rates are reported in Section V, not here.
11. C3 is defined as an integrity or plausibility violation against the declared attack classes of the WS02 threat model, with the exclusions (compromised robot, RSM or specification); no sentence identifies C3 with low confidence.
12. Section III contains the fault and threat model at the length of the budget and names the attack classes exactly as the WS02 output does.
13. `python tools/check_paper.py terms claims tokens numerals paper/sections/03-formulation.tex paper/sections/04-method.tex` exits 0. `grep -nE '[0-9]+ ?mmHg' paper/sections/03-formulation.tex paper/sections/04-method.tex` prints nothing (numeric clinical values live only in registry-generated tables, `01-conventions.md` section 8), and any parameter shown is marked illustrative and unverified unless `WS00-T07.md` records its review (ADR-020).
14. Each subsection is within its budget by 0.10 page; the sum of Sections III and IV is within 2.20 pages plus 0.10.
15. Every citation key is in `paper/refs/references.bib` and verified (`python3 tools/check_bib.py`); a statement whose reference is not verified is left with `\ph{cite: <topic>}` in the ledger for WS12-T06.

## Passi

1. Read the WS01 and WS02 files listed in Contesto and the two contracts, then the contracts `#verdict` (verdict rules), `#forecaster` (scope), `#conformal-calibrator` (rules of calibration) and `#ros-2-interfaces` (placement) of `docs/plan/02-interfaces.md`. Copy nothing that is not in a frozen output; if a needed output is missing, stop and write a blocking note.
2. Run the checks above on the skeleton and note which fail (they fail on the empty sections).
3. Section III. Signals and sampling: the signal set actually used (`SignalId` of the contract), monitor period, piecewise-constant hold, events as one-sample impulses, integer millisecond time, device timestamp versus receive time with a bounded reorder buffer, and that timestamps are an attack surface (replay). Then pathway template versus patient care plan and the decomposition. Then the fault model and the threat model from WS02. Then the alert tuple with field semantics from `#alert`, and one sentence stating a cause-based taxonomy over violations of the three-part specification (analisi §4.8). This folds the old taxonomy prose into definitions (cut ledger item 4).
4. Section IV-A. Formal definitions of the past-time operators and of robustness (spatial for values, time robustness for timing) replace the operator tutorial of the workshop paper (cut ledger item 2). Then the five aspects of analisi §4.1: pre-dose reference as a derived signal, counters as derived signals with atomic predicates, the hold parameter, the measurement obligation induced by the response window (this is the bridge to the robot task, say so), point events evaluated over the window widened by one monitor period. Include Table I with its caption. One sentence on the FHIR PlanDefinition or BPMN mapping sketch only if `docs/formal/07-alert-tuple-mapping.md` (WS01-T07) delivers it.
5. Section IV-B. Per-template normalisation and lexicographic ranking, the alternatives (AGM robustness, weighted STL, ordinal bands) in one sentence, the table of rho, the two thresholds (likely violation, possible violation) with the clinical justification recorded by WS01-T06.
6. Section IV-C. Past-time rewriting and the causal, bounded-latency verdict; robustness intervals with physiological bounds replacing unknown future values; the verdict rule; conformal completion in PENDING; the forecaster paragraph (check 9); Proposition 1 and proof; the three caveats; the state diagram in one sentence and, if the budget allows, the ten-line algorithm with per-sample cost O(active template instances) (`#monitor` rules). The algorithm is the first thing cut if the page-fit ladder of WS12-T08 needs space.
7. Section IV-D. As in check 10, using the WS02 hierarchy and matrix; the natural-language rendering of the explanation is described as specification-level traceability, never as intrinsic explainability (analisi §4.8, row 1).
8. Section IV-E. From ADR-003 and `02-interfaces.md#ros-2-interfaces`: ward node with BLE gateway and continuous monitoring, robot running the embodied specifications and providing evidence, heartbeat, watchdog, fallback to the nurse when the robot is unavailable, single auditable verification path kept with the watchdog (analisi §4.8, row 6). State that the core library is independent of ROS 2 while lifecycle and liveliness states are used as evidence (this fixes the "middleware-agnostic" inconsistency of R3-W7). Keep it within 0.15 page next to Fig. 1 (cut ledger item 1). The hazards, standards and robot-risk paragraph of `docs/models/diagnosability-hazards.md` is placed in Section VI by WS12-T06; here a cross-reference is enough.
9. Compile, measure, trim to the budgets, run the checks of the Test section, fix findings. Update `PAGE_BUDGET.md`.
10. Set `status: done`; set newly unblocked dependents (WS12-T06) to `ready` if their other dependencies are done. Commit `WS12-T04: write sections III and IV`.

## Done when

```
python tools/check_paper.py terms claims tokens paper/sections/03-formulation.tex paper/sections/04-method.tex   # exit 0
grep -nE '[0-9]+ ?mmHg' paper/sections/03-formulation.tex paper/sections/04-method.tex                            # prints nothing
make -C paper pdf                                                                                                # exit 0
```

`paper/PAGE_BUDGET.md` shows Sections III and IV-A to IV-E measured within their budgets by 0.10 page, and lists every remaining `\ph` of these files (for example `\ph{forecaster-model}`) with the task that resolves it.
