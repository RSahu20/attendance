.PHONY: setup up down logs test lint format migrate

setup:
	cp -n .env.example .env || true

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

test:
	docker compose run --rm api pytest

lint:
	docker compose run --rm api ruff check src tests alembic

format:
	docker compose run --rm api ruff format src tests alembic

migrate:
	docker compose run --rm api alembic upgrade head

