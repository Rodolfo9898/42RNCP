"""Progress.md reaches the web app as a mounted file, and the editor has a command and a button for it."""

import json
import re

from tests.paths import EXTENSION, ROOT


def test_only_the_web_app_sees_progress_md_and_make_creates_it_first():
    compose = (ROOT / "docker-compose.yml").read_text()
    services = re.split(r"\n  (?=[a-z]+:\n)", compose)
    seeing = [s.split(":", 1)[0].strip() for s in services if "Progress.md" in s and not s.startswith("#")]
    assert seeing == ["web"] or [x for x in seeing if x.startswith("web")]
    assert "PROGRESS_FILE: /progress/Progress.md" in compose and "- ./Progress.md:/progress/Progress.md" in compose
    makefile = (ROOT / "Makefile").read_text()
    assert re.search(r"^build:.*\bprogress\b", makefile, re.M) and "[ -e Progress.md ] || : > Progress.md" in makefile


def test_the_editor_has_a_command_and_a_button_for_it():
    manifest = json.loads((EXTENSION / "package.json").read_text())
    assert "verdict.updateProgress" in {c["command"] for c in manifest["contributes"]["commands"]}
    assert any(m["command"] == "verdict.updateProgress" for m in manifest["contributes"]["menus"]["view/title"])
