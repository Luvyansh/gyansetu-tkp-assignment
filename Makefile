# GyanSetu TKP — common developer tasks (requires `uv` on PATH).
# Windows: use `make` via Git Bash / chocolatey, or run the `uv run …` recipes directly.

.PHONY: help sync dev-db migrate backend frontend test test-unit lint format typecheck \
	bandit eval eval-real pre-commit docker-build clean

help:
	@echo "Targets: sync | dev-db | migrate | backend | frontend | test | test-unit"
	@echo "         lint | format | typecheck | bandit | eval | pre-commit | docker-build"

sync:
	uv sync --extra dev

dev-db:
	docker compose -f docker-compose.dev.yml up -d

migrate:
	uv run alembic upgrade head

backend:
	uv run uvicorn backend.app.main:app --reload --port 8000

frontend:
	uv run streamlit run frontend/streamlit_app.py

test:
	uv run pytest

test-unit:
	uv run pytest backend/tests/unit -q --cov-fail-under=0

lint:
	uv run ruff check backend frontend evals
	uv run ruff format --check backend frontend evals

format:
	uv run ruff check --fix backend frontend evals
	uv run ruff format backend frontend evals

typecheck:
	uv run mypy backend/app

bandit:
	uv run bandit -c pyproject.toml -r backend/app

eval:
	EVAL_MOCK=1 uv run python evals/run_ragas_eval.py --mock

eval-real:
	EVAL_MOCK=0 uv run python evals/run_ragas_eval.py --real

pre-commit:
	uv run pre-commit install
	uv run pre-commit run --all-files

docker-build:
	docker build -t gyansetu-tkp:latest .

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
