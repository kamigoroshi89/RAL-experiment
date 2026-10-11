---
id: WS08-T08
title: "Per-template metrics, equal-weight aggregate without RESP, false alarms outside injection windows (ADR-071 (b), ADR-072 (b))"
workstream: WS08-experiments
owner: agent
status: ready
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
