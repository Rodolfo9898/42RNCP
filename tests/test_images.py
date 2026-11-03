"""Guards for the container images and compose file. They cannot build an image, but they catch the mistakes that
break a build or weaken the isolation, which are easy to make and hard to notice."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SANDBOX = (ROOT / "sandbox/Dockerfile").read_text()
TERMINAL = (ROOT / "terminal/Dockerfile").read_text()
COMPOSE = (ROOT / "docker-compose.yml").read_text()
DOCKERFILES = {"sandbox": SANDBOX, "terminal": TERMINAL, "web": (ROOT / "Dockerfile").read_text()}


def services():
    """service name -> its block of text in docker-compose.yml"""
    top = COMPOSE.split("\nnetworks:")[0]
    parts = re.split(r"^  ([a-z-]+):\n", top.split("services:\n", 1)[1], flags=re.M)      # [text before, name, body, name, body, ...]
    return dict(zip(parts[1::2], parts[2::2]))


def without_comments(text):
    """Comments may legitimately mention what is forbidden ("the host's docker.sock is never mounted")."""
    return "\n".join(re.sub(r"(^|\s)#.*$", "", line) for line in text.splitlines())


def final_stage(dockerfile):
    return dockerfile.rsplit("\nFROM ", 1)[1]


def apt_packages(dockerfile):
    text = final_stage(dockerfile)
    match = re.search(r"apt-get install -y --no-install-recommends ([^&]+?)\s*\\?\s*&&", text.replace("\\\n", " "))
    assert match, "no apt-get install in the final stage"
    return set(match.group(1).split())


# ---------------------------------------------------------------- the Docker client


@pytest.mark.parametrize("name", ["sandbox", "terminal"])
def test_the_docker_client_comes_from_the_official_image(name):
    text = DOCKERFILES[name]
    assert re.search(r"^ARG DOCKER_CLI_IMAGE=docker:cli$", text, re.M)
    first_from = text.index("\nFROM ")
    assert text.index("ARG DOCKER_CLI_IMAGE") < first_from, "a global ARG used by FROM must come before the first FROM"
    assert "FROM ${DOCKER_CLI_IMAGE} AS dockercli" in text
    assert "COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker" in text
    assert "COPY --from=dockercli /usr/local/libexec/docker/cli-plugins/docker-compose" in text
    assert "RUN docker --version && docker compose version" in final_stage(text)            # the build fails if the client is broken


@pytest.mark.parametrize("name", ["sandbox", "terminal"])
def test_there_is_no_docker_daemon_in_the_images(name):
    text = without_comments(DOCKERFILES[name])
    for forbidden in ("docker.io", "docker-ce", "dockerd", "containerd", "docker:dind", "podman"):
        assert forbidden not in text, forbidden


# ---------------------------------------------------------------- isolation must not erode


def networks_of(block):
    match = re.search(r"networks:\s*\[(.*?)\]", block)
    return {n.strip() for n in match.group(1).split(",")} if match else {"default"}


def test_the_hosts_docker_socket_is_never_mounted():
    everything = without_comments(COMPOSE + "".join(DOCKERFILES.values()) + (ROOT / "entrypoint.sh").read_text() + (ROOT / "Makefile").read_text())
    assert "docker.sock" not in everything and "/var/run/docker" not in everything
    assert "pid: host" not in COMPOSE and "network_mode: host" not in COMPOSE and "ipc: host" not in COMPOSE


def test_only_the_rootless_daemon_is_privileged_and_it_is_boxed_in():
    privileged = [name for name, block in services().items() if re.search(r"^\s*privileged\s*:\s*true", without_comments(block), re.M | re.I)]
    assert privileged == ["dind"], f"only the Docker daemon may be privileged, found {privileged}"
    block = without_comments(services()["dind"])
    assert "image: docker:dind-rootless" in block                       # rootless: even an escape lands as an unprivileged user
    assert "ports:" not in block                                        # unreachable from outside the private networks
    mounts = re.findall(r"^\s+- (\S+:\S+)", block.split("volumes:", 1)[1].split("networks:", 1)[0], re.M)
    assert mounts == ["docker-data:/home/rootless/.local/share/docker"], f"no bind mounts of your files: {mounts}"
    assert networks_of(block) == {"docker-net", "builds-net"}
    for secret in ("ANTHROPIC_API_KEY", "LLM_API_KEY", "TERMINAL_TOKEN", "SSH_AUTH_SOCK", "PROJECTS_DIR"):
        assert secret not in block, secret
    assert "mem_limit" in block and "pids_limit" in block and "cpus" in block      # it cannot starve the machine


def test_the_networks_keep_student_code_away_from_the_internet():
    nets = COMPOSE.split("\nnetworks:")[1].split("\nvolumes:")[0]
    assert re.search(r"sandbox-net:\s*\n\s+internal: true", nets) and re.search(r"docker-net:[^\n]*\n\s+internal: true", nets)
    assert re.search(r"builds-net:\s*\{\}", nets)                                  # the only network with internet access...
    holders = [name for name, block in services().items() if "builds-net" in networks_of(block)]
    assert holders == ["dind"]                                                 # ...and only the daemon is on it


def test_the_sandbox_that_runs_student_code_stays_locked_down():
    block = without_comments(services()["sandbox"])
    assert networks_of(block) == {"sandbox-net", "docker-net"}      # both internal: no route to the internet, ever
    assert "DOCKER_HOST: tcp://dind:2375" in block                   # the separate daemon, not the host's
    assert "read_only: true" in block and "cap_drop: [ALL]" in block and "no-new-privileges:true" in block
    assert "ports:" not in block and "privileged" not in block


def test_the_terminal_gets_the_projects_folder_read_write_by_default_and_only_that_folder():
    block = without_comments(services()["terminal"])
    mounts = re.findall(r"^\s+- (\S+:/projects\S*)", block, re.M)
    assert mounts == ["${PROJECTS_DIR:-./projects}:/projects:${TERMINAL_PROJECTS_MODE:-rw}"]      # read-write unless TERMINAL_PROJECTS_MODE=ro
    others = re.findall(r"^\s+- (\S+:\S+)", block.split("volumes:", 1)[1].split("tmpfs:", 1)[0], re.M)
    assert others == [mounts[0], "claude-home:/home/term", "./.ssh-pub:/home/term/.ssh:ro"], others    # nothing else of yours is mounted


def test_the_terminal_gets_only_your_public_keys_and_read_only():
    recipe = MAKEFILE.split("\npubkeys:", 1)[1].split("\n\n", 1)[0]
    assert "$(HOME)/.ssh/*.pub" in recipe and not re.search(r"\.ssh/(\*|id_)[^.\s]*\s", recipe)              # never a private key
    assert re.search(r"^build: .*\bpubkeys\b", MAKEFILE, re.M)                                                 # refreshed on every build
    assert ".ssh-pub" in (ROOT / ".gitignore").read_text() and ".ssh-pub" in (ROOT / ".dockerignore").read_text()


def test_the_shell_tab_runs_zsh_with_oh_my_zsh_without_writing_into_the_image():
    final = final_stage(TERMINAL)
    assert "zsh" in apt_packages(TERMINAL)
    assert "TERMINAL_SHELL=/usr/bin/zsh" in final and "ZDOTDIR=/etc/verdict-zsh" in final
    assert "COPY terminal/zshrc /etc/verdict-zsh/.zshrc" in final and "/opt/oh-my-zsh" in final
    zshrc = (ROOT / "terminal" / "zshrc").read_text()
    assert 'ZSH_CACHE_DIR="$HOME/' in zshrc and "':omz:update' mode disabled" in zshrc                       # the image is read-only


def test_the_terminal_keeps_its_isolation_and_none_of_the_apps_secrets():
    block = without_comments(services()["terminal"])
    assert "read_only: true" in block and "cap_drop: [ALL]" in block                               # (the container's own filesystem stays read-only)
    for secret in ("ANTHROPIC_API_KEY", "LLM_API_KEY", "SSH_AUTH_SOCK", "ssh-auth.sock"):
        assert secret not in block, secret
    assert "ports:" not in block and "privileged" not in block
    assert "DOCKER_HOST: tcp://dind:2375" in block and networks_of(block) == {"default", "docker-net"}


# ---------------------------------------------------------------- the two toolchains stay the same


def test_the_terminal_has_every_package_the_sandbox_has():
    sandbox, terminal = apt_packages(SANDBOX), apt_packages(TERMINAL)
    assert sandbox <= terminal, f"missing from the terminal image: {sorted(sandbox - terminal)}"
    for needed in ("build-essential", "make", "valgrind", "vim", "nano", "libreadline-dev", "libx11-dev", "libxext-dev", "libbsd-dev", "zlib1g-dev"):
        assert needed in sandbox and needed in terminal


def test_both_images_pin_the_same_norminette():
    pins = [re.findall(r"^ARG (NORMINETTE_REF|NORMINETTE_COMMIT)=(\S+)$", d, re.M) for d in (SANDBOX, TERMINAL)]
    assert pins[0] and pins[0] == pins[1]


def test_the_compose_parser_used_by_these_tests_sees_all_services():
    assert set(services()) == {"web", "sandbox", "terminal", "dind"}
    assert "build:" in services()["web"] and "tmpfs:" in services()["terminal"]

# ---------------------------------------------------------------- git credentials for the terminal: opt-in, and nothing else widens

SSH_OVERRIDE = (ROOT / "docker-compose.ssh.yml").read_text()
MAKEFILE = (ROOT / "Makefile").read_text()

def test_the_agent_is_not_in_the_default_setup_for_the_terminal():
    # the guarantee above still holds for docker-compose.yml itself: the opt-in lives in a separate file
    block = without_comments(services()["terminal"])
    assert "SSH_AUTH_SOCK" not in block and "ssh-auth.sock" not in block and "user:" not in block and "cap_add" not in block

def test_the_ssh_override_only_gives_the_terminal_the_agent_and_the_means_to_drop_privileges():
    text = without_comments(SSH_OVERRIDE)
    assert re.findall(r"^  ([a-z-]+):\n", text.split("services:\n", 1)[1], re.M) == ["terminal"]       # no other service is touched
    assert "SSH_AUTH_SOCK: /run/host-services/ssh-auth.sock" in text
    assert re.findall(r"^\s+- (\S+:\S+)", text, re.M) == ["${SSH_AGENT_MOUNT:-/run/host-services/ssh-auth.sock}:/run/host-services/ssh-auth.sock"]
    assert "cap_add: [SETUID, SETGID]" in text and "user: root" in text
    for forbidden in ("privileged", "docker.sock", "network", "ports:", "read_only", "cap_drop", "ANTHROPIC", "LLM_", "PROJECTS_DIR", ".env"):
        assert forbidden not in text, forbidden
    assert "ANYTHING that runs in the terminal container can use your keys" in SSH_OVERRIDE         # the cost is stated where it is switched on

def test_the_ssh_override_is_only_used_when_asked_for():
    assert re.search(r"^TERMINAL_SSH \?= \$\(shell grep -m1 '\^TERMINAL_SSH=' \.env", MAKEFILE, re.M)
    assert re.search(r"^ifeq \(\$\(TERMINAL_SSH\),1\)\nCOMPOSE = docker compose -f docker-compose\.yml -f docker-compose\.ssh\.yml\nendif$", MAKEFILE, re.M)
    assert "docker-compose.ssh.yml" not in re.sub(r"ifeq \(\$\(TERMINAL_SSH\),1\)\n.*?\nendif", "", without_comments(MAKEFILE), flags=re.S)

def test_the_terminal_image_can_push_over_ssh_but_trusts_only_githubs_pinned_key():
    final = final_stage(TERMINAL)
    assert {"openssh-client", "socat"} <= apt_packages(TERMINAL)
    assert "ARG GITHUB_ED25519_FINGERPRINT=SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU" in final         # same pin as norminette's
    assert '[ "$(ssh-keygen -lf /etc/ssh/ssh_known_hosts | awk \'{print $2}\')" = "$GITHUB_ED25519_FINGERPRINT" ]' in final   # the build fails on a mismatch
    assert "StrictHostKeyChecking yes" in final                                                                  # any other host is refused
    assert not re.search(r"id_(rsa|ed25519|ecdsa)|PRIVATE KEY", final)                                           # no key is ever baked in

def test_the_terminal_starts_through_the_shared_entrypoint_but_still_runs_as_the_unprivileged_user():
    final = final_stage(TERMINAL)
    assert "COPY --chmod=755 entrypoint.sh /entrypoint.sh" in final and 'ENTRYPOINT ["/entrypoint.sh"]' in final
    assert final.index("ENTRYPOINT") < final.index("\nUSER term")                                                 # and the default user is still term
    assert final.rstrip().splitlines()[-1].startswith("CMD ")


def test_claude_and_the_shell_work_in_the_project_by_default_and_the_copy_is_one_setting_away():
    block = without_comments(services()["terminal"])
    assert "TERMINAL_WORKDIR: ${TERMINAL_WORKDIR:-live}" in block                       # live unless TERMINAL_WORKDIR=copy
    for other in ("web", "sandbox", "dind"):
        assert "TERMINAL_WORKDIR" not in without_comments(services()[other]), other     # the web app asks the terminal, so the two cannot disagree


def test_the_terminal_can_read_pdfs_without_a_script_of_claudes_own():
    final = final_stage(TERMINAL)
    assert "poppler-utils" in apt_packages(TERMINAL)                                          # pdftotext, pdftoppm, pdfinfo
    assert "COPY --chmod=755 terminal/readpdf /usr/local/bin/readpdf" in final
    assert final.index("RUN pip install --no-cache-dir .") < final.index("readpdf --help")     # (it needs PyMuPDF, which that installs)
    assert "RUN readpdf --help >/dev/null && pdftotext -v" in final                          # the build fails if either tool is broken
    script = (ROOT / "terminal" / "readpdf")
    assert script.read_text().startswith("#!/usr/bin/env python3") and script.stat().st_mode & 0o111
