.PHONY: up down seed test demo lint format migrate

up:
	docker compose up --build

down:
	docker compose down

seed:
	docker compose exec api python -m app.synthetic.generator

test:
	docker compose exec api pytest tests/ -v --tb=short --cov=app --cov-report=term-missing

demo:
	docker compose exec api python -m app.synthetic.generator
	docker compose exec api python -m app.ml.train
	@echo "Demo ready. Open http://localhost:5173"
	@echo "Starting live simulation on AF-204..."
	curl -s -X POST http://localhost:8000/api/v1/simulation/live/start -H "Content-Type: application/json" -d '{"aircraft_id": "AF-204"}' || true

lint:
	docker compose exec api ruff check app/ tests/

format:
	docker compose exec api ruff format app/ tests/

migrate:
	docker compose exec api alembic upgrade head

migrate-create:
	docker compose exec api alembic revision --autogenerate -m "$(msg)"
