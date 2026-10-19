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


def test_the_terminal_keeps_the_projects_read_only_and_none_of_the_apps_secrets():
    block = without_comments(services()["terminal"])
    assert ":/projects:ro" in block and "read_only: true" in block and "cap_drop: [ALL]" in block
    for secret in ("ANTHROPIC_API_KEY", "LLM_API_KEY", "SSH_AUTH_SOCK", "ssh-auth.sock"):
        assert secret not in block, secret
    assert "ports:" not in block and "privileged" not in block
    assert "DOCKER_HOST: tcp://dind:2375" in block and networks_of(block) == {"default", "docker-net"}


# ---------------------------------------------------------------- the two toolchains stay the same


def test_the_terminal_has_every_package_the_sandbox_has():
    sandbox, terminal = apt_packages(SANDBOX), apt_packages(TERMINAL)
    assert sandbox <= terminal, f"missing from the terminal image: {sorted(sandbox - terminal)}"
    for needed in ("build-essential", "make", "valgrind", "libreadline-dev", "libx11-dev", "libxext-dev", "libbsd-dev", "zlib1g-dev"):
        assert needed in sandbox and needed in terminal


def test_both_images_pin_the_same_norminette():
    pins = [re.findall(r"^ARG (NORMINETTE_REF|NORMINETTE_COMMIT)=(\S+)$", d, re.M) for d in (SANDBOX, TERMINAL)]
    assert pins[0] and pins[0] == pins[1]


def test_the_compose_parser_used_by_these_tests_sees_all_services():
    assert set(services()) == {"web", "sandbox", "terminal", "dind"}
    assert "build:" in services()["web"] and "tmpfs:" in services()["terminal"]
