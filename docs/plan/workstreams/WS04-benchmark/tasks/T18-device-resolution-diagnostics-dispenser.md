---
id: WS04-T18
title: "Generator: cuff resolution (rounding), driver diagnostics reports under two device profiles, dispenser interval, ADR-040 conventions (ADR-074)"
workstream: WS04-benchmark
owner: agent
status: blocked
depends_on: ["WS05-T13", "WS04-T16"]
critical_path: true
non_negotiable: false
estimate_pd: 3
sources: ["ADR-032", "ADR-040", "ADR-074"]
interfaces: ["02-interfaces.md#trace-schema", "02-interfaces.md#evidencevector"]
review_items: []
---
## Obiettivo

Make the generator emit what the evidence fields of `#evidencevector` 0.2.0 read, under declared device profiles. (1) Round the cuff readings (`bp` and the cuff `hr_pulse`) at the device boundary to the device resolution, a device-profile parameter with default 1 mmHg / 1 bpm; the resolution is also what the extractor's `cuff_value_repeated` assumes (prototype: natural repeat probability 0.0197 for the generator's noise, 0 without rounding; this is a property of the generator, not of a real cuff). (2) `NODE_STATE` `diagnostics` reports of the device driver under the liveness contract of `docs/models/evidence-channels.md` ("Bridge node: liveness contract"): `ok` at start and each driver period for every device with the capability; an idle on-demand device never reports `stale`; `stale` only after the lease with an open session or a continuous device; the profile 'driver with diagnostics' and the profile 'without' are two named profiles in the manifest. `stale_lease_ms` and the driver period are profile parameters without default (`awaiting_human_value`); a run with the profile 'driver with diagnostics' and an unset lease fails loudly. (3) `DISPENSE` payload `interval_since_previous_ms` (the generator emits none today) and `content_change` before minus after, release positive, bounce zero (ADR-040 (2)); the informed attacker's forged dispense copies the bounce timing as in the pair prototype. (4) ADR-040 (3): the builder (WS04-T11) writes `colocated` True/False for the robot visits in variants with the robot, none otherwise; verify and fix. (5) Goldens move: list every file that changes and why.

## Contesto

`docs/benchmark/evidence/likelihood-attribution.md` sections 9 and 10 and `docs/benchmark/evidence/scripts/likelihood/` (the research copy with the switch `RALMON_DRIVER_DIAG`, the rounding at the device boundary, and the pair variants), `docs/benchmark/evidence/pairs-allocation.md`, ADR-032, 040, 074, `src/ralmon/benchmark/{measurement,base,inject_c2,inject_c3,confounders,builder}.py`.

## File toccati

`src/ralmon/benchmark/measurement.py`, `base.py`, `inject_c3.py`, `builder.py`, `configs/benchmark/generator_design.yaml` (profile rows as `awaiting_human_value` where no value exists), `docs/benchmark/builder.md`, `tests/benchmark/**`, the golden files that move.

## Test

1. `test_cuff_readings_are_multiples_of_the_resolution` (default 1; resolution 5 gives multiples of 5).
2. `test_fault_free_repeat_rate_matches_the_rounding_formula` (seeded; within the binomial interval of the analytic value).
3. `test_idle_cuff_never_reports_stale_over_24h`.
4. `test_open_session_with_stopped_publisher_goes_stale_after_the_lease`.
5. `test_profile_without_diagnostics_emits_no_diagnostics_report`.
6. `test_unset_lease_with_diagnostics_profile_fails_loudly`.
7. `test_dispense_payload_has_interval_and_signed_content_change`.
8. `test_bounce_has_content_change_zero_and_release_positive`.
9. `test_colocated_events_follow_the_robot_visits`.
10. `test_rounding_does_not_change_ground_truth` (latent trace and truth unchanged; observed readings are the rounded ones).

## Passi

1. Tests first. 2. Rounding. 3. Diagnostics reports and profiles. 4. Dispenser payload. 5. `colocated`. 6. Regenerate goldens and list them.

## Done when

`pytest -q`, `ruff check src tests`, `ruff format --check src tests`, `mypy src/ralmon` exit 0; `python3 tools/check_plan.py` exits 0.

## Notes

### Hand-over from WS05-T13 (`#evidencevector` 0.2.0, 2026-10-11)

- The `dispenser_bounce` sidecar declares the paths `dispenser.interval_since_previous_ms` and `dispenser.content_change`, and `stuck_at` declares `signal_quality.cuff_value_repeated`. The declaration is conditional by design (the fault-model union of raised and conditional fields). The generator does not raise `interval_since_previous_ms` until this task emits the key, so a sidecar generated before this task declares a path that the trace cannot show; benchmarks generated before WS05-T13 also carry the old empty signatures and `seq_gap_or_replay` and must be regenerated.
- The cuff resolution parameter that the generator rounds to must be the same value that the run's `DeviceProfile` gives the extractor as `cuff_resolution`; nothing else couples them, and a profile without it makes `cuff_value_repeated` `None`.
- Emit `interval_since_previous_ms` as an `int` >= 0, omit it for the first opening of a stream and across midnight, and keep `content_change` before minus after (+1.0 for a release, 0.0 for a bounce). Give each DISPENSE its own `seq`: a re-sent copy with the same `seq` is skipped by the extractor.
