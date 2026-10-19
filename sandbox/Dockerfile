# ---- stage 1: build norminette from its official repository (https://github.com/42School/norminette)
# Same steps as that repository's own Dockerfile: compile the translations, then build a wheel.
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

# ---- stage 2: the sandbox that builds and runs the code under review
FROM python:3.14-slim

# Toolchains used to build and check the repositories under review (keep in step with terminal/Dockerfile).
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential make valgrind libreadline-dev libx11-dev libxext-dev libbsd-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --from=norminette /dist /tmp/dist
RUN pip install --no-cache-dir /tmp/dist/*.whl flake8 mypy \
    && rm -rf /tmp/dist \
    && norminette --version

RUN useradd --create-home --uid 1000 sandbox \
    && mkdir /workspace /projects && chown sandbox:sandbox /workspace /projects

COPY sandbox/runner.py /opt/runner.py

USER sandbox
WORKDIR /workspace
ENV PYTHONDONTWRITEBYTECODE=1
EXPOSE 8001
CMD ["python", "/opt/runner.py"]
