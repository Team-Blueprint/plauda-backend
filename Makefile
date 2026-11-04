.PHONY: install dev test lint fmt migrate revision openapi deploy

install:
	cd backend && uv sync

dev:
	cd backend && uv run uvicorn app.main:app --reload --port 8000

test:
	cd backend && uv run pytest -q

lint:
	cd backend && uv run ruff check .

fmt:
	cd backend && uv run ruff format .

migrate:
	cd backend && uv run alembic upgrade head

revision:
	cd backend && uv run alembic revision --autogenerate -m "$(m)"

openapi:
	cd backend && uv run python scripts/export_openapi.py

deploy:
	cd backend && uv run fastapi deploy
