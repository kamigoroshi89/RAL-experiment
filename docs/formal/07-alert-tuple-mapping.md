# 07 Alert tuple, traceability wording and FHIR/BPMN mapping sketch

Document WS01-T07. Feeds the definition of the alert tuple, the decomposition wording and the claim wording that the human uses for paper Sections II and III (the paper text itself is not written here, ADR-037: section 8), the attribution specification of WS02-T04, the attribution package of WS05-T07 (`Alert`, `Explanation`, the rendering of `Explanation.text`), the design of the vignette study of WS11-T01 and the claim audit of WS12-T07. Draft for the M1 freeze (WS01-T08); it changes no contract of `docs/plan/02-interfaces.md` (gaps and clarifications are recorded in section 9). It builds on `docs/formal/01-signals-sampling.md` ("T01": decomposition and wording rules, section 6), `docs/formal/02-templates.md` ("T02": templates, margin and guard rule, obligations, load checks of section 5.4), `docs/formal/03-parameter-registry.md` ("T03": versioning and per-patient values, section 5), `docs/formal/04-normalisation-ranking.md` ("T04": sigma-tilde, ranking, frozen value), `docs/formal/05-three-valued-semantics.md` ("T05": verdict states, certified severity, state machine) and `docs/formal/06-rho-proposition1.md` ("T06": rho per verdict type, the quantities of a predicted alert). For the vocabulary of attribution and evidence it reads `docs/models/evidence-channels.md` ("EC"), `docs/models/fault-model.md` ("FM") and `docs/models/threat-model.md` ("TM"). The rule document of the attribution layer, `docs/models/attribution-rule.md` (WS02-T04), does not exist when this document is written (WS02-T04 depends on this task): what is said here about kappa rests on ADR-010, the contracts `#attribution` and `#evidencevector`, EC, FM and TM, and every place that would need the rule document says so. Validation in this project is technical and pre-clinical; nothing in this document is a clinical claim, and the comprehensibility of the text that an alert shows to nursing staff is not tested here (section 3.4).

Every clinical number is either fixture arithmetic (FIXTURE-ONLY, fixture registry F0 of `docs/plan/workstreams/WS01-formalization/README.md`) or a value of analisi §4.1, §4.2 or §4.6 labelled "illustrative, unverified" (ADR-020). Every number in the worked tuples of section 1.9, in the cascade example of section 1.8 and in the three example sentences of section 3.5 is recomputed from golden cases of T02, T05 and T06 (the case ids are named where the numbers are used) and from nothing else. Scales and priorities are registry values that no clinician has reviewed (WS00-T07); no alert in this document is a statement about a patient. Nothing here reads `LatentDay` or `GroundTruthEvent`: an alert is built from verdict records and evidence vectors of the observed trace.

What this document answers (review items): R1 weakness 8 (the clinical and the system specification conflated: sections 2 and 3), R1 weakness 9 (integrity and versioning of the specification distributed to the robot: section 4), the contract points CP5 (range of `sigma_norm`) and CP13 (kappa of a predicted alert) of the WS01 README, the two open reconciliations that the reviews of T04 and T06 handed to this task (the value of `sigma_norm` for a VIOLATED alert and for a predicted alert: section 1.5), and analisi §3.4 (the partial mapping from a standard representation: sections 5 to 7).

**Notation and wording.** `tau` is the template of an alert (a `TemplateId`), never a time; the time of an alert is `t_ms`. "sigma" without tilde is raw robustness in the native unit of the template (workshop Table I reports it with no unit); `sigma_tilde` (code name `sigma_norm`) is the normalised value in `[-1, 1]` of T04. "Robustness" is used only for STL semantics; the reading of `sigma_tilde` is "severity". The four verdict states are PENDING, PREDICTED_VIOLATION, VIOLATED, SATISFIED. An **alert** is the output tuple; a **violation** is a violated sub-formula and it names its conjunct (T01 section 6.2); the **attributed cause** is kappa. `N_s` is the normalisation of T04 section 2.1 (`clip(sigma / s, -1, 1)`), `hi` the upper end of the raw robustness interval of a record. No reference is cited from memory: markers `[ref-needed: WS03]` and `[verify: standard text]` are used where a source would be needed, and no entry of `paper/refs/references.bib` is cited (the entries on the topics of sections 5 and 6 all have `verified = {false}`, ADR-018).

**Parameters used.** All are registry names or fixture rows; none is invented here.

| Name | Unit | Origin |
|---|---|---|
| `bp_band_low`, `bp_band_high` | mmHg | analisi §4.1 (illustrative, unverified): 110 and 140 in F0 |
| `scale_range` | mmHg | analisi §4.2 example (20 in F0); registry 0.1.0 entry, `reviewed_by` null |
| `priority_range`, `priority_sched` | rank, 1 = highest | analisi §4.2 order example (2 and 3 in F0); registry 0.1.0 entries, unreviewed |
| `sched_window` | ms | registry: `unset`; F0 value 1800000 ms (30 min) is FIXTURE-ONLY |
| `scale_sched` | ms | analisi §4.2 example, 30 min (1800000 in F0); registry 0.1.0 entry |
| `dose_max_24h` | dose | analisi §4.1 (illustrative, unverified): 2 in F0 |
| `scale_count` | dose | analisi §4.2 example (1 in F0); registry 0.1.0 entry |
| `priority_count` | rank | registry: `unset`; F0 value 2 is FIXTURE-ONLY |
| `delta1`, `delta2` | ms | analisi §4.6 window [08:00, 10:00] of a 07:00 dispense (3600000 and 10800000 in F0), used only in section 5.2 |
| `cuff_error_sd` | mmHg | registry: `unset` (T03, awaiting WS00-T07); F0 value 6 mmHg is FIXTURE-ONLY (T06) |
| `registry_version` | string | field of `CarePlan` and of the registry file (T03 section 5); "0.1.0" in the seed |
| `step_ms` (`T_s`), `reorder_delay_ms` (`D`) | ms | monitor configuration, not registry entries (F0: 60000 and 0) |
| `evidence_grace_ms` | ms | registry-parameter request of EC; no value is used here |

## 1 Alert tuple

### 1.1 The contract text relied upon, quoted

From `docs/plan/02-interfaces.md#alert` (version 0.1.0, owner WS01). The block is verbatim except for the docstring of `Explanation` and one clause of the first semantic bullet below, which quote claims that section 3.1 rewords (rows 1 and 3) and are abridged so that the claim words appear in this document only in the quoted-claim column of that table:

```python
class AttributedCause(str, Enum):
    C1_CLINICAL = "C1"       # clinical or adherence deviation
    C2_SYSTEM = "C2"         # system or embodiment failure
    C3_INTEGRITY = "C3"      # integrity or plausibility violation
    UNDETERMINED = "UNDETERMINED"

@dataclass(frozen=True, slots=True)
class Explanation:
    """xi: specification-level traceability (abridged here, see below)."""
    template: TemplateId
    instance_key: str
    subformula_path: str              # path to the violated sub-formula
    param_values: Mapping[str, float] # clinical parameters used
    evidence_used: Sequence[str]      # EvidenceVector fields that decided kappa
    text: str                         # natural-language rendering for nursing staff

@dataclass(frozen=True, slots=True)
class Detection:
    """Minimal output shared by every detector, including baselines B1-B4."""
    t_ms: TimeMs
    label: AttributedCause | None     # None for detectors that do not attribute
    score: float                      # detector-specific; higher = more anomalous, only for ROC-style curves

@dataclass(frozen=True, slots=True)
class Alert(Detection):
    tau: TemplateId                   # violated template (constraint)
    kappa: AttributedCause            # attributed cause; UNDETERMINED is a valid output
    sigma_norm: float                 # normalised robustness in [-1, 0) for a violation
    rho: Rho                          # confidence with declared kind and guarantee
    xi: Explanation
    verdict: VerdictState             # VIOLATED or PREDICTED_VIOLATION
    priority: int                     # clinician-assigned template priority
    root_cause_of: Sequence[str]      # instance keys of downstream violations explained by this alert (cascades)
    caused_by: str | None             # instance key of the upstream alert when this one is a cascade effect
```

Semantics of the contract: "σ̃ answers 'how badly is the prescribed care violated' in clinical scale units; ρ answers 'how confidently can the violation be claimed', with its `kind` telling which guarantee applies. They are complementary (analisi §4.8; the rest of the sentence is abridged here, see row 3 of section 3.1)." "κ is produced by the attribution layer, never by the sub-formula alone (analisi §4.5). A value of `UNDETERMINED` is not an error." "A cascade effect (for example a counter violation caused by a C2 missed measurement) carries `caused_by` and is not shown as a separate top-level alert (analisi §4.9 item 3)." "Ordering of alerts uses `rank_alerts` from `#template`." From `#monitor`: "The monitor separates verdicts from attribution: it emits `VerdictRecord`s; the `Attribution` step turns violated records into alerts." From `#attribution`: `attribute_all(self, violated: Sequence[VerdictRecord], evidence: Mapping[str, EvidenceVector]) -> Sequence[Alert]`, with the comment "propagates root causes over cascades (analisi §4.9 item 3)".

The field order of `Alert` is `t_ms`, `label`, `score` (inherited from `Detection`), then `tau`, `kappa`, `sigma_norm`, `rho`, `xi`, `verdict`, `priority`, `root_cause_of`, `caused_by`. The tuple of the analysis, ⟨τ, κ, σ̃, ρ, ξ⟩, is the five fields `tau`, `kappa`, `sigma_norm`, `rho`, `xi`; the other seven fields carry the time, the baseline-compatible view of the alert, the verdict state, the priority and the cascade links.

### 1.2 The five elements of the tuple

| Symbol | Contract field | Type | Unit or range | Semantics (one sentence) | Producer | Defining document | `None` |
|---|---|---|---|---|---|---|---|
| tau | `tau` | `TemplateId` | one of range, sched, hold, count, resp, sys, int | The template whose instance is violated (or predicted to be violated); an alert has exactly one `tau`, never a compound. | monitor: `VerdictRecord.template`, copied by the attribution layer | T02 (section 3.1: id, conjunct `kind`, unit) | never; the type is not optional |
| kappa | `kappa` | `AttributedCause` | C1, C2, C3, UNDETERMINED | The cause that the attribution rules assign to the violation from the evidence vector, or UNDETERMINED when the evidence does not support one cause; for a PREDICTED_VIOLATION alert it is UNDETERMINED by definition (section 1.7). | attribution layer, never the monitor and never the violated sub-formula alone | WS02: `attribution-rule.md` of WS02-T04 (planned), EC, FM, TM; ADR-010 | never; UNDETERMINED is a value and not `None` (`Detection.label` is `None` only for detectors that do not attribute) |
| sigma-tilde | `sigma_norm` | `float` | dimensionless, `[-1, 0)` in exact arithmetic (`[-1, 0]` in floating point, T04 section 2.3 (a)) | The normalised bound that decided the emission of the alert: `N_s(hi)` of the first VIOLATED record, or `clip(sigma_hat + q, -1, 1)` for a predicted alert (section 1.5). | monitor: the record (`sigma_norm_interval`, or the predicted bound); copied by the attribution layer | T04 (normalisation, ranking), T05 section 3.7 (certified severity), T06 section 2.4 (predicted quantity), this document section 1.5 | never; never NaN (T04 section 4.9) |
| rho | `rho` | `Rho` | `value` in `[0, 1]`, `kind` MEASURED, DETERMINISTIC (VIOLATED alert) or PREDICTED (predicted alert), `guarantee`, `alpha`, `assumptions` | How confidently the violation can be claimed, with the kind and the exact guarantee that belong to the evidence that decided or predicted it. | monitor: `VerdictRecord.rho`, copied unchanged | T06 (sections 2.2 and 2.3) | never for an alert (a record in SATISFIED or PENDING has `rho` `None` and raises no alert); `Rho.alpha` is `None` for MEASURED and DETERMINISTIC |
| xi | `xi` | `Explanation` | six fields (table of section 1.3) | The specification-level traceability record: which instance, which sub-formula, which clinical parameters, which evidence decided kappa, and a deterministic natural-language rendering for nursing staff. | attribution layer: instance and path from the record, parameters from the plan and the registry, evidence from the rule, text from the renderer | this document (sections 1.4 and 3), EC for the evidence paths, WS05-T07 for the renderer | never; `evidence_used` can be empty (section 1.7) |

Notes. (1) Sigma-tilde and rho are complementary and correlated, not independent: for a measured violation, rho tends to one half as the measured value approaches the limit while sigma-tilde tends to zero (T06 section 1.3). With F0, the band violations G-RANGE-3 (bp 104, sigma -6 mmHg, sigma-tilde -0.3) and G-RANGE-2 (bp 152, sigma -12 mmHg, sigma-tilde -0.6) carry rho 0.8413 and 0.9772 (C-6): in these two cases the more severe measurement is also the more confidently claimed one, as the formula `Phi((x - L) / s)` of T06 section 3.2 gives; sigma-tilde depends on the registry scale of the template and rho on the device error model, two different parameters. (2) Rho carries its `kind` and its exact `guarantee` and `assumptions` strings (T06 section 2.2): a consumer never shows the number without them. (3) Rho is never an input of kappa (TM Non-claims 1; WS02-T04 invariant I1 as stated in its task text), and kappa is not an input of rho: a low rho is not integrity evidence (R2 weakness 7).

### 1.3 The other seven fields and the six fields of `xi`

| Field | Type | How it is filled | Anchor |
|---|---|---|---|
| `t_ms` | `TimeMs` | VIOLATED alert: `decided_at_ms` of the first VIOLATED record (the grid time of the deciding step; the monitor emits it at `decided_at_ms + D`). Predicted alert: `t_eval_ms` of the record at which the PENDING instance entered PREDICTED_VIOLATION. It is an event time, not the monitor time at which the alert leaves the attribution layer (that time adds `D`, the evidence grace and the compute time and goes to the log). | T05 sections 3.1 and 7.1; EC (cut-off); WS05 README D7. T04 section 4.1 writes "the time at which the alert is emitted" loosely: the order of T04 is unchanged by this reading (OP-T07-9) |
| `label` | attributed cause or `None` | equal to `kappa`; an alert always attributes, so `label` is never `None` for an alert. | contract comment of `Detection.label`; WS05 README D7 |
| `score` | `float` | minus `sigma_norm`, in `[0, 1]` (a floating-point `-0.0` gives `0.0`); higher means more severe; used only for ROC-style curves, never for ranking (ranking reads `priority`, `sigma_norm`, `t_ms` and `xi.instance_key`, T04 section 4.1). | contract comment of `Detection.score`; WS05 README D7; WS05-T07 test 3 |
| `verdict` | `VerdictState` | VIOLATED or PREDICTED_VIOLATION, the state of the record that produced the alert (a PENDING or SATISFIED record produces no alert). | contract comment; T05 section 4.2 |
| `priority` | `int` | the registry entry named by `Template.priority_param` for `tau`; 1 is the highest and the order is ascending (T04 section 4.3, which closes the direction part of CP5). It does not depend on kappa (T04 OP-10). With registry 0.1.0, `priority_count`, `priority_resp`, `priority_sys` and `priority_int` are unset, so an alert of those templates exists only with the fixture registry (AH-11). | T04 sections 3.1 and 4.3 |
| `root_cause_of` | sequence of `str` | the `xi.instance_key` values of the alerts of the same care plan that this alert explains; empty for an alert that is not a root (section 1.8). | contract comment; EC D-1 (keys per care plan) |
| `caused_by` | `str` or `None` | the `xi.instance_key` of the upstream alert when this one is a cascade effect, else `None` (section 1.8). | contract comment |
| `xi.template` | `TemplateId` | equal to `tau` (a redundancy kept by the contract; a mismatch is a defect). | contract |
| `xi.instance_key` | `str` | `VerdictRecord.instance_key`, unique within a care plan; it is the identity of the alert (section 1.4). | contract (`TemplateInstance.instance_key`); T05 section 3.8 |
| `xi.subformula_path` | `str` | the path of the decisive sub-formula, then the other violated sub-formulas of the instance (section 1.4, item 2). | WS05-T04 step 8 (carrier, proposed); T02 section 2.1 |
| `xi.param_values` | mapping `str` to `float` | the values of the registry names in `Template.params` that the instance used (the plan value in `TemplateInstance.param_values`, else the registry value); units are not in the mapping and are added from `RegistryEntry.unit` by the renderer. | T02 section 3.1; T03 section 5.3; AH-14 |
| `xi.evidence_used` | sequence of `str` | the canonical `group.field` paths (EC, section Conventions) of the evidence fields that decided kappa, in precedence order; empty when no field decided (a predicted alert, or an abstention without a decisive field). | EC; contract comment |
| `xi.text` | `str` | deterministic English rendering of the alert (section 3.4). | WS05-T07 tests 21 to 27 (planned) |

### 1.4 Granularity, identity and lifecycle of an alert

**1. One alert per violated template instance.** The unit is the instance (`VerdictRecord.instance_key`): a verdict episode is an instance (T05 section 3.8), the instances are created one per anchor event and template (T05 section 6.2: a DISPENSE event creates the RESP, HOLD, COUNT-limit and INT instances), and `instance_key` is unique within a care plan (contract). Consequences.

- *Two templates violated by one event give two alerts, never a compound tau.* Each has its own `tau`, instance key, sigma-tilde, rho, priority and path. This is the answer to error (e) of the workshop Table I, row 21:02 (analisi §4.6, error (e): τ is given as a single value although the text speaks of two violated sub-formulae; translated from the Italian source). Example: an unscheduled dispense creates a COUNT-limit instance and an INT instance; if both are VIOLATED there are two alerts, `count@21:02` and `int@21:02`. In the workshop example the RESP instance of the same dispense is not decided at 21:02 (T05 section 7.6: its window has not closed, and it could be violated earlier only through the physiological bounds), so the row of the workshop table would carry one alert, for the dosage instance.
- *HOLD and COUNT instances that share a dispense* are separate alerts, ordered by `rank_alerts` (priority first, T04 section 4.2), not merged and not given a shared sigma-tilde.
- *A counter that stays above its limit* gives one alert for the excess dose; a later dispense while the count is still above the limit is a new instance and a new alert (T05 section 3.8); there is no alert per grid step, and the day-end COUNT instance is its own alert. The aggregation that T05 section 3.8 handed to this task is therefore: no aggregation by the alert layer.
- *Refinement records* of a VIOLATED SCHED instance (T05 section 6.5) are not new alerts (section 1.5).
- *Cascades* are the only relation between alerts, and they are links (`caused_by`, `root_cause_of`), not merges (section 1.8).

**2. The sub-formula path.** `Explanation.subformula_path` is one `str`. Convention adopted here, with no signature change: the string starts with the path of the *decisive* sub-formula, the one that attains the minimum of the instance body (the first in the order of the template string when several tie, T02 section 2.1 item 3); other sub-formulas of the same instance that are negative at the deciding step follow, separated by `;`, in increasing order of value. By T02 section 2.1 each template has one margin dimension and at most one guard that can fail besides the trigger, so the list after the first element is short; a failed guard is itself a sub-formula, and when it is the decisive one the marker name of T02 section 2.1 (`no_measurement_after_tick`, `no_recent_measurement`, `obligation_unmet`, `cuff_unhealthy`, `no_witness`) must be recoverable from the path (T04 OP-5 asked this task to carry the marker `guard_failed` in the alert record). The exact syntax of the path is the one WS05-T04 step 8 gives to `VerdictRecord.subformula_path` (child-index path with the labels of T02); the carrier field does not exist in contract 0.1.0 (OP-T07-6).

**3. Identity and lifecycle.** The identity of an alert within a care plan is `xi.instance_key`. `Alert` is a frozen value, so "the same alert updated" can only mean "a new value that supersedes the old one". The rules, per event on the instance (transition ids of T05 section 4.2):

| Event on the instance | Effect on the alert set | Reason |
|---|---|---|
| T2, PENDING to PREDICTED_VIOLATION | emit a predicted alert (verdict PREDICTED_VIOLATION, kappa UNDETERMINED) | sticky: at most one predictive alarm per instance (T05 section 4.3) |
| T5, PREDICTED_VIOLATION stays | none | the interval refines, the alert does not |
| T6, PREDICTED_VIOLATION to VIOLATED | emit a violated alert with the same `xi.instance_key`; it supersedes the predicted alert in the current set, and the predicted alert stays in the history | a new *value*, not a refinement: `t_ms`, `verdict`, `kappa`, `sigma_norm` and `rho` (kind PREDICTED to MEASURED or DETERMINISTIC, T05 T6) all change, and the definitive statement is a different statement from the warning (K1 of T04 section 4.5 treats the verdict as a class); the history is needed for the false-alarm and lead-time metrics (`detection_delay_ms`: "negative = early warning") |
| T3, PENDING to VIOLATED | emit a violated alert | |
| T7, PREDICTED_VIOLATION to SATISFIED | no new alert; the predicted alert is closed as a false predictive alarm | the verdict layer counts it (contract, allowed transitions); the closure is carried by the `VerdictRecord`, because `Alert` has no closed state (OP-T07-5) |
| T1, PENDING stays, also after `pending_until_ms` with an `undecidable` marker (CP6) | none | the contract admits only VIOLATED and PREDICTED_VIOLATION as `Alert.verdict`; the follow-up of an undecidable instance is not an alert in contract 0.1.0 (OP-T07-14) |
| T8, VIOLATED refinement (SCHED graded value until `H_i`) | none | the alert is frozen at emission (section 1.5) |
| a cascade link appears or changes | re-issue the alert with only `root_cause_of` or `caused_by` changed | the contract defines `root_cause_of` as "downstream violations explained by this alert", which can be known only after the downstream violation exists; the other fields are those of the first issue (section 1.8) |

The *current set* holds, per instance key, the last issued value; the *history* holds every issued value. `rank_alerts` is applied to the current set (or to its top-level part, section 1.8); a predicted alert sorts after a violated one of the same priority only if the order K1 of T04 section 4.5 is adopted (ADR-028 proposed, OP-3 of T04).

**4. Emission time.** An alert is a function of the first VIOLATED record `rec(i, k*)` (T05 Lemma 4 (c)) and of the evidence at the cut-off `C(i) = decided_at_ms + D + evidence_grace_ms` that EC derives from the first VIOLATED record of the instance; with a grace of zero, attribution adds no latency to the verdict (EC, section Timing and evidence window, rules 3 and 4). A violated alert never appears before its record, and a record is never produced from a forecast (T05 (P2)).

**5. Sigma and sigma-tilde.** The "sigma" of the workshop paper (without tilde) is raw robustness in the native unit of the template, and the workshop Table I gives it no unit (the values -12, -21 and -8 are in mmHg, "seconds?" and an unknown unit: analisi §2 R1 weakness 2, translated from the Italian source). The alert carries sigma-tilde only; raw robustness stays inside `spec` and in `VerdictRecord.sigma_interval`, and the ablation A3 takes the raw value from the record by a join on `xi.instance_key` (T04 section 7).

### 1.5 Sigma-tilde of an alert: the two reconciliations

**What is fixed.** `sigma_norm` is *the normalised bound that decided the emission of the alert*: the value that the rule that emitted the alert compared with zero.

| Verdict | Value | Source | Range | Frozen? |
|---|---|---|---|---|
| VIOLATED | `N_s(hi)`, the second component of `sigma_norm_interval` of the first VIOLATED record `rec(i, k*)` | T05 section 3.7 (certified severity), T04 section 2.1 (`N_s`) | `[-1, 0)`: `hi < 0` is the emission rule and `N_s` preserves the sign (T04 Lemma 2) | yes: the refinement records of T05 section 6.5 do not change the alert |
| PREDICTED_VIOLATION | `clip(sigma_hat + q, -1, 1)`, with `sigma_hat` clipped into `[N_s(lo), N_s(hi)]` of the record (T05 (P4)) and `q` the quantile that decided the emission (`q_{1-alpha}` for "likely", `q^lo_alpha` for "possible") | T06 section 2.4, carried by `VerdictRecord.predicted_sigma_norm` (WS05-T04 step 8, proposed) | `[-1, 0)`: `sigma_hat + q < 0` is the emission rule and `clip` keeps the sign | yes: a predicted alert is replaced by the violated alert, never edited |

**Resolution of the flag from the WS01-T04 review (VIOLATED alert; T04 section 4.7, OP-9 and OP-14).** The task text (line 40) attributes to T04 the rule "`sigma_norm` is the upper end of the normalised interval at emission (certified severity, T04)". T04 does not state it: section 4.7 offers "`-1` with a guard marker, or a graded value", and OP-14 records the discrepancy. T05 section 3.7 fixes the rule at the verdict layer: "The certified severity of a VIOLATED record is the normalised upper end `N_s(hi)` at the step where it is emitted", with Lemma 8 (the frozen value is never more severe than the resolved one, under (H-fin), (H-dom), (H-grid) and where the accepted trace is defined) and hands the alert field to this task. **Adopted: `sigma_norm = N_s(hi)` of the first VIOLATED record, frozen at emission.** Reasons. (1) It is the one point of the interval that Lemma 3 of T05 licenses as a statement about every completion: the instance is *at least* that far below its limit. The alternative `-1` with a guard marker would assert a full scale of severity that no lemma certifies (for a SCHED violation at the deadline, `hi` is one monitor step: F0 V-SCHED-3, `[-inf, -60000]` ms, `N_s(hi) = -0.0333`, `N_s(lo) = -1`). (2) It keeps the contract range `[-1, 0)` without a clarification. (3) T04 section 4.7 recommends that the alert be frozen at emission ("The `sigma_norm` of an alert is the value of the record at emission and does not change afterwards; `rank_alerts` is a pure function of the alerts it receives"), the remark of T04 that a frozen value "can be more severe than the final value" holds only under the `-inf` choice of T02 section 2.3 and not under this rule (T05 section 3.7), and EC already takes the evidence of the alert from the first VIOLATED record, "so the refinement records of a SCHED instance (T05 section 6.5) do not change the vector". (4) It is the rule that WS01-T08 R3, WS05 README D7 and WS05-T07 test 3 already use. **Consequences, to be reported.** (a) Every SCHED alert has, at emission, `hi = -T_s` and therefore the same `sigma_norm` (`-T_s / s`, F0 `-0.0333`): the graded lateness exists only in the refinement records (V-SCHED-5a: `-0.3667` at 09:40; V-SCHED-5b, the measurement at 09:51: `-0.7`), and among the SCHED alerts of one priority class the order falls to `t_ms` and `instance_key` (T04 section 4.2). The lateness that a consumer can show comes from the verdict stream joined on `xi.instance_key`, not from the alert. (b) `sigma_norm = -1` already had two origins (a clipped finite value, and a failed guard with `hi = -inf`, T04 OP-5); under this rule a failed guard of SCHED at its deadline does not even give `-1` (it gives `-T_s / s`), so `sigma_norm` cannot be used to detect a failed guard, while for the B = 0 templates and RESP a failed guard still gives `-1`. The guard marker therefore travels in `xi.subformula_path` (section 1.4, item 2), as T04 OP-5 requires. (c) The question of T05 OP-T05-19 (does `update` return a refinement record as a changed alert) is answered: it does not, because the alert does not carry the interval. (d) If the clinician wants the displayed lateness to grow, the alternative is to re-issue the violated alert at each refinement (a new value, same identity, as for the cascade links); it is not adopted because it moves a violated alert in the ranked list after the nurse has seen it and changes the evidence cut-off (OP-T07-11).

**Resolution of the flag from the WS01-T06 review (predicted alert; T04 section 4.6, OP-4 and OP-15; T06 sections 2.4 and 10 item 5).** The task text (line 40) says that a predicted alert carries "the normalised forecast sigma-hat, which can be non-negative under the variant possible". T06 adopted the other quantity and handed the field to this task: "Adopted here, at the level of the quantity that this document supplies: the bound `clip(sigma_hat + q, -1, 1)`", "with the consequence that if T07 prefers the point forecast, only that field changes and nothing in the propositions does". **Adopted: `sigma_norm = clip(sigma_hat + q, -1, 1)`.** Reasons. (1) It is negative for every emitted alert, so the contract range `[-1, 0)` holds for both verdicts and CP5, as far as the range is concerned, does not arise for a predicted alert; the point forecast can be non-negative whenever the quantile is negative, and under the variant "possible", where the emission test is on the lower quantile. (2) One rule covers both verdicts: *`sigma_norm` is the bound that the emitting rule compared with zero* (`hi < 0` for a violated record, `sigma_hat + q < 0` for a predicted one). (3) It is the quantity of WS05-T04 step 8 and of WS05-T08 tests 5 and 15 (`-0.7333 + 0.4 = -0.3333`; for V-PRED-1, `-0.3333 + 0.09 = -0.2433`). (4) Nothing in the contract forbids it: the prohibition of normalising by the width of a conformal interval (analisi §4.2, `#template` rules, T04 section 6) is about a division; the scale stays the registry value `scale_<id>` and the quantile is added after the normalisation of the forecast, not used to scale it. **Cost, accepted and reported (T04 section 4.6 reasons 1 and 2, T06 section 2.4).** The value moves with the calibration set, with `alpha` and with the forecaster version, and it carries part of the uncertainty that rho also carries, so severity and confidence are correlated through `q` (complementary, not independent: analisi §4.8), and the separation of severity from uncertainty that analisi §4.2 asks for (it forbids normalising by the conformal width, for the same reason) is weaker for a predicted alert than for a violated one. The point forecast and the quantile stay in the log of the predictive module (OP-T07-3). **Reading.** The value is not a point estimate of the severity. For the variant "likely", `sigma_hat + q_{1-alpha}` is the upper conformal end: the alert reads "predicted to be at least this severe", and the marginal coverage of the upper quantile (T06 section 5.3) is a statement about the sign event of Proposition 1, not about this value for one alert (T06 sections 1.3 and 5.5): no per-alert guarantee on the value is claimed. For the variant "possible", `sigma_hat + q^lo_alpha` is the lower conformal end, the most pessimistic credible value: the alert reads "a violation cannot be excluded; at the pessimistic end of the range it is this severe", and a rendering that says "at least this severe" would be wrong (section 3.4). The point forecast is not shown as the severity, and a predicted alert sorts after a violated alert of the same priority only under the order K1 of T04 section 4.5 (OP-T07-3), which is why K1 is recommended together with this rule. The variant is not a field of the alert or of the record; it is a per-run option (`MonitorConfig.variant`) that the renderer reads (AH-7, OP-T07-7).

### 1.6 Rho of an alert, and the display of a low rho

The `rho` of an alert is the `rho` of the record that produced it, unchanged: for a VIOLATED alert a `Rho` of kind MEASURED (RANGE, HOLD and RESP margins) or DETERMINISTIC (guards, SCHED, COUNT, SYS, INT), by the table of T06 section 2.3; for a predicted alert a `Rho` of kind PREDICTED with `value = m / (n + 1)` and `Rho.alpha` the level at which the emission test ran (the configured level, or the per-test level when the level is allocated over the tests of a patient-day: T06 sections 2.2 and 6.2). It carries `kind`, `guarantee` and `assumptions` with the exact strings of T06 section 2.2, and the renderer shows the kind and the guarantee in words wherever it shows the number. When a predicted alert is replaced (T6), the predicted `rho` is dropped with it (T06 section 1.2). Two display rules.

- *The value of a predicted alert is not the probability that the violation will occur and not the precision of the alerts* (T06 sections 1.3 and 5.5). The text says that it is a conformal score with a guarantee that is marginal over patient episodes under exchangeability.
- *A low value on a "possible" alert is not an inconsistency* (T06 section 2.4 and section 10 item 3; golden C-3: value 0.3 at `alpha = 0.2`). For that variant the level `alpha` bounds the missed violations (Proposition 1b), not the value, and an alert is issued whenever a violation cannot be excluded. The text names the variant ("possible-violation early warning") and does not present a value below `1 - alpha` as a weak alert. For the variant "likely" an emitted alert has a value of at least `1 - alpha` (T06 section 4.6, Lemma 1 (i)).

### 1.7 Kappa, and the attributed cause of a predicted alert (CP13)

**What is fixed for every alert.** Kappa is produced by the attribution layer from the evidence vector, never by the violated sub-formula alone: deriving C2 from the fact that phi_SYS is violated is circular, and "low confidence" does not identify C3 (analisi §4.5; R2 weakness 7). Provenance is context and never sufficient (TM Non-claims 6). `UNDETERMINED` is a valid output and is scored (ADR-010; contract). Kappa never suppresses an alert: a violated verdict is always reported, and kappa changes the wording of the alert and the offered action, not its existence (check 6 of the task text of WS02-T04). A device fault or an integrity violation is not a violation of the care plan: only a violation of phi_CP is (T01 section 6.2 rule 2), the causes C1, C2 and C3 are values of kappa and "a C2 violation" is not written (rule 3), and C3 names an integrity or plausibility violation against declared attack classes (ADR-002; TM).

**CP13.** The contract says that the attribution step "turns violated records into alerts" (`#monitor`), takes `violated: Sequence[VerdictRecord]` (`#attribution`), and defines `Alert.verdict` as "VIOLATED or PREDICTED_VIOLATION"; kappa of a predicted alert is therefore not defined by the text. **Adopted: the attribution layer builds an alert for a record in either violation-claiming state (AH-2), and for a PREDICTED_VIOLATION record it sets `kappa = UNDETERMINED`, `label = UNDETERMINED` and `xi.evidence_used` empty, without evaluating the rule. The definitive alert that supersedes it (T6) carries the kappa of the rule on the evidence at the cut-off of the first VIOLATED record.** Reasons.

1. *Definition.* Kappa names the cause of a violation; at the prediction instant there is none (T05 (P2), the verdict is "early warning, never definitive"), and a cause attributed to an event that has not happened is a statement about the future.
2. *The evidence is not there yet for the main predictive case.* The predictive targets are the care-delivery deadlines of the robot (T05 section 5.3; the SCHED instance is "the main case"). The evidence that a late measurement is a system failure is a robot task outcome. By hypothesis H-OVERRUN of EC, a task that misses its deadline is reported by the robot node as an event "stamped with the deadline of the task", and the evidence window of a record that is not yet decided is cut at `t_eval_ms` (EC, section Evidence window), before the deadline. At the prediction instant the overrun report is therefore not in the window, and unless other system evidence is already asserted the hierarchy of ADR-010 would find none and, with the channels that are available coherent, would reach the third rule of the contract (a violation with coherent channels is C1): a warning that the robot will be late would be labelled a clinical or adherence deviation. Abstaining is the honest output (analisi §4.5, translated from the Italian source: the class UNDETERMINED is essential; invariant I4 of the task text of WS02-T04: no certainty from missing data).
3. *It keeps the metrics honest, with one consequence for them.* WS08 README E3 and E4 compute attribution on matched pairs, and E3 makes an early warning the matched detection when it is the earliest detection in the window; with kappa of a predicted alert UNDETERMINED by definition, such a pair would count as an abstention by construction. The attribution of a pair whose matched detection is a predicted alert must therefore be read from the alert that supersedes it (the same `xi.instance_key`), and a predicted alert that is never superseded (a false predictive alarm) has no attribution to score; predicted alerts are scored by the predictive metrics (coverage, false predictive alarms, lead time, E6 and E7) (OP-T07-10).
4. *It is what the plan scenario assumes* (WS01-T08 row R5: kappa UNDETERMINED, CP13).

**Tensions recorded (CP13 in section 9).** (a) EC decision D-1 builds an evidence vector for a PREDICTED_VIOLATION record and TM ("Attacks that raise no violation") reads the Attributor as taking the predicted violations as well; the vector is harmless but unused for kappa. (b) The task text of WS02-T04 (check 8) proposes a provisional kappa from the evidence at `t_eval_ms`, and WS05-T07 test 20 expects "an alert with a provisional kappa" and test 25 an "early warning" rendering: the part "replaced, not duplicated" is adopted here (section 1.4), the part "provisional kappa" is not. (c) The contract wording "violated records" is read as "records that claim a violation", the reading of TM. **Not adopted, and why.** A provisional kappa from the same rule (unsound for the case in reason 2), or a provisional kappa restricted to C2 and C3 when system or integrity evidence is already asserted (it avoids the unsound C1; the benefit is an early system label for a warning, which the benchmark can show only after the rule document exists): a possible refinement for WS02-T04 if the benchmark shows a gain, not a decision of this task.

### 1.8 Cascades

**Fields.** `root_cause_of` (on the root) and `caused_by` (on the effect), analisi §4.9 item 3 (translated from the Italian source): a C2 generates downstream violations that look like C1 (a missed measurement, the counter, a drug response that cannot be verified), and the attribution must propagate the cause, otherwise the alerts multiply. **What this document fixes** (requirements on the cascade table of WS02-T04, which does not exist yet, AH-10):

1. Both fields hold `xi.instance_key` values of alerts of the same care plan (EC D-1: the key is per care plan).
2. They are mutual inverses: `b.caused_by == a.xi.instance_key` if and only if `b.xi.instance_key` is in `a.root_cause_of`.
3. The relation is acyclic, and an effect carries the kappa of its root (invariant I6 of the task text of WS02-T04).
4. Only VIOLATED alerts take part. A predicted alert has `caused_by = None` and `root_cause_of` empty, is never folded and never a root; a cascade link is computed on the violated alerts only.
5. Folding hides and does not delete: the effect is still an `Alert` returned by `attribute_all`, its `VerdictRecord` stays, and a consumer that shows only top-level alerts filters on `caused_by is None`. An effect keeps its own `sigma_norm`, `rho` and `priority`; nothing is inherited except kappa.
6. Which pairs are linked is the cascade table of WS02-T04, not this document. FM distinguishes a *fan-out* (one emptied position violates several instances that do not cause one another, CAS-1) from a *chain*; the links of the example below follow analisi §4.9 item 3 and the plan scenario R3 and R4 of WS01-T08 (a missed measurement makes the response obligation unmet) and are not a claim that the root violation causes the effect in the sense of a chain.
7. A link can appear after the first issue of an alert; the alert is then re-issued with only the link field changed (section 1.4, item 3), the other fields being those of the first issue.

**Example (F0; instance keys illustrative: the contract example is `resp@2026-01-01T07:00`).** The cuff node crashes before the 09:00 tick. The SCHED instance of the tick is VIOLATED at 09:30 (V-SCHED-3: `[-inf, -60000]` ms, `sigma_norm` -0.0333, rho DETERMINISTIC 1.0, guard `no_measurement_after_tick`, kappa C2 from system evidence, priority 3): the root alert, `root_cause_of = ("resp@07:00",)`. The RESP instance of the 07:00 dispense has its window [08:00, 10:00] with no measurement and is VIOLATED at 10:00 (V-RESP-5: `[-inf, -inf]` mmHg, `sigma_norm` -1.0, rho DETERMINISTIC 1.0, guard `obligation_unmet`): the effect alert, `caused_by = "sched@09:00"`, kappa C2 inherited, not a top-level alert. The effect has the more severe `sigma_norm` and is hidden under the root; both alerts remain in the output.

### 1.9 Worked tuples (F0, illustrative)

All values are fixture arithmetic or analisi examples labelled illustrative, unverified; kappa is shown as given by the plan scenario of WS01-T08 and is provisional until the rule document of WS02-T04 exists. The paths are descriptions, not the final syntax.

| Field | A: RANGE, G-RANGE-2 and C-6 | B: SCHED, V-SCHED-3 | C: COUNT, V-COUNT-1 | D: SCHED predicted, V-PRED-1 | D': SCHED violated, V-PRED-3 (replaces D) |
|---|---|---|---|---|---|
| `tau` | `range` | `sched` | `count` | `sched` | `sched` |
| `verdict` | VIOLATED | VIOLATED | VIOLATED | PREDICTED_VIOLATION | VIOLATED |
| `t_ms` | 32700000 (09:05) | 34200000 (09:30) | 75720000 (21:02) | 33000000 (09:10) | 34200000 (09:30) |
| `sigma_norm` | -0.6 (`-12 / 20`) | -0.0333 (`-60000 / 1800000`) | -1.0 (`-1 / 1`) | -0.2433 (`-0.3333 + 0.09`) | -0.0333 |
| `score` | 0.6 | 0.0333 | 1.0 | 0.2433 | 0.0333 |
| `rho` | MEASURED 0.9772 | DETERMINISTIC 1.0 | DETERMINISTIC 1.0 | PREDICTED 0.9 (`alpha` 0.2, `alpha*` 0.1) | DETERMINISTIC 1.0 |
| `kappa` = `label` | C1 (coherent channels, none asserted) | C2 (`system.liveliness_ok` asserted) | UNDETERMINED (no channel separates the causes) | UNDETERMINED (by definition) | by the rule on the evidence at the cut-off (V-PRED-3 has no evidence inputs) |
| `priority` | 2 | 3 | 2 (FIXTURE-ONLY) | 3 | 3 |
| `xi.instance_key` | `range@09:05` | `sched@09:00` | `count@21:02` | `sched@09:00` | `sched@09:00` |
| decisive sub-formula | `bp <= bp_band_high` | guard `no_measurement_after_tick` | `dose_count <= dose_max_24h` | the deadline margin `age >= 0` | guard `no_measurement_after_tick` |
| `xi.param_values` | `bp_band_low` 110.0, `bp_band_high` 140.0 | `sched_window` 1800000.0 | `dose_max_24h` 2.0 | `sched_window` 1800000.0 | `sched_window` 1800000.0 |
| `xi.evidence_used` | none asserted | `system.liveliness_ok` | empty (abstention) | empty | by the rule |

Recomputation. A: sigma `min(152 - 110, 140 - 152) = -12` mmHg (G-RANGE-2), `-12 / 20 = -0.6`, rho `Phi((110 - 152) / 6) + Phi((152 - 140) / 6) = Phi(-7) + Phi(2) = 0.9772` (the term `Phi(-7)` is about `1.3e-12`; C-6 gives 0.97725 for the single-limit form); 09:05 is `(9 * 60 + 5) * 60000 = 32700000`. B: tick 09:00, `sched_window` 1800000 ms, deadline step `k_d = 570`, `hi = (k_d - (k_d + 1)) * T_s = -60000` ms, `-60000 / 1800000 = -0.0333`; 09:30 is `34200000`. C: the dispenses 07:00, 21:00 and 21:02 give `c_d = 3` against `dose_max_24h = 2`, margin `2 - 3 = -1` dose, `-1 / 1 = -1.0`; 21:02 is `1262 * 60000 = 75720000`. D: forecast arrival 09:40 against the deadline 09:30 gives `-600000 / 1800000 = -0.3333`, calibrator C-1 (`n = 9`, `alpha = 0.2`, `q = 0.09`, `m = 9`): bound `-0.3333 + 0.09 = -0.2433`, `rho = 9 / 10 = 0.9`, `alpha* = 0.1`; 09:10 is `33000000`. D': at 09:30 with no measurement the record of V-PRED-3 is VIOLATED and the alert is the one of column B.

### 1.10 Hypotheses

Every statement above rests on the hypotheses below; none is hidden.

| Id | Hypothesis | Where it is verified, or why it is open |
|---|---|---|
| AH-1 | The unit of an alert is the template instance, and the identity of an alert within a care plan is `xi.instance_key`. | Verified by reading: T05 sections 3.8 and 6.2; contract (`instance_key` unique within a care plan). Open for a ward-wide list: `Alert` has no patient or care-plan identifier (T04 OP-6; ADR-028); OP-T07-8. |
| AH-2 | An alert exists only for a record in a violation-claiming state, VIOLATED or PREDICTED_VIOLATION; "violated records" of `#monitor` and `#attribution` is read that way. | The contract field `Alert.verdict` and TM ("Attacks that raise no violation") read it so; the literal text of `#monitor` does not. Open as a wording clarification: OP-T07-4. |
| AH-3 | The alert is built from the first VIOLATED record (step `k*`), and its `sigma_norm`, `t_ms`, `rho` and the evidence cut-off do not change later. | T05 Lemma 4 (c) and the transitions T3 and T6; EC (cut-off rule 3). Verified by reading. The freezing itself is a decision of this document (section 1.5). |
| AH-4 | `VerdictRecord.sigma_norm_interval` carries `(N_s(lo), N_s(hi))`, so `N_s(hi)` needs no new field. | Contract field and T05 section 3.1. Verified by reading. |
| AH-5 | The frozen `sigma_norm` of a violated alert is never more severe than the resolved value of the instance. | Only under (H-fin), (H-dom) and (H-grid) and where the accepted trace is defined (T05 Lemma 8); outside (H-dom) not claimed (T05 section 2.5). |
| AH-6 | The bound of a predicted alert reaches the attribution layer. | Needs `VerdictRecord.predicted_sigma_norm` (WS05-T04 step 8), which is proposed and not in contract 0.1.0. Open until the ADR of WS05-T04 is accepted (OP-T07-3). |
| AH-7 | The predictive variant is a per-run option, readable by the renderer, and not a per-alert field. | `MonitorConfig.variant` (contract). Open if a run mixes variants (OP-T07-7). |
| AH-8 | An instance has at most one predictive alarm. | T05 section 4.3 (sticky warning, consequence 1). Verified by reading. A monitor that re-evaluates at every step is not covered (T06 section 4.3). |
| AH-9 | The main predictive target is a care-delivery deadline, and the evidence for its cause is stamped at the deadline. | T05 section 5.3; EC H-OVERRUN and check EX-11. The argument of section 1.7 for UNDETERMINED rests on it; for other targets (heart rate and SpO2 are read by no template, T05 section 5.3) it is open. |
| AH-10 | The links of a cascade are decided by the cascade table of WS02-T04. | That document does not exist yet. The constraints of section 1.8 (inverse, acyclic, same kappa) are quoted from the task text of WS02-T04 (invariant I6), so they are requirements on it and not results. |
| AH-11 | Scales and priorities exist for the template of an alert. | With registry 0.1.0 only RANGE and SCHED can be both normalised and ranked; COUNT lacks a priority, HOLD a scale, RESP, SYS and INT both (T04 section 3.1). Every example here therefore uses F0 and says so; a run before the clinician review uses the fixture registry of ADR-027 (proposed). |
| AH-12 | The kind of rho follows T06 section 2.3, including SYS as DETERMINISTIC. | T06 section 10 item 6 adopts it and names the alternative (a MEASURED rho for SYS with a timing error parameter, which the registry does not have); the other kinds are not affected. |
| AH-13 | Instance keys are strings unique within a care plan; the format in the examples (`sched@09:00`) is illustrative. | Contract example `resp@2026-01-01T07:00`; the golden files use `sched@32400000`. |
| AH-14 | `xi.param_values` lists the values that the instance used, however the plan stores them. | The contract does not say whether `TemplateInstance.param_values` holds only the values that differ from the registry or all of them (T03 section 5.3 item 6, OP-6). Open. |
| AH-15 | The text is rendered from fields, in English, and its comprehensibility is not claimed. | Section 3.4; the check is the vignette study (WS11). |
| AH-16 | The signature covers the fields of the `CarePlan` of contract 0.1.0 and any field added later. | Scope is defined as every field except `signature` (section 4.4); the implementation must derive the field list and not hard-code it (WS05-T03). Open as a test requirement. |
| AH-17 | A ward deployment refuses an unsigned plan. | The contract allows `signature` `None`, and TM states that nothing is checked then; the requirement is made here and the mechanism (`require_signature`) is planned in WS05-T03 test 28. Open. |
| AH-18 | A compromised back-end, a compromised signing key and a compromised specification are outside the claim. | TM, section Exclusions (rows 3 to 5). The governance of section 4 is limited accordingly. |

## 2 Decomposition wording

**The decomposition.** The specification is phi = phi_CP and phi_SYS and phi_INT, three separately evaluated conjuncts (T01 section 6.1). Each template instance has its own verdict, unit, scale and priority; no numeric `min` is taken across the three parts, because the raw margins are in mmHg, ms and doses (T04 section 3.2).

| Conjunct | `TemplateKind` | Constrains | Templates |
|---|---|---|---|
| phi_CP | CARE_PLAN | the prescribed care of the patient care plan | RANGE, SCHED, HOLD, COUNT, RESP |
| phi_SYS | SYSTEM | the health of the monitoring system (a measurement is valid only if the cuff node is healthy and the inflation acceptable) | SYS |
| phi_INT | INTEGRITY | the provenance of events (a dispense is backed by a robot witness or an authenticated event) | INT |

**The sentence that is replaced.** The workshop paper, Section III-A, says "A single monitor handles all three classes". It confuses the clinical specification with the system specification (R1 weakness 8; analisi §4.1 item 4), and "classes" is ambiguous between the three conjuncts and the three cause classes C1 to C3; the replacement names the conjunction and the cause separately. The wording that replaces it:

> a single monitor evaluates the conjunction phi = phi_CP and phi_SYS and phi_INT and an attribution layer assigns each alert a cause.

The monitor emits verdict records for the three conjuncts; it does not attribute (`#monitor`: "The monitor separates verdicts from attribution"). The attribution layer assigns kappa. Which conjunct is violated is the provenance evidence of the attribution layer (`provenance.template_kind`), which is context and never sufficient to attribute a cause (TM Non-claims 6; T01 section 6.3).

**Wording rules** (T01 section 6.2, T02 section 6.6, the binding glossary of `01-conventions.md` section 7).

1. "phi_CP" is used only for constraints derived from the patient care plan. The workshop's phi_HW and phi_DOSE appear only in a table caption; here the system constraint is SYS and the dose constraint is COUNT, each with a formula (T02 sections 4.4 and 4.6).
2. **Alert** is the output tuple; **violation** is a violated sub-formula and always names its conjunct (a violation of phi_CP, of phi_SYS or of phi_INT); the **attributed cause** is kappa. A predicted alert is an early warning and does not report a violation, because there is none yet.
3. C1, C2, C3 and UNDETERMINED are values of kappa and are not violations; "a C2 violation" and "a violation of class C3" are not written. C3 is an integrity violation against declared attack classes (ADR-002) and is a cause class; it is not a violation of phi_CP. A violated phi_SYS sub-formula is a violation of phi_SYS, and a device fault is not a violation of the care plan.
4. The cause taxonomy is a cause-based taxonomy over violations of phi_CP and phi_SYS and phi_INT, not a taxonomy induced by the structure of the constraints (analisi §4.8; row 4 of the table of section 3.1).
5. The institutional, population-level object is the **pathway template**; one patient's prescription is the **patient care plan** (`CarePlan`). "Clinical Pathway" is not used for a patient's prescription (section 4.1).
6. **DISPENSE** (the dispenser opened) is not **INTAKE** (verified only by the robot witness, ADR-004); no alert text says that a dose was taken because the dispenser opened.
7. "Robustness" is used only for STL semantics; the severity is `sigma_tilde`.

R1 weakness 8 asked for exactly this: the system constraint and the dose constraint with their own formulas, and a sentence that does not say that one monitor treats clinical and system specification as one.

## 3 Traceability wording

### 3.1 The ten claim reformulations of analisi §4.8

Each row starts with the current claim, quoted (the workshop section is given after it), then the problem and the allowed wording. The "support" column names where the repository supports the allowed wording, for the claim audit of WS12-T07. The audit and the paper text are the human's (ADR-037).

| Current claim | Problem | Allowed wording | Support in this repository |
|---|---|---|---|
| "intrinsic explainability" (Sec. II-B.d, IV) | Pointing to a sub-formula is traceability, not an explanation of the cause; for C2 and C3 the cause is inferred by kappa from evidence, so it is not inherent in the formula. | **specification-level traceability**: each alert references the violated template instance, its clinical parameters, and the evidence used for attribution. | `Explanation` (section 1.3), properties TR-1 to TR-4 (section 3.2), rendering (sections 3.4, 3.5); the vignette study (WS11) if run |
| "a faulty sensor cannot masquerade as a clinical event" (Sec. III-A) | False for silent faults (bias, plausible stuck values): the diagnosability matrix of analisi §4.5 marks them not distinguishable. | faults that manifest in node health, device error codes, or signal quality are attributed to C2; silent faults producing plausible values remain indistinguishable from clinical deviations (Sec. X), with the rate measured on the benchmark. | analisi §4.5 matrix rows 4 and 10; FM CAS-4; `configs/diagnosability.yaml` (WS02-T05); WS08 |
| "two orthogonal axes" (Sec. II-B.d) | Severity and confidence are correlated: near the threshold the confidence falls. | **complementary**. | T06 section 1.3; section 1.2 note 1 |
| "natural taxonomy induced by the constraint structure" (Sec. III-A) | C2 and C3 derive from causes, not from the structure of the constraints. | a **cause-based taxonomy** over violations of phi_CP and phi_SYS and phi_INT. | T01 section 6.2 rule 4; section 2 |
| "Embodiment as a safety asset ... redundancy a passive network cannot" (Sec. IV) | Not measured; the redundancy exists only while the robot is present. | The embodied channel is evaluated by ablation (A4), with and without it, reporting the gain on kappa for C2 and C3 and declaring the temporal coverage. | EC (A4 mask); WS08-T04 |
| "every alert goes through a single auditable verification path" (Sec. II-A) | Read by a reviewer as a single point of failure. | Keep the auditability and add the watchdog and the fallback: the ward node supervises the robot with a heartbeat, and if the robot is unavailable the fallback escalates to the nurse. | ADR-003; analisi §4.9 item 1 |
| "distribution-free coverage" (Sec. II-B.c) | Omits that coverage is marginal and requires exchangeability. | The coverage is marginal over patient episodes under exchangeability; the calibration unit is the patient episode; with many tests per patient-day the level is allocated. | T06 sections 5.1, 6.1 and 6.2 |
| "beyond static edge-based solutions" (contribution 2) | A comparative claim without a comparison. | Remove it, or support it with the ablation and the baselines. | WS06 (B1 to B5), WS08 |
| "to assist nursing staff in real-world hospital wards" (abstract) | There is no real context. | Remove it from the abstract; validation is technical and pre-clinical, in simulation and a laboratory demonstration. | ADR-001 |
| "ensures" (Sec. III-A) | Guarantee language without a proof. | "is designed to", except where the statement is covered by the proposition, with its hypotheses. | T06 section 5.1 (Proposition 1) |

The three reformulations that the vocabulary of the project fixes are "specification-level traceability", "complementary" and "cause-based taxonomy" (`01-conventions.md` section 7). The sentence for traceability is the one of row 1 (analisi §4.8): each alert references the violated template instance, its clinical parameters, and the evidence used for attribution.

### 3.2 What specification-level traceability means, as properties that can be tested

The claim of row 1 is allowed only to the extent that these properties hold for every alert (WS05-T07 tests 21 to 27 are their tests).

- **TR-1 (resolvable instance).** `xi.instance_key` identifies exactly one template instance of the care plan, and `xi.template` equals `tau`.
- **TR-2 (parameters).** Every name in `xi.param_values` is a name in `Template.params` of `tau`, and its value is the value that the monitor used for the instance.
- **TR-3 (evidence).** Every path in `xi.evidence_used` is one of the twenty fields of the `EvidenceVector` (EC canonical `group.field` path), and the field was available and decided kappa; for a predicted alert and for an abstention without a decisive field the list is empty.
- **TR-4 (rendering).** `xi.text` is a deterministic function of the alert, its record and its template (no clock, no locale, no dictionary order), so it can be regenerated from the log.

Traceability is not an explanation of the cause (kappa is inferred by a rule over evidence), not a proof that the rule is correct, and not evidence that a nurse understands the text.

### 3.3 Template names in plain words

The plain words of the renderer are derived from the contract comments of `TemplateId` (they are not new definitions).

| `tau` | Plain words |
|---|---|
| `range` | the measured blood pressure inside the prescribed band |
| `sched` | a blood pressure measurement within the allowed time after the scheduled time |
| `hold` | no dose dispensed while the latest blood pressure is below the hold threshold |
| `count` | the number of doses dispensed in 24 hours within the prescribed limit, and the day-end count obligation |
| `resp` | the prescribed blood pressure decrease, measured in the response window after a dose, relative to the pre-dose reference |
| `sys` | a measurement taken with a healthy cuff node and an acceptable inflation time |
| `int` | a dispense backed by robot-observed presence or by an authenticated event |

### 3.4 Requirements for the natural-language text of `Explanation.text`

The text is for nursing staff. It is generated from the fields, never typed per case, and satisfies these requirements (the first six are the checklist of this task; the others follow from the sections above).

1. **Template in plain words** (section 3.3), not only the identifier.
2. **Instance time:** the time of the anchor of the instance (a measurement time, a tick, a dispense) and the time of the verdict (`t_ms`), as `hh:mm`.
3. **Parameter values with units:** each value of `xi.param_values` with the unit of its registry entry (for example "140 mmHg", "30 minutes", "2 doses").
4. **Evidence used:** in plain words, with the canonical `group.field` path of each decisive field in parentheses; for an abstention, the abstention reason of WS02-T04 and the unavailable fields by path.
5. **Verdict state in words:** "violated (definitive)" or "early warning, not a definitive verdict".
6. **Attributed cause in words:** "clinical or adherence deviation" (C1), "system or embodiment failure" (C2), "integrity or plausibility violation" (C3), "not determined" (UNDETERMINED). A device fault is not described as a violation of the care plan.
7. **Severity and confidence:** the margin in the native unit and the normalised value to two decimals, then the confidence with its kind and its guarantee in plain words (section 1.6).
8. **A violated alert reports the certified bound:** where the value is not final at emission (a SCHED violation at its deadline) the text says "late by at least" the certified amount and never "late by" (section 1.5); the graded lateness belongs to the verdict stream.
9. **A predicted alert** says that it is an early warning, names the variant in words, states the confidence as a conformal score with a guarantee that is marginal over patient episodes under exchangeability and not the probability that the violation will occur, and for the variant "possible" says that the severity is the value at the pessimistic end of the range (sections 1.5 and 1.6). It names no cause (kappa is UNDETERMINED by definition, section 1.7).
10. **DISPENSE and INTAKE:** text about the dispenser says "dispenser opened" or "dispensed"; text about the robot witness says "intake observed".
11. **Cascades:** an effect alert says that it follows from the root alert and names it; a root alert says how many further violations it accounts for.
12. **Determinism:** identical inputs give identical text (TR-4). English only in this version.
13. **Claim wording:** the text uses the glossary and the claim reformulations of analisi §4.8 (the forbidden-term list of `01-conventions.md` section 7 is checked by WS05-T07 test 23) and states no clinical recommendation; actions are those of the action policy of WS02-T04, with clinician confirmation.

**Comprehensibility is deferred.** Whether nursing staff understand the text, and whether it helps them, is not tested here. The vignette study (WS11-T01 designs it) is the check, and until it is run no claim of interpretability is made.

### 3.5 Three example sentences (F0, illustrative)

All numbers are fixture arithmetic or analisi examples labelled illustrative, unverified (ADR-020), recomputed from the golden cases named below. The sentences show the requirements; they are not final wording, and the attributed causes are those of the plan scenario of WS01-T08, provisional until the rule document of WS02-T04 exists.

**Example 1, a clinical deviation (RANGE; G-RANGE-2 and C-6; illustrative numbers).**

> Blood pressure was measured at 09:05 and was 152 mmHg, above the prescribed upper limit of 140 mmHg (band 110 to 140 mmHg). The measurement is 12 mmHg beyond the limit, which is 0.60 of the clinically significant deviation of 20 mmHg. This is a definitive violation. Attributed cause: clinical or adherence deviation, because no system or integrity evidence was found in the channels that were available. Confidence that the true value is outside the band: 0.98, under the declared device error model (standard deviation 6 mmHg), conditional on the adequacy of that model.

Numbers: `152 - 140 = 12`; sigma `min(152 - 110, 140 - 152) = -12` mmHg; `-12 / 20 = -0.60` (`scale_range` 20 mmHg); rho `Phi(-7) + Phi(2) = 0.9772`, shown as 0.98 (`cuff_error_sd` 6 mmHg, FIXTURE-ONLY); 09:05 is `32700000` ms.

**Example 2, a system failure (SCHED; V-SCHED-3; illustrative numbers).**

> The blood pressure measurement scheduled for 09:00 was not taken within the allowed 30 minutes, which ended at 09:30. At 09:30 it is late by at least 1 minute, which is 0.03 of the clinically significant deviation of 30 minutes. This is a definitive violation. Attributed cause: system or embodiment failure, because the cuff node stopped responding (evidence: `system.liveliness_ok`). Confidence: 1.0, given the event log; the authenticity of the events is not covered by this value.

Numbers: `sched_window` 1800000 ms is 30 min (FIXTURE-ONLY); at the deadline step `hi = -60000` ms, 1 min; `-60000 / 1800000 = -0.0333`, shown as 0.03; rho DETERMINISTIC 1.0 (V-SCHED-3); the evidence field is the one of the plan scenario R3.

**Example 3, an undetermined cause (COUNT; V-COUNT-1; illustrative numbers).**

> The dispenser was opened at 21:02. This is the third opening within 24 hours (07:00, 21:00 and 21:02); the prescribed limit is 2 doses. The limit is exceeded by 1 dose, which is 1.00 of the clinically significant deviation of 1 dose. This is a definitive violation. Attributed cause: not determined. The available evidence cannot separate a second dose taken by the patient from a repeated dispenser signal, because no dispenser content evidence is available and the robot was not present (unavailable: `witness.robot_present`, `witness.intake_observed`). Confidence in the count: 1.0, given the dispenser log; the authenticity of the events is not covered by this value.

Numbers: `dose_max_24h` 2 (analisi §4.1, illustrative); `c_d = 3` at 21:02 (V-COUNT-1), margin `2 - 3 = -1` dose, `-1 / 1 = -1.00` (`scale_count` 1 dose); rho DETERMINISTIC 1.0 (T06 C-7); kappa UNDETERMINED as in the scenario R8 of WS01-T08 (CP8, ADR-032 proposed: no dispenser content evidence).

## 4 Care plan governance

### 4.1 The two objects

A **pathway template** is the institutional, population-level specification of a pathology: the set of constraint patterns of the template library of T02 with their registry parameters, identified by `CarePlan.pathway_template_id`. A **patient care plan** is the instance of it for one patient: the contract type `CarePlan`, which holds the template instances with their parameter values, the schedule and the version and signature fields. Two uses of the word must not be confused: the contract text of `#template` calls a single parametric formula "a pathway template", while this document (and the glossary) reserves "pathway template" for the institutional object and writes "template" or "STL template" for a `Template`; the project's `CarePlan` is also not the FHIR resource of the same name, although the mapping of section 5 relates them (OP-T07-12).

### 4.2 Who authors and who evaluates

The clinician authors the plan and the clinician-reviewed registry values; the back-end (off the safety-critical path) issues the signed plan (the topic `/ralmon/care_plan` carries the signed `CarePlan` from the back-end to the RSM, which reads it only). The ward node and the robot evaluate the plan and cannot author or modify a plan, a patient value or the registry (analisi §4.9 item 7: "the robot only evaluates specifications it cannot author or modify"; T03 section 5.3 item 4). The patient-specific calibration of parameters that the workshop paper describes is reconciled with this by versioning and signature (analisi §4.9 item 7; T03 section 5): a value that differs from the pathway template for one patient travels in `TemplateInstance.param_values` inside the signed plan, only for a name with an approved range, and in registry 0.1.0 none is supported (T03 section 5.3 items 2 and 5).

### 4.3 Version fields

| Field of `CarePlan` | Type | Set by | What it pins | Check at load |
|---|---|---|---|---|
| `pathway_template_id` | `str` | back-end | the institutional pathway template the plan instantiates; an identifier, not a version | no check is defined; the contract has no version field for the pathway template itself, so a revised pathway template is a new plan with a higher `plan_version` (OP-T07-12) |
| `registry_version` | `str` | back-end | the exact version of the parameter registry the plan was issued against (`MAJOR.MINOR.PATCH`, T03 section 5.1) | exact string equality with the version of the loaded registry; every bump, a patch included, requires the plans to be issued again (T03 section 5.2) |
| `plan_version` | `int` | back-end | the revision of this patient's plan | not lower than the version already loaded for the same `care_plan_id` (rollback refused; planned in WS05-T04 test 25 and WS05 README D8, not in contract 0.1.0) |

### 4.4 Signature scope

**The signature covers the canonical serialisation of every `CarePlan` field except `signature`.** The fields of `CarePlan` in contract 0.1.0 (`02-interfaces.md#template`) are `care_plan_id`, `pathway_template_id`, `patient_id`, `registry_version`, `instances` (a sequence of `TemplateInstance`, each with `template`, `instance_key`, `param_values` and `anchor_ms`), `schedule`, `plan_version` and `signature`. The signed content is therefore the first seven, with the four fields of every instance. *Canonical* means a deterministic byte form: the field order is fixed, mapping keys are sorted, the order of a sequence is preserved (reordering `instances` or `schedule` is a modification), and a number and `None` have one textual form each. The exact encoding is WS05-T03's (AH-16). The scope is defined by exclusion (every field except `signature`) so that a field added to `CarePlan` later is signed without a change of this definition.

**What the signature does not cover.** The template library (the strings of T02) and the parameter registry file are not part of the plan: the plan is bound to the registry only by the `registry_version` string. T03 section 5.2 proposes recording the registry version and a digest of the registry file in every run manifest, which ties a reported number to the file but does not authenticate the registry to the monitor. The monitor configuration, the device profile and the evidence parameters are not covered either.

### 4.5 Load-time behaviour

The contract says `Monitor.load(plan)` "verifies plan signature if present". The behaviour required by this document, with the source of each check:

| Check | Source | On failure |
|---|---|---|
| signature verifies over the canonical bytes with the configured verifier | contract comment of `Monitor.load`; planned in WS05-T03 tests 24 to 28 | refuse the plan |
| the signature is present, in a ward deployment | requirement of this document (AH-17); the contract allows `None` and TM states that nothing is checked then | refuse the plan |
| `registry_version` equals the loaded registry version | T03 section 5.2 | refuse the plan |
| `plan_version` is not lower than the loaded version of the same `care_plan_id` | WS05-T04 test 25 (planned) | refuse the plan |
| window parameters are multiples of `step_ms` (check F1) and the feasibility checks F2 to F6 pass | T02 section 5.4 (they run in `Monitor.load` together with the signature check) | refuse the plan, naming the check and the offending tick |
| every key of `param_values` equals the registry value or lies in an approved range of `overrides:` | T03 section 5.3 items 2, 3 and 6 | refuse the plan |

**On any failure the monitor refuses the plan, emits no verdict for it, logs the reason, and escalates to the nurse** (the fallback of ADR-003; the escalation on a refused plan is a requirement of this document and is not in the contract). What a refusal means when an older valid plan is already loaded (keep monitoring on the older plan and escalate, or stop) is not decided here; the recommendation is to keep the last valid plan and escalate, because stopping monitoring is also a loss of safety (OP-T07-12).

A failed signature is **not an alert and not an attributed cause C3.** C3 is the cause class of integrity or plausibility violations of the trace against the declared attack classes (ADR-002; TM); a compromised specification is excluded from that claim (TM, section Exclusions: "the mitigation (the care-plan signature and `plan_version`, checked at `Monitor.load` if a signature is present) belongs to WS05, not to attribution"). R1 weakness 9 is closed by the load-time check, not by the attribution layer, and the `Alert` contract has no template for a refused plan.

### 4.6 What is deferred, and what is not claimed

The algorithm, the format of the signature string, and the generation, distribution, rotation and revocation of keys are deferred to WS05-T03, which records them as an ADR (proposed, with the confirmation tag); no library is named here. The limits that follow from TM are part of the claim: the signature is meant to detect accidental corruption, and modification by a party that holds no signing key, between the back-end and the monitor (TM, assumption on keys; WS05-T03 plans the same limit, "accidental corruption and modification in transit only"); a compromised back-end or plan authoring, a compromised key, and insiders with valid credentials are excluded (TM, section Exclusions); and the claim for this item is limited to this: the distributed specification carries a version and an integrity signature that the monitor checks at load, and the scheme and the key management are a deployment matter. No claim of security assurance for a deployment is made.

## 5 FHIR PlanDefinition mapping sketch

### 5.1 What the sketch is

A sketch of a **partial mapping from a standard representation to the templates** (analisi §3.4, translated from the Italian source: showing even partially a mapping from a standard representation, FHIR PlanDefinition or BPMN, to the templates is strong and cheap). The source side is a care plan expressed as a FHIR PlanDefinition and its instantiation as a FHIR CarePlan; the target side is the list of `TemplateInstance` and the `schedule` of the project's `CarePlan`. Every FHIR element name below is marked `[verify: standard text]`: no network access is used and no name is written from memory as a fact; the correspondences are proposals to be checked against the standard text by a human (WS03). Only the standards named in analisi §3.4 appear (FHIR PlanDefinition and CarePlan, Clinical Quality Language, Arden Syntax, openEHR GDL). The sketch is read by a person; no translator exists and none is claimed.

### 5.2 Element correspondences

| Source element (FHIR) | Project element | What the correspondence gives | What it leaves out |
|---|---|---|---|
| goal target: `PlanDefinition.goal.target.measure` `[verify: standard text]`, `PlanDefinition.goal.target.detail[x]` `[verify: standard text]` (a range of the pressure) | `bp_band_low`, `bp_band_high` of RANGE; `bp_hold_threshold` of HOLD | the bounds of the band and the threshold, with their unit (example with F0 values, illustrative, unverified: 110 and 140 mmHg; 100 mmHg) | the per-measurement instance semantics, the margin, the scale, the priority |
| action timing: `PlanDefinition.action.timing[x]` `[verify: standard text]` | `CarePlan.schedule` (the measurement and dispense ticks); the anchor of SCHED instances | the times of the ticks; the kind of each tick (measurement or dispense) must be read from the action it belongs to, which the project's `schedule` does not record (T02 TG-1) | the allowed delay after a tick (`sched_window`) when the timing element carries none |
| related-action offsets: `PlanDefinition.action.relatedAction.relationship` `[verify: standard text]` and `PlanDefinition.action.relatedAction.offset[x]` `[verify: standard text]` (an offset range after the start of the dispense action) | the RESP window `delta1` to `delta2` (example: offsets of 1 h and 3 h after a 07:00 dispense give [08:00, 10:00], analisi §4.6, F0 3600000 and 10800000 ms); the HOLD precedence and look-back `hold_lookback` (a measurement action before the dispense action within an offset) | the window of the response and the order of two actions | the pre-dose reference (`bp_pre`), the response threshold `delta_resp` unless a goal target of change carries it, the guard semantics (a missing measurement is a failed guard, not a graded lateness) |
| conditions: `PlanDefinition.action.condition.kind` `[verify: standard text]` and `PlanDefinition.action.condition.expression` `[verify: standard text]` | the guards of the templates (for HOLD, the condition on the latest pressure; for RESP, the measurement in the window) | the Boolean condition of an action, in an expression language such as Clinical Quality Language `[verify: standard text]` | which of several readings counts (HOLD refined form, T02 section 4.3) unless the expression says so; quantitative margins |
| dose limit: `Dosage.maxDosePerPeriod` `[verify: standard text]` (carried by the dosage of the dispensing action) | `dose_max_24h` of COUNT | the limit of doses in a period | the trailing 24 h window as a derived signal, the day-end minimum `dose_min_day_end` |
| care plan instantiation of a plan definition: `CarePlan.instantiatesCanonical` `[verify: standard text]` | `CarePlan.pathway_template_id` | the link from the patient care plan to the institutional pathway template | the version of the pathway template (no field in the project's `CarePlan`) |
| versioning: `PlanDefinition.version` `[verify: standard text]` for the pathway template, resource-level versioning of the standard for the patient plan (`meta.versionId` `[verify: standard text]`) | `plan_version` for the patient plan; no counterpart for the pathway template revision | the revision of the patient's plan | the pathway template revision; the pinned `registry_version` |
| provenance and signature | `signature` | none assumed: the standards named in analisi §3.4 are not assumed to carry the project's signature over the canonical serialisation; a provenance mechanism of the standard, if used, is to be checked `[verify: standard text]` | the canonical serialisation and the scope of section 4.4 |

### 5.3 Other standards named in analisi §3.4

Clinical Quality Language `[verify: standard text]`, Arden Syntax `[verify: standard text]` and openEHR GDL `[verify: standard text]` are named in analisi §3.4 as standards for the logic of guidelines. They are expected to be able to carry the Boolean conditions of the guards (the condition and action logic over clinical data) and not the sampled signals, the quantitative margin or the derived signals; this is a reading of their purpose and has not been checked against the standard texts. They are not mapped here.

## 6 BPMN mapping sketch

### 6.1 What the sketch is

The same kind of sketch for a care pathway drawn as a BPMN process. Every BPMN construct name below is marked `[verify: standard text]` for the same reason as in section 5. As assumed here (to be verified against the standard text `[verify: standard text]`), BPMN is a notation for control flow, timers and message exchanges between participants; it has no sampled signals, no derived signals and no quantitative robustness, so a mapping yields the Boolean skeleton and the windows of a template and never the margin, the scale or the priority. The extension of BPMN for clinical pathways named in analisi §3.4, BPMN4CP (Braun et al., 2014, marked with a dagger in the analysis), is cited here by name only: `[ref-needed: WS03]`. Its constructs are not described, because no description is written from memory.

### 6.2 Construct correspondences

| Source construct (BPMN) | Project element | What the correspondence gives | What it leaves out |
|---|---|---|---|
| timer event and boundary timer event on a task: intermediate timer catch event `[verify: standard text]`, timer boundary event `[verify: standard text]` | the SCHED window (`sched_window`) as a boundary timer on the measurement task, with the tick as the start; the RESP window (`delta1` as a timer before the response task, `delta2` as the boundary timer that ends it) | the deadline structure and the durations of SCHED and RESP | the graded lateness (a timer fires, it does not measure how late the event is), the margin, the guard failure markers |
| exclusive gateway before the dispense task: exclusive gateway `[verify: standard text]` | HOLD: the branch condition on the latest measured pressure against `bp_hold_threshold`, with the branch "do not dispense" | the Boolean hold condition at the dispense | the look-back window as a timestamp condition unless the expression states it, the choice of the latest of several readings |
| multi-instance activity or loop with a counter: multi-instance activity `[verify: standard text]`, loop marker `[verify: standard text]` | COUNT: a bounded number of repetitions of the dispense task, `dose_max_24h` | the limit as a bound on repetitions | the trailing 24 h window, the day-end obligation, the unscheduled dispense (a process models the planned flow) |
| message flow and participant: message event `[verify: standard text]`, participant or lane `[verify: standard text]` | INT: the witness as a message from the robot participant to the process before the dispense task | the existence and order of a witness message | the backward window `int_window`, the provenance of the event, the authenticated alternative |
| exclusive gateway after a measurement task | RANGE: the band condition on each planned measurement | the band bounds as constants of a condition | measurements outside the plan, the margin |
| (no counterpart) | SYS: health of the cuff node and inflation duration | nothing: an error boundary event `[verify: standard text]` could carry the occurrence of a device error, not the duration threshold or the health status | the whole template |

## 7 Coverage and limits of the mapping

### 7.1 Definitions

For each template, a source representation supports the mapping **fully** if every registry parameter named in the template's `params` (T02 section 3.1) and its trigger and window structure have a counterpart element, **partly** if some have, and **not** if none has. A trigger alone (a task that is a measurement or a dispense) does not count as a counterpart of the constraint. "Fully" is about the Boolean skeleton of the template: no standard element carries the margin, the scale or the priority. The judgements come from reading the correspondences of sections 5.2 and 6.2; they are not tested on any real pathway document, and they hold only if the element names, once verified, mean what the sketch assumes.

### 7.2 Per template

| Template | FHIR PlanDefinition | BPMN | What a standard representation does not carry |
|---|---|---|---|
| RANGE | partly: bounds from a goal target; the per-measurement trigger is not expressed | partly: a gateway on planned measurements | the margin to the nearer limit, the scale, the priority, measurements that the plan did not announce |
| SCHED | partly: the ticks from the action timing; the allowed delay only if the representation carries one | fully, for the Boolean skeleton: a boundary timer with the window | the graded lateness (time robustness), the scale, the priority |
| HOLD | partly: the precedence and look-back from an offset, the condition from an expression | partly: a gateway before the dispense | the "latest reading" semantics of the refined form, the margin in mmHg, the guard failure marker |
| COUNT | partly: the limit of doses per period; not the day-end minimum | partly: a bounded loop; not the trailing window or the day-end obligation | the derived counter `dose_count`, the trailing 24 h window, the unit `dose`, the unscheduled dispense |
| RESP | partly: the window from offsets; not the pre-dose reference or the response threshold | partly: the window from timers; not the pre-dose reference | the derived signal `bp_pre` and `bp_drop`, the per-instance capture, the margin, the guard `obligation_unmet` |
| SYS | not | not | the health of the monitoring system and the inflation duration: a phi_SYS constraint is not part of a care pathway |
| INT | not | partly: a message from the robot participant | the provenance of the event, the backward window, the authenticated alternative, the robot channels and their availability |

What no standard representation carries, for any template: signal-level quantitative constraints (the margin in the unit of the template), the scale and the priority of each template (registry values fixed with the clinician), the derived signals (counters, the pre-dose reference), the instance semantics (one instance per anchor, evaluated at the decision step), the monitor configuration (`step_ms`, `reorder_delay_ms`), the evidence channels and the diagnosability matrix, and the three-valued verdicts. A pathway drawn in either representation therefore yields at best the structure and the parameters of the Boolean skeleton of the templates it names, to which a clinician and the registry add the rest.

### 7.3 Wording and limits of the claim

The allowed wording is **a partial mapping from a standard representation to the templates** (analisi §3.4). Not claimed: an automatic translation (the sketch is read and applied by a person); that a pathway document in use in a hospital maps onto the templates; that the mapping preserves the clinical meaning (that is the clinician's review); that the element names are those of the standards (all are marked for verification); any validation on real pathway documents. The related-work note `docs/related-work/citation-selection.md` (P3) says that FHIR PlanDefinition and CarePlan is "the standard representation the paper targets"; that sentence must stay consistent with this one and be read as a partial mapping sketch (OP-T07-13).

## 8 Paper excerpt (Section III and mapping sentence)

Not written: paper text is outside the agent's scope (ADR-037)

## 9 Open points for WS01-T08

Each item gives the anchor, the resolution adopted or the question handed over, and whether an ADR is needed. None edits `02-interfaces.md`. No ADR is appended by this task: no decision below changes a signature, and WS01-T08 groups the alert, verdict and registry points of ADR-021 into its ADRs; the grouping suggested at the end of this section is for it. Items marked "downstream" name task files whose text this document contradicts or refines; their files are not edited here.

**CP5 (range and direction; `02-interfaces.md#alert`, `sigma_norm` and `priority`).** *Adopted (section 1.5):* the contract range `[-1, 0)` holds for both verdicts, because `sigma_norm` is the bound that the emitting rule compared with zero: `N_s(hi)` of the first VIOLATED record (negative because `hi < 0` and `N_s` keeps the sign, T04 Lemma 2) and `clip(sigma_hat + q, -1, 1)` for a predicted alert (negative because `sigma_hat + q < 0`). In floating point the range reads `[-1, 0]` (T04 section 2.3 (a)). The direction of `priority` (1 is the highest) is closed by T04 section 4.3 (OP-2 there). *Gap:* the comment "in [-1, 0) for a violation" does not say that the field is a bound and not a point value; a clarification of the comment is proposed, with no signature change. The task text (line 40) assumed that a predicted alert can be non-negative (range `[-1, 1]`, as in T04 section 4.6); that assumption is not adopted. *ADR:* a clarification of the comment, at the discretion of WS01-T08. *Anchors:* T04 section 4.6 and OP-1; T05 section 3.7; T06 section 2.4.

**CP13 (kappa of a predicted alert; `#monitor`, `#attribution`, `#alert`).** *Adopted (section 1.7):* the attribution layer builds an alert for VIOLATED and for PREDICTED_VIOLATION records, and for a predicted alert `kappa = UNDETERMINED`, `label = UNDETERMINED`, `xi.evidence_used` empty, without evaluating the rule; the violated alert that supersedes it carries the kappa of the rule on the evidence at the cut-off of the first VIOLATED record. *Tensions:* (1) `#monitor` ("turns violated records into alerts") and `#attribution` (`violated: Sequence[VerdictRecord]`) against `Alert.verdict` (VIOLATED or PREDICTED_VIOLATION); read as "records that claim a violation", the reading of TM (section "Attacks that raise no violation"); (2) EC decision D-1 builds an evidence vector for a predicted record and EC decision D-7 says that the alert of WS05-T07 `update` "already replaces predicted alerts"; (3) downstream: the task text of WS02-T04 (check 8, "provisional κ from the evidence available at `t_eval_ms`") and step 5, WS05-T07 tests 20 and 25 ("an alert with a provisional kappa"); the replace-not-duplicate part is adopted, the provisional kappa is not; (4) WS01-T08 row R5 already assumes UNDETERMINED. *ADR:* a clarification of the contract text (the word "violated"), at the discretion of WS01-T08; a restricted provisional kappa (C2 and C3 only) is a possible refinement for WS02-T04 if the benchmark shows a gain.

**OP-T07-1 Severity of a VIOLATED alert (the flag from the WS01-T04 review).** *Adopted (section 1.5):* `sigma_norm = N_s(hi)` of the first VIOLATED record, frozen at emission; the refinement records do not change the alert. *Anchors:* T04 section 4.7, OP-9 and OP-14 (the upper-end rule is not stated there); T05 section 3.7 and Lemma 8 (the rule is fixed at the verdict layer and the field handed to this task); WS01-T08 R3; WS05 README D7; WS05-T07 test 3. *Consequences:* every SCHED alert has `sigma_norm = -T_s / s` at emission (F0 `-0.0333`); `sigma_norm` cannot be used to detect a failed guard (a failed SCHED guard gives `-T_s / s`); the graded lateness is in the verdict stream. *ADR:* none; the decision for the clinician is whether the displayed lateness should grow (OP-T07-11).

**OP-T07-2 Severity of a predicted alert (the flag from the WS01-T06 review).** *Adopted (section 1.5):* `sigma_norm = clip(sigma_hat + q, -1, 1)`, with `sigma_hat` clipped into the interval of the record and `q` the quantile of the variant that emitted. *Anchors:* T04 section 4.6, OP-4 and OP-15 (the point forecast, proposed there); T06 section 2.4 and section 10 item 5 (the bound, adopted as the quantity and handed over); T05 section 5.5; WS05-T04 step 8; WS05-T08 tests 5 and 15 (consistent with the bound). *Alternative not adopted:* the point forecast `clip(sigma_hat, -1, 1)`, with range `[-1, 1]` and CP5 left open; the change is confined to this one field and to the order of predicted alerts. *ADR:* none beyond the carrier field of WS05-T04 step 8.

**OP-T07-3 Carrier and logging of the predicted bound (`#verdict`).** `VerdictRecord` has no field for the bound or for `sigma_hat`, `q`, `alpha`, `n` and the variant. The bound is carried by `predicted_sigma_norm` (WS05-T04 step 8, proposed with its ADR); the other quantities belong to the log of the predictive module (WS05-T08), which the audit of a predicted alert and ablation A1 need. Also open: whether a predicted alert sorts after a violated alert of the same priority (K1 of T04 section 4.5, ADR-028 proposed), which keeps the calibration-dependence of a predicted `sigma_norm` away from the order of certified violations. *Downstream:* WS05-T08.

**OP-T07-4 The word "violated" in `#monitor` and `#attribution`.** Read as "claiming a violation" (AH-2). A sentence in the contract text is enough. *ADR:* with CP13.

**OP-T07-5 Closure of a predicted alert.** When the instance ends SATISFIED (T7) the predicted alert is closed as a false predictive alarm, and `Alert` has no state to say so: a consumer that subscribes only to `/ralmon/alerts` cannot see the closure. Options: the nurse interface also subscribes to `/ralmon/verdicts`; or a closure notice is added to the contract. *Downstream:* WS05-T09, WS07.

**OP-T07-6 Carrier and syntax of the path (`Explanation.subformula_path`, `VerdictRecord`).** The field is one `str`; this document asks for the decisive sub-formula first and the other violated sub-formulas after it, separated by `;`, and for the guard marker to be recoverable (section 1.4, item 2). `VerdictRecord` has no path field in contract 0.1.0 (WS05-T04 step 8 proposes `subformula_path: str or None`, default `None`); an alert from a record whose path is `None` has no source for `xi.subformula_path`. A dedicated field for the guard marker would be cleaner. *Downstream:* WS05-T04 step 8, WS05-T07 test 27.

**OP-T07-7 The predictive variant is not carried by the alert.** Neither `Alert`, `Rho` nor `VerdictRecord` carries "likely" or "possible"; the renderer reads `MonitorConfig.variant` (AH-7). T06 section 10 item 3 handed to this task "how the alert shows a low rho with a flagged variant": answered by the display rules of section 1.6 and requirement 9 of section 3.4, which need the variant. If a run can mix variants, a field is needed (a version bump).

**OP-T07-8 Identity of an alert beyond one care plan.** `Alert` has no patient or care-plan identifier; the identity `xi.instance_key` is per care plan (EC D-1; T04 OP-6; ADR-028). A ward-level list, a cross-patient order and the cascade keys need the identifier.

**OP-T07-9 The meaning of `t_ms`.** An event time (`decided_at_ms`, or `t_eval_ms` for a predicted alert), not the monitor time of emission (section 1.3). T04 section 4.1 writes "the time at which the alert is emitted"; the order of T04 does not change (an event time is a function of the log, as the tie-break of T04 section 4.2 requires; a monitor time with the compute jitter of a run would make the order depend on the run). *Downstream:* WS08 `detection_delay_ms` (relative to the first decidable instant) is zero for a violated alert by construction; the emission latency is a separate metric.

**OP-T07-10 Which alerts feed which metrics.** Predicted alerts have `label` UNDETERMINED by definition. WS08 README E3 lets an early warning be the matched detection of a ground-truth event, and E4 scores attribution on matched pairs with UNDETERMINED as an abstention, so a pair matched by a predicted alert would be an abstention by construction. Proposed: the attribution of a matched pair is read from the alert that supersedes the matched predicted alert (same `xi.instance_key`), a predicted alert never superseded has no attribution to score, and predicted alerts are scored by the predictive metrics (`empirical_coverage`, false predictive alarms, `detection_delay_ms` with negative values for early warnings, E6 and E7). The `Metrics` contract and E4 do not say so. *Downstream:* WS08-T01.

**OP-T07-11 Frozen alert and refinement.** Adopted: frozen at emission; the link fields are the only fields re-issued. T05 OP-T05-19 (does `update` return a refinement record as a changed alert) is answered: no. Question for the clinician review (WS00-T07): whether the displayed lateness of a late measurement should grow with the refinement; if so, the alert is re-issued at each refinement, and the evidence cut-off and the stability of the ranked list must be reconsidered. *Downstream:* WS05-T07 test 18.

**OP-T07-12 Governance (section 4).** (a) The contract has no version field for the pathway template (`pathway_template_id` only); a revised pathway template is a new plan with a higher `plan_version`. (b) The word "pathway template" in the contract text of `#template` names a single parametric formula, against the glossary; a wording fix. (c) The behaviour when a refused plan update meets an older valid plan is not decided (recommendation: keep the last valid plan and escalate). (d) A ward deployment must require the signature (AH-17). (e) The template library and the registry file are bound to the plan only by the `registry_version` string (section 4.4); T03 section 5.2 proposes the registry digest in run manifests. (f) The algorithm, the key management and the format of the signature are WS05-T03's ADR; the sources fix no scheme (analisi §4.9 item 7 says "versioning and signature"). (g) The escalation on a refused plan is a requirement of this document (ADR-003 is the precedent), not a contract text. *Downstream:* WS05-T03, WS05-T04 test 25, WS07.

**OP-T07-13 Mapping (sections 5 to 7).** (a) The FHIR and BPMN element names are all marked for verification and none is verified; WS03 or the human checks them against the standard texts. (b) The mapping of timing to `schedule` needs the kind of each tick (T02 TG-1). (c) The related-work note `docs/related-work/citation-selection.md` (P3) says that FHIR PlanDefinition and CarePlan is "the standard representation the paper targets"; it must read as a partial mapping sketch, not as a target of the system. (d) BPMN4CP is cited by name with `[ref-needed: WS03]`; none of the standards of section 5.3 is cited.

**OP-T07-14 An undecidable instance raises no alert.** A PENDING instance after `pending_until_ms` with an `undecidable` marker (T05 section 3.5, CP6; TM-OP-15 of the threat model) has no alert path, because `Alert.verdict` admits only VIOLATED and PREDICTED_VIOLATION; how the nurse learns that an INT instance cannot be decided after its deadline (a robot that was away) is not defined. Related: ADR-029 (proposed), ADR-003 (the fallback to the nurse).

**OP-T07-15 Cascade fields.** The semantics of the links belongs to WS02-T04 (AH-10). Requirements stated here: inverse, acyclic, same kappa, violated alerts only, folding hides and does not delete, a re-issue when a link appears (section 1.8). FM distinguishes a fan-out from a chain (CAS-1); whether a fan-out member is a cascade effect is a decision of WS02-T04, and the example of section 1.8 follows analisi §4.9 item 3 and the plan scenario. *Downstream:* WS05-T07 tests 14 to 19.

**OP-T07-16 Rendering.** The text is a deterministic function of the alert (TR-4); the requirements are in section 3.4, the forbidden-term list is that of `01-conventions.md` section 7 and WS05-T07 test 23; comprehensibility is the vignette study (WS11). The example sentences are inputs to the claim audit, not final wording.

**Downstream task texts that this document contradicts or refines (files not edited).** The task text of WS01-T07 itself (line 40: "`sigma_norm` ... is the normalised forecast sigma-hat" and the range `[-1, 1]`; check 4); WS02-T04 (check 8 and step 5: provisional kappa); WS05-T07 (tests 20 and 25: provisional kappa; test 18: `update` and the refinement records; test 3: consistent, with the note that the rule of this document wins); WS05-T04 step 8 and WS05-T08 tests 5 and 15 (consistent with the bound); WS01-T08 rows R3, R4, R5 (consistent); EC D-1 and D-7 (consistent, with the unused vector of a predicted record); WS08 README E3 and E4 (attribution on matched pairs: a pair matched by a predicted alert, OP-T07-10).

**Suggested grouping of the ADRs for WS01-T08.** One ADR "Alert field semantics" for OP-T07-1, OP-T07-2, CP13, the lifecycle of section 1.4 and the metrics rule of OP-T07-10 (no signature change; the carrier fields of OP-T07-3 and OP-T07-6 go with the ADR of WS05-T04 step 8), and a wording clarification of the contract text for CP5, OP-T07-4 and OP-T07-12 (b).

**Touch points with earlier tasks (respected, not overridden).** T01 section 6.2 (wording rules) is section 2 here; T02 section 2.1 (margin and guard rule) gives the decisive sub-formula and the guard marker, section 5.4 the load checks, TG-1 the tick kinds; T03 section 5 is section 4 here; T04 sections 4.1, 4.3, 4.5 and 4.7 (fields read by `rank_alerts`, direction of priority, K1, frozen value), OP-5 (marker in the alert record: carried by the path), OP-6 (patient identifier), OP-10 (priority independent of kappa); T05 sections 3.7, 3.8, 4.2, 4.3, 5.3 and 6.5 (certified severity, episodes, transitions, sticky warning, targets, refinement records) are used as stated; T06 sections 1.2, 2.2, 2.3, 2.4 and 10 items 3, 5 and 6 are used as stated, with the field of item 5 decided as in section 1.5.
