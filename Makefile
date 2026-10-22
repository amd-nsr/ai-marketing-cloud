# Developer entry points. Run `make help` for the list.
.DEFAULT_GOAL := help
SHELL := /bin/bash

BACKEND := cd backend &&
FRONTEND := cd frontend &&

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# --- Setup -------------------------------------------------------------------

.PHONY: setup
setup: ## Install backend and frontend dependencies, create .env if missing
	@test -f .env || (cp .env.example .env && echo "Created .env from .env.example")
	$(BACKEND) uv sync
	$(FRONTEND) npm ci

# --- Local services ------------------------------------------------------------

.PHONY: deps
deps: ## Start PostgreSQL and Redis in Docker
	docker compose up -d --wait postgres redis

.PHONY: up
up: ## Run the whole stack in Docker (postgres, redis, backend, worker, frontend)
	docker compose up --build

.PHONY: down
down: ## Stop all Docker services (data volumes are kept)
	docker compose down

# --- Running natively (after `make deps`) -------------------------------------

.PHONY: backend
backend: ## Run the Django dev server on :8000
	$(BACKEND) uv run python manage.py runserver 8000

.PHONY: worker
worker: ## Run a Celery worker
	$(BACKEND) uv run celery -A config worker --loglevel=INFO

.PHONY: beat
beat: ## Run the Celery beat scheduler (exactly one per environment)
	$(BACKEND) uv run celery -A config beat --loglevel=INFO -s /tmp/amc-celerybeat-schedule

.PHONY: frontend
frontend: ## Run the Next.js dev server on :3000
	$(FRONTEND) npm run dev

.PHONY: migrate
migrate: ## Apply database migrations
	$(BACKEND) uv run python manage.py migrate

.PHONY: migrations
migrations: ## Create migrations for model changes
	$(BACKEND) uv run python manage.py makemigrations

# --- Quality -----------------------------------------------------------------

.PHONY: check
check: check-backend check-frontend ## Run every lint, type check, and test

.PHONY: check-backend
check-backend: ## Backend: format check, lint, types, migrations, contract, tests
	$(BACKEND) uv run ruff format --check .
	$(BACKEND) uv run ruff check .
	$(BACKEND) uv run mypy .
	$(BACKEND) uv run python manage.py makemigrations --check --dry-run
	$(MAKE) openapi-check
	$(BACKEND) uv run pytest

.PHONY: check-frontend
check-frontend: ## Frontend: format check, lint, types, tests
	$(FRONTEND) npm run format:check
	$(FRONTEND) npm run lint
	$(FRONTEND) npm run typecheck
	$(FRONTEND) npm test

.PHONY: format
format: ## Auto-format backend and frontend code
	$(BACKEND) uv run ruff format . && uv run ruff check --fix .
	$(FRONTEND) npm run format

.PHONY: test
test: ## Run backend and frontend tests only
	$(BACKEND) uv run pytest
	$(FRONTEND) npm test

# --- API contract --------------------------------------------------------------

.PHONY: openapi
openapi: ## Regenerate docs/api/openapi.yaml from the Django API
	$(BACKEND) uv run python manage.py spectacular --validate --fail-on-warn --file ../docs/api/openapi.yaml

.PHONY: openapi-check
openapi-check: ## Fail if docs/api/openapi.yaml is out of date
	@tmp=$$(mktemp) && trap 'rm -f "$$tmp"' EXIT && \
	  (cd backend && uv run python manage.py spectacular --validate --fail-on-warn --file "$$tmp") && \
	  diff -u docs/api/openapi.yaml "$$tmp" && echo "OpenAPI contract is up to date." || \
	  (echo "docs/api/openapi.yaml is stale: run 'make openapi'." && exit 1)

.PHONY: audit
audit: ## Check Python and npm dependencies for known vulnerabilities
	@tmp=$$(mktemp) && trap 'rm -f "$$tmp"' EXIT && \
	  (cd backend && uv export --frozen --no-dev --no-hashes --no-emit-project --format requirements-txt -o "$$tmp" >/dev/null) && \
	  uvx pip-audit --strict -r "$$tmp"
	cd frontend && npm audit --omit=dev --audit-level=moderate

.PHONY: e2e
e2e: ## Run the Playwright pilot journey against the running dev stack (see docs/development/e2e.md)
	cd frontend && npm run e2e
