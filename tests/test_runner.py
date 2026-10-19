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
    if sys.platform == "darwin":  # RLIMIT_NPROC would constrain the developer's whole account
        monkeypatch.setattr(module, "_limits", lambda: None)
    return module


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
