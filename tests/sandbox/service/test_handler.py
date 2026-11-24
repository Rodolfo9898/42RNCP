"""src/sandbox/service: the HTTP handler and the facade behind it."""

import io
import json
import sys
from types import SimpleNamespace

import pytest

from sandbox.execution.command import CommandRunner
from sandbox.execution.environment import CommandEnvironment
from sandbox.execution.limits import ResourceLimits
from sandbox.request.roots import AllowedRoots
from sandbox.request.validator import RequestValidator
from sandbox.service.exec_service import ExecService
from sandbox.service.handler import RunnerHandler
from sandbox.service.serve import build_service
from tests.sandbox.fakes import NoDisplay


@pytest.fixture
def service(tmp_path):
    return build_service({"WORKSPACE": str(tmp_path)}, NoDisplay())


def call(service, method, path, body=b"", length=None, max_body=1_000_000):
    """Drive the real HTTP handler without a socket: returns (status, answer)."""
    answers = []
    handler = object.__new__(RunnerHandler)
    handler.path, handler.rfile = path, io.BytesIO(body)
    handler.headers = {} if length is False else {"Content-Length": str(len(body) if length is None else length)}
    handler.server = SimpleNamespace(service=service, max_body=max_body)
    handler._send = lambda status, payload: answers.append((status, payload))
    getattr(handler, f"do_{method}")()
    return answers[0]


def post_exec(service, request):
    return call(service, "POST", "/exec", json.dumps(request).encode())


def test_the_http_handler_runs_a_command_with_subjects_dir_and_refuses_anything_else(service, tmp_path):
    folder = tmp_path / "abc123" / "subjects"
    folder.mkdir(parents=True)
    show = [sys.executable, "-c", "import os; print(os.environ.get('SUBJECTS_DIR'), os.environ.get('LD_PRELOAD'))"]
    status, body = post_exec(service, {"argv": show, "cwd": str(tmp_path), "env": {"SUBJECTS_DIR": str(folder)}})
    assert status == 200 and body["stdout"].split() == [str(folder.resolve()), "None"]
    status, body = post_exec(service, {"argv": show, "cwd": str(tmp_path)})                                 # no env: as before
    assert status == 200 and body["stdout"].split() == ["None", "None"]
    for env in ({"LD_PRELOAD": "/tmp/evil.so"}, {"SUBJECTS_DIR": "/etc"}, {"SUBJECTS_DIR": str(tmp_path / "missing")}, ["SUBJECTS_DIR"]):
        status, body = post_exec(service, {"argv": show, "cwd": str(tmp_path), "env": env})
        assert status == 400 and "error" in body, env                                                      # refused before anything runs


def test_a_body_that_is_not_a_request_is_a_400(service, tmp_path):
    for raw in (b"not json", b"[]", b"{}", b'{"argv": ["ls"]}', b'{"argv": ["ls"], "cwd": 5}'):
        status, body = call(service, "POST", "/exec", raw)
        assert status == 400 and "error" in body, raw
    assert call(service, "POST", "/exec", b"{}", length=False)[0] == 400                                   # no Content-Length: an empty body
    assert call(service, "POST", "/exec", b"{}", length="many")[0] == 400


def test_a_body_over_the_limit_is_refused_without_being_read(service, tmp_path):
    assert call(service, "POST", "/exec", b"x" * 20, max_body=10)[0] == 413


def test_a_command_that_cannot_start_answers_127_not_an_error(service, tmp_path):
    status, body = post_exec(service, {"argv": ["definitely-not-a-command"], "cwd": str(tmp_path)})
    assert status == 200 and body["rc"] == 127 and body["stderr"] and not body["timed_out"]


def test_only_health_and_exec_exist(service):
    assert call(service, "GET", "/health") == (200, {"status": "ok"})
    assert call(service, "GET", "/exec")[0] == 404
    assert call(service, "POST", "/health")[0] == 404


def test_the_facade_needs_nothing_but_a_validator_and_a_runner(tmp_path):
    validator = RequestValidator(AllowedRoots([tmp_path]), 300)
    runner = CommandRunner(CommandEnvironment(NoDisplay()), ResourceLimits(cpu_seconds=300))
    status, body = ExecService(validator, runner).handle(json.dumps({"argv": ["true"], "cwd": str(tmp_path)}).encode())
    assert status == 200 and body["rc"] == 0
