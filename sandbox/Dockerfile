# ---- stage 1: build norminette from its official repository (https://github.com/42School/norminette)
# Same steps as that repository's own Dockerfile: compile the translations, then build a wheel.
# Which image the Docker client is copied from (global ARG: it must come before the first FROM).
ARG DOCKER_CLI_IMAGE=docker:cli

FROM python:3.14-slim AS norminette

ARG NORMINETTE_REPO=git@github.com:42school/norminette.git
ARG NORMINETTE_HTTPS=https://github.com/42school/norminette.git
ARG NORMINETTE_REF=3.3.60
ARG NORMINETTE_COMMIT=9e9fd09b75ed89be4e1e2cc339674eabefac833e
ARG GITHUB_ED25519_FINGERPRINT=SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU

RUN apt-get update \
    && apt-get install -y --no-install-recommends git openssh-client gettext ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY sandbox/fetch-norminette.sh /usr/local/bin/fetch-norminette
RUN --mount=type=ssh fetch-norminette

RUN for po in /src/norminette/locale/*/LC_MESSAGES/norminette.po; do msgfmt "$po" -o "${po%.po}.mo"; done \
    && pip wheel --no-deps --wheel-dir /dist /src

# ---- the Docker client (docker, docker compose) from the official image. A CLIENT only: there is deliberately no daemon here
# and the host's /var/run/docker.sock is never mounted (that would give student code root on your machine).
FROM ${DOCKER_CLI_IMAGE} AS dockercli

# ---- stage 2: the sandbox that builds and runs the code under review
FROM python:3.14-slim

# Toolchains used to build and check the repositories under review (keep in step with terminal/Dockerfile).
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates build-essential make valgrind vim nano libreadline-dev libx11-dev libxext-dev libbsd-dev zlib1g-dev xvfb x11-utils \
    && rm -rf /var/lib/apt/lists/*

# A virtual X display for programs with a window (MiniLibX): runner.py starts Xvfb and gives every command DISPLAY=:99.
RUN command -v Xvfb && command -v xdpyinfo

# A project's submodules, with no key: there is no ssh client here, so a git@github.com: address is read as https://github.com/ and a
# public repository can be fetched whichever form .gitmodules uses. It only reaches GitHub with docker-compose.sandbox-github.yml.
RUN git config --system url."https://github.com/".insteadOf "git@github.com:" \
    && git config --system --add url."https://github.com/".insteadOf "ssh://git@github.com/"

COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=dockercli /usr/local/libexec/docker/cli-plugins/docker-compose /usr/local/libexec/docker/cli-plugins/docker-compose
RUN docker --version && docker compose version

COPY --from=norminette /dist /tmp/dist
RUN pip install --no-cache-dir /tmp/dist/*.whl flake8 mypy \
    && rm -rf /tmp/dist \
    && norminette --version

# The basics must really be there: C, C++ and make (anything else comes from a Dockerfile the student ships).
RUN cc --version | head -1 && c++ --version | head -1 && make --version | head -1

RUN useradd --create-home --uid 1000 sandbox \
    && mkdir /workspace /projects && chown sandbox:sandbox /workspace /projects

COPY sandbox/runner.py /opt/runner.py

USER sandbox
WORKDIR /workspace
ENV PYTHONDONTWRITEBYTECODE=1
EXPOSE 8001
CMD ["python", "/opt/runner.py"]
