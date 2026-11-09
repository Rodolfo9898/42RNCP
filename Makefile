COMPOSE = docker compose

# TERMINAL_SSH=1 (on the command line, or a line TERMINAL_SSH=1 in .env) gives claude's terminal and the shell tab your
# ssh-agent so `git push` works there. Off by default: while it is on, anything running in that container, including a
# project's code that claude builds, can use your keys. See docker-compose.ssh.yml.
# (spaces, tabs, quotes and a Windows line ending around the 1 are ignored: "TERMINAL_SSH=1 " must not silently mean off)
TERMINAL_SSH ?= $(shell grep -m1 '^TERMINAL_SSH=' .env 2>/dev/null | cut -d= -f2- | tr -d ' \t\r"')
ifeq ($(strip $(TERMINAL_SSH)),1)
COMPOSE_FILES += -f docker-compose.ssh.yml
endif

# SANDBOX_GITHUB=1 (same two places) gives the sandbox a route to github.com:443 only, so a project's public submodules can be fetched
# during the checks. No key and no ssh-agent are involved. Off by default. See docker-compose.sandbox-github.yml.
SANDBOX_GITHUB ?= $(shell grep -m1 '^SANDBOX_GITHUB=' .env 2>/dev/null | cut -d= -f2- | tr -d ' \t\r"')
ifeq ($(strip $(SANDBOX_GITHUB)),1)
COMPOSE_FILES += -f docker-compose.sandbox-github.yml
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
build: token ssh pubkeys
	$(if $(wildcard $(AGENT_SOCK)),SSH_AUTH_SOCK=$(AGENT_SOCK) $(COMPOSE) build --ssh default,$(COMPOSE) build)

run: build token
	@mkdir -p $(PROJECTS_DIR)
	$(COMPOSE) up

clean: token
	$(COMPOSE) down --remove-orphans

fclean: token
	$(COMPOSE) down --remove-orphans --volumes --rmi local

re: fclean build

# The web app and the terminal container share a random token; it lives in .env (never committed).
token:
	@touch .env && chmod 600 .env
	@grep -q '^TERMINAL_TOKEN=.' .env || { printf '\nTERMINAL_TOKEN=%s\n' "$$(openssl rand -hex 24)" >> .env; echo "created TERMINAL_TOKEN in .env"; }

# Starts the agent if needed and loads your keys into it (asks for each key's passphrase once).
ssh:
	@VERDICT_OWN_AGENT=$(OWN_AGENT) sh scripts/ssh-setup.sh "$(AGENT_SOCK)" $(SSH_KEYS)

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
	curl -fsS -m 30 "$$base/models" $${key:+-H "Authorization: Bearer $$key"} | python3 scripts/models.py

# 42Cursus: the repo with every project as a submodule, grouped by track (see scripts/cursus.sh). GitHub is the only copy: each
# command clones it into a temporary folder, works there, pushes the result and deletes the folder. Add CURSUS_DRY_RUN=1 to any
# of them to do everything except pushing and creating.
#   make cursus-push                 push your projects (all of ./projects) to their own GitHub repos, so the rest sees them
#   make cursus-push ONLY="libft nm" ...or only these
#   make cursus                      create the private GitHub repo (once)
#   make cursus-sort                 add what is in the projects folder to it as submodules, and push
#                                    (a folder of repos, e.g. cpp-modules/, stays a folder: common-core/cpp-modules/cpp00)
#   make cursus-sort MAP="ft_transcendence=common-core"   for a project that has no subject PDF with its name
#   make cursus-update               move every submodule to the newest commit of its own GitHub repo, and push
cursus:
	@sh scripts/cursus.sh init

cursus-sort:
	@sh scripts/cursus.sh sort $(MAP)

cursus-update:
	@sh scripts/cursus.sh update

cursus-push:
	@sh scripts/cursus.sh push $(ONLY)

# The page itself (every script, with a fake server) is run in jsdom by tests/test_ui.py: no browser needed. This installs jsdom once, next
# to the tests (tests/js/node_modules), and runs them. Without jsdom `uv run pytest` skips them.
test-ui:
	@cd tests/js && npm install --no-audit --no-fund --silent
	@uv run pytest tests/test_ui.py -q

.PHONY: all build run clean fclean re models token ssh pubkeys cursus cursus-sort cursus-update cursus-push test-ui
