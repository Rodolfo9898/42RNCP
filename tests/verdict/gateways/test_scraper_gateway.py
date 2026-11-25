"""The web app's gateway to the subject downloader: the paths it calls, the token it sends, and what it makes of the answers.

The scraper service is an `httpx.MockTransport` here: these tests pin the internal REST contract from the web app's side."""

import json

import httpx
import pytest

from verdict.core.errors import Conflict, Failed, Unavailable, VerdictError
from verdict.gateways.scraper import NOT_CONFIGURED, TOKEN_REFUSED, UNREACHABLE, NullScraper, ScraperGateway

URL, TOKEN = "http://scraper:8003", "s3cr3t-token"
PLAN = {"session": {"valid": True, "reason": ""}, "tracks": [], "unknown": [], "misplaced": 0}
EVERY_CALL = [
    ("plan", ([], True), {}, ("GET", "/plan")),
    ("start_download", (), {"tracks": None, "projects": None, "artifacts": True, "children": True, "force": False}, ("POST", "/downloads")),
    ("current_download", (0,), {}, ("GET", "/downloads/current")),
    ("cancel_download", (), {}, ("DELETE", "/downloads/current")),
    ("reorganize", (True,), {}, ("POST", "/reorganizations")),
]


class Service:
    """A scraper service that answers what it is told to and remembers every request it got."""

    def __init__(self, answers=None):
        self.requests, self.answers = [], dict(answers or {})

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        answer = self.answers.get((request.method, request.url.path), httpx.Response(404, json={"detail": "not found"}))
        if isinstance(answer, Exception):
            raise answer
        return answer

    def gateway(self) -> ScraperGateway:
        return ScraperGateway(URL, TOKEN, transport=httpx.MockTransport(self))

    @property
    def last(self) -> httpx.Request:
        return self.requests[-1]


def answer(body, status=200):
    return httpx.Response(status, json=body)


def refused_by(response):
    """What the gateway raises for this answer to `reorganize` (any call would do: they share the handling of answers)."""
    service = Service({("POST", "/reorganizations"): response})
    with pytest.raises(VerdictError) as raised:
        service.gateway().reorganize(True)
    return raised.value


def test_the_plan_asks_for_the_tracks_named_and_the_children_with_the_token():
    service = Service({("GET", "/plan"): answer(PLAN)})
    assert service.gateway().plan(["rncp", "common-core"], False) == PLAN
    assert (service.last.method, service.last.url.path) == ("GET", "/plan")
    assert service.last.url.params.multi_items() == [("track", "rncp"), ("track", "common-core"), ("children", "false")]
    assert service.last.headers["x-scraper-token"] == TOKEN
    service.gateway().plan([], True)
    assert service.last.url.params.multi_items() == [("children", "true")]


def test_a_download_is_started_with_a_json_selection_that_has_every_field():
    service = Service({("POST", "/downloads"): answer({"id": "d1", "state": "running"}, 202)})
    selection = {"tracks": ["rncp"], "projects": ["libft", "Django - 0"], "artifacts": False, "children": True, "force": True}
    assert service.gateway().start_download(**selection) == {"id": "d1", "state": "running"}
    assert (service.last.method, service.last.url.path, json.loads(service.last.content)) == ("POST", "/downloads", selection)
    assert service.last.headers["content-type"] == "application/json" and service.last.headers["x-scraper-token"] == TOKEN
    service.gateway().start_download(tracks=None, projects=None, artifacts=True, children=True, force=False)
    assert json.loads(service.last.content) == {"tracks": None, "projects": None, "artifacts": True, "children": True, "force": False}


def test_the_current_download_is_asked_from_a_line_on_and_cancelled_at_the_same_address():
    current = {"state": "running", "id": "d1", "lines": ["a"], "next": 9, "summary": None}
    service = Service({("GET", "/downloads/current"): answer(current), ("DELETE", "/downloads/current"): answer({"state": "running"})})
    gateway = service.gateway()
    assert gateway.current_download(8) == current
    assert (service.last.method, str(service.last.url)) == ("GET", f"{URL}/downloads/current?since=8")
    assert gateway.current_download() == current and service.last.url.params["since"] == "0"
    assert gateway.cancel_download() == {"state": "running"}
    assert (service.last.method, str(service.last.url), service.last.content) == ("DELETE", f"{URL}/downloads/current", b"")
    assert all(r.headers["x-scraper-token"] == TOKEN for r in service.requests)


def test_a_reorganization_is_a_dry_run_or_not():
    done = {"dry_run": False, "done": 1, "moves": [{"from": "samples/a.pdf", "to": "samples/s/a.pdf"}]}
    service = Service({("POST", "/reorganizations"): answer(done)})
    assert service.gateway().reorganize(False) == done
    assert (service.last.method, service.last.url.path, json.loads(service.last.content)) == ("POST", "/reorganizations", {"dry_run": False})
    service.gateway().reorganize(True)
    assert json.loads(service.last.content) == {"dry_run": True}


def test_every_call_goes_to_its_own_address_with_the_token_and_the_health_check_is_never_used():
    service = Service({(method, path): answer({"ok": True}) for _name, _args, _kw, (method, path) in EVERY_CALL})
    gateway = service.gateway()
    for name, args, kwargs, _route in EVERY_CALL:
        assert getattr(gateway, name)(*args, **kwargs) == {"ok": True}
    assert [(r.method, r.url.path) for r in service.requests] == [route for *_rest, route in EVERY_CALL]
    assert all(r.headers["x-scraper-token"] == TOKEN for r in service.requests) and "/health" not in {r.url.path for r in service.requests}


def test_each_call_has_a_time_to_answer_that_fits_what_the_service_does_for_it():
    service = Service({(method, path): answer({}) for _name, _args, _kw, (method, path) in EVERY_CALL})
    gateway = service.gateway()
    for name, args, kwargs, _route in EVERY_CALL:
        getattr(gateway, name)(*args, **kwargs)
    reads = {r.method + r.url.path: r.extensions["timeout"] for r in service.requests}
    assert {key: t["read"] for key, t in reads.items()} == {"GET/plan": 45, "POST/downloads": 45, "GET/downloads/current": 10,
                                                           "DELETE/downloads/current": 10, "POST/reorganizations": 60}
    assert all(t["connect"] == t["read"] for t in reads.values())              # (one bound for every phase: nothing waits for ever)


@pytest.mark.parametrize("failure", [httpx.ConnectError("refused"), httpx.ConnectTimeout("slow"), httpx.ReadTimeout("slow"),
                                     httpx.WriteTimeout("slow"), httpx.PoolTimeout("busy"), httpx.ReadError("reset"),
                                     httpx.RemoteProtocolError("garbage"), httpx.UnsupportedProtocol("no scheme"),
                                     httpx.DecodingError("bad gzip")])
@pytest.mark.parametrize("name, args, kwargs, route", EVERY_CALL)
def test_a_service_that_cannot_be_reached_is_unavailable_with_a_message_for_every_call(failure, name, args, kwargs, route):
    service = Service({route: failure})
    with pytest.raises(Unavailable) as raised:
        getattr(service.gateway(), name)(*args, **kwargs)
    assert raised.value.message == UNREACHABLE and raised.value.status == 503 and raised.value.__cause__ is failure
    assert TOKEN not in raised.value.message and URL not in raised.value.message


def test_an_address_that_is_no_address_is_an_unavailable_service_not_a_crash():
    with pytest.raises(Unavailable, match="could not reach the subject downloader"):
        ScraperGateway("http://scraper:port", TOKEN).plan([], True)
    with pytest.raises(Unavailable, match="could not reach the subject downloader"):
        ScraperGateway("scraper:8003", TOKEN).plan([], True)


def test_a_bad_request_is_the_apps_bad_request_with_the_words_of_the_service():
    detail = "the saved session is not usable: run `make samples-login` on your computer (the session expired)"
    error = refused_by(answer({"detail": detail}, 400))
    assert type(error) is VerdictError and error.status == 400 and error.message == detail


def test_a_download_that_is_already_running_is_a_conflict_with_the_words_of_the_service():
    service = Service({("POST", "/downloads"): answer({"detail": "a download is already running"}, 409)})
    with pytest.raises(Conflict) as raised:
        service.gateway().start_download(tracks=None, projects=None, artifacts=True, children=True, force=False)
    assert raised.value.status == 409 and raised.value.message == "a download is already running"


@pytest.mark.parametrize("status", [400, 409])
@pytest.mark.parametrize("body", [{}, {"detail": ""}, {"detail": None}, {"detail": 7}, {"detail": [{"loc": ["body"], "msg": "x"}]}, ["detail"]])
def test_a_refusal_without_a_readable_detail_still_says_what_status_it_was(status, body):
    error = refused_by(answer(body, status))
    assert error.status == status and error.message == f"the subject downloader answered HTTP {status}"


@pytest.mark.parametrize("response", [httpx.Response(400, text="<html>Bad request</html>"), httpx.Response(409, content=b"\xff\xfe"),
                                      httpx.Response(400, content=b"")])
def test_a_refusal_that_is_not_json_is_still_a_refusal(response):
    error = refused_by(response)
    assert error.status == response.status_code and error.message == f"the subject downloader answered HTTP {response.status_code}"


@pytest.mark.parametrize("status", [401, 403])
def test_a_token_the_service_does_not_accept_is_told_as_a_service_that_is_not_usable_without_the_token_in_it(status):
    error = refused_by(answer({"detail": f"invalid token {TOKEN}"}, status))
    assert isinstance(error, Unavailable) and error.status == 503 and error.message == TOKEN_REFUSED and TOKEN not in error.message


@pytest.mark.parametrize("status", [502, 503, 504])
def test_a_service_that_is_down_behind_its_proxy_is_unavailable(status):
    error = refused_by(answer({"detail": "upstream is down"}, status))
    assert isinstance(error, Unavailable) and error.message == "upstream is down"


@pytest.mark.parametrize("status", [404, 405, 413, 422, 429, 500, 501, 507])
def test_any_other_refusal_is_a_failure_of_the_downloader(status):
    error = refused_by(answer({"detail": "it broke"}, status))
    assert isinstance(error, Failed) and error.status == 500 and error.message == "it broke"
    assert refused_by(httpx.Response(status, text="Internal Server Error")).message == f"the subject downloader answered HTTP {status}"


def test_a_redirect_is_not_followed_with_the_token_and_is_a_failure():
    service = Service({("POST", "/reorganizations"): httpx.Response(307, headers={"location": "http://elsewhere.invalid/x"}),
                       ("GET", "/x"): answer({"stolen": True})})
    with pytest.raises(Failed):
        service.gateway().reorganize(True)
    assert [r.url.host for r in service.requests] == ["scraper"]


@pytest.mark.parametrize("response", [httpx.Response(200, text="<html>hello</html>"), httpx.Response(200, content=b""), httpx.Response(200, content=b"\xff"),
                                      answer([1, 2]), answer(None), answer("ok"), answer(7), httpx.Response(202, text="accepted")])
@pytest.mark.parametrize("name, args, kwargs, route", EVERY_CALL)
def test_an_answer_that_is_no_json_object_is_a_failure_not_a_crash(response, name, args, kwargs, route):
    service = Service({route: response})
    with pytest.raises(Failed) as raised:
        getattr(service.gateway(), name)(*args, **kwargs)
    assert raised.value.status == 500 and raised.value.message == "the subject downloader answered something this app cannot read"


def test_the_address_may_end_with_a_slash_and_no_proxy_variable_is_honoured(monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.invalid:3128")
    monkeypatch.setenv("ALL_PROXY", "http://proxy.invalid:3128")
    service = Service({("GET", "/plan"): answer(PLAN)})
    gateway = ScraperGateway(URL + "/", TOKEN, transport=httpx.MockTransport(service))
    gateway.plan([], True)
    assert str(service.last.url) == f"{URL}/plan?children=true" and gateway.url == URL
    seen = {}
    real = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kw: seen.update(kw) or real(transport=httpx.MockTransport(service)))
    ScraperGateway(URL, TOKEN).plan([], True)
    assert seen["trust_env"] is False                                              # an internal service: the proxies are never used
    assert "follow_redirects" not in seen or seen["follow_redirects"] is False


def test_without_a_downloader_every_call_says_it_is_not_configured():
    scraper = NullScraper()
    assert scraper.configured is False and NOT_CONFIGURED == "the subject downloader is not configured"
    for name, args, kwargs, _route in EVERY_CALL:
        with pytest.raises(Unavailable) as raised:
            getattr(scraper, name)(*args, **kwargs)
        assert raised.value.message == NOT_CONFIGURED and raised.value.status == 503


def test_the_gateway_is_a_configured_downloader_with_the_same_calls_as_the_null_one():
    gateway = ScraperGateway(URL, TOKEN)
    assert gateway.configured is True and (gateway.url, gateway.token) == (URL, TOKEN)
    assert all(callable(getattr(NullScraper, name)) and getattr(ScraperGateway, name) is getattr(NullScraper, name) for name, *_rest in EVERY_CALL)
