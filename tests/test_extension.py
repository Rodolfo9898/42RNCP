"""The Verdict extension of the editor (terminal/vscode/verdict): its node tests, and that its manifest, the editor's settings and the
app agree on the names they share."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from verdict import editor, shared, terminal

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "terminal" / "vscode" / "verdict"
SETTINGS = ROOT / "terminal" / "vscode" / "settings.json"
MANIFEST = json.loads((EXT / "package.json").read_text())
SOURCES = {p.name: p.read_text() for p in EXT.glob("*.js")}
BUILT_IN_LANGUAGES = {"properties", "c"}      # VS Code's own, which the settings point a file at


def node_runs_tests() -> str | None:
    node = shutil.which("node")
    if not node:
        return None
    version = subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip()
    return node if version.startswith("v") and int(version[1:].split(".")[0]) >= 20 else None


@pytest.mark.skipif(not node_runs_tests(), reason="node 20 or newer is not installed")
def test_the_extension_passes_its_node_tests():
    """The merge of claude's report after every pass, the pretty JSON view, the markdown page/code buttons (a fake editor), and the colours
    of the ignore files when `make test-extension` has installed the TextMate engine."""
    files = sorted(str(p.relative_to(ROOT)) for p in (ROOT / "tests" / "js").glob("*.test.js"))
    done = subprocess.run([node_runs_tests(), "--test", "--test-timeout=60000", *files], cwd=ROOT, capture_output=True, text=True, timeout=600)
    assert done.returncode == 0, (done.stdout + done.stderr)[-4000:]


def registered() -> set[str]:
    return {m for source in SOURCES.values() for m in re.findall(r'(?:command|registerCommand)\(\s*"(verdict\.\w+)"', source)}


def test_every_command_of_the_manifest_is_registered_and_every_menu_uses_a_command_of_the_manifest():
    declared = {c["command"] for c in MANIFEST["contributes"]["commands"]}
    assert declared <= registered(), declared - registered()
    for place, entries in MANIFEST["contributes"]["menus"].items():
        for entry in entries:
            assert entry["command"] in declared, (place, entry)
    assert all(c["title"] and c["category"] == "Verdict" for c in MANIFEST["contributes"]["commands"])


def test_every_file_the_extension_loads_is_in_its_folder_and_so_in_the_image():
    for name, source in SOURCES.items():
        for target in re.findall(r'require\("\./([\w.-]+)"\)', source):
            assert (EXT / (target if target.endswith(".js") else target + ".js")).is_file(), (name, target)
    assert "COPY terminal/vscode/verdict /opt/openvscode-server/extensions/verdict" in (ROOT / "terminal" / "Dockerfile").read_text()


def test_claudes_report_is_looked_for_where_the_app_and_the_terminal_put_it():
    assert f'process.env.REPORTS_ROOT || "{shared.TERMINAL_REPORTS_ROOT}"' in SOURCES["extension.js"]
    assert f'REPORT_NAME = "{terminal.REVIEW_FILE}"' in SOURCES["report.js"]
    assert "claude-review/collect" in SOURCES["extension.js"]


def test_the_ignore_files_have_a_language_a_grammar_and_the_settings_use_them():
    languages = {lang["id"]: lang for lang in MANIFEST["contributes"]["languages"]}
    ignore = languages["verdict-ignore"]
    assert {".gitignore", ".dockerignore"} <= set(ignore["filenames"])
    assert (EXT / ignore["configuration"]).is_file()
    grammar = MANIFEST["contributes"]["grammars"][0]
    assert grammar["language"] == "verdict-ignore"
    syntax = json.loads((EXT / grammar["path"]).read_text())
    assert syntax["scopeName"] == grammar["scopeName"] == "source.verdict-ignore"
    settings = json.loads(SETTINGS.read_text())
    associations = settings["files.associations"]
    assert {".gitignore", ".dockerignore", ".gitmodules"} <= set(associations)
    assert set(associations.values()) <= set(languages) | BUILT_IN_LANGUAGES
    assert {name for name, lang in associations.items() if lang == "verdict-ignore"} <= set(ignore["filenames"])


def test_markdown_opens_as_a_page_and_both_buttons_are_in_the_title_bar():
    settings = json.loads(SETTINGS.read_text())
    assert settings["workbench.editorAssociations"] == {"*.md": "vscode.markdown.preview.editor"}
    assert SOURCES["viewers.js"].count("vscode.markdown.preview.editor") == 1
    titles = {e["command"]: e["when"] for e in MANIFEST["contributes"]["menus"]["editor/title"]}
    assert "activeCustomEditorId == 'vscode.markdown.preview.editor'" in titles["verdict.markdownCode"]
    assert "resourceExtname == .md" in titles["verdict.markdownPreview"]
    assert "resourceScheme == verdict-json" in titles["verdict.jsonRaw"] and "verdict.jsonMinified" in titles["verdict.jsonPretty"]


def test_the_markdown_page_is_dark_and_comes_from_the_listed_extension():
    """The GitHub styles follow the editor's theme by default ("auto"), which did not give a dark page: dark is set outright."""
    assert json.loads(SETTINGS.read_text())["markdown-preview-github-styles.colorTheme"] == "dark"
    listed = [line.strip() for line in (ROOT / "config" / "extensions.txt").read_text().splitlines() if not line.startswith("#")]
    assert "bierner.markdown-preview-github-styles" in listed


def test_the_json_view_has_a_setting_that_the_code_reads():
    props = MANIFEST["contributes"]["configuration"]["properties"]
    assert props["verdict.json.prettyOnOpen"]["default"] is True
    assert '.get("json.prettyOnOpen", true)' in SOURCES["viewers.js"]


def test_the_languages_have_their_servers_and_the_editor_is_set_up_for_them():
    """Colours come with VS Code for the usual languages; completion, hover and errors come from a language server. clangd is in the
    image (the extension would not download one for arm64) and the other servers are bundled in their extensions."""
    text = (ROOT / "config" / "extensions.txt").read_text()
    listed = editor.read_list(ROOT / "config" / "extensions.txt")
    assert len(listed) == len([line for line in text.splitlines() if line.strip() and not line.startswith("#")]), "an id was not read"
    assert {"llvm-vs-code-extensions.vscode-clangd", "ms-pyright.pyright", "mads-hartmann.bash-ide-vscode", "redhat.vscode-yaml",
            "tamasfe.even-better-toml"} <= set(listed)
    settings = json.loads(SETTINGS.read_text())
    assert settings["editor.semanticHighlighting.enabled"] is True, "functions, macros and parameters are coloured by the language server"
    assert settings["files.associations"]["*.h"] == "c", "a header is C here, not C++ (which is what VS Code assumes)"
    assert settings["clangd.path"] == "/usr/bin/clangd"
    assert "--background-index" in settings["clangd.arguments"]
