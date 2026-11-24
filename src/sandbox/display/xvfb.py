"""A virtual X display. Standard library only: the sandbox image has no dependencies, and the terminal service reuses this."""

from __future__ import annotations

import resource
import shutil
import subprocess
import threading
import time
from pathlib import Path

from sandbox.display.probe import DisplayProbe

START_WAIT_SECONDS = 5


class VirtualDisplay:
    """Programs with a window (MiniLibX: fract-ol, so_long, cub3D...) need an X display, and a container has none. Xvfb is a virtual one:
    the program draws into memory and nobody sees it, but mlx_init() succeeds, so such a program can be started, crash-tested and run
    under valgrind. One server for the whole container, started with the first command that asks and again if it ever dies.
    (A lazily started shared service: the composition root makes one and hands it to whoever builds environments.)"""

    def __init__(self, display: str = ":99", screen: str = "1280x1024x24", directory: Path = Path("/tmp/.X11-unix"),
                 probe: DisplayProbe | None = None) -> None:
        self.display, self.screen, self.directory = display, screen, directory
        self.probe = probe or DisplayProbe(display[1:], directory)
        self._process: subprocess.Popen | None = None
        self._lock = threading.Lock()

    def environment(self) -> dict[str, str]:
        """{"DISPLAY": ":99"} when a virtual X server is running (started, or restarted, here); {} when this image has none."""
        executable = shutil.which("Xvfb")
        if executable is None:
            return {}
        with self._lock:
            if (self._process is None or self._process.poll() is not None) and not self._start(executable):
                return {}
            return {"DISPLAY": self.display} if self._wait_until_up() else {}

    def stop(self) -> None:
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                self._process.kill()
                self._process.wait()

    def _start(self, executable: str) -> bool:
        number = self.display[1:]
        for stale in (self.directory.parent / f".X{number}-lock", self.directory / f"X{number}"):       # what a server that died leaves behind
            try:
                stale.unlink()
            except OSError:
                pass
        try:
            self.directory.mkdir(mode=0o1777, exist_ok=True)
            self.directory.chmod(0o1777)
        except OSError:
            pass
        try:
            self._process = subprocess.Popen([executable, self.display, "-screen", "0", self.screen, "-nolisten", "tcp", "-ac"],
                                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                             start_new_session=True, preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_CORE, (0, 0)))
        except OSError:
            self._process = None
            return False
        return True

    def _wait_until_up(self) -> bool:
        end = time.monotonic() + START_WAIT_SECONDS
        while not self.probe.is_up():
            if self._process.poll() is not None or time.monotonic() > end:
                return False
            time.sleep(0.05)
        return True
