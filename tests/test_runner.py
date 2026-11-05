import importlib.util
import sys
import time
from pathlib import Path

import pytest

RUNNER = Path(__file__).resolve().parent.parent / "sandbox" / "runner.py"


@pytest.fixture
def runner(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKSPACE", str(tmp_path))
    spec = importlib.util.spec_from_file_location("runner_under_test", RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_limits_never_cap_processes_per_uid(runner, monkeypatch):
    # RLIMIT_NPROC counts every process of the uid on the whole host (uid 1000 is often the host's own user).
    calls = []
    monkeypatch.setattr(runner.resource, "setrlimit", lambda which, value: calls.append(which))
    runner._limits()
    assert calls and runner.resource.RLIMIT_NPROC not in calls


def test_run_captures_output_and_exit_code(runner, tmp_path):
    res = runner.run([sys.executable, "-c", "import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)"], tmp_path, 10, "")
    assert (res["rc"], res["stdout"].strip(), res["stderr"].strip(), res["timed_out"]) == (3, "out", "err", False)


def test_run_passes_stdin_and_a_clean_environment(runner, tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_TOKEN", "hunter2")
    res = runner.run([sys.executable, "-c", "import os,sys; print(sys.stdin.read(), os.environ.get('SECRET_TOKEN'))"], tmp_path, 10, "hi")
    assert res["stdout"].strip() == "hi None"


def test_timeout_kills_the_whole_process_group(runner, tmp_path):
    marker = tmp_path / "survivor"
    code = f"import subprocess,time; subprocess.Popen(['sh','-c','sleep 2; touch {marker}']); time.sleep(30)"
    start = time.monotonic()
    res = runner.run([sys.executable, "-c", code], tmp_path, 1, "")
    assert res["timed_out"] and time.monotonic() - start < 10
    time.sleep(2.5)
    assert not marker.exists(), "a child process outlived the timeout"


def test_signal_death_is_a_negative_rc(runner, tmp_path):
    res = runner.run([sys.executable, "-c", "import os,signal; os.kill(os.getpid(), signal.SIGSEGV)"], tmp_path, 10, "")
    assert res["rc"] < 0 and not res["timed_out"]


def test_missing_executable_is_an_oserror(runner, tmp_path):
    with pytest.raises(OSError):
        runner.run(["definitely-not-a-command"], tmp_path, 5, "")


def test_request_validation(runner, tmp_path):
    ok = runner.parse_request({"argv": ["ls"], "cwd": str(tmp_path), "timeout": 9999})
    assert ok[2] == runner.MAX_TIMEOUT
    for bad in (
        {"argv": [], "cwd": str(tmp_path)},
        {"argv": ["ls", 1], "cwd": str(tmp_path)},
        {"argv": ["ls"], "cwd": "/etc"},
        {"argv": ["ls"], "cwd": str(tmp_path / ".." )},
        {"argv": ["ls"], "cwd": str(tmp_path / "missing")},
    ):
        with pytest.raises(ValueError):
            runner.parse_request(bad)


def load_runner(tmp_path, monkeypatch, **env):
    monkeypatch.setenv("WORKSPACE", str(tmp_path))
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    spec = importlib.util.spec_from_file_location("runner_env_test", RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_no_docker_daemon_address_is_passed_on_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    runner = load_runner(tmp_path, monkeypatch)
    assert "DOCKER_HOST" not in runner.ENV and runner.ENV["DOCKER_CONFIG"] == "/tmp/.docker"
    res = runner.run([sys.executable, "-c", "import os; print(os.environ.get('DOCKER_HOST'))"], tmp_path, 10, "")
    assert res["stdout"].strip() == "None"


def test_a_daemon_address_set_for_the_runner_reaches_the_commands_it_runs(tmp_path, monkeypatch):
    runner = load_runner(tmp_path, monkeypatch, DOCKER_HOST="tcp://dind:2375")
    res = runner.run([sys.executable, "-c", "import os; print(os.environ.get('DOCKER_HOST'))"], tmp_path, 10, "")
    assert res["stdout"].strip() == "tcp://dind:2375"


# ---------------------------------------------------------------- SUBJECTS_DIR: the one variable a request may add


def test_a_request_may_add_subjects_dir_only_for_a_folder_inside_the_allowed_roots(runner, tmp_path):
    folder = tmp_path / "abc123" / "subjects"
    folder.mkdir(parents=True)
    assert runner.parse_env({}) == {} and runner.parse_env({"env": None}) == {} and runner.parse_env({"env": {}}) == {}
    assert runner.parse_env({"env": {"SUBJECTS_DIR": str(folder)}}) == {"SUBJECTS_DIR": str(folder.resolve())}
    for bad in (
        {"env": {"SUBJECTS_DIR": "/etc"}},                                     # outside the allowed roots
        {"env": {"SUBJECTS_DIR": str(tmp_path / ".." / "etc")}},
        {"env": {"SUBJECTS_DIR": str(tmp_path / "missing")}},                  # not an existing folder
        {"env": {"SUBJECTS_DIR": str(folder / "x.pdf")}},
        {"env": {"SUBJECTS_DIR": 5}},
        {"env": {"LD_PRELOAD": str(folder)}},                                  # no other variable can be set, ever
        {"env": {"PATH": str(folder)}},
        {"env": {"DOCKER_HOST": "tcp://evil:2375"}},
        {"env": ["SUBJECTS_DIR"]},
    ):
        with pytest.raises(ValueError):
            runner.parse_env(bad)


def test_the_commands_see_subjects_dir_on_top_of_the_clean_environment(runner, tmp_path):
    folder = tmp_path / "subjects"
    folder.mkdir()
    show = [sys.executable, "-c", "import os; print(os.environ.get('SUBJECTS_DIR')); print(sorted(k for k in os.environ if k not in ('LC_CTYPE', '__CF_USER_TEXT_ENCODING')))"]
    plain = runner.run(show, tmp_path, 10, "")["stdout"].splitlines()
    with_it = runner.run(show, tmp_path, 10, "", {"SUBJECTS_DIR": str(folder)})["stdout"].splitlines()
    assert plain[0] == "None" and with_it[0] == str(folder)
    assert "SUBJECTS_DIR" in with_it[1] and with_it[1].replace("'SUBJECTS_DIR', ", "") == plain[1]       # nothing else changed


def post_exec(runner, request):
    """Drive the real HTTP handler's POST /exec without a socket: returns (status, body)."""
    import io
    import json

    answers = []
    handler = object.__new__(runner.Handler)
    body = json.dumps(request).encode()
    handler.path, handler.headers, handler.rfile = "/exec", {"Content-Length": str(len(body))}, io.BytesIO(body)
    handler._send = lambda status, payload: answers.append((status, payload))
    handler.do_POST()
    return answers[0]


def test_the_http_handler_runs_a_command_with_subjects_dir_and_refuses_anything_else(runner, tmp_path):
    folder = tmp_path / "abc123" / "subjects"
    folder.mkdir(parents=True)
    show = [sys.executable, "-c", "import os; print(os.environ.get('SUBJECTS_DIR'), os.environ.get('LD_PRELOAD'))"]
    status, body = post_exec(runner, {"argv": show, "cwd": str(tmp_path), "env": {"SUBJECTS_DIR": str(folder)}})
    assert status == 200 and body["stdout"].split() == [str(folder.resolve()), "None"]
    status, body = post_exec(runner, {"argv": show, "cwd": str(tmp_path)})                                 # no env: as before
    assert status == 200 and body["stdout"].split() == ["None", "None"]
    for env in ({"LD_PRELOAD": "/tmp/evil.so"}, {"SUBJECTS_DIR": "/etc"}, {"SUBJECTS_DIR": str(tmp_path / "missing")}, ["SUBJECTS_DIR"]):
        status, body = post_exec(runner, {"argv": show, "cwd": str(tmp_path), "env": env})
        assert status == 400 and "error" in body, env                                                      # refused before anything runs


def test_commands_never_get_an_ssh_agent(tmp_path, monkeypatch):
    assert "SSH_AUTH_SOCK" not in load_runner(tmp_path, monkeypatch, SSH_AUTH_SOCK="/run/agent.sock").ENV



# ---------------------------------------------------------------- a virtual X display for programs with a window (MiniLibX)


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


class FakeX:
    def __init__(self, folder):
        self.folder, self.log = folder, folder / "log"

    def starts(self, count, wait=3.0):
        """The lines the stand-in server logged, once there are `count` of them (it runs in its own process)."""
        end = time.monotonic() + wait
        while time.monotonic() < end and (not self.log.exists() or len(self.log.read_text().splitlines()) < count):
            time.sleep(0.02)
        return self.log.read_text().splitlines() if self.log.exists() else []

    def need_sockets(self):
        """Kept for the tests that listen on a real socket (below): some sandboxes forbid binding one."""
        import socket
        probe = socket.socket(socket.AF_UNIX)
        try:
            probe.bind(str(self.folder / "x11" / "probe"))
        except PermissionError:
            pytest.skip("this environment forbids binding unix sockets")
        finally:
            probe.close()
            (self.folder / "x11" / "probe").unlink(missing_ok=True)


@pytest.fixture
def xvfb(runner, monkeypatch):
    """A stand-in Xvfb on PATH: it listens on the display's socket, like the real one, and records how it was started."""
    import os
    import stat
    import tempfile
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
        monkeypatch.setattr(runner, "X_DIR", folder / "x11")
        monkeypatch.setattr(runner, "_xvfb", None)
        monkeypatch.setattr(runner, "_display_up", lambda: (folder / "x11" / "X99").exists())      # (the real probe is tried below, on a real socket)
        yield FakeX(folder)
        if runner._xvfb is not None:
            runner._xvfb.kill()
            runner._xvfb.wait()


def test_without_xvfb_commands_run_as_before_with_no_display(runner, tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "/nonexistent")
    assert runner.display_env() == {}
    res = runner.run([sys.executable, "-c", "import os; print(os.environ.get('DISPLAY'))"], tmp_path, 10, "")
    assert res["stdout"].strip() == "None"


def test_every_command_gets_the_display_of_one_virtual_server_started_for_the_container(runner, tmp_path, xvfb):
    assert runner.display_env() == {"DISPLAY": ":99"}
    res = runner.run([sys.executable, "-c", "import os; print(os.environ.get('DISPLAY'))"], tmp_path, 10, "")
    assert res["stdout"].strip() == ":99"
    runner.display_env()
    runner.run(["true"], tmp_path, 10, "")
    assert xvfb.log.read_text().splitlines() == [":99 -screen 0 1280x1024x24 -nolisten tcp -ac"]      # started once, for everything, and not reachable over the network


def test_a_server_that_died_is_started_again_with_what_it_left_behind_removed(runner, tmp_path, xvfb):
    assert runner.display_env() == {"DISPLAY": ":99"}
    first = runner._xvfb
    first.kill()
    first.wait()
    (xvfb.folder / ".X99-lock").write_text("123")                                  # what a server that died leaves behind: its lock and its socket
    assert (xvfb.folder / "x11" / "X99").exists()
    assert runner.display_env() == {"DISPLAY": ":99"} and runner._xvfb is not first
    assert xvfb.starts(2) == [":99 -screen 0 1280x1024x24 -nolisten tcp -ac"] * 2        # (no [STALE]: both were removed first)


def test_a_server_that_cannot_start_means_no_display_and_no_long_wait(runner, tmp_path, monkeypatch, xvfb):
    monkeypatch.setenv("FAKE_XVFB_BROKEN", "1")
    start = time.monotonic()
    assert runner.display_env() == {}
    assert time.monotonic() - start < 4
    res = runner.run([sys.executable, "-c", "import os; print(os.environ.get('DISPLAY'))"], tmp_path, 10, "")
    assert res["stdout"].strip() == "None" and res["rc"] == 0                    # the command still runs


def test_a_request_can_never_choose_the_display(runner, tmp_path, xvfb):
    with pytest.raises(ValueError, match="cannot be set"):
        runner.parse_env({"env": {"DISPLAY": "evil:0"}})
    (tmp_path / "subjects").mkdir()
    res = runner.run([sys.executable, "-c", "import os; print(os.environ.get('DISPLAY'))"], tmp_path, 10, "", {"SUBJECTS_DIR": str(tmp_path / "subjects")})
    assert res["stdout"].strip() == ":99"


def test_the_real_probe_answers_only_when_something_listens_on_the_displays_socket(runner, tmp_path, monkeypatch, xvfb):
    xvfb.need_sockets()
    import socket
    monkeypatch.undo()                                                    # (the stand-in probe is replaced by the real one)
    monkeypatch.setattr(runner, "X_DIR", xvfb.folder / "x11")
    assert runner._display_up() is False
    server = socket.socket(socket.AF_UNIX)
    server.bind(str(xvfb.folder / "x11" / "X99"))
    server.listen(1)
    try:
        assert runner._display_up() is True
    finally:
        server.close()
