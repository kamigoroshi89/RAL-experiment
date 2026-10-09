"""Ward scenario: validated description of the simulated ward, and occupancy-grid helpers (WS07-T02).

Pure module: no ``rclpy``, no ``ralmon`` (WS05 is not a dependency of WS07-T02), no network. It
reads the scenario file ``config/ward_scenario.yaml`` (rooms with door, bedside, bed and dispenser
poses, one patient slot per room, the dock, a pose that cannot be reached, the compression factor and
the stagger of the clock policy of the WS07 README, the monitor values in ward-clock milliseconds)
and the occupancy map of the world (a ROS ``map_server`` YAML plus a PGM image).

Conventions
-----------
* Times are integer milliseconds (ADR-017); every integer is a plain ``int`` (``bool``, ``float``
  and ``str`` are refused) not larger than ``MAX_INT_VALUE``.
* Poses are in the map frame, in metres and radians (yaw in [-pi, pi]). The map frame is the Gazebo
  world frame: the world SDF and the map are generated from one layout (scripts/generate_ward_world.py).
* The loader is strict: every required key must be present (no defaults), an unknown key is an
  error, and every error is a ``ScenarioError`` that names the key (``rooms[1].door.x``). Nothing
  else escapes for any input (a file, a path or a value): not ``TypeError``, ``KeyError``,
  ``ValueError``, ``OverflowError``, ``OSError`` or ``yaml.YAMLError``.
* YAML is read with ``yaml.SafeLoader`` only (no object construction), after a size check and with
  anchors, aliases, merge keys and repeated keys refused, so an alias bomb cannot expand. A named
  pipe, a device or a directory is refused without blocking.

Occupancy grid (``map_server`` convention, checked against ``nav2_map_server/src/map_io.cpp``, branch
humble, trinary mode)
* a pixel is ``shade = pixel / maxval``; the occupancy is ``1 - shade`` (``negate`` 0) or ``shade``
  (``negate`` 1);
* a cell is *occupied* when the occupancy is strictly above ``occupied_thresh``, *free* when it is
  strictly below ``free_thresh``, and *unknown* otherwise (both comparisons are strict);
* image row 0 is the top of the map; the lower-left corner of the lowest row is ``origin``. The
  origin yaw must be 0 (Nav2 ignores it in most places) and only the ``trinary`` mode is supported;
* a pose lies on the cell that contains it (``floor`` of the offset over the resolution), so a
  point exactly on a cell boundary belongs to the cell above and to the right; a point on or
  beyond the far edge is outside the map. The heading and the robot footprint are ignored.

Reachability (``reachable_from``): a search over free cells with an 8-neighbourhood. A diagonal step
needs both neighbouring orthogonal cells free (no squeezing between two diagonally touching
obstacles, which a robot with a footprint cannot do); ``diagonal_squeeze=True`` allows it. Under the
default policy the reachable set equals the 4-connected one. The result is a statement about the
map only: the inflated costmap of Nav2 is stricter, so a goal that is reachable here can still fail
there (the ``ros`` tests check the shipped scenario at both levels).
"""

from __future__ import annotations

import math
import os
import re
import stat
from collections import deque
from collections.abc import Hashable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml

__all__ = [
    "MAX_COORD_M",
    "MAX_FILE_BYTES",
    "MAX_GRID_CELLS",
    "MAX_INT_VALUE",
    "MAX_PGM_BYTES",
    "MAX_ROOMS",
    "MAX_STAGGER_SLOTS",
    "MAX_TIME_ENTRIES",
    "MIN_ROOMS",
    "POSE_NAMES",
    "MonitorSettings",
    "OccupancyGrid",
    "Pose2D",
    "Room",
    "ScenarioError",
    "WardScenario",
    "cell_of",
    "load_occupancy_grid",
    "load_scenario",
    "occupancy_grid_from_pixels",
    "parse_pgm",
    "parse_scenario",
    "pose_is_free",
    "pose_is_occupied",
    "reachable_from",
    "stagger_offsets",
]

# source: analisi section 5.2 ("un robot, 4-8 stanze") and the task text of WS07-T02
MIN_ROOMS: int = 4
MAX_ROOMS: int = 8

# algorithmic: upper bound on a YAML file (1 MiB); the real files are a few kilobytes
MAX_FILE_BYTES: int = 1_048_576
# algorithmic: upper bound on a PGM image file (16 MiB); the shipped map is far smaller
MAX_PGM_BYTES: int = 16_777_216
# algorithmic: upper bound on the cells of a map (1000 x 1000, 50 m at 0.05 m per cell); keeps the
# search of reachable_from below a few seconds
MAX_GRID_CELLS: int = 1_000_000
# algorithmic: upper bound on any integer of the scenario (10**12 ms is about 31.7 years)
MAX_INT_VALUE: int = 10**12
# algorithmic: bound on |x| and |y| of a pose, in metres
MAX_COORD_M: float = 1.0e6
# algorithmic: bounds on the resolution of a map, in metres per cell
MIN_RESOLUTION_M: float = 1.0e-6
MAX_RESOLUTION_M: float = 1.0e3
# algorithmic: bound on the number of slots stagger_offsets will generate
MAX_STAGGER_SLOTS: int = 100_000
# algorithmic: bound on the length of each time-entry list (a registry has a few dozen names)
MAX_TIME_ENTRIES: int = 64
# algorithmic: characters of a value quoted in an error message
_SHOW_LIMIT: int = 60
# algorithmic: digits accepted in one number of a PGM header or raster
_PGM_MAX_DIGITS: int = 12

SCHEMA_VERSION: int = 1
# Frozen pose names of every room (WS10-T01 mirrors one room of this world; do not rename)
POSE_NAMES: tuple[str, ...] = ("door", "bedside", "bed", "dispenser")
_VARIANTS: tuple[str, ...] = ("likely", "possible")

_ROOM_ID = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,31}")  # a valid ROS name token
_PATIENT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")  # becomes a directory name
_WORLD_FILE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,120}\.(?:world|sdf)")
_YAML_FILE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,120}\.yaml")
_IMAGE_FILE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_REGISTRY_VERSION = re.compile(r"[0-9A-Za-z][0-9A-Za-z._+-]{0,31}")
_ENTRY_NAME = re.compile(r"[a-z][a-z0-9_]{0,63}")
_PGM_WHITESPACE = frozenset(b" \t\n\r\x0b\x0c")
_LINE_ENDS = frozenset(b"\n\r")
_HASH = ord("#")
_PGM_NUMBER = re.compile(rb"[0-9]{1," + str(_PGM_MAX_DIGITS).encode() + rb"}")
_MERGE_TAG = "tag:yaml.org,2002:merge"


class ScenarioError(ValueError):
    """Any failure to read or validate a scenario, a map or an image; the message names the key."""


# ----------------------------------------------------------------------------------------------
# Messages and scalar validation
# ----------------------------------------------------------------------------------------------


def _show(value: object) -> str:
    """A short, safe quotation of ``value`` for an error message."""
    try:
        text = repr(value)
    except Exception:  # noqa: BLE001 (repr of a foreign object can raise anything)
        text = "<" + type(value).__name__ + ">"
    if len(text) > _SHOW_LIMIT:
        text = text[:_SHOW_LIMIT] + "..."
    return text


def _join(where: str, key: str) -> str:
    return key if not where else where + "." + key


def _int(value: object, where: str, minimum: int, maximum: int = MAX_INT_VALUE) -> int:
    if type(value) is not int:
        raise ScenarioError(f"{where}: must be an integer, got {_show(value)}")
    if value < minimum or value > maximum:
        raise ScenarioError(
            f"{where}: must be between {minimum} and {maximum}, got {_show(value)}"
        )
    return value


def _float(value: object, where: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ScenarioError(f"{where}: must be a number, got {_show(value)}")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ScenarioError(f"{where}: the number is too large") from exc
    if not math.isfinite(number) or number < low or number > high:
        raise ScenarioError(
            f"{where}: must be a finite number between {low} and {high}, got {_show(value)}"
        )
    return number


def _bool(value: object, where: str) -> bool:
    if type(value) is not bool:
        raise ScenarioError(f"{where}: must be true or false, got {_show(value)}")
    return value


def _text(value: object, where: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str):
        raise ScenarioError(f"{where}: must be text, got {_show(value)}")
    if pattern.fullmatch(value) is None:
        raise ScenarioError(
            f"{where}: {_show(value)} does not match the pattern {pattern.pattern}"
        )
    return value


def _mapping(
    value: object,
    where: str,
    required: Sequence[str],
    optional: Sequence[str] = (),
) -> dict[str, Any]:
    """``value`` as a dict with exactly the required keys and some of the optional ones."""
    if not isinstance(value, dict):
        raise ScenarioError(f"{where}: must be a mapping, got {_show(value)}")
    for key in value:
        if not isinstance(key, str):
            raise ScenarioError(f"{where}: keys must be text, got {_show(key)}")
        if key not in required and key not in optional:
            raise ScenarioError(f"{where}: unknown key {_show(key)}")
    for key in required:
        if key not in value:
            raise ScenarioError(f"{_join(where, key)}: required key is missing")
    return value


# ----------------------------------------------------------------------------------------------
# Data classes
# ----------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Pose2D:
    """A pose in the map frame: ``x`` and ``y`` in metres, ``yaw`` in radians within [-pi, pi]."""

    x: float
    y: float
    yaw: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "x", _float(self.x, "Pose2D.x", -MAX_COORD_M, MAX_COORD_M)
        )
        object.__setattr__(
            self, "y", _float(self.y, "Pose2D.y", -MAX_COORD_M, MAX_COORD_M)
        )
        object.__setattr__(
            self, "yaw", _float(self.yaw, "Pose2D.yaw", -math.pi, math.pi)
        )


@dataclass(frozen=True, slots=True)
class Room:
    """One patient room: its slot, its stagger offset and four named poses.

    ``door`` is the standing pose in the corridor in front of the doorway, facing it, and
    ``bedside`` the standing pose of the robot next to the bed (both lie on free cells of the
    map); ``bed`` and ``dispenser`` are furniture
    positions (on occupied cells of the map, not goals). ``offset_ms`` is the resolved offset of
    the room's care plan in ward-clock milliseconds.
    """

    room_id: str
    patient_id: str
    day_index: int
    offset_ms: int
    door: Pose2D
    bedside: Pose2D
    bed: Pose2D
    dispenser: Pose2D


@dataclass(frozen=True, slots=True)
class MonitorSettings:
    """The ``MonitorConfig`` values of the scenario, in ward-clock milliseconds.

    The fields are those of ``MonitorConfig`` in ``02-interfaces.md#monitor``; this module does not
    import ``ralmon``, so the consumer builds the config from these values.
    """

    step_ms: int
    reorder_delay_ms: int
    predictive: bool
    alpha: float | None
    variant: str
    registry_version: str


@dataclass(frozen=True, slots=True)
class WardScenario:
    """The validated ward scenario (see ``config/ward_scenario.yaml``)."""

    rooms: tuple[Room, ...]
    dock: Pose2D
    unreachable_pose: Pose2D
    world_file: str
    map_file: str
    compression_factor: int
    replay_start_ms: int
    spacing_ms: int
    monitor: MonitorSettings
    care_plan_time_entries: tuple[str, ...]
    physical_time_entries: tuple[str, ...]
    startup_timeout_ms: int
    nav_goal_timeout_ms: int


# ----------------------------------------------------------------------------------------------
# Stagger
# ----------------------------------------------------------------------------------------------


def stagger_offsets(n_rooms: int, spacing_ms: int) -> list[int]:
    """Offsets ``[0, s, 2 s, ...]`` in ward-clock milliseconds, one per room (``s`` is the spacing)."""
    if type(n_rooms) is not int or not 1 <= n_rooms <= MAX_STAGGER_SLOTS:
        raise ScenarioError(
            f"n_rooms: must be an integer between 1 and {MAX_STAGGER_SLOTS}, got {_show(n_rooms)}"
        )
    spacing = _int(spacing_ms, "spacing_ms", 1)
    if (n_rooms - 1) * spacing > MAX_INT_VALUE:
        raise ScenarioError(
            f"spacing_ms: {n_rooms} offsets of {spacing} ms exceed {MAX_INT_VALUE} ms"
        )
    return [index * spacing for index in range(n_rooms)]


# ----------------------------------------------------------------------------------------------
# Reading YAML
# ----------------------------------------------------------------------------------------------


class _StrictLoader(yaml.SafeLoader):
    """Safe loader that refuses anchors, aliases, merge keys and repeated keys."""

    def compose_node(self, parent: yaml.Node | None, index: object) -> yaml.Node | None:
        event = self.peek_event()  # type: ignore[no-untyped-call]
        if getattr(event, "anchor", None) is not None:
            raise yaml.composer.ComposerError(
                None, None, "anchors and aliases are not allowed", event.start_mark
            )
        return super().compose_node(parent, index)  # type: ignore[arg-type]

    def construct_mapping(
        self, node: yaml.MappingNode, deep: bool = False
    ) -> dict[Hashable, Any]:
        seen: set[Hashable] = set()
        for key_node, _value_node in node.value:
            if key_node.tag == _MERGE_TAG:
                raise yaml.constructor.ConstructorError(
                    None, None, "merge keys are not allowed", key_node.start_mark
                )
            key = self.construct_object(key_node, deep=deep)
            if isinstance(key, Hashable):
                if key in seen:
                    raise yaml.constructor.ConstructorError(
                        None,
                        None,
                        f"duplicate key {_show(key)} in a mapping",
                        key_node.start_mark,
                    )
                seen.add(key)
        return super().construct_mapping(node, deep=deep)


def _coerce_path(path: object, what: str) -> Path:
    if isinstance(path, bool) or not isinstance(path, (str, os.PathLike)):
        raise ScenarioError(
            f"{what}: the path must be a str or an os.PathLike, got {_show(path)}"
        )
    try:
        raw = os.fspath(path)
    except Exception as exc:
        raise ScenarioError(f"{what}: the path cannot be converted to text") from exc
    if not isinstance(raw, str):
        raise ScenarioError(f"{what}: the path must be text, not {type(raw).__name__}")
    return Path(raw)


def _read_limited(path: Path, limit: int, what: str) -> bytes:
    """The bytes of the regular file at ``path``; refuse anything larger than ``limit``.

    The file is opened without blocking and its kind is checked on the open descriptor, so a named
    pipe, a device or a directory is refused with an error (a plain ``open`` of a named pipe with
    no writer blocks for ever) and there is no race between a check of the path and the open.
    """
    shown = _show(str(path))
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
    except (OSError, ValueError) as exc:
        reason = exc.strerror if isinstance(exc, OSError) and exc.strerror else str(exc)
        raise ScenarioError(f"{what}: cannot read {shown}: {_show(reason)}") from exc
    try:
        is_regular = stat.S_ISREG(os.fstat(descriptor).st_mode)
    except OSError as exc:
        os.close(descriptor)
        raise ScenarioError(f"{what}: cannot read {shown}") from exc
    if not is_regular:
        os.close(descriptor)
        raise ScenarioError(f"{what}: {shown} is not a regular file")
    try:
        # open() takes over the descriptor and closes it
        with open(descriptor, "rb") as handle:
            data = handle.read(limit + 1)
    except (OSError, ValueError) as exc:
        raise ScenarioError(f"{what}: cannot read {shown}") from exc
    if len(data) > limit:
        raise ScenarioError(f"{what}: {shown} is larger than {limit} bytes")
    return data


def _parse_yaml(data: bytes, what: str) -> object:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ScenarioError(f"{what}: the file is not valid UTF-8") from exc
    try:
        return yaml.load(text, Loader=_StrictLoader)
    except yaml.YAMLError as exc:
        first_line = (str(exc).strip().splitlines() or [""])[0]
        raise ScenarioError(f"{what}: invalid YAML ({_show(first_line)})") from exc
    except RecursionError as exc:
        raise ScenarioError(f"{what}: the YAML is nested too deeply") from exc
    except Exception as exc:  # an impossible date, an oversized number, ...
        raise ScenarioError(
            f"{what}: invalid YAML content ({_show(str(exc))})"
        ) from exc


# ----------------------------------------------------------------------------------------------
# Scenario
# ----------------------------------------------------------------------------------------------

_TOP_KEYS = (
    "schema_version",
    "world_file",
    "map_file",
    "compression_factor",
    "replay_start_ms",
    "stagger",
    "monitor",
    "time_entries",
    "startup_timeout_ms",
    "nav_goal_timeout_ms",
    "dock",
    "unreachable_pose",
    "rooms",
)
_MONITOR_KEYS = (
    "step_ms",
    "reorder_delay_ms",
    "predictive",
    "alpha",
    "variant",
    "registry_version",
)
_ROOM_KEYS = ("room_id", "patient_id", "day_index", *POSE_NAMES)


def _pose(value: object, where: str) -> Pose2D:
    fields = _mapping(value, where, ("x", "y", "yaw"))
    return Pose2D(
        _float(fields["x"], _join(where, "x"), -MAX_COORD_M, MAX_COORD_M),
        _float(fields["y"], _join(where, "y"), -MAX_COORD_M, MAX_COORD_M),
        _float(fields["yaw"], _join(where, "yaw"), -math.pi, math.pi),
    )


def _name_list(value: object, where: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ScenarioError(
            f"{where}: must be a list of registry names, got {_show(value)}"
        )
    if len(value) > MAX_TIME_ENTRIES:
        raise ScenarioError(
            f"{where}: at most {MAX_TIME_ENTRIES} names, got {len(value)}"
        )
    names: list[str] = []
    for index, item in enumerate(value):
        name = _text(item, f"{where}[{index}]", _ENTRY_NAME)
        if name in names:
            raise ScenarioError(f"{where}[{index}]: {_show(name)} is listed twice")
        names.append(name)
    return tuple(names)


def _monitor(value: object) -> MonitorSettings:
    fields = _mapping(value, "monitor", _MONITOR_KEYS)
    predictive = _bool(fields["predictive"], "monitor.predictive")
    alpha_value = fields["alpha"]
    alpha: float | None
    if alpha_value is None:
        alpha = None
    elif not isinstance(alpha_value, float):
        raise ScenarioError(
            f"monitor.alpha: must be null or a float, got {_show(alpha_value)}"
        )
    else:
        alpha = _float(alpha_value, "monitor.alpha", 0.0, 1.0)
        if alpha <= 0.0 or alpha >= 1.0:
            raise ScenarioError(
                f"monitor.alpha: must lie strictly between 0 and 1, got {_show(alpha_value)}"
            )
    if predictive and alpha is None:
        raise ScenarioError("monitor.alpha: a predictive monitor needs an alpha")
    variant = fields["variant"]
    if not isinstance(variant, str) or variant not in _VARIANTS:
        raise ScenarioError(
            f"monitor.variant: must be one of {list(_VARIANTS)}, got {_show(variant)}"
        )
    return MonitorSettings(
        step_ms=_int(fields["step_ms"], "monitor.step_ms", 1),
        reorder_delay_ms=_int(
            fields["reorder_delay_ms"], "monitor.reorder_delay_ms", 0
        ),
        predictive=predictive,
        alpha=alpha,
        variant=variant,
        registry_version=_text(
            fields["registry_version"], "monitor.registry_version", _REGISTRY_VERSION
        ),
    )


def _room(value: object, index: int) -> tuple[Room, bool]:
    """A room (with offset 0 for now) and whether the file gave it an explicit offset."""
    where = f"rooms[{index}]"
    fields = _mapping(value, where, _ROOM_KEYS, ("offset_ms",))
    explicit = "offset_ms" in fields
    offset = _int(fields["offset_ms"], _join(where, "offset_ms"), 0) if explicit else 0
    room = Room(
        room_id=_text(fields["room_id"], _join(where, "room_id"), _ROOM_ID),
        patient_id=_text(fields["patient_id"], _join(where, "patient_id"), _PATIENT_ID),
        day_index=_int(fields["day_index"], _join(where, "day_index"), 0),
        offset_ms=offset,
        door=_pose(fields["door"], _join(where, "door")),
        bedside=_pose(fields["bedside"], _join(where, "bedside")),
        bed=_pose(fields["bed"], _join(where, "bed")),
        dispenser=_pose(fields["dispenser"], _join(where, "dispenser")),
    )
    return room, explicit


def _rooms(value: object, spacing_ms: int) -> tuple[Room, ...]:
    if not isinstance(value, list):
        raise ScenarioError(f"rooms: must be a list of rooms, got {_show(value)}")
    if not MIN_ROOMS <= len(value) <= MAX_ROOMS:
        raise ScenarioError(
            f"rooms: the scenario needs {MIN_ROOMS} to {MAX_ROOMS} rooms, got {len(value)}"
        )
    parsed = [_room(item, index) for index, item in enumerate(value)]
    seen_ids: set[str] = set()
    seen_slots: set[tuple[str, int]] = set()
    for index, (room, _) in enumerate(parsed):
        if room.room_id in seen_ids:
            raise ScenarioError(
                f"rooms[{index}].room_id: duplicate room_id {_show(room.room_id)}"
            )
        seen_ids.add(room.room_id)
        slot = (room.patient_id, room.day_index)
        if slot in seen_slots:
            raise ScenarioError(
                f"rooms[{index}]: duplicate slot (patient_id, day_index) = {_show(slot)}"
            )
        seen_slots.add(slot)
    generated = stagger_offsets(len(parsed), spacing_ms)
    offsets = [
        room.offset_ms if explicit else generated[index]
        for index, (room, explicit) in enumerate(parsed)
    ]
    first_owner: dict[int, int] = {}
    for index, offset in enumerate(offsets):
        if offset in first_owner:
            earlier = first_owner[offset]
            blamed = index if parsed[index][1] else earlier
            raise ScenarioError(
                f"rooms[{blamed}].offset_ms: the offset {offset} ms is also used by "
                f"rooms[{earlier if blamed == index else index}]; offsets must be distinct"
            )
        first_owner[offset] = index
    return tuple(
        Room(
            room_id=room.room_id,
            patient_id=room.patient_id,
            day_index=room.day_index,
            offset_ms=offsets[index],
            door=room.door,
            bedside=room.bedside,
            bed=room.bed,
            dispenser=room.dispenser,
        )
        for index, (room, _) in enumerate(parsed)
    )


def parse_scenario(data: object) -> WardScenario:
    """Validate plain data (the content of ``ward_scenario.yaml``) and return the scenario."""
    top = _mapping(data, "scenario", _TOP_KEYS)
    _int(top["schema_version"], "schema_version", SCHEMA_VERSION, SCHEMA_VERSION)
    world_file = _text(top["world_file"], "world_file", _WORLD_FILE)
    map_file = _text(top["map_file"], "map_file", _YAML_FILE)
    compression_factor = _int(top["compression_factor"], "compression_factor", 1)
    replay_start_ms = _int(top["replay_start_ms"], "replay_start_ms", 0)
    stagger = _mapping(top["stagger"], "stagger", ("spacing_ms",))
    spacing_ms = _int(stagger["spacing_ms"], "stagger.spacing_ms", 1)
    monitor = _monitor(top["monitor"])
    entries = _mapping(
        top["time_entries"],
        "time_entries",
        ("care_plan_time_entries", "physical_time_entries"),
    )
    care = _name_list(
        entries["care_plan_time_entries"], "time_entries.care_plan_time_entries"
    )
    physical = _name_list(
        entries["physical_time_entries"], "time_entries.physical_time_entries"
    )
    for name in care:
        if name in physical:
            raise ScenarioError(
                f"time_entries: {_show(name)} is in both care_plan_time_entries and "
                "physical_time_entries; the lists must be disjoint"
            )
    startup_timeout_ms = _int(top["startup_timeout_ms"], "startup_timeout_ms", 1)
    nav_goal_timeout_ms = _int(top["nav_goal_timeout_ms"], "nav_goal_timeout_ms", 1)
    dock = _pose(top["dock"], "dock")
    unreachable = _pose(top["unreachable_pose"], "unreachable_pose")
    rooms = _rooms(top["rooms"], spacing_ms)
    return WardScenario(
        rooms=rooms,
        dock=dock,
        unreachable_pose=unreachable,
        world_file=world_file,
        map_file=map_file,
        compression_factor=compression_factor,
        replay_start_ms=replay_start_ms,
        spacing_ms=spacing_ms,
        monitor=monitor,
        care_plan_time_entries=care,
        physical_time_entries=physical,
        startup_timeout_ms=startup_timeout_ms,
        nav_goal_timeout_ms=nav_goal_timeout_ms,
    )


def load_scenario(path: str | os.PathLike[str]) -> WardScenario:
    """Read and validate a scenario file; only ``ScenarioError`` can be raised."""
    file_path = _coerce_path(path, "scenario")
    data = _read_limited(file_path, MAX_FILE_BYTES, "scenario")
    return parse_scenario(_parse_yaml(data, "scenario"))


# ----------------------------------------------------------------------------------------------
# PGM and occupancy grid
# ----------------------------------------------------------------------------------------------


def _pgm_token(data: bytes, position: int) -> tuple[bytes, int]:
    """The next header token at or after ``position`` and the index of the byte that ended it.

    Whitespace and comments (``#`` to the end of the line) before the token are skipped.
    """
    size = len(data)
    while position < size:
        byte = data[position]
        if byte == _HASH:
            while position < size and data[position] not in _LINE_ENDS:
                position += 1
        elif byte in _PGM_WHITESPACE:
            position += 1
        else:
            break
    start = position
    while (
        position < size
        and data[position] not in _PGM_WHITESPACE
        and data[position] != _HASH
    ):
        position += 1
    return data[start:position], position


def _pgm_int(token: bytes, what: str) -> int:
    if _PGM_NUMBER.fullmatch(token) is None:
        raise ScenarioError(f"pgm: {what} must be a decimal number, got {_show(token)}")
    return int(token)


def parse_pgm(data: bytes) -> tuple[np.ndarray, int]:
    """Parse a binary (P5) or ASCII (P2) PGM image; return ``(pixels, maxval)``.

    ``pixels`` is a read-only ``uint16`` array of shape ``(height, width)`` whose row 0 is the top
    of the image. Comments (``#`` to the end of the line) are allowed in the header (and in the
    raster of P2). The raster must have exactly ``width * height`` samples, none above ``maxval``,
    and the image at most ``MAX_GRID_CELLS`` cells.
    """
    if type(data) is not bytes:
        raise ScenarioError(f"pgm: the image must be bytes, got {_show(data)}")
    magic, position = _pgm_token(data, 0)
    if magic not in (b"P5", b"P2"):
        raise ScenarioError(f"pgm: unsupported magic number {_show(magic)} (P5 or P2)")
    width_token, position = _pgm_token(data, position)
    height_token, position = _pgm_token(data, position)
    maxval_token, position = _pgm_token(data, position)
    width = _pgm_int(width_token, "width")
    height = _pgm_int(height_token, "height")
    maxval = _pgm_int(maxval_token, "maxval")
    if width < 1 or height < 1:
        raise ScenarioError(f"pgm: the size must be positive, got {width} x {height}")
    if width * height > MAX_GRID_CELLS:
        raise ScenarioError(
            f"pgm: {width} x {height} is more than the limit of {MAX_GRID_CELLS} cells"
        )
    if not 1 <= maxval <= 65535:
        raise ScenarioError(f"pgm: maxval must be between 1 and 65535, got {maxval}")
    cells = width * height
    samples: np.ndarray
    if magic == b"P5":
        if position >= len(data) or data[position] not in _PGM_WHITESPACE:
            raise ScenarioError("pgm: the header must end with one whitespace byte")
        start = position + 1
        bytes_per_sample = 1 if maxval < 256 else 2
        expected = cells * bytes_per_sample
        if len(data) - start != expected:
            raise ScenarioError(
                f"pgm: the raster has {len(data) - start} bytes, expected {expected}"
            )
        dtype = np.dtype(np.uint8) if bytes_per_sample == 1 else np.dtype(">u2")
        samples = np.frombuffer(data, dtype=dtype, count=cells, offset=start)
    else:
        cleaned = re.sub(rb"#[^\r\n]*", b" ", data[position:])
        values: list[int] = []
        for match in re.finditer(rb"[^\s]+", cleaned):
            if len(values) >= cells:
                raise ScenarioError(f"pgm: more than the {cells} samples of the header")
            values.append(_pgm_int(match.group(0), "sample"))
        if len(values) != cells:
            raise ScenarioError(f"pgm: {len(values)} samples, expected {cells}")
        samples = np.array(values, dtype=np.int64)
    if int(samples.max()) > maxval:
        raise ScenarioError(f"pgm: a sample is above maxval {maxval}")
    pixels = samples.astype(np.uint16).reshape(height, width)
    pixels.setflags(write=False)
    return pixels, maxval


@dataclass(frozen=True, slots=True, eq=False)
class OccupancyGrid:
    """A trinary occupancy grid: ``free`` and ``occupied`` masks, row 0 at the top of the map.

    A cell that is neither free nor occupied is unknown. ``origin_x`` and ``origin_y`` are the map
    coordinates of the lower-left corner of the lowest row; ``resolution`` is in metres per cell.
    """

    resolution: float
    origin_x: float
    origin_y: float
    free: np.ndarray
    occupied: np.ndarray


def occupancy_grid_from_pixels(
    pixels: np.ndarray,
    maxval: int,
    *,
    resolution: float,
    origin: tuple[float, float],
    negate: int,
    free_thresh: float,
    occupied_thresh: float,
) -> OccupancyGrid:
    """Apply the ``map_server`` trinary convention (module docstring) to an image."""
    if not isinstance(pixels, np.ndarray) or pixels.ndim != 2 or pixels.size == 0:
        raise ScenarioError("map: the pixels must be a non-empty 2-D array")
    if pixels.size > MAX_GRID_CELLS:
        raise ScenarioError(f"map: more than the limit of {MAX_GRID_CELLS} cells")
    if pixels.dtype.kind not in "iu":
        raise ScenarioError("map: the pixels must be integers")
    maxval = _int(maxval, "maxval", 1, 65535)
    if int(pixels.min()) < 0 or int(pixels.max()) > maxval:
        raise ScenarioError(f"map: a pixel is outside 0..{maxval}")
    resolution = _float(resolution, "resolution", MIN_RESOLUTION_M, MAX_RESOLUTION_M)
    if not isinstance(origin, (tuple, list)) or len(origin) != 2:
        raise ScenarioError("origin: must hold x and y")
    origin_x = _float(origin[0], "origin.x", -MAX_COORD_M, MAX_COORD_M)
    origin_y = _float(origin[1], "origin.y", -MAX_COORD_M, MAX_COORD_M)
    if isinstance(negate, bool):
        negate = int(negate)
    if type(negate) is not int or negate not in (0, 1):
        raise ScenarioError(f"negate: must be 0 or 1, got {_show(negate)}")
    free_level = _float(free_thresh, "free_thresh", 0.0, 1.0)
    occupied_level = _float(occupied_thresh, "occupied_thresh", 0.0, 1.0)
    if not free_level < occupied_level:
        raise ScenarioError(
            f"free_thresh {free_level} must be below occupied_thresh {occupied_level}"
        )
    shade = pixels.astype(np.float64) / float(maxval)
    occupancy = shade if negate == 1 else 1.0 - shade
    free = occupancy < free_level
    occupied = occupancy > occupied_level
    free.setflags(write=False)
    occupied.setflags(write=False)
    return OccupancyGrid(
        resolution=resolution,
        origin_x=origin_x,
        origin_y=origin_y,
        free=free,
        occupied=occupied,
    )


_MAP_KEYS = (
    "image",
    "resolution",
    "origin",
    "negate",
    "occupied_thresh",
    "free_thresh",
)


def load_occupancy_grid(path: str | os.PathLike[str]) -> OccupancyGrid:
    """Read a ``map_server`` YAML (trinary mode) and the PGM image next to it."""
    file_path = _coerce_path(path, "map")
    document = _parse_yaml(_read_limited(file_path, MAX_FILE_BYTES, "map"), "map")
    fields = _mapping(document, "map", _MAP_KEYS, ("mode",))
    if "mode" in fields and fields["mode"] != "trinary":
        raise ScenarioError(
            f"mode: only 'trinary' is supported, got {_show(fields['mode'])}"
        )
    image = _text(fields["image"], "image", _IMAGE_FILE)
    resolution = _float(
        fields["resolution"], "resolution", MIN_RESOLUTION_M, MAX_RESOLUTION_M
    )
    origin = fields["origin"]
    if not isinstance(origin, list) or len(origin) != 3:
        raise ScenarioError(
            f"origin: must be a list of x, y and yaw, got {_show(origin)}"
        )
    origin_x = _float(origin[0], "origin.x", -MAX_COORD_M, MAX_COORD_M)
    origin_y = _float(origin[1], "origin.y", -MAX_COORD_M, MAX_COORD_M)
    origin_yaw = _float(origin[2], "origin.yaw", -math.pi, math.pi)
    if origin_yaw != 0.0:
        raise ScenarioError(f"origin: the yaw must be 0, got {_show(origin[2])}")
    negate = fields["negate"]
    if type(negate) not in (int, bool) or negate not in (0, 1):
        raise ScenarioError(f"negate: must be 0 or 1, got {_show(negate)}")
    free_thresh = _float(fields["free_thresh"], "free_thresh", 0.0, 1.0)
    occupied_thresh = _float(fields["occupied_thresh"], "occupied_thresh", 0.0, 1.0)
    if not free_thresh < occupied_thresh:
        raise ScenarioError(
            f"free_thresh {free_thresh} must be below occupied_thresh {occupied_thresh}"
        )
    raw = _read_limited(file_path.parent / image, MAX_PGM_BYTES, "map image")
    pixels, maxval = parse_pgm(raw)
    return occupancy_grid_from_pixels(
        pixels,
        maxval,
        resolution=resolution,
        origin=(origin_x, origin_y),
        negate=int(negate),
        free_thresh=free_thresh,
        occupied_thresh=occupied_thresh,
    )


# ----------------------------------------------------------------------------------------------
# Poses on the grid
# ----------------------------------------------------------------------------------------------


def _check_grid(grid: object) -> OccupancyGrid:
    if not isinstance(grid, OccupancyGrid):
        raise ScenarioError(f"grid: must be an OccupancyGrid, got {_show(grid)}")
    return grid


def _check_pose(pose: object, what: str) -> Pose2D:
    if not isinstance(pose, Pose2D):
        raise ScenarioError(f"{what}: must be a Pose2D, got {_show(pose)}")
    return pose


def cell_of(grid: OccupancyGrid, pose: Pose2D) -> tuple[int, int] | None:
    """The ``(row, column)`` of the cell that contains ``pose``, or None outside the map."""
    grid = _check_grid(grid)
    pose = _check_pose(pose, "pose")
    height, width = grid.free.shape
    column = math.floor((pose.x - grid.origin_x) / grid.resolution)
    row_from_bottom = math.floor((pose.y - grid.origin_y) / grid.resolution)
    if not (0 <= column < width and 0 <= row_from_bottom < height):
        return None
    return (height - 1 - row_from_bottom, column)


def pose_is_free(grid: OccupancyGrid, pose: Pose2D) -> bool:
    """True when ``pose`` lies on a free cell (a pose outside the map is not free)."""
    cell = cell_of(grid, pose)
    return cell is not None and bool(grid.free[cell])


def pose_is_occupied(grid: OccupancyGrid, pose: Pose2D) -> bool:
    """True when ``pose`` lies on an occupied cell (a pose outside the map is not occupied)."""
    cell = cell_of(grid, pose)
    return cell is not None and bool(grid.occupied[cell])


_ORTHOGONAL = ((-1, 0), (1, 0), (0, -1), (0, 1))
_DIAGONAL = ((-1, -1), (-1, 1), (1, -1), (1, 1))


def reachable_from(
    grid: OccupancyGrid,
    start: Pose2D,
    goals: Sequence[Pose2D],
    *,
    diagonal_squeeze: bool = False,
) -> list[bool]:
    """For each goal, whether its cell is reachable from the cell of ``start`` over free cells.

    Returns all False when the start is outside the map or not on a free cell. See the module
    docstring for the neighbourhood and the diagonal policy.
    """
    grid = _check_grid(grid)
    start = _check_pose(start, "start")
    if not isinstance(goals, (list, tuple)):
        raise ScenarioError(f"goals: must be a list of Pose2D, got {_show(goals)}")
    for index, goal in enumerate(goals):
        _check_pose(goal, f"goals[{index}]")
    start_cell = cell_of(grid, start)
    if start_cell is None or not grid.free[start_cell]:
        return [False] * len(goals)
    height, width = grid.free.shape
    free = grid.free.ravel().tolist()
    seen = bytearray(height * width)
    first = start_cell[0] * width + start_cell[1]
    seen[first] = 1
    queue = deque([first])
    while queue:
        index = queue.popleft()
        row, column = divmod(index, width)
        for d_row, d_column in _ORTHOGONAL:
            n_row, n_column = row + d_row, column + d_column
            if 0 <= n_row < height and 0 <= n_column < width:
                neighbour = n_row * width + n_column
                if free[neighbour] and not seen[neighbour]:
                    seen[neighbour] = 1
                    queue.append(neighbour)
        for d_row, d_column in _DIAGONAL:
            n_row, n_column = row + d_row, column + d_column
            if not (0 <= n_row < height and 0 <= n_column < width):
                continue
            neighbour = n_row * width + n_column
            if not free[neighbour] or seen[neighbour]:
                continue
            if not diagonal_squeeze and not (
                free[n_row * width + column] and free[row * width + n_column]
            ):
                continue
            seen[neighbour] = 1
            queue.append(neighbour)
    result = []
    for goal in goals:
        cell = cell_of(grid, goal)
        result.append(cell is not None and bool(seen[cell[0] * width + cell[1]]))
    return result
