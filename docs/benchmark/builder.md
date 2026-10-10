# The benchmark builder: files, manifest fields, reader and command line

Document of WS04-T11 (`src/ralmon/benchmark/builder.py`, `__main__.py`, `configs/benchmark/default.yaml`). It states what a
built benchmark directory contains, which fields of `manifest.json` the experiments read, and the rules that are not in
the contract text. The benchmark is semi-synthetic and pre-clinical: no real patient, and nothing here is a clinical
claim. The numbers of the default configuration (split fractions, seed, monitor step, injection rates, pairs per
variant) are design choices without a source, awaiting the confirmation H3; ADR-067 (proposed) records them.

## Directory layout

```
<dir>/manifest.json
<dir>/days/<patient_id>/<day_index>.json       ObservedDay only (what a monitor or a baseline reads)
<dir>/truth/<patient_id>/<day_index>.json      latent day, ground truth, injection_log, behaviour_log
<dir>/plans/<care_plan_id>.json                CarePlan of the whole record of a patient
<dir>/generator/<patient_id>/<day_index>.json  latent baseline pressure (generator sidecar)
```

All files are canonical JSON (sorted keys, two-space indent, final newline). The manifest lists every file with its
sha256, so `python -m ralmon.benchmark verify <dir>` is a complete integrity check. A detector run reads `days/` and
`plans/` only. `generator/` holds `baseline_sbp_mmhg`, the latent pressure before the drug effect and the injected
pulses, on the latent grid of the day (`latent_step_ms`): the validation report (V3, prior fidelity) re-estimates the
patient parameters from it, because the latent `bp` of the truth file carries the drug and the pulses.

## The tail day (ADR-066)

Every patient has `n_days + 1` days: the scored days `0 .. n_days - 1` and one unscored tail day `n_days`, generated with
the same machinery (latent day, injections, observed day, robot reports) and labelled with the history of the scored days.
It exists because the closing step of the last scored day is the first step of the tail day, and by ADR-064 (b) a record
decided at the shared step belongs to the day that starts there.

* `manifest.patients[<id>].n_scored_days` and `tail_day_index` (equal to `n_scored_days`) mark it; `settings.tail_day` is
  `true` and `settings.n_scored_days` is the number of scored days of a virtual patient.
* The tail day is in no split count, in no day total (`settings.n_patient_days` counts the scored days of all patients, the
  twins included) and not in `event_counts`; `BenchmarkReader.days(patient)` lists the scored days only.
* The truth of the closing step of the last scored day is `BenchmarkReader.closing_step_truth(patient)`: the C1 events of the
  tail day that are decided at its first step (the C2 and C3 events of that day are injected events of the tail day and are not part of it), that is whose `end_ms` is the start of the tail day (a windowed
  obligation whose deadline is the closing step, for example the response window of a dose at 21:00 that closes at 24:00),
  or, for an event without `end_ms`, whose `onset_ms` is that instant. Every other event of the tail day is not scored,
  and neither the monitor nor a baseline is run on it. `settings.tail_event_counts` and `settings.closing_step_event_counts`
  count the events of the tail days and the part of them decided at the first step.
* A detection that a method emits at the closing step of the last scored day is scored against these events, with the same
  rule as every closing step (a detection at the closing step of day d-1 is scored against day d).

## Manifest fields

`generator_git_rev` (the command line reads `git rev-parse HEAD`, with `-dirty` when the tree has changes; the library
takes it as an argument), `generation_seed`, `prior_source_name`, `prior_provenance`, `fixture_only`, `n_unfilled` (always 0:
a build with an unfilled prior or design row is refused), `n_unverified` (rows without `verified_by`: the prior and the
design files), `files`, `event_counts` (scored days, key `<class>/<subtype>`), and:

* `patients[<id>]`: `split` (the reference split, `train`, `calibration` or `test`), `cohort`, `role` (`patient` or
  `confounder_pair`), `n_scored_days`, `tail_day_index`, `care_plan_id`, `patient_index`; a twin also has `pair`, `member`
  (`A` the C1 mechanism, `B` the C2 or C3 one), `group`, `variant_id` and `mechanism`.
* `settings`: `latent_measurement_mode`, `latent_step_ms` (the step of the monitor configuration of the labeller),
  `monitor` (`step_ms`, `reorder_delay_ms`), `jitter_source`, `segment_source`, `disabled_subtypes` (subtypes that an
  injector could not run, for example `ecg_noise` without a noise segment), `numpy_version`, `python_version`,
  `registry_version`, `registry_sha256`, `registry_fixture_only`, `device_profile` (ADR-036: `dispenser_content_sensing`,
  `authenticating_devices`), `design_sha256` (the care-plan, generator-design and injection files), `history_days`,
  `injection_rates`, `confounder_pairs_per_variant`, `plan_skipped` (injections that the plan drew and could not place:
  overlap, no position, a replay on the first day), `schedule`, `cohorts`, `split_fractions`, `n_unverified_prior`,
  `n_unverified_design`. There is no clock, host or user field.

## Truth sidecars

`injection_log` has one entry per injection record of the day, in the order of the records, with the keys of
`ralmon.benchmark.injection.injection_log` and, for a twin, `variant_id` and `indistinguishable_by_construction` (the
flag computed from the two observed days, not the expectation of the YAML grid), plus:

* `record_index`: the position of the record in the list;
* `truth_indices`: the positions in the `ground_truth` of the same day of the events that the record explains or produced;
* `explains_in_later_days`: `{day_index, truth_index}` for each event of a later day that the record explains. An event of
  day d explained by a record of day d-1 (the morning COUNT event after an evening `double_take`, a RESP event after an
  evening `drug_nonresponse`) is `injected` and is in no `truth_indices` of day d: the record is found by this list.

## Robot reports

Each visit of the robot produces a `NODE_STATE` event of the source `robot` with `payload.state` `active` and
`payload.colocated` (a bool): `true` at the arrival of every visit (the first of the day included, at the instant of the
presence sample) and `false` where no other visit keeps the robot in the room. WS05-T11 turns them into the availability of
`presence` and `intake` (ADR-054 (b)); the gate `presence_samples_without_availability_marks == 0` holds on every built day
(test `test_every_robot_visit_has_an_arrival_report_and_the_gate_is_zero`). A twin whose variant has no robot has no robot
report and no presence sample.

## Care plans

`plans/<care_plan_id>.json` is the plan of the whole record of a patient (scored days and tail day, anchors on the
continuing axis `day_index * T_day + clock time`): a SCHED instance for every measurement tick, the day-end COUNT of every day,
and one parameter record each for RANGE, HOLD and COUNT (`anchor_ms` null, the values of the registry), so that the baseline B1
runs its four rules (`rules_active == ("R1", "R2", "R3", "R4")`). `registry_version` is the registry in use; the plan is unsigned.

## Reader

```python
from ralmon.benchmark import open_benchmark
reader = open_benchmark("<dir>", verify=False)
reader.patient_ids(split="test", role="patient", cohort=None)
reader.days(patient), reader.tail_day(patient)
reader.observed(patient, day)            # never reads truth/
reader.truth(patient, day)               # TruthUnavailableError without a truth directory
reader.benchmark_day(patient, day)
reader.closing_step_truth(patient)
reader.baseline_sbp(patient, day)
reader.care_plan(observed_day.care_plan_id)
```

`ralmon.benchmark.split_patients(ids, fractions, seed)` is the split helper: largest-remainder sizes, deterministic for a
seed and independent of the order of `ids`. WS08 re-draws the split per experiment seed with it.

## Command line

`python -m ralmon.benchmark build --config PATH --out DIR [--seed N] [--prior PATH] [--allow-fixture-only] [--git-rev REV]
[--n-patients N] [--n-days N]`, `verify DIR`, `validate DIR` (placeholder until WS04-T12; it exits 2). Exit codes: 0 done,
1 `verify` found a problem, 2 configuration error, 3 provenance error (a fixture-only input without the flag, an unfilled
row). The committed configuration cannot be built until a human has filled the rows that `injections.yaml` and
`generator_design.yaml` still await (`n_unfilled` must be 0): the command stops with exit code 3 and names them.

## What the build does not claim

An injection that finds nothing to change (a cuff fault in a window with no reading, a replay of a day without messages) is
logged with `realised` false and is not a ground-truth event; the realisation rate per subtype is reported by WS04-T12.
Injections that the plan cannot place are counted in `settings.plan_skipped`. The uniform choice of the subtype and of the
level inside a class, and the Poisson count, are design choices of the plan (`plan:` section of `injections.yaml`), not
properties of any real population.
