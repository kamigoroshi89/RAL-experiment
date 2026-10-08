# Package availability of the simulation stack (WS07-T01)

Record: `ros2/ralmon_sim/config/package_availability.yaml` (machine-checked by
`ros2/ralmon_sim/test/test_package_availability.py`). Checked on 2026-10-08 by the agent. Every
status, version and source URL below was read from the source named, or observed by a command whose
captured output is in section Reproduction. The task text speaks of ROS 2 Jazzy and Gazebo Harmonic;
ADR-042 (accepted 2026-10-08) replaced them by Humble and Gazebo Classic, and this document reads
the task that way.

## Host

| Fact | Value |
|---|---|
| OS | Ubuntu 26.04.1 LTS (Resolute Raccoon), kernel Linux 7.0.0-38-generic, x86_64 |
| CPU | AMD Ryzen 9 8940HX with Radeon Graphics, 16 cores, 32 threads |
| RAM | 31347192 kB (29.9 GiB) |
| GPU | NVIDIA GeForce RTX 5070 Laptop GPU (driver 580.178.04, 8151 MiB) and an AMD Raphael iGPU; not used (simulation renders on the CPU with Xvfb and Mesa llvmpipe, so a machine without a GPU runs the same route) |
| Privilege | no sudo (it asks for a password); unprivileged user namespaces restricted (`kernel.apparmor_restrict_unprivileged_userns = 1`) |
| Docker | client 29.5.0, server 29.8.0, Compose v5.1.1; the data root is under `/var/snap/docker`, and a bind mount of `/tmp` showed an empty directory in the container, so scratch files of the checks were under `outputs/` (not committed) |

The host is not a supported platform of the target distribution: REP 2000 targets ROS 2 Humble at
Ubuntu Jammy (22.04) amd64, Tier 1, and this host runs Ubuntu 26.04. The route chosen for every
step is therefore a container: `docker compose --profile ros2 run --rm ros2` (image
`ralmon-ros2:humble`, built from `docker/Dockerfile.ros2` on `ros:humble-ros-base`, digest
`sha256:860e53793ccf575e5369b5e9a19939de2bfcfb46a299954d06f54f2af54fed19` pulled on 2026-10-08;
Ubuntu 22.04.5, Python 3.10.12). The repository is mounted at `/work` and the container runs as the
host user. Image of the final run:

```
image id sha256:7c7b20dce63c78a9392d0c7e3bab83c5b2072b98273f265a0515de5dab659d7a size 4349470147 created 2026-10-08T21:38:37.946023849+02:00
```

The image holds, from the ROS apt repository: Gazebo Classic with `gazebo_ros_pkgs`,
`ros_gz_bridge` and `ros_gz_sim` (Fortress), Nav2, `tiago_simulation`, `tiago_pro_simulation`,
CycloneDDS, LTTng, `ros2trace`, `tracetools_analysis`; and an overlay built from `ros2/sim.repos`
(`tracetools` compiled against LTTng, the AWS hospital world). It replaces `ralmon-ros2:jazzy`
(ADR-031 described the Jazzy image; ADR-042 supersedes that choice). The old image is still on the
machine; it is no longer referenced and a human may remove it with `docker rmi ralmon-ros2:jazzy`.

## Verdict

Verdict: `supersede_adr_011`, with `target.ros_distro: humble`, `target.gazebo: classic` and the
fallback Fortress. ADR-042 already records this decision (accepted, decision of gab, 2026-10-08), so
no ADR is appended; the checks confirm it and found nothing that contradicts it.

Reasons, each backed by the component table:

1. The four gate components (`ros2_distro`, `gazebo`, `ros_gz_bridge`, `nav2`) are `available` for Humble with Gazebo Classic and were observed in the image by `check_sim_env.sh`.
2. The PAL simulation packages exist as ROS apt binaries for Humble only (`tiago_simulation` has no branch named jazzy), and both the TIAGo and the TIAGo Pro simulation launched with Nav2 in the image.
3. The AWS hospital world builds from its `ros2` branch and loads in Gazebo Classic 11.10.2 without porting.
4. The rule the test `test_verdict_consistent_with_components` encodes: `adopt_adr_011` needs the four gate components available with target jazzy and harmonic; the Jazzy target was not checked because ADR-042 decided against it. `supersede_adr_011` needs target humble and classic and the four available.

Adaptations from the Jazzy and Harmonic wording of the task (also in the completion note of the task file):

- Target distribution and simulator: Humble and Gazebo Classic 11; Fortress is the fallback, not Harmonic.
- The Python check of `ros2_distro` is against 3.10 (ADR-042), not 3.11; the image delivers 3.10.12.
- The ROS-apt binaries (packages.ros.org) of `ros_gz_bridge` for Humble are Fortress only: the README table of `ros_gz` (branch humble) lists Fortress for packages.ros.org and also Garden and Harmonic for Humble from packages.osrfoundation.org; Classic is not listed. The integration for Gazebo Classic is `gazebo_ros_pkgs`. The component records both and `check_sim_env.sh` observes both. The hand-over text said "Classic or Fortress" for the bridge; the README does not list Classic.
- `test_verdict_consistent_with_components` was adapted for `supersede_adr_011` (target humble and classic, the four gate components available, the superseding ADR present in `03-decisions.md`); `adopt_adr_011` is still forbidden when any gate component is unavailable. The other tests are as the task lists them, plus extra tests for the record header, the dependencies of `package.xml`, `sim.repos`, the headings and the exit code of `check_sim_env.sh`.
- Tracing on Humble needs LTTng and `tracetools` built from source (the Debian package "will not work out-of-the-box"); the overlay of the image does that.
- The PAL packages install from the ROS apt repository; the PAL developer Docker image is not used.
- The image `ralmon-ros2:jazzy` is replaced by `ralmon-ros2:humble`; `docker-compose.yml`, `docker/Dockerfile.ros2`, `docker/ros-entrypoint.sh` and `docker/README.md` follow.

## Component table

All rows verified on 2026-10-08 by the agent. "Observed" is the third column of `check_sim_env.sh` in the Humble image.

| id | status | version (source) | observed |
|---|---|---|---|
| `ros2_distro` | available | Humble Hawksbill; Ubuntu 22.04, Python 3.10.4 per REP 2000, 3.10.12 in the image ([REP 2000](https://raw.githubusercontent.com/ros-infrastructure/rep/master/rep-2000.rst)) | yes |
| `gazebo` | available | Gazebo Classic 11.10.2+dfsg-1 ([Ubuntu jammy package](https://packages.ubuntu.com/jammy/gazebo)); Fortress fallback `ign gazebo --versions` 6.18.0, no Fortress simulation launched | yes |
| `ros_gz_bridge` | available | `ros_gz_bridge` 0.244.26-1 for Fortress and `gazebo_ros_pkgs` 3.9.0-1 for Classic ([rosdistro humble](https://raw.githubusercontent.com/ros/rosdistro/master/humble/distribution.yaml), [ros_gz README](https://raw.githubusercontent.com/gazebosim/ros_gz/humble/README.md)) | yes |
| `nav2` | available | 1.1.20-1 ([rosdistro humble](https://raw.githubusercontent.com/ros/rosdistro/master/humble/distribution.yaml)) | yes |
| `robot_sim_pal` | available, variant `tiago_pro` | `tiago_pro_simulation` 1.19.0-1 and `tiago_simulation` 4.13.0-1, branch humble-devel ([rosdistro humble](https://raw.githubusercontent.com/ros/rosdistro/master/humble/distribution.yaml)) | yes |
| `hospital_world` | available, decision `use_ros2_branch` | `aws_robomaker_hospital_world` 1.0.0, commit 7161eb8, archived upstream ([repository](https://github.com/aws-robotics/aws-robomaker-hospital-world/tree/ros2)) | yes |
| `human_sim` | partial | HuNavSim, README "Tested in ROS2 Humble", wrappers for Gazebo Classic 11 and Fortress; no binary package, no build attempted ([repository](https://github.com/robotics-upo/hunav_sim)) | no |
| `ros2_tracing` | available | ros2_tracing 4.1.2-1, `tracetools_analysis` 3.0.0-4, LTTng 2.13.4; `tracetools` built from commit 3c159b3 ([rosdistro humble](https://raw.githubusercontent.com/ros/rosdistro/master/humble/distribution.yaml)) | yes |
| `tc_netem` | partial | iproute2 5.15.0-1ubuntu2.2, jammy-updates, the version in the image; the jammy release pocket has 5.15.0-1ubuntu2 ([Ubuntu jammy-updates package](https://packages.ubuntu.com/jammy-updates/iproute2)); works in a container with `NET_ADMIN`, not on the host (no privilege) | yes (`tc` present) |
| `onboard_computer` | partial | TIAGo Pro datasheet: Intel i5, 16 GB RAM, 512 GB SSD; cores not stated ([datasheet](https://pal-robotics.com/wp-content/uploads/2025/05/2025-Datasheet-TIAGo-Pro.pdf)) | n/a |
| `isaac_sim` | not_evaluated | by design (analisi section 5.2: optional, GPU-expensive, advised against for a small group) | n/a |

## Reproduction

Ordered commands, run from the repository root on 2026-10-08. Outputs are copied from the saved
files of the checks; output lines are cut at 150 characters. The probe scripts were run from
`outputs/ws07-t01/` (not committed) and their full text is reproduced below, so the steps can be
repeated by saving each block to that directory.

Reproducibility limits (an item for WS13, see Open items for a human): the base image is the
floating tag `ros:humble-ros-base` (the digest of 2026-10-08 is recorded in section Host), the apt
and pip packages installed by `docker/Dockerfile.ros2` are not pinned (the resolved ROS versions are
printed in step 2), and the 44 Gazebo Fuel models of the hospital world are downloaded from a hosted
server at build time without pins or checksums, so a later build can differ or fail.

### Step 1. Image and tool versions

```
docker compose --profile ros2 build ros2
docker compose --profile ros2 run --rm ros2 bash
```

Every probe below is a script saved under `outputs/ws07-t01/` (not committed) and run in a
throw-away container with the pattern

```
docker run --rm -u "$(id -u):$(id -g)" -v "$PWD/outputs/ws07-t01:/probe" ralmon-ros2:humble bash /probe/<script>
```

`stack_probe.sh`:

```
set -u
echo "== host of this check"; grep PRETTY_NAME /etc/os-release; python3 --version; echo "ROS_DISTRO=$ROS_DISTRO"; echo "RMW_IMPLEMENTATION=${RMW_IMPLEMENTATION:-unset}"
echo "== dpkg versions (ROS apt repository, packages.ros.org)"
for p in ros-humble-gazebo-ros-pkgs ros-humble-gazebo-ros ros-humble-ros-gz-bridge ros-humble-ros-gz-sim ros-humble-navigation2 ros-humble-nav2-bringup ros-humble-nav2-msgs ros-humble-tiago-simulation ros-humble-tiago-gazebo ros-humble-tiago-pro-simulation ros-humble-tiago-pro-gazebo ros-humble-pal-gazebo-worlds ros-humble-tracetools ros-humble-ros2trace ros-humble-tracetools-analysis ros-humble-rmw-cyclonedds-cpp gazebo lttng-tools; do dpkg-query -W -f='${Package} ${Version}\n' "$p" 2>/dev/null || echo "$p NOT INSTALLED"; done
echo "== gazebo --version"; gazebo --version 2>&1 | head -n 3
echo "== ign gazebo --versions (Fortress, fallback)"; ign gazebo --versions 2>&1 | head -n 2
echo "== ros2 pkg prefix"
for p in gazebo_ros ros_gz_bridge ros_gz_sim nav2_bringup tiago_gazebo tiago_pro_gazebo pal_gazebo_worlds aws_robomaker_hospital_world tracetools hunav_agent_manager; do printf '%s: ' "$p"; ros2 pkg prefix "$p" 2>&1 | head -n 1; done
echo "== ros2 launch --show-args (argument 'gazebo_version', 'arm_type')"
ros2 launch tiago_gazebo tiago_gazebo.launch.py --show-args 2>&1 | grep -A3 -E "^ +'(gazebo_version|arm_type|is_public_sim|navigation)'" | head -n 20
ros2 launch tiago_pro_gazebo tiago_pro_gazebo.launch.py --show-args 2>&1 | grep -A3 -E "^ +'(gazebo_version|arm_type_right|navigation)'" | head -n 14
echo "== hospital world files"; ls "$(ros2 pkg prefix aws_robomaker_hospital_world)/share/aws_robomaker_hospital_world" ; ls "$(ros2 pkg prefix aws_robomaker_hospital_world)/share/aws_robomaker_hospital_world/worlds" "$(ros2 pkg prefix aws_robomaker_hospital_world)/share/aws_robomaker_hospital_world/launch"; echo "fuel_models: $(ls "$(ros2 pkg prefix aws_robomaker_hospital_world)/share/aws_robomaker_hospital_world/fuel_models" | wc -l) directories; models: $(ls "$(ros2 pkg prefix aws_robomaker_hospital_world)/share/aws_robomaker_hospital_world/models" | wc -l); size: $(du -sh "$(ros2 pkg prefix aws_robomaker_hospital_world)/share/aws_robomaker_hospital_world" | cut -f1)"
```

Output (first lines):

```
== host of this check
PRETTY_NAME="Ubuntu 22.04.5 LTS"
Python 3.10.12
ROS_DISTRO=humble
RMW_IMPLEMENTATION=unset
```

### Step 2. Package versions read from the apt index and the ROS 2 environment

Output of the same script (the `ign gazebo --versions` line is the Fortress fallback):

```
== dpkg versions (ROS apt repository, packages.ros.org)
ros-humble-gazebo-ros-pkgs 3.9.0-1jammy.20260908.002217
ros-humble-gazebo-ros 3.9.0-1jammy.20260907.222900
ros-humble-ros-gz-bridge 0.244.26-1jammy.20260907.225444
ros-humble-ros-gz-sim 0.244.26-1jammy.20260907.235058
ros-humble-navigation2 1.1.20-1jammy.20260908.015443
ros-humble-nav2-bringup 1.1.20-1jammy.20260908.021125
ros-humble-nav2-msgs 1.1.20-1jammy.20260907.223327
ros-humble-tiago-simulation 4.13.0-1jammy.20260909.013002
ros-humble-tiago-gazebo 4.13.0-1jammy.20260909.012114
ros-humble-tiago-pro-simulation 1.19.0-1jammy.20260909.013841
ros-humble-tiago-pro-gazebo 1.19.0-1jammy.20260909.013642
ros-humble-pal-gazebo-worlds 4.16.0-1jammy.20260907.222326
ros-humble-tracetools 4.1.2-1jammy.20260907.192206
ros-humble-ros2trace 4.1.2-1jammy.20260907.222309
ros-humble-tracetools-analysis 3.0.0-4jammy.20260304.195619
ros-humble-rmw-cyclonedds-cpp 1.3.5-1jammy.20260907.205235
gazebo 11.10.2+dfsg-1
lttng-tools 2.13.4-1build1
== gazebo --version
Gazebo multi-robot simulator, version 11.10.2
Copyright (C) 2012 Open Source Robotics Foundation.
Released under the Apache 2 License.
== ign gazebo --versions (Fortress, fallback)
6.18.0
== ros2 pkg prefix
gazebo_ros: /opt/ros/humble
ros_gz_bridge: /opt/ros/humble
ros_gz_sim: /opt/ros/humble
nav2_bringup: /opt/ros/humble
tiago_gazebo: /opt/ros/humble
tiago_pro_gazebo: /opt/ros/humble
pal_gazebo_worlds: /opt/ros/humble
aws_robomaker_hospital_world: /opt/ralmon_overlay/install
tracetools: /opt/ralmon_overlay/install
hunav_agent_manager: Package not found
== ros2 launch --show-args (argument 'gazebo_version', 'arm_type')
    'arm_type':
        Arm type. Valid choices are: ['tiago-arm', 'no-arm']
        (default: 'tiago-arm')

--
    'navigation':
        Specify if launching Navigation2. Valid choices are: ['True', 'False']
        (default: 'False')

--
    'is_public_sim':
        Enable public simulation. Valid choices are: ['True', 'False']
        (default: 'False')

--
    'gazebo_version':
        Version of Gazebo to be used, 'classic' or 'gazebo'. Valid choices are: ['gazebo', 'classic']
        (default: 'classic')
    'arm_type_right':
        Arm type right. Valid choices are: ['tiago-pro', 'tiago-pro-s', 'no-arm']
        (default: 'tiago-pro')

--
    'navigation':
        Specify if launching Navigation2. Valid choices are: ['True', 'False']
        (default: 'False')

--
    'gazebo_version':
        Version of Gazebo to be used, 'classic' or 'gazebo'. Valid choices are: ['gazebo', 'classic']
        (default: 'classic')
== hospital world files
cmake
environment
fuel_models
hook
launch
local_setup.bash
local_setup.dsv
local_setup.sh
local_setup.zsh
models
package.bash
package.dsv
package.ps1
package.sh
package.xml
package.zsh
worlds
/opt/ralmon_overlay/install/share/aws_robomaker_hospital_world/launch:
hospital.launch.py
view_hospital.launch.py

/opt/ralmon_overlay/install/share/aws_robomaker_hospital_world/worlds:
hospital.world
hospital_three_floors.world
hospital_two_floors.world
fuel_models: 44 directories; models: 37; size: 132M
```

### Step 3. The core suite under Python 3.10 (ADR-042 migration)

`pyproject.toml` says `requires-python = ">=3.10"` and `tests/test_toolchain.py` pins `>=3.10` and
falls back to `tomli` where `tomllib` does not exist (Python 3.10). Versions in the image, then the
four commands of the lint and test services:

```
Python 3.10.12
numpy 1.26.4 PyYAML 5.4.1 pytest 6.2.5 hypothesis 6.168.5
ruff 0.16.10
mypy 2.4.0 (compiled: yes)
pandas 1.3.5
```

```
== pytest -q
........................................................................ [ 97%]
.....................................................                    [100%]
2357 passed in 59.88s
exit=0
== ruff check src tests
All checks passed!
exit=0
== ruff format --check src tests
69 files already formatted
exit=0
== mypy src/ralmon
Success: no issues found in 39 source files
exit=0
```

On the system numpy of Humble (1.21.5, REP 2000) the same suite gives `1 failed, 2356 passed`
(`test_foreign_objects_with_unreadable_fields_are_named_errors`: the core does not raise
`C1InjectionError`) and `mypy src/ralmon` reports 5 `no-untyped-call` errors. Both are numpy
effects, not Python 3.10 effects. Bisection in throw-away containers (pip `--target` under `/tmp`,
Python 3.10.12, script `numpy_bisect.sh` below, output `numpy_bisect.out`): the test fails with numpy 1.21.6,
1.22.4, 1.23.5 and 1.24.4 and passes with 1.25.0, 1.25.1, 1.25.2, 1.26.4 (and 2.2.6, earlier run);
mypy reports the 5 errors with 1.21.5 and 1.21.6 and passes with 1.22.4, 1.25.0 and 1.25.2. The patch
versions between those (for example 1.24.0 to 1.24.3) were not run, so the floor for the test is
"about 1.25" (first passing version tried: 1.25.0). The image installs numpy `<2` (1.26.4), because
numpy 2.2.6 breaks the import of the apt pandas 1.3.5 that `tracetools_analysis` uses.

`numpy_bisect.sh`:

```
# Throw-away container, as the host user; numpy versions are installed with pip --target under /tmp
# (never into the image) and put first on PYTHONPATH. Python 3.10.12.
set -u
cd /work
for v in 1.21.6 1.22.4 1.23.5 1.24.4 1.25.0 1.25.1 1.25.2 1.26.4; do
  d=/tmp/np_$v
  python3 -m pip install -q --no-deps --target "$d" "numpy==$v" >/dev/null 2>&1 || { echo "numpy $v: pip install failed"; continue; }
  got=$(PYTHONPATH=$d:/work/src python3 -c "import numpy; print(numpy.__version__)")
  t=$(PYTHONPATH=$d:/work/src pytest -q -p no:cacheprovider tests/benchmark/test_c1_confounders.py -k unreadable_fields 2>&1 | tail -n 1)
  echo "numpy $got: test -> $t"
done
echo "== mypy src/ralmon"
for v in 1.21.6 1.22.4 1.25.0 1.25.2; do
  d=/tmp/np_$v
  m=$(PYTHONPATH=$d:/work/src mypy src/ralmon 2>&1 | tail -n 1)
  echo "numpy $v: mypy -> $m"
done
```

Output:

```
numpy 1.21.6: test -> 1 failed, 164 deselected, 2 warnings in 0.55s
numpy 1.22.4: test -> 1 failed, 164 deselected, 2 warnings in 0.71s
numpy 1.23.5: test -> 1 failed, 164 deselected, 2 warnings in 0.78s
numpy 1.24.4: test -> 1 failed, 164 deselected, 2 warnings in 0.72s
numpy 1.25.0: test -> 1 passed, 164 deselected in 2.37s
numpy 1.25.1: test -> 1 passed, 164 deselected in 2.34s
numpy 1.25.2: test -> 1 passed, 164 deselected in 2.39s
numpy 1.26.4: test -> 1 passed, 164 deselected in 2.34s
== mypy src/ralmon
numpy 1.21.6: mypy -> Found 5 errors in 3 files (checked 39 source files)
numpy 1.22.4: mypy -> Success: no issues found in 39 source files
numpy 1.25.0: mypy -> Success: no issues found in 39 source files
numpy 1.25.2: mypy -> Success: no issues found in 39 source files
```

### Step 4. Workspace build

```
cd ros2 && colcon build --packages-select ralmon_sim
source install/setup.bash && ros2 pkg prefix ralmon_sim
```

```
Starting >>> ralmon_sim
--- stderr: ralmon_sim
warning: build_py: byte-compiling is disabled, skipping.

warning: install_lib: byte-compiling is disabled, skipping.

---
Finished <<< ralmon_sim [0.47s]

Summary: 1 package finished [0.58s]
  1 package had stderr output: ralmon_sim
colcon build exit=0
/work/ros2/install/ralmon_sim
ros2 pkg prefix exit=0
ralmon_sim deadline_logger_node;ralmon_sim deadline_prediction;ralmon_sim fault_injector_node;ralmon_sim measure_run;ralmon_sim robot_task_node;ralmon
ralmon_sim	ralmon_sim	(ros.ament_python)
/work/ros2/build:
COLCON_IGNORE
ralmon_sim

/work/ros2/install:
COLCON_IGNORE
_local_setup_util_ps1.py
_local_setup_util_sh.py
Package not found
Package not found
```

`package.xml` declares `ralmon_sim_msgs` and `ralmon_ros` as `exec_depend`; neither package exists
yet (WS07-T03 and WS05-T09), and the build above succeeded without them, so an `exec_depend` on a
package outside the workspace does not stop `colcon build --packages-select ralmon_sim`.
`ros2 pkg prefix` prints `Package not found` for both until those tasks add them. (Do not put a double
hyphen in an XML comment of `package.xml`: a first version did, colcon then treated the package as
plain `python` and `ros2 pkg prefix` failed; the output above shows the type `ros.ament_python`.)

### Step 5. Environment check

```
$ bash ros2/ralmon_sim/scripts/check_sim_env.sh   # host shell, no ROS 2 sourced
ROS 2 environment not sourced
exit=2
```

```
$ docker compose --profile ros2 run --rm ros2 bash ros2/ralmon_sim/scripts/check_sim_env.sh   # Humble environment sourced
ros2_distro available yes
gazebo available yes
ros_gz_bridge available yes
nav2 available yes
robot_sim_pal available yes
hospital_world available yes
human_sim partial no
ros2_tracing available yes
tc_netem partial yes
onboard_computer partial n/a
isaac_sim not_evaluated n/a
# info: import ralmon works (informational only)
# info: ROS_DISTRO=humble python=Python 3.10.12
exit=0
```

The exit code is 0 exactly when every component recorded as `available` is observed: with
`human_sim` temporarily recorded as `available` in a copy of the record, the script printed
`human_sim available no`, `# 1 component(s) recorded as available are not observed` and exited 1. A component that cannot be
observed on a machine (`onboard_computer`, `isaac_sim`) prints `n/a`; recorded as `available` it
counts as not observed, so the script exits 1 (container run with `isaac_sim` set to `available` in a
scratch copy: `isaac_sim available n/a`, `# 1 component(s) recorded as available are not observed (no or n/a)`,
exit 1). A record that cannot be read gives one line and exit 3 (container run with the content
`components: [unclosed`: `cannot read .../config/package_availability.yaml: ParserError: while parsing a flow sequence`,
exit 3, no traceback). The tests `test_check_script_exits_*` run the same paths on a scratch copy with stub
executables, so they do not depend on the machine.

### Step 6. Tracing (LTTng and ros2_tracing, user-space, uid 1000)

`trace_probe.sh`, run as uid 1000 with `HOME=/tmp`:

```
set -u
echo "== id: $(id -u):$(id -g)  HOME=$HOME"
echo "== ros2 run tracetools status"; ros2 run tracetools status; echo "exit=$?"
echo "== lttng --version"; lttng --version
echo "== python3 -c import lttng, babeltrace"; python3 -c "import lttng, babeltrace; print('lttng and babeltrace python bindings import OK')"
echo "== tracetools_analysis import"; python3 -c "import tracetools_analysis, pandas; print('tracetools_analysis', pandas.__version__)" 2>&1 | tail -n 2
rm -rf /tmp/tracing
echo "== ros2 trace (user-space session, no root): Enter starts, Enter stops"
( sleep 6; echo; sleep 12; echo ) | ros2 trace -s ws07probe -p /tmp/tracing -u 'ros2:*' 2>&1 | tail -n 8 &
sleep 10
timeout 6 ros2 topic pub -r 20 /ws07probe std_msgs/msg/String "{data: hi}" >/dev/null 2>&1
wait
echo "== trace dir"; find /tmp/tracing | head -n 20; du -sh /tmp/tracing
python3 - <<'PY'
import collections
from tracetools_read.trace import get_trace_events, is_trace_directory
path = "/tmp/tracing/ws07probe"
print("is_trace_directory:", is_trace_directory(path))
events = get_trace_events(path)
names = collections.Counter(e["_name"] for e in events)
print("events read with tracetools_read:", sum(names.values()))
for name, count in names.most_common(6):
    print(" ", count, name)
PY
```

Output (the index files of the trace directory are not listed):

```
== id: 1000:1000  HOME=/tmp
== ros2 run tracetools status
Tracing enabled
exit=0
== lttng --version
lttng (LTTng Trace Control) 2.13.4 - Nordicité
== python3 -c import lttng, babeltrace
lttng and babeltrace python bindings import OK
== tracetools_analysis import
tracetools_analysis 1.3.5
== ros2 trace (user-space session, no root): Enter starts, Enter stops
UST tracing enabled (1 events)
kernel tracing disabled
context (3 names)
writing tracing session to: /tmp/tracing/ws07probe
press enter to start...press enter to stop...stopping & destroying tracing session
== trace dir
/tmp/tracing
/tmp/tracing/ws07probe
/tmp/tracing/ws07probe/ust
/tmp/tracing/ws07probe/ust/uid
/tmp/tracing/ws07probe/ust/uid/1000
/tmp/tracing/ws07probe/ust/uid/1000/64-bit
/tmp/tracing/ws07probe/ust/uid/1000/64-bit/ros2_12
/tmp/tracing/ws07probe/ust/uid/1000/64-bit/index
300K	/tmp/tracing
is_trace_directory: True
events read with tracetools_read: 240
  114 ros2:rmw_publish
  106 ros2:rcl_publish
  8 ros2:rmw_take
  4 ros2:rmw_publisher_init
  3 ros2:rcl_publisher_init
  2 ros2:rcl_timer_init
```

Kernel tracing needs root and `lttng-modules-dkms`; it was not tried.

### Step 7. Gazebo Classic and the hospital world, headless

```
gzserver --verbose -s libgazebo_ros_init.so -s libgazebo_ros_factory.so \
    $(ros2 pkg prefix aws_robomaker_hospital_world)/share/aws_robomaker_hospital_world/worlds/hospital.world
```

`gz_smoke.sh`, run as root in a throw-away container (`-u 0:0 -e HOME=/tmp`, wrapped in `timeout 400`):

```
set -u
W="$(ros2 pkg prefix aws_robomaker_hospital_world)/share/aws_robomaker_hospital_world/worlds/hospital.world"
export GAZEBO_MODEL_PATH="$GAZEBO_MODEL_PATH:$(ros2 pkg prefix aws_robomaker_hospital_world)/share/aws_robomaker_hospital_world/models:$(ros2 pkg prefix aws_robomaker_hospital_world)/share/aws_robomaker_hospital_world/fuel_models"
echo "GAZEBO_MODEL_PATH=$GAZEBO_MODEL_PATH" | cut -c1-300
START=$(date +%s)
timeout 200 gzserver --verbose -s libgazebo_ros_init.so -s libgazebo_ros_factory.so "$W" > /tmp/gzserver.log 2>&1 &
GP=$!
echo "== waiting for the first /clock message (up to 150 s)"
timeout 150 ros2 topic echo /clock --once 2>&1 | head -n 6
echo "first /clock after $(( $(date +%s) - START )) s"
echo "== services"; ros2 service list 2>&1 | grep -E "spawn_entity|get_model_list|pause_physics" | head -n 4
echo "== models in world"; ros2 service call /get_model_list gazebo_msgs/srv/GetModelList 2>&1 | grep -o "model_names=\[.*\]" | tr "," "\n" | wc -l
pkill -9 gzserver; sleep 1
echo "== gzserver log (ANSI stripped, errors and warnings)"; sed 's/\x1b\[[0-9;]*m//g' /tmp/gzserver.log | grep -E "\[Err\]|\[Wrn\]|terminate|core" | sort | uniq -c | sort -rn | head -n 12 | cut -c1-220
```

Output:

```
GAZEBO_MODEL_PATH=/opt/ros/humble/share/pal_gazebo_worlds/models:/opt/ralmon_overlay/install/share/aws_robomaker_hospital_world/models:/opt/ralmon_ove
== waiting for the first /clock message (up to 150 s)
clock:
  sec: 0
  nanosec: 100000000
---
first /clock after 2 s
== services
/get_model_list
/pause_physics
/spawn_entity
/unpause_physics
== models in world
182
/probe/gz_smoke.sh: line 13:    37 Killed                  timeout 200 gzserver --verbose -s libgazebo_ros_init.so -s libgazebo_ros_factory.so "$W" >
== gzserver log (ANSI stripped, errors and warnings)
     14 [Wrn] [ColladaLoader.cc:1547] Unable to add material[]
      1 [Wrn] [gazebo_ros_init.cpp:178]
      1 [Wrn] [RenderEngine.cc:89] Unable to create X window. Rendering will be disabled
      1 [Wrn] [RenderEngine.cc:292] Cannot initialize render engine since render path type is NONE. Ignore this warning ifrendering has been turned of
      1 [Wrn] [OBJLoader.cc:79] Both `d` and `Tr` parameters defined for "IVStand". Use the value of `d` for dissolve (line 8 in .mtl.)
      1 [Wrn] [OBJLoader.cc:79] Both `d` and `Tr` parameters defined for "Chair". Use the value of `d` for dissolve (line 8 in .mtl.)
      1 [Err] [RenderEngine.cc:749] Can't open display:
      1 [Err] [OpenAL.cc:84] Unable to open audio device[default]
```

The same run as uid 1000 (the host user) gave the same `/clock` and services (saved as
`gz_smoke_uid1000.out`).

### Step 8. PAL TIAGo and TIAGo Pro simulation with Nav2, headless with Xvfb

In a throw-away root container (`docker run --rm -u 0:0 ... ralmon-ros2:humble`), `apt-get install
xvfb libgl1-mesa-dri mesa-utils`, `Xvfb :99 -screen 0 1280x1024x24 +extension GLX +render -noreset`,
`DISPLAY=:99 LIBGL_ALWAYS_SOFTWARE=1`, `RMW_IMPLEMENTATION=rmw_cyclonedds_cpp`. `tiago_xvfb_smoke.sh`
(argument `tiago`; with the argument `tiago_pro` it launches `tiago_pro_gazebo`):

```
set -u
apt-get update -qq >/dev/null 2>&1 && apt-get install -y -qq --no-install-recommends xvfb libgl1-mesa-dri mesa-utils >/dev/null 2>&1; echo "xvfb installed: $(command -v Xvfb)"
export HOME=/tmp
Xvfb :99 -screen 0 1280x1024x24 +extension GLX +render -noreset > /tmp/xvfb.log 2>&1 &
sleep 3
export DISPLAY=:99 LIBGL_ALWAYS_SOFTWARE=1
echo "== glxinfo renderer"; glxinfo 2>/dev/null | grep -E "OpenGL renderer|OpenGL version" | head -n 2
VARIANT="${1:-tiago}"
if [ "$VARIANT" = tiago_pro ]; then
  LAUNCH="ros2 launch tiago_pro_gazebo tiago_pro_gazebo.launch.py is_public_sim:=True gzclient:=False navigation:=True"
else
  LAUNCH="ros2 launch tiago_gazebo tiago_gazebo.launch.py is_public_sim:=True gzclient:=False navigation:=True"
fi
echo "== $LAUNCH"
$LAUNCH > /tmp/launch_$VARIANT.log 2>&1 &
for i in $(seq 1 30); do
  sleep 6
  S=$(ros2 topic list 2>/dev/null | grep -cE "^/scan")
  echo "t=$((i*6))s scan_topics=$S"
  if [ "$S" -ge 1 ] && [ "$i" -ge 5 ]; then break; fi
done
echo "== controllers"; timeout 30 ros2 control list_controllers 2>&1 | sed 's/\x1b\[[0-9;]*m//g' | head -n 10
echo "== scan topics"; ros2 topic list 2>&1 | grep -E "scan|map|amcl|navigate|plan" | head -n 10
echo "== one scan message (header only)"; timeout 20 ros2 topic echo --once --field header /scan_raw 2>&1 | head -n 6
echo "== nav2 lifecycle nodes"; ros2 lifecycle nodes 2>&1 | head -n 12
echo "== nav2 launch errors (ANSI stripped)"; sed 's/\x1b\[[0-9;]*m//g' /tmp/launch_$VARIANT.log | grep -iE "\[ERROR\]|process has died|Segmentation|failed" | head -n 8 | cut -c1-240
pkill -9 -f gzserver; pkill -9 -f "ros2 launch"; sleep 1
```

Output for TIAGo:

```
xvfb installed: /usr/bin/Xvfb
== glxinfo renderer
OpenGL renderer string: llvmpipe (LLVM 15.0.7, 256 bits)
OpenGL version string: 4.5 (Compatibility Profile) Mesa 23.2.1-1ubuntu3.1~22.04.4
== ros2 launch tiago_gazebo tiago_gazebo.launch.py is_public_sim:=True gzclient:=False navigation:=True
t=6s scan_topics=2
t=12s scan_topics=2
t=18s scan_topics=2
t=24s scan_topics=2
t=30s scan_topics=2
== controllers
ft_sensor_controller    force_torque_sensor_broadcaster/ForceTorqueSensorBroadcaster  active
joint_state_broadcaster joint_state_broadcaster/JointStateBroadcaster                 active
arm_controller          joint_trajectory_controller/JointTrajectoryController         active
gripper_controller      joint_trajectory_controller/JointTrajectoryController         active
torso_controller        joint_trajectory_controller/JointTrajectoryController         active
head_controller         joint_trajectory_controller/JointTrajectoryController         active
mobile_base_controller  diff_drive_controller/DiffDriveController                     active
== scan topics
/amcl/transition_event
/amcl_pose
/display_planned_path
/downsampled_costmap
/downsampled_costmap_updates
/global_costmap/costmap
/global_costmap/costmap_raw
/global_costmap/costmap_updates
/global_costmap/footprint
/global_costmap/global_costmap/transition_event
== one scan message (header only)
stamp:
  sec: 30
  nanosec: 821000000
frame_id: base_laser_link
---
== nav2 lifecycle nodes
/amcl
/behavior_server
/bt_navigator
/controller_server
/global_costmap/global_costmap
/local_costmap/local_costmap
/map_server
/planner_server
/play_motion2_executor
/play_motion2_mgr
/smoother_server
/velocity_smoother
```

For the TIAGo Pro, `tiago_pro_probe2.sh` (the same Xvfb set-up, `rviz:=False moveit:=False`, queried 100 s after the launch):

```
set -u
apt-get update -qq >/dev/null 2>&1 && apt-get install -y -qq --no-install-recommends xvfb libgl1-mesa-dri mesa-utils >/dev/null 2>&1
export HOME=/tmp
Xvfb :99 -screen 0 1280x1024x24 +extension GLX +render -noreset > /tmp/xvfb.log 2>&1 &
sleep 3
export DISPLAY=:99 LIBGL_ALWAYS_SOFTWARE=1
ros2 launch tiago_pro_gazebo tiago_pro_gazebo.launch.py is_public_sim:=True gzclient:=False navigation:=True rviz:=False moveit:=False > /tmp/launch_pro.log 2>&1 &
sleep 100
echo "== controllers (t=100s)"; timeout 30 ros2 control list_controllers 2>&1 | sed 's/\x1b\[[0-9;]*m//g'
echo "== controller-related lines in the launch log"; sed 's/\x1b\[[0-9;]*m//g' /tmp/launch_pro.log | grep -iE "spawner|controller" | grep -iE "base|omni|mobile|fail|error|unable" | head -n 12 | cut -c1-220
echo "== topics with cmd_vel / odom / scan"; ros2 topic list | grep -E "cmd_vel|odom|scan" | head
echo "== lifecycle nodes + states (nav2)"; for n in /amcl /controller_server /planner_server /bt_navigator; do printf '%s ' $n; ros2 lifecycle get $n 2>&1 | head -n 1; done
pkill -9 -f gzserver; pkill -9 -f "ros2 launch"; sleep 1
```

Output:

```
== controllers (t=100s)
head_controller          joint_trajectory_controller/JointTrajectoryController  active
joint_state_broadcaster  joint_state_broadcaster/JointStateBroadcaster          active
torso_controller         joint_trajectory_controller/JointTrajectoryController  active
arm_left_controller      joint_trajectory_controller/JointTrajectoryController  active
arm_right_controller     joint_trajectory_controller/JointTrajectoryController  active
gripper_left_controller  joint_trajectory_controller/JointTrajectoryController  active
gripper_right_controller joint_trajectory_controller/JointTrajectoryController  active
== controller-related lines in the launch log
[controller_server-2] [INFO] [1791489952.804673124] [controller_server]: Using critic "BaseObstacle" (dwb_critics::BaseObstacleCritic)
[gzserver-1] [INFO] [1791489954.575250106] [gazebo_ros_planar_move]: Subscribed to [/mobile_base_controller/cmd_vel_unstamped]
[gzserver-1] [INFO] [1791489954.576084539] [gazebo_ros_planar_move]: Advertise odometry on [/mobile_base_controller/odom]
== topics with cmd_vel / odom / scan
/cmd_vel
/cmd_vel_nav
/input_joy/cmd_vel
/mobile_base_controller/cmd_vel_unstamped
/mobile_base_controller/odom
/scan_front_raw
/scan_rear_raw
== lifecycle nodes + states (nav2)
/amcl active [3]
/controller_server active [3]
/planner_server active [3]
/bt_navigator active [3]
/probe/tiago_pro_probe2.sh: line 13:   390 Killed                  ros2 launch tiago_pro_gazebo tiago_pro_gazebo.launch.py is_public_sim:=True gzclien
```

Without a display the same TIAGo launch brought up the controllers but no laser scan topic (first
smoke run, not saved). No robot motion, navigation goal or hospital world with the robot was run
here.

### Step 9. tc netem

On the host (read-only checks and a namespace test that did not touch the host network):

```
$ command -v tc            -> /usr/sbin/tc   (iproute2 6.19.0)
$ lsmod | grep netem       -> sch_netem (loaded by the container runs of this step)
$ sudo -n true             -> sudo: interactive authentication is required
$ unshare -Urn tc qdisc add dev lo root netem loss 10%
unshare: write failed /proc/self/uid_map: Operation not permitted
```

In a throw-away container as root with `--cap-add NET_ADMIN` (its own network namespace; the host
interfaces are not touched), started with `docker run --rm --cap-add NET_ADMIN -u root -e HOME=/tmp -v "$PWD:/work"
-w /work ralmon-ros2:humble bash /work/outputs/ws07-t01/netem_matrix.sh`. The probe is
`ros2/ralmon_sim/scripts/netem_probe.py` (in the repository); `netem_matrix.sh` below also writes the
Fast DDS profile that forces UDP:

```
# Runs inside a throw-away root container with --cap-add NET_ADMIN (own network namespace).
set -u
PROBE=/work/ros2/ralmon_sim/scripts/netem_probe.py
echo "== kernel: $(uname -r); tc: $(tc -V)"
echo "== interfaces"; ip -br addr | cut -c1-100
echo "== modprobe-free check: add and show a netem qdisc on lo"
tc qdisc add dev lo root netem loss 30% 2>&1; echo "tc add exit=$?"; tc qdisc show dev lo; tc qdisc del dev lo root 2>&1; echo "tc del exit=$?"
run() { # rmw dev loss [fastdds profile]
  local rmw="$1" dev="$2" loss="$3" prof="${4:-}"
  export RMW_IMPLEMENTATION="$rmw" ROS_DOMAIN_ID=77
  if [ -n "$prof" ]; then export FASTRTPS_DEFAULT_PROFILES_FILE="$prof"; else unset FASTRTPS_DEFAULT_PROFILES_FILE; fi
  if [ "$dev" != none ]; then tc qdisc add dev "$dev" root netem loss "$loss" >/dev/null 2>&1 || echo "netem add failed on $dev"; fi
  python3 "$PROBE" sub --seconds 18 > /tmp/sub.out 2>&1 &
  local sp=$!
  sleep 3
  python3 "$PROBE" pub --seconds 10 --rate 100 > /tmp/pub.out 2>&1
  wait "$sp"
  if [ "$dev" != none ]; then tc qdisc del dev "$dev" root >/dev/null 2>&1; fi
  echo "rmw=$rmw netem=$dev($loss) profile=${prof:-default} :: $(tr '\n' ' ' < /tmp/pub.out) $(tr '\n' ' ' < /tmp/sub.out)"
}
cat > /tmp/fastdds_udp_only.xml <<'XML'
<?xml version="1.0" encoding="UTF-8" ?>
<profiles xmlns="http://www.eprosima.com/XMLSchemas/fastRTPS_Profiles">
  <transport_descriptors>
    <transport_descriptor>
      <transport_id>udp_only</transport_id>
      <type>UDPv4</type>
    </transport_descriptor>
  </transport_descriptors>
  <participant profile_name="udp_only_participant" is_default_profile="true">
    <rtps>
      <useBuiltinTransports>false</useBuiltinTransports>
      <userTransports><transport_id>udp_only</transport_id></userTransports>
    </rtps>
  </participant>
</profiles>
XML
for rmw in rmw_cyclonedds_cpp rmw_fastrtps_cpp; do
  run "$rmw" none 0%
  run "$rmw" lo 30%
  run "$rmw" eth0 30%
done
run rmw_fastrtps_cpp lo 30% /tmp/fastdds_udp_only.xml
```

The profile is used with `FASTRTPS_DEFAULT_PROFILES_FILE`. Each row starts a subscriber, waits 3 s, publishes
1000 best-effort messages at 100 Hz and counts what arrives; `tc qdisc add dev <dev> root netem
loss 30%` is added before and deleted after. Two runs (the first on the previous build of the
image, same apt and overlay layers):

Run 1:

```
== kernel: 7.0.0-38-generic; tc: tc utility, iproute2-5.15.0, libbpf 0.5.0
== interfaces
lo               UNKNOWN        127.0.0.1/8 ::1/128
eth0@if72        UP             172.17.0.3/16
== modprobe-free check: add and show a netem qdisc on lo
tc add exit=0
qdisc netem 8001: root refcnt 2 limit 1000 loss 30%
tc del exit=0
rmw=rmw_cyclonedds_cpp netem=none(0%) profile=default :: pub matched_subscribers=1 sent=1000  sub received=1000
rmw=rmw_cyclonedds_cpp netem=lo(30%) profile=default :: pub matched_subscribers=1 sent=1000  sub received=698
rmw=rmw_cyclonedds_cpp netem=eth0(30%) profile=default :: pub matched_subscribers=1 sent=1000  sub received=1000
rmw=rmw_fastrtps_cpp netem=none(0%) profile=default :: pub matched_subscribers=1 sent=1000  sub received=1000
rmw=rmw_fastrtps_cpp netem=lo(30%) profile=default :: pub matched_subscribers=1 sent=1000  sub received=941
rmw=rmw_fastrtps_cpp netem=eth0(30%) profile=default :: pub matched_subscribers=1 sent=1000  sub received=1000
rmw=rmw_fastrtps_cpp netem=lo(30%) profile=/tmp/fastdds_udp_only.xml :: pub matched_subscribers=1 sent=1000  sub received=233
```

Run 2:

```
== kernel: 7.0.0-38-generic; tc: tc utility, iproute2-5.15.0, libbpf 0.5.0
== interfaces
lo               UNKNOWN        127.0.0.1/8 ::1/128
eth0@if164       UP             172.17.0.2/16
== modprobe-free check: add and show a netem qdisc on lo
tc add exit=0
qdisc netem 8007: root refcnt 2 limit 1000 loss 30%
tc del exit=0
rmw=rmw_cyclonedds_cpp netem=none(0%) profile=default :: pub matched_subscribers=1 sent=1000  sub received=1000
rmw=rmw_cyclonedds_cpp netem=lo(30%) profile=default :: pub matched_subscribers=1 sent=1000  sub received=704
rmw=rmw_cyclonedds_cpp netem=eth0(30%) profile=default :: pub matched_subscribers=1 sent=1000  sub received=1000
rmw=rmw_fastrtps_cpp netem=none(0%) profile=default :: pub matched_subscribers=1 sent=1000  sub received=1000
rmw=rmw_fastrtps_cpp netem=lo(30%) profile=default :: pub matched_subscribers=1 sent=1000  sub received=1000
rmw=rmw_fastrtps_cpp netem=eth0(30%) profile=default :: pub matched_subscribers=1 sent=1000  sub received=1000
rmw=rmw_fastrtps_cpp netem=lo(30%) profile=/tmp/fastdds_udp_only.xml :: pub matched_subscribers=1 sent=1000  sub received=715
```

What it proves: `tc netem` and the `sch_netem` module work on this host kernel inside a container
with `NET_ADMIN`; a same-host stream is affected by netem on `lo` and not on `eth0`; with CycloneDDS
the received fraction (69.8 % and 70.4 %) matches the nominal 30 % loss. What it does not prove: that
the host user can use netem on the host (no privilege), or how Fast DDS behaves (94.1 % and 100 %
with default transports, 23.3 % and 71.5 % with the UDP-only profile: the causes were not isolated).

### Step 10. Tests and lint of the package

Results of the Done-when commands are in the completion note of the task file
(`docs/plan/workstreams/WS07-ros2-sim/tasks/T01-sim-workspace.md`).

## Hospital world decision

Decision: `use_ros2_branch`. The `ros2` branch of `aws-robotics/aws-robomaker-hospital-world`
(commit `7161eb8448f5cba6a469da7a79ae5d660b0b7f58`, pinned in `ros2/sim.repos`) is used as it is.

| Item | Finding (source) |
|---|---|
| ROS 2 support | branch `ros2`, `ament_cmake`, `exec_depend` `gazebo_ros`, `gazebo`, `gazebo_plugins` (`package.xml` of the branch) |
| Gazebo generation of the model files | Gazebo Classic: SDF 1.6 with ODE physics; README "Supported versions of Gazebo 7.14.0+ and 9.16.0+"; no port to the new Gazebo in the repository |
| Repository state | GitHub API: archived, default branch `archive`, last push 2026-07-21, branch `ros2` last commit 2021-07-29; size 65871 KB |
| Contents when built | 3 worlds (`hospital.world`, `hospital_two_floors.world`, `hospital_three_floors.world`), 37 local models, 44 Fuel models downloaded at build time from `fuel.ignitionrobotics.org`; installed size 132 MB; `hospital.world` has 183 includes |
| Licence | `LICENSE` of the repository: "Copyright 2019 Amazon.com, Inc. or its affiliates", a permission notice without a condition to keep the notice (its text matches the MIT No Attribution licence; that identification is the agent's); `package.xml` says "Apache 2.0"; GitHub detects no licence; the licence of each Fuel model was not checked |
| Observed | built in the image (6 min, network needed for Fuel); headless Gazebo Classic loaded it, `/clock` after 2 s, services `/spawn_entity` and `/get_model_list` |

Consequences for WS07-T02: the overlay package does not add its models to `GAZEBO_MODEL_PATH` (the
variable held only `pal_gazebo_worlds/models` in the sourced image), so the launch file must set it;
the image has no display, so a headless launch with sensors needs Xvfb (step 8); the `rmf_demos`
clinic world (Humble support not checked) stays an alternative, and `procedural` is the fallback if
the archived repository or its Fuel downloads disappear.

Proposal for the human (one short phrase for the paper, not paper text): "The ward is the
`ros2` branch of the AWS RoboMaker hospital world (archived upstream), run unmodified in Gazebo
Classic 11."

## Robot variant decision

Decision: `tiago_pro` (preference order `tiago_pro`, `tiago`, `stand_in`). Both vendor simulations
install from the ROS apt repository and launch with Nav2 on the target stack, so no stand-in is
needed and the wording "TIAGo-class" is not required for the simulation.

| Item | Finding |
|---|---|
| Repositories | `pal-robotics/tiago_pro_simulation` (branches alum-devel, humble-devel, master), `pal-robotics/tiago_simulation` (branches include alum-devel, foxy-devel, galactic-devel, humble-devel; none named jazzy); `git ls-remote --heads` on 2026-10-08 |
| Releases for Humble | `tiago_pro_simulation` 1.19.0-1 (`tiago_pro_gazebo`, `tiago_pro_mujoco`), `tiago_simulation` 4.13.0-1 ([rosdistro humble](https://raw.githubusercontent.com/ros/rosdistro/master/humble/distribution.yaml)); ROS apt versions in step 2 |
| Gazebo generations | launch argument `gazebo_version` with choices `gazebo` and `classic`, default `classic` (both launch files, `--show-args`); `gazebo` is Fortress on Humble (`gz-sensors6` and `libignition-gazebo6` dependencies) |
| Arm simulated | yes: `arm_type_right` and `arm_type_left` (TIAGo Pro), `arm_type` (TIAGo); arm and gripper controllers were active in the smoke tests; the robot tasks of WS07 do not manipulate (declared assumption of the WS07 README) |
| Observed | TIAGo Pro: 7 controllers active, `/scan_front_raw` and `/scan_rear_raw`, Nav2 lifecycle nodes active at 100 s; base driven by `gazebo_ros_planar_move` (omnidirectional) on `/mobile_base_controller/cmd_vel_unstamped`. TIAGo: 7 controllers including `mobile_base_controller`, a `/scan_raw` message |
| Outside the PAL developer image | yes: the packages come from `packages.ros.org` and run on the stock `ros:humble-ros-base` plus apt (closes the open point of WS00-T05) |

Proposal for the human (one short phrase, not paper text): "Simulation: PAL TIAGo Pro model
(`tiago_pro_simulation` 1.19.0) with Nav2 1.1.20 on ROS 2 Humble; manipulation is not simulated in
the experiments."

## Onboard computer

Chosen variant: TIAGo Pro. Source: `2025-Datasheet-TIAGo-Pro.pdf`, page 2 (read with `pdftotext`
and as an image on 2026-10-08).

| Field | Value |
|---|---|
| `cpu_model` | Intel i5 (base configuration; generation and model number not stated); upgrade Intel i7 |
| `cores` | not stated in 2025-Datasheet-TIAGo-Pro.pdf |
| `ram_gb` | 16 (upgrade 32) |
| Storage | 512 GB SSD (upgrade 1 TB SSD) |
| GPU | not stated in 2025-Datasheet-TIAGo-Pro.pdf (the datasheet lists a GPU only under upgrades, "NVIDIA Jetson PC", and never says that the base configuration has none) |
| OS and middleware | "Ubuntu LTS 64-bits \| PREEMPT-RT", "ROS 2" (release not stated) |
| `source_ref` | https://pal-robotics.com/wp-content/uploads/2025/05/2025-Datasheet-TIAGo-Pro.pdf |

The TIAGo datasheet (2024-04, `Datasheet-TIAGo.pdf`, block COMPUTER) states CPU "Intel i5 / i7", RAM
"8 GB / 16 GB", SSD "250 GB / 500 GB"; cores are not stated there either. WS00-T05 names no
equivalent hardware for the WS07-T07 measurement (open point there); the exact configuration of the
group's units is not stated in any source.

## Open items for a human

1. Onboard computer (`partial`): state the exact CPU model, core count, RAM and GPU option of the group's TIAGo Pro (the datasheet gives no core count and no base GPU), and whether WS07-T07 may run on its onboard computer. Until then the CPU and memory figures use the host description of this record. The booking questions of WS00-T05 (location, contact, time window) are still open there.
2. `tc netem` (`partial`): the host user has no privilege. Either a human with root runs the commands of Reproduction step 9 on the host, or approves a compose service with `cap_add: [NET_ADMIN]` (WS07-T05 would add it). The Fast DDS results varied between two runs; netem faults should use CycloneDDS or be re-measured with the experiment's RMW.
3. numpy floor: `pyproject.toml` declares no numpy version (ADR-016, no pins). Bisected on Python 3.10.12 (step 3): the core test `test_foreign_objects_with_unreadable_fields_are_named_errors` fails with numpy 1.21.6, 1.22.4, 1.23.5 and 1.24.4 (the core does not raise `C1InjectionError`) and passes from 1.25.0 (tried: 1.25.0, 1.25.1, 1.25.2, 1.26.4, 2.2.6); mypy strict reports 5 errors only with 1.21.5 and 1.21.6 (passes from 1.22.4). The apt numpy of Humble is 1.21.5. Decide whether the ward node and the robot must run a numpy of about 1.25 or newer (pip; numpy 2 breaks the apt pandas of `tracetools_analysis`), or whether the core should declare a floor of about 1.25 (not added to `pyproject.toml` here), or accept the risk.
4. Dev dependency `tomli`: the `tomllib` fallback of `tests/test_toolchain.py` on Python 3.10 relies on `tomli` arriving as a dependency of pytest 9 (`tomli>=1; python_version < "3.11"`) or of mypy (`tomli>=1.1.0; python_version < "3.11"`). It is missing only with the apt pytest 6.2.5 and no mypy. A human may add `tomli; python_version < "3.11"` to the dev extras of `pyproject.toml` (not done: this task changes `requires-python` only, and `test_pyproject_declares_toolchain` accepts plain names only; the marker would need that test to change).
5. Licences before any release (WS13): the hospital world has inconsistent licence statements (`LICENSE` text versus `package.xml` "Apache 2.0", none detected by GitHub) and its 44 Fuel models carry their own licences, not checked.
6. Reproducibility of the image (WS13): floating base tag, unpinned apt and pip packages, and Fuel models downloaded at build time without pins (see Reproduction); a release needs pinned versions or a saved image.
7. RMW of the real robots: which RMW implementation do the group's TIAGo and TIAGo Pro run? WS00-T05 records that mixed nodes must use the same RMW implementation (ROS documentation: "the same ROS version and the same RMW implementation"). The simulation here used CycloneDDS (compose sets `RMW_IMPLEMENTATION=rmw_cyclonedds_cpp`). PAL's own simulation README (https://raw.githubusercontent.com/pal-robotics/tiago_simulation/humble-devel/README.md, opened on 2026-10-08) says: "In our testing environment, we've found out that the simulation is more reliable if we switch to Cyclone DDS" and "We are still looking on the issues when working with Fast RTPS."
8. HuNavSim (`partial`, optional): decide in WS07-T02 whether moving humans justify a source build (lightsfm, people_msgs, BehaviorTree.CPP, BehaviorTree.ROS2; only the README of branch v1.0-humble names a BehaviorTree.CPP version, 4.6, and the README of v2.0 names none).
9. Plan documents still describing Jazzy (not edited here): `docs/plan/workstreams/WS07-ros2-sim/README.md` line 20 ("ROS 2 Jazzy with Gazebo Harmonic (ADR-011)"), `docs/plan/workstreams/WS07-ros2-sim/tasks/T02-hospital-world.md` line 17 ("a Gazebo Harmonic (or the generation fixed by WS07-T01) hospital world"), and the text of ADR-031 in `docs/plan/03-decisions.md` (lines 262 and 264: Jazzy image, ADR-011 `[DA-CONFERMARE]`).
10. Known risks, not actions: Gazebo Classic is end of life since January 2025 and the AWS hospital world repository is archived (both recorded by ADR-042 and WS00-T05); the ROS distribution that the branches `alum-devel` and `master` of `tiago_pro_simulation` target was not checked.
11. The image `ralmon-ros2:jazzy` is unused; remove it with `docker rmi ralmon-ros2:jazzy` if the space is wanted.

## Proposed ADR

No new ADR is appended to `docs/plan/03-decisions.md`: the verdict `supersede_adr_011` is carried by
ADR-042, which is already accepted and which this check confirms. What is new relative to ADR-042
(facts the ADR log may want to cite):

- The PAL packages are available as ROS apt binaries for Humble and ran headless with Nav2 outside the PAL developer image.
- The new-Gazebo option on Humble is Fortress (`libignition-gazebo6`, `gz-sensors6`); the ROS-apt binaries of `ros_gz_bridge` for Humble serve Fortress, and Gazebo Classic is served by `gazebo_ros_pkgs`.
- ADR-042 migration done: `requires-python = ">=3.10"`, the `tomllib` import of `tests/test_toolchain.py` has a `tomli` fallback for Python 3.10, and the suite, ruff and mypy pass under Python 3.10.12 in the Humble image (numpy below 2); ADR-031's description of the Jazzy image is superseded by `ralmon-ros2:humble`.
- Open decision, not an ADR yet (candidate text for a human to promote): numpy floor. Context: Python 3.10 on Humble comes with numpy 1.21.5, which fails one test and mypy strict on the core; by bisection the test passes from numpy 1.25.0 (first version tried that passes) and mypy from 1.22.4. Decision (proposed): declare a numpy floor of about 1.25 in `pyproject.toml` and install numpy below 2 in the ROS image (the apt pandas needs numpy 1). Alternatives: no floor and a note in the image README; pin numpy in the image only. Consequences: a `pyproject.toml` change that ADR-016 forbids without a decision. Status: proposed, for a human.
