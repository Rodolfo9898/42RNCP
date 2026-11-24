"""src/sandbox/execution: running a command with limits, a clean environment and a timeout."""

import sys
import time

import pytest

from sandbox.execution.command import CommandRunner
from sandbox.execution.environment import CommandEnvironment
from sandbox.execution.limits import ResourceLimits
from sandbox.request.validator import ExecRequest
from tests.sandbox.fakes import NoDisplay


def runner_for(display=None, docker_host=""):
    return CommandRunner(CommandEnvironment(display or NoDisplay(), docker_host), ResourceLimits(cpu_seconds=300))


def run(tmp_path, code, timeout=10, stdin="", env=None, runner=None):
    request = ExecRequest([sys.executable, "-c", code], tmp_path, timeout, stdin, env or {})
    return (runner or runner_for()).run(request)


def test_limits_never_cap_processes_per_uid(monkeypatch):
    # RLIMIT_NPROC counts every process of the uid on the whole host (uid 1000 is often the host's own user).
    import resource
    calls = []
    monkeypatch.setattr(resource, "setrlimit", lambda which, value: calls.append(which))
    ResourceLimits(cpu_seconds=300).apply()
    assert calls and resource.RLIMIT_NPROC not in calls


def test_run_captures_output_and_exit_code(tmp_path):
    res = run(tmp_path, "import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)")
    assert (res.rc, res.stdout.strip(), res.stderr.strip(), res.timed_out) == (3, "out", "err", False)


def test_run_passes_stdin_and_a_clean_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_TOKEN", "hunter2")
    res = run(tmp_path, "import os,sys; print(sys.stdin.read(), os.environ.get('SECRET_TOKEN'))", stdin="hi")
    assert res.stdout.strip() == "hi None"


def test_timeout_kills_the_whole_process_group(tmp_path):
    marker = tmp_path / "survivor"
    code = f"import subprocess,time; subprocess.Popen(['sh','-c','sleep 2; touch {marker}']); time.sleep(30)"
    start = time.monotonic()
    res = run(tmp_path, code, timeout=1)
    assert res.timed_out and time.monotonic() - start < 10
    time.sleep(2.5)
    assert not marker.exists(), "a child process outlived the timeout"


def test_signal_death_is_a_negative_rc(tmp_path):
    res = run(tmp_path, "import os,signal; os.kill(os.getpid(), signal.SIGSEGV)")
    assert res.rc < 0 and not res.timed_out


def test_output_is_cut_and_said_to_be(tmp_path):
    runner = CommandRunner(CommandEnvironment(NoDisplay()), ResourceLimits(cpu_seconds=300), max_output=10)
    res = run(tmp_path, "print('x' * 100)", runner=runner)
    assert res.stdout == "x" * 10 and res.truncated


def test_missing_executable_is_an_oserror(tmp_path):
    with pytest.raises(OSError):
        runner_for().run(ExecRequest(["definitely-not-a-command"], tmp_path, 5, ""))


def test_an_executable_that_does_not_start_is_the_shells_127_with_the_reason():
    from sandbox.execution.command import ExecResult
    assert ExecResult.not_started(FileNotFoundError("no such file")).as_dict() == {
        "rc": 127, "stdout": "", "stderr": "no such file", "timed_out": False, "truncated": False}


SHOW_DOCKER_HOST = "import os; print(os.environ.get('DOCKER_HOST'))"


def test_no_docker_daemon_address_is_passed_on_by_default(tmp_path):
    environment = CommandEnvironment.from_environment({}, NoDisplay())
    assert "DOCKER_HOST" not in environment.base and environment.base["DOCKER_CONFIG"] == "/tmp/.docker"
    assert run(tmp_path, SHOW_DOCKER_HOST).stdout.strip() == "None"


def test_a_daemon_address_set_for_the_runner_reaches_the_commands_it_runs(tmp_path):
    environment = CommandEnvironment.from_environment({"DOCKER_HOST": "tcp://dind:2375"}, NoDisplay())
    res = run(tmp_path, SHOW_DOCKER_HOST, runner=CommandRunner(environment, ResourceLimits(cpu_seconds=300)))
    assert res.stdout.strip() == "tcp://dind:2375"


def test_commands_never_get_an_ssh_agent():
    assert "SSH_AUTH_SOCK" not in CommandEnvironment.from_environment({"SSH_AUTH_SOCK": "/run/agent.sock"}, NoDisplay()).build()


def test_the_commands_see_subjects_dir_on_top_of_the_clean_environment(tmp_path):
    folder = tmp_path / "subjects"
    folder.mkdir()
    show = "import os; print(os.environ.get('SUBJECTS_DIR')); print(sorted(k for k in os.environ if k not in ('LC_CTYPE', '__CF_USER_TEXT_ENCODING')))"
    plain = run(tmp_path, show).stdout.splitlines()
    with_it = run(tmp_path, show, env={"SUBJECTS_DIR": str(folder)}).stdout.splitlines()
    assert plain[0] == "None" and with_it[0] == str(folder)
    assert "SUBJECTS_DIR" in with_it[1] and with_it[1].replace("'SUBJECTS_DIR', ", "") == plain[1]       # nothing else changed
