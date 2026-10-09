"""Tests of the ward world, scenario file and Nav2 bring-up (WS07-T02).

Pure tests (no ROS 2, no network, no Gazebo; they run on Python 3.10 to 3.14) build scenario files
and occupancy maps with ``tmp_path`` and read only committed files for the shipped scenario. The
tests with the marker ``ros`` bring the simulation up headless and are skipped when ``rclpy``
cannot be imported. Numeric fixture values are test-only, not clinical.
"""

from __future__ import annotations

import ast
import copy
import dataclasses
import importlib.util
import math
import os
import re
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml
from ralmon_sim import ward_scenario as ws

PACKAGE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = PACKAGE_DIR.parent.parent
SCENARIO_PATH = PACKAGE_DIR / "config" / "ward_scenario.yaml"
WORLDS_DIR = PACKAGE_DIR / "worlds"
NAV2_PARAMS_PATH = PACKAGE_DIR / "config" / "nav2_params.yaml"
LAUNCH_PATH = PACKAGE_DIR / "launch" / "sim_ward.launch.py"
GENERATOR_PATH = PACKAGE_DIR / "scripts" / "generate_ward_world.py"
REGISTRY_PATH = REPO_ROOT / "configs" / "registry" / "hypertension.yaml"

# ----------------------------------------------------------------------------------------------
# Builders for scenario data (test-only values, not clinical)
# ----------------------------------------------------------------------------------------------


def pose(x: float, y: float, yaw: float = 0.0) -> dict[str, float]:
    return {"x": x, "y": y, "yaw": yaw}


def make_room(index: int) -> dict[str, Any]:
    """A room with test-only coordinates; the slot (patient_id, day_index) is a placeholder."""
    base = 3.0 * index
    return {
        "room_id": f"r{index + 1:02d}",
        "patient_id": f"slot-p{index + 1:02d}",
        "day_index": index,
        "door": pose(base + 1.0, 1.0, 1.5),
        "bedside": pose(base + 1.0, 3.0, 0.0),
        "bed": pose(base + 2.0, 3.0, 0.0),
        "dispenser": pose(base + 0.5, 3.5, 0.0),
    }


def make_data(n_rooms: int = 4) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "world_file": "ward.world",
        "map_file": "ward_map.yaml",
        "compression_factor": 30,
        "replay_start_ms": 60_000,
        "stagger": {"spacing_ms": 30_000},
        "monitor": {
            "step_ms": 2_000,
            "reorder_delay_ms": 0,
            "predictive": False,
            "alpha": None,
            "variant": "likely",
            "registry_version": "0.2.0",
        },
        "time_entries": {
            "care_plan_time_entries": ["sched_window", "delta1"],
            "physical_time_entries": ["cuff_inflation_min"],
        },
        "startup_timeout_ms": 300_000,
        "nav_goal_timeout_ms": 120_000,
        "dock": pose(0.5, 0.0, 0.0),
        "unreachable_pose": pose(9.0, 9.0, 0.0),
        "rooms": [make_room(i) for i in range(n_rooms)],
    }


def write_data(tmp_path: Path, data: object, name: str = "scenario.yaml") -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def load_data(tmp_path: Path, data: object) -> ws.WardScenario:
    return ws.load_scenario(write_data(tmp_path, data))


def dotted(path: tuple[object, ...]) -> str:
    """The key path in the form the errors use: ``rooms[0].door.x``."""
    text = ""
    for part in path:
        if isinstance(part, int):
            text += f"[{part}]"
        else:
            text += ("." if text else "") + str(part)
    return text


def get_at(data: Any, path: tuple[object, ...]) -> Any:
    for part in path:
        data = data[part]
    return data


def set_at(data: Any, path: tuple[object, ...], value: object) -> None:
    get_at(data, path[:-1])[path[-1]] = value


def delete_at(data: Any, path: tuple[object, ...]) -> None:
    del get_at(data, path[:-1])[path[-1]]


# ----------------------------------------------------------------------------------------------
# Rooms: count, uniqueness
# ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize("n_rooms", [4, 5, 6, 7, 8])
def test_load_scenario_accepts_four_to_eight_rooms(
    tmp_path: Path, n_rooms: int
) -> None:
    scenario = load_data(tmp_path, make_data(n_rooms))
    assert len(scenario.rooms) == n_rooms
    assert all(isinstance(room, ws.Room) for room in scenario.rooms)
    assert [room.room_id for room in scenario.rooms] == [
        f"r{i + 1:02d}" for i in range(n_rooms)
    ]
    assert [room.day_index for room in scenario.rooms] == list(range(n_rooms))


def test_load_scenario_returns_the_declared_values(tmp_path: Path) -> None:
    data = make_data(4)
    data["monitor"]["predictive"] = True
    data["monitor"]["alpha"] = 0.25
    data["monitor"]["variant"] = "possible"
    scenario = load_data(tmp_path, data)
    assert isinstance(scenario, ws.WardScenario)
    assert scenario.compression_factor == 30
    assert scenario.replay_start_ms == 60_000
    assert scenario.spacing_ms == 30_000
    assert scenario.startup_timeout_ms == 300_000
    assert scenario.nav_goal_timeout_ms == 120_000
    assert scenario.world_file == "ward.world"
    assert scenario.map_file == "ward_map.yaml"
    assert scenario.monitor == ws.MonitorSettings(
        step_ms=2_000,
        reorder_delay_ms=0,
        predictive=True,
        alpha=0.25,
        variant="possible",
        registry_version="0.2.0",
    )
    assert scenario.care_plan_time_entries == ("sched_window", "delta1")
    assert scenario.physical_time_entries == ("cuff_inflation_min",)
    assert scenario.dock == ws.Pose2D(0.5, 0.0, 0.0)
    assert scenario.unreachable_pose == ws.Pose2D(9.0, 9.0, 0.0)
    first = scenario.rooms[0]
    assert first.patient_id == "slot-p01"
    assert first.door == ws.Pose2D(1.0, 1.0, 1.5)
    assert first.bedside == ws.Pose2D(1.0, 3.0, 0.0)
    assert first.bed == ws.Pose2D(2.0, 3.0, 0.0)
    assert first.dispenser == ws.Pose2D(0.5, 3.5, 0.0)
    assert isinstance(scenario.rooms, tuple)
    assert isinstance(scenario.care_plan_time_entries, tuple)


def test_integer_coordinates_are_accepted_and_stored_as_floats(tmp_path: Path) -> None:
    data = make_data(4)
    data["dock"] = {"x": 1, "y": 2, "yaw": 0}
    scenario = load_data(tmp_path, data)
    assert scenario.dock == ws.Pose2D(1.0, 2.0, 0.0)
    assert all(isinstance(v, float) for v in (scenario.dock.x, scenario.dock.y))
    assert isinstance(scenario.dock.yaw, float)


@pytest.mark.parametrize("n_rooms", [0, 1, 3, 9, 20])
def test_load_scenario_rejects_three_and_nine_rooms(
    tmp_path: Path, n_rooms: int
) -> None:
    data = make_data(4)
    data["rooms"] = [make_room(i) for i in range(n_rooms)]
    with pytest.raises(ws.ScenarioError, match="rooms"):
        load_data(tmp_path, data)


@pytest.mark.parametrize("bad", [None, 5, "rooms", {"r01": {}}, True, 1.5])
def test_rooms_must_be_a_list(tmp_path: Path, bad: object) -> None:
    data = make_data(4)
    data["rooms"] = bad
    with pytest.raises(ws.ScenarioError, match="rooms"):
        load_data(tmp_path, data)


@pytest.mark.parametrize("bad", [None, 5, "r01", [], True])
def test_each_room_must_be_a_mapping(tmp_path: Path, bad: object) -> None:
    data = make_data(4)
    data["rooms"][2] = bad
    with pytest.raises(ws.ScenarioError, match=r"rooms\[2\]"):
        load_data(tmp_path, data)


def test_room_ids_and_patient_slots_unique(tmp_path: Path) -> None:
    duplicate_id = make_data(4)
    duplicate_id["rooms"][3]["room_id"] = duplicate_id["rooms"][0]["room_id"]
    with pytest.raises(ws.ScenarioError, match="room_id"):
        load_data(tmp_path, duplicate_id)

    duplicate_slot = make_data(4)
    duplicate_slot["rooms"][2]["patient_id"] = duplicate_slot["rooms"][1]["patient_id"]
    duplicate_slot["rooms"][2]["day_index"] = duplicate_slot["rooms"][1]["day_index"]
    with pytest.raises(ws.ScenarioError, match="patient_id"):
        load_data(tmp_path, duplicate_slot)


def test_same_patient_with_another_day_or_same_day_with_another_patient_is_allowed(
    tmp_path: Path,
) -> None:
    same_patient = make_data(4)
    same_patient["rooms"][1]["patient_id"] = same_patient["rooms"][0]["patient_id"]
    same_patient["rooms"][1]["day_index"] = 7
    assert len(load_data(tmp_path, same_patient).rooms) == 4

    same_day = make_data(4)
    same_day["rooms"][1]["day_index"] = same_day["rooms"][0]["day_index"]
    assert len(load_data(tmp_path, same_day).rooms) == 4


# ----------------------------------------------------------------------------------------------
# Required keys, unknown keys, types and ranges
# ----------------------------------------------------------------------------------------------

REQUIRED_PATHS: list[tuple[object, ...]] = [
    ("schema_version",),
    ("world_file",),
    ("map_file",),
    ("compression_factor",),
    ("replay_start_ms",),
    ("stagger",),
    ("stagger", "spacing_ms"),
    ("monitor",),
    ("monitor", "step_ms"),
    ("monitor", "reorder_delay_ms"),
    ("monitor", "predictive"),
    ("monitor", "alpha"),
    ("monitor", "variant"),
    ("monitor", "registry_version"),
    ("time_entries",),
    ("time_entries", "care_plan_time_entries"),
    ("time_entries", "physical_time_entries"),
    ("startup_timeout_ms",),
    ("nav_goal_timeout_ms",),
    ("dock",),
    ("dock", "x"),
    ("dock", "y"),
    ("dock", "yaw"),
    ("unreachable_pose",),
    ("unreachable_pose", "x"),
    ("unreachable_pose", "y"),
    ("unreachable_pose", "yaw"),
    ("rooms",),
    ("rooms", 1, "room_id"),
    ("rooms", 1, "patient_id"),
    ("rooms", 1, "day_index"),
    ("rooms", 1, "door"),
    ("rooms", 1, "door", "x"),
    ("rooms", 1, "door", "y"),
    ("rooms", 1, "door", "yaw"),
    ("rooms", 1, "bedside"),
    ("rooms", 1, "bedside", "yaw"),
    ("rooms", 1, "bed"),
    ("rooms", 1, "bed", "x"),
    ("rooms", 1, "dispenser"),
    ("rooms", 1, "dispenser", "y"),
]


@pytest.mark.parametrize(
    "path", REQUIRED_PATHS, ids=[dotted(p) for p in REQUIRED_PATHS]
)
def test_required_keys_have_no_defaults(
    tmp_path: Path, path: tuple[object, ...]
) -> None:
    data = make_data(4)
    delete_at(data, path)
    with pytest.raises(ws.ScenarioError) as info:
        load_data(tmp_path, data)
    assert dotted(path) in str(info.value)


def test_required_keys_of_the_task_are_all_listed() -> None:
    # the nine keys named by the task text must be in the table above
    named = {
        ("compression_factor",),
        ("replay_start_ms",),
        ("stagger",),
        ("monitor", "step_ms"),
        ("monitor", "reorder_delay_ms"),
        ("dock",),
        ("unreachable_pose",),
        ("time_entries", "care_plan_time_entries"),
        ("time_entries", "physical_time_entries"),
    }
    assert named <= set(REQUIRED_PATHS)


UNKNOWN_KEY_PATHS: list[tuple[object, ...]] = [
    (),
    ("stagger",),
    ("monitor",),
    ("time_entries",),
    ("dock",),
    ("rooms", 0),
    ("rooms", 0, "bed"),
]


@pytest.mark.parametrize(
    "path", UNKNOWN_KEY_PATHS, ids=[dotted(p) or "top" for p in UNKNOWN_KEY_PATHS]
)
def test_unknown_keys_are_rejected_and_named(
    tmp_path: Path, path: tuple[object, ...]
) -> None:
    data = make_data(4)
    get_at(data, path)["surprise_key"] = 1
    with pytest.raises(ws.ScenarioError, match="surprise_key"):
        load_data(tmp_path, data)


@pytest.mark.parametrize("key", [1, 2.5, True, None, ("a", 1)])
def test_non_text_keys_are_rejected(tmp_path: Path, key: object) -> None:
    data = make_data(4)
    data["monitor"][key] = 1
    path = tmp_path / "scenario.yaml"
    path.write_text(yaml.dump(data, sort_keys=False), encoding="utf-8")
    with pytest.raises(ws.ScenarioError):
        ws.load_scenario(path)


BAD_INTS = [
    None,
    True,
    False,
    1.5,
    1.0,
    "7",
    float("nan"),
    float("inf"),
    float("-inf"),
    10**400,
    [],
    {},
]

# (path, smallest accepted value); each is an integer field without a default
INT_FIELDS: list[tuple[tuple[object, ...], int]] = [
    (("compression_factor",), 1),
    (("replay_start_ms",), 0),
    (("stagger", "spacing_ms"), 1),
    (("monitor", "step_ms"), 1),
    (("monitor", "reorder_delay_ms"), 0),
    (("startup_timeout_ms",), 1),
    (("nav_goal_timeout_ms",), 1),
    (("rooms", 0, "day_index"), 0),
    (("rooms", 0, "offset_ms"), 0),
]


@pytest.mark.parametrize(
    "path,minimum", INT_FIELDS, ids=[dotted(p) for p, _ in INT_FIELDS]
)
def test_integer_fields_accept_their_minimum_and_reject_everything_else(
    tmp_path: Path, path: tuple[object, ...], minimum: int
) -> None:
    ok = make_data(4)
    set_at(ok, path, minimum)
    assert load_data(tmp_path, ok) is not None
    for bad in [*BAD_INTS, minimum - 1, -(10**400)]:
        data = make_data(4)
        set_at(data, path, bad)
        with pytest.raises(ws.ScenarioError) as info:
            ws.load_scenario(write_data(tmp_path, data))
        assert dotted(path) in str(info.value), (bad, str(info.value))


def test_compression_factor_is_integer_at_least_one(tmp_path: Path) -> None:
    for good in (1, 30):
        data = make_data(4)
        data["compression_factor"] = good
        assert load_data(tmp_path, data).compression_factor == good
    for bad in (0, -1, 1.5, "30", True, None, 30.0):
        data = make_data(4)
        data["compression_factor"] = bad
        with pytest.raises(ws.ScenarioError, match="compression_factor"):
            load_data(tmp_path, data)


def test_integer_upper_bound_is_a_named_constant(tmp_path: Path) -> None:
    limit = ws.MAX_INT_VALUE
    data = make_data(4)
    data["replay_start_ms"] = limit
    assert load_data(tmp_path, data).replay_start_ms == limit
    data["replay_start_ms"] = limit + 1
    with pytest.raises(ws.ScenarioError, match="replay_start_ms"):
        load_data(tmp_path, data)


def test_schema_version_must_be_exactly_one(tmp_path: Path) -> None:
    for bad in (0, 2, -1, "1", 1.0, True, None):
        data = make_data(4)
        data["schema_version"] = bad
        with pytest.raises(ws.ScenarioError, match="schema_version"):
            load_data(tmp_path, data)


BAD_FLOATS = [
    None,
    True,
    False,
    "1.0",
    [],
    {},
    float("nan"),
    float("inf"),
    float("-inf"),
    10**400,
    -(10**400),
    1e300,
    ws.MAX_COORD_M * 2,
]


@pytest.mark.parametrize("name", ["dock", "unreachable_pose"])
@pytest.mark.parametrize("field", ["x", "y", "yaw"])
def test_pose_fields_reject_non_finite_and_non_numbers(
    tmp_path: Path, name: str, field: str
) -> None:
    for bad in BAD_FLOATS:
        data = make_data(4)
        data[name][field] = bad
        with pytest.raises(ws.ScenarioError) as info:
            ws.load_scenario(write_data(tmp_path, data))
        assert f"{name}.{field}" in str(info.value), bad


def test_pose_value_ranges(tmp_path: Path) -> None:
    for good in (-ws.MAX_COORD_M, ws.MAX_COORD_M, 0, -2.5):
        data = make_data(4)
        data["dock"]["x"] = good
        assert load_data(tmp_path, data).dock.x == good
    for yaw in (-math.pi, math.pi, 0.0, 1):
        data = make_data(4)
        data["dock"]["yaw"] = yaw
        assert load_data(tmp_path, data).dock.yaw == yaw
    for yaw in (math.pi + 1e-9, -math.pi - 1e-9, 4.0, -4.0, 100):
        data = make_data(4)
        data["dock"]["yaw"] = yaw
        with pytest.raises(ws.ScenarioError, match="dock.yaw"):
            load_data(tmp_path, data)
    data = make_data(4)
    data["dock"]["x"] = ws.MAX_COORD_M * (1 + 1e-9)
    with pytest.raises(ws.ScenarioError, match="dock.x"):
        load_data(tmp_path, data)


def test_pose_dataclass_validates_itself() -> None:
    assert ws.Pose2D(1, 2, 3).x == 1.0
    for args in [
        (float("nan"), 0, 0),
        (0, float("inf"), 0),
        (0, 0, 4.0),
        (True, 0, 0),
        ("1", 0, 0),
        (None, 0, 0),
        (10**400, 0, 0),
        (0, 0, -3.2),
    ]:
        with pytest.raises(ws.ScenarioError):
            ws.Pose2D(*args)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "path,bad",
    [
        (
            ("rooms", 0, "room_id"),
            ["", "1abc", "r 1", "r-1", "a" * 33, "r01\n", "é", "а1"],
        ),
        (
            ("rooms", 0, "patient_id"),
            ["", ".hidden", "-x", "a" * 65, "a/b", "a b", "p\n", ".."],
        ),
        (
            ("world_file",),
            ["", "a/b.world", ".world", "../x.world", "x.txt", "w" * 200],
        ),
        (("map_file",), ["", "a/b.yaml", "..", "x.pgm", "m" * 200]),
        (("monitor", "registry_version"), ["", "v 1", "1" * 40, "0.2.0\n", "a/b"]),
    ],
    ids=["room_id", "patient_id", "world_file", "map_file", "registry_version"],
)
def test_identifier_patterns(
    tmp_path: Path, path: tuple[object, ...], bad: list[str]
) -> None:
    for value in [*bad, None, 7, True, [], {}, 1.5]:
        data = make_data(4)
        set_at(data, path, value)
        with pytest.raises(ws.ScenarioError) as info:
            ws.load_scenario(write_data(tmp_path, data))
        assert dotted(path) in str(info.value), repr(value)


def test_identifier_patterns_accept_the_documented_forms(tmp_path: Path) -> None:
    data = make_data(4)
    data["rooms"][0]["room_id"] = "R" + "a_9" * 10 + "z"  # 32 characters
    data["rooms"][0]["patient_id"] = "p" + "A.b_c-9" * 9  # 64 characters
    data["world_file"] = "ward-2.world"
    data["map_file"] = "ward_map.v2.yaml"
    data["monitor"]["registry_version"] = "0.2.0"
    scenario = load_data(tmp_path, data)
    assert len(scenario.rooms[0].room_id) == 32
    assert len(scenario.rooms[0].patient_id) == 64
    data["world_file"] = "ward.sdf"
    assert load_data(tmp_path, data).world_file == "ward.sdf"


def test_monitor_fields(tmp_path: Path) -> None:
    for bad in (0, 1, "true", None, "False", [], 1.0):
        data = make_data(4)
        data["monitor"]["predictive"] = bad
        with pytest.raises(ws.ScenarioError, match="predictive"):
            load_data(tmp_path, data)
    for bad in ("Likely", "", "unlikely", None, 1, True, "possible "):
        data = make_data(4)
        data["monitor"]["variant"] = bad
        with pytest.raises(ws.ScenarioError, match="variant"):
            load_data(tmp_path, data)
    for good in ("likely", "possible"):
        data = make_data(4)
        data["monitor"]["variant"] = good
        assert load_data(tmp_path, data).monitor.variant == good


def test_alpha_is_none_or_a_level_strictly_between_zero_and_one(tmp_path: Path) -> None:
    for good in (0.001, 0.2, 0.999):
        data = make_data(4)
        data["monitor"]["alpha"] = good
        assert load_data(tmp_path, data).monitor.alpha == good
    data = make_data(4)
    data["monitor"]["alpha"] = None
    assert load_data(tmp_path, data).monitor.alpha is None
    for bad in (
        0.0,
        1.0,
        -0.1,
        1.5,
        0,
        1,
        "0.1",
        True,
        False,
        float("nan"),
        float("inf"),
        [],
        {},
    ):
        data = make_data(4)
        data["monitor"]["alpha"] = bad
        with pytest.raises(ws.ScenarioError, match="alpha"):
            load_data(tmp_path, data)


def test_predictive_monitor_needs_an_alpha(tmp_path: Path) -> None:
    data = make_data(4)
    data["monitor"]["predictive"] = True
    data["monitor"]["alpha"] = None
    with pytest.raises(ws.ScenarioError, match="alpha"):
        load_data(tmp_path, data)
    data["monitor"]["alpha"] = 0.1
    assert load_data(tmp_path, data).monitor.predictive is True
    data["monitor"]["predictive"] = False
    assert load_data(tmp_path, data).monitor.predictive is False


# ----------------------------------------------------------------------------------------------
# Stagger
# ----------------------------------------------------------------------------------------------


def test_stagger_offsets_from_spacing() -> None:
    assert ws.stagger_offsets(n_rooms=4, spacing_ms=900_000) == [
        0,
        900_000,
        1_800_000,
        2_700_000,
    ]
    assert ws.stagger_offsets(n_rooms=1, spacing_ms=5) == [0]
    for spacing in (0, -1, -900_000):
        with pytest.raises(ws.ScenarioError, match="spacing_ms"):
            ws.stagger_offsets(n_rooms=4, spacing_ms=spacing)
    assert ws.stagger_offsets(n_rooms=8, spacing_ms=1) == list(range(8))
    assert isinstance(ws.stagger_offsets(n_rooms=4, spacing_ms=3), list)


@pytest.mark.parametrize(
    "spacing", [0, -1, -900_000, 1.5, 900_000.0, "9", None, True, 10**400]
)
def test_stagger_spacing_must_be_a_positive_integer(spacing: object) -> None:
    with pytest.raises(ws.ScenarioError, match="spacing_ms"):
        ws.stagger_offsets(n_rooms=4, spacing_ms=spacing)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "n_rooms", [0, -1, 2.5, "4", None, True, 10**400, ws.MAX_STAGGER_SLOTS + 1]
)
def test_stagger_slot_count_must_be_a_positive_bounded_integer(n_rooms: object) -> None:
    with pytest.raises(ws.ScenarioError, match="n_rooms"):
        ws.stagger_offsets(n_rooms=n_rooms, spacing_ms=10)  # type: ignore[arg-type]


def test_stagger_offsets_stay_below_the_integer_bound() -> None:
    limit = ws.MAX_INT_VALUE
    assert ws.stagger_offsets(n_rooms=2, spacing_ms=limit) == [0, limit]
    with pytest.raises(ws.ScenarioError, match="spacing_ms"):
        ws.stagger_offsets(n_rooms=3, spacing_ms=limit)
    with pytest.raises(ws.ScenarioError, match="spacing_ms"):
        ws.stagger_offsets(n_rooms=2, spacing_ms=limit + 1)


def test_generated_offsets_are_used_when_no_room_has_one(tmp_path: Path) -> None:
    scenario = load_data(tmp_path, make_data(5))
    assert [room.offset_ms for room in scenario.rooms] == [
        0,
        30_000,
        60_000,
        90_000,
        120_000,
    ]


def test_explicit_room_offsets_override_and_must_be_distinct(tmp_path: Path) -> None:
    data = make_data(4)
    data["rooms"][0]["offset_ms"] = 5_000
    data["rooms"][2]["offset_ms"] = 7_000
    scenario = load_data(tmp_path, data)
    # explicit values replace the generated ones; the other rooms keep index * spacing
    assert [room.offset_ms for room in scenario.rooms] == [5_000, 30_000, 7_000, 90_000]

    equal = make_data(4)
    equal["rooms"][0]["offset_ms"] = 11_000
    equal["rooms"][1]["offset_ms"] = 11_000
    with pytest.raises(ws.ScenarioError, match="offset_ms"):
        load_data(tmp_path, equal)

    collides_with_generated = make_data(4)
    collides_with_generated["rooms"][0]["offset_ms"] = 30_000  # room 1 generates 30_000
    with pytest.raises(ws.ScenarioError, match="offset_ms"):
        load_data(tmp_path, collides_with_generated)

    negative = make_data(4)
    negative["rooms"][1]["offset_ms"] = -1
    with pytest.raises(ws.ScenarioError, match="offset_ms"):
        load_data(tmp_path, negative)


def test_every_room_may_carry_an_explicit_offset(tmp_path: Path) -> None:
    data = make_data(4)
    for room, offset in zip(data["rooms"], (400, 300, 200, 100), strict=True):
        room["offset_ms"] = offset
    scenario = load_data(tmp_path, data)
    assert [room.offset_ms for room in scenario.rooms] == [400, 300, 200, 100]


# ----------------------------------------------------------------------------------------------
# Time entries
# ----------------------------------------------------------------------------------------------


def test_time_entry_lists_are_disjoint(tmp_path: Path) -> None:
    data = make_data(4)
    data["time_entries"]["care_plan_time_entries"] = ["sched_window", "delta1"]
    data["time_entries"]["physical_time_entries"] = ["delta1", "cuff_inflation_min"]
    with pytest.raises(ws.ScenarioError, match="delta1"):
        load_data(tmp_path, data)


def test_time_entry_lists_may_be_empty_but_must_be_lists_of_registry_names(
    tmp_path: Path,
) -> None:
    data = make_data(4)
    data["time_entries"]["care_plan_time_entries"] = []
    data["time_entries"]["physical_time_entries"] = []
    scenario = load_data(tmp_path, data)
    assert scenario.care_plan_time_entries == ()
    assert scenario.physical_time_entries == ()
    for key in ("care_plan_time_entries", "physical_time_entries"):
        for bad in (
            None,
            "sched_window",
            {"a": 1},
            5,
            True,
            ["a", 1],
            [None],
            [""],
            ["Bad"],
            ["a b"],
            ["1a"],
            ["a" * 65],
            [["a"]],
        ):
            data = make_data(4)
            data["time_entries"][key] = bad
            with pytest.raises(ws.ScenarioError, match=key):
                load_data(tmp_path, data)


def test_time_entry_lists_reject_repeats_inside_one_list(tmp_path: Path) -> None:
    for key in ("care_plan_time_entries", "physical_time_entries"):
        data = make_data(4)
        data["time_entries"][key] = ["delta2", "delta2"]
        with pytest.raises(ws.ScenarioError, match="delta2"):
            load_data(tmp_path, data)


def test_time_entry_lists_are_bounded(tmp_path: Path) -> None:
    n = ws.MAX_TIME_ENTRIES
    data = make_data(4)
    data["time_entries"]["care_plan_time_entries"] = [f"e{i}" for i in range(n)]
    assert len(load_data(tmp_path, data).care_plan_time_entries) == n
    data["time_entries"]["care_plan_time_entries"] = [f"e{i}" for i in range(n + 1)]
    with pytest.raises(ws.ScenarioError, match="care_plan_time_entries"):
        load_data(tmp_path, data)
    data = make_data(4)
    data["time_entries"]["physical_time_entries"] = [f"e{i}" for i in range(n + 1)]
    with pytest.raises(ws.ScenarioError, match="physical_time_entries"):
        load_data(tmp_path, data)


# ----------------------------------------------------------------------------------------------
# Hostile files and top-level shapes
# ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "",
        "null\n",
        "true\n",
        "5\n",
        "'text'\n",
        "[]\n",
        "- a\n- b\n",
        "{}\n",
        "---\n---\n",
        "a: [\n",
    ],
    ids=[
        "empty",
        "null",
        "bool",
        "int",
        "str",
        "list",
        "list2",
        "empty-map",
        "two-docs",
        "syntax",
    ],
)
def test_malformed_documents_raise_scenario_error(tmp_path: Path, text: str) -> None:
    path = tmp_path / "s.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ws.ScenarioError):
        ws.load_scenario(path)


def test_duplicate_keys_are_rejected(tmp_path: Path) -> None:
    good = yaml.safe_dump(make_data(4), sort_keys=False)
    path = tmp_path / "s.yaml"
    path.write_text(good + "compression_factor: 2\n", encoding="utf-8")
    with pytest.raises(ws.ScenarioError, match="duplicate"):
        ws.load_scenario(path)
    nested = good.replace("  step_ms: 2000\n", "  step_ms: 2000\n  step_ms: 3000\n")
    assert nested != good
    path.write_text(nested, encoding="utf-8")
    with pytest.raises(ws.ScenarioError, match="duplicate"):
        ws.load_scenario(path)


def test_anchors_aliases_and_merge_keys_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "s.yaml"
    text = yaml.safe_dump(make_data(4), sort_keys=False)
    path.write_text(
        text.replace("  step_ms: 2000\n", "  step_ms: &a 2000\n").replace(
            "  reorder_delay_ms: 0\n", "  reorder_delay_ms: *a\n"
        ),
        encoding="utf-8",
    )
    with pytest.raises(ws.ScenarioError, match="anchor"):
        ws.load_scenario(path)
    merge = text.replace("dock:\n", "base: &b {x: 1.0}\ndock:\n  <<: *b\n", 1)
    path.write_text(merge, encoding="utf-8")
    with pytest.raises(ws.ScenarioError):
        ws.load_scenario(path)
    plain_merge = text.replace("dock:\n", "dock:\n  <<: {x: 1.0}\n", 1)
    assert plain_merge != text
    path.write_text(plain_merge, encoding="utf-8")
    with pytest.raises(ws.ScenarioError, match="merge"):
        ws.load_scenario(path)


def test_alias_expansion_bomb_is_refused_quickly(tmp_path: Path) -> None:
    lines = ["a0: &a0 [x, x, x, x, x, x, x, x, x]"]
    for i in range(1, 12):
        previous = f"*a{i - 1}"
        lines.append(f"a{i}: &a{i} [{', '.join([previous] * 9)}]")
    path = tmp_path / "bomb.yaml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    started = time.monotonic()
    with pytest.raises(ws.ScenarioError):
        ws.load_scenario(path)
    assert time.monotonic() - started < 5.0


def test_python_tags_are_not_constructed(tmp_path: Path) -> None:
    marker = tmp_path / "executed"
    path = tmp_path / "s.yaml"
    text = yaml.safe_dump(make_data(4), sort_keys=False)
    text += f"surprise: !!python/object/apply:os.mkdir ['{marker}']\n"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ws.ScenarioError):
        ws.load_scenario(path)
    assert not marker.exists()


def test_unhashable_mapping_keys_raise_scenario_error(tmp_path: Path) -> None:
    path = tmp_path / "s.yaml"
    path.write_text("? [1, 2]\n: x\n", encoding="utf-8")
    with pytest.raises(ws.ScenarioError):
        ws.load_scenario(path)


def test_deeply_nested_documents_raise_scenario_error(tmp_path: Path) -> None:
    path = tmp_path / "s.yaml"
    path.write_text("[" * 50_000 + "]" * 50_000, encoding="utf-8")
    with pytest.raises(ws.ScenarioError):
        ws.load_scenario(path)
    path.write_text("a: " + "[" * 50_000, encoding="utf-8")
    with pytest.raises(ws.ScenarioError):
        ws.load_scenario(path)


def test_non_utf8_and_binary_files_raise_scenario_error(tmp_path: Path) -> None:
    path = tmp_path / "s.yaml"
    for payload in (b"\xff\xfe\x00bad", b"a: \xc3\x28\n", b"\x00\x01\x02", b"a: \x80"):
        path.write_bytes(payload)
        with pytest.raises(ws.ScenarioError):
            ws.load_scenario(path)


def test_control_characters_in_the_text_raise_scenario_error(tmp_path: Path) -> None:
    path = tmp_path / "s.yaml"
    path.write_text("a: \x07\n", encoding="utf-8")
    with pytest.raises(ws.ScenarioError):
        ws.load_scenario(path)


def test_missing_file_directory_and_bad_path_types(tmp_path: Path) -> None:
    with pytest.raises(ws.ScenarioError, match="cannot read"):
        ws.load_scenario(tmp_path / "missing.yaml")
    with pytest.raises(ws.ScenarioError, match="not a regular file"):
        ws.load_scenario(tmp_path)
    for bad in (None, 5, 1.5, True, b"scenario.yaml", ["a"], object()):
        with pytest.raises(ws.ScenarioError):
            ws.load_scenario(bad)  # type: ignore[arg-type]
    with pytest.raises(ws.ScenarioError):
        ws.load_scenario("bad\x00name.yaml")
    with pytest.raises(ws.ScenarioError):
        ws.load_scenario("x" * 5000)


def test_load_scenario_accepts_str_and_pathlike(tmp_path: Path) -> None:
    path = write_data(tmp_path, make_data(4))
    assert len(ws.load_scenario(str(path)).rooms) == 4
    assert len(ws.load_scenario(path).rooms) == 4

    class Like:
        def __fspath__(self) -> str:
            return str(path)

    assert len(ws.load_scenario(Like()).rooms) == 4  # type: ignore[arg-type]

    class Broken:
        def __fspath__(self) -> str:
            raise RuntimeError("broken")

    with pytest.raises(ws.ScenarioError):
        ws.load_scenario(Broken())  # type: ignore[arg-type]

    class NotText:
        def __fspath__(self) -> bytes:
            return b"x"

    with pytest.raises(ws.ScenarioError):
        ws.load_scenario(NotText())  # type: ignore[arg-type]


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs named pipes")
def test_named_pipe_is_refused_without_blocking(tmp_path: Path) -> None:
    fifo = tmp_path / "pipe.yaml"
    os.mkfifo(fifo)
    outcome: list[object] = []

    def run() -> None:
        try:
            ws.load_scenario(fifo)
        except BaseException as exc:  # noqa: BLE001 (recorded, checked by the main thread)
            outcome.append(exc)

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(timeout=10)
    assert not worker.is_alive(), "load_scenario blocked on a named pipe"
    assert len(outcome) == 1 and isinstance(outcome[0], ws.ScenarioError)
    assert "not a regular file" in str(outcome[0])


def test_oversized_file_is_refused_before_parsing(tmp_path: Path) -> None:
    path = tmp_path / "big.yaml"
    path.write_bytes(b"#" + b"a" * ws.MAX_FILE_BYTES + b"\n")
    with pytest.raises(ws.ScenarioError, match="larger than"):
        ws.load_scenario(path)
    exact = tmp_path / "exact.yaml"
    body = yaml.safe_dump(make_data(4), sort_keys=False).encode()
    exact.write_bytes(body + b"#" * (ws.MAX_FILE_BYTES - len(body)))
    assert len(exact.read_bytes()) == ws.MAX_FILE_BYTES
    assert len(ws.load_scenario(exact).rooms) == 4


def test_a_symlink_to_a_regular_file_is_followed(tmp_path: Path) -> None:
    target = write_data(tmp_path, make_data(4), "target.yaml")
    link = tmp_path / "link.yaml"
    link.symlink_to(target)
    assert len(ws.load_scenario(link).rooms) == 4


def test_error_messages_are_bounded(tmp_path: Path) -> None:
    data = make_data(4)
    data["x" * 100_000] = 1
    with pytest.raises(ws.ScenarioError) as info:
        load_data(tmp_path, data)
    assert len(str(info.value)) < 600
    data = make_data(4)
    data["rooms"][0]["room_id"] = "y" * 100_000
    with pytest.raises(ws.ScenarioError) as info:
        load_data(tmp_path, data)
    assert len(str(info.value)) < 600
    data = make_data(4)
    data["compression_factor"] = 10**400
    with pytest.raises(ws.ScenarioError) as info:
        load_data(tmp_path, data)
    assert len(str(info.value)) < 600


def test_only_scenario_error_escapes_for_odd_values(tmp_path: Path) -> None:
    odd = [
        None,
        True,
        False,
        0,
        -1,
        10**400,
        -(10**400),
        1.5,
        float("nan"),
        float("inf"),
        "",
        "x",
        "\x00",
        "é" * 10,
        [],
        [[]],
        [None],
        {},
        {"a": {"b": []}},
        ["a", 1, None],
    ]
    paths = [p for p, _ in INT_FIELDS] + [
        ("monitor", "alpha"),
        ("monitor", "predictive"),
        ("monitor", "variant"),
        ("dock",),
        ("dock", "x"),
        ("stagger",),
        ("time_entries",),
        ("time_entries", "care_plan_time_entries"),
        ("rooms", 0),
        ("rooms", 0, "door"),
        ("rooms", 0, "room_id"),
        ("rooms", 0, "patient_id"),
        ("world_file",),
    ]
    for path in paths:
        for value in odd:
            data = make_data(4)
            set_at(data, path, copy.deepcopy(value))
            try:
                ws.parse_scenario(data)
            except ws.ScenarioError:
                pass


def test_parse_scenario_takes_plain_data() -> None:
    assert len(ws.parse_scenario(make_data(6)).rooms) == 6
    for bad in (None, 5, "x", [], True, object()):
        with pytest.raises(ws.ScenarioError):
            ws.parse_scenario(bad)


def test_scenario_dataclasses_are_frozen_and_slotted() -> None:
    scenario = ws.parse_scenario(make_data(4))
    for obj, attr in (
        (scenario, "compression_factor"),
        (scenario.rooms[0], "room_id"),
        (scenario.dock, "x"),
        (scenario.monitor, "step_ms"),
    ):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(obj, attr, 1)
        assert not hasattr(obj, "__dict__")


# ----------------------------------------------------------------------------------------------
# PGM parsing
# ----------------------------------------------------------------------------------------------


def p5(
    width: int, height: int, maxval: int, samples: list[int], header_extra: bytes = b""
) -> bytes:
    head = b"P5\n" + header_extra + f"{width} {height}\n{maxval}\n".encode()
    if maxval < 256:
        body = bytes(samples)
    else:
        body = b"".join(int(s).to_bytes(2, "big") for s in samples)
    return head + body


def test_parse_pgm_binary_with_comments() -> None:
    data = b"P5\n# a comment\n3 2 # inline\n# more\n255\n" + bytes(
        [0, 1, 2, 250, 251, 255]
    )
    pixels, maxval = ws.parse_pgm(data)
    assert maxval == 255
    assert pixels.shape == (2, 3)
    assert pixels.tolist() == [[0, 1, 2], [250, 251, 255]]


def test_parse_pgm_binary_raster_starting_with_a_hash_byte_is_not_a_comment() -> None:
    data = b"P5 2 1 255\n" + bytes([0x23, 0x0A])
    pixels, _ = ws.parse_pgm(data)
    assert pixels.tolist() == [[0x23, 0x0A]]
    data = b"P5 2 1 255 " + bytes([0x20, 0x23])  # one whitespace byte, then the raster
    pixels, _ = ws.parse_pgm(data)
    assert pixels.tolist() == [[0x20, 0x23]]


def test_parse_pgm_sixteen_bit_is_big_endian() -> None:
    data = p5(2, 1, 1000, [1, 999])
    pixels, maxval = ws.parse_pgm(data)
    assert maxval == 1000
    assert pixels.tolist() == [[1, 999]]
    data = b"P5 1 1 65535\n" + bytes([0x01, 0x02])
    pixels, maxval = ws.parse_pgm(data)
    assert pixels.tolist() == [[0x0102]] and maxval == 65535
    data = b"P5 1 1 256\n" + bytes([0x01, 0x00])
    assert ws.parse_pgm(data)[0].tolist() == [[256]]


def test_parse_pgm_ascii() -> None:
    data = b"P2\n# comment\n3 2\n7\n0 1 2 # inline\n5\n6 7\n"
    pixels, maxval = ws.parse_pgm(data)
    assert maxval == 7
    assert pixels.tolist() == [[0, 1, 2], [5, 6, 7]]
    assert ws.parse_pgm(b"P2 1 1 255 3")[0].tolist() == [[3]]
    assert ws.parse_pgm(b"P2\r\n1 1\r\n255\r\n3\r\n")[0].tolist() == [[3]]


BAD_PGM = {
    "empty": b"",
    "magic": b"P6\n1 1\n255\n\x00\x00\x00",
    "magic-text": b"hello",
    "no-dims": b"P5\n",
    "one-dim": b"P5\n3\n",
    "no-maxval": b"P5\n1 1\n",
    "zero-width": b"P5\n0 1\n255\n",
    "zero-height": b"P5\n1 0\n255\n",
    "negative": b"P5\n-1 1\n255\n\x00",
    "maxval-zero": b"P5\n1 1\n0\n\x00",
    "maxval-big": b"P5\n1 1\n65536\n\x00\x00",
    "short-raster": b"P5\n2 2\n255\n\x00\x00\x00",
    "short-raster-16": b"P5\n1 1\n300\n\x01",
    "long-raster": b"P5\n1 1\n255\n\x00\x00",
    "non-numeric": b"P5\nx 1\n255\n\x00",
    "float-dim": b"P5\n1.5 1\n255\n\x00",
    "plus-sign": b"P5\n+1 1\n255\n\x00",
    "ascii-short": b"P2\n2 1\n255\n1\n",
    "ascii-long": b"P2\n1 1\n255\n1 2\n",
    "ascii-over-maxval": b"P2\n1 1\n7\n8\n",
    "ascii-negative": b"P2\n1 1\n7\n-1\n",
    "ascii-word": b"P2\n1 1\n7\nabc\n",
    "binary-over-maxval": b"P5\n1 1\n7\n\x08",
    "header-no-whitespace": b"P51 1 255\n\x00",
    "huge-dims": b"P5\n999999999 999999999\n255\n",
    "huge-number": b"P5\n" + b"9" * 400 + b" 1\n255\n",
    "only-comment": b"P5\n# 1 1 255\n",
}


@pytest.mark.parametrize("name", sorted(BAD_PGM))
def test_parse_pgm_rejects_malformed_input(name: str) -> None:
    with pytest.raises(ws.ScenarioError):
        ws.parse_pgm(BAD_PGM[name])


@pytest.mark.parametrize("bad", [None, "P5", 5, [1], bytearray(b"P5 1 1 255 \x00")])
def test_parse_pgm_requires_bytes(bad: object) -> None:
    with pytest.raises(ws.ScenarioError):
        ws.parse_pgm(bad)  # type: ignore[arg-type]


def test_parse_pgm_size_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ws, "MAX_GRID_CELLS", 6)
    assert ws.parse_pgm(p5(3, 2, 255, [0] * 6))[0].shape == (2, 3)
    with pytest.raises(ws.ScenarioError, match="cells"):
        ws.parse_pgm(p5(7, 1, 255, [0] * 7))
    with pytest.raises(ws.ScenarioError, match="cells"):
        ws.parse_pgm(p5(1, 7, 255, [0] * 7))
    with pytest.raises(ws.ScenarioError, match="cells"):
        ws.parse_pgm(b"P2 100000 100000 255 ")


def test_parse_pgm_returns_read_only_unsigned_pixels() -> None:
    pixels, _ = ws.parse_pgm(p5(2, 1, 255, [1, 2]))
    assert pixels.dtype == np.uint16
    assert not pixels.flags.writeable


# ----------------------------------------------------------------------------------------------
# Occupancy grid, free cells, poses
# ----------------------------------------------------------------------------------------------


def grid_from(
    rows: list[list[int]],
    *,
    maxval: int = 255,
    resolution: float = 1.0,
    origin: tuple[float, float] = (0.0, 0.0),
    negate: int = 0,
    free_thresh: float = 0.25,
    occupied_thresh: float = 0.65,
) -> ws.OccupancyGrid:
    return ws.occupancy_grid_from_pixels(
        np.array(rows, dtype=np.uint16),
        maxval,
        resolution=resolution,
        origin=origin,
        negate=negate,
        free_thresh=free_thresh,
        occupied_thresh=occupied_thresh,
    )


def test_pixel_to_occupancy_follows_the_map_server_convention() -> None:
    # maxval 4: shade = pixel / 4 and, with negate 0, occupancy = 1 - shade
    # pixel 4 -> 0.0 (free), 3 -> 0.25, 2 -> 0.5, 1 -> 0.75, 0 -> 1.0 (occupied)
    grid = grid_from(
        [[4, 3, 2, 1, 0]], maxval=4, free_thresh=0.25, occupied_thresh=0.65
    )
    assert grid.free.tolist() == [[True, False, False, False, False]]
    assert grid.occupied.tolist() == [[False, False, False, True, True]]


def test_thresholds_are_strict() -> None:
    # occupancy exactly at free_thresh is NOT free; exactly at occupied_thresh is NOT occupied
    grid = grid_from([[3, 2, 1]], maxval=4, free_thresh=0.25, occupied_thresh=0.75)
    assert grid.free.tolist() == [[False, False, False]]
    assert grid.occupied.tolist() == [[False, False, False]]
    grid = grid_from([[3, 2, 1]], maxval=4, free_thresh=0.5, occupied_thresh=0.75)
    assert grid.free.tolist() == [[True, False, False]]
    grid = grid_from([[3, 2, 1, 0]], maxval=4, free_thresh=0.25, occupied_thresh=0.5)
    assert grid.occupied.tolist() == [[False, False, True, True]]


def test_negate_flips_the_reading() -> None:
    grid = grid_from(
        [[0, 1, 2, 3, 4]], maxval=4, negate=1, free_thresh=0.25, occupied_thresh=0.65
    )
    # negate 1: occupancy = shade, so pixel 0 is free and pixel 4 is occupied
    assert grid.free.tolist() == [[True, False, False, False, False]]
    assert grid.occupied.tolist() == [[False, False, False, True, True]]


def test_unknown_cells_are_neither_free_nor_occupied() -> None:
    grid = grid_from([[2]], maxval=4, free_thresh=0.25, occupied_thresh=0.75)
    assert not grid.free[0, 0] and not grid.occupied[0, 0]
    assert not ws.pose_is_free(grid, ws.Pose2D(0.5, 0.5, 0))
    assert not ws.pose_is_occupied(grid, ws.Pose2D(0.5, 0.5, 0))


def test_the_default_thresholds_of_nav2_treat_gray_205_as_free() -> None:
    # with free_thresh 0.25 a pixel of 205 reads as occupancy 0.196, below the threshold: free
    grid = grid_from(
        [[205, 254, 0, 100]], maxval=255, free_thresh=0.25, occupied_thresh=0.65
    )
    assert grid.free.tolist() == [[True, True, False, False]]
    assert grid.occupied.tolist() == [[False, False, True, False]]


def test_grid_arrays_are_read_only_and_shaped_like_the_image() -> None:
    grid = grid_from([[255, 0, 255], [0, 255, 0]])
    assert grid.free.shape == (2, 3) and grid.occupied.shape == (2, 3)
    assert grid.free.dtype == np.bool_ and grid.occupied.dtype == np.bool_
    assert not grid.free.flags.writeable and not grid.occupied.flags.writeable
    with pytest.raises(dataclasses.FrozenInstanceError):
        grid.resolution = 2.0  # type: ignore[misc]


# image rows from top; row 0 is the top (largest y). Pixels: 255 free, 0 occupied.
FIVE = [
    [0, 0, 0, 0, 0],
    [0, 255, 255, 255, 0],
    [0, 255, 0, 255, 0],
    [0, 255, 255, 255, 0],
    [0, 0, 0, 0, 0],
]


def test_pose_to_cell_uses_origin_resolution_and_a_flipped_row_axis() -> None:
    grid = grid_from(FIVE, resolution=0.5, origin=(10.0, -4.0))
    # x in [10, 12.5), y in [-4, -1.5); the bottom image row is the lowest y
    assert ws.cell_of(grid, ws.Pose2D(10.0, -4.0, 0.0)) == (4, 0)
    assert ws.cell_of(grid, ws.Pose2D(10.49, -3.51, 0.0)) == (4, 0)
    assert ws.cell_of(grid, ws.Pose2D(10.5, -3.5, 0.0)) == (3, 1)
    assert ws.cell_of(grid, ws.Pose2D(12.49, -1.51, 0.0)) == (0, 4)
    assert ws.cell_of(grid, ws.Pose2D(11.2, -2.7, 0.0)) == (2, 2)
    # outside: one cell width beyond each edge, and exactly on the far edges
    for x, y in [
        (9.99, -3.0),
        (12.5, -3.0),
        (11.0, -4.01),
        (11.0, -1.5),
        (-100.0, 50.0),
    ]:
        assert ws.cell_of(grid, ws.Pose2D(x, y, 0.0)) is None


def test_pose_is_free_on_a_five_by_five_map() -> None:
    grid = grid_from(FIVE)
    assert ws.pose_is_free(grid, ws.Pose2D(1.5, 3.5, 0.0))  # row 1, col 1
    assert not ws.pose_is_free(grid, ws.Pose2D(2.5, 2.5, 0.0))  # centre block
    assert not ws.pose_is_free(grid, ws.Pose2D(0.5, 0.5, 0.0))  # corner wall
    assert ws.pose_is_free(grid, ws.Pose2D(3.9, 1.1, 0.0))  # row 3, col 3
    assert not ws.pose_is_free(
        grid, ws.Pose2D(5.0, 2.5, 0.0)
    )  # on the far edge: outside
    assert not ws.pose_is_free(grid, ws.Pose2D(-0.1, 2.5, 0.0))  # outside
    assert ws.pose_is_occupied(grid, ws.Pose2D(2.5, 2.5, 0.0))
    assert not ws.pose_is_occupied(grid, ws.Pose2D(1.5, 1.5, 0.0))
    assert not ws.pose_is_occupied(
        grid, ws.Pose2D(50.0, 2.5, 0.0)
    )  # outside is not occupied


def test_pose_is_free_ignores_the_heading() -> None:
    grid = grid_from(FIVE)
    for yaw in (-math.pi, 0.0, 1.0, math.pi):
        assert ws.pose_is_free(grid, ws.Pose2D(1.5, 3.5, yaw))


def test_pose_functions_require_the_types() -> None:
    grid = grid_from(FIVE)
    for call in (ws.pose_is_free, ws.pose_is_occupied, ws.cell_of):
        with pytest.raises(ws.ScenarioError):
            call(grid, (1.5, 3.5, 0.0))  # type: ignore[arg-type]
        with pytest.raises(ws.ScenarioError):
            call("grid", ws.Pose2D(1.5, 3.5, 0.0))  # type: ignore[arg-type]


def test_reachable_from_open_ring() -> None:
    grid = grid_from(FIVE)
    start = ws.Pose2D(1.5, 3.5, 0.0)
    goals = [
        ws.Pose2D(3.5, 1.5, 0.0),
        ws.Pose2D(1.5, 1.5, 0.0),
        ws.Pose2D(3.5, 3.5, 0.0),
    ]
    assert ws.reachable_from(grid, start, goals) == [True, True, True]
    assert ws.reachable_from(grid, start, []) == []
    # the start itself is reachable from itself
    assert ws.reachable_from(grid, start, [start]) == [True]


def test_goals_on_walls_or_outside_are_not_reachable() -> None:
    grid = grid_from(FIVE)
    start = ws.Pose2D(1.5, 3.5, 0.0)
    goals = [
        ws.Pose2D(2.5, 2.5, 0.0),
        ws.Pose2D(0.5, 0.5, 0.0),
        ws.Pose2D(9.0, 9.0, 0.0),
        ws.Pose2D(-1, -1, 0),
    ]
    assert ws.reachable_from(grid, start, goals) == [False, False, False, False]


def test_start_not_on_a_free_cell_reaches_nothing() -> None:
    grid = grid_from(FIVE)
    goals = [ws.Pose2D(1.5, 3.5, 0.0), ws.Pose2D(2.5, 2.5, 0.0)]
    assert ws.reachable_from(grid, ws.Pose2D(0.5, 0.5, 0.0), goals) == [False, False]
    assert ws.reachable_from(grid, ws.Pose2D(9.0, 9.0, 0.0), goals) == [False, False]
    assert ws.reachable_from(grid, ws.Pose2D(2.5, 2.5, 0.0), goals) == [False, False]


def test_a_wall_splits_the_map() -> None:
    rows = [
        [255, 255, 0, 255, 255],
        [255, 255, 0, 255, 255],
        [255, 255, 0, 255, 255],
        [255, 255, 0, 255, 255],
        [255, 255, 0, 255, 255],
    ]
    grid = grid_from(rows)
    left, right = ws.Pose2D(0.5, 2.5, 0.0), ws.Pose2D(4.5, 2.5, 0.0)
    assert ws.reachable_from(grid, left, [ws.Pose2D(1.5, 0.5, 0.0), right]) == [
        True,
        False,
    ]
    assert ws.reachable_from(grid, right, [left, ws.Pose2D(3.5, 4.5, 0.0)]) == [
        False,
        True,
    ]


def test_unknown_cells_do_not_connect() -> None:
    rows = [[255, 128, 255]]
    grid = grid_from(rows, maxval=255, free_thresh=0.25, occupied_thresh=0.65)
    # pixel 128 is occupancy 0.498: unknown, not traversable
    assert ws.reachable_from(
        grid, ws.Pose2D(0.5, 0.5, 0), [ws.Pose2D(2.5, 0.5, 0)]
    ) == [False]


def test_a_gap_that_touches_only_at_a_corner_is_not_passable_by_default() -> None:
    # two free cells touch diagonally; both orthogonal cells between them are occupied
    rows = [
        [255, 0, 0],
        [0, 255, 0],
        [0, 0, 255],
    ]
    grid = grid_from(rows)
    top_left, centre, bottom_right = (
        ws.Pose2D(0.5, 2.5, 0.0),
        ws.Pose2D(1.5, 1.5, 0.0),
        ws.Pose2D(2.5, 0.5, 0.0),
    )
    # policy: no squeezing between two occupied corners
    assert ws.reachable_from(grid, top_left, [centre, bottom_right]) == [False, False]
    # the permissive variant moves diagonally whenever the target cell is free
    assert ws.reachable_from(
        grid, top_left, [centre, bottom_right], diagonal_squeeze=True
    ) == [True, True]


def test_a_corner_with_one_free_neighbour_is_walked_around() -> None:
    # one orthogonal neighbour is occupied: the route goes through the free one
    rows = [
        [255, 0],
        [255, 255],
    ]
    grid = grid_from(rows)
    a, d = ws.Pose2D(0.5, 1.5, 0.0), ws.Pose2D(1.5, 0.5, 0.0)
    assert ws.reachable_from(grid, a, [d]) == [True]  # down, then right


def test_long_corridor_is_traversed_end_to_end_and_bounds_hold() -> None:
    rows = [[255] * 40]
    grid = grid_from(rows, resolution=0.25)
    assert ws.reachable_from(
        grid, ws.Pose2D(0.1, 0.1, 0), [ws.Pose2D(9.9, 0.1, 0)]
    ) == [True]
    assert ws.reachable_from(
        grid, ws.Pose2D(0.1, 0.1, 0), [ws.Pose2D(10.1, 0.1, 0)]
    ) == [False]


def test_reachable_from_requires_valid_arguments() -> None:
    grid = grid_from(FIVE)
    ok = ws.Pose2D(1.5, 3.5, 0.0)
    with pytest.raises(ws.ScenarioError):
        ws.reachable_from(grid, (1.5, 3.5), [ok])  # type: ignore[arg-type]
    with pytest.raises(ws.ScenarioError):
        ws.reachable_from(grid, ok, [(1.5, 3.5)])  # type: ignore[list-item]
    with pytest.raises(ws.ScenarioError):
        ws.reachable_from(grid, ok, None)  # type: ignore[arg-type]
    with pytest.raises(ws.ScenarioError):
        ws.reachable_from("grid", ok, [ok])  # type: ignore[arg-type]


# map YAML + PGM files


def write_map(
    tmp_path: Path,
    rows: list[list[int]] | None = None,
    *,
    yaml_overrides: dict[str, object] | None = None,
    drop: tuple[str, ...] = (),
    image_name: str = "m.pgm",
    name: str = "m.yaml",
) -> Path:
    rows = rows if rows is not None else FIVE
    (tmp_path / image_name).write_bytes(
        p5(len(rows[0]), len(rows), 255, [v for row in rows for v in row])
    )
    doc: dict[str, object] = {
        "image": image_name,
        "mode": "trinary",
        "resolution": 0.5,
        "origin": [10.0, -4.0, 0.0],
        "negate": 0,
        "occupied_thresh": 0.65,
        "free_thresh": 0.25,
    }
    doc.update(yaml_overrides or {})
    for key in drop:
        doc.pop(key, None)
    path = tmp_path / name
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return path


def test_load_occupancy_grid_reads_the_map_yaml_fields(tmp_path: Path) -> None:
    grid = ws.load_occupancy_grid(write_map(tmp_path))
    assert grid.resolution == 0.5
    assert (grid.origin_x, grid.origin_y) == (10.0, -4.0)
    assert grid.free.shape == (5, 5)
    assert ws.pose_is_free(
        grid, ws.Pose2D(11.2, -2.2, 0.0)
    )  # col 2.4 -> 2? row: see FIVE
    assert not ws.pose_is_free(grid, ws.Pose2D(11.2, -2.7, 0.0))  # centre block


def test_map_yaml_without_mode_is_trinary_and_negate_may_be_boolean(
    tmp_path: Path,
) -> None:
    grid = ws.load_occupancy_grid(write_map(tmp_path, drop=("mode",)))
    assert grid.free.shape == (5, 5)
    flipped = ws.load_occupancy_grid(
        write_map(tmp_path, yaml_overrides={"negate": True})
    )
    assert flipped.occupied[1, 1] and not flipped.free[1, 1]
    assert flipped.free[0, 0] and not flipped.occupied[0, 0]
    kept = ws.load_occupancy_grid(write_map(tmp_path, yaml_overrides={"negate": False}))
    assert kept.free[1, 1]


MAP_REQUIRED = (
    "image",
    "resolution",
    "origin",
    "negate",
    "occupied_thresh",
    "free_thresh",
)


@pytest.mark.parametrize("key", MAP_REQUIRED)
def test_map_yaml_keys_are_required(tmp_path: Path, key: str) -> None:
    with pytest.raises(ws.ScenarioError, match=key):
        ws.load_occupancy_grid(write_map(tmp_path, drop=(key,)))


@pytest.mark.parametrize(
    "override",
    [
        {"mode": "scale"},
        {"mode": "raw"},
        {"mode": "Trinary"},
        {"mode": None},
        {"resolution": 0},
        {"resolution": -0.05},
        {"resolution": float("nan")},
        {"resolution": float("inf")},
        {"resolution": "0.05"},
        {"resolution": True},
        {"resolution": None},
        {"origin": [0.0, 0.0]},
        {"origin": [0.0, 0.0, 0.0, 0.0]},
        {"origin": [0.0, 0.0, 0.5]},
        {"origin": [0.0, 0.0, -0.5]},
        {"origin": [0.0, "a", 0.0]},
        {"origin": [0.0, float("nan"), 0.0]},
        {"origin": [True, 0.0, 0.0]},
        {"origin": "0 0 0"},
        {"origin": None},
        {"negate": 2},
        {"negate": -1},
        {"negate": 0.5},
        {"negate": "0"},
        {"negate": None},
        {"free_thresh": -0.1},
        {"free_thresh": 0.65},
        {"free_thresh": 0.9},
        {"free_thresh": float("nan")},
        {"free_thresh": "0.25"},
        {"free_thresh": True},
        {"occupied_thresh": 1.5},
        {"occupied_thresh": 0.25},
        {"occupied_thresh": 0.2},
        {"occupied_thresh": float("nan")},
        {"occupied_thresh": "0.65"},
        {"image": "sub/m.pgm"},
        {"image": "../m.pgm"},
        {"image": ""},
        {"image": None},
        {"image": 5},
        {"image": "missing.pgm"},
        {"surprise": 1},
    ],
    ids=lambda d: next(iter(d)) + "=" + repr(next(iter(d.values()))),
)
def test_map_yaml_value_errors(tmp_path: Path, override: dict[str, object]) -> None:
    with pytest.raises(ws.ScenarioError) as info:
        ws.load_occupancy_grid(write_map(tmp_path, yaml_overrides=override))
    assert next(iter(override)) in str(info.value)


def test_map_yaml_accepts_the_threshold_edges(tmp_path: Path) -> None:
    ws.load_occupancy_grid(
        write_map(tmp_path, yaml_overrides={"free_thresh": 0.0, "occupied_thresh": 1.0})
    )
    ws.load_occupancy_grid(
        write_map(
            tmp_path, yaml_overrides={"free_thresh": 0.0, "occupied_thresh": 0.001}
        )
    )
    with pytest.raises(ws.ScenarioError):
        ws.load_occupancy_grid(
            write_map(
                tmp_path, yaml_overrides={"free_thresh": 0.5, "occupied_thresh": 0.5}
            )
        )


def test_map_yaml_integer_origin_and_resolution_are_accepted(tmp_path: Path) -> None:
    grid = ws.load_occupancy_grid(
        write_map(tmp_path, yaml_overrides={"resolution": 1, "origin": [1, 2, 0]})
    )
    assert grid.resolution == 1.0 and (grid.origin_x, grid.origin_y) == (1.0, 2.0)


def test_map_loader_is_as_strict_as_the_scenario_loader(tmp_path: Path) -> None:
    path = write_map(tmp_path)
    text = path.read_text()
    path.write_text(text + "resolution: 0.1\n")
    with pytest.raises(ws.ScenarioError, match="duplicate"):
        ws.load_occupancy_grid(path)
    path.write_text("[]\n")
    with pytest.raises(ws.ScenarioError):
        ws.load_occupancy_grid(path)
    with pytest.raises(ws.ScenarioError):
        ws.load_occupancy_grid(tmp_path / "missing.yaml")
    with pytest.raises(ws.ScenarioError):
        ws.load_occupancy_grid(None)  # type: ignore[arg-type]
    big = tmp_path / "big.yaml"
    big.write_bytes(b"#" + b"a" * ws.MAX_FILE_BYTES)
    with pytest.raises(ws.ScenarioError, match="larger than"):
        ws.load_occupancy_grid(big)


def test_a_corrupt_or_oversized_image_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = write_map(tmp_path)
    (tmp_path / "m.pgm").write_bytes(b"P5\n5 5\n255\n\x00")
    with pytest.raises(ws.ScenarioError):
        ws.load_occupancy_grid(path)
    path = write_map(tmp_path)
    monkeypatch.setattr(ws, "MAX_PGM_BYTES", 10)
    with pytest.raises(ws.ScenarioError, match="larger than"):
        ws.load_occupancy_grid(path)
    monkeypatch.undo()
    (tmp_path / "m.pgm").unlink()
    (tmp_path / "m.pgm").mkdir()
    with pytest.raises(ws.ScenarioError, match="not a regular file"):
        ws.load_occupancy_grid(path)


def test_the_map_image_is_found_next_to_the_yaml(tmp_path: Path) -> None:
    sub = tmp_path / "maps"
    sub.mkdir()
    path = write_map(sub, image_name="a.pgm", name="a.yaml")
    assert ws.load_occupancy_grid(path).free.shape == (5, 5)


# ----------------------------------------------------------------------------------------------
# Shipped scenario, world and map (committed files only)
# ----------------------------------------------------------------------------------------------


def shipped() -> ws.WardScenario:
    return ws.load_scenario(SCENARIO_PATH)


def shipped_grid() -> ws.OccupancyGrid:
    return ws.load_occupancy_grid(WORLDS_DIR / shipped().map_file)


def header_comment() -> str:
    lines = []
    for line in SCENARIO_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or (line.strip() == "" and lines):
            lines.append(line)
        else:
            break
    return "\n".join(lines)


def test_shipped_scenario_loads_and_has_four_to_eight_rooms() -> None:
    scenario = shipped()
    assert 4 <= len(scenario.rooms) <= 8


def test_shipped_scenario_room_count_recorded() -> None:
    found = re.findall(
        r"^#\s*Number of rooms:\s*(\d+)\s*$", header_comment(), re.MULTILINE
    )
    assert len(found) == 1, (
        "the header comment must state 'Number of rooms: N' exactly once"
    )
    count = int(found[0])
    assert 4 <= count <= 8
    assert count == len(shipped().rooms)


def test_shipped_scenario_records_the_dry_drive_time() -> None:
    found = re.findall(
        r"^#\s*Dry-drive time dock to farthest door:\s*(\d+) ms of simulation time",
        header_comment(),
        re.MULTILINE,
    )
    assert len(found) == 1, (
        "the header comment must record the measured dry-drive time once"
    )
    assert 0 < int(found[0]) < shipped().nav_goal_timeout_ms


def test_shipped_scenario_marks_placeholder_slots() -> None:
    text = SCENARIO_PATH.read_text(encoding="utf-8")
    assert "PLACEHOLDER" in text and "WS04-T11" in text


def test_room_poses_in_free_cells_of_map() -> None:
    scenario, grid = shipped(), shipped_grid()
    assert ws.pose_is_free(grid, scenario.dock), "dock"
    for room in scenario.rooms:
        assert ws.pose_is_free(grid, room.door), room.room_id + " door"
        assert ws.pose_is_free(grid, room.bedside), room.room_id + " bedside"


def test_bed_and_dispenser_poses_are_furniture_inside_the_map() -> None:
    scenario, grid = shipped(), shipped_grid()
    for room in scenario.rooms:
        for name in ("bed", "dispenser"):
            cell = ws.cell_of(grid, getattr(room, name))
            assert cell is not None, f"{room.room_id} {name} outside the map"
            assert grid.occupied[cell], f"{room.room_id} {name} is not on furniture"


def test_unreachable_pose_is_occupied_or_outside_map() -> None:
    scenario, grid = shipped(), shipped_grid()
    pose_ = scenario.unreachable_pose
    assert ws.pose_is_occupied(grid, pose_) or ws.cell_of(grid, pose_) is None
    assert not ws.pose_is_free(grid, pose_)


def test_every_door_connected_to_dock_in_free_space() -> None:
    scenario, grid = shipped(), shipped_grid()
    doors = [room.door for room in scenario.rooms]
    bedsides = [room.bedside for room in scenario.rooms]
    assert all(ws.reachable_from(grid, scenario.dock, doors))
    assert all(ws.reachable_from(grid, scenario.dock, bedsides))
    assert ws.reachable_from(grid, scenario.dock, [scenario.unreachable_pose]) == [
        False
    ]


def test_door_poses_are_further_apart_than_twice_the_goal_tolerance() -> None:
    # Nav2's goal tolerance is 0.25 m (config/nav2_params.yaml): two door poses closer than twice
    # that could not be told apart by "the robot is within the tolerance of this pose"
    scenario = shipped()
    points = [(room.door.x, room.door.y) for room in scenario.rooms]
    for i, a in enumerate(points):
        for b in points[i + 1 :]:
            assert math.dist(a, b) > 0.5


def test_shipped_pose_names_are_the_frozen_list() -> None:
    # WS10-T01 mirrors one room of this world; these names must not change
    assert [f.name for f in ws.Room.__dataclass_fields__.values()][:2] == [
        "room_id",
        "patient_id",
    ]
    names = set(ws.Room.__dataclass_fields__)
    assert {"door", "bedside", "bed", "dispenser"} <= names
    assert {"dock", "unreachable_pose"} <= set(ws.WardScenario.__dataclass_fields__)
    assert ws.POSE_NAMES == ("door", "bedside", "bed", "dispenser")


def test_shipped_files_exist_and_worlds_has_no_subdirectory() -> None:
    scenario = shipped()
    for name in (scenario.world_file, scenario.map_file, "NOTICE"):
        assert (WORLDS_DIR / name).is_file(), name
    image = yaml.safe_load((WORLDS_DIR / scenario.map_file).read_text())["image"]
    assert (WORLDS_DIR / image).is_file()
    # setup.py installs worlds/* with a glob that skips directories
    assert [
        p.name for p in WORLDS_DIR.iterdir() if p.is_dir() and p.name != "__pycache__"
    ] == []


def test_every_numeric_value_has_a_provenance_comment() -> None:
    """Each scalar of the scenario sits under a comment that says where it comes from."""
    lines = SCENARIO_PATH.read_text(encoding="utf-8").splitlines()
    keys = (
        "compression_factor",
        "replay_start_ms",
        "spacing_ms",
        "step_ms",
        "reorder_delay_ms",
        "predictive",
        "alpha",
        "variant",
        "registry_version",
        "startup_timeout_ms",
        "nav_goal_timeout_ms",
        "care_plan_time_entries",
        "physical_time_entries",
    )
    for key in keys:
        indexes = [i for i, line in enumerate(lines) if re.match(rf"^\s*{key}:", line)]
        assert len(indexes) == 1, key
        block: list[str] = []
        i = indexes[0] - 1
        while i >= 0 and lines[i].lstrip().startswith("#"):
            block.append(lines[i])
            i -= 1
        text = " ".join(block).lower()
        assert "run parameter" in text or "source:" in text, (
            f"{key}: no provenance comment"
        )


def test_slots_are_declared_placeholders_not_manifest_values() -> None:
    scenario = shipped()
    assert all(room.patient_id.startswith("slot-") for room in scenario.rooms)


# ----------------------------------------------------------------------------------------------
# Consistency with the parameter registry (a data file; no import of ralmon)
# ----------------------------------------------------------------------------------------------


def registry() -> dict[str, Any]:
    loaded = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_every_ms_registry_entry_is_classified_exactly_once() -> None:
    reg = registry()
    ms_names = {e["name"] for e in reg["entries"] if e["unit"] == "ms"}
    scenario = shipped()
    care = set(scenario.care_plan_time_entries)
    physical = set(scenario.physical_time_entries)
    assert care.isdisjoint(physical)
    assert care | physical == ms_names, (
        "unclassified: "
        + str(sorted(ms_names - care - physical))
        + "; not ms entries: "
        + str(sorted((care | physical) - ms_names))
    )


def test_registry_version_matches_the_registry_file() -> None:
    assert shipped().monitor.registry_version == str(registry()["registry_version"])


def test_window_parameters_stay_multiples_of_the_step_after_compression() -> None:
    reg = registry()
    scenario = shipped()
    entries = {e["name"]: e["value"] for e in reg["entries"]}
    factor, step = scenario.compression_factor, scenario.monitor.step_ms
    for name in reg["window_parameters"]:
        assert name in scenario.care_plan_time_entries, name
        compressed = entries[name] / factor
        assert compressed == int(compressed), name
        assert int(compressed) % step == 0, (name, compressed, step)


def test_compressed_step_is_the_fixture_step_divided_by_the_factor() -> None:
    # docs/formal/01-signals-sampling.md section 1: T_s = 60000 ms in trace time (FIXTURE-ONLY)
    scenario = shipped()
    assert scenario.monitor.step_ms * scenario.compression_factor == 60_000


# ----------------------------------------------------------------------------------------------
# The generator of the world and the map
# ----------------------------------------------------------------------------------------------


def load_generator() -> Any:
    name = "t07_generate_ward_world"
    spec = importlib.util.spec_from_file_location(name, GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_generator_reproduces_the_committed_world_and_map_byte_for_byte(
    tmp_path: Path,
) -> None:
    gen = load_generator()
    scenario = shipped()
    assert gen.main(["--rooms", str(len(scenario.rooms)), "--out", str(tmp_path)]) == 0
    for name in (scenario.world_file, scenario.map_file, "ward_map.pgm"):
        assert (tmp_path / name).read_bytes() == (WORLDS_DIR / name).read_bytes(), name


def test_generator_check_mode_reports_a_difference(tmp_path: Path) -> None:
    gen = load_generator()
    scenario = shipped()
    n = str(len(scenario.rooms))
    assert gen.main(["--rooms", n, "--out", str(WORLDS_DIR), "--check"]) == 0
    gen.main(["--rooms", n, "--out", str(tmp_path)])
    (tmp_path / scenario.world_file).write_text("changed\n")
    assert gen.main(["--rooms", n, "--out", str(tmp_path), "--check"]) == 1
    (tmp_path / scenario.world_file).unlink()
    assert gen.main(["--rooms", n, "--out", str(tmp_path), "--check"]) == 1


def test_generator_is_deterministic_and_does_not_use_randomness() -> None:
    gen = load_generator()
    a, b = gen.render_world(gen.build_layout(6)), gen.render_world(gen.build_layout(6))
    assert a == b
    assert gen.render_map(gen.build_layout(6)) == gen.render_map(gen.build_layout(6))
    source = GENERATOR_PATH.read_text(encoding="utf-8")
    assert not re.search(
        r"^\s*(import|from)\s+(random|secrets|time|datetime|uuid)\b",
        source,
        re.MULTILINE,
    )
    assert "numpy.random" not in source and "np.random" not in source


def test_generator_rejects_room_counts_outside_four_to_eight() -> None:
    gen = load_generator()
    for n in (0, 3, 9, -1, True, 4.0, "4", None):
        with pytest.raises((ValueError, TypeError)):
            gen.build_layout(n)
    for n in (4, 8):
        gen.build_layout(n)


def test_scenario_poses_equal_the_layout_poses() -> None:
    gen = load_generator()
    scenario = shipped()
    poses = gen.layout_poses(len(scenario.rooms))
    assert tuple(poses["dock"]) == (scenario.dock.x, scenario.dock.y, scenario.dock.yaw)
    assert tuple(poses["unreachable_pose"]) == (
        scenario.unreachable_pose.x,
        scenario.unreachable_pose.y,
        scenario.unreachable_pose.yaw,
    )
    for room in scenario.rooms:
        for name in ws.POSE_NAMES:
            p = getattr(room, name)
            assert tuple(poses[f"{room.room_id}.{name}"]) == (p.x, p.y, p.yaw), (
                room.room_id,
                name,
            )
    assert len(poses) == 2 + 4 * len(scenario.rooms)


@pytest.mark.parametrize("n_rooms", [4, 5, 6, 7, 8])
def test_every_generated_layout_satisfies_the_scenario_conditions(
    tmp_path: Path, n_rooms: int
) -> None:
    gen = load_generator()
    assert gen.main(["--rooms", str(n_rooms), "--out", str(tmp_path)]) == 0
    grid = ws.load_occupancy_grid(tmp_path / "ward_map.yaml")
    poses = gen.layout_poses(n_rooms)
    to_pose = {k: ws.Pose2D(*v) for k, v in poses.items()}
    rooms = sorted({k.split(".")[0] for k in poses if "." in k})
    assert len(rooms) == n_rooms
    dock = to_pose["dock"]
    assert ws.pose_is_free(grid, dock)
    for room in rooms:
        assert ws.pose_is_free(grid, to_pose[f"{room}.door"]), room
        assert ws.pose_is_free(grid, to_pose[f"{room}.bedside"]), room
        assert ws.pose_is_occupied(grid, to_pose[f"{room}.bed"]), room
        assert ws.pose_is_occupied(grid, to_pose[f"{room}.dispenser"]), room
    reach = ws.reachable_from(
        grid,
        dock,
        [to_pose[f"{r}.door"] for r in rooms]
        + [to_pose[f"{r}.bedside"] for r in rooms],
    )
    assert all(reach)
    assert ws.pose_is_occupied(grid, to_pose["unreachable_pose"])
    assert ws.reachable_from(grid, dock, [to_pose["unreachable_pose"]]) == [False]


def sdf_boxes(world: Path) -> list[tuple[float, float, float, float]]:
    """Axis-aligned collision boxes (x0, y0, x1, y1) read from the SDF text, without rotation."""
    root = ET.parse(world).getroot()
    boxes = []
    for model in root.iter("model"):
        if model.get("name") == "ground_plane":
            continue
        model_pose = [
            float(v) for v in (model.findtext("pose") or "0 0 0 0 0 0").split()
        ]
        for link in model.iter("link"):
            link_pose = [
                float(v) for v in (link.findtext("pose") or "0 0 0 0 0 0").split()
            ]
            for collision in link.iter("collision"):
                size = collision.find("geometry/box/size")
                if size is None or size.text is None:
                    continue
                sx, sy, _ = (float(v) for v in size.text.split())
                col_pose = [
                    float(v)
                    for v in (collision.findtext("pose") or "0 0 0 0 0 0").split()
                ]
                assert link_pose[3:] == [0.0, 0.0, 0.0] and model_pose[3:] == [
                    0.0,
                    0.0,
                    0.0,
                ]
                assert col_pose[3:] == [0.0, 0.0, 0.0]
                cx = model_pose[0] + link_pose[0] + col_pose[0]
                cy = model_pose[1] + link_pose[1] + col_pose[1]
                boxes.append((cx - sx / 2, cy - sy / 2, cx + sx / 2, cy + sy / 2))
    return boxes


def test_map_is_the_rasterisation_of_the_collision_boxes_of_the_world() -> None:
    scenario = shipped()
    grid = shipped_grid()
    boxes = sdf_boxes(WORLDS_DIR / scenario.world_file)
    assert len(boxes) > 10
    height, width = grid.occupied.shape
    xs = grid.origin_x + (np.arange(width) + 0.5) * grid.resolution
    ys = grid.origin_y + (height - 1 - np.arange(height) + 0.5) * grid.resolution
    expected = np.zeros((height, width), dtype=bool)
    for x0, y0, x1, y1 in boxes:
        inside_x = (xs >= x0) & (xs <= x1)
        inside_y = (ys >= y0) & (ys <= y1)
        expected |= np.outer(inside_y, inside_x)
    assert np.array_equal(grid.occupied, expected)
    # the map has no unknown cells: every cell is either free or occupied
    assert np.all(grid.free | grid.occupied)
    assert not np.any(grid.free & grid.occupied)


def test_world_is_authored_by_the_generator_and_has_no_third_party_reference() -> None:
    scenario = shipped()
    text = (WORLDS_DIR / scenario.world_file).read_text(encoding="utf-8")
    assert "Generated by ros2/ralmon_sim/scripts/generate_ward_world.py" in text
    uris = re.findall(r"<uri>([^<]*)</uri>", text)
    assert uris == [], "the generated world includes no external model: " + str(uris)
    notice = (WORLDS_DIR / "NOTICE").read_text(encoding="utf-8")
    for needle in ("generated", "not cleared", "aws", "LICENSE", "package.xml"):
        assert needle.lower() in notice.lower(), needle


# ----------------------------------------------------------------------------------------------
# Nav2 parameters, launch file, packaging (static checks)
# ----------------------------------------------------------------------------------------------


def walk(node: object):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk(value)


def test_nav2_params_use_sim_time_everywhere() -> None:
    params = yaml.safe_load(NAV2_PARAMS_PATH.read_text(encoding="utf-8"))
    assert isinstance(params, dict)
    seen = 0
    for section in walk(params):
        if "use_sim_time" in section:
            seen += 1
            assert section["use_sim_time"] is True
    assert seen >= 8
    for node in (
        "amcl",
        "map_server",
        "planner_server",
        "controller_server",
        "bt_navigator",
    ):
        assert params[node]["ros__parameters"]["use_sim_time"] is True, node


def test_nav2_params_name_the_shipped_map() -> None:
    params = yaml.safe_load(NAV2_PARAMS_PATH.read_text(encoding="utf-8"))
    assert (
        params["map_server"]["ros__parameters"]["yaml_filename"] == shipped().map_file
    )


def test_planner_does_not_move_goals_out_of_walls() -> None:
    # a goal on an occupied cell must fail; PAL's default tolerance of 0.5 m would relocate it
    params = yaml.safe_load(NAV2_PARAMS_PATH.read_text(encoding="utf-8"))
    planner = params["planner_server"]["ros__parameters"]["GridBased"]
    assert planner["tolerance"] == 0.0


def launch_tree() -> ast.Module:
    return ast.parse(LAUNCH_PATH.read_text(encoding="utf-8"))


def test_launch_declares_scenario_and_headless_but_not_use_humans() -> None:
    declared: set[str] = set()
    for node in ast.walk(launch_tree()):
        if (
            isinstance(node, ast.Call)
            and getattr(node.func, "id", getattr(node.func, "attr", ""))
            == "DeclareLaunchArgument"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            declared.add(str(node.args[0].value))
    assert declared == {"scenario", "headless"}
    text = LAUNCH_PATH.read_text(encoding="utf-8")
    header = text.split('"""', 2)[1] if text.lstrip().startswith('"""') else ""
    assert "use_humans" in header and "human_sim" in header, (
        "the limitation must be stated"
    )
    for node in ast.walk(launch_tree()):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert node.value != "use_humans"


def test_launch_sets_the_ward_epoch_to_zero_and_sim_time_on() -> None:
    text = LAUNCH_PATH.read_text(encoding="utf-8")
    assert re.search(r"ward_epoch_ms[\"'],\s*[\"']0[\"']", text)
    assert re.search(r"use_sim_time[\"'],\s*[\"'](true|True)[\"']", text)


def python_sources() -> list[Path]:
    found = []
    for path in PACKAGE_DIR.rglob("*.py"):
        if (
            "__pycache__" in path.parts
            or "build" in path.parts
            or "install" in path.parts
        ):
            continue
        found.append(path)
    return found


def test_nothing_under_ralmon_sim_imports_ralmon() -> None:
    offenders = []
    for path in python_sources():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""] if node.level == 0 else []
            else:
                continue
            if any(name == "ralmon" or name.startswith("ralmon.") for name in names):
                offenders.append(f"{path.relative_to(PACKAGE_DIR)}:{node.lineno}")
    assert offenders == []


def test_ward_scenario_module_imports_only_the_standard_library_numpy_and_yaml() -> (
    None
):
    allowed = {"numpy", "yaml"}
    tree = ast.parse(
        (PACKAGE_DIR / "ralmon_sim" / "ward_scenario.py").read_text(encoding="utf-8")
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots = [alias.name.split(".")[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            roots = (
                [(node.module or "").split(".")[0]] if node.level == 0 else ["relative"]
            )
        else:
            continue
        for root in roots:
            assert (
                root in allowed
                or root in sys.stdlib_module_names
                or root == "__future__"
            ), root
            assert root not in {"rclpy", "ralmon", "launch", "ament_index_python"}


def test_setup_installs_the_launch_config_and_world_files() -> None:
    tree = ast.parse((PACKAGE_DIR / "setup.py").read_text(encoding="utf-8"))
    text = ast.unparse(tree)
    for needle in ("launch/*.launch.py", "config/*.yaml", "worlds/*"):
        assert needle in text, needle


# ----------------------------------------------------------------------------------------------
# ROS 2 tests: world, robot and Nav2 headless (marker ros; skipped without rclpy)
# ----------------------------------------------------------------------------------------------

# test-only, not clinical and not part of the scenario: how far from a requested pose the robot may
# end (Nav2's own goal tolerance is 0.25 m), the sim-seconds the clock must advance, and the factor
# between a simulation-time timeout and the wall-clock guard of a goal.
POSE_MARGIN_M = 0.5
CLOCK_ADVANCE_S = 1.0
WALL_GUARD_FACTOR = 10
ACTIVE_STATE = 3  # lifecycle_msgs/State.PRIMARY_STATE_ACTIVE
ROBOT_MODEL_NAME = "tiago-pro"  # the model name used by sim_ward.launch.py (and by PAL)
NAV2_LIFECYCLE_NODES = (
    "map_server",
    "amcl",
    "planner_server",
    "controller_server",
    "bt_navigator",
)


class Stack:
    """The running simulation as seen from the test process (rclpy node, clock, Nav2 client)."""

    def __init__(self, scenario: ws.WardScenario, handle: Any) -> None:
        import rclpy
        import rclpy.qos
        from gazebo_msgs.msg import ModelStates
        from nav2_msgs.action import NavigateToPose
        from rclpy.action import ActionClient
        from rosgraph_msgs.msg import Clock

        self.scenario = scenario
        self.handle = handle
        if not rclpy.ok():
            rclpy.init()
        self.rclpy = rclpy
        self.node = rclpy.create_node("ward_world_test")
        self.sim_time_ns = 0
        self.clock_messages = 0
        # gazebo_ros publishes /clock best effort: a default (reliable) subscription never matches
        self.node.create_subscription(
            Clock, "/clock", self._on_clock, rclpy.qos.qos_profile_sensor_data
        )
        # ground truth: the pose of the robot model in the world (world plugin gazebo_ros_state)
        self.truth: tuple[float, float] | None = None
        self.node.create_subscription(
            ModelStates,
            "/gazebo/model_states",
            self._on_model_states,
            rclpy.qos.qos_profile_sensor_data,
        )
        self.nav = ActionClient(self.node, NavigateToPose, "navigate_to_pose")
        self.NavigateToPose = NavigateToPose

    def _on_clock(self, msg: Any) -> None:
        self.sim_time_ns = msg.clock.sec * 1_000_000_000 + msg.clock.nanosec
        self.clock_messages += 1

    def _on_model_states(self, msg: Any) -> None:
        if ROBOT_MODEL_NAME in msg.name:
            position = msg.pose[msg.name.index(ROBOT_MODEL_NAME)].position
            self.truth = (position.x, position.y)

    @property
    def sim_ms(self) -> int:
        return self.sim_time_ns // 1_000_000

    def spin_for(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.rclpy.spin_once(self.node, timeout_sec=0.05)

    def lifecycle_state(self, node_name: str) -> int | None:
        """Lifecycle state id of ``node_name`` (3 is active), or None when it does not answer."""
        from lifecycle_msgs.srv import GetState

        key = "_lifecycle_" + node_name
        client = getattr(self, key, None)
        if client is None:
            client = self.node.create_client(GetState, f"/{node_name}/get_state")
            setattr(self, key, client)
        if not client.wait_for_service(timeout_sec=0.2):
            return None
        future = client.call_async(GetState.Request())
        end = time.monotonic() + 5.0
        while not future.done() and time.monotonic() < end:
            self.rclpy.spin_once(self.node, timeout_sec=0.05)
        if not future.done():
            return None
        return int(future.result().current_state.id)

    def check_alive(self) -> None:
        if not self.handle.alive():
            raise AssertionError("the launch process ended:\n" + self.handle.tail())

    def wait_until(self, predicate: Any, wall_s: float, what: str) -> None:
        end = time.monotonic() + wall_s
        while time.monotonic() < end:
            self.check_alive()
            self.rclpy.spin_once(self.node, timeout_sec=0.1)
            if predicate():
                return
        raise AssertionError(
            f"{what} not reached within {wall_s:.0f} s of wall time\n"
            + self.handle.tail()
        )

    def navigate(self, target: ws.Pose2D, timeout_ms: int) -> tuple[str, int, Any]:
        """Send a NavigateToPose goal; return (outcome, sim ms used, final goal status)."""
        from action_msgs.msg import GoalStatus
        from geometry_msgs.msg import PoseStamped

        goal = self.NavigateToPose.Goal()
        goal.pose = PoseStamped()
        goal.pose.header.frame_id = "map"
        goal.pose.pose.position.x = target.x
        goal.pose.pose.position.y = target.y
        goal.pose.pose.orientation.z = math.sin(target.yaw / 2.0)
        goal.pose.pose.orientation.w = math.cos(target.yaw / 2.0)
        started_ms = self.sim_ms
        wall_end = time.monotonic() + WALL_GUARD_FACTOR * timeout_ms / 1000.0
        send = self.nav.send_goal_async(goal)
        while not send.done():
            self.rclpy.spin_once(self.node, timeout_sec=0.05)
            if time.monotonic() > wall_end:
                raise AssertionError(
                    "no answer to the goal request within the wall-clock guard"
                )
        handle = send.result()
        if not handle.accepted:
            return "rejected", 0, GoalStatus.STATUS_UNKNOWN
        result = handle.get_result_async()
        timed_out = False
        while not result.done():
            self.check_alive()
            self.rclpy.spin_once(self.node, timeout_sec=0.05)
            if self.sim_ms - started_ms > timeout_ms or time.monotonic() > wall_end:
                timed_out = True
                break
        if timed_out:
            cancel = handle.cancel_goal_async()
            cancel_end = time.monotonic() + 60.0
            while not result.done() and time.monotonic() < cancel_end:
                self.rclpy.spin_once(self.node, timeout_sec=0.05)
            status = (
                result.result().status if result.done() else GoalStatus.STATUS_UNKNOWN
            )
            del cancel
            return "timeout", self.sim_ms - started_ms, status
        status = result.result().status
        outcome = "succeeded" if status == GoalStatus.STATUS_SUCCEEDED else "failed"
        return outcome, self.sim_ms - started_ms, status

    def localisation_error(self) -> float:
        """Distance in metres between the AMCL estimate and the model pose (nan when unknown)."""
        estimate = self.robot_pose()
        if estimate is None or self.truth is None:
            return float("nan")
        return math.dist(estimate, self.truth)

    def robot_pose(self) -> tuple[float, float] | None:
        """Latest map-frame position of the robot (AMCL estimate through tf), or None."""
        import tf2_ros
        from rclpy.time import Time

        if not hasattr(self, "_tf_buffer"):
            self._tf_buffer = tf2_ros.Buffer()
            self._tf_listener = tf2_ros.TransformListener(self._tf_buffer, self.node)
            self.spin_for(1.0)
        try:
            transform = self._tf_buffer.lookup_transform(
                "map", "base_footprint", Time()
            )
        except Exception:  # noqa: BLE001 (tf2 raises several types before the first transform)
            return None
        t = transform.transform.translation
        return (t.x, t.y)


@pytest.fixture(scope="module")
def ward_stack(background_launch: Any, display_env: dict[str, str]) -> Any:
    scenario = shipped()
    handle = background_launch(
        [
            "ros2",
            "launch",
            str(LAUNCH_PATH),
            "headless:=true",
            f"scenario:={SCENARIO_PATH}",
        ],
        env=display_env,
        name="sim_ward",
    )
    stack = Stack(scenario, handle)
    yield stack
    stack.node.destroy_node()
    if stack.rclpy.ok():
        stack.rclpy.shutdown()


@pytest.mark.ros
def test_launch_arguments_are_scenario_and_headless_only() -> None:
    result = subprocess.run(
        ["ros2", "launch", str(LAUNCH_PATH), "--show-args"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    names = set(re.findall(r"^\s+'([a-z_]+)':\s*$", result.stdout, re.MULTILINE))
    assert names == {"scenario", "headless"}, result.stdout


@pytest.mark.ros
def test_world_publishes_clock_headless(ward_stack: Stack) -> None:
    wall_s = ward_stack.scenario.startup_timeout_ms / 1000.0
    ward_stack.wait_until(
        lambda: ward_stack.clock_messages > 0, wall_s, "the first /clock message"
    )
    first = ward_stack.sim_time_ns
    ward_stack.wait_until(
        lambda: ward_stack.sim_time_ns - first >= int(CLOCK_ADVANCE_S * 1e9),
        wall_s,
        "a /clock advance",
    )
    assert ward_stack.sim_time_ns > first


def wait_for_navigation(stack: Stack) -> None:
    wall_s = stack.scenario.startup_timeout_ms / 1000.0
    end = time.monotonic() + wall_s
    while not stack.nav.wait_for_server(timeout_sec=1.0):
        stack.check_alive()
        assert time.monotonic() < end, (
            "navigate_to_pose not available\n" + stack.handle.tail()
        )
    for node_name in NAV2_LIFECYCLE_NODES:
        stack.wait_until(
            lambda name=node_name: stack.lifecycle_state(name) == ACTIVE_STATE,
            wall_s,
            f"lifecycle node {node_name} active",
        )
    stack.wait_until(
        lambda: stack.robot_pose() is not None,
        wall_s,
        "a map->base_footprint transform",
    )
    stack.wait_until(lambda: stack.truth is not None, wall_s, "/gazebo/model_states")


@pytest.mark.ros
def test_robot_reaches_every_room_door(ward_stack: Stack) -> None:
    stack = ward_stack
    wait_for_navigation(stack)
    scenario = stack.scenario
    assert stack.truth is not None
    assert math.dist(stack.truth, (scenario.dock.x, scenario.dock.y)) < POSE_MARGIN_M, (
        "the robot is not at the dock"
    )
    # the farthest door first, from the dock: its time is the dry-drive time of the scenario header
    ordered = sorted(
        scenario.rooms,
        key=lambda r: (
            -math.dist((scenario.dock.x, scenario.dock.y), (r.door.x, r.door.y))
        ),
    )
    for index, room in enumerate(ordered):
        outcome, used_ms, _ = stack.navigate(room.door, scenario.nav_goal_timeout_ms)
        stack.spin_for(1.0)
        print(
            f"NAV room={room.room_id} outcome={outcome} sim_ms={used_ms} first_leg={index == 0} "
            f"amcl_error_m={stack.localisation_error():.2f}"
        )
        assert outcome == "succeeded", (
            f"{room.room_id}: {outcome} after {used_ms} sim ms"
        )
        assert used_ms <= scenario.nav_goal_timeout_ms
        # the answer of Nav2 rests on the AMCL pose; the model pose in the world is the test
        assert stack.truth is not None
        assert math.dist(stack.truth, (room.door.x, room.door.y)) < POSE_MARGIN_M, (
            f"{room.room_id}: Nav2 reports success but the robot is at {stack.truth}"
        )


@pytest.mark.ros
def test_robot_reaches_the_bedside_pose_of_every_room(ward_stack: Stack) -> None:
    """The robot task layer (WS07-T04) navigates to the bedside pose: through the door, room to room."""
    stack = ward_stack
    wait_for_navigation(stack)
    scenario = stack.scenario
    for room in scenario.rooms:
        outcome, used_ms, _ = stack.navigate(room.bedside, scenario.nav_goal_timeout_ms)
        stack.spin_for(1.0)
        print(
            f"NAV bedside room={room.room_id} outcome={outcome} sim_ms={used_ms} "
            f"amcl_error_m={stack.localisation_error():.2f}"
        )
        assert outcome == "succeeded", (
            f"{room.room_id}: {outcome} after {used_ms} sim ms"
        )
        assert stack.truth is not None
        assert (
            math.dist(stack.truth, (room.bedside.x, room.bedside.y)) < POSE_MARGIN_M
        ), f"{room.room_id}: Nav2 reports success but the robot is at {stack.truth}"


@pytest.mark.ros
def test_unreachable_pose_goal_does_not_succeed(ward_stack: Stack) -> None:
    stack = ward_stack
    wait_for_navigation(stack)
    target = stack.scenario.unreachable_pose
    outcome, used_ms, status = stack.navigate(
        target, stack.scenario.nav_goal_timeout_ms
    )
    print(f"NAV unreachable outcome={outcome} sim_ms={used_ms} status={status}")
    assert outcome in {"rejected", "failed", "timeout"}
    assert outcome != "succeeded"
    stack.spin_for(1.0)
    assert stack.truth is not None
    assert math.dist(stack.truth, (target.x, target.y)) > POSE_MARGIN_M
