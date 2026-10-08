---
id: WS07-T01
title: "Package availability check and simulation workspace"
workstream: WS07-ros2-sim
owner: agent
status: in_progress
depends_on: ["WS00-T05"]
critical_path: true
non_negotiable: false
estimate_pd: 2
sources: ["analisi §5.2"]
interfaces: ["02-interfaces.md#ros-2-interfaces"]
review_items: []
---
## Obiettivo

Verify from primary sources that the simulation stack of analisi §5.2 exists for the target ROS 2 Jazzy with Gazebo Harmonic (ADR-011) and record the result, with evidence for every claim, in `ros2/ralmon_sim/config/package_availability.yaml`: the ROS-Gazebo bridge, Nav2, the PAL TIAGo Pro or TIAGo simulation packages, a hospital world (the AWS RoboMaker hospital world named in analisi §5.2: ROS 2 support and the port from Gazebo Classic), HuNavSim (optional), ros2_tracing with LTTng, `tc netem`, and the onboard computer specification. Also create the colcon workspace skeleton `ros2/` with the package `ralmon_sim` and all console-script entry points of the README module map, so that WS05-T09 can add its packages to the same workspace. This task must not depend on WS05 and must not import `ralmon`, because WS05-T09 depends on it.

## Contesto

Blocked until WS00-T05 is done: read its artefact `docs/plan/workstreams/WS00-admin/outputs/WS00-T05.md` first (sections `ROS 2 distribution and Gazebo compatibility`, `TIAGo Pro simulation model`, `Onboard computer specs`, `ADR-011 decision`, `Open points`). Its findings are prior evidence, not a substitute for the checks below.

- `docs/source/analisi.md` §5.2 (setup), §9 rows 0.7 and 7; `docs/plan/workstreams/WS07-ros2-sim/README.md` (module map, layout, clock policy).
- `docs/plan/03-decisions.md` ADR-011 (Jazzy with Gazebo Harmonic; superseded by Humble if the packages need it), ADR-003 (ward node plus robot), ADR-016 (Python 3.11 or newer).
- `docs/plan/02-interfaces.md#ros-2-interfaces` (lifecycle nodes, liveliness and deadline QoS, topic names).
- `docs/plan/01-conventions.md` section 1 (`ros2/` holds thin packages; `src/ralmon` never imports ROS).

## File toccati

- `ros2/` workspace skeleton (create): `ros2/.gitignore` (build, install, log), `ros2/sim.repos` (vcstool file pinning third-party sources), and the package `ros2/ralmon_sim/{package.xml,setup.py,setup.cfg,resource/ralmon_sim,ralmon_sim/__init__.py}`.
- `ros2/ralmon_sim/config/package_availability.yaml` (create)
- `ros2/ralmon_sim/doc/availability.md` (create)
- `ros2/ralmon_sim/scripts/check_sim_env.sh` (create)
- `ros2/ralmon_sim/test/` (create): `conftest.py` and `test_package_availability.py`.
- `docs/plan/03-decisions.md` (modify only if the verdict is `supersede_adr_011`: append the superseding ADR, next free number, status proposed)

## Test

Write these pytest tests first (plain Python, no ROS, no network). They read the YAML record and the package files as text.

- `test_component_ids_complete`: the record has a `components` mapping containing at least `ros2_distro`, `gazebo`, `ros_gz_bridge`, `nav2`, `robot_sim_pal`, `hospital_world`, `human_sim`, `ros2_tracing`, `tc_netem`, `onboard_computer`, `isaac_sim`.
- `test_status_values_valid`: every component `status` is one of `available`, `partial`, `unavailable`, `unverified`, `not_evaluated`; `isaac_sim` is `not_evaluated` with a `notes` field citing analisi §5.2.
- `test_evidence_required_unless_unverified`: a component with status `available`, `partial` or `unavailable` has non-empty `evidence`, an ISO `verified_on` date and `verified_by` (`agent` or a name taken from WS00-T05).
- `test_version_requires_source_url`: a non-null `version` implies a non-empty `source_url` (no value from memory).
- `test_verdict_consistent_with_components`: `verdict` is `adopt_adr_011`, `supersede_adr_011` or `blocked`; `adopt_adr_011` requires `ros2_distro`, `gazebo`, `ros_gz_bridge` and `nav2` to be `available` with `target.ros_distro: jazzy` and `target.gazebo: harmonic`; any `unavailable` among those four forbids `adopt_adr_011`.
- `test_robot_variant_declared`: `robot_sim_pal.variant` is one of `tiago_pro`, `tiago`, `stand_in`; `stand_in` requires a `notes` field explaining that no vendor model runs on the target stack and naming the wording for the paper ("TIAGo-class").
- `test_hospital_world_decision_declared`: `hospital_world.decision` is one of `port_aws`, `use_ros2_branch`, `procedural`, with `license` and `source_url` filled unless `procedural`.
- `test_onboard_computer_fields`: `onboard_computer` has `cpu_model`, `cores`, `ram_gb`, `source_ref`, `verified_by`; a field not found in a source is the string `not stated in <source>`, never a guess.
- `test_conftest_makes_package_importable`: after collection, `import ralmon_sim` succeeds without installing the package (the conftest puts `ros2/ralmon_sim` on `sys.path`), and the module resolves to the working tree.
- `test_ros_marker_skips_without_rclpy`: in an interpreter where `rclpy` cannot be imported, a test marked `ros` is reported as skipped by the conftest hook, not failed (checked with `pytester` or a subprocess).
- `test_setup_py_declares_module_map_entry_points`: `setup.py` contains every console script of the README module map (`sim_device_node`, `sim_gateway_node`, `sim_backend_node`, `robot_task_node`, `fault_injector_node`, `deadline_prediction`, `deadline_logger_node`, `measure_run`) with the module paths of that table.
- `test_package_xml_declares_runtime_dependencies`: `package.xml` has `exec_depend` entries for `rclpy`, `lifecycle_msgs`, `std_msgs`, `std_srvs`, `geometry_msgs`, `nav2_msgs`, `launch_ros`, `ralmon_sim_msgs` and `ralmon_ros`.
- `test_no_ralmon_import_in_skeleton`: no file under `ros2/ralmon_sim/` imports `ralmon` (T01 stays independent of WS05).

Verification checks for the non-code parts:

1. `bash ros2/ralmon_sim/scripts/check_sim_env.sh` in a shell without a sourced ROS 2 environment exits 2 and prints "ROS 2 environment not sourced".
2. In the sourced environment it prints one line per component (`id status observed`) and exits 0 exactly when every component recorded as `available` is observed on the machine.
3. `doc/availability.md` has the H2 headings `Host`, `Verdict`, `Component table`, `Reproduction`, `Hospital world decision`, `Robot variant decision`, `Onboard computer`, `Open items for a human`, `Proposed ADR`.

## Passi

1. Read the WS00-T05 artefact; copy its per-component findings into the record as prior evidence with `verified_by: WS00-T05` only where it gives a source and a date; list gaps for step 4.
2. Write `conftest.py` (puts `ros2/ralmon_sim` on `sys.path`, marker `ros`, skip hook when `rclpy` is missing, a helper fixture that starts a launch file in a subprocess with a timeout and kills its process group on teardown) and `test_package_availability.py` with the tests above. Run `pytest ros2/ralmon_sim/test -q`; it must fail because the record does not exist.
3. Record the host in `package_availability.yaml` under `host`: OS release, kernel, architecture, CPU model, core count, RAM, GPU or none (headless rendering). If the host OS is not a supported platform of the target distribution, record the container or virtual machine route chosen and use it for every later step.
4. Check each component against its primary source (official package index, repository, release notes or documentation; network required) and fill `status`, `version` (only if read from the source), `source_url`, `evidence` (URL, or a command with its captured output saved in `doc/availability.md`), `verified_on`, `verified_by`:
   - `ros2_distro` and `gazebo`: installable on the host route; Python version delivered by the distribution satisfies ADR-016 (3.11 or newer).
   - `ros_gz_bridge`: packages that pair Jazzy with Gazebo Harmonic (package names as found).
   - `nav2`: binary packages for the target distribution.
   - `robot_sim_pal`: vendor simulation repositories for TIAGo Pro and TIAGo, the distributions and Gazebo generations each branch supports, and whether an arm is simulated; choose `variant` (preference order `tiago_pro`, `tiago`, `stand_in`).
   - `hospital_world`: repository, branches, whether a ROS 2 branch exists, Gazebo generation of the model files, license text, size; choose `decision`. `procedural` means WS07-T02 generates a ward from the room layout.
   - `human_sim`: HuNavSim repository, supported distributions and Gazebo generations (marked with a dagger, unverified, in analisi §5.2); optional.
   - `ros2_tracing`: tracing packages for the distribution, LTTng installation, whether the current user may create a trace session, and which analysis tool (`tracetools_analysis` or a CTF reader) is installable.
   - `tc_netem`: `tc` present, kernel module `sch_netem` available, privilege needed; whether a same-host DDS stream is affected (shared-memory transport may bypass the network interface, so run a message-count probe and, if drops do not appear, record the RMW settings that force UDP). If no privilege is available the status is `unverified` with the required human action.
   - `onboard_computer`: CPU, cores, RAM from the vendor documentation for the chosen robot variant, with `source_ref`; note the equivalent hardware named in WS00-T05.
   - `isaac_sim`: `not_evaluated` by design (analisi §5.2 advises against it for a small group).
5. Set `target` (`ros_distro`, `gazebo`) and `verdict`. If the verdict is `supersede_adr_011` or `blocked`, write the proposed ADR (context, decision, alternatives, consequences, status proposed) in `doc/availability.md` under `Proposed ADR` and append it to `docs/plan/03-decisions.md` with the next free number; the `ralmon` core is unaffected because it is ROS-independent.
6. Create the workspace: `ros2/.gitignore`; `ros2/sim.repos` in vcstool format with one entry per third-party repository, each pinned to the commit found in step 4 (an empty `repositories:` mapping if none is needed); the `ralmon_sim` skeleton with `setup.py` (data files for `launch`, `config`, `config/experiments`, `config/fault_schedules`, `worlds` by glob; all console scripts of the README module map), `package.xml` (dependencies of the test above, only names verified in step 4 or fixed by the plan), `setup.cfg`, the `resource/ralmon_sim` marker and an empty `ralmon_sim/__init__.py`.
7. Write `check_sim_env.sh` (exit 2 without a sourced environment; otherwise one line per component; exit 0 when every `available` component is observed, exit 1 otherwise). It must not require `ralmon`; it may print whether `import ralmon` works, as information only.
8. From `ros2/`, run `colcon build --packages-select ralmon_sim`, source the install space and check `ros2 pkg prefix ralmon_sim`. Fix until it exits 0.
9. Write `doc/availability.md` with the required headings: host facts, verdict and reasons, the component table, the ordered install and reproduction commands, the hospital world and robot variant decisions with the wording for the paper, the onboard computer, every `unverified` item with the human action needed, the proposed ADR if any.
10. Run the tests until they pass, run `ruff check ros2/ralmon_sim` and `ruff format ros2/ralmon_sim`, and commit with `WS07-T01: verify simulation stack and create workspace`. Tell the owner of WS05-T09 that it is unblocked and give the verdict.

## Done when

From the repository root, in the environment described by the record:

- `pytest ros2/ralmon_sim/test/test_package_availability.py -q` exits 0.
- `ruff check ros2/ralmon_sim` and `ruff format --check ros2/ralmon_sim` exit 0.
- `(cd ros2 && colcon build --packages-select ralmon_sim)` exits 0.
- `bash ros2/ralmon_sim/scripts/check_sim_env.sh` exits 0.
- `grep -cE '^## (Host|Verdict|Component table|Reproduction|Hospital world decision|Robot variant decision|Onboard computer|Open items for a human|Proposed ADR)$' ros2/ralmon_sim/doc/availability.md` prints `9`.
- `grep -rnE '^(import|from) ralmon' ros2/ralmon_sim` prints nothing, and `grep -nE 'TO''DO|TB''D|lo''rem|[?][?][?]' ros2/ralmon_sim/doc/availability.md ros2/ralmon_sim/config/package_availability.yaml` prints nothing.

## Notes

### Blocking note (orchestrator, 2026-10-02) [resolved 2026-10-08]

Selected by the loop on 2026-10-02 and SKIPPED (the status stays `ready` because `tools/check_plan.py` rejects `blocked` when every dependency is `done`; the loop skips tasks that carry an unresolved blocking note). The task reads `docs/plan/workstreams/WS00-admin/outputs/WS00-T05.md` (TIAGo availability, ROS 2 distribution and Gazebo compatibility, ADR-011 decision), marked `done` by the human but absent from the repository, and needs ROS 2, `rclpy` and Gazebo, which are not installed on this machine (no sudo, no system packages). Set the status back to `ready` once the artefact exists and ROS 2 is installed.

Update 2026-10-04: ROS 2 Jazzy, Gazebo Harmonic (`gz sim` 8.15.0), `rclpy`, `ros_gz_sim` and `ros_gz_bridge` are now available in the image `ralmon-ros2:jazzy` (`docker compose --profile ros2 run --rm ros2`, ADR-031 proposed). The remaining block is the missing record `docs/plan/workstreams/WS00-admin/outputs/WS00-T05.md` (TIAGo or TIAGo Pro availability, the simulation package versions and the ADR-011 decision); the image contains no TIAGo packages.

### Hand-over from WS00-T05 (agent, 2026-10-08)

The blocking note above is resolved: `docs/plan/workstreams/WS00-admin/outputs/WS00-T05.md` exists, and ADR-011 is superseded by ADR-042 (accepted by gab): **ROS 2 Humble with Gazebo Classic** (Fortress through PAL's new-Gazebo option as fallback), and **Python 3.10 as the floor of `ralmon`** (supersedes ADR-016). Read the task's Jazzy and Harmonic wording accordingly: the verdict is `supersede_adr_011` with ADR-042 already written, the Python check of step 2 is against 3.10, and `ros_gz_bridge` pairs Humble with Classic or Fortress. First step, before the stack check: the migration of ADR-042 (`requires-python = ">=3.10"` in `pyproject.toml`, `tests/test_toolchain.py` pins `>=3.11`, then `pytest`, `ruff` and `mypy` run under Python 3.10 in a Humble container) and a Humble image replacing `ralmon-ros2:jazzy` (ADR-031). PAL packages: `tiago_simulation` 4.13.0 and `tiago_pro_simulation` 1.19.0 on `humble-devel` (the TIAGo Pro instructions start from the PAL developer Docker image; building outside it is unchecked). Tracing on Humble needs LTTng and `tracetools` built from source. The real TIAGo and TIAGo Pro of the group run Humble.

### Completion note (worker, 2026-10-08)

Status stays `in_progress`: not set to `done`, not merged. Branch `ws07-t01-sim-workspace`; commits `WS07-T01: add failing availability tests` and `WS07-T01: verify simulation stack and create workspace`. Owner of WS05-T09: the task is unblocked in substance (workspace `ros2/` with `ros2/ralmon_sim` exists, verdict `supersede_adr_011`, image `ralmon-ros2:humble`); the status flip of dependents is for the reviewer.

**Verdict and record.** `supersede_adr_011` with `target.ros_distro: humble`, `target.gazebo: classic`, fallback Fortress; ADR-042 is already accepted, so no ADR was appended (`doc/availability.md`, `Proposed ADR`, lists what is new). Statuses (all verified 2026-10-08, `verified_by: agent`): `ros2_distro`, `gazebo`, `ros_gz_bridge`, `nav2`, `robot_sim_pal` (variant `tiago_pro`), `hospital_world` (decision `use_ros2_branch`) and `ros2_tracing` are `available` and observed by `check_sim_env.sh` in the image; `human_sim` (HuNavSim, optional: documented for Humble and Classic, no binary, no build attempted), `tc_netem` (works in a container with `NET_ADMIN`, the host user has no privilege) and `onboard_computer` (TIAGo Pro datasheet: Intel i5, 16 GB; cores and the group's exact configuration not stated) are `partial`; `isaac_sim` is `not_evaluated`. Nothing is `unverified`; the human actions are in `Open items for a human`.

**Adaptations from the Jazzy and Harmonic wording.** (1) Target Humble and Classic, Fortress as fallback; (2) the Python check is against 3.10 (image: 3.10.12); (3) the ROS-apt binaries (packages.ros.org) of `ros_gz_bridge` for Humble are Fortress only (the ros_gz README table also lists Garden and Harmonic for Humble from packages.osrfoundation.org; Classic is not listed), the Classic integration is `gazebo_ros_pkgs`, so the component records both and the script observes both (the hand-over said "Classic or Fortress"); (4) `test_verdict_consistent_with_components` adapted for `supersede_adr_011` (target humble and classic, four gate components available, ADR present in `03-decisions.md`), `adopt_adr_011` still forbidden when a gate component is unavailable; (5) tracing needs LTTng and a source build of `tracetools` (overlay of the image, pinned in `ros2/sim.repos` with the hospital world); (6) PAL packages come from the ROS apt repository (the PAL developer image is not needed; this closes the open point of WS00-T05); the new-Gazebo option on Humble is Fortress (`libignition-gazebo6`, `gz-sensors6`; closes the second open point); (7) the image `ralmon-ros2:jazzy` is replaced by `ralmon-ros2:humble` (4.35 GB, base `ros:humble-ros-base`); the old Jazzy image is still on the machine, unreferenced.

**Python 3.10 migration (ADR-042).** `pyproject.toml`: `requires-python = ">=3.10"` only. Incompatibilities found by a real run under Python 3.10.12 in the Humble container: (a) `tests/test_toolchain.py` imported `tomllib` (3.11+) and pinned `>=3.11`: pin changed to `>=3.10`, import falls back to `tomli` on 3.10 (pytest and mypy depend on it there); this is the only edit under `src` or `tests`, no public API changed. (b) With the system numpy of Humble (1.21.5, REP 2000) one test fails (`tests/benchmark/test_c1_confounders.py::test_foreign_objects_with_unreadable_fields_are_named_errors`) and `mypy src/ralmon` reports 5 `no-untyped-call` errors (`can_cast`, `diff`); both pass on Python 3.10 with numpy 1.26.4 and 2.2.6, so they are numpy effects, not Python effects, and were not changed (a numpy floor would be a `pyproject.toml` pin, ADR-016; listed for a human). The image installs numpy `<2` (1.26.4), because numpy 2.2.6 breaks the import of the apt pandas 1.3.5 used by `tracetools_analysis`, and keeps the apt pytest 6.2.5 because pytest 9 breaks the ROS `launch_testing` plugins at start-up. Results: Python 3.10.12 (Humble image) `pytest -q` 2357 passed, `ruff check src tests`, `ruff format --check src tests`, `mypy src/ralmon` exit 0; Python 3.12.15 (`ralmon-dev`, `docker compose run --rm test` and `lint`) 2357 passed and lint exit 0; Python 3.14.4 (host `.venv`) 2357 passed, ruff and mypy exit 0. On the apt numpy 1.21.5 the 3.10 suite gives 2356 passed and 1 failed.

**Done-when, real exit codes.** In the Humble container: `pytest ros2/ralmon_sim/test/test_package_availability.py -q` 23 passed, exit 0 (22 passed and 1 skipped, exit 0, on the host `.venv` and in `ralmon-dev`: the `ros` test needs `rclpy`); `ruff check ros2/ralmon_sim` 0; `ruff format --check ros2/ralmon_sim` 0; `(cd ros2 && colcon build --packages-select ralmon_sim)` 0 and `ros2 pkg prefix ralmon_sim` 0; `bash ros2/ralmon_sim/scripts/check_sim_env.sh` 0 (the host shell, no ROS sourced, prints `ROS 2 environment not sourced` and exits 2; a copy of the record with `human_sim` set to `available` exits 1). On the host: the heading grep prints `9`, the `^(import|from) ralmon` grep and the forbidden-words grep print nothing (exit 1 each), `python3 tools/check_plan.py` exit 0. `colcon build` does not need `ralmon_sim_msgs` and `ralmon_ros` (declared as `exec_depend`, absent; the build succeeded without them).

**Deviations and additions.** Files outside the task list, all allowed by the hand-over or needed by it: `pyproject.toml`, `tests/test_toolchain.py`, `docker/Dockerfile.ros2`, `docker/ros-entrypoint.sh`, `docker/README.md`, `docker-compose.yml` (image tag only), and `ros2/ralmon_sim/scripts/netem_probe.py` (the message-count probe cited by the record). `ros2/.gitignore` also ignores `third_party/` (the vcstool import target). `sim.repos` pins two repositories (ros2_tracing, hospital world); HuNavSim is not pinned. The `ros` marker test and extra tests (record header, `sim.repos`, headings, exit code 2 of the script) were added to the listed tests. `package.xml` carries `<license>NOASSERTION</license>` and the git author as maintainer, to be replaced by WS13-T01. The build cache of the image builds and the scratch directory `outputs/ws07-t01/` (not committed) were left in place.

**Not shown.** No robot motion, navigation goal or hospital world with a robot was run; no Fortress simulation was launched; HuNavSim was not built; kernel tracing was not tried; `tc netem` was not applied on the host; the netem Fast DDS results varied between two runs (the cause was not isolated).

### Fix round 1 (worker, 2026-10-08)

Status stays `in_progress`; no new ADR; `pyproject.toml` untouched in this round. Each finding was checked against its source before the change; none was disputed.

- **F1 fixed.** The page 2 image of `2025-Datasheet-TIAGo-Pro.pdf` lists a GPU only under UPGRADES AND ACCESORIES ("NVIDIA Jetson PC"). `onboard_computer.gpu` is now `not stated in 2025-Datasheet-TIAGo-Pro.pdf`, with a new `gpu_upgrade` field; the doc table says the same. New test `test_onboard_computer_gpu_is_not_guessed` (failed first).
- **F2 fixed.** `BehaviorTree.CPP 4.6` is in the README of branch `v1.0-humble` only; the v2.0 README lists BehaviorTree.CPP and BehaviorTree.ROS2 without a version. `human_sim.notes` and open item 8 now say so.
- **F3 fixed.** `check_sim_env.sh` catches any error while reading the record (including a missing PyYAML), prints one line `cannot read <file>: <ErrorType>: <first line>` on stderr and exits 3, with no traceback. Tests (failed first): `test_check_script_exits_3_with_one_line_on_a_malformed_record` for a YAML syntax error, a list instead of a mapping and a record without `components`.
- **F4 fixed.** A row recorded as `available` whose observation is not `yes` (`no` or `n/a`) now counts as missing, so the script exits 1; `n/a` is still printed. Tests (failed first): `test_check_script_exits_1_when_an_available_component_cannot_be_observed` for `isaac_sim` and `onboard_computer` set to `available` in a scratch record, and `test_check_script_exits_0_on_the_committed_record_when_everything_is_observed`. They run a copy of the script with stub `ros2`, `gazebo`, `lttng`, `tc` and `python3` executables, so they do not depend on the machine; the host exit-2 test and the `ros` marked test are unchanged. Container run with the committed record: exit 0; with `isaac_sim` available: `isaac_sim available n/a`, exit 1; with a malformed record: one line, exit 3.
- **F5 noted.** Verified in the package metadata: pytest 9.1.1 requires `tomli>=1; python_version < "3.11"` and mypy `tomli>=1.1.0; python_version < "3.11"`; the apt pytest 6.2.5 requires neither. Open item 4 of `doc/availability.md` proposes `tomli; python_version < "3.11"` for the dev extras (a human decision; `test_pyproject_declares_toolchain` accepts plain names only).
- **F6 verified and written.** Bisection in throw-away Humble containers (pip `--target` under `/tmp`, Python 3.10.12, `outputs/ws07-t01/numpy_bisect.sh`): the test fails with numpy 1.21.6, 1.22.4, 1.23.5, 1.24.4 and passes with 1.25.0, 1.25.1, 1.25.2, 1.26.4 (and 2.2.6, earlier run); mypy reports its 5 errors with 1.21.5 and 1.21.6 and passes with 1.22.4, 1.25.0, 1.25.2. Patch versions in between were not run, so the floor is "about 1.25". Written in open item 3, in `Step 3` of the doc and in `docker/README.md`; not added to `pyproject.toml`.
- **F7 fixed.** The doc Verdict bullet, the doc Proposed ADR bullet, the YAML `ros_gz_bridge.notes` and point (3) of the completion note above now say that the ROS-apt binaries are Fortress only, and that the README table also lists Garden and Harmonic for Humble from packages.osrfoundation.org.
- **F9 written.** Reproducibility limits (floating base tag, unpinned apt and pip, 44 Fuel models downloaded at build time without pins) are stated in the Reproduction intro and as open item 6 for WS13.
- **F10 written.** Open item 7: which RMW the group's real robots run. PAL's `tiago_simulation` README (branch humble-devel, opened on 2026-10-08, saved in `outputs/ws07-t01/src/`) says the simulation is more reliable with Cyclone DDS and that issues with Fast RTPS are still being looked at; quoted with its URL.
- **F11 fixed.** `tc_netem.version` is `5.15.0-1ubuntu2.2` (jammy-updates; verified with `dpkg-query` in the image and on `https://packages.ubuntu.com/jammy-updates/iproute2`), with the release pocket version named.
- **Observation for the orchestrator.** Open item 9 lists the plan documents that still describe Jazzy and were not edited: `WS07-ros2-sim/README.md` line 20, `tasks/T02-hospital-world.md` line 17, and ADR-031 in `03-decisions.md` (lines 262 and 264).
- **Scratch containers.** `docker rm -f t07simrev-1 t07simrev-5` failed with `permission denied` (could not kill the container); left in place.

Re-run after the edits (real exit codes): availability test 30 passed exit 0 in the Humble container, 29 passed and 1 skipped exit 0 on the host `.venv` and in `ralmon-dev`; `ruff check ros2/ralmon_sim` and `ruff format --check ros2/ralmon_sim` exit 0 (host and container); `colcon build --packages-select ralmon_sim` exit 0 and `ros2 pkg prefix ralmon_sim` exit 0; `check_sim_env.sh` host exit 2, container exit 0; heading count 9; the import and forbidden-word greps print nothing; `python3 tools/check_plan.py` exit 0; core suites: host Python 3.14.4 2357 passed, ralmon-dev Python 3.12 2357 passed, Humble Python 3.10.12 2357 passed, with `ruff check`, `ruff format --check` and `mypy src/ralmon` exit 0 in all three.
