import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "models.py"


def run(stdin: str):
    return subprocess.run([sys.executable, "-I", str(SCRIPT)], input=stdin, capture_output=True, text=True)


def test_lists_ids_with_the_hints_the_server_provides():
    out = run(json.dumps({"data": [{"id": "b-model", "free": True, "context_length": 32768, "noise": 1}, {"id": "a-model"}]}))
    assert out.returncode == 0
    assert out.stdout.splitlines() == ["a-model", "b-model   free=True, context_length=32768"]


def test_accepts_a_bare_list_of_ids():
    assert run(json.dumps(["x", "y"])).stdout.split() == ["x", "y"]


def test_errors_are_explained_on_stderr():
    for body, text in ((json.dumps({"error": {"message": "invalid key"}}), "invalid key"), ("<html>nope</html>", "did not answer with JSON"),
                       (json.dumps({"data": []}), "No models found")):
        out = run(body)
        assert out.returncode == 1 and text in out.stderr and out.stdout == ""
