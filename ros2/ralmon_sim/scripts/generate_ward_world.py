#!/usr/bin/env python3
"""Generate the ward world (SDF) and its occupancy map (PGM and map YAML) from one layout (WS07-T02).

    python3 ros2/ralmon_sim/scripts/generate_ward_world.py --rooms 6 [--out DIR] [--check]

The world is a technical test environment, not a model of a real ward: a straight corridor with
rooms on its two sides, built from axis-aligned boxes. Everything is deterministic (integer
arithmetic, no randomness, no clock): the same ``--rooms`` always gives the same bytes. The map is
the rasterisation of the collision boxes of the world, so the world and the map cannot disagree, and
the poses of the scenario file are the poses printed by ``layout_poses``.

Layout (centimetres, map frame = Gazebo world frame; x runs along the corridor)
* the corridor interior is x in [0, XE], y in [-150, 150] (``CORRIDOR_HALF_WIDTH_CM``);
* rooms alternate between the north side (y > 0) and the south side: room ``r01`` is the first
  north room, ``r02`` the first south room, and so on; a room has a 400 x 400 interior and a 180 wide
  door in the middle of its corridor-side wall; walls are 20 thick and 250 high;
* in a room, with ``u`` along +x from the west interior face and ``v`` from the corridor-side
  interior face into the room: bed 100 x 200 against the back wall (u in [290, 390], v in [200, 400]),
  dispenser table 40 x 40 (u in [360, 400], v in [140, 180]); the robot's bedside pose is
  (u 200, v 300), in line with the doorway, facing the bed;
* the door pose is in the corridor in front of the doorway, 110 from the corridor-side wall face,
  facing the doorway (not in the doorway: see the note at ``DOOR_WIDTH_CM``);
* the dock is at x = 100, y = 0 facing +x; the unreachable pose is inside the corridor wall.

All sizes are layout choices of this test environment with no clinical source and no source in the
literature. They were chosen so that the TIAGo Pro (0.70 x 0.48 m footprint in the Nav2 parameters
of PAL) navigates the world with those parameters; the attempts that did not work are in the
completion note of WS07-T02.

Only the Python standard library is used.
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from pathlib import Path

WORLD_FILE = "ward.world"
MAP_YAML_FILE = "ward_map.yaml"
MAP_IMAGE_FILE = "ward_map.pgm"

MIN_ROOMS = 4  # source: analisi section 5.2 ("4-8 stanze")
MAX_ROOMS = 8

# Layout constants, in centimetres (design choices of the test environment)
RESOLUTION_CM = 5  # map resolution: 0.05 m per cell, the resolution of the PAL costmaps
WALL_CM = 20
WALL_HEIGHT_CM = 250
CORRIDOR_HALF_WIDTH_CM = 150
ROOM_INTERIOR_CM = 400
# Corridor, door and stand-off sizes. With a 2.4 m corridor, 1.2 m or 1.6 m doors and the door pose in
# the doorway or 0.6 to 0.9 m from the wall, the robot with the PAL parameters stopped near the pose
# (it must turn 90 degrees to the yaw of the pose within the 0.25 m goal tolerance), the spin
# recovery failed with "Collision Ahead" (the footprint, circumscribed radius 0.42 m, plus the
# inscribed radius 0.24 m does not fit between the pose and a wall) and AMCL jumped by metres in
# the corridor. The sizes below, with AMCL motion noise 0.05 (config/nav2_params.yaml), reach every
# door and bedside pose.
DOOR_WIDTH_CM = 180
# Distance from the corridor-side wall face to the standing point of the door pose, in the corridor
DOOR_STAND_OFF_CM = 110
FIRST_ROOM_X_CM = 300  # west edge of the interior of the first room of each side
MAP_MARGIN_CM = 100
DOCK_X_CM = 100
BED_U_CM = (290, 390)
BED_V_CM = (200, 400)
BED_HEIGHT_CM = 50
TABLE_U_CM = (360, 400)
TABLE_V_CM = (140, 180)
TABLE_HEIGHT_CM = 80
BEDSIDE_U_CM = 200
BEDSIDE_V_CM = 300

# Occupancy map pixel values (the values written by nav2_map_server: free 254, occupied 0)
PIXEL_FREE = 254
PIXEL_OCCUPIED = 0
OCCUPIED_THRESH = "0.65"
FREE_THRESH = "0.25"


@dataclass(frozen=True)
class Box:
    """An axis-aligned box with collision and visual, in centimetres (x0 < x1, y0 < y1)."""

    name: str
    x0: int
    y0: int
    x1: int
    y1: int
    height: int
    color: tuple[float, float, float]


@dataclass(frozen=True)
class Layout:
    n_rooms: int
    boxes: tuple[Box, ...]
    poses: dict[str, tuple[float, float, float]]
    x_min: int
    y_min: int
    x_max: int
    y_max: int


def _check_rooms(n_rooms: object) -> int:
    if type(n_rooms) is not int:
        raise ValueError(f"the number of rooms must be an integer, got {n_rooms!r}")
    if not MIN_ROOMS <= n_rooms <= MAX_ROOMS:
        raise ValueError(
            f"the number of rooms must be {MIN_ROOMS} to {MAX_ROOMS}, got {n_rooms}"
        )
    return n_rooms


def _meters(centimetres: int) -> float:
    """Centimetres as metres: one correctly rounded division, equal to the decimal literal."""
    return centimetres / 100


def _split(lo: int, hi: int, gaps: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """The segments of [lo, hi] left after removing the (sorted, disjoint) gaps."""
    segments = []
    position = lo
    for gap_lo, gap_hi in gaps:
        if gap_lo > position:
            segments.append((position, gap_lo))
        position = gap_hi
    if hi > position:
        segments.append((position, hi))
    return segments


def build_layout(n_rooms: int) -> Layout:
    """The boxes and the named poses of a ward with ``n_rooms`` rooms (4 to 8)."""
    n_rooms = _check_rooms(n_rooms)
    per_side = {1: (n_rooms + 1) // 2, -1: n_rooms // 2}
    longest = max(per_side.values())
    pitch = ROOM_INTERIOR_CM + WALL_CM
    corridor_end = FIRST_ROOM_X_CM + pitch * longest  # outer face of the last room wall
    wall_grey = (0.85, 0.85, 0.85)
    boxes: list[Box] = []
    poses: dict[str, tuple[float, float, float]] = {}

    # corridor ends and the two corridor-side walls, with a doorway per room
    boxes.append(
        Box(
            "end_west",
            -WALL_CM,
            -CORRIDOR_HALF_WIDTH_CM,
            0,
            CORRIDOR_HALF_WIDTH_CM,
            WALL_HEIGHT_CM,
            wall_grey,
        )
    )
    boxes.append(
        Box(
            "end_east",
            corridor_end,
            -CORRIDOR_HALF_WIDTH_CM,
            corridor_end + WALL_CM,
            CORRIDOR_HALF_WIDTH_CM,
            WALL_HEIGHT_CM,
            wall_grey,
        )
    )
    for side, side_name in ((1, "north"), (-1, "south")):
        gaps = []
        for slot in range(per_side[side]):
            room_x0 = FIRST_ROOM_X_CM + pitch * slot
            door_x0 = room_x0 + (ROOM_INTERIOR_CM - DOOR_WIDTH_CM) // 2
            gaps.append((door_x0, door_x0 + DOOR_WIDTH_CM))
        wall_y_in = CORRIDOR_HALF_WIDTH_CM
        wall_y_out = CORRIDOR_HALF_WIDTH_CM + WALL_CM
        for index, (seg_x0, seg_x1) in enumerate(
            _split(-WALL_CM, corridor_end + WALL_CM, gaps)
        ):
            y0, y1 = (wall_y_in, wall_y_out) if side == 1 else (-wall_y_out, -wall_y_in)
            boxes.append(
                Box(
                    f"corridor_wall_{side_name}_{index}",
                    seg_x0,
                    y0,
                    seg_x1,
                    y1,
                    WALL_HEIGHT_CM,
                    wall_grey,
                )
            )
        # room walls: dividing walls and the back wall
        interior_in = wall_y_out  # corridor-side interior face of the rooms
        interior_out = interior_in + ROOM_INTERIOR_CM
        for wall_index in range(per_side[side] + 1):
            wall_x0 = FIRST_ROOM_X_CM - WALL_CM + pitch * wall_index
            y0, y1 = (
                (interior_in, interior_out)
                if side == 1
                else (-interior_out, -interior_in)
            )
            boxes.append(
                Box(
                    f"room_wall_{side_name}_{wall_index}",
                    wall_x0,
                    y0,
                    wall_x0 + WALL_CM,
                    y1,
                    WALL_HEIGHT_CM,
                    wall_grey,
                )
            )
        if per_side[side]:
            back_x0 = FIRST_ROOM_X_CM - WALL_CM
            back_x1 = FIRST_ROOM_X_CM - WALL_CM + pitch * per_side[side] + WALL_CM
            y0, y1 = (
                (interior_out, interior_out + WALL_CM)
                if side == 1
                else (-interior_out - WALL_CM, -interior_out)
            )
            boxes.append(
                Box(
                    f"back_wall_{side_name}",
                    back_x0,
                    y0,
                    back_x1,
                    y1,
                    WALL_HEIGHT_CM,
                    wall_grey,
                )
            )

    # rooms: furniture and poses (interior_in is the corridor-side interior face of the rooms)
    interior_in = CORRIDOR_HALF_WIDTH_CM + WALL_CM
    for index in range(n_rooms):
        side = 1 if index % 2 == 0 else -1
        slot = index // 2
        room_id = f"r{index + 1:02d}"
        room_x0 = FIRST_ROOM_X_CM + pitch * slot

        def to_map(
            u: int, v: int, side: int = side, room_x0: int = room_x0
        ) -> tuple[int, int]:
            return room_x0 + u, side * (interior_in + v)

        bed_a = to_map(BED_U_CM[0], BED_V_CM[0])
        bed_b = to_map(BED_U_CM[1], BED_V_CM[1])
        boxes.append(
            Box(
                f"{room_id}_bed",
                min(bed_a[0], bed_b[0]),
                min(bed_a[1], bed_b[1]),
                max(bed_a[0], bed_b[0]),
                max(bed_a[1], bed_b[1]),
                BED_HEIGHT_CM,
                (0.45, 0.55, 0.8),
            )
        )
        table_a = to_map(TABLE_U_CM[0], TABLE_V_CM[0])
        table_b = to_map(TABLE_U_CM[1], TABLE_V_CM[1])
        boxes.append(
            Box(
                f"{room_id}_dispenser_table",
                min(table_a[0], table_b[0]),
                min(table_a[1], table_b[1]),
                max(table_a[0], table_b[0]),
                max(table_a[1], table_b[1]),
                TABLE_HEIGHT_CM,
                (0.75, 0.55, 0.3),
            )
        )
        door_x = room_x0 + ROOM_INTERIOR_CM // 2
        door_y = side * (CORRIDOR_HALF_WIDTH_CM - DOOR_STAND_OFF_CM)
        into_room_yaw = side * (math.pi / 2)
        bed_cx, bed_cy = to_map(
            (BED_U_CM[0] + BED_U_CM[1]) // 2, (BED_V_CM[0] + BED_V_CM[1]) // 2
        )
        table_cx, table_cy = to_map(
            (TABLE_U_CM[0] + TABLE_U_CM[1]) // 2, (TABLE_V_CM[0] + TABLE_V_CM[1]) // 2
        )
        bedside_x, bedside_y = to_map(BEDSIDE_U_CM, BEDSIDE_V_CM)
        poses[f"{room_id}.door"] = (_meters(door_x), _meters(door_y), into_room_yaw)
        poses[f"{room_id}.bedside"] = (_meters(bedside_x), _meters(bedside_y), 0.0)
        poses[f"{room_id}.bed"] = (_meters(bed_cx), _meters(bed_cy), 0.0)
        poses[f"{room_id}.dispenser"] = (_meters(table_cx), _meters(table_cy), 0.0)

    poses["dock"] = (_meters(DOCK_X_CM), 0.0, 0.0)
    # inside the corridor wall on the north side, between the dock and the first doorway
    poses["unreachable_pose"] = (
        _meters(200),
        _meters(CORRIDOR_HALF_WIDTH_CM + WALL_CM // 2),
        0.0,
    )

    x_min = min(box.x0 for box in boxes)
    y_min = min(box.y0 for box in boxes)
    x_max = max(box.x1 for box in boxes)
    y_max = max(box.y1 for box in boxes)
    return Layout(n_rooms, tuple(boxes), poses, x_min, y_min, x_max, y_max)


def layout_poses(n_rooms: int) -> dict[str, tuple[float, float, float]]:
    """The named poses ``(x, y, yaw)`` in metres: ``dock``, ``unreachable_pose``, ``rNN.<name>``."""
    return dict(build_layout(n_rooms).poses)


def _map_geometry(layout: Layout) -> tuple[int, int, int, int]:
    """(origin x, origin y, width, height) of the map in centimetres and cells."""
    origin_x = layout.x_min - MAP_MARGIN_CM
    origin_y = layout.y_min - MAP_MARGIN_CM
    width = (layout.x_max + MAP_MARGIN_CM - origin_x) // RESOLUTION_CM
    height = (layout.y_max + MAP_MARGIN_CM - origin_y) // RESOLUTION_CM
    return origin_x, origin_y, width, height


def render_map(layout: Layout) -> tuple[bytes, str]:
    """The PGM image (P5) and the ``map_server`` YAML text of the occupancy map."""
    origin_x, origin_y, width, height = _map_geometry(layout)
    for box in layout.boxes:
        for value in (box.x0, box.y0, box.x1, box.y1):
            if value % RESOLUTION_CM:
                raise ValueError(f"box {box.name} is not aligned to the map grid")
    # A cell is occupied when its centre lies inside a box. Every box edge is a multiple of the
    # resolution, so the cells of a box are exactly the columns and rows between its edges.
    cells = bytearray([PIXEL_FREE]) * (width * height)
    for box in layout.boxes:
        first_column = (box.x0 - origin_x) // RESOLUTION_CM
        end_column = (box.x1 - origin_x) // RESOLUTION_CM
        first_up = (box.y0 - origin_y) // RESOLUTION_CM  # rows counted from the bottom
        end_up = (box.y1 - origin_y) // RESOLUTION_CM
        for up in range(first_up, end_up):
            start = (height - 1 - up) * width
            cells[start + first_column : start + end_column] = bytes(
                [PIXEL_OCCUPIED] * (end_column - first_column)
            )
    rows = bytes(cells)
    pgm = f"P5\n{width} {height}\n255\n".encode("ascii") + rows
    text = (
        "# Generated by ros2/ralmon_sim/scripts/generate_ward_world.py: the rasterisation of the\n"
        f"# collision boxes of {WORLD_FILE} ({layout.n_rooms} rooms). Do not edit; regenerate.\n"
        f"image: {MAP_IMAGE_FILE}\n"
        "mode: trinary\n"
        f"resolution: {RESOLUTION_CM / 100:.2f}\n"
        f"origin: [{_meters(origin_x):.2f}, {_meters(origin_y):.2f}, 0.0]\n"
        "negate: 0\n"
        f"occupied_thresh: {OCCUPIED_THRESH}\n"
        f"free_thresh: {FREE_THRESH}\n"
    )
    return pgm, text


def _box_link(box: Box) -> str:
    cx = _meters(box.x0 + box.x1) / 2
    cy = _meters(box.y0 + box.y1) / 2
    sx = _meters(box.x1 - box.x0)
    sy = _meters(box.y1 - box.y0)
    sz = _meters(box.height)
    red, green, blue = box.color
    colour = f"{red:.2f} {green:.2f} {blue:.2f} 1"
    return (
        f'      <link name="{box.name}">\n'
        f"        <pose>{cx:.3f} {cy:.3f} {sz / 2:.3f} 0 0 0</pose>\n"
        f'        <collision name="collision">\n'
        f"          <geometry><box><size>{sx:.2f} {sy:.2f} {sz:.2f}</size></box></geometry>\n"
        f"        </collision>\n"
        f'        <visual name="visual">\n'
        f"          <geometry><box><size>{sx:.2f} {sy:.2f} {sz:.2f}</size></box></geometry>\n"
        f"          <material><ambient>{colour}</ambient><diffuse>{colour}</diffuse></material>\n"
        f"        </visual>\n"
        f"      </link>\n"
    )


def render_world(layout: Layout) -> str:
    """The SDF text of the world: physics, light, ground plane and one static model of boxes."""
    centre_x = _meters(layout.x_min + layout.x_max) / 2
    links = "".join(_box_link(box) for box in layout.boxes)
    return (
        '<?xml version="1.0" ?>\n'
        f"<!-- Generated by ros2/ralmon_sim/scripts/generate_ward_world.py for {layout.n_rooms} rooms. "
        "Do not edit; regenerate.\n"
        "     A technical test environment made of boxes (corridor and rooms), authored for this project;\n"
        "     it includes no third-party model, mesh or texture (see NOTICE). Dimensions are layout choices\n"
        "     of the test environment, not a model of a real ward and not clinical. -->\n"
        '<sdf version="1.6">\n'
        '  <world name="default">\n'
        "    <!-- Physics block of the worlds of pal_gazebo_worlds (the PAL robots are tuned for it) -->\n"
        '    <physics type="ode">\n'
        "      <gravity>0 0 -9.81</gravity>\n"
        "      <ode>\n"
        "        <solver><type>quick</type><iters>50</iters><sor>1.4</sor></solver>\n"
        "        <constraints>\n"
        "          <cfm>0.0</cfm>\n"
        "          <erp>0.2</erp>\n"
        "          <contact_max_correcting_vel>100.0</contact_max_correcting_vel>\n"
        "          <contact_surface_layer>0.0</contact_surface_layer>\n"
        "        </constraints>\n"
        "      </ode>\n"
        "      <real_time_update_rate>1000</real_time_update_rate>\n"
        "      <max_step_size>0.001</max_step_size>\n"
        "    </physics>\n"
        "    <!-- Ground truth for the tests: /gazebo/model_states (the tests compare the pose given by\n"
        "         AMCL with the pose of the model) -->\n"
        '    <plugin name="gazebo_ros_state" filename="libgazebo_ros_state.so">\n'
        "      <ros><namespace>/gazebo</namespace></ros>\n"
        "      <update_rate>10.0</update_rate>\n"
        "    </plugin>\n"
        '    <light name="sun" type="directional">\n'
        "      <cast_shadows>0</cast_shadows>\n"
        "      <pose>0 0 10 0 0 0</pose>\n"
        "      <diffuse>0.8 0.8 0.8 1</diffuse>\n"
        "      <specular>0.2 0.2 0.2 1</specular>\n"
        "      <direction>0.5 0.1 -0.9</direction>\n"
        "    </light>\n"
        '    <model name="ground_plane">\n'
        "      <static>1</static>\n"
        '      <link name="link">\n'
        '        <collision name="collision">\n'
        "          <geometry><plane><normal>0 0 1</normal><size>100 100</size></plane></geometry>\n"
        "          <surface><friction><ode><mu>100</mu><mu2>50</mu2></ode></friction></surface>\n"
        "        </collision>\n"
        '        <visual name="visual">\n'
        "          <cast_shadows>0</cast_shadows>\n"
        "          <geometry><plane><normal>0 0 1</normal><size>100 100</size></plane></geometry>\n"
        "          <material><ambient>0.55 0.55 0.55 1</ambient><diffuse>0.55 0.55 0.55 1</diffuse></material>\n"
        "        </visual>\n"
        "      </link>\n"
        "    </model>\n"
        '    <model name="ward">\n'
        "      <static>1</static>\n"
        "      <pose>0 0 0 0 0 0</pose>\n"
        f"{links}"
        "    </model>\n"
        "    <gui>\n"
        '      <camera name="user_camera">\n'
        f"        <pose>{centre_x:.2f} 0 28 0 1.5708 0</pose>\n"
        "      </camera>\n"
        "    </gui>\n"
        "  </world>\n"
        "</sdf>\n"
    )


def render_all(n_rooms: int) -> dict[str, bytes]:
    """File name to content for the three generated files."""
    layout = build_layout(n_rooms)
    pgm, map_yaml = render_map(layout)
    return {
        WORLD_FILE: render_world(layout).encode("utf-8"),
        MAP_IMAGE_FILE: pgm,
        MAP_YAML_FILE: map_yaml.encode("utf-8"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the ward world and its occupancy map."
    )
    parser.add_argument(
        "--rooms",
        type=int,
        required=True,
        help=f"number of rooms, {MIN_ROOMS} to {MAX_ROOMS}",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "worlds",
        help="output directory (default: ros2/ralmon_sim/worlds)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="compare with the files in --out, write nothing",
    )
    args = parser.parse_args(argv)
    try:
        files = render_all(args.rooms)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.check:
        differing = []
        for name, content in files.items():
            path = args.out / name
            if not path.is_file() or path.read_bytes() != content:
                differing.append(name)
        if differing:
            print(
                "differs from the generator output: " + ", ".join(differing),
                file=sys.stderr,
            )
            return 1
        return 0
    args.out.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (args.out / name).write_bytes(content)
        print(f"wrote {args.out / name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
