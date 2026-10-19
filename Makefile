COMPOSE = docker compose

# Host folder that holds the cloned projects (mounted at /projects in the containers).
PROJECTS_DIR ?= ./projects
export PROJECTS_DIR

all: build

# norminette is cloned from GitHub over SSH when an ssh-agent is available (falls back to HTTPS).
build: token
	$(COMPOSE) build $(if $(SSH_AUTH_SOCK),--ssh default,)

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

# Lists the models offered by the server in .env (LLM_BASE_URL / LLM_API_KEY). The key is never printed.
models:
	@base="$${LLM_BASE_URL:-$$(grep -m1 '^LLM_BASE_URL=' .env 2>/dev/null | cut -d= -f2-)}"; \
	key="$${LLM_API_KEY:-$$(grep -m1 '^LLM_API_KEY=' .env 2>/dev/null | cut -d= -f2-)}"; \
	[ -n "$$base" ] || { echo "Set LLM_BASE_URL in .env first."; exit 1; }; \
	curl -fsS -m 30 "$$base/models" $${key:+-H "Authorization: Bearer $$key"} | python3 scripts/models.py

.PHONY: all build run clean fclean re models token
