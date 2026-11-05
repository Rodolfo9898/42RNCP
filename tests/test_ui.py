"""The real page (index.html and every script) in jsdom, with a fake server: boot, activity bar, moving views between the side bars and the panel,
editors and their groups, find, quick open, keys and chords, terminals and their panes, Source Control and its diff, search, settings, menus.

There is no layout engine in jsdom: these check what the page builds, stores and asks the server for, not how it looks. They need node and
jsdom (`npm install` in tests/js, or JSDOM_PATH pointing at an installed one) and are skipped without them. All scenarios run in one node
process (tests/js/ui_scenarios.js --all); each is reported here under its own name.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

RUNNER = Path(__file__).resolve().parent / "js" / "ui_scenarios.js"


def node(*args, timeout=900):
    return subprocess.run(["node", str(RUNNER), *args], capture_output=True, text=True, timeout=timeout)


HAVE_NODE = shutil.which("node") is not None
SCENARIOS = node("--list", timeout=60).stdout.split() if HAVE_NODE else []
pytestmark = pytest.mark.skipif(not HAVE_NODE or node("--check", timeout=60).returncode != 0, reason="needs node and jsdom (npm install in tests/js, or set JSDOM_PATH)")


@pytest.fixture(scope="module")
def results():
    done = node("--all", timeout=1500)
    assert done.returncode == 0, done.stderr[-2000:]
    return {r["name"]: r for r in json.loads(done.stdout.strip().splitlines()[-1])}


def test_there_are_scenarios():
    assert len(SCENARIOS) >= 60


@pytest.mark.parametrize("name", SCENARIOS)
def test_scenario(results, name):
    result = results[name]
    assert result["ok"], result.get("error")
