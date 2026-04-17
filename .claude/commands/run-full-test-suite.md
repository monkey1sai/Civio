# /project:run-full-test-suite

Runs every verification gate across the entire monorepo. Use this before any PR or when you want to confirm the whole system is green.

## Steps

1. **Root-level lint**
   ```bash
   pre-commit run --all-files
   ```

2. **Cloud: lint + types + unit + integration**
   ```bash
   cd civio-cloud
   poetry install --sync
   poetry run ruff check src/ tests/
   poetry run ruff format --check src/ tests/
   poetry run mypy src/ --strict
   poetry run bandit -r src/ -ll
   poetry run alembic check
   poetry run pytest tests/unit -x -q --cov=src --cov-fail-under=80
   poetry run pytest tests/integration -x -q
   cd ..
   ```

3. **Edge: lint + types + unit**
   ```bash
   for service in sync_agent event_publisher auth_callback; do
     cd civio-edge/$service
     poetry install --sync
     poetry run ruff check src/
     poetry run mypy src/ --strict
     poetry run pytest tests -x -q
     cd ../..
   done
   ```

4. **Flutter: format + analyze + unit**
   ```bash
   cd civio-app
   flutter pub get
   dart format --set-exit-if-changed lib/ test/
   dart analyze --fatal-infos lib/ test/
   flutter test --coverage
   cd ..
   ```

5. **Docker builds**
   ```bash
   docker compose -f docker-compose.yml config -q
   docker compose -f docker-compose.yml build
   docker compose -f civio-cloud/docker-compose.yml build
   docker compose -f civio-edge/docker-compose.yml build
   ```

6. **Contract tests** (requires cloud running)
   ```bash
   docker compose up -d postgres redis rabbitmq
   cd civio-cloud
   poetry run uvicorn src.main:app --port 8000 &
   sleep 5
   poetry run schemathesis run ../docs/03-api-contract.yaml \
     --base-url http://localhost:8000 \
     --checks all
   kill %1
   cd ..
   ```

7. **E2E** (SIPp + full stack)
   ```bash
   docker compose -f docker-compose.e2e.yml up -d
   ./scripts/e2e.sh
   docker compose -f docker-compose.e2e.yml down -v
   ```

8. **Security scan**
   ```bash
   trufflehog git file://. --since-commit HEAD~50
   docker scout cves civio-cloud:latest || true   # don't fail yet, warn
   docker scout cves civio-edge:latest || true
   ```

9. **Report**
   - If every step passed: print ✅ and proceed
   - If any failed: print ❌ with which step, do NOT proceed

## Notes

- This suite takes 10-15 minutes on a modern laptop
- Run before every PR merge
- CI runs the same suite with parallel jobs
