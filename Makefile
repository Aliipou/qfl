.PHONY: install test lint format docker-up docker-down clean migrate

install:
	pip install -e ".[dev]"
	pre-commit install

test:
	pytest tests/ -v

test-unit:
	pytest tests/unit/ -v

test-integration:
	pytest tests/integration/ -v

test-quantum:
	pytest tests/quantum/ -v

lint:
	ruff check .
	mypy api/ core/ sdk/

format:
	black .
	ruff check --fix .

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down -v

docker-logs:
	docker compose logs -f

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .coverage coverage.xml htmlcov/ dist/ .mypy_cache/ .ruff_cache/

migrate:
	alembic upgrade head

dev:
	uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
