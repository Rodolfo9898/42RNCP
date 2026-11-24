"""The Norm: attached to a review while C code is detected (a subject that requires C, or a repository with C and no C++), taken away after."""

from tests.conftest import make_pdf
from tests.verdict.api.support import NORM, a_result, attach_repo, new_session
from verdict.library import norm as norm_module


def add(c, sid, *paths):
    return c.post(f"/api/sessions/{sid}/subjects", json={"paths": list(paths)})


def norm_names(view):
    return [s["name"] for s in view["subjects"] if s["kind"] == "norm"]


def test_norm_is_attached_when_the_subject_is_in_c(client):
    c, _ = client
    sid = new_session(c)
    state = add(c, sid, "common-core/push_swap.pdf").json()
    assert norm_names(state) == ["en.norm.pdf"]
    norm = next(s for s in state["subjects"] if s["kind"] == "norm")
    assert [r["text"] for r in norm["rules"] if r["kind"] == "manual"] == ["Your comments should be in English, and useful.",
                                                                          "Inclusion of unused headers is forbidden."]
    refused = c.delete(f"/api/sessions/{sid}/subjects/en.norm.pdf")                      # it follows the detection
    assert refused.status_code == 400 and "goes away by itself" in refused.json()["detail"]
    state = c.delete(f"/api/sessions/{sid}/subjects/push_swap.pdf").json()
    assert state["subjects"] == []                                                       # no C left: no Norm


def test_norm_is_attached_when_the_repo_has_c_code(client):
    c, harness = client
    sid = new_session(c)
    no_lang = make_pdf(["Chapter I\nMandatory part\nYou must write a configuration file.\n"])
    c.post("/api/library/rncp/subjects", files=[("files", ("conf.pdf", no_lang, "application/pdf"))])
    add(c, sid, "rncp/conf.pdf")
    repo = attach_repo(harness, sid, "c-repo")
    (repo / "main.c").write_text("int main(void){return 0;}\n")
    session = harness.store.get(sid)
    harness.norm.sync(session)
    assert NORM in session.subjects
    (repo / "main.cpp").write_text("int main(){}\n")                                   # C++ in the repo: not the Norm
    harness.norm.sync(session)
    assert NORM not in session.subjects
    (repo / "main.cpp").unlink()
    (repo / "mlx").mkdir()
    (repo / "main.c").rename(repo / "mlx" / "mlx.c")                                    # vendored C does not count
    harness.norm.sync(session)
    assert NORM not in session.subjects


def test_choosing_a_repository_with_c_code_attaches_the_norm_to_the_review(client):
    c, harness = client
    sid = new_session(c)
    repo = harness.settings.projects / "plain"
    repo.mkdir()
    (repo / "main.c").write_text("int main(void){return 0;}\n")
    view = c.put(f"/api/sessions/{sid}/repo", json={"kind": "existing", "path": "plain"}).json()
    assert norm_names(view) == [NORM]


def test_a_subject_that_says_cpp_keeps_the_norm_away_whatever_the_repository_has(client):
    c, harness = client
    sid = new_session(c)
    cpp = make_pdf(["Chapter I\nCommon Instructions\n- Your code must still compile with the flag -std=c++98.\n"])
    c.post("/api/library/rncp/subjects", files=[("files", ("cpp00.pdf", cpp, "application/pdf"))])
    view = add(c, sid, "rncp/cpp00.pdf").json()
    assert next(s for s in view["subjects"] if s["name"] == "cpp00.pdf")["lang"] == "cpp" and norm_names(view) == []


def test_the_norm_is_parsed_once_per_version_of_the_file(client, monkeypatch):
    _, harness = client
    reads = []
    real = norm_module.read_pages
    monkeypatch.setattr(norm_module, "read_pages", lambda data: reads.append(len(data)) or real(data))
    first = harness.norm.subject()
    assert first is not None and harness.norm.subject() is not first and len(reads) == 1      # (always a copy: the cache is never handed out)
    harness.norm.subject().rules.clear()
    assert harness.norm.subject().rules and len(reads) == 1
    harness.library.norm_path.write_bytes(make_pdf(["Chapter I\nThe Norm\n- Each function must be at most 10 lines long.\n"]))
    harness.norm.subject()
    assert len(reads) == 2


def test_without_a_norm_in_the_library_nothing_is_attached(client):
    c, harness = client
    harness.library.norm_path.unlink()
    assert harness.norm.subject() is None
    sid = new_session(c)
    assert norm_names(add(c, sid, "common-core/push_swap.pdf").json()) == []


def test_the_norm_is_refreshed_with_the_parser_like_any_subject(client):
    c, harness = client
    sid = new_session(c)
    add(c, sid, "common-core/push_swap.pdf")
    session = harness.store.get(sid)
    assert session.subjects[NORM].rules
    session.subjects[NORM].rules = []                                                       # a Norm stored by an older parser
    assert harness.subjects.refresh_rules(session) is True and session.subjects[NORM].rules
    assert harness.subjects.refresh_rules(session) is False


def test_attaching_or_removing_the_norm_forgets_the_results_that_did_not_have_it(client):
    c, harness = client
    sid = new_session(c)
    add(c, sid, "common-core/push_swap.pdf")
    session = harness.store.get(sid)
    del session.subjects[NORM]
    session.results = [a_result()]
    harness.norm.sync(session)
    assert NORM in session.subjects and session.results == []
