"""WS07-T01: the package availability record, the workspace skeleton and the environment check.

Plain Python and no network: every test reads the YAML record and the package files as text and
does not depend on the machine (no ``rclpy``, no ROS, no ``ralmon``). Tests that need a ROS 2
installation carry the marker ``ros`` and are skipped without ``rclpy``.
"""

from __future__ import annotations

import ast
import datetime
import importlib
import os
import re
import subprocess
import sys
import textwrap
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

PACKAGE_DIR = Path(__file__).resolve().parent.parent
WORKSPACE = PACKAGE_DIR.parent
REPO_ROOT = WORKSPACE.parent
RECORD = PACKAGE_DIR / "config" / "package_availability.yaml"
DOC = PACKAGE_DIR / "doc" / "availability.md"
SCRIPT = PACKAGE_DIR / "scripts" / "check_sim_env.sh"
SETUP_PY = PACKAGE_DIR / "setup.py"
PACKAGE_XML = PACKAGE_DIR / "package.xml"
README = REPO_ROOT / "docs" / "plan" / "workstreams" / "WS07-ros2-sim" / "README.md"
WS00_T05 = (
    REPO_ROOT
    / "docs"
    / "plan"
    / "workstreams"
    / "WS00-admin"
    / "outputs"
    / "WS00-T05.md"
)
DECISIONS = REPO_ROOT / "docs" / "plan" / "03-decisions.md"

REQUIRED_COMPONENTS = [
    "ros2_distro",
    "gazebo",
    "ros_gz_bridge",
    "nav2",
    "robot_sim_pal",
    "hospital_world",
    "human_sim",
    "ros2_tracing",
    "tc_netem",
    "onboard_computer",
    "isaac_sim",
]
STATUSES = {"available", "partial", "unavailable", "unverified", "not_evaluated"}
VERIFIED_STATUSES = {"available", "partial", "unavailable"}
GATE_COMPONENTS = ["ros2_distro", "gazebo", "ros_gz_bridge", "nav2"]
HEADINGS = [
    "Host",
    "Verdict",
    "Component table",
    "Reproduction",
    "Hospital world decision",
    "Robot variant decision",
    "Onboard computer",
    "Open items for a human",
    "Proposed ADR",
]
EXPECTED_SCRIPTS = {
    "sim_device_node",
    "sim_gateway_node",
    "sim_backend_node",
    "robot_task_node",
    "fault_injector_node",
    "deadline_prediction",
    "deadline_logger_node",
    "measure_run",
}
RUNTIME_DEPENDENCIES = [
    "rclpy",
    "lifecycle_msgs",
    "std_msgs",
    "std_srvs",
    "geometry_msgs",
    "nav2_msgs",
    "launch_ros",
    "ralmon_sim_msgs",
    "ralmon_ros",
]


def _record() -> dict[str, Any]:
    data = yaml.safe_load(RECORD.read_text(encoding="utf-8"))
    assert isinstance(data, dict), "the record must be a YAML mapping"
    return data


def _components() -> dict[str, dict[str, Any]]:
    components = _record().get("components")
    assert isinstance(components, dict), "the record needs a `components` mapping"
    return components


def _iso_date(value: object) -> datetime.date:
    """Dates are quoted strings in the record; PyYAML turns an unquoted one into a date."""
    if isinstance(value, datetime.date):
        return value
    assert isinstance(value, str), f"not an ISO date: {value!r}"
    return datetime.date.fromisoformat(value)


def _nonempty(value: object) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict)):
        return len(value) > 0
    return value is not None


def _readme_module_map() -> dict[str, tuple[str, str]]:
    """Console scripts `name = module:function` of the module map table of the WS07 README."""
    text = README.read_text(encoding="utf-8")
    section = text.split("### Package layout and module map", 1)[1]
    section = section.split("### Simulation-internal interfaces", 1)[0]
    entry = re.compile(r"`([a-z_]+) = ([a-z_.]+):([a-z_]+)`")
    found: dict[str, tuple[str, str]] = {}
    for row in section.splitlines():
        if row.startswith("|") and not row.startswith(
            "| Module"
        ):  # skip the header row
            for name, module, function in entry.findall(row):
                found[name] = (module, function)
    return found


def _setup_call() -> ast.Call:
    tree = ast.parse(SETUP_PY.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "setup"
        ):
            return node
    raise AssertionError("setup.py has no call to setup()")


def _setup_keyword(name: str) -> ast.expr:
    for keyword in _setup_call().keywords:
        if keyword.arg == name:
            return keyword.value
    raise AssertionError(f"setup() has no keyword {name!r}")


# --------------------------------------------------------------------------------------------
# The record
# --------------------------------------------------------------------------------------------


def test_component_ids_complete() -> None:
    assert set(REQUIRED_COMPONENTS) <= set(_components())


def test_status_values_valid() -> None:
    components = _components()
    for name, component in components.items():
        assert component.get("status") in STATUSES, (
            f"{name}: status {component.get('status')!r}"
        )
    isaac = components["isaac_sim"]
    assert isaac["status"] == "not_evaluated"
    notes = str(isaac.get("notes", ""))
    assert "analisi" in notes and "5.2" in notes, (
        "isaac_sim notes must cite analisi section 5.2"
    )


def test_evidence_required_unless_unverified() -> None:
    allowed = {"agent", "WS00-T05"}
    match = re.search(
        r"^completed_by:\s*(\S+)", WS00_T05.read_text(encoding="utf-8"), re.MULTILINE
    )
    assert match, "WS00-T05 artefact names no completed_by"
    allowed.add(match.group(1))
    for name, component in _components().items():
        if component["status"] not in VERIFIED_STATUSES:
            continue
        assert _nonempty(component.get("evidence")), f"{name}: empty evidence"
        _iso_date(component.get("verified_on"))
        assert component.get("verified_by") in allowed, f"{name}: verified_by"


def test_unverified_components_name_the_human_action() -> None:
    for name, component in _components().items():
        if component["status"] == "unverified":
            assert _nonempty(component.get("human_action")), f"{name}: no human_action"
            assert _nonempty(component.get("notes")), f"{name}: no notes"


def test_version_requires_source_url() -> None:
    def walk(name: str, node: object) -> None:
        if isinstance(node, dict):
            if node.get("version") is not None:
                assert _nonempty(node.get("source_url")), (
                    f"{name}: version without source_url"
                )
            for key, value in node.items():
                walk(f"{name}.{key}", value)
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(f"{name}[{index}]", value)

    walk("components", _components())


def test_verdict_consistent_with_components() -> None:
    record = _record()
    components = _components()
    target = record.get("target")
    assert isinstance(target, dict)
    verdict = record.get("verdict")
    assert verdict in {"adopt_adr_011", "supersede_adr_011", "blocked"}
    gate = {name: components[name]["status"] for name in GATE_COMPONENTS}
    if verdict == "adopt_adr_011":
        assert all(status == "available" for status in gate.values()), gate
        assert target.get("ros_distro") == "jazzy"
        assert target.get("gazebo") == "harmonic"
    if "unavailable" in gate.values():
        assert verdict != "adopt_adr_011", gate
    if verdict == "supersede_adr_011":
        # ADR-042 (accepted 2026-10-08): ROS 2 Humble with Gazebo Classic supersedes ADR-011.
        # Adaptation of the task text (Jazzy and Harmonic): the four gate components must
        # be available for the superseding target, otherwise the verdict is `blocked`.
        assert target.get("ros_distro") == "humble"
        assert target.get("gazebo") == "classic"
        assert all(status == "available" for status in gate.values()), gate
        decision = str(record.get("superseding_adr", ""))
        assert re.fullmatch(r"ADR-\d{3}", decision), decision
        assert f"## {decision} " in DECISIONS.read_text(encoding="utf-8")
    if verdict == "blocked":
        assert _nonempty(record.get("verdict_reasons"))


def test_robot_variant_declared() -> None:
    robot = _components()["robot_sim_pal"]
    assert robot.get("variant") in {"tiago_pro", "tiago", "stand_in"}
    if robot["variant"] == "stand_in":
        notes = str(robot.get("notes", ""))
        assert "no vendor model" in notes
        assert "TIAGo-class" in notes


def test_hospital_world_decision_declared() -> None:
    world = _components()["hospital_world"]
    assert world.get("decision") in {"port_aws", "use_ros2_branch", "procedural"}
    if world["decision"] != "procedural":
        assert _nonempty(world.get("license"))
        assert _nonempty(world.get("source_url"))


def test_onboard_computer_fields() -> None:
    computer = _components()["onboard_computer"]
    for field in ("cpu_model", "cores", "ram_gb", "source_ref", "verified_by"):
        assert field in computer, field
        assert _nonempty(computer[field]), field
        value = computer[field]
        if isinstance(value, str) and value.startswith("not stated"):
            assert re.fullmatch(r"not stated in \S.*", value), value


def test_onboard_computer_gpu_is_not_guessed() -> None:
    """The datasheet lists a GPU only as an upgrade and never says "none" (review F1)."""
    computer = _components()["onboard_computer"]
    gpu = str(computer.get("gpu", ""))
    assert re.fullmatch(r"not stated in \S.*", gpu), gpu
    assert "Jetson" in str(computer.get("gpu_upgrade", ""))


def test_target_and_record_header_declared() -> None:
    record = _record()
    assert record.get("schema_version") == 1
    target = record["target"]
    assert target["ros_distro"] in {"humble", "jazzy"}
    assert target["gazebo"] in {"classic", "fortress", "harmonic"}
    assert re.fullmatch(r"\d+\.\d+", str(target["python_floor"]))
    host = record["host"]
    for field in (
        "os_release",
        "kernel",
        "architecture",
        "cpu_model",
        "cores",
        "ram_gb",
        "gpu",
        "route",
    ):
        assert _nonempty(host.get(field)), f"host.{field}"
    _iso_date(record.get("checked_on"))


# --------------------------------------------------------------------------------------------
# The workspace skeleton
# --------------------------------------------------------------------------------------------


def test_conftest_makes_package_importable() -> None:
    for name in [
        m for m in sys.modules if m == "ralmon_sim" or m.startswith("ralmon_sim.")
    ]:
        del sys.modules[name]
    module = importlib.import_module("ralmon_sim")
    resolved = Path(module.__file__ or "").resolve()
    assert resolved == (PACKAGE_DIR / "ralmon_sim" / "__init__.py").resolve()
    assert str(PACKAGE_DIR) in sys.path


def test_ros_marker_skips_without_rclpy(tmp_path: Path) -> None:
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    (stubs / "rclpy.py").write_text('raise ImportError("rclpy hidden for this test")\n')
    suite = tmp_path / "suite"
    suite.mkdir()
    (suite / "conftest.py").write_text(
        (PACKAGE_DIR / "test" / "conftest.py").read_text()
    )
    (suite / "test_inner.py").write_text(
        textwrap.dedent(
            """
            import pytest

            @pytest.mark.ros
            def test_needs_ros():
                assert False, "must be skipped, not run"

            def test_plain():
                assert True
            """
        )
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        filter(None, [str(stubs), env.get("PYTHONPATH", "")])
    )
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-rs",
            "-p",
            "no:cacheprovider",
            str(suite),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed, 1 skipped" in result.stdout, result.stdout
    assert "failed" not in result.stdout


def _alive(pid: int) -> bool:
    """True when the process exists and is not a zombie (Linux /proc)."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except (FileNotFoundError, ProcessLookupError):
        return False
    return stat.rsplit(")", 1)[1].split()[0] != "Z"


def test_launch_process_fixture_kills_the_process_group(
    launch_process: Callable[..., Any],
) -> None:
    code = (
        "import subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        "print('child', child.pid, flush=True)\n"
        "time.sleep(60)\n"
    )
    handle = launch_process([sys.executable, "-c", code], timeout_s=30.0)
    child_pid = int(handle.read_until("child").split()[-1])
    assert _alive(child_pid)
    handle.stop()
    assert handle.process.poll() is not None
    for _ in range(100):
        if not _alive(child_pid):
            break
        time.sleep(0.05)
    assert not _alive(child_pid), (
        "the grandchild survived the kill of the process group"
    )


def test_setup_py_declares_module_map_entry_points() -> None:
    module_map = _readme_module_map()
    assert set(module_map) == EXPECTED_SCRIPTS, (
        "the README module map changed: update this test"
    )
    entry_points = ast.literal_eval(_setup_keyword("entry_points"))
    declared = {
        match.group(1): (match.group(2), match.group(3))
        for line in entry_points["console_scripts"]
        if (match := re.fullmatch(r"([a-z_]+) = ([a-z_.]+):([a-z_]+)", line))
    }
    assert declared == module_map
    assert len(entry_points["console_scripts"]) == len(module_map)


def test_setup_py_installs_the_resource_directories() -> None:
    source = SETUP_PY.read_text(encoding="utf-8")
    for fragment in (
        "launch",
        "config",
        "config/experiments",
        "config/fault_schedules",
        "worlds",
    ):
        assert f'"{fragment}' in source or f"'{fragment}" in source, fragment
    assert "glob" in source
    assert "resource/" in source and "package.xml" in source


def test_setup_cfg_and_resource_marker() -> None:
    cfg = (PACKAGE_DIR / "setup.cfg").read_text(encoding="utf-8")
    assert "script_dir=$base/lib/ralmon_sim" in cfg
    assert "install_scripts=$base/lib/ralmon_sim" in cfg
    assert (PACKAGE_DIR / "resource" / "ralmon_sim").is_file()
    assert (PACKAGE_DIR / "ralmon_sim" / "__init__.py").is_file()


def test_package_xml_declares_runtime_dependencies() -> None:
    root = ET.parse(PACKAGE_XML).getroot()
    assert root.findtext("name") == "ralmon_sim"
    exec_depend = {(e.text or "").strip() for e in root.findall("exec_depend")}
    assert set(RUNTIME_DEPENDENCIES) <= exec_depend
    build_type = root.find("export/build_type")
    assert build_type is not None and build_type.text == "ament_python"
    declared = {
        (e.text or "").strip()
        for tag in (
            "depend",
            "build_depend",
            "exec_depend",
            "buildtool_depend",
            "test_depend",
        )
        for e in root.findall(tag)
    }
    assert "ralmon" not in declared, "T01 stays independent of the ralmon core"


def test_no_ralmon_import_in_skeleton() -> None:
    offenders: list[str] = []
    for path in sorted(PACKAGE_DIR.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        # the grep of the Done-when list, at the start of a line
        for number, line in enumerate(text.splitlines(), start=1):
            if re.match(r"(import|from) ralmon\b", line):
                offenders.append(f"{path}:{number}")
        if path.suffix == ".py":
            for node in ast.walk(ast.parse(text)):
                names: list[str] = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                if any(
                    name == "ralmon" or name.startswith("ralmon.") for name in names
                ):
                    offenders.append(f"{path}:{node.lineno}")
    assert not offenders, offenders


def test_gitignore_and_sim_repos() -> None:
    ignored = (WORKSPACE / ".gitignore").read_text(encoding="utf-8").split()
    for entry in ("build/", "install/", "log/"):
        assert entry in ignored, entry
    repos = yaml.safe_load((WORKSPACE / "sim.repos").read_text(encoding="utf-8"))
    assert isinstance(repos, dict) and "repositories" in repos
    for name, repo in (repos["repositories"] or {}).items():
        assert repo["type"] == "git", name
        assert str(repo["url"]).startswith("https://"), name
        assert re.fullmatch(r"[0-9a-f]{40}", str(repo["version"])), (
            f"{name}: not a commit"
        )


# --------------------------------------------------------------------------------------------
# The documents and the environment check
# --------------------------------------------------------------------------------------------


def test_availability_doc_has_exactly_the_required_headings() -> None:
    text = DOC.read_text(encoding="utf-8")
    h2 = re.findall(r"^## (.+)$", text, re.MULTILINE)
    assert h2 == HEADINGS


def test_no_placeholder_words_in_record_or_doc() -> None:
    pattern = re.compile("TO" + "DO|TB" + "D|lo" + "rem|[?][?][?]")
    for path in (RECORD, DOC):
        assert not pattern.search(path.read_text(encoding="utf-8")), path


def test_check_script_exits_2_without_ros_environment() -> None:
    env = {"PATH": "/usr/bin:/bin", "HOME": str(PACKAGE_DIR)}
    result = subprocess.run(
        ["bash", str(SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert "ROS 2 environment not sourced" in result.stdout + result.stderr


_STUB_ROS2 = """#!/bin/sh
case "$1 $2" in
  "pkg prefix") echo "/stub/$3" ;;
  "run tracetools") echo "Tracing enabled" ;;
esac
exit 0
"""


def _run_check_script(
    tmp_path: Path, record_text: str
) -> subprocess.CompletedProcess[str]:
    """Run a copy of check_sim_env.sh on `record_text` in a stubbed 'sourced' environment.

    The stubs make every observation succeed, so the result depends on the script and the
    record only, not on the machine (no ROS 2, no Gazebo, no network).
    """
    (tmp_path / "scripts").mkdir()
    (tmp_path / "config").mkdir()
    (tmp_path / "bin").mkdir()
    script = tmp_path / "scripts" / "check_sim_env.sh"
    script.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "config" / "package_availability.yaml").write_text(
        record_text, encoding="utf-8"
    )
    stubs = {
        "ros2": _STUB_ROS2,
        "gazebo": '#!/bin/sh\necho "Gazebo multi-robot simulator, version 11.10.2"\n',
        "lttng": '#!/bin/sh\necho "lttng 2.13.4"\n',
        "tc": "#!/bin/sh\nexit 0\n",
        "ign": "#!/bin/sh\necho 6.18.0\n",
        "gz": "#!/bin/sh\necho 8.0.0\n",
        # a wrapper, not a symlink: a venv interpreter must keep its own location
        "python3": f'#!/bin/sh\nexec "{sys.executable}" "$@"\n',
    }
    for name, text in stubs.items():
        path = tmp_path / "bin" / name
        path.write_text(text, encoding="utf-8")
        path.chmod(0o755)
    env = {
        "PATH": f"{tmp_path / 'bin'}:/usr/bin:/bin",
        "HOME": str(tmp_path),
        "ROS_DISTRO": "humble",
    }
    return subprocess.run(
        ["bash", str(script)],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_check_script_exits_0_on_the_committed_record_when_everything_is_observed(
    tmp_path: Path,
) -> None:
    result = _run_check_script(tmp_path, RECORD.read_text(encoding="utf-8"))
    assert result.returncode == 0, result.stdout + result.stderr
    rows = {
        line.split()[0]: line.split()
        for line in result.stdout.splitlines()
        if len(line.split()) == 3
    }
    assert set(rows) == set(_components())
    assert rows["isaac_sim"][2] == "n/a"
    assert rows["onboard_computer"][2] == "n/a"
    assert all(
        rows[name][2] == "yes"
        for name, component in _components().items()
        if component["status"] == "available"
    )


@pytest.mark.parametrize("name", ["isaac_sim", "onboard_computer"])
def test_check_script_exits_1_when_an_available_component_cannot_be_observed(
    tmp_path: Path, name: str
) -> None:
    record = _record()
    record["components"][name]["status"] = "available"
    result = _run_check_script(tmp_path, yaml.safe_dump(record))
    assert result.returncode == 1, result.stdout + result.stderr
    assert f"{name} available n/a" in result.stdout.splitlines()


@pytest.mark.parametrize(
    "broken",
    [
        "components: [unclosed\n",
        "- a list, not a mapping\n",
        "target: {ros_distro: humble, gazebo: classic}\n",
    ],
    ids=["yaml-syntax", "wrong-type", "missing-keys"],
)
def test_check_script_exits_3_with_one_line_on_a_malformed_record(
    tmp_path: Path, broken: str
) -> None:
    result = _run_check_script(tmp_path, broken)
    output = (result.stdout + result.stderr).splitlines()
    assert result.returncode == 3, result.stdout + result.stderr
    assert "Traceback" not in result.stdout + result.stderr
    assert len([line for line in output if line.strip()]) == 1, output
    assert "cannot read" in output[0]


@pytest.mark.ros
def test_check_script_exit_code_matches_observed_components() -> None:
    result = subprocess.run(
        ["bash", str(SCRIPT)], capture_output=True, text=True, timeout=300, check=False
    )
    rows = [
        line.split() for line in result.stdout.splitlines() if len(line.split()) == 3
    ]
    rows = [row for row in rows if row[2] in {"yes", "no", "n/a"}]
    components = _components()
    assert {row[0] for row in rows} == set(components), result.stdout
    for row in rows:
        assert row[1] == components[row[0]]["status"], row
    missing = [
        r[0]
        for r in rows
        if components[r[0]]["status"] == "available" and r[2] != "yes"
    ]
    assert result.returncode == (1 if missing else 0), result.stdout
