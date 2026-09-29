---
id: WS07-T01
title: "Package availability check and simulation workspace"
workstream: WS07-ros2-sim
owner: agent
status: blocked
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
