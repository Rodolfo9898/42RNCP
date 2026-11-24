"""The web app's gateway to the terminal service: the paths it calls, the token it sends, and what it makes of the answers.

The terminal service is an `httpx.MockTransport` here: these tests pin the internal REST contract from the web app's side."""

import httpx
import pytest

from verdict.core.errors import Unavailable
from verdict.gateways.terminal import NO_REPORT, NullTerminal, TerminalGateway

URL, TOKEN = "http://terminal:8002", "tok"


class Service:
    """A terminal service that answers what it is told to and remembers every request it got."""

    def __init__(self, answers=None):
        self.requests, self.answers = [], dict(answers or {})

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        answer = self.answers.get((request.method, request.url.path), httpx.Response(404, json={"detail": "not found"}))
        if isinstance(answer, Exception):
            raise answer
        return answer

    def gateway(self) -> TerminalGateway:
        return TerminalGateway(URL, TOKEN, transport=httpx.MockTransport(self))

    @property
    def last(self) -> httpx.Request:
        return self.requests[-1]


def json_answer(body, status=200):
    return httpx.Response(status, json=body)


def test_the_report_of_a_session_is_read_from_its_address_with_the_token():
    service = Service({("GET", "/sessions/abc123/report"): json_answer({"found": True, "text": "# Review", "name": "claude-review.md"})})
    assert service.gateway().report("abc123") == {"found": True, "text": "# Review", "name": "claude-review.md"}
    assert (service.last.method, str(service.last.url), service.last.headers["x-terminal-token"]) == ("GET", f"{URL}/sessions/abc123/report", TOKEN)


def test_a_report_that_is_not_there_is_an_answer_not_an_error():
    service = Service({("GET", "/sessions/abc123/report"): json_answer({"found": False, "text": "", "name": "claude-review.md"})})
    assert service.gateway().report("abc123")["found"] is False


@pytest.mark.parametrize("answer", [httpx.ConnectError("refused"), httpx.ReadTimeout("slow"), json_answer({"detail": "bad token"}, 401),
                                    json_answer({"detail": "boom"}, 500)])
def test_a_report_that_cannot_be_asked_for_raises_so_the_caller_can_say_the_terminal_is_down(answer):
    service = Service({("GET", "/sessions/abc123/report"): answer})
    with pytest.raises(httpx.HTTPError):
        service.gateway().report("abc123")


def test_a_new_run_deletes_the_last_report():
    service = Service({("DELETE", "/sessions/abc123/report"): json_answer({"deleted": True})})
    assert service.gateway().delete_report("abc123") is True
    assert (service.last.method, str(service.last.url), service.last.headers["x-terminal-token"]) == ("DELETE", f"{URL}/sessions/abc123/report", TOKEN)
    service.answers[("DELETE", "/sessions/abc123/report")] = json_answer({"deleted": False})
    assert service.gateway().delete_report("abc123") is False


@pytest.mark.parametrize("answer", [httpx.ConnectError("down"), json_answer({"detail": "no"}, 403), httpx.Response(200, text="not json"),
                                    json_answer({"detail": "boom"}, 500)])
def test_deleting_the_report_is_best_effort_and_never_stops_a_run(answer):
    service = Service({("DELETE", "/sessions/abc123/report"): answer})
    assert service.gateway().delete_report("abc123") is False


def test_the_digests_of_the_pdfs_the_terminal_holds_are_read_by_name():
    digests = {"push_swap.pdf": "a" * 64, "en.norm.pdf": "b" * 64}
    service = Service({("GET", "/sessions/abc123/subjects"): json_answer({"files": digests})})
    assert service.gateway().subject_digests("abc123") == digests
    assert (str(service.last.url), service.last.headers["x-terminal-token"]) == (f"{URL}/sessions/abc123/subjects", TOKEN)
    service.answers[("GET", "/sessions/abc123/subjects")] = json_answer({"files": None})
    assert service.gateway().subject_digests("abc123") == {}
    service.answers[("GET", "/sessions/abc123/subjects")] = json_answer({})
    assert service.gateway().subject_digests("abc123") == {}


def test_the_pdfs_are_put_as_a_multipart_replacing_the_ones_held():
    service = Service({("PUT", "/sessions/abc123/subjects"): json_answer({"stored": ["push_swap.pdf", "en.norm.pdf"]})})
    pdfs = {"push_swap.pdf": b"%PDF-1.4 subject", "en.norm.pdf": b"%PDF-1.4 norm"}
    assert service.gateway().put_subjects("abc123", pdfs) is None
    request = service.last
    assert (request.method, str(request.url), request.headers["x-terminal-token"]) == ("PUT", f"{URL}/sessions/abc123/subjects", TOKEN)
    assert request.headers["content-type"].startswith("multipart/form-data; boundary=")
    body = request.content
    for name, data in pdfs.items():
        assert f'name="files"; filename="{name}"'.encode() in body and data in body
    assert body.count(b"Content-Type: application/pdf") == 2
    assert request.extensions["timeout"]["read"] == 60                            # (PDFs can be big: more time than for a question)


def test_a_terminal_that_refuses_the_pdfs_raises_to_the_handover_that_logs_it():
    service = Service({("PUT", "/sessions/abc123/subjects"): json_answer({"detail": "not a pdf"}, 400)})
    with pytest.raises(httpx.HTTPStatusError):
        service.gateway().put_subjects("abc123", {"x.pdf": b"%PDF"})


def test_the_environment_of_the_terminal_is_asked_shallow_or_deep():
    tools = [{"name": "make", "ok": True, "required": True, "detail": "GNU Make 4.4"}]
    service = Service({("GET", "/environment"): json_answer({"tools": tools})})
    gateway = service.gateway()
    assert gateway.environment() == {"tools": tools}
    assert service.last.url.params["deep"] == "false" and service.last.headers["x-terminal-token"] == TOKEN
    assert service.last.extensions["timeout"]["read"] == 90
    assert gateway.environment(deep=True) == {"tools": tools}
    assert service.last.url.params["deep"] == "true" and service.last.extensions["timeout"]["read"] == 360      # (it builds a Dockerfile)


@pytest.mark.parametrize("answer", [httpx.ConnectError("refused"), json_answer({"detail": "bad token"}, 401), httpx.Response(200, text="<html>"),
                                    json_answer({"detail": "boom"}, 500)])
def test_an_environment_that_cannot_be_read_is_an_unavailable_terminal_with_a_message(answer):
    service = Service({("GET", "/environment"): answer})
    with pytest.raises(Unavailable) as raised:
        service.gateway().environment()
    assert raised.value.message.startswith("could not reach the terminal service (") and raised.value.status == 503


def test_every_call_carries_the_token_and_the_health_check_is_never_used():
    answers = {("GET", "/sessions/s1/report"): json_answer({"found": False, "text": "", "name": ""}),
               ("DELETE", "/sessions/s1/report"): json_answer({"deleted": False}),
               ("GET", "/sessions/s1/subjects"): json_answer({"files": {}}),
               ("PUT", "/sessions/s1/subjects"): json_answer({"stored": []}),
               ("GET", "/environment"): json_answer({"tools": []})}
    service = Service(answers)
    gateway = service.gateway()
    gateway.report("s1")
    gateway.delete_report("s1")
    gateway.subject_digests("s1")
    gateway.put_subjects("s1", {"a.pdf": b"%PDF"})
    gateway.environment()
    assert [(r.method, r.url.path) for r in service.requests] == list(answers)
    assert all(r.headers["x-terminal-token"] == TOKEN for r in service.requests) and "/health" not in {r.url.path for r in service.requests}


def test_the_address_may_end_with_a_slash_and_no_proxy_variable_is_honoured(monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.invalid:3128")
    monkeypatch.setenv("ALL_PROXY", "http://proxy.invalid:3128")
    service = Service({("GET", "/sessions/s1/report"): json_answer({"found": False, "text": "", "name": ""})})
    gateway = TerminalGateway(URL + "/", TOKEN, transport=httpx.MockTransport(service))
    gateway.report("s1")
    assert str(service.last.url) == f"{URL}/sessions/s1/report" and gateway.url == URL
    seen = {}
    real = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kw: seen.update(kw) or real(transport=httpx.MockTransport(service)))
    TerminalGateway(URL, TOKEN).report("s1")
    assert seen["trust_env"] is False                                                # an internal service: the proxies are never used


def test_without_a_terminal_nothing_is_found_and_nothing_is_done():
    terminal = NullTerminal()
    assert terminal.configured is False
    assert terminal.report("s1") == NO_REPORT and terminal.report("s1") is not NO_REPORT           # (a copy: nobody can change the constant)
    assert terminal.delete_report("s1") is False and terminal.subject_digests("s1") == {} and terminal.put_subjects("s1", {"a.pdf": b"%PDF"}) is None
    with pytest.raises(Unavailable, match="not configured"):
        terminal.environment()


def test_the_gateway_is_a_configured_terminal():
    assert TerminalGateway(URL, TOKEN).configured is True

