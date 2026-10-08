"""Test configuration of the ralmon_sim package (WS07-T01).

Plain Python, no ROS 2 needed: the package directory is put on ``sys.path`` so that
``import ralmon_sim`` resolves to the working tree without installing the package. Tests that
need a ROS 2 installation carry the marker ``ros`` and are skipped when ``rclpy`` cannot be
imported. A helper fixture starts a launch file (or any command) in its own process group and
kills the whole group on teardown.

WS07-T02 adds two fixtures for tests that bring up the simulation: ``display_env`` (an X display
for the Gazebo Classic sensors: the existing ``DISPLAY`` or a private Xvfb) and
``background_launch`` (a long-running command whose output goes to a log file, so that a full pipe
cannot block it, killed with its process group at the end of the module).
"""

from __future__ import annotations

import os
import select
import shutil
import signal
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

PACKAGE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = PACKAGE_DIR.parent.parent

if str(PACKAGE_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGE_DIR))


def _rclpy_importable() -> bool:
    """True when ``import rclpy`` works (a real import: a stub that raises counts as missing)."""
    try:
        import rclpy  # noqa: F401
    except ImportError:
        return False
    return True


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "ros: needs a sourced ROS 2 environment (rclpy importable); skipped otherwise",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if _rclpy_importable():
        return
    skip = pytest.mark.skip(
        reason="rclpy cannot be imported: ROS 2 environment not sourced"
    )
    for item in items:
        if "ros" in item.keywords:
            item.add_marker(skip)


class LaunchHandle:
    """A subprocess running in its own session, so that its process group can be killed."""

    def __init__(
        self, args: list[str], timeout_s: float, env: dict[str, str] | None
    ) -> None:
        self.args = list(args)
        self.timeout_s = timeout_s
        self._deadline = time.monotonic() + timeout_s
        self.process = subprocess.Popen(
            self.args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
            env=env,
        )

    @property
    def pgid(self) -> int:
        return os.getpgid(self.process.pid)

    def read_until(self, needle: str) -> str:
        """Read output lines until ``needle`` appears; fail when the timeout is over."""
        assert self.process.stdout is not None
        seen: list[str] = []
        while time.monotonic() < self._deadline:
            line = self.process.stdout.readline()
            if line == "":
                break
            seen.append(line)
            if needle in line:
                return "".join(seen)
        raise AssertionError(
            f"{needle!r} not seen within {self.timeout_s} s; output:\n" + "".join(seen)
        )

    def stop(self, grace_s: float = 5.0) -> None:
        """Terminate the process group, then kill it if it ignores the signal."""
        try:
            pgid = os.getpgid(self.process.pid)
        except ProcessLookupError:
            pgid = None
        if pgid is not None:
            for sig, wait_s in (
                (signal.SIGINT, grace_s),
                (signal.SIGTERM, grace_s),
                (signal.SIGKILL, 0.0),
            ):
                try:
                    os.killpg(pgid, sig)
                except ProcessLookupError:
                    break
                try:
                    self.process.wait(timeout=wait_s if wait_s > 0 else None)
                    break
                except subprocess.TimeoutExpired:
                    continue
        if self.process.stdout is not None:
            self.process.stdout.close()
        self.process.wait()


@pytest.fixture
def launch_process() -> Iterator[Callable[..., LaunchHandle]]:
    """Factory that starts a command in a subprocess; every started group is killed on teardown.

    ``launch_process(["ros2", "launch", pkg, file], timeout_s=30)`` returns a handle whose
    ``read_until(text)`` waits for a line of output within the timeout.
    """
    handles: list[LaunchHandle] = []

    def start(
        args: list[str], timeout_s: float = 30.0, env: dict[str, str] | None = None
    ) -> LaunchHandle:
        handle = LaunchHandle(args, timeout_s, env)
        handles.append(handle)
        return handle

    yield start
    for handle in reversed(handles):
        handle.stop()


# algorithmic: seconds to wait for Xvfb to report its display number
DISPLAY_WAIT_S = 20.0


@pytest.fixture(scope="session")
def display_env() -> Iterator[dict[str, str]]:
    """Environment entries that give Gazebo Classic an X display (WS07-T02).

    The laser scans of the PAL robots exist only when a display is present (doc/availability.md,
    Reproduction step 8). An existing ``DISPLAY`` is used as it is; otherwise a private ``Xvfb``
    with Mesa software rendering is started (the ``ralmon-ros2`` image has it) and stopped at the
    end of the session. The test fails with the reason when neither exists.
    """
    if os.environ.get("DISPLAY"):
        yield {}
        return
    xvfb = shutil.which("Xvfb")
    if xvfb is None:
        pytest.fail(
            "no X display and no Xvfb: the laser sensors of the simulation need one; "
            "rebuild the image with `docker compose --profile ros2 build ros2`"
        )
    read_fd, write_fd = os.pipe()
    process = subprocess.Popen(
        [
            xvfb,
            "-displayfd",
            str(write_fd),
            "-screen",
            "0",
            "1280x1024x24",
            "+extension",
            "GLX",
            "+render",
            "-noreset",
        ],
        pass_fds=(write_fd,),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    os.close(write_fd)
    try:
        ready, _, _ = select.select([read_fd], [], [], DISPLAY_WAIT_S)
        line = os.read(read_fd, 64).decode("ascii", "replace").strip() if ready else ""
    finally:
        os.close(read_fd)
    if not line.isdigit():
        process.kill()
        process.wait()
        pytest.fail("Xvfb did not report a display number")
    try:
        yield {"DISPLAY": ":" + line, "LIBGL_ALWAYS_SOFTWARE": "1"}
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


class BackgroundLaunch:
    """A command in its own session; its output goes to ``log_path``, never to a pipe."""

    def __init__(self, args: list[str], log_path: Path, env: dict[str, str]) -> None:
        self.args = list(args)
        self.log_path = log_path
        self._log = open(log_path, "w")  # closed in stop()
        self.process = subprocess.Popen(
            self.args,
            stdout=self._log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=env,
        )

    def alive(self) -> bool:
        return self.process.poll() is None

    def tail(self, lines: int = 40) -> str:
        """The last lines of the log (for failure messages)."""
        try:
            text = self.log_path.read_text(errors="replace")
        except OSError:
            return ""
        return "\n".join(text.splitlines()[-lines:])

    def stop(self, grace_s: float = 10.0) -> None:
        """SIGINT, then SIGTERM, then SIGKILL to the whole process group."""
        pgid = None
        try:
            pgid = os.getpgid(self.process.pid)
        except ProcessLookupError:
            pass
        if pgid is not None:
            for sig, wait_s in (
                (signal.SIGINT, grace_s),
                (signal.SIGTERM, grace_s),
                (signal.SIGKILL, 5.0),
            ):
                try:
                    os.killpg(pgid, sig)
                except ProcessLookupError:
                    break
                try:
                    self.process.wait(timeout=wait_s)
                    break
                except subprocess.TimeoutExpired:
                    continue
            # members that outlived the leader are killed with the group
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        self.process.wait()
        self._log.close()


@pytest.fixture(scope="module")
def background_launch(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[Callable[..., BackgroundLaunch]]:
    """Factory for long-running commands (a simulation), killed at the end of the module."""
    started: list[BackgroundLaunch] = []

    def start(
        args: list[str], env: dict[str, str] | None = None, name: str = "launch"
    ) -> BackgroundLaunch:
        log_dir = tmp_path_factory.mktemp(name)
        handle = BackgroundLaunch(
            args, log_dir / (name + ".log"), {**os.environ, **(env or {})}
        )
        started.append(handle)
        return handle

    yield start
    for handle in reversed(started):
        handle.stop()
