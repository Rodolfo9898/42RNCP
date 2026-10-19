COMPOSE = docker compose

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
build: token ssh
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

# Lists the models offered by the server in .env (LLM_BASE_URL / LLM_API_KEY). The key is never printed.
models:
	@base="$${LLM_BASE_URL:-$$(grep -m1 '^LLM_BASE_URL=' .env 2>/dev/null | cut -d= -f2-)}"; \
	key="$${LLM_API_KEY:-$$(grep -m1 '^LLM_API_KEY=' .env 2>/dev/null | cut -d= -f2-)}"; \
	[ -n "$$base" ] || { echo "Set LLM_BASE_URL in .env first."; exit 1; }; \
	curl -fsS -m 30 "$$base/models" $${key:+-H "Authorization: Bearer $$key"} | python3 scripts/models.py

.PHONY: all build run clean fclean re models token ssh
