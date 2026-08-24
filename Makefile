# Common developer tasks. `make help` lists them.
.DEFAULT_GOAL := help
.PHONY: help install test test-integration lint fmt up down logs clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## Install backend (dev) + frontend dependencies
	pip install -e ".[dev]"
	cd frontend && npm ci

test: ## Run unit tests (no external services)
	pytest -m "not integration" --cov=app --cov-report=term-missing

test-integration: ## Run integration tests (needs live Neo4j + Qdrant)
	RUN_INTEGRATION=1 pytest -m integration

lint: ## Lint backend (ruff) + frontend (eslint)
	ruff check .
	cd frontend && npm run lint

fmt: ## Auto-fix + format backend with ruff
	ruff check --fix .
	ruff format .

up: ## Start the full stack (UI + API + Neo4j + Qdrant)
	docker compose up --build

down: ## Stop the stack
	docker compose down

logs: ## Tail stack logs
	docker compose logs -f

clean: ## Stop the stack and remove volumes (DESTRUCTIVE: drops DB data)
	docker compose down -v
