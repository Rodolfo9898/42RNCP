"""The documented settings must be the settings the app really reads, and the example must never hold a secret."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest
from tests.paths import DOCKER, ROOT, SCRIPTS, SRC

EXAMPLE = (ROOT / ".env.example").read_text()
COMPOSE = (ROOT / "docker-compose.yml").read_text()
MAKEFILE = (ROOT / "Makefile").read_text()
SCRAPER_CONFIG = (SRC / "scraper" / "config.py").read_text()
SETUP = SCRIPTS / "env" / "env-setup.sh"


def documented():
    """Every NAME= in the example, whether or not it is commented out."""
    return set(re.findall(r"^#?\s*([A-Z][A-Z_]+)=", EXAMPLE, re.M))


def test_every_setting_compose_reads_is_documented():
    read = set(re.findall(r"\$\{([A-Z_]+)", COMPOSE))
    assert read - documented() == set(), f"settings the app reads but .env.example does not mention: {sorted(read - documented())}"


def test_nothing_documented_is_a_setting_nobody_reads():
    read = (set(re.findall(r"\$\{([A-Z_]+)", COMPOSE)) | set(re.findall(r"grep -m1 '\^([A-Z_]+)=", MAKEFILE))
            | set(re.findall(r'env\("([A-Z_]+)"', SCRAPER_CONFIG)))               # the subject scraper reads INTRA_LOGIN and INTRA_PASSWORD
    assert documented() - read == set(), f"stale entries: {sorted(documented() - read)}"


def test_the_example_activates_only_the_one_line_that_is_needed_for_the_ai_review():
    active = re.findall(r"^([A-Z][A-Z_]+)=(.*?)(?:\s+#.*)?$", EXAMPLE, re.M)
    assert active == [("LLM_PROVIDER", "claude-cli")]


def test_the_example_holds_no_secret_or_real_looking_value():
    for name, value in re.findall(r"^#?\s*([A-Z][A-Z_]+)=(\S*)", EXAMPLE, re.M):
        if name in {"TERMINAL_TOKEN", "EDITOR_TOKEN", "LLM_API_KEY", "ANTHROPIC_API_KEY", "INTRA_LOGIN", "INTRA_PASSWORD"}:
            assert value == "", f"{name} must be empty in the example"
    assert not re.search(r"sk-[A-Za-z0-9_-]{8,}|[0-9a-f]{32,}", EXAMPLE)


def test_the_intra_login_is_never_handed_to_a_container():
    assert "INTRA_" not in COMPOSE and "INTRA_" not in (DOCKER / "terminal" / "compose.ssh.yml").read_text()
    assert re.search(r"^# INTRA_LOGIN=", EXAMPLE, re.M) and re.search(r"^# INTRA_PASSWORD=", EXAMPLE, re.M)


def test_the_token_is_documented_as_automatic_and_not_activated():
    assert re.search(r"^# TERMINAL_TOKEN=$", EXAMPLE, re.M) and not re.search(r"^TERMINAL_TOKEN=", EXAMPLE, re.M)
    assert "make` fills it in" in EXAMPLE


def test_the_example_is_committed_while_the_real_file_is_not():
    if not (ROOT / ".git").exists() or shutil.which("git") is None:
        pytest.skip("not a git checkout")
    ignored = lambda name: subprocess.run(["git", "check-ignore", "-q", name], cwd=ROOT).returncode == 0
    assert ignored(".env") and not ignored(".env.example")


def setup_env(folder: Path, *, example: str = EXAMPLE, env: str | None = None) -> str:
    """Run scripts/env/env-setup.sh in `folder` the way `make token` does; the resulting .env."""
    (folder / "scripts" / "env").mkdir(parents=True, exist_ok=True)
    (folder / "scripts" / "env" / "env-setup.sh").write_text(SETUP.read_text())
    (folder / ".env.example").write_text(example)
    if env is not None:
        (folder / ".env").write_text(env)
    run = subprocess.run(["sh", "scripts/env/env-setup.sh", ".env", ".env.example"], cwd=folder, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    return (folder / ".env").read_text()


needs_tools = pytest.mark.skipif(shutil.which("openssl") is None or shutil.which("sh") is None, reason="needs sh and openssl")


@needs_tools
def test_a_missing_env_is_a_copy_of_the_example_with_only_the_tokens_filled_in(tmp_path):
    text = setup_env(tmp_path)
    assert (tmp_path / ".env").stat().st_mode & 0o077 == 0
    lines, original = text.splitlines(), EXAMPLE.splitlines()
    assert len(lines) == len(original)                                             # same structure: no line added, moved or dropped
    changed = [(a, b) for a, b in zip(original, lines) if a != b]
    assert [a for a, _ in changed] == ["# TERMINAL_TOKEN=", "# EDITOR_TOKEN="]
    assert re.fullmatch(r"TERMINAL_TOKEN=[0-9a-f]{48}", changed[0][1]) and re.fullmatch(r"EDITOR_TOKEN=[0-9a-f]{48}", changed[1][1])
    assert changed[0][1].split("=")[1] != changed[1][1].split("=")[1]
    assert "LLM_PROVIDER=claude-cli" in lines                                      # the example's one active line comes along


@needs_tools
def test_running_it_again_changes_nothing_and_a_value_that_is_there_is_kept(tmp_path):
    first = setup_env(tmp_path)
    assert setup_env(tmp_path) == first
    mine = EXAMPLE.replace("# TERMINAL_TOKEN=", "TERMINAL_TOKEN=my-own-value")
    text = setup_env(tmp_path / "other" if (tmp_path / "other").mkdir() is None else tmp_path, env=mine)
    assert "TERMINAL_TOKEN=my-own-value" in text and len(re.findall(r"^TERMINAL_TOKEN=", text, re.M)) == 1
    assert re.search(r"^EDITOR_TOKEN=[0-9a-f]{48}$", text, re.M)                   # only the missing one is added


@needs_tools
def test_an_env_that_was_not_made_from_the_example_gets_the_tokens_at_the_end(tmp_path):
    text = setup_env(tmp_path, env="LLM_PROVIDER=claude-cli\nPROJECTS_DIR=/x\n")
    assert text.startswith("LLM_PROVIDER=claude-cli\nPROJECTS_DIR=/x\n")
    assert re.search(r"\nTERMINAL_TOKEN=[0-9a-f]{48}\nEDITOR_TOKEN=[0-9a-f]{48}\n$", text)


@needs_tools
def test_without_an_example_the_env_is_still_made(tmp_path):
    (tmp_path / "scripts" / "env").mkdir(parents=True)
    (tmp_path / "scripts" / "env" / "env-setup.sh").write_text(SETUP.read_text())
    assert subprocess.run(["sh", "scripts/env/env-setup.sh", ".env", "missing.example"], cwd=tmp_path).returncode == 0
    assert len(re.findall(r"^(TERMINAL|EDITOR)_TOKEN=[0-9a-f]{48}$", (tmp_path / ".env").read_text(), re.M)) == 2


@pytest.mark.skipif(shutil.which("make") is None or shutil.which("docker") is None, reason="needs make and docker")
def test_copying_the_example_and_running_make_gives_a_file_compose_accepts(tmp_path, monkeypatch):
    for name in ("TERMINAL_TOKEN", "LLM_PROVIDER"):
        monkeypatch.delenv(name, raising=False)
    (tmp_path / "Makefile").write_text(MAKEFILE)
    (tmp_path / "scripts" / "env").mkdir(parents=True)
    (tmp_path / "scripts" / "env" / "env-setup.sh").write_text(SETUP.read_text())
    (tmp_path / ".env.example").write_text(EXAMPLE)                                 # no .env at all: make copies the example
    for _ in range(2):                                                             # idempotent: the second run adds nothing
        subprocess.run(["make", "token"], cwd=tmp_path, capture_output=True, check=True)
    text = (tmp_path / ".env").read_text()
    assert len(re.findall(r"^TERMINAL_TOKEN=[0-9a-f]{48}$", text, re.M)) == 1 and len(text.splitlines()) == len(EXAMPLE.splitlines())
    assert (tmp_path / ".env").stat().st_mode & 0o077 == 0
    ok = subprocess.run(["docker", "compose", "--env-file", str(tmp_path / ".env"), "config", "-q"], cwd=ROOT, capture_output=True, text=True)
    assert ok.returncode == 0, ok.stderr
