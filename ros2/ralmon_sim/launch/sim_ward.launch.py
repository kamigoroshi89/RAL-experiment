# Copyright (c) 2024 PAL Robotics S.L. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# The notice above is the header of tiago_pro_gazebo.launch.py of the package tiago_pro_gazebo
# 1.19.0 (PAL Robotics; its package.xml declares "Apache License 2.0"), whose structure this file
# adapts. The licence text itself is not in the image (the Debian copyright file of the package says
# "See repository for full license text"): see worlds/NOTICE, section 4b.
#
# Modified by the ralmon project (WS07-T02, 2026-10-09). Changes against the PAL file: the launch
# arguments are only `scenario` and `headless`; the world, the map and the spawn pose come from the
# ward scenario file; the robot is spawned with an explicit pose (spawn_entity.py -x -y -Y) at the
# dock; navigation_public_sim.launch.py, MoveIt and RViz are not started, Nav2 localisation and
# navigation are included directly with config/nav2_params.yaml and the map of the scenario, and
# the initial pose of AMCL is rewritten to the dock pose; the launch configuration `ward_epoch_ms`
# is set to 0; the structure is reduced to what the ward needs.

"""Launch file of the simulated ward (WS07-T02): world, one robot, Nav2, headless.

    ros2 launch ralmon_sim sim_ward.launch.py headless:=true [scenario:=<ward_scenario.yaml>]

Arguments
* ``scenario``: the ward scenario file (default: ``config/ward_scenario.yaml`` of this package);
  it names the world and the map and gives the dock pose where the robot is spawned.
* ``headless``: ``true`` starts ``gzserver`` only, ``false`` also starts ``gzclient`` (a GUI, needs a
  display). The laser scans of the PAL robot exist only when an X display is present even with
  ``headless:=true`` (Xvfb with Mesa software rendering works; see test/conftest.py).

What it starts: Gazebo Classic with the generated world of the scenario, the TIAGo Pro simulation
(robot_state_publisher, controllers, twist_mux; spawned at the dock pose of the scenario, arms
tucked), and Nav2 (map_server, AMCL, planner, controller, behaviors, BT navigator) with
``config/nav2_params.yaml`` and the map of the scenario. Everything runs on simulation time
(``use_sim_time`` True) and the launch configuration ``ward_epoch_ms`` is set to 0, the value that
the clock policy of the WS07 README prescribes under simulated time (no node of this launch file
declares it; the launch files that add ward nodes pass it on).

Limitation, stated on purpose: there is no ``use_humans`` argument. Moving humans (HuNavSim) are
optional in analisi section 5.2, and the availability record of WS07-T01 marks ``human_sim`` as
``partial`` (documented for Humble and Gazebo Classic, no binary package, no build attempted), so the
simulated ward has no moving humans. An argument would be added when the build exists.

Derived structure: the sequence follows ``tiago_pro_gazebo.launch.py`` of the package
tiago_pro_gazebo 1.19.0 of PAL Robotics (Apache License 2.0 in its package.xml), which cannot
spawn the robot at a given pose nor use a map of another world; see worlds/NOTICE.

No import of ``ralmon``: this launch file belongs to the simulation environment (WS05 is not a
dependency of WS07-T02).
"""

import atexit
import os
import sys
import tempfile
from pathlib import Path

import yaml
from ament_index_python.packages import get_package_prefix, get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    OpaqueFunction,
    SetEnvironmentVariable,
    SetLaunchConfiguration,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_pal.include_utils import include_scoped_launch_py_description
from launch_ros.actions import Node

# The launch file sits in <package>/launch both in the source tree and in the install space
# (share/ralmon_sim/launch), and config/ and worlds/ sit next to it in both.
PACKAGE_DIR = Path(__file__).resolve().parent.parent

try:
    from ralmon_sim.ward_scenario import load_scenario
except ImportError:  # not installed: running from the source tree
    sys.path.insert(0, str(PACKAGE_DIR))
    from ralmon_sim.ward_scenario import load_scenario

# Packages whose share directories the PAL launch puts on GAZEBO_MODEL_PATH for the robot model
# (the list in tiago_pro_gazebo.launch.py, public simulation).
ROBOT_MODEL_PACKAGES = [
    "tiago_pro_description",
    "pal_sea_arm_description",
    "omni_base_description",
    "pal_pro_gripper_description",
    "tiago_pro_head_description",
    "pal_urdf_utils",
]
ROBOT_ENTITY_NAME = "tiago-pro"  # the Gazebo model name used by PAL


def _robot_model_path() -> str:
    paths = [
        os.path.join(get_package_prefix(name), "share") for name in ROBOT_MODEL_PACKAGES
    ]
    existing = os.environ.get("GAZEBO_MODEL_PATH")
    if existing:
        paths.append(existing)
    return os.pathsep.join(paths)


def _nav2_params_for(scenario_dock: object, map_path: Path) -> str:
    """The Nav2 parameter file with the dock pose as AMCL initial pose (a temporary copy)."""
    with open(PACKAGE_DIR / "config" / "nav2_params.yaml", encoding="utf-8") as handle:
        params = yaml.safe_load(handle)
    amcl = params["amcl"]["ros__parameters"]
    amcl["initial_pose"] = {
        "x": scenario_dock.x,  # type: ignore[attr-defined]
        "y": scenario_dock.y,  # type: ignore[attr-defined]
        "z": 0.0,
        "yaw": scenario_dock.yaw,  # type: ignore[attr-defined]
    }
    params["map_server"]["ros__parameters"]["yaml_filename"] = str(map_path)
    handle_fd, name = tempfile.mkstemp(prefix="ward_nav2_params_", suffix=".yaml")
    with os.fdopen(handle_fd, "w", encoding="utf-8") as out:
        yaml.safe_dump(params, out, sort_keys=False)
    atexit.register(lambda: os.path.exists(name) and os.unlink(name))
    return name


def _setup(context, *args, **kwargs):
    scenario_path = Path(LaunchConfiguration("scenario").perform(context)).expanduser()
    scenario = load_scenario(scenario_path)
    world_path = PACKAGE_DIR / "worlds" / scenario.world_file
    map_path = PACKAGE_DIR / "worlds" / scenario.map_file
    for needed in (world_path, map_path):
        if not needed.is_file():
            raise RuntimeError(f"sim_ward: {needed} does not exist")
    gzclient = (
        "False"
        if LaunchConfiguration("headless").perform(context).lower() == "true"
        else "True"
    )
    dock = scenario.dock

    gazebo = include_scoped_launch_py_description(
        pkg_name="pal_gazebo_worlds",
        paths=["launch", "pal_gazebo.launch.py"],
        env_vars=[SetEnvironmentVariable("GAZEBO_MODEL_PATH", _robot_model_path())],
        launch_arguments={
            "world_name": str(world_path),
            "gzclient": gzclient,
            "gazebo_version": "classic",
        },
    )
    spawn_robot = Node(
        package="gazebo_ros",
        executable="spawn_entity.py",
        arguments=[
            "-topic",
            "robot_description",
            "-entity",
            ROBOT_ENTITY_NAME,
            "-x",
            repr(dock.x),
            "-y",
            repr(dock.y),
            "-Y",
            repr(dock.yaw),
        ],
        output="screen",
    )
    bringup = include_scoped_launch_py_description(
        pkg_name="tiago_pro_bringup",
        paths=["launch", "tiago_pro_bringup.launch.py"],
        launch_arguments={
            "use_sim_time": "True",
            "is_public_sim": "True",
            "gazebo_version": "classic",
        },
    )
    tuck_arm = Node(
        package="tiago_pro_gazebo",
        executable="tuck_arm.py",
        emulate_tty=True,
        output="both",
    )
    nav2_dir = get_package_share_directory("nav2_bringup")
    params_file = _nav2_params_for(dock, map_path)
    localization = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(nav2_dir, "launch", "localization_launch.py")
        ),
        launch_arguments={
            "params_file": params_file,
            "map": str(map_path),
            "use_sim_time": "True",
            "autostart": "true",
        }.items(),
    )
    navigation = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(nav2_dir, "launch", "navigation_launch.py")
        ),
        launch_arguments={
            "params_file": params_file,
            "use_sim_time": "True",
            "autostart": "true",
        }.items(),
    )
    return [gazebo, spawn_robot, bringup, tuck_arm, localization, navigation]


def generate_launch_description() -> LaunchDescription:
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "scenario",
                default_value=str(PACKAGE_DIR / "config" / "ward_scenario.yaml"),
                description="Ward scenario file (world, map, dock pose)",
            ),
            DeclareLaunchArgument(
                "headless",
                default_value="true",
                choices=["true", "false"],
                description="true: gzserver only; false: also the Gazebo GUI",
            ),
            SetLaunchConfiguration("use_sim_time", "True"),
            SetLaunchConfiguration("ward_epoch_ms", "0"),
            OpaqueFunction(function=_setup),
        ]
    )
