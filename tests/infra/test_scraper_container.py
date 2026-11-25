"""The scraper container is the only thing that talks to the 42 intra for the editor, and it never holds a login: the session is made
on the person's computer and mounted read-only into this container alone. These guards keep it that way."""

import re

from tests.infra.test_images import COMPOSE, DOCKERFILES, final_stage, networks_of, services, without_comments
from tests.paths import DOCKER, ROOT, SRC

BLOCK = without_comments(services()["scraper"])
MAKEFILE = (ROOT / "Makefile").read_text()


def mounts(block):
    return re.findall(r"^\s+- (\S+:\S+)", block.split("volumes:", 1)[1].split("networks:", 1)[0], re.M)


def test_the_scraper_writes_the_subject_folders_and_only_reads_the_session():
    assert mounts(BLOCK) == ["./samples:/samples", "./artifacts:/artifacts", "./.session:/session:ro"]


def test_the_session_is_mounted_nowhere_else():
    holders = [name for name, block in services().items() if ".session" in without_comments(block)]
    assert holders == ["scraper"]                                      # not the web app (ssh-agent, projects), not the terminal (claude on untrusted code)


def test_the_scraper_holds_no_secret_but_its_own_token():
    for secret in ("INTRA_", "ANTHROPIC_API_KEY", "LLM_", "SSH_AUTH_SOCK", "TERMINAL_TOKEN", "EDITOR_TOKEN", "PROJECTS_DIR", "PROGRESS_FILE"):
        assert secret not in BLOCK, secret
    assert "SCRAPER_TOKEN: ${SCRAPER_TOKEN:?" in BLOCK                    # it never starts without its token
    assert "SCRAPER_TOKEN" not in without_comments(services()["terminal"])


def test_the_scraper_is_locked_down_and_unreachable_from_outside():
    assert "read_only: true" in BLOCK and "cap_drop: [ALL]" in BLOCK and "no-new-privileges:true" in BLOCK
    assert "ports:" not in BLOCK and "privileged" not in BLOCK and "cap_add" not in BLOCK and "user: root" not in BLOCK
    assert "mem_limit" in BLOCK and "pids_limit" in BLOCK and "cpus" in BLOCK


def test_only_the_web_app_shares_a_network_with_the_scraper_and_only_the_scraper_has_the_intra_net():
    assert networks_of(BLOCK) == {"scraper-net", "intra-net"}                # not `default`: the terminal cannot even reach it
    nets = COMPOSE.split("\nnetworks:")[1].split("\nvolumes:")[0]
    assert re.search(r"scraper-net:[^\n]*\n\s+internal: true", nets)
    assert re.search(r"intra-net:\s*\{\}", nets)                               # the one network with internet access it has
    on = lambda net: sorted(name for name, block in services().items() if net in networks_of(block))
    assert on("scraper-net") == ["scraper", "web"] and on("intra-net") == ["scraper"]


def test_the_web_app_finds_the_scraper_by_name_with_the_shared_token():
    web = without_comments(services()["web"])
    assert "SCRAPER_URL: http://scraper:8003" in web and "SCRAPER_TOKEN: ${SCRAPER_TOKEN:?" in web
    assert "INTRA_" not in web


def test_the_image_has_no_browser_no_credentials_and_runs_as_the_unprivileged_user():
    text = (DOCKER / "scraper" / "Dockerfile").read_text()
    code = without_comments(text)
    assert "playwright" not in code.lower() and "chrom" not in code.lower() and "INTRA_" not in code
    assert "useradd --create-home --uid 1000 scraper" in text and "\nUSER scraper" in final_stage(text)
    assert final_stage(text).rstrip().splitlines()[-1] == 'CMD ["uvicorn", "scraper_server:app", "--host", "0.0.0.0", "--port", "8003"]'
    assert "pip install --no-cache-dir -r requirements.txt" in text and (SRC / "scraper" / "requirements-service.txt").is_file()
    assert "playwright" not in without_comments((SRC / "scraper" / "requirements-service.txt").read_text()).lower()   # the login stays on the computer
    assert "scraper" in DOCKERFILES


def test_the_login_runs_on_the_computer_and_the_folders_exist_before_compose_starts():
    login = MAKEFILE.split("\nsamples-login:", 1)[1].split("\n\n", 1)[0]
    assert "src/subject_scraper.py --login" in login and "$(SCRAPE_VENV)" in login          # the host's venv (Playwright), never a container
    assert re.search(r"^build: .*\bscraper-dirs\b", MAKEFILE, re.M)
    assert "mkdir -p samples artifacts .session && chmod 700 .session" in MAKEFILE
    assert re.search(r"^\.session/$", (ROOT / ".gitignore").read_text(), re.M)              # cookies are never committed
