import shutil
import subprocess
from pathlib import Path

import pytest

from verdict.sandbox import ExecResult, sandbox_selftest
from verdict.selftest import PROBES, Outcome, run_selftest, summarize


def by_name(results):
    return {r["name"]: r for r in results}


class Recorder:
    """A fake environment: records every command, and fails the ones listed in `broken`."""

    def __init__(self, broken=(), raising=(), timeout=()):
        self.calls, self.broken, self.raising, self.timeout = [], set(broken), set(raising), set(timeout)

    def __call__(self, argv, cwd, timeout):
        self.calls.append((argv, cwd))
        key = " ".join(argv[:2])
        if key in self.raising:
            raise RuntimeError("the runner fell over")
        if key in self.timeout:
            return Outcome(-1, timed_out=True)
        if key in self.broken:
            return Outcome(127, stderr=f"{argv[0]}: not found\nmore noise")
        return Outcome(0, stdout=f"{argv[0]} 1.2.3\nsecond line")


def test_everything_present_means_ready(tmp_path):
    results = run_selftest(Recorder(), tmp_path)
    names = by_name(results)
    for expected in [p[0] for p in PROBES] + ["build C and C++ with make", "run the C program", "run the C++ program"]:
        assert names[expected]["ok"], expected
    assert names["make"]["detail"] == "make 1.2.3"                       # first line only
    assert summarize(results) == {"ready": True, "failed": [], "basics_ok": True, "docker_ok": True, "docker_daemon_down": False}


def test_the_real_build_happens_in_a_scratch_folder_that_is_removed(tmp_path):
    recorder = Recorder()
    run_selftest(recorder, tmp_path)
    build = next((argv, cwd) for argv, cwd in recorder.calls if argv == ["make"])
    assert build[1].parent == tmp_path and build[1].name.startswith("selftest-")
    assert [argv for argv, _ in recorder.calls if argv in (["./c"], ["./cpp"])] == [["./c"], ["./cpp"]]
    assert not build[1].exists() and list(tmp_path.iterdir()) == []


def test_a_missing_compiler_is_reported_as_not_ready_and_named(tmp_path):
    results = run_selftest(Recorder(broken={"c++ --version", "make --version"}), tmp_path)
    s = summarize(results)
    assert not s["ready"] and s["failed"] == ["C++ compiler (c++)", "make"] and not s["basics_ok"] and s["docker_ok"]
    assert by_name(results)["make"]["detail"] == "make: not found"


def test_docker_client_without_a_daemon_is_a_distinct_problem(tmp_path):
    results = run_selftest(Recorder(broken={"docker info"}), tmp_path)
    s = summarize(results)
    assert s["basics_ok"] and not s["docker_ok"] and s["docker_daemon_down"] and s["failed"] == ["docker daemon"]


def test_no_docker_at_all_is_not_confused_with_a_down_daemon(tmp_path):
    results = run_selftest(Recorder(broken={"docker --version", "docker compose", "docker info"}), tmp_path)
    s = summarize(results)
    assert not s["docker_ok"] and not s["docker_daemon_down"] and "docker client" in s["failed"]


def test_optional_tools_do_not_block_readiness(tmp_path):
    results = run_selftest(Recorder(broken={"valgrind --version", "norminette --version"}), tmp_path)
    assert summarize(results)["ready"] is True
    assert [r["required"] for r in results if r["name"] in ("valgrind", "norminette")] == [False, False]


def test_a_failing_make_skips_running_the_programs(tmp_path):
    recorder = Recorder(broken={"make"})
    results = run_selftest(recorder, tmp_path)
    assert not by_name(results)["build C and C++ with make"]["ok"]
    assert "run the C program" not in by_name(results) and ["./c"] not in [a for a, _ in recorder.calls]


def test_a_crash_or_timeout_in_the_runner_is_reported_not_raised(tmp_path):
    results = run_selftest(Recorder(raising={"cc --version"}, timeout={"docker info"}), tmp_path)
    named = by_name(results)
    assert not named["C compiler (cc)"]["ok"] and "the runner fell over" in named["C compiler (cc)"]["detail"]
    assert not named["docker daemon"]["ok"] and named["docker daemon"]["detail"] == "timed out"


def test_the_docker_build_only_runs_when_asked(tmp_path):
    shallow = Recorder()
    run_selftest(shallow, tmp_path)
    assert not any(a[:2] == ["docker", "build"] for a, _ in shallow.calls)
    deep = Recorder()
    results = run_selftest(deep, tmp_path, deep=True)
    assert [a for a, _ in deep.calls if a[:2] == ["docker", "build"]] and by_name(results)["docker run the image"]["ok"]
    failing = run_selftest(Recorder(broken={"docker build"}), tmp_path, deep=True)
    assert "docker run the image" not in by_name(failing) and not summarize(failing)["ready"]


def test_extra_probes_for_one_environment(tmp_path):
    results = run_selftest(Recorder(broken={"gdb --version"}), tmp_path, extra=[("gdb", ["gdb", "--version"], False), ("claude", ["claude", "--version"], True)])
    named = by_name(results)
    assert named["gdb"]["required"] is False and named["claude"]["required"] is True and summarize(results)["ready"]


@pytest.mark.skipif(not (shutil.which("make") and shutil.which("cc") and shutil.which("c++")), reason="needs make, cc and c++")
def test_a_real_environment_really_compiles_and_runs_c_and_cpp(tmp_path):
    """No fakes: the C and C++ programs are compiled with the strict flags through make and executed."""
    def run(argv, cwd, timeout):
        done = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return Outcome(done.returncode, done.stdout, done.stderr)

    named = by_name(run_selftest(run, tmp_path))
    for step in ("C compiler (cc)", "C++ compiler (c++)", "make", "build C and C++ with make"):
        assert named[step]["ok"], named[step]
    assert named["run the C program"]["detail"] == "hello from C"
    assert named["run the C++ program"]["detail"] == "hello from C++"


def test_the_sandbox_adapter_runs_everything_through_the_runner_inside_the_workspace(tmp_path):
    class FakeSandbox:
        def __init__(self):
            self.cwds = []

        def exec(self, argv, cwd, timeout=60, stdin=""):
            self.cwds.append(Path(cwd))
            return ExecResult(rc=0, stdout=f"{argv[0]} ok\n")

    sandbox = FakeSandbox()
    results = sandbox_selftest(sandbox, tmp_path)
    assert summarize(results)["ready"] and all(c == tmp_path / "_selftest" or (tmp_path / "_selftest") in c.parents for c in sandbox.cwds)
