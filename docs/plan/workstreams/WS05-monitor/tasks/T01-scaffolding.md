---
id: WS05-T01
title: "Scaffolding of src/ralmon and toolchain"
workstream: WS05-monitor
owner: agent
status: in_progress
depends_on: []
critical_path: true
non_negotiable: false
estimate_pd: 0.5
sources: ["analisi §9 (5)", "analisi §8.1"]
interfaces: ["02-interfaces.md#package-public-api"]
review_items: []
---
## Obiettivo

Create the only package skeleton of the repository: `pyproject.toml` (Python 3.11 or newer, pytest, Hypothesis, ruff, mypy strict; ADR-016), `src/ralmon/` with exactly the eight packages `signals`, `spec`, `monitor`, `conformal`, `attribution`, `benchmark`, `baselines`, `eval`, a `tests/` tree that mirrors them, and one importable placeholder for every name of the Package public API contract. This is the only task that creates a package directory: later tasks of every workstream replace placeholders by real code inside the existing packages. Concrete output: `pytest tests -q` is green, and its assertions are limited to "every public name imports", "placeholders fail loudly and never fake behaviour", "the package graph follows `01-conventions.md` section 1" and "the toolchain is configured".

## Contesto

- `docs/plan/01-conventions.md` (sections 1, 2, 3 and 8: layout, dependency direction, Python style, TDD, no clinical constants in `src/ralmon`).
- `02-interfaces.md#package-public-api` (the table is the normative list of names; the aliases and constants of the time contract are copied verbatim as real definitions).
- `docs/plan/03-decisions.md` (ADR-016 toolchain, ADR-017 integer milliseconds, ADR-013 RTAMT is not installed by this task).
- `docs/plan/workstreams/WS05-monitor/README.md` (module layout, design decisions D1 and D2, readiness map of names to owner tasks).
- `docs/source/analisi.md` §8.1 (glossary used in identifiers and docstrings).

## File toccati

- `pyproject.toml` (create)
- `src/ralmon/` (create: eight package directories each with `__init__.py` and `_stubs.py`, `signals/units.py`, the private helper `_stub.py`, `py.typed`)
- `tests/` (create: one directory per package with `__init__.py`, `conftest.py`, `fixtures/`, `test_public_api.py`, `test_layering.py`, `test_toolchain.py`)
- `tools/check_plan.py` (modify: the bootstrap rule "no file under `src/`" lapses once this task is `done`)
- `docs/plan/02-interfaces.md` (modify: only the Package public API table and its version line; only if the ADR of step 7 applies)
- `docs/plan/03-decisions.md` (modify: append one ADR, status `proposed`, next free number; only if step 7 applies)

## Test

Stub policy that the tests enforce (decision D1 of the workstream README). A placeholder exists only so that a name imports; it never simulates behaviour.

- Constants and type aliases of `#time-and-units` (`TimeMs`, `DurationMs`, `MS_PER_SECOND`, `MS_PER_MINUTE`, `MS_PER_HOUR`) carry no behaviour and are defined for real, verbatim from the contract, in `src/ralmon/signals/units.py`.
- Every other public name is imported by its package `__init__.py` from a private module `_stubs.py` of the same package. A class or Protocol placeholder is an empty class whose instantiation raises `NotImplementedError` naming its owner task; a function placeholder is `(*args: object, **kwargs: object) -> NoReturn` and raises `NotImplementedError` naming its owner task. Both carry the attribute `__ralmon_stub_owner__ = "WSnn-Tnn"`, set by the two decorators of `src/ralmon/_stub.py` (the only place in `src/ralmon` that may write `NotImplementedError`).
- A placeholder never returns a value, never has a `pass` body, never catches exceptions, and is never typed `Any`. Behaviour tests arrive with the owner task; T01 asserts no behaviour beyond "fails loudly".
- The owner task moves its names out of `_stubs.py` into a real module, changes the import line in `__init__.py`, and deletes the placeholder; the marker then disappears and the stub tests stop covering the name. When `_stubs.py` is empty its owner deletes it.
- Placeholders are consumers' blocking signal: a task that needs a real type checks `__ralmon_stub_owner__` and stays blocked until the owner task is `done` (README readiness map).

Tests (write first; every one fails before the skeleton exists):

1. `test_contract_table_lists_exactly_eight_packages` in `tests/test_public_api.py`: the table under `## Package public API` of `docs/plan/02-interfaces.md` has exactly the eight package names.
2. `test_every_public_name_is_importable[<package>.<name>]`: parametrised from the parsed table (names in backticks; "`EvidenceVector` (and its parts)" expands to the six part classes `ProvenanceEvidence`, `SystemHealthEvidence`, `SignalQualityEvidence`, `CrossDeviceEvidence`, `EmbodiedWitnessEvidence`, `CryptoTemporalEvidence`): `importlib.import_module(package)` has the attribute.
3. `test_dunder_all_equals_contract_names[<package>]`: `set(module.__all__)` equals the parsed names of that package, no more and no fewer (a name added by an ADR appears in the table first).
4. `test_only_eight_package_directories`: the subdirectories of `src/ralmon` that hold an `__init__.py` are exactly the eight names.
5. `test_stub_functions_raise_not_implemented_naming_owner`: every exported object with `__ralmon_stub_owner__` that is a function raises `NotImplementedError` when called with no arguments, and the message contains its owner id.
6. `test_stub_classes_cannot_be_instantiated_silently`: instantiating any exported placeholder class raises `NotImplementedError` naming its owner.
7. `test_every_stub_owner_is_a_real_task`: each owner id matches `WS\d\d-T\d\d` and a file `docs/plan/workstreams/WS<nn>-*/tasks/T<nn>-*.md` exists for it.
8. `test_not_implemented_error_is_written_only_in_stub_helper`: no file under `src/ralmon` other than `_stub.py` contains the token `NotImplementedError` (so real code never hides an unfinished branch).
9. `test_layering_edges_follow_conventions` in `tests/test_layering.py`: an AST scan of every `import` and `from ... import` in `src/ralmon` builds the package graph; each edge is in `ALLOWED_EDGES` (constant at the top of the test): `signals` none; `spec` signals; `conformal` signals, spec; `monitor` signals, spec, conformal; `attribution` signals, spec, monitor; `benchmark` signals, spec, monitor (this is wider than `01-conventions.md` section 1, which says signals only, because WS04-T02 reads the registry and WS04-T10 runs the monitor; the ADR of step 7 records the amendment); `baselines` signals, spec, monitor, conformal, attribution, benchmark; `eval` all other seven. Type-only imports count as edges.
10. `test_cross_package_imports_use_package_root_only`: a module outside package P imports from `ralmon.P` and never from `ralmon.P.<submodule>` (contract: consumers import only from the package root).
11. `test_package_graph_is_acyclic`: the graph of test 9 has no cycle.
12. `test_core_never_imports_ros`: no file under `src/ralmon` imports `rclpy` or `rclcpp` (`01-conventions.md` section 1).
13. `test_time_constants_are_exact` (`tests/signals/test_units.py`): `MS_PER_SECOND == 1_000`, `MS_PER_MINUTE == 60_000`, `MS_PER_HOUR == 3_600_000`, `TimeMs is int`, `DurationMs is int`.
14. `test_pyproject_declares_toolchain` in `tests/test_toolchain.py`: `tomllib` reads `pyproject.toml`; `requires-python` starts with `>=3.11`; `tool.mypy.strict` is true and `files` covers `src/ralmon`; `tool.ruff.lint.extend-select` contains `I` and `B`; `tool.pytest.ini_options.testpaths` is `["tests"]`; runtime dependencies include `numpy` and `pyyaml`; the `dev` extra includes `pytest`, `hypothesis`, `ruff`, `mypy`; no dependency string carries a version specifier (versions are not invented, ADR-016; the environment resolves them and the completion note records them).
15. `test_hypothesis_profile_is_deterministic`: the profile loaded by `tests/conftest.py` has `derandomize=True` and no example database.
16. `test_rng_fixture_is_seeded_with_zero`: the fixture `rng` returns a `numpy.random.Generator`; two fresh fixtures give the same first draw (`01-conventions.md` sections 2 and 3, seed 0).

## Passi

1. Branch `ws05-t01-scaffolding` from `main`; set `status: in_progress` in this file. Create a virtual environment `.venv` (already gitignored) with Python 3.11 or newer.
2. Write the three test files, `tests/conftest.py` (Hypothesis profile registered and loaded with `derandomize=True`; fixture `rng` = `numpy.random.default_rng(0)`) and the empty per-package test directories with `__init__.py` so that equal test basenames in different directories do not collide. Run `pytest tests -q`; every test must fail or error because `ralmon` does not exist. Commit `WS05-T01: add failing scaffolding tests`.
3. Write `pyproject.toml` (PEP 621 metadata, `src` layout with `setuptools`, name `ralmon`, `requires-python = ">=3.11"`; runtime dependencies `numpy` and `pyyaml`; extra `dev` with `pytest`, `hypothesis`, `ruff`, `mypy` and the typing stubs for PyYAML if `mypy --strict` asks for them; `[tool.ruff.lint] extend-select = ["I", "B"]`; `[tool.mypy] strict = true`, `files = ["src/ralmon"]`; `[tool.pytest.ini_options] testpaths = ["tests"]`). Do not add `rtamt`: WS05-T02 decides (ADR-013). Install with `pip install -e ".[dev]"`; record the resolved versions in the completion note, nowhere else.
4. Write `src/ralmon/_stub.py` (the two decorators and nothing else) and `src/ralmon/py.typed`. Create the eight package directories. In each, write `_stubs.py` with one placeholder per name owned by another task, and `__init__.py` that imports every public name from `_stubs.py` (or from `signals/units.py` for the five real definitions) and lists them in `__all__`. Owner ids come from the readiness map of the README; the same map is reproduced below for this task.

   | Names | Owner |
   |---|---|
   | `ralmon.signals`: `SignalId`, `Sample`, `Event`, `EventKind`, `DerivedSignal`, `hold_last`, `minutes`, `hours` and the ADR additions `ObservedTrace`, `default_derived_signals`, `event_to_sample`, `impulses_on_grid` | WS05-T02 |
   | `ralmon.spec`: every name, including the ADR additions `Rho`, `RhoKind`, `PlanVerifier`, `HmacSha256PlanVerifier`, `PlanIntegrityError`, `verify_plan` | WS05-T03 |
   | `ralmon.monitor`: `Monitor`, `MonitorConfig`, `VerdictRecord`, `VerdictState`, `RobustnessInterval`, `run_offline` and the ADR additions `StreamingMonitor`, `Forecast`, `Forecaster`, `PointEvaluator`, `make_point_evaluator`, `MonitorConfigError`, `PlanVersionError` | WS05-T04 |
   | `ralmon.monitor`: `build_calibration_episodes`, `StaleCalibratorError` | WS05-T08 |
   | `ralmon.monitor`: `Rho`, `RhoKind` | no placeholder: re-exported from `ralmon.spec` |
   | `ralmon.conformal`: every name, including `BonferroniAllocation` | WS05-T06 |
   | `ralmon.attribution`: every name, including the six evidence parts and the ADR additions `RuleAttributor`, `EvidenceExtractor`, `extract_evidence` | WS05-T07 |
   | `ralmon.benchmark`: `BenchmarkDay`, `ObservedDay`, `LatentDay`, `GroundTruthEvent`, `InjectedClass` | WS04-T01 |
   | `ralmon.benchmark`: `PriorSource`, `LiteraturePriorSource`, `PatientParams`, `AdherenceParams`, `DeviceErrorModel`, `ParamProvenance` | WS04-T02 |
   | `ralmon.benchmark`: `generate_benchmark` | WS04-T11 |
   | `ralmon.baselines`: `Detector` WS06-T01; `B1StaticThresholds` WS06-T02; `B2AnomalyDetection` WS06-T03; `B3PlainSTL` WS06-T04; `B4ConformalOnly` WS06-T05; `B5ConformalSTL` WS06-T06 | as listed |
   | `ralmon.eval`: every name | WS08-T01 |

5. Write `signals/units.py` (aliases and constants verbatim from `#time-and-units`; `minutes` and `hours` stay placeholders owned by WS05-T02).
6. Run the tests until only step 7 items remain; run `ruff format src tests`, `ruff check src tests`, `mypy src/ralmon`.
7. API reconciliation ADR. The Package public API table is the list the tests parse, and the contracts of WS05-T02 to WS05-T08 use names it does not list. Unless the table already lists every name marked "ADR addition" above (check with `grep -c "default_derived_signals" docs/plan/02-interfaces.md`), append one ADR (status `proposed`, confirmation tag as defined at the top of `03-decisions.md`, next free number) and edit the table in the same commit, bumping the Package public API version from 0.1.0 to 0.2.0. Content of the ADR:
   - Context: `TimeMs` and `DurationMs` are used in every contract but are not public; `Forecaster` and `Forecast` have no package; no concrete `Monitor` or `Attributor` is public although the ROS 2 wrappers and WS08 need one; `Rho` is defined in `#verdict` (monitor) but `PredictedViolation` (conformal) needs it while `monitor` uses `conformal`, which would create a cycle; `run_offline` takes `ObservedDay`, defined in `benchmark`, while WS04-T10 needs `monitor`; `rank_alerts` names `Alert`, which lives above `spec`.
   - Decision: add the names listed above to their packages; define `Rho` and `RhoKind` once in `ralmon.spec` and re-export them from `ralmon.monitor`; add the structural `ObservedTrace` Protocol to `ralmon.signals` and annotate monitor inputs with it (`ObservedDay` satisfies it, the contract signature is unchanged for callers); `rank_alerts` is typed by structural Protocol on `priority` and `sigma_norm`; amend `01-conventions.md` section 1 so that `benchmark` may import `spec` and `monitor` public APIs. No signature of any contract changes here.
   - Alternatives: move the day dataclasses to `signals`; import `benchmark` from `monitor` (creates a cycle with WS04-T10).
   - Consequences: affected tasks WS05-T02 to WS05-T08, WS04-T02, WS04-T10, WS06-T03 to WS06-T06, WS08-T01, WS05-T09.
8. Adjust `tools/check_plan.py`: `check_src` (bootstrap rule 8, "src/ must be empty") reports an error only while WS05-T01 is not `done`; once it is `done` it fails if `src/` holds anything other than the package `ralmon` (and its `*.egg-info`). The plan verifier must keep exiting 0 after the scaffold exists.
9. Run every command of "Done when". Commit `WS05-T01: scaffold ralmon package`. Set `status: done`; set `status: ready` in the task files whose `depends_on` are now all `done` (WS05-T02 and every other task whose only open dependency was this one); the plan verifier checks this coherence.

## Done when

From the repository root, inside `.venv`:

- `pytest tests -q` exits 0.
- `ruff check src tests` exits 0 and `ruff format --check src tests` exits 0.
- `mypy src/ralmon` exits 0.
- `python -c "import ralmon.signals, ralmon.spec, ralmon.monitor, ralmon.conformal, ralmon.attribution, ralmon.benchmark, ralmon.baselines, ralmon.eval"` exits 0.
- `test "$(find src/ralmon -mindepth 1 -maxdepth 1 -type d ! -name __pycache__ ! -name '*.egg-info' | wc -l)" = 8` succeeds.
- `! grep -rn "NotImplementedError" src/ralmon --include=*.py | grep -v "src/ralmon/_stub.py"` succeeds.
- `python tools/check_plan.py` exits 0 (task status coherence, the edited contract anchors and the adjusted `src/` rule).
- When step 7 applied: `grep -c "^Version 0.2.0. Owner WS05. Consumers: all." docs/plan/02-interfaces.md` prints 1 and `grep -c "^## ADR-" docs/plan/03-decisions.md` has increased by one.
