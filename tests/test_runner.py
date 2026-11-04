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
