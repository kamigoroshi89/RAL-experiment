---
id: WS01-T08
title: "Formalization freeze: consistency review and hand-worked patient-day (M1)"
workstream: WS01-formalization
owner: agent
status: ready
depends_on: ["WS01-T03", "WS01-T04", "WS01-T05", "WS01-T06", "WS01-T07"]
critical_path: true
non_negotiable: true
estimate_pd: 2
sources: ["analisi §4.1", "analisi §4.6", "analisi §6", "analisi §4.5 (diagnosability rows used by the worked day)"]
interfaces: ["02-interfaces.md#template", "02-interfaces.md#alert"]
review_items: ["R1-W1", "AE-2"]
---
## Obiettivo

Freeze the formalization (milestone M1). This task is non-negotiable (analisi §9). It (a) reviews `docs/formal/01` to `07` against every contract in `02-interfaces.md`, records a disposition for each apparent gap (CP1 to CP13 of the workstream README and any new one) and proposes ADRs where a contract must change, without editing `02-interfaces.md`; (b) checks cross-document consistency (registry names, units, symbols, fixture F0, glossary); (c) writes a hand-worked patient-day that replaces the workshop Table I and avoids every error listed in analisi §4.6, together with its machine-readable form for later end-to-end tests; (d) writes the index and freeze marker `docs/formal/README.md`. It closes R1 weakness 1 at document level (complete, consistent formulas) and AE-2 (absent formalization). It decides no clinical value.

## Contesto

Unblocks when WS01-T03, T04, T05, T06 and T07 are all `done`. Read first:

1. `docs/formal/` (all documents `01` to `07`, `docs/formal/golden/*.yaml`, `configs/registry/hypertension.yaml`).
2. `docs/plan/02-interfaces.md` (every contract; the review is against its exact text) and `docs/plan/01-conventions.md` section 6 (contract change procedure).
3. `docs/source/analisi.md` §4.6 (errors of Table I), §4.1, §6 (contributions), §4.5 (matrix rows used by the worked day).
4. `docs/plan/03-decisions.md` (ADR entry format, index line, numbering).
5. `docs/plan/workstreams/WS01-formalization/README.md` (CP1 to CP13, fixture F0, INDEX observations).

## File toccati

- `docs/formal/08-consistency-review.md` (create)
- `docs/formal/09-worked-patient-day.md` (create)
- `docs/formal/golden/patient-day.yaml` (create)
- `docs/formal/README.md` (create)
- `docs/plan/03-decisions.md` (modify: append proposed ADR entries and extend the index line; no existing entry is changed)
- `docs/plan/PROGRESS.md` (modify: one note that M1 formalization is frozen, with the clinician-review status)

## Test

Document task: verification checks.

1. **Headings.** `08-consistency-review.md`: `## 1 Method`, `## 2 Contract-by-contract table`, `## 3 Cross-document checks`, `## 4 Proposed ADRs`, `## 5 Freeze statement`. `09-worked-patient-day.md`: `## 1 Scenario and fixture`, `## 2 Timeline`, `## 3 Alerts and ranking`, `## 4 Coverage matrix`, `## 5 Table I error checklist`, `## 6 Paper excerpt (replacement of Table I)`.
2. **Contract table.** Section 2 of the review has one row per contract clause reviewed (at least: `#time-and-units` rules 1 to 4; `#signals` rule and `hold_last`; `#template` fields, `normalise`, `rank_alerts`; `#parameter-registry` rule; `#verdict` semantics 1 to 4 and transitions; `#conformal-calibrator` rules 1 to 4; `#alert` semantics; `#monitor` rules; `#trace-schema` day structure; `#evidencevector` and `#attribution` as read by the worked day), each with the clause quoted in short, what `docs/formal` states, and one disposition from: consistent; clarified in docs; ADR proposed; reported to another workstream. CP1 to CP13 each appear with a disposition. CP8 is reported to WS02 (no field for dispenser content or weight change; the default rule of `#attribution` yields C1 for a coherent violation while the analisi §4.5 matrix says a double take is distinguishable only if the dispenser measures content, so the worked day must abstain).
3. **Cross-document checks.** Section 3 records the result of: (a) every registry name used in `docs/formal` exists in `hypertension.yaml` as entry, derived or unset (command below); (b) each template's unit in `02-templates.md` matches the unit of its `scale_<id>` and the `expected.unit` of its golden cases; (c) every symbol in a formula of `02-templates.md` is defined in `01-signals-sampling.md`; (d) the `fixture_registry` of `templates.yaml` equals the F0 table of the workstream README and no golden file uses another value; (e) at least ten golden values, drawn from the four golden files of T02, T04, T05 and T06, are re-derived independently (Phi values with a calculator), and the outcome is written down; (f) glossary sweep: no "subsystem", "edge cloud", "embodied AI" and no unqualified "ensures", "intrinsic explainability", "orthogonal axes", "distribution-free coverage" outside the quoted claim table of T07; (g) no numeric clinical value outside registry, F0 or a label "illustrative, unverified"; (h) every "Open points" section of `01` to `07` is either resolved or copied into section 2.
4. **Defects are not patched here.** If a check fails because of a defect in `01` to `07`, section 3 names the owning task and this task reopens it (set its `status` back to `in_progress`, fix it there, rerun its own "Done when"); T08 does not edit those files.
5. **ADRs.** Section 4 lists each proposed ADR as a line `- ADR-0nn: <title> (contract points: CPx, ...)`, and `docs/plan/03-decisions.md` gains a matching `## ADR-0nn ...` entry for each, in the existing format (context, decision, alternatives, consequences, status), stating the old contract text, the new text, the affected tasks and the migration (`01-conventions.md` section 6), with the status line written like the entries ADR-011 to ADR-017 (proposed, with the confirm tag those entries carry). Numbers are the next free ones when the task runs. Recommended grouping: (i) verdict semantics (tie rule CP3, unavailable channel CP6, infinite endpoints CP12); (ii) lower conformal quantile and the definition of the variant "possible" (CP4); (iii) template set and units (CP1, CP2, CP9: obligation record); (iv) alert fields (CP5, CP13); (v) cross-day carry-over (CP7); (vi) registry typing (CP10). CP11 is clarified in documents (primary margin rule) and needs no ADR unless the review finds otherwise. `02-interfaces.md` is not edited and its version numbers are not bumped by this task.
6. **Worked day.** `09-worked-patient-day.md` and `docs/formal/golden/patient-day.yaml` use F0 and the scenario below; every number is computed by hand with a shown calculation and agrees with the golden cases of `templates.yaml`, `verdicts.yaml` and `conformal.yaml`; every row states template, verdict state, raw interval or value with unit, normalised value, rho with kind, attributed cause where an alert is emitted, priority, and cascade links. The timeline table has one row per event below (R11 only if T02 adopted a measurement-count obligation, CP2).
7. **Coverage matrix.** Section 4 of the worked day shows that the day contains: all four verdict states (PENDING, PREDICTED_VIOLATION then SATISFIED, VIOLATED, SATISFIED); all three kinds of rho and the absent rho; the causes C1, C2, C3 and UNDETERMINED; one cascade with `caused_by`; one tie (sigma = 0); one clipped value; one unmet-obligation guard; all seven templates; `dispense` distinct from `intake`; the final ranked list.
8. **Table I checklist.** Section 5 answers, row by row, the errors of analisi §4.6 with the row of the worked day that avoids each (list below).
9. **Freeze marker.** `docs/formal/README.md` has: an index of documents `01` to `09` with version `1.0`, the contract versions consumed (all `0.1.0`), the registry version, the golden files, the proposed ADR ids, a line `FROZEN: yes (M1 formalization freeze)`, and a line `clinician_review: pending` or `clinician_review: done (WS00-T07)` set from the existence and content of `docs/plan/workstreams/WS00-admin/outputs/WS00-T07.md`; when the review is pending the line says so and M1 is not called complete in `PROGRESS.md`.
10. **Contracts untouched.** `git diff --quiet -- docs/plan/02-interfaces.md` exits 0.
11. **Paper excerpt.** Section 6 of the worked day gives (a) the sentence that replaces Table I in the paper ("a patient-day generated by the system on a benchmark trace is shown in Fig. 2", analisi §4.6 and §7) and (b) the data of the hand-worked day that WS09-T03 uses to design and hand-check Fig. 2.

Scenario for the worked day (F0; `step_ms` 60000; `reorder_delay_ms` 0; plan ticks: measurement at 06:50, 09:00, 12:00, 20:30, 22:30; dispense at 07:00 and 21:00; the plan passes the feasibility checks of T02: a measurement tick in `[a - hold_lookback, a)` and in `[a + delta1, a + delta2]` for each dispense tick `a`). Expected values, to be reproduced and shown with calculations:

| Row | Event | Expected |
|---|---|---|
| R1 | 06:52 measurement bp 138, `inflation_ms` 45000, cuff healthy | SCHED@06:50 SATISFIED, sigma +28 min = 1680000 ms, 0.9333; RANGE SATISFIED, sigma min(28, 2) = +2 mmHg, 0.1; SYS SATISFIED, +15000 ms, 0.5; rho none |
| R2 | 06:58 `presence` observed and identity confirmed; 07:00 DISPENSE (`auth` false); 07:01 INTAKE observed | HOLD SATISFIED, +38 mmHg, 1.0 (clip of 1.9); COUNT SATISFIED, +1 dose, 1.0; INT SATISFIED, 300000 - 120000 = +180000 ms, 0.6; RESP@07:00 created with `bp_pre` 138, PENDING, raw interval [-inf, 78 mmHg], normalised (-1, 1), pending_until 10:00, rho none |
| R3 | 08:56 cuff node crash (heartbeat lost, liveliness false); 09:00 tick; no measurement; at 09:30 | SCHED@09:00 VIOLATED, decided 09:30, [-inf, -60000 ms], normalised upper end -0.0333, rho DETERMINISTIC 1.0, kappa C2 (system evidence: liveliness), priority 3, root cause of RESP@07:00 |
| R4 | 10:00 window of RESP@07:00 closes with no measurement | RESP@07:00 VIOLATED, [-inf, -inf], -1, guard `obligation_unmet`, rho DETERMINISTIC 1.0, `caused_by` SCHED@09:00, not a top-level alert |
| R5 | 11:20 cuff node restarted; 12:00 tick; 12:10 forecast arrival 12:40; 12:24 measurement bp 152 | 12:10: PREDICTED_VIOLATION of SCHED@12:00, sigma-hat -10 min = -0.3333, variant likely with fixture C-1 (`q` 0.09, alpha 0.2): -0.3333 + 0.09 < 0, rho PREDICTED 0.9 (alpha* 0.1), kappa UNDETERMINED (CP13). 12:24: SCHED@12:00 SATISFIED, +6 min = 360000 ms, 0.2 (false predictive alarm); RANGE VIOLATED, sigma -12 mmHg, -0.6, rho MEASURED 0.9772, kappa C1 (coherent channels, no system or integrity evidence), priority 2 |
| R6 | 20:30 tick; 20:32 sample bp 152 whose `seq` duplicates the 12:24 sample (replay) | SCHED@20:30 SATISFIED, +28 min, 0.9333; RANGE VIOLATED, -12 mmHg, -0.6, rho MEASURED 0.9772 (model-based, conditional on authenticity), kappa C3 (`seq_gap_or_replay` true; integrity evidence is tested first), priority 2 |
| R7 | 21:00 DISPENSE (scheduled, `auth` true, robot absent: `presence` and `intake` unavailable) | HOLD SATISFIED, latest measurement 20:32, +52 mmHg, 1.0; COUNT `c_d` = 2 = limit: sigma 0, SATISFIED by the tie rule, 0; INT SATISFIED by `auth`, +300000 ms, 1.0; RESP@21:00 created, `bp_pre` 152, PENDING, [-inf, 92], pending_until 24:00 |
| R8 | 21:02 unscheduled DISPENSE (`auth` true) | COUNT VIOLATED at once, sigma -1 dose, -1.0, rho DETERMINISTIC 1.0, kappa UNDETERMINED (no channel separates a double take from other causes: no content sensing, robot absent, CP8), priority 2; HOLD and INT SATISFIED; RESP@21:02 created, `bp_pre` 152, window [22:02, 00:02], pending_until 00:02 (after the day end, CP7); the two RESP instances cannot be violated at 21:02 because their windows open at 22:00 and 22:02 |
| R9 | 22:30 tick; 22:35 measurement bp 132 | SCHED@22:30 SATISFIED, +25 min, 0.8333; RANGE SATISFIED, sigma min(22, 8) = +8 mmHg, 0.4; RESP@21:00 and RESP@21:02 SATISFIED at 22:35, drop 20, margin +10 mmHg, 0.5 |
| R10 | end of day ranked list of the four top-level alerts | COUNT@21:02 (priority 2, -1.0), RANGE@12:24 (priority 2, -0.6, `t_ms` earlier), RANGE@20:32 (priority 2, -0.6), SCHED@09:00 (priority 3, -0.0333) |
| R11 (only if CP2 adopted) | 24:00 measurement count | 4 measurements (06:52, 12:24, 20:32, 22:35) of `meas_min_day` 5: sigma -1, VIOLATED, `caused_by` SCHED@09:00 |

Table I errors to answer in section 5 (analisi §4.6): row 07:00 (formula and unit undefined, counter margin, response window still open so sigma undefined, "confidence" on a satisfied event, dispenser opening taken as intake); row 08:55 (time not in a declared schedule, whether the range constraint applies during the onset window: an open clinical question for WS00-T07, the worked day applies RANGE at every measurement and says so, rho reproducible from an error model); row 15:00 (implicit unit, low confidence on a deterministic event, a deliberate lifecycle change versus a crash detected by liveliness or heartbeat, cascade not handled); row 21:00 (as 07:00); row 21:02 (counter margin -1 dose and not -8, cross-modal sub-formula cannot be violated at 21:02, low rho on a deterministic predicate, implausible C3 label for a double take or bounce, a single tau for two sub-formulas).

## Passi

1. **Review first.** Read documents `01` to `07` and the contracts. Build section 2 of `08` clause by clause; for each mismatch decide: fix in the owning document (reopen the owning task), clarify, propose an ADR, or report (CP8 to WS02). Keep the list of new points (not CP1 to CP13) with exact contract anchors.
2. Run the cross-document checks of "Done when" and the independent re-derivation of at least ten golden values; record results in section 3.
3. Draft the proposed ADRs (section 4 of `08`) and append them to `docs/plan/03-decisions.md`; extend the index line at the top of that file with the new ids. Check that `docs/plan/02-interfaces.md` is unchanged.
4. **Worked day.** Write `docs/formal/golden/patient-day.yaml` first (the observed day as samples and events in milliseconds, the expected `VerdictRecord` fields at each decision instant, the expected alerts with `tau`, `kappa`, `sigma_norm`, `rho`, `verdict`, `priority`, `caused_by`, `root_cause_of`, marked `kappa: provisional until WS02-T04`). Then write `09` from it, computing each number by hand with the calculation shown; recompute each once more.
5. Write the coverage matrix, the Table I checklist and the paper excerpt.
6. Write `docs/formal/README.md` (index, versions, freeze marker, clinician-review status) and the one-line note in `docs/plan/PROGRESS.md`.
7. Run "Done when"; set `status` to `done`; commit `WS01-T08: freeze formalization (M1)`.

## Done when

```bash
cd "/home/gab/Desktop/RAL experiment"
a=docs/formal/08-consistency-review.md; b=docs/formal/09-worked-patient-day.md; r=docs/formal/README.md
test -f "$a" && test -f "$b" && test -f "$r" && test -f docs/formal/golden/patient-day.yaml
for h in "## 1 Method" "## 2 Contract-by-contract table" "## 3 Cross-document checks" "## 4 Proposed ADRs" "## 5 Freeze statement"; do
  grep -qF "$h" "$a" || echo "missing heading in 08: $h"; done                      # prints nothing
for h in "## 1 Scenario and fixture" "## 2 Timeline" "## 3 Alerts and ranking" "## 4 Coverage matrix" \
         "## 5 Table I error checklist" "## 6 Paper excerpt (replacement of Table I)"; do
  grep -qF "$h" "$b" || echo "missing heading in 09: $h"; done                      # prints nothing
for c in CP1 CP2 CP3 CP4 CP5 CP6 CP7 CP8 CP9 CP10 CP11 CP12 CP13; do grep -q "$c" "$a" || echo "no disposition: $c"; done   # prints nothing
git diff --quiet -- docs/plan/02-interfaces.md                                       # exit 0
for id in $(grep -oE '^- ADR-0[0-9]+' "$a" | sed 's/^- //'); do
  grep -q "^## $id" docs/plan/03-decisions.md || echo "ADR not in 03-decisions: $id"; done   # prints nothing
grep -q '^FROZEN: yes' "$r" && grep -qE '^clinician_review: (pending|done)' "$r"
for n in $(grep -hoE '`(scale|priority|max_latency|bound)_[a-z0-9_]*`|`(bp_band_low|bp_band_high|bp_hold_threshold|hold_lookback|dose_max_24h|dose_min_day_end|int_window|delta1|delta2|delta_resp|sched_window|cuff_inflation_min|cuff_error_sd|meas_min_day)`' docs/formal/0*.md | tr -d '`' | sort -u); do
  grep -q "$n" configs/registry/hypertension.yaml || echo "not in registry: $n"; done   # prints nothing
grep -rniE 'subsystem|edge cloud|embodied (medical )?ai|clinical robotic architecture' docs/formal   # prints nothing
grep -rn 'ensures' docs/formal | grep -v ':| "'                                       # prints nothing
! grep -rnE 'T[O]DO|T[B]D|[?][?][?]|lore[m]' docs/formal configs/registry            # exit 0
```

## Notes

### Flag from the WS01-T03 review (orchestrator, 2026-09-30)

The cross-document check that greps every formula symbol in `configs/registry/hypertension.yaml` now prints `not in registry:` for `meas_min_day` (deliberately not registered: WS01-T02 adopted no measurement-count obligation), `priority_param` and `scale_param` (field names picked up by the regex, not registry entries). WS01 README item 3 ("every parameter name used in a docs/formal document is an entry, a derived bound or a declared unset name") is likewise not literally met for `meas_min_day`, `step_ms` and `reorder_delay_ms`. Adapt the check when this task runs. Also decide the open points of `docs/formal/03-parameter-registry.md` section 7 (OP-5 `window_parameters` as a required top-level key, OP-2 and OP-4 marked "ADR: yes") and ADR-027 (proposed).

### Hand-over from ADR-043 (agent, 2026-10-08)

WS00-T07 is no longer a dependency (decision of gab, ADR-043): run the freeze with `clinician_review: pending` in `docs/formal/README.md`. In `PROGRESS.md` M1 may be called reached with the review pending (this supersedes the last clause of check 9). Values of the registry are not part of the freeze: literature-anchored proposals come from WS01-T09 and are checked by gab.
