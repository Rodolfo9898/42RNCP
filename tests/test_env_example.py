"""The documented settings must be the settings the app really reads, and the example must never hold a secret."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = (ROOT / ".env.example").read_text()
COMPOSE = (ROOT / "docker-compose.yml").read_text()
MAKEFILE = (ROOT / "Makefile").read_text()


def documented():
    """Every NAME= in the example, whether or not it is commented out."""
    return set(re.findall(r"^#?\s*([A-Z][A-Z_]+)=", EXAMPLE, re.M))


def test_every_setting_compose_reads_is_documented():
    read = set(re.findall(r"\$\{([A-Z_]+)", COMPOSE))
    assert read - documented() == set(), f"settings the app reads but .env.example does not mention: {sorted(read - documented())}"


def test_nothing_documented_is_a_setting_nobody_reads():
    read = set(re.findall(r"\$\{([A-Z_]+)", COMPOSE)) | set(re.findall(r"grep -m1 '\^([A-Z_]+)=", MAKEFILE))
    assert documented() - read == set(), f"stale entries: {sorted(documented() - read)}"


def test_the_example_activates_only_the_one_line_that_is_needed_for_the_ai_review():
    active = re.findall(r"^([A-Z][A-Z_]+)=(.*?)(?:\s+#.*)?$", EXAMPLE, re.M)
    assert active == [("LLM_PROVIDER", "claude-cli")]


def test_the_example_holds_no_secret_or_real_looking_value():
    for name, value in re.findall(r"^#?\s*([A-Z][A-Z_]+)=(\S*)", EXAMPLE, re.M):
        if name in {"TERMINAL_TOKEN", "LLM_API_KEY", "ANTHROPIC_API_KEY"}:
            assert value == "", f"{name} must be empty in the example"
    assert not re.search(r"sk-[A-Za-z0-9_-]{8,}|[0-9a-f]{32,}", EXAMPLE)


def test_the_token_is_documented_as_automatic_and_not_activated():
    assert re.search(r"^# TERMINAL_TOKEN=$", EXAMPLE, re.M) and not re.search(r"^TERMINAL_TOKEN=", EXAMPLE, re.M)
    assert "make` generates it" in EXAMPLE


def test_the_example_is_committed_while_the_real_file_is_not():
    if not (ROOT / ".git").exists() or shutil.which("git") is None:
        pytest.skip("not a git checkout")
    ignored = lambda name: subprocess.run(["git", "check-ignore", "-q", name], cwd=ROOT).returncode == 0
    assert ignored(".env") and not ignored(".env.example")


@pytest.mark.skipif(shutil.which("make") is None or shutil.which("docker") is None, reason="needs make and docker")
def test_copying_the_example_and_running_make_gives_a_file_compose_accepts(tmp_path, monkeypatch):
    for name in ("TERMINAL_TOKEN", "LLM_PROVIDER"):
        monkeypatch.delenv(name, raising=False)
    (tmp_path / "Makefile").write_text(MAKEFILE)
    (tmp_path / ".env").write_text(EXAMPLE)                                         # cp .env.example .env
    for _ in range(2):                                                             # idempotent: the second run adds nothing
        subprocess.run(["make", "token"], cwd=tmp_path, capture_output=True, check=True)
    text = (tmp_path / ".env").read_text()
    assert len(re.findall(r"^TERMINAL_TOKEN=[0-9a-f]{48}$", text, re.M)) == 1
    assert text.startswith(EXAMPLE.rstrip("\n")) and (tmp_path / ".env").stat().st_mode & 0o077 == 0
    ok = subprocess.run(["docker", "compose", "--env-file", str(tmp_path / ".env"), "config", "-q"], cwd=ROOT, capture_output=True, text=True)
    assert ok.returncode == 0, ok.stderr
