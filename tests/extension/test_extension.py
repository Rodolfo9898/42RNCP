"""The Verdict extension of the editor (src/extension, TypeScript): its node tests, and that its manifest, the editor's settings, the image
and the app agree on the names they share.

The node tests need node 20 or newer and the TypeScript tooling (`make test-extension` runs `npm install` in src/extension and
tests/extension, then this file); without them the node tests are skipped, with the reason, and the consistency checks still run."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from terminal.editor.extensions import ExtensionList
from shared import constants as shared
from tests.paths import DOCKER, EXTENSION, ROOT, SRC

EXT = EXTENSION
TESTS = ROOT / "tests" / "extension"
TSC = EXT / "node_modules" / "typescript" / "bin" / "tsc"            # the extension's own compiler (the tests are compiled with it too)
SETTINGS = DOCKER / "terminal" / "editor-settings.json"
MANIFEST = json.loads((EXT / "package.json").read_text())
SOURCES = {str(p.relative_to(EXT)): p.read_text() for p in sorted(EXT.rglob("*.ts"))
           if "node_modules" not in p.parts and p.relative_to(EXT).parts[0] != "out"}
BUILT_IN_LANGUAGES = {"properties", "c"}      # VS Code's own, which the settings point a file at


def node_20() -> str | None:
    node = shutil.which("node")
    if not node:
        return None
    version = subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip()
    return node if version.startswith("v") and int(version[1:].split(".")[0]) >= 20 else None


def tooling() -> str:
    """The node that runs the compiler and the tests, or a skip that says what is missing."""
    node = node_20()
    if not node:
        pytest.skip("node 20 or newer is not installed")
    if not TSC.is_file():
        pytest.skip("the TypeScript tooling is not installed: run `make test-extension` (npm install in src/extension and tests/extension)")
    return node


def compile_project(node: str, project: Path, *options: str) -> subprocess.CompletedProcess:
    return subprocess.run([node, str(TSC), "-p", str(project), *options], cwd=ROOT, capture_output=True, text=True, timeout=600)


def test_the_extension_compiles_and_passes_its_node_tests():
    """The tests are TypeScript: compiled (this also type-checks the extension), then run by node with a fake editor. They cover the merge
    of claude's report after every pass, the REST calls, the views, the pretty JSON view, the markdown buttons, the PDF viewer, Progress.md,
    and the colours of the ignore files when `make test-extension` has installed the TextMate engine."""
    node = tooling()
    built = compile_project(node, TESTS)
    assert built.returncode == 0, (built.stdout + built.stderr)[-4000:]
    files = sorted(str(p) for p in (TESTS / "out" / "tests" / "extension").rglob("*.test.js"))
    assert files, "the compiled tests are not where they are expected"
    done = subprocess.run([node, "--test", "--test-timeout=60000", *files], cwd=ROOT, capture_output=True, text=True, timeout=600)
    assert done.returncode == 0, (done.stdout + done.stderr)[-4000:]


def test_the_production_build_makes_the_file_the_manifest_points_at(tmp_path):
    node = tooling()
    tsconfig = json.loads((EXT / "tsconfig.json").read_text())["compilerOptions"]
    assert MANIFEST["main"] == f"./{tsconfig['outDir']}/extension.js"
    built = compile_project(node, EXT, "--outDir", str(tmp_path / "out"))
    assert built.returncode == 0, (built.stdout + built.stderr)[-4000:]
    entry = tmp_path / "out" / "extension.js"
    assert entry.is_file() and "exports.activate = activate" in entry.read_text()


def test_the_typescript_is_strict_and_builds_what_the_editors_node_runs():
    options = json.loads((EXT / "tsconfig.json").read_text())["compilerOptions"]
    assert options["strict"] is True
    assert options["target"] == "ES2022" and options["module"].lower() in ("commonjs", "node16")
    assert {"typescript", "@types/node", "@types/vscode"} <= set(MANIFEST["devDependencies"])
    assert "dependencies" not in MANIFEST, "the extension runs on node's own modules and the editor's API only"
    engine = tuple(int(n) for n in re.findall(r"\d+", MANIFEST["engines"]["vscode"])[:2])
    types = tuple(int(n) for n in re.findall(r"\d+", MANIFEST["devDependencies"]["@types/vscode"])[:2])
    assert types <= engine, "@types/vscode must not describe an API newer than the editor the manifest asks for"
    assert (EXT / ".gitignore").read_text().split() == ["node_modules/", "out/"], "the compiled output is not source"


def test_the_lock_files_point_at_the_public_registry_so_that_the_image_can_install_from_them():
    for lock in (EXT / "package-lock.json", TESTS / "package-lock.json"):
        resolved = re.findall(r'"resolved": "([^"]+)"', lock.read_text())
        assert resolved and all(url.startswith("https://registry.npmjs.org/") for url in resolved), lock


def registered() -> set[str]:
    return {m for source in SOURCES.values() for m in re.findall(r'(?:guarded|registerCommand)\(\s*"(verdict\.\w+)"', source)}


def test_every_command_of_the_manifest_is_registered_and_every_menu_uses_a_command_of_the_manifest():
    declared = {c["command"] for c in MANIFEST["contributes"]["commands"]}
    assert declared <= registered(), declared - registered()
    for place, entries in MANIFEST["contributes"]["menus"].items():
        for entry in entries:
            assert entry["command"] in declared, (place, entry)
    assert all(c["title"] and c["category"] == "Verdict" for c in MANIFEST["contributes"]["commands"])


def test_every_file_the_extension_loads_is_in_its_folder_and_the_image_builds_and_ships_it():
    for name, source in SOURCES.items():
        for target in re.findall(r'from "(\.[^"]+)"', source):
            assert ((EXT / name).parent / f"{target}.ts").resolve().is_file(), (name, target)
    dockerfile = (DOCKER / "terminal" / "Dockerfile").read_text()
    stage = dockerfile.split("AS extension\n", 1)[1].split("\nFROM ", 1)[0]
    assert re.search(r"^FROM node:\d+\.\d+\.\d+-slim AS extension$", dockerfile, re.M), "the build stage is pinned"
    assert "npm ci" in stage and "npm run build" in stage
    shipped = re.search(r"cp -r (.+) /dist", stage)
    assert shipped, "what VS Code needs is gathered in /dist"
    grammar, icon = MANIFEST["contributes"]["grammars"][0]["path"], MANIFEST["contributes"]["viewsContainers"]["activitybar"][0]["icon"]
    language = MANIFEST["contributes"]["languages"][0]["configuration"]
    needed = {"package.json", MANIFEST["main"].split("/")[1], grammar.split("/")[1], icon.split("/")[0], language.removeprefix("./")}
    assert needed == set(shipped.group(1).split()), "the image gets the manifest, the compiled code, the grammar, the language configuration and the icon: nothing else"
    assert "COPY --from=extension /dist /opt/openvscode-server/extensions/verdict" in dockerfile


def test_claudes_report_is_looked_for_where_the_app_and_the_terminal_put_it():
    assert re.search(rf'REPORTS_ROOT \|\| "{re.escape(shared.TERMINAL_REPORTS_ROOT)}"', SOURCES["settings/environment.ts"])
    assert 'REPORT_NAME = "claude-review.md"' in SOURCES["report/report-file.ts"]
    assert any('"claude-review.md"' in p.read_text() for p in (SRC / "terminal").rglob("*.py")), "the terminal service saves and reads that name"
    assert '/claude-review`, { method: "PUT"' in SOURCES["api/verdict-api.ts"]


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
    assert sum(source.count("vscode.markdown.preview.editor") for source in SOURCES.values()) == 1
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
    assert '.get("json.prettyOnOpen", true)' in SOURCES["settings/configuration.ts"]


def test_the_languages_have_their_servers_and_the_editor_is_set_up_for_them():
    """Colours come with VS Code for the usual languages; completion, hover and errors come from a language server. clangd is in the
    image (the extension would not download one for arm64) and the other servers are bundled in their extensions."""
    text = (ROOT / "config" / "extensions.txt").read_text()
    listed = ExtensionList(ROOT / "config" / "extensions.txt").read()
    assert len(listed) == len([line for line in text.splitlines() if line.strip() and not line.startswith("#")]), "an id was not read"
    assert {"llvm-vs-code-extensions.vscode-clangd", "ms-pyright.pyright", "mads-hartmann.bash-ide-vscode", "redhat.vscode-yaml",
            "tamasfe.even-better-toml"} <= set(listed)
    settings = json.loads(SETTINGS.read_text())
    assert settings["editor.semanticHighlighting.enabled"] is True, "functions, macros and parameters are coloured by the language server"
    assert settings["files.associations"]["*.h"] == "c", "a header is C here, not C++ (which is what VS Code assumes)"
    assert settings["clangd.path"] == "/usr/bin/clangd"
    assert "--background-index" in settings["clangd.arguments"]


def test_a_subject_and_the_page_a_check_cites_open_the_pdf_in_the_editor():
    manifest_commands = {c["command"] for c in MANIFEST["contributes"]["commands"]}
    assert "verdict.openSubject" in manifest_commands
    rows = SOURCES["views/subjects-tree.ts"] + SOURCES["views/check-nodes.ts"]
    assert rows.count('command: "verdict.openSubject"') == 2            # a subject of the Subjects view, and a "From x.pdf, page N"
    assert "arguments: [s.name]" in rows and "arguments: [source.pdf, source.page]" in rows
    root = SOURCES["extension.ts"]
    assert "viewers.pdf.register()" in root and "viewers.pdf.sync()" in root
    inline = [m for m in MANIFEST["contributes"]["menus"]["view/item/context"] if m["command"] == "verdict.openSubject"]
    assert inline and "viewItem == subject" in inline[0]["when"] and "viewItem == norm" in inline[0]["when"]


# ---------------------------------------------------------------- the REST API the extension calls

# The routes of the app that the extension uses (the "Public REST API" table): method, path with {} for every parameter.
PUBLIC_API = {
    ("GET", "/api/health"), ("GET", "/api/environment"), ("GET", "/api/library"), ("POST", "/api/library/{}/subjects"), ("POST", "/api/sessions"),
    ("GET", "/api/sessions/{}"), ("POST", "/api/sessions/{}/subjects"), ("DELETE", "/api/sessions/{}/subjects/{}"),
    ("GET", "/api/sessions/{}/subjects/{}/pages/{}.png"), ("GET", "/api/projects"), ("PUT", "/api/sessions/{}/repo"), ("POST", "/api/sessions/{}/runs"),
    ("PUT", "/api/sessions/{}/claude-review"), ("POST", "/api/sessions/{}/ai-review"), ("GET", "/api/sessions/{}/prompts/review"),
    ("GET", "/api/sessions/{}/prompts/fix"), ("PUT", "/api/sessions/{}/progress"), ("GET", "/api/sessions/{}/verdict.md"),
    ("GET", "/api/library/plan"), ("POST", "/api/library/downloads"), ("GET", "/api/library/downloads/current"),
    ("DELETE", "/api/library/downloads/current"), ("POST", "/api/library/reorganizations"),
}
CALL = re.compile(r'this\.client\.(?:json|bytes|text)(?:<[^(]*>)?\(\s*(?:([`"])(.*?)\1|(this\.of\(sid\)))(?:,\s*\{(.*?)\})?\)', re.S)


def routes_called() -> set[tuple[str, str]]:
    """(method, path) of every call the typed client of the extension makes, read from its source."""
    found = set()
    for _quote, template, _expression, options in CALL.findall(SOURCES["api/verdict-api.ts"]):
        route = re.sub(r"\$\{this\.of\(sid\)\}", "sessions/{}", template) if template else "sessions/{}"
        route = re.sub(r"\$\{deep \? \"\?deep=true\" : \"\"\}", "", route)
        route = re.sub(r"\$\{[^}]*\}", "{}", route).split("?")[0]            # (a query string is not part of the route)
        method = re.search(r'method: "(\w+)"', options or "")
        found.add((method.group(1) if method else "GET", "/api/" + route))
    return found


def test_the_extension_only_calls_routes_of_the_public_api():
    called = routes_called()
    assert len(called) >= 23, called
    assert called <= PUBLIC_API, called - PUBLIC_API
    assert PUBLIC_API - called == set(), "a route of the table the extension does not use: take it off the table"


def app_routes() -> set[tuple[str, str]]:
    import verdict_server

    paths = verdict_server.app.openapi()["paths"]
    return {(method.upper(), re.sub(r"\{[^}]*\}", "{}", route)) for route, methods in paths.items() for method in methods}


def test_the_app_serves_every_route_the_extension_calls():
    missing = routes_called() - app_routes()
    assert not missing, f"the extension calls routes the app does not have: {sorted(missing)}"
