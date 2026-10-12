---
id: WS08-T08
title: "Per-template metrics, equal-weight aggregate without RESP, false alarms outside injection windows (ADR-071 (b), ADR-072 (b))"
workstream: WS08-experiments
owner: agent
status: in_progress
depends_on: ["WS08-T01"]
critical_path: true
non_negotiable: false
estimate_pd: 2
sources: ["ADR-071", "ADR-072", "analisi §5.5"]
interfaces: ["02-interfaces.md#metrics"]
review_items: []
---
## Obiettivo

Add to `ralmon.eval` the metrics that ADR-071 (b) and ADR-072 (b) require: (1) every metric is available PER TEMPLATE; (2) the aggregate metrics are the mean over the templates with EQUAL weights, and RESP is reported apart and does NOT enter the aggregate; (3) the false-alarm figure is measured on WINDOWS WITHOUT INJECTIONS (outside every injection window and outside its causal consequences), the exposure being the patient-time outside such windows; natural truth events are truth, noise alarms (observed out of band while the latent value is in band) are false alarms; (4) the injected C1 subtypes are reported as the EXCESS over the background (the same metric on the same patients with the injection removed, or the natural rate in the windows without injections). `estimate_pd` is a rough planning figure, not a measurement.

## Contesto

- `docs/plan/03-decisions.md` ADR-071 (read (a), (b), (f)) and ADR-072 (read (b)); `docs/benchmark/evidence/fault-free-diagnostic.md` (the background, the noise alarms) and `evidence/benchmark-size-all-subtypes.md`.
- `src/ralmon/eval/metrics.py` and `runner.py` as WS08-T01 left them (read its Notes: matching per patient record, cluster bootstrap as the headline interval, the guards). The injection windows and their causal footprint: `InjectionRecord` and the sidecar `injection_log` of the benchmark (`docs/benchmark/builder.md`); for C2 and C3 the footprint is the window (use `t_rx` for a replay); for C1 it is the window plus the physiological tail (a stated, finite horizon: choose it from the generator's own pharmacokinetics and AR decay, record it as a parameter of the experiment config with its reason, not as a clinical value).
- The analyses of `docs/benchmark/evidence/nonadditivity.md` on footprints.

## File toccati

- `src/ralmon/eval/metrics.py` (modify: per-template breakdown, equal-weight aggregate, the background false-alarm metric, the excess metric).
- `src/ralmon/eval/runner.py` (modify: the metadata fields and the per-template outputs; the guards stay).
- `tests/eval/` (create `test_per_template.py`, `test_background_false_alarms.py`; modify the tests that pin the aggregate).
- `tests/fixtures/eval/` (modify: hand-written cases for windows with and without injections).
- `docs/benchmark/builder.md` (one paragraph on the footprint).

## Test

Write first; expected values hand-computed.

1. `test_metrics_are_available_per_template`: on the mini benchmark every template present in the truth has its own precision, recall, F1 and delay; a template with no truth event gives `null`, not zero.
2. `test_aggregate_is_the_equal_weight_mean_of_the_templates_without_resp`: with hand-made counts the aggregate recall is the plain mean of the per-template recalls of RANGE, SCHED, HOLD, COUNT, SYS, INT (the templates present); RESP is reported apart and its removal changes the aggregate by the amount computed by hand.
3. `test_false_alarms_are_counted_outside_injection_windows`: a detection inside an injection window (or its footprint) is not a background false alarm; the same detection outside is; the exposure is the patient-time outside the windows, computed by hand (a day with two windows of known length).
4. `test_natural_events_are_truth_and_noise_alarms_are_false_alarms`: a detection matched to a natural latent event is a true positive; an observed out-of-band reading with an in-band latent value that raises an alarm is a false alarm.
5. `test_excess_over_background`: for an injected subtype the reported rate is the difference between the rate with the injection and the background rate, with its bootstrap interval (cluster over patients); a subtype with no excess gives an interval that contains 0.
6. `test_resp_reported_apart_flag`: the metadata states that RESP is excluded from the aggregate and why (ADR-072).
7. `test_footprint_uses_t_rx_for_a_replay`.

## Passi

1. Tests first (red commit).
2. Footprint function (window plus stated tail) and the exposure.
3. Per-template breakdown and the equal-weight aggregate.
4. Background false alarms and the excess; metadata and guards.
5. Tell WS08-T02 (Notes) the output layout.

## Done when

- `pytest tests/eval -q` exits 0 and `pytest -q` exits 0.
- `ruff check src tests`, `ruff format --check src tests` and `mypy src/ralmon` exit 0.
- `python -m ralmon.eval.runner --config tests/fixtures/eval/smoke.yaml --output "$(mktemp -d)"` exits 0 and its `metrics.json` has the per-template and background fields.
- `python3 tools/check_plan.py` exits 0.

## Notes

### Worker notes (2026-10-12): what was built, judgment calls, hand-over to WS08-T02 and WS08-T09

Built: `src/ralmon/eval/background.py` (new: `Footprint`, `record_footprint`, `patient_footprints`, `PatientBackground`), additions to `metrics.py` (`TEMPLATES`, `AGGREGATE_TEMPLATES`, `template_of_event`, `template_table`, `table_template_metric`, `table_aggregate_metric`, `table_background_fa_per_day`, `excess_table`, `table_excess_*`) and to `runner.py` (`run_options.background`, the guard `C1_FOOTPRINT_TAIL_AWAITING`, the keys below). The geometry went into a new module instead of `metrics.py` (listed in "File toccati") because `metrics.py` was already 1000 lines and the geometry has no dependency on the matching. Tests: `tests/eval/test_per_template.py` and `test_background_false_alarms.py` (41 tests, red commit first). The only existing test changed is `test_metrics_json_top_level_keys` (the two new top-level keys are allowed). `docs/benchmark/builder.md` has the paragraph on the footprint; the WS08 README "metrics.json layout" has the new keys.

Output layout (for WS08-T02 and WS08-T09), all additive; the 11 metric names and `meta`/`analysis` are unchanged:

* `per_template.<det>` (null for a detector that did not run as a main instance): `templates.{RANGE,SCHED,HOLD,COUNT,SYS,INT}`, `resp`, `aggregate`. Template block: `n_events`, `n_matched`, `precision`, `recall`, `f1` (scalar leaves with `value`, `ci_*`, `ci_cluster_*`), `delay_ms.{n_matched, mean, fraction_early}`; a template with no truth event is `{n_events: 0, n_matched, precision: null, recall: null, f1: null, delay_ms: null}`. `aggregate`: `templates`, `templates_with_events`, `weights: "equal"`, `precision`, `recall`, `f1`, `delay_ms_mean`. The aggregate is the plain mean of the template values, recomputed in every bootstrap replicate over the templates that have an event in that replicate.
* `background.false_alarms_per_patient_day.<det>`: scalar leaf plus `n_false_alarms_background`, `n_false_alarms_in_footprint`, `exposure_patient_days`. `background.excess_over_background.<det>.<subtype>`: `template`, `events`, `detected`, `recall` (scalar leaves; `ci_cluster_*` is the headline interval) and `counts`.
* `meta.aggregate` (weights, templates, `excluded: ["RESP"]`, `excluded_reason` quoting ADR-072, the precision convention) and `meta.background` (rule, axis `t_rx`, tail value/status/reason, margin and its source). `meta.guards.facts.background_tail_awaiting`. `analysis.run.background`: records, footprints, exposure, events and natural events by template, per patient-day.
* WS08-T09: the per-template layout is `per_template.<det>.templates.<T>` and `.resp`; the attribution and set metrics per template can sit next to `precision/recall/f1` in the same block. I did not touch `#metrics` in `02-interfaces.md` (the new keys are runner outputs, not contract functions); if the text of `#metrics` 0.2.0 should list them, that is T09's. Set metrics are not implemented here.

Judgment calls (each reversible; none is a clinical value):

1. Template of a C2 event is SYS and of a C3 event INT. The ground truth carries no template for them (`template_id` None), and ADR-072 (b) and the test list name SYS and INT in the aggregate.
2. (SUPERSEDED by the fix round below.) Per-template precision is `TP_t / (TP_t + FA)` with FA the BACKGROUND false alarms (unmatched, outside every footprint) pooled over templates, as E3 pools them over classes, because B1 to B5 emit plain `Detection`s with no template; for an `Alert` the `tau` could attribute a false alarm to a template, which would make precision per template depend on the detector family, so I did not. It differs from `per_class_prf` precision, which still counts every unmatched detection and is untouched. An unmatched detection inside a footprint is in neither the background rate nor the precision (counted as `n_false_alarms_in_footprint`).
3. C1 tail: the repository has the PK decay (non-response and double take: 9.3 mmHg on day 0 to 1.8e-5 mmHg on day 7, nonadditivity.md) but any finite tail needs a threshold for "negligible", which is a decision, so `c1_footprint_tail_ms` is `awaiting_human_value` (absent = the same). Until a human sets it the footprint of a C1 record is its window only, the run carries the flag `C1_FOOTPRINT_TAIL_AWAITING` and a `headline: true` run is refused. `tests/fixtures/eval/smoke.yaml` carries a labelled test value (1 h), nothing else does. `experiments/main.yaml` (WS08-T02) must either set the tail with its reason or stay non-headline. The AR noise is never changed by an injection (own stream), so it adds no tail.
4. Margin: every footprint is widened by `footprint_margin_ms` (default the matching tolerance of the run) so that a detection within the tolerance of an injection, matched or not, is not background. Declared in `meta.background`.
5. Limit to report: for a point or per-tick C2/C3 fault (`end_ms` None: dispenser_bounce, nav_delay tick, stuck_at when anchored) the footprint is the instant plus the margin. nonadditivity.md used a generous test footprint (tick plus delay plus 2 h) for its additivity test; the task says "for C2 and C3 the footprint is the window", so I followed the task. A detection caused by such a fault but later than the margin counts as a background false alarm. If gab wants a longer footprint for those subtypes it is one more per-subtype parameter (awaiting value) in `run_options.background`.
6. (Headline figure SUPERSEDED by the fix round below: the excess is a count per injection record.) Excess: the repository has no "same patients with the injection removed" build (the `drop=` of F2 in nonadditivity.md is not implemented), so I used the second option of the task: the natural rate in the windows without injections. For an injected C1 subtype with a footprint, `events` is (events of its template with onset in the footprints of the subtype) per patient-day of footprint time, minus (events of the template with onset outside every footprint) per patient-day of time outside every footprint; `detected` is the same with the matched events; `recall` the difference of recalls. The template of the subtype is the template of the C1 truth events of that subtype in the test patients (not hard-coded); with none or several the block is `template: null`. Footprints of different subtypes may overlap, so the exposure inside the footprints of one subtype can include time that another subtype also covers. The intervals are bootstrap over patients of the whole difference.
7. Noise alarms are false alarms through the matching (an observed out-of-band reading with the latent value in band has no truth event, so its alarm is unmatched); they are NOT separated from other background false alarms. Separating them needs the latent reading at the detection instant and a rule for a detection that follows a reading with a delay; not done.
8. Footprints are read from the scored days only (the tail day's injection log is not used, but its ground truth is read for `explains_in_later_days` that point into it); the exposure is the patient-time of the scored days. The log windows are on the same continuing axis as the ground-truth events (the log and `record_to_ground_truth` take the same `realised_onset_ms`).
9. Bootstrap cost: each leaf calls `ci_with_report` twice (patient-day and cluster), about 40 leaves per detector; trivial on the mini benchmark, to be timed on the real one (n_bootstrap x units x 38 columns per leaf).

For WS08-T02: `experiments/main.yaml` needs a `run_options.background` block (tail with reason, or the awaiting value and a non-headline run) and should read the headline figures from `per_template.<det>.aggregate`, the background rate from `background.false_alarms_per_patient_day` and the C1 subtypes `hypertensive_spike` and `drug_nonresponse` from `background.excess_over_background`, not from the pooled `per_class_prf`. Report RESP from `per_template.<det>.resp` with the ADR-072 sentence from `meta.aggregate.excluded_reason`. The footprints read `truth_indices` and `explains_in_later_days` of the log when present (a log entry without them gives the window only); the builder writes both today.

### Fix round after the independent review (2026-10-12): what changed, limits, hand-over

Supersedes judgment calls 2 and 6 and the layout lines above where they differ. Tests first (red commit), then the code.

* **I1 (aggregate rule).** ONE rule: for a template WITH events, recall, precision and F1 are 0 when it has no true positive (never NaN, never dropped; also when the detector emitted nothing for it). Only the delay is undefined without a match. Every aggregate leaf carries `templates_averaged` (the exact list): recall, precision and F1 average the templates with events (RESP excluded), the delay the templates with at least one match. The reviewer's scenario is a test (`test_aggregate_f1_averages_every_template_with_events_and_one_false_alarm_does_not_swing_it`: RANGE 5 of 10, the other five templates with events and none matched: aggregate F1 1/9, not 2/3; one RANGE false alarm gives 5/48, a factor 0.9375). The rule is stated in `meta.aggregate.average_rule` and `precision_rule`. In a bootstrap replicate a template with no event in the resample is left out of that replicate (the point value uses the full list).
* **I2 (precision).** Per-template `precision` and `f1` exist only for a detector whose detections carry a template: `TP_t / (TP_t + FA_t)`, `FA_t` the unmatched alerts of template `Alert.tau` outside every footprint. A detector is `templated` when it is the proposed method (`OursDetector`) or when every detection it emitted is an `Alert`; B1 to B5 emit plain `Detection`s (checked in `src/ralmon/baselines`: every `Detection(...)` has `label=None` and no template), so for them `precision`, `f1` and the aggregate precision and F1 are `null`; aggregate recall and delay exist for all. The old pooled figure is renamed `precision_pooled_fa` (pooled false alarms over all templates, true positives anywhere including inside footprints, false alarms only outside): it depends on the number of events of the template, is present for every detector, and does not enter any aggregate. Open: a templated detector that emitted no detection at all and is not `OursDetector` is read as not templated.
* **I3 (excess).** Headline: `events_per_record` and `detected_per_record` = (events in the footprints - background rate x exposure in the footprints) / injection records of the subtype (a linked span of an explained event is not a record); `recall` (inside minus outside) kept; `events_per_patient_day` and `detected_per_patient_day` kept as secondary and flagged as dependent on the footprint tail and margin (`note`). The counterfactual is the natural rate in the windows without injections, which ignores the time-of-day structure (natural RANGE and HOLD events cluster near the dosing times): fair only if the injection windows are placed like the rest of the day (in `meta.background.excess_counterfactual_note` and `builder.md`).
* **I4 (class proxies).** SYS means the C2 events and INT the C3 events, not the violations of the SYS and INT templates: `meta.aggregate.class_proxies` and `class_proxy_note`, `class_proxy: true` in the SYS and INT blocks, the README layout.
* **M1.** An event whose onset is at or beyond the end of the scored axis (`n_days * D`, for example the day-end COUNT of the last day) is in neither the in-footprint nor the background count of the excess, so the counts match the exposure. **M2.** The template of an excess subtype comes from the static `LINK_TABLE` of the labeller (hypertensive_spike RANGE, drug_nonresponse RESP, hypotension_below_hold HOLD, measurement_refusal SCHED, double_take COUNT), not from the truth events present; a subtype outside the table gets `template: null`. **M3.** The runner uses the named columns (`excess_counts`) and `T_DAY_MS` instead of positions and a literal. **M7.** Only the cluster intervals `ci_cluster_*` of the excess are usable (`meta.background.excess_interval_note`).
* **M6 (decision for gab).** Deferring `c1_footprint_tail_ms` as `awaiting_human_value` deviates from the task text ("choose it from the generator's own pharmacokinetics and AR decay"): the PK decay never reaches zero, so any finite tail needs a threshold for a negligible residual effect, which I judged a decision and not a derivation. It needs gab's sign-off (either a value with its reason, for example the residual effect in mmHg that is negligible, converted through the decay of the committed prior, or an explicit acceptance of window-only footprints). `experiments/main.yaml` (WS08-T02) cannot be a `headline: true` run until it is set: the guard `C1_FOOTPRINT_TAIL_AWAITING` is a hard failure there.
* **Limits to report (add to judgment call 5).** (a) A point or per-tick C2/C3 fault has the instant plus the margin as footprint. (b) M4: a detector with a long memory (a recursive filter, a rolling window, an anomaly score over a long context) that alarms after a fault window by more than the margin counts those alarms as BACKGROUND false alarms, which penalises it for the consequences of an injection; the margin is a parameter of the experiment. (c) The excess counterfactual ignores time of day. (d) The background rate of an excess subtype is estimated from the same test patients, outside every footprint of any subtype.
* **Hand-over.** Layout changes since the first report: block keys `precision` (null unless `templated`), `precision_pooled_fa`, `class_proxy`; `per_template.<det>.templated`; aggregate leaves with `templates_averaged` and null `precision`/`f1` for plain detectors; excess keys `events_per_record`, `detected_per_record`, `recall`, `events_per_patient_day`, `detected_per_patient_day`, `counts.n_injection_records`, `note`. WS08-T09 can put its attribution metrics per template next to `recall` in the same block; WS08-T02 (see its Notes) reads the headline from `per_template.<det>.aggregate` and, for precision and F1, only for `ours`.
