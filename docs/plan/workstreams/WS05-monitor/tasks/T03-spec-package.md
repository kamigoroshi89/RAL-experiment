---
id: WS05-T03
title: "spec package: registry and template loaders, normalisation, ranking, plan signature check"
workstream: WS05-monitor
owner: agent
status: in_progress
depends_on: ["WS05-T02", "WS01-T03", "WS01-T04"]
critical_path: true
non_negotiable: false
estimate_pd: 3
sources: ["analisi §4.1", "analisi §4.2", "analisi §4.9 (7)"]
interfaces: ["02-interfaces.md#template", "02-interfaces.md#parameter-registry"]
review_items: ["R1-W9"]
---
## Obiettivo

Implement `ralmon.spec`: the contract dataclasses and enums of `#template` and `#parameter-registry`, `load_registry` and `load_templates` (with validation), `normalise` and `rank_alerts` of `#template`, the shared value types `Rho` and `RhoKind` of `#verdict` (single definition, re-exported by `ralmon.monitor`), and the integrity check of a distributed care plan (canonical serialisation, signature verification, registry version check). After this task no numeric clinical constant exists in `src/ralmon` outside the registry loader, and every template of the library loads with its unit, scale, priority and latency parameters resolved. It closes R1-W9 (integrity and versioning of the distributed specification, analisi §4.9 item 7).

## Contesto

Blocked until WS05-T02, WS01-T03 and WS01-T04 are `done` (WS01-T02 is done transitively, through WS01-T03).

- `docs/formal/03-parameter-registry.md` (YAML schema, which entries are time windows, derived entries such as `max_latency_<id>`, working names).
- `docs/formal/02-templates.md` (section 3, the seven-row template table; the fixture registry F0 and the 26 golden cases).
- `docs/formal/04-normalisation-ranking.md` (definition of `normalise` for infinities and clipping; direction of `priority`: in F0, priority 1 is the highest; ranking golden cases).
- `02-interfaces.md#template` (dataclasses, `normalise`, `rank_alerts`; the registry protocol and the verdict types are quoted where used).
- `docs/source/analisi.md` §4.9 item 7 (governance of the specification: versioning and signature).

## File toccati

- `src/ralmon/spec/` (modify: real modules `registry.py`, `templates.py`, `plan.py`, `normalise.py`, `rho.py`, `integrity.py`; placeholders removed from `_stubs.py`)
- `tests/spec/` (create: `test_normalise.py`, `test_rank_alerts.py`, `test_registry.py`, `test_templates.py`, `test_plan_integrity.py`, `test_rho_types.py`, `test_no_clinical_constants.py`)
- `tests/fixtures/spec/` (create: registry F0 in the WS01-T03 schema, template table fixture, copies of the golden cases used, signed-plan fixture and `make_plan_golden.sh`)
- `configs/templates/hypertension.yaml` (create only if WS01-T02 and WS01-T03 produced no machine-readable template table; transcription of the seven rows of `02-templates.md` section 3, each row with the locator `source`)
- `docs/plan/03-decisions.md` (modify: append one ADR, status `proposed`, for the plan signature scheme)

## Test

Write first; each fails before the implementation. Fixture registry F0 is the test-only table of `docs/plan/workstreams/WS01-formalization/README.md`; its clinical-looking rows are "illustrative, unverified" or fixture-only and never enter `configs/registry/hypertension.yaml`.

`test_normalise.py` and `test_rank_alerts.py`

1. `test_normalise_matches_ranking_golden[<id>]`: every `normalise` case of `docs/formal/golden/ranking.yaml` gives its expected value.
2. `test_normalise_hand_values`: `normalise(-12.0, 20.0) == -0.6`, `normalise(15.0, 20.0) == 0.75`, `normalise(-60.0, 20.0) == -1.0` (clipped, G-RANGE-5), `normalise(1_500_000.0, 1_800_000.0)` is `pytest.approx(0.8333, abs=1e-4)` (G-SCHED-1), `normalise(-180_000.0, 300_000.0) == -0.6` (G-INT-2), `normalise(-1.0, 1.0) == -1.0` (G-COUNT-1).
3. `test_normalise_infinities_and_nan`: `-inf` gives `-1.0`, `+inf` gives `1.0`, NaN raises `ValueError` (a failed guard is minus infinity, WS01-T02 section 2).
4. `test_normalise_rejects_nonpositive_scale`: scale `0.0` and `-20.0` raise `ValueError`.
5. `test_normalise_is_monotone_bounded_and_sign_preserving` (Hypothesis): for scale `s > 0` and `a <= b`, `normalise(a, s) <= normalise(b, s)`; the value is in `[-1, 1]`; `normalise(x, s)` has the sign of `x`.
6. `test_rank_alerts_priority_then_sigma_ascending`: alerts (priority, sigma_norm) = HOLD (1, -0.3), RANGE (2, -0.6), RANGE (2, -0.2), SCHED (3, -0.9) given in the order SCHED, RANGE(-0.2), HOLD, RANGE(-0.6) come out HOLD, RANGE(-0.6), RANGE(-0.2), SCHED: the most negative sigma is last only because its priority is lowest (lexicographic, never a `min` across units).
7. `test_rank_alerts_is_stable_on_ties`: equal `(priority, sigma_norm)` keep input order.
8. `test_rank_alerts_permutation_and_lexicographic_property` (Hypothesis): the output is a permutation of the input and no alert precedes one with a strictly higher priority.
9. `test_rank_alerts_accepts_any_object_with_priority_and_sigma_norm`: a local dataclass with only those two fields is accepted (structural typing; `ralmon.spec` never imports `ralmon.attribution`).

`test_registry.py`

10. `test_registry_f0_entries`: `get("bp_band_low")` is a `RegistryEntry` with value `110.0`, unit `mmHg`, `reviewed_by is None` and a rationale containing `illustrative, unverified`; `get("delta1").value == 3_600_000` and `get("delta2").value == 10_800_000`.
11. `test_registry_unknown_name_raises_registry_error`.
12. `test_registry_bounds`: `bounds("bp") == PhysioBounds(signal="bp", lower=50.0, upper=250.0)` (F0 `bound_bp_lower`, `bound_bp_upper`).
13. `test_registry_rejects_entry_without_rationale_or_source_ref`: an entry with an empty `rationale` or `source_ref` raises `RegistryError` naming the entry (ADR-020: every value carries both).
14. `test_registry_rejects_inverted_bounds`: `lower >= upper` raises `RegistryError`.
15. `test_registry_window_entries_are_multiples_of_step` (WS01-T01 W7): with `step_ms=60_000` a window entry of `1_800_000` loads and one of `90_500` raises `RegistryError`; the entries checked are those the WS01-T03 schema marks as windows (thresholds such as an inflation duration are not windows).
16. `test_registry_derived_latency_entries`: with `step_ms=60_000`, `get("max_latency_resp").value == 10_860_000` (`delta2 + step_ms`) and `get("max_latency_sched").value == 1_860_000` (`sched_window + step_ms`); the loader evaluates the derivation grammar of the WS01-T03 schema and never uses `eval`.
17. `test_registry_version_declared`: `version()` returns the string of the file; a file without one raises `RegistryError`.
18. `test_real_registry_file_loads`: `load_registry()` with no argument reads `configs/registry/hypertension.yaml` (WS01-T03) and validates it; unreviewed entries (`reviewed_by is None`) are accepted, never dropped.
19. `test_no_illustrative_clinical_constants_in_core_sources` (`test_no_clinical_constants.py`): an AST scan of `src/ralmon/{signals,spec,monitor,conformal,attribution}` finds no numeric literal equal to 50, 100, 110, 140 or 250 (the illustrative values of analisi §4.1 and §4.7); docstrings and comments are not scanned, the list is a constant of the test and a hit names file and line.

`test_templates.py`

20. `test_templates_cover_seven_ids_with_contract_kinds`: exactly one `Template` per `TemplateId`; kinds `RANGE`, `SCHED`, `HOLD`, `COUNT`, `RESP` are `CARE_PLAN`, `SYS` is `SYSTEM`, `INT` is `INTEGRITY`; `creates_robot_obligation` equals the section-3 table of `02-templates.md` (transcribed in the fixture with locator).
21. `test_template_names_follow_pattern_and_resolve`: `scale_param == "scale_<id>"`, `priority_param == "priority_<id>"`, `max_verdict_latency_param == "max_latency_<id>"` (WS01-T02 check 3), and every name in `params` and these three resolves in the F0 registry; an unknown name raises `TemplateLibraryError`.
22. `test_template_signals_are_signal_ids`: every entry of `Template.signals` is a `SignalId` value; a fixture row with an unknown signal raises `TemplateLibraryError`.
23. `test_enums_match_contract`: values of `TemplateKind`, `TemplateId`, `RobustnessUnit`, `RhoKind` and field names and order of `Template`, `TemplateInstance`, `CarePlan`, `RegistryEntry`, `PhysioBounds`, `Rho` equal the contract (hand-copied into the test).

`test_plan_integrity.py` and `test_rho_types.py`

24. `test_canonical_bytes_ignore_signature_and_mapping_order`: two plans that differ only in `signature` or in the insertion order of `param_values` produce identical canonical bytes (sorted keys, no whitespace, integers as integers).
25. `test_hmac_signature_matches_independent_golden`: the canonical bytes of the fixture plan, signed with the fixture key, equal the digest stored in the fixture and computed once with `openssl dgst -sha256 -hmac` (command in `make_plan_golden.sh`), so the expectation does not come from the code under test.
26. `test_verify_plan_rejects_tampered_field` (failing-first): changing one `schedule` tick or one `param_values` entry after signing raises `PlanIntegrityError`.
27. `test_verify_plan_rejects_registry_version_mismatch`: `plan.registry_version != registry.version()` raises `PlanIntegrityError`.
28. `test_unsigned_plan_allowed_unless_required`: `signature=None` passes with `require_signature=False` and raises with `True`; a signed plan with no verifier configured raises (never silently accepted).
29. `test_rho_and_rhokind_are_single_definition`: `ralmon.spec.Rho` is frozen and slotted with fields `value`, `kind`, `guarantee`, `alpha`, `assumptions`; `RhoKind` values are `measured`, `predicted`, `deterministic`.

## Passi

1. Verify unblock conditions; branch `ws05-t03-spec-package`; `status: in_progress`. Read the WS01 documents of Contesto. Write in the completion note: the path and schema of the registry, the path of the machine-readable template table (or that `configs/templates/hypertension.yaml` was created), and the priority direction found in `ranking.yaml`.
2. Copy the F0 registry and the seven-row template table into `tests/fixtures/spec/` in the WS01-T03 schema (fixture-only rows marked as such); copy the golden cases used with their `id` and `source`; add a test that the F0 copy equals the `fixture_registry` section of `docs/formal/golden/templates.yaml` when that file exists.
3. Write the tests of the Test section and the fixtures (`make_plan_golden.sh` builds the canonical bytes of the fixture plan and runs `openssl dgst -sha256 -hmac <fixture key>`; the stored digest and the key are committed). Run `pytest tests/spec -q`; watch the failures. Commit `WS05-T03: add failing spec tests`.
4. Implement in this order: `normalise.py`; `rho.py` (`Rho`, `RhoKind` verbatim from `#verdict`); `registry.py` (dataclasses, YAML loading with `yaml.safe_load`, validation rules exactly those of the WS01-T03 schema plus `lower < upper` and `scale > 0`, derived entries, window check, `RegistryError`, `load_registry(path=None, *, step_ms=None)` where `None` resolves `configs/registry/hypertension.yaml` from the directory that holds `pyproject.toml` and raises `RegistryError` naming the missing path); `templates.py` (`load_templates(path=None, registry=None)`, `TemplateLibraryError`); `plan.py` (`TemplateInstance`, `CarePlan`); `integrity.py`; `normalise.py` also holds `rank_alerts`, typed as `def rank_alerts(alerts: Sequence[A]) -> list[A]` with `A` bound to a Protocol that has read-only `priority: int` and `sigma_norm: float`, so `spec` does not import `attribution`.
5. Plan integrity in `integrity.py`: `PlanVerifier` Protocol (`verify(payload: bytes, signature: str) -> bool`), `HmacSha256PlanVerifier(key: bytes)` with `sign(plan) -> str` (hex digest of HMAC-SHA256 over the canonical bytes, standard library only, `hmac.compare_digest`), `canonical_plan_bytes(plan)` (JSON with sorted keys and compact separators over every `CarePlan` field except `signature`, UTF-8), `PlanIntegrityError` and `verify_plan(plan, verifier, *, registry_version=None, require_signature=False)`. Monotonic `plan_version` is enforced by the monitor when it loads a plan (WS05-T04), not here.
6. Append the ADR (status `proposed`, confirmation tag): the sources fix no signature scheme ("firma e versioning", analisi §4.9 item 7); HMAC-SHA256 with a shared key is chosen as the reference scheme because it needs no dependency and keeps the interface (`PlanVerifier`) open; key distribution and asymmetric signatures are a deployment matter, listed as a limitation; the threat model (WS02-T02) excludes a compromised specification, so this scheme covers accidental corruption and modification in transit only; alternatives: asymmetric signatures with a cryptography library, no signature.
7. Refactor; remove the migrated names from `spec/_stubs.py` and update `spec/__init__.py`; run `pytest tests/spec -q`, `ruff format src tests`, `ruff check src tests`, `mypy src/ralmon`, `python tools/check_plan.py`. Commit `WS05-T03: implement spec package`; set `status: done` and `status: ready` in the task files whose `depends_on` are now all `done`.

## Done when

From the repository root, inside `.venv`:

- `pytest tests/spec -q` exits 0 (the golden cases of `ranking.yaml` and `templates.yaml` used appear by id in the test report: `pytest tests/spec -q -k golden --collect-only | grep -c "golden"` prints at least 1).
- `ruff check src tests` and `ruff format --check src tests` exit 0; `mypy src/ralmon` exits 0.
- `python -c "from ralmon.spec import Template, TemplateId, TemplateKind, TemplateInstance, CarePlan, RobustnessUnit, ParameterRegistry, RegistryEntry, PhysioBounds, normalise, rank_alerts, load_registry, load_templates, Rho, RhoKind, PlanVerifier, HmacSha256PlanVerifier, PlanIntegrityError, verify_plan"` exits 0 and none of these names has `__ralmon_stub_owner__`.
- `python -c "from ralmon.spec import load_registry, load_templates; r = load_registry(); print(len(load_templates(registry=r)))"` prints 7.
- `! grep -rn "^from ralmon\.\(attribution\|monitor\|conformal\)\|^import ralmon\.\(attribution\|monitor\|conformal\)" src/ralmon/spec` succeeds.
- `grep -c "^## ADR-" docs/plan/03-decisions.md` has increased by one and the new entry names `HMAC-SHA256`.

## Notes

### Flag from the WS01-T04 review (orchestrator, 2026-09-30)

Test 7 ("equal `(priority, sigma_norm)` keep input order") conflicts with the tie-break `(t_ms, instance_key)` of `docs/formal/04-normalisation-ranking.md` (K0, OP-6). Test 9 ("a local dataclass with only those two fields is accepted") conflicts with K0, which needs `t_ms` and `xi.instance_key`. Test 1 (golden loader) must handle N-7 (`sigma_norm` as a two-element list over `calls`) and N-8 and N-9 (`expected.error`). Kept `blocked` until ADR-028 (proposed, `[DA-CONFERMARE]`) is decided; then adapt tests 7 and 9.

### Blocking note (orchestrator, 2026-10-05) [resolved 2026-10-08]

SKIPPED by the loop (the status is `ready` only because `tools/check_plan.py` rejects `blocked` when every dependency is `done`; the loop skips tasks that carry an unresolved blocking note). All dependencies are done (WS05-T02, WS01-T03, WS01-T04), but the task cannot be executed correctly until the human decides ADR-028 (proposed, `[DA-CONFERMARE]`: order key of `rank_alerts`, tie-break `(t_ms, instance_key)`, Protocol typing): tests 7 and 9 conflict with the tie-break and with the structural Protocol, test 1 (golden loader) must handle the shapes N-7, N-8 and N-9 of `docs/formal/golden/ranking.yaml`, and the fixture registry for runs before the clinician review is ADR-027 (proposed). The flags of the WS01-T04 review above describe the conflicts. Set the blocking note aside (delete this subsection) once ADR-028 and ADR-027 are confirmed or amended.

### ADR update (agent, 2026-10-08)

ADR-028 (order key `K0 = (priority, sigma_tilde, t_ms, instance_key)`, Protocol extended with `t_ms` and `instance_key`) was accepted by gab on 2026-10-08; adapt tests 7 and 9 to it. ADR-027 (fixture registry) is still proposed: gab asked for an assessment of using the datasets instead before deciding, so the blocking note above stays until ADR-027 is decided.

ADR-027 was accepted by gab later on 2026-10-08 as well: `configs/registry/fixture.yaml` with the F0 rows marked FIXTURE-ONLY, loaded only with `allow_fixture_only`, created by this task. With ADR-027 and ADR-028 accepted, the blocking note above is resolved and the task can run (tests 7 and 9 follow ADR-028; test 1 still handles the golden shapes N-7, N-8 and N-9).

### Completion note (worker, 2026-10-09)

Left `in_progress` on branch `ws05-t03-spec-package` (not merged, not set to `done`: the review closes it). Commits: `864c838` failing tests (collection errors for the missing modules, `NotImplementedError` from the placeholders), `ee3a933` implementation, `e566d15`, `6ebfcc2`, `8159237` test hardening after the mutation review, then the commit of this note. Only paths listed in "File toccati", `configs/registry/fixture.yaml` (ADR-027), two private helpers in `src/ralmon/spec/` (`_yaml.py`, `_text.py`), the ADR index line and ADR-051 were touched; no existing test, contract, ADR, registry value or formal document was edited.

**Facts asked by Passo 1.** Registry: `configs/registry/hypertension.yaml` (version 0.2.0, 31 entries, 7 derived, 3 unset: `priority_sys`, `priority_int`, `bound_dose_count_upper`), schema `configs/registry/registry.schema.json`; the loader re-implements the schema in code (no JSON Schema dependency). Fixture registry (ADR-027): `configs/registry/fixture.yaml`, version `0.0.0`, 29 entries, 7 derived, no unset, every entry FIXTURE-ONLY (the `rationale` starts with `FIXTURE-ONLY`, the F0 origin stays in the text); the test-owned copy `tests/fixtures/spec/registry_f0.yaml` is equal to it and to the `fixture_registry` section of `docs/formal/golden/templates.yaml` (checked; `meas_min_day`, `step_ms`, `reorder_delay_ms` are F0 rows that are not registry names, 03 section 3.3). Template table: no machine-readable table existed (`golden/templates.yaml` holds the F0 section and the 26 cases only), so `configs/templates/hypertension.yaml` was created (7 rows, locator in `source`); tests compare every cell with the markdown table of `02-templates.md` section 3.1 and with the transcription `tests/fixtures/spec/template_table.yaml`. Priority direction in `ranking.yaml` and `04` section 4.3: 1 is the highest, ascending order (`K0`).

**API.** `ralmon.spec.__all__` is the contract table (19 names). Outside `__all__` but importable from the package root (the layering rule forbids deep imports): `RegistryError`, `UnsetParameterError` (subclass), `TemplateLibraryError`, `LoadedRegistry` (the concrete registry: `get`, `bounds`, `version`, `is_declared`, `is_set`, `unset_names`, `unverified_names`, `fixture_only_names`, `overrides`, `window_parameters`, `step_ms`, `sha256`, `fixture_only`, `path`), `as_duration_ms`, `as_priority`. `load_registry(path=None, *, step_ms=None, allow_fixture_only=False)`, `load_templates(path=None, registry=None) -> tuple[Template, ...]` (enum order), `canonical_plan_bytes`, `verify_plan(plan, verifier, *, registry_version=None, require_signature=False) -> None`. `get()` on an unset name raises `UnsetParameterError` (never a default, never `None`). Rank order `K0`; `normalise` raises `ValueError` for everything invalid, a bool is not a number, `+-inf` maps to `+-1.0`.

**Deviations and decisions to confirm.**
1. `rank_alerts` Protocol: ADR-028 and the task text say a Protocol with `t_ms` and `instance_key`, but the real `Alert` carries `xi.instance_key` (04 section 4.1). The key is read from `xi.instance_key` when `xi` exists and from a flat `instance_key` otherwise; the TypeVar is bound to the union of the two Protocols. Tests 7 and 9 are adapted to ADR-028 as asked.
2. `load_registry` has the keyword `allow_fixture_only` that ADR-027 asks for, beyond the OP-4 signature. The `window_parameters` key is required (OP-5). A derived name needs `step_ms` only if its formula uses it (all seven do). The non-negative width `delta2 - delta1` is checked only when `step_ms` is given (03 section 2.5 rule 8, as written).
3. The unit and positivity checks of `scale_<id>` against the margin of the template (03 rule 10) live in `load_templates` (they need the table); the registry loader checks that a scale is positive with unit mmHg, ms or dose, and priorities (integral rank >= 1, unit 1) and ms durations (integral, >= 0).
4. `fixture.yaml` marks every entry FIXTURE-ONLY (ADR-027 literal), including the F0 rows whose origin is analisi; a registry with such a row is refused without the flag, the message names the rows. `registry.fixture_only` and `fixture_only_names()` are for the run manifest.
5. `load_templates` is stricter than the contract: the kind follows the decomposition, the three metadata names follow `scale_<id>`, `priority_<id>`, `max_latency_<id>`, and `signals` and `params` must be exactly the names the string mentions (`age` and `step_ms` are grammar words).
6. Plan canonical form (ADR-051): integers are signed 64-bit, `param_values` are written as floats (`2` and `2.0` sign alike), non-finite numbers and bools are refused, `-0.0` differs from `0.0`; an unsigned plan is not serialised by `verify_plan`; a signature has one text form (lowercase hex) and a verifier must return exactly `True`.
7. Contract dataclasses (`Template`, `CarePlan`, `Rho`, ...) have no validation in their constructors (frozen, slots, as the contract); validation is in the loaders and in `canonical_plan_bytes`.
8. `Rho` and `RhoKind` are defined once in `spec/rho.py`; `ralmon.monitor` already re-exported them, so no monitor change was needed. Nothing in the existing suite was edited.

**Where a proposed ADR would change this implementation.** ADR-045 (c): `CarePlan.schedule` becomes `Sequence[ScheduleTick]`, so the dataclass, the `_ticks` encoder (integers only) and the golden digests change, and plans signed before are invalid; (a) the `creates_robot_obligation` comment (the table already has True for INT); (e) the `formula_past_time` comment (the loader already enforces the grammar of 02 section 1.2); (f) HOLD refined form is already the string of the table. ADR-047: (d) `RegistryError`, `UnsetParameterError` and `load_registry`'s signature move into `__all__` and the Package public API (0.2.1); my extra `allow_fixture_only` keyword and `LoadedRegistry` extras are not in it; (g) the `param_values`-versus-`overrides` rule is not implemented here (the loader exposes `overrides()`; the monitor load, WS05-T04, applies it). ADR-049 (a), (b), (c): comment-only; the code already follows them. ADR-050: `K1` adds the verdict class as second key component and `rank_alerts` must then read `verdict` (RK-5 `recommended_extension` becomes the expected order and `test_rank_alerts_matches_ranking_golden[RK-5]` flips). ADR-046: negative `TimeMs` is already accepted by `rank_alerts` and the canonical form. ADR-051 (mine) fixes the signature scheme.

**Hand-overs.** WS05-T04: call `verify_plan(plan, verifier, registry_version=config.registry_version, require_signature=<ward deployment>)` in `Monitor.load` and refuse a lower `plan_version` yourself; read durations with `as_duration_ms`, priorities with `as_priority`, bounds with `registry.bounds`, per-patient keys against `registry.overrides()`; `load_registry(step_ms=config.step_ms)` already checks the alignment F1 and F6 partly (`load_templates` checks scale unit and priority); with the real registry `priority_sys`, `priority_int` and `bound_dose_count_upper` are unset, so SYS and INT cannot be ranked until they are filled or the fixture registry is used. WS05-T07/T08: `rank_alerts` accepts `Alert` as is. WS04-T10 to T12 and WS08: for runs before the review use `load_registry(<configs/registry/fixture.yaml>, step_ms=..., allow_fixture_only=True)` and label results with `registry.fixture_only`; put `registry.version()` and `registry.sha256` in the manifest; sign plans with `HmacSha256PlanVerifier(key).sign(plan)` and keep ints in the int64 range. WS06 baselines: `LoadedRegistry` satisfies `ParameterRegistry` (the audit wrapper only needs `get`, `bounds`, `version`); `sched_window` is an entry in 0.2.0. WS07-T03 and WS10-T04: a compressed registry written for `load_registry` needs every top-level key, `window_parameters`, the unverified rationale suffix, unit strings `mmHg`/`ms`/`dose`/`"1"` and integral ms values. WS08-T01 says it reuses the YAML reader of `load_registry`: it is private (`ralmon.spec._yaml`, bounded, safe, no anchors, no duplicate keys, no merge keys); the layering rule forbids a deep import, so it needs an ADR to export or a copy.

**Evidence** (real exit codes). `pytest tests/spec -q`: 917 passed, exit 0 (10.7 s, peak 104 MB with `/usr/bin/time -v`); `pytest -q` whole suite: 3274 passed (host 3.14, container 3.12 `docker compose run --rm test`, Humble image Python 3.10.12), exit 0 each; `ruff check src tests`, `ruff format --check src tests`, `mypy src/ralmon` exit 0 on the host, in `docker compose run --rm lint` and under 3.10 in the Humble image (`ruff check` and `mypy`); `pytest tests/spec -q -k golden --collect-only | grep -c golden` prints 61 and the 42 golden ids (26 `G-*`, `N-1` to `N-10`, `RK-1` to `RK-6`) are all collected and run; the Done-when imports exit 0 with no `__ralmon_stub_owner__`, the count command prints 7, the layering grep succeeds, the ADR count went from 50 to 51 and ADR-051 names HMAC-SHA256, `python3 tools/check_plan.py` exit 0, `python -m ralmon.benchmark.priors --check-table` exit 0. Changed-state proof: a `git archive HEAD` copy with the real registry changed (values, version, reviewers, `review_status`, every unset name filled; and a second copy fully reviewed with nothing unset) passes the 917 tests of `tests/spec`. Mutation self-check on copies of `HEAD`: 220 targeted mutants (normalise clip, sign, infinity, NaN and scale checks; rank key order, direction, tie-break and stability; registry window, derived grammar, bounds, rationale, unset, fixture gate, version, status; template kinds, flags, names, signals; canonical form per field, HMAC algorithm, compare, require_signature, version, key and signature format; error conversions; the data files); 219 killed after the tests added in `e566d15`, `6ebfcc2` and `8159237`; one survivor, `I29` (dropping the early `len(signature) != 64` return in `HmacSha256PlanVerifier.verify`), is equivalent because `hmac.compare_digest` returns `False` for unequal lengths. Golden digests of the plan tests come from `openssl dgst -sha256 -hmac` through `tests/fixtures/spec/make_plan_golden.sh` (run for real, outputs committed).

**Limits.** `verify_plan` does not serialise an unsigned plan, so a malformed unsigned plan passes it; the plan feasibility checks F2 to F7 and the `plan_version` monotonicity are the monitor's (WS05-T04). The HMAC key is shared, so the verifier can forge (stated in ADR-051). All registry values stay unreviewed (`reviewed_by` null): nothing here is a clinical claim.
