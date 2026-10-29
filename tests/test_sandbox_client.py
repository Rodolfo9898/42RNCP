"""The web app's client for the sandbox runner: what it sends, and the extra environment of a run."""

import json

import httpx

from verdict.sandbox import Sandbox

REAL_CLIENT = httpx.Client          # captured once: patching it again must not wrap an earlier patch


def posted(monkeypatch, sandbox, **kw):
    seen = []
    real_client = REAL_CLIENT

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"rc": 0, "stdout": "ok"})

    monkeypatch.setattr(httpx, "Client", lambda **opts: real_client(transport=httpx.MockTransport(handler)))
    result = sandbox.exec(["ls"], kw.get("cwd", "/workspace/abc/work"))
    return seen[0], result


def test_a_plain_sandbox_sends_no_environment(monkeypatch):
    body, result = posted(monkeypatch, Sandbox("http://sandbox:8001"))
    assert "env" not in body and body["argv"] == ["ls"] and result.ok


def test_with_env_adds_variables_to_every_command_of_that_client_only(monkeypatch):
    base = Sandbox("http://sandbox:8001/")
    scoped = base.with_env({"SUBJECTS_DIR": "/workspace/abc/subjects"})
    body, _ = posted(monkeypatch, scoped)
    assert body["env"] == {"SUBJECTS_DIR": "/workspace/abc/subjects"} and scoped.url == "http://sandbox:8001"
    assert base.env == {} and "env" not in posted(monkeypatch, base)[0]                       # the shared client is untouched
    assert scoped.with_env({"SUBJECTS_DIR": "/workspace/def/subjects"}).env == {"SUBJECTS_DIR": "/workspace/def/subjects"}
