# CLAUDE.md — civio-cloud

## Scope
This subproject is the **cloud control plane**: a Python FastAPI service that is the source of truth for all community, user, SIP endpoint, token ledger, call log, and sync state data. It also hosts async workers that consume events from RabbitMQ.

Deployed as two container images from the same codebase:
- `civio-cloud-api` — FastAPI HTTP server (entry point: `src/main.py`)
- `civio-cloud-worker` — RabbitMQ consumer (entry point: `src/worker.py`)

## Tech stack (pinned)

```
python = "3.12"
fastapi = "^0.115"
uvicorn = {extras = ["standard"], version = "^0.34"}
sqlalchemy = {extras = ["asyncio"], version = "^2.0.36"}
asyncpg = "^0.30"
alembic = "^1.14"
pydantic = "^2.10"
pydantic-settings = "^2.7"
python-jose = {extras = ["cryptography"], version = "^3.3"}
passlib = {extras = ["bcrypt"], version = "^1.7"}
aio-pika = "^9.5"
redis = {extras = ["hiredis"], version = "^5.2"}
structlog = "^24.4"
httpx = "^0.28"
tenacity = "^9.0"

[tool.poetry.group.dev.dependencies]
pytest = "^8.3"
pytest-asyncio = "^0.24"
pytest-cov = "^6.0"
ruff = "^0.8"
mypy = "^1.13"
httpx = "^0.28"
```

Use Poetry. Keep `pyproject.toml` as the source of truth.

## Directory layout

```
civio-cloud/
├── CLAUDE.md                       this file
├── pyproject.toml
├── poetry.lock
├── Dockerfile                      multi-stage, python:3.12-slim
├── docker-compose.yml              local dev for just this service
├── alembic.ini
├── .env.example
├── src/
│   ├── __init__.py
│   ├── main.py                     FastAPI app factory
│   ├── worker.py                   worker entry point
│   ├── core/
│   │   ├── config.py               pydantic-settings Settings
│   │   ├── database.py             async engine, session factory, get_db
│   │   ├── security.py             JWT, password hashing, OTP
│   │   ├── dependencies.py         auth deps, current_user, require_role
│   │   ├── event_bus.py            aio-pika wrapper, EventPublisher class
│   │   ├── redis_client.py         async Redis client
│   │   ├── logging.py              structlog setup
│   │   └── exceptions.py           custom exceptions + handlers
│   ├── models/                     SQLAlchemy DeclarativeBase models
│   │   ├── base.py                 Base, TimestampMixin
│   │   ├── community.py
│   │   ├── unit.py
│   │   ├── user.py
│   │   ├── user_unit_relation.py
│   │   ├── sip_endpoint.py
│   │   ├── friend_mapping.py
│   │   ├── token_ledger.py
│   │   ├── call_log.py
│   │   ├── billing_record.py
│   │   ├── sync_event.py
│   │   └── sync_state.py
│   ├── schemas/                    Pydantic request/response models
│   │   ├── auth.py
│   │   ├── community.py
│   │   ├── user.py
│   │   ├── sip.py
│   │   ├── token.py
│   │   ├── sync.py
│   │   └── cdr.py
│   ├── repositories/
│   │   ├── base.py                 BaseRepository[T] generic
│   │   ├── community_repo.py
│   │   ├── unit_repo.py
│   │   ├── user_repo.py
│   │   ├── sip_endpoint_repo.py
│   │   ├── friend_repo.py
│   │   ├── token_ledger_repo.py
│   │   ├── call_log_repo.py
│   │   ├── sync_event_repo.py
│   │   └── sync_state_repo.py
│   ├── services/
│   │   ├── auth_service.py
│   │   ├── tenant_service.py
│   │   ├── sip_provisioning_service.py
│   │   ├── call_policy_service.py   ← decides allow/deny for each call
│   │   ├── token_service.py
│   │   ├── billing_service.py
│   │   ├── sync_service.py
│   │   └── messaging_service.py
│   ├── api/
│   │   ├── v1/
│   │   │   ├── __init__.py         aggregates all v1 routers
│   │   │   ├── auth.py
│   │   │   ├── communities.py
│   │   │   ├── units.py
│   │   │   ├── users.py
│   │   │   ├── sip.py              includes /authorize callback
│   │   │   ├── tokens.py
│   │   │   ├── cdr.py
│   │   │   ├── sync.py
│   │   │   ├── messaging.py
│   │   │   └── admin.py
│   │   └── deps.py                 common deps (get_current_user, etc.)
│   ├── events/
│   │   ├── schemas.py              CloudEvent models
│   │   ├── producers.py            publish helpers
│   │   └── consumers/
│   │       ├── cdr_consumer.py
│   │       ├── billing_consumer.py
│   │       └── audit_consumer.py
│   └── migrations/
│       ├── env.py                  async Alembic config
│       └── versions/
└── tests/
    ├── conftest.py
    ├── unit/
    │   ├── services/
    │   └── repositories/
    └── integration/
        ├── api/
        ├── events/
        └── sync/
```

## Key classes and their contracts

Claude Code MUST implement these classes with these signatures. Add helpers as needed, but do not change these.

### `core/database.py`

```python
engine: AsyncEngine
AsyncSessionLocal: async_sessionmaker[AsyncSession]

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency. Commits on success, rolls back on exception."""
```

### `core/security.py`

```python
def hash_password(plain: str) -> str: ...
def verify_password(plain: str, hashed: str) -> bool: ...
def create_access_token(sub: str, extra: dict | None = None) -> str: ...
def create_refresh_token(sub: str) -> str: ...
def decode_token(token: str) -> TokenPayload: ...
def generate_otp(length: int = 6) -> str: ...
```

### `core/event_bus.py`

```python
class EventPublisher:
    async def connect(self) -> None: ...
    async def publish(self, event_type: str, data: dict, tenant_id: UUID) -> None: ...
    async def close(self) -> None: ...
```

### `repositories/base.py`

```python
class BaseRepository(Generic[ModelT]):
    def __init__(self, model: type[ModelT], session: AsyncSession) -> None: ...
    async def get(self, id: UUID) -> ModelT | None: ...
    async def list(self, *, skip: int = 0, limit: int = 100, **filters: object) -> Sequence[ModelT]: ...
    async def create(self, **kwargs: object) -> ModelT: ...
    async def update(self, id: UUID, **kwargs: object) -> ModelT: ...
    async def delete(self, id: UUID) -> None: ...
```

### `services/auth_service.py`

```python
class AuthService:
    def __init__(self, user_repo: UserRepository, redis: Redis) -> None: ...
    async def send_otp(self, mobile: str) -> OtpChallenge: ...
    async def verify_otp(self, challenge_id: UUID, code: str) -> TokenPair: ...
    async def refresh(self, refresh_token: str) -> TokenPair: ...
```

### `services/call_policy_service.py`

This is the **most important service** in the system. Every INVITE hits it via the `/api/v1/sip/authorize` callback.

```python
class CallPolicyService:
    async def authorize(
        self,
        caller_sip_uri: str,
        callee_sip_uri: str,
    ) -> CallAuthDecision:
        """
        Decision order:
          1. Resolve caller + callee to users; if either missing → DENY(unknown_user)
          2. If cross-community → DENY(cross_community)
          3. If callee is admin center → ALLOW(admin_always)
          4. If caller+callee are in the same unit (family) → ALLOW(family)
          5. If caller+callee are friends (active mapping) → ALLOW(friend)
          6. Check token balance; if 0 → DENY(no_token)
          7. ALLOW(friend) with token cost estimate
        Decision is ALWAYS logged to audit queue asynchronously.
        """
```

### `services/sync_service.py`

```python
class SyncService:
    async def generate_full_snapshot(self, community_id: UUID) -> FullSnapshot: ...
    async def get_delta_since(self, community_id: UUID, version: int) -> DeltaBatch: ...
    async def acknowledge(self, community_id: UUID, version: int, merkle_root: str) -> SyncAckResult: ...
    async def emit_event(self, community_id: UUID, event_type: str, payload: dict) -> None: ...
```

## API endpoints (must exist, follow OpenAPI spec)

See `docs/03-api-contract.yaml` for the authoritative contract. Claude Code MUST regenerate `docs/03-api-contract.yaml` from FastAPI's built-in OpenAPI output whenever endpoints change:

```bash
python -c "import json; from src.main import app; print(json.dumps(app.openapi(), indent=2))" > docs/03-api-contract.yaml
```

Minimum required endpoints:

```
POST   /api/v1/auth/otp/send
POST   /api/v1/auth/otp/verify
POST   /api/v1/auth/refresh
POST   /api/v1/auth/logout

GET    /api/v1/communities
POST   /api/v1/communities              admin only
GET    /api/v1/communities/{id}
PATCH  /api/v1/communities/{id}

GET    /api/v1/units
POST   /api/v1/units                    admin only
PATCH  /api/v1/units/{id}

GET    /api/v1/users/me
GET    /api/v1/users
POST   /api/v1/users                    admin only
PATCH  /api/v1/users/{id}

POST   /api/v1/sip/authorize            OpenSIPS callback — NO JWT, uses shared secret
GET    /api/v1/sip/endpoints/{user_id}  returns endpoint metadata, NEVER password

POST   /api/v1/friends                  create friend mapping
DELETE /api/v1/friends/{id}
GET    /api/v1/friends

GET    /api/v1/tokens/balance?scope=user|community
POST   /api/v1/tokens/topup
GET    /api/v1/tokens/ledger

GET    /api/v1/cdr
GET    /api/v1/cdr/{id}

GET    /api/v1/sync/full                edge-only, signed request
GET    /api/v1/sync/delta?since=<v>     edge-only
POST   /api/v1/sync/ack                 edge-only

GET    /api/v1/messaging/announcements
POST   /api/v1/messaging/announcements  admin only
GET    /api/v1/messaging/tasks
POST   /api/v1/messaging/tasks
PATCH  /api/v1/messaging/tasks/{id}

GET    /api/v1/admin/health
GET    /api/v1/admin/sync-status
```

## Testing requirements

Tests MUST pass for a feature to be considered done.

### Test organisation

```
tests/
├── conftest.py                     shared fixtures: db, client, event bus
├── unit/
│   ├── services/
│   │   ├── test_auth_service.py
│   │   ├── test_call_policy_service.py   ← exhaustive matrix
│   │   ├── test_token_service.py
│   │   └── ...
│   └── repositories/
│       └── ...
└── integration/
    ├── api/
    │   ├── test_auth_flow.py
    │   ├── test_sip_authorize.py
    │   └── ...
    ├── events/
    │   ├── test_cdr_consumer.py
    │   └── ...
    └── sync/
        └── test_full_and_delta_sync.py
```

### Coverage targets

- Service layer: >= 90% line coverage
- Repository layer: >= 85%
- API routers: >= 80% (integration tests cover most paths)
- Overall: >= 80%

Run with: `pytest --cov=src --cov-report=term-missing --cov-fail-under=80`

### Call policy test matrix (mandatory)

`test_call_policy_service.py` MUST include at least these scenarios:

| Scenario | Expected |
|---|---|
| Same unit, both verified | ALLOW(family) |
| Different unit, active friend mapping | ALLOW(friend), cost > 0 |
| Different unit, no friend mapping | DENY(not_friend) |
| Cross community | DENY(cross_community) |
| Callee is admin center | ALLOW(admin_always), cost 0 |
| Caller has zero tokens, no community coverage | DENY(no_token) |
| Caller has zero tokens, community pays | ALLOW(friend), scope=community |
| Callee SIP URI unknown | DENY(unknown_user) |
| Caller auth_status = Revoked | DENY(user_revoked) |

## Verification commands

Run all of these before considering a task complete:

```bash
poetry run ruff check src/ tests/
poetry run ruff format --check src/ tests/
poetry run mypy src/ --strict
poetry run alembic check
poetry run pytest tests/unit -x -q --cov=src --cov-fail-under=80
poetry run pytest tests/integration -x -q
docker compose build
```

## Migration workflow

```bash
# 1. Edit models in src/models/
# 2. Generate migration
poetry run alembic revision --autogenerate -m "add_friend_mapping"
# 3. Review the generated file in src/migrations/versions/
# 4. Apply
poetry run alembic upgrade head
# 5. Commit both the model change AND the migration together
```

If `alembic check` reports drift, there is an unmigrated model change. Fix it before continuing.

## Event bus conventions

Events follow CloudEvents 1.0:

```python
{
    "specversion": "1.0",
    "id": "evt_<uuid4>",
    "source": "civio-cloud",            # or "civio-edge:<community_id>"
    "type": "call.ended",
    "time": "2025-...",
    "tenantid": "<community_id>",       # extension attribute
    "datacontenttype": "application/json",
    "data": { ... }
}
```

Exchange names:
- `civio.events` (topic) — main event bus
- `civio.events.dlx` (topic) — dead letter exchange

Routing keys: `<domain>.<action>` — e.g. `call.started`, `call.ended`, `cdr.created`, `billing.charged`, `sync.requested`, `user.provisioned`.

Consumer queues:
- `cdr.processor` — bound to `cdr.created`
- `billing.worker` — bound to `billing.charge`
- `audit.logger` — bound to `#` (all events)

Every consumer MUST:
- Use manual ack
- Wrap processing in try/except, nack on failure with `requeue=False`
- Store `event.id` in `processed_events` table for idempotency
- Have a DLQ configured with 5-minute message TTL
