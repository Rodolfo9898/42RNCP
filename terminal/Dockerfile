# The `terminal` service: claude (Claude Code) in its own container, away from the web app's secrets.
# It has the SAME toolchain as the sandbox (cc/c++, make, valgrind, norminette, readline and X11 headers), so claude
# can build and run the student's project itself instead of only reading it. Keep the packages in step with sandbox/Dockerfile.

# ---- stage 1: claude (Claude Code), pinned
# Which image the Docker client is copied from (global ARG: it must come before the first FROM).
ARG DOCKER_CLI_IMAGE=docker:cli

FROM node:22-slim AS claude
ARG CLAUDE_CODE_VERSION=2.1.303
RUN npm install -g --prefix /opt/claude "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" \
    && /opt/claude/bin/claude --version

# ---- stage 2: norminette from its official repository at a pinned, verified commit (same as the sandbox)
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

# ---- stage 3: the terminal service
FROM python:3.14-slim

# Node runtime for claude, copied from the official image (the app itself needs Python 3.14).
COPY --from=claude /usr/local/bin/node /usr/local/bin/node
COPY --from=claude /opt/claude /opt/claude
ENV PATH="/opt/claude/bin:${PATH}"

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git openssh-client socat ripgrep build-essential make valgrind gdb vim nano libreadline-dev libx11-dev libxext-dev libbsd-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# git over ssh, for `git push` from claude's terminal or the shell tab. It only works when docker-compose.ssh.yml gives the
# container your ssh-agent (off by default); there are no keys in the image. GitHub's ED25519 host key is trusted, checked
# against the pinned fingerprint (the build fails if it differs), and every other host is refused instead of asked about.
ARG GITHUB_ED25519_FINGERPRINT=SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU
RUN echo 'github.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl' > /etc/ssh/ssh_known_hosts \
    && [ "$(ssh-keygen -lf /etc/ssh/ssh_known_hosts | awk '{print $2}')" = "$GITHUB_ED25519_FINGERPRINT" ] \
    && printf 'Host *\n\tStrictHostKeyChecking yes\n' > /etc/ssh/ssh_config.d/verdict.conf

COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=dockercli /usr/local/libexec/docker/cli-plugins/docker-compose /usr/local/libexec/docker/cli-plugins/docker-compose
RUN docker --version && docker compose version

COPY --from=norminette /dist /tmp/dist
RUN pip install --no-cache-dir /tmp/dist/*.whl flake8 \
    && rm -rf /tmp/dist \
    && norminette --version

RUN cc --version | head -1 && c++ --version | head -1 && make --version | head -1

RUN useradd --create-home --home-dir /home/term --uid 1000 term \
    && mkdir -p /projects /scratch /home/term/.claude \
    && chown -R term:term /scratch /home/term

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

# The same entrypoint as the web app. As `term` (the default) it only starts the service. With docker-compose.ssh.yml the container
# starts as root, relays the ssh-agent socket so that uid 1000 can open it (Docker Desktop's is root-owned), then drops to uid 1000.
COPY --chmod=755 entrypoint.sh /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]

USER term
ENV PROJECTS_DIR=/projects SCRATCH_DIR=/scratch TERMINAL_HOME=/home/term \
    CLAUDE_CONFIG_DIR=/home/term/.claude PYTHONDONTWRITEBYTECODE=1
EXPOSE 8002
CMD ["uvicorn", "verdict.terminal:app", "--host", "0.0.0.0", "--port", "8002"]
