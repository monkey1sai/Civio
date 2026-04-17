.PHONY: help up down logs test test-unit test-integration test-e2e lint type migrate clean build \
        cloud-install cloud-run cloud-test edge-up edge-down app-run app-test

DEFAULT_GOAL := help

# ─── Help ──────────────────────────────────────────────────────────
help:
	@echo "Civio — community SIP platform"
	@echo ""
	@echo "Top-level targets:"
	@echo "  make up                  bring up full local stack"
	@echo "  make down                stop and remove all services"
	@echo "  make logs                tail logs from all services"
	@echo "  make test                run the full test suite"
	@echo "  make lint                run all linters"
	@echo "  make type                run all type checkers"
	@echo "  make migrate             run Alembic upgrade head"
	@echo "  make build               build all Docker images"
	@echo "  make clean               remove volumes, caches, generated files"
	@echo ""
	@echo "Cloud targets:"
	@echo "  make cloud-install       install Python deps for civio-cloud"
	@echo "  make cloud-run           run FastAPI dev server"
	@echo "  make cloud-test          run cloud test suite"
	@echo ""
	@echo "Edge targets:"
	@echo "  make edge-up             bring up a single community edge"
	@echo "  make edge-down           stop the edge stack"
	@echo ""
	@echo "App targets:"
	@echo "  make app-run             flutter run on attached device"
	@echo "  make app-test            flutter test"

# ─── Infrastructure ─────────────────────────────────────────────────
up:
	docker compose up -d
	@echo "API:        http://api.civio.local (add to /etc/hosts: 127.0.0.1 api.civio.local)"
	@echo "RabbitMQ:   http://localhost:15672"
	@echo "Traefik:    http://localhost:8081"

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

build:
	docker compose build

# ─── Testing ────────────────────────────────────────────────────────
test: test-unit test-integration

test-unit:
	@cd civio-cloud && poetry run pytest tests/unit -x -q --cov=src --cov-fail-under=80
	@cd civio-app && flutter test --coverage

test-integration:
	@cd civio-cloud && poetry run pytest tests/integration -x -q

test-e2e:
	@./scripts/e2e.sh

# ─── Code quality ──────────────────────────────────────────────────
lint:
	@cd civio-cloud && poetry run ruff check src/ tests/
	@cd civio-cloud && poetry run ruff format --check src/ tests/
	@cd civio-app && dart format --set-exit-if-changed lib/ test/
	@cd civio-app && dart analyze --fatal-infos lib/ test/

type:
	@cd civio-cloud && poetry run mypy src/ --strict

# ─── Migrations ────────────────────────────────────────────────────
migrate:
	@cd civio-cloud && poetry run alembic upgrade head

migrate-down:
	@cd civio-cloud && poetry run alembic downgrade -1

migrate-new:
	@read -p "Migration name: " name; \
	cd civio-cloud && poetry run alembic revision --autogenerate -m "$$name"

# ─── Cleaning ──────────────────────────────────────────────────────
clean:
	docker compose down -v
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf civio-cloud/htmlcov civio-cloud/.coverage
	@cd civio-app && flutter clean || true

# ─── Cloud shortcuts ───────────────────────────────────────────────
cloud-install:
	@cd civio-cloud && poetry install

cloud-run:
	@cd civio-cloud && poetry run uvicorn src.main:app --reload --port 8000

cloud-test:
	@cd civio-cloud && poetry run pytest -x -q

# ─── Edge shortcuts ────────────────────────────────────────────────
edge-up:
	@cd civio-edge && docker compose up -d

edge-down:
	@cd civio-edge && docker compose down

# ─── App shortcuts ─────────────────────────────────────────────────
app-run:
	@cd civio-app && flutter run

app-test:
	@cd civio-app && flutter test
