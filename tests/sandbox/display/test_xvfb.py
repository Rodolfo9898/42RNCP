"""src/sandbox/display: a virtual X display for programs with a window (MiniLibX), started once and again when it dies."""

import os
import socket
import stat
import sys
import tempfile
import time
from pathlib import Path

import pytest

from sandbox.display.probe import DisplayProbe
from sandbox.display.xvfb import VirtualDisplay

FAKE_XVFB = """#!%(python)s
import os, sys, time
number = sys.argv[1][1:]
folder = os.environ["FAKE_X_DIR"]
if os.environ.get("FAKE_XVFB_BROKEN"):
    sys.exit(1)
marker = os.path.join(folder, "X" + number)
stale = os.path.exists(marker) or os.path.exists(os.path.join(os.path.dirname(folder), ".X" + number + "-lock"))
open(os.environ["FAKE_X_LOG"], "a").write(" ".join(sys.argv[1:]) + (" [STALE]" if stale else "") + "\\n")
open(marker, "w").write("up")                      # where the real server has its socket: "the display answers"
time.sleep(60)
"""

STARTED_AS = ":99 -screen 0 1280x1024x24 -nolisten tcp -ac"


class FileProbe:
    """The stand-in server 'listens' by creating the file the real one has its socket at."""

    def __init__(self, folder):
        self.folder = folder

    def is_up(self):
        return (self.folder / "X99").exists()


class FakeX:
    def __init__(self, folder, display):
        self.folder, self.log, self.display = folder, folder / "log", display

    def starts(self, count, wait=3.0):
        """The lines the stand-in server logged, once there are `count` of them (it runs in its own process)."""
        end = time.monotonic() + wait
        while time.monotonic() < end and (not self.log.exists() or len(self.log.read_text().splitlines()) < count):
            time.sleep(0.02)
        return self.log.read_text().splitlines() if self.log.exists() else []


@pytest.fixture
def xvfb(monkeypatch):
    """A stand-in Xvfb on PATH: it 'listens' on the display's socket path, like the real one, and records how it was started."""
    with tempfile.TemporaryDirectory(dir="/tmp", prefix="xv") as folder:        # (short: unix socket paths are length-limited)
        folder = Path(folder)
        (folder / "bin").mkdir()
        (folder / "x11").mkdir()
        exe = folder / "bin" / "Xvfb"
        exe.write_text(FAKE_XVFB % {"python": sys.executable})
        exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
        monkeypatch.setenv("PATH", f"{folder / 'bin'}:{os.environ['PATH']}")
        monkeypatch.setenv("FAKE_X_DIR", str(folder / "x11"))
        monkeypatch.setenv("FAKE_X_LOG", str(folder / "log"))
        display = VirtualDisplay(directory=folder / "x11", probe=FileProbe(folder / "x11"))     # (the real probe is tried below, on a real socket)
        yield FakeX(folder, display)
        display.stop()


def test_without_xvfb_there_is_no_display(monkeypatch):
    monkeypatch.setenv("PATH", "/nonexistent")
    assert VirtualDisplay().environment() == {}


def test_one_virtual_server_is_started_for_everything_that_asks_and_it_is_not_reachable_over_the_network(xvfb):
    assert xvfb.display.environment() == {"DISPLAY": ":99"}
    xvfb.display.environment()
    assert xvfb.log.read_text().splitlines() == [STARTED_AS]


def test_a_server_that_died_is_started_again_with_what_it_left_behind_removed(xvfb):
    assert xvfb.display.environment() == {"DISPLAY": ":99"}
    first = xvfb.display._process
    first.kill()
    first.wait()
    (xvfb.folder / ".X99-lock").write_text("123")                                  # what a server that died leaves behind: its lock and its socket
    assert (xvfb.folder / "x11" / "X99").exists()
    assert xvfb.display.environment() == {"DISPLAY": ":99"} and xvfb.display._process is not first
    assert xvfb.starts(2) == [STARTED_AS] * 2                                      # (no [STALE]: both were removed first)


def test_a_server_that_cannot_start_means_no_display_and_no_long_wait(monkeypatch, xvfb):
    monkeypatch.setenv("FAKE_XVFB_BROKEN", "1")
    start = time.monotonic()
    assert xvfb.display.environment() == {}
    assert time.monotonic() - start < 4


def test_an_executable_that_cannot_be_run_means_no_display(monkeypatch, tmp_path):
    broken = tmp_path / "bin"
    broken.mkdir()
    (broken / "Xvfb").write_text("not a program")
    (broken / "Xvfb").chmod(0o755)
    monkeypatch.setenv("PATH", str(broken))
    assert VirtualDisplay(directory=tmp_path / "x11", probe=FileProbe(tmp_path)).environment() == {}


def test_stopping_the_display_ends_the_server(xvfb):
    xvfb.display.environment()
    process = xvfb.display._process
    xvfb.display.stop()
    assert process.poll() is not None
    xvfb.display.stop()                                                            # (and again is harmless)


def test_the_real_probe_answers_only_when_something_listens_on_the_displays_socket(xvfb):
    probe = socket.socket(socket.AF_UNIX)
    try:
        probe.bind(str(xvfb.folder / "x11" / "probe"))
    except PermissionError:
        pytest.skip("this environment forbids binding unix sockets")
    finally:
        probe.close()
        (xvfb.folder / "x11" / "probe").unlink(missing_ok=True)
    real = DisplayProbe("99", xvfb.folder / "x11")
    assert real.is_up() is False
    server = socket.socket(socket.AF_UNIX)
    server.bind(str(xvfb.folder / "x11" / "X99"))
    server.listen(1)
    try:
        assert real.is_up() is True
    finally:
        server.close()
