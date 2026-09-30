# Related work note: conformal and predictive monitoring (analisi 3.2)

Task WS03-T02. Bibliography fragment: `paper/refs/fragments/ws03-t02.bib` (rows 22 to 32 of the inventory; rows 1 to 21 are in `stl-rv-robotics.md`). Every entry has `verified = {false}` (ADR-018); nothing here is verified.

## Scope

Analisi section 3.2, "Conformal prediction applicata a STL e a sistemi con predittori appresi": eleven entries, transcribed as analisi recalls them (authors, year, venue as given; a dagger marks specific uncertainty on venue, year or author list). The section contains the closest published work, Lindemann, Qin, Deshmukh and Pappas (ICCPS 2023, `lindemann-conformal-stl`). It is the highest novelty risk of the paper (analisi rates it MOLTO ALTO) and it is the basis of baseline B5 (WS06-T06, non-negotiable). Nothing has been added from other sources: titles appear only where analisi quotes one.

## Reference table

| Key | Authors as recalled | Year | Venue | Dagger | ref_status | Role in the text |
|---|---|---|---|---|---|---|
| `lindemann-conformal-stl` | Lindemann, Qin, Deshmukh and Pappas | 2023 | ICCPS | no | recalled | closest work; baseline B5 |
| `bortolussi-neural-predictive-monitoring-conf` | Bortolussi, Cairoli, Paoletti and others | 2019 | RV | yes | recalled | predictive monitoring (conference version) |
| `bortolussi-neural-predictive-monitoring-ext` | Bortolussi, Cairoli, Paoletti and others | not given | STTT | yes | recalled | predictive monitoring (extended version) |
| `cairoli-conformal-quantitative-monitoring` | Cairoli, Paoletti and Bortolussi | 2023 | HSCC | yes | recalled | conformal quantitative predictive monitoring of STL requirements |
| `zhao-robust-conformal-stl` | Zhao, Hoxha, Fainekos, Deshmukh and Lindemann | 2024 | ICCPS | yes | recalled | distribution shift |
| `lindemann-safe-planning` | Lindemann and others | 2023 | IEEE RA-L | no | recalled | conformal prediction in robotics; to be cited because it appeared in RA-L |
| `stankeviciute-conformal-time-series` | Stankeviciute, Alaa and van der Schaar | 2021 | NeurIPS | no | recalled | conformal prediction for time series |
| `xu-xie-enbpi` | Xu and Xie | 2021 | ICML | no | recalled | conformal prediction for time series (EnbPI) |
| `gibbs-candes-adaptive-conformal` | Gibbs and Candes | 2021 | NeurIPS | no | recalled | non-exchangeability (adaptive conformal inference) |
| `barber-beyond-exchangeability` | Barber, Candes, Ramdas and Tibshirani | 2023 | Annals of Statistics | no | recalled | non-exchangeability |
| `angelopoulos-conformal-pid` | Angelopoulos, Candes and Tibshirani | 2023 | NeurIPS | no | recalled | non-exchangeability (conformal PID control) |

## What the reviewer expects

- Closest work: Lindemann, Qin, Deshmukh and Pappas, "Conformal prediction for STL runtime verification" (ICCPS 2023).
- Predictive monitoring: Bortolussi, Cairoli, Paoletti and others, "Neural predictive monitoring" (RV 2019, and an extended version in STTT; dagger); Cairoli, Paoletti and Bortolussi, conformal quantitative predictive monitoring of STL requirements (dagger, HSCC 2023).
- Distribution shift: Zhao, Hoxha, Fainekos, Deshmukh and Lindemann, robust conformal prediction for STL runtime verification (dagger, ICCPS 2024).
- Conformal prediction in robotics: Lindemann and others, "Safe planning in dynamic environments using conformal prediction" (IEEE RA-L 2023). Because it appeared in RA-L, it must be cited.
- Conformal prediction on time series: Stankeviciute, Alaa and van der Schaar (NeurIPS 2021); Xu and Xie, EnbPI (ICML 2021).
- Non-exchangeability: Gibbs and Candes, adaptive conformal inference (NeurIPS 2021); Barber, Candes, Ramdas and Tibshirani, "Conformal prediction beyond exchangeability" (Annals of Statistics 2023); Angelopoulos, Candes and Tibshirani, conformal PID control (NeurIPS 2023).

Analisi warns that the sentence of the workshop abstract "combines temporal prediction, uncertainty-aware reasoning, and constraint-based verification" describes almost exactly Lindemann et al. 2023. If that work is neither cited nor used as a baseline, reviewers R1 or R2 will raise it, and a reject for lack of novelty becomes likely.

## Difference

(a) The four candidate differences of analisi section 3.2:

1. sparse, event-driven sampling instead of dense trajectories;
2. explicit separation between the verdict on measured data and the predictive verdict;
3. calibration per patient episode, with an adaptive variant for the single patient;
4. integration with cause attribution.

(b) Analisi section 10, objection 2, prescribes a precise difference sentence with four elements: sparse event-driven sampling, formal separation of the measured and the predicted verdict, normalized severity over mixed units, attribution with abstention. These four are the ones used in the sentence in (d). The per-episode calibration with an adaptive variant (item 3 of (a)) is kept for the sentences that precede it in paragraph 2, where Gibbs and Candes and Barber and others are cited; normalized severity comes from section 10 and is not in the section 3.2 list.

(c) Traceability of each element to the plan artefact that realizes it, and to the place where it is tested against the closest work.

| Element | Realized by | Tested against the closest work |
|---|---|---|
| Sparse event-driven sampling | WS01-T01 (signals and sampling semantics) | B5, WS06-T06: analisi 5.4 lists sparse sampling among the points where it fails |
| Formal separation of measured and predicted verdict | WS01-T05 and WS01-T06 (ADR-008: conformal prediction only in PENDING) | Not listed among the B5 failure points of analisi 5.4; the components are tested by ablations A1 and A2 (ADR-008) |
| Normalized severity over mixed units | WS01-T04 (ADR-009) | B5, WS06-T06: analisi 5.4 lists mixed units among the points where it fails |
| Attribution with abstention | WS02-T04 (ADR-010) | B5, WS06-T06: analisi 5.4 lists the absence of attribution among the points where it fails |

(d) Binding sentence for the second Related Work paragraph:

> Unlike conformal STL runtime verification on dense predicted trajectories \cite{lindemann-conformal-stl}, our monitor works on sparse, event-driven samples; it separates formally the verdict on measured data from the predictive verdict, confining conformal prediction to the PENDING state; it ranks alerts by a clinically normalized severity over mixed units; and it attributes each alert to a cause, or abstains (UNDETERMINED).

WS03-T05 may shorten the sentence but must keep the four elements and the key `lindemann-conformal-stl`. Hedge that travels with the sentence: the characterization "dense predicted trajectories" is taken from analisi section 3.2 ("anziche traiettorie dense"), which recalls the paper from memory; it has not been checked against the paper text. The human checks it in WS03-T06 (mandatory), and the sentence is corrected there if the paper differs. This note describes Lindemann et al. only as far as analisi does.

## Risk and handling in the text

Analisi rates the risk MOLTO ALTO: a reject for lack of novelty becomes likely if Lindemann et al. is neither cited nor used as a baseline. Handling, following analisi section 10, objection 2:

- cite Lindemann et al. 2023 explicitly, with the difference sentence above;
- cite the Bortolussi and Cairoli line, describing those works only by the topic recorded in the reference table (predictive monitoring; conformal quantitative predictive monitoring of STL requirements);
- use the method as baseline B5 (WS06-T06) and report at least one result in which it fails (analisi 5.4: sparse sampling, mixed units, no attribution);
- present Proposition 1 as small but new in the three-valued setting, without inflating it.

Wording constraints: make no priority or novelty claim ("first", "novel"). Do not use the unqualified coverage phrase that analisi 4.8 replaces: coverage is marginal, requires exchangeability, and the calibration unit must be stated (here the patient episode). Where exchangeability across episodes is doubtful, the text points to the adaptive and non-exchangeable variants (Gibbs and Candes; Barber and others) and does not claim more. Validation is technical and pre-clinical.

## Unresolved and for human verification

- Four entries carry a dagger in analisi and need specific verification of venue, year or author list: `bortolussi-neural-predictive-monitoring-conf`, `bortolussi-neural-predictive-monitoring-ext`, `cairoli-conformal-quantitative-monitoring`, `zhao-robust-conformal-stl` (rows 23 to 26). The dagger covers both the conference and the extended version of the Bortolussi work; the extended entry has no year in analisi.
- Which Bortolussi version to cite (rows 23 and 24) is decided in WS03-T05 and recorded in `citation-selection.md`.
- Mandatory check in WS03-T06: the description of Lindemann et al. in the difference sentence ("dense predicted trajectories") matches the paper text.
- Every entry lacks first names, full titles (except rows 22, 23, 27 and 31), pages and DOIs; the human adds them in WS03-T06.
