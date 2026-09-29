---
id: WS11-T02
title: Vignette generation, natural-language alerts, answer key draft
workstream: WS11-vignettes
owner: agent
status: blocked
depends_on: ["WS11-T01", "WS05-T07", "WS04-T11", "WS06-T02", "WS06-T03"]
critical_path: false
non_negotiable: false
estimate_pd: 3
sources: ["analisi §5.7"]
interfaces: ["02-interfaces.md#alert", "02-interfaces.md#trace-schema"]
review_items: ["R3-W6"]
---
## Obiettivo

OPTIONAL: first item in the cut order (`docs/plan/00-master-plan.md` section 7). Build, from benchmark events and the real monitoring and attribution pipeline, the vignette families defined in `study/protocol.yaml`: each family is one benchmark event rendered in three conditions (`THR` threshold alarm, `ANOM` anomaly score, `RSM` alert), plus practice families, the divergence block and, if `protocol.yaml` includes it, the urgency-ranking set (one set of RSM alerts that participants order by urgency, analisi §5.5). The `RSM` rendering uses the natural-language text produced by the attribution package of WS05-T07 without rewriting it. Concrete outputs: `study/build_vignettes.py`, the participant-facing bundle `study/vignettes/` (with manifest and a pilot pack), and `study/answer-key-draft.yaml`, a draft key that the clinician validates in WS11-T03.

## Contesto

- `study/` : `design.md` and `protocol.yaml` from WS11-T01 (families, conditions, display rules, divergence rule, action vocabulary, scoring classes). This task implements them and does not change them.
- `docs/plan/02-interfaces.md` sections `#alert` (fields of `Alert`, `Explanation.text`, `Detection`) and `#trace-schema` (`BenchmarkDay`, `ObservedDay`, `LatentDay`, `GroundTruthEvent`; the monitor never sees latent data or ground truth).
- `docs/plan/workstreams/WS05-monitor/tasks/T07-attribution-package.md` (how to turn an `ObservedDay` into `Alert` objects and where the natural-language text comes from; record the exact call chain used in the completion note).
- `docs/plan/workstreams/WS04-benchmark/tasks/T11-benchmark-builder.md` (how a benchmark version and its manifest are built and read).
- `docs/source/analisi.md` §4.5 (diagnosability matrix), §5.1 items 3 and 4 (injections, confounders), §5.7.

Precondition not captured by `depends_on`: `ralmon.baselines` must export `B1StaticThresholds` and `B2AnomalyDetection` (WS06-T02, WS06-T03), which provide the `THR` and `ANOM` renderings. If they are not done when this task starts, stop and report the gap; do not write stand-in detectors.

Unblocked when WS11-T01, WS05-T07 and WS04-T11 are `done` and a benchmark version exists on disk.

## File toccati

- `study/build_vignettes.py` (create)
- `study/vignettes/` (create; generated: one JSON file per family, `manifest.json`, `pilot-pack.md`)
- `study/answer-key-draft.yaml` (create)
- `tests/study/test_vignettes.py` (create)
- `tests/study/fixtures/` (create; hand-written `Alert`, `ObservedDay`, `LatentDay` and registry fixtures)
- `tests/study/conftest.py` (create; puts the repository root on `sys.path` so that tests import the scripts under `study/`; WS11-T04 and T06 reuse it)

## Test

Written first and run to fail (import error is an acceptable first failure). Fixture values are arbitrary test data, not clinical values. Tests import only names from the package public API (`02-interfaces.md#package-public-api`).

- `test_three_renderings_share_source_event`: for every family in a fixture build, the `THR`, `ANOM` and `RSM` renderings carry the same `patient_id`, `day_index` and `onset_ms`, and their context blocks are byte-identical.
- `test_rsm_text_is_verbatim_from_attribution_package`: the `RSM` panel text equals `Alert.xi.text` of a hand-written fixture alert; the builder contains no second natural-language renderer (a fixture alert with an unusual sentence must come out unchanged).
- `test_rsm_panel_shows_only_the_tuple_fields`: the `RSM` panel keys are exactly {template, cause label, severity, confidence, text, priority} for the fixture, where severity is σ̃ and confidence is ρ as displayed by the rule in `protocol.yaml`.
- `test_thr_panel_has_no_severity_confidence_or_cause`: the `THR` panel contains none of the `RSM` panel keys and none of the plain-language cause labels; it contains the signal, the observed value, and the limit read from the registry fixture.
- `test_anom_panel_shows_score_and_signal_only`: the `ANOM` panel contains the detection score (and the detector cut-off if the fixture detector has one), the signal name and the time; nothing else.
- `test_context_uses_only_observed_samples_before_alert_time`: a fixture `ObservedDay` with one sample whose `t_rx_ms` is after the alert time produces a context without it.
- `test_context_is_observed_not_latent`: a fixture `BenchmarkDay` whose latent value differs from the observed value at the same instant produces a context with the observed value only.
- `test_participant_bundle_has_no_key_or_ground_truth`: a recursive walk over every JSON file in the bundle finds none of the keys `ground_truth`, `subtype`, `injected`, `confounder_group`, `latent`, `expected_action`, `scoring`.
- `test_divergence_cells_median_split`: for the alerts (σ̃, ρ) = (-0.9, 0.95), (-0.8, 0.30), (-0.2, 0.90), (-0.1, 0.25) the median σ̃ is -0.5 and the median ρ is 0.60, so the cells are (high severity, high confidence), (high severity, low confidence), (low severity, high confidence), (low severity, low confidence) in that order. If WS11-T01 chose another rule, recompute the expected cells by hand for that rule.
- `test_constructed_alerts_are_flagged`: a family built from an alert that a fixture pipeline produced has `constructed: false` in the manifest; a family built by calling `normalise` and `Rho` on controlled inputs (used only when a divergence cell is empty in the benchmark alerts) has `constructed: true`.
- `test_selection_is_seeded_and_logged`: two builds with the same integer seed choose the same events; the manifest lists every rejected candidate with its reason; a different seed may choose differently.
- `test_key_draft_entries_are_unreviewed`: every family entry of `answer-key-draft.yaml` has `status: draft` and `reviewed_by: null` (the `ranking` entry carries only `system_order`); the expected action id is in the family's option list; every option id is in the generic vocabulary of `protocol.yaml` (so no drug or dose action appears); each family offers every scoring class that `protocol.yaml` requires.
- `test_key_is_independent_of_condition`: the key has one entry per family, with no condition field.
- `test_ranking_set_system_order_equals_rank_alerts`: for a fixture set of three alerts of equal priority with σ̃ = -0.2, -0.9, -0.5, the system order stored in the draft key is the alert with -0.9, then -0.5, then -0.2 (`rank_alerts`, lexicographic by priority then σ̃ ascending), computed by hand.
- `test_ranking_set_hides_system_order`: the participant bundle lists the ranking items in a seeded shuffled order that differs from the system order for the fixture, and the system order appears only in `answer-key-draft.yaml` under `ranking`.
- `test_bundle_is_reproducible`: building twice into two temporary directories gives byte-identical files.
- `test_pilot_pack_has_no_key`: `pilot-pack.md` contains none of the expected action ids or rationales of the draft key.

## Passi

1. Read `study/design.md` and `study/protocol.yaml`, the WS05-T07 and WS04-T11 task files and their completion notes. Confirm the precondition on B1 and B2; if it fails, stop.
2. Write the fixtures under `tests/study/fixtures/` by hand and the tests listed above; run `pytest tests/study -q` and watch every test fail.
3. Implement candidate selection: for each family in `protocol.yaml`, list the benchmark events of the required ground-truth subtype in the benchmark version named in the manifest; draw candidates in a seeded order (explicit integer seed, `numpy.random.Generator`); accept the first candidate that passes the eligibility checks of the family (the pipeline produced an alert of the intended type; no unrelated simultaneous alert unless the family requires it); log every rejection with its reason. Never choose an event by looking at how it renders.
4. Implement the pipeline call: run the monitor and the attribution package on the chosen `ObservedDay` through the public API; run B1 and B2 on the same day to get the `Detection` for `THR` and `ANOM`. Build the `RSM` panel from the resulting `Alert` (text from `Alert.xi.text`, unchanged); build the `THR` and `ANOM` panels by the display rules of `protocol.yaml`. Read band limits from the parameter registry through `ralmon.spec`, never as literals.
5. Build the shared context block from observed samples and the `CarePlan` only, up to the alert time. Build the divergence block: instantiate the cut-offs from the distribution of σ̃ and ρ over the benchmark alerts of the calibration split, write them to the manifest, assign each block alert to its cell; if a cell is empty in the benchmark alerts, construct the alert with `normalise` and `Rho` from controlled inputs and flag it `constructed: true`.
6. Write the draft key. For each family list the option catalogue (ids from the generic vocabulary) with a scoring class per option and a one-line rationale that cites its basis (the diagnosability row of analisi §4.5, the clinician-in-the-loop principle of analisi §4.9 item 4, or the care-plan template). The key is a property of the event, not of the rendering: it must score the same action identically in all three conditions, including families where the RSM attribution is misleading. Every entry is `status: draft`, `reviewed_by: null`. This is a proposal, not an expert key.
7. If `protocol.yaml` includes the ranking set, build it from benchmark alerts (real pipeline output, same selection and logging rules as for families), render each item as an `RSM` panel, compute the system order with `rank_alerts` from `ralmon.spec` and store it only in the draft key, and shuffle the item order in the bundle with the seed.
8. Write `manifest.json` (benchmark manifest path and version, `seed`, `families`, selection log, cut-offs, `constructed` flags, generator git revision, family to set assignment from `protocol.yaml`) and `pilot-pack.md` (participant-facing walk-through of all families in all three renderings, no key).
9. Run `pytest tests/study -q` until green, then `ruff check study tests`; refactor. Commit on branch `ws11-t02-vignette-generation` with `WS11-T02: generate vignette families and draft key`; set `status: done`. In the completion note give the command output and the call chain used from `ObservedDay` to `Alert`.

## Done when

From the repository root, each exits 0:

- `pytest tests/study -q`
- `ruff check study tests`
- `test -f study/vignettes/manifest.json && test -f study/vignettes/pilot-pack.md && test -f study/answer-key-draft.yaml`
- `python3 -c "import json; m=json.load(open('study/vignettes/manifest.json')); assert m['seed'] is not None and m['families']"`
- `grep -c 'status: draft' study/answer-key-draft.yaml` prints the number of scored families in `study/protocol.yaml` (rotating families plus divergence block families; practice families are not scored and have no key entry).
