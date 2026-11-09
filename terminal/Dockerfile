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

# ---- the editor: VS Code in the browser (OpenVSCode Server, which installs extensions from Open VSX), pinned and checked
FROM python:3.14-slim AS openvscode
ARG TARGETARCH
ARG OPENVSCODE_VERSION=1.109.5
ARG OPENVSCODE_SHA256_X64=b433bf4f0227321a7014d8460d10a8f958adc0f45aa79bd889e84e65e8f88363
ARG OPENVSCODE_SHA256_ARM64=36d9c14036489b63de84ebace837fcacf7e60e669a0dc715802c5443684ea4dc
RUN set -e; \
    case "${TARGETARCH:-amd64}" in arm64) arch=arm64; sum=$OPENVSCODE_SHA256_ARM64 ;; *) arch=x64; sum=$OPENVSCODE_SHA256_X64 ;; esac; \
    name="openvscode-server-v${OPENVSCODE_VERSION}-linux-${arch}"; \
    python -c "import sys, urllib.request as u; u.urlretrieve(sys.argv[1], '/tmp/ovs.tgz')" \
        "https://github.com/gitpod-io/openvscode-server/releases/download/openvscode-server-v${OPENVSCODE_VERSION}/${name}.tar.gz"; \
    echo "$sum  /tmp/ovs.tgz" | sha256sum -c -; \
    mkdir /opt/openvscode-server && tar -xzf /tmp/ovs.tgz -C /opt/openvscode-server --strip-components=1 && rm /tmp/ovs.tgz

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
    && apt-get install -y --no-install-recommends ca-certificates git openssh-client socat poppler-utils ripgrep build-essential make valgrind gdb vim nano zsh libreadline-dev libx11-dev libxext-dev libbsd-dev zlib1g-dev xvfb x11-utils \
    && rm -rf /var/lib/apt/lists/*

# A virtual X display for programs with a window (MiniLibX): the service starts Xvfb and gives claude and the shell DISPLAY=:99.
RUN command -v Xvfb && command -v xdpyinfo

# The ⌨ Shell tab runs zsh (TERMINAL_SHELL below) with Oh My Zsh. Both live in the image (no auto-update: the image is
# read-only); the rc file also sources your own ~/.zshrc if you add one. OH_MY_ZSH_REF pins a branch, tag or commit.
ARG OH_MY_ZSH_REF=master
RUN git clone --quiet https://github.com/ohmyzsh/ohmyzsh.git /opt/oh-my-zsh \
    && git -C /opt/oh-my-zsh checkout --quiet "$OH_MY_ZSH_REF" \
    && git -C /opt/oh-my-zsh log -1 --format='oh-my-zsh %h %cs' \
    && rm -rf /opt/oh-my-zsh/.git
COPY terminal/zshrc /etc/verdict-zsh/.zshrc

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

# Reading the subject PDFs: `readpdf` (text of a PDF, by page or searched; only the PDFs of the review) and poppler's pdftotext, pdftoppm
# and pdfinfo, which claude's own PDF reading and quick commands need. Without them claude says it has no PDF tool and writes a script.
COPY --chmod=755 terminal/readpdf /usr/local/bin/readpdf
RUN readpdf --help >/dev/null && pdftotext -v 2>&1 | head -1

# The editor (see src/verdict/editor.py): VS Code, with the Verdict extension built in (terminal/vscode/verdict) and the settings it
# starts with. The extensions you add (config/extensions.txt) and your own settings live in the claude-home volume.
COPY --from=openvscode /opt/openvscode-server /opt/openvscode-server
COPY terminal/vscode/verdict /opt/openvscode-server/extensions/verdict
COPY terminal/vscode/settings.json /etc/verdict-editor/settings.json
RUN /opt/openvscode-server/bin/openvscode-server --version | head -1

# The same entrypoint as the web app. As `term` (the default) it only starts the service. With docker-compose.ssh.yml the container
# starts as root, relays the ssh-agent socket so that uid 1000 can open it (Docker Desktop's is root-owned), then drops to uid 1000.
COPY --chmod=755 entrypoint.sh /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]

USER term
ENV PROJECTS_DIR=/projects SCRATCH_DIR=/scratch TERMINAL_HOME=/home/term \
    CLAUDE_CONFIG_DIR=/home/term/.claude PYTHONDONTWRITEBYTECODE=1 \
    TERMINAL_SHELL=/usr/bin/zsh ZDOTDIR=/etc/verdict-zsh
# 3000: the editor (published by docker-compose.yml); 8002: the terminal service (the web app only, on the internal network).
EXPOSE 3000 8002
CMD ["python", "-m", "verdict.editor"]
