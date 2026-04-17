# /project:scaffold-module

Scaffolds a new business module in `civio-cloud` with the full layer stack: model, schema, repository, service, router, and tests.

## Arguments
`$ARGUMENTS` — module name in snake_case (e.g. `announcements`, `payment_orders`)

## Steps

1. Create the SQLAlchemy model at `civio-cloud/src/models/$ARGUMENTS.py`
   - Extend `Base` and `TimestampMixin`
   - Primary key `id: UUID`
   - Include `community_id: UUID` if tenant-scoped
   - Define relationships where relevant

2. Create Pydantic schemas at `civio-cloud/src/schemas/$ARGUMENTS.py`
   - `${Module}Create` — fields required to create
   - `${Module}Update` — all fields optional
   - `${Module}Read` — response shape (NEVER includes password hashes)

3. Create repository at `civio-cloud/src/repositories/${ARGUMENTS}_repo.py`
   - Extend `BaseRepository[${Model}]`
   - Add any domain-specific query methods

4. Create service at `civio-cloud/src/services/${ARGUMENTS}_service.py`
   - Inject repository and any other services via `__init__`
   - One class method per use case
   - No DB session management; rely on caller's transaction

5. Create router at `civio-cloud/src/api/v1/$ARGUMENTS.py`
   - Use `APIRouter(prefix="/$ARGUMENTS", tags=["$ARGUMENTS"])`
   - Depends on `get_current_user` for auth
   - Follow endpoint naming: GET list, POST create, GET/PATCH/DELETE by id
   - Register in `src/api/v1/__init__.py`

6. Create Alembic migration
   ```bash
   cd civio-cloud
   poetry run alembic revision --autogenerate -m "add_$ARGUMENTS"
   ```
   Review the generated file.

7. Create unit tests:
   - `tests/unit/services/test_${ARGUMENTS}_service.py` — mock repository, test each service method
   - `tests/unit/repositories/test_${ARGUMENTS}_repo.py` — test query methods with in-memory SQLite

8. Create integration test:
   - `tests/integration/api/test_${ARGUMENTS}.py` — test each endpoint via httpx AsyncClient

9. Update `docs/03-api-contract.yaml` with the new endpoints

10. Run verification:
    ```bash
    cd civio-cloud
    poetry run ruff check src/ tests/
    poetry run ruff format --check src/ tests/
    poetry run mypy src/ --strict
    poetry run alembic upgrade head
    poetry run alembic check
    poetry run pytest tests/unit -x -q
    poetry run pytest tests/integration -x -q
    ```

11. Only if ALL checks pass, commit with message:
    ```
    feat($ARGUMENTS): scaffold module with model, service, router, tests
    ```
