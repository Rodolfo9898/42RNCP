"""src/terminal/editor/extensions.py: the list of the editor's extensions (config/extensions.txt) and what is installed."""

import json

from terminal.editor.extensions import HEADER, ExtensionList, InstalledExtensions
from tests.terminal.fakes import manifest


def test_the_list_keeps_ids_only_in_order_once_and_in_lower_case(tmp_path):
    path = tmp_path / "extensions.txt"
    path.write_text("# my extensions\nmhutchie.git-graph\n\n  Oderwat.Indent-Rainbow  # the indents\nnot an id\nmhutchie.git-graph\n../evil\n")
    assert ExtensionList(path).read() == ["mhutchie.git-graph", "oderwat.indent-rainbow"]
    assert ExtensionList(tmp_path / "missing.txt").read() == []


def test_writing_the_list_keeps_its_comments_and_sorts_the_ids(tmp_path):
    path = tmp_path / "extensions.txt"
    path.write_text("# mine\n# two lines\nzz.last\n")
    ExtensionList(path).write(["b.two", "a.one", "a.one"])
    assert path.read_text() == "# mine\n# two lines\na.one\nb.two\n"
    fresh = tmp_path / "fresh.txt"
    ExtensionList(fresh).write(["a.one"])
    assert fresh.read_text() == HEADER + "a.one\n"


def test_writing_the_list_is_done_in_place_because_it_is_a_bind_mount(tmp_path):
    path = tmp_path / "extensions.txt"
    path.write_text("# mine\n")
    before = path.stat().st_ino
    ExtensionList(path).write(["a.one"])
    assert path.stat().st_ino == before, "a rename into a bind-mounted file would replace it by a file the host never sees"


def test_installed_reads_the_manifest_and_survives_a_broken_one(tmp_path):
    manifest(tmp_path, "mhutchie.git-graph", "Oderwat.indent-rainbow")
    assert InstalledExtensions(tmp_path).ids() == {"mhutchie.git-graph", "oderwat.indent-rainbow"}
    (tmp_path / "extensions.json").write_text("{not json")
    assert InstalledExtensions(tmp_path).ids() == set()
    (tmp_path / "extensions.json").write_text(json.dumps([{"identifier": {"id": "../evil"}}, "text", {"identifier": None}, {"identifier": {"id": 5}}]))
    assert InstalledExtensions(tmp_path).ids() == set()
    assert InstalledExtensions(tmp_path / "nothing").ids() == set()


def test_an_extension_installed_in_the_editor_is_added_and_one_uninstalled_is_taken_off(tmp_path):
    extensions = ExtensionList(tmp_path / "extensions.txt")
    extensions.write(["mhutchie.git-graph", "never.installed"])
    assert extensions.sync({"mhutchie.git-graph"}, {"mhutchie.git-graph", "new.one"})
    assert extensions.read() == ["mhutchie.git-graph", "never.installed", "new.one"]
    assert extensions.sync({"mhutchie.git-graph", "new.one"}, {"new.one"})
    assert extensions.read() == ["never.installed", "new.one"], "an id whose install failed stays for the next start"
    assert not extensions.sync({"new.one"}, {"new.one"}), "nothing changed: the file is not written"
