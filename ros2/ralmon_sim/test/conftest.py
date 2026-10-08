"""Test configuration of the ralmon_sim package (WS07-T01).

Plain Python, no ROS 2 needed: the package directory is put on ``sys.path`` so that
``import ralmon_sim`` resolves to the working tree without installing the package. Tests that
need a ROS 2 installation carry the marker ``ros`` and are skipped when ``rclpy`` cannot be
imported. A helper fixture starts a launch file (or any command) in its own process group and
kills the whole group on teardown.
"""

from __future__ import annotations

import os
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


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if _rclpy_importable():
        return
    skip = pytest.mark.skip(reason="rclpy cannot be imported: ROS 2 environment not sourced")
    for item in items:
        if "ros" in item.keywords:
            item.add_marker(skip)


class LaunchHandle:
    """A subprocess running in its own session, so that its process group can be killed."""

    def __init__(self, args: list[str], timeout_s: float, env: dict[str, str] | None) -> None:
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
        raise AssertionError(f"{needle!r} not seen within {self.timeout_s} s; output:\n" + "".join(seen))

    def stop(self, grace_s: float = 5.0) -> None:
        """Terminate the process group, then kill it if it ignores the signal."""
        try:
            pgid = os.getpgid(self.process.pid)
        except ProcessLookupError:
            pgid = None
        if pgid is not None:
            for sig, wait_s in ((signal.SIGINT, grace_s), (signal.SIGTERM, grace_s), (signal.SIGKILL, 0.0)):
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
