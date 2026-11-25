COMPOSE = docker compose

# TERMINAL_SSH=1 (on the command line, or a line TERMINAL_SSH=1 in .env) gives claude's terminal and the shell tab your
# ssh-agent so `git push` works there. Off by default: while it is on, anything running in that container, including a
# project's code that claude builds, can use your keys. See docker/terminal/compose.ssh.yml.
# (spaces, tabs, quotes and a Windows line ending around the 1 are ignored: "TERMINAL_SSH=1 " must not silently mean off)
TERMINAL_SSH ?= $(shell grep -m1 '^TERMINAL_SSH=' .env 2>/dev/null | cut -d= -f2- | tr -d ' \t\r"')
ifeq ($(strip $(TERMINAL_SSH)),1)
COMPOSE_FILES += -f docker/terminal/compose.ssh.yml
endif

# SANDBOX_GITHUB=1 (same two places) gives the sandbox a route to github.com:443 only, so a project's public submodules can be fetched
# during the checks. No key and no ssh-agent are involved. Off by default. See docker/sandbox/compose.github.yml.
SANDBOX_GITHUB ?= $(shell grep -m1 '^SANDBOX_GITHUB=' .env 2>/dev/null | cut -d= -f2- | tr -d ' \t\r"')
ifeq ($(strip $(SANDBOX_GITHUB)),1)
COMPOSE_FILES += -f docker/sandbox/compose.github.yml
endif

ifneq ($(strip $(COMPOSE_FILES)),)
COMPOSE = docker compose -f docker-compose.yml $(COMPOSE_FILES)
endif

# Host folder that holds the cloned projects (mounted at /projects in the containers).
PROJECTS_DIR ?= ./projects
export PROJECTS_DIR

# SSH: clones use your ssh-agent. `make` makes sure one is running with your keys (~/.ssh/id_*, or SSH_KEYS=...)
# loaded, and mounts its socket into the web container. The private keys themselves never enter a container.
ifeq ($(shell uname -s),Darwin)
# Docker Desktop forwards the macOS agent into its VM at a fixed path.
AGENT_SOCK := $(SSH_AUTH_SOCK)
SSH_AGENT_MOUNT ?= /run/host-services/ssh-auth.sock
else ifneq ($(SSH_AUTH_SOCK),)
AGENT_SOCK := $(SSH_AUTH_SOCK)
SSH_AGENT_MOUNT ?= $(AGENT_SOCK)
else
# No agent in this shell: make starts one at this path and reuses it on later runs.
AGENT_SOCK := $(HOME)/.ssh/verdict-agent.sock
OWN_AGENT := 1
SSH_AGENT_MOUNT ?= $(AGENT_SOCK)
endif
export SSH_AGENT_MOUNT
SSH_KEYS ?=

all: build

# norminette is cloned from GitHub over SSH through the same agent (falls back to HTTPS).
build: token ssh pubkeys progress scraper-dirs
	$(if $(wildcard $(AGENT_SOCK)),SSH_AUTH_SOCK=$(AGENT_SOCK) $(COMPOSE) build --ssh default,$(COMPOSE) build)

run: build token
	@mkdir -p $(PROJECTS_DIR)
	@$(MAKE) --no-print-directory url
	$(COMPOSE) up

clean: token
	$(COMPOSE) down --remove-orphans

fclean: token
	$(COMPOSE) down --remove-orphans --volumes --rmi local

re: fclean build

# The web app and the terminal container share a random token, the editor has its own (the ?tkn= of its link), and the web app and the
# scraper container have a third; all live in .env (never committed). A missing .env is a copy of .env.example with those filled in, on their own lines (scripts/env/env-setup.sh).
token:
	@sh scripts/env/env-setup.sh .env .env.example

# Progress.md is mounted into the web container as a file (`Verdict: Update Progress.md` writes the project's row). It has to exist
# before compose starts, or Docker makes a folder of that name. An empty one is fine: the first update writes the table.
progress:
	@[ -e Progress.md ] || : > Progress.md

# The folders the scraper container mounts (samples/, artifacts/, and .session/, where `make samples-login` saves your intra session, read-only
# for the container). They have to exist before compose starts, or Docker makes root-owned ones. .session holds cookies: only you can read it.
scraper-dirs:
	@mkdir -p samples artifacts .session && chmod 700 .session

# The link to the editor, with its token.
url: token
	@echo "Open http://localhost:$${EDITOR_PORT:-8000}/?tkn=$$(grep -m1 '^EDITOR_TOKEN=' .env | cut -d= -f2-)"

# Starts the agent if needed and loads your keys into it (asks for each key's passphrase once).
ssh:
	@VERDICT_OWN_AGENT=$(OWN_AGENT) sh scripts/ssh/ssh-setup.sh "$(AGENT_SOCK)" $(SSH_KEYS)

# Your PUBLIC keys for claude's terminal and the shell tab: ~/.ssh/*.pub, and nothing else, are copied into .ssh-pub/, which the
# terminal container sees read-only as ~/.ssh. The private keys never leave your ~/.ssh. Refreshed on every build.
pubkeys:
	@rm -rf .ssh-pub && mkdir -p .ssh-pub && chmod 755 .ssh-pub
	@for k in $(HOME)/.ssh/*.pub; do [ -f "$$k" ] && cp "$$k" .ssh-pub/ && chmod 644 ".ssh-pub/$${k##*/}"; done; true

# Lists the models offered by the server in .env (LLM_BASE_URL / LLM_API_KEY). The key is never printed.
models:
	@base="$${LLM_BASE_URL:-$$(grep -m1 '^LLM_BASE_URL=' .env 2>/dev/null | cut -d= -f2-)}"; \
	key="$${LLM_API_KEY:-$$(grep -m1 '^LLM_API_KEY=' .env 2>/dev/null | cut -d= -f2-)}"; \
	[ -n "$$base" ] || { echo "Set LLM_BASE_URL in .env first."; exit 1; }; \
	curl -fsS -m 30 "$$base/models" $${key:+-H "Authorization: Bearer $$key"} | python3 scripts/llm/models.py

# 42Cursus: the repo with every project as a submodule, grouped by track (see scripts/cursus/cursus.sh). GitHub is the only copy: each
# command clones it into a temporary folder, works there, pushes the result and deletes the folder. Add CURSUS_DRY_RUN=1 to any
# of them to do everything except pushing and creating.
#   make cursus-push                 push your projects (all of ./projects) to their own GitHub repos, so the rest sees them
#   make cursus-push ONLY="libft nm" ...or only these
#   make cursus-refresh              pull the newest commits of every project of ./projects from its GitHub repo (fast-forward only)
#   make cursus-refresh ONLY="libft" ...or only these
#   make cursus                      create the private GitHub repo (once)
#   make cursus-sort                 add what is in the projects folder to it as submodules, and push
#                                    (a folder of repos, e.g. cpp-modules/, stays a folder: common-core/cpp-modules/cpp00)
#   make cursus-sort MAP="ft_transcendence=common-core"   for a project that has no subject PDF with its name
#   make cursus-update               move every submodule to the newest commit of its own GitHub repo, and push
cursus:
	@sh scripts/cursus/cursus.sh init

cursus-sort:
	@sh scripts/cursus/cursus.sh sort $(MAP)

cursus-update:
	@sh scripts/cursus/cursus.sh update

cursus-push:
	@sh scripts/cursus/cursus.sh push $(ONLY)

cursus-refresh:
	@sh scripts/cursus/cursus.sh refresh $(ONLY)

# Subjects: fills samples/ (the PDFs, one folder per track, series in sub-folders) and artifacts/ (the other files of a project) from the
# 42 intra, using the lists in src/scraper/data. Two ways, one scraper:
#  - From the editor: `Verdict: Download Subjects from the Intra` (and `Show What Subjects Are Missing`). The `scraper` container does the work.
#    It never logs in: it uses the session that `make samples-login` saves on THIS computer (.session/, mounted read-only into it alone).
#  - From this terminal: `make samples`. Same thing, without Docker.
# Both need your intra login, which no container ever gets (INTRA_LOGIN and INTRA_PASSWORD in .env, or it asks for them).
#   make samples-login                        log in once (a browser opens when you add ARGS=--headed: 2FA, captcha); repeat when it expires
#   make samples-plan                         what is missing, per track (offline: nothing is fetched, no login)
#   make samples                              download what is missing: the PDFs and the artifacts
#   make samples ARGS="--track rncp --no-artifacts"      ...only the RNCP PDFs (more options: ARGS=--help)
#   make samples ARGS="-p libft -p cpp-module-00"        ...only these projects
SCRAPE_VENV ?= .scraper-venv

$(SCRAPE_VENV)/.ready: src/scraper/requirements.txt
	python3 -m venv $(SCRAPE_VENV)
	$(SCRAPE_VENV)/bin/pip install -q -r src/scraper/requirements.txt
	@touch $@

samples-login: $(SCRAPE_VENV)/.ready scraper-dirs
	@$(SCRAPE_VENV)/bin/python src/subject_scraper.py --login $(ARGS)

samples-plan: $(SCRAPE_VENV)/.ready
	@$(SCRAPE_VENV)/bin/python src/subject_scraper.py --dry-run $(ARGS)

samples: $(SCRAPE_VENV)/.ready
	@$(SCRAPE_VENV)/bin/python src/subject_scraper.py $(ARGS)

# The Verdict extension (src/extension) is TypeScript. Its tests (tests/extension) are TypeScript too: tests/extension/test_extension.py
# compiles both with the extension's own compiler and runs them in node with a fake editor (skipped, with the reason, when node 20+ or
# the compiler is missing). This installs, once and next to each, the compiler and typings (src/extension) and the TextMate engine that
# checks the colours of the ignore files (tests/extension). To build the extension by hand: cd src/extension && npm install && npm run build
test-extension:
	@cd src/extension && npm install --no-audit --no-fund --silent
	@cd tests/extension && npm install --no-audit --no-fund --silent
	@uv run pytest tests/extension/test_extension.py -q

.PHONY: all build run clean fclean re models token url ssh pubkeys progress scraper-dirs samples samples-login samples-plan cursus cursus-sort cursus-update cursus-push cursus-refresh test-extension
