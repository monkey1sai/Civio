# civio-cloud

Python FastAPI control plane. The source of truth for all community, user, SIP endpoint, and token data.

## Before touching this directory

**Read `CLAUDE.md` in this folder first.** It contains the authoritative architecture, class contracts, testing requirements, and constraints for this subproject.

## Quick reference

```bash
# Install
poetry install

# Migrate
poetry run alembic upgrade head

# Run the API
poetry run uvicorn src.main:app --reload --port 8000

# Run the worker
poetry run python -m src.worker

# Test
poetry run pytest tests/ -x -q
poetry run pytest tests/unit --cov=src --cov-fail-under=80

# Lint + type
poetry run ruff check src/ tests/
poetry run mypy src/ --strict

# Create a new module
# (from repo root) use /project:scaffold-module <name>
```

## Subdirectories

- `src/` — all Python source
- `tests/` — unit + integration tests
- `opensips/` — OpenSIPS Docker image + config
- `admin-web/` — React admin console (Phase 11)

## Further reading

- `/docs/01-architecture.md`
- `/docs/02-database-schema.sql`
- `/docs/03-api-contract.yaml`
- `/docs/05-test-strategy.md`
