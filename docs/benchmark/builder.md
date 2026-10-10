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
sha256, so `python -m ralmon.benchmark verify <dir>` is a complete integrity check: it checks the hashes, refuses a file on
disk that the manifest does not list, parses every observed file as an `ObservedDay` (an unknown key or an undeclared payload
key is an error, so it reads the whole `days/` tree) and refuses an observed file that names latent data, ground truth or the
injection vocabulary (record fields, subtype names, template ids, the prefix `spontaneous_`). A detector run reads `days/` and
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
* The tail day is in no split count, in no day total (`settings.n_patient_days` counts the scored days of the virtual
  patients; the twins' are `n_twin_patient_days`) and not in `event_counts`; `BenchmarkReader.days(patient)` lists the scored days only.
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
  `injection_rates`, `confounder_pairs_per_variant`, `excluded_zero_levels` (per cohort and subtype, the magnitude levels
  the plan does not draw because they resolve to zero, see below), `plan_skipped` (injections that the plan drew and could not place:
  overlap, no position, a replay on the first day), `schedule`, `cohorts`, `split_fractions`, `n_unverified_prior`,
  `n_unverified_design`, `prior_sha256` (per cohort) and, in `design_sha256`, the hash of the configuration file besides the
  care-plan, generator-design and injection files. There is no clock, host or user field. `python_version` and
  `numpy_version` are host properties: the manifest bytes depend on the machine that built it while the day, truth,
  plan and generator files do not (compare the files, not the manifest, across machines). A configuration file that
  lives in another directory has other paths and so another hash.

## Virtual patients and twins are counted apart

The headline figures are the virtual patients' (`role: patient`): `event_counts`, `settings.n_patients`,
`n_patient_days`, `tail_event_counts`, `closing_step_event_counts`, and the first lines of the command-line output. The
twins (`role: confounder_pair`, one scored day each) have their own fields: `n_twin_patients`, `n_twin_patient_days`,
`twin_event_counts`, `twin_tail_event_counts`, `twin_closing_step_event_counts`; `total_event_counts` is the explicit
sum. `BenchmarkReader.n_patient_days(role="patient")` defaults to the virtual patients (`role=None`: all). The twin
patients are not counted in the 200 x 7 patient-days of analisi §5.1.

## Opaque ids

A patient id has the shape `p0042` for a virtual patient and for a twin alike (with the cohort id in front when there are
several cohorts). The id numbers of all patients are one permutation drawn from the generation seed, so an id, a care-plan
id (`plan-<id>`), a directory or a file name says nothing about the role, and member A of a pair is the lower id in about
half of the pairs. `pair`, `member`, `group`, `variant_id` and `mechanism` are in the manifest and the truth side only;
the manifest is not a detector input. Test `test_twin_ids_carry_no_role_and_have_the_shape_of_a_virtual_id` scans the
observed side of a build for them.

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

`open_benchmark(path, view="observed")` is the view that the monitor, the baselines and any code that fits or runs a
detector must be given: it offers only the observed days, the care plans, the day lists and the split (`patients` maps an id
to `split` and `cohort`), and raises `ObservedViewError` on `truth`, `benchmark_day`, `closing_step_truth`,
`baseline_sbp`, `manifest`, `root` and the role filters. `view="full"` (the default) is for evaluation code. The generator
sidecar is refused in the full view too once the `truth/` directory is gone.

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
row). A build that fails removes the directory it created (never a pre-existing one; a pre-existing empty directory is emptied).
The revision is dirty (`-dirty`) when a tracked file has changes or an untracked file lies under `src/` or `configs/`; untracked
files elsewhere do not count. The committed configuration cannot be built until a human has filled the rows that `injections.yaml` and
`generator_design.yaml` still await (`n_unfilled` must be 0): the command stops with exit code 3 and names them.

## What the build does not claim

An injection that finds nothing to change (a cuff fault in a window with no reading, a replay of a day without messages) is
logged with `realised` false and is not a ground-truth event; the realisation rate per subtype is reported by WS04-T12.
Injections that the plan cannot place are counted in `settings.plan_skipped`. The uniform choice of the subtype and of the
level inside a class, and the Poisson count, are design choices of the plan (`plan:` section of `injections.yaml`), not
properties of any real population.

A level whose resolved magnitude is exactly zero is not drawn (fixed after the observability analysis, 2026-10-10). The
magnitude block of `cuff_silent_bias` has the levels `low`, `medium`, `high` and `device_bias`, and `device_bias` is the
multiplier 1.0 of the prior `cuff_bias_mmhg`; for an accurate device that prior is 0.0 mmHg, so the injected shift is zero,
the injector changes nothing and the injection is never realised, in one draw out of four. The plan therefore draws
uniformly among the levels of a cohort whose resolved magnitude is not zero (`drawable_magnitude_levels`, which uses
`resolve_magnitude`) and lists the others in `settings.excluded_zero_levels`. The level is not removed from the design: with a
non-zero `cuff_bias_mmhg` it is drawn again, and its sign rule (no random sign) is unchanged. A block in which every level
resolves to zero is a configuration error.

## Open decisions for gab (ADR-067)

* **Realised injections.** Windows are placed uniformly over the day, while cuff readings are 5 a day and intakes 2 a day, so
  few windows hit anything. Reviewer's figures on a 40-patient, 7-day fixture build at rates 1/1/1, realised over planned:
  cuff_detached 5/45, cuff_silent_bias 3/48, stuck_at 4/52, injection_naive 6/56, injection_informed 5/61, replay 4/31,
  ecg_noise 0/55 (the fixture library has no noise segment), drug_nonresponse 0/50 (windows with no intake in them). At the
  default rates 0.3/0.3/0.2 about 5 to 10 realised positives per cuff subtype and 0 to 4 for drug_nonresponse are expected.
  Placement was not changed; an option is to place C1 and cuff windows on a known tick or intake. WS04-T12 reports the
  realised fraction per subtype.
* **Closing-step truth is C1 only.** A C2 or C3 event that starts exactly at the first instant of the tail day (about 0.1
  expected at the default scale) is not part of `closing_step_truth`, so a detection of it at the closing step of the last
  scored day would be scored as a false positive unless WS08 scores closing-step detections against C1 only or states the limit.
* **Twins in headline counts, split design of the pair units** (stratify them over the splits, or keep them out of train and
  calibration; the fractions are targets for the units that are split), **the 65 awaiting rows** (2 in the prior, 8 in
  `generator_design.yaml`, 55 in `injections.yaml`) and **the confirmation of the design values** (0.5/0.25/0.25, seed 0,
  60000 ms, reorder delay 0, rates 0.3/0.3/0.2, 2 pairs per variant).
